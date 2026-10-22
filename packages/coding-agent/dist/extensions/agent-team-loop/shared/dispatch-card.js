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
 * guesses a project root. The claims section below re-implements the fence
 * state machine of `worker/output-sections.ts` for the same reason instead of
 * importing it (claims design §3.1).
 */
import * as fs from "node:fs";
import * as path from "node:path";
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
    // Decision-book writer (mw-decision-substitution W8, renamed W10): a role
    // that only fills a decision book from evidence, never edits code. The type
    // value is `decide_prepare` (was `decision`; no alias kept).
    "decide_prepare",
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
    decide_prepare: [
        ["dp", /^\s*(?:[-*+]\s*)?(?:\*\*)?dp(?:\*\*)?\s*[:：]/im],
        ["证据来源", /证据来源|证据清单|证据出处|evidence[-_ ]?sources?/i],
        ["分支后果", /分支后果|各分支|后果说明|branch[-_ ]?(consequences?|outcomes?)/i],
        ["allow-send", /allow[-_ ]?send/i],
    ],
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
// ── claims: constants (design §2.1/§2.3, parity-locked by T-06) ─────────────
/**
 * Self-reported judgement kind of one claim. The classifier never infers the
 * kind (agreement with the corpus is only 63.5%, RQ-3 §2.4); the card declares
 * it and {@link claimsGaps} only checks that the `判据` prefix agrees.
 */
export const CLAIM_TYPES = ["cmd", "grep", "struct", "manual"];
/**
 * `unverified` reason vocabulary (design §2.3). Single source: the Python
 * mirror (`autopilot/dispatch.py`) and the T-06 parity lock read this tuple
 * verbatim. Never write a second copy — the `ESCALATED_REASONS` precedent
 * (`packages/multi-workers/decision_points.py:111-120`) records exactly that
 * drift lesson.
 */
export const UNVERIFIED_REASONS = [
    "budget",
    "no-access",
    "not-found",
    "ambiguous",
    "environment",
    "out-of-scope",
    "awaiting-input",
];
/**
 * Default gate mode (D-006): `advisory` warns only, `enforce` refuses with zero
 * side effects. `MW_CLAIM_GATE=enforce` overrides it at runtime; both sides of
 * the TS/Python pair use the same constant and the same env name.
 */
export const CLAIM_GATE_DEFAULT = "advisory";
/**
 * Calibrated read budget of one dispatch unit (RQ-1 §5, D-007): 30 calls,
 * 393,216 B cumulative, from the p90 single-fetch cost (4,854 tokens) and the
 * <400k chars safe band. `perClaim` is the planning weight, `hardCap` the
 * floor(177856/4977) ceiling and `claimByteCap` the per-claim byte allowance.
 */
