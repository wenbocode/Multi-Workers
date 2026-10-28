/**
 * T-09 (mw-vision-role AC-011 / VC-011): worker-side image-capability backstop.
 *
 * A task that declared `images: yes` must not run its body when the resolved
 * runtime model cannot read images. The check lives in the sole event context
 * that exposes the model (`session_start`), refuses through the same failure
 * channel as the dispatch gate, and emits the machine line
 * `[IMAGE-CAP] model=<id> provider=<p> task=<key> declared=images:yes`.
 *
 * Observation seam for `worker.log`: `writeWorkerLogLine` writes to fd 1 with
 * `fs.writeSync`, so `vi.spyOn(fs, "writeSync")` is impossible (ESM namespace
 * is not configurable). The `node:fs` module is partially mocked instead —
 * every other export is the real one.
 *
 * `[VERIFY]` lines go straight to stdout via `process.stdout.write` (the suite
 * is `silent: "passed-only"`).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const { workerLog } = vi.hoisted(() => ({ workerLog: [] as string[] }));

vi.mock("node:fs", async (importOriginal) => {
	const actual = await importOriginal<typeof import("node:fs")>();
	const realWriteSync = actual.writeSync as (...args: unknown[]) => number;
	return {
		...actual,
		default: actual,
		writeSync: (fd: number, data: unknown, ...rest: unknown[]): number => {
			if (fd === 1 && typeof data === "string") workerLog.push(data);
			return realWriteSync(fd, data, ...rest);
		},
	};
});

function verify(line: string): void {
	process.stdout.write(`${line}\n`);
}

// Each activation registers a process 'exit' hook; one file may activate many.
process.setMaxListeners(50);

const tmpRoots: string[] = [];

function mkdtemp(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "atl-image-cap-"));
	tmpRoots.push(dir);
	return dir;
}

afterEach(() => {
	workerLog.length = 0;
	delete process.env.PI_WORKER_TASK;
	delete process.env.PI_WORKER_IDLE_MS;
	while (tmpRoots.length > 0) {
		const dir = tmpRoots.pop();
		if (dir) fs.rmSync(dir, { recursive: true, force: true });
	}
});

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown, ctx?: unknown) => void;
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(event: unknown, ctx: unknown) => void>>();
	const pi = {
		on: (name: string, cb: (event: unknown, ctx: unknown) => void) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: () => {},
		setActiveTools: () => {},
		registerTool: () => {},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name: string, payload?: unknown, ctx?: unknown) => {
			for (const cb of handlers.get(name) ?? []) cb(payload, ctx);
		},
	};
}

/** Activate the worker loop against root/{owner}/workers/{task}. */
async function startWorker(
	root: string,
	taskKey: string,
	body: string,
): Promise<{ worker: FakeWorker; taskDir: string }> {
	const taskDir = path.join(root, "key-a", "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), body, "utf8");
	process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
	process.env.PI_WORKER_IDLE_MS = "60000";
	const worker = fakeWorkerPi();
	await workerModeActivate(worker.pi);
	return { worker, taskDir };
}

function readIfExists(file: string): string | undefined {
	return fs.existsSync(file) ? fs.readFileSync(file, "utf8") : undefined;
}

const SESSION_START = { type: "session_start", reason: "startup" };
/** Text-only runtime model: no "image" in `input` → incapable. */
const TEXT_ONLY_CTX = { model: { id: "glm-5.3", provider: "timi", input: ["text"] } };
/** Image-capable model → the backstop must stay silent. */
const VISION_CTX = { model: { id: "gpt-5v", provider: "openai", input: ["text", "image"] } };

describe("worker image-capability backstop (VC-011)", () => {
	it("VC-011: `images: yes` + text-only runtime model refuses with [IMAGE-CAP] and exit(1)", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		try {
			const beforeHooks = process.listenerCount("exit");
			const { worker, taskDir } = await startWorker(root, "t-image-cap", "type: vision\nimages: yes\n\nwork\n");
			worker.emit("session_start", SESSION_START, TEXT_ONLY_CTX);

			expect(exitSpy).toHaveBeenCalledWith(1);
			const logged = workerLog.join("");
			expect(logged).toContain("[IMAGE-CAP]");
			expect(logged).toContain("model=glm-5.3");
			expect(logged).toContain("provider=timi");
			expect(logged).toContain("task=t-image-cap");
			expect(logged).toContain("declared=images:yes");

			const output = readIfExists(path.join(taskDir, "output.md"));
			expect(output).toBeDefined();
			expect(output).toContain("Task refused (image capability).");
			expect(output).toContain("[IMAGE-CAP] model=glm-5.3 provider=timi task=t-image-cap declared=images:yes");

			const trace = readIfExists(path.join(taskDir, "trace.log"));
			expect(trace).toContain("[IMAGE-CAP] model=glm-5.3 provider=timi task=t-image-cap declared=images:yes");

			// Real-run shape: process.exit(1) fires the registered 'exit' safety
			// net. It must NOT append its crash output over the refusal, which is
			// what `outputWritten = true` buys (process.exit is mocked in-test, so
			// the hook is invoked by hand).
			for (const hook of process.listeners("exit").slice(beforeHooks)) (hook as (code: number) => void)(1);
			const afterHook = readIfExists(path.join(taskDir, "output.md")) ?? "";
			expect(afterHook).toContain("Task refused (image capability).");
			expect(afterHook).not.toContain("(worker exited without writing output)");

			verify("[VERIFY] VC-011: image_cap_line=true exit=1 control_ok=true");
		} finally {
			exitSpy.mockRestore();
		}
	});

	it("VC-011 control: `images: yes` + image-capable model is untouched", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		try {
			const { worker, taskDir } = await startWorker(root, "t-image-ok", "type: vision\nimages: yes\n\nwork\n");
			worker.emit("session_start", SESSION_START, VISION_CTX);
			expect(exitSpy).not.toHaveBeenCalled();
			expect(workerLog.join("")).not.toContain("[IMAGE-CAP]");
			expect(fs.existsSync(path.join(taskDir, "output.md"))).toBe(false);
		} finally {
			exitSpy.mockRestore();
		}
	});

	it("VC-011 control: a task with no `images:` header is never affected", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		try {
			const { worker, taskDir } = await startWorker(root, "t-no-images", "type: coding\n\nwork\n");
			worker.emit("session_start", SESSION_START, TEXT_ONLY_CTX);
			expect(exitSpy).not.toHaveBeenCalled();
			expect(workerLog.join("")).not.toContain("[IMAGE-CAP]");
			expect(fs.existsSync(path.join(taskDir, "output.md"))).toBe(false);
		} finally {
			exitSpy.mockRestore();
		}
	});

	it("VC-011 fail-open: an undefined ctx.model records a trace note and never blocks", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		try {
			const { worker, taskDir } = await startWorker(root, "t-image-nomodel", "type: vision\nimages: yes\n\nwork\n");
			worker.emit("session_start", SESSION_START, { model: undefined });
			expect(exitSpy).not.toHaveBeenCalled();
			expect(workerLog.join("")).not.toContain("[IMAGE-CAP]");
			const trace = readIfExists(path.join(taskDir, "trace.log")) ?? "";
			expect(trace).toMatch(/\[IMAGE-CAP\] fail-open/);
			expect(fs.existsSync(path.join(taskDir, "output.md"))).toBe(false);
		} finally {
			exitSpy.mockRestore();
		}
	});
});
