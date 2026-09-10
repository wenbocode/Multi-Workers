/**
 * Tests for the /autopilot console (goal-autopilot T-15, design D-005/D-105/
 * D-109/D-110, AC-015/016/018/025).
 *
 * - status model (VC-017/AC-015): /autopilot status --json carries the
 *   stage/gates/timeline field groups plus the schema version string and the
 *   per-key rounds structure; it is rebuilt from fixture FILES ALONE (the
 *   console keeps no state, D-005) in <10s; the human view renders the same
 *   derivation, so every number matches the --json values (view parity).
 * - rounds parity (VC-020/AC-018): the TS usedRounds derivation equals the
 *   Python autopilot/state.py used_rounds result for the same task dirs
 *   (annotated below from a probe run against this exact fixture layout),
 *   including the missing-attempt directory-identity degradation.
 * - gate writer (AC-016/D-105): approve/reject rewrite exactly the four
 *   answer fields under .mw/gates.lock with every other line byte-preserved;
 *   a held lock blocks the answer; corrupt input is refused.
 * - timeline replay (VC-017/D-109): watermark filtering, beat filtering,
 *   --all, rotated-generation order, the "N events pruned" notice, and the
 *   --since → seq-watermark mapping.
 * - command set: registration via pmActivate, config writes
 *   (enable/disable/pause/resume, D-110 validation), and the session-entry
 *   watermark persistence.
 *
 * No provider APIs, keys, or network: pure file fixtures + fake
 * ExtensionAPI/command contexts (same pattern as autopilot-protocol.test.ts).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import type { ExtensionAPI, ExtensionCommandContext } from "../../src/core/extensions/types.ts";
import { registerAutopilotCommands } from "../../src/extensions/agent-team-loop/autopilot/console.ts";
import { answerGate } from "../../src/extensions/agent-team-loop/autopilot/gate-writer.ts";
import {
	DEFAULT_CONFIG,
	deriveStatusModel,
	gatesDir,
	gatesLockPath,
	listGates,
	nonBeatFilter,
	parseTaskLabels,
	queryTimeline,
	readConfig,
	renderStatusText,
	saveConfig,
	timelinePath,
	usedRounds,
	watermarkFromSince,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import { pmActivate } from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "ap-console-"));
}

// ── Fixtures ─────────────────────────────────────────────────────────────────

/** One timeline event line (D-109 schema): seq N carries ts 12:00:(N-1). */
function tl(seq: number, ev: string, key: string, stage: number | null, detail: string): string {
	return JSON.stringify({
		ts: `2026-09-08T12:${String(Math.floor((seq - 1) / 60)).padStart(2, "0")}:${String((seq - 1) % 60).padStart(2, "0")}+00:00`,
		seq,
		ev,
		key,
		stage,
		detail,
	});
}

/** A gate file in the exact shape gates.py _gate_file_content writes. */
function gateFile(g: {
	id: string;
	kind: string;
	stage: number | null;
	key: string | null;
	question: string;
	status: "pending" | "approved" | "rejected";
	answeredAt?: string;
	answeredBy?: string;
	note?: string;
}): string {
	const lines = [
		"---",
		`id: ${g.id}`,
		`kind: ${g.kind}`,
		`stage: ${g.stage === null ? "" : g.stage}`,
		g.key === null ? "key:" : `key: ${g.key}`,
		"created_at: 2026-09-08T11:00:00+00:00",
		"created_by: conductor",
		`question: '${g.question}'`,
		"context_refs:",
		"  - .agenticdoc/_autopilot/_roadmap.md",
		`status: ${g.status}`,
		`answered_at: ${g.answeredAt ?? ""}`,
		`answered_by: ${g.answeredBy ?? ""}`,
		`note: ${g.note === undefined ? "" : `'${g.note}'`}`,
		"---",
		"",
		`# Gate ${g.id} (${g.kind})`,
		"",
		g.question,
		"",
		"## Context",
		"",
		"- .agenticdoc/_autopilot/_roadmap.md",
	];
	return `${lines.join("\n")}\n`;
}

/**
 * A complete autopilot project fixture:
 *   - config.json (D-110 defaults, enabled)
 *   - _roadmap.md (stage 1 closed, stage 2 running with keys k1/k2)
 *   - _index.parallel (k1 EXECUTE, k2 VERIFY)
 *   - gates: gate-0001 approved, gate-0002/gate-0003 pending
 *   - timeline: rotations .2 (seq 1-2) → .1 (seq 3-4) → current (seq 5-9,
 *     beats at 5 and 7)
 *   - worker task dirs whose loop/attempt labels are the rounds fixture
 *     (see PY_USED_ROUNDS — the VC-020 parity annotation)
 */
