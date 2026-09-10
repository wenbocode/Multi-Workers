"""
roadmap.py — parse/validate/update helpers for .agenticdoc/_autopilot/_roadmap.md
(goal-autopilot T-03, design D-105).

Schema (D-105):

    # Roadmap
    > generated_at: <iso>
    > goal_mtime: <ms>
    ## Stage 1: <title>
    > goal: <stage goal, required non-empty>
    > status: pending | approved | running | closed | closed-human | halted
    > key-status: <key>=<running|done|stalled|closed-legacy>, ...
    ### Keys
    | key | role | depends_on |
    |-----|------|-----------|
    | k1 | <role> | - |

Semantics locked here:

- Parse failures raise RoadmapError explicitly (never silently swallowed):
  the conductor catches it, skips its tick, and records a config event
  (D-105). RoadmapError covers: missing/unreadable file, no stage sections,
  malformed stage headers, missing required '> goal:'/'> status:' lines,
  status/key-status values outside their enums, malformed key-status
  entries, malformed Keys-table rows, duplicate stage numbers / key rows.
- Stage order = order of appearance in the file. Dependency legality
  (validate_roadmap) is defined against that order: a dependency must point
  to a key in the same stage or an earlier stage.
- key-status line is optional (a fresh roadmap proposal has no runtime
  state yet). Once present, validate_roadmap requires its key set to equal
  the stage's Keys-table key set (both directions), so callers should
  initialize an entry for every stage key when the stage starts running.
- Pipe-separated parsing tolerates trailing spaces and empty segments
  (spec §5 pitfall, VC-041): blank lines are skipped, table cells are
  stripped, bounding empty cells dropped, empty comma-separated entries
  filtered out.
- Update helpers (update_stage_status / update_key_status) are pure
  text -> text transforms that rewrite ONLY the '> status:' / '> key-status:'
  line of one stage; every other line is preserved byte-for-byte (including
  a trailing CR when the source line had one). The caller composes locking
  (.mw/roadmap.lock) and the atomic replace — this module never writes
  files and never holds locks.
"""

from __future__ import annotations

import pathlib
import re
from dataclasses import dataclass, field

# Stage lifecycle statuses (D-105).
STAGE_STATUSES: tuple[str, ...] = (
    "pending",
    "approved",
    "running",
    "closed",
    "closed-human",
    "halted",
)

# Per-key runtime statuses persisted on the key-status line (D-105).
KEY_STATUSES: tuple[str, ...] = (
    "running",
    "done",
    "stalled",
    "closed-legacy",
)

# Field names recognized inside a stage section.
_STAGE_FIELDS = ("goal", "status", "key-status")
# Field names recognized in the document header (before the first stage).
_DOC_FIELDS = ("generated_at", "goal_mtime")

_STAGE_PREFIX_RE = re.compile(r"^##\s*Stage\b")
_STAGE_HEADER_RE = re.compile(r"^##\s*Stage\s+(\d+)\s*:\s*(.+)$")
_FIELD_LINE_RE = re.compile(r"^>\s*([A-Za-z][A-Za-z0-9_-]*)\s*:\s*(.*)$")
_SEPARATOR_CELL_RE = re.compile(r"^:?-+:?$")


class RoadmapError(Exception):
    """Explicit roadmap parse/structure failure (caller skips tick + logs)."""


@dataclass
class RoadmapKey:
    """One row of a stage's Keys table."""

    key: str
    role: str
    depends_on: tuple[str, ...]


@dataclass
class RoadmapStage:
    """One '## Stage N: <title>' section."""

    number: int
    title: str
    goal: str
    status: str
    key_status: dict[str, str] = field(default_factory=dict)
    key_status_present: bool = False
    keys: tuple[RoadmapKey, ...] = ()

    @property
    def key_names(self) -> tuple[str, ...]:
        return tuple(k.key for k in self.keys)


@dataclass
class Roadmap:
    """A parsed _roadmap.md."""

    generated_at: str | None = None
    goal_mtime: str | None = None
    stages: tuple[RoadmapStage, ...] = ()


# ── Paths ─────────────────────────────────────────────────────────────────────

