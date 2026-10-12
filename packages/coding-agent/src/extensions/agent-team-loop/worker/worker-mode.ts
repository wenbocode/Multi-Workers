import * as fs from "node:fs";
import * as path from "node:path";
import { minimatch } from "minimatch";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { killTrackedDetachedChildren } from "../../../utils/shell.ts";
import { recordDispatchAlarm } from "../pm/pm-orchestrator.ts";
import { WRITE_SURFACE_MARKER, WRITE_SURFACE_MARKER_END } from "../pm/ui-bridge.ts";
import { Breaker, Budget } from "../rag/budget.ts";
import { requiredFor } from "../rag/config.ts";
import { appendEvidence } from "../rag/evidence.ts";
import { researchDocEvidence, scanCitations, validateResearchDoc } from "../rag/research-doc.ts";
import {
	applyRagTools,
	RAG_CHAT_BUDGET_HEADER,
	RAG_TIME_BUDGET_HEADER,
	type RagRuntime,
	registerRagTools,
} from "../rag/tools.ts";
import { hasDeliverableEvidence } from "../shared/deliverable-evidence.ts";
import { roleForTaskType } from "../shared/dispatch-models.ts";
import { formatHeartbeatAge, HEARTBEAT_INTERVAL_MS } from "../shared/heartbeat.ts";
import { controlRootFromTaskPath } from "../shared/paths.ts";
import {
	collectArtifacts,
	isTerminalRunStatus,
	newRunId,
	parseSupersedes,
	RUN_SCHEMA,
	type RunState,
	type RunStatus,
	runMarker,
	writeRunState,
} from "../shared/run-store.ts";
import { findTypeEscalation, readTaskType, scanBodyTypeLines } from "../shared/task-frontmatter.ts";
import {
	appendCheckpoint,
	appendEnd,
	appendError,
	appendGoalCheck,
	appendHeartbeat,
	appendModel,
	appendPhase,
	appendProgressLine,
	appendStart,
	appendTimeout,
	appendTool,
	appendToolError,
	appendTrace,
	formatMachineCheckpoint,
	type WriteOutputOpts,
	writeOutput,
} from "./output-writer.ts";
import type { TaskPhase } from "./phase-runner.ts";
import { goalMtime, writePhaseFile } from "./phase-runner.ts";
import {
	applyParentRootUnion,
	checkReadScopeCall,
	isSameOrUnder,
	normalizeForCompare,
	parentRootFromTaskContent,
	type ReadScopeConfig,
	type ReadScopeRejection,
	type ReadScopeState,
	readScopeConfigFromMeta,
} from "./read-scope.ts";
import { registerWorkerFileTool, WORKER_FILE_TOOL } from "./worker-file-tool.ts";

// ── Tool allowlists by task type ─────────────────────────────────────────────

const TOOL_ALLOWLISTS: Record<string, string[]> = {
	coding: ["read", "write", "edit", "bash", "find", "grep", "ls"],
	review: ["read", "find", "grep", "ls"],
	research: ["read", "find", "grep", "ls", "bash"],
	// Autopilot typed dispatches (D-107/VC-023): per-type tool sets must stay
	// EXACTLY equal to the Python-side REGISTRY in
	// packages/multi-workers/autopilot/dispatch.py (entry order included) —
	// the T-17 L0 parity test locks that equality. "fallback" is the internal
	// default bucket, not a dispatchable type.
	"roadmap-writer": ["read", "write", "edit", "find", "grep", "ls"],
	"phase-writer": ["read", "write", "edit", "bash", "find", "grep", "ls"],
	verifier: ["read", "find", "grep", "ls"],
	reviewer: ["read", "find", "grep", "ls"],
	repair: ["read", "write", "edit", "bash", "find", "grep", "ls"],
	// RAG research bucket (mw-rag-integration D-011): renders rag_chat, the only
	// type allowed to call it. PM/`/worker`-dispatched only — the conductor
	// refuses it on the Python side (conductor_dispatchable=False).
	"rag-research": [
		"read",
		"find",
		"grep",
		"ls",
		"rag_search",
		"rag_symbol",
		"rag_graph",
		"rag_impact",
		"rag_sources",
		"rag_feedback",
		"rag_chat",
	],
	// Vision bucket (mw-vision-role D-001): full coding set, same order as the
	// Python-side REGISTRY entry in autopilot/dispatch.py.
	vision: ["read", "write", "edit", "bash", "find", "grep", "ls"],
	fallback: ["read", "write", "edit", "bash", "find", "grep", "ls"],
};

/** Is this a dispatchable type with an explicit allowlist entry? "fallback"
 * is the internal default bucket (D-107: a `type: fallback` task with
 * origin: conductor must fail closed, not resolve to the full set). */
function isRegisteredType(taskType: string): boolean {
	return taskType !== "fallback" && taskType in TOOL_ALLOWLISTS;
}

export function toolsForType(taskType: string): string[] {
	return TOOL_ALLOWLISTS[taskType] ?? TOOL_ALLOWLISTS.fallback ?? [];
}

/** `toolsForType` plus the narrow write channel for roles with no write/edit
 * tool (D-104/D-106). The allowlist table and `toolsForType` stay byte for
 * byte unchanged (Python parity lock, direct test imports); the writeless
 * extra lives only here. Write roles get the base array untouched, read-only
 * roles get a copy with `worker_file` appended. */
export function activeToolsForType(taskType: string): string[] {
	const base = toolsForType(taskType);
	return base.includes("write") ? base : [...base, WORKER_FILE_TOOL];
}

/** Is this a role whose tool set carries `bash` (contract C3)? */
export function isShellRole(taskType: string): boolean {
	return activeToolsForType(taskType).includes("bash");
}

/** Is this a role with no write/edit tool (contract C3)? Such a role writes
 * only through the narrow `worker_file` channel, so bash is the one structural
 * hole left for the AC-005b write-surface guard. */
export function isWritelessRole(taskType: string): boolean {
	const tools = activeToolsForType(taskType);
	return !tools.includes("write") && !tools.includes("edit");
}

/** Checkpoint self-assessment steer text, split by role (D-104/VC-004).
 * - `hasWriteTools === true`: the pre-change wording byte for byte — the
 *   agent appends its own CKPT line to progress.md with its write tool.
 * - `hasWriteTools === false`: never tells the agent to append to a file it
 *   cannot write. The machine evidence is already on disk (framework-written),
 *   and the self-assessment goes through the narrow tool or the reply.
 * `deliverAs` stays `followUp` for both branches (decided by the caller). */
export function checkpointSteerText(opts: {
	elapsedMs: number;
	budgetMs: number;
	progressPath: string;
	hasWriteTools: boolean;
	narrowTool: string;
}): string {
	if (opts.hasWriteTools) {
		return `[mw checkpoint] 运行 ${formatHeartbeatAge(opts.elapsedMs)}（总预算 ${formatHeartbeatAge(
			opts.budgetMs,
		)}）。请立即自评收敛性，把一行追加到 ${opts.progressPath}：CKPT ${Math.round(
			opts.elapsedMs / 60_000,
		)}m converging=yes|no eta≈<X>m <一句话理由>。若不收敛：立即收窄范围，优先保证已完成部分可交付，不要展开新工作。`;
	}
	return `[mw checkpoint] 运行 ${formatHeartbeatAge(opts.elapsedMs)}（总预算 ${formatHeartbeatAge(
		opts.budgetMs,
	)}）。检查点机器证据（reads/writes/phases/risk）已由框架写入 ${opts.progressPath}。请立即自评收敛性：用 ${
		opts.narrowTool
	} 工具把一行自评写入该文件，或在本回复中直接给出一行 CKPT ${Math.round(
		opts.elapsedMs / 60_000,
	)}m converging=yes|no eta≈<X>m <一句话理由>。若不收敛：立即收窄范围，优先保证已完成部分可交付，不要展开新工作。`;
}

// ── Watchdog budgets (GC-4 as amended 2026-09-09: activity-based hang
// detection + per-task wall budget) ─────────────────────────────────────────

/** Default wall budget. The old 30m value killed healthy tasks (OverCode
 * cpr-004/005: actively working 28s/9s before the kill); 60m covers every
 * observed successful run (7–14m) with margin for generation-heavy tasks. */
export const DEFAULT_BUDGET_MS = 60 * 60_000;

/** Default hang threshold: no activity (token deltas, tools, turns) for this
 * long while the task is unfinished means a dead API call. Conservative —
 * above the 7m legit single-generation observed on glm-5.3 (cpr-003); tighten
 * after confirming streaming deltas arrive on the timi route. */
export const DEFAULT_IDLE_MS = 10 * 60_000;

const CHECKPOINT_ANCHOR_MS = 30 * 60_000;
const CHECKPOINT_REFRESH_MS = 10 * 60_000;
const STEER_MIN_MS = 5 * 60_000;

/** Wall budget: task.md `timeout:` (minutes) > PI_WORKER_TIMEOUT_MS > default. */
export function resolveBudgetMs(timeoutMin: number | undefined, env: string | undefined): number {
	if (timeoutMin !== undefined) return timeoutMin * 60_000;
	const envMs = Number(env);
	if (Number.isFinite(envMs) && envMs > 0) return envMs;
	return DEFAULT_BUDGET_MS;
}

/** Hang threshold from PI_WORKER_IDLE_MS (falling back to the default). */
export function resolveIdleMs(env: string | undefined): number {
	const envMs = Number(env);
	if (Number.isFinite(envMs) && envMs > 0) return envMs;
	return DEFAULT_IDLE_MS;
}

/** Max silence allowed while a tool is in flight, before the in-flight branch
 * of the idle watchdog kills. Root cause (measured 2026-09-26, T-04/AC-005):
 * 22/24 idle kills died while a bash call was in flight with zero
 * `tool_execution_update` — bash updates are output-driven (core/tools/bash.ts),
 * so a long command that prints nothing looked like a hung worker. A tool that
 * is still running legitimately owns the activity clock, but only up to a
 * bound: a genuinely hung tool must still die (VC-006). 30m mirrors the
 * design's floor (D-016) and sits inside the 60m default wall budget, which
 * remains the outer guard. Deliberately a code constant: T-04 forbids a new
 * config key, so this is NOT wired through `_autopilot/config.json`.
 *
 * Deliberately does not change `DEFAULT_IDLE_MS` or the PI_WORKER_IDLE_MS
 * semantics: the threshold was never the root cause. */
export const DEFAULT_TOOL_IDLE_MS = 30 * 60_000;

/** Effective in-flight tool-idle bound: the configured raw idle threshold
 * (lower bound, so a tightened PI_WORKER_IDLE_MS also tightens this) vs the
 * 30m floor. */
export function resolveToolIdleMs(idleMs: number): number {
	return Math.max(idleMs, DEFAULT_TOOL_IDLE_MS);
}

/** First convergence-checkpoint time: the 30m anchor, scaled down
 * proportionally for small budgets so smoke runs exercise the whole path. */
export function checkpointAnchorMs(budgetMs: number): number {
	return Math.min(CHECKPOINT_ANCHOR_MS, Math.max(1_000, Math.round(budgetMs / 2)));
}

/** Deadline-steer time: budget minus min(5m, budget/4). */
export function steerAtMs(budgetMs: number): number {
	return Math.max(1_000, budgetMs - Math.min(STEER_MIN_MS, Math.round(budgetMs / 4)));
}

/** Read-ish tools for checkpoint convergence signals. */
const READ_TOOLS = new Set(["read", "grep", "find", "ls", "glob"]);
/** Write-ish tools for checkpoint convergence signals. */
const WRITE_TOOLS = new Set(["write", "edit"]);

export interface ConvergenceSignals {
	elapsedMs: number;
	/** Checkpoint anchor (min(30m, budget/2)) — the point past which zero
	 * output stops being "warming up" and starts being divergence. */
	anchorMs: number;
	writes: number;
	phasesTotal: number;
	phasesDone: number;
	/** Highest per-target repeat count for reads. */
	repeatTop: number;
}

/** Machine divergence heuristic (AC-004, advisory only — the PM with the
 * fullest context judges and decides):
 * - high: past the anchor with ZERO writes — pure exploration, the cpr-007
 *   pattern (22 minutes of reads, generation never got time to land).
 * - mid: phase framework present but nothing completed past the anchor, or
 *   the same target read ≥4 times (spinning).
 * - low: writes advancing — implementation underway. */
export function computeRisk(s: ConvergenceSignals): "low" | "mid" | "high" {
	if (s.writes === 0 && s.elapsedMs >= s.anchorMs) return "high";
	if ((s.phasesTotal > 0 && s.phasesDone === 0 && s.elapsedMs >= s.anchorMs) || s.repeatTop >= 4) return "mid";
	return "low";
}

// ── Task file parsing ────────────────────────────────────────────────────────

interface TaskMeta {
	type: string;
	/** task.md `phase:` header (the phase axis of `required = role.require OR
	 * phase.require`, T-14). Distinct from the `phases` framework array below. */
	phase?: string;
	phases?: TaskPhase[];
	taskKey: string;
	agenticdocRoot: string;
	/** Dispatch origin marker (D-104): "conductor" on autopilot dispatches,
	 * undefined on manual/legacy tasks (which keep the fallback path, GC-8). */
	origin?: string;
	/** task.md `images:` header (T-09/AC-011): `true` only when the dispatch
	 * declared `images: yes` (the task needs image reads). An undeclared header
	 * stays `undefined` and changes nothing (zero branches). */
	images?: boolean;
	/** TRUE .agenticdoc root — task.md four levels up
	 * (.agenticdoc/{owner}/workers/{taskKey}/task.md → .agenticdoc), where
	 * goal.md lives (D-116). Distinct from `agenticdocRoot`, which is the
	 * owner's workers/ dir and stays the outputDir base (contract unchanged). */
	trueAgenticdocRoot: string;
	/** Wall budget in minutes from the task.md `timeout:` header. */
	timeoutMin?: number;
	/** read_scope entries (D-106), project-root relative. Present → read
	 * containment enabled; absent → zero interception (AC-012 red line). */
	readScope?: string[];
	/** deny_globs entries (mw-dual-workspace AC-006), minimatch dual-basis.
	 * Present → deny firewall active even without read_scope (deny-only). */
	denyGlobs?: string[];
	/** write_scope entries (contract C1/T-03), project-root relative. Present →
	 * the AC-005b bash write surface is narrowed to the intersection with the
	 * default (own taskDir + `<key>/evidence/**`); absent → default surface. */
	writeScope?: string[];
	/** l2_read_file_cap frontmatter (positive int), when present. */
	readFileCap?: number;
	/** l2_read_byte_cap frontmatter (positive int), when present. */
	readByteCap?: number;
	/** task.md `rag_chat_budget:` header (positive int), when present. */
	ragChatBudget?: number;
	/** task.md `rag_time_budget_s:` header (positive int seconds), when present. */
	ragTimeBudgetS?: number;
	/** AC-010/T-12: structure of the C2 contract markers read back from this
	 * task book (see {@link writeSurfaceMarkerState}). */
	writeSurfaceMarker: WriteSurfaceMarkerState;
}

