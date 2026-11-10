"""autopilot/xkey.py — cross-key red repair mechanism: pure logic + file primitives.

Key ``xkey-repair-mechanism`` (design D-001..D-012). This module owns every
mechanical judgement the mechanism needs; ``conductor.py`` only mounts it
(T-03) and never re-implements any of it. It deliberately does **not** import
``conductor`` (no cycles) and pulls no third-party dependency.

Layout (all under ``<project>/.agenticdoc/_autopilot/xkey/``, D-004)::

    ledger.json                     # {rows: [row, ...], updated_at}
    tickets/xkey-<request_id>.md    # machine frontmatter + human body (D-003)
    evidence/<request_id>/          # per-request evidence bundle (AC-006)

The ``root`` argument of every public function is the **project root** (the
directory that contains ``.agenticdoc/``), never the ``.agenticdoc`` dir.

Contract notes (frozen in ``plan.md``; signatures are byte-for-byte):

* ``parse_registration`` / ``collect_registrations`` — D-001 compatible
  parser. Key/value pairs win; ``path::test`` and owner-shape whitelists are
  the fallback. A registration is only usable when ``(file, test_id)`` **and**
  a concrete ``owner_key`` are present; anything else returns ``None``
  ("unparseable ⇒ escalate only, never propose", AC-002). Role words
  (``兄弟 key`` / ``PM`` / ``conductor`` / ``owner``) are never owners.
* The ledger row shape is ``{dedup_key, source_key, owner_key, test_id, file,
  frozen_block, status, request_id, history[]}``; appending the same
  ``dedup_key`` never adds a row (only merges fields / appends de-duplicated
  history entries, AC-001). A corrupt ledger is never overwritten.

Tickets are gate-protocol *shape* (``---`` fenced ``key: value``
block + human body) rendered by this module's own YAML subset; complex values
are rendered as nested blocks (or inline JSON, which the parser also accepts,
so hand-written tickets round-trip).

H07 (AC-026/AC-027/AC-052) adds the restricted cross-key repair machine layer
at the end of this module: :func:`assess_repair_request` judges the complete PM
note + exact approval + role/actor + claim, and :func:`claim_acquire` takes
real per-file ``O_CREAT|O_EXCL`` markers in sorted order. None of these
judgements writes or dispatches; :func:`apply_block_replace` only writes when
the caller passes an executable verdict that names the target file.

Hashing (D-011/D-012): every mechanical anchor is a **byte-exact** sha256 over
the frozen ``line_range`` bytes, CRLF/LF untouched. Matching EOL-normalized
values are recorded alongside as ``sha256_eol_normalized`` (same recipe as
``mw_common.sha256_eol_normalized``, which is path-scoped and therefore not
directly usable for a block).
"""

from __future__ import annotations

import ast
import dataclasses
import datetime
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import socket
import subprocess
import sys
import time
import uuid

# Script-mode bootstrap: mirror conductor.py / state.py so ``import mw_common``
# works both under pytest (repo root on sys.path) and as a plain module.
_PARENT = pathlib.Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import mw_common  # noqa: E402  (path bootstrapped above)
import decision_validity as _validity  # noqa: E402  (pure sibling module)
from autopilot import contract_guard as _guard  # noqa: E402

# ── Public constants (frozen contract) ────────────────────────────────────────

REGISTRATION_KEYS: tuple[str, ...] = (
    "cross_key_test",
    "owner",
    "handoff",
    "frozen_block",
)

XKEY_STATUSES: tuple[str, ...] = (
    "detected",
    "ticketed",
    "approved",
    "applied",
    "verified",
    "closed",
    "rejected",
    "timed-out",
    "boundary_violation",
    "escalated",
)

# Ticket statuses that may never authorise an on-disk write. Unknown/absent
# status is tolerated by the primitive (the conductor owns the state machine),
# but a *known* unauthorised status is fail-closed.
_UNAUTHORIZED_APPLY_STATUSES = frozenset({
    "detected",
    "ticketed",
    "rejected",
    "timed-out",
    "boundary_violation",
    "escalated",
})

XKEY_DIR_REL = (".agenticdoc", "_autopilot", "xkey")
LEDGER_NAME = "ledger.json"
TICKETS_DIR_NAME = "tickets"
EVIDENCE_DIR_NAME = "evidence"
TICKET_PREFIX = "xkey-"
LOCK_NAME = "xkey-ledger.lock"

# Owner values that are roles (or relation words), never concrete keys
# (FM corpus S-E/S-G/S-H observed all of these in the wild).
_OWNER_ROLE_TOKENS = frozenset({
    "兄弟 key",
    "兄弟key",
    "兄弟",
    "pm",
    "conductor",
    "owner",
    "user",
    "human",
})

_KEY_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# ── Errors ─────────────────────────────────────────────────────────────────────


class XKeyError(ValueError):
    """Base class for every mechanical refusal in this module (fail-closed)."""


class XKeyFormatError(XKeyError):
    """Malformed input: ledger, ticket or proposal shape."""


class XKeyLedgerCorrupt(XKeyFormatError):
    """The ledger exists but is unusable; it is never overwritten."""


class XKeyShaDrift(XKeyError):
    """The frozen block bytes no longer match the ticket's recorded sha256."""


class XKeyAuthorizationError(XKeyError):
    """A write was attempted on a ticket that is not authorised."""


class XKeyBoundaryViolation(XKeyAuthorizationError):
    """The actual splice overlaps the ticket's forbidden file or lines."""


# ── Small time/path/hash helpers ──────────────────────────────────────────────