function writeStatusFixture(root: string): void {
	const agenticdoc = path.join(root, ".agenticdoc");
	const ap = path.join(agenticdoc, "_autopilot");
	fs.mkdirSync(path.join(ap, "gates"), { recursive: true });

	fs.writeFileSync(
		path.join(ap, "config.json"),
		`${JSON.stringify(
			{
				enabled: true,
				paused: false,
				poll_interval_sec: 4,
				max_parallel_keys: 2,
				round_budget: 2,
				worker_timeout_min: 30,
				l2_read_file_cap: 8,
				l2_read_byte_cap: 65536,
			},
			null,
			2,
		)}\n`,
		"utf8",
	);

	fs.writeFileSync(
		path.join(ap, "_roadmap.md"),
		[
			"# Roadmap",
			"> generated_at: 2026-09-08T00:00:00+00:00",
			"> goal_mtime: 1700000000000",
			"",
			"## Stage 1: Foundation",
			"> goal: lay the ground",
			"> status: closed",
			"> key-status: k0=done",
			"### Keys",
			"| key | role | depends_on |",
			"|-----|------|-----------|",
			"| k0 | ground work | - |",
			"",
			"## Stage 2: Build",
			"> goal: build the thing",
			"> status: running",
			"> key-status: k1=running, k2=done",
			"### Keys",
			"| key | role | depends_on |",
			"|-----|------|-----------|",
			"| k1 | impl | k0 |",
			"| k2 | verify | k0 |",
			"",
		].join("\n"),
		"utf8",
	);

	fs.writeFileSync(
		path.join(agenticdoc, "_index.parallel"),
		[
			"# Index Parallel",
			"| Key | Status | Phase | Claim-Id | Deps | Desc | Updated |",
			"| --- | --- | --- | --- | --- | --- | --- |",
			"| k1 | active | EXECUTE | host:100 | - | key one | 2026-09-08T00:00:00Z |",
			"| k2 | active | VERIFY | host:101 | k1 | key two | 2026-09-08T00:00:00Z |",
			"",
		].join("\n"),
		"utf8",
	);

	fs.writeFileSync(
		path.join(ap, "gates", "gate-0001.md"),
		gateFile({
			id: "gate-0001",
			kind: "stage-confirm",
			stage: 2,
			key: null,
			question: "Approve stage 2 for execution?",
			status: "approved",
			answeredAt: "2026-09-08T11:05:00+00:00",
			answeredBy: "host:100",
			note: "ok to proceed",
		}),
		"utf8",
	);
	fs.writeFileSync(
		path.join(ap, "gates", "gate-0002.md"),
		gateFile({
			id: "gate-0002",
			kind: "stalled",
			stage: 2,
			key: "k1",
			question: "k1 stalled after 2 L2 rounds — retry or legacy-close?",
			status: "pending",
		}),
		"utf8",
	);
	fs.writeFileSync(
		path.join(ap, "gates", "gate-0003.md"),
		gateFile({
			id: "gate-0003",
			kind: "budget-exhausted",
			stage: 2,
			key: "k2",
			question: "k2 retry budget exhausted — how to proceed?",
			status: "pending",
		}),
		"utf8",
	);

	fs.writeFileSync(
		path.join(ap, "timeline.jsonl.2"),
		`${[
			tl(1, "config", "-", null, "conductor start"),
			tl(2, "goal-snapshot", "2", 2, "goal_mtime=1700000000000"),
		].join("\n")}\n`,
		"utf8",
	);
	fs.writeFileSync(
		path.join(ap, "timeline.jsonl.1"),
		`${[
			tl(3, "dispatch", "k1", 2, "ap-k1-ver-1 type=verifier"),
			tl(4, "worker-terminal", "k1", 2, "ap-k1-ver-1 done"),
		].join("\n")}\n`,
		"utf8",
	);
	fs.writeFileSync(
		path.join(ap, "timeline.jsonl"),
		`${[
			tl(5, "beat", "2", 2, ""),
			tl(6, "advance", "k1", 2, "SPEC->DESIGN exit=0"),
			tl(7, "beat", "2", 2, ""),
			tl(8, "gate-created", "2", 2, "gate-0002 stalled"),
			tl(9, "dispatch", "k2", 2, "ap-k2-ver-1 type=verifier"),
		].join("\n")}\n`,
		"utf8",
	);

	const fencedTask = (owner: string, name: string, fm: string[]): void => {
		const dir = path.join(agenticdoc, owner, "workers", name);
		fs.mkdirSync(dir, { recursive: true });
		fs.writeFileSync(path.join(dir, "task.md"), `${["---", ...fm, "---", "", "work", ""].join("\n")}\n`, "utf8");
	};
	fencedTask("k1", "ap-k1-ver-1", ["type: verifier", "origin: conductor", "loop: l2:k1:spec-to-design", "attempt: 1"]);
	fencedTask("k1", "ap-k1-ver-2", ["type: verifier", "origin: conductor", "loop: l2:k1:spec-to-design", "attempt: 2"]);
	fencedTask("k1", "ap-k1-ver-3", ["type: verifier", "origin: conductor", "loop: l2:k1:design-to-plan", "attempt: 1"]);
	fencedTask("k1", "ap-k1-l3-1", ["type: reviewer", "origin: conductor", "loop: l3:k1", "attempt: 1"]);
	fencedTask("k1", "ap-k1-exec-a", ["type: phase-writer", "origin: conductor", "loop: exec:k1:t1", "attempt: 1"]);
	fencedTask("k1", "ap-k1-exec-b", ["type: phase-writer", "origin: conductor", "loop: exec:k1:t1", "attempt: 2"]);
	fencedTask("k1", "ap-k1-exec-c", ["type: phase-writer", "origin: conductor", "loop: exec:k1:t2"]);
	fencedTask("k1", "ap-k1-repair", ["type: repair", "origin: conductor", "loop: repair:k1", "attempt: 1"]);
	fencedTask("k2", "ap-k2-ver-1", ["type: verifier", "origin: conductor", "loop: l2:k2:spec-to-design", "attempt: 1"]);
	// Unlabeled manual task — contributes nothing to any loop budget.
	const manual = path.join(agenticdoc, "k1", "workers", "manual-thing");
	fs.mkdirSync(manual, { recursive: true });
	fs.writeFileSync(path.join(manual, "task.md"), "type: coding\n\nwork\n", "utf8");
}

