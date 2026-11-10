import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fauxAssistantMessage } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SUMMARIZATION_SYSTEM_PROMPT } from "../../src/core/compaction/utils.ts";
import {
	consumeContextPolicyFailure,
	registerContextPolicy,
} from "../../src/extensions/agent-team-loop/shared/context-extension.ts";
import { registerModelConcurrency } from "../../src/extensions/agent-team-loop/shared/model-concurrency-extension.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { createHarness, type Harness } from "../suite/harness.ts";

let root: string;
let exitListeners: Set<NodeJS.ExitListener>;
const harnesses: Harness[] = [];

beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-summary-recovery-"));
	exitListeners = new Set(process.listeners("exit"));
	vi.stubEnv("MW_RAG_SERVERS_FILE", path.join(root, "no-rag.yml"));
	vi.stubEnv("MW_CONCURRENCY_DIR", path.join(root, "slots"));
	vi.stubEnv("PI_WORKER_TASK", "");
	vi.stubEnv("PI_WORKER_IDLE_MS", "600000");
	vi.stubEnv("PI_WORKER_TIMEOUT_MS", "3600000");
});

afterEach(() => {
	while (harnesses.length) harnesses.pop()?.cleanup();
	for (const listener of process.listeners("exit")) {
		if (!exitListeners.has(listener)) process.removeListener("exit", listener);
	}
	vi.restoreAllMocks();
	vi.unstubAllEnvs();
	fs.rmSync(root, { recursive: true, force: true });
});

async function setup(worker: boolean) {
	const taskDir = path.join(root, ".agenticdoc/recovery/workers/task");
	fs.mkdirSync(taskDir, { recursive: true });
	const taskFile = path.join(taskDir, "task.md");
	fs.writeFileSync(taskFile, "type: coding\n\nRun the counter exactly once and report the result.\n");
	if (worker) vi.stubEnv("PI_WORKER_TASK", taskFile);
	fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
	fs.writeFileSync(
		path.join(root, ".mw/context.json"),
		JSON.stringify({ version: 1, defaults: { maxTokens: 100000 } }),
	);
	let effects = 0;
	const h = await createHarness({
		models: [{ id: "summary-recovery", reasoning: true, contextWindow: 300000, maxTokens: 65536 }],
		settings: {
			retry: { enabled: false },
			compaction: { enabled: false, reserveTokens: 16384, keepRecentTokens: 1 },
		},
		tools: [
			{
				name: "read",
				label: "Counter",
				description: "Increment once",
				parameters: Type.Object({ path: Type.String() }),
				execute: async () => {
					effects++;
					return { content: [{ type: "text", text: "counter=1" }], details: {} };
				},
			},
		],
		initialActiveToolNames: ["read"],
		extensionFactories: [
			async (pi) => {
				registerModelConcurrency(pi);
				registerContextPolicy(pi, {
					controlRoot: root,
					homeDir: path.join(root, "home"),
					taskFile: worker ? taskFile : "",
				});
				if (worker) await workerModeActivate(pi);
			},
		],
	});
	harnesses.push(h);
	h.session.agent.streamFunction = h.session.modelRuntime.streamSimple.bind(h.session.modelRuntime);
	await h.session.bindExtensions({});
	h.session.setThinkingLevel("high");
	const selected = h.getModel();
	h.sessionManager.appendMessage({ role: "user", content: "Prior work and constraints", timestamp: 1 });
	h.sessionManager.appendMessage({
		...fauxAssistantMessage("prior completed work ".repeat(8000)),
		api: selected.api,
		provider: selected.provider,
		model: selected.id,
		timestamp: 2,
	});
	h.sessionManager.appendMessage({ role: "user", content: "Continue with the assigned counter task.", timestamp: 3 });
	h.session.agent.state.messages = h.sessionManager.buildSessionContext().messages;
	return { h, taskDir, effects: () => effects };
}

