import * as fs from "node:fs";
import * as path from "node:path";
import { collectMalformedCandidates, diffLedger } from "../shared/change-ledger.js";
import { readRunState } from "../shared/run-store.js";
import { readTaskType } from "../shared/task-frontmatter.js";
import { checkRecovery, claimCoverage, isMechanicalSection, parseVerdictTable, recoverySectionsFor, } from "./output-sections.js";
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
/** Role-slug report basename shape (AC-015; same form `writesLabel` and
 * `WORKER_FILE_NAME_RE` treat as a first-class product). */
const SLUG_REPORT_RE = /^report-.+\.md$/;
/** Non-empty `report-<slug>.md` files in `dir`, newest mtime first (AC-015).
 * Ties break by name so the order is deterministic across filesystems; an
 * unreadable/empty file is not a candidate. */
function slugReportsByMtime(dir) {
    let names;
    try {
        names = fs.readdirSync(dir);
    }
    catch {
        return [];
    }
    const files = [];
    for (const name of names) {
        if (!SLUG_REPORT_RE.test(name))
            continue;
        const file = path.join(dir, name);
        try {
            const stat = fs.statSync(file);
            if (!stat.isFile() || stat.size === 0)
                continue;
            files.push({ file, mtimeMs: stat.mtimeMs });
        }
        catch {
            // Unreadable => not a candidate.
        }
    }
    files.sort((a, b) => b.mtimeMs - a.mtimeMs || a.file.localeCompare(b.file));
    return files.map((entry) => entry.file);
}
/**
 * The one file the recovery judgement will read (AC-015 order): `report.md` →
 * `report-<slug>.md` (newest first) → `output.md`, each skipped when missing or
 * empty. `undefined` means no product is on disk and the judgement falls back
 * to the settle summary — the I2 backfill cannot append to a summary, so that
 * state is fail-closed (design §4.3).
 */
export function judgedProductFile(dir) {
    const canonical = path.join(dir, "report.md");
    if (readFileSafe(canonical).trim() !== "")
        return canonical;
    const slug = slugReportsByMtime(dir)[0];
    if (slug !== undefined)
        return slug;
    const output = path.join(dir, "output.md");
    if (readFileSafe(output).trim() !== "")
        return output;
    return undefined;
}
/**
 * The agent-authored product text the contracts judge (AC-015 order).
 * `report.md` first because design §3.1 puts the coding `改动清单` there, and a
 * coding worker's final reply can be terse while its report is complete
 * (judging the reply alone would false-flip it).
 */
export function agentProductText(dir, summary) {
    const file = judgedProductFile(dir);
    return file === undefined ? summary : readFileSafe(file);
}
/**
 * Does a role's report product exist (AC-015 second entry point)? A non-empty
 * `report.md` OR `report-<slug>.md` — the SAME candidate set `agentProductText`
 * reads, so the `judgeRecovery` gate and the judged text cannot disagree. Before
 * AC-015 this predicate only `statSync`ed `report.md`, so a write role that
 * produced only `report-<slug>.md` was never judged at all.
 */
export function hasReportProduct(dir) {
    if (readFileSafe(path.join(dir, "report.md")).trim() !== "")
        return true;
    return slugReportsByMtime(dir).length > 0;
}
/**
 * The recovery verdict on the CURRENT product text, before the mechanical
 * backfill and before the terminal write (the AC-004 self-check gate). Empty
 * for a legacy book (`type === undefined`, P-07/P-09).
 */
export function currentRecoveryMissing(opts) {
    if (opts.type === undefined)
        return [];
    const dir = outputDir(opts.taskKey, opts.agenticdocRoot);
    return checkRecovery(agentProductText(dir, opts.summary), opts.type).missing;
}
/** Idempotency marker of the framework's mechanical `## 上下文来源` append. */
export const MECHANICAL_CONTEXT_MARKER = "<!-- mw-mechanical-context-sources: v1 -->";
/** `task.md` header scalar (the same `^[ \t]*key[ \t]*:.*$` shape the service
 * layer uses); `""` when absent. */
