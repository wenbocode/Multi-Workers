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
	/** Model id from the [MODEL] line (new bundles) — what the worker is
	 * actually running, launcher defaults included. Undefined on old bundles
	 * and when the model was unresolved at session start. */
	model: string | undefined;
}

const HEARTBEAT_LINE_RE = /^\[HEARTBEAT\] (\S+) task=(\S+)(?: phase=(\S+))?$/;
const START_LINE_RE = /^\[START\] (\S+) task=\S+ type=\S+ phases=(\S+)$/;
const MODEL_LINE_RE = /^\[MODEL\] (\S+) model=(\S+)$/;
const END_LINE_RE = /^\[END\] (\S+) exit=(\d+) elapsed=(\d+)s tools=(\d+) phases=(\S+)$/;
const TOOL_LINE_RE = /^\[TOOL\] (\S+) (\S+)(?: (.*))?$/;
const CHECKPOINT_LINE_RE =
	/^\[CHECKPOINT\] (\S+) elapsed=(\d+)s reads=(\d+) writes=(\d+) phases=(\S+) uniq_targets=(\d+) repeat_top=(\d+) risk=(low|mid|high)$/;

/** Human-readable age for heartbeat display: "15s", "3m", "2h". Shared by
 * the watch widget's `hb` field and terminal-summary runtime stats. */
export function formatHeartbeatAge(ms: number): string {
	const s = Math.max(0, Math.round(ms / 1000));
	if (s < 60) return `${s}s`;
	const m = Math.floor(s / 60);
	if (m < 60) return `${m}m`;
	return `${Math.floor(m / 60)}h`;
}

/** Parse the full progress state from a worker task's trace.log. Returns
 * undefined when trace.log is absent or unreadable; individual fields stay
 * undefined when their line types are missing (old bundles wrote only
 * [FLOW]/[HEARTBEAT]/[GOAL_CHECK] lines). */
export function readTaskProgress(taskDir: string): TaskProgress | undefined {
	let content: string;
	try {
		content = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
	} catch {
		return undefined;
	}

	let hbFirstTs = "";
	let hbLastTs = "";
	let hbCount = 0;
	let phase = "-";
	let phaseTotal = "-";
	let startTs: string | undefined;
	let endTs: string | undefined;
	let exitCode: number | undefined;
	let endPhases: string | undefined;
	let lastAction: string | undefined;
	let checkpoint: CheckpointInfo | undefined;
	let model: string | undefined;

	for (const line of content.split("\n")) {
		const hb = HEARTBEAT_LINE_RE.exec(line);
		if (hb) {
			hbCount++;
			if (!hbFirstTs) hbFirstTs = hb[1] ?? "";
			hbLastTs = hb[1] ?? "";
			const label = hb[3] ?? "-";
			if (label === "-") {
				phase = "-";
				phaseTotal = "-";
			} else {
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
			if (Number.isInteger(code)) exitCode = code;
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
				risk: (ck[8] as CheckpointInfo["risk"]) ?? "low",
			};
		}
	}

	const heartbeat: HeartbeatInfo | undefined =
		hbCount > 0
			? {
					lastTs: hbLastTs,
					ageMs: Date.now() - Date.parse(hbLastTs),
					phase,
					phaseTotal,
					count: hbCount,
					firstTs: hbFirstTs,
				}
			: undefined;

	let elapsedMs: number | undefined;
	if (startTs) {
		const end = endTs ? Date.parse(endTs) : Date.now();
		elapsedMs = Math.max(0, end - Date.parse(startTs));
	}

	return { heartbeat, startTs, endTs, exitCode, endPhases, elapsedMs, lastAction, checkpoint, model };
}

/** Parse heartbeat state from a worker task's trace.log (last line wins).
 * Returns undefined when the file exists but carries no [HEARTBEAT] lines
 * (old bundles, pre-start) or when trace.log is absent/unreadable. */
export function readHeartbeatInfo(taskDir: string): HeartbeatInfo | undefined {
	return readTaskProgress(taskDir)?.heartbeat;
}
