import { type Api, type Context, InMemoryCredentialStore, type Model } from "@earendil-works/pi-ai";
import { Type } from "typebox";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI, ProviderConfig } from "../../src/core/extensions/types.ts";
import { ModelRuntime } from "../../src/core/model-runtime.ts";
import { activate } from "../../src/extensions/agent-team-loop/index.ts";
import { registerLocalCodex, streamLocalCodex } from "../../src/extensions/agent-team-loop/shared/codex-local.ts";
import { LOCAL_CODEX_PROVIDER } from "../../src/extensions/agent-team-loop/shared/codex-proxy.ts";

vi.mock("../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts", () => ({ pmActivate: vi.fn() }));
vi.mock("../../src/extensions/agent-team-loop/worker/worker-mode.ts", () => ({ workerModeActivate: vi.fn() }));
vi.mock("../../src/extensions/agent-team-loop/pm/decision-tool.ts", () => ({
	initiatorRoleFromWorkerTask: vi.fn(),
	registerAskDecisionTool: vi.fn(),
}));
vi.mock("../../src/extensions/agent-team-loop/shared/implementation-gate.ts", () => ({
	registerImplementationGate: vi.fn(),
}));
vi.mock("../../src/extensions/agent-team-loop/shared/protected-config.ts", () => ({
	registerProtectedConfigGuard: vi.fn(),
}));
vi.mock("../../src/extensions/agent-team-loop/shared/worktree-junction-guard.ts", () => ({
	registerWorktreeJunctionGuard: vi.fn(),
}));
vi.mock("../../src/extensions/agent-team-loop/shared/xkey-gate-guard.ts", () => ({
	registerDecisionSignoffGuard: vi.fn(),
	registerXkeyGateGuard: vi.fn(),
}));

const token = "test-local-token-at-least-24-characters";
const model: Model<Api> = {
	id: "test-model",
	name: "Test",
	api: "openai-codex-responses",
	provider: "openai-codex",
	baseUrl: "http://127.0.0.1:7010",
	reasoning: true,
	input: ["text"],
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
	contextWindow: 10000,
	maxTokens: 1000,
};
const context: Context = {
	systemPrompt: "system instruction",
	messages: [{ role: "user", content: "hello", timestamp: 1 }],
	tools: [{ name: "read", description: "read", parameters: Type.Object({ path: Type.String() }) }],
};

afterEach(() => {
	vi.unstubAllEnvs();
	delete (globalThis as Record<string, unknown>).__agentTeamLoopActivated;
});

function fakeFetch(event: object): typeof fetch {
	return vi.fn<typeof fetch>(async (url) =>
		String(url).endsWith("/status")
			? Response.json({ status: "ready", backend: "codex-cli", protocol: 2, active: [] })
			: new Response(`${JSON.stringify(event)}\n`),
	);
}

