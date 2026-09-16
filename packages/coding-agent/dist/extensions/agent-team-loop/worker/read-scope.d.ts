/**
 * Read-scope containment for autopilot L2 workers (design D-106, AC-009).
 *
 * When a task.md carries a `read_scope:` block list, every read/ls/find/grep
 * call must resolve inside one of the scope entries (dossier pointers +
 * whitelist), subject to per-worker file/byte caps. The algorithm is
 * implementation-locked by D-106:
 *
 * 1. Base: scope entries and request paths are both resolved against the
 *    worker cwd (the project root; guaranteed by the launcher).
 * 2. Normalization: path.resolve first (lexical ../ collapsing), then
 *    fs.realpathSync (symlinks/junctions). A nonexistent tail is rejoined
 *    onto the realpath of its deepest existing ancestor, so normalization
 *    cannot be bypassed through a path that never touches an existing
 *    directory.
 * 3. Comparison: realpath(request) must equal some realpath(scope) or start
 *    with it + path.sep (segment boundary — "goal-autopilot-evil" never
 *    matches scope "goal-autopilot"). win32 compares lower-cased on both
 *    sides (drive-letter normalization).
 *
 * This module is pure decision logic (read-only fs, no pi dependency, no
 * writes): worker-mode.ts owns the tool_call wiring and the trace.log /
 * output.md rejection records.
 */
/** Default per-worker caps (D-106): 8 read-ish calls, 64 KiB of read bytes. */
export declare const DEFAULT_READ_FILE_CAP = 8;
export declare const DEFAULT_READ_BYTE_CAP = 65536;
/** Rejection rule identifiers — recorded with every blocked call (AC-009). */
export type ReadScopeRule = "scope" | "cap-file" | "cap-byte" | "deny-glob";
/** One blocked call, as accumulated in memory and written to output.md. */
export interface ReadScopeRejection {
    tool: string;
    /** The raw path exactly as the tool call carried it. */
    path: string;
    rule: ReadScopeRule;
    /** ISO timestamp of the blocked call. */
    ts: string;
}
/** Parsed read_scope frontmatter, as enforcement config. */
export interface ReadScopeConfig {
    /** Scope entries (root-relative or absolute). A present-but-empty
     * list blocks every read-ish call (fail-closed on a misconfigured task).
     * null = deny-only mode: a task.md carrying deny_globs but no read_scope
     * gets the deny firewall without containment or caps (mw-dual-workspace
     * D-004 L1 — deny is not silently disabled by a missing scope). */
    scope: string[] | null;
    /** deny_globs frontmatter (mw-dual-workspace AC-006): minimatch globs,
     * dual-basis matched (see matchedDenyGlob). Deny wins over scope allow. */
    denyGlobs: string[];
    /** Max allowed read/ls/find/grep calls over the worker lifetime. */
    fileCap: number;
    /** Max cumulative bytes charged by allowed read calls. */
    byteCap: number;
}
/** Mutable per-worker cap accounting. */
export interface ReadScopeState {
    /** Read-ish calls allowed so far. */
    allowedCalls: number;
    /** Bytes charged by allowed read calls so far. */
    bytesRead: number;
}
/** Decision for one read-ish tool call. Pure: the caller applies the verdict
 * (increments its state counters on allow). */
export interface ReadScopeVerdict {
    allowed: boolean;
    /** Rule that fired on a block (always present when allowed=false). */
    rule?: ReadScopeRule;
    /** Block reason carrying the raw path and the rule token. */
    reason?: string;
    /** Bytes this call charges against the byte cap (allowed read calls only). */
    chargedBytes: number;
}
/** Segment-boundary containment: candidate equals prefix, or begins with
 * prefix + one separator. win32 compares lower-cased on both sides (drive
 * letters); other platforms are byte-exact. */
export declare function isSameOrUnder(prefix: string, candidate: string): boolean;
/** Normalize one path (scope entry or request) for comparison: resolve
 * against projectRoot (lexical .. collapsing), then realpathSync (symlinks
 * and junctions). A nonexistent tail is rejoined onto the realpath of its
 * deepest existing ancestor — the symlink above a missing tail still
 * resolves, so normalization cannot be bypassed. */
export declare function normalizeForCompare(projectRoot: string, p: string): string;
/** Containment check (D-106 steps 1–4): does requestPath resolve inside one
 * of the scope entries? */
export declare function isWithinScope(projectRoot: string, scopeEntries: string[], requestPath: string): boolean;
/**
 * Dual-basis deny matching (mw-dual-workspace D-003, minimatch 实测):
 * a deny glob hits when it matches EITHER the normalized absolute path OR
 * the projectRoot-relative path with forward slashes. The relative basis is
 * what makes bare-directory forms like `DerivedDataCache/**` work — minimatch
 * does not match them against absolute paths (measured, design note 补充核查).
 * projectRoot is the worker cwd (dual mode: the game root; single: the
 * control root), so "relative to root" keeps one meaning everywhere.
 * Returns the matching glob for the block reason, or null.
 */
export declare function matchedDenyGlob(projectRoot: string, denyGlobs: string[], rawPath: string): string | null;
/**
 * The full gate for one read-ish tool call: deny globs first (deny wins over
 * scope allow, AC-006), then containment, then the file cap, then (read only)
 * the byte cap. Containment and caps apply only in scope mode (scope !==
 * null). statSize is injectable for tests; the default stats the resolved
 * path (the read tool loads whole files, so the file size is what the call
 * actually reads).
 */
export declare function checkReadScopeCall(projectRoot: string, config: ReadScopeConfig, state: ReadScopeState, tool: string, rawPath: string, statSize?: (absolutePath: string) => number): ReadScopeVerdict;
/** Build the enforcement config from parsed task.md meta. Undefined when
 * the task carries neither read_scope nor deny_globs: interception disabled
 * (AC-012 red line — manual/legacy tasks behave exactly as before). A task
 * with deny_globs but no read_scope gets deny-only mode (scope=null). Missing
 * or invalid caps fall back to the defaults, never an error. */
export declare function readScopeConfigFromMeta(meta: {
    readScope?: string[];
    denyGlobs?: string[];
    readFileCap?: number;
    readByteCap?: number;
}): ReadScopeConfig | undefined;
//# sourceMappingURL=read-scope.d.ts.map