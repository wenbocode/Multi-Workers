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
import * as path from "node:path";
import { IndexStore } from "../shared/index-store.js";
import { getMwStatus, readServeMeta, serveStaleness } from "../shared/mw-runner.js";
import { WorkerStore, workerBelongsToKey, workerOwnerKey } from "../shared/worker-store.js";
import { BEAT_EV, blockedOnHuman, blockerClassOf, configPath, DEFAULT_CONFIG, deriveGateReason, GATE_SCOPE_UNRESOLVED, gatesDir, isStageTerminal, readConfig, readGateReminders, readRoadmap, reminderCountForGate, TERMINAL_WORKER_STATUSES, timelinePath, } from "./status-model.js";
/** Widget id for the monitor panel (the watch widget is
 * "agent-team-loop-watch" — the two coexist, D-003). */
export const MONITOR_WIDGET_ID = "agent-team-loop-monitor";
/** Poll cadence — the same 4s beat as the watch widget (spec §2.2). */
export const MONITOR_INTERVAL_MS = 4000;
/** G4 AC-015: how many refresh periods the frame stamp may sit still before
 * the header must say STALE PANEL. AC-015 fixes the bound at "more than 3
 * refresh periods". This is the panel-cadence instance of the conductor's
 * `staleAfterMs = max(30s, pollMs*5)` / `tickStale` mechanism (a small
 * multiple of the observed cadence) — deliberately not a re-use of that
 * variable's VALUE, because the conductor beat and the panel refresh are
 * separate clocks. */
export const PANEL_STALE_MISSED_CYCLES = 3;
/** Panel line width cap (same as the watch widget's WATCH_LINE_MAX). */
const MONITOR_LINE_MAX = 110;
/** `conductor.py::_DISPATCH_SKIP_STATUSES` mirror: a key in one of these key
 * statuses is never dispatched this tick, so it can never be on the
 * dependency frontier (AC-005). */
const DISPATCH_SKIP_STATUSES = new Set(["done", "stalled", "closed-legacy", "pending-review"]);
/** `conductor.py::_DEP_SATISFIED` mirror: only these dependency statuses
 * release a downstream key. */
const DEP_SATISFIED_STATUSES = new Set(["done", "closed-legacy"]);
/** The auto-decision kill switch, read raw so the value stays visible even
 * while the TS config mirror does not yet declare `auto_gate_mode` (T-03 owns
 * the key on the Python side). Missing/unreadable config = off. */
export function readAutoGateMode(projectDir) {
    try {
        const parsed = JSON.parse(fs.readFileSync(configPath(projectDir), "utf8"));
        if (typeof parsed === "object" && parsed !== null) {
            const mode = parsed.auto_gate_mode;
            if (mode === "off" || mode === "shadow" || mode === "live")
                return mode;
        }
    }
    catch {
        // missing/invalid config — autopilot never enabled
    }
    return "off";
}
// ── Collect: readMonitorState (pure, read-only) ──────────────────────────────
/** Parse one gate file's frontmatter text for the fields the panel needs
 * (D-004 line scan — no YAML dependency). Returns the gate only when it is
 * `status: pending` with a usable id/kind; anything else (answered gates,
 * non-gate or unparsable files) is skipped. Also captures `created_at`,
 * `reason_code` and `evidence_refs` so the panel can show age/reason and
 * compute the evidence-drift marker (AC-012). Reading the file is the
 * caller's job now, so a read failure can be surfaced as
 * `gate-queue-unreadable` instead of silently dropping the gate (AC-003). */
function parsePendingGateText(text) {
    const lines = text.split(/\r\n|\r|\n/);
    if (lines.length === 0 || lines[0].trim() !== "---")
        return null;
    let id = "";
    let kind = "";
    let stage = null;
    let key = "";
    let status = "";
    let createdAt = null;
    let reasonCode = null;
    let blockerClass = null;
    const evidenceRefs = [];
    let activeList = null;
    for (let i = 1; i < lines.length; i++) {
        const line = lines[i];
        if (line.trim() === "---")
            break; // frontmatter closed
        if (activeList === "evidence_refs") {
            const item = /^[ \t]+-[ \t]+(.*)$/.exec(line);
            if (item !== null) {
                const ref = (item[1] ?? "").trim().replace(/^'(.*)'$/, "$1");
                if (ref !== "")
                    evidenceRefs.push(ref);
                continue;
            }
            activeList = null; // dedent
        }
        const m = /^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*?)[ \t]*$/.exec(line);
        if (m === null)
            continue; // list items, blank lines, etc.
        const name = m[1] ?? "";
        const value = m[2] ?? "";
        if (name === "id")
            id = value;
        else if (name === "kind")
            kind = value;
        else if (name === "status")
            status = value;
        else if (name === "key")
            key = value;
        else if (name === "stage")
            stage = /^-?\d+$/.test(value) ? Number.parseInt(value, 10) : null;
        else if (name === "created_at")
            createdAt = value === "" ? null : value;
        else if (name === "reason_code")
            reasonCode = value === "" ? null : value;
        // T-14b: same shape as `reason_code` — verbatim when present, blank folds
        // to null (the field's presenceness is kept out of this loose line scan;
        // the closed-set/format checks belong to the strict `parseGateFile`).
        else if (name === "blocker_class")
            blockerClass = value === "" ? null : value;
        else if (name === "evidence_refs") {
            if (value === "") {
                activeList = "evidence_refs";
            }
            else if (value === "[]") {
                activeList = null;
            }
            else if (value.startsWith("'")) {
                // v2 renderer shape: a single-line JSON array substring.
                try {
                    const decoded = JSON.parse(value.replace(/^'/, "").replace(/'$/, "").replaceAll("''", "'"));
                    if (Array.isArray(decoded)) {
                        for (const item of decoded)
                            if (typeof item === "string" && item !== "")
                                evidenceRefs.push(item);
                    }
                }
                catch {
                    // unparsable — drift stays unknown rather than guessing
                }
            }
        }
    }
    if (status !== "pending" || id === "" || kind === "")
        return null;
    return { id, kind, stage, key, createdAt, reasonCode, blockerClass, evidenceRefs, ageMs: null, drift: null };
}
/** Resolve one `evidence_refs` entry (`kind:relpath[#sha][@mtime_ns]`)
 * against the project's `.agenticdoc/` first, then the project root. */
export function evidenceFilePath(projectDir, ref) {
    const body = ref.replace(/^[^:]*:/, "");
    const rel = body.split("#")[0].split("@")[0] ?? "";
    if (rel === "")
        return null;
    const underAgenticdoc = path.join(projectDir, ".agenticdoc", rel);
    if (fs.existsSync(underAgenticdoc))
        return underAgenticdoc;
    const underRoot = path.join(projectDir, rel);
    return fs.existsSync(underRoot) ? underRoot : null;
}
/** `DRIFT(...)` detail when the newest evidence mtime is newer than the gate's
 * created_at, else null. Never throws: an unstattable ref is skipped. */
