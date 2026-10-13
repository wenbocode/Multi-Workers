/**
 * worker/output-sections.ts — T-04 recovery contract (AC-003, design §3.2).
 *
 * This is the WRITE-SIDE contract for `output.md`: which sections a worker's
 * report must carry so the PM can recover it, and the broad (宽档) predicate
 * that judges an arbitrary product text against it. It is deliberately distinct
 * from `shared/output-sections.ts`, which is the READ side (splitting an
 * append-only `output.md` into blocks and picking the last non-placeholder one)
 * — same file name, opposite direction, no shared symbols.
 *
 * The five-section shape (design §3.2):
 *   base 4 for every role: 结论 / 证据 / 残留与未验证 / 上下文来源
 *   + 改动清单           for `coding`
 *   + 未覆盖面声明       for `review`
 *
 * The predicate is BROAD on purpose (same style as T-01's envelope word table,
 * `shared/dispatch-card.ts`): a section counts as present when a heading OR the
 * body text hits any alias. Strict heading matching would over-block real
 * reports (spec §8 P-03: "过拦同样违约"), and the historical corpus is the
 * measured proof that strictness misfires (99.4% / 87.2%). The gate is
 * fail-open on vocabulary, fail-closed on the *verdict* — a text that hits none
 * of a section's aliases is missing that section.
 *
 * Migration: this module only answers a question; the caller
 * (`worker/output-writer.ts`) decides when to ask it. Historical task books
 * without a header `type:` are never re-judged (P-07 / P-09).
 */
/** Sections every role's `output.md` must carry (design §3.2). */
export declare const RECOVERY_SECTIONS: readonly ["结论", "证据", "残留与未验证", "上下文来源"];
/** Extra section a role must add on top of `RECOVERY_SECTIONS`. Roles absent
 * from this table carry the base four only. */
export declare const RECOVERY_TYPE_SECTIONS: Readonly<Record<string, readonly string[]>>;
/** Which sections `type` must carry: the base four plus its role extra. */
export declare function recoverySectionsFor(type: string | undefined): string[];
export interface RecoveryVerdict {
    /** True when every required section is present. */
    ok: boolean;
    /** Required sections with no alias hit, in contract order. Empty iff `ok`. */
    missing: string[];
    /** The full required list for the given type (diagnostic/tests). */
    required: string[];
}
/**
 * Judge an agent-authored product text against the recovery contract.
 *
 * `text` is the agent's report (what `output.md` already carries, or the final
 * reply) — never the harness block the writer appends afterwards. `type` is the
 * header `type:` of the dispatch; `undefined` (legacy/manual task book) yields
 * the base four, and the caller is responsible for only asking at all when the
 * dispatch is forward (see `worker/output-writer.ts`).
 *
 * Never throws: any string (including empty) yields a verdict.
 */
export declare function checkRecovery(text: string, type: string | undefined): RecoveryVerdict;
//# sourceMappingURL=output-sections.d.ts.map