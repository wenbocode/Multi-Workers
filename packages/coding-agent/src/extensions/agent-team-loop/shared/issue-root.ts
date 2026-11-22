/**
 * shared/issue-root.ts — explicit, same-machine MW development repo binding
 * (mw-issue-feedback T-02, design D-003 / DRQ-1).
 *
 * The authority for product feedback lives in the MW DEVELOPMENT repo, not in
 * the project the pi window happens to be running in. The only way to locate
 * that repo is a machine-level pointer file written by an explicit,
 * user-confirmed bind performed from the dev repo's own pi window. Every other
 * project is a READ-ONLY consumer of that pointer.
 *
 * Hard rules:
 *  - No cwd discovery, no upward `.agenticdoc` probing, no `findMwPy()` /
 *    `.mw-py-path` / installed-bundle fallback, no `MW_PY` override. A missing,
 *    malformed, ambiguous or unreachable binding is a structured error, never a
 *    guess. `process.cwd()` is not called anywhere in this module.
 *  - Both sides of every comparison are canonicalized with realpath + Windows
 *    device-prefix/case folding (P-027/P-029), so 8.3 names, junctions and
 *    `..` aliases of ONE repo stay one repo.
 *  - The pointer plus three repo markers are structural checks only. They do
 *    NOT prove repo identity, authenticate a writer, or create an OS permission
 *    grant: another process running as the same OS user can edit the pointer or
 *    the authoritative files directly. AC-006 covers the MW entry path only.
 *  - Resolution never writes. Binding persists exactly one pointer file after
 *    confirmation + dev-window identity + marker checks all pass, and never
 *    creates directories (no machine-config side effects by default). During
 *    the short transaction it uses a fixed `.tmp` bind lock and a unique `wx`
 *    payload temp; each is removed only by the call that created it. A foreign
 *    `.tmp` is another writer's lock and must never be deleted.
 *  - `IssueDevRootLocator` is injectable (`env` / `home` / `pointerFile`) so
 *    offline two-project fixtures use temp dirs: no network, no real machine
 *    configuration, no global pointer writes.
 *
 * Downstream contract (T-03 store / T-04 window):
 *  - `resolveIssueDevRoot({ projectRoot, ... })` → canonicalRoot/canonicalMwPy
 *    for authoritative reads/writes; `projectRoot`/`mode` are for the CURRENT
 *    project's local ID/pending index only, never for deriving the authority.
 *  - `bindIssueDevRoot(...)` is the only writer; call it behind a real TUI
 *    `ctx.ui.confirm(...) === true` gate with the window's project root.
 *  - On `ok: false`, surface `formatIssueDevRootFailure(...)` to the user;
 *    never fall back to a guessed root.
 */

import { createHash, randomUUID } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

export const ISSUE_DEV_ROOT_SCHEMA = 1;
export const ISSUE_DEV_ROOT_KIND = "mw-issue-dev-root";
export const ISSUE_DEV_ROOT_WRITTEN_BY = "agent-team-loop/issue-root";

/** Whole-file override (absolute path). Injected by tests / explicit setup. */
export const ISSUE_DEV_ROOT_FILE_ENV = "MW_ISSUE_DEV_ROOT_FILE";
/** Machine-home override, checked before HOME/USERPROFILE. */
export const ISSUE_DEV_ROOT_HOME_ENV = "MW_ISSUE_DEV_ROOT_HOME";
export const ISSUE_DEV_ROOT_POINTER_DIR = ".agents";
export const ISSUE_DEV_ROOT_POINTER_BASENAME = "mw-issue-dev-root.json";
export const ISSUE_DEV_ROOT_MW_PY_RELATIVE = "packages/multi-workers/mw.py";

/** Stored verbatim in every pointer: the binding is a local fact, not a grant. */
export const ISSUE_DEV_ROOT_NOTICE =
	"Explicit local pointer to the MW development repo. Not an OS permission grant, " +
	"not writer authentication, not proof of repo identity, and not protection against " +
	"a same-OS user editing files directly.";

export interface IssueDevRootMarker {
	readonly id: string;
	readonly relative: string;
	readonly kind: "file" | "dir";
}

