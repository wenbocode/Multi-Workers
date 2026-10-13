import * as fs from "node:fs";
import * as path from "node:path";
import { diffLedger } from "../shared/change-ledger.js";
import { readTaskType } from "../shared/task-frontmatter.js";
import { checkRecovery } from "./output-sections.js";
/** Never-throwing read (the product files may not exist yet). */
function readFileSafe(filePath) {
    try {
        return fs.readFileSync(filePath, "utf8");
    }
    catch {
        return "";
    }
}
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
/** Header `type:` of the worker's `task.md`, or undefined when the file is
 * missing / carries no header value. `readTaskType` never reads a body line, so
 * the legacy double-header form cannot hand this predicate the wrong role. */
function typeFromTaskMd(dir) {
    try {
        const reading = readTaskType(fs.readFileSync(path.join(dir, "task.md"), "utf8"));
        return reading.source === "header" ? reading.type : undefined;
    }
    catch {
        return undefined;
    }
}
/**
 * The agent-authored product text the contracts judge: the worker's own report
 * (`report.md`) when present, else the harness/agent product (`output.md`),
 * else the settle summary. `report.md` first because design §3.1 puts the
 * coding `改动清单` there, and a coding worker's final reply can be terse while
 * its report is complete (judging the reply alone would false-flip it). */
function agentProductText(dir, summary) {
    for (const name of ["report.md", "output.md"]) {
        const text = readFileSafe(path.join(dir, name));
        if (text.trim() !== "")
            return text;
    }
    return summary;
}
/**
 * Compute a run's terminal gaps in one place (T-07 requirements 1 + 6): the
 * AC-003 recovery contract over the agent product and the AC-004 change ledger
 * (`diffLedger`) over the report + trace. A migration book (no `task.md`
 * header `type:`) is never judged (P-07/P-09). A trace with zero
 * `[WRITE_FILE]` events and a non-empty declaration is *unjudgeable*
 * (`unjudgeableFiles`, T-12/F-04) — never a clean pass.
 */
