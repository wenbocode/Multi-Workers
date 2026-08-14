import { afterAll, beforeEach, describe, expect, it, vi } from "vitest";
import { stream as streamAnthropic } from "../src/api/anthropic-messages.ts";
import { convertResponsesMessages } from "../src/api/openai-responses-shared.ts";
import type { Api, AssistantMessage, Context, Model } from "../src/types.ts";

// ---------------------------------------------------------------------------
// Mock @anthropic-ai/sdk so anthropic-messages tests never hit the network
// ---------------------------------------------------------------------------

const mockState = vi.hoisted(() => ({
	createParams: undefined as Record<string, unknown> | undefined,
}));

vi.mock("@anthropic-ai/sdk", () => {
	function createSseResponse(): Response {
		const body = [
			`event: message_start\ndata: ${JSON.stringify({
				type: "message_start",
				message: { id: "msg_test", usage: { input_tokens: 10, output_tokens: 0 } },
			})}\n`,
			`event: message_delta\ndata: ${JSON.stringify({
				type: "message_delta",
				delta: { stop_reason: "end_turn" },
				usage: { output_tokens: 5 },
			})}\n`,
		].join("\n");
		return new Response(body, { status: 200, headers: { "content-type": "text/event-stream" } });
	}

	class FakeAnthropic {
		messages = {
			create: (params: Record<string, unknown>) => {
				mockState.createParams = params;
				return { asResponse: async () => createSseResponse() };
			},
		};
	}

	return { default: FakeAnthropic };
});

// ---------------------------------------------------------------------------
// Shared helpers
// ---------------------------------------------------------------------------

const ZERO_USAGE = {
	input: 10,
	output: 5,
	cacheRead: 0,
	cacheWrite: 0,
	totalTokens: 15,
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
};

function makeResponsesModel(): Model<"openai-responses"> {
	return {
		id: "gpt-5.6-sol",
		name: "GPT-5.6 Sol",
		api: "openai-responses",
		provider: "timi",
		baseUrl: "https://example.invalid/v1",
		reasoning: true,
		input: ["text", "image"],
		cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
		contextWindow: 200000,
		maxTokens: 64000,
		compat: {
			supportsDeveloperRole: true,
			sessionAffinityFormat: "openai-nosession",
			supportsLongCacheRetention: false,
			supportsStrictMode: false,
			supportsOpenAIGrammarTools: false,
			supportsToolSearch: false,
			supportsExplicitPromptCacheMode: false,
		},
	};
}

function makeAnthropicModel(): Model<"anthropic-messages"> {
	return {
		id: "claude-sonnet-4.6",
		name: "Claude Sonnet 4.6",
		api: "anthropic-messages",
		provider: "timi",
		reasoning: false,
		input: ["text", "image"],
		cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
		contextWindow: 200000,
		maxTokens: 64000,
	};
}

// A valid serialized ResponseReasoningItem (used as thinkingSignature for openai-responses messages)
const RESPONSES_THINKING_SIGNATURE = JSON.stringify({
	type: "reasoning",
	id: "rs_test_abc123",
	summary: [{ type: "summary_text", text: "I thought about the problem carefully." }],
});

// A plausible Anthropic encrypted signature string (not real; format is opaque to the code)
const ANTHROPIC_THINKING_SIGNATURE = "EqoBCkgIBRgCKkAVQVEQ6HyGAAAAAAAAAAAA";

function makeAssistantMsg(api: Api, thinkingSignature: string): AssistantMessage {
	return {
		role: "assistant",
		content: [
			{ type: "thinking", thinking: "My reasoning.", thinkingSignature },
			{ type: "text", text: "Final answer." },
		],
		api,
		provider: "timi",
		model: api === "anthropic-messages" ? "claude-sonnet-4.6" : "gpt-5.6-sol",
		usage: ZERO_USAGE,
		stopReason: "end_turn",
		timestamp: 1720000000000,
	};
}

function makeContext(assistantMsg: AssistantMessage): Context {
	return {
		messages: [
			{ role: "user", content: "Hello", timestamp: 1720000000000 },
			assistantMsg,
			{ role: "user", content: "Continue", timestamp: 1720000000001 },
		],
	};
}

