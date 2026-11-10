import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import { createServer, type Server } from "node:http";
import * as os from "node:os";
import * as path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { fileURLToPath } from "node:url";
import { Agent } from "@earendil-works/pi-agent-core";
import {
	type Api,
	type AssistantMessage,
	type Context,
	createAssistantMessageEventStream,
	InMemoryCredentialStore,
	type Message,
	type Model,
	type Provider,
	type SimpleStreamOptions,
} from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { completeSummarization } from "../../src/core/compaction/compaction.ts";
import type {
	ExtensionAPI,
	ExtensionCommandContext,
	ExtensionContext,
	ProviderConfig,
} from "../../src/core/extensions/types.ts";
import { convertToLlm } from "../../src/core/messages.ts";
import { ModelRegistry } from "../../src/core/model-registry.ts";
import { ModelRuntime } from "../../src/core/model-runtime.ts";
import { SessionManager } from "../../src/core/session-manager.ts";
import { registerMwCommands } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import {
	configureLocalCodex,
	createLocalCodexPayload,
} from "../../src/extensions/agent-team-loop/shared/codex-local.ts";
import { computeContextBudget, estimateContext } from "../../src/extensions/agent-team-loop/shared/context-budget.ts";
import {
	CONTEXT_CHECKPOINT_TYPE,
	type ContextCheckpoint,
} from "../../src/extensions/agent-team-loop/shared/context-checkpoint.ts";
import {
	CONTEXT_COMPACTION_USAGE_TYPE,
	contextPolicyFailureMessage,
	isContextPolicyFailure,
	MwContextPolicyError,
} from "../../src/extensions/agent-team-loop/shared/context-controller.ts";
import {
	consumeContextPolicyFailure,
	registerContextPolicy,
	runContextCommand,
} from "../../src/extensions/agent-team-loop/shared/context-extension.ts";
import { resolveContextPolicy } from "../../src/extensions/agent-team-loop/shared/context-policy.ts";
import {
	acquireModelSlot,
	readConcurrencyState,
	setConcurrencyLimit,
} from "../../src/extensions/agent-team-loop/shared/model-concurrency.ts";
import { registerModelConcurrency } from "../../src/extensions/agent-team-loop/shared/model-concurrency-extension.ts";
import { allowNetwork } from "../test-network-env.ts";

let directory: string;
let project: string;
let home: string;
const servers: Server[] = [];
const model: Model<Api> = {
	id: "fake-model",
	name: "Context fixture",
	provider: "context-fixture",
	api: "openai-completions",
	baseUrl: "http://127.0.0.1:1",
	reasoning: false,
	input: ["text"],
	contextWindow: 200000,
	maxTokens: 4096,
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
};
const summary = {
	goal: "finish fixture",
	constraints: "only allowed files",
	decisions: "keep protocol",
	changes: "fixture.ts changed",
	verification: "two tools completed",
	remaining: "finish response",
};

beforeEach(() => {
	directory = fs.mkdtempSync(path.join(os.tmpdir(), "mw-context-integration-"));
	project = path.join(directory, "control");
	home = path.join(directory, "home");
	fs.mkdirSync(project, { recursive: true });
	fs.mkdirSync(home, { recursive: true });
	vi.stubEnv("MW_CONCURRENCY_DIR", path.join(directory, "slots"));
	vi.stubEnv("PI_WORKER_TASK", "");
	vi.stubEnv("MW_CODEX_LOCAL_URL", "");
	vi.stubEnv("MW_CODEX_LOCAL_TOKEN", "");
	vi.stubEnv("USERPROFILE", home);
	vi.stubEnv("HOME", home);
	writePolicy();
});
afterEach(async () => {
	await Promise.all(
		servers
			.splice(0)
			.map(
				(server) =>
					new Promise<void>((resolve, reject) => server.close((error) => (error ? reject(error) : resolve()))),
			),
	);
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	fs.rmSync(directory, { recursive: true, force: true });
});

function writePolicy(maxTokens = 80000, enabled = true): void {
	fs.mkdirSync(path.join(project, ".mw"), { recursive: true });
	fs.writeFileSync(
		path.join(project, ".mw/context.json"),
		JSON.stringify({ version: 1, defaults: { maxTokens, compaction: { enabled, keepRecentTokens: 1000 } } }),
	);
}

function assistant(
	content: AssistantMessage["content"] = [{ type: "text", text: "done" }],
	selected = model,
): AssistantMessage {
	return {
		role: "assistant",
		api: selected.api,
		provider: selected.provider,
		model: selected.id,
		content,
		timestamp: Date.now(),
		stopReason: content.some((part) => part.type === "toolCall") ? "toolUse" : "stop",
		usage: {
			input: 11,
			output: 7,
			cacheRead: 3,
			cacheWrite: 2,
			totalTokens: 23,
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
		},
	};
}

function history(bytes = 150000): Context {
	return {
		systemPrompt: "Task constraint: only allowed files",
		messages: [
			{ role: "user", content: "finish fixture", timestamp: 1 },
			assistant([{ type: "text", text: "x".repeat(bytes) }]),
			{ role: "user", content: "continue", timestamp: 2 },
		],
	};
}

