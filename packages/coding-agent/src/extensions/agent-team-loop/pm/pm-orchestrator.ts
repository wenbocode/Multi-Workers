import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI, ExtensionContext } from "../../../core/extensions/types.ts";
import { autoStartMonitor, registerAutopilotCommands } from "../autopilot/console.ts";
import { stopMonitor } from "../autopilot/monitor.ts";
import { readConfig } from "../autopilot/status-model.ts";
import { registerRagTools } from "../rag/tools.ts";
import { AckStore } from "../shared/ack-store.ts";
import { registerMainWindowModel } from "../shared/dispatch-models.ts";
import { formatHeartbeatAge, readTaskProgress } from "../shared/heartbeat.ts";
import { IndexStore } from "../shared/index-store.ts";
import { getMwStatus, initMw, serveStaleness, startMw, waitForMwStart } from "../shared/mw-runner.ts";
import { agenticdocRoot as resolveAgenticdocRoot, SCRATCH_WORKERS_KEY } from "../shared/paths.ts";
import { dispatchDocGaps, readPhaseDocs } from "../shared/phase-docs.ts";
import { syncPmStateClaimId } from "../shared/pm-state-claim.ts";
import { registerPmStateGuard } from "../shared/pm-state-guard.ts";
import { evaluateRunIdentity, type RunIdentityRefusal } from "../shared/run-store.ts";
import { readTaskType } from "../shared/task-frontmatter.ts";
import { type WorkerEntry, type WorkerStatus, WorkerStore } from "../shared/worker-store.ts";
import { isGoalEstablished, readGoal } from "./goal-reader.ts";
import { StateManager } from "./state-manager.ts";
import { dispatchTask } from "./task-dispatcher.ts";
import {
	applyWatchWidget,
	claimState,
	claimSyncWarningText,
	deliverPmAlert,
	deliverWorkerResult,
	displaySummary,
	makeScopedDocGateNotifier,
	ownerKeyOf,
	type PmUiHolder,
	type PmWatchState,
	readOutputBody,
	readSpawnFailure,
	registerAdvancePhaseTool,
	registerMwCommands,
	registerMwTools,
	registerPmKeyCommands,
	registerPmSaveCommand,
	registerSwitchKeyTool,
	registerWatchCommand,
	registerWorkerCommands,
	registerWorkerTools,
	renderWatchLines,
	setWatchWidget,
	takeOverKey,
	WATCH_ENTRY_TYPE,
	windowClaimId,
} from "./ui-bridge.ts";

const POLL_INTERVAL_MS = 4000; // < 5s per AC-001

function isTerminal(status: WorkerStatus): boolean {
	return status === "done" || status === "failed" || status === "needs-clarification" || status === "lost";
}

export type PhaseDocName = "spec.md" | "design.md" | "plan.md";

interface DocWriteTarget {
	key: string;
	doc: PhaseDocName;
}

/** The phase-doc write/edit target, when the tool path resolves to
 * {agenticdocRoot}/{key}/spec.md | design.md | plan.md — the PM phase docs that
 * mean "this window is now executing this key". Any other path (or file) is
 * not a claim signal. */
function docWriteTarget(
	toolName: string,
	args: unknown,
	projectDir: string,
	agenticdocRoot: string,
): DocWriteTarget | undefined {
	if (toolName !== "write" && toolName !== "edit") return undefined;
	const filePath = (args as { path?: unknown } | undefined)?.path;
	if (typeof filePath !== "string" || filePath === "") return undefined;
	const rel = path.relative(path.resolve(agenticdocRoot), path.resolve(projectDir, filePath));
	if (rel.startsWith("..") || path.isAbsolute(rel)) return undefined; // outside .agenticdoc
	const parts = rel.split(path.sep);
	const doc = parts.length === 2 ? parts[1] : undefined;
	if (doc !== "spec.md" && doc !== "design.md" && doc !== "plan.md") return undefined;
	const key = parts[0] ?? "";
	if (!key || key.startsWith("_") || key.startsWith(".")) return undefined;
	return { key, doc };
}

/** The key a phase-doc write/edit belongs to (see docWriteTarget). */
export function keyFromDocWrite(
	toolName: string,
	args: unknown,
	projectDir: string,
	agenticdocRoot: string,
): string | undefined {
	return docWriteTarget(toolName, args, projectDir, agenticdocRoot)?.key;
}

/** Which phase doc was written/edited (see docWriteTarget). */
export function docFromWrite(
	toolName: string,
	args: unknown,
	projectDir: string,
	agenticdocRoot: string,
): PhaseDocName | undefined {
	return docWriteTarget(toolName, args, projectDir, agenticdocRoot)?.doc;
}

export type EvidencePhase = "spec" | "design";

/** The evidence-note write target, when the tool path resolves to
 * {agenticdocRoot}/{key}/evidence/research/spec-*.md | design-*.md. Not a
 * claim signal (only phase docs are) — but the moment evidence lands is the
 * moment an already-written phase doc's claims can be re-reviewed against
 * it. */
export function evidencePhaseFromWrite(
	toolName: string,
	args: unknown,
	projectDir: string,
	agenticdocRoot: string,
): { key: string; phase: EvidencePhase } | undefined {
	if (toolName !== "write" && toolName !== "edit") return undefined;
	const filePath = (args as { path?: unknown } | undefined)?.path;
	if (typeof filePath !== "string" || filePath === "") return undefined;
	const rel = path.relative(path.resolve(agenticdocRoot), path.resolve(projectDir, filePath));
	if (rel.startsWith("..") || path.isAbsolute(rel)) return undefined; // outside .agenticdoc
	const parts = rel.split(path.sep);
	if (parts.length !== 4 || parts[1] !== "evidence" || parts[2] !== "research") return undefined;
	const note = parts[3] ?? "";
	if (!note.endsWith(".md")) return undefined;
	const phase: EvidencePhase | undefined = note.startsWith("spec-")
		? "spec"
		: note.startsWith("design-")
			? "design"
			: undefined;
	if (!phase) return undefined;
	const key = parts[0] ?? "";
	if (!key || key.startsWith("_") || key.startsWith(".")) return undefined;
	return { key, phase };
}

/** UI notice when a phase doc and its research evidence coexist — the
 * "re-review when evidence is generated" protocol, as a *notice*, not an
 * injected instruction (mw-evidence-nudge-notify): the old sendUserMessage
 * form made the model treat the automatic nudge as the user ordering an
 * immediate review pass, so the window agent started rewriting the doc with
 * no consent and no chance to veto, hijacking the turn. The framework's role
 * is to flag the moment; the user decides when (and whether) to run the
 * review. Fires once per (key, phase) per session, only when both the phase
 * doc (>= 500 bytes) and >= 1 evidence note exist: the review needs both
 * sides of the comparison. */
export function evidenceReviewNotice(
	ctx: ExtensionContext,
	key: string,
	phase: EvidencePhase,
	agenticdocRoot: string,
	notified: Set<string>,
): void {
	const dedup = `${key}:${phase}`;
	if (notified.has(dedup)) return;
	const docs = readPhaseDocs(agenticdocRoot, key);
	const docOk = phase === "spec" ? docs.spec : docs.design;
	const evidence = phase === "spec" ? docs.specEvidence : docs.designEvidence;
	if (!docOk || evidence < 1) return;
	notified.add(dedup);
	const doc = phase === "spec" ? "spec.md" : "design.md";
	ctx.ui.notify(
		`[mw] ${key}: ${phase} 阶段证据已就位（${evidence} 份 research note）——建议对照 evidence/research/ 复查 ${doc}（断言-证据对照 / 数字口径 / 内部一致性 / 可证伪性）。何时执行复查由你决定。`,
		"info",
	);
}

/** Nudge the user toward the /goal brainstorm when the project goal is not
 * yet established. Headless sessions (print/-p) skip the nudge entirely:
 * sendUserMessage starts a generation immediately, and the queued -p prompt
 * would collide with it ("Agent is already processing") before ever reaching
 * the model — `pi -p` in any project without an established goal.md would
 * hard-fail at startup. */
