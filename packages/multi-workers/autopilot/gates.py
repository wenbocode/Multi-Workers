"""
gates.py - human gate file protocol (goal-autopilot D-105, task T-05).

One Markdown file per gate under the gates directory
(`<project>/.agenticdoc/_autopilot/gates/gate-{seq:04d}.md` - the directory is
always passed in explicitly; path policy lives in config, not here). Scanning
the directory is scanning the queue. Frontmatter is the machine contract; the
body is the human-readable question plus a context summary.

Roles (D-105):
  - create: conductor only. This module never takes locks - the caller
    composes the `.mw/gates.lock` protocol around mutations.
  - answer: TS side `/autopilot gate` rewrites status/answered_at/
    answered_by/note. Manual file edits are equally legal answers: the file
    is the source of truth (review B5), and Python only reads.
  - consume: tick scan via enumerate()/pending_gates().

seq allocation: rescan the directory on every create and take
max(existing gate id) + 1. There is no in-memory counter, so restarts
(restart rescan) are safe by construction, and with the conductor as the
sole creator there is no concurrent-allocation conflict.

Frontmatter schema (design 4.1) - 12 fields:
  id, kind, stage, key, created_at, created_by, question, context_refs,
  status, answered_at, answered_by, note
  kind   in {stage-confirm, stage-close, stalled, budget-exhausted, goal-change,
            xkey-authorize}  (the closed set is GATE_KINDS; the TS mirror is
            status-model.ts GATE_KINDS — both sides validate fail-closed)
  status in {pending, approved, rejected}

YAML subset (hand-rolled: stdlib ships no yaml and third-party pyyaml is not
allowed):
  - `key: value` scalars; empty value or a null literal (`~`, `null`, `-`)
    parses as None
  - single-quoted strings with `''` escaping; double-quoted scalars are
    rejected explicitly (no escape-rule support)
  - `context_refs:` block list (`  - item` lines, at least one space of
    indent) or inline `[]` for the empty list
  - no comments, no flow lists other than `[]`
  - `stage` renders as a bare int or empty (None); `key`/`answered_*`/`note`
    as plain scalars when unambiguous, single-quoted otherwise
"""

from __future__ import annotations

import dataclasses
import datetime
import pathlib
import re
from collections.abc import Sequence

# --- Protocol constants -------------------------------------------------------

GATE_KINDS: tuple[str, ...] = (
    "stage-confirm",
    "stage-close",
    "stalled",
    "budget-exhausted",
    "goal-change",
    "xkey-authorize",
)

GATE_STATUSES: tuple[str, ...] = ("pending", "approved", "rejected")

CREATED_BY = "conductor"

# Canonical frontmatter field order (design 4.1 gate schema, 12 fields).
FRONTMATTER_FIELDS: tuple[str, ...] = (
    "id",
    "kind",
    "stage",
    "key",
    "created_at",
    "created_by",
    "question",
    "context_refs",
    "status",
    "answered_at",
    "answered_by",
    "note",
)

# Fields that must be present and non-empty in every gate file. The remaining
# schema fields default to their empty value (None / []) when absent, which
# matches what create() writes for empty optionals.
_REQUIRED_FIELDS = frozenset(
    {"id", "kind", "created_at", "created_by", "question", "status"}
)

GATE_ID_RE = re.compile(r"^gate-(\d+)$")
GATE_FILE_RE = re.compile(r"^gate-(\d+)\.md$")
_FIELD_LINE_RE = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*):(?:[ \t]+(.*))?[ \t]*$")
_LIST_ITEM_RE = re.compile(r"^[ \t]+-[ \t]+(.*)$")
# Scalars safe to render unquoted (no YAML indicators, no spaces, no quotes).
_PLAIN_SCALAR_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_./:+@()-]*$")
# Bare forms that would read back as null/bool under the subset below, so the
# renderer must quote them and the parser must map them to None.
_AMBIGUOUS_SCALARS = frozenset({
    "", "-", "~",
    "null", "Null", "NULL",
    "true", "True", "TRUE", "false", "False", "FALSE",
    "yes", "Yes", "YES", "no", "No", "NO", "on", "On", "off", "Off",
})
_NULL_LITERALS = frozenset({"", "~", "-", "null", "Null", "NULL"})


