/**
 * pm/review-split-plan.ts — the `plan`-tier composer of the claim-driven review
 * split (card T-10, key `claim-driven-review-orchestration`; design §2.2, spec
 * AC-S2).
 *
 * `plan` means: produce the split manifest and ONE receipt line, dispatch
 * nothing, create no unit directory, write no queue row. `on` is the same plan
 * plus the dispatch of `k` unit cards, so the plan is the whole difference the
 * operator can inspect before committing to a split — it must be visible and
 * reversible (`.agenticdoc/goal.md`).
 *
 * One function wires the four parts together, nothing else:
 *
 *   source list  →  `extractClaims` (degraded path only)  →  `packClaims`
 *                →  `buildSplitManifest`  →  receipt line
 *
 * Source list, in order, first non-empty wins:
 *   1. the card's `<!-- mw-claims: v1 -->` block (`parseClaimsBlock`), used
 *      verbatim when it yields ≥1 claim — a card that already carries machine
 *      claims is never re-derived;
 *   2. deterministic downgrade: the entries of the ask sections. A `## …`
 *      heading qualifies when, parenthetical supplements removed, it CONTAINS
 *      one of `要求` / `审计目标` / `检查项` / `必须覆盖` / `验收` — that is what
 *      makes `## 要求（…对应 AC-001..005）` and `## 必须覆盖的 10 项对抗探针`
 *      ask sections too (card T-13 item 4). An entry is a list item (behaviour
 *      unchanged) or one blank-line-separated prose paragraph of the section
 *      (card T-13 item 5). Each entry derives its claim(s) in this order, first
 *      hit wins:
 *        a. the entry carries a `path:line` / `path:a-b` locator → one
 *           `findings` row with `judgement: "manual: <first 80 chars>"`;
 *        b. the entry names an AC range (`AC-001 到 AC-013`, `AC-001..005`,
 *           separators 到/至/~/～/../-/–/—) → ONE `acRows` row PER id,
 *           ascending, both ends included, at most
 *           {@link PLAN_AC_RANGE_LIMIT} ids per range
 *           (`extract:range-truncated:<total>` when cut): "每条 AC 都要给判定"
 *           is exactly the conservation the merge gate checks, so a range is
 *           never collapsed into one claim;
 *        c. the entry names one `AC-<nnn>` → one `acRows` row;
 *        c'. the entry names NO AC at all → the AC set of its section heading is
 *           its default scope (card T-13 item 6): `## 要求（…对应 AC-001..005）`
 *           makes every bare item of that section cover AC-001..AC-005, expanded
 *           exactly like b./c.;
 *        d. nothing above → the entry is an unmapped ask.
 *
 *      Every 定位 that reaches `extractClaims` — the inline one of (a.) and the
 *      one the AC index resolves — first passes {@link canonicalizeLocator}.
 *      The pack unit is a 定位 CLUSTER, so the same card composed directly
 *      (`spec.md:42`) and through the gate (`.agenticdoc/<key>/spec.md:42`) must
 *      produce the same clusters: otherwise `units` depends on how a path is
 *      spelled (`evidence/m1-exit-probe-20261022.md` §6.1 defect 1). The
 *      claims-block path above keeps its cells verbatim (AC-005).
 *      An AC row's 定位 is `acIndex[id]` and its 判据 `manual: <summary>
 *      [<id>]`: that is the deterministic bridge from the measured card shape
 *      where the 定位 lives in 上下文/被审对象 while the ask lives in
 *      要求/审计目标 (`evidence/m1-exit-probe-20261022.md` — three of four real
 *      review cards scanned `units=0 claims=0`). An id the index cannot resolve
 *      yields no claim, only `extract:ac-unresolved:<id>`. A card where NO item
 *      produces a claim yields `units=0` + `extract:no-source` instead of an
 *      invented claim.
 *
 * L0 measures ASK COVERAGE, not claim count: `asks` = every scanned list item,
 * `mapped` = how many items produced at least one claim, `unmapped` = one
 * truncated summary per item that produced none, so
 * `asks - mapped === unmapped.length` holds in EVERY branch (the no-source
 * branch included) by construction. `claims` is free to EXCEED `mapped`: one
 * "判 AC-001..AC-013" item is ONE covered ask and THIRTEEN claims.
 *
 * Receipt (frozen wording, so later stages can grep it):
 *
 *   [review-split] mode=<plan|on> units=<K> claims=<n> cap=<parentFileCap> \
 *     capSum=<Σ unit fileCap> inflation=<ratio 2dp> l0=<mapped>/<asks> \
 *     fals=<n> l1=<ok|gaps:n>
 *
 * `fals` counts `extract:falsifier-missing:<id>`: AC-derived claims are `manual`
 * by construction, so the falsifier gap is the normal state of a prose card and
 * gets its own field. `l1` counts `packGaps.length + manifestGaps.length` — the
 * STRUCTURAL gaps of packing and manifest only, never the falsifier gaps, the
 * manifest being self-checked by `verifySplitManifest`: a content gap must not
 * pin `l1` to a non-`ok` value forever (card T-13 item 7). The no-source plan keeps the same
 * field set and appends ` gap=no-source` — the marker the card requires, in the
 * only place a receipt can carry it without losing `cap`/`inflation`.
 *
 * Pure by construction (P-048): no file is read or written (the caller-supplied
 * `projectDir` is carried for the dispatch link of T-11, never consulted here),
 * no model is called, no clock/random source is touched, and nothing throws —
 * a programming error in the composition degrades to a `split:plan-failed:<m>`
 * gap with `units=0`.
 */