/** Structural marker set. All three must be real entries inside the bound root. */
export const ISSUE_DEV_ROOT_MARKERS: readonly IssueDevRootMarker[] = [
	{ id: "mw_py", relative: ISSUE_DEV_ROOT_MW_PY_RELATIVE, kind: "file" },
	{ id: "extension_dir", relative: "packages/coding-agent/src/extensions/agent-team-loop", kind: "dir" },
	{ id: "goal", relative: ".agenticdoc/goal.md", kind: "file" },
];

/** Exact pointer key set — pinned by issue-root.test.ts. */
export const ISSUE_DEV_ROOT_POINTER_KEYS = [
	"schema",
	"kind",
	"canonical_dev_root",
	"canonical_mw_py",
	"marker_fingerprint",
	"written_by",
	"written_at",
	"notice",
] as const;

export interface IssueDevRootPointer {
	schema: 1;
	kind: "mw-issue-dev-root";
	/** Absolute, canonical (realpath) path of the dev repo root. */
	canonical_dev_root: string;
	/** Absolute, canonical path of <root>/packages/multi-workers/mw.py. */
	canonical_mw_py: string;
	/** Structural fingerprint of the marker set (not identity/authorization). */
	marker_fingerprint: string;
	written_by: "agent-team-loop/issue-root";
	written_at: string;
	notice: string;
}

export type IssueDevRootErrorCode =
	| "E-ISSUE-DEV-ROOT-NOT_CONFIGURED"
	| "E-ISSUE-DEV-ROOT-INVALID_POINTER"
	| "E-ISSUE-DEV-ROOT-UNREACHABLE"
	| "E-ISSUE-DEV-ROOT-AMBIGUOUS"
	| "E-ISSUE-DEV-ROOT-MARKER_MISMATCH"
	| "E-ISSUE-DEV-ROOT-PROJECT_UNREACHABLE"
	| "E-ISSUE-DEV-ROOT-BIND_NOT_CONFIRMED"
	| "E-ISSUE-DEV-ROOT-BIND_FOREIGN_WINDOW"
	| "E-ISSUE-DEV-ROOT-BIND_POINTER_UNREACHABLE";

export interface IssueDevRootFailure {
	ok: false;
	code: IssueDevRootErrorCode;
	/** Human-readable, explicit reason (no silent fallback). */
	reason: string;
	pointerPath: string | null;
	wrote: false;
}

export interface IssueDevRootResolved {
	ok: true;
	/** Canonical dev repo root: the only authority for feedback records. */
	canonicalRoot: string;
	canonicalMwPy: string;
	/** Validated absolute marker paths inside canonicalRoot. */
	markers: readonly string[];
	pointerPath: string;
	/** Canonical CURRENT project root; never an authority candidate. */
	projectRoot: string;
	mode: "local" | "external";
	source: "explicit-binding";
	wrote: false;
}

export interface IssueDevRootBound {
	ok: true;
	pointerPath: string;
	canonicalRoot: string;
	canonicalMwPy: string;
	pointer: IssueDevRootPointer;
	wrote: true;
}

export type IssueDevRootResult = IssueDevRootResolved | IssueDevRootFailure;
export type BindIssueDevRootResult = IssueDevRootBound | IssueDevRootFailure;

/** Injectable pointer discovery. Tests pass temp `home`/`pointerFile` so no
 * real machine config is read or written. */
export interface IssueDevRootLocator {
	env?: NodeJS.ProcessEnv;
	home?: string;
	pointerFile?: string;
}

export interface ResolveIssueDevRootOptions extends IssueDevRootLocator {
	/** Current project root (for local ID/pending index + mode only). */
	projectRoot: string;
	/** Optional caller-supplied roots to cross-check; disagreement is
	 * AMBIGUOUS. This module itself never consults installed scripts. */
	crossCheckRoots?: readonly string[];
}

export interface BindIssueDevRootOptions {
	/** The pi window's own project root; must BE the dev repo root. */
	callerProjectRoot: string;
	/** Explicitly chosen dev repo root (not derived from cwd). */
	candidateRoot: string;
	/** Result of a real user confirmation in a trusted TUI window. */
	userConfirmed: boolean;
	/** Absolute pointer file to write. Required: never writes real machine
	 * config implicitly, and its parent directory must already exist. */
	pointerFile: string;
	now?: () => Date;
}

