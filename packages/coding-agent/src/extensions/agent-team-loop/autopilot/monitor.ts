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
import { IndexStore } from "../shared/index-store.ts";
import { getMwStatus, readServeMeta, serveStaleness } from "../shared/mw-runner.ts";
import { type WorkerEntry, WorkerStore, workerBelongsToKey, workerOwnerKey } from "../shared/worker-store.ts";
import {
	BEAT_EV,
	blockedOnHuman,
	type ConfigResult,
	configPath,
	DEFAULT_CONFIG,
	gatesDir,
	type RoadmapResult,
	readConfig,
	readRoadmap,
	TERMINAL_WORKER_STATUSES,
	type TimelineEvent,
	timelinePath,
} from "./status-model.ts";

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
}

/** The auto-decision kill switch, read raw so the value stays visible even
 * while the TS config mirror does not yet declare `auto_gate_mode` (T-03 owns
 * the key on the Python side). Missing/unreadable config = off. */
export function readAutoGateMode(projectDir: string): string {
	try {
		const parsed: unknown = JSON.parse(fs.readFileSync(configPath(projectDir), "utf8"));
		if (typeof parsed === "object" && parsed !== null) {
			const mode = (parsed as Record<string, unknown>).auto_gate_mode;
			if (mode === "off" || mode === "shadow" || mode === "live") return mode;
		}
	} catch {
		// missing/invalid config — autopilot never enabled
	}
	return "off";
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

// ── Collect: readMonitorState (pure, read-only) ──────────────────────────────

/** Scan one gate file's frontmatter for the fields the panel needs (D-004
 * line scan — no YAML dependency). Returns the gate only when it is
 * `status: pending` with a usable id/kind; anything else (answered gates,
 * non-gate or unparsable files) is skipped. Also captures `created_at`,
 * `reason_code` and `evidence_refs` so the panel can show age/reason and
 * compute the evidence-drift marker (AC-012). */
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
	let createdAt: string | null = null;
	let reasonCode: string | null = null;
	const evidenceRefs: string[] = [];
	let activeList: string | null = null;
	for (let i = 1; i < lines.length; i++) {
		const line = lines[i];
		if (line.trim() === "---") break; // frontmatter closed
		if (activeList === "evidence_refs") {
			const item = /^[ \t]+-[ \t]+(.*)$/.exec(line);
			if (item !== null) {
				const ref = (item[1] ?? "").trim().replace(/^'(.*)'$/, "$1");
				if (ref !== "") evidenceRefs.push(ref);
				continue;
			}
			activeList = null; // dedent
		}
		const m = /^([A-Za-z_][A-Za-z0-9_]*):[ \t]*(.*?)[ \t]*$/.exec(line);
		if (m === null) continue; // list items, blank lines, etc.
		const name = m[1] ?? "";
		const value = m[2] ?? "";
		if (name === "id") id = value;
		else if (name === "kind") kind = value;
		else if (name === "status") status = value;
		else if (name === "key") key = value;
		else if (name === "stage") stage = /^-?\d+$/.test(value) ? Number.parseInt(value, 10) : null;
		else if (name === "created_at") createdAt = value === "" ? null : value;
		else if (name === "reason_code") reasonCode = value === "" ? null : value;
		else if (name === "evidence_refs") {
			if (value === "") {
				activeList = "evidence_refs";
			} else if (value === "[]") {
				activeList = null;
			} else if (value.startsWith("'")) {
				// v2 renderer shape: a single-line JSON array substring.
				try {
					const decoded: unknown = JSON.parse(value.replace(/^'/, "").replace(/'$/, "").replaceAll("''", "'"));
					if (Array.isArray(decoded)) {
						for (const item of decoded) if (typeof item === "string" && item !== "") evidenceRefs.push(item);
					}
				} catch {
					// unparsable — drift stays unknown rather than guessing
				}
			}
		}
	}
	if (status !== "pending" || id === "" || kind === "") return null;
	return { id, kind, stage, key, createdAt, reasonCode, evidenceRefs, ageMs: null, drift: null };
}

/** Resolve one `evidence_refs` entry (`kind:relpath[#sha][@mtime_ns]`)
 * against the project's `.agenticdoc/` first, then the project root. */