def _iso_now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _xkey_dir(root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(root).joinpath(*XKEY_DIR_REL)


def ledger_path(root: pathlib.Path | str) -> pathlib.Path:
    return _xkey_dir(root) / LEDGER_NAME


def tickets_dir(root: pathlib.Path | str) -> pathlib.Path:
    return _xkey_dir(root) / TICKETS_DIR_NAME


def evidence_dir(root: pathlib.Path | str, request_id: str) -> pathlib.Path:
    return _xkey_dir(root) / EVIDENCE_DIR_NAME / request_id


def _lock_path(root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(root) / ".mw" / LOCK_NAME


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sha256_eol_normalized_bytes(data: bytes) -> str:
    """Block-scoped twin of ``mw_common.sha256_eol_normalized`` (D-012).

    ``mw_common.sha256_eol_normalized`` hashes a whole file path; the frozen
    block identity needs the same CRLF→LF recipe on a byte slice.
    """
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def _split_text_lines(text: str) -> list[str]:
    """Physical lines (keepends) using Python's own newline rules (\\n/\\r\\n/\\r)."""
    out: list[str] = []
    start = 0
    i = 0
    length = len(text)
    while i < length:
        ch = text[i]
        if ch == "\n":
            out.append(text[start:i + 1])
            start = i + 1
        elif ch == "\r":
            if i + 1 < length and text[i + 1] == "\n":
                i += 1
            out.append(text[start:i + 1])
            start = i + 1
        i += 1
    if start < length:
        out.append(text[start:])
    return out


def _split_bytes_lines(data: bytes) -> list[bytes]:
    """Byte twin of :func:`_split_text_lines` (indices stay AST-compatible)."""
    out: list[bytes] = []
    start = 0
    i = 0
    length = len(data)
    while i < length:
        byte = data[i]
        if byte == 0x0A:
            out.append(data[start:i + 1])
            start = i + 1
        elif byte == 0x0D:
            if i + 1 < length and data[i + 1] == 0x0A:
                i += 1
            out.append(data[start:i + 1])
            start = i + 1
        i += 1
    if start < length:
        out.append(data[start:])
    return out


def _normalize_rel(path_value: object) -> str:
    """Normalise a path-ish value for comparison: slash form, no line suffix."""
    text = str(path_value).strip().strip("`'\"* ")
    text = text.replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    text = re.sub(r":\d+(?:-\d+)?$", "", text)
    return text


# ── Registration parsing (D-001) ──────────────────────────────────────────────

# `k=v` with a value that may be backtick/double/single quoted or a bare token.
_KV_RE = re.compile(
    r"(?P<key>[A-Za-z_][A-Za-z0-9_]*)"
    r"\s*=\s*"
    r"(?P<val>`[^`]*`|\"[^\"]*\"|'[^']*'|[^\s]+)"
)
_OWNER_COLON_RE = re.compile(
    r"\bowner\s*:\s*(?P<val>`[^`]*`|\"[^\"]*\"|'[^']*'|[^\s]+)",
    re.IGNORECASE,
)
_PATH_TEST_RE = re.compile(
    r"(?P<file>[A-Za-z0-9_./\\-]+\.py)::(?P<test>[A-Za-z_][A-Za-z0-9_]*)"
)
_BOLD_BACKTICK_RE = re.compile(r"\*\*\s*`([^`]+)`\s*\*\*")
_HANDOFF_HINT_KEY = "not_fixed_by_this_key"


def _strip_wrappers(value: str) -> str:
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "`\"'":
        text = text[1:-1] if text[0] != "'" else text[1:-1].replace("''", "'")
    return text.strip()


def _valid_owner(value: object) -> str | None:
    """A concrete key name, or None (role words and non-key shapes rejected)."""
    if not isinstance(value, str):
        return None
    text = _strip_wrappers(value)
    if not text:
        return None
    if text.lower() in _OWNER_ROLE_TOKENS:
        return None
    if not _KEY_NAME_RE.match(text):
        return None
    return text


def _line_partial(line: str) -> dict | None:
    """One line → partial registration record (or None when nothing matches)."""
    record: dict = {}
    handoff_hint = False

    for match in _KV_RE.finditer(line):
        key = match.group("key")
        raw = _strip_wrappers(match.group("val"))
        if key == "cross_key_test":
            _apply_cross_key_test(record, raw)
        elif key in ("file", "path"):
            if not record.get("file") and raw:
                record["file"] = raw
        elif key in ("test_id", "test"):
            if not record.get("test_id") and raw:
                record["test_id"] = raw
        elif key in ("owner", "owner_key"):
            owner = _valid_owner(raw)
            if owner and not record.get("owner_key"):
                record["owner_key"] = owner
        elif key == "handoff":
            if raw and not record.get("handoff"):
                record["handoff"] = raw
        elif key in ("frozen_block", "frozen"):
            if raw and not record.get("frozen_block"):
                record["frozen_block"] = raw
        elif key == _HANDOFF_HINT_KEY and raw.lower() == "true":
            handoff_hint = True

    if not record.get("file") or not record.get("test_id"):
        path_match = _PATH_TEST_RE.search(line)
        if path_match:
            if not record.get("file"):
                record["file"] = path_match.group("file")
            if not record.get("test_id"):
                record["test_id"] = path_match.group("test")

    if not record.get("owner_key"):
        colon = _OWNER_COLON_RE.search(line)
        if colon:
            owner = _valid_owner(colon.group("val"))
            if owner:
                record["owner_key"] = owner

    if not record.get("owner_key") and (
        "跨 key" in line or "跨key" in line or "cross-key" in line
        or "cross_key" in line or _PATH_TEST_RE.search(line) is not None
    ):
        for candidate in _BOLD_BACKTICK_RE.findall(line):
            owner = _valid_owner(candidate)
            if owner:
                record["owner_key"] = owner
                break

    if record.get("handoff") is None and handoff_hint:
        record["handoff"] = "registered"

    if not record:
        return None
    record.setdefault("frozen_block", None)
    return record


def _apply_cross_key_test(record: dict, raw: str) -> None:
    """``<path>::<test>`` (or a bare path) from the ``cross_key_test`` value."""
    if not raw:
        return
    if "::" in raw:
        file_part, _, test_part = raw.partition("::")
        if file_part and not record.get("file"):
            record["file"] = file_part.strip()
        if test_part and not record.get("test_id"):
            record["test_id"] = test_part.strip()
    elif not record.get("file"):
        record["file"] = raw


def _merge_partials(records: list[dict]) -> list[dict]:
    """Group partials by ``(file, test_id)``; union fields, keep first-seen order.

    Partials without a concrete ``(file, test_id)`` cannot be addressed and are
    dropped (no guessing, D-001).
    """
    merged: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []
    for record in records:
        file_part = record.get("file")
        test_part = record.get("test_id")
        if not file_part or not test_part:
            continue
        key = (file_part, test_part)
        if key not in merged:
            merged[key] = dict(record)
            order.append(key)
        else:
            target = merged[key]
            for field, value in record.items():
                if value and not target.get(field):
                    target[field] = value
    return [merged[key] for key in order]


def _complete_registration(records: list[dict]) -> dict | None:
    for record in records:
        if record.get("file") and record.get("test_id") and record.get("owner_key"):
            return {
                "file": record["file"],
                "test_id": record["test_id"],
                "owner_key": record["owner_key"],
                "handoff": record.get("handoff"),
                "frozen_block": record.get("frozen_block"),
            }
    return None


def parse_registration(source_text: str) -> dict | None:
    """Parse one source's handoff registration (D-001). ``None`` = escalate only.

    Returns ``{"file","test_id","owner_key","handoff","frozen_block"}`` only
    when ``(file, test_id)`` and a concrete ``owner_key`` are all present.
    Prose-only shapes (FM S-C/S-E/S-F), unresolved-owner shapes (S-G/S-H) and
    count-only shapes (S-I) all return ``None``.
    """
    if not isinstance(source_text, str) or not source_text:
        return None
    records = [rec for rec in (_line_partial(line) for line in source_text.splitlines()) if rec]
    return _complete_registration(_merge_partials(records))


def collect_registrations(sources: list[tuple[str, str]]) -> dict | None:
    """Parse ``[(source_name, text), ...]`` and merge per ``(file, test_id)``.

    Fields of the same red may live in different sources (FM: ``path::test``
    in ``report.md``, ``owner=`` in both); the union is only usable when one
    red reaches ``(file, test_id, owner_key)``.
    """
    records: list[dict] = []
    for source in sources or []:
        try:
            name, text = source
        except (TypeError, ValueError):
            continue
        if not isinstance(text, str):
            continue
        records.extend(rec for rec in (_line_partial(line) for line in text.splitlines()) if rec)
    return _complete_registration(_merge_partials(records))


# ── Ledger (D-002) ────────────────────────────────────────────────────────────

_ROW_FIELDS = (
    "source_key",
    "owner_key",
    "test_id",
    "file",
    "frozen_block",
    "status",
    "request_id",
)


def dedup_key(file: str, test_id: str, block_sha: str) -> str:
    """Stable identity of one red: sha256 over ``(file, test_id, block_sha)``."""
    raw = "\x1f".join([
        "" if file is None else str(file),
        "" if test_id is None else str(test_id),
        "" if block_sha is None else str(block_sha),
    ])
    return _sha256(raw.encode("utf-8"))


def _empty_ledger() -> dict:
    return {"rows": [], "updated_at": None}


def _ledger_read(root: pathlib.Path | str) -> tuple[dict, bool]:
    """(ledger, corrupt). Corrupt is reported, never repaired here."""
    path = ledger_path(root)
    if not path.is_file():
        return _empty_ledger(), False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, UnicodeDecodeError):
        return _empty_ledger(), True
    if not isinstance(data, dict):
        return _empty_ledger(), True
    rows = data.get("rows")
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return _empty_ledger(), True
    return {"rows": list(rows), "updated_at": data.get("updated_at")}, False


def ledger_load(root: pathlib.Path | str) -> dict:
    """Read the ledger; missing **or** corrupt yields the empty shape (fail-closed)."""
    data, _ = _ledger_read(root)
    return data


def _history_key(entry: dict) -> tuple:
    detail = entry.get("detail")
    return (
        entry.get("ts"),
        entry.get("event"),
        json.dumps(detail, ensure_ascii=False, sort_keys=True, default=str),
    )


def _normalize_history(raw: object) -> list[dict]:
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    seen: set[tuple] = set()
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        normalized = {
            "ts": entry.get("ts") or _iso_now(),
            "event": str(entry.get("event") or ""),
            "detail": entry.get("detail"),
        }
        key = _history_key(normalized)
        if key in seen:
            continue
        seen.add(key)
        out.append(normalized)
    return out


def _merge_into(existing: dict, incoming: dict) -> None:
    for field in _ROW_FIELDS:
        if field not in incoming:
            continue
        value = incoming[field]
        if value is None or value == "":
            continue
        if existing.get(field) == value:
            continue
        if field == "status" and existing.get("status") == "closed":
            # AC-007: a closed row never regresses; repeated closure is a no-op.
            continue
        existing[field] = value
    for key, value in incoming.items():
        if key in ("dedup_key", "history") or key in _ROW_FIELDS:
            continue
        if value is None or value == "":
            continue
        if existing.get(key) != value:
            existing[key] = value
    existing_history = existing.setdefault("history", [])
    seen = {_history_key(entry) for entry in existing_history if isinstance(entry, dict)}
    for entry in _normalize_history(incoming.get("history")):
        key = _history_key(entry)
        if key not in seen:
            seen.add(key)
            existing_history.append(entry)


def _write_json_atomic(path: pathlib.Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(str(path) + ".tmp")
    tmp.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(tmp, path)


def ledger_append(root: pathlib.Path | str, row: dict) -> str:
    """Locked read-modify-write append; idempotent on ``dedup_key`` (AC-001).

    A repeated ``dedup_key`` never adds a row: fields are merged and incoming
    ``history`` entries are appended only if new. The write is ``tmp`` +
    ``os.replace``. A corrupt ledger raises :class:`XKeyLedgerCorrupt` and is
    left untouched. Returns the ``dedup_key``.
    """
    if not isinstance(row, dict):
        raise XKeyFormatError("ledger row must be a dict")
    key = row.get("dedup_key")
    if not isinstance(key, str) or not key:
        raise XKeyFormatError("ledger row requires a non-empty 'dedup_key'")

    lock = _lock_path(root)
    mw_common.acquire_lock(lock)
    try:
        data, corrupt = _ledger_read(root)
        if corrupt:
            raise XKeyLedgerCorrupt(
                f"refusing to write corrupt ledger: {ledger_path(root)}"
            )
        rows: list[dict] = data["rows"]
        existing = None
        for candidate in rows:
            if candidate.get("dedup_key") == key:
                existing = candidate
                break
        if existing is None:
            new_row = {"dedup_key": key}
            _merge_into(new_row, row)
            rows.append(new_row)
        else:
            _merge_into(existing, row)
        data["updated_at"] = _iso_now()
        _write_json_atomic(ledger_path(root), {"rows": rows, "updated_at": data["updated_at"]})
    finally:
        mw_common.release_lock(lock)
    return key


# ── Tickets (D-003) ───────────────────────────────────────────────────────────

_MAP_LINE_RE = re.compile(
    r"^(?P<indent> *)(?P<key>[A-Za-z_][A-Za-z0-9_.-]*):(?:[ \t]+(?P<val>.*))?[ \t]*$"
)
_SEQ_LINE_RE = re.compile(r"^(?P<indent> *)-(?:[ \t]+(?P<val>.*))?[ \t]*$")
_PLAIN_SCALAR_RE = re.compile(r"^[A-Za-z0-9_./+:@()-]+$")
_NUMERIC_SCALAR_RE = re.compile(r"^-?\d+(?:\.\d+)?$")
_AMBIGUOUS_SCALARS = frozenset({
    "", "-", "~", "null", "Null", "NULL",
    "true", "True", "TRUE", "false", "False", "FALSE",
})
_REQUEST_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")


def _indent_of(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def _render_scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return repr(value)
    text = str(value)
    if "\n" in text or "\r" in text:
        return json.dumps(text, ensure_ascii=False)
    if text in _AMBIGUOUS_SCALARS:
        return "'" + text.replace("'", "''") + "'"
    if _PLAIN_SCALAR_RE.match(text) and not _NUMERIC_SCALAR_RE.match(text):
        return text
    return "'" + text.replace("'", "''") + "'"


def _render_mapping(mapping: dict, indent: int) -> list[str]:
    lines: list[str] = []
    pad = " " * indent
    for key, value in mapping.items():
        if isinstance(value, dict):
            if not value:
                lines.append(f"{pad}{key}: {{}}")
            else:
                lines.append(f"{pad}{key}:")
                lines.extend(_render_mapping(value, indent + 2))
        elif isinstance(value, (list, tuple)):
            if not value:
                lines.append(f"{pad}{key}: []")
            else:
                lines.append(f"{pad}{key}:")
                lines.extend(_render_sequence(list(value), indent + 2))
        else:
            lines.append(f"{pad}{key}: {_render_scalar(value)}")
    return lines


def _render_sequence(values: list, indent: int) -> list[str]:
    lines: list[str] = []
    pad = " " * indent
    for item in values:
        if isinstance(item, dict):
            if not item:
                lines.append(f"{pad}- {{}}")
            else:
                lines.append(f"{pad}-")
                lines.extend(_render_mapping(item, indent + 2))
        elif isinstance(item, (list, tuple)):
            if not item:
                lines.append(f"{pad}- []")
            else:
                lines.append(f"{pad}-")
                lines.extend(_render_sequence(list(item), indent + 2))
        else:
            lines.append(f"{pad}- {_render_scalar(item)}")
    return lines


def _parse_scalar(raw: str) -> object:
    text = raw.strip()
    if text == "":
        return None
    if text == "-":
        return None
    if text[0] in "[{":
        try:
            return json.loads(text)
        except ValueError:
            return text
    if text[0] == '"':
        try:
            return json.loads(text)
        except ValueError:
            return text
    if len(text) >= 2 and text[0] == "'" and text[-1] == "'":
        return text[1:-1].replace("''", "'")
    lowered = text.lower()
    if lowered in ("null", "~"):
        return None
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def _parse_node(lines: list[str], index: int, indent: int) -> tuple[object, int]:
    while index < len(lines) and not lines[index].strip():
        index += 1
    if index >= len(lines):
        return None, index
    match = _SEQ_LINE_RE.match(lines[index])
    if match is not None and _indent_of(lines[index]) == indent:
        return _parse_sequence(lines, index, indent)
    return _parse_mapping(lines, index, indent)


def _parse_mapping(lines: list[str], index: int, indent: int) -> tuple[dict, int]:
    out: dict = {}
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        match = _MAP_LINE_RE.match(line)
        if match is None or _indent_of(line) != indent:
            break
        key = match.group("key")
        raw = match.group("val")
        if raw is None or raw.strip() == "":
            peek = index + 1
            while peek < len(lines) and not lines[peek].strip():
                peek += 1
            if peek < len(lines) and _indent_of(lines[peek]) > indent:
                value, index = _parse_node(lines, peek, _indent_of(lines[peek]))
            else:
                value, index = None, index + 1
        else:
            value, index = _parse_scalar(raw), index + 1
        out[key] = value
    return out, index


def _parse_sequence(lines: list[str], index: int, indent: int) -> tuple[list, int]:
    out: list = []
    while index < len(lines):
        line = lines[index]
        if not line.strip():
            index += 1
            continue
        match = _SEQ_LINE_RE.match(line)
        if match is None or _indent_of(line) != indent:
            break
        raw = match.group("val")
        if raw is None or raw.strip() == "":
            peek = index + 1
            while peek < len(lines) and not lines[peek].strip():
                peek += 1
            if peek < len(lines) and _indent_of(lines[peek]) > indent:
                value, index = _parse_node(lines, peek, _indent_of(lines[peek]))
            else:
                value, index = None, index + 1
        else:
            value, index = _parse_scalar(raw), index + 1
        out.append(value)
    return out, index


def _ticket_path(root: pathlib.Path | str, request_id: str) -> pathlib.Path:
    return tickets_dir(root) / f"{TICKET_PREFIX}{request_id}.md"


def _split_frontmatter(text: str, where: object) -> tuple[list[str], str]:
    content = text[1:] if text.startswith("\ufeff") else text
    lines = content.splitlines()
    start = 0
    while start < len(lines) and not lines[start].strip():
        start += 1
    if start >= len(lines) or lines[start].strip() != "---":
        raise XKeyFormatError(f"{where}: missing opening '---' frontmatter fence")
    close = None
    for i in range(start + 1, len(lines)):
        if lines[i].strip() == "---":
            close = i
            break
    if close is None:
        raise XKeyFormatError(f"{where}: frontmatter never closes with '---'")
    body = "\n".join(lines[close + 1:])
    return lines[start + 1:close], body


def _parse_ticket_text(text: str, where: object) -> dict:
    front, _body = _split_frontmatter(text, where)
    value, _ = _parse_node(front, 0, 0)
    if not isinstance(value, dict):
        raise XKeyFormatError(f"{where}: frontmatter must be a mapping")
    return value


def ticket_write(root: pathlib.Path | str, ticket: dict) -> str:
    """Write ``tickets/xkey-<request_id>.md`` atomically; return its path."""
    if not isinstance(ticket, dict):
        raise XKeyFormatError("ticket must be a dict")
    request_id = ticket.get("request_id")
    if not isinstance(request_id, str) or not _REQUEST_ID_RE.match(request_id):
        raise XKeyFormatError(
            "ticket requires a filename-safe 'request_id' ([A-Za-z0-9][A-Za-z0-9._-]*)"
        )
    frontmatter = {key: value for key, value in ticket.items() if key != "body"}
    body = ticket.get("body")
    if not isinstance(body, str) or not body.strip():
        body = f"# XKey Ticket {request_id}\n"
    lines = ["---", *_render_mapping(frontmatter, 0), "---", "", body.rstrip("\n")]
    path = _ticket_path(root, request_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = pathlib.Path(str(path) + ".tmp")
    tmp.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    os.replace(tmp, path)
    return str(path)


def ticket_load(root: pathlib.Path | str, request_id: str) -> dict | None:
    """Load one ticket; missing → ``None``; malformed → :class:`XKeyFormatError`."""
    if not isinstance(request_id, str) or not request_id:
        return None
    candidates = [_ticket_path(root, request_id), tickets_dir(root) / f"{request_id}.md"]
    for path in candidates:
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            return _parse_ticket_text(text, path)
    return None


def tickets_iter(root: pathlib.Path | str) -> list[dict]:
    """All tickets in the directory, filename order (directory scan = queue)."""
    directory = tickets_dir(root)
    if not directory.is_dir():
        return []
    out: list[dict] = []
    for entry in sorted(directory.iterdir(), key=lambda p: p.name):
        if not entry.is_file() or entry.suffix != ".md":
            continue
        if entry.name.endswith(".tmp"):
            continue
        out.append(_parse_ticket_text(entry.read_text(encoding="utf-8"), entry))
    return out


# ── Frozen-block location (D-006, AST only, fail-closed) ──────────────────────

_FUNC_TYPES = (ast.FunctionDef, ast.AsyncFunctionDef)


def _module_level_assignments(tree: ast.Module) -> tuple[dict, set]:
    """(clean direct defs name→stmt, disqualified names).

    Clean = a single ``Name`` target of a direct ``Assign`` (or a valued
    ``AnnAssign``) at ``Module.body`` top level. Conditional assignments,
    augmented assignments, tuple targets, re-assignments and imports are all
    disqualified (dynamic / ambiguous → degrade, D-006).
    """
    defs: dict[str, ast.stmt] = {}
    disqualified: set[str] = set()

    def note(name: str, stmt: ast.stmt) -> None:
        if name in defs:
            disqualified.add(name)
        else:
            defs[name] = stmt

    for stmt in tree.body:
        if isinstance(stmt, ast.Assign):
            if len(stmt.targets) != 1 or not isinstance(stmt.targets[0], ast.Name):
                for target in ast.walk(stmt):
                    if isinstance(target, ast.Name) and isinstance(target.ctx, ast.Store):
                        disqualified.add(target.id)
                continue
            note(stmt.targets[0].id, stmt)
        elif isinstance(stmt, ast.AnnAssign):
            if isinstance(stmt.target, ast.Name) and stmt.value is not None:
                note(stmt.target.id, stmt)
            elif isinstance(stmt.target, ast.Name):
                disqualified.add(stmt.target.id)
        elif isinstance(stmt, ast.AugAssign):
            if isinstance(stmt.target, ast.Name):
                disqualified.add(stmt.target.id)
        elif isinstance(stmt, (ast.Import, ast.ImportFrom)):
            for alias in stmt.names:
                disqualified.add((alias.asname or alias.name).split(".")[0])
        else:
            # Any module-level control flow / def / class that binds a name is
            # not a clean direct constant definition (conditional assignment
            # and friends must degrade, D-006).
            for inner in ast.walk(stmt):
                if isinstance(inner, ast.Name) and isinstance(inner.ctx, ast.Store):
                    disqualified.add(inner.id)
    return defs, disqualified


def _local_bindings(fn: ast.AST) -> set[str]:
    bound: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)):
            bound.add(node.id)
        elif isinstance(node, ast.arg):
            bound.add(node.arg)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                bound.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.Global, ast.Nonlocal)):
            bound.update(node.names)
    return bound