/**
 * The Python-side derivation for these exact task dirs (autopilot/state.py
 * used_rounds, probed 2026-09-09 against this fixture layout). VC-020 locks
 * the TS implementation to this annotated result — the two sides implement
 * the same file-derivation rule independently.
 */
const PY_USED_ROUNDS: Record<string, number> = {
	"l2:k1:spec-to-design": 2,
	"l2:k1:design-to-plan": 1,
	"l3:k1": 1,
	"exec:k1:t1": 2,
	"exec:k1:t2": 1,
	"repair:k1": 1,
	"l2:k2:spec-to-design": 1,
};

// ── Fake pi / command context ────────────────────────────────────────────────

function fakeConsolePi(): {
	pi: ExtensionAPI;
	commands: Map<string, { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> }>;
	entries: Array<{ customType: string; data: unknown }>;
} {
	const commands = new Map<string, { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> }>();
	const entries: Array<{ customType: string; data: unknown }> = [];
	const pi = {
		registerCommand: (
			name: string,
			opts: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
		) => {
			commands.set(name, opts);
		},
		appendEntry: (customType: string, data: unknown) => {
			entries.push({ customType, data });
		},
	} as unknown as ExtensionAPI;
	return { pi, commands, entries };
}

function fakeCmdCtx(sessionEntries: Array<{ type: string; customType: string; data?: unknown }> = []): {
	ctx: ExtensionCommandContext;
	notifications: string[];
} {
	const notifications: string[] = [];
	const ctx = {
		hasUI: true,
		ui: {
			notify: (message: string) => {
				notifications.push(message);
			},
		},
		sessionManager: { getEntries: () => sessionEntries },
	} as unknown as ExtensionCommandContext;
	return { ctx, notifications };
}

// ── Status model derivation (VC-017 / AC-015) ────────────────────────────────

