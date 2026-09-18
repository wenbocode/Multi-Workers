/**
 * Locate the installed AgenticTask framework's scripts directory
 * (advance_phase.py / update_index.py / audit_phase.py / detect_root.py).
 *
 * Resolution order:
 *   1. {projectDir}/.claude/scripts — the installed mirror every platform
 *      workflow references as {PLATFORM_DIR}/scripts (written by install.py,
 *      refreshed by sync_framework.py).
 *   2. {projectDir}/.agents/skills/agentic-task/claude/scripts — the skill
 *      clone install.py leaves behind (same content; survives a partial
 *      install where .claude was not laid down).
 *
 * Returns null when neither exists (`mw init --no-framework` / framework not
 * installed) — callers fail closed with an actionable message.
 */
export declare function agenticScriptsDir(projectDir: string): string | null;
export interface AgenticScriptResult {
    ok: boolean;
    /** Combined stdout+stderr — the gate scripts print failures to stderr. */
    output: string;
}
/**
 * Run one AgenticTask framework script directly: spawn with list args, no
 * shell. Same execution model as mw-runner's mw.py calls, so framework state
 * operations never depend on the agent window's bash tool — a fresh machine
 * whose pi shell resolution or in-shell `python` PATH differs (WSL-only bash,
 * Store-stub python, python3-only Linux) can still advance phases.
 */
export declare function runAgenticScript(projectDir: string, scriptName: string, args: string[], timeoutMs?: number): AgenticScriptResult;
//# sourceMappingURL=agentic-scripts.d.ts.map