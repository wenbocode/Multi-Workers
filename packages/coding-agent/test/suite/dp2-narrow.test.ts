/**
 * mw-decision-substitution T-07 / design D-011: dp2 checkpoint narrowing.
 *
 * Locked invariants (design §5.4 + card T-07):
 *  1. Only `narrow` may be executed by the machine. `split`, `direct-exec`,
 *     `escalate` and every unknown answer keep the ORIGINAL PM alert — byte for
 *     byte and still with `triggerTurn: true`.
 *  2. Closed states change nothing: no `.mw/decide.json` (complete bypass), a
 *     `dp2-checkpoint-split` row with `enabled=false`, and `mode=suggest` all
 *     deliver the pre-dp2 alert and spend ZERO child processes on the decision.
 *  3. `acted` narrow writes `<taskDir>/steer-dp2.md` and reports through
 *     `displaySummary` (no `triggerTurn` — the PM must not burn a turn).
 *  4. The escalation bound is unchanged: one decision, one wake/steer per task
 *     per PM session, even when newer checkpoints arrive.
 *  5. The structured state is the 8+4 checkpoint fields plus the ≤3-point
 *     trend, carries the dp2 question-set version, and stays under 2000 bytes.
 *
 * Fixtures are pure files + a fake `pi` + a fake `DecideRunner` (the
 * triage-client seam): no provider APIs, keys, or network.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	DP2_CHECKPOINT_ID,
	DP2_CHECKPOINT_QUESTION,
	DP2_NARROW_FALLBACK_LINE,
	DP2_NARROW_MARKER,
	DP2_QUESTIONS_VERSION,
	DP2_STEER_FILE,
	DP2_STEER_REQUEST_HEADER,
	probeDp2TaskLiveness,
	readCheckpointTrend,
	readDp2Authorization,
	startWorkerPollLoop,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import type {
	DecideRunner,
	DecideRunRequest,
	RawDecideRun,
} from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import {
	assertStateMatchesRegistry,
	type PmUiHolder,
	type PmWatchState,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { RUN_SCHEMA } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";
import {
	DP2_CONSUMED_MARKER,
	formatDp2NarrowSteer,
	hasDp2ConsumedMarker,
	workerModeActivate,
} from "../../src/extensions/agent-team-loop/worker/worker-mode.ts";

const OWNER = "mwds-t07";
const TASK = "t07-worker";
const INTERVAL_MS = 100;

const tempDirs: string[] = [];
function mkProject(): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), "mwds-t07-"));
	tempDirs.push(dir);
	return dir;
}

let savedCwd = process.cwd();

beforeEach(() => {
	savedCwd = process.cwd();
});

afterEach(() => {
	process.chdir(savedCwd);
	delete process.env.PI_WORKER_TASK;
	vi.useRealTimers();
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

// ── fixtures ────────────────────────────────────────────────────────────────

function checkpointLine(elapsedS: number, reads: number, writes: number, risk = "mid"): string {
	return (
		`[CHECKPOINT] 2026-10-20T10:00:00Z elapsed=${elapsedS}s reads=${reads} writes=${writes}` +
		` phases=1/3 uniq_targets=2 repeat_top=5 risk=${risk}`
	);
}

function makeTask(
	projectDir: string,
	opts?: { checkpoints?: string[]; header?: string },
): { agenticdocRoot: string; taskDir: string } {
	const agenticdocRoot = path.join(projectDir, ".agenticdoc");
	const taskDir = path.join(agenticdocRoot, OWNER, "workers", TASK);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(
		path.join(taskDir, "task.md"),
		opts?.header ?? "type: coding\nphase: EXECUTE\ntimeout: 40\n\nwork\n",
		"utf8",
	);
	const lines = opts?.checkpoints ?? [checkpointLine(1800, 12, 3)];
	fs.writeFileSync(path.join(taskDir, "trace.log"), `${lines.join("\n")}\n`, "utf8");
	return { agenticdocRoot, taskDir };
}

async function queueRunning(agenticdocRoot: string, taskDir: string): Promise<void> {
	await new WorkerStore(agenticdocRoot).upsert({
		taskKey: TASK,
		status: "running",
		cli: "pi",
		provider: "timi",
		taskPath: path.join(taskDir, "task.md"),
		dispatchedAt: "",
		updatedAt: "",
		model: "",
	});
	await new IndexStore(agenticdocRoot).upsert({
		key: OWNER,
		status: "active",
		phase: "EXECUTE",
		claimId: "1",
		deps: "",
		desc: "",
		updated: new Date().toISOString(),
	});
}

function writeDecideConfig(projectDir: string): void {
	fs.mkdirSync(path.join(projectDir, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(projectDir, ".mw", "decide.json"), `{"enabled": true}\n`, "utf8");
}

function writePoints(projectDir: string, row: unknown): void {
	fs.mkdirSync(path.join(projectDir, ".mw"), { recursive: true });
	fs.writeFileSync(
		path.join(projectDir, ".mw", "decide-points.json"),
		`${JSON.stringify({ version: 1, points: { [DP2_CHECKPOINT_ID]: row } })}\n`,
		"utf8",
	);
}

interface Sent {
	content: string;
	triggerTurn: boolean | undefined;
	customType: string | undefined;
}

function fakePi(): { pi: ExtensionAPI; sent: Sent[] } {
	const sent: Sent[] = [];
	const pi = {
		sendMessage: (message: { content: string; customType?: string }, opts?: { triggerTurn?: boolean }) => {
			sent.push({ content: message.content, triggerTurn: opts?.triggerTurn, customType: message.customType });
		},
		appendEntry: () => undefined,
	} as unknown as ExtensionAPI;
	return { pi, sent };
}

interface RunnerOptions {
	answer?: string;
	/** Aggregated `answers[...].confidence` of the child (AC-016 gate input). */
	confidence?: number;
	/** `payload.mode` echoed by the child. `null` omits the key: a child that
	 * reports no mode must fail closed (no `acted`). Default `auto`. */
	mode?: string | null;
	available?: boolean;
	reason?: string;
	status?: number;
	stdout?: string;
	timedOut?: boolean;
}