/** Structure of the C2 write-surface contract markers in a task book
 * (AC-010/T-12). The producer is `pm/ui-bridge.ts::applyWriteSurfaceContract`
 * (contract section injected for writeless roles); until now nothing in the
 * execution path read the paired markers back, so the only writer-side
 * guarantee was that idempotency regex — a half-removed or duplicated pair
 * would survive into the task book unobserved. `parseTaskMd` records the
 * structure here and `workerModeActivate` consumes it: `"malformed"` appends
 * one `[WRITE_SURFACE]` audit line. `"absent"` is the normal state for
 * manual/legacy task books (the section is opt-in and conductor-rendered task
 * books never carry it), so absence is deliberately not flagged. Only markers
 * that occupy a whole line count: the section is line-joined, and an inline
 * mention in prose (a task book quoting the marker) is not a section. */
export type WriteSurfaceMarkerState = "absent" | "ok" | "malformed";

export function writeSurfaceMarkerState(content: string): WriteSurfaceMarkerState {
	const lines = content.split(/\r?\n/).map((line) => line.trimEnd());
	const starts = lines.filter((line) => line === WRITE_SURFACE_MARKER).length;
	const ends = lines.filter((line) => line === WRITE_SURFACE_MARKER_END).length;
	if (starts === 0 && ends === 0) return "absent";
	if (starts !== 1 || ends !== 1) return "malformed";
	return lines.indexOf(WRITE_SURFACE_MARKER) < lines.indexOf(WRITE_SURFACE_MARKER_END) ? "ok" : "malformed";
}

export function parseTaskMd(taskPath: string): TaskMeta {
	const content = fs.readFileSync(taskPath, "utf8");
	const lines = content.split("\n");

	const taskType = readTaskType(content).type ?? "default";
	let phase: string | undefined;
	let timeoutMin: number | undefined;
	let origin: string | undefined;
	let images: boolean | undefined;
	const phases: TaskPhase[] = [];
	let currentPhase: TaskPhase | null = null;
	let inPhasePrompt = false;
	let readScope: string[] | undefined;
	let inReadScopeList = false;
	let denyGlobs: string[] | undefined;
	let inDenyGlobsList = false;
	let writeScope: string[] | undefined;
	let inWriteScopeList = false;
	let readFileCap: number | undefined;
	let readByteCap: number | undefined;
	let ragChatBudget: number | undefined;
	let ragTimeBudgetS: number | undefined;

	for (const line of lines) {
		const trimmed = line.trim();
		if (trimmed.startsWith("phase:")) {
			const v = trimmed.slice("phase:".length).trim();
			if (v) phase = v;
		}
		if (trimmed.startsWith("timeout:")) {
			const v = Number(trimmed.slice("timeout:".length).trim());
			if (Number.isFinite(v) && v > 0) timeoutMin = v;
		}
		if (trimmed.startsWith("origin:")) {
			origin = trimmed.slice("origin:".length).trim();
		}
		if (trimmed.startsWith("images:")) images = trimmed.slice("images:".length).trim() === "yes";
		// read_scope renders as a YAML block list (dispatch.py render_task_md):
		// `  - entry` lines after a bare `read_scope:`. Any other line ends the
		// list. `read_scope:` present-but-empty keeps the field defined — the
		// interceptor then fails closed (everything out of scope).
		if (trimmed === "read_scope:") {
			readScope = [];
			inReadScopeList = true;
		} else if (inReadScopeList && !inPhasePrompt) {
			if (trimmed.startsWith("- ")) {
				const item = trimmed.slice(2).trim();
				if (item) readScope?.push(item);
			} else {
				inReadScopeList = false;
			}
		}
		// deny_globs renders like read_scope (dispatch.py render_task_md), but
		// entries are globs — dispatch quotes them (a leading `*` is a YAML
		// alias marker), so strip one pair of surrounding quotes when present.
		if (trimmed === "deny_globs:") {
			denyGlobs = [];
			inDenyGlobsList = true;
		} else if (inDenyGlobsList && !inPhasePrompt) {
			if (trimmed.startsWith("- ")) {
				let item = trimmed.slice(2).trim();
				if ((item.startsWith('"') && item.endsWith('"')) || (item.startsWith("'") && item.endsWith("'"))) {
					item = item.slice(1, -1);
				}
				if (item) denyGlobs?.push(item);
			} else {
				inDenyGlobsList = false;
			}
		}
		// write_scope (contract C1, T-02 → T-03): the producer renders the
		// one-line comma form (`write_scope: a, b`); the read_scope/deny_globs
		// YAML block-list form is accepted too, so the two consumer paths cannot
		// drift apart. A present-but-blank value stays defined as [] (fail-closed,
		// mirroring read_scope); an absent header leaves the field undefined and
		// the consumer falls back to the default surface.
		if (trimmed.startsWith("write_scope:")) {
			const rest = trimmed.slice("write_scope:".length).trim();
			if (rest) {
				writeScope = rest
					.split(",")
					.map((item) => item.trim())
					.map((item) =>
						(item.startsWith('"') && item.endsWith('"')) || (item.startsWith("'") && item.endsWith("'"))
							? item.slice(1, -1)
							: item,
					)
					.filter((item) => item.length > 0);
				inWriteScopeList = false;
			} else {
				writeScope = [];
				inWriteScopeList = true;
			}
		} else if (inWriteScopeList && !inPhasePrompt) {
			if (trimmed.startsWith("- ")) {
				let item = trimmed.slice(2).trim();
				if ((item.startsWith('"') && item.endsWith('"')) || (item.startsWith("'") && item.endsWith("'"))) {
					item = item.slice(1, -1);
				}
				if (item) writeScope?.push(item);
			} else {
				inWriteScopeList = false;
			}
		}
		if (trimmed.startsWith("l2_read_file_cap:")) {
			const v = Number(trimmed.slice("l2_read_file_cap:".length).trim());
			if (Number.isFinite(v) && v > 0) readFileCap = v;
		}
		if (trimmed.startsWith("l2_read_byte_cap:")) {
			const v = Number(trimmed.slice("l2_read_byte_cap:".length).trim());
			if (Number.isFinite(v) && v > 0) readByteCap = v;
		}
		if (trimmed.startsWith(RAG_CHAT_BUDGET_HEADER)) {
			const v = Number(trimmed.slice(RAG_CHAT_BUDGET_HEADER.length).trim());
			if (Number.isFinite(v) && v > 0) ragChatBudget = v;
		}
		if (trimmed.startsWith(RAG_TIME_BUDGET_HEADER)) {
			const v = Number(trimmed.slice(RAG_TIME_BUDGET_HEADER.length).trim());
			if (Number.isFinite(v) && v > 0) ragTimeBudgetS = v;
		}
		if (trimmed.startsWith("- name:")) {
			currentPhase = { name: trimmed.slice("- name:".length).trim(), prompt: "" };
			phases.push(currentPhase);
			inPhasePrompt = false;
		} else if (trimmed === "prompt: |" && currentPhase) {
			inPhasePrompt = true;
		} else if (inPhasePrompt && currentPhase) {
			if (trimmed.startsWith("- ") || trimmed.startsWith("name:")) {
				inPhasePrompt = false;
			} else {
				currentPhase.prompt += `${line}\n`;
			}
		}
	}

	// taskKey is the parent directory name of the task file; `agenticdocRoot`
	// is its parent — the owner's workers/ dir, the outputDir base (contract
	// unchanged). The TRUE .agenticdoc root (goal.md's parent) is four levels
	// up from task.md (D-116 semantic split).
	const agenticdocRoot = path.dirname(path.dirname(taskPath));
	const taskKey = path.basename(path.dirname(taskPath));
	const trueAgenticdocRoot = path.dirname(path.dirname(agenticdocRoot));

	return {
		type: taskType,
		phase,
		phases: phases.length > 0 ? phases : undefined,
		taskKey,
		agenticdocRoot,
		origin,
		images,
		trueAgenticdocRoot,
		timeoutMin,
		readScope,
		denyGlobs,
		writeScope,
		readFileCap,
		readByteCap,
		ragChatBudget,
		ragTimeBudgetS,
		writeSurfaceMarker: writeSurfaceMarkerState(content),
	};
}

// ── Trace helpers ────────────────────────────────────────────────────────────

/** Short, single-line argument summary for trace [TOOL] lines: the file path a
 * read/write/edit targets, the first command line for bash, or the search
 * pattern. Keeps one tool call = one trace line. */
function toolTarget(args: unknown): string {
	const a = args as
		| { path?: unknown; command?: unknown; pattern?: unknown; query?: unknown; file?: unknown }
		| undefined;
	const raw =
		typeof a?.path === "string"
			? a.path
			: typeof a?.command === "string"
				? a.command
				: typeof a?.pattern === "string"
					? a.pattern
					: typeof a?.query === "string"
						? a.query
						: typeof a?.file === "string"
							? a.file
							: "";
	if (!raw) return "";
	return raw.split("\n")[0] ?? "";
}

/** First line of a failed tool result, for trace [TOOL_ERR] lines. */
function toolErrorText(result: unknown): string {
	const r = result as { content?: Array<{ type?: string; text?: unknown }> } | undefined;
	const text = r?.content?.find((c) => typeof c.text === "string")?.text;
	const first = typeof text === "string" ? (text.split("\n")[0] ?? "") : "";
	return first || "tool error";
}

/** Best-effort synchronous status line into worker.log. The launcher redirects
 * the worker's stdout (fd 1) to worker.log; fs.writeSync lands there even when
 * we process.exit() immediately after (async writes would be dropped). */
function writeWorkerLogLine(line: string): void {
	try {
		fs.writeSync(1, `${line}\n`);
	} catch {
		// fd closed / not writable — trace.log and output.md carry the state
	}
}

// ── Process observation + fail-closed gate (D-115/D-107) ──────────────────

/** D-115 process-observation anchor: one pure `[START] pid=<pid>` line per
 * spawn, appended (never reset) to trace.log before the first agent turn —
 * the launcher truncates worker.log per spawn, but trace.log only ever
 * grows, so spawn counts survive. Python autopilot/state.py start_pids
 * counts spawns by exactly this line format (`^\[START\] pid=(\d+)\s*$`);
 * the timestamped [START] runtime anchor from appendStart is a different,
 * coexisting line. */
function appendStartPidLine(taskKey: string, agenticdocRoot: string): void {
	try {
		const dir = path.resolve(agenticdocRoot, taskKey);
		fs.mkdirSync(dir, { recursive: true });
		fs.appendFileSync(path.join(dir, "trace.log"), `[START] pid=${process.pid}\n`, "utf8");
	} catch {
		// Diagnostic append — must never break worker startup
	}
}

/** Append one `[HEADER]` audit line to trace.log (AC-005 §1.4). Best-effort,
 * like the other trace anchors: a diagnostic append must never break startup. */
function appendHeaderTraceLine(taskKey: string, agenticdocRoot: string, line: string): void {
	try {
		const dir = path.resolve(agenticdocRoot, taskKey);
		fs.mkdirSync(dir, { recursive: true });
		fs.appendFileSync(path.join(dir, "trace.log"), `${line}\n`, "utf8");
	} catch {
		// Diagnostic append — must never break worker startup
	}
}

/** AC-005 observability (DRQ-3 §1.4): record how the single-source role was
 * resolved and what the header boundary ignored. `body-type-ignored` lists the
 * below-header `type:` lines the parser refused to read (A8); `BOM detected`
 * makes the Python-side divergence visible; an unregistered type on an UNMARKED
 * task is the GC-8 fallback the PM ruling keeps (origin-marked tasks are
 * refused by `dispatchRefusal` before this is read). Observational only — it
 * never changes the run's fate (T-13 zero interception). */
function appendHeaderAudit(taskKey: string, agenticdocRoot: string, content: string, taskType: string): void {
	const reading = readTaskType(content);
	if (reading.bomStripped) appendHeaderTraceLine(taskKey, agenticdocRoot, "[HEADER] BOM detected");
	const bodyLines = scanBodyTypeLines(content);
	if (bodyLines.length > 0) {
		const shown = bodyLines.slice(0, 4);
		const lines = shown.map((l) => l.line).join(",");
		const values = shown.map((l) => l.value).join(",");
		// The escalation predicate is reported, not enforced here (T-07 scope:
		// the PM ruling only refuses missing/invalid types on origin-marked tasks).
		const escaped = findTypeEscalation(bodyLines, taskType, activeToolsForType) !== undefined;
		appendHeaderTraceLine(
			taskKey,
			agenticdocRoot,
			`[HEADER] body-type-ignored count=${bodyLines.length} lines=${lines} values=${values} ` +
				`escaped=${escaped} role=${roleForTaskType(taskType)}`,
		);
	}
	if (!isRegisteredType(taskType)) {
		appendHeaderTraceLine(
			taskKey,
			agenticdocRoot,
			`[HEADER] unregistered-type-fallback type=${taskType} source=${reading.source} ` +
				`role=${roleForTaskType(taskType)}`,
		);
	}
}

/** Worker-side re-check of the conductor's dispatch-time refusals (D-107
 * double insurance, VC-023): what the Python registry rejects must also fail
 * closed here, so a stale bundle or a non-conductor queue path can never land
 * an unregistered conductor type in the fallback full tool set, nor run a
 * scopeless conductor verifier. Conductor dispatches only — the manual path
 * keeps the GC-8 fallback and the T-13 no-read_scope contract (no origin
 * marker → zero interception) untouched. Returns the exit reason, or
 * undefined when the task may run. */
function dispatchRefusal(meta: TaskMeta): string | undefined {
	if (meta.origin !== "conductor") return undefined;
	if (!isRegisteredType(meta.type)) {
		const registered = Object.keys(TOOL_ALLOWLISTS)
			.filter((t) => t !== "fallback")
			.sort()
			.join(", ");
		return (
			`Fail-closed (D-107/VC-023): this task carries origin: conductor but type '${meta.type}' has no ` +
			`tool-allowlist entry — running it would fall back to the full tool set, which conductor dispatches ` +
			`never get. Registered types: ${registered}.`
		);
	}
	if (meta.type === "verifier" && (meta.readScope?.length ?? 0) === 0) {
		return (
			"Fail-closed (D-106): verifier dispatches require a non-empty read_scope in task.md — " +
			"without one the L2 containment boundary is undefined."
		);
	}
	return undefined;
}

// ── Read-scope rejection records (D-106/AC-009) ──────────────────────────────
// Blocked read-ish calls are recorded twice: immediately in trace.log (the PM
// watch reads trace.log live) and at exit in output.md. Both land in the
// worker task dir, the same directory the output-writer functions use.

/** Append one `[READ_SCOPE]` line to trace.log at block time. */
function appendReadScopeTraceLine(taskKey: string, agenticdocRoot: string, r: ReadScopeRejection): void {
	try {
		const dir = path.resolve(agenticdocRoot, taskKey);
		fs.mkdirSync(dir, { recursive: true });
		fs.appendFileSync(
			path.join(dir, "trace.log"),
			`[READ_SCOPE] ${r.ts} blocked path=${r.path} rule=${r.rule} tool=${r.tool}\n`,
			"utf8",
		);
	} catch {
		// Diagnostic append — a failure must never break the block itself
	}
}

