/**
 * mw-decision-substitution T-08 — decision association (spec §6.1/§6.2, design
 * D-012/D-013).
 *
 * Locked invariants:
 *
 * 1. **`decision:` head line is `acted`-gated** — `writeDispatchTaskMd` injects
 *    it only when the decision actually acted; a `suggest` answer (acted=false),
 *    no decision at all and a malformed decision id all keep the pre-T-08 bytes.
 * 2. **6 terminal-state settle mapping** — done(exit 0)→`ok`, failed→`rework`,
 *    failed+exit 3/model_exhausted→`inconclusive`, `needs-clarification`→no row,
 *    `lost`→`pending`+`note=lost`, superseded→`rollback`.
 * 3. **Idempotency** — `(decision_id, outcome, run_id)` is appended at most once;
 *    a PM restart replay writes nothing.
 * 4. **Ordering** — a `rollback` only exists after that decision settled `ok`, and
 *    because the fold takes the LAST settle it is appended after the `ok` row.
 * 5. **No guessing** — a task without a `decision:` head line writes no row at
 *    all (spec §6.2's un-associable classes).
 * 6. dp2's automatic checkpoint seam is RETIRED (PM-initiated only, 2026-10-23).
 *
 * Fixtures are plain files plus an injected append seam: no provider APIs, no
 * keys, no `decide_archive.py` child in the unit tests.
 */