function fakeRunner(options: RunnerOptions = {}): { run: DecideRunner; calls: DecideRunRequest[] } {
	const calls: DecideRunRequest[] = [];
	const run: DecideRunner = (request) => {
		calls.push(request);
		const raw = (payload: unknown): RawDecideRun => ({
			status: 0,
			stdout: JSON.stringify(payload),
			stderr: "",
			timedOut: false,
		});
		if (options.timedOut) return { status: null, stdout: "", stderr: "", timedOut: true };
		if (options.status !== undefined && options.status !== 0) {
			return { status: options.status, stdout: "", stderr: "boom", timedOut: false };
		}
		if (options.stdout !== undefined) return { status: 0, stdout: options.stdout, stderr: "", timedOut: false };
		if (options.available === false) return raw({ available: false, reason: options.reason ?? "entry-unavailable" });
		return raw({
			available: true,
			...(options.mode === null ? {} : { mode: options.mode ?? "auto" }),
			confidence_source: "model-self-report",
			answers: { [DP2_CHECKPOINT_QUESTION]: { value: options.answer, confidence: options.confidence ?? 0.8 } },
		});
	};
	return { run, calls };
}

/** Run the real poll loop for `ticks` ticks against this project. */
async function runTicks(projectDir: string, run: DecideRunner | undefined, ticks = 4): Promise<Sent[]> {
	const agenticdocRoot = path.join(projectDir, ".agenticdoc");
	const watch: PmWatchState = { key: OWNER };
	const ui: PmUiHolder = { ctx: undefined };
	const { pi, sent } = fakePi();
	vi.useFakeTimers();
	try {
		const handle = startWorkerPollLoop(
			pi,
			new WorkerStore(agenticdocRoot),
			new AckStore(agenticdocRoot),
			new IndexStore(agenticdocRoot),
			agenticdocRoot,
			watch,
			ui,
			INTERVAL_MS,
			{ projectDir, run },
		);
		vi.advanceTimersByTime(INTERVAL_MS * ticks + 10);
		clearInterval(handle);
	} finally {
		vi.useRealTimers();
	}
	return sent;
}

const ALERT_PREFIX = `[mw] 发散风险：worker '${TASK}' 检查点 risk=mid`;

// ── 1. closed states ────────────────────────────────────────────────────────

describe("dp2 closed states (D-007 / AC-015)", () => {
	it("no .mw/decide.json => zero spawn, alert byte-identical", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir);
		await queueRunning(agenticdocRoot, taskDir);

		const runner = fakeRunner({ answer: "narrow" });
		const sent = await runTicks(projectDir, runner.run);

		expect(runner.calls).toHaveLength(0);
		expect(sent).toHaveLength(1);
		expect(sent[0]?.triggerTurn).toBe(true);
		expect(sent[0]?.content.startsWith(ALERT_PREFIX)).toBe(true);
		expect(fs.existsSync(path.join(taskDir, DP2_STEER_FILE))).toBe(false);
		console.log(`[VERIFY] dp2 closed(no config): spawn=0, alert=${sent[0]?.content.slice(0, 40)}`);
	});

	it("dp2 row enabled=false or an unusable row => zero spawn, same alert", async () => {
		for (const row of [
			{ tier: "P2", enabled: false, mode: "auto" },
			{ tier: "P2", enabled: "yes", mode: "auto" },
			{ tier: "P2", enabled: true, mode: "bogus" },
		]) {
			const projectDir = mkProject();
			const { agenticdocRoot, taskDir } = makeTask(projectDir);
			await queueRunning(agenticdocRoot, taskDir);
			const baseline = await runTicks(projectDir, fakeRunner({ answer: "narrow" }).run);

			writeDecideConfig(projectDir);
			writePoints(projectDir, row);
			const runner = fakeRunner({ answer: "narrow" });
			const sent = await runTicks(projectDir, runner.run);

			expect(runner.calls, JSON.stringify(row)).toHaveLength(0);
			expect(sent[0]?.triggerTurn).toBe(true);
			expect(sent[0]?.content).toBe(baseline[0]?.content);
			expect(fs.existsSync(path.join(taskDir, DP2_STEER_FILE))).toBe(false);
		}
	});

	it("a non-object dp2 row (L2) disables dp2 => zero spawn, same alert", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir);
		await queueRunning(agenticdocRoot, taskDir);
		const baseline = await runTicks(projectDir, fakeRunner({ answer: "narrow" }).run);

		writeDecideConfig(projectDir);
		writePoints(projectDir, "yes");
		const runner = fakeRunner({ answer: "narrow" });
		const sent = await runTicks(projectDir, runner.run);

		// decision_points.py L2 force-off: a row that is not an object disables the
		// dp. Falling back to the registry default here would pay for a child that
		// Python rejects.
		expect(readDp2Authorization(projectDir)).toEqual({ enabled: false, source: "invalid" });
		expect(runner.calls).toHaveLength(0);
		expect(sent).toHaveLength(1);
		expect(sent[0]?.triggerTurn).toBe(true);
		expect(sent[0]?.content).toBe(baseline[0]?.content);
		expect(fs.existsSync(path.join(taskDir, DP2_STEER_FILE))).toBe(false);
		console.log("[VERIFY] dp2 L2 non-object row: spawn=0, alert byte-identical");
	});

	it("readDp2Authorization: registry default / usable row / L2+L3 force-off", () => {
		const projectDir = mkProject();
		expect(readDp2Authorization(projectDir)).toEqual({ enabled: true, source: "default" });
		writeDecideConfig(projectDir);
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "suggest", note: "trial" });
		expect(readDp2Authorization(projectDir)).toEqual({ enabled: true, source: "config" });

		// L2: a present-but-non-object row is OFF, never the registry default.
		writePoints(projectDir, "yes");
		expect(readDp2Authorization(projectDir)).toEqual({ enabled: false, source: "invalid" });

		// L3 (mode/note/tier type) and L5 (enabled type) force the dp off.
		for (const row of [
			{ enabled: true, mode: "auto", note: 5 },
			{ enabled: true, mode: "auto", note: null },
			{ enabled: true, mode: "auto", tier: 7 },
			{ enabled: "yes", mode: "auto" },
			{ enabled: true, mode: "sometimes" },
		]) {
			writePoints(projectDir, row);
			expect(readDp2Authorization(projectDir), JSON.stringify(row)).toEqual({ enabled: false, source: "invalid" });
		}

		// L4/L7 are advisory only: an illegal or differing tier VALUE keeps the row
		// enabled (the registry tier wins in Python).
		writePoints(projectDir, { tier: "P9", enabled: true, mode: "auto" });
		expect(readDp2Authorization(projectDir)).toEqual({ enabled: true, source: "config" });

		writePoints(projectDir, { tier: "P2", enabled: false, mode: "auto" });
		expect(readDp2Authorization(projectDir)).toEqual({ enabled: false, source: "config" });
	});
});

