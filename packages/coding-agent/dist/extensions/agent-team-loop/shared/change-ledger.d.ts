/**
 * shared/change-ledger.ts — T-05 / AC-004 (design §3.1): coding change history.
 *
 * A coding task produces two independent records of what it touched:
 *   - MACHINE: every successful `write`/`edit` appends one `[WRITE_FILE]
 *     path=<path>` line to the worker's `trace.log` (worker-mode.ts), every
 *     successful `worker_file` write does the same (worker-file-tool.ts), and
 *     every successful shell command with a KNOWN write target does too
 *     (T-12/F-04, `extractBashWriteCandidates`);
 *   - WORKER: the report carries a `改动清单` section listing the files it
 *     claims to have changed.
 * `diffLedger` reconciles the two: `declared ⊆ recorded`. `extra` is the
 * declared-but-unrecorded set — non-empty means "the report says it changed A,
 * the trace has no write of A".
 *
 * Leak guard (requirement 3): the event carries the path only, never the
 * written content. The parser returns paths only.
 *
 * Migration (requirement 4): a trace with ZERO `[WRITE_FILE]` lines predates
 * this mechanism (historical task books, pre-T-05 bundles) OR carried only
 * writes the extractor could not classify. T-12/F-04 splits the two by what
 * the report declares: no declaration ⇒ nothing to reconcile (green); a
 * non-empty declaration ⇒ `unjudgeable` (never green, never a false red).
 * Shell writes are recorded as events too (`worker-mode.ts`), so a bash-only
 * run is judged like any other.
 *
 * This is a leaf module: the judgement (`diffLedger`) is pure text-in/
 * verdict-out, and the only filesystem touch is the best-effort event append
 * (`appendWriteFileEvent`), which the two producers call directly. It imports
 * nothing from the extension tree (no cycles with worker-mode.ts).
 *
 * T-21 (write-intent soundness): the extraction above the reconciliation is
 * guarded so a report's prose cannot invent declarations:
 *   - negation scope is the SAME declaration item (list item line / table row /
 *     sentence), never the whole report — `未写入`/`不得`/`not written`/... drop
 *     only the path they govern, and a real `写入 x` elsewhere still counts;
 *   - only declaration positions declare (list-item heads, table rows, and
 *     write-verb-anchored prose), so a referenced path in intent prose
 *     (`import ... from "../config.ts"`, `见 task.md`) is not a declaration;
 *   - HTML comments, marker-delimited contract sections and fenced code blocks
 *     are stripped BEFORE tokenization — diff/regex documentation is not a file
 *     list;
 *   - candidates must be shape-valid repo paths (whitelist charset); tokens
 *     with a separator that fail the whitelist (`host/pid`, `src/**`, `a\nb`,
 *     full-width punctuation) are `malformed` (warn-only, never judged).
 *
 * T-25 (dotless漏红): the shape gate's "separator ⇒ dotted basename" rule is a
 * heuristic, not a truth. A separator-bearing token that passes every other
 * shape rule and names something real on disk is a declaration after all
 * (`scripts/deploy`), while a nonexistent word pair (`host/pid`) keeps the old
 * behaviour. The existence probe is read-only and resolves against the worker's
 * cwd (`LedgerOptions.projectRoot` overrides it for non-cwd callers).
 *
 * T-17 (role-aware ledger, C-36a/b/c): a writeless role's report is a survey —
 * it is full of paths it READ. When `LedgerOptions.role` is a writeless type,
 * the declaration set is therefore rebuilt (C-36a): the task's deliverable
 * (fresh files under the key's `evidence/` tree, `LedgerOptions.deliverableDir`)
 * plus real change-list declarations; surveyed paths elsewhere are read
 * references. The deliverable may sit outside taskDir,
 * so it is reconciled from disk (existence + run-window freshness,
 * `LedgerOptions.runStartedAtMs`) rather than being invisible (C-36b). Path
 * hygiene (C-36c): unexpanded variables/`%VAR%` and unparseable paths stay
 * `malformed` — warn-only, never declared, never recorded. With no `role` the
 * historical all-roles semantics are byte-for-byte unchanged.
 *
 * Attribution stays per-worker by construction: the recorded side is only the
 * caller's own `traceText` (the worker's `[WRITE_FILE]` events) — no repo-wide
 * `git status`/diff ever enters this module.
 *
 * T-17b (C-36 fourth class): framework-owned infrastructure writes are not
 * worker writes. `_workers.parallel`, the index, the worker's own
 * `run.json`/`trace.log`/`output.md`, `serve.meta` and `pm-state.md` all have
 * mtimes inside (or just after) a worker's run window, so mtime can never
 * attribute them; `INFRA_BASENAMES` does it by OWNERSHIP. They are removed from
 * `extra` and reported in `ChangeLedger.infra` instead (warn-only), which is
 * what stops the T-12 false red `未记录写入：_workers.parallel` without
 * loosening a real out-of-scope write (P-03).
 *
 * T-21 R-1 (C-37): the exemption is FILE-level only. T-17b's path-SEGMENT rule
 * (`_autopilot/**`, `.mw/**`) exempted whole trees, so a worker declaring its
 * own gate answer (`_autopilot/gates/gate-0007.md`), the roadmap or the shadow
 * decision ledger was classified infra — a real out-of-scope control-plane
 * write silently downgraded to a warn. Conductor/launcher state trees are now
 * judged like any other repo path: existing + declared + unrecorded ⇒ RED. The
 * framework files that must stay infra (the worker's own run record/trace/
 * product, the shared queue/index, `serve.meta`, `pm-state.md`) are all covered
 * by `INFRA_BASENAMES`.
 *
 * T-17c (C-36 fifth class): "declared but not on disk" is not a write. The T-16
 * terminal named four unrecorded writes; all four were false positives, two of
 * them new shapes — `update_index.py` (a ghost file name harvested from code
 * text the report quoted) and `os.replace` (a Python identifier, seven
 * occurrences in `conductor.py`, never a path). The judgement is a filesystem
 * FACT, not a token shape: a worker cannot write a file that does not exist, so
 * a declared-but-unrecorded path with no file/directory on disk is excluded
 * from `extra` and surfaced warn-only (`ChangeLedger.unresolvable`, the
 * `## Ledger Unresolvable` product section + a `[FLOW] ledger-unresolvable`
 * trace line), exactly like T-17b's infra class. Shape heuristics are explicitly
 * forbidden here — `os.replace` is shape-identical to a real dotless basename
 * declaration, and mtime cannot attribute a write (T-17b); existence is the
 * only sound discriminator. The P-03 counterweight is unchanged: a real
 * out-of-scope write leaves an existing file, so a declared existing
 * non-infrastructure path the trace never recorded still lands in `extra`.
 */
