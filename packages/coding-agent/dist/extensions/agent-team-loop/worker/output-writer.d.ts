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
/** Single-line conclusion extracted from a summary (D-005): first non-empty
 * line, leading markdown markers stripped in a loop, whitespace collapsed,
 * capped at 100 chars (truncLine style — total length, ellipsis included,
 * stays <=100). Empty input, or a line that strips to nothing (e.g. `**`),
 * yields "(no conclusion)". writeOutput writes this as the `## TL;DR` first section
 * (AC-009 write half) so done-row widget details are single-line conclusions;
 * the verbatim `## Summary` section keeps readOutputSummary compatible. */
export declare function headline(summary: string): string;
/**
 * The one file the recovery judgement will read (AC-015 order): `report.md` →
 * `report-<slug>.md` (newest first) → `output.md`, each skipped when missing or
 * empty. `undefined` means no product is on disk and the judgement falls back
 * to the settle summary — the I2 backfill cannot append to a summary, so that
 * state is fail-closed (design §4.3).
 */
export declare function judgedProductFile(dir: string): string | undefined;
/**
 * The agent-authored product text the contracts judge (AC-015 order).
 * `report.md` first because design §3.1 puts the coding `改动清单` there, and a
 * coding worker's final reply can be terse while its report is complete
 * (judging the reply alone would false-flip it).
 */
export declare function agentProductText(dir: string, summary: string): string;
/**
 * Does a role's report product exist (AC-015 second entry point)? A non-empty
 * `report.md` OR `report-<slug>.md` — the SAME candidate set `agentProductText`
 * reads, so the `judgeRecovery` gate and the judged text cannot disagree. Before
 * AC-015 this predicate only `statSync`ed `report.md`, so a write role that
 * produced only `report-<slug>.md` was never judged at all.
 */
export declare function hasReportProduct(dir: string): boolean;
/**
 * The recovery verdict on the CURRENT product text, before the mechanical
 * backfill and before the terminal write (the AC-004 self-check gate). Empty
 * for a legacy book (`type === undefined`, P-07/P-09).
 */
export declare function currentRecoveryMissing(opts: {
    taskKey: string;
    agenticdocRoot: string;
    summary: string;
    type: string | undefined;
}): string[];
/** Idempotency marker of the framework's mechanical `## 上下文来源` append. */
export declare const MECHANICAL_CONTEXT_MARKER = "<!-- mw-mechanical-context-sources: v1 -->";
export interface MechanicalContextSourcesResult {
    /** Every required section is present after the attempt (empty `missing`). */
    ok: boolean;
    /** The mechanical section was appended by this call. */
    appended: boolean;
    /** Required sections still missing after the attempt (empty iff `ok`). */
    missing: string[];
    /** The file the append targeted, when a product candidate exists. */
    target?: string;
    /** Why the attempt could not satisfy the contract (fail-closed, design §4.3). */
    reason?: "no-product-file" | "not-writable" | "already-marked" | "still-missing";
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
export declare function appendMechanicalContextSources(opts: {
    taskKey: string;
    agenticdocRoot: string;
    summary: string;
    type: string | undefined;
}): MechanicalContextSourcesResult;
/**
 * Compute a run's terminal gaps in one place (T-07 requirements 1 + 6): the
 * AC-003 recovery contract over the agent product and the AC-004 change ledger
 * (`diffLedger`) over the report + trace. A migration book (no `task.md`
 * header `type:`) is never judged (P-07/P-09). A trace with zero
 * `[WRITE_FILE]` events and a non-empty declaration is *unjudgeable*
 * (`unjudgeableFiles`, T-12/F-04) — never a clean pass.
 */
export declare function readTerminalGaps(opts: {
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
}): TerminalGaps;
export declare function writeOutput(opts: WriteOutputOpts): void;
export declare function appendTrace(taskKey: string, agenticdocRoot: string, line: string): void;
/** Task start marker: `[START] ts task=<key> type=<type> phases=<n|->`. */
export declare function appendStart(taskKey: string, agenticdocRoot: string, type: string, phaseTotal: number): void;
/** Model record (D-116: worker model visibility): `[MODEL] ts model=<id>` —
 * the pi-resolved model id captured at session start (ExtensionAPI exposes
 * the model only via event contexts, so this is written from the worker's
 * session_start handler, before the first turn). Consumed by the watch
 * widget's model badge; old bundles simply lack the line. */
export declare function appendModel(taskKey: string, agenticdocRoot: string, modelId: string): void;
/** Phase transition marker: `[PHASE] ts start|done <idx>/<total> [name]`. */
export declare function appendPhase(taskKey: string, agenticdocRoot: string, state: "start" | "done", idx: number, total: number, name?: string): void;
/** Tool action marker: `[TOOL] ts <tool> [target]` — the file/command a tool
 * call operates on, so trace.log shows WHAT the worker is doing, not just that
 * it is alive. */
export declare function appendTool(taskKey: string, agenticdocRoot: string, toolName: string, target: string): void;
/** Failed tool call marker: `[TOOL_ERR] ts <tool> <first error line>`. */
export declare function appendToolError(taskKey: string, agenticdocRoot: string, toolName: string, message: string): void;
/** Watchdog fire marker (AC-001): `[TIMEOUT] ts <kind>: <detail>`.
 * kind="idle" — no activity (deltas/tools/turns) for the idle threshold:
 * a genuinely hung API call / dead connection. kind="wall" — the task's
 * total wall budget ran out while still healthy (work was ongoing); the PM
 * decides retry-with-larger-budget vs split vs takeover from the Exit Reason. */
export declare function appendTimeout(taskKey: string, agenticdocRoot: string, kind: "idle" | "wall", detail: string): void;
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
export declare function appendCheckpoint(taskKey: string, agenticdocRoot: string, opts: CheckpointTraceOpts): void;
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
export declare function formatMachineCheckpoint(opts: MachineCheckpointOpts): string;
/** Append one pre-formatted progress line to `<taskKey>/progress.md`
 * (design D-107). Pure append: never reads or truncates existing content, so
 * PM-authored or worker self-assessed lines are preserved byte-for-byte
 * (AC-002) and the P-003 truncate-before-evaluate failure mode cannot occur.
 * Reuses outputDir(), so taskKey path traversal keeps being rejected. */
export declare function appendProgressLine(taskKey: string, agenticdocRoot: string, line: string): void;
/** Unexpected worker error marker: `[ERROR] ts <first line>`. */
export declare function appendError(taskKey: string, agenticdocRoot: string, message: string): void;
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
export declare function appendEnd(taskKey: string, agenticdocRoot: string, opts: EndTraceOpts): void;
export declare function appendGoalCheck(taskKey: string, agenticdocRoot: string, phaseNum: number, goalMtimeMs: number): void;
/** Append a worker heartbeat line to trace.log (design D-003). Written by
 * the worker-mode interval timer — pure code, never the LLM — so liveness
 * continues while the agent is mid-generation. `phase` is
 * "<completed>/<total>" for phased tasks or "-" for phaseless ones. */
export declare function appendHeartbeat(taskKey: string, agenticdocRoot: string, phase: string): void;
//# sourceMappingURL=output-writer.d.ts.map