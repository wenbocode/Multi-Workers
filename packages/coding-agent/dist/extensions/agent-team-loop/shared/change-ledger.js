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
import * as fs from "node:fs";
import * as path from "node:path";
/** Machine event marker. One line per successful write, `path=` is the only
 * field (a path may contain spaces, so the value runs to end of line). */
export const WRITE_FILE_EVENT = "[WRITE_FILE]";
/** The single source of the event grammar: producers format with this, the
 * parser below reads it back. */
export function formatWriteFileEvent(filePath) {
    return `${WRITE_FILE_EVENT} path=${filePath}`;
}
/** Best-effort append of one `[WRITE_FILE]` event. A trace write failure must
 * never break the write itself (same contract as every other trace helper), and
 * "failed write ⇒ no event" is enforced by the caller only calling this after
 * success. */
export function appendWriteFileEvent(tracePath, filePath) {
    try {
        fs.mkdirSync(path.dirname(tracePath), { recursive: true });
        fs.appendFileSync(tracePath, `${formatWriteFileEvent(filePath)}\n`, "utf8");
    }
    catch {
        // Diagnostic append — best effort.
    }
}
/** One anchored line of the trace: `[WRITE_FILE] path=<path>`. The `[` is
 * escaped so no other bracketed event can match; `(.+)` keeps spaces in the
 * value. */
const WRITE_FILE_LINE_RE = /^\[WRITE_FILE\][ \t]+path=(.+?)[ \t]*$/;
/** The repo-relative form of `target` when it sits under `base` (default: the
 * worker's cwd, which the launcher sets to the project root); otherwise the
 * path unchanged. Emitting a repo-relative path keeps the trace portable
 * across drives, while a foreign/absolute path stays a truthful record. */
export function repoRelativePath(target, base = process.cwd()) {
    const rel = path.relative(base, target);
    if (rel === "" || rel.startsWith("..") || path.isAbsolute(rel))
        return normalizePath(target);
    return normalizePath(rel);
}
/** Recorded write paths, in file order, de-duplicated. Never throws. */
export function parseWriteFileEvents(traceText) {
    const out = [];
    const seen = new Set();
    for (const line of traceText.split(/\r?\n/)) {
        const match = WRITE_FILE_LINE_RE.exec(line);
        if (match === null)
            continue;
        const value = normalizePath(match[1]);
        if (value === "" || seen.has(value))
            continue;
        seen.add(value);
        out.push(value);
    }
    return out;
}
/** Normalize a path for comparison: forward slashes, no `./`, no trailing
 * slash, no doubled separators. Never touches case (see `samePath`). */