// ── 2. narrow is the only acted action ──────────────────────────────────────

describe("dp2 narrow: acted via steer request + displaySummary", () => {
	it("writes steer-dp2.md and reports without triggerTurn", async () => {
		const projectDir = mkProject();
		// four checkpoints: `#ckpt4` is the trigger, the trend keeps the last 3
		const { agenticdocRoot, taskDir } = makeTask(projectDir, {
			checkpoints: [
				checkpointLine(600, 4, 1),
				checkpointLine(1200, 9, 2),
				checkpointLine(1800, 12, 3),
				checkpointLine(2100, 13, 3),
			],
		});
		await queueRunning(agenticdocRoot, taskDir);
		const baseline = await runTicks(projectDir, fakeRunner({ answer: "narrow" }).run);
		expect(baseline[0]?.content.startsWith(ALERT_PREFIX)).toBe(true);

		writeDecideConfig(projectDir);
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto" });
		const runner = fakeRunner({ answer: "narrow" });
		const sent = await runTicks(projectDir, runner.run);

		const decisionId = `${DP2_CHECKPOINT_ID}:${TASK}#ckpt4`;
		expect(runner.calls).toHaveLength(1);
		expect(sent).toHaveLength(1);
		expect(sent[0]?.triggerTurn).toBeUndefined();
		expect(sent[0]?.customType).toBe("agent-team-loop:worker-summary");
		expect(sent[0]?.content).toContain(`[mw] dp2 已自动收窄 ${TASK}`);
		expect(sent[0]?.content).toContain(`decision_id=${decisionId}`);
		expect(sent[0]?.content).not.toBe(baseline[0]?.content);

		const steer = fs.readFileSync(path.join(taskDir, DP2_STEER_FILE), "utf8");
		expect(steer).toContain("[dp2-narrow-request]");
		expect(steer).toContain(`decision_id=${decisionId}`);
		expect(steer).toContain("risk=mid");
		expect(steer).toContain("[mw dp2-narrow]");

		// T-04d: the executed narrow leaves ONE acted correlation line in the task
		// trace; an un-executed decision (fallback / suggest / disabled) must not.
		const actedTrace = fs
			.readFileSync(path.join(taskDir, "trace.log"), "utf8")
			.split("\n")
			.filter((line) => line.startsWith("[DECISION] dp2 acted=1"));
		expect(actedTrace).toEqual([`[DECISION] dp2 acted=1 decision_id=${decisionId} trigger=${TASK}#ckpt4`]);
		console.log(`[VERIFY] dp2 acted trace: ${actedTrace[0]}`);

		// Structured envelope: registry-owned questions (no `questions` map), dp id,
		// the 8+4 checkpoint fields and the 3-point trend.
		const request = runner.calls[0] as DecideRunRequest;
		expect(request.dp).toBe(DP2_CHECKPOINT_ID);
		const envelope = JSON.parse(request.input) as { state: Record<string, unknown>; questions?: unknown };
		expect(envelope.questions).toBeUndefined();
		const state = envelope.state;
		expect(state.schema_version).toBe(2);
		expect(state.decision_point).toBe(DP2_CHECKPOINT_ID);
		expect(state.key).toBe(OWNER);
		expect(state.task_key).toBeUndefined();
		expect(state.phase).toBe("EXECUTE");
		expect(state.task_type).toBe("coding");
		expect(state.risk).toBe("mid");
		expect(state.risk_source).toBe("machine");
		expect(state.authority_tier).toBe("P2");
		expect(state.questions_version).toBe(DP2_QUESTIONS_VERSION);
		const progress = state.progress as Record<string, unknown>;
		expect(progress.elapsed_minutes).toBe(35);
		expect(progress.budget_minutes).toBe(40);
		expect(progress.phases_done).toBe(1);
		expect(progress.phases_total).toBe(3);
		expect(progress.artifact_present).toBe(true);
		expect(progress.writes).toBe(3);
		expect(progress.uniq_targets).toBe(2);
		expect(progress.repeat_top).toBe(5);
		const trend = progress.trend as Array<Record<string, number>>;
		expect(trend.map((point) => point.elapsed_minutes)).toEqual([20, 30, 35]);
		expect(trend.map((point) => point.reads)).toEqual([9, 12, 13]);
		// W6: the engineered context carries a one-line change summary plus the
		// fs-stated artifact rows (expected outputs first, ≤24).
		const context = state.context as {
			change_summary?: string;
			artifact_status?: Array<{ path: string; exists: boolean; bytes: number }>;
		};
		expect(context.change_summary).toContain("elapsed=35m/40m");
		expect(context.change_summary).toContain("phases=1/3");
		const artifacts = context.artifact_status ?? [];
		expect(artifacts.length).toBeGreaterThan(0);
		expect(artifacts.length).toBeLessThanOrEqual(24);
		const taskMd = artifacts.find((entry) => entry.path === "task.md");
		expect(taskMd?.exists).toBe(true);
		expect(taskMd?.bytes).toBeGreaterThan(0);
		expect(artifacts.find((entry) => entry.path === "output.md")?.exists).toBe(false);
		expect(Buffer.byteLength(request.input, "utf8")).toBeLessThan(2000);
		console.log(`[VERIFY] dp2 narrow: decision=${decisionId}, state=${Buffer.byteLength(request.input)}B`);
	});

	it("assertStateMatchesRegistry rejects a dp2 state that drifts from the registry (W6)", () => {
		const partial: Record<string, unknown> = {
			schema_version: 2,
			decision_point: DP2_CHECKPOINT_ID,
			key: OWNER,
		};
		expect(() => assertStateMatchesRegistry(DP2_CHECKPOINT_ID, partial)).toThrow(/missing=phase/);
		expect(() => assertStateMatchesRegistry(DP2_CHECKPOINT_ID, { ...partial, task_key: TASK })).toThrow(
			/extra=task_key/,
		);
	});

	it("readCheckpointTrend: total count drives #ckpt<N>, only the last 3 are kept", () => {
		const projectDir = mkProject();
		const { taskDir } = makeTask(projectDir, {
			checkpoints: [
				checkpointLine(60, 1, 0),
				checkpointLine(660, 5, 1),
				checkpointLine(1260, 8, 2),
				checkpointLine(1860, 11, 3),
				checkpointLine(2460, 14, 3),
			],
		});
		const series = readCheckpointTrend(taskDir);
		expect(series.total).toBe(5);
		expect(series.points.map((point) => point.elapsedMin)).toEqual([21, 31, 41]);
		expect(readCheckpointTrend(path.join(projectDir, "missing")).total).toBe(0);
	});
});

