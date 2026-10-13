/**
 * shared/dispatch-card.ts — T-01 dispatch-card envelope contract
 * (key `mw-dispatch-card-gate`, contract C1).
 *
 * SINGLE JUDGEMENT for "is this task card a complete dispatch envelope?".
 * The tool layer (`dispatch_worker` / `/worker`, T-02) and the service layer
 * (`packages/multi-workers/launcher.py::_poll_once`, T-03, a Python mirror of
 * the constants below) both consult this shape, so the two gates cannot drift
 * (design.md §4 G-1/G-3, P-04).
 *
 * Judgement only, never a verdict: `readEnvelope` reports what it found and
 * `typeExtrasMissing` names the type-specific gaps; the caller decides the
 * action (refusal text, failed queue row, ...). No content-quality judgement
 * is made here.
 *
 * Wide-档 section criterion (design.md §6.3, DQ-2): a section counts as
 * present when a heading in its family is matched AND that section has a
 * non-empty body, OR when the whole document carries the family's paragraph
 * semantics. A strict-heading criterion would reject 87.2% of the historical
 * card corpus and 99.4% of the dispatch corpus (P-03: over-blocking is as much
 * a breach as under-blocking).
 *
 * `seedItemsMissing` (T-12/F-05) is the tool-layer seed minimum (AC-002 ①②);
 * `typeExtrasMissing` is the per-type §1.2 criterion both gates share.
 *
 * Vocabulary source: `.agenticdoc/mw-dispatch-card-gate/evidence/research/
 * spec-card-format-corpus-20261012.md` §0.2 (the slot word-frequency table),
 * consumed verbatim; the constants are exported so the Python mirror (T-03)
 * and the card audit (T-06) can lock the same table.
 *
 * Leaf layer: intentionally depends only on `node:fs` (plus the `node:path` /
 * `./paths.ts` allowance of the card). It must not import `pm/**` or
 * `worker/**`, and callers pass a resolved `cardPath` so the module never
 * guesses a project root.
 */
import * as fs from "node:fs";
import { readTaskType } from "./task-frontmatter.js";
/** The three envelope sections every dispatchable card must carry (§1.1). */
export const ENVELOPE_SECTIONS = ["context", "requirements", "deliverables"];
/** Human labels used in refusal text and audit output (design.md §1.1). */
export const ENVELOPE_SECTION_LABELS = {
    context: "上下文",
    requirements: "要求",
    deliverables: "交付格式",
};
// ── Vocabulary (corpus §0.2; mirrored by launcher.py, T-03) ─────────────────
/**
 * Ordered heading families. First hit wins, so `交付` outranks the
 * context/requirement families (corpus classification order). Each family is
 * a prefix match after the numbering prefix is stripped, matching the corpus
 * "标题侧（H2 及以下，正文非空的节）用前缀匹配" rule.
 */
