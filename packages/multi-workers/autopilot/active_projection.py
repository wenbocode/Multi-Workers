"""autopilot/active_projection.py — canonical `_index.md` active projection.

Design D-002/D-005/D-006 (key ``mw-window-claim-isolation``, T-03/T-09).
``.agenticdoc/_index.md`` is a DERIVED view of the authoritative
``.agenticdoc/_index.parallel``: UTF-8/LF, no BOM, exactly::

    # AgenticTask Index

    active_keys: ["key-a", "key-b"]

Frozen bytes: ``"# AgenticTask Index" + LF + LF + "active_keys: " +
json.dumps(keys) + LF``. Empty is ``[]``; one key is still an array. Order is
the parallel row order, de-duplicated through normalize_key with the FIRST
active row's stored spelling preserved.

T-09 hardens the two private writers (``autopilot.index_parallel._mutate`` and
``mw.cmd_init``):

  * a STRICT raw-active parser rejects ANY untrusted active row (bad column
    count, bare/non-canonical pipe shape) before any authority or projection
    write, even when valid active rows are mixed in;
  * authority bytes are decoded as strict UTF-8; invalid UTF-8 fails closed
    instead of being decoded with ``errors="replace"`` and rewritten;
  * an existing `_index.md` is migrated only when it is a safely recognized
    program/legacy-scalar shape; real user content is preserved and reported
    as an INCOMPLETE projection (non-zero init), never a warn-and-success;
  * T-18 narrows that shape gate to the exact canonical program header and the
    one frozen `# legacy` / `active: stale` pair. An arbitrary user heading
    followed by `active_keys`/`active` is never treated as program content.
  * the conductor writer uses byte-exact line fragments with their original
    endings, so mixed LF/CRLF, no trailing newline and trailing blank lines
    survive verbatim outside the single target row.

This module takes NO lock of its own: every caller holds the shared
``.mw/index.lock``. A projection write failure after a successful authority
write is a visible PARTIAL WRITE, not a cross-file rollback; the next
successful mutation or ``mw init`` rebuilds the view. `_index.md` is never
read to decide identity, ownership or authority.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import uuid
from collections.abc import Iterable, Mapping

PROJECTION_NAME = "_index.md"
PROJECTION_HEADER = "# AgenticTask Index"
ACTIVE_PREFIX = "active_keys: "
LF = chr(10)
EMPTY_TEXT = PROJECTION_HEADER + LF + LF + ACTIVE_PREFIX + "[]" + LF
DASH = chr(0x2014)

# ── Key identity gate (same decision as update_index.py / index-store.ts) ────
RESERVED_INDEX_NAMES = (
    "_scratch",
    ".mw",
    "_index.parallel",
    "_index.md",
    "_workers.parallel",
    "_workers.stale.parallel",
    "_workers.acked",
    "_autopilot",
    "_project_log.md",
    "_arch_snapshot.md",
    "_pitfalls.md",
    ".agenticdoc",
    "_impl_gate.log",
    "_incidents",
)
RESERVED_INDEX_NAME_SET = frozenset(RESERVED_INDEX_NAMES)

_JS_TRIM_CHARS = (
    chr(9) + chr(10) + chr(11) + chr(12) + chr(13) + " "
    + chr(0x00A0) + chr(0xFEFF) + chr(0x2028) + chr(0x2029)
    + chr(0x1680)
    + "".join(chr(code) for code in range(0x2000, 0x200B))
    + chr(0x202F) + chr(0x205F) + chr(0x3000)
)
KEY_MAX_LENGTH = 64
_ASCII_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
_ILLEGAL_KEY_CHARS = set(":<>\"|?*")
_KEY_SHAPE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
_SEPARATOR_CHARS = set("|-: " + chr(9))
_INDEX_HEADER_CELLS = (
    "Key", "Status", "Phase", "ClaimId", "Deps", "Desc", "Updated",
)
_APPROVED_LEGACY_SHAPE = ("# legacy", "active: stale")


class ActiveProjectionError(RuntimeError):
    """The derived projection could not be written; authority may have moved."""


def normalize_key(key: str) -> str:
    """Comparison form of a key: JS-trimmed and lower-cased (normalizeKey)."""
    return key.strip(_JS_TRIM_CHARS).lower()


def key_name_refusal(key: str) -> tuple[str, str] | None:
    """Stable ``(code, message)`` of a refused name, or ``None`` when usable."""
    trimmed = key.strip(_JS_TRIM_CHARS)
    if not trimmed:
        return ("empty-key", "the key is empty")
    if normalize_key(trimmed) in RESERVED_INDEX_NAME_SET:
        return (
            "reserved-key-name",
            f"'{trimmed}' is a reserved framework name, not an AgenticTask key namespace",
        )
    if trimmed in (".", ".."):
        return ("key-path-escape", f"'{trimmed}' escapes the .agenticdoc root")
    if (
        chr(47) in trimmed
        or chr(92) in trimmed
        or (len(trimmed) > 1 and trimmed[1] == ":" and trimmed[0] in _ASCII_LETTERS)
    ):
        return (
            "key-path-escape",
            f"'{trimmed}' contains a path separator or drive prefix",
        )
    if len(trimmed) > KEY_MAX_LENGTH:
        return (
            "key-illegal-shape",
            f"the key is {len(trimmed)} chars (max {KEY_MAX_LENGTH})",
        )
    if trimmed.endswith("."):
        return ("key-illegal-shape", f"'{trimmed}' ends with '.'")
    if any(
        ord(char) < 0x20 or ord(char) == 0x7F or char in _ILLEGAL_KEY_CHARS
        for char in trimmed
    ):
        return (
            "key-illegal-shape",
            f"'{trimmed}' contains a control, ADS or shell metacharacter",
        )
    if not _KEY_SHAPE_RE.fullmatch(trimmed):
        return (
            "key-illegal-shape",
            f"'{trimmed}' does not match ^[A-Za-z0-9][A-Za-z0-9._-]*$",
        )
    return None


def active_keys(rows: Iterable[Mapping[str, str]]) -> list[str]:
    """Pure: active keys in authority order, deduped, first spelling kept."""
    keys: list[str] = []
    seen: set[str] = set()
    for row in rows:
        status = str(row.get("status", "")).strip(_JS_TRIM_CHARS)
        if status != "active":
            continue
        key = str(row.get("key", "")).strip(_JS_TRIM_CHARS)
        normalized = normalize_key(key)
        if normalized in seen:
            continue
        seen.add(normalized)
        refusal = key_name_refusal(key)
        if refusal is not None:
            code, message = refusal
            raise ActiveProjectionError(
                f"active key refused ({code}): {message}; refusing to project "
                "an out-of-bounds key from _index.parallel"
            )
        keys.append(key)
    return keys


def serialize_keys(keys: list[str]) -> str:
    """Pure serialization of an already-selected, ordered key list."""
    if not keys:
        return EMPTY_TEXT
    rendered = json.dumps(keys, ensure_ascii=False)
    return PROJECTION_HEADER + LF + LF + ACTIVE_PREFIX + rendered + LF


def projection_text(rows: Iterable[Mapping[str, str]]) -> str:
    """Pure serialization: canonical UTF-8/LF text for one set of rows."""
    return serialize_keys(active_keys(rows))


def _line_body_and_ending(line: str) -> tuple[str, str]:
    """Split one ``splitlines(keepends=True)`` fragment into body + ending."""
    body_lines = line.splitlines(keepends=False)
    body = body_lines[0] if body_lines else ""
    return body, line[len(body):]


def _is_separator(line: str) -> bool:
    return line.startswith("|") and all(char in _SEPARATOR_CHARS for char in line)


def _is_canonical_index_header(cells: list[str]) -> bool:
    """Only the COMPLETE 7-column header is decoration, not `cells[0]=='Key'`."""
    return len(cells) == 7 and tuple(cells) == _INDEX_HEADER_CELLS


def _strict_row_from_line(
    body: str, lineno: int
) -> tuple[dict[str, str], list[str]] | None:
    """Parse one canonical 7-col or trusted legacy 5-col row.

    Any raw line containing an ``active`` cell that is NOT a canonical row is
    an untrusted active row: fail closed with zero writes. This also catches a
    pipe inside a key that shifts the status cell. Non-active unparsable/comment
    lines are ignored so byte-preserving conductors can keep them verbatim.
    """
    text = body.strip(_JS_TRIM_CHARS)
    if not text or text.startswith("#") or "|" not in text:
        return None
    cells = [cell.strip(_JS_TRIM_CHARS) for cell in text.strip("|").split("|")]
    looks_active = any(cell == "active" for cell in cells[1:])
    canonical = (
        text.startswith("|")
        and text.endswith("|")
        and not _is_separator(text)
    )
    valid_shape = (
        canonical
        and len(cells) in (5, 7)
        and cells[0] != ""
        and not _is_canonical_index_header(cells)
    )
    if looks_active and not valid_shape:
        raise ActiveProjectionError(
            f"untrusted raw active row at _index.parallel line {lineno}: "
            f"{body!r}; the strict parser cannot read it; refusing to project "
            "an incomplete active-key set (authority and projection were not written)"
        )
    if not valid_shape:
        return None
    if len(cells) == 7:
        row = {
            "key": cells[0], "status": cells[1], "phase": cells[2],
            "claim_id": cells[3], "deps": cells[4], "desc": cells[5],
            "updated": cells[6],
        }
    else:
        row = {
            "key": cells[0], "status": cells[1], "phase": DASH,
            "claim_id": cells[2], "deps": DASH, "desc": cells[3],
            "updated": cells[4],
        }
    return row, cells


def strict_rows_with_lines(
    lines: Iterable[str],
) -> list[tuple[int, dict[str, str], list[str], str]]:
    """Strict parse with fragment indices, cells and original line endings."""
    parsed: list[tuple[int, dict[str, str], list[str], str]] = []
    for index, fragment in enumerate(lines):
        body, ending = _line_body_and_ending(fragment)
        item = _strict_row_from_line(body, index + 1)
        if item is None:
            continue
        row, cells = item
        parsed.append((index, row, cells, ending))
    return parsed


def strict_rows_from_lines(lines: Iterable[str]) -> list[dict[str, str]]:
    return [row for _, row, _, _ in strict_rows_with_lines(lines)]


def rows_from_lines(lines: Iterable[str]) -> list[dict[str, str]]:
    """Backwards-compatible name; now STRICT, never silently omitting rows."""
    return strict_rows_from_lines(lines)


def strict_rows_from_bytes(raw: bytes) -> list[dict[str, str]]:
    """Strict UTF-8 decode; invalid bytes fail closed before any rewrite."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ActiveProjectionError(
            f"_index.parallel contains invalid UTF-8 ({exc}); refusing to "
            "decode with replacement characters or rewrite any bytes"
        ) from exc
    return strict_rows_from_lines(text.splitlines(keepends=True))


