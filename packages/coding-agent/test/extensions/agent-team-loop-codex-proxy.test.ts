import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { type Api, type Context, InMemoryCredentialStore, type Model } from "@earendil-works/pi-ai";
import { afterEach, describe, expect, it, vi } from "vitest";
import { AuthStorage } from "../../src/core/auth-storage.ts";
import type {
	ExtensionAPI,
	ExtensionCommandContext,
	ExtensionContext,
	ProviderConfig,
} from "../../src/core/extensions/types.ts";
import { ModelRegistry } from "../../src/core/model-registry.ts";
import { ModelRuntime } from "../../src/core/model-runtime.ts";
import { readMonitorState, renderMonitorLines } from "../../src/extensions/agent-team-loop/autopilot/monitor.ts";
import { registerMwCommands } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { registerLocalCodex, streamLocalCodex } from "../../src/extensions/agent-team-loop/shared/codex-local.ts";
import * as proxy from "../../src/extensions/agent-team-loop/shared/codex-proxy.ts";
import { recordWindowModel } from "../../src/extensions/agent-team-loop/shared/dispatch-models.ts";

const token = "test-secret-proxy-token-at-least-24-characters";
const roots: string[] = [];
function project(): string {
	const root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-proxy-test-"));
	roots.push(root);
	fs.mkdirSync(path.join(root, ".mw"));
	fs.mkdirSync(path.join(root, ".agenticdoc"));
	fs.writeFileSync(
		path.join(root, ".mw/codex-local.json"),
		JSON.stringify({ version: 1, url: "http://127.0.0.1:7010", token }),
	);
	return root;
}
const ready = { status: "ready", backend: "codex-cli", protocol: 2, active: [], concurrency: 2 };
const context: Context = { messages: [{ role: "user", content: "hi", timestamp: 1 }] };
const model: Model<Api> = {
	id: "gpt-5.6-sol",
	name: "Codex",
	provider: proxy.LOCAL_CODEX_PROVIDER,
	api: "openai-codex-responses",
	baseUrl: "http://127.0.0.1:7010",
	input: ["text"],
	reasoning: true,
	contextWindow: 10000,
	maxTokens: 1000,
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
};

afterEach(() => {
	vi.useRealTimers();
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	vi.unstubAllGlobals();
	for (const root of roots.splice(0)) fs.rmSync(root, { recursive: true, force: true });
});

