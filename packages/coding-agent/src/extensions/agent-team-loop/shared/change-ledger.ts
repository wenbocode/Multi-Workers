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

import * as fs from "node:fs";
import * as path from "node:path";

/** Machine event marker. One line per successful write, `path=` is the only
 * field (a path may contain spaces, so the value runs to end of line). */
export const WRITE_FILE_EVENT = "[WRITE_FILE]";

/** The single source of the event grammar: producers format with this, the
 * parser below reads it back. */
export function formatWriteFileEvent(filePath: string): string {
	return `${WRITE_FILE_EVENT} path=${filePath}`;
}

/** Best-effort append of one `[WRITE_FILE]` event. A trace write failure must
 * never break the write itself (same contract as every other trace helper), and
 * "failed write ⇒ no event" is enforced by the caller only calling this after
 * success. */
export function appendWriteFileEvent(tracePath: string, filePath: string): void {
	try {
		fs.mkdirSync(path.dirname(tracePath), { recursive: true });
		fs.appendFileSync(tracePath, `${formatWriteFileEvent(filePath)}\n`, "utf8");
	} catch {
		// Diagnostic append — best effort.
	}
}

/** One anchored line of the trace: `[WRITE_FILE] path=<path>`. The `[` is
 * escaped so no other bracketed event can match; `(.+)` keeps spaces in the
 * value. */
const WRITE_FILE_LINE_RE = /^\[WRITE_FILE\][ \t]+path=(.+?)[ \t]*$/;

/** AC-017/T-02: a shell write verb whose target cannot be statically resolved
 * (`$VAR` with no literal binding, a glob, an opaque placeholder) is stated as
 * this event instead of a `[WRITE_FILE]`. It is an explicit "a write happened,
 * path unknown" record — NOT a recorded path: the reconciliation reads
 * `[WRITE_FILE]` only, so this line can never fake a write, and the
 * `unjudgeable` gate ("zero usable `[WRITE_FILE]` events") is not closed by it.
 * Before this split the producer wrote every extracted target, resolved or not,
 * as `[WRITE_FILE]`; a mis-lexed here-string body then entered the ledger as a
 * valid path. */
export const UNRESOLVED_WRITE_EVENT = "[WRITE_UNRESOLVED]";

/** Fold CR/LF and other control characters to the two-character `\\n` text so an
 * unresolved target can never split the event across physical trace lines (the
 * measured footgun of the old unconditional recorder: a `\n`-bearing target
 * wrote a truncated event plus junk continuation lines). */
function oneLine(value: string): string {
	return value.replace(/[\r\n\u0000-\u001f]+/g, "\\n");
}

/** The single source of the unresolved-event grammar (mirrors
 * {@link formatWriteFileEvent}). */
export function formatUnresolvedWriteEvent(pattern: string, target: string): string {
	return `${UNRESOLVED_WRITE_EVENT} pattern=${pattern} target=${oneLine(target)}`;
}

/** Best-effort append of one `[WRITE_UNRESOLVED]` event (same contract as
 * {@link appendWriteFileEvent}: a trace write failure never breaks the caller). */
export function appendUnresolvedWriteEvent(tracePath: string, pattern: string, target: string): void {
	try {
		fs.mkdirSync(path.dirname(tracePath), { recursive: true });
		fs.appendFileSync(tracePath, `${formatUnresolvedWriteEvent(pattern, target)}\n`, "utf8");
	} catch {
		// Diagnostic append — best effort.
	}
}

/** One parsed `[WRITE_UNRESOLVED]` line. */
export interface UnresolvedWriteEvent {
	pattern: string;
	target: string;
}

/** `[WRITE_UNRESOLVED] pattern=<label> target=<one-line>`; the pattern is a
 * single token, the target runs to end of line (it may contain spaces). */
const UNRESOLVED_WRITE_LINE_RE = /^\[WRITE_UNRESOLVED\][ \t]+pattern=(\S+)[ \t]+target=(.*)$/;

/** Unresolved write statements, in file order. Never throws; a malformed line
 * is skipped, and a `[WRITE_FILE]` line never matches (the two grammars are
 * distinct, so a legacy consumer of `parseWriteFileEvents` ignores these). */
export function parseUnresolvedWriteEvents(traceText: string): UnresolvedWriteEvent[] {
	const out: UnresolvedWriteEvent[] = [];
	for (const line of traceText.split(/\r?\n/)) {
		const match = UNRESOLVED_WRITE_LINE_RE.exec(line);
		if (match === null) continue;
		out.push({ pattern: match[1], target: match[2] });
	}
	return out;
}

