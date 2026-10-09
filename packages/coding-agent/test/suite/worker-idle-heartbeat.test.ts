/**
 * worker-idle-heartbeat.test.ts — T-04 (AC-005, VC-004/005/006): the worker
 * idle watchdog must (a) not kill a worker whose long-running bash call is
 * legitimately silent, (b) still kill a genuinely hung worker, and (c) emit
 * structured `[IDLE_KILL]` evidence before any idle kill.
 *
 * Measured root cause (2026-09-26): 22/24 idle kills died while a bash call was
 * in flight with zero `tool_execution_update` — bash updates are output-driven
 * (core/tools/bash.ts), so a silent long command looked dead. The fix is a
 * heartbeat plus an in-flight classification, not a bigger threshold:
 *   - bash emits a 30s no-op progress update while running (worker sessions
 *     only), mirroring rag/budget.ts `withHeartbeat`;
 *   - while a tool is in flight the watchdog judges the TOOL-idle clock against
 *     `toolIdleMs` (>= 30m) instead of raw idle, so a hung tool still dies;
 *   - the no-in-flight branch keeps the existing raw-idle judgement plus a
 *     token-delta second confirmation.
 *
 * These tests drive `workerModeActivate` directly against a fake ExtensionAPI
 * (the rag-e2e-slow.test.ts precedent in this suite) so the watchdog timing is
 * deterministic under fake timers. No provider API is touched.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionContext } from "../../src/core/extensions/types.ts";
import { createBashToolDefinition } from "../../src/core/tools/bash.ts";
import {
	DEFAULT_TOOL_IDLE_MS,
	resolveToolIdleMs,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const IDLE_MS = 60_000;
/** 2h wall budget: the wall must not win before the 30m tool-idle bound. */
const WALL_MS = 2 * 60 * 60_000;
const TOOL_IDLE_MS = resolveToolIdleMs(IDLE_MS);

class FakeWorkerPi {
	readonly handlers = new Map<string, Array<(event: unknown) => void>>();
	readonly sent: Array<{ text: string; options?: { deliverAs?: string } }> = [];

	on(name: string, cb: (event: unknown) => void): void {
		const list = this.handlers.get(name) ?? [];
		list.push(cb);
		this.handlers.set(name, list);
	}

	sendUserMessage(text: string, options?: { deliverAs?: string }): void {
		this.sent.push({ text, options });
	}

	emit(name: string, payload?: unknown): void {
		for (const cb of this.handlers.get(name) ?? []) cb(payload);
	}
}

const savedEnv = new Map<string, string | undefined>();
const tempDirs: string[] = [];

function setEnv(name: string, value: string): void {
	if (!savedEnv.has(name)) savedEnv.set(name, process.env[name]);
	process.env[name] = value;
}

function clearEnv(name: string): void {
	if (!savedEnv.has(name)) savedEnv.set(name, process.env[name]);
	delete process.env[name];
}

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "idle-heartbeat-"));
	tempDirs.push(dir);
	return dir;
}

/** Create root/key-a/workers/<taskKey>/task.md and point PI_WORKER_TASK/
 * PI_WORKER_IDLE_MS/PI_WORKER_TIMEOUT_MS at it (the watchdog test pattern). */
