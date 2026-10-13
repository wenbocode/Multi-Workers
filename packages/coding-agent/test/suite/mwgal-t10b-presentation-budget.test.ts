/**
 * T-10b presentation budget (mw-autopilot-gate-alarm-liveness AC-001 x AC-012):
 * the Layer A pending-gate line must fit 110 columns while NEVER losing the
 * evidence-drift mark, the suppression reason or the age.
 *
 * This file locks, as a machine-checkable contract:
 *   - the compact encoding table (`~D`, `R:queue`/`R:flight`/`R:cap`/
 *     `R:term`/`R:notdue`/`R:scope`/`R:due`, compact age `12m`/`3h`/`2d`),
 *   - the trailing `+N` omission trace for compressed-away secondary fields,
 *   - the deterministic fit ladder (first fit wins, no hidden ordering),
 *   - the constructive counterexample showing the full-form combination is
 *     infeasible at 110 columns, and
 *   - the worst-case sweep (every reason x kind x long key) staying bounded
 *     with the trio (drift/reason/age) intact.
 *
 * Pure unit fixtures over `renderPendingGateLine` + `renderMonitorLines`,
 * plus one file fixture through `readMonitorState`. No provider APIs, keys,
 * or network.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import {
	GATE_DRIFT_MARK,
	GATE_REASON_CODE,
	type MonitorGate,
	type MonitorSnapshot,
	readMonitorState,
	renderMonitorLines,
	renderPendingGateLine,
} from "../../src/extensions/agent-team-loop/autopilot/monitor.ts";
import {
	GATE_REASONS,
	type GateReason,
	gatesDir,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";

const LINE_MAX = 110;
const NOW_MS = Date.parse("2026-10-13T12:00:00+00:00");

function gate(overrides: Partial<MonitorGate> & { id: string; kind: string }): MonitorGate {
	return { stage: null, key: "", ...overrides };
}

function snapshotWith(gates: MonitorGate[]): MonitorSnapshot {
	return {
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
		gates,
		blockedOnHuman: false,
	};
}

/** The reason is visible either verbosely (`reason=`) or as its compact code. */
function reasonVisible(line: string, reason: GateReason | null | undefined): boolean {
	if (reason === null || reason === undefined) return line.includes("R:due") || line.includes("reason=-");
	return line.includes(`reason=${reason}`) || line.includes(GATE_REASON_CODE[reason] ?? "\u0000");
}

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "mwgal-t10b-"));
}

function apPath(root: string): string {
	return path.join(root, ".agenticdoc", "_autopilot");
}

function writeDriftFixture(root: string): void {
	fs.mkdirSync(apPath(root), { recursive: true });
	fs.writeFileSync(
		path.join(apPath(root), "config.json"),
		`${JSON.stringify({ enabled: true, paused: false, auto_gate_mode: "shadow" }, null, 2)}\n`,
		"utf8",
	);
	const evidence = path.join(root, ".agenticdoc", "_autopilot", "stages", "stage-1-close.md");
	fs.mkdirSync(path.dirname(evidence), { recursive: true });
	fs.writeFileSync(evidence, "## Keys\n", "utf8");
	const stamp = new Date(Date.parse("2026-10-14T00:00:00+00:00"));
	fs.utimesSync(evidence, stamp, stamp);
	const dir = gatesDir(root);
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(
		path.join(dir, "gate-0008.md"),
		[
			"---",
			"id: gate-0008",
			"kind: stage-close",
			"stage: 1",
			"key: ",
			"created_at: 2026-10-13T08:00:00+00:00",
			"created_by: conductor",
			"question: 'proceed?'",
			"context_refs:",
			"  - .agenticdoc/_autopilot/_roadmap.md",
			"reason_code: stage:all-keys-terminal",
			"evidence_refs:",
			"  - gate-dossier:_autopilot/stages/stage-1-close.md",
			"status: pending",
			"---",
			"",
			"# Gate gate-0008",
			"",
		].join("\n"),
		"utf8",
	);
}

// ── Encoding table ───────────────────────────────────────────────────────────