/** Is a parsed `[WRITE_FILE]` path a *usable* recorded event (AC-017(d))?
 * The producer only emits a normalized path for a statically resolved target,
 * so a machine event is a repo path token; a historical junk event from the
 * pre-AC-017 recorder (`` `:1175 ``, `, .agenticdoc/_aut + opilot)`) is not one.
 * Before this predicate any single garbage line closed the `unjudgeable` gate
 * and could flip a run green. Shape is used here ONLY to withhold event
 * validity (an unusable event makes the run *unjudgeable*, never a recorded
 * write) — the positive signal (the write verb) is upstream in the extractor,
 * so R9's "never shape alone" holds. */
function isRecordedEventUsable(filePath: string, projectRoot?: string): boolean {
	if (filePath === "") return false;
	if (isPathCandidate(filePath)) return true;
	return isExistingDotlessCandidate(filePath, projectRoot);
}

/** The repo-relative form of `target` when it sits under `base` (default: the
 * worker's cwd, which the launcher sets to the project root); otherwise the
 * path unchanged. Emitting a repo-relative path keeps the trace portable
 * across drives, while a foreign/absolute path stays a truthful record. */
export function repoRelativePath(target: string, base: string = process.cwd()): string {
	const rel = path.relative(base, target);
	if (rel === "" || rel.startsWith("..") || path.isAbsolute(rel)) return normalizePath(target);
	return normalizePath(rel);
}

/** Recorded write paths, in file order, de-duplicated. Never throws. */
export function parseWriteFileEvents(traceText: string): string[] {
	const out: string[] = [];
	const seen = new Set<string>();
	for (const line of traceText.split(/\r?\n/)) {
		const match = WRITE_FILE_LINE_RE.exec(line);
		if (match === null) continue;
		const value = normalizePath(match[1]);
		if (value === "" || seen.has(value)) continue;
		seen.add(value);
		out.push(value);
	}
	return out;
}

/** Normalize a path for comparison: forward slashes, no `./`, no trailing
 * slash, no doubled separators. Never touches case (see `samePath`). */
