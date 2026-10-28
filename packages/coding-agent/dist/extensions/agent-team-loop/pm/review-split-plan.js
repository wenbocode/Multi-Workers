/**
 * pm/review-split-plan.ts — the `plan`-tier composer of the claim-driven review
 * split (card T-10, key `claim-driven-review-orchestration`; design §2.2, spec
 * AC-S2).
 *
 * `plan` means: produce the split manifest and ONE receipt line, dispatch
 * nothing, create no unit directory, write no queue row. `on` is the same plan
 * plus the dispatch of `k` unit cards, so the plan is the whole difference the
 * operator can inspect before committing to a split — it must be visible and
 * reversible (`.agenticdoc/goal.md`).
 *
 * One function wires the four parts together, nothing else:
 *
 *   source list  →  `extractClaims` (degraded path only)  →  `packClaims`
 *                →  `buildSplitManifest`  →  receipt line
 *
 * Source list, in order, first non-empty wins:
 *   1. the card's `<!-- mw-claims: v1 -->` block (`parseClaimsBlock`), used
 *      verbatim when it yields ≥1 claim — a card that already carries machine
 *      claims is never re-derived;
 *   2. deterministic downgrade: the entries of the ask sections. A `## …`
 *      heading qualifies when, parenthetical supplements removed, it CONTAINS
 *      one of `要求` / `审计目标` / `检查项` / `必须覆盖` / `验收` — that is what
 *      makes `## 要求（…对应 AC-001..005）` and `## 必须覆盖的 10 项对抗探针`
 *      ask sections too (card T-13 item 4). An entry is a list item (behaviour
 *      unchanged) or one blank-line-separated prose paragraph of the section
 *      (card T-13 item 5). Each entry derives its claim(s) in this order, first
 *      hit wins:
 *        a. the entry carries a `path:line` / `path:a-b` locator → one
 *           `findings` row with `judgement: "manual: <first 80 chars>"`;
 *        b. the entry names an AC range (`AC-001 到 AC-013`, `AC-001..005`,
 *           separators 到/至/~/～/../-/–/—) → ONE `acRows` row PER id,
 *           ascending, both ends included, at most
 *           {@link PLAN_AC_RANGE_LIMIT} ids per range
 *           (`extract:range-truncated:<total>` when cut): "每条 AC 都要给判定"
 *           is exactly the conservation the merge gate checks, so a range is
 *           never collapsed into one claim;
 *        c. the entry names one `AC-<nnn>` → one `acRows` row;
 *        c'. the entry names NO AC at all → the AC set of its section heading is
 *           its default scope (card T-13 item 6): `## 要求（…对应 AC-001..005）`
 *           makes every bare item of that section cover AC-001..AC-005, expanded
 *           exactly like b./c.;
 *        d. nothing above → the entry is an unmapped ask.
 *
 *      Every 定位 that reaches `extractClaims` — the inline one of (a.) and the
 *      one the AC index resolves — first passes {@link canonicalizeLocator}.
 *      The pack unit is a 定位 CLUSTER, so the same card composed directly
 *      (`spec.md:42`) and through the gate (`.agenticdoc/<key>/spec.md:42`) must
 *      produce the same clusters: otherwise `units` depends on how a path is
 *      spelled (`evidence/m1-exit-probe-20261022.md` §6.1 defect 1). The
 *      claims-block path above keeps its cells verbatim (AC-005).
 *      An AC row's 定位 is `acIndex[id]` and its 判据 `manual: <summary>
 *      [<id>]`: that is the deterministic bridge from the measured card shape
 *      where the 定位 lives in 上下文/被审对象 while the ask lives in
 *      要求/审计目标 (`evidence/m1-exit-probe-20261022.md` — three of four real
 *      review cards scanned `units=0 claims=0`). An id the index cannot resolve
 *      yields no claim, only `extract:ac-unresolved:<id>`. A card where NO item
 *      produces a claim yields `units=0` + `extract:no-source` instead of an
 *      invented claim.
 *
 * L0 measures ASK COVERAGE, not claim count: `asks` = every scanned list item,
 * `mapped` = how many items produced at least one claim, `unmapped` = one
 * truncated summary per item that produced none, so
 * `asks - mapped === unmapped.length` holds in EVERY branch (the no-source
 * branch included) by construction. `claims` is free to EXCEED `mapped`: one
 * "判 AC-001..AC-013" item is ONE covered ask and THIRTEEN claims.
 *
 * Receipt (frozen wording, so later stages can grep it):
 *
 *   [review-split] mode=<plan|on> units=<K> claims=<n> cap=<parentFileCap> \
 *     capSum=<Σ unit fileCap> inflation=<ratio 2dp> l0=<mapped>/<asks> \
 *     fals=<n> l1=<ok|gaps:n>
 *
 * `fals` counts `extract:falsifier-missing:<id>`: AC-derived claims are `manual`
 * by construction, so the falsifier gap is the normal state of a prose card and
 * gets its own field. `l1` counts `packGaps.length + manifestGaps.length` — the
 * STRUCTURAL gaps of packing and manifest only, never the falsifier gaps, the
 * manifest being self-checked by `verifySplitManifest`: a content gap must not
 * pin `l1` to a non-`ok` value forever (card T-13 item 7). The no-source plan keeps the same
 * field set and appends ` gap=no-source` — the marker the card requires, in the
 * only place a receipt can carry it without losing `cap`/`inflation`.
 *
 * Pure by construction (P-048): no file is read or written (the caller-supplied
 * `projectDir` is carried for the dispatch link of T-11, never consulted here),
 * no model is called, no clock/random source is touched, and nothing throws —
 * a programming error in the composition degrades to a `split:plan-failed:<m>`
 * gap with `units=0`.
 */