export function evidenceFilePath(projectDir: string, ref: string): string | null {
	const body = ref.replace(/^[^:]*:/, "");
	const rel = body.split("#")[0].split("@")[0] ?? "";
	if (rel === "") return null;
	const underAgenticdoc = path.join(projectDir, ".agenticdoc", rel);
	if (fs.existsSync(underAgenticdoc)) return underAgenticdoc;
	const underRoot = path.join(projectDir, rel);
	return fs.existsSync(underRoot) ? underRoot : null;
}

/** `DRIFT(...)` detail when the newest evidence mtime is newer than the gate's
 * created_at, else null. Never throws: an unstattable ref is skipped. */
function gateDriftDetail(projectDir: string, gate: MonitorGate, createdAtMs: number | null): string | null {
	if (createdAtMs === null || gate.evidenceRefs === undefined || gate.evidenceRefs.length === 0) return null;
	let newestMs = Number.NEGATIVE_INFINITY;
	for (const ref of gate.evidenceRefs) {
		const file = evidenceFilePath(projectDir, ref);
		if (file === null) continue;
		try {
			const mtimeMs = fs.statSync(file).mtimeMs;
			if (mtimeMs > newestMs) newestMs = mtimeMs;
		} catch {
			// transient stat race — skip this ref
		}
	}
	if (!Number.isFinite(newestMs) || newestMs <= createdAtMs) return null;
	// Compact by design: the panel only flags the drift; the full mtime pair
	// lives in the /autopilot gates card (L6) and `mw doctor`.
	return "mtime>created_at";
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
	const conductor: MonitorConductor = {
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
	const workers: MonitorWorker[] = [];
	let nonTerminalRows = 0;
	for (const entry of new WorkerStore(path.join(projectDir, ".agenticdoc")).readAll()) {
		// In-flight means NON-TERMINAL, not merely `running`: a `pending` row
		// starts on the next tick, so counting it prevents a false
		// BLOCKED_ON_HUMAN (design D-008/F6, same set as _TERMINAL_STATUSES).
		if (!TERMINAL_WORKER_STATUSES.has(entry.status)) nonTerminalRows += 1;
		if (entry.status !== "running") continue;
		const dispatched = Date.parse(entry.dispatchedAt);
		if (Number.isNaN(dispatched)) continue;
		workers.push({ ...entry, elapsedMs: Math.max(0, nowMs - dispatched) });
	}
	workers.sort((a, b) => b.elapsedMs - a.elapsedMs || a.taskKey.localeCompare(b.taskKey));

	// gates — pending queue only, seq order (the directory scan is the queue).
	// Age and the evidence-drift marker are computed HERE (collect) so the
	// renderer stays a pure function of the snapshot.
	const gates: MonitorGate[] = [];
	try {
		const dir = gatesDir(projectDir);
		for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
			if (!entry.isFile() || !/^gate-\d+\.md$/.test(entry.name)) continue;
			const gate = scanPendingGate(path.join(dir, entry.name));
			if (gate === null) continue;
			const createdMs = gate.createdAt === null || gate.createdAt === undefined ? null : Date.parse(gate.createdAt);
			const createdKnown = createdMs !== null && !Number.isNaN(createdMs) ? createdMs : null;
			gate.ageMs = createdKnown === null ? null : Math.max(0, nowMs - createdKnown);
			gate.drift = gateDriftDetail(projectDir, gate, createdKnown);
			gates.push(gate);
		}
	} catch {
		// gates dir missing — empty queue
	}
	gates.sort((a, b) => a.id.localeCompare(b.id));

	const autopilot = deriveAutopilotPanel(projectDir, nowMs, workers);

	// G2 AC-007 (D-008): the file-only truth table, shared verbatim with the
	// Python reminder (T-07). Collected once here; the renderer adds the
	// TS-only third axis (`!tickStale`) on top.
	const blocked = blockedOnHuman(gates.length, nonTerminalRows);
	// G4 AC-015 (D-017): stamp the frame here so ANY caller of readMonitorState
	// gets a self-attesting snapshot; startMonitor then advances `tickCount`
	// and re-stamps `collectedAtMs` with its own (possibly injected) clock.
	return {
		serve,
		conductor,
		autopilot,
		workers,
		gates,
		blockedOnHuman: blocked,
		collectedAtMs: nowMs,
		tickCount: monitorTickCount,
	};
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
			inFlight: workers.filter((w) => workerBelongsToKey(w, key)).length,
			blockedBy: (depsByKey.get(key) ?? []).filter(
				(dep) => !["done", "closed-legacy"].includes(statusByKey.get(dep) ?? ""),
			),
		});
	}
	const busyKeys = new Set<string>();
	for (const w of workers) {
		const owner = workerOwnerKey(w);
		if (owner !== "" && allKeys.includes(owner) && workerBelongsToKey(w, owner)) busyKeys.add(owner);
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

/** G4 AC-015 (D-017): the panel header doubles as the frame's
 * self-attestation. It carries the STALE PANEL alert plus the absolute
 * `collected` stamp and monotonic `tick` count. Bits are appended in priority
 * order and truncated/dropped before the alert can be cut away, so a long
 * detail can never hide "STALE PANEL". */
function monitorHeaderLine(s: MonitorSnapshot): string {
	const bits: string[] = [];
	if (s.stale === true) bits.push(`STALE PANEL (${s.staleDetail ?? "no refresh"})`);
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
		if (room > 8) line = `${line} ${trunc(bit, room)}`;
		break;
	}
	return line;
}