describe("status model derivation (VC-017 / AC-015)", () => {
	it("VC-017: status --json shape — stage/gates/timeline field groups + schema version + rounds structure, rebuilt from fixture files in <10s", () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const t0 = Date.now();
			const result = deriveStatusModel(root);
			const elapsedMs = Date.now() - t0;
			expect(result.ok).toBe(true);
			if (!result.ok) return;
			expect(elapsedMs).toBeLessThan(10_000);

			const s = result.model.status;
			expect(s.schema).toBe("autopilot-status/1");
			// stage group: current stage + per-key phase/state/rounds (AC-018)
			expect(s.stage).toEqual({
				current: 2,
				status: "running",
				keys: [
					{
						key: "k1",
						phase: "EXECUTE",
						state: "running",
						rounds: { l2: { used: 2, max: 2 }, l3: { used: 1, max: 2 }, retry: { used: 2, max: 2 } },
					},
					{
						key: "k2",
						phase: "VERIFY",
						state: "done",
						rounds: { l2: { used: 1, max: 2 }, l3: { used: 0, max: 2 }, retry: { used: 0, max: 2 } },
					},
				],
			});
			// gates group: all gates, seq order, {id, kind, status}
			expect(s.gates).toEqual([
				{ id: "gate-0001", kind: "stage-confirm", status: "approved" },
				{ id: "gate-0002", kind: "stalled", status: "pending" },
				{ id: "gate-0003", kind: "budget-exhausted", status: "pending" },
			]);
			// timeline group: the last-seen watermark {seq, ts}
			expect(s.timeline).toEqual({ seq: 9, ts: "2026-09-08T12:00:08+00:00" });
			// config group: round_budget is the rounds max source (AC-011)
			expect(s.config).toEqual({ enabled: true, poll_interval_sec: 4, round_budget: 2, max_parallel_keys: 2 });
			expect(result.model.paused).toBe(false);
			// A clean fixture parses without a single warning.
			expect(result.model.warnings).toEqual([]);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-017: view parity — every number in the human view equals the --json values", () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const result = deriveStatusModel(root);
			expect(result.ok).toBe(true);
			if (!result.ok) return;
			const text = renderStatusText(result.model);
			const s = result.model.status;
			expect(text).toContain(`stage ${s.stage.current} (${s.stage.status})`);
			for (const k of s.stage.keys) {
				expect(text).toContain(`${k.key} | phase=${k.phase} | state=${k.state}`);
				expect(text).toContain(`L2 ${k.rounds.l2.used}/${k.rounds.l2.max}`);
				expect(text).toContain(`L3 ${k.rounds.l3.used}/${k.rounds.l3.max}`);
				expect(text).toContain(`retry ${k.rounds.retry.used}/${k.rounds.retry.max}`);
			}
			expect(text).toContain(`gates: ${s.gates.length} total`);
			for (const g of s.gates) expect(text).toContain(`${g.id} ${g.kind} ${g.status}`);
			expect(text).toContain(`timeline: seq=${s.timeline.seq} ts=${s.timeline.ts}`);
			expect(text).toContain(`enabled=${s.config.enabled}`);
			expect(text).toContain(`poll_interval_sec=${s.config.poll_interval_sec}`);
			expect(text).toContain(`round_budget=${s.config.round_budget}`);
			expect(text).toContain(`max_parallel_keys=${s.config.max_parallel_keys}`);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-017: a second derivation (console closed and reopened, D-005) is identical — no process state", () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const first = deriveStatusModel(root);
			const second = deriveStatusModel(root);
			expect(second).toEqual(first);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-015: a project without autopilot files degrades to empty views, not an error", () => {
		const root = mkdtemp();
		try {
			const result = deriveStatusModel(root);
			expect(result.ok).toBe(true);
			if (!result.ok) return;
			const s = result.model.status;
			expect(s.stage).toEqual({ current: 0, status: "none", keys: [] });
			expect(s.gates).toEqual([]);
			expect(s.timeline).toEqual({ seq: 0, ts: "" });
			expect(s.config).toEqual({ enabled: false, poll_interval_sec: 4, round_budget: 2, max_parallel_keys: 2 });
			// The missing roadmap surfaces as a warning in the human view.
			expect(result.model.warnings.join("\n")).toContain("roadmap file not found");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-015: corrupt gate files are excluded from the queue and reported, never silently wrong", () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			fs.writeFileSync(
				path.join(gatesDir(root), "gate-0004.md"),
				"---\nid: gate-0004\nkind: mystery\n---\n\nbroken\n",
				"utf8",
			);
			const scan = listGates(root);
			expect(scan.gates.map((g) => g.id)).toEqual(["gate-0001", "gate-0002", "gate-0003"]);
			expect(scan.errors.join("\n")).toContain("gate-0004");
			expect(scan.errors.join("\n")).toContain("mystery");
			const result = deriveStatusModel(root);
			expect(result.ok).toBe(true);
			if (!result.ok) return;
			expect(result.model.status.gates).toHaveLength(3);
			expect(result.model.warnings.join("\n")).toContain("gate-0004");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── Rounds parity with Python state.py (VC-020 / AC-018) ─────────────────────

describe("rounds parity with Python state.py (VC-020 / AC-018)", () => {
	it("VC-020: usedRounds equals the Python derivation annotated for this fixture (same task dirs, same rule)", () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const k1Workers = path.join(root, ".agenticdoc", "k1", "workers");
			const k2Workers = path.join(root, ".agenticdoc", "k2", "workers");
			const result = usedRounds([k1Workers, k2Workers]);
			expect(Object.fromEntries(result)).toEqual(PY_USED_ROUNDS);

			// The status rounds are the family aggregation of those per-loop
			// counts: l2/l3/retry = most-consumed loop in the family, max =
			// config round_budget (k1: max(l2 edges 2,1)=2, l3=1,
			// max(exec 2, exec 1, repair 1)=2).
			const model = deriveStatusModel(root);
			expect(model.ok).toBe(true);
			if (!model.ok) return;
			const k1 = model.model.status.stage.keys.find((k) => k.key === "k1");
			expect(k1?.rounds).toEqual({
				l2: { used: 2, max: 2 },
				l3: { used: 1, max: 2 },
				retry: { used: 2, max: 2 },
			});
			const k2 = model.model.status.stage.keys.find((k) => k.key === "k2");
			expect(k2?.rounds).toEqual({ l2: { used: 1, max: 2 }, l3: { used: 0, max: 2 }, retry: { used: 0, max: 2 } });
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-020: a missing attempt label degrades to directory-identity counting — the same dir rewritten never double-counts", () => {
		const root = mkdtemp();
		const workers = path.join(root, ".agenticdoc", "kx", "workers");
		fs.mkdirSync(path.join(workers, "t-a"), { recursive: true });
		fs.writeFileSync(path.join(workers, "t-a", "task.md"), "---\nloop: exec:kx:t9\n---\n\nwork\n", "utf8");
		expect(usedRounds([workers]).get("exec:kx:t9")).toBe(1);
		// Orphan re-insertion shape: same dir, same loop, still no attempt.
		fs.writeFileSync(
			path.join(workers, "t-a", "task.md"),
			"---\norigin: conductor\nloop: exec:kx:t9\n---\n\nwork again\n",
			"utf8",
		);
		expect(usedRounds([workers]).get("exec:kx:t9")).toBe(1);
		// A second dir in the same loop without attempt labels: 2 units.
		fs.mkdirSync(path.join(workers, "t-b"), { recursive: true });
		fs.writeFileSync(path.join(workers, "t-b", "task.md"), "---\nloop: exec:kx:t9\n---\n\nwork\n", "utf8");
		expect(usedRounds([workers]).get("exec:kx:t9")).toBe(2);
		fs.rmSync(root, { recursive: true, force: true });
	});

	it("VC-020 anchor: parseTaskLabels mirrors state.py on CRLF task.md (probed values)", () => {
		const root = mkdtemp();
		const dir = path.join(root, "crlf-task");
		fs.mkdirSync(dir, { recursive: true });
		fs.writeFileSync(
			path.join(dir, "task.md"),
			"---\r\ntype: verifier\r\nloop: l2:k1:crlf-edge\r\nattempt: 3\r\n---\r\n\r\nwork\r\n",
			"utf8",
		);
		// Python parse_task_labels on this file: {attempt: "3", loop:
		// "l2:k1:crlf-edge", type: "verifier"} (probed 2026-09-09).
		expect(Object.fromEntries(parseTaskLabels(path.join(dir, "task.md")))).toEqual({
			type: "verifier",
			loop: "l2:k1:crlf-edge",
			attempt: "3",
		});
		fs.rmSync(root, { recursive: true, force: true });
	});
});

// ── Gate writer (AC-016 / D-105) ──────────────────────────────────────────────

describe("gate writer (AC-016 / D-105)", () => {
	it("AC-016: approve rewrites exactly the four answer fields; every other line is byte-preserved", async () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const gateFile = path.join(gatesDir(root), "gate-0002.md");
			const before = fs.readFileSync(gateFile, "utf8");
			const result = await answerGate({
				gateFile,
				lockFile: gatesLockPath(root),
				decision: "approve",
				note: "retry once with a narrower scope",
				answeredBy: "console-host:4242",
			});
			expect(result.ok).toBe(true);
			const after = fs.readFileSync(gateFile, "utf8");

			const beforeLines = before.split("\n");
			const afterLines = after.split("\n");
			expect(afterLines).toHaveLength(beforeLines.length);
			const answerFields = new Set(["status", "answered_at", "answered_by", "note"]);
			let changed = 0;
			for (let i = 0; i < beforeLines.length; i++) {
				if (beforeLines[i] === afterLines[i]) continue;
				changed += 1;
				const name = /^([A-Za-z_][A-Za-z0-9_]*):/.exec(beforeLines[i] ?? "")?.[1];
				expect(answerFields.has(name ?? ""), `line ${i} changed: '${beforeLines[i]}' -> '${afterLines[i]}'`).toBe(
					true,
				);
			}
			expect(changed).toBe(4);
			expect(after).toContain("status: approved");
			expect(after).toMatch(/^answered_by: console-host:4242$/m);
			// Z-form second-precision ISO — the exact shape gates.py _check_iso accepts.
			expect(after).toMatch(/^answered_at: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/m);
			expect(after).toContain("note: 'retry once with a narrower scope'");
			// Body and context untouched.
			expect(after).toContain("k1 stalled after 2 L2 rounds — retry or legacy-close?");
			expect(after).toContain("  - .agenticdoc/_autopilot/_roadmap.md");
			// The lock was released.
			expect(fs.existsSync(gatesLockPath(root))).toBe(false);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-016: reject without a note rewrites the answer fields and clears the note", async () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const gateFile = path.join(gatesDir(root), "gate-0003.md");
			const result = await answerGate({
				gateFile,
				lockFile: gatesLockPath(root),
				decision: "reject",
				answeredBy: "console-host:4242",
			});
			expect(result.ok).toBe(true);
			expect(result.ok && result.status).toBe("rejected");
			const after = fs.readFileSync(gateFile, "utf8");
			expect(after).toContain("status: rejected");
			expect(after).toMatch(/^note:$/m);
			expect(after).toMatch(/^answered_at: \d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/m);
			expect(after).toMatch(/^answered_by: console-host:4242$/m);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-016: answering is mutually exclusive with a held .mw/gates.lock (O_CREAT|O_EXCL)", async () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const gateFile = path.join(gatesDir(root), "gate-0002.md");
			const lockFile = gatesLockPath(root);
			fs.mkdirSync(path.dirname(lockFile), { recursive: true });
			fs.writeFileSync(lockFile, "", "utf8"); // a concurrent holder
			const before = fs.readFileSync(gateFile, "utf8");
			const blocked = await answerGate({
				gateFile,
				lockFile,
				decision: "approve",
				answeredBy: "h:1",
				lockOpts: { retries: 1, baseDelayMs: 1 },
			});
			expect(blocked.ok).toBe(false);
			if (!blocked.ok) expect(blocked.error).toContain("lock");
			expect(fs.readFileSync(gateFile, "utf8")).toBe(before); // untouched

			fs.unlinkSync(lockFile);
			const retry = await answerGate({
				gateFile,
				lockFile,
				decision: "approve",
				answeredBy: "h:1",
				lockOpts: { retries: 1, baseDelayMs: 1 },
			});
			expect(retry.ok).toBe(true);
			expect(fs.readFileSync(gateFile, "utf8")).toContain("status: approved");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-016: unknown gate ids, missing status lines, and multiline notes are refused", async () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const lockFile = gatesLockPath(root);
			const missing = await answerGate({
				gateFile: path.join(gatesDir(root), "gate-9999.md"),
				lockFile,
				decision: "approve",
				answeredBy: "h:1",
			});
			expect(missing.ok).toBe(false);

			const corrupt = path.join(gatesDir(root), "gate-0004.md");
			fs.writeFileSync(corrupt, "---\nid: gate-0004\nkind: stalled\nquestion: 'q?'\n---\n\nno status\n", "utf8");
			const refused = await answerGate({ gateFile: corrupt, lockFile, decision: "approve", answeredBy: "h:1" });
			expect(refused.ok).toBe(false);
			if (!refused.ok) expect(refused.error).toContain("status");

			const multiline = await answerGate({
				gateFile: path.join(gatesDir(root), "gate-0002.md"),
				lockFile,
				decision: "approve",
				note: "line one\nline two",
				answeredBy: "h:1",
			});
			expect(multiline.ok).toBe(false);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── Timeline replay (VC-017 / D-109) ─────────────────────────────────────────

describe("timeline replay (VC-017 / D-109)", () => {
	it("D-109: default replay filters beats and applies the last-seen watermark", () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const q = queryTimeline(timelinePath(root), 4, nonBeatFilter());
			expect(q.events.map((e) => e.seq)).toEqual([6, 8, 9]);
			expect(q.events.every((e) => e.ev !== "beat")).toBe(true);
			expect(q.pruned).toBe(0);
			expect(q.head).toEqual({ seq: 9, ts: "2026-09-08T12:00:08+00:00" });
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("D-109: --all replays everything including beats, oldest rotation first", () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const q = queryTimeline(timelinePath(root), 0, undefined);
			expect(q.events.map((e) => e.seq)).toEqual([1, 2, 3, 4, 5, 6, 7, 8, 9]);
			expect(q.events.filter((e) => e.ev === "beat").map((e) => e.seq)).toEqual([5, 7]);
			expect(q.pruned).toBe(0);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("D-109: a watermark predating the retained chain reports N events pruned — never a silent gap", () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			// Drop the oldest generation (.2): oldest retained seq becomes 3.
			fs.rmSync(path.join(root, ".agenticdoc", "_autopilot", "timeline.jsonl.2"));
			const q0 = queryTimeline(timelinePath(root), 0, nonBeatFilter());
			expect(q0.pruned).toBe(2); // seq 1-2 lost to rotation
			expect(q0.events.map((e) => e.seq)).toEqual([3, 4, 6, 8, 9]);
			const q1 = queryTimeline(timelinePath(root), 1, nonBeatFilter());
			expect(q1.pruned).toBe(1);
			// Torn lines are counted, not hidden.
			fs.appendFileSync(path.join(root, ".agenticdoc", "_autopilot", "timeline.jsonl"), '{"broken": \n', "utf8");
			const q2 = queryTimeline(timelinePath(root), 8, nonBeatFilter());
			expect(q2.skipped).toBe(1);
			expect(q2.events.map((e) => e.seq)).toEqual([9]);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("D-109: an empty chain with a positive watermark reports the watermark's worth as pruned", () => {
		const root = mkdtemp();
		try {
			const q = queryTimeline(timelinePath(root), 7, nonBeatFilter());
			expect(q.events).toEqual([]);
			expect(q.pruned).toBe(7);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("D-109: --since maps an ISO timestamp onto the seq watermark", () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			// Events at/before 12:00:03 are seq 1-4 → mark 4 → replay 5-9.
			expect(watermarkFromSince(timelinePath(root), "2026-09-08T12:00:03+00:00")).toBe(4);
			const q = queryTimeline(
				timelinePath(root),
				watermarkFromSince(timelinePath(root), "2026-09-08T12:00:03+00:00"),
				nonBeatFilter(),
			);
			expect(q.events.map((e) => e.seq)).toEqual([6, 8, 9]);
			// Before everything → mark 0 → full replay.
			expect(watermarkFromSince(timelinePath(root), "2026-09-07T00:00:00+00:00")).toBe(0);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── Config (D-110) ────────────────────────────────────────────────────────────

describe("config read/write (D-110)", () => {
	it("D-110: validation mirrors config.py — invalid values fail closed on read and write", () => {
		const root = mkdtemp();
		try {
			fs.mkdirSync(path.join(root, ".agenticdoc", "_autopilot"), { recursive: true });
			fs.writeFileSync(
				path.join(root, ".agenticdoc", "_autopilot", "config.json"),
				`${JSON.stringify({ enabled: true, poll_interval_sec: 9 })}\n`,
				"utf8",
			);
			const read = readConfig(root);
			expect(read.ok).toBe(false);
			if (!read.ok) expect(read.error).toContain("poll_interval_sec");

			const tooLow = saveConfig(root, { ...DEFAULT_CONFIG, max_parallel_keys: 1 });
			expect(tooLow.ok).toBe(false);
			const unknown = saveConfig(root, { ...DEFAULT_CONFIG, extra: "x" } as unknown as Parameters<
				typeof saveConfig
			>[1]);
			expect(unknown.ok).toBe(false);
			if (!unknown.ok) expect(unknown.error).toContain("unknown field");
			// Nothing was written by the refused saves.
			expect(
				JSON.parse(fs.readFileSync(path.join(root, ".agenticdoc", "_autopilot", "config.json"), "utf8")),
			).toEqual({
				enabled: true,
				poll_interval_sec: 9,
			});
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("D-110: a missing config file yields the defaults with zero footprint", () => {
		const root = mkdtemp();
		try {
			const read = readConfig(root);
			expect(read.ok).toBe(true);
			if (read.ok) expect(read.config).toEqual(DEFAULT_CONFIG);
			expect(fs.existsSync(path.join(root, ".agenticdoc"))).toBe(false);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── /autopilot command set (VC-017 / AC-015/016/025) ─────────────────────────

describe("/autopilot command set (VC-017 / AC-015 / AC-016 / AC-025)", () => {
	it("VC-017: /autopilot status --json emits the schema-versioned JSON and persists the timeline watermark session entry", async () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const { pi, commands, entries } = fakeConsolePi();
			registerAutopilotCommands(pi, root);
			const { ctx, notifications } = fakeCmdCtx();
			await commands.get("autopilot")?.handler("status --json", ctx);
			const parsed = JSON.parse(notifications[0] ?? "");
			expect(parsed.schema).toBe("autopilot-status/1");
			expect(parsed.stage.current).toBe(2);
			expect(parsed.timeline.seq).toBe(9);
			expect(entries).toContainEqual({
				customType: "agent-team-loop:autopilot-seen",
				data: { seq: 9, ts: "2026-09-08T12:00:08+00:00" },
			});
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-017: /autopilot timeline replays from the session watermark with beats filtered; --all includes them", async () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const { pi, commands, entries } = fakeConsolePi();
			registerAutopilotCommands(pi, root);
			const { ctx, notifications } = fakeCmdCtx([
				{
					type: "custom",
					customType: "agent-team-loop:autopilot-seen",
					data: { seq: 4, ts: "2026-09-08T12:00:03+00:00" },
				},
			]);
			await commands.get("autopilot")?.handler("timeline", ctx);
			const replay = notifications[0] ?? "";
			expect(replay).toContain("6 2026-09-08T12:00:05+00:00 advance key=k1 stage=2 SPEC->DESIGN exit=0");
			expect(replay).toContain("9 2026-09-08T12:00:08+00:00 dispatch key=k2 stage=2");
			expect(replay).not.toContain("beat");
			expect(replay).not.toContain("events pruned");
			const seen = entries.filter((e) => e.customType === "agent-team-loop:autopilot-seen");
			expect(seen.at(-1)?.data).toEqual({ seq: 9, ts: "2026-09-08T12:00:08+00:00" });

			await commands.get("autopilot")?.handler("timeline --all", ctx);
			const all = notifications[1] ?? "";
			expect(all).toContain("1 2026-09-08T12:00:00+00:00 config key=-");
			expect(all).toContain("5 2026-09-08T12:00:04+00:00 beat");
			expect(all).toContain("7 2026-09-08T12:00:06+00:00 beat");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("D-109: /autopilot timeline shows the pruned notice when the watermark predates the retained chain", async () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			fs.rmSync(path.join(root, ".agenticdoc", "_autopilot", "timeline.jsonl.2"));
			const { pi, commands } = fakeConsolePi();
			registerAutopilotCommands(pi, root);
			const { ctx, notifications } = fakeCmdCtx(); // no session entry → watermark 0
			await commands.get("autopilot")?.handler("timeline", ctx);
			expect(notifications[0]).toContain("2 events pruned");
			expect(notifications[0]).toContain("3 2026-09-08T12:00:02+00:00 dispatch");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("D-109: /autopilot timeline --since replays events after that timestamp", async () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const { pi, commands } = fakeConsolePi();
			registerAutopilotCommands(pi, root);
			const { ctx, notifications } = fakeCmdCtx();
			await commands.get("autopilot")?.handler("timeline --since 2026-09-08T12:00:03+00:00", ctx);
			const text = notifications[0] ?? "";
			expect(text).not.toContain("1 2026-09-08T12:00:00+00:00");
			expect(text).toContain("6 2026-09-08T12:00:05+00:00 advance");
			expect(text).toContain("9 2026-09-08T12:00:08+00:00 dispatch");
			// An invalid --since is refused, not silently ignored.
			await commands.get("autopilot")?.handler("timeline --since not-a-date", ctx);
			expect(notifications[1]).toContain("invalid --since");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-016: /autopilot gate <id> approve --note answers via the gates lock", async () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const { pi, commands } = fakeConsolePi();
			registerAutopilotCommands(pi, root);
			const { ctx, notifications } = fakeCmdCtx();
			await commands.get("autopilot")?.handler("gate gate-0002 approve --note retry once, narrower scope", ctx);
			expect(notifications[0]).toContain("gate-0002 approved");
			const after = fs.readFileSync(path.join(gatesDir(root), "gate-0002.md"), "utf8");
			expect(after).toContain("status: approved");
			expect(after).toContain("note: 'retry once, narrower scope'");
			expect(after).toMatch(/^answered_by: [^\s]+:\d+$/m); // this window's claimId
			expect(fs.existsSync(gatesLockPath(root))).toBe(false);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-016: /autopilot gate with an unknown id fails and lists the pending gates", async () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const { pi, commands } = fakeConsolePi();
			registerAutopilotCommands(pi, root);
			const { ctx, notifications } = fakeCmdCtx();
			await commands.get("autopilot")?.handler("gate gate-9999 approve", ctx);
			expect(notifications[0]).toContain("gate answer failed");
			expect(notifications[1]).toContain("gate-0002");
			// Path traversal via the id is refused up front.
			await commands.get("autopilot")?.handler("gate ../evil approve", ctx);
			expect(notifications[2]).toContain("invalid gate id");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-015: /autopilot gates lists pending gates; /autopilot roadmap summarizes stages", async () => {
		const root = mkdtemp();
		writeStatusFixture(root);
		try {
			const { pi, commands } = fakeConsolePi();
			registerAutopilotCommands(pi, root);
			const { ctx, notifications } = fakeCmdCtx();
			await commands.get("autopilot")?.handler("gates", ctx);
			const gates = notifications[0] ?? "";
			expect(gates).toContain("2 pending gate(s)");
			expect(gates).toContain("gate-0002 [stalled] stage=2 key=k1");
			expect(gates).toContain("gate-0003 [budget-exhausted] stage=2 key=k2");
			expect(gates).toContain("/autopilot gate gate-0002 approve|reject");
			expect(gates).not.toContain("gate-0001");

			await commands.get("autopilot")?.handler("roadmap", ctx);
			const roadmap = notifications[1] ?? "";
			expect(roadmap).toContain("Stage 1: Foundation — closed");
			expect(roadmap).toContain("Stage 2: Build — running");
			expect(roadmap).toContain("goal: build the thing");
			expect(roadmap).toContain("k1=running, k2=done");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-025: /autopilot enable writes config and starts mw when it is not running; disable/pause/resume write config only", async () => {
		const root = mkdtemp();
		try {
			const starts: string[] = [];
			const { pi, commands } = fakeConsolePi();
			registerAutopilotCommands(pi, root, {
				ensureMwRunning: (dir) => {
					starts.push(dir);
					return "started";
				},
			});
			const { ctx, notifications } = fakeCmdCtx();
			const configFile = path.join(root, ".agenticdoc", "_autopilot", "config.json");

			await commands.get("autopilot")?.handler("enable", ctx);
			expect(starts).toEqual([root]);
			expect(notifications[0]).toContain("enabled");
			const enabled = JSON.parse(fs.readFileSync(configFile, "utf8"));
			expect(enabled).toEqual({
				enabled: true,
				paused: false,
				poll_interval_sec: 4,
				max_parallel_keys: 2,
				round_budget: 2,
				worker_timeout_min: 30,
				l2_read_file_cap: 8,
				l2_read_byte_cap: 65536,
			});
			// Same shape config.py save_config writes: indent-2 + trailing newline.
			expect(fs.readFileSync(configFile, "utf8").endsWith("}\n")).toBe(true);

			await commands.get("autopilot")?.handler("disable", ctx);
			expect(JSON.parse(fs.readFileSync(configFile, "utf8")).enabled).toBe(false);
			expect(starts).toHaveLength(1); // disable never spawns

			await commands.get("autopilot")?.handler("pause", ctx);
			expect(notifications[2]).toContain("paused");
			expect(JSON.parse(fs.readFileSync(configFile, "utf8")).paused).toBe(true);

			await commands.get("autopilot")?.handler("resume", ctx);
			expect(notifications[3]).toContain("resumed");
			expect(JSON.parse(fs.readFileSync(configFile, "utf8")).paused).toBe(false);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("AC-025: enable against a running mw does not spawn a second serve", async () => {
		const root = mkdtemp();
		try {
			const { pi, commands } = fakeConsolePi();
			registerAutopilotCommands(pi, root, {
				ensureMwRunning: () => "already-running",
			});
			const { ctx, notifications } = fakeCmdCtx();
			await commands.get("autopilot")?.handler("enable", ctx);
			expect(notifications[0]).toContain("mw serve is running");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("D-110: an invalid config makes status fail closed with the offending field", async () => {
		const root = mkdtemp();
		try {
			fs.mkdirSync(path.join(root, ".agenticdoc", "_autopilot"), { recursive: true });
			fs.writeFileSync(
				path.join(root, ".agenticdoc", "_autopilot", "config.json"),
				`${JSON.stringify({ round_budget: 0 })}\n`,
				"utf8",
			);
			const { pi, commands } = fakeConsolePi();
			registerAutopilotCommands(pi, root);
			const { ctx, notifications } = fakeCmdCtx();
			await commands.get("autopilot")?.handler("status --json", ctx);
			expect(notifications[0]).toContain("status unavailable");
			expect(notifications[0]).toContain("round_budget");
			await commands.get("autopilot")?.handler("pause", ctx);
			expect(notifications[1]).toContain("round_budget");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("T-15: pmActivate registers the /autopilot command (and the poll loop tears down)", async () => {
		const root = mkdtemp();
		fs.mkdirSync(path.join(root, ".agenticdoc"), { recursive: true });
		const cwd = process.cwd();
		process.chdir(root);
		try {
			const handlers = new Map<string, (event?: unknown) => unknown>();
			const commands = new Map<string, { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> }>();
			const pi = {
				registerCommand: (
					name: string,
					opts: { handler: (args: string, ctx: ExtensionCommandContext) => Promise<void> },
				) => {
					commands.set(name, opts);
				},
				registerTool: () => {},
				on: (name: string, handler: (event?: unknown) => unknown) => {
					handlers.set(name, handler);
				},
				appendEntry: () => {},
				sendMessage: () => {},
			} as unknown as ExtensionAPI;
			pmActivate(pi);
			expect(commands.has("autopilot")).toBe(true);
			// The autopilot command is wired to real derivations on this project.
			const { ctx, notifications } = fakeCmdCtx();
			await commands.get("autopilot")?.handler("status", ctx);
			expect(notifications[0]).toContain("stage: none");
			// Stop the poll loop so no live timer outlives the test.
			const shutdown = handlers.get("session_shutdown");
			expect(typeof shutdown).toBe("function");
			shutdown?.();
		} finally {
			process.chdir(cwd);
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});
