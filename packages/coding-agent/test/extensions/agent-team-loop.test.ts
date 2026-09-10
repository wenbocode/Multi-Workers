/**
 * Tests for the agent-team-loop extension internals.
 *
 * mw-dispatch-reliability T-10: absorbs packages/multi-workers/test-l1-full.ts
 * (a loose script that had drifted from the code — it imported a runPhases that
 * no longer exists and asserted the pre-model 7-column worker rows). Adds the
 * waitForStart stability-window tests (T-08) and the /mw doctor formatter
 * tests (T-09).
 */

import { spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../src/core/extensions/types.ts";
import {
	autoTakeOverFromDoc,
	dispatchNewTasks,
	docFromWrite,
	evidencePhaseFromWrite,
	keyFromDocWrite,
	nudgeEvidenceReview,
	nudgeGoalUnestablished,
	pmActivate,
	restoreWatch,
	startWorkerPollLoop,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import { StateManager } from "../../src/extensions/agent-team-loop/pm/state-manager.ts";
import { dispatchTask } from "../../src/extensions/agent-team-loop/pm/task-dispatcher.ts";
import {
	ackTasks,
	claimState,
	formatDoctorReport,
	makeScopedDocGateNotifier,
	type PmUiHolder,
	type PmWatchState,
	readOutputSection,
	readTerminalDetail,
	readWorkerLogTail,
	registerMwCommands,
	registerPmKeyCommands,
	registerSwitchKeyTool,
	registerWorkerTools,
	renderWatchLines,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import {
	HEARTBEAT_INTERVAL_MS,
	readHeartbeatInfo,
	readTaskProgress,
} from "../../src/extensions/agent-team-loop/shared/heartbeat.ts";
import { IndexStore, readIndexMdActive } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import type { DoctorJson } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import { waitForStart } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import {
	dispatchDocGaps,
	formatDocsBadge,
	phaseDocGaps,
	readPhaseDocs,
} from "../../src/extensions/agent-team-loop/shared/phase-docs.ts";
import {
	phaseAuditWarnings,
	pmStateInterfaceViolation,
} from "../../src/extensions/agent-team-loop/shared/pm-state-guard.ts";
import { type WorkerStatus, WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import {
	appendCheckpoint,
	appendEnd,
	appendError,
	appendGoalCheck,
	appendHeartbeat,
	appendPhase,
	appendStart,
	appendTimeout,
	appendTool,
	appendToolError,
	appendTrace,
	writeOutput,
} from "../../src/extensions/agent-team-loop/worker/output-writer.ts";
import { goalMtime, writePhaseFile } from "../../src/extensions/agent-team-loop/worker/phase-runner.ts";
import {
	checkpointAnchorMs,
	computeRisk,
	DEFAULT_BUDGET_MS,
	DEFAULT_IDLE_MS,
	parseTaskMd,
	resolveBudgetMs,
	resolveIdleMs,
	steerAtMs,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "atl-test-"));
}

function makeTaskDir(root: string, key: string): string {
	const dir = path.join(root, key);
	fs.mkdirSync(dir, { recursive: true });
	return dir;
}

/** Write a complete phase-doc set for a key: spec + design (>= 500 bytes),
 * a numbered AC, and one research note per phase — everything the docs gate
 * requires (no goal.md is written, so the §0 check is skipped like on a
 * project without an established goal). */
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

function fakeCmdPi(): {
	pi: ExtensionAPI;
	commands: Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>;
	tools: Map<
		string,
		{
			execute: (
				id: string,
				params: unknown,
				signal: undefined,
				onUpdate: undefined,
				ctx: ExtensionContext,
			) => Promise<{ content: Array<{ type: string; text: string }> }>;
		}
	>;
	entries: Array<{ customType: string; data: unknown }>;
	messages: string[];
	sent: Array<{ customType: string; content: string }>;
} {
	const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
	const tools = new Map<
		string,
		{
			execute: (
				id: string,
				params: unknown,
				signal: undefined,
				onUpdate: undefined,
				ctx: ExtensionContext,
			) => Promise<{ content: Array<{ type: string; text: string }> }>;
		}
	>();
	const entries: Array<{ customType: string; data: unknown }> = [];
	const messages: string[] = [];
	const sent: Array<{ customType: string; content: string }> = [];
	const pi = {
		registerCommand: (
			name: string,
			opts: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
		) => {
			commands.set(name, opts.handler);
		},
		registerTool: (tool: {
			name: string;
			execute: (
				id: string,
				params: unknown,
				signal: undefined,
				onUpdate: undefined,
				ctx: ExtensionContext,
			) => Promise<{ content: Array<{ type: string; text: string }> }>;
		}) => {
			tools.set(tool.name, tool);
		},
		appendEntry: (customType: string, data: unknown) => {
			entries.push({ customType, data });
		},
		sendUserMessage: (message: string) => {
			messages.push(message);
		},
		sendMessage: (m: { customType: string; content: string }) => {
			sent.push(m);
		},
	} as unknown as ExtensionAPI;
	return { pi, commands, tools, entries, messages, sent };
}

async function seedKey(
	root: string,
	key: string,
	claimId: string,
	status: "active" | "idle" | "done" = "active",
): Promise<void> {
	await new IndexStore(root).upsert({
		key,
		status,
		phase: "EXECUTE",
		claimId,
		deps: "",
		desc: "",
		updated: new Date().toISOString(),
	});
}

function fakeCmdCtx(): {
	ctx: ExtensionCommandContext;
	notifications: string[];
	widgets: Array<string[] | undefined>;
} {
	const notifications: string[] = [];
	const widgets: Array<string[] | undefined> = [];
	const ctx = {
		hasUI: true,
		ui: {
			notify: (message: string) => {
				notifications.push(message);
			},
			setWidget: (_key: string, content: string[] | undefined) => {
				widgets.push(content);
			},
		},
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications, widgets };
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

	it("VC-004: heartbeat interval stays under the 60s AC-003 ceiling; lines are structured", () => {
		expect(HEARTBEAT_INTERVAL_MS).toBeLessThanOrEqual(60_000);
		const root = mkdtemp();
		const key = "task-hb";
		makeTaskDir(root, key);
		appendHeartbeat(key, root, "2/3");
		appendHeartbeat(key, root, "-");
		const lines = fs
			.readFileSync(path.join(root, key, "trace.log"), "utf8")
			.trim()
			.split("\n");
		expect(lines).toHaveLength(2);
		for (const line of lines) {
			expect(line).toMatch(/^\[HEARTBEAT\] \S+ task=task-hb phase=\S+$/);
		}
		expect(lines[0]).toContain("phase=2/3");
		expect(lines[1]).toContain("phase=-");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-005: heartbeats coexist with [FLOW]/[GOAL_CHECK] lines without changing their format", () => {
		const root = mkdtemp();
		const key = "task-hb-mixed";
		makeTaskDir(root, key);
		appendTrace(key, root, "tool_call bash");
		appendHeartbeat(key, root, "1/2");
		appendGoalCheck(key, root, 1, 123.45);
		appendHeartbeat(key, root, "2/2");
		const lines = fs
			.readFileSync(path.join(root, key, "trace.log"), "utf8")
			.trim()
			.split("\n");
		expect(lines[0]).toMatch(/^\[FLOW\] \S+ tool_call bash$/);
		expect(lines[1]).toMatch(/^\[HEARTBEAT\] \S+ task=task-hb-mixed phase=1\/2$/);
		expect(lines[2]).toMatch(/^\[GOAL_CHECK\] phase=1 goal_mtime=123\.45$/);
		expect(lines[3]).toMatch(/^\[HEARTBEAT\] \S+ task=task-hb-mixed phase=2\/2$/);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("readHeartbeatInfo parses count, phase progress, and recency", () => {
		const root = mkdtemp();
		const key = "task-hb-read";
		makeTaskDir(root, key);
		appendHeartbeat(key, root, "1/3");
		appendHeartbeat(key, root, "2/3");
		const info = readHeartbeatInfo(path.join(root, key));
		expect(info?.count).toBe(2);
		expect(info?.phase).toBe("2");
		expect(info?.phaseTotal).toBe("3");
		expect(info?.ageMs).toBeGreaterThanOrEqual(0);
		expect(info?.ageMs).toBeLessThan(60_000);
		expect(info?.firstTs).toMatch(/^\d{4}-\d{2}-\d{2}T/);

		// Phaseless task: phase labels read back as "-".
		appendHeartbeat(key, root, "-");
		const info2 = readHeartbeatInfo(path.join(root, key));
		expect(info2?.phase).toBe("-");
		expect(info2?.phaseTotal).toBe("-");

		// trace.log without heartbeat lines (old bundle) → undefined.
		const other = makeTaskDir(root, "task-legacy");
		fs.writeFileSync(path.join(other, "trace.log"), "[FLOW] 2026-01-01T00:00:00Z tool_call read\n", "utf8");
		expect(readHeartbeatInfo(other)).toBeUndefined();
		// Missing trace.log entirely → undefined.
		expect(readHeartbeatInfo(path.join(root, "nope"))).toBeUndefined();
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-016: lifecycle appenders write structured, parseable trace lines", () => {
		const root = mkdtemp();
		const key = "task-lifecycle";
		makeTaskDir(root, key);
		appendStart(key, root, "coding", 3);
		appendPhase(key, root, "start", 1, 3, "investigate");
		appendTool(key, root, "read", "src/index.ts");
		appendTool(key, root, "bash", "npm test");
		appendToolError(key, root, "edit", "oldText not found in file");
		appendPhase(key, root, "done", 1, 3);
		appendTimeout(key, root, "idle", "no activity for 612s (last delta 612s ago, last tool 640s ago)");
		appendError(key, root, "boom\nsecond line ignored");
		appendEnd(key, root, { exitCode: 1, elapsedMs: 65_000, toolCalls: 4, phaseDone: 1, phaseTotal: 3 });

		const lines = fs
			.readFileSync(path.join(root, key, "trace.log"), "utf8")
			.trim()
			.split("\n");
		expect(lines[0]).toMatch(/^\[START\] \S+ task=task-lifecycle type=coding phases=3$/);
		expect(lines[1]).toMatch(/^\[PHASE\] \S+ start 1\/3 investigate$/);
		expect(lines[2]).toMatch(/^\[TOOL\] \S+ read src\/index\.ts$/);
		expect(lines[3]).toMatch(/^\[TOOL\] \S+ bash npm test$/);
		expect(lines[4]).toMatch(/^\[TOOL_ERR\] \S+ edit oldText not found in file$/);
		expect(lines[5]).toMatch(/^\[PHASE\] \S+ done 1\/3$/);
		expect(lines[6]).toMatch(
			/^\[TIMEOUT\] \S+ idle: no activity for 612s \(last delta 612s ago, last tool 640s ago\)$/,
		);
		expect(lines[7]).toMatch(/^\[ERROR\] \S+ boom$/);
		expect(lines[8]).toMatch(/^\[END\] \S+ exit=1 elapsed=65s tools=4 phases=1\/3$/);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-016: phaseless [START]/[END] use phases=- and long tool targets truncate", () => {
		const root = mkdtemp();
		const key = "task-flat";
		makeTaskDir(root, key);
		appendStart(key, root, "review", 0);
		const longPath = `${"a".repeat(100)}.ts`;
		appendTool(key, root, "read", longPath);
		appendEnd(key, root, { exitCode: 0, elapsedMs: 5_000, toolCalls: 1 });
		const trace = fs.readFileSync(path.join(root, key, "trace.log"), "utf8");
		expect(trace).toMatch(/^\[START\] \S+ task=task-flat type=review phases=-$/m);
		expect(trace).toMatch(/^\[END\] \S+ exit=0 elapsed=5s tools=1 phases=-$/m);
		// One tool call stays one trace line even with a long target.
		expect(trace).toMatch(/^\[TOOL\] \S+ read a{79}…$/m);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-016: readTaskProgress parses runtime, exit code, and last action", () => {
		const root = mkdtemp();
		const key = "task-prog";
		makeTaskDir(root, key);
		const start = new Date(Date.now() - 120_000).toISOString();
		const end = new Date(Date.now() - 30_000).toISOString();
		fs.writeFileSync(
			path.join(root, key, "trace.log"),
			`[START] ${start} task=task-prog type=coding phases=2\n` +
				`[TOOL] ${start} read src/a.ts\n` +
				`[HEARTBEAT] ${new Date(Date.now() - 90_000).toISOString()} task=task-prog phase=1/2\n` +
				`[TOOL] ${end} edit src/b.ts\n` +
				`[END] ${end} exit=0 elapsed=90s tools=7 phases=2/2\n`,
			"utf8",
		);
		const prog = readTaskProgress(path.join(root, key));
		expect(prog?.startTs).toBe(start);
		expect(prog?.endTs).toBe(end);
		expect(prog?.exitCode).toBe(0);
		expect(prog?.endPhases).toBe("2/2");
		expect(prog?.lastAction).toBe("edit src/b.ts");
		// Terminal runtime: endTs - startTs = 90s.
		expect(prog?.elapsedMs).toBeGreaterThanOrEqual(89_000);
		expect(prog?.elapsedMs).toBeLessThanOrEqual(91_000);
		// Heartbeat state still parses alongside the lifecycle lines.
		expect(prog?.heartbeat?.count).toBe(1);
		expect(prog?.heartbeat?.phase).toBe("1");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-016: readTaskProgress computes running elapsed from [START] and tolerates old formats", () => {
		const root = mkdtemp();
		const running = makeTaskDir(root, "task-run");
		fs.writeFileSync(
			path.join(running, "trace.log"),
			`[START] ${new Date(Date.now() - 45_000).toISOString()} task=task-run type=coding phases=-\n` +
				`[TOOL] ${new Date(Date.now() - 10_000).toISOString()} grep TODO\n`,
			"utf8",
		);
		const run = readTaskProgress(running);
		expect(run?.endTs).toBeUndefined();
		expect(run?.lastAction).toBe("grep TODO");
		expect(run?.elapsedMs).toBeGreaterThanOrEqual(44_000);
		expect(run?.elapsedMs).toBeLessThanOrEqual(46_000);
		// Old bundle trace: only [FLOW]/[HEARTBEAT] lines — no lifecycle fields.
		const legacy = makeTaskDir(root, "task-old");
		fs.writeFileSync(
			path.join(legacy, "trace.log"),
			"[FLOW] 2026-01-01T00:00:00Z tool_call read\n" + "[HEARTBEAT] 2026-01-01T00:00:30Z task=task-old phase=-\n",
			"utf8",
		);
		const old = readTaskProgress(legacy);
		expect(old?.startTs).toBeUndefined();
		expect(old?.elapsedMs).toBeUndefined();
		expect(old?.lastAction).toBeUndefined();
		expect(old?.heartbeat?.count).toBe(1);
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

	it("VC-007: worker liveness line names stale workers; absent when no running workers", () => {
		const withLiveness: DoctorJson = {
			...sample,
			worker_liveness: [
				{ task_key: "t-run", last_heartbeat: "2026-09-08T03:00:00Z", age_s: 10, verdict: "alive" },
				{ task_key: "t-stuck", last_heartbeat: "2026-09-08T02:00:00Z", age_s: 600, verdict: "stale" },
				{ task_key: "t-old", last_heartbeat: null, age_s: null, verdict: "no-heartbeat" },
			],
		};
		const text = formatDoctorReport(withLiveness, false);
		expect(text).toContain("worker 活性: 存活 1; 疑似挂起: t-stuck; 无心跳 1");
		// Old doctor output without the section keeps a clean summary.
		expect(formatDoctorReport(sample, false)).not.toContain("worker 活性");
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

	it("VC-001: with divergent active rows the most recently updated wins", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		await is.upsert({
			key: "agent-team-loop",
			status: "active",
			phase: "EXECUTE",
			claimId: "1",
			deps: "",
			desc: "",
			updated: "2026-09-07T10:00:00.000Z",
		});
		await is.upsert({
			key: "goal-autopilot",
			status: "active",
			phase: "EXECUTE",
			claimId: "2",
			deps: "",
			desc: "",
			updated: "2026-09-08T02:00:00.000Z",
		});
		expect(is.activeKey()).toBe("goal-autopilot");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-001: python-style local timestamp is compared as a real instant, not lexicographically", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		// ISO-UTC "2026-09-01T00:00:00Z" vs local "2026-09-08 10:00" — the local
		// row is newer by days under any timezone (max shift ±14h). Lexicographic
		// order would also agree here, but a mixed "T"-format pair would not.
		await is.upsert({
			key: "old-iso",
			status: "active",
			phase: "EXECUTE",
			claimId: "1",
			deps: "",
			desc: "",
			updated: "2026-09-01T00:00:00.000Z",
		});
		await is.upsert({
			key: "new-local",
			status: "active",
			phase: "EXECUTE",
			claimId: "2",
			deps: "",
			desc: "",
			updated: "2026-09-08 10:00",
		});
		expect(is.activeKey()).toBe("new-local");
		fs.rmSync(root, { recursive: true, force: true });
	});
});

describe("readIndexMdActive", () => {
	it("VC-002: reads the degraded-mode active pointer from _index.md", () => {
		const root = mkdtemp();
		fs.writeFileSync(path.join(root, "_index.md"), "active: my-feature-key\n", "utf8");
		expect(readIndexMdActive(root)).toBe("my-feature-key");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-002: returns undefined when the file or the active line is missing", () => {
		const root = mkdtemp();
		expect(readIndexMdActive(root)).toBeUndefined();
		fs.writeFileSync(path.join(root, "_index.md"), "# no active pointer\n", "utf8");
		expect(readIndexMdActive(root)).toBeUndefined();
		fs.rmSync(root, { recursive: true, force: true });
	});
});

describe("IndexStore.claim (M1: atomic claim primitive)", () => {
	it("demotes other active rows, verifies the write, and refuses held-live targets without force", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		// key-a held by a foreign live claim (predicate says held), key-b idle.
		await is.upsert({
			key: "key-a",
			status: "active",
			phase: "EXECUTE",
			claimId: "other-window:1",
			deps: "",
			desc: "",
			updated: new Date().toISOString(),
		});
		await is.upsert({
			key: "key-b",
			status: "idle",
			phase: "SPEC",
			claimId: "",
			deps: "",
			desc: "",
			updated: new Date().toISOString(),
		});

		// Take key-b for self-1: ok, key-a demoted (single-active discipline).
		const r1 = await is.claim("key-b", "self-1", () => false);
		expect(r1.ok).toBe(true);
		expect(r1.created).toBe(false);
		expect(is.findByKey("key-b")?.claimId).toBe("self-1");
		expect(is.findByKey("key-b")?.status).toBe("active");
		expect(is.findByKey("key-a")?.status).toBe("idle");

		// self-2 cannot take key-b while the predicate reports the holder live.
		const r2 = await is.claim("key-b", "self-2", () => true);
		expect(r2.ok).toBe(false);
		expect(r2.blockedBy).toBe("self-1");
		expect(is.findByKey("key-b")?.claimId).toBe("self-1"); // untouched

		// force stomps the held-live claim.
		const r3 = await is.claim("key-b", "self-2", () => true, { force: true });
		expect(r3.ok).toBe(true);
		expect(is.findByKey("key-b")?.claimId).toBe("self-2");

		// Unknown keys are auto-created as active SPEC rows.
		const r4 = await is.claim("key-new", "self-1", () => false);
		expect(r4.ok).toBe(true);
		expect(r4.created).toBe(true);
		expect(is.findByKey("key-new")?.status).toBe("active");
		expect(is.findByKey("key-new")?.phase).toBe("SPEC");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("quiet claim (session restore) keeps the row's status and spares other active rows", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		const seed = async (key: string, status: "active" | "done", claimId: string): Promise<void> => {
			await is.upsert({
				key,
				status,
				phase: "VERIFY",
				claimId,
				deps: "",
				desc: "",
				updated: new Date().toISOString(),
			});
		};
		await seed("key-a", "done", "old-self:1"); // completed key, stale claim
		await seed("key-x", "active", "live-window:2"); // someone else's active row

		const r = await is.claim("key-a", "self-new", () => false, { demoteOthers: false, activate: false });
		expect(r.ok).toBe(true);
		expect(is.findByKey("key-a")?.claimId).toBe("self-new");
		// activate=false: a done key stays done; demoteOthers=false: key-x untouched.
		expect(is.findByKey("key-a")?.status).toBe("done");
		expect(is.findByKey("key-x")?.status).toBe("active");
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
		writePhaseDocs(root, "my-key");
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
		writePhaseDocs(root, "my-key");
		writeTaskMd(root, path.join("my-key", "workers", "task-x"));
		await dispatchNewTasks(store, root);
		// Rewind status to pending and rescan — the key is already queued.
		const entry = store.readAll().find((e) => e.taskKey === "task-x");
		expect(entry).toBeDefined();
		await dispatchNewTasks(store, root);
		expect(store.readAll().filter((e) => e.taskKey === "task-x")).toHaveLength(1);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-009/VC-010: type review/research scan routes to pi/timi; codex preserved", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		writePhaseDocs(root, "my-key");
		writeTaskMd(root, path.join("my-key", "workers", "rev-task"), "review");
		writeTaskMd(root, path.join("my-key", "workers", "res-task"), "research");
		writeTaskMd(root, path.join("my-key", "workers", "cx-task"), "codex");

		await dispatchNewTasks(store, root);

		const rev = store.findByKey("rev-task");
		const res = store.findByKey("res-task");
		const cx = store.findByKey("cx-task");
		expect(rev?.cli).toBe("pi");
		expect(rev?.provider).toBe("timi");
		expect(res?.cli).toBe("pi");
		expect(res?.provider).toBe("timi");
		expect(cx?.cli).toBe("codex");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-013: undoc key with all tasks already queued produces no gate event", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		// Undocumented key whose only task is already in the queue (historical
		// work) — the scan must not evaluate or report its gate at all.
		writeTaskMd(root, path.join("undoc-quiet", "workers", "task-q"));
		await dispatchTask(
			{
				taskKey: "task-q",
				status: "done",
				cli: "pi",
				provider: "timi",
				taskPath: path.join(root, "undoc-quiet", "workers", "task-q", "task.md"),
				model: "",
			},
			store,
		);
		const gates: Array<{ key: string; gaps: string[] }> = [];

		await dispatchNewTasks(store, root, {
			warnedKeys: new Set<string>(),
			onDocGate: (key, gaps) => {
				gates.push({ key, gaps });
				return true;
			},
		});

		expect(gates).toHaveLength(0);
		// Contrast: an undoc key WITH an undispatched task still gates once (VC-014).
		writeTaskMd(root, path.join("undoc-live", "workers", "task-l"));
		await dispatchNewTasks(store, root, {
			warnedKeys: new Set<string>(),
			onDocGate: (key, gaps) => {
				gates.push({ key, gaps });
				return true;
			},
		});
		expect(gates).toHaveLength(1);
		expect(gates[0]?.key).toBe("undoc-live");
		expect(store.findByKey("task-l")).toBeUndefined();
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("m1: a suppressed gate broadcast does not burn the once-per-session slot", async () => {
		const root = mkdtemp();
		const ws = new WorkerStore(root);
		// Undocumented key with one undispatched task.
		const taskDir = path.join(root, "undoc-key", "workers", "t1");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");

		const warned = new Set<string>();
		const broadcast: string[] = [];

		// First scan: notifier suppresses (scoped to another window's key).
		await dispatchNewTasks(ws, root, { warnedKeys: warned, onDocGate: () => false });
		expect(broadcast).toHaveLength(0);
		expect(warned.has("undoc-key")).toBe(false); // slot NOT burned

		// Second scan: notifier broadcasts (e.g. the user switched to the key).
		await dispatchNewTasks(ws, root, {
			warnedKeys: warned,
			onDocGate: (k) => {
				broadcast.push(k);
				return true;
			},
		});
		expect(broadcast).toEqual(["undoc-key"]);
		expect(warned.has("undoc-key")).toBe(true);

		// Third scan: deduped — no further broadcasts.
		await dispatchNewTasks(ws, root, {
			warnedKeys: warned,
			onDocGate: (k) => {
				broadcast.push(k);
				return true;
			},
		});
		expect(broadcast).toEqual(["undoc-key"]);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-015: scoped doc-gate notifier broadcasts only the watched key", () => {
		const sent: Array<{ customType: string; content: string }> = [];
		const pi = {
			sendMessage: (m: { customType: string; content: string }) => sent.push(m),
		} as unknown as ExtensionAPI;
		const watch: PmWatchState = { key: "watched" };
		const notify = makeScopedDocGateNotifier(pi, watch);

		notify("watched", ["spec.md missing"]);
		notify("other", ["spec.md missing"]);
		watch.key = undefined;
		notify("watched", ["spec.md missing"]);

		const gateMessages = sent.filter((m) => m.content.includes("skipped dispatch"));
		expect(gateMessages).toHaveLength(1);
		expect(gateMessages[0]?.content).toContain("'watched'");
		expect(gateMessages[0]?.content).toContain("spec.md missing");
	});

	it("skips worker tasks under undocumented keys, reports once, dispatches after docs exist", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		writeTaskMd(root, path.join("undoc-key", "workers", "task-u"));
		const gates: Array<{ key: string; gaps: string[] }> = [];
		const opts = {
			warnedKeys: new Set<string>(),
			onDocGate: (key: string, gaps: string[]) => {
				gates.push({ key, gaps });
				return true;
			},
		};

		await dispatchNewTasks(store, root, opts);
		expect(store.readAll().filter((e) => e.taskKey === "task-u")).toHaveLength(0);
		expect(gates).toHaveLength(1);
		expect(gates[0]?.key).toBe("undoc-key");
		// No goal.md in the fixture → §0 skipped; 5 = spec, spec evidence, AC, design, design evidence.
		expect(gates[0]?.gaps).toHaveLength(5);

		// Second scan: the same key is not reported again.
		await dispatchNewTasks(store, root, opts);
		expect(gates).toHaveLength(1);

		// Once the docs exist, the queued task dispatches.
		writePhaseDocs(root, "undoc-key");
		await dispatchNewTasks(store, root, opts);
		expect(store.readAll().find((e) => e.taskKey === "task-u")?.status).toBe("pending");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("classifies doc presence, sizes, and evidence notes like advance_phase.py", () => {
		const root = mkdtemp();
		const keyDir = path.join(root, "k");
		fs.mkdirSync(keyDir, { recursive: true });
		// Empty key: all gate items missing except §0 (no goal.md → check skipped).
		expect(phaseDocGaps(readPhaseDocs(root, "k"))).toHaveLength(5);

		// Under-size spec still counts as missing.
		fs.writeFileSync(path.join(keyDir, "spec.md"), "x".repeat(499), "utf8");
		expect(phaseDocGaps(readPhaseDocs(root, "k"))[0]).toContain("spec.md");

		// Full-size spec (with a numbered AC) + spec evidence note clear the spec half of the gate.
		fs.writeFileSync(path.join(keyDir, "spec.md"), `${"x".repeat(500)}\n\n| AC-001 | in x, y returns z |\n`, "utf8");
		const research = path.join(keyDir, "evidence", "research");
		fs.mkdirSync(research, { recursive: true });
		fs.writeFileSync(path.join(research, "spec-topic-2026-01-01.md"), "n", "utf8");
		expect(phaseDocGaps(readPhaseDocs(root, "k"))).toHaveLength(2);

		// Only spec-*/design-* note prefixes count as phase evidence.
		fs.writeFileSync(path.join(research, "notes.md"), "n", "utf8");
		expect(phaseDocGaps(readPhaseDocs(root, "k"))).toHaveLength(2);

		// Full docs: no gaps; _scratch bypasses the dispatch gate entirely.
		fs.writeFileSync(path.join(keyDir, "design.md"), "x".repeat(500), "utf8");
		fs.writeFileSync(path.join(research, "design-topic-2026-01-01.md"), "n", "utf8");
		expect(dispatchDocGaps(root, "k")).toHaveLength(0);
		expect(dispatchDocGaps(root, "_scratch")).toHaveLength(0);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("formats the docs badge", () => {
		expect(
			formatDocsBadge({ spec: true, design: false, specEvidence: 1, designEvidence: 0, specS0: true, specAC: true }),
		).toBe("S+ D- ev:1/2");
	});

	it("requires §0 Goal Alignment when goal.md is established, and numbered ACs always", () => {
		const root = mkdtemp();
		const keyDir = path.join(root, "k");
		fs.mkdirSync(keyDir, { recursive: true });
		fs.writeFileSync(
			path.join(root, "goal.md"),
			"# Project Goal\n\n## Goal\nBuild the agent team framework\n\n## Context\n\n## Key Constraints\n",
			"utf8",
		);
		fs.writeFileSync(path.join(keyDir, "spec.md"), `${"x".repeat(500)}\n\n| AC-001 | in x, y returns z |\n`, "utf8");
		const research = path.join(keyDir, "evidence", "research");
		fs.mkdirSync(research, { recursive: true });
		fs.writeFileSync(path.join(research, "spec-topic-2026-01-01.md"), "n", "utf8");

		// Goal established but spec has no §0 → gap.
		expect(phaseDocGaps(readPhaseDocs(root, "k")).some((g) => g.includes("§0 Goal Alignment"))).toBe(true);

		// §0 present but without 预期收益 → still a gap.
		fs.writeFileSync(
			path.join(keyDir, "spec.md"),
			`${"x".repeat(500)}\n\n## §0 Goal Alignment\n- alignment: serves the goal\n\n| AC-001 | in x, y returns z |\n`,
			"utf8",
		);
		expect(phaseDocGaps(readPhaseDocs(root, "k")).some((g) => g.includes("§0 Goal Alignment"))).toBe(true);

		// §0 naming 预期收益 clears it.
		fs.writeFileSync(
			path.join(keyDir, "spec.md"),
			`${"x".repeat(500)}\n\n## §0 Goal Alignment\n- alignment: serves the goal\n- 预期收益: fewer false kills (evidence/runs)\n\n| AC-001 | in x, y returns z |\n`,
			"utf8",
		);
		expect(phaseDocGaps(readPhaseDocs(root, "k")).some((g) => g.includes("§0 Goal Alignment"))).toBe(false);

		// No numbered AC → gap regardless of goal state.
		fs.writeFileSync(
			path.join(keyDir, "spec.md"),
			`${"x".repeat(500)}\n\n## §0 Goal Alignment\n- 预期收益: x\n`,
			"utf8",
		);
		expect(phaseDocGaps(readPhaseDocs(root, "k")).some((g) => g.includes("AC-NNN"))).toBe(true);

		// draft goal → §0 check skipped; only the AC gap remains.
		fs.writeFileSync(
			path.join(root, "goal.md"),
			"# Project Goal\n\n> status: draft\n\n## Goal\n<!-- placeholder -->\n",
			"utf8",
		);
		fs.writeFileSync(path.join(keyDir, "spec.md"), `${"x".repeat(500)}\n`, "utf8");
		const gapsDraft = phaseDocGaps(readPhaseDocs(root, "k"));
		expect(gapsDraft.some((g) => g.includes("§0"))).toBe(false);
		expect(gapsDraft.some((g) => g.includes("AC-NNN"))).toBe(true);
		fs.rmSync(root, { recursive: true, force: true });
	});
	it("VC-003: owner-key mismatch warns once per pair and dispatches under the active key", async () => {
		const root = mkdtemp();
		const ws = new WorkerStore(root);
		const is = new IndexStore(root);
		const { pi, tools, sent } = fakeCmdPi();
		writePhaseDocs(root, "vc3-active"); // documented so dispatch proceeds
		await seedKey(root, "vc3-active", windowClaimId());
		const watch: PmWatchState = { key: "vc3-watched" };
		registerWorkerTools(pi, ws, new AckStore(root), is, root, watch);
		const tool = tools.get("dispatch_worker");
		if (!tool) throw new Error("dispatch_worker not registered");

		const r1 = await tool.execute(
			"id1",
			{ task_key: "t1", description: "work" },
			undefined,
			undefined,
			fakeCmdCtx().ctx,
		);
		expect(r1.content[0]?.text).toContain("Dispatched worker 't1'");
		// Task lands under the ACTIVE key, never the stale watch.
		expect(fs.existsSync(path.join(root, "vc3-active", "workers", "t1", "task.md"))).toBe(true);
		// Exactly one mismatch warning naming both keys.
		const warns = sent.filter((m) => m.content.includes("owner-key mismatch"));
		expect(warns).toHaveLength(1);
		expect(warns[0]?.content).toContain("vc3-watched");
		expect(warns[0]?.content).toContain("vc3-active");

		// Second dispatch under the same divergence: no repeat warning.
		await tool.execute("id2", { task_key: "t2", description: "work" }, undefined, undefined, fakeCmdCtx().ctx);
		expect(sent.filter((m) => m.content.includes("owner-key mismatch"))).toHaveLength(1);
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── pm-state.md interface guard (hard block) + takeover audit ──────────────

describe("pm-state-guard", () => {
	it("blocks write/edit that changes or creates pm-state.md interface lines", () => {
		const root = mkdtemp();
		const keyDir = path.join(root, "k");
		fs.mkdirSync(keyDir, { recursive: true });
		const pm = path.join(keyDir, "pm-state.md");
		fs.writeFileSync(pm, "# PM State: k\n\n- Key: k\n- Phase: SPEC\n- Updated: 2026-09-09 12:00\n", "utf8");

		// Write changing the Phase line → blocked.
		const blocked = pmStateInterfaceViolation(
			"write",
			{ path: pm, content: "# PM State: k\n- Phase: EXECUTE\n- Updated: 2026-09-09 12:00\n" },
			os.tmpdir(),
			root,
		);
		expect(blocked).toBeDefined();
		expect(blocked).toContain("advance_phase.py");

		// Write that keeps the interface lines byte-identical (log update) → allowed.
		const allowed = pmStateInterfaceViolation(
			"write",
			{ path: pm, content: "# PM State: k\n- Phase: SPEC\n- Updated: 2026-09-09 12:00\n\nnew log line\n" },
			os.tmpdir(),
			root,
		);
		expect(allowed).toBeUndefined();

		// Edit hunk touching the Phase line → blocked (even when removing it).
		const editBlocked = pmStateInterfaceViolation(
			"edit",
			{ path: pm, edits: [{ oldText: "- Phase: SPEC\n", newText: "- Phase: EXECUTE\n" }] },
			os.tmpdir(),
			root,
		);
		expect(editBlocked).toContain("advance_phase.py");

		// Edit touching only log sections → allowed.
		const editOk = pmStateInterfaceViolation(
			"edit",
			{ path: pm, edits: [{ oldText: "# PM State: k\n", newText: "# PM State: k\n\n## Log\n- entry\n" }] },
			os.tmpdir(),
			root,
		);
		expect(editOk).toBeUndefined();

		// Non-pm-state files, paths outside .agenticdoc, and _scratch → allowed.
		expect(
			pmStateInterfaceViolation("write", { path: path.join(keyDir, "spec.md"), content: "x" }, os.tmpdir(), root),
		).toBeUndefined();
		expect(
			pmStateInterfaceViolation(
				"write",
				{ path: path.join(root, "..", "elsewhere.md"), content: "- Phase: X\n" },
				os.tmpdir(),
				root,
			),
		).toBeUndefined();
		expect(
			pmStateInterfaceViolation(
				"write",
				{ path: path.join(root, "_scratch", "pm-state.md"), content: "- Phase: X\n" },
				os.tmpdir(),
				root,
			),
		).toBeUndefined();
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("phaseAuditWarnings replays gates and flags two-source divergence (timeout-key replica)", () => {
		const root = mkdtemp();
		const keyDir = path.join(root, "k");
		fs.mkdirSync(keyDir, { recursive: true });
		fs.writeFileSync(
			path.join(root, "goal.md"),
			"# Project Goal\n\n## Goal\nBuild the agent team framework\n\n## Context\n\n## Key Constraints\n",
			"utf8",
		);
		// Hand-bypassed key: pm-state at EXECUTE, spec without §0, misnamed research
		// note, no tasks/ — and the index still says SPEC.
		fs.writeFileSync(path.join(keyDir, "spec.md"), `${"x".repeat(500)}\n\n| AC-001 | y |\n`, "utf8");
		fs.mkdirSync(path.join(keyDir, "evidence", "research"), { recursive: true });
		fs.writeFileSync(path.join(keyDir, "evidence", "research", "forensics-2026-09-09.md"), "n", "utf8");
		fs.writeFileSync(path.join(keyDir, "design.md"), "x".repeat(500), "utf8");
		fs.writeFileSync(path.join(keyDir, "pm-state.md"), "- Phase: EXECUTE\n- Updated: 2026-09-09 16:20\n", "utf8");

		const warnings = phaseAuditWarnings(root, "k", "SPEC");
		expect(warnings.some((w) => w.includes("INDEX-DIVERGENCE"))).toBe(true);
		expect(warnings.some((w) => w.includes("§0 Goal Alignment"))).toBe(true);
		expect(warnings.some((w) => w.includes("spec-*.md"))).toBe(true);
		expect(warnings.some((w) => w.includes("design-*.md"))).toBe(true);
		expect(warnings.some((w) => w.includes("tasks/"))).toBe(true);

		// Compliant key at the same phase → no warnings.
		fs.writeFileSync(path.join(keyDir, "evidence", "research", "spec-init.md"), "n", "utf8");
		fs.writeFileSync(path.join(keyDir, "evidence", "research", "design-arch.md"), "n", "utf8");
		fs.writeFileSync(
			path.join(keyDir, "spec.md"),
			`${"x".repeat(500)}\n\n## §0 Goal Alignment\n- 预期收益: x\n\n| AC-001 | y |\n`,
			"utf8",
		);
		fs.mkdirSync(path.join(keyDir, "tasks"), { recursive: true });
		fs.writeFileSync(path.join(keyDir, "tasks", "001-first.md"), "# Task\n", "utf8");
		expect(phaseAuditWarnings(root, "k", "EXECUTE")).toHaveLength(0);

		// Early-phase / pending / scratch keys → nothing to audit.
		fs.writeFileSync(path.join(keyDir, "pm-state.md"), "- Phase: (pending)\n", "utf8");
		expect(phaseAuditWarnings(root, "k", "—")).toHaveLength(0);
		expect(phaseAuditWarnings(root, "_scratch", "EXECUTE")).toHaveLength(0);
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── startWorkerPollLoop summary scoping (baseline + active-key filter) ──────

describe("startWorkerPollLoop summary scoping", () => {
	function fakePi(): {
		pi: ExtensionAPI;
		messages: string[];
		options: Array<{ triggerTurn?: boolean } | undefined>;
	} {
		const messages: string[] = [];
		const options: Array<{ triggerTurn?: boolean } | undefined> = [];
		const pi = {
			sendMessage: (m: { content: string }, opts?: { triggerTurn?: boolean }) => {
				messages.push(m.content);
				options.push(opts);
			},
		} as unknown as ExtensionAPI;
		return { pi, messages, options };
	}

	/** A fake ExtensionContext whose setWidget calls are captured. */
	function fakeUiCtx(): { ctx: ExtensionContext; widgets: Array<string[] | undefined> } {
		const widgets: Array<string[] | undefined> = [];
		const ctx = {
			hasUI: true,
			ui: {
				setWidget: (_key: string, content: string[] | undefined) => {
					widgets.push(content);
				},
			},
		} as unknown as ExtensionContext;
		return { ctx, widgets };
	}

	/** Queue a task row (with output.md) under {owner}/workers/{taskKey}/. */
	async function queueTask(root: string, owner: string, taskKey: string, status: WorkerStatus): Promise<void> {
		const taskDir = path.join(root, owner, "workers", taskKey);
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
		fs.writeFileSync(path.join(taskDir, "output.md"), "## Summary\n\ndid the thing\n", "utf8");
		await new WorkerStore(root).upsert({
			taskKey,
			status,
			cli: "pi",
			provider: "timi",
			taskPath: path.join(taskDir, "task.md"),
			dispatchedAt: "",
			updatedAt: "",
			model: "",
		});
	}

	async function activateKey(root: string, key: string): Promise<void> {
		await new IndexStore(root).upsert({
			key,
			status: "active",
			phase: "EXECUTE",
			claimId: "1",
			deps: "",
			desc: "",
			updated: new Date().toISOString(),
		});
	}

	it("never replays terminal rows that predate the window (baseline snapshot)", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		await queueTask(root, "key-a", "old-done", "done");
		await queueTask(root, "key-a", "old-failed", "failed");
		const watch: PmWatchState = { key: "key-a" };
		const ui: PmUiHolder = { ctx: undefined };

		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			vi.advanceTimersByTime(500);
			expect(messages).toEqual([]);
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("notifies a pending→done transition under the watched key exactly once", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		await queueTask(root, "key-a", "t1", "pending");
		const watch: PmWatchState = { key: "key-a" };
		const ui: PmUiHolder = { ctx: undefined };

		vi.useFakeTimers();
		try {
			const { pi, messages, options } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			const entry = store.findByKey("t1");
			if (!entry) throw new Error("t1 missing from queue");
			await store.upsert({ ...entry, status: "done" });
			vi.advanceTimersByTime(500);
			expect(messages).toHaveLength(1);
			expect(messages[0]).toContain("[t1] done");
			expect(messages[0]).toContain("did the thing");
			// AC-015: the terminal result is the finish call — it must trigger a PM
			// turn so an idle PM processes the result and continues the loop.
			expect(options[0]?.triggerTurn).toBe(true);
			expect(messages[0]).toContain("PM 循环");
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("stays silent without a watched key and for tasks under other keys", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		await activateKey(root, "key-b");
		await queueTask(root, "key-a", "t0", "pending");
		await queueTask(root, "key-b", "t2", "pending");
		const watch: PmWatchState = { key: undefined };
		const ui: PmUiHolder = { ctx: undefined };

		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			for (const key of ["t0", "t2"]) {
				const entry = store.findByKey(key);
				if (!entry) throw new Error(`${key} missing from queue`);
				await store.upsert({ ...entry, status: "done" });
			}
			vi.advanceTimersByTime(500);
			// No watched key → no notifications, even for globally active keys.
			expect(messages).toEqual([]);
			// Watching key-a later must not resurrect the already-consumed t0.
			watch.key = "key-a";
			vi.advanceTimersByTime(500);
			expect(messages).toEqual([]);
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("notifies _scratch tasks when _scratch is watched", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await queueTask(root, "_scratch", "t4", "pending");
		const watch: PmWatchState = { key: "_scratch" };
		const ui: PmUiHolder = { ctx: undefined };

		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			const entry = store.findByKey("t4");
			if (!entry) throw new Error("t4 missing from queue");
			await store.upsert({ ...entry, status: "failed" });
			vi.advanceTimersByTime(500);
			expect(messages).toHaveLength(1);
			expect(messages[0]).toContain("[t4] failed");
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	/** Queue a task row with no output.md; optionally write a worker.log. */
	async function queueTaskNoOutput(root: string, owner: string, taskKey: string, workerLog?: string): Promise<void> {
		const taskDir = path.join(root, owner, "workers", taskKey);
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: review\n\nwork\n", "utf8");
		if (workerLog !== undefined) fs.writeFileSync(path.join(taskDir, "worker.log"), workerLog, "utf8");
		await new WorkerStore(root).upsert({
			taskKey,
			status: "pending",
			cli: "claude",
			provider: "",
			taskPath: path.join(taskDir, "task.md"),
			dispatchedAt: "",
			updatedAt: "",
			model: "",
		});
	}

	it("surfaces the launcher spawn-failure reason when output.md is missing", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		await queueTaskNoOutput(
			root,
			"key-a",
			"t5",
			"[launcher] spawn failed (2026-09-05T10:23:12+00:00): Required credential for route 'claude-cli' is not available (env ANTHROPIC_AUTH_TOKEN unset).\n",
		);
		const watch: PmWatchState = { key: "key-a" };
		const ui: PmUiHolder = { ctx: undefined };

		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			const entry = store.findByKey("t5");
			if (!entry) throw new Error("t5 missing from queue");
			await store.upsert({ ...entry, status: "failed" });
			vi.advanceTimersByTime(500);
			expect(messages).toHaveLength(1);
			expect(messages[0]).toContain("[t5] failed");
			expect(messages[0]).toContain("[launcher] spawn failed");
			expect(messages[0]).toContain("ANTHROPIC_AUTH_TOKEN unset");
			expect(messages[0]).not.toContain("可能崩溃/超时");
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("falls back to the generic crash message when worker.log has no spawn failure", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		// Log large enough to be skipped, or with unrelated content — either way
		// no spawn-failure line must surface.
		await queueTaskNoOutput(root, "key-a", "t6", "session output line\n");
		const watch: PmWatchState = { key: "key-a" };
		const ui: PmUiHolder = { ctx: undefined };

		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			const entry = store.findByKey("t6");
			if (!entry) throw new Error("t6 missing from queue");
			await store.upsert({ ...entry, status: "failed" });
			vi.advanceTimersByTime(500);
			expect(messages).toHaveLength(1);
			expect(messages[0]).toContain("[t6] failed");
			expect(messages[0]).toContain("无 output.md 摘要");
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("renders the bottom widget for the watched key and clears it on off", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		await queueTask(root, "key-a", "t7", "running");
		const watch: PmWatchState = { key: "key-a" };
		const { ctx, widgets } = fakeUiCtx();
		const ui: PmUiHolder = { ctx };

		vi.useFakeTimers();
		try {
			const { pi } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			vi.advanceTimersByTime(500);
			expect(widgets.length).toBeGreaterThan(0);
			const last = widgets[widgets.length - 1];
			expect(last).toBeDefined();
			expect(last?.[0]).toContain("[mw] key-a");
			expect(last?.[0]).toContain("phase=EXECUTE");
			expect(last?.some((l) => l.includes("> t7"))).toBe(true);
			// Turning the watch off clears the widget.
			watch.key = undefined;
			vi.advanceTimersByTime(500);
			expect(widgets[widgets.length - 1]).toBeUndefined();
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("does not render a widget without a UI context (headless)", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		await queueTask(root, "key-a", "t8", "running");
		const watch: PmWatchState = { key: "key-a" };
		const ui: PmUiHolder = { ctx: undefined };

		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			vi.advanceTimersByTime(500);
			expect(messages).toEqual([]); // no terminal transitions
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("renderWatchLines shows counts, phase, and failure details", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		await queueTask(root, "key-a", "done-task", "done");
		await queueTaskNoOutput(
			root,
			"key-a",
			"fail-task",
			"[launcher] spawn failed (2026-09-05T10:23:12+00:00): Required credential for route 'claude-cli' is not available (env ANTHROPIC_AUTH_TOKEN unset).\n",
		);
		const failEntry = store.findByKey("fail-task");
		if (!failEntry) throw new Error("fail-task missing");
		await store.upsert({ ...failEntry, status: "failed" });
		await queueTask(root, "key-b", "other-key-task", "running");

		const lines = renderWatchLines(is, store, new AckStore(root), root, "key-a");
		expect(lines[0]).toContain("[mw] key-a");
		expect(lines[0]).toContain("phase=EXECUTE");
		expect(lines[0]).toContain("docs S- D- ev:0/2");
		expect(lines[0]).toContain("1 done");
		expect(lines[0]).toContain("1 failed");
		expect(lines.some((l) => l.includes("+ done-task") && l.includes("did the thing"))).toBe(true);
		expect(lines.some((l) => l.includes("x fail-task") && l.includes("ANTHROPIC_AUTH_TOKEN unset"))).toBe(true);
		// Tasks owned by other keys never appear.
		expect(lines.some((l) => l.includes("other-key-task"))).toBe(false);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-018: running lines show heartbeat phase progress, hb age, and STALE mark", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		await queueTask(root, "key-a", "fresh-task", "running");
		await queueTask(root, "key-a", "stale-task", "running");
		await queueTask(root, "key-a", "legacy-task", "running");

		const hbLine = (ageMs: number, ph: string): string =>
			`[HEARTBEAT] ${new Date(Date.now() - ageMs).toISOString()} task=x phase=${ph}\n`;
		fs.writeFileSync(path.join(root, "key-a", "workers", "fresh-task", "trace.log"), hbLine(15_000, "2/3"), "utf8");
		fs.writeFileSync(path.join(root, "key-a", "workers", "stale-task", "trace.log"), hbLine(300_000, "1/2"), "utf8");
		// Old bundle: trace has [FLOW] lines only — visible (no-hb) placeholder.
		fs.writeFileSync(
			path.join(root, "key-a", "workers", "legacy-task", "trace.log"),
			"[FLOW] 2026-09-08T02:00:00.000Z tool_call read\n",
			"utf8",
		);

		const lines = renderWatchLines(is, store, new AckStore(root), root, "key-a");
		const fresh = lines.find((l) => l.includes("fresh-task"));
		const stale = lines.find((l) => l.includes("stale-task"));
		const legacy = lines.find((l) => l.includes("legacy-task"));
		expect(fresh).toContain("ph 2/3");
		expect(fresh).toMatch(/hb \d+s/);
		expect(fresh).not.toContain("STALE");
		expect(stale).toContain("ph 1/2");
		expect(stale).toContain("STALE");
		expect(legacy).toContain("(no-hb)");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-016: running lines show elapsed runtime from [START] and the last [TOOL] action", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		await queueTask(root, "key-a", "live-task", "running");
		const taskDir = path.join(root, "key-a", "workers", "live-task");
		fs.writeFileSync(
			path.join(taskDir, "trace.log"),
			`[START] ${new Date(Date.now() - 240_000).toISOString()} task=live-task type=coding phases=3\n` +
				`[HEARTBEAT] ${new Date(Date.now() - 20_000).toISOString()} task=live-task phase=1/3\n` +
				`[TOOL] ${new Date(Date.now() - 5_000).toISOString()} read src/deep/nested/file.ts\n`,
			"utf8",
		);
		const lines = renderWatchLines(is, store, new AckStore(root), root, "key-a");
		const live = lines.find((l) => l.includes("live-task"));
		expect(live).toContain("ph 1/3");
		expect(live).toMatch(/up 4m/);
		expect(live).toMatch(/hb \d+s/);
		expect(live).toContain("· read src/deep/nested/file.ts");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-019: terminal summary appends heartbeat stats when >=2 heartbeats exist", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		await queueTask(root, "key-a", "t-hb", "pending");
		await queueTask(root, "key-a", "t-low", "pending");
		const hb = (ageMs: number, ph: string): string =>
			`[HEARTBEAT] ${new Date(Date.now() - ageMs).toISOString()} task=x phase=${ph}\n`;
		// t-hb: three heartbeats spanning exactly 120s, last one at phase 3/3.
		fs.writeFileSync(
			path.join(root, "key-a", "workers", "t-hb", "trace.log"),
			hb(150_000, "1/3") + hb(90_000, "2/3") + hb(30_000, "3/3"),
			"utf8",
		);
		// t-low: single heartbeat — below the 2-line bar, format stays unchanged.
		fs.writeFileSync(path.join(root, "key-a", "workers", "t-low", "trace.log"), hb(30_000, "1/1"), "utf8");
		const watch: PmWatchState = { key: "key-a" };
		const ui: PmUiHolder = { ctx: undefined };
		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			for (const key of ["t-hb", "t-low"]) {
				const entry = store.findByKey(key);
				if (!entry) throw new Error(`${key} missing from queue`);
				await store.upsert({ ...entry, status: "done" });
			}
			vi.advanceTimersByTime(500);
			expect(messages).toHaveLength(2);
			const withStats = messages.find((m) => m.includes("[t-hb] done"));
			const withoutStats = messages.find((m) => m.includes("[t-low] done"));
			// VC-020 format: header carries the stats, then the full output.md body.
			expect(withStats).toContain("[t-hb] done (2m, ph 3/3):");
			expect(withStats).toContain("did the thing");
			// Below the 2-heartbeat bar and no queue timestamps: no stats suffix,
			// but the AC-015 continuation hint is always appended.
			expect(withoutStats).toContain("[t-low] done:\n\n## Summary\n\ndid the thing");
			expect(withoutStats).toContain("PM 循环");
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-016: [START]/[END] lines give the terminal summary exact runtime and phases", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		await queueTask(root, "key-a", "t-exact", "pending");
		const taskDir = path.join(root, "key-a", "workers", "t-exact");
		fs.writeFileSync(
			path.join(taskDir, "trace.log"),
			`[START] ${new Date(Date.now() - 65_000).toISOString()} task=t-exact type=coding phases=2\n` +
				`[END] ${new Date().toISOString()} exit=0 elapsed=65s tools=9 phases=1/2\n`,
			"utf8",
		);
		const watch: PmWatchState = { key: "key-a" };
		const ui: PmUiHolder = { ctx: undefined };

		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			const entry = store.findByKey("t-exact");
			if (!entry) throw new Error("t-exact missing from queue");
			await store.upsert({ ...entry, status: "done" });
			vi.advanceTimersByTime(500);
			expect(messages).toHaveLength(1);
			// Exact [START]→[END] runtime wins even with zero heartbeats.
			expect(messages[0]).toContain("[t-exact] done (1m, ph 1/2):");
			expect(messages[0]).toContain("did the thing");
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-015: failed transitions also trigger a PM turn (finish call)", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		const taskDir = path.join(root, "key-a", "workers", "t-fail");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
		await store.upsert({
			taskKey: "t-fail",
			status: "pending",
			cli: "pi",
			provider: "timi",
			taskPath: path.join(taskDir, "task.md"),
			dispatchedAt: "",
			updatedAt: "",
			model: "",
		});
		const watch: PmWatchState = { key: "key-a" };
		const ui: PmUiHolder = { ctx: undefined };

		vi.useFakeTimers();
		try {
			const { pi, messages, options } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			const entry = store.findByKey("t-fail");
			if (!entry) throw new Error("t-fail missing from queue");
			await store.upsert({ ...entry, status: "failed" });
			vi.advanceTimersByTime(500);
			expect(messages).toHaveLength(1);
			expect(messages[0]).toContain("[t-fail] failed");
			expect(options[0]?.triggerTurn).toBe(true);
			expect(messages[0]).toContain("PM 循环");
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});
});

describe("terminal detail sources (T-05: AC-007/008/009, VC-007/008/009)", () => {
	/** Task dir fixture under key-a/workers/<taskKey> with arbitrary files. */
	function detailDir(files: Record<string, string>): string {
		const root = mkdtemp();
		const dir = path.join(root, "key-a", "workers", "t-detail");
		fs.mkdirSync(dir, { recursive: true });
		for (const [name, body] of Object.entries(files)) fs.writeFileSync(path.join(dir, name), body, "utf8");
		return dir;
	}

	it("readOutputSection extracts any section body, tolerating missing files", () => {
		const dir = detailDir({
			"output.md": "## TL;DR\n\nall green\n\n## Summary\n\nlong text\n\n## Exit Reason\n\nboom\n",
		});
		expect(readOutputSection(dir, "TL;DR")).toBe("all green");
		expect(readOutputSection(dir, "Exit Reason")).toBe("boom");
		expect(readOutputSection(dir, "Missing")).toBeUndefined();
		expect(readOutputSection(path.join(dir, "nowhere"), "TL;DR")).toBeUndefined();
		fs.rmSync(path.dirname(path.dirname(dir)), { recursive: true, force: true });
	});

	it("review S3: section literal is regex-escaped, metacharacters cannot inject", () => {
		const dir = detailDir({
			"output.md": "## a.b(c)+\n\nbrackets body\n\n## Summary\n\nplain body\n",
		});
		// `.`/`(`/`+` would match other sections if injected raw.
		expect(readOutputSection(dir, "a.b(c)+")).toBe("brackets body");
		expect(readOutputSection(dir, "Summary")).toBe("plain body");
		expect(readOutputSection(dir, "aXbXcX")).toBeUndefined();
		fs.rmSync(path.dirname(path.dirname(dir)), { recursive: true, force: true });
	});

	it("VC-007: failed detail = spawn reason (prefix stripped) ?? Exit Reason first line", () => {
		const spawn = detailDir({
			"worker.log":
				"[launcher] spawn failed (2026-09-05T10:23:12+00:00): Required credential for route 'claude-cli' is not available.\n",
			"output.md": "## Exit Reason\n\nignored\n",
		});
		expect(readTerminalDetail(spawn, "failed")).toBe("Required credential for route 'claude-cli' is not available.");
		fs.rmSync(path.dirname(path.dirname(spawn)), { recursive: true, force: true });

		const exit = detailDir({
			"output.md": "## Exit Reason\n\nwall budget exhausted at 45m\nsecond line ignored\n",
		});
		expect(readTerminalDetail(exit, "failed")).toBe("wall budget exhausted at 45m");
		fs.rmSync(path.dirname(path.dirname(exit)), { recursive: true, force: true });
	});

	it("VC-007: failed detail never starts with markdown markers", () => {
		const dir = detailDir({ "output.md": "## Exit Reason\n\n## 预算耗尽（wall）\n" });
		const detail = readTerminalDetail(dir, "failed");
		expect(detail).toBe("预算耗尽（wall）");
		expect(detail.startsWith("#")).toBe(false);
		fs.rmSync(path.dirname(path.dirname(dir)), { recursive: true, force: true });
	});

	it("VC-008: needs-clarification detail = Questions ?? worker.log tail ?? no-output hint", () => {
		const questions = detailDir({ "output.md": "## Questions\n\n- 需要确认数据库选型：Postgres 还是 SQLite？\n" });
		expect(readTerminalDetail(questions, "needs-clarification")).toBe("需要确认数据库选型：Postgres 还是 SQLite？");
		fs.rmSync(path.dirname(path.dirname(questions)), { recursive: true, force: true });

		// No output.md (claude/codex task): worker.log tail is the fallback.
		const logTail = detailDir({
			"worker.log": "[worker] start task=x type=coding\n\n[worker] asking about schema\n",
		});
		expect(readTerminalDetail(logTail, "needs-clarification")).toBe("[worker] asking about schema");
		expect(readWorkerLogTail(logTail)).toBe("[worker] asking about schema");
		fs.rmSync(path.dirname(path.dirname(logTail)), { recursive: true, force: true });

		// Neither file: explicit hint.
		const nothing = detailDir({ "task.md": "type: coding\n" });
		expect(readTerminalDetail(nothing, "needs-clarification")).toBe("no output.md");
		fs.rmSync(path.dirname(path.dirname(nothing)), { recursive: true, force: true });
	});

	it("VC-008: oversized worker.log is not read (256KB guard)", () => {
		const dir = detailDir({ "task.md": "type: coding\n" });
		fs.writeFileSync(path.join(dir, "worker.log"), "x".repeat(256 * 1024 + 1), "utf8");
		expect(readWorkerLogTail(dir)).toBeUndefined();
		expect(readTerminalDetail(dir, "needs-clarification")).toBe("no output.md");
		fs.rmSync(path.dirname(path.dirname(dir)), { recursive: true, force: true });
	});

	it("VC-009: done detail = TL;DR ?? headline-cleaned Summary first line", () => {
		const tldr = detailDir({ "output.md": "## TL;DR\n\nall tests green\n\n## Summary\n\nignored\n" });
		expect(readTerminalDetail(tldr, "done")).toBe("all tests green");
		fs.rmSync(path.dirname(path.dirname(tldr)), { recursive: true, force: true });

		// Old output.md (pre-TL;DR): Summary first line, markers stripped.
		const legacy = detailDir({ "output.md": "## Summary\n\n## Task 002 执行完毕（TDD red 阶段完成）\n细节…\n" });
		expect(readTerminalDetail(legacy, "done")).toBe("Task 002 执行完毕（TDD red 阶段完成）");
		fs.rmSync(path.dirname(path.dirname(legacy)), { recursive: true, force: true });

		// No output.md at all: empty detail, not a placeholder.
		const bare = detailDir({ "task.md": "type: coding\n" });
		expect(readTerminalDetail(bare, "done")).toBe("");
		fs.rmSync(path.dirname(path.dirname(bare)), { recursive: true, force: true });
		console.log("[VERIFY] VC-007: exit_reason=yes, marker_strip=yes");
		console.log("[VERIFY] VC-008: questions=yes, log_tail=yes, hint=yes, size_guard=yes");
		console.log("[VERIFY] VC-009: tldr=yes, legacy_summary_fallback=yes");
	});

	it("renderWatchLines wires readTerminalDetail into terminal rows", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await is.upsert({
			key: "key-a",
			status: "active",
			phase: "EXECUTE",
			claimId: "1",
			deps: "",
			desc: "",
			updated: new Date().toISOString(),
		});
		const taskDir = path.join(root, "key-a", "workers", "t-done");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
		fs.writeFileSync(
			path.join(taskDir, "output.md"),
			"## TL;DR\n\n回归收口完成，三套件全绿\n\n## Summary\n\nignored\n",
			"utf8",
		);
		await store.upsert({
			taskKey: "t-done",
			status: "done",
			cli: "pi",
			provider: "timi",
			taskPath: path.join(taskDir, "task.md"),
			dispatchedAt: "",
			updatedAt: "",
			model: "",
		});
		const lines = renderWatchLines(is, store, new AckStore(root), root, "key-a");
		expect(lines.some((l) => l.includes("+ t-done") && l.includes("回归收口完成，三套件全绿"))).toBe(true);
		fs.rmSync(root, { recursive: true, force: true });
	});
});

describe("watch widget sections (T-06: AC-001/002/003, VC-001/002/003)", () => {
	/** Queue row + task dir fixture under key-a/workers/<taskKey>. */
	async function row(root: string, taskKey: string, status: WorkerStatus, updatedAt: string): Promise<void> {
		const taskDir = path.join(root, "key-a", "workers", taskKey);
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
		fs.writeFileSync(path.join(taskDir, "output.md"), `## Summary\n\n${taskKey} body\n`, "utf8");
		await new WorkerStore(root).upsert({
			taskKey,
			status,
			cli: "pi",
			provider: "timi",
			taskPath: path.join(taskDir, "task.md"),
			dispatchedAt: "",
			updatedAt,
			model: "",
		});
	}

	async function setup(root: string): Promise<void> {
		await new IndexStore(root).upsert({
			key: "key-a",
			status: "active",
			phase: "EXECUTE",
			claimId: "1",
			deps: "",
			desc: "",
			updated: new Date().toISOString(),
		});
	}

	it("VC-001: live rows (running, then pending) are all shown, never folded", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await setup(root);
		for (let i = 1; i <= 3; i++) await row(root, `run-${i}`, "running", `2026-09-10T07:0${i}:00Z`);
		for (let i = 1; i <= 2; i++) await row(root, `pend-${i}`, "pending", `2026-09-10T07:0${i}:00Z`);
		// Six done rows: history folds at 5 — live must not inherit the cap.
		for (let i = 1; i <= 6; i++) await row(root, `hist-${i}`, "done", `2026-09-10T06:0${i}:00Z`);
		const lines = renderWatchLines(is, store, new AckStore(root), root, "key-a");
		for (const k of ["run-1", "run-2", "run-3", "pend-1", "pend-2"]) {
			expect(lines.some((l) => l.includes(k))).toBe(true);
		}
		const idxOf = (k: string): number => lines.findIndex((l) => l.includes(k));
		expect(idxOf("run-1")).toBeLessThan(idxOf("pend-1")); // running before pending
		const more = lines.find((l) => l.includes("more"));
		expect(more).toContain("+1 more"); // 6 done -> 5 shown + 1 folded
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("review S1: live rows sort newest-first within running and pending", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await setup(root);
		// Seed in file order old→new so file order differs from recency order.
		await row(root, "run-old", "running", "2026-09-10T07:00:00Z");
		await row(root, "run-new", "running", "2026-09-10T08:00:00Z");
		await row(root, "pend-old", "pending", "2026-09-10T07:30:00Z");
		await row(root, "pend-new", "pending", "2026-09-10T08:30:00Z");
		const lines = renderWatchLines(is, store, new AckStore(root), root, "key-a");
		const idxOf = (k: string): number => lines.findIndex((l) => l.includes(k));
		expect(idxOf("run-new")).toBeLessThan(idxOf("run-old"));
		expect(idxOf("pend-new")).toBeLessThan(idxOf("pend-old"));
		expect(idxOf("run-old")).toBeLessThan(idxOf("pend-new")); // running section first
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-002: unacked failed/nc rows are always shown; ack clears them from unhandled", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		const ackStore = new AckStore(root);
		await setup(root);
		for (let i = 1; i <= 7; i++) await row(root, `fail-${i}`, "failed", `2026-09-10T06:0${i}:00Z`);
		await row(root, "nc-1", "needs-clarification", "2026-09-10T07:00:00Z");
		let lines = renderWatchLines(is, store, ackStore, root, "key-a");
		expect(lines[0]).toContain("8 unhandled");
		// Unhandled rows never fold: all 8 visible even though > 5.
		for (let i = 1; i <= 7; i++) expect(lines.some((l) => l.includes(`fail-${i}`))).toBe(true);
		expect(lines.some((l) => l.includes("nc-1"))).toBe(true);
		expect(lines.some((l) => l.includes("more"))).toBe(false);

		// Ack everything: unhandled empties (header count gone), rows become
		// history (folded at 5) — the ack channel effect AC-002 leans on.
		await ackStore.ack(["fail-1", "fail-2", "fail-3", "fail-4", "fail-5", "fail-6", "fail-7", "nc-1"]);
		lines = renderWatchLines(is, store, ackStore, root, "key-a");
		expect(lines[0]).not.toContain("unhandled");
		expect(lines.some((l) => l.includes("more"))).toBe(true);
		expect(lines.filter((l) => l.includes("more")).some((l) => l.includes("+3 more"))).toBe(true);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-003: history = done ∪ acked terminal, newest-first, capped at 5 with +N more", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		const ackStore = new AckStore(root);
		await setup(root);
		// h-1 oldest … h-7 newest.
		for (let i = 1; i <= 7; i++) await row(root, `h-${i}`, "done", `2026-09-10T06:0${i}:00Z`);
		let lines = renderWatchLines(is, store, ackStore, root, "key-a");
		expect(lines.some((l) => l.includes("h-7"))).toBe(true); // newest kept
		expect(lines.some((l) => l.includes("h-3"))).toBe(true);
		expect(lines.some((l) => l.includes("h-2"))).toBe(false); // oldest folded
		expect(lines.some((l) => l.includes("h-1"))).toBe(false);
		expect(lines.some((l) => l.includes("+2 more"))).toBe(true);
		const idxOf = (k: string): number => lines.findIndex((l) => l.includes(k));
		expect(idxOf("h-7")).toBeLessThan(idxOf("h-3")); // newest first

		// Five done rows: no fold line.
		const root2 = mkdtemp();
		const store2 = new WorkerStore(root2);
		const is2 = new IndexStore(root2);
		await setup(root2);
		for (let i = 1; i <= 5; i++) await row(root2, `d-${i}`, "done", `2026-09-10T06:0${i}:00Z`);
		lines = renderWatchLines(is2, store2, new AckStore(root2), root2, "key-a");
		expect(lines.some((l) => l.includes("more"))).toBe(false);

		// An acked failed row joins history (done ∪ acked).
		await row(root2, "f-acked", "failed", "2026-09-10T08:00:00Z");
		await new AckStore(root2).ack(["f-acked"]);
		lines = renderWatchLines(is2, store2, new AckStore(root2), root2, "key-a");
		expect(lines.some((l) => l.includes("f-acked"))).toBe(true); // newest -> shown
		expect(lines[0]).not.toContain("unhandled");
		console.log("[VERIFY] VC-001: live_rows=5/5, fold=history_only");
		console.log("[VERIFY] VC-002: unhandled_persist=8/8, after_ack=0");
		console.log("[VERIFY] VC-003: history_cap=5, more=+2, order=newest_first");
		fs.rmSync(root, { recursive: true, force: true });
		fs.rmSync(root2, { recursive: true, force: true });
	});
});

describe("ack channels (T-07: AC-004/005/006/010/011, VC-004/005/006/010/011)", () => {
	async function terminalRow(root: string, taskKey: string, status: WorkerStatus): Promise<void> {
		const taskDir = path.join(root, "key-a", "workers", taskKey);
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
		await new WorkerStore(root).upsert({
			taskKey,
			status,
			cli: "pi",
			provider: "timi",
			taskPath: path.join(taskDir, "task.md"),
			dispatchedAt: "",
			updatedAt: new Date().toISOString(),
			model: "",
		});
	}

	it("VC-004: ackTasks acks terminal rows, persists across instances, rejects non-terminal", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const ackStore = new AckStore(root);
		await terminalRow(root, "t-done", "done");
		await terminalRow(root, "t-fail", "failed");
		await terminalRow(root, "t-run", "running");

		// Terminal rows: acked + persisted (a fresh instance reads the same keys).
		const ok = await ackTasks(store, ackStore, ["t-done", "t-fail"]);
		expect(ok.acked).toEqual(["t-done", "t-fail"]);
		expect(ok.rejected).toEqual([]);
		const reread = new AckStore(root).readAll();
		expect(reread.has("t-done")).toBe(true);
		expect(reread.has("t-fail")).toBe(true);
		expect(reread.get("t-fail")).toMatch(/^\d{4}-\d{2}-\d{2}T/); // ISO timestamp

		// Running row: rejected, nothing written.
		const bad = await ackTasks(store, ackStore, ["t-run"]);
		expect(bad.acked).toEqual([]);
		expect(bad.rejected[0]?.key).toBe("t-run");
		expect(bad.rejected[0]?.reason).toContain("not terminal");
		expect(new AckStore(root).readAll().has("t-run")).toBe(false);

		// Unknown key: rejected.
		const ghost = await ackTasks(store, ackStore, ["no-such-task"]);
		expect(ghost.rejected[0]?.reason).toContain("no such task");

		// "all" after both were acked: nothing unacked remains, then a new
		// terminal row is covered.
		const all = await ackTasks(store, new AckStore(root), "all");
		expect(all.acked).toEqual([]);
		await terminalRow(root, "t-nc", "needs-clarification");
		const all2 = await ackTasks(store, new AckStore(root), "all");
		expect(all2.acked).toEqual(["t-nc"]);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-004: /mw ack writes the sidecar and reports rejections", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const ackStore = new AckStore(root);
		await terminalRow(root, "t-fail", "failed");
		await terminalRow(root, "t-run", "running");
		const { pi, commands } = fakeCmdPi();
		registerMwCommands(pi, root, store, ackStore);
		const handler = commands.get("mw");
		if (!handler) throw new Error("mw command not registered");
		const { ctx, notifications } = fakeCmdCtx();

		await handler("ack t-fail", ctx);
		expect(notifications.some((n) => n.includes("Acked 1 task") && n.includes("t-fail"))).toBe(true);
		expect(new AckStore(root).readAll().has("t-fail")).toBe(true);

		await handler("ack t-run", ctx);
		expect(notifications.some((n) => n.includes("Not acked: t-run") && n.includes("not terminal"))).toBe(true);
		expect(new AckStore(root).readAll().has("t-run")).toBe(false);

		await handler("ack all", ctx);
		const all = new AckStore(root).readAll();
		expect(all.has("t-fail")).toBe(true);
		expect(all.has("t-run")).toBe(false);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-005: ack_worker_result tool registered in PM mode, absent in worker mode", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		const { pi, tools } = fakeCmdPi();
		registerWorkerTools(pi, store, new AckStore(root), is, root, { key: undefined });
		expect(tools.has("ack_worker_result")).toBe(true);

		// Worker mode (PI_WORKER_TASK set) registers no tools at all — the
		// ack tool can never reach a worker.
		const workerTools: string[] = [];
		const workerPi = {
			on: () => {},
			registerTool: (t: { name: string }) => {
				workerTools.push(t.name);
			},
			sendUserMessage: () => {},
		} as unknown as ExtensionAPI;
		const taskDir = path.join(root, "key-a", "workers", "w1");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
		process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
		process.env.PI_WORKER_IDLE_MS = "60000";
		try {
			await workerModeActivate(workerPi);
			expect(workerTools.includes("ack_worker_result")).toBe(false);
		} finally {
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-005: ack_worker_result tool acks and reports like /mw ack", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const ackStore = new AckStore(root);
		await terminalRow(root, "t-nc", "needs-clarification");
		await terminalRow(root, "t-run", "running");
		const { pi, tools } = fakeCmdPi();
		registerWorkerTools(pi, store, ackStore, new IndexStore(root), root, { key: undefined });
		const tool = tools.get("ack_worker_result");
		if (!tool) throw new Error("ack_worker_result not registered");

		const res1 = await tool.execute("id", { task_key: "t-nc" }, undefined, undefined, {} as ExtensionContext);
		expect(res1.content[0]?.type === "text" && res1.content[0].text.includes("Acked 1 task(s): t-nc")).toBe(true);
		expect(new AckStore(root).readAll().has("t-nc")).toBe(true);

		const res2 = await tool.execute("id", { task_key: "t-run" }, undefined, undefined, {} as ExtensionContext);
		const text2 = res2.content[0]?.type === "text" ? res2.content[0].text : "";
		expect(text2.includes("NOT acked: t-run")).toBe(true);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-006: ack never touches queue statuses and never triggers re-dispatch", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const ackStore = new AckStore(root);
		writePhaseDocs(root, "key-a");
		await terminalRow(root, "t-done", "done");
		const before = store.readAll().map((e) => `${e.taskKey}:${e.status}`);

		await ackTasks(store, ackStore, ["t-done"]);
		// Status columns are byte-identical after ack.
		expect(store.readAll().map((e) => `${e.taskKey}:${e.status}`)).toEqual(before);

		// agent_settled-style dispatch scan: the row's task.md still exists, but
		// the queue already owns the row — no duplicate pending dispatch.
		await dispatchNewTasks(store, root);
		const rows = store.readAll();
		expect(rows.filter((e) => e.taskKey === "t-done")).toHaveLength(1);
		expect(rows.find((e) => e.taskKey === "t-done")?.status).toBe("done");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-010: terminal readbacks carry the ack directive; VC-011: list_tasks badges acked rows", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const ackStore = new AckStore(root);
		await terminalRow(root, "t-new", "pending");
		await terminalRow(root, "t-old", "failed");
		await ackStore.ack(["t-old"]);

		// VC-010: the finish-call message (PM_CONTINUE_HINT) directs the PM to ack.
		// The readback fires only on transitions observed by the loop — seed a
		// pending row and flip it to done mid-loop.
		const watch: PmWatchState = { key: "key-a" };
		const ui: PmUiHolder = { ctx: undefined };
		vi.useFakeTimers();
		try {
			const { pi, sent } = fakeCmdPi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), new IndexStore(root), root, watch, ui, 100);
			vi.advanceTimersByTime(150); // baseline snapshot: t-new still pending
			const entry = store.findByKey("t-new");
			if (!entry) throw new Error("t-new missing");
			await store.upsert({ ...entry, status: "done" });
			vi.advanceTimersByTime(150);
			clearInterval(handle);
			const withHint = sent.map((s) => s.content).find((m) => m.includes("ack_worker_result"));
			expect(withHint).toBeDefined();
			expect(withHint).toContain("/mw ack all");
		} finally {
			vi.useRealTimers();
		}

		// VC-011: list_tasks output — acked terminal row badged, unacked not.
		const { pi, tools } = fakeCmdPi();
		registerWorkerTools(pi, store, ackStore, new IndexStore(root), root, { key: undefined });
		const list = tools.get("list_tasks");
		if (!list) throw new Error("list_tasks not registered");
		const res = await list.execute("id", {}, undefined, undefined, {} as ExtensionContext);
		const text = res.content[0]?.type === "text" ? res.content[0].text : "";
		const oldLine = text.split("\n").find((l) => l.startsWith("t-old"));
		const newLine = text.split("\n").find((l) => l.startsWith("t-new"));
		expect(oldLine).toContain("| acked");
		expect(newLine).not.toContain("acked");
		console.log("[VERIFY] VC-004: persist=yes, non_terminal_rejected=yes, all=yes");
		console.log("[VERIFY] VC-005: tool_registered=yes, worker_mode_absent=yes");
		console.log("[VERIFY] VC-006: status_unchanged=yes, no_redispatch=yes");
		console.log("[VERIFY] VC-010: hint=ack_worker_result-present");
		console.log("[VERIFY] VC-011: badge=acked-present");
		fs.rmSync(root, { recursive: true, force: true });
	});
});

describe("terminal readback (AC-014 / VC-020)", () => {
	function fakePi(): {
		pi: ExtensionAPI;
		messages: string[];
		options: Array<{ triggerTurn?: boolean } | undefined>;
	} {
		const messages: string[] = [];
		const options: Array<{ triggerTurn?: boolean } | undefined> = [];
		const pi = {
			sendMessage: (m: { content: string }, opts?: { triggerTurn?: boolean }) => {
				messages.push(m.content);
				options.push(opts);
			},
		} as unknown as ExtensionAPI;
		return { pi, messages, options };
	}

	it("VC-020: terminal message readbacks the full output.md body, capped at 20k with a pointer", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await is.upsert({
			key: "key-a",
			status: "active",
			phase: "EXECUTE",
			claimId: "1",
			deps: "",
			desc: "",
			updated: new Date().toISOString(),
		});
		const taskDirFull = path.join(root, "key-a", "workers", "t-full");
		fs.mkdirSync(taskDirFull, { recursive: true });
		fs.writeFileSync(path.join(taskDirFull, "task.md"), "type: coding\n\nwork\n", "utf8");
		fs.writeFileSync(
			path.join(taskDirFull, "output.md"),
			"## Summary\n\ndid the thing\n\n## Findings\n\n- one\n- two\n",
			"utf8",
		);
		await store.upsert({
			taskKey: "t-full",
			status: "pending",
			cli: "pi",
			provider: "timi",
			taskPath: path.join(taskDirFull, "task.md"),
			dispatchedAt: "",
			updatedAt: "",
			model: "",
		});

		// Over-cap body: 25k chars -> truncated with a "full report:" pointer.
		const taskDirBig = path.join(root, "key-a", "workers", "t-big");
		fs.mkdirSync(taskDirBig, { recursive: true });
		fs.writeFileSync(path.join(taskDirBig, "task.md"), "type: coding\n\nwork\n", "utf8");
		fs.writeFileSync(path.join(taskDirBig, "output.md"), `## Summary\n\n${"x".repeat(25_000)}\n`, "utf8");
		await store.upsert({
			taskKey: "t-big",
			status: "pending",
			cli: "pi",
			provider: "timi",
			taskPath: path.join(taskDirBig, "task.md"),
			dispatchedAt: "",
			updatedAt: "",
			model: "",
		});

		const watch: PmWatchState = { key: "key-a" };
		const ui: PmUiHolder = { ctx: undefined };
		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			for (const key of ["t-full", "t-big"]) {
				const entry = store.findByKey(key);
				if (!entry) throw new Error(`${key} missing from queue`);
				await store.upsert({ ...entry, status: "done" });
			}
			vi.advanceTimersByTime(500);
			expect(messages).toHaveLength(2);

			const full = messages.find((m) => m.includes("[t-full] done"));
			expect(full).toContain("[t-full] done:");
			// Full body injected — sections beyond the Summary excerpt included.
			expect(full).toContain("## Findings");
			expect(full).toContain("- two");

			const big = messages.find((m) => m.includes("[t-big] done"));
			expect(big).toContain("full report:");
			expect(big?.length ?? 0).toBeLessThan(25_000);
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});
});

describe("pm-key takeover claims", () => {
	/** Command ctx capturing notifications and widget renders. */
	/** Spawn a short-lived child and wait until its pid is observable. */
	function spawnLivePid(): Promise<{ pid: number; done: Promise<void> }> {
		const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 15000)"]);
		if (child.pid === undefined) throw new Error("spawn failed");
		return new Promise((resolve) => {
			child.on("spawn", () => {
				const done = new Promise<void>((res) => {
					child.on("exit", () => res());
				});
				resolve({ pid: child.pid as number, done });
			});
			// Fallback if the spawn event never fires
			setTimeout(() => {
				const done = new Promise<void>((res) => {
					child.on("exit", () => res());
				});
				resolve({ pid: child.pid as number, done });
			}, 500);
		});
	}

	it("classifies claims: empty/self/legacy are free, live and foreign pids held", async () => {
		const self = windowClaimId();
		expect(claimState("", self)).toBe("free");
		expect(claimState(self, self)).toBe("free");
		// Legacy timestamp claims (pre-takeover format) are stale.
		expect(claimState("20260808-142655-3496", self)).toBe("free");
		// Foreign host — liveness unverifiable, treated as held.
		expect(claimState("other-host:12345", self)).toBe("held-live");

		const live = await spawnLivePid();
		try {
			expect(claimState(`${os.hostname()}:${live.pid}`, self)).toBe("held-live");
		} finally {
			process.kill(live.pid);
			await live.done;
		}
		// After the process exits the same-host claim is stale.
		expect(claimState(`${os.hostname()}:${live.pid}`, self)).toBe("held-stale");
	}, 20000);

	it("switch refuses a live foreign claim without --force and takes over with it", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		const live = await spawnLivePid();
		const otherClaim = `${os.hostname()}:${live.pid}`;
		await seedKey(root, "key-a", otherClaim);
		await seedKey(root, "key-b", "", "active");
		const { pi, commands, entries } = fakeCmdPi();
		const watch: PmWatchState = { key: undefined };
		const refresh = (_ctx: ExtensionContext): void => {};
		registerPmKeyCommands(pi, is, watch, refresh, root);
		const handler = commands.get("pm-key");
		if (!handler) throw new Error("pm-key not registered");

		const blocked = fakeCmdCtx();
		await handler("switch key-a", blocked.ctx);
		expect(blocked.notifications.some((n) => n.includes("claimed by another live window"))).toBe(true);
		expect(is.findByKey("key-a")?.claimId).toBe(otherClaim); // untouched
		expect(watch.key).toBeUndefined();
		expect(entries).toHaveLength(0);

		const forced = fakeCmdCtx();
		await handler("switch key-a --force", forced.ctx);
		expect(is.findByKey("key-a")?.claimId).toBe(windowClaimId());
		expect(is.findByKey("key-a")?.status).toBe("active");
		expect(is.findByKey("key-b")?.status).toBe("idle"); // others marked idle
		expect(watch.key).toBe("key-a");
		expect(entries.at(-1)?.data).toEqual({ key: "key-a", claimed: true });

		process.kill(live.pid);
		await live.done;
		fs.rmSync(root, { recursive: true, force: true });
	}, 20000);

	it("switch silently takes over stale claims and /pm-key new refuses duplicates", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		await seedKey(root, "key-a", "20260808-142655-3496"); // legacy = stale
		const { pi, commands } = fakeCmdPi();
		const watch: PmWatchState = { key: undefined };
		const refresh = (_ctx: ExtensionContext): void => {};
		registerPmKeyCommands(pi, is, watch, refresh, root);
		const handler = commands.get("pm-key");
		if (!handler) throw new Error("pm-key not registered");

		const stale = fakeCmdCtx();
		await handler("switch key-a", stale.ctx);
		expect(is.findByKey("key-a")?.claimId).toBe(windowClaimId());
		expect(watch.key).toBe("key-a");

		const dup = fakeCmdCtx();
		await handler("new key-a", dup.ctx);
		expect(dup.notifications.some((n) => n.includes("already exists"))).toBe(true);

		const fresh = fakeCmdCtx();
		await handler("new key-c", fresh.ctx);
		expect(is.findByKey("key-c")?.claimId).toBe(windowClaimId());
		expect(watch.key).toBe("key-c");
		// m2: /pm-key new routes through the atomic claim — the previously
		// active key is demoted instead of silently creating a second active row.
		expect(is.findByKey("key-a")?.status).toBe("idle");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("restoreWatch re-claims a stale claim and defers to a live one", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		const ws = new WorkerStore(root);

		// Stale claim (an already-exited child's pid) — quiet re-claim.
		const dead = await spawnLivePid();
		process.kill(dead.pid);
		await dead.done;
		await seedKey(root, "key-a", `${os.hostname()}:${dead.pid}`);
		await seedKey(root, "key-x", ""); // another window's active row
		const watch: PmWatchState = { key: undefined };
		const entries1 = [{ type: "custom", customType: "agent-team-loop:watch", data: { key: "key-a", claimed: true } }];
		const fake1 = {
			hasUI: true,
			ui: {
				notify: (_m: string) => {},
				setWidget: (_k: string, _c: string[] | undefined) => {},
			},
			sessionManager: { getEntries: () => entries1 },
		} as unknown as ExtensionContext;
		const pi = { appendEntry: (_t: string, _d: unknown) => {} } as unknown as ExtensionAPI;
		await restoreWatch(pi, watch, is, ws, new AckStore(root), root, fake1);
		expect(watch.key).toBe("key-a");
		expect(is.findByKey("key-a")?.claimId).toBe(windowClaimId());
		// M2: the quiet re-claim spares other active rows (no global demote —
		// that is switch's explicit takeover) and keeps the target row's status.
		expect(is.findByKey("key-x")?.status).toBe("active");
		expect(is.findByKey("key-a")?.status).toBe("active");

		// Live foreign claim — watch-only, shared row untouched.
		const live = await spawnLivePid();
		try {
			await seedKey(root, "key-b", `${os.hostname()}:${live.pid}`);
			const watch2: PmWatchState = { key: undefined };
			const notes: string[] = [];
			const entries2 = [
				{ type: "custom", customType: "agent-team-loop:watch", data: { key: "key-b", claimed: true } },
			];
			const fake2 = {
				hasUI: true,
				ui: {
					notify: (m: string) => {
						notes.push(m);
					},
					setWidget: (_k: string, _c: string[] | undefined) => {},
				},
				sessionManager: { getEntries: () => entries2 },
			} as unknown as ExtensionContext;
			await restoreWatch(pi, watch2, is, ws, new AckStore(root), root, fake2);
			expect(watch2.key).toBe("key-b");
			expect(is.findByKey("key-b")?.claimId).toBe(`${os.hostname()}:${live.pid}`);
			expect(notes.some((n) => n.includes("watching only"))).toBe(true);
		} finally {
			process.kill(live.pid);
			await live.done;
		}
		fs.rmSync(root, { recursive: true, force: true });
	}, 20000);

	it("keyFromDocWrite matches {key}/spec|design|plan.md writes and edits", () => {
		const project = mkdtemp();
		const agentic = path.join(project, ".agenticdoc");
		fs.mkdirSync(agentic, { recursive: true });

		// Relative (cwd-style) and absolute paths both resolve; all three phase docs.
		for (const doc of ["spec.md", "design.md", "plan.md"]) {
			expect(keyFromDocWrite("write", { path: path.join(".agenticdoc", "key-a", doc) }, project, agentic)).toBe(
				"key-a",
			);
			expect(keyFromDocWrite("edit", { path: path.join(agentic, "key-a", doc) }, project, agentic)).toBe("key-a");
		}

		// Non-doc files, nested paths, root-level files, reserved dirs, other
		// tools, and paths outside .agenticdoc never trigger.
		expect(
			keyFromDocWrite("write", { path: path.join(agentic, "key-a", "tasks.md") }, project, agentic),
		).toBeUndefined();
		expect(
			keyFromDocWrite("write", { path: path.join(agentic, "key-a", "workers", "t1", "spec.md") }, project, agentic),
		).toBeUndefined();
		expect(keyFromDocWrite("write", { path: path.join(agentic, "spec.md") }, project, agentic)).toBeUndefined();
		expect(
			keyFromDocWrite("write", { path: path.join(agentic, "_scratch", "spec.md") }, project, agentic),
		).toBeUndefined();
		expect(
			keyFromDocWrite("write", { path: path.join(project, "src", "spec.md") }, project, agentic),
		).toBeUndefined();
		expect(
			keyFromDocWrite("read", { path: path.join(agentic, "key-a", "spec.md") }, project, agentic),
		).toBeUndefined();
		expect(keyFromDocWrite("write", {}, project, agentic)).toBeUndefined();
		fs.rmSync(project, { recursive: true, force: true });
	});

	it("autoTakeOverFromDoc registers fresh keys, is idempotent, defers to live claims", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		const { pi, entries } = fakeCmdPi();
		const watch: PmWatchState = { key: undefined };
		const refresh = (_ctx: ExtensionContext): void => {};
		await seedKey(root, "key-other", "", "active");

		// Fresh key: row auto-created + claimed + watched; other active keys idle.
		const c1 = fakeCmdCtx();
		await autoTakeOverFromDoc(pi, is, watch, refresh, "key-new", "spec.md", root, c1.ctx);
		const row = is.findByKey("key-new");
		expect(row?.claimId).toBe(windowClaimId());
		expect(row?.status).toBe("active");
		expect(row?.phase).toBe("SPEC");
		expect(is.findByKey("key-other")?.status).toBe("idle");
		expect(watch.key).toBe("key-new");
		expect(entries.at(-1)?.data).toEqual({ key: "key-new", claimed: true });
		expect(c1.notifications.some((n) => n.includes("claimed key 'key-new'"))).toBe(true);
		// Idempotent: already watching + our claim → no repeated takeover notify/entry
		// (the missing-evidence warning below is independent of idempotency).
		const before = entries.length;
		const c2 = fakeCmdCtx();
		await autoTakeOverFromDoc(pi, is, watch, refresh, "key-new", "spec.md", root, c2.ctx);
		expect(entries.length).toBe(before);
		expect(c2.notifications.filter((n) => n.includes("claimed key"))).toHaveLength(0);
		// spec.md written without research notes → symmetric evidence warning.
		expect(c2.notifications.some((n) => n.includes("evidence/research/spec-*.md"))).toBe(true);

		// Live foreign claim → watch-only, shared row untouched.
		const live = await spawnLivePid();
		try {
			await seedKey(root, "key-b", `${os.hostname()}:${live.pid}`);
			const watch2: PmWatchState = { key: undefined };
			const c3 = fakeCmdCtx();
			await autoTakeOverFromDoc(pi, is, watch2, refresh, "key-b", "spec.md", root, c3.ctx);
			expect(watch2.key).toBe("key-b");
			expect(is.findByKey("key-b")?.claimId).toBe(`${os.hostname()}:${live.pid}`);
			expect(c3.notifications.some((n) => n.includes("watching only"))).toBe(true);
		} finally {
			process.kill(live.pid);
			await live.done;
		}
		fs.rmSync(root, { recursive: true, force: true });
	}, 20000);

	it("switch_key tool takes over, blocks on live claims, and forces with confirmation semantics", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		const { pi, tools, entries } = fakeCmdPi();
		const watch: PmWatchState = { key: undefined };
		const refreshes: number[] = [];
		const refresh = (_ctx: ExtensionContext): void => {
			refreshes.push(1);
		};
		registerSwitchKeyTool(pi, is, watch, refresh, root);
		const tool = tools.get("switch_key");
		if (!tool) throw new Error("switch_key not registered");

		// Fresh takeover: auto-registers the key, watches it, persists, refreshes.
		const r1 = await tool.execute("id1", { key: "tool-key" }, undefined, undefined, fakeCmdCtx().ctx);
		expect(r1.content[0]?.text).toContain("Took over key 'tool-key'");
		expect(is.findByKey("tool-key")?.claimId).toBe(windowClaimId());
		expect(watch.key).toBe("tool-key");
		expect(entries.at(-1)?.data).toEqual({ key: "tool-key", claimed: true });
		expect(refreshes.length).toBe(1);

		// Live foreign claim: blocked without force, watch untouched.
		const live = await spawnLivePid();
		try {
			await seedKey(root, "held-key", `${os.hostname()}:${live.pid}`);
			const watch2: PmWatchState = { key: undefined };
			registerSwitchKeyTool(pi, is, watch2, refresh, root);
			const tool2 = tools.get("switch_key");
			if (!tool2) throw new Error("switch_key missing");
			const blocked = await tool2.execute("id2", { key: "held-key" }, undefined, undefined, fakeCmdCtx().ctx);
			expect(blocked.content[0]?.text).toContain("claimed by another live window");
			expect(is.findByKey("held-key")?.claimId).toBe(`${os.hostname()}:${live.pid}`);
			expect(watch2.key).toBeUndefined();

			// force=true steals the claim.
			const forced = await tool2.execute(
				"id3",
				{ key: "held-key", force: true },
				undefined,
				undefined,
				fakeCmdCtx().ctx,
			);
			expect(forced.content[0]?.text).toContain("Took over key 'held-key'");
			expect(is.findByKey("held-key")?.claimId).toBe(windowClaimId());
			expect(watch2.key).toBe("held-key");
		} finally {
			process.kill(live.pid);
			await live.done;
		}
		fs.rmSync(root, { recursive: true, force: true });
	}, 20000);

	it("dispatch_worker refuses undocumented keys, allows _scratch and documented keys", async () => {
		const root = mkdtemp();
		const ws = new WorkerStore(root);
		const is = new IndexStore(root);
		const { pi, tools } = fakeCmdPi();
		registerWorkerTools(pi, ws, new AckStore(root), is, root, { key: undefined });
		const tool = tools.get("dispatch_worker");
		if (!tool) throw new Error("dispatch_worker not registered");

		// Undocumented key: refused with actionable gaps; nothing is created.
		const r1 = await tool.execute(
			"id1",
			{ task_key: "t1", description: "work", key: "undoc" },
			undefined,
			undefined,
			fakeCmdCtx().ctx,
		);
		expect(r1.content[0]?.text).toContain("Worker dispatch blocked");
		expect(r1.content[0]?.text).toContain("evidence/research/spec-*.md");
		expect(fs.existsSync(path.join(root, "undoc", "workers", "t1"))).toBe(false);
		expect(ws.readAll()).toHaveLength(0);

		// _scratch: the ad-hoc escape hatch, no docs needed.
		const r2 = await tool.execute(
			"id2",
			{ task_key: "t2", description: "work", key: "_scratch" },
			undefined,
			undefined,
			fakeCmdCtx().ctx,
		);
		expect(r2.content[0]?.text).toContain("Dispatched worker 't2'");
		expect(ws.findByKey("t2")?.status).toBe("pending");

		// Fully documented key: dispatches.
		writePhaseDocs(root, "doc-key");
		const r3 = await tool.execute(
			"id3",
			{ task_key: "t3", description: "work", key: "doc-key" },
			undefined,
			undefined,
			fakeCmdCtx().ctx,
		);
		expect(r3.content[0]?.text).toContain("Dispatched worker 't3'");
		expect(ws.findByKey("t3")?.status).toBe("pending");

		// VC-010: explicit cli=claude still routes to claude (task.md gets the
		// review type field, queue row keeps cli=claude, provider stays empty).
		const r4 = await tool.execute(
			"id4",
			{ task_key: "t4", description: "work", cli: "claude", key: "_scratch" },
			undefined,
			undefined,
			fakeCmdCtx().ctx,
		);
		expect(r4.content[0]?.text).toContain("Dispatched worker 't4'");
		expect(ws.findByKey("t4")?.cli).toBe("claude");
		expect(ws.findByKey("t4")?.provider).toBe("");
		const t4md = fs.readFileSync(path.join(root, "_scratch", "workers", "t4", "task.md"), "utf8");
		expect(t4md).toContain("type: review");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("autoTakeOverFromDoc warns about missing phase evidence on design/plan writes", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		const { pi } = fakeCmdPi();
		const watch: PmWatchState = { key: undefined };
		const refresh = (_ctx: ExtensionContext): void => {};

		// design.md write without spec evidence → warning (advance-to-design gate).
		const c1 = fakeCmdCtx();
		await autoTakeOverFromDoc(pi, is, watch, refresh, "key-d", "design.md", root, c1.ctx);
		expect(c1.notifications.some((n) => n.includes("evidence/research/spec-*.md"))).toBe(true);

		// plan.md write without design docs → warning (advance-to-plan gate).
		const c2 = fakeCmdCtx();
		await autoTakeOverFromDoc(pi, is, watch, refresh, "key-p", "plan.md", root, c2.ctx);
		expect(c2.notifications.some((n) => n.includes("design.md missing"))).toBe(true);

		// Fully documented key: no evidence warnings on design/plan writes.
		writePhaseDocs(root, "key-ok");
		const c3 = fakeCmdCtx();
		await autoTakeOverFromDoc(pi, is, watch, refresh, "key-ok", "design.md", root, c3.ctx);
		const c4 = fakeCmdCtx();
		await autoTakeOverFromDoc(pi, is, watch, refresh, "key-ok", "plan.md", root, c4.ctx);
		expect(c3.notifications.filter((n) => n.includes("evidence/research"))).toHaveLength(0);
		expect(c4.notifications.filter((n) => n.includes("evidence/research"))).toHaveLength(0);
		fs.rmSync(root, { recursive: true, force: true });
	});
	it("docFromWrite reports which phase doc was written", () => {
		const project = mkdtemp();
		const agentic = path.join(project, ".agenticdoc");
		fs.mkdirSync(agentic, { recursive: true });
		expect(docFromWrite("write", { path: path.join(agentic, "key-a", "design.md") }, project, agentic)).toBe(
			"design.md",
		);
		expect(
			docFromWrite("write", { path: path.join(agentic, "key-a", "tasks.md") }, project, agentic),
		).toBeUndefined();
		fs.rmSync(project, { recursive: true, force: true });
	});

	it("evidencePhaseFromWrite matches research-note writes only", () => {
		const project = mkdtemp();
		const agentic = path.join(project, ".agenticdoc");
		fs.mkdirSync(agentic, { recursive: true });
		const note = (p: string): string => path.join(agentic, p);
		expect(
			evidencePhaseFromWrite(
				"write",
				{ path: note("key-a/evidence/research/spec-topic-2026-01-01.md") },
				project,
				agentic,
			),
		).toEqual({ key: "key-a", phase: "spec" });
		expect(
			evidencePhaseFromWrite("edit", { path: note("key-a/evidence/research/design-x.md") }, project, agentic),
		).toEqual({ key: "key-a", phase: "design" });
		// Wrong depth / dirs / prefix / extension / reserved keys / other tools.
		expect(
			evidencePhaseFromWrite("write", { path: note("key-a/evidence/spec-x.md") }, project, agentic),
		).toBeUndefined();
		expect(
			evidencePhaseFromWrite("write", { path: note("key-a/research/spec-x.md") }, project, agentic),
		).toBeUndefined();
		expect(
			evidencePhaseFromWrite("write", { path: note("key-a/evidence/research/notes.md") }, project, agentic),
		).toBeUndefined();
		expect(
			evidencePhaseFromWrite("write", { path: note("key-a/evidence/research/spec-x.txt") }, project, agentic),
		).toBeUndefined();
		expect(
			evidencePhaseFromWrite("write", { path: note("_scratch/evidence/research/spec-x.md") }, project, agentic),
		).toBeUndefined();
		expect(
			evidencePhaseFromWrite("read", { path: note("key-a/evidence/research/spec-x.md") }, project, agentic),
		).toBeUndefined();
		fs.rmSync(project, { recursive: true, force: true });
	});

	it("nudgeEvidenceReview fires once when doc + evidence coexist, with the checklist", () => {
		const root = mkdtemp();
		const { pi, messages } = fakeCmdPi();
		const nudged = new Set<string>();

		// Evidence alone (no phase doc yet) — review needs both sides.
		fs.mkdirSync(path.join(root, "k", "evidence", "research"), { recursive: true });
		fs.writeFileSync(path.join(root, "k", "evidence", "research", "spec-x.md"), "n", "utf8");
		nudgeEvidenceReview(pi, "k", "spec", root, nudged);
		expect(messages).toHaveLength(0);

		// Phase doc present: nudge fires once, then dedups within the session.
		writePhaseDocs(root, "k");
		nudgeEvidenceReview(pi, "k", "spec", root, nudged);
		expect(messages).toHaveLength(1);
		expect(messages[0]).toContain("证据复查");
		expect(messages[0]).toContain("断言-证据对照");
		expect(messages[0]).toContain("spec.md");
		nudgeEvidenceReview(pi, "k", "spec", root, nudged);
		expect(messages).toHaveLength(1);

		// Design phase is tracked independently with its own checklist.
		nudgeEvidenceReview(pi, "k", "design", root, nudged);
		expect(messages).toHaveLength(2);
		expect(messages[1]).toContain("复用≠零成本");
		expect(messages[1]).toContain("design.md");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("nudgeGoalUnestablished is skipped headless and for established goals", () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
		const { pi, messages } = fakeCmdPi();

		// No goal.md + headless (print/-p): the nudge would start a generation
		// that collides with the queued -p prompt — must be skipped.
		nudgeGoalUnestablished(pi, root, false);
		expect(messages).toHaveLength(0);

		// No goal.md + UI: the nudge fires.
		nudgeGoalUnestablished(pi, root, true);
		expect(messages).toHaveLength(1);
		expect(messages[0]).toContain("尚未确立");

		// Established goal (status active): no nudge even with UI.
		fs.writeFileSync(path.join(root, "goal.md"), "status: active\n\n## Goal\n\nShip it.\n", "utf8");
		nudgeGoalUnestablished(pi, root, true);
		expect(messages).toHaveLength(1);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("nudgeEvidenceReview queues as followUp — it fires mid-run from tool-write events", () => {
		const root = mkdtemp();
		const calls: Array<{ content: string; options?: { deliverAs?: string } }> = [];
		const pi = {
			sendUserMessage: (content: string, options?: { deliverAs?: string }) => {
				calls.push({ content, options });
			},
		} as unknown as ExtensionAPI;
		fs.mkdirSync(path.join(root, "k", "evidence", "research"), { recursive: true });
		fs.writeFileSync(path.join(root, "k", "evidence", "research", "spec-x.md"), "n", "utf8");
		writePhaseDocs(root, "k");

		nudgeEvidenceReview(pi, "k", "spec", root, new Set<string>());
		expect(calls).toHaveLength(1);
		expect(calls[0].options?.deliverAs).toBe("followUp");
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── Watchdog budgets + convergence checkpoint (mw-worker-timeout-convergence) ─

describe("watchdog budgets and convergence checkpoint", () => {
	function fakePi(): {
		pi: ExtensionAPI;
		messages: string[];
		options: Array<{ triggerTurn?: boolean } | undefined>;
	} {
		const messages: string[] = [];
		const options: Array<{ triggerTurn?: boolean } | undefined> = [];
		const pi = {
			sendMessage: (m: { content: string }, opts?: { triggerTurn?: boolean }) => {
				messages.push(m.content);
				options.push(opts);
			},
		} as unknown as ExtensionAPI;
		return { pi, messages, options };
	}

	async function queueRunning(root: string, key: string, taskKey: string): Promise<void> {
		const taskDir = path.join(root, key, "workers", taskKey);
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
		await new WorkerStore(root).upsert({
			taskKey,
			status: "running",
			cli: "pi",
			provider: "timi",
			taskPath: path.join(taskDir, "task.md"),
			dispatchedAt: "",
			updatedAt: "",
			model: "",
		});
	}

	it("AC-002: resolveBudgetMs precedence task.md > PI_WORKER_TIMEOUT_MS > 60m default", () => {
		expect(resolveBudgetMs(15, "120000")).toBe(15 * 60_000); // task.md wins
		expect(resolveBudgetMs(undefined, "120000")).toBe(120_000); // env
		expect(resolveBudgetMs(undefined, undefined)).toBe(DEFAULT_BUDGET_MS);
		expect(DEFAULT_BUDGET_MS).toBe(60 * 60_000); // GC-4 as amended: 60m wall backstop
		// Junk env values fall through to the default, never NaN/0.
		expect(resolveBudgetMs(undefined, "abc")).toBe(DEFAULT_BUDGET_MS);
		expect(resolveBudgetMs(undefined, "0")).toBe(DEFAULT_BUDGET_MS);
		expect(resolveBudgetMs(undefined, "-5")).toBe(DEFAULT_BUDGET_MS);
	});

	it("AC-001: resolveIdleMs honors PI_WORKER_IDLE_MS and rejects junk", () => {
		expect(resolveIdleMs("25000")).toBe(25_000);
		expect(resolveIdleMs(undefined)).toBe(DEFAULT_IDLE_MS);
		expect(DEFAULT_IDLE_MS).toBe(10 * 60_000); // above the 7m legit single-generation
		expect(resolveIdleMs("abc")).toBe(DEFAULT_IDLE_MS);
		expect(resolveIdleMs("0")).toBe(DEFAULT_IDLE_MS);
	});

	it("AC-002/D-004: checkpoint anchor and steer times scale with budget", () => {
		// Default 60m budget: the user's 30m convergence anchor, steer at 55m.
		expect(checkpointAnchorMs(60 * 60_000)).toBe(30 * 60_000);
		expect(steerAtMs(60 * 60_000)).toBe(55 * 60_000);
		// Small smoke budget: proportional anchor (1m) and steer (90s).
		expect(checkpointAnchorMs(2 * 60_000)).toBe(60_000);
		expect(steerAtMs(2 * 60_000)).toBe(90_000);
		// Anchor never exceeds 30m even for huge budgets.
		expect(checkpointAnchorMs(6 * 60 * 60_000)).toBe(30 * 60_000);
	});

	it("AC-002: parseTaskMd reads the timeout: header (minutes); junk is ignored", () => {
		const root = mkdtemp();
		const taskDir = path.join(root, "key-a", "workers", "t-budget");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\ntimeout: 15\n\nwork\n", "utf8");
		const meta = parseTaskMd(path.join(taskDir, "task.md"));
		expect(meta.timeoutMin).toBe(15);
		expect(meta.taskKey).toBe("t-budget");
		expect(meta.agenticdocRoot).toBe(path.join(root, "key-a", "workers"));

		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\ntimeout: 0\ntimeout: abc\n\nwork\n", "utf8");
		expect(parseTaskMd(path.join(taskDir, "task.md")).timeoutMin).toBeUndefined();
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-004: computeRisk — high (zero writes past anchor), mid (stalled phases / repeat reads), low (writes advancing)", () => {
		const anchor = 30 * 60_000;
		// cpr-007 pattern: 30m+ of reads, zero writes.
		expect(
			computeRisk({
				elapsedMs: 32 * 60_000,
				anchorMs: anchor,
				writes: 0,
				phasesTotal: 0,
				phasesDone: 0,
				repeatTop: 1,
			}),
		).toBe("high");
		// Phase framework present but nothing completed past the anchor.
		expect(
			computeRisk({
				elapsedMs: 31 * 60_000,
				anchorMs: anchor,
				writes: 3,
				phasesTotal: 4,
				phasesDone: 0,
				repeatTop: 1,
			}),
		).toBe("mid");
		// Same target read 4+ times — spinning.
		expect(
			computeRisk({
				elapsedMs: 5 * 60_000,
				anchorMs: anchor,
				writes: 2,
				phasesTotal: 3,
				phasesDone: 1,
				repeatTop: 4,
			}),
		).toBe("mid");
		// Writes advancing before the anchor — still warming up, not divergence.
		expect(
			computeRisk({
				elapsedMs: 20 * 60_000,
				anchorMs: anchor,
				writes: 0,
				phasesTotal: 0,
				phasesDone: 0,
				repeatTop: 0,
			}),
		).toBe("low");
		// Implementation underway.
		expect(
			computeRisk({
				elapsedMs: 35 * 60_000,
				anchorMs: anchor,
				writes: 9,
				phasesTotal: 3,
				phasesDone: 1,
				repeatTop: 2,
			}),
		).toBe("low");
	});

	it("AC-004: appendCheckpoint writes the structured line; readTaskProgress parses it, last one wins", () => {
		const root = mkdtemp();
		const key = "task-ckpt";
		makeTaskDir(root, key);
		appendCheckpoint(key, root, {
			elapsedMs: 30 * 60_000,
			reads: 74,
			writes: 0,
			phases: "-",
			uniqTargets: 0,
			repeatTop: 3,
			risk: "high",
		});
		appendCheckpoint(key, root, {
			elapsedMs: 40 * 60_000,
			reads: 80,
			writes: 6,
			phases: "1/2",
			uniqTargets: 4,
			repeatTop: 3,
			risk: "low",
		});
		const trace = fs.readFileSync(path.join(root, key, "trace.log"), "utf8");
		expect(trace).toMatch(
			/^\[CHECKPOINT\] \S+ elapsed=1800s reads=74 writes=0 phases=- uniq_targets=0 repeat_top=3 risk=high$/m,
		);
		const ck = readTaskProgress(path.join(root, key))?.checkpoint;
		expect(ck?.risk).toBe("low"); // last checkpoint wins
		expect(ck?.elapsedS).toBe(2400);
		expect(ck?.reads).toBe(80);
		expect(ck?.writes).toBe(6);
		expect(ck?.phases).toBe("1/2");
		expect(ck?.uniqTargets).toBe(4);
		expect(ck?.repeatTop).toBe(3);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-001: appendTimeout records the discriminating evidence per kind", () => {
		const root = mkdtemp();
		const key = "task-to";
		makeTaskDir(root, key);
		appendTimeout(key, root, "idle", "no activity for 612s (last delta 612s ago, last tool 640s ago)");
		appendTimeout(key, root, "wall", "budget 3600s exceeded (last activity 8s ago)");
		const trace = fs.readFileSync(path.join(root, key, "trace.log"), "utf8");
		expect(trace).toMatch(
			/^\[TIMEOUT\] \S+ idle: no activity for 612s \(last delta 612s ago, last tool 640s ago\)$/m,
		);
		expect(trace).toMatch(/^\[TIMEOUT\] \S+ wall: budget 3600s exceeded \(last activity 8s ago\)$/m);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-005: running widget line carries the checkpoint badge; non-low risks get the warning glyph", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await is.upsert({
			key: "key-a",
			status: "active",
			phase: "EXECUTE",
			claimId: "1",
			deps: "",
			desc: "",
			updated: new Date().toISOString(),
		});
		await queueRunning(root, "key-a", "diverging");
		await queueRunning(root, "key-a", "converging");
		const ckLine = (risk: string): string =>
			`[CHECKPOINT] ${new Date().toISOString()} elapsed=1800s reads=${risk === "high" ? 74 : 20} writes=${
				risk === "high" ? 0 : 8
			} phases=- uniq_targets=1 repeat_top=1 risk=${risk}\n`;
		fs.writeFileSync(
			path.join(root, "key-a", "workers", "diverging", "trace.log"),
			`[HEARTBEAT] ${new Date().toISOString()} task=x phase=-\n${ckLine("high")}`,
			"utf8",
		);
		fs.writeFileSync(
			path.join(root, "key-a", "workers", "converging", "trace.log"),
			`[HEARTBEAT] ${new Date().toISOString()} task=x phase=-\n${ckLine("low")}`,
			"utf8",
		);

		const lines = renderWatchLines(is, store, new AckStore(root), root, "key-a");
		const diverging = lines.find((l) => l.includes("diverging"));
		const converging = lines.find((l) => l.includes("converging"));
		expect(diverging).toContain("ck30m high\u26a0");
		expect(converging).toContain("ck30m");
		expect(converging).not.toContain("\u26a0");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-004: poll loop wakes the PM once on a mid/high checkpoint (triggerTurn) and leaves low-risk alone", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await is.upsert({
			key: "key-a",
			status: "active",
			phase: "EXECUTE",
			claimId: "1",
			deps: "",
			desc: "",
			updated: new Date().toISOString(),
		});
		await queueRunning(root, "key-a", "t-diverge");
		await queueRunning(root, "key-a", "t-ok");
		// Diverging worker: zero writes past the anchor (cpr-007 pattern).
		fs.writeFileSync(
			path.join(root, "key-a", "workers", "t-diverge", "trace.log"),
			`[START] ${new Date(Date.now() - 35 * 60_000).toISOString()} task=t-diverge type=coding phases=-\n` +
				`[CHECKPOINT] ${new Date().toISOString()} elapsed=1800s reads=74 writes=0 phases=- uniq_targets=0 repeat_top=3 risk=high\n`,
			"utf8",
		);
		// Converging worker: writes advancing.
		fs.writeFileSync(
			path.join(root, "key-a", "workers", "t-ok", "trace.log"),
			`[START] ${new Date(Date.now() - 35 * 60_000).toISOString()} task=t-ok type=coding phases=-\n` +
				`[CHECKPOINT] ${new Date().toISOString()} elapsed=1800s reads=20 writes=8 phases=- uniq_targets=3 repeat_top=1 risk=low\n`,
			"utf8",
		);
		const watch: PmWatchState = { key: "key-a" };
		const ui: PmUiHolder = { ctx: undefined };

		vi.useFakeTimers();
		try {
			const { pi, messages, options } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			vi.advanceTimersByTime(500);
			// Exactly one escalation: the high-risk worker, not the low-risk one.
			expect(messages).toHaveLength(1);
			expect(messages[0]).toContain("发散风险");
			expect(messages[0]).toContain("'t-diverge'");
			expect(messages[0]).toContain("risk=high");
			expect(messages[0]).toContain("reads=74 writes=0");
			expect(messages[0]).toContain("trace.log");
			expect(messages[0]).toContain("progress.md");
			expect(options[0]?.triggerTurn).toBe(true);
			// Second tick: no duplicate escalation (once per task).
			vi.advanceTimersByTime(500);
			expect(messages).toHaveLength(1);
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-004: diverging workers owned by other keys never wake this window", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await is.upsert({
			key: "key-a",
			status: "active",
			phase: "EXECUTE",
			claimId: "1",
			deps: "",
			desc: "",
			updated: new Date().toISOString(),
		});
		await queueRunning(root, "key-b", "t-foreign");
		fs.writeFileSync(
			path.join(root, "key-b", "workers", "t-foreign", "trace.log"),
			`[CHECKPOINT] ${new Date().toISOString()} elapsed=1800s reads=74 writes=0 phases=- uniq_targets=0 repeat_top=3 risk=high\n`,
			"utf8",
		);
		const watch: PmWatchState = { key: "key-a" };
		const ui: PmUiHolder = { ctx: undefined };

		vi.useFakeTimers();
		try {
			const { pi, messages } = fakePi();
			const handle = startWorkerPollLoop(pi, store, new AckStore(root), is, root, watch, ui, 100);
			vi.advanceTimersByTime(500);
			expect(messages).toHaveLength(0);
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── Integrated watchdog behavior via workerModeActivate (AC-001/002) ──────────
// The idle/wall kill decisions live in closure state inside the worker loop,
// so the interval logic is exercised end-to-end: PI_WORKER_TASK → activate →
// emit/withhold lifecycle events under fake timers → assert trace.log and
// output.md. process.exit is spied (a real exit would kill the runner) and
// fs.writeSync is silenced (worker.log status lines go to fd 1).
describe("watchdog integration (workerModeActivate)", () => {
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
	 * Budget comes from the task.md `timeout:` header; idle threshold is always
	 * shortened to 60s via env so the interval logic is reachable in-test. */
	async function startWatchdogTask(
		root: string,
		taskKey: string,
		body: string,
	): Promise<ReturnType<typeof fakeWorkerPi>> {
		const taskDir = path.join(root, "key-a", "workers", taskKey);
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), body, "utf8");
		const { pi, emit, sent } = fakeWorkerPi();
		process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
		process.env.PI_WORKER_IDLE_MS = "60000";
		await workerModeActivate(pi);
		return { pi, emit, sent };
	}

	it("AC-001: no activity for idleMs kills with the idle evidence line", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			await startWatchdogTask(root, "t-hang", "type: coding\ntimeout: 30\n\nwork\n");
			// No lifecycle events at all: ticks at 30s (below threshold) and 60s
			// (idleFor=60s >= 60s) — the 60s tick must kill.
			vi.advanceTimersByTime(60_000);
			expect(exitSpy).toHaveBeenCalledWith(1);
			const taskDir = path.join(root, "key-a", "workers", "t-hang");
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toContain("[TIMEOUT]");
			expect(trace).toContain("idle: no activity for 60s (last delta -s ago, last tool -s ago)");
			expect(trace).toContain("[END] ");
			expect(trace).toContain("exit=1");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("idle timeout: no activity for 60s");
			expect(output).not.toContain("checkpoint:");
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-001: token deltas reset the idle clock — a trickling stream is never killed", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			const { emit } = await startWatchdogTask(root, "t-stream", "type: coding\ntimeout: 30\n\nwork\n");
			// Delta every 25s for 200s: every gap stays under the 60s idle
			// threshold — exactly the cpr-003 slow-generation case that the old
			// 30m wall clock used to kill.
			for (let i = 0; i < 8; i++) {
				vi.advanceTimersByTime(25_000);
				emit("message_update");
			}
			expect(exitSpy).not.toHaveBeenCalled();
			const taskDir = path.join(root, "key-a", "workers", "t-stream");
			expect(fs.readFileSync(path.join(taskDir, "trace.log"), "utf8")).not.toContain("[TIMEOUT]");
			// Settle normally: success path, no process.exit.
			emit("agent_end", { messages: [] });
			emit("agent_settled");
			expect(exitSpy).not.toHaveBeenCalled();
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toContain("exit=0");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("Agent settled after 0 tool call(s).");
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-001: the watchdog survives phase-settles (multi-phase tasks keep coverage)", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			const { emit, sent } = await startWatchdogTask(
				root,
				"t-phases",
				"type: coding\ntimeout: 30\n\n- name: build\n  prompt: |\n    do build\n\n- name: verify\n  prompt: |\n    do verify\n",
			);
			// First settle dispatches phase 1 — it must NOT tear down the timers.
			emit("agent_end", { messages: [] });
			emit("agent_settled");
			expect(sent[0]?.text).toContain("do build");
			expect(exitSpy).not.toHaveBeenCalled();
			// Silence after the phase prompt: the idle kill still fires.
			vi.advanceTimersByTime(60_000);
			expect(exitSpy).toHaveBeenCalledWith(1);
			const taskDir = path.join(root, "key-a", "workers", "t-phases");
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toContain("idle: no activity for 60s");
			expect(trace).toContain("phases=0/2");
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-002/003/004: deadline steer, checkpoint steer and wall kill fire in order on a small budget", async () => {
		const root = mkdtemp();
		const exitSpy = vi.spyOn(process, "exit").mockImplementation(() => undefined as never);
		vi.useFakeTimers();
		try {
			// budget 3m: steerAt = 180s - min(5m, 45s) = 135s, checkpoint anchor =
			// min(30m, 90s) = 90s, wall = 180s. Order: checkpoint → deadline → wall.
			const { emit, sent } = await startWatchdogTask(root, "t-order", "type: coding\ntimeout: 3\n\nwork\n");
			// Keep activity trickling so the idle watchdog stays out of the way.
			for (let t = 0; t < 12; t++) {
				vi.advanceTimersByTime(15_000);
				emit("message_update");
			}
			// t=180s: all three timers have fired. Steers must carry the queueing
			// mode that Run 1 of the live smoke proved mandatory mid-run.
			const steer = sent.find((m) => m.text.includes("[mw deadline]"));
			const ckpt = sent.find((m) => m.text.includes("[mw checkpoint]"));
			expect(steer?.options?.deliverAs).toBe("steer");
			expect(ckpt?.options?.deliverAs).toBe("followUp");
			expect(exitSpy).toHaveBeenCalledWith(1);
			const taskDir = path.join(root, "key-a", "workers", "t-order");
			const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
			expect(trace).toContain("[CHECKPOINT] ");
			expect(trace).toContain("risk=high"); // zero reads/writes — pure no-op task
			expect(trace).toContain("wall: budget 180s exceeded");
			const output = fs.readFileSync(path.join(taskDir, "output.md"), "utf8");
			expect(output).toContain("wall timeout: budget 180s exceeded");
			expect(output).toContain("(checkpoint: risk=high reads=0 writes=0");
		} finally {
			vi.useRealTimers();
			exitSpy.mockRestore();
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
		}
		fs.rmSync(root, { recursive: true, force: true });
	});
});

describe("pmActivate lifecycle (m3)", () => {
	it("session_shutdown clears the poll loop — no zombie ticks after teardown", async () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
		const cwd = process.cwd();
		process.chdir(root);
		try {
			const handlers = new Map<string, (event?: unknown, ctx?: unknown) => unknown>();
			const commands = new Map<string, (args: string, ctx: ExtensionCommandContext) => Promise<void>>();
			const sent: Array<{ customType: string; content: string }> = [];
			const pi = {
				registerCommand: (
					name: string,
					opts: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
				) => {
					commands.set(name, opts.handler);
				},
				registerTool: () => {},
				on: (name: string, handler: (event?: unknown, ctx?: unknown) => unknown) => {
					handlers.set(name, handler);
				},
				appendEntry: () => {},
				sendMessage: (m: { customType: string; content: string }) => {
					sent.push(m);
				},
			} as unknown as ExtensionAPI;

			vi.useFakeTimers();
			try {
				pmActivate(pi);
				expect(handlers.has("session_shutdown")).toBe(true);

				// Watch key-a so the poll loop emits terminal summaries for it.
				const agenticdoc = path.join(root, ".agenticdoc");
				const is = new IndexStore(agenticdoc);
				const ws = new WorkerStore(agenticdoc);
				const taskDir = path.join(agenticdoc, "key-a", "workers", "t1");
				fs.mkdirSync(taskDir, { recursive: true });
				fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
				fs.writeFileSync(path.join(taskDir, "output.md"), "## Summary\n\nok\n", "utf8");
				await is.upsert({
					key: "key-a",
					status: "active",
					phase: "EXECUTE",
					claimId: "1",
					deps: "",
					desc: "",
					updated: new Date().toISOString(),
				});
				await ws.upsert({
					taskKey: "t1",
					status: "pending",
					cli: "pi",
					provider: "timi",
					taskPath: path.join(taskDir, "task.md"),
					dispatchedAt: "",
					updatedAt: "",
					model: "",
				});
				const watchHandler = commands.get("mw-watch");
				if (!watchHandler) throw new Error("mw-watch not registered");
				const ctx = {
					hasUI: true,
					ui: { notify: () => {}, setWidget: () => {} },
					sessionManager: { getEntries: () => [] },
				} as unknown as ExtensionCommandContext;
				await watchHandler("key-a", ctx);

				const entry = ws.findByKey("t1");
				if (!entry) throw new Error("t1 missing from queue");
				await ws.upsert({ ...entry, status: "done" });
				vi.advanceTimersByTime(5_000);
				expect(sent).toHaveLength(1); // summary emitted by the live loop

				// Teardown: the session_shutdown handler must clear the interval.
				(handlers.get("session_shutdown") as () => void)();
				vi.advanceTimersByTime(60_000);
				expect(sent).toHaveLength(1); // no zombie ticks after shutdown
			} finally {
				vi.useRealTimers();
			}
		} finally {
			process.chdir(cwd);
			fs.rmSync(root, { recursive: true, force: true });
		}
	}, 20000);
});
