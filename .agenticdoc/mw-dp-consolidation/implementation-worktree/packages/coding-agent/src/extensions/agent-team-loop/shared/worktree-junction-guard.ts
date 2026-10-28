import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { parseBashSegments } from "./bash-segments.ts";

/**
 * Worktree junction guard (mw-worktree-junction-guard G1, AC-001/002/003).
 *
 * Why: `git worktree remove --force <path>` walks THROUGH reparse points
 * (Windows junctions) inside the worktree and recursively deletes the link
 * TARGET. The 2026-10-09 accident ran
 * `cd H:/git/Multi-Workers; git worktree remove --force "$env:TEMP\qg-head"`
 * and removed 3,456 tracked files from the shared tree (8 package trees +
 * packages/tui) plus other sessions' uncommitted work, because the worktree
 * contained a `node_modules` junction pointing back at the real tree. The
 * target was not even a literal path: it was an environment interpolation.
 *
 * This guard is the first mechanical guarantee, not a sandbox (same class as
 * shared/protected-config.ts and shared/implementation-gate.ts): before a
 * `git worktree remove|rm` bash call executes it resolves the operand,
 * scans the target tree, and blocks when it cannot prove the tree is free of
 * reparse points. The refusal text carries the copyable replacement command
 * `mw worktree rm "<worktree>"` (G2 six-step transaction).
 *
 * Boundaries (design D-4 + decision D-11, extended by D-19): covers
 * `git worktree remove|rm` (incl. `--force`, `-C`, and command-internal
 * location bases `cd`/`Set-Location`/`pushd`/`sl`/`chdir`, incl. cmd `cd /d`)
 * and the penetrating forms `<path>/`, `<path>/*`, `<path>\*` for `rm` (incl.
 * `-r`/`-rf`/`-f`) plus the PowerShell aliases `Remove-Item`/`ri`/`del`/
 * `erase`/`rd`/`rmdir` (D-19: pi pins its shell to PowerShell, so those
 * spellings have identical reach). A separator-free, glob-free operand stays
 * out of scope: `rm -rf <link>`, `rmdir /S`, and `robocopy /MIR` are NOT
 * covered, and `checkBashWriteTarget` / `WRITE_VERBS` are deliberately not
 * extended. A penetrating hit on a
 * registered worktree keeps the §4.3 text (`mw worktree rm "<path>"`); any
 * other target gets the second text with the per-link
 * `cmd /c rmdir "<link>"` prescription (AC-002 extension, D-11).
 *
 * Parsing is structural (shared/bash-segments.ts `parseBashSegments`), never
 * a word-list match — the `dd` false positive in protected-config's
 * WRITE_VERB_RE is the counter-example this guard must not repeat.
 *
 * Registered in EVERY mode (index.ts, next to the other guards) so a worker
 * window is covered too.
 *
 * AC-014 (D-13, audit N-06): the guard also hangs off the `user_bash` event,
 * the channel used by the TUI `!`/`!!` prefix and the RPC `bash` command. That
 * path never reaches the bash tool and never fires `tool_call`, so without
 * this hook `! git worktree remove --force <worktree-with-a-junction>` is the
 * exact accident shape with no guard in front of it. The handler reuses the
 * same `decideWorktreeRemove` verdict and text; returning `result` is the
 * documented short-circuit (the caller uses it INSTEAD of executing — see
 * `extensionRunner.emitUserBash` consumers in modes/interactive and modes/rpc).
 */

/** basis values are a fixed vocabulary (design §3.2). */
export interface WorktreeGuardVerdict {
	block: boolean;
	/** AC-002: link path + target + copyable `mw worktree rm "<path>"`. */
	reason?: string;
	/** Resolved absolute worktree path (audit). */
	target?: string;
	/** Absolute paths of the reparse points found in the target tree. */
	hits: string[];
	/** resolved | unresolved:<var> | glob | bare-name-ambiguous |
	 * reparse-point | delete-penetration | target-absent |
	 * scan-error:<code> | not-remove */
	basis: string;
}

/**
 * Entry budget for one synchronous scan. The `tool_call` handler runs on the
 * agent loop with no timeout wrapper (core/extensions/runner.ts awaits
 * handlers bare), so a pathological tree must not block the loop forever:
 * over budget = block (fail-closed). 200,000 entries is ~7x the whole repo's
 * pruned entry count (design §5.2 measured 43,412 for a full-repo walk).
 */
const MAX_SCAN_ENTRIES = 200_000;

