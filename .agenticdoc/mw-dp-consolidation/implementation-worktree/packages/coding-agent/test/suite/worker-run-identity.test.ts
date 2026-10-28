/**
 * worker-run-identity.test.ts — T-20 (AC-022/D-022/R15): the worker writes its
 * own run record.
 *
 * The dispatcher can only trust `run.json` if the process that owns the task is
 * the one writing it: `running` at start, terminal on every exit path, a
 * heartbeat stamp while alive. It must also never let that bookkeeping get in
 * the way of the actual deliverable (R15) or displace an agent-written
 * machine-readable first line in output.md (D-117/VERDICT contract).
 *
 * Drives `workerModeActivate` directly against a fake ExtensionAPI (the
 * worker-idle-heartbeat.test.ts precedent). No provider API is touched.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { readRunState, runPath } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

class FakeWorkerPi {
	readonly handlers = new Map<string, Array<(event: unknown, ctx?: unknown) => void>>();
	readonly sent: Array<{ text: string; options?: { deliverAs?: string } }> = [];

	on(name: string, cb: (event: unknown, ctx?: unknown) => void): void {
		const list = this.handlers.get(name) ?? [];
		list.push(cb);
		this.handlers.set(name, list);
	}

	sendUserMessage(text: string, options?: { deliverAs?: string }): void {
		this.sent.push({ text, options });
	}

	emit(name: string, payload?: unknown, ctx?: unknown): void {
		for (const cb of this.handlers.get(name) ?? []) cb(payload, ctx);
	}
}

const savedEnv = new Map<string, string | undefined>();
const tempDirs: string[] = [];

function setEnv(name: string, value: string): void {
	if (!savedEnv.has(name)) savedEnv.set(name, process.env[name]);
	process.env[name] = value;
}

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mw-run-identity-"));
	tempDirs.push(dir);
	return dir;
}

/** `.agenticdoc`-shaped root + `key-a/workers/<taskKey>/task.md`, with
 * PI_WORKER_TASK pointed at it. */
function makeWorkerTask(root: string, taskKey: string, body = "type: coding\n\nwork\n"): string {
	const taskDir = path.join(root, "key-a", "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), body, "utf8");
	setEnv("PI_WORKER_TASK", path.join(taskDir, "task.md"));
	return taskDir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
	for (const [name, value] of savedEnv) {
		if (value === undefined) delete process.env[name];
		else process.env[name] = value;
	}
	savedEnv.clear();
	vi.restoreAllMocks();
});

describe("worker run identity (T-20, AC-022)", () => {
	it("records `running` with its own identity before the first turn", async () => {
		const root = mkdtemp();
		const taskDir = makeWorkerTask(root, "t-1");
		const pi = new FakeWorkerPi();

		await workerModeActivate(pi as unknown as ExtensionAPI);

		const state = readRunState(taskDir);
		expect(state?.schema).toBe(1);
		expect(state?.task_key).toBe("t-1");
		expect(state?.owner_key).toBe("key-a");
		expect(state?.kind).toBe("coding");
		expect(state?.status).toBe("running");
		expect(state?.run_id).toMatch(/^t-1@/);
		expect(state?.started_at).toBeTruthy();
		expect(state?.pid).toBe(process.pid);
		expect(state?.last_heartbeat_at).toBeTruthy();
		expect(state?.ended_at).toBeUndefined();
		expect(fs.existsSync(`${runPath(taskDir)}.tmp`)).toBe(false);
	});

	it("writes the terminal state and the run marker on a clean settle", async () => {
		const root = mkdtemp();
		const taskDir = makeWorkerTask(root, "t-1");
		const pi = new FakeWorkerPi();
		await workerModeActivate(pi as unknown as ExtensionAPI);

		pi.emit("agent_settled");

		const state = readRunState(taskDir);
		expect(state?.status).toBe("done");
		expect(state?.exit).toBe(0);
		expect(state?.ended_at).toBeTruthy();
		expect(state?.artifacts).toContain("output.md");

		const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
		expect(output.startsWith(`<!-- mw-run: ${state?.run_id} status=done -->`)).toBe(true);
	});

	it("keeps an agent-written machine-readable first line in place (D-117)", async () => {
		const root = mkdtemp();
		const taskDir = makeWorkerTask(root, "t-1");
		// The task template told the agent to write VERDICT=/TASKS= first.
		fs.writeFileSync(
			path.join(taskDir, "output.md"),
			"VERDICT=pass TASKS=2/2\n\n## Report\n\nfound no blockers\n",
			"utf8",
		);
		const pi = new FakeWorkerPi();
		await workerModeActivate(pi as unknown as ExtensionAPI);

		pi.emit("agent_settled");

		const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
		expect(output.split("\n")[0]).toBe("VERDICT=pass TASKS=2/2");
		expect(output).toContain("<!-- mw-run: ");
		expect(output.indexOf("<!-- mw-run: ")).toBeGreaterThan(output.indexOf("---"));
	});

	it("carries the supersedes header into the record (D-023)", async () => {
		const root = mkdtemp();
		const taskDir = makeWorkerTask(root, "t-2", "type: coding\nsupersedes: t-1\n\nwork\n");
		const pi = new FakeWorkerPi();

		await workerModeActivate(pi as unknown as ExtensionAPI);

		expect(readRunState(taskDir)?.supersedes).toBe("t-1");
	});

	it("records a startup refusal as a terminal failure (never restartable)", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation((() => undefined) as never);
		const taskDir = makeWorkerTask(root, "t-1", "origin: conductor\ntype: fallback\n\nwork\n");
		const pi = new FakeWorkerPi();

		await workerModeActivate(pi as unknown as ExtensionAPI);

		const state = readRunState(taskDir);
		expect(state?.status).toBe("failed");
		expect(state?.exit).toBe(1);
		expect(state?.ended_at).toBeTruthy();
		expect(exitSpy).toHaveBeenCalledWith(1);
	});

	it("still writes output.md when the run record cannot be written (R15)", async () => {
		const root = mkdtemp();
		const taskDir = makeWorkerTask(root, "t-1");
		// A directory in the run.json slot makes every record swap fail.
		fs.mkdirSync(path.join(taskDir, "run.json"), { recursive: true });
		const pi = new FakeWorkerPi();

		await workerModeActivate(pi as unknown as ExtensionAPI);
		pi.emit("agent_settled");

		expect(fs.existsSync(path.join(taskDir, "output.md"))).toBe(true);
		expect(fs.readFileSync(path.join(taskDir, "trace.log"), "utf8")).toContain("[RUN] run.json write failed");
	});
});
