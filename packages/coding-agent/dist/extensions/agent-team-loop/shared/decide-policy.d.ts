/**
 * Per-dp policy resolution (spec §14 AC-016, design D-048..D-051).
 *
 * One authority chain, mirrored byte-for-byte with
 * `packages/multi-workers/decision_points.py::resolve_policy`:
 *
 *   per-dp row in `.mw/decide-points.json`
 *     > declared keys of `.mw/decide.json`
 *       > built-in defaults (0.7 / 8 / 20)
 *
 * Lives in `shared/` (not `pm/`) because BOTH consumers need it: the worker
 * (`worker/worker-mode.ts`, dp3 thresholds) and the PM
 * (`pm/pm-orchestrator.ts`, dp2 gate). A `pm/` home would make the worker
 * extension import the PM layer, which the module layout forbids.
 *
 * Fail-soft by contract (AC-016): an illegal value is dropped with a
 * `problems` entry and the resolver falls through to the next layer. Nothing
 * here throws, and a missing/unreadable file is simply an empty layer.
 */
/** The three knobs of AC-016. Order is frozen (parity with Python). */
export declare const DECIDE_POLICY_KEYS: readonly ["min_confidence", "max_questions", "timeout_s"];
export type DecidePolicyKey = (typeof DECIDE_POLICY_KEYS)[number];
/** Built-in (last-resort) layer — the values that were hard-coded in TS. */
export declare const DECIDE_POLICY_BUILTIN: Readonly<Record<DecidePolicyKey, number>>;
/** Per-dp row domain (`POLICY_ROW_BOUNDS` in `decision_points.py`). */
export declare const DECIDE_POLICY_ROW_BOUNDS: Readonly<Record<DecidePolicyKey, readonly [number, number]>>;
/** Which layer decided an effective value (audit / `dp check` parity). */
export type DecidePolicyOrigin = "row" | "decide.json" | "builtin";
/** Effective per-dp policy plus the provenance `mw decide dp check` prints. */
export interface ResolvedDecidePolicy {
    minConfidence: number;
    maxQuestions: number;
    timeoutS: number;
    origins: Record<DecidePolicyKey, DecidePolicyOrigin>;
    /** One line per dropped value, e.g. `L8: min_confidence 1.5 is outside [0, 1]`. */
    problems: string[];
    /** Where the two files were read from (diagnostics only). */
    pointsPath: string;
    decidePath: string;
}
/** Validate one knob; `{ value }` or `{ problem }` — never throws. */
export declare function coerceDecidePolicyValue(key: DecidePolicyKey, value: unknown, perDp: boolean): {
    value: number;
    problem?: undefined;
} | {
    problem: string;
    value?: undefined;
};
/**
 * Resolve the effective per-dp policy for `dpId` under `projectDir`.
 *
 * The row layer is the raw `.mw/decide-points.json` `points[dpId]` object: a
 * missing row or a non-object row contributes nothing (Python keeps such a row
 * `enabled=false` / unparsed, and its policy fields are unset either way). The
 * global layer is the *declared* keys of `.mw/decide.json` — a dataclass default
 * is not a declaration, so an unset file never masks the built-in layer.
 */
export declare function resolveDecidePolicy(dpId: string, projectDir: string): ResolvedDecidePolicy;
//# sourceMappingURL=decide-policy.d.ts.map