import { type ConcurrencyRequest } from "./model-concurrency.ts";
export interface ConcurrencyRow {
    route: string;
    limit: number | null;
    active: number;
    waiting: number;
}
export interface ConcurrencySnapshot {
    rows: ConcurrencyRow[];
    requests: ConcurrencyRequest[];
    error?: string;
}
/** Read-only: malformed state must be visible, never interpreted as zero usage. */
export declare function readConcurrencySnapshot(directory?: string): ConcurrencySnapshot;
export declare function taskQueueStatus(snapshot: ConcurrencySnapshot, taskPath: string, nowMs: number): string;
export declare function renderConcurrencyLines(snapshot: ConcurrencySnapshot, nowMs: number): string[];
//# sourceMappingURL=concurrency-view.d.ts.map