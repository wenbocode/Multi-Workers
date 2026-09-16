import { existsSync } from "node:fs";
import * as path from "node:path";
import { delimiter } from "node:path";
import { spawn, spawnSync } from "child_process";
import { getBinDir } from "../config.js";
/**
 * Find bash executable on PATH (cross-platform)
 */
function isLegacyWslBashPath(shellPath) {
    const normalized = shellPath.replace(/\//g, "\\").toLowerCase();
    return /^[a-z]:\\windows\\(?:system32|sysnative)\\bash\.exe$/.test(normalized);
}
function getBashShellConfig(shell) {
    return isLegacyWslBashPath(shell)
        ? { shell, args: ["-s"], commandTransport: "stdin", type: "bash" }
        : { shell, args: ["-c"], type: "bash" };
}
/**
 * Probe whether a WSL/system bash is actually functional (has a distro installed).
 * Returns false if the process exits non-zero or if stdout doesn't match "ok".
 */
function isWslBashWorking(bashPath) {
    try {
        const result = spawnSync(bashPath, ["-c", "echo ok"], {
            encoding: "utf-8",
            timeout: 3000,
            windowsHide: true,
        });
        return result.status === 0 && (result.stdout ?? "").trim() === "ok";
    }
    catch {
        return false;
    }
}
/**
 * Find PowerShell on Windows. Prefers pwsh (7+) over powershell (5.1).
 * Returns null if neither is found.
 */
function getPowerShellConfig() {
    for (const name of ["pwsh.exe", "powershell.exe"]) {
        try {
            const result = spawnSync("where", [name], {
                encoding: "utf-8",
                timeout: 3000,
                windowsHide: true,
            });
            if (result.status === 0 && result.stdout) {
                const first = result.stdout.trim().split(/\r?\n/)[0];
                if (first && existsSync(first)) {
                    return { shell: first, args: ["-NoProfile", "-NonInteractive", "-Command"], type: "powershell" };
                }
            }
        }
        catch {
            // continue to next candidate
        }
    }
    return null;
}
function findBashOnPath() {
    if (process.platform === "win32") {
        // Windows: Use 'where' and verify file exists (where can return non-existent paths)
        try {
            const result = spawnSync("where", ["bash.exe"], {
                encoding: "utf-8",
                timeout: 5000,
                windowsHide: true,
            });
            if (result.status === 0 && result.stdout) {
                const firstMatch = result.stdout.trim().split(/\r?\n/)[0];
                if (firstMatch && existsSync(firstMatch)) {
                    return firstMatch;
                }
            }
        }
        catch {
            // Ignore errors
        }
        return null;
    }
    // Unix: Use 'which' and trust its output (handles Termux and special filesystems)
    try {
        const result = spawnSync("which", ["bash"], { encoding: "utf-8", timeout: 5000 });
        if (result.status === 0 && result.stdout) {
            const firstMatch = result.stdout.trim().split(/\r?\n/)[0];
            if (firstMatch) {
                return firstMatch;
            }
        }
    }
    catch {
        // Ignore errors
    }
    return null;
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
export function getShellConfig(customShellPath) {
    // 1. Check user-specified shell path
    if (customShellPath) {
        if (existsSync(customShellPath)) {
            return getBashShellConfig(customShellPath);
        }
        throw new Error(`Custom shell path not found: ${customShellPath}`);
    }
    if (process.platform === "win32") {
        // 2. WSL bash — only if a distro is installed and actually responding.
        //    WSL is the preferred bash on Windows when configured correctly.
        const bashOnPath = findBashOnPath();
        if (bashOnPath && isLegacyWslBashPath(bashOnPath) && isWslBashWorking(bashOnPath)) {
            return getBashShellConfig(bashOnPath);
        }
        // 3. PowerShell fallback — universal on Windows, no third-party install needed.
        //    bash-only scripts should have a windows/ PowerShell variant (resolveScriptPath).
        const psConfig = getPowerShellConfig();
        if (psConfig) {
            return psConfig;
        }
        throw new Error(`No shell found. Options:\n` + `  1. Install WSL: wsl --install\n` + `  2. Set shellPath in settings.json\n`);
    }
    // Unix: try /bin/bash, then bash on PATH, then fallback to sh
    if (existsSync("/bin/bash")) {
        return getBashShellConfig("/bin/bash");
    }
    const bashOnPath = findBashOnPath();
    if (bashOnPath) {
        return getBashShellConfig(bashOnPath);
    }
    return { shell: "sh", args: ["-c"], type: "bash" };
}
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
export function resolveScriptPath(scriptPath, shellConfig) {
    if (shellConfig.type !== "powershell")
        return scriptPath;
    const dir = path.dirname(scriptPath);
    const name = path.basename(scriptPath, path.extname(scriptPath));
    const windowsVariant = path.join(dir, "windows", `${name}.ps1`);
    return existsSync(windowsVariant) ? windowsVariant : scriptPath;
}
export function getShellEnv() {
    const binDir = getBinDir();
    const pathKey = Object.keys(process.env).find((key) => key.toLowerCase() === "path") ?? "PATH";
    const currentPath = process.env[pathKey] ?? "";
    const pathEntries = currentPath.split(delimiter).filter(Boolean);
    const hasBinDir = pathEntries.includes(binDir);
    const updatedPath = hasBinDir ? currentPath : [binDir, currentPath].filter(Boolean).join(delimiter);
    return {
        ...process.env,
        [pathKey]: updatedPath,
    };
}
/**
 * Sanitize binary output for display/storage.
 * Removes characters that crash string-width or cause display issues:
 * - Control characters (except tab, newline, carriage return)
 * - Lone surrogates
 * - Unicode Format characters (crash string-width due to a bug)
 * - Characters with undefined code points
 */
export function sanitizeBinaryOutput(str) {
    // Use Array.from to properly iterate over code points (not code units)
    // This handles surrogate pairs correctly and catches edge cases where
    // codePointAt() might return undefined
    return Array.from(str)
        .filter((char) => {
        // Filter out characters that cause string-width to crash
        // This includes:
        // - Unicode format characters
        // - Lone surrogates (already filtered by Array.from)
        // - Control chars except \t \n \r
        // - Characters with undefined code points
        const code = char.codePointAt(0);
        // Skip if code point is undefined (edge case with invalid strings)
        if (code === undefined)
            return false;
        // Allow tab, newline, carriage return
        if (code === 0x09 || code === 0x0a || code === 0x0d)
            return true;
        // Filter out control characters (0x00-0x1F, except 0x09, 0x0a, 0x0x0d)
        if (code <= 0x1f)
            return false;
        // Filter out Unicode format characters
        if (code >= 0xfff9 && code <= 0xfffb)
            return false;
        return true;
    })
        .join("");
}
/**
 * Detached child processes must be tracked so they can be killed on parent
 * shutdown signals (SIGHUP/SIGTERM).
 */
const trackedDetachedChildPids = new Set();
export function trackDetachedChildPid(pid) {
    trackedDetachedChildPids.add(pid);
}
export function untrackDetachedChildPid(pid) {
    trackedDetachedChildPids.delete(pid);
}
export function killTrackedDetachedChildren() {
    for (const pid of trackedDetachedChildPids) {
        killProcessTree(pid);
    }
    trackedDetachedChildPids.clear();
}
/**
 * Kill a process and all its children (cross-platform)
 */
export function killProcessTree(pid) {
    if (process.platform === "win32") {
        // Use taskkill on Windows to kill process tree
        try {
            spawn("taskkill", ["/F", "/T", "/PID", String(pid)], {
                stdio: "ignore",
                detached: true,
                windowsHide: true,
            });
        }
        catch {
            // Ignore errors if taskkill fails
        }
    }
    else {
        // Use SIGKILL on Unix/Linux/Mac
        try {
            process.kill(-pid, "SIGKILL");
        }
        catch {
            // Fallback to killing just the child if process group kill fails
            try {
                process.kill(pid, "SIGKILL");
            }
            catch {
                // Process already dead
            }
        }
    }
}
//# sourceMappingURL=shell.js.map