export function nudgeGoalUnestablished(pi: ExtensionAPI, agenticdocRoot: string, hasUI: boolean): void {
	const goal = readGoal(agenticdocRoot);
	if (hasUI && !isGoalEstablished(goal)) {
		pi.sendUserMessage(
			"[agent-team-loop] 项目总目标（.agenticdoc/goal.md）尚未确立。\n" +
				"建议先运行 /goal，与我对话共创项目总目标——它是后续每个 spec 对齐的锚点。\n" +
				"（也可直接编辑 .agenticdoc/goal.md 填好三段内容并把 status 改为 active。）",
		);
	}
}

/** Auto-takeover on phase-doc write: writing/editing {key}/spec.md, design.md,
 * or plan.md is this window saying "I am now executing key X" — claim it and
 * watch it, exactly like /pm-key switch. A live foreign claim blocks the claim
 * (watch-only) but never the watch itself. Writing design.md / plan.md also
 * runs the next-phase evidence gate (mirrors advance_phase.py): the previous
 * phase's research notes must exist, or the user is warned immediately. */
export async function autoTakeOverFromDoc(
	pi: ExtensionAPI,
	indexStore: IndexStore,
	watch: PmWatchState,
	refreshWatch: (ctx: ExtensionContext) => void,
	key: string,
	doc: PhaseDocName,
	agenticdocRoot: string,
	ctx: ExtensionContext,
): Promise<void> {
	// Next-phase evidence gate: writing design.md means the spec phase should be
	// complete (its research notes exist); writing plan.md means design should be.
	// Fires regardless of takeover idempotency — the missing evidence is the
	// message, and it stays true until the notes are written.
	const docs = readPhaseDocs(agenticdocRoot, key);
	if (doc === "spec.md" && docs.specEvidence < 1) {
		ctx.ui.notify(
			`[mw] ${key}: no evidence/research/spec-*.md found — write the research notes (or a zero-research declaration) alongside the spec; the advance-to-design gate checks them.`,
			"warning",
		);
	}
	if (doc === "design.md" && docs.specEvidence < 1) {
		ctx.ui.notify(
			`[mw] ${key}: no evidence/research/spec-*.md found — the advance-to-design gate requires >= 1 research note (a zero-research declaration counts). Write it before advancing.`,
			"warning",
		);
	}
	if (doc === "plan.md") {
		if (!docs.design) {
			ctx.ui.notify(
				`[mw] ${key}: design.md missing or under 500 bytes — required before plan (run the system-design workflow).`,
				"warning",
			);
		} else if (docs.designEvidence < 1) {
			ctx.ui.notify(
				`[mw] ${key}: no evidence/research/design-*.md found — the advance-to-plan gate requires >= 1 research note (a zero-research declaration counts). Write it before advancing.`,
				"warning",
			);
		}
	}

	const row = indexStore.findByKey(key);
	const wasWatching = watch.key === key;
	const wasClaimed = row?.claimId === windowClaimId();
	if (wasWatching && wasClaimed) return; // already ours — nothing to do

	const result = await takeOverKey(indexStore, key, false, agenticdocRoot);
	watch.key = key;
	pi.appendEntry(WATCH_ENTRY_TYPE, { key, claimed: result.ok });
	refreshWatch(ctx);
	if (result.ok) {
		ctx.ui.notify(
			`[mw] claimed key '${key}' (doc write detected) — watching it${result.created ? " (new key registered)" : ""}.`,
			"info",
		);
		if (result.audit.length > 0) ctx.ui.notify(result.audit.join("\n"), "warning");
	} else {
		ctx.ui.notify(
			`[mw] key '${key}' is claimed by another live window (${result.blockedBy}) — watching only.`,
			"warning",
		);
	}
}

/** Restore this window's watched key from the session file (survives restart
 * and resume) and re-render the bottom widget. A watch that came with a key
 * takeover re-claims the key with this process's identity — quietly, unless
 * another live window took it over in the meantime. */
export async function restoreWatch(
	pi: ExtensionAPI,
	watch: PmWatchState,
	indexStore: IndexStore,
	workerStore: WorkerStore,
	ackStore: AckStore,
	agenticdocRoot: string,
	ctx: ExtensionContext,
): Promise<void> {
	let data: { key?: string; claimed?: boolean } | undefined;
	try {
		const entries = ctx.sessionManager.getEntries();
		for (let i = entries.length - 1; i >= 0; i--) {
			const e = entries[i];
			if (e.type === "custom" && e.customType === WATCH_ENTRY_TYPE) {
				data = e.data as { key?: string; claimed?: boolean } | undefined;
				break;
			}
		}
	} catch {
		return; // session entries unavailable — nothing to restore
	}
	if (!data?.key) return;
	const key = data.key;
	watch.key = key;

	if (data.claimed) {
		const row = indexStore.findByKey(key);
		if (row) {
			const self = windowClaimId();
			if (claimState(row.claimId, self) === "held-live") {
				// Another window took over while this one was closed — keep the
				// watch (display-only) and say so; do not touch the shared row.
				ctx.ui.notify(
					`[mw] key '${key}' is claimed by another window (${row.claimId}) — watching only.`,
					"warning",
				);
			} else {
				// Our previous process is gone; re-bind ownership through the
				// atomic claim — a window that raced us to this key wins and we
				// degrade to watch-only (review M2). Quiet re-claim: no demote of
				// other active rows, no status flip; only claimId/updated move.
				const outcome = await indexStore.claim(key, self, (id) => claimState(id, self) === "held-live", {
					demoteOthers: false,
					activate: false,
				});
				if (!outcome.ok) {
					ctx.ui.notify(
						`[mw] key '${key}' is claimed by another window (${outcome.blockedBy}) — watching only.`,
						"warning",
					);
				} else {
					// This path flips the index row's Claim column too, so the
					// pm-state.md mirror must be synced as well (D-108). A failed
					// mirror never reverts the claim — the index row is
					// authoritative — but the divergence must be visible.
					const sync = syncPmStateClaimId(agenticdocRoot, key, self);
					const syncWarning = claimSyncWarningText(key, sync);
					if (syncWarning !== "") ctx.ui.notify(syncWarning, "warning");
				}
			}
		}
	}

	setWatchWidget(
		ctx,
		renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, key, watch.dispatchedTaskKeys),
	);
	// Re-stamp the entry so it lands in the (possibly new) session file.
	pi.appendEntry(WATCH_ENTRY_TYPE, { key, claimed: data.claimed ?? false });

	// Saved working context (pm-save): point the user at it — a notice, never
	// an injected instruction (same principle as evidenceReviewNotice: the
	// framework flags, the user decides whether the agent reads it).
	const pmStatePath = path.join(agenticdocRoot, key, "pm-state.md");
	if (fs.existsSync(pmStatePath)) {
		const updated = fs.statSync(pmStatePath).mtime.toISOString();
		ctx.ui.notify(
			`[mw] key '${key}' 有已保存的 pm-state.md（更新于 ${updated}）。如需接续上次的工作上下文，让 agent 读取 ${key}/pm-state.md 的 Notes 区。`,
			"info",
		);
	}
}

function pickWorkerRoute(taskContent: string): { cli: string; provider: string } {
	// Global default is pi/timi: review/research are routing HINTS for the
	// agent, not claude redirects (design D-005) — a claude worker requires an
	// explicit `cli` param on dispatch_worker / /worker, where missing
	// credentials fail per-task instead of silently degrading the route.
	// The reading comes from the single-source header parser (AC-005/F-6): the
	// old `/^type:\s*codex/im` full-text regex let one body line flip the
	// dispatch CLI, outside the shared `type:` matrix.
	if (readTaskType(taskContent).type === "codex") return { cli: "codex", provider: "" };
	return { cli: "pi", provider: "timi" };
}

// Optional `model:` line in task.md → passed through to the launcher as --model/-m.
function readModel(taskContent: string): string {
	const m = taskContent.match(/^model:\s*(.+)$/im);
	return m ? m[1].trim() : "";
}

