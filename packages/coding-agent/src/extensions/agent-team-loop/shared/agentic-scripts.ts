import { execFile, spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { findMwPy, PYTHON_EXE } from "./mw-runner.ts";

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

/** Done may need a read-only attestation from this PM process while the
 * native script is running. Leave the event loop available to answer it. */
export async function runAgenticDone(
	projectDir: string,
	args: string[],
	signal?: AbortSignal,
): Promise<AgenticScriptResult> {
	let dir: string;
	const markerPath = path.join(projectDir, ".agentic-framework");
	try {
		const repo = fs.existsSync(markerPath)
			? /^repo=(.+)$/m.exec(fs.readFileSync(markerPath, "utf8"))?.[1]?.trim()
			: path.join(projectDir, ".agents", "skills", "agentic-task");
		if (!repo || !path.isAbsolute(repo))
			return { ok: false, output: "AgenticTask framework marker has no absolute repo path." };
		const probe = await new Promise<string>((resolve, reject) => {
			execFile(
				PYTHON_EXE,
				["-X", "utf8", path.join(repo, "scripts", "detect_root.py"), "--json"],
				{ cwd: projectDir, encoding: "utf8", timeout: 10_000, windowsHide: true, signal },
				(error, stdout) => (error ? reject(error) : resolve(stdout)),
			);
		});
		const { PROJECT_ROOT, PLATFORM_DIR } = JSON.parse(probe) as {
			PROJECT_ROOT?: unknown;
			PLATFORM_DIR?: unknown;
		};
		if (
			typeof PROJECT_ROOT !== "string" ||
			typeof PLATFORM_DIR !== "string" ||
			!path.isAbsolute(PLATFORM_DIR) ||
			path.relative(fs.realpathSync.native(PROJECT_ROOT), fs.realpathSync.native(projectDir)) !== ""
		)
			return { ok: false, output: "AgenticTask framework resolved a different project root." };
		dir = path.join(PLATFORM_DIR, "scripts");
	} catch (error) {
		const reason = error instanceof Error ? error.message : String(error);
		return { ok: false, output: `AgenticTask framework could not be verified: ${reason}` };
	}
	const script = path.join(dir, "advance_phase.py");
	const mw = findMwPy();
	if (mw) {
		const preflight = await new Promise<AgenticScriptResult>((resolve) => {
			execFile(
				PYTHON_EXE,
				["-X", "utf8", mw, "decide", "sign", args[0]!, "--project", projectDir, "--for-done", "--json"],
				{ cwd: projectDir, encoding: "utf8", timeout: 30_000, windowsHide: true, signal },
				(error, stdout, stderr) => {
					resolve({ ok: !error, output: `${stdout}${stderr}`.trim() || error?.message || "(no output)" });
				},
			);
		});
		if (!preflight.ok) return { ok: false, output: `Done sign-off blocked: ${preflight.output}` };
	}
	return new Promise((resolve) => {
		execFile(
			PYTHON_EXE,
			["-X", "utf8", script, ...args],
			{ cwd: projectDir, encoding: "utf8", timeout: 30_000, windowsHide: true, signal },
			(error, stdout, stderr) => {
				const output = `${stdout}${stderr}`.trim();
				resolve({ ok: !error, output: output || error?.message || "(no output)" });
			},
		);
	});
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
		const code = source.replace(/#[^\r\n]*/g, "");
		// Newer framework scripts also import contract helpers from this module.
		const imported = [...code.matchAll(/^from[ \t]+plan_closure[ \t]+import[ \t]+(\([^)]*\)|[^\r\n]+)/gm)].some(
			([, names = ""]) => {
				const entries = names.startsWith("(") ? names.slice(1, -1) : names;
				return entries.split(",").some((entry) => {
					const binding = /^problems(?:[ \t]+as[ \t]+([A-Za-z_]\w*))?$/.exec(entry.trim());
					return binding !== null && new RegExp(`\\b${binding[1] ?? "problems"}\\s*\\(`).test(code);
				});
			},
		);
		if (
			!fs.statSync(closure).isFile() ||
			!imported ||
			!/["']tasks["']\s*:\s*\[\s*\(\s*["']plan\.md["']\s*,\s*["']plan_closure["']/.test(code)
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
		const mw = findMwPy();
		if (!mw) return { ok: false, output: "MW scope review requires a runnable MW Python installation." };
		const scope = spawnSync(
			PYTHON_EXE,
			["-X", "utf8", path.join(path.dirname(mw), "scope_review.py"), projectDir, args[0]!],
			{ cwd: projectDir, encoding: "utf8", timeout: timeoutMs, windowsHide: true },
		);
		if (scope.status !== 0)
			return { ok: false, output: (scope.stderr || scope.error?.message || "Scope review failed.").trim() };
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