import { extractClaims } from "../shared/claim-extract.js";
import { packClaims } from "../shared/claim-pack.js";
import { claimBudgetCaps, parseClaimsBlock } from "../shared/dispatch-card.js";
import { buildSplitManifest, serializeSplitManifest, verifySplitManifest, } from "../shared/split-manifest.js";
// ── constants ───────────────────────────────────────────────────────────────
/**
 * Keywords an H2 must CONTAIN (parentheticals removed) to be an ask section
 * (cards T-10/T-12/T-13 item 4). Substring match on purpose: `审查要求` and
 * `必须覆盖的 10 项对抗探针` are the same section kind as `要求`.
 */
const PLAN_HEADINGS = ["检查项", "要求", "审计目标", "必须覆盖", "验收"];
/** Width of the `unmapped` summaries and of the `manual:` 判据 cell. */
const PLAN_SUMMARY_WIDTH = 80;
/** Width of the detail of a `split:plan-failed:<detail>` gap. */
const PLAN_FAILURE_WIDTH = 120;
/** Gap of a card with no claim source at all — never invented claims. */
export const PLAN_NO_SOURCE_GAP = "extract:no-source";
/** Seven columns of the unit card's claims table (`parseClaimsBlock` aliases). */
export const UNIT_CARD_COLUMNS = ["claim", "类型", "陈述", "反证条件", "定位", "判据", "预算"];
/** H2 on an already-trimmed line (`###` is a sub-heading, not a new section). */
const PLAN_H2_RE = /^##(?!#)\s+(.*)$/;
/** H1 closes any section the scan is in. */
const PLAN_H1_RE = /^#(?!#)\s+/;
/** `- item`, `* item`, `+ item`, `1. item`, `1) item`. */
const PLAN_LIST_ITEM_RE = /^\s*(?:[-*+]|\d{1,3}[.)])\s+(.*)$/;
/** Fence opener / closer (` ``` ` or `~~~`), ignored by the scan. */
const PLAN_FENCE_RE = /^\s*(`{3,}|~{3,})/;
/** `path:line` / `path:line-line` candidate; the path is validated separately. */
const PLAN_LOCATOR_RE = /([A-Za-z0-9_][A-Za-z0-9_.@/-]*):(\d+)(?:-(\d+))?/g;
/** A token names a file when it has an extension or a separator. */
const PLAN_PATH_EXT_RE = /\.[A-Za-z][A-Za-z0-9]{0,7}$/;
/** One `AC-<nnn>` reference outside a range (the AC bridge of card T-12). */
const PLAN_AC_ID_SOURCE = "AC-\\d{3}";
/**
 * `AC-001 到 AC-013` / `AC-001..005` (also 至 / ~ / ～ / - / – / —), cards
 * T-12 item 3.2 and T-13 item 6: the right end may drop its `AC-` prefix, which
 * is how the measured card writes its section scope (`AC-001..005`).
 */
const PLAN_AC_RANGE_SOURCE = "AC-(\\d{3})\\s*(?:到|至|~|～|\\.\\.|[-–—])\\s*(?:AC-)?(\\d{3})";
/** `extract:falsifier-missing:<id>` — counted by the receipt's `fals=<n>`. */
const PLAN_FALSIFIER_GAP_PREFIX = "extract:falsifier-missing:";
/** Ids one ask item may expand to; a wider range is cut and reported. */
const PLAN_AC_RANGE_LIMIT = 200;
/** `extract:falsifier-missing:<id>` gaps of a plan (the receipt's `fals=<n>`). */
function planFalsifierCount(gaps) {
    let count = 0;
    for (const gap of gaps)
        if (gap.startsWith(PLAN_FALSIFIER_GAP_PREFIX))
            count += 1;
    return count;
}
/**
 * Render the receipt. `inflation` is `capSum / cap` with two decimals; `cap = 0`
 * (no parent claim, hence no derived read budget) prints `0.00` instead of
 * dividing by zero. Field order is frozen: `mode, units, claims, cap, capSum,
 * inflation, l0, fals, l1` (`gap=no-source` last).
 */
function formatPlanReceipt(fields) {
    const ratio = fields.cap > 0 && Number.isFinite(fields.capSum / fields.cap) ? fields.capSum / fields.cap : 0;
    const receipt = `[review-split] mode=${fields.mode} units=${fields.units} claims=${fields.claims} cap=${fields.cap} capSum=${fields.capSum} inflation=${ratio.toFixed(2)} l0=${fields.mapped}/${fields.asks} fals=${fields.fals} l1=${fields.l1}`;
    return fields.noSource === true ? `${receipt} gap=no-source` : receipt;
}
/** Cut to `width` code points (never splits a surrogate pair), no ellipsis. */
function planSummary(text, width = PLAN_SUMMARY_WIDTH) {
    return Array.from(text.trim()).slice(0, width).join("");
}
/** Last segment of `text` (`/` and `\` both separate), `text` itself when it has none. */
function planBasename(text) {
    const normalized = text.replace(/\\/g, "/").replace(/\/+$/, "");
    const cut = normalized.lastIndexOf("/");
    return cut === -1 ? normalized : normalized.slice(cut + 1);
}
/**
 * Canonical form of a 定位: `basename:line[-end]` (card T-13 item 1).
 *
 * A split unit is a CLUSTER of claims sharing a 定位 token, so the same card
 * used to split differently depending on how the path was spelled — composed
 * directly `units=8`, through the gate `units=12` (`evidence/m1-exit-probe-20261022.md`
 * §6.1 defect 1). Every 定位 that reaches `extractClaims` therefore passes
 * through here first: directories, the `.agenticdoc/<key>/` prefix and
 * backtick/whitespace padding are dropped, only the file name and the line
 * range survive (`path/a.ts:3-5` → `a.ts:3-5`, `.agenticdoc/x/spec.md:42` →
 * `spec.md:42`). A cell naming no file (a bare symbol, `-`) keeps its normal
 * form, so nothing is invented for it.
 *
 * The claims-block path is NOT canonicalized: those cells are the parent's own
 * bytes and AC-005 forbids rewriting them.
 */
export function canonicalizeLocator(locator) {
    const text = typeof locator === "string" ? locator.replace(/`/g, "").trim() : "";
    if (text === "")
        return "";
    const ranged = /^(.*?):(\d+)(?:-(\d+))?$/.exec(text);
    if (ranged === null)
        return planBasename(text);
    const file = planBasename((ranged[1] ?? "").trim());
    if (file === "")
        return text;
    const start = ranged[2] ?? "";
    const end = ranged[3];
    return end === undefined ? `${file}:${start}` : `${file}:${start}-${end}`;
}
/** A locator path is a file when it has an extension or a separator. */
function planLooksLikePath(text) {
    return text.includes("/") || PLAN_PATH_EXT_RE.test(text);
}
/** First `path:line` / `path:a-b` of `text` whose path looks like a file. */
function firstPlanLocator(text) {
    const pattern = new RegExp(PLAN_LOCATOR_RE.source, "g");
    for (;;) {
        const match = pattern.exec(text);
        if (match === null)
            return undefined;
        const pathText = (match[1] ?? "").trim();
        if (!planLooksLikePath(pathText))
            continue;
        const start = match[2] ?? "";
        const end = match[3];
        return end === undefined ? `${pathText}:${start}` : `${pathText}:${start}-${end}`;
    }
}
/**
 * The deterministic AC bridge (card T-12 items 3.2/3.3): a named range expands
 * to EVERY id it covers ("每条 AC 都要给判定" is the merge gate's conservation
 * check, so a range is not one claim), a single id is one claim. A range wins
 * over a single reference inside the same item (first hit wins). No model, no
 * guess, no clock — only the item text is read.
 */
