/**
 * Single-source task.md header (frontmatter) parsing — AC-005 / VC-039.
 *
 * The role of a worker task is decided by exactly one value: the FIRST `type:`
 * inside the task header. Nothing below the header may flip it — the old
 * full-text last-wins scan in `worker-mode.ts::parseTaskMd` let a body line
 * (`type: coding`) hand a `review` task the write/edit/bash surface (A8).
 * Every consumer (worker, PM dispatch, autopilot status model, test corpus
 * scanners) reads from this one module so the dispatch-side judgement and the
 * execution-side judgement cannot drift.
 *
 * Boundary algorithm (design.md 4.4.1; design-role-key-identity-20261011 1.2):
 *
 * 1. A leading BOM (U+FEFF) is stripped up front and reported (`byteOrderMark`
 *    on the region, `bomStripped` on the reading) because Python's str.strip()
 *    does not eat it and 7 historical task.md files carry one.
 * 2. Newline sequences (`\r\n`, `\r`, U+2028, U+2029) fold to "\n" first, so
 *    both language sides index ONE `\n` space; one trailing newline is then
 *    dropped and each line trimmed (keeps the no-blank-line branch reachable).
 * 3. Header region = first line is `---` → first following `---` (an unclosed
 *    fence falls through to the next rule instead of yielding an empty
 *    header); else the first blank line; else the leading run of key-shaped
 *    lines (`key:` or `- ` block-list items), which sets `truncated`. If the
 *    first line is not key-shaped that run is empty (startLine > endLine).
 * 4. A scalar is the FIRST matching key inside that region; only the `type:`
 *    key value is exposed with provenance. `readTaskType` returns
 *    `source: "body"` (with `type: undefined`) when the header has no `type:`
 *    but the body does — the body value is never returned, per spec F-10.
 *
 * Pure functions only: no fs, no cwd, no clock, no throws (structured results).
 * The module has zero imports on purpose (see the purity test in
 * test/suite/task-frontmatter.test.ts).
 */
/** Key grammar of a header line (design.md 4.4.1). Anchored: `type : x` and
 * `types: x` are not the `type:` key. */
const HEADER_KEY_RE = /^[A-Za-z_][A-Za-z0-9_-]*:/;
/** Block-list item inside a header run without a trailing blank line. */
const HEADER_LIST_ITEM_RE = /^-\s/;
const TYPE_PREFIX = "type:";
/** Tool names that distinguish a power role from a read-only one (the
 * escalation predicate, design-role-key-identity 1.4). */
const POWER_TOOL_NAMES = ["write", "edit", "bash"];
/** Normalize to ONE `\n` index space: `\r\n`, `\r`, U+2028, U+2029 fold to
 * `\n` (Python mirror `mw_common._split_task_lines`); drop one trailing empty. */
function splitTaskLines(text) {
    const byteOrderMark = text.startsWith("\uFEFF");
    const lines = (byteOrderMark ? text.slice(1) : text).replace(/\r\n?|[\u2028\u2029]/g, "\n").split("\n");
    if (lines.length > 1 && lines[lines.length - 1] === "")
        lines.pop();
    for (let i = 0; i < lines.length; i++) {
        lines[i] = lines[i].replace(/\r$/, "").trim();
    }
    return { lines, byteOrderMark };
}
function regionFromLines(lines, byteOrderMark) {
    if (lines[0] === "---") {
        const close = lines.indexOf("---", 1);
        if (close > 0)
            return { startLine: 1, endLine: close - 1, fenced: true, truncated: false, byteOrderMark };
        // Unclosed fence: fall through to the unfenced rules (never an empty header).
    }
    const blank = lines.indexOf("");
    if (blank >= 0)
        return { startLine: 0, endLine: blank - 1, fenced: false, truncated: false, byteOrderMark };
    let end = 0;
    while (end < lines.length && (HEADER_KEY_RE.test(lines[end]) || HEADER_LIST_ITEM_RE.test(lines[end])))
        end++;
    return { startLine: 0, endLine: end - 1, fenced: false, truncated: true, byteOrderMark };
}
/** Extract the header region of a task.md document. */
export function extractTaskHeader(text) {
    const { lines, byteOrderMark } = splitTaskLines(text);
    return regionFromLines(lines, byteOrderMark);
}
/** First scalar value for `key` inside the header region. Returns the trimmed
 * value (`""` when the key is present but empty) or `undefined` when the
 * header carries no such key. */
export function readTaskHeaderScalar(text, key) {
    const { lines } = splitTaskLines(text);
    const region = regionFromLines(lines, false);
    const prefix = `${key}:`;
    for (let i = region.startLine; i <= region.endLine; i++) {
        const line = lines[i];
        if (line.startsWith(prefix) && HEADER_KEY_RE.test(line))
            return line.slice(prefix.length).trim();
    }
    return undefined;
}
function bodyTypeLinesFromLines(lines, region) {
    const out = [];
    for (let i = region.endLine + 1; i < lines.length; i++) {
        const line = lines[i];
        if (line.startsWith(TYPE_PREFIX) && HEADER_KEY_RE.test(line)) {
            out.push({ line: i + 1, value: line.slice(TYPE_PREFIX.length).trim() });
        }
    }
    return out;
}
/** The single-source `type:` reading with provenance. Never throws and never
 * reads below the header for the value. */
export function readTaskType(text) {
    const { lines, byteOrderMark } = splitTaskLines(text);
    const region = regionFromLines(lines, byteOrderMark);
    for (let i = region.startLine; i <= region.endLine; i++) {
        const line = lines[i];
        if (line.startsWith(TYPE_PREFIX) && HEADER_KEY_RE.test(line)) {
            const value = line.slice(TYPE_PREFIX.length).trim();
            return value === ""
                ? { type: undefined, source: "invalid", bomStripped: byteOrderMark }
                : { type: value, source: "header", bomStripped: byteOrderMark };
        }
    }
    const hasBodyType = bodyTypeLinesFromLines(lines, region).length > 0;
    return { type: undefined, source: hasBodyType ? "body" : "missing", bomStripped: byteOrderMark };
}
/** Every `type:` line below the header region, in file order (1-based line
 * numbers). Used for the body-type audit line and the escalation predicate. */
export function scanBodyTypeLines(text) {
    const { lines, byteOrderMark } = splitTaskLines(text);
    return bodyTypeLinesFromLines(lines, regionFromLines(lines, byteOrderMark));
}
/** Power-tool non-subset predicate (design-role-key-identity 1.4):
 * `exists p ∈ toolsFor(bodyType) ∩ {write,edit,bash} : p ∉ toolsFor(headerType)`.
 * Returns the first escalating body line, or `undefined`. An unregistered
 * bodyType resolves through `toolsFor` (the fallback carries write/edit/bash,
 * so it escalates against any read-only header). */
export function findTypeEscalation(bodyLines, headerType, toolsFor) {
    const headerPower = toolsFor(headerType).filter((tool) => POWER_TOOL_NAMES.includes(tool));
    for (const candidate of bodyLines) {
        const bodyPower = toolsFor(candidate.value).filter((tool) => POWER_TOOL_NAMES.includes(tool));
        if (bodyPower.some((tool) => !headerPower.includes(tool)))
            return candidate;
    }
    return undefined;
}
//# sourceMappingURL=task-frontmatter.js.map