/** Append the `## Read Scope Rejections` section to output.md. Called right
 * after every writeOutput (which overwrites output.md), so the section rides
 * along the unified write-out points on every exit path. No-op when nothing
 * was blocked. */
function appendReadScopeRejectionsSection(
	taskKey: string,
	agenticdocRoot: string,
	rejections: ReadScopeRejection[],
): void {
	if (rejections.length === 0) return;
	try {
		const dir = path.resolve(agenticdocRoot, taskKey);
		fs.mkdirSync(dir, { recursive: true });
		const lines = ["## Read Scope Rejections", "", "| tool | rule | path | ts |", "| ---- | ---- | ---- | ---- |"];
		for (const r of rejections) {
			lines.push(`| ${r.tool} | ${r.rule} | ${r.path.replaceAll("|", "\\|")} | ${r.ts} |`);
		}
		fs.appendFileSync(path.join(dir, "output.md"), `\n${lines.join("\n")}\n`, "utf8");
	} catch {
		// Best-effort at exit — nothing else we can do
	}
}

// ── Bash write-surface guard (AC-005b / contract C3) ─────────────────────────
//
// A role with `bash` but no `write`/`edit` (today: `research` only) can bypass
// its narrow `worker_file` channel with a shell command (the old gap R23). The
// guard classifies each bash command against KNOWN write patterns, extracts the
// target paths and blocks only targets outside the worker's write surface (own
// taskDir + `<key>/evidence/**`, narrowed by the task's `write_scope:` header
// when present). Tier P1 (design DD-03): the failure mode is a MISS — an exotic
// write slips through — never a false block, so pure-read and unclassifiable
// commands pass without a trace line.

/** One extracted write target. */
export interface BashWriteCandidate {
	/** Raw path exactly as written in the command. */
	target: string;
	/** Which write pattern produced it (audit/debug). */
	pattern: string;
	/** False when the target word carries a live shell expansion (`$`, backtick,
	 * unquoted leading `~`, glob, brace). The verdict layer only receives the raw
	 * string (four quoting forms are byte-identical there), so the flag is
	 * computed in the lexer and carried through. */
	verbatim: boolean;
}

/** Block rule identifiers, mirroring read-scope's rule tokens. `allow-unknown`
 * is the non-blocking token for a target that is not statically determinable
 * (see `checkBashWriteScopeTarget`), not a block reason. */
export type BashWriteScopeRule = "deny" | "scope" | "write-scope" | "allow-unknown";

/** Enforcement config for one writeless+shell worker. */
export interface BashWriteScopeConfig {
	/** Worker cwd = project root (launcher guarantee). */
	projectRoot: string;
	/** Own task dir (`.agenticdoc/<key>/workers/<taskKey>`), absolute. */
	taskDir: string;
	/** Own key dir (`.agenticdoc/<key>`), absolute. */
	keyDir: string;
	/** TRUE `.agenticdoc` root (`.agenticdoc`), absolute. */
	trueRoot: string;
	/** `write_scope:` entries (project-root relative): undefined = header
	 * absent (the default surface), [] = present-but-blank (fail-closed). */
	writeScope: string[] | undefined;
}

/** Verdict for one extracted target. */
export interface BashWriteScopeVerdict {
	allowed: boolean;
	/** Rule that fired on a block. */
	rule?: BashWriteScopeRule;
	/** Short machine token for the trace line (e.g. `denied:pm-state.md`). */
	detail?: string;
	/** Human block reason (carries the allowed dirs on every rule). */
	reason?: string;
	/** The raw target the verdict was produced for. */
	target?: string;
	/** Set on an `allow-unknown` verdict whose basename still names a deny-list
	 * artifact (`pm-state.md`, `_workers*`) — the residual-risk marker (AC-007). */
	risk?: "deny-basename";
}

interface ShellToken {
	text: string;
	/** True for an unquoted control-operator token (`>`, `>>`, `|`, ...). */
	operator: boolean;
	/** False once the word contains a live expansion (see the tokenizer). */
	verbatim: boolean;
}

/** Live shell-expansion characters. Deliberately NOT `GLOB_MAGIC_RE`: that set
 * matches `write_scope:` entries, this one decides `verbatim` on command words. */
const LIVE_EXPANSION_CHARS = new Set(["$", "`", "*", "?", "[", "{"]);

/** Split a shell command into quote-aware tokens; control operators become
 * their own tokens, so `echo "a > b"` never yields a redirect. */
export function tokenizeShellCommand(command: string): ShellToken[] {
	const tokens: ShellToken[] = [];
	let word = "";
	let hasWord = false;
	let inert = true;
	const append = (ch: string, live: boolean): void => {
		word += ch;
		if (live && (LIVE_EXPANSION_CHARS.has(ch) || (ch === "~" && word.length === 1))) inert = false;
	};
	const flush = (): void => {
		if (hasWord) {
			tokens.push({ text: word, operator: false, verbatim: inert });
			word = "";
			hasWord = false;
			inert = true;
		}
	};
	let i = 0;
	while (i < command.length) {
		const ch = command[i];
		if (ch === "'" || ch === '"') {
			hasWord = true;
			i++;
			while (i < command.length && command[i] !== ch) {
				if (ch === '"' && command[i] === "\\" && i + 1 < command.length) {
					// POSIX: only `$`, a backtick, `"` and `\` are escaped in double quotes (P-1).
					i = appendDoubleQuoteEscape(command, i, append);
				} else {
					// Single quotes inert everything; double quotes only inert an
					// escaped character (`$`/backtick/glob stay live inside `"`).
					append(command[i], ch === '"');
				}
				i++;
			}
			i++; // closing quote (or end of input)
			continue;
		}
		if (ch === "\\" && i + 1 < command.length) {
			hasWord = true;
			append(command[i + 1], false);
			i += 2;
			continue;
		}
		if (ch === " " || ch === "\t") {
			flush();
			i++;
			continue;
		}
		if (ch === "\n") {
			flush();
			tokens.push(markLineBreak({ text: ";", operator: true, verbatim: true }));
			i++;
			continue;
		}
		if (ch === ">" || ch === "<" || ch === "|" || ch === ";" || ch === "&" || ch === "(" || ch === ")") {
			flush();
			let op = ch;
			while (i + 1 < command.length && (command[i + 1] === ch || (command[i + 1] === "-" && op === "<<"))) {
				op += command[i + 1]; // `ch` repeats, but `<<-` absorbs its `-`
				i++;
			}
			tokens.push({ text: op, operator: true, verbatim: true });
			i++;
			continue;
		}
		hasWord = true;
		append(ch, true);
		i++;
	}
	flush();
	return tokens;
}

/** Wrapper commands whose following word is still a command position.
 * Byte-frozen: expanded (never replaced) by `COMMAND_WRAPPERS` below. */
const SHELL_WRAPPER_COMMANDS = new Set(["sudo", "env", "command", "nohup", "time", "nice", "stdbuf", "xargs"]);

/** Command-position wrappers: skip their known flags, the next word is the command. */
const COMMAND_WRAPPERS = new Set([...SHELL_WRAPPER_COMMANDS, "doas", "timeout", "setsid"]);
/** Wrappers whose payload is shell source (re-tokenized and scanned again). */
const SHELL_SCRIPT_WRAPPERS = new Set(["bash", "sh", "zsh", "dash", "ksh"]);
const CMD_SCRIPT_WRAPPERS = new Set(["cmd"]);
const PS_SCRIPT_WRAPPERS = new Set(["powershell", "pwsh"]);
/** Unwrap recursion budget; a deeper payload is left undecided (fails open). */
const MAX_UNWRAP_DEPTH = 3;

/** Wrapper flags that consume one value. Unlisted flags are arity 0, which can
 * only lose coverage — never introduce a false block. */
const WRAPPER_VALUE_FLAGS: Record<string, Set<string>> = {
	sudo: new Set([
		"-u",
		"--user",
		"-g",
		"--group",
		"-p",
		"--prompt",
		"-C",
		"--close-from",
		"-h",
		"--host",
		"-r",
		"--role",
		"-t",
		"--type",
		"-T",
		"--command-timeout",
		"-U",
		"--other-user",
		"-R",
		"--chroot",
		"-D",
		"--chdir",
	]),
	doas: new Set(["-u", "-C"]),
	env: new Set(["-u", "--unset", "-C", "--chdir", "-S", "--split-string"]),
	nice: new Set(["-n", "--adjustment"]),
	stdbuf: new Set(["-i", "--input", "-o", "--output", "-e", "--error"]),
	timeout: new Set(["-k", "--kill-after", "-s", "--signal"]),
	xargs: new Set([
		"-n",
		"--max-args",
		"-I",
		"--replace",
		"-i",
		"-d",
		"--delimiter",
		"-E",
		"--eof",
		"-P",
		"--max-procs",
		"-s",
		"--max-chars",
		"-L",
		"--max-lines",
		"-a",
		"--arg-file",
	]),
	time: new Set(["-o", "--output", "-f", "--format"]),
};

/** Operand-position flags that consume one value (arity-aware `positionals`). */
const OPERAND_VALUE_FLAGS: Record<string, Set<string>> = {
	truncate: new Set(["-s", "--size", "-r", "--reference"]),
	install: new Set(["-m", "--mode", "-o", "--owner", "-g", "--group", "-t", "--target-directory", "-S", "--suffix"]),
	cp: new Set(["-t", "--target-directory", "-S", "--suffix"]),
	mv: new Set(["-t", "--target-directory", "-S", "--suffix"]),
	ln: new Set(["-t", "--target-directory", "-S", "--suffix"]),
	rsync: new Set([
		"-e",
		"--rsh",
		"--exclude",
		"--include",
		"--files-from",
		"--chown",
		"--chmod",
		"--bwlimit",
		"--port",
		"--rsync-path",
		"--filter",
		"--exclude-from",
		"--include-from",
		"--log-file",
		"-T",
		"--temp-dir",
		"-M",
		"--remote-option",
		"--out-format",
		"--suffix",
	]),
	sed: new Set(["-e", "--expression"]),
	perl: new Set(["-e", "-E"]),
};

function flagBase(value: string): string {
	if (value.includes("=")) return value.slice(0, value.indexOf("="));
	if (value.startsWith("--")) return value;
	return `-${value[1] ?? ""}`;
}

function flagHasAttachedValue(value: string): boolean {
	return value.includes("=") || (value.startsWith("-") && !value.startsWith("--") && value.length > 2);
}

/** Word tokens from `start` up to (not including) the next operator. */
function shellOperands(tokens: ShellToken[], start: number): ShellToken[] {
	const values: ShellToken[] = [];
	for (let i = start; i < tokens.length; i++) {
		if (tokens[i].operator) break;
		values.push(tokens[i]);
	}
	return values;
}

/** Positional tokens after arity-aware flag skipping; a bare `--` stops flag
 * interpretation so `rm -- -weird.txt` keeps its operand. */
function positionals(operandTokens: ShellToken[], commandName: string): ShellToken[] {
	const values: ShellToken[] = [];
	const valueFlags = OPERAND_VALUE_FLAGS[commandName];
	let flagsDone = false;
	for (let i = 0; i < operandTokens.length; i++) {
		const token = operandTokens[i];
		const value = token.text;
		if (!flagsDone) {
			if (value === "--") {
				flagsDone = true;
				continue;
			}
			if (value.startsWith("-") && value !== "-") {
				if (valueFlags?.has(flagBase(value)) === true && !flagHasAttachedValue(value)) i++;
				continue;
			}
		}
		values.push(token);
	}
	return values;
}

/** The `-t`/`--target-directory` value, with or without an embedded `=`. */
function targetDirectory(operandTokens: ShellToken[], flags: string[]): ShellToken | null {
	for (let i = 0; i < operandTokens.length; i++) {
		const value = operandTokens[i].text;
		if (flags.includes(value)) return operandTokens[i + 1] ?? null;
		for (const flag of flags) {
			if (flag.startsWith("--") && value.startsWith(`${flag}=`)) {
				const text = value.slice(flag.length + 1);
				return text === "" ? null : { text, operator: false, verbatim: operandTokens[i].verbatim };
			}
		}
	}
	return null;
}

/** Targets that are not repository writes (null devices / std streams). */
const NULL_WRITE_TARGETS = new Set([
	"/dev/null",
	"/dev/stdout",
	"/dev/stderr",
	"/dev/fd/1",
	"/dev/fd/2",
	"nul",
	"/nul",
	"$null", // PowerShell null stream: not a repository write, no audit noise
]);

/** PowerShell write cmdlets and the flags that carry an explicit path. */
const POWERSHELL_WRITE_COMMANDS = new Set([
	"set-content",
	"add-content",
	"clear-content",
	"out-file",
	"new-item",
	"remove-item",
]);
const POWERSHELL_PATH_FLAGS = new Set(["-path", "-literalpath", "-filepath", "-destination"]);

/** Inline python/node write call sites; the LAST capture group is the path.
 * The bare `write_(text|bytes)` form is intentionally absent: it captures the
 * written CONTENT, not the path (historical false-positive `write_text('x')`). */
