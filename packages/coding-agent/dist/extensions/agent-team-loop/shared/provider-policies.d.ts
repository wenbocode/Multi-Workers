import { type Api, type AssistantMessage, type AssistantMessageEventStream, type Context, type Model, type SimpleStreamOptions } from "@earendil-works/pi-ai";
import type { ExtensionContext } from "../../../core/extensions/types.ts";
import { type NativeSummaryReport } from "./native-summary-policy.ts";
export interface ProviderContextPolicy {
    prepare(model: Model<Api>, context: Context, options: SimpleStreamOptions | undefined, mode: {
        nativeSummary?: boolean;
        budgetOnly?: boolean;
        automaticNativeSummary?: boolean;
    }): Promise<Context>;
    observeUsage(model: Model<Api>, context: Context, options: SimpleStreamOptions | undefined, usage: AssistantMessage["usage"]): void;
}
export interface ProviderPolicyHooks {
    controller?: ProviderContextPolicy;
    nativeSummarySignals?: WeakSet<AbortSignal>;
    automaticNativeSummarySignals?: WeakSet<AbortSignal>;
    policyFailure?: (model: Model<Api>, error: unknown) => AssistantMessage | undefined;
    nativeSummaryFailure?: (model: Model<Api>, response: AssistantMessage, signal: AbortSignal | undefined, failure?: unknown, report?: NativeSummaryReport) => AssistantMessage | undefined;
    nativeSummaryComplete?: (model: Model<Api>, report: NativeSummaryReport, signal: AbortSignal | undefined) => void;
    nativeSummaryPolicyFailure?: (model: Model<Api>, response: AssistantMessage, report: NativeSummaryReport, signal: AbortSignal | undefined) => void;
    authChanged?: (model: Model<Api>) => Error;
    limit?: (model: Model<Api>, start: () => AssistantMessageEventStream, signal: AbortSignal | undefined, ctx: ExtensionContext) => AssistantMessageEventStream;
}
/** One coordinator owns the request pipeline; each physical call owns its own slot. */
export declare function installProviderPolicies(ctx: ExtensionContext, contextPolicy?: ProviderPolicyHooks): void;
//# sourceMappingURL=provider-policies.d.ts.map