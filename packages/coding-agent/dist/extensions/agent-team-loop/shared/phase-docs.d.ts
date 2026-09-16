/** Minimum phase-doc size, matching advance_phase.py's GATES thresholds. */
export declare const MIN_PHASE_DOC_BYTES = 500;
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
/** Phase-doc + research-evidence presence for an AgenticTask key. Mirrors
 * advance_phase.py's design/plan gates: spec.md and design.md must each be
 * >= 500 bytes, and each phase needs >= 1 evidence/research/ note (a
 * zero-research declaration note counts). The design gate also requires a
 * §0 Goal Alignment section (when goal.md is established) and >= 1 numbered
 * AC — the same machine checks audit_phase.py replays. */
export declare function readPhaseDocs(agenticdocRoot: string, key: string): PhaseDocStatus;
/** Missing gate items in gate order; [] = fully documented. */
export declare function phaseDocGaps(status: PhaseDocStatus): string[];
/** Compact widget badge for the docs gate, e.g. `S+ D- ev:1/2`. */
export declare function formatDocsBadge(status: PhaseDocStatus): string;
/** Actionable hint appended to every docs-gate refusal. */
export declare const DOC_GATE_HINT: string;
/** Whether a key may dispatch worker tasks: _scratch is the ad-hoc escape
 * hatch; real AgenticTask keys need the full spec + design + research-evidence
 * chain (the advance_phase.py design/plan gates, checked mechanically here so
 * undocumented work cannot reach the worker queue). Returns the gap list,
 * empty when dispatch is allowed. */
export declare function dispatchDocGaps(agenticdocRoot: string, key: string): string[];
//# sourceMappingURL=phase-docs.d.ts.map