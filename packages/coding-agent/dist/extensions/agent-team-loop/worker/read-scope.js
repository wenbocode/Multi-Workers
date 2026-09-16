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
import * as fs from "node:fs";
import * as path from "node:path";
import { minimatch } from "minimatch";
/** Default per-worker caps (D-106): 8 read-ish calls, 64 KiB of read bytes. */
export const DEFAULT_READ_FILE_CAP = 8;
export const DEFAULT_READ_BYTE_CAP = 65_536;
const IS_WIN32 = process.platform === "win32";
/** Segment-boundary containment: candidate equals prefix, or begins with
 * prefix + one separator. win32 compares lower-cased on both sides (drive
 * letters); other platforms are byte-exact. */
export function isSameOrUnder(prefix, candidate) {
    const a = IS_WIN32 ? prefix.toLowerCase() : prefix;
    const c = IS_WIN32 ? candidate.toLowerCase() : candidate;
    return c === a || c.startsWith(`${a}${path.sep}`);
}
/** Normalize one path (scope entry or request) for comparison: resolve
 * against projectRoot (lexical .. collapsing), then realpathSync (symlinks
 * and junctions). A nonexistent tail is rejoined onto the realpath of its
 * deepest existing ancestor — the symlink above a missing tail still
 * resolves, so normalization cannot be bypassed. */
export function normalizeForCompare(projectRoot, p) {
    const abs = path.resolve(projectRoot, p);
    let cur = abs;
    const tail = [];
    for (;;) {
        try {
            return path.join(fs.realpathSync(cur), ...tail);
        }
        catch {
            const parent = path.dirname(cur);
            if (parent === cur)
                return abs; // reached the fs root unresolved — lexical is the best available
            tail.unshift(path.basename(cur));
            cur = parent;
        }
    }
}
/** Containment check (D-106 steps 1–4): does requestPath resolve inside one
 * of the scope entries? */
export function isWithinScope(projectRoot, scopeEntries, requestPath) {
    const req = normalizeForCompare(projectRoot, requestPath);
    return scopeEntries.some((entry) => isSameOrUnder(normalizeForCompare(projectRoot, entry), req));
}
function defaultStatSize(absolutePath) {
    try {
        return fs.statSync(absolutePath).size;
    }
    catch {
        return 0; // unreadable/nonexistent: the read itself fails, charge nothing
    }
}
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
export function matchedDenyGlob(projectRoot, denyGlobs, rawPath) {
    if (denyGlobs.length === 0)
        return null;
    const abs = normalizeForCompare(projectRoot, rawPath);
    const rel = path.relative(projectRoot, abs).replaceAll("\\", "/");
    for (const glob of denyGlobs) {
        if (minimatch(abs, glob) || minimatch(rel, glob))
            return glob;
        // A trailing /** also denies the directory itself: plain minimatch
        // leaves `ls`/`find` on the bare directory (which lists its contents)
        // unblocked — a firewall hole. `DerivedDataCache/**` therefore also
        // matches the root-relative `DerivedDataCache`.
        if (glob.endsWith("/**")) {
            const stripped = glob.slice(0, -3);
            if (stripped !== "" && minimatch(rel, stripped))
                return glob;
        }
    }
    return null;
}
/**
 * The full gate for one read-ish tool call: deny globs first (deny wins over
 * scope allow, AC-006), then containment, then the file cap, then (read only)
 * the byte cap. Containment and caps apply only in scope mode (scope !==
 * null). statSize is injectable for tests; the default stats the resolved
 * path (the read tool loads whole files, so the file size is what the call
 * actually reads).
 */
export function checkReadScopeCall(projectRoot, config, state, tool, rawPath, statSize = defaultStatSize) {
    const denyGlob = matchedDenyGlob(projectRoot, config.denyGlobs, rawPath);
    if (denyGlob !== null) {
        return {
            allowed: false,
            rule: "deny-glob",
            reason: `read_scope: blocked ${tool} of ${rawPath}: the path matches deny glob '${denyGlob}' [rule=deny-glob]`,
            chargedBytes: 0,
        };
    }
    if (config.scope !== null && !isWithinScope(projectRoot, config.scope, rawPath)) {
        return {
            allowed: false,
            rule: "scope",
            reason: `read_scope: blocked ${tool} of ${rawPath}: the path resolves outside the allowed read scope ` +
                `(${config.scope.join(", ")}) [rule=scope]`,
            chargedBytes: 0,
        };
    }
    if (config.scope !== null && state.allowedCalls >= config.fileCap) {
        return {
            allowed: false,
            rule: "cap-file",
            reason: `read_scope: blocked ${tool} of ${rawPath}: the read file cap is reached ` +
                `(${state.allowedCalls}/${config.fileCap} calls already allowed) [rule=cap-file]`,
            chargedBytes: 0,
        };
    }
    let chargedBytes = 0;
    if (tool === "read") {
        chargedBytes = statSize(path.resolve(projectRoot, rawPath));
        if (state.bytesRead + chargedBytes > config.byteCap) {
            return {
                allowed: false,
                rule: "cap-byte",
                reason: `read_scope: blocked ${tool} of ${rawPath}: the read byte cap would be exceeded ` +
                    `(${state.bytesRead}/${config.byteCap} bytes already read, this file is ${chargedBytes}B) [rule=cap-byte]`,
                chargedBytes: 0,
            };
        }
    }
    return { allowed: true, chargedBytes };
}
/** Build the enforcement config from parsed task.md meta. Undefined when
 * the task carries neither read_scope nor deny_globs: interception disabled
 * (AC-012 red line — manual/legacy tasks behave exactly as before). A task
 * with deny_globs but no read_scope gets deny-only mode (scope=null). Missing
 * or invalid caps fall back to the defaults, never an error. */
export function readScopeConfigFromMeta(meta) {
    if (meta.readScope === undefined && meta.denyGlobs === undefined)
        return undefined;
    return {
        scope: meta.readScope === undefined ? null : meta.readScope,
        denyGlobs: meta.denyGlobs ?? [],
        fileCap: meta.readFileCap ?? DEFAULT_READ_FILE_CAP,
        byteCap: meta.readByteCap ?? DEFAULT_READ_BYTE_CAP,
    };
}
//# sourceMappingURL=read-scope.js.map