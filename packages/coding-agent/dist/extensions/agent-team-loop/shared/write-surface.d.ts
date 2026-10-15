/**
 * shared/write-surface.ts — single source of truth for "may this worker role
 * write this path?" (mw-worker-output-contract W1, design §3; AC-006 / AC-007 /
 * AC-016).
 *
 * Before this module the same path was judged in two places with opposite
 * answers: the runtime channel (`worker/worker-file-tool.ts`) and the shell
 * guard (`worker/worker-mode.ts::checkBashWriteScopeTarget`) both allowed
 * `<key>/evidence/**`, while the dispatch-time judge
 * (`pm/ui-bridge.ts::judgeWriteTarget`) had no evidence face at all. This
 * module holds the one predicate (`judgeWriteTarget`) and the one deny table
 * (`pmWriteDenyReason`) plus the one basename whitelist
 * (`WORKER_FILE_NAME_RE` / `isAllowedWorkerFileName`); the call sites degrade
 * to thin adapters that only convert their input shape.
 *
 * Path-domain semantics (design §3.2, DR1):
 * - Allowed face = the task's own dir + `<key>/evidence/**` with TWO accepted
 *   bases: project-root relative (`.agenticdoc/<key>/evidence/…`) and keyDir
 *   relative (`evidence/…`); `evidence/**` has no extension restriction.
 * - Refusals stay fail-closed: `../..`, another key, repo source, `.git`,
 *   `node_modules`-class paths, and anything else outside the face.
 * - `WORKER_FILE_NAME_RE` is moved here byte-for-byte (never widened to accept
 *   directories): it is shared by `shared/deliverable-evidence.ts` (a basename
 *   check on `readdirSync` output) and the non-directory basename channel.
 * - `write_scope:` narrows the face here too (default face === the rendered
 *   `write_scope:` from `renderDefaultWriteScope`, so today's behavior is
 *   unchanged).
 *
 * Dependency direction (hard constraint, DR1 §3.2): this module imports only
 * `node:path`, `node:fs`, `minimatch`, `../worker/read-scope.ts` and
 * `./paths.ts`. It must never import `worker-file-tool.ts`, `worker-mode.ts`,
 * `pm/ui-bridge.ts` or `deliverable-evidence.ts` (that would create the cycle
 * `ui-bridge → worker-file-tool → change-ledger`).
 */
/** Bare basename alternative shared by the basename and path regexes. */
export declare const WORKER_FILE_BASENAME_ALT = "progress\\.md|report\\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\\.md";
/**
 * Single source of truth for the writable basename set (D-102): `progress.md`,
 * `report.md` and `report[-.]<slug>.md` with a 1..41 char slug. No `g` flag
 * (no `lastIndex` state); `$` without `m` rejects a trailing newline. Semantics
 * are unchanged from the original `worker-file-tool.ts` definition — the
 * `evidence/**` face lives in {@link judgeWriteTarget}, never in this regex.
 */
export declare const WORKER_FILE_NAME_RE: RegExp;
export declare const WORKER_FILE_EVIDENCE_ALT = "(?:\\.agenticdoc/[A-Za-z0-9._-]+/)?evidence/(?!\\.{1,2}(?:/|$))[A-Za-z0-9._-]+(?:/(?!\\.{1,2}(?:/|$))[A-Za-z0-9._-]+)*";
/** Schema-layer pattern: a worker_file basename OR an evidence path. */
export declare const WORKER_FILE_PATH_RE: RegExp;
/** Basename whitelist check (the name shared by worker-file-tool and its tests). */
export declare function isAllowedWorkerFileName(name: string): boolean;
/** Shape classes for one candidate token (AC-004). The first four (`punct`,
 * `version`, `abbrev`, `bare`) are non-candidates: prose, not write targets. */
export type WriteTargetShape = "punct" | "version" | "abbrev" | "bare" | "sep" | "dot-lead" | "drive-relative" | "ads" | "colon" | "ext" | "deny-name" | "exists";
/** Shape classification for one candidate token (AC-004). Ordered so the
 * pointed Win32 forms (`drive-relative`, `ads`) are labelled before the `ext`
 * rule can swallow them; trailing dots/spaces are stripped first (Win32
 * CreateFile semantics). Read-only (`existsSync`). */
export declare function classifyWriteTargetShape(pathToken: string, ctx: {
    projectRoot: string;
}): WriteTargetShape;
/** Raw inputs a call site has at hand. `keyDir`/`trueRoot` are optional to
 * preserve the historical PM semantics ("omitted ⇒ the deny table and the
 * evidence face are not evaluated"); `writeScope` is the parsed `write_scope:`
 * narrowing carrier (undefined = header absent ⇒ default face; [] =
 * present-but-empty ⇒ fail-closed). */
export interface WriteSurfaceSeed {
    taskDir: string;
    projectRoot?: string;
    /** Own key dir (`.agenticdoc/<key>`). */
    keyDir?: string;
    /** TRUE `.agenticdoc` root. */
    trueRoot?: string;
    /** `write_scope:` entries, project-root relative. */
    writeScope?: string[];
}
/** Normalized path domain used by the predicate. */
export interface WriteSurfacePaths {
    taskDir: string;
    keyDir?: string;
    agenticdocRoot?: string;
    projectRoot: string;
}
/** Normalize the raw seed into the four path anchors. Explicit values win;
 * missing anchors stay missing (no derivation) so that a PM ctx without a
 * `keyDir` keeps the historical "evidence not evaluable" fail-closed
 * behavior. Runtime callers that only have `taskDir` derive them explicitly
 * (see `worker/worker-file-tool.ts`). */
