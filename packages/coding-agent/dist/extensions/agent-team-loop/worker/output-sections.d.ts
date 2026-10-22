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
 *
 * The T-04a verdict-table half at the bottom is the same shape of contract for
 * the L3 layer: `parseVerdictTable` reads the agent-authored `## 断言裁决`
 * table and `claimCoverage` judges it against the card's claim set. Both are
 * pure (plus `statSync`/line counts for evidence refs) and never throw.
 */
import { type Claim } from "../shared/dispatch-card.ts";
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
/** One parsed `## 断言裁决` row, all cells trimmed (never normalized away: the
 * raw cell text is what the diagnostics quote). */
export interface VerdictRow {
    /** `C-01` / `C-01.3` id, upper-cased. */
    id: string;
    /** `类型` cell, lower-cased, `""` when the column is absent. */
    type: string;
    verdict: string;
    finding: string;
    evidence: string;
    fetches: string;
    reason: string;
    /** 1-based line of the row in the parsed text (diagnostics only). */
    row: number;
}
/** Result of {@link parseVerdictTable}. Never throws (P-048). */
export interface VerdictTable {
    /** The `## 断言裁决` H2 was seen outside a fence. */
    present: boolean;
    rows: VerdictRow[];
    /** `claim:<row>:unparsable` findings, row = 1-based source line. */
    errors: string[];
}
/**
 * Parse the agent-authored `## 断言裁决` table (RQ-3 §5.1/§5.6).
 *
 * Tolerance is the contract (P-048): the heading may carry a suffix, column
 * order is free, extra columns are ignored, header words take both scripts,
 * full-width `：｜`/digits fold to ASCII, and fenced code blocks contribute
 * nothing (the same fence state machine `h2Headings` uses). A row whose
 * `claim` cell is not a claim id is reported as `claim:<row>:unparsable` and
 * skipped; this function never throws.
 */
export declare function parseVerdictTable(text: string): VerdictTable;
/** Options of {@link claimCoverage}. `projectDir` is the root the evidence path
 * refs resolve against (the launcher's cwd in production, a fixture in tests). */
export interface ClaimCoverageOptions {
    projectDir?: string;
}
/**
 * Judge the `## 断言裁决` table against the card's claim set (RQ-3 §5, B-1/B-4/
 * B-10). Every returned string is one frozen criterion; the string IS the
 * diagnostic, so no second vocabulary is introduced.
 *
 * Criteria (in emission order):
 *   `claims:missing-table`            no `## 断言裁决` H2 at all
 *   `claim:<id>:missing-row`          a card claim the table never adjudicates
 *   `claims:extra-row:<id>`           a table row the card never declared
 *   `claim:<id>:verdict`              `裁决` outside closed|partial|unverified
 *   `claim:<id>:finding`              `判定` outside 成立|不成立|无法判定
 *   `claim:<id>:verdict-finding`      the two columns disagree (§5.1 mapping)
 *   `claim:<id>:evidence`             no evidence for closed/partial, or a ref
 *                                     that is unparsable / missing on disk /
 *                                     past EOF / wider than 200 lines
 *   `claim:<id>:reason`               `unverified` without a 7-word reason
 *   `claim:<id>:self-evidence`        every ref is `report*`/output/progress/task
 *   `claim:<id>:struct-held`          a `struct` row counted as `closed` (B-10)
 *   `claim:<id>:budget`               `取数` not a count, or > min(Σ预算, 30)
 *   `claim:<id>:tautology`            T-01's B-5 tautology judge fired
 *
 * Never throws. A claim-free card returns `[]` (nothing to adjudicate), and a
 * table-only run without claims is likewise not judged.
 */
export declare function claimCoverage(claims: Claim[], table: VerdictTable, opts?: ClaimCoverageOptions): string[];
//# sourceMappingURL=output-sections.d.ts.map