// ── 3. split / direct / escalate keep the human path ───────────────────────

describe("dp2 non-narrow answers keep the original escalation path", () => {
	for (const answer of ["split", "direct-exec", "escalate", "wait", ""]) {
		it(`answer=${JSON.stringify(answer)} => alert byte-identical + triggerTurn`, async () => {
			const projectDir = mkProject();
			const { agenticdocRoot, taskDir } = makeTask(projectDir);
			await queueRunning(agenticdocRoot, taskDir);
			const baseline = await runTicks(projectDir, fakeRunner({ answer: "narrow" }).run);

			writeDecideConfig(projectDir);
			writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto" });
			const runner = fakeRunner({ answer });
			const sent = await runTicks(projectDir, runner.run);

			expect(runner.calls).toHaveLength(1);
			expect(sent).toHaveLength(1);
			expect(sent[0]?.triggerTurn).toBe(true);
			expect(sent[0]?.content).toBe(baseline[0]?.content);
			expect(fs.existsSync(path.join(taskDir, DP2_STEER_FILE))).toBe(false);
		});
	}

	it("mode=suggest records the answer but never acts (AC-015)", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir);
		await queueRunning(agenticdocRoot, taskDir);
		const baseline = await runTicks(projectDir, fakeRunner({ answer: "narrow" }).run);

		writeDecideConfig(projectDir);
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "suggest" });
		// The child echoes the effective mode; that echo — not the local row — is
		// what the acted verdict consumes (D-036).
		const runner = fakeRunner({ answer: "narrow", mode: "suggest" });
		const sent = await runTicks(projectDir, runner.run);

		expect(runner.calls).toHaveLength(1);
		expect(sent[0]?.triggerTurn).toBe(true);
		expect(sent[0]?.content).toBe(baseline[0]?.content);
		expect(fs.existsSync(path.join(taskDir, DP2_STEER_FILE))).toBe(false);
		// T-04d: suggest never acted, so it never claims `dp2 acted=1`.
		expect(fs.readFileSync(path.join(taskDir, "trace.log"), "utf8")).not.toContain("[DECISION] dp2 acted=1");
	});

	it("acted follows the child's mode, not the local row (D-036)", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir);
		await queueRunning(agenticdocRoot, taskDir);
		const baseline = await runTicks(projectDir, fakeRunner({ answer: "narrow" }).run);

		writeDecideConfig(projectDir);
		// The local mirror says auto (so the child is spawned), Python answers
		// suggest: `suggest` must win — the answer is recorded, nothing is acted.
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto" });
		const runner = fakeRunner({ answer: "narrow", mode: "suggest" });
		const sent = await runTicks(projectDir, runner.run);

		expect(runner.calls).toHaveLength(1);
		expect(sent[0]?.triggerTurn).toBe(true);
		expect(sent[0]?.content).toBe(baseline[0]?.content);
		expect(fs.existsSync(path.join(taskDir, DP2_STEER_FILE))).toBe(false);
		expect(fs.readFileSync(path.join(taskDir, "trace.log"), "utf8")).not.toContain("[DECISION] dp2 acted=1");
		console.log("[VERIFY] dp2 acted: payload.mode=suggest wins over local mode=auto");
	});

	for (const [label, options] of [
		["unavailable", { available: false, reason: "entry-unavailable" }],
		["child exit != 0", { status: 1 }],
		["non-JSON stdout", { stdout: "not json at all" }],
		["timeout", { timedOut: true }],
		["child reports no mode", { answer: "narrow", mode: null }],
	] as Array<[string, RunnerOptions]>) {
		it(`degraded (${label}) => fail-closed onto the alert`, async () => {
			const projectDir = mkProject();
			const { agenticdocRoot, taskDir } = makeTask(projectDir);
			await queueRunning(agenticdocRoot, taskDir);
			const baseline = await runTicks(projectDir, fakeRunner({ answer: "narrow" }).run);

			writeDecideConfig(projectDir);
			writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto" });
			const runner = fakeRunner(options);
			const sent = await runTicks(projectDir, runner.run);

			expect(runner.calls).toHaveLength(1);
			expect(sent[0]?.triggerTurn).toBe(true);
			expect(sent[0]?.content).toBe(baseline[0]?.content);
			expect(fs.existsSync(path.join(taskDir, DP2_STEER_FILE))).toBe(false);
			// T-04d: a degraded path falls back to the alert and records no acted line.
			expect(fs.readFileSync(path.join(taskDir, "trace.log"), "utf8")).not.toContain("[DECISION] dp2 acted=1");
		});
	}
});