export const CLAIM_BUDGET = {
    perClaim: 6,
    callCap: 30,
    hardCap: 35,
    claimByteCap: 65536,
    byteCapMax: 393216,
};
// ── claims: 解析 / parsing (design §2.1, P-048 tolerance) ────────────────────
/** Opening marker of the card's claims block. */
const CLAIMS_OPEN_RE = /^<!--\s*mw-claims\s*:\s*v1\s*-->$/i;
/** Closing marker; when absent the block tolerates up to the next H2. */
const CLAIMS_CLOSE_RE = /^<!--\s*\/\s*mw-claims\s*-->$/i;
/** H2 on an already-trimmed line: the tolerance end of an unterminated block. */
const CLAIMS_STOP_H2_RE = /^##(?!#)\s+/;
/** Fence opener/closer; same semantics as `worker/output-sections.ts`. */
const CLAIMS_FENCE_RE = /^(`{3,}|~{3,})(.*)$/;
/** `C-01` / `C-01.3` (the `C` is case-insensitive, digits are 2-3 wide). */
const CLAIM_ID_RE = /^C-(\d{2,3})(?:\.(\d+))?$/i;
/**
 * Header aliases per field (P-048, RQ-3 §5.6): column order is free, extra
 * columns are ignored, and either script of the header word is accepted.
 */
const CLAIM_COLUMN_ALIASES = [
    ["id", ["claim", "claim id", "claim id /", "断言", "断言 id"]],
    ["type", ["类型", "type", "类别"]],
    ["statement", ["陈述", "statement", "主张", "断言内容"]],
    ["falsifier", ["反证条件", "反证", "falsifier", "refutation"]],
    ["locator", ["定位", "locator", "anchor", "锚点"]],
    ["judgement", ["判据", "judgement", "judgment", "criterion"]],
    ["budget", ["预算", "budget"]],
];
/** Tracks fenced-code-block state across lines (mirror of the worker copy). */
function advanceClaimFence(line, open) {
    const match = CLAIMS_FENCE_RE.exec(line);
    if (match === null)
        return open;
    const marker = match[1] ?? "";
    const rest = match[2] ?? "";
    const char = marker[0] ?? "";
    if (open === undefined)
        return { char, len: marker.length };
    if (char === open.char && marker.length >= open.len && rest.trim() === "")
        return undefined;
    return open;
}
/**
 * Fold the full-width forms the card corpus mixes in (P-048): `：` -> `:`,
 * `｜` -> `|`, full-width digits -> ASCII digits, ideographic space -> space.
 */
function normalizeClaimText(text) {
    return text
        .replace(/[\uFF10-\uFF19]/g, (digit) => String.fromCharCode(digit.charCodeAt(0) - 0xfee0))
        .replace(/\uFF1A/g, ":")
        .replace(/\uFF5C/g, "|")
        .replace(/\u3000/g, " ")
        .trim();
}
/** Cells never carry markdown code fences: strip the backticks a writer adds. */
function stripClaimTicks(text) {
    return text.replace(/`/g, "").trim();
}
/** Split a `| a | b |` row into trimmed cells (leading/trailing pipes dropped). */
function splitClaimRow(line) {
    const cells = normalizeClaimText(line).split("|");
    if (cells.length > 0 && (cells[0] ?? "").trim() === "")
        cells.shift();
    if (cells.length > 0 && (cells[cells.length - 1] ?? "").trim() === "")
        cells.pop();
    return cells.map((cell) => cell.trim());
}
/** Header of a claims table, `undefined` when the row is not a claims header. */
function matchClaimHeader(cells) {
    const columns = {};
    let hasClaimColumn = false;
    for (let i = 0; i < cells.length; i++) {
        const name = stripClaimTicks(normalizeClaimText(cells[i] ?? ""))
            .toLowerCase()
            .replace(/\s+/g, " ")
            .replace(/:$/, "");
        for (const [field, aliases] of CLAIM_COLUMN_ALIASES) {
            if (!aliases.includes(name))
                continue;
            if (columns[field] === undefined)
                columns[field] = i;
            if (field === "id")
                hasClaimColumn = true;
            break;
        }
    }
    return hasClaimColumn ? columns : undefined;
}
/** `| --- | --- |` separator row (any dash count, optional alignment colons). */
function isClaimSeparatorRow(cells) {
    if (cells.length === 0)
        return false;
    return cells.every((cell) => cell === "" || /^:?-{1,}:?$/.test(cell));
}
/** Cell of `field` in `cells`, `""` when the column is absent (P-048). */
function claimCell(cells, columns, field) {
    const index = columns[field];
    if (index === undefined)
        return "";
    return (cells[index] ?? "").trim();
}
/**
 * Parse the card's `<!-- mw-claims: v1 -->` block (design §2.1).
 *
 * Tolerance is the contract, not a nicety (P-048: an over-strict schema caused
 * 30 minutes of consecutive false refusals): the block end falls back to the
 * next H2 or EOF, column order is free, extra columns are ignored, header
 * words take aliases, full-width `：｜`/digits fold to ASCII, and fenced code
 * blocks contribute nothing. An unparsable row is reported as
 * `claim:<row>:unparsable` and skipped — this function never throws.
 */
