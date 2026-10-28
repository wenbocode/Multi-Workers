import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";

/**
 * Cross-window protected-config guard (hard block).
 *
 * Why (incident 2026-09-15): a running session cleared ~/.pi/agent/auth.json
 * while other pi windows were live. auth.json is the credential store shared
 * by EVERY window (AuthStorage hot-reloads it on file revision), so the clear
 * instantly broke them all ("Error: Provider is not configured: timi") and
 * several hung. models.json / settings.json / oauth.json (legacy credential
 * store) have the same blast radius: they are live config for every open
 * session and must never be modified from inside one.
 *
 * Rule: agent tool calls must not create, modify, move, or delete the
 * protected files or the agent dir. This session being alive is already proof
 * that "runtime" is on, so the block is unconditional — there is no
 * agent-side override. Reads stay allowed. A human who needs to change these
 * files closes pi windows and edits from a plain terminal, or uses pi /login
 * (a core flow, outside the tool layer). The mw bootstrap hint instructs the
 * user the same way; framework Python code never writes these files
 * (mw_common.assert_not_protected_agent_config carries the rule there).
 *
 * Mechanics: write/edit tool paths are resolved like the tools do (relative
 * against cwd, leading ~ expanded) and compared to the protected set. bash
 * commands get their home/env-var spellings expanded (~, $HOME, %USERPROFILE%,
 * $env:USERPROFILE, PI_CODING_AGENT_DIR forms), then a write-construct scan
 * — fail-closed: a command that both references a protected path and carries
 * any write construct is denied even when the reference is its read side;
 * rerun the read part alone. This is a text-level heuristic, not a sandbox:
 * obfuscated one-liners are covered best-effort (python -c / node -e write
 * markers), plain writes are covered exactly.
 *
 * Not protected: ~/.pi/agent/extensions (the extension bundle loads at
 * startup, so replacing it mid-run does not corrupt live sessions).
 */

const IS_WIN32 = process.platform === "win32";

/** Protected file names inside the pi agent dir. */
const PROTECTED_CONFIG_FILES = ["auth.json", "models.json", "settings.json", "oauth.json"] as const;

/** Mirrors ENV_AGENT_DIR in core config.ts (APP_NAME "pi"): the agentDir
 * override. The extension must not import core config — the standalone
 * esbuild bundle (build-extension.sh) stays self-contained — so the
 * resolution is mirrored here; core getAgentDir() remains canonical. */
const ENV_AGENT_DIR = "PI_CODING_AGENT_DIR";

const GUARD_EXPLANATION =
	"~/.pi/agent/{auth,models,settings,oauth}.json are cross-window config shared by every live pi session " +
	"(credentials hot-reload per window). Modifying them from a running session breaks the other windows " +
	"(2026-09-15 incident: clearing auth.json broke every open window with 'Provider is not configured'). " +
	"Reads are allowed. To change credentials/models/settings: close pi windows and edit from a plain " +
	"terminal, or use pi /login (core flow, outside the tool layer).";

function fold(p: string): string {
	return IS_WIN32 ? p.toLowerCase() : p;
}

function toForwardSlashes(p: string): string {
	return p.replaceAll("\\", "/");
}

