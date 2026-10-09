/**
 * console.ts — the /autopilot command set (goal-autopilot T-15, AC-015/016/
 * 018/025, design §4.1 / D-005 / D-109).
 *
 * The console is STATELESS: every command derives its view from the file
 * family alone (D-005 — console closed and reopened is just a normal
 * reopen). The one piece of persistent context, the timeline watermark, is
 * a pi session entry (`agent-team-loop:autopilot-seen`, same mechanism as
 * WATCH_ENTRY_TYPE) — the session file belongs to pi, not the console.
 *
 * Commands:
 *   /autopilot status [--json]        stage progress / gate queue / timeline
 *                                     watermark / per-key round budgets; the
 *                                     human view and --json come from the
 *                                     same derivation (view parity, VC-017)
 *   /autopilot gates                  pending gate list
 *   /autopilot gate <id> approve|reject [--note <text>]
 *                                     answer a gate under .mw/gates.lock
 *                                     (AC-016)
 *   /autopilot timeline [--since <iso>] [--all]
 *                                     replay events since the last-seen
 *                                     watermark (default), beats filtered;
 *                                     --all replays everything incl. beats
 *   /autopilot enable | disable       write config atomically; enable starts
 *                                     mw serve when it is not running
 *                                     (AC-025)
 *   /autopilot pause | resume         write config paused — the conductor
 *                                     stays alive but stops dispatching
 *   /autopilot monitor [on|off]        toggle the bottom monitor panel
 *                                     (serve/conductor/workers/gates,
 *                                     read-only, 4s refresh — AC-001..008;
 *                                     print mode degrades to a notice)
 *   /autopilot roadmap                stage summary view
 */

import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../../core/extensions/types.ts";
import { windowClaimId } from "../pm/ui-bridge.ts";
import { acquireLock, type LockOptions } from "../shared/file-lock.ts";
import { getMwStatus, restartMw, serveStaleness, startMw } from "../shared/mw-runner.ts";
import { answerGate } from "./gate-writer.ts";
import {
	evidenceFilePath,
	isMonitorActive,
	MONITOR_WIDGET_ID,
	readAutoGateMode,
	type readMonitorState,
	startMonitor,
	stopMonitor,
} from "./monitor.ts";
import {
	type AutopilotConfig,
	configLockPath,
	deriveStatusModel,
	type GateRecord,
	gatesDir,
	gatesLockPath,
	listGates,
	MISSING_FIELD_SENTINEL,
	nonBeatFilter,
	queryTimeline,
	type RoadmapStage,
	readConfig,
	readRoadmap,
	renderStatusText,
	saveConfig,
	type TimelineQuery,
	timelinePath,
	watermarkFromSince,
} from "./status-model.ts";

/** Session entry type persisting this window's timeline watermark (D-109
 * seq/watermark protocol — same mechanism as WATCH_ENTRY_TYPE). */
export const AUTOPILOT_SEEN_ENTRY_TYPE = "agent-team-loop:autopilot-seen";

export type EnsureMwOutcome = "started" | "already-running" | "restarted" | "spawn-failed";

export interface AutopilotConsoleDeps {
	/** Test seam for the enable flow's "ensure a CURRENT mw serve is running"
	 * step (AC-025 + stale-serve fix). Default: getMwStatus + startMw, plus a
	 * stale-serve restart — a serve predating the current code never spawns
	 * the conductor, so enable must not promise one. */
	ensureMwRunning?: (projectDir: string) => EnsureMwOutcome | Promise<EnsureMwOutcome>;
	/** Test seam for the monitor panel's state derivation (autopilot-monitor
	 * L1 fixtures). Default: readMonitorState from monitor.ts. */
	readMonitorState?: typeof readMonitorState;
	/** Test seam for the monitor poll interval (default 4000ms). */
	monitorIntervalMs?: number;
	/** Auto-show the monitor for autopilot-enabled projects on session start
	 * (default true). Set false to opt out (tests / embeddings). */
	autoMonitor?: boolean;
	/** Lock retry budget for the config read-modify-write handlers. Default:
	 * retries=6, baseDelayMs=20 (identical to the Python writer, worst case
	 * ~1.26s). Tests inject a tiny budget. */
	lockOpts?: LockOptions;
}