// Conductor-origin marker line (D-104): `origin: conductor`. Conductor task.md
// files are rendered by autopilot/dispatch.py render_task_md; the value is the
// literal token "conductor" (line-exact, CRLF-tolerant).
const ORIGIN_LINE_RE = /^origin:[ \t]*(\S+)[ \t\r]*$/m;

/** Dispatch origin of a task.md, when it carries an `origin:` line. */
function readTaskOrigin(taskContent: string): string | undefined {
	return ORIGIN_LINE_RE.exec(taskContent)?.[1];
}

/** Is this a conductor-owned task (D-104)? Such tasks are queued by the
 * conductor alone — the TS scan must never upsert them, closing both the
 * scan/upsert race and the re-insert-as-pending path that a launcher restart
 * (or an archived row) would otherwise open. Manual/legacy tasks carry no
 * marker and behave exactly as before (AC-012 zero regression). Unreadable
 * task.md returns false so the dispatch loop hits the same read error it
 * always did. */
function isConductorTask(taskMdPath: string): boolean {
	try {
		return readTaskOrigin(fs.readFileSync(taskMdPath, "utf8")) === "conductor";
	} catch {
		return false;
	}
}

/** Why a dispatch scan refused to queue anything (AC-020/AC-021). */
export type DispatchAlarmKind =
	| "queue-rows-unparsable"
	| "queue-unreadable"
	| "dispatch-quota"
	// A candidate outside this window's scope (AC-019/T-19): the PM must be able
	// to see what it did NOT touch, aggregated per scan — visibility, not
	// prohibition (the read side stays global, AC-024).
	| "out-of-scope"
	// A candidate whose product already ends the run while the ledger says
	// nothing (AC-022/T-20): refused, never re-run.
	| "run-ledger-conflict"
	// A read-only run that settled without any deliverable (AC-006): the worker
	// recorded `needs-clarification` and emitted this alarm itself, with the
	// ledger root pinned to the true `.agenticdoc` (never `<key>/workers`).
	| "no-product"
	// Residual write-guard risk (AC-007/T-03): a writeless+shell worker was
	// allowed through by contract on a target that is not statically
	// determinable (`allow-unknown`) while its basename still names a deny-list
	// artifact (`pm-state.md`, `_workers*`). The guard itself cannot block;
	// observability is the only remaining defence (design DD-08).
	| "write-scope-risk";

export interface DispatchAlarm {
	kind: DispatchAlarmKind;
	count: number;
	detail?: string;
}

/** Autopilot ledger path (shared with the Python conductor). */
const AUTO_DECISIONS_FILE = "auto-decisions.jsonl";

/** One-line human text for a refused dispatch scan (AC-020/AC-021). */
export function describeDispatchAlarm(alarm: DispatchAlarm): string {
	switch (alarm.kind) {
		case "queue-rows-unparsable":
			return `${alarm.count} unreadable row(s) in _workers.parallel — dispatch refused (fix the row; nothing was queued)${
				alarm.detail ? `: ${alarm.detail}` : ""
			}`;
		case "queue-unreadable":
			return `the queue looks empty while the work has already run (key ${alarm.detail ?? "?"}) — dispatch refused instead of re-running ${
				alarm.count
			} task(s)`;
		case "dispatch-quota":
			return `scan quota reached after ${alarm.count} task(s) — the rest of this scan was refused`;
		case "out-of-scope":
			return `${alarm.count} key(s) outside this window's scope were not scanned (${
				alarm.detail ?? "?"
			}) — read-only visible, never touched`;
		case "run-ledger-conflict":
			return `${alarm.count} task(s) already have a terminal run.json while the queue has no row for them — not re-queued${
				alarm.detail ? `: ${alarm.detail}` : ""
			}`;
		case "no-product":
			return `${alarm.count} read-only run(s) settled without a product — needs-clarification, awaiting human judgement${
				alarm.detail ? `: ${alarm.detail}` : ""
			}`;
		case "write-scope-risk":
			return `${alarm.count} write-scope residual-risk row(s) (blocked=false, risk=deny-basename)${
				alarm.detail ? ` on ${alarm.detail}` : ""
			} — the guard allowed them by contract; review the audited target`;
	}
}

/** Append one machine-readable alarm row to the autopilot ledger
 * (`.agenticdoc/_autopilot/auto-decisions.jsonl`, AC-020/AC-021). The shape
 * mirrors the Python single writer (`conductor._append_auto_decision_row`):
 * one JSON object per line, 1-based `seq`. Decision consumers filter on
 * `phase == "decide"`, so `phase: "dispatch-alarm"` is invisible to them while
 * staying visible to humans, `mw doctor` and later consumers. Best-effort by
 * design: losing the alarm must never break dispatch. */
export function recordDispatchAlarm(agenticdocRoot: string, alarm: DispatchAlarm): void {
	try {
		const ledger = path.join(agenticdocRoot, "_autopilot", AUTO_DECISIONS_FILE);
		let seq = 1;
		try {
			seq =
				fs
					.readFileSync(ledger, "utf8")
					.split("\n")
					.filter((l) => l.trim() !== "").length + 1;
		} catch {
			seq = 1;
		}
		const row = { seq, phase: "dispatch-alarm", kind: alarm.kind, count: alarm.count, detail: alarm.detail ?? "" };
		fs.mkdirSync(path.dirname(ledger), { recursive: true });
		fs.appendFileSync(ledger, `${JSON.stringify(row)}\n`, "utf8");
	} catch (err) {
		console.error(`[mw] dispatch alarm not recorded: ${err instanceof Error ? err.message : String(err)}`);
	}
}

/** Count the write-guard residual-risk audit rows in one worker trace
 * (AC-007/T-03): `[WRITE_SCOPE]` lines carrying BOTH `blocked=false` and
 * `risk=deny-basename`. The filter is deliberately the two-field pair and never
 * `rule=allow-unknown` alone (design-write-guard-landing §5.5): the unknown tier
 * is the contract, the deny-list basename is the residual risk. Best-effort — a
 * missing/unreadable trace is zero, never an error. */
export function countWriteScopeResidualRisks(taskDir: string): number {
	let raw: string;
	try {
		raw = fs.readFileSync(path.join(taskDir, "trace.log"), "utf8");
	} catch {
		return 0;
	}
	let count = 0;
	for (const line of raw.split("\n")) {
		if (!line.startsWith("[WRITE_SCOPE] ")) continue;
		if (!line.includes("blocked=false")) continue;
		if (!line.includes("risk=deny-basename")) continue;
		count += 1;
	}
	return count;
}

/** PM-side exit for the write-guard residual risk (AC-007/DD-08): the worker
 * was allowed through by contract, so the ledger row is the remaining defence.
 * Reuses the single dispatch-alarm channel and its unchanged row shape; returns
 * the number of residual-risk rows found (0 ⇒ nothing written). */
export function recordWriteScopeResidualRisks(agenticdocRoot: string, taskKey: string, taskDir: string): number {
	const count = countWriteScopeResidualRisks(taskDir);
	if (count === 0) return 0;
	recordDispatchAlarm(agenticdocRoot, { kind: "write-scope-risk", count, detail: taskKey });
	return count;
}

/** Single-scan dispatch quota (AC-021). A scan that wants to queue more rows
 * than this is looking at something it does not understand (IN-3 queued 252 in
 * one scan and the launcher spawned 66 workers at once). */
export const DEFAULT_DISPATCH_MAX_PER_SCAN = 3;

/** `dispatch_max_per_scan` from the project's autopilot config (D-026/AC-021).
 *
 * An explicit `DispatchScanOptions.maxPerScan` wins (tests and refreshers);
 * otherwise the project config decides. Read-only and fail-soft: a missing,
 * unreadable or out-of-range config falls back to
 * {@link DEFAULT_DISPATCH_MAX_PER_SCAN} — a broken file must never be able to
 * disable the quota (the IN-3 direction of the failure is *more* dispatching,
 * never less). */
