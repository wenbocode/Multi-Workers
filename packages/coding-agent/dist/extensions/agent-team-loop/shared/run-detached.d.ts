import type { ExtensionAPI } from "../../../core/extensions/types.ts";
/**
 * shared/run-detached.ts — the TS entry for `mw run-detached` (AC-008, design
 * D-005). One internal function backs both activation surfaces:
 *   - the `mw_run_detached` tool (PM + worker, dual-path registration),
 *   - the `/mw run-detached` slash command (human/PM, ui-bridge — W-03b).
 *
 * The Python side (console_run.py, L1) owns the windowing/console flag
 * contract and the marker/heartbeat/log evidence; the TS side only forwards
 * the options verbatim (AC-003: no re-implementation of Python flag
 * semantics) and parses the CLI's 4-line handoff contract:
 *
 *   [mw run-detached] pid=<supervisor_pid>
 *   marker=<path>
 *   heartbeat=<path>
 *   log=<path>
 *
 * Fail-open by contract: a missing mw.py / spawn failure / unparsable output
 * returns a structured error object inside the union result — this function
 * never throws through an extension boundary.
 */
/** The registered tool name (shared across access points). */
export declare const MW_RUN_DETACHED_TOOL = "mw_run_detached";
/** Parsed handoff from `mw run-detached`'s stdout contract. */
export interface RunDetachedHandle {
    /** Supervisor (hidden-console) process id. */
    pid: number;
    /** marker.json path; poll it for `rc`/`timed_out` when the run ends. */
    marker: string;
    /** heartbeat.json path — mtime advances while the command is alive. */
    heartbeat: string;
    /** run.log path — child stdout+stderr combined. */
    log: string;
}
export type RunDetachedResult = {
    ok: true;
    handle: RunDetachedHandle;
} | {
    ok: false;
    error: string;
};
export interface RunDetachedOptions {
    /** Command argv after `--` (verbatim, no shell). Required non-empty. */
    cmd: string[];
    /** Working directory for the command (default: the current project dir). */
    cwd?: string;
    /** Evidence run dir; default `<cwd>/.mw/runs/run-<timestamp>`. */
    run_dir?: string;
    /** Kill the command tree after N minutes (marker rc=124, timed_out=true). */
    timeout_min?: number;
    /** Heartbeat write interval in seconds (default 5). */
    heartbeat_s?: number;
}
/**
 * Dispatch a background command via `mw run-detached` and parse the handoff.
 * Fail-open: every failure path returns `{ok:false,error}` and never throws.
 * Uses spawnSync against the foreground CLI — the foreground half prints the
 * 4-line handoff and returns immediately; the actual backgrounding happens in
 * the hidden-console supervisor (L1), so no detached/stdio plumbing is needed
 * here (unlike startMw, which spawns the resident service directly).
 */
export declare function runDetachedMw(opts: RunDetachedOptions): RunDetachedResult;
/**
 * Register the `mw_run_detached` tool (design D-005, AC-008). Called from
 * BOTH activate paths — pmActivate and workerModeActivate (the
 * registerRagTools precedent) — so PM and worker windows can dispatch
 * background commands. Worker visibility is decided by the `activeToolsForType`
 * allowlist gate (shell roles only); this registration is structural and
 * unconditional. `controlRoot` is the default working directory for the
 * dispatched command when the caller does not pass `cwd`.
 */
export declare function registerRunDetachedTool(pi: ExtensionAPI, controlRoot: string): void;
//# sourceMappingURL=run-detached.d.ts.map