// ── 4. once-per-task bound is unchanged ────────────────────────────────────

describe("dp2 escalation bound", () => {
	it("a newer mid/high checkpoint does not decide or wake twice", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir);
		await queueRunning(agenticdocRoot, taskDir);
		writeDecideConfig(projectDir);
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto" });

		const runner = fakeRunner({ answer: "split" });
		const { pi, sent } = fakePi();
		vi.useFakeTimers();
		try {
			const handle = startWorkerPollLoop(
				pi,
				new WorkerStore(agenticdocRoot),
				new AckStore(agenticdocRoot),
				new IndexStore(agenticdocRoot),
				agenticdocRoot,
				{ key: OWNER },
				{ ctx: undefined },
				INTERVAL_MS,
				{ projectDir, run: runner.run },
			);
			vi.advanceTimersByTime(INTERVAL_MS * 4);
			expect(runner.calls).toHaveLength(1);
			expect(sent).toHaveLength(1);

			fs.appendFileSync(path.join(taskDir, "trace.log"), `${checkpointLine(2400, 20, 4, "high")}\n`, "utf8");
			vi.advanceTimersByTime(INTERVAL_MS * 6);
			expect(runner.calls).toHaveLength(1);
			expect(sent).toHaveLength(1);
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
	});

	it("a narrow answer is delivered as one steer request, never twice", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir);
		await queueRunning(agenticdocRoot, taskDir);
		writeDecideConfig(projectDir);
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto" });

		const runner = fakeRunner({ answer: "narrow" });
		const sent = await runTicks(projectDir, runner.run, 8);
		expect(runner.calls).toHaveLength(1);
		expect(sent).toHaveLength(1);
		expect(fs.readFileSync(path.join(taskDir, DP2_STEER_FILE), "utf8")).toContain(
			`${DP2_CHECKPOINT_ID}:${TASK}#ckpt1`,
		);
	});

	it("low-risk checkpoints still never reach dp2", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir, { checkpoints: [checkpointLine(1800, 12, 3, "low")] });
		await queueRunning(agenticdocRoot, taskDir);
		writeDecideConfig(projectDir);
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto" });

		const runner = fakeRunner({ answer: "narrow" });
		const sent = await runTicks(projectDir, runner.run);
		expect(runner.calls).toHaveLength(0);
		expect(sent).toHaveLength(0);
	});

	it("a worker owned by another key never reaches dp2 (ownership gate first)", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir);
		await queueRunning(agenticdocRoot, taskDir);
		writeDecideConfig(projectDir);
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto" });

		const runner = fakeRunner({ answer: "narrow" });
		const { pi, sent } = fakePi();
		vi.useFakeTimers();
		try {
			const handle = startWorkerPollLoop(
				pi,
				new WorkerStore(agenticdocRoot),
				new AckStore(agenticdocRoot),
				new IndexStore(agenticdocRoot),
				agenticdocRoot,
				{ key: "another-key" },
				{ ctx: undefined },
				INTERVAL_MS,
				{ projectDir, run: runner.run },
			);
			vi.advanceTimersByTime(INTERVAL_MS * 4);
			expect(runner.calls).toHaveLength(0);
			expect(sent).toHaveLength(0);
			expect(fs.existsSync(path.join(taskDir, DP2_STEER_FILE))).toBe(false);
			clearInterval(handle);
		} finally {
			vi.useRealTimers();
		}
	});
});

// ── 5. question-set drift guard ────────────────────────────────────────────

describe("dp2 question set", () => {
	it("matches the Python registry (choices + questions_version)", () => {
		const registryPath = fileURLToPath(new URL("../../../multi-workers/decision_points.py", import.meta.url));
		const source = fs.readFileSync(registryPath, "utf8");
		const block = /dp_id="dp2-checkpoint-split"([\s\S]*?)executor=/.exec(source)?.[1] ?? "";
		expect(block).toContain(`"id": "${DP2_CHECKPOINT_QUESTION}"`);
		for (const choice of ["narrow", "split", "direct-exec", "escalate"]) {
			expect(block).toContain(`"${choice}"`);
		}
		// decision_points._questions_version() for exactly this question set.
		expect(DP2_QUESTIONS_VERSION).toBe("q-ba8e970f");
		expect(DP2_QUESTIONS_VERSION).toMatch(/^q-[0-9a-f]{8}$/);
	});
});

// ── 6. worker-side consumer: the steer MUST be read (T-07b / DS-4) ─────────
//
// Before T-07b `steer-dp2.md` had no reader at all: a `narrow` suppressed the PM
// wake and reached nobody, so the task stalled silently (fail-open). These
// tests pin the consumer contract: inject once, never replay, mark the file,
// never inject an empty file, and cover a request that arrives mid-turn.

