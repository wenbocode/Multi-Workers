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

/** Leading markdown markers stripped from a summary's first line (D-005):
 * heading hashes, bold asterisks, list bullets, blockquotes. */
const HEADLINE_MARKER_RE = /^(?:#{1,6}\s+|\*\*|[-*]\s+|>\s+)/;

/** Single-line conclusion extracted from a summary (D-005): first non-empty
 * line, leading markdown markers stripped in a loop, whitespace collapsed,
 * capped at 100 chars (truncLine style — total length, ellipsis included,
 * stays <=100). Empty input, or a line that strips to nothing (e.g. `**`),
 * yields "(no conclusion)". writeOutput writes this as the `## TL;DR` first section
 * (AC-009 write half) so done-row widget details are single-line conclusions;
 * the verbatim `## Summary` section keeps readOutputSummary compatible. */
export function headline(summary: string): string {
	const firstLine = summary.split("\n").find((line) => line.trim() !== "") ?? "";
	let s = firstLine.trim();
	while (HEADLINE_MARKER_RE.test(s)) {
		s = s.replace(HEADLINE_MARKER_RE, "").trim();
	}
	s = s.replace(/\s+/g, " ");
	return s === "" ? "(no conclusion)" : truncLine(s, 100);
}

export function writeOutput(opts: WriteOutputOpts): void {
	const dir = outputDir(opts.taskKey, opts.agenticdocRoot);
	fs.mkdirSync(dir, { recursive: true });

	const outputPath = path.join(dir, "output.md");

	const sections: string[] = [];
	// TL;DR first section (D-005): single-line conclusion on every exit path,
	// ahead of the verbatim ## Summary (readOutputSummary regex compatibility).
	sections.push(`## TL;DR\n\n${headline(opts.summary)}`);
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

	// D-117 (output.md clobber): task templates direct workers to write
	// deliverables and machine-readable lines into output.md (VERDICT=/TASKS=
	// first lines, conductor [VERIFY] rows, L3 verdict sections) — a full
	// overwrite at exit destroyed them, so terminal readers (PM readback,
	// readTerminalDetail, conductor regexes) only ever saw the harness
	// summary. When the file already carries agent content, preserve it
	// verbatim — its first line keeps the machine-readable contract — and
	// append the harness sections below a separator; the section parsers
	// match anywhere in the file. Empty/missing files keep today's format
	// (the agent never wrote). worker-mode guarantees one writeOutput call
	// per process (outputWritten guard), so the merge cannot compound.
	let existing = "";
	try {
		existing = fs.readFileSync(outputPath, "utf8");
	} catch {
		existing = "";
	}
	const body = `${sections.join("\n\n")}\n`;
	fs.writeFileSync(outputPath, existing.trim() === "" ? body : `${existing.trimEnd()}\n\n---\n\n${body}`, "utf8");
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

/** Model record (D-116: worker model visibility): `[MODEL] ts model=<id>` —
 * the pi-resolved model id captured at session start (ExtensionAPI exposes
 * the model only via event contexts, so this is written from the worker's
 * session_start handler, before the first turn). Consumed by the watch
 * widget's model badge; old bundles simply lack the line. */
export function appendModel(taskKey: string, agenticdocRoot: string, modelId: string): void {
	appendLifecycleLine(taskKey, agenticdocRoot, `[MODEL] ${new Date().toISOString()} model=${modelId}`);
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

export interface MachineCheckpointOpts {
	elapsedMs: number;
	reads: number;
	writes: number;
	/** "<done>/<total>" for phased tasks, "-" for phaseless. */
	phases: string;
	repeatTop: number;
	risk: "low" | "mid" | "high";
}

/** Machine checkpoint line (design D-105) written into a worker's progress.md
 * for read-only roles that have no write tool: `CKPT <n>m [machine]
 * ts=<ISO-8601> reads=<n> writes=<n> phases=<d>/<t> repeat_top=<k>
 * risk=<low|mid|high>`. Exactly one line with no trailing newline — the caller
 * (appendProgressLine) owns the newline so the file stays pure-append. The
 * `[machine]` marker keeps it distinguishable from agent self-assessed CKPT
 * lines in the same file (AC-002/AC-003). */
export function formatMachineCheckpoint(opts: MachineCheckpointOpts): string {
	return `CKPT ${Math.round(opts.elapsedMs / 60000)}m [machine] ts=${new Date().toISOString()} reads=${
		opts.reads
	} writes=${opts.writes} phases=${opts.phases} repeat_top=${opts.repeatTop} risk=${opts.risk}`;
}

/** Append one pre-formatted progress line to `<taskKey>/progress.md`
 * (design D-107). Pure append: never reads or truncates existing content, so
 * PM-authored or worker self-assessed lines are preserved byte-for-byte
 * (AC-002) and the P-003 truncate-before-evaluate failure mode cannot occur.
 * Reuses outputDir(), so taskKey path traversal keeps being rejected. */
export function appendProgressLine(taskKey: string, agenticdocRoot: string, line: string): void {
	const dir = outputDir(taskKey, agenticdocRoot);
	fs.mkdirSync(dir, { recursive: true });
	fs.appendFileSync(path.join(dir, "progress.md"), `${line}\n`, "utf8");
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