import { type Claim } from "../shared/dispatch-card.ts";
import { type SplitManifest, type SplitManifestL0 } from "../shared/split-manifest.ts";
/** Input of {@link planReviewSplit}. `mode` is validated by the caller
 * (`off` never reaches the composer, design §2.2). */
export interface ReviewSplitPlanInput {
    /** Parent task key; unit keys are `<taskKey>-u<k>` (`workers/<...>`). */
    taskKey: string;
    /** Project root, carried for the dispatch link (T-11). Not read here. */
    projectDir: string;
    /** Parent card text: the claims source AND the value of `parentSha256`. */
    cardText: string;
    mode: "plan" | "on";
    /**
     * AC id → its 定位 (`spec.md:42`), the deterministic bridge of card T-12:
     * an ask item that only names an AC id still gets a 定位. Optional; a card
     * without an index degrades to `extract:ac-unresolved:<id>` instead of a
     * guessed locator.
     */
    acIndex?: Record<string, string>;
}
/** Result of {@link planReviewSplit}: one receipt line plus the manifest. */
export interface ReviewSplitPlan {
    mode: "plan" | "on";
    /** The `[review-split] …` line (frozen wording, see the module doc). */
    receipt: string;
    /** Absent when there is no source list (`extract:no-source`). */
    manifest?: SplitManifest;
    /** `serializeSplitManifest(manifest)`; absent with the manifest. */
    manifestText?: string;
    /**
     * L0 ask coverage, ALWAYS present: the no-source branch builds no manifest,
     * so `asks - mapped === unmapped.length` would be uncheckable from the
     * receipt alone (the T-10 bug this field closes).
     */
    l0: SplitManifestL0;
    /** `extract:*` then `split:*` gaps, in that order. Never a throw. */
    gaps: string[];
}
/** Gap of a card with no claim source at all — never invented claims. */
export declare const PLAN_NO_SOURCE_GAP = "extract:no-source";
/** Seven columns of the unit card's claims table (`parseClaimsBlock` aliases). */
export declare const UNIT_CARD_COLUMNS: readonly string[];
/**
 * Canonical form of a 定位: `basename:line[-end]` (card T-13 item 1).
 *
 * A split unit is a CLUSTER of claims sharing a 定位 token, so the same card
 * used to split differently depending on how the path was spelled — composed
 * directly `units=8`, through the gate `units=12` (`evidence/m1-exit-probe-20261022.md`
 * §6.1 defect 1). Every 定位 that reaches `extractClaims` therefore passes
 * through here first: directories, the `.agenticdoc/<key>/` prefix and
 * backtick/whitespace padding are dropped, only the file name and the line
 * range survive (`path/a.ts:3-5` → `a.ts:3-5`, `.agenticdoc/x/spec.md:42` →
 * `spec.md:42`). A cell naming no file (a bare symbol, `-`) keeps its normal
 * form, so nothing is invented for it.
 *
 * The claims-block path is NOT canonicalized: those cells are the parent's own
 * bytes and AC-005 forbids rewriting them.
 */
export declare function canonicalizeLocator(locator: string): string;
/**
 * The unit card body: the unit's claims as a `<!-- mw-claims: v1 -->` seven
 * column table, every cell copied verbatim from the parent claim row (ids,
 * types, statements, falsifiers, locators, judgements, budgets are never
 * rewritten — AC-005 forbids normalization). The body re-parses to the same
 * claims through `parseClaimsBlock`, which is what makes the unit card
 * self-describing for the dispatcher and the merge gate.
 */
export declare function serializeUnitCardText(input: {
    taskKey: string;
    claims: readonly Claim[];
}): string;
/**
 * Plan the claim-driven split of ONE review card: source list → extract
 * (degraded path only) → pack → manifest → receipt.
 *
 * Pure and total (P-048): nothing is read from disk, nothing is written, no
 * model is called, and no input shape throws — an empty card, a card without a
 * source list, or a composition error all come back as a `units=0` plan with
 * the gap that explains it.
 */
export declare function planReviewSplit(input: ReviewSplitPlanInput): ReviewSplitPlan;
//# sourceMappingURL=review-split-plan.d.ts.map