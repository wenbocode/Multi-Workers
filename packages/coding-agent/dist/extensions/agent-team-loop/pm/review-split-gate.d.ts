/**
 * pm/review-split-gate.ts — the `plan`-tier dispatch short-circuit (card T-11,
 * key `claim-driven-review-orchestration`; design §2.2, spec AC-S2).
 *
 * The `plan` tier promises "visible, reversible, ZERO side effects": produce
 * the split manifest plus ONE receipt line and dispatch nothing. Both dispatch
 * entries in `pm/ui-bridge.ts` write the task directory/task.md
 * (`writeDispatchTaskMd`) and then the queue row (`dispatchTask`), so the
 * short-circuit has to sit BETWEEN `readDispatchCard` and
 * `writeDispatchTaskMd` — earlier refusals would lose the card verdict, later
 * ones would already have created `workers/<taskKey>/` and a `_workers.parallel`
 * row (GC-3).
 *
 * What this gate may write: exactly one file,
 * `<agenticdocRoot>/<ownerKey>/evidence/split/review-<taskKey>-manifest.json`
 * (`mkdirSync` + `.tmp` + `rename`). It never creates `workers/<taskKey>/`,
 * never writes a `task.md`, and never touches a queue file — those bytes are
 * the difference between `plan` and `on`.
 *
 * What this gate may READ: the card (once) and
 * `<agenticdocRoot>/<ownerKey>/spec.md` (at most once, only to build the AC
 * index of card T-12 — an absent spec is an empty index, never an error). No
 * other file, no command, no model call.
 *
 * `off` and `on` are not this module's business: `off` returns `null` (the
 * dispatch proceeds byte-identically, AC-007) and `on` is a later stage.
 *
 * Total by construction (P-048): nothing here throws. A card that cannot be
 * read, an unwritable manifest directory, or any unexpected error degrades to
 * `[review-split] mode=plan error=<code>` so the dispatch is still stopped (the
 * mode was `plan`) and the operator sees why. A non-`review` card and a card of
 * an unreadable type return `null` silently — the gate only speaks for review
 * cards, and a `coding` dispatch under `plan` keeps today's behaviour.
 */
/** Directory of the split evidence, relative to the owner key (design §2.3). */
export declare const REVIEW_SPLIT_MANIFEST_DIR = "evidence/split";
/** The only card type the `plan` gate splits. */
export declare const REVIEW_SPLIT_CARD_TYPE = "review";
/** File (under the owner key) the AC index is read from — the ONLY other read. */
export declare const REVIEW_SPLIT_SPEC_FILE = "spec.md";
/** Input of {@link planReviewSplitGate}; mirrors the tool-side dispatch facts. */
export interface ReviewSplitGateInput {
    /** Card reference as the caller received it (absolute or project-relative). */
    cardPath: string;
    /** Task key of the parent review dispatch. */
    taskKey: string;
    /** Owner key the dispatch would land under. */
    ownerKey: string;
    /** `.agenticdoc` root (absolute). */
    agenticdocRoot: string;
    /** Project root: base of a relative `cardPath`, base of the receipt's
     * manifest path, and the `MW_REVIEW_SPLIT` lookup root. */
    projectDir: string;
}
/** Result of a `plan` intercept: the receipt (+ manifest link) to show. */
export interface ReviewSplitGateResult {
    /** `plan.receipt` + `\n[review-split] manifest=<path relative to projectDir>`,
     * or `[review-split] mode=plan error=<code>` on the degraded branch. */
    text: string;
    /** Absolute path of the written manifest; `""` on the error branch. */
    manifestPath: string;
}
/** `evidence/split/review-<taskKey>-manifest.json` under the owner key. */
export declare function reviewSplitManifestPath(input: {
    agenticdocRoot: string;
    ownerKey: string;
    taskKey: string;
}): string;
/**
 * `plan`-tier gate for one dispatch: `null` when the dispatch must proceed
 * byte-identically (`off`, `on`, non-review card), the receipt + manifest when
 * the dispatch was intercepted, and a non-throwing `error=<code>` receipt when
 * the plan could not be produced (still intercepted: `mode=plan` was explicit).
 */
export declare function planReviewSplitGate(input: ReviewSplitGateInput): ReviewSplitGateResult | null;
//# sourceMappingURL=review-split-gate.d.ts.map