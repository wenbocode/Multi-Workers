"""autopilot/index_parallel.py — the conductor's ONE claim-cell writer (T-16).

`_index.parallel` has several writers in this system (the TS
``shared/index-store.ts`` under the window lock, the framework's
``update_index.py`` under the same lock) and T-16 must not add a *concurrent*
one. This module is therefore deliberately narrow:

  * it writes exactly ONE cell group of ONE row — the ``ClaimId`` (plus the
    ``Status``/``Updated`` cells a real claim moves) — never whole-table
    rewrites, never a row insert for a key that has no row;
  * every other line of the file (header, separator, blank lines, rows it does
    not target, and even unparsable lines) is copied verbatim, so a conductor
    claim can never delete a row the parser could not read (the read-half of
    the IN-3 write bugs);
  * every write happens under the **shared** `.mw/index.lock`
    (O_CREAT|O_EXCL, the same file the TS `IndexStore` and `update_index.py`
    take), so the synthetic-claim write is serialized against every existing
    claim writer instead of racing them;
  * the read-modify-write is verified against a fresh read (mtime unchanged
    during the hold) and retried, mirroring ``update_index._write_index_atomic``;
  * a transient `os.replace` failure (Windows EPERM/AV/editor hold) returns
    ``False`` and leaves the file untouched — a claim write is best-effort and
    must never kill a conductor tick.

The row format is the frozen 7-column AgenticTask schema
``| Key | Status | Phase | ClaimId | Deps | Desc | Updated |`` (legacy
5-column rows keep their own claim index), parsed with the same tolerance as
``state._parse_index_row`` / ``update_index._parse_row``. The column count and
order are never changed; only cell values move.
"""

from __future__ import annotations

import os
import pathlib
import re
import sys
import time
from collections.abc import Callable

# Script-mode bootstrap (same rationale as state.py / dispatch.py).
_PARENT = pathlib.Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import mw_common  # noqa: E402  (path bootstrapped above)

INDEX_FILE = "_index.parallel"
INDEX_LOCK_NAME = "index.lock"
# The framework's placeholder for "no claim" in a cell.
NO_CLAIM = "—"

_HEADER_RE = re.compile(r"^\|[\s:\-|]+\|?\s*$")
_TRIM_CHARS = "\t\n\v\f\r "
# Windows: an editor/AV/indexer can hold the target open for a few ms; retry the
# atomic replace instead of dropping the heartbeat.
_REPLACE_RETRIES = 5
_REPLACE_DELAY_SEC = 0.02


def index_path(project_root: pathlib.Path) -> pathlib.Path:
    """`<project>/.agenticdoc/_index.parallel`."""
    return pathlib.Path(project_root) / ".agenticdoc" / INDEX_FILE


def index_lock_path(project_root: pathlib.Path) -> pathlib.Path:
    """The cross-writer lock `update_index._index_lock` / the TS store use."""
    return pathlib.Path(project_root) / ".mw" / INDEX_LOCK_NAME


def _cells(line: str) -> list[str] | None:
    """Cell list of one Markdown data row, or ``None`` for anything else.

    Mirrors `update_index._parse_row`'s structural rules: a row must start
    with ``|``, not be a separator, and carry at least 5 cells whose key is
    neither empty nor the header name.
    """
    s = line.strip(_TRIM_CHARS)
    if not s.startswith("|"):
        return None
    if _HEADER_RE.match(s):
        return None
    parts = s.strip("|").split("|")
    cols = [c.strip(_TRIM_CHARS) for c in parts]
    if len(cols) < 5 or cols[0] in ("Key", ""):
        return None
    return cols


def _claim_index(cols: list[str]) -> int:
    """Claim cell index: 3 in the 7-column schema, 2 in a legacy 5-column row."""
    return 3 if len(cols) >= 7 else 2


def _render(cols: list[str]) -> str:
    return "| " + " | ".join(cols) + " |"


