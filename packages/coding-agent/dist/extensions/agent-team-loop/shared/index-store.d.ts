export type IndexStatus = "active" | "idle" | "done";
/** Reserved `.agenticdoc/` root entries that name framework files/dirs, not
 * AgenticTask key namespaces: the 12 names from RQ-5 plus `_impl_gate.log`
 * (`shared/implementation-gate.ts` writes it) and `_incidents`. This is an
 * EXPLICIT list, deliberately not a `_`/`.` prefix rule (the pre-AC-006
 * exemption): a prefix rule would also exempt `_tmp`, `.mw` and
 * `_index.parallel` from the cross-key guard and let a dispatch with
 * `key: _index.parallel` create `.agenticdoc/_index.parallel/workers/`. */
export declare const RESERVED_INDEX_NAMES: readonly string[];
/** Lower-cased membership set of {@link RESERVED_INDEX_NAMES} (stored names
 * are lower-case; compare through {@link normalizeKey}). */
export declare const RESERVED_INDEX_NAME_SET: ReadonlySet<string>;
/** Comparison form of a key: trimmed and lower-cased. Windows filesystems are
 * case-insensitive, so `MW-KEY` and `mw-key` name the SAME directory — the key
 * namespace must be case-insensitive too (A6). Reads normalize; writes keep
 * the first-seen casing so existing `_index.parallel` bytes are never
 * rewritten by a read (no migration). */
export declare function normalizeKey(key: string): string;
/** True for `_scratch` and its case variants — the only reserved name that is
 * still usable as an owner key (never as a claimable/advanceable key). */
export declare function isScratchKey(key: string): boolean;
/** Stable machine code + human message of a refused key name. */
export interface KeyNameRefusal {
    code: string;
    message: string;
}
/** Shape + reserved-name gate shared by the cross-key guard, `IndexStore.claim`
 * and `advance_phase` (AC-006/DD-07a/DD-07b): `null` = usable key name. Every
 * other return refuses the name unconditionally, independent of claim state,
 * so no caller can bootstrap a namespace next to a framework file. */
export declare function keyNameRefusal(key: string): KeyNameRefusal | null;
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
    /** Present when ok=false and the refusal was the key NAME itself (AC-006):
     * stable {@link keyNameRefusal} code (`reserved-key-name`,
     * `key-illegal-shape`, `key-path-escape`, `empty-key`). */
    refusal?: string;
    /** Present when ok=true and the request hit an existing row that differs
     * from it only by case (A6): the stored, first-written spelling. The claim
     * resolves to that row -- this field exists so the substitution is auditable
     * rather than silent. */
    caseVariantOf?: string;
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