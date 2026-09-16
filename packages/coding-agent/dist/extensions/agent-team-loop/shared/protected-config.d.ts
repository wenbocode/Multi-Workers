import type { ExtensionAPI } from "../../../core/extensions/types.ts";
/** Resolve the pi agent dir, mirroring core getAgentDir(): the env override
 * (tilde-expanded, resolved to absolute) wins, else ~/.pi/agent. env
 * injectable for tests. */
export declare function resolveAgentDir(env?: NodeJS.ProcessEnv): string;
/** Absolute paths of the protected files for one agent dir. */
export declare function protectedConfigPaths(agentDir: string): string[];
/** Does a write/edit tool path target a protected config file (or the agent
 * dir itself)? Pure: resolves the path like the tools do (cwd-relative, ~
 * expanded) and compares folded. */
export declare function isProtectedConfigPath(agentDir: string, rawPath: string, cwd?: string): boolean;
export interface BashGuardVerdict {
    /** True when the command must be blocked (protected reference + write
     * construct, or a redirect whose target is protected). */
    prohibited: boolean;
    /** Block reason (always present when prohibited=true). */
    reason?: string;
}
/** Decision for one bash tool command: fail-closed — any protected-path
 * reference plus any write construct is denied, redirect targets are checked
 * separately (a redirect to an unprotected path with a protected read side
 * stays allowed). Inline code (python -c / node -e) with a write marker also
 * matches a bare `.pi/agent` fragment, because path assembly via string
 * concat / process.env access defeats the reference expansion. */
export declare function checkProtectedBashCommand(agentDir: string, command: string): BashGuardVerdict;
/** Worker-mode visibility: append one [PROTECTED_CONFIG] line to the task's
 * trace.log (dirname of PI_WORKER_TASK — the same file the PM watch reads
 * live) so a blocked worker shows up immediately. Best-effort: a failure
 * here must never break the block itself. taskPathEnv injectable for tests. */
export declare function recordProtectedBlockTrace(toolName: string, detail: string, taskPathEnv?: string | undefined): void;
/** Register the tool_call hard block: write/edit paths and bash commands are
 * checked against the protected set; everything else (including all reads)
 * passes through untouched. Runs in every mode (PM, worker, interactive). */
export declare function registerProtectedConfigGuard(pi: ExtensionAPI): void;
//# sourceMappingURL=protected-config.d.ts.map