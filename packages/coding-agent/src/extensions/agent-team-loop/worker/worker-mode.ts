import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { killTrackedDetachedChildren } from "../../../utils/shell.ts";
import { formatHeartbeatAge, HEARTBEAT_INTERVAL_MS } from "../shared/heartbeat.ts";
import {
	appendCheckpoint,
	appendEnd,
	appendError,
	appendGoalCheck,
	appendHeartbeat,
	appendModel,
	appendPhase,
	appendStart,
	appendTimeout,
	appendTool,
	appendToolError,
	appendTrace,
	type WriteOutputOpts,
	writeOutput,
} from "./output-writer.ts";
import type { TaskPhase } from "./phase-runner.ts";
import { goalMtime, writePhaseFile } from "./phase-runner.ts";
import {
	checkReadScopeCall,
	type ReadScopeConfig,
	type ReadScopeRejection,
	type ReadScopeState,
	readScopeConfigFromMeta,
} from "./read-scope.ts";

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
	fallback: ["read", "write", "edit", "bash", "find", "grep", "ls"],
};

/** Is this a dispatchable type with an explicit allowlist entry? "fallback"
 * is the internal default bucket (D-107: a `type: fallback` task with
 * origin: conductor must fail closed, not resolve to the full set). */
function isRegisteredType(taskType: string): boolean {
	return taskType !== "fallback" && taskType in TOOL_ALLOWLISTS;
}

function toolsForType(taskType: string): string[] {
	return TOOL_ALLOWLISTS[taskType] ?? TOOL_ALLOWLISTS.fallback ?? [];
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
	phases?: TaskPhase[];
	taskKey: string;
	agenticdocRoot: string;
	/** Dispatch origin marker (D-104): "conductor" on autopilot dispatches,
	 * undefined on manual/legacy tasks (which keep the fallback path, GC-8). */
	origin?: string;
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
	/** l2_read_file_cap frontmatter (positive int), when present. */
	readFileCap?: number;
	/** l2_read_byte_cap frontmatter (positive int), when present. */
	readByteCap?: number;
}

