"""autopilot/write_face.py - write-face glob normalizer + intersection operator.

Frozen contract: `.agenticdoc/mw-write-face-guard/evidence/research/design-glob-intersection-20261014.md`
Section 3.1 (canonical syntax + parse-time fail-closed rules), 3.2 (deny does
NOT participate in the overlap decision; conservative-fallback list), 3.3
(three states), 4.2 (segment-level character-pattern intersection), 4.3
(epsilon-NFA product over glob segment sequences), 4.4 (face-level operator).

Design decisions honoured here (design.md D-001/D-006/D-111/D-112):

* single `/`-separated syntax; `\\` is always a separator, never an escape;
* leading/embedded `!` refused; `..` refused; entry-internal `,` refused;
* `a/**` INCLUDES the bare `a`; leading `./`, empty segments and trailing `/`
  are normalized away; repeated `**` segments collapse;
* a literal entry is an EXACT node (a directory must be written `a/**`);
* `dot:true` - a leading `.` segment is an ordinary segment;
* case sensitivity is an explicit parameter, never inferred from the platform;
* `**` inside a segment (`a**b`) behaves as `*` (does not cross `/`);
* the overlap decision never subtracts `deny`;
* D-112 entry splitting is syntax-blind (`split(',')` on the raw head value,
  trim, drop empty fields); brackets/braces/quotes never protect a comma;
* D-111 precedence: parse-time hard violations win over unsupported syntax and
  are entry-order independent; at intersection time a provable conflict wins
  over unsupported syntax (`Unsupported` means "cannot decide");
* `fnmatch` / `pathlib.PurePath.match` are NOT used anywhere in this module -
  the Python `fnmatch` semantics (`*` crosses `/`, win32 case folding) diverge
  from the minimatch-based TS side, which is the semantic baseline.

The only imported matching machinery is the standard library `re` (used for
head-line detection and drive-letter detection) plus the hand-written state
machines below.
"""

from __future__ import annotations

import dataclasses
import re
from collections import deque
from collections.abc import Iterable, Sequence

# ---------------------------------------------------------------------------
# Stable refusal codes (parse-time, fail-closed, zero side effects).
# ---------------------------------------------------------------------------

WRITE_FACE_EMPTY = "write-face-empty"
WRITE_FACE_INVALID_ENTRY = "write-face-invalid-entry"
WRITE_FACE_ESCAPE = "write-face-escape"
WRITE_FACE_OUTSIDE_BASE = "write-face-outside-base"

# ---------------------------------------------------------------------------
# Conservative-fallback limits (section 3.2).  Hitting any of these must be
# observable (Unsupported), never a silent NONE.
# ---------------------------------------------------------------------------

MAX_TOKEN_RUN = 256          # per-segment character-pattern token count
MAX_GLOB_SEGMENTS = 512      # per-glob segment count
MAX_PRODUCT_STATES = 1 << 16  # (|A|+1)*(|B|+1) product-state cap
MAX_SEG_BFS_STATES = 1 << 16  # segment-pattern product-state cap
MAX_BRACE_DEPTH = 8          # nested brace / @() depth
MAX_BRACE_EXPANSIONS = 256   # branches produced by brace expansion

_ANY = "**"  # the only str segment value; everything else is a CharPattern

_PROBE = (
    tuple("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-")
    + tuple(chr(c) for c in range(0x21, 0x7F))
    + tuple(chr(c) for c in range(0x80, 0x200))
)


