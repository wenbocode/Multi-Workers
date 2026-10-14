/**
 * `write_face` glob normalizer + intersection operator — TS side
 * (mw-write-face-guard W-02, card T-W-I02).
 *
 * Frozen contract:
 * `.agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md`
 * §3.1 (canonical syntax + parse-time fail-closed rules), §3.2 (deny does NOT
 * participate in the overlap decision; conservative-fallback list), §3.3
 * (three states), §4.2 (segment-level character-pattern intersection), §4.3
 * (epsilon-NFA product over glob segment sequences), §4.4 (face-level operator).
 *
 * The repository already has five "one path vs one pattern" predicates
 * (`worker/read-scope.ts:isSameOrUnder`/`isWithinScope`/`matchedDenyGlob`,
 * `worker/worker-mode.ts:matchesWriteScopeEntry`, Python `xkey.py:fnmatch`);
 * none of them is a glob x glob operator, so this module is new. `minimatch`
 * is only the single-path semantic baseline — it is NEVER called here; the
 * intersection is the hand-written epsilon-NFA product below.
 *
 * Semantics honoured (design.md D-001/D-006):
 *
 * - single `/`-separated syntax; `\` is always a separator, never an escape;
 * - a bare `!` is refused (`write-face-invalid-entry`); `..` is refused
 *   (`write-face-escape`); a top-level `,` inside an entry is refused;
 * - a refusal carries the conductor's `Refused.detail` (`write_face.py:654/668/
 *   674/685`): `present-but-empty write_face head` for an empty head, and
 *   `entry '<raw>'` / `deny entry '<raw>'` for a rejected entry (the raw text,
 *   NOT Python's `repr` quote-selection — see the bounded-difference note in
 *   the W-14 evidence: a raw containing a single quote keeps the single-quote
 *   wrapper here, while Python `repr` switches to double quotes);
 * - `a/**` INCLUDES the bare `a`; leading `./`, empty segments and a trailing
 *   `/` are normalized away; repeated `**` segments collapse;
 * - a literal entry is an EXACT node (a directory must be written `a/**`);
 * - `dot:true` — a leading `.` segment is an ordinary segment;
 * - case sensitivity is an explicit parameter, never inferred from the
 *   platform;
 * - `**` inside a segment (`a**b`) behaves as `*` (does not cross `/`);
 * - the overlap decision never subtracts `deny`;
 * - the Python mirror is `packages/multi-workers/autopilot/write_face.py`; both
 *   sides read the same frozen corpus `test/fixtures/write-face-corpus.json`.
 */
// ---------------------------------------------------------------------------
// Stable refusal codes (parse-time, fail-closed, zero side effects).
// ---------------------------------------------------------------------------
export const WRITE_FACE_EMPTY = "write-face-empty";
export const WRITE_FACE_INVALID_ENTRY = "write-face-invalid-entry";
export const WRITE_FACE_ESCAPE = "write-face-escape";
export const WRITE_FACE_OUTSIDE_BASE = "write-face-outside-base";
/** The conductor's `Refused.detail` for a present-but-empty head
 * (`write_face.py:654/674`). The only refusal with no offending entry, so it is
 * the one detail constant instead of a `${label} '${raw}'` rendering. */
export const WRITE_FACE_EMPTY_DETAIL = "present-but-empty write_face head";
// ---------------------------------------------------------------------------
// Conservative-fallback limits (§3.2). Hitting any of these must be
// observable (an `unsupported` result), never a silent "no intersection".
// ---------------------------------------------------------------------------
const MAX_TOKEN_RUN = 256;
const MAX_GLOB_SEGMENTS = 512;
const MAX_PRODUCT_STATES = 1 << 16;
const MAX_SEG_BFS_STATES = 1 << 16;
const MAX_BRACE_DEPTH = 8;
const MAX_BRACE_EXPANSIONS = 256;
const ANY_SEGMENT = "**";
/** Probe pool for the segment product when both sides constrain a character
 * only negatively (`[!b]`). Mirrors the Python `_PROBE` ordering: letters,
 * digits, `.`, `_`, `-`, then printable ASCII, then Latin-1. */