function normalizePath(raw) {
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
function samePath(declared, recorded) {
    if (declared === recorded)
        return true;
    const a = declared.toLowerCase();
    const b = recorded.toLowerCase();
    if (a === b)
        return true;
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
/** A heading line (ATX). */
const HEADING_RE = /^\s*#{1,6}\s+(.*)$/;
function isLedgerHeading(line) {
    const heading = HEADING_RE.exec(line);
    if (heading === null)
        return false;
    const title = heading[1].toLowerCase();
    return LEDGER_SECTION_ALIASES.some((alias) => title.includes(alias.toLowerCase()));
}
/** Section body of the `改动清单` block: from the heading to the next heading.
 * Empty when the text carries no such heading — a report that lists no files
 * declares nothing, which is `⊆`-satisfiable by definition. */
function extractLedgerBody(reportText) {
    const lines = reportText.split(/\r?\n/);
    let start = -1;
    for (let i = 0; i < lines.length; i++) {
        if (isLedgerHeading(lines[i])) {
            start = i + 1;
            break;
        }
    }
    if (start === -1)
        return "";
    const body = [];
    for (let i = start; i < lines.length; i++) {
        if (HEADING_RE.test(lines[i]))
            break;
        body.push(lines[i]);
    }
    return body.join("\n");
}
/** Candidate token boundaries: whitespace plus the punctuation that separates a
 * path from its annotation in a markdown bullet (`- src/a.ts — intent`). */
const TOKEN_SPLIT_RE = /[^\s`"'()[\]{}<>,;，；：、]+/g;
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
function isPathCandidate(token) {
    if (token.startsWith("-"))
        return false;
    if (token.includes("://"))
        return false;
    if (token.includes("\\"))
        return false;
    if (!PATH_SHAPE_RE.test(token))
        return false;
    const trimmed = token.replace(/\/+$/, "");
    if (trimmed.includes("/")) {
        const base = trimmed.slice(trimmed.lastIndexOf("/") + 1);
        return base.includes(".");
    }
    return BASENAME_WITH_EXT_RE.test(trimmed);
}
/** Path-intent signal for the malformed bucket: the token wants to be a path
 * (it carries a separator) but fails the shape whitelist. */
function isSeparatorBearing(token) {
    return token.includes("/") || token.includes("\\");
}
/** Does `token` name something real on disk (file OR directory)? Read-only and
 * best-effort: an absent/unreadable root is "not found", never an error. */
function existsOnDisk(token, projectRoot) {
    try {
        return fs.existsSync(path.resolve(projectRoot ?? process.cwd(), token));
    }
    catch {
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
function isExistingDotlessCandidate(token, projectRoot) {
    if (isPathCandidate(token))
        return false;
    if (!isSeparatorBearing(token))
        return false;
    if (!PATH_SHAPE_RE.test(token))
        return false;
    const trimmed = token.replace(/\/+$/, "");
    const base = trimmed.slice(trimmed.lastIndexOf("/") + 1);
    if (base.includes("."))
        return false;
    return existsOnDisk(trimmed, projectRoot);
}
/** Tokens of a line, in order, with a trailing sentence full stop dropped (a
 * filename ending in `.` is invalid on Windows, so `- src/a.ts.` keeps matching
 * a declared `src/a.ts`). */
function lineTokens(line) {
    const out = [];
    for (const match of line.matchAll(TOKEN_SPLIT_RE)) {
        const token = match[0].replace(/[.。]+$/, "");
        if (token === "")
            continue;
        out.push(token);
    }
    return out;
}
/** Marker-delimited framework contract sections (write surface, dispatch card).
 * They are HTML-comment-delimited, but their BODY is plain markdown; strip the
 * whole span so a contract quoted into a report cannot declare anything. */
const CONTRACT_SECTION_RES = [
    /<!--\s*mw-write-surface: v1\s*-->[\s\S]*?<!--\s*\/mw-write-surface: v1\s*-->/g,
    /<!--\s*mw-dispatch-card: v1\s*-->[\s\S]*?<!--\s*\/mw-dispatch-card: v1\s*-->/g,
];
const HTML_COMMENT_RE = /<!--[\s\S]*?-->/g;
const FENCE_OPEN_RE = /^[ \t]*(`{3,}|~{3,})/;
/** Remove every non-declarative span from report text (T-21 requirement 4): the
 * marker contract sections, all HTML comments, and fenced code blocks. The
 * fence strip is line-based so an unterminated fence drops to EOF rather than
 * leaking its diff/regex lines as declarations. */
export function stripNonDeclarativeSpans(text) {
    let out = text;
    for (const re of CONTRACT_SECTION_RES)
        out = out.replace(re, "");
    out = out.replace(HTML_COMMENT_RE, "");
    const lines = [];
    let fence = null;
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
        if (open !== null && open[1][0] === fence)
            fence = null;
    }
    return lines.join("\n");
}
/** Prefix negation markers (T-21 requirement 2): they negate whatever follows
 * them in the same declaration item. Kept as explicit compounds — a bare `未`
 * or `不` would over-negate honest `未改 A、新增 B` lines. */
const NEGATION_PREFIX_MARKERS = [
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
const NEGATION_SUFFIX_MARKERS = [
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
function isNegatedInScope(scope, token) {
    const at = scope.indexOf(token);
    if (at === -1)
        return false;
    const low = scope.toLowerCase();
    const before = low.slice(0, at);
    const after = low.slice(at + token.length);
    if (NEGATION_PREFIX_MARKERS.some((marker) => before.includes(marker)))
        return true;
    return NEGATION_SUFFIX_MARKERS.some((marker) => after.includes(marker));
}
/** A markdown table row (`| a | b |`). */
const TABLE_ROW_RE = /^\s*\|.*\|\s*$/;
/** A list item: bullet or ordered marker, with its indentation captured. */
const LIST_ITEM_RE = /^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$/;
/** Write verbs for prose declarations (`修改了 src/a.ts`, `wrote src/a.ts`). */
const DECLARATION_VERB_RE = /(?:写入到|写入|写到|修改|新建|新增|创建|删除|重命名|wrote|written to|write to|write|edited|edit|created|create|modified|modify|changed|change)/gi;
/** Particles/quoting a verb may be separated from its target by (`修改了 x`). */
const DECLARATION_GAP_RE = /^[\s`"'*：:了到至在，,]*/;
/** Declaration items of a ledger body (T-21 requirement 3/4): list-item heads
 * at the body's minimum indentation, table rows, and write-verb-anchored
 * prose. Nested sub-bullets are the parent item's intent detail, not a second
 * declaration — that is where the `import ... from "../config.ts"` / `见
 * task.md` references lived. A body with no structured item falls back to
 * per-line prose so an unstructured ledger is still judged. */
function declarationItems(body) {
    const lines = body.split(/\r?\n/);
    let minIndent = Number.POSITIVE_INFINITY;
    for (const line of lines) {
        const li = LIST_ITEM_RE.exec(line);
        if (li !== null)
            minIndent = Math.min(minIndent, li[1].length);
    }
    const items = [];
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
            if (li[1].length !== minIndent)
                continue;
            structured = true;
            items.push({ declaration: li[2], scope: line });
            continue;
        }
        // Prose declaration: a write verb anchors the token that follows it.
        for (const match of line.matchAll(DECLARATION_VERB_RE)) {
            const at = (match.index ?? 0) + match[0].length;
            const rest = line.slice(at).replace(DECLARATION_GAP_RE, "");
            const token = lineTokens(rest)[0];
            if (token === undefined)
                continue;
            structured = true;
            items.push({ declaration: token, scope: line });
            break;
        }
    }
    if (structured)
        return items;
    return lines.filter((line) => line.trim() !== "").map((line) => ({ declaration: line, scope: line }));
}
/** The declared file set of a ledger body: declaration positions only,
 * shape-gated and negation-aware (T-21 requirements 2-4). One item = one
 * subject: the FIRST shape-valid token declares, the rest is intent prose (a
 * path referenced there — `import ... from "../config.ts"`, `见 task.md` — is
 * not a second declared file). */
function collectDeclared(body, projectRoot) {
    const out = [];
    for (const item of declarationItems(body)) {
        for (const token of lineTokens(item.declaration)) {
            if (!isPathCandidate(token) && !isExistingDotlessCandidate(token, projectRoot))
                continue;
            if (isNegatedInScope(item.scope, token))
                break;
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
export function collectMalformedCandidates(reportText) {
    const body = extractLedgerBody(stripNonDeclarativeSpans(reportText));
    const out = [];
    const seen = new Set();
    for (const line of body.split(/\r?\n/)) {
        for (const token of lineTokens(line)) {
            if (!isSeparatorBearing(token))
                continue;
            if (!/[^/\\]/.test(token))
                continue; // a lone `/` separator is punctuation, not a candidate
            if (isPathCandidate(token))
                continue;
            if (seen.has(token))
                continue;
            seen.add(token);
            out.push(token);
        }
    }
    return out;
}
/**
 * Reconcile a report's `改动清单` against the worker's trace.
 *
 * `reportText` is the agent-authored report (report.md / output.md); `traceText`
 * is the full `trace.log`. Pure: text in, verdict out, never throws.
 */
export function diffLedger(reportText, traceText, options) {
    // Per-worker attribution is structural, not a policy knob: `traceText` is the
    // caller's own trace (worker-mode.ts `readTerminalGaps` reads
    // `<own taskDir>/trace.log`), so no repo-wide `git status`/diff can enter the
    // recorded side and a concurrent worker's files can never be charged here.
    const recorded = parseWriteFileEvents(traceText);
    const body = extractLedgerBody(stripNonDeclarativeSpans(reportText));
    const declared = dedupe(collectDeclared(body, options?.projectRoot));
    // Migration / unjudgeable gate: not one recorded event ⇒ this trace could
    // not have recorded anything. T-12/F-04: with a non-empty declaration that
    // is *unjudgeable*, not green — a bash-only run must not bypass the ledger
    // and an honest declaration must not be false-red. With no declaration there
    // is nothing to reconcile, so it is trivially green.
    if (recorded.length === 0) {
        return { declared, recorded, extra: [], unjudgeable: declared.length > 0 };
    }
    const extra = declared.filter((file) => !recorded.some((recordedFile) => samePath(file, recordedFile)));
    return { declared, recorded, extra, unjudgeable: false };
}
function dedupe(values) {
    const seen = new Set();
    const out = [];
    for (const value of values) {
        if (seen.has(value))
            continue;
        seen.add(value);
        out.push(value);
    }
    return out;
}
//# sourceMappingURL=change-ledger.js.map