class GateFormatError(ValueError):
    """A gate file (or gate creation argument) violates the D-105 schema.

    Never swallowed silently: parse()/enumerate() raise it explicitly so the
    caller can skip the gate and record a timeline config event (design 9).
    """


# --- Gate object --------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class Gate:
    """One gate, parsed from (or destined for) a gate file.

    The first 12 attributes are the frontmatter schema (design 4.1); `path`
    records the originating file so consumers (conductor tick, status views)
    can point back at it. `stage`/`key` are None for stage-level gates;
    `answered_at`/`answered_by`/`note` are None while the gate is pending
    (or when a manual answer left them empty - the file is the truth, no
    cross-field consistency is enforced).
    """

    id: str
    kind: str
    stage: int | None
    key: str | None
    created_at: str
    created_by: str
    question: str
    context_refs: list[str]
    status: str
    answered_at: str | None
    answered_by: str | None
    note: str | None
    path: pathlib.Path


# --- Rendering ----------------------------------------------------------------


def _iso_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _render_scalar(value: str) -> str:
    """One YAML-subset scalar: plain when unambiguous, single-quoted else."""
    if value not in _AMBIGUOUS_SCALARS and _PLAIN_SCALAR_RE.match(value):
        return value
    return "'" + value.replace("'", "''") + "'"


def _gate_file_content(
    gate_id: str,
    kind: str,
    stage: int | None,
    key: str | None,
    question: str,
    context_refs: list[str],
    created_at: str,
) -> str:
    """Full gate file text: frontmatter in canonical order + human body."""
    lines: list[str] = [
        "---",
        f"id: {gate_id}",
        f"kind: {kind}",
        f"stage: {'' if stage is None else stage}",
        f"key: {_render_scalar(key)}" if key is not None else "key:",
        f"created_at: {created_at}",
        f"created_by: {CREATED_BY}",
        f"question: {_render_scalar(question)}",
    ]
    if context_refs:
        lines.append("context_refs:")
        lines.extend(f"  - {_render_scalar(ref)}" for ref in context_refs)
    else:
        lines.append("context_refs: []")
    lines += [
        "status: pending",
        "answered_at:",
        "answered_by:",
        "note:",
        "---",
        "",
        f"# Gate {gate_id} ({kind})",
        "",
        question,
    ]
    if context_refs:
        lines += ["", "## Context", ""]
        lines += [f"- {ref}" for ref in context_refs]
    return "\n".join(lines) + "\n"