function planAcRefs(text) {
    const ids = [];
    const gaps = [];
    const seen = new Set();
    const add = (id) => {
        if (seen.has(id))
            return;
        seen.add(id);
        ids.push(id);
    };
    const rangePattern = new RegExp(PLAN_AC_RANGE_SOURCE, "g");
    for (;;) {
        const match = rangePattern.exec(text);
        if (match === null)
            break;
        const first = Number(match[1] ?? "");
        const last = Number(match[2] ?? "");
        if (!Number.isInteger(first) || !Number.isInteger(last))
            continue;
        const low = Math.min(first, last);
        const high = Math.max(first, last);
        const total = high - low + 1;
        const taken = Math.min(total, PLAN_AC_RANGE_LIMIT);
        if (total > taken) {
            const gap = `extract:range-truncated:${total}`;
            if (!gaps.includes(gap))
                gaps.push(gap);
        }
        for (let n = low; n < low + taken; n++)
            add(`AC-${String(n).padStart(3, "0")}`);
    }
    // Only when the item names no range at all: one claim per single reference.
    if (ids.length === 0) {
        const idPattern = new RegExp(PLAN_AC_ID_SOURCE, "g");
        for (;;) {
            const match = idPattern.exec(text);
            if (match === null)
                break;
            add(match[0]);
        }
    }
    return { ids, gaps };
}
/** `acIndex` as read: a non-object is empty, a non-string/blank entry is dropped.
 * Every value is canonicalized on the way in, so the index spelling cannot reach
 * `extractClaims` (card T-13 items 1/2). */