const USAGE =
	"Usage: /autopilot status [--json] | gates | gate <id> approve|reject [--note <text>] | " +
	"timeline [--since <iso>] [--all] | enable | disable | pause | resume | roadmap | monitor [on|off]";

export function registerAutopilotCommands(pi: ExtensionAPI, projectDir: string, deps: AutopilotConsoleDeps = {}): void {
	pi.registerCommand("autopilot", {
		description:
			"Autopilot console: status / gates / gate / timeline / enable / disable / pause / resume / roadmap / monitor",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const tokens = args
				.trim()
				.split(/\s+/)
				.filter((t) => t !== "");
			const sub = tokens[0] ?? "";
			const rest = tokens.slice(1);
			switch (sub) {
				case "status":
					cmdStatus(pi, ctx, projectDir, rest);
					return;
				case "gates":
					cmdGates(ctx, projectDir);
					return;
				case "gate":
					await cmdGate(ctx, projectDir, rest);
					return;
				case "timeline":
					cmdTimeline(pi, ctx, projectDir, rest);
					return;
				case "enable":
					await cmdSetEnabled(ctx, projectDir, true, deps);
					return;
				case "disable":
					await cmdSetEnabled(ctx, projectDir, false, deps);
					return;
				case "pause":
					await cmdSetPaused(ctx, projectDir, true, deps);
					return;
				case "resume":
					await cmdSetPaused(ctx, projectDir, false, deps);
					return;
				case "roadmap":
					cmdRoadmap(ctx, projectDir);
					return;
				case "monitor":
					cmdMonitor(ctx, projectDir, deps, rest);
					return;
				default:
					ctx.ui.notify(USAGE, "warning");
					return;
			}
		},
	});
}

/** Read this session's last-seen timeline watermark (D-109). A new session
 * has none → the caller replays from 0 (full replay). */
function readSeenWatermark(ctx: ExtensionCommandContext): { seq: number; ts: string } | undefined {
	try {
		const entries = ctx.sessionManager.getEntries();
		for (let i = entries.length - 1; i >= 0; i--) {
			const e = entries[i];
			if (e.type !== "custom" || e.customType !== AUTOPILOT_SEEN_ENTRY_TYPE) continue;
			const data = e.data as { seq?: unknown; ts?: unknown } | undefined;
			if (
				data !== undefined &&
				typeof data.seq === "number" &&
				Number.isInteger(data.seq) &&
				typeof data.ts === "string"
			) {
				return { seq: data.seq, ts: data.ts };
			}
		}
	} catch {
		// session entries unavailable — same as no watermark
	}
	return undefined;
}

// ── /autopilot status (AC-015/018, VC-017) ───────────────────────────────────

function cmdStatus(pi: ExtensionAPI, ctx: ExtensionCommandContext, projectDir: string, rest: string[]): void {
	const json = rest.includes("--json");
	const result = deriveStatusModel(projectDir);
	if (!result.ok) {
		ctx.ui.notify(`[autopilot] status unavailable: ${result.error}`, "error");
		return;
	}
	// D-109: every status/timeline view persists the last-seen watermark.
	const head = result.model.status.timeline;
	if (head.seq > 0) pi.appendEntry(AUTOPILOT_SEEN_ENTRY_TYPE, { seq: head.seq, ts: head.ts });
	ctx.ui.notify(json ? JSON.stringify(result.model.status, null, 2) : renderStatusText(result.model), "info");
}

// ── /autopilot gates (AC-015 pending queue, AC-026 13-line card) ─────────────

/** Per-kind consequence table for the card's A/R line. Code constants only —
 * no prose derivation and no model call (design D3.2 L3). */
