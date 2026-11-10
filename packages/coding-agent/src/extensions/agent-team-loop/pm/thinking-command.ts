import type { ExtensionCommandContext } from "../../../core/extensions/types.ts";
import { type MwCliResult, thinkingMw } from "../shared/mw-runner.ts";

/**
 * `/mw thinking ...` — strict, thin window face over `mw.py thinking`.
 *
 * Python is the single source of YAML semantics; this module NEVER edits the
 * config, never re-implements role/level rules beyond the closed validation
 * needed to reject illegal input before a subprocess starts, and forwards an
 * argv array (never a shell string) through `thinkingMw`. The runner is
 * injectable so the real registered `/mw` handler can be driven offline.
 *
 * Accepted shapes (bare `thinking` == `show`):
 *   /mw thinking [show]
 *   /mw thinking set   <default|role> <level>
 *   /mw thinking clear <default|role|all>
 */

/** Worker roles the thinking config accepts. `main` (the PM/model role) and any
 * role alias are deliberately excluded — thinking never targets `main`. */
export const THINKING_ROLES = ["coding", "review", "research", "vision", "decide_prepare"] as const;

/** Closed level set. Kept here only as a pre-spawn guard; Python owns the real
 * validation/serialization (including keeping `off` a string). */
export const THINKING_LEVELS = ["off", "minimal", "low", "medium", "high", "xhigh", "max"] as const;

const SET_TARGETS: ReadonlySet<string> = new Set<string>(["default", ...THINKING_ROLES]);
const CLEAR_TARGETS: ReadonlySet<string> = new Set<string>(["default", "all", ...THINKING_ROLES]);
const LEVELS: ReadonlySet<string> = new Set<string>(THINKING_LEVELS);

/** A valid token is a bare lowercase word (underscore allowed for
 * `decide_prepare`). Anything with quotes, punctuation, flags, paths, shell
 * metacharacters, uppercase or digits is rejected before any subprocess runs —
 * so an unpaired quote or an injected `;`/`&&` never reaches spawnSync. */
const TOKEN_RE = /^[a-z_]+$/;

export const THINKING_USAGE =
	"Usage: /mw thinking [show] | set <default|coding|review|research|vision|decide_prepare> " +
	"<off|minimal|low|medium|high|xhigh|max> | clear <default|coding|review|research|vision|decide_prepare|all>";

/** Split into closed-set tokens. Returns null when any token is not a bare
 * lowercase word (unpaired/mismatched quotes, shell metacharacters, extra
 * paths, flags…), so the caller rejects with zero subprocess side effects. */
function tokenize(argsText: string): string[] | null {
	const trimmed = argsText.trim();
	if (trimmed === "") return [];
	const parts = trimmed.split(/\s+/);
	return parts.every((part) => TOKEN_RE.test(part)) ? parts : null;
}

/** Notify a runner result on the correct channel. A successful mutate appends
 * the next-spawn reminder (the launcher resolves thinking per spawn, so the
 * current PM and running workers are unchanged); `show` is read-only and never
 * writes the config, so it gets no mutate notice. */
function report(ctx: ExtensionCommandContext, action: string, result: MwCliResult, mutate: boolean): void {
	if (!result.ok) {
		ctx.ui.notify(`mw thinking ${action} failed: ${result.error}`, "error");
		return;
	}
	const notice = result.output || `mw thinking ${action}: ok`;
	ctx.ui.notify(
		mutate
			? `${notice}\nApplies on the next worker spawn (no serve restart); current PM/workers are unchanged.`
			: notice,
		"info",
	);
}

export async function runMwThinkingCommand(
	ctx: ExtensionCommandContext,
	projectDir: string,
	argsText: string,
	runner: (projectDir: string, args: string[]) => MwCliResult = thinkingMw,
): Promise<void> {
	const parts = tokenize(argsText);
	if (parts === null) {
		ctx.ui.notify(THINKING_USAGE, "warning");
		return;
	}

	// Bare `thinking` (parts === []) defaults to `show`.
	const action = parts.length === 0 ? "show" : parts[0];

	let args: string[];
	let mutate: boolean;

	if (action === "show") {
		// Only `[]` (bare) and `["show"]` are legal; show never takes a trailing
		// token (unlike the wider model show).
		if (parts.length > 1) {
			ctx.ui.notify(`/mw thinking show takes no arguments. ${THINKING_USAGE}`, "warning");
			return;
		}
		args = ["show"];
		mutate = false;
	} else if (action === "set") {
		const target = parts[1];
		const level = parts[2];
		// Exact arity, closed target (no `main`, no `all`, no alias) and level.
		if (parts.length !== 3 || !target || !level || !SET_TARGETS.has(target) || !LEVELS.has(level)) {
			ctx.ui.notify(`/mw thinking set needs <default|role> <level>. ${THINKING_USAGE}`, "warning");
			return;
		}
		args = ["set", target, level];
		mutate = true;
	} else if (action === "clear") {
		const target = parts[1];
		// Exact arity, closed target (adds `all`, still no `main`/alias).
		if (parts.length !== 2 || !target || !CLEAR_TARGETS.has(target)) {
			ctx.ui.notify(`/mw thinking clear needs <default|role|all>. ${THINKING_USAGE}`, "warning");
			return;
		}
		args = ["clear", target];
		mutate = true;
	} else {
		// Unknown action: main, role aliases, misspellings, stray verbs, etc.
		ctx.ui.notify(`Unknown /mw thinking action '${action}'. ${THINKING_USAGE}`, "warning");
		return;
	}

	let result: MwCliResult;
	try {
		result = runner(projectDir, args);
	} catch (err) {
		// A throwing runner (e.g. a spawnSync that throws) becomes an error
		// notification instead of an unhandled handler rejection.
		ctx.ui.notify(`mw thinking ${action} failed: ${String(err)}`, "error");
		return;
	}
	report(ctx, action, result, mutate);
}
