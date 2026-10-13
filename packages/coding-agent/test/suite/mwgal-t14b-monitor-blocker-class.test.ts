/**
 * T-14b — `blocker_class` on the monitor panel (mw-autopilot-gate-alarm-liveness
 * AC-007 x AC-012 x AC-001).
 *
 * T-14 registered the closed-set scalar `blocker_class ∈ {paperwork, judgment}`
 * across the Python and TS read surfaces but left `monitor.ts` outside its write
 * surface, so the field reached the state model yet not the panel (the DRQ-1
 * "silently disappears" gap, monitor half). This suite locks the closed loop:
 *
 *   1. PARSE      — the loose pending-gate line scan reads `blocker_class`
 *                   verbatim (blank folds to null), exactly like `reason_code`.
 *   2. FOLD       — the panel mark is produced through `blockerClassOf`, the
 *                   SAME fold `status-model.ts` uses: only an explicit
 *                   `paperwork` is `P`; absent/blank/out-of-set is `J`
 *                   (fail-closed: an unclassified v1 gate is never auto-releasable).
 *   3. LADDER     — the mark rides the T-10b fit ladder as a secondary field in
 *                   the same tier as `code=`/`scope=`/`stage=`/`key=`/
 *                   `reminders=`, and every omission (this one included) is
 *                   counted into the trailing `+N`.
 *   4. CONTRACTS  — DRIFT/reason/age survive and every line stays <= 110 columns.
 *
 * Pure file fixtures + pure render calls. No provider APIs, keys, or network.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import {
	GATE_BLOCKER_MARK,
	GATE_DRIFT_MARK,
	type MonitorGate,
	readMonitorState,
	renderMonitorLines,
	renderPendingGateLine,
} from "../../src/extensions/agent-team-loop/autopilot/monitor.ts";
import {
	blockerClassOf,
	deriveStatusModel,
	gatesDir,
} from "../../src/extensions/agent-team-loop/autopilot/status-model.ts";

const NOW_MS = Date.parse("2026-10-13T12:00:00+00:00");
const LINE_MAX = 110;

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "mwgal-t14b-"));
}

interface GateSpec {
	id: string;
	kind: string;
	stage?: number | null;
	key?: string;
	status?: string;
	createdAt?: string;
	reasonCode?: string;
	/** Value written as `blocker_class: <value>`; `null` writes a blank line. */
	blockerClass?: string | null;
	evidenceRefs?: string[];
}

/** One gate file in the Python renderer's shape (line-scan compatible). */
function writeGate(root: string, spec: GateSpec): string {
	const dir = gatesDir(root);
	fs.mkdirSync(dir, { recursive: true });
	const lines = [
		"---",
		`id: ${spec.id}`,
		`kind: ${spec.kind}`,
		`stage: ${spec.stage === null || spec.stage === undefined ? "" : spec.stage}`,
		`key: ${spec.key ?? ""}`,
		`created_at: ${spec.createdAt ?? "2026-10-13T11:00:00+00:00"}`,
		"created_by: conductor",
		"question: 'proceed?'",
		"context_refs:",
		"  - .agenticdoc/_autopilot/_roadmap.md",
	];
	if (spec.reasonCode !== undefined) lines.push(`reason_code: ${spec.reasonCode}`);
	if (spec.evidenceRefs !== undefined) {
		lines.push("evidence_refs:");
		for (const ref of spec.evidenceRefs) lines.push(`  - ${ref}`);
	}
	if (spec.blockerClass !== undefined) {
		// `null` = the field exists but is blank (the explicit "unclassified" shape).
		lines.push(`blocker_class:${spec.blockerClass === null ? "" : ` ${spec.blockerClass}`}`);
	}
	lines.push(`status: ${spec.status ?? "pending"}`, "---", "", `# Gate ${spec.id}`, "");
	const file = path.join(dir, `${spec.id}.md`);
	fs.writeFileSync(file, `${lines.join("\n")}\n`, "utf8");
	return file;
}

function writeConfig(root: string): void {
	const dir = path.join(root, ".agenticdoc", "_autopilot");
	fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(
		path.join(dir, "config.json"),
		`${JSON.stringify({ enabled: true, paused: false, auto_gate_mode: "shadow" }, null, 2)}\n`,
		"utf8",
	);
}

/** One hand-built gate for the pure renderer (stage/key default as T-10 does). */
function gate(overrides: Partial<MonitorGate> & { id: string; kind: string }): MonitorGate {
	return { stage: null, key: "", ...overrides };
}

