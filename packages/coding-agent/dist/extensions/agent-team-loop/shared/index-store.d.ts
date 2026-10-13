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
/** Conductor-side verdict for one claim id (mirror of
 * `packages/multi-workers/autopilot/state.py::claim_state`). `"free"` —
 * empty/placeholder/self; `"live"` — this host, pid alive (the conductor's
 * ONLY skip condition); `"dead"` — foreign host or dead pid; `"stale"` —
 * unparseable (legacy). */
export type ConductorClaimState = "free" | "live" | "dead" | "stale";
/** Liveness verdict the Python conductor uses to decide whether a key's claim
 * blocks dispatch (`conductor.py`: `if claim == state.CLAIM_LIVE: ... continue`).
 *
 * This is deliberately NOT `ui-bridge.ts::claimState`: that one is the
 * takeover guard and conservatively reports a FOREIGN host as `held-live`
 * ("cannot verify liveness"), while the conductor treats a foreign host as
 * `dead` ("conductor-side rule: foreign host is not live"). ORPHANED judgement
 * and the repair path must speak the CONDUCTOR's language, or a key the
 * conductor is happy to drive would be mis-labelled orphaned. */
export declare function conductorClaimState(claimId: string, selfId?: string): ConductorClaimState;
/** Owner evidence LOCAL to a key namespace (T-22 / AC-011): the `_index.parallel`
 * row is gone, but the key itself still carries owner-authored facts. Final,
 * testable predicate (the report quotes this verbatim):
 *
 *   `{agenticdocRoot}/{key}/pm-state.md` has a `- Claim-Id:` or `- Phase:`
 *   line, OR `{agenticdocRoot}/{key}/workers/<task-key>/trace.log` exists (any
 *   depth under `workers/`).
 *
 * The pm-state lines are the framework machine interface (`state-manager.ts` /
 * `advance_phase.py` write them) and `trace.log` is only ever written by a
 * worker that actually ran — both survive a lost index row.
 *
 * A bare directory holding only `task.md` files is NOT owner evidence: there is
 * no fact to reconstruct the row from, so it stays a notice-only case (T-22
 * req. 3). This predicate NEVER reads or writes `_index.parallel`; it only feeds
 * the admission decision — the scan still refuses to write any index row
 * (req. 4), so guessing a row's Phase/ClaimId/Deps is impossible by
 * construction. */
export declare function keyHasOwnerTraces(agenticdocRoot: string, key: string): boolean;
/** Freshness window for a key's own state documents (T-24/C-30): how recently
 * `pm-state.md` / `plan.md` must have moved for a claim-free repair to treat
 * the owner as still present. C-30 measured an `idle` key whose only evidence
 * was a legacy August Claim-Id and whose worker dirs were months old, yet the
 * T-22 widened admission still called it ORPHANED. */
export declare const OWNER_EVIDENCE_FRESH_MS: number;
/** The two key-level state documents a live owner writes (the framework's
 * machine interface for `pm-state.md`, the human plan for `plan.md`). */
export declare function keyStateDocPaths(agenticdocRoot: string, key: string): string[];
/** Verdict of {@link ownerEvidenceCurrent}. */
export interface OwnerEvidenceVerdict {
    /** True when the key's owner looks current enough to repair for (T-24 req. 2). */
    current: boolean;
    /** True when the key publishes at least one of `pm-state.md` / `plan.md`.
     * Such a key has current-state authority: the state documents decide both
     * which tasks are live work and whether the owner is still present. A key
     * with neither document has nothing to narrow against, so the durable
     * owner traces stay the only evidence (T-19/T-22 behaviour). */
    hasStateDocs: boolean;
    /** Machine-ish reason when `current` is false, used verbatim in the notice
     * (`index 状态 idle`, `无 index 行且 pm-state 未近期更新`). */
    reason?: string;
}
/** Is a key's owner evidence still CURRENT (T-24 req. 2)? The repair path used
 * to accept any T-19 index row or T-22 owner trace, so an `idle` key carrying a
 * months-old legacy Claim-Id stayed repairable forever. Evidence is current when
 * ANY holds:
 *
 *   - the key publishes no `pm-state.md` / `plan.md` (nothing to be stale against;
 *     the durable row/trace is the only fact there is, T-19/T-22 semantics);
 *   - a state document moved within {@link OWNER_EVIDENCE_FRESH_MS};
 *   - the index row's status is not `idle` / `done` (an `active` row is a live
 *     owner; `done` is terminal and must not be repaired);
 *   - the row's claim is conductor-`live` (this host, pid alive).
 *
 * Read-only; the caller decides what to do with the verdict. */
export declare function ownerEvidenceCurrent(agenticdocRoot: string, key: string, row: IndexEntry | undefined, now?: number, freshMs?: number): OwnerEvidenceVerdict;
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