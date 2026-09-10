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

/** Default per-worker caps (D-106): 8 read-ish calls, 64 KiB of read bytes. */
export const DEFAULT_READ_FILE_CAP = 8;
export const DEFAULT_READ_BYTE_CAP = 65_536;

/** Rejection rule identifiers — recorded with every blocked call (AC-009). */
export type ReadScopeRule = "scope" | "cap-file" | "cap-byte";

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
	/** Scope entries (project-root relative or absolute). A present-but-empty
	 * list blocks every read-ish call (fail-closed on a misconfigured task). */
	scope: string[];
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

const IS_WIN32 = process.platform === "win32";

/** Segment-boundary containment: candidate equals prefix, or begins with
 * prefix + one separator. win32 compares lower-cased on both sides (drive
 * letters); other platforms are byte-exact. */
export function isSameOrUnder(prefix: string, candidate: string): boolean {
	const a = IS_WIN32 ? prefix.toLowerCase() : prefix;
	const c = IS_WIN32 ? candidate.toLowerCase() : candidate;
	return c === a || c.startsWith(`${a}${path.sep}`);
}

/** Normalize one path (scope entry or request) for comparison: resolve
 * against projectRoot (lexical .. collapsing), then realpathSync (symlinks
 * and junctions). A nonexistent tail is rejoined onto the realpath of its
 * deepest existing ancestor — the symlink above a missing tail still
 * resolves, so normalization cannot be bypassed. */
export function normalizeForCompare(projectRoot: string, p: string): string {
	const abs = path.resolve(projectRoot, p);
	let cur = abs;
	const tail: string[] = [];
	for (;;) {
		try {
			return path.join(fs.realpathSync(cur), ...tail);
		} catch {
			const parent = path.dirname(cur);
			if (parent === cur) return abs; // reached the fs root unresolved — lexical is the best available
			tail.unshift(path.basename(cur));
			cur = parent;
		}
	}
}

/** Containment check (D-106 steps 1–4): does requestPath resolve inside one
 * of the scope entries? */
export function isWithinScope(projectRoot: string, scopeEntries: string[], requestPath: string): boolean {
	const req = normalizeForCompare(projectRoot, requestPath);
	return scopeEntries.some((entry) => isSameOrUnder(normalizeForCompare(projectRoot, entry), req));
}

function defaultStatSize(absolutePath: string): number {
	try {
		return fs.statSync(absolutePath).size;
	} catch {
		return 0; // unreadable/nonexistent: the read itself fails, charge nothing
	}
}

/**
 * The full gate for one read-ish tool call: containment first, then the file
 * cap, then (read only) the byte cap. statSize is injectable for tests; the
 * default stats the resolved path (the read tool loads whole files, so the
 * file size is what the call actually reads).
 */
export function checkReadScopeCall(
	projectRoot: string,
	config: ReadScopeConfig,
	state: ReadScopeState,
	tool: string,
	rawPath: string,
	statSize: (absolutePath: string) => number = defaultStatSize,
): ReadScopeVerdict {
	if (!isWithinScope(projectRoot, config.scope, rawPath)) {
		return {
			allowed: false,
			rule: "scope",
			reason:
				`read_scope: blocked ${tool} of ${rawPath}: the path resolves outside the allowed read scope ` +
				`(${config.scope.join(", ")}) [rule=scope]`,
			chargedBytes: 0,
		};
	}
	if (state.allowedCalls >= config.fileCap) {
		return {
			allowed: false,
			rule: "cap-file",
			reason:
				`read_scope: blocked ${tool} of ${rawPath}: the read file cap is reached ` +
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
				reason:
					`read_scope: blocked ${tool} of ${rawPath}: the read byte cap would be exceeded ` +
					`(${state.bytesRead}/${config.byteCap} bytes already read, this file is ${chargedBytes}B) [rule=cap-byte]`,
				chargedBytes: 0,
			};
		}
	}
	return { allowed: true, chargedBytes };
}

/** Build the enforcement config from parsed task.md meta. Undefined when the
 * task carries no read_scope: interception disabled (AC-012 red line —
 * manual/legacy tasks behave exactly as before). Missing or invalid caps
 * fall back to the defaults, never an error. */
export function readScopeConfigFromMeta(meta: {
	readScope?: string[];
	readFileCap?: number;
	readByteCap?: number;
}): ReadScopeConfig | undefined {
	if (meta.readScope === undefined) return undefined;
	return {
		scope: meta.readScope,
		fileCap: meta.readFileCap ?? DEFAULT_READ_FILE_CAP,
		byteCap: meta.readByteCap ?? DEFAULT_READ_BYTE_CAP,
	};
}