function normalizePath(raw: string): string {
	return raw
		.trim()
		.replace(/\\/g, "/")
		.replace(/\/{2,}/g, "/")
		.replace(/^\.\//, "")
		.replace(/\/+$/, "");
}

/** Does a declared path name the recorded file? Exact match, case-insensitive
 * match (Windows worktrees), or a full-segment suffix match — the reporter
 * writes a repo-relative path while the trace may carry an absolute one (or the
 * reverse). The `/`-boundary is required, so `worker-mode.ts` never matches
 * `mode.ts`. */
function samePath(declared: string, recorded: string): boolean {
	if (declared === recorded) return true;
	const a = declared.toLowerCase();
	const b = recorded.toLowerCase();
	if (a === b) return true;
	return a.endsWith(`/${b}`) || b.endsWith(`/${a}`);
}

/** Section aliases, broad-档 in the same spirit as `worker/output-sections.ts`
 * (a report heading is authored by a human/model, so heading-shape strictness
 * would over-block). Keep in sync with the recovery contract's `改动清单`
 * aliases — this module must not become a second, narrower oracle. */
const LEDGER_SECTION_ALIASES = [
	"改动清单",
	"变更清单",
	"改动历史",
	"变更历史",
	"changed files",
	"files changed",
	"改动",
	"变更",
	"修改文件",
];

/** Narrow ledger aliases for writeless roles (C-36a). The broad
 * `改动`/`变更` aliases match any prose heading that merely *mentions* the
 * concept (`结论 6｜可度量：改动前后的期望变化…`), which turned a whole survey
 * section into a declaration body and charged the reader's references as
 * writes (T-08: `l3-verdict.txt`/`auto-decisions.jsonl`/`gates.pending`). A
 * writeless role only declares from a real change-list heading. */
const WRITELESS_LEDGER_ALIASES = [
	"改动清单",
	"变更清单",
	"改动历史",
	"变更历史",
	"修改清单",
	"修改文件",
	"changed files",
	"files changed",
];

/** Roles with no `write`/`edit` tool (`worker-mode.ts::isWritelessRole`, which
 * this leaf module cannot import without a cycle). Kept as the ledger's own
 * classification; the T-17 regression test locks the set against the runtime
 * allowlist so the two cannot drift (P-08 single source by test). */
export const WRITELESS_LEDGER_ROLES: ReadonlySet<string> = new Set([
	"research",
	"review",
	"verifier",
	"reviewer",
	"rag-research",
]);

/** Is `role` a writeless task type (C-36a role split)? */
export function isWritelessLedgerRole(role: string | undefined): boolean {
	return role !== undefined && WRITELESS_LEDGER_ROLES.has(role);
}

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
export const INFRA_BASENAMES: ReadonlySet<string> = new Set([
	"_workers.parallel",
	"_workers.stale.parallel",
	"_index.parallel",
	"_index.md",
	"task.md",
	"run.json",
	"trace.log",
	"output.md",
	"report.md",
	"progress.md",
	"worker.log",
	"serve.meta",
	"pm-state.md",
]);

/** Framework-generated basenames with a suffix: the `worker_file` report
 * channel `report-<slug>.md` and the phase/stage products `collectArtifacts`
 * already enumerates. T-21 R-1 keeps every exemption FILE-level, so the
 * conductor's timeline rotations (`timeline.jsonl.<n>`) are no longer matched
 * by a path segment and are judged like any other declared path. */
const INFRA_BASENAME_RES: readonly RegExp[] = [/^report-.+\.md$/, /^phase-.+\.md$/, /^stage-\d+.*\.md$/];

/** Is `filePath` a framework-owned infrastructure path (T-17b, narrowed to
 * file level by T-21 R-1)? Case-folded: a Windows worktree spells the same file
 * with a different case. Only the basename participates — no directory inside
 * the path can exempt a file, so `_autopilot/**` and `.mw/**` are judgeable. */
export function isInfrastructurePath(filePath: string): boolean {
	const normalized = normalizePath(filePath).toLowerCase();
	if (normalized === "") return false;
	const base = normalized.slice(normalized.lastIndexOf("/") + 1);
	if (INFRA_BASENAMES.has(base)) return true;
	return INFRA_BASENAME_RES.some((re) => re.test(base));
}

/** `$VAR` / `${VAR}` / `$1` / `%VAR%` residue: a shell variable that was never
 * expanded (C-36c). Never a path, never part of a judgement — warn-only. */
const UNEXPANDED_VARIABLE_RE = /\$(?:\{[A-Za-z_][A-Za-z0-9_]*\}|[A-Za-z_][A-Za-z0-9_]*|[0-9])|%[A-Za-z_][A-Za-z0-9_]*%/;

function hasUnexpandedVariable(token: string): boolean {
	return UNEXPANDED_VARIABLE_RE.test(token);
}

/** A heading line (ATX): capture 1 is the `#` run (the level), capture 2 the
 * title. */
const HEADING_RE = /^\s*(#{1,6})\s+(.*)$/;

/** Section-number / list prefix a report may put before a section name
 * (`### 7. 类型检查与改动面`, `- 改动清单`, `（1）变更清单`). Stripped before the
 * alias comparison so the number cannot shadow the anchor. */
const HEADING_PREFIX_RE = /^(?:\d+[.、)）]\s*|[（(]\s*\d+\s*[)）]\s*|[-*+]\s+|第\s*\d+\s*[章节]?\s*[.、]?\s*)+/;

/** Clause separators inside a heading. The T-21 QG corpus heading
 * `### 结论 6｜可度量：改动前后的期望变化…` declares via a clause, not the title
 * head (`mwgal-t21-qg-fixes.test.ts` locks that verdict). */
const TITLE_CLAUSE_RE = /[：:｜|]/;

/** ASCII-only lower-case fold: heading and alias are compared in one case
 * class, and the CJK bytes must not be touched by a locale fold. */
function asciiLower(text: string): string {
	return text.replace(/[A-Z]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) + 32));
}

/** Is `line` the report's declaration (change-list) section heading?
 *
 * T-11: the level-1 title is the report's own title, never a section — a real
 * event's `# T-02 · 变更账本抽取器加固…` matched the broad `变更` alias and
 * turned the document header (`card:` line, `目标锚点：.agenticdoc/goal.md`)
 * into a declaration body. Only level >= 2 participates. The alias is then
 * anchored: after stripping the section-number/list prefix, folding case and
 * collapsing whitespace, it must start the title or one of its `：`/`｜`
 * clauses. `includes` is gone, so `### 7. 类型检查与改动面` no longer matches,
 * while `## 改动清单（本卡写面）` and `## 变更清单` still do. */
