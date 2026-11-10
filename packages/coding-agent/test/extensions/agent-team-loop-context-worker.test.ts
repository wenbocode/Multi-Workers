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
import { SUMMARIZATION_SYSTEM_PROMPT } from "../../src/core/compaction/utils.ts";
import { SessionManager } from "../../src/core/session-manager.ts";
import {
	CONTEXT_COMPACTION_USAGE_TYPE,
	type ContextCompactionUsage,
	contextPolicyFailureMessage,
	MwContextPolicyError,
} from "../../src/extensions/agent-team-loop/shared/context-controller.ts";
import { registerContextPolicy } from "../../src/extensions/agent-team-loop/shared/context-extension.ts";
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

async function workerHarness(
	options: {
		policy?: boolean;
		phases?: boolean;
		type?: "coding" | "review";
		retry?: boolean;
		worker?: boolean;
		nativeKeepRecentTokens?: number;
	} = {},
) {
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
		settings: {
			retry: { enabled: options.retry ?? false, maxRetries: 1, baseDelayMs: 1 },
			compaction: { enabled: false, keepRecentTokens: options.nativeKeepRecentTokens ?? 1, reserveTokens: 16384 },
		},
		extensionFactories: [
			async (pi) => {
				const send = pi.sendUserMessage.bind(pi);
				pi.sendUserMessage = (text, options) => {
					sendCalls.push(typeof text === "string" ? text : JSON.stringify(text));
					send(text, options);
				};
				if (options.policy)
					registerContextPolicy(pi, { controlRoot: root, taskFile, homeDir: path.join(root, "home") });
				if (options.worker !== false) await workerModeActivate(pi);
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
	it.each(["throw", "rejected-stream"] as const)(
		"native provider %s is safely projected before core/worker persistence",
		async (mode) => {
			const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
			const { h, taskDir } = await workerHarness({ policy: true });
			fs.writeFileSync(
				path.join(root, ".mw/context.json"),
				JSON.stringify({ version: 1, defaults: { maxTokens: 80000, compaction: { triggerRatio: 0.2 } } }),
			);
			h.sessionManager.appendMessage({ role: "user", content: "Preserve task work", timestamp: 1 });
			h.sessionManager.appendMessage(fauxAssistantMessage("completed work ".repeat(5000)));
			h.session.agent.state.messages = h.sessionManager.buildSessionContext().messages;
			const failure = Object.assign(new Error("fetch failed PRIVATE-NATIVE-KEY https://private?key=secret"), {
				code: "ECONNRESET",
				status: 503,
			});
			let calls = 0;
			const stream = () => {
				calls++;
				if (mode === "throw") throw failure;
				const result = createAssistantMessageEventStream();
				result.end(fauxAssistantMessage(""));
				Object.defineProperty(result, "result", {
					value: async () => {
						throw failure;
					},
				});
				return result;
			};
			const selected = h.getModel();
			h.session.modelRuntime.registerNativeProvider({
				id: selected.provider,
				name: "Throwing native fixture",
				getModels: () => h.models,
				auth: { apiKey: { name: "Fixture", resolve: async () => ({ auth: { apiKey: "faux-key" } }) } },
				stream,
				streamSimple: stream,
			});
			await expect(h.session.prompt("continue assigned work")).rejects.toMatchObject({
				details: {
					code: "SUMMARY_FAILED",
					summaryFailure: { category: "network", httpStatus: 503, errorType: "ECONNRESET" },
					nativeSummaryUsage: null,
				},
			});
			expect(exit).toHaveBeenCalledExactlyOnceWith(2);
			expect(calls).toBe(1);
			expect(h.faux.state.callCount).toBe(0);
			const persisted = fs.readFileSync(path.join(taskDir, "run.json"), "utf8");
			expect(persisted).not.toContain("PRIVATE-");
			expect(persisted).not.toContain("https://private");
			expect(JSON.stringify(h.events)).not.toContain("PRIVATE-");
			expect(h.sessionManager.getBranch().filter((entry) => entry.type === "compaction")).toHaveLength(0);
		},
	);
	it.each(["transient", "quota", "no-progress"] as const)(
		"native %s retry follows pi settings without leaking failed text",
		async (kind) => {
			const { h } = await workerHarness({
				policy: true,
				retry: true,
				worker: false,
				nativeKeepRecentTokens: kind === "no-progress" ? 100 : 1,
			});
			fs.writeFileSync(
				path.join(root, ".mw/context.json"),
				JSON.stringify({ version: 1, defaults: { maxTokens: 80000, compaction: { triggerRatio: 0.2 } } }),
			);
			h.sessionManager.appendMessage({ role: "user", content: "Retain all completed work", timestamp: 1 });
			h.sessionManager.appendMessage(fauxAssistantMessage("completed work ".repeat(5000)));
			h.sessionManager.appendMessage({ role: "user", content: "Prior confirmation", timestamp: 2 });
			h.sessionManager.appendMessage(fauxAssistantMessage("Confirmed."));
			h.session.agent.state.messages = h.sessionManager.buildSessionContext().messages;
			let summaries = 0,
				business = 0;
			const response = (context: Context) => {
				if (context.systemPrompt !== SUMMARIZATION_SYSTEM_PROMPT) {
					business++;
					return fauxAssistantMessage("Task complete without replay.");
				}
				summaries++;
				if (summaries === 1)
					return fauxAssistantMessage("", {
						stopReason: "error",
						errorMessage:
							kind === "quota"
								? "HTTP 429 insufficient_quota PRIVATE-QUOTA-KEY"
								: "HTTP 503 service unavailable PRIVATE-TRANSIENT-KEY",
					});
				return fauxAssistantMessage("Native retained history: all prior work complete, continue remaining task.");
			};
			h.setResponses(Array.from({ length: 8 }, () => response));
			if (kind === "quota")
				await expect(h.session.prompt("continue assigned work")).rejects.toMatchObject({
					details: { code: "SUMMARY_FAILED", summaryFailure: { category: "quota" } },
				});
			else if (kind === "no-progress")
				await expect(h.session.prompt("continue assigned work")).rejects.toMatchObject({
					details: { code: "SUMMARY_NO_PROGRESS" },
				});
			else await h.session.prompt("continue assigned work");
			// Native split-turn compaction makes two generation calls; one transient retry adds a third.
			expect([summaries, business]).toEqual(kind === "quota" ? [1, 0] : kind === "no-progress" ? [2, 0] : [3, 1]);
			expect(h.sessionManager.getBranch().filter((entry) => entry.type === "compaction")).toHaveLength(
				kind === "quota" ? 0 : 1,
			);
			expect(JSON.stringify(h.sessionManager.getEntries())).not.toContain("PRIVATE-");
			expect(JSON.stringify(h.events)).not.toContain("PRIVATE-");
		},
	);
	it.each([
		{ status: "error", code: "SUMMARY_FAILED", category: "quota" },
		{ status: "length", code: "SUMMARY_TRUNCATED", category: "unknown" },
		{ status: "aborted", code: "SUMMARY_ABORTED", category: "unknown" },
	] as const)("real worker persists exhausted $status summary diagnostics without phase advance", async (failure) => {
		const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		const { h, taskDir, sendCalls } = await workerHarness({ policy: true, phases: true });
		fs.writeFileSync(
			path.join(root, ".mw/context.json"),
			JSON.stringify({
				version: 1,
				defaults: { maxTokens: 80000, compaction: { triggerRatio: 0.2, targetRatio: 0.1, keepRecentTokens: 100 } },
			}),
		);
		h.sessionManager.appendMessage({ role: "user", content: "preserve existing work", timestamp: 1 });
		h.sessionManager.appendMessage(fauxAssistantMessage("completed work ".repeat(5000)));
		h.session.agent.state.messages = h.sessionManager.buildSessionContext().messages;
		let summaries = 0;
		let business = 0;
		const attempts = failure.status === "length" ? 2 : 1;
		h.setResponses(
			Array.from({ length: attempts }, () => (context: Context) => {
				if (context.systemPrompt?.startsWith(SUMMARIZATION_SYSTEM_PROMPT)) summaries++;
				else business++;
				return fauxAssistantMessage("PRIVATE-SUMMARY-BODY", {
					stopReason: failure.status,
					errorMessage:
						failure.status === "error" ? "HTTP 429 insufficient_quota PRIVATE-API-KEY" : "PRIVATE-ERROR-TEXT",
				});
			}),
		);
		await expect(h.session.prompt("continue assigned work")).rejects.toMatchObject({
			details: { code: failure.code },
		});
		expect(exit).toHaveBeenCalledExactlyOnceWith(2);
		expect([summaries, business, h.faux.state.callCount]).toEqual([attempts, 0, attempts]);
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
		expect(details.attemptId).toEqual(expect.any(String));
		expect(details.attemptStartedAt).toEqual(expect.any(String));
		expect(details.nativeSummaryUsage).toEqual({
			input: expect.any(Number),
			output: expect.any(Number),
			cacheRead: 0,
			cacheWrite: 0,
		});
		expect((details.nativeSummaryUsage as { input: number }).input).toBeGreaterThan(0);
		expect(
			h.sessionManager
				.getBranch()
				.filter((entry) => entry.type === "custom" && entry.customType === CONTEXT_COMPACTION_USAGE_TYPE),
		).toHaveLength(0);
		expect(h.sessionManager.getBranch().filter((entry) => entry.type === "compaction")).toHaveLength(0);
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

it("historical MW usage remains readable and deduplicated by the real Python stats kernel", async () => {
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
	// Explicit historical fixture: current controller no longer emits this legacy record.
	const historical: ContextCompactionUsage = {
		version: 1,
		attemptId: "historical-summary",
		attemptStartedAt: new Date().toISOString(),
		provider: model.provider,
		model: model.id,
		purpose: "summary",
		providerRequestStarted: true,
		status: "stop",
		usage: { input: 101, output: 202, cacheRead: 303, cacheWrite: 404 },
	};
	session.appendCustomEntry(CONTEXT_COMPACTION_USAGE_TYPE, historical);
	session.appendCustomEntry(CONTEXT_COMPACTION_USAGE_TYPE, historical);
	session.appendCustomEntry(CONTEXT_COMPACTION_USAGE_TYPE, {
		...historical,
		attemptId: "historical-queued",
		providerRequestStarted: false,
		status: "aborted",
		usage: null,
	});
	session.appendMessage(contextPolicyFailureMessage(model, new MwContextPolicyError("INPUT_BUDGET")));
	const file = session.getSessionFile();
	if (!file) throw new Error("persisted session missing");
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
