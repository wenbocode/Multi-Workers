import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";

/**
 * Implementation entry gate (mw-implementation-gate, 2026-09-21).
 *
 * Why: within one week two mid-session requirements were implemented "wild"
 * (update-env, ue-toolchain) — code landed with no AgenticTask key, i.e. no
 * traceability, goal alignment, evidence, or closure. The AGENTS.md rule is
 * advisory text; this module moves the discipline into the tool layer.
 *
 * Three layers (design D-1):
 *  1. write/edit hard gate (main form): the tool path is resolved exactly
 *     like the tools do and checked against the code-path set.
 *  2. bash narrowed fallback: ONLY write-structure TARGET arguments are
 *     checked — `>`/`>>`/`n>`/`&>` redirect targets and the file operand
 *     sides of tee / cp / mv / rm / sed -i (quote-aware lexing, `cd` is
 *     tracked, heredoc bodies are skipped as payload text). Payload text
 *     that merely references a code path never triggers — the 2026-09-21
 *     W2 measurement showed reference+write-word co-occurrence
 *     false-positives on agents writing research docs (blocked twice while
 *     writing one note). Not a sandbox: python -c inline writes,
 *     pre-written script execution, find -delete/-exec, tar, PowerShell
 *     cmdlets, and env-var path spellings are known misses, accepted as
 *     legacy gaps.
 *  3. post-hoc audit: every block and every mini fast-path pass appends
 *     one line to .agenticdoc/_impl_gate.log. All modes (PM, worker,
 *     interactive); keyed/worker passes are not audited (the claim row and
 *     dispatch state are already the record); the audit write is
 *     best-effort and can never change the decision.
 *
 * Pass semantics (D-3): a gated write to a code path passes when ANY of
 *  (a) an active row in .agenticdoc/_index.parallel carries this window's
 *      host:pid claim id (update_index.py claim — the /agentic flow),
 *  (b) PI_WORKER_TASK is set (dispatched workers are pre-authorized by
 *      their task; without this every coding worker would be blocked),
 *  (c) some .agenticdoc/<key>/mini-spec.md is newer than 24h (trivial-fix
 *      fast path; freshness stops a stale spec from holding the door open,
 *      and the pass is audited).
 * Otherwise the call is blocked with a reason that names the two compliant
 * paths (create a key / mini fast path). _index.parallel missing or
 * unparsable counts as "no claim" — fail-closed.
 *
 * Code path (D-4): resolved under <root>/packages/ with extension
 * .ts/.tsx/.js/.cjs/.mjs/.py, excluding any node_modules/dist/.tmp
 * segment. .md, docs/, README.md, tmp/** never match (AC-004 whitelist
 * behavior). <root> = MW_IMPL_GATE_ROOT env override (test hook) else
 * process.cwd().
 *
 * Judgment reads the filesystem only (the index file and mini-spec mtimes)
 * and never writes coordination state. Mirrors protected-config.ts's shape
 * (pure decision functions + registerXxxGuard(pi)) so the decisions are
 * unit-testable without pi; the module stays self-contained for the
 * standalone esbuild bundle (no core imports beyond the extension type).
 */

const IS_WIN32 = process.platform === "win32";

/** Repo root override (test hook), else process.cwd(). */
const ENV_GATE_ROOT = "MW_IMPL_GATE_ROOT";
/** Dispatched worker env — its presence pre-authorizes code writes. */
const ENV_WORKER_TASK = "PI_WORKER_TASK";

const AGENTICDOC_DIR = ".agenticdoc";
const INDEX_FILE = "_index.parallel";
const MINI_SPEC_FILE = "mini-spec.md";
const GATE_LOG_FILE = "_impl_gate.log";

/** Mini-spec freshness window: the fast path decays after 24h. */
const MINI_SPEC_FRESH_MS = 24 * 60 * 60 * 1000;

const PACKAGES_DIR = "packages";
const CODE_EXTENSIONS = [".ts", ".tsx", ".js", ".cjs", ".mjs", ".py"] as const;
const CODE_EXCLUDED_SEGMENTS = ["node_modules", "dist", ".tmp"] as const;

