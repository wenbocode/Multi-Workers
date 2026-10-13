import * as fs from "node:fs";
import * as path from "node:path";
import { collectMalformedCandidates, diffLedger } from "../shared/change-ledger.ts";
import { readRunState } from "../shared/run-store.ts";
import { readTaskType } from "../shared/task-frontmatter.ts";
import { checkRecovery } from "./output-sections.ts";

export interface WriteOutputOpts {
	taskKey: string;
	agenticdocRoot: string;
	exitCode: 0 | 1 | 2 | 130;
	summary: string;
	/** Role type (T-04 recovery contract). Optional: when omitted the worker's
	 * `task.md` header `type:` is used; when neither is available the recovery
	 * contract is not applied (legacy/manual task book, migration-compatible).
	 * `worker-mode.ts` passes no type today, so the task.md lookup is the live
	 * path for real runs. */
	type?: string;
	/** Deliverables observed at settle time (AC-007/DD-09). The historical name
	 * is kept for the frozen call sites, but the list is now rendered as
	 * `## Deliverables` (the machine-generated products `output.md` and
	 * `progress.md` are dropped). An empty list omits the section entirely —
	 * never an empty section, never a `(none)` placeholder. */
	changedFiles?: string[];
	verificationSteps?: string;
	questions?: string;
	exitReason?: string;
	/** Product-carried run identity line (`<!-- mw-run: <task_key>@<iso>
	 * status=<s> -->`, D-022/AC-022). Written as the first line of the HARNESS
	 * block: on an empty/missing output.md that is the file's first line, and when
	 * the agent wrote its own content the harness block already sits below the
	 * `---` separator — so the marker can never displace an agent-written
	 * machine-readable first line (VERDICT=/TASKS=, D-117 contract). */
	runMarker?: string;
	/** T-07 terminal verdict, computed once by the caller (`worker-mode.ts`
	 * `finishSuccess`) so the exit code and the product it writes cannot
	 * disagree. When omitted, {@link readTerminalGaps} is called here (the
	 * direct/test callers keep that path). */
	terminalGaps?: TerminalGaps;
}

/** The two judgeable gap classes at a run's terminal write (T-07).
 *
 * `missingSections` — the AC-003 recovery contract: required `output.md`
 * sections with no alias hit. `unrecordedFiles` — the AC-004 change ledger:
 * files the report's `改动清单` declares that the trace never recorded as
 * written (`diffLedger().extra`). `judged: false` is the migration state (no
 * `task.md` or no header `type:`) where neither contract applies (P-07/P-09). */
export interface TerminalGaps {
	judged: boolean;
	missingSections: string[];
	unrecordedFiles: string[];
	/** T-12/F-04: report-declared files on a trace with ZERO write events — the
	 * ledger cannot be judged. Named on the readback line and in the product so
	 * the run is not mistaken for a clean pass. */
	unjudgeableFiles: string[];
	/** T-17/C-36c: malformed path tokens (unexpanded `$VAR`/`%VAR%` residue and
	 * unparseable paths). WARN-ONLY: surfaced in a `## Ledger Malformed` product
	 * section and a trace line, never part of `ok` and never a gap. */
	malformedFiles: string[];
	/** T-17b/C-36 fourth class: declared-but-unrecorded paths that are
	 * framework-owned infrastructure (`_workers.parallel`, the index, the run
	 * record / trace / product, `serve.meta`, `pm-state.md`). T-21 R-1 narrowed
	 * this to FILE-level ownership: the conductor's `_autopilot/**` control
	 * plane is judgeable and lands in `unrecordedFiles` (red) instead.
	 * WARN-ONLY, exactly like `malformedFiles`: surfaced in a `## Ledger Infra`
	 * product section and a `[FLOW]` trace line, never part of `ok` and never a
	 * gap — these are framework writes, not worker writes. */
	infraFiles: string[];
	/** T-17c/C-36 fifth class: declared-but-unrecorded paths that do not exist on
	 * disk (`update_index.py` — a ghost name harvested from code text;
	 * `os.replace` — a Python identifier). A path with no file/directory on disk
	 * cannot be a write this run performed, so it is WARN-ONLY like the infra
	 * class: surfaced in a `## Ledger Unresolvable` product section and a
	 * `[FLOW] ledger-unresolvable` trace line, never part of `ok` and never a
	 * gap. The classification reads the filesystem (existence), never the
	 * token's shape. */
	unresolvableFiles: string[];
	/** True iff every gap list is empty. */
	ok: boolean;
}

