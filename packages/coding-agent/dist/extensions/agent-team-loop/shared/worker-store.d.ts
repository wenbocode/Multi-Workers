export type WorkerStatus = "pending" | "running" | "done" | "failed" | "needs-clarification";
/** Queue-row provenance (D-019/AC-021): `conductor` rows were dispatched by
 * the autopilot conductor, `manual` rows by a PM/TS dispatch. Row membership
 * is decided by this cell plus `taskPath` — never by the `ap-` task-key
 * prefix, which is a false signal on its own (6 measured rows). */
export type WorkerOrigin = "conductor" | "manual";
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
    /** Originating writer; absent on legacy rows (pre-column) and normalised to
     * `manual` by {@link workerOrigin}. */
    origin?: WorkerOrigin;
}
/** Normalise an `origin` cell: only the literal `conductor` is a conductor
 * dispatch; a missing/empty/unknown cell fails closed to `manual` so the
 * `ap-` prefix can never resurrect the old false signal (VC-028). */
export declare function normalizeWorkerOrigin(raw: string | undefined): WorkerOrigin;
/** Provenance of a row, with legacy rows (no column) read as `manual`. */
export declare function workerOrigin(entry: WorkerEntry): WorkerOrigin;
/** Owner project key of a row: the key its `taskPath` is filed under ("" when
 * the path is not under a `.agenticdoc/<key>/workers/` directory). Independent
 * of `origin` — a manual row still groups under its key; it just never holds a
 * conductor slot (VC-028 `fallback=path`).
 *
 * Anchored exactly like `mw_common.worker_path_key`, so the Python reader and
 * the TS writer agree on the owner key of every row. */
export declare function workerOwnerKey(entry: WorkerEntry): string;
/** Unified owner predicate (D-019): does this row hold `key`'s autopilot slot?
 * `origin` decides first — manual/legacy rows own no slot — and a conductor
 * row owns the key its `taskPath` anchors under. */
export declare function workerBelongsToKey(entry: WorkerEntry, key: string): boolean;
export declare class WorkerStore {
    private readonly filePath;
    private readonly lockPath;
    constructor(agenticdocRoot: string);
    readAll(): WorkerEntry[];
    upsert(entry: WorkerEntry): Promise<void>;
    findByKey(taskKey: string): WorkerEntry | undefined;
}
//# sourceMappingURL=worker-store.d.ts.map