async function harness(
	handler: (context: Context, options?: SimpleStreamOptions) => AssistantMessage | Promise<AssistantMessage>,
	taskFile?: string,
	persistedSession?: SessionManager,
) {
	const runtime = await ModelRuntime.create({ modelsPath: null, credentials: new InMemoryCredentialStore() });
	let key = "stable-key";
	const stream = (selected: Model<Api>, context: Context, options?: SimpleStreamOptions) => {
		const events = createAssistantMessageEventStream();
		void Promise.resolve()
			.then(() => handler(context, options))
			.then((message) => {
				const result = { ...message, api: selected.api, provider: selected.provider, model: selected.id };
				events.push({ type: "start", partial: result });
				if (result.stopReason === "error" || result.stopReason === "aborted")
					events.push({ type: "error", reason: result.stopReason, error: result });
				else events.push({ type: "done", reason: result.stopReason as "stop" | "toolUse", message: result });
				events.end(result);
			});
		return events;
	};
	const native: Provider = {
		id: model.provider,
		name: "Fixture",
		getModels: () => [model],
		auth: {
			apiKey: { name: "Fixture", resolve: async () => ({ auth: { apiKey: key, headers: { "x-auth": key } } }) },
		},
		stream,
		streamSimple: stream,
	};
	runtime.registerNativeProvider(native);
	const session = persistedSession ?? SessionManager.inMemory(project);
	const hooks = new Map<string, Array<(event: unknown, ctx: ExtensionContext) => unknown>>();
	const pi = {
		on: (name: string, handler: (event: unknown, ctx: ExtensionContext) => unknown) =>
			hooks.set(name, [...(hooks.get(name) ?? []), handler]),
		appendEntry: (type: string, data: unknown) => {
			session.appendCustomEntry(type, data);
		},
		sendMessage: vi.fn(),
		registerProvider: (id: string, config: ProviderConfig) => runtime.registerProvider(id, config),
	} as unknown as ExtensionAPI;
	const ctx = {
		modelRegistry: new ModelRegistry(runtime),
		sessionManager: session,
		model,
		cwd: project,
		hasUI: true,
		ui: { setStatus: vi.fn(), notify: vi.fn() },
	} as unknown as ExtensionCommandContext;
	registerModelConcurrency(pi);
	registerContextPolicy(pi, { controlRoot: project, homeDir: home, taskFile: taskFile ?? "" });
	const emit = async (name: string, event: unknown = {}) => {
		const results = [];
		for (const handler of hooks.get(name) ?? []) results.push(await handler(event, ctx));
		return results;
	};
	await emit("session_start");
	return {
		runtime,
		session,
		pi,
		ctx,
		emit,
		native,
		setKey: (value: string) => {
			key = value;
		},
	};
}

