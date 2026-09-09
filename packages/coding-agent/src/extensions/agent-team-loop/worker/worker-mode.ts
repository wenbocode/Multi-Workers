import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";
import { formatHeartbeatAge, HEARTBEAT_INTERVAL_MS } from "../shared/heartbeat.ts";
import {
	appendCheckpoint,
	appendEnd,
	appendError,
	appendGoalCheck,
	appendHeartbeat,
	appendPhase,
	appendStart,
	appendTimeout,
	appendTool,
	appendToolError,
	appendTrace,
	writeOutput,
} from "./output-writer.ts";
import type { TaskPhase } from "./phase-runner.ts";
import { goalMtime, writePhaseFile } from "./phase-runner.ts";

// ── Tool allowlists by task type ─────────────────────────────────────────────

const TOOL_ALLOWLISTS: Record<string, string[]> = {
	coding: ["read", "write", "edit", "bash", "find", "grep", "ls"],
	review: ["read", "find", "grep", "ls"],
	research: ["read", "find", "grep", "ls", "bash"],
	fallback: ["read", "write", "edit", "bash", "find", "grep", "ls"],
};

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
	/** Wall budget in minutes from the task.md `timeout:` header. */
	timeoutMin?: number;
}

export function parseTaskMd(taskPath: string): TaskMeta {
	const content = fs.readFileSync(taskPath, "utf8");
	const lines = content.split("\n");

	let taskType = "default";
	let timeoutMin: number | undefined;
	const phases: TaskPhase[] = [];
	let currentPhase: TaskPhase | null = null;
	let inPhasePrompt = false;

	for (const line of lines) {
		const trimmed = line.trim();
		if (trimmed.startsWith("type:")) {
			taskType = trimmed.slice("type:".length).trim();
		}
		if (trimmed.startsWith("timeout:")) {
			const v = Number(trimmed.slice("timeout:".length).trim());
			if (Number.isFinite(v) && v > 0) timeoutMin = v;
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

	// taskKey is the parent directory name of the task file
	const agenticdocRoot = path.dirname(path.dirname(taskPath));
	const taskKey = path.basename(path.dirname(taskPath));

	return {
		type: taskType,
		phases: phases.length > 0 ? phases : undefined,
		taskKey,
		agenticdocRoot,
		timeoutMin,
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

// ── Main entry ───────────────────────────────────────────────────────────────

export async function workerModeActivate(pi: ExtensionAPI): Promise<void> {
	const taskPathEnv = process.env.PI_WORKER_TASK;
	if (!taskPathEnv) {
		return;
	}

	const taskPath = path.resolve(taskPathEnv);
	if (!fs.existsSync(taskPath)) {
		process.exit(1);
	}

	const meta = parseTaskMd(taskPath);
	const startedAt = Date.now();
	const phaseTotal = meta.phases?.length ?? 0;

	// Task lifecycle start: trace.log gets a machine-parseable [START] anchor
	// (runtime origin for elapsed computation), worker.log a human status line.
	appendStart(meta.taskKey, meta.agenticdocRoot, meta.type, phaseTotal);
	writeWorkerLogLine(
		`[worker] start task=${meta.taskKey} type=${meta.type} phases=${phaseTotal > 0 ? phaseTotal : "-"}`,
	);

	// Safety net: guarantee an output.md exists on any exit path. The normal
	// writers (success / timeout / catch) set outputWritten=true; if the process
	// dies before any of them run (hard crash, unexpected process.exit), the
	// exit hook writes a minimal failure output so the PM never sees silence.
	let outputWritten = false;
	process.on("exit", () => {
		if (outputWritten) return;
		try {
			writeOutput({
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
		writeOutput({
			taskKey: meta.taskKey,
			agenticdocRoot: meta.agenticdocRoot,
			exitCode: 1,
			summary: `Worker timed out (${kind}).`,
			exitReason: `${kind} timeout: ${detail}${ckpt}`,
		});
		recordEnd(1);
		outputWritten = true;
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
			)}。立即停止开始新工作：完成当前最小步骤后收尾，最终回复中列出已完成/未完成/后续建议（会被存为 output.md 摘要）。`,
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
		writeOutput({
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
				appendGoalCheck(meta.taskKey, meta.agenticdocRoot, phaseIndex + 1, goalMtime(meta.agenticdocRoot));
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
			writeOutput({
				taskKey: meta.taskKey,
				agenticdocRoot: meta.agenticdocRoot,
				exitCode: 1,
				summary: "Task failed during output writing.",
				exitReason: String(err),
			});
			recordEnd(1);
			outputWritten = true;
			process.exit(1);
		}
	});
}