/** Fingerprint of the marker structure, not of repo contents. */
export function issueDevRootMarkerFingerprint(): string {
	const lines = ISSUE_DEV_ROOT_MARKERS.map((m) => `${m.id}:${m.kind}:${m.relative}`).join("\n");
	return `sha256:${createHash("sha256").update(`mw-issue-dev-root/markers/v1\n${lines}\n`).digest("hex")}`;
}

/** Single-source pointer location. Precedence: explicit injection → whole-file
 * env override → machine-home override → HOME → USERPROFILE → os.homedir().
 * Exactly one path is consulted; nothing is created and no cwd is used. */
export function issueDevRootPointerPath(locator: IssueDevRootLocator = {}): string {
	if (locator.pointerFile) return locator.pointerFile;
	const env = locator.env ?? process.env;
	const override = (env[ISSUE_DEV_ROOT_FILE_ENV] ?? "").trim();
	if (override) return override;
	const home = locator.home ?? firstMachineHome(env);
	return path.join(home, ISSUE_DEV_ROOT_POINTER_DIR, ISSUE_DEV_ROOT_POINTER_BASENAME);
}

function firstMachineHome(env: NodeJS.ProcessEnv): string {
	for (const name of [ISSUE_DEV_ROOT_HOME_ENV, "HOME", "USERPROFILE"]) {
		const value = (env[name] ?? "").trim();
		if (value) return value;
	}
	return os.homedir();
}

/** UTF-8 + LF, no BOM, fixed key order: one canonical on-disk format. */
export function serializeIssueDevRootPointer(pointer: IssueDevRootPointer): string {
	return `${JSON.stringify(
		{
			schema: pointer.schema,
			kind: pointer.kind,
			canonical_dev_root: pointer.canonical_dev_root,
			canonical_mw_py: pointer.canonical_mw_py,
			marker_fingerprint: pointer.marker_fingerprint,
			written_by: pointer.written_by,
			written_at: pointer.written_at,
			notice: pointer.notice,
		},
		null,
		2,
	)}\n`;
}

export type PointerParseResult = { ok: true; pointer: IssueDevRootPointer } | { ok: false; reason: string };

/** Strict pointer parsing: exact key set, absolute canonical paths, pinned
 * schema/kind/writer/notice/marker fingerprint. Relative paths are rejected
 * instead of being resolved against cwd. */
export function parseIssueDevRootPointer(raw: string): PointerParseResult {
	let parsed: unknown;
	try {
		parsed = JSON.parse(raw);
	} catch (err) {
		return { ok: false, reason: `pointer is not valid JSON: ${errorText(err)}` };
	}
	if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
		return { ok: false, reason: "pointer must be a JSON object" };
	}
	const obj = parsed as Record<string, unknown>;
	const keys = Object.keys(obj).sort();
	const expected = [...ISSUE_DEV_ROOT_POINTER_KEYS].sort();
	if (keys.length !== expected.length || keys.some((key, i) => key !== expected[i])) {
		return { ok: false, reason: `pointer fields must be exactly [${expected.join(", ")}], got [${keys.join(", ")}]` };
	}
	if (obj.schema !== ISSUE_DEV_ROOT_SCHEMA) {
		return { ok: false, reason: `pointer schema must be ${ISSUE_DEV_ROOT_SCHEMA}` };
	}
	if (obj.kind !== ISSUE_DEV_ROOT_KIND) {
		return { ok: false, reason: `pointer kind must be ${ISSUE_DEV_ROOT_KIND}` };
	}
	for (const field of ["canonical_dev_root", "canonical_mw_py"] as const) {
		const value = obj[field];
		if (typeof value !== "string" || value.trim() === "") {
			return { ok: false, reason: `pointer ${field} must be a non-empty string` };
		}
		if (!path.isAbsolute(value)) {
			return { ok: false, reason: `pointer ${field} must be absolute; cwd resolution is not allowed` };
		}
	}
	if (obj.marker_fingerprint !== issueDevRootMarkerFingerprint()) {
		return { ok: false, reason: "pointer marker_fingerprint does not match the required repo marker set" };
	}
	if (obj.written_by !== ISSUE_DEV_ROOT_WRITTEN_BY) {
		return { ok: false, reason: `pointer written_by must be ${ISSUE_DEV_ROOT_WRITTEN_BY}` };
	}
	if (typeof obj.written_at !== "string" || obj.written_at.trim() === "") {
		return { ok: false, reason: "pointer written_at must be a non-empty ISO timestamp" };
	}
	if (obj.notice !== ISSUE_DEV_ROOT_NOTICE) {
		return { ok: false, reason: "pointer notice must state that this binding is not an OS permission grant" };
	}
	return {
		ok: true,
		pointer: {
			schema: ISSUE_DEV_ROOT_SCHEMA,
			kind: ISSUE_DEV_ROOT_KIND,
			canonical_dev_root: obj.canonical_dev_root as string,
			canonical_mw_py: obj.canonical_mw_py as string,
			marker_fingerprint: obj.marker_fingerprint as string,
			written_by: ISSUE_DEV_ROOT_WRITTEN_BY,
			written_at: obj.written_at as string,
			notice: obj.notice as string,
		},
	};
}