describe("local Codex adapter", () => {
	it("uses the local provider through ModelRuntime with an isolated credential store", async () => {
		vi.stubEnv("MW_CODEX_LOCAL_URL", model.baseUrl);
		vi.stubEnv("MW_CODEX_LOCAL_TOKEN", token);
		const runtime = await ModelRuntime.create({ modelsPath: null, credentials: new InMemoryCredentialStore() });
		registerLocalCodex({
			on: vi.fn(),
			registerProvider: (name: string, config: ProviderConfig) => runtime.registerProvider(name, config),
		} as unknown as ExtensionAPI);
		const localModel = runtime.getModel(LOCAL_CODEX_PROVIDER, "gpt-5.6-sol");
		expect(localModel).toBeDefined();
		if (!localModel) throw new Error("Missing catalog model");
		expect(localModel.baseUrl).toBe(model.baseUrl);
		expect(localModel.input).toEqual(["text"]);
		expect(localModel.cost.input).toBe(0);
		const output = await runtime.completeSimple(localModel, context, {
			fetch: fakeFetch({ type: "result", text: "local", toolCalls: [] }),
		});
		expect(output.stopReason).toBe("stop");
		expect(output.content).toEqual([{ type: "text", text: "local" }]);
	});

	it("is opt-in and rejects remote endpoints or missing tokens", () => {
		vi.stubEnv("MW_CODEX_LOCAL_URL", "");
		const registerProvider = vi.fn();
		const pi = { registerProvider, on: vi.fn() } as unknown as ExtensionAPI;
		registerLocalCodex(pi);
		expect(registerProvider).not.toHaveBeenCalled();
		vi.stubEnv("MW_CODEX_LOCAL_URL", "https://example.com");
		vi.stubEnv("MW_CODEX_LOCAL_TOKEN", token);
		expect(() => registerLocalCodex(pi)).toThrow("127.0.0.1");
		vi.stubEnv("MW_CODEX_LOCAL_URL", model.baseUrl);
		vi.stubEnv("MW_CODEX_LOCAL_TOKEN", "");
		expect(() => registerLocalCodex(pi)).toThrow("token");
	});

	it.each(["", "/worker/task.md"])("registers through actual activate for worker=%s", async (task) => {
		vi.stubEnv("PI_WORKER_TASK", task);
		vi.stubEnv("MW_CODEX_LOCAL_URL", model.baseUrl);
		vi.stubEnv("MW_CODEX_LOCAL_TOKEN", token);
		const registerProvider = vi.fn();
		await activate({ registerProvider, on: vi.fn() } as unknown as ExtensionAPI);
		expect(registerProvider).toHaveBeenCalledWith(
			LOCAL_CODEX_PROVIDER,
			expect.objectContaining({
				streamSimple: expect.any(Function),
				api: model.api,
				baseUrl: model.baseUrl,
			}),
		);
	});

	it("forwards model/context, hooks, token and usage with buffered text", async () => {
		const fetcher = fakeFetch({
			type: "result",
			text: "你好",
			toolCalls: [],
			usage: { input_tokens: 12, cached_input_tokens: 2, output_tokens: 3 },
		});
		const onPayload = vi.fn(() => undefined);
		const onResponse = vi.fn();
		const stream = streamLocalCodex(model, context, {
			fetch: fetcher,
			env: { MW_CODEX_LOCAL_TOKEN: token },
			onPayload,
			onResponse,
		});
		const events = [];
		for await (const event of stream) events.push(event.type);
		const output = await stream.result();
		expect(output.content).toEqual([{ type: "text", text: "你好" }]);
		expect(output.usage).toMatchObject({ input: 10, cacheRead: 2, output: 3, totalTokens: 15 });
		expect(events).toEqual(["start", "text_start", "text_delta", "text_end", "done"]);
		expect(onPayload).toHaveBeenCalledWith({ model: model.id, context, reasoning: undefined }, model);
		expect(onResponse).toHaveBeenCalledWith(expect.objectContaining({ status: 200 }), model);
		expect(fetcher).toHaveBeenCalledWith(
			`${model.baseUrl}/complete`,
			expect.objectContaining({
				body: JSON.stringify({ model: model.id, context }),
				headers: expect.objectContaining({ Authorization: `Bearer ${token}` }),
				redirect: "error",
			}),
		);
	});

	it("returns tools to pi without executing them", async () => {
		const call = { id: "call_1", name: "read", arguments: { path: "hello.txt" } };
		const output = await streamLocalCodex(model, context, {
			env: { MW_CODEX_LOCAL_TOKEN: token },
			fetch: fakeFetch({ type: "result", text: "", toolCalls: [call] }),
		}).result();
		expect(output.stopReason).toBe("toolUse");
		expect(output.content).toEqual([{ type: "toolCall", ...call }]);
	});

	it("handles fragmented UTF-8 NDJSON and honors payload replacement", async () => {
		const bytes = new TextEncoder().encode(
			`${JSON.stringify({ type: "heartbeat" })}\n${JSON.stringify({ type: "result", text: "中文", toolCalls: [] })}\n`,
		);
		const fetcher = vi.fn<typeof fetch>(async (url) =>
			String(url).endsWith("/status")
				? Response.json({ status: "ready", backend: "codex-cli", protocol: 2, active: [] })
				: new Response(
						new ReadableStream<Uint8Array>({
							start(controller) {
								for (const byte of bytes) controller.enqueue(new Uint8Array([byte]));
								controller.close();
							},
						}),
					),
		);
		const output = await streamLocalCodex(model, context, {
			env: { MW_CODEX_LOCAL_TOKEN: token },
			fetch: fetcher,
			onPayload: () => null,
		}).result();
		expect(output.content).toEqual([{ type: "text", text: "中文" }]);
		expect(fetcher).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ body: "null" }));
	});

	it.each([
		{ type: "error", error: "Codex timed out" },
		{ type: "heartbeat" },
		{ type: "result", text: "", toolCalls: [] },
		{ type: "result", text: "", toolCalls: [{ id: "x", name: "unknown", arguments: {} }] },
	])("fails instead of emitting success for %j", async (event) => {
		const output = await streamLocalCodex(model, context, {
			env: { MW_CODEX_LOCAL_TOKEN: token },
			fetch: fakeFetch(event),
		}).result();
		expect(output.stopReason).toBe("error");
		expect(output.errorMessage).toBeTruthy();
	});

	it("propagates cancellation to fetch", async () => {
		const controller = new AbortController();
		controller.abort();
		const fetcher = vi.fn<typeof fetch>(async (_url, init) => {
			init?.signal?.throwIfAborted();
			throw new Error("Expected an aborted signal");
		});
		const output = await streamLocalCodex(model, context, {
			env: { MW_CODEX_LOCAL_TOKEN: token },
			fetch: fetcher,
			signal: controller.signal,
		}).result();
		expect(output.stopReason).toBe("aborted");
	});
});