const GATE_ACTIONS: Record<string, { approve: string; reject: string; reversible: string }> = {
	"stage-confirm": {
		approve: "stage opens, its keys become eligible",
		reject: "stage stays halted until a new proposal",
		reversible: "no",
	},
	"stage-close": {
		approve: "stage -> closed, next stage-confirm opens",
		reject: "stage -> halted, roadmap edit required",
		reversible: "no",
	},
	stalled: {
		approve: "one resume round granted for the key",
		reject: "key stays stalled (terminal)",
		reversible: "yes",
	},
	"budget-exhausted": {
		approve: "one resume round granted for the loop",
		reject: "loop stays exhausted (terminal)",
		reversible: "yes",
	},
	"goal-change": {
		approve: "new goal adopted, keys re-validate",
		reject: "goal change refused, halt and report",
		reversible: "no",
	},
	"xkey-authorize": {
		approve: "cross-key write ticket authorized",
		reject: "ticket refused, blocker recorded",
		reversible: "no",
	},
};

/** Card line width cap: each gate renders EXACTLY 13 lines, each <= 110 cols. */
const GATE_CARD_LINE_MAX = 110;

function cardClamp(value: string, max: number): string {
	return value.length <= max ? value : `${value.slice(0, max - 1)}…`;
}

function cardLine(value: string): string {
	return cardClamp(value, GATE_CARD_LINE_MAX);
}

/** "45s" / "3m" / "3.9h" / "15d" — waited-time for the card's L1. */
function formatWaited(ms: number): string {
	const s = Math.max(0, Math.floor(ms / 1000));
	if (s < 60) return `${s}s`;
	const m = Math.floor(s / 60);
	if (m < 60) return `${m}m`;
	const h = ms / 3_600_000;
	if (h < 48) return `${(Math.round(h * 10) / 10).toFixed(1)}h`;
	return `${Math.round(ms / 86_400_000)}d`;
}

/** `stage=N` / `key=K` scope token (identical to the monitor panel's). */
function gateScope(g: GateRecord): string {
	const parts: string[] = [];
	if (g.stage !== null) parts.push(`stage=${g.stage}`);
	if (g.key !== null && g.key !== "") parts.push(`key=${g.key}`);
	return parts.length === 0 ? "scope=none" : parts.join(" ");
}

/** Same-scope key for L8/L11 (stage + key). Answered gates of any kind in the
 * same scope count as replay history, but a keyed pending gate never inherits
 * a stage-level (keyless) answered gate as its history. */
function gateScopeKey(g: GateRecord): string {
	return `${g.stage ?? "-"}|${g.key ?? ""}`;
}

/** One evidence descriptor: `relpath (bytesB, sections=[...], mtime=iso)`. */
function describeEvidence(projectDir: string, ref: string): string {
	const body = ref.replace(/^[^:]*:/, "");
	const rel = body.split("#")[0].split("@")[0] || ref;
	const file = evidenceFilePath(projectDir, ref);
	if (file === null) return `${rel} (${MISSING_FIELD_SENTINEL})`;
	try {
		const stat = fs.statSync(file);
		const sections = fs
			.readFileSync(file, "utf8")
			.split(/\r\n|\r|\n/)
			.filter((line) => line.startsWith("## "))
			.map((line) => line.slice(3).trim())
			.filter((name) => name !== "");
		const sectionText = sections.length === 0 ? "[]" : `[${sections.slice(0, 4).join(",")}]`;
		return `${rel} (${stat.size}B, sections=${sectionText}, mtime=${new Date(stat.mtimeMs).toISOString()})`;
	} catch {
		return `${rel} (${MISSING_FIELD_SENTINEL})`;
	}
}

/** `DRIFT(...)` suffix when the newest evidence mtime is newer than the gate.
 * Same judgement as the monitor panel (design D5): mtime > created_at. */
function evidenceDrift(projectDir: string, refs: string[], createdAt: string): string | null {
	const createdMs = Date.parse(createdAt);
	if (Number.isNaN(createdMs)) return null;
	let newestMs = Number.NEGATIVE_INFINITY;
	for (const ref of refs) {
		const file = evidenceFilePath(projectDir, ref);
		if (file === null) continue;
		try {
			const mtimeMs = fs.statSync(file).mtimeMs;
			if (mtimeMs > newestMs) newestMs = mtimeMs;
		} catch {
			// transient stat race — skip this ref
		}
	}
	if (!Number.isFinite(newestMs) || newestMs <= createdMs) return null;
	return `mtime=${new Date(newestMs).toISOString()}, gate_created=${new Date(createdMs).toISOString()}`;
}