/** bash write verbs whose FILE OPERAND side is a write target. */
const WRITE_VERBS = new Set(["tee", "cp", "mv", "rm", "sed"]);

const GATE_EXPLANATION =
	"Create a key first: run /agentic (the AgenticTask flow), or write .agenticdoc/<key>/spec.md — update_index.py " +
	"claim then records this window (host:pid) as the owner. For a trivial fix use the mini fast path: write " +
	".agenticdoc/<key>/mini-spec.md, then retry this tool call (the pass is audited to .agenticdoc/_impl_gate.log).";

function fold(p: string): string {
	return IS_WIN32 ? p.toLowerCase() : p;
}

function toForwardSlashes(p: string): string {
	return p.replaceAll("\\", "/");
}

/** Tilde expansion only (mirrors core normalizePath's tilde branch): `~` and
 * `~/x` fold onto the home dir; everything else is returned unchanged —
 * relative paths stay relative so callers resolve them against THEIR base. */
function expandTildePath(p: string): string {
	if (p === "~") return os.homedir();
	if (p.startsWith("~/") || p.startsWith("~\\")) {
		return path.join(os.homedir(), p.slice(2));
	}
	return p;
}

function isExistingDir(absPath: string): boolean {
	try {
		return fs.statSync(absPath).isDirectory();
	} catch {
		return false;
	}
}

function defaultReadTextFile(absPath: string): string | undefined {
	try {
		return fs.readFileSync(absPath, "utf8");
	} catch {
		return undefined;
	}
}

/** Resolve the repo root the gate anchors code paths against: the
 * MW_IMPL_GATE_ROOT override (tilde-expanded, resolved) wins, else the
 * process cwd. env injectable for tests. */
export function resolveGateRoot(env: NodeJS.ProcessEnv = process.env): string {
	const raw = env[ENV_GATE_ROOT];
	if (typeof raw === "string" && raw !== "") {
		return path.resolve(expandTildePath(raw));
	}
	return process.cwd();
}

/** This window's claim id, in update_index.py's host:pid format. */
export function currentClaimId(): string {
	return `${os.hostname()}:${process.pid}`;
}

/** rel of absPath under <root>/packages/ (forward slashes), or undefined
 * when the path is outside that tree. */
function codePathRel(absPath: string, root: string): string | undefined {
	const target = toForwardSlashes(fold(path.normalize(absPath)));
	const prefix = `${toForwardSlashes(fold(path.normalize(root)))}/${PACKAGES_DIR}/`;
	if (!target.startsWith(prefix)) return undefined;
	return target.slice(prefix.length);
}

function isCodePathAbs(absPath: string, root: string): boolean {
	const rel = codePathRel(absPath, root);
	if (rel === undefined || rel === "") return false;
	const ext = path.extname(rel).toLowerCase();
	if (!(CODE_EXTENSIONS as readonly string[]).includes(ext)) return false;
	const segments = rel.split("/");
	return !segments.some((s) => (CODE_EXCLUDED_SEGMENTS as readonly string[]).includes(s));
}

/** Does a write/edit tool path target a code file (D-4)? Pure: resolves the
 * path like the tools do (cwd-relative, ~ expanded) and checks the
 * packages/ tree, the code extensions, and the node_modules/dist/.tmp
 * exclusions. */
export function isCodePath(rawPath: string, root: string = resolveGateRoot(), cwd: string = process.cwd()): boolean {
	if (typeof rawPath !== "string" || rawPath === "") return false;
	return isCodePathAbs(path.resolve(cwd, expandTildePath(rawPath)), root);
}

// ============================================================================
// _index.parallel parsing (read-only; fail-closed)
// ============================================================================

interface IndexRow {
	key: string;
	status: string;
	claimId: string;
}

function splitTableRow(line: string): string[] {
	let cells = line.split("|").map((c) => c.trim());
	if (cells.length > 0 && cells[0] === "") cells = cells.slice(1);
	if (cells.length > 0 && cells[cells.length - 1] === "") cells = cells.slice(0, -1);
	return cells;
}

function isSeparatorRow(cells: string[]): boolean {
	return cells.length > 0 && cells.every((c) => /^:?-{2,}:?$/.test(c));
}