export declare function resolveWriteSurfacePaths(seed: WriteSurfaceSeed): WriteSurfacePaths;
/** Derive the write-surface seed from the canonical task layout
 * `<projectRoot>/.agenticdoc/<key>/workers/<taskKey>` (shared by the runtime
 * tool, which only receives `taskDir`). A non-canonical directory yields only
 * `taskDir`, so the evidence face stays unavailable (fail-closed). */
export declare function deriveWriteSurfacePaths(taskDir: string): {
    taskDir: string;
    projectRoot: string;
    keyDir?: string;
    trueRoot?: string;
};
/** PM-side deny prefix table: same six rules and priority as
 * `worker-mode.ts::bashWriteDenyReason`, parameterized by `keyDir`/`trueRoot`.
 * `target` must already be normalized by `normalizeForCompare`. Returns the
 * machine-readable rule name, or null when the target is not denied. */
export declare function pmWriteDenyReason(ctx: WriteSurfacePaths, target: string): string | null;
/** Parse the task.md `write_scope:` header with the same semantics as
 * `worker-mode.ts` (comma form `write_scope: a, b` and the YAML block-list
 * form, one pair of surrounding quotes stripped). Returns undefined when the
 * header is absent. This is the runtime channel's narrowing carrier so
 * `worker_file` honours the same declaration the shell guard does. */
export declare function parseWriteScopeHeader(text: string): string[] | undefined;
/** One `write_scope:`/`write_face:` style entry match, project-root based
 * (glob entries use the same dual-basis minimatch rule as the shell guard; the
 * shell guard imports THIS function, so the two carriers cannot diverge). */
export declare function matchesWriteScopeEntry(projectRoot: string, entry: string, absoluteTarget: string): boolean;
/** Verdict of the target axis. `rule` exists only when allowed=false:
 * `deny` = the deny prefix table fired, `scope` = a path-shaped target outside
 * the write surface, `write-scope` = a declared `write_scope:` narrowed it
 * away. `domain` names the face that accepted the target. */
export interface WriteTargetVerdict {
    allowed: boolean;
    shape: WriteTargetShape;
    domain?: "task-dir" | "evidence";
    rule?: "deny" | "scope" | "write-scope";
    detail?: string;
    /** Absolute target the write resolves to (present on every verdict when it
     * could be resolved). */
    target: string;
}
/**
 * The one write-surface predicate (design §3.1/§3.2). Evaluation order:
 *   1. deny prefixes (absolute priority; deny table is never widened by
 *      `write_scope:`)
 *   2. own task dir (realpath + segment boundary)
 *   3. own-key `<key>/evidence/**`, dual basis (project-root and keyDir
 *      relative); no extension restriction
 *   4. task-dir basename channel — ONLY for a token with no directory
 *      component, so a whitelisted basename can never whitelist a foreign
 *      directory
 *   5. `write_scope:` narrowing (applies to faces 2–4; absent = full default
 *      face, which equals `renderDefaultWriteScope`)
 *   6. path shape => refuse (fail-closed)
 *   7. non-candidate prose => pass untouched
 */
export declare function judgeWriteTarget(pathToken: string, seed: WriteSurfaceSeed): WriteTargetVerdict;
/** How a relative path token resolves to the own-key evidence tree.
 * - `"dual"` (dispatch + `worker_file`): project-root relative
 *   (`.agenticdoc/<key>/evidence/…`) AND keyDir relative (`evidence/…`), both
 *   accepted (design §3.2 / DR1).
 * - `"project-root"` (shell guard): only the project-root basis. A shell target
 *   is a cwd-resolved literal, so a keyDir-relative `evidence/x.md` resolves to
 *   `<cwd>/evidence/x.md` and must stay fail-closed (DR1 ruling — a designed
 *   difference, not a bug: the guard cannot rewrite the user's path). */
export type EvidenceBasis = "dual" | "project-root";
/** The own-key evidence directory (absolute), or undefined when the key dir is
 * unknown (PM semantics: no key dir ⇒ the evidence face is not evaluable). One
 * definition shared by the predicate, the shell guard's display label and the
 * tests. */
export declare function evidenceDirOf(paths: WriteSurfacePaths): string | undefined;
/** The matched own write face for one token. */
export interface OwnWriteTarget {
    domain: "task-dir" | "evidence";
    target: string;
}
/** Resolve `pathToken` against the own task dir and own-key evidence tree, or
 * null when it is outside both. The basename channel (task-dir basenames such
 * as `report.md`) belongs to the dispatch/`worker_file` face and is disabled
 * for the shell guard, which only ever sees cwd-resolved literals. */
export declare function resolveOwnWriteTarget(pathToken: string, paths: WriteSurfacePaths, opts?: {
    evidenceBasis?: EvidenceBasis;
    basenameChannel?: boolean;
}): OwnWriteTarget | null;
//# sourceMappingURL=write-surface.d.ts.map