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

import * as fs from "node:fs";
import * as path from "node:path";
import { IndexStore } from "../shared/index-store.ts";
import { getMwStatus, readServeMeta, serveStaleness } from "../shared/mw-runner.ts";
import { WorkerStore } from "../shared/worker-store.ts";
import {
	BEAT_EV,
	type ConfigResult,
	configPath,
	DEFAULT_CONFIG,
	gatesDir,
	type RoadmapResult,
	readConfig,
	readRoadmap,
	type TimelineEvent,
	timelinePath,
} from "./status-model.ts";

/** Widget id for the monitor panel (the watch widget is
 * "agent-team-loop-watch" — the two coexist, D-003). */
export const MONITOR_WIDGET_ID = "agent-team-loop-monitor";

/** Poll cadence — the same 4s beat as the watch widget (spec §2.2). */
export const MONITOR_INTERVAL_MS = 4000;

/** Panel line width cap (same as the watch widget's WATCH_LINE_MAX). */
const MONITOR_LINE_MAX = 110;

// ── Snapshot types (design §4.1 — T-02 and the tests depend on these) ───────

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

// ── Collect: readMonitorState (pure, read-only) ──────────────────────────────

/** Scan one gate file's frontmatter for the four fields the panel needs
 * (D-004 line scan — no YAML dependency). Returns the gate only when it is
 * `status: pending` with a usable id/kind; anything else (answered gates,
 * non-gate or unparsable files) is skipped. */
function scanPendingGate(file: string): MonitorGate | null {
	let text: string;
	try {
		text = fs.readFileSync(file, "utf8");
	} catch {
		return null;
	}
	const lines = text.split(/\r\n|\r|\n/);
	if (lines.length === 0 || lines[0].trim() !== "---") return null;
	let id = "";
	let kind = "";
	let stage: number | null = null;
	let key = "";
	let status = "";
	for (let i = 1; i < lines.length; i++) {
		const line = lines[i];
		if (line.trim() === "---") break; // frontmatter closed
		const m = /^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*?)[ \t]*$/.exec(line);
		if (m === null) continue; // list items, blank lines, etc.
		const name = m[1] ?? "";
		const value = m[2] ?? "";
		if (name === "id") id = value;
		else if (name === "kind") kind = value;
		else if (name === "status") status = value;
		else if (name === "key") key = value;
		else if (name === "stage") stage = /^-?\d+$/.test(value) ? Number.parseInt(value, 10) : null;
	}
	if (status !== "pending" || id === "" || kind === "") return null;
	return { id, kind, stage, key };
}

/** Derive the full monitor snapshot from the file family. Read-only; every
 * individual source degrades to a safe default (missing pid file → not
 * running, missing config → never enabled, missing gates dir → empty queue)
 * instead of throwing — a half-present project still renders a full panel
 * (AC-007). */