export function parseTaskMd(taskPath: string): TaskMeta {
	const content = fs.readFileSync(taskPath, "utf8");
	const lines = content.split("\n");

	let taskType = "default";
	let timeoutMin: number | undefined;
	let origin: string | undefined;
	const phases: TaskPhase[] = [];
	let currentPhase: TaskPhase | null = null;
	let inPhasePrompt = false;
	let readScope: string[] | undefined;
	let inReadScopeList = false;
	let denyGlobs: string[] | undefined;
	let inDenyGlobsList = false;
	let readFileCap: number | undefined;
	let readByteCap: number | undefined;

	for (const line of lines) {
		const trimmed = line.trim();
		if (trimmed.startsWith("type:")) {
			taskType = trimmed.slice("type:".length).trim();
		}
		if (trimmed.startsWith("timeout:")) {
			const v = Number(trimmed.slice("timeout:".length).trim());
			if (Number.isFinite(v) && v > 0) timeoutMin = v;
		}
		if (trimmed.startsWith("origin:")) {
			origin = trimmed.slice("origin:".length).trim();
		}
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
		if (trimmed.startsWith("l2_read_file_cap:")) {
			const v = Number(trimmed.slice("l2_read_file_cap:".length).trim());
			if (Number.isFinite(v) && v > 0) readFileCap = v;
		}
		if (trimmed.startsWith("l2_read_byte_cap:")) {
			const v = Number(trimmed.slice("l2_read_byte_cap:".length).trim());
			if (Number.isFinite(v) && v > 0) readByteCap = v;
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
		phases: phases.length > 0 ? phases : undefined,
		taskKey,
		agenticdocRoot,
		origin,
		trueAgenticdocRoot,
		timeoutMin,
		readScope,
		denyGlobs,
		readFileCap,
		readByteCap,
	};
}

// ── Trace helpers ────────────────────────────────────────────────────────────

/** Short, single-line argument summary for trace [TOOL] lines: the file path a
 * read/write/edit targets, the first command line for bash, or the search
 * pattern. Keeps one tool call = one trace line. */
function toolTarget(args: unknown): string {
	const a = args as { path?: unknown; command?: unknown; pattern?: unknown; query?: unknown } | undefined;
	const raw =
		typeof a?.path === "string"
			? a.path
			: typeof a?.command === "string"
				? a.command
				: typeof a?.pattern === "string"
					? a.pattern
					: typeof a?.query === "string"
						? a.query
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

	// D-107 fail-closed gate: refuse the task before any agent turn, with the
	// reason in output.md (counts into the loop budget escalation on the
	// conductor side, AC-023).
	const refusal = dispatchRefusal(meta);
	if (refusal !== undefined) {
		appendError(meta.taskKey, meta.agenticdocRoot, refusal);
		writeOutput({
			taskKey: meta.taskKey,
			agenticdocRoot: meta.agenticdocRoot,
			exitCode: 1,
			summary: "Task refused at startup (fail-closed).",
			exitReason: refusal,
		});
		writeWorkerLogLine(`[worker] refused task=${meta.taskKey} type=${meta.type}: ${refusal}`);
		killTrackedDetachedChildren();
		process.exit(1);
	}

	// Read-scope enforcement (D-106/AC-009): active only when task.md carries
	// read_scope — otherwise zero interception (AC-012 red line). Rejections
	// accumulate in memory and are written to output.md on every exit path via
	// writeOutputGuarded (the output-writer remains the unified write-out point).
	const readScopeConfig: ReadScopeConfig | undefined = readScopeConfigFromMeta(meta);
	const readScopeState: ReadScopeState = { allowedCalls: 0, bytesRead: 0 };
	const readScopeRejections: ReadScopeRejection[] = [];

	function writeOutputGuarded(opts: WriteOutputOpts): void {
		writeOutput(opts);
		appendReadScopeRejectionsSection(meta.taskKey, meta.agenticdocRoot, readScopeRejections);
	}

	// Task lifecycle start: trace.log gets a machine-parseable [START] anchor
	// (runtime origin for elapsed computation), worker.log a human status line.
	appendStart(meta.taskKey, meta.agenticdocRoot, meta.type, phaseTotal);
	// D-116: record which model runs this task. ExtensionAPI has no model
	// getter — the resolved id is only readable from an event context, so
	// capture it at session start (fires before the first turn). A duplicate
	// line on a later session event is harmless: readers take the last one.
	pi.on("session_start", (_event, ctx) => {
		const modelId = ctx.model?.id;
		if (modelId) appendModel(meta.taskKey, meta.agenticdocRoot, modelId);
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
	});

	// Set tool allowlist once before the first agent run (AC-010)
	// setActiveTools is an action method — must be deferred to after runner.initialize()
	pi.on("before_agent_start", () => {
		pi.setActiveTools(toolsForType(meta.type));
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

	// Activity tracking (AC-001): lastActivityAt is refreshed by every
	// lifecycle signal — token deltas (message_update: the discriminator
	// between a slow in-flight generation and a dead connection), message
	// boundaries, turns, and tool events. The idle watchdog kills only when
	// NOTHING has moved for the idle threshold.
	let lastActivityAt = startedAt;
	let lastDeltaAt: number | undefined;
	let lastToolAt: number | undefined;
	const touch = (): void => {
		lastActivityAt = Date.now();
	};
	pi.on("message_update", () => {
		touch();
		lastDeltaAt = Date.now();
	});
	pi.on("message_start", touch);
	pi.on("message_end", touch);
	pi.on("turn_start", touch);
	pi.on("turn_end", touch);
	pi.on("agent_start", touch);
	pi.on("tool_execution_update", touch);
	pi.on("tool_execution_end", touch);

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
		touch();
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
		touch();
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
	function recordEnd(exitCode: 0 | 1): void {
		appendEnd(meta.taskKey, meta.agenticdocRoot, {
			exitCode,
			elapsedMs: Date.now() - startedAt,
			toolCalls: toolCallCount,
			phaseDone: meta.phases ? completedPhaseIdx : undefined,
			phaseTotal,
		});
		writeWorkerLogLine(
			`[worker] ${exitCode === 0 ? "done" : "failed"} exit=${exitCode} elapsed=${formatHeartbeatAge(
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
		// Self-assessment steer: the agent appends one CKPT line to progress.md
		// (its own convergence judgment) next to the machine evidence.
		// sendUserMessage with deliverAs: while the agent is mid-run (tool call or
		// generation) a bare call throws "Agent is already processing" — followUp
		// queues the steer as its own turn after the current one, so in-flight
		// work is never disrupted (smoke-validated 2026-09-09).
		const taskDir = path.dirname(taskPath);
		pi.sendUserMessage(
			`[mw checkpoint] 运行 ${formatHeartbeatAge(elapsedMs)}（总预算 ${formatHeartbeatAge(
				budgetMs,
			)}）。请立即自评收敛性，把一行追加到 ${path.join(taskDir, "progress.md")}：CKPT ${Math.round(
				elapsedMs / 60_000,
			)}m converging=yes|no eta≈<X>m <一句话理由>。若不收敛：立即收窄范围，优先保证已完成部分可交付，不要展开新工作。`,
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
		const idleForMs = Date.now() - lastActivityAt;
		if (idleForMs < idleMs) return;
		const now = Date.now();
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
	}, HEARTBEAT_INTERVAL_MS);
	heartbeat.unref();

	function buildSummary(): string {
		const base = lastAssistantText || "Task completed.";
		const tools =
			toolsUsed.size > 0 ? ` Tools used: ${[...toolsUsed].sort().join(", ")} (${toolCallCount} calls).` : "";
		return `${base}${tools}`;
	}

	/** Success path. Does NOT process.exit: this handler runs inside pi's
	 * agent_settled emit — returning lets pi's print mode resolve, print the
	 * final assistant message to stdout (captured as worker.log), flush, and
	 * exit with its own code. Exiting here was why worker.log stayed empty:
	 * process.exit truncates the pending stdout flush. */
	function finishSuccess(): void {
		taskDone = true;
		clearWatchdogTimers();
		clearInterval(heartbeat);
		writeOutputGuarded({
			taskKey: meta.taskKey,
			agenticdocRoot: meta.agenticdocRoot,
			exitCode: 0,
			summary: buildSummary(),
			changedFiles: [],
			verificationSteps: "See task output for details.",
			exitReason: `Agent settled after ${toolCallCount} tool call(s).`,
		});
		recordEnd(0);
		outputWritten = true;
	}

	pi.on("agent_settled", () => {
		try {
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