def locate_frozen_block(root: pathlib.Path | str, file: str, test_id: str) -> dict | None:
    """Locate the frozen module-level constant a test references (D-006).

    ``test_id → FunctionDef → unique module-level reference → Assign range``.
    Any ambiguity (function hit ≠ 1, reference hit ≠ 1, dynamic ``getattr``,
    cross-file constant, conditional/augmented assignment, local shadowing,
    non-literal value) returns ``None`` ("only propose", R-2).

    Returns ``{"file","symbol","line_range","old_block_sha256",
    "sha256_eol_normalized"}`` where ``line_range`` is inclusive
    ``[start, end]`` and the shas cover those exact bytes (D-012).
    """
    if not isinstance(file, str) or not file or not isinstance(test_id, str) or not test_id:
        return None
    path = pathlib.Path(root) / file
    if not path.is_file():
        return None
    try:
        data = path.read_bytes()
        text = data.decode("utf-8")
        tree = ast.parse(text)
    except (OSError, UnicodeDecodeError, SyntaxError, ValueError):
        return None

    functions = [
        node for node in ast.walk(tree)
        if isinstance(node, _FUNC_TYPES) and node.name == test_id
    ]
    if len(functions) != 1:
        return None
    function = functions[0]

    defs, disqualified = _module_level_assignments(tree)
    bound = _local_bindings(function)
    referenced = {
        node.id for node in ast.walk(function)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
    }
    candidates = sorted(
        name for name in referenced
        if name in defs and name not in disqualified and name not in bound
    )
    if len(candidates) != 1:
        return None
    symbol = candidates[0]
    assign_stmt = defs[symbol]
    value_node = getattr(assign_stmt, "value", None)
    try:
        ast.literal_eval(value_node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None

    start = getattr(assign_stmt, "lineno", None)
    end = getattr(assign_stmt, "end_lineno", None)
    if not isinstance(start, int) or not isinstance(end, int) or start < 1 or end < start:
        return None
    byte_lines = _split_bytes_lines(data)
    if end > len(byte_lines):
        return None
    block = b"".join(byte_lines[start - 1:end])
    return {
        "file": file,
        "symbol": symbol,
        "line_range": [start, end],
        "old_block_sha256": _sha256(block),
        "sha256_eol_normalized": _sha256_eol_normalized_bytes(block),
    }


# ── Boundary check (D-005 / D-012) ────────────────────────────────────────────


def _pick(mapping: object, *keys: str) -> object:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def _line_set(value: object) -> set[int] | None:
    """Coerce ``[s, e]`` / ``[n, ...]`` / ``"s-e"`` / ``n`` into a line set."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return {value}
    if isinstance(value, str):
        match = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", value)
        if match:
            return _expand(int(match.group(1)), int(match.group(2)))
        if re.fullmatch(r"\s*\d+\s*", value):
            return {int(value)}
        return None
    if isinstance(value, (list, tuple)):
        if len(value) == 2 and all(isinstance(item, int) and not isinstance(item, bool) for item in value):
            return _expand(value[0], value[1])
        if value and all(isinstance(item, int) and not isinstance(item, bool) for item in value):
            return set(value)
        if value and all(isinstance(item, (list, tuple)) for item in value):
            out: set[int] = set()
            for item in value:
                part = _line_set(item)
                if part is None:
                    return None
                out |= part
            return out
    return None


def _expand(start: int, end: int) -> set[int] | None:
    if start < 1 or end < start:
        return None
    return set(range(start, end + 1))


def _proposal_line_set(proposal: dict) -> set[int] | None:
    for container in (
        proposal,
        proposal.get("proposed_boundary"),
        proposal.get("frozen_block"),
    ):
        value = _pick(container, "lines", "changed_lines", "line_range", "changed_line_range")
        if value is not None:
            return _line_set(value)
    return None


def _ticket_line_set(ticket: dict) -> set[int] | None:
    for container in (
        ticket.get("frozen_block"),
        ticket.get("proposed_boundary"),
        ticket,
    ):
        value = _pick(
            container, "line_range", "lines", "declared_lines", "allowed_lines"
        )
        if value is not None:
            return _line_set(value)
    return None


def _ticket_file(ticket: dict) -> str | None:
    for container in (ticket.get("frozen_block"), ticket.get("proposed_boundary"), ticket):
        value = _pick(container, "file", "path", "target_file")
        if isinstance(value, str) and value.strip():
            return _normalize_rel(value)
    return None


def _untouchable_entries(ticket: dict) -> list[str]:
    raw = _pick(ticket, "untouchable", "untouchable_paths", "forbidden")
    if isinstance(raw, str):
        return [raw]
    if isinstance(raw, (list, tuple)):
        return [str(entry) for entry in raw if isinstance(entry, str) and entry.strip()]
    return []


def _untouchable_lines(ticket: dict) -> set[int]:
    """Line numbers in the ticket's ``untouchable`` list (single-file ticket)."""
    raw = _pick(ticket, "untouchable", "untouchable_lines", "forbidden")
    lines: set[int] = set()
    if isinstance(raw, (list, tuple)):
        for entry in raw:
            if isinstance(entry, int) and not isinstance(entry, bool):
                lines.add(entry)
    return lines


def _matches_path(target: str, pattern: str) -> bool:
    if not pattern:
        return False
    if target == pattern:
        return True
    if pattern.endswith("/") and target.startswith(pattern):
        return True
    if pattern.endswith("/**") and target.startswith(pattern[:-3].rstrip("/") + "/"):
        return True
    return fnmatch.fnmatch(target, pattern)


def check_boundary(proposal: dict, ticket: dict) -> str:
    """"ok" iff the proposal stays inside the ticket's declared boundary.

    Checks: proposal file == declared file (no second file), the proposal line
    set is a subset of the declared line set, and no untouchable path/line is
    touched. Any missing/ambiguous input is a ``"violation"`` (fail-closed).
    Pure: never writes, never calls :func:`apply_block_replace`.
    """
    if not isinstance(proposal, dict) or not isinstance(ticket, dict):
        return "violation"

    allowed_file = _ticket_file(ticket)
    proposal_file = _pick(proposal, "file", "path", "target_file")
    if not allowed_file or not isinstance(proposal_file, str) or not proposal_file.strip():
        return "violation"
    proposal_file = _normalize_rel(proposal_file)
    if proposal_file != allowed_file:
        return "violation"

    extra_files = _pick(proposal, "files", "extra_files", "touched_files", "other_files")
    if isinstance(extra_files, (list, tuple)):
        for entry in extra_files:
            if _normalize_rel(entry) != allowed_file:
                return "violation"

    proposal_lines = _proposal_line_set(proposal)
    ticket_lines = _ticket_line_set(ticket)
    if not proposal_lines or not ticket_lines:
        return "violation"
    if not proposal_lines.issubset(ticket_lines):
        return "violation"

    blocked_lines = _untouchable_lines(ticket)
    if blocked_lines and proposal_lines & blocked_lines:
        return "violation"

    for entry in _untouchable_entries(ticket):
        parts = entry.strip().strip("`'\"* ")
        line_spec = re.search(r":(\d+)(?:-(\d+))?$", parts)
        pattern = _normalize_rel(parts)
        if not _matches_path(proposal_file, pattern):
            continue
        if line_spec is None:
            return "violation"
        start = int(line_spec.group(1))
        end = int(line_spec.group(2)) if line_spec.group(2) else start
        blocked = _expand(start, end)
        if blocked and proposal_lines & blocked:
            return "violation"

    proposal_sha = _pick(proposal, "old_block_sha256", "old_sha256")
    ticket_sha = _pick(ticket.get("frozen_block"), "old_block_sha256", "old_sha256")
    if ticket_sha is None:
        ticket_sha = _pick(ticket, "old_block_sha256", "old_sha256")
    if isinstance(proposal_sha, str) and isinstance(ticket_sha, str) and proposal_sha != ticket_sha:
        return "violation"

    return "ok"


# ── Apply (D-005 / D-012) ─────────────────────────────────────────────────────


def _apply_targets(ticket: dict) -> tuple[str, list[int], str]:
    frozen = ticket.get("frozen_block")
    file_value = _pick(frozen, "file", "path") or _pick(ticket, "file", "path")
    range_value = _pick(frozen, "line_range", "lines") or _pick(ticket, "line_range", "lines")
    sha_value = _pick(frozen, "old_block_sha256", "old_sha256") or _pick(
        ticket, "old_block_sha256", "old_sha256"
    )
    if not isinstance(file_value, str) or not file_value.strip():
        raise XKeyFormatError("ticket is missing the frozen block 'file'")
    line_range = _line_set(range_value)
    if line_range is None:
        raise XKeyFormatError("ticket is missing a parseable frozen block 'line_range'")
    if not isinstance(sha_value, str) or not sha_value:
        raise XKeyFormatError("ticket is missing 'old_block_sha256'")
    ordered = sorted(line_range)
    if ordered != list(range(ordered[0], ordered[-1] + 1)):
        raise XKeyFormatError("frozen block 'line_range' must be contiguous")
    return _normalize_rel(file_value), [ordered[0], ordered[-1]], sha_value


def apply_block_replace(
    root: pathlib.Path | str,
    ticket: dict,
    new_bytes: bytes,
    *,
    authorization: "RepairVerdict | None" = None,
) -> str:
    """Splice ``new_bytes`` over the ticket's frozen ``line_range`` (D-005).

    Recomputes ``sha256`` over the **current** bytes of that range and compares
    it with the ticket's ``old_block_sha256``; a mismatch raises
    :class:`XKeyShaDrift` and nothing is written. Otherwise the whole file is
    rewritten atomically (``tmp`` + ``os.replace``) with every other byte
    untouched. Returns ``sha256`` of the **new block bytes** (D-012), which is
    the ``new`` value of the AC-006 ``old → new`` pair.

    When ``authorization`` is supplied (H07), the write additionally requires an
    executable repair verdict that names this exact file. The verdict itself
    never writes or dispatches; this explicit call is the only write.
    """
    if not isinstance(ticket, dict):
        raise XKeyFormatError("ticket must be a dict")
    status = ticket.get("status")
    if isinstance(status, str) and status in _UNAUTHORIZED_APPLY_STATUSES:
        raise XKeyAuthorizationError(
            f"ticket status {status!r} does not authorise a write"
        )
    file_value, line_range, expected_sha = _apply_targets(ticket)
    if authorization is not None:
        if getattr(authorization, "_issued", None) is not _REPAIR_ISSUED:
            raise XKeyAuthorizationError(
                "repair authorization was not issued by the real-supply assessment"
            )
        if not getattr(authorization, "executable", False):
            raise XKeyAuthorizationError("repair authorization is not executable")
        if not getattr(authorization, "binding_verified", False):
            raise XKeyAuthorizationError(
                "repair authorization is not bound to a verified real source"
            )
        decision_ref = getattr(authorization, "decision_ref", None)
        if not isinstance(decision_ref, str) or not decision_ref:
            raise XKeyAuthorizationError("repair authorization carries no decision binding")
        approved = tuple(getattr(authorization, "approved_files", ()) or ())
        if _normalize_rel(file_value) not in approved:
            raise XKeyAuthorizationError(
                f"repair authorization does not cover {file_value}"
            )
        approved_key = getattr(authorization, "target_key", None)
        ticket_key = ticket.get("owner_key") or ticket.get("target_key")
        if approved_key is not None and ticket_key is not None and approved_key != ticket_key:
            raise XKeyAuthorizationError(
                "repair authorization names a different target key than the ticket"
            )

    if check_boundary(
        {"file": file_value, "line_range": line_range, "old_block_sha256": expected_sha},
        ticket,
    ) != "ok":
        raise XKeyBoundaryViolation(
            f"ticket boundary violation in {file_value}:{line_range[0]}-{line_range[1]} "
            "(no write)"
        )

    if isinstance(new_bytes, str):
        payload = new_bytes.encode("utf-8")
    elif isinstance(new_bytes, (bytes, bytearray)):
        payload = bytes(new_bytes)
    else:
        raise XKeyFormatError("new_bytes must be bytes (or a str)")

    path = pathlib.Path(root) / file_value
    if not path.is_file():
        raise XKeyFormatError(f"target file not found: {path}")
    data = path.read_bytes()
    lines = _split_bytes_lines(data)
    start, end = line_range
    if start < 1 or end > len(lines):
        raise XKeyFormatError(
            f"frozen line_range {line_range} is outside {file_value} ({len(lines)} lines)"
        )
    current_block = b"".join(lines[start - 1:end])
    current_sha = _sha256(current_block)
    if current_sha != expected_sha:
        raise XKeyShaDrift(
            f"frozen block sha256 drift in {file_value}:{start}-{end}: "
            f"ticket={expected_sha} disk={current_sha} (no write)"
        )

    if payload:
        last = lines[end - 1]
        if last.endswith(b"\r\n"):
            ending = b"\r\n"
        elif last.endswith(b"\r"):
            ending = b"\r"
        elif last.endswith(b"\n"):
            ending = b"\n"
        else:
            ending = b""
        if ending and not payload.endswith((b"\n", b"\r")):
            payload = payload + ending

    new_data = b"".join(lines[:start - 1]) + payload + b"".join(lines[end:])
    tmp = pathlib.Path(str(path) + ".tmp")
    tmp.write_bytes(new_data)
    os.replace(tmp, path)
    return _sha256(payload)


# ── Verification execution (D-007) ────────────────────────────────────────────

_PYTEST_COUNT_RE = re.compile(r"(\d+)\s+(passed|failed|error|errors|skipped|xfailed|xpassed|deselected)\b")


def _parse_pytest_red_counts(text: str) -> tuple[dict, str]:
    summary_lines = [
        line.strip() for line in text.splitlines()
        if re.search(r"\d+\s+(passed|failed|error|errors)\b", line)
    ]
    summary = summary_lines[-1] if summary_lines else ""
    counts = {"passed": 0, "failed": 0, "errors": 0}
    for match in _PYTEST_COUNT_RE.finditer(summary):
        number = int(match.group(1))
        kind = match.group(2)
        if kind == "passed":
            counts["passed"] = number
        elif kind == "failed":
            counts["failed"] = number
        elif kind in ("error", "errors"):
            counts["errors"] = number
    counts["total"] = counts["failed"] + counts["errors"]
    return counts, summary


def _append_run_evidence(path: pathlib.Path, payload: bytes) -> str:
    """Append a self-anchored record (header carries the payload sha256)."""
    digest = _sha256(payload)
    header = f"# xkey-run {_iso_now()} bytes={len(payload)} sha256={digest}\n".encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(header)
        handle.write(payload)
        if not payload.endswith(b"\n"):
            handle.write(b"\n")
    return digest


def run_verification(
    cmd: list[str],
    cwd: str,
    run_dir: str,
    timeout: int,
) -> dict:
    """Run ``cmd`` (``shell=False``, list argv) and capture raw evidence (D-007).

    stdout/stderr land in ``run_dir`` as append-only, self-anchored files; a
    timeout keeps the partial output (rc 124). Red counts come from the last
    pytest summary line, never from ``mw_common.scan_build_error_lines`` (UE
    only). Returns ``{"stdout_path","sha256","red_counts"}`` where ``sha256``
    is the stdout payload digest and ``red_counts`` also carries the run facts
    (``passed/failed/errors/total/returncode/timed_out/summary``).
    """
    if not cmd:
        raise XKeyFormatError("verification command must be a non-empty list")
    argv = [str(part) for part in cmd]
    out_dir = pathlib.Path(run_dir)
    try:
        timeout_value = float(timeout)
    except (TypeError, ValueError):
        raise XKeyFormatError(f"timeout must be a number, got {timeout!r}") from None

    returncode = 124
    timed_out = True
    stdout = b""
    stderr = b""
    try:
        proc = subprocess.run(
            argv,
            shell=False,
            cwd=str(cwd),
            capture_output=True,
            timeout=timeout_value,
        )
        returncode = proc.returncode
        timed_out = False
        stdout = proc.stdout or b""
        stderr = proc.stderr or b""
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout or b""
        stderr = exc.stderr or b""
        timeout_note = f"\n[TIMEOUT] after {timeout_value}s\n".encode("utf-8")
        stdout = stdout + timeout_note
    except FileNotFoundError as exc:
        returncode = 127
        timed_out = False
        stderr = str(exc).encode("utf-8", "replace")

    stdout_path = out_dir / "stdout.txt"
    digest = _append_run_evidence(stdout_path, stdout)
    _append_run_evidence(out_dir / "stderr.txt", stderr)

    red_counts, summary = _parse_pytest_red_counts(stdout.decode("utf-8", "replace"))
    red_counts["returncode"] = returncode
    red_counts["timed_out"] = timed_out
    red_counts["summary"] = summary
    return {
        "stdout_path": str(stdout_path),
        "sha256": digest,
        "red_counts": red_counts,
    }


# ── Evidence bundle (AC-006) ──────────────────────────────────────────────────

_BUNDLE_ITEM_KEYS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("old_sha256", ("old_sha256", "old_block_sha256")),
    ("new_sha256", ("new_sha256", "new_block_sha256")),
    ("reason", ("reason",)),
    ("relaxed_assertion", ("relaxed_assertion", "assertion_relaxed")),
    (
        "verify_cmd",
        ("verify_cmd", "targeted_cmd", "rerun_cmd", "repro_command", "command"),
    ),
    ("stdout_path", ("stdout_path", "raw_stdout", "stdout")),
    ("red_before", ("red_before", "full_red_before", "reds_before")),
    ("red_after", ("red_after", "full_red_after", "reds_after")),
)


