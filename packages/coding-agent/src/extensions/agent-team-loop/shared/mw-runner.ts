import { spawn, spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

export interface MwStatus {
	running: boolean;
	pid: number | null;
}

const PYTHON_EXE = process.platform === "win32" ? "python" : "python3";

/** Resolve mw.py: MW_PY env override → relative from extension source → null */
export function findMwPy(): string | null {
	const envPath = process.env.MW_PY;
	if (envPath && fs.existsSync(envPath)) return envPath;

	try {
		// Works when jiti loads the source file (development); not in a bundled binary.
		const here = path.dirname(fileURLToPath(import.meta.url));
		const candidate = path.resolve(here, "../../../../../multi-workers/mw.py");
		if (fs.existsSync(candidate)) return candidate;
	} catch {
		// import.meta.url is not a file URL (bundled binary) — fall through
	}

	return null;
}

function pidFilePath(projectDir: string): string {
	return path.join(projectDir, ".mw", "mw.pid");
}

export function getMwStatus(projectDir: string): MwStatus {
	const pidPath = pidFilePath(projectDir);
	if (!fs.existsSync(pidPath)) return { running: false, pid: null };
	const raw = fs.readFileSync(pidPath, "utf8").trim();
	const pid = Number.parseInt(raw, 10);
	if (Number.isNaN(pid)) return { running: false, pid: null };

	// Signal 0: check process liveness without sending a signal
	try {
		process.kill(pid, 0);
		return { running: true, pid };
	} catch {
		return { running: false, pid: null };
	}
}

/**
 * Run mw init via `mw.py init --project=<dir>` (synchronous — creates directory structure).
 * Returns { ok: true } on success, or { ok: false, error } on failure.
 */
export function initMw(projectDir: string): { ok: true } | { ok: false; error: string } {
	const mwPy = findMwPy();
	if (!mwPy) return { ok: false, error: "Could not find mw.py — set MW_PY env var." };

	const result = spawnSync(PYTHON_EXE, [mwPy, "init", `--project=${projectDir}`], {
		encoding: "utf8",
		timeout: 30_000,
	});
	if (result.error) {
		return { ok: false, error: `Failed to spawn mw.py: ${result.error.message}` };
	}
	if (result.status !== 0) {
		const stderr = result.stderr?.trim();
		return { ok: false, error: stderr || `mw init exited with code ${result.status}` };
	}
	return { ok: true };
}

/**
 * Start mw in the background via `mw.py start --project=<dir>`.
 * Returns true if the spawn was attempted, false if mw.py could not be found.
 */
export function startMw(projectDir: string): boolean {
	const mwPy = findMwPy();
	if (!mwPy) return false;

	const child = spawn(PYTHON_EXE, [mwPy, "start", `--project=${projectDir}`], {
		detached: true,
		stdio: "ignore",
		windowsHide: true,
	});
	child.unref();
	return true;
}

/**
 * Stop mw via `mw.py stop --project=<dir>` (synchronous, waits up to 10s via mw's own logic).
 * Returns true if the command was executed.
 */
export function stopMw(projectDir: string): boolean {
	const mwPy = findMwPy();
	if (!mwPy) return false;

	// Inherit stdio so the stop message is visible to the caller
	const result = spawn(PYTHON_EXE, [mwPy, "stop", `--project=${projectDir}`], {
		stdio: "inherit",
	});
	result.unref();
	return true;
}