def roadmap_path(project_dir: pathlib.Path | str) -> pathlib.Path:
    """Location of the roadmap file under a project root."""
    return pathlib.Path(project_dir) / ".agenticdoc" / "_autopilot" / "_roadmap.md"


# ── Parsing ───────────────────────────────────────────────────────────────────

def parse_roadmap(text: str) -> Roadmap:
    """Parse roadmap markdown into a Roadmap. Raises RoadmapError on any
    structural failure (explicit, never silent)."""
    stages: list[RoadmapStage] = []
    seen_stage_numbers: set[int] = set()
    doc_fields: dict[str, str] = {}

    cur: _StageBuilder | None = None
    in_keys_table = False
    table_header_seen = False

    def finish_stage(builder: _StageBuilder) -> None:
        stages.append(builder.build())

    for lineno, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            if line.startswith("###"):
                heading = line.lstrip("#").strip()
                if cur is not None and heading.lower() == "keys":
                    if cur.keys_table_seen:
                        raise RoadmapError(
                            f"line {lineno} (stage {cur.number}): duplicate '### Keys' section"
                        )
                    cur.keys_table_seen = True
                    in_keys_table = True
                    table_header_seen = False
                else:
                    # Any other subsection ends the keys table.
                    in_keys_table = False
                continue
            if line.startswith("##"):
                if _STAGE_PREFIX_RE.match(line):
                    m = _STAGE_HEADER_RE.match(line)
                    if not m:
                        raise RoadmapError(
                            f"line {lineno}: malformed stage header {line!r} "
                            "(expected '## Stage <number>: <title>')"
                        )
                    if cur is not None:
                        finish_stage(cur)
                    number = int(m.group(1))
                    if number in seen_stage_numbers:
                        raise RoadmapError(f"line {lineno}: duplicate stage number {number}")
                    seen_stage_numbers.add(number)
                    cur = _StageBuilder(number=number, title=m.group(2).strip())
                else:
                    # An unrelated H2 section: ends the current stage.
                    if cur is not None:
                        finish_stage(cur)
                        cur = None
                in_keys_table = False
                continue
            # Document title (H1) or deeper heading: ignored.
            in_keys_table = False
            continue
        if line.startswith("|"):
            if cur is not None and in_keys_table:
                cells = _split_table_row(line)
                if cells and all(_SEPARATOR_CELL_RE.match(c) for c in cells):
                    continue  # |----|----| separator row
                if not table_header_seen and _is_header_row(cells):
                    table_header_seen = True
                    continue
                assert cur is not None
                cur.add_key_row(cells, lineno)
            # Pipe rows outside a keys table (prose tables) are ignored.
            continue
        if line.startswith(">"):
            m = _FIELD_LINE_RE.match(line)
            name = m.group(1) if m else ""
            if cur is None:
                if name in _DOC_FIELDS:
                    if name in doc_fields:
                        raise RoadmapError(f"line {lineno}: duplicate header field {name!r}")
                    doc_fields[name] = m.group(2).strip()
                # Other blockquote lines (prose) are ignored.
            else:
                if name in _STAGE_FIELDS:
                    cur.set_field(name, m.group(2).strip(), lineno)
                # Other blockquote lines (prose) are ignored.
                in_keys_table = False
            continue
        # Any other line (prose) is ignored but ends the keys table.
        in_keys_table = False

    if cur is not None:
        finish_stage(cur)
    if not stages:
        raise RoadmapError("no '## Stage <number>: <title>' sections found")

    return Roadmap(
        generated_at=doc_fields.get("generated_at"),
        goal_mtime=doc_fields.get("goal_mtime"),
        stages=tuple(stages),
    )


def load_roadmap(path: pathlib.Path | str) -> Roadmap:
    """Read + parse a roadmap file. Raises RoadmapError when the file is
    missing, unreadable, or structurally invalid."""
    p = pathlib.Path(path)
    if not p.exists():
        raise RoadmapError(f"roadmap file not found: {p}")
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise RoadmapError(f"cannot read roadmap {p}: {e}") from e
    return parse_roadmap(text)