def _write_atomic(path: pathlib.Path, content: str) -> None:
    """Atomic write with explicit UTF-8 and LF endings (mw_common style)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(str(path) + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    tmp.replace(path)


# --- Creation -----------------------------------------------------------------


def _validate_new_gate(
    kind: str,
    question: str,
    context_refs: Sequence[str],
    stage: int | None,
    key: str | None,
) -> list[str]:
    """Validate create() arguments; returns the refs as a plain list."""
    if kind not in GATE_KINDS:
        raise GateFormatError(
            f"unknown gate kind {kind!r} (expected one of: {', '.join(GATE_KINDS)})"
        )
    if not isinstance(question, str) or not question.strip():
        raise GateFormatError("question must be a non-empty string")
    if "\n" in question or "\r" in question:
        raise GateFormatError("question must be a single line")
    if stage is not None and (isinstance(stage, bool) or not isinstance(stage, int)):
        raise GateFormatError(
            f"stage must be an int or None, got {type(stage).__name__}"
        )
    if key is not None and (
        not isinstance(key, str) or not key or "\n" in key or "\r" in key
    ):
        raise GateFormatError("key must be None or a non-empty single-line string")
    refs: list[str] = []
    for ref in context_refs:
        if not isinstance(ref, str) or not ref or "\n" in ref or "\r" in ref:
            raise GateFormatError(
                "context_refs entries must be non-empty single-line strings"
            )
        refs.append(ref)
    return refs


def _next_seq(gates_dir: pathlib.Path) -> int:
    """max(existing gate id) + 1, recomputed from the directory every call.

    Restart-safe by construction (no in-memory counter). The conductor is
    the sole gate creator, so there is no concurrent-allocation conflict.
    """
    if not gates_dir.is_dir():
        return 1
    highest = 0
    for entry in gates_dir.iterdir():
        m = GATE_FILE_RE.match(entry.name)
        if m is not None:
            highest = max(highest, int(m.group(1)))
    return highest + 1


def create(
    gates_dir: pathlib.Path | str,
    kind: str,
    question: str,
    context_refs: Sequence[str] = (),
    stage: int | None = None,
    key: str | None = None,
) -> pathlib.Path:
    """Create the next pending gate file and return its path.

    seq = max(existing gate id) + 1 via directory rescan; the file is
    written atomically (tmp + replace) with LF endings. No lock is taken
    here - the caller composes the gates.lock protocol around mutations
    (D-105: conductor is the sole gate creator, TS only answers).
    """
    gates_dir = pathlib.Path(gates_dir)
    refs = _validate_new_gate(kind, question, context_refs, stage, key)
    seq = _next_seq(gates_dir)
    gate_id = f"gate-{seq:04d}"
    content = _gate_file_content(
        gate_id, kind, stage, key, question, refs, _iso_now()
    )
    path = gates_dir / f"{gate_id}.md"
    _write_atomic(path, content)
    return path


# --- Parsing ------------------------------------------------------------------


def _parse_scalar(raw: str | None, path: pathlib.Path, lineno: int) -> str | None:
    """YAML-subset scalar: ''-quoted string, null literal, or plain string."""
    if raw is None:
        return None
    if raw.startswith("'"):
        if len(raw) < 2 or not raw.endswith("'"):
            raise GateFormatError(
                f"{path}: unterminated single-quoted scalar (line {lineno}): {raw!r}"
            )
        return raw[1:-1].replace("''", "'")
    if raw.startswith('"'):
        raise GateFormatError(
            f"{path}: double-quoted scalars are not supported (line {lineno}): {raw!r}"
        )
    if raw in _NULL_LITERALS:
        return None
    return raw


def _parse_frontmatter(text: str, path: pathlib.Path) -> dict[str, object]:
    """Parse the leading `---` frontmatter block into a field dict.

    Scalar values are stored unquoted (str | None); context_refs is stored as
    a list[str]. Anything else raises GateFormatError explicitly.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise GateFormatError(f"{path}: frontmatter must open with a '---' line")
    fields: dict[str, object] = {}
    in_refs = False
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            return fields
        if in_refs:
            item = _LIST_ITEM_RE.match(line)
            if item is not None:
                ref = _parse_scalar(item.group(1), path, i + 1)
                if not ref:
                    raise GateFormatError(
                        f"{path}: empty context_refs item (line {i + 1})"
                    )
                fields["context_refs"].append(ref)  # type: ignore[union-attr]
                i += 1
                continue
            in_refs = False  # dedent: fall through to a normal field line
        field = _FIELD_LINE_RE.match(line)
        if field is None:
            raise GateFormatError(
                f"{path}: invalid frontmatter line {i + 1}: {line!r}"
            )
        name = field.group(1)
        if name not in FRONTMATTER_FIELDS:
            raise GateFormatError(
                f"{path}: unknown frontmatter field '{name}' (line {i + 1})"
            )
        if name in fields:
            raise GateFormatError(
                f"{path}: duplicate frontmatter field '{name}' (line {i + 1})"
            )
        raw = field.group(2)
        if name == "context_refs":
            if raw is None or raw == "":
                fields["context_refs"] = []
                in_refs = True
            elif raw == "[]":
                fields["context_refs"] = []
            else:
                raise GateFormatError(
                    f"{path}: context_refs must be a block list or [] (line {i + 1})"
                )
        else:
            fields[name] = _parse_scalar(raw, path, i + 1)
        i += 1
    raise GateFormatError(f"{path}: frontmatter never closes with a '---' line")


def _check_iso(value: str, field: str, path: pathlib.Path) -> None:
    """Validate an ISO-8601 timestamp (accepts the trailing Z form TS writes)."""
    probe = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        datetime.datetime.fromisoformat(probe)
    except ValueError as exc:
        raise GateFormatError(
            f"{path}: {field} is not an ISO-8601 timestamp: {value!r}"
        ) from exc


