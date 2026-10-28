/**
 * Review-split switch resolution (claim-driven-review-orchestration design
 * §2.2, spec AC-S1, card T-01).
 *
 * Single source of truth for "is claim-driven review splitting enabled?, and
 * where did that value come from?": `MW_REVIEW_SPLIT` (env) >
 * `.mw/review-split.json` > `REVIEW_SPLIT_DEFAULT="off"`. The resolved state
 * always carries its source because `mw review-split status` must echo the
 * effective value AND its provenance (env/config/default) — a bare `off`
 * cannot distinguish "explicitly off" from "never configured".
 *
 * Tolerance (P-048): this resolver never throws. An illegal env value is
 * ignored (as if unset) and its raw text is returned in `invalid` so the
 * caller can log `split:mode-invalid:<v>` without being refused; a missing,
 * corrupt, or wrongly-versioned config file degrades to the next layer. Mode
 * matching is case-insensitive and surrounding whitespace is trimmed, so
 * `Plan` / `ON` resolve like `plan` / `on`.
 *
 * Pure read: only `readFileSync` (no exists/stat probes, no writes, no
 * directories created). A missing `.mw` directory is simply "no config".
 * The Python side (`mw_common.resolve_review_split`, separate card) mirrors
 * these semantics 1:1 — the TS/Python parity pattern of CLAIM_GATE_DEFAULT
 * in shared/dispatch-card.ts.
 */
/** Legal switch values, in escalation order: off < plan < on. */
export declare const REVIEW_SPLIT_MODES: readonly ["off", "plan", "on"];
export type ReviewSplitMode = (typeof REVIEW_SPLIT_MODES)[number];
/** Default when neither env nor config says anything (design §1, AC-S1:
 * the default MUST NOT change behavior — off is byte-identical to HEAD). */
export declare const REVIEW_SPLIT_DEFAULT: ReviewSplitMode;
/** Env override (highest precedence). */
export declare const REVIEW_SPLIT_ENV = "MW_REVIEW_SPLIT";
/** Persisted switch file, relative to the project root (spec §5.1:
 * `{"v":1,"mode":"...","updated":"..."}`). */
export declare const REVIEW_SPLIT_CONFIG = ".mw/review-split.json";
/** Where the effective value came from (status output field). */
export type ReviewSplitSource = "env" | "config" | "default";
export interface ReviewSplitState {
    mode: ReviewSplitMode;
    source: ReviewSplitSource;
    /** Absolute path of the config file the resolver consulted (reported
     * even when the value came from env/default, so `status` can print it). */
    configPath: string;
    /** Raw illegal env value or config downgrade reason (`config-invalid-json`,
     * `config-invalid-shape`, `config-invalid-v:<v>`,
     * `config-invalid-mode:<mode>`, `config-unreadable:<code>`). Present only
     * when something was rejected. An empty env value yields `""` (falsy) so
     * a caller's `if (state.invalid)` skips the warning. */
    invalid?: string;
}
/** Path of the persisted switch file for a project root (exported for
 * `mw review-split status` / `set`). */
export declare function reviewSplitConfigPath(projectDir: string): string;
/**
 * Resolve the effective review-split switch for a project root.
 *
 * Precedence env > `.mw/review-split.json` > `REVIEW_SPLIT_DEFAULT`; an
 * illegal env value falls through to the config file (and is still reported
 * in `invalid`), an unusable config file falls through to the default. Never
 * throws and never writes: the caller can use it on every review dispatch,
 * and `mw review-split status` can use it as a read-only probe.
 */
export declare function resolveReviewSplit(projectDir: string, env?: Record<string, string | undefined>): ReviewSplitState;
//# sourceMappingURL=review-split.d.ts.map