/** Parse the markdown index table. undefined = unparsable (no table header,
 * or the Key/Status/ClaimId columns are absent) → callers fail closed. Rows
 * with escaped pipes in later cells shift columns; the shift reads as a
 * non-matching claim id, i.e. fail-closed, which is the safe direction. */
function parseIndexRows(content: string): IndexRow[] | undefined {
	let header: string[] | undefined;
	const dataRows: string[][] = [];
	for (const line of content.split(/\r?\n/)) {
		const t = line.trim();
		if (!t.startsWith("|")) continue;
		const cells = splitTableRow(t);
		if (header === undefined) {
			if (!isSeparatorRow(cells)) header = cells;
		} else if (!isSeparatorRow(cells)) {
			dataRows.push(cells);
		}
	}
	if (header === undefined) return undefined;
	const keyIdx = header.findIndex((c) => c.toLowerCase() === "key");
	const statusIdx = header.findIndex((c) => c.toLowerCase() === "status");
	const claimIdx = header.findIndex((c) => c.toLowerCase() === "claimid");
	if (keyIdx < 0 || statusIdx < 0 || claimIdx < 0) return undefined;
	return dataRows.map((cells) => ({
		key: cells[keyIdx] ?? "",
		status: cells[statusIdx] ?? "",
		claimId: cells[claimIdx] ?? "",
	}));
}

/** Active-claim matcher (D-3a): does .agenticdoc/_index.parallel hold a row
 * with status active whose claim id equals the given host:pid
 * (case-insensitive)? Missing or unparsable file = no claim (fail-closed).
 * readIndexFile injectable for pure tests. */
export function hasActiveKeyClaim(
	root: string,
	claimId: string,
	readIndexFile: (absPath: string) => string | undefined = defaultReadTextFile,
): boolean {
	const wanted = claimId.trim().toLowerCase();
	if (wanted === "") return false;
	const content = readIndexFile(path.join(root, AGENTICDOC_DIR, INDEX_FILE));
	if (content === undefined) return false;
	const rows = parseIndexRows(content);
	if (rows === undefined) return false;
	return rows.some((r) => r.status.toLowerCase() === "active" && r.claimId.toLowerCase() === wanted);
}

// ============================================================================
// Mini-spec freshness (read-only)
// ============================================================================

/** Fresh mini-spec finder (D-3c): the most recently modified
 * .agenticdoc/<key>/mini-spec.md whose mtime is within the freshness window
 * (future mtimes count as fresh — clock skew is not the agent's fault);
 * undefined when none exists. now injectable for pure tests. */
export function findFreshMiniSpec(
	root: string,
	now: number = Date.now(),
	maxAgeMs: number = MINI_SPEC_FRESH_MS,
): string | undefined {
	let entries: fs.Dirent[];
	try {
		entries = fs.readdirSync(path.join(root, AGENTICDOC_DIR), { withFileTypes: true });
	} catch {
		return undefined; // no .agenticdoc → no fast path
	}
	let best: string | undefined;
	let bestMtime = Number.NEGATIVE_INFINITY;
	for (const entry of entries) {
		if (!entry.isDirectory() || entry.name.startsWith(".")) continue;
		const candidate = path.join(root, AGENTICDOC_DIR, entry.name, MINI_SPEC_FILE);
		try {
			const mtime = fs.statSync(candidate).mtimeMs;
			if (now - mtime <= maxAgeMs && mtime > bestMtime) {
				best = candidate;
				bestMtime = mtime;
			}
		} catch {
			// no mini-spec.md in this key dir
		}
	}
	return best;
}

// ============================================================================
// bash write-target extraction (quote-aware lexer, target side only)
// ============================================================================

interface BashSegment {
	/** argv words: quotes stripped, backslash escapes resolved. */
	words: string[];
	/** File targets of `>` / `>>` / `n>` / `&>` redirections in this segment. */
	redirectTargets: string[];
}

/** Read the heredoc delimiter right after `<<` (optional `-`, optional
 * quotes). Returns the delimiter and the scan position after it. */