const PROBE = buildProbe();
function buildProbe() {
    const out = [];
    for (const ch of "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
        out.push(ch);
    for (let code = 0x21; code < 0x7f; code++)
        out.push(String.fromCharCode(code));
    for (let code = 0x80; code < 0x200; code++)
        out.push(String.fromCharCode(code));
    return out;
}
// ---------------------------------------------------------------------------
// Small string helpers
// ---------------------------------------------------------------------------
function normalizeSeparators(text) {
    return text.replace(/\\/g, "/");
}
function fold(text, caseInsensitive) {
    return caseInsensitive ? text.toLowerCase() : text;
}
function eq(a, b, caseInsensitive) {
    if (a === b)
        return true;
    return caseInsensitive && a.toLowerCase() === b.toLowerCase();
}
function isAbsolutePath(p) {
    return p.startsWith("/") || /^[A-Za-z]:\//.test(p);
}
function toRelative(p, base, caseInsensitive) {
    const b = normalizeSeparators(base).replace(/\/+$/, "");
    if (eq(p, b, caseInsensitive))
        return "";
    if (fold(p, caseInsensitive).startsWith(fold(`${b}/`, caseInsensitive)))
        return p.slice(b.length + 1);
    return null;
}
function collapseDoubleStar(segments) {
    const out = [];
    for (const seg of segments) {
        if (seg === ANY_SEGMENT && out.length > 0 && out[out.length - 1] === ANY_SEGMENT)
            continue;
        out.push(seg);
    }
    return out;
}
/** Split into lines the same way the Python mirror's `str.splitlines()` does
 * for the line boundaries that actually occur in task.md files. */
function splitLines(text) {
    return text.replace(/\r\n|[\n\r\v\f\u0085\u2028\u2029]/g, "\n").split("\n");
}
const BLOCK_ITEM_RE = /^[ \t]+-[ \t]*(.*)$/;
/** First `name:` head line, with an indented `- item` block list when the
 * value is empty. An indented item is required (a bare `- type: coding` line
 * is not part of the list). */
function findHead(lines, name) {
    for (let idx = 0; idx < lines.length; idx++) {
        const line = lines[idx];
        if (!line.startsWith(name))
            continue;
        const tail = line.slice(name.length);
        const m = /^[ \t]*:(.*)$/.exec(tail);
        if (m === null)
            continue;
        const rest = m[1].trim();
        if (rest !== "")
            return { value: rest, block: null };
        const items = [];
        let k = idx + 1;
        while (k < lines.length) {
            const item = BLOCK_ITEM_RE.exec(lines[k]);
            if (item === null)
                break;
            items.push(item[1].trim());
            k++;
        }
        return { value: "", block: items.length > 0 ? items : null };
    }
    return null;
}
/** One-line form: a value wrapped in matching quotes is ONE entry (so a `,`
 * inside it is unrepresentable); otherwise split on `,`. */
function splitSingleLine(value) {
    const s = value.trim();
    if (s.length >= 2 && s[0] === s[s.length - 1] && (s[0] === '"' || s[0] === "'"))
        return [s.slice(1, -1)];
    return s.split(",");
}
/** Find the first `{...}` or `@(...)` outside a character class. */
function findAltStart(text) {
    let inClass = false;
    for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (inClass) {
            if (c === "]")
                inClass = false;
            continue;
        }
        if (c === "[") {
            inClass = true;
            continue;
        }
        if (c === "{")
            return { kind: "brace", start: i, end: matchClose(text, i, "{", "}") };
        if (c === "@" && i + 1 < text.length && text[i + 1] === "(")
            return { kind: "alt", start: i, end: matchClose(text, i + 1, "(", ")") };
    }
    return null;
}
function matchClose(text, openIdx, opener, closer) {
    let depth = 0;
    let inClass = false;
    for (let i = openIdx; i < text.length; i++) {
        const c = text[i];
        if (inClass) {
            if (c === "]")
                inClass = false;
            continue;
        }
        if (c === "[") {
            inClass = true;
            continue;
        }
        if (c === opener)
            depth++;
        else if (c === closer) {
            depth--;
            if (depth === 0)
                return i;
        }
    }
    return null;
}
/** Split on a separator that is at brace/paren depth 0 and outside a class. */
function splitTopLevel(body, sep) {
    const parts = [];
    let current = "";
    let braceDepth = 0;
    let parenDepth = 0;
    let inClass = false;
    for (const c of body) {
        if (inClass) {
            current += c;
            if (c === "]")
                inClass = false;
            continue;
        }
        if (c === "[") {
            inClass = true;
            current += c;
            continue;
        }
        if (c === "{")
            braceDepth++;
        else if (c === "}")
            braceDepth--;
        else if (c === "(")
            parenDepth++;
        else if (c === ")")
            parenDepth--;
        if (c === sep && braceDepth === 0 && parenDepth === 0) {
            parts.push(current);
            current = "";
            continue;
        }
        current += c;
    }
    parts.push(current);
    return parts;
}
/** Expand `{a,b}` / `@(a|b)` into concrete alternatives. `ok=false` marks an
 * unsupported construct (unmatched bracket, depth limit, branch-count limit,
 * single-branch form). Mirrors the Python `_expand_alts` stack algorithm so the
 * output ORDER matches. */
