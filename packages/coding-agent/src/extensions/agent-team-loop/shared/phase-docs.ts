import * as fs from "node:fs";
import * as path from "node:path";
import { isGoalEstablished, readGoal } from "../pm/goal-reader.ts";
import { SCRATCH_WORKERS_KEY } from "./paths.ts";

/** Minimum phase-doc size, matching advance_phase.py's GATES thresholds. */
export const MIN_PHASE_DOC_BYTES = 500;

export interface PhaseDocStatus {
	spec: boolean;
	design: boolean;
	/** Count of evidence/research/spec-*.md notes (>= 1 required). */
	specEvidence: number;
	/** Count of evidence/research/design-*.md notes (>= 1 required). */
	designEvidence: number;
	/** spec.md has a non-empty §0 Goal Alignment section naming 预期收益.
	 * True by default when goal.md is NOT established (advance_phase.py skips
	 * the check in that case — same rule here). */
	specS0: boolean;
	/** spec.md contains >= 1 numbered acceptance criterion (AC-NNN). */
	specAC: boolean;
}

function fileAtLeast(file: string, minBytes: number): boolean {
	try {
		return fs.statSync(file).size >= minBytes;
	} catch {
		return false;
	}
}

function countNotes(dir: string, prefix: string): number {
	try {
		return fs.readdirSync(dir).filter((n) => n.startsWith(prefix) && n.endsWith(".md")).length;
	} catch {
		return 0;
	}
}

/** Whether text contains a heading whose title mentions any of `headingKws`
 * with a non-empty (comment-stripped) body that also includes `mustContain`.
 * Port of advance_phase.py's _section_body: the section ends at the next
 * same-or-higher-level heading; deeper subheadings belong to it. */
function hasSectionWith(text: string, headingKws: string[], mustContain?: string): boolean {
	const stripped = text.replace(/<!--[\s\S]*?-->/g, "");
	const lines = stripped.split("\n");
	let inSection = false;
	let level = 0;
	const body: string[] = [];
	for (const line of lines) {
		const m = /^(#{1,6})\s/.exec(line);
		if (m) {
			const lv = m[1].length;
			if (inSection && lv <= level) break;
			if (!inSection && headingKws.some((kw) => line.includes(kw))) {
				inSection = true;
				level = lv;
			}
			continue;
		}
		if (inSection) body.push(line);
	}
	const joined = body.join("\n").trim();
	return joined.length > 0 && (mustContain === undefined || joined.includes(mustContain));
}

function readSpecContent(keyDir: string): string | undefined {
	try {
		return fs.readFileSync(path.join(keyDir, "spec.md"), "utf8");
	} catch {
		return undefined;
	}
}

/** Phase-doc + research-evidence presence for an AgenticTask key. Mirrors
 * advance_phase.py's design/plan gates: spec.md and design.md must each be
 * >= 500 bytes, and each phase needs >= 1 evidence/research/ note (a
 * zero-research declaration note counts). The design gate also requires a
 * §0 Goal Alignment section (when goal.md is established) and >= 1 numbered
 * AC — the same machine checks audit_phase.py replays. */
export function readPhaseDocs(agenticdocRoot: string, key: string): PhaseDocStatus {
	const keyDir = path.join(agenticdocRoot, key);
	const specContent = readSpecContent(keyDir);
	const goalEstablished = isGoalEstablished(readGoal(agenticdocRoot));
	return {
		spec: fileAtLeast(path.join(keyDir, "spec.md"), MIN_PHASE_DOC_BYTES),
		design: fileAtLeast(path.join(keyDir, "design.md"), MIN_PHASE_DOC_BYTES),
		specEvidence: countNotes(path.join(keyDir, "evidence", "research"), "spec-"),
		designEvidence: countNotes(path.join(keyDir, "evidence", "research"), "design-"),
		specS0: !goalEstablished || hasSectionWith(specContent ?? "", ["§0", "Goal Alignment"], "预期收益"),
		specAC: /AC-\d{3}/.test(specContent ?? ""),
	};
}

/** Missing gate items in gate order; [] = fully documented. */
export function phaseDocGaps(status: PhaseDocStatus): string[] {
	const gaps: string[] = [];
	if (!status.spec) gaps.push("spec.md missing or under 500 bytes");
	if (status.specEvidence < 1)
		gaps.push("evidence/research/spec-*.md missing (>= 1 research note; a zero-research declaration counts)");
	if (!status.specS0)
		gaps.push("spec.md missing a non-empty §0 Goal Alignment section with 预期收益 (goal.md is established)");
	if (!status.specAC) gaps.push("spec.md has no numbered acceptance criteria (AC-NNN)");
	if (!status.design) gaps.push("design.md missing or under 500 bytes");
	if (status.designEvidence < 1)
		gaps.push("evidence/research/design-*.md missing (>= 1 research note; a zero-research declaration counts)");
	return gaps;
}

/** Compact widget badge for the docs gate, e.g. `S+ D- ev:1/2`. */
export function formatDocsBadge(status: PhaseDocStatus): string {
	const ev = (status.specEvidence >= 1 ? 1 : 0) + (status.designEvidence >= 1 ? 1 : 0);
	return `S${status.spec ? "+" : "-"} D${status.design ? "+" : "-"} ev:${ev}/2`;
}

/** Actionable hint appended to every docs-gate refusal. */
export const DOC_GATE_HINT =
	"Generate them via the agentic-task requirements/system-design workflows " +
	"(every key decision needs an evidence/research/ note; zero-research still needs a " +
	"declaration note). For throwaway ad-hoc work, dispatch under '_scratch' instead.";

/** Whether a key may dispatch worker tasks: _scratch is the ad-hoc escape
 * hatch; real AgenticTask keys need the full spec + design + research-evidence
 * chain (the advance_phase.py design/plan gates, checked mechanically here so
 * undocumented work cannot reach the worker queue). Returns the gap list,
 * empty when dispatch is allowed. */
export function dispatchDocGaps(agenticdocRoot: string, key: string): string[] {
	if (key === SCRATCH_WORKERS_KEY) return [];
	return phaseDocGaps(readPhaseDocs(agenticdocRoot, key));
}