function escapeRegExp(s: string): string {
	return s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/** Fragment boundary: the match must not continue into a word character or
 * dash (`.pi/agent` yes, `.pi/agents` / `.pi/agent-x` no). */
function boundary(): string {
	return "(?![\\w-])";
}

/** Is the given path fragment present in scan text with a proper boundary? */
function fragmentPresent(scan: string, frag: string): boolean {
	return new RegExp(escapeRegExp(frag) + boundary()).test(scan);
}

/** Tilde expansion only (mirrors core normalizePath's tilde branch): `~`
 * and `~/x` fold onto the home dir; everything else is returned unchanged —
 * relative paths stay relative so callers resolve them against THEIR base. */
function expandTildePath(p: string): string {
	if (p === "~") return os.homedir();
	if (p.startsWith("~/") || p.startsWith("~\\")) {
		return path.join(os.homedir(), p.slice(2));
	}
	return p;
}

/** Resolve the pi agent dir, mirroring core getAgentDir(): the env override
 * (tilde-expanded, resolved to absolute) wins, else ~/.pi/agent. env
 * injectable for tests. */
export function resolveAgentDir(env: NodeJS.ProcessEnv = process.env): string {
	const raw = env[ENV_AGENT_DIR];
	if (typeof raw === "string" && raw !== "") {
		return path.resolve(expandTildePath(raw));
	}
	return path.join(os.homedir(), ".pi", "agent");
}

/** Absolute paths of the protected files for one agent dir. */
export function protectedConfigPaths(agentDir: string): string[] {
	return PROTECTED_CONFIG_FILES.map((name) => path.join(agentDir, name));
}

/** Does a write/edit tool path target a protected config file (or the agent
 * dir itself)? Pure: resolves the path like the tools do (cwd-relative, ~
 * expanded) and compares folded. */
export function isProtectedConfigPath(agentDir: string, rawPath: string, cwd: string = process.cwd()): boolean {
	if (typeof rawPath !== "string" || rawPath === "") return false;
	const target = fold(path.normalize(path.resolve(cwd, expandTildePath(rawPath))));
	if (target === fold(path.normalize(agentDir))) return true;
	return protectedConfigPaths(agentDir).some((p) => target === fold(path.normalize(p)));
}

/** Expand home/agentDir env-var spellings inside a bash command so ~, $HOME,
 * ${HOME}, %USERPROFILE%, $env:USERPROFILE and the PI_CODING_AGENT_DIR forms
 * all fold onto the same absolute prefixes before fragment matching. */
function expandCommandReferences(command: string, agentDir: string): string {
	const home = os.homedir();
	let s = command;
	for (const v of ["$HOME", `\${HOME}`, "%USERPROFILE%", "$env:USERPROFILE", "$Env:USERPROFILE"]) {
		s = s.split(v).join(home);
	}
	for (const v of [`$${ENV_AGENT_DIR}`, `\${${ENV_AGENT_DIR}}`, `%${ENV_AGENT_DIR}%`]) {
		s = s.split(v).join(agentDir);
	}
	// Word-leading ~ (tilde expansion at command positions; quoted or not).
	s = s.replace(/(^|[\s;&|(='"])~/g, (_m: string, prefix: string) => prefix + home);
	return s;
}

/** Normalized bash scan text: references expanded, win32-folded, backslashes
 * unified to forward slashes. */
function bashScanText(command: string, agentDir: string): string {
	return toForwardSlashes(fold(expandCommandReferences(command, agentDir)));
}

/** Protected-path references present in bash scan text, for the block
 * reason. Matches the home-prefixed `.pi/agent` tree (any spelling after
 * expansion) and, when PI_CODING_AGENT_DIR points elsewhere, that absolute
 * dir; a project-relative `.pi/agent` matches only when the command first
 * `cd`s into the home dir, because then the relative form resolves there. */
function protectedReferences(scan: string, agentDir: string): string[] {
	const homeFrag = `${toForwardSlashes(fold(os.homedir()))}/.pi/agent`;
	const dirFrag = toForwardSlashes(fold(path.normalize(agentDir)));
	const refs: string[] = [];
	if (fragmentPresent(scan, homeFrag)) refs.push(homeFrag);
	if (dirFrag !== homeFrag && fragmentPresent(scan, dirFrag)) refs.push(dirFrag);
	const homeAbs = toForwardSlashes(fold(os.homedir()));
	const cdHome = new RegExp(`(?:^|[\\s;&|(])cd\\s+["']?${escapeRegExp(homeAbs)}["']?${boundary()}`);
	if (cdHome.test(scan) && fragmentPresent(scan, ".pi/agent")) {
		refs.push(`${homeFrag} (relative after cd ~)`);
	}
	return refs;
}

/** Shell/PowerShell write verbs (word-bounded so 'perm'/'delete' prose does
 * not fire; the dashed PowerShell cmdlets are matched as plain substrings). */
const WRITE_VERB_RE =
	/\b(rm|rmdir|rd|del|erase|mv|move|ren|rename|cp|copy|rsync|install|dd|tee|shred|truncate|touch|chmod|chown|ln)\b/i;
const POWERSHELL_WRITE_RE =
	/\b(remove-item|move-item|copy-item|rename-item|new-item|set-content|add-content|clear-content|out-file)\b/i;
const SED_IN_PLACE_RE = /\bsed\b[^\n;&|]*(?:\s-i(?:\.\w+)?\b|--in-place\b)/i;
const FIND_WRITE_RE = /\bfind\b[^\n;&|]*(\s-delete\b|\s-exec\b|\s-execdir\b)/i;
/** Redirects (`>`, `>>`, `2>`) with a capture of the target token. */
const REDIRECT_RE = /(?:^|[\s;&|(])\d?>{1,2}\s*("[^"]*"|'[^']*'|[^\s;&|>]+)/g;
/** Inline code execution: `python -c`, `node -e`, `node --eval`, or a
 * heredoc/stdin pipe into python/node. */
const INLINE_CODE_RE = /\b(python3?|node)\b[^\n;&|]*(\s-c\b|\s-e\b|\s--eval\b|<<)/i;
/** Write-mode markers that make inline code a protected-write risk. */
const INLINE_WRITE_MARKER_RE =
	/(['"][wa]['"]|writefile|write_file|unlink|rmsync|rmtree|os\.remove|os\.rename|shutil\.(move|copy|copyfile)|truncate\(|appendfile|open\([^)]*,\s*['"][wa]['"])/i;

export interface BashGuardVerdict {
	/** True when the command must be blocked (protected reference + write
	 * construct, or a redirect whose target is protected). */
	prohibited: boolean;
	/** Block reason (always present when prohibited=true). */
	reason?: string;
}

/** Decision for one bash tool command: fail-closed — any protected-path
 * reference plus any write construct is denied, redirect targets are checked
 * separately (a redirect to an unprotected path with a protected read side
 * stays allowed). Inline code (python -c / node -e) with a write marker also
 * matches a bare `.pi/agent` fragment, because path assembly via string
 * concat / process.env access defeats the reference expansion. */
export function checkProtectedBashCommand(agentDir: string, command: string): BashGuardVerdict {
	if (typeof command !== "string" || command === "") return { prohibited: false };
	const scan = bashScanText(command, agentDir);
	const refs = protectedReferences(scan, agentDir);
	const inline = INLINE_CODE_RE.test(scan) && INLINE_WRITE_MARKER_RE.test(scan);
	const bareFragment = new RegExp(escapeRegExp(".pi/agent") + boundary()).test(scan);
	if (refs.length === 0 && !(inline && bareFragment)) return { prohibited: false };

	const constructs: string[] = [];
	if (WRITE_VERB_RE.test(scan)) constructs.push("write verb");
	if (POWERSHELL_WRITE_RE.test(scan)) constructs.push("powershell write cmdlet");
	if (SED_IN_PLACE_RE.test(scan)) constructs.push("sed -i");
	if (FIND_WRITE_RE.test(scan)) constructs.push("find -delete/-exec");
	for (const m of scan.matchAll(REDIRECT_RE)) {
		const target = (m[1] ?? "").replace(/^["']|["']$/g, "");
		if (target !== "" && protectedReferences(target, agentDir).length > 0) constructs.push("redirect target");
	}
	if (inline) constructs.push("inline code write");

	if (constructs.length === 0) return { prohibited: false };
	const refText = refs.length > 0 ? refs.join(", ") : ".pi/agent (path assembled inside inline code)";
	return {
		prohibited: true,
		reason:
			`protected-config: blocked a bash command referencing cross-window config (${refText}) ` +
			`with a write construct (${constructs.join(", ")}). ${GUARD_EXPLANATION}`,
	};
}

/** Worker-mode visibility: append one [PROTECTED_CONFIG] line to the task's
 * trace.log (dirname of PI_WORKER_TASK — the same file the PM watch reads
 * live) so a blocked worker shows up immediately. Best-effort: a failure
 * here must never break the block itself. taskPathEnv injectable for tests. */
export function recordProtectedBlockTrace(
	toolName: string,
	detail: string,
	taskPathEnv: string | undefined = process.env.PI_WORKER_TASK,
): void {
	if (!taskPathEnv) return;
	try {
		const dir = path.dirname(path.resolve(taskPathEnv));
		fs.mkdirSync(dir, { recursive: true });
		const first = detail.split("\n")[0] ?? "";
		fs.appendFileSync(
			path.join(dir, "trace.log"),
			`[PROTECTED_CONFIG] ${new Date().toISOString()} blocked tool=${toolName} target=${first}\n`,
			"utf8",
		);
	} catch {
		// best-effort diagnostic — the block itself already happened
	}
}

/** Register the tool_call hard block: write/edit paths and bash commands are
 * checked against the protected set; everything else (including all reads)
 * passes through untouched. Runs in every mode (PM, worker, interactive). */
export function registerProtectedConfigGuard(pi: ExtensionAPI): void {
	const agentDir = resolveAgentDir();
	pi.on("tool_call", (event) => {
		if (event.toolName === "write" || event.toolName === "edit") {
			const rawPath = event.input.path;
			if (typeof rawPath === "string" && rawPath !== "" && isProtectedConfigPath(agentDir, rawPath)) {
				recordProtectedBlockTrace(event.toolName, rawPath);
				return {
					block: true,
					reason: `protected-config: blocked ${event.toolName} of ${rawPath}. ${GUARD_EXPLANATION}`,
				};
			}
			return undefined;
		}
		if (event.toolName === "bash") {
			const command = event.input.command;
			if (typeof command === "string" && command !== "") {
				const verdict = checkProtectedBashCommand(agentDir, command);
				if (verdict.prohibited) {
					recordProtectedBlockTrace(event.toolName, command);
					return { block: true, reason: verdict.reason };
				}
			}
			return undefined;
		}
		return undefined;
	});
}