export const ENVELOPE_HEADING_FAMILIES = [
    [
        "deliverables",
        [
            "交付物",
            "交付",
            "预期产出",
            "预期产物",
            "产物",
            "输出",
            "证据格式",
            "证据",
            "报告要求",
            "回执",
            "Deliverable",
            "Expected Output",
            "Artifact",
        ],
    ],
    [
        "context",
        [
            "背景",
            "上下文",
            "问题",
            "现状",
            "动机",
            "根因",
            "缺陷",
            "偏差",
            "目标",
            "描述",
            "输入",
            "前置",
            "范围",
            "Context",
            "Motivation",
            "Rationale",
            "Why",
            "Goal",
            "Objective",
            "Description",
            "Input",
            "Scope",
        ],
    ],
    [
        "requirements",
        [
            "要求",
            "任务",
            "契约",
            "验收",
            "验证",
            "完成判定",
            "完成判据",
            "判据",
            "行为",
            "测试",
            "接口",
            "用例",
            "协议",
            "内容",
            "标准",
            "做法",
            "策略",
            "断言",
            "规范",
            "编码",
            "对照",
            "反例",
            "反向",
            "必须",
            "实现",
            "步骤",
            "改动",
            "变更",
            "Acceptance Criteria",
            "Requirement",
            "Expected Behavior",
            "[VERIFY]",
            "AC ",
            "VC ",
            "TDD",
        ],
    ],
];
/** Paragraph-semantic fallback hints, scanned line-wise over the whole text. */
export const ENVELOPE_BODY_HINTS = {
    context: /背景|动机|原因|由于|因为|现状|痛点|为什么|为何|根因/,
    requirements: /AC-\d+|VC-\d+/i,
    deliverables: /report\.md|progress\.md|output\.md|evidence\/|回执/,
};
/** Bullet/field key predicates for the paragraph-semantic fallback. */
export const ENVELOPE_BULLET_KEYS = {
    context: /^(背景|动机|问题|现状|范围|规格|目的|前提)$/,
    requirements: /要求|规格|验收|必须|步骤|实现|改动|协议|契约|条件/,
    deliverables: /产物|交付|佐证|证据|输出|结果|报告/,
};
/** Type-specific extra items every `coding` card must declare (§1.2). */
export const CODING_EXTRA_SECTIONS = ["写入允许面", "写入禁止面", "验收命令", "改动历史"];
/** Type-specific extra items every `research` card must declare (§1.2). */
export const RESEARCH_EXTRA_SECTIONS = ["唯一证据文件"];
/** Type-specific extra items every `review` card must declare (§1.2). */
export const REVIEW_EXTRA_SECTIONS = ["审计目标", "未覆盖面声明"];
/** Extra-item names per type, in reporting order. */
export const TYPE_EXTRA_SECTIONS = {
    coding: CODING_EXTRA_SECTIONS,
    research: RESEARCH_EXTRA_SECTIONS,
    review: REVIEW_EXTRA_SECTIONS,
};
/**
 * Single-source dispatch-role vocabulary (P-08 closure, T-07).
 *
 * Enumerated from the real corpus (probe run 2026-10-12, `.agenticdoc`):
 *   - `tasks/*.md` card prologues: coding 9 / research 1 / vision 0 / 337 none;
 *   - `workers/<task>/task.md` headers: coding 227 / research 94 / review 28 /
 *     vision 1 / 1 missing;
 *   - `trace.log` `[START] ... type=`: coding 983 / research 349 / review 78 /
 *     vision 4 / default 4.
 * plus the code-side aliases the worker runtime and the dispatch role map have
 * always accepted (`verifier`, `reviewer`, `repair`, `phase-writer`,
 * `roadmap-writer`, `rag-research`) and the legacy cli-derived `codex` value
 * T-02 measured hitting `unknown-type:codex` (P-03: over-blocking an in-use
 * value is as much a breach as under-blocking).
 *
 * This ONE tuple is the shared recognition source: `typeExtrasMissing` below
 * (the tool-layer envelope extras) and the worker runtime table in
 * `worker/worker-mode.ts` are locked to it by
 * `test/suite/dispatch-recovery-terminal.test.ts`. Adding a role means changing
 * this tuple once.
 */
export const DISPATCH_TYPE_VOCABULARY = [
    "coding",
    "review",
    "research",
    "rag-research",
    "vision",
    "verifier",
    "reviewer",
    "repair",
    "phase-writer",
    "roadmap-writer",
    "codex",
];
/** Is `type` part of the single-source dispatch vocabulary? */
export function isKnownDispatchType(type) {
    return DISPATCH_TYPE_VOCABULARY.includes(type);
}
/**
 * Known dispatchable roles that carry no envelope extras in this key.
 * Kept as an exported subset of {@link DISPATCH_TYPE_VOCABULARY} for the
 * Python mirror and audit consumers; the extras check now consults the
 * vocabulary directly, so this is descriptive rather than exhaustive.
 */
