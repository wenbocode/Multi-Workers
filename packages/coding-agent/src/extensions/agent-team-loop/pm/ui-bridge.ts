import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { Type } from "typebox";
import type { ExtensionAPI, ExtensionCommandContext, ExtensionContext } from "../../../core/extensions/types.ts";
import { formatHeartbeatAge, HEARTBEAT_STALE_MS, readTaskProgress } from "../shared/heartbeat.ts";
import { type IndexStore, readIndexMdActive } from "../shared/index-store.ts";
import type { DoctorJson } from "../shared/mw-runner.ts";
import { buildMw, doctorMw, getMwStatus, initMw, startMw, stopMw } from "../shared/mw-runner.ts";
import { SCRATCH_WORKERS_KEY, workerTaskDir } from "../shared/paths.ts";
import { DOC_GATE_HINT, dispatchDocGaps, formatDocsBadge, readPhaseDocs } from "../shared/phase-docs.ts";
import { phaseAuditWarnings } from "../shared/pm-state-guard.ts";
import type { WorkerEntry, WorkerStatus, WorkerStore } from "../shared/worker-store.ts";
import { dispatchTask } from "./task-dispatcher.ts";

/** Owner key for a worker task, synchronized with this window's watch state.
 * Explicit key wins (deliberate choice — no warning). Otherwise resolve the
 * active key: latest-active row in _index.parallel, then the degraded
 * _index.md `active:` pointer, then _scratch. When auto-resolution lands on
 * a key other than what this window watches, warn once per (watch, owner)
 * pair — the dispatch follows the active key, never a stale watch. */
export function resolveOwnerKeyWithSync(
	pi: ExtensionAPI,
	indexStore: IndexStore,
	watch: PmWatchState,
	explicit: string | undefined,
	agenticdocRoot: string,
): string {
	const explicitKey = (explicit ?? "").trim();
	if (explicitKey) return explicitKey;
	const owner = indexStore.activeKey() ?? readIndexMdActive(agenticdocRoot) ?? SCRATCH_WORKERS_KEY;
	if (watch.key && watch.key !== owner) warnOwnerMismatchOnce(pi, watch.key, owner);
	return owner;
}

/** Warned (watch -> owner) pairs this session. displaySummary persists the
 * warning to the transcript (LLM-visible), so once per pair is enough. */
const warnedOwnerMismatches = new Set<string>();

function warnOwnerMismatchOnce(pi: ExtensionAPI, watchKey: string, ownerKey: string): void {
	const pair = `${watchKey}->${ownerKey}`;
	if (warnedOwnerMismatches.has(pair)) return;
	warnedOwnerMismatches.add(pair);
	displaySummary(
		pi,
		`[mw] owner-key mismatch: this window watches '${watchKey}' but the active key is '${ownerKey}' — ` +
			`dispatching under '${ownerKey}'. Run /pm-key switch ${ownerKey} to align the window.`,
	);
}

export function displaySummary(pi: ExtensionAPI, summary: string): void {
	pi.sendMessage({
		customType: "agent-team-loop:worker-summary",
		content: summary,
		display: true,
		details: summary,
	});
}

/** Deliver a message into the conversation AND trigger a PM turn — the
 * shared "wake the PM" channel (finish calls and mid-run escalations).
 * `pi.sendMessage` without `triggerTurn` only injects the message into LLM
 * context: it displays in the transcript, but an idle PM never wakes up.
 * With `triggerTurn: true` an idle PM starts an LLM turn immediately; a
 * streaming PM gets the text steered into the current turn. Informational
 * notices (init, mw start, gate skips) stay passive via displaySummary —
 * they must not spend agent turns. */
export function deliverPmAlert(pi: ExtensionAPI, text: string): void {
	pi.sendMessage(
		{
			customType: "agent-team-loop:worker-summary",
			content: text,
			display: true,
			details: text,
		},
		{ triggerTurn: true },
	);
}

/** Deliver a terminal worker result (the "finish call" of dispatch →
 * monitor → finish call → pm run). See deliverPmAlert for the channel. */
export function deliverWorkerResult(pi: ExtensionAPI, summary: string): void {
	deliverPmAlert(pi, summary);
}

// ── Per-window watch state + bottom progress widget ────────────────────────

export interface PmWatchState {
	/** AgenticTask key this window explicitly executes; undefined = not watching. */
	key: string | undefined;
}

export interface PmUiHolder {
	/** Latest ExtensionContext, captured on session_start so background timers
	 * can render UI. Undefined before session start or in headless runs. */
	ctx: ExtensionContext | undefined;
}

/** Session entry type persisting this window's watched key across restarts. */
export const WATCH_ENTRY_TYPE = "agent-team-loop:watch";

// ── Window claim identity (_index.parallel claimId) ─────────────────────────

/** This window's claim identity: host:pid. Written into _index.parallel so
 * another window can tell whether a key's claim is still held by a live
 * process (pid check) before taking it over. */
export function windowClaimId(): string {
	return `${os.hostname()}:${process.pid}`;
}

