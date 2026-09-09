import * as fs from "node:fs";
import * as path from "node:path";

export interface WriteOutputOpts {
	taskKey: string;
	agenticdocRoot: string;
	exitCode: 0 | 1 | 2 | 130;
	summary: string;
	changedFiles?: string[];
	verificationSteps?: string;
	questions?: string;
	exitReason?: string;
}

function outputDir(taskKey: string, agenticdocRoot: string): string {
	const resolved = path.resolve(agenticdocRoot, taskKey);
	const root = path.resolve(agenticdocRoot);
	if (!resolved.startsWith(`${root}${path.sep}`) && resolved !== root) {
		throw new Error(`Invalid taskKey: path traversal detected in "${taskKey}"`);
	}
	return resolved;
}

export function writeOutput(opts: WriteOutputOpts): void {
	const dir = outputDir(opts.taskKey, opts.agenticdocRoot);
	fs.mkdirSync(dir, { recursive: true });

	const outputPath = path.join(dir, "output.md");

	const sections: string[] = [];
	sections.push(`## Summary\n\n${opts.summary || "(no summary)"}`);

	if (opts.exitCode === 0) {
		const files = opts.changedFiles?.join("\n") ?? "(none)";
		sections.push(`## Changed Files\n\n${files}`);
		sections.push(`## Verification Steps\n\n${opts.verificationSteps || "(none)"}`);
		sections.push(`## Exit Reason\n\n${opts.exitReason || "Task completed successfully."}`);
	} else if (opts.exitCode === 1) {
		sections.push(`## Exit Reason\n\n${opts.exitReason || "Task failed."}`);
	} else if (opts.exitCode === 2) {
		sections.push(`## Questions\n\n${opts.questions || "(no questions provided)"}`);
	} else if (opts.exitCode === 130) {
		sections.push(`## Exit Reason\n\nTask was cancelled (exit 130).`);
	}

	fs.writeFileSync(outputPath, `${sections.join("\n\n")}\n`, "utf8");
}

export function appendTrace(taskKey: string, agenticdocRoot: string, line: string): void {
	const dir = outputDir(taskKey, agenticdocRoot);
	fs.mkdirSync(dir, { recursive: true });
	const tracePath = path.join(dir, "trace.log");
	const ts = new Date().toISOString();
	fs.appendFileSync(tracePath, `[FLOW] ${ts} ${line}\n`, "utf8");
}

// ── Structured lifecycle lines (trace.log) ────────────────────────────────────
// Machine-parseable progress beyond liveness: what the task is doing, for how
// long, and how it ended. Formats are mirrored by the regexes in
// shared/heartbeat.ts (readTaskProgress) — keep the two in sync.

function appendLifecycleLine(taskKey: string, agenticdocRoot: string, line: string): void {
	const dir = outputDir(taskKey, agenticdocRoot);
	fs.mkdirSync(dir, { recursive: true });
	fs.appendFileSync(path.join(dir, "trace.log"), `${line}\n`, "utf8");
}

function truncLine(s: string, max: number): string {
	return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}

/** Task start marker: `[START] ts task=<key> type=<type> phases=<n|->`. */
export function appendStart(taskKey: string, agenticdocRoot: string, type: string, phaseTotal: number): void {
	appendLifecycleLine(
		taskKey,
		agenticdocRoot,
		`[START] ${new Date().toISOString()} task=${taskKey} type=${type} phases=${phaseTotal > 0 ? phaseTotal : "-"}`,
	);
}

/** Phase transition marker: `[PHASE] ts start|done <idx>/<total> [name]`. */
export function appendPhase(
	taskKey: string,
	agenticdocRoot: string,
	state: "start" | "done",
	idx: number,
	total: number,
	name = "",
): void {
	const tail = state === "start" && name ? ` ${truncLine(name, 60)}` : "";
	appendLifecycleLine(taskKey, agenticdocRoot, `[PHASE] ${new Date().toISOString()} ${state} ${idx}/${total}${tail}`);
}

/** Tool action marker: `[TOOL] ts <tool> [target]` — the file/command a tool
 * call operates on, so trace.log shows WHAT the worker is doing, not just that
 * it is alive. */
export function appendTool(taskKey: string, agenticdocRoot: string, toolName: string, target: string): void {
	appendLifecycleLine(
		taskKey,
		agenticdocRoot,
		`[TOOL] ${new Date().toISOString()} ${toolName}${target ? ` ${truncLine(target, 80)}` : ""}`,
	);
}

/** Failed tool call marker: `[TOOL_ERR] ts <tool> <first error line>`. */
export function appendToolError(taskKey: string, agenticdocRoot: string, toolName: string, message: string): void {
	appendLifecycleLine(
		taskKey,
		agenticdocRoot,
		`[TOOL_ERR] ${new Date().toISOString()} ${toolName} ${truncLine(message, 120)}`,
	);
}

