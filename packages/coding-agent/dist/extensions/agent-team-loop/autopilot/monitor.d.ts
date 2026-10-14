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
 *      errors (transient rename/lock races) no longer drop the frame: the
 *      tick emits a DEGRADED frame that reuses the last good payload and
 *      carries the failure time + summary (AC-017/D-018). Every frame also
 *      self-attests its freshness with an absolute collection stamp plus a
 *      monotonic tick count, and the header raises STALE PANEL once the
 *      stamp has not moved for more than PANEL_STALE_MISSED_CYCLES periods
 *      (AC-015/D-017). The `apply` callback is injected by console.ts (it
 *      wraps ctx.ui.setWidget), so this module holds no pi dependency —
 *      that is the test seam.
 *
 * PURE READ-ONLY (AC-008): no fs write API anywhere in this file; the
 * on/off state lives only in module memory (AC-009), never in config.json.
 */
import * as fs from "node:fs";
import { type WorkerEntry } from "../shared/worker-store.ts";
import { type BlockerClass, type ConfigResult, type GateReason, type RoadmapResult, type TimelineEvent } from "./status-model.ts";
/** Widget id for the monitor panel (the watch widget is
 * "agent-team-loop-watch" — the two coexist, D-003). */
export declare const MONITOR_WIDGET_ID = "agent-team-loop-monitor";
/** Poll cadence — the same 4s beat as the watch widget (spec §2.2). */
export declare const MONITOR_INTERVAL_MS = 4000;
/** G4 AC-015: how many refresh periods the frame stamp may sit still before
 * the header must say STALE PANEL. AC-015 fixes the bound at "more than 3
 * refresh periods". This is the panel-cadence instance of the conductor's
 * `staleAfterMs = max(30s, pollMs*5)` / `tickStale` mechanism (a small
 * multiple of the observed cadence) — deliberately not a re-use of that
 * variable's VALUE, because the conductor beat and the panel refresh are
 * separate clocks. */
export declare const PANEL_STALE_MISSED_CYCLES = 3;
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
    /** Auto-decision kill switch (`auto_gate_mode`: off|shadow|live, T-03).
     * Optional on hand-built snapshots; absent renders as `off`. */
    autoMode?: string;
}
/** One running queue row plus its panel-computed age. The full
 * {@link WorkerEntry} is carried so slot ownership is decided by the canonical
 * predicate ({@link workerBelongsToKey} / {@link workerOwnerKey}) — never by
 * the `ap-` task-key prefix, which is a false signal on its own (AC-021). */
export interface MonitorWorker extends WorkerEntry {
    elapsedMs: number;
}
export interface MonitorGate {
    id: string;
    kind: string;
    stage: number | null;
    /** Owning key (empty for stage-level gates) — the stalled-gate recovery
     * hint needs it to point at the right key. */
    key: string;
    /** `created_at` verbatim (null only when absent/unparsable) — without it
     * the panel cannot show the gate's age (AC-012). Optional so hand-built
     * snapshots stay constructible. */
    createdAt?: string | null;
    /** Age in ms at collect time (null when created_at is unknown). */
    ageMs?: number | null;
    /** `reason_code` verbatim when present — never derived from `question`. */
    reasonCode?: string | null;
    /** Evidence pointers (`evidence_refs`) — the drift input. */
    evidenceRefs?: string[];
    /** `DRIFT(...)` detail when an evidence mtime is newer than created_at. */
    drift?: string | null;
    /** AC-003 suppression reason derived from disk, or null when the gate is
     * due (the renderer then prints `reason=-`, never an empty value).
     * Optional so hand-built snapshots stay constructible. */
    reason?: GateReason | null;
    /** True when the gate's scope (stage/key + created_at) resolved against the
     * roadmap; false renders the orthogonal `unresolved-scope` marker. */
    scopeResolved?: boolean;
    /** `phase:"remind"` ledger rows for this gate (cap-axis input, AC-003). */
    reminders?: number;
    /** `gate_reminder_max` at collect time. */
    reminderMax?: number;
    /** T-14b: the RAW `blocker_class` value from the frontmatter line scan, or
     * `null` when the line is absent or blank (same shape as `reasonCode` — the
     * loose scan carries no field-presence bit). The parser never folds: the
     * `judgment` fold is applied at render time through {@link blockerClassOf},
     * the same function `status-model.ts` uses, so the two surfaces cannot
     * disagree about an unclassified (v1 legacy) gate. */
    blockerClass?: string | null;
}
/** Gate-queue readability (AC-003 `gate-queue-unreadable`). `ok` = the whole
 * directory scan succeeded (an absent gates directory is a legitimately empty
 * queue); `partial` = the directory read but at least one gate file did not;
 * `unreadable` = the directory scan itself failed. The old code degraded every
 * failure to "0 pending", which printed "no gates" for "cannot read gates". */