/** git global options that consume the following word (before the subcommand). */
const GIT_GLOBAL_VALUE_OPTIONS = new Set(["--git-dir", "--work-tree", "--namespace", "--exec-path"]);

/** KEY=value with no spaces (POSIX inline assignment). */
const ASSIGNMENT_RE = /^([^=\s]+)=(.*)$/;

/* -------------------------------------------------------------------------- */
/* Public decision function                                                   */
/* -------------------------------------------------------------------------- */

/** Decide whether a bash command is a dangerous `git worktree remove`.
 * Pure apart from reading the filesystem and, for bare names, asking git for
 * the worktree registry. `env` is the variable table for interpolation. */
export function decideWorktreeRemove(command: string, cwd: string, env: NodeJS.ProcessEnv): WorktreeGuardVerdict {
	if (typeof command !== "string" || command === "") return notRemove();
	const segments = parseBashSegments(command);
	const table = createVarTable(env);
	let effectiveCwd: string | undefined = cwd;
	let cwdMissing: string | undefined;

	for (const segment of segments) {
		const words = segment.words;
		if (words.length === 0) continue;

		// Command-internal assignment (`$t = "..."` / `FOO=bar` / `$env:X = y`).
		const assignment = readAssignmentStatement(words);
		if (assignment !== undefined) {
			storeAssignment(table, assignment.name, assignment.value);
			continue;
		}

		// Working-directory update (`cd` / `Set-Location` / `pushd` / `sl` /
		// `chdir`). A location verb without an operand (bare `pushd` -> $HOME,
		// cmd `cd` -> prints the cwd) leaves the base unprovable, so the next
		// relative target must fail closed — same disposition as `cd $UNSET`
		// (D-19), never a silent reuse of the old cwd.
		const location = readLocationTarget(words);
		if (location !== undefined) {
			if (location.target === "") {
				cwdMissing = location.verb;
				effectiveCwd = undefined;
				continue;
			}
			const expanded = expandToken(location.target, table);
			if (expanded.missing !== undefined) {
				cwdMissing = expanded.missing;
				effectiveCwd = undefined;
			} else if (effectiveCwd !== undefined) {
				effectiveCwd = path.resolve(effectiveCwd, expandTilde(expanded.value));
				cwdMissing = undefined;
			}
			continue;
		}

		const invocation = parseGitInvocation(words);
		if (invocation === undefined || invocation.subcommand !== "worktree") {
			// D-11/D-19: the covered delete verbs' penetrating forms (`<path>/`,
			// `<path>/*`, `<path>\*`) delete THROUGH a reparse point one level
			// down. Only the
			// trailing-separator / glob operand face is covered; a separator-free,
			// glob-free operand stays outside the guard (D-4 rule 3).
			const deletion = parseDeleteInvocation(words);
			if (deletion !== undefined) {
				let verdict: WorktreeGuardVerdict | undefined;
				for (const rawToken of deletion) {
					const current = decideDeletePenetration(rawToken, effectiveCwd, cwdMissing, table);
					if (current.block) return current;
					verdict ??= current;
				}
				if (verdict !== undefined) return verdict;
			}
			continue;
		}
		const action = invocation.args[0] ?? "";
		if (action !== "remove" && action !== "rm") continue;

		for (const inline of invocation.leadingAssignments) storeAssignment(table, inline.name, inline.value);

		const operands = collectOperands(invocation.args.slice(1));
		if (operands.length !== 1) {
			return {
				block: true,
				reason:
					`[mw-worktree-guard] blocked: git worktree ${action} 需要且仅需要一个目标，` +
					`实际识别到 ${operands.length} 个；删除面无法定死，按 fail-closed 拒绝。`,
				hits: [],
				basis: "bare-name-ambiguous",
			};
		}
		const rawToken = operands[0] ?? "";

		// Base directory = `-C` operand > command-internal cd/Set-Location > ctx.cwd.
		let base = effectiveCwd;
		if (invocation.base !== undefined) {
			const expandedBase = expandToken(invocation.base, table);
			if (expandedBase.missing !== undefined) return unresolvedVerdict(expandedBase.missing, rawToken);
			base = path.resolve(effectiveCwd ?? cwd, expandTilde(expandedBase.value));
		}
		if (base === undefined) return unresolvedVerdict(cwdMissing ?? "cwd", rawToken);

		// Command substitution cannot be resolved statically -> block (rule c).
		if (rawToken.includes("$(") || rawToken.includes("`")) return globVerdict(rawToken);

		const expanded = expandToken(rawToken, table);
		if (expanded.missing !== undefined) return unresolvedVerdict(expanded.missing, rawToken);
		const value = expanded.value;
		if (hasGlobOrSubstitution(value)) return globVerdict(rawToken);
		if (hasTrailingSeparator(value)) return globVerdict(rawToken);
		if (isBareName(value)) return decideBareName(value, base);
		return scanVerdict(path.resolve(base, expandTilde(value)));
	}
	return notRemove();
}

