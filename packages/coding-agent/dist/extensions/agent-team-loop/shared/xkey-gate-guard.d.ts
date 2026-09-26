import type { ExtensionAPI } from "../../../core/extensions/types.ts";
/** Resolve the project root the gate directory is anchored against: the
 * MW_XKEY_GATE_ROOT override (tilde-expanded, resolved) wins, else the
 * process cwd (PM and worker windows both run with the project as cwd).
 * env injectable for tests. */
export declare function resolveXkeyGateRoot(env?: NodeJS.ProcessEnv): string;
/** The project's gate directory: `<root>/.agenticdoc/_autopilot/gates`. */
export declare function xkeyGateDir(root: string): string;
/** Does a write/edit tool path target the gate directory? Pure: resolves the
 * path like the tools do (cwd-relative, ~ expanded, folded) and also matches
 * an absolute spelling of any project's gate directory, so a write aimed at
 * a different project is still refused. */
export declare function isXkeyGatePath(root: string, rawPath: string, cwd?: string): boolean;
export interface XkeyGateBashVerdict {
    /** True when the command must be blocked (gate-dir reference + write
     * construct, or a redirect whose target is inside the gate dir). */
    prohibited: boolean;
    /** Block reason (always present when prohibited=true). */
    reason?: string;
}
/** Decision for one bash tool command: fail-closed — a gate-directory
 * reference plus any write construct is denied, redirect targets are checked
 * separately (a redirect to an unprotected path with a gate read side stays
 * allowed). Text-level heuristic mirroring protected-config.ts, not a
 * sandbox. */
export declare function checkXkeyGateBashCommand(root: string, command: string): XkeyGateBashVerdict;
/** Worker-mode visibility: append one [XKEY_GATE] line to the task's
 * trace.log (dirname of PI_WORKER_TASK — the same file the PM watch reads
 * live) so a refused worker shows up immediately. Best-effort: a failure
 * here must never break the block itself. taskPathEnv injectable for tests. */
export declare function recordXkeyGateBlockTrace(toolName: string, detail: string, taskPathEnv?: string | undefined): void;
/** Register the tool_call gate-dir block: write/edit paths and bash commands
 * are checked against the gate directory; everything else (including all
 * reads and the xkey evidence/ledger/tickets tree) passes through untouched.
 * Runs in every mode (PM, worker, interactive). */
export declare function registerXkeyGateGuard(pi: ExtensionAPI): void;
//# sourceMappingURL=xkey-gate-guard.d.ts.map