/** The panel row for `id` (first line starts with the count header). */
function rowFor(root: string, id: string): string {
	const row = renderMonitorLines(readMonitorState(root, NOW_MS)).find((line) => line.includes(id));
	expect(row, `no panel row for ${id}`).toBeDefined();
	return row ?? "";
}

// ── 1. Parse: both closed-set values land on MonitorGate ─────────────────────

describe("T-14b parse: blocker_class reaches MonitorGate", () => {
	it("reads both closed-set values verbatim", () => {
		const root = mkdtemp();
		try {
			writeGate(root, { id: "gate-0001", kind: "stalled", stage: 2, key: "k1", blockerClass: "paperwork" });
			writeGate(root, { id: "gate-0002", kind: "stalled", stage: 2, key: "k1", blockerClass: "judgment" });
			writeGate(root, { id: "gate-0003", kind: "stalled", stage: 2, key: "k1" });
			writeGate(root, { id: "gate-0004", kind: "stalled", stage: 2, key: "k1", blockerClass: null });
			const byId = new Map(readMonitorState(root, NOW_MS).gates.map((g) => [g.id, g]));
			expect(byId.get("gate-0001")?.blockerClass).toBe("paperwork");
			expect(byId.get("gate-0002")?.blockerClass).toBe("judgment");
			// The parser never folds (same split as status-model.ts). Like
			// `reason_code`, an absent field and an explicit blank both land as null:
			// the loose scan carries no field-presence bit, and the fold is applied at
			// render/derivation time (`blockerClassOf`) on both surfaces.
			expect(byId.get("gate-0003")?.blockerClass).toBeNull();
			expect(byId.get("gate-0004")?.blockerClass).toBeNull();
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

// ── 2. Fold: absent == judgment, and it equals the status-model direction ───

describe("T-14b fold: absent folds to judgment on BOTH surfaces", () => {
	it("renders the same mark for absent/blank as for explicit judgment (status-model cross-check)", () => {
		const root = mkdtemp();
		try {
			writeConfig(root);
			writeGate(root, { id: "gate-0001", kind: "stalled", stage: 2, key: "k1", blockerClass: "paperwork" });
			writeGate(root, { id: "gate-0002", kind: "stalled", stage: 2, key: "k1", blockerClass: "judgment" });
			writeGate(root, { id: "gate-0003", kind: "stalled", stage: 2, key: "k1" }); // v1 legacy
			writeGate(root, { id: "gate-0004", kind: "stalled", stage: 2, key: "k1", blockerClass: null });

			// Panel side (monitor.ts renders through blockerClassOf).
			expect(rowFor(root, "gate-0001")).toContain(` ${GATE_BLOCKER_MARK.paperwork} `);
			expect(rowFor(root, "gate-0002")).toContain(` ${GATE_BLOCKER_MARK.judgment} `);
			expect(rowFor(root, "gate-0003")).toContain(` ${GATE_BLOCKER_MARK.judgment} `);
			expect(rowFor(root, "gate-0004")).toContain(` ${GATE_BLOCKER_MARK.judgment} `);

			// Judgment side (status-model.ts derivation layer) — the two must agree
			// on every gate id, and neither may call an unclassified gate healthy.
			const model = deriveStatusModel(root, NOW_MS);
			expect(model.ok).toBe(true);
			if (!model.ok) return;
			const folded = model.model.gateBlockerClasses ?? {};
			expect(folded["gate-0001"]).toBe("paperwork");
			expect(folded["gate-0002"]).toBe("judgment");
			expect(folded["gate-0003"]).toBe("judgment");
			expect(folded["gate-0004"]).toBe("judgment");
			for (const id of ["gate-0001", "gate-0002", "gate-0003", "gate-0004"]) {
				// Two-sided comparison: the panel mark is the mark of the folded class.
				const mark = ` ${GATE_BLOCKER_MARK[blockerClassOf({ blockerClass: null })]}`;
				const expected = folded[id] === "paperwork" ? ` ${GATE_BLOCKER_MARK.paperwork}` : mark;
				expect(rowFor(root, id), id).toContain(expected);
			}
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("never folds an unknown out-of-set value to paperwork (fail-closed)", () => {
		// The strict parser rejects out-of-set values, but the loose monitor scan
		// can still see them; the fold must send them to judgment.
		expect(blockerClassOf({ blockerClass: "bogus" })).toBe("judgment");
		const line = renderPendingGateLine(gate({ id: "gate-0001", kind: "stalled", blockerClass: "bogus" }), 0, 1);
		expect(line).toContain(` ${GATE_BLOCKER_MARK.judgment} `);
		expect(line).not.toContain(` ${GATE_BLOCKER_MARK.paperwork} `);
	});
});

// ── 3. Ladder: visible when it fits, counted into +N when it does not ────────

describe("T-14b fit ladder: blocker mark is a countable secondary", () => {
	it("shows P/J while keeping the trio, and counts the mark into +N when omitted", () => {
		// Short base: the mark fits, the (oversized) code= is the one that yields.
		const shortBase = gate({
			id: "gate-0001",
			kind: "stalled",
			ageMs: 12 * 3_600_000,
			reasonCode: "x".repeat(30),
			reason: "not-due",
			blockerClass: "paperwork",
		});
		const shortLine = renderPendingGateLine(shortBase, 0, 1);
		expect(shortLine.length).toBeLessThanOrEqual(LINE_MAX);
		expect(shortLine).toContain(` ${GATE_BLOCKER_MARK.paperwork} `);
		expect(shortLine).not.toContain("code=");
		expect(shortLine).toMatch(/ \+1$/); // exactly the code= yielded
		expect(shortLine).toContain(" age=12h");
		expect(shortLine).toContain("reason=not-due");

		// One column more base: now code= + the mark + the trio cannot coexist,
		// so the mark is compressed away too and the +N counts it.
		const longBase = gate({
			id: "gate-00011",
			kind: "stalled",
			ageMs: 12 * 3_600_000,
			reasonCode: "x".repeat(30),
			reason: "not-due",
			blockerClass: "paperwork",
		});
		const longLine = renderPendingGateLine(longBase, 0, 1);
		expect(longLine.length).toBeLessThanOrEqual(LINE_MAX);
		expect(longLine).not.toContain(` ${GATE_BLOCKER_MARK.paperwork} `);
		expect(longLine).not.toContain(` ${GATE_BLOCKER_MARK.judgment} `);
		expect(longLine).not.toContain("code=");
		expect(longLine).toMatch(/ \+2$/); // code= AND the blocker mark
		expect(longLine).toContain(" age=12h");
		expect(longLine).toContain("reason=not-due");
	});

	it("under maximal pressure keeps DRIFT/reason/age and counts the mark in +N", () => {
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
			blockerClass: "paperwork",
		});
		const line = renderPendingGateLine(worst, 0, 1);
		expect(line.length, line).toBeLessThanOrEqual(LINE_MAX);
		// Required trio survives (encoding may compact, never drop).
		expect(line).toContain(GATE_DRIFT_MARK);
		expect(line).toContain("age=");
		expect(line).toMatch(/reason=gate-queue-unreadable|R:queue/);
		expect(line).toContain("-> /autopilot gates");
		// The mark is omitted here; the trace counts all four secondaries
		// (blocker mark + code= + stage= + reminders=).
		expect(line).not.toContain(` ${GATE_BLOCKER_MARK.paperwork} `);
		expect(line).toMatch(/ \+4$/);
		// Deterministic: same input, same line.
		expect(renderPendingGateLine(worst, 0, 1)).toBe(line);
	});
});

// ── 4. Existing contracts stay green on the same surface ─────────────────────

describe("T-14b existing contracts: 110 columns and DRIFT intact", () => {
	it("keeps every panel line <= 110 and preserves ~D on a drifting gate", () => {
		const root = mkdtemp();
		try {
			writeConfig(root);
			const evidence = path.join(root, ".agenticdoc", "_autopilot", "stages", "stage-1-close.md");
			fs.mkdirSync(path.dirname(evidence), { recursive: true });
			fs.writeFileSync(evidence, "## Keys\n", "utf8");
			const stamp = new Date(Date.parse("2026-10-14T00:00:00+00:00"));
			fs.utimesSync(evidence, stamp, stamp);
			writeGate(root, {
				id: "gate-0008",
				kind: "stage-close",
				stage: 1,
				reasonCode: "stage:all-keys-terminal",
				evidenceRefs: ["gate-dossier:_autopilot/stages/stage-1-close.md"],
				blockerClass: "paperwork",
			});
			const panel = renderMonitorLines(readMonitorState(root, NOW_MS));
			const gateLine = panel.find((line) => line.startsWith("gates:"));
			expect(gateLine).toBeDefined();
			expect(gateLine ?? "").toContain(GATE_DRIFT_MARK);
			expect(gateLine ?? "").toContain("age=");
			expect(gateLine ?? "").toMatch(/reason=| R:/);
			expect(gateLine ?? "").toContain(` ${GATE_BLOCKER_MARK.paperwork} `);
			for (const line of panel) expect(line.length, line).toBeLessThanOrEqual(LINE_MAX);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});