/**
 * Render the snapshot as the fixed-section panel. Every section is always
 * present (0 running folds to the "workers: 0 running" header, 0 pending to
 * "gates: 0 pending") so the panel's height — and therefore the editor
 * layout — never flickers between ticks (§9). All lines cap at
 * MONITOR_LINE_MAX columns with an ellipsis. The first line is the
 * self-attesting header (see {@link monitorHeaderLine}).
 */
export function renderMonitorLines(s: MonitorSnapshot): string[] {
	const lines: string[] = [monitorHeaderLine(s)];
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

	const autoToken = ` | auto=${s.conductor.autoMode ?? "off"}`;
	if (!s.conductor.everEnabled) {
		lines.push(`conductor: not enabled (/autopilot enable)${autoToken}`);
	} else if (s.conductor.pid !== null && s.conductor.alive) {
		lines.push(
			trunc(
				`conductor: PID ${s.conductor.pid} alive | ${conductorIntent(s.conductor)}${autoToken}`,
				MONITOR_LINE_MAX,
			),
		);
	} else if (s.conductor.pid !== null) {
		lines.push(`conductor: dead (pid ${s.conductor.pid} stale)${autoToken}`);
	} else {
		lines.push(trunc(`conductor: not running | ${conductorIntent(s.conductor)}${autoToken}`, MONITOR_LINE_MAX));
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
		// G2 AC-008 (VC-011): first-glance "is a human actually the blocker?"
		// marker — a pending gate with zero non-terminal workers. The third
		// truth-table axis is render-time: a stale tick already prints STALE on
		// the line above, so the marker stays off instead of double-reporting.
		if (s.blockedOnHuman && !a.tickStale) {
			lines.push(
				trunc(
					`BLOCKED_ON_HUMAN: ${s.gates.length} pending gate(s), 0 non-terminal workers -> /autopilot gates`,
					MONITOR_LINE_MAX,
				),
			);
		}
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
	} else {
		// One line per pending gate (AC-012): the first carries the count, the
		// rest indent like the attention rows. age/reason/DRIFT are collected
		// facts, never derived from the question prose. On overflow the optional
		// tokens are dropped whole (reason -> age -> scope -> drift) so `id`,
		// `kind` and the complete answer entry always survive (design D3.1).
		s.gates.forEach((g, index) => {
			const head = index === 0 ? `gates: ${s.gates.length} pending - ` : "  · ";
			const base = `${head}${g.id} (${g.kind})`;
			const answer = ` -> /autopilot gate ${g.id} approve|reject`;
			const tokens: Array<{ text: string; drop: number }> = [];
			const scope = g.stage !== null ? ` stage=${g.stage}` : g.key !== "" ? ` key=${g.key}` : "";
			if (scope !== "") tokens.push({ text: scope, drop: 3 });
			if (g.ageMs !== null && g.ageMs !== undefined)
				tokens.push({ text: ` age=${formatDuration(g.ageMs)}`, drop: 2 });
			if (g.reasonCode !== null && g.reasonCode !== undefined)
				tokens.push({ text: ` reason=${g.reasonCode}`, drop: 1 });
			if (g.drift !== null && g.drift !== undefined) tokens.push({ text: ` DRIFT(${g.drift})`, drop: 4 });
			let line = `${base}${tokens.map((t) => t.text).join("")}${answer}`;
			for (const drop of [1, 2, 3, 4]) {
				if (line.length <= MONITOR_LINE_MAX) break;
				line = `${base}${tokens
					.filter((t) => t.drop > drop)
					.map((t) => t.text)
					.join("")}${answer}`;
			}
			lines.push(trunc(line, MONITOR_LINE_MAX));
		});
	}

	return lines;
}

