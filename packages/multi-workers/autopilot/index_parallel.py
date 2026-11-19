"""autopilot/index_parallel.py — the conductor's ONE claim-cell writer (T-16).

`_index.parallel` has several writers in this system (the TS
``shared/index-store.ts`` under the window lock, the framework's
``update_index.py`` under the same lock) and T-16 must not add a *concurrent*
one. This module is therefore deliberately narrow:

  * it writes exactly ONE cell group of ONE row — the ``ClaimId`` (plus the
    ``Status``/``Updated`` cells a real claim moves) — never whole-table
    rewrites, never a row insert for a key that has no row;
  * every other BYTE FRAGMENT of the file (header, separator, blank lines, rows
    it does not target, mixed LF/CRLF, no trailing newline, trailing blank
    lines, and even unparsable lines) is copied verbatim through
    ``splitlines(keepends=True)`` + ``"".join(...)``; only the one target row's
    body is re-rendered with its original line ending. A conductor claim can
    never delete or re-normalize a row the parser could not read (T-09/D-005);
  * every write happens under the **shared** `.mw/index.lock`
    (O_CREAT|O_EXCL, the same file the TS `IndexStore` and `update_index.py`
    take), so the synthetic-claim write is serialized against every existing
    claim writer instead of racing them;
  * the read-modify-write is verified against a fresh read (mtime unchanged
    during the hold) and retried, mirroring ``update_index._write_index_atomic``;
  * a transient `os.replace` failure (Windows EPERM/AV/editor hold) on the
    AUTHORITY returns ``False`` and leaves the file untouched — a claim write
    is best-effort and must never kill a conductor tick;
  * after a successful authority write, the SAME `index.lock` hold refreshes
    the derived complete-active projection (`_index.md`) from the exact rows
    just written (`autopilot.active_projection`, design D-002/D-005/D-006).
    The authority file is still rewritten one row at a time — no whole-table
    rewrite is introduced for the projection. A projection failure raises
    `ActiveProjectionError` with a message that the authority may already have
    changed: there is NO cross-file transaction, no authority rollback, and the
    next successful mutation (or `mw init`) rebuilds the projection.
  * before any write, the authority bytes are strict-UTF-8 decoded and a
    STRICT raw-active parser rejects any untrusted active row, invalid UTF-8,
    and duplicate normalized target keys. Those cases raise
    `ActiveProjectionError` with zero authority/projection writes; a physical
    projection IO failure AFTER the authority replace is a visible PARTIAL
    WRITE, never a silent success.

The row format is the frozen 7-column AgenticTask schema
``| Key | Status | Phase | ClaimId | Deps | Desc | Updated |`` (legacy
5-column rows keep their own claim index), parsed by
``autopilot.active_projection``'s strict raw-active parser: canonical 7-column
or trusted 5-column legacy rows only. The column count and order are never
changed; only cell values move.
"""

from __future__ import annotations

import os
import pathlib
import sys
import time
from collections.abc import Callable

# Script-mode bootstrap (same rationale as state.py / dispatch.py).
_PARENT = pathlib.Path(__file__).resolve().parent.parent
if str(_PARENT) not in sys.path:
    sys.path.insert(0, str(_PARENT))

import mw_common  # noqa: E402  (path bootstrapped above)
from autopilot import active_projection as _projection  # noqa: E402

INDEX_FILE = "_index.parallel"
INDEX_LOCK_NAME = "index.lock"
# The framework's placeholder for "no claim" in a cell.
NO_CLAIM = "—"

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


def _claim_index(cols: list[str]) -> int:
    """Claim cell index: 3 in the 7-column schema, 2 in a legacy 5-column row."""
    return 3 if len(cols) >= 7 else 2


def _render(cols: list[str]) -> str:
    return "| " + " | ".join(cols) + " |"


def _write_atomic(path: pathlib.Path, fragments: list[str]) -> bool:
    """Per-PID tmp + atomic replace; ``False`` on a persistent OS refusal.

    ``fragments`` come from ``str.splitlines(keepends=True)``: joining them
    verbatim preserves every original line ending, a missing final newline and
    trailing blank lines. ``write_text(..., newline="")`` prevents Windows CRLF
    translation. No whole-table normalization is performed.
    """
    content = "".join(fragments)
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
    """Locked, byte-exact read-modify-write of exactly ONE target row.

    Strict UTF-8 and strict raw-active validation happen before any write;
    duplicate normalized targets are refused rather than picking the first
    row. Non-target byte fragments (including their line endings) are copied
    verbatim. A projection IO failure after the authority replace is a visible
    PARTIAL WRITE, never a silent success.
    """
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
        target = _projection.normalize_key(key)
        try:
            before = path.stat().st_mtime_ns
            raw = path.read_bytes()
        except OSError:
            return False
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise _projection.ActiveProjectionError(
                f"_index.parallel contains invalid UTF-8 ({exc}); refusing to "
                "decode with replacement characters or rewrite any bytes"
            ) from exc
        fragments = text.splitlines(keepends=True)
        matches = [
            (index, cells, ending)
            for index, row, cells, ending
            in _projection.strict_rows_with_lines(fragments)
            if _projection.normalize_key(row["key"]) == target
        ]
        if len(matches) > 1:
            raise _projection.ActiveProjectionError(
                f"ambiguous normalized target key {target!r}: "
                f"{len(matches)} authority rows match; refusing to pick the "
                "first row for a claim (authority and projection were not written)"
            )
        if not matches:
            return False
        index, cols, ending = matches[0]
        if not apply(cols, _claim_index(cols)):
            return False
        new_fragments = list(fragments)
        new_fragments[index] = _render(cols) + ending
        # The lock is the primary exclusion; this re-check is the in-process
        # defence `update_index` also keeps.
        if path.stat().st_mtime_ns != before:
            return False
        # Serialize from the EXACT new fragments, before touching the authority:
        # mixed bad active rows / illegal keys must fail closed with zero writes.
        projection = _projection.projection_text_from_lines(new_fragments)
        if not _write_atomic(path, new_fragments):
            return False
        # Same lock hold: the authority is now written. A projection failure is
        # deliberately visible rather than swallowed: the authority may already
        # have changed and the next successful mutation rebuilds the view.
        try:
            _projection.write_projection(project_root, projection)
        except _projection.ActiveProjectionError as exc:
            raise _projection.ActiveProjectionError(
                f"PARTIAL WRITE: _index.parallel authority was already written "
                f"for {key!r}; _index.md projection is stale: {exc}"
            ) from exc
        return True
    except OSError:
        return False
    finally:
        mw_common.release_lock(lock)