function gateDriftDetail(projectDir, gate, createdAtMs) {
    if (createdAtMs === null || gate.evidenceRefs === undefined || gate.evidenceRefs.length === 0)
        return null;
    let newestMs = Number.NEGATIVE_INFINITY;
    for (const ref of gate.evidenceRefs) {
        const file = evidenceFilePath(projectDir, ref);
        if (file === null)
            continue;
        try {
            const mtimeMs = fs.statSync(file).mtimeMs;
            if (mtimeMs > newestMs)
                newestMs = mtimeMs;
        }
        catch {
            // transient stat race — skip this ref
        }
    }
    if (!Number.isFinite(newestMs) || newestMs <= createdAtMs)
        return null;
    // Compact by design: the panel only flags the drift; the full mtime pair
    // lives in the /autopilot gates card (L6) and `mw doctor`.
    return "mtime>created_at";
}
/** Derive the full monitor snapshot from the file family. Read-only; every
 * individual source degrades to a safe default (missing pid file → not
 * running, missing config → never enabled, missing gates dir → empty queue)
 * instead of throwing — a half-present project still renders a full panel
 * (AC-007). */
export function readMonitorState(projectDir, nowMs, deps) {
    // serve — mw-runner owns the pid-file liveness + staleness logic.
    const status = getMwStatus(projectDir);
    let serve = { running: false, pid: null, stale: false, staleDetail: "", upMs: null };
    if (status.running) {
        const staleness = serveStaleness(projectDir);
        // Serve start: serve.meta first, mw.pid mtime as the pre-meta fallback.
        let startedAtMs = readServeMeta(projectDir)?.startedAtMs ?? null;
        if (startedAtMs === null) {
            try {
                startedAtMs = fs.statSync(path.join(projectDir, ".mw", "mw.pid")).mtimeMs;
            }
            catch {
                startedAtMs = null;
            }
        }
        serve = {
            running: true,
            pid: status.pid,
            stale: staleness?.stale ?? false,
            staleDetail: staleness?.detail ?? "",
            upMs: startedAtMs === null ? null : Math.max(0, nowMs - startedAtMs),
        };
    }
    // conductor — pid file + signal-0 liveness (same technique as getMwStatus);
    // intent (enabled/paused) from config.json, whose absence means "never
    // enabled", never an error.
    let conductorPid = null;
    let conductorAlive = false;
    try {
        const raw = fs.readFileSync(path.join(projectDir, ".mw", "conductor.pid"), "utf8").trim();
        const parsed = Number.parseInt(raw, 10);
        if (!Number.isNaN(parsed)) {
            conductorPid = parsed;
            try {
                process.kill(parsed, 0);
                conductorAlive = true;
            }
            catch {
                conductorAlive = false;
            }
        }
    }
    catch {
        // no/unreadable conductor pid file — nothing is running
    }
    let everEnabled = false;
    let enabled = false;
    let paused = false;
    if (fs.existsSync(configPath(projectDir))) {
        const cfg = readConfig(projectDir);
        if (cfg.ok) {
            everEnabled = true;
            enabled = cfg.config.enabled;
            paused = cfg.config.paused;
        }
    }
    const conductor = {
        pid: conductorPid,
        alive: conductorAlive,
        enabled,
        paused,
        everEnabled,
        autoMode: readAutoGateMode(projectDir),
    };
    // workers — every running row across ALL keys (system-scoped, unlike the
    // key-scoped watch widget), elapsed from dispatchedAt; rows with an
    // unparsable dispatchedAt are dropped rather than shown wrong.
    const workers = [];
    let nonTerminalRows = 0;
    // Non-terminal rows per owning key — the AC-003 `key-in-flight` axis. Unlike
    // the `workers` list below (running only) this keeps `pending` rows in, the
    // same non-terminal set `_is_in_flight` uses on the Python side.
    const nonTerminalByKey = new Map();
    // AC-012 / D-106: the `slotsUsed` source of truth, the SAME predicate the
    // conductor's `_is_in_flight` + `_row_belongs_to` pair applies — non-terminal
    // (so `pending` counts) AND origin=conductor AND a `.agenticdoc/<key>/` path
    // owner (so `manual`/legacy rows own no slot). Built here where the full row
    // set is read, because `workers` below is running-only.
    const conductorInflightKeys = new Set();
    for (const entry of new WorkerStore(path.join(projectDir, ".agenticdoc")).readAll()) {
        // In-flight means NON-TERMINAL, not merely `running`: a `pending` row
        // starts on the next tick, so counting it prevents a false
        // BLOCKED_ON_HUMAN (design D-008/F6, same set as _TERMINAL_STATUSES).
        if (!TERMINAL_WORKER_STATUSES.has(entry.status)) {
            nonTerminalRows += 1;
            const owner = workerOwnerKey(entry);
            nonTerminalByKey.set(owner, (nonTerminalByKey.get(owner) ?? 0) + 1);
            if (owner !== "" && workerBelongsToKey(entry, owner))
                conductorInflightKeys.add(owner);
        }
        if (entry.status !== "running")
            continue;
        const dispatched = Date.parse(entry.dispatchedAt);
        if (Number.isNaN(dispatched))
            continue;
        workers.push({ ...entry, elapsedMs: Math.max(0, nowMs - dispatched) });
    }
    workers.sort((a, b) => b.elapsedMs - a.elapsedMs || a.taskKey.localeCompare(b.taskKey));
    // gates — pending queue only, seq order (the directory scan is the queue).
    // Age, the evidence-drift marker AND the AC-003 suppression reason are
    // computed HERE (collect) so the renderer stays a pure function of the
    // snapshot. A readdir/readFile failure is NO LONGER folded into "empty
    // queue": it becomes `queueState` so the panel can say
    // `gate-queue-unreadable` instead of lying with `0 pending`.
    const gates = [];
    let queueState = "ok";
    let queueError = null;
    const queueFailures = [];
    const gatesDirectory = gatesDir(projectDir);
    let gateFiles = [];
    try {
        gateFiles = (deps?.readGateDir ?? ((dir) => fs.readdirSync(dir, { withFileTypes: true })))(gatesDirectory);
    }
    catch (err) {
        if (err.code !== "ENOENT") {
            // Directory present but unreadable (EACCES/EPERM/EBUSY/ENOTDIR...). An
            // absent directory is a legitimately empty queue; anything else is
            // not "no gates" and must be said out loud (AC-003).
            queueState = "unreadable";
            queueFailures.push(errorSummary(err));
            queueError = queueFailures[0];
        }
    }
    const autopilotBase = deriveAutopilotPanel(projectDir, nowMs, workers, undefined, conductorInflightKeys);
    const cfgResult = readConfig(projectDir);
    const reminderMax = cfgResult.ok ? cfgResult.config.gate_reminder_max : DEFAULT_CONFIG.gate_reminder_max;
    const afterMin = cfgResult.ok ? cfgResult.config.gate_reminder_after_min : DEFAULT_CONFIG.gate_reminder_after_min;
    const reminders = readGateReminders(path.join(projectDir, ".agenticdoc"));
    if (queueState === "ok") {
        for (const entry of gateFiles) {
            if (!entry.isFile() || !/^gate-\d+\.md$/.test(entry.name))
                continue;
            const file = path.join(gatesDirectory, entry.name);
            let text;
            try {
                text = (deps?.readGateText ?? ((f) => fs.readFileSync(f, "utf8")))(file);
            }
            catch (err) {
                queueState = "partial";
                // T-21 R-2: keep EVERY failure sample (the old code overwrote the
                // message per file, so a count was impossible) and re-derive the
                // summary from the samples, so "n unreadable" is truthful.
                queueFailures.push(`${entry.name}: ${errorSummary(err)}`);
                queueError = formatQueueFailures(queueFailures);
                continue;
            }
            const gate = parsePendingGateText(text);
            if (gate === null)
                continue;
            const createdMs = gate.createdAt === null || gate.createdAt === undefined ? null : Date.parse(gate.createdAt);
            const createdKnown = createdMs !== null && !Number.isNaN(createdMs) ? createdMs : null;
            gate.ageMs = createdKnown === null ? null : Math.max(0, nowMs - createdKnown);
            gate.drift = gateDriftDetail(projectDir, gate, createdKnown);
            // Two-level scope resolution, exactly like conductor.pending_gate_reminders:
            // the gate's own `stage` snapshot first, then `stage_of_key` on its key.
            const stageOfKey = autopilotBase.stageOfKey;
            const resolvedStage = gate.stage !== null ? gate.stage : gate.key !== "" ? (stageOfKey?.get(gate.key) ?? null) : null;
            const stageStatus = resolvedStage === null ? undefined : autopilotBase.stageStatusByNumber?.get(resolvedStage);
            gate.scopeResolved =
                createdKnown !== null &&
                    (gate.stage !== null
                        ? autopilotBase.stageStatusByNumber?.has(gate.stage) === true
                        : gate.key !== ""
                            ? stageOfKey?.has(gate.key) === true
                            : false);
            const remindersForGate = reminderCountForGate(reminders, gate.id);
            gate.reminders = remindersForGate;
            gate.reminderMax = reminderMax;
            const thresholdMs = (remindersForGate + 1) * afterMin * 60_000;
            const due = createdKnown === null ? null : nowMs - createdKnown >= thresholdMs;
            gate.reason = deriveGateReason({
                queueUnreadable: false,
                inFlightForKey: gate.key === "" ? 0 : (nonTerminalByKey.get(gate.key) ?? 0),
                reminders: remindersForGate,
                reminderMax,
                stageTerminal: isStageTerminal(stageStatus),
                due,
            });
            gates.push(gate);
        }
    }
    gates.sort((a, b) => a.id.localeCompare(b.id));
    // AC-016 stage main-gate rows: `_stage_activation` returns True (and thus
    // releases per-key dispatch) only when a stage is `running`; every other
    // status stalls the whole tick. The rows below are the direct answer.
    const autopilot = {
        ...autopilotBase,
        stages: deriveMonitorStages(autopilotBase, gates),
    };
    // G2 AC-007 (D-008): the file-only truth table, shared verbatim with the
    // Python reminder (T-07). Collected once here; the renderer adds the
    // TS-only third axis (`!tickStale`) on top. The per-key axis (T-10/D2) is
    // wired by T-11 in this caller; T-10 owns the derivation in status-model.ts.
    const blocked = blockedOnHuman(gates.length, nonTerminalRows, {
        gateKeys: gates.map((g) => g.key),
        nonTerminalByKey,
    });
    // G4 AC-015 (D-017): stamp the frame here so ANY caller of readMonitorState
    // gets a self-attesting snapshot; startMonitor then advances `tickCount`
    // and re-stamps `collectedAtMs` with its own (possibly injected) clock.
    return {
        serve,
        conductor,
        autopilot,
        workers,
        gates,
        queueState,
        queueError,
        queueFailures,
        blockedOnHuman: blocked,
        collectedAtMs: nowMs,
        tickCount: monitorTickCount,
    };
}
/** Gate kinds that can hold the stage main gate, most-specific first (AC-016).
 * `stage-confirm` blocks the START of a stage, `stage-close`/`stalled`/
 * `budget-exhausted` block its COMPLETION, `goal-change` halts the project. */