function readHeredocDelimiter(command: string, start: number): { delim: string; next: number } {
	let i = start;
	const n = command.length;
	if (command[i] === "-") i += 1; // <<- form
	while (command[i] === " " || command[i] === "\t") i += 1;
	let delim = "";
	if (command[i] === "'" || command[i] === '"') {
		const quote = command[i];
		i += 1;
		while (i < n && command[i] !== quote) {
			delim += command[i];
			i += 1;
		}
		if (i < n) i += 1;
	} else {
		while (i < n && !/[\s;&|<>()]/.test(command[i] ?? "")) {
			delim += command[i];
			i += 1;
		}
	}
	return { delim, next: i };
}

/** From the newline ending the heredoc operator line, skip body lines until
 * the delimiter line; returns the position at the terminator after it
 * (or EOF). A line with extra text after the delimiter does not terminate
 * the heredoc — the rest of the command is then skipped too, which can only
 * under-block, never false-positive. */
function skipHeredocBody(command: string, start: number, delim: string): number {
	let i = start;
	const n = command.length;
	while (i < n) {
		i += 1; // consume the line terminator
		let line = "";
		while (i < n && command[i] !== "\n") {
			line += command[i];
			i += 1;
		}
		if (line.trim() === delim) return i;
	}
	return i;
}

/** Characters a backslash actually escapes outside quotes: the POSIX shell
 * metacharacters that carry lexical structure here. Before any other
 * character the backslash stays literal — required for Windows path
 * separators (`H:\repo\packages\x.py` must not collapse to `H:repopackagesx.py`)
 * and matching POSIX shells, where `echo a\b` prints `a\b`. */
const BACKSLASH_ESCAPES_UNQUOTED = new Set([
	" ",
	"\t",
	"\r",
	"\n",
	";",
	"&",
	"|",
	"<",
	">",
	"(",
	")",
	"'",
	'"',
	"\\",
	"$",
	"`",
]);

/** Inside double quotes a backslash only escapes $ ` " \\ and newline (POSIX);
 * everywhere else — including the separators of a Windows path — it is a
 * literal character. */
const BACKSLASH_ESCAPES_DOUBLE_QUOTED = new Set(["$", "`", '"', "\\", "\n"]);

/** Split a command into `;`/`&&`/`||`/`|`/`&`/paren-separated segments with
 * quote-aware, escape-aware words and redirect targets captured separately
 * from payload words. Quote content is always literal (a quoted `>` is
 * text, not a redirect — the false-positive lesson from P-002's bash
 * heuristic). Heredoc bodies are skipped entirely: they are payload text,
 * and scanning them would let a doc that quotes shell commands fire the
 * gate. */
