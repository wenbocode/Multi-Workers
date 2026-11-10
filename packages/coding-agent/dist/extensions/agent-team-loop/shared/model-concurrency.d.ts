export interface ConcurrencyRequest {
    id: string;
    pid: number;
    route: string;
    phase: "waiting" | "active";
    createdAt: number;
    project?: string;
    taskPath?: string;
}
export interface ConcurrencyState {
    version: 1;
    limits: Record<string, number>;
    requests: ConcurrencyRequest[];
}
export declare function concurrencyDirectory(): string;
/** Public dispatch prefixes and pi provider IDs must consume the same slots. */
export declare function concurrencyRoute(value: string): string;
export declare function readConcurrencyState(directory?: string): ConcurrencyState;
export declare function setConcurrencyLimit(value: string, limit: number | undefined, directory?: string): Promise<void>;
export interface ConcurrencyWaitOptions {
    directory?: string;
    signal?: AbortSignal;
    waitMs?: number;
    onWait?: () => void;
    project?: string;
    taskPath?: string;
}
/** The lease covers the provider stream, not subsequent local tool execution. */
export declare function acquireModelSlot(value: string, options?: ConcurrencyWaitOptions): Promise<() => Promise<void>>;
export declare function formatConcurrencyState(state: ConcurrencyState): string;
//# sourceMappingURL=model-concurrency.d.ts.map