export function readDispatchMaxPerScan(agenticdocRoot: string): number {
	try {
		const result = readConfig(path.dirname(agenticdocRoot));
		if (!result.ok) return DEFAULT_DISPATCH_MAX_PER_SCAN;
		const value = result.config.dispatch_max_per_scan;
		return Number.isInteger(value) && value >= 1 ? value : DEFAULT_DISPATCH_MAX_PER_SCAN;
	} catch {
		return DEFAULT_DISPATCH_MAX_PER_SCAN;
	}
}

/** Product evidence for {@link dispatchNewTasks}'s empty-queue guard (AC-020):
 * files the worker itself writes into its own directory. A task dir holding
 * only `task.md` has never run — that is a fresh project, not a lost queue. */
function hasProductEvidence(taskDir: string): boolean {
	for (const name of ["output.md", "report.md", "run.json", "trace.log"]) {
		if (fs.existsSync(path.join(taskDir, name))) return true;
	}
	return false;
}

export interface DispatchScanOptions {
	/** Keys already warned about in this session — a key is reported at most once. */
	warnedKeys?: Set<string>;
	/** Fires once per undocumented key whose worker tasks were skipped.
	 * MUST return whether the event was actually broadcast: false when it was
	 * intentionally suppressed (e.g. scoped to another window's key) so the
	 * once-per-session dedup does not burn the key's only slot. */
	onDocGate?: (key: string, gaps: string[]) => boolean;
	/** Scan scope (AC-019). `pm` = this window's watched key plus `_scratch`;
	 * `cli` = the whole project. Defaults to `cli` so every pre-existing caller
	 * (the `mw` command surface, tests, refreshers) keeps its global behaviour;
	 * the PM-side automatic scan passes `pm` explicitly. */
	scope?: "pm" | "cli";
	/** The window's watched key; the only non-scratch key in `scope: "pm"`. */
	watchedKey?: string;
	/** Single-scan quota override (AC-021); defaults to
	 * {@link DEFAULT_DISPATCH_MAX_PER_SCAN}. */
	maxPerScan?: number;
	/** Run-identity gate on the task's own product (AC-022, T-20). Default: no
	 * information, i.e. pre-T-20 behaviour — the queue row alone decides.
	 * `readTaskContent` is lazy so a candidate with its own run record is decided
	 * without reading task.md. */
	runVerdict?: (task: {
		taskKey: string;
		taskDir: string;
		readTaskContent: () => string;
	}) => { ok: true } | { ok: false; reason: RunIdentityRefusal; detail?: string };
	/** Alarm sink (AC-020/AC-021). Production wires it to the ledger row (and
	 * from there to the PM alert); the scan itself never invents a write path. */
	onAlarm?: (alarm: DispatchAlarm) => void;
}

export async function dispatchNewTasks(
	workerStore: WorkerStore,
	agenticdocRoot: string,
	opts: DispatchScanOptions = {},
): Promise<void> {
	// Worker tasks live under {key}/workers/<task-key>/task.md (owner = AgenticTask
	// key) or _scratch/workers/<task-key>/task.md (keyless ad-hoc). Root-level
	// task dirs are no longer dispatched - they polluted the key namespace.
	if (!fs.existsSync(agenticdocRoot)) return;
	// Read the queue once, through `readQueue()`: its rows drive the
	// already-queued set, and any unreadable row aborts the whole scan
	// (AC-020/AC-023). This is the guard IN-3 lacked — the old code built the set
	// from `readAll()`, so a row the parser silently dropped looked like a task
	// that had never run and the entire project was re-queued (252 rows within
	// one second, 2026-10-10T02:50:05Z, peak 66 concurrent workers).
	const queue = workerStore.readQueue();
	if (queue.unparsable.length > 0) {
		opts.onAlarm?.({
			kind: "queue-rows-unparsable",
			count: queue.unparsable.length,
			detail: queue.unparsable[0]?.reason,
		});
		return;
	}
	const dispatched = new Set(queue.rows.map((e) => e.taskKey));
	const scope = opts.scope ?? "cli";
	const maxPerScan = opts.maxPerScan ?? readDispatchMaxPerScan(agenticdocRoot);
	const queueIsEmpty = queue.rows.length === 0;
	let queued = 0;

	// Visibility for the two "skipped, not refused" classes (T-19/T-20): keys
	// outside this window's scope, and candidates whose product already ended the
	// run. Both are aggregated per scan and go through the same alarm channel
	// (once per kind per session at the wiring), so a healthy project sees at
	// most one row per session instead of one per candidate.
	const outOfScope: string[] = [];
	const runRefused: Array<{ taskKey: string; reason: RunIdentityRefusal; detail?: string }> = [];
	const flushScanAlarms = (): void => {
		if (outOfScope.length > 0) {
			opts.onAlarm?.({
				kind: "out-of-scope",
				count: outOfScope.length,
				detail: `${outOfScope.slice(0, 3).join(",")}${outOfScope.length > 3 ? ",…" : ""}`,
			});
		}
		if (runRefused.length > 0) {
			// Aggregate, bounded: the PM needs to see WHICH tasks and WHY (the
			// distinct reasons are what tells a stale ledger from a live run),
			// without one ledger row per candidate.
			const reasons = [...new Set(runRefused.map((r) => r.reason))].sort().join(",");
			const shown = runRefused
				.slice(0, 3)
				.map((r) => `${r.taskKey}:${r.reason}${r.detail ? `(${r.detail})` : ""}`)
				.join(",");
			opts.onAlarm?.({
				kind: "run-ledger-conflict",
				count: runRefused.length,
				detail: `${runRefused.length} refused (${reasons}): ${shown}${runRefused.length > 3 ? ",…" : ""}`,
			});
		}
	};

	let owners: fs.Dirent[];
	try {
		owners = fs.readdirSync(agenticdocRoot, { withFileTypes: true });
	} catch {
		return;
	}

	for (const owner of owners) {
		if (!owner.isDirectory() || owner.name.startsWith(".")) continue;
		// Scope (AC-019): the PM-side automatic scan only looks at the key this
		// window watches plus the keyless scratch. Explicit callers (the `mw`
		// command surface, refreshers, tests) stay global, which is why this is
		// opt-in per call site instead of a hard restriction.
		if (scope === "pm" && owner.name !== SCRATCH_WORKERS_KEY && owner.name !== opts.watchedKey) {
			outOfScope.push(owner.name);
			continue;
		}
		const workersDir = path.join(agenticdocRoot, owner.name, "workers");
		let taskDirs: fs.Dirent[];
		try {
			taskDirs = fs.readdirSync(workersDir, { withFileTypes: true });
		} catch {
			continue; // owner has no workers/ dir (plain key or meta entry)
		}
		// Collect undispatched tasks FIRST (AC-010): a key with nothing new to
		// queue must not even evaluate the docs gate — fully-queued undoc keys
		// are historical, not actionable, and gate noise for them drowns real
		// blockage in multi-key projects.
		const undispatched: Array<{ taskKey: string; taskMdPath: string }> = [];
		for (const taskDir of taskDirs) {
			if (!taskDir.isDirectory() || taskDir.name.startsWith(".")) continue;
			const taskKey = taskDir.name;
			if (dispatched.has(taskKey)) continue;
			const taskMdPath = path.join(workersDir, taskKey, "task.md");
			if (!fs.existsSync(taskMdPath)) continue;
			// D-104: conductor-owned tasks (origin: conductor) never enter the TS
			// dispatch path — not queued, not upserted, and not counted as
			// undispatched work for the docs gate below. The conductor is their
			// only queue writer; its reconciliation is the sole repair path.
			if (isConductorTask(taskMdPath)) continue;
			// AC-022 (T-20): the product carries the run's own terminal state. A task
			// whose run.json already ended is never re-queued (the queue row is a
			// cache, the product is the truth) and a live run is never duplicated;
			// more work on a finished task means a NEW task_key declaring
			// `supersedes:`. Candidates without any run record keep the pre-T-20
			// behaviour (zero backfill, P-018). The task.md read is lazy, so a
			// candidate that already has a run record is decided without any read.
			if (opts.runVerdict) {
				const verdict = opts.runVerdict({
					taskKey,
					taskDir: path.join(workersDir, taskKey),
					readTaskContent: () => fs.readFileSync(taskMdPath, "utf8"),
				});
				if (!verdict.ok) {
					runRefused.push({ taskKey, reason: verdict.reason, detail: verdict.detail });
					continue;
				}
			}
			undispatched.push({ taskKey, taskMdPath });
		}
		if (undispatched.length === 0) continue;
		// AC-020: an empty queue plus product evidence in the very tasks we are
		// about to queue is the IN-3 shape — the queue lost its rows while the
		// work had already run. Refuse the whole scan instead of re-running
		// history; a real fresh project has no such evidence and dispatches.
		if (queueIsEmpty && undispatched.some((t) => hasProductEvidence(path.dirname(t.taskMdPath)))) {
			flushScanAlarms();
			opts.onAlarm?.({ kind: "queue-unreadable", count: undispatched.length, detail: owner.name });
			return;
		}
		// Docs gate, phase-tiered (mw-worker-visibility-gate D-110): the tier comes
		// from the SCAN KEY's own phase (its pm-state '- Phase:' line), never from
		// this window's watch — the background scan and the dispatch_worker tool
		// entry must not diverge. _scratch is the ad-hoc escape hatch. Report
		// each blocked key at most once.
		if (owner.name !== SCRATCH_WORKERS_KEY) {
			const ownerPhase = new StateManager(agenticdocRoot, owner.name).read().phase ?? "";
			const gaps = dispatchDocGaps(agenticdocRoot, owner.name, ownerPhase);
			if (gaps.length > 0) {
				if (!opts.warnedKeys?.has(owner.name)) {
					// Mark as warned only when the notifier actually broadcast —
					// a suppressed broadcast (scoped to another window's key) must
					// not burn this key's once-per-session slot (review m1).
					if (opts.onDocGate?.(owner.name, gaps) !== false) {
						opts.warnedKeys?.add(owner.name);
					}
				}
				continue;
			}
		}
		for (const { taskKey, taskMdPath } of undispatched) {
			// AC-021: one scan may queue at most `maxPerScan` rows. Exceeding the
			// quota means the scan is looking at something it does not understand,
			// not that hundreds of tasks need running.
			if (queued >= maxPerScan) {
				flushScanAlarms();
				opts.onAlarm?.({ kind: "dispatch-quota", count: queued });
				return;
			}
			const taskContent = fs.readFileSync(taskMdPath, "utf8");
			const { cli, provider } = pickWorkerRoute(taskContent);
			const model = readModel(taskContent);
			try {
				await dispatchTask(
					{
						taskKey,
						status: "pending",
						cli,
						provider,
						model,
						taskPath: taskMdPath,
					},
					workerStore,
				);
				queued += 1;
			} catch (err) {
				// Fail-closed (mw-dual-workspace AC-007): an unusable target.yml
				// must never silently degrade to an un-injected task.md — the task
				// stays undispatched and is retried on the next scan once the
				// config is fixed. Per-task isolation: one bad task never blocks
				// the rest of the scan.
				console.error(`[mw] dispatch refused for ${taskKey}: ${err instanceof Error ? err.message : String(err)}`);
			}
		}
	}
	flushScanAlarms();
}

