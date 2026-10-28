/**
 * shared/dispatch-card.ts — T-01 dispatch-card envelope contract
 * (key `mw-dispatch-card-gate`, contract C1).
 *
 * SINGLE JUDGEMENT for "is this task card a complete dispatch envelope?".
 * The tool layer (`dispatch_worker` / `/worker`, T-02) and the service layer
 * (`packages/multi-workers/launcher.py::_poll_once`, T-03, a Python mirror of
 * the constants below) both consult this shape, so the two gates cannot drift
 * (design.md §4 G-1/G-3, P-04).
 *
 * Judgement only, never a verdict: `readEnvelope` reports what it found and
 * `typeExtrasMissing` names the type-specific gaps; the caller decides the
 * action (refusal text, failed queue row, ...). No content-quality judgement
 * is made here.
 *
 * Wide-档 section criterion (design.md §6.3, DQ-2): a section counts as
 * present when a heading in its family is matched AND that section has a
 * non-empty body, OR when the whole document carries the family's paragraph
 * semantics. A strict-heading criterion would reject 87.2% of the historical
 * card corpus and 99.4% of the dispatch corpus (P-03: over-blocking is as much
 * a breach as under-blocking).
 *
 * `seedItemsMissing` (T-12/F-05) is the tool-layer seed minimum (AC-002 ①②);
 * `typeExtrasMissing` is the per-type §1.2 criterion both gates share.
 *
 * Vocabulary source: `.agenticdoc/mw-dispatch-card-gate/evidence/research/
 * spec-card-format-corpus-20261012.md` §0.2 (the slot word-frequency table),
 * consumed verbatim; the constants are exported so the Python mirror (T-03)
 * and the card audit (T-06) can lock the same table.
 *
 * Leaf layer: intentionally depends only on `node:fs` (plus the `node:path` /
 * `./paths.ts` allowance of the card). It must not import `pm/**` or
 * `worker/**`, and callers pass a resolved `cardPath` so the module never
 * guesses a project root. The claims section below re-implements the fence
 * state machine of `worker/output-sections.ts` for the same reason instead of
 * importing it (claims design §3.1).
 */
/** The three envelope sections every dispatchable card must carry (§1.1). */
export declare const ENVELOPE_SECTIONS: readonly ["context", "requirements", "deliverables"];
/** Section key union, derived from `ENVELOPE_SECTIONS`. */
export type EnvelopeSection = (typeof ENVELOPE_SECTIONS)[number];
/** Human labels used in refusal text and audit output (design.md §1.1). */
export declare const ENVELOPE_SECTION_LABELS: Readonly<Record<EnvelopeSection, string>>;
/**
 * Per-section detection result. A non-empty string is the evidence that made
 * the section count (`heading:<text>` or `semantics`); `""` means absent. The
 * string shape keeps the frozen `plan.md` interface while remaining truthy /
 * falsy for boolean consumers, and gives the gate something specific to name.
 */
export interface EnvelopeDetected {
    context: string;
    requirements: string;
    deliverables: string;
}
/** `readEnvelope` result (frozen interface, `plan.md` §冻结接口). */
export interface EnvelopeCheck {
    ok: boolean;
    missing: string[];
    /** `type:` value from the card prologue, `""` when the card has none. */
    type: string;
    detected: EnvelopeDetected;
}
/**
 * Ordered heading families. First hit wins, so `交付` outranks the
 * context/requirement families (corpus classification order). Each family is
 * a prefix match after the numbering prefix is stripped, matching the corpus
 * "标题侧（H2 及以下，正文非空的节）用前缀匹配" rule.
 */
export declare const ENVELOPE_HEADING_FAMILIES: ReadonlyArray<readonly [EnvelopeSection, readonly string[]]>;
/** Paragraph-semantic fallback hints, scanned line-wise over the whole text. */
export declare const ENVELOPE_BODY_HINTS: Readonly<Record<EnvelopeSection, RegExp>>;
/** Bullet/field key predicates for the paragraph-semantic fallback. */
export declare const ENVELOPE_BULLET_KEYS: Readonly<Record<EnvelopeSection, RegExp>>;
/** Type-specific extra items every `coding` card must declare (§1.2). */
export declare const CODING_EXTRA_SECTIONS: readonly ["写入允许面", "写入禁止面", "验收命令", "改动历史"];
/** Type-specific extra items every `research` card must declare (§1.2). */
export declare const RESEARCH_EXTRA_SECTIONS: readonly ["唯一证据文件"];
/** Type-specific extra items every `review` card must declare (§1.2). */
export declare const REVIEW_EXTRA_SECTIONS: readonly ["审计目标", "未覆盖面声明"];
/** Extra-item names per type, in reporting order. */
export declare const TYPE_EXTRA_SECTIONS: Readonly<Record<string, readonly string[]>>;
/**
 * Single-source dispatch-role vocabulary (P-08 closure, T-07).
 *
 * Enumerated from the real corpus (probe run 2026-10-12, `.agenticdoc`):
 *   - `tasks/*.md` card prologues: coding 9 / research 1 / vision 0 / 337 none;
 *   - `workers/<task>/task.md` headers: coding 227 / research 94 / review 28 /
 *     vision 1 / 1 missing;
 *   - `trace.log` `[START] ... type=`: coding 983 / research 349 / review 78 /
 *     vision 4 / default 4.
 * plus the code-side aliases the worker runtime and the dispatch role map have
 * always accepted (`verifier`, `reviewer`, `repair`, `phase-writer`,
 * `roadmap-writer`, `rag-research`) and the legacy cli-derived `codex` value
 * T-02 measured hitting `unknown-type:codex` (P-03: over-blocking an in-use
 * value is as much a breach as under-blocking).
 *
 * This ONE tuple is the shared recognition source: `typeExtrasMissing` below
 * (the tool-layer envelope extras) and the worker runtime table in
 * `worker/worker-mode.ts` are locked to it by
 * `test/suite/dispatch-recovery-terminal.test.ts`. Adding a role means changing
 * this tuple once.
 */