def _bundle_lookup(bundle: dict, keys: tuple[str, ...]) -> tuple[bool, object]:
    for key in keys:
        if key in bundle and bundle[key] not in (None, ""):
            return True, bundle[key]
    return False, None


def _stdout_resolvable(root: pathlib.Path | str, stdout_path: str) -> bool:
    candidate = pathlib.Path(stdout_path)
    if not candidate.is_absolute():
        candidate = pathlib.Path(root) / candidate
    return candidate.is_file()


def evidence_bundle_write(root: pathlib.Path | str, request_id: str, bundle: dict) -> str:
    """Write the AC-006 evidence bundle; missing items are never silent.

    Five logical items: ``old_sha256``/``new_sha256``, ``reason``,
    ``relaxed_assertion`` (bool), the targeted rerun command + raw stdout
    (file must exist), and the full red count before → after. The written
    ``bundle.json`` carries ``closed`` (all five complete) and ``missing``
    (item names) so the conductor can judge ``closed=False``.

    Returns the path of the written ``bundle.json`` document.
    """
    if not isinstance(request_id, str) or not _REQUEST_ID_RE.match(request_id):
        raise XKeyFormatError("evidence bundle requires a filename-safe request_id")
    if not isinstance(bundle, dict):
        raise XKeyFormatError("bundle must be a dict")

    values: dict[str, object] = {}
    missing: list[str] = []
    for slot, keys in _BUNDLE_ITEM_KEYS:
        present, value = _bundle_lookup(bundle, keys)
        if present:
            values[slot] = value
        else:
            missing.append(slot)

    if not isinstance(values.get("relaxed_assertion"), bool):
        if "relaxed_assertion" not in missing:
            missing.append("relaxed_assertion")
        values.pop("relaxed_assertion", None)

    stdout_ok = False
    stdout_path = values.get("stdout_path")
    if isinstance(stdout_path, str) and stdout_path:
        stdout_ok = _stdout_resolvable(root, stdout_path)
    if isinstance(stdout_path, str) and stdout_path and not stdout_ok:
        missing.append("stdout_missing")

    missing = list(dict.fromkeys(missing))
    closed = (
        not missing
        and all(
            slot in values
            for slot in ("old_sha256", "new_sha256", "reason", "verify_cmd", "stdout_path",
                         "red_before", "red_after")
        )
        and isinstance(values.get("relaxed_assertion"), bool)
        and stdout_ok
    )

    directory = evidence_dir(root, request_id)
    directory.mkdir(parents=True, exist_ok=True)
    document = {
        "request_id": request_id,
        "closed": closed,
        "missing": missing,
        "stdout_exists": stdout_ok,
        "items": values,
        "bundle": bundle,
        "written_at": _iso_now(),
    }
    payload = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    bundle_path = directory / "bundle.json"
    closure_path = directory / "closure.json"
    for target in (bundle_path, closure_path):
        tmp = pathlib.Path(str(target) + ".tmp")
        tmp.write_text(payload, encoding="utf-8", newline="\n")
        os.replace(tmp, target)
    return str(bundle_path)


