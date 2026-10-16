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

import * as fs from "node:fs";
import * as path from "node:path";
import { minimatch } from "minimatch";
import { isSameOrUnder, normalizeForCompare } from "../worker/read-scope.ts";
import { WORKERS_DIR } from "./paths.ts";

// ── Basename whitelist (moved verbatim from worker/worker-file-tool.ts) ───────

/** Bare basename alternative shared by the basename and path regexes. */
export const WORKER_FILE_BASENAME_ALT = "progress\\.md|report\\.md|report[-.][a-z0-9][a-z0-9._-]{0,40}\\.md";

/**
 * Single source of truth for the writable basename set (D-102): `progress.md`,
 * `report.md` and `report[-.]<slug>.md` with a 1..41 char slug. No `g` flag
 * (no `lastIndex` state); `$` without `m` rejects a trailing newline. Semantics
 * are unchanged from the original `worker-file-tool.ts` definition — the
 * `evidence/**` face lives in {@link judgeWriteTarget}, never in this regex.
 */
export const WORKER_FILE_NAME_RE = new RegExp(`^(?:${WORKER_FILE_BASENAME_ALT})$`);

/**
 * Evidence path alternative for the tool schema pre-filter (DR1 §3.1). A
 * segment is `[A-Za-z0-9._-]+` and may not be `.` or `..`; depth is unbounded;
 * the project-root-relative `.agenticdoc/<key>/` prefix is optional so both
 * accepted bases pass the schema layer. The authoritative decision stays in
 * {@link judgeWriteTarget}; this regex only keeps obviously-invalid values out
 * of the TypeBox layer.
 */
// Segment: alphabet including dots, but at least one non-dot char — rejects
// "."/".." segments WITHOUT lookaround (Azure strict JSON-schema validation of
// tool `pattern` fields rejects ECMA lookaround; broke review-role workers on
// gpt-6.1-sol). Equivalent to the old (?!.{1,2}(?:/|$)) guard.
const WORKER_FILE_EVIDENCE_SEG = "[A-Za-z0-9._-]*[A-Za-z0-9_-][A-Za-z0-9._-]*";
export const WORKER_FILE_EVIDENCE_ALT = `(?:\\.agenticdoc/[A-Za-z0-9._-]+/)?evidence/${WORKER_FILE_EVIDENCE_SEG}(?:/${WORKER_FILE_EVIDENCE_SEG})*`;

/** Schema-layer pattern: a worker_file basename OR an evidence path. */
export const WORKER_FILE_PATH_RE = new RegExp(`^(?:${WORKER_FILE_BASENAME_ALT}|${WORKER_FILE_EVIDENCE_ALT})$`);

/** Basename whitelist check (the name shared by worker-file-tool and its tests). */
export function isAllowedWorkerFileName(name: string): boolean {
	return WORKER_FILE_NAME_RE.test(name);
}

// ── Target-shape classification (moved from pm/ui-bridge.ts) ─────────────────

/** Shape classes for one candidate token (AC-004). The first four (`punct`,
 * `version`, `abbrev`, `bare`) are non-candidates: prose, not write targets. */
export type WriteTargetShape =
	| "punct"
	| "version"
	| "abbrev"
	| "bare"
	| "sep"
	| "dot-lead"
	| "drive-relative"
	| "ads"
	| "colon"
	| "ext"
	| "deny-name"
	| "exists";

/** Non-path prose forms that would otherwise scan as a path shape: `e.g.` /
 * `i.e.` are abbreviations, not files. */
const WRITE_INTENT_ABBREVIATIONS = new Set(["e.g", "i.e", "etc", "vs", "cf"]);

/** Extension-less target names the shape layer must still refuse (AC-004,
 * `Makefile` class). A finite name table — never a bare-token fail-closed
 * (that was measured at 35% false positives on the writeless corpus). */
const WRITE_INTENT_DENY_NAMES = new Set([
	"Makefile",
	"makefile",
	"GNUmakefile",
	"Dockerfile",
	"Containerfile",
	"Rakefile",
	"Gemfile",
	"Procfile",
	"Vagrantfile",
	"Justfile",
	"Brewfile",
]);

