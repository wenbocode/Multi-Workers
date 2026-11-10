import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { AssistantMessage, Context, ImageContent, Usage } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
	ContextBudgetError,
	ContextCalibration,
	computeContextBudget,
	estimateContext,
	estimateTextTokens,
} from "../../src/extensions/agent-team-loop/shared/context-budget.ts";
import { resolveContextPolicy } from "../../src/extensions/agent-team-loop/shared/context-policy.ts";

let root: string;
beforeEach(() => {
	root = fs.mkdtempSync(path.join(os.tmpdir(), "mw-context-budget-"));
});
afterEach(() => {
	fs.rmSync(root, { recursive: true, force: true });
});

const zeroUsage: Usage = {
	input: 0,
	output: 0,
	cacheRead: 0,
	cacheWrite: 0,
	totalTokens: 0,
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
};

describe("context budget math", () => {
	it.each([
		[1000000, 32768, undefined, 512000, 32768, 10240, 468992, 375193, 234496],
		[128000, 65536, undefined, 128000, 65536, 4096, 58368, 46694, 29184],
		[512000, 4096, undefined, 512000, 16384, 10240, 485376, 388300, 242688],
		[512000, 65536, 40000, 512000, 40000, 10240, 461760, 369408, 230880],
		[512000, 65536, 4096, 512000, 16384, 10240, 485376, 388300, 242688],
	])(
		"reserves declared output and caps model=%i output=%i override=%j",
		(
			contextWindow,
			maxTokens,
			output,
			effectiveWindow,
			outputReserve,
			safetyMargin,
			inputBudget,
			triggerTokens,
			targetTokens,
		) => {
			const model = Object.freeze({ contextWindow, maxTokens });
			const original = JSON.stringify(model);
			const policy = resolveContextPolicy({ controlRoot: root, homeDir: root });
			expect(computeContextBudget(model, policy, output)).toEqual({
				modelWindow: contextWindow,
				configuredMaxTokens: 512000,
				effectiveWindow,
				outputReserve,
				safetyMargin,
				inputBudget,
				triggerTokens,
				targetTokens,
			});
			expect(JSON.stringify(model)).toBe(original);
			expect(fs.readdirSync(root)).toEqual([]);
		},
	);

	it("allows fixed anchors at B and refuses B+1 without reducing output", () => {
		const policy = resolveContextPolicy({ controlRoot: root, homeDir: root });
		const model = Object.freeze({ contextWindow: 128000, maxTokens: 16384 });
		expect(computeContextBudget(model, policy, undefined, 107520).inputBudget).toBe(107520);
		expect(() => computeContextBudget(model, policy, undefined, 107521)).toThrow("MW_CONTEXT_BUDGET_IMPOSSIBLE");
		expect(model.maxTokens).toBe(16384);
	});

	it.each([0, -1, Number.NaN, Number.POSITIVE_INFINITY, 1.2, Number.MAX_SAFE_INTEGER + 1])(
		"rejects invalid model windows and explicit output budgets %j",
		(invalid) => {
			const policy = resolveContextPolicy({ controlRoot: root, homeDir: root });
			expect(() => computeContextBudget({ contextWindow: invalid, maxTokens: 16384 }, policy)).toThrow(
				ContextBudgetError,
			);
			expect(() => computeContextBudget({ contextWindow: 128000, maxTokens: 16384 }, policy, invalid)).toThrow(
				ContextBudgetError,
			);
		},
	);

	it("rejects output reserve larger than E and preserves explanatory numbers", () => {
		const policy = resolveContextPolicy({ controlRoot: root, homeDir: root });
		try {
			computeContextBudget({ contextWindow: 20000, maxTokens: 32768 }, policy);
			throw new Error("expected rejection");
		} catch (error) {
			expect(error).toBeInstanceOf(ContextBudgetError);
			expect((error as ContextBudgetError).details).toMatchObject({
				effectiveWindow: 20000,
				outputReserve: 32768,
				safetyMargin: 4096,
				inputBudget: -16864,
			});
		}
	});
});

