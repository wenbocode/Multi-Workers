/**
 * Tests for the autopilot worker/TS protocol increment (goal-autopilot T-14,
 * design D-104/D-107/D-115/D-116, AC-021/VC-023).
 *
 * - dispatchNewTasks origin skip (D-104): conductor-origin task.md files are
 *   never queued or upserted, burn no docs-gate warning, and stay out of the
 *   re-insert-as-pending path a queue wipe (launcher restart / archived row)
 *   would otherwise open; unmarked tasks behave exactly as before (AC-012).
 * - Typed tool allowlists (D-107/VC-023): the 5 autopilot types resolve to
 *   per-type sets exactly equal to the Python REGISTRY
 *   (packages/multi-workers/autopilot/dispatch.py); an unregistered type on a
 *   conductor task fails closed (exit 1 + reason in output.md); the manual
 *   fallback to the full set stays (GC-8); a conductor verifier without a
 *   read_scope fails closed (D-106).
 * - [START] pid observation (D-115): one pure `[START] pid=<pid>` line per
 *   spawn, appended to trace.log (never reset), in exactly the format Python
 *   autopilot/state.py start_pids parses.
 * - agenticdocRoot semantic split (D-116): goalMtime/[GOAL_CHECK] use the
 *   TRUE .agenticdoc root (task.md four levels up) while outputDir keeps the
 *   workers-dir base (contract unchanged).
 *
 * No provider APIs, keys, or network: worker-mode is activated against a
 * fake ExtensionAPI (same pattern as test/suite/autopilot-read-scope.test.ts
 * and the watchdog integration tests in test/extensions/agent-team-loop.test.ts).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import { dispatchNewTasks } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import { goalMtime } from "../../src/extensions/agent-team-loop/worker/phase-runner.ts";
import { WORKER_FILE_TOOL } from "../../src/extensions/agent-team-loop/worker/worker-file-tool.ts";
import { parseTaskMd, workerModeActivate } from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "ap-proto-"));
}

// worker-mode registers a process-exit safety hook per activation; this file
// activates many workers in one process, tripping Node's listener-leak
// heuristic (>10 "exit" listeners). All hooks are intentional and harmless.
process.setMaxListeners(50);

/** Write a complete phase-doc set for a key: spec + design (>= 500 bytes), a
 * numbered AC, and one research note per phase — everything the dispatch
 * docs gate requires (no goal.md → the §0 check is skipped). Same fixture as
 * test/extensions/agent-team-loop.test.ts. */
function writePhaseDocs(root: string, key: string): void {
	const keyDir = path.join(root, key);
	fs.mkdirSync(keyDir, { recursive: true });
	fs.writeFileSync(
		path.join(keyDir, "spec.md"),
		`# Spec\n${"x".repeat(600)}\n\n| AC-001 | in x, y returns z |\n`,
		"utf8",
	);
	fs.writeFileSync(path.join(keyDir, "design.md"), `# Design\n${"x".repeat(600)}`, "utf8");
	const research = path.join(keyDir, "evidence", "research");
	fs.mkdirSync(research, { recursive: true });
	fs.writeFileSync(path.join(research, "spec-topic-2026-01-01.md"), "# research\n", "utf8");
	fs.writeFileSync(path.join(research, "design-topic-2026-01-01.md"), "# research\n", "utf8");
}

/** The pure `[START] pid=<pid>` line format Python state.py start_pids
 * counts spawns by (`^\[START\] pid=(\d+)\s*$`). */
const START_PID_RE = /^\[START\] pid=(\d+)$/;

// Mirrors of the Python-side REGISTRY tool sets (autopilot/dispatch.py:
// _CODING_TOOLS / _REVIEW_TOOLS and the roadmap-writer entry, entry order
// included). VC-023 locks the TS TOOL_ALLOWLISTS equal to this table; the
// T-17 L0 parity test locks the Python side against the same table.
const PY_CODING_TOOLS = ["read", "write", "edit", "bash", "find", "grep", "ls"];
const PY_REVIEW_TOOLS = ["read", "find", "grep", "ls"];
const PY_REGISTRY: Record<string, string[]> = {
	"roadmap-writer": ["read", "write", "edit", "find", "grep", "ls"],
	"phase-writer": PY_CODING_TOOLS,
	verifier: PY_REVIEW_TOOLS,
	reviewer: PY_REVIEW_TOOLS,
	repair: PY_CODING_TOOLS,
};

