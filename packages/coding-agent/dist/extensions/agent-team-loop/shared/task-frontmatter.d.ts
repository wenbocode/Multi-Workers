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
/** Header-region line bounds over the normalized line array (0-based, both
 * inclusive). `startLine > endLine` means the document has no header. */
export interface TaskHeaderRegion {
    startLine: number;
    endLine: number;
    /** The first line was `---` and a closing `---` was found. */
    fenced: boolean;
    /** No fence and no blank line: the region was cut by the header key
     * grammar instead (degenerate branch, audited by the caller). */
    truncated: boolean;
    /** The raw text began with U+FEFF (it was stripped before parsing). */
    byteOrderMark: boolean;
}
/** Where the `type:` candidate was seen. `type` is only ever populated from
 * the header: header = header value present; invalid = header `type:` line
 * present with an empty value; body = only the body carries a `type:` line
 * (value deliberately withheld); missing = neither. */
export type TaskTypeSource = "header" | "body" | "missing" | "invalid";
/** `readTaskType` result: the resolved value plus the provenance an auditing
 * caller needs (worker `[HEADER]` trace lines, PM dispatch refusal). */
export interface TaskTypeReading {
    type: string | undefined;
    source: TaskTypeSource;
    bomStripped: boolean;
}
/** One body-region `type:` line: 1-based line number (matching editor gutters)
 * and the trimmed value. */
export interface TaskBodyTypeLine {
    line: number;
    value: string;
}
/** Extract the header region of a task.md document. */
export declare function extractTaskHeader(text: string): TaskHeaderRegion;
/** First scalar value for `key` inside the header region. Returns the trimmed
 * value (`""` when the key is present but empty) or `undefined` when the
 * header carries no such key. */
export declare function readTaskHeaderScalar(text: string, key: string): string | undefined;
/** The single-source `type:` reading with provenance. Never throws and never
 * reads below the header for the value. */
export declare function readTaskType(text: string): TaskTypeReading;
/** Every `type:` line below the header region, in file order (1-based line
 * numbers). Used for the body-type audit line and the escalation predicate. */
export declare function scanBodyTypeLines(text: string): TaskBodyTypeLine[];
/** Power-tool non-subset predicate (design-role-key-identity 1.4):
 * `exists p ∈ toolsFor(bodyType) ∩ {write,edit,bash} : p ∉ toolsFor(headerType)`.
 * Returns the first escalating body line, or `undefined`. An unregistered
 * bodyType resolves through `toolsFor` (the fallback carries write/edit/bash,
 * so it escalates against any read-only header). */
export declare function findTypeEscalation(bodyLines: ReadonlyArray<TaskBodyTypeLine>, headerType: string, toolsFor: (type: string) => readonly string[]): TaskBodyTypeLine | undefined;
//# sourceMappingURL=task-frontmatter.d.ts.map