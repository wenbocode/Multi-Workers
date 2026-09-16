export interface ShellConfig {
    shell: string;
    args: string[];
    commandTransport?: "argv" | "stdin";
    /** Identifies the shell family so callers can route to platform-specific script variants. */
    type?: "bash" | "powershell";
}
/**
 * Resolve shell configuration based on platform and an optional explicit shell path.
 * Resolution order (Windows):
 * 1. User-specified shellPath
 * 2. WSL bash — only if a distro is installed and responds to `echo ok`
 * 3. PowerShell (pwsh / powershell) — universal fallback; bash-only scripts
 *    should provide a windows/ PowerShell variant via resolveScriptPath()
 *
 * Resolution order (Unix):
 * 1. User-specified shellPath
 * 2. /bin/bash, then bash on PATH, then sh
 */
export declare function getShellConfig(customShellPath?: string): ShellConfig;
/**
 * Resolve the platform-appropriate path for a bash-only script.
 *
 * Convention: bash-only scripts live at some/path/script.sh; their Windows
 * PowerShell equivalents live at some/path/windows/script.ps1.
 *
 * When the active shell is PowerShell, this function replaces the .sh path with
 * the windows/ variant if it exists. Falls back to the original path so the
 * caller can decide how to handle a missing variant.
 */
export declare function resolveScriptPath(scriptPath: string, shellConfig: ShellConfig): string;
export declare function getShellEnv(): NodeJS.ProcessEnv;
/**
 * Sanitize binary output for display/storage.
 * Removes characters that crash string-width or cause display issues:
 * - Control characters (except tab, newline, carriage return)
 * - Lone surrogates
 * - Unicode Format characters (crash string-width due to a bug)
 * - Characters with undefined code points
 */
export declare function sanitizeBinaryOutput(str: string): string;
export declare function trackDetachedChildPid(pid: number): void;
export declare function untrackDetachedChildPid(pid: number): void;
export declare function killTrackedDetachedChildren(): void;
/**
 * Kill a process and all its children (cross-platform)
 */
export declare function killProcessTree(pid: number): void;
//# sourceMappingURL=shell.d.ts.map