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
import * as fs from "node:fs";
import * as path from "node:path";
/** Legal switch values, in escalation order: off < plan < on. */
export const REVIEW_SPLIT_MODES = ["off", "plan", "on"];
/** Default when neither env nor config says anything (design §1, AC-S1:
 * the default MUST NOT change behavior — off is byte-identical to HEAD). */
export const REVIEW_SPLIT_DEFAULT = "off";
/** Env override (highest precedence). */
export const REVIEW_SPLIT_ENV = "MW_REVIEW_SPLIT";
/** Persisted switch file, relative to the project root (spec §5.1:
 * `{"v":1,"mode":"...","updated":"..."}`). */
export const REVIEW_SPLIT_CONFIG = ".mw/review-split.json";
/** Path of the persisted switch file for a project root (exported for
 * `mw review-split status` / `set`). */
export function reviewSplitConfigPath(projectDir) {
    return path.join(projectDir, REVIEW_SPLIT_CONFIG);
}
/** Case-insensitive, whitespace-tolerant mode match; null when illegal. */
function asMode(value) {
    if (typeof value !== "string")
        return null;
    const normalized = value.trim().toLowerCase();
    return REVIEW_SPLIT_MODES.includes(normalized) ? normalized : null;
}
/** Render a rejected JSON value for the `invalid` reason (never throws). */
function describe(value) {
    try {
        return JSON.stringify(value) ?? String(value);
    }
    catch {
        return String(value);
    }
}
/**
 * Read `.mw/review-split.json` (pure read, never throws). `mode: null` means
 * "no usable config" — missing file/dir, unparsable JSON, non-object top
 * level, `v` other than the number 1, or an illegal mode; the latter four
 * also report why in `invalid`.
 */
function readConfigMode(configPath) {
    let text;
    try {
        text = fs.readFileSync(configPath, "utf-8");
    }
    catch (err) {
        const code = err.code;
        // Missing file / missing or non-directory `.mw` is not an error.
        if (code === undefined || code === "ENOENT" || code === "ENOTDIR" || code === "EISDIR") {
            return { mode: null };
        }
        return { mode: null, invalid: `config-unreadable:${code}` };
    }
    let parsed;
    try {
        parsed = JSON.parse(text);
    }
    catch {
        return { mode: null, invalid: "config-invalid-json" };
    }
    if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
        return { mode: null, invalid: "config-invalid-shape" };
    }
    const raw = parsed;
    // Format version gate (spec §5.1): only v1 is understood; anything else
    // (missing, string "1", future v2) degrades instead of guessing.
    if (raw.v !== 1) {
        return { mode: null, invalid: `config-invalid-v:${describe(raw.v)}` };
    }
    const mode = asMode(raw.mode);
    if (mode === null) {
        return { mode: null, invalid: `config-invalid-mode:${describe(raw.mode)}` };
    }
    return { mode };
}
/**
 * Resolve the effective review-split switch for a project root.
 *
 * Precedence env > `.mw/review-split.json` > `REVIEW_SPLIT_DEFAULT`; an
 * illegal env value falls through to the config file (and is still reported
 * in `invalid`), an unusable config file falls through to the default. Never
 * throws and never writes: the caller can use it on every review dispatch,
 * and `mw review-split status` can use it as a read-only probe.
 */
export function resolveReviewSplit(projectDir, env = process.env) {
    const configPath = reviewSplitConfigPath(projectDir);
    let invalid;
    const rawEnv = env[REVIEW_SPLIT_ENV];
    if (rawEnv !== undefined) {
        const envMode = asMode(rawEnv);
        if (envMode !== null)
            return { mode: envMode, source: "env", configPath };
        // Illegal env value: act as unset (P-048) but keep the raw text for
        // the upper layer's `split:mode-invalid:<v>` warning.
        invalid = rawEnv;
    }
    const config = readConfigMode(configPath);
    if (config.mode !== null) {
        return invalid === undefined
            ? { mode: config.mode, source: "config", configPath }
            : { mode: config.mode, source: "config", configPath, invalid };
    }
    // Env's raw value is the more actionable warning (the operator set it),
    // so it wins over the config downgrade reason when both are present.
    if (invalid === undefined)
        invalid = config.invalid;
    return invalid === undefined
        ? { mode: REVIEW_SPLIT_DEFAULT, source: "default", configPath }
        : { mode: REVIEW_SPLIT_DEFAULT, source: "default", configPath, invalid };
}
//# sourceMappingURL=review-split.js.map