# ── H07: restricted cross-key repair (AC-026 / AC-027 / AC-052) ───────────────
#
# A cross-key repair is requested by the PM but executed by a worker. The note
# has to name necessity, target key/file/action, impact, authorization,
# coordination and verification; the approval must cover exactly that surface.
# Project write-face containment is never a permission. Execution additionally
# requires a role/actor match and a real exclusive claim.

CLAIMS_DIR_NAME = "claims"

_REPAIR_ISSUED = object()

_REPAIR_REQUIRED_FIELDS: tuple[str, ...] = (
    "request_id",
    "target_key",
    "action",
    "necessity",
    "impact",
    "authorization",
    "coordination",
    "verification",
)


@dataclasses.dataclass(frozen=True)
class RepairRequest:
    """The PM-prepared restricted cross-key repair note (intent only)."""

    request_id: str
    target_key: str
    files: tuple[str, ...]
    action: str
    necessity: str
    impact: str
    authorization: str
    coordination: str
    verification: str


@dataclasses.dataclass(frozen=True)
class RepairApproval:
    """The approving answer: only the named key/files/action.

    ``authority_ref`` is resolved against the real T07 authority source; the
    ``authority_source`` text is retained only for display and is never a
    grant.
    """

    approval_ref: str
    target_key: str
    files: tuple[str, ...]
    action: str
    authority_source: str
    authority_ref: str = ""


