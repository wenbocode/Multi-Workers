import { type Context, InMemoryCredentialStore } from "@earendil-works/pi-ai";
import { afterEach, expect, it, vi } from "vitest";
import { ModelRegistry } from "../../src/core/model-registry.ts";
import { ModelRuntime } from "../../src/core/model-runtime.ts";
import { registerToa } from "../../src/extensions/agent-team-loop/shared/toa-provider.ts";

afterEach(() => vi.unstubAllEnvs());

it.each(["hy4", "hy3"])("streams %s through TokenLink across retries, tool calls and questions", async (id) => {
	vi.stubEnv("TOA_API_KEY", "toa-test");
	const runtime = await ModelRuntime.create({ credentials: new InMemoryCredentialStore(), modelsPath: null });
	const registry = new ModelRegistry(runtime);
	const on = vi.fn();
	registerToa({ registerProvider: registry.registerProvider.bind(registry), on });
	await runtime.refresh({ allowNetwork: false });
	const model = runtime.getModel("toa", id);
	if (!model) throw new Error(`Missing toa/${id}`);
	expect(model.contextWindow).toBe(id === "hy4" ? 1048576 : 262144);
	expect(model.input).toEqual(id === "hy4" ? ["text", "image"] : ["text"]);
	const context: Context = {
		messages: [{ role: "user", content: "look up", timestamp: 1 }],
		tools: [{ name: "lookup", description: "Look up a value", parameters: { type: "object", properties: {} } }],
	};
	const requests: { headers: Headers; body: Record<string, unknown> }[] = [];
	const fetcher: typeof fetch = async (url, init) => {
		expect(String(url)).toBe("https://tokenlink.woa.com/openapi/v1/chat/completions");
		expect(init?.method).toBe("POST");
		const headers = new Headers(init?.headers);
		expect(headers.get("authorization")).toBe("Bearer toa-test");
		requests.push({ headers, body: JSON.parse(String(init?.body)) });
		if (requests.length === 1) return new Response("Busy", { status: 429, headers: { "retry-after-ms": "1" } });
		const toolCall = requests.length === 2;
		const delta = toolCall
			? { tool_calls: [{ index: 0, id: "c1", type: "function", function: { name: "lookup", arguments: "{}" } }] }
			: { content: "ok" };
		const choice = { index: 0, delta, finish_reason: toolCall ? "tool_calls" : "stop" };
		return new Response(`data: ${JSON.stringify({ choices: [choice] })}\n\ndata: [DONE]\n\n`, {
			headers: { "content-type": "text/event-stream" },
		});
	};
	const options = { fetch: fetcher, sessionId: "session-1", maxRetries: 1, reasoning: "low" } as const;
	const [event, messageStart] = on.mock.calls[0];
	expect(event).toBe("message_start");
	const ctx = { sessionManager: { getSessionId: () => options.sessionId } };
	messageStart({ message: context.messages[0] }, ctx);
	const first = await runtime.completeSimple(model, context, options);
	expect(first.stopReason, first.errorMessage).toBe("toolUse");
	expect(first.content).toContainEqual(expect.objectContaining({ type: "toolCall", id: "c1", name: "lookup" }));
	expect(requests[0].body).toMatchObject({
		model: id,
		stream: true,
		prompt_cache_key: "session-1",
		reasoning_effort: id === "hy4" ? "high" : "low",
		tools: [expect.objectContaining({ type: "function" })],
	});
	context.messages.push(first, {
		role: "toolResult",
		toolCallId: "c1",
		toolName: "lookup",
		content: [{ type: "text", text: "42" }],
		isError: false,
		timestamp: 2,
	});
	const second = await runtime.completeSimple(model, context, options);
	expect(second.content).toContainEqual({ type: "text", text: "ok" });
	expect(requests[2].body.messages).toContainEqual(expect.objectContaining({ role: "tool", tool_call_id: "c1" }));
	context.messages.push(second, { role: "user", content: "next", timestamp: 3 });
	messageStart({ message: context.messages.at(-1) }, ctx);
	const third = await runtime.completeSimple(model, context, {
		...options,
		reasoning: undefined,
		cacheRetention: "none",
	});
	expect(third.stopReason).toBe("stop");
	expect(requests[3].body.reasoning_effort).toBe("no_think");
	expect(requests[3].body).not.toHaveProperty("prompt_cache_key");
	const requestIds = requests.map(({ headers }) => headers.get("x-model-request-id"));
	expect(new Set(requestIds).size).toBe(4);
	for (const request of requests) {
		expect(request.headers.get("x-model-request-id")).toMatch(/^[0-9a-f-]{36}$/);
		expect(request.headers.get("x-session-id")).toBe("session-1");
	}
	const qa = requests.map(({ headers }) => headers.get("x-qa-id"));
	expect(qa[0]).toBeTruthy();
	expect(qa.slice(1, 3)).toEqual([qa[0], qa[0]]);
	expect(qa[3]).toBeTruthy();
	expect(qa[3]).not.toBe(qa[0]);
});
