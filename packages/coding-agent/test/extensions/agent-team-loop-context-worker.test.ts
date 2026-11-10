import { execFileSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
	type Api,
	type AssistantMessage,
	type Context,
	createAssistantMessageEventStream,
	fauxAssistantMessage,
	type Model,
} from "@earendil-works/pi-ai";
import { streamSimple as streamFaux } from "@earendil-works/pi-ai/compat";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SessionManager } from "../../src/core/session-manager.ts";
import {
	CONTEXT_COMPACTION_USAGE_TYPE,
	type ContextCompactionUsage,
	ContextController,
	contextPolicyFailureMessage,
	MwContextPolicyError,
} from "../../src/extensions/agent-team-loop/shared/context-controller.ts";
import { registerContextPolicy } from "../../src/extensions/agent-team-loop/shared/context-extension.ts";
import { resolveContextPolicy } from "../../src/extensions/agent-team-loop/shared/context-policy.ts";
import { checkRecovery } from "../../src/extensions/agent-team-loop/worker/output-sections.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { createHarness, type Harness } from "../suite/harness.ts";

const model: Model<Api> = {
	id: "fixture",
	name: "Fixture",
	provider: "context-fixture",
	api: "openai-completions",
	baseUrl: "https://invalid.invalid",
	contextWindow: 80000,
	maxTokens: 4096,
	reasoning: false,
	input: ["text"],
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
};
let root: string;
let oldExitListeners: Set<NodeJS.ExitListener>;
const harnesses: Harness[] = [];
beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-context-worker-"));
	oldExitListeners = new Set(process.listeners("exit"));
	vi.stubEnv("MW_RAG_SERVERS_FILE", path.join(root, "no-rag.yml"));
});
afterEach(() => {
	while (harnesses.length) harnesses.pop()?.cleanup();
	for (const listener of process.listeners("exit")) {
		if (!oldExitListeners.has(listener)) process.removeListener("exit", listener);
	}
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	fs.rmSync(root, { recursive: true, force: true });
});

async function workerHarness(options: { policy?: boolean; phases?: boolean; type?: "coding" | "review" } = {}) {
	const taskDir = path.join(root, ".agenticdoc", "context-key", "workers", "context-task");
	fs.mkdirSync(taskDir, { recursive: true });
	const taskFile = path.join(taskDir, "task.md");
	fs.writeFileSync(
		taskFile,
		`type: ${options.type ?? "coding"}\n\nPreserve existing work.\n${options.phases ? "\n- name: implement\n  prompt: |\n    never advance after refusal\n" : ""}`,
	);
	fs.writeFileSync(path.join(taskDir, "report.md"), "existing partial evidence sentinel\n");
	vi.stubEnv("PI_WORKER_TASK", taskFile);
	if (options.policy) {
		fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
		fs.writeFileSync(
			path.join(root, ".mw", "context.json"),
			JSON.stringify({ version: 1, defaults: { maxTokens: 1 } }),
		);
	}
	const sendCalls: string[] = [];
	const h = await createHarness({
		settings: { retry: { enabled: false }, compaction: { enabled: false } },
		extensionFactories: [
			async (pi) => {
				const send = pi.sendUserMessage.bind(pi);
				pi.sendUserMessage = (text, options) => {
					sendCalls.push(typeof text === "string" ? text : JSON.stringify(text));
					send(text, options);
				};
				if (options.policy)
					registerContextPolicy(pi, { controlRoot: root, taskFile, homeDir: path.join(root, "home") });
				await workerModeActivate(pi);
			},
		],
	});
	harnesses.push(h);
	if (options.policy) {
		const selected = h.getModel();
		h.session.modelRuntime.registerNativeProvider({
			id: selected.provider,
			name: "Worker fixture",
			getModels: () => h.models,
			auth: { apiKey: { name: "Fixture", resolve: async () => ({ auth: { apiKey: "faux-key" } }) } },
			stream: streamFaux,
			streamSimple: streamFaux,
		});
		h.session.agent.streamFunction = (selectedModel, context, requestOptions) =>
			h.session.modelRuntime.streamSimple(selectedModel, context, requestOptions);
	}
	return { h, taskDir, sendCalls };
}

