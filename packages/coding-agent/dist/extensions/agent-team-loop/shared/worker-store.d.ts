export type WorkerStatus = "pending" | "running" | "done" | "failed" | "needs-clarification" | "lost";
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
/** Why a raw queue line could not be read as a row. `cols` = the cell count fell
 * outside the 7..9 window; `task-key` = the first cell is empty. */
export type WorkerLineFailure = "cols" | "task-key";
export interface UnparsableWorkerLine {
    /** 0-based line index inside the queue file (headers and blanks included). */
    index: number;
    line: string;
    reason: WorkerLineFailure;
}
export interface WorkerQueue {
    rows: WorkerEntry[];
    /** Non-empty, non-comment lines that are not readable rows. They are reported
     * here instead of being dropped (AC-023), and the writer re-inserts them
     * verbatim — an unreadable row can never turn into a silent deletion. */
    unparsable: UnparsableWorkerLine[];
    /** `mw-queue:vN` header value; 1 when the queue carries no header. */
    version: number;
}
/** Reads the version header of one raw line, or `undefined` for anything else. */
export declare function parseQueueHeader(line: string): number | undefined;
export declare class WorkerStore {
    private readonly filePath;
    private readonly lockPath;
    constructor(agenticdocRoot: string);
    /** Raw queue lines with the trailing newline dropped; `[]` when the file is
     * absent or empty. Keeping the lines verbatim is what lets {@link upsert}
     * rewrite one row without touching any other byte of the file (AC-023). */
    private readRawLines;
    /** The full queue read: rows, unreadable lines (counted, never dropped) and
     * the declared layout version. Blank lines and `#` comments are neither. */
    readQueue(): WorkerQueue;
    readAll(): WorkerEntry[];
    upsert(entry: WorkerEntry): Promise<void>;
    findByKey(taskKey: string): WorkerEntry | undefined;
}
//# sourceMappingURL=worker-store.d.ts.map