/** `key:verdict` summary from the verdicts_final snapshot (L5). */
function verdictSummary(value: unknown): string {
	if (!Array.isArray(value)) return MISSING_FIELD_SENTINEL;
	const parts: string[] = [];
	for (const item of value) {
		if (typeof item !== "object" || item === null) continue;
		const row = item as Record<string, unknown>;
		const key = typeof row.key === "string" ? row.key : "?";
		const verdict = typeof row.verdict === "string" ? row.verdict : "?";
		parts.push(`${key}:${verdict}`);
	}
	return parts.length === 0 ? MISSING_FIELD_SENTINEL : parts.join(",");
}

function jsonSummary(value: unknown): string {
	return value === null || value === undefined ? MISSING_FIELD_SENTINEL : JSON.stringify(value);
}

/** Keys that depend (transitively) on the gate's key, or every key of a
 * stage-level gate's stage. Null when the roadmap/stage is unavailable. */
function downstreamKeys(stage: RoadmapStage | undefined, gate: GateRecord): string[] | null {
	if (stage === undefined) return null;
	if (gate.key === null || gate.key === "") return stage.keys.map((k) => k.key);
	const found = new Set<string>();
	let grew = true;
	while (grew) {
		grew = false;
		for (const k of stage.keys) {
			if (found.has(k.key)) continue;
			if (k.dependsOn.includes(gate.key) || k.dependsOn.some((d) => found.has(d))) {
				found.add(k.key);
				grew = true;
			}
		}
	}
	return [...found];
}

/** The /autopilot gates card: header + EXACTLY 13 lines per pending gate, in a
 * fixed order, every line <= 110 columns (AC-026 / design D3.2). Missing v2
 * fields render the one sentinel literal — never prose, never a guess. */
