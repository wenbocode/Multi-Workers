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

Frontmatter schema (design 4.1) - 12 base fields plus 28 optional v2 fields
(design D1.1 items 1..26 + the two consumption-record fields). Every v2 field
is optional and never enters _REQUIRED_FIELDS, so v1 files parse unchanged and
an absent gate_schema means 1 (legacy):
  base: id, kind, stage, key, created_at, created_by, question, context_refs,
        status, answered_at, answered_by, note
  v2:   reason_code, evidence_refs, loop, used_rounds, round_limit,
        credits_used, observed_at, verdicts_final, open_items, subject_sha256,
        roadmap_validation, proposal_sha256, goal_sha256, constraints,
        goal_sha256_before, goal_sha256_after, goal_diff, write_scope,
        blast_radius, answer_source, auto_policy_id, expires_at,
        evidence_anchor_mtime_ns, default_action, out_of_band_actions,
        gate_schema, consumed_at, consumed_seq
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
import json
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

# Schema version marker values: absent means 1 (legacy v1 file), create()
# writes 2. Any other value is a fail-closed parse error (enum convention).
GATE_SCHEMA_LEGACY = 1
GATE_SCHEMA_CURRENT = 2
_GATE_SCHEMA_VALUES = frozenset({GATE_SCHEMA_LEGACY, GATE_SCHEMA_CURRENT})

# Canonical frontmatter field order. The first 12 names are the frozen base
# schema (design 4.1; never reordered, never repurposed); the remaining 28 are
# the additive v2 set (design D1.1 1..26 + consumed_at/consumed_seq).
FRONTMATTER_FIELDS: tuple[str, ...] = (
    # base (design 4.1)
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
    # v2 (design D1.1 1..26)
    "reason_code",
    "evidence_refs",
    "loop",
    "used_rounds",
    "round_limit",
    "credits_used",
    "observed_at",
    "verdicts_final",
    "open_items",
    "subject_sha256",
    "roadmap_validation",
    "proposal_sha256",
    "goal_sha256",
    "constraints",
    "goal_sha256_before",
    "goal_sha256_after",
    "goal_diff",
    "write_scope",
    "blast_radius",
    "answer_source",
    "auto_policy_id",
    "expires_at",
    "evidence_anchor_mtime_ns",
    "default_action",
    "out_of_band_actions",
    "gate_schema",
    # consumption record (design D-004, outside the D1.1 26)
    "consumed_at",
    "consumed_seq",
)

# Fields that must be present and non-empty in every gate file. The remaining
# schema fields default to their empty value (None / []) when absent, which
# matches what create() writes for empty optionals. FROZEN: schema v2 stays
# purely additive - the assert below fires at import time if this set is
# edited (length or membership).
_REQUIRED_FIELDS = frozenset(
    {"id", "kind", "created_at", "created_by", "question", "status"}
)
assert _REQUIRED_FIELDS == frozenset(
    {"id", "kind", "created_at", "created_by", "question", "status"}
) and len(_REQUIRED_FIELDS) == 6, (
    "gates._REQUIRED_FIELDS is frozen at 6 fields; v2 fields must stay optional"
)

# Named block-list fields (YAML subset: `name:` + `  - item` lines, or `[]`).
# Every other structured field is a single-line JSON substring instead of YAML
# nesting (design D1.5): json-list for `[...]`, json-obj for `{...}`. Malformed
# JSON is a GateFormatError, never a silently empty value.
_LIST_FIELDS = {"context_refs", "evidence_refs"}
_JSON_LIST_FIELDS = frozenset(
    {
        "verdicts_final",
        "open_items",
        "roadmap_validation",
        "constraints",
        "write_scope",
        "out_of_band_actions",
    }
)
_JSON_OBJ_FIELDS = frozenset({"goal_diff", "blast_radius"})

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

    The first 12 attributes are the frozen base schema (design 4.1); the
    remaining attributes are the optional v2 set (design D1.1 1..26 plus the
    consumption record), defaulting to None/[]/1 when absent. `path` records
    the originating file so consumers (conductor tick, status views) can point
    back at it. `stage`/`key` are None for stage-level gates;
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
    # --- schema v2 (all optional; absent -> None/[]/1) --------------------
    reason_code: str | None = None
    evidence_refs: list[str] = dataclasses.field(default_factory=list)
    loop: str | None = None
    used_rounds: int | None = None
    round_limit: int | None = None
    credits_used: int | None = None
    observed_at: str | None = None
    verdicts_final: list[object] | None = None
    open_items: list[object] | None = None
    subject_sha256: str | None = None
    roadmap_validation: list[object] | None = None
    proposal_sha256: str | None = None
    goal_sha256: str | None = None
    constraints: list[object] | None = None
    goal_sha256_before: str | None = None
    goal_sha256_after: str | None = None
    goal_diff: dict[str, object] | None = None
    write_scope: list[object] | None = None
    blast_radius: dict[str, object] | None = None
    answer_source: str | None = None
    auto_policy_id: str | None = None
    expires_at: str | None = None
    evidence_anchor_mtime_ns: int | None = None
    default_action: str | None = None
    out_of_band_actions: list[object] | None = None
    gate_schema: int = GATE_SCHEMA_LEGACY
    consumed_at: str | None = None
    consumed_seq: int | None = None


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
        f"gate_schema: {GATE_SCHEMA_CURRENT}",
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


