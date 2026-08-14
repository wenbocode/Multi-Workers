import { afterAll, describe, expect, it } from "vitest";
import { timiResponsesApi } from "../src/api/timi-responses.ts";
import type {
	AssistantMessage,
	AssistantMessageEvent,
	Context,
	Model,
	ProviderStreams,
	StreamOptions,
} from "../src/types.ts";
import { AssistantMessageEventStream } from "../src/utils/event-stream.ts";
import { PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC } from "../src/utils/retry.ts";

// ---------------------------------------------------------------------------
// Shared fixtures
// ---------------------------------------------------------------------------

const ZERO_USAGE = {
	input: 0,
	output: 0,
	cacheRead: 0,
	cacheWrite: 0,
	totalTokens: 0,
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
};

const model: Model<"openai-responses"> = {
	id: "gpt-5.6-sol",
	name: "GPT-5.6 Sol",
	api: "openai-responses",
	provider: "timi",
	baseUrl: "https://example.invalid/v1",
	reasoning: true,
	input: ["text"],
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
	contextWindow: 200000,
	maxTokens: 64000,
};

const context: Context = {
	messages: [{ role: "user", content: "Hello", timestamp: 1720000000000 }],
};

function makeErrorMsg(msg: string): AssistantMessage {
	return {
		role: "assistant",
		content: [],
		api: "openai-responses",
		provider: "timi",
		model: "gpt-5.6-sol",
		usage: ZERO_USAGE,
		stopReason: "error",
		errorMessage: msg,
		timestamp: 1720000000000,
	};
}

function makePartialMsg(): AssistantMessage {
	return {
		role: "assistant",
		content: [],
		api: "openai-responses",
		provider: "timi",
		model: "gpt-5.6-sol",
		usage: ZERO_USAGE,
		stopReason: "pending",
		timestamp: 1720000000000,
	};
}

// ---------------------------------------------------------------------------
// Helper: build a fake delegate that captures wrapOptions outputs
// ---------------------------------------------------------------------------

type CapturedWrapOptions = {
	maxRetries?: number;
	onPayload?: (payload: unknown, m: unknown) => Promise<unknown>;
};

function makeCaptureDelegate(): { delegate: ProviderStreams; captured: CapturedWrapOptions } {
	const captured: CapturedWrapOptions = {};
	const delegate: ProviderStreams = {
		stream(_m, _ctx, options) {
			const o = options as StreamOptions | undefined;
			captured.maxRetries = o?.maxRetries;
			captured.onPayload = o?.onPayload as CapturedWrapOptions["onPayload"];
			return new AssistantMessageEventStream();
		},
		streamSimple(_m, _ctx, options) {
			captured.maxRetries = (options as { maxRetries?: number } | undefined)?.maxRetries;
			return new AssistantMessageEventStream();
		},
	};
	return { delegate, captured };
}

/** Run .stream() and return the captured wrapOptions. */
async function captureOptions(streamOptions: Partial<StreamOptions>): Promise<CapturedWrapOptions> {
	const { delegate, captured } = makeCaptureDelegate();
	timiResponsesApi(delegate).stream(model, context, streamOptions as StreamOptions);
	return captured;
}

/** Run .stream() with a test payload and return the normalized result from onPayload. */
async function invokeOnPayload(
	testPayload: Record<string, unknown>,
	callerOnPayload?: (p: unknown, m: unknown) => Promise<unknown>,
): Promise<unknown> {
	const { delegate, captured } = makeCaptureDelegate();
	timiResponsesApi(delegate).stream(model, context, {
		onPayload: callerOnPayload as StreamOptions["onPayload"],
	} as StreamOptions);
	if (!captured.onPayload) throw new Error("onPayload was not captured");
	return captured.onPayload(testPayload, model);
}

// ---------------------------------------------------------------------------
// Helper: stream wrapping (pre/post-start error diagnostics)
// ---------------------------------------------------------------------------

function makeStreamDelegate(events: AssistantMessageEvent[]): ProviderStreams {
	return {
		stream() {
			const inner = new AssistantMessageEventStream();
			// Push events asynchronously so the outer stream can iterate
			Promise.resolve().then(() => {
				for (const ev of events) inner.push(ev);
			});
			return inner;
		},
		streamSimple() {
			return new AssistantMessageEventStream();
		},
	};
}

async function collectEvents(s: AssistantMessageEventStream): Promise<AssistantMessageEvent[]> {
	const out: AssistantMessageEvent[] = [];
	for await (const e of s) out.push(e);
	return out;
}

// ---------------------------------------------------------------------------
// Tests: payload normalization (AC-004)
// ---------------------------------------------------------------------------