describe("context worker terminal path", () => {
	it.each([
		{ status: "error", code: "SUMMARY_FAILED", category: "quota" },
		{ status: "length", code: "SUMMARY_TRUNCATED", category: "unknown" },
		{ status: "aborted", code: "SUMMARY_ABORTED", category: "unknown" },
	] as const)("real worker persists $status summary diagnostics without retry or phase advance", async (failure) => {
		const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		const { h, taskDir, sendCalls } = await workerHarness({ policy: true, phases: true });
		fs.writeFileSync(
			path.join(root, ".mw/context.json"),
			JSON.stringify({
				version: 1,
				defaults: { maxTokens: 80000, compaction: { triggerRatio: 0.2, targetRatio: 0.1, keepRecentTokens: 100 } },
			}),
		);
		h.session.agent.state.messages = [
			{ role: "user", content: "preserve existing work", timestamp: 1 },
			fauxAssistantMessage("completed work ".repeat(5000)),
		];
		let summaries = 0;
		let business = 0;
		h.setResponses([
			(context) => {
				if (context.systemPrompt?.includes("Summarize historical task state")) summaries++;
				else business++;
				return fauxAssistantMessage("PRIVATE-SUMMARY-BODY", {
					stopReason: failure.status,
					errorMessage:
						failure.status === "error" ? "HTTP 429 insufficient_quota PRIVATE-API-KEY" : "PRIVATE-ERROR-TEXT",
				});
			},
		]);
		await h.session.prompt("continue assigned work");
		expect(exit).toHaveBeenCalledExactlyOnceWith(2);
		expect([summaries, business, h.faux.state.callCount]).toEqual([1, 0, 1]);
		expect(sendCalls).toEqual([]);
		const rawRun = fs.readFileSync(path.join(taskDir, "run.json"), "utf8");
		const run = JSON.parse(rawRun) as Record<string, unknown>;
		expect(run).toMatchObject({
			status: "needs-clarification",
			exit: 2,
			context_policy_code: failure.code,
			context_policy_details: {
				code: failure.code,
				summaryStatus: failure.status,
				noProviderRequest: true,
				provider: h.getModel().provider,
				model: h.getModel().id,
				summaryFailure: { category: failure.category },
			},
		});
		const details = run.context_policy_details as Record<string, unknown>;
		const usage = h.sessionManager
			.getBranch()
			.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_COMPACTION_USAGE_TYPE);
		expect(usage).toHaveLength(1);
		if (usage[0].type !== "custom") throw new Error("missing usage");
		expect(usage[0].data).toMatchObject({
			attemptId: details.attemptId,
			attemptStartedAt: details.attemptStartedAt,
			providerRequestStarted: true,
			status: failure.status,
		});
		expect(
			h.sessionManager
				.getBranch()
				.filter((entry) => entry.type === "custom" && entry.customType === "mw-context-checkpoint"),
		).toHaveLength(0);
		expect(run.model_exhausted).toBeUndefined();
		expect(rawRun).not.toContain("PRIVATE-");
		const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
		expect(trace).toContain("[MW_CONTEXT_TERMINAL]");
		expect(trace).not.toMatch(/\[MODEL_ERR\]|\[MODEL_RETRY\]|\[MODEL_FALLBACK\]|\[PHASE\]|self-check/);
		expect(fs.readFileSync(path.join(taskDir, "report.md"), "utf8")).toBe("existing partial evidence sentinel\n");
	});

	it.each(["coding", "review"] as const)(
		"real %s worker records needs-clarification/exit2 before any provider request or phase",
		async (type) => {
			const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
			const { h, taskDir, sendCalls } = await workerHarness({ policy: true, phases: true, type });
			await h.session.prompt("perform assigned work");
			expect(exit).toHaveBeenCalledExactlyOnceWith(2);
			expect(h.faux.state.callCount).toBe(0);
			expect(sendCalls).toEqual([]);
			const run = JSON.parse(fs.readFileSync(path.join(taskDir, "run.json"), "utf8")) as Record<string, unknown>;
			expect(run).toMatchObject({ status: "needs-clarification", exit: 2, context_policy_code: "INVALID_POLICY" });
			expect(run.context_policy_details).toMatchObject({
				code: "INVALID_POLICY",
				noProviderRequest: true,
				configured: 1,
			});
			expect(run.model_exhausted).toBeUndefined();
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("needs-clarification");
			expect(checkRecovery(output, type).missing).toEqual([]);
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toContain("[MW_CONTEXT_TERMINAL]");
			expect(trace).toContain("exit=2");
			expect(trace).not.toMatch(/\[MODEL_ERR\]|\[MODEL_RETRY\]|\[MODEL_FALLBACK\]|\[PHASE\]|self-check/);
			expect(fs.readFileSync(path.join(taskDir, "report.md"), "utf8")).toBe("existing partial evidence sentinel\n");
		},
	);

	it("actual aborted assistant remains aborted and writes failed/exit1 with explicit cancellation metadata", async () => {
		const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		const { h, taskDir, sendCalls } = await workerHarness({ phases: true });
		h.setResponses([fauxAssistantMessage("", { stopReason: "aborted", errorMessage: "Request cancelled" })]);
		await h.session.prompt("cancel this task");
		expect(exit).toHaveBeenCalledExactlyOnceWith(1);
		expect(h.faux.state.callCount).toBe(1);
		expect(sendCalls).toEqual([]);
		expect(h.session.messages.filter((message) => message.role === "assistant").at(-1)).toMatchObject({
			stopReason: "aborted",
		});
		const run = JSON.parse(fs.readFileSync(path.join(taskDir, "run.json"), "utf8")) as Record<string, unknown>;
		expect(run).toMatchObject({ status: "failed", exit: 1, aborted: true });
		expect(run.model_exhausted).toBeUndefined();
		expect(run.context_policy_code).toBeUndefined();
		const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
		expect(output).toContain("aborted: parent request cancelled");
		expect(fs.readFileSync(path.join(taskDir, "trace.log"), "utf8")).not.toMatch(/\[MODEL_ERR\]|\[PHASE\]/);
	});

	it("preserves the existing ordinary model-error exit3 path", async () => {
		const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		const { h, taskDir, sendCalls } = await workerHarness();
		h.setResponses([fauxAssistantMessage("", { stopReason: "error", errorMessage: "ordinary fixture failure" })]);
		await h.session.prompt("ordinary model error");
		expect(exit).toHaveBeenCalledExactlyOnceWith(3);
		expect(h.faux.state.callCount).toBe(1);
		expect(sendCalls).toEqual([]);
		expect(JSON.parse(fs.readFileSync(path.join(taskDir, "run.json"), "utf8"))).toMatchObject({
			status: "failed",
			exit: 3,
			model_exhausted: true,
		});
		expect(fs.readFileSync(path.join(taskDir, "trace.log"), "utf8")).toContain("[MODEL_ERR]");
	});
});