/** User-visible text for a failure; callers must not substitute a guessed root. */
export function formatIssueDevRootFailure(failure: IssueDevRootFailure): string {
	const where = failure.pointerPath ? ` (pointer: ${failure.pointerPath})` : "";
	return `${failure.code}: ${failure.reason}${where}`;
}

function fail(code: IssueDevRootErrorCode, reason: string, pointerPath: string | null): IssueDevRootFailure {
	return { ok: false, code, reason, pointerPath, wrote: false };
}

function errorText(err: unknown): string {
	return err instanceof Error ? err.message : String(err);
}

function closeQuietly(fd: number): void {
	try {
		fs.closeSync(fd);
	} catch {
		// The descriptor is already closed or unusable; cleanup continues.
	}
}

function unlinkQuietly(file: string): void {
	try {
		fs.unlinkSync(file);
	} catch {
		// The file was consumed by the atomic rename or is already gone.
	}
}

function nodeErrorCode(err: unknown): string | null {
	if (err instanceof Error && "code" in err && typeof (err as { code?: unknown }).code === "string") {
		return (err as { code: string }).code;
	}
	return null;
}

/** Node's native realpath returns `\\?\` extended-length paths on Windows.
 * Strip it so joined markers, comparisons and outputs are ordinary paths. */
function stripDevicePrefix(value: string): string {
	if (process.platform !== "win32") return value;
	if (value.startsWith("\\\\?\\UNC\\")) return `\\\\${value.slice(8)}`;
	if (value.startsWith("\\\\?\\")) return value.slice(4);
	return value;
}

/** Case/prefix-insensitive comparison key (P-027: fold BOTH sides). */
function fold(value: string): string {
	const normalized = path.normalize(stripDevicePrefix(value));
	return process.platform === "win32" ? normalized.toLowerCase() : normalized;
}

function isInside(root: string, target: string): boolean {
	const r = fold(root);
	const t = fold(target);
	if (r === t) return true;
	const sep = r.endsWith(path.sep) || r.endsWith("/") ? "" : path.sep;
	return t.startsWith(`${r}${sep}`);
}

interface CanonicalPath {
	path: string;
}

function canonicalize(raw: string, kind: "dir" | "file"): CanonicalPath | { error: string } {
	if (!path.isAbsolute(raw)) {
		return { error: `'${raw}' is not absolute; cwd resolution is not allowed` };
	}
	try {
		const st = fs.statSync(raw);
		if (kind === "dir" ? !st.isDirectory() : !st.isFile()) {
			return { error: `'${raw}' is not a ${kind === "dir" ? "directory" : "file"}` };
		}
		return { path: stripDevicePrefix(fs.realpathSync.native(raw)) };
	} catch (err) {
		return { error: `'${raw}' is unreachable: ${errorText(err)}` };
	}
}

interface ValidatedRoot {
	canonicalRoot: string;
	canonicalMwPy: string;
	markers: readonly string[];
}

