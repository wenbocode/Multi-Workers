import {
	type Api,
	type AssistantMessage,
	type AssistantMessageEventStream,
	type Context,
	createAssistantMessageEventStream,
	type Model,
	type Provider,
	type SimpleStreamOptions,
} from "@earendil-works/pi-ai";
import type { ExtensionContext } from "../../../core/extensions/types.ts";
import type { ModelRegistry } from "../../../core/model-registry.ts";
import { projectSummaryFailure } from "./context-summary-diagnostics.ts";
import { type NativeSummaryReport, runNativeSummaryPolicy } from "./native-summary-policy.ts";

export interface ProviderContextPolicy {
	prepare(
		model: Model<Api>,
		context: Context,
		options: SimpleStreamOptions | undefined,
		mode: { nativeSummary?: boolean; budgetOnly?: boolean; automaticNativeSummary?: boolean },
	): Promise<Context>;
	observeUsage(
		model: Model<Api>,
		context: Context,
		options: SimpleStreamOptions | undefined,
		usage: AssistantMessage["usage"],
	): void;
}

export interface ProviderPolicyHooks {
	controller?: ProviderContextPolicy;
	nativeSummarySignals?: WeakSet<AbortSignal>;
	automaticNativeSummarySignals?: WeakSet<AbortSignal>;
	policyFailure?: (model: Model<Api>, error: unknown) => AssistantMessage | undefined;
	nativeSummaryFailure?: (
		model: Model<Api>,
		response: AssistantMessage,
		signal: AbortSignal | undefined,
		failure?: unknown,
		report?: NativeSummaryReport,
	) => AssistantMessage | undefined;
	nativeSummaryComplete?: (model: Model<Api>, report: NativeSummaryReport, signal: AbortSignal | undefined) => void;
	nativeSummaryPolicyFailure?: (
		model: Model<Api>,
		response: AssistantMessage,
		report: NativeSummaryReport,
		signal: AbortSignal | undefined,
	) => void;
	authChanged?: (model: Model<Api>) => Error;
	limit?: (
		model: Model<Api>,
		start: () => AssistantMessageEventStream,
		signal: AbortSignal | undefined,
		ctx: ExtensionContext,
	) => AssistantMessageEventStream;
}

interface ProviderPolicyState extends ProviderPolicyHooks {
	ctx: ExtensionContext;
}

const states = new WeakMap<ModelRegistry, ProviderPolicyState>();
const wrappers = new WeakSet<Provider>();

