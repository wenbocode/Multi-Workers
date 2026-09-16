/** Worker heartbeat cadence (design D-003). 30s keeps a 2x margin under the
 * 60s AC-003 ceiling while limiting trace.log growth (~120 lines/hour). */
export declare const HEARTBEAT_INTERVAL_MS = 30000;
/** A worker whose last heartbeat is older than this is considered stalled.
 * The watch widget's STALE mark uses this value; mw doctor's worker_liveness
 * uses the same 90s default (packages/multi-workers/mw_common.py) — keep the
 * two in sync when changing either. */
export declare const HEARTBEAT_STALE_MS = 90000;
export interface HeartbeatInfo {
    /** ISO timestamp of the last [HEARTBEAT] line. */
    lastTs: string;
    /** Milliseconds since the last heartbeat (Date.now() - lastTs). */
    ageMs: number;
    /** Completed phase count from the last heartbeat ("2"), or "-" when the
     * task has no phases. */
    phase: string;
    /** Total phase count from the last heartbeat ("3"), or "-" for phaseless. */
    phaseTotal: string;
    /** Total [HEARTBEAT] lines found in trace.log. */
    count: number;
    /** ISO timestamp of the first [HEARTBEAT] line (runtime start). */
    firstTs: string;
}
export interface CheckpointInfo {
    /** ISO timestamp of the [CHECKPOINT] line. */
    ts: string;
    /** Elapsed seconds at checkpoint time. */
    elapsedS: number;
    /** Read-ish tool calls so far (read/grep/find/ls/glob). */
    reads: number;
    /** Write-ish tool calls so far (write/edit). */
    writes: number;
    /** Phase completion ("1/3"), "-" for phaseless tasks. */
    phases: string;
    /** Unique write/edit targets so far. */
    uniqTargets: number;
    /** Highest per-target repeat count for reads. */
    repeatTop: number;
    /** Machine divergence heuristic (advisory — the PM decides). */
    risk: "low" | "mid" | "high";
}
/** Structured progress parsed from a worker task's trace.log: lifecycle
 * ([START]/[END] — exact runtime + exit status), the last [TOOL] action, the
 * last convergence [CHECKPOINT], and the heartbeat state. Written by
 * worker-mode; consumed by the watch widget, terminal summaries, and the PM
 * divergence escalation. */
export interface TaskProgress {
    /** Heartbeat state; undefined when trace.log has no [HEARTBEAT] lines. */
    heartbeat: HeartbeatInfo | undefined;
    /** ISO timestamp of the [START] line, when present. */
    startTs: string | undefined;
    /** ISO timestamp of the [END] line, when present (terminal tasks). */
    endTs: string | undefined;
    /** Exit code from the [END] line (0/1/2/130). */
    exitCode: number | undefined;
    /** Phase completion from [END] ("2/3"), "-" for phaseless tasks. */
    endPhases: string | undefined;
    /** Task runtime in ms: endTs-startTs once terminal, now-startTs while
     * running. Undefined without a [START] line (old bundles). */
    elapsedMs: number | undefined;
    /** Last [TOOL] action ("<tool> <target>"), e.g. "read src/index.ts". */
    lastAction: string | undefined;
    /** Last convergence checkpoint, when the task ran past the checkpoint
     * time (new bundles; undefined on old bundles / short tasks). */
    checkpoint: CheckpointInfo | undefined;
}
/** Human-readable age for heartbeat display: "15s", "3m", "2h". Shared by
 * the watch widget's `hb` field and terminal-summary runtime stats. */
export declare function formatHeartbeatAge(ms: number): string;
/** Parse the full progress state from a worker task's trace.log. Returns
 * undefined when trace.log is absent or unreadable; individual fields stay
 * undefined when their line types are missing (old bundles wrote only
 * [FLOW]/[HEARTBEAT]/[GOAL_CHECK] lines). */
export declare function readTaskProgress(taskDir: string): TaskProgress | undefined;
/** Parse heartbeat state from a worker task's trace.log (last line wins).
 * Returns undefined when the file exists but carries no [HEARTBEAT] lines
 * (old bundles, pre-start) or when trace.log is absent/unreadable. */
export declare function readHeartbeatInfo(taskDir: string): HeartbeatInfo | undefined;
//# sourceMappingURL=heartbeat.d.ts.map