describe("observable request estimate", () => {
	it("uses UTF8 bytes/3 including Chinese and counts protocol overhead even with empty history", () => {
		expect(estimateTextTokens("abc")).toBe(1);
		expect(estimateTextTokens("中文")).toBe(2);
		expect(estimateTextTokens("😀")).toBe(2);
		const base = estimateContext({ messages: [] });
		expect(base.baseTokens).toBe(1029);
		expect(base.estimatedTokens).toBe(base.baseTokens);
		expect(base.calibrationFactor).toBe(1);
		const chinese = estimateContext({ messages: [{ role: "user", timestamp: 1, content: "中".repeat(300) }] });
		const ascii = estimateContext({ messages: [{ role: "user", timestamp: 1, content: "a".repeat(300) }] });
		expect(chinese.baseTokens - ascii.baseTokens).toBe(200);
	});

	it("includes system, tools, tool arguments/results and thinking without response bookkeeping", () => {
		const assistant: AssistantMessage = {
			role: "assistant",
			api: "openai-completions",
			provider: "fake",
			model: "fake",
			timestamp: 1,
			usage: zeroUsage,
			stopReason: "toolUse",
			content: [
				{ type: "thinking", thinking: "think".repeat(1000), thinkingSignature: "signed" },
				{ type: "toolCall", id: "call-1", name: "read", arguments: { path: "file".repeat(1000) } },
			],
		};
		const context: Context = {
			systemPrompt: "system".repeat(1000),
			tools: [
				{ name: "read", description: "description".repeat(1000), parameters: Type.Object({ path: Type.String() }) },
			],
			messages: [
				{ role: "user", content: "task", timestamp: 1 },
				assistant,
				{
					role: "toolResult",
					toolCallId: "call-1",
					toolName: "read",
					isError: false,
					timestamp: 2,
					content: [{ type: "text", text: "result".repeat(1000) }],
					details: { notSent: "private".repeat(1000) },
				},
			],
		};
		const full = estimateContext(context);
		expect(full.baseTokens).toBeGreaterThan(10000);
		for (const reduced of [
			{ ...context, systemPrompt: "" },
			{ ...context, tools: [] },
			{ ...context, messages: context.messages.slice(0, 2) },
			{ ...context, messages: [context.messages[0], { ...assistant, content: [] }, context.messages[2]] },
		])
			expect(estimateContext(reduced).baseTokens).toBeLessThan(full.baseTokens);
		assistant.usage = { ...zeroUsage, input: 9999999, output: 8888888 };
		assistant.timestamp = 99999999;
		expect(estimateContext(context).baseTokens).toBe(full.baseTokens);
	});

	it("uses known image dimensions and fallback4096 without charging base64 as text", () => {
		const header = Buffer.alloc(24);
		header.writeUInt32BE(0x89504e47, 0);
		header.writeUInt32BE(1024, 16);
		header.writeUInt32BE(1024, 20);
		const known: ImageContent = { type: "image", mimeType: "image/png", data: header.toString("base64") };
		const imageContext = (image: ImageContent): Context => ({
			messages: [{ role: "user", timestamp: 1, content: [image] }],
		});
		const estimate = estimateContext(imageContext(known));
		expect(estimate.imageTokens).toBe(1399);
		expect(estimate.imageFallbackCount).toBe(0);
		const small = estimateContext(imageContext({ type: "image", mimeType: "image/unknown", data: "a".repeat(100) }));
		const huge = estimateContext(
			imageContext({ type: "image", mimeType: "image/unknown", data: "a".repeat(1000000) }),
		);
		expect(huge.imageTokens).toBe(4096);
		expect(huge.imageFallbackCount).toBe(1);
		expect(huge.baseTokens).toBe(small.baseTokens);
	});

	it("counts complete local wire wrapping, CLI reserve and calibration together", () => {
		const context: Context = {
			systemPrompt: "ignored duplicate",
			messages: [{ role: "user", timestamp: 1, content: "task" }],
		};
		const payload = JSON.stringify({ wrapper: "x".repeat(3000), request: { task: "任务" } });
		const estimate = estimateContext(context, {
			serializedPayload: payload,
			additionalTokens: 16384,
			wrapperKey: "local-codex-json-v1",
			calibrationFactor: 1.5,
		});
		expect(estimate.textBytes).toBe(Buffer.byteLength(payload, "utf8"));
		expect(estimate.baseTokens).toBe(estimateTextTokens(payload) + 1024 + 16384);
		expect(estimate.estimatedTokens).toBe(Math.ceil(estimate.baseTokens * 1.5));
		expect(estimate.wrapperKey).toBe("local-codex-json-v1");
		expect(estimate.baseTokens).toBeGreaterThan(estimateContext(context).baseTokens + 16384);
	});

	it("removes image transport bytes from serialized wrapping while retaining image estimate", () => {
		const image: ImageContent = { type: "image", mimeType: "image/unknown", data: "a".repeat(100000) };
		const context: Context = { messages: [{ role: "user", timestamp: 1, content: [image] }] };
		const estimate = estimateContext(context, { serializedPayload: JSON.stringify({ wrapped: context }) });
		expect(estimate.textBytes).toBeLessThan(200);
		expect(estimate.imageTokens).toBe(4096);
	});

	it("refuses nonserializable tool input instead of treating it as zero", () => {
		const cyclic: Record<string, unknown> = {};
		cyclic.self = cyclic;
		const parameters = Type.Object({});
		Object.assign(parameters, { cyclic });
		const context: Context = {
			messages: [],
			tools: [{ name: "bad", description: "bad", parameters }],
		};
		expect(() => estimateContext(context)).toThrow("MW_CONTEXT_ESTIMATE_INVALID");
	});
});