import { createHash } from "node:crypto";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { afterEach, describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionContext } from "../../src/core/extensions/types.ts";
import * as pmOrchestrator from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import {
	type DecisionSettleAppender,
	type DecisionSettleRow,
	mapTerminalToSettle,
	planDecisionSettle,
	readDecisionSettles,
	recordDecisionSettle,
	splitDecisionId,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import type {
	DecideRunner,
	DecideRunRequest,
	RawDecideRun,
	TriageResult,
} from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import { canonicalStateBytes } from "../../src/extensions/agent-team-loop/pm/triage-client.ts";
import {
	actedDecisionOf,
	type CardSections,
	type DispatchDecision,
	type DispatchTriage,
	mergeDecisionHeader,
	planDispatchFrontmatter,
	registerWorkerTools,
	windowClaimId,
	writeDispatchTaskMd,
} from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { RUN_SCHEMA, type RunState } from "../../src/extensions/agent-team-loop/shared/run-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const OWNER = "mwds-t08";

const tempDirs: string[] = [];

function mkdtemp(prefix: string): string {
	const dir = fs.mkdtempSync(path.join(os.tmpdir(), prefix));
	tempDirs.push(dir);
	return dir;
}

afterEach(() => {
	for (const dir of tempDirs.splice(0)) fs.rmSync(dir, { recursive: true, force: true });
});

// ── fixtures ────────────────────────────────────────────────────────────────

/** A project root that owns `.agenticdoc/` (the archive lands under it). */
function mkProject(): { projectDir: string; agenticdocRoot: string } {
	const projectDir = mkdtemp(`mwds-t08-${OWNER}-`);
	const agenticdocRoot = path.join(projectDir, ".agenticdoc");
	fs.mkdirSync(agenticdocRoot, { recursive: true });
	return { projectDir, agenticdocRoot };
}

function archivePathOf(agenticdocRoot: string): string {
	return path.join(agenticdocRoot, "_autopilot", "decisions.jsonl");
}

/** Write one worker task dir: `task.md` (head lines) + optional `run.json`. */
function mkTask(
	agenticdocRoot: string,
	taskKey: string,
	input: { decisionId?: string; supersedes?: string; run?: Partial<RunState> } = {},
): string {
	const taskDir = path.join(agenticdocRoot, OWNER, "workers", taskKey);
	fs.mkdirSync(taskDir, { recursive: true });
	const head = ["type: coding"];
	if (input.decisionId !== undefined) head.push(`decision: ${input.decisionId}`);
	if (input.supersedes !== undefined) head.push(`supersedes: ${input.supersedes}`);
	fs.writeFileSync(path.join(taskDir, "task.md"), `${head.join("\n")}\n\nbody\n`, "utf8");
	if (input.run) {
		const state: RunState = {
			schema: RUN_SCHEMA,
			task_key: taskKey,
			run_id: `${taskKey}@2026-10-20T00:00:00.000Z`,
			owner_key: OWNER,
			kind: "coding",
			status: "done",
			started_at: "2026-10-20T00:00:00.000Z",
			artifacts: [],
			...input.run,
		};
		fs.writeFileSync(path.join(taskDir, "run.json"), `${JSON.stringify(state, null, 2)}\n`, "utf8");
	}
	return taskDir;
}

/** Archive appender that really appends, so the dedupe/ordering read side is
 * exercised (row shape mirrors `decide_archive.append_settle`). */
function fileAppender(archivePath: string): DecisionSettleAppender & { rows: DecisionSettleRow[] } {
	const rows: DecisionSettleRow[] = [];
	const append = ((row: DecisionSettleRow) => {
		fs.mkdirSync(path.dirname(archivePath), { recursive: true });
		const line = JSON.stringify({
			kind: "settle",
			decision_id: row.decisionId,
			dp: row.dp,
			key: row.key,
			task_key: row.taskKey,
			outcome: row.outcome,
			settled_by: row.settledBy,
			evidence_ref: row.evidenceRef,
			note: row.note,
		});
		fs.appendFileSync(archivePath, `${line}\n`, "utf8");
		rows.push(row);
		return { ok: true as const };
	}) as DecisionSettleAppender & { rows: DecisionSettleRow[] };
	append.rows = rows;
	return append;
}

const DONE_RUN: Partial<RunState> = { status: "done", exit: 0 };

// ── 1. decision: head line (requirement 1) ──────────────────────────────────

describe("decision: head line (acted-gated)", () => {
	const frontmatter = "type: coding\nphase: TASKS\n";

	it("injects `decision: <decision_id>` when the decision acted", () => {
		const { agenticdocRoot } = mkProject();
		const written = writeDispatchTaskMd(
			{ agenticdocRoot, ownerKey: OWNER },
			{
				taskKey: "t08-acted",
				type: "coding",
				body: "body",
				frontmatter,
				decision: { decisionId: "dp1-dispatch-type:t08-acted", acted: true },
			},
		);
		const content = fs.readFileSync(written.path, "utf8");
		expect(content).toBe("type: coding\nphase: TASKS\ndecision: dp1-dispatch-type:t08-acted\n\nbody\n");
		// The line is the LAST head line: it must precede the body separator.
		expect(content.indexOf("decision:")).toBeLessThan(content.indexOf("\n\nbody"));
	});

	it("never injects the line for a suggest answer (acted=false)", () => {
		const { agenticdocRoot } = mkProject();
		const written = writeDispatchTaskMd(
			{ agenticdocRoot, ownerKey: OWNER },
			{
				taskKey: "t08-suggest",
				type: "coding",
				body: "body",
				frontmatter,
				decision: { decisionId: "dp1-dispatch-type:t08-suggest", acted: false },
			},
		);
		expect(fs.readFileSync(written.path, "utf8")).toBe("type: coding\nphase: TASKS\n\nbody\n");
		expect(fs.readFileSync(written.path, "utf8")).not.toContain("decision:");
	});

	it("keeps the bytes unchanged with no decision and with a malformed id", () => {
		const { agenticdocRoot } = mkProject();
		const plain = writeDispatchTaskMd(
			{ agenticdocRoot, ownerKey: OWNER },
			{ taskKey: "t08-none", type: "coding", body: "body", frontmatter },
		);
		const malformed = writeDispatchTaskMd(
			{ agenticdocRoot, ownerKey: OWNER },
			{
				taskKey: "t08-malformed",
				type: "coding",
				body: "body",
				frontmatter,
				decision: { decisionId: "not a decision id", acted: true },
			},
		);
		const expected = "type: coding\nphase: TASKS\n\nbody\n";
		expect(fs.readFileSync(plain.path, "utf8")).toBe(expected);
		expect(fs.readFileSync(malformed.path, "utf8")).toBe(expected);
	});

	it("merges at most one decision line (idempotent merge)", () => {
		const decision: DispatchDecision = { decisionId: "dp1-dispatch-type:x", acted: true };
		const once = mergeDecisionHeader(frontmatter, decision);
		expect(mergeDecisionHeader(once, decision)).toBe(once);
		expect(once.match(/^decision:/gm)).toHaveLength(1);
	});

	it("only an acted triage result is correlated (D-036: no local mode mirror)", () => {
		const result = (fields: Record<string, unknown>): DispatchTriage => ({
			result: fields as unknown as TriageResult,
			alertOnDisagreement: true,
			notifyOnUnavailable: false,
			dispatchedType: "coding",
			disagreement: false,
			receipt: "",
			statePath: "material",
			stateTrace: "",
		});
		expect(actedDecisionOf(null)).toBeUndefined();
		expect(actedDecisionOf(result({ decision_id: "dp1-dispatch-type:x", mode: "auto" }))).toBeUndefined();
		expect(actedDecisionOf(result({ decision_id: "dp1-dispatch-type:x", acted: false }))).toBeUndefined();
		expect(actedDecisionOf(result({ decision_id: "", acted: true }))).toBeUndefined();
		expect(actedDecisionOf(result({ decision_id: "dp1-dispatch-type:x", acted: true }))).toEqual({
			decisionId: "dp1-dispatch-type:x",
			acted: true,
		});
	});
});

// ── 2. the 6 terminal-state mapping (requirement 2) ─────────────────────────

describe("terminal-state -> settle outcome (6 states)", () => {
	it("done -> ok", () => {
		expect(mapTerminalToSettle({ status: "done", runExit: 0, modelError: false })).toEqual({
			ok: true,
			outcome: "ok",
		});
	});

	it("failed -> rework", () => {
		expect(mapTerminalToSettle({ status: "failed", runExit: 1, modelError: false })).toEqual({
			ok: true,
			outcome: "rework",
		});
	});

	it("failed + exit 3 / model_exhausted -> inconclusive", () => {
		expect(mapTerminalToSettle({ status: "failed", runExit: 3, modelError: false })).toEqual({
			ok: true,
			outcome: "inconclusive",
		});
		expect(mapTerminalToSettle({ status: "failed", runExit: 1, modelError: true })).toEqual({
			ok: true,
			outcome: "inconclusive",
		});
	});

	it("needs-clarification -> no row at all", () => {
		expect(mapTerminalToSettle({ status: "needs-clarification", runExit: 2, modelError: false })).toEqual({
			ok: false,
			reason: "needs-clarification",
		});
	});

	it("lost -> pending with note=lost", () => {
		expect(mapTerminalToSettle({ status: "lost", modelError: false })).toEqual({
			ok: true,
			outcome: "pending",
			note: "lost",
		});
	});

	it("done with a non-zero exit is contradictory and never guessed", () => {
		expect(mapTerminalToSettle({ status: "done", runExit: 2, modelError: false })).toEqual({
			ok: false,
			reason: "inconsistent-run",
		});
	});
});

// ── 3. dedupe + rollback ordering (requirement 2) ───────────────────────────

describe("settle idempotency and rollback ordering", () => {
	const base = {
		decisionId: "dp1-dispatch-type:t08",
		ownerKey: OWNER,
		taskKey: "t08",
		runId: "t08@2026-10-20T00:00:00.000Z",
	};

	it("splits the decision id on the FIRST colon only (D-023)", () => {
		expect(splitDecisionId("dp1-dispatch-type:t08")).toEqual({ dp: "dp1-dispatch-type", triggerId: "t08" });
		expect(splitDecisionId("dp2-checkpoint-split:t08#ckpt1")).toEqual({
			dp: "dp2-checkpoint-split",
			triggerId: "t08#ckpt1",
		});
		expect(splitDecisionId("dp2-checkpoint-split:a:b")).toEqual({ dp: "dp2-checkpoint-split", triggerId: "a:b" });
		expect(splitDecisionId("no-colon")).toBeUndefined();
		expect(splitDecisionId(":empty")).toBeUndefined();
	});

	it("writes the first settle and skips the (decision_id, outcome, run_id) replay", () => {
		const first = planDecisionSettle({ ...base, outcome: "ok", prior: [] });
		expect(first.ok).toBe(true);
		if (!first.ok) return;
		expect(first.row).toEqual({
			decisionId: base.decisionId,
			dp: "dp1-dispatch-type",
			key: OWNER,
			taskKey: "t08",
			outcome: "ok",
			settledBy: "pm-auto",
			evidenceRef: base.runId,
			note: null,
		});
		const replay = planDecisionSettle({
			...base,
			outcome: "ok",
			prior: [{ decisionId: base.decisionId, outcome: "ok", runId: base.runId }],
		});
		expect(replay).toEqual({ ok: false, reason: "duplicate-settle" });
	});

	it("a new run id may settle the same decision again (re-dispatch)", () => {
		const second = planDecisionSettle({
			...base,
			runId: "t08@2026-10-21T00:00:00.000Z",
			outcome: "ok",
			prior: [{ decisionId: base.decisionId, outcome: "ok", runId: base.runId }],
		});
		expect(second.ok).toBe(true);
	});

	it("rollback is refused before any ok settle", () => {
		expect(planDecisionSettle({ ...base, outcome: "rollback", prior: [] })).toEqual({
			ok: false,
			reason: "rollback-without-ok",
		});
		expect(
			planDecisionSettle({
				...base,
				outcome: "rollback",
				prior: [{ decisionId: base.decisionId, outcome: "rework", runId: "other-run" }],
			}),
		).toEqual({ ok: false, reason: "rollback-without-ok" });
	});

	it("rollback after ok is allowed", () => {
		const rollback = planDecisionSettle({
			...base,
			outcome: "rollback",
			prior: [{ decisionId: base.decisionId, outcome: "ok", runId: base.runId }],
		});
		expect(rollback.ok).toBe(true);
	});

	it("another decision's ok neither licenses a rollback nor blocks this settle", () => {
		// A different decision settling ok on the SAME run must not make this
		// decision rollback-able, and must not dedupe its own settle.
		expect(
			planDecisionSettle({
				...base,
				outcome: "rollback",
				prior: [{ decisionId: "dp2-checkpoint-split:t08#ckpt1", outcome: "ok", runId: base.runId }],
			}),
		).toEqual({ ok: false, reason: "rollback-without-ok" });
		expect(
			planDecisionSettle({
				...base,
				outcome: "ok",
				prior: [{ decisionId: "dp2-checkpoint-split:t08#ckpt1", outcome: "ok", runId: base.runId }],
			}).ok,
		).toBe(true);
	});

	it("reading the archive tolerates a half-written tail line", () => {
		const { agenticdocRoot } = mkProject();
		const archive = archivePathOf(agenticdocRoot);
		fs.mkdirSync(path.dirname(archive), { recursive: true });
		fs.writeFileSync(
			archive,
			`${JSON.stringify({ kind: "decide", decision_id: "dp1:x", outcome: "pending" })}\n` +
				`${JSON.stringify({ kind: "settle", decision_id: "dp1:x", outcome: "ok", evidence_ref: "x@1" })}\n` +
				`{"kind":"settle","decision_id":"dp1:x","outc`,
			"utf8",
		);
		expect(readDecisionSettles(archive)).toEqual([{ decisionId: "dp1:x", outcome: "ok", runId: "x@1" }]);
	});
});

// ── 4. recordDecisionSettle end to end (requirements 2 + 3) ─────────────────

describe("recordDecisionSettle", () => {
	it("writes nothing for an un-associated task (no decision header, no guessing)", () => {
		const { agenticdocRoot } = mkProject();
		const taskDir = mkTask(agenticdocRoot, "t08-plain", { run: DONE_RUN });
		const append = fileAppender(archivePathOf(agenticdocRoot));
		const result = recordDecisionSettle(agenticdocRoot, OWNER, { taskKey: "t08-plain", status: "done" }, taskDir, {
			append,
		});
		expect(result.written).toEqual([]);
		expect(result.skipped).toEqual([{ decisionId: "", reason: "no-decision-header" }]);
		expect(append.rows).toEqual([]);
		expect(fs.existsSync(archivePathOf(agenticdocRoot))).toBe(false);
	});

	it("writes nothing for needs-clarification", () => {
		const { agenticdocRoot } = mkProject();
		const taskDir = mkTask(agenticdocRoot, "t08-nc", {
			decisionId: "dp1-dispatch-type:t08-nc",
			run: { status: "needs-clarification", exit: 2 },
		});
		const append = fileAppender(archivePathOf(agenticdocRoot));
		const result = recordDecisionSettle(
			agenticdocRoot,
			OWNER,
			{ taskKey: "t08-nc", status: "needs-clarification" },
			taskDir,
			{ append },
		);
		expect(result.written).toEqual([]);
		expect(result.skipped).toEqual([{ decisionId: "dp1-dispatch-type:t08-nc", reason: "needs-clarification" }]);
		expect(append.rows).toEqual([]);
	});

	it("settles done -> ok with the run id as the idempotency half", () => {
		const { agenticdocRoot } = mkProject();
		const taskDir = mkTask(agenticdocRoot, "t08-done", {
			decisionId: "dp1-dispatch-type:t08-done",
			run: DONE_RUN,
		});
		const append = fileAppender(archivePathOf(agenticdocRoot));
		const result = recordDecisionSettle(agenticdocRoot, OWNER, { taskKey: "t08-done", status: "done" }, taskDir, {
			append,
		});
		expect(result.written).toEqual([
			{
				decisionId: "dp1-dispatch-type:t08-done",
				dp: "dp1-dispatch-type",
				key: OWNER,
				taskKey: "t08-done",
				outcome: "ok",
				settledBy: "pm-auto",
				evidenceRef: "t08-done@2026-10-20T00:00:00.000Z",
				note: null,
			},
		]);
	});

	it("settles lost -> pending + note=lost", () => {
		const { agenticdocRoot } = mkProject();
		const taskDir = mkTask(agenticdocRoot, "t08-lost", {
			decisionId: "dp1-dispatch-type:t08-lost",
			run: { status: "lost" },
		});
		const append = fileAppender(archivePathOf(agenticdocRoot));
		const result = recordDecisionSettle(agenticdocRoot, OWNER, { taskKey: "t08-lost", status: "lost" }, taskDir, {
			append,
		});
		expect(result.written[0]?.outcome).toBe("pending");
		expect(result.written[0]?.note).toBe("lost");
	});

	it("replays are idempotent across a PM restart (same run id, same outcome)", () => {
		const { agenticdocRoot } = mkProject();
		const taskDir = mkTask(agenticdocRoot, "t08-replay", {
			decisionId: "dp1-dispatch-type:t08-replay",
			run: DONE_RUN,
		});
		const archive = archivePathOf(agenticdocRoot);
		const first = recordDecisionSettle(agenticdocRoot, OWNER, { taskKey: "t08-replay", status: "done" }, taskDir, {
			append: fileAppender(archive),
			archivePath: archive,
		});
		expect(first.written).toHaveLength(1);
		const second = recordDecisionSettle(agenticdocRoot, OWNER, { taskKey: "t08-replay", status: "done" }, taskDir, {
			append: fileAppender(archive),
			archivePath: archive,
		});
		expect(second.written).toEqual([]);
		expect(second.skipped).toEqual([{ decisionId: "dp1-dispatch-type:t08-replay", reason: "duplicate-settle" }]);
		expect(readDecisionSettles(archive)).toHaveLength(1);
	});

	it("records the rollback of a superseded decision AFTER its ok settle", () => {
		const { agenticdocRoot } = mkProject();
		const archive = archivePathOf(agenticdocRoot);
		// 1) the replaced task settled ok
		const oldDir = mkTask(agenticdocRoot, "t08-old", {
			decisionId: "dp1-dispatch-type:t08-old",
			run: DONE_RUN,
		});
		recordDecisionSettle(agenticdocRoot, OWNER, { taskKey: "t08-old", status: "done" }, oldDir, {
			append: fileAppender(archive),
			archivePath: archive,
		});
		// 2) the replacement lands (done) and declares `supersedes:`
		const newDir = mkTask(agenticdocRoot, "t08-new", {
			decisionId: "dp1-dispatch-type:t08-new",
			supersedes: "t08-old",
			run: DONE_RUN,
		});
		const result = recordDecisionSettle(agenticdocRoot, OWNER, { taskKey: "t08-new", status: "done" }, newDir, {
			append: fileAppender(archive),
			archivePath: archive,
		});
		expect(result.written.map((row) => [row.decisionId, row.outcome])).toEqual([
			["dp1-dispatch-type:t08-new", "ok"],
			["dp1-dispatch-type:t08-old", "rollback"],
		]);
		// File order is what the fold reads: rollback is the LAST settle of the old
		// decision, i.e. strictly after its ok row.
		const settles = readDecisionSettles(archive);
		const oldSettles = settles.filter((row) => row.decisionId === "dp1-dispatch-type:t08-old");
		expect(oldSettles.map((row) => row.outcome)).toEqual(["ok", "rollback"]);
		// The rollback carries the REPLACED run's id, not the replacement's.
		expect(oldSettles[1]?.runId).toBe("t08-old@2026-10-20T00:00:00.000Z");
	});

	it("does not roll back when the replacement failed (no half-failed reversal)", () => {
		const { agenticdocRoot } = mkProject();
		const archive = archivePathOf(agenticdocRoot);
		const oldDir = mkTask(agenticdocRoot, "t08-old2", {
			decisionId: "dp1-dispatch-type:t08-old2",
			run: DONE_RUN,
		});
		recordDecisionSettle(agenticdocRoot, OWNER, { taskKey: "t08-old2", status: "done" }, oldDir, {
			append: fileAppender(archive),
			archivePath: archive,
		});
		const newDir = mkTask(agenticdocRoot, "t08-new2", {
			decisionId: "dp1-dispatch-type:t08-new2",
			supersedes: "t08-old2",
			run: { status: "failed", exit: 1 },
		});
		const result = recordDecisionSettle(agenticdocRoot, OWNER, { taskKey: "t08-new2", status: "failed" }, newDir, {
			append: fileAppender(archive),
			archivePath: archive,
		});
		expect(result.written.map((row) => row.outcome)).toEqual(["rework"]);
		expect(readDecisionSettles(archive).some((row) => row.outcome === "rollback")).toBe(false);
	});

	it("reports an unwritable archive instead of throwing", () => {
		const { agenticdocRoot } = mkProject();
		const taskDir = mkTask(agenticdocRoot, "t08-fail", {
			decisionId: "dp1-dispatch-type:t08-fail",
			run: DONE_RUN,
		});
		const result = recordDecisionSettle(agenticdocRoot, OWNER, { taskKey: "t08-fail", status: "done" }, taskDir, {
			append: () => ({ ok: false, error: "archive locked" }),
		});
		expect(result.written).toEqual([]);
		expect(result.skipped).toEqual([{ decisionId: "dp1-dispatch-type:t08-fail", reason: "append-failed" }]);
	});
});

// ── 5. dp2 structured-state version (requirement 0) ─────────────────────────

// ── fixtures of the material path (T-03 dp1 envelope) ───────────────────────

const DP1_FACTS: { key: string; taskKey: string; sections: CardSections } = {
	key: "mw-ds-t08",
	taskKey: "t08-material",
	sections: {
		context: "triage fixture。种子锚点 .agenticdoc/goal.md；判据入口 pm/ui-bridge.ts:1257。",
		requirements: "AC-001 成立。",
		deliverables: "report.md。",
		extras: [],
	},
};

const DP1_DESCRIPTION = "wire the dp1 material envelope (T-08) into the dispatch path";

interface MaterialCall {
	dp: string;
	envelope: {
		material: Record<string, string>;
		meta: Record<string, unknown>;
		questions?: unknown;
	};
}

/** A `mw decide run --stdin` double for the versioned envelope: it records the
 * `{material, meta}` payload and answers with the authority keys Python returns. */
function materialChild(extra: Record<string, unknown>): { run: DecideRunner; calls: MaterialCall[] } {
	const calls: MaterialCall[] = [];
	const run: DecideRunner = (request: DecideRunRequest) => {
		calls.push({ dp: request.dp, envelope: JSON.parse(request.input) as MaterialCall["envelope"] });
		return {
			status: 0,
			timedOut: false,
			stderr: "",
			stdout: JSON.stringify({
				available: true,
				confidence_source: "api",
				latency_ms: 9,
				answers: { triage_type: { value: "coding", confidence: 0.8 } },
				...extra,
			}),
		};
	};
	return { run, calls };
}

// ── 6. dp2's automatic checkpoint seam is RETIRED (user revision 2026-10-23) ─

describe("dp2 automatic checkpoint seam (retired)", () => {
	it("no machine-side build/decide seam remains; the PM-initiated tool is the entry", () => {
		const pm = pmOrchestrator as unknown as Record<string, unknown>;
		// The dead seam must not be resurrected as a second, local authority.
		expect(pm).not.toHaveProperty("buildDp2CheckpointState");
		expect(pm).not.toHaveProperty("decideDp2Checkpoint");
		expect(pm).not.toHaveProperty("Dp2CheckpointStateInput");
		// The worker-side consume contract of a PM-written request file stays.
		expect(pm.DP2_STEER_FILE).toBe("steer-dp2.md");
		expect(pm.DP2_NARROW_MARKER).toBe("[mw dp2-narrow]");
		expect(pm.DP2_STEER_REQUEST_HEADER).toBe("[dp2-narrow-request]");
		// The registry question set is still pinned (the PM points at it).
		expect(pm.DP2_QUESTIONS_VERSION).toMatch(/^q-[0-9a-f]{8}$/);
	});
});

// ── 6b. dp1 dispatch adoption (T-04c / D-041) ───────────────────────────────

function enableTriage(projectDir: string): void {
	fs.mkdirSync(path.join(projectDir, ".mw"), { recursive: true });
	fs.writeFileSync(path.join(projectDir, ".mw", "decide.json"), `${JSON.stringify({ enabled: true })}\n`, "utf8");
}

/** One `mw decide run` payload plus the T-02b authority keys. */
function triageRun(extra: Record<string, unknown>): RawDecideRun {
	return {
		status: 0,
		timedOut: false,
		stderr: "",
		stdout: JSON.stringify({
			available: true,
			confidence_source: "api",
			latency_ms: 9,
			answers: {
				triage_type: { value: "coding", confidence: 0.8 },
				triage_risk: { value: "mid", confidence: 0.6 },
			},
			...extra,
		}),
	};
}

function planFor(
	projectDir: string,
	raw: RawDecideRun | DecideRunner,
	extra: {
		description?: string;
		taskType?: string;
		dp1?: { key?: string; taskKey?: string | null; sections?: CardSections };
	} = {},
) {
	const run: DecideRunner = typeof raw === "function" ? raw : () => raw;
	const plan = planDispatchFrontmatter({
		cwd: projectDir,
		cli: "pi",
		provider: "timi",
		taskType: extra.taskType ?? "coding",
		phase: "TASKS",
		model: "",
		modelReason: "",
		registry: undefined,
		triageRun: run,
		dp1: extra.dp1,
		description: extra.description,
	});
	if (!plan.ok) throw new Error(plan.message);
	return plan;
}

/** Stable text hash (the byte-equality proof uses it, not just the strings). */
function sha256(text: string): string {
	return createHash("sha256").update(text, "utf8").digest("hex");
}

function writePlanTask(
	agenticdocRoot: string,
	taskKey: string,
	plan: { frontmatter: string },
	decision: DispatchDecision | undefined,
	decisionTrace?: string,
): string {
	const written = writeDispatchTaskMd(
		{ agenticdocRoot, ownerKey: OWNER },
		{ taskKey, type: "coding", body: "body", frontmatter: plan.frontmatter, decision, decisionTrace },
	);
	return fs.readFileSync(written.path, "utf8");
}

describe("dp1 dispatch adoption (T-04c / D-041)", () => {
	it("auto + usable + triage_type makes writeDispatchTaskMd write the decision: line", () => {
		const { projectDir, agenticdocRoot } = mkProject();
		enableTriage(projectDir);
		const plan = planFor(
			projectDir,
			triageRun({ decision_id: "dp1-dispatch-type:ds-t04c-auto", mode: "auto", acted: false }),
			{ dp1: DP1_FACTS },
		);

		// Python's `acted=false` (intent=answer) does not mean "not adopted": the
		// dispatch side adopted the auto answer, and that is the fact it records.
		expect(plan.triage?.decision).toEqual({ decisionId: "dp1-dispatch-type:ds-t04c-auto", acted: true });

		const content = writePlanTask(agenticdocRoot, "t04c-auto", plan, plan.triage?.decision);
		expect(content).toBe(
			`${plan.frontmatter.replace(/\r?\n$/, "")}\ndecision: dp1-dispatch-type:ds-t04c-auto\n\nbody\n`,
		);
		// The head line is the LAST head line, before the body separator.
		expect(content.indexOf("decision:")).toBeLessThan(content.indexOf("\n\nbody"));
	});

	it("auto + a disagreeing triage_type is NOT adopted: no `decision:` line, id stays observable", () => {
		const { projectDir, agenticdocRoot } = mkProject();
		enableTriage(projectDir);
		// AC-014: the dispatch never rewrites its `type:` from the advice, so the
		// advice named `research` while `coding` went out. T-04c adoption means
		// "the dispatcher took this type", so a disagreement is not adoption (it
		// stays observable in the triage result / ledger row).
		const plan = planFor(
			projectDir,
			triageRun({
				decision_id: "dp1-dispatch-type:ds-t04c-dis",
				mode: "auto",
				acted: true,
				answers: { triage_type: { value: "research", confidence: 0.8 } },
			}),
			{ dp1: DP1_FACTS },
		);
		expect(plan.triage?.disagreement).toBe(true);
		expect(plan.triage?.result.decision_id).toBe("dp1-dispatch-type:ds-t04c-dis");
		expect(plan.triage?.decision).toBeUndefined();
		const content = writePlanTask(agenticdocRoot, "t04c-dis", plan, plan.triage?.decision);
		expect(content).toBe(`${plan.frontmatter.replace(/\r?\n$/, "")}\n\nbody\n`);
	});

	it("suggest mode leaves task.md byte-identical to the closed baseline", () => {
		const { projectDir, agenticdocRoot } = mkProject();
		enableTriage(projectDir);
		const plan = planFor(
			projectDir,
			triageRun({ decision_id: "dp1-dispatch-type:ds-t04c-suggest", mode: "suggest", acted: false }),
			{ dp1: DP1_FACTS },
		);
		expect(plan.triage?.decision).toBeUndefined();
		const content = writePlanTask(agenticdocRoot, "t04c-suggest", plan, plan.triage?.decision);
		expect(content).toBe(`${plan.frontmatter.replace(/\r?\n$/, "")}\n\nbody\n`);
	});

	it("an unavailable result and an auto answer without triage_type stay un-correlated", () => {
		const { projectDir } = mkProject();
		enableTriage(projectDir);
		const unavailable = planFor(
			projectDir,
			{ status: 0, timedOut: false, stderr: "", stdout: JSON.stringify({ available: false, reason: "timeout" }) },
			{ dp1: DP1_FACTS },
		);
		expect(unavailable.triage?.decision).toBeUndefined();
		const typedless = planFor(
			projectDir,
			triageRun({ decision_id: "dp1-dispatch-type:ds-t04c-empty", mode: "auto", acted: false, answers: {} }),
			{ dp1: DP1_FACTS },
		);
		expect(typedless.triage?.decision).toBeUndefined();
	});
});

// ── 6c. dp1 material envelope (T-03/T-08, the replaced T-04d state) ─────────

describe("dp1 material envelope", () => {
	it("sends the card's three bodies verbatim and the decision: line becomes reachable", () => {
		const { projectDir, agenticdocRoot } = mkProject();
		enableTriage(projectDir);
		const child = materialChild({ decision_id: "dp1-dispatch-type:mw-ds-t08", mode: "auto", acted: false });
		const plan = planFor(projectDir, child.run, { description: DP1_DESCRIPTION, dp1: DP1_FACTS });

		// ── the production payload really is the material envelope ───────────
		expect(child.calls).toHaveLength(1);
		const call = child.calls[0] as MaterialCall;
		expect(call.dp).toBe("dp1-dispatch-type");
		expect(Object.keys(call.envelope).sort()).toEqual(["material", "meta"]);
		expect(call.envelope.questions).toBeUndefined();
		expect(call.envelope.material).toEqual({
			task_goal: DP1_FACTS.sections.context,
			task_requirements: DP1_FACTS.sections.requirements,
			task_deliverables: DP1_FACTS.sections.deliverables,
		});
		expect(call.envelope.meta).toMatchObject({
			record_version: 2,
			key: DP1_FACTS.key,
			task_key: "t08-material",
			initiator_role: "pm",
			retry_of: null,
		});
		// Identity never rides in the model material.
		for (const key of ["key", "task_key", "logical_id", "initiator_role", "schema_version"]) {
			expect(call.envelope.material, key).not.toHaveProperty(key);
		}
		// The budget is the transport's (Python) call: nothing is truncated here.
		expect(canonicalStateBytes(call.envelope.material)).toBeGreaterThan(0);

		// ── the response's authority keys are consumed ───────────────────────
		expect(plan.triage?.statePath).toBe("material");
		expect(plan.triage?.stateTrace).toMatch(/^\[DECISION\] dp1 state=material bytes=\d+$/);
		expect(plan.triage?.result.decision_id).toBe("dp1-dispatch-type:mw-ds-t08");
		expect(plan.triage?.result.mode).toBe("auto");
		expect(plan.triage?.result.acted).toBe(false);
		expect(plan.triage?.decision).toEqual({ decisionId: "dp1-dispatch-type:mw-ds-t08", acted: true });

		// ── task.md carries the correlation line the trace records ──────────
		const content = writePlanTask(
			agenticdocRoot,
			"t08-material",
			plan,
			plan.triage?.decision,
			plan.triage?.stateTrace,
		);
		expect(content).toBe(
			`${plan.frontmatter.replace(/\r?\n$/, "")}\ndecision: dp1-dispatch-type:mw-ds-t08\n\nbody\n`,
		);
		const trace = fs.readFileSync(path.join(agenticdocRoot, OWNER, "workers", "t08-material", "trace.log"), "utf8");
		expect(trace).toContain("[DECISION] dp1 state=material");
		expect(trace).not.toContain("state=skipped");
	});

	it("skips with zero spawn (byte-identical task.md) when no material can be built", () => {
		const cases: Array<{
			name: string;
			dp1: { key?: string; taskKey?: string | null; sections?: CardSections };
			taskType?: string;
		}> = [
			// A role outside the dp1 taxonomy has no enum value: report missing
			// instead of guessing `coding`.
			{ name: "out-of-taxonomy type", dp1: DP1_FACTS, taskType: "vision" },
			// No owner key => the local envelope's required `key` is blank.
			{ name: "no owner key", dp1: { ...DP1_FACTS, key: "" } },
			// Empty card bodies: a required material field is absent, never faked.
			{
				name: "missing material",
				dp1: {
					key: DP1_FACTS.key,
					taskKey: "t08-skip",
					sections: { context: "", requirements: "", deliverables: "", extras: [] },
				},
			},
		];

		for (const testCase of cases) {
			const { projectDir, agenticdocRoot } = mkProject();
			enableTriage(projectDir);
			const child = materialChild({ decision_id: "dp1-dispatch-type:never", mode: "auto", acted: false });

			const baseline = mkProject(); // triage off: the byte baseline
			const baselineRun: DecideRunner = () => {
				throw new Error("triage must not spawn on the baseline");
			};
			const baselinePlan = planFor(baseline.projectDir, baselineRun, {
				description: DP1_DESCRIPTION,
				taskType: testCase.taskType,
				dp1: testCase.dp1,
			});
			expect(baselinePlan.triage, testCase.name).toBeNull();

			const plan = planFor(projectDir, child.run, {
				description: DP1_DESCRIPTION,
				taskType: testCase.taskType,
				dp1: testCase.dp1,
			});

			// Zero spawn: a skip never asks the service.
			expect(child.calls, testCase.name).toHaveLength(0);
			expect(plan.triage?.statePath, testCase.name).toBe("skipped");
			expect(plan.triage?.stateTrace, testCase.name).toMatch(/^\[DECISION\] dp1 state=skipped reason=/);
			// The skipped response carries no authority keys, so nothing is adopted.
			expect(plan.triage?.decision, testCase.name).toBeUndefined();

			const slug = testCase.name.replace(/\s+/g, "-");
			const bytes = writePlanTask(
				agenticdocRoot,
				`t08-skip-${slug}`,
				plan,
				plan.triage?.decision,
				plan.triage?.stateTrace,
			);
			const baselineBytes = writePlanTask(baseline.agenticdocRoot, `t08-baseline-${slug}`, baselinePlan, undefined);
			// Byte-identical task.md AND identical sha (not just "no decision line").
			expect(bytes, testCase.name).toBe(baselineBytes);
			expect(sha256(bytes), testCase.name).toBe(sha256(baselineBytes));

			const trace = fs.readFileSync(
				path.join(agenticdocRoot, OWNER, "workers", `t08-skip-${slug}`, "trace.log"),
				"utf8",
			);
			expect(trace, testCase.name).toContain("[DECISION] dp1 state=skipped reason=");
			expect(trace, testCase.name).not.toContain("state=material");
		}
	});

	it("never leaks the free-text description into the material", () => {
		const { projectDir } = mkProject();
		enableTriage(projectDir);
		const child = materialChild({ decision_id: "dp1-dispatch-type:leak", mode: "auto", acted: false });
		planFor(projectDir, child.run, {
			description: "fix H:\\git\\Multi-Workers\\packages\\multi-workers\\mw.py failing test",
			dp1: DP1_FACTS,
		});
		const wire = JSON.stringify((child.calls[0] as MaterialCall).envelope);
		expect(wire).not.toContain("H:");
		expect(wire).not.toContain("failing test");
	});

	it("the dispatch_worker ENTRY sends the material (production wiring)", async () => {
		// The plan-level tests above prove the payload shape; this drives the real
		// `dispatch_worker` tool so the entry's own wiring (owner key + the card's
		// bodies + the child seam) is proven too.
		const root = mkdtemp(`mwds-t08-entry-`);
		const agenticdocRoot = path.join(root, ".agenticdoc");
		const projectDir = root;
		enableTriage(projectDir);
		const key = "k";
		const keyDir = path.join(agenticdocRoot, key);
		fs.mkdirSync(path.join(keyDir, "evidence", "research"), { recursive: true });
		fs.writeFileSync(path.join(keyDir, "spec.md"), `# Spec\n${"x".repeat(600)}\n\n| AC-001 | a |\n`, "utf8");
		fs.writeFileSync(path.join(keyDir, "design.md"), `# Design\n${"x".repeat(600)}`, "utf8");
		fs.writeFileSync(path.join(keyDir, "evidence", "research", "spec-topic-2026-01-01.md"), "# r\n", "utf8");
		fs.writeFileSync(path.join(keyDir, "evidence", "research", "design-topic-2026-01-01.md"), "# r\n", "utf8");
		fs.writeFileSync(path.join(keyDir, "pm-state.md"), "- Phase: EXECUTE\n- Updated: 2026-01-01 00:00\n", "utf8");
		const indexStore = new IndexStore(agenticdocRoot);
		await indexStore.upsert({
			key,
			status: "active",
			phase: "EXECUTE",
			claimId: windowClaimId(),
			deps: "",
			desc: "",
			updated: new Date().toISOString(),
		});

		// A compliant card with the three judged bodies.
		const cardDir = path.join(keyDir, "tasks");
		fs.mkdirSync(cardDir, { recursive: true });
		const cardPath = path.join(cardDir, "T-08-fixture.md");
		fs.writeFileSync(
			cardPath,
			[
				"type: coding",
				"",
				"## 上下文",
				"",
				"triage fixture。种子锚点 .agenticdoc/goal.md；判据入口 pm/ui-bridge.ts:1257。",
				"",
				"## 要求",
				"",
				"AC-001 成立。",
				"",
				"## 交付格式",
				"",
				"report.md。",
				"",
				"## 写入允许面",
				"",
				"- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`",
				"- `packages/multi-workers/mw.py`",
				"",
				"## 写入禁止面",
				"",
				"本任务目录之外的任何路径。",
				"",
				"## 验收命令",
				"",
				"node ../../node_modules/vitest/dist/cli.js --run test/suite/decision-association.test.ts",
				"",
				"## 改动历史",
				"",
				"见本任务 trace.log 写入事件与 report.md 的改动清单。",
				"",
			].join("\n"),
			"utf8",
		);

		const tools = new Map<string, { execute: (...args: unknown[]) => Promise<unknown> }>();
		const pi = {
			registerTool: (tool: { name: string; execute: (...args: unknown[]) => Promise<unknown> }) => {
				tools.set(tool.name, tool);
			},
			registerCommand: () => undefined,
			sendMessage: () => undefined,
			sendUserMessage: () => undefined,
			appendEntry: () => undefined,
		} as unknown as ExtensionAPI;
		const child = materialChild({ decision_id: "dp1-dispatch-type:k", mode: "auto", acted: false });
		registerWorkerTools(
			pi,
			new WorkerStore(agenticdocRoot),
			new AckStore(agenticdocRoot),
			indexStore,
			agenticdocRoot,
			{ key },
			projectDir,
			child.run,
		);
		const dispatchWorker = tools.get("dispatch_worker");
		if (!dispatchWorker) throw new Error("dispatch_worker not registered");
		await dispatchWorker.execute(
			"id",
			{ task_key: "t08-entry", card_path: cardPath, description: DP1_DESCRIPTION, type: "coding" },
			undefined,
			undefined,
			{} as unknown as ExtensionContext,
		);

		// The payload the child really received.
		expect(child.calls).toHaveLength(1);
		const envelope = (child.calls[0] as MaterialCall).envelope;
		expect(envelope.questions).toBeUndefined();
		expect(Object.keys(envelope.material).sort()).toEqual(["task_deliverables", "task_goal", "task_requirements"]);
		expect(String(envelope.material.task_goal)).toContain("triage fixture");
		expect(envelope.meta).toMatchObject({ key, task_key: "t08-entry", initiator_role: "pm" });
		// The task.md correlation line + the trace line both landed.
		const taskDir = path.join(agenticdocRoot, key, "workers", "t08-entry");
		expect(fs.readFileSync(path.join(taskDir, "task.md"), "utf8")).toContain("decision: dp1-dispatch-type:k");
		expect(fs.readFileSync(path.join(taskDir, "trace.log"), "utf8")).toContain("dp1 state=material");
		console.log(
			`[VERIFY] dispatch_worker entry: material.task_goal_bytes=${Buffer.byteLength(String(envelope.material.task_goal), "utf8")} key=${key}`,
		);
	});

	it("the dp1 question set mirrors the Python registry (the registry is the authority)", () => {
		const registryPath = fileURLToPath(new URL("../../../multi-workers/decide_registry.json", import.meta.url));
		const registry = JSON.parse(fs.readFileSync(registryPath, "utf8")) as {
			points: Array<{ id: string; questions: Array<{ id: string; choices?: string[] }> }>;
		};
		const dp1 = registry.points.find((point) => point.id === "dp1-dispatch-type");
		if (!dp1) throw new Error("dp1 not in the registry");
		expect(dp1.questions).toHaveLength(1);
		expect(dp1.questions[0]).toMatchObject({ id: "triage_type", choices: ["coding", "research", "review"] });
	});
});