export declare const DISPATCH_TYPE_VOCABULARY: readonly ["coding", "review", "research", "rag-research", "vision", "decide_prepare", "verifier", "reviewer", "repair", "phase-writer", "roadmap-writer", "codex"];
/** Is `type` part of the single-source dispatch vocabulary? */
export declare function isKnownDispatchType(type: string): boolean;
/**
 * Known dispatchable roles that carry no envelope extras in this key.
 * Kept as an exported subset of {@link DISPATCH_TYPE_VOCABULARY} for the
 * Python mirror and audit consumers; the extras check now consults the
 * vocabulary directly, so this is descriptive rather than exhaustive.
 */
export declare const TYPES_WITHOUT_EXTRA_RULES: readonly string[];
/**
 * Judge an already-read card body (pure; no fs). Exported so a caller that
 * already holds the text (queue row, corpus scan) shares the exact judgement
 * instead of re-implementing it.
 */
export declare function inspectEnvelope(text: string): EnvelopeCheck;
/**
 * Read a task card and report its envelope status. A missing/unreadable card
 * yields `missing: ["file"]` (all sections absent) so the caller can name the
 * path it was given; every other finding is a normal `ok: false` report.
 */
export declare function readEnvelope(cardPath: string): EnvelopeCheck;
/**
 * Type-specific gaps of `text` for `type`: the item names listed in
 * design.md §1.2 that the card does not declare, `[]` when none. An
 * unrecognised type returns `["unknown-type:<type>"]` so the gate names the
 * role rather than silently passing it. Every role in the single-source
 * `DISPATCH_TYPE_VOCABULARY` (dispatchable roles + the runtime aliases +
 * legacy `codex`) is recognised here and carries no extras in this key.
 *
 * "Declared" is wide on purpose (heading, bullet/field label, or the canonical
 * item name anywhere in the card): the per-type extras exist to catch an
 * omitted contract, not to police wording (P-03).
 */
export declare function typeExtrasMissing(type: string, text: string): string[];
/**
 * The seed four-item acceptance (AC-002 ①②) had no machine judge, so a card
 * that handed the worker no starting anchor passed the tool gate (F-05). The
 * judged minimum is deliberately just two items, both WIDE (P-03):
 *
 *  - a literal `goal.md` reference — the project-level goal anchor; and
 *  - at least one `path:line` reference — a resolvable starting point.
 *
 * The card's own 上下文/要求 sections are delivered verbatim as the seed already,
 * so they need no separate judgement here. This is the tool-layer (G-1)
 * criterion; the service layer re-checks the envelope + type extras on the
 * derived task.md, into which the card context (and so these references) is
 * injected.
 */
export declare const GOAL_ANCHOR = "goal.md";
export declare const SEED_GOAL_ITEM = "seed:goal.md";
export declare const SEED_PATH_ITEM = "seed:path:line";
/** Seed items the card does not declare, `[]` when it declares both. */
export declare function seedItemsMissing(text: string): string[];
/**
 * Self-reported judgement kind of one claim. The classifier never infers the
 * kind (agreement with the corpus is only 63.5%, RQ-3 §2.4); the card declares
 * it and {@link claimsGaps} only checks that the `判据` prefix agrees.
 */
export declare const CLAIM_TYPES: readonly ["cmd", "grep", "struct", "manual"];
/** One member of {@link CLAIM_TYPES}. */
export type ClaimType = (typeof CLAIM_TYPES)[number];
/**
 * `unverified` reason vocabulary (design §2.3). Single source: the Python
 * mirror (`autopilot/dispatch.py`) and the T-06 parity lock read this tuple
 * verbatim. Never write a second copy — the `ESCALATED_REASONS` precedent
 * (`packages/multi-workers/decision_points.py:111-120`) records exactly that
 * drift lesson.
 */