const INLINE_WRITE_PATTERNS: RegExp[] = [
	/\bopen\s*\(\s*(?:f)?(['"])([^'"]+)\1\s*,\s*(?:mode\s*=\s*)?['"][wax+]/i,
	/\bos\.(?:remove|unlink|rmdir|mkdir|makedirs|rename)\s*\(\s*(['"])([^'"]+)\1/i,
	/\bshutil\.rmtree\s*\(\s*(['"])([^'"]+)\1/i,
	/\bshutil\.(?:copy|copyfile|move)\s*\(\s*(['"])([^'"]+)\1\s*,\s*(['"])([^'"]+)\3/i,
	/\bPath\s*\(\s*(['"])([^'"]+)\1\s*\)\s*\.\s*(?:write_text|write_bytes|touch|mkdir|unlink|rename|replace)/i,
	/\b(?:fs\.)?(?:writeFileSync|writeFile|appendFileSync|appendFile|unlinkSync|unlink|rmSync|rm|rmdirSync|rmdir|mkdirSync|mkdir|createWriteStream)\s*\(\s*(['"])([^'"]+)\1/i,
	/\b(?:fs\.)?renameSync\s*\(\s*(['"])([^'"]+)\1\s*,\s*(['"])([^'"]+)\3/i,
];

/** Perl/Ruby inline write call sites (literal path is the last capture). */
const PERL_INLINE_PATTERNS: RegExp[] = [
	/\bopen\s*\(\s*(?:[A-Za-z_]\w*\s*,\s*)?(['"])[^'"]*\1\s*,\s*(['"])([^'"]+)\2/,
	/\bopen\s*\(\s*(?:[A-Za-z_]\w*\s*,\s*)?(['"])[>+]{1,2}([^'"]+)\1/,
];
const RUBY_INLINE_PATTERNS: RegExp[] = [
	/\bFile\s*\.\s*(?:write|binwrite|open)\s*\(\s*(['"])([^'"]+)\1/,
	/\bIO\s*\.\s*(?:write|binwrite)\s*\(\s*(['"])([^'"]+)\1/,
];
/** Inline process-spawn call sites; the captured literal is a shell payload. */
const INLINE_EXEC_PATTERNS: RegExp[] = [
	/\bos\s*\.\s*(?:system|popen)\s*\(\s*(['"])([^'"]+)\1/,
	/\bsubprocess\s*\.\s*(?:run|call|check_call|check_output|Popen)\s*\(\s*(['"])([^'"]+)\1/,
	/\b(?:execSync|exec|execFileSync|spawnSync|spawn)\s*\(\s*(['"])([^'"]+)\1/,
];

function matchInline(patterns: RegExp[], script: string): string[] {
	const values: string[] = [];
	for (const pattern of patterns) {
		const match = pattern.exec(script);
		if (match === null) continue;
		const value = match[match.length - 1];
		if (typeof value === "string" && value.length > 0) values.push(value);
	}
	return values;
}

/** Which flag of `commandName` introduces an inline script payload. */
function scriptPayloadFlag(commandName: string, value: string): boolean {
	if (SHELL_SCRIPT_WRAPPERS.has(commandName)) {
		return value.startsWith("-") && !value.startsWith("--") && value.includes("c");
	}
	if (CMD_SCRIPT_WRAPPERS.has(commandName)) {
		return value === "/c" || value === "/C" || value === "/k" || value === "/K";
	}
	if (PS_SCRIPT_WRAPPERS.has(commandName)) {
		const lower = value.toLowerCase();
		return lower === "-command" || lower === "-c" || lower === "-commandwithargs";
	}
	if (commandName === "perl") return /^-[A-Za-z]*[eE][A-Za-z]*$/.test(value);
	if (commandName === "ruby") return value === "-e" || value === "-E";
	if (commandName === "python" || commandName === "python3" || commandName === "py") return value === "-c";
	if (commandName === "node") return value === "-e" || value === "--eval" || value === "-p" || value === "--print";
	return false;
}

function scriptPayloadToken(operands: ShellToken[], commandName: string): ShellToken | null {
	for (let i = 0; i < operands.length; i++) {
		if (scriptPayloadFlag(commandName, operands[i].text)) return operands[i + 1] ?? null;
	}
	return null;
}

interface WrapperSkip {
	index: number;
	placeholders: string[];
}

/** Skip command-position wrappers and their flags; returns the inner command
 * index plus any `xargs` replacement placeholders. */
function skipWrapperPrefix(tokens: ShellToken[], start: number): WrapperSkip {
	let i = start;
	const placeholders: string[] = [];
	while (i < tokens.length && !tokens[i].operator) {
		const name = commandBasename(tokens[i].text);
		if (!COMMAND_WRAPPERS.has(name)) break;
		i++;
		while (i < tokens.length && !tokens[i].operator) {
			const value = tokens[i].text;
			if (value === "--") {
				i++;
				continue;
			}
			if (!value.startsWith("-")) {
				if (name === "timeout") {
					// `timeout` takes exactly one leading positional (DURATION) before
					// the wrapped command; consume it and stop skipping.
					i++;
					break;
				}
				if (name === "env" && /^[A-Za-z_][A-Za-z0-9_]*=/.test(value)) {
					i++;
					continue;
				}
				break;
			}
			if (name === "xargs") {
				const base = flagBase(value);
				if (base === "--replace" || base === "-I" || base === "-i") {
					if (flagHasAttachedValue(value)) {
						const attached = value.includes("=") ? value.slice(value.indexOf("=") + 1) : value.slice(2);
						if (attached !== "") placeholders.push(attached);
						i++;
						continue;
					}
					if (base === "-i") {
						placeholders.push("{}");
						i++;
						continue;
					}
					const next = tokens[i + 1];
					if (next !== undefined && !next.operator) {
						placeholders.push(next.text);
						i += 2;
						continue;
					}
					i++;
					continue;
				}
			}
			const arity = WRAPPER_VALUE_FLAGS[name]?.has(flagBase(value)) === true ? 1 : 0;
			i += arity === 1 && !flagHasAttachedValue(value) ? 2 : 1;
		}
	}
	return { index: i, placeholders };
}

type AddCandidate = (source: ShellToken | string, pattern: string, verbatimOverride?: boolean) => void;

/** Recursive extractor over already-tokenized words. `opaqueTokens` are runtime
 * placeholders (`{}`, `xargs -I R`): a target containing one is not statically
 * determinable and is marked non-verbatim (fail-open). */
function extractFromTokens(
	tokens: ShellToken[],
	depth: number,
	out: BashWriteCandidate[],
	opaqueTokens: Set<string>,
): void {
	const add: AddCandidate = (source, pattern, verbatimOverride) => {
		const value = (typeof source === "string" ? source : source.text).trim();
		if (value === "" || NULL_WRITE_TARGETS.has(value.toLowerCase())) return;
		let verbatim = verbatimOverride ?? (typeof source === "string" ? true : source.verbatim);
		if (verbatim) {
			for (const opaque of opaqueTokens) {
				if (opaque !== "" && value.includes(opaque)) {
					verbatim = false;
					break;
				}
			}
		}
		out.push({ target: value, pattern, verbatim });
	};

	// Comparison contexts (`[[ a > b ]]`, `(( a > b ))`, `$(( a > b ))`): the
	// `>`/`<` there compare, they do not redirect (F-2). Track the depth so a real
	// redirect after the closing bracket still registers.
	let comparisonDepth = 0;
	for (let i = 0, list = dropHeredocBodies(tokens); i < list.length; i++) {
		const token = list[i];
		if (token.operator) {
			if (token.text === "((") {
				comparisonDepth += 1;
				continue;
			}
			if (token.text === "))") {
				if (comparisonDepth > 0) comparisonDepth -= 1;
				continue;
			}
			if (token.text === ">" || token.text === ">>") {
				if (comparisonDepth > 0) continue;
				const next = list[i + 1];
				if (next === undefined) continue;
				if (!next.operator) {
					add(next, "redirect");
					continue;
				}
				const after = list[i + 2];
				if (after !== undefined && !after.operator) {
					if (next.text === "|") add(after, "redirect-clobber");
					else if (next.text === "&" && !/^\d+$/.test(after.text) && after.text !== "-") {
						add(after, "redirect-fd-target");
					}
				}
			}
			continue;
		}
		if (token.text === "[[") {
			comparisonDepth += 1;
			continue;
		}
		if (token.text === "]]") {
			if (comparisonDepth > 0) comparisonDepth -= 1;
			continue;
		}
		const previous = list[i - 1];
		if (previous !== undefined && !previous.operator) continue;
		extractCommand(list, i, depth, out, add, opaqueTokens);
	}
}

/** Extract the write targets of one command found at `start` (which may be a
 * command-position wrapper chain). */
function extractCommand(
	tokens: ShellToken[],
	start: number,
	depth: number,
	out: BashWriteCandidate[],
	add: AddCandidate,
	opaqueTokens: Set<string>,
): void {
	const skip = skipWrapperPrefix(tokens, start);
	const commandIndex = skip.index;
	if (commandIndex >= tokens.length) return;
	const commandToken = tokens[commandIndex];
	if (commandToken.operator) return;
	const commandName = commandBasename(commandToken.text);
	const operandTokens = shellOperands(tokens, commandIndex + 1);
	const childOpaque = new Set(opaqueTokens);
	for (const placeholder of skip.placeholders) if (placeholder !== "") childOpaque.add(placeholder);
	const recurseShell = (payload: string): void => {
		if (depth >= MAX_UNWRAP_DEPTH) return;
		extractFromTokens(tokenizeShellCommand(payload), depth + 1, out, childOpaque);
	};
	const inlineTargets = (patterns: RegExp[], script: ShellToken): void => {
		for (const value of matchInline(patterns, script.text)) {
			add(value, "inline-script", script.verbatim && !/[$`]/.test(value));
		}
	};

	switch (commandName) {
		case "bash":
		case "sh":
		case "zsh":
		case "dash":
		case "ksh":
		case "cmd":
		case "powershell":
		case "pwsh": {
			const payload = scriptPayloadToken(operandTokens, commandName);
			if (payload !== null) recurseShell(payload.text);
			break;
		}
		case "perl": {
			let suffix: string | undefined;
			let suffixVerbatim = true;
			const files: ShellToken[] = [];
			for (let k = 0; k < operandTokens.length; k++) {
				const token = operandTokens[k];
				const value = token.text;
				if (value === "--") {
					for (let m = k + 1; m < operandTokens.length; m++) files.push(operandTokens[m]);
					break;
				}
				if (value === "-i" || value === "--in-place") {
					suffix = "";
					continue;
				}
				if (value.startsWith("-i") && value.length > 2 && !value.startsWith("--")) {
					suffix = value.slice(2);
					suffixVerbatim = token.verbatim;
					continue;
				}
				if (value.startsWith("--in-place=")) {
					suffix = value.slice("--in-place=".length);
					suffixVerbatim = token.verbatim;
					continue;
				}
				if (scriptPayloadFlag("perl", value)) {
					const payload = operandTokens[k + 1];
					if (payload !== undefined) inlineTargets(PERL_INLINE_PATTERNS, payload);
					k++;
					continue;
				}
				if (value.startsWith("-")) continue;
				files.push(token);
			}
			if (suffix !== undefined) {
				for (const file of files) {
					add(file, "perl -i");
					if (suffix !== "") add(`${file.text}${suffix}`, "perl -i", file.verbatim && suffixVerbatim);
				}
			}
			break;
		}
		case "ruby": {
			const payload = scriptPayloadToken(operandTokens, "ruby");
			if (payload !== null) inlineTargets(RUBY_INLINE_PATTERNS, payload);
			break;
		}
		case "python":
		case "python3":
		case "py":
		case "node": {
			const payload = scriptPayloadToken(operandTokens, commandName);
			if (payload !== null) {
				inlineTargets(INLINE_WRITE_PATTERNS, payload);
				for (const captured of matchInline(INLINE_EXEC_PATTERNS, payload.text)) recurseShell(captured);
			}
			break;
		}
		case "tee": {
			for (const token of operandTokens) if (!token.text.startsWith("-")) add(token, "tee");
			break;
		}
		case "cp":
		case "mv": {
			const dir = targetDirectory(operandTokens, ["-t", "--target-directory"]);
			if (dir !== null) {
				add(dir, commandName);
				break;
			}
			const values = positionals(operandTokens, commandName);
			const destination = values[values.length - 1];
			if (destination !== undefined) add(destination, commandName);
			break;
		}
		case "rm":
		case "mkdir":
		case "touch":
		case "truncate": {
			for (const token of positionals(operandTokens, commandName)) add(token, commandName);
			break;
		}
		case "install": {
			const dir = targetDirectory(operandTokens, ["-t", "--target-directory"]);
			const values = positionals(operandTokens, "install");
			if (dir !== null) {
				add(dir, "install -t");
				for (const token of values) add(token, "install");
			} else if (values.length >= 2) {
				add(values[values.length - 1], "install");
			}
			break;
		}
		case "ln": {
			const dir = targetDirectory(operandTokens, ["-t", "--target-directory"]);
			if (dir !== null) {
				add(dir, "ln -t");
				break;
			}
			const values = positionals(operandTokens, "ln");
			if (values.length >= 2) add(values[values.length - 1], "ln");
			break;
		}
		case "rsync": {
			const values = positionals(operandTokens, "rsync");
			if (values.length >= 2) add(values[values.length - 1], "rsync");
			break;
		}
		case "dd": {
			for (const token of operandTokens) {
				const match = /^of=(.*)$/.exec(token.text);
				if (match !== null && match[1] !== "") add(match[1], "dd of=", token.verbatim);
			}
			break;
		}
		case "tar": {
			let create = false;
			let extract = false;
			// Keep the whole token (not only its text) so the target's live-expansion
			// flag survives: `tar -czf $OUT.tar` is not statically determinable and
			// must land in the allow-unknown tier, not be denied as a literal (F-1).
			let archive: ShellToken | undefined;
			let directory: ShellToken | undefined;
			for (let k = 0; k < operandTokens.length; k++) {
				const token = operandTokens[k];
				const value = token.text;
				if (value === "-C" || value === "--directory") {
					directory = operandTokens[k + 1];
					k++;
					continue;
				}
				if (value.startsWith("--directory=")) {
					directory = { text: value.slice("--directory=".length), operator: false, verbatim: token.verbatim };
					continue;
				}
				if (value === "-f" || value === "--file") {
					archive = operandTokens[k + 1];
					k++;
					continue;
				}
				if (value.startsWith("--file=")) {
					archive = { text: value.slice("--file=".length), operator: false, verbatim: token.verbatim };
					continue;
				}
				if (value.startsWith("-") && !value.startsWith("--")) {
					const letters = value.slice(1);
					if (letters.includes("c")) create = true;
					if (letters.includes("x")) extract = true;
					if (letters.includes("f")) {
						archive = operandTokens[k + 1];
						k++;
					}
				}
			}
			if (extract && directory !== undefined) add(directory, "tar -C");
			else if (extract) add(".", "tar -x");
			else if (create && archive !== undefined) add(archive, "tar -c");
			break;
		}
		case "sed": {
			const inPlace = operandTokens.some(
				(token) =>
					token.text === "-i" ||
					token.text === "--in-place" ||
					token.text.startsWith("--in-place=") ||
					(token.text.startsWith("-i") && token.text.length > 2 && !token.text.startsWith("--")),
			);
			if (!inPlace) break;
			let suffix = "";
			let suffixVerbatim = true;
			for (const token of operandTokens) {
				if (token.text.startsWith("--in-place=")) {
					suffix = token.text.slice("--in-place=".length);
					suffixVerbatim = token.verbatim;
				} else if (token.text.startsWith("-i") && token.text.length > 2 && !token.text.startsWith("--")) {
					suffix = token.text.slice(2);
					suffixVerbatim = token.verbatim;
				}
			}
			const values = positionals(operandTokens, "sed");
			for (const token of values.slice(1)) {
				add(token, "sed -i");
				if (suffix !== "") add(`${token.text}${suffix}`, "sed -i", token.verbatim && suffixVerbatim);
			}
			break;
		}
		case "find": {
			const roots: ShellToken[] = [];
			for (const token of operandTokens) {
				if (token.text.startsWith("-") || token.text === "!") break;
				roots.push(token);
			}
			if (roots.length === 0) roots.push({ text: ".", operator: false, verbatim: true });
			let remove = false;
			for (let k = 0; k < operandTokens.length; k++) {
				const value = operandTokens[k].text;
				if (value === "-delete") remove = true;
				if (value === "-exec" || value === "-execdir") {
					const sub: ShellToken[] = [];
					let m = k + 1;
					while (m < operandTokens.length && operandTokens[m].text !== ";" && operandTokens[m].text !== "+") {
						sub.push(operandTokens[m]);
						m++;
					}
					if (depth < MAX_UNWRAP_DEPTH) extractFromTokens(sub, depth + 1, out, childOpaque);
					k = m;
				}
			}
			if (remove) for (const root of roots) add(root, "find -delete");
			break;
		}
		case "git": {
			const sub = operandTokens[0]?.text.toLowerCase();
			if (sub !== "checkout" && sub !== "apply" && sub !== "clean" && sub !== "restore") break;
			const paths = positionals(operandTokens.slice(1), "git");
			if (paths.length === 0) add(".", `git ${sub}`);
			else for (const token of paths) add(token, `git ${sub}`);
			break;
		}
		case "curl": {
			for (let k = 0; k < operandTokens.length; k++) {
				const value = operandTokens[k].text;
				if (value === "-o" || value === "--output") {
					const next = operandTokens[k + 1];
					if (next !== undefined) add(next, "curl -o");
				} else if (value.startsWith("--output=")) {
					add(value.slice("--output=".length), "curl -o", operandTokens[k].verbatim);
				}
			}
			break;
		}
		case "wget": {
			for (let k = 0; k < operandTokens.length; k++) {
				const value = operandTokens[k].text;
				if (value === "-O" || value === "--output-document") {
					const next = operandTokens[k + 1];
					if (next !== undefined) add(next, "wget -O");
				} else if (value.startsWith("--output-document=")) {
					add(value.slice("--output-document=".length), "wget -O", operandTokens[k].verbatim);
				}
			}
			break;
		}
		default: {
			if (!POWERSHELL_WRITE_COMMANDS.has(commandName)) break;
			for (let k = 0; k < operandTokens.length; k++) {
				const value = operandTokens[k].text;
				if (value.startsWith("-")) {
					if (POWERSHELL_PATH_FLAGS.has(value.toLowerCase()) && operandTokens[k + 1] !== undefined) {
						add(operandTokens[k + 1], `${commandName} -Path`);
					}
					continue;
				}
				const previous = operandTokens[k - 1];
				if (previous?.text.startsWith("-")) continue;
				add(operandTokens[k], commandName);
			}
			break;
		}
	}
}

/** Extract the KNOWN write targets of a bash command. An empty result means
 * "not a recognized write" — the caller must allow it (P1, DD-03). */
export function extractBashWriteCandidates(command: string): BashWriteCandidate[] {
	const out: BashWriteCandidate[] = [];
	extractFromTokens(tokenizeShellCommand(command), 0, out, new Set(["{}"]));
	return out;
}

function samePath(a: string, b: string): boolean {
	return isSameOrUnder(a, b) && isSameOrUnder(b, a);
}

const GLOB_MAGIC_RE = /[*?[\]{}]/;

/** Absolute deny reason for a resolved target, or null. The deny list is
 * checked first and can never be widened by a `write_scope:` header. */
function bashWriteDenyReason(config: BashWriteScopeConfig, target: string): string | null {
	const workersDir = path.join(config.keyDir, "workers");
	if (samePath(target, path.join(config.keyDir, "pm-state.md"))) return "pm-state.md";
	if (isSameOrUnder(workersDir, target)) {
		const firstSegment = path.relative(workersDir, target).split(/[\\/]/)[0] ?? "";
		if (firstSegment.startsWith("_workers")) return "workers/_workers*";
	}
	if (samePath(target, path.join(config.trueRoot, "_index.parallel"))) return "_index.parallel";
	if (isSameOrUnder(config.trueRoot, target) && !isSameOrUnder(config.keyDir, target)) {
		return "other key dir / .agenticdoc root";
	}
	if (isSameOrUnder(path.join(config.projectRoot, "packages"), target)) return "packages/**";
	if (isSameOrUnder(path.join(config.projectRoot, ".git"), target)) return ".git/**";
	return null;
}

function matchesWriteScopeEntry(config: BashWriteScopeConfig, entry: string, absoluteTarget: string): boolean {
	const normalized = entry.trim();
	if (normalized === "") return false;
	if (GLOB_MAGIC_RE.test(normalized)) {
		const relative = path.relative(config.projectRoot, absoluteTarget).replaceAll("\\", "/");
		const forward = absoluteTarget.replaceAll("\\", "/");
		const glob = normalized.replaceAll("\\", "/");
		if (minimatch(relative, glob) || minimatch(forward, glob)) return true;
		if (glob.endsWith("/**")) {
			const stripped = glob.slice(0, -3);
			if (stripped !== "" && (minimatch(relative, stripped) || minimatch(forward, stripped))) return true;
		}
		return false;
	}
	return isSameOrUnder(normalizeForCompare(config.projectRoot, normalized), absoluteTarget);
}

/** The bash write-surface verdict for one extracted target: a non-verbatim
 * target is not statically determinable (`allow-unknown`, fail-open); otherwise
 * the deny list comes first (absolute priority), then the default surface (own
 * taskDir + `<key>/evidence`), then the task's `write_scope:` intersection when
 * the header is present. */
export function checkBashWriteScopeTarget(
	config: BashWriteScopeConfig,
	rawTarget: string,
	verbatim: boolean,
): BashWriteScopeVerdict {
	if (!verbatim) {
		const basename = rawTarget.split(/[\\/]/).pop() ?? "";
		const risk = basename === "pm-state.md" || basename.startsWith("_workers") ? "deny-basename" : undefined;
		return {
			allowed: true,
			rule: "allow-unknown",
			detail: "target-not-statically-determinable",
			target: rawTarget,
			risk,
		};
	}
	const target = normalizeForCompare(config.projectRoot, rawTarget);
	const evidenceDir = path.join(config.keyDir, "evidence");
	const allowedLabel = `${config.taskDir} or ${evidenceDir}`;
	const denied = bashWriteDenyReason(config, target);
	if (denied !== null) {
		return {
			allowed: false,
			rule: "deny",
			detail: `denied:${denied}`,
			target: rawTarget,
			reason:
				`write-scope: blocked bash write to ${rawTarget}: ${denied} is on the denied write list ` +
				`[rule=deny]; allowed: ${allowedLabel}`,
		};
	}
	if (!isSameOrUnder(config.taskDir, target) && !isSameOrUnder(evidenceDir, target)) {
		return {
			allowed: false,
			rule: "scope",
			detail: "outside-allowed-surface",
			target: rawTarget,
			reason:
				`write-scope: blocked bash write to ${rawTarget}: outside the worker write surface ` +
				`[rule=scope]; allowed: ${allowedLabel}`,
		};
	}
	if (
		config.writeScope !== undefined &&
		!config.writeScope.some((entry) => matchesWriteScopeEntry(config, entry, target))
	) {
		return {
			allowed: false,
			rule: "write-scope",
			detail: "outside-declared-write-scope",
			target: rawTarget,
			reason:
				`write-scope: blocked bash write to ${rawTarget}: outside the task's declared write_scope ` +
				`[rule=write-scope]; allowed: ${allowedLabel}`,
		};
	}
	return { allowed: true, target: rawTarget };
}

/** One judged bash write, as accumulated for the trace audit line. */
interface BashWriteScopeRejection {
	ts: string;
	/** The negated `verdict.allowed`: the ONLY source of the audit `blocked=`
	 * field (never derived from `rule`, AC-007/T-03). */
	blocked: boolean;
	rule: BashWriteScopeRule;
	detail: string;
	/** Set on the allow-unknown residual-risk rows (F1–F3). */
	risk?: "deny-basename";
	target: string;
	pattern: string;
	command: string;
}

/** The three write-scope outcome counters (AC-007/T-03): `allowUnknown` is the
 * F1–F3 contract-cost tier, `allowDetermined` the decided allow, `deny` the
 * blocked rows. */
interface WriteScopeCounts {
	allowDetermined: number;
	deny: number;
	allowUnknown: number;
}

/** Append one `[WRITE_SCOPE] ... write-scope ...` audit line to trace.log.
 * Contract (AC-005b/AC-007): the line carries the `write-scope` token, the
 * `blocked=<bool>` field, the optional `risk=<token>` residual marker and the
 * blocked command summary. Pure-read/unclassified commands never reach here (no
 * audit noise — the P1 miss surface is covered by the existing full command
 * trace). */
function appendBashWriteScopeTraceLine(taskKey: string, agenticdocRoot: string, r: BashWriteScopeRejection): void {
	try {
		const dir = path.resolve(agenticdocRoot, taskKey);
		fs.mkdirSync(dir, { recursive: true });
		const summary = r.command.replace(/\s+/g, " ").trim().slice(0, 200);
		const risk = r.risk === undefined ? "" : `risk=${r.risk} `;
		fs.appendFileSync(
			path.join(dir, "trace.log"),
			`[WRITE_SCOPE] ${r.ts} write-scope blocked=${String(r.blocked)} ${risk}rule=${r.rule} detail=${r.detail} ` +
				`pattern=${r.pattern} target=${r.target} cmd=${summary}\n`,
			"utf8",
		);
	} catch {
		// Diagnostic append — a failure must never break the block itself
	}
}

/** Append one machine `[WRITE_SCOPE_SUMMARY]` counter line for a guarded run
 * (AC-007/T-03). Its `allow-unknown=` count and the number of
 * `blocked=false rule=allow-unknown` audit rows are the two independent sources
 * of the equality criterion `allow_unknown_audited == allow_unknown_count`.
 * Best-effort like the audit line: a diagnostic append failure must never break
 * the settle path. */
function appendWriteScopeSummary(taskKey: string, agenticdocRoot: string, counts: WriteScopeCounts): void {
	try {
		const dir = path.resolve(agenticdocRoot, taskKey);
		fs.mkdirSync(dir, { recursive: true });
		fs.appendFileSync(
			path.join(dir, "trace.log"),
			`[WRITE_SCOPE_SUMMARY] allow=${counts.allowDetermined} deny=${counts.deny} allow-unknown=${counts.allowUnknown}\n`,
			"utf8",
		);
	} catch {
		// Diagnostic append — a failure must never break the settle path
	}
}

// ── Idle-kill evidence (T-04/VC-004) ─────────────────────────────────────────

/** Structured evidence emitted before any idle kill (VC-004/AC-005). Every
 * field is part of the contract: which tool was in flight (or `none`), how long
 * it had been running, the threshold that produced the verdict, and the last
 * source that refreshed the activity clock. */
export interface IdleKillEvidence {
	/** In-flight tool name, or "none" when the worker was tool-idle. */
	toolInFlight: string;
	/** Seconds the in-flight tool has been running; null when none. */
	toolRunS: number | null;
	/** Seconds since the in-flight tool's last activity; null when none. */
	toolIdleS: number | null;
	/** Seconds since ANY worker activity (the raw idle clock). */
	silenceS: number;
	/** The threshold used for this verdict, in seconds. */
	thresholdS: number;
	/** Which clock produced the verdict. */
	thresholdKind: "idle" | "tool_idle";
	/** Last source that refreshed the activity clock. */
	lastActivity: string;
}

/** Append one machine `[IDLE_KILL]` line to trace.log. Returns false when the
 * line could not be written — the caller must then NOT kill ("no evidence ->
 * no kill"); the wall watchdog stays the outer bound, so a hung worker is
 * still reaped even if the evidence write keeps failing. */
export function appendIdleKillEvidence(taskKey: string, agenticdocRoot: string, evidence: IdleKillEvidence): boolean {
	try {
		const dir = path.resolve(agenticdocRoot, taskKey);
		fs.mkdirSync(dir, { recursive: true });
		const num = (value: number | null): string => (value === null ? "-" : String(value));
		const line =
			`[IDLE_KILL] ${new Date().toISOString()} tool_in_flight=${evidence.toolInFlight} ` +
			`tool_run_s=${num(evidence.toolRunS)} tool_idle_s=${num(evidence.toolIdleS)} ` +
			`silence_s=${evidence.silenceS} threshold_s=${evidence.thresholdS} ` +
			`threshold_kind=${evidence.thresholdKind} last_activity=${evidence.lastActivity}`;
		fs.appendFileSync(path.join(dir, "trace.log"), `${line}\n`, "utf8");
		return true;
	} catch {
		return false;
	}
}

// ── VC-014 worker-face emission (T-14) ───────────────────────────────────────
// `required = role.require OR phase.require` is a warning-only contract
// (AC-010): a required role/phase that produced no verifiable citation gets one
// `rag-required-missing` trace line plus a machine-readable output.md marker,
// and the task still settles done. The line itself comes from T-09's
// `researchDocEvidence` (the single mechanism T-10's audit shares) — never a
// second line builder here.

/** task.md `phase:` value, or the literal `unknown` — never a guess. */
export function evidencePhase(phase: string | undefined): string {
	return phase !== undefined && phase.length > 0 ? phase : "unknown";
}

const RAG_UNUSED_MARKER = "RAG 未生效：required but unused";

/** Append `line` once: a re-run/duplicate settle must not double the trace. */
function appendEvidenceOnce(taskDir: string, line: string): void {
	try {
		const tracePath = path.join(path.resolve(taskDir), "trace.log");
		let existing = "";
		try {
			existing = fs.readFileSync(tracePath, "utf8");
		} catch {
			// No trace yet — nothing to dedupe against.
		}
		if (existing.includes(line)) return;
	} catch {
		// Fall through to the append; the writer handles a bad dir best-effort.
	}
	appendEvidence(taskDir, line);
}

/** Append the `## RAG` marker to output.md once. output.md is rewritten on
 * every exit path, so a re-settle naturally re-adds the marker exactly once. */
function markOutputRagUnused(taskDir: string): void {
	try {
		const outputPath = path.join(path.resolve(taskDir), "output.md");
		if (!fs.existsSync(outputPath)) return;
		if (fs.readFileSync(outputPath, "utf8").includes(RAG_UNUSED_MARKER)) return;
		fs.appendFileSync(outputPath, `\n## RAG\n\n${RAG_UNUSED_MARKER}\n`, "utf8");
	} catch {
		// Best-effort at exit — the trace line is the machine gate.
	}
}

/** Server for the evidence line: role spec > phase spec > default_server
 * (mirror of mw_common._rag_resolve_defaults). */
function ragServerFor(config: RagRuntime["config"], role: string, phase: string): string {
	return config.roles[role]?.server ?? config.phases[phase]?.server ?? config.defaultServer ?? "";
}

export interface RagRequiredCheck {
	config: RagRuntime["config"];
	taskType: string;
	/** task.md `phase:` value (already normalized via `evidencePhase`). */
	phase: string;
	/** The worker's own deliverable text (final assistant reply). */
	outputText: string;
	/** Owner key dir (`.agenticdoc/<key>`) — the research-doc location. */
	keyDir: string;
	/** Worker task dir (trace.log / output.md live here). */
	taskDir: string;
}

/**
 * VC-014 (AC-010) worker face: for a *required* role/phase, emit the shared
 * `rag-required-missing` evidence line and mark output.md when no verifiable
 * citation was produced. Returns the emitted line, or null on a no-op (not
 * required, or a citation exists). Zero writes when not required.
 *
 * "Verifiable citation" mirrors T-10's audit: a parseable D-004 citation in
 * the worker's own deliverable, or — for the research role, whose citations
 * live in `<key>/rag/*.md` — a citation in that key's research doc. The
 * research-doc report's `ok` is the used-flag and the line is routed through
 * `researchDocEvidence`, so there is exactly one line builder.
 */
export function emitRagRequiredMissing(check: RagRequiredCheck): string | null {
	const role = roleForTaskType(check.taskType);
	if (!requiredFor(check.config, role, check.phase)) return null;
	const report = validateResearchDoc(check.keyDir);
	const used = scanCitations(check.outputText).length > 0 || (role === "research" && report.citations.length > 0);
	const line = researchDocEvidence(
		{ ...report, ok: used },
		role,
		check.phase,
		ragServerFor(check.config, role, check.phase),
	);
	if (line === null) return null;
	appendEvidenceOnce(check.taskDir, line);
	markOutputRagUnused(check.taskDir);
	return line;
}

// ── Main entry ───────────────────────────────────────────────────────────────

export async function workerModeActivate(pi: ExtensionAPI): Promise<void> {
	const taskPathEnv = process.env.PI_WORKER_TASK;
	if (!taskPathEnv) {
		return;
	}

	const taskPath = path.resolve(taskPathEnv);
	if (!fs.existsSync(taskPath)) {
		killTrackedDetachedChildren();
		process.exit(1);
	}

	const meta = parseTaskMd(taskPath);
	const startedAt = Date.now();
	const phaseTotal = meta.phases?.length ?? 0;

	// D-115: record this spawn before anything else — the process itself is
	// the observation unit (spawn count + pid liveness), even when the task
	// is refused right below.
	appendStartPidLine(meta.taskKey, meta.agenticdocRoot);

	// Product-carried run identity (D-022/D-023, AC-022): this process writes its
	// OWN run.json — `running` now, a terminal state on every exit path below.
	// That is what makes a finished task un-restartable even when its ledger row
	// is lost (IN-3 rebuilt 252 rows in one second and a re-run overwrote a
	// finished task's output.md at 11:45:40), and what forces more work on a
	// finished task to use a NEW task_key declaring `supersedes:`.
	// task.md is read once here and reused for the read-scope parent root below.
	const taskDir = path.dirname(taskPath);
	const taskContent = fs.readFileSync(taskPath, "utf8");

	// AC-005 observability: record the ignored body `type:` lines / BOM / GC-8
	// fallback before the fail-closed gate so a refused spawn is audited too.
	appendHeaderAudit(meta.taskKey, meta.agenticdocRoot, taskContent, meta.type);

	const runState: RunState = {
		schema: RUN_SCHEMA,
		task_key: meta.taskKey,
		run_id: newRunId(meta.taskKey),
		// `.agenticdoc/<key>/workers/<task>` (or `_scratch`): the owner key is the
		// directory that owns this task, never inferred from the task-key prefix.
		owner_key: path.basename(path.dirname(path.dirname(taskDir))),
		kind: meta.type,
		status: "running",
		started_at: new Date().toISOString(),
		supersedes: parseSupersedes(taskContent),
		artifacts: [],
		pid: process.pid,
		last_heartbeat_at: new Date().toISOString(),
	};
	writeRunState(taskDir, runState);

	// D-107 fail-closed gate: refuse the task before any agent turn, with the
	// reason in output.md (counts into the loop budget escalation on the
	// conductor side, AC-023).
	const refusal = dispatchRefusal(meta);
	if (refusal !== undefined) {
		appendError(meta.taskKey, meta.agenticdocRoot, refusal);
		markOutcome(1);
		writeOutput({
			taskKey: meta.taskKey,
			agenticdocRoot: meta.agenticdocRoot,
			exitCode: 1,
			summary: "Task refused at startup (fail-closed).",
			exitReason: refusal,
			runMarker: runMarker(runState),
		});
		// A refusal is a real terminal outcome: record it as such, so the row and
		// the product tell the same story and the task is never auto-restarted.
		finishRun("failed", 1);
		writeWorkerLogLine(`[worker] refused task=${meta.taskKey} type=${meta.type}: ${refusal}`);
		killTrackedDetachedChildren();
		process.exit(1);
	}

	// Read-scope enforcement (D-106/AC-009): active only when task.md carries
	// read_scope — otherwise zero interception (AC-012 red line). Rejections
	// accumulate in memory and are written to output.md on every exit path via
	// writeOutputGuarded (the output-writer remains the unified write-out point).
	// Partition extended-workspace union (mw-partition-parent-extended AC-002):
	// the profile block's Parent root joins the allowed scope — parent is a
	// directly developed extension of the workspace, not read-only context.
	// No-op for empty (fail-closed) / deny-only scopes and non-partition tasks.
	const readScopeConfig: ReadScopeConfig | undefined = applyParentRootUnion(
		readScopeConfigFromMeta(meta),
		parentRootFromTaskContent(taskContent),
	);
	const readScopeState: ReadScopeState = { allowedCalls: 0, bytesRead: 0 };
	const readScopeRejections: ReadScopeRejection[] = [];

	function writeOutputGuarded(opts: WriteOutputOpts): void {
		// The product write is this run's terminal moment, and the marker it carries
		// must state the outcome the same write records — so reflect it in memory
		// first (finishRun persists it right after, R15).
		markOutcome(opts.exitCode);
		writeOutput({ ...opts, runMarker: runMarker(runState) });
		appendReadScopeRejectionsSection(meta.taskKey, meta.agenticdocRoot, readScopeRejections);
	}

	/** The one place that maps an exit code to a terminal status (shared by the
	 * output.md marker and the persisted record). AC-006 adds the framework's
	 * no-product verdict: exit 2 = needs-clarification (not a crash), so the OS
	 * exit code, `[END] exit=`, run.json.status and the output.md marker all
	 * agree with `launcher._exit_to_status`. */
	function markOutcome(exitCode: number): RunStatus {
		runState.status = exitCode === 0 ? "done" : exitCode === 2 ? "needs-clarification" : "failed";
		return runState.status;
	}

	/** Terminal write for THIS run (AC-022/D-022). Every exit path lands here
	 * through `recordEnd`, a startup refusal, or the process-exit safety net.
	 * Best-effort by contract (R15): when the write fails it is noted in
	 * trace.log and the run still writes output.md. `artifacts` is re-collected
	 * here (the deliverables exist by now), never for a `lost` run — the Python
	 * launcher owns that single addition (D-023). */
	function finishRun(status: RunStatus, exit?: number): void {
		runState.status = status;
		runState.ended_at = new Date().toISOString();
		if (exit !== undefined) runState.exit = exit;
		runState.artifacts = collectArtifacts(taskDir);
		writeRunState(taskDir, runState);
	}

	// Task lifecycle start: trace.log gets a machine-parseable [START] anchor
	// (runtime origin for elapsed computation), worker.log a human status line.
	appendStart(meta.taskKey, meta.agenticdocRoot, meta.type, phaseTotal);
	// AC-010/T-12: consume the C2 contract markers read back by `parseTaskMd`.
	// The producer is PM-side; a malformed pair here means renderer drift (a
	// dangling marker the cleanup regex could not remove, or a duplicated
	// section) and the agent may be reading a stale half-contract. Absence is
	// the normal state for manual/legacy task books and is never flagged.
	if (meta.writeSurfaceMarker === "malformed") {
		appendTrace(
			meta.taskKey,
			meta.agenticdocRoot,
			"[WRITE_SURFACE] contract-section markers malformed (expected exactly one ordered marker pair)",
		);
	}
	// D-116: record which model runs this task. ExtensionAPI has no model
	// getter — the resolved id is only readable from an event context, so
	// capture it at session start (fires before the first turn). A duplicate
	// line on a later session event is harmless: readers take the last one.
	pi.on("session_start", (_event, ctx) => {
		const modelId = ctx.model?.id;
		if (modelId) appendModel(meta.taskKey, meta.agenticdocRoot, modelId);
		// T-09/AC-011 (VC-011): runtime image-capability backstop. The dispatch
		// declared `images: yes` but the resolved model cannot read images —
		// refuse before the task body runs, through the same failure channel as
		// dispatchRefusal. `outputWritten` is set first so the process 'exit'
		// safety net does not append its crash output over this refusal.
		if (meta.images === true && ctx.model && Array.isArray(ctx.model.input) && !ctx.model.input.includes("image")) {
			const line = `[IMAGE-CAP] model=${ctx.model.id} provider=${ctx.model.provider} task=${meta.taskKey} declared=images:yes`;
			writeWorkerLogLine(line);
			appendError(meta.taskKey, meta.agenticdocRoot, line);
			markOutcome(1);
			writeOutput({
				taskKey: meta.taskKey,
				agenticdocRoot: meta.agenticdocRoot,
				exitCode: 1,
				summary: "Task refused (image capability).",
				exitReason: line,
				runMarker: runMarker(runState),
			});
			outputWritten = true;
			finishRun("failed", 1);
			killTrackedDetachedChildren();
			process.exit(1);
			return;
		}
		// Fail-open (GC-8): without a resolved model the capability is
		// unverifiable — record a trace note, never block the task.
		if (meta.images === true && ctx.model === undefined) {
			appendTrace(
				meta.taskKey,
				meta.agenticdocRoot,
				"[IMAGE-CAP] fail-open: ctx.model undefined, image capability unverifiable for declared=images:yes",
			);
		}
	});
	writeWorkerLogLine(
		`[worker] start task=${meta.taskKey} type=${meta.type} phases=${phaseTotal > 0 ? phaseTotal : "-"}`,
	);

	// Safety net: guarantee an output.md exists on any exit path. The normal
	// writers (success / timeout / catch) set outputWritten=true; if the process
	// dies before any of them run (hard crash, unexpected process.exit), the
	// exit hook writes a minimal failure output so the PM never sees silence.
	let outputWritten = false;
	process.on("exit", () => {
		// Hard-crash backstop: an exit path that bypassed the explicit kills
		// below (uncaught exception, unexpected process.exit) must not leak the
		// bash tool's in-flight child trees as orphans (2026-09-19 incident:
		// idle-killed worker left a spinning probe at 151 GB WS).
		// Isolated so a future throwing change in the kill path can never
		// skip the fallback output write below (currently throw-free: both
		// killProcessTree branches swallow their own errors).
		try {
			killTrackedDetachedChildren();
		} catch {
			// Best-effort during exit — nothing else we can do.
		}
		if (outputWritten) return;
		try {
			writeOutputGuarded({
				taskKey: meta.taskKey,
				agenticdocRoot: meta.agenticdocRoot,
				exitCode: 1,
				summary: "(worker exited without writing output)",
				exitReason: "Process exited before output.md was written (crash or unexpected exit).",
			});
		} catch {
			// Best-effort during exit — nothing else we can do.
		}
		// Crash backstop: nothing wrote output, so this run ended without a
		// result — record that in the product too (a normal terminal path returns
		// above via `outputWritten`). Guarded so a terminal state is never
		// downgraded.
		if (!isTerminalRunStatus(runState.status)) finishRun("failed", 1);
	});

	// RAG surface (D-002): registered only when the project enables servers;
	// disabled projects get no registration and no probe (structural zero impact).
	// The probe runs here so tool descriptions can carry the unreachable marker
	// before the first agent turn.
	let ragRuntime: RagRuntime | null = null;
	const controlRoot = controlRootFromTaskPath(taskPath);
	const workerTaskDir = path.dirname(taskPath);
	try {
		ragRuntime = registerRagTools(pi, controlRoot, {
			breaker: new Breaker(),
			workerTaskDir,
			role: roleForTaskType(meta.type),
			phase: meta.phase ?? "",
		});
	} catch (err) {
		writeWorkerLogLine(`[worker] rag disabled: ${err instanceof Error ? err.message : String(err)}`);
	}
	// Narrow write channel (D-101/D-104/D-106): roles whose allowlist has no
	// write/edit tool get `worker_file` registered — a structural gate mirroring
	// `registerRagTools`'s disabled→skip. OUTSIDE the RAG try/catch on purpose:
	// a broken RAG config must not swallow a read-only role's only channel.
	const hasWriteTools = toolsForType(meta.type).includes("write");
	if (!hasWriteTools) {
		registerWorkerFileTool(pi, workerTaskDir);
	}
	if (ragRuntime !== null) {
		await ragRuntime.ready;
		ragRuntime.workerTaskDir = workerTaskDir;
		// T-05: real budget instance. task.md headers win over the project's
		// `rag.budgets` defaults; the wall guard shares the watchdog wall budget.
		ragRuntime.budget = new Budget(
			workerTaskDir,
			meta.ragChatBudget ?? ragRuntime.config.budgets.chat,
			(meta.ragTimeBudgetS ?? ragRuntime.config.budgets.timeS) * 1000,
			{ taskWallMs: resolveBudgetMs(meta.timeoutMin, process.env.PI_WORKER_TIMEOUT_MS) },
		);
	}

	// Set tool allowlist once before the first agent run (AC-010)
	// setActiveTools is an action method — must be deferred to after runner.initialize().
	// `applyRagTools` recomputes the complete expected set on every run, so the
	// handler stays idempotent across phase/follow-up turns (D-002); a null
	// runtime reproduces the pre-RAG `setActiveTools(toolsForType(type))` byte
	// for byte.
	pi.on("before_agent_start", () => {
		applyRagTools(pi, ragRuntime, meta.type);
	});

	// Read-scope interceptor (D-106): read/ls/find/grep share one containment
	// gate. ls/find/grep default to the cwd (= project root) when their path
	// is omitted — that implicit target goes through the same containment as
	// an explicit path, so dropping the argument cannot bypass the scope.
	// grep's glob filter is not separately validated (the search root is).
	if (readScopeConfig) {
		const projectRoot = process.cwd(); // launcher spawns workers with cwd = project root (D-106 base)
		pi.on("tool_call", (event) => {
			if (
				event.toolName !== "read" &&
				event.toolName !== "ls" &&
				event.toolName !== "find" &&
				event.toolName !== "grep"
			) {
				return undefined;
			}
			const inputPath = (event.input as { path?: unknown } | undefined)?.path;
			const rawPath = typeof inputPath === "string" && inputPath !== "" ? inputPath : ".";
			const verdict = checkReadScopeCall(projectRoot, readScopeConfig, readScopeState, event.toolName, rawPath);
			if (verdict.allowed) {
				readScopeState.allowedCalls++;
				readScopeState.bytesRead += verdict.chargedBytes;
				return undefined;
			}
			const rejection: ReadScopeRejection = {
				tool: event.toolName,
				path: rawPath,
				rule: verdict.rule ?? "scope",
				ts: new Date().toISOString(),
			};
			readScopeRejections.push(rejection);
			appendReadScopeTraceLine(meta.taskKey, meta.agenticdocRoot, rejection);
			return { block: true, reason: verdict.reason };
		});
	}

	// Bash write-surface guard (AC-005b / contract C3): a role with `bash` but no
	// write/edit tool (today: `research` only) could bypass its narrow
	// `worker_file` channel through a shell command. Known write patterns are
	// classified, their targets resolved, and only targets outside the worker's
	// write surface are blocked. The surface is the default (own taskDir +
	// `<key>/evidence/**`), narrowed by the task's `write_scope:` header when the
	// producer (T-02) rendered one. Pure-read and unclassifiable commands pass
	// silently (P1: a miss is preferable to a false block).
	const bashWriteScopeConfig: BashWriteScopeConfig | undefined =
		isShellRole(meta.type) && isWritelessRole(meta.type)
			? {
					projectRoot: process.cwd(), // launcher spawns workers with cwd = project root
					taskDir,
					keyDir: path.dirname(meta.agenticdocRoot),
					trueRoot: meta.trueAgenticdocRoot,
					writeScope: meta.writeScope,
				}
			: undefined;
	// AC-007/T-03 outcome counters: mutated by the guard below, consumed by
	// `recordEnd` for the `[WRITE_SCOPE_SUMMARY]` line. Declared outside the
	// `if` so the settle path can read them.
	const writeScopeCounts: WriteScopeCounts = { allowDetermined: 0, deny: 0, allowUnknown: 0 };
	if (bashWriteScopeConfig) {
		const config = bashWriteScopeConfig;
		pi.on("tool_call", (event) => {
			if (event.toolName !== "bash") return undefined;
			const command = (event.input as { command?: unknown } | undefined)?.command;
			if (typeof command !== "string" || command.trim() === "") return undefined;
			for (const candidate of extractBashWriteCandidates(command)) {
				const verdict = checkBashWriteScopeTarget(config, candidate.target, candidate.verbatim);
				if (verdict.rule === "allow-unknown") {
					// Contract cost (F1–F3): not blockable — audit first, then continue.
					writeScopeCounts.allowUnknown += 1;
					appendBashWriteScopeTraceLine(meta.taskKey, meta.agenticdocRoot, {
						ts: new Date().toISOString(),
						blocked: false,
						rule: "allow-unknown",
						detail: verdict.detail ?? "target-not-statically-determinable",
						risk: verdict.risk,
						target: candidate.target,
						pattern: candidate.pattern,
						command,
					});
					continue;
				}
				if (verdict.allowed) {
					writeScopeCounts.allowDetermined += 1;
					continue;
				}
				writeScopeCounts.deny += 1;
				appendBashWriteScopeTraceLine(meta.taskKey, meta.agenticdocRoot, {
					ts: new Date().toISOString(),
					blocked: true,
					rule: verdict.rule ?? "scope",
					detail: verdict.detail ?? "blocked",
					target: candidate.target,
					pattern: candidate.pattern,
					command,
				});
				return { block: true, reason: verdict.reason };
			}
			return undefined;
		});
	}

	// Activity tracking (AC-001): lastActivityAt is refreshed by every
	// lifecycle signal — token deltas (message_update: the discriminator
	// between a slow in-flight generation and a dead connection), message
	// boundaries, turns, and tool events. The idle watchdog kills only when
	// NOTHING has moved for the idle threshold.
	// In-flight tools (T-04 classification): a running tool owns the activity
	// clock. A bash call is legitimately silent for long stretches (its updates
	// are output-driven), so raw idle is the wrong discriminator while it is in
	// flight — the tool-idle clock is judged instead, bounded by toolIdleMs so a
	// HUNG tool still dies. Keyed by toolCallId; tool_execution_end fires on
	// every path (errors included), so the state cannot leak into the next turn.
	interface InFlightTool {
		name: string;
		startedAt: number;
		lastActivityAt: number;
	}
	const inFlightTools = new Map<string, InFlightTool>();
	let lastActivityAt = startedAt;
	let lastDeltaAt: number | undefined;
	let lastToolAt: number | undefined;
	/** Last source that refreshed `lastActivityAt` (VC-004 evidence field). */
	let lastActivitySource = "session_start";
	const touch = (source: string): void => {
		lastActivityAt = Date.now();
		lastActivitySource = source;
	};
	pi.on("message_update", () => {
		touch("delta");
		lastDeltaAt = Date.now();
	});
	pi.on("message_start", () => touch("message_start"));
	pi.on("message_end", () => touch("message_end"));
	pi.on("turn_start", () => touch("turn_start"));
	pi.on("turn_end", () => touch("turn_end"));
	pi.on("agent_start", () => touch("agent_start"));
	pi.on("tool_execution_update", (event) => {
		const tool = inFlightTools.get(event.toolCallId);
		if (tool) tool.lastActivityAt = Date.now();
		touch("tool_update");
	});
	pi.on("tool_execution_end", (event) => {
		inFlightTools.delete(event.toolCallId);
		touch("tool_end");
	});

	// Track tool calls for trace.log (AC-012) + structured [TOOL]/[TOOL_ERR]
	// progress lines: what the worker is operating on, and where it failed.
	// Read/write counters and target sets feed the convergence checkpoint.
	let toolCallCount = 0;
	let toolErrorCount = 0;
	const toolsUsed = new Set<string>();
	let readCount = 0;
	let writeCount = 0;
	const writeTargets = new Set<string>();
	const readCounts = new Map<string, number>();
	pi.on("tool_execution_start", (event) => {
		toolCallCount++;
		toolsUsed.add(event.toolName);
		const toolStartedAt = Date.now();
		inFlightTools.set(event.toolCallId, {
			name: event.toolName,
			startedAt: toolStartedAt,
			lastActivityAt: toolStartedAt,
		});
		touch("tool_start");
		lastToolAt = Date.now();
		const target = toolTarget(event.args);
		if (READ_TOOLS.has(event.toolName)) {
			readCount++;
			if (target) readCounts.set(target, (readCounts.get(target) ?? 0) + 1);
		} else if (WRITE_TOOLS.has(event.toolName)) {
			writeCount++;
			if (target) writeTargets.add(target);
		}
		appendTrace(meta.taskKey, meta.agenticdocRoot, `tool_call ${event.toolName}`);
		appendTool(meta.taskKey, meta.agenticdocRoot, event.toolName, target);
	});
	pi.on("tool_execution_end", (event) => {
		if (!event.isError) return;
		toolErrorCount++;
		appendToolError(meta.taskKey, meta.agenticdocRoot, event.toolName, toolErrorText(event.result));
	});

	// Capture last assistant text for output summary (AC-019)
	let lastAssistantText = "";
	pi.on("agent_end", (event) => {
		touch("agent_end");
		for (let i = event.messages.length - 1; i >= 0; i--) {
			const msg = event.messages[i];
			if (msg.role === "assistant") {
				const text = msg.content
					.filter((c): c is { type: "text"; text: string } => c.type === "text" && "text" in c)
					.map((c) => c.text)
					.join("\n");
				if (text) lastAssistantText = text;
				break;
			}
		}
	});

	// Shared terminal bookkeeping: trace [END] with exact runtime + a status
	// line into worker.log (synchronous — survives an immediate process.exit).
	function recordEnd(exitCode: 0 | 1 | 2): void {
		// Single exit-code → status mapping (markOutcome), reused here so the trace
		// line, the persisted record and the marker can never disagree (AC-006).
		const status = markOutcome(exitCode);
		appendEnd(meta.taskKey, meta.agenticdocRoot, {
			exitCode,
			elapsedMs: Date.now() - startedAt,
			toolCalls: toolCallCount,
			phaseDone: meta.phases ? completedPhaseIdx : undefined,
			phaseTotal,
		});
		// AC-007/T-03: one machine summary per guarded run, after the last audit
		// row and before the terminal status is persisted. Write roles register no
		// guard and stay byte-identical (VC-024).
		if (bashWriteScopeConfig) {
			appendWriteScopeSummary(meta.taskKey, meta.agenticdocRoot, writeScopeCounts);
		}
		finishRun(status, exitCode);
		writeWorkerLogLine(
			`[worker] ${status} exit=${exitCode} elapsed=${formatHeartbeatAge(
				Date.now() - startedAt,
			)} tools=${toolCallCount}${toolErrorCount > 0 ? ` tool_errors=${toolErrorCount}` : ""}${
				phaseTotal > 0 ? ` phases=${completedPhaseIdx}/${phaseTotal}` : ""
			}`,
		);
	}

	// Watchdog suite (AC-001/002/003/004, GC-4 as amended 2026-09-09).
	// - idle watchdog: NOTHING moved (no deltas/tools/turns) for idleMs while
	//   the task is unfinished → true hang (dead API call). Detail line records
	//   the discriminating evidence (last delta vs last tool).
	// - wall budget: total runtime exceeded → the task simply needs more time;
	//   the PM reads the Exit Reason and decides retry-with-larger-budget vs
	//   split vs takeover. Wall kills with recent activity are NOT hangs.
	// - convergence checkpoint: past min(30m, budget/2) while unfinished, write
	//   machine evidence + steer the agent to self-assess; refresh every 10m.
	// - deadline steer: near budget end, steer the agent to wrap up and produce
	//   its final reply (→ output.md) instead of dying mid-finalization.
	const budgetMs = resolveBudgetMs(meta.timeoutMin, process.env.PI_WORKER_TIMEOUT_MS);
	const idleMs = resolveIdleMs(process.env.PI_WORKER_IDLE_MS);
	// T-04: the in-flight branch judges the tool-idle clock against this bound
	// (>= the raw idle threshold) so a silent long command is not a hang, while a
	// tool that never reports progress still dies.
	const toolIdleMs = resolveToolIdleMs(idleMs);
	const riskAnchorMs = checkpointAnchorMs(budgetMs);
	let taskDone = false;
	let lastCheckpoint: { risk: "low" | "mid" | "high"; reads: number; writes: number; phases: string } | undefined;
	let checkpointTimer: NodeJS.Timeout | undefined;
	let steerTimer: NodeJS.Timeout | undefined;
	let idleTimer: NodeJS.Timeout | undefined;
	let wallTimer: NodeJS.Timeout | undefined;

	function clearWatchdogTimers(): void {
		if (idleTimer) clearInterval(idleTimer);
		if (wallTimer) clearTimeout(wallTimer);
		if (checkpointTimer) clearTimeout(checkpointTimer);
		if (steerTimer) clearTimeout(steerTimer);
	}

	/** Freshest in-flight tool (max lastActivityAt), or undefined when none. */
	function freshestInFlightTool(): InFlightTool | undefined {
		let best: InFlightTool | undefined;
		for (const tool of inFlightTools.values()) {
			if (best === undefined || tool.lastActivityAt > best.lastActivityAt) best = tool;
		}
		return best;
	}

	function timeoutExit(kind: "idle" | "wall", detail: string): void {
		taskDone = true;
		clearWatchdogTimers();
		clearInterval(heartbeat);
		appendTimeout(meta.taskKey, meta.agenticdocRoot, kind, detail);
		const ckpt = lastCheckpoint
			? ` (checkpoint: risk=${lastCheckpoint.risk} reads=${lastCheckpoint.reads} writes=${
					lastCheckpoint.writes
				} phases=${lastCheckpoint.phases})`
			: "";
		writeOutputGuarded({
			taskKey: meta.taskKey,
			agenticdocRoot: meta.agenticdocRoot,
			exitCode: 1,
			summary: `Worker timed out (${kind}).`,
			exitReason: `${kind} timeout: ${detail}${ckpt}`,
		});
		recordEnd(1);
		outputWritten = true;
		// Kill the bash tool's in-flight child trees before exiting: the
		// watchdog fires while a tool call can still be hung (spinning probe,
		// dead API call mid-command) and Windows descendants survive the
		// parent. Fire-and-forget (detached taskkill / kill(-pgid)); every
		// write above is already synchronous.
		killTrackedDetachedChildren();
		process.exit(1);
	}

	/** Machine convergence evidence for the checkpoint line (AC-004). Risk is
	 * advisory only — the PM (fullest context) judges and decides. */
	function writeCheckpoint(): void {
		const elapsedMs = Date.now() - startedAt;
		let repeatTop = 0;
		for (const n of readCounts.values()) repeatTop = Math.max(repeatTop, n);
		const phasesStr = phaseTotal > 0 ? `${completedPhaseIdx}/${phaseTotal}` : "-";
		const risk = computeRisk({
			elapsedMs,
			anchorMs: riskAnchorMs,
			writes: writeCount,
			phasesTotal: phaseTotal,
			phasesDone: completedPhaseIdx,
			repeatTop,
		});
		appendCheckpoint(meta.taskKey, meta.agenticdocRoot, {
			elapsedMs,
			reads: readCount,
			writes: writeCount,
			phases: phasesStr,
			uniqTargets: writeTargets.size,
			repeatTop,
			risk,
		});
		lastCheckpoint = { risk, reads: readCount, writes: writeCount, phases: phasesStr };
		// Machine line: written by code (D-104/D-105) for roles with no write tool;
		// the self-assessment line goes through worker_file or the reply, per role.
		// Write roles keep the pre-change behavior byte for byte (no [machine] line).
		if (!hasWriteTools) {
			appendProgressLine(
				meta.taskKey,
				meta.agenticdocRoot,
				formatMachineCheckpoint({
					elapsedMs,
					reads: readCount,
					writes: writeCount,
					phases: phasesStr,
					repeatTop,
					risk,
				}),
			);
		}
		// Self-assessment steer. sendUserMessage with deliverAs: while the agent is
		// mid-run (tool call or generation) a bare call throws "Agent is already
		// processing" — followUp queues the steer as its own turn after the current
		// one, so in-flight work is never disrupted (smoke-validated 2026-09-09).
		// Both role branches keep followUp; only the wording differs (VC-004).
		const taskDir = path.dirname(taskPath);
		pi.sendUserMessage(
			checkpointSteerText({
				elapsedMs,
				budgetMs,
				progressPath: path.join(taskDir, "progress.md"),
				hasWriteTools,
				narrowTool: WORKER_FILE_TOOL,
			}),
			{ deliverAs: "followUp" },
		);
	}

	function scheduleCheckpoint(delayMs: number): void {
		checkpointTimer = setTimeout(() => {
			if (taskDone) return;
			writeCheckpoint();
			scheduleCheckpoint(CHECKPOINT_REFRESH_MS);
		}, delayMs);
		checkpointTimer.unref();
	}
	scheduleCheckpoint(riskAnchorMs);

	steerTimer = setTimeout(() => {
		if (taskDone) return;
		// deliverAs "steer": urgent — inject into the CURRENT turn so the model
		// sees the wrap-up directive at its next opportunity, mid-turn.
		pi.sendUserMessage(
			`[mw deadline] 预算还剩约 ${formatHeartbeatAge(
				budgetMs - steerAtMs(budgetMs),
			)}。立即停止开始新工作：完成当前最小步骤后收尾，最终回复中列出已完成/未完成/后续建议（会被存为 output.md 摘要）。最终回复第一行必须是单行结论（状态 + 关键产出/卡点）。`,
			{ deliverAs: "steer" },
		);
	}, steerAtMs(budgetMs));
	steerTimer.unref();

	idleTimer = setInterval(() => {
		if (taskDone) return;
		const now = Date.now();
		const idleForMs = now - lastActivityAt;
		// B (T-04): while a tool is in flight, judge the TOOL-idle clock, not raw
		// activity. A silent long bash is not a hung worker; the tool's own
		// heartbeat (core/tools/bash.ts) keeps this clock fresh. The bound keeps a
		// genuinely hung tool killable (C/VC-006).
		const inFlight = freshestInFlightTool();
		if (inFlight !== undefined) {
			const toolIdleForMs = now - inFlight.lastActivityAt;
			if (toolIdleForMs < toolIdleMs) return;
			const toolRunS = Math.round((now - inFlight.startedAt) / 1000);
			const written = appendIdleKillEvidence(meta.taskKey, meta.agenticdocRoot, {
				toolInFlight: inFlight.name,
				toolRunS,
				toolIdleS: Math.round(toolIdleForMs / 1000),
				silenceS: Math.round(idleForMs / 1000),
				thresholdS: Math.round(toolIdleMs / 1000),
				thresholdKind: "tool_idle",
				lastActivity: lastActivitySource,
			});
			if (!written) return; // no evidence -> no kill
			timeoutExit(
				"idle",
				`in-flight tool ${inFlight.name} silent for ${Math.round(
					toolIdleForMs / 1000,
				)}s (tool running ${toolRunS}s, threshold ${Math.round(toolIdleMs / 1000)}s, last activity ${
					lastActivitySource
				})`,
			);
			return;
		}
		if (idleForMs < idleMs) return;
		// C (T-04): the no-in-flight branch keeps the existing judgement, with a
		// second confirmation that the token-delta clock is stale too — a recent
		// delta is the one signal that separates a slow generation from a dead
		// connection, so a genuinely hung worker is still killed (VC-006).
		const deltaIdleMs = lastDeltaAt === undefined ? Number.POSITIVE_INFINITY : now - lastDeltaAt;
		if (deltaIdleMs < idleMs) return;
		const written = appendIdleKillEvidence(meta.taskKey, meta.agenticdocRoot, {
			toolInFlight: "none",
			toolRunS: null,
			toolIdleS: null,
			silenceS: Math.round(idleForMs / 1000),
			thresholdS: Math.round(idleMs / 1000),
			thresholdKind: "idle",
			lastActivity: lastActivitySource,
		});
		if (!written) return; // no evidence -> no kill
		const d = lastDeltaAt === undefined ? "-" : `${Math.round((now - lastDeltaAt) / 1000)}`;
		const t = lastToolAt === undefined ? "-" : `${Math.round((now - lastToolAt) / 1000)}`;
		timeoutExit(
			"idle",
			`no activity for ${Math.round(idleForMs / 1000)}s (last delta ${d}s ago, last tool ${t}s ago)`,
		);
	}, 30_000);
	idleTimer.unref();

	wallTimer = setTimeout(() => {
		if (taskDone) return;
		const sinceAct = Math.round((Date.now() - lastActivityAt) / 1000);
		timeoutExit("wall", `budget ${Math.round(budgetMs / 1000)}s exceeded (last activity ${sinceAct}s ago)`);
	}, budgetMs);
	wallTimer.unref();

	// Phase state machine: track how many phases have been dispatched and completed.
	// - initialSettled: true once the first agent_settled fires (after pi -p <task_content>)
	// - nextPhaseIdx: index of the next phase prompt to send (or phases.length when all sent)
	// - completedPhaseIdx: index of the phase whose output should be written on current settle
	let initialSettled = false;
	let nextPhaseIdx = 0;
	let completedPhaseIdx = 0;
	const phases = meta.phases;

	// Heartbeat: a [HEARTBEAT] line every HEARTBEAT_INTERVAL_MS, written by pure
	// code (this timer, not the LLM) so liveness evidence continues while the
	// agent is mid-generation with no tool calls (design D-003). Phase progress
	// is read at tick time; unref'd so it never holds the event loop, cleared on
	// every exit path below.
	const heartbeat = setInterval(() => {
		appendHeartbeat(
			meta.taskKey,
			meta.agenticdocRoot,
			phases && phases.length > 0 ? `${completedPhaseIdx}/${phases.length}` : "-",
		);
		// Same tick refreshes the product-carried liveness stamp: a reader that
		// has only run.json can still tell a live run from a dead one (D-022).
		runState.last_heartbeat_at = new Date().toISOString();
		writeRunState(taskDir, runState);
	}, HEARTBEAT_INTERVAL_MS);
	heartbeat.unref();

	function buildSummary(): string {
		const base = lastAssistantText || "Task completed.";
		const tools =
			toolsUsed.size > 0 ? ` Tools used: ${[...toolsUsed].sort().join(", ")} (${toolCallCount} calls).` : "";
		return `${base}${tools}`;
	}

	/** AC-007/DD-09: the effort half of `## Exit Reason` — which product file this
	 * run actually wrote, taken from the live write-tool targets (not from disk, so
	 * it reflects what the agent did even when the file was later removed). The
	 * value domain is fixed: the two canonical products, or `none`. */
	function writesLabel(): "report.md" | "progress.md" | "none" {
		const bases = new Set([...writeTargets].map((t) => path.basename(t.replace(/[\\/]+$/, ""))));
		if ([...bases].some((b) => b === "report.md" || /^report-.+\.md$/.test(b))) return "report.md";
		if (bases.has("progress.md")) return "progress.md";
		return "none";
	}

	/** Success path. Does NOT process.exit: this handler runs inside pi's
	 * agent_settled emit — returning lets pi's print mode resolve, print the
	 * final assistant message to stdout (captured as worker.log), flush, and
	 * exit with its own code. Exiting here was why worker.log stayed empty:
	 * process.exit truncates the pending stdout flush. */
	function finishSuccess(): void {
		// AC-010②: a second settle in the same process is a no-op — without this the
		// append-only writer (output-writer.ts D-117) adds a second harness block,
		// a second `[END]` and (for an NC run) a second no-product alarm.
		if (taskDone) return;
		taskDone = true;
		clearWatchdogTimers();
		clearInterval(heartbeat);
		// AC-006 (contract C5): a writeless role that settles without a product is
		// needs-clarification, not done. Judged here — before the single write-out —
		// so the output.md marker, `## Questions`, run.json.status and `[END] exit=`
		// all carry the same verdict. Write roles are exempt: a coding run's
		// deliverable is the repository, not a file in its own task dir.
		const evidence = isWritelessRole(meta.type)
			? hasDeliverableEvidence(taskDir, lastAssistantText)
			: { delivered: true, channel: "none" as const, detail: "write role" };
		const exitCode: 0 | 2 = evidence.delivered ? 0 : 2;
		// AC-007/DD-09: carry the settle-time artifacts into the product so a
		// `## Deliverables` section can list them (the writer drops output.md and
		// progress.md, and omits the section when nothing is left).
		const effort = `writes=${writesLabel()}`;
		writeOutputGuarded({
			taskKey: meta.taskKey,
			agenticdocRoot: meta.agenticdocRoot,
			exitCode,
			summary: buildSummary(),
			changedFiles: collectArtifacts(taskDir),
			verificationSteps: "See task output for details.",
			exitReason: evidence.delivered
				? `Agent settled after ${toolCallCount} tool call(s). ${effort}`
				: `Agent settled after ${toolCallCount} tool call(s) without a deliverable: ${evidence.detail} ${effort}`,
			questions: evidence.delivered ? undefined : `no-product: ${evidence.detail}`,
		});
		if (!evidence.delivered) {
			// The ledger root is the TRUE `.agenticdoc` root (meta.trueAgenticdocRoot),
			// never `<key>/workers` (meta.agenticdocRoot) — the latter would scatter the
			// row into a directory no consumer reads.
			recordDispatchAlarm(meta.trueAgenticdocRoot, {
				kind: "no-product",
				count: 1,
				detail: `${meta.taskKey}:${evidence.channel}`,
			});
		}
		// VC-014 (AC-010): warning-only required-but-unused marker. ragRuntime is
		// null on an RAG-less project, so this is a structural zero-write no-op.
		if (ragRuntime !== null) {
			emitRagRequiredMissing({
				config: ragRuntime.config,
				taskType: meta.type,
				phase: evidencePhase(meta.phase),
				outputText: lastAssistantText,
				keyDir: path.dirname(meta.agenticdocRoot),
				taskDir: path.dirname(taskPath),
			});
		}
		recordEnd(exitCode);
		outputWritten = true;
	}

	pi.on("agent_settled", () => {
		try {
			// AC-010②: this handler is the settle entry point; once finishSuccess has
			// run (taskDone), later settles must not re-write phase files, re-emit
			// goal checks or append another output.md block. Phased tasks keep
			// taskDone === false until the final finishSuccess, so the phase machine
			// below is unaffected.
			if (taskDone) return;
			if (!initialSettled) {
				initialSettled = true;
				// Initial task prompt (from pi -p) has settled
				if (phases && phases.length > 0) {
					// Send first phase prompt
					appendPhase(meta.taskKey, meta.agenticdocRoot, "start", 1, phases.length, phases[0].name);
					pi.sendUserMessage(phases[0].prompt);
					nextPhaseIdx = 1;
					return;
				}
				// No phases — write output and let pi exit naturally
				finishSuccess();
				return;
			}

			// A phase just completed: write its output file and goal-check trace
			if (phases) {
				const phaseIndex = completedPhaseIdx;
				writePhaseFile(
					meta.taskKey,
					meta.agenticdocRoot,
					phaseIndex,
					lastAssistantText || `Phase ${phaseIndex + 1} complete`,
				);
				// D-116: goal.md lives in the TRUE .agenticdoc root (task.md four
				// levels up) — meta.agenticdocRoot is the workers dir and would stat
				// {owner}/workers/goal.md, a guaranteed miss ([GOAL_CHECK] recorded 0).
				appendGoalCheck(meta.taskKey, meta.agenticdocRoot, phaseIndex + 1, goalMtime(meta.trueAgenticdocRoot));
				completedPhaseIdx++;
				appendPhase(meta.taskKey, meta.agenticdocRoot, "done", phaseIndex + 1, phases.length);

				if (nextPhaseIdx < phases.length) {
					// More phases — send next prompt
					const next = phases[nextPhaseIdx];
					appendPhase(meta.taskKey, meta.agenticdocRoot, "start", nextPhaseIdx + 1, phases.length, next.name);
					pi.sendUserMessage(next.prompt);
					nextPhaseIdx++;
					return;
				}
			}

			// All phases done (or no phases after initial settle)
			finishSuccess();
		} catch (err) {
			taskDone = true;
			clearWatchdogTimers();
			clearInterval(heartbeat);
			appendError(meta.taskKey, meta.agenticdocRoot, String(err));
			writeOutputGuarded({
				taskKey: meta.taskKey,
				agenticdocRoot: meta.agenticdocRoot,
				exitCode: 1,
				summary: "Task failed during output writing.",
				exitReason: String(err),
			});
			recordEnd(1);
			outputWritten = true;
			killTrackedDetachedChildren();
			process.exit(1);
		}
	});
}

/** Double-quote backslash handling for `tokenizeShellCommand` (P-1): POSIX says
 * a backslash inside double quotes escapes only `$`, a backtick, `"` and `\`;
 * every other backslash is a literal character. Folding all of them away erased
 * Windows path separators, so `& "C:\Program Files\Git\bin\bash.exe" -c "..."`
 * tokenized to a name no wrapper set could match. Appends the escaped/literal
 * character and returns the last consumed index (the caller advances one).
 * Declared after its call site on purpose: AC-011 pins the line numbers that
 * spec.md/design.md reference.
 *
 * T-18/A also folds a trailing `.exe` off the command basename at the two
 * command-position call sites (`skipWrapperPrefix`, `extractCommand`):
 * `bash.exe`/`cmd.exe`/`powershell.exe` are the same wrappers as their bare
 * names, and the unwrap sets are exact-name matches. */
function appendDoubleQuoteEscape(command: string, i: number, append: (ch: string, live: boolean) => void): number {
	const next = command[i + 1];
	if (next === "$" || next === "`" || next === '"' || next === "\\") {
		append(next, false);
		return i + 1;
	}
	append("\\", false);
	return i;
}

/** T-18/A + T-20/H-2: the command-position basename with a trailing Windows
 * `.exe` folded away. `bash.exe`/`cmd.exe`/`powershell.exe` are the same
 * wrappers as their bare names, and the unwrap sets are exact-name matches.
 * Splits on both separators itself instead of `path.basename`: the latter uses
 * the host's semantics, so `C:\...\bash.exe` did not fold on POSIX (Linux CI).
 * Declared after its call sites for the same AC-011 line-number reason. */
function commandBasename(text: string): string {
	const base = (
		text
			.replace(/[\\/]+$/, "")
			.split(/[\\/]/)
			.pop() ?? ""
	).toLowerCase();
	return base.replace(/\.exe$/, "");
}

/** T-20/H-4: the tokenizer emits `;` both for a literal `;` and for a physical
 * newline, but a heredoc body starts at the physical newline. Tag the newline
 * tokens so `dropHeredocBodies` can split on real line boundaries: with
 * `cat <<EOF; printf y > real.md` the `;` is not a body start, the following
 * `\n` is. The tag lives in a `WeakSet` so `ShellToken` itself is unchanged. */
const LINE_BREAK_TOKENS = new WeakSet<ShellToken>();
function markLineBreak(token: ShellToken): ShellToken {
	LINE_BREAK_TOKENS.add(token);
	return token;
}

/** T-19/C-17: a heredoc body is DATA, not shell source. `cat <<EOF > out.md`
 * writes only out.md, and a body line `x > y` writes nothing — judging its `>`
 * as a redirect was a false block. The tokenizer has no line state of its own
 * (a newline is just a `;` operator), so the body token ranges are identified
 * and removed here before the redirect scan. Handles `<<` / `<<-` (one operator
 * token) and quoted delimiters (the tokenizer already unquotes the word), skips
 * `<<` inside `(( ))` arithmetic (a shift, not a heredoc) and ignores `<<<`
 * here-strings (single-word, no body). Declared after its call site on purpose:
 * AC-011 pins the line numbers that spec.md/design.md reference. */
function dropHeredocBodies(tokens: ShellToken[]): ShellToken[] {
	const lines: ShellToken[][] = [[]];
	for (const token of tokens) {
		if (LINE_BREAK_TOKENS.has(token)) lines.push([]);
		else lines[lines.length - 1].push(token);
	}
	const dropped = new Set<number>();
	// T-20/H-3: on a CRLF-opened heredoc the tokenizer keeps a trailing `\r` in
	// the word, so a `<<EOF\r` opener and an `EOF` closer (mixed EOL) must compare
	// equal or the search runs to the end and swallows the real redirects.
	const trimDelimiter = (value: string): string => value.replace(/\r+$/, "");
	for (let line = 0; line < lines.length; line++) {
		const delimiters: string[] = [];
		let depth = 0;
		for (let i = 0; i + 1 < lines[line].length; i++) {
			const token = lines[line][i];
			if (token.operator && token.text === "((") depth += 1;
			else if (token.operator && token.text === "))") depth = Math.max(0, depth - 1);
			else if (depth === 0 && token.operator && (token.text === "<<" || token.text === "<<-")) {
				if (!lines[line][i + 1].operator) delimiters.push(trimDelimiter(lines[line][i + 1].text));
			}
		}
		if (delimiters.length === 0) continue;
		let cursor = line;
		for (const delimiter of delimiters) {
			let end = cursor + 1;
			while (end < lines.length && !(lines[end].length === 1 && trimDelimiter(lines[end][0].text) === delimiter))
				end++;
			for (let d = cursor + 1; d <= end && d < lines.length; d++) dropped.add(d);
			cursor = end;
		}
		line = cursor;
	}
	if (dropped.size === 0) return tokens;
	const kept: ShellToken[] = [];
	for (let line = 0; line < lines.length; line++) {
		if (line > 0) kept.push({ text: ";", operator: true, verbatim: true });
		if (!dropped.has(line)) kept.push(...lines[line]);
	}
	return kept;
}
