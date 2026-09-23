/**
 * Gate-layer tests for the phase-tiered dispatch docs gate
 * (mw-worker-visibility-gate T-1; AC/VC-001..005 + VC-012).
 *
 * Every fixture lives under os.tmpdir() — the repo is never polluted. The
 * docs gate is a pure read-only function, so each scenario is built by
 * writing key files into a temp .agenticdoc root and calling
 * dispatchDocGaps / phaseDocGaps / gateTierOf directly. The tool-entrance
 * forms of these ACs (task.md written, refusal text, workers/ dir) belong to
 * T-3's tests; here the gate layer must prove the phase axis alone.
 *
 * [VERIFY] lines are emitted via process.stdout.write because vitest's
 * silent: "passed-only" swallows console.log for passing tests — the PM
 * greps these lines from the raw run log (P-006).
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { describe, expect, it } from "vitest";
import {
	dispatchDocGaps,
	gateTierOf,
	MIN_PHASE_DOC_BYTES,
	phaseDocGaps,
	readPhaseDocs,
} from "../../src/extensions/agent-team-loop/shared/phase-docs.ts";

function mkdtemp(): string {
	return fs.mkdtempSync(path.join(os.tmpdir(), "mwvg-t1-"));
}

/** Established project goal (no status line + real Goal content → established
 * via the legacy rule), so the spec-side §0 check is actually enforced. */
function writeEstablishedGoal(root: string): void {
	fs.writeFileSync(
		path.join(root, "goal.md"),
		"# Project Goal\n\n## Goal\nBuild the agent team framework\n\n## Context\n\n## Key Constraints\n",
		"utf8",
	);
}

/** Complete spec-side chain: spec.md >= 500 bytes with a §0 Goal Alignment
 * section naming 预期收益, a numbered AC, and one spec research note. */
function writeSpecSide(root: string, key: string): void {
	const keyDir = path.join(root, key);
	fs.mkdirSync(keyDir, { recursive: true });
	fs.writeFileSync(
		path.join(keyDir, "spec.md"),
		`# Spec\n${"x".repeat(600)}\n\n## §0 Goal Alignment\n- 预期收益: research workers run under their owner key at SPEC phase\n\n| AC-001 | in x, y returns z |\n`,
		"utf8",
	);
	const research = path.join(keyDir, "evidence", "research");
	fs.mkdirSync(research, { recursive: true });
	fs.writeFileSync(path.join(research, "spec-topic-2026-01-01.md"), "# research\n", "utf8");
}

/** Write design.md with exactly `bytes` bytes; returns its path. */
function writeDesignDoc(root: string, key: string, bytes: number): string {
	const keyDir = path.join(root, key);
	fs.mkdirSync(keyDir, { recursive: true });
	const designPath = path.join(keyDir, "design.md");
	fs.writeFileSync(designPath, "x".repeat(bytes), "utf8");
	return designPath;
}

/** One design-side research note. */
function writeDesignNote(root: string, key: string): void {
	const research = path.join(root, key, "evidence", "research");
	fs.mkdirSync(research, { recursive: true });
	fs.writeFileSync(path.join(research, "design-topic-2026-01-01.md"), "# research\n", "utf8");
}

/** How many gaps name the design side (design.md / design-* evidence). */
function designGapCount(gaps: string[]): number {
	return gaps.filter((g) => g.includes("design")).length;
}

describe("gateTierOf normalization", () => {
	it("maps every phase spelling to a tier (full value table)", () => {
		const specPhases = [
			"SPEC",
			"spec",
			"Spec",
			"init",
			"INIT",
			"Init",
			"—",
			"-",
			"",
			"   ",
			"weird-phase",
			"SPEC ",
			" init ",
			"design-draft",
		];
		for (const p of specPhases) {
			expect(gateTierOf(p)).toBe("spec");
		}
		const designPhases = [
			"DESIGN",
			"design",
			"PLAN",
			"Plan",
			"TASKS",
			"tasks",
			"EXECUTE",
			"execute",
			"VERIFY",
			"verify",
			"DONE",
			"done",
			" DONE ",
		];
		for (const p of designPhases) {
			expect(gateTierOf(p)).toBe("design");
		}
		process.stdout.write(
			`[VERIFY] gateTierOf: SPEC→${gateTierOf("SPEC")} init→${gateTierOf("init")} —→${gateTierOf("—")} ""→${gateTierOf("")} unknown→${gateTierOf("weird-phase")} DESIGN→${gateTierOf("DESIGN")} PLAN→${gateTierOf("PLAN")} TASKS→${gateTierOf("TASKS")} EXECUTE→${gateTierOf("EXECUTE")} VERIFY→${gateTierOf("VERIFY")} DONE→${gateTierOf("DONE")}\n`,
		);
	});
});

