import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import {
	type Api,
	type AssistantMessage,
	type Context,
	fauxAssistantMessage,
	type Message,
	type Model,
} from "@earendil-works/pi-ai";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import { computeContextBudget, estimateContext } from "../../src/extensions/agent-team-loop/shared/context-budget.ts";
import {
	type ContextCheckpoint,
	completeContextGroups,
	contextPrefixHash,
	parseContextSummary,
	projectContext,
} from "../../src/extensions/agent-team-loop/shared/context-checkpoint.ts";
import {
	ContextController,
	type ContextControllerOptions,
	contextPolicyFailureMessage,
	isContextPolicyFailure,
	MwContextPolicyError,
} from "../../src/extensions/agent-team-loop/shared/context-controller.ts";
import {
	type ResolvedContextPolicy,
	resolveContextPolicy,
} from "../../src/extensions/agent-team-loop/shared/context-policy.ts";

const model: Model<Api> = {
	id: "fixture",
	name: "Fixture",
	api: "openai-completions",
	provider: "fake",
	baseUrl: "https://invalid.invalid",
	reasoning: false,
	input: ["text"],
	contextWindow: 80000,
	maxTokens: 4096,
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
};
let root: string;
let policy: ResolvedContextPolicy;
beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-native-controller-"));
	policy = resolveContextPolicy({ controlRoot: root, homeDir: path.join(root, "home") });
	policy.maxTokens = 80000;
});
afterEach(() => fs.rmSync(root, { recursive: true, force: true }));
function controller(options: Partial<ContextControllerOptions> = {}) {
	return new ContextController({ readPolicy: () => policy, ...options });
}
function history(size = 75000): Context {
	return {
		systemPrompt: "fixed system",
		messages: [
			{ role: "user", content: "Preserve the task goal and completed work", timestamp: 0 },
			{
				...fauxAssistantMessage("historical state ".repeat(size)),
				api: model.api,
				provider: model.provider,
				model: model.id,
			},
		],
	};
}

