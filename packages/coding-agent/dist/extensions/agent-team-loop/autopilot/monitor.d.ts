/**
 * monitor.ts — the /autopilot monitor panel (autopilot-monitor T-01, design
 * D-001..D-007, AC-001..AC-009).
 *
 * Three responsibilities, one per section below:
 *   1. collect  — readMonitorState: a pure read-only derivation of the
 *      orchestration chain's health (mw serve / conductor / cross-key
 *      running workers / pending gates / autopilot progress) from the file
 *      family alone. Serve data comes from mw-runner (getMwStatus/serveStaleness/readServeMeta
 *      — never re-implemented here); workers come from WorkerStore; the
 *      conductor pid gets the same signal-0 liveness check; gates get a
 *      lightweight frontmatter line scan (D-004) keeping only
 *      `status: pending` rows; autopilot progress (tick freshness, slots,
 *      per-key phase/status, advance failure runs) is derived by
 *      deriveAutopilotPanel from config.json + _roadmap.md +
 *      _index.parallel + a bounded timeline tail (mw-autopilot-stall-feedback
 *      AC-006: a stalled key must be visible here, not only in the timeline).
 *   2. render   — renderMonitorLines: a fixed-section panel (header + serve
 *      + conductor + autopilot + workers + gates, every section always present so the
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
import { type ConfigResult, type RoadmapResult, type TimelineEvent } from "./status-model.ts";
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
    /** Owning key (empty for stage-level gates) — the stalled-gate recovery
     * hint needs it to point at the right key. */
    key: string;
}
/** One roadmap key as the autopilot section shows it (AC-006). */
export interface MonitorKey {
    key: string;
    /** Phase from _index.parallel ("—" when the key has no index row yet). */
    phase: string;
    /** Roadmap key-status (running|done|stalled|closed-legacy|unknown). */
    status: string;
    inFlight: number;
    /** Deps whose status is not terminal — the reason an idle key waits. */
    blockedBy: string[];
}
/** One key's most recent advance failure run (AC-006). */
export interface MonitorStall {
    key: string;
    edge: string;
    count: number;
    primaryClass: string;
    classCounts: Record<string, number>;
    lastError: string;
    ageMs: number | null;
}
/** The autopilot progress section (AC-006/AC-007). */
export interface MonitorAutopilot {
    enabled: boolean;
    everEnabled: boolean;
    tickSeq: number | null;
    tickAgeMs: number | null;
    /** age > max(30s, 5 x poll_interval): the conductor stopped ticking. */
    tickStale: boolean;
    slotsUsed: number;
    slotsMax: number;
    stallTicks: number;
    keys: MonitorKey[];
    stalls: MonitorStall[];
}
export interface MonitorSnapshot {
    serve: MonitorServe;
    conductor: MonitorConductor;
    autopilot: MonitorAutopilot;
    workers: MonitorWorker[];
    gates: MonitorGate[];
}
/** Derive the full monitor snapshot from the file family. Read-only; every
 * individual source degrades to a safe default (missing pid file → not
 * running, missing config → never enabled, missing gates dir → empty queue)
 * instead of throwing — a half-present project still renders a full panel
 * (AC-007). */
export declare function readMonitorState(projectDir: string, nowMs: number): MonitorSnapshot;
/** Bounded tail read of the current timeline file — the TS mirror of
 * autopilot/timeline.py tail_events. Rotated generations are deliberately
 * not consulted (this answers "what just happened") and the window keeps the
 * panel O(window) instead of O(history) on a multi-megabyte timeline. Torn
 * lines are skipped. Never throws: an absent/unreadable file yields []. */
export declare function readTimelineTail(file: string, opts?: {
    maxBytes?: number;
    limit?: number;
}): TimelineEvent[];
export declare function classifyAdvanceFailure(text: string): string;
/** One key's most recent advance failure run from the timeline tail.
 *
 * Mirrors the conductor's watch on purpose, so the panel never reports
 * `recovered` while the guard keeps counting: only a successful advance of
 * the *same* edge ends a run (a neighbouring boundary's success is ignored,
 * exactly as `conductor._advance_failure_streak` skips it). The one
 * deliberate difference is the trailing edge — the panel keeps showing the
 * run that led to a `stalled`/`gate-created` event, which the guard stops at
 * because it decides whether to freeze the key. */
export declare function deriveAdvanceStalls(events: TimelineEvent[], nowMs: number): MonitorStall[];
/** Injection seam for tests (same pattern as startMonitor's readState). */
export interface AutopilotPanelDeps {
    readConfigFile?: (projectDir: string) => ConfigResult;
    readRoadmapFile?: (projectDir: string) => RoadmapResult;
    readIndexPhases?: (projectDir: string) => Map<string, string>;
    readTimeline?: (file: string) => TimelineEvent[];
}
/** Derive the autopilot section from the file family (AC-007: every source
 * degrades to a safe default instead of throwing — a half-present project
 * still renders a full panel). Pure read-only. */
export declare function deriveAutopilotPanel(projectDir: string, nowMs: number, workers: MonitorWorker[], deps?: AutopilotPanelDeps): MonitorAutopilot;
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