interface ClaimInfo {
	host: string;
	pid: number;
}

/** Parse a `host:pid` claim; anything else (e.g. legacy timestamp claims) is
 * unparseable and treated as stale. */
function parseClaim(claimId: string): ClaimInfo | undefined {
	const m = claimId.match(/^([^:]+):(\d+)$/);
	if (!m) return undefined;
	const pid = Number(m[2]);
	if (!Number.isInteger(pid) || pid <= 0) return undefined;
	return { host: m[1] ?? "", pid };
}

function isPidAlive(pid: number): boolean {
	try {
		process.kill(pid, 0);
		return true;
	} catch (err) {
		// EPERM: process exists but is not ours — still alive. ESRCH: gone.
		return (err as NodeJS.ErrnoException).code === "EPERM";
	}
}

export type ClaimState = "free" | "held-live" | "held-stale";

/** Whether a key's claim blocks a takeover. "held-live" = another live window
 * (or a foreign host we cannot verify) holds it and --force is required. */
export function claimState(claimId: string, self: string): ClaimState {
	const trimmed = claimId.trim();
	if (!trimmed || trimmed === self) return "free";
	const c = parseClaim(trimmed);
	if (!c) return "free"; // legacy/unparseable claim — stale
	if (c.host !== os.hostname()) return "held-live"; // cannot verify liveness
	return isPidAlive(c.pid) ? "held-live" : "held-stale";
}

export interface TakeoverResult {
	ok: boolean;
	/** Present when ok=false: the live claim that blocked the takeover. */
	blockedBy?: string;
	claimId: string;
	/** True when the key row was auto-created (key was unknown to _index.parallel). */
	created: boolean;
	/** Phase-chain audit warnings for the claimed key (empty = clean):
	 * two-source divergence + gate-evidence gaps for phases the pm-state
	 * claims to have passed. Non-blocking — claiming a broken key to fix it
	 * is legitimate; the warnings make the breakage visible immediately. */
	audit: string[];
}

/** Claim a key for this window — shared by /pm-key switch, /pm-key new and
 * the spec-write auto-takeover. Routes through IndexStore.claim so the
 * liveness check, demote, and write are one atomic step under the index
 * lock: racing windows cannot both believe they claimed. Also runs the
 * phase-chain audit on success (audit_phase.py's TS-side mirror). */
export async function takeOverKey(
	indexStore: IndexStore,
	key: string,
	force: boolean,
	agenticdocRoot: string,
): Promise<TakeoverResult> {
	const self = windowClaimId();
	const outcome = await indexStore.claim(key, self, (id) => claimState(id, self) === "held-live", { force });
	const audit = outcome.ok ? phaseAuditWarnings(agenticdocRoot, key, outcome.entry.phase) : [];
	return { ok: outcome.ok, blockedBy: outcome.blockedBy, claimId: self, created: outcome.created, audit };
}

const WATCH_WIDGET_KEY = "agent-team-loop-watch";
const WATCH_MAX_TASK_LINES = 6;
const WATCH_LINE_MAX = 110;

const STATUS_GLYPH: Record<WorkerStatus, string> = {
	pending: ".",
	running: ">",
	done: "+",
	failed: "x",
	"needs-clarification": "?",
};

function trunc(s: string, max: number): string {
	return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}

/** Owner key of a queue row: the first taskPath segment below the agenticdoc
 * root ({key}/workers/<task>/task.md → key). Legacy root-level rows resolve to
 * their own task key and simply never match a watched key. */
export function ownerKeyOf(entry: WorkerEntry, agenticdocRoot: string): string {
	const rel = path.relative(agenticdocRoot, path.normalize(entry.taskPath));
	return rel.split(path.sep)[0] ?? "";
}