@dataclasses.dataclass(frozen=True)
class RepairVerdict:
    """Whether the repair may execute, and on which restricted files.

    ``dispatched`` and ``written`` are always ``False`` here: a selection is
    not a dispatch, and an authorization is not a modification.
    ``binding_verified`` is only set by a successful real-supply verification;
    :func:`apply_block_replace` refuses an authorization without it.
    """

    status: str
    executable: bool
    reasons: tuple[str, ...]
    approved_files: tuple[str, ...]
    dispatched: bool = False
    written: bool = False
    binding_verified: bool = False
    authority_ref: str | None = None
    target_key: str | None = None
    decision_ref: str | None = None
    _issued: object | None = dataclasses.field(default=None, repr=False, compare=False)


def claims_dir(root: pathlib.Path | str) -> pathlib.Path:
    """Per-file claim markers for the xkey repair surface."""

    return _xkey_dir(root) / CLAIMS_DIR_NAME


def _surface_problem(value: object) -> tuple[str | None, str | None]:
    """Validate one restricted repair path (fail-closed; no wildcards)."""

    if not isinstance(value, str) or not value.strip():
        return "empty_write_face", None
    text = value.strip().replace("\\", "/")
    if text.startswith("/") or re.match(r"^[A-Za-z]:", text):
        return "absolute_path", None
    if "*" in text or "?" in text or "[" in text:
        return "open_ended_repair", None
    if text.endswith("/"):
        return "open_ended_repair", None
    parts = [part for part in text.split("/") if part not in ("", ".")]
    if ".." in parts:
        return "parent_traversal", None
    if not parts:
        return "empty_write_face", None
    return None, "/".join(parts)


def _repair_files(values: object) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not isinstance(values, (list, tuple)) or not values:
        return ("empty_write_face",), ()
    problems: list[str] = []
    files: list[str] = []
    for value in values:
        problem, normalised = _surface_problem(value)
        if problem is not None:
            problems.append(problem)
        elif normalised is not None:
            files.append(normalised)
    return tuple(dict.fromkeys(problems)), tuple(sorted(set(files)))


def _repair_note_problems(request: "RepairRequest", note: str | None) -> tuple[str, ...]:
    """The PM note must name necessity, target, action, impact and checks."""

    if not isinstance(note, str) or not note.strip():
        return ("missing_pm_note",)
    required = [
        request.target_key,
        request.action,
        request.necessity,
        request.impact,
        request.coordination,
        request.verification,
        *request.files,
    ]
    if any(value not in note for value in required):
        return ("incomplete_pm_note",)
    return ()


