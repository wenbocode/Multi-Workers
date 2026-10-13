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
 * guesses a project root.
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
export declare const DISPATCH_TYPE_VOCABULARY: readonly ["coding", "review", "research", "rag-research", "vision", "verifier", "reviewer", "repair", "phase-writer", "roadmap-writer", "codex"];
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
//# sourceMappingURL=dispatch-card.d.ts.map