/** All markers must exist, have the right type, sit at their exact relative
 * path AND realpath inside the bound root. A marker that is a link to another
 * tree (junction/symlink) is rejected: no writing into a foreign project. */
function validateDevRoot(
	canonicalRoot: string,
): { ok: true; value: ValidatedRoot } | { ok: false; code: IssueDevRootErrorCode; reason: string } {
	const markers: string[] = [];
	let canonicalMwPy = path.join(canonicalRoot, ISSUE_DEV_ROOT_MW_PY_RELATIVE);
	for (const marker of ISSUE_DEV_ROOT_MARKERS) {
		const joined = path.join(canonicalRoot, marker.relative);
		let real: string;
		let st: fs.Stats;
		try {
			st = fs.statSync(joined);
			real = stripDevicePrefix(fs.realpathSync.native(joined));
		} catch (err) {
			return {
				ok: false,
				code: "E-ISSUE-DEV-ROOT-MARKER_MISMATCH",
				reason: `repo marker '${marker.relative}' is missing or unreadable: ${errorText(err)}`,
			};
		}
		if (marker.kind === "file" ? !st.isFile() : !st.isDirectory()) {
			return {
				ok: false,
				code: "E-ISSUE-DEV-ROOT-MARKER_MISMATCH",
				reason: `repo marker '${marker.relative}' is not a ${marker.kind === "file" ? "file" : "directory"}`,
			};
		}
		if (fold(real) !== fold(joined) || !isInside(canonicalRoot, real)) {
			return {
				ok: false,
				code: "E-ISSUE-DEV-ROOT-MARKER_MISMATCH",
				reason: `repo marker '${marker.relative}' resolves outside the bound root (${real}); refusing a foreign tree`,
			};
		}
		if (marker.id === "mw_py") canonicalMwPy = real;
		markers.push(real);
	}
	return { ok: true, value: { canonicalRoot, canonicalMwPy, markers } };
}

/**
 * READ-ONLY resolution of the explicitly bound dev repo root. Missing,
 * malformed, ambiguous and unreachable bindings each produce a distinct
 * structured error. Nothing is created, written or derived from cwd/installed
 * scripts — not even a mkdir on a candidate root.
 */
