/**
 * worker/output-sections.ts — T-05 recovery contract (AC-001/AC-003/AC-014,
 * design §4.1).
 *
 * This is the WRITE-SIDE contract for a worker's product text (`output.md` /
 * `report.md` / `report-<slug>.md`, in the AC-015 candidate order): which
 * sections the report must carry so the PM can recover it, and the H2-heading
 * predicate that judges that text. It is deliberately distinct from
 * `shared/output-sections.ts`, which is the READ side (splitting an
 * append-only `output.md` into blocks and picking the last non-placeholder one)
 * — same file name, opposite direction, no shared symbols.
 *
 * The five-section shape (design §3.2):
 *   base 4 for every role: 结论 / 证据 / 残留与未验证 / 上下文来源
 *   + 改动清单           for `coding`
 *   + 未覆盖面声明       for `review`
 *
 * Judgement (design §4.1, H2 档): the haystack is ONLY the H2 heading text —
 * every line matching ` {0,3}##(?!#)[ \t]+` outside fenced code blocks and
 * outside blockquotes — normalized by stripping trailing `#`, trimming,
 * collapsing internal whitespace and ASCII-lowering. A section is present when
 * one of its 45 aliases is a substring of some heading. Body text never
 * participates (that is what closed the FW-001 self-witness hole, where the
 * framework's own `## Recovery Gaps` paragraph naming `上下文来源` made the
 * missing section read as satisfied). The vocabulary stays fail-open (a heading
 * may use any alias) while the verdict is fail-closed (a required section with
 * no heading hit is missing). No punctuation stripping; `###` is not an H2.
 *
 * AC-014 (corrected attribution): this file used to justify its whole-text
 * predicate with `99.4% / 87.2%`. Those numbers belong to a DIFFERENT contract
 * — the dispatch-envelope/card compliance stats of `mw-dispatch-card-gate`
 * (341/343 = 99.4%, `evidence/research/spec-dispatch-input-format-20261012.md:142`;
 * 301/345 = 87.2%, `spec-card-format-corpus-20261012.md:281`) — and must not be
 * cited as this contract's evidence (`.agenticdoc/_framework-reflect.md`
 * FW-001 修法 5, corrected 2026-10-14). The honest reason the vocabulary is
 * broad is historical: the old contract did not require headings, and
 * historical products are never an acceptance object (R1). This contract's own
 * measured background is 145/433 = 33.5% whole-text vs 35/433 = 8.1%
 * heading-only (spec-rq1-contract-corpus-20261014.md), recorded as background
 * only.
 *
 * Migration: this module only answers a question; the caller decides when to
 * ask it (`worker/output-writer.ts`, `worker/worker-mode.ts`). Historical task
 * books without a header `type:` are never re-judged (P-07/P-09).
 */
/** Sections every role's product must carry (design §3.2). */
export declare const RECOVERY_SECTIONS: readonly ["结论", "证据", "残留与未验证", "上下文来源"];
/** Extra section a role must add on top of `RECOVERY_SECTIONS`. Roles absent
 * from this table carry the base four only. */
export declare const RECOVERY_TYPE_SECTIONS: Readonly<Record<string, readonly string[]>>;
/** The card-declared report roles whose `task.md` carries the S2 contract
 * checklist (`recoveryContractSection`). Mirror of
 * `packages/multi-workers/autopilot/dispatch.py::RECOVERY_CONTRACT_TYPES`
 * (`test_mwoc_s2_sections.py::test_recovery_tables_match_the_ts_source` locks
 * the two tables above against this file; the TS scope constant is the TS
 * mirror of the Python one). */
export declare const RECOVERY_CONTRACT_TYPES: readonly string[];
/** Fixed heading of the injected checklist section (mirror of the Python
 * `dispatch.RECOVERY_CONTRACT_HEADING`). */
export declare const RECOVERY_CONTRACT_HEADING = "## \u4EA4\u4ED8\u6BB5\u5951\u7EA6\uFF08\u672C\u89D2\u8272\uFF09";
/**
 * Sections the framework is allowed to fill mechanically (R2 hard constraint):
 * `上下文来源` is derivable from facts the framework already holds (the task's
 * `card_path` / `card_sha256`, its own read-tool events, the product path), so
 * an I2 backfill may append it. Every other section — `结论`, `证据`,
 * `残留与未验证`, `改动清单`, `未覆盖面声明`, and `## Questions` — is a
 * substantive judgement and is NEVER auto-generated; a whitelist (not a
 * blacklist) so a future section cannot be auto-filled by accident.
 */
export declare const MECHANICAL_SECTIONS: readonly string[];
/** True when `name` is on the mechanical-backfill whitelist (R2). */
export declare function isMechanicalSection(name: string): boolean;
/** Which sections `type` must carry: the base four plus its role extra. */
export declare function recoverySectionsFor(type: string | undefined): string[];
/**
 * The `## 交付段契约（本角色）` block for `task_type`, or `""` outside
 * `RECOVERY_CONTRACT_TYPES`. Every required section is rendered as a copyable
 * `- \`## <段名>\`` line so the worker can paste the canonical heading the
 * settle judge looks for — never an invented alias. Byte-shape mirror of
 * `dispatch.py::recovery_contract_section` so the two producers inject the same
 * section (idempotent on re-application).
 */
export declare function recoveryContractSection(type: string | undefined): string;
/**
 * The normalized H2 headings of `text`, in document order (design §4.1).
 * Fenced code blocks and blockquote lines contribute nothing; `###` is not an
 * H2. Exported for the AC-001 8-case matrix and for tests that lock the
 * normalization.
 */
export declare function h2Headings(text: string): string[];
export interface RecoveryVerdict {
    /** True when every required section is present. */
    ok: boolean;
    /** Required sections with no H2 heading hit, in contract order. Empty iff `ok`. */
    missing: string[];
    /** The full required list for the given type (diagnostic/tests). */
    required: string[];
}
/**
 * Judge an agent-authored product text against the recovery contract.
 *
 * `text` is the agent's report (what `report.md` / `output.md` already carries,
 * or the final reply) — never the harness block the writer appends afterwards.
 * `type` is the header `type:` of the dispatch; `undefined` (legacy/manual task
 * book) yields the base four, and the caller is responsible for only asking at
 * all when the dispatch is forward (see `worker/output-writer.ts`).
 *
 * Never throws: any string (including empty) yields a verdict.
 */
export declare function checkRecovery(text: string, type: string | undefined): RecoveryVerdict;
//# sourceMappingURL=output-sections.d.ts.map