class _ConservativeUnknown(Exception):
    """Raised internally when a conservative fallback must trigger (section 3.2)."""

    def __init__(self, reason: str, detail: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.detail = detail


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Lit:
    ch: str


@dataclasses.dataclass(frozen=True)
class Star:
    pass


@dataclasses.dataclass(frozen=True)
class QMark:
    pass


@dataclasses.dataclass(frozen=True)
class CharClass:
    chars: tuple[str, ...]
    negated: bool


Token = Lit | Star | QMark | CharClass


@dataclasses.dataclass(frozen=True)
class CharPattern:
    tokens: tuple[Token, ...]


Segment = str | CharPattern  # str is always _ANY


@dataclasses.dataclass(frozen=True)
class CompiledGlob:
    """One normalized allow entry, expanded (braces) and tokenized."""

    segments: tuple[Segment, ...]
    entry: str
    unsupported: bool = False


@dataclasses.dataclass(frozen=True)
class WriteFace:
    """A parsed, normalized, non-empty write face (section 3.3 'non-empty')."""

    allow: tuple[CompiledGlob, ...]
    allow_entries: tuple[str, ...]
    deny: tuple[str, ...]
    deny_entries: tuple[str, ...]
    base: str
    case_insensitive: bool


@dataclasses.dataclass(frozen=True)
class Undeclared:
    """State 1 of section 3.3: no `write_face:` head (or a dash-only head)."""

    reason: str = "write-face-undeclared"


@dataclasses.dataclass(frozen=True)
class Refused:
    """State 2 of section 3.3 / any parse-time rule violation."""

    code: str
    detail: str = ""
    entry: str | None = None


ParseResult = Undeclared | Refused


@dataclasses.dataclass(frozen=True)
class Conflict:
    """A lexically-provable non-empty intersection (section 4.4)."""

    sample: str
    rule: str
    other: str
    reason: str = "write-face-overlap"


@dataclasses.dataclass(frozen=True)
class Unsupported:
    """Conservative fallback (section 3.2): callers MUST treat this as overlap."""

    reason: str
    detail: str = ""
    rule: str | None = None
    other: str | None = None


# ---------------------------------------------------------------------------
# Small string helpers
# ---------------------------------------------------------------------------


def _norm_sep(text: str) -> str:
    return text.replace("\\", "/")


def _fold(text: str, ci: bool) -> str:
    return text.lower() if ci else text


def _eq(a: str, b: str, ci: bool) -> bool:
    if a == b:
        return True
    return ci and a.lower() == b.lower()


def _is_absolute(path: str) -> bool:
    if path.startswith("/"):
        return True
    return re.match(r"^[A-Za-z]:/", path) is not None


def _to_relative(path: str, base: str, ci: bool) -> str | None:
    """Return `path` relative to `base`, or None when outside base."""
    b = _norm_sep(base).rstrip("/")
    p = path
    if _fold(p, ci) == _fold(b, ci):
        return ""
    if _fold(p, ci).startswith(_fold(b + "/", ci)):
        return p[len(b) + 1 :]
    return None


# ---------------------------------------------------------------------------
# Head-line detection (section 3.1 carrier format)
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class _Head:
    name: str
    value: str
    block: tuple[str, ...] | None
    line_index: int


_BLOCK_ITEM_RE = re.compile(r"^[ \t]+-[ \t]*(.*)$")


def _find_head(text: str, name: str) -> _Head | None:
    lines = text.splitlines()
    head_re = re.compile(rf"^{re.escape(name)}[ \t]*:(.*)$")
    for idx, line in enumerate(lines):
        m = head_re.match(line)
        if m is None:
            continue
        rest = m.group(1).strip()
        if rest != "":
            return _Head(name, rest, None, idx)
        items: list[str] = []
        k = idx + 1
        while k < len(lines):
            item = _BLOCK_ITEM_RE.match(lines[k])
            if item is None:
                break
            items.append(item.group(1).strip())
            k += 1
        return _Head(name, "", tuple(items) if items else None, idx)
    return None


def _split_single_line(value: str) -> list[str]:
    """Split a single-line head value into entries (design D-112).

    The split is deliberately **syntax-blind**: `split(',')` on the raw value,
    then trim each field and drop the empty ones.  Brackets, braces and quotes
    never protect a comma, so an unterminated `[` can never swallow a later
    field (`P22`/`P23`), and an unclosed `{` does not either (`P21` - the
    fragment after the comma only *adds* an allow entry, so its error
    direction is fail-closed).  A quoted scalar like `"a,b"` therefore becomes
    the fields `"a` and `b"`; the first is refused as `write-face-invalid-entry`
    (P16), which is the same code the old quote-aware splitter produced.

    The optional block-list carrier form (`write_face:` + `  - entry` lines) is
    untouched: each list item is already one field, so a comma inside a balanced
    `{b,c}` alternation survives there (design 3.1 equivalence).
    """
    fields = (field.strip() for field in value.split(","))
    return [field for field in fields if field != ""]


def _has_bare_comma(text: str) -> bool:
    """True for a `,` outside `{...}` alternation and character classes (D-8)."""
    brace = 0
    in_class = False
    for c in text:
        if in_class:
            if c == "]":
                in_class = False
            continue
        if c == "[":
            in_class = True
            continue
        if c == "{":
            brace += 1
        elif c == "}":
            brace = max(0, brace - 1)
        elif c == "," and brace == 0:
            return True
    return False


# ---------------------------------------------------------------------------
# Brace / @() alternation expansion (section 3.1 grammar)
# ---------------------------------------------------------------------------


def _find_alt_start(text: str) -> tuple[str, int, int | None] | None:
    """Find the first `{...}` or `@(...)` outside a character class."""
    i = 0
    n = len(text)
    in_class = False
    while i < n:
        c = text[i]
        if in_class:
            if c == "]":
                in_class = False
            i += 1
            continue
        if c == "[":
            in_class = True
            i += 1
            continue
        if c == "{":
            return ("brace", i, _match_close(text, i, "{", "}"))
        if c == "@" and i + 1 < n and text[i + 1] == "(":
            return ("alt", i, _match_close(text, i + 1, "(", ")"))
        i += 1
    return None


def _match_close(text: str, open_idx: int, opener: str, closer: str) -> int | None:
    depth = 0
    i = open_idx
    n = len(text)
    in_class = False
    while i < n:
        c = text[i]
        if in_class:
            if c == "]":
                in_class = False
            i += 1
            continue
        if c == "[":
            in_class = True
            i += 1
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return None


def _split_top_level(body: str, sep: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    depth_brace = 0
    depth_paren = 0
    in_class = False
    for c in body:
        if in_class:
            cur.append(c)
            if c == "]":
                in_class = False
            continue
        if c == "[":
            in_class = True
            cur.append(c)
            continue
        if c == "{":
            depth_brace += 1
        elif c == "}":
            depth_brace -= 1
        elif c == "(":
            depth_paren += 1
        elif c == ")":
            depth_paren -= 1
        if c == sep and depth_brace == 0 and depth_paren == 0:
            parts.append("".join(cur))
            cur = []
            continue
        cur.append(c)
    parts.append("".join(cur))
    return parts


def _expand_alts(text: str) -> tuple[list[str], bool]:
    """Expand `{a,b}` / `@(a|b)` into concrete alternatives.

    Returns `(expanded, ok)`; `ok=False` marks an unsupported construct
    (unmatched bracket, depth limit, branch-count limit, single-branch form).
    """
    out: list[str] = []
    ok = True
    stack: list[tuple[str, int]] = [(text, 0)]
    while stack:
        cur, depth = stack.pop()
        found = _find_alt_start(cur)
        if found is None:
            out.append(cur)
            if len(out) > MAX_BRACE_EXPANSIONS:
                ok = False
                break
            continue
        kind, start, end = found
        if end is None:
            ok = False
            out.append(cur)
            continue
        if depth + 1 > MAX_BRACE_DEPTH:
            ok = False
            out.append(cur)
            continue
        body = cur[start + 1 : end] if kind == "brace" else cur[start + 2 : end]
        sep = "," if kind == "brace" else "|"
        parts = _split_top_level(body, sep)
        if len(parts) == 1:  # `{a}` is not an alternation
            ok = False
            out.append(cur)
            continue
        for part in reversed(parts):
            stack.append((cur[:start] + part + cur[end + 1 :], depth + 1))
    return out, ok


# ---------------------------------------------------------------------------
# Character-pattern tokenizer (section 3.1 charpat)
# ---------------------------------------------------------------------------


def _tokenize_segment(seg: str) -> tuple[tuple[Token, ...] | None, bool]:
    tokens: list[Token] = []
    i = 0
    n = len(seg)
    while i < n:
        c = seg[i]
        if c == "*":
            if i + 1 < n and seg[i + 1] == "(":
                return None, False
            tokens.append(Star())
            i += 1
        elif c == "?":
            if i + 1 < n and seg[i + 1] == "(":
                return None, False
            tokens.append(QMark())
            i += 1
        elif c == "[":
            parsed = _parse_class(seg, i)
            if parsed is None:
                return None, False
            cls, i = parsed
            tokens.append(cls)
        elif c in "]}":
            return None, False  # stray magic char: unsupported, keeps witness glob-free
        elif c in "+!" and i + 1 < n and seg[i + 1] == "(":
            return None, False  # extglob form: unsupported
        else:
            tokens.append(Lit(c))
            i += 1
    if not tokens:
        return None, False
    return tuple(tokens), True


def _parse_class(seg: str, start: int) -> tuple[CharClass, int] | None:
    n = len(seg)
    i = start + 1
    negated = False
    if i < n and seg[i] in "!^":
        negated = True
        i += 1
    chars: list[str] = []
    first = True
    while i < n:
        c = seg[i]
        if c == "]" and not first:
            if not chars:
                return None
            return CharClass(tuple(chars), negated), i + 1
        if c == "]" and first:
            chars.append("]")
            first = False
            i += 1
            continue
        if i + 2 < n and seg[i + 1] == "-" and seg[i + 2] != "]":
            lo, hi = seg[i], seg[i + 2]
            if ord(lo) > ord(hi):
                return None
            chars.extend(chr(x) for x in range(ord(lo), ord(hi) + 1))
            first = False
            i += 3
            continue
        if c in "*?":
            # magic inside a class is a literal member; keep enum small and safe
            chars.append(c)
            first = False
            i += 1
            continue
        chars.append(c)
        first = False
        i += 1
    return None


def _scan_bangs(text: str) -> tuple[bool, bool]:
    """Return `(bare_bang, extglob)` for `!a/**` vs `!(...)` / `+()` etc."""
    bare = False
    extglob = False
    in_class = False
    i = 0
    n = len(text)
    while i < n:
        c = text[i]
        if in_class:
            if c == "]":
                in_class = False
            i += 1
            continue
        if c == "[":
            in_class = True
            i += 1
            continue
        if c == "!":
            if i + 1 < n and text[i + 1] == "(":
                extglob = True
            else:
                bare = True
            i += 1
            continue
        if c in "+*?" and i + 1 < n and text[i + 1] == "(":
            extglob = True
            i += 2
            continue
        i += 1
    return bare, extglob


# ---------------------------------------------------------------------------
# Entry normalization + compilation (section 3.1)
# ---------------------------------------------------------------------------


def _collapse_double_star(segments: Iterable[str]) -> list[str]:
    out: list[str] = []
    for seg in segments:
        if seg == _ANY and out and out[-1] == _ANY:
            continue
        out.append(seg)
    return out


def _compile_normalized(norm: str) -> tuple[list[CompiledGlob] | None, str | None]:
    """Compile a normalized entry into one or more expanded globs."""
    expanded, ok = _expand_alts(norm)
    globs: list[CompiledGlob] = []
    for text in expanded:
        unsupported = not ok
        segments: list[Segment] = []
        for seg in text.split("/"):
            if seg in ("", "."):
                continue
            if seg == "..":
                return None, WRITE_FACE_ESCAPE
            if seg == _ANY:
                if segments and segments[-1] == _ANY:
                    continue
                segments.append(_ANY)
                continue
            tokens, tok_ok = _tokenize_segment(seg)
            if not tok_ok:
                unsupported = True
                segments.append(CharPattern(()))
                continue
            if len(tokens) > MAX_TOKEN_RUN:
                unsupported = True
            segments.append(CharPattern(tokens))
        if not segments or len(segments) > MAX_GLOB_SEGMENTS:
            if len(segments) > MAX_GLOB_SEGMENTS:
                unsupported = True
            else:
                return None, WRITE_FACE_INVALID_ENTRY
        globs.append(CompiledGlob(tuple(segments), text, unsupported))
    if not globs:
        return None, WRITE_FACE_INVALID_ENTRY
    return globs, None


def _normalize_entry(
    raw: str, *, base: str, case_insensitive: bool
) -> tuple[list[CompiledGlob] | None, str | None, str | None]:
    """Normalize + compile one entry.

    Returns `(globs, normalized_entry, refusal_code)`.  For a conservative
    unsupported construct the entry still parses (globs carry the flag).
    """
    entry = raw.strip()
    if entry == "" or entry == "-":
        return None, None, None  # ignored (section 3.1: empty entries)
    if len(entry) >= 2 and entry[0] == entry[-1] and entry[0] in "\"'":
        entry = entry[1:-1]
    if _has_bare_comma(entry):
        return None, None, WRITE_FACE_INVALID_ENTRY
    if '"' in entry or "'" in entry:
        return None, None, WRITE_FACE_INVALID_ENTRY
    entry = _norm_sep(entry)
    bare, _extglob = _scan_bangs(entry)
    if bare:
        return None, None, WRITE_FACE_INVALID_ENTRY
    if _is_absolute(entry):
        rel = _to_relative(entry, base, case_insensitive)
        if rel is None:
            return None, None, WRITE_FACE_OUTSIDE_BASE
        entry = rel
    segments: list[str] = []
    for seg in entry.split("/"):
        if seg in ("", "."):
            continue
        if seg == "..":
            return None, None, WRITE_FACE_ESCAPE
        segments.append(seg)
    segments = _collapse_double_star(segments)
    if not segments:
        return None, None, WRITE_FACE_INVALID_ENTRY
    norm = "/".join(segments)
    globs, refusal = _compile_normalized(norm)
    if refusal is not None:
        return None, None, refusal
    return globs, norm, None


# ---------------------------------------------------------------------------
# Public parser (section 3.3 three states)
# ---------------------------------------------------------------------------


def parse_write_face(
    text: str, *, base: str, case_insensitive: bool = False
) -> WriteFace | ParseResult:
    """Parse the `write_face:` head of a task.md.

    Three states (section 3.3):

    * no `write_face:` head, or a dash-only value (`write_face: -`) -> `Undeclared`;
    * a present-but-empty head -> `Refused(WRITE_FACE_EMPTY)`;
    * a non-empty head -> `WriteFace` with the normalized, expanded allow set.

    An optional `write_face_deny:` head is parsed for completeness, but the
    overlap operator never uses it (section 3.2).
    """
    allow_head = _find_head(text, "write_face")
    if allow_head is None:
        return Undeclared()
    if allow_head.block is None and allow_head.value.strip() == "-":
        return Undeclared()

    if allow_head.block is not None:
        raw_entries = list(allow_head.block)
    else:
        raw_entries = _split_single_line(allow_head.value)
    if not raw_entries:
        return Refused(WRITE_FACE_EMPTY, detail="present-but-empty write_face head")

    globs: list[CompiledGlob] = []
    norm_entries: list[str] = []
    # D-111 parse-time precedence: walk the fields in order and return the
    # first *hard* rule violation.  An unsupported-syntax entry never produces
    # a refusal (it is recorded as an unknown glob), so it cannot mask a later
    # `write-face-escape` / `write-face-invalid-entry` / `write-face-outside-base`
    # - the verdict is therefore independent of the entry order.
    for raw in raw_entries:
        entry_globs, norm, refusal = _normalize_entry(
            raw, base=base, case_insensitive=case_insensitive
        )
        if refusal is not None:
            return Refused(refusal, detail=f"entry {raw!r}", entry=raw)
        if entry_globs is None:
            continue  # ignored empty entry
        globs.extend(entry_globs)
        norm_entries.append(norm)  # type: ignore[arg-type]
    if not norm_entries:
        return Refused(WRITE_FACE_EMPTY, detail="present-but-empty write_face head")

    deny_entries: list[str] = []
    deny_head = _find_head(text, "write_face_deny")
    if deny_head is not None and not (deny_head.block is None and deny_head.value.strip() == "-"):
        raw_deny = list(deny_head.block) if deny_head.block is not None else _split_single_line(deny_head.value)
        for raw in raw_deny:
            _, norm, refusal = _normalize_entry(
                raw, base=base, case_insensitive=case_insensitive
            )
            if refusal is not None:
                return Refused(refusal, detail=f"deny entry {raw!r}", entry=raw)
            if norm is not None:
                deny_entries.append(norm)

    return WriteFace(
        allow=tuple(globs),
        allow_entries=tuple(norm_entries),
        deny=tuple(deny_entries),
        deny_entries=tuple(deny_entries),
        base=base,
        case_insensitive=case_insensitive,
    )


# ---------------------------------------------------------------------------
# Segment-level character-pattern intersection (section 4.2)
# ---------------------------------------------------------------------------


def _token_allows(tok: Token, ch: str, ci: bool) -> bool:
    if isinstance(tok, Lit):
        return _eq(tok.ch, ch, ci)
    if isinstance(tok, CharClass):
        member = any(_eq(c, ch, ci) for c in tok.chars)
        return (not member) if tok.negated else member
    return True  # Star / QMark


def _common_char(ta: Token, tb: Token, ci: bool) -> str | None:
    if isinstance(ta, Lit):
        return ta.ch if _token_allows(tb, ta.ch, ci) else None
    if isinstance(tb, Lit):
        return tb.ch if _token_allows(ta, tb.ch, ci) else None
    if isinstance(ta, CharClass) and not ta.negated:
        for c in ta.chars:
            if _token_allows(tb, c, ci):
                return c
        return None
    if isinstance(tb, CharClass) and not tb.negated:
        for c in tb.chars:
            if _token_allows(ta, c, ci):
                return c
        return None
    for c in _PROBE:
        if _token_allows(ta, c, ci) and _token_allows(tb, c, ci):
            return c
    raise _ConservativeUnknown(
        "segment-pattern-probe-exhausted", "no common character found in probe pool"
    )


def _seg_overlap(pa: CharPattern, pb: CharPattern, ci: bool) -> str | None:
    """Return a concrete non-empty common string, None, or raise _ConservativeUnknown."""
    a = pa.tokens
    b = pb.tokens
    if len(a) > MAX_TOKEN_RUN or len(b) > MAX_TOKEN_RUN:
        raise _ConservativeUnknown(
            "segment-pattern-length-limit",
            f"|a|={len(a)} |b|={len(b)} > {MAX_TOKEN_RUN}",
        )
    start = (0, 0, False)
    parent: dict[tuple[int, int, bool], tuple[int, int, bool] | None] = {start: None}
    char_in: dict[tuple[int, int, bool], str] = {start: ""}
    queue: deque[tuple[int, int, bool]] = deque([start])
    while queue:
        state = queue.popleft()
        i, j, consumed = state
        if i == len(a) and j == len(b):
            if not consumed:
                continue
            chars: list[str] = []
            cur: tuple[int, int, bool] | None = state
            while cur is not None:
                chars.append(char_in[cur])
                cur = parent[cur]
            chars.reverse()
            return "".join(chars)

        def push(nxt: tuple[int, int, bool], ch: str) -> None:
            if nxt not in parent:
                parent[nxt] = state
                char_in[nxt] = ch
                queue.append(nxt)

        if i < len(a) and isinstance(a[i], Star):
            push((i + 1, j, consumed), "")
        if j < len(b) and isinstance(b[j], Star):
            push((i, j + 1, consumed), "")
        if i < len(a) and j < len(b):
            ta, tb = a[i], b[j]
            if isinstance(ta, Star) and isinstance(tb, Star):
                push((i, j, True), "x")
            else:
                ch = _common_char(ta, tb, ci)
                if ch is not None:
                    ni = i if isinstance(ta, Star) else i + 1
                    nj = j if isinstance(tb, Star) else j + 1
                    push((ni, nj, True), ch)
        if len(parent) > MAX_SEG_BFS_STATES:
            raise _ConservativeUnknown(
                "segment-pattern-state-limit", f"states > {MAX_SEG_BFS_STATES}"
            )
    return None


def _seg_example(pattern: CharPattern, ci: bool) -> str:
    witness = _seg_overlap(pattern, pattern, ci)
    # A token pattern always generates itself, so a non-empty witness exists
    # unless the pattern only matches the empty string (which is never emitted
    # because empty segments are normalized away at parse time).
    if witness is None:
        raise _ConservativeUnknown(
            "segment-pattern-empty", "pattern has no non-empty example"
        )
    return witness


# ---------------------------------------------------------------------------
# Glob (segment sequence) product (section 4.3)
# ---------------------------------------------------------------------------


def _globs_overlap(
    ga: tuple[Segment, ...], gb: tuple[Segment, ...], ci: bool
) -> tuple[str, ...] | None:
    la, lb = len(ga), len(gb)
    if (la + 1) * (lb + 1) > MAX_PRODUCT_STATES:
        raise _ConservativeUnknown(
            "glob-product-state-limit", f"({la}+1)*({lb}+1) > {MAX_PRODUCT_STATES}"
        )
    start = (0, 0, False)
    parent: dict[tuple[int, int, bool], tuple[int, int, bool] | None] = {start: None}
    seg_in: dict[tuple[int, int, bool], str | None] = {start: None}
    queue: deque[tuple[int, int, bool]] = deque([start])
    while queue:
        state = queue.popleft()
        i, j, consumed = state
        if i == la and j == lb and consumed:
            segs: list[str] = []
            cur: tuple[int, int, bool] | None = state
            while cur is not None:
                witness = seg_in[cur]
                if witness is not None:
                    segs.append(witness)
                cur = parent[cur]
            segs.reverse()
            return tuple(segs)

        def push(nxt: tuple[int, int, bool], witness: str | None) -> None:
            if nxt not in parent:
                parent[nxt] = state
                seg_in[nxt] = witness
                queue.append(nxt)

        if i < la and ga[i] == _ANY:
            push((i + 1, j, consumed), None)
        if j < lb and gb[j] == _ANY:
            push((i, j + 1, consumed), None)
        if i < la and j < lb:
            sa, sb = ga[i], gb[j]
            if sa == _ANY and sb == _ANY:
                push((i, j, True), "x")
            elif sa == _ANY:
                push((i, j + 1, True), _seg_example(sb, ci))  # type: ignore[arg-type]
            elif sb is _ANY:
                push((i + 1, j, True), _seg_example(sa, ci))  # type: ignore[arg-type]
            else:
                witness = _seg_overlap(sa, sb, ci)  # type: ignore[arg-type]
                if witness is not None:
                    push((i + 1, j + 1, True), witness)
    return None


def globs_overlap(
    a: Sequence[str], b: Sequence[str], *, case_insensitive: bool = False
) -> tuple[str, ...] | None | Unsupported:
    """Segment-sequence variant of section 4.3, for direct boundary testing.

    Each element is a single normalized glob string (e.g. `"a/**/b"`).
    Returns the witness segment sequence, `None`, or `Unsupported`.
    """
    try:
        compiled_a = [(_compile_normalized(_norm_sep(item))[0] or []) for item in a]
        compiled_b = [(_compile_normalized(_norm_sep(item))[0] or []) for item in b]
    except _ConservativeUnknown as exc:
        return Unsupported(reason=exc.reason, detail=exc.detail)
    unsupported_rule: str | None = None
    for group in (compiled_a, compiled_b):
        for globs in group:
            for glob in globs:
                if glob.unsupported and unsupported_rule is None:
                    unsupported_rule = glob.entry
    try:
        # D-111: a provable witness wins over an undecidable entry.
        for ga_globs in compiled_a:
            for gb_globs in compiled_b:
                for ga in ga_globs:
                    if ga.unsupported:
                        continue
                    for gb in gb_globs:
                        if gb.unsupported:
                            continue
                        witness = _globs_overlap(ga.segments, gb.segments, case_insensitive)
                        if witness is not None:
                            return witness
    except _ConservativeUnknown as exc:
        return Unsupported(reason=exc.reason, detail=exc.detail)
    if unsupported_rule is not None:
        return Unsupported(
            reason="unsupported-syntax", detail=unsupported_rule, rule=unsupported_rule
        )
    return None


# ---------------------------------------------------------------------------
# Face-level operator (section 4.4)
# ---------------------------------------------------------------------------


def overlap(a: WriteFace, b: WriteFace) -> Conflict | None | Unsupported:
    """Decide whether two parsed write faces share a lexically-provable path.

    `a` and `b` must both be `WriteFace` (an undeclared side is handled by the
    caller as serial-only, design D-003).  `deny` never participates.

    Returns a `Conflict` with a concrete glob-free witness, `None` for a
    lexically-provable empty intersection, or `Unsupported` for any
    conservative fallback (section 3.2) - callers MUST treat `Unsupported` as
    overlap.
    """
    base_a = _norm_sep(a.base).rstrip("/")
    base_b = _norm_sep(b.base).rstrip("/")
    if base_a != base_b:
        same_folded = (
            a.case_insensitive
            and b.case_insensitive
            and base_a.lower() == base_b.lower()
        )
        if not same_folded:
            return Unsupported(
                reason="incomparable-base",
                detail=f"base mismatch: {a.base!r} vs {b.base!r}",
            )
    if a.case_insensitive != b.case_insensitive:
        return Unsupported(
            reason="incomparable-case-mode",
            detail=f"case mode mismatch: {a.case_insensitive} vs {b.case_insensitive}",
        )
    ci = a.case_insensitive
    # D-111 intersection-time precedence, in the exact shape of the TS
    # `writeFacesOverlap` (shared/write-face.ts): prove a conflict first.  A
    # pair that cannot be decided - unsupported syntax on either side, or a
    # state-machine fallback (`_ConservativeUnknown`) - is *deferred* into this
    # single slot (first encountered wins) and never short-circuits the search,
    # so a provable conflict always wins over an earlier undecidable pair
    # regardless of allow-entry order.  `Unsupported` means "cannot decide",
    # not "decided overlap without a witness".
    deferred: Unsupported | None = None
    for ga in a.allow:
        for gb in b.allow:
            if ga.unsupported or gb.unsupported:
                # TS: `deferred = deferred ?? "unsupported-syntax"`.  The
                # unsupported-syntax entries and the state-machine fallbacks
                # below share this one deferred slot; first encountered wins.
                if deferred is None:
                    deferred = Unsupported(
                        reason="unsupported-syntax",
                        detail="unsupported glob syntax in allow entry",
                        rule=ga.entry,
                        other=gb.entry,
                    )
                continue
            try:
                # Deferral is per pair: the fallback is scoped to this pair
                # only, and the next pair is still examined for a witness.
                witness = _globs_overlap(ga.segments, gb.segments, ci)
            except _ConservativeUnknown as exc:
                if deferred is None:
                    deferred = Unsupported(
                        reason=exc.reason,
                        detail=exc.detail,
                        rule=ga.entry,
                        other=gb.entry,
                    )
                continue
            if witness is None:
                continue
            return Conflict(sample="/".join(witness), rule=ga.entry, other=gb.entry)
    # TS: the deferred fallback is reported only after the whole pair product
    # is exhausted (a conflict may still have been provable later).
    if deferred is not None:
        return deferred
    return None


# ---------------------------------------------------------------------------
# Convenience
# ---------------------------------------------------------------------------


def is_overlap(result: Conflict | None | Unsupported) -> bool:
    """Single predicate for the conservative direction: anything not None collides."""
    return result is not None