/**
 * Register the tool_call worktree block: only bash `git worktree remove|rm`
 * commands are inspected; every other tool call passes through untouched.
 * Runs in every mode (PM, worker, interactive).
 *
 * AC-014 adds the `user_bash` face on the same registration function: the TUI
 * `!`/`!!` prefix and the RPC `bash` command go through
 * `ExtensionRunner.emitUserBash` (core/extensions/runner.ts), never through
 * the bash tool, so `tool_call` alone leaves that channel unguarded. Both
 * hooks share `decideWorktreeRemove` and the `[WORKTREE_GUARD]` trace; the
 * only difference is the shape of the refusal (tool_call: `{block, reason}`;
 * user_bash: `{result}` = full replacement, i.e. the command does not run).
 *
 * `pi.on` writes the handler into a `Map<string, handler[]>` with no event
 * allow-list (core/extensions/loader.ts `on()`), so the `user_bash`
 * registration cannot break extension loading even on an older pi build that
 * ignores the event; the try/catch fallback is therefore unnecessary.
 */
export function registerWorktreeJunctionGuard(pi: ExtensionAPI): void {
	pi.on("tool_call", (event, ctx) => {
		if (event.toolName !== "bash") return undefined;
		const command = event.input.command;
		if (typeof command !== "string" || command === "") return undefined;
		const verdict = decideWorktreeRemove(command, ctx.cwd, process.env);
		if (!verdict.block) return undefined;
		recordWorktreeGuardBlockTrace("bash", verdict.target ?? command);
		return { block: true, reason: verdict.reason };
	});

	// AC-014: user-typed (`!`/`!!`) and RPC bash. `event.cwd` is the caller's
	// current working directory, the same base the bash tool would run in.
	// A returned `result` is consumed as the command's full replacement, so the
	// command body is never spawned; leaving it undefined keeps the command on
	// the normal execution path (no false interception).
	pi.on("user_bash", (event) => {
		const command = event.command;
		if (typeof command !== "string" || command === "") return undefined;
		const verdict = decideWorktreeRemove(command, event.cwd, process.env);
		if (!verdict.block) return undefined;
		recordWorktreeGuardBlockTrace("user_bash", verdict.target ?? command);
		return {
			result: {
				output: verdict.reason ?? "[mw-worktree-guard] blocked",
				exitCode: 1,
				cancelled: false,
				truncated: false,
			},
		};
	});
}

/* -------------------------------------------------------------------------- */
/* Target-tree scan                                                           */
/* -------------------------------------------------------------------------- */

interface ScanOutcome {
	/** Top-level target does not exist: git itself rejects with rc=128. */
	absent: boolean;
	hits: string[];
	/** Enumeration failed (permission/race/budget) -> fail-closed. */
	error?: string;
}

/**
 * Explicit-stack walk of the target tree. Constraint set (design §3.3):
 * `readdirSync(dir, { withFileTypes: true })` with our own stack (never
 * `{ recursive: true }`, which follows junctions); reparse points are hit
 * with `lstatSync(...).isSymbolicLink()` (broken links included, where
 * stat/existsSync are blind); a hit is never descended into; the entry
 * budget is enforced; any enumeration failure is fail-closed.
 */
function scanTree(root: string): ScanOutcome {
	let rootStat: fs.Stats;
	try {
		rootStat = fs.lstatSync(root);
	} catch (err) {
		if (errorCode(err) === "ENOENT") return { absent: true, hits: [] };
		return { absent: false, hits: [], error: errorCode(err) };
	}

	const hits: string[] = [];
	if (rootStat.isSymbolicLink()) hits.push(root);
	const stack: string[] = rootStat.isDirectory() ? [root] : [];
	let entries = 0;

	while (stack.length > 0) {
		const dir = stack.pop() ?? "";
		let listing: fs.Dirent[];
		try {
			listing = fs.readdirSync(dir, { withFileTypes: true });
		} catch (err) {
			return { absent: false, hits, error: errorCode(err) };
		}
		for (const entry of listing) {
			entries += 1;
			if (entries > MAX_SCAN_ENTRIES) return { absent: false, hits, error: "entry-budget" };
			const full = path.join(dir, entry.name);
			let isLink: boolean;
			try {
				isLink = fs.lstatSync(full).isSymbolicLink();
			} catch (err) {
				return { absent: false, hits, error: errorCode(err) };
			}
			if (isLink) {
				hits.push(full);
				continue;
			}
			if (entry.isDirectory()) stack.push(full);
		}
	}
	return { absent: false, hits };
}