export function renderGateCards(gates: GateRecord[], projectDir: string, nowMs: number): string[] {
	const pending = gates.filter((g) => g.status === "pending");
	if (pending.length === 0) return [`no pending gates (${gates.length} total)`];
	const roadmap = readRoadmap(projectDir);
	const stages = roadmap.ok ? roadmap.stages : [];
	const autoMode = readAutoGateMode(projectDir);
	const lines: string[] = [`${pending.length} pending gate(s):`];
	for (const g of pending) {
		const stage = g.stage === null ? undefined : stages.find((s) => s.number === g.stage);
		const createdMs = Date.parse(g.createdAt);
		const waited = Number.isNaN(createdMs) ? MISSING_FIELD_SENTINEL : formatWaited(Math.max(0, nowMs - createdMs));
		const scope = gateScope(g);
		const action = GATE_ACTIONS[g.kind];
		const approve = action === undefined ? MISSING_FIELD_SENTINEL : action.approve;
		const reject = action === undefined ? MISSING_FIELD_SENTINEL : action.reject;
		const reversible = action === undefined ? MISSING_FIELD_SENTINEL : action.reversible;
		const goal = stage === undefined || stage.goal === "" ? MISSING_FIELD_SENTINEL : stage.goal;
		const src = g.contextRefs.length > 1 ? g.contextRefs[1] : MISSING_FIELD_SENTINEL;
		const prior = gates.filter((h) => h.id !== g.id && h.status !== "pending" && gateScopeKey(h) === gateScopeKey(g));
		const history =
			prior.length === 0
				? "none"
				: prior.map((h) => `${h.id} [${h.kind}] ${gateScope(h)} ${h.status} ${h.answeredAt ?? "—"}`).join("; ");
		const withNote = prior.filter((h) => h.note !== null && h.note !== "");
		const lastNote = withNote[withNote.length - 1];
		const priorNote = lastNote === undefined ? "none" : `[${lastNote.id}] ${lastNote.note}`;
		const constraints = g.constraints.length === 0 ? MISSING_FIELD_SENTINEL : g.constraints.join("; ");
		const downstream = downstreamKeys(stage, g);
		const impact =
			downstream === null
				? MISSING_FIELD_SENTINEL
				: `downstream=${downstream.length} keys [${downstream.slice(0, 5).join(",")}]`;
		const roadmapStatus = stage === undefined ? MISSING_FIELD_SENTINEL : stage.status;
		const qTail = ` (full: ${g.path})`;
		const evidence =
			g.evidenceRefs.length === 0
				? `evidence: ${MISSING_FIELD_SENTINEL}`
				: `evidence: ${g.evidenceRefs
						.slice(0, 3)
						.map((ref) => describeEvidence(projectDir, ref))
						.join("; ")}${g.evidenceRefs.length > 3 ? ` +${g.evidenceRefs.length - 3} more` : ""}${
						evidenceDrift(projectDir, g.evidenceRefs, g.createdAt) === null
							? ""
							: ` DRIFT(${evidenceDrift(projectDir, g.evidenceRefs, g.createdAt)})`
					}`;

		lines.push(cardLine(`${g.id} [${g.kind}] ${scope} created=${g.createdAt} waited=${waited}`));
		lines.push(cardLine(`Q: ${cardClamp(g.question, Math.max(0, GATE_CARD_LINE_MAX - 3 - qTail.length))}${qTail}`));
		lines.push(
			cardLine(
				`A: approve = ${approve} (reversible: ${reversible}) | R: reject = ${reject} (reversible: ${reversible})`,
			),
		);
		lines.push(
			cardLine(
				`goal: ${cardClamp(goal, 60)} | goal_sha256=${g.goalSha256 ?? MISSING_FIELD_SENTINEL} | ` +
					`proposal_sha256=${g.proposalSha256 ?? MISSING_FIELD_SENTINEL} | roadmap_validation=${jsonSummary(g.roadmapValidation)}`,
			),
		);
		lines.push(
			cardLine(
				`reason: ${g.reasonCode ?? MISSING_FIELD_SENTINEL} src="${cardClamp(src, 60)}" | ` +
					`verdict: l3=${verdictSummary(g.verdictsFinal)}`,
			),
		);
		lines.push(cardLine(evidence));
		lines.push(
			cardLine(
				`impact: ${impact} | stage-close: ${g.kind === "stage-close" ? "this gate" : "na"} | ` +
					`next-stage: na | roadmap: ${roadmapStatus}`,
			),
		);
		lines.push(cardLine(`history: ${history}`));
		lines.push(
			cardLine(
				`default: ${g.defaultAction ?? MISSING_FIELD_SENTINEL} | ttl: ${g.expiresAt ?? MISSING_FIELD_SENTINEL} | auto=${autoMode}`,
			),
		);
		lines.push(
			cardLine(
				`budget: loop=${g.loop ?? MISSING_FIELD_SENTINEL} used=${g.usedRounds ?? MISSING_FIELD_SENTINEL}/${
					g.roundLimit ?? MISSING_FIELD_SENTINEL
				} credits=${g.creditsUsed ?? MISSING_FIELD_SENTINEL}`,
			),
		);
		lines.push(cardLine(`constraints: ${cardClamp(constraints, 50)} | prior: ${cardClamp(priorNote, 40)}`));
		lines.push(
			cardLine(`open-items: ${g.openItems === null ? MISSING_FIELD_SENTINEL : JSON.stringify(g.openItems)}`),
		);
		lines.push(
			cardLine(
				`answer: /autopilot gate ${g.id} approve|reject --note <text>  expected: ${g.answerSource ?? MISSING_FIELD_SENTINEL}`,
			),
		);
	}
	return lines;
}

function cmdGates(ctx: ExtensionCommandContext, projectDir: string): void {
	const { gates, errors } = listGates(projectDir);
	const lines = renderGateCards(gates, projectDir, Date.now());
	for (const e of errors) lines.push(`warning: ${e}`);
	ctx.ui.notify(lines.join("\n"), "info");
}

// ── /autopilot gate (AC-016) ──────────────────────────────────────────────────