export function readOutputSummary(taskDir: string): string | undefined {
	const outputPath = path.join(taskDir, "output.md");
	if (!fs.existsSync(outputPath)) return undefined;
	const content = fs.readFileSync(outputPath, "utf8");
	const m = content.match(/## Summary\s*\n+([\s\S]*?)(?=\n## |$)/);
	return m ? m[1].trim() : undefined;
}

/** Cap for terminal readback bodies (AC-014). */
export const OUTPUT_READBACK_MAX = 20_000;

/** Full output.md body for terminal readback (AC-014): worker results are
 * delivered into the watching window's conversation so the PM processes
 * them without manual file reads. Over-cap reports are truncated with a
 * pointer to the file. */
export function readOutputBody(taskDir: string): string | undefined {
	const outputPath = path.join(taskDir, "output.md");
	let content: string;
	try {
		content = fs.readFileSync(outputPath, "utf8").trim();
	} catch {
		return undefined;
	}
	if (!content) return undefined;
	if (content.length <= OUTPUT_READBACK_MAX) return content;
	return `${content.slice(0, OUTPUT_READBACK_MAX)}\n\n…(truncated — full report: ${outputPath})`;
}

/** Last `[launcher] spawn failed …` line from worker.log, if any. Spawn-failure
 * logs are tiny (the CLI never ran — the launcher writes exactly this line and
 * nothing else); a large log means the worker actually ran, so ignore it. */
export function readSpawnFailure(taskDir: string): string | undefined {
	const logPath = path.join(taskDir, "worker.log");
	try {
		const stat = fs.statSync(logPath);
		if (stat.size > 64 * 1024) return undefined;
		const lines = fs.readFileSync(logPath, "utf8").split("\n");
		for (let i = lines.length - 1; i >= 0; i--) {
			const line = lines[i].trim();
			if (line.startsWith("[launcher] spawn failed")) return line;
		}
		return undefined;
	} catch {
		return undefined;
	}
}

/** Live bottom-widget lines for the watched key: phase from _index.parallel,
 * per-task worker statuses, and failure/summary details for terminal tasks. */
export function renderWatchLines(
	indexStore: IndexStore,
	workerStore: WorkerStore,
	agenticdocRoot: string,
	key: string,
): string[] {
	const counts: Record<WorkerStatus, number> = {
		pending: 0,
		running: 0,
		done: 0,
		failed: 0,
		"needs-clarification": 0,
	};
	const owned = workerStore.readAll().filter((e) => ownerKeyOf(e, agenticdocRoot) === key);
	for (const e of owned) counts[e.status]++;

	const idx = indexStore.findByKey(key);
	const phase = idx
		? `phase=${idx.phase}`
		: key === SCRATCH_WORKERS_KEY
			? "manual tasks"
			: "key not in _index.parallel";
	const badge = key === SCRATCH_WORKERS_KEY ? undefined : formatDocsBadge(readPhaseDocs(agenticdocRoot, key));
	const parts: string[] = [];
	if (counts.running > 0) parts.push(`${counts.running} running`);
	if (counts.pending > 0) parts.push(`${counts.pending} pending`);
	if (counts.done > 0) parts.push(`${counts.done} done`);
	if (counts.failed > 0) parts.push(`${counts.failed} failed`);
	if (counts["needs-clarification"] > 0) parts.push(`${counts["needs-clarification"]} needs-clarification`);
	const header = `[mw] ${key} | ${phase}${badge ? ` | docs ${badge}` : ""} | ${
		parts.length > 0 ? parts.join(" / ") : "no workers"
	}`;

	if (owned.length === 0) return [header, "  (no worker tasks)"];

	// Live tasks first (running, then pending), terminal tasks newest-first.
	const rank = (s: WorkerStatus): number => (s === "running" ? 0 : s === "pending" ? 1 : 2);
	const tasks = [...owned].sort(
		(a, b) => rank(a.status) - rank(b.status) || (b.updatedAt ?? "").localeCompare(a.updatedAt ?? ""),
	);
	const lines = [header];
	for (const e of tasks.slice(0, WATCH_MAX_TASK_LINES)) {
		let detail = "";
		if (e.status === "running") {
			// Heartbeat-derived live progress (design D-008): phase counter + age
			// of the last [HEARTBEAT] line, refreshed on every poll tick. Old
			// bundles without heartbeats get a visible (no-hb) placeholder.
			// [START] adds elapsed runtime ("up 6m") and the last [TOOL] line
			// names what the worker is currently doing.
			const prog = readTaskProgress(path.dirname(e.taskPath));
			const hb = prog?.heartbeat;
			if (hb) {
				const ph = hb.phase === "-" ? "ph -" : `ph ${hb.phase}/${hb.phaseTotal}`;
				const up = prog?.elapsedMs !== undefined ? ` up ${formatHeartbeatAge(prog.elapsedMs)}` : "";
				const stale = hb.ageMs > HEARTBEAT_STALE_MS ? " STALE" : "";
				detail = `${ph}${up} hb ${formatHeartbeatAge(hb.ageMs)}${stale}`;
			} else {
				detail = "(no-hb)";
			}
			// Convergence checkpoint badge (AC-005): past the checkpoint time the
			// running line carries the machine risk verdict — the PM's divergence
			// radar at a glance. Non-low risks get a warning glyph.
			const ck = prog?.checkpoint;
			if (ck) {
				detail += ` ck${Math.round(ck.elapsedS / 60)}m${ck.risk !== "low" ? ` ${ck.risk}⚠` : ""}`;
			}
			if (prog?.lastAction) detail += ` · ${prog.lastAction}`;
		} else if (e.status !== "pending") {
			const taskDir = path.dirname(e.taskPath);
			detail = readOutputSummary(taskDir) ?? readSpawnFailure(taskDir) ?? "";
			detail = (detail.split("\n")[0] ?? "").trim();
			// Strip the launcher prefix (timestamp) so the reason fits the line budget.
			const reason = detail.match(/^\[launcher\] spawn failed \([^)]*\):\s*(.*)$/);
			if (reason) detail = reason[1] ?? "";
		}
		lines.push(trunc(`  ${STATUS_GLYPH[e.status]} ${e.taskKey}${detail ? ` — ${detail}` : ""}`, WATCH_LINE_MAX));
	}
	if (tasks.length > WATCH_MAX_TASK_LINES) lines.push(`  ... +${tasks.length - WATCH_MAX_TASK_LINES} more`);
	return lines;
}