function expandAlts(text) {
    const out = [];
    let ok = true;
    const stack = [{ text, depth: 0 }];
    while (stack.length > 0) {
        const cur = stack.pop();
        if (cur === undefined)
            break;
        const found = findAltStart(cur.text);
        if (found === null) {
            out.push(cur.text);
            if (out.length > MAX_BRACE_EXPANSIONS) {
                ok = false;
                break;
            }
            continue;
        }
        if (found.end === null || cur.depth + 1 > MAX_BRACE_DEPTH) {
            ok = false;
            out.push(cur.text);
            continue;
        }
        const body = found.kind === "brace"
            ? cur.text.slice(found.start + 1, found.end)
            : cur.text.slice(found.start + 2, found.end);
        const sep = found.kind === "brace" ? "," : "|";
        const parts = splitTopLevel(body, sep);
        if (parts.length === 1) {
            ok = false;
            out.push(cur.text);
            continue;
        }
        for (let p = parts.length - 1; p >= 0; p--) {
            stack.push({
                text: cur.text.slice(0, found.start) + parts[p] + cur.text.slice(found.end + 1),
                depth: cur.depth + 1,
            });
        }
    }
    return { alternatives: out, ok };
}
function parseClass(seg, start) {
    const n = seg.length;
    let i = start + 1;
    let negated = false;
    if (i < n && (seg[i] === "!" || seg[i] === "^")) {
        negated = true;
        i++;
    }
    const chars = [];
    let first = true;
    while (i < n) {
        const c = seg[i];
        if (c === "]" && !first) {
            if (chars.length === 0)
                return null;
            return { token: { kind: "class", members: chars, negated }, next: i + 1 };
        }
        if (c === "]" && first) {
            chars.push("]");
            first = false;
            i++;
            continue;
        }
        if (i + 2 < n && seg[i + 1] === "-" && seg[i + 2] !== "]") {
            const lo = seg[i];
            const hi = seg[i + 2];
            if (lo.charCodeAt(0) > hi.charCodeAt(0))
                return null;
            for (let code = lo.charCodeAt(0); code <= hi.charCodeAt(0); code++)
                chars.push(String.fromCharCode(code));
            first = false;
            i += 3;
            continue;
        }
        chars.push(c);
        first = false;
        i++;
    }
    return null;
}
/** Tokenize one non-`**` segment. `null` marks an unsupported construct: a
 * `*(`/`?(`/`+(`/`!(` extglob form, an illegal class, a stray magic char. */
function tokenizeSegment(seg) {
    const tokens = [];
    const n = seg.length;
    let i = 0;
    while (i < n) {
        const c = seg[i];
        if (c === "*") {
            if (i + 1 < n && seg[i + 1] === "(")
                return null;
            tokens.push({ kind: "star" });
            i++;
        }
        else if (c === "?") {
            if (i + 1 < n && seg[i + 1] === "(")
                return null;
            tokens.push({ kind: "qmark" });
            i++;
        }
        else if (c === "[") {
            const parsed = parseClass(seg, i);
            if (parsed === null)
                return null;
            tokens.push(parsed.token);
            i = parsed.next;
        }
        else if (c === "]" || c === "}" || c === "{") {
            return null; // stray magic char: unsupported (keeps the witness glob-free)
        }
        else if ((c === "+" || c === "!") && i + 1 < n && seg[i + 1] === "(") {
            return null; // extglob form: unsupported
        }
        else {
            tokens.push({ kind: "lit", ch: c });
            i++;
        }
    }
    if (tokens.length === 0)
        return null;
    return tokens;
}
/** A bare `!` (not the start of an extglob form) is a refusal; `!(`, `+(`,
 * `*(`, `?(` are extglob forms that the tokenizer later marks unsupported. */
