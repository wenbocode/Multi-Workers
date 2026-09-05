/**
 * Tests for the agent-team-loop extension internals.
 *
 * mw-dispatch-reliability T-10: absorbs packages/multi-workers/test-l1-full.ts
 * (a loose script that had drifted from the code — it imported a runPhases that
 * no longer exists and asserted the pre-model 7-column worker rows). Adds the
 * waitForStart stability-window tests (T-08) and the /mw doctor formatter
 * tests (T-09).
 */
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import { dispatchNewTasks } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import { StateManager } from "../../src/extensions/agent-team-loop/pm/state-manager.ts";
import { dispatchTask } from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import { formatDoctorReport } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import type { DoctorJson } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import { waitForStart } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import {
	appendGoalCheck,
	appendTrace,
	writeOutput,
} from "../../src/extensions/agent-team-loop/worker/output-writer.ts";
import { goalMtime, writePhaseFile } from "../../src/extensions/agent-team-loop/worker/phase-runner.ts";

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "atl-test-"));
}

function makeTaskDir(root: string, key: string): string {
	const dir = path.join(root, key);
	fs.mkdirSync(dir, { recursive: true });
	return dir;
}

// ── WorkerStore + dispatchTask ───────────────────────────────────────────────

describe("WorkerStore", () => {
	it("upserts and reads back two entries", async () => {
		const root = mkdtemp();
		const ws = new WorkerStore(root);
		await ws.upsert({
			taskKey: "k1",
			status: "pending",
			cli: "pi",
			provider: "",
			taskPath: "/t1",
			dispatchedAt: "",
			updatedAt: "",
			model: "",
		});
		await ws.upsert({
			taskKey: "k2",
			status: "running",
			cli: "codex",
			provider: "",
			taskPath: "/t2",
			dispatchedAt: "",
			updatedAt: "",
			model: "",
		});
		expect(ws.readAll()).toHaveLength(2);
		expect(ws.findByKey("k2")?.status).toBe("running");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("writes 8-column rows (incl. model)", async () => {
		const root = mkdtemp();
		const ws = new WorkerStore(root);
		await ws.upsert({
			taskKey: "k1",
			status: "pending",
			cli: "pi",
			provider: "timi",
			taskPath: "/t1",
			dispatchedAt: "",
			updatedAt: "",
			model: "m1",
		});
		const lines = fs
			.readFileSync(path.join(root, "_workers.parallel"), "utf8")
			.split("\n")
			.filter((l) => l.trim());
		expect(lines).toHaveLength(1);
		expect(lines[0].split(" | ")).toHaveLength(8);
		expect(lines[0].split(" | ")[7]).toBe("m1");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("dispatchTask stamps ISO 8601 timestamps", async () => {
		const root = mkdtemp();
		const ws = new WorkerStore(root);
		await dispatchTask(
			{ taskKey: "disp-1", status: "pending", cli: "pi", provider: "timi", model: "", taskPath: "/t" },
			ws,
		);
		const line =
			fs
				.readFileSync(path.join(root, "_workers.parallel"), "utf8")
				.split("\n")
				.find((l) => l.includes("disp-1")) ?? "";
		const cols = line.split(" | ");
		expect(/^\d{4}-\d{2}-\d{2}T/.test(cols[5]?.trim() ?? "")).toBe(true);
		expect(/^\d{4}-\d{2}-\d{2}T/.test(cols[6]?.trim() ?? "")).toBe(true);
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── StateManager ─────────────────────────────────────────────────────────────

describe("StateManager", () => {
	it("rejects an invalid phase", async () => {
		const root = mkdtemp();
		const sm = new StateManager(root, "task-x");
		await expect(sm.write({ phase: "WRONG" as unknown as "SPEC" })).rejects.toThrow(/Invalid phase/);
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── output-writer ────────────────────────────────────────────────────────────

describe("output-writer writeOutput", () => {
	it("exit 0 writes the four sections and >50 bytes", () => {
		const root = mkdtemp();
		const key = "task-out";
		makeTaskDir(root, key);
		writeOutput({
			taskKey: key,
			agenticdocRoot: root,
			exitCode: 0,
			summary: "Done",
			changedFiles: ["x.ts"],
			verificationSteps: "npm test",
			exitReason: "OK",
		});
		const out = fs.readFileSync(path.join(root, key, "output.md"), "utf8");
		for (const section of ["## Summary", "## Changed Files", "## Verification Steps", "## Exit Reason"]) {
			expect(out).toContain(section);
		}
		expect(out.length).toBeGreaterThan(50);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("exit 1 writes Exit Reason", () => {
		const root = mkdtemp();
		const key = "task-out";
		makeTaskDir(root, key);
		writeOutput({ taskKey: key, agenticdocRoot: root, exitCode: 1, summary: "Err", exitReason: "bad" });
		expect(fs.readFileSync(path.join(root, key, "output.md"), "utf8")).toContain("## Exit Reason");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("exit 2 writes Questions", () => {
		const root = mkdtemp();
		const key = "task-out";
		makeTaskDir(root, key);
		writeOutput({ taskKey: key, agenticdocRoot: root, exitCode: 2, summary: "Need", questions: "What?" });
		expect(fs.readFileSync(path.join(root, key, "output.md"), "utf8")).toContain("## Questions");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("exit 130 still writes the file", () => {
		const root = mkdtemp();
		const key = "task-out";
		makeTaskDir(root, key);
		writeOutput({ taskKey: key, agenticdocRoot: root, exitCode: 130, summary: "Cancelled" });
		expect(fs.existsSync(path.join(root, key, "output.md"))).toBe(true);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("appendTrace and appendGoalCheck write trace markers", () => {
		const root = mkdtemp();
		const key = "task-trace";
		makeTaskDir(root, key);
		appendTrace(key, root, "tool_call bash");
		appendGoalCheck(key, root, 1, 123.45);
		const trace = fs.readFileSync(path.join(root, key, "trace.log"), "utf8");
		expect(trace).toContain("[FLOW]");
		expect(trace).toContain("tool_call bash");
		expect(trace).toContain("[GOAL_CHECK] phase=1 goal_mtime=123.45");
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── phase-runner ─────────────────────────────────────────────────────────────

describe("phase-runner", () => {
	it("writePhaseFile creates progress/phase-1.md with content", () => {
		const root = mkdtemp();
		const key = "task-ph";
		makeTaskDir(root, key);
		writePhaseFile(key, root, 0, "phase one summary text");
		const phaseFile = path.join(root, key, "progress", "phase-1.md");
		expect(fs.existsSync(phaseFile)).toBe(true);
		expect(fs.readFileSync(phaseFile, "utf8").length).toBeGreaterThan(20);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("goalMtime returns a number (0 when goal.md is missing)", () => {
		const root = mkdtemp();
		expect(goalMtime(root)).toBe(0);
		fs.writeFileSync(path.join(root, "goal.md"), "# Goal", "utf8");
		expect(typeof goalMtime(root)).toBe("number");
		expect(goalMtime(root)).toBeGreaterThan(0);
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── IndexStore ───────────────────────────────────────────────────────────────

describe("IndexStore", () => {
	it("upserts and reads back an entry in AgenticTask 7-column format", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		await is.upsert({
			key: "my-key",
			status: "active",
			phase: "EXECUTE",
			claimId: "123",
			deps: "",
			desc: "test",
			updated: new Date().toISOString(),
		});
		const entry = is.findByKey("my-key");
		expect(entry?.phase).toBe("EXECUTE");
		expect(entry?.status).toBe("active");
		const raw = fs.readFileSync(path.join(root, "_index.parallel"), "utf8");
		expect(raw).toContain("| my-key | active | EXECUTE | 123 |");
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── waitForStart stability window (mw-dispatch-reliability AC-005) ──────────

describe("waitForStart stability window", () => {
	it("returns false when the process dies inside the window", async () => {
		let alive = false;
		setTimeout(() => {
			alive = true;
		}, 10);
		setTimeout(() => {
			alive = false;
		}, 150);
		// PID file appears at 10ms, process dies at 150ms — never stable for 300ms.
		const result = await waitForStart(() => ({ running: alive }), 700, 300, 20);
		expect(result).toBe(false);
	});

	it("returns true when the process stays alive past the window", async () => {
		const result = await waitForStart(() => ({ running: true }), 2000, 200, 20);
		expect(result).toBe(true);
	});

	it("falls back to the instantaneous state at timeout", async () => {
		let alive = false;
		setTimeout(() => {
			alive = true;
		}, 300);
		// Alive at the 400ms deadline but observed for <300ms: still started.
		const result = await waitForStart(() => ({ running: alive }), 400, 300, 20);
		expect(result).toBe(true);
	});

	it("returns false when never running", async () => {
		const result = await waitForStart(() => ({ running: false }), 200, 300, 20);
		expect(result).toBe(false);
	});
});

// ── /mw doctor formatter (mw-dispatch-reliability AC-007) ───────────────────

describe("formatDoctorReport", () => {
	const sample: DoctorJson = {
		service: { running: false, pid: null, pid_file: "/x/.mw/mw.pid" },
		proxy: [{ route: "claude", port: 7001, listening: true }],
		orphan_proxy: { detected: true, ports: [{ port: 7001, owner_pids: [2716] }] },
		launcher_log: { exists: true, tail: ["x"], error_count: 2, fatal: true },
		queue: {
			non_terminal: [{ task_key: "t", status: "pending", cli: "pi", task_md_exists: false }],
			stale_count: 1,
			archived_total: 3,
		},
		credentials: {
			routes: [{ route: "timi", available: true, source: { kind: "file", path: "~/.x" }, missing: null }],
		},
		bundle: { available: true, stale: true },
		fix: { applied: ["archived stale entries: t"] },
		summary: {
			healthy: false,
			issues: ["mw service not running (workers will not be dispatched)"],
			suggestions: ["run /mw build"],
		},
	};

	it("renders every doctor section in the summary", () => {
		const text = formatDoctorReport(sample, true);
		expect(text).toContain("服务: 未运行");
		expect(text).toContain("代理端口");
		expect(text).toContain("孤儿代理");
		expect(text).toContain("launcher 日志: 2 个错误行（含 FATAL）");
		expect(text).toContain("队列: 1 个进行中任务，1 个 stale，3 条已归档");
		expect(text).toContain("路由凭证: timi 可用");
		expect(text).toContain("扩展 bundle: 源码较新，建议 /mw build 重建");
		expect(text).toContain("已自动修复: archived stale entries: t");
		expect(text).toContain("整体: 1 个问题");
		expect(text).toContain("建议: run /mw build");
	});

	it("reports a healthy project without fix actions", () => {
		const healthy: DoctorJson = {
			service: { running: true, pid: 60512 },
			proxy: [{ route: "claude", port: 7001, listening: true }],
			orphan_proxy: { detected: false, ports: [] },
			launcher_log: { exists: false, tail: [], error_count: 0, fatal: false },
			queue: { non_terminal: [], stale_count: 0, archived_total: 0 },
			credentials: { routes: [] },
			bundle: { available: true, stale: false },
			summary: { healthy: true, issues: [], suggestions: [] },
		};
		const text = formatDoctorReport(healthy, false);
		expect(text).toContain("服务: 运行中 (PID 60512)");
		expect(text).toContain("整体: 健康");
		expect(text).not.toContain("已自动修复");
	});
});

// ── keyed workers layout ({key}/workers/<task-key>/, _scratch fallback) ──────

describe("IndexStore.activeKey", () => {
	it("returns the active key and ignores idle entries", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		await is.upsert({
			key: "k-idle",
			status: "idle",
			phase: "SPEC",
			claimId: "1",
			deps: "",
			desc: "",
			updated: new Date().toISOString(),
		});
		await is.upsert({
			key: "k-active",
			status: "active",
			phase: "EXECUTE",
			claimId: "2",
			deps: "",
			desc: "",
			updated: new Date().toISOString(),
		});
		expect(is.activeKey()).toBe("k-active");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("returns undefined when no key is active", () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		expect(is.activeKey()).toBeUndefined();
		fs.rmSync(root, { recursive: true, force: true });
	});
});

describe("dispatchNewTasks keyed workers scan", () => {
	function writeTaskMd(root: string, rel: string, type = "coding"): string {
		const dir = path.join(root, rel);
		fs.mkdirSync(dir, { recursive: true });
		const md = path.join(dir, "task.md");
		fs.writeFileSync(md, `type: ${type}\n\nwork\n`, "utf8");
		return md;
	}

	it("dispatches tasks under {key}/workers/ and _scratch/workers/", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const mdA = writeTaskMd(root, path.join("my-key", "workers", "task-a"));
		const mdB = writeTaskMd(root, path.join("_scratch", "workers", "task-b"));

		await dispatchNewTasks(store, root);

		const entries = store.readAll();
		const a = entries.find((e) => e.taskKey === "task-a");
		const b = entries.find((e) => e.taskKey === "task-b");
		expect(a?.status).toBe("pending");
		expect(a?.taskPath).toBe(mdA);
		expect(b?.status).toBe("pending");
		expect(b?.taskPath).toBe(mdB);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("ignores root-level task dirs (legacy layout) and plain key dirs", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		// Legacy root-level worker dir — must NOT be dispatched anymore.
		writeTaskMd(root, "root-task");
		// Plain AgenticTask key dir without workers/ — must not crash or dispatch.
		fs.mkdirSync(path.join(root, "plain-key"), { recursive: true });
		fs.writeFileSync(path.join(root, "plain-key", "spec.md"), "x", "utf8");

		await dispatchNewTasks(store, root);

		expect(store.readAll().filter((e) => e.taskKey === "root-task")).toHaveLength(0);
		expect(store.readAll().filter((e) => e.taskKey === "plain-key")).toHaveLength(0);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("does not re-dispatch a task key already in the queue", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		writeTaskMd(root, path.join("my-key", "workers", "task-x"));
		await dispatchNewTasks(store, root);
		// Rewind status to pending and rescan — the key is already queued.
		const entry = store.readAll().find((e) => e.taskKey === "task-x");
		expect(entry).toBeDefined();
		await dispatchNewTasks(store, root);
		expect(store.readAll().filter((e) => e.taskKey === "task-x")).toHaveLength(1);
		fs.rmSync(root, { recursive: true, force: true });
	});
});
