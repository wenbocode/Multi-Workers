import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { PYTHON_EXE } from "./mw-runner.ts";

/**
 * Locate the installed AgenticTask framework's scripts directory
 * (advance_phase.py / update_index.py / audit_phase.py / detect_root.py).
 *
 * Resolution order:
 *   1. {projectDir}/.claude/scripts — the installed mirror every platform
 *      workflow references as {PLATFORM_DIR}/scripts (written by install.py,
 *      refreshed by sync_framework.py).
 *   2. {projectDir}/.agents/skills/agentic-task/claude/scripts — the skill
 *      clone install.py leaves behind (same content; survives a partial
 *      install where .claude was not laid down).
 *
 * Returns null when neither exists (`mw init --no-framework` / framework not
 * installed) — callers fail closed with an actionable message.
 */
export function agenticScriptsDir(projectDir: string): string | null {
	const candidates = [
		path.join(projectDir, ".claude", "scripts"),
		path.join(projectDir, ".agents", "skills", "agentic-task", "claude", "scripts"),
	];
	for (const dir of candidates) {
		if (fs.existsSync(path.join(dir, "advance_phase.py"))) return dir;
	}
	return null;
}

export interface AgenticScriptResult {
	ok: boolean;
	/** Combined stdout+stderr — the gate scripts print failures to stderr. */
	output: string;
}

/** Inspect the same installation the window will invoke, without executing project code at startup. */
export function inspectPlanGate(projectDir: string): AgenticScriptResult {
	const dir = agenticScriptsDir(projectDir);
	if (!dir)
		return {
			ok: false,
			output: `AgenticTask framework scripts not found under ${projectDir}. Run the framework installer.`,
		};
	const advance = path.join(dir, "advance_phase.py");
	const closure = path.join(dir, "plan_closure.py");
	try {
		const source = fs.readFileSync(advance, "utf8");
		const imported = /^from plan_closure import problems(?: as (\w+))?\s*$/m.exec(source);
		if (
			!fs.statSync(closure).isFile() ||
			!imported ||
			!new RegExp(`\\b${imported[1] ?? "problems"}\\s*\\(`).test(source) ||
			!/["']tasks["']\s*:\s*\[\s*\(\s*["']plan\.md["']\s*,\s*["']plan_closure["']/.test(source)
		) {
			throw new Error("missing PLAN → TASKS closure registration");
		}
		return { ok: true, output: advance };
	} catch (error) {
		return {
			ok: false,
			output: `AgenticTask PLAN → TASKS gate unavailable in ${dir}: ${error instanceof Error ? error.message : String(error)}. Update the installed AgenticTask scripts.`,
		};
	}
}

/**
 * Run one AgenticTask framework script directly: spawn with list args, no
 * shell. Same execution model as mw-runner's mw.py calls, so framework state
 * operations never depend on the agent window's bash tool — a fresh machine
 * whose pi shell resolution or in-shell `python` PATH differs (WSL-only bash,
 * Store-stub python, python3-only Linux) can still advance phases.
 */
export function runAgenticScript(
	projectDir: string,
	scriptName: string,
	args: string[],
	timeoutMs = 30_000,
): AgenticScriptResult {
	const dir = agenticScriptsDir(projectDir);
	if (!dir) {
		return {
			ok: false,
			output:
				"AgenticTask framework scripts not found (looked for .claude/scripts/advance_phase.py and " +
				".agents/skills/agentic-task/claude/scripts/advance_phase.py under the project root). " +
				"Run the framework installer (mw setup / install.py) first.",
		};
	}
	const script = path.join(dir, scriptName);
	if (!fs.existsSync(script)) {
		return { ok: false, output: `Framework script not found: ${script}` };
	}
	if (scriptName === "advance_phase.py" && args[1]?.toLowerCase() === "tasks") {
		const gate = inspectPlanGate(projectDir);
		if (!gate.ok) return gate;
	}
	// -X utf8: framework gate scripts print Chinese diagnostics; a Windows
	// console default (cp936) read back as utf8 would turn them into '?'.
	const result = spawnSync(PYTHON_EXE, ["-X", "utf8", script, ...args], {
		cwd: projectDir,
		encoding: "utf8",
		timeout: timeoutMs,
		windowsHide: true,
	});
	if (result.error) {
		return {
			ok: false,
			output:
				`Failed to spawn ${PYTHON_EXE} for ${scriptName}: ${result.error.message}. ` +
				`Install Python and make sure '${PYTHON_EXE}' resolves on this machine's PATH.`,
		};
	}
	if (result.status === null) {
		return {
			ok: false,
			output: `${scriptName} was killed before finishing (signal ${result.signal ?? "?"}) — timeout?`,
		};
	}
	const output = `${result.stdout ?? ""}${result.stderr ?? ""}`.trim();
	if (result.status !== 0) {
		return { ok: false, output: output || `${scriptName} exited with code ${result.status}` };
	}
	return { ok: true, output: output || "(no output)" };
}
