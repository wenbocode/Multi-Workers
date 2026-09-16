import * as fs from "node:fs";
import * as path from "node:path";
function outputDir(taskKey, agenticdocRoot) {
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
export function headline(summary) {
    const firstLine = summary.split("\n").find((line) => line.trim() !== "") ?? "";
    let s = firstLine.trim();
    while (HEADLINE_MARKER_RE.test(s)) {
        s = s.replace(HEADLINE_MARKER_RE, "").trim();
    }
    s = s.replace(/\s+/g, " ");
    return s === "" ? "(no conclusion)" : truncLine(s, 100);
}
export function writeOutput(opts) {
    const dir = outputDir(opts.taskKey, opts.agenticdocRoot);
    fs.mkdirSync(dir, { recursive: true });
    const outputPath = path.join(dir, "output.md");
    const sections = [];
    // TL;DR first section (D-005): single-line conclusion on every exit path,
    // ahead of the verbatim ## Summary (readOutputSummary regex compatibility).
    sections.push(`## TL;DR\n\n${headline(opts.summary)}`);
    sections.push(`## Summary\n\n${opts.summary || "(no summary)"}`);
    if (opts.exitCode === 0) {
        const files = opts.changedFiles?.join("\n") ?? "(none)";
        sections.push(`## Changed Files\n\n${files}`);
        sections.push(`## Verification Steps\n\n${opts.verificationSteps || "(none)"}`);
        sections.push(`## Exit Reason\n\n${opts.exitReason || "Task completed successfully."}`);
    }
    else if (opts.exitCode === 1) {
        sections.push(`## Exit Reason\n\n${opts.exitReason || "Task failed."}`);
    }
    else if (opts.exitCode === 2) {
        sections.push(`## Questions\n\n${opts.questions || "(no questions provided)"}`);
    }
    else if (opts.exitCode === 130) {
        sections.push(`## Exit Reason\n\nTask was cancelled (exit 130).`);
    }
    fs.writeFileSync(outputPath, `${sections.join("\n\n")}\n`, "utf8");
}
export function appendTrace(taskKey, agenticdocRoot, line) {
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
function appendLifecycleLine(taskKey, agenticdocRoot, line) {
    const dir = outputDir(taskKey, agenticdocRoot);
    fs.mkdirSync(dir, { recursive: true });
    fs.appendFileSync(path.join(dir, "trace.log"), `${line}\n`, "utf8");
}
function truncLine(s, max) {
    return s.length <= max ? s : `${s.slice(0, max - 1)}…`;
}
/** Task start marker: `[START] ts task=<key> type=<type> phases=<n|->`. */
export function appendStart(taskKey, agenticdocRoot, type, phaseTotal) {
    appendLifecycleLine(taskKey, agenticdocRoot, `[START] ${new Date().toISOString()} task=${taskKey} type=${type} phases=${phaseTotal > 0 ? phaseTotal : "-"}`);
}
/** Phase transition marker: `[PHASE] ts start|done <idx>/<total> [name]`. */
export function appendPhase(taskKey, agenticdocRoot, state, idx, total, name = "") {
    const tail = state === "start" && name ? ` ${truncLine(name, 60)}` : "";
    appendLifecycleLine(taskKey, agenticdocRoot, `[PHASE] ${new Date().toISOString()} ${state} ${idx}/${total}${tail}`);
}
/** Tool action marker: `[TOOL] ts <tool> [target]` — the file/command a tool
 * call operates on, so trace.log shows WHAT the worker is doing, not just that
 * it is alive. */
export function appendTool(taskKey, agenticdocRoot, toolName, target) {
    appendLifecycleLine(taskKey, agenticdocRoot, `[TOOL] ${new Date().toISOString()} ${toolName}${target ? ` ${truncLine(target, 80)}` : ""}`);
}
/** Failed tool call marker: `[TOOL_ERR] ts <tool> <first error line>`. */
export function appendToolError(taskKey, agenticdocRoot, toolName, message) {
    appendLifecycleLine(taskKey, agenticdocRoot, `[TOOL_ERR] ${new Date().toISOString()} ${toolName} ${truncLine(message, 120)}`);
}
/** Watchdog fire marker (AC-001): `[TIMEOUT] ts <kind>: <detail>`.
 * kind="idle" — no activity (deltas/tools/turns) for the idle threshold:
 * a genuinely hung API call / dead connection. kind="wall" — the task's
 * total wall budget ran out while still healthy (work was ongoing); the PM
 * decides retry-with-larger-budget vs split vs takeover from the Exit Reason. */
export function appendTimeout(taskKey, agenticdocRoot, kind, detail) {
    appendLifecycleLine(taskKey, agenticdocRoot, `[TIMEOUT] ${new Date().toISOString()} ${kind}: ${detail}`);
}
/** Convergence checkpoint marker (AC-004): `[CHECKPOINT] ts elapsed=<s>s
 * reads=<n> writes=<n> phases=<d>/<t> uniq_targets=<n> repeat_top=<k>
 * risk=<low|mid|high>`. Written past the checkpoint time while the task is
 * still running (refreshed every 10m) — the machine evidence the PM uses to
 * judge convergence vs divergence. Mirrored by CHECKPOINT_LINE_RE in
 * shared/heartbeat.ts. */
export function appendCheckpoint(taskKey, agenticdocRoot, opts) {
    appendLifecycleLine(taskKey, agenticdocRoot, `[CHECKPOINT] ${new Date().toISOString()} elapsed=${Math.round(opts.elapsedMs / 1000)}s reads=${opts.reads} writes=${opts.writes} phases=${opts.phases} uniq_targets=${opts.uniqTargets} repeat_top=${opts.repeatTop} risk=${opts.risk}`);
}
/** Unexpected worker error marker: `[ERROR] ts <first line>`. */
export function appendError(taskKey, agenticdocRoot, message) {
    appendLifecycleLine(taskKey, agenticdocRoot, `[ERROR] ${new Date().toISOString()} ${truncLine(message.split("\n")[0] ?? "", 160)}`);
}
/** Terminal marker: `[END] ts exit=<c> elapsed=<sec>s tools=<n> phases=<done>/<total>|->`. */
export function appendEnd(taskKey, agenticdocRoot, opts) {
    const phases = opts.phaseTotal && opts.phaseTotal > 0 ? `${opts.phaseDone ?? 0}/${opts.phaseTotal}` : "-";
    appendLifecycleLine(taskKey, agenticdocRoot, `[END] ${new Date().toISOString()} exit=${opts.exitCode} elapsed=${Math.round(opts.elapsedMs / 1000)}s tools=${opts.toolCalls} phases=${phases}`);
}
export function appendGoalCheck(taskKey, agenticdocRoot, phaseNum, goalMtimeMs) {
    const dir = outputDir(taskKey, agenticdocRoot);
    fs.mkdirSync(dir, { recursive: true });
    const tracePath = path.join(dir, "trace.log");
    fs.appendFileSync(tracePath, `[GOAL_CHECK] phase=${phaseNum} goal_mtime=${goalMtimeMs}\n`, "utf8");
}
/** Append a worker heartbeat line to trace.log (design D-003). Written by
 * the worker-mode interval timer — pure code, never the LLM — so liveness
 * continues while the agent is mid-generation. `phase` is
 * "<completed>/<total>" for phased tasks or "-" for phaseless ones. */
export function appendHeartbeat(taskKey, agenticdocRoot, phase) {
    const dir = outputDir(taskKey, agenticdocRoot);
    fs.mkdirSync(dir, { recursive: true });
    const tracePath = path.join(dir, "trace.log");
    const ts = new Date().toISOString();
    fs.appendFileSync(tracePath, `[HEARTBEAT] ${ts} task=${taskKey} phase=${phase}\n`, "utf8");
}
//# sourceMappingURL=output-writer.js.map