/** Machine event marker. One line per successful write, `path=` is the only
 * field (a path may contain spaces, so the value runs to end of line). */
export declare const WRITE_FILE_EVENT = "[WRITE_FILE]";
/** The single source of the event grammar: producers format with this, the
 * parser below reads it back. */
export declare function formatWriteFileEvent(filePath: string): string;
/** Best-effort append of one `[WRITE_FILE]` event. A trace write failure must
 * never break the write itself (same contract as every other trace helper), and
 * "failed write ⇒ no event" is enforced by the caller only calling this after
 * success. */
export declare function appendWriteFileEvent(tracePath: string, filePath: string): void;
/** AC-017/T-02: a shell write verb whose target cannot be statically resolved
 * (`$VAR` with no literal binding, a glob, an opaque placeholder) is stated as
 * this event instead of a `[WRITE_FILE]`. It is an explicit "a write happened,
 * path unknown" record — NOT a recorded path: the reconciliation reads
 * `[WRITE_FILE]` only, so this line can never fake a write, and the
 * `unjudgeable` gate ("zero usable `[WRITE_FILE]` events") is not closed by it.
 * Before this split the producer wrote every extracted target, resolved or not,
 * as `[WRITE_FILE]`; a mis-lexed here-string body then entered the ledger as a
 * valid path. */
export declare const UNRESOLVED_WRITE_EVENT = "[WRITE_UNRESOLVED]";
/** The single source of the unresolved-event grammar (mirrors
 * {@link formatWriteFileEvent}). */
export declare function formatUnresolvedWriteEvent(pattern: string, target: string): string;
/** Best-effort append of one `[WRITE_UNRESOLVED]` event (same contract as
 * {@link appendWriteFileEvent}: a trace write failure never breaks the caller). */
export declare function appendUnresolvedWriteEvent(tracePath: string, pattern: string, target: string): void;
/** One parsed `[WRITE_UNRESOLVED]` line. */
export interface UnresolvedWriteEvent {
    pattern: string;
    target: string;
}
/** Unresolved write statements, in file order. Never throws; a malformed line
 * is skipped, and a `[WRITE_FILE]` line never matches (the two grammars are
 * distinct, so a legacy consumer of `parseWriteFileEvents` ignores these). */
export declare function parseUnresolvedWriteEvents(traceText: string): UnresolvedWriteEvent[];
/** The repo-relative form of `target` when it sits under `base` (default: the
 * worker's cwd, which the launcher sets to the project root); otherwise the
 * path unchanged. Emitting a repo-relative path keeps the trace portable
 * across drives, while a foreign/absolute path stays a truthful record. */
