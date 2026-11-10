export interface ContextCompactionPolicy {
    enabled: boolean;
    triggerRatio: number;
    targetRatio: number;
    keepRecentTokens: number;
    maxSummaryTokens: number;
    timeoutMs: number;
}
export declare const CONTEXT_POLICY_FIELDS: readonly ["maxTokens", "compaction.enabled", "compaction.triggerRatio", "compaction.targetRatio", "compaction.keepRecentTokens", "compaction.maxSummaryTokens", "compaction.timeoutMs"];
export type ContextPolicyField = (typeof CONTEXT_POLICY_FIELDS)[number];
export declare const DELEGATED_CONTEXT_FIELDS: readonly ContextPolicyField[];
export type ContextPolicyScope = "global" | "project";
export interface ContextPolicySource {
    scope: ContextPolicyScope;
    level: "defaults" | "type";
    path: string;
    taskType?: string;
    builtin: boolean;
}
export interface ContextPolicyOverride {
    maxTokens?: number;
    compaction?: Partial<ContextCompactionPolicy>;
}
export interface ContextPolicyDocument {
    version: 1;
    defaults?: ContextPolicyOverride;
    types?: Record<string, ContextPolicyOverride>;
}
export interface ContextPolicyLocation {
    controlRoot: string;
    taskType?: string;
    taskFile?: string;
    homeDir?: string;
}
export interface ResolvedContextPolicy {
    version: 1;
    taskType: string;
    controlRoot: string;
    maxTokens: number;
    compaction: ContextCompactionPolicy;
    sources: Record<ContextPolicyField, ContextPolicySource>;
    paths: {
        global: string;
        project: string;
    };
}
export declare class ContextPolicyError extends Error {
    readonly code: string;
    readonly path: string;
    readonly field: string;
    constructor(code: string, filePath: string, field: string, reason: string);
}
/** Missing files alone use defaults. Malformed or inaccessible files always fail closed. */
export declare function readContextPolicyDocument(filePath: string): ContextPolicyDocument | undefined;
export declare function resolveContextPolicy(options: ContextPolicyLocation): ResolvedContextPolicy;
export interface ContextPolicyUpdate extends ContextPolicyLocation {
    scope: ContextPolicyScope;
    type?: string;
    field: ContextPolicyField | "type";
    value?: number | boolean;
    operation: "set" | "clear";
}
/** A short same-directory lock and atomic replacement preserve unrelated explicit fields. */
export declare function updateContextPolicy(options: ContextPolicyUpdate): Promise<ResolvedContextPolicy>;
//# sourceMappingURL=context-policy.d.ts.map