describe("T-10b compact encoding table", () => {
	it("maps every closed reason value to a unique documented code", () => {
		expect(Object.keys(GATE_REASON_CODE).sort()).toEqual([...GATE_REASONS].sort());
		const codes = Object.values(GATE_REASON_CODE);
		expect(new Set(codes).size).toBe(codes.length);
		expect(codes).toEqual(expect.arrayContaining(["R:queue", "R:flight", "R:cap", "R:term", "R:notdue", "R:scope"]));
		expect(GATE_DRIFT_MARK).toBe("~D");
	});

	it("compacts the age to 12m/3h/2d only when the verbose form does not fit", () => {
		// 12h at the first line: full `age=12h 0m` + verbose reason + full answer
		// does not fit, so the ladder compacts the age and keeps the reason verbose.
		const twelveHours = gate({
			id: "gate-0001",
			kind: "stalled",
			stage: 2,
			key: "k1",
			ageMs: 12 * 3_600_000,
			reason: "not-due",
		});
		const line = renderPendingGateLine(twelveHours, 0, 1);
		expect(line).toContain(" age=12h");
		expect(line).not.toContain("age=12h 0m");
		expect(line).toContain("reason=not-due");
		expect(line.length).toBeLessThanOrEqual(LINE_MAX);

		// 2 days compacts to `2d` (formatDuration would print `48h 0m`).
		const twoDays = gate({
			id: "gate-0001",
			kind: "stalled",
			stage: 2,
			key: "k1",
			ageMs: 2 * 86_400_000,
			reason: "not-due",
		});
		expect(renderPendingGateLine(twoDays, 0, 1)).toContain(" age=2d");

		// A minute-level age is identical in both encodings (no information loss).
		const twelveMinutes = gate({
			id: "gate-0001",
			kind: "stalled",
			stage: 2,
			key: "k1",
			ageMs: 12 * 60_000,
			reason: "not-due",
		});
		expect(renderPendingGateLine(twelveMinutes, 0, 1)).toContain(" age=12m");
	});
});

// ── Never-drop trio + deterministic ladder ───────────────────────────────────

describe("T-10b never-drop trio and omission trace", () => {
	it("keeps ~D, the reason and the age under maximal width pressure", () => {
		const worst = gate({
			id: "gate-9999",
			kind: "budget-exhausted",
			stage: 999,
			key: "feature-with-a-very-long-key-name-for-truncation",
			reasonCode: "advance:interface-drift-with-a-very-long-suffix",
			reminders: 2,
			reminderMax: 2,
			drift: "mtime>created_at",
			ageMs: 3 * 3_600_000 + 55 * 60_000,
			reason: "gate-queue-unreadable",
		});
		const line = renderPendingGateLine(worst, 0, 1);
		expect(line.length, line).toBeLessThanOrEqual(LINE_MAX);
		expect(line).toContain(GATE_DRIFT_MARK);
		expect(line).toContain("age=");
		expect(reasonVisible(line, "gate-queue-unreadable"), line).toBe(true);
		// code + scope + reminders are gone; the trace says how many.
		expect(line).not.toContain("code=");
		expect(line).not.toContain("reminders=");
		expect(line).toMatch(/ \+\d$/);
	});

	it("falls to the compact reason code when even the short answer + verbose reason cannot fit", () => {
		const crowded = gate({
			id: "gate-00000000000000",
			kind: "budget-exhausted",
			key: "k1",
			reasonCode: "c".repeat(30),
			reminders: 2,
			reminderMax: 2,
			drift: "mtime>created_at",
			ageMs: 5 * 86_400_000,
			reason: "gate-queue-unreadable",
		});
		const line = renderPendingGateLine(crowded, 0, 1);
		expect(line.length, line).toBeLessThanOrEqual(LINE_MAX);
		expect(line, line).toContain(GATE_DRIFT_MARK);
		expect(line, line).toContain("age=");
		expect(line, line).toContain("R:queue");
		expect(line, line).not.toContain("reason=gate-queue-unreadable");
		expect(line, line).toContain("-> /autopilot gates");
	});

	it("counts exactly the omitted secondary fields in the trailing +N", () => {
		// Only the `code=` secondary field exists and it does not fit.
		const codeOnly = gate({
			id: "gate-0001",
			kind: "stalled",
			ageMs: 12 * 3_600_000,
			reasonCode: "x".repeat(30),
			reason: "not-due",
		});
		const line = renderPendingGateLine(codeOnly, 0, 1);
		expect(line.length).toBeLessThanOrEqual(LINE_MAX);
		expect(line).not.toContain("code=");
		expect(line).toMatch(/ \+1$/);
		expect(line).toContain(" age=12h");
		expect(line).toContain("reason=not-due");

		// Nothing yields: no trace marker at all.
		const roomy = gate({ id: "gate-0001", kind: "stalled", stage: 1, ageMs: 60_000, reason: null });
		const roomyLine = renderPendingGateLine(roomy, 0, 1);
		expect(roomyLine).not.toMatch(/ \+\d/);
		expect(roomyLine).toContain("reason=-");
		expect(roomyLine).toContain("age=1m");
	});

	it("omits ~D when there is no drift and never invents one", () => {
		const clean = gate({ id: "gate-0001", kind: "stalled", stage: 1, ageMs: 60_000, reason: "not-due" });
		expect(renderPendingGateLine(clean, 0, 1)).not.toContain(GATE_DRIFT_MARK);
	});

	it("leaves the resolved-scope marker droppable but never the reason", () => {
		// On a narrow row (short id/kind) the marker fits and is shown.
		const unresolved = gate({ id: "g1", kind: "s", key: "", scopeResolved: false, reason: null });
		const narrow = renderMonitorLines(snapshotWith([unresolved])).join("\n");
		expect(narrow).toContain("scope=unresolved-scope");
		expect(narrow).toContain("reason=-");

		// Under pressure the marker is the field that yields (rank 2), and the
		// omission trace records it; the reason still survives.
		const pressured = gate({ id: "gate-0001", kind: "stalled", key: "", scopeResolved: false, reason: null });
		const line = renderPendingGateLine(pressured, 0, 1);
		expect(line.length).toBeLessThanOrEqual(LINE_MAX);
		expect(line).not.toContain("scope=unresolved-scope");
		expect(line).toMatch(/ \+1$/);
		expect(reasonVisible(line, null)).toBe(true);
	});
});