/** Continuation directive appended to terminal worker results: the finish
 * call wakes an idle PM (triggerTurn) — this line tells it what "continue the
 * PM loop" means per terminal status, so results are processed and the next
 * task is dispatched without the user re-prompting. Timeout failures get an
 * explicit retry policy (AC-004/D-005): the Exit Reason in the readback body
 * distinguishes idle (true hang) from wall (healthy but out of budget). */
const PM_CONTINUE_HINT =
	"[mw] worker 终态回读。请继续 PM 循环：吸收上述结果（done→推进下一任务/phase；failed→读 worker.log 与 trace.log 排查后决定重试或修复；needs-clarification→整理问题向用户澄清；超时失败（Exit Reason 含 idle/wall timeout）→ wall 型用双倍 timeout 预算重派一次，再失败转 PM 直执，idle 型直接排查环境），然后派发下一个任务或汇报阶段完成。吸收终态结果后调用 ack_worker_result(task_key)（或 /mw ack all）确认处理完成，widget 待处理区才会清空。";

/** Runtime stats for terminal worker summaries (AC-013):
 * ` (6m-style coarse duration, ph i/n)`. Preference order: exact [START]→[END]
 * interval from trace.log (present on every new-bundle terminal task), ≥2
 * [HEARTBEAT] lines (older format), then the queue row's dispatchedAt→updatedAt
 * (coarse but always present). Empty when nothing is derivable. */
function heartbeatStatsSuffix(taskDir: string, entry: WorkerEntry): string {
	const prog = readTaskProgress(taskDir);
	if (prog?.startTs && prog.endTs) {
		const durMs = Math.max(0, Date.parse(prog.endTs) - Date.parse(prog.startTs));
		const ph = prog.endPhases && prog.endPhases !== "-" ? `, ph ${prog.endPhases}` : "";
		return ` (${formatHeartbeatAge(durMs)}${ph})`;
	}
	const hb = prog?.heartbeat;
	if (hb && hb.count >= 2) {
		const durMs = Math.max(0, Date.parse(hb.lastTs) - Date.parse(hb.firstTs));
		const ph = hb.phase === "-" ? "" : `, ph ${hb.phase}/${hb.phaseTotal}`;
		return ` (${formatHeartbeatAge(durMs)}${ph})`;
	}
	const durMs = Date.parse(entry.updatedAt) - Date.parse(entry.dispatchedAt);
	if (!Number.isNaN(durMs) && durMs > 0) return ` (${formatHeartbeatAge(durMs)})`;
	return "";
}

/** One pending-gate reminder row from the autopilot ledger
 * (`.agenticdoc/_autopilot/auto-decisions.jsonl`, design D-006). The Python
 * conductor is the single writer and the only judge of "pending past
 * threshold"; this module reads and delivers, it never recomputes the
 * decision (D-005 — one judge, no TS/Python threshold drift). */
interface GateReminder {
	/** 1-based ledger position; the delivery watermark. */
	seq: number;
	gateId: string;
	gateKind: string;
	/** `gate.key`; "" for stage-level / keyless gates. */
	gateKey: string;
	/** 1-based reminder ordinal (1..`gate_reminder_max`, default 2). */
	reminderN: number;
	detail: string;
}

/** Session entry type recording a delivered gate reminder. Read back on
 * restart/resume so the same ledger row is never pushed twice (design D-010).
 * Same mechanism as WATCH_ENTRY_TYPE / AUTOPILOT_SEEN_ENTRY_TYPE. */
export const GATE_REMINDER_ENTRY_TYPE = "agent-team-loop:gate-reminder-seen";

/** Read `phase:"remind"` rows from the autopilot ledger (read-only, D-005/
 * D-006). Malformed / torn lines are skipped: a broken ledger must never take
 * the poll loop down, and the conductor's per-line append makes a partial
 * trailing line the only realistic failure. */
function readGateReminders(agenticdocRoot: string): GateReminder[] {
	const ledger = path.join(agenticdocRoot, "_autopilot", AUTO_DECISIONS_FILE);
	let raw: string;
	try {
		raw = fs.readFileSync(ledger, "utf8");
	} catch {
		return []; // no ledger yet (producer absent or nothing recorded) — nothing to deliver
	}
	const out: GateReminder[] = [];
	for (const line of raw.split("\n")) {
		const trimmed = line.trim();
		if (trimmed === "") continue;
		let parsed: unknown;
		try {
			parsed = JSON.parse(trimmed);
		} catch {
			continue; // torn/partial line during a concurrent append
		}
		if (typeof parsed !== "object" || parsed === null) continue;
		const row = parsed as Record<string, unknown>;
		if (row.phase !== "remind") continue;
		const gateId = typeof row.gate_id === "string" ? row.gate_id : "";
		const reminderN = typeof row.reminder_n === "number" ? row.reminder_n : 0;
		if (gateId === "" || reminderN <= 0) continue;
		out.push({
			seq: typeof row.seq === "number" ? row.seq : 0,
			gateId,
			gateKind: typeof row.gate_kind === "string" ? row.gate_kind : "",
			gateKey: typeof row.gate_key === "string" ? row.gate_key : "",
			reminderN,
			detail: typeof row.detail === "string" ? row.detail : "",
		});
	}
	return out;
}