/** Shapes that name a path rather than prose (AC-004). Membership in this set
 * is what makes the last step of the judge refuse an out-of-surface candidate. */
const WRITE_TARGET_PATH_SHAPES: ReadonlySet<WriteTargetShape> = new Set([
	"sep",
	"dot-lead",
	"drive-relative",
	"ads",
	"colon",
	"ext",
	"deny-name",
	"exists",
]);

/** Shape classification for one candidate token (AC-004). Ordered so the
 * pointed Win32 forms (`drive-relative`, `ads`) are labelled before the `ext`
 * rule can swallow them; trailing dots/spaces are stripped first (Win32
 * CreateFile semantics). Read-only (`existsSync`). */
export function classifyWriteTargetShape(pathToken: string, ctx: { projectRoot: string }): WriteTargetShape {
	const t = pathToken.replace(/[.\s]+$/, "");
	if (t === "" || !/[A-Za-z0-9]/.test(t)) return "punct";
	if (/^\d+(\.\d+)+$/.test(t)) return "version";
	if (WRITE_INTENT_ABBREVIATIONS.has(t.toLowerCase())) return "abbrev";
	if (/[\\/]/.test(t)) return "sep";
	if (/^\.[A-Za-z0-9_]/.test(t)) return "dot-lead";
	if (/::/.test(t)) return "ads";
	if (/^[A-Za-z]:(?![\\/])/.test(t)) return "drive-relative";
	if (t.includes(":")) return "colon";
	if (/\.[A-Za-z0-9]{1,8}$/.test(t)) return "ext";
	if (WRITE_INTENT_DENY_NAMES.has(t)) return "deny-name";
	if (fs.existsSync(path.resolve(ctx.projectRoot, t))) return "exists";
	return "bare";
}

// ── Path resolution ─────────────────────────────────────────────────────────

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
export function resolveWriteSurfacePaths(seed: WriteSurfaceSeed): WriteSurfacePaths {
	const taskDir = path.resolve(seed.taskDir);
	const projectRoot = seed.projectRoot === undefined ? process.cwd() : path.resolve(seed.projectRoot);
	return {
		taskDir,
		keyDir: seed.keyDir === undefined ? undefined : path.resolve(seed.keyDir),
		agenticdocRoot: seed.trueRoot === undefined ? undefined : path.resolve(seed.trueRoot),
		projectRoot,
	};
}

/** Derive the write-surface seed from the canonical task layout
 * `<projectRoot>/.agenticdoc/<key>/workers/<taskKey>` (shared by the runtime
 * tool, which only receives `taskDir`). A non-canonical directory yields only
 * `taskDir`, so the evidence face stays unavailable (fail-closed). */
export function deriveWriteSurfacePaths(taskDir: string): {
	taskDir: string;
	projectRoot: string;
	keyDir?: string;
	trueRoot?: string;
} {
	const abs = path.resolve(taskDir);
	const workersDir = path.dirname(abs);
	if (path.basename(workersDir) !== WORKERS_DIR) return { taskDir: abs, projectRoot: process.cwd() };
	const keyDir = path.dirname(workersDir);
	const trueRoot = path.dirname(keyDir);
	const projectRoot = path.dirname(trueRoot);
	return { taskDir: abs, projectRoot, keyDir, trueRoot };
}

// ── Deny table (moved from pm/ui-bridge.ts::pmWriteDenyReason) ───────────────

function samePath(a: string, b: string): boolean {
	return isSameOrUnder(a, b) && isSameOrUnder(b, a);
}

/** PM-side deny prefix table: same six rules and priority as
 * `worker-mode.ts::bashWriteDenyReason`, parameterized by `keyDir`/`trueRoot`.
 * `target` must already be normalized by `normalizeForCompare`. Returns the
 * machine-readable rule name, or null when the target is not denied. */
