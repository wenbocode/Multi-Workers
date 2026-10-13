/**
 * T-10 state surface (mw-autopilot-gate-alarm-liveness AC-001/AC-003/AC-010/
 * AC-016): resident pending-gate rows, the stage main-gate rows, the six-value
 * suppression-reason enum, the corrected drop order, the no-longer-silent
 * unreadable queue, the no-watch drop record, and the per-key `blockedOnHuman`
 * derivation.
 *
 * Pure file fixtures + a fake pi; no provider APIs, keys, or network.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ExtensionAPI } from "../../src/core/extensions/types.ts";
import {
	type MonitorSnapshot,
	readMonitorState,
	renderMonitorLines,
} from "../../src/extensions/agent-team-loop/autopilot/monitor.ts";
import {
	blockedOnHuman,
	deriveGateReason,
	GATE_REASONS,
	GATE_SCOPE_UNRESOLVED,
	GATE_SUPPRESSION_PRIORITY,
	gatesDir,
	readGateReminders,
	reminderCountForGate,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";
import {
	GATE_REMINDER_DROPPED_ENTRY_TYPE,
	startWorkerPollLoop,
} from "../../src/extensions/agent-team-loop/pm/pm-orchestrator.ts";
import type { PmUiHolder, PmWatchState } from "../../src/extensions/agent-team-loop/pm/ui-bridge.ts";
import { AckStore } from "../../src/extensions/agent-team-loop/shared/ack-store.ts";
import { IndexStore } from "../../src/extensions/agent-team-loop/shared/index-store.ts";
import { WorkerStore } from "../../src/extensions/agent-team-loop/shared/worker-store.ts";

const NOW_MS = Date.parse("2026-10-13T12:00:00+00:00");
const LINE_MAX = 110;

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "mwgal-t10-"));
}

function ap(root: string): string {
	return path.join(root, ".agenticdoc", "_autopilot");
}

function writeConfig(root: string, extra: Record<string, unknown> = {}): void {
	fs.mkdirSync(ap(root), { recursive: true });
	fs.writeFileSync(
		path.join(ap(root), "config.json"),
		`${JSON.stringify({ enabled: true, paused: false, ...extra }, null, 2)}\n`,
		"utf8",
	);
}

function writeRoadmap(root: string, text: string): void {
	fs.mkdirSync(ap(root), { recursive: true });
	fs.writeFileSync(path.join(ap(root), "_roadmap.md"), text, "utf8");
}

function writeGate(
	root: string,
	g: { id: string; kind: string; stage?: number | null; key?: string; status?: string; createdAt?: string },
): void {
	const dir = gatesDir(root);
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(
		path.join(dir, `${g.id}.md`),
		[
			"---",
			`id: ${g.id}`,
			`kind: ${g.kind}`,
			`stage: ${g.stage === null || g.stage === undefined ? "" : g.stage}`,
			`key: ${g.key ?? ""}`,
			`created_at: ${g.createdAt ?? "2026-10-13T11:00:00+00:00"}`,
			"created_by: conductor",
			"question: 'Proceed?'",
			"context_refs:",
			"  - .agenticdoc/_autopilot/_roadmap.md",
			`status: ${g.status ?? "pending"}`,
			"---",
			"",
			`# Gate ${g.id}`,
			"",
		].join("\n"),
		"utf8",
	);
}

function writeLedger(root: string, rows: Array<Record<string, unknown>>): void {
	fs.mkdirSync(ap(root), { recursive: true });
	fs.writeFileSync(
		path.join(ap(root), "auto-decisions.jsonl"),
		`${rows.map((r) => JSON.stringify(r)).join("\n")}\n`,
		"utf8",
	);
}

function writeWorkers(
	root: string,
	rows: Array<{ key: string; status: string; ownerKey?: string; origin?: string }>,
): void {
	const agenticdoc = path.join(root, ".agenticdoc");
	fs.mkdirSync(agenticdoc, { recursive: true });
	const lines = rows.map((r) => {
		const owner = r.ownerKey ?? "_scratch";
		return (
			`${r.key} | ${r.status} | pi | timi | ` +
			`${path.join(agenticdoc, owner, "workers", r.key, "task.md")} | ` +
			`2026-10-13T11:30:00+00:00 | 2026-10-13T11:30:00+00:00 |  | ${r.origin ?? "conductor"}`
		);
	});
	fs.writeFileSync(path.join(agenticdoc, "_workers.parallel"), `${lines.join("\n")}\n`, "utf8");
}

const ROADMAP_TWO_STAGES = [
	"# Roadmap",
	"> generated_at: 2026-10-13T00:00:00+00:00",
	"> goal_mtime: 1",
	"",
	"## Stage 1: Foundation",
	"> goal: ground",
	"> status: closed",
	"> key-status: k0=done",
	"### Keys",
	"| key | role | depends_on |",
	"|-----|------|-----------|",
	"| k0 | ground | - |",
	"",
	"## Stage 2: Build",
	"> goal: build",
	"> status: running",
	"> key-status: k1=stalled, k2=pending-review",
	"### Keys",
	"| key | role | depends_on |",
	"|-----|------|-----------|",
	"| k1 | impl | k0 |",
	"| k2 | verify | k0 |",
	"",
].join("\n");

// ── AC-003: the closed enum + funnel priority (pure) ────────────────────────

describe("AC-003 six-value suppression enum and funnel priority", () => {
	it("declares exactly the six closed values in the card order", () => {
		expect([...GATE_REASONS]).toEqual([
			"gate-queue-unreadable",
			"key-in-flight",
			"cap-reached",
			"stage-terminal",
			"not-due",
			"unresolved-scope",
		]);
		expect([...GATE_SUPPRESSION_PRIORITY]).toEqual([
			"gate-queue-unreadable",
			"key-in-flight",
			"cap-reached",
			"stage-terminal",
			"not-due",
		]);
	});

	it("deriveGateReason returns each value and follows funnel precedence", () => {
		const base = {
			queueUnreadable: false,
			inFlightForKey: 0,
			reminders: 0,
			reminderMax: 2,
			stageTerminal: false,
			due: true,
		};
		expect(deriveGateReason(base)).toBeNull(); // due, not suppressed → reason=-
		expect(deriveGateReason({ ...base, due: null })).toBeNull(); // unknown anchor, not a guess
		expect(deriveGateReason({ ...base, due: false })).toBe("not-due");
		expect(deriveGateReason({ ...base, stageTerminal: true, due: false })).toBe("stage-terminal");
		expect(deriveGateReason({ ...base, reminders: 2, stageTerminal: true, due: false })).toBe("cap-reached");
		expect(deriveGateReason({ ...base, inFlightForKey: 1, reminders: 2, stageTerminal: true, due: false })).toBe(
			"key-in-flight",
		);
		expect(
			deriveGateReason({
				...base,
				queueUnreadable: true,
				inFlightForKey: 1,
				reminders: 2,
				stageTerminal: true,
				due: false,
			}),
		).toBe("gate-queue-unreadable");
		// The orthogonal marker has no suppression seat: it is a scope fact.
		expect(GATE_SCOPE_UNRESOLVED).toBe("unresolved-scope");
	});
});

// ── AC-001/AC-003: resident rows carry scope/age/reason ─────────────────────

describe("AC-001/AC-003 resident pending-gate rows", () => {
	it("shows id/kind/key/stage/age/reason/scope for every pending gate with no cap", () => {
		const root = mkdtemp();
		try {
			writeConfig(root);
			writeRoadmap(root, ROADMAP_TWO_STAGES);
			// 15 pending gates — no cap, no dedup, one row each.
			for (let i = 1; i <= 15; i++) {
				writeGate(root, { id: `gate-${String(i).padStart(4, "0")}`, kind: "stalled", stage: 2, key: "k1" });
			}
			const snap = readMonitorState(root, NOW_MS);
			expect(snap.gates).toHaveLength(15);
			const lines = renderMonitorLines(snap);
			const rows = lines.filter((l) => l.startsWith("gates:") || l.startsWith("  · "));
			expect(rows.length).toBeGreaterThanOrEqual(15);
			// A due gate (no reminders, created 60m ago, after_min default 30)
			// renders the explicit `reason=-`, never an empty value.
			expect(rows.join("\n")).toContain("reason=-");
			expect(rows.join("\n")).toContain("age=1h 0m");
			// The gate's own key resolves against the roadmap → no unresolved marker.
			expect(rows.join("\n")).not.toContain("scope=unresolved-scope");
			for (const line of lines) expect(line.length).toBeLessThanOrEqual(LINE_MAX);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("marks an off-roadmap gate with the orthogonal unresolved-scope token", () => {
		const root = mkdtemp();
		try {
			writeConfig(root);
			writeRoadmap(root, ROADMAP_TWO_STAGES);
			writeGate(root, { id: "gate-0001", kind: "stalled", stage: null, key: "ghost-key" });
			const snap = readMonitorState(root, NOW_MS);
			expect(snap.gates[0]?.scopeResolved).toBe(false);
			// The scope fact is orthogonal: it never replaces the suppression reason.
			expect(snap.gates[0]?.reason).toBeNull();
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("renders the unresolved-scope marker on a narrow row (no width pressure)", () => {
		const snap: MonitorSnapshot = {
			serve: { running: false, pid: null, stale: false, staleDetail: "", upMs: null },
			conductor: { pid: null, alive: false, enabled: false, paused: false, everEnabled: false },
			autopilot: {
				enabled: true,
				everEnabled: true,
				tickSeq: null,
				tickAgeMs: null,
				tickStale: false,
				slotsUsed: 0,
				slotsMax: 2,
				stallTicks: 5,
				keys: [],
				stalls: [],
			},
			workers: [],
			gates: [{ id: "g1", kind: "s", stage: null, key: "", scopeResolved: false, reason: null }],
			blockedOnHuman: false,
		};
		const panel = renderMonitorLines(snap).join("\n");
		expect(panel).toContain(`scope=${GATE_SCOPE_UNRESOLVED}`);
		expect(panel).toContain("reason=-");
	});

	it("derives key-in-flight, cap-reached, stage-terminal and not-due from disk", () => {
		const root = mkdtemp();
		try {
			writeConfig(root);
			writeRoadmap(root, ROADMAP_TWO_STAGES);
			// k1 has a non-terminal row → key-in-flight (highest non-queue reason).
			writeWorkers(root, [{ key: "t1", status: "running", ownerKey: "k1" }]);
			writeGate(root, { id: "gate-0001", kind: "stalled", stage: 2, key: "k1" });
			// cap-reached: two remind rows for gate-0002, cap 2.
			writeGate(root, { id: "gate-0002", kind: "stalled", stage: 2, key: "k2" });
			writeLedger(root, [
				{ phase: "remind", seq: 1, gate_id: "gate-0002", gate_kind: "stalled", gate_key: "k2", reminder_n: 1 },
				{ phase: "remind", seq: 2, gate_id: "gate-0002", gate_kind: "stalled", gate_key: "k2", reminder_n: 2 },
			]);
			// stage-terminal: stage 1 is closed.
			writeGate(root, { id: "gate-0003", kind: "stalled", stage: 1, key: "k0" });
			// not-due: created 2 minutes ago, next threshold 30m.
			writeGate(root, {
				id: "gate-0004",
				kind: "stalled",
				stage: 2,
				key: "k2",
				createdAt: "2026-10-13T11:58:00+00:00",
			});
			const snap = readMonitorState(root, NOW_MS);
			const byId = new Map(snap.gates.map((g) => [g.id, g]));
			expect(byId.get("gate-0001")?.reason).toBe("key-in-flight");
			expect(byId.get("gate-0002")?.reason).toBe("cap-reached");
			expect(byId.get("gate-0002")?.reminders).toBe(2);
			expect(byId.get("gate-0003")?.reason).toBe("stage-terminal");
			expect(byId.get("gate-0004")?.reason).toBe("not-due");
			const panel = renderMonitorLines(snap).join("\n");
			expect(panel).toContain("R:flight");
			expect(panel).toContain("cap-reached");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── AC-001/AC-004: corrected drop order ─────────────────────────────────────

describe("AC-001 corrected drop order: reason and age survive width pressure", () => {
	it("keeps reason= and age= while DRIFT/code/scope/reminders yield, never exceeding 110", () => {
		const snap: MonitorSnapshot = {
			serve: { running: false, pid: null, stale: false, staleDetail: "", upMs: null },
			conductor: { pid: null, alive: false, enabled: false, paused: false, everEnabled: false },
			autopilot: {
				enabled: true,
				everEnabled: true,
				tickSeq: null,
				tickAgeMs: null,
				tickStale: false,
				slotsUsed: 0,
				slotsMax: 2,
				stallTicks: 5,
				keys: [],
				stalls: [],
			},
			workers: [],
			gates: [
				{
					id: "gate-0001",
					kind: "stalled",
					stage: null,
					key: "k1",
					ageMs: 12 * 3_600_000,
					reasonCode: "rc",
					drift: "mtime>created_at",
					reason: "not-due",
					scopeResolved: true,
					reminders: 2,
					reminderMax: 2,
				},
			],
			blockedOnHuman: false,
		};
		const line = renderMonitorLines(snap).find((l) => l.startsWith("gates:")) ?? "";
		expect(line.length).toBeLessThanOrEqual(LINE_MAX);
		// reason and age are the LAST tokens to drop ⇒ they survive here.
		expect(line).toContain("R:notdue");
		expect(line).toContain("age=12h");
		// The lower-priority facts yield: DRIFT first, then reason_code, scope,
		// reminders. The recovery entry is never dropped.
		expect(line).not.toContain("DRIFT(");
		expect(line).not.toContain("code=");
		expect(line).not.toContain(" key=k1");
		expect(line).not.toContain("reminders=");
		expect(line).toContain("-> /autopilot gate gate-0001 approve|reject");
	});
});

// ── AC-003/AC-005: the queue is never silently empty ────────────────────────

describe("AC-003/AC-005 gate queue readability", () => {
	it("reports gate-queue-unreadable when the gates directory cannot be scanned", () => {
		const root = mkdtemp();
		try {
			writeConfig(root);
			// A FILE where the gates directory should be: readdirSync throws
			// ENOTDIR, a non-ENOENT failure the old code folded into "0 pending".
			fs.mkdirSync(ap(root), { recursive: true });
			fs.writeFileSync(gatesDir(root), "not a directory", "utf8");
			const snap = readMonitorState(root, NOW_MS);
			expect(snap.queueState).toBe("unreadable");
			const panel = renderMonitorLines(snap).join("\n");
			expect(panel).toContain("gate-queue-unreadable");
			expect(panel).not.toContain("gates: 0 pending");
			// The value is also producible by the pure derivation.
			expect(
				deriveGateReason({
					queueUnreadable: true,
					inFlightForKey: 0,
					reminders: 0,
					reminderMax: 2,
					stageTerminal: false,
					due: true,
				}),
			).toBe("gate-queue-unreadable");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("keeps the absent-directory case a legitimate empty queue", () => {
		const root = mkdtemp();
		try {
			writeConfig(root);
			const snap = readMonitorState(root, NOW_MS);
			expect(snap.queueState).toBe("ok");
			expect(renderMonitorLines(snap).join("\n")).toContain("gates: 0 pending");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("renders the partial marker for an unreadable individual gate file", () => {
		const snap: MonitorSnapshot = {
			serve: { running: false, pid: null, stale: false, staleDetail: "", upMs: null },
			conductor: { pid: null, alive: false, enabled: false, paused: false, everEnabled: false },
			autopilot: {
				enabled: true,
				everEnabled: true,
				tickSeq: null,
				tickAgeMs: null,
				tickStale: false,
				slotsUsed: 0,
				slotsMax: 2,
				stallTicks: 5,
				keys: [],
				stalls: [],
			},
			workers: [],
			gates: [{ id: "gate-0001", kind: "stalled", stage: 1, key: "k1" }],
			queueState: "partial",
			queueError: "gate-0002.md: EACCES",
			blockedOnHuman: false,
		};
		const panel = renderMonitorLines(snap).join("\n");
		expect(panel).toContain("gate-queue-unreadable");
		expect(panel).toContain("gate-0002.md");
	});
});

// ── AC-016: stage main-gate rows ────────────────────────────────────────────

describe("AC-016 stage main-gate rows", () => {
	it("shows every stage status, the blocking gate, its age and the frozen keys", () => {
		const root = mkdtemp();
		try {
			writeConfig(root);
			writeRoadmap(
				root,
				[
					"# Roadmap",
					"> generated_at: 2026-10-13T00:00:00+00:00",
					"> goal_mtime: 1",
					"",
					"## Stage 1: Foundation",
					"> goal: ground",
					"> status: closed",
					"> key-status: k0=done",
					"### Keys",
					"| key | role | depends_on |",
					"|-----|------|-----------|",
					"| k0 | ground | - |",
					"",
					"## Stage 2: Build",
					"> goal: build",
					"> status: pending",
					"> key-status: k1=running",
					"### Keys",
					"| key | role | depends_on |",
					"|-----|------|-----------|",
					"| k1 | impl | k0 |",
					"",
					"## Stage 3: Harden",
					"> goal: harden",
					"> status: running",
					"> key-status: k2=stalled",
					"### Keys",
					"| key | role | depends_on |",
					"|-----|------|-----------|",
					"| k2 | review | k1 |",
					"",
				].join("\n"),
			);
			// Stage 2 is blocked on its confirm gate; stage 3 has a stalled key.
			writeGate(root, { id: "gate-0001", kind: "stage-confirm", stage: 2 });
			writeGate(root, { id: "gate-0002", kind: "stalled", stage: 3, key: "k2" });

			const snap = readMonitorState(root, NOW_MS);
			const stages = snap.autopilot.stages ?? [];
			expect(stages.map((s) => s.number)).toEqual([1, 2, 3]);
			expect(stages.find((s) => s.number === 1)?.status).toBe("closed");
			const stage2 = stages.find((s) => s.number === 2);
			expect(stage2?.status).toBe("pending");
			expect(stage2?.blockerKind).toBe("stage-confirm");
			expect(stage2?.blockerGateId).toBe("gate-0001");
			expect(stage2?.blockerAgeMs).toBe(3_600_000);
			const stage3 = stages.find((s) => s.number === 3);
			expect(stage3?.blockerKind).toBe("stalled");
			expect(stage3?.frozenKeys).toEqual(["k2"]);

			const panel = renderMonitorLines(snap).join("\n");
			expect(panel).toContain("stages: 3");
			expect(panel).toContain("stage 2 pending | waiting on stage-confirm gate-0001 | age=1h 0m");
			expect(panel).toContain("stage 3 running | waiting on stalled gate-0002");
			expect(panel).toContain("frozen k2");
			for (const line of renderMonitorLines(snap)) expect(line.length).toBeLessThanOrEqual(LINE_MAX);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("names halted as its own blocker (no gate can release it)", () => {
		const root = mkdtemp();
		try {
			writeConfig(root);
			writeRoadmap(
				root,
				[
					"# Roadmap",
					"> generated_at: 2026-10-13T00:00:00+00:00",
					"> goal_mtime: 1",
					"",
					"## Stage 1: Foundation",
					"> goal: ground",
					"> status: halted",
					"> key-status: k0=running",
					"### Keys",
					"| key | role | depends_on |",
					"|-----|------|-----------|",
					"| k0 | ground | - |",
					"",
				].join("\n"),
			);
			const snap = readMonitorState(root, NOW_MS);
			expect(snap.autopilot.stages?.[0]?.blockerKind).toBe("halted");
			expect(renderMonitorLines(snap).join("\n")).toContain("stage 1 halted | waiting on halted");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── AC-010: no-watch drops leave a visible record ───────────────────────────

describe("AC-010 dropped reminders leave a visible record", () => {
	afterEach(() => {
		vi.useRealTimers();
	});

	it("records a no-watch drop in the session instead of discarding it silently", () => {
		vi.useFakeTimers();
		const root = mkdtemp();
		const entries: Array<{ customType: string; data: unknown }> = [];
		const pi = {
			appendEntry: (customType: string, data: unknown) => {
				entries.push({ customType, data });
			},
		} as unknown as ExtensionAPI;
		try {
			writeLedger(root, [
				{
					phase: "remind",
					seq: 1,
					gate_id: "gate-0001",
					gate_kind: "stalled",
					gate_key: "k1",
					reminder_n: 1,
					detail: "pending 31m >= 30m",
				},
			]);
			const agenticdocRoot = path.join(root, ".agenticdoc");
			const store = new WorkerStore(agenticdocRoot);
			const watch: PmWatchState = { key: undefined };
			const ui: PmUiHolder = { ctx: undefined };
			const timer = startWorkerPollLoop(
				pi,
				store,
				new AckStore(agenticdocRoot),
				new IndexStore(agenticdocRoot),
				agenticdocRoot,
				watch,
				ui,
				1000,
			);
			try {
				vi.advanceTimersByTime(1000);
				// A second tick must not spam a duplicate record.
				vi.advanceTimersByTime(1000);
			} finally {
				clearInterval(timer);
			}
			const drops = entries.filter((e) => e.customType === GATE_REMINDER_DROPPED_ENTRY_TYPE);
			expect(drops).toHaveLength(1);
			expect(drops[0]?.data).toEqual({
				gateId: "gate-0001",
				n: 1,
				gateKey: "k1",
				reason: "no-watch",
			});
			// The drop record carries no `seq`, so it can never advance the
			// delivery watermark and suppress a later real delivery.
			expect(drops[0]?.data).not.toHaveProperty("seq");
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── T-10/D2: per-key blockedOnHuman derivation ──────────────────────────────

describe("T-10/D2 blockedOnHuman per-key derivation", () => {
	it("keeps the legacy project-level axis when no per-key input is passed", () => {
		expect(blockedOnHuman(0, 0)).toBe(false);
		expect(blockedOnHuman(1, 0)).toBe(true);
		expect(blockedOnHuman(1, 3)).toBe(false);
	});

	it("is human-blocked only when the gate's own key has no in-flight row", () => {
		const inFlight = new Map([["k1", 1]]);
		expect(blockedOnHuman(1, 5, { gateKeys: ["k1"], nonTerminalByKey: inFlight })).toBe(false);
		expect(blockedOnHuman(1, 5, { gateKeys: ["k1"], nonTerminalByKey: new Map() })).toBe(true);
		expect(blockedOnHuman(2, 5, { gateKeys: ["k1", "k2"], nonTerminalByKey: inFlight })).toBe(true);
		expect(blockedOnHuman(1, 5, { gateKeys: [""], nonTerminalByKey: inFlight })).toBe(true); // unresolved fail-open
		expect(blockedOnHuman(1, 5, { gateKeys: [null], nonTerminalByKey: inFlight })).toBe(true);
		expect(blockedOnHuman(1, 0, { gateKeys: ["k1"], nonTerminalByKey: new Map() })).toBe(true);
	});
});

// ── cap axis: readGateReminders parity input ────────────────────────────────

describe("cap axis input readGateReminders", () => {
	it("reads phase:remind rows and counts them by gate (row count, not distinct n)", () => {
		const root = mkdtemp();
		try {
			writeLedger(root, [
				{ phase: "decide", seq: 1, gate_id: "gate-0001" },
				{ phase: "remind", seq: 2, gate_id: "gate-0001", gate_kind: "stalled", gate_key: "k1", reminder_n: 1 },
				{ phase: "remind", seq: 3, gate_id: "gate-0001", gate_kind: "stalled", gate_key: "k1", reminder_n: 1 },
			]);
			const rows = readGateReminders(path.join(root, ".agenticdoc"));
			expect(rows).toHaveLength(2);
			expect(reminderCountForGate(rows, "gate-0001")).toBe(2);
			expect(reminderCountForGate(rows, "gate-9999")).toBe(0);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});