export type MonitorQueueState = "ok" | "partial" | "unreadable";
/** One roadmap stage as the AC-016 main-gate line shows it. */
export interface MonitorStage {
    number: number;
    title: string;
    /** pending | approved | running | closed | closed-human | halted */
    status: string;
    /** The main gate currently blocking per-key dispatch in this stage
     * (stage-confirm / stage-close / stalled / budget-exhausted / goal-change),
     * or null when nothing is pending. `_stage_activation` gates ALL per-key
     * dispatch on a `running` stage (conductor.py:245-247/671). */
    blockerKind: string | null;
    blockerGateId: string | null;
    /** How long the blocking gate has waited (ms), null when unknown. */
    blockerAgeMs: number | null;
    /** Keys frozen by a non-dispatching status (`_DISPATCH_SKIP_STATUSES`:
     * stalled / pending-review) — a freeze is not terminal, so the stage can
     * never close while one exists. */
    frozenKeys: string[];
}
/** The auto-decision kill switch, read raw so the value stays visible even
 * while the TS config mirror does not yet declare `auto_gate_mode` (T-03 owns
 * the key on the Python side). Missing/unreadable config = off. */
export declare function readAutoGateMode(projectDir: string): string;
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
    /** Config key-layer upper bound (AC-005). Same value as `slotsMax`, kept as
     * its own field so the panel can print `cap` independent of the `U/M`
     * summary slot. Optional so hand-built snapshots stay constructible. */
    slotsCap?: number;
    /** This tick's effective key-layer concurrency: `min(cap, |F|)` (AC-005).
     * Optional so hand-built snapshots stay constructible. */
    slotsEffective?: number;
    /** Dependency-frontier size `|F|` (AC-005): running-stage keys whose key
     * status is not dispatch-skipped and whose deps are all satisfied.
     * Optional so hand-built snapshots stay constructible. */
    frontierSize?: number;
    stallTicks: number;
    keys: MonitorKey[];
    stalls: MonitorStall[];
    /** AC-016 stage main-gate rows, derived from the same roadmap parse as
     * `keys`. Optional so hand-built snapshots stay constructible. */
    stages?: MonitorStage[];
    /** key → stage number (two-level gate→stage resolution input, AC-003). */
    stageOfKey?: ReadonlyMap<string, number>;
    /** stage number → roadmap status. */
    stageStatusByNumber?: ReadonlyMap<number, string>;
    /** stage number → title. */
    stageTitleByNumber?: ReadonlyMap<number, string>;
}
export interface MonitorSnapshot {
    serve: MonitorServe;
    conductor: MonitorConductor;
    autopilot: MonitorAutopilot;
    workers: MonitorWorker[];
    gates: MonitorGate[];
    /** AC-003: readability of the gate queue this frame. `unreadable` means the
     * gate list above is NOT "no gates" but "could not read gates" — the panel
     * must say so instead of printing `0 pending`. Optional on hand-built
     * snapshots (absent = `ok`). */
    queueState?: MonitorQueueState;
    /** One-line detail of the queue read failure (per-file for `partial`). */
    queueError?: string | null;
    /** T-21 R-2: per-file failure samples behind `queueState`, so the panel can
     * print a failure COUNT (not just one message). Populated on the same pass as
     * `queueError`; optional on hand-built snapshots (absent = derive one sample
     * from `queueError`). */
    queueFailures?: string[];
    /** G2 AC-007/AC-008 (design D-008/D-009): a pending gate exists AND no
     * non-terminal worker row is in flight — the file-only truth table shared
     * verbatim with the Python reminder (T-07, `blockedOnHuman` in
     * status-model.ts). The third axis ("conductor still ticking") is TS-only
     * and stays render-time: see the `BLOCKED_ON_HUMAN` line in
     * {@link renderMonitorLines}, which also requires `!autopilot.tickStale`. */
    blockedOnHuman: boolean;
    /** G4 AC-015 (D-017): absolute wall-clock ms (`Date.now()`) of the LAST
     * SUCCESSFUL collection behind this frame — NOT a frame-relative age (which
     * is always 0 at render time and therefore proves nothing). A frozen panel
     * stops advancing here, so this is the one in-frame fact that can tell a
     * frozen frame from a live one. Absent on hand-built snapshots. */
    collectedAtMs?: number;
    /** G4 AC-015: monotonic count of successful collections since module load.
     * Never reset by stop()/re-arm (`startMonitor`), so freshness cannot be
     * faked by going back to 0 (D-017). */
    tickCount?: number;
    /** G4 AC-015: the frame's own stamp has not advanced for more than
     * `PANEL_STALE_MISSED_CYCLES` refresh periods ⇒ the header says STALE
     * PANEL. Set by the tick loop, the only place that knows the cadence and
     * the wall clock. */
    stale?: boolean;
    /** G4 AC-015: `no refresh since <iso>, <duration>` when `stale`; rendered
     * verbatim inside the header alert. */
    staleDetail?: string;
    /** G4 AC-017 (D-018): this frame is DEGRADED — the read threw, so the payload
     * is the last good snapshot plus diagnostics (never a dropped frame). */
    degraded?: boolean;
    /** G4 AC-017: wall-clock ms of the failed read that produced this frame. */
    lastErrorAtMs?: number;
    /** G4 AC-017: one-line error summary (`name: message`, capped). */
    lastError?: string;
}
/** Resolve one `evidence_refs` entry (`kind:relpath[#sha][@mtime_ns]`)
 * against the project's `.agenticdoc/` first, then the project root. */