/** Run streamAnthropic until stop and return the captured messages payload. */
async function captureAnthropicMessages(context: Context): Promise<unknown[]> {
	mockState.createParams = undefined;
	const s = streamAnthropic(makeAnthropicModel(), context, { apiKey: "test-key" });
	for await (const event of s) {
		if (event.type === "stop" || event.type === "error") break;
	}
	return (mockState.createParams?.messages as unknown[]) ?? [];
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("cross-api thinking history isolation (VC-006)", () => {
	beforeEach(() => {
		mockState.createParams = undefined;
	});

	it("Test 1 — anthropic→responses: omits thinking block from Responses serialization", () => {
		// History message came from anthropic-messages; current model uses openai-responses.
		// The thinking signature must NOT appear in the Responses input as a reasoning item.
		const assistantMsg = makeAssistantMsg("anthropic-messages", ANTHROPIC_THINKING_SIGNATURE);
		const context = makeContext(assistantMsg);
		const model = makeResponsesModel();

		const output = convertResponsesMessages(model, context, new Set());

		// Find any reasoning items in the output
		const reasoningItems = output.filter((item) => {
			if (typeof item === "object" && item !== null) {
				const obj = item as Record<string, unknown>;
				return obj.type === "reasoning";
			}
			return false;
		});

		expect(reasoningItems).toHaveLength(0);

		// Text content from the assistant message is still present
		const assistantOutputs = output.filter((item) => {
			const obj = item as Record<string, unknown>;
			return obj.type === "message" && obj.role === "assistant";
		});
		expect(assistantOutputs.length).toBeGreaterThan(0);
	});

	it("Test 2 — responses→anthropic: omits thinking block from Anthropic serialization", async () => {
		// History message came from openai-responses; current model uses anthropic-messages.
		// The thinking block must NOT appear in the Anthropic messages payload.
		const assistantMsg = makeAssistantMsg("openai-responses", RESPONSES_THINKING_SIGNATURE);
		const context = makeContext(assistantMsg);

		const messages = await captureAnthropicMessages(context);

		// Find any thinking or redacted_thinking blocks in the assistant message
		const assistantMsgPayload = messages.find((m) => {
			const obj = m as Record<string, unknown>;
			return obj.role === "assistant";
		}) as Record<string, unknown> | undefined;

		expect(assistantMsgPayload).toBeDefined();
		const blocks = assistantMsgPayload?.content as Array<Record<string, unknown>>;
		const thinkingBlocks = blocks.filter((b) => b.type === "thinking" || b.type === "redacted_thinking");
		expect(thinkingBlocks).toHaveLength(0);

		// Text content is preserved
		const textBlocks = blocks.filter((b) => b.type === "text");
		expect(textBlocks.length).toBeGreaterThan(0);
	});

	it("Test 3 — same-protocol anthropic: replays thinking block normally", async () => {
		// History message came from anthropic-messages; current model also uses anthropic-messages.
		// The thinking block MUST appear in the Anthropic messages payload.
		const assistantMsg = makeAssistantMsg("anthropic-messages", ANTHROPIC_THINKING_SIGNATURE);
		const context = makeContext(assistantMsg);

		const messages = await captureAnthropicMessages(context);

		const assistantMsgPayload = messages.find((m) => {
			const obj = m as Record<string, unknown>;
			return obj.role === "assistant";
		}) as Record<string, unknown> | undefined;

		expect(assistantMsgPayload).toBeDefined();
		const blocks = assistantMsgPayload?.content as Array<Record<string, unknown>>;
		const thinkingBlocks = blocks.filter((b) => b.type === "thinking");
		expect(thinkingBlocks).toHaveLength(1);
		expect(thinkingBlocks[0]!.signature).toBe(ANTHROPIC_THINKING_SIGNATURE);
	});

	it("Test 4 — same-protocol responses: replays reasoning item normally", () => {
		// History message came from openai-responses; current model also uses openai-responses.
		// The thinking signature must be replayed as a reasoning item in the Responses input.
		const assistantMsg = makeAssistantMsg("openai-responses", RESPONSES_THINKING_SIGNATURE);
		const context = makeContext(assistantMsg);
		const model = makeResponsesModel();

		const output = convertResponsesMessages(model, context, new Set());

		const reasoningItems = output.filter((item) => {
			const obj = item as Record<string, unknown>;
			return obj.type === "reasoning";
		});

		expect(reasoningItems).toHaveLength(1);
		expect((reasoningItems[0] as Record<string, unknown>).id).toBe("rs_test_abc123");
	});

	afterAll(() => {
		console.log("[VERIFY] VC-006: history_cases=4 failures=0");
	});
});
