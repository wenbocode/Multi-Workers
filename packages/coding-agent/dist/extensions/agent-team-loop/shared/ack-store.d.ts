/**
 * Sidecar store for worker-task acknowledgements (mw-widget-terminal-lifecycle
 * T-01, AC-004/VC-004 — storage half only).
 *
 * Backs `.agenticdoc/_workers.acked`: one `taskKey | ackedAtIso` row per
 * acked task. Writes take the shared workers lock (`.mw/workers.lock`, the
 * same lock WorkerStore uses) and swap the file atomically via tmp + rename,
 * so concurrent PM windows never observe a torn file. The /mw ack channel and
 * its terminal-state validation live in T-07; this class is pure storage.
 */
export declare class AckStore {
    private readonly filePath;
    private readonly lockPath;
    constructor(agenticdocRoot: string);
    /** taskKey -> ackedAt (UTC ISO). Missing file yields an empty map; `#`
     * comment lines and malformed rows are skipped. */
    readAll(): Map<string, string>;
    /** Ack taskKeys: hold the workers lock, read-merge-write via tmp + rename.
     * Idempotent — re-acking a key overwrites its timestamp. Returns the keys
     * actually written plus the keys rejected by taskKey validation (empty or
     * containing `|`); rejected keys never touch the file. */
    ack(taskKeys: string[]): Promise<{
        acked: string[];
        rejected: string[];
    }>;
}
//# sourceMappingURL=ack-store.d.ts.map