function planAcIndex(value) {
    const index = {};
    if (typeof value !== "object" || value === null)
        return index;
    for (const [id, locator] of Object.entries(value)) {
        if (typeof locator !== "string" || locator.trim() === "")
            continue;
        const canonical = canonicalizeLocator(locator);
        if (canonical === "")
            continue;
        index[id] = canonical;
    }
    return index;
}
/** Drop `（…）` / `(…)` supplements (one level of nesting per pass, repeated). */
function planStripParenthetical(text) {
    let stripped = text;
    for (;;) {
        const next = stripped.replace(/（[^（）]*）|\([^()]*\)/g, "");
        if (next === stripped)
            return stripped;
        stripped = next;
    }
}
/**
 * `## 检查项` / `## 要求（这是本轮的核心）` / `## 必须覆盖的 10 项对抗探针` are the
 * same section kind: after the parenthetical supplements are dropped the heading
 * only has to CONTAIN one of {@link PLAN_HEADINGS} (card T-13 item 4).
 */
function isPlanHeading(text) {
    const folded = planStripParenthetical(text
        .trim()
        .replace(/[：:]\s*$/, "")
        .trim()).trim();
    return PLAN_HEADINGS.some((heading) => folded.includes(heading));
}
/** Paragraph text: soft-wrapped lines joined, trimmed, markdown emphasis stripped. */
function planParagraphText(lines) {
    return lines
        .join(" ")
        .trim()
        .replace(/^[*_]+/, "")
        .replace(/[*_]+$/, "")
        .trim();
}
/** Fence state after `line`; `undefined` = outside a fenced block. */
function planFenceAfter(line, open) {
    const match = PLAN_FENCE_RE.exec(line);
    if (match === null)
        return open;
    const marker = match[1] ?? "";
    const char = marker[0] ?? "";
    if (open === undefined)
        return char;
    return char === open ? undefined : open;
}
/**
 * Scan the ask sections for entries (cards T-10 item 2, T-13 items 4/5). An
 * entry is one list item (`去列表符号后的整行`) or one blank-line-separated prose
 * paragraph (`以空行分隔的非列表块`); a continuation line of a list item belongs
 * to that item, a fenced block and another H2 end the block. Each entry carries
 * the AC scope of its section heading as its default (card T-13 item 6).
 * Deterministic and read-only — the card text is the only input.
 */