function scanVerdict(target: string): WorktreeGuardVerdict {
	const outcome = scanTree(target);
	if (outcome.absent) return { block: false, hits: [], basis: "target-absent", target };
	if (outcome.error !== undefined) return scanErrorVerdict(target, outcome.error, outcome.hits);
	if (outcome.hits.length > 0) return reparsePointVerdict(target, outcome.hits);
	return { block: false, hits: [], basis: "resolved", target };
}

/* -------------------------------------------------------------------------- */
/* Delete-verb penetrating forms (design D-4 rule 2 / decision D-11)          */
/* -------------------------------------------------------------------------- */

/** `<path>/`, `<path>\`, `<path>/*`, `<path>\*`, `<path>?`, `<path>[`: the
 * forms RQ-1 measured as deleting THROUGH a reparse point one level down. */
function hasPenetratingForm(value: string): boolean {
	return /[*?[]/.test(value) || /[\\/]$/.test(value);
}

/** Directory to scan for a penetrating deletion: strip the glob tail (and
 * trailing separator) so `dir/*` scans `dir` and `dir/sub*` scans `dir` —
 * over-broad by design, since over-blocking is the fail-closed side. A bare
 * leading glob resolves `"."` against the caller's base. */
function deleteScanRoot(value: string): string {
	const match = /[*?[]/.exec(value);
	if (match === null || match.index === undefined) return value;
	const prefix = value.slice(0, match.index);
	if (prefix === "") return ".";
	if (/[\\/]$/.test(prefix)) return prefix;
	return path.dirname(prefix);
}

/** Same pipeline as the git channel: expand (an unknown variable blocks only
 * when the raw operand already shows a penetrating form), resolve against the
 * tracked base, scan, then block/allow. A worktree-registered target gets the
 * §4.3 text (`mw worktree rm`); every other target gets the second text with
 * the per-link `cmd /c rmdir` prescription (AC-002 / D-11). */
function decideDeletePenetration(
	rawToken: string,
	base: string | undefined,
	cwdMissing: string | undefined,
	table: VarTable,
): WorktreeGuardVerdict {
	const expanded = expandToken(rawToken, table);
	if (expanded.missing !== undefined) {
		return hasPenetratingForm(rawToken) ? unresolvedVerdict(expanded.missing, rawToken) : notRemove();
	}
	const value = expanded.value;
	if (!hasPenetratingForm(value)) return notRemove();
	// Command substitution inside a penetrating operand cannot be resolved
	// statically -> block (same class as the git channel's `glob` verdict).
	if (value.includes("$(") || value.includes("`")) return deleteGlobVerdict(rawToken);
	if (base === undefined) return unresolvedVerdict(cwdMissing ?? "cwd", rawToken);

	const target = path.resolve(base, expandTilde(deleteScanRoot(value)));
	const outcome = scanTree(target);
	if (outcome.absent) return { block: false, hits: [], basis: "target-absent", target };
	if (outcome.error !== undefined) return scanErrorVerdict(target, outcome.error, outcome.hits);
	if (outcome.hits.length === 0) return { block: false, hits: [], basis: "resolved", target };
	if (isRegisteredWorktree(target)) return reparsePointVerdict(target, outcome.hits);
	return deletePenetrationVerdict(target, outcome.hits);
}

/** Unique registry match of `target` in `git -C target worktree list
 * --porcelain`. Zero or ambiguous matches -> false (second text applies). */
function isRegisteredWorktree(target: string): boolean {
	const listing = listWorktrees(target);
	if (listing.error !== undefined || listing.paths === undefined) return false;
	const wanted = canonicalComparePath(target);
	let matches = 0;
	for (const listed of listing.paths) {
		if (canonicalComparePath(listed) === wanted) matches += 1;
	}
	return matches === 1;
}

/** Compare without following the FINAL component (a junction must stay the
 * link itself) and case-insensitively on Windows, where git may emit the long
 * 8.3-expanded form while `os.tmpdir()` can be the short one. */
function canonicalComparePath(value: string): string {
	const dir = path.dirname(value);
	let realDir: string;
	try {
		realDir = fs.realpathSync.native(dir);
	} catch {
		realDir = path.resolve(dir);
	}
	const joined = path.join(realDir, path.basename(value));
	return process.platform === "win32" ? joined.toLowerCase() : joined;
}

/* -------------------------------------------------------------------------- */
/* Bare-name resolution via `git worktree list --porcelain`                   */
/* -------------------------------------------------------------------------- */

/** Decide a separator-free operand (a worktree id/basename). git matches the
 * registry, not the cwd; zero matches -> allow (git rejects with rc=128),
 * ambiguity or an unreadable registry -> block. */
function decideBareName(token: string, base: string): WorktreeGuardVerdict {
	const listing = listWorktrees(base);
	if (listing.error !== undefined) return scanErrorVerdict(undefined, listing.error, []);
	const matches = (listing.paths ?? []).filter((p) => path.basename(p).toLowerCase() === token.toLowerCase());
	if (matches.length === 0) return { block: false, hits: [], basis: "target-absent" };
	if (matches.length > 1) {
		return {
			block: true,
			reason:
				`[mw-worktree-guard] blocked: worktree 裸名 ${token} 在 git 工作树注册表中匹配到 ${matches.length} 项，` +
				`删除面无法定死；请改用完整字面路径后重试。`,
			hits: [],
			basis: "bare-name-ambiguous",
		};
	}
	return scanVerdict(path.resolve(matches[0] ?? ""));
}

interface WorktreeListing {
	paths?: string[];
	error?: string;
}

function listWorktrees(base: string): WorktreeListing {
	const result = spawnSync("git", ["-C", base, "worktree", "list", "--porcelain"], {
		encoding: "utf8",
		windowsHide: true,
	});
	if (result.error) return { error: "git-spawn" };
	if (result.status !== 0) return { error: `git-${result.status ?? "signal"}` };
	const paths = (result.stdout ?? "")
		.split(/\r?\n/)
		.filter((line) => line.startsWith("worktree "))
		.map((line) => line.slice("worktree ".length).trim())
		.filter((line) => line !== "");
	return { paths };
}

/* -------------------------------------------------------------------------- */
/* Command structure                                                          */
/* -------------------------------------------------------------------------- */

interface VariableAssignment {
	name: string;
	value: string;
}

interface GitInvocation {
	base?: string;
	subcommand: string;
	args: string[];
	/** Leading `KEY=value` words of this same segment. */
	leadingAssignments: VariableAssignment[];
}

/** `git [-C dir] worktree remove|rm ...`, tolerating common global options. */
function parseGitInvocation(words: string[]): GitInvocation | undefined {
	let i = 0;
	const leadingAssignments: VariableAssignment[] = [];
	while (i < words.length) {
		const word = words[i] ?? "";
		if (word.includes("/") || word.includes("\\")) break;
		const match = ASSIGNMENT_RE.exec(word);
		if (!match || (match[1] ?? "") === "") break;
		leadingAssignments.push({ name: normalizeVarName(match[1] ?? ""), value: match[2] ?? "" });
		i += 1;
	}
	if (i >= words.length) return undefined;
	if (basenameLower(words[i] ?? "") !== "git") return undefined;
	i += 1;

	let base: string | undefined;
	while (i < words.length) {
		const word = words[i] ?? "";
		if (word === "-C") {
			if (i + 1 < words.length) {
				base = words[i + 1] ?? "";
				i += 2;
			} else {
				i += 1;
			}
			continue;
		}
		if (word.startsWith("-C") && word.length > 2) {
			base = word.slice(2);
			i += 1;
			continue;
		}
		if (word === "-c") {
			i += 2;
			continue;
		}
		if (GIT_GLOBAL_VALUE_OPTIONS.has(word)) {
			i += 2;
			continue;
		}
		if (word.startsWith("-")) {
			i += 1;
			continue;
		}
		return { base, subcommand: word, args: words.slice(i + 1), leadingAssignments };
	}
	return undefined;
}

/** `$t = "..."` (words `["$t","=","..."]`) or `FOO=bar` (single word). */
function readAssignmentStatement(words: string[]): VariableAssignment | undefined {
	if (words.length >= 3 && words[1] === "=") {
		const name = normalizeVarName(words[0] ?? "");
		if (name !== "") return { name, value: words.slice(2).join(" ") };
		return undefined;
	}
	if (words.length === 1) {
		const word = words[0] ?? "";
		if (word.includes("/") || word.includes("\\")) return undefined;
		const match = ASSIGNMENT_RE.exec(word);
		if (match && (match[1] ?? "") !== "") {
			return { name: normalizeVarName(match[1] ?? ""), value: match[2] ?? "" };
		}
	}
	return undefined;
}

interface LocationUpdate {
	/** Verb as written (basename, lower-cased). */
	verb: string;
	/** Raw operand; "" when the verb carries none (base unprovable). */
	target: string;
}

/** Location verbs whose operand becomes the base for later relative targets:
 * POSIX/cmd `cd`, cmd `chdir`/`pushd` and PowerShell `Set-Location`/`sl`
 * (D-19). `undefined` means "not a location verb"; a location verb with no
 * operand returns `target: ""` and the caller fails closed. */
const LOCATION_VERBS = new Set(["cd", "set-location", "pushd", "sl", "chdir"]);

/** PowerShell path parameters: the value is the next word (`-Path <dir>`) or
 * the tail after `=` in the same word (`-Path=<dir>`). */
const PATH_PARAMETERS = new Set(["-path", "-literalpath"]);

/** `cd <dir>` / `Set-Location [-Path] <dir>` / `pushd <dir>` target: the first
 * operand word, skipping the cmd-style `/d`/`/D` flag and every `-`-prefixed
 * parameter (reading the value out of `-Path=<dir>` / `-LiteralPath=<dir>`). */
function readLocationTarget(words: string[]): LocationUpdate | undefined {
	const verb = basenameLower(words[0] ?? "");
	if (!LOCATION_VERBS.has(verb)) return undefined;
	for (let i = 1; i < words.length; i += 1) {
		const word = words[i] ?? "";
		// cmd-style `cd /d <dir>` / `cd /D <dir>`: a flag, not the operand.
		if (word === "/d" || word === "/D") continue;
		if (word.startsWith("-")) {
			const eq = word.indexOf("=");
			if (eq > 1 && PATH_PARAMETERS.has(word.slice(0, eq).toLowerCase())) {
				return { verb, target: word.slice(eq + 1) };
			}
			continue;
		}
		return { verb, target: word };
	}
	return { verb, target: "" };
}

/** Operand words after `remove|rm`, excluding options and the `--` marker. */
function collectOperands(args: string[]): string[] {
	const operands: string[] = [];
	let endOfOptions = false;
	for (const arg of args) {
		if (!endOfOptions) {
			if (arg === "--") {
				endOfOptions = true;
				continue;
			}
			if (arg.startsWith("-")) continue;
		}
		operands.push(arg);
	}
	return operands;
}

/** Delete verbs whose penetrating operands are covered (D-11, extended by
 * D-19): `rm`, and the PowerShell `Remove-Item` family (`Remove-Item` plus
 * its `ri`/`del`/`erase`/`rd`/`rmdir` aliases, which share its reach because
 * pi pins its shell to PowerShell). Returns undefined for every other head
 * word; the recursive-flag, trailing-separator / glob and `notRemove`
 * predicates are unchanged, so this does not widen the covered face. */
const DELETE_VERBS = new Set(["rm", "remove-item", "ri", "del", "erase", "rd", "rmdir"]);

function parseDeleteInvocation(words: string[]): string[] | undefined {
	const head = basenameLower(words[0] ?? "");
	if (!DELETE_VERBS.has(head)) return undefined;
	return collectOperands(words.slice(1));
}

function basenameLower(word: string): string {
	const base = path.basename(word).toLowerCase();
	return base.endsWith(".exe") ? base.slice(0, -4) : base;
}

/* -------------------------------------------------------------------------- */
/* Interpolation                                                              */
/* -------------------------------------------------------------------------- */

interface VarTable {
	/** Command-internal names (lower-cased) -> expanded value, null = unresolved. */
	locals: Map<string, string | null>;
	/** Environment, lower-cased for case-insensitive lookup. */
	envLower: Map<string, string>;
}

interface Expansion {
	value: string;
	missing?: string;
}

function createVarTable(env: NodeJS.ProcessEnv): VarTable {
	const envLower = new Map<string, string>();
	for (const [key, value] of Object.entries(env)) {
		if (typeof value === "string") envLower.set(key.toLowerCase(), value);
	}
	return { locals: new Map(), envLower };
}

function storeAssignment(table: VarTable, name: string, rawValue: string): void {
	const expanded = expandToken(rawValue, table);
	table.locals.set(name.toLowerCase(), expanded.missing === undefined ? expanded.value : null);
}

function normalizeVarName(raw: string): string {
	let name = raw.trim();
	if (name.startsWith("$")) name = name.slice(1);
	if (/^env:/i.test(name)) name = name.slice(4);
	return name;
}

function lookupVar(table: VarTable, rawName: string): { found: boolean; value: string } {
	const key = normalizeVarName(rawName).toLowerCase();
	if (table.locals.has(key)) {
		const value = table.locals.get(key);
		return value === null || value === undefined ? { found: false, value: "" } : { found: true, value };
	}
	const envValue = table.envLower.get(key);
	if (envValue !== undefined) return { found: true, value: envValue };
	return { found: false, value: "" };
}

/** Expand `$env:N` / `${N}` / `$N` / `%N%` (case-insensitive). Any unknown
 * variable aborts the expansion (`missing`) and the caller blocks. */
function expandToken(token: string, table: VarTable): Expansion {
	let out = "";
	let i = 0;
	while (i < token.length) {
		const c = token.charAt(i);
		if (c === "$") {
			if (token.charAt(i + 1) === "{") {
				const close = token.indexOf("}", i + 2);
				if (close > i + 2) {
					const name = token.slice(i + 2, close);
					const resolved = lookupVar(table, name);
					if (!resolved.found) return { value: out, missing: normalizeVarName(name) };
					out += resolved.value;
					i = close + 1;
					continue;
				}
			}
			const envMatch = /^env:([A-Za-z0-9_()]+)/i.exec(token.slice(i + 1));
			if (envMatch) {
				const name = envMatch[1] ?? "";
				const resolved = lookupVar(table, name);
				if (!resolved.found) return { value: out, missing: normalizeVarName(name) };
				out += resolved.value;
				i += 1 + envMatch[0].length;
				continue;
			}
			const plainMatch = /^([A-Za-z_][A-Za-z0-9_]*)/.exec(token.slice(i + 1));
			if (plainMatch) {
				const name = plainMatch[1] ?? "";
				const resolved = lookupVar(table, name);
				if (!resolved.found) return { value: out, missing: normalizeVarName(name) };
				out += resolved.value;
				i += 1 + plainMatch[0].length;
				continue;
			}
			out += c;
			i += 1;
			continue;
		}
		if (c === "%") {
			const close = token.indexOf("%", i + 1);
			if (close > i + 1) {
				const name = token.slice(i + 1, close);
				if (/^[A-Za-z_][A-Za-z0-9_]*$/.test(name)) {
					const resolved = lookupVar(table, name);
					if (!resolved.found) return { value: out, missing: normalizeVarName(name) };
					out += resolved.value;
					i = close + 1;
					continue;
				}
			}
			out += c;
			i += 1;
			continue;
		}
		out += c;
		i += 1;
	}
	return { value: out };
}

function hasGlobOrSubstitution(value: string): boolean {
	return /[*?[]/.test(value) || value.includes("$(") || value.includes("`");
}

function hasTrailingSeparator(value: string): boolean {
	return /[\\/]$/.test(value);
}

function isBareName(value: string): boolean {
	if (value === "" || value === "." || value === "..") return false;
	if (value.includes("/") || value.includes("\\")) return false;
	if (/^[A-Za-z]:/.test(value)) return false;
	return true;
}

function expandTilde(value: string): string {
	if (value === "~") return os.homedir();
	if (value.startsWith("~/") || value.startsWith("~\\")) return path.join(os.homedir(), value.slice(2));
	return value;
}

/* -------------------------------------------------------------------------- */
/* Verdicts                                                                   */
/* -------------------------------------------------------------------------- */

function notRemove(): WorktreeGuardVerdict {
	return { block: false, hits: [], basis: "not-remove" };
}

/** design §4.3 template, verbatim (AC-002). */
function reparsePointVerdict(target: string, hits: string[]): WorktreeGuardVerdict {
	const example = hits[0] ?? target;
	const linkTarget = readLinkTarget(example);
	const reason =
		`[mw-worktree-guard] blocked: ${target} 内有 ${hits.length} 个 reparse point（示例 ${example} -> ${linkTarget}）；\n` +
		"直接执行 git worktree remove 会穿透并删除目标真树内容。请改用：\n" +
		`  mw worktree rm "${target}"`;
	return { block: true, reason, target, hits, basis: "reparse-point" };
}

function unresolvedVerdict(name: string, rawToken: string): WorktreeGuardVerdict {
	return {
		block: true,
		reason:
			`[mw-worktree-guard] blocked: worktree 目标 ${rawToken} 含无法解析的变量 ${name}；` +
			"无法证明目标树内无 reparse point。请显式给出可解析的 worktree 路径后重试。",
		hits: [],
		basis: `unresolved:${name}`,
	};
}

function globVerdict(rawToken: string): WorktreeGuardVerdict {
	return {
		block: true,
		reason:
			`[mw-worktree-guard] blocked: worktree 目标 ${rawToken} 含通配、命令替换或尾分隔符；` +
			"`<link>/`、`<link>/*` 这类形态会让 git worktree remove 穿透链接删除真树内容。" +
			"请改用字面 worktree 路径后重试。",
		hits: [],
		basis: "glob",
	};
}

function scanErrorVerdict(target: string | undefined, code: string, hits: string[]): WorktreeGuardVerdict {
	return {
		block: true,
		reason:
			`[mw-worktree-guard] blocked: 无法完整枚举 worktree ${target ?? "<unknown>"}（${code}）；` +
			"无法证明其中无 reparse point，按 fail-closed 拒绝执行 git worktree remove。",
		target,
		hits,
		basis: `scan-error:${code}`,
	};
}

/** D-11 second text: the target is not a registered worktree, so
 * `mw worktree rm` does not apply. Name the penetrating form, list up to 3
 * `link -> target` chains (plus the total) and print the per-link command
 * that unlinks WITHOUT `/S` and WITHOUT a trailing separator, then the
 * original delete can be retried. */
const MAX_PENETRATION_LINES = 3;

function deletePenetrationVerdict(target: string, hits: string[]): WorktreeGuardVerdict {
	const listed = hits.slice(0, MAX_PENETRATION_LINES);
	const chains = listed.map((link) => `  ${link} -> ${readLinkTarget(link)}`);
	const prescriptions = listed.map((link) => `  cmd /c rmdir "${link}"`);
	const remaining = hits.length - listed.length;
	const tail = remaining > 0 ? `（另有 ${remaining} 条未列出，请对每个命中的链执行同一条 rmdir 后重试）` : "";
	const reason =
		`[mw-worktree-guard] blocked: 该删除形态（尾分隔符或通配）会穿透 reparse point，删除链接指向的真树内容。` +
		`目标 ${target} 内命中 ${hits.length} 个 reparse point：\n` +
		`${chains.join("\n")}\n` +
		`请先逐条摘链（无 /S、无尾分隔符），再重试原删除命令${tail}：\n` +
		`${prescriptions.join("\n")}`;
	return { block: true, reason, target, hits, basis: "delete-penetration" };
}

function readLinkTarget(link: string): string {
	try {
		return stripExtendedPrefix(fs.readlinkSync(link));
	} catch {
		return "<unreadable>";
	}
}

function deleteGlobVerdict(rawToken: string): WorktreeGuardVerdict {
	return {
		block: true,
		reason:
			`[mw-worktree-guard] blocked: 删除目标 ${rawToken} 含命令替换，无法静态解析；` +
			"`<link>/`、`<link>/*` 这类形态会穿透链接删除真树内容，按 fail-closed 拒绝。",
		hits: [],
		basis: "glob",
	};
}

function stripExtendedPrefix(value: string): string {
	if (value.startsWith("\\\\?\\")) return value.slice(4);
	if (value.startsWith("\\??\\")) return value.slice(4);
	return value;
}

function errorCode(err: unknown): string {
	if (err !== null && typeof err === "object" && "code" in err) {
		const code = (err as { code?: unknown }).code;
		if (typeof code === "string") return code;
	}
	return "unknown";
}

/* -------------------------------------------------------------------------- */
/* Audit                                                                      */
/* -------------------------------------------------------------------------- */

/** Worker-mode visibility: append one [WORKTREE_GUARD] line to the task's
 * trace.log (same file the PM watch reads live). Best-effort: a failure here
 * must never break the block itself. Mirrors protected-config.ts. */
function recordWorktreeGuardBlockTrace(toolName: string, detail: string): void {
	const taskPath = process.env.PI_WORKER_TASK;
	if (!taskPath) return;
	try {
		const dir = path.dirname(path.resolve(taskPath));
		fs.mkdirSync(dir, { recursive: true });
		const first = detail.split("\n")[0] ?? "";
		fs.appendFileSync(
			path.join(dir, "trace.log"),
			`[WORKTREE_GUARD] ${new Date().toISOString()} blocked tool=${toolName} target=${first}\n`,
			"utf8",
		);
	} catch {
		// best-effort diagnostic — the block itself already happened
	}
}