function hasBareBang(text) {
    let inClass = false;
    for (let i = 0; i < text.length; i++) {
        const c = text[i];
        if (inClass) {
            if (c === "]")
                inClass = false;
            continue;
        }
        if (c === "[") {
            inClass = true;
            continue;
        }
        if (c === "!") {
            if (!(i + 1 < text.length && text[i + 1] === "("))
                return true;
        }
    }
    return false;
}
/** A `,` outside `{}`/`()`/`[]` is unrepresentable in the one-line form. */
function hasTopLevelComma(text) {
    let braceDepth = 0;
    let parenDepth = 0;
    let inClass = false;
    for (const c of text) {
        if (inClass) {
            if (c === "]")
                inClass = false;
            continue;
        }
        if (c === "[") {
            inClass = true;
            continue;
        }
        if (c === "{")
            braceDepth++;
        else if (c === "}")
            braceDepth--;
        else if (c === "(")
            parenDepth++;
        else if (c === ")")
            parenDepth--;
        else if (c === "," && braceDepth === 0 && parenDepth === 0)
            return true;
    }
    return false;
}
function compileNormalized(norm) {
    const { alternatives, ok } = expandAlts(norm);
    const globs = [];
    for (const text of alternatives) {
        let unsupported = !ok;
        const segments = [];
        for (const seg of text.split("/")) {
            if (seg === "" || seg === ".")
                continue;
            if (seg === "..")
                return { kind: "rejected", code: WRITE_FACE_ESCAPE };
            if (seg === ANY_SEGMENT) {
                if (segments.length > 0 && segments[segments.length - 1].kind === "any")
                    continue;
                segments.push({ kind: "any" });
                continue;
            }
            const tokens = tokenizeSegment(seg);
            if (tokens === null) {
                unsupported = true;
                segments.push({ kind: "pattern", tokens: [] });
                continue;
            }
            if (tokens.length > MAX_TOKEN_RUN)
                unsupported = true;
            segments.push({ kind: "pattern", tokens });
        }
        if (segments.length === 0)
            return { kind: "rejected", code: WRITE_FACE_INVALID_ENTRY };
        if (segments.length > MAX_GLOB_SEGMENTS)
            unsupported = true;
        globs.push({ text, segments, unsupported });
    }
    if (globs.length === 0)
        return { kind: "rejected", code: WRITE_FACE_INVALID_ENTRY };
    return { kind: "ok", globs };
}
function normalizeEntry(raw, base, caseInsensitive) {
    let entry = raw.trim();
    if (entry === "" || entry === "-")
        return { kind: "skip" };
    if (entry.length >= 2 && entry[0] === entry[entry.length - 1] && (entry[0] === '"' || entry[0] === "'")) {
        entry = entry.slice(1, -1);
    }
    if (hasTopLevelComma(entry))
        return { kind: "rejected", code: WRITE_FACE_INVALID_ENTRY };
    if (entry.includes('"') || entry.includes("'"))
        return { kind: "rejected", code: WRITE_FACE_INVALID_ENTRY };
    entry = normalizeSeparators(entry);
    if (hasBareBang(entry))
        return { kind: "rejected", code: WRITE_FACE_INVALID_ENTRY };
    if (isAbsolutePath(entry)) {
        const rel = toRelative(entry, base, caseInsensitive);
        if (rel === null)
            return { kind: "rejected", code: WRITE_FACE_OUTSIDE_BASE };
        entry = rel;
    }
    const segments = [];
    for (const seg of entry.split("/")) {
        if (seg === "" || seg === ".")
            continue;
        if (seg === "..")
            return { kind: "rejected", code: WRITE_FACE_ESCAPE };
        segments.push(seg);
    }
    const collapsed = collapseDoubleStar(segments);
    if (collapsed.length === 0)
        return { kind: "rejected", code: WRITE_FACE_INVALID_ENTRY };
    const norm = collapsed.join("/");
    const compiled = compileNormalized(norm);
    if (compiled.kind === "rejected")
        return compiled;
    return { kind: "ok", globs: compiled.globs, norm };
}
/** Normalize one raw entry list. `label` is the conductor's refusal prefix
 * (`entry` / `deny entry`, `write_face.py:668/685`); the raw text is kept
 * verbatim (no `repr` quote-selection — the caller renders). */