function scanChecklistEntries(cardText) {
    const entries = [];
    let active = false;
    let inList = false;
    let fence;
    let section = { ids: [], gaps: [] };
    let paragraph = [];
    const flush = () => {
        if (paragraph.length === 0)
            return;
        const text = planParagraphText(paragraph);
        paragraph = [];
        if (text === "")
            return;
        entries.push({ index: entries.length, text, locator: firstPlanLocator(text), kind: "paragraph", section });
    };
    for (const raw of cardText.split(/\r\n|\r|\n/)) {
        const openFence = fence;
        const fenceLine = PLAN_FENCE_RE.test(raw);
        fence = planFenceAfter(raw, fence);
        if (openFence !== undefined || fenceLine) {
            // Fenced content is not prose: it closes the block it sits in.
            flush();
            inList = false;
            continue;
        }
        if (raw.trim() === "") {
            flush();
            inList = false;
            continue;
        }
        const heading = PLAN_H2_RE.exec(raw);
        if (heading !== null) {
            flush();
            inList = false;
            const title = heading[1] ?? "";
            active = isPlanHeading(title);
            section = active ? planAcRefs(title) : { ids: [], gaps: [] };
            continue;
        }
        if (PLAN_H1_RE.test(raw)) {
            flush();
            inList = false;
            active = false;
            section = { ids: [], gaps: [] };
            continue;
        }
        if (!active)
            continue;
        const item = PLAN_LIST_ITEM_RE.exec(raw);
        if (item !== null) {
            flush();
            inList = true;
            const text = (item[1] ?? "").trim();
            if (text === "")
                continue;
            entries.push({ index: entries.length, text, locator: firstPlanLocator(text), kind: "item", section });
            continue;
        }
        // A soft-wrapped continuation of a list item is that item's text, not a
        // new ask; only a block after a blank line is a paragraph of its own.
        if (inList)
            continue;
        paragraph.push(raw.trim());
    }
    flush();
    return entries;
}
// ── unit card body (card T-10 item 3) ───────────────────────────────────────
/** One table cell: the parent cell verbatim, with any line break folded. */
function planTableCell(value) {
    return value.replace(/\r\n|\r|\n/g, " ").trim();
}
/** 预算 cell; a `Number.NaN` budget (unparsable in the parent) stays empty. */
function planBudgetCell(budget) {
    return Number.isInteger(budget) && budget >= 0 ? String(budget) : "";
}
/**
 * The unit card body: the unit's claims as a `<!-- mw-claims: v1 -->` seven
 * column table, every cell copied verbatim from the parent claim row (ids,
 * types, statements, falsifiers, locators, judgements, budgets are never
 * rewritten — AC-005 forbids normalization). The body re-parses to the same
 * claims through `parseClaimsBlock`, which is what makes the unit card
 * self-describing for the dispatcher and the merge gate.
 */