it("production controller appendEntry persists summary usage once for the real Python stats kernel", async () => {
	const session = SessionManager.create(root, path.join(root, "sessions"));
	const business: AssistantMessage = {
		...fauxAssistantMessage("business"),
		api: model.api,
		provider: model.provider,
		model: model.id,
		usage: {
			input: 1,
			output: 2,
			cacheRead: 3,
			cacheWrite: 4,
			totalTokens: 10,
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
		},
	};
	session.appendMessage(business);
	const policy = resolveContextPolicy({ controlRoot: root, homeDir: path.join(root, "home") });
	policy.compaction = {
		...policy.compaction,
		triggerRatio: 0.3,
		targetRatio: 0.2,
		keepRecentTokens: 100,
		maxSummaryTokens: 1000,
	};
	const controller = new ContextController({
		readPolicy: () => policy,
		getCheckpointEntries: () => session.getBranch().filter((entry) => entry.type === "custom"),
		appendEntry: (type, data) => {
			session.appendCustomEntry(type, data);
		},
	});
	const context: Context = {
		messages: [
			{ role: "user", content: "fixed task", timestamp: 0 },
			{ ...business, content: [{ type: "text", text: "old completed work ".repeat(4500) }] },
			{ role: "user", content: "continue", timestamp: 1 },
		],
	};
	await controller.prepare(model, context, { maxTokens: 4096 }, () => {
		const result: AssistantMessage = {
			...business,
			content: [
				{
					type: "text",
					text: JSON.stringify({
						goal: "fixed task",
						constraints: "allowed only",
						decisions: "none",
						changes: "none",
						verification: "none",
						remaining: "continue",
					}),
				},
			],
			usage: { ...business.usage, input: 101, output: 202, cacheRead: 303, cacheWrite: 404, totalTokens: 1010 },
		};
		const stream = createAssistantMessageEventStream();
		stream.push({ type: "done", reason: "stop", message: result });
		stream.end(result);
		return stream;
	});
	const custom = session
		.getBranch()
		.find((entry) => entry.type === "custom" && entry.customType === CONTEXT_COMPACTION_USAGE_TYPE);
	if (custom?.type !== "custom") throw new Error("production summary usage missing");
	expect(custom.data).toMatchObject({ providerRequestStarted: true, status: "stop" });
	session.appendCustomEntry(CONTEXT_COMPACTION_USAGE_TYPE, custom.data as ContextCompactionUsage);
	const cancelledController = new ContextController({
		readPolicy: () => policy,
		getCheckpointEntries: () => [],
		appendEntry: (type, data) => {
			session.appendCustomEntry(type, data);
		},
	});
	const parent = new AbortController();
	let dispatchQueued = false;
	const cancelled = cancelledController.prepare(model, context, { maxTokens: 4096, signal: parent.signal }, () => {
		dispatchQueued = true;
		const pending = createAssistantMessageEventStream();
		Object.defineProperty(pending, "providerRequestStarted", { get: () => false });
		return pending;
	});
	const rejection = expect(cancelled).rejects.toBeDefined();
	await vi.waitFor(() => expect(dispatchQueued).toBe(true));
	parent.abort();
	await rejection;
	const cancelledUsage = session
		.getBranch()
		.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_COMPACTION_USAGE_TYPE);
	expect(cancelledUsage).toHaveLength(3);
	const lastCancelledUsage = cancelledUsage.at(-1);
	if (lastCancelledUsage?.type !== "custom") throw new Error("cancelled summary usage missing");
	expect(lastCancelledUsage.data).toMatchObject({ providerRequestStarted: false, status: "aborted", usage: null });
	session.appendMessage(contextPolicyFailureMessage(model, new MwContextPolicyError("INPUT_BUDGET")));
	const file = session.getSessionFile();
	if (!file) throw new Error("persisted session missing");
	expect(fs.existsSync(file)).toBe(true);
	const python = execFileSync(
		process.env.PYTHON_EXE ?? "python",
		["-m", "pytest", "-q", "test_context_usage.py", "-k", "typescript_production_session_fixture"],
		{
			cwd: path.resolve(import.meta.dirname, "../../../multi-workers"),
			env: { ...process.env, MW_CONTEXT_TS_FIXTURE: file },
			encoding: "utf8",
		},
	);
	expect(python).toContain("1 passed");
	process.stdout.write(python);
});