async function cmdGate(ctx: ExtensionCommandContext, projectDir: string, rest: string[]): Promise<void> {
	const id = rest[0] ?? "";
	const decision = rest[1] ?? "";
	if (id === "" || (decision !== "approve" && decision !== "reject")) {
		ctx.ui.notify("Usage: /autopilot gate <id> approve|reject [--note <text>]", "warning");
		return;
	}
	if (!/^gate-\d+$/.test(id)) {
		ctx.ui.notify(`[autopilot] invalid gate id '${id}' (expected gate-<digits>)`, "error");
		return;
	}
	let note: string | undefined;
	const noteIdx = rest.indexOf("--note");
	if (noteIdx >= 0)
		note =
			rest
				.slice(noteIdx + 1)
				.join(" ")
				.trim() || undefined;

	const result = await answerGate({
		gateFile: path.join(gatesDir(projectDir), `${id}.md`),
		lockFile: gatesLockPath(projectDir),
		decision,
		note,
		answeredBy: windowClaimId(),
	});
	if (result.ok) {
		ctx.ui.notify(
			`[autopilot] ${id} ${result.status} (by ${windowClaimId()}) — the conductor reads the answer within one poll interval (<=5s).`,
			"info",
		);
		return;
	}
	ctx.ui.notify(`[autopilot] gate answer failed: ${result.error}`, "error");
	const pending = listGates(projectDir).gates.filter((g) => g.status === "pending");
	if (pending.length > 0) ctx.ui.notify(`pending gates: ${pending.map((g) => g.id).join(", ")}`, "info");
}

// ── /autopilot timeline (AC-015 offline replay, D-109) ───────────────────────

function cmdTimeline(pi: ExtensionAPI, ctx: ExtensionCommandContext, projectDir: string, rest: string[]): void {
	const all = rest.includes("--all");
	let since: string | undefined;
	const sinceIdx = rest.indexOf("--since");
	if (sinceIdx >= 0) since = rest[sinceIdx + 1];
	if (since !== undefined && Number.isNaN(Date.parse(since))) {
		ctx.ui.notify(`[autopilot] invalid --since value '${since}' (expected an ISO-8601 timestamp)`, "error");
		return;
	}
	const tlPath = timelinePath(projectDir);
	// Default = this session's last-seen watermark (a new session replays
	// everything); --since maps an explicit timestamp onto the seq protocol;
	// --all replays the full retained chain including beats.
	let mark = 0;
	if (since !== undefined) mark = watermarkFromSince(tlPath, since);
	else if (!all) mark = readSeenWatermark(ctx)?.seq ?? 0;
	const query = queryTimeline(tlPath, mark, all ? undefined : nonBeatFilter());
	ctx.ui.notify(renderTimelineText(query, mark), "info");
	if (query.head !== undefined) {
		pi.appendEntry(AUTOPILOT_SEEN_ENTRY_TYPE, { seq: query.head.seq, ts: query.head.ts });
	}
}

function renderTimelineText(query: TimelineQuery, mark: number): string {
	const lines: string[] = [`timeline replay (from seq=${mark}) — ${query.events.length} event(s)`];
	if (query.pruned > 0) lines.push(`${query.pruned} events pruned (older than the retained rotation generations)`);
	for (const ev of query.events) {
		const stage = ev.stage === null ? "" : ` stage=${ev.stage}`;
		const detail = ev.detail === "" ? "" : ` ${ev.detail}`;
		lines.push(`${ev.seq} ${ev.ts} ${ev.ev} key=${ev.key}${stage}${detail}`);
	}
	if (query.events.length === 0) lines.push("(no events)");
	if (query.skipped > 0) lines.push(`${query.skipped} unparsable line(s) skipped`);
	return lines.join("\n");
}

// ── /autopilot enable|disable (AC-025) and pause|resume ──────────────────────

/** Lock retry budget frozen by plan §2.2 — identical to the Python writer
 * (`mw_common.acquire_lock(retries=6, base_delay=0.02)`). */
export const DEFAULT_CONFIG_LOCK_OPTS: LockOptions = { retries: 6, baseDelayMs: 20 };

/** Read-modify-write config.json under `.mw/autopilot-config.lock` (D-006).
 * The whole read → mutate → atomic write runs inside the lock: two windows (or
 * a window and the `mw autopilot verify` CLI) can otherwise interleave and roll
 * each other back. A lock that cannot be taken fails closed — the caller
 * reports the error and NOTHING is written. The lock deliberately lives here,
 * not inside `saveConfig` (the primitive is not re-entrant, D-006). */
