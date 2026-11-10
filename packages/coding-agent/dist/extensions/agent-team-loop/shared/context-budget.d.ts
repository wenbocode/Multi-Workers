import type { Api, Context, Model, Usage } from "@earendil-works/pi-ai";
import type { ResolvedContextPolicy } from "./context-policy.ts";
export interface ContextBudget {
    modelWindow: number;
    configuredMaxTokens: number;
    effectiveWindow: number;
    outputReserve: number;
    safetyMargin: number;
    inputBudget: number;
    triggerTokens: number;
}
export declare class ContextBudgetError extends Error {
    readonly code: string;
    readonly details: Record<string, number>;
    constructor(code: string, details: Record<string, number>);
}
/** This never mutates model metadata or silently reduces the caller's output budget. */
export declare function computeContextBudget(model: Pick<Model<Api>, "contextWindow" | "maxTokens">, policy: ResolvedContextPolicy, explicitMaxTokens?: number, fixedTokens?: number): ContextBudget;
export interface ContextEstimateOptions {
    calibrationFactor?: number;
    /** Complete actual wire wrapping, replacing the generic Context projection. */
    serializedPayload?: string;
    additionalTokens?: number;
    /** Distinct versions for generic Context and each wire wrapping. */
    wrapperKey?: string;
}
export interface ContextEstimate {
    baseTokens: number;
    estimatedTokens: number;
    calibrationFactor: number;
    textBytes: number;
    imageTokens: number;
    imageFallbackCount: number;
    wrapperKey: string;
}
export declare function estimateTextTokens(text: string): number;
/** Observable request inputs only; response usage, timestamps and tool details are not model input. */
export declare function estimateContext(context: Context, options?: ContextEstimateOptions): ContextEstimate;
/** Input calibration is monotone and scoped to the exact provider/model/wrapping tuple. */
export declare class ContextCalibration {
    private readonly factors;
    getFactor(provider: string, model: string, wrapperKey: string): number;
    observe(provider: string, model: string, wrapperKey: string, baseTokens: number, usage: Pick<Usage, "input" | "output" | "cacheRead" | "cacheWrite">): number;
    reset(): void;
}
//# sourceMappingURL=context-budget.d.ts.map