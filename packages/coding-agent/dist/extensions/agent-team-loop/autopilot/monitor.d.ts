/**
 * monitor.ts — the /autopilot monitor panel (autopilot-monitor T-01, design
 * D-001..D-007, AC-001..AC-009).
 *
 * Three responsibilities, one per section below:
 *   1. collect  — readMonitorState: a pure read-only derivation of the
 *      orchestration chain's health (mw serve / conductor / cross-key
 *      running workers / pending gates) from the file family alone. Serve
 *      data comes from mw-runner (getMwStatus/serveStaleness/readServeMeta
 *      — never re-implemented here); workers come from WorkerStore; the
 *      conductor pid gets the same signal-0 liveness check; gates get a
 *      lightweight frontmatter line scan (D-004) keeping only
 *      `status: pending` rows.
 *   2. render   — renderMonitorLines: a fixed-section panel (header + serve
 *      + conductor + workers + gates, every section always present so the
 *      panel height never flickers), 110-column truncation, the same
 *      English-label style as the watch widget.
 *   3. lifetime — startMonitor/stopMonitor/isMonitorActive: a module-level
 *      interval singleton (D-001: independent from the watch poll loop,
 *      which is key-scoped). start renders the FIRST FRAME synchronously
 *      (AC-001 met with zero ticks), then re-reads every intervalMs. Read
 *      errors (transient rename/lock races) skip the tick silently — the
 *      panel keeps the last frame (§9). The `apply` callback is injected by
 *      console.ts (it wraps ctx.ui.setWidget), so this module holds no pi
 *      dependency — that is the test seam.
 *
 * PURE READ-ONLY (AC-008): no fs write API anywhere in this file; the
 * on/off state lives only in module memory (AC-009), never in config.json.
 */
/** Widget id for the monitor panel (the watch widget is
 * "agent-team-loop-watch" — the two coexist, D-003). */
export declare const MONITOR_WIDGET_ID = "agent-team-loop-monitor";
/** Poll cadence — the same 4s beat as the watch widget (spec §2.2). */
export declare const MONITOR_INTERVAL_MS = 4000;
export interface MonitorServe {
    running: boolean;
    pid: number | null;
    stale: boolean;
    staleDetail: string;
    /** Uptime in ms (now − start), or null when no start time is known. */
    upMs: number | null;
}
export interface MonitorConductor {
    pid: number | null;
    alive: boolean;
    enabled: boolean;
    paused: boolean;
    /** False while _autopilot/config.json is absent or invalid — autopilot
     * was never enabled (a missing config is not an error, D-110). */
    everEnabled: boolean;
}
export interface MonitorWorker {
    taskKey: string;
    elapsedMs: number;
}
export interface MonitorGate {
    id: string;
    kind: string;
    stage: number | null;
}
export interface MonitorSnapshot {
    serve: MonitorServe;
    conductor: MonitorConductor;
    workers: MonitorWorker[];
    gates: MonitorGate[];
}
/** Derive the full monitor snapshot from the file family. Read-only; every
 * individual source degrades to a safe default (missing pid file → not
 * running, missing config → never enabled, missing gates dir → empty queue)
 * instead of throwing — a half-present project still renders a full panel
 * (AC-007). */
export declare function readMonitorState(projectDir: string, nowMs: number): MonitorSnapshot;
/**
 * Render the snapshot as the fixed-section panel. Every section is always
 * present (0 running folds to the "workers: 0 running" header, 0 pending to
 * "gates: 0 pending") so the panel's height — and therefore the editor
 * layout — never flickers between ticks (§9). All lines cap at
 * MONITOR_LINE_MAX columns with an ellipsis.
 */
export declare function renderMonitorLines(s: MonitorSnapshot): string[];
export declare function isMonitorActive(): boolean;
/**
 * Start the monitor. Idempotent: already active → true, nothing changes.
 * The FIRST FRAME renders synchronously before this returns (AC-001 with
 * zero ticks), then every `intervalMs` (default 4000ms) the state is
 * re-derived and re-rendered. A read that throws (transient file race)
 * skips that tick silently — the panel keeps the previous frame and the
 * next tick retries.
 */
export declare function startMonitor(projectDir: string, apply: (lines: string[] | undefined) => void, opts?: {
    intervalMs?: number;
    readState?: typeof readMonitorState;
    nowMs?: () => number;
}): boolean;
/**
 * Stop the monitor. Idempotent: not active → false, nothing happens (the
 * widget is NOT cleared in that case). When active, clears the interval and
 * calls `apply(undefined)` — clearing the widget — using the passed callback
 * or the one captured at start.
 */
export declare function stopMonitor(apply?: (lines: string[] | undefined) => void): boolean;
//# sourceMappingURL=monitor.d.ts.map