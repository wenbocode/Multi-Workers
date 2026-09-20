/**
 * mw-worker-tree-kill live test (AC-006, VC-006): a watchdog-killed worker
 * must take its tracked child trees — grandchildren included — down with it.
 *
 * No mocks: real processes, real trackDetachedChildPid, real
 * killTrackedDetachedChildren → real taskkill /T /F (win32) or kill(-pgid)
 * (POSIX). Two independent tracked sleepers are spawned (per-pid coverage);
 * the first one spawns a grandchild that parks its pid in a file so the test
 * can prove the tree, not just the direct child, dies.
 *
 * 2026-09-19 incident replay, mechanism-level: the orphaned probe was
 * worker → WindowsApps python.exe shim → pythoncore-3.14, 151 GB WS after
 * 50 minutes. Here: worker (this process) → node sleeper → node grandchild.
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { killProcessTree, trackDetachedChildPid, untrackDetachedChildPid } from "../../src/utils/shell.ts";

const GRANDCHILD_SCRIPT =
	"require('fs').writeFileSync(process.argv[1], String(process.pid)); setInterval(() => {}, 40000);";
const PARENT_TREE_SCRIPT =
	"const cp = require('child_process'); cp.spawn(process.execPath, ['-e', process.argv[1], process.argv[2]], { stdio: 'ignore' }); setInterval(() => {}, 40000);";
const SLEEPER_SCRIPT = "setInterval(() => {}, 40000);";

function alive(pid: number): boolean {
	try {
		process.kill(pid, 0);
		return true;
	} catch {
		return false;
	}
}

async function waitFor(cond: () => boolean, deadlineMs = 15_000, stepMs = 100): Promise<boolean> {
	const start = Date.now();
	while (Date.now() - start < deadlineMs) {
		if (cond()) return true;
		await new Promise((r) => setTimeout(r, stepMs));
	}
	return cond();
}

function fakeWorkerPi(): { pi: ExtensionAPI; emit: (name: string, payload?: unknown) => void } {
	const handlers = new Map<string, Array<(e: unknown) => void>>();
	const pi = {
		on: (name: string, cb: (e: unknown) => void) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: () => {},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name: string, payload?: unknown) => {
			for (const cb of handlers.get(name) ?? []) cb(payload);
		},
	};
}

describe("worker exit tree-kill live (workerModeActivate)", () => {
	it(
		"AC-006: idle-killed worker reaps every tracked child tree, grandchildren included",
		{ timeout: 120_000 },
		async () => {
			const root = fs.mkdtempSync(path.join(os.tmpdir(), "atl-tree-kill-live-"));
			const pidFile = path.join(root, "grandchild.pid");
			// Mirror the bash tool's spawn semantics (bash.ts): detached on
			// POSIX (group leader → kill(-pid) reaps the group), plain child on
			// Windows (taskkill /T walks the parentage tree).
			const spawnOpts = {
				detached: process.platform !== "win32",
				stdio: "ignore" as const,
				windowsHide: true,
			};
			const parentTree = spawn(process.execPath, ["-e", PARENT_TREE_SCRIPT, GRANDCHILD_SCRIPT, pidFile], spawnOpts);
			const sleeper = spawn(process.execPath, ["-e", SLEEPER_SCRIPT], spawnOpts);
			expect(parentTree.pid).toBeTruthy();
			expect(sleeper.pid).toBeTruthy();
			const treePid = parentTree.pid!;
			const sleeperPid = sleeper.pid!;
			trackDetachedChildPid(treePid);
			trackDetachedChildPid(sleeperPid);

			const taskDir = path.join(root, "key-a", "workers", "t-live");
			fs.mkdirSync(taskDir, { recursive: true });
			fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
			process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
			process.env.PI_WORKER_IDLE_MS = "60000";

			const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
			try {
				// Grandchild must be up (pid parked) before the kill fires.
				const grandchildReady = await waitFor(() => fs.existsSync(pidFile), 15_000);
				expect(grandchildReady).toBe(true);
				const grandchildPid = Number.parseInt(fs.readFileSync(pidFile, "utf8"), 10);
				expect(Number.isFinite(grandchildPid)).toBe(true);
				expect(alive(treePid)).toBe(true);
				expect(alive(sleeperPid)).toBe(true);
				expect(alive(grandchildPid)).toBe(true);

				// Fire the idle watchdog: 60s of no activity under fake timers →
				// timeoutExit → real killTrackedDetachedChildren.
				vi.useFakeTimers();
				const { pi } = fakeWorkerPi();
				await workerModeActivate(pi);
				vi.advanceTimersByTime(60_000);
				vi.useRealTimers();
				expect(exitSpy).toHaveBeenCalledWith(1);

				// [VERIFY] VC-006: every tracked tree — and the grandchild — is
				// gone within 60s of the worker's exit.
				const reaped = await waitFor(
					() => !alive(treePid) && !alive(sleeperPid) && !alive(grandchildPid),
					60_000,
					200,
				);
				expect(reaped).toBe(true);
				expect(alive(treePid)).toBe(false);
				expect(alive(sleeperPid)).toBe(false);
				expect(alive(grandchildPid)).toBe(false);

				const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
				expect(trace).toContain("[TIMEOUT]");
				expect(trace).toContain("idle: no activity for 60s");
			} finally {
				// Never leak the fixtures, whatever happened above.
				killProcessTree(treePid);
				killProcessTree(sleeperPid);
				untrackDetachedChildPid(treePid);
				untrackDetachedChildPid(sleeperPid);
				vi.useRealTimers();
				exitSpy.mockRestore();
				delete process.env.PI_WORKER_TASK;
				delete process.env.PI_WORKER_IDLE_MS;
				fs.rmSync(root, { recursive: true, force: true });
			}
		},
	);
});