// ── Lifetime: start/stop/isMonitorActive (module-level singleton) ────────────

/** One monitor per window: the interval + apply callback live in module
 * memory only (AC-009 — never persisted; each pi process is its own module
 * instance, so windows cannot see each other's state). */
let monitorTimer: ReturnType<typeof setInterval> | null = null;
let monitorApply: ((lines: string[] | undefined) => void) | null = null;

/** G4 AC-015 (D-017): monotonic count of SUCCESSFUL collections. Module-level
 * and deliberately NOT reset by stop()/start() — a re-arm must not make a
 * frozen panel look fresh again by returning to tick 0. */
let monitorTickCount = 0;

/** G4 AC-017 (D-018): the last frame whose read succeeded. A degraded frame
 * reuses this payload verbatim. Run-scoped: `startMonitor` clears it, because
 * a new run has no previous frame to fall back to. */
let lastGoodSnapshot: MonitorSnapshot | null = null;

/** G4 AC-015: wall-clock anchor of the current run — the time of the last
 * SUCCESSFUL collection, or the run start while nothing has succeeded yet. A
 * degraded frame keeps showing it so a frozen panel is self-evident (the
 * stamp must not advance just because the read failed again). */
let anchorAtMs: number | null = null;

export function isMonitorActive(): boolean {
	return monitorTimer !== null;
}

/** One-line error summary for a degraded frame (`name: message`), never empty
 * and never thrown. */
function errorSummary(err: unknown): string {
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
function degradedSnapshot(err: unknown, nowMs: number, intervalMs: number): MonitorSnapshot {
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
	if (lastGoodSnapshot !== null) return { ...lastGoodSnapshot, ...diagnostics };
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
export function startMonitor(
	projectDir: string,
	apply: (lines: string[] | undefined) => void,
	opts?: { intervalMs?: number; readState?: typeof readMonitorState; nowMs?: () => number },
): boolean {
	if (monitorTimer !== null) return true;
	const readState = opts?.readState ?? readMonitorState;
	const nowMs = opts?.nowMs ?? Date.now;
	const intervalMs = opts?.intervalMs ?? MONITOR_INTERVAL_MS;
	// A fresh run has no reusable frame: if the FIRST tick fails there is
	// nothing to fall back to and the frame must say so (D-018 boundary). The
	// anchor starts at the run start and only moves on a successful collection.
	lastGoodSnapshot = null;
	anchorAtMs = nowMs();
	const render = (): void => {
		const now = nowMs();
		let frame: MonitorSnapshot;
		try {
			const collected = readState(projectDir, now);
			monitorTickCount += 1;
			// Stamp the successful collection: absolute wall clock + the
			// monotonic count are the frame's self-attestation (AC-015).
			frame = { ...collected, collectedAtMs: now, tickCount: monitorTickCount };
			lastGoodSnapshot = frame;
			anchorAtMs = now;
		} catch (err) {
			// G4 AC-017: no longer swallow the whole tick — degrade instead.
			frame = degradedSnapshot(err, now, intervalMs);
		}
		try {
			apply(renderMonitorLines(frame));
		} catch {
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
export function stopMonitor(apply?: (lines: string[] | undefined) => void): boolean {
	if (monitorTimer === null) return false;
	clearInterval(monitorTimer);
	monitorTimer = null;
	const clear = apply ?? monitorApply;
	monitorApply = null;
	clear?.(undefined);
	return true;
}