export declare function evidenceFilePath(projectDir: string, ref: string): string | null;
/** Injection seam for readMonitorState (T-21 R-2 tests): the gate-directory
 * scan and the per-file text read are the two failure points that produce
 * `unreadable` / `partial`, and a single unreadable file cannot be constructed
 * portably on every platform (Windows has no chmod-based read denial). Same
 * injection pattern as {@link AutopilotPanelDeps}. */
export interface MonitorStateDeps {
    readGateDir?: (dir: string) => fs.Dirent[];
    readGateText?: (file: string) => string;
}
/** Derive the full monitor snapshot from the file family. Read-only; every
 * individual source degrades to a safe default (missing pid file → not
 * running, missing config → never enabled, missing gates dir → empty queue)
 * instead of throwing — a half-present project still renders a full panel
 * (AC-007). */
export declare function readMonitorState(projectDir: string, nowMs: number, deps?: MonitorStateDeps): MonitorSnapshot;
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
export declare function deriveAutopilotPanel(projectDir: string, nowMs: number, workers: MonitorWorker[], deps?: AutopilotPanelDeps, conductorInflightKeys?: ReadonlySet<string>): MonitorAutopilot;
/** Compact drift marker (`~D` = evidence newer than `created_at`). */
export declare const GATE_DRIFT_MARK = "~D";
/** T-14b compact blocker-class marks. One column of payload (plus the token's
 * leading space) is the entire budget the frozen 110-column contracts leave for
 * an always-present classification, so the class is encoded exactly like the
 * `~D` / `R:*` marks rather than as a `blocker=` field. `judgment` is the
 * {@link blockerClassOf} fold of an absent/blank/out-of-set value, so a v1
 * legacy gate can NEVER render as auto-releasable. */
export declare const GATE_BLOCKER_MARK: Record<BlockerClass, string>;
/** Compact reason codes — the encode half of the table above. */
export declare const GATE_REASON_CODE: Record<string, string>;
/**
 * Render ONE pending gate as a Layer A row (AC-001/AC-012). Pure function of
 * the collected gate + its position in the queue; the encoding table and the
 * fit ladder above are the whole contract. `reason`, age and the `~D` drift
 * mark are always present — only their encoding can change.
 */
export declare function renderPendingGateLine(gate: MonitorGate, index: number, total: number): string;
/**
 * Render the snapshot as the fixed-section panel. Every section is always
 * present (0 running folds to the "workers: 0 running" header, 0 pending to
 * "gates: 0 pending") so the panel's height — and therefore the editor
 * layout — never flickers between ticks (§9). All lines cap at
 * MONITOR_LINE_MAX columns with an ellipsis. The first line is the
 * self-attesting header (see {@link monitorHeaderLine}).
 */
export declare function renderMonitorLines(s: MonitorSnapshot): string[];
export declare function isMonitorActive(): boolean;
/**
 * Start the monitor. Idempotent: already active → true, nothing changes.
 * The FIRST FRAME renders synchronously before this returns (AC-001 with
 * zero ticks), then every `intervalMs` (default 4000ms) the state is
 * re-derived and re-rendered. A read that throws no longer skips the tick: it
 * emits a DEGRADED frame (last good payload + failure time + summary) so a
 * failing panel can never be silently frozen (AC-017). A failure of the widget
 * write itself is not recoverable from here — the next tick retries (re-arming
 * after a session swap is T-12/D-019, not this task).
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