/** One coordinator owns the request pipeline; each physical call owns its own slot. */
export function installProviderPolicies(ctx: ExtensionContext, contextPolicy?: ProviderPolicyHooks): void {
	const registry = ctx.modelRegistry;
	let state = states.get(registry);
	if (!state) {
		state = { ctx };
		states.set(registry, state);
	}
	state.ctx = ctx;
	if (contextPolicy) Object.assign(state, contextPolicy);
	for (const id of new Set(registry.getAll().map((model) => model.provider))) {
		const native = registry.getRegisteredNativeProvider(id);
		if (native && wrappers.has(native)) continue;
		const provider = registry.getProvider(id);
		if (!provider) continue;
		const current = state;
		const dispatch = (
			method: "stream" | "streamSimple",
			model: Model<Api>,
			context: Context,
			options?: SimpleStreamOptions,
		): AssistantMessageEventStream => {
			const output = createAssistantMessageEventStream();
			void (async () => {
				try {
					const entryAuth = await registry.getApiKeyAndHeaders(model);
					if (!entryAuth.ok) throw new Error(entryAuth.error);
					const physicalDispatch = (
						selected: Model<Api>,
						request: Context,
						requestOptions?: SimpleStreamOptions,
					): AssistantMessageEventStream => {
						let started = false;
						const start = () => {
							const transport = createAssistantMessageEventStream();
							void (async () => {
								try {
									// Resolve after waiting for the slot, including after an intervening summary.
									const auth = await registry.getApiKeyAndHeaders(selected);
									if (!auth.ok) throw new Error(auth.error);
									requestOptions?.signal?.throwIfAborted();
									const changed = () =>
										current.authChanged?.(selected) ??
										new Error("Request authentication changed; retry with fresh credentials");
									if (
										requestOptions?.apiKey !== undefined &&
										requestOptions.apiKey === entryAuth.apiKey &&
										auth.apiKey !== entryAuth.apiKey
									)
										throw changed();
									const authenticated = {
										...requestOptions,
										maxTokens: requestOptions?.maxTokens ?? selected.maxTokens,
										apiKey:
											requestOptions?.apiKey !== undefined && requestOptions.apiKey !== entryAuth.apiKey
												? requestOptions.apiKey
												: auth.apiKey,
										headers: refreshAuthValues(
											entryAuth.headers,
											auth.headers,
											requestOptions?.headers,
											changed,
										),
										env: refreshAuthValues(entryAuth.env, auth.env, requestOptions?.env, changed),
									};
									const resolved = auth.baseUrl ? { ...selected, baseUrl: auth.baseUrl } : selected;
									// Queue/auth waits may span a policy edit. This last guard never summarizes while holding a slot.
									await current.controller?.prepare(selected, request, requestOptions, {
										budgetOnly: true,
										nativeSummary:
											!!requestOptions?.signal && current.nativeSummarySignals?.has(requestOptions.signal),
										automaticNativeSummary:
											!!requestOptions?.signal &&
											current.automaticNativeSummarySignals?.has(requestOptions.signal),
									});
									requestOptions?.signal?.throwIfAborted();
									started = true;
									const stream = provider[method](resolved, request, authenticated);
									for await (const event of stream) transport.push(event);
									transport.end(await stream.result());
								} catch (error) {
									const failure = requestFailure(selected, error, requestOptions?.signal, current, false);
									if (requestOptions?.signal && current.nativeSummarySignals?.has(requestOptions.signal)) {
										// Preserve allowlisted transport fields through the summary retry boundary.
										// The raw Error and its body/stack never enter a diagnostic.
										const safe = projectSummaryFailure(error);
										failure.diagnostics = [
											...(failure.diagnostics ?? []),
											{
												type: "native_summary_transport",
												timestamp: Date.now(),
												details: { httpStatus: safe.httpStatus, code: safe.errorType },
											},
										];
									}
									transport.push({
										type: "error",
										reason: failure.stopReason === "aborted" ? "aborted" : "error",
										error: failure,
									});
									transport.end(failure);
								}
							})();
							return transport;
						};
						const stream = current.limit
							? current.limit(selected, start, requestOptions?.signal, current.ctx)
							: start();
						Object.defineProperty(stream, "providerRequestStarted", { get: () => started });
						return stream;
					};
					if (options?.signal && current.nativeSummarySignals?.has(options.signal)) {
						const summarySignal = options.signal;
						const { response, report } = await runNativeSummaryPolicy(
							model,
							context,
							options,
							async (request, requestOptions) => {
								let projected: Context;
								try {
									projected = current.controller
										? await current.controller.prepare(model, request, requestOptions, {
												nativeSummary: true,
												automaticNativeSummary: current.automaticNativeSummarySignals?.has(summarySignal),
											})
										: request;
									requestOptions.signal?.throwIfAborted();
								} catch (error) {
									return {
										response: requestFailure(model, error, summarySignal, current, false),
										providerRequestStarted: false,
									};
								}
								const stream = physicalDispatch(model, projected, requestOptions);
								const result = await stream.result();
								if (Reflect.get(stream, "providerRequestStarted") === true)
									current.controller?.observeUsage(model, projected, requestOptions, result.usage);
								return {
									response: result,
									providerRequestStarted: Reflect.get(stream, "providerRequestStarted") === true,
								};
							},
						);
						let result = response;
						if (response.diagnostics?.some((diagnostic) => diagnostic.type === "mw_context_policy")) {
							result = {
								...response,
								diagnostics: response.diagnostics.map((diagnostic) =>
									diagnostic.type === "mw_context_policy"
										? { ...diagnostic, details: { ...diagnostic.details, nativeSummaryReport: report } }
										: diagnostic,
								),
							};
							current.nativeSummaryPolicyFailure?.(model, result, report, summarySignal);
						} else if (response.stopReason === "stop" && !options.signal.aborted) {
							current.nativeSummaryComplete?.(model, report, options.signal);
						} else if (!summarySignal.aborted) {
							result =
								current.nativeSummaryFailure?.(model, response, options.signal, undefined, report) ?? response;
						}
						if (result.stopReason === "pending") {
							const incomplete = {
								...result,
								stopReason: "error" as const,
								errorMessage: "Native summary ended without a final response",
							};
							output.push({ type: "error", reason: "error", error: incomplete });
							output.end(incomplete);
							return;
						}
						if (result.stopReason === "error" || result.stopReason === "aborted")
							output.push({ type: "error", reason: result.stopReason, error: result });
						else output.push({ type: "done", reason: result.stopReason, message: result });
						output.end(result);
						return;
					}
					const projected = current.controller
						? await current.controller.prepare(model, context, options, {
								nativeSummary: !!options?.signal && current.nativeSummarySignals?.has(options.signal),
								automaticNativeSummary:
									!!options?.signal && current.automaticNativeSummarySignals?.has(options.signal),
							})
						: context;
					options?.signal?.throwIfAborted();
					const stream = physicalDispatch(model, projected, options);
					for await (const event of stream) {
						if (event.type === "done")
							current.controller?.observeUsage(model, projected, options, event.message.usage);
						output.push(event);
					}
					output.end(await stream.result());
				} catch (error) {
					const failure = requestFailure(model, error, options?.signal, current);
					output.push({
						type: "error",
						reason: failure.stopReason === "aborted" ? "aborted" : "error",
						error: failure,
					});
					output.end(failure);
				}
			})();
			return output;
		};
		const wrapper: Provider = {
			id: provider.id,
			name: provider.name,
			baseUrl: provider.baseUrl,
			headers: provider.headers,
			auth: provider.auth,
			getModels: provider.getModels.bind(provider),
			refreshModels: provider.refreshModels?.bind(provider),
			filterModels: provider.filterModels?.bind(provider),
			fetchDeferred: provider.fetchDeferred?.bind(provider),
			cancelDeferred: provider.cancelDeferred?.bind(provider),
			stream: (model, context, options) => dispatch("stream", model, context, options),
			streamSimple: (model, context, options) => dispatch("streamSimple", model, context, options),
		};
		wrappers.add(wrapper);
		registry.registerProvider(wrapper);
	}
}

