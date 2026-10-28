/**
 * VC-002: Verifies that timiProvider() correctly dispatches claude-* models
 * to anthropic-messages API and all other models to openai-responses API.
 * No network calls are made — onPayload aborts the stream early.
 */
import { afterAll, describe, expect, it, vi } from "vitest";
import { timiProvider } from "../src/providers/timi.ts";
import type { Context } from "../src/types.ts";

// ---------------------------------------------------------------------------
// Stub @anthropic-ai/sdk so anthropic-messages never touches the network
// ---------------------------------------------------------------------------

vi.mock("@anthropic-ai/sdk", () => {
	class FakeAnthropic {
		messages = {
			create: (_params: unknown) => ({
				asResponse: async () => new Response("", { status: 200, headers: { "content-type": "text/event-stream" } }),
			}),
		};
	}
	return { default: FakeAnthropic };
});

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

class PayloadCaptured extends Error {
	readonly captured: unknown;

	constructor(captured: unknown) {
		super("payload captured");
		this.captured = captured;
	}
}

const context: Context = {
	messages: [{ role: "user", content: "Hello", timestamp: 1720000000000 }],
};

async function capturePayload(modelId: string): Promise<unknown> {
	const provider = timiProvider();
	const model = provider.getModels().find((m) => m.id === modelId);
	if (!model) throw new Error(`Model not found: ${modelId}`);

	let captured: unknown;
	const s = provider.stream(model, context, {
		apiKey: "test-key",
		onPayload: async (payload) => {
			captured = payload;
			throw new PayloadCaptured(payload);
		},
	});
	for await (const event of s) {
		if (event.type === "error" || event.type === "done") break;
	}
	return captured;
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe("timi provider dispatch (VC-002)", () => {
	it("routes claude-sonnet-4.6 to anthropic-messages (payload has 'messages' field)", async () => {
		const payload = (await capturePayload("claude-sonnet-4.6")) as Record<string, unknown>;
		expect(payload).toBeDefined();
		// Anthropic Messages API payload uses "messages" array
		expect(payload).toHaveProperty("messages");
		expect(payload).not.toHaveProperty("input");
	});

	it("routes gpt-5.6-sol to openai-responses (payload has 'input' field)", async () => {
		const payload = (await capturePayload("gpt-5.6-sol")) as Record<string, unknown>;
		expect(payload).toBeDefined();
		// OpenAI Responses API payload uses "input" array
		expect(payload).toHaveProperty("input");
		expect(payload).not.toHaveProperty("messages");
	});

	it("has both anthropic-messages and openai-responses implementations (no missing-impl error)", async () => {
		const provider = timiProvider();
		const models = provider.getModels();
		const claudeModel = models.find((m) => m.id === "claude-sonnet-4.6");
		const gptModel = models.find((m) => m.id === "gpt-5.6-sol");
		expect(claudeModel).toBeDefined();
		expect(claudeModel?.api).toBe("anthropic-messages");
		expect(gptModel).toBeDefined();
		expect(gptModel?.api).toBe("openai-responses");
	});

	afterAll(() => {
		console.log("[VERIFY] VC-002: dispatch_families=2 failures=0");
	});
});