/** Watchdog fire marker (AC-001): `[TIMEOUT] ts <kind>: <detail>`.
 * kind="idle" — no activity (deltas/tools/turns) for the idle threshold:
 * a genuinely hung API call / dead connection. kind="wall" — the task's
 * total wall budget ran out while still healthy (work was ongoing); the PM
 * decides retry-with-larger-budget vs split vs takeover from the Exit Reason. */
export function appendTimeout(taskKey: string, agenticdocRoot: string, kind: "idle" | "wall", detail: string): void {
	appendLifecycleLine(taskKey, agenticdocRoot, `[TIMEOUT] ${new Date().toISOString()} ${kind}: ${detail}`);
}

export interface CheckpointTraceOpts {
	elapsedMs: number;
	reads: number;
	writes: number;
	/** "<done>/<total>" for phased tasks, "-" for phaseless. */
	phases: string;
	uniqTargets: number;
	repeatTop: number;
	risk: "low" | "mid" | "high";
}

/** Convergence checkpoint marker (AC-004): `[CHECKPOINT] ts elapsed=<s>s
 * reads=<n> writes=<n> phases=<d>/<t> uniq_targets=<n> repeat_top=<k>
 * risk=<low|mid|high>`. Written past the checkpoint time while the task is
 * still running (refreshed every 10m) — the machine evidence the PM uses to
 * judge convergence vs divergence. Mirrored by CHECKPOINT_LINE_RE in
 * shared/heartbeat.ts. */
export function appendCheckpoint(taskKey: string, agenticdocRoot: string, opts: CheckpointTraceOpts): void {
	appendLifecycleLine(
		taskKey,
		agenticdocRoot,
		`[CHECKPOINT] ${new Date().toISOString()} elapsed=${Math.round(opts.elapsedMs / 1000)}s reads=${
			opts.reads
		} writes=${opts.writes} phases=${opts.phases} uniq_targets=${opts.uniqTargets} repeat_top=${
			opts.repeatTop
		} risk=${opts.risk}`,
	);
}

/** Unexpected worker error marker: `[ERROR] ts <first line>`. */
export function appendError(taskKey: string, agenticdocRoot: string, message: string): void {
	appendLifecycleLine(
		taskKey,
		agenticdocRoot,
		`[ERROR] ${new Date().toISOString()} ${truncLine(message.split("\n")[0] ?? "", 160)}`,
	);
}

export interface EndTraceOpts {
	exitCode: 0 | 1 | 2 | 130;
	/** Total task runtime in ms. */
	elapsedMs: number;
	toolCalls: number;
	/** Completed phase count (phased tasks only). */
	phaseDone?: number;
	phaseTotal?: number;
}

/** Terminal marker: `[END] ts exit=<c> elapsed=<sec>s tools=<n> phases=<done>/<total>|->`. */
export function appendEnd(taskKey: string, agenticdocRoot: string, opts: EndTraceOpts): void {
	const phases = opts.phaseTotal && opts.phaseTotal > 0 ? `${opts.phaseDone ?? 0}/${opts.phaseTotal}` : "-";
	appendLifecycleLine(
		taskKey,
		agenticdocRoot,
		`[END] ${new Date().toISOString()} exit=${opts.exitCode} elapsed=${Math.round(
			opts.elapsedMs / 1000,
		)}s tools=${opts.toolCalls} phases=${phases}`,
	);
}

export function appendGoalCheck(taskKey: string, agenticdocRoot: string, phaseNum: number, goalMtimeMs: number): void {
	const dir = outputDir(taskKey, agenticdocRoot);
	fs.mkdirSync(dir, { recursive: true });
	const tracePath = path.join(dir, "trace.log");
	fs.appendFileSync(tracePath, `[GOAL_CHECK] phase=${phaseNum} goal_mtime=${goalMtimeMs}\n`, "utf8");
}

/** Append a worker heartbeat line to trace.log (design D-003). Written by
 * the worker-mode interval timer — pure code, never the LLM — so liveness
 * continues while the agent is mid-generation. `phase` is
 * "<completed>/<total>" for phased tasks or "-" for phaseless ones. */
export function appendHeartbeat(taskKey: string, agenticdocRoot: string, phase: string): void {
	const dir = outputDir(taskKey, agenticdocRoot);
	fs.mkdirSync(dir, { recursive: true });
	const tracePath = path.join(dir, "trace.log");
	const ts = new Date().toISOString();
	fs.appendFileSync(tracePath, `[HEARTBEAT] ${ts} task=${taskKey} phase=${phase}\n`, "utf8");
}