const STAGE_BLOCKER_KINDS = ["stage-confirm", "stage-close", "stalled", "budget-exhausted", "goal-change"];
/** AC-016: one row per roadmap stage — status + the gate it is stuck on + how
 * long + the frozen key list. Pure function of the already-collected payload.
 * A `halted` stage renders as its own blocker (no gate can release it: only a
 * human roadmap edit can, conductor.py `_stage_activation`). */
function deriveMonitorStages(autopilot, gates) {
    const statusByNumber = autopilot.stageStatusByNumber ?? new Map();
    const stageOfKey = autopilot.stageOfKey ?? new Map();
    const goalChangeGate = gates.find((g) => g.kind === "goal-change");
    const statuses = [...statusByNumber.entries()].sort((a, b) => a[0] - b[0]);
    return statuses.map(([number, status]) => {
        const frozenKeys = autopilot.keys
            .filter((k) => k.status === "stalled" || k.status === "pending-review")
            .filter((k) => stageOfKey.get(k.key) === number)
            .map((k) => k.key)
            .sort();
        const candidates = gates.filter((g) => {
            const resolved = g.stage !== null ? g.stage : g.key !== "" ? (stageOfKey.get(g.key) ?? null) : null;
            return resolved === number;
        });
        // A pending goal-change gate halts every non-terminal stage project-wide
        // (conductor.py `open_goal_change_gate`), so it is a candidate everywhere.
        if (goalChangeGate !== undefined && status !== "closed" && status !== "closed-human") {
            candidates.push(goalChangeGate);
        }
        candidates.sort((a, b) => STAGE_BLOCKER_KINDS.indexOf(a.kind) - STAGE_BLOCKER_KINDS.indexOf(b.kind));
        const blocker = candidates[0];
        return {
            number,
            title: autopilot.stageTitleByNumber?.get(number) ?? "",
            status,
            blockerKind: blocker?.kind ?? (status === "halted" ? "halted" : null),
            blockerGateId: blocker?.id ?? null,
            blockerAgeMs: blocker?.ageMs ?? null,
            frozenKeys,
        };
    });
}
// ── Autopilot progress: deriveAutopilotPanel (AC-006/AC-007) ──────────────────
/** Bounded tail read of the current timeline file — the TS mirror of
 * autopilot/timeline.py tail_events. Rotated generations are deliberately
 * not consulted (this answers "what just happened") and the window keeps the
 * panel O(window) instead of O(history) on a multi-megabyte timeline. Torn
 * lines are skipped. Never throws: an absent/unreadable file yields []. */
export function readTimelineTail(file, opts) {
    const maxBytes = opts?.maxBytes ?? 512 * 1024;
    const limit = opts?.limit ?? 400;
    let fd;
    try {
        fd = fs.openSync(file, "r");
    }
    catch {
        return [];
    }
    try {
        const size = fs.fstatSync(fd).size;
        if (size <= 0)
            return [];
        const start = Math.max(0, size - maxBytes);
        const buf = Buffer.alloc(size - start);
        fs.readSync(fd, buf, 0, buf.length, start);
        let lines = buf.toString("utf8").split("\n");
        if (start > 0)
            lines = lines.slice(1); // the window cut the first line
        const events = [];
        for (const line of lines) {
            const trimmed = line.trim();
            if (trimmed === "")
                continue;
            let parsed;
            try {
                parsed = JSON.parse(trimmed);
            }
            catch {
                continue;
            }
            if (typeof parsed !== "object" || parsed === null)
                continue;
            const ev = parsed;
            if (typeof ev.seq !== "number")
                continue;
            events.push({
                ts: typeof ev.ts === "string" ? ev.ts : "",
                seq: ev.seq,
                ev: typeof ev.ev === "string" ? ev.ev : "",
                key: typeof ev.key === "string" ? ev.key : "-",
                stage: typeof ev.stage === "number" ? ev.stage : null,
                detail: typeof ev.detail === "string" ? ev.detail : "",
            });
        }
        return limit > 0 && events.length > limit ? events.slice(-limit) : events;
    }
    catch {
        return [];
    }
    finally {
        fs.closeSync(fd);
    }
}
/** Event `detail` shape for one advance attempt (conductor
 * _record_advance_result): `{edge} exit={n}[ class={cls}]`. */
