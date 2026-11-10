import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage } from "@earendil-works/pi-ai";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { registerContextPolicy } from "../../src/extensions/agent-team-loop/shared/context-extension.ts";
import { registerModelConcurrency } from "../../src/extensions/agent-team-loop/shared/model-concurrency-extension.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { createHarness, type Harness } from "../suite/harness.ts";

let root: string;
let oldExitListeners: Set<NodeJS.ExitListener>;
const harnesses: Harness[] = [];
beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-context-native-"));
	oldExitListeners = new Set(process.listeners("exit"));
	vi.stubEnv("MW_RAG_SERVERS_FILE", path.join(root, "no-rag.yml"));
	vi.stubEnv("MW_CONCURRENCY_DIR", path.join(root, "slots"));
	vi.stubEnv("PI_WORKER_IDLE_MS", "600000");
	vi.stubEnv("PI_WORKER_TIMEOUT_MS", "3600000");
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

describe("native AgentSession compaction and real worker settlement", () => {
	it.each(["policy-refusal", "parent-cancel", "in-flight-cancel"])(
		"preserves %s after the core compaction path flattens provider outcomes",
		async (mode) => {
			const taskDir = path.join(root, ".agenticdoc/context-native/workers/task");
			fs.mkdirSync(taskDir, { recursive: true });
			const taskFile = path.join(taskDir, "task.md");
			fs.writeFileSync(taskFile, "type: coding\n\nPreserve existing work and report remaining tasks.\n");
			fs.writeFileSync(path.join(taskDir, "report.md"), "partial evidence sentinel\n");
			vi.stubEnv("PI_WORKER_TASK", taskFile);
			fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
			const policyPath = path.join(root, ".mw/context.json");
			fs.writeFileSync(policyPath, JSON.stringify({ version: 1, defaults: { maxTokens: 80000 } }));
			const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
			let nativeEvents = 0;
			const sent: string[] = [];
			let h: Harness | undefined;
			h = await createHarness({
				models: [{ id: "native-fixture", contextWindow: 200000, maxTokens: 4096 }],
				settings: {
					retry: { enabled: false },
					compaction: { enabled: true, keepRecentTokens: 1, reserveTokens: 16384 },
				},
				extensionFactories: [
					async (pi) => {
						const send = pi.sendUserMessage.bind(pi);
						pi.sendUserMessage = (text, options) => {
							sent.push(typeof text === "string" ? text : JSON.stringify(text));
							send(text, options);
						};
						registerModelConcurrency(pi);
						registerContextPolicy(pi, { controlRoot: root, taskFile, homeDir: path.join(root, "home") });
						pi.on("session_before_compact", (event) => {
							if (event.reason !== "overflow") return;
							nativeEvents++;
							if (mode === "policy-refusal")
								fs.writeFileSync(policyPath, JSON.stringify({ version: 1, defaults: { maxTokens: 21000 } }));
							else if (mode === "parent-cancel") h?.session.abortCompaction();
						});
						await workerModeActivate(pi);
					},
				],
			});
			harnesses.push(h);
			h.session.agent.streamFunction = h.session.modelRuntime.streamSimple.bind(h.session.modelRuntime);
			await h.session.bindExtensions({});
			const selected = h.getModel();
			const oldUser = { role: "user" as const, content: "Prior task goal", timestamp: Date.now() - 1000 };
			const oldAssistant = {
				...fauxAssistantMessage("prior completed work ".repeat(1000)),
				api: selected.api,
				provider: selected.provider,
				model: selected.id,
				usage: {
					input: 100,
					output: 10,
					cacheRead: 0,
					cacheWrite: 0,
					totalTokens: 110,
					cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
				},
				timestamp: Date.now() - 500,
			};
			h.sessionManager.appendMessage(oldUser);
			h.sessionManager.appendMessage(oldAssistant);
			h.session.agent.state.messages = h.sessionManager.buildSessionContext().messages;
			h.setResponses([
				fauxAssistantMessage("partial business work", {
					stopReason: "error",
					errorMessage: "maximum context length exceeded",
				}),
				(_context, options) =>
					new Promise((resolve) => {
						const signal = options?.signal;
						if (!signal) throw new Error("missing native provider signal");
						signal.addEventListener(
							"abort",
							() =>
								resolve(
									fauxAssistantMessage("", { stopReason: "aborted", errorMessage: "native fixture canceled" }),
								),
							{ once: true },
						);
						queueMicrotask(() => h?.session.abortCompaction());
					}),
			]);
			await h.session.prompt("continue assigned task");
			expect(nativeEvents).toBe(1);
			expect(h.faux.state.callCount).toBe(mode === "in-flight-cancel" ? 2 : 1);
			expect(h.eventsOfType("compaction_start")).toEqual([{ type: "compaction_start", reason: "overflow" }]);
			expect(h.eventsOfType("compaction_end")).toHaveLength(1);
			expect(h.eventsOfType("agent_end")).toHaveLength(1);
			expect(h.eventsOfType("agent_settled")).toHaveLength(1);
			const run = JSON.parse(fs.readFileSync(path.join(taskDir, "run.json"), "utf8")) as Record<string, unknown>;
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(sent).toEqual([]);
			expect(trace).not.toMatch(/\[MODEL_ERR\]|\[MODEL_RETRY\]|\[MODEL_FALLBACK\]|self-check/);
			expect(run.model_exhausted).toBeUndefined();
			if (mode === "policy-refusal") {
				expect(h.eventsOfType("compaction_end")[0].errorMessage).toContain(
					"MW_CONTEXT_POLICY:NATIVE_SUMMARY_BUDGET",
				);
				expect(exit).toHaveBeenCalledExactlyOnceWith(2);
				expect(run).toMatchObject({
					status: "needs-clarification",
					exit: 2,
					context_policy_code: "NATIVE_SUMMARY_BUDGET",
				});
				expect(run.context_policy_details).toMatchObject({
					configured: 21000,
					effective: 21000,
					estimate: expect.any(Number),
					noProviderRequest: true,
					source: { maxTokens: { path: policyPath, scope: "project" } },
				});
			} else {
				expect(exit).toHaveBeenCalledExactlyOnceWith(1);
				expect(run).toMatchObject({ status: "failed", exit: 1, aborted: true });
				expect(run.context_policy_code).toBeUndefined();
			}
			expect(fs.readFileSync(path.join(taskDir, "report.md"), "utf8")).toBe("partial evidence sentinel\n");
			expect(h.sessionManager.getBranch().filter((entry) => entry.type === "compaction")).toHaveLength(0);
		},
	);
});