const CONSUMER_TASK = "t07b-consumer";

function makeConsumerTask(projectDir: string): { taskDir: string; taskPath: string } {
	const taskDir = path.join(projectDir, ".agenticdoc", OWNER, "workers", CONSUMER_TASK);
	fs.mkdirSync(taskDir, { recursive: true });
	fs.writeFileSync(path.join(taskDir, "task.md"), "---\ntype: research\n---\n\nphase: EXECUTE\ndo the work\n", "utf8");
	fs.writeFileSync(path.join(projectDir, ".agenticdoc", "goal.md"), "# Goal\n\nfile-driven coordination\n", "utf8");
	return { taskDir, taskPath: path.join(taskDir, "task.md") };
}

function writeDp2SteerRequestFile(taskDir: string, decisionId: string): string {
	const content = [
		`${DP2_STEER_REQUEST_HEADER} decision_id=${decisionId} dp=${DP2_CHECKPOINT_ID}` +
			" risk=mid elapsed_minutes=35 budget_minutes=40 remaining_min=5",
		`[mw dp2-narrow] dp2 已自动判定收窄本任务（decision_id=${decisionId}）：停止展开新工作，只保留能直接收敛的路径。`,
		"",
	].join("\n");
	fs.writeFileSync(path.join(taskDir, DP2_STEER_FILE), content, "utf8");
	return content;
}

function traceText(taskDir: string): string {
	return fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
}

function consumedMarkerLines(taskDir: string): string[] {
	const file = path.join(taskDir, DP2_STEER_FILE);
	if (!fs.existsSync(file)) return [];
	return fs
		.readFileSync(file, "utf8")
		.split("\n")
		.filter((line) => line.trim().startsWith(DP2_CONSUMED_MARKER));
}

interface WorkerSent {
	text: string;
	options?: { deliverAs?: string };
}

interface FakeWorker {
	pi: ExtensionAPI;
	emit: (name: string, payload?: unknown) => void;
	sent: WorkerSent[];
}

function fakeWorkerPi(): FakeWorker {
	const handlers = new Map<string, Array<(event: unknown) => unknown>>();
	const sent: WorkerSent[] = [];
	const pi = {
		on: (name: string, cb: (event: unknown) => unknown) => {
			const list = handlers.get(name) ?? [];
			list.push(cb);
			handlers.set(name, list);
		},
		sendUserMessage: (text: string, options?: { deliverAs?: string }) => {
			sent.push({ text, options });
		},
		setActiveTools: () => undefined,
		registerTool: () => undefined,
	};
	return {
		pi: pi as unknown as ExtensionAPI,
		emit: (name, payload) => {
			for (const cb of handlers.get(name) ?? []) cb(payload);
		},
		sent,
	};
}

async function startConsumerWorker(taskPath: string, projectDir: string): Promise<FakeWorker> {
	process.env.PI_WORKER_TASK = taskPath;
	process.chdir(projectDir);
	const worker = fakeWorkerPi();
	await workerModeActivate(worker.pi);
	return worker;
}

function settleWorker(worker: FakeWorker, reply: string): void {
	worker.emit("agent_end", { messages: [{ role: "assistant", content: [{ type: "text", text: reply }] }] });
	worker.emit("agent_settled");
}