export const TYPES_WITHOUT_EXTRA_RULES = ["vision", "rag-research"];
/** Item-name patterns for `typeExtrasMissing`; keys mirror `TYPE_EXTRA_SECTIONS`. */
const TYPE_EXTRA_PATTERNS = {
    coding: [
        ["写入允许面", /写入允许面|允许写入|允许写|写入范围|写面|write_scope|allow[-_ ]?write/i],
        ["写入禁止面", /写入禁止面|禁止写入|禁止写|不得写|写入禁区|禁止范围|deny[-_ ]?write|forbid/i],
        ["验收命令", /验收命令|验证命令|验收标准|验收判据|验收方式|验收|完成判据|acceptance/i],
        ["改动历史", /改动历史|改动清单|变更历史|写入事件|trace\.log|write[-_ ]?history|change[-_ ]?log/i],
    ],
    research: [["唯一证据文件", /唯一证据文件|唯一证据|唯一产物|仅此一写|sole[-_ ]?evidence/i]],
    review: [
        ["审计目标", /审计目标|审计问题|审计对象|审计范围|审计维度|问题域|要回答|audit[-_ ]?(target|scope|question)/i],
        [
            "未覆盖面声明",
            /未覆盖面|未覆盖声明|未覆盖范围|未及范围|未查看|未探索|未涉及|not[-_ ]?covered|out[-_ ]?of[-_ ]?scope/i,
        ],
    ],
};
// ── Text primitives ─────────────────────────────────────────────────────────
const HEADING_RE = /^(#{2,6})\s+(.*)$/;
const BULLET_LABEL_RE = /^\s*(?:[-*+]|\d+[.)])\s+(?:\*\*)?([^:：]{1,48}?)(?:\*\*)?\s*[:：]/;
const FIELD_LABEL_RE = /^\s*(?:\*\*)?([A-Za-z_][A-Za-z0-9_.-]{0,40})(?:\*\*)?\s*:/;
/**
 * A `type:` declaration anywhere in the card prologue. The historical card
 * corpus has almost no fenced `type:` header (0/345 cards, RQ-2), while the
 * live PM convention writes it inline in the metadata prologue
 * (`- Key: …｜type: coding`, `> key: … | type: coding`); a header-only reader
 * would reject every real card, so the prologue is the card-level header.
 * The lookbehind alternation also accepts the bare `type: …` frontmatter form.
 */
const CARD_TYPE_RE = /(?:^|[\s|｜>*+-])type:\s*([^\s|｜]+)/;
/**
 * Same newline folding as `shared/task-frontmatter.ts` so both sides index one
 * `\n` space: `\r\n`, `\r`, U+2028, U+2029 fold to `\n`, one trailing empty
 * line drops, each line trims. A leading BOM is stripped first.
 */
function splitLines(text) {
    const lines = (text.startsWith("\uFEFF") ? text.slice(1) : text).replace(/\r\n?|[\u2028\u2029]/g, "\n").split("\n");
    if (lines.length > 1 && lines[lines.length - 1] === "")
        lines.pop();
    for (let i = 0; i < lines.length; i++)
        lines[i] = lines[i].replace(/\r$/, "").trim();
    return lines;
}
/**
 * First `type:` declaration in the card prologue (lines before the first H2
 * heading), `""` when absent or empty. Everything at or below the first H2 is
 * body: a `type:` written there must not flip the role (the same rule as
 * `task-frontmatter.ts::readTaskType`'s F-10 body-type exclusion).
 */
