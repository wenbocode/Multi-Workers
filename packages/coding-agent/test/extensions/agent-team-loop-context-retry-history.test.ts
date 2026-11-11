import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { AgentTool } from "@earendil-works/pi-agent-core";
import {
	type Api,
	type AssistantMessage,
	type Context,
	fauxAssistantMessage,
	fauxToolCall,
	type Message,
	type Model,
} from "@earendil-works/pi-ai";
import { streamSimple as streamFaux } from "@earendil-works/pi-ai/compat";
import { Type } from "typebox";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { SUMMARIZATION_SYSTEM_PROMPT } from "../../src/core/compaction/utils.ts";
import { computeContextBudget, estimateContext } from "../../src/extensions/agent-team-loop/shared/context-budget.ts";
import { completeContextGroups } from "../../src/extensions/agent-team-loop/shared/context-checkpoint.ts";
import { ContextController } from "../../src/extensions/agent-team-loop/shared/context-controller.ts";
import { registerContextPolicy } from "../../src/extensions/agent-team-loop/shared/context-extension.ts";
import { resolveContextPolicy } from "../../src/extensions/agent-team-loop/shared/context-policy.ts";
import { createHarness, type Harness } from "../suite/harness.ts";

let root: string;
const harnesses: Harness[] = [];
beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-retry-history-"));
});
afterEach(() => {
	while (harnesses.length) harnesses.pop()?.cleanup();
	fs.rmSync(root, { recursive: true, force: true });
});

function toolResult(id: string, name = "read"): Message {
	return {
		role: "toolResult",
		toolCallId: id,
		toolName: name,
		content: [{ type: "text", text: "completed" }],
		isError: false,
		timestamp: 1,
	};
}