/** Render (or clear) the bottom watch widget on a UI-capable context. */
export function setWatchWidget(ctx: ExtensionContext, lines: string[] | undefined): void {
	if (!ctx.hasUI) return;
	ctx.ui.setWidget(WATCH_WIDGET_KEY, lines, { placement: "belowEditor" });
}

/** Render (or clear) the widget via the session_start-captured context.
 * No-op before session start or in headless runs. */
export function applyWatchWidget(ui: PmUiHolder, lines: string[] | undefined): void {
	if (!ui.ctx) return;
	setWatchWidget(ui.ctx, lines);
}

/** Set this window's watched key, persist it in the session file (survives
 * restart/resume), and refresh the bottom widget immediately. `claimed` marks
 * watches that came with a key takeover. */
function setWindowWatch(
	pi: ExtensionAPI,
	watch: PmWatchState,
	refresh: (ctx: ExtensionContext) => void,
	ctx: ExtensionCommandContext,
	key: string | undefined,
	claimed: boolean,
): void {
	watch.key = key;
	pi.appendEntry(WATCH_ENTRY_TYPE, { key, claimed });
	refresh(ctx);
}

/** Doc-gate notifier scoped to this window's watched key (AC-011): the scan
 * evaluates gates for every undocumented key (blocking stays global), but a
 * gate event is only BROADCAST here when it is this window's own key — other
 * keys' gates belong to their owning windows. A window watching nothing
 * stays silent. */
export function makeScopedDocGateNotifier(
	pi: ExtensionAPI,
	watch: PmWatchState,
): (key: string, gaps: string[]) => boolean {
	return (key, gaps) => {
		if (!watch.key || key !== watch.key) return false;
		displaySummary(
			pi,
			`[mw] skipped dispatch for '${key}' — missing phase docs: ${gaps.join("; ")}. ` +
				"Generate spec/design + evidence/research notes (agentic-task workflows), or move ad-hoc work under _scratch.",
		);
		return true;
	};
}

export function registerPmKeyCommands(
	pi: ExtensionAPI,
	indexStore: IndexStore,
	watch: PmWatchState,
	refreshWatch: (ctx: ExtensionContext) => void,
	agenticdocRoot: string,
): void {
	pi.registerCommand("pm-key", {
		description: "Manage PM keys: new / switch (take over + watch) / list",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const [sub, ...rest] = args.trim().split(/\s+/);
			const flags = rest.filter((t) => t.startsWith("--"));
			const positional = rest.filter((t) => !t.startsWith("--"));
			const keyName = positional[0] ?? "";
			const force = flags.includes("--force");

			if (sub === "list") {
				const entries = indexStore.readAll();
				if (entries.length === 0) {
					ctx.ui.notify("No keys found.", "info");
					return;
				}
				const table = entries.map((e) => `${e.key} | ${e.status} | ${e.phase} | ${e.claimId}`).join("\n");
				ctx.ui.notify(table, "info");
				return;
			}

			if (sub === "new") {
				if (!keyName) {
					ctx.ui.notify("Usage: /pm-key new <key-name>", "warning");
					return;
				}
				if (indexStore.findByKey(keyName)) {
					ctx.ui.notify(
						`Key '${keyName}' already exists — use /pm-key switch ${keyName} to take it over.`,
						"warning",
					);
					return;
				}
				// Route through the atomic claim: auto-create + demote other active
				// rows (single-active discipline) in one locked step.
				const result = await takeOverKey(indexStore, keyName, false, agenticdocRoot);
				// Executing a key in this window also watches it (bottom progress widget).
				setWindowWatch(pi, watch, refreshWatch, ctx, keyName, true);
				ctx.ui.notify(`Created and claimed key: ${keyName} (${result.claimId})`, "info");
				if (result.audit.length > 0) ctx.ui.notify(result.audit.join("\n"), "warning");
				return;
			}

			if (sub === "switch") {
				if (!keyName) {
					ctx.ui.notify("Usage: /pm-key switch <key-name> [--force]", "warning");
					return;
				}
				const target = indexStore.findByKey(keyName);
				if (!target) {
					ctx.ui.notify(`Key not found: ${keyName}`, "error");
					return;
				}
				const result = await takeOverKey(indexStore, keyName, force, agenticdocRoot);
				if (!result.ok) {
					ctx.ui.notify(
						`Key '${keyName}' is claimed by another live window (${result.blockedBy}). Use /pm-key switch ${keyName} --force to take it over.`,
						"warning",
					);
					return;
				}
				// Switching keys in this window also switches what it watches.
				setWindowWatch(pi, watch, refreshWatch, ctx, keyName, true);
				ctx.ui.notify(`Took over key: ${keyName} (claim ${result.claimId})`, "info");
				if (result.audit.length > 0) ctx.ui.notify(result.audit.join("\n"), "warning");
				return;
			}

			ctx.ui.notify("Usage: /pm-key new|switch|list [key-name] [--force]", "warning");
		},
	});
}

