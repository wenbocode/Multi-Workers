import { afterEach, describe, expect, it, vi } from "vitest";
import { timiDecisionsApi } from "../src/api/timi-decisions.ts";
import { TIMI_MODELS } from "../src/providers/timi.models.ts";
import { timiProvider } from "../src/providers/timi.ts";
import type { AssistantMessage, Context, FetchFunction, Model } from "../src/types.ts";

const model: Model<"timi-decisions"> = {
	id: "jev-latest",
	name: "JEV Latest",
	api: "timi-decisions",
	provider: "timi",
	baseUrl: "https://typesafe.test/gateway",
	reasoning: false,
	input: ["text"],
	cost: { input: 1, output: 2, cacheRead: 0, cacheWrite: 0 },
	contextWindow: 200_000,
	maxTokens: 64_000,
};

const question = { billing: { type: "noul", instructions: "Is this message about billing?" } };
const requestBody = { state: "I was charged twice for my subscription.", questions: question };
const answers = { billing: { type: "noul", noul: 0.98 } };

function jsonContext(value: unknown): Context {
	return {
		messages: [{ role: "user", content: JSON.stringify(value), timestamp: 1 }],
	};
}

function mockFetch(response: () => Response) {
	return vi.fn<FetchFunction>(async () => response());
}

afterEach(() => {
	vi.unstubAllGlobals();
	vi.restoreAllMocks();
});

describe("timi-decisions api", () => {
	it("posts only {model, state, questions} to /v1/decisions and returns answers as compact JSON", async () => {
		const fetchMock = mockFetch(
			() =>
				new Response(
					JSON.stringify({ model: "jev-latest-2026", answers, usage: { input_tokens: 120, output_tokens: 12 } }),
					{ status: 200, headers: { "content-type": "application/json" } },
				),
		);
		const ambient = vi.fn<FetchFunction>(async () => {
			throw new Error("ambient fetch must not be called");
		});
		vi.stubGlobal("fetch", ambient);

		const result = await timiDecisionsApi()
			.stream(model, jsonContext(requestBody), { apiKey: "test-key", fetch: fetchMock })
			.result();

		expect(fetchMock).toHaveBeenCalledOnce();
		expect(ambient).not.toHaveBeenCalled();

		const [url, init] = fetchMock.mock.calls[0] as [URL, RequestInit];
		expect(String(url).endsWith("/v1/decisions")).toBe(true);
		expect(String(url)).toBe("https://typesafe.test/gateway/v1/decisions");
		expect(init.method).toBe("POST");

		const headers = init.headers as Record<string, string>;
		expect(headers.authorization).toBe("test-key");
		expect(headers["content-type"]).toBe("application/json");

		expect(JSON.parse(String(init.body))).toEqual({
			model: "jev-latest",
			state: requestBody.state,
			questions: question,
		});

		const content = result.content as { type: string; text: string }[];
		expect(content).toHaveLength(1);
		expect(content[0]?.type).toBe("text");
		expect(content[0]?.text).toBe(JSON.stringify(answers));
		expect(result.stopReason).toBe("stop");
		expect(result.model).toBe("jev-latest-2026");
		expect(result.usage.input).toBe(120);
		expect(result.usage.output).toBe(12);
		expect(result.usage.totalTokens).toBe(132);
	});

	it("emits a start -> text delta -> done sequence", async () => {
		const fetchMock = mockFetch(
			() => new Response(JSON.stringify({ model: "jev-latest", answers, usage: {} }), { status: 200 }),
		);

		const events: string[] = [];
		for await (const event of timiDecisionsApi().stream(model, jsonContext(requestBody), {
			apiKey: "test-key",
			fetch: fetchMock,
		})) {
			events.push(event.type);
		}

		expect(events).toEqual(["start", "text_delta", "done"]);
	});

	it("rejects a non-JSON user message with zero fetch calls", async () => {
		const fetchMock = mockFetch(() => new Response("{}", { status: 200 }));
		vi.stubGlobal(
			"fetch",
			vi.fn<FetchFunction>(async () => {
				throw new Error("ambient fetch must not be called");
			}),
		);

		const result: AssistantMessage = await timiDecisionsApi()
			.stream(
				model,
				{ messages: [{ role: "user", content: "Is this about billing?", timestamp: 1 }] },
				{
					apiKey: "test-key",
					fetch: fetchMock,
				},
			)
			.result();

		expect(fetchMock).not.toHaveBeenCalled();
		expect(result.stopReason).toBe("error");
		expect(result.errorMessage).toContain("expects the last user message");
	});

	it("rejects a JSON object missing state/questions with zero fetch calls", async () => {
		const fetchMock = mockFetch(() => new Response("{}", { status: 200 }));

		const result = await timiDecisionsApi()
			.stream(model, jsonContext({ questions: question }), { apiKey: "test-key", fetch: fetchMock })
			.result();

		expect(fetchMock).not.toHaveBeenCalled();
		expect(result.stopReason).toBe("error");
		expect(result.errorMessage).toContain("expects the last user message");
	});

	it("surfaces an upstream 429 as an error without retrying", async () => {
		const fetchMock = mockFetch(
			() =>
				new Response(JSON.stringify({ error: "rate limited" }), {
					status: 429,
					statusText: "Too Many Requests",
					headers: { "content-type": "application/json" },
				}),
		);

		const result = await timiDecisionsApi()
			.stream(model, jsonContext(requestBody), { apiKey: "test-key", fetch: fetchMock })
			.result();

		expect(fetchMock).toHaveBeenCalledOnce();
		expect(result.stopReason).toBe("error");
		expect(result.errorMessage).toContain("429");
	});
});

describe("timi provider jev-latest routing", () => {
	it("routes only jev-latest to timi-decisions", () => {
		const models = timiProvider().getModels();

		const jev = models.find((entry) => entry.id === "jev-latest");
		expect(jev).toBeDefined();
		expect(jev?.api).toBe("timi-decisions");

		const others = models.filter((entry) => entry.id !== "jev-latest");
		expect(others.length).toBeGreaterThan(0);
		for (const entry of others) {
			expect(entry.api).toBe(TIMI_MODELS[entry.id as keyof typeof TIMI_MODELS].api);
		}

		expect(models.find((entry) => entry.id === "claude-sonnet-4.6")?.api).toBe("anthropic-messages");
		expect(models.find((entry) => entry.id === "gpt-5.6-sol")?.api).toBe("openai-responses");
	});
});
