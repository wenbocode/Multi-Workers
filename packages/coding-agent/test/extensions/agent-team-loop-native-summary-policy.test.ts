import {
	type Api,
	type AssistantMessage,
	type Context,
	createAssistantMessageEventStream,
	InMemoryCredentialStore,
	type Model,
	type Provider,
	type SimpleStreamOptions,
} from "@earendil-works/pi-ai";
import { openAICompletionsApi } from "@earendil-works/pi-ai/api/openai-completions.lazy";
import { describe, expect, it, vi } from "vitest";
import type { ExtensionContext } from "../../src/core/extensions/types.ts";
import { ModelRegistry } from "../../src/core/model-registry.ts";
import { ModelRuntime } from "../../src/core/model-runtime.ts";
import {
	contextPolicyFailureMessage,
	MwContextPolicyError,
} from "../../src/extensions/agent-team-loop/shared/context-controller.ts";
import { projectSummaryFailure } from "../../src/extensions/agent-team-loop/shared/context-summary-diagnostics.ts";
import type { NativeSummaryReport } from "../../src/extensions/agent-team-loop/shared/native-summary-policy.ts";
import {
	installProviderPolicies,
	type ProviderPolicyHooks,
} from "../../src/extensions/agent-team-loop/shared/provider-policies.ts";

const model: Model<"openai-completions"> = {
	id: "summary-fixture",
	name: "Summary fixture",
	provider: "summary-fixture",
	api: "openai-completions",
	baseUrl: "http://127.0.0.1:1",
	reasoning: true,
	input: ["text"],
	contextWindow: 256000,
	maxTokens: 65536,
	thinkingLevelMap: { off: "no_think", high: "high" },
	cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 },
};

function assistant(
	stopReason: AssistantMessage["stopReason"] = "stop",
	text = "Complete native task summary",
): AssistantMessage {
	return {
		role: "assistant",
		api: model.api,
		provider: model.provider,
		model: model.id,
		content: [{ type: "text", text }],
		stopReason,
		timestamp: Date.now(),
		usage: {
			input: 10,
			output: 6,
			cacheRead: 3,
			cacheWrite: 2,
			reasoning: 4,
			totalTokens: 21,
			cost: { input: 1, output: 2, cacheRead: 3, cacheWrite: 4, total: 10 },
		},
	};
}

async function harness(
	handler: (context: Context, options?: SimpleStreamOptions) => AssistantMessage | Promise<AssistantMessage>,
	hooks: ProviderPolicyHooks = {},
	selected: Model<Api> = model,
) {
	const runtime = await ModelRuntime.create({ modelsPath: null, credentials: new InMemoryCredentialStore() });
	let key = "stable-key";
	const calls: Array<{ context: Context; options: SimpleStreamOptions | undefined }> = [];
	const stream: Provider["streamSimple"] = (requestModel, context, options) => {
		calls.push({ context, options });
		const events = createAssistantMessageEventStream();
		void Promise.resolve(handler(context, options)).then((response) => {
			const result = { ...response, api: requestModel.api, provider: requestModel.provider, model: requestModel.id };
			if (result.stopReason === "error" || result.stopReason === "aborted")
				events.push({ type: "error", reason: result.stopReason, error: result });
			else if (result.stopReason === "stop" || result.stopReason === "length" || result.stopReason === "toolUse")
				events.push({ type: "done", reason: result.stopReason, message: result });
			events.end(result);
		});
		return events;
	};
	runtime.registerNativeProvider({
		id: selected.provider,
		name: "Fixture",
		getModels: () => [selected],
		auth: { apiKey: { name: "Fixture", resolve: async () => ({ auth: { apiKey: key } }) } },
		stream,
		streamSimple: stream,
	});
	const registry = new ModelRegistry(runtime);
	const signal = new AbortController();
	const summaries = new WeakSet([signal.signal]);
	const failure = vi.fn(
		(
			requestModel: Model<Api>,
			response: AssistantMessage,
			_signal: AbortSignal | undefined,
			_error: unknown,
			report: NativeSummaryReport | undefined,
		) =>
			contextPolicyFailureMessage(
				requestModel,
				new MwContextPolicyError(report?.invalid ? "SUMMARY_INVALID" : "SUMMARY_TRUNCATED", {
					summaryFailure: projectSummaryFailure(response),
					nativeSummaryUsage: response.usage,
					nativeSummaryReport: report,
				}),
			),
	);
	const complete = vi.fn();
	const policyRefusal = vi.fn();
	installProviderPolicies({ modelRegistry: registry } as ExtensionContext, {
		nativeSummarySignals: summaries,
		nativeSummaryFailure: failure,
		nativeSummaryComplete: complete,
		nativeSummaryPolicyFailure: policyRefusal,
		...hooks,
	});
	return {
		runtime,
		registry,
		signal,
		calls,
		failure,
		complete,
		policyRefusal,
		setKey(value: string) {
			key = value;
		},
	};
}

