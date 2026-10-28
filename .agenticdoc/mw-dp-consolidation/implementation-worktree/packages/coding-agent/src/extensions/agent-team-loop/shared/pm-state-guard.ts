import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { SCRATCH_WORKERS_KEY } from "./paths.ts";
import { readPhaseDocs } from "./phase-docs.ts";

/**
 * pm-state.md machine-interface guard (hard block) + phase-chain audit
 * warnings (takeover-time).
 *
 * Why: advance_phase.py gates only fire when the script runs. A PM agent that
 * hand-writes pm-state.md bypasses every gate — the mw-worker-timeout-convergence
 * case: pm-state hand-set to EXECUTE while _index.parallel stayed at SPEC
 * (two-source divergence), a research note named outside the spec-* convention,
 * and no §0 in the spec. Python-side audit_phase.py catches this retroactively
 * (and runs on `update_index.py claim`); this module closes the bypass at the
 * tool layer so the hand-edit never lands in the first place.
 */

/** Interface lines owned by framework scripts: advance_phase.py writes
 * `- Phase:`, update_index.py writes `- Claim-Id:`. Agent writes may carry
 * them only byte-identical (e.g. full-file rewrites that update log sections). */
const INTERFACE_LINE = /^- (Phase|Claim-Id):/m;

const PHASE_LINE = /^- Phase:\s*(.+?)\s*$/m;

/** Phase ladder, matching advance_phase.py's PHASES (upper-case for compare). */
export const PHASE_ORDER = ["SPEC", "DESIGN", "PLAN", "TASKS", "EXECUTE", "VERIFY", "DONE"] as const;

export const PHASE_GUARD_HINT =
	"pm-state.md's '- Phase:' and '- Claim-Id:' lines are machine interfaces owned by the framework " +
	"scripts (advance_phase.py / update_index.py); hand-editing them bypasses the phase gates. " +
	"To change phase, call the advance_phase tool (shell-free) or run: " +
	"python <framework>/scripts/advance_phase.py <key> <target-phase> " +
	"(gates are checked, pm-state and _index.parallel stay in sync). To update the rest of " +
	"pm-state.md (logs, ledgers, decisions), keep the interface lines byte-identical.";

function interfaceLines(content: string): string[] {
	return content.split("\n").filter((l) => INTERFACE_LINE.test(l));
}

/** The key whose pm-state.md a write/edit targets ({key}/pm-state.md), if any. */
function pmStateTarget(
	toolName: string,
	args: unknown,
	projectDir: string,
	agenticdocRoot: string,
): { key: string; absPath: string } | undefined {
	if (toolName !== "write" && toolName !== "edit") return undefined;
	const filePath = (args as { path?: unknown } | undefined)?.path;
	if (typeof filePath !== "string" || filePath === "") return undefined;
	const rel = path.relative(path.resolve(agenticdocRoot), path.resolve(projectDir, filePath));
	if (rel.startsWith("..") || path.isAbsolute(rel)) return undefined; // outside .agenticdoc
	const parts = rel.split(path.sep);
	if (parts.length !== 2 || parts[1] !== "pm-state.md") return undefined;
	const key = parts[0] ?? "";
	if (!key || key.startsWith("_") || key.startsWith(".")) return undefined;
	return { key, absPath: path.resolve(projectDir, filePath) };
}

/**
 * Detect a write/edit tool call that would create, change, or remove a
 * pm-state.md machine-interface line. Returns the block reason, or undefined
 * to allow (non-pm-state paths, scratch keys, edits that leave the interface
 * lines untouched).
 */
export function pmStateInterfaceViolation(
	toolName: string,
	args: unknown,
	projectDir: string,
	agenticdocRoot: string,
	readFile: (abs: string) => string | undefined = defaultReadFile,
): string | undefined {
	const target = pmStateTarget(toolName, args, projectDir, agenticdocRoot);
	if (!target) return undefined;

	if (toolName === "write") {
		const content = (args as { content?: unknown } | undefined)?.content;
		if (typeof content !== "string") return undefined;
		const next = interfaceLines(content);
		if (next.length === 0) return undefined; // rewrite without interface lines: allowed, advance guards handle drift
		const cur = interfaceLines(readFile(target.absPath) ?? "");
		if (cur.length === next.length && cur.every((l, i) => l === next[i])) return undefined;
		return `${PHASE_GUARD_HINT} (key: ${target.key})`;
	}

	// edit: block any hunk whose oldText or newText carries an interface line
	const edits = (args as { edits?: unknown } | undefined)?.edits;
	if (!Array.isArray(edits)) return undefined;
	for (const e of edits) {
		const oldText = (e as { oldText?: unknown } | undefined)?.oldText;
		const newText = (e as { newText?: unknown } | undefined)?.newText;
		if (
			(typeof oldText === "string" && INTERFACE_LINE.test(oldText)) ||
			(typeof newText === "string" && INTERFACE_LINE.test(newText))
		) {
			return `${PHASE_GUARD_HINT} (key: ${target.key})`;
		}
	}
	return undefined;
}