describe("context provider integration", () => {
	it.each([
		{ status: "error", code: "SUMMARY_FAILED", category: "quota" },
		{ status: "length", code: "SUMMARY_TRUNCATED", category: "unknown" },
		{ status: "aborted", code: "SUMMARY_ABORTED", category: "unknown" },
	] as const)("persists safe $status summary diagnostics through real runtime and session", async (failure) => {
		const session = SessionManager.create(project, path.join(directory, "diagnostic-sessions"));
		const context = history();
		for (const message of context.messages) session.appendMessage(message);
		let summaries = 0;
		let business = 0;
		const h = await harness(
			(request) => {
				if (!request.systemPrompt?.includes("Summarize historical task state")) {
					business++;
					return assistant();
				}
				summaries++;
				return {
					...assistant([{ type: "text", text: "PRIVATE-SUMMARY-BODY" }]),
					stopReason: failure.status,
					errorMessage:
						failure.status === "error"
							? "HTTP 429 insufficient_quota Bearer PRIVATE-API-KEY https://private.invalid/?secret=PRIVATE-QUERY"
							: "PRIVATE-ERROR-TEXT",
				};
			},
			undefined,
			session,
		);
		const result = await h.runtime.completeSimple(model, context);
		h.session.appendMessage(result);
		expect([summaries, business]).toEqual([1, 0]);
		expect(result.stopReason).toBe("error");
		expect(result.diagnostics).toContainEqual(
			expect.objectContaining({ type: "provider_retry_boundary", details: { outerRetryEligible: false } }),
		);
		const details = result.diagnostics?.find((entry) => entry.type === "mw_context_policy")?.details;
		expect(details).toMatchObject({
			code: failure.code,
			provider: model.provider,
			model: model.id,
			summaryStatus: failure.status,
			maxSummaryTokens: 4096,
			summaryOutputTokens: 7,
			summaryFailure: { category: failure.category },
			noProviderRequest: true,
		});
		if (failure.status === "error") expect(details?.summaryFailure).toMatchObject({ httpStatus: 429 });
		expect(result.errorMessage).toContain(`summary=${failure.category}`);
		const file = session.getSessionFile();
		if (!file) throw new Error("missing persisted diagnostic session");
		const reopened = SessionManager.open(file);
		const usage = reopened
			.getBranch()
			.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_COMPACTION_USAGE_TYPE);
		expect(usage).toHaveLength(1);
		if (usage[0].type !== "custom") throw new Error("missing usage");
		expect(usage[0].data).toMatchObject({
			attemptId: details?.attemptId,
			attemptStartedAt: details?.attemptStartedAt,
			providerRequestStarted: true,
			status: failure.status,
			usage: { input: 11, output: 7 },
		});
		expect(typeof details?.attemptId).toBe("string");
		expect(typeof details?.attemptStartedAt).toBe("string");
		expect(
			reopened
				.getBranch()
				.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_CHECKPOINT_TYPE),
		).toHaveLength(0);
		const storedAssistant = reopened
			.getBranch()
			.find(
				(entry) =>
					entry.type === "message" && entry.message.role === "assistant" && entry.message.stopReason === "error",
			);
		expect(storedAssistant).toMatchObject({ message: { diagnostics: result.diagnostics } });
		expect(fs.readFileSync(file, "utf8")).not.toMatch(/PRIVATE-|Bearer|private\.invalid/);
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it("rechecks policy after a delayed auth resolver and before actual transport", async () => {
		writePolicy(80000, false);
		let calls = 0;
		const h = await harness(() => {
			calls++;
			return assistant();
		});
		const original = h.ctx.modelRegistry.getApiKeyAndHeaders.bind(h.ctx.modelRegistry);
		let reads = 0;
		let releaseAuth = (): void => {};
		const waiting = new Promise<void>((resolve) => {
			releaseAuth = resolve;
		});
		vi.spyOn(h.ctx.modelRegistry, "getApiKeyAndHeaders").mockImplementation(async (selected) => {
			reads++;
			if (reads === 2) await waiting;
			return original(selected);
		});
		const pending = h.runtime.completeSimple(model, history(30000));
		await vi.waitFor(() => expect(reads).toBe(2));
		writePolicy(22000, false);
		releaseAuth();
		expect(isContextPolicyFailure(await pending)).toBe(true);
		expect(calls).toBe(0);
	});

	it("shows a valid but unusable saved budget with sources as JSON while still blocking all requests", async () => {
		let calls = 0;
		const h = await harness(() => {
			calls++;
			return assistant();
		});
		await runContextCommand(h.pi, h.ctx, project, "set maxTokens 1 --project", { homeDir: home });
		await runContextCommand(h.pi, h.ctx, project, "show --json", { homeDir: home });
		const notify = vi.mocked(h.ctx.ui.notify);
		const text = notify.mock.calls.at(-1)?.[0];
		if (typeof text !== "string") throw new Error("missing JSON report");
		const report = JSON.parse(text) as Record<string, unknown>;
		expect(report).toMatchObject({
			maxTokens: 1,
			modelWindow: model.contextWindow,
			budget: null,
			state: "blocked-by-budget",
			budgetError: { code: "MW_CONTEXT_BUDGET_IMPOSSIBLE" },
			sources: { maxTokens: { scope: "project", path: path.join(project, ".mw/context.json") } },
		});
		expect(isContextPolicyFailure(await h.runtime.completeSimple(model, { messages: [] }))).toBe(true);
		expect(calls).toBe(0);
	});
	it.each(["empty", "missing", "error", "no-progress", "target"])(
		"bounds the real provider %s summary failure without business or checkpoint",
		async (failure) => {
			const context = history(failure === "no-progress" ? 3000 : failure === "target" ? 20000 : 150000);
			const original = structuredClone(context);
			if (failure === "no-progress" || failure === "target") {
				const triggerRatio = failure === "no-progress" ? 0.02 : 0.1;
				fs.writeFileSync(
					path.join(project, ".mw/context.json"),
					JSON.stringify({
						version: 1,
						defaults: {
							maxTokens: 80000,
							compaction: { triggerRatio, targetRatio: triggerRatio / 2, keepRecentTokens: 100 },
						},
					}),
				);
			}
			let summaries = 0;
			let business = 0;
			const h = await harness((request) => {
				if (!request.systemPrompt?.includes("Summarize historical task state")) {
					business++;
					return assistant();
				}
				summaries++;
				if (failure === "error")
					return { ...assistant(), stopReason: "error", errorMessage: "fixture summary failure" };
				if (failure === "empty") return assistant([{ type: "text", text: "" }]);
				if (failure === "missing")
					return assistant([{ type: "text", text: JSON.stringify({ goal: "only one field" }) }]);
				return assistant([
					{
						type: "text",
						text: JSON.stringify(Object.fromEntries(Object.keys(summary).map((key) => [key, "s".repeat(1500)]))),
					},
				]);
			});
			const result = await h.runtime.completeSimple(model, context);
			expect(isContextPolicyFailure(result)).toBe(true);
			expect([summaries, business]).toEqual([1, 0]);
			expect(context).toEqual(original);
			expect(
				h.session
					.getBranch()
					.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_CHECKPOINT_TYPE),
			).toHaveLength(0);
			const code = result.diagnostics?.find((entry) => entry.type === "mw_context_policy")?.details?.code;
			expect(code).toBe(
				failure === "no-progress"
					? "SUMMARY_NO_PROGRESS"
					: failure === "target"
						? "SUMMARY_TARGET_NOT_MET"
						: failure === "error"
							? "SUMMARY_FAILED"
							: "SUMMARY_INVALID",
			);
		},
	);

	it("honors disabling automatic compaction while a managed summary waits for its slot", async () => {
		await setConcurrencyLimit(`${model.provider}/${model.id}`, 1);
		const release = await acquireModelSlot(`${model.provider}/${model.id}`);
		let calls = 0;
		const h = await harness(() => {
			calls++;
			return assistant();
		});
		const pending = h.runtime.completeSimple(model, history());
		await vi.waitFor(() =>
			expect(readConcurrencyState().requests.some((request) => request.phase === "waiting")).toBe(true),
		);
		writePolicy(80000, false);
		await release();
		expect(isContextPolicyFailure(await pending)).toBe(true);
		expect(calls).toBe(0);
		const usage = h.session
			.getBranch()
			.find((entry) => entry.type === "custom" && entry.customType === CONTEXT_COMPACTION_USAGE_TYPE);
		expect((usage as { data: unknown } | undefined)?.data).toMatchObject({ providerRequestStarted: false });
		expect(
			h.session
				.getBranch()
				.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_CHECKPOINT_TYPE),
		).toHaveLength(0);
		expect(readConcurrencyState().requests).toEqual([]);
	});
	it.each(["timeout", "abort"])("records a queued summary %s as zero actual provider requests", async (mode) => {
		await setConcurrencyLimit(`${model.provider}/${model.id}`, 1);
		const release = await acquireModelSlot(`${model.provider}/${model.id}`);
		const policyPath = path.join(project, ".mw/context.json");
		const policy = JSON.parse(fs.readFileSync(policyPath, "utf8")) as {
			defaults: { compaction: { timeoutMs: number } };
		};
		policy.defaults.compaction.timeoutMs = mode === "abort" ? 10000 : 100;
		fs.writeFileSync(policyPath, JSON.stringify(policy));
		let calls = 0;
		const persisted = SessionManager.create(project, path.join(directory, "queued-sessions"));
		const h = await harness(
			() => {
				calls++;
				return assistant();
			},
			undefined,
			persisted,
		);
		const parent = new AbortController();
		try {
			const pending = h.runtime.completeSimple(model, history(), { signal: parent.signal });
			await vi.waitFor(
				() => expect(readConcurrencyState().requests.some((request) => request.phase === "waiting")).toBe(true),
				{ interval: 5 },
			);
			if (mode === "abort") parent.abort();
			const result = await pending;
			// Flush custom usage with a no-request assistant instead of a billable fixture response.
			h.session.appendMessage(contextPolicyFailureMessage(model, new MwContextPolicyError("FIXTURE_FLUSH")));
			expect(result.stopReason).toBe(mode === "abort" ? "aborted" : "error");
			expect(calls).toBe(0);
			const usage = h.session
				.getBranch()
				.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_COMPACTION_USAGE_TYPE);
			expect(usage).toHaveLength(1);
			expect((usage[0] as { data: unknown }).data).toMatchObject({ providerRequestStarted: false, usage: null });
			const file = h.session.getSessionFile();
			if (!file) throw new Error("missing queued session file");
			const output = execFileSync(
				"python",
				["-m", "pytest", "-q", "test_context_usage.py", "-k", "typescript_queued_session_fixture"],
				{
					cwd: fileURLToPath(new URL("../../../multi-workers", import.meta.url)),
					env: { ...process.env, MW_CONTEXT_TS_FIXTURE: file },
					encoding: "utf8",
					windowsHide: true,
				},
			);
			expect(output).toContain("1 passed");
			expect(
				h.session
					.getBranch()
					.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_CHECKPOINT_TYPE),
			).toHaveLength(0);
		} finally {
			await release();
		}
		await vi.waitFor(() => expect(readConcurrencyState().requests).toEqual([]));
	});
	it("rechecks the current policy after a real limiter queue wait without nested summarization", async () => {
		writePolicy(80000, false);
		await setConcurrencyLimit(`${model.provider}/${model.id}`, 1);
		const release = await acquireModelSlot(`${model.provider}/${model.id}`);
		let calls = 0;
		const h = await harness(() => {
			calls++;
			return assistant();
		});
		const pending = h.runtime.completeSimple(model, history(30000));
		await vi.waitFor(() =>
			expect(readConcurrencyState().requests.some((request) => request.phase === "waiting")).toBe(true),
		);
		writePolicy(22000, false);
		await release();
		const result = await pending;
		expect(isContextPolicyFailure(result)).toBe(true);
		expect(result.diagnostics?.find((entry) => entry.type === "mw_context_policy")?.details?.code).toBe(
			"CURRENT_POLICY_BUDGET",
		);
		expect(calls).toBe(0);
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it("restores a persisted checkpoint only on its real SessionManager branch and invalidates it after native compaction", async () => {
		const session = SessionManager.create(project, path.join(directory, "sessions"));
		const context = history();
		const ids = context.messages.map((message) => session.appendMessage(message));
		let summaries = 0;
		const handler = (request: Context) => {
			if (request.systemPrompt?.includes("Summarize historical task state")) {
				summaries++;
				return assistant([{ type: "text", text: JSON.stringify(summary) }]);
			}
			return assistant();
		};
		const first = await harness(handler, undefined, session);
		expect((await first.runtime.completeSimple(model, context)).stopReason).toBe("stop");
		expect(summaries).toBe(1);
		const file = session.getSessionFile();
		if (!file) throw new Error("missing session file");
		const reopened = SessionManager.open(file);
		const seen: Context[] = [];
		const resumed = await harness(
			(request) => {
				seen.push(request);
				return handler(request);
			},
			undefined,
			reopened,
		);
		expect((await resumed.runtime.completeSimple(model, context)).stopReason).toBe("stop");
		expect(summaries).toBe(1);
		expect(JSON.stringify(seen.at(-1)?.messages)).toContain("Historical task state");
		reopened.branch(ids[0]);
		for (const message of context.messages.slice(1)) reopened.appendMessage(message);
		expect((await resumed.runtime.completeSimple(model, context)).stopReason).toBe("stop");
		expect(summaries).toBe(2);
		const latestUser = reopened
			.getBranch()
			.filter((entry) => entry.type === "message" && entry.message.role === "user")
			.at(-1);
		if (!latestUser) throw new Error("missing last user");
		reopened.appendCompaction("native compacted task state", latestUser.id, 55000);
		await resumed.emit("session_compact");
		const nativeContext = { ...context, messages: convertToLlm(reopened.buildSessionContext().messages) };
		expect((await resumed.runtime.completeSimple(model, nativeContext)).stopReason).toBe("stop");
		expect(summaries).toBe(2);
		expect(JSON.stringify(seen.at(-1)?.messages)).not.toContain("Historical task state");
	});

	it("keeps a cleared global type removed after a fresh controller and inherits current defaults", async () => {
		const h = await harness(() => assistant());
		for (const args of [
			"set maxTokens 190000 --global",
			"clear maxTokens --project",
			"clear type --global --type coding",
		])
			await runContextCommand(h.pi, h.ctx, project, args, { homeDir: home });
		const global = JSON.parse(fs.readFileSync(path.join(home, ".mw/context.json"), "utf8")) as {
			types: Record<string, unknown>;
		};
		expect(Object.hasOwn(global.types, "coding")).toBe(false);
		expect(Object.keys(global.types).sort()).toEqual(["research", "review"]);
		const task = path.join(project, ".agenticdoc/key/workers/coding/task.md");
		fs.mkdirSync(path.dirname(task), { recursive: true });
		fs.writeFileSync(task, "type: coding\n\nTask");
		const restarted = await harness(() => assistant(), task);
		expect((await restarted.runtime.completeSimple(model, { messages: [] })).stopReason).toBe("stop");
		expect(restarted.ctx.ui.setStatus).toHaveBeenCalledWith("mw-context", "Context coding: 190000 tokens; auto on");
		expect(
			resolveContextPolicy({ controlRoot: project, homeDir: home, taskFile: task }).sources.maxTokens,
		).toMatchObject({ scope: "global", level: "defaults", builtin: false });
	});

	it("retains native policy failures across flattened core errors, consumes once, and clears the next run", async () => {
		const h = await harness(() => assistant());
		const signal = new AbortController().signal;
		await h.emit("session_before_compact", { reason: "manual", signal });
		const failed = await completeSummarization(
			model,
			history(250000),
			{ signal },
			h.runtime.streamSimple.bind(h.runtime),
		);
		expect(isContextPolicyFailure(failed)).toBe(true);
		expect(consumeContextPolicyFailure(h.ctx.modelRegistry)?.code).toBe("NATIVE_SUMMARY_BUDGET");
		expect(consumeContextPolicyFailure(h.ctx.modelRegistry)).toBeUndefined();
		await completeSummarization(model, history(250000), { signal }, h.runtime.streamSimple.bind(h.runtime));
		await h.emit("before_agent_start");
		expect(consumeContextPolicyFailure(h.ctx.modelRegistry)).toBeUndefined();
	});
	it("continues the same real Agent after a complete parallel tool batch, using separate limit=1 leases", async () => {
		await setConcurrencyLimit(`${model.provider}/${model.id}`, 1);
		let business = 0;
		let summaries = 0;
		let toolExecutions = 0;
		let completed = 0;
		const requests: Context[] = [];
		const h = await harness((context, options) => {
			expect(readConcurrencyState().requests.filter((request) => request.phase === "active")).toHaveLength(1);
			expect(options?.apiKey).toBe("stable-key");
			expect(options?.headers?.["x-auth"]).toBe("stable-key");
			if (context.systemPrompt?.includes("Summarize historical task state")) {
				summaries++;
				expect(completed).toBe(2);
				expect(context.tools).toEqual([]);
				expect(options?.maxTokens).toBe(4096);
				return assistant([{ type: "text", text: JSON.stringify(summary) }]);
			}
			requests.push(context);
			business++;
			return business === 1
				? assistant([1, 2].map((id) => ({ type: "toolCall", id: `call-${id}`, name: "lookup", arguments: { id } })))
				: business === 2
					? assistant([{ type: "toolCall", id: "call-3", name: "lookup", arguments: { id: 3 } }])
					: assistant();
		});
		const events: string[] = [];
		const agent = new Agent({
			streamFn: h.runtime.streamSimple.bind(h.runtime),
			toolExecution: "parallel",
			initialState: {
				model,
				systemPrompt: "Task constraint: only allowed files",
				tools: [
					{
						name: "lookup",
						label: "lookup",
						description: "fixture side effect",
						parameters: Type.Object({ id: Type.Number() }),
						execute: async (_id, args) => {
							const { id } = args as { id: number };
							toolExecutions++;
							await delay(id === 1 ? 20 : 1);
							completed++;
							return {
								content: [{ type: "text", text: id < 3 ? "x".repeat(75000) : "last result" }],
								details: undefined,
							};
						},
					},
				],
			},
		});
		agent.subscribe((event) => {
			events.push(event.type);
			if (event.type === "message_end") h.session.appendMessage(event.message as Message);
		});
		await agent.prompt("finish fixture; only allowed files");
		expect(agent.state.errorMessage).toBeUndefined();
		expect([business, summaries, toolExecutions, completed]).toEqual([3, 1, 3, 3]);
		expect(events.filter((event) => event === "agent_start")).toHaveLength(1);
		expect(events.filter((event) => event === "agent_end")).toHaveLength(1);
		expect(
			requests[1].messages.some(
				(message) => typeof message.content === "string" && message.content.includes("Historical task state"),
			),
		).toBe(true);
		expect(requests[2].messages.filter((message) => message.role === "toolResult")).toHaveLength(1);
		expect(agent.state.messages.filter((message) => message.role === "toolResult")).toHaveLength(3);
		const checkpoints = h.session
			.getBranch()
			.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_CHECKPOINT_TYPE);
		expect(checkpoints).toHaveLength(1);
		const checkpoint = (checkpoints[0] as { data: ContextCheckpoint }).data;
		expect(checkpoint.afterTokens).toBeLessThan(checkpoint.beforeTokens);
		expect(checkpoint.afterTokens).toBeLessThanOrEqual(
			computeContextBudget(model, resolveContextPolicy({ controlRoot: project, homeDir: home })).targetTokens,
		);
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it("admits exactly the first-request input budget and refuses the next token without a transport", async () => {
		writePolicy(80000, false);
		let calls = 0;
		const h = await harness(() => {
			calls++;
			return assistant();
		});
		const budget = computeContextBudget(model, resolveContextPolicy({ controlRoot: project, homeDir: home }));
		const context: Context = { messages: [{ role: "user", content: "", timestamp: 0 }] };
		const base = estimateContext(context).estimatedTokens;
		const content = "x".repeat((budget.inputBudget - base) * 3);
		context.messages = [{ role: "user", content, timestamp: 0 }];
		expect(estimateContext(context).estimatedTokens).toBe(budget.inputBudget);
		expect((await h.runtime.completeSimple(model, context)).stopReason).toBe("stop");
		const refused = await h.runtime.completeSimple(model, {
			messages: [{ role: "user", content: `${content}xxx`, timestamp: 0 }],
		});
		expect(isContextPolicyFailure(refused)).toBe(true);
		expect(calls).toBe(1);
	});

	it("rechecks a smaller model and a policy tightened during the summary before sending business", async () => {
		let calls = 0;
		const h = await harness(() => {
			calls++;
			writePolicy(21000, false);
			return assistant([{ type: "text", text: JSON.stringify(summary) }]);
		});
		expect(isContextPolicyFailure(await h.runtime.completeSimple(model, history()))).toBe(true);
		expect(calls).toBe(1);
		writePolicy(80000, false);
		expect(
			isContextPolicyFailure(await h.runtime.completeSimple({ ...model, contextWindow: 30000 }, history(60000))),
		).toBe(true);
		expect(calls).toBe(1);
	});

	it("keeps one wrapper across refresh/reinstall/re-registration and preserves explicit request auth", async () => {
		const keys: string[] = [];
		const headers: Array<string | null | undefined> = [];
		const h = await harness((_context, options) => {
			keys.push(options?.apiKey ?? "missing");
			headers.push(options?.headers?.["x-auth"]);
			return assistant();
		});
		const registered = h.ctx.modelRegistry.getRegisteredNativeProvider(model.provider);
		await h.ctx.modelRegistry.refresh({ allowNetwork: false });
		await h.emit("context");
		await h.emit("model_select");
		expect(h.ctx.modelRegistry.getRegisteredNativeProvider(model.provider)).toBe(registered);
		await h.runtime.complete(model, { messages: [] });
		await h.runtime.completeSimple(
			model,
			{ messages: [] },
			{ apiKey: "explicit-override", headers: { "x-auth": "explicit-header" } },
		);
		h.runtime.registerNativeProvider(h.native);
		await h.emit("context");
		await h.runtime.completeSimple(model, { messages: [] });
		expect(keys).toEqual(["stable-key", "explicit-override", "stable-key"]);
		expect(headers).toEqual(["stable-key", "explicit-header", "stable-key"]);
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it.each(["timeout", "parent-abort", "noncooperative"])(
		"keeps %s bounded and owns its actual summary lease until transport terminal",
		async (mode) => {
			await setConcurrencyLimit(`${model.provider}/${model.id}`, 1);
			const policyPath = path.join(project, ".mw/context.json");
			const policy = JSON.parse(fs.readFileSync(policyPath, "utf8")) as {
				defaults: { compaction: { timeoutMs: number } };
			};
			policy.defaults.compaction.timeoutMs = mode === "parent-abort" ? 10000 : 30;
			fs.writeFileSync(policyPath, JSON.stringify(policy));
			const h = await harness(() => assistant());
			let calls = 0;
			let finish: (() => void) | undefined;
			const parent = new AbortController();
			const stream = (_selected: Model<Api>, _context: Context, options?: SimpleStreamOptions) => {
				calls++;
				const events = createAssistantMessageEventStream();
				finish = () => {
					const result = assistant([{ type: "text", text: JSON.stringify(summary) }]);
					events.push({ type: "done", reason: "stop", message: result });
					events.end(result);
				};
				if (mode !== "noncooperative")
					options?.signal?.addEventListener(
						"abort",
						() => {
							const result = { ...assistant(), stopReason: "aborted" as const, errorMessage: "fixture aborted" };
							events.push({ type: "error", reason: "aborted", error: result });
							events.end(result);
						},
						{ once: true },
					);
				return events;
			};
			h.runtime.registerNativeProvider({ ...h.native, stream, streamSimple: stream });
			await h.emit("context");
			const pending = h.runtime.completeSimple(model, history(), { signal: parent.signal });
			await vi.waitFor(() => expect(calls).toBe(1));
			if (mode === "parent-abort") parent.abort();
			const result = await pending;
			expect(result.stopReason).toBe(mode === "parent-abort" ? "aborted" : "error");
			if (mode !== "parent-abort") expect(isContextPolicyFailure(result)).toBe(true);
			expect(calls).toBe(1);
			if (mode === "noncooperative") {
				expect(readConcurrencyState().requests).toHaveLength(1);
				finish?.();
			}
			await vi.waitFor(() => expect(readConcurrencyState().requests).toEqual([]));
			expect(
				h.session
					.getBranch()
					.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_CHECKPOINT_TYPE),
			).toHaveLength(0);
		},
	);

	it("fails safely when credentials rotate during the managed summary, before the business transport", async () => {
		let calls = 0;
		const h = await harness(() => {
			calls++;
			h.setKey("rotated-key");
			return assistant([{ type: "text", text: JSON.stringify(summary) }]);
		});
		const result = await h.runtime.completeSimple(model, history());
		expect(calls).toBe(1);
		expect(isContextPolicyFailure(result)).toBe(true);
		expect(result.diagnostics).toEqual(
			expect.arrayContaining([
				expect.objectContaining({
					type: "mw_context_policy",
					details: expect.objectContaining({ code: "AUTH_CHANGED", noProviderRequest: true }),
				}),
			]),
		);
		expect(
			h.session
				.getBranch()
				.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_COMPACTION_USAGE_TYPE),
		).toHaveLength(1);
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it.each(["dual-game", "partition-engine"])(
		"uses the control workspace and exact worker type in %s despite conflicting target policy",
		async (workspace) => {
			const task = path.join(project, ".agenticdoc/key/workers/custom/task.md");
			fs.mkdirSync(path.dirname(task), { recursive: true });
			fs.writeFileSync(task, "type: verifier\n\nTask");
			const target = path.join(directory, workspace);
			fs.mkdirSync(path.join(target, ".mw"), { recursive: true });
			fs.writeFileSync(path.join(target, ".mw/context.json"), "invalid-json");
			let calls = 0;
			const h = await harness(() => {
				calls++;
				return assistant();
			}, task);
			h.ctx.cwd = target;
			await h.emit("context");
			await h.runtime.completeSimple(model, { messages: [] });
			expect(calls).toBe(1);
			expect(h.ctx.ui.setStatus).toHaveBeenCalledWith("mw-context", "Context verifier: 80000 tokens; auto on");
		},
	);

	it("rejects invalid and tightened policies with zero additional actual calls and a nonretry diagnostic", async () => {
		let calls = 0;
		const h = await harness(() => {
			calls++;
			return assistant();
		});
		await h.runtime.completeSimple(model, { messages: [] });
		writePolicy(22000, false);
		const result = await h.runtime.completeSimple(model, history(30000));
		expect(calls).toBe(1);
		expect(isContextPolicyFailure(result)).toBe(true);
		expect(result.diagnostics).toEqual(
			expect.arrayContaining([
				expect.objectContaining({ type: "provider_retry_boundary", details: { outerRetryEligible: false } }),
			]),
		);
		fs.writeFileSync(path.join(project, ".mw/context.json"), "{");
		expect(isContextPolicyFailure(await h.runtime.completeSimple(model, { messages: [] }))).toBe(true);
		expect(calls).toBe(1);
	});

	it("when automatic compaction is disabled, admits the trigger-to-budget interval and refuses beyond budget", async () => {
		writePolicy(80000, false);
		let calls = 0;
		const h = await harness(() => {
			calls++;
			return assistant();
		});
		expect((await h.runtime.completeSimple(model, history())).stopReason).toBe("stop");
		expect(isContextPolicyFailure(await h.runtime.completeSimple(model, history(200000)))).toBe(true);
		expect(calls).toBe(1);
		expect(h.session.getBranch().filter((entry) => entry.type === "custom")).toHaveLength(0);
	});

	it.each(["manual", "overflow", "tree"])(
		"identifies native %s summary by the actual signal through completeSummarization",
		async (reason) => {
			let calls = 0;
			const h = await harness((_context, options) => {
				calls++;
				if (calls === 1) expect(options?.cacheRetention).toBe("none");
				return assistant();
			});
			const abort = new AbortController();
			const responses =
				reason === "tree"
					? await h.emit("session_before_tree", { preparation: { userWantsSummary: true }, signal: abort.signal })
					: await h.emit("session_before_compact", { reason, signal: abort.signal });
			expect(responses.some((result) => (result as { cancel?: boolean } | undefined)?.cancel)).toBe(false);
			const result = await completeSummarization(
				model,
				history(),
				{ signal: abort.signal },
				h.runtime.streamSimple.bind(h.runtime),
			);
			expect(result.stopReason).toBe("stop");
			expect(calls).toBe(1);
			expect(h.session.getBranch().filter((entry) => entry.type === "custom")).toHaveLength(0);
			// The next request has a different signal and must go through managed compaction.
			const next = await h.runtime.completeSimple(model, history(), { signal: new AbortController().signal });
			expect(isContextPolicyFailure(next)).toBe(true); // Fake native response is intentionally not valid managed JSON.
			expect(calls).toBe(2);
		},
	);

	it("hands native threshold ownership to the controller and disables native overflow summaries with auto off", async () => {
		const h = await harness(() => assistant());
		const signal = new AbortController().signal;
		expect(await h.emit("session_before_compact", { reason: "threshold", signal })).toContainEqual({ cancel: true });
		writePolicy(80000, false);
		expect(await h.emit("session_before_compact", { reason: "overflow", signal })).toContainEqual({ cancel: true });
		expect(await h.emit("session_before_compact", { reason: "manual", signal })).not.toContainEqual({ cancel: true });
	});

	it("actual /mw context set/show/clear writes only selected overrides, applies next request, and refuses worker mutation", async () => {
		const h = await harness(() => assistant());
		let command: ((args: string, ctx: ExtensionCommandContext) => Promise<void>) | undefined;
		const pi = {
			...h.pi,
			registerCommand: (_name: string, value: { handler: typeof command }) => {
				command = value.handler;
			},
		} as unknown as ExtensionAPI;
		registerMwCommands(pi, project, {} as never, {} as never, {} as never, path.join(project, ".agenticdoc"));
		if (!command) throw new Error("missing mw command");
		await command("context set maxTokens 90000 --project --type verifier", h.ctx);
		expect(resolveContextPolicy({ controlRoot: project, homeDir: home, taskType: "verifier" }).maxTokens).toBe(90000);
		await command("context show --type verifier --json", h.ctx);
		expect(h.ctx.ui.notify).toHaveBeenCalledWith(expect.stringContaining('"effectiveWindow": 90000'), "info");
		await command("context clear type --project --type verifier", h.ctx);
		expect(resolveContextPolicy({ controlRoot: project, homeDir: home, taskType: "verifier" }).maxTokens).toBe(80000);
		await command("context set compaction.enabled false --global --type coding", h.ctx);
		// The project defaults override global type fields until explicitly cleared.
		expect(resolveContextPolicy({ controlRoot: project, homeDir: home, taskType: "coding" }).compaction.enabled).toBe(
			true,
		);
		await command("context clear compaction.enabled --project", h.ctx);
		expect(resolveContextPolicy({ controlRoot: project, homeDir: home, taskType: "coding" }).compaction.enabled).toBe(
			false,
		);
		const before = fs.readFileSync(path.join(project, ".mw/context.json"), "utf8");
		await runContextCommand(h.pi, h.ctx, project, "set maxTokens 1 --project", {
			taskFile: "worker-task",
			homeDir: home,
		});
		expect(fs.readFileSync(path.join(project, ".mw/context.json"), "utf8")).toBe(before);
		await command("context set maxTokens 22000 --project", h.ctx);
		expect(isContextPolicyFailure(await h.runtime.completeSimple(model, history(30000)))).toBe(true);
	});

	it("real local HTTP relay receives the same wrapper used for estimates and no transport after policy rejection", async () => {
		allowNetwork();
		const bodies: unknown[] = [];
		const authorization: Array<string | undefined> = [];
		const server = createServer(async (request, response) => {
			if (request.url === "/status") {
				response.setHeader("Content-Type", "application/json");
				response.end(JSON.stringify({ status: "ready", backend: "codex-cli", protocol: 2, active: [] }));
				return;
			}
			let text = "";
			for await (const chunk of request) text += String(chunk);
			const payload = JSON.parse(text) as { context: Context };
			bodies.push(payload);
			authorization.push(request.headers.authorization);
			const summaryRequest = payload.context.systemPrompt?.includes("Summarize historical task state");
			response.end(
				`${JSON.stringify({ type: "result", text: summaryRequest ? JSON.stringify(summary) : "local done", toolCalls: [], usage: { input_tokens: 10, output_tokens: 2 } })}\n`,
			);
		});
		servers.push(server);
		await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
		const address = server.address();
		if (!address || typeof address === "string") throw new Error("missing server address");
		const token = "fixture-local-token-at-least-24-characters";
		fs.writeFileSync(
			path.join(project, ".mw/codex-local.json"),
			JSON.stringify({ version: 1, url: `http://127.0.0.1:${address.port}`, token }),
		);
		const h = await harness(() => assistant());
		configureLocalCodex(h.pi, project);
		await h.emit("context");
		const selected = h.runtime.getModel("openai-codex-local", "gpt-5.6-sol");
		if (!selected) throw new Error("missing local model");
		const context = { messages: [{ role: "user" as const, content: "local fixture", timestamp: 1 }] };
		const admitted = await h.runtime.completeSimple(selected, context, { reasoning: "low", maxTokens: 4096 });
		expect(admitted.errorMessage).toBeUndefined();
		expect(admitted.stopReason).toBe("stop");
		expect(bodies).toEqual([createLocalCodexPayload(selected, context, { reasoning: "low" }, project)]);
		expect(authorization).toEqual([`Bearer ${token}`]);
		const wrapped = JSON.stringify(bodies[0]);
		expect(estimateContext(context, { serializedPayload: wrapped, additionalTokens: 16384 }).baseTokens).toBe(
			Math.ceil(Buffer.byteLength(wrapped) / 3) + 1024 + 16384,
		);
		writePolicy(120000);
		await setConcurrencyLimit("codex/gpt-5.6-sol", 1);
		const compacted = await h.runtime.completeSimple(selected, history(210000), { maxTokens: 4096 });
		expect(compacted.errorMessage).toBeUndefined();
		expect(bodies).toHaveLength(3);
		expect(
			h.session
				.getBranch()
				.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_COMPACTION_USAGE_TYPE),
		).toHaveLength(1);
		writePolicy(30000, false);
		const refused = await h.runtime.completeSimple(selected, context, { maxTokens: 4096 });
		expect(isContextPolicyFailure(refused)).toBe(true);
		expect(bodies).toHaveLength(3);
		expect(readConcurrencyState().requests).toEqual([]);
	});
});