function readCardType(lines) {
    // P-08 single source (T-07): `shared/task-frontmatter.ts::readTaskType` owns
    // the `type:` header semantics (fence -> first blank line -> key run; a body
    // `type:` never flips the role). A live PM card that writes
    // `- Key: ...｜type: coding` below a blank line sits outside that header
    // region, so the card-prologue scan below is the fallback — it never
    // overrides a value the shared reader already found, and it never reads a
    // `type:` below the first H2 (F-10). readEnvelope's verdict is unchanged.
    const shared = readTaskType(lines.join("\n")).type;
    if (shared !== undefined && shared !== "")
        return shared.trim();
    const firstHeading = lines.findIndex((line) => HEADING_RE.test(line));
    const end = firstHeading === -1 ? lines.length : firstHeading;
    for (let i = 0; i < end; i++) {
        const match = CARD_TYPE_RE.exec(lines[i]);
        if (match)
            return match[1].trim();
    }
    return "";
}
/** Strip a leading `1.` / `1.2.` / `(2)` / `A.` / `一、` numbering prefix. */
function stripNumbering(text) {
    let out = text.trim();
    out = out.replace(/^[（(]\s*[0-9A-Za-z一二三四五六七八九十]+\s*[)）]\s*/, "");
    out = out.replace(/^[0-9]+(?:\.[0-9]+)*\s*[.、)）]\s*/, "");
    out = out.replace(/^[A-Za-z]\s*[.、)）]\s*/, "");
    out = out.replace(/^[一二三四五六七八九十]+\s*[、.)）]\s*/, "");
    return out.trim();
}
/** First heading family the heading belongs to (deliverables > context > requirements). */
function classifyHeading(heading) {
    const lower = heading.toLowerCase();
    for (const [section, tokens] of ENVELOPE_HEADING_FAMILIES) {
        for (const token of tokens) {
            if (lower.startsWith(token.toLowerCase()))
                return section;
        }
    }
    return undefined;
}
/** A bullet/field label in the card (`- 允许写：…`, `write_scope: …`). */
function labelOf(line) {
    const bullet = BULLET_LABEL_RE.exec(line);
    if (bullet)
        return bullet[1].trim();
    const field = FIELD_LABEL_RE.exec(line);
    if (field)
        return field[1].trim();
    return undefined;
}
function anyLabelMatches(lines, keyRe) {
    for (const line of lines) {
        const label = labelOf(line);
        if (label !== undefined && keyRe.test(label))
            return true;
    }
    return false;
}
function collectHeadings(lines) {
    const headings = [];
    for (let i = 0; i < lines.length; i++) {
        const match = HEADING_RE.exec(lines[i]);
        if (match)
            headings.push({ level: match[1].length, text: stripNumbering(match[2]), line: i });
    }
    return headings;
}
function bodySemanticHit(section, lines) {
    if (lines.some((line) => ENVELOPE_BODY_HINTS[section].test(line)))
        return true;
    return anyLabelMatches(lines, ENVELOPE_BULLET_KEYS[section]);
}
function detectSections(lines) {
    const detected = { context: "", requirements: "", deliverables: "" };
    const headings = collectHeadings(lines);
    for (let i = 0; i < headings.length; i++) {
        const heading = headings[i];
        const section = classifyHeading(heading.text);
        if (section === undefined || detected[section] !== "")
            continue;
        let end = lines.length;
        for (let j = i + 1; j < headings.length; j++) {
            if (headings[j].level <= heading.level) {
                end = headings[j].line;
                break;
            }
        }
        let hasBody = false;
        for (let k = heading.line + 1; k < end; k++) {
            if (lines[k] !== "") {
                hasBody = true;
                break;
            }
        }
        if (hasBody)
            detected[section] = `heading:${heading.text}`;
    }
    for (const section of ENVELOPE_SECTIONS) {
        if (detected[section] === "" && bodySemanticHit(section, lines))
            detected[section] = "semantics";
    }
    return detected;
}
// ── Public judgement ────────────────────────────────────────────────────────
/** The empty detection record (used for unreadable cards). */
function emptyDetected() {
    return { context: "", requirements: "", deliverables: "" };
}
/**
 * Judge an already-read card body (pure; no fs). Exported so a caller that
 * already holds the text (queue row, corpus scan) shares the exact judgement
 * instead of re-implementing it.
 */