function taskHeaderScalar(dir, key) {
    const text = readFileSafe(path.join(dir, "task.md"));
    const match = new RegExp(`^[ \\t]*${key}[ \\t]*:[ \\t]*(\\S+)[ \\t]*$`, "m").exec(text);
    return match?.[1] ?? "";
}
/** Read targets recorded in `trace.log` (`[TOOL] <ts> <read|find|grep|ls>
 * <target>`) — at most five, de-duplicated, in first-seen order. */
function traceReadTargets(traceText) {
    const out = [];
    for (const line of traceText.split(/\r?\n/)) {
        const match = /^\[TOOL\] \S+ (?:read|find|grep|ls) (.+)$/.exec(line);
        if (match === null)
            continue;
        const target = (match[1] ?? "").trim();
        if (target !== "" && !out.includes(target))
            out.push(target);
        if (out.length >= 5)
            break;
    }
    return out;
}
/** The mechanical section body: framework-held facts only (card path/sha, the
 * product path, and up to five trace read sources). Never a substantive
 * judgement (R2). */
function renderMechanicalSections(dir, target, names) {
    const cardPath = taskHeaderScalar(dir, "card_path");
    const cardSha = taskHeaderScalar(dir, "card_sha256");
    const reads = traceReadTargets(readFileSafe(path.join(dir, "trace.log")));
    const card = cardPath === "" ? "`task.md`" : `\`${cardPath}\`${cardSha === "" ? "" : `（sha256 \`${cardSha}\`）`}`;
    const sources = reads.length > 0 ? reads : ["task.md"];
    return [
        "",
        "",
        ...names.flatMap((name) => [`## ${name}`, ""]),
        MECHANICAL_CONTEXT_MARKER,
        "",
        "> 本节由框架按已掌握事实机械补齐（settle 判定之前）；不含实质判断。",
        "",
        `- 任务卡：${card}`,
        `- 产物：\`${path.basename(target)}\``,
        `- 读取来源：${sources.map((source) => `\`${source}\``).join("、")}`,
        "",
    ].join("\n");
}
/**
 * I2 mechanical backfill (AC-005): append the mechanical `## 上下文来源` section
 * to the file the judgement will read, BEFORE the judgement runs, so the judged
 * text and the landed product cannot diverge (invariant I1). Only the
 * `MECHANICAL_SECTIONS` whitelist is ever appended (R2). Three failure classes
 * are fail-closed (design §4.3): no product file on disk (the judgement would
 * run on the settle summary), a product that cannot be written, and a product
 * that still misses the section after the append. Pure append + idempotent
 * marker: an existing marker means the file was already backfilled, so nothing
 * is written a second time.
 */
export function appendMechanicalContextSources(opts) {
    if (opts.type === undefined)
        return { ok: true, appended: false, missing: [] };
    const dir = outputDir(opts.taskKey, opts.agenticdocRoot);
    const mechanical = recoverySectionsFor(opts.type).filter((name) => isMechanicalSection(name));
    if (mechanical.length === 0)
        return { ok: true, appended: false, missing: [] };
    const target = judgedProductFile(dir);
    if (target === undefined) {
        const missing = checkRecovery(agentProductText(dir, opts.summary), opts.type).missing;
        return { ok: missing.length === 0, appended: false, missing, reason: "no-product-file" };
    }
    const before = readFileSafe(target);
    const preMissing = checkRecovery(before, opts.type).missing;
    const toFill = mechanical.filter((name) => preMissing.includes(name));
    if (toFill.length === 0) {
        return { ok: preMissing.length === 0, appended: false, missing: preMissing, target };
    }
    if (before.includes(MECHANICAL_CONTEXT_MARKER)) {
        // Marker present without the section: the file was tampered with / the
        // marker was copied. Never append twice; stay fail-closed.
        return { ok: preMissing.length === 0, appended: false, missing: preMissing, target, reason: "already-marked" };
    }
    let appended = false;
    try {
        fs.appendFileSync(target, renderMechanicalSections(dir, target, toFill), "utf8");
        appended = true;
    }
    catch {
        return { ok: false, appended: false, missing: preMissing, target, reason: "not-writable" };
    }
    const postMissing = checkRecovery(readFileSafe(target), opts.type).missing;
    if (postMissing.some((name) => toFill.includes(name))) {
        return { ok: false, appended, missing: postMissing, target, reason: "still-missing" };
    }
    return { ok: postMissing.length === 0, appended, missing: postMissing, target };
}
/** `run.json.started_at` as epoch ms, or undefined when the run record is
 * absent/legacy. Used by the T-17/C-36b deliverable freshness probe. */