export function readTerminalGaps(opts) {
    const dir = outputDir(opts.taskKey, opts.agenticdocRoot);
    const type = opts.type ?? typeFromTaskMd(dir);
    if (type === undefined)
        return { judged: false, missingSections: [], unrecordedFiles: [], unjudgeableFiles: [], ok: true };
    const productText = agentProductText(dir, opts.summary);
    const missingSections = opts.judgeRecovery === false ? [] : checkRecovery(productText, type).missing;
    const traceText = readFileSafe(path.join(dir, "trace.log"));
    const ledger = diffLedger(productText, traceText);
    const unjudgeableFiles = ledger.unjudgeable ? ledger.declared : [];
    return {
        judged: true,
        missingSections,
        unrecordedFiles: ledger.extra,
        unjudgeableFiles,
        ok: missingSections.length === 0 && ledger.extra.length === 0 && unjudgeableFiles.length === 0,
    };
}
export function writeOutput(opts) {
    const dir = outputDir(opts.taskKey, opts.agenticdocRoot);
    fs.mkdirSync(dir, { recursive: true });
    const outputPath = path.join(dir, "output.md");
    // T-04 recovery contract (AC-003 / design §3.2) + T-07 change ledger
    // (AC-004): judge the AGENT-authored product text — what output.md /
    // report.md already carry, or the final reply — BEFORE writing. The harness
    // block this call adds must never be the thing that satisfies (or hides) the
    // contract. Migration: only a dispatch that carries a header `type:` is
    // judged, so historical/manual task books and the legacy unit callers that
    // pass no type keep their byte-identical output (P-07). `opts.terminalGaps`
    // lets the settle path pass the verdict it already used for the exit code,
    // so the product and the run status can never disagree.
    const gaps = opts.terminalGaps ??
        readTerminalGaps({ taskKey: opts.taskKey, agenticdocRoot: opts.agenticdocRoot, summary: opts.summary });
    // The readback line the PM actually consumes is the FIRST line of
    // `## Questions` (pm/ui-bridge.ts readTerminalDetail), so the missing section
    // names have to ride that line — not a later paragraph the widget never reads.
    const gapNote = gaps.missingSections.length > 0 ? `缺失段：${gaps.missingSections.join("、")}` : "";
    // AC-004 (T-07 requirement 6): report-declared files the trace never recorded
    // as written are a red verdict, named on the same readback line and in their
    // own `## Ledger Gaps` section.
    const ledgerNote = gaps.unrecordedFiles.length > 0 ? `未记录写入：${gaps.unrecordedFiles.join("、")}` : "";
    // T-12/F-04: a zero-event trace with a declaration is unjudgeable — name it
    // on the readback line so the PM sees why the ledger verdict is absent
    // instead of reading a false green (or a false red).
    const unjudgeableNote = gaps.unjudgeableFiles.length > 0 ? `未记录写入（不可判）：${gaps.unjudgeableFiles.join("、")}` : "";
    const terminalNote = [gapNote, ledgerNote, unjudgeableNote].filter((note) => note !== "").join("；");
    const sections = [];
    // TL;DR first section (D-005): single-line conclusion on every exit path,
    // ahead of the verbatim ## Summary (readOutputSummary regex compatibility).
    sections.push(`## TL;DR\n\n${headline(opts.summary)}`);
    sections.push(`## Summary\n\n${opts.summary || "(no summary)"}`);
    if (opts.exitCode === 0) {
        // AC-007/DD-09: the old `## Changed Files` section claimed a file list that
        // could never exist (`changedFiles` had a single `[]` producer, so the
        // `?? "(none)"` branch was dead code). Render the collected deliverables
        // instead, and omit the section when there are none — an empty section or a
        // `(none)` placeholder would be noise a reader cannot distinguish from a
        // real, empty delivery.
        const deliverables = (opts.changedFiles ?? []).filter((f) => f !== "output.md" && f !== "progress.md");
        if (deliverables.length > 0)
            sections.push(`## Deliverables\n\n${deliverables.join("\n")}`);
        sections.push(`## Verification Steps\n\n${opts.verificationSteps || "(none)"}`);
        sections.push(`## Exit Reason\n\n${opts.exitReason || "Task completed successfully."}${terminalNote ? ` | ${terminalNote}` : ""}`);
    }
    else if (opts.exitCode === 1) {
        sections.push(`## Exit Reason\n\n${opts.exitReason || "Task failed."}${terminalNote ? ` | ${terminalNote}` : ""}`);
    }
    else if (opts.exitCode === 2) {
        sections.push(`## Questions\n\n${opts.questions || "(no questions provided)"}${terminalNote ? ` | ${terminalNote}` : ""}`);
    }
    else if (opts.exitCode === 130) {
        sections.push(`## Exit Reason\n\nTask was cancelled (exit 130).${terminalNote ? ` | ${terminalNote}` : ""}`);
    }
    // A `done` product that misses required sections / declares unrecorded
    // writes must not read as a clean completion, and a `needs-clarification`
    // run must still carry the `## Ledger Gaps` diff the PM has to chase — so the
    // named gaps are product sections on EVERY exit path (T-07 requirements 1/6).
    if (gapNote)
        sections.push(`## Recovery Gaps\n\n${gapNote}`);
    if (ledgerNote)
        sections.push(`## Ledger Gaps\n\n${ledgerNote}`);
    if (unjudgeableNote)
        sections.push(`## Ledger Unjudgeable\n\n${unjudgeableNote}`);
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
    const body = `${opts.runMarker ? `${opts.runMarker}\n\n` : ""}${sections.join("\n\n")}\n`;
    const existing = readFileSafe(outputPath);
    fs.writeFileSync(outputPath, existing.trim() === "" ? body : `${existing.trimEnd()}\n\n---\n\n${body}`, "utf8");
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
/** Model record (D-116: worker model visibility): `[MODEL] ts model=<id>` —
 * the pi-resolved model id captured at session start (ExtensionAPI exposes
 * the model only via event contexts, so this is written from the worker's
 * session_start handler, before the first turn). Consumed by the watch
 * widget's model badge; old bundles simply lack the line. */
export function appendModel(taskKey, agenticdocRoot, modelId) {
    appendLifecycleLine(taskKey, agenticdocRoot, `[MODEL] ${new Date().toISOString()} model=${modelId}`);
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
/** Machine checkpoint line (design D-105) written into a worker's progress.md
 * for read-only roles that have no write tool: `CKPT <n>m [machine]
 * ts=<ISO-8601> reads=<n> writes=<n> phases=<d>/<t> repeat_top=<k>
 * risk=<low|mid|high>`. Exactly one line with no trailing newline — the caller
 * (appendProgressLine) owns the newline so the file stays pure-append. The
 * `[machine]` marker keeps it distinguishable from agent self-assessed CKPT
 * lines in the same file (AC-002/AC-003). */
export function formatMachineCheckpoint(opts) {
    return `CKPT ${Math.round(opts.elapsedMs / 60000)}m [machine] ts=${new Date().toISOString()} reads=${opts.reads} writes=${opts.writes} phases=${opts.phases} repeat_top=${opts.repeatTop} risk=${opts.risk}`;
}
/** Append one pre-formatted progress line to `<taskKey>/progress.md`
 * (design D-107). Pure append: never reads or truncates existing content, so
 * PM-authored or worker self-assessed lines are preserved byte-for-byte
 * (AC-002) and the P-003 truncate-before-evaluate failure mode cannot occur.
 * Reuses outputDir(), so taskKey path traversal keeps being rejected. */
export function appendProgressLine(taskKey, agenticdocRoot, line) {
    const dir = outputDir(taskKey, agenticdocRoot);
    fs.mkdirSync(dir, { recursive: true });
    fs.appendFileSync(path.join(dir, "progress.md"), `${line}\n`, "utf8");
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