/** /mw-watch — toggle this window's bottom progress widget for one key.
 * Display-only observation: no claim is taken. Use /pm-key switch to take
 * over a key while developing it.
 *
 * Usage: /mw-watch <key>   watch a key (widget appears below the editor)
 *        /mw-watch off     stop watching (widget cleared)
 *        /mw-watch         show current watch state
 */
export function registerWatchCommand(
	pi: ExtensionAPI,
	watch: PmWatchState,
	refreshWatch: (ctx: ExtensionContext) => void,
	indexStore: IndexStore,
): void {
	const USAGE = "Usage: /mw-watch <key> | off   (display only — /pm-key switch takes over a key)";
	pi.registerCommand("mw-watch", {
		description: "Show one key's live worker progress in a bottom widget (/mw-watch <key> | off)",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const arg = args.trim();
			if (!arg) {
				ctx.ui.notify(watch.key ? `Watching: ${watch.key}. ${USAGE}` : `Not watching anything. ${USAGE}`, "info");
				return;
			}
			if (arg === "off" || arg === "none") {
				watch.key = undefined;
				pi.appendEntry(WATCH_ENTRY_TYPE, { key: undefined, claimed: false });
				refreshWatch(ctx);
				ctx.ui.notify("Watch disabled — bottom widget cleared.", "info");
				return;
			}
			if (arg !== SCRATCH_WORKERS_KEY && !indexStore.findByKey(arg)) {
				ctx.ui.notify(
					`Key '${arg}' not found in _index.parallel (or use ${SCRATCH_WORKERS_KEY}). ${USAGE}`,
					"warning",
				);
				return;
			}
			setWindowWatch(pi, watch, refreshWatch, ctx, arg, false);
			ctx.ui.notify(`Watching '${arg}' — worker progress shown below the editor.`, "info");
		},
	});
}

export function registerMwTools(pi: ExtensionAPI, projectDir: string): void {
	pi.registerTool({
		name: "mw_status",
		label: "mw_status",
		description:
			"Check whether the multi-worker background service (mw serve) is running. Returns PID if running, or 'not running' if stopped.",
		parameters: Type.Object({}),
		execute: async (_toolCallId, _params, _signal, _onUpdate, _context) => {
			const s = getMwStatus(projectDir);
			return {
				content: [
					{
						type: "text",
						text: s.running
							? `mw is running (PID ${s.pid}). Workers are being dispatched and monitored.`
							: "mw is not running. Workers will not be dispatched. Use /mw start or ask the user to start it.",
					},
				],
				details: undefined,
			};
		},
	});
}

/**
 * Register agent-callable tools for worker dispatch and task listing.
 * These complement the slash commands in registerWorkerCommands.
 */