class _StageBuilder:
    """Accumulates one stage section during parsing."""

    def __init__(self, number: int, title: str) -> None:
        self.number = number
        self.title = title
        self.goal: str | None = None
        self.status: str | None = None
        self.key_status: dict[str, str] | None = None
        self.keys: list[RoadmapKey] = []
        self.seen_keys: set[str] = set()
        self.keys_table_seen = False

    def set_field(self, name: str, value: str, lineno: int) -> None:
        if name == "goal":
            if self.goal is not None:
                raise RoadmapError(f"line {lineno} (stage {self.number}): duplicate '> goal:' line")
            self.goal = value
        elif name == "status":
            if self.status is not None:
                raise RoadmapError(f"line {lineno} (stage {self.number}): duplicate '> status:' line")
            if value not in STAGE_STATUSES:
                raise RoadmapError(
                    f"line {lineno} (stage {self.number}): invalid status {value!r} "
                    f"(expected one of: {', '.join(STAGE_STATUSES)})"
                )
            self.status = value
        elif name == "key-status":
            if self.key_status is not None:
                raise RoadmapError(
                    f"line {lineno} (stage {self.number}): duplicate '> key-status:' line"
                )
            self.key_status = _parse_key_status(value, lineno, self.number)

    def add_key_row(self, cells: list[str], lineno: int) -> None:
        if len(cells) != 3:
            raise RoadmapError(
                f"line {lineno} (stage {self.number}): keys table row must have 3 columns "
                f"(key | role | depends_on), got {len(cells)}: {cells!r}"
            )
        key = cells[0]
        if not key:
            raise RoadmapError(f"line {lineno} (stage {self.number}): keys table row has empty key cell")
        if key in self.seen_keys:
            raise RoadmapError(f"line {lineno} (stage {self.number}): duplicate key row {key!r}")
        self.seen_keys.add(key)
        depends_on = _parse_depends_on(cells[2])
        self.keys.append(RoadmapKey(key=key, role=cells[1], depends_on=depends_on))

    def build(self) -> RoadmapStage:
        if self.goal is None:
            raise RoadmapError(f"stage {self.number}: missing '> goal:' line")
        if self.status is None:
            raise RoadmapError(f"stage {self.number}: missing '> status:' line")
        return RoadmapStage(
            number=self.number,
            title=self.title,
            goal=self.goal,
            status=self.status,
            key_status=dict(self.key_status) if self.key_status is not None else {},
            key_status_present=self.key_status is not None,
            keys=tuple(self.keys),
        )


def _split_table_row(line: str) -> list[str]:
    """Split a markdown table row into stripped cells.

    Bounding pipes are dropped; interior empty cells are preserved so column
    positions stay aligned (spec §5 trailing-space tolerance)."""
    body = line[1:] if line.startswith("|") else line
    if body.endswith("|"):
        body = body[:-1]
    return [c.strip() for c in body.split("|")]


def _is_header_row(cells: list[str]) -> bool:
    return [c.lower() for c in cells] == ["key", "role", "depends_on"]


def _parse_depends_on(cell: str) -> tuple[str, ...]:
    """Parse a depends_on cell: '-' or empty = no deps; comma-separated key
    names otherwise. Empty segments (trailing commas) are filtered."""
    cell = cell.strip()
    if not cell or cell == "-":
        return ()
    deps: list[str] = []
    for part in cell.split(","):
        part = part.strip()
        if part and part != "-":
            deps.append(part)
    return tuple(deps)


def _parse_key_status(value: str, lineno: int, stage_number: int) -> dict[str, str]:
    """Parse the key-status value: '<key>=<status>' entries, comma separated.
    Trailing commas / extra spaces are tolerated; anything ambiguous raises."""
    entries: dict[str, str] = {}
    for part in value.split(","):
        part = part.strip()
        if not part:
            continue
        key, sep, status = part.partition("=")
        key = key.strip()
        status = status.strip()
        if not sep or not key:
            raise RoadmapError(
                f"line {lineno} (stage {stage_number}): malformed key-status entry {part!r} "
                "(expected <key>=<status>)"
            )
        if status not in KEY_STATUSES:
            raise RoadmapError(
                f"line {lineno} (stage {stage_number}): key {key!r} has invalid status "
                f"{status!r} (expected one of: {', '.join(KEY_STATUSES)})"
            )
        if key in entries:
            raise RoadmapError(
                f"line {lineno} (stage {stage_number}): duplicate key-status entry for {key!r}"
            )
        entries[key] = status
    return entries