function isLedgerHeading(line: string, aliases: readonly string[] = LEDGER_SECTION_ALIASES): boolean {
	const heading = HEADING_RE.exec(line);
	if (heading === null) return false;
	if (heading[1].length < 2) return false; // H1 is the document title, not a section
	const title = asciiLower(heading[2].replace(HEADING_PREFIX_RE, "").replace(/\s+/g, " ").trim());
	if (title === "") return false;
	const clauses = title.split(TITLE_CLAUSE_RE).map((clause) => clause.trim());
	return aliases.some((alias) => {
		const needle = asciiLower(alias);
		return clauses.some((clause) => clause.startsWith(needle));
	});
}

/** Section body of the `改动清单` block: from the heading to the next heading.
 * Empty when the text carries no such heading — a report that lists no files
 * declares nothing, which is `⊆`-satisfiable by definition. */
function extractLedgerBody(reportText: string, aliases: readonly string[] = LEDGER_SECTION_ALIASES): string {
	const lines = reportText.split(/\r?\n/);
	let start = -1;
	for (let i = 0; i < lines.length; i++) {
		if (isLedgerHeading(lines[i], aliases)) {
			start = i + 1;
			break;
		}
	}
	if (start === -1) return "";
	const body: string[] = [];
	for (let i = start; i < lines.length; i++) {
		if (HEADING_RE.test(lines[i])) break;
		body.push(lines[i]);
	}
	return body.join("\n");
}

/** Candidate token boundaries: whitespace plus the punctuation that separates a
 * path from its annotation in a markdown bullet (`- src/a.ts — intent`). Braces
 * stay inside the token so an unexpanded `${VAR}/x.ts` is ONE malformed
 * candidate instead of a `$` plus a phantom `/x.ts` declaration (C-36c). */
