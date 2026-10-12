/**
 * shared/output-sections.ts — AC-010 read-side section reader (contract C7).
 *
 * `output.md` is append-only across runs (D-117: `output-writer.ts` merges a
 * new harness block below a `---` separator instead of clobbering the file), so
 * a task dir that was spawned N times carries N `## TL;DR` / `## Summary`
 * blocks: an early crash block is a placeholder while the real report sits in a
 * LATER block. The generic `readOutputSection` (`pm/ui-bridge.ts`) is a
 * first-match reader and is pinned by frozen tests, so it must keep returning
 * the first block; the terminal widget needs the opposite: the LAST block that
 * is not a placeholder.
 *
 * "Non-placeholder" is deliberately NOT a second oracle. The 15/16 literal
 * placeholder strings and their exact match rule live in
 * `shared/deliverable-evidence.ts` (AC-006, contract C5) and are imported here
 * — that module's header explicitly names this file as the intended consumer.
 * The two readers therefore share one placeholder set, and `readTerminalDetail`
 * picks the last non-placeholder block while `hasDeliverableEvidence` accepts
 * "any non-placeholder block" (spec §3.1 step 2, [REVISED @ 2026-10-11]). Same
 * predicate, opposite direction over the same list.
 *
 * NOTE on the byte-threshold heuristic raised in the task card
 * (`isPlaceholderSection` "or < 32 B"): it is intentionally NOT applied. A
 * shorter-than-32-B product body is still a real product — the frozen VC-009
 * fixture `## TL;DR\n\nall tests green\n` (14 B) must keep yielding
 * `readTerminalDetail(dir, "done") === "all tests green"`
 * (`test/extensions/agent-team-loop.test.ts:2696`), and VC-007's nested
 * `## Exit Reason\n\n## 预算耗尽（wall）` (27 B) must keep yielding
 * `"预算耗尽（wall）"` (`:2661`). A threshold would turn both into placeholders
 * and break AC-010's "single block unchanged" requirement (VC-044). It would
 * also fork the AC-006 oracle: a short delivered body would be `delivered` to
 * `hasDeliverableEvidence` but invisible to the widget. The corpus minimum for a
 * real TL;DR/Summary body is 53 B (`mwg-qg-review-20261010`), so the shared
 * literal set alone already covers every historical stub.
 */
export { DELIVERABLE_PLACEHOLDERS, isPlaceholderBody } from "./deliverable-evidence.ts";
/** One `## <title>` section of an `output.md` file. */
export interface OutputSectionBlock {
    /** Heading text with the leading `##` and surrounding whitespace removed. */
    title: string;
    /** Body lines between this heading and the next one, with the harness
     * `---` block separator removed and the result trimmed. */
    body: string;
    /** 1-based line number of the heading in the source text. */
    startLine: number;
}
/** All `## <title>` sections of `text`, in file order (contract C7). Never
 * throws; an empty/heading-less text yields an empty array. */
export declare function readOutputSections(text: string): OutputSectionBlock[];
/**
 * Is this section body a harness placeholder (contract C7)? Blank bodies and
 * every literal in the AC-006 oracle count. `title` is part of the C7 signature
 * and reserved for future section specialisation; the current oracle is
 * section-agnostic (`deliverable-evidence.ts`), so the read side must not invent
 * a stricter per-section rule — that would be the second oracle the spec
 * forbids.
 */
export declare function isPlaceholderSection(_title: string, body: string): boolean;
/**
 * The LAST non-placeholder section of `text` (contract C7 / AC-010). With no
 * `titles`, scans all blocks from the file end backwards (the card's "从末块向
 * 前取首个非占位块"). With `titles`, they are a priority list: the last
 * non-placeholder block for the first title that has one wins — used by the
 * done row as `["TL;DR", "Summary"]` so a legacy TL;DR-less file still falls
 * back to its Summary. Returns `undefined` when every candidate is a
 * placeholder (the caller then takes its pre-existing degraded path).
 */
export declare function readLastProductSection(text: string, titles?: readonly string[]): OutputSectionBlock | undefined;
/**
 * File-reading convenience for `readTerminalDetail`'s four read points: the body
 * of the last non-placeholder section among `titles` in `<taskDir>/output.md`,
 * or `undefined` when the file/section is missing or placeholder-only. Reading
 * failures (missing file, permission) degrade to `undefined`, never throw.
 */
export declare function readLastProductSectionBody(taskDir: string, titles: readonly string[]): string | undefined;
//# sourceMappingURL=output-sections.d.ts.map