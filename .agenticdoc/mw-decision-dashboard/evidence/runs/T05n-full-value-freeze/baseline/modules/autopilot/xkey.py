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

Ticket frontmatter is the gate-protocol *shape* (``---`` fenced ``key: value``
block + human body) rendered by this module's own YAML subset; complex values
are rendered as nested blocks (or inline JSON, which the parser also accepts,
so hand-written tickets round-trip).

Hashing (D-011/D-012): every mechanical anchor is a **byte-exact** sha256 over
the frozen ``line_range`` bytes, CRLF/LF untouched. Matching EOL-normalized
values are recorded alongside as ``sha256_eol_normalized`` (same recipe as
``mw_common.sha256_eol_normalized``, which is path-scoped and therefore not
directly usable for a block).
"""

from __future__ import annotations

import ast
import datetime
import fnmatch
import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys

# Script-mode bootstrap: mirror conductor.py / state.py so ``import mw_common``
# works both under pytest (repo root on sys.path) and as a plain module.
_PARENT = pathlib.Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import mw_common  # noqa: E402  (path bootstrapped above)

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


def apply_block_replace(root: pathlib.Path | str, ticket: dict, new_bytes: bytes) -> str:
    """Splice ``new_bytes`` over the ticket's frozen ``line_range`` (D-005).

    Recomputes ``sha256`` over the **current** bytes of that range and compares
    it with the ticket's ``old_block_sha256``; a mismatch raises
    :class:`XKeyShaDrift` and nothing is written. Otherwise the whole file is
    rewritten atomically (``tmp`` + ``os.replace``) with every other byte
    untouched. Returns ``sha256`` of the **new block bytes** (D-012), which is
    the ``new`` value of the AC-006 ``old → new`` pair.
    """
    if not isinstance(ticket, dict):
        raise XKeyFormatError("ticket must be a dict")
    status = ticket.get("status")
    if isinstance(status, str) and status in _UNAUTHORIZED_APPLY_STATUSES:
        raise XKeyAuthorizationError(
            f"ticket status {status!r} does not authorise a write"
        )
    file_value, line_range, expected_sha = _apply_targets(ticket)

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