const ADVANCE_DETAIL_RE = /^(\S+) exit=(\d+)(?: class=(\S+))?$/;
/** Failure classes — markers identical to autopilot/conductor.py
 * _classify_advance_failure (one contract, two implementations). */
const INTERFACE_DRIFT_MARKERS = [
    "unknown phase",
    "valid: spec",
    "phase-line",
    "phase field",
    "unsupported framework",
    "framework version",
];
const GATE_BLOCKED_MARKERS = [
    "gate blocked",
    "gate fail",
    "missing:",
    "missing prerequisite",
    "缺少",
    "not met",
    "未满足",
];
const TIMEOUT_ENV_MARKERS = ["timeout", "timed out", "locate", "advanceerror", "no such file", "cannot find"];
export function classifyAdvanceFailure(text) {
    const low = text.toLowerCase();
    if (INTERFACE_DRIFT_MARKERS.some((m) => low.includes(m)))
        return "interface-drift";
    if (GATE_BLOCKED_MARKERS.some((m) => low.includes(m)))
        return "gate-blocked";
    if (TIMEOUT_ENV_MARKERS.some((m) => low.includes(m)))
        return "timeout-env";
    return "other";
}
/** One key's most recent advance failure run from the timeline tail.
 *
 * Mirrors the conductor's watch on purpose, so the panel never reports
 * `recovered` while the guard keeps counting: only a successful advance of
 * the *same* edge ends a run (a neighbouring boundary's success is ignored,
 * exactly as `conductor._advance_failure_streak` skips it). The one
 * deliberate difference is the trailing edge — the panel keeps showing the
 * run that led to a `stalled`/`gate-created` event, which the guard stops at
 * because it decides whether to freeze the key. */
export function deriveAdvanceStalls(events, nowMs) {
    const active = new Map();
    const cleared = new Set();
    const pendingError = new Map();
    for (let i = events.length - 1; i >= 0; i--) {
        const ev = events[i];
        if (ev === undefined)
            continue;
        const key = ev.key;
        if (key === "" || key === "-")
            continue;
        if (ev.ev === "config") {
            if (!pendingError.has(key) && ev.detail.includes("advance")) {
                pendingError.set(key, ev.detail
                    .slice(ev.detail.indexOf(":") + 1)
                    .trim()
                    .slice(0, 120));
            }
            continue;
        }
        if (ev.ev !== "advance")
            continue;
        const m = ADVANCE_DETAIL_RE.exec(ev.detail);
        if (m === null)
            continue;
        const edge = m[1] ?? "";
        if (cleared.has(`${key}|${edge}`))
            continue;
        const exitCode = Number.parseInt(m[2] ?? "0", 10);
        if (exitCode === 0) {
            // Only this edge's own success ends its run (the conductor skips a
            // different edge's advance entirely); older same-edge failures are
            // then skipped via `cleared`, so two boundaries never merge.
            const activeEntry = active.get(key);
            if (activeEntry !== undefined && activeEntry.edge === edge)
                active.delete(key);
            cleared.add(`${key}|${edge}`);
            continue;
        }
        const acc = active.get(key);
        if (acc !== undefined) {
            if (acc.edge !== edge)
                continue; // another boundary's failures
            acc.count += 1;
            const cls = m[3] ?? classifyAdvanceFailure(acc.lastError);
            acc.classes[cls] = (acc.classes[cls] ?? 0) + 1;
            continue;
        }
        const lastError = pendingError.get(key) ?? "";
        const cls = m[3] ?? classifyAdvanceFailure(lastError);
        active.set(key, { edge, count: 1, classes: { [cls]: 1 }, lastError, newestTs: ev.ts });
    }
    const stalls = [];
    for (const [key, acc] of active) {
        const ranked = Object.entries(acc.classes).sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
        const parsed = Date.parse(acc.newestTs);
        stalls.push({
            key,
            edge: acc.edge,
            count: acc.count,
            primaryClass: ranked[0]?.[0] ?? "other",
            classCounts: acc.classes,
            lastError: acc.lastError,
            ageMs: Number.isNaN(parsed) ? null : Math.max(0, nowMs - parsed),
        });
    }
    stalls.sort((a, b) => b.count - a.count || a.key.localeCompare(b.key));
    return stalls;
}
function defaultIndexPhases(projectDir) {
    try {
        const entries = new IndexStore(path.join(projectDir, ".agenticdoc")).readAll();
        return new Map(entries.map((e) => [e.key, e.phase]));
    }
    catch {
        return new Map();
    }
}
/** Derive the autopilot section from the file family (AC-007: every source
 * degrades to a safe default instead of throwing — a half-present project
 * still renders a full panel). Pure read-only. */
export function deriveAutopilotPanel(projectDir, nowMs, workers, deps, conductorInflightKeys) {
    const configResult = (deps?.readConfigFile ?? readConfig)(projectDir);
    const config = configResult.ok ? configResult.config : null;
    const roadmap = (deps?.readRoadmapFile ?? readRoadmap)(projectDir);
    const statusByKey = new Map();
    const depsByKey = new Map();
    const stageOfKey = new Map();
    const stageStatusByNumber = new Map();
    const stageTitleByNumber = new Map();
    if (roadmap.ok) {
        for (const stage of roadmap.stages) {
            stageStatusByNumber.set(stage.number, stage.status);
            stageTitleByNumber.set(stage.number, stage.title);
            for (const [key, status] of Object.entries(stage.keyStatus))
                statusByKey.set(key, status);
            for (const row of stage.keys) {
                depsByKey.set(row.key, row.dependsOn);
                stageOfKey.set(row.key, stage.number);
            }
            // A key-status entry without a keys-table row still resolves its stage
            // (the two-level gate→stage rule reads whatever status facts exist).
            for (const key of Object.keys(stage.keyStatus)) {
                if (!stageOfKey.has(key))
                    stageOfKey.set(key, stage.number);
            }
        }
    }
    const phaseByKey = (deps?.readIndexPhases ?? defaultIndexPhases)(projectDir);
    const events = (deps?.readTimeline ?? ((file) => readTimelineTail(file)))(timelinePath(projectDir));
    let tickSeq = null;
    let tickAgeMs = null;
    for (let i = events.length - 1; i >= 0; i--) {
        const ev = events[i];
        if (ev === undefined || ev.ev !== BEAT_EV)
            continue;
        tickSeq = ev.seq;
        const parsed = Date.parse(ev.ts);
        tickAgeMs = Number.isNaN(parsed) ? null : Math.max(0, nowMs - parsed);
        break;
    }
    const pollMs = (config?.poll_interval_sec ?? DEFAULT_CONFIG.poll_interval_sec) * 1000;
    const staleAfterMs = Math.max(30_000, pollMs * 5);
    const keys = [];
    const allKeys = [...new Set([...statusByKey.keys(), ...phaseByKey.keys()])].sort();
    for (const key of allKeys) {
        keys.push({
            key,
            phase: phaseByKey.get(key) ?? "—",
            status: statusByKey.get(key) ?? "unknown",
            inFlight: workers.filter((w) => workerBelongsToKey(w, key)).length,
            blockedBy: (depsByKey.get(key) ?? []).filter((dep) => !["done", "closed-legacy"].includes(statusByKey.get(dep) ?? "")),
        });
    }
    // AC-005 |F|: the dependency frontier — keys in a `running` stage whose key
    // status is not dispatch-skipped and whose deps are all satisfied. The
    // conductor additionally requires a free claim (`state.read_key_states`),
    // which this view does not read, so the panel's frontier is an
    // over-approximation (`frontierSize >= |F_conductor|`) and `eff` is an
    // upper bound; equation `eff == min(cap, |F|)` holds on the panel's own |F|.
    let frontierSize = 0;
    if (roadmap.ok) {
        for (const stage of roadmap.stages) {
            if (stage.status !== "running")
                continue;
            for (const row of stage.keys) {
                const keyStatus = stage.keyStatus[row.key] ?? "running";
                if (DISPATCH_SKIP_STATUSES.has(keyStatus))
                    continue;
                const depsSatisfied = row.dependsOn.every((dep) => DEP_SATISFIED_STATUSES.has(statusByKey.get(dep) ?? ""));
                if (depsSatisfied)
                    frontierSize += 1;
            }
        }
    }
    const slotsCap = config?.max_parallel_keys ?? DEFAULT_CONFIG.max_parallel_keys;
    // AC-012 / D-106: prefer the caller's conductor-equivalent in-flight set
    // (built from ALL non-terminal rows, so `pending` counts and `manual` does
    // not). Direct callers that pass no set keep the historical running-only
    // worker scan, so the panel degrades to its old value instead of "0".
    const inflightOwners = new Set(conductorInflightKeys ?? []);
    if (conductorInflightKeys === undefined) {
        for (const w of workers) {
            const owner = workerOwnerKey(w);
            if (owner !== "" && workerBelongsToKey(w, owner))
                inflightOwners.add(owner);
        }
    }
    const busyKeys = new Set();
    for (const owner of inflightOwners) {
        if (allKeys.includes(owner))
            busyKeys.add(owner);
    }
    return {
        enabled: config?.enabled ?? false,
        everEnabled: fs.existsSync(configPath(projectDir)) && configResult.ok,
        tickSeq,
        tickAgeMs,
        tickStale: tickAgeMs !== null && tickAgeMs > staleAfterMs,
        slotsUsed: busyKeys.size,
        slotsMax: slotsCap,
        slotsCap,
        slotsEffective: Math.min(slotsCap, frontierSize),
        frontierSize,
        stallTicks: config?.advance_stall_ticks ?? DEFAULT_CONFIG.advance_stall_ticks,
        keys,
        stalls: deriveAdvanceStalls(events, nowMs),
        stageOfKey,
        stageStatusByNumber,
        stageTitleByNumber,
    };
}
// ── Render: renderMonitorLines (pure) ────────────────────────────────────────
function trunc(s, max) {
    return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}
