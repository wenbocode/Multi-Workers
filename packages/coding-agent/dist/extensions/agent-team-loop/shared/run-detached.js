import { spawnSync } from "node:child_process";
import { Type } from "typebox";
import { findMwPy, PYTHON_EXE } from "./mw-runner.js";
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
export const MW_RUN_DETACHED_TOOL = "mw_run_detached";
const HANDOFF_PID_RE = /^\[mw run-detached\] pid=(\d+)$/;
const HANDOFF_PATH_RE = /^(marker|heartbeat|log)=(.*)$/;
/** Parse the 4-line handoff contract. Returns undefined on any structural
 * mismatch — the caller turns that into a structured fail-open error. */
function parseHandoff(stdout) {
    let pid;
    const out = {};
    for (const raw of stdout.split(/\r?\n/)) {
        const line = raw.trim();
        if (!line)
            continue;
        const pidMatch = HANDOFF_PID_RE.exec(line);
        if (pidMatch) {
            pid = Number.parseInt(pidMatch[1], 10);
            continue;
        }
        const pathMatch = HANDOFF_PATH_RE.exec(line);
        if (pathMatch) {
            out[pathMatch[1]] = pathMatch[2] ?? "";
        }
    }
    if (pid === undefined || Number.isNaN(pid))
        return undefined;
    if (!out.marker || !out.heartbeat || !out.log)
        return undefined;
    return { pid, marker: out.marker, heartbeat: out.heartbeat, log: out.log };
}
/**
 * Shared positive bound for the two duration options (F2b): strictly greater
 * than 0, decimals allowed. `exclusiveMinimum` (not an integer `minimum`) is
 * required to keep sub-second/sub-minute values legal — 0.5s (VC-004a) and
 * 0.05min (VC-004b) must stay valid.
 */
const POSITIVE_DURATION = { exclusiveMinimum: 0 };
/** Build the `python mw.py run-detached ... -- <cmd...>` argv. */
function buildArgv(opts) {
    const cmd = [...opts.cmd];
    // argparse REMAINDER passes the first `--` through in some cases; the
    // Python side strips one separator, so the TS side never adds one either.
    if (cmd[0] === "--")
        cmd.shift();
    const args = [findMwPy() ?? "mw.py", "run-detached"];
    if (opts.cwd !== undefined)
        args.push(`--cwd=${opts.cwd}`);
    if (opts.run_dir !== undefined)
        args.push(`--run-dir=${opts.run_dir}`);
    if (opts.timeout_min !== undefined)
        args.push(`--timeout-min=${opts.timeout_min}`);
    if (opts.heartbeat_s !== undefined)
        args.push(`--heartbeat-s=${opts.heartbeat_s}`);
    args.push("--", ...cmd);
    return args;
}
/**
 * Dispatch a background command via `mw run-detached` and parse the handoff.
 * Fail-open: every failure path returns `{ok:false,error}` and never throws.
 * Uses spawnSync against the foreground CLI — the foreground half prints the
 * 4-line handoff and returns immediately; the actual backgrounding happens in
 * the hidden-console supervisor (L1), so no detached/stdio plumbing is needed
 * here (unlike startMw, which spawns the resident service directly).
 */
