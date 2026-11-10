import { type Api, type AssistantMessage, type AssistantMessageEventStream, type Context, type Model, type SimpleStreamOptions } from "@earendil-works/pi-ai";
import type { ExtensionContext } from "../../../core/extensions/types.ts";
export interface ProviderContextPolicy {
    prepare(model: Model<Api>, context: Context, options: SimpleStreamOptions | undefined, dispatch: (model: Model<Api>, context: Context, options?: SimpleStreamOptions, intent?: {
        managedSummary?: boolean;
    }) => AssistantMessageEventStream, mode: {
        nativeSummary?: boolean;
        budgetOnly?: boolean;
        managedSummary?: boolean;
    }): Promise<Context>;
    observeUsage(model: Model<Api>, context: Context, options: SimpleStreamOptions | undefined, usage: AssistantMessage["usage"]): void;
}
export interface ProviderPolicyHooks {
    controller?: ProviderContextPolicy;
    nativeSummarySignals?: WeakSet<AbortSignal>;
    policyFailure?: (model: Model<Api>, error: unknown) => AssistantMessage | undefined;
    authChanged?: (model: Model<Api>) => Error;
    limit?: (model: Model<Api>, start: () => AssistantMessageEventStream, signal: AbortSignal | undefined, ctx: ExtensionContext) => AssistantMessageEventStream;
}
/** One coordinator owns the request pipeline; each physical call owns its own slot. */
export declare function installProviderPolicies(ctx: ExtensionContext, contextPolicy?: ProviderPolicyHooks): void;
//# sourceMappingURL=provider-policies.d.ts.map