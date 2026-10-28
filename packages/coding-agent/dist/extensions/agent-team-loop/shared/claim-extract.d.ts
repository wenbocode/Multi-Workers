/**
 * shared/claim-extract.ts — E1 structured claim extraction (T-03, key
 * `claim-driven-review-orchestration`; spec AC-E1, design §2.1).
 *
 * A real review card is prose: it has no `<!-- mw-claims: v1 -->` block, so the
 * split path (L0 → L1) needs a machine-checkable coverage list BEFORE a single
 * unit is spawned. E1 is the cheapest rung of stage 0: take rows that already
 * ARE a list (QG findings, spec AC rows, diff hunks, anti-pattern grep hits)
 * and turn them into {@link Claim} rows mechanically — zero LLM, zero reads.
 *
 * Contract (cards T-03 + T-06):
 *   - consumption order is fixed — `findings` → `acRows` → `diffHunks` →
 *     `antiPatternHits` — so ids `C-01`, `C-02`, … are deterministic (2 digits,
 *     3 from the 100th claim on);
 *   - `type` comes from the 判据 prefix only (`cmd:`/`grep:`/`fs:`/`struct:`);
 *     no prefix (and `manual:`) stays `manual`. The kind is never inferred from
 *     the statement (RQ-3 §2.4: the classifier agrees with the corpus 63.5%);
 *   - `falsifier` is a caller cell when the row carries one (trimmed). E1 only
 *     DERIVES a refutation condition for machine-shaped sources and only when
 *     the derived text is executable: an anti-pattern hit refutes itself when
 *     the pattern is not at `path:line`, a hunk when it does not show the
 *     stated change. Prose rows (`findings`/`acRows`) and every `manual` claim
 *     get NO derived falsifier: there E1 says `extract:falsifier-missing:<id>`
 *     and KEEPS the claim (losing it would lose coverage). The validator is
 *     never relaxed for E1: `claimsGaps` keeps reporting `claim:<id>:falsifier`
 *     and this module renames exactly that gap to the one wording above, so a
 *     missing falsifier has one name and cannot throw;
 *   - the 判据 prefix is normalized to the validator's canonical spelling:
 *     `fs:`/`struct:` both become `shape:` (a `struct` claim may only carry
 *     `shape:`), `cmd:`/`grep:`/`manual:` keep their lowercase canonical form.
 *     Unknown prefixes are left alone;
 *   - source-side reconciliation (AC-E1): a row that cannot become a claim is
 *     `extract:lost-source-row:<index>` (0-based, within its own source list),
 *     a 定位 naming a file outside the change face the input declares is
 *     `extract:foreign-locator:<id>`;
 *   - the produced claims are handed to `claimsGaps` and its findings are
 *     passed through verbatim, except the one falsifier rename above — the
 *     validator keeps one implementation (T-06).
 *
 * Pure by construction (P-048: bad input becomes a gap, never a throw): no
 * project file is read, nothing is written, no model is called. `claimsGaps`
 * only `statSync`es 定位 cells, and the default project root is a path nothing
 * creates, so the default result does not depend on the caller's cwd or tree.
 */
import { type Claim } from "./dispatch-card.ts";
/** One prose list row: the shape of a QG finding and of a spec AC line. */
export interface ClaimSourceRow {
    /** 陈述 — what the row asserts. Empty means the row cannot become a claim. */
    text: string;
    /** 定位, copied verbatim (a `path:line`, a symbol, `-`, …). */
    locator: string;
    /** 判据; its prefix picks the claim type. Empty stays empty (a real gap). */
    judgement: string;
    /**
     * 反证条件 supplied by the caller (T-06). T-03's "`falsifier` stays `''`"
     * conflicted with the validator, which treats an empty one as a structural
     * gap; the fix is to carry the caller's text here, not to soften the
     * validator. Prose rows get no derivation: a human verdict cannot be
     * machine-refuted, so a missing cell is reported, never invented.
     */
    falsifier?: string;
}
/** A QG finding row (`findings` source). */
export type ClaimSourceFinding = ClaimSourceRow;
/** A spec AC row (`acRows` source). */
export type ClaimSourceAcRow = ClaimSourceRow;
/** One diff hunk of the change face (the A-class source, spec §2.0). */
export interface ClaimSourceDiffHunk {
    /** Path the hunk touches (repo-relative in practice). */
    path: string;
    /** 1-based first changed line. */
    start: number;
    /** 1-based last changed line (`end >= start`). */
    end: number;
    /** What this hunk is supposed to prove — the caller supplies it, E1 never guesses. */
    statement: string;
    /** 判据; absent keeps the claim `manual` with an empty 判据 (a real gap). */
    judgement?: string;
    /**
     * 反证条件 supplied by the caller (T-06). When absent, a non-`manual` hunk
     * derives {@link HUNK_FALSIFIER}: a hunk that does not show the stated
     * change refutes it, which is executable (re-read the diff).
     */
    falsifier?: string;
}
/** One anti-pattern grep hit. */
export interface ClaimSourceAntiPattern {
    path: string;
    /** 1-based line of the hit. */
    line: number;
    /** The matched anti-pattern; it becomes the claim statement's subject. */
    pattern: string;
    /** 判据; absent keeps the claim `manual` with an empty 判据 (a real gap). */
    judgement?: string;
    /**
     * 反证条件 supplied by the caller (T-06). When absent, a non-`manual` hit
     * derives `在 path:line 处找不到 pattern`: re-grepping that one line is the
     * refutation, so the condition is executable instead of a restatement.
     */
    falsifier?: string;
}
export interface ClaimExtractInput {
    findings?: readonly ClaimSourceFinding[];
    acRows?: readonly ClaimSourceAcRow[];
    diffHunks?: readonly ClaimSourceDiffHunk[];
    antiPatternHits?: readonly ClaimSourceAntiPattern[];
}
/** Options of {@link extractClaims}. */
export interface ClaimExtractOptions {
    /**
     * Root the 定位 paths resolve against. Only `claimsGaps`' soft checks
     * consult it, so it matters only with `enforce: true`; the default cannot
     * resolve any file (extraction must not depend on the caller's cwd).
     */
    projectDir?: string;
    /** D-006 grey switch handed to `claimsGaps`; default `false` (advisory). */
    enforce?: boolean;
}
/** Result of {@link extractClaims}. */
export interface ClaimExtractResult {
    claims: Claim[];
    /**
     * In emission order: `extract:lost-source-row:<index>` in source-row order
     * (lost rows as they are scanned), then `extract:foreign-locator:<id>` in
     * claim order, then the `claimsGaps` findings. A `claim:<id>:falsifier`
     * finding is renamed to `extract:falsifier-missing:<id>` (one wording per
     * problem); every other validator finding passes through verbatim.
     */
    gaps: string[];
    /** Rows the input carried; `sourceRows === claims.length + lost rows`. */
    sourceRows: number;
}
/**
 * E1: rows already shaped like a list → {@link Claim} rows (AC-E1).
 *
 * Consumption order is fixed, ids are positional, and nothing depends on the
 * clock, a random source or the filesystem, so two calls with the same input
 * return deeply equal results (`JSON.stringify` stable). Malformed rows are
 * reported as `extract:lost-source-row:<index>` and skipped instead of throwing.
 */
export declare function extractClaims(input?: ClaimExtractInput, opts?: ClaimExtractOptions): ClaimExtractResult;
//# sourceMappingURL=claim-extract.d.ts.map