function normalizeEntries(rawEntries, base, caseInsensitive, label) {
    const globs = [];
    const entries = [];
    for (const raw of rawEntries) {
        const r = normalizeEntry(raw, base, caseInsensitive);
        if (r.kind === "skip")
            continue;
        if (r.kind === "rejected")
            return { kind: "rejected", code: r.code, detail: `${label} '${raw}'` };
        globs.push(...r.globs);
        entries.push(r.norm);
    }
    return { kind: "ok", globs, entries };
}
function buildFace(rawAllow, rawDeny, opts) {
    if (rawAllow.length === 0)
        return { kind: "rejected", code: WRITE_FACE_EMPTY, detail: WRITE_FACE_EMPTY_DETAIL };
    const allow = normalizeEntries(rawAllow, opts.base, opts.caseInsensitive, "entry");
    if (allow.kind === "rejected")
        return allow;
    if (allow.entries.length === 0)
        return { kind: "rejected", code: WRITE_FACE_EMPTY, detail: WRITE_FACE_EMPTY_DETAIL };
    const denyNormalized = normalizeEntries(rawDeny, opts.base, opts.caseInsensitive, "deny entry");
    if (denyNormalized.kind === "rejected")
        return denyNormalized;
    const face = {
        allow: allow.globs,
        entries: allow.entries,
        deny: denyNormalized.entries,
        base: opts.base,
        caseInsensitive: opts.caseInsensitive,
    };
    return { kind: "declared", face };
}
// ---------------------------------------------------------------------------
// Public parser (§3.3 three states)
// ---------------------------------------------------------------------------
/**
 * Parse the `write_face:` head of a task.md. Three states (§3.3):
 *
 * - no `write_face:` head, or a dash-only value (`write_face: -`) -> undeclared
 *   (D-003 serial-only; the overlap operator is never called for it);
 * - a present-but-empty head -> refused `write-face-empty`;
 * - a non-empty head -> a normalized, expanded `WriteFace`.
 *
 * An optional `write_face_deny:` head is parsed for completeness, but the
 * overlap operator never uses it (§3.2).
 */
export function parseWriteFace(text, opts) {
    const lines = splitLines(text);
    const allowHead = findHead(lines, "write_face");
    if (allowHead === null)
        return { kind: "undeclared" };
    if (allowHead.block === null && allowHead.value.trim() === "-")
        return { kind: "undeclared" };
    const rawAllow = allowHead.block !== null ? allowHead.block : splitSingleLine(allowHead.value);
    const denyHead = findHead(lines, "write_face_deny");
    let rawDeny = [];
    if (denyHead !== null && !(denyHead.block === null && denyHead.value.trim() === "-")) {
        rawDeny = denyHead.block !== null ? denyHead.block : splitSingleLine(denyHead.value);
    }
    return buildFace(rawAllow, rawDeny, opts);
}
/**
 * Entry-array variant of {@link parseWriteFace}, for callers (and the shared
 * corpus) that already hold one entry per string. Each element is ONE entry —
 * a top-level `,` inside an element is a refusal rather than a separator.
 */
export function parseWriteFaceEntries(entries, opts, denyEntries = []) {
    return buildFace(entries, denyEntries, opts);
}
// ---------------------------------------------------------------------------
// Segment-level character-pattern intersection (§4.2)
// ---------------------------------------------------------------------------
function tokenAllows(tok, ch, caseInsensitive) {
    if (tok.kind === "lit")
        return eq(tok.ch, ch, caseInsensitive);
    if (tok.kind === "class") {
        const member = tok.members.some((c) => eq(c, ch, caseInsensitive));
        return tok.negated ? !member : member;
    }
    return true; // star / qmark
}
/** A concrete character accepted by both tokens, or `null` when provably none. */
function commonChar(ta, tb, caseInsensitive) {
    if (ta.kind === "lit")
        return { kind: "ok", value: tokenAllows(tb, ta.ch, caseInsensitive) ? ta.ch : null };
    if (tb.kind === "lit")
        return { kind: "ok", value: tokenAllows(ta, tb.ch, caseInsensitive) ? tb.ch : null };
    if (ta.kind === "class" && !ta.negated) {
        for (const c of ta.members)
            if (tokenAllows(tb, c, caseInsensitive))
                return { kind: "ok", value: c };
        return { kind: "ok", value: null };
    }
    if (tb.kind === "class" && !tb.negated) {
        for (const c of tb.members)
            if (tokenAllows(ta, c, caseInsensitive))
                return { kind: "ok", value: c };
        return { kind: "ok", value: null };
    }
    for (const c of PROBE)
        if (tokenAllows(ta, c, caseInsensitive) && tokenAllows(tb, c, caseInsensitive))
            return { kind: "ok", value: c };
    return { kind: "unsupported", reason: "segment-pattern-probe-exhausted" };
}
/**
 * Product of two single-segment token runs (§4.2): returns a concrete non-empty
 * common string, `none` for a proved-empty intersection, or `unsupported` at a
 * step/state limit. State = `(i, j, consumed)`; a `*` has an epsilon advance and
 * a self-loop consume.
 */
