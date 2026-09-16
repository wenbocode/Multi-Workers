import type { ExtensionAPI } from "../../../core/extensions/types.ts";
export declare const PHASE_GUARD_HINT: string;
/**
 * Detect a write/edit tool call that would create, change, or remove a
 * pm-state.md machine-interface line. Returns the block reason, or undefined
 * to allow (non-pm-state paths, scratch keys, edits that leave the interface
 * lines untouched).
 */
export declare function pmStateInterfaceViolation(toolName: string, args: unknown, projectDir: string, agenticdocRoot: string, readFile?: (abs: string) => string | undefined): string | undefined;
/**
 * Register the tool_call hard block. Blocks write/edit calls that change or
 * remove pm-state.md's `- Phase:` / `- Claim-Id:` lines. bash-based edits
 * (sed/echo) are not intercepted; audit_phase.py still catches them after
 * the fact via the two-source divergence check.
 */
export declare function registerPmStateGuard(pi: ExtensionAPI, projectDir: string, agenticdocRoot: string): void;
/** The `- Phase:` value from {key}/pm-state.md, trimmed; undefined when the
 * file or line is missing. */
export declare function readPmStatePhase(agenticdocRoot: string, key: string): string | undefined;
/**
 * Phase-chain audit at takeover time (TS-side mirror of audit_phase.py's
 * replay, minus the python process): re-checks the gate evidence for every
 * phase the key's pm-state claims to have passed, plus the two-source
 * consistency between pm-state.md and _index.parallel. Non-blocking — claiming
 * a broken key in order to fix it is legitimate; the warnings make the
 * breakage visible in the takeover result.
 */
export declare function phaseAuditWarnings(agenticdocRoot: string, key: string, indexPhase: string): string[];
//# sourceMappingURL=pm-state-guard.d.ts.map