def _parse_list_field(
    name: str, raw: str | None, path: pathlib.Path, lineno: int
) -> list[str]:
    """One named list field (_LIST_FIELDS): a block list (`  - item`), `[]`,
    or a single-line JSON array scalar (design D2.3 after-example). Malformed
    JSON is a GateFormatError - never a silently empty list."""
    if raw is None or raw == "":
        return []  # block list items, if any, follow on the next lines
    if raw == "[]":
        return []
    if raw.startswith("'") and raw.endswith("'") and len(raw) >= 2:
        inner = raw[1:-1].replace("''", "'")
        try:
            decoded = json.loads(inner)
        except json.JSONDecodeError as exc:
            raise GateFormatError(
                f"{path}: {name} must be a block list, [] or a single-line "
                f"JSON array (line {lineno}): {exc}"
            ) from exc
        if not isinstance(decoded, list) or not all(
            isinstance(item, str) and item for item in decoded
        ):
            raise GateFormatError(
                f"{path}: {name} JSON array must contain non-empty strings "
                f"(line {lineno})"
            )
        return list(decoded)
    raise GateFormatError(
        f"{path}: {name} must be a block list or [] (line {lineno})"
    )


def _parse_frontmatter(text: str, path: pathlib.Path) -> dict[str, object]:
    """Parse the leading `---` frontmatter block into a field dict.

    Scalar values are stored unquoted (str | None); the named list fields
    (_LIST_FIELDS) are stored as list[str]. Anything else raises
    GateFormatError explicitly.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        raise GateFormatError(f"{path}: frontmatter must open with a '---' line")
    fields: dict[str, object] = {}
    active_list: str | None = None
    i = 1
    while i < len(lines):
        line = lines[i]
        if line.strip() == "---":
            return fields
        if active_list is not None:
            item = _LIST_ITEM_RE.match(line)
            if item is not None:
                ref = _parse_scalar(item.group(1), path, i + 1)
                if not ref:
                    raise GateFormatError(
                        f"{path}: empty {active_list} item (line {i + 1})"
                    )
                fields[active_list].append(ref)  # type: ignore[union-attr]
                i += 1
                continue
            active_list = None  # dedent: fall through to a normal field line
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
        if name in _LIST_FIELDS:
            fields[name] = _parse_list_field(name, raw, path, i + 1)
            if raw is None or raw == "":
                active_list = name  # block list items follow
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

    def optional_int(name: str) -> int | None:
        value = fields.get(name)
        if value is None:
            return None
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                raise GateFormatError(
                    f"{path}: field '{name}' must be an integer, got {value!r}"
                ) from None
        raise GateFormatError(f"{path}: field '{name}' must be an integer or empty")

    def optional_iso(name: str) -> str | None:
        value = optional(name)
        if value is not None:
            _check_iso(value, name, path)
        return value

    def optional_json(name: str) -> object:
        value = optional(name)
        if value is None:
            return None
        if name in _JSON_LIST_FIELDS:
            expected: type = list
        elif name in _JSON_OBJ_FIELDS:
            expected = dict
        else:  # programming error: only declared JSON fields call this
            raise GateFormatError(f"{path}: field '{name}' is not a JSON field")
        shape = "array" if expected is list else "object"
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError as exc:
            raise GateFormatError(
                f"{path}: field '{name}' must be a single-line JSON {shape}: {exc}"
            ) from exc
        if not isinstance(decoded, expected):
            raise GateFormatError(
                f"{path}: field '{name}' must decode to a JSON {shape}, got "
                f"{type(decoded).__name__}"
            )
        return decoded

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
    evidence_raw = fields.get("evidence_refs", [])
    if not isinstance(evidence_raw, list) or not all(
        isinstance(r, str) and r for r in evidence_raw
    ):
        raise GateFormatError(
            f"{path}: evidence_refs must be a list of non-empty strings"
        )
    gate_schema = optional_int("gate_schema")
    if gate_schema is None:
        gate_schema = GATE_SCHEMA_LEGACY
    elif gate_schema not in _GATE_SCHEMA_VALUES:
        raise GateFormatError(
            f"{path}: gate_schema must be one of "
            f"{sorted(_GATE_SCHEMA_VALUES)}, got {gate_schema}"
        )

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
        reason_code=optional("reason_code"),
        evidence_refs=list(evidence_raw),
        loop=optional("loop"),
        used_rounds=optional_int("used_rounds"),
        round_limit=optional_int("round_limit"),
        credits_used=optional_int("credits_used"),
        observed_at=optional_iso("observed_at"),
        verdicts_final=optional_json("verdicts_final"),
        open_items=optional_json("open_items"),
        subject_sha256=optional("subject_sha256"),
        roadmap_validation=optional_json("roadmap_validation"),
        proposal_sha256=optional("proposal_sha256"),
        goal_sha256=optional("goal_sha256"),
        constraints=optional_json("constraints"),
        goal_sha256_before=optional("goal_sha256_before"),
        goal_sha256_after=optional("goal_sha256_after"),
        goal_diff=optional_json("goal_diff"),
        write_scope=optional_json("write_scope"),
        blast_radius=optional_json("blast_radius"),
        answer_source=optional("answer_source"),
        auto_policy_id=optional("auto_policy_id"),
        expires_at=optional_iso("expires_at"),
        evidence_anchor_mtime_ns=optional_int("evidence_anchor_mtime_ns"),
        default_action=optional("default_action"),
        out_of_band_actions=optional_json("out_of_band_actions"),
        gate_schema=gate_schema,
        consumed_at=optional_iso("consumed_at"),
        consumed_seq=optional_int("consumed_seq"),
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