/** Render a conductor-shaped task.md (autopilot/dispatch.py render_task_md):
 * frontmatter labels + prompt body. `extra` lines slot in before the closing
 * fence (read_scope blocks, caps...). */
function conductorTaskMd(taskType: string, extra: string[] = []): string {
	return [
		"---",
		`type: ${taskType}`,
		"origin: conductor",
		"loop: l2:goal-ap:spec-to-design",
		"attempt: 1",
		...extra,
		"---",
		"",
		"Do the phase-gate work.",
		"",
	].join("\n");
}

// ── dispatchNewTasks origin skip (D-104) ─────────────────────────────────────

describe("dispatchNewTasks origin skip (D-104 / VC-023)", () => {
	it("VC-023/D-104: origin: conductor tasks are never queued or upserted; unmarked tasks dispatch unchanged (AC-012)", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		writePhaseDocs(root, "goal-ap");

		// Conductor dispatches (render_task_md shape), LF and CRLF variants.
		const c1 = path.join(root, "goal-ap", "workers", "ap-goal-ap-t99");
		fs.mkdirSync(c1, { recursive: true });
		fs.writeFileSync(
			path.join(c1, "task.md"),
			conductorTaskMd("verifier", ["read_scope:", "  - .agenticdoc/goal.md"]),
			"utf8",
		);
		const c2 = path.join(root, "goal-ap", "workers", "ap-goal-ap-crlf");
		fs.mkdirSync(c2, { recursive: true });
		// CRLF variant: a hand-edited conductor task.md on Windows must be
		// recognized too (the origin-line match is line-exact, \r-tolerant).
		fs.writeFileSync(path.join(c2, "task.md"), conductorTaskMd("reviewer").replaceAll("\n", "\r\n"), "utf8");
		// Unmarked manual task under the same owner.
		const manual = path.join(root, "goal-ap", "workers", "manual-task");
		fs.mkdirSync(manual, { recursive: true });
		fs.writeFileSync(path.join(manual, "task.md"), "type: coding\nmodel: test-model-1\n\nwork\n", "utf8");

		await dispatchNewTasks(store, root);

		expect(store.findByKey("ap-goal-ap-t99")).toBeUndefined();
		expect(store.findByKey("ap-goal-ap-crlf")).toBeUndefined();
		const entry = store.findByKey("manual-task");
		expect(entry?.status).toBe("pending");
		expect(entry?.cli).toBe("pi"); // route unchanged (AC-012)
		expect(entry?.provider).toBe("timi");
		expect(entry?.model).toBe("test-model-1"); // model: passthrough unchanged
		expect(entry?.taskPath).toBe(path.join(manual, "task.md"));

		// Launcher-restart shape: the queue file is wiped (rows archived/lost)
		// and the scan runs again. The manual task re-enters the queue exactly
		// as before (AC-012 zero regression); the conductor tasks must NOT be
		// re-inserted as pending — their only queue writer is the conductor.
		fs.rmSync(path.join(root, "_workers.parallel"), { force: true });
		await dispatchNewTasks(store, root);
		expect(store.readAll().filter((e) => e.taskKey.startsWith("ap-"))).toHaveLength(0);
		expect(store.findByKey("manual-task")?.status).toBe("pending");
		const raw = fs.readFileSync(path.join(root, "_workers.parallel"), "utf8");
		expect(raw).not.toContain("ap-goal-ap-t99");
		expect(raw).not.toContain("ap-goal-ap-crlf");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("D-104: an owner with only conductor tasks burns no docs-gate warning", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		// Undocumented key whose only undispatched task is a conductor task —
		// the skip happens at collection, so the docs gate never fires.
		const taskDir = path.join(root, "undoc-key", "workers", "ap-undoc-key-x");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(
			path.join(taskDir, "task.md"),
			conductorTaskMd("verifier", ["read_scope:", "  - .agenticdoc/goal.md"]),
			"utf8",
		);
		const gates: string[] = [];

		await dispatchNewTasks(store, root, {
			warnedKeys: new Set<string>(),
			onDocGate: (key) => {
				gates.push(key);
				return true;
			},
		});

		expect(gates).toHaveLength(0);
		expect(store.readAll()).toHaveLength(0);
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── Worker-mode wiring ───────────────────────────────────────────────────────

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	/** Last setActiveTools payload (copy). */
	activeTools: () => string[] | undefined;
	sent: string[];
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(e: unknown) => unknown>>();
	const tools: Array<string[]> = [];
	const sent: string[] = [];
	const pi = {
		on: (name: string, cb: (e: unknown) => unknown) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: (text: string) => {
			sent.push(text);
		},
		setActiveTools: (t: string[]) => {
			tools.push([...t]);
		},
		registerTool: () => {},
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name: string, payload?: unknown) => {
			for (const cb of handlers.get(name) ?? []) cb(payload);
		},
		activeTools: () => tools.at(-1),
		sent,
	};
}

/** Write {agenticdocRoot}/{owner}/workers/{taskKey}/task.md and activate
 * worker-mode against it (PI_WORKER_TASK set; caller deletes the env in
 * finally). `agenticdocRoot` is the directory holding {owner}/workers/. */
async function activateWorker(
	agenticdocRoot: string,
	owner: string,
	taskKey: string,
	taskMd: string,
): Promise<{ worker: FakeWorker; taskDir: string }> {
	const taskDir = path.join(agenticdocRoot, owner, "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), taskMd, "utf8");
	process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
	const worker = fakeWorkerPi();
	await workerModeActivate(worker.pi);
	return { worker, taskDir };
}

describe("typed tool allowlists (D-107 / VC-023)", () => {
	it("VC-023: the 5 autopilot types resolve to per-type tool sets exactly equal to the Python REGISTRY", async () => {
		const root = mkdtemp();
		const cases: Array<{ type: string; expected: string[]; extra?: string[] }> = [
			{ type: "roadmap-writer", expected: PY_REGISTRY["roadmap-writer"] },
			{ type: "phase-writer", expected: PY_REGISTRY["phase-writer"] },
			// Read-only types additionally carry the narrow write channel
			// (D-101/D-104/D-106): the Python REGISTRY tuples stay unchanged, so
			// the parity assertion is the Python set plus the TS-only worker_file.
			{
				type: "verifier",
				expected: [...PY_REGISTRY.verifier, WORKER_FILE_TOOL],
				extra: ["read_scope:", "  - .agenticdoc/goal.md"],
			},
			{ type: "reviewer", expected: [...PY_REGISTRY.reviewer, WORKER_FILE_TOOL] },
			{ type: "repair", expected: PY_REGISTRY.repair },
		];
		try {
			for (const c of cases) {
				const { worker } = await activateWorker(
					root,
					"goal-ap",
					`ap-goal-ap-${c.type}`,
					conductorTaskMd(c.type, c.extra),
				);
				worker.emit("before_agent_start");
				// Order-exact equality against the dispatch.py tool tuples.
				expect(worker.activeTools(), c.type).toEqual(c.expected);
			}
		} finally {
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-023: origin=conductor with an unregistered type fails closed — exit 1, reason in output.md", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		try {
			const { taskDir } = await activateWorker(root, "goal-ap", "ap-goal-ap-stale", conductorTaskMd("verifier-pro"));
			expect(exitSpy).toHaveBeenCalledTimes(1);
			expect(exitSpy).toHaveBeenCalledWith(1);
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("Fail-closed");
			expect(output).toContain("verifier-pro");
			expect(output).toContain("tool-allowlist entry");
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toContain("[ERROR]");
			// The refused spawn still recorded its pid observation line (D-115).
			expect(trace.split("\n").filter((l) => START_PID_RE.test(l))).toHaveLength(1);
		} finally {
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-023: origin=conductor with type 'fallback' also fails closed (the fallback bucket is not a dispatchable type)", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		try {
			const { taskDir } = await activateWorker(root, "goal-ap", "ap-goal-ap-fb", conductorTaskMd("fallback"));
			expect(exitSpy).toHaveBeenCalledWith(1);
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("Fail-closed");
			expect(output).toContain("'fallback'");
		} finally {
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-023/D-106: a conductor verifier without a read_scope fails closed (missing and present-but-empty both refuse)", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		try {
			// read_scope absent entirely (stale-bundle shape).
			const missing = await activateWorker(root, "goal-ap", "ap-goal-ap-noscope", conductorTaskMd("verifier"));
			expect(exitSpy).toHaveBeenCalledTimes(1);
			expect(exitSpy).toHaveBeenCalledWith(1);
			let output = fs.readFileSync(path.join(missing.taskDir, "output.md"), "utf8");
			expect(output).toContain("Fail-closed");
			expect(output).toContain("read_scope");

			// read_scope present but empty — same refusal (parity with dispatch.py,
			// which rejects empty scopes for verifier).
			exitSpy.mockClear();
			const empty = await activateWorker(
				root,
				"goal-ap",
				"ap-goal-ap-emptyscope",
				conductorTaskMd("verifier", ["read_scope:"]),
			);
			expect(exitSpy).toHaveBeenCalledTimes(1);
			output = fs.readFileSync(path.join(empty.taskDir, "output.md"), "utf8");
			expect(output).toContain("read_scope");
		} finally {
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("GC-8/AC-012: manual and pre-existing types keep their sets — unknown manual types fall back to the full set", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		try {
			const cases: Array<{ taskKey: string; md: string; expected: string[] }> = [
				{ taskKey: "m-coding", md: "type: coding\n\nwork\n", expected: PY_CODING_TOOLS },
				{ taskKey: "m-review", md: "type: review\n\nwork\n", expected: [...PY_REVIEW_TOOLS, WORKER_FILE_TOOL] },
				{
					taskKey: "m-research",
					md: "type: research\n\nwork\n",
					expected: ["read", "find", "grep", "ls", "bash", WORKER_FILE_TOOL],
				},
				// GC-8 verbatim: the manual fallback path stays for unknown types.
				{ taskKey: "m-unknown", md: "type: mystery-type\n\nwork\n", expected: PY_CODING_TOOLS },
			];
			for (const c of cases) {
				const { worker } = await activateWorker(root, "goal-ap", c.taskKey, c.md);
				worker.emit("before_agent_start");
				expect(worker.activeTools(), c.taskKey).toEqual(c.expected);
			}
			// No refusal fired anywhere on the manual path.
			expect(exitSpy).not.toHaveBeenCalled();

			// A MANUAL verifier without read_scope also runs (no origin marker →
			// the fail-closed gate does not apply; T-13's zero-interception
			// contract for unmarked tasks is unchanged).
			const { worker } = await activateWorker(root, "goal-ap", "m-verifier", "type: verifier\n\nwork\n");
			worker.emit("before_agent_start");
			expect(worker.activeTools()).toEqual([...PY_REVIEW_TOOLS, WORKER_FILE_TOOL]);
			expect(exitSpy).not.toHaveBeenCalled();
		} finally {
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── [START] pid observation (D-115) ──────────────────────────────────────────

describe("[START] pid observation (D-115)", () => {
	it("VC-024 anchor: exactly one [START] pid=<pid> line per spawn, appended to trace.log without reset", async () => {
		const root = mkdtemp();
		const owner = "goal-ap";
		const taskKey = "ap-goal-ap-start";
		const taskDir = path.join(root, owner, "workers", taskKey);
		fs.mkdirSync(taskDir, { recursive: true });
		// A previous spawn's observation line + unrelated trace content:
		// trace.log is append-only (worker.log is what the launcher truncates
		// per spawn), so both must survive every new spawn.
		fs.writeFileSync(
			path.join(taskDir, "trace.log"),
			"[START] pid=11111\n[FLOW] 2026-01-01T00:00:00Z tool_call read\n",
			"utf8",
		);
		const pidLines = (): string[] =>
			fs
				.readFileSync(path.join(taskDir, "trace.log"), "utf8")
				.split("\n")
				.filter((l) => START_PID_RE.test(l));

		try {
			await activateWorker(root, owner, taskKey, "type: coding\n\nwork\n");
			expect(pidLines()).toEqual(["[START] pid=11111", `[START] pid=${process.pid}`]);

			// Second spawn of the same task: exactly one more line, nothing reset.
			await activateWorker(root, owner, taskKey, "type: coding\n\nwork\n");
			expect(pidLines()).toEqual(["[START] pid=11111", `[START] pid=${process.pid}`, `[START] pid=${process.pid}`]);

			// Every line parses under the Python state.py start_pids regex
			// (^(\d+)$ exact) — spawn count 3, including the pre-seeded one.
			const pids = pidLines().map((l) => Number(START_PID_RE.exec(l)?.[1]));
			expect(pids).toEqual([11111, process.pid, process.pid]);
		} finally {
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── agenticdocRoot semantic split (D-116) ────────────────────────────────────

describe("agenticdocRoot semantic split (D-116)", () => {
	it("D-116: parseTaskMd splits the outputDir base (workers dir) from the true .agenticdoc root", () => {
		const root = mkdtemp();
		const taskMd = path.join(root, ".agenticdoc", "goal-ap", "workers", "ap-goal-ap-l2", "task.md");
		fs.mkdirSync(path.dirname(taskMd), { recursive: true });
		fs.writeFileSync(taskMd, "type: phase-writer\n\nwork\n", "utf8");
		const meta = parseTaskMd(taskMd);
		// Output-path contract unchanged: the workers dir stays the base.
		expect(meta.agenticdocRoot).toBe(path.join(root, ".agenticdoc", "goal-ap", "workers"));
		// The true root is task.md four levels up — where goal.md lives.
		expect(meta.trueAgenticdocRoot).toBe(path.join(root, ".agenticdoc"));

		// _scratch layout resolves to the same true root; origin round-trips.
		const scratchMd = path.join(root, ".agenticdoc", "_scratch", "workers", "ap-roadmap", "task.md");
		fs.mkdirSync(path.dirname(scratchMd), { recursive: true });
		fs.writeFileSync(scratchMd, conductorTaskMd("roadmap-writer"), "utf8");
		const scratchMeta = parseTaskMd(scratchMd);
		expect(scratchMeta.trueAgenticdocRoot).toBe(path.join(root, ".agenticdoc"));
		expect(scratchMeta.origin).toBe("conductor");
		expect(meta.origin).toBeUndefined();
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("D-116: [GOAL_CHECK] records the real goal.md mtime; outputDir stays the task dir", async () => {
		const root = mkdtemp();
		const agenticdoc = path.join(root, ".agenticdoc");
		const owner = "goal-ap";
		const taskKey = "ap-goal-ap-l2";
		const taskDir = path.join(agenticdoc, owner, "workers", taskKey);
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(agenticdoc, "goal.md"), "# Project Goal\n\n## Goal\nship it\n", "utf8");
		const goalMs = fs.statSync(path.join(agenticdoc, "goal.md")).mtimeMs;
		// Negative control (the D-116 bug): the OLD root — the workers dir —
		// never contains goal.md, so its mtime was a guaranteed 0 miss.
		expect(goalMtime(path.join(agenticdoc, owner, "workers"))).toBe(0);
		expect(goalMtime(agenticdoc)).toBe(goalMs);

		try {
			const { worker } = await activateWorker(
				agenticdoc,
				owner,
				taskKey,
				[
					"---",
					"type: phase-writer",
					"origin: conductor",
					"loop: l2:goal-ap:spec-to-design",
					"attempt: 1",
					"---",
					"",
					"- name: patch",
					"  prompt: |",
					"    patch the evidence",
					"",
				].join("\n"),
			);
			worker.emit("agent_settled"); // dispatches phase 1
			worker.emit("agent_settled"); // phase 1 completes → [GOAL_CHECK] + success

			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			const m = /\[GOAL_CHECK\] phase=1 goal_mtime=(\d+(?:\.\d+)?)/.exec(trace);
			expect(m).toBeDefined();
			expect(Number(m?.[1])).toBeGreaterThan(0);
			expect(Number(m?.[1])).toBe(goalMs); // the REAL goal.md mtime, not 0
			// outputDir contract unchanged: outputs land in the task dir.
			expect(fs.existsSync(path.join(taskDir, "output.md"))).toBe(true);
			expect(fs.existsSync(path.join(taskDir, "progress", "phase-1.md"))).toBe(true);
		} finally {
			delete process.env.PI_WORKER_TASK;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});
});