/** T-21 R-2: `gate-0001.md: EACCES` for one failure, `2 files unreadable:
 * gate-0001.md: EACCES; gate-0002.md: EBUSY` for many. The count is always
 * explicit so a truncated line still states HOW MANY gate files are missing. */
function formatQueueFailures(failures) {
    if (failures.length === 1)
        return failures[0];
    return `${failures.length} files unreadable: ${failures.join("; ")}`;
}
/** Failure samples of a partial/unreadable queue frame. Hand-built snapshots
 * that only set `queueError` still get a one-sample list, so the renderer never
 * has to special-case "no structured samples". */
function queueFailureSamples(s) {
    if (s.queueFailures !== undefined && s.queueFailures.length > 0)
        return s.queueFailures;
    if (s.queueError !== null && s.queueError !== undefined && s.queueError !== "")
        return [s.queueError];
    return [];
}
/** "45s", "3m", "2h 3m" — coarse duration (serve uptime, stall age). */
function formatDuration(ms) {
    const s = Math.max(0, Math.floor(ms / 1000));
    if (s < 60)
        return `${s}s`;
    const m = Math.floor(s / 60);
    if (m < 60)
        return `${m}m`;
    return `${Math.floor(m / 60)}h ${m % 60}m`;
}
/** Autopilot intent half of the conductor line. */
function conductorIntent(c) {
    if (!c.enabled)
        return "autopilot disabled";
    return c.paused ? "autopilot enabled, paused" : "autopilot enabled, not paused";
}
/** G4 AC-015 (D-017): the panel header doubles as the frame's
 * self-attestation. It carries the STALE PANEL alert plus the absolute
 * `collected` stamp and monotonic `tick` count. Bits are appended in priority
 * order and truncated/dropped before the alert can be cut away, so a long
 * detail can never hide "STALE PANEL". */
function monitorHeaderLine(s) {
    const bits = [];
    if (s.stale === true)
        bits.push(`STALE PANEL (${s.staleDetail ?? "no refresh"})`);
    if (s.collectedAtMs !== undefined) {
        bits.push(`collected ${new Date(s.collectedAtMs).toISOString()} tick ${s.tickCount ?? 0}`);
    }
    let line = "[autopilot monitor]";
    for (const bit of bits) {
        if (`${line} ${bit}`.length <= MONITOR_LINE_MAX) {
            line = `${line} ${bit}`;
            continue;
        }
        const room = MONITOR_LINE_MAX - line.length - 1;
        if (room > 8)
            line = `${line} ${trunc(bit, room)}`;
        break;
    }
    return line;
}
// ── Gate-line compact encoding (T-10b, AC-001 x AC-012) ──────────────────────
//
// A Layer A gate line must fit MONITOR_LINE_MAX (110) columns while NEVER
// losing three facts: evidence drift (existing AC-012 `DRIFT(` contract), the
// suppression reason (AC-001) and the gate age (AC-001/AC-012). When a
// combination does not fit, the line COMPRESSES those three instead of
// dropping any of them, and drops only secondary fields with a visible
// `+N` trace.
//
// ENCODING TABLE (code -> meaning)
//   Drift (evidence mtime newer than created_at):
//     ~D            drift present (compact mark; replaces the verbose
//                   `DRIFT(mtime>created_at)` form — never dropped)
//   Reason (deriveGateReason / GateReason -> compact code):
//     R:queue       gate-queue-unreadable
//     R:flight      key-in-flight
//     R:cap         cap-reached
//     R:term        stage-terminal
//     R:notdue      not-due
//     R:scope       unresolved-scope (orthogonal scope marker)
//     R:due         no suppression (the gate is due; verbose `reason=-`)
//   Blocker class (gates.py BLOCKER_CLASSES -> one-column mark, T-14b):
//     J             judgment  = a human must decide (the FAIL-CLOSED fold of a
//                   missing/blank/out-of-set `blocker_class` — v1 gates land here)
//     P             paperwork = evidence is collectible, auto-release eligible
//   Age (`formatDuration` -> compact):
//     <n>s / <n>m / <n>h / <n>d   sub-minute / sub-hour / sub-day / days
//                   (e.g. `3h 55m` -> `3h`, `12h 0m` -> `12h`, `2d`)
//   Omitted secondary fields:
//     +N            N secondary fields were compressed away on this line
//
// DETERMINISTIC FIT LADDER (first fit wins):
//   1. answer tier: full `-> /autopilot gate <id> approve|reject`, then
//      short `-> /autopilot gates`.
//   2. compaction level: 0 = full age + full reason; 1 = compact age + full
//      reason; 2 = compact age + compact reason. Drift is always `~D`.
//   3. secondary keep threshold 0..5 (rank rises as value falls):
//       1 ` code=<reason_code>`, 2 ` scope=unresolved-scope`,
//       3 ` stage=N` / ` key=<key>`, 4 ` reminders=n/m`, 5 blocker mark (`J`/`P`).
//      Every omitted secondary field is counted into the trailing `+N`.
// The ladder prefers compacting a required field's FORMAT (cheap, reversible
// from the encoding table) over dropping a whole secondary FIELD, and prefers
// dropping secondary fields over shortening the recovery command.
/** Compact drift marker (`~D` = evidence newer than `created_at`). */
export const GATE_DRIFT_MARK = "~D";
/** T-14b compact blocker-class marks. One column of payload (plus the token's
 * leading space) is the entire budget the frozen 110-column contracts leave for
 * an always-present classification, so the class is encoded exactly like the
 * `~D` / `R:*` marks rather than as a `blocker=` field. `judgment` is the
 * {@link blockerClassOf} fold of an absent/blank/out-of-set value, so a v1
 * legacy gate can NEVER render as auto-releasable. */
