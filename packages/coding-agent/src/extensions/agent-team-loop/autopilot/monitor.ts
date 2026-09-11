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

import * as fs from "node:fs";
import * as path from "node:path";
import { getMwStatus, readServeMeta, serveStaleness } from "../shared/mw-runner.ts";
import { WorkerStore } from "../shared/worker-store.ts";
import { configPath, gatesDir, readConfig } from "./status-model.ts";

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
}

export interface MonitorSnapshot {
	serve: MonitorServe;
	conductor: MonitorConductor;
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
		else if (name === "stage") stage = /^-?\d+$/.test(value) ? Number.parseInt(value, 10) : null;
	}
	if (status !== "pending" || id === "" || kind === "") return null;
	return { id, kind, stage };
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

	return { serve, conductor, workers, gates };
}

// ── Render: renderMonitorLines (pure) ────────────────────────────────────────

function trunc(s: string, max: number): string {
	return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}

/** "45s", "3m", "2h 3m" — coarse serve uptime. */
function formatUptime(ms: number): string {
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
		const up = s.serve.upMs !== null ? `, up ${formatUptime(s.serve.upMs)}` : "";
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
