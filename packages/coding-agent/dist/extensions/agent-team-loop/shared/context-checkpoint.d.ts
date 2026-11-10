import type { Context, Message } from "@earendil-works/pi-ai";
export declare const CONTEXT_CHECKPOINT_TYPE = "mw-context-checkpoint";
export declare const CONTEXT_SUMMARY_FIELDS: readonly ["goal", "constraints", "decisions", "changes", "verification", "remaining"];
export type ContextSummary = Record<(typeof CONTEXT_SUMMARY_FIELDS)[number], string>;
export interface ContextCheckpoint {
    schemaVersion: 1;
    checkpointId: string;
    coveredMessages: number;
    prefixSha256: string;
    summary: ContextSummary;
    provider: string;
    model: string;
    beforeTokens: number;
    afterTokens: number;
}
export interface ContextCheckpointEntry {
    customType?: string;
    data?: unknown;
}
export interface ContextMessageGroup {
    start: number;
    end: number;
}
/** Only fields that can reach a provider: never usage, prices, timestamps or diagnostics. */
export declare function contextMessageSemantics(message: Message): Record<string, unknown>;
export declare function contextPrefixHash(messages: readonly Message[], count: number): string;
export declare function parseContextSummary(value: unknown): ContextSummary | undefined;
/** A group containing tool calls is complete only once every result has arrived. */
export declare function completeContextGroups(messages: readonly Message[], start?: number): ContextMessageGroup[];
export declare function taskAnchorEnd(messages: readonly Message[]): number;
export declare function latestContextCheckpoint(entries: readonly ContextCheckpointEntry[], messages: readonly Message[]): ContextCheckpoint | undefined;
export declare function projectContext(context: Context, checkpoint?: ContextCheckpoint): Context;
//# sourceMappingURL=context-checkpoint.d.ts.map