import type { Api, AssistantMessage, Context, Model, SimpleStreamOptions, Usage } from "@earendil-works/pi-ai";
export declare const NATIVE_SUMMARY_POLICY: {
    readonly minimumOutputTokens: 16384;
    readonly maxAttempts: 2;
    readonly thinking: "off";
    readonly outputGrowth: 2;
};
export interface NativeSummaryAttempt {
    attempt: number;
    maxTokens: number;
    reasoning: "off";
    status: AssistantMessage["stopReason"];
    usage: Pick<Usage, "input" | "output" | "cacheRead" | "cacheWrite"> | null;
    reasoningTokens: number | null;
    textChars: number;
    invalid: boolean;
    providerRequestStarted: boolean;
}
export interface NativeSummaryReport {
    summaryStatus: AssistantMessage["stopReason"];
    invalid: boolean;
    attempts: NativeSummaryAttempt[];
}
/** Retry only summary generation, before native core can persist or replace context. */
export declare function runNativeSummaryPolicy(model: Model<Api>, context: Context, options: SimpleStreamOptions | undefined, produce: (request: Context, requestOptions: SimpleStreamOptions) => Promise<{
    response: AssistantMessage;
    providerRequestStarted: boolean;
}>): Promise<{
    response: AssistantMessage;
    report: NativeSummaryReport;
}>;
//# sourceMappingURL=native-summary-policy.d.ts.map