export function startWorkerPollLoop(
	pi: ExtensionAPI,
	workerStore: WorkerStore,
	ackStore: AckStore,
	indexStore: IndexStore,
	agenticdocRoot: string,
	watch: PmWatchState,
	ui: PmUiHolder,
	pollIntervalMs = POLL_INTERVAL_MS,
): NodeJS.Timeout {
	// Baseline snapshot: rows already terminal when this window opens are
	// history — never replay their summaries. Only transitions observed while
	// this session is open are notified, at most once each.
	const notified = new Set(
		workerStore
			.readAll()
			.filter((e) => isTerminal(e.status))
			.map((e) => e.taskKey),
	);
	// Running workers already escalated for divergence (AC-004): one PM wake
	// per task, at the first mid/high convergence checkpoint.
	const escalated = new Set<string>();
	let widgetShown = false;
	// Pending-gate reminder delivery (AC-005/AC-018; design D-005/D-006/D-010).
	// The conductor (Python) is the sole decider and writer; this loop is the
	// only channel that wakes an idle PM (deliverPmAlert → triggerTurn). The same
	// ledger row must never wake the PM twice:
	//   - `reminderWatermark` = highest delivered ledger `seq`, persisted per
	//     session as a pi entry: a restart/resume continues where it left off and
	//     an append-only ledger row can never be re-delivered;
	//   - `unsequencedSeen` is the process-local fallback for a row missing `seq`
	//     (the conductor always sets it, so this is belt-and-braces only).
	// The watermark starts at the ledger's high-water mark at window open, so a
	// fresh window does not replay reminders that predate it (mirrors the
	// `notified` worker baseline). `reminderHistoryRead` gates the one-shot
	// resume path: when this session already recorded deliveries, the watermark
	// drops back to the last recorded seq so rows appended while the window was
	// down still reach the PM.
	const unsequencedSeen = new Set<string>();
	let reminderWatermark = 0;
	{
		const rows = readGateReminders(agenticdocRoot);
		for (const r of rows) if (r.seq > reminderWatermark) reminderWatermark = r.seq;
	}
	let reminderHistoryRead = false;

	return setInterval(() => {
		try {
			// Live bottom widget for the watched key (per-window state, NOT the
			// shared _index.parallel active set — every window decides its own key).
			if (watch.key) {
				applyWatchWidget(
					ui,
					renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, watch.key, watch.dispatchedTaskKeys),
				);
				widgetShown = true;
			} else if (widgetShown) {
				applyWatchWidget(ui, undefined);
				widgetShown = false;
			}

			const entries = workerStore.readAll();
			// Divergence escalation (AC-004): running workers past the convergence
			// checkpoint whose machine risk is mid/high wake the PM once per task
			// with the evidence — the PM (fullest context) decides continue /
			// descope / kill + split / takeover. Low-risk checkpoints stay in the
			// widget only; no cross-window broadcast (scoped to the watched key ∪
			// this window's dispatched tasks — mw-crosskey-risk-escalation D-101).
			for (const entry of entries) {
				if (entry.status !== "running" || escalated.has(entry.taskKey)) continue;
				// Ownership is "watched key OR dispatched by this window": a task this
				// window sent across keys (explicit `key:` dispatch, gate fallback to
				// _scratch) is still this PM's work, while other windows' workers stay
				// silent. `!watch.key` stays first: a window watching nothing must not
				// start delivering off historical dispatch records.
				const ownerKey = ownerKeyOf(entry, agenticdocRoot);
				const owned = watch.dispatchedTaskKeys?.has(entry.taskKey) ?? false;
				if (!watch.key || (ownerKey !== watch.key && !owned)) continue;
				const ck = readTaskProgress(path.dirname(entry.taskPath))?.checkpoint;
				if (!ck || ck.risk === "low") continue;
				escalated.add(entry.taskKey);
				const taskDir = path.dirname(entry.taskPath);
				// Cross-key alerts carry the owner key right after the worker name
				// (D-102) so the PM can tell an off-watch task from a watched-key one;
				// the watched-key label keeps the byte-exact `'name' ` form (AC-004).
				const workerLabel =
					ownerKey === watch.key ? `'${entry.taskKey}' ` : `'${entry.taskKey}'（owner key=${ownerKey}）`;
				deliverPmAlert(
					pi,
					`[mw] 发散风险：worker ${workerLabel}检查点 risk=${ck.risk}` +
						`（elapsed ${Math.round(ck.elapsedS / 60)}m，reads=${ck.reads} writes=${ck.writes}，phases=${ck.phases}，` +
						`重复读 top=${ck.repeatTop}）。机器判据仅供参考——请结合本 key 最全上下文判断：继续等待 / steer 收窄范围 / 终止并分拆重派 / PM 直执。` +
						`证据：${path.join(taskDir, "trace.log")}（[CHECKPOINT] 行）与 ${path.join(taskDir, "progress.md")}（自评行；无写工具角色另含框架机器行）。`,
				);
			}
			for (const entry of entries) {
				if (notified.has(entry.taskKey) || !isTerminal(entry.status)) continue;
				notified.add(entry.taskKey);
				// One-shot transcript summaries fire only for this window's watched
				// key; without a watched key the window stays silent (no cross-window
				// broadcast). The widget above still shows current state either way.
				if (!watch.key || ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;
				// Task dir from the queue row taskPath: works for keyed {key}/workers/<task-key>/ and legacy root paths.
				const taskDir = path.dirname(entry.taskPath);
				// AC-007/DD-08 residual risk: a contract-allowed write whose basename
				// still names a deny-list artifact is only observable here (the guard
				// wrote `blocked=false risk=deny-basename` and moved on). Reuses the
				// single dispatch-alarm ledger channel; `notified` above bounds it to
				// once per task per session.
				recordWriteScopeResidualRisks(agenticdocRoot, entry.taskKey, taskDir);
				// Terminal readback (AC-014): inject the full output.md body into
				// the conversation so worker results reach the PM without manual
				// file reads. Falls through to the spawn-failure / no-output
				// notices when there is nothing to read back. Sent via
				// deliverWorkerResult (triggerTurn) so an idle PM wakes up,
				// processes the result, and runs the next step — the finish call
				// of dispatch → monitor → finish call → pm run (AC-015).
				const header = `[${entry.taskKey}] ${entry.status}${heartbeatStatsSuffix(taskDir, entry)}`;
				const body = readOutputBody(taskDir);
				if (body) {
					deliverWorkerResult(pi, `${header}:\n\n${body}\n\n${PM_CONTINUE_HINT}`);
				} else {
					// Terminal but no output.md summary — never stay silent. Prefer the
					// launcher's exact spawn-failure reason (e.g. missing credential) over
					// the generic crash/timeout guess; both point at the per-task log.
					const logPath = path.join(taskDir, "worker.log");
					const spawnFailure = readSpawnFailure(taskDir);
					deliverWorkerResult(
						pi,
						`${header} — ${
							spawnFailure
								? `${spawnFailure}。日志：${logPath}`
								: `无 output.md 摘要（worker 可能崩溃/超时）。日志：${logPath}`
						}\n\n${PM_CONTINUE_HINT}`,
					);
				}
			}

			// Pending-gate reminders (appended last: the worker terminal-readback
			// order above must not change). Read-only — the ledger belongs to the
			// conductor; this branch never writes it.
			const reminders = readGateReminders(agenticdocRoot);
			if (!reminderHistoryRead) {
				reminderHistoryRead = true;
				let delivered = 0;
				try {
					for (const e of ui.ctx?.sessionManager.getEntries() ?? []) {
						if (e.type !== "custom" || e.customType !== GATE_REMINDER_ENTRY_TYPE) continue;
						const data = e.data as { seq?: unknown } | undefined;
						if (typeof data?.seq === "number" && data.seq > delivered) delivered = data.seq;
					}
				} catch {
					// Session entries unavailable — treat this as a fresh window.
				}
				// Resume from the recorded point (may be below the open-time baseline,
				// so rows appended while this window was down are still delivered);
				// a fresh session keeps the no-replay baseline.
				if (delivered > 0) reminderWatermark = delivered;
			}
			for (const reminder of reminders) {
				// Multi-window scope (D-010): a keyed gate is only this window's
				// business when it watches that key; keyless/stage-level gates fall
				// through to the per-session watermark. A window watching nothing
				// stays silent, like the worker summaries above.
				if (!watch.key) continue;
				if (reminder.gateKey !== "" && reminder.gateKey !== watch.key) continue;
				const dedup = `${reminder.gateId}:${reminder.reminderN}`;
				if (reminder.seq > 0) {
					// Session watermark: the row was delivered already (this tick or a
					// previous session) whenever its seq is not ahead of the mark.
					if (reminder.seq <= reminderWatermark) continue;
					reminderWatermark = reminder.seq;
				} else {
					if (unsequencedSeen.has(dedup)) continue;
					unsequencedSeen.add(dedup);
				}
				// Persist the delivery so /new, /resume and restarts do not replay it.
				pi.appendEntry(GATE_REMINDER_ENTRY_TYPE, {
					seq: reminder.seq,
					gateId: reminder.gateId,
					n: reminder.reminderN,
				});
				const scope = reminder.gateKey === "" ? "stage" : `key=${reminder.gateKey}`;
				deliverPmAlert(
					pi,
					`[mw] 门提醒（${reminder.reminderN}）：gate ${reminder.gateId}（kind=${reminder.gateKind}，${scope}）已 pending 超阈，等待人工应答。` +
						`（判定由 conductor 完成；用 /autopilot gates 查看，/autopilot gate ${reminder.gateId} approve|reject 应答。）` +
						(reminder.detail ? ` ${reminder.detail}` : ""),
				);
			}
		} catch {
			// Transient I/O error (e.g. EACCES during concurrent rename) — skip this tick
		}
	}, pollIntervalMs);
}