export const GATE_BLOCKER_MARK = { judgment: "J", paperwork: "P" };
/** Compact reason codes — the encode half of the table above. */
export const GATE_REASON_CODE = {
    "gate-queue-unreadable": "R:queue",
    "key-in-flight": "R:flight",
    "cap-reached": "R:cap",
    "stage-terminal": "R:term",
    "not-due": "R:notdue",
    "unresolved-scope": "R:scope",
};
/** Secondary-field drop ranks (lower drops first). The required trio
 * (`~D` / age / reason) has no rank here — it is never dropped. T-14b's
 * `blocker` mark joins the same tier at rank 5: it is the LAST secondary to
 * yield, because "auto-release or wait for a human" is the decision the panel
 * exists to answer, while it still yields visibly (`+N`) under real pressure. */
const GATE_DROP_RANK = { code: 1, scopeMarker: 2, scopeToken: 3, reminders: 4, blocker: 5 };
const GATE_MAX_DROP = 5;
/** ` age=3h 55m` (verbose) or the empty string when `created_at` is unknown. */
function gateAgeToken(ageMs, compact) {
    if (ageMs === null || ageMs === undefined)
        return "";
    if (!compact)
        return ` age=${formatDuration(ageMs)}`;
    const s = Math.max(0, Math.floor(ageMs / 1000));
    if (s < 60)
        return ` age=${s}s`;
    const m = Math.floor(s / 60);
    if (m < 60)
        return ` age=${m}m`;
    const h = Math.floor(m / 60);
    if (h < 24)
        return ` age=${h}h`;
    return ` age=${Math.floor(h / 24)}d`;
}
/** ` reason=-` (verbose) or ` R:xxx` (compact). Unknown runtime values keep the
 * verbose form rather than mislabeling them as `R:due`. */
function gateReasonToken(reason, compact) {
    if (!compact)
        return ` reason=${reason ?? "-"}`;
    if (reason === null || reason === undefined)
        return " R:due";
    return ` ${GATE_REASON_CODE[reason] ?? `reason=${reason}`}`;
}
/**
 * Render ONE pending gate as a Layer A row (AC-001/AC-012). Pure function of
 * the collected gate + its position in the queue; the encoding table and the
 * fit ladder above are the whole contract. `reason`, age and the `~D` drift
 * mark are always present — only their encoding can change.
 */
export function renderPendingGateLine(gate, index, total) {
    const head = index === 0 ? `gates: ${total} pending - ` : "  · ";
    const base = `${head}${gate.id} (${gate.kind})`;
    const drift = gate.drift !== null && gate.drift !== undefined ? ` ${GATE_DRIFT_MARK}` : "";
    const optionals = [];
    // T-14b: the folded blocker class is a secondary field in the same tier as
    // `code=`/`scope=`/`stage=`/`key=`/`reminders=` below. It is pushed FIRST so
    // it sits right after the kind (the classification is a headline fact) but
    // carries the HIGHEST rank, so the fit ladder drops it only after every other
    // secondary; every omitted optional — this one included — is counted into the
    // trailing `+N`.
    optionals.push({
        text: ` ${GATE_BLOCKER_MARK[blockerClassOf({ blockerClass: gate.blockerClass ?? null })]}`,
        rank: GATE_DROP_RANK.blocker,
    });
    if (gate.reasonCode !== null && gate.reasonCode !== undefined) {
        optionals.push({ text: ` code=${gate.reasonCode}`, rank: GATE_DROP_RANK.code });
    }
    if (gate.scopeResolved === false) {
        optionals.push({ text: ` scope=${GATE_SCOPE_UNRESOLVED}`, rank: GATE_DROP_RANK.scopeMarker });
    }
    const scope = gate.stage !== null ? ` stage=${gate.stage}` : gate.key !== "" ? ` key=${gate.key}` : "";
    if (scope !== "")
        optionals.push({ text: scope, rank: GATE_DROP_RANK.scopeToken });
    if (gate.reminders !== undefined && gate.reminders > 0) {
        optionals.push({
            text: ` reminders=${gate.reminders}/${gate.reminderMax ?? "?"}`,
            rank: GATE_DROP_RANK.reminders,
        });
    }
    const answers = [` -> /autopilot gate ${gate.id} approve|reject`, " -> /autopilot gates"];
    for (const answer of answers) {
        for (let level = 0; level <= 2; level++) {
            const age = gateAgeToken(gate.ageMs, level >= 1);
            const reason = gateReasonToken(gate.reason, level >= 2);
            for (let keep = 0; keep <= GATE_MAX_DROP; keep++) {
                const kept = optionals.filter((t) => t.rank > keep);
                const omitted = optionals.length - kept.length;
                const trace = omitted > 0 ? ` +${omitted}` : "";
                const candidate = `${base}${drift}${kept.map((t) => t.text).join("")}${age}${reason}${answer}${trace}`;
                if (candidate.length <= MONITOR_LINE_MAX)
                    return candidate;
            }
        }
    }
    // Last resort (unreachable for gate ids/kinds within the panel's own
    // bounds): keep the required trio + compact reason/age + the short recovery
    // entry and shrink only the head — never the trio (AC-001 + AC-012).
    const tail = `${drift}${gateAgeToken(gate.ageMs, true)}${gateReasonToken(gate.reason, true)}${answers[1] ?? ""}`;
    const room = MONITOR_LINE_MAX - tail.length;
    return `${trunc(base, Math.max(0, room))}${tail}`;
}
/**
 * Render the snapshot as the fixed-section panel. Every section is always
 * present (0 running folds to the "workers: 0 running" header, 0 pending to
 * "gates: 0 pending") so the panel's height — and therefore the editor
 * layout — never flickers between ticks (§9). All lines cap at
 * MONITOR_LINE_MAX columns with an ellipsis. The first line is the
 * self-attesting header (see {@link monitorHeaderLine}).
 */
