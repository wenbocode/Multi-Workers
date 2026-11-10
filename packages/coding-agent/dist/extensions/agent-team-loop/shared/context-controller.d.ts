import type { Api, AssistantMessage, Context, Model, SimpleStreamOptions, Usage } from "@earendil-works/pi-ai";
import { type ContextBudget, type ContextEstimateOptions } from "./context-budget.ts";
import { type ResolvedContextPolicy } from "./context-policy.ts";
import { type SummaryFailure } from "./context-summary-diagnostics.ts";
export declare const CONTEXT_COMPACTION_USAGE_TYPE = "mw-context-compaction-usage";
export interface ContextCompactionUsage {
    version: 1;
    attemptId: string;
    attemptStartedAt: string;
    provider: string;
    model: string;
    purpose: "summary";
    providerRequestStarted: boolean;
    usage: Pick<Usage, "input" | "output" | "cacheRead" | "cacheWrite"> | null;
    status: "stop" | "length" | "error" | "aborted" | "unknown";
    taskId?: string;
}
export interface MwContextPolicyDetails extends Record<string, unknown> {
    code: string;
    source: unknown;
    configured: number | null;
    effective: number | null;
    estimate: number | null;
    noProviderRequest: true;
    summaryFailure?: SummaryFailure;
}
export declare class MwContextPolicyError extends Error {
    readonly details: MwContextPolicyDetails;
    constructor(code: string, details?: Partial<MwContextPolicyDetails>);
}
export declare function isContextPolicyFailure(message: AssistantMessage): boolean;
export declare function contextPolicyFailureMessage(model: Model<Api>, error: MwContextPolicyError): AssistantMessage;
export interface ContextControllerOptions {
    readPolicy: () => ResolvedContextPolicy | Promise<ResolvedContextPolicy>;
    estimateOptions?: (model: Model<Api>, context: Context, options?: SimpleStreamOptions) => ContextEstimateOptions;
}
export interface NativeCompactionPlan {
    beforeTokens: number;
    beforeBaseTokens: number;
    policy: ResolvedContextPolicy;
    budget: ContextBudget;
}
/** MW owns admission and triggering; pi owns generation, persistence and context rebuilding. */
export declare class ContextController {
    private readonly options;
    private readonly calibration;
    constructor(options: ContextControllerOptions);
    resetCalibration(): void;
    private estimate;
    observeUsage(model: Model<Api>, context: Context, options: SimpleStreamOptions | undefined, usage: Usage): void;
    private settings;
    private failure;
    /** Called only at complete-turn boundaries, before core native compaction is requested. */
    planNativeCompaction(model: Model<Api>, context: Context, options?: SimpleStreamOptions): Promise<NativeCompactionPlan | undefined>;
    /** Provider requests never generate or project summaries. They only enforce the actual budget. */
    prepare(model: Model<Api>, context: Context, options?: SimpleStreamOptions, mode?: {
        nativeSummary?: boolean;
        budgetOnly?: boolean;
        automaticNativeSummary?: boolean;
    }): Promise<Context>;
    /** Core has already committed and rebuilt native context; reject continuation if it made no progress. */
    assertNativeProgress(model: Model<Api>, context: Context, plan: NativeCompactionPlan, options?: SimpleStreamOptions): Promise<void>;
    nativeFailure(model: Model<Api>, failure: unknown, code?: string): MwContextPolicyError;
}
//# sourceMappingURL=context-controller.d.ts.map