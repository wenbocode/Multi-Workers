import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import {
	type Api,
	type AssistantMessage,
	createAssistantMessageEventStream,
	InMemoryCredentialStore,
	type Model,
} from "@earendil-works/pi-ai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type {
	ExtensionAPI,
	ExtensionCommandContext,
	ExtensionContext,
	ProviderConfig,
} from "../../src/core/extensions/types.ts";
import { ModelRegistry } from "../../src/core/model-registry.ts";
import { ModelRuntime } from "../../src/core/model-runtime.ts";
import { registerMwCommands } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { configureLocalCodex } from "../../src/extensions/agent-team-loop/shared/codex-local.ts";
import {
	acquireModelSlot,
	concurrencyRoute,
	formatConcurrencyState,
	readConcurrencyState,
	setConcurrencyLimit,
} from "../../src/extensions/agent-team-loop/shared/model-concurrency.ts";
import {
	installConcurrencyProviders,
	limitProviderStream,
	registerModelConcurrency,
} from "../../src/extensions/agent-team-loop/shared/model-concurrency-extension.ts";

let directory: string;
beforeEach(() => {
	directory = fs.mkdtempSync(path.join(os.tmpdir(), "mw-concurrency-"));
	vi.stubEnv("MW_CONCURRENCY_DIR", directory);
});
afterEach(() => {
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	vi.unstubAllGlobals();
	fs.rmSync(directory, { recursive: true, force: true });
});

const model: Model<Api> = {
	id: "model-a",
	name: "Fake model",
	provider: "fake",
	api: "openai-completions",
	baseUrl: "https://invalid.invalid",
	reasoning: false,
	input: ["text"],
	contextWindow: 10000,
	maxTokens: 100,
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
};
function message(selected = model): AssistantMessage {
	return {
		role: "assistant",
		api: selected.api,
		provider: selected.provider,
		model: selected.id,
		content: [{ type: "toolCall", id: "t1", name: "lookup", arguments: { value: 42 } }],
		stopReason: "toolUse",
		timestamp: 1,
		usage: {
			input: 1,
			output: 2,
			cacheRead: 0,
			cacheWrite: 0,
			totalTokens: 3,
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
		},
	};
}
async function waiting(count = 1): Promise<void> {
	await vi.waitFor(() =>
		expect(readConcurrencyState().requests.filter((r) => r.phase === "waiting")).toHaveLength(count),
	);
}