export function registerWorkerTools(
	pi: ExtensionAPI,
	workerStore: WorkerStore,
	indexStore: IndexStore,
	agenticdocRoot: string,
	watch: PmWatchState,
): void {
	// dispatch_worker: create a task.md and immediately dispatch it to the worker queue.
	pi.registerTool({
		name: "dispatch_worker",
		label: "dispatch_worker",
		description:
			"Dispatch a task to a background worker agent. Creates .agenticdoc/<task_key>/task.md and queues it for execution by the mw worker service. Returns the task key on success.",
		parameters: Type.Object({
			task_key: Type.String({
				description:
					"Unique kebab-case key for this task (e.g. 'fix-login-bug', 'add-auth-endpoint'). Must be unique across tasks in this project.",
			}),
			description: Type.String({
				description: "Full task description and instructions for the worker agent.",
			}),
			cli: Type.Optional(
				Type.String({
					description:
						"Worker CLI: 'pi' (default for all task types incl. review/research), 'claude' (explicit override — requires claude credentials, fails per-task when missing), 'codex' (codex tasks).",
				}),
			),
			model: Type.Optional(
				Type.String({
					description: "Optional model override for this worker (e.g. 'claude-sonnet-4-5').",
				}),
			),
			key: Type.Optional(
				Type.String({
					description:
						"AgenticTask key owning this worker task. Default: the active key (latest active row in _index.parallel, or the _index.md pointer); falls back to _scratch when no key is active.",
				}),
			),
		}),
		execute: async (_toolCallId, params, _signal, _onUpdate, _context) => {
			const {
				task_key,
				description,
				cli = "pi",
				model,
				key,
			} = params as {
				task_key: string;
				description: string;
				cli?: string;
				model?: string;
				key?: string;
			};
			const ownerKey = resolveOwnerKeyWithSync(pi, indexStore, watch, key, agenticdocRoot);

			const validCli = ["pi", "claude", "codex"];
			if (!validCli.includes(cli)) {
				return {
					content: [{ type: "text", text: `Invalid cli '${cli}'. Must be one of: ${validCli.join(", ")}.` }],
					details: undefined,
				};
			}

			// Docs gate: real keys need spec + design + research evidence before any
			// worker runs (advance_phase.py gate semantics, enforced mechanically).
			const docGaps = dispatchDocGaps(agenticdocRoot, ownerKey);
			if (docGaps.length > 0) {
				return {
					content: [
						{
							type: "text",
							text:
								`Worker dispatch blocked: key '${ownerKey}' is missing phase documentation.\n` +
								`${docGaps.map((g) => `- ${g}`).join("\n")}\n${DOC_GATE_HINT}`,
						},
					],
					details: undefined,
				};
			}

			// Worker tasks live under {ownerKey}/workers/<task_key>/ (never at the
			// agenticdoc root - that namespace belongs to AgenticTask keys).
			const taskDir = workerTaskDir(agenticdocRoot, ownerKey, task_key);
			if (fs.existsSync(taskDir)) {
				return {
					content: [
						{
							type: "text",
							text: `Task '${task_key}' already exists at ${taskDir}. Choose a different task_key or check existing tasks with list_tasks.`,
						},
					],
					details: undefined,
				};
			}

			const typeField = cli === "codex" ? "codex" : cli === "claude" ? "review" : "coding";
			const provider = cli === "pi" ? "timi" : "";

			fs.mkdirSync(taskDir, { recursive: true });
			const taskMdPath = path.join(taskDir, "task.md");
			const frontmatter = model ? `type: ${typeField}\nmodel: ${model}\n` : `type: ${typeField}\n`;
			fs.writeFileSync(taskMdPath, `${frontmatter}\n${description}\n`, "utf8");

			await dispatchTask(
				{ taskKey: task_key, status: "pending", cli, provider, model: model ?? "", taskPath: taskMdPath },
				workerStore,
			);

			return {
				content: [
					{
						type: "text",
						text: `Dispatched worker '${task_key}' (type: ${cli}${model ? `, model: ${model}` : ""}) under key '${ownerKey}'. Task file: ${taskMdPath}. Check mw_status to confirm the service is running.`,
					},
				],
				details: undefined,
			};
		},
	});

	// list_tasks: return all tracked tasks and their current status.
	pi.registerTool({
		name: "list_tasks",
		label: "list_tasks",
		description:
			"List all worker tasks in this project with their current status (pending / running / done / failed / needs-clarification).",
		parameters: Type.Object({}),
		execute: async (_toolCallId, _params, _signal, _onUpdate, _context) => {
			const entries = workerStore.readAll();
			if (entries.length === 0) {
				return { content: [{ type: "text", text: "No tasks found." }], details: undefined };
			}
			const lines = entries.map(
				(e) => `${e.taskKey} | ${e.status} | ${e.cli}${e.model ? ` | model: ${e.model}` : ""}`,
			);
			return { content: [{ type: "text", text: lines.join("\n") }], details: undefined };
		},
	});
}

/** Register the agent-callable switch_key tool: same takeover as
 * /pm-key switch, callable mid-conversation. Tool description + prompt
 * guidelines teach the agent when to call it (explicit user request, or
 * starting real task work on a key — ask the user first in that case). */
export function registerSwitchKeyTool(
	pi: ExtensionAPI,
	indexStore: IndexStore,
	watch: PmWatchState,
	refreshWatch: (ctx: ExtensionContext) => void,
	agenticdocRoot: string,
): void {
	pi.registerTool({
		name: "switch_key",
		label: "switch_key",
		description:
			"Take over (claim + watch) an AgenticTask key in this window: marks it active in _index.parallel with this window's claim (host:pid) and shows its live worker progress in the bottom widget. " +
			"Call it when the user asks to take over or switch to a key, or when you are about to execute a key's tasks in this window. " +
			"Writing .agenticdoc/{key}/spec.md, design.md, or plan.md switches automatically — no call needed. " +
			"If another live window holds the key's claim, the call fails unless force is true; tell the user and let them decide.",
		promptGuidelines: [
			"Before doing real work on an AgenticTask key (executing its tasks), make sure this window has taken it over via switch_key; if the user has not asked for that key, ask them first whether to switch.",
		],
		parameters: Type.Object({
			key: Type.String({ description: "The AgenticTask key to take over." }),
			force: Type.Optional(
				Type.Boolean({
					description:
						"Steal the claim even if another live window holds it. Only with the user's explicit confirmation.",
				}),
			),
		}),
		execute: async (_toolCallId, params, _signal, _onUpdate, ctx) => {
			const { key, force = false } = params as { key: string; force?: boolean };
			const trimmed = key.trim();
			if (!trimmed) {
				return { content: [{ type: "text", text: "key is required." }], details: undefined };
			}
			const result = await takeOverKey(indexStore, trimmed, force, agenticdocRoot);
			if (!result.ok) {
				return {
					content: [
						{
							type: "text",
							text: `Key '${trimmed}' is claimed by another live window (${result.blockedBy}). The takeover was NOT performed. Tell the user; they can decide on a forced takeover (force=true).`,
						},
					],
					details: undefined,
				};
			}
			watch.key = trimmed;
			pi.appendEntry(WATCH_ENTRY_TYPE, { key: trimmed, claimed: true });
			refreshWatch(ctx);
			const auditNote =
				result.audit.length > 0
					? `\n\nPHASE-CHAIN AUDIT WARNINGS for this key (fix before continuing; phase changes go through advance_phase.py only):\n${result.audit.join("\n")}`
					: "";
			return {
				content: [
					{
						type: "text",
						text:
							`Took over key '${trimmed}' (claim ${result.claimId})` +
							`${result.created ? " — new key registered in _index.parallel" : ""}. ` +
							"This window now watches it; the bottom widget shows its live progress. Previously active keys were marked idle." +
							auditNote,
					},
				],
				details: undefined,
			};
		},
	});
}