describe("managed Codex proxy", () => {
	it("routes PM and dual-root workers while preserving the same stored OAuth file", async () => {
		const authRoot = project();
		const oldAuth = { type: "oauth" as const, access: "old-access", refresh: "old-refresh", expires: 1 };
		const authPath = path.join(authRoot, "auth.json");
		const originalAuthBytes = JSON.stringify({ "openai-codex": oldAuth }, null, 2);
		fs.writeFileSync(authPath, originalAuthBytes);
		const credentials = AuthStorage.create(authPath);
		for (const worker of [false, true]) {
			const root = project();
			vi.spyOn(process, "cwd").mockReturnValue(worker ? path.join(root, "game") : root);
			vi.stubEnv("PI_WORKER_TASK", worker ? path.join(root, ".agenticdoc/key/workers/task/task.md") : "");
			vi.stubEnv("MW_CODEX_LOCAL_URL", "");
			const runtime = await ModelRuntime.create({ credentials, modelsPath: null });
			const handlers = new Map<string, (event: never, ctx: ExtensionContext) => Promise<void> | void>();
			const ctx = {
				cwd: root,
				model: runtime.getModel("openai-codex", model.id),
				modelRegistry: new ModelRegistry(runtime),
				ui: { setStatus: vi.fn() },
			} as unknown as ExtensionContext;
			const pi = {
				registerProvider: (id: string, config: ProviderConfig) => runtime.registerProvider(id, config),
				on: (name: string, handler: (event: never, ctx: ExtensionContext) => Promise<void> | void) =>
					handlers.set(name, handler),
				setModel: vi.fn(async (next: Model<Api>) => {
					ctx.model = next;
					return true;
				}),
			} as unknown as ExtensionAPI;
			const fetcher = vi.fn<typeof fetch>(async (url) =>
				String(url).endsWith("/status")
					? Response.json(ready)
					: new Response('{"type":"result","text":"ok","toolCalls":[]}\n'),
			);
			vi.stubGlobal("fetch", fetcher);
			registerLocalCodex(pi);
			try {
				await handlers.get("session_start")?.({} as never, ctx);
				expect(ctx.model?.provider).toBe(proxy.LOCAL_CODEX_PROVIDER);
				const output = await runtime.completeSimple(ctx.model as Model<Api>, context, { fetch: fetcher });
				expect(output.stopReason).toBe("stop");
				const requestsBefore = fetcher.mock.calls.filter(([url]) => String(url).endsWith("/complete")).length;
				await handlers.get("turn_end")?.({} as never, ctx);
				await handlers.get("model_select")?.({ model: ctx.model } as never, ctx);
				expect(fetcher.mock.calls.filter(([url]) => String(url).endsWith("/complete"))).toHaveLength(
					requestsBefore,
				);
				expect(await credentials.read("openai-codex")).toEqual(oldAuth);
				expect(fs.readFileSync(authPath, "utf8")).toBe(originalAuthBytes);
				recordWindowModel(root, ctx.model);
				expect(fs.readFileSync(path.join(root, ".mw/window-model"), "utf8")).toBe(`codex/${model.id}\n`);
			} finally {
				await handlers.get("session_shutdown")?.({} as never, ctx);
			}
		}
	});

	it.each([401, 503])("preflight rejects HTTP %s before sending context", async (code) => {
		const fetcher = vi.fn<typeof fetch>(async () => new Response("no", { status: code }));
		const output = await streamLocalCodex(model, context, {
			fetch: fetcher,
			env: { MW_CODEX_LOCAL_TOKEN: token },
		}).result();
		expect(output.stopReason).toBe("error");
		expect(fetcher).toHaveBeenCalledTimes(1);
		expect(fetcher.mock.calls[0][0]).toBe(`${model.baseUrl}/status`);
	});

	it("heartbeat loss aborts a stalled body and clears the live request", async () => {
		vi.useFakeTimers();
		const root = project();
		const cancelled = vi.fn();
		const fetcher = vi.fn<typeof fetch>(async (url) =>
			String(url).endsWith("/status")
				? Response.json(ready)
				: new Response(new ReadableStream<Uint8Array>({ cancel: cancelled })),
		);
		const result = streamLocalCodex(
			model,
			context,
			{ fetch: fetcher, env: { MW_CODEX_LOCAL_TOKEN: token } },
			root,
		).result();
		await vi.advanceTimersByTimeAsync(1);
		expect(proxy.proxySnapshot(root)?.request?.phase).toBe("waiting for Codex");
		await vi.advanceTimersByTimeAsync(10_001);
		expect((await result).errorMessage).toContain("heartbeat lost");
		expect(cancelled).toHaveBeenCalled();
		expect(proxy.proxySnapshot(root)?.request).toBeUndefined();
	});

	it("continuous heartbeats cannot defeat the overall deadline", async () => {
		let pulse: ReturnType<typeof setInterval> | undefined;
		const fetcher = vi.fn<typeof fetch>(async (url) =>
			String(url).endsWith("/status")
				? Response.json(ready)
				: new Response(
						new ReadableStream<Uint8Array>({
							start(controller) {
								pulse = setInterval(
									() => controller.enqueue(new TextEncoder().encode('{"type":"heartbeat"}\n')),
									5,
								);
							},
							cancel() {
								clearInterval(pulse);
							},
						}),
					),
		);
		try {
			const output = await streamLocalCodex(model, context, {
				fetch: fetcher,
				timeoutMs: 60,
				env: { MW_CODEX_LOCAL_TOKEN: token },
			}).result();
			expect(output.stopReason).toBe("error");
			expect(output.errorMessage).toMatch(/timeout|aborted/i);
		} finally {
			clearInterval(pulse);
		}
	});

	it("existing monitor renders proxy activity, failures and stale data", () => {
		const root = project();
		proxy.setProxySnapshot(root, {
			...ready,
			checkedAt: Date.now() - 20_000,
			active: [{ id: "r", model: model.id, age_s: 9 }],
			timeout_s: 180,
			last_error: { at: Date.now() / 1000, error: "Codex request failed" },
		});
		const text = renderMonitorLines(readMonitorState(root, Date.now())).join("\n");
		expect(text).toContain("codex proxy: STALE ready");
		expect(text).toContain("waiting 9s / 180s");
		expect(text).toContain("Codex request failed");
		expect(text).not.toContain(token);
	});

	it("/mw command forwards proxy actions and enables the current model", async () => {
		const root = project();
		const runtime = await ModelRuntime.create({ credentials: new InMemoryCredentialStore(), modelsPath: null });
		const manager = vi.spyOn(proxy, "manageProxy").mockResolvedValue(ready);
		const commands = new Map<string, { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> }>();
		const pi = {
			registerCommand: (
				name: string,
				command: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
			) => commands.set(name, command),
			registerProvider: (id: string, config: ProviderConfig) => runtime.registerProvider(id, config),
			setModel: vi.fn(async () => true),
		} as unknown as ExtensionAPI;
		const ctx = {
			hasUI: true,
			model: runtime.getModel("openai-codex", model.id),
			modelRegistry: new ModelRegistry(runtime),
			ui: { notify: vi.fn() },
		} as unknown as ExtensionCommandContext;
		registerMwCommands(pi, root, {} as never, {} as never, {} as never, path.join(root, ".agenticdoc"));
		for (const command of ["start", "status", "check", "check --deep", "stop"])
			await commands.get("mw")?.handler(`proxy ${command}`, ctx);
		expect(manager.mock.calls.map((call) => call[1])).toEqual(["start", "status", "check", "check", "stop"]);
		expect(manager).toHaveBeenCalledWith(root, "check", model.id, true);
		expect(pi.setModel).toHaveBeenCalledWith(expect.objectContaining({ provider: proxy.LOCAL_CODEX_PROVIDER }));
		await commands.get("mw")?.handler("proxy start --unsafe", ctx);
		expect(manager).toHaveBeenCalledTimes(5);
	});
});