describe("native summary recovery before persistence", () => {
	it.each([false, true])("recovers in the original task without replay (worker=%s)", async (worker) => {
		const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		const { h, taskDir, effects } = await setup(worker);
		let summaries = 0;
		h.setResponses([
			(context, options) => {
				expect(context.systemPrompt).toContain(SUMMARIZATION_SYSTEM_PROMPT);
				expect(options?.maxTokens).toBe(16384);
				expect(options?.reasoning).toBeUndefined();
				summaries++;
				return fauxAssistantMessage("PRIVATE-TRUNCATED", { stopReason: "length" });
			},
			(context, options) => {
				expect(context.systemPrompt).toContain(SUMMARIZATION_SYSTEM_PROMPT);
				expect(options?.maxTokens).toBe(32768);
				expect(options?.reasoning).toBeUndefined();
				expect(h.sessionManager.getEntries().some((entry) => entry.type === "compaction")).toBe(false);
				expect(exit).not.toHaveBeenCalled();
				summaries++;
				return fauxAssistantMessage("Goal: run counter once. Prior work is complete; preserve task constraints.");
			},
			(context, options) => {
				expect(context.systemPrompt).not.toBe(SUMMARIZATION_SYSTEM_PROMPT);
				expect(options?.reasoning).toBe("high");
				expect(h.sessionManager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(1);
				return fauxAssistantMessage([
					{
						type: "toolCall",
						id: "counter-once",
						name: "read",
						arguments: { path: path.join(taskDir, "task.md") },
					},
				]);
			},
			fauxAssistantMessage("Counter verified: 1. Assigned task complete."),
		]);
		await h.session.prompt("Run the assigned counter task.");
		expect(summaries).toBe(2);
		expect(effects()).toBe(1);
		expect(h.getPendingResponseCount()).toBe(0);
		expect(consumeContextPolicyFailure(h.session.extensionRunner.getModelRegistry())).toBeUndefined();
		const compactions = h.sessionManager.getEntries().filter((entry) => entry.type === "compaction");
		expect(compactions).toHaveLength(1);
		const resultEntry = h.sessionManager
			.getEntries()
			.find((entry) => entry.type === "custom" && entry.customType === "mw-native-summary-result");
		if (resultEntry?.type !== "custom") throw new Error("missing summary attempt report");
		const report = resultEntry.data as { attempts: Array<{ usage: { input: number; output: number } }> };
		expect(report.attempts).toHaveLength(2);
		expect(compactions[0].usage).toMatchObject({
			input: report.attempts.reduce((sum, attempt) => sum + attempt.usage.input, 0),
			output: report.attempts.reduce((sum, attempt) => sum + attempt.usage.output, 0),
		});
		expect(JSON.stringify(compactions)).not.toContain("PRIVATE-TRUNCATED");
		expect(h.eventsOfType("agent_settled")).toHaveLength(1);
		if (worker) {
			expect(exit).not.toHaveBeenCalled();
			const run = JSON.parse(fs.readFileSync(path.join(taskDir, "run.json"), "utf8")) as Record<string, unknown>;
			expect(run).toMatchObject({ status: "done", exit: 0 });
			expect(run.context_policy_code).toBeUndefined();
		}
		process.stdout.write("[VERIFY] VC-001,VC-002,VC-005: PASS\n");
	});

	it.each(["length", "empty", "thinking"])("rejects exhausted %s before saving native compaction", async (mode) => {
		const exit = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		const { h, taskDir, effects } = await setup(true);
		const failure =
			mode === "length"
				? fauxAssistantMessage("PRIVATE-TRUNCATED", { stopReason: "length" })
				: fauxAssistantMessage(mode === "thinking" ? [{ type: "thinking", thinking: "PRIVATE-THINKING" }] : " ");
		h.setResponses([failure, failure]);
		await expect(h.session.prompt("Run the assigned counter task.")).rejects.toThrow(
			mode === "length" ? "SUMMARY_TRUNCATED" : "SUMMARY_INVALID",
		);
		expect(h.faux.state.callCount).toBe(2);
		expect(effects()).toBe(0);
		expect(h.sessionManager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(0);
		expect(JSON.stringify(h.session.messages)).toContain("prior completed work");
		expect(exit).toHaveBeenCalledExactlyOnceWith(2);
		const run = JSON.parse(fs.readFileSync(path.join(taskDir, "run.json"), "utf8")) as {
			context_policy_code: string;
			context_policy_details: { summaryAttempts: unknown[] };
		};
		expect(run.context_policy_code).toBe(mode === "length" ? "SUMMARY_TRUNCATED" : "SUMMARY_INVALID");
		expect(run.context_policy_details.summaryAttempts).toHaveLength(2);
		expect(JSON.stringify(run)).not.toMatch(/PRIVATE-/);
		process.stdout.write("[VERIFY] VC-003,VC-005: PASS\n");
	});
});