describe("native summary generation policy", () => {
	it("preserves allowlisted thrown transport fields across the recovery boundary without leaking the error", async () => {
		const h = await harness(() => {
			throw Object.assign(new Error("fetch failed PRIVATE-KEY https://private.invalid"), {
				code: "ECONNRESET",
				status: 503,
			});
		});
		const result = await h.runtime.completeSimple(model, { messages: [] }, { signal: h.signal.signal });
		expect(h.calls).toHaveLength(1);
		expect(result.diagnostics?.find((entry) => entry.type === "mw_context_policy")?.details?.summaryFailure).toEqual({
			category: "network",
			httpStatus: 503,
			errorType: "ECONNRESET",
		});
		expect(JSON.stringify(result)).not.toMatch(/PRIVATE-KEY|private\.invalid|stack/);
	});
	it("recovers one truncation with independent thinking/output and sums usage without calibrating the sum", async () => {
		let count = 0;
		const prepare = vi.fn(async (_model: Model<Api>, context: Context) => context);
		const observeUsage = vi.fn(
			(
				_model: Model<Api>,
				_context: Context,
				_options: SimpleStreamOptions | undefined,
				_usage: AssistantMessage["usage"],
			) => undefined,
		);
		let slots = 0;
		const h = await harness(() => assistant(++count === 1 ? "length" : "stop"), {
			controller: { prepare, observeUsage },
			limit: (_model, start) => {
				slots++;
				return start();
			},
		});
		const options: SimpleStreamOptions = {
			signal: h.signal.signal,
			maxTokens: 8192,
			reasoning: "high",
			thinkingBudgets: { high: 8192 },
		};
		const context = { systemPrompt: "Summarize history", messages: [] };
		const result = await h.runtime.completeSimple(model, context, options);
		expect(result.stopReason).toBe("stop");
		expect(h.calls.map((call) => call.options?.maxTokens)).toEqual([16384, 32768]);
		for (const call of h.calls) {
			expect(call.options?.reasoning).toBeUndefined();
			expect(call.options?.thinkingBudgets).toBeUndefined();
		}
		expect(h.calls[1].context.systemPrompt).toContain("Generate a shorter, complete summary");
		expect(options.reasoning).toBe("high");
		expect(context.systemPrompt).toBe("Summarize history");
		expect(slots).toBe(2);
		expect(prepare).toHaveBeenCalledTimes(4);
		expect(observeUsage).toHaveBeenCalledTimes(2);
		for (const call of observeUsage.mock.calls) expect(call[3]).toMatchObject({ input: 10, output: 6 });
		expect(result.usage).toMatchObject({ input: 20, output: 12, reasoning: 8, totalTokens: 42, cost: { total: 20 } });
		expect(h.failure).not.toHaveBeenCalled();
		expect(h.complete).toHaveBeenCalledOnce();
		expect(h.complete.mock.calls[0][1]).toMatchObject({
			summaryStatus: "stop",
			invalid: false,
			attempts: [
				{
					attempt: 1,
					maxTokens: 16384,
					reasoning: "off",
					status: "length",
					reasoningTokens: 4,
					providerRequestStarted: true,
				},
				{
					attempt: 2,
					maxTokens: 32768,
					reasoning: "off",
					status: "stop",
					reasoningTokens: 4,
					providerRequestStarted: true,
				},
			],
		});
	});

	it("clamps both attempts to model output capability and invokes failure once after exhaustion", async () => {
		const small = { ...model, maxTokens: 10000 };
		const h = await harness(() => assistant("length", "PRIVATE-PARTIAL"), {}, small);
		const result = await h.runtime.completeSimple(
			small,
			{ messages: [] },
			{ signal: h.signal.signal, maxTokens: 8192 },
		);
		expect(h.calls.map((call) => call.options?.maxTokens)).toEqual([10000, 10000]);
		expect(result.stopReason).toBe("error");
		expect(h.failure).toHaveBeenCalledOnce();
		expect(h.failure.mock.calls[0][1].usage.input).toBe(20);
		expect(h.complete).not.toHaveBeenCalled();
		expect(JSON.stringify(result)).not.toContain("PRIVATE-PARTIAL");
	});

	it.each(["empty", "thinking"])("retries unusable %s stop and fails before core can save it", async (mode) => {
		const h = await harness(() => ({
			...assistant("stop", " \n "),
			...(mode === "thinking" ? { content: [{ type: "thinking" as const, thinking: "PRIVATE-THINKING" }] } : {}),
		}));
		const result = await h.runtime.completeSimple(model, { messages: [] }, { signal: h.signal.signal });
		expect(h.calls).toHaveLength(2);
		expect(result.errorMessage).toContain("SUMMARY_INVALID");
		expect(h.failure.mock.calls[0][4]).toMatchObject({ summaryStatus: "stop", invalid: true });
		expect(h.complete).not.toHaveBeenCalled();
		expect(JSON.stringify(result)).not.toContain("PRIVATE-THINKING");
	});

	it("leaves business reasoning/output and length responses unchanged", async () => {
		const h = await harness(() => assistant("length"));
		const result = await h.runtime.completeSimple(model, { messages: [] }, { maxTokens: 8192, reasoning: "high" });
		expect(result.stopReason).toBe("length");
		expect(h.calls).toHaveLength(1);
		expect(h.calls[0].options).toMatchObject({ maxTokens: 8192, reasoning: "high" });
		expect(h.failure).not.toHaveBeenCalled();
		expect(h.complete).not.toHaveBeenCalled();
	});

	it.each(["length", "stop"] as const)(
		"honors cancellation with a late %s response without recovery or success",
		async (status) => {
			const h = await harness(() => {
				h.signal.abort();
				return assistant(status);
			});
			const result = await h.runtime.completeSimple(model, { messages: [] }, { signal: h.signal.signal });
			expect(result.stopReason).toBe("aborted");
			expect(h.calls).toHaveLength(1);
			expect(h.failure).not.toHaveBeenCalled();
			expect(h.complete).not.toHaveBeenCalled();
		},
	);

	it.each(["before-slot", "after-slot"])(
		"rechecks admission %s on recovery and preserves the typed refusal",
		async (phase) => {
			let slots = 0;
			const h = await harness(() => assistant("length"), {
				controller: {
					prepare: async (_model, request, _options, mode) => {
						if ((phase === "before-slot" && slots === 1 && !mode.budgetOnly) || (slots === 2 && mode.budgetOnly))
							throw new MwContextPolicyError("NATIVE_SUMMARY_BUDGET");
						return request;
					},
					observeUsage: vi.fn(),
				},
				limit: (_model, start) => {
					slots++;
					return start();
				},
				policyFailure: (selected, error) =>
					error instanceof MwContextPolicyError ? contextPolicyFailureMessage(selected, error) : undefined,
			});
			const result = await h.runtime.completeSimple(model, { messages: [] }, { signal: h.signal.signal });
			expect(slots).toBe(phase === "before-slot" ? 1 : 2);
			expect(h.calls).toHaveLength(1);
			expect(result.errorMessage).toContain("NATIVE_SUMMARY_BUDGET");
			expect(h.failure).not.toHaveBeenCalled();
			expect(h.policyRefusal).toHaveBeenCalledOnce();
			expect(result.diagnostics?.find((entry) => entry.type === "mw_context_policy")?.details).toMatchObject({
				code: "NATIVE_SUMMARY_BUDGET",
				nativeSummaryReport: { attempts: [{ providerRequestStarted: true }, { providerRequestStarted: false }] },
			});
		},
	);

	it("rereads auth between recovery calls and refuses an ambiguous stale injected request key", async () => {
		let count = 0;
		const h = await harness(
			() => {
				if (++count === 1) {
					h.setKey("rotated-key");
					return assistant("length");
				}
				return assistant();
			},
			{
				authChanged: () => new MwContextPolicyError("AUTH_CHANGED"),
				policyFailure: (selected, error) =>
					error instanceof MwContextPolicyError ? contextPolicyFailureMessage(selected, error) : undefined,
			},
		);
		const result = await h.runtime.completeSimple(model, { messages: [] }, { signal: h.signal.signal });
		expect(result.errorMessage).toContain("AUTH_CHANGED");
		expect(h.calls.map((call) => call.options?.apiKey)).toEqual(["stable-key"]);
		expect(h.failure).not.toHaveBeenCalled();
	});

	it("removes provider-specific reasoningEffort on raw native streams", async () => {
		const h = await harness(() => assistant());
		const result = await h.runtime.complete(
			model,
			{ messages: [] },
			{ signal: h.signal.signal, reasoningEffort: "high" },
		);
		expect(result.stopReason).toBe("stop");
		expect(h.calls).toHaveLength(1);
		expect(Reflect.get(h.calls[0].options ?? {}, "reasoningEffort")).toBeUndefined();
	});

	it("maps disabled thinking to the actual TOA-compatible no_think payload without network", async () => {
		const chat = openAICompletionsApi();
		const bodies: unknown[] = [];
		const h = await harness(async (request, options) =>
			chat
				.streamSimple(model, request, {
					...options,
					fetch: async (_input, init) => {
						bodies.push(JSON.parse(String(init?.body)));
						return new Response(
							`data: ${JSON.stringify({ id: "offline", choices: [{ index: 0, delta: { content: "Complete summary" }, finish_reason: "stop" }], usage: { prompt_tokens: 10, completion_tokens: 4 } })}\n\ndata: [DONE]\n\n`,
							{ headers: { "content-type": "text/event-stream" } },
						);
					},
				})
				.result(),
		);
		const result = await h.runtime.completeSimple(
			model,
			{ messages: [] },
			{ signal: h.signal.signal, reasoning: "high", maxTokens: 8192 },
		);
		expect(result.stopReason).toBe("stop");
		expect(bodies).toEqual([expect.objectContaining({ reasoning_effort: "no_think", max_completion_tokens: 16384 })]);
	});
});