export function runDetachedMw(opts) {
    const cmd = opts.cmd ?? [];
    if (cmd.length === 0 || cmd.every((c) => c.trim() === "")) {
        return { ok: false, error: "mw run-detached: no command provided after '--'." };
    }
    // F2b (runtime half): the tool schema already rejects these, but the
    // `/mw run-detached` command path parses flags itself and calls this
    // function directly — enforce the same strictly-positive bound here so
    // both surfaces fail with one structured error.
    if (opts.timeout_min !== undefined && !(opts.timeout_min > 0)) {
        return { ok: false, error: "mw run-detached: timeout_min must be > 0 (minutes)." };
    }
    if (opts.heartbeat_s !== undefined && !(opts.heartbeat_s > 0)) {
        return { ok: false, error: "mw run-detached: heartbeat_s must be > 0 (seconds)." };
    }
    const mwPy = findMwPy();
    if (!mwPy) {
        return { ok: false, error: "Could not find mw.py — set MW_PY env var." };
    }
    const args = buildArgv(opts);
    // WindowsHide keeps the foreground CLI from flashing its own console; the
    // supervisor it spawns is already hidden by the Python flag contract.
    const result = spawnSync(PYTHON_EXE, args, { encoding: "utf8", timeout: 30_000, windowsHide: true });
    if (result.error) {
        return { ok: false, error: `Failed to spawn mw run-detached: ${result.error.message}` };
    }
    const stdout = `${result.stdout ?? ""}${result.stderr ?? ""}`;
    if (result.status !== 0 && stdout.trim() === "") {
        return { ok: false, error: `mw run-detached exited with code ${result.status}` };
    }
    const handle = parseHandoff(stdout);
    if (!handle) {
        return { ok: false, error: `mw run-detached returned an unparsable handoff:\n${stdout.trim()}` };
    }
    return { ok: true, handle };
}
/**
 * Register the `mw_run_detached` tool (design D-005, AC-008). Called from
 * BOTH activate paths — pmActivate and workerModeActivate (the
 * registerRagTools precedent) — so PM and worker windows can dispatch
 * background commands. Worker visibility is decided by the `activeToolsForType`
 * allowlist gate (shell roles only); this registration is structural and
 * unconditional. `controlRoot` is the default working directory for the
 * dispatched command when the caller does not pass `cwd`.
 */
export function registerRunDetachedTool(pi, controlRoot) {
    pi.registerTool({
        name: MW_RUN_DETACHED_TOOL,
        label: "mw_run_detached",
        description: "Dispatch a background command via `python mw.py run-detached -- <cmd...>`: a hidden-console " +
            "supervisor runs the argv (no shell) while this call returns immediately with the evidence " +
            "paths. Poll marker.json for the exit code (`rc`, `timed_out`) and read run.log for output; " +
            "heartbeat.json mtime advances while the command is alive.",
        promptGuidelines: [
            "cmd is the full argv after `--` (verbatim, no shell interpretation). A missing mw.py / " +
                "spawn failure / unparsable handoff fails open with an error object, never a crash.",
            "timeout_min kills the command tree (marker rc=124, timed_out=true); heartbeat_s controls " +
                "the heartbeat.json write interval.",
            "cwd defaults to the current project dir; run_dir defaults to <cwd>/.mw/runs/run-<timestamp>.",
        ],
        parameters: Type.Object({
            cmd: Type.Array(Type.String({ minLength: 1 }), {
                minItems: 1,
                description: "Command argv after `--` (verbatim, no shell).",
            }),
            cwd: Type.Optional(Type.String({ description: "Working dir for the command (default: current project dir)." })),
            run_dir: Type.Optional(Type.String({ description: "Evidence run dir (default: <cwd>/.mw/runs/run-<timestamp>)." })),
            timeout_min: Type.Optional(Type.Number({
                ...POSITIVE_DURATION,
                description: "Kill the command tree after N minutes (must be > 0).",
            })),
            heartbeat_s: Type.Optional(Type.Number({
                ...POSITIVE_DURATION,
                description: "Heartbeat write interval in seconds, > 0 (default 5).",
            })),
        }, { additionalProperties: false }),
        execute: async (_toolCallId, params) => {
            const result = runDetachedMw({
                cmd: params.cmd,
                cwd: params.cwd ?? controlRoot,
                run_dir: params.run_dir,
                timeout_min: params.timeout_min,
                heartbeat_s: params.heartbeat_s,
            });
            if (!result.ok) {
                // Throw so the failure surfaces as a tool error ([TOOL_ERR] in
                // worker mode) — the worker_file/rag precedent.
                throw new Error(result.error);
            }
            const { pid, marker, heartbeat, log } = result.handle;
            return {
                content: [
                    {
                        type: "text",
                        text: `dispatched pid=${pid} marker=${marker} heartbeat=${heartbeat} log=${log}`,
                    },
                ],
                details: { pid, marker, heartbeat, log },
            };
        },
    });
}
//# sourceMappingURL=run-detached.js.map