export async function saveConfigLocked(
	projectDir: string,
	mutate: (config: AutopilotConfig) => AutopilotConfig,
	lockOpts?: LockOptions,
): Promise<{ ok: true } | { ok: false; error: string }> {
	const lockFile = configLockPath(projectDir);
	let release: () => void;
	try {
		release = await acquireLock(lockFile, { ...DEFAULT_CONFIG_LOCK_OPTS, ...lockOpts });
	} catch (err) {
		return {
			ok: false,
			error:
				`could not take ${lockFile} (another autopilot writer holds it; ` +
				`delete the file if it is stale): ${err instanceof Error ? err.message : String(err)}`,
		};
	}
	try {
		const cfg = readConfig(projectDir);
		if (!cfg.ok) return { ok: false, error: cfg.error };
		return saveConfig(projectDir, mutate(cfg.config));
	} finally {
		release();
	}
}

async function cmdSetEnabled(
	ctx: ExtensionCommandContext,
	projectDir: string,
	enabled: boolean,
	deps: AutopilotConsoleDeps,
): Promise<void> {
	const saved = await saveConfigLocked(projectDir, (config) => ({ ...config, enabled }), deps.lockOpts);
	if (!saved.ok) {
		ctx.ui.notify(`[autopilot] ${saved.error}`, "error");
		return;
	}
	if (!enabled) {
		ctx.ui.notify(
			"[autopilot] disabled — mw serve stops the conductor on its next config poll (if running).",
			"info",
		);
		return;
	}
	const outcome = await (deps.ensureMwRunning ?? defaultEnsureMwRunning)(projectDir);
	if (outcome === "started") {
		ctx.ui.notify(
			"[autopilot] enabled + mw serve starting — the conductor spawns within ~1s of serve startup (AC-025).",
			"info",
		);
	} else if (outcome === "restarted") {
		ctx.ui.notify("[autopilot] enabled — stale serve restarted; the conductor spawns within ~1s (AC-025).", "info");
	} else if (outcome === "already-running") {
		ctx.ui.notify(
			"[autopilot] enabled — mw serve is running and spawns the conductor on its next config poll (<=1s).",
			"info",
		);
	} else {
		ctx.ui.notify("[autopilot] enabled, but mw serve could not be started — run /mw start or set MW_PY.", "warning");
	}
}

/** The /mw command pattern, extended with the stale-serve restart: a
 * running-but-stale serve never spawns the conductor (its supervision code
 * predates the feature), so restart it before promising one. */
async function defaultEnsureMwRunning(projectDir: string): Promise<EnsureMwOutcome> {
	if (getMwStatus(projectDir).running) {
		const stale = serveStaleness(projectDir);
		if (stale?.stale) {
			const r = await restartMw(projectDir);
			if (r === "restarted") return "restarted";
			return "spawn-failed"; // restart failed — surface it instead of a false promise
		}
		return "already-running";
	}
	return startMw(projectDir) ? "started" : "spawn-failed";
}

async function cmdSetPaused(
	ctx: ExtensionCommandContext,
	projectDir: string,
	paused: boolean,
	deps: AutopilotConsoleDeps,
): Promise<void> {
	const saved = await saveConfigLocked(projectDir, (config) => ({ ...config, paused }), deps.lockOpts);
	if (!saved.ok) {
		ctx.ui.notify(`[autopilot] ${saved.error}`, "error");
		return;
	}
	ctx.ui.notify(
		paused
			? "[autopilot] paused — the conductor stays alive but dispatches nothing until /autopilot resume."
			: "[autopilot] resumed — the conductor resumes dispatching on its next tick.",
		"info",
	);
}

// ── /autopilot monitor (autopilot-monitor T-01, AC-001..008) ─────────────────

/** Toggle the bottom monitor panel. `on`/`off` are explicit; no argument
 * toggles (D-006). Print mode (ctx.hasUI === false) is guarded BEFORE any
 * UI path: the command degrades to a notice, never starts the poll loop,
 * never throws (AC-006 — the goal-nudge 8a063f4d9 lesson). */