describe("MW native compaction admission", () => {
	it.each([-1, 0])("plans native compaction at the exact trigger boundary offset=%s", async (offset) => {
		const threshold = computeContextBudget(model, policy).triggerTokens;
		const instance = controller({
			estimateOptions: (_model, context) =>
				context.messages.length > 1 ? { serializedPayload: "x".repeat((threshold + offset - 1024) * 3) } : {},
		});
		const context = history(1);
		const plan = await instance.planNativeCompaction(model, context);
		if (offset < 0) expect(plan).toBeUndefined();
		else expect(plan).toMatchObject({ beforeTokens: threshold, budget: { triggerTokens: threshold } });
		expect(context.messages).toHaveLength(2);
	});
	it("provider admission never creates a summary/checkpoint or transforms raw messages", async () => {
		const context = history(2000);
		const snapshot = structuredClone(context);
		expect(await controller().prepare(model, context)).toBe(context);
		expect(context).toEqual(snapshot);
	});
	it("disabled accepts within B and rejects B+1 without scheduling native generation", async () => {
		policy.compaction.enabled = false;
		const context = history(1),
			budget = computeContextBudget(model, policy);
		const at = controller({
			estimateOptions: (_m, c) =>
				c.messages.length > 1 ? { serializedPayload: "x".repeat((budget.inputBudget - 1024) * 3) } : {},
		});
		expect(await at.planNativeCompaction(model, context)).toBeUndefined();
		expect(await at.prepare(model, context)).toBe(context);
		const over = controller({
			estimateOptions: (_m, c) =>
				c.messages.length > 1 ? { serializedPayload: "x".repeat((budget.inputBudget + 1 - 1024) * 3) } : {},
		});
		await expect(over.planNativeCompaction(model, context)).rejects.toMatchObject({
			details: { code: "AUTOCOMPACTION_DISABLED" },
		});
		await expect(over.prepare(model, context, {}, { budgetOnly: true })).rejects.toMatchObject({
			details: { code: "CURRENT_POLICY_BUDGET" },
		});
	});
	it("does not hide invalid policy or fixed context overflow behind compaction", async () => {
		await expect(
			controller({
				readPolicy: () => {
					throw new Error("unreadable secret");
				},
			}).prepare(model, history(1)),
		).rejects.toMatchObject({ details: { code: "INVALID_POLICY" } });
		const context: Context = {
			systemPrompt: "x".repeat(200000),
			messages: [{ role: "user", content: "goal", timestamp: 0 }],
		};
		await expect(controller().planNativeCompaction(model, context)).rejects.toMatchObject({
			details: { code: "FIXED_CONTEXT_BUDGET" },
		});
	});
	it("rejects incomplete tool batches before requesting native compaction", async () => {
		const context: Context = {
			messages: [
				{ ...fauxAssistantMessage(""), content: [{ type: "toolCall", id: "a", name: "work", arguments: {} }] },
			],
		};
		await expect(controller().planNativeCompaction(model, context)).rejects.toMatchObject({
			details: { code: "INCOMPLETE_TOOL_BATCH" },
		});
		await expect(controller().prepare(model, context)).rejects.toMatchObject({
			details: { code: "INCOMPLETE_TOOL_BATCH" },
		});
	});
	it("native generation bypasses MW triggers but is still hard-budget checked", async () => {
		policy.compaction.enabled = false;
		const small = history(10);
		expect(await controller().prepare(model, small, {}, { nativeSummary: true })).toBe(small);
		await expect(
			controller().prepare(model, small, {}, { nativeSummary: true, automaticNativeSummary: true }),
		).rejects.toMatchObject({ details: { code: "AUTOCOMPACTION_DISABLED" } });
		await expect(controller().prepare(model, history(), {}, { nativeSummary: true })).rejects.toMatchObject({
			details: { code: "NATIVE_SUMMARY_BUDGET" },
		});
	});
	it("estimator failures stay typed and cannot expose arbitrary payload text", async () => {
		await expect(
			controller({
				estimateOptions: () => {
					throw new Error("PRIVATE-PAYLOAD");
				},
			}).prepare(model, history(1)),
		).rejects.toMatchObject({ details: { code: "PREPARATION_FAILED" } });
	});
	it("rejects native no-progress once instead of requesting another summary", async () => {
		const instance = controller(),
			context = history(9000);
		const plan = await instance.planNativeCompaction(model, context);
		if (!plan) throw new Error("fixture must reach trigger");
		await expect(instance.assertNativeProgress(model, context, plan)).rejects.toMatchObject({
			details: { code: "SUMMARY_NO_PROGRESS" },
		});
		await expect(instance.assertNativeProgress(model, history(20), plan)).resolves.toBeUndefined();
	});
	it("rechecks current model and policy after native context rebuilding", async () => {
		const instance = controller(),
			plan = await instance.planNativeCompaction(model, history(9000));
		if (!plan) throw new Error("fixture must reach trigger");
		policy = { ...policy, maxTokens: 21000 };
		await expect(instance.assertNativeProgress(model, history(1000), plan)).rejects.toMatchObject({
			details: { code: "CURRENT_POLICY_BUDGET", configured: 21000 },
		});
	});
	it("preserves the parent's exact cancellation before and after planning", async () => {
		const parent = new AbortController(),
			reason = new Error("parent canceled");
		parent.abort(reason);
		await expect(controller().prepare(model, history(1), { signal: parent.signal })).rejects.toBe(reason);
		await expect(controller().planNativeCompaction(model, history(1), { signal: parent.signal })).rejects.toBe(
			reason,
		);
	});
	it("resets provider-specific calibration after native compaction", async () => {
		const context = history(50),
			instance = controller();
		const usage = { ...fauxAssistantMessage("").usage, input: 100000 };
		instance.observeUsage(model, context, {}, usage);
		await expect(instance.prepare(model, context)).rejects.toBeInstanceOf(MwContextPolicyError);
		instance.resetCalibration();
		expect(await instance.prepare(model, context)).toBe(context);
		expect(estimateContext(context).estimatedTokens).toBeLessThan(computeContextBudget(model, policy).inputBudget);
	});
	it("safe native errors never persist the upstream text and cannot trigger outer retry", () => {
		const error = controller().nativeFailure(
			model,
			new Error("HTTP 429 insufficient_quota Bearer sk-secret https://private?key=secret"),
		);
		const message = contextPolicyFailureMessage(model, error);
		expect(isContextPolicyFailure(message)).toBe(true);
		expect(error.details.summaryFailure).toEqual({
			category: "quota",
			httpStatus: 429,
			errorType: "insufficient_quota",
		});
		expect(JSON.stringify(message)).not.toMatch(/sk-secret|Bearer|https/);
		expect(message.diagnostics).toContainEqual(
			expect.objectContaining({ type: "provider_retry_boundary", details: { outerRetryEligible: false } }),
		);
	});
});

describe("historical MW checkpoint parsing remains inert", () => {
	it("groups reversed completed parallel batches and rejects orphan results", () => {
		const call: AssistantMessage = {
			...fauxAssistantMessage(""),
			content: [
				{ type: "toolCall", id: "a", name: "work", arguments: {} },
				{ type: "toolCall", id: "b", name: "work", arguments: {} },
			],
		};
		const result = (id: string): Message => ({
			role: "toolResult",
			toolCallId: id,
			toolName: "work",
			content: [{ type: "text", text: id }],
			isError: false,
			timestamp: 0,
		});
		expect(completeContextGroups([call, result("b"), result("a")])).toEqual([{ start: 0, end: 3 }]);
		expect(() => completeContextGroups([result("a")])).toThrow("ORPHAN_TOOL_RESULT");
	});
	it("can read a previously persisted checkpoint without generating new ones", () => {
		const context = history(2);
		const summary = {
			goal: "goal",
			constraints: "none",
			decisions: "none",
			changes: "done",
			verification: "done",
			remaining: "continue",
		};
		expect(parseContextSummary(summary)).toEqual(summary);
		expect(parseContextSummary({ ...summary, goal: " " })).toBeUndefined();
		const checkpoint: ContextCheckpoint = {
			schemaVersion: 1,
			checkpointId: "historical",
			coveredMessages: 2,
			prefixSha256: contextPrefixHash(context.messages, 2),
			summary,
			provider: model.provider,
			model: model.id,
			beforeTokens: 1000,
			afterTokens: 100,
		};
		expect(projectContext(context, checkpoint).messages[0]).toBe(context.messages[0]);
		expect(context.messages).toHaveLength(2);
	});
});