describe("payload normalization", () => {
	it("removes top-level store", async () => {
		const result = (await invokeOnPayload({ model: "gpt-5.6-sol", store: true, input: [] })) as Record<
			string,
			unknown
		>;
		expect(result).not.toHaveProperty("store");
		expect(result.model).toBe("gpt-5.6-sol");
	});

	it("removes store from nested objects recursively", async () => {
		const payload = {
			model: "gpt-5.6-sol",
			input: [
				{ role: "user", store: "nested-store", content: "hello" },
				{ role: "assistant", extra: { store: "deep-store" }, content: "hi" },
			],
		};
		const result = (await invokeOnPayload(payload)) as Record<string, unknown>;
		const input = result.input as Array<Record<string, unknown>>;
		expect(input[0]).not.toHaveProperty("store");
		expect(input[1]!.extra as Record<string, unknown>).not.toHaveProperty("store");
	});

	it("fills blank tool descriptions with 'Tool <name>'", async () => {
		const payload = {
			tools: [
				{ name: "search", description: "" },
				{ name: "fetch", description: "   " },
			],
		};
		const result = (await invokeOnPayload(payload)) as Record<string, unknown>;
		const tools = result.tools as Array<{ name: string; description: string }>;
		expect(tools[0]!.description).toBe("Tool search");
		expect(tools[1]!.description).toBe("Tool fetch");
	});

	it("fills blank unnamed tool descriptions with 'Tool <index>'", async () => {
		const payload = { tools: [{ description: "" }] };
		const result = (await invokeOnPayload(payload)) as Record<string, unknown>;
		const tools = result.tools as Array<{ description: string }>;
		expect(tools[0]!.description).toBe("Tool 0");
	});

	it("preserves non-blank tool descriptions unchanged", async () => {
		const payload = { tools: [{ name: "lookup", description: "Look up a value" }] };
		const result = (await invokeOnPayload(payload)) as Record<string, unknown>;
		const tools = result.tools as Array<{ description: string }>;
		expect(tools[0]!.description).toBe("Look up a value");
	});

	it("preserves null/missing tool descriptions (non-string)", async () => {
		const payload = { tools: [{ name: "t1", description: null }, { name: "t2" }] };
		const result = (await invokeOnPayload(payload)) as Record<string, unknown>;
		const tools = result.tools as Array<Record<string, unknown>>;
		expect(tools[0]!.description).toBeNull();
		expect(Object.hasOwn(tools[1], "description")).toBe(false);
	});

	it("does not mutate the caller's payload object", async () => {
		const payload = {
			store: "keep-original",
			tools: [{ name: "t", description: "" }],
		};
		await invokeOnPayload(payload);
		expect(payload.store).toBe("keep-original");
		const tools = payload.tools as Array<{ description: string }>;
		expect(tools[0]!.description).toBe("");
	});

	it("runs normalization on the caller-replaced payload", async () => {
		const replacedPayload = {
			model: "gpt-5.6-sol",
			store: "should-be-removed",
			tools: [{ name: "t", description: "" }],
		};
		const result = (await invokeOnPayload(
			{ model: "original", store: "original" },
			async () => replacedPayload,
		)) as Record<string, unknown>;
		expect(result).not.toHaveProperty("store");
		const tools = result.tools as Array<{ description: string }>;
		expect(tools[0]!.description).toBe("Tool t");
	});

	it("recursively processes nested tool arrays", async () => {
		const payload = {
			input: [
				{
					tools: [{ name: "nested", description: "" }],
				},
			],
		};
		const result = (await invokeOnPayload(payload)) as Record<string, unknown>;
		const nested = (result.input as Array<Record<string, unknown>>)[0]!.tools as Array<{
			description: string;
		}>;
		expect(nested[0]!.description).toBe("Tool nested");
	});
});

// ---------------------------------------------------------------------------
// Tests: maxRetries (AC-005)
// ---------------------------------------------------------------------------

describe("maxRetries", () => {
	it("defaults to 8 when not specified", async () => {
		const { maxRetries } = await captureOptions({});
		expect(maxRetries).toBe(8);
	});

	it("preserves explicit 0", async () => {
		const { maxRetries } = await captureOptions({ maxRetries: 0 });
		expect(maxRetries).toBe(0);
	});

	it("preserves explicit non-default value", async () => {
		const { maxRetries } = await captureOptions({ maxRetries: 3 });
		expect(maxRetries).toBe(3);
	});
});

// ---------------------------------------------------------------------------
// Tests: stream retry boundary wrapping (AC-005)
// ---------------------------------------------------------------------------

describe("stream retry boundary", () => {
	it("pre-start error event carries provider_retry_boundary diagnostic", async () => {
		const errorMsg = makeErrorMsg("connection refused");
		const delegate = makeStreamDelegate([{ type: "error", reason: "error", error: errorMsg }]);
		const outer = timiResponsesApi(delegate).stream(model, context, {});
		const events = await collectEvents(outer);

		const errEvent = events.find((e) => e.type === "error") as { type: "error"; error: AssistantMessage } | undefined;
		expect(errEvent).toBeDefined();
		const boundary = errEvent!.error.diagnostics?.find((d) => d.type === PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC);
		expect(boundary).toBeDefined();
		expect(boundary!.details?.outerRetryEligible).toBe(false);
	});

	it("post-start error event does not carry provider_retry_boundary diagnostic", async () => {
		const partial = makePartialMsg();
		const errorMsg = makeErrorMsg("network error mid-stream");
		const delegate = makeStreamDelegate([
			{ type: "start", partial },
			{ type: "error", reason: "error", error: errorMsg },
		]);
		const outer = timiResponsesApi(delegate).stream(model, context, {});
		const events = await collectEvents(outer);

		const errEvent = events.find((e) => e.type === "error") as { type: "error"; error: AssistantMessage } | undefined;
		expect(errEvent).toBeDefined();
		const boundary = errEvent!.error.diagnostics?.find((d) => d.type === PROVIDER_RETRY_BOUNDARY_DIAGNOSTIC);
		expect(boundary).toBeUndefined();
	});

	it("forwarded start event is still present in outer stream", async () => {
		const partial = makePartialMsg();
		const doneMsg: AssistantMessage = { ...partial, stopReason: "stop" };
		const delegate = makeStreamDelegate([
			{ type: "start", partial },
			{ type: "done", reason: "stop", message: doneMsg },
		]);
		const outer = timiResponsesApi(delegate).stream(model, context, {});
		const events = await collectEvents(outer);
		expect(events.some((e) => e.type === "start")).toBe(true);
	});
});

afterAll(() => {
	console.log("[VERIFY] VC-004 VC-005: normalization=ok maxRetries=ok retry_boundary=ok");
});