/** Marker opening the injected parallel-protocol block, and the idempotency
 * guard: a handler that already sees it in the chained system prompt must not
 * append it a second time (two loaded bundle copies would otherwise duplicate
 * the text on every run). */
export const PARALLEL_PROTOCOL_MARKER = "[mw] 并行优先协议";

/** Static parallel-first rules appended to the PM window's system prompt once
 * per agent run (mw-parallel-protocol). Static on purpose: a constant suffix
 * keeps the system-prompt prefix cacheable, and `before_agent_start` costs no
 * session tokens (an injected message would accumulate one per run). The two
 * conflict surfaces are deliberately different: research/review workers are
 * read-only (worker-mode.ts TOOL_ALLOWLISTS), so research batches in the
 * spec/design phases parallelize freely and only need a unique note file per
 * research question; coding workers share files and must be split by
 * file/module boundary. PM-only by construction: pmActivate() runs only when
 * PI_WORKER_TASK is unset (index.ts). */
export const PARALLEL_PROTOCOL = [
	`${PARALLEL_PROTOCOL_MARKER}（PM 常驻规则）：`,
	"1. 拆解任何 phase（spec/design/plan/tasks）之前，先做并行性分析：可并行单元 / 共享资源与文件冲突面 / 必须串行的理由。",
	"2. spec/design 的调研与证据收集默认全并行：把调研拆成互不重叠的研究问题 RQ-1..N，一次性派发 N 个 type: research worker",
	"   （只读角色，彼此无文件冲突），每个 RQ 只写唯一的 evidence/research/<phase>-<rq-slug>-<date>.md；禁止两个 worker 写同一文件。",
	"3. 编码按文件/模块边界并行：同一文件同一时刻只允许一个 worker。",
	"4. 相位文档（spec.md / design.md）由 PM 自己串行写，不派 worker。",
	"5. 派发前先看 widget 上的 running worker 数：能并行就不要串行等待；worker 终态回读后立刻补派下一批。",
	"6. 引用图片/截图/mockup 的任务用 type: vision 派发（视觉角色，worker 读取图片文件并受 image 能力门禁约束）。",
].join("\n");

