/**
 * mw-worker-tree-kill (AC-001~005): worker exit paths must kill the bash
 * tool's tracked child trees before process.exit(1).
 *
 * 2026-09-19 incident: an idle-killed worker's in-flight `python probe2.py`
 * (bash tool child) survived the parent on Windows and spun to 151 GB WS.
 * Root cause: print-mode only kills tracked children from SIGTERM/SIGHUP
 * handlers; worker-mode's watchdog called process.exit(1) directly, dropping
 * the tracked-pid set on the floor.
 *
 * Observation seam: killTrackedDetachedChildren is mocked at the module
 * export (worker-mode imports it cross-module, so the vi.mock factory always
 * intercepts). Mocking killProcessTree instead would NOT work: the real
 * killTrackedDetachedChildren calls it through the module-internal closure
 * binding, which a factory mock of the export table cannot observe.
 * Per-pid coverage and the real taskkill/kill are proven by the companion
 * live test (agent-team-loop-worker-tree-kill-live.test.ts).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { writePhaseFile } from "../../src/extensions/agent-team-loop/worker/phase-runner.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";
import { killTrackedDetachedChildren } from "../../src/utils/shell.ts";

vi.mock("../../src/utils/shell.ts", async (importOriginal) => {
	const actual = await importOriginal<typeof import("../../src/utils/shell.ts")>();
	return { ...actual, killTrackedDetachedChildren: vi.fn() };
});

vi.mock("../../src/extensions/agent-team-loop/worker/phase-runner.ts", async (importOriginal) => {
	const actual = await importOriginal<typeof import("../../src/extensions/agent-team-loop/worker/phase-runner.ts")>();
	return { ...actual, writePhaseFile: vi.fn() };
});

const killMock = vi.mocked(killTrackedDetachedChildren);

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "atl-tree-kill-"));
}

function fakeWorkerPi(): {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	sent: Array<{ text: string; options?: { deliverAs?: string } }>;
} {
	const handlers = new Map<string, Array<(e: unknown) => void>>();
	const sent: Array<{ text: string; options?: { deliverAs?: string } }> = [];
	const pi = {
		on: (name: string, cb: (e: unknown) => void) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: (text: string, options?: { deliverAs?: string }) => {
			sent.push({ text, options });
		},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name: string, payload?: unknown) => {
			for (const cb of handlers.get(name) ?? []) cb(payload);
		},
		sent,
	};
}

/** Activate the worker loop against a task.md at root/{key}/workers/{task}.
 * PI_WORKER_IDLE_MS is always shortened to 60s so the interval logic is
 * reachable in-test (same pattern as the watchdog suite in
 * agent-team-loop.test.ts). */