export function serializeUnitCardText(input) {
    const lines = [
        `# 取证单元 ${input.taskKey}`,
        "",
        "<!-- mw-claims: v1 -->",
        `| ${UNIT_CARD_COLUMNS.join(" | ")} |`,
        `| ${UNIT_CARD_COLUMNS.map(() => "---").join(" | ")} |`,
    ];
    for (const claim of input.claims) {
        const cells = [
            claim.id,
            claim.type,
            claim.statement,
            claim.falsifier,
            claim.locator,
            claim.judgement,
            planBudgetCell(claim.budget),
        ];
        lines.push(`| ${cells.map(planTableCell).join(" | ")} |`);
    }
    lines.push("<!-- /mw-claims -->", "");
    return lines.join("\n");
}
// ── composer (card T-10) ────────────────────────────────────────────────────
/**
 * Plan the claim-driven split of ONE review card: source list → extract
 * (degraded path only) → pack → manifest → receipt.
 *
 * Pure and total (P-048): nothing is read from disk, nothing is written, no
 * model is called, and no input shape throws — an empty card, a card without a
 * source list, or a composition error all come back as a `units=0` plan with
 * the gap that explains it.
 */
export function planReviewSplit(input) {
    const cardText = typeof input?.cardText === "string" ? input.cardText : "";
    const taskKey = typeof input?.taskKey === "string" ? input.taskKey : "";
    const mode = input?.mode === "on" ? "on" : "plan";
    const gaps = [];
    let claims = [];
    let asks = 0;
    let unmapped = [];
    /** Items that produced at least one claim (ask coverage, card T-12 item 4). */
    let mappedCount = 0;
    const block = parseClaimsBlock(cardText);
    if (block.claims.length > 0) {
        // 1. The card already carries machine claims: use them verbatim, never
        //    re-derive. L0 is trivially closed (every ask is a claim).
        claims = block.claims;
        asks = claims.length;
        mappedCount = claims.length;
    }
    else {
        // 2. Deterministic downgrade, per item, first hit wins (card T-12 item 3).
        const entries = scanChecklistEntries(cardText);
        asks = entries.length;
        const acIndex = planAcIndex(input?.acIndex);
        const findings = [];
        const acRows = [];
        /** Entry index owning `findings[n]` / `acRows[n]` (extraction order). */
        const findingOwners = [];
        const acOwners = [];
        for (const entry of entries) {
            const summary = planSummary(entry.text);
            // a. An inline locator IS the claim's 定位 (canonical, card T-13 item 1).
            if (entry.locator !== undefined) {
                findings.push({
                    text: entry.text,
                    locator: canonicalizeLocator(entry.locator),
                    judgement: `manual: ${summary}`,
                });
                findingOwners.push(entry.index);
                continue;
            }
            // b./c. No inline locator: borrow it from the AC index — the entry's own
            // references first, its section heading's default scope second (card T-13
            // item 6). A range expands to one row per id, so `claims` can exceed the
            // covered ask count.
            const own = planAcRefs(entry.text);
            const refs = own.ids.length > 0 ? own : entry.section;
            for (const gap of refs.gaps)
                if (!gaps.includes(gap))
                    gaps.push(gap);
            for (const id of refs.ids) {
                const locator = acIndex[id];
                if (locator === undefined) {
                    // No spec line for this id: no claim, and name the id.
                    const gap = `extract:ac-unresolved:${id}`;
                    if (!gaps.includes(gap))
                        gaps.push(gap);
                    continue;
                }
                acRows.push({ text: entry.text, locator, judgement: `manual: ${summary} [${id}]` });
                acOwners.push(entry.index);
            }
            // d. No locator and no AC reference: a plain unmapped ask.
        }
        if (findings.length === 0 && acRows.length === 0) {
            // No entry produced a claim: report it, invent nothing (card T-10 item
            // 2, T-12 item 5). L0 still accounts for EVERY ask.
            unmapped = entries.map((entry) => planSummary(entry.text));
            return {
                mode,
                receipt: formatPlanReceipt({
                    mode,
                    units: 0,
                    claims: 0,
                    cap: 0,
                    capSum: 0,
                    mapped: 0,
                    asks,
                    fals: planFalsifierCount(gaps),
                    l1: "ok",
                    noSource: true,
                }),
                l0: { asks, mapped: 0, unmapped },
                gaps: [...gaps, PLAN_NO_SOURCE_GAP],
            };
        }
        const extracted = extractClaims({ findings, acRows });
        claims = extracted.claims;
        gaps.push(...extracted.gaps);
        // Ask coverage: claims are positional in row order (findings first, then
        // `acRows`, `claim-extract.ts` step 5), so the offset names the ask it
        // serves. `asks - mapped === unmapped.length` then holds by construction.
        const owners = [...findingOwners, ...acOwners];
        const claimsPerEntry = new Map();
        const addClaim = (owner) => {
            if (owner === undefined)
                return;
            claimsPerEntry.set(owner, (claimsPerEntry.get(owner) ?? 0) + 1);
        };
        if (claims.length === owners.length) {
            for (let offset = 0; offset < claims.length; offset++)
                addClaim(owners[offset]);
        }
        else {
            // A row the extractor dropped: fall back to "the item produced a row".
            for (const owner of owners)
                addClaim(owner);
        }
        for (const entry of entries) {
            const produced = claimsPerEntry.get(entry.index) ?? 0;
            if (produced > 0) {
                mappedCount += 1;
                continue;
            }
            gaps.push(`extract:unmapped-ask:${entry.index}`);
            unmapped.push(planSummary(entry.text));
        }
    }
    const cap = claimBudgetCaps(claims).fileCap;
    try {
        // 3. Pack, then seal one unit card per pack unit.
        const packed = packClaims(claims);
        const claimById = new Map();
        for (const claim of claims) {
            if (!claimById.has(claim.id))
                claimById.set(claim.id, claim);
        }
        const unitClaims = packed.units.map((unit) => unit.ids.map((id) => claimById.get(id)).filter((claim) => claim !== undefined));
        const unitInputs = packed.units.map((unit, position) => {
            const unitTaskKey = `${taskKey}-u${unit.k}`;
            return {
                k: unit.k,
                taskKey: unitTaskKey,
                ids: [...unit.ids],
                budgetSum: unit.budgetSum,
                slots: unit.slots,
                writeFace: `workers/${unitTaskKey}`,
                text: serializeUnitCardText({ taskKey: unitTaskKey, claims: unitClaims[position] ?? [] }),
            };
        });
        // Derived read budget of each unit; `Σ` is the inflation the split buys.
        const capSum = unitClaims.reduce((sum, unitRows) => sum + claimBudgetCaps(unitRows).fileCap, 0);
        const manifest = buildSplitManifest({
            parent: taskKey,
            mode,
            parentText: cardText,
            // The merge gate iterates `ids`; it is the unit id union in unit order.
            ids: unitInputs.flatMap((unit) => unit.ids),
            units: unitInputs,
            packing: packed.packing.map((row) => ({ cluster: [...row.cluster], unit: row.unit, why: row.why })),
            l0: { asks, mapped: mappedCount, unmapped: [...unmapped] },
        });
        const manifestGaps = verifySplitManifest(manifest);
        // `l1` is structural only: the pack's and the manifest's own gaps. The
        // falsifier gaps are counted by `fals` and stay out of it (card T-13 item 7).
        const l1Count = packed.gaps.length + manifestGaps.length;
        return {
            mode,
            receipt: formatPlanReceipt({
                mode,
                units: manifest.units.length,
                claims: claims.length,
                cap,
                capSum,
                mapped: mappedCount,
                asks,
                fals: planFalsifierCount(gaps),
                l1: l1Count === 0 ? "ok" : `gaps:${l1Count}`,
            }),
            manifest,
            manifestText: serializeSplitManifest(manifest),
            l0: { asks, mapped: mappedCount, unmapped: [...unmapped] },
            gaps: [...gaps, ...packed.gaps, ...manifestGaps],
        };
    }
    catch (err) {
        // A composition error is a programming error, not user input; the plan
        // still must not throw (P-048) and must stay readable.
        const detail = planSummary(err instanceof Error ? err.message : String(err), PLAN_FAILURE_WIDTH);
        return {
            mode,
            receipt: formatPlanReceipt({
                mode,
                units: 0,
                claims: claims.length,
                cap,
                capSum: 0,
                mapped: mappedCount,
                asks,
                fals: planFalsifierCount(gaps),
                l1: "gaps:1",
            }),
            l0: { asks, mapped: mappedCount, unmapped: [...unmapped] },
            gaps: [...gaps, `split:plan-failed:${detail}`],
        };
    }
}
//# sourceMappingURL=review-split-plan.js.map