describe("dp2 narrow consumer (worker side, T-07b)", () => {
	it("injects the steer once as a [mw dp2-narrow] followUp and marks the file tail", async () => {
		const projectDir = mkProject();
		const { taskDir, taskPath } = makeConsumerTask(projectDir);
		const decisionId = `${DP2_CHECKPOINT_ID}:${CONSUMER_TASK}#ckpt1`;
		const request = writeDp2SteerRequestFile(taskDir, decisionId);

		const worker = await startConsumerWorker(taskPath, projectDir);
		worker.emit("before_agent_start");

		expect(worker.sent).toHaveLength(1);
		expect(worker.sent[0]?.text.startsWith(DP2_NARROW_MARKER)).toBe(true);
		expect(worker.sent[0]?.text).toContain("停止展开新工作");
		// the machine transport header is not part of the directive
		expect(worker.sent[0]?.text).not.toContain(DP2_STEER_REQUEST_HEADER);
		expect(worker.sent[0]?.options).toEqual({ deliverAs: "followUp" });

		const after = fs.readFileSync(path.join(taskDir, DP2_STEER_FILE), "utf8");
		// the PM's request body is preserved verbatim; the marker is appended
		expect(after.startsWith(request)).toBe(true);
		expect(hasDp2ConsumedMarker(after)).toBe(true);
		const tail =
			after
				.split("\n")
				.filter((line) => line.trim() !== "")
				.at(-1) ?? "";
		expect(tail.startsWith(`${DP2_CONSUMED_MARKER} ${CONSUMER_TASK}@`)).toBe(true);
		expect(tail).toMatch(/\]\s*$/);
		expect(tail.endsWith("]")).toBe(true);
		expect(consumedMarkerLines(taskDir)).toHaveLength(1);

		expect(traceText(taskDir)).toContain("[DECISION] dp2 consumed=1");
		expect(traceText(taskDir)).toContain(`decision_id=${decisionId}`);
		console.log(`[VERIFY] dp2 consumer: injected once, marker=${tail}`);
	});

	it("a second and third run start never re-inject (idempotent in-process)", async () => {
		const projectDir = mkProject();
		const { taskDir, taskPath } = makeConsumerTask(projectDir);
		writeDp2SteerRequestFile(taskDir, `${DP2_CHECKPOINT_ID}:${CONSUMER_TASK}#ckpt1`);

		const worker = await startConsumerWorker(taskPath, projectDir);
		worker.emit("before_agent_start");
		worker.emit("before_agent_start");
		worker.emit("before_agent_start");

		expect(worker.sent).toHaveLength(1);
		expect(consumedMarkerLines(taskDir)).toHaveLength(1);
	});

	it("a worker restart re-reads the same file and still injects only once", async () => {
		const projectDir = mkProject();
		const { taskDir, taskPath } = makeConsumerTask(projectDir);
		writeDp2SteerRequestFile(taskDir, `${DP2_CHECKPOINT_ID}:${CONSUMER_TASK}#ckpt1`);

		const first = await startConsumerWorker(taskPath, projectDir);
		first.emit("before_agent_start");
		expect(first.sent).toHaveLength(1);
		const firstMarker = consumedMarkerLines(taskDir)[0] ?? "";

		// A fresh process on the same task dir: the file marker is the only state
		// that survives, so it must be enough to suppress the replay.
		const second = await startConsumerWorker(taskPath, projectDir);
		second.emit("before_agent_start");
		expect(second.sent).toHaveLength(0);
		expect(consumedMarkerLines(taskDir)).toEqual([firstMarker]);
	});

	it("an empty request file injects nothing and is not marked", async () => {
		const projectDir = mkProject();
		const { taskDir, taskPath } = makeConsumerTask(projectDir);
		fs.writeFileSync(path.join(taskDir, DP2_STEER_FILE), "", "utf8");

		const worker = await startConsumerWorker(taskPath, projectDir);
		worker.emit("before_agent_start");

		expect(worker.sent).toHaveLength(0);
		expect(fs.readFileSync(path.join(taskDir, DP2_STEER_FILE), "utf8")).toBe("");
		expect(traceText(taskDir)).toContain("[DECISION] dp2 consume-failed reason=empty");
	});

	it("formatDp2NarrowSteer: header-only is not a steer, a bare body gets the prefix", () => {
		expect(formatDp2NarrowSteer("")).toBeUndefined();
		expect(formatDp2NarrowSteer(`${DP2_STEER_REQUEST_HEADER} decision_id=x dp=y\n\n`)).toBeUndefined();
		expect(formatDp2NarrowSteer("narrow the scope")).toBe(`${DP2_NARROW_MARKER} narrow the scope`);
		expect(formatDp2NarrowSteer(`${DP2_NARROW_MARKER} already prefixed`)).toBe(
			`${DP2_NARROW_MARKER} already prefixed`,
		);
	});

	it("a request that arrives mid-turn is consumed at settle and keeps the run open", async () => {
		const projectDir = mkProject();
		const { taskDir, taskPath } = makeConsumerTask(projectDir);

		const worker = await startConsumerWorker(taskPath, projectDir);
		worker.emit("before_agent_start");
		expect(worker.sent).toHaveLength(0);

		// The PM writes the steer while this turn is running.
		writeDp2SteerRequestFile(taskDir, `${DP2_CHECKPOINT_ID}:${CONSUMER_TASK}#ckpt1`);
		settleWorker(worker, "partial work, still exploring");

		expect(worker.sent).toHaveLength(1);
		expect(worker.sent[0]?.text.startsWith(DP2_NARROW_MARKER)).toBe(true);
		expect(traceText(taskDir)).toContain("via=settle");
		// the run stays open so the queued follow-up turn actually executes
		expect(fs.existsSync(path.join(taskDir, "output.md"))).toBe(false);
		const run = JSON.parse(fs.readFileSync(path.join(taskDir, "run.json"), "utf8")) as { status: string };
		expect(run.status).toBe("running");

		// the (now narrower) turn settles again: the second settle lands the product
		settleWorker(worker, "narrowed: delivered what converges");
		expect(worker.sent).toHaveLength(1);
		expect(fs.existsSync(path.join(taskDir, "output.md"))).toBe(true);
	});
});

// ── 7. PM fallback: a settled task goes back to the human (T-07b / DS-4) ────

