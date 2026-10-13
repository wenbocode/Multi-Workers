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
 * Attribution stays per-worker by construction: the recorded side is only the
 * caller's own `traceText` (the worker's `[WRITE_FILE]` events) — no repo-wide
 * `git status`/diff ever enters this module.
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
/** The repo-relative form of `target` when it sits under `base` (default: the
 * worker's cwd, which the launcher sets to the project root); otherwise the
 * path unchanged. Emitting a repo-relative path keeps the trace portable
 * across drives, while a foreign/absolute path stays a truthful record. */
export declare function repoRelativePath(target: string, base?: string): string;
/** Recorded write paths, in file order, de-duplicated. Never throws. */
export declare function parseWriteFileEvents(traceText: string): string[];
/** Options shared by the ledger extractors. */
export interface LedgerOptions {
    /** Root the T-25 dotless existence arbitration resolves against. Defaults to
     * `process.cwd()` — the launcher starts every worker with `cwd` set to the
     * project root, so a repo-relative declaration resolves against the repo. */
    projectRoot?: string;
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
     * de-duplicated. */
    recorded: string[];
    /** declared \ recorded — non-empty means the report claims a file the trace
     * never saw written (AC-004 red). Empty when the trace carries no
     * `[WRITE_FILE]` line at all (migration compatibility). */
    extra: string[];
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