def projection_text_from_lines(lines: Iterable[str]) -> str:
    """Serialize from raw authority lines (conductor byte fragments)."""
    return projection_text(rows_from_lines(lines))


def write_projection(project_root: pathlib.Path, text: str) -> None:
    """Atomically replace ``_index.md``; caller holds the shared index.lock."""
    path = pathlib.Path(project_root) / ".agenticdoc" / PROJECTION_NAME
    tmp = path.with_name(
        f"{PROJECTION_NAME}.tmp.{os.getpid()}.{uuid.uuid4().hex}"
    )
    try:
        try:
            tmp.write_text(text, encoding="utf-8", newline="")
            os.replace(tmp, path)
        except (OSError, ValueError, TypeError) as exc:
            raise ActiveProjectionError(
                f"PARTIAL WRITE: failed to atomically write {PROJECTION_NAME}: "
                f"{exc!r}; _index.parallel may already have changed "
                "(no cross-file transaction); the next successful mutation "
                "or mw init rebuilds the projection"
            ) from exc
    finally:
        try:
            tmp.unlink()
        except OSError:
            pass


def _is_active_scalar_line(line: str) -> bool:
    """A single-value old machine shape (``active:`` / ``active_keys:``)."""
    for prefix in ("active:", "active_keys:"):
        if line.startswith(prefix):
            value = line[len(prefix):].strip(_JS_TRIM_CHARS)
            if value.startswith("["):
                return False
            return " " not in value and chr(9) not in value
    return False