export declare function repoRelativePath(target: string, base?: string): string;
/** Recorded write paths, in file order, de-duplicated. Never throws. */
export declare function parseWriteFileEvents(traceText: string): string[];
/** Roles with no `write`/`edit` tool (`worker-mode.ts::isWritelessRole`, which
 * this leaf module cannot import without a cycle). Kept as the ledger's own
 * classification; the T-17 regression test locks the set against the runtime
 * allowlist so the two cannot drift (P-08 single source by test). */
export declare const WRITELESS_LEDGER_ROLES: ReadonlySet<string>;
/** Is `role` a writeless task type (C-36a role split)? */
export declare function isWritelessLedgerRole(role: string | undefined): boolean;
/**
 * T-17b (C-36 fourth class): framework-owned infrastructure writes.
 *
 * A worker's report routinely names files the FRAMEWORK writes — the queue
 * ledger, the index, the worker's own run record / trace / product, the PM's
 * state mirror. Their mtimes naturally fall inside (or just after) the worker's
 * run window: `_workers.parallel` is appended by the launcher while the worker
 * runs, and the queue file may be rewritten again after it exits. An mtime
 * window therefore CANNOT attribute a write — the only sound discriminator is
 * OWNERSHIP, i.e. this static table of files the framework writes itself.
 *
 * The T-12 live incident made the defect concrete: `mwgal-t12-stage-close-auto`
 * (coding) was charged `未记录写入：_workers.parallel` although its `trace.log`
 * contains ZERO `_workers.parallel` hits, the file exists, and its mtime
 * (19:23:30 local) is AFTER the worker's run window (19:07–19:20 local) — it is
 * the launcher's queue, not the worker's write.
 *
 * Entries are matched by basename (case-folded) or, for the conductor/launcher
 * state trees, by path segment. Every entry names the producing side:
 *   - `_workers.parallel` / `_workers.stale.parallel` — `shared/worker-store.ts:152`
 *     (`WorkerStore`), the Python launcher and conductor
 *     (`packages/multi-workers/mw_common.py`); queue rows are appended outside
 *     any worker process.
 *   - `_index.parallel` / `_index.md` — `shared/index-store.ts:334`/`:530`
 *     (`IndexStore`), `update_index.py`/`advance_phase.py`.
 *   - `task.md` — dispatched by the PM before the worker starts
 *     (`pm/ui-bridge.ts::writeDispatchTaskMd`).
 *   - `run.json` — `shared/run-store.ts::writeRunState` (the worker's own run
 *     identity; the Python launcher may only add `lost`, `mw_common.mark_run_lost`).
 *   - `trace.log` — `worker/output-writer.ts` (`appendTrace`,
 *     `appendLifecycleLine`, `appendHeartbeat`), `shared/change-ledger.ts`
 *     (`appendWriteFileEvent`), `worker/worker-mode.ts`.
 *   - `output.md` — `worker/output-writer.ts::writeOutput`.
 *   - `report.md` / `report-<slug>.md` / `progress.md` — the `worker_file`
 *     channel (`worker/worker-file-tool.ts`), the harness product contract.
 *   - `phase-<n>.md` — `worker/phase-runner.ts::writePhaseFile`.
 *   - `stage-<n>*.md` — the key's stage products (`shared/run-store.ts::collectArtifacts`).
 *   - `worker.log` — the launcher's stdout redirect (`worker/worker-mode.ts:567`,
 *     `pm/ui-bridge.ts::FRAMEWORK_TASK_BASENAMES`).
 *   - `serve.meta` — `mw serve` startup (`shared/mw-runner.ts:219`).
 *   - `pm-state.md` — the PM's key mirror (`pm/ui-bridge.ts:1006`).
 *
 * T-21 R-1: the conductor's `_autopilot/**` tree (`_roadmap.md`, `timeline.jsonl`,
 * `auto-decisions.jsonl`, `gates/**`, `tickets/**`, `xkey/ledger.json`) and the
 * launcher's `.mw/**` locks/pids are deliberately NOT here. They are written
 * only by the conductor / `mw serve` (`shared/xkey-gate-guard.ts:39`), so a
 * worker declaring one of them is exactly the C-37 out-of-scope signal the
 * ledger exists to surface (QG R-1 counterexample: a coding worker answering
 * its own `_autopilot/gates/gate-0007.md`). Exempting them by path segment
 * would silently warn-only that write and, with it, the R-6 shadow-history
 * forgery chain. A bare `auto-decisions.jsonl` stays non-infra for the same
 * reason — and it keeps the T-17 writeless survey verdict (a READ reference,
 * C-36a) byte-identical.
 *
 * These paths are excluded from the coding `extra` judgement and surfaced on a
 * warn-only channel instead (`TerminalGaps.infraFiles`, `## Ledger Infra`), so
 * the suppression is visible and never falsifying. The P-03 counterweight is
 * unchanged: a declared NON-infrastructure repo path the trace never recorded
 * stays red.
 */