export function resolveIssueDevRoot(options: ResolveIssueDevRootOptions): IssueDevRootResult {
	const pointerPath = issueDevRootPointerPath(options);
	if (!path.isAbsolute(pointerPath)) {
		return fail(
			"E-ISSUE-DEV-ROOT-INVALID_POINTER",
			`pointer path '${pointerPath}' is not absolute; cwd resolution is not allowed`,
			pointerPath,
		);
	}
	let raw: string;
	try {
		raw = fs.readFileSync(pointerPath, "utf8");
	} catch (err) {
		const code = nodeErrorCode(err);
		const missing = code === "ENOENT" || code === "ENOTDIR";
		return fail(
			missing ? "E-ISSUE-DEV-ROOT-NOT_CONFIGURED" : "E-ISSUE-DEV-ROOT-UNREACHABLE",
			missing
				? `no explicit MW dev repo binding exists at '${pointerPath}'; bind it from the dev repo pi window first`
				: `pointer is unreadable: ${errorText(err)}`,
			pointerPath,
		);
	}
	if (raw.charCodeAt(0) === 0xfeff) {
		return fail(
			"E-ISSUE-DEV-ROOT-INVALID_POINTER",
			"pointer has a UTF-8 BOM; expected plain UTF-8 + LF",
			pointerPath,
		);
	}
	const parsed = parseIssueDevRootPointer(raw);
	if (!parsed.ok) {
		return fail("E-ISSUE-DEV-ROOT-INVALID_POINTER", parsed.reason, pointerPath);
	}
	const root = canonicalize(parsed.pointer.canonical_dev_root, "dir");
	if ("error" in root) {
		return fail("E-ISSUE-DEV-ROOT-UNREACHABLE", `bound dev root ${root.error}`, pointerPath);
	}
	const mwPy = canonicalize(parsed.pointer.canonical_mw_py, "file");
	if ("error" in mwPy) {
		return fail("E-ISSUE-DEV-ROOT-UNREACHABLE", `bound mw.py ${mwPy.error}`, pointerPath);
	}
	// Two independent canonical candidates that disagree = ambiguity, not a guess.
	// mw.py is <root>/packages/multi-workers/mw.py, so three dirnames reach <root>.
	const derivedRoot = path.dirname(path.dirname(path.dirname(mwPy.path)));
	if (fold(derivedRoot) !== fold(root.path)) {
		return fail(
			"E-ISSUE-DEV-ROOT-AMBIGUOUS",
			`pointer names two different dev roots: root=${root.path} vs mw.py-derived=${derivedRoot}`,
			pointerPath,
		);
	}
	const validated = validateDevRoot(root.path);
	if (!validated.ok) {
		return fail(validated.code, validated.reason, pointerPath);
	}
	if (fold(mwPy.path) !== fold(validated.value.canonicalMwPy)) {
		return fail(
			"E-ISSUE-DEV-ROOT-AMBIGUOUS",
			`pointer mw.py (${mwPy.path}) disagrees with the bound root's marker (${validated.value.canonicalMwPy})`,
			pointerPath,
		);
	}
	for (const candidate of options.crossCheckRoots ?? []) {
		const checked = canonicalize(candidate, "dir");
		if ("error" in checked || fold(checked.path) !== fold(root.path)) {
			return fail(
				"E-ISSUE-DEV-ROOT-AMBIGUOUS",
				`cross-check root '${candidate}' disagrees with bound root ${root.path}; refusing to choose`,
				pointerPath,
			);
		}
	}
	const project = canonicalize(options.projectRoot, "dir");
	if ("error" in project) {
		return fail("E-ISSUE-DEV-ROOT-PROJECT_UNREACHABLE", `current project root ${project.error}`, pointerPath);
	}
	return {
		ok: true,
		canonicalRoot: root.path,
		canonicalMwPy: validated.value.canonicalMwPy,
		markers: validated.value.markers,
		pointerPath,
		projectRoot: project.path,
		mode: fold(project.path) === fold(root.path) ? "local" : "external",
		source: "explicit-binding",
		wrote: false,
	};
}

/**
 * Explicit bind: only from the MW dev repo's own pi window, only after user
 * confirmation. Persists exactly one pointer file via a fixed `wx` bind lock,
 * a unique `wx` payload temp + rename; never creates directories and never
 * touches any candidate repo root. A competing bind fails visibly instead of
 * silently replacing the pointer, and cleanup removes only files this call
 * created. Pointer parent must already exist, so an offline fixture stays
 * fully self-contained.
 */