def _write_atomic(path: pathlib.Path, lines: list[str], newline: str = "\n") -> bool:
    """Per-PID tmp + atomic replace; ``False`` on a persistent OS refusal.

    `newline` is the terminator the file already used, so a CRLF index keeps
    CRLF and a conductor claim never rewrites the file's line-ending style.
    """
    content = newline.join(lines) + newline
    tmp = path.with_name(f"_index.tmp.{os.getpid()}")
    try:
        tmp.write_text(content, encoding="utf-8", newline="")
        for attempt in range(_REPLACE_RETRIES):
            try:
                os.replace(tmp, path)
                return True
            except OSError:
                if attempt == _REPLACE_RETRIES - 1:
                    raise
                time.sleep(_REPLACE_DELAY_SEC)
    except OSError:
        try:
            tmp.unlink()
        except OSError:
            pass
        return False
    return False


def set_claim(
    project_root: pathlib.Path,
    key: str,
    *,
    claim_id: str,
    status: str | None = None,
    updated: str | None = None,
) -> bool:
    """Set one key's claim cell (locked, in place). Returns True when bytes moved.

    ``key`` is matched case-insensitively (the Windows key namespace is), the
    stored spelling is preserved. A key with no row is NOT created: a synthetic
    claim only ever annotates an existing registration (inventing a row would
    fabricate Phase/Desc facts — T-19/T-22's red line). ``status``/``updated``
    are optional so the heartbeat can move only the freshness cell.
    """
    return _mutate(
        project_root,
        key,
        lambda cols, idx: _apply_cells(cols, idx, claim_id=claim_id, status=status, updated=updated),
    )


def clear_claim(
    project_root: pathlib.Path,
    key: str,
    *,
    status: str | None = None,
    updated: str | None = None,
) -> bool:
    """Reset one key's claim cell to the framework's placeholder (locked)."""
    return _mutate(
        project_root,
        key,
        lambda cols, idx: _apply_cells(cols, idx, claim_id=NO_CLAIM, status=status, updated=updated),
    )


def _apply_cells(
    cols: list[str],
    idx: int,
    *,
    claim_id: str,
    status: str | None,
    updated: str | None,
) -> bool:
    changed = False
    if cols[idx] != claim_id:
        cols[idx] = claim_id
        changed = True
    if status is not None and len(cols) > 1 and cols[1] != status:
        cols[1] = status
        changed = True
    if updated is not None and len(cols) > idx and cols[-1] != updated:
        cols[-1] = updated
        changed = True
    return changed


def _mutate(
    project_root: pathlib.Path,
    key: str,
    apply: Callable[[list[str], int], bool],
) -> bool:
    """Locked read-modify-write of exactly one row. ``apply`` is a callable
    ``(cols, claim_idx) -> bool`` returning True when it touched the cells."""
    path = index_path(project_root)
    if not path.is_file():
        return False
    lock = index_lock_path(project_root)
    try:
        lock.parent.mkdir(parents=True, exist_ok=True)
        mw_common.acquire_lock(lock, retries=4, base_delay=0.02)
    except (OSError, RuntimeError):
        return False
    try:
        target = key.strip(_TRIM_CHARS).lower()
        try:
            before = path.stat().st_mtime_ns
            raw = path.read_bytes().decode("utf-8", errors="replace")
        except OSError:
            return False
        newline = "\r\n" if "\r\n" in raw else "\n"
        lines = raw.splitlines()
        out: list[str] = []
        changed = False
        for line in lines:
            cols = _cells(line)
            if cols is None or changed:
                out.append(line)
                continue
            if cols[0].strip(_TRIM_CHARS).lower() != target:
                out.append(line)
                continue
            idx = _claim_index(cols)
            if apply(cols, idx):
                changed = True
                out.append(_render(cols))
            else:
                out.append(line)
        if not changed:
            return False
        # The lock is the primary exclusion (same protocol as every writer);
        # this re-check is the in-process defence `update_index` also keeps.
        if path.stat().st_mtime_ns != before:
            return False
        return _write_atomic(path, out, newline)
    except OSError:
        return False
    finally:
        mw_common.release_lock(lock)