describe("failed retry history does not suppress native compaction", () => {
	it.each(["error", "aborted"] as const)(
		"keeps %s attempts as nonexecuted history and still plans a later completed batch",
		async (status) => {
			const failed = fauxAssistantMessage(
				[fauxToolCall("edit", { path: "never-executed" }, { id: "failed-edit" })],
				{ stopReason: status },
			);
			const context: Context = {
				messages: [
					{ role: "user", content: "Preserve the task and restrictions", timestamp: 1 },
					fauxAssistantMessage("x".repeat(150000)),
					failed,
					fauxAssistantMessage([fauxToolCall("read", { path: "completed" }, { id: "success-read" })], {
						stopReason: "toolUse",
					}),
					toolResult("success-read"),
				],
			};
			const before = JSON.stringify(context);
			expect(completeContextGroups(context.messages)).toEqual([
				{ start: 0, end: 1 },
				{ start: 1, end: 2 },
				{ start: 2, end: 3 },
				{ start: 3, end: 5 },
			]);
			const policy = resolveContextPolicy({ controlRoot: root, homeDir: path.join(root, "home") });
			policy.maxTokens = 80000;
			const controller = new ContextController({ readPolicy: () => policy });
			const model: Model<Api> = {
				id: "history-model",
				name: "History fixture",
				provider: "fixture",
				api: "openai-completions",
				baseUrl: "https://invalid.invalid",
				reasoning: false,
				input: ["text"],
				contextWindow: 160000,
				maxTokens: 16384,
				cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
			};
			const planned = await controller.planNativeCompaction(model, context);
			expect(planned?.beforeTokens).toBeGreaterThanOrEqual(planned?.budget.triggerTokens ?? Infinity);
			expect(planned?.budget.configuredMaxTokens).toBe(80000);
			expect(JSON.stringify(context)).toBe(before);
			expect(failed.content).toHaveLength(1);
		},
	);

	it.each(["stop", "toolUse", "length"] as const)(
		"still requires real %s tool calls to have every matching result",
		(status) => {
			const call = fauxAssistantMessage([fauxToolCall("read", {}, { id: "live" })], { stopReason: status });
			expect(() => completeContextGroups([call])).toThrow("MW_CONTEXT_INCOMPLETE_TOOL_BATCH");
			expect(completeContextGroups([call, toolResult("live")])).toEqual([{ start: 0, end: 2 }]);
		},
	);

	it("still rejects duplicate live calls, duplicate results and wrong tool names", () => {
		const call = fauxToolCall("read", {}, { id: "live" });
		expect(() => completeContextGroups([fauxAssistantMessage([call, call])])).toThrow(
			"MW_CONTEXT_DUPLICATE_TOOL_CALL",
		);
		expect(() =>
			completeContextGroups([fauxAssistantMessage([call]), toolResult("live"), toolResult("live")]),
		).toThrow("MW_CONTEXT_ORPHAN_TOOL_RESULT");
		expect(() => completeContextGroups([fauxAssistantMessage([call]), toolResult("live", "edit")])).toThrow(
			"MW_CONTEXT_INCOMPLETE_TOOL_BATCH",
		);
	});

	it.each(["error", "aborted"] as const)("does not use a %s attempt to legitimize an orphan tool result", (status) => {
		const failed = fauxAssistantMessage([fauxToolCall("edit", {}, { id: "failed" })], { stopReason: status });
		expect(() => completeContextGroups([failed, toolResult("failed", "edit")])).toThrow(
			"MW_CONTEXT_ORPHAN_TOOL_RESULT",
		);
	});

	it("real AgentSession retries an error carrying an unexecuted edit then compacts and continues without replay", async () => {
		fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
		fs.writeFileSync(
			path.join(root, ".mw", "context.json"),
			JSON.stringify({
				version: 1,
				defaults: { maxTokens: 65000, compaction: { enabled: true, triggerRatio: 0.6 } },
			}),
		);
		let edits = 0;
		let reads = 0;
		const parameters = Type.Object({ path: Type.String() });
		const tools: AgentTool<typeof parameters>[] = [
			{
				name: "edit",
				label: "Edit",
				description: "Record an edit side effect",
				parameters,
				execute: async () => {
					edits++;
					return { content: [{ type: "text", text: "edited" }], details: {} };
				},
			},
			{
				name: "read",
				label: "Read",
				description: "Read once",
				parameters,
				execute: async () => {
					reads++;
					return { content: [{ type: "text", text: "r".repeat(60000) }], details: {} };
				},
			},
		];
		const h = await createHarness({
			models: [{ id: "retry-history", contextWindow: 100000, maxTokens: 32000 }],
			tools,
			initialActiveToolNames: ["read", "edit"],
			settings: {
				retry: { enabled: true, maxRetries: 1, baseDelayMs: 1 },
				compaction: { enabled: false, keepRecentTokens: 1, reserveTokens: 16384 },
			},
			extensionFactories: [
				(pi) => registerContextPolicy(pi, { controlRoot: root, homeDir: path.join(root, "home") }),
			],
		});
		harnesses.push(h);
		const selected = h.getModel();
		h.session.modelRuntime.registerNativeProvider({
			id: selected.provider,
			name: "Retry fixture",
			getModels: () => h.models,
			auth: { apiKey: { name: "Fixture", resolve: async () => ({ auth: { apiKey: "faux-key" } }) } },
			stream: streamFaux,
			streamSimple: streamFaux,
		});
		h.session.agent.streamFunction = h.session.modelRuntime.streamSimple.bind(h.session.modelRuntime);
		h.sessionManager.appendMessage({ role: "user", content: "Old task restrictions", timestamp: 1 });
		h.sessionManager.appendMessage(fauxAssistantMessage("historical completed work ".repeat(600)));
		h.session.agent.state.messages = h.sessionManager.buildSessionContext().messages;
		let business = 0;
		let summaries = 0;
		let retainedFailed: AssistantMessage | undefined;
		let retainedFailedSnapshot: string | undefined;
		const respond = (context: Context): AssistantMessage => {
			if (context.systemPrompt === SUMMARIZATION_SYSTEM_PROMPT) {
				summaries++;
				return fauxAssistantMessage("Retain restrictions; the read completed and its result remains available.");
			}
			business++;
			const policy = resolveContextPolicy({ controlRoot: root, homeDir: path.join(root, "home") });
			expect(estimateContext(context).estimatedTokens).toBeLessThanOrEqual(
				computeContextBudget(selected, policy).inputBudget,
			);
			if (business === 1)
				return fauxAssistantMessage([fauxToolCall("edit", { path: "must-not-edit" }, { id: "failed-edit" })], {
					stopReason: "error",
					errorMessage: "503 server overloaded",
				});
			if (business === 2) {
				expect(
					context.messages.some((message) => message.role === "assistant" && message.stopReason === "error"),
				).toBe(false);
				const original = h.sessionManager
					.getEntries()
					.find(
						(entry) =>
							entry.type === "message" &&
							entry.message.role === "assistant" &&
							entry.message.stopReason === "error",
					);
				if (original?.type !== "message" || original.message.role !== "assistant")
					throw new Error("Failed attempt history missing");
				retainedFailed = original.message;
				retainedFailedSnapshot = JSON.stringify(original.message);
				return fauxAssistantMessage([fauxToolCall("read", { path: "once" }, { id: "success-read" })], {
					stopReason: "toolUse",
				});
			}
			expect(summaries).toBeGreaterThan(0);
			return fauxAssistantMessage("Task complete after retry and native compaction");
		};
		h.setResponses(Array.from({ length: 8 }, () => respond));
		await h.session.prompt("Finish the assigned task");
		expect(h.session.state.errorMessage).toBeUndefined();
		expect(h.eventsOfType("auto_retry_start")).toHaveLength(1);
		expect(h.eventsOfType("compaction_start")).toHaveLength(1);
		expect(h.sessionManager.getEntries().filter((entry) => entry.type === "compaction")).toHaveLength(1);
		expect(business).toBe(3);
		expect(edits).toBe(0);
		expect(reads).toBe(1);
		expect(
			h.sessionManager.getEntries().filter(
				(entry) =>
					entry.type === "message" &&
					entry.message.role === "user" &&
					(typeof entry.message.content === "string"
						? entry.message.content
						: entry.message.content
								.filter((part) => part.type === "text")
								.map((part) => part.text)
								.join("")) === "Finish the assigned task",
			),
		).toHaveLength(1);
		expect(
			h.sessionManager.getEntries().filter((entry) => entry.type === "message" && entry.message.role === "user"),
		).toHaveLength(2);
		expect(retainedFailed).toBeDefined();
		expect(JSON.stringify(retainedFailed)).toBe(retainedFailedSnapshot);
		expect(
			h.sessionManager.getEntries().some((entry) => entry.type === "message" && entry.message === retainedFailed),
		).toBe(true);
		expect(
			h.sessionManager
				.getEntries()
				.filter(
					(entry) =>
						entry.type === "message" &&
						entry.message.role === "toolResult" &&
						entry.message.toolCallId === "failed-edit",
				),
		).toHaveLength(0);
		expect(h.eventsOfType("agent_settled")).toHaveLength(1);
	});
});