# ── Validation (AC-001 three elements + dependency/key-status consistency) ────

def validate_roadmap(roadmap: Roadmap) -> list[str]:
    """Semantic validation. Returns a list of human-readable problems
    (empty list = valid). Structural failures already raised at parse time."""
    problems: list[str] = []
    key_stage: dict[str, int] = {}

    for idx, stage in enumerate(roadmap.stages):
        if not stage.keys:
            problems.append(f"stage {stage.number}: Keys table has no key rows (>= 1 required)")
        for k in stage.keys:
            if k.key in key_stage:
                prev = roadmap.stages[key_stage[k.key]].number
                problems.append(f"key {k.key!r} declared in both stage {prev} and stage {stage.number}")
            else:
                key_stage[k.key] = idx

    for stage in roadmap.stages:
        if not stage.goal.strip():
            problems.append(f"stage {stage.number}: goal is empty")

    for idx, stage in enumerate(roadmap.stages):
        for k in stage.keys:
            for dep in k.depends_on:
                if dep not in key_stage:
                    problems.append(
                        f"stage {stage.number} key {k.key!r}: dependency {dep!r} not found"
                    )
                elif key_stage[dep] > idx:
                    later = roadmap.stages[key_stage[dep]].number
                    problems.append(
                        f"stage {stage.number} key {k.key!r}: dependency {dep!r} "
                        f"points to later stage {later}"
                    )
                elif dep == k.key:
                    problems.append(
                        f"stage {stage.number} key {k.key!r}: depends on itself"
                    )

    cycle = _find_cycle(roadmap)
    if cycle:
        problems.append("dependency cycle: " + " -> ".join(cycle))

    for stage in roadmap.stages:
        if not stage.key_status_present:
            continue  # fresh proposal: no runtime state yet
        table_keys = {k.key for k in stage.keys}
        status_keys = set(stage.key_status)
        unknown = sorted(status_keys - table_keys)
        missing = sorted(table_keys - status_keys)
        if unknown:
            problems.append(
                f"stage {stage.number}: key-status has unknown key(s): {', '.join(unknown)}"
            )
        if missing:
            problems.append(
                f"stage {stage.number}: key-status missing key(s): {', '.join(missing)}"
            )

    return problems


def _find_cycle(roadmap: Roadmap) -> list[str] | None:
    """First dependency cycle in the declared graph (as a key path closing on
    itself), or None. Backward-only legality rules out cross-stage cycles,
    so this mainly catches intra-stage cycles / self-deps beyond the obvious."""
    graph = dependency_graph(roadmap)
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in graph}
    stack: list[str] = []

    def dfs(node: str) -> list[str] | None:
        color[node] = GRAY
        stack.append(node)
        for dep in sorted(graph.get(node, ())):
            if dep not in color:
                continue  # dangling dependency: reported by validate_roadmap
            if color[dep] == GRAY:
                return stack[stack.index(dep):] + [dep]
            if color[dep] == WHITE:
                found = dfs(dep)
                if found:
                    return found
        stack.pop()
        color[node] = BLACK
        return None

    for node in sorted(graph):
        if color[node] == WHITE:
            found = dfs(node)
            if found:
                return found
    return None


# ── Query helpers (stage enumeration + key dependency graph) ─────────────────

def stage_by_number(roadmap: Roadmap, number: int) -> RoadmapStage | None:
    for stage in roadmap.stages:
        if stage.number == number:
            return stage
    return None


def stage_of_key(roadmap: Roadmap) -> dict[str, int]:
    """Map every declared key to its stage number (first declaration wins)."""
    out: dict[str, int] = {}
    for stage in roadmap.stages:
        for k in stage.keys:
            out.setdefault(k.key, stage.number)
    return out


def dependency_graph(roadmap: Roadmap) -> dict[str, set[str]]:
    """Direct dependency graph over all declared keys (key -> set of keys it
    depends on). Edges are declared as-is; use validate_roadmap to check
    legality before driving dispatch off this graph."""
    graph: dict[str, set[str]] = {}
    for stage in roadmap.stages:
        for k in stage.keys:
            graph.setdefault(k.key, set()).update(k.depends_on)
    return graph


# ── Update helpers (pure text transforms; caller owns lock + atomic write) ────

