import { spawn, spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

export interface MwStatus {
	running: boolean;
	pid: number | null;
}

const PYTHON_EXE = process.platform === "win32" ? "python" : "python3";

/** pi's global extensions dir — mirrors _global_ext_dir() in mw.py. */
function globalExtDir(): string {
	const envDir = process.env.PI_CODING_AGENT_DIR;
	const base = envDir ? envDir : path.join(os.homedir(), ".pi", "agent");
	return path.join(base, "extensions");
}

/**
 * Resolve mw.py, in order:
 *   1. MW_PY env override
 *   2. `.mw-py-path` sidecar written by `mw setup`/`mw build --install` — the
 *      reliable path when the bundle is loaded from the GLOBAL install dir in an
 *      unrelated project (where the repo-relative lookup below cannot resolve).
 *   3. relative from the extension source (development / project-local install)
 */
export function findMwPy(): string | null {
	const envPath = process.env.MW_PY;
	if (envPath && fs.existsSync(envPath)) return envPath;

	try {
		const rec = path.join(globalExtDir(), ".mw-py-path");
		if (fs.existsSync(rec)) {
			const recorded = fs.readFileSync(rec, "utf8").trim();
			if (recorded && fs.existsSync(recorded)) return recorded;
		}
	} catch {
		// Unreadable sidecar — fall through to the repo-relative lookup
	}

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

/**
 * Rebuild the extension bundle and reinstall it globally via `mw.py build --install`.
 * Bash-free and cwd-independent (mw.py derives all paths from its own location),
 * so this works from any pi window. The new bundle loads on the next pi start.
 */
export function buildMw(): { ok: true; output: string } | { ok: false; error: string } {
	const mwPy = findMwPy();
	if (!mwPy) return { ok: false, error: "Could not find mw.py — set MW_PY env var." };

	const result = spawnSync(PYTHON_EXE, [mwPy, "build", "--install"], {
		encoding: "utf8",
		timeout: 120_000,
	});
	if (result.error) {
		return { ok: false, error: `Failed to spawn mw.py: ${result.error.message}` };
	}
	if (result.status !== 0) {
		const stderr = result.stderr?.trim();
		return { ok: false, error: stderr || `mw build exited with code ${result.status}` };
	}
	return { ok: true, output: (result.stdout || "").trim() };
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
 * Wait for mw to be running by polling getMwStatus.
 * Call this after startMw() to confirm the service is actually up before the
 * agent's first turn.
 *
 * Stability window (mw-dispatch-reliability D-006): the PID file must stay
 * alive for `stableMs` after first sight before this reports started. mw serve
 * can die right after startup (e.g. route precheck failure) — the old
 * "PID file appeared" check reported a false "started" in that window.
 *
 * Returns true if mw is confirmed running within `timeoutMs`, false otherwise.
 */
export async function waitForMwStart(projectDir: string, timeoutMs = 8000, stableMs = 3000): Promise<boolean> {
	return waitForStart(() => getMwStatus(projectDir), timeoutMs, stableMs);
}

/**
 * Testable core of waitForMwStart: poll an injected status function until it
 * has been continuously `running` for `stableMs` (or the timeout elapses).
 * On timeout the instantaneous state decides — a service alive but observed
 * for less than the stable window still counts as started.
 */
export async function waitForStart(
	statusFn: () => { running: boolean },
	timeoutMs: number,
	stableMs: number,
	pollMs = 250,
): Promise<boolean> {
	const deadline = Date.now() + timeoutMs;
	let stableSince: number | null = null;
	while (Date.now() < deadline) {
		if (statusFn().running) {
			if (stableSince === null) stableSince = Date.now();
			if (Date.now() - stableSince >= stableMs) return true;
		} else {
			stableSince = null;
		}
		await new Promise<void>((resolve) => setTimeout(resolve, pollMs));
	}
	return statusFn().running;
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

// ── mw doctor (mw-dispatch-reliability D-005) ──────────────────────────────

/** Minimal typed view of `mw.py doctor --json` output used by /mw doctor. */
export interface DoctorJson {
	service?: { running?: boolean; pid?: number | null; pid_file?: string };
	proxy?: Array<{ route?: string; port?: number; listening?: boolean }>;
	orphan_proxy?: { detected?: boolean; ports?: Array<{ port?: number; owner_pids?: number[] }> };
	launcher_log?: { exists?: boolean; tail?: string[]; error_count?: number; fatal?: boolean };
	queue?: {
		non_terminal?: Array<{ task_key?: string; status?: string; cli?: string; task_md_exists?: boolean }>;
		stale_count?: number;
		archived_total?: number;
	};
	credentials?: {
		routes?: Array<{
			route?: string;
			available?: boolean;
			source?: { kind?: string; name?: string; path?: string };
			missing?: string | null;
		}>;
		all_missing?: boolean;
	};
	bundle?: {
		available?: boolean;
		stale?: boolean | null;
		global_bundle_mtime?: string;
		source_newest_mtime?: string;
		note?: string;
	};
	fix?: { applied?: unknown };
	summary?: { healthy?: boolean; issues?: unknown; suggestions?: unknown };
}

export type DoctorMwResult = { ok: true; report: DoctorJson } | { ok: false; error: string };

/**
 * Run `mw.py doctor --project=<dir> --json` (single source of diagnostics —
 * the TS side never re-implements checks). `fix` adds --fix first.
 */
export function doctorMw(projectDir: string, fix = false): DoctorMwResult {
	const mwPy = findMwPy();
	if (!mwPy) return { ok: false, error: "Could not find mw.py — set MW_PY env var." };

	const args = [mwPy, "doctor", `--project=${projectDir}`, "--json"];
	if (fix) args.push("--fix");
	const result = spawnSync(PYTHON_EXE, args, { encoding: "utf8", timeout: 15_000 });
	if (result.error) {
		return { ok: false, error: `Failed to spawn mw.py: ${result.error.message}` };
	}
	if (!result.stdout || !result.stdout.trim()) {
		// doctor exits 1 on issues but still prints JSON; empty stdout = real failure
		const stderr = result.stderr?.trim() ?? "";
		return { ok: false, error: stderr || `mw doctor exited with code ${result.status}` };
	}
	try {
		return { ok: true, report: JSON.parse(result.stdout) as DoctorJson };
	} catch (err) {
		return { ok: false, error: `mw doctor returned non-JSON output: ${String(err)}` };
	}
}