function defaultReadFile(abs: string): string | undefined {
	try {
		return fs.readFileSync(abs, "utf8");
	} catch {
		return undefined;
	}
}

/**
 * Register the tool_call hard block. Blocks write/edit calls that change or
 * remove pm-state.md's `- Phase:` / `- Claim-Id:` lines. bash-based edits
 * (sed/echo) are not intercepted; audit_phase.py still catches them after
 * the fact via the two-source divergence check.
 */
export function registerPmStateGuard(pi: ExtensionAPI, projectDir: string, agenticdocRoot: string): void {
	pi.on("tool_call", (event) => {
		if (event.toolName !== "write" && event.toolName !== "edit") return undefined;
		const reason = pmStateInterfaceViolation(event.toolName, event.input, projectDir, agenticdocRoot);
		return reason ? { block: true, reason } : undefined;
	});
}

/** The `- Phase:` value from {key}/pm-state.md, trimmed; undefined when the
 * file or line is missing. */
export function readPmStatePhase(agenticdocRoot: string, key: string): string | undefined {
	try {
		const content = fs.readFileSync(path.join(agenticdocRoot, key, "pm-state.md"), "utf8");
		const m = PHASE_LINE.exec(content);
		return m?.[1];
	} catch {
		return undefined;
	}
}

/**
 * Phase-chain audit at takeover time (TS-side mirror of audit_phase.py's
 * replay, minus the python process): re-checks the gate evidence for every
 * phase the key's pm-state claims to have passed, plus the two-source
 * consistency between pm-state.md and _index.parallel. Non-blocking — claiming
 * a broken key in order to fix it is legitimate; the warnings make the
 * breakage visible in the takeover result.
 */
export function phaseAuditWarnings(agenticdocRoot: string, key: string, indexPhase: string): string[] {
	if (key === SCRATCH_WORKERS_KEY) return [];
	const warnings: string[] = [];
	const pmPhase = readPmStatePhase(agenticdocRoot, key);
	if (!pmPhase || pmPhase === "(pending)" || pmPhase.toUpperCase() === "INIT") return warnings;

	const upper = pmPhase.toUpperCase();
	const rank = PHASE_ORDER.indexOf(upper as (typeof PHASE_ORDER)[number]);
	if (rank < 0) {
		warnings.push(`[audit] pm-state.md has unknown phase '${pmPhase}' (valid: ${PHASE_ORDER.join("/")}).`);
		return warnings;
	}

	if (indexPhase && indexPhase !== "—" && indexPhase.toUpperCase() !== upper) {
		warnings.push(
			`[audit] INDEX-DIVERGENCE: pm-state.md phase=${upper} != _index.parallel phase=${indexPhase} — phase changes must go through advance_phase.py (it syncs both sources); divergence means a hand-edit bypassed the gates.`,
		);
	}

	const docs = readPhaseDocs(agenticdocRoot, key);
	if (rank >= PHASE_ORDER.indexOf("DESIGN")) {
		if (!docs.spec) warnings.push("[audit] design gate: spec.md missing or under 500 bytes.");
		if (docs.specEvidence < 1)
			warnings.push(
				"[audit] design gate: evidence/research/spec-*.md missing (>= 1 note; zero-research declaration counts).",
			);
		if (!docs.specS0)
			warnings.push(
				"[audit] design gate: spec.md missing a non-empty §0 Goal Alignment section with 预期收益 (goal.md is established).",
			);
		if (!docs.specAC) warnings.push("[audit] design gate: spec.md has no numbered acceptance criteria (AC-NNN).");
	}
	if (rank >= PHASE_ORDER.indexOf("PLAN")) {
		if (!docs.design) warnings.push("[audit] plan gate: design.md missing or under 500 bytes.");
		if (docs.designEvidence < 1)
			warnings.push(
				"[audit] plan gate: evidence/research/design-*.md missing (>= 1 note; zero-research declaration counts).",
			);
	}
	if (rank >= PHASE_ORDER.indexOf("EXECUTE")) {
		try {
			const n = fs.readdirSync(path.join(agenticdocRoot, key, "tasks")).filter((f) => f.endsWith(".md")).length;
			if (n < 1) warnings.push("[audit] execute gate: tasks/ has no .md files.");
		} catch {
			warnings.push(
				"[audit] execute gate: tasks/ directory missing (mw-dispatch flows: keep a pointer task.md under tasks/ so the key stays auditable).",
			);
		}
	}
	return warnings;
}