export function renderMonitorLines(s) {
    const lines = [monitorHeaderLine(s)];
    // G4 AC-017 (D-018): a degraded frame says so on its own line — the payload
    // below stays the last known truth, the diagnostic is explicit and in-frame
    // (no write path). Error summary first so a long path/timestamp cannot hide
    // it; the line is capped like every other.
    if (s.degraded === true) {
        const at = s.lastErrorAtMs === undefined ? "?" : new Date(s.lastErrorAtMs).toISOString();
        lines.push(trunc(`DEGRADED: ${s.lastError ?? "unknown error"} (read failed at ${at})`, MONITOR_LINE_MAX));
    }
    if (!s.serve.running) {
        lines.push("serve: not running -> /mw restart");
    }
    else if (s.serve.stale) {
        // Cap the DETAIL (not the line) so the /mw restart recovery hint is
        // always visible even with long staleness timestamps (AC-007 spirit).
        const head = `serve: PID ${s.serve.pid} STALE CODE`;
        const tail = " -> /mw restart";
        const room = MONITOR_LINE_MAX - head.length - tail.length - 3; // " (…)"
        let detail = s.serve.staleDetail;
        if (detail.length > room)
            detail = `${detail.slice(0, Math.max(0, room - 1))}…`;
        lines.push(`${head} (${detail})${tail}`);
    }
    else {
        const up = s.serve.upMs !== null ? `, up ${formatDuration(s.serve.upMs)}` : "";
        lines.push(trunc(`serve: PID ${s.serve.pid ?? "?"} fresh${up}`, MONITOR_LINE_MAX));
    }
    const autoToken = ` | auto=${s.conductor.autoMode ?? "off"}`;
    if (!s.conductor.everEnabled) {
        lines.push(`conductor: not enabled (/autopilot enable)${autoToken}`);
    }
    else if (s.conductor.pid !== null && s.conductor.alive) {
        lines.push(trunc(`conductor: PID ${s.conductor.pid} alive | ${conductorIntent(s.conductor)}${autoToken}`, MONITOR_LINE_MAX));
    }
    else if (s.conductor.pid !== null) {
        lines.push(`conductor: dead (pid ${s.conductor.pid} stale)${autoToken}`);
    }
    else {
        lines.push(trunc(`conductor: not running | ${conductorIntent(s.conductor)}${autoToken}`, MONITOR_LINE_MAX));
    }
    if (s.autopilot.enabled) {
        const a = s.autopilot;
        const tick = a.tickSeq === null
            ? "tick: none yet"
            : `tick seq ${a.tickSeq} (${a.tickAgeMs === null ? "—" : formatDuration(a.tickAgeMs)} ago)`;
        const stale = a.tickStale ? " STALE (conductor not ticking)" : "";
        const count = (status) => a.keys.filter((k) => k.status === status).length;
        lines.push(trunc(`autopilot: ${tick}${stale} | slots ${a.slotsUsed}/${a.slotsMax} | ` +
            `keys ${a.keys.length} (running ${count("running")}, stalled ${count("stalled")}, ` +
            `done ${count("done")}) | stall-ticks ${a.stallTicks}`, MONITOR_LINE_MAX));
        // AC-005: the two concurrency quantities on their own row so the 110-column
        // cap can never truncate them off the (already long) summary line, and so
        // no existing row's content or order changes. `cap` = config upper bound,
        // `eff` = min(cap, |F|) for THIS snapshot.
        if (a.slotsEffective !== undefined && a.frontierSize !== undefined) {
            lines.push(trunc(`autopilot: cap ${a.slotsCap ?? a.slotsMax} | eff ${a.slotsEffective} (frontier ${a.frontierSize})`, MONITOR_LINE_MAX));
        }
        // G2 AC-008 (VC-011): first-glance "is a human actually the blocker?"
        // marker — a pending gate with zero non-terminal workers. The third
        // truth-table axis is render-time: a stale tick already prints STALE on
        // the line above, so the marker stays off instead of double-reporting.
        if (s.blockedOnHuman && !a.tickStale) {
            lines.push(trunc(`BLOCKED_ON_HUMAN: ${s.gates.length} pending gate(s), 0 non-terminal workers -> /autopilot gates`, MONITOR_LINE_MAX));
        }
        const stallByKey = new Map(a.stalls.map((stall) => [stall.key, stall]));
        const attention = a.keys.filter((k) => k.status === "stalled" || k.inFlight > 0 || k.blockedBy.length > 0 || stallByKey.has(k.key));
        for (const k of attention.slice(0, 6)) {
            const stall = stallByKey.get(k.key);
            const bits = [`  · ${k.key} ${k.phase}/${k.status}`];
            if (k.inFlight > 0)
                bits.push(`${k.inFlight} running`);
            if (stall !== undefined) {
                const error = stall.lastError === "" ? "" : ` "${stall.lastError}"`;
                bits.push(`advance ${stall.count}x ${stall.primaryClass} ` +
                    `${stall.ageMs === null ? "—" : formatDuration(stall.ageMs)} ago${error}`);
            }
            if (k.blockedBy.length > 0)
                bits.push(`deps blocked by ${k.blockedBy.join(",")}`);
            if (k.status === "stalled") {
                const gate = s.gates.find((g) => g.kind === "stalled" && g.key === k.key);
                const hint = gate === undefined
                    ? "-> /autopilot gate <id> approve|reject"
                    : `-> /autopilot gate ${gate.id} approve|reject`;
                bits.push(gate === undefined ? hint : `${hint} (resume grants one round)`);
            }
            lines.push(trunc(bits.join(" | "), MONITOR_LINE_MAX));
        }
        if (attention.length > 6)
            lines.push(`  · +${attention.length - 6} more -> /autopilot status`);
    }
    else if (!s.autopilot.everEnabled) {
        lines.push("autopilot: not enabled (/autopilot enable)");
    }
    else {
        lines.push("autopilot: disabled (config.json enabled=false)");
    }
    if (s.workers.length === 0) {
        lines.push("workers: 0 running");
    }
    else {
        lines.push(`workers: ${s.workers.length} running (all keys)`);
        for (const w of s.workers) {
            lines.push(trunc(`  · ${w.taskKey}  ${Math.ceil(w.elapsedMs / 60_000)}m`, MONITOR_LINE_MAX));
        }
    }
    // AC-016 (D1): stage main-gate rows. Every roadmap stage is listed; the row
    // is the direct answer to "why did per-key work stop?" when there is no
    // individual gate to point at (a `pending`/`halted` stage stalls the whole
    // tick — `_stage_activation` at conductor.py:671).
    if (s.autopilot.stages !== undefined && s.autopilot.stages.length > 0) {
        const stages = s.autopilot.stages;
        const statusCount = (status) => stages.filter((st) => st.status === status).length;
        const summary = ["running", "pending", "halted", "closed", "closed-human", "approved"]
            .map((status) => `${status} ${statusCount(status)}`)
            .filter((bit) => !bit.endsWith(" 0"))
            .join(", ");
        lines.push(trunc(`stages: ${stages.length}${summary === "" ? "" : ` (${summary})`}`, MONITOR_LINE_MAX));
        for (const st of stages) {
            const bits = [`  · stage ${st.number} ${st.status}`];
            if (st.blockerKind !== null) {
                const gate = st.blockerGateId === null ? "" : ` ${st.blockerGateId}`;
                bits.push(`waiting on ${st.blockerKind}${gate}`);
                if (st.blockerAgeMs !== null)
                    bits.push(`age=${formatDuration(st.blockerAgeMs)}`);
            }
            else if (st.status !== "closed" && st.status !== "closed-human") {
                bits.push("waiting on activation");
            }
            if (st.frozenKeys.length > 0)
                bits.push(`frozen ${st.frozenKeys.join(",")}`);
            lines.push(trunc(bits.join(" | "), MONITOR_LINE_MAX));
        }
    }
    if (s.queueState === "unreadable") {
        // AC-003 (D3): an unreadable queue must NOT render as "0 pending".
        lines.push(trunc(`gates: gate-queue-unreadable (${s.queueError ?? "unknown error"}) -> /mw doctor`, MONITOR_LINE_MAX));
    }
    else if (s.queueState === "partial" && s.gates.length === 0) {
        // T-21 R-2 (QG counterexample): the directory scanned but every gate file
        // it listed failed to read. That is "cannot read gates", NOT "no gates" —
        // the old ladder fell straight into `gates: 0 pending` because the partial
        // branch only ran after at least one gate rendered. The count + samples
        // ride the head of the line so truncation can never erase them.
        const samples = queueFailureSamples(s);
        const detail = samples.length === 0 ? "unknown error" : `${samples.length} unreadable: ${samples.join("; ")}`;
        lines.push(trunc(`gates: gate-queue-unreadable (${detail}) -> /mw doctor`, MONITOR_LINE_MAX));
    }
    else if (s.gates.length === 0) {
        lines.push("gates: 0 pending");
    }
    else {
        // One line per pending gate (AC-012): the first carries the count, the
        // rest indent like the attention rows. Every line is a resident row
        // (AC-001: no cap, no decay, no dedup). id/kind/age/reason/answer are
        // collected facts, never derived from the question prose. The compact
        // encoding + fit ladder (see the table above) keep DRIFT, reason and age
        // visible under width pressure; secondary fields yield with a `+N` trace.
        s.gates.forEach((g, index) => {
            lines.push(renderPendingGateLine(g, index, s.gates.length));
        });
        if (s.queueState === "partial") {
            const samples = queueFailureSamples(s);
            const detail = samples.length === 0
                ? "one gate file could not be read"
                : `${samples.length} unreadable: ${samples.join("; ")}`;
            lines.push(trunc(`  · gate-queue-unreadable: ${detail}`, MONITOR_LINE_MAX));
        }
    }
    return lines;
}
// ── Lifetime: start/stop/isMonitorActive (module-level singleton) ────────────
/** One monitor per window: the interval + apply callback live in module
 * memory only (AC-009 — never persisted; each pi process is its own module
 * instance, so windows cannot see each other's state). */