function segOverlap(a, b, caseInsensitive) {
    if (a.length > MAX_TOKEN_RUN || b.length > MAX_TOKEN_RUN)
        return { kind: "unsupported", reason: "segment-pattern-length-limit" };
    const key = (i, j, consumed) => `${i},${j},${consumed ? 1 : 0}`;
    const parent = new Map();
    const charIn = new Map();
    const start = key(0, 0, false);
    parent.set(start, null);
    charIn.set(start, "");
    const queue = [{ i: 0, j: 0, consumed: false }];
    for (let head = 0; head < queue.length; head++) {
        const { i, j, consumed } = queue[head];
        const state = key(i, j, consumed);
        if (i === a.length && j === b.length && consumed) {
            const chars = [];
            let cur = state;
            while (cur !== null) {
                chars.push(charIn.get(cur) ?? "");
                cur = parent.get(cur) ?? null;
            }
            chars.reverse();
            return { kind: "ok", value: chars.join("") };
        }
        const push = (ni, nj, nConsumed, ch) => {
            const k = key(ni, nj, nConsumed);
            if (!parent.has(k)) {
                parent.set(k, state);
                charIn.set(k, ch);
                queue.push({ i: ni, j: nj, consumed: nConsumed });
            }
        };
        if (i < a.length && a[i].kind === "star")
            push(i + 1, j, consumed, "");
        if (j < b.length && b[j].kind === "star")
            push(i, j + 1, consumed, "");
        if (i < a.length && j < b.length) {
            const ta = a[i];
            const tb = b[j];
            if (ta.kind === "star" && tb.kind === "star") {
                push(i, j, true, "x");
            }
            else {
                const ch = commonChar(ta, tb, caseInsensitive);
                if (ch.kind === "unsupported")
                    return ch;
                if (ch.kind === "ok" && ch.value !== null) {
                    const ni = ta.kind === "star" ? i : i + 1;
                    const nj = tb.kind === "star" ? j : j + 1;
                    push(ni, nj, true, ch.value);
                }
            }
        }
        if (parent.size > MAX_SEG_BFS_STATES)
            return { kind: "unsupported", reason: "segment-pattern-state-limit" };
    }
    return { kind: "none" };
}
/** A concrete non-empty segment generated by one token run (self-intersection). */
function segmentExample(tokens, caseInsensitive) {
    const r = segOverlap(tokens, tokens, caseInsensitive);
    if (r.kind === "ok")
        return r;
    if (r.kind === "unsupported")
        return r;
    return { kind: "unsupported", reason: "segment-pattern-empty" };
}
// ---------------------------------------------------------------------------
// Glob (segment sequence) product (§4.3)
// ---------------------------------------------------------------------------
/**
 * Product of two globs (§4.3). `**` has a zero-segment epsilon advance and a
 * one-segment self-loop consume; acceptance is reaching `(|A|, |B|)` after at
 * least one consume edge. Returns the witness segment sequence, `none` for a
 * proved-empty intersection, or `unsupported`.
 */
