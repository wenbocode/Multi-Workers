import type { Api, AssistantMessage, AssistantMessageEventStream, Context, Model, SimpleStreamOptions, Usage } from "@earendil-works/pi-ai";
import { type ContextEstimateOptions } from "./context-budget.ts";
import { type ContextCheckpointEntry } from "./context-checkpoint.ts";
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
export type PhysicalContextStream = AssistantMessageEventStream & {
    readonly providerRequestStarted?: boolean;
};
export interface PhysicalContextIntent {
    managedSummary?: boolean;
}
export type PhysicalContextDispatch = (model: Model<Api>, context: Context, options?: SimpleStreamOptions, intent?: PhysicalContextIntent) => PhysicalContextStream;
export interface ContextControllerOptions {
    readPolicy: () => ResolvedContextPolicy | Promise<ResolvedContextPolicy>;
    getCheckpointEntries: () => readonly ContextCheckpointEntry[];
    /** Must resolve only after the entry is durably committed. Production appendEntry is synchronous. */
    appendEntry: (customType: string, data: unknown) => void | Promise<void>;
    estimateOptions?: (model: Model<Api>, context: Context, options?: SimpleStreamOptions) => ContextEstimateOptions;
    taskId?: string;
}
export declare class ContextController {
    private readonly options;
    private readonly calibration;
    constructor(options: ContextControllerOptions);
    resetCalibration(): void;
    private estimate;
    observeUsage(model: Model<Api>, context: Context, options: SimpleStreamOptions | undefined, usage: Usage): void;
    private policy;
    prepare(model: Model<Api>, context: Context, options: SimpleStreamOptions | undefined, physicalDispatch: PhysicalContextDispatch, mode?: {
        nativeSummary?: boolean;
        budgetOnly?: boolean;
        managedSummary?: boolean;
    }): Promise<Context>;
    private prepareContext;
    private recordUsage;
}
//# sourceMappingURL=context-controller.d.ts.map