function runStartedAtMs(dir) {
    const startedAt = readRunState(dir)?.started_at;
    if (typeof startedAt !== "string")
        return undefined;
    const ms = Date.parse(startedAt);
    return Number.isFinite(ms) ? ms : undefined;
}
/** The worker key's `evidence/` tree (C-36b deliverable channel):
 * `<agenticdocRoot>/<taskKey>` is `<keyDir>/workers/<name>` by construction, so
 * the key dir is two levels up in both the worker-mode and the test layouts. */
function deliverableDir(taskDir) {
    return path.join(path.dirname(path.dirname(taskDir)), "evidence");
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
        return {
            judged: false,
            missingSections: [],
            unrecordedFiles: [],
            unjudgeableFiles: [],
            malformedFiles: [],
            infraFiles: [],
            unresolvableFiles: [],
            ok: true,
        };
    const productText = agentProductText(dir, opts.summary);
    const missingSections = opts.judgeRecovery === false ? [] : checkRecovery(productText, type).missing;
    // T-04a: the claim-coverage judgement rides the same product text and the
    // same single decision point as the recovery contract (design §2.2: inside
    // `readTerminalGaps`, folded into `ok` before the caller's terminal flip).
    const claimGaps = opts.claims === undefined || opts.judgeRecovery === false
        ? undefined
        : claimCoverage(opts.claims, parseVerdictTable(productText), { projectDir: opts.projectRoot });
    const traceText = readFileSafe(path.join(dir, "trace.log"));
    // T-17: pass the role + the key's evidence tree + the run clock, so a
    // writeless role's outside-taskDir deliverable is reconciled from disk
    // (C-36a/b) instead of judged as an unrecorded read reference.
    const ledger = diffLedger(productText, traceText, {
        role: type,
        deliverableDir: deliverableDir(dir),
        runStartedAtMs: runStartedAtMs(dir),
        projectRoot: opts.projectRoot,
    });
    // T-17b/T-17c: an infra-only or unresolvable-only zero-event declaration is
    // trivially green (see `diffLedger`), and a framework/ghost path must never
    // ride the unjudgeable gap list either — only the judgeable (existing,
    // non-infra) declarations are named.
    const infraSet = new Set(ledger.infra);
    const unresolvableSet = new Set(ledger.unresolvable);
    const unjudgeableFiles = ledger.unjudgeable
        ? ledger.declared.filter((file) => !infraSet.has(file) && !unresolvableSet.has(file))
        : [];
    // C-36c: warn-only path hygiene — the malformed sample is visible but it
    // never enters a gap list and never flips `ok`.
    const malformedFiles = collectMalformedCandidates(productText);
    const gaps = {
        judged: true,
        missingSections,
        unrecordedFiles: ledger.extra,
        unjudgeableFiles,
        malformedFiles,
        // T-17b: framework-owned infrastructure writes are named for visibility
        // but never judged (they are not this worker's writes).
        infraFiles: ledger.infra,
        // T-17c: declared paths not on disk are named for visibility but never
        // judged (a nonexistent file cannot be a write).
        unresolvableFiles: ledger.unresolvable,
        ok: missingSections.length === 0 &&
            ledger.extra.length === 0 &&
            unjudgeableFiles.length === 0 &&
            (claimGaps?.length ?? 0) === 0,
    };
    // Only present when the run actually has a claim contract: an absent field
    // keeps the pre-claim verdict object byte-identical for legacy callers.
    if (claimGaps !== undefined)
        gaps.claimGaps = claimGaps;
    return gaps;
}
/**
 * T-04a: the `## Questions` first-line note naming the un-settled claims. The
 * first line of `## Questions` is the PM's readback point
 * (`pm/ui-bridge.ts::readTerminalDetail`), so the ids have to ride that line
 * rather than a later paragraph. At most three ids, with an ellipsis only when
 * more are hidden; `""` when the run has no claim gaps, so a claim-free product
 * keeps its byte-identical readback line. A gap without a claim id
 * (`claims:missing-table`) is named by its own token.
 */