async function startTask(root: string, taskKey: string, body: string): Promise<ReturnType<typeof fakeWorkerPi>> {
	const taskDir = path.join(root, "key-a", "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), body, "utf8");
	const { pi, emit, sent } = fakeWorkerPi();
	process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
	process.env.PI_WORKER_IDLE_MS = "60000";
	await workerModeActivate(pi);
	return { pi, emit, sent };
}

/** invocationCallOrder comparison: every recorded kill call happened before
 * the (single) exit call.
 *
 * "exactly once" holds because process.exit is mocked, so the 'exit' hook
 * never fires; in a real run the hook fires a second, by-design no-op call
 * after the explicit one already cleared the tracked-Set (shell.ts).
 * That idempotent double-fire path itself is untested here — the live test
 * covers the real exit sequence end to end. */
function expectKillBeforeExit(exitSpy: ReturnType<typeof vi.spyOn>): void {
	expect(killMock).toHaveBeenCalledTimes(1);
	expect(exitSpy).toHaveBeenCalledTimes(1);
	const killOrder = killMock.mock.invocationCallOrder[0];
	const exitOrder = exitSpy.mock.invocationCallOrder[0];
	expect(killOrder).toBeDefined();
	expect(exitOrder).toBeDefined();
	expect(killOrder!).toBeLessThan(exitOrder!);
}

describe("worker exit tree-kill (workerModeActivate)", () => {
	let exitSpy: ReturnType<typeof vi.spyOn>;

	beforeEach(() => {
		killMock.mockReset();
		vi.mocked(writePhaseFile).mockReset();
	});

	it("AC-001: idle watchdog kill fires killTrackedDetachedChildren exactly once, before process.exit(1)", async () => {
		const root = mkdtemp();
		exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			await startTask(root, "t-idle", "type: coding\n\nwork\n");
			// No lifecycle events: ticks at 30s (below threshold) and 60s
			// (idleFor=60s >= 60s) — the 60s tick must kill.
			vi.advanceTimersByTime(60_000);
			expect(exitSpy).toHaveBeenCalledWith(1);
			expectKillBeforeExit(exitSpy);
			// Writes happened before the kill (same synchronous block; content check):
			const taskDir = path.join(root, "key-a", "workers", "t-idle");
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toContain("[TIMEOUT]");
			expect(trace).toContain("idle: no activity for 60s");
			expect(trace).toContain("[END] ");
			expect(trace).toContain("exit=1");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("idle timeout: no activity for 60s");
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-002: wall budget kill shares the same kill-before-exit ordering", async () => {
		const root = mkdtemp();
		exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			// budget 2m: steerAt = 120s - min(5m, 30s) = 90s, checkpoint anchor
			// = min(30m, 60s) = 60s, wall = 120s. Activity trickles every 15s so
			// the idle watchdog stays out of the way.
			const { emit } = await startTask(root, "t-wall", "type: coding\ntimeout: 2\n\nwork\n");
			for (let t = 0; t < 8; t++) {
				vi.advanceTimersByTime(15_000);
				emit("message_update");
			}
			expect(exitSpy).toHaveBeenCalledWith(1);
			expectKillBeforeExit(exitSpy);
			const taskDir = path.join(root, "key-a", "workers", "t-wall");
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toContain("wall: budget 120s exceeded");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("wall timeout: budget 120s exceeded");
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-003: agent_settled handler exception kills tracked children before exit", async () => {
		const root = mkdtemp();
		exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		try {
			const { emit, sent } = await startTask(
				root,
				"t-catch",
				"type: coding\n\n- name: build\n  prompt: |\n    do build\n",
			);
			// First settle dispatches phase 1 (no write of phase output yet).
			emit("agent_settled");
			expect(sent[0]?.text).toContain("do build");
			expect(exitSpy).not.toHaveBeenCalled();
			// Second settle writes the phase file — make it blow up so the
			// catch path (recordEnd → kill → process.exit(1)) runs.
			vi.mocked(writePhaseFile).mockImplementation(() => {
				throw new Error("phase write boom");
			});
			emit("agent_settled");
			expect(exitSpy).toHaveBeenCalledWith(1);
			expectKillBeforeExit(exitSpy);
			const taskDir = path.join(root, "key-a", "workers", "t-catch");
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toContain("phase write boom");
			expect(trace).toContain("exit=1");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("Task failed during output writing.");
		} finally {
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-004: the process 'exit' safety-net hook also kills tracked children (hard-crash backstop)", async () => {
		const root = mkdtemp();
		try {
			// Capture the listener delta so accumulated hooks from earlier
			// workerModeActivate calls (this file never removes them — same as
			// the existing watchdog suite) stay out of the assertion.
			const before = process.listenerCount("exit");
			await startTask(root, "t-hook", "type: coding\n\nwork\n");
			const added = process.listeners("exit").slice(before);
			expect(added.length).toBeGreaterThanOrEqual(1);
			// Simulate a hard crash: run the registered hook directly instead of
			// process.emit("exit") (which would also fire every accumulated
			// listener and pollute counts).
			for (const hook of added) (hook as (code: number) => void)(1);
			expect(killMock).toHaveBeenCalledTimes(1);
			// The hook's other duty is unchanged: fallback output on paths that
			// never wrote one.
			const taskDir = path.join(root, "key-a", "workers", "t-hook");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("(worker exited without writing output)");
		} finally {
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-005: successful settle never kills and never exits", async () => {
		const root = mkdtemp();
		exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		try {
			const { emit } = await startTask(root, "t-ok", "type: coding\n\nwork\n");
			emit("agent_end", { messages: [] });
			emit("agent_settled");
			expect(exitSpy).not.toHaveBeenCalled();
			expect(killMock).not.toHaveBeenCalled();
			const taskDir = path.join(root, "key-a", "workers", "t-ok");
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toContain("exit=0");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("Agent settled after 0 tool call(s).");
		} finally {
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("D-002 early exit: missing task file kills tracked children before exit", async () => {
		const root = mkdtemp();
		exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		try {
			// The env points at a task.md that is never created; the existsCheck
			// branch kills and exits before parseTaskMd, whose read failure is
			// what surfaces here (the mocked exit lets execution continue).
			const taskDir = path.join(root, "key-a", "workers", "t-missing");
			fs.mkdirSync(taskDir, { recursive: true });
			process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
			process.env.PI_WORKER_IDLE_MS = "60000";
			const { pi } = fakeWorkerPi();
			await expect(workerModeActivate(pi)).rejects.toThrow();
			expect(exitSpy).toHaveBeenCalledWith(1);
			expectKillBeforeExit(exitSpy);
		} finally {
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("D-002 early exit: startup refusal kills tracked children before exit", async () => {
		const root = mkdtemp();
		exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			// origin: conductor + unregistered type = fail-closed refusal
			// (D-107): output/log writes, kill, exit — before any agent turn.
			// The mocked exit lets activation continue (hook + fake timers),
			// which is harmless — the assertions below pin the refusal path.
			await startTask(root, "t-refused", "type: bogus-type\norigin: conductor\n\nwork\n");
			expect(exitSpy).toHaveBeenCalledWith(1);
			expectKillBeforeExit(exitSpy);
			const taskDir = path.join(root, "key-a", "workers", "t-refused");
			// The refusal reason lands in trace.log as an [ERROR] line (the
			// "[worker] refused" line is console-only); the start rows around it
			// prove the writes happened before the kill/exit.
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toContain("Fail-closed (D-107");
			expect(trace).toContain("type 'bogus-type'");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("Task refused at startup (fail-closed).");
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});
});
