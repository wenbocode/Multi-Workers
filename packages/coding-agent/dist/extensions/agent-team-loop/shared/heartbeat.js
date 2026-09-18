import * as fs from "node:fs";
import * as path from "node:path";
/** Worker heartbeat cadence (design D-003). 30s keeps a 2x margin under the
 * 60s AC-003 ceiling while limiting trace.log growth (~120 lines/hour). */
export const HEARTBEAT_INTERVAL_MS = 30_000;
/** A worker whose last heartbeat is older than this is considered stalled.
 * The watch widget's STALE mark uses this value; mw doctor's worker_liveness
 * uses the same 90s default (packages/multi-workers/mw_common.py) — keep the
 * two in sync when changing either. */
export const HEARTBEAT_STALE_MS = 90_000;
const HEARTBEAT_LINE_RE = /^\[HEARTBEAT\] (\S+) task=(\S+)(?: phase=(\S+))?$/;
const START_LINE_RE = /^\[START\] (\S+) task=\S+ type=\S+ phases=(\S+)$/;
const MODEL_LINE_RE = /^\[MODEL\] (\S+) model=(\S+)$/;
const END_LINE_RE = /^\[END\] (\S+) exit=(\d+) elapsed=(\d+)s tools=(\d+) phases=(\S+)$/;
const TOOL_LINE_RE = /^\[TOOL\] (\S+) (\S+)(?: (.*))?$/;
const CHECKPOINT_LINE_RE = /^\[CHECKPOINT\] (\S+) elapsed=(\d+)s reads=(\d+) writes=(\d+) phases=(\S+) uniq_targets=(\d+) repeat_top=(\d+) risk=(low|mid|high)$/;
/** Human-readable age for heartbeat display: "15s", "3m", "2h". Shared by
 * the watch widget's `hb` field and terminal-summary runtime stats. */
export function formatHeartbeatAge(ms) {
    const s = Math.max(0, Math.round(ms / 1000));
    if (s < 60)
        return `${s}s`;
    const m = Math.floor(s / 60);
    if (m < 60)
        return `${m}m`;
    return `${Math.floor(m / 60)}h`;
}
/** Parse the full progress state from a worker task's trace.log. Returns
 * undefined when trace.log is absent or unreadable; individual fields stay
 * undefined when their line types are missing (old bundles wrote only
 * [FLOW]/[HEARTBEAT]/[GOAL_CHECK] lines). */
export function readTaskProgress(taskDir) {
    let content;
    try {
        content = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
    }
    catch {
        return undefined;
    }
    let hbFirstTs = "";
    let hbLastTs = "";
    let hbCount = 0;
    let phase = "-";
    let phaseTotal = "-";
    let startTs;
    let endTs;
    let exitCode;
    let endPhases;
    let lastAction;
    let checkpoint;
    let model;
    for (const line of content.split("\n")) {
        const hb = HEARTBEAT_LINE_RE.exec(line);
        if (hb) {
            hbCount++;
            if (!hbFirstTs)
                hbFirstTs = hb[1] ?? "";
            hbLastTs = hb[1] ?? "";
            const label = hb[3] ?? "-";
            if (label === "-") {
                phase = "-";
                phaseTotal = "-";
            }
            else {
                const [p, t] = label.split("/");
                phase = p ?? "-";
                phaseTotal = t ?? "-";
            }
            continue;
        }
        const start = START_LINE_RE.exec(line);
        if (start) {
            startTs = start[1] ?? "";
            continue;
        }
        const mdl = MODEL_LINE_RE.exec(line);
        if (mdl) {
            model = mdl[2] ?? undefined;
            continue;
        }
        const end = END_LINE_RE.exec(line);
        if (end) {
            endTs = end[1] ?? "";
            const code = Number(end[2]);
            if (Number.isInteger(code))
                exitCode = code;
            endPhases = end[5] ?? "-";
            continue;
        }
        const tool = TOOL_LINE_RE.exec(line);
        if (tool) {
            lastAction = [tool[2], tool[3]].filter(Boolean).join(" ");
            continue;
        }
        const ck = CHECKPOINT_LINE_RE.exec(line);
        if (ck) {
            checkpoint = {
                ts: ck[1] ?? "",
                elapsedS: Number(ck[2]),
                reads: Number(ck[3]),
                writes: Number(ck[4]),
                phases: ck[5] ?? "-",
                uniqTargets: Number(ck[6]),
                repeatTop: Number(ck[7]),
                risk: ck[8] ?? "low",
            };
        }
    }
    const heartbeat = hbCount > 0
        ? {
            lastTs: hbLastTs,
            ageMs: Date.now() - Date.parse(hbLastTs),
            phase,
            phaseTotal,
            count: hbCount,
            firstTs: hbFirstTs,
        }
        : undefined;
    let elapsedMs;
    if (startTs) {
        const end = endTs ? Date.parse(endTs) : Date.now();
        elapsedMs = Math.max(0, end - Date.parse(startTs));
    }
    return { heartbeat, startTs, endTs, exitCode, endPhases, elapsedMs, lastAction, checkpoint, model };
}
/** Parse heartbeat state from a worker task's trace.log (last line wins).
 * Returns undefined when the file exists but carries no [HEARTBEAT] lines
 * (old bundles, pre-start) or when trace.log is absent/unreadable. */
export function readHeartbeatInfo(taskDir) {
    return readTaskProgress(taskDir)?.heartbeat;
}
//# sourceMappingURL=heartbeat.js.map