export declare const INFRA_BASENAMES: ReadonlySet<string>;
/** Is `filePath` a framework-owned infrastructure path (T-17b, narrowed to
 * file level by T-21 R-1)? Case-folded: a Windows worktree spells the same file
 * with a different case. Only the basename participates — no directory inside
 * the path can exempt a file, so `_autopilot/**` and `.mw/**` are judgeable. */
export declare function isInfrastructurePath(filePath: string): boolean;
/** Options shared by the ledger extractors. */
export interface LedgerOptions {
    /** Root the T-25 dotless existence arbitration resolves against. Defaults to
     * `process.cwd()` — the launcher starts every worker with `cwd` set to the
     * project root, so a repo-relative declaration resolves against the repo. */
    projectRoot?: string;
    /** Task role from the `task.md` header `type:` (T-17/AC-004). When it is a
     * writeless role, the ledger judges only the task's declared deliverable and
     * explicit write declarations; every other path in the report is a read
     * reference (C-36a). Omitted ⇒ the historical all-roles behaviour, byte for
     * byte (unit callers and legacy books). */
    role?: string;
    /** Absolute path of the worker's key `evidence/` tree — the writeless
     * deliverable channel (C-36b). Only references that resolve under it are
     * candidate deliverables; references to other keys/repos stay read
     * references. */
    deliverableDir?: string;
    /** Epoch ms the run started (`run.json.started_at`). A deliverable whose
     * mtime predates the run is a pre-existing read reference, not this run's
     * product (C-36b anti-forgery). Omitted ⇒ existence is enough. */
    runStartedAtMs?: number;
}
/** Remove every non-declarative span from report text (T-21 requirement 4): the
 * marker contract sections, all HTML comments, and fenced code blocks. The
 * fence strip is line-based so an unterminated fence drops to EOF rather than
 * leaking its diff/regex lines as declarations. */
export declare function stripNonDeclarativeSpans(text: string): string;
/** Malformed candidates of a report's ledger section (T-21 requirement 4):
 * tokens that look path-shaped (carry a separator) but fail the whitelist.
 * Warn-only — never part of the `declared \ recorded` judgement. Exported so
 * the caller/diagnostics can count them without widening {@link ChangeLedger}. */
export declare function collectMalformedCandidates(reportText: string): string[];
export interface ChangeLedger {
    /** Files the report's 改动清单 declares at a declaration position, normalized,
     * de-duplicated. T-21: prose references, negated items, fenced/card text and
     * malformed tokens are not declarations (see `collectMalformedCandidates`). */
    declared: string[];
    /** Files the trace records as successfully written, normalized,
     * de-duplicated — plus (writeless roles only) the fresh deliverable files the
     * key's `evidence/` tree verifiably holds, so an outside-taskDir product is
     * reconciled instead of invisible (C-36b). */
    recorded: string[];
    /** declared \ recorded — non-empty means the report claims a file the trace
     * never saw written (AC-004 red). Empty when the trace carries no
     * `[WRITE_FILE]` line at all (migration compatibility). Framework-owned
     * infrastructure paths (T-17b) and paths that do not exist on disk (T-17c)
     * are EXCLUDED here and reported in `infra` / `unresolvable`. */
    extra: string[];
    /** T-17b: declared-but-unrecorded paths that are framework-owned
     * infrastructure (`isInfrastructurePath`). Excluded from `extra` and `ok`,
     * surfaced warn-only (the `## Ledger Infra` product section + a `[FLOW]`
     * trace line) so the suppression is visible instead of silent. */
    infra: string[];
    /** T-17c: declared-but-unrecorded paths with no file/directory on disk
     * (checked against `LedgerOptions.projectRoot`, the worker's cwd in
     * production). Such a path cannot be a write this run performed, so it is
     * excluded from `extra` and `ok` and surfaced warn-only (the
     * `## Ledger Unresolvable` product section + a `[FLOW]` trace line). The
     * discriminator is existence only — never the token's shape. */
    unresolvable: string[];
    /** T-12/F-04: the report declares files but the trace recorded ZERO write
     * events. That trace cannot be judged: it is either a legacy trace (T-05
     * predates it) or a run whose writes all went through an unclassifiable
     * shell command. The caller must mark it — never a clean green, and never a
     * false red on an honest declaration. */
    unjudgeable: boolean;
}
/**
 * Reconcile a report's `改动清单` against the worker's trace.
 *
 * `reportText` is the agent-authored report (report.md / output.md); `traceText`
 * is the full `trace.log`. Pure: text in, verdict out, never throws.
 */
export declare function diffLedger(reportText: string, traceText: string, options?: LedgerOptions): ChangeLedger;
//# sourceMappingURL=change-ledger.d.ts.map