describe("dp2 narrow falls back to the human alert when the task is not running", () => {
	function writeRunJson(taskDir: string, status: string, extra: Record<string, unknown> = {}): void {
		fs.writeFileSync(
			path.join(taskDir, "run.json"),
			`${JSON.stringify({
				schema: RUN_SCHEMA,
				task_key: TASK,
				run_id: `${TASK}@2026-10-20T10:00:00.000Z`,
				status,
				...extra,
			})}\n`,
			"utf8",
		);
	}

	it("run.json terminal => alert with [dp2-narrow-fallback] and no steer file", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir);
		await queueRunning(agenticdocRoot, taskDir);
		writeRunJson(taskDir, "done");
		writeDecideConfig(projectDir);
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto" });

		const runner = fakeRunner({ answer: "narrow" });
		const sent = await runTicks(projectDir, runner.run);

		expect(runner.calls).toHaveLength(1);
		expect(sent).toHaveLength(1);
		expect(sent[0]?.triggerTurn).toBe(true);
		expect(sent[0]?.content.startsWith(ALERT_PREFIX)).toBe(true);
		expect(sent[0]?.content.endsWith(DP2_NARROW_FALLBACK_LINE)).toBe(true);
		expect(sent[0]?.content).toContain("[dp2-narrow-fallback] task not running; escalated instead");
		// T-04d: the fallback alert is NOT an executed narrow — no acted line.
		expect(fs.readFileSync(path.join(taskDir, "trace.log"), "utf8")).not.toContain("[DECISION] dp2 acted=1");
		expect(fs.existsSync(path.join(taskDir, DP2_STEER_FILE))).toBe(false);
		console.log("[VERIFY] dp2 fallback: settled run => alert, steer=absent");
	});

	it("run.json running with a live pid => the steer is still written", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir);
		await queueRunning(agenticdocRoot, taskDir);
		writeRunJson(taskDir, "running", { pid: process.pid });
		writeDecideConfig(projectDir);
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto" });

		const runner = fakeRunner({ answer: "narrow" });
		const sent = await runTicks(projectDir, runner.run);

		expect(sent).toHaveLength(1);
		expect(sent[0]?.triggerTurn).toBeUndefined();
		expect(sent[0]?.content).toContain("[mw] dp2 已自动收窄");
		const steer = fs.readFileSync(path.join(taskDir, DP2_STEER_FILE), "utf8");
		expect(steer).toContain(DP2_CHECKPOINT_ID);
		expect(steer).not.toContain(DP2_CONSUMED_MARKER);
		// T-04d: a live worker means the narrow really executed -> acted trace.
		expect(fs.readFileSync(path.join(taskDir, "trace.log"), "utf8")).toContain(
			`[DECISION] dp2 acted=1 decision_id=${DP2_CHECKPOINT_ID}:${TASK}#ckpt1 trigger=${TASK}#ckpt1`,
		);
	});

	it("dp2 disabled stays byte-identical even when the run is settled (probe never reached)", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir);
		await queueRunning(agenticdocRoot, taskDir);
		writeRunJson(taskDir, "done");
		const baseline = await runTicks(projectDir, fakeRunner({ answer: "narrow" }).run);

		writeDecideConfig(projectDir);
		writePoints(projectDir, { tier: "P2", enabled: false, mode: "auto" });
		const runner = fakeRunner({ answer: "narrow" });
		const sent = await runTicks(projectDir, runner.run);

		expect(runner.calls).toHaveLength(0);
		expect(sent[0]?.triggerTurn).toBe(true);
		expect(sent[0]?.content).toBe(baseline[0]?.content);
		expect(sent[0]?.content).not.toContain("[dp2-narrow-fallback]");
		expect(fs.existsSync(path.join(taskDir, DP2_STEER_FILE))).toBe(false);
	});

	it("probeDp2TaskLiveness: terminal / live / dead-pid / unknown", () => {
		const projectDir = mkProject();
		const { taskDir } = makeTask(projectDir);
		expect(probeDp2TaskLiveness(taskDir, "running")).toBe("running"); // no run.json: the ledger row decides

		writeRunJson(taskDir, "done");
		expect(probeDp2TaskLiveness(taskDir, "running")).toBe("settled");

		writeRunJson(taskDir, "running", { pid: process.pid });
		expect(probeDp2TaskLiveness(taskDir, "done")).toBe("running");

		// an active record whose pid is gone is a stale record, not a live worker
		writeRunJson(taskDir, "running", { pid: 2_147_483_647 });
		expect(probeDp2TaskLiveness(taskDir, "running")).toBe("settled");

		fs.writeFileSync(path.join(taskDir, "run.json"), "not json\n", "utf8");
		expect(probeDp2TaskLiveness(taskDir, "weird-status")).toBe("unknown");
	});
});

// ���� AC-016: per-dp policy knobs (min_confidence / max_questions / timeout_s)

describe("dp2 per-dp policy knobs (AC-016)", () => {
	it("a per-dp min_confidence above the child confidence keeps the human alert", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir, {
			checkpoints: [checkpointLine(600, 4, 1), checkpointLine(1200, 9, 2), checkpointLine(1800, 12, 3)],
		});
		await queueRunning(agenticdocRoot, taskDir);
		writeDecideConfig(projectDir);
		// The child answers `narrow` at 0.8: the built-in gate (0.7) would act,
		// this row (0.95) must not. Python applies the same threshold before it
		// can report `auto`, so the TS mirror stays on the human alert.
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto", min_confidence: 0.95 });
		const runner = fakeRunner({ answer: "narrow", confidence: 0.8 });
		const sent = await runTicks(projectDir, runner.run);

		expect(runner.calls).toHaveLength(1);
		expect(sent).toHaveLength(1);
		expect(sent[0]?.content.startsWith(ALERT_PREFIX)).toBe(true);
		expect(sent[0]?.triggerTurn).toBe(true);
		expect(fs.existsSync(path.join(taskDir, DP2_STEER_FILE))).toBe(false);
		const trace = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
		expect(trace).not.toContain("[DECISION] dp2 acted=1");
	});

	it("the same answer acts under the built-in 0.7 gate", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir, {
			checkpoints: [checkpointLine(600, 4, 1), checkpointLine(1200, 9, 2), checkpointLine(1800, 12, 3)],
		});
		await queueRunning(agenticdocRoot, taskDir);
		writeDecideConfig(projectDir);
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto" });
		const runner = fakeRunner({ answer: "narrow", confidence: 0.8 });
		const sent = await runTicks(projectDir, runner.run);

		expect(runner.calls).toHaveLength(1);
		expect(sent).toHaveLength(1);
		expect(sent[0]?.triggerTurn).toBeUndefined();
		expect(fs.readFileSync(path.join(taskDir, DP2_STEER_FILE), "utf8")).toContain("[dp2-narrow-request]");
	});

	it("a per-dp timeout_s drives the child budget (300s cap respected)", async () => {
		const projectDir = mkProject();
		const { agenticdocRoot, taskDir } = makeTask(projectDir, {
			checkpoints: [checkpointLine(600, 4, 1), checkpointLine(1200, 9, 2), checkpointLine(1800, 12, 3)],
		});
		await queueRunning(agenticdocRoot, taskDir);
		writeDecideConfig(projectDir);
		writePoints(projectDir, { tier: "P2", enabled: true, mode: "auto", timeout_s: 45 });
		const runner = fakeRunner({ answer: "escalate" });
		await runTicks(projectDir, runner.run);

		expect(runner.calls[0]?.timeoutMs).toBe(45_000);
	});
});