export function pmWriteDenyReason(ctx: WriteSurfacePaths, target: string): string | null {
	const keyDir = ctx.keyDir;
	const trueRoot = ctx.agenticdocRoot;
	if (keyDir !== undefined) {
		if (samePath(target, path.join(keyDir, "pm-state.md"))) return "pm-state.md";
		const workersDir = path.join(keyDir, WORKERS_DIR);
		if (isSameOrUnder(workersDir, target)) {
			const first = path.relative(workersDir, target).split(/[\\/]/)[0] ?? "";
			if (first.startsWith("_workers")) return "workers/_workers*";
		}
	}
	if (trueRoot !== undefined && samePath(target, path.join(trueRoot, "_index.parallel"))) return "_index.parallel";
	if (
		trueRoot !== undefined &&
		keyDir !== undefined &&
		isSameOrUnder(trueRoot, target) &&
		!isSameOrUnder(keyDir, target)
	) {
		return "other key dir / .agenticdoc root";
	}
	if (isSameOrUnder(path.join(ctx.projectRoot, "packages"), target)) return "packages/**";
	if (isSameOrUnder(path.join(ctx.projectRoot, ".git"), target)) return ".git/**";
	return null;
}

// ── write_scope narrowing (the one parser + entry matcher; T-10) ────────────

const GLOB_MAGIC_RE = /[*?[\]{}]/;

function stripSurroundingQuotes(value: string): string {
	if ((value.startsWith('"') && value.endsWith('"')) || (value.startsWith("'") && value.endsWith("'"))) {
		return value.slice(1, -1);
	}
	return value;
}

/** Parse the task.md `write_scope:` header with the same semantics as
 * `worker-mode.ts` (comma form `write_scope: a, b` and the YAML block-list
 * form, one pair of surrounding quotes stripped). Returns undefined when the
 * header is absent. This is the runtime channel's narrowing carrier so
 * `worker_file` honours the same declaration the shell guard does. */
export function parseWriteScopeHeader(text: string): string[] | undefined {
	let writeScope: string[] | undefined;
	let inList = false;
	for (const line of text.split(/\r?\n/)) {
		const trimmed = line.trim();
		if (trimmed.startsWith("write_scope:")) {
			const rest = trimmed.slice("write_scope:".length).trim();
			if (rest) {
				writeScope = rest
					.split(",")
					.map((item) => stripSurroundingQuotes(item.trim()))
					.filter((item) => item.length > 0);
				inList = false;
			} else {
				writeScope = [];
				inList = true;
			}
			continue;
		}
		if (!inList) continue;
		if (trimmed.startsWith("- ")) {
			const item = stripSurroundingQuotes(trimmed.slice(2).trim());
			if (item) writeScope?.push(item);
		} else {
			inList = false;
		}
	}
	return writeScope;
}

/** One `write_scope:`/`write_face:` style entry match, project-root based
 * (glob entries use the same dual-basis minimatch rule as the shell guard; the
 * shell guard imports THIS function, so the two carriers cannot diverge). */
export function matchesWriteScopeEntry(projectRoot: string, entry: string, absoluteTarget: string): boolean {
	const normalized = entry.trim();
	if (normalized === "") return false;
	if (GLOB_MAGIC_RE.test(normalized)) {
		const relative = path.relative(projectRoot, absoluteTarget).replaceAll("\\", "/");
		const forward = absoluteTarget.replaceAll("\\", "/");
		const glob = normalized.replaceAll("\\", "/");
		if (minimatch(relative, glob) || minimatch(forward, glob)) return true;
		if (glob.endsWith("/**")) {
			const stripped = glob.slice(0, -3);
			if (stripped !== "" && (minimatch(relative, stripped) || minimatch(forward, stripped))) return true;
		}
		return false;
	}
	return isSameOrUnder(normalizeForCompare(projectRoot, normalized), absoluteTarget);
}

/** Default face under a declared `write_scope:`: absent header = the full
 * default face (today's zero-behavior-change case); present-but-empty
 * (`[]`) = fail-closed. */
function scopeAllows(projectRoot: string, writeScope: string[] | undefined, target: string): boolean {
	if (writeScope === undefined) return true;
	return writeScope.some((entry) => matchesWriteScopeEntry(projectRoot, entry, target));
}