def _to_gate(fields: dict[str, object], path: pathlib.Path) -> Gate:
    """Type/enum-validate the parsed field dict and build the Gate."""

    def required(name: str) -> str:
        value = fields[name]
        if not isinstance(value, str) or not value:
            raise GateFormatError(f"{path}: field '{name}' must be a non-empty string")
        return value

    def optional(name: str) -> str | None:
        value = fields.get(name)
        if value is None:
            return None
        if not isinstance(value, str):  # defensive: only str | None is stored
            raise GateFormatError(f"{path}: field '{name}' must be a string")
        return value or None

    missing = [name for name in _REQUIRED_FIELDS if name not in fields]
    if missing:
        raise GateFormatError(
            f"{path}: missing frontmatter field(s): {', '.join(missing)}"
        )

    gate_id = required("id")
    if not GATE_ID_RE.match(gate_id):
        raise GateFormatError(
            f"{path}: id must match 'gate-<digits>', got {gate_id!r}"
        )
    kind = required("kind")
    if kind not in GATE_KINDS:
        raise GateFormatError(
            f"{path}: unknown kind {kind!r} (expected one of: {', '.join(GATE_KINDS)})"
        )
    status = required("status")
    if status not in GATE_STATUSES:
        raise GateFormatError(
            f"{path}: unknown status {status!r} "
            f"(expected one of: {', '.join(GATE_STATUSES)})"
        )
    stage_raw = fields.get("stage")
    stage: int | None
    if stage_raw is None:
        stage = None
    elif isinstance(stage_raw, str):
        try:
            stage = int(stage_raw)
        except ValueError:
            raise GateFormatError(
                f"{path}: stage must be an integer, got {stage_raw!r}"
            ) from None
    else:
        raise GateFormatError(f"{path}: stage must be an integer or empty")
    refs_raw = fields.get("context_refs", [])
    if not isinstance(refs_raw, list) or not all(
        isinstance(r, str) and r for r in refs_raw
    ):
        raise GateFormatError(
            f"{path}: context_refs must be a list of non-empty strings"
        )
    created_at = required("created_at")
    _check_iso(created_at, "created_at", path)
    answered_at = optional("answered_at")
    if answered_at is not None:
        _check_iso(answered_at, "answered_at", path)

    return Gate(
        id=gate_id,
        kind=kind,
        stage=stage,
        key=optional("key"),
        created_at=created_at,
        created_by=required("created_by"),
        question=required("question"),
        context_refs=list(refs_raw),
        status=status,
        answered_at=answered_at,
        answered_by=optional("answered_by"),
        note=optional("note"),
        path=path,
    )


def parse(path: pathlib.Path | str) -> Gate:
    """Parse one gate file into a Gate.

    Raises GateFormatError (a ValueError) on any frontmatter/schema violation
    - corrupt files are never silently swallowed; the caller skips and
    records a timeline config event (design 9). A missing or unreadable file
    raises OSError unchanged. The body below the frontmatter is ignored
    (human prose only).
    """
    path = pathlib.Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise GateFormatError(f"{path}: gate file is not valid UTF-8: {exc}") from exc
    return _to_gate(_parse_frontmatter(text, path), path)


# --- Queue scan ---------------------------------------------------------------


def enumerate(gates_dir: pathlib.Path | str) -> list[Gate]:
    """All gates in the directory, ordered by seq. Directory scan = queue.

    Non-gate files (and leftover `.tmp` files) are ignored; a missing
    directory is an empty queue. Raises GateFormatError naming the offending
    file if any gate file is corrupt or its frontmatter id disagrees with its
    file name - the skip policy (timeline config event) belongs to the caller.
    """
    gates_dir = pathlib.Path(gates_dir)
    if not gates_dir.is_dir():
        return []
    found: list[tuple[int, str, Gate]] = []
    for entry in sorted(gates_dir.iterdir()):
        m = GATE_FILE_RE.match(entry.name)
        if m is None or not entry.is_file():
            continue
        gate = parse(entry)
        if gate.id != entry.stem:
            raise GateFormatError(
                f"{entry}: frontmatter id {gate.id!r} does not match file name"
            )
        found.append((int(m.group(1)), gate.id, gate))
    found.sort(key=lambda item: (item[0], item[1]))
    return [gate for _, _, gate in found]


def pending_gates(gates_dir: pathlib.Path | str) -> list[Gate]:
    """Only gates still awaiting an answer (status == 'pending')."""
    return [gate for gate in enumerate(gates_dir) if gate.status == "pending"]
