r"""autopilot/task_graph.py — pure task-level dependency graph for one key.

Task-level dependency carrier + validation + frontier.  Pure functions: stdlib
only, no file I/O, no module-level mutable state, no import of ``conductor``
(the tick engine) and no reuse of ``card_audit._header_value`` (measured: it
returns ``""`` for 5/5 real cards because a card starts with an H1, which the
dispatch-header parser rejects at ``card_audit.py:160-162``).

Why
---
Today a task card has no machine-readable prerequisite carrier: the conductor
orders cards by plan appearance (``conductor.py:1717 _plan_task_order``) and
always runs one task per key.  This module supplies the missing primitive —
read ``deps:``/``依赖:`` from a card header, validate the resulting graph, and
compute the dependency frontier — so ``M-02`` can later consume it.  This
module itself changes no dispatch behaviour and opens no concurrency.

Card header region rule
-----------------------
The declaration is only honoured inside the card *header*: after the first H1
(or inside YAML frontmatter, or from line 1 when there is no H1), through blank
lines, ``## 元信息``-style headings, and ``key: value`` / ``- key: value``
lines, stopping at the first body heading (``##`` other than a metadata
heading) or the first non ``key: value`` line.  This is what keeps a body
sentence such as ``## 输入`` → ``- 依赖: Stage 1 全部完成`` from being read as a
declaration (real card: ``timi-gpt-pi-routing/tasks/007-build-verify.md``).

Accepted forms (all four real ones, plus the embedded ``· 依赖:`` shape that
47/434 cards use):

* ``- deps: T-01, T-02``   (bullet)
* ``- 依赖: T-01, T-02``   (bullet, Chinese key)
* ``deps: T-01``           (bare)
* ``- 依赖：T-01``         (full-width colon)
* ``- 波次: **1** · 依赖: T-01, T-03`` (embedded)

``-`` / ``—`` / ``无`` / ``none`` / empty = no dependencies (AC-008).  An item
may carry trailing prose (``T-02 · 预估: 60-90min``); only its leading id token
is used and the prose is dropped.  YAML flow lists (``[001, 002]``) and item
bold (``**T-15``) are tolerated.

Resolution
----------
Dep tokens are joined to card ids by **numeric core** (``T-01-file-lock`` and
``T-1`` and ``T-001`` all have core ``1``), because exact-stem resolution was
measured at 0/146 real tokens.  A core that matches exactly one card binds; a
core that matches two or more cards (``agent-team-loop`` has both
``T-01-file-lock`` and ``T-01-task-protocol``) is *ambiguous* and is never
silently resolved to one of them.  ``numeric_core`` keeps the digits as written
(``T-01-x`` → ``"01"``, ``T-1`` → ``"1"``); joins compare them numerically so
``1 == 01``.

Validation V1–V7
----------------
Every problem is a structured :class:`DepProblem` carrying ``kind``, the
``card_id``, the 1-based original ``line`` and the original ``snippet``:

* V1 ``deps-unknown-id``  — dep item is not a task id at all (prose), or a graph
  node whose id is not in the key's card set.
* V2 ``deps-dangling``    — well-formed id whose core matches no card.
* V3 ``deps-cycle``       — dependency cycle of length ≥ 2.
* V4 ``deps-cross-key``   — cross-key reference (``../``, ``\``, ``/tasks/``,
  ``<key>:<id>``).
* V5 ``deps-duplicate``   — the same dependency declared twice, or a second
  declaration line.
* V6 ``deps-self``        — a card depends on itself (``find_cycle`` reports a
  self-loop as the length-1 cycle; ``validate_task_graph`` attributes it to V6
  so it is not double-reported as V3).
* V7 ``deps-unsupported`` — shorthand the design refuses to expand (D-110):
  ranges ``T-01…T-13``, ``...``, ``~``, ``*`` wildcard.  The whole language of
  this branch lives in :data:`_RANGE_RE` — the single reversible point.

Fail-closed: any problem makes :attr:`TaskGraph.plan_is_serializable` ``False``,
which is the "fall back to serial for the whole key" signal.  Partial
activation and default amplification are both excluded.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = [
    "HEADER_SCAN_LINES",
    "META_HEADINGS",
    "DepProblem",
    "TaskGraph",
    "deps_declaration_lines",
    "find_cycle",
    "frontier",
    "join_deps",
    "numeric_core",
    "parse_card_deps",
    "validate_task_graph",
]

# Header region is bounded (a card's metadata never runs to the body).  Measured
# max deps line on the real corpus: 19, well inside this window.
HEADER_SCAN_LINES = 40

# ``## 元信息``-style headings that open a metadata section inside the header.
META_HEADINGS = frozenset({"元信息", "基本信息", "任务信息", "元数据"})

# A declared value that means "no dependencies" (AC-008: missing line and a
# dash/empty value are the same thing).
_NO_DEP_MARKERS = frozenset({"-", "—", "–", "无", "none", "nil", "null", "n/a", "na"})

# Reversible point (D-110): every "shorthand we refuse to expand" glyph is here.
# To add range expansion later, change this regex + the frozen corpus only.
_RANGE_RE = re.compile(r"…|\.\.\.|~|～|\*")

# ``- deps: X`` / ``- 依赖: X`` / ``deps: X`` / ``- 依赖：X``.
_DEPS_LINE_RE = re.compile(
    r"^\s*(?:-\s*)?(?P<key>deps|依赖)\s*[:：]\s*(?P<value>.*)$", re.IGNORECASE
)
# Embedded ``- 波次: **1** · 依赖: X`` shape (47/434 real cards).
_DEPS_EMBED_RE = re.compile(r"[·・]\s*(?P<key>deps|依赖)\s*[:：]\s*(?P<value>.*)$", re.IGNORECASE)
# Any ``key: value`` header line (bullet or bare); used only to keep scanning
# the header region, never to read a value.  Keys are label-like: real ones are
# ``type``/``ac_refs``/``预估``/``负责 Agent``/``只读参考（不得改）``, so the
# length cap stops a prose sentence that merely ends in ``：`` from extending the
# header region into the body.
_ANY_META_RE = re.compile(r"^\s*(?:-\s*)?[^\s:：][^:：]{0,29}\s*[:：]")
_H1_RE = re.compile(r"^#\s+\S")
_H2_RE = re.compile(r"^##\s*(?P<name>.*?)\s*$")
_FENCE_RE = re.compile(r"^---\s*$")

# Leading task id of an item: ``T-01``, ``T-1-slug``, ``001-slug``, ``T1-x``.
_ID_RE = re.compile(r"^(?P<id>[Tt]?-?\d{1,3}(?:-[A-Za-z0-9_.]+)*)")
# Numeric core at the very start of a card id / stem.
_CORE_RE = re.compile(r"^\s*[Tt]?-?(\d{1,3})")
# Cross-key reference: path escape / path segment / ``<key>:<id>`` prefix.
_CROSS_KEY_RE = re.compile(r"(?:^|[\\/])\.\.|\\|/tasks/|^\s*[A-Za-z][A-Za-z0-9_-]*\s*:\s*[Tt]?-?\d")
# Explanatory parenthetical after an item (``T-02（adapter）``): content, not a dep.
_ANNOTATION_RE = re.compile(r"[（(][^（）()]*[)）]")
# ``·`` / ``・`` separates an annotation section (``· 预估:``, ``· 覆盖:``).
_ANNOTATION_SEP_RE = re.compile(r"[·・]")


@dataclass(frozen=True)
class DepProblem:
    """One structured validation problem (kind + origin line + original text)."""

    kind: str
    card_id: str
    line: int
    snippet: str
    token: str = ""
    detail: str = ""

    def as_dict(self) -> dict[str, object]:
        """Plain-dict view (for logs / timeline payloads built by the caller)."""
        return {
            "kind": self.kind,
            "card_id": self.card_id,
            "line": self.line,
            "snippet": self.snippet,
            "token": self.token,
            "detail": self.detail,
        }


@dataclass(frozen=True)
class TaskGraph:
    """Validated task graph for one key.

    ``deps_by_id`` maps each card id to its resolved prerequisite card ids (only
    unambiguous bindings; empty when undeclared).  ``problems`` is the V1-V7
    list.  ``plan_is_serializable`` is the fail-closed signal: ``False`` means
    the whole key must fall back to serial execution.
    """

    deps_by_id: dict[str, tuple[str, ...]]
    problems: tuple[DepProblem, ...]

    @property
    def plan_is_serializable(self) -> bool:
        """``False`` ⇒ the caller must run the whole key serially (fail-closed)."""
        return not self.problems


@dataclass(frozen=True)
class _Token:
    """One declared dependency item with its origin."""

    raw: str
    id: str
    line: int
    snippet: str
    unsupported: bool = False
    cross_key: bool = False


def _strip_bold(value: str) -> str:
    """Drop markdown bold markers so ``**T-15`` parses as ``T-15``."""
    return value.replace("**", "").strip()


def _is_no_dep(value: str) -> bool:
    """True when a declared item means "no dependency" (``-``/``无``/...)."""
    text = _strip_bold(value).strip().lower()
    if text in _NO_DEP_MARKERS:
        return True
    # ``无（本卡是 G5/G6 的起点）`` — marker followed by an explanation.
    return bool(re.match(r"^(?:无|none|—|–|-|n/?a|nil|null)\s*[（(]", text))


def _iter_header_lines(card_text: str) -> list[tuple[int, str]]:
    """Header-region lines as ``(1-based line number, raw line)``.

    Frontmatter (a leading ``---`` fence) is scanned to its closing fence.  A
    card without H1 (e.g. a dispatch ``task.md``) is scanned from line 1.
    """
    lines = card_text.splitlines()
    if not lines:
        return []
    window = lines[:HEADER_SCAN_LINES]

    if window[0].strip() == "---":
        out: list[tuple[int, str]] = []
        for index, raw in enumerate(window[1:], start=1):
            if _FENCE_RE.match(raw.strip()):
                break
            out.append((index + 1, raw))
        return out

    start = 0
    for index, raw in enumerate(window):
        if _H1_RE.match(raw.strip()):
            start = index + 1
            break

    out = []
    for index in range(start, len(window)):
        raw = window[index]
        line = raw.strip()
        if not line or _FENCE_RE.match(line):
            continue
        heading = _H2_RE.match(line)
        if heading:
            if heading.group("name").strip().strip("#").strip() in META_HEADINGS:
                continue
            break
        if not _ANY_META_RE.match(line):
            break
        out.append((index + 1, raw))
        continue
    return out


def _deps_value(line: str) -> str | None:
    """The declared dependency value on ``line``, or ``None`` when not a deps line.

    An embedded declaration is cut at the next ``·`` section marker, so the
    ``· 覆盖: VC-001,002`` tail of ``key: ... · 依赖: 无（…） · 覆盖: ...`` is not
    read as further dependency items.
    """
    match = _DEPS_LINE_RE.match(line)
    value = match.group("value") if match else None
    if value is None:
        embed = _DEPS_EMBED_RE.search(line)
        if embed is None:
            return None
        value = embed.group("value")
    return _ANNOTATION_SEP_RE.split(value, maxsplit=1)[0]


def _split_items(value: str) -> list[str]:
    """Split a deps value into items (flow list, ``,``, ``、``).

    Item annotations are removed first: parenthesized text (``T-02（adapter）``)
    is an explanation, and ``·`` tails were already cut by :func:`_deps_value`.
    """
    text = _ANNOTATION_RE.sub("", value).strip()
    if not text:
        return []
    if len(text) >= 2 and text[0] == "[" and text[-1] == "]":
        text = text[1:-1]
    return [part.strip() for part in re.split(r"[,、]", text) if part.strip()]


def _classify_tokens(value: str, line: int, snippet: str) -> list[_Token]:
    """Turn one declared deps value into ordered tokens with syntax flags."""
    tokens: list[_Token] = []
    for item in _split_items(value):
        if _is_no_dep(item):
            continue
        text = _strip_bold(item)
        if not text:
            continue
        if _RANGE_RE.search(text):
            tokens.append(_Token(item, text, line, snippet, unsupported=True))
            continue
        if _CROSS_KEY_RE.search(text):
            tokens.append(_Token(item, text, line, snippet, cross_key=True))
            continue
        for part in re.split(r"[/+]", text):
            part = part.strip()
            if not part:
                continue
            match = _ID_RE.match(part)
            tokens.append(_Token(item, match.group("id") if match else part, line, snippet))
    return tokens


def _parse_tokens(card_text: str) -> list[_Token]:
    """All declared dependency tokens in a card, in declaration order."""
    tokens: list[_Token] = []
    for line, raw in _iter_header_lines(card_text):
        value = _deps_value(raw)
        if value is None:
            continue
        tokens.extend(_classify_tokens(value, line, raw.rstrip()))
    return tokens


def parse_card_deps(card_text: str) -> list[str]:
    """Declared dependency items of a card header, in order.

    Returns the id token of each item (``T-01``, ``001-slug``, ...) and the raw
    text of items that are not id-shaped (prose / range / cross-key) — a
    declaration is never silently dropped.  ``-``/empty/``无``/``none`` and a
    missing line both yield ``[]`` (AC-008).
    """
    return [token.id for token in _parse_tokens(card_text)]


def deps_declaration_lines(card_text: str) -> tuple[int, ...]:
    """1-based line numbers of every ``deps:``/``依赖:`` declaration in the header.

    Distinct from :func:`parse_card_deps`: a declaration with value ``无`` still
    counts here, which is what the corpus distribution (cards *with* a line)
    measures.
    """
    return tuple(
        line for line, raw in _iter_header_lines(card_text) if _deps_value(raw) is not None
    )


def numeric_core(card_id_or_stem: str) -> str:
    """Leading numeric core of a card id / stem, digits as written, or ``""``.

    ``T-01-x`` → ``"01"``; ``T-1`` → ``"1"``; ``002-py-target-config-parity`` →
    ``"002"``.  Joins normalize the core numerically, so ``1 == 01``.
    """
    text = str(card_id_or_stem or "").strip().replace("\\", "/").rsplit("/", 1)[-1]
    if text.lower().endswith(".md"):
        text = text[:-3]
    match = _CORE_RE.match(text)
    return match.group(1) if match else ""


def _core_key(core: str) -> str:
    """Canonical comparison key of a numeric core (``"01"`` → ``"1"``)."""
    try:
        return str(int(core))
    except ValueError:  # pragma: no cover - _CORE_RE guarantees digits
        return core


def join_deps(deps, card_ids) -> dict:
    """Resolve dep tokens against the key's card ids (numeric-core join).

    Returns a dict:

    * ``bindings``   — ``{token: card_id}`` for an exact-stem hit or a unique
      numeric-core hit;
    * ``ambiguous``  — ``{token: (card_id, ...)}`` when a core has ≥2 candidates
      (never resolved to one of them);
    * ``unknown``    — tuple of items with no task-id shape (V1);
    * ``dangling``   — tuple of well-formed ids with no matching card (V2);
    * ``cross_key``  — tuple of cross-key references (V4);
    * ``unsupported``— tuple of refused shorthand forms (V7);
    * ``problems``   — the same findings as structured dicts (no line info).
    """
    ids = [str(card_id) for card_id in card_ids]
    by_core: dict[str, list[str]] = {}
    for card_id in ids:
        core = numeric_core(card_id)
        if core:
            by_core.setdefault(_core_key(core), []).append(card_id)

    bindings: dict[str, str] = {}
    ambiguous: dict[str, tuple[str, ...]] = {}
    unknown: list[str] = []
    dangling: list[str] = []
    cross_key: list[str] = []
    unsupported: list[str] = []
    problems: list[dict[str, object]] = []

    for raw in deps:
        token = str(raw).strip()
        if not token:
            continue
        text = _strip_bold(token)
        if _is_no_dep(text):
            continue
        if _RANGE_RE.search(text):
            unsupported.append(token)
            problems.append({"kind": "deps-unsupported", "token": token, "detail": "shorthand"})
            continue
        if _CROSS_KEY_RE.search(text):
            cross_key.append(token)
            problems.append({"kind": "deps-cross-key", "token": token, "detail": "cross-key"})
            continue
        match = _ID_RE.match(text)
        if not match:
            unknown.append(token)
            problems.append({"kind": "deps-unknown-id", "token": token, "detail": "not an id"})
            continue
        dep_id = match.group("id")
        if dep_id in ids:
            bindings[token] = dep_id
            continue
        core = numeric_core(dep_id)
        candidates = by_core.get(_core_key(core), []) if core else []
        if len(candidates) == 1:
            bindings[token] = candidates[0]
        elif len(candidates) > 1:
            ambiguous[token] = tuple(candidates)
            problems.append(
                {
                    "kind": "deps-ambiguous",
                    "token": token,
                    "detail": "core %s matches %d cards" % (core, len(candidates)),
                }
            )
        else:
            dangling.append(token)
            problems.append({"kind": "deps-dangling", "token": token, "detail": "no card"})

    return {
        "bindings": bindings,
        "ambiguous": ambiguous,
        "unknown": tuple(dict.fromkeys(unknown)),
        "dangling": tuple(dict.fromkeys(dangling)),
        "cross_key": tuple(dict.fromkeys(cross_key)),
        "unsupported": tuple(dict.fromkeys(unsupported)),
        "problems": tuple(problems),
    }


def find_cycle(deps_by_id) -> list[str] | None:
    """Return one dependency cycle as ``[n0, n1, ..., n0]``, or ``None``.

    Generic over the graph kind (a directed graph as ``{node: iterable(node)}``),
    so it also serves roadmap validation.  A self-loop is returned as
    ``[n, n]``; :func:`validate_task_graph` reports that case as V6 instead.
    """
    graph = {str(node): [str(dep) for dep in deps] for node, deps in deps_by_id.items()}
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for dep in graph.get(node, ()):
            if dep not in graph:
                continue
            if state.get(dep, 0) == 0:
                found = visit(dep)
                if found is not None:
                    return found
            elif state.get(dep) == 1:
                return stack[stack.index(dep) :] + [dep]
        stack.pop()
        state[node] = 2
        return None

    for node in graph:
        if state.get(node, 0) == 0:
            found = visit(node)
            if found is not None:
                return found
    return None


def _problem(kind: str, card_id: str, token: _Token, detail: str = "") -> DepProblem:
    return DepProblem(
        kind=kind,
        card_id=card_id,
        line=token.line,
        snippet=token.snippet,
        token=token.id,
        detail=detail,
    )


def validate_task_graph(cards, card_ids=None) -> TaskGraph:
    """Validate the task graph of one key.

    ``cards`` maps ``card_id -> card text``; ``card_ids`` is the key's declared
    card set (defaults to the keys of ``cards``).  Returns a :class:`TaskGraph`
    whose ``plan_is_serializable`` is ``False`` as soon as any V1-V7 problem or
    ambiguity exists — the whole-key serial-fallback signal.
    """
    ids = [str(card_id) for card_id in (cards if card_ids is None else card_ids)]
    id_set = set(ids)
    problems: list[DepProblem] = []
    deps_by_id: dict[str, list[str]] = {card_id: [] for card_id in ids}
    edge_origin: dict[tuple[str, str], _Token] = {}

    for card_id, text in cards.items():
        card_id = str(card_id)
        if card_id not in id_set:
            problems.append(
                DepProblem(
                    kind="deps-unknown-id",
                    card_id=card_id,
                    line=0,
                    snippet=card_id,
                    detail="node not in the key card set",
                )
            )
        if card_id not in deps_by_id:
            deps_by_id[card_id] = []

        tokens = _parse_tokens(text)
        declaration_lines = deps_declaration_lines(text)
        for extra_line in declaration_lines[1:]:
            problems.append(
                DepProblem(
                    kind="deps-duplicate",
                    card_id=card_id,
                    line=extra_line,
                    snippet=_line_text(text, extra_line),
                    detail="second deps declaration line",
                )
            )

        seen: set[str] = set()
        for token in tokens:
            joined = join_deps([token.id], ids)
            if token.unsupported:
                problems.append(_problem("deps-unsupported", card_id, token, "refused shorthand"))
                identity = "raw:" + token.id
            elif token.cross_key:
                problems.append(_problem("deps-cross-key", card_id, token, "cross-key"))
                identity = "raw:" + token.id
            elif joined["bindings"]:
                bound = joined["bindings"][token.id]
                identity = "id:" + bound
                if bound == card_id:
                    problems.append(_problem("deps-self", card_id, token, "self reference"))
                deps_by_id[card_id].append(bound)
                edge_origin[(card_id, bound)] = token
            elif joined["ambiguous"]:
                candidates = joined["ambiguous"][token.id]
                problems.append(
                    _problem(
                        "deps-ambiguous",
                        card_id,
                        token,
                        "%d cards share core %s" % (len(candidates), numeric_core(token.id)),
                    )
                )
                identity = "core:" + _core_key(numeric_core(token.id))
            elif joined["unknown"]:
                problems.append(_problem("deps-unknown-id", card_id, token, "not an id"))
                identity = "raw:" + token.id
            else:
                problems.append(_problem("deps-dangling", card_id, token, "no card"))
                identity = "id:" + token.id
            if identity in seen:
                problems.append(_problem("deps-duplicate", card_id, token, "repeated"))
            seen.add(identity)

    graph = {card_id: tuple(dict.fromkeys(deps)) for card_id, deps in deps_by_id.items()}
    multi = {card_id: tuple(dep for dep in deps if dep != card_id) for card_id, deps in graph.items()}
    cycle = find_cycle(multi)
    if cycle is not None:
        origin = edge_origin.get((cycle[0], cycle[1]))
        problems.append(
            DepProblem(
                kind="deps-cycle",
                card_id=cycle[0],
                line=origin.line if origin is not None else 0,
                snippet=origin.snippet if origin is not None else " -> ".join(cycle),
                token=cycle[1],
                detail="dependency cycle: %s" % " -> ".join(cycle),
            )
        )

    return TaskGraph(deps_by_id=graph, problems=tuple(problems))


def _line_text(card_text: str, line: int) -> str:
    """Original text of a 1-based line, or ``""`` when out of range."""
    lines = card_text.splitlines()
    if 1 <= line <= len(lines):
        return lines[line - 1].rstrip()
    return ""


def frontier(deps_by_id, terminal_ids) -> list[str]:
    """Cards that are ready to start, in the input card order.

    A card is on the frontier when it is not itself terminal and every
    prerequisite is satisfied — terminal, or absent from ``deps_by_id`` (an
    unknown node cannot block).  Order is the caller's card order, so a
    ``_plan_task_order`` sequence stays stable (chain → width 1, fan-out →
    parallel width).
    """
    terminal = {str(card_id) for card_id in terminal_ids}
    ready: list[str] = []
    for card_id, deps in deps_by_id.items():
        card_id = str(card_id)
        if card_id in terminal:
            continue
        if all(str(dep) in terminal or str(dep) not in deps_by_id for dep in deps):
            ready.append(card_id)
    return ready
