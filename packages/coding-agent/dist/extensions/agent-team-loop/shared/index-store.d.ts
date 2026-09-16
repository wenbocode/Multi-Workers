export type IndexStatus = "active" | "idle" | "done";
export interface IndexEntry {
    key: string;
    status: IndexStatus;
    phase: string;
    claimId: string;
    deps: string;
    desc: string;
    updated: string;
}
export declare class IndexStore {
    private readonly filePath;
    private readonly lockPath;
    constructor(agenticdocRoot: string);
    readAll(): IndexEntry[];
    upsert(entry: IndexEntry): Promise<void>;
    /** Atomically claim `key` for `self`: liveness check, optional demote of
     * other active rows, upsert, and a post-write disk verification — all
     * under ONE lock acquisition, so racing windows cannot both walk away
     * believing they hold the claim. `heldLive` decides whether a foreign
     * claim blocks us (ui-bridge claimState; injected to keep this store free
     * of host/os dependencies). */
    claim(key: string, self: string, heldLive: (claimId: string) => boolean, opts?: ClaimOptions): Promise<ClaimOutcome>;
    /** Serialize rows back to _index.parallel, preserving AgenticTask header
     * lines. Callers must hold the index lock. */
    private writeRows;
    findByKey(key: string): IndexEntry | undefined;
    /** The currently active row, if any (single-active discipline).
     * Legacy divergence can leave several active rows; the most recently
     * updated one wins (ties: the later row in file order). TS rows carry
     * ISO-UTC `updated` while update_index.py writes local "YYYY-MM-DD HH:MM",
     * so compare via Date.parse rather than lexicographic order. Exposes the
     * full row so callers can also read its claimId (owner resolution must
     * distinguish "our" active row from another live window's). */
    activeEntry(): IndexEntry | undefined;
    activeKey(): string | undefined;
}
export interface ClaimOutcome {
    ok: boolean;
    /** Present when ok=false: the claim that blocked or beat us. */
    blockedBy?: string;
    /** The target row as it stands after the attempt. */
    entry: IndexEntry;
    /** True when the target row was auto-created (key unknown to the index). */
    created: boolean;
}
export interface ClaimOptions {
    /** Stomp a held-live foreign claim on the target key. */
    force?: boolean;
    /** Demote other active rows (single-active discipline). Explicit takeovers
     * want this; quiet re-claims of our own row do not. Default true. */
    demoteOthers?: boolean;
    /** Flip the target row to "active". Quiet re-claims keep the row's status. */
    activate?: boolean;
}
/** Read the degraded-mode `active:` pointer from `_index.md`. Fallback for
 * owner-key resolution when `_index.parallel` has no active row. Returns
 * undefined when the file or the line is missing. */
export declare function readIndexMdActive(agenticdocRoot: string): string | undefined;
//# sourceMappingURL=index-store.d.ts.map