function makeWorkerTask(root: string, taskKey: string): { taskDir: string; taskPath: string } {
	const taskDir = path.join(root, "key-a", "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	const taskPath = path.join(taskDir, "task.md");
	fs.writeFileSync(taskPath, "type: coding\n\nwork\n", "utf8");
	setEnv("PI_WORKER_TASK", taskPath);
	setEnv("PI_WORKER_IDLE_MS", String(IDLE_MS));
	setEnv("PI_WORKER_TIMEOUT_MS", String(WALL_MS));
	return { taskDir, taskPath };
}

function idleKillLine(taskDir: string): string | undefined {
	const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
	return trace.split(/\r?\n/).find((line) => line.startsWith("[IDLE_KILL]"));
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	for (const [name, value] of savedEnv) {
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
	savedEnv.clear();
	vi.restoreAllMocks();
	vi.useRealTimers();
});

describe("worker idle watchdog: in-flight classification + heartbeat + evidence (T-04)", () => {
	it("VC-005: a real bash heartbeat keeps a silent long command alive past toolIdleMs", async () => {
		vi.useFakeTimers();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation((() => undefined) as never);
		const root = mkdtemp();
		const { taskDir } = makeWorkerTask(root, "t-alive");
		let resolveExec: ((value: { exitCode: number | null }) => void) | undefined;
		const bash = createBashToolDefinition(root, {
			operations: {
				exec: () =>
					new Promise<{ exitCode: number | null }>((resolve) => {
						resolveExec = resolve;
					}),
			},
			exposeSessionEnvironment: false,
		});
		const pi = new FakeWorkerPi();
		await workerModeActivate(pi as unknown as ExtensionAPI);

		// The host emits tool_execution_start; bash itself emits the heartbeats
		// through onUpdate, which the host forwards as tool_execution_update.
		const callId = "call-bash-silent";
		pi.emit("tool_execution_start", {
			type: "tool_execution_start",
			toolCallId: callId,
			toolName: "bash",
			args: { command: "silent-long-command" },
		});
		let updates = 0;
		const execPromise = bash.execute(
			callId,
			{ command: "silent-long-command" },
			undefined,
			() => {
				updates += 1;
				pi.emit("tool_execution_update", {
					type: "tool_execution_update",
					toolCallId: callId,
					toolName: "bash",
					args: { command: "silent-long-command" },
					partialResult: {},
				});
			},
			{} as ExtensionContext,
		);
		const updatesAfterStart = updates;

		// Run well past BOTH the raw idle threshold and the tool-idle bound with
		// zero output. Without the heartbeat this would be an idle kill.
		expect(TOOL_IDLE_MS).toBeGreaterThan(IDLE_MS);
		for (let tick = 0; tick < Math.ceil((TOOL_IDLE_MS + 60_000) / 30_000); tick++) {
			vi.advanceTimersByTime(30_000);
		}

		expect(exitSpy).not.toHaveBeenCalled();
		expect(updates).toBeGreaterThan(updatesAfterStart);
		const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
		expect(trace).not.toContain("[IDLE_KILL]");
		expect(trace).not.toContain("[TIMEOUT]");

		resolveExec?.({ exitCode: 0 });
		await execPromise;
	});

	it("VC-006: no in-flight tool and no token delta is still killed, with complete [IDLE_KILL] evidence", async () => {
		vi.useFakeTimers();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation((() => undefined) as never);
		const root = mkdtemp();
		const { taskDir } = makeWorkerTask(root, "t-hang");
		const pi = new FakeWorkerPi();
		await workerModeActivate(pi as unknown as ExtensionAPI);

		// No lifecycle events at all: the 60s tick must kill.
		vi.advanceTimersByTime(IDLE_MS);
		expect(exitSpy).toHaveBeenCalledWith(1);
		expect(exitSpy).toHaveBeenCalledTimes(1);

		const line = idleKillLine(taskDir);
		expect(line, "an idle kill must carry [IDLE_KILL] evidence").toBeDefined();
		// VC-004 field contract: in-flight tool, its running seconds, the threshold
		// used, and the last-activity source.
		expect(line).toContain("tool_in_flight=none");
		expect(line).toContain("tool_run_s=-");
		expect(line).toContain("tool_idle_s=-");
		expect(line).toContain("silence_s=60");
		expect(line).toContain("threshold_s=60");
		expect(line).toContain("threshold_kind=idle");
		expect(line).toMatch(/last_activity=\S+/);

		const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
		expect(trace).toContain("idle: no activity for 60s");
		expect(trace).toContain("[TIMEOUT]");
	});

	it("VC-006: a hung in-flight tool is still killed at the tool-idle bound, with [IDLE_KILL] evidence", async () => {
		vi.useFakeTimers();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation((() => undefined) as never);
		const root = mkdtemp();
		const { taskDir } = makeWorkerTask(root, "t-hung-tool");
		const pi = new FakeWorkerPi();
		await workerModeActivate(pi as unknown as ExtensionAPI);

		// A tool that starts and never reports again: no update, no end. Raw idle
		// would have killed it at 60s; the classification defers to the (lower)
		// tool-idle clock, which must stay the outer bound.
		const callId = "call-hung";
		pi.emit("tool_execution_start", {
			type: "tool_execution_start",
			toolCallId: callId,
			toolName: "bash",
			args: { command: "hung" },
		});
		vi.advanceTimersByTime(TOOL_IDLE_MS + 30_000);
		expect(exitSpy).toHaveBeenCalledWith(1);

		const line = idleKillLine(taskDir);
		expect(line, "the bounded in-flight kill must carry [IDLE_KILL] evidence").toBeDefined();
		expect(line).toContain("tool_in_flight=bash");
		expect(line).toMatch(/tool_run_s=\d+/);
		expect(line).toMatch(/tool_idle_s=\d+/);
		expect(line).toContain(`threshold_s=${TOOL_IDLE_MS / 1000}`);
		expect(line).toContain("threshold_kind=tool_idle");
		expect(line).toContain("last_activity=tool_start");
	});

	it("bash heartbeat is worker-session only: interactive runs get no extra updates", async () => {
		vi.useFakeTimers();
		clearEnv("PI_WORKER_TASK");
		const root = mkdtemp();
		let resolveExec: ((value: { exitCode: number | null }) => void) | undefined;
		const bash = createBashToolDefinition(root, {
			operations: {
				exec: () =>
					new Promise<{ exitCode: number | null }>((resolve) => {
						resolveExec = resolve;
					}),
			},
			exposeSessionEnvironment: false,
		});
		let updates = 0;
		const execPromise = bash.execute(
			"call-interactive",
			{ command: "silent" },
			undefined,
			() => {
				updates += 1;
			},
			{} as ExtensionContext,
		);
		expect(updates).toBe(1); // the initial empty update only
		vi.advanceTimersByTime(2 * 60_000);
		expect(updates).toBe(1);
		resolveExec?.({ exitCode: 0 });
		await execPromise;
	});

	it("toolIdleMs bound is the 30m floor or the configured idle threshold, whichever is larger", () => {
		expect(DEFAULT_TOOL_IDLE_MS).toBe(30 * 60_000);
		expect(resolveToolIdleMs(60_000)).toBe(DEFAULT_TOOL_IDLE_MS);
		expect(resolveToolIdleMs(60 * 60_000)).toBe(60 * 60_000);
	});
});