export declare const UNVERIFIED_REASONS: readonly ["budget", "no-access", "not-found", "ambiguous", "environment", "out-of-scope", "awaiting-input"];
/** One member of {@link UNVERIFIED_REASONS}. */
export type UnverifiedReason = (typeof UNVERIFIED_REASONS)[number];
/**
 * Default gate mode (D-006): `advisory` warns only, `enforce` refuses with zero
 * side effects. `MW_CLAIM_GATE=enforce` overrides it at runtime; both sides of
 * the TS/Python pair use the same constant and the same env name.
 */
export declare const CLAIM_GATE_DEFAULT: "advisory";
/**
 * Calibrated read budget of one dispatch unit (RQ-1 §5, D-007): 30 calls,
 * 393,216 B cumulative, from the p90 single-fetch cost (4,854 tokens) and the
 * <400k chars safe band. `perClaim` is the fetch allowance ONE claim buys
 * (D-014: `6 × n`, capped at `callCap`), `hardCap` the floor(177856/4977)
 * ceiling and `claimByteCap` the per-claim byte allowance. The separate `Σ预算`
 * planning weight (`manual` = 2) only prices the card for `claimsGaps`.
 */
export declare const CLAIM_BUDGET: {
    readonly perClaim: 6;
    readonly callCap: 30;
    readonly hardCap: 35;
    readonly claimByteCap: 65536;
    readonly byteCapMax: 393216;
};
/** One parsed claim row of the card's `<!-- mw-claims: v1 -->` block. */
export interface Claim {
    /** Normalized `C-01` / `C-01.3` id. */
    id: string;
    /** Lower-cased self-reported 类型, `""` when the cell or column is absent. */
    type: string;
    /** Parent id of a `C-01.3` child row, `""` for a top-level claim. */
    parent: string;
    statement: string;
    falsifier: string;
    locator: string;
    judgement: string;
    /** Parsed 预算; `Number.NaN` when missing or not a non-negative integer. */
    budget: number;
    /** 1-based line of the row in the parsed text (diagnostics only). */
    row: number;
}
/** Result of {@link parseClaimsBlock}. Never throws (P-048). */
export interface ClaimBlock {
    /** A `<!-- mw-claims: v1 -->` marker was seen outside a fence. */
    present: boolean;
    claims: Claim[];
    /** `claim:<row>:unparsable` findings, row = 1-based source line. */
    errors: string[];
}
/**
 * Parse the card's `<!-- mw-claims: v1 -->` block (design §2.1).
 *
 * Tolerance is the contract, not a nicety (P-048: an over-strict schema caused
 * 30 minutes of consecutive false refusals): the block end falls back to the
 * next H2 or EOF, column order is free, extra columns are ignored, header
 * words take aliases, full-width `：｜`/digits fold to ASCII, and fenced code
 * blocks contribute nothing. An unparsable row is reported as
 * `claim:<row>:unparsable` and skipped — this function never throws.
 */
export declare function parseClaimsBlock(text: string): ClaimBlock;
/** Options of {@link claimsGaps}. */
export interface ClaimsGapOptions {
    /** Absolute project root the `定位` paths resolve against. */
    projectDir: string;
    /** `true` upgrades the advisory findings to gaps (D-006 grey release). */
    enforce: boolean;
}
/**
 * Judge a parsed claims block (design §2.1/§3.1, AC-001). Never throws.
 *
 * Structural gaps (`type` / `statement` / `falsifier` / `locator` /
 * `judgement` / `budget`) are gaps in both modes: a claim missing a required
 * cell is not a claim. The soft findings — `type-prefix`, `cmd-locator`,
 * `locator-unresolved`, `locator-range`, `tautology` and the two `claims:*`
 * aggregates — are returned only when `opts.enforce` is true; an advisory
 * caller gets `[]` for them here and can re-query with `enforce: true` to
 * render the same string list as warnings (D-006: advisory warns, never
 * refuses).
 *
 * Item shapes are frozen because T-02 concatenates them into the refusal text:
 * `claim:<id>:<element>` and `claims:<rule>:<detail>`.
 */
export declare function claimsGaps(block: ClaimBlock, opts: ClaimsGapOptions): string[];
/**
 * Read-scope caps derived from the claims block (design §4, D-014):
 * `fileCap = min(30, perClaim × n)`, `byteCap = min(393,216, 65,536 × n)`.
 * The file cap is a FETCH allowance per claim (6 calls), not the `Σ预算`
 * planning weight: `Σ预算` prices a card (a `manual` claim counts double because
 * it buys PM attention) and is gated at 40 by `claimsGaps`, while the worker
 * needs a read budget that scales with how many claims it must settle —
 * `Σ预算` gave a 5-claim grep card 5 calls and starved it after the 5th
 * (measured, T-07 e2e: `5/5 calls already allowed`).
 * No claims means no derived cap — `{ fileCap: 0, byteCap: 0 }` lets the caller
 * keep the project-level default instead of zeroing a read budget.
 */
export declare function claimBudgetCaps(claims: Claim[]): {
    fileCap: number;
    byteCap: number;
};
//# sourceMappingURL=dispatch-card.d.ts.map