describe("context input calibration", () => {
	it("includes cache reads/writes, excludes output and never decreases", () => {
		const calibration = new ContextCalibration();
		expect(calibration.getFactor("p", "m", "w")).toBe(1);
		expect(
			calibration.observe("p", "m", "w", 100, { input: 50, cacheRead: 100, cacheWrite: 150, output: 10000 }),
		).toBe(3);
		expect(calibration.observe("p", "m", "w", 100, { input: 100, cacheRead: 0, cacheWrite: 0, output: 10000 })).toBe(
			3,
		);
		expect(
			estimateContext({ messages: [] }, { calibrationFactor: calibration.getFactor("p", "m", "w") }).estimatedTokens,
		).toBe(3087);
	});

	it("isolates provider/model/wrapping and resets after native compact", () => {
		const calibration = new ContextCalibration();
		calibration.observe("p", "m", "w", 100, { input: 400, cacheRead: 0, cacheWrite: 0, output: 0 });
		for (const [provider, model, wrapper] of [
			["other", "m", "w"],
			["p", "small", "w"],
			["p", "m", "new-wrapper"],
		])
			expect(calibration.getFactor(provider, model, wrapper)).toBe(1);
		calibration.reset();
		expect(calibration.getFactor("p", "m", "w")).toBe(1);
	});

	it.each([
		{ input: 0, cacheRead: 0, cacheWrite: 0, output: 0 },
		{ input: -1, cacheRead: 100, cacheWrite: 0, output: 0 },
		{ input: Number.NaN, cacheRead: 100, cacheWrite: 0, output: 0 },
		{ input: 100, cacheRead: 100, cacheWrite: 0.1, output: 0 },
	])("does not calibrate from zero or malformed usage %j", (usage) => {
		const calibration = new ContextCalibration();
		expect(calibration.observe("p", "m", "w", 100, usage)).toBe(1);
	});
});