/** Never-throwing read (the product files may not exist yet). */
function readFileSafe(filePath: string): string {
	try {
		return fs.readFileSync(filePath, "utf8");
	} catch {
		return "";
	}
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

/** Header `type:` of the worker's `task.md`, or undefined when the file is
 * missing / carries no header value. `readTaskType` never reads a body line, so
 * the legacy double-header form cannot hand this predicate the wrong role. */
function typeFromTaskMd(dir: string): string | undefined {
	try {
		const reading = readTaskType(fs.readFileSync(path.join(dir, "task.md"), "utf8"));
		return reading.source === "header" ? reading.type : undefined;
	} catch {
		return undefined;
	}
}

/**
 * The agent-authored product text the contracts judge: the worker's own report
 * (`report.md`) when present, else the harness/agent product (`output.md`),
 * else the settle summary. `report.md` first because design §3.1 puts the
 * coding `改动清单` there, and a coding worker's final reply can be terse while
 * its report is complete (judging the reply alone would false-flip it). */
function agentProductText(dir: string, summary: string): string {
	for (const name of ["report.md", "output.md"]) {
		const text = readFileSafe(path.join(dir, name));
		if (text.trim() !== "") return text;
	}
	return summary;
}

/** `run.json.started_at` as epoch ms, or undefined when the run record is
 * absent/legacy. Used by the T-17/C-36b deliverable freshness probe. */
function runStartedAtMs(dir: string): number | undefined {
	const startedAt = readRunState(dir)?.started_at;
	if (typeof startedAt !== "string") return undefined;
	const ms = Date.parse(startedAt);
	return Number.isFinite(ms) ? ms : undefined;
}

/** The worker key's `evidence/` tree (C-36b deliverable channel):
 * `<agenticdocRoot>/<taskKey>` is `<keyDir>/workers/<name>` by construction, so
 * the key dir is two levels up in both the worker-mode and the test layouts. */
function deliverableDir(taskDir: string): string {
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
export function readTerminalGaps(opts: {
	taskKey: string;
	agenticdocRoot: string;
	summary: string;
	type?: string;
	/** Root the T-17c existence probe (and the T-25 dotless arbitration)
	 * resolves declared paths against. Defaults to `process.cwd()` — the
	 * launcher starts every worker with `cwd` set to the project root, so the
	 * production default is already correct; non-cwd callers (tests) pass it. */
	projectRoot?: string;
	/** AC-003 recovery contract applies to this run. Default `true`. The settle
	 * path passes `true` for a writeless role (its reply IS the deliverable) and
	 * for a write role that actually produced a `report.md` product; a write
	 * role with no report product keeps the AC-006/C5 exemption (its deliverable
	 * is the repository). The change ledger (AC-004) is always judged. */
	judgeRecovery?: boolean;
}): TerminalGaps {
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
	return {
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
		ok: missingSections.length === 0 && ledger.extra.length === 0 && unjudgeableFiles.length === 0,
	};
}

export function writeOutput(opts: WriteOutputOpts): void {
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
	const gaps =
		opts.terminalGaps ??
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
	const unjudgeableNote =
		gaps.unjudgeableFiles.length > 0 ? `未记录写入（不可判）：${gaps.unjudgeableFiles.join("、")}` : "";
	// T-17/C-36c: warn-only path hygiene. Deliberately NOT folded into
	// `terminalNote` — a malformed token is a formatting warning, not a gap, so
	// it must never read as a failure on the `## Questions` readback line.
	const malformedNote =
		gaps.malformedFiles.length > 0 ? `格式异常（warn，不影响判定）：${gaps.malformedFiles.join("、")}` : "";
	if (malformedNote !== "") {
		appendTrace(
			opts.taskKey,
			opts.agenticdocRoot,
			`ledger-malformed count=${gaps.malformedFiles.length} samples=${gaps.malformedFiles.join(",")}`,
		);
	}
	// T-17b/C-36 fourth class: framework-owned infrastructure paths the report
	// named are NOT this worker's writes, so they are excluded from the ledger
	// judgement. Same warn shape as `malformed` — a `## Ledger Infra` section
	// plus a `[FLOW]` trace line — so the exclusion is visible, not silent, and
	// never reads as a failure on the `## Questions` readback line.
	const infraNote =
		gaps.infraFiles.length > 0 ? `框架基础设施写入（warn，不计入判定）：${gaps.infraFiles.join("、")}` : "";
	if (infraNote !== "") {
		appendTrace(
			opts.taskKey,
			opts.agenticdocRoot,
			`ledger-infra count=${gaps.infraFiles.length} samples=${gaps.infraFiles.join(",")}`,
		);
	}
	// T-17c: a declared path with no file on disk cannot be a write, so it is
	// excluded from the ledger judgement — never from the report. Same warn shape
	// as `malformed`/`infra`: a `## Ledger Unresolvable` section plus a `[FLOW]`
	// trace line, so the exclusion is visible, not silent, and never reads as a
	// failure on the `## Questions` readback line.
	const unresolvableNote =
		gaps.unresolvableFiles.length > 0
			? `不可解析声明（磁盘不存在，warn，不计入判定）：${gaps.unresolvableFiles.join("、")}`
			: "";
	if (unresolvableNote !== "") {
		appendTrace(
			opts.taskKey,
			opts.agenticdocRoot,
			`ledger-unresolvable count=${gaps.unresolvableFiles.length} samples=${gaps.unresolvableFiles.join(",")}`,
		);
	}
	const terminalNote = [gapNote, ledgerNote, unjudgeableNote].filter((note) => note !== "").join("；");

	const sections: string[] = [];
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
		if (deliverables.length > 0) sections.push(`## Deliverables\n\n${deliverables.join("\n")}`);
		sections.push(`## Verification Steps\n\n${opts.verificationSteps || "(none)"}`);
		sections.push(
			`## Exit Reason\n\n${opts.exitReason || "Task completed successfully."}${terminalNote ? ` | ${terminalNote}` : ""}`,
		);
	} else if (opts.exitCode === 1) {
		sections.push(
			`## Exit Reason\n\n${opts.exitReason || "Task failed."}${terminalNote ? ` | ${terminalNote}` : ""}`,
		);
	} else if (opts.exitCode === 2) {
		sections.push(
			`## Questions\n\n${opts.questions || "(no questions provided)"}${terminalNote ? ` | ${terminalNote}` : ""}`,
		);
	} else if (opts.exitCode === 130) {
		sections.push(`## Exit Reason\n\nTask was cancelled (exit 130).${terminalNote ? ` | ${terminalNote}` : ""}`);
	}
	// A `done` product that misses required sections / declares unrecorded
	// writes must not read as a clean completion, and a `needs-clarification`
	// run must still carry the `## Ledger Gaps` diff the PM has to chase — so the
	// named gaps are product sections on EVERY exit path (T-07 requirements 1/6).
	if (gapNote) sections.push(`## Recovery Gaps\n\n${gapNote}`);
	if (ledgerNote) sections.push(`## Ledger Gaps\n\n${ledgerNote}`);
	if (unjudgeableNote) sections.push(`## Ledger Unjudgeable\n\n${unjudgeableNote}`);
	if (malformedNote) sections.push(`## Ledger Malformed\n\n${malformedNote}`);
	if (infraNote) sections.push(`## Ledger Infra\n\n${infraNote}`);
	if (unresolvableNote) sections.push(`## Ledger Unresolvable\n\n${unresolvableNote}`);

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