def _is_active_array_line(line: str) -> bool:
    if not line.startswith("active_keys:"):
        return False
    value = line[len("active_keys:"):].strip(_JS_TRIM_CHARS)
    return value.startswith("[") and value.endswith("]")


def _projection_shape(raw: bytes) -> str:
    """Classify an existing `_index.md`: program / legacy / user.

    ``program`` = canonical-header + active_keys array (stale arrays included).
    ``legacy`` = blank/whitespace slot, no-header or old-header single-value
    machine scalar. ``user`` = anything else (including canonical header plus
    real prose): preserve and make init explicitly incomplete. Strict UTF-8
    only; invalid bytes are a hard fail-closed error, never replacement text.
    """
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ActiveProjectionError(
            f"_index.md contains invalid UTF-8 ({exc}); refusing to rewrite it"
        ) from exc
    nonblank = [
        line.strip(_JS_TRIM_CHARS)
        for line in text.splitlines()
        if line.strip(_JS_TRIM_CHARS)
    ]
    if not nonblank:
        return "legacy"
    if len(nonblank) == 1:
        line = nonblank[0]
        if _is_active_array_line(line):
            return "program"
        if _is_active_scalar_line(line):
            return "legacy"
        return "user"
    if len(nonblank) == 2:
        first, second = nonblank
        if first == PROJECTION_HEADER:
            if _is_active_array_line(second):
                return "program"
            if _is_active_scalar_line(second):
                return "legacy"
            return "user"
        if (first, second) == _APPROVED_LEGACY_SHAPE:
            return "legacy"
        return "user"
    return "user"


