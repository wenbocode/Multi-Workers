import * as fs from "node:fs";
import * as path from "node:path";
import { isGoalEstablished, readGoal } from "../pm/goal-reader.ts";
import { SCRATCH_WORKERS_KEY } from "./paths.ts";

/** Minimum phase-doc size, matching advance_phase.py's GATES thresholds. */
export const MIN_PHASE_DOC_BYTES = 500;

export interface PhaseDocStatus {
	spec: boolean;
	design: boolean;
	/** Count of optional evidence/research/spec-*.md notes. */
	specEvidence: number;
	/** Count of optional evidence/research/design-*.md notes. */
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

/** Read dispatch prerequisites and optional research counts for the widget.
 * The spec gate requires goal alignment when established and a numbered AC. */
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

/** The design tier adds the design document to the spec requirements. */
export type GateTier = "spec" | "design";

/** Phases whose docs gate includes the design side. */
const DESIGN_TIER_PHASES = new Set<string>(["DESIGN", "PLAN", "TASKS", "EXECUTE", "VERIFY", "DONE"]);

/** Normalize a phase string (a pm-state `- Phase:` value or a
 * caller-supplied phase) into a gate tier. Placeholder and unknown phases —
 * "init" (the stub `update_index.py claim` writes for new keys), "—" (the
 * index-row placeholder), ""/whitespace, or any unrecognized value — fall
 * back to the spec tier so a new key is never held to design-phase
 * documentation requirements before its design phase even starts
 * (mw-worker-visibility-gate D-102). Matching is case-insensitive and trims
 * surrounding whitespace. */
export function gateTierOf(phase: string): GateTier {
	return DESIGN_TIER_PHASES.has(phase.trim().toUpperCase()) ? "design" : "spec";
}

/** Missing required documents or contents. Research counts are informational. */
export function phaseDocGaps(status: PhaseDocStatus, tier: GateTier = "design"): string[] {
	const gaps: string[] = [];
	if (!status.spec) gaps.push("spec.md missing or under 500 bytes");
	if (!status.specS0)
		gaps.push("spec.md missing a non-empty §0 Goal Alignment section with 预期收益 (goal.md is established)");
	if (!status.specAC) gaps.push("spec.md has no numbered acceptance criteria (AC-NNN)");
	if (tier === "design" && !status.design) gaps.push("design.md missing or under 500 bytes");
	return gaps;
}

/** Compact widget badge for the docs gate, e.g. `S+ D- ev:1/2`. */
export function formatDocsBadge(status: PhaseDocStatus): string {
	const ev = (status.specEvidence >= 1 ? 1 : 0) + (status.designEvidence >= 1 ? 1 : 0);
	return `S${status.spec ? "+" : "-"} D${status.design ? "+" : "-"} ev:${ev}/2`;
}

/** Actionable hint appended to every docs-gate refusal. */
export const DOC_GATE_HINT =
	"Complete the missing requirements via the agentic-task requirements/system-design workflows. " +
	"For throwaway ad-hoc work, dispatch under '_scratch'.";

/** Apply the owner key's docs tier from pm-state. _scratch bypasses this gate,
 * and an omitted or unknown phase uses the spec tier. */
export function dispatchDocGaps(agenticdocRoot: string, key: string, phase?: string): string[] {
	if (key === SCRATCH_WORKERS_KEY) return [];
	return phaseDocGaps(readPhaseDocs(agenticdocRoot, key), gateTierOf(phase ?? ""));
}