export function readMonitorState(projectDir: string, nowMs: number): MonitorSnapshot {
	// serve — mw-runner owns the pid-file liveness + staleness logic.
	const status = getMwStatus(projectDir);
	let serve: MonitorServe = { running: false, pid: null, stale: false, staleDetail: "", upMs: null };
	if (status.running) {
		const staleness = serveStaleness(projectDir);
		// Serve start: serve.meta first, mw.pid mtime as the pre-meta fallback.
		let startedAtMs: number | null = readServeMeta(projectDir)?.startedAtMs ?? null;
		if (startedAtMs === null) {
			try {
				startedAtMs = fs.statSync(path.join(projectDir, ".mw", "mw.pid")).mtimeMs;
			} catch {
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
	let conductorPid: number | null = null;
	let conductorAlive = false;
	try {
		const raw = fs.readFileSync(path.join(projectDir, ".mw", "conductor.pid"), "utf8").trim();
		const parsed = Number.parseInt(raw, 10);
		if (!Number.isNaN(parsed)) {
			conductorPid = parsed;
			try {
				process.kill(parsed, 0);
				conductorAlive = true;
			} catch {
				conductorAlive = false;
			}
		}
	} catch {
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
	const conductor: MonitorConductor = { pid: conductorPid, alive: conductorAlive, enabled, paused, everEnabled };

	// workers — every running row across ALL keys (system-scoped, unlike the
	// key-scoped watch widget), elapsed from dispatchedAt; rows with an
	// unparsable dispatchedAt are dropped rather than shown wrong.
	const workers: MonitorWorker[] = [];
	for (const entry of new WorkerStore(path.join(projectDir, ".agenticdoc")).readAll()) {
		if (entry.status !== "running") continue;
		const dispatched = Date.parse(entry.dispatchedAt);
		if (Number.isNaN(dispatched)) continue;
		workers.push({ taskKey: entry.taskKey, elapsedMs: Math.max(0, nowMs - dispatched) });
	}
	workers.sort((a, b) => b.elapsedMs - a.elapsedMs || a.taskKey.localeCompare(b.taskKey));

	// gates — pending queue only, seq order (the directory scan is the queue).
	const gates: MonitorGate[] = [];
	try {
		const dir = gatesDir(projectDir);
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			if (!entry.isFile() || !/^gate-\d+\.md$/.test(entry.name)) continue;
			const gate = scanPendingGate(path.join(dir, entry.name));
			if (gate !== null) gates.push(gate);
		}
	} catch {
		// gates dir missing — empty queue
	}
	gates.sort((a, b) => a.id.localeCompare(b.id));

	const autopilot = deriveAutopilotPanel(projectDir, nowMs, workers);

	return { serve, conductor, autopilot, workers, gates };
}

// ── Autopilot progress: deriveAutopilotPanel (AC-006/AC-007) ──────────────────

/** Bounded tail read of the current timeline file — the TS mirror of
 * autopilot/timeline.py tail_events. Rotated generations are deliberately
 * not consulted (this answers "what just happened") and the window keeps the
 * panel O(window) instead of O(history) on a multi-megabyte timeline. Torn
 * lines are skipped. Never throws: an absent/unreadable file yields []. */
export function readTimelineTail(file: string, opts?: { maxBytes?: number; limit?: number }): TimelineEvent[] {
	const maxBytes = opts?.maxBytes ?? 512 * 1024;
	const limit = opts?.limit ?? 400;
	let fd: number;
	try {
		fd = fs.openSync(file, "r");
	} catch {
		return [];
	}
	try {
		const size = fs.fstatSync(fd).size;
		if (size <= 0) return [];
		const start = Math.max(0, size - maxBytes);
		const buf = Buffer.alloc(size - start);
		fs.readSync(fd, buf, 0, buf.length, start);
		let lines = buf.toString("utf8").split("\n");
		if (start > 0) lines = lines.slice(1); // the window cut the first line
		const events: TimelineEvent[] = [];
		for (const line of lines) {
			const trimmed = line.trim();
			if (trimmed === "") continue;
			let parsed: unknown;
			try {
				parsed = JSON.parse(trimmed);
			} catch {
				continue;
			}
			if (typeof parsed !== "object" || parsed === null) continue;
			const ev = parsed as Partial<TimelineEvent>;
			if (typeof ev.seq !== "number") continue;
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
	} catch {
		return [];
	} finally {
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

export function classifyAdvanceFailure(text: string): string {
	const low = text.toLowerCase();
	if (INTERFACE_DRIFT_MARKERS.some((m) => low.includes(m))) return "interface-drift";
	if (GATE_BLOCKED_MARKERS.some((m) => low.includes(m))) return "gate-blocked";
	if (TIMEOUT_ENV_MARKERS.some((m) => low.includes(m))) return "timeout-env";
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
export function deriveAdvanceStalls(events: TimelineEvent[], nowMs: number): MonitorStall[] {
	interface Acc {
		edge: string;
		count: number;
		classes: Record<string, number>;
		lastError: string;
		newestTs: string;
	}
	const active = new Map<string, Acc>();
	const cleared = new Set<string>();
	const pendingError = new Map<string, string>();
	for (let i = events.length - 1; i >= 0; i--) {
		const ev = events[i];
		if (ev === undefined) continue;
		const key = ev.key;
		if (key === "" || key === "-") continue;
		if (ev.ev === "config") {
			if (!pendingError.has(key) && ev.detail.includes("advance")) {
				pendingError.set(
					key,
					ev.detail
						.slice(ev.detail.indexOf(":") + 1)
						.trim()
						.slice(0, 120),
				);
			}
			continue;
		}
		if (ev.ev !== "advance") continue;
		const m = ADVANCE_DETAIL_RE.exec(ev.detail);
		if (m === null) continue;
		const edge = m[1] ?? "";
		if (cleared.has(`${key}|${edge}`)) continue;
		const exitCode = Number.parseInt(m[2] ?? "0", 10);
		if (exitCode === 0) {
			// Only this edge's own success ends its run (the conductor skips a
			// different edge's advance entirely); older same-edge failures are
			// then skipped via `cleared`, so two boundaries never merge.
			const activeEntry = active.get(key);
			if (activeEntry !== undefined && activeEntry.edge === edge) active.delete(key);
			cleared.add(`${key}|${edge}`);
			continue;
		}
		const acc = active.get(key);
		if (acc !== undefined) {
			if (acc.edge !== edge) continue; // another boundary's failures
			acc.count += 1;
			const cls = m[3] ?? classifyAdvanceFailure(acc.lastError);
			acc.classes[cls] = (acc.classes[cls] ?? 0) + 1;
			continue;
		}
		const lastError = pendingError.get(key) ?? "";
		const cls = m[3] ?? classifyAdvanceFailure(lastError);
		active.set(key, { edge, count: 1, classes: { [cls]: 1 }, lastError, newestTs: ev.ts });
	}
	const stalls: MonitorStall[] = [];
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

/** Injection seam for tests (same pattern as startMonitor's readState). */
export interface AutopilotPanelDeps {
	readConfigFile?: (projectDir: string) => ConfigResult;
	readRoadmapFile?: (projectDir: string) => RoadmapResult;
	readIndexPhases?: (projectDir: string) => Map<string, string>;
	readTimeline?: (file: string) => TimelineEvent[];
}

function defaultIndexPhases(projectDir: string): Map<string, string> {
	try {
		const entries = new IndexStore(path.join(projectDir, ".agenticdoc")).readAll();
		return new Map(entries.map((e) => [e.key, e.phase]));
	} catch {
		return new Map();
	}
}

/** Derive the autopilot section from the file family (AC-007: every source
 * degrades to a safe default instead of throwing — a half-present project
 * still renders a full panel). Pure read-only. */
export function deriveAutopilotPanel(
	projectDir: string,
	nowMs: number,
	workers: MonitorWorker[],
	deps?: AutopilotPanelDeps,
): MonitorAutopilot {
	const configResult = (deps?.readConfigFile ?? readConfig)(projectDir);
	const config = configResult.ok ? configResult.config : null;
	const roadmap = (deps?.readRoadmapFile ?? readRoadmap)(projectDir);
	const statusByKey = new Map<string, string>();
	const depsByKey = new Map<string, string[]>();
	if (roadmap.ok) {
		for (const stage of roadmap.stages) {
			for (const [key, status] of Object.entries(stage.keyStatus)) statusByKey.set(key, status);
			for (const row of stage.keys) depsByKey.set(row.key, row.dependsOn);
		}
	}
	const phaseByKey = (deps?.readIndexPhases ?? defaultIndexPhases)(projectDir);
	const events = (deps?.readTimeline ?? ((file: string) => readTimelineTail(file)))(timelinePath(projectDir));

	let tickSeq: number | null = null;
	let tickAgeMs: number | null = null;
	for (let i = events.length - 1; i >= 0; i--) {
		const ev = events[i];
		if (ev === undefined || ev.ev !== BEAT_EV) continue;
		tickSeq = ev.seq;
		const parsed = Date.parse(ev.ts);
		tickAgeMs = Number.isNaN(parsed) ? null : Math.max(0, nowMs - parsed);
		break;
	}
	const pollMs = (config?.poll_interval_sec ?? DEFAULT_CONFIG.poll_interval_sec) * 1000;
	const staleAfterMs = Math.max(30_000, pollMs * 5);

	const keys: MonitorKey[] = [];
	const allKeys = [...new Set([...statusByKey.keys(), ...phaseByKey.keys()])].sort();
	for (const key of allKeys) {
		keys.push({
			key,
			phase: phaseByKey.get(key) ?? "—",
			status: statusByKey.get(key) ?? "unknown",
			inFlight: workers.filter((w) => w.taskKey.startsWith(`ap-${key}-`)).length,
			blockedBy: (depsByKey.get(key) ?? []).filter(
				(dep) => !["done", "closed-legacy"].includes(statusByKey.get(dep) ?? ""),
			),
		});
	}
	const busyKeys = new Set<string>();
	for (const w of workers) {
		const owner = allKeys.find((key) => w.taskKey.startsWith(`ap-${key}-`));
		busyKeys.add(owner ?? w.taskKey);
	}

	return {
		enabled: config?.enabled ?? false,
		everEnabled: fs.existsSync(configPath(projectDir)) && configResult.ok,
		tickSeq,
		tickAgeMs,
		tickStale: tickAgeMs !== null && tickAgeMs > staleAfterMs,
		slotsUsed: busyKeys.size,
		slotsMax: config?.max_parallel_keys ?? DEFAULT_CONFIG.max_parallel_keys,
		stallTicks: config?.advance_stall_ticks ?? DEFAULT_CONFIG.advance_stall_ticks,
		keys,
		stalls: deriveAdvanceStalls(events, nowMs),
	};
}

// ── Render: renderMonitorLines (pure) ────────────────────────────────────────

function trunc(s: string, max: number): string {
	return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}

/** "45s", "3m", "2h 3m" — coarse duration (serve uptime, stall age). */
function formatDuration(ms: number): string {
	const s = Math.max(0, Math.floor(ms / 1000));
	if (s < 60) return `${s}s`;
	const m = Math.floor(s / 60);
	if (m < 60) return `${m}m`;
	return `${Math.floor(m / 60)}h ${m % 60}m`;
}

/** Autopilot intent half of the conductor line. */
function conductorIntent(c: MonitorConductor): string {
	if (!c.enabled) return "autopilot disabled";
	return c.paused ? "autopilot enabled, paused" : "autopilot enabled, not paused";
}

/**
 * Render the snapshot as the fixed-section panel. Every section is always
 * present (0 running folds to the "workers: 0 running" header, 0 pending to
 * "gates: 0 pending") so the panel's height — and therefore the editor
 * layout — never flickers between ticks (§9). All lines cap at
 * MONITOR_LINE_MAX columns with an ellipsis.
 */
export function renderMonitorLines(s: MonitorSnapshot): string[] {
	const lines: string[] = ["[autopilot monitor]"];

	if (!s.serve.running) {
		lines.push("serve: not running -> /mw restart");
	} else if (s.serve.stale) {
		// Cap the DETAIL (not the line) so the /mw restart recovery hint is
		// always visible even with long staleness timestamps (AC-007 spirit).
		const head = `serve: PID ${s.serve.pid} STALE CODE`;
		const tail = " -> /mw restart";
		const room = MONITOR_LINE_MAX - head.length - tail.length - 3; // " (…)"
		let detail = s.serve.staleDetail;
		if (detail.length > room) detail = `${detail.slice(0, Math.max(0, room - 1))}…`;
		lines.push(`${head} (${detail})${tail}`);
	} else {
		const up = s.serve.upMs !== null ? `, up ${formatDuration(s.serve.upMs)}` : "";
		lines.push(trunc(`serve: PID ${s.serve.pid ?? "?"} fresh${up}`, MONITOR_LINE_MAX));
	}

	if (!s.conductor.everEnabled) {
		lines.push("conductor: not enabled (/autopilot enable)");
	} else if (s.conductor.pid !== null && s.conductor.alive) {
		lines.push(trunc(`conductor: PID ${s.conductor.pid} alive | ${conductorIntent(s.conductor)}`, MONITOR_LINE_MAX));
	} else if (s.conductor.pid !== null) {
		lines.push(`conductor: dead (pid ${s.conductor.pid} stale)`);
	} else {
		lines.push(trunc(`conductor: not running | ${conductorIntent(s.conductor)}`, MONITOR_LINE_MAX));
	}

	if (s.autopilot.enabled) {
		const a = s.autopilot;
		const tick =
			a.tickSeq === null
				? "tick: none yet"
				: `tick seq ${a.tickSeq} (${a.tickAgeMs === null ? "—" : formatDuration(a.tickAgeMs)} ago)`;
		const stale = a.tickStale ? " STALE (conductor not ticking)" : "";
		const count = (status: string): number => a.keys.filter((k) => k.status === status).length;
		lines.push(
			trunc(
				`autopilot: ${tick}${stale} | slots ${a.slotsUsed}/${a.slotsMax} | ` +
					`keys ${a.keys.length} (running ${count("running")}, stalled ${count("stalled")}, ` +
					`done ${count("done")}) | stall-ticks ${a.stallTicks}`,
				MONITOR_LINE_MAX,
			),
		);
		const stallByKey = new Map(a.stalls.map((stall) => [stall.key, stall]));
		const attention = a.keys.filter(
			(k) => k.status === "stalled" || k.inFlight > 0 || k.blockedBy.length > 0 || stallByKey.has(k.key),
		);
		for (const k of attention.slice(0, 6)) {
			const stall = stallByKey.get(k.key);
			const bits = [`  · ${k.key} ${k.phase}/${k.status}`];
			if (k.inFlight > 0) bits.push(`${k.inFlight} running`);
			if (stall !== undefined) {
				const error = stall.lastError === "" ? "" : ` "${stall.lastError}"`;
				bits.push(
					`advance ${stall.count}x ${stall.primaryClass} ` +
						`${stall.ageMs === null ? "—" : formatDuration(stall.ageMs)} ago${error}`,
				);
			}
			if (k.blockedBy.length > 0) bits.push(`deps blocked by ${k.blockedBy.join(",")}`);
			if (k.status === "stalled") {
				const gate = s.gates.find((g) => g.kind === "stalled" && g.key === k.key);
				const hint =
					gate === undefined
						? "-> /autopilot gate <id> approve|reject"
						: `-> /autopilot gate ${gate.id} approve|reject`;
				bits.push(gate === undefined ? hint : `${hint} (resume grants one round)`);
			}
			lines.push(trunc(bits.join(" | "), MONITOR_LINE_MAX));
		}
		if (attention.length > 6) lines.push(`  · +${attention.length - 6} more -> /autopilot status`);
	} else if (!s.autopilot.everEnabled) {
		lines.push("autopilot: not enabled (/autopilot enable)");
	} else {
		lines.push("autopilot: disabled (config.json enabled=false)");
	}

	if (s.workers.length === 0) {
		lines.push("workers: 0 running");
	} else {
		lines.push(`workers: ${s.workers.length} running (all keys)`);
		for (const w of s.workers) {
			lines.push(trunc(`  · ${w.taskKey}  ${Math.ceil(w.elapsedMs / 60_000)}m`, MONITOR_LINE_MAX));
		}
	}

	if (s.gates.length === 0) {
		lines.push("gates: 0 pending");
	} else if (s.gates.length === 1) {
		const g = s.gates[0];
		lines.push(
			trunc(`gates: 1 pending - ${g.id} (${g.kind}) -> /autopilot gate ${g.id} approve|reject`, MONITOR_LINE_MAX),
		);
	} else {
		const list = s.gates.map((g) => `${g.id} (${g.kind})`).join(", ");
		lines.push(trunc(`gates: ${s.gates.length} pending - ${list} -> /autopilot gates`, MONITOR_LINE_MAX));
	}

	return lines;
}

// ── Lifetime: start/stop/isMonitorActive (module-level singleton) ────────────

/** One monitor per window: the interval + apply callback live in module
 * memory only (AC-009 — never persisted; each pi process is its own module
 * instance, so windows cannot see each other's state). */
let monitorTimer: ReturnType<typeof setInterval> | null = null;
let monitorApply: ((lines: string[] | undefined) => void) | null = null;

export function isMonitorActive(): boolean {
	return monitorTimer !== null;
}

/**
 * Start the monitor. Idempotent: already active → true, nothing changes.
 * The FIRST FRAME renders synchronously before this returns (AC-001 with
 * zero ticks), then every `intervalMs` (default 4000ms) the state is
 * re-derived and re-rendered. A read that throws (transient file race)
 * skips that tick silently — the panel keeps the previous frame and the
 * next tick retries.
 */
export function startMonitor(
	projectDir: string,
	apply: (lines: string[] | undefined) => void,
	opts?: { intervalMs?: number; readState?: typeof readMonitorState; nowMs?: () => number },
): boolean {
	if (monitorTimer !== null) return true;
	const readState = opts?.readState ?? readMonitorState;
	const nowMs = opts?.nowMs ?? Date.now;
	const render = (): void => {
		try {
			apply(renderMonitorLines(readState(projectDir, nowMs())));
		} catch {
			// transient read error — keep the last frame, retry next tick
		}
	};
	render();
	monitorApply = apply;
	monitorTimer = setInterval(render, opts?.intervalMs ?? MONITOR_INTERVAL_MS);
	return true;
}

/**
 * Stop the monitor. Idempotent: not active → false, nothing happens (the
 * widget is NOT cleared in that case). When active, clears the interval and
 * calls `apply(undefined)` — clearing the widget — using the passed callback
 * or the one captured at start.
 */
export function stopMonitor(apply?: (lines: string[] | undefined) => void): boolean {
	if (monitorTimer === null) return false;
	clearInterval(monitorTimer);
	monitorTimer = null;
	const clear = apply ?? monitorApply;
	monitorApply = null;
	clear?.(undefined);
	return true;
}