def _active_claim_for(
    root: pathlib.Path | str,
    *,
    actor: str,
    task_key: str,
    files: tuple[str, ...],
) -> tuple[str, ...]:
    """Every requested file must carry this actor/task's real claim marker."""

    reasons: list[str] = []
    markers = claims_dir(root)
    for file_value in files:
        marker = _claim_marker(root, file_value)
        if not marker.is_file():
            reasons.append("missing_claim")
            continue
        try:
            existing = json.loads(marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            reasons.append("unreadable_claim")
            continue
        if (
            not isinstance(existing, dict)
            or existing.get("owner") != actor
            or existing.get("task_key") != task_key
            or existing.get("exclusive") is not True
            or existing.get("canonical")
            != _canonical_claim_path(root, file_value)[0]
        ):
            reasons.append("foreign_claim")
    return tuple(dict.fromkeys(reasons))


def assess_repair_request(
    request: RepairRequest,
    approval: RepairApproval | None,
    claims: list,
    claim_request: object,
    *,
    actor: str,
    role: str,
    supply: _guard.TrustedSupply | None = None,
    pm_note: str | None = None,
) -> RepairVerdict:
    """Judge one restricted cross-key repair against real artefacts.

    The request text is intent only. Execution additionally requires the real
    T17 gate, T10 request/basis/note, live PM claim, T07 authority, cumulative
    hard budget and the actor's own on-disk claim markers.
    """

    reasons: list[str] = []
    missing = [
        field
        for field in _REPAIR_REQUIRED_FIELDS
        if not isinstance(getattr(request, field), str)
        or not getattr(request, field).strip()
    ]
    if not isinstance(request.files, (list, tuple)) or not request.files:
        missing.append("files")
    if missing:
        reasons.append("incomplete_repair_note")

    if role != "worker":
        reasons.append("role_not_allowed")
    claim_actor = getattr(claim_request, "actor", None)
    claim_task = getattr(claim_request, "task_key", None)
    if (
        not isinstance(actor, str)
        or not actor.strip()
        or claim_actor != actor
        or not isinstance(claim_task, str)
        or not claim_task.strip()
    ):
        reasons.append("actor_mismatch")

    target_key = request.target_key
    if (
        not isinstance(target_key, str)
        or not _KEY_NAME_RE.match(target_key)
        or target_key.lower() in _OWNER_ROLE_TOKENS
    ):
        reasons.append("invalid_target_key")

    file_problems, requested_files = _repair_files(request.files)
    reasons.extend(file_problems)
    reasons.extend(_repair_note_problems(request, pm_note))

    approved_files: tuple[str, ...] = ()
    if approval is None:
        reasons.append("missing_approval")
    else:
        approved_problems, approved_files = _repair_files(approval.files)
        reasons.extend(approved_problems)
        if approval.target_key != request.target_key:
            reasons.append("reused_unrelated_repair_approval")
        if approval.action != request.action:
            reasons.append("approval_action_mismatch")
        if approval.authority_ref != request.authorization:
            reasons.append("approval_authority_mismatch")
        requested = set(requested_files)
        approved = set(approved_files)
        if approved - requested:
            reasons.append("approval_scope_expansion")
        if requested - approved:
            reasons.append("approval_scope_too_narrow")

    supply_reasons: tuple[str, ...] = ()
    if not file_problems and requested_files and claim_actor == actor and claim_task:
        claim_verdict = _validity.assess_claim(list(claims), claim_request)
        if claim_verdict.status != "clear":
            reasons.append("claim_conflict")
        supply_reasons, _gate = _guard.verify_supply(
            supply,
            gate_kind="xkey-authorize",
            expected_gate_key=request.target_key,
            required_scope=(
                f"xkey-repair:{request.target_key}",
                f"xkey-action:{request.action}",
                *(f"xkey-file:{file}" for file in requested_files),
            ),
            authority_ref=request.authorization,
            require_files=requested_files,
            note=pm_note,
            target_key=request.target_key,
        )
        if supply is not None:
            supply_reasons = tuple(supply_reasons) + _active_claim_for(
                supply.project_root,
                actor=actor,
                task_key=claim_task,
                files=requested_files,
            )
    else:
        supply_reasons, _gate = _guard.verify_supply(
            supply,
            gate_kind="xkey-authorize",
            expected_gate_key=request.target_key,
            required_scope=(),
            authority_ref=request.authorization,
            note=pm_note,
            target_key=request.target_key,
        )
    reasons.extend(supply_reasons)

    unique = tuple(dict.fromkeys(reasons))
    executable = not unique
    return RepairVerdict(
        status="authorized" if executable else "blocked",
        executable=executable,
        reasons=unique,
        approved_files=requested_files if executable else approved_files,
        dispatched=False,
        written=False,
        binding_verified=executable and supply is not None,
        authority_ref=request.authorization if executable else None,
        target_key=request.target_key if executable else None,
        decision_ref=(supply.decision_ref if executable and supply is not None else None),
        _issued=_REPAIR_ISSUED if executable else None,
    )


#: This process's own claim generation: only a matching token is a re-entry.
_PROCESS_TOKEN = uuid.uuid4().hex
_HOST = socket.gethostname()


def _canonical_claim_path(
    root: pathlib.Path | str, file_value: str
) -> tuple[str, str]:
    """One physical identity for a claimed path (case/alias/reparse aware)."""

    rel = _normalize_rel(file_value)
    candidate = pathlib.Path(root) / rel
    try:
        resolved = candidate.resolve()
    except (OSError, RuntimeError):
        resolved = pathlib.Path(os.path.abspath(str(candidate)))
    return os.path.normcase(str(resolved)), rel


def _claim_marker(root: pathlib.Path | str, file_value: str) -> pathlib.Path:
    canonical, _rel = _canonical_claim_path(root, file_value)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]
    return claims_dir(root) / f"{digest}.json"


def _unlink_claim_marker(marker: pathlib.Path) -> None:
    """Unlink a marker even while a concurrent reader still has it open.

    Windows refuses to remove an open file (WinError 32). Concurrent claim
    attempts read markers to decide conflicts, so a losing attempt's cleanup
    can race that short-lived read. Retry only the transient sharing error;
    every other error stays visible (a failed cleanup must not be silent).
    """

    for attempt in range(40):
        try:
            marker.unlink()
            return
        except FileNotFoundError:
            return
        except PermissionError:
            if attempt == 39:
                raise
            time.sleep(0.005)


def _claim_identity(
    owner: str, task_key: str, files: tuple[str, ...], root: pathlib.Path | str
) -> str:
    canonical = ",".join(
        sorted(_canonical_claim_path(root, file_value)[0] for file_value in files)
    )
    return _sha256(
        (owner + "\x1f" + task_key + "\x1f" + canonical + "\x1f" + _PROCESS_TOKEN).encode(
            "utf-8"
        )
    )[:16]


def _read_marker(marker: pathlib.Path) -> dict | None:
    """A usable marker, or ``None`` for an empty/corrupt/foreign-shaped file."""

    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    if not isinstance(data.get("owner"), str) or not data.get("owner"):
        return None
    if not isinstance(data.get("task_key"), str) or not data.get("task_key"):
        return None
    if data.get("exclusive") is not True:
        return None
    return data


def _marker_liveness(existing: dict) -> str:
    if existing.get("host") != _HOST:
        return "unknown"
    pid = existing.get("pid")
    if type(pid) is not int or pid <= 0:
        return "unknown"
    return mw_common.process_alive_state(pid)


def claim_acquire(
    root: pathlib.Path | str,
    *,
    owner: str,
    task_key: str,
    files: list[str] | tuple[str, ...],
) -> dict:
    """Acquire per-file claims with ``O_CREAT|O_EXCL`` markers (real lock).

    Files are attempted in canonical sorted order so two windows never
    deadlock. Only the *same process generation* (same owner, task, file set
    and process token) is re-entrant; the same owner/task from another process
    is a second writer and therefore a conflict. Empty/corrupt markers are
    conflicts (never overwritten), and a dead owner is reported stale without
    takeover. Any conflict releases only what this call created.
    """

    if not isinstance(owner, str) or not owner.strip():
        raise XKeyFormatError("claim requires a non-empty owner")
    if not isinstance(task_key, str) or not task_key.strip():
        raise XKeyFormatError("claim requires a non-empty task_key")
    problems, normalised = _repair_files(files)
    if problems or not normalised:
        raise XKeyFormatError(
            "claim requires a valid restricted write face: " + ", ".join(problems or ("empty",))
        )

    ordered = sorted(
        normalised, key=lambda value: _canonical_claim_path(root, value)[0]
    )
    claim_id = _claim_identity(owner, task_key, tuple(ordered), root)
    acquired: list[str] = []
    reentrant: list[str] = []
    conflicts: list[str] = []
    stale: list[str] = []
    unreadable: list[str] = []
    conflicting_owners: set[str] = set()
    claims_dir(root).mkdir(parents=True, exist_ok=True)
    try:
        for file_value in ordered:
            marker = _claim_marker(root, file_value)
            payload = {
                "schema": 2,
                "file": file_value,
                "canonical": _canonical_claim_path(root, file_value)[0],
                "owner": owner,
                "task_key": task_key,
                "claim_id": claim_id,
                "pid": os.getpid(),
                "host": _HOST,
                "process_token": _PROCESS_TOKEN,
                "exclusive": True,
                "created_at": _iso_now(),
            }
            # Publish the complete marker atomically: a concurrent reader must
            # never observe the in-progress empty file between O_EXCL create and
            # write (that would be indistinguishable from a crashed writer).
            staging = marker.with_name(f"{marker.name}.{uuid.uuid4().hex}.tmp")
            staging.write_text(
                json.dumps(payload, ensure_ascii=False) + "\n",
                encoding="utf-8",
                newline="\n",
            )
            try:
                os.link(staging, marker)
            except FileExistsError:
                _unlink_claim_marker(staging)
                existing = _read_marker(marker)
                if existing is None:
                    conflicts.append(file_value)
                    unreadable.append(file_value)
                    conflicting_owners.add("unknown")
                    continue
                if (
                    existing.get("process_token") == _PROCESS_TOKEN
                    and existing.get("claim_id") == claim_id
                ):
                    reentrant.append(file_value)
                    continue
                conflicts.append(file_value)
                conflicting_owners.add(str(existing.get("owner", "unknown")))
                if (
                    existing.get("owner") == owner
                    and existing.get("task_key") == task_key
                    and _marker_liveness(existing) == "dead"
                ):
                    stale.append(file_value)
                continue
            _unlink_claim_marker(staging)
            acquired.append(file_value)
    except BaseException:
        for file_value in acquired:
            try:
                _unlink_claim_marker(_claim_marker(root, file_value))
            except FileNotFoundError:
                pass
        raise

    if conflicts:
        for file_value in acquired:
            try:
                _unlink_claim_marker(_claim_marker(root, file_value))
            except FileNotFoundError:
                pass
        return {
            "status": "conflict",
            "claim_id": None,
            "owner": owner,
            "task_key": task_key,
            "owned": (),
            "reentrant": tuple(sorted(reentrant)),
            "conflicts": tuple(sorted(conflicts)),
            "conflicting_owners": tuple(sorted(conflicting_owners)),
            "stale": tuple(sorted(stale)),
            "unreadable": tuple(sorted(unreadable)),
            "takeover": False,
        }

    return {
        "status": "acquired",
        "claim_id": claim_id,
        "owner": owner,
        "task_key": task_key,
        "owned": tuple(sorted(acquired)),
        "reentrant": tuple(sorted(reentrant)),
        "conflicts": (),
        "conflicting_owners": (),
        "stale": (),
        "unreadable": (),
        "takeover": False,
    }


def claim_release(root: pathlib.Path | str, claim: dict) -> None:
    """Release only this exact claim generation (idempotent for missing files)."""

    if not isinstance(claim, dict):
        raise XKeyFormatError("claim must be a dict")
    owner = claim.get("owner")
    task_key = claim.get("task_key")
    claim_id = claim.get("claim_id")
    if not isinstance(claim_id, str) or not claim_id:
        raise XKeyFormatError("claim release requires the acquired claim_id")
    for file_value in claim.get("owned", ()) or ():
        marker = _claim_marker(root, file_value)
        if not marker.exists():
            continue
        existing = _read_marker(marker)
        if existing is None or (
            existing.get("owner") != owner
            or existing.get("task_key") != task_key
            or existing.get("claim_id") != claim_id
            or existing.get("process_token") != _PROCESS_TOKEN
        ):
            raise XKeyAuthorizationError(
                f"claim marker {marker} belongs to another owner/task/generation"
            )
        _unlink_claim_marker(marker)


