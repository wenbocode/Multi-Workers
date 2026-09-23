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
/** Docs-gate layer for an owner key: "spec" checks only the four spec-side
 * items; "design" checks all six (spec + design side). */
export type GateTier = "spec" | "design";
/** Normalize a phase string (a pm-state `- Phase:` value or a
 * caller-supplied phase) into a gate tier. Placeholder and unknown phases —
 * "init" (the stub `update_index.py claim` writes for new keys), "—" (the
 * index-row placeholder), ""/whitespace, or any unrecognized value — fall
 * back to the spec tier so a new key is never held to design-phase
 * documentation requirements before its design phase even starts
 * (mw-worker-visibility-gate D-102). Matching is case-insensitive and trims
 * surrounding whitespace. */
export declare function gateTierOf(phase: string): GateTier;
/** Missing gate items in gate order; [] = fully documented. The `tier` picks
 * the gate layer: "spec" pushes only the four spec-side items (order
 * unchanged); "design" pushes all six items in the exact pre-tiering order.
 * An omitted tier keeps the legacy full (design-layer) check so existing
 * one-argument callers behave exactly as before. */
export declare function phaseDocGaps(status: PhaseDocStatus, tier?: GateTier): string[];
/** Compact widget badge for the docs gate, e.g. `S+ D- ev:1/2`. */
export declare function formatDocsBadge(status: PhaseDocStatus): string;
/** Actionable hint appended to every docs-gate refusal. */
export declare const DOC_GATE_HINT: string;
/** Whether a key may dispatch worker tasks: _scratch is the ad-hoc escape
 * hatch; real AgenticTask keys are gated by the phase-derived tier. From
 * DESIGN onward the full spec + design + research-evidence chain is required
 * (the advance_phase.py design/plan gates, checked mechanically here so
 * undocumented work cannot reach the worker queue); at SPEC (or any
 * placeholder/unknown phase) only the spec-side chain is required, so early
 * research workers can run under their owner key instead of _scratch.
 * `phase` is the owner key's current phase (its pm-state `- Phase:` value;
 * "" when unknown). Omitting `phase` defaults to the spec tier (D-101b) so
 * call sites that have not been wired to pass a phase yet keep compiling
 * and behave as the SPEC layer. Returns the gap list, empty when dispatch
 * is allowed. */
export declare function dispatchDocGaps(agenticdocRoot: string, key: string, phase?: string): string[];
//# sourceMappingURL=phase-docs.d.ts.map