export function inspectEnvelope(text) {
    const lines = splitLines(text);
    const type = readCardType(lines);
    const detected = detectSections(lines);
    const missing = [];
    if (type === "")
        missing.push("type");
    for (const section of ENVELOPE_SECTIONS) {
        if (detected[section] === "")
            missing.push(section);
    }
    return { ok: missing.length === 0, missing, type, detected };
}
/**
 * Read a task card and report its envelope status. A missing/unreadable card
 * yields `missing: ["file"]` (all sections absent) so the caller can name the
 * path it was given; every other finding is a normal `ok: false` report.
 */
export function readEnvelope(cardPath) {
    let text;
    try {
        text = fs.readFileSync(cardPath, "utf8");
    }
    catch {
        return { ok: false, missing: ["file"], type: "", detected: emptyDetected() };
    }
    return inspectEnvelope(text);
}
/**
 * Type-specific gaps of `text` for `type`: the item names listed in
 * design.md §1.2 that the card does not declare, `[]` when none. An
 * unrecognised type returns `["unknown-type:<type>"]` so the gate names the
 * role rather than silently passing it. Every role in the single-source
 * `DISPATCH_TYPE_VOCABULARY` (dispatchable roles + the runtime aliases +
 * legacy `codex`) is recognised here and carries no extras in this key.
 *
 * "Declared" is wide on purpose (heading, bullet/field label, or the canonical
 * item name anywhere in the card): the per-type extras exist to catch an
 * omitted contract, not to police wording (P-03).
 */
export function typeExtrasMissing(type, text) {
    const patterns = TYPE_EXTRA_PATTERNS[type];
    if (patterns === undefined) {
        // P-08: every in-use role is in the single-source vocabulary; only a
        // genuinely unknown value is named (keeps the unknown-type branch
        // discriminating without over-blocking the legacy/runtime roles).
        return isKnownDispatchType(type) ? [] : [`unknown-type:${type}`];
    }
    const lines = splitLines(text);
    const missing = [];
    for (const [item, pattern] of patterns) {
        if (text.includes(item))
            continue;
        if (anyLabelMatches(lines, pattern))
            continue;
        let headingHit = false;
        for (const line of lines) {
            const heading = HEADING_RE.exec(line);
            if (heading && pattern.test(stripNumbering(heading[2]))) {
                headingHit = true;
                break;
            }
        }
        if (!headingHit)
            missing.push(item);
    }
    return missing;
}
// ── Seed minimum (T-12/F-05, AC-002 ①②) ─────────────────────────────────────
/**
 * The seed four-item acceptance (AC-002 ①②) had no machine judge, so a card
 * that handed the worker no starting anchor passed the tool gate (F-05). The
 * judged minimum is deliberately just two items, both WIDE (P-03):
 *
 *  - a literal `goal.md` reference — the project-level goal anchor; and
 *  - at least one `path:line` reference — a resolvable starting point.
 *
 * The card's own 上下文/要求 sections are delivered verbatim as the seed already,
 * so they need no separate judgement here. This is the tool-layer (G-1)
 * criterion; the service layer re-checks the envelope + type extras on the
 * derived task.md, into which the card context (and so these references) is
 * injected.
 */
export const GOAL_ANCHOR = "goal.md";
export const SEED_GOAL_ITEM = "seed:goal.md";
export const SEED_PATH_ITEM = "seed:path:line";
/** `name.ext:123` — a file reference with a line number. The dot + letter-init
 * extension requirement keeps times (`12:30`) and extensionless tokens out. */
const PATH_LINE_RE = /[A-Za-z0-9_][\w./-]*\.[A-Za-z][A-Za-z0-9]{0,7}:\d+/;
/** Seed items the card does not declare, `[]` when it declares both. */
export function seedItemsMissing(text) {
    const missing = [];
    if (!text.includes(GOAL_ANCHOR))
        missing.push(SEED_GOAL_ITEM);
    if (!PATH_LINE_RE.test(text))
        missing.push(SEED_PATH_ITEM);
    return missing;
}
//# sourceMappingURL=dispatch-card.js.map