function parseBashSegments(command: string): BashSegment[] {
	const segments: BashSegment[] = [];
	let current: BashSegment = { words: [], redirectTargets: [] };
	let word = "";
	let hasWord = false;
	let quote: "'" | '"' | null = null;
	let pendingRedirect = false;
	let pendingRead = false;
	let heredocDelim: string | undefined;

	const flushWord = (): void => {
		if (!hasWord) return;
		if (pendingRedirect) {
			current.redirectTargets.push(word);
		} else if (!pendingRead) {
			current.words.push(word);
		}
		pendingRedirect = false;
		pendingRead = false;
		word = "";
		hasWord = false;
	};
	const endSegment = (): void => {
		flushWord();
		pendingRedirect = false;
		pendingRead = false;
		if (current.words.length > 0 || current.redirectTargets.length > 0) segments.push(current);
		current = { words: [], redirectTargets: [] };
	};

	let i = 0;
	const n = command.length;
	while (i < n) {
		const c = command[i] ?? "";
		if (quote !== null) {
			if (c === "\\" && quote === '"') {
				const next = command[i + 1];
				if (next !== undefined && BACKSLASH_ESCAPES_DOUBLE_QUOTED.has(next)) {
					word += next;
					hasWord = true;
					i += 2;
				} else {
					// literal backslash (Windows path separator before an ordinary char)
					word += c;
					hasWord = true;
					i += 1;
				}
				continue;
			}
			if (c === quote) {
				quote = null;
				i += 1;
				continue;
			}
			word += c;
			hasWord = true;
			i += 1;
			continue;
		}
		if (c === "'" || c === '"') {
			quote = c;
			hasWord = true;
			i += 1;
			continue;
		}
		if (c === "\\") {
			const next = command[i + 1];
			if (next !== undefined && BACKSLASH_ESCAPES_UNQUOTED.has(next)) {
				word += next;
				hasWord = true;
				i += 2;
			} else {
				// literal backslash (Windows path separator before an ordinary char)
				word += c;
				hasWord = true;
				i += 1;
			}
			continue;
		}
		if (c === " " || c === "\t" || c === "\r") {
			flushWord();
			i += 1;
			continue;
		}
		if (c === "\n") {
			flushWord();
			if (heredocDelim !== undefined) {
				i = skipHeredocBody(command, i, heredocDelim);
				heredocDelim = undefined;
				continue;
			}
			i += 1;
			continue;
		}
		if (c === ";") {
			endSegment();
			i += 1;
			continue;
		}
		if (c === "&") {
			if (command[i + 1] === "&") {
				endSegment();
				i += 2;
				continue;
			}
			if (command[i + 1] === ">") {
				flushWord(); // &> redirects both streams
				pendingRedirect = true;
				i += 2;
				continue;
			}
			endSegment();
			i += 1;
			continue;
		}
		if (c === "|") {
			endSegment();
			i += command[i + 1] === "|" ? 2 : 1;
			continue;
		}
		if (c === "(" || c === ")") {
			endSegment();
			i += 1;
			continue;
		}
		if (c === "<") {
			if (command[i + 1] === "<") {
				flushWord();
				const parsed = readHeredocDelimiter(command, i + 2);
				heredocDelim = parsed.delim === "" ? undefined : parsed.delim;
				i = parsed.next;
				continue;
			}
			flushWord();
			pendingRead = true; // input redirect: the next word is a read side, dropped
			i += 1;
			continue;
		}
		if (c === ">") {
			if (hasWord && /^\d+$/.test(word)) {
				// fd-prefixed form (2>log): the digits are the fd number, not a word
				word = "";
				hasWord = false;
			} else {
				flushWord();
			}
			pendingRedirect = true;
			i += command[i + 1] === ">" ? 2 : 1;
			continue;
		}
		word += c;
		hasWord = true;
		i += 1;
	}
	flushWord();
	if (current.words.length > 0 || current.redirectTargets.length > 0) segments.push(current);
	return segments;
}

function stripEnvAssignments(words: string[]): string[] {
	let i = 0;
	while (i < words.length && /^[A-Za-z_][A-Za-z0-9_]*=/.test(words[i] ?? "")) i += 1;
	return words.slice(i);
}

function resolveToken(dir: string, token: string): string {
	return path.resolve(dir, expandTildePath(token));
}

function joinDestName(dest: string, src: string): string {
	return path.join(dest, path.basename(expandTildePath(src)));
}

/** The file operands of one write verb that the command would create,
 * overwrite, or delete. Option parsing covers the shapes agents actually
 * emit (short flags, `--`, `-t`/`--target-directory=`, sed's `-i` and
 * script options); exotic flags are treated as options, which can only
 * under-block. */