function cmdMonitor(
	ctx: ExtensionCommandContext,
	projectDir: string,
	deps: AutopilotConsoleDeps,
	rest: string[],
): void {
	if (!ctx.hasUI) {
		ctx.ui.notify(
			"[autopilot] monitor needs a visual UI — there is no visual UI in this mode, so no panel was started.",
			"warning",
		);
		return;
	}
	const arg = rest[0] ?? "";
	if (arg !== "" && arg !== "on" && arg !== "off") {
		ctx.ui.notify("Usage: /autopilot monitor [on|off]", "warning");
		return;
	}
	const apply = (lines: string[] | undefined): void => {
		ctx.ui.setWidget(MONITOR_WIDGET_ID, lines, { placement: "belowEditor" });
	};
	if (arg === "off" || (arg === "" && isMonitorActive())) {
		const stopped = stopMonitor(apply);
		if (arg === "off") monitorSuppressed = true; // stays off for this session
		ctx.ui.notify(
			stopped ? "[autopilot] monitor off — bottom panel cleared." : "[autopilot] monitor was not running.",
			"info",
		);
		return;
	}
	monitorSuppressed = false;
	startMonitor(projectDir, apply, { intervalMs: deps.monitorIntervalMs, readState: deps.readMonitorState });
	ctx.ui.notify(
		"[autopilot] monitor on — serve/conductor/autopilot/workers/gates panel below the editor, refreshed every 4s. " +
			"/autopilot monitor off closes it.",
		"info",
	);
}

/** Session-scoped suppression flag for the auto-shown panel (AC-008): memory
 * only, never persisted — an explicit `/autopilot monitor off` keeps the panel
 * closed for this session while `/autopilot monitor on` clears it again. */
let monitorSuppressed = false;

/** Forget the session-level suppression. The test suite uses it so one case's
 * `/autopilot monitor off` cannot leak into the next (a production session is
 * one process lifetime; a future session_shutdown hook can call this too). */
export function resetMonitorSuppression(): void {
	monitorSuppressed = false;
}

/** Show the monitor automatically for autopilot-enabled projects.
 *
 * Called from the PM session_start hook, the first place a UI context exists
 * (registerAutopilotCommands runs at extension load, with no ctx). Feedback for
 * a stalled key has to be visible without remembering a command to run — the
 * E2Feature incident ran 2h35m unnoticed because nothing surfaced it.
 *
 * Returns true when the panel is showing. Idempotent: an already-active panel
 * is left alone (and reports true). Guards, in order: no visual UI, the
 * autoMonitor opt-out, an explicit session-level `/autopilot monitor off`,
 * and a config that is absent/invalid or `enabled: false`. */
export function autoStartMonitor(ctx: ExtensionContext, projectDir: string, deps: AutopilotConsoleDeps = {}): boolean {
	if (!ctx.hasUI) return false;
	if (deps.autoMonitor === false) return false;
	if (monitorSuppressed) return false;
	if (isMonitorActive()) return true;
	const cfg = readConfig(projectDir);
	if (!cfg.ok || !cfg.config.enabled) return false;
	startMonitor(
		projectDir,
		(lines: string[] | undefined): void => {
			ctx.ui.setWidget(MONITOR_WIDGET_ID, lines, { placement: "belowEditor" });
		},
		{ intervalMs: deps.monitorIntervalMs, readState: deps.readMonitorState },
	);
	return true;
}

// ── /autopilot roadmap (summary view) ────────────────────────────────────────

function cmdRoadmap(ctx: ExtensionCommandContext, projectDir: string): void {
	const roadmap = readRoadmap(projectDir);
	if (!roadmap.ok) {
		ctx.ui.notify(`[autopilot] ${roadmap.error}`, "warning");
		return;
	}
	const lines: string[] = [];
	if (roadmap.stages.length === 0) lines.push("(no stages parsed)");
	for (const stage of roadmap.stages) {
		lines.push(`Stage ${stage.number}: ${stage.title} — ${stage.status}`);
		lines.push(`  goal: ${stage.goal === "" ? "(missing)" : stage.goal}`);
		const keys = stage.keys.map((k) => `${k.key}=${stage.keyStatus[k.key] ?? "-"}`).join(", ");
		lines.push(`  keys: ${keys === "" ? "(none)" : keys}`);
	}
	for (const w of roadmap.warnings) lines.push(`warning: ${w}`);
	ctx.ui.notify(lines.join("\n"), "info");
}