function refreshAuthValues<T extends string | null>(
	entry: Record<string, T> | undefined,
	fresh: Record<string, T> | undefined,
	supplied: Record<string, T> | undefined,
	changed: () => Error,
): Record<string, T> {
	const values = { ...fresh };
	for (const [key, value] of Object.entries(supplied ?? {}) as Array<[string, T]>) {
		if (entry?.[key] !== undefined && value === entry[key] && fresh?.[key] !== entry[key]) throw changed();
		if (value !== entry?.[key] || fresh?.[key] === entry?.[key]) values[key] = value;
	}
	return values;
}

function requestFailure(
	model: Model<Api>,
	error: unknown,
	signal: AbortSignal | undefined,
	state: ProviderPolicyState,
	guardNativeSummary = true,
): AssistantMessage {
	const policy = !signal?.aborted ? state.policyFailure?.(model, error) : undefined;
	if (policy) return policy;
	const message: AssistantMessage = {
		role: "assistant",
		api: model.api,
		provider: model.provider,
		model: model.id,
		content: [],
		stopReason: signal?.aborted ? "aborted" : "error",
		errorMessage: error instanceof Error ? error.message : String(error),
		timestamp: Date.now(),
		usage: {
			input: 0,
			output: 0,
			cacheRead: 0,
			cacheWrite: 0,
			totalTokens: 0,
			cost: { input: 0, output: 0, cacheRead: 0, cacheWrite: 0, total: 0 },
		},
	};
	if (guardNativeSummary && !signal?.aborted && signal && state.nativeSummarySignals?.has(signal))
		return state.nativeSummaryFailure?.(model, message, signal, error) ?? message;
	return message;
}