describe("T-10b deterministic fit ladder", () => {
	it("proves the full-form combination is infeasible and compresses instead of dropping", () => {
		const g = gate({
			id: "gate-0001",
			kind: "stalled",
			key: "k1",
			ageMs: 12 * 3_600_000,
			reasonCode: "rc",
			drift: "mtime>created_at",
			reason: "not-due",
			reminders: 2,
			reminderMax: 2,
		});
		// Constructive counterexample: even with the compact `~D` mark, the
		// full age + full reason + full recovery command + the `+3` trace is
		// 114 columns, so no layout can keep all of them verbatim.
		const fullVerbose =
			`gates: 1 pending - gate-0001 (stalled) ${GATE_DRIFT_MARK} age=12h 0m reason=not-due` +
			` -> /autopilot gate gate-0001 approve|reject +3`;
		expect(fullVerbose.length).toBeGreaterThan(LINE_MAX);

		const line = renderPendingGateLine(g, 0, 1);
		expect(line.length).toBeLessThanOrEqual(LINE_MAX);
		expect(line).toContain(GATE_DRIFT_MARK); // AC-012: drift semantics kept
		expect(line).toContain("age="); // AC-001: age kept
		expect(reasonVisible(line, "not-due")).toBe(true); // AC-001: reason kept
		expect(line).toContain("-> /autopilot gate gate-0001 approve|reject");
		expect(line).toMatch(/ \+\d$/);
		// Same input -> same output (no hidden ordering / randomness).
		expect(renderPendingGateLine(g, 0, 1)).toBe(line);
	});

	it("sweeps every reason x kind x long key: bounded and trio-intact", () => {
		const kinds = ["stage-confirm", "stage-close", "stalled", "budget-exhausted", "goal-change"];
		const reasons: Array<GateReason | null> = [...GATE_REASONS, null];
		for (const reason of reasons) {
			for (const kind of kinds) {
				const g = gate({
					id: "gate-0001",
					kind,
					stage: 12,
					key: "k".repeat(60),
					reasonCode: "c".repeat(40),
					reminders: 2,
					reminderMax: 2,
					drift: "mtime>created_at",
					ageMs: 5 * 86_400_000,
					reason,
				});
				const line = renderPendingGateLine(g, 0, 3);
				expect(line.length, line).toBeLessThanOrEqual(LINE_MAX);
				expect(line, line).toContain(GATE_DRIFT_MARK);
				expect(line, line).toContain("age=");
				expect(reasonVisible(line, reason), line).toBe(true);
				// A non-first row is shorter; it must still keep the trio.
				const indented = renderPendingGateLine(g, 1, 3);
				expect(indented.length).toBeLessThanOrEqual(LINE_MAX);
				expect(indented).toContain(GATE_DRIFT_MARK);
				expect(indented).toContain("age=");
				expect(reasonVisible(indented, reason)).toBe(true);
			}
		}
	});

	it("never truncates the trio away in the last-resort branch (absurd id)", () => {
		const absurd = gate({
			id: `gate-${"9".repeat(200)}`,
			kind: "stalled",
			ageMs: 90_000,
			reason: null,
			drift: "mtime>created_at",
		});
		const line = renderPendingGateLine(absurd, 0, 1);
		expect(line.length).toBeLessThanOrEqual(LINE_MAX);
		expect(line).toContain(GATE_DRIFT_MARK);
		expect(line).toContain("age=");
		expect(reasonVisible(line, null)).toBe(true);
	});
});

// ── File-fixture integration (AC-012 contract through the collector) ─────────

describe("T-10b monitor integration", () => {
	it("renders ~D + age + reason together on a drifting pending gate", () => {
		const root = mkdtemp();
		try {
			writeDriftFixture(root);
			const panel = renderMonitorLines(readMonitorState(root, NOW_MS));
			const gateLine = panel.find((l) => l.startsWith("gates:"));
			expect(gateLine).toBeDefined();
			expect(gateLine ?? "").toContain(GATE_DRIFT_MARK);
			expect(gateLine ?? "").toContain("age=");
			expect(gateLine ?? "").toMatch(/reason=| R:/);
			for (const line of panel) expect(line.length, line).toBeLessThanOrEqual(LINE_MAX);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});