export function parseClaimsBlock(text) {
    const block = { present: false, claims: [], errors: [] };
    const byId = new Map();
    let fence;
    let inBlock = false;
    let columns;
    const lines = splitLines(text);
    for (let i = 0; i < lines.length; i++) {
        const line = lines[i] ?? "";
        fence = advanceClaimFence(line, fence);
        if (fence !== undefined)
            continue;
        if (!inBlock) {
            if (CLAIMS_OPEN_RE.test(line)) {
                inBlock = true;
                block.present = true;
            }
            continue;
        }
        if (CLAIMS_CLOSE_RE.test(line) || CLAIMS_STOP_H2_RE.test(line)) {
            inBlock = false;
            columns = undefined;
            continue;
        }
        if (!normalizeClaimText(line).startsWith("|")) {
            columns = undefined;
            continue;
        }
        const cells = splitClaimRow(line);
        if (columns === undefined) {
            columns = matchClaimHeader(cells);
            continue;
        }
        if (isClaimSeparatorRow(cells))
            continue;
        const claim = claimFromRow(cells, columns, i + 1, byId);
        if (claim === undefined) {
            block.errors.push(`claim:${i + 1}:unparsable`);
            continue;
        }
        block.claims.push(claim);
        byId.set(claim.id, claim);
    }
    return block;
}
/** One table row -> {@link Claim}, `undefined` when the row cannot be parsed. */
function claimFromRow(cells, columns, row, byId) {
    const idMatch = CLAIM_ID_RE.exec(stripClaimTicks(claimCell(cells, columns, "id")));
    if (idMatch === null)
        return undefined;
    const number = idMatch[1] ?? "";
    const child = idMatch[2];
    const parent = child === undefined ? "" : `C-${number}`;
    const id = `C-${number}${child === undefined ? "" : `.${child}`}`;
    if (parent !== "") {
        // RQ-3 §5.1 / B-10: a `父.序号` child row is only legal under a `struct`
        // parent (a struct enumerates the sub-items of one shape).
        const parentClaim = byId.get(parent);
        if (parentClaim === undefined || parentClaim.type !== "struct")
            return undefined;
    }
    const declaredType = stripClaimTicks(claimCell(cells, columns, "type")).toLowerCase();
    const budgetText = stripClaimTicks(claimCell(cells, columns, "budget"));
    return {
        id,
        // A struct child restates part of the parent shape, so an empty `类型`
        // cell inherits `struct` instead of manufacturing a second gap.
        type: declaredType === "" && parent !== "" ? "struct" : declaredType,
        parent,
        statement: claimCell(cells, columns, "statement"),
        falsifier: claimCell(cells, columns, "falsifier"),
        locator: claimCell(cells, columns, "locator"),
        judgement: claimCell(cells, columns, "judgement"),
        budget: /^\d+$/.test(budgetText) ? Number(budgetText) : Number.NaN,
        row,
    };
}
// ── claims: 校验 / validation (design §2.1, AC-001) ──────────────────────────
/** `判据` prefix each self-reported type must carry (design §2.1). */
const CLAIM_TYPE_PREFIX = {
    cmd: "cmd:",
    grep: "grep:",
    struct: "shape:",
    manual: "manual:",
};
/** `Σ预算` cap, manual rows counted twice (AC-001 ⑤). */
const CLAIM_BUDGET_SUM_MAX = 40;
/** `manual` cap numerator of `min(4, ceil(n/3))` (AC-001 ⑤, RQ-3 §6.1). */
const CLAIM_MANUAL_CAP = 4;
/** Normalized-similarity threshold of the tautology judge (RQ-3 B-5). */
const CLAIM_TAUTOLOGY_SIMILARITY = 0.9;
/** Above this size a `定位` must name a line range (AC-001 ④). */
const CLAIM_LOCATOR_RANGE_BYTES = 32768;
/** D-005: a `cmd` locator is the PM's pre-executed evidence file row. */
const CLAIM_CMD_LOCATOR_RE = /^evidence\/claims\/[^#\s]+#(C-\d{2,3}(?:\.\d+)?)$/i;
/** A locator names a file when it has a separator or a file extension. */
function looksLikeClaimPath(text) {
    if (text.includes("/"))
        return true;
    return /\.[A-Za-z][A-Za-z0-9]{0,7}$/.test(text);
}
/**
 * Resolve a `定位` cell against `projectDir` without reading content: only
 * `statSync` runs (design §3.1). A bare symbol, a missing file, a non-file and
 * a path outside `projectDir` are all `unresolved` (never a throw).
 */
function resolveClaimLocator(locator, projectDir) {
    const raw = stripClaimTicks(locator);
    if (raw === "" || raw === "-")
        return { kind: "skipped", size: 0, ranged: false };
    const withoutFragment = raw.replace(/#.*$/, "");
    const range = /^(.*?):(\d+)(?:-(\d+))?$/.exec(withoutFragment);
    const pathText = (range === null ? withoutFragment : (range[1] ?? "")).trim();
    const ranged = range !== null && range[3] !== undefined;
    if (pathText === "" || !looksLikeClaimPath(pathText))
        return { kind: "unresolved", size: 0, ranged };
    const absolute = path.resolve(projectDir, pathText);
    const relative = path.relative(projectDir, absolute);
    if (relative === "" || relative === ".." || relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative)) {
        return { kind: "unresolved", size: 0, ranged };
    }
    try {
        const stat = fs.statSync(absolute);
        if (!stat.isFile())
            return { kind: "unresolved", size: 0, ranged };
        return { kind: "resolved", size: stat.size, ranged };
    }
    catch {
        return { kind: "unresolved", size: 0, ranged };
    }
}
/**
 * Negation / absence words plus aspect fillers stripped before the tautology
 * similarity test, so that "X 已修复" vs "X 未修复" compares the same
 * remainder (RQ-3 B-5: the whole point is that a minimal rewrite only differs
 * by these words). Longest-first so `不再` wins over `不` and `已经` over `已`.
 */
const CLAIM_NEGATION_TOKENS = [
    "已经",
    "不再",
    "不会",
    "不能",
    "不得",
    "没有",
    "无法",
    "禁止",
    "absent",
    "cannot",
    "didn't",
    "doesn't",
    "failed",
    "fails",
    "isn't",
    "aren't",
    "missing",
    "never",
    "without",
    "can't",
    "fail",
    "not",
    "已",
    "不",
    "未",
    "无",
    "非",
    "否",
    "缺",
].sort((a, b) => b.length - a.length);
/** Drop negation words (ASCII ones with word boundaries), then all separators. */
function normalizeClaimSimilarityText(text) {
    let out = text.toLowerCase().replace(/`/g, " ");
    for (const token of CLAIM_NEGATION_TOKENS) {
        out = /^[a-z']+$/.test(token) ? out.replace(new RegExp(`\\b${token}\\b`, "gi"), " ") : out.split(token).join(" ");
    }
    return out.replace(/[^\p{L}\p{N}]+/gu, "");
}
/** Levenshtein distance over code points (both inputs are short in practice). */
function claimEditDistance(a, b) {
    const left = Array.from(a);
    const right = Array.from(b);
    let previous = right.map((_, index) => index);
    previous = [0, ...previous];
    for (let i = 1; i <= left.length; i++) {
        const current = [i];
        for (let j = 1; j <= right.length; j++) {
            const cost = left[i - 1] === right[j - 1] ? 0 : 1;
            current[j] = Math.min((previous[j] ?? Number.POSITIVE_INFINITY) + 1, (current[j - 1] ?? Number.POSITIVE_INFINITY) + 1, (previous[j - 1] ?? Number.POSITIVE_INFINITY) + cost);
        }
        previous = current;
    }
    return previous[right.length] ?? 0;
}
/** Artifact tokens (paths, symbols, commands) that a `判据` can point at. */
const CLAIM_ARTIFACT_TOKEN_RE = /[A-Za-z0-9_][A-Za-z0-9_./-]*/g;
/** Artifact tokens of a `判据`, with the leading type prefix removed. */
function claimJudgementArtifacts(judgement) {
    const body = judgement.replace(/^\s*(?:cmd|grep|shape|manual)\s*:\s*/i, "");
    const tokens = body.match(CLAIM_ARTIFACT_TOKEN_RE) ?? [];
    return tokens.filter((token) => token.length >= 3);
}
/**
 * Tautology judge (RQ-3 B-5): `陈述` and `反证条件` become the same text once
 * negation words are dropped (similarity >= 0.90) AND the `判据` names no
 * artifact that `陈述` does not already name. Any new artifact (path, symbol,
 * command) means the claim is still falsifiable, so it is not tautological.
 */
function isTautologicalClaim(claim) {
    if (claim.statement === "" || claim.falsifier === "" || claim.judgement === "")
        return false;
    const statement = normalizeClaimSimilarityText(claim.statement);
    const falsifier = normalizeClaimSimilarityText(claim.falsifier);
    if (statement === "" || falsifier === "")
        return false;
    const distance = claimEditDistance(statement, falsifier);
    const similarity = 1 - distance / Math.max(statement.length, falsifier.length);
    if (similarity < CLAIM_TAUTOLOGY_SIMILARITY)
        return false;
    const haystack = claim.statement.toLowerCase();
    return !claimJudgementArtifacts(claim.judgement).some((token) => !haystack.includes(token.toLowerCase()));
}
/**
 * Judge a parsed claims block (design §2.1/§3.1, AC-001). Never throws.
 *
 * Structural gaps (`type` / `statement` / `falsifier` / `locator` /
 * `judgement` / `budget`) are gaps in both modes: a claim missing a required
 * cell is not a claim. The soft findings — `type-prefix`, `cmd-locator`,
 * `locator-unresolved`, `locator-range`, `tautology` and the two `claims:*`
 * aggregates — are returned only when `opts.enforce` is true; an advisory
 * caller gets `[]` for them here and can re-query with `enforce: true` to
 * render the same string list as warnings (D-006: advisory warns, never
 * refuses).
 *
 * Item shapes are frozen because T-02 concatenates them into the refusal text:
 * `claim:<id>:<element>` and `claims:<rule>:<detail>`.
 */
export function claimsGaps(block, opts) {
    const structural = [];
    const advisory = [];
    let budgetSum = 0;
    let manualCount = 0;
    for (const claim of block.claims) {
        const type = claim.type.toLowerCase();
        const known = CLAIM_TYPES.includes(type);
        budgetSum += type === "manual" ? 2 : 1;
        if (type === "manual")
            manualCount += 1;
        if (!known)
            structural.push(`claim:${claim.id}:type`);
        if (claim.statement === "")
            structural.push(`claim:${claim.id}:statement`);
        if (claim.falsifier === "")
            structural.push(`claim:${claim.id}:falsifier`);
        if (claim.locator === "")
            structural.push(`claim:${claim.id}:locator`);
        if (claim.judgement === "")
            structural.push(`claim:${claim.id}:judgement`);
        if (!Number.isInteger(claim.budget) || claim.budget < 0)
            structural.push(`claim:${claim.id}:budget`);
        if (!known)
            continue;
        if (claim.judgement !== "") {
            const prefix = CLAIM_TYPE_PREFIX[type];
            if (!claim.judgement.trim().toLowerCase().startsWith(prefix))
                advisory.push(`claim:${claim.id}:type-prefix`);
        }
        if (type === "cmd" && claim.locator !== "") {
            const cmdLocator = CLAIM_CMD_LOCATOR_RE.exec(stripClaimTicks(claim.locator));
            if (cmdLocator === null || (cmdLocator[1] ?? "").toUpperCase() !== claim.id.toUpperCase()) {
                advisory.push(`claim:${claim.id}:cmd-locator`);
            }
        }
        const target = resolveClaimLocator(claim.locator, opts.projectDir);
        if (target.kind === "unresolved")
            advisory.push(`claim:${claim.id}:locator-unresolved`);
        if (target.kind === "resolved" && target.size > CLAIM_LOCATOR_RANGE_BYTES && !target.ranged) {
            advisory.push(`claim:${claim.id}:locator-range`);
        }
        if (isTautologicalClaim(claim))
            advisory.push(`claim:${claim.id}:tautology`);
    }
    const total = block.claims.length;
    if (budgetSum > CLAIM_BUDGET_SUM_MAX)
        advisory.push(`claims:budget-sum:${budgetSum}>${CLAIM_BUDGET_SUM_MAX}`);
    const manualCap = Math.min(CLAIM_MANUAL_CAP, Math.ceil(total / 3));
    if (manualCount > manualCap)
        advisory.push(`claims:manual-overflow:${manualCount}/${total}`);
    return opts.enforce ? [...structural, ...advisory] : structural;
}
// ── claims: 预算 / budget (design §4, AC-003) ────────────────────────────────
/**
 * Read-scope caps derived from the claims block (design §4):
 * `fileCap = min(30, Σ(manual ? 2 : 1))`, `byteCap = min(393,216, 65,536 × n)`.
 * No claims means no derived cap — `{ fileCap: 0, byteCap: 0 }` lets the caller
 * keep the project-level default instead of zeroing a read budget.
 */
export function claimBudgetCaps(claims) {
    if (claims.length === 0)
        return { fileCap: 0, byteCap: 0 };
    let weightSum = 0;
    for (const claim of claims)
        weightSum += claim.type.toLowerCase() === "manual" ? 2 : 1;
    return {
        fileCap: Math.min(CLAIM_BUDGET.callCap, weightSum),
        byteCap: Math.min(CLAIM_BUDGET.byteCapMax, CLAIM_BUDGET.claimByteCap * claims.length),
    };
}
//# sourceMappingURL=dispatch-card.js.map