let monitorTimer = null;
let monitorApply = null;
/** G4 AC-015 (D-017): monotonic count of SUCCESSFUL collections. Module-level
 * and deliberately NOT reset by stop()/start() — a re-arm must not make a
 * frozen panel look fresh again by returning to tick 0. */
let monitorTickCount = 0;
/** G4 AC-017 (D-018): the last frame whose read succeeded. A degraded frame
 * reuses this payload verbatim. Run-scoped: `startMonitor` clears it, because
 * a new run has no previous frame to fall back to. */
let lastGoodSnapshot = null;
/** G4 AC-015: wall-clock anchor of the current run — the time of the last
 * SUCCESSFUL collection, or the run start while nothing has succeeded yet. A
 * degraded frame keeps showing it so a frozen panel is self-evident (the
 * stamp must not advance just because the read failed again). */
let anchorAtMs = null;
export function isMonitorActive() {
    return monitorTimer !== null;
}
/** One-line error summary for a degraded frame (`name: message`), never empty
 * and never thrown. */
function errorSummary(err) {
    const text = err instanceof Error ? `${err.name}: ${err.message}` : String(err);
    return text.trim() === "" ? "unknown error" : text;
}
/**
 * G4 AC-017 (D-018): build the DEGRADED frame for a failed read.
 *
 * With a previous good frame the payload is reused verbatim (the panel keeps
 * showing the last known truth), and `collectedAtMs`/`tickCount` keep their
 * last-good values — that is what lets a frozen stamp be told apart from a
 * live one. `stale`/`staleDetail` flag it once the stamp has not moved for
 * more than {@link PANEL_STALE_MISSED_CYCLES} refresh periods.
 *
 * BOUNDARY (D-018): if the FIRST collection already failed there is no
 * previous frame to reuse, so the frame carries only `collectedAtMs` (this
 * failed attempt) plus the error summary; `stale` stays false because there is
 * no past stamp to measure from. The frame is still emitted — never dropped
 * silently.
 */
function degradedSnapshot(err, nowMs, intervalMs) {
    const summary = trunc(errorSummary(err), 160);
    // The anchor does not advance on a failed read: freshness is measured from
    // the last real collection (or the run start when there has been none), so
    // a panel stuck on failures eventually says STALE PANEL instead of looking
    // freshly stamped (AC-015).
    const anchor = anchorAtMs ?? nowMs;
    const ageMs = Math.max(0, nowMs - anchor);
    const late = ageMs > intervalMs * PANEL_STALE_MISSED_CYCLES;
    const diagnostics = {
        collectedAtMs: anchor,
        tickCount: monitorTickCount,
        degraded: true,
        lastErrorAtMs: nowMs,
        lastError: summary,
        stale: late,
        staleDetail: late ? `no refresh since ${new Date(anchor).toISOString()}, ${formatDuration(ageMs)}` : undefined,
    };
    if (lastGoodSnapshot !== null)
        return { ...lastGoodSnapshot, ...diagnostics };
    // BOUNDARY (D-018): before the first successful collection there is no
    // previous payload to reuse — only the (non-advancing) anchor stamp and the
    // error summary. The frame is still emitted, never dropped silently.
    return {
        serve: { running: false, pid: null, stale: false, staleDetail: "", upMs: null },
        conductor: { pid: null, alive: false, enabled: false, paused: false, everEnabled: false },
        autopilot: {
            enabled: false,
            everEnabled: false,
            tickSeq: null,
            tickAgeMs: null,
            tickStale: false,
            slotsUsed: 0,
            slotsMax: 0,
            stallTicks: 0,
            keys: [],
            stalls: [],
        },
        workers: [],
        gates: [],
        blockedOnHuman: false,
        ...diagnostics,
    };
}
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
export function startMonitor(projectDir, apply, opts) {
    if (monitorTimer !== null)
        return true;
    const readState = opts?.readState ?? readMonitorState;
    const nowMs = opts?.nowMs ?? Date.now;
    const intervalMs = opts?.intervalMs ?? MONITOR_INTERVAL_MS;
    // A fresh run has no reusable frame: if the FIRST tick fails there is
    // nothing to fall back to and the frame must say so (D-018 boundary). The
    // anchor starts at the run start and only moves on a successful collection.
    lastGoodSnapshot = null;
    anchorAtMs = nowMs();
    const render = () => {
        const now = nowMs();
        let frame;
        try {
            const collected = readState(projectDir, now);
            monitorTickCount += 1;
            // Stamp the successful collection: absolute wall clock + the
            // monotonic count are the frame's self-attestation (AC-015).
            frame = { ...collected, collectedAtMs: now, tickCount: monitorTickCount };
            lastGoodSnapshot = frame;
            anchorAtMs = now;
        }
        catch (err) {
            // G4 AC-017: no longer swallow the whole tick — degrade instead.
            frame = degradedSnapshot(err, now, intervalMs);
        }
        try {
            apply(renderMonitorLines(frame));
        }
        catch {
            // The widget write itself failed (e.g. an invalidated session
            // runner): nothing to render into, retry next tick.
        }
    };
    render();
    monitorApply = apply;
    monitorTimer = setInterval(render, intervalMs);
    return true;
}
/**
 * Stop the monitor. Idempotent: not active → false, nothing happens (the
 * widget is NOT cleared in that case). When active, clears the interval and
 * calls `apply(undefined)` — clearing the widget — using the passed callback
 * or the one captured at start.
 */
export function stopMonitor(apply) {
    if (monitorTimer === null)
        return false;
    clearInterval(monitorTimer);
    monitorTimer = null;
    const clear = apply ?? monitorApply;
    monitorApply = null;
    clear?.(undefined);
    return true;
}
//# sourceMappingURL=monitor.js.map