describe("phaseDocGaps tiers", () => {
	it("design tier keeps the exact pre-tiering six-gap order; omitted tier stays legacy", () => {
		const root = mkdtemp();
		try {
			writeEstablishedGoal(root);
			fs.mkdirSync(path.join(root, "order-key"), { recursive: true });
			const expected = [
				"spec.md missing or under 500 bytes",
				"evidence/research/spec-*.md missing (>= 1 research note; a zero-research declaration counts)",
				"spec.md missing a non-empty §0 Goal Alignment section with 预期收益 (goal.md is established)",
				"spec.md has no numbered acceptance criteria (AC-NNN)",
				"design.md missing or under 500 bytes",
				"evidence/research/design-*.md missing (>= 1 research note; a zero-research declaration counts)",
			];
			const status = readPhaseDocs(root, "order-key");
			expect(phaseDocGaps(status, "design")).toEqual(expected);
			// Legacy one-argument callers must behave exactly as before the tiering.
			expect(phaseDocGaps(status)).toEqual(expected);
			// Spec tier = the same four spec-side items, same order, nothing else.
			expect(phaseDocGaps(status, "spec")).toEqual(expected.slice(0, 4));
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});

describe("dispatchDocGaps phase tiering", () => {
	it("VC-001: SPEC phase passes on the spec side alone while design.md is missing", () => {
		const root = mkdtemp();
		try {
			writeEstablishedGoal(root);
			writeSpecSide(root, "vc1-key");
			// design.md and design-* evidence deliberately absent.
			const status = readPhaseDocs(root, "vc1-key");
			expect(status.spec).toBe(true);
			expect(status.specS0).toBe(true);
			expect(status.specAC).toBe(true);
			expect(status.specEvidence).toBe(1);
			expect(status.design).toBe(false);

			const gaps = dispatchDocGaps(root, "vc1-key", "SPEC");
			expect(gaps).toEqual([]);
			const pass = gaps.length === 0;
			process.stdout.write(`[VERIFY] VC-001: spec_phase_pass=${pass} gate_blocked=${gaps.length > 0}\n`);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-002: DESIGN phase with design.md missing reports exactly one design gap", () => {
		const root = mkdtemp();
		try {
			writeEstablishedGoal(root);
			writeSpecSide(root, "vc2-key");
			// design-* evidence present so the design.md gap is the ONLY one left.
			writeDesignNote(root, "vc2-key");
			const gaps = dispatchDocGaps(root, "vc2-key", "DESIGN");
			expect(gaps).toHaveLength(1);
			expect(gaps[0]).toBe("design.md missing or under 500 bytes");
			// Pure gate: it must not create any workers/ task directory.
			const taskDirCreated = fs.existsSync(path.join(root, "vc2-key", "workers"));
			expect(taskDirCreated).toBe(false);
			process.stdout.write(
				`[VERIFY] VC-002: blocked=${gaps.length > 0} design_gap=${gaps.length} task_dir=${taskDirCreated}\n`,
			);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-003: DESIGN phase with design.md present but zero design evidence reports one evidence gap", () => {
		const root = mkdtemp();
		try {
			writeEstablishedGoal(root);
			writeSpecSide(root, "vc3-key");
			writeDesignDoc(root, "vc3-key", 600);
			// No design-* research note exists.
			const gaps = dispatchDocGaps(root, "vc3-key", "DESIGN");
			expect(gaps).toHaveLength(1);
			expect(gaps[0]).toBe(
				"evidence/research/design-*.md missing (>= 1 research note; a zero-research declaration counts)",
			);
			process.stdout.write(`[VERIFY] VC-003: blocked=${gaps.length > 0} design_evidence_gap=${gaps.length}\n`);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-004: placeholder and unknown phases are judged exactly like SPEC", () => {
		const root = mkdtemp();
		try {
			writeEstablishedGoal(root);
			writeSpecSide(root, "vc4-key");
			const specGaps = dispatchDocGaps(root, "vc4-key", "SPEC");
			expect(specGaps).toEqual([]);

			const variants = ["—", "", "init", "weird-phase"];
			const tiers = variants.map((p) => gateTierOf(p));
			expect(tiers.every((t) => t === "spec")).toBe(true);
			let designGaps = 0;
			for (const p of variants) {
				const gaps = dispatchDocGaps(root, "vc4-key", p);
				expect(gaps).toEqual(specGaps);
				designGaps += designGapCount(gaps);
			}
			expect(designGaps).toBe(0);
			// Negative control: the very same fixture IS held to the design tier.
			expect(dispatchDocGaps(root, "vc4-key", "DESIGN")).toHaveLength(2);
			process.stdout.write(
				`[VERIFY] VC-004: tier=${tiers[0]} design_gaps=${designGaps} variants=${variants.length}\n`,
			);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-005: SPEC phase with an under-sized spec.md reports only the spec-side gaps", () => {
		const root = mkdtemp();
		try {
			writeEstablishedGoal(root);
			const keyDir = path.join(root, "vc5-key");
			fs.mkdirSync(keyDir, { recursive: true });
			// 499 bytes: no size, no §0, no AC; no spec evidence; no design side at all.
			fs.writeFileSync(path.join(keyDir, "spec.md"), "x".repeat(MIN_PHASE_DOC_BYTES - 1), "utf8");
			const gaps = dispatchDocGaps(root, "vc5-key", "SPEC");
			expect(gaps).toEqual([
				"spec.md missing or under 500 bytes",
				"evidence/research/spec-*.md missing (>= 1 research note; a zero-research declaration counts)",
				"spec.md missing a non-empty §0 Goal Alignment section with 预期收益 (goal.md is established)",
				"spec.md has no numbered acceptance criteria (AC-NNN)",
			]);
			expect(designGapCount(gaps)).toBe(0);
			process.stdout.write(`[VERIFY] VC-005: spec_gaps=${gaps.length} design_gaps=${designGapCount(gaps)}\n`);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("VC-012: the phase gate never rejects by task type at SPEC (regression; tool entrance is T-3)", () => {
		const root = mkdtemp();
		try {
			writeEstablishedGoal(root);
			writeSpecSide(root, "vc12-key");
			// Structural fact: the gate layer has no task-type input at all —
			// its parameters are exactly (agenticdocRoot, key, phase).
			expect(dispatchDocGaps.length).toBe(3);
			const gaps = dispatchDocGaps(root, "vc12-key", "SPEC");
			const pass = gaps.length === 0;
			expect(pass).toBe(true);
			process.stdout.write(`[VERIFY] VC-012: coding_at_spec_allowed=${pass} gate_blocked=${gaps.length > 0}\n`);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("design tier passes at exactly MIN_PHASE_DOC_BYTES (threshold is >=)", () => {
		const root = mkdtemp();
		try {
			writeEstablishedGoal(root);
			writeSpecSide(root, "b1-key");
			const designPath = writeDesignDoc(root, "b1-key", MIN_PHASE_DOC_BYTES);
			writeDesignNote(root, "b1-key");
			const size = fs.statSync(designPath).size;
			expect(size).toBe(500);
			const gaps = dispatchDocGaps(root, "b1-key", "DESIGN");
			expect(gaps).toEqual([]);
			process.stdout.write(`[VERIFY] boundary: design_md_bytes=${size} design_tier_pass=${gaps.length === 0}\n`);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("omitting the phase argument defaults to the spec tier (D-101b)", () => {
		const root = mkdtemp();
		try {
			writeEstablishedGoal(root);
			writeSpecSide(root, "d101b-key");
			const byDefault = dispatchDocGaps(root, "d101b-key");
			expect(byDefault).toEqual([]); // spec tier: design side not required
			expect(byDefault).toEqual(dispatchDocGaps(root, "d101b-key", ""));
			expect(dispatchDocGaps(root, "d101b-key", "DESIGN")).toHaveLength(2);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});

	it("_scratch bypasses the gate regardless of phase (D-104)", () => {
		const root = mkdtemp();
		try {
			expect(dispatchDocGaps(root, "_scratch")).toEqual([]);
			expect(dispatchDocGaps(root, "_scratch", "DESIGN")).toEqual([]);
		} finally {
			fs.rmSync(root, { recursive: true, force: true });
		}
	});
});