function claimGapNote(claimGaps) {
    if (claimGaps === undefined || claimGaps.length === 0)
        return "";
    const ids = [];
    for (const gap of claimGaps) {
        const match = /^claim:(C-\d{2,3}(?:\.\d+)?):/.exec(gap);
        if (match === null)
            continue;
        const id = match[1] ?? "";
        if (!ids.includes(id))
            ids.push(id);
    }
    const items = ids.length > 0 ? ids : Array.from(new Set(claimGaps));
    return `未裁决断言：${items.slice(0, 3).join("、")}${items.length > 3 ? "…" : ""}`;
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
    // T-17/C-36c: warn-only path hygiene. Deliberately NOT folded into
    // `terminalNote` — a malformed token is a formatting warning, not a gap, so
    // it must never read as a failure on the `## Questions` readback line.
    const malformedNote = gaps.malformedFiles.length > 0 ? `格式异常（warn，不影响判定）：${gaps.malformedFiles.join("、")}` : "";
    if (malformedNote !== "") {
        appendTrace(opts.taskKey, opts.agenticdocRoot, `ledger-malformed count=${gaps.malformedFiles.length} samples=${gaps.malformedFiles.join(",")}`);
    }
    // T-17b/C-36 fourth class: framework-owned infrastructure paths the report
    // named are NOT this worker's writes, so they are excluded from the ledger
    // judgement. Same warn shape as `malformed` — a `## Ledger Infra` section
    // plus a `[FLOW]` trace line — so the exclusion is visible, not silent, and
    // never reads as a failure on the `## Questions` readback line.
    const infraNote = gaps.infraFiles.length > 0 ? `框架基础设施写入（warn，不计入判定）：${gaps.infraFiles.join("、")}` : "";
    if (infraNote !== "") {
        appendTrace(opts.taskKey, opts.agenticdocRoot, `ledger-infra count=${gaps.infraFiles.length} samples=${gaps.infraFiles.join(",")}`);
    }
    // T-17c: a declared path with no file on disk cannot be a write, so it is
    // excluded from the ledger judgement — never from the report. Same warn shape
    // as `malformed`/`infra`: a `## Ledger Unresolvable` section plus a `[FLOW]`
    // trace line, so the exclusion is visible, not silent, and never reads as a
    // failure on the `## Questions` readback line.
    const unresolvableNote = gaps.unresolvableFiles.length > 0
        ? `不可解析声明（磁盘不存在，warn，不计入判定）：${gaps.unresolvableFiles.join("、")}`
        : "";
    if (unresolvableNote !== "") {
        appendTrace(opts.taskKey, opts.agenticdocRoot, `ledger-unresolvable count=${gaps.unresolvableFiles.length} samples=${gaps.unresolvableFiles.join(",")}`);
    }
    const terminalNote = [gapNote, ledgerNote, unjudgeableNote, claimGapNote(gaps.claimGaps)]
        .filter((note) => note !== "")
        .join("；");
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
    else if (opts.exitCode === 3) {
        // Model-exhausted terminal (design D6 / AC-001/AC-004/AC-010): the worker
        // tripped its consecutive-error breaker. The Exit Reason opens with
        // `model unavailable:` so the PM attributes the failure with zero text
        // parsing, and the collected artifacts stay listed like any other
        // terminal product (AC-010).
        const deliverables = (opts.changedFiles ?? []).filter((f) => f !== "output.md" && f !== "progress.md");
        if (deliverables.length > 0)
            sections.push(`## Deliverables\n\n${deliverables.join("\n")}`);
        sections.push(`## Exit Reason\n\n${opts.exitReason || "model unavailable: model error budget exhausted."}${terminalNote ? ` | ${terminalNote}` : ""}`);
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
    if (malformedNote)
        sections.push(`## Ledger Malformed\n\n${malformedNote}`);
    if (infraNote)
        sections.push(`## Ledger Infra\n\n${infraNote}`);
    if (unresolvableNote)
        sections.push(`## Ledger Unresolvable\n\n${unresolvableNote}`);
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