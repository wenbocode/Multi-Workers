export type SummaryFailureCategory = "quota" | "rate_limit" | "auth" | "context" | "network" | "unknown";
export interface SummaryFailure {
    category: SummaryFailureCategory;
    httpStatus?: number;
    errorType?: (typeof ERROR_TYPES)[number][0];
}
declare const ERROR_TYPES: readonly [readonly ["insufficient_quota", "quota"], readonly ["quota_exceeded", "quota"], readonly ["rate_limit_exceeded", "rate_limit"], readonly ["invalid_api_key", "auth"], readonly ["authentication_error", "auth"], readonly ["permission_denied", "auth"], readonly ["context_length_exceeded", "context"], readonly ["ECONNRESET", "network"], readonly ["ECONNREFUSED", "network"], readonly ["ETIMEDOUT", "network"], readonly ["ENOTFOUND", "network"]];
/** Fixed fields, bounded scanning, and enum-only output: never serialize upstream objects. */
export declare function projectSummaryFailure(value: unknown): SummaryFailure;
export {};
//# sourceMappingURL=context-summary-diagnostics.d.ts.map