function verbTargets(verb: string, args: string[], dir: string): string[] {
	const operands: string[] = [];
	let targetDirOpt: string | undefined;
	let sedInPlace = false;
	let sedScriptOpt = false;
	for (let i = 0; i < args.length; i++) {
		const arg = args[i] ?? "";
		if (arg === "--") {
			for (let j = i + 1; j < args.length; j++) operands.push(args[j] ?? "");
			break;
		}
		if (arg.startsWith("-") && arg !== "-" && arg !== "") {
			if ((verb === "cp" || verb === "mv") && (arg === "-t" || arg === "--target-directory")) {
				targetDirOpt = args[i + 1];
				i += 1;
			} else if ((verb === "cp" || verb === "mv") && arg.startsWith("--target-directory=")) {
				targetDirOpt = arg.slice("--target-directory=".length);
			} else if (
				verb === "sed" &&
				(/^-i(\..+)?$/.test(arg) || arg === "--in-place" || arg.startsWith("--in-place="))
			) {
				sedInPlace = true;
			} else if (
				verb === "sed" &&
				(arg === "-e" || arg === "-f" || arg === "--expression" || arg === "--file" || arg === "--script")
			) {
				sedScriptOpt = true;
				i += 1;
			} else if (
				verb === "sed" &&
				(arg.startsWith("--expression=") || arg.startsWith("--file=") || arg.startsWith("--script="))
			) {
				sedScriptOpt = true;
			}
			continue;
		}
		operands.push(arg);
	}
	switch (verb) {
		case "tee":
		case "rm":
			// every file operand is a write target
			return operands;
		case "cp":
		case "mv": {
			if (operands.length === 0) return [];
			if (targetDirOpt !== undefined) {
				return operands.map((src) => joinDestName(targetDirOpt ?? "", src));
			}
			if (operands.length < 2) return [];
			const dest = operands[operands.length - 1] ?? "";
			const srcs = operands.slice(0, -1);
			if (dest.endsWith("/") || dest.endsWith("\\") || isExistingDir(resolveToken(dir, dest))) {
				// directory destination: the writes land as dest/<src name>
				return srcs.map((src) => joinDestName(dest, src));
			}
			return [dest];
		}
		case "sed": {
			if (!sedInPlace) return []; // without -i, sed writes stdout only
			// without -e/-f the first operand is the script; the rest are the files
			return sedScriptOpt ? operands : operands.slice(1);
		}
		default:
			return [];
	}
}

/** bash write-target check (D-1 layer 2): the write-structure target
 * arguments (redirect targets + tee/cp/mv/rm/sed -i operand sides) that
 * resolve to code paths, as the raw tokens appear in the command. Empty =
 * nothing gated. `cd` is tracked so relative targets resolve like the shell
 * would. Payload words are never scanned — only target sides. */
export function checkBashWriteTarget(
	command: string,
	root: string = resolveGateRoot(),
	cwd: string = process.cwd(),
): string[] {
	if (typeof command !== "string" || command === "") return [];
	const hits: string[] = [];
	let dir = cwd;
	for (const segment of parseBashSegments(command)) {
		const argv = stripEnvAssignments(segment.words);
		const verb = argv.length > 0 ? path.basename(argv[0] ?? "") : "";
		if (verb === "cd" && argv.length === 2) {
			dir = resolveToken(dir, argv[1] ?? "");
			continue;
		}
		for (const target of segment.redirectTargets) {
			if (isCodePathAbs(resolveToken(dir, target), root)) hits.push(target);
		}
		if (argv.length > 0 && WRITE_VERBS.has(verb)) {
			for (const target of verbTargets(verb, argv.slice(1), dir)) {
				if (isCodePathAbs(resolveToken(dir, target), root)) hits.push(target);
			}
		}
	}
	return hits;
}

// ============================================================================
// Gate decision + registration
// ============================================================================

export interface GateDecision {
	/** True when the tool call must be blocked. */
	blocked: boolean;
	/** Block reason (always present when blocked=true): why + the two
	 * compliant paths. */
	reason?: string;
	/** Machine-readable decision basis: not-gated-tool | no-path |
	 * no-command | not-a-code-path | no-code-path-target | claim |
	 * worker-env | mini-spec:<path> | no-claim-no-mini. */
	basis: string;
	/** The gated code path (write/edit input path, or the first bash write
	 * target hit), for the audit line. */
	target?: string;
}

/** The tool input shape the gate reads (write/edit `path`, bash `command`).
 * Structural so the typed tool events pass through without casts. */
export interface GateToolInput {
	path?: unknown;
	command?: unknown;
}

function miniSpecBasis(mini: string, root: string): string {
	const rel = path.relative(root, mini);
	const shown = rel === "" || rel.startsWith("..") ? mini : rel;
	return `mini-spec:${toForwardSlashes(shown)}`;
}

function blockReason(toolName: string, targets: string[], root: string): string {
	const targetsText = targets.length === 1 ? (targets[0] ?? "") : targets.join(", ");
	return (
		`implementation-gate: blocked ${toolName} targeting code path ${targetsText}: this window holds no active ` +
		`AgenticTask key claim (no status=active row in ${AGENTICDOC_DIR}/${INDEX_FILE} matches claim id ` +
		`${currentClaimId()}), ${ENV_WORKER_TASK} is not set, and no ${AGENTICDOC_DIR}/*/mini-spec.md is newer ` +
		`than 24h (root: ${root}). ${GATE_EXPLANATION}`
	);
}

