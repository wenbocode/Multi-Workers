export type WorkerStatus = "pending" | "running" | "done" | "failed" | "needs-clarification";
export interface WorkerEntry {
    taskKey: string;
    status: WorkerStatus;
    cli: string;
    provider: string;
    taskPath: string;
    dispatchedAt: string;
    updatedAt: string;
    /** Optional model id passed to the worker CLI (--model/-m). Empty = launcher default. */
    model: string;
}
export declare class WorkerStore {
    private readonly filePath;
    private readonly lockPath;
    constructor(agenticdocRoot: string);
    readAll(): WorkerEntry[];
    upsert(entry: WorkerEntry): Promise<void>;
    findByKey(taskKey: string): WorkerEntry | undefined;
}
//# sourceMappingURL=worker-store.d.ts.map