/**
 * Spawn a worker directly from the pi window.
 * Usage: /worker <claude|codex|pi> [--model <id>] <task description>
 */
export function registerWorkerCommands(
	pi: ExtensionAPI,
	workerStore: WorkerStore,
	indexStore: IndexStore,
	agenticdocRoot: string,
	watch: PmWatchState,
): void {
	const USAGE = "Usage: /worker <claude|codex|pi> [--model <id>] [--key <name>] <task description>";
	pi.registerCommand("worker", {
		description: "Spawn a worker: /worker <claude|codex|pi> [--model <id>] <task description>",
		handler: async (args: string, ctx: ExtensionCommandContext) => {
			const parts = args.trim().split(/\s+/);
			const cli = (parts[0] ?? "").toLowerCase();

			// Optional `--model <id>` and `--key <name>` flags right after the cli;
			// everything else is the description.
			let idx = 1;
			let model = "";
			let keyArg = "";
			while (parts[idx] === "--model" || parts[idx] === "--key") {
				if (parts[idx] === "--model") {
					model = parts[idx + 1] ?? "";
					idx += 2;
					if (!model) {
						ctx.ui.notify(USAGE, "warning");
						return;
					}
				} else {
					keyArg = parts[idx + 1] ?? "";
					idx += 2;
					if (!keyArg) {
						ctx.ui.notify(USAGE, "warning");
						return;
					}
				}
			}
			const description = parts.slice(idx).join(" ");

			const validCli = ["claude", "codex", "pi"];
			if (!validCli.includes(cli)) {
				ctx.ui.notify(USAGE, "warning");
				return;
			}
			if (!description) {
				ctx.ui.notify("Task description is required.", "warning");
				return;
			}

			// Map CLI to task.md type field (must match pickWorkerRoute mapping)
			const typeField = cli === "codex" ? "codex" : cli === "claude" ? "review" : "coding";
			const provider = cli === "pi" ? "timi" : "";

			// Create task directory and task.md under {ownerKey}/workers/ (persist
			// model: so it's visible + re-parseable)
			const taskKey = `manual-${Date.now()}`;
			const ownerKey = resolveOwnerKeyWithSync(pi, indexStore, watch, keyArg, agenticdocRoot);
			const docGaps = dispatchDocGaps(agenticdocRoot, ownerKey);
			if (docGaps.length > 0) {
				ctx.ui.notify(
					`Worker dispatch blocked ('${ownerKey}'): ${docGaps.join("; ")}. Generate the phase docs first or dispatch under _scratch.`,
					"warning",
				);
				return;
			}
			const taskDir = workerTaskDir(agenticdocRoot, ownerKey, taskKey);
			fs.mkdirSync(taskDir, { recursive: true });
			const taskMdPath = path.join(taskDir, "task.md");
			const frontmatter = model ? `type: ${typeField}\nmodel: ${model}\n` : `type: ${typeField}\n`;
			fs.writeFileSync(taskMdPath, `${frontmatter}\n${description}\n`, "utf8");

			// Dispatch directly to _workers.parallel
			await dispatchTask({ taskKey, status: "pending", cli, provider, model, taskPath: taskMdPath }, workerStore);

			ctx.ui.notify(
				`Dispatched ${cli} worker (${taskKey}) under key '${ownerKey}'${model ? ` [model: ${model}]` : ""}.`,
				"info",
			);
		},
	});
}

/** Format a doctor JSON report as a readable Chinese summary (same data as
 * the CLI text output — the TS side never re-implements checks, AC-007). */