def update_stage_status(text: str, stage_number: int, new_status: str) -> str:
    """Return text with the '> status:' line of stage <stage_number> rewritten
    to <new_status>. Only that line changes. Raises RoadmapError for an
    unknown stage, an invalid status value, or any structural parse failure
    (the caller's text is never modified on error)."""
    if new_status not in STAGE_STATUSES:
        raise RoadmapError(
            f"invalid stage status {new_status!r} (expected one of: {', '.join(STAGE_STATUSES)})"
        )
    _require_stage(parse_roadmap(text), stage_number)
    return _rewrite_field_line(text, stage_number, "status", f"> status: {new_status}")


def update_key_status(text: str, stage_number: int, key: str, new_status: str) -> str:
    """Return text with one key's entry on stage <stage_number>'s
    '> key-status:' line set to <new_status>. Creates the line (right after
    '> status:') when absent; preserves existing entry order otherwise.

    Note: once the key-status line exists, validate_roadmap requires it to
    cover every key of the stage's Keys table — callers should initialize
    entries for all stage keys when a stage starts running.

    Raises RoadmapError for an unknown stage, a key not in the stage's Keys
    table, an invalid status value, or any structural parse failure."""
    if new_status not in KEY_STATUSES:
        raise RoadmapError(
            f"invalid key status {new_status!r} (expected one of: {', '.join(KEY_STATUSES)})"
        )
    stage = _require_stage(parse_roadmap(text), stage_number)
    if key not in stage.key_names:
        raise RoadmapError(
            f"key {key!r} not in stage {stage_number} Keys table "
            f"(declared: {', '.join(stage.key_names)})"
        )
    entries = dict(stage.key_status)
    entries[key] = new_status
    new_line = "> key-status: " + ", ".join(f"{k}={v}" for k, v in entries.items())
    if stage.key_status_present:
        return _rewrite_field_line(text, stage_number, "key-status", new_line)
    return _insert_after_field(text, stage_number, "status", new_line)


def _require_stage(roadmap: Roadmap, stage_number: int) -> RoadmapStage:
    stage = stage_by_number(roadmap, stage_number)
    if stage is None:
        raise RoadmapError(
            f"stage {stage_number} not found (stages: "
            f"{', '.join(str(s.number) for s in roadmap.stages)})"
        )
    return stage


def _current_stage_number(line: str) -> int | None:
    """Stage number if the (stripped) line is a stage header; None for any
    other H2 (which ends the current stage context)."""
    if _STAGE_HEADER_RE.match(line):
        return int(_STAGE_HEADER_RE.match(line).group(1))  # type: ignore[union-attr]
    return None


def _rewrite_field_line(text: str, stage_number: int, field_name: str, new_line: str) -> str:
    """Replace the first '> <field_name>:' line inside the stage section.
    Every other line is preserved exactly (including a trailing CR)."""
    lines = text.split("\n")
    current: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or not stripped.startswith("#"):
            if current == stage_number:
                m = _FIELD_LINE_RE.match(stripped)
                if m and m.group(1) == field_name:
                    lines[i] = new_line + ("\r" if line.endswith("\r") else "")
                    return "\n".join(lines)
            continue
        if stripped.startswith("###"):
            continue  # subsection heading: stage context unchanged
        if stripped.startswith("##"):
            current = _current_stage_number(stripped)
            continue
        # H1: stage context unchanged
    raise RoadmapError(f"stage {stage_number}: '> {field_name}:' line not found")


def _insert_after_field(text: str, stage_number: int, field_name: str, new_line: str) -> str:
    """Insert new_line directly after the stage's '> <field_name>:' line."""
    lines = text.split("\n")
    current: int | None = None
    for i, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or not stripped.startswith("#"):
            if current == stage_number:
                m = _FIELD_LINE_RE.match(stripped)
                if m and m.group(1) == field_name:
                    lines.insert(i + 1, new_line + ("\r" if line.endswith("\r") else ""))
                    return "\n".join(lines)
            continue
        if stripped.startswith("###"):
            continue
        if stripped.startswith("##"):
            current = _current_stage_number(stripped)
            continue
    raise RoadmapError(f"stage {stage_number}: '> {field_name}:' line not found")