function globsOverlap(ga, gb, caseInsensitive) {
    const la = ga.length;
    const lb = gb.length;
    if ((la + 1) * (lb + 1) > MAX_PRODUCT_STATES)
        return { kind: "unsupported", reason: "glob-product-state-limit" };
    const key = (i, j, consumed) => `${i},${j},${consumed ? 1 : 0}`;
    const parent = new Map();
    const segIn = new Map();
    const start = key(0, 0, false);
    parent.set(start, null);
    segIn.set(start, null);
    const queue = [{ i: 0, j: 0, consumed: false }];
    for (let head = 0; head < queue.length; head++) {
        const { i, j, consumed } = queue[head];
        const state = key(i, j, consumed);
        if (i === la && j === lb && consumed) {
            const segments = [];
            let cur = state;
            while (cur !== null) {
                const witness = segIn.get(cur);
                if (witness !== null && witness !== undefined)
                    segments.push(witness);
                cur = parent.get(cur) ?? null;
            }
            segments.reverse();
            return { kind: "ok", value: segments };
        }
        const push = (ni, nj, nConsumed, witness) => {
            const k = key(ni, nj, nConsumed);
            if (!parent.has(k)) {
                parent.set(k, state);
                segIn.set(k, witness);
                queue.push({ i: ni, j: nj, consumed: nConsumed });
            }
        };
        if (i < la && ga[i].kind === "any")
            push(i + 1, j, consumed, null);
        if (j < lb && gb[j].kind === "any")
            push(i, j + 1, consumed, null);
        if (i < la && j < lb) {
            const sa = ga[i];
            const sb = gb[j];
            if (sa.kind === "any" && sb.kind === "any") {
                push(i, j, true, "x");
            }
            else if (sa.kind === "any" && sb.kind === "pattern") {
                const witness = segmentExample(sb.tokens, caseInsensitive);
                if (witness.kind === "unsupported")
                    return witness;
                push(i, j + 1, true, witness.value);
            }
            else if (sa.kind === "pattern" && sb.kind === "any") {
                const witness = segmentExample(sa.tokens, caseInsensitive);
                if (witness.kind === "unsupported")
                    return witness;
                push(i + 1, j, true, witness.value);
            }
            else if (sa.kind === "pattern" && sb.kind === "pattern") {
                const witness = segOverlap(sa.tokens, sb.tokens, caseInsensitive);
                if (witness.kind === "unsupported")
                    return witness;
                if (witness.kind === "ok")
                    push(i + 1, j + 1, true, witness.value);
            }
        }
    }
    return { kind: "none" };
}
// ---------------------------------------------------------------------------
// Face-level operator (§4.4)
// ---------------------------------------------------------------------------
/**
 * Decide whether two parsed write faces share a lexically-provable path.
 *
 * `a` and `b` must both be declared (an undeclared side is handled by the
 * caller as serial-only, design D-003). `deny` never participates (§3.2).
 * D-111 precedence: a provable conflict among *supported* entries wins; a
 * conservative fallback (`{ unsupported }`) is returned only when no conflict
 * is provable and at least one side carries syntax the product cannot decide.
 * Callers MUST treat `unsupported` as overlap.
 */
export function writeFacesOverlap(a, b) {
    const baseA = fold(normalizeSeparators(a.base).replace(/\/+$/, ""), a.caseInsensitive);
    const baseB = fold(normalizeSeparators(b.base).replace(/\/+$/, ""), b.caseInsensitive);
    if (baseA !== baseB)
        return { unsupported: "incomparable-base" };
    if (a.caseInsensitive !== b.caseInsensitive)
        return { unsupported: "incomparable-case-mode" };
    const caseInsensitive = a.caseInsensitive;
    // D-111 overlap phase: prove a conflict first. A pair that cannot be decided
    // (unsupported syntax, or a state-machine fallback) is deferred, never
    // short-circuits the search, so a provable conflict always wins.
    let deferred = null;
    for (const ga of a.allow) {
        for (const gb of b.allow) {
            if (ga.unsupported || gb.unsupported) {
                deferred = deferred ?? "unsupported-syntax";
                continue;
            }
            const witness = globsOverlap(ga.segments, gb.segments, caseInsensitive);
            if (witness.kind === "unsupported") {
                deferred = deferred ?? witness.reason;
                continue;
            }
            if (witness.kind === "none")
                continue;
            return { sample: witness.value.join("/"), rule: ga.text, other: gb.text, reason: "write-face-overlap" };
        }
    }
    if (deferred !== null)
        return { unsupported: deferred };
    return null;
}
/** Single conservative predicate: anything but `null` collides. */
export function isWriteFaceOverlap(result) {
    return result !== null;
}
//# sourceMappingURL=write-face.js.map