export function bindIssueDevRoot(options: BindIssueDevRootOptions): BindIssueDevRootResult {
	const pointerPath = options.pointerFile;
	if (options.userConfirmed !== true) {
		return fail(
			"E-ISSUE-DEV-ROOT-BIND_NOT_CONFIRMED",
			"binding requires an explicit user confirmation in the dev repo pi window",
			pointerPath,
		);
	}
	if (!path.isAbsolute(pointerPath)) {
		return fail(
			"E-ISSUE-DEV-ROOT-BIND_POINTER_UNREACHABLE",
			`pointer file '${pointerPath}' must be absolute; cwd resolution is not allowed`,
			pointerPath,
		);
	}
	const parent = path.dirname(pointerPath);
	let parentReal: string;
	try {
		if (!fs.statSync(parent).isDirectory()) {
			return fail(
				"E-ISSUE-DEV-ROOT-BIND_POINTER_UNREACHABLE",
				`pointer parent '${parent}' is not a directory; no directory is created`,
				pointerPath,
			);
		}
		// Canonicalize the parent too: 8.3 short names / junctions must not make
		// a pointer inside the dev repo look like it lives elsewhere (P-027).
		parentReal = stripDevicePrefix(fs.realpathSync.native(parent));
	} catch (err) {
		return fail(
			"E-ISSUE-DEV-ROOT-BIND_POINTER_UNREACHABLE",
			`pointer parent is unreachable: ${errorText(err)}; no directory is created`,
			pointerPath,
		);
	}
	const candidate = canonicalize(options.candidateRoot, "dir");
	if ("error" in candidate) {
		return fail("E-ISSUE-DEV-ROOT-UNREACHABLE", `candidate dev root ${candidate.error}`, pointerPath);
	}
	const caller = canonicalize(options.callerProjectRoot, "dir");
	if ("error" in caller) {
		return fail("E-ISSUE-DEV-ROOT-UNREACHABLE", `caller pi window project root ${caller.error}`, pointerPath);
	}
	if (fold(caller.path) !== fold(candidate.path)) {
		return fail(
			"E-ISSUE-DEV-ROOT-BIND_FOREIGN_WINDOW",
			`binding is only allowed from the MW dev repo's own pi window (caller=${caller.path}, candidate=${candidate.path})`,
			pointerPath,
		);
	}
	if (isInside(candidate.path, path.join(parentReal, path.basename(pointerPath)))) {
		return fail(
			"E-ISSUE-DEV-ROOT-BIND_POINTER_UNREACHABLE",
			"machine-level pointer must not live inside the dev repo; other projects could not discover it",
			pointerPath,
		);
	}
	const validated = validateDevRoot(candidate.path);
	if (!validated.ok) {
		return fail(validated.code, validated.reason, pointerPath);
	}
	const pointer: IssueDevRootPointer = {
		schema: ISSUE_DEV_ROOT_SCHEMA,
		kind: ISSUE_DEV_ROOT_KIND,
		canonical_dev_root: candidate.path,
		canonical_mw_py: validated.value.canonicalMwPy,
		marker_fingerprint: issueDevRootMarkerFingerprint(),
		written_by: ISSUE_DEV_ROOT_WRITTEN_BY,
		written_at: (options.now ?? (() => new Date()))().toISOString(),
		notice: ISSUE_DEV_ROOT_NOTICE,
	};
	const lockPath = `${pointerPath}.tmp`;
	const lockToken = `${process.pid}:${randomUUID()}`;
	const tmp = `${pointerPath}.${process.pid}.${randomUUID()}.tmp`;
	let lockFd: number | undefined;
	let tmpFd: number | undefined;
	let ownsLock = false;
	let ownsTmp = false;
	let lockTokenWritten = false;
	try {
		// The fixed .tmp path is an exclusive bind lock, not the payload file:
		// if another writer already owns it, `wx` fails and this call leaves it
		// untouched. The unique payload temp cannot collide with that lock.
		lockFd = fs.openSync(lockPath, "wx", 0o600);
		ownsLock = true;
		fs.writeFileSync(lockFd, lockToken, "utf8");
		lockTokenWritten = true;
		fs.closeSync(lockFd);
		lockFd = undefined;

		tmpFd = fs.openSync(tmp, "wx", 0o600);
		ownsTmp = true;
		fs.writeFileSync(tmpFd, serializeIssueDevRootPointer(pointer), "utf8");
		fs.fsyncSync(tmpFd);
		fs.closeSync(tmpFd);
		tmpFd = undefined;
		fs.renameSync(tmp, pointerPath);
		ownsTmp = false;
	} catch (err) {
		const detail =
			nodeErrorCode(err) === "EEXIST"
				? `another explicit bind already holds the pointer lock (${lockPath})`
				: errorText(err);
		return fail(
			"E-ISSUE-DEV-ROOT-BIND_POINTER_UNREACHABLE",
			`could not write pointer atomically: ${detail}`,
			pointerPath,
		);
	} finally {
		if (lockFd !== undefined) closeQuietly(lockFd);
		if (tmpFd !== undefined) closeQuietly(tmpFd);
		if (ownsTmp) unlinkQuietly(tmp);
		if (ownsLock) {
			if (!lockTokenWritten) {
				unlinkQuietly(lockPath);
			} else {
				try {
					if (fs.readFileSync(lockPath, "utf8") === lockToken) fs.unlinkSync(lockPath);
				} catch {
					// A replaced or unreadable lock belongs to another writer; never delete it.
				}
			}
		}
	}
	return {
		ok: true,
		pointerPath,
		canonicalRoot: candidate.path,
		canonicalMwPy: validated.value.canonicalMwPy,
		pointer,
		wrote: true,
	};
}
