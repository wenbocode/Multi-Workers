import * as fs from "node:fs";
import { createServer, type Server } from "node:http";
import * as os from "node:os";
import * as path from "node:path";
import { setTimeout as delay } from "node:timers/promises";
import { Agent, type AgentTool } from "@earendil-works/pi-agent-core";
import {
	type Api,
	type AssistantMessage,
	type Context,
	createAssistantMessageEventStream,
	InMemoryCredentialStore,
	type Model,
	type Provider,
	type SimpleStreamOptions,
} from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { AgentSession } from "../../src/core/agent-session.ts";
import { completeSummarization } from "../../src/core/compaction/compaction.ts";
import { SUMMARIZATION_SYSTEM_PROMPT } from "../../src/core/compaction/utils.ts";
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
import { SettingsManager } from "../../src/core/settings-manager.ts";
import { registerMwCommands } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import {
	configureLocalCodex,
	createLocalCodexPayload,
} from "../../src/extensions/agent-team-loop/shared/codex-local.ts";
import { computeContextBudget, estimateContext } from "../../src/extensions/agent-team-loop/shared/context-budget.ts";
import { CONTEXT_CHECKPOINT_TYPE } from "../../src/extensions/agent-team-loop/shared/context-checkpoint.ts";
import {
	CONTEXT_COMPACTION_USAGE_TYPE,
	isContextPolicyFailure,
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
import { createTestExtensionsResult, createTestResourceLoader } from "../utilities.ts";

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
const nativeSessions: AgentSession[] = [];

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
	while (nativeSessions.length) nativeSessions.pop()?.dispose();
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
		JSON.stringify({ version: 1, defaults: { maxTokens, compaction: { enabled } } }),
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

async function nativeHarness(
	handler: (context: Context, options?: SimpleStreamOptions) => AssistantMessage | Promise<AssistantMessage>,
	manager = SessionManager.create(project, path.join(directory, "native-sessions")),
	tools: AgentTool[] = [],
) {
	const h = await harness(handler, undefined, manager);
	// Install real-session hooks on the original transport, without the lightweight harness wrapper.
	h.runtime.registerNativeProvider(h.native);
	const registry = h.ctx.modelRegistry;
	const agent = new Agent({
		getApiKey: async () => {
			const auth = await registry.getApiKeyAndHeaders(model);
			if (!auth.ok) throw new Error(auth.error);
			return auth.apiKey;
		},
		streamFn: h.runtime.streamSimple.bind(h.runtime),
		convertToLlm,
		initialState: {
			model,
			systemPrompt: "Task constraint: only allowed files",
			tools,
			messages: manager.buildSessionContext().messages,
		},
	});
	const result = await createTestExtensionsResult(
		[
			async (pi) => {
				registerModelConcurrency(pi);
				registerContextPolicy(pi, { controlRoot: project, homeDir: home });
			},
		],
		project,
	);
	const resourceLoader = createTestResourceLoader({ extensionsResult: result });
	const settings = SettingsManager.inMemory({
		retry: { enabled: false },
		compaction: { enabled: false, keepRecentTokens: 1, reserveTokens: 16384 },
	});
	const session = new AgentSession({
		agent,
		sessionManager: manager,
		settingsManager: settings,
		cwd: project,
		modelRuntime: h.runtime,
		resourceLoader,
		baseToolsOverride: Object.fromEntries(tools.map((tool) => [tool.name, tool])),
		initialActiveToolNames: tools.map((tool) => tool.name),
	});
	nativeSessions.push(session);
	return { ...h, agentSession: session, settings };
}

describe("context provider integration", () => {
	it.each([
		{ status: "error", code: "SUMMARY_FAILED", category: "quota" },
		{ status: "length", code: "SUMMARY_TRUNCATED", category: "unknown" },
		{ status: "aborted", code: "SUMMARY_ABORTED", category: "unknown" },
	] as const)("persists safe native $status failure without managed usage or checkpoint", async (failure) => {
		const manager = SessionManager.create(project, path.join(directory, "failed-native"));
		for (const message of history().messages) manager.appendMessage(message);
		let summaries = 0;
		let business = 0;
		const h = await nativeHarness((request) => {
			if (!request.systemPrompt?.startsWith(SUMMARIZATION_SYSTEM_PROMPT)) {
				business++;
				return assistant();
			}
			summaries++;
			return {
				...assistant([{ type: "text", text: "PRIVATE-BODY" }]),
				stopReason: failure.status,
				errorMessage:
					failure.status === "error"
						? "HTTP 429 insufficient_quota PRIVATE-KEY https://secret.invalid"
						: "PRIVATE-ERROR",
			};
		}, manager);
		await expect(h.agentSession.prompt("continue")).rejects.toThrow(`MW_CONTEXT_POLICY:${failure.code}`);
		const attempts = failure.status === "length" ? 2 : 1;
		expect([summaries, business]).toEqual([attempts, 0]);
		const details = consumeContextPolicyFailure(h.agentSession.extensionRunner.getModelRegistry());
		expect(details).toMatchObject({
			code: failure.code,
			summaryStatus: failure.status,
			provider: model.provider,
			model: model.id,
			summaryFailure: { category: failure.category },
			nativeSummaryUsage: { input: 11 * attempts, output: 7 * attempts },
		});
		expect(typeof details?.attemptId).toBe("string");
		expect(typeof details?.attemptStartedAt).toBe("string");
		const file = manager.getSessionFile();
		if (!file) throw new Error("missing native failure session");
		const reopened = SessionManager.open(file);
		expect(reopened.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(0);
		expect(
			reopened
				.getEntries()
				.filter((entry) => entry.type === "custom" && entry.customType === "mw-context-policy-failure"),
		).toEqual([expect.objectContaining({ data: details })]);
		expect(fs.readFileSync(file, "utf8")).not.toMatch(/PRIVATE-|secret\.invalid/);
		expect(
			reopened
				.getEntries()
				.filter(
					(entry) =>
						entry.type === "custom" &&
						[CONTEXT_CHECKPOINT_TYPE, CONTEXT_COMPACTION_USAGE_TYPE].includes(entry.customType),
				),
		).toHaveLength(0);
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it("native compaction persists real state and reopens without repeating the summary", async () => {
		const manager = SessionManager.create(project, path.join(directory, "resume-native"));
		for (const message of history().messages) manager.appendMessage(message);
		let summaries = 0;
		const requests: Context[] = [];
		const respond = (request: Context) => {
			if (request.systemPrompt === SUMMARIZATION_SYSTEM_PROMPT) {
				summaries++;
				return assistant([{ type: "text", text: "Native persisted task summary" }]);
			}
			requests.push(request);
			return assistant();
		};
		const first = await nativeHarness(respond, manager);
		await first.agentSession.prompt("continue");
		expect(summaries).toBe(1);
		const file = manager.getSessionFile();
		if (!file) throw new Error("native session was not persisted");
		const reopened = SessionManager.open(file);
		const compactions = reopened.getEntries().filter((entry) => entry.type === "compaction");
		expect(compactions).toHaveLength(1);
		expect(compactions[0]).toMatchObject({
			summary: "Native persisted task summary",
			usage: { input: 11, output: 7 },
		});
		expect(reopened.buildSessionContext().messages.some((message) => message.role === "compactionSummary")).toBe(
			true,
		);
		expect(reopened.getEntries().filter((entry) => entry.type === "message")).toHaveLength(5);
		const resumed = await nativeHarness(respond, reopened);
		await resumed.agentSession.prompt("finish after resume");
		expect(summaries).toBe(1);
		expect(JSON.stringify(requests.at(-1)?.messages)).toContain("Native persisted task summary");
		expect(JSON.stringify(requests.at(-1)?.messages)).not.toContain("x".repeat(1000));
		expect(
			reopened
				.getEntries()
				.filter(
					(entry) =>
						entry.type === "custom" &&
						[CONTEXT_CHECKPOINT_TYPE, CONTEXT_COMPACTION_USAGE_TYPE].includes(entry.customType),
				),
		).toHaveLength(0);
	});

	it("real AgentSession recovers a truncated summary after a parallel tool batch using separate limit=1 leases", async () => {
		await setConcurrencyLimit(`${model.provider}/${model.id}`, 1);
		let business = 0;
		let summaries = 0;
		let completed = 0;
		const executions: number[] = [];
		const requests: Context[] = [];
		const manager = SessionManager.create(project, path.join(directory, "tool-native"));
		manager.appendMessage({ role: "user", content: "existing task", timestamp: 1 });
		manager.appendMessage(assistant([{ type: "text", text: "old work ".repeat(500) }]));
		const h = await nativeHarness(
			(request, options) => {
				expect(readConcurrencyState().requests.filter((entry) => entry.phase === "active")).toHaveLength(1);
				expect(options?.apiKey).toBe("stable-key");
				if (request.systemPrompt?.startsWith(SUMMARIZATION_SYSTEM_PROMPT)) {
					summaries++;
					expect(completed).toBe(2);
					return {
						...assistant([{ type: "text", text: "Native task and completed tool results" }]),
						stopReason: summaries === 1 ? "length" : "stop",
					};
				}
				requests.push(request);
				business++;
				return business === 1
					? assistant(
							[1, 2].map((id) => ({ type: "toolCall", id: `lookup-${id}`, name: "lookup", arguments: { id } })),
						)
					: assistant();
			},
			manager,
			[
				{
					name: "lookup",
					label: "lookup",
					description: "fixture side effect",
					parameters: Type.Object({ id: Type.Number() }),
					execute: async (_id, args) => {
						const id = (args as { id: number }).id;
						executions.push(id);
						await delay(id === 1 ? 20 : 1);
						completed++;
						return { content: [{ type: "text", text: "x".repeat(75000) }], details: undefined };
					},
				},
			],
		);
		await h.agentSession.prompt("finish fixture; only allowed files");
		expect([business, completed]).toEqual([2, 2]);
		// Native compaction may summarize an older prefix and the retained split turn separately.
		expect(summaries).toBeGreaterThanOrEqual(2);
		expect(executions.sort()).toEqual([1, 2]);
		const ids = requests[1].messages.flatMap((message) =>
			message.role === "assistant"
				? message.content.filter((part) => part.type === "toolCall").map((part) => part.id)
				: [],
		);
		for (const message of requests[1].messages)
			if (message.role === "toolResult") expect(ids).toContain(message.toolCallId);
		expect(manager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(1);
		expect(
			manager
				.getEntries()
				.filter(
					(entry) =>
						entry.type === "custom" &&
						[CONTEXT_CHECKPOINT_TYPE, CONTEXT_COMPACTION_USAGE_TYPE].includes(entry.customType),
				),
		).toHaveLength(0);
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it("native no-progress stops before business and preserves the original committed history", async () => {
		const manager = SessionManager.create(project, path.join(directory, "no-progress-native"));
		for (const message of history().messages) manager.appendMessage(message);
		let business = 0;
		const h = await nativeHarness((request) => {
			if (request.systemPrompt === SUMMARIZATION_SYSTEM_PROMPT)
				return assistant([{ type: "text", text: "y".repeat(170000) }]);
			business++;
			return assistant();
		}, manager);
		await expect(h.agentSession.prompt("continue")).rejects.toThrow("SUMMARY_NO_PROGRESS");
		expect(business).toBe(0);
		expect(manager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(1);
		expect(manager.getEntries().filter((entry) => entry.type === "message")).toHaveLength(3);
	});

	it("native compaction rechecks tightened policy and a smaller model before business", async () => {
		const manager = SessionManager.create(project, path.join(directory, "tightened-native"));
		for (const message of history().messages) manager.appendMessage(message);
		let calls = 0;
		const h = await nativeHarness(() => {
			calls++;
			writePolicy(21000, false);
			return assistant([{ type: "text", text: "native state" }]);
		}, manager);
		await expect(h.agentSession.prompt("continue")).rejects.toThrow("CURRENT_POLICY_BUDGET");
		expect(calls).toBe(1);
		writePolicy(80000, false);
		expect(
			isContextPolicyFailure(await h.runtime.completeSimple({ ...model, contextWindow: 30000 }, history(60000))),
		).toBe(true);
		expect(calls).toBe(1);
	});

	it.each([false, true])("queued request rereads credentials, explicit override=%s", async (explicit) => {
		await setConcurrencyLimit(`${model.provider}/${model.id}`, 1);
		const release = await acquireModelSlot(`${model.provider}/${model.id}`);
		const keys: Array<string | undefined> = [];
		const h = await harness((_request, options) => {
			keys.push(options?.apiKey);
			return assistant();
		});
		const pending = h.runtime.completeSimple(
			model,
			{ messages: [] },
			explicit ? { apiKey: "explicit-override", headers: { "x-auth": "explicit-header" } } : undefined,
		);
		await vi.waitFor(() =>
			expect(readConcurrencyState().requests.some((request) => request.phase === "waiting")).toBe(true),
		);
		h.setKey("rotated-key");
		await release();
		const result = await pending;
		if (!explicit) {
			expect(isContextPolicyFailure(result)).toBe(true);
			expect(keys).toEqual([]);
		} else {
			expect(result.stopReason).toBe("stop");
			expect(keys).toEqual(["explicit-override"]);
		}
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it("disabling automatic compaction while a native summary is queued prevents its physical request", async () => {
		await setConcurrencyLimit(`${model.provider}/${model.id}`, 1);
		const release = await acquireModelSlot(`${model.provider}/${model.id}`);
		const manager = SessionManager.create(project, path.join(directory, "disabled-queued-native"));
		for (const message of history().messages) manager.appendMessage(message);
		let calls = 0;
		const h = await nativeHarness(() => {
			calls++;
			return assistant();
		}, manager);
		const pending = h.agentSession.prompt("continue");
		const rejected = expect(pending).rejects.toThrow("AUTOCOMPACTION_DISABLED");
		try {
			await vi.waitFor(() =>
				expect(readConcurrencyState().requests.some((request) => request.phase === "waiting")).toBe(true),
			);
			writePolicy(80000, false);
		} finally {
			await release();
		}
		await rejected;
		expect(calls).toBe(0);
		expect(manager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(0);
		expect(
			manager
				.getEntries()
				.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_COMPACTION_USAGE_TYPE),
		).toHaveLength(0);
		expect(readConcurrencyState().requests).toEqual([]);
	});

	it("queued native summary cancellation makes zero physical calls and no fabricated usage", async () => {
		await setConcurrencyLimit(`${model.provider}/${model.id}`, 1);
		const release = await acquireModelSlot(`${model.provider}/${model.id}`);
		const manager = SessionManager.create(project, path.join(directory, "queued-native"));
		for (const message of history().messages) manager.appendMessage(message);
		let calls = 0;
		const h = await nativeHarness(() => {
			calls++;
			return assistant();
		}, manager);
		const pending = h.agentSession.prompt("continue");
		const observed = pending.catch(() => {});
		try {
			await vi.waitFor(() =>
				expect(readConcurrencyState().requests.some((request) => request.phase === "waiting")).toBe(true),
			);
			await h.agentSession.abort();
			await observed;
			expect(calls).toBe(0);
			expect(manager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(0);
			expect(
				manager
					.getEntries()
					.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_COMPACTION_USAGE_TYPE),
			).toHaveLength(0);
		} finally {
			await release();
		}
		await vi.waitFor(() => expect(readConcurrencyState().requests).toEqual([]));
	});

	it("native summary transport retains its concurrency lease until a cancelled transport terminates", async () => {
		await setConcurrencyLimit(`${model.provider}/${model.id}`, 1);
		const manager = SessionManager.create(project, path.join(directory, "late-native"));
		for (const message of history().messages) manager.appendMessage(message);
		let finish: (() => void) | undefined;
		const h = await nativeHarness(
			async () =>
				await new Promise<AssistantMessage>((resolve) => {
					finish = () => resolve(assistant([{ type: "text", text: "late native state" }]));
				}),
			manager,
		);
		const pending = h.agentSession.prompt("continue");
		const observed = pending.catch(() => {});
		await vi.waitFor(() => expect(finish).toBeDefined());
		const aborting = h.agentSession.abort();
		expect(readConcurrencyState().requests.filter((entry) => entry.phase === "active")).toHaveLength(1);
		finish?.();
		await aborting;
		await observed;
		expect(manager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(0);
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
		expect(restarted.ctx.ui.setStatus).toHaveBeenCalledWith(
			"mw-context",
			"Context coding: 190000 tokens; native auto on",
		);
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
		await h.emit("before_agent_start", { prompt: "next" });
		expect(consumeContextPolicyFailure(h.ctx.modelRegistry)).toBeUndefined();
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
			expect(h.ctx.ui.setStatus).toHaveBeenCalledWith(
				"mw-context",
				"Context verifier: 80000 tokens; native auto on",
			);
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
			expect(h.session.getBranch().filter((entry) => entry.type === "custom")).toEqual([
				expect.objectContaining({ customType: "mw-native-summary-result" }),
			]);
			// The provider layer now admits the next business call without generating any summary.
			const next = await h.runtime.completeSimple(model, history(), { signal: new AbortController().signal });
			expect(next.stopReason).toBe("stop");
			expect(calls).toBe(2);
		},
	);

	it("keeps MW threshold ownership, native manual handling and disables overflow summaries with auto off", async () => {
		const h = await harness(() => assistant());
		const signal = new AbortController().signal;
		expect(await h.emit("session_before_compact", { reason: "threshold", signal })).toContainEqual({
			cancel: true,
		});
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
			const summaryRequest = payload.context.systemPrompt === SUMMARIZATION_SYSTEM_PROMPT;
			response.end(
				`${JSON.stringify({ type: "result", text: summaryRequest ? "Native relay task summary" : "local done", toolCalls: [], usage: { input_tokens: 10, output_tokens: 2 } })}\n`,
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
		const h = await nativeHarness(() => assistant());
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
		// Exercise the actual native lifecycle against the local relay, rather than emulating a summary dispatch.
		writePolicy(300000);
		await setConcurrencyLimit("codex/gpt-5.6-sol", 1);
		for (const message of history(400000).messages) h.session.appendMessage(message);
		h.agentSession.agent.state.messages = h.session.buildSessionContext().messages;
		await h.agentSession.setModel(selected);
		await h.agentSession.prompt("finish local task after native compression");
		expect(h.session.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(1);
		expect(bodies).toHaveLength(3);
		expect(
			h.session
				.getBranch()
				.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_COMPACTION_USAGE_TYPE),
		).toHaveLength(0);
		writePolicy(30000, false);
		const refused = await h.runtime.completeSimple(selected, context, { maxTokens: 4096 });
		expect(isContextPolicyFailure(refused)).toBe(true);
		expect(bodies).toHaveLength(3);
		expect(readConcurrencyState().requests).toEqual([]);
	});
});