def claim_read(root: pathlib.Path | str) -> list[dict]:
    """Read every claim marker (sorted; unreadable markers fail closed)."""

    directory = claims_dir(root)
    if not directory.is_dir():
        return []
    rows: list[dict] = []
    for marker in sorted(directory.glob("*.json")):
        data = _read_marker(marker)
        if data is None:
            raise XKeyFormatError(f"claim marker is unreadable or not an object: {marker}")
        rows.append(data)
    return rows



# --- Normal-PM consumption for H07 (T20-pm-source) ---------------------------
#
# The strict layer above takes a ``TrustedSupply``. A normally claimed PM must
# not assemble that source/usage/bearer by hand. These functions read the real
# protected source through ``contract_guard.prepare_pm_binding`` (which uses
# ``operator_authority.read_pm_authority``), verify the recorded
# ``dp-gate-approve`` decision + T10 rows + live claim + policy hash, and only
# then run the original strict repair assessment. The write itself re-reads the
# source and re-runs that assessment immediately before ``apply_block_replace``;
# a revoked record, moved claim, changed gate/version or an exclusive-face
# conflict in between refuses the write. Nothing is dispatched here and no
# approval is minted: the PM decision must already be recorded.


def _repair_plan(
    root: pathlib.Path | str,
    request: "RepairRequest",
    approval: "RepairApproval | None",
    claim_request: object,
    actor: str,
    role: str,
    note: str | None,
) -> dict:
    return {
        "root": pathlib.Path(root),
        "request": request,
        "approval": approval,
        "claim_request": claim_request,
        "actor": actor,
        "role": role,
        "note": note,
        "family": "cross-key-repair",
    }


def _marker_claims(root: pathlib.Path | str) -> list:
    """Claim markers as the pure validity layer's typed ``Claim`` rows.

    A readable exclusive marker is an active claim; a marker that cannot be
    read is left to the strict source check (which refuses unknown owners).
    """

    rows: list = []
    for marker in claim_read(root):
        if not isinstance(marker, dict):
            continue
        files = marker.get("files")
        if not isinstance(files, (list, tuple)) or not files:
            single = marker.get("file")
            files = (single,) if isinstance(single, str) and single else ()
        owner = marker.get("owner")
        task_key = marker.get("task_key")
        if not files or not isinstance(owner, str) or not isinstance(task_key, str):
            continue
        rows.append(
            _validity.Claim(
                owner=owner,
                task_key=task_key,
                files=tuple(str(item) for item in files),
                active=True,
                lock_mode="exclusive",
            )
        )
    return rows


def prepare_repair_consumption(
    root: pathlib.Path | str,
    *,
    key: str,
    request: "RepairRequest",
    approval: "RepairApproval | None",
    claim_request: object,
    actor: str,
    role: str,
    gate_id: str,
    decision_ref: str,
    note: str | None,
    expected_matter_ref: str | None = None,
    expected_version: str | None = None,
) -> _guard.PmConsumption:
    """Bind the recorded repair approval to the real PM source (no write)."""

    plan = _repair_plan(root, request, approval, claim_request, actor, role, note)
    binding, reasons = _guard.prepare_pm_binding(
        root,
        key,
        gate_id=gate_id,
        decision_ref=decision_ref,
        note=note,
        authority_ref=request.authorization,
        gate_kind="xkey-authorize",
        expected_gate_key=request.target_key,
        required_scope=(
            f"xkey-repair:{request.target_key}",
            f"xkey-action:{request.action}",
            *(f"xkey-file:{file}" for file in request.files),
        ),
        require_files=tuple(request.files),
        target_key=request.target_key,
        expected_matter_ref=expected_matter_ref,
        expected_version=expected_version,
    )
    if reasons:
        # Still give the caller the original assessment shape (blocked, never
        # executable) so the surface/role/claim reason is visible. No source is
        # bound here, so the writer can never accept this verdict.
        local = assess_repair_request(
            request,
            approval,
            _marker_claims(root),
            claim_request,
            actor=actor,
            role=role,
            supply=None,
            pm_note=note,
        )
        blocked = tuple(dict.fromkeys((*reasons, *local.reasons)))
        return _guard.PmConsumption(
            family="cross-key-repair",
            status="blocked",
            reasons=blocked,
            binding=None,
            verdict=local,
            action=None,
            written=False,
            target=None,
            receipt={"family": "cross-key-repair", "blocked_reasons": list(blocked)},
            plan=plan,
        )
    claims = _marker_claims(root)
    verdict = assess_repair_request(
        request,
        approval,
        claims,
        claim_request,
        actor=actor,
        role=role,
        supply=binding.supply,
        pm_note=note,
    )
    status = "authorized" if verdict.executable else "blocked"
    return _guard.PmConsumption(
        family="cross-key-repair",
        status=status,
        reasons=tuple(verdict.reasons),
        binding=binding,
        verdict=verdict,
        action=None,
        written=False,
        target=None,
        receipt=_guard._pm_receipt(binding, action=None, verdict=verdict, target=None),
        plan=plan,
    )


def consume_repair_request(*args: object, **kwargs: object) -> _guard.PmConsumption:
    """One normal-PM call: consume the recorded decision into an authorization.

    This deliberately does not dispatch or write. Execution is the separate
    :func:`apply_repair_consumption`, which re-reads the source first.
    """

    return prepare_repair_consumption(*args, **kwargs)


def apply_repair_consumption(
    consumption: _guard.PmConsumption,
    ticket: dict,
    new_bytes: bytes,
) -> _guard.PmConsumption:
    """Re-read the source, re-assess, then perform the original exact write."""

    if (
        not isinstance(consumption, _guard.PmConsumption)
        or consumption.family != "cross-key-repair"
        or consumption.binding is None
    ):
        return consumption
    plan = consumption.plan
    fresh, reasons = _guard.revalidate_pm_binding(consumption.binding)
    if reasons:
        return _guard.PmConsumption(
            family="cross-key-repair",
            status="blocked",
            reasons=reasons,
            binding=consumption.binding,
            verdict=None,
            action=None,
            written=False,
            target=None,
            receipt=_guard._pm_receipt(
                consumption.binding,
                action=None,
                verdict=None,
                target=None,
                reasons=reasons,
            ),
            plan=plan,
        )
    request = plan["request"]
    approval = plan["approval"]
    verdict = assess_repair_request(
        request,
        approval,
        _marker_claims(plan["root"]),
        plan["claim_request"],
        actor=str(plan["actor"]),
        role=str(plan["role"]),
        supply=fresh.supply,
        pm_note=str(plan["note"]) if plan["note"] is not None else None,
    )
    if not verdict.executable:
        return _guard.PmConsumption(
            family="cross-key-repair",
            status="blocked",
            reasons=tuple(verdict.reasons),
            binding=fresh,
            verdict=verdict,
            action=None,
            written=False,
            target=None,
            receipt=_guard._pm_receipt(
                fresh,
                action=None,
                verdict=verdict,
                target=None,
                reasons=verdict.reasons,
            ),
            plan=plan,
        )
    try:
        target_file, _range, _sha = _apply_targets(ticket)
        new_sha = apply_block_replace(
            plan["root"], ticket, new_bytes, authorization=verdict
        )
    except XKeyShaDrift:
        return _guard.PmConsumption(
            family="cross-key-repair",
            status="blocked",
            reasons=("frozen_block_drift",),
            binding=fresh,
            verdict=verdict,
            action=None,
            written=False,
            target=None,
            receipt=_guard._pm_receipt(
                fresh,
                action=None,
                verdict=verdict,
                target=None,
                reasons=("frozen_block_drift",),
            ),
            plan=plan,
        )
    except XKeyAuthorizationError as exc:
        reason = (
            "ticket_boundary_violation"
            if isinstance(exc, XKeyBoundaryViolation)
            else "write_not_authorized"
        )
        return _guard.PmConsumption(
            family="cross-key-repair",
            status="blocked",
            reasons=(reason,),
            binding=fresh,
            verdict=verdict,
            action=None,
            written=False,
            target=None,
            receipt=_guard._pm_receipt(
                fresh,
                action=None,
                verdict=verdict,
                target=None,
                reasons=(reason,),
            ),
            plan=plan,
        )
    except XKeyFormatError:
        return _guard.PmConsumption(
            family="cross-key-repair",
            status="blocked",
            reasons=("invalid_ticket",),
            binding=fresh,
            verdict=verdict,
            action=None,
            written=False,
            target=None,
            receipt=_guard._pm_receipt(
                fresh,
                action=None,
                verdict=verdict,
                target=None,
                reasons=("invalid_ticket",),
            ),
            plan=plan,
        )
    receipt = _guard._pm_receipt(
        fresh, action="restricted-repair-write", verdict=verdict, target=target_file
    )
    receipt["new_sha256"] = new_sha
    return _guard.PmConsumption(
        family="cross-key-repair",
        status="applied",
        reasons=(),
        binding=fresh,
        verdict=verdict,
        action="restricted-repair-write",
        written=True,
        target=target_file,
        receipt=receipt,
        plan=plan,
    )