describe("shared concurrency state", () => {
	it("normalizes aliases, rejects invalid limits, and leaves default requests unrestricted", async () => {
		expect(concurrencyRoute("openai-codex-local/gpt-a")).toBe("codex/gpt-a");
		expect(concurrencyRoute("openai-codex/gpt-a")).toBe("codex/gpt-a");
		expect(concurrencyRoute("anthropic/*")).toBe("claude/*");
		await (await acquireModelSlot("fake/model-a"))();
		expect(fs.existsSync(path.join(directory, "state.json"))).toBe(false);
		for (const value of [0, -1, 1.5, Number.NaN, Number.POSITIVE_INFINITY])
			await expect(setConcurrencyLimit("fake/model-a", value)).rejects.toThrow("positive integer");
		for (const value of ["fake", "fake/", "fake/a b", "fake/a*", "codex_cli/a"])
			expect(() => concurrencyRoute(value)).toThrow();
		expect(fs.existsSync(path.join(directory, "state.json"))).toBe(false);
	});

	it("enforces exact and aggregate limits while allowing other providers", async () => {
		await setConcurrencyLimit("codex/*", 2);
		await setConcurrencyLimit("codex/a", 1);
		const first = await acquireModelSlot("openai-codex-local/a");
		const second = await acquireModelSlot("codex/b");
		const next = acquireModelSlot("openai-codex/a");
		await waiting();
		const other = await acquireModelSlot("fake/a");
		expect(formatConcurrencyState(readConcurrencyState())).toContain("codex/*: limit=2 active=2 waiting=1");
		await second();
		await delay(220);
		expect(readConcurrencyState().requests.filter((r) => r.phase === "waiting")).toHaveLength(1);
		await first();
		await (await next)();
		await other();
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it("hot changes preserve active leases and admit queued work using the latest limit", async () => {
		await setConcurrencyLimit("fake/a", 2);
		const a = await acquireModelSlot("fake/a");
		const b = await acquireModelSlot("fake/a");
		await setConcurrencyLimit("fake/a", 1);
		const c = acquireModelSlot("fake/a");
		await waiting();
		await a();
		await delay(220);
		expect(readConcurrencyState().requests.filter((r) => r.phase === "waiting")).toHaveLength(1);
		await setConcurrencyLimit("fake/a", 2);
		const releaseC = await c;
		const d = acquireModelSlot("fake/a");
		await waiting();
		await setConcurrencyLimit("fake/a", undefined);
		await (await d)();
		await releaseC();
		await b();
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it("cancels and times out waiting requests without losing the active lease", async () => {
		await setConcurrencyLimit("fake/a", 1);
		const release = await acquireModelSlot("fake/a");
		const abort = new AbortController();
		const canceled = acquireModelSlot("fake/a", { signal: abort.signal });
		const canceledResult = expect(canceled).rejects.toThrow();
		await waiting();
		abort.abort();
		await canceledResult;
		await expect(acquireModelSlot("fake/a", { waitMs: 40 })).rejects.toThrow("queue timed out");
		expect(readConcurrencyState().requests).toHaveLength(1);
		await release();
	});

	it("corrupt state and an occupied transaction lock fail closed", async () => {
		fs.writeFileSync(path.join(directory, "state.json"), "not-json");
		await expect(acquireModelSlot("fake/a")).rejects.toThrow("Cannot read");
		fs.writeFileSync(path.join(directory, "state.json"), JSON.stringify({ version: 1, limits: {}, requests: [] }));
		fs.writeFileSync(path.join(directory, "state.lock"), "held");
		await expect(acquireModelSlot("fake/a", { waitMs: 50 })).rejects.toThrow("queue timed out");
		expect(fs.readFileSync(path.join(directory, "state.lock"), "utf8")).toBe("held");
	});

	it("coordinates real child processes and reclaims a dead process lease", async () => {
		await setConcurrencyLimit("fake/a", 2);
		const source = fileURLToPath(
			new URL("../../src/extensions/agent-team-loop/shared/model-concurrency.ts", import.meta.url),
		);
		const script = path.join(directory, "client.mjs");
		fs.writeFileSync(
			script,
			`import { acquireModelSlot } from ${JSON.stringify(pathToFileURL(source).href)};
import { setTimeout as delay } from 'node:timers/promises';
import * as fs from 'node:fs';
import * as path from 'node:path';
const release = await acquireModelSlot('fake/a');
const marker = path.join(process.env.MW_CONCURRENCY_DIR, process.pid + '.active');
fs.writeFileSync(marker, '');
console.log(fs.readdirSync(process.env.MW_CONCURRENCY_DIR).filter(name => name.endsWith('.active')).length);
await delay(300);
fs.unlinkSync(marker);
if (process.argv[2] !== 'crash') await release();
`,
		);
		let peak = 0;
		const children = Array.from({ length: 6 }, () =>
			spawn(process.execPath, [script], { windowsHide: true, stdio: ["ignore", "pipe", "pipe"] }),
		);
		try {
			await Promise.all(
				children.map(
					(child) =>
						new Promise<void>((resolve, reject) => {
							let stderr = "";
							child.stdout.on("data", (data: Buffer) => {
								for (const line of data.toString().trim().split(/\r?\n/)) {
									peak = Math.max(peak, Number(line));
								}
							});
							child.stderr.on("data", (data: Buffer) => {
								stderr += data.toString();
							});
							child.on("error", reject);
							child.on("close", (code) => (code === 0 ? resolve() : reject(new Error(stderr))));
						}),
				),
			);
			expect(peak).toBe(2);
			expect(fs.readdirSync(directory).filter((name) => name.endsWith(".active"))).toEqual([]);
			expect(readConcurrencyState().requests).toEqual([]);
			const crash = spawn(process.execPath, [script, "crash"], { windowsHide: true, stdio: "ignore" });
			await new Promise<void>((resolve, reject) => {
				crash.on("error", reject);
				crash.on("close", () => resolve());
			});
			expect(JSON.parse(fs.readFileSync(path.join(directory, "state.json"), "utf8")).requests).toHaveLength(1);
			await (await acquireModelSlot("fake/a"))();
			expect(readConcurrencyState().requests).toEqual([]);
		} finally {
			for (const child of children) if (child.exitCode === null) child.kill();
		}
	}, 15_000);
});

describe("extension integration", () => {
	it("real PM/worker ModelRuntimes preserve auth and tool events across refresh and repeated installation", async () => {
		await setConcurrencyLimit("fake/model-a", 1);
		let active = 0;
		let peak = 0;
		const optionsSeen: string[] = [];
		const config: ProviderConfig = {
			api: model.api,
			apiKey: "fake-api-key",
			models: [model],
			streamSimple: (selected, _context, options) => {
				peak = Math.max(peak, ++active);
				optionsSeen.push(options?.apiKey ?? "missing");
				const stream = createAssistantMessageEventStream();
				void delay(80).then(() => {
					active--;
					stream.push({ type: "done", reason: "toolUse", message: message(selected) });
					stream.end(message(selected));
				});
				return stream;
			},
		};
		const runtimes: ModelRuntime[] = [];
		for (const worker of [false, true]) {
			vi.stubEnv("PI_WORKER_TASK", worker ? "Z:/control/.agenticdoc/key/workers/t/task.md" : "");
			const runtime = await ModelRuntime.create({ credentials: new InMemoryCredentialStore(), modelsPath: null });
			runtime.registerProvider("fake", config);
			const ctx = {
				modelRegistry: new ModelRegistry(runtime),
				model,
				ui: { setStatus: vi.fn() },
			} as unknown as ExtensionContext;
			const hooks = new Map<string, (event: never, context: ExtensionContext) => void>();
			registerModelConcurrency({
				on: (name: string, handler: (event: never, context: ExtensionContext) => void) => hooks.set(name, handler),
			} as unknown as ExtensionAPI);
			hooks.get("session_start")?.({} as never, ctx);
			await ctx.modelRegistry.refresh({ allowNetwork: false });
			hooks.get("context")?.({} as never, ctx);
			hooks.get("model_select")?.({} as never, ctx);
			runtimes.push(runtime);
		}
		const outputs = await Promise.all(
			runtimes.map((runtime, i) =>
				i === 0 ? runtime.complete(model, { messages: [] }) : runtime.completeSimple(model, { messages: [] }),
			),
		);
		expect(peak).toBe(1);
		expect(optionsSeen).toEqual(["fake-api-key", "fake-api-key"]);
		for (const output of outputs) expect(output.content).toEqual(message().content);
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it("provider exceptions, error events and waiting abort release slots without sending extra requests", async () => {
		await setConcurrencyLimit("fake/model-a", 1);
		const thrown = await limitProviderStream(
			model,
			() => {
				throw new Error("provider failed");
			},
			undefined,
			directory,
		).result();
		expect(thrown.errorMessage).toBe("provider failed");
		const failed = await limitProviderStream(
			model,
			() => {
				const stream = createAssistantMessageEventStream();
				const error = { ...message(), stopReason: "error" as const, errorMessage: "HTTP 500" };
				stream.push({ type: "error", reason: "error", error });
				stream.end(error);
				return stream;
			},
			undefined,
			directory,
		).result();
		expect(failed.errorMessage).toBe("HTTP 500");
		const release = await acquireModelSlot("fake/model-a");
		const abort = new AbortController();
		const start = vi.fn(() => createAssistantMessageEventStream());
		const result = limitProviderStream(model, start, abort.signal, directory).result();
		await waiting();
		abort.abort();
		expect((await result).stopReason).toBe("aborted");
		expect(start).not.toHaveBeenCalled();
		await release();
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it("actual /mw command supports set/show/clear and rejects invalid input without mutation", async () => {
		const runtime = await ModelRuntime.create({ credentials: new InMemoryCredentialStore(), modelsPath: null });
		const notify = vi.fn();
		const ctx = {
			hasUI: true,
			modelRegistry: new ModelRegistry(runtime),
			ui: { notify, setStatus: vi.fn() },
		} as unknown as ExtensionCommandContext;
		const commands = new Map<
			string,
			{ handler: (args: string, context: ExtensionCommandContext) => Promise<void> }
		>();
		const pi = {
			registerCommand: (
				name: string,
				command: { handler: (args: string, context: ExtensionCommandContext) => Promise<void> },
			) => commands.set(name, command),
		} as unknown as ExtensionAPI;
		registerMwCommands(pi, directory, {} as never, {} as never, {} as never, path.join(directory, ".agenticdoc"));
		await commands.get("mw")?.handler("concurrency set openai-codex-local/gpt-a 2", ctx);
		expect(readConcurrencyState().limits).toEqual({ "codex/gpt-a": 2 });
		const before = fs.readFileSync(path.join(directory, "state.json"), "utf8");
		await commands.get("mw")?.handler("concurrency set codex/gpt-a 0", ctx);
		expect(fs.readFileSync(path.join(directory, "state.json"), "utf8")).toBe(before);
		await commands.get("mw")?.handler("concurrency show", ctx);
		expect(notify).toHaveBeenCalledWith(expect.stringContaining("limit=2 active=0 waiting=0"), "info");
		await commands.get("mw")?.handler("concurrency clear codex/gpt-a", ctx);
		expect(readConcurrencyState().limits).toEqual({});
	});

	it("local Codex provider remains routed through the limiter after re-registration", async () => {
		await setConcurrencyLimit("codex/gpt-5.6-sol", 1);
		fs.mkdirSync(path.join(directory, ".mw"));
		fs.writeFileSync(
			path.join(directory, ".mw/codex-local.json"),
			JSON.stringify({ version: 1, url: "http://127.0.0.1:7010", token: "fake-token-at-least-24-characters" }),
		);
		const runtime = await ModelRuntime.create({ credentials: new InMemoryCredentialStore(), modelsPath: null });
		const pi = {
			registerProvider: (id: string, config: ProviderConfig) => runtime.registerProvider(id, config),
		} as unknown as ExtensionAPI;
		const ctx = {
			modelRegistry: new ModelRegistry(runtime),
			ui: { setStatus: vi.fn() },
		} as unknown as ExtensionContext;
		configureLocalCodex(pi, directory);
		installConcurrencyProviders(ctx);
		configureLocalCodex(pi, directory);
		installConcurrencyProviders(ctx);
		await ctx.modelRegistry.refresh({ allowNetwork: false });
		const selected = runtime.getModel("openai-codex-local", "gpt-5.6-sol");
		if (!selected) throw new Error("missing local model");
		const fetcher = vi.fn<typeof fetch>(async (url) =>
			String(url).endsWith("/status")
				? Response.json({ status: "ready", backend: "codex-cli", protocol: 2, active: [] })
				: new Response('{"type":"result","text":"ok","toolCalls":[]}\n'),
		);
		const result = await runtime.completeSimple(selected, { messages: [] }, { fetch: fetcher });
		expect(result.content).toEqual([{ type: "text", text: "ok" }]);
		expect(readConcurrencyState().requests).toEqual([]);
	});
});
