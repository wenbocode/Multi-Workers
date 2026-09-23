/**
 * Tests for the agent-team-loop extension internals.
 *
 * mw-dispatch-reliability T-10: absorbs packages/multi-workers/test-l1-full.ts
 * (a loose script that had drifted from the code — it imported a runPhases that
 * no longer exists and asserted the pre-model 7-column worker rows). Adds the
 * waitForStart stability-window tests (T-08) and the /mw doctor formatter
 * tests (T-09).
 */

import { spawn, spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { Model } from "@earendil-works/pi-ai";
import { describe, expect, it, vi } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../src/core/extensions/types.ts";
import type { ModelRegistry } from "../../src/core/model-registry.ts";
import { activate } from "../../src/extensions/agent-team-loop/index.ts";
import {
	autoTakeOverFromDoc,
	dispatchNewTasks,
	docFromWrite,
	evidencePhaseFromWrite,
	evidenceReviewNotice,
	keyFromDocWrite,
	nudgeGoalUnestablished,
	PARALLEL_PROTOCOL,
	PARALLEL_PROTOCOL_MARKER,
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
	registerAdvancePhaseTool,
	registerMwCommands,
	registerPmKeyCommands,
	registerPmSaveCommand,
	registerSwitchKeyTool,
	registerWorkerCommands,
	registerWorkerTools,
	renderWatchLines,
	resolveDispatchType,
	runMwModelCommand,
	runMwPartitionCommand,
	runMwTargetCommand,
	splitCommandLine,
	windowClaimId,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { agenticScriptsDir, runAgenticScript } from "../../src/extensions/agent-team-loop/shared/agentic-scripts.ts";
import {
	applyMainModelConfig,
	DISPATCH_ROLE_BY_TYPE,
	PREFIX_TO_PROVIDER_ID,
	PROVIDER_ID_TO_PREFIX,
	parseModelValue,
	readMainModelConfig,
	readRoleModel,
	recordWindowModel,
	roleForTaskType,
	settingsDefaultModel,
	validateModelValue,
	windowModelPath,
} from "../../src/extensions/agent-team-loop/shared/dispatch-models.ts";
import {
	HEARTBEAT_INTERVAL_MS,
	readHeartbeatInfo,
	readTaskProgress,
} from "../../src/extensions/agent-team-loop/shared/heartbeat.ts";
import { IndexStore, readIndexMdActive } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import type { DoctorJson, MwCliResult } from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
import {
	mwCodeNewestMtimeMs,
	PYTHON_EXE,
	readServeMeta,
	restartSequence,
	serveStaleness,
	waitForStart,
} from "../../src/extensions/agent-team-loop/shared/mw-runner.ts";
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
	appendModel,
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

/** Spawn a short-lived child and wait until its pid is observable — the
 * stand-in for "another live window's" claim in takeover/owner-resolution
 * tests. */
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

	it("D-117: agent-written output.md is preserved, harness sections appended below a separator", () => {
		const root = mkdtemp();
		const key = "task-merge";
		makeTaskDir(root, key);
		// The agent wrote a machine-readable first line + a body during the task
		// (dispatch-template contract; conductor [VERIFY]/L3 sections alike).
		const agentBody = "VERDICT=pass TASKS=2/2\n\n## Report\n\nfound no blockers\n";
		fs.writeFileSync(path.join(root, key, "output.md"), agentBody, "utf8");
		writeOutput({
			taskKey: key,
			agenticdocRoot: root,
			exitCode: 0,
			summary: "Done",
			exitReason: "OK",
		});
		const out = fs.readFileSync(path.join(root, key, "output.md"), "utf8");
		// First line keeps the machine-readable contract.
		expect(out.split("\n")[0]).toBe("VERDICT=pass TASKS=2/2");
		expect(out).toContain("## Report\n\nfound no blockers");
		// Harness sections appended after a separator, still parseable.
		expect(out).toContain("\n---\n\n## TL;DR");
		expect(out).toContain("## Exit Reason\n\nOK");
		// Agent body above the separator, harness below it.
		expect(out.indexOf("## Report")).toBeLessThan(out.indexOf("---"));
		expect(out.indexOf("## Summary")).toBeGreaterThan(out.indexOf("---"));
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("D-117: empty or missing output.md keeps the harness-only format", () => {
		const root = mkdtemp();
		const key = "task-empty";
		makeTaskDir(root, key);
		// Whitespace-only file counts as "the agent never wrote".
		fs.writeFileSync(path.join(root, key, "output.md"), "   \n\n", "utf8");
		writeOutput({ taskKey: key, agenticdocRoot: root, exitCode: 0, summary: "Done" });
		const out = fs.readFileSync(path.join(root, key, "output.md"), "utf8");
		expect(out.startsWith("## TL;DR")).toBe(true);
		expect(out).not.toContain("---\n\n## TL;DR");
		// Missing file: plain harness format (refusal/failure paths).
		const key2 = "task-missing";
		makeTaskDir(root, key2);
		writeOutput({ taskKey: key2, agenticdocRoot: root, exitCode: 1, summary: "Err", exitReason: "bad" });
		const out2 = fs.readFileSync(path.join(root, key2, "output.md"), "utf8");
		expect(out2.startsWith("## TL;DR")).toBe(true);
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

	it("D-116: [MODEL] records the model id and readTaskProgress exposes it (old traces stay compatible)", () => {
		const root = mkdtemp();
		// Writer side: appendModel writes the machine-parseable record line.
		const key = "task-model";
		makeTaskDir(root, key);
		appendModel(key, root, "glm-5.3");
		expect(fs.readFileSync(path.join(root, key, "trace.log"), "utf8")).toMatch(/^\[MODEL\] \S+ model=glm-5\.3$/m);
		// Reader side: [MODEL] exposes the model; pre-D-116 traces without it
		// keep parsing (undefined).
		const withModel = makeTaskDir(root, "task-m1");
		fs.writeFileSync(
			path.join(withModel, "trace.log"),
			`[START] ${new Date(Date.now() - 5_000).toISOString()} task=task-m1 type=coding phases=1\n` +
				`[MODEL] ${new Date(Date.now() - 4_000).toISOString()} model=claude-sonnet-4-5\n`,
			"utf8",
		);
		expect(readTaskProgress(withModel)?.model).toBe("claude-sonnet-4-5");
		const noModel = makeTaskDir(root, "task-m2");
		fs.writeFileSync(
			path.join(noModel, "trace.log"),
			`[START] ${new Date(Date.now() - 5_000).toISOString()} task=task-m2 type=coding phases=1\n`,
			"utf8",
		);
		expect(readTaskProgress(noModel)?.model).toBeUndefined();
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

// ── AgenticTask framework scripts (shell-free runner) ───────────────────────

/** Python availability probe — the spawn tests below are skipped where the
 * interpreter is absent (python3-only containers, stripped CI images). */
const pythonAvailable = (() => {
	try {
		return spawnSync(PYTHON_EXE, ["-c", "print(1)"], { encoding: "utf8", timeout: 5000 }).status === 0;
	} catch {
		return false;
	}
})();

describe("agentic-scripts", () => {
	it("agenticScriptsDir prefers .claude/scripts, falls back to the skill clone, null when absent", () => {
		const root = mkdtemp();
		expect(agenticScriptsDir(root)).toBeNull();

		const claudeScripts = path.join(root, ".claude", "scripts");
		fs.mkdirSync(claudeScripts, { recursive: true });
		fs.writeFileSync(path.join(claudeScripts, "advance_phase.py"), "# stub\n", "utf8");
		expect(agenticScriptsDir(root)).toBe(claudeScripts);
		fs.rmSync(root, { recursive: true, force: true });

		const root2 = mkdtemp();
		const cloneScripts = path.join(root2, ".agents", "skills", "agentic-task", "claude", "scripts");
		fs.mkdirSync(cloneScripts, { recursive: true });
		fs.writeFileSync(path.join(cloneScripts, "advance_phase.py"), "# stub\n", "utf8");
		expect(agenticScriptsDir(root2)).toBe(cloneScripts);
		fs.rmSync(root2, { recursive: true, force: true });
	});

	it("runAgenticScript fails closed when the framework scripts are missing", () => {
		const root = mkdtemp();
		const r = runAgenticScript(root, "advance_phase.py", ["k", "design"]);
		expect(r.ok).toBe(false);
		expect(r.output).toContain("framework scripts not found");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it.skipIf(!pythonAvailable)("runAgenticScript spawns python with list args and captures stdout+stderr", () => {
		const root = mkdtemp();
		const scripts = path.join(root, ".claude", "scripts");
		fs.mkdirSync(scripts, { recursive: true });
		fs.writeFileSync(
			path.join(scripts, "advance_phase.py"),
			"import sys\nprint('ARGV=' + repr(sys.argv[1:]))\nprint('gate-warn', file=sys.stderr)\n",
			"utf8",
		);
		const r = runAgenticScript(root, "advance_phase.py", ["my key", "design"]);
		expect(r.ok).toBe(true);
		expect(r.output).toContain("ARGV=['my key', 'design']"); // space survives: list args, no shell
		expect(r.output).toContain("gate-warn");
		fs.rmSync(root, { recursive: true, force: true });
	});
});

describe("advance_phase tool", () => {
	it("validates key and target phase without spawning anything", async () => {
		const { pi, tools } = fakeCmdPi();
		registerAdvancePhaseTool(pi, path.join(os.tmpdir(), "no-such-project"));
		const tool = tools.get("advance_phase");
		if (!tool) throw new Error("advance_phase not registered");

		const badPhase = await tool.execute(
			"id1",
			{ key: "k", target_phase: "nope" },
			undefined,
			undefined,
			fakeCmdCtx().ctx,
		);
		expect(badPhase.content[0]?.text).toContain("Unknown phase 'nope'");

		const reserved = await tool.execute(
			"id2",
			{ key: "_scratch", target_phase: "design" },
			undefined,
			undefined,
			fakeCmdCtx().ctx,
		);
		expect(reserved.content[0]?.text).toContain("reserved prefix");

		const missing = await tool.execute("id3", { key: "k", target_phase: "" }, undefined, undefined, fakeCmdCtx().ctx);
		expect(missing.content[0]?.text).toContain("required");

		// done 汇总契约：缺 summary 在工具层先拦，不 spawn。
		const noSummary = await tool.execute(
			"id4",
			{ key: "k", target_phase: "done" },
			undefined,
			undefined,
			fakeCmdCtx().ctx,
		);
		expect(noSummary.content[0]?.text).toContain("requires a non-empty summary");

		// 非 done 阶段不要求 summary。
		const nonDone = await tool.execute(
			"id5",
			{ key: "k", target_phase: "verify" },
			undefined,
			undefined,
			fakeCmdCtx().ctx,
		);
		expect((nonDone.content[0]?.text ?? "").includes("summary")).toBe(false);
	});

	it.skipIf(!pythonAvailable)("runs the gate script shell-free and surfaces its output", async () => {
		const root = mkdtemp();
		const scripts = path.join(root, ".claude", "scripts");
		fs.mkdirSync(scripts, { recursive: true });
		fs.writeFileSync(
			path.join(scripts, "advance_phase.py"),
			"import sys\nprint('GATE OK ' + ' '.join(sys.argv[1:]))\n",
			"utf8",
		);
		const { pi, tools } = fakeCmdPi();
		registerAdvancePhaseTool(pi, root);
		const tool = tools.get("advance_phase");
		if (!tool) throw new Error("advance_phase not registered");

		// Upper-case target is normalized; optional flags pass through in order.
		const r = await tool.execute(
			"id",
			{ key: "my-key", target_phase: "PLAN", summary: "core done" },
			undefined,
			undefined,
			fakeCmdCtx().ctx,
		);
		expect(r.content[0]?.text).toContain("GATE OK my-key plan --summary core done");
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── Serve staleness detection + restart (stale-serve fix) ──────────────────

describe("serve staleness detection + restart", () => {
	const T = 1_700_000_000_000; // fixed epoch ms base

	it("mwCodeNewestMtimeMs: newest runtime source, tests/scratch/pycache/dist excluded", () => {
		const dir = mkdtemp();
		try {
			const touch = (rel: string, atime: number): void => {
				const p = path.join(dir, rel);
				fs.mkdirSync(path.dirname(p), { recursive: true });
				fs.writeFileSync(p, "x", "utf8");
				fs.utimesSync(p, new Date(atime), new Date(atime));
			};
			touch("mw.py", T);
			touch("providers.json", T + 5_000);
			touch("autopilot/conductor.py", T + 10_000);
			// All newer than the expected result — must be ignored:
			touch("test_dev.py", T + 100_000);
			touch("_scratch.py", T + 100_000);
			touch("__pycache__/mw.cpython-314.pyc", T + 100_000);
			touch("dist/agent-team-loop.js", T + 100_000);
			expect(mwCodeNewestMtimeMs(path.join(dir, "mw.py"))).toBe(T + 10_000);
		} finally {
			fs.rmSync(dir, { recursive: true, force: true });
		}
	});

	it("serveStaleness: fresh / stale / unknown / pid-file fallback", () => {
		const root = mkdtemp();
		try {
			fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
			// No meta, no pid — cannot determine.
			expect(serveStaleness(root, T)).toBeUndefined();

			// serve.meta present: code newer than start → stale.
			fs.writeFileSync(
				path.join(root, ".mw", "serve.meta"),
				JSON.stringify({ pid: 1, started_at_ms: T, code_dir: "x" }),
				"utf8",
			);
			expect(serveStaleness(root, T + 60_000)?.stale).toBe(true);
			expect(serveStaleness(root, T)?.stale).toBe(false); // same age = fresh

			// Fallback: no meta but a pid file — its mtime approximates serve start.
			fs.rmSync(path.join(root, ".mw", "serve.meta"));
			const pidFile = path.join(root, ".mw", "mw.pid");
			fs.writeFileSync(pidFile, "1", "utf8");
			fs.utimesSync(pidFile, new Date(T), new Date(T));
			expect(serveStaleness(root, T + 60_000)?.stale).toBe(true);
			expect(serveStaleness(root, T)?.stale).toBe(false);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("readServeMeta tolerates garbage", () => {
		const root = mkdtemp();
		try {
			fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
			fs.writeFileSync(path.join(root, ".mw", "serve.meta"), "{not json", "utf8");
			expect(readServeMeta(root)).toBeNull();
			fs.writeFileSync(path.join(root, ".mw", "serve.meta"), JSON.stringify({ pid: 1 }), "utf8");
			expect(readServeMeta(root)).toBeNull(); // missing started_at_ms
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("restartSequence: graceful stop -> start -> confirmed up", async () => {
		const running = true;
		let stopRequested = false;
		const r = await restartSequence(
			() => running && !stopRequested,
			() => {
				stopRequested = true;
			},
			() => true,
			async () => true,
			1000,
			1,
		);
		expect(r).toBe("restarted");
		expect(stopRequested).toBe(true);
	});

	it("restartSequence: serve refusing to exit fails the restart", async () => {
		const r = await restartSequence(
			() => true,
			() => {},
			() => true,
			async () => true,
			50,
			1,
		);
		expect(r).toBe("stop-failed");
	});

	it("restartSequence: start failure and unconfirmed startup both fail", async () => {
		expect(
			await restartSequence(
				() => false,
				() => {},
				() => false,
				async () => true,
				100,
				1,
			),
		).toBe("start-failed");
		expect(
			await restartSequence(
				() => false,
				() => {},
				() => true,
				async () => false,
				100,
				1,
			),
		).toBe("start-failed");
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

	it("renders the pi_shell row: ok shows the path, other statuses show detail, not-applicable stays silent", () => {
		const ok: DoctorJson = {
			...sample,
			pi_shell: {
				status: "ok",
				settings: "C:/x/settings.json",
				shell_path: "C:/pwsh.exe",
				detected: null,
				detail: "",
			},
		};
		expect(formatDoctorReport(ok, false)).toContain("pi shell: C:/pwsh.exe");

		const missing: DoctorJson = {
			...sample,
			pi_shell: {
				status: "missing",
				settings: "C:/x/settings.json",
				shell_path: null,
				detected: "C:/pwsh.exe",
				detail: "shellPath not configured — detected C:/pwsh.exe; pin it",
			},
		};
		expect(formatDoctorReport(missing, false)).toContain("pi shell: missing");
		expect(formatDoctorReport(missing, false)).toContain("shellPath not configured");

		const notApplicable: DoctorJson = {
			...sample,
			pi_shell: { status: "not-applicable", settings: "/home/x", shell_path: null, detected: null, detail: "" },
		};
		expect(formatDoctorReport(notApplicable, false)).not.toContain("pi shell");

		// Absent section (old serve) stays silent too.
		expect(formatDoctorReport(sample, false)).not.toContain("pi shell");
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
		// goal.md 不存在 → §0 跳过；相位分层后该 key 无 pm-state → spec 层 = spec.md + spec 证据 + AC = 3
		expect(gates[0]?.gaps).toHaveLength(3);

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

	it("MW-001: this window's claimed key wins over the globally-latest active row", async () => {
		const root = mkdtemp();
		const ws = new WorkerStore(root);
		const is = new IndexStore(root);
		const { pi, tools, sent } = fakeCmdPi();
		writePhaseDocs(root, "k-own"); // documented so dispatch proceeds
		await seedKey(root, "k-own", windowClaimId());
		// Seeded after k-own → the latest-updated ACTIVE row belongs to another
		// window (stale claim: no live pid). Old behavior dispatched here.
		await seedKey(root, "k-other", "20260808-142655-3496");
		const watch: PmWatchState = { key: "k-own" };
		registerWorkerTools(pi, ws, new AckStore(root), is, root, watch);
		const tool = tools.get("dispatch_worker");
		if (!tool) throw new Error("dispatch_worker not registered");

		const r = await tool.execute(
			"id1",
			{ task_key: "t1", description: "work" },
			undefined,
			undefined,
			fakeCmdCtx().ctx,
		);
		expect(r.content[0]?.text).toContain("under key 'k-own'");
		// The task lands under THIS window's key, never the latest active row.
		expect(fs.existsSync(path.join(root, "k-own", "workers", "t1", "task.md"))).toBe(true);
		expect(fs.existsSync(path.join(root, "k-other", "workers", "t1"))).toBe(false);
		// Own claim → authoritative, no mismatch warning.
		expect(sent.filter((m) => m.content.includes("owner-key mismatch"))).toHaveLength(0);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("MW-002: a live foreign claim on the active key degrades dispatch to _scratch", async () => {
		const root = mkdtemp();
		const ws = new WorkerStore(root);
		const is = new IndexStore(root);
		const { pi, tools, sent } = fakeCmdPi();
		const live = await spawnLivePid();
		try {
			// The only active row is held live by another window; this window
			// watches nothing — the old behavior injected work into that key.
			await seedKey(root, "k-foreign", `${os.hostname()}:${live.pid}`);
			const watch: PmWatchState = { key: undefined };
			registerWorkerTools(pi, ws, new AckStore(root), is, root, watch);
			const tool = tools.get("dispatch_worker");
			if (!tool) throw new Error("dispatch_worker not registered");

			const r = await tool.execute(
				"id1",
				{ task_key: "t2", description: "work" },
				undefined,
				undefined,
				fakeCmdCtx().ctx,
			);
			expect(r.content[0]?.text).toContain("under key '_scratch'");
			expect(fs.existsSync(path.join(root, "_scratch", "workers", "t2", "task.md"))).toBe(true);
			expect(fs.existsSync(path.join(root, "k-foreign", "workers", "t2"))).toBe(false);
			// Warned once, naming the foreign-held key.
			const warns = sent.filter((m) => m.content.includes("claimed by another live window"));
			expect(warns).toHaveLength(1);
			expect(warns[0]?.content).toContain("k-foreign");
		} finally {
			process.kill(live.pid);
			await live.done;
			fs.rmSync(root, { recursive: true, force: true });
		}
	}, 20000);
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

	it("D-116: rows carry the worker model badge — trace [START] for running/terminal, queue override for pending", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const is = new IndexStore(root);
		await activateKey(root, "key-a");
		// Running: effective model from trace.log [MODEL] (pi-resolved id,
		// launcher defaults included).
		await queueTask(root, "key-a", "mdl-live", "running");
		fs.writeFileSync(
			path.join(root, "key-a", "workers", "mdl-live", "trace.log"),
			`[START] ${new Date(Date.now() - 10_000).toISOString()} task=mdl-live type=coding phases=2\n` +
				`[MODEL] ${new Date(Date.now() - 9_000).toISOString()} model=glm-5.3\n` +
				`[HEARTBEAT] ${new Date(Date.now() - 5_000).toISOString()} task=mdl-live phase=1/2\n`,
			"utf8",
		);
		// Running with a pre-D-116 trace (no [MODEL] line): no badge.
		await queueTask(root, "key-a", "mdl-old", "running");
		fs.writeFileSync(
			path.join(root, "key-a", "workers", "mdl-old", "trace.log"),
			`[START] ${new Date(Date.now() - 10_000).toISOString()} task=mdl-old type=coding phases=2\n`,
			"utf8",
		);
		// Pending: dispatch-time --model override from the queue row (no
		// trace.log yet); a second pending task without one shows no badge.
		await queueTask(root, "key-a", "mdl-wait", "pending");
		const waitEntry = store.findByKey("mdl-wait");
		if (!waitEntry) throw new Error("mdl-wait missing from queue");
		await store.upsert({ ...waitEntry, model: "claude-sonnet-4-5" });
		await queueTask(root, "key-a", "mdl-bare", "pending");

		const lines = renderWatchLines(is, store, new AckStore(root), root, "key-a");
		const live = lines.find((l) => l.includes("mdl-live"));
		const old = lines.find((l) => l.includes("mdl-old"));
		const wait = lines.find((l) => l.includes("mdl-wait"));
		const bare = lines.find((l) => l.includes("mdl-bare"));
		expect(live).toContain("mdl-live [glm-5.3]");
		expect(old).toBeDefined();
		expect(old).not.toMatch(/mdl-old \[/);
		expect(wait).toContain("mdl-wait [claude-sonnet-4-5]");
		expect(bare).toBeDefined();
		expect(bare).not.toMatch(/mdl-bare \[/);
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
		registerMwCommands(pi, root, store, ackStore, { key: "key-a" }, root);
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
		registerWorkerTools(pi, store, ackStore, new IndexStore(root), root, { key: "key-a" });
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
		registerWorkerTools(pi, store, ackStore, new IndexStore(root), root, { key: "key-a" });
		const list = tools.get("list_tasks");
		if (!list) throw new Error("list_tasks not registered");
		const res = await list.execute("id", { scope: "all" }, undefined, undefined, {} as ExtensionContext);
		const text = res.content[0]?.type === "text" ? res.content[0].text : "";
		const oldLine = text.split("\n").find((l) => l.includes("t-old"));
		const newLine = text.split("\n").find((l) => l.includes("t-new"));
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

describe("task scope isolation (mw-task-scope-isolation: AC-001..AC-007)", () => {
	/** Seed a queue row under an arbitrary owner key (root IS the .agenticdoc dir). */
	async function rowIn(root: string, owner: string, taskKey: string, status: WorkerStatus): Promise<void> {
		const taskDir = path.join(root, owner, "workers", taskKey);
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

	const textOf = (res: { content: Array<{ type: string; text?: string }> }): string =>
		res.content[0]?.type === "text" ? (res.content[0].text ?? "") : "";

	it("AC-001..AC-004: list_tasks scopes to this window by default, owner column, guidance", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const ackStore = new AckStore(root);
		await rowIn(root, "key-a", "t-mine", "running");
		await rowIn(root, "key-b", "t-theirs", "failed");
		const { pi, tools } = fakeCmdPi();
		registerWorkerTools(pi, store, ackStore, new IndexStore(root), root, { key: "key-a" });
		const list = tools.get("list_tasks");
		if (!list) throw new Error("list_tasks not registered");

		// AC-001: default scope = mine (watched key only), owner prefix on every row.
		const mine = textOf(await list.execute("id", {}, undefined, undefined, {} as ExtensionContext));
		expect(mine).toContain("key-a :: t-mine | running | pi");
		expect(mine).not.toContain("t-theirs");

		// AC-002: scope "all" keeps the whole-project view (both owners).
		const all = textOf(await list.execute("id", { scope: "all" }, undefined, undefined, {} as ExtensionContext));
		expect(all).toContain("key-a :: t-mine");
		expect(all).toContain("key-b :: t-theirs");

		// AC-003: scope "key" filters by owner; a missing/unknown parameter is a
		// text error, never a silent fallback to the whole project.
		const one = textOf(
			await list.execute("id", { scope: "key", key: "key-b" }, undefined, undefined, {} as ExtensionContext),
		);
		expect(one).toContain("key-b :: t-theirs");
		expect(one).not.toContain("t-mine");
		const missing = textOf(await list.execute("id", { scope: "key" }, undefined, undefined, {} as ExtensionContext));
		expect(missing).toContain('scope "key" requires key');
		const bogus = textOf(await list.execute("id", { scope: "nope" }, undefined, undefined, {} as ExtensionContext));
		expect(bogus).toContain("Unknown scope");

		// AC-004: a window with no watched key and no dispatch gets guidance and
		// never another window's rows.
		const { pi: pi2, tools: tools2 } = fakeCmdPi();
		registerWorkerTools(pi2, store, ackStore, new IndexStore(root), root, { key: undefined });
		const idle = tools2.get("list_tasks");
		if (!idle) throw new Error("list_tasks not registered");
		const idleText = textOf(await idle.execute("id", {}, undefined, undefined, {} as ExtensionContext));
		expect(idleText).toContain("No tasks found for this window");
		expect(idleText).toContain("switch_key");
		expect(idleText).toContain('scope: "all"');
		expect(idleText).not.toContain("t-mine");
		expect(idleText).not.toContain("t-theirs");
		console.log("[VERIFY] AC-001..004: mine_scoped=yes, all=whole_project, key_filter=yes, empty_guidance=yes");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-005/AC-006: ack is window-scoped; foreign rows are refused and never written", async () => {
		const root = mkdtemp();
		const store = new WorkerStore(root);
		const ackStore = new AckStore(root);
		await rowIn(root, "key-a", "a-done", "done");
		await rowIn(root, "key-b", "b-failed", "failed");
		const { pi, tools } = fakeCmdPi();
		registerWorkerTools(pi, store, ackStore, new IndexStore(root), root, { key: "key-a" });
		const ack = tools.get("ack_worker_result");
		if (!ack) throw new Error("ack_worker_result not registered");

		// AC-005: "all" covers this window only — the other key's unhandled row
		// survives (the sidecar is project-level, so this is the whole point).
		const res = textOf(await ack.execute("id", { task_key: "all" }, undefined, undefined, {} as ExtensionContext));
		expect(res).toContain("Acked 1 task(s): a-done");
		const after = new AckStore(root).readAll();
		expect(after.has("a-done")).toBe(true);
		expect(after.has("b-failed")).toBe(false);

		// AC-006: naming a foreign row is rejected with the owning key, and the
		// sidecar stays untouched.
		const foreign = textOf(
			await ack.execute("id", { task_key: "b-failed" }, undefined, undefined, {} as ExtensionContext),
		);
		expect(foreign).toContain("NOT acked: b-failed");
		expect(foreign).toContain("owned by key 'key-b'");
		expect(foreign).toContain("/pm-key switch key-b");
		expect(new AckStore(root).readAll().has("b-failed")).toBe(false);
		console.log("[VERIFY] AC-005/006: all_scoped=yes, foreign_rejected=yes, sidecar_untouched=yes");
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("AC-007: an explicit cross-key dispatch stays this window's task", async () => {
		const root = mkdtemp();
		const ws = new WorkerStore(root);
		const is = new IndexStore(root);
		writePhaseDocs(root, "key-b"); // documented so the dispatch gate passes
		const { pi, tools } = fakeCmdPi();
		registerWorkerTools(pi, ws, new AckStore(root), is, root, { key: "key-a" });
		const dispatch = tools.get("dispatch_worker");
		const list = tools.get("list_tasks");
		if (!dispatch || !list) throw new Error("tools not registered");

		const r = await dispatch.execute(
			"id",
			{ task_key: "x-task", description: "work", key: "key-b" },
			undefined,
			undefined,
			fakeCmdCtx().ctx,
		);
		expect(textOf(r)).toContain("Dispatched worker 'x-task'");
		expect(fs.existsSync(path.join(root, "key-b", "workers", "x-task", "task.md"))).toBe(true);

		// The owner key is NOT the watched key, yet scope "mine" lists it — the
		// in-process dispatch record is what keeps it this window's task.
		const mine = textOf(await list.execute("id", {}, undefined, undefined, {} as ExtensionContext));
		expect(mine).toContain("key-b :: x-task | pending");
		console.log("[VERIFY] AC-007: cross_key_dispatch_visible=yes");
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

	it("/pm-save writes a session snapshot and asks the agent to fill in context", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		const ws = new WorkerStore(root);
		await seedKey(root, "key-a", windowClaimId());
		await ws.upsert({
			taskKey: "t1",
			status: "done",
			cli: "pi",
			provider: "timi",
			taskPath: path.join(root, "key-a", "workers", "t1", "task.md"),
			dispatchedAt: "",
			updatedAt: "",
			model: "",
		});
		const { pi, commands, messages } = fakeCmdPi();
		const watch: PmWatchState = { key: "key-a" };
		registerPmSaveCommand(pi, is, ws, watch, root);
		const handler = commands.get("pm-save");
		if (!handler) throw new Error("pm-save not registered");

		// No watch → warning, nothing written.
		const off = fakeCmdPi();
		registerPmSaveCommand(off.pi, is, ws, { key: undefined }, root);
		const offHandler = off.commands.get("pm-save");
		if (!offHandler) throw new Error("pm-save not registered");
		const warnCtx = fakeCmdCtx();
		await offHandler("", warnCtx.ctx);
		expect(warnCtx.notifications.some((n) => n.includes("Not watching any key"))).toBe(true);
		expect(fs.existsSync(path.join(root, "key-a", "pm-state.md"))).toBe(false);

		// Watched key: skeleton created, snapshot inserted under ## Notes.
		const okCtx = fakeCmdCtx();
		await handler("restart before framework swap", okCtx.ctx);
		const statePath = path.join(root, "key-a", "pm-state.md");
		const content = fs.readFileSync(statePath, "utf8");
		expect(content).toContain("# PM State: key-a");
		expect(content).toContain("### Session Snapshot — ");
		expect(content).toContain("Watch: key-a");
		expect(content).toContain("status=active phase=EXECUTE");
		expect(content).toContain("1 done");
		expect(content).toContain("Note: restart before framework swap");
		expect(okCtx.notifications.some((n) => n.includes("Saved session snapshot"))).toBe(true);
		// The agent is explicitly asked to fill in the conversational context
		// (user-invoked command — not a framework-injected nudge).
		expect(messages.at(-1)).toContain("pm-state.md");
		expect(messages.at(-1)).toContain("上下文状态");

		// Existing pm-state.md: machine-interface lines stay byte-identical and
		// prior notes survive; the snapshot is inserted under ## Notes.
		fs.writeFileSync(
			statePath,
			"# PM State: key-a\n\n## Section 1: Snapshot\n- Key: key-a\n- Claim-Id: cid-1\n- Phase: EXECUTE\n- Updated: 2026-01-01T00:00:00Z\n\n## Notes\n\nprior log line\n",
			"utf8",
		);
		const againCtx = fakeCmdCtx();
		await handler("", againCtx.ctx);
		const content2 = fs.readFileSync(statePath, "utf8");
		expect(content2).toContain("- Phase: EXECUTE");
		expect(content2).toContain("- Claim-Id: cid-1");
		expect(content2).toContain("prior log line");
		const notesIdx = content2.indexOf("## Notes");
		const snapIdx = content2.indexOf("### Session Snapshot");
		expect(notesIdx).toBeGreaterThanOrEqual(0);
		expect(snapIdx).toBeGreaterThan(notesIdx);
		expect(snapIdx).toBeLessThan(content2.indexOf("prior log line"));
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("restoreWatch points at a saved pm-state.md instead of injecting it", async () => {
		const root = mkdtemp();
		const is = new IndexStore(root);
		const ws = new WorkerStore(root);
		const as = new AckStore(root);
		await seedKey(root, "key-a", windowClaimId());
		fs.mkdirSync(path.join(root, "key-a"), { recursive: true });
		fs.writeFileSync(
			path.join(root, "key-a", "pm-state.md"),
			"# PM State: key-a\n\n## Notes\n\n### Session Snapshot — 2026-09-14T00:00:00Z (w)\n- Watch: key-a\n",
			"utf8",
		);
		const { pi } = fakeCmdPi();
		const watch: PmWatchState = { key: undefined };
		const entries = [{ type: "custom", customType: "agent-team-loop:watch", data: { key: "key-a", claimed: false } }];
		const notifications: string[] = [];
		const ctx = {
			hasUI: true,
			ui: { notify: (m: string) => notifications.push(m), setWidget: () => {} },
			sessionManager: { getEntries: () => entries },
		} as unknown as ExtensionContext;
		await restoreWatch(pi, watch, is, ws, as, root, ctx);
		expect(watch.key).toBe("key-a");
		// A notice pointing at the file — never an injected instruction
		// (evidenceReviewNotice principle).
		expect(notifications.some((n) => n.includes("pm-state.md"))).toBe(true);
		expect(notifications.some((n) => n.includes("让 agent 读取"))).toBe(true);
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

	it("evidenceReviewNotice fires once when doc + evidence coexist — as a UI notice, never an injected instruction", () => {
		const root = mkdtemp();
		const notices: Array<{ message: string; type: string }> = [];
		const ctx = {
			ui: {
				notify: (message: string, type?: string) => notices.push({ message, type: type ?? "" }),
			},
		} as unknown as ExtensionContext;
		const notified = new Set<string>();

		// Evidence alone (no phase doc yet) — review needs both sides.
		fs.mkdirSync(path.join(root, "k", "evidence", "research"), { recursive: true });
		fs.writeFileSync(path.join(root, "k", "evidence", "research", "spec-x.md"), "n", "utf8");
		evidenceReviewNotice(ctx, "k", "spec", root, notified);
		expect(notices).toHaveLength(0);

		// Phase doc present: notice fires once, then dedups within the session.
		writePhaseDocs(root, "k");
		evidenceReviewNotice(ctx, "k", "spec", root, notified);
		expect(notices).toHaveLength(1);
		expect(notices[0].type).toBe("info");
		expect(notices[0].message).toContain("k");
		expect(notices[0].message).toContain("spec.md");
		expect(notices[0].message).toContain("建议对照");
		// Never an injected user instruction (mw-evidence-nudge-notify): the
		// framework flags the moment; it must not command the agent. The notice
		// signature takes only a UI ctx — there is no sendUserMessage path.
		evidenceReviewNotice(ctx, "k", "spec", root, notified);
		expect(notices).toHaveLength(1);

		// Design phase is tracked independently.
		evidenceReviewNotice(ctx, "k", "design", root, notified);
		expect(notices).toHaveLength(2);
		expect(notices[1].message).toContain("design.md");
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

describe("pmActivate parallel protocol (mw-parallel-protocol)", () => {
	/** Fake pi collecting handlers per event name (arrays — several
	 * registrations may share one event). */
	function fakePi(): {
		pi: ExtensionAPI;
		handlers: Map<string, Array<(event?: unknown) => unknown>>;
	} {
		const handlers = new Map<string, Array<(event?: unknown) => unknown>>();
		const pi = {
			on: (name: string, handler: (event?: unknown) => unknown) => {
				const list = handlers.get(name) ?? [];
				list.push(handler);
				handlers.set(name, list);
			},
			registerCommand: () => {},
			registerTool: () => {},
			setActiveTools: () => {},
			appendEntry: () => {},
			sendMessage: () => {},
			sendUserMessage: () => {},
		} as unknown as ExtensionAPI;
		return { pi, handlers };
	}

	it("AC-001..AC-004: appends the protocol every run, exactly once", async () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
		const cwd = process.cwd();
		process.chdir(root);
		delete process.env.PI_WORKER_TASK;
		try {
			vi.useFakeTimers();
			const { pi, handlers } = fakePi();
			pmActivate(pi);
			const hooks = handlers.get("before_agent_start") ?? [];
			expect(hooks).toHaveLength(1);

			// AC-001: append-only — the existing system prompt stays the prefix.
			const first = (await hooks[0]({ systemPrompt: "BASE" })) as { systemPrompt?: string } | undefined;
			expect(first?.systemPrompt?.startsWith("BASE\n\n")).toBe(true);
			expect(first?.systemPrompt?.endsWith(PARALLEL_PROTOCOL)).toBe(true);

			// AC-002: the four action classes are actually spelled out.
			expect(first?.systemPrompt).toContain(PARALLEL_PROTOCOL_MARKER);
			expect(first?.systemPrompt).toContain("先做并行性分析");
			expect(first?.systemPrompt).toContain("RQ-1..N");
			expect(first?.systemPrompt).toContain("evidence/research/<phase>-<rq-slug>-<date>.md");
			expect(first?.systemPrompt).toContain("同一文件同一时刻只允许一个 worker");
			expect(first?.systemPrompt).toContain("相位文档");

			// AC-003: idempotent — re-feeding our own output must not append twice.
			expect(await hooks[0]({ systemPrompt: first?.systemPrompt })).toBeUndefined();

			// AC-004: missing/empty base prompt neither throws nor loses the block.
			const fromEmpty = (await hooks[0]({})) as { systemPrompt?: string } | undefined;
			expect(fromEmpty?.systemPrompt).toBe(PARALLEL_PROTOCOL);
		} finally {
			vi.useRealTimers();
			process.chdir(cwd);
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-005: worker mode never injects the protocol", async () => {
		const root = mkdtemp();
		const taskDir = path.join(root, "key-a", "workers", "w1");
		fs.mkdirSync(taskDir, { recursive: true });
		fs.writeFileSync(path.join(taskDir, "task.md"), "type: coding\n\nwork\n", "utf8");
		const { pi, handlers } = fakePi();
		process.env.PI_WORKER_TASK = path.join(taskDir, "task.md");
		process.env.PI_WORKER_IDLE_MS = "60000";
		try {
			await workerModeActivate(pi);
			const hooks = handlers.get("before_agent_start") ?? [];
			expect(hooks.length).toBeGreaterThan(0); // worker registers its own per-run hooks
			for (const hook of hooks) {
				const out = (await hook({ systemPrompt: "BASE" })) as { systemPrompt?: string } | undefined;
				expect(out?.systemPrompt ?? "").not.toContain(PARALLEL_PROTOCOL_MARKER);
			}
		} finally {
			delete process.env.PI_WORKER_TASK;
			delete process.env.PI_WORKER_IDLE_MS;
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

describe("activation guard re-arm (double-load + session replacement)", () => {
	/** Fake pi capturing event handlers (arrays — several registrations per
	 * event), commands, and tools, for direct activate() calls. */
	function fakePi(): {
		pi: ExtensionAPI;
		handlers: Map<string, Array<(event?: unknown, ctx?: unknown) => Promise<unknown> | unknown>>;
		commands: Set<string>;
		tools: Set<string>;
	} {
		const handlers = new Map<string, Array<(event?: unknown, ctx?: unknown) => Promise<unknown> | unknown>>();
		const commands = new Set<string>();
		const tools = new Set<string>();
		const pi = {
			on: (name: string, handler: (event?: unknown, ctx?: unknown) => Promise<unknown> | unknown) => {
				const list = handlers.get(name) ?? [];
				list.push(handler);
				handlers.set(name, list);
			},
			registerCommand: (name: string) => {
				commands.add(name);
			},
			registerTool: (tool: { name: string }) => {
				tools.add(tool.name);
			},
			registerShortcut: () => {},
			registerFlag: () => {},
			appendEntry: () => {},
			sendMessage: () => {},
			sendUserMessage: () => {},
		} as unknown as ExtensionAPI;
		return { pi, handlers, commands, tools };
	}

	async function fireShutdown(handlers: Map<string, Array<(event?: unknown) => unknown>>): Promise<void> {
		for (const h of handlers.get("session_shutdown") ?? []) await h({ type: "session_shutdown" });
	}

	it("blocks a same-pass double load, then fully re-activates after session_shutdown", async () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
		const cwd = process.cwd();
		process.chdir(root);
		delete process.env.PI_WORKER_TASK;
		const g = globalThis as Record<string, unknown>;
		const copies: ReturnType<typeof fakePi>[] = [];
		try {
			vi.useFakeTimers();
			// First load: full registration.
			const first = fakePi();
			copies.push(first);
			await activate(first.pi);
			expect(first.commands.has("pm-key")).toBe(true);
			expect(first.commands.has("mw")).toBe(true);
			expect(first.tools.has("dispatch_worker")).toBe(true);
			expect(g.__agentTeamLoopActivated).toBe(true);

			// Same-pass second copy (global + stale local double-load): blocked.
			const second = fakePi();
			copies.push(second);
			await activate(second.pi);
			expect(second.commands.size).toBe(0);
			expect(second.tools.size).toBe(0);

			// Session replacement (/new, /resume, /fork, /reload): teardown fires
			// session_shutdown on every live registration, re-arming the guard...
			for (const c of copies) await fireShutdown(c.handlers);
			expect(g.__agentTeamLoopActivated).toBeUndefined();

			// ...so the replacement runtime's activate() registers everything again
			// (the old behavior left the session with no commands/tools/widget).
			const third = fakePi();
			copies.push(third);
			await activate(third.pi);
			expect(third.commands.has("pm-key")).toBe(true);
			expect(third.commands.has("mw")).toBe(true);
			expect(third.commands.has("mw-watch")).toBe(true);
			expect(third.commands.has("autopilot")).toBe(true);
			expect(third.tools.has("dispatch_worker")).toBe(true);
			expect(third.tools.has("switch_key")).toBe(true);

			// A same-pass double load after re-activation is still blocked.
			const fourth = fakePi();
			copies.push(fourth);
			await activate(fourth.pi);
			expect(fourth.commands.size).toBe(0);
		} finally {
			vi.useRealTimers();
			// Stop every poll loop the activations started and clear the flag so
			// later tests in this file start from a clean slate.
			for (const c of copies) await fireShutdown(c.handlers);
			delete g.__agentTeamLoopActivated;
			process.chdir(cwd);
			fs.rmSync(root, { recursive: true, force: true });
		}
	}, 20000);
});

describe("/mw target (dual-workspace config)", () => {
	it("show/clear forward to mw.py target with the control root as --project", async () => {
		const calls: Array<[string, string[]]> = [];
		const ctx = fakeCmdCtx();
		await runMwTargetCommand(ctx.ctx, "/proj", "show", (projectDir, args) => {
			calls.push([projectDir, args]);
			return { ok: true, output: "[mw target] mode: single (source: default)" };
		});
		expect(calls).toEqual([["/proj", ["show"]]]);
		expect(ctx.notifications.some((n) => n.includes("mode: single"))).toBe(true);
	});

	it("set parses quoted Windows paths and forwards --game/--engine/--vcs/--uproject", async () => {
		const calls: Array<[string, string[]]> = [];
		const ctx = fakeCmdCtx();
		await runMwTargetCommand(
			ctx.ctx,
			"/proj",
			'set --game "D:\\My Game" --engine D:\\UE5 --vcs p4 --uproject "D:\\My Game\\X.uproject"',
			(projectDir, args) => {
				calls.push([projectDir, args]);
				return { ok: true, output: "[mw target] mode: dual" };
			},
		);
		expect(calls).toEqual([
			["/proj", ["set", "--game=D:\\My Game", "--engine=D:\\UE5", "--vcs=p4", "--uproject=D:\\My Game\\X.uproject"]],
		]);
		// The next-spawn reminder rides along on success.
		expect(ctx.notifications.some((n) => n.includes("next worker spawn"))).toBe(true);
	});

	it("set without --game shows usage and runs nothing", async () => {
		let ran = false;
		const ctx = fakeCmdCtx();
		await runMwTargetCommand(ctx.ctx, "/proj", "set --engine D:\\UE5", () => {
			ran = true;
			return { ok: true, output: "" };
		});
		expect(ran).toBe(false);
		expect(ctx.notifications.some((n) => n.startsWith("Usage: /mw target set"))).toBe(true);
	});

	it("unknown action shows the general usage", async () => {
		const ctx = fakeCmdCtx();
		await runMwTargetCommand(ctx.ctx, "/proj", "frobnicate", () => ({ ok: true, output: "" }));
		expect(ctx.notifications.some((n) => n.startsWith("Usage: /mw target show"))).toBe(true);
	});

	it("runner failure notifies an error", async () => {
		const ctx = fakeCmdCtx();
		await runMwTargetCommand(ctx.ctx, "/proj", "clear", () => ({ ok: false, error: "target.yml is read-only" }));
		expect(ctx.notifications.some((n) => n.includes("mw target clear failed") && n.includes("read-only"))).toBe(true);
	});

	it("splitCommandLine honors double quotes and collapses whitespace", () => {
		expect(splitCommandLine('set --game "D:\\My Game"  --engine  D:\\UE5')).toEqual([
			"set",
			"--game",
			"D:\\My Game",
			"--engine",
			"D:\\UE5",
		]);
		expect(splitCommandLine("")).toEqual([]);
		expect(splitCommandLine('   "a b"   ')).toEqual(["a b"]);
	});
});

describe("/mw partition (partition-workspace config)", () => {
	it("show/clear/on/off forward to mw.py partition with the control root as --project", async () => {
		const calls: Array<[string, string[]]> = [];
		const ctx = fakeCmdCtx();
		for (const action of ["show", "clear", "on", "off"] as const) {
			await runMwPartitionCommand(ctx.ctx, "/proj", action, (projectDir, args) => {
				calls.push([projectDir, args]);
				return { ok: true, output: "[mw partition] mode: partition (source: target-yml)" };
			});
		}
		expect(calls).toEqual([
			["/proj", ["show"]],
			["/proj", ["clear"]],
			["/proj", ["on"]],
			["/proj", ["off"]],
		]);
		expect(ctx.notifications.some((n) => n.includes("mode: partition"))).toBe(true);
	});

	it("set parses quoted paths and repeated --root, forwarding the CLI flag grammar in order", async () => {
		// Arg-sequence parity with `mw.py partition set` (AC-012): the flags are
		// exactly --parent/--partition/--vcs/--root (repeatable); the forwarded
		// sequence hits the same mw.py entry point a direct CLI run would, so
		// identical args ⇒ identical target.yml bytes (byte determinism is
		// asserted on the Python side — test_mw_partition.py).
		const calls: Array<[string, string[]]> = [];
		const ctx = fakeCmdCtx();
		await runMwPartitionCommand(
			ctx.ctx,
			"/proj",
			'set --parent "D:\\Big Project" --partition D:\\combat --root sdk=D:\\SDK --root tools=D:\\Tools --vcs git',
			(projectDir, args) => {
				calls.push([projectDir, args]);
				return { ok: true, output: "[mw partition] mode: partition" };
			},
		);
		expect(calls).toEqual([
			[
				"/proj",
				[
					"set",
					"--parent=D:\\Big Project",
					"--partition=D:\\combat",
					"--vcs=git",
					"--root=sdk=D:\\SDK",
					"--root=tools=D:\\Tools",
				],
			],
		]);
		// The next-spawn reminder rides along on success.
		expect(ctx.notifications.some((n) => n.includes("next worker spawn"))).toBe(true);
	});

	it("set without --parent shows usage and runs nothing", async () => {
		let ran = false;
		const ctx = fakeCmdCtx();
		await runMwPartitionCommand(ctx.ctx, "/proj", "set --partition D:\\combat", () => {
			ran = true;
			return { ok: true, output: "" };
		});
		expect(ran).toBe(false);
		expect(ctx.notifications.some((n) => n.startsWith("Usage: /mw partition set"))).toBe(true);
	});

	it("set with a flag missing its value shows usage and runs nothing", async () => {
		let ran = false;
		const ctx = fakeCmdCtx();
		await runMwPartitionCommand(ctx.ctx, "/proj", "set --parent D:\\p --vcs", () => {
			ran = true;
			return { ok: true, output: "" };
		});
		expect(ran).toBe(false);
		expect(ctx.notifications.some((n) => n.startsWith("Usage: /mw partition set"))).toBe(true);
	});

	it("unknown verb shows the general usage", async () => {
		const ctx = fakeCmdCtx();
		await runMwPartitionCommand(ctx.ctx, "/proj", "frobnicate", () => ({ ok: true, output: "" }));
		expect(ctx.notifications.some((n) => n.startsWith("Usage: /mw partition show"))).toBe(true);
	});

	it("runner failure notifies an error", async () => {
		const ctx = fakeCmdCtx();
		await runMwPartitionCommand(ctx.ctx, "/proj", "on", () => ({
			ok: false,
			error: "[mw partition on] Error: no partition block — run `mw partition set ...` first",
		}));
		expect(
			ctx.notifications.some((n) => n.includes("mw partition on failed") && n.includes("no partition block")),
		).toBe(true);
	});
});

describe("/mw model (dispatch model defaults)", () => {
	it("show forwards to mw.py model show with the control root as --project", async () => {
		const calls: Array<[string, string[]]> = [];
		const ctx = fakeCmdCtx();
		await runMwModelCommand(ctx.ctx, "/proj", "show", (projectDir, args) => {
			calls.push([projectDir, args]);
			return { ok: true, output: "config: /proj/.mw/dispatch.yml\nwindow model: timi/glm-5.3" };
		});
		expect(calls).toEqual([["/proj", ["show"]]]);
		expect(ctx.notifications.some((n) => n.includes("window model"))).toBe(true);
	});

	it("bare /mw model defaults to show", async () => {
		const calls: Array<[string, string[]]> = [];
		const ctx = fakeCmdCtx();
		await runMwModelCommand(ctx.ctx, "/proj", "", (projectDir, args) => {
			calls.push([projectDir, args]);
			return { ok: true, output: "" };
		});
		expect(calls).toEqual([["/proj", ["show"]]]);
	});

	it("set forwards role and value, reminding when it takes effect", async () => {
		const calls: Array<[string, string[]]> = [];
		const ctx = fakeCmdCtx();
		await runMwModelCommand(ctx.ctx, "/proj", "set review timi/glm-5.3-air", (projectDir, args) => {
			calls.push([projectDir, args]);
			return { ok: true, output: "[mw model set] review = timi/glm-5.3-air → /proj/.mw/dispatch.yml" };
		});
		expect(calls).toEqual([["/proj", ["set", "review", "timi/glm-5.3-air"]]]);
		// The next-spawn / next-window-start reminder rides along on success.
		expect(ctx.notifications.some((n) => n.includes("next spawn"))).toBe(true);
	});

	it("set with a missing role or value shows usage and runs nothing", async () => {
		let ran = false;
		const ctx = fakeCmdCtx();
		await runMwModelCommand(ctx.ctx, "/proj", "set review", () => {
			ran = true;
			return { ok: true, output: "" };
		});
		expect(ran).toBe(false);
		expect(ctx.notifications.some((n) => n.startsWith("Usage: /mw model set"))).toBe(true);
	});

	it("clear requires an explicit role or all", async () => {
		let ran = false;
		const ctx = fakeCmdCtx();
		await runMwModelCommand(ctx.ctx, "/proj", "clear", () => {
			ran = true;
			return { ok: true, output: "" };
		});
		expect(ran).toBe(false);
		expect(ctx.notifications.some((n) => n.startsWith("Usage: /mw model clear"))).toBe(true);

		const calls: Array<[string, string[]]> = [];
		await runMwModelCommand(ctx.ctx, "/proj", "clear all", (projectDir, args) => {
			calls.push([projectDir, args]);
			return { ok: true, output: "[mw model clear] removed all roles" };
		});
		expect(calls).toEqual([["/proj", ["clear", "all"]]]);
	});

	it("unknown action shows the general usage", async () => {
		const ctx = fakeCmdCtx();
		await runMwModelCommand(ctx.ctx, "/proj", "frobnicate", () => ({ ok: true, output: "" }));
		expect(ctx.notifications.some((n) => n.startsWith("Usage: /mw model show"))).toBe(true);
	});

	it("runner failure notifies an error", async () => {
		const ctx = fakeCmdCtx();
		await runMwModelCommand(ctx.ctx, "/proj", "set review nope/x", () => ({
			ok: false,
			error: "[mw model set] Error: unknown prefix 'nope'",
		}));
		expect(ctx.notifications.some((n) => n.includes("mw model set failed") && n.includes("unknown prefix"))).toBe(
			true,
		);
	});

	it("the /mw slash command routes the model subcommand (missing-wiring regression)", async () => {
		const root = mkdtemp();
		const { pi, commands } = fakeCmdPi();
		registerMwCommands(pi, root, new WorkerStore(root), new AckStore(root), { key: undefined }, root);
		const handler = commands.get("mw");
		if (!handler) throw new Error("mw command not registered");
		const { ctx, notifications } = fakeCmdCtx();

		// Before the wiring, "model" fell through to the general /mw usage line.
		await handler("model set", ctx);
		expect(notifications.some((n) => n.startsWith("Usage: /mw model set"))).toBe(true);
		expect(notifications.some((n) => n.startsWith("Usage: /mw build"))).toBe(false);

		await handler("model frobnicate", ctx);
		expect(notifications.some((n) => n.startsWith("Usage: /mw model show"))).toBe(true);
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── Dispatch model config (mw-dispatch-models) ───────────────────────────

describe("dispatch model config", () => {
	// Mirror of mw_common.MODEL_PREFIX_TO_PI_PROVIDER (inverse direction).
	// The Python-side lock lives in test_dispatch_models.py — keep both tables
	// equal when a provider joins the namespace.
	const PY_PREFIX_MAP: Record<string, string> = {
		timi: "timi",
		anthropic: "claude",
		"openai-codex": "codex",
		deepseek: "deepseek",
		"zai-coding-cn": "zai",
	};

	it("PROVIDER_ID_TO_PREFIX stays in sync with the Python map", () => {
		expect(PROVIDER_ID_TO_PREFIX).toEqual(PY_PREFIX_MAP);
		for (const [provider, prefix] of Object.entries(PY_PREFIX_MAP)) {
			expect(PREFIX_TO_PROVIDER_ID[prefix]).toBe(provider);
		}
	});

	it("parseModelValue splits prefix and bare values", () => {
		expect(parseModelValue("timi/glm-5.3")).toEqual({ prefix: "timi", modelId: "glm-5.3" });
		expect(parseModelValue("codex_cli/gpt-5.6-sol")).toEqual({ prefix: "codex_cli", modelId: "gpt-5.6-sol" });
		expect(parseModelValue("glm-5.3")).toEqual({ prefix: "", modelId: "glm-5.3" });
	});

	it("recordWindowModel writes prefix/model only in framework projects", () => {
		const root = mkdtemp();
		const model = { provider: "anthropic", id: "claude-sonnet-5" } as unknown as Model<any>;
		// No .agenticdoc → no write, no .mw dir (the extension is global; random
		// projects must stay untouched).
		recordWindowModel(root, model);
		expect(fs.existsSync(path.join(root, ".mw"))).toBe(false);

		fs.mkdirSync(path.join(root, ".agenticdoc"));
		recordWindowModel(root, model);
		expect(fs.readFileSync(windowModelPath(root), "utf8")).toBe("claude/claude-sonnet-5\n");

		// Unmapped provider (e.g. openrouter) is inert on the Python side → skip.
		recordWindowModel(root, { provider: "openrouter", id: "x" } as unknown as Model<any>);
		expect(fs.readFileSync(windowModelPath(root), "utf8")).toBe("claude/claude-sonnet-5\n");
	});

	it("readMainModelConfig parses the mw-model-owned format", () => {
		const root = mkdtemp();
		expect(readMainModelConfig(root)).toBeNull();
		fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
		fs.writeFileSync(
			path.join(root, ".mw", "dispatch.yml"),
			"models:\n  coding: timi/glm-5.3\n  main: timi/glm-5.3\n  review: timi/glm-5.3-air\n",
			"utf8",
		);
		expect(readMainModelConfig(root)).toBe("timi/glm-5.3");
		fs.writeFileSync(path.join(root, ".mw", "dispatch.yml"), "models:\n  coding: timi/glm-5.3\n", "utf8");
		expect(readMainModelConfig(root)).toBeNull();
	});

	it("settingsDefaultModel reads the agent dir settings", () => {
		const agentDir = mkdtemp();
		vi.stubEnv("PI_CODING_AGENT_DIR", agentDir);
		try {
			expect(settingsDefaultModel()).toBeNull();
			fs.writeFileSync(path.join(agentDir, "settings.json"), '{"defaultModel": "claude-sonnet-4-20250514"}', "utf8");
			expect(settingsDefaultModel()).toBe("claude-sonnet-4-20250514");
		} finally {
			vi.unstubAllEnvs();
		}
	});

	it("applyMainModelConfig: explicit user choices always win", async () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, ".agenticdoc"));
		fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
		fs.writeFileSync(path.join(root, ".mw", "dispatch.yml"), "models:\n  main: timi/glm-5.3\n", "utf8");
		const model = { provider: "timi", id: "glm-5.3" } as unknown as Model<any>;
		const setModel = vi.fn(async () => true);
		const notifications: string[] = [];
		const pi = { setModel } as unknown as ExtensionAPI;
		const mkCtx = (): ExtensionContext =>
			({
				cwd: root,
				model: undefined,
				modelRegistry: {
					find: (p: string, id: string) => (p === "timi" && id === "glm-5.3" ? model : undefined),
				},
				ui: { notify: (m: string) => notifications.push(m) },
			}) as unknown as ExtensionContext;

		const argv = process.argv;
		try {
			// No flag, no settings default → applies.
			vi.stubEnv("PI_CODING_AGENT_DIR", mkdtemp()); // no settings.json there
			await applyMainModelConfig(pi, mkCtx());
			expect(setModel).toHaveBeenCalledTimes(1);
			expect(setModel).toHaveBeenCalledWith(model);
			expect(notifications.some((n) => n.includes("dispatch.yml main"))).toBe(true);

			// settings.json defaultModel wins → no application.
			const agentDir = mkdtemp();
			fs.writeFileSync(path.join(agentDir, "settings.json"), '{"defaultModel": "x"}', "utf8");
			vi.stubEnv("PI_CODING_AGENT_DIR", agentDir);
			setModel.mockClear();
			await applyMainModelConfig(pi, mkCtx());
			expect(setModel).not.toHaveBeenCalled();

			// --model flag wins → no application.
			vi.stubEnv("PI_CODING_AGENT_DIR", mkdtemp());
			process.argv = ["pi", "--model", "glm-4"];
			await applyMainModelConfig(pi, mkCtx());
			expect(setModel).not.toHaveBeenCalled();
		} finally {
			vi.unstubAllEnvs();
			process.argv = argv;
		}
	});

	it("applyMainModelConfig: unknown model notifies and leaves the window alone", async () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
		fs.writeFileSync(path.join(root, ".mw", "dispatch.yml"), "models:\n  main: timi/nope\n", "utf8");
		const setModel = vi.fn(async () => true);
		const notifications: string[] = [];
		const pi = { setModel } as unknown as ExtensionAPI;
		const ctx = {
			cwd: root,
			modelRegistry: { find: () => undefined },
			ui: { notify: (m: string) => notifications.push(m) },
		} as unknown as ExtensionContext;
		vi.stubEnv("PI_CODING_AGENT_DIR", mkdtemp());
		try {
			await applyMainModelConfig(pi, ctx);
		} finally {
			vi.unstubAllEnvs();
		}
		expect(setModel).not.toHaveBeenCalled();
		expect(notifications.some((n) => n.includes("not found"))).toBe(true);
	});

	it("formatDoctorReport renders the dispatch row (silent when unset)", () => {
		const base: DoctorJson = {
			service: { running: true, pid: 1 },
			proxy: [],
			orphan_proxy: { detected: false, ports: [] },
			launcher_log: { exists: false, tail: [], error_count: 0, fatal: false },
			queue: { non_terminal: [], stale_count: 0, archived_total: 0 },
			credentials: { routes: [] },
			bundle: { available: true, stale: false },
			summary: { healthy: true, issues: [], suggestions: [] },
		};
		expect(formatDoctorReport(base, false)).not.toContain("派发模型");
		const withDispatch: DoctorJson = {
			...base,
			dispatch: { exists: true, models: { coding: "timi/glm-5.3" }, window_model: "claude/claude-sonnet-5" },
		};
		expect(formatDoctorReport(withDispatch, false)).toContain(
			"派发模型: coding=timi/glm-5.3; 窗口模型 claude/claude-sonnet-5",
		);
		const broken: DoctorJson = {
			...base,
			dispatch: { exists: true, models: {}, window_model: "", error: "dispatch.yml unreadable: boom" },
		};
		expect(formatDoctorReport(broken, false)).toContain("派发模型: 配置错误 — dispatch.yml unreadable: boom");
	});
});

describe("dispatch role + model override gate (mw-dispatch-role-escape)", () => {
	function fakeRegistry(entries: Array<{ provider: string; id: string }>): ModelRegistry {
		const models = entries.map((e) => ({ ...e }) as unknown as Model<any>);
		return {
			getAll: () => models,
			find: (provider: string, modelId: string) => models.find((m) => m.provider === provider && m.id === modelId),
		} as unknown as ModelRegistry;
	}

	const TIMI = (): ModelRegistry =>
		fakeRegistry([
			{ provider: "timi", id: "gpt-5.6-sol" },
			{ provider: "timi", id: "gpt-5.6-luna" },
			{ provider: "timi", id: "deepseek-v4.1-flash" },
		]);

	function writeDispatchYml(root: string, body: string): void {
		fs.mkdirSync(path.join(root, ".mw"), { recursive: true });
		fs.writeFileSync(path.join(root, ".mw", "dispatch.yml"), body, "utf8");
	}

	/** dispatch_worker fixture: documented key "k" claimed by this window. */
	async function setupTool(dispatchYml?: string): Promise<{
		root: string;
		execute: (params: Record<string, unknown>, registry?: ModelRegistry) => Promise<string>;
	}> {
		const root = mkdtemp();
		const ws = new WorkerStore(root);
		const is = new IndexStore(root);
		if (dispatchYml !== undefined) writeDispatchYml(root, dispatchYml);
		const { pi, tools } = fakeCmdPi();
		writePhaseDocs(root, "k");
		await seedKey(root, "k", windowClaimId());
		registerWorkerTools(pi, ws, new AckStore(root), is, root, { key: "k" }, root);
		const tool = tools.get("dispatch_worker");
		if (!tool) throw new Error("dispatch_worker not registered");
		return {
			root,
			execute: async (params, registry) => {
				const ctx =
					registry === undefined
						? fakeCmdCtx().ctx
						: ({ ...fakeCmdCtx().ctx, modelRegistry: registry } as unknown as ExtensionContext);
				return (await tool.execute("id", params, undefined, undefined, ctx)).content[0]?.text ?? "";
			},
		};
	}

	/** /worker command fixture (same documented + claimed key). */
	async function setupCommand(dispatchYml?: string): Promise<{
		root: string;
		run: (args: string, registry?: ModelRegistry) => Promise<string[]>;
	}> {
		const root = mkdtemp();
		const ws = new WorkerStore(root);
		const is = new IndexStore(root);
		if (dispatchYml !== undefined) writeDispatchYml(root, dispatchYml);
		const { pi, commands } = fakeCmdPi();
		writePhaseDocs(root, "k");
		await seedKey(root, "k", windowClaimId());
		registerWorkerCommands(pi, ws, is, root, { key: "k" }, root);
		const handler = commands.get("worker");
		if (!handler) throw new Error("/worker not registered");
		return {
			root,
			run: async (args, registry) => {
				const { ctx, notifications } = fakeCmdCtx();
				const withRegistry =
					registry === undefined
						? ctx
						: ({ ...ctx, modelRegistry: registry } as unknown as ExtensionCommandContext);
				await handler(args, withRegistry);
				return notifications;
			},
		};
	}

	function taskMdOf(root: string, taskKey: string): string {
		return fs.readFileSync(path.join(root, "k", "workers", taskKey, "task.md"), "utf8");
	}

	function workerDirExists(root: string, taskKey: string): boolean {
		return fs.existsSync(path.join(root, "k", "workers", taskKey));
	}

	it("VC-001: dispatch_worker declares type, keeps legacy defaults, refuses an unknown type", async () => {
		const declared = await setupTool();
		const r1 = await declared.execute({ task_key: "t1", description: "work", type: "review" });
		expect(taskMdOf(declared.root, "t1").startsWith("type: review\n")).toBe(true);
		expect(r1).toContain("type: review, role: review");
		fs.rmSync(declared.root, { recursive: true, force: true });

		const legacyPi = await setupTool();
		await legacyPi.execute({ task_key: "t1", description: "work" });
		expect(taskMdOf(legacyPi.root, "t1").startsWith("type: coding\n")).toBe(true);
		fs.rmSync(legacyPi.root, { recursive: true, force: true });

		const legacyCodex = await setupTool();
		await legacyCodex.execute({ task_key: "t1", description: "work", cli: "codex" });
		expect(taskMdOf(legacyCodex.root, "t1").startsWith("type: codex\n")).toBe(true);
		fs.rmSync(legacyCodex.root, { recursive: true, force: true });

		const bad = await setupTool();
		const r4 = await bad.execute({ task_key: "t1", description: "work", type: "deploy" });
		expect(r4).toContain("Invalid type 'deploy'");
		expect(r4).toContain("coding, review, research");
		expect(workerDirExists(bad.root, "t1")).toBe(false);
		expect(fs.existsSync(path.join(bad.root, "_workers.parallel"))).toBe(false);
		fs.rmSync(bad.root, { recursive: true, force: true });
	});

	it("VC-002: /worker --type reaches the review role and echoes it; unknown type is refused", async () => {
		const declared = await setupCommand();
		const notes = await declared.run("pi --type review --key k review the diff");
		const workers = fs.readdirSync(path.join(declared.root, "k", "workers"));
		expect(workers).toHaveLength(1);
		const taskKey = workers[0] as string;
		expect(taskMdOf(declared.root, taskKey).startsWith("type: review\n")).toBe(true);
		expect(notes.join("\n")).toContain("[type: review, role: review,");
		fs.rmSync(declared.root, { recursive: true, force: true });

		const bad = await setupCommand();
		const badNotes = await bad.run("pi --type deploy --key k do work");
		expect(badNotes.join("\n")).toContain("Invalid type 'deploy'");
		expect(fs.existsSync(path.join(bad.root, "k", "workers"))).toBe(false);
		fs.rmSync(bad.root, { recursive: true, force: true });
	});

	it("VC-003: an override of a configured role default requires model_reason and is recorded", async () => {
		const yml = "models:\n  review: timi/gpt-5.6-sol\n";
		const missing = await setupTool(yml);
		const refused = await missing.execute({
			task_key: "t1",
			description: "work",
			type: "review",
			model: "timi/gpt-5.6-luna",
		});
		expect(refused).toContain("needs model_reason");
		expect(refused).toContain("review=timi/gpt-5.6-sol");
		expect(workerDirExists(missing.root, "t1")).toBe(false);
		fs.rmSync(missing.root, { recursive: true, force: true });

		const withReason = await setupTool(yml);
		const accepted = await withReason.execute({
			task_key: "t1",
			description: "work",
			type: "review",
			model: "timi/gpt-5.6-luna",
			model_reason: "luna has the longer context this diff needs",
		});
		const md = taskMdOf(withReason.root, "t1");
		expect(md).toContain("model: timi/gpt-5.6-luna\n");
		expect(md).toContain("model-reason: luna has the longer context this diff needs\n");
		expect(accepted).toContain("model override: role default review=timi/gpt-5.6-sol -> timi/gpt-5.6-luna");
		fs.rmSync(withReason.root, { recursive: true, force: true });

		const multiline = await setupTool(yml);
		await multiline.execute({
			task_key: "t1",
			description: "work",
			type: "review",
			model: "timi/gpt-5.6-luna",
			model_reason: "line one\nline two",
		});
		expect(taskMdOf(multiline.root, "t1")).toContain("model-reason: line one line two\n");
		fs.rmSync(multiline.root, { recursive: true, force: true });
	});

	it("VC-004: a request equal to the configured default is not pinned in task.md", async () => {
		const root = await setupTool("models:\n  coding: timi/deepseek-v4.1-flash\n");
		const r = await root.execute({
			task_key: "t1",
			description: "work",
			model: "timi/deepseek-v4.1-flash",
		});
		const md = taskMdOf(root.root, "t1");
		expect(md.startsWith("type: coding\n")).toBe(true);
		expect(md).not.toContain("model:");
		expect(r).toContain("requested value matches the configured default");
		fs.rmSync(root.root, { recursive: true, force: true });
	});

	it("VC-005: validateModelValue rejects unknown ids and unknown prefixes only", () => {
		const registry = TIMI();
		expect(validateModelValue(registry, "pi", "timi", "timi/gpt-5.6.sol").ok).toBe(false);
		expect(validateModelValue(registry, "pi", "timi", "timi/gpt-5.6.sol").message).toContain(
			"not found for provider 'timi'",
		);
		expect(validateModelValue(registry, "pi", "timi", "timi/gpt-5.6-sol").ok).toBe(true);
		expect(validateModelValue(registry, "pi", "timi", "gpt-5.6-sol").ok).toBe(true);
		expect(validateModelValue(registry, "pi", "nope", "gpt-5.6-sol").ok).toBe(true);
		expect(validateModelValue(registry, "pi", "timi", "openrouter/gpt-5.6-sol").ok).toBe(false);
		expect(validateModelValue(registry, "pi", "timi", "openrouter/gpt-5.6-sol").message).toContain("unknown prefix");
		expect(validateModelValue(registry, "pi", "timi", "codex_cli/gpt-5.6-sol").ok).toBe(true);
		expect(validateModelValue(registry, "codex", "timi", "gpt-5.6.sol").ok).toBe(true);
		expect(validateModelValue(undefined, "pi", "timi", "timi/gpt-5.6.sol").ok).toBe(true);
		expect(validateModelValue(registry, "pi", "timi", "").ok).toBe(true);
	});

	it("VC-006: an unresolvable configured role default fails closed; an explicit model is the escape hatch", async () => {
		const yml = "models:\n  coding: timi/gpt-5.6.sol\n";
		const blocked = await setupTool(yml);
		const refused = await blocked.execute({ task_key: "t1", description: "work" }, TIMI());
		expect(refused).toContain("not found for provider 'timi'");
		expect(workerDirExists(blocked.root, "t1")).toBe(false);
		fs.rmSync(blocked.root, { recursive: true, force: true });

		const escaped = await setupTool(yml);
		const ok = await escaped.execute(
			{
				task_key: "t1",
				description: "work",
				model: "timi/gpt-5.6-sol",
				model_reason: "config value is a typo; tracker ticket INF-42",
			},
			TIMI(),
		);
		expect(ok).toContain("model override");
		expect(taskMdOf(escaped.root, "t1")).toContain("model: timi/gpt-5.6-sol\n");
		fs.rmSync(escaped.root, { recursive: true, force: true });
	});

	it("VC-007: readRoleModel parses per-role values and readMainModelConfig is unchanged", () => {
		const root = mkdtemp();
		expect(readRoleModel(root, "review")).toBeNull();
		writeDispatchYml(
			root,
			"models:\n  coding: timi/deepseek-v4.1-flash\n  main: timi/glm-5.3\n  review: timi/gpt-5.6-sol\n",
		);
		expect(readRoleModel(root, "coding")).toBe("timi/deepseek-v4.1-flash");
		expect(readRoleModel(root, "review")).toBe("timi/gpt-5.6-sol");
		expect(readRoleModel(root, "research")).toBeNull();
		expect(readRoleModel(root, "main")).toBe(readMainModelConfig(root));
		expect(roleForTaskType("verifier")).toBe("review");
		expect(roleForTaskType("unknown-type")).toBe("coding");
		expect(DISPATCH_ROLE_BY_TYPE.review).toBe("review");
		expect(resolveDispatchType("pi", "")).toEqual({ ok: true, type: "coding" });
		expect(resolveDispatchType("claude", "")).toEqual({ ok: true, type: "review" });
		expect(resolveDispatchType("pi", "research")).toEqual({ ok: true, type: "research" });
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-008: /mw model set validates a prefixed id before writing", async () => {
		const root = mkdtemp();
		const calls: string[][] = [];
		const runner = (_projectDir: string, args: string[]): MwCliResult => {
			calls.push(args);
			return { ok: true, output: "ok" };
		};
		const bad = fakeCmdCtx();
		await runMwModelCommand(
			{ ...bad.ctx, modelRegistry: TIMI() } as unknown as ExtensionCommandContext,
			root,
			"set review timi/gpt-5.6.sol",
			runner,
		);
		expect(calls).toHaveLength(0);
		expect(bad.notifications.join("\n")).toContain("not found for provider 'timi'");

		const good = fakeCmdCtx();
		await runMwModelCommand(
			{ ...good.ctx, modelRegistry: TIMI() } as unknown as ExtensionCommandContext,
			root,
			"set review timi/gpt-5.6-sol",
			runner,
		);
		expect(calls).toEqual([["set", "review", "timi/gpt-5.6-sol"]]);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-013: a BOM-prefixed dispatch.yml is read like PyYAML reads it", async () => {
		const bomYml = "\uFEFFmodels:\n  review: timi/gpt-5.6-sol\n";
		const reader = mkdtemp();
		writeDispatchYml(reader, bomYml);
		expect(readRoleModel(reader, "review")).toBe("timi/gpt-5.6-sol");
		fs.rmSync(reader, { recursive: true, force: true });

		// The gate must see the configured default through a BOM too, otherwise a
		// hand-edited file silently disabled the reason requirement.
		const gated = await setupTool(bomYml);
		const refused = await gated.execute({
			task_key: "t1",
			description: "work",
			type: "review",
			model: "timi/gpt-5.6-luna",
		});
		expect(refused).toContain("needs model_reason");
		expect(workerDirExists(gated.root, "t1")).toBe(false);
		fs.rmSync(gated.root, { recursive: true, force: true });
	});

	it("VC-010: a legacy dispatch (no type/model) writes byte-identical frontmatter", async () => {
		const legacy = await setupTool();
		await legacy.execute({ task_key: "t1", description: "work" });
		expect(taskMdOf(legacy.root, "t1")).toBe("type: coding\n\nwork\n");
		fs.rmSync(legacy.root, { recursive: true, force: true });
	});
});