const TOKEN_SPLIT_RE = /[^\s`"'()[\]<>,;，；：、]+/g;

/** Basename channel (T-02 lesson): a `name.ext` token with no separator. No
 * extension enumeration — a new file type must not need a code change. */
const BASENAME_WITH_EXT_RE = /^[^/\s]+\.[A-Za-z][A-Za-z0-9]{0,7}$/;

/** Whitelist shape of a repo path (T-21 requirement 4): optional Windows drive
 * prefix, `/`-separated segments of `[A-Za-z0-9._-]`. Everything else — `* ^ $
 * ` | : （）`, CJK prose, a raw `\n` escape — makes the token a *malformed*
 * candidate (warn-only), never a declaration. Backslashes are refused: a
 * declared path must be repo-relative/forward-slashed, and `\n`/`\s` escape
 * residue would otherwise normalize into a fake `/n`/`/s` path. */
const PATH_SHAPE_RE = /^(?:[A-Za-z]:)?\/?(?:[A-Za-z0-9._-]+\/)*[A-Za-z0-9._-]+\/?$/;

/** Shape judge: is `token` a declaration-shaped path (T-21 requirement 4)?
 * A separator-bearing token must end in a dotted basename, so the English word
 * pairs the task book called out (`host/pid`, `notice/refusal`) are refused. */
function isPathCandidate(token: string): boolean {
	if (token.startsWith("-")) return false;
	if (token.includes("://")) return false;
	if (token.includes("\\")) return false;
	if (!PATH_SHAPE_RE.test(token)) return false;
	const trimmed = token.replace(/\/+$/, "");
	if (trimmed.includes("/")) {
		const base = trimmed.slice(trimmed.lastIndexOf("/") + 1);
		return base.includes(".");
	}
	return BASENAME_WITH_EXT_RE.test(trimmed);
}

/** Path-intent signal for the malformed bucket: the token wants to be a path
 * (it carries a separator) but fails the shape whitelist. */
function isSeparatorBearing(token: string): boolean {
	return token.includes("/") || token.includes("\\");
}

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

/** Case-insensitive `target === base | target below base` over resolved paths. */
function isUnder(base: string, target: string): boolean {
	const clean = (p: string): string => path.resolve(p).replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase();
	const b = clean(base);
	const t = clean(target);
	return t === b || t.startsWith(`${b}/`);
}

/** Resolve a report token to an existing file under the key's `evidence/` tree
 * (C-36b). Accepts the three forms the reports actually use: absolute, repo
 * relative (`.agenticdoc/<key>/evidence/…`) and key relative
 * (`evidence/research/…`). Variable residue and out-of-tree paths never
 * resolve. */
function resolveDeliverablePath(token: string, projectRoot: string, deliverableDir: string): string | undefined {
	if (hasUnexpandedVariable(token)) return undefined;
	// A trailing full-width annotation glued to the path (`…/x.md（本文件）`) is
	// prose, not part of the file name.
	const stripped = token.replace(/[（(][^（）()]*[）)]$/, "");
	const forms = stripped === token || stripped === "" ? [token] : [stripped, token];
	const keyDir = path.dirname(deliverableDir);
	for (const form of forms) {
		const candidates = path.isAbsolute(form) ? [form] : [path.resolve(projectRoot, form), path.resolve(keyDir, form)];
		for (const candidate of candidates) {
			if (!isUnder(deliverableDir, candidate)) continue;
			try {
				if (fs.statSync(candidate).isFile()) return candidate;
			} catch {
				// Not on disk — not a deliverable.
			}
		}
	}
	return undefined;
}

/** Is a resolved deliverable fresh enough to be *this* run's product? */
function isFreshDeliverable(abs: string, runStartedAtMs: number | undefined): boolean {
	if (runStartedAtMs === undefined || !Number.isFinite(runStartedAtMs)) return true;
	try {
		return fs.statSync(abs).mtimeMs >= runStartedAtMs;
	} catch {
		return false;
	}
}

/** Explicit write-verb declarations are extracted at declaration positions
 * (T-21). `DECLARATION_VERB_RE` has no word boundary of its own because the
 * CJK alternatives must match mid-sentence; a prose line whose target is a
 * real file still declares here. The English alternatives must not match
 * inside a longer identifier — `gate-writer.ts` used to yield a bogus `r.ts`
 * declaration. */
function verbEndsAtWordBoundary(line: string, end: number): boolean {
	const next = line[end];
	return next === undefined || !/[A-Za-z0-9_]/.test(next);
}

/** Writeless-role declaration set (C-36a/C-36b): the task's deliverable —
 * every fresh file under the key's `evidence/` tree the report references —
 * plus the narrow change-list declarations. Read references (surveyed paths,
 * other keys, `/tmp` files) are dropped. The fresh deliverables are the
 * recorded side of the disk channel. */
function collectWritelessDeclarations(
	reportText: string,
	options: LedgerOptions,
): { declared: string[]; delivered: string[] } {
	const declared: string[] = [];
	const delivered: string[] = [];
	const projectRoot = options.projectRoot ?? process.cwd();
	if (options.deliverableDir !== undefined) {
		const deliverableDir = path.resolve(options.deliverableDir);
		for (const line of reportText.split(/\r?\n/)) {
			for (const token of lineTokens(line)) {
				const abs = resolveDeliverablePath(token, projectRoot, deliverableDir);
				if (abs === undefined || !isFreshDeliverable(abs, options.runStartedAtMs)) continue;
				const rel = repoRelativePath(abs, projectRoot);
				if (!declared.includes(rel)) declared.push(rel);
				if (!delivered.includes(rel)) delivered.push(rel);
			}
		}
	}
	const body = extractLedgerBody(reportText, WRITELESS_LEDGER_ALIASES);
	for (const file of collectDeclared(body, options.projectRoot)) {
		if (!declared.includes(file)) declared.push(file);
	}
	return { declared, delivered };
}

/** Does `token` name something real on disk (file OR directory)? Read-only and
 * best-effort: an absent/unreadable root is "not found", never an error. The
 * T-17c existence discriminator for the declared-but-unrecorded set (and the
 * T-25 dotless arbitration) both read the filesystem through this one probe. */
function existsOnDisk(token: string, projectRoot?: string): boolean {
	try {
		return fs.existsSync(path.resolve(projectRoot ?? process.cwd(), token));
	} catch {
		return false;
	}
}

/** T-25 existence arbitration for the dotless case.
 *
 * The T-21 shape whitelist refuses a separator-bearing token whose basename has
 * no `.`, so the English word pairs the task book called out (`host/pid`,
 * `notice/refusal`) are not declarations. That heuristic also drops real
 * extensionless files (`scripts/deploy`), which then vanish from `declared` —
 * a genuine out-of-scope declaration the trace never recorded went undetected.
 * Give the shape gate a second chance: a token that passes *every other* shape
 * rule and names an existing file/directory is a declaration. It stays in
 * `collectMalformedCandidates` (warn-only diagnostics keep the shape signal).
 * A nonexistent token (`host/pid`) keeps the old behaviour. */
function isExistingDotlessCandidate(token: string, projectRoot?: string): boolean {
	if (isPathCandidate(token)) return false;
	if (!isSeparatorBearing(token)) return false;
	if (!PATH_SHAPE_RE.test(token)) return false;
	const trimmed = token.replace(/\/+$/, "");
	const base = trimmed.slice(trimmed.lastIndexOf("/") + 1);
	if (base.includes(".")) return false;
	return existsOnDisk(trimmed, projectRoot);
}

/** Tokens of a line, in order, with a trailing sentence full stop dropped (a
 * filename ending in `.` is invalid on Windows, so `- src/a.ts.` keeps matching
 * a declared `src/a.ts`). */
function lineTokens(line: string): string[] {
	const out: string[] = [];
	for (const match of line.matchAll(TOKEN_SPLIT_RE)) {
		const token = match[0].replace(/[.。]+$/, "");
		if (token === "") continue;
		out.push(token);
	}
	return out;
}

/** Marker-delimited framework contract sections (write surface, dispatch card).
 * They are HTML-comment-delimited, but their BODY is plain markdown; strip the
 * whole span so a contract quoted into a report cannot declare anything. */
const CONTRACT_SECTION_RES: readonly RegExp[] = [
	/<!--\s*mw-write-surface: v1\s*-->[\s\S]*?<!--\s*\/mw-write-surface: v1\s*-->/g,
	/<!--\s*mw-dispatch-card: v1\s*-->[\s\S]*?<!--\s*\/mw-dispatch-card: v1\s*-->/g,
];
const HTML_COMMENT_RE = /<!--[\s\S]*?-->/g;
const FENCE_OPEN_RE = /^[ \t]*(`{3,}|~{3,})/;

/** Remove every non-declarative span from report text (T-21 requirement 4): the
 * marker contract sections, all HTML comments, and fenced code blocks. The
 * fence strip is line-based so an unterminated fence drops to EOF rather than
 * leaking its diff/regex lines as declarations. */
export function stripNonDeclarativeSpans(text: string): string {
	let out = text;
	for (const re of CONTRACT_SECTION_RES) out = out.replace(re, "");
	out = out.replace(HTML_COMMENT_RE, "");
	const lines: string[] = [];
	let fence: string | null = null;
	for (const line of out.split(/\r?\n/)) {
		const open = FENCE_OPEN_RE.exec(line);
		if (fence === null) {
			if (open !== null) {
				fence = open[1][0];
				continue;
			}
			lines.push(line);
			continue;
		}
		if (open !== null && open[1][0] === fence) fence = null;
	}
	return lines.join("\n");
}

/** Prefix negation markers (T-21 requirement 2): they negate whatever follows
 * them in the same declaration item. Kept as explicit compounds — a bare `未`
 * or `不` would over-negate honest `未改 A、新增 B` lines. */
const NEGATION_PREFIX_MARKERS: readonly string[] = [
	"未写入",
	"未写",
	"未记录",
	"未改",
	"未修改",
	"未新增",
	"未删除",
	"未触碰",
	"未碰",
	"未动",
	"未做",
	"未重建",
	"未涉及",
	"不涉及",
	"不写",
	"不改",
	"不动",
	"不需要改",
	"无需",
	"禁止",
	"不得",
	"不准",
	"勿",
	"没有",
	"无",
	"not written",
	"not modified",
	"not changed",
	"not touched",
	"unchanged",
	"untouched",
	"forbidden",
	"must not",
	"do not",
	"don't",
	"never",
	"no changes",
	"unrecorded",
];

/** No-change markers that also negate a declaration when they FOLLOW it in the
 * same item — the `| path | **未改** |` / `` path **未改**：`` shapes. Only the
 * unambiguous no-change vocabulary, never a generic suffix word. */
const NEGATION_SUFFIX_MARKERS: readonly string[] = [
	"未写入",
	"未记录",
	"未改",
	"未修改",
	"未新增",
	"未删除",
	"未触碰",
	"未碰",
	"未动",
	"未做",
	"未重建",
	"不改",
	"unchanged",
	"untouched",
	"not changed",
	"not modified",
	"no changes",
	"unrecorded",
];

/** Is `token` negated INSIDE `scope` (one list item / table row / sentence)?
 * Prefix markers negate forward; no-change markers also negate backward. The
 * scope is always the item, never the report — requirement 2 forbids a coarse
 * "the report contains 禁止 ⇒ everything is exempt". */
function isNegatedInScope(scope: string, token: string): boolean {
	const at = scope.indexOf(token);
	if (at === -1) return false;
	const low = scope.toLowerCase();
	const before = low.slice(0, at);
	const after = low.slice(at + token.length);
	if (NEGATION_PREFIX_MARKERS.some((marker) => before.includes(marker))) return true;
	return NEGATION_SUFFIX_MARKERS.some((marker) => after.includes(marker));
}

/** A markdown table row (`| a | b |`). */
const TABLE_ROW_RE = /^\s*\|.*\|\s*$/;
/** A list item: bullet or ordered marker, with its indentation captured. */
const LIST_ITEM_RE = /^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$/;
/** Write verbs for prose declarations (`修改了 src/a.ts`, `wrote src/a.ts`). */
const DECLARATION_VERB_RE =
	/(?:写入到|写入|写到|修改|新建|新增|创建|删除|重命名|wrote|written to|write to|write|edited|edit|created|create|modified|modify|changed|change)/gi;
/** Particles/quoting a verb may be separated from its target by (`修改了 x`). */
const DECLARATION_GAP_RE = /^[\s`"'*：:了到至在，,]*/;

interface DeclarationItem {
	/** Text the declared tokens are read from. */
	declaration: string;
	/** Negation scope: the same list item / table row / sentence. */
	scope: string;
}

/** Declaration items of a ledger body (T-21 requirement 3/4): list-item heads
 * at the body's minimum indentation, table rows, and write-verb-anchored
 * prose. Nested sub-bullets are the parent item's intent detail, not a second
 * declaration — that is where the `import ... from "../config.ts"` / `见
 * task.md` references lived. A body with no structured item falls back to
 * per-line prose so an unstructured ledger is still judged. */
function declarationItems(body: string): DeclarationItem[] {
	const lines = body.split(/\r?\n/);
	let minIndent = Number.POSITIVE_INFINITY;
	for (const line of lines) {
		const li = LIST_ITEM_RE.exec(line);
		if (li !== null) minIndent = Math.min(minIndent, li[1].length);
	}
	const items: DeclarationItem[] = [];
	let structured = false;
	for (const line of lines) {
		if (TABLE_ROW_RE.test(line)) {
			structured = true;
			// One row = one subject: the first shape-valid token anywhere in the row
			// declares (the path column may be first or, in a flipped table, second).
			items.push({ declaration: line, scope: line });
			continue;
		}
		const li = LIST_ITEM_RE.exec(line);
		if (li !== null) {
			if (li[1].length !== minIndent) continue;
			structured = true;
			items.push({ declaration: li[2], scope: line });
			continue;
		}
		// Prose declaration: a write verb anchors the token that follows it.
		for (const match of line.matchAll(DECLARATION_VERB_RE)) {
			const at = (match.index ?? 0) + match[0].length;
			if (!verbEndsAtWordBoundary(line, at)) continue;
			const rest = line.slice(at).replace(DECLARATION_GAP_RE, "");
			const token = lineTokens(rest)[0];
			if (token === undefined) continue;
			structured = true;
			items.push({ declaration: token, scope: line });
			break;
		}
	}
	if (structured) return items;
	return lines.filter((line) => line.trim() !== "").map((line) => ({ declaration: line, scope: line }));
}

/** The declared file set of a ledger body: declaration positions only,
 * shape-gated and negation-aware (T-21 requirements 2-4). One item = one
 * subject: the FIRST shape-valid token declares, the rest is intent prose (a
 * path referenced there — `import ... from "../config.ts"`, `见 task.md` — is
 * not a second declared file). */
function collectDeclared(body: string, projectRoot?: string): string[] {
	const out: string[] = [];
	for (const item of declarationItems(body)) {
		for (const token of lineTokens(item.declaration)) {
			if (!isPathCandidate(token) && !isExistingDotlessCandidate(token, projectRoot)) continue;
			if (isNegatedInScope(item.scope, token)) break;
			out.push(normalizePath(token));
			break;
		}
	}
	return out;
}

/** Malformed candidates of a report's ledger section (T-21 requirement 4):
 * tokens that look path-shaped (carry a separator) but fail the whitelist.
 * Warn-only — never part of the `declared \ recorded` judgement. Exported so
 * the caller/diagnostics can count them without widening {@link ChangeLedger}. */
export function collectMalformedCandidates(reportText: string): string[] {
	const body = extractLedgerBody(stripNonDeclarativeSpans(reportText));
	const out: string[] = [];
	const seen = new Set<string>();
	for (const line of body.split(/\r?\n/)) {
		for (const token of lineTokens(line)) {
			const variable = hasUnexpandedVariable(token);
			if (!isSeparatorBearing(token) && !variable) continue;
			if (!variable && !/[^/\\]/.test(token)) continue; // a lone `/` separator is punctuation, not a candidate
			if (isPathCandidate(token)) continue;
			if (seen.has(token)) continue;
			seen.add(token);
			out.push(token);
		}
	}
	return out;
}

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
export function diffLedger(reportText: string, traceText: string, options?: LedgerOptions): ChangeLedger {
	// Per-worker attribution is structural, not a policy knob: `traceText` is the
	// caller's own trace (worker-mode.ts `readTerminalGaps` reads
	// `<own taskDir>/trace.log`), so no repo-wide `git status`/diff can enter the
	// recorded side and a concurrent worker's files can never be charged here.
	const recordedEvents = parseWriteFileEvents(traceText);
	const stripped = stripNonDeclarativeSpans(reportText);
	let declared: string[];
	let delivered: string[] = [];
	if (isWritelessLedgerRole(options?.role)) {
		// C-36a: a writeless role's survey paths are read references, not write
		// intent. C-36b: its deliverable may live outside taskDir (the key's
		// `evidence/` tree), so a fresh referenced file there is both declared and
		// recorded — the run is judgeable instead of `writes=none`.
		const writeless = collectWritelessDeclarations(stripped, options ?? {});
		declared = dedupe(writeless.declared);
		delivered = writeless.delivered;
	} else {
		const body = extractLedgerBody(stripped);
		declared = dedupe(collectDeclared(body, options?.projectRoot));
	}
	const recorded = dedupe([...recordedEvents, ...delivered]);
	// AC-017(d): the `unjudgeable` gate keys off USABLE events, not the raw line
	// count (a garbage event must not close it). The `delivered` side counts too:
	// a writeless run whose product is verified on disk is judgeable.
	const usableEvents = dedupe(recordedEvents.filter((file) => isRecordedEventUsable(file, options?.projectRoot)));
	// T-17b: split the declared-but-unrecorded set into framework infrastructure
	// (warn-only, never a gap) and genuinely unrecorded worker writes (AC-004
	// red). Ownership, not mtime: every infra file's mtime falls inside a
	// worker's run window, so a window test cannot attribute a write (see
	// INFRA_BASENAMES).
	const unrecorded = declared.filter((file) => !recorded.some((recordedFile) => samePath(file, recordedFile)));
	// T-17c: three-way split of the declared-but-unrecorded set. INFRA wins first
	// (T-17b ownership is name-based and must not regress to "unresolvable" when
	// the framework file is absent from a fixture tree); then the filesystem fact:
	// a path with no file/directory on disk cannot be a write this run made
	// (`update_index.py`, `os.replace`), so it is warn-only, not a gap.
	const infra: string[] = [];
	const unresolvable: string[] = [];
	const judgeable: string[] = [];
	for (const file of unrecorded) {
		if (isInfrastructurePath(file)) infra.push(file);
		else if (existsOnDisk(file, options?.projectRoot)) judgeable.push(file);
		else unresolvable.push(file);
	}
	// Migration / unjudgeable gate: not one recorded event ⇒ this trace could
	// not have recorded anything. T-12/F-04: with a non-empty declaration that
	// is *unjudgeable*, not green — a bash-only run must not bypass the ledger
	// and an honest declaration must not be false-red. With no declaration there
	// is nothing to reconcile, so it is trivially green. An infra-only or
	// unresolvable-only declaration has no real write to reconcile either, so the
	// gate keys off the judgeable (existing, non-infra) declaration set.
	if (usableEvents.length === 0 && delivered.length === 0) {
		return { declared, recorded, extra: [], infra, unresolvable, unjudgeable: judgeable.length > 0 };
	}
	return { declared, recorded, extra: judgeable, infra, unresolvable, unjudgeable: false };
}

function dedupe(values: string[]): string[] {
	const seen = new Set<string>();
	const out: string[] = [];
	for (const value of values) {
		if (seen.has(value)) continue;
		seen.add(value);
		out.push(value);
	}
	return out;
}