def sync_init_projection(project_root: pathlib.Path) -> str:
    """Create/correct the init projection from the CURRENT authority table.

    The caller holds ``.mw/index.lock`` for this whole call. Returns one of
    ``created`` / ``corrected`` / ``migrated`` / ``unchanged`` /
    ``incomplete-user-content``. The last state means the existing `_index.md`
    was preserved but is NOT a complete projection; the caller must report a
    non-zero, incomplete init rather than a green AC-006. Only `_index.md` may
    be written here; invalid UTF-8 or untrusted active authority rows fail
    closed with ZERO writes.
    """
    project_root = pathlib.Path(project_root)
    authority = project_root / ".agenticdoc" / "_index.parallel"
    path = project_root / ".agenticdoc" / PROJECTION_NAME
    try:
        authority_bytes = authority.read_bytes() if authority.is_file() else b""
        current = path.read_bytes() if path.is_file() else None
    except OSError as exc:
        raise ActiveProjectionError(
            f"cannot read the authority/projection to build active_keys: {exc!r}; "
            "no projection write was attempted"
        ) from exc
    rows = strict_rows_from_bytes(authority_bytes)
    text = serialize_keys(active_keys(rows))
    if current is None:
        write_projection(project_root, text)
        return "created"
    if current == text.encode("utf-8"):
        return "unchanged"
    shape = _projection_shape(current)
    if shape == "user":
        return "incomplete-user-content"
    write_projection(project_root, text)
    return "corrected" if shape == "program" else "migrated"