/** The gate decision for one tool call (D-3): not gated / not a code path →
 * pass; a code path passes on the three-condition OR (active claim for this
 * host:pid, worker env, fresh mini-spec); otherwise blocked with guidance.
 * env and cwd injectable for tests; root comes from env
 * (MW_IMPL_GATE_ROOT) or the process cwd. */
export function gateDecision(
	toolName: string,
	input: GateToolInput,
	env: NodeJS.ProcessEnv,
	cwd: string = process.cwd(),
): GateDecision {
	if (toolName !== "write" && toolName !== "edit" && toolName !== "bash") {
		return { blocked: false, basis: "not-gated-tool" };
	}
	const root = resolveGateRoot(env);
	let targets: string[];
	if (toolName === "bash") {
		const command = input.command;
		if (typeof command !== "string" || command === "") {
			return { blocked: false, basis: "no-command" };
		}
		targets = checkBashWriteTarget(command, root, cwd);
		if (targets.length === 0) return { blocked: false, basis: "no-code-path-target" };
	} else {
		const rawPath = input.path;
		if (typeof rawPath !== "string" || rawPath === "") {
			return { blocked: false, basis: "no-path" };
		}
		if (!isCodePath(rawPath, root, cwd)) return { blocked: false, basis: "not-a-code-path" };
		targets = [rawPath];
	}

	if (hasActiveKeyClaim(root, currentClaimId())) {
		return { blocked: false, basis: "claim", target: targets[0] };
	}
	const workerTask = env[ENV_WORKER_TASK];
	if (typeof workerTask === "string" && workerTask !== "") {
		return { blocked: false, basis: "worker-env", target: targets[0] };
	}
	const mini = findFreshMiniSpec(root);
	if (mini !== undefined) {
		return { blocked: false, basis: miniSpecBasis(mini, root), target: targets[0] };
	}
	return {
		blocked: true,
		reason: blockReason(toolName, targets, root),
		basis: "no-claim-no-mini",
		target: targets[0],
	};
}

/** Append one audit line to <root>/.agenticdoc/_impl_gate.log (D-6):
 * `[GATE] <ISO> <tag> tool=<t> target=<p> basis=<b>`. Append-only (never
 * read-modify-write — pitfall P-003), best-effort: a failure here must
 * never change the decision. */
export function recordImplGateAudit(
	tag: "blocked" | "mini-pass",
	toolName: string,
	target: string,
	basis: string,
	root: string = resolveGateRoot(),
): void {
	try {
		const dir = path.join(root, AGENTICDOC_DIR);
		fs.mkdirSync(dir, { recursive: true });
		fs.appendFileSync(
			path.join(dir, GATE_LOG_FILE),
			`[GATE] ${new Date().toISOString()} ${tag} tool=${toolName} target=${target} basis=${basis}\n`,
			"utf8",
		);
	} catch {
		// best-effort audit — the decision itself already stands
	}
}

/** Register the tool_call gate (D-1/D-2): write/edit/bash calls are decided
 * by gateDecision; a block returns {block, reason} so the tool never runs;
 * every block and every mini fast-path pass appends one audit line. Runs in
 * every mode (PM, worker, interactive). */
export function registerImplementationGate(pi: ExtensionAPI): void {
	pi.on("tool_call", (event) => {
		if (event.toolName !== "write" && event.toolName !== "edit" && event.toolName !== "bash") {
			return undefined;
		}
		const decision = gateDecision(event.toolName, event.input, process.env);
		if (decision.blocked) {
			recordImplGateAudit("blocked", event.toolName, decision.target ?? "", decision.basis);
			return { block: true, reason: decision.reason };
		}
		if (decision.basis.startsWith("mini-spec")) {
			recordImplGateAudit("mini-pass", event.toolName, decision.target ?? "", decision.basis);
		}
		return undefined;
	});
}