// ── The single predicate ────────────────────────────────────────────────────

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
export function judgeWriteTarget(pathToken: string, seed: WriteSurfaceSeed): WriteTargetVerdict {
	const paths = resolveWriteSurfacePaths(seed);
	return judgeResolvedWriteTarget(pathToken, paths, seed.writeScope);
}

function judgeResolvedWriteTarget(
	pathToken: string,
	paths: WriteSurfacePaths,
	writeScope: string[] | undefined,
): WriteTargetVerdict {
	const shape = classifyWriteTargetShape(pathToken, { projectRoot: paths.projectRoot });
	const target = normalizeForCompare(paths.projectRoot, pathToken);
	const denied = pmWriteDenyReason(paths, target);
	if (denied !== null) return { allowed: false, shape, rule: "deny", detail: `denied:${denied}`, target };
	const own = resolveOwnWriteTarget(pathToken, paths, { evidenceBasis: "dual", basenameChannel: true });
	if (own !== null) {
		if (!scopeAllows(paths.projectRoot, writeScope, own.target)) {
			return {
				allowed: false,
				shape,
				rule: "write-scope",
				detail: "outside-declared-write-scope",
				target: own.target,
			};
		}
		return { allowed: true, shape, domain: own.domain, target: own.target };
	}
	// A token carrying a directory component is always a path attempt, never
	// prose: anything outside the faces above is refused. (The shape table alone
	// is not enough — `../..` strips to `punct`, which must still fail closed.)
	if (/[\\/]/.test(pathToken) || WRITE_TARGET_PATH_SHAPES.has(shape)) {
		return { allowed: false, shape, rule: "scope", detail: "outside-write-surface", target };
	}
	return { allowed: true, shape, target };
}

// ── Own write face (own task dir + own-key evidence) ─────────────────────────

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
export function evidenceDirOf(paths: WriteSurfacePaths): string | undefined {
	return paths.keyDir === undefined ? undefined : normalizeForCompare(paths.keyDir, "evidence");
}

/** The matched own write face for one token. */
export interface OwnWriteTarget {
	domain: "task-dir" | "evidence";
	target: string;
}

/** Resolve `pathToken` against the own task dir and own-key evidence tree, or
 * null when it is outside both. The basename channel (task-dir basenames such
 * as `report.md`) belongs to the dispatch/`worker_file` face and is disabled
 * for the shell guard, which only ever sees cwd-resolved literals. */
export function resolveOwnWriteTarget(
	pathToken: string,
	paths: WriteSurfacePaths,
	opts?: { evidenceBasis?: EvidenceBasis; basenameChannel?: boolean },
): OwnWriteTarget | null {
	const target = normalizeForCompare(paths.projectRoot, pathToken);
	const task = normalizeForCompare(paths.projectRoot, paths.taskDir);
	if (isSameOrUnder(task, target)) return { domain: "task-dir", target };
	const evidenceTarget = matchEvidenceTarget(pathToken, paths, opts?.evidenceBasis ?? "dual");
	if (evidenceTarget !== null) return { domain: "evidence", target: evidenceTarget };
	if ((opts?.basenameChannel ?? true) && !/[\\/]/.test(pathToken) && WORKER_FILE_NAME_RE.test(pathToken)) {
		return { domain: "task-dir", target: path.join(paths.taskDir, pathToken) };
	}
	return null;
}

/** Resolve `pathToken` against the own-key evidence tree on the requested
 * basis, or null. The evidence directory itself (`evidence`, `evidence/`) is
 * not a writable target; anything strictly inside it is, extension-agnostic. */
function matchEvidenceTarget(pathToken: string, paths: WriteSurfacePaths, basis: EvidenceBasis): string | null {
	const evidenceDir = evidenceDirOf(paths);
	if (evidenceDir === undefined) return null;
	const bases: string[] =
		basis === "dual" && paths.keyDir !== undefined ? [paths.projectRoot, paths.keyDir] : [paths.projectRoot];
	for (const base of bases) {
		const absBase = normalizeForCompare(base, pathToken);
		if (absBase !== evidenceDir && isSameOrUnder(evidenceDir, absBase)) return absBase;
	}
	return null;
}