export function formatDoctorReport(report: DoctorJson, fix: boolean): string {
	const lines: string[] = [];
	const svc = report.service;
	lines.push(svc?.running ? `服务: 运行中 (PID ${svc.pid ?? "?"})` : "服务: 未运行");

	const proxyParts = (report.proxy ?? []).map(
		(p) => `${p.route ?? "?"}/${p.port ?? "?"} ${p.listening ? "监听中" : "未监听"}`,
	);
	if (proxyParts.length > 0) lines.push(`代理端口: ${proxyParts.join("; ")}`);

	const orphan = report.orphan_proxy;
	if (orphan?.detected) {
		const ports = (orphan.ports ?? []).map((p) => `${p.port} (PID ${(p.owner_pids ?? []).join(",") || "?"})`);
		lines.push(`孤儿代理: ${ports.join("; ")}（mw 未运行但端口被占，可启动 mw 接管或处置占用进程）`);
	}

	const log = report.launcher_log;
	if (log?.exists) {
		lines.push(`launcher 日志: ${log.error_count ?? 0} 个错误行${log.fatal ? "（含 FATAL）" : ""}`);
	} else {
		lines.push("launcher 日志: 无日志文件");
	}

	const queue = report.queue;
	lines.push(
		`队列: ${queue?.non_terminal?.length ?? 0} 个进行中任务，${
			queue?.stale_count ?? 0
		} 个 stale，${queue?.archived_total ?? 0} 条已归档`,
	);

	// Worker liveness (mw doctor worker_liveness section — informational).
	// Stale workers are named so the PM sees which task is suspected hung.
	const liveness = report.worker_liveness ?? [];
	if (liveness.length > 0) {
		const alive = liveness.filter((v) => v.verdict === "alive").length;
		const stale = liveness.filter((v) => v.verdict === "stale").map((v) => v.task_key ?? "?");
		const noHb = liveness.filter((v) => v.verdict === "no-heartbeat").length;
		const parts = [`存活 ${alive}`];
		if (stale.length > 0) parts.push(`疑似挂起: ${stale.join(", ")}`);
		if (noHb > 0) parts.push(`无心跳 ${noHb}`);
		lines.push(`worker 活性: ${parts.join("; ")}`);
	}

	const credParts = (report.credentials?.routes ?? []).map(
		(r) => `${r.route ?? "?"} ${r.available ? "可用" : "缺凭证"}`,
	);
	if (credParts.length > 0) lines.push(`路由凭证: ${credParts.join("; ")}（以 mw 进程 env 为准）`);

	const bundle = report.bundle;
	if (bundle?.available) {
		lines.push(bundle.stale ? "扩展 bundle: 源码较新，建议 /mw build 重建" : "扩展 bundle: 最新");
	}

	if (fix) {
		const applied = report.fix?.applied;
		lines.push(Array.isArray(applied) && applied.length > 0 ? `已自动修复: ${applied.join("; ")}` : "无可自动修复项");
	}

	const summary = report.summary;
	if (summary?.healthy) {
		lines.push("整体: 健康");
	} else {
		const issues = Array.isArray(summary?.issues) ? (summary?.issues as string[]) : [];
		lines.push(issues.length > 0 ? `整体: ${issues.length} 个问题 — ${issues.join("; ")}` : "整体: 未知");
	}
	const suggestions = Array.isArray(summary?.suggestions) ? (summary?.suggestions as string[]) : [];
	for (const s of suggestions) lines.push(`建议: ${s}`);
	return lines.join("\n");
}

export function registerMwCommands(pi: ExtensionAPI, projectDir: string): void {
	pi.registerCommand("mw", {
		description: "Control mw: build / init / start / stop / status",
		handler: async (_args: string, ctx: ExtensionCommandContext) => {
			const sub = _args.trim().split(/\s+/)[0] ?? "status";

			if (sub === "build") {
				ctx.ui.notify("Rebuilding extension bundle (bash-free)…", "info");
				const r = buildMw();
				if (r.ok) {
					ctx.ui.notify(`mw build OK — reinstalled globally. Restart pi windows to load it.\n${r.output}`, "info");
				} else {
					ctx.ui.notify(`mw build failed: ${r.error}`, "error");
				}
				return;
			}

			if (sub === "init") {
				const result = initMw(projectDir);
				if (result.ok) {
					ctx.ui.notify("mw init complete — .agenticdoc/ .mw/ .pi/extensions/ created.", "info");
				} else {
					ctx.ui.notify(result.error, "error");
				}
				return;
			}

			if (sub === "doctor") {
				const fix = _args.trim().split(/\s+/)[1]?.toLowerCase() === "fix";
				const r = doctorMw(projectDir, fix);
				if (r.ok) {
					ctx.ui.notify(formatDoctorReport(r.report, fix), "info");
				} else {
					ctx.ui.notify(`mw doctor 执行失败: ${r.error}`, "error");
				}
				return;
			}

			if (sub === "status") {
				const s = getMwStatus(projectDir);
				ctx.ui.notify(s.running ? `mw running (PID ${s.pid})` : "mw not running", "info");
				return;
			}

			if (sub === "start") {
				const s = getMwStatus(projectDir);
				if (s.running) {
					ctx.ui.notify(`mw already running (PID ${s.pid})`, "info");
					return;
				}
				const ok = startMw(projectDir);
				ctx.ui.notify(
					ok ? "mw starting in background…" : "Could not find mw.py — set MW_PY env var.",
					ok ? "info" : "error",
				);
				return;
			}

			if (sub === "stop") {
				const s = getMwStatus(projectDir);
				if (!s.running) {
					ctx.ui.notify("mw is not running", "info");
					return;
				}
				stopMw(projectDir);
				ctx.ui.notify("mw stop signal sent", "info");
				return;
			}

			ctx.ui.notify("Usage: /mw build|init|start|stop|status|doctor [fix]", "warning");
		},
	});
}