export function pmActivate(pi: ExtensionAPI): void {
	const projectDir = process.cwd();
	const agenticdocRoot = resolveAgenticdocRoot(projectDir);
	const workerStore = new WorkerStore(agenticdocRoot);
	const ackStore = new AckStore(agenticdocRoot);
	const indexStore = new IndexStore(agenticdocRoot);

	// Per-window watch state: the key THIS window explicitly executes (set via
	// /mw-watch or /pm-key switch|new). Worker summaries and the bottom progress
	// widget are scoped to it — replacing the old global active-keys matching
	// that made every window notify about every active key.
	const watch: PmWatchState = { key: undefined };
	const ui: PmUiHolder = { ctx: undefined };
	const refreshWatch = (ctx: ExtensionContext): void => {
		if (!watch.key) {
			setWatchWidget(ctx, undefined);
			return;
		}
		setWatchWidget(
			ctx,
			renderWatchLines(indexStore, workerStore, ackStore, agenticdocRoot, watch.key, watch.dispatchedTaskKeys),
		);
	};

	// Register commands and tools during loading (safe — not action methods)
	registerPmKeyCommands(pi, indexStore, watch, refreshWatch, agenticdocRoot);
	registerPmSaveCommand(pi, indexStore, workerStore, watch, agenticdocRoot);
	registerMwCommands(pi, projectDir, workerStore, ackStore, watch, agenticdocRoot);
	registerMwTools(pi, projectDir);
	registerAdvancePhaseTool(pi, projectDir, indexStore);
	registerWorkerTools(pi, workerStore, ackStore, indexStore, agenticdocRoot, watch, projectDir);
	registerSwitchKeyTool(pi, indexStore, watch, refreshWatch, agenticdocRoot);
	registerWorkerCommands(pi, workerStore, indexStore, agenticdocRoot, watch, projectDir);
	// RAG tool surface (D-002): registration is structural — an empty enabled
	// set registers nothing and probes nothing. A broken config must not take
	// the whole PM window down (dispatch is gated separately in ui-bridge).
	try {
		registerRagTools(pi, projectDir);
	} catch (err) {
		console.error(`[mw] rag tools disabled: ${err instanceof Error ? err.message : String(err)}`);
	}
	registerWatchCommand(pi, watch, refreshWatch, indexStore);
	// Autopilot console (T-15): /autopilot status|gates|gate|timeline|enable|
	// disable|pause|resume|roadmap — stateless, file-derived (D-005).
	registerAutopilotCommands(pi, projectDir);
	// Dispatch model chain, main-window side (mw-dispatch-models): record this
	// window's model for worker inheritance and apply a configured `main` role.
	registerMainWindowModel(pi);

	// Hard gate: pm-state.md's '- Phase:' / '- Claim-Id:' interface lines are
	// script-owned (advance_phase.py / update_index.py). Hand-editing them is
	// how phase gates get bypassed (mw-worker-timeout-convergence: pm-state
	// hand-set to EXECUTE while _index.parallel stayed at SPEC), so the edit is
	// blocked at the tool layer and the agent is pointed at the script.
	registerPmStateGuard(pi, projectDir, agenticdocRoot);

	// Parallel-first protocol (mw-parallel-protocol): append the constant block
	// to this run's system prompt. Appending (never replacing) preserves what
	// other extensions chained in before us.
	pi.on("before_agent_start", (event) => {
		const base = typeof event.systemPrompt === "string" ? event.systemPrompt : "";
		if (base.includes(PARALLEL_PROTOCOL_MARKER)) return undefined;
		return { systemPrompt: base === "" ? PARALLEL_PROTOCOL : `${base}\n\n${PARALLEL_PROTOCOL}` };
	});

	// Start worker status poll loop (setInterval is safe; displaySummary inside fires later)
	const pollHandle = startWorkerPollLoop(pi, workerStore, ackStore, indexStore, agenticdocRoot, watch, ui);
	// Session teardown stops the loop (review m3): a fresh runtime re-runs
	// pmActivate and starts a new one, so this only removes the zombie that
	// would keep ticking against a disposed context after /reload or session
	// replacement. It also stops the autopilot monitor panel (AC-018/VC-023):
	// the next session_start re-arms it via autoStartMonitor, so the panel is
	// never left pointing at a disposed ctx (and no interval leaks). stopMonitor
	// is a no-op when no panel is active — it never clears non-active state.
	pi.on("session_shutdown", () => {
		clearInterval(pollHandle);
		stopMonitor();
	});

	// After each agent turn, scan for new task.md files and dispatch them (AC-030).
	// Undocumented keys are skipped and reported once per session (docs gate).
	// Gate broadcast is scoped to this window's watched key (AC-011). The scan
	// itself is scoped to that key too (AC-019): a PM turn must never re-queue
	// another key's history — the whole-project view belongs to `mw` commands.
	const docGateWarned = new Set<string>();
	// Dispatch alarms are once per kind per session: a queue that stays broken
	// must not append a ledger row or wake the PM on every settled turn.
	const dispatchAlarmsSeen = new Set<DispatchAlarmKind>();
	pi.on("agent_settled", () => {
		dispatchNewTasks(workerStore, agenticdocRoot, {
			warnedKeys: docGateWarned,
			onDocGate: makeScopedDocGateNotifier(pi, watch),
			scope: "pm",
			watchedKey: watch.key,
			// AC-022 (T-20): the product decides. A candidate whose own run.json
			// already ended (or is still live) is refused before any queue write;
			// `supersedes:` in task.md is the only way to replace a finished run, and
			// the replaced directory is never touched. Every read is best-effort
			// ("no information" ⇒ pre-T-20 behaviour, zero backfill).
			runVerdict: (task) =>
				evaluateRunIdentity({
					taskDir: task.taskDir,
					readTaskContent: task.readTaskContent,
					resolveTaskDir: (key) => {
						const dir = path.join(path.dirname(task.taskDir), key);
						return fs.existsSync(dir) ? dir : undefined;
					},
				}),
			onAlarm: (alarm) => {
				if (dispatchAlarmsSeen.has(alarm.kind)) return;
				dispatchAlarmsSeen.add(alarm.kind);
				recordDispatchAlarm(agenticdocRoot, alarm);
				deliverPmAlert(pi, `[mw] dispatch 已拒绝：${describeDispatchAlarm(alarm)}`);
			},
		}).catch(() => {
			// Dispatch errors are non-fatal — PM loop continues
		});
	});

	// Spec-write auto-takeover: tool_execution_end carries no args, so correlate
	// them with the args captured on tool_execution_start via toolCallId. Only
	// write/edit calls are tracked; the map entry is consumed on end.
	const pendingToolArgs = new Map<string, { toolName: string; args: unknown }>();
	pi.on("tool_execution_start", (event) => {
		if (event.toolName === "write" || event.toolName === "edit") {
			pendingToolArgs.set(event.toolCallId, { toolName: event.toolName, args: event.args });
		}
	});
	// Evidence-review notices fire once per (key, phase) per session.
	const evidenceReviewNotified = new Set<string>();
	pi.on("tool_execution_end", (event, ctx) => {
		const pending = pendingToolArgs.get(event.toolCallId);
		pendingToolArgs.delete(event.toolCallId);
		if (!pending || event.isError) return;
		const target = docWriteTarget(pending.toolName, pending.args, projectDir, agenticdocRoot);
		if (target) {
			autoTakeOverFromDoc(pi, indexStore, watch, refreshWatch, target.key, target.doc, agenticdocRoot, ctx).catch(
				() => {
					// Takeover failures (e.g. lock contention) must never disturb the turn
				},
			);
			// Phase-doc write with its evidence already present → notice that the
			// doc's claims can be re-reviewed against the notes (plan has no
			// evidence phase). A notice, never an injected instruction.
			if (target.doc !== "plan.md") {
				evidenceReviewNotice(
					ctx,
					target.key,
					target.doc === "spec.md" ? "spec" : "design",
					agenticdocRoot,
					evidenceReviewNotified,
				);
			}
			return;
		}
		// Research-note write: not a claim signal, but it may complete the
		// evidence set for an already-written phase doc → review notice.
		const ev = evidencePhaseFromWrite(pending.toolName, pending.args, projectDir, agenticdocRoot);
		if (ev) {
			evidenceReviewNotice(ctx, ev.key, ev.phase, agenticdocRoot, evidenceReviewNotified);
		}
	});

	// Defer action method calls to after runner.initialize() (session_start fires post-init)
	pi.on("session_start", async (_event, ctx) => {
		// Capture the UI context so the poll loop can render the bottom widget.
		ui.ctx = ctx;
		// Autopilot progress panel: auto-show for enabled projects so a stalled
		// key is visible without anyone running a command (mw-autopilot-stall-feedback
		// AC-008). An explicit /autopilot monitor off suppresses it for this session.
		autoStartMonitor(ctx, projectDir);
		// Resume the watched key this session had before restart/resume.
		await restoreWatch(pi, watch, indexStore, workerStore, ackStore, agenticdocRoot, ctx);
		// Auto-init project if it hasn't been initialized yet. Gate on .agenticdoc
		// (the project marker mw init creates), NOT on a project-local bundle copy:
		// the extension is now installed GLOBALLY (mw setup), so no project-local
		// bundle exists and checking for one would re-run init on every session.
		const initialized = fs.existsSync(path.join(projectDir, ".agenticdoc"));
		if (!initialized) {
			const result = initMw(projectDir);
			if (result.ok) {
				displaySummary(pi, "[mw] Project initialized — .agenticdoc/ .mw/ .pi/extensions/ created.");
			} else {
				displaySummary(pi, `[mw] Init failed: ${result.error}`);
				return;
			}
		}

		// Auto-start mw background service if not already running.
		// After spawning, poll for the PID file so the agent's first turn doesn't
		// race against Python startup and falsely report mw as not running.
		// Stability window: the PID must stay alive for 3s — mw serve can die
		// right after startup (route precheck failure) and the old check would
		// report a false "started" in that window (mw-dispatch-reliability AC-005).
		const mwStatus = getMwStatus(projectDir);
		if (!mwStatus.running) {
			const started = startMw(projectDir);
			if (started) {
				const confirmed = await waitForMwStart(projectDir, 8000);
				displaySummary(
					pi,
					confirmed
						? "[mw] Background service started."
						: "[mw] Background service 启动未确认（可能预检失败或仍在启动）——运行 /mw doctor 诊断。",
				);
			} else {
				displaySummary(pi, "[mw] Could not find mw.py — run `mw start --project=.` manually.");
			}
		} else {
			// Stale-serve detection: a serve started before the current mw code
			// silently misses features (e.g. conductor supervision) — surface it
			// instead of letting /autopilot enable promise a conductor that never
			// spawns.
			const stale = serveStaleness(projectDir);
			if (stale?.stale) {
				displaySummary(
					pi,
					`[mw] serve (PID ${mwStatus.pid}) is running stale code — ${stale.detail}. Run /mw restart.`,
				);
			}
		}

		// The project goal is the north-star every key/spec derives from.
		// Do NOT fabricate a placeholder — if it isn't established yet, softly
		// guide the user into the goal brainstorm workflow (/goal). An
		// established goal (or a legacy goal.md with content) is left untouched.
		// Headless sessions skip the goal nudge (see nudgeGoalUnestablished).
		nudgeGoalUnestablished(pi, agenticdocRoot, ctx.hasUI);
	});
}
