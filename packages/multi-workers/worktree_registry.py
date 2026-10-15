"""
worktree_registry.py — junction registry for `mw worktree` (G3 seam, T-W02).

An entry binds one reparse point created by `mw worktree add --link-deps` to
its target, so a later `mw worktree rm` can clear it and the `mw doctor`
worktree_links section (T-W03) can report leftovers.

Location: <project>/.mw/worktree-registry.json
Lock:     <project>/.mw/worktree-registry.lock

Writes are lock + tmp + os.replace + read-back verification. `open("w")`
truncates before serializing, so a serialization failure there would leave an
empty file that reads back as "no links registered" — a false negative, which
is exactly the failure class this guard exists to prevent.

Fields (AC-008 names target/created_at/created_by):

    link        absolute path of the reparse point
    target      absolute path the link resolves to
    worktree    absolute path of the worktree the link was created for
    repo_root   absolute path of the repository whose node_modules it targets
    created_at  ISO-8601 local timestamp
    created_by  "mw worktree add --link-deps (pid ..., user ...)"

Concurrency reuses ``mw_common.acquire_lock`` / ``release_lock`` (the same
O_CREAT|O_EXCL protocol the TS side uses) — no second lock implementation.
"""
from __future__ import annotations

import getpass
import json
import os
import pathlib
from datetime import datetime
from typing import Iterator

import mw_common

REGISTRY_FILE_NAME = "worktree-registry.json"
REGISTRY_LOCK_NAME = "worktree-registry.lock"
REGISTRY_VERSION = 1

#: Fields every entry must carry; `link` is the upsert key, the rest feed
#: AC-008 and the doctor/rm lookups.
REQUIRED_FIELDS = ("link", "target", "created_at", "created_by")


class WorktreeRegistryError(RuntimeError):
    """Unreadable or malformed registry file.

    Fail-closed: a corrupt registry must never be read as an empty one. An
    empty registry means "no leftover links", which is the false negative the
    whole worktree guard exists to prevent.
    """


def registry_path(project_root: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_root) / ".mw" / REGISTRY_FILE_NAME


def registry_lock(project_root: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(project_root) / ".mw" / REGISTRY_LOCK_NAME


def _normkey(path: str) -> str:
    return os.path.normcase(os.path.normpath(str(path)))


def _validate_entry(entry: object) -> dict:
    if not isinstance(entry, dict):
        raise WorktreeRegistryError(f"registry entry is not an object: {entry!r}")
    missing = [
        field for field in REQUIRED_FIELDS
        if not str(entry.get(field) or "").strip()
    ]
    if missing:
        raise WorktreeRegistryError(
            f"registry entry missing {', '.join(missing)}: {entry!r}"
        )
    return {str(key): str(value) for key, value in entry.items()}


def read_registry(project_root: pathlib.Path) -> list[dict]:
    """All entries, in file order. Missing file -> ``[]``; bad file -> raise."""
    path = registry_path(project_root)
    # D-17 (T-W16): `exists()` follows a reparse point, so a dangling link to a
    # removed target reads as "no registry" and the doctor goes silent - the
    # one silent shape among the bad-registry corpus. `lexists` does not follow
    # the final component, so the dangling link reaches `read_text`, raises, and
    # folds into `WorktreeRegistryError` (fail-closed). A genuinely absent file
    # still returns `[]`.
    if not os.path.lexists(str(path)):
        return []
    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, ValueError) as exc:
        raise WorktreeRegistryError(f"cannot read registry {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("entries"), list):
        raise WorktreeRegistryError(
            f"malformed registry {path}: expected {{'version', 'entries': [...]}}"
        )
    return [_validate_entry(entry) for entry in data["entries"]]


def iter_entries(project_root: pathlib.Path) -> Iterator[dict]:
    """Read-only iteration over the registry (missing file -> empty)."""
    yield from read_registry(project_root)


def find_entry(project_root: pathlib.Path, link: str) -> dict | None:
    key = _normkey(link)
    for entry in read_registry(project_root):
        if _normkey(entry["link"]) == key:
            return entry
    return None


def _write_registry(project_root: pathlib.Path, entries: list[dict]) -> None:
    path = registry_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": REGISTRY_VERSION, "entries": entries}
    tmp = pathlib.Path(str(path) + ".tmp")
    tmp.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    os.replace(str(tmp), str(path))


def register_link(
    project_root: pathlib.Path,
    *,
    link: str,
    target: str,
    worktree: str,
    repo_root: str,
    created_by: str,
    created_at: str | None = None,
) -> dict:
    """Upsert one entry by ``link`` under the registry lock, then read it back.

    Returns the stored entry. Raises ``WorktreeRegistryError`` when a required
    field is empty or when the read-back does not match what was written.
    """
    entry = _validate_entry({
        "link": str(link),
        "target": str(target),
        "worktree": str(worktree),
        "repo_root": str(repo_root),
        "created_at": created_at or datetime.now().astimezone().isoformat(timespec="seconds"),
        "created_by": str(created_by),
    })
    key = _normkey(entry["link"])
    lock = registry_lock(project_root)
    mw_common.acquire_lock(lock)
    try:
        entries = [e for e in read_registry(project_root) if _normkey(e["link"]) != key]
        entries.append(entry)
        _write_registry(project_root, entries)
        stored = find_entry(project_root, entry["link"])
        if stored is None or stored["target"] != entry["target"]:
            raise WorktreeRegistryError(
                f"registry read-back mismatch for {entry['link']}: wrote {entry['target']!r}, "
                f"read {stored and stored.get('target')!r}"
            )
        return stored
    finally:
        mw_common.release_lock(lock)


def unregister_link(project_root: pathlib.Path, link: str) -> bool:
    """Drop the entry for ``link`` (idempotent). True when one was removed."""
    key = _normkey(link)
    lock = registry_lock(project_root)
    mw_common.acquire_lock(lock)
    try:
        entries = read_registry(project_root)
        remaining = [e for e in entries if _normkey(e["link"]) != key]
        if len(remaining) == len(entries):
            return False
        _write_registry(project_root, remaining)
        if find_entry(project_root, link) is not None:
            raise WorktreeRegistryError(f"registry read-back still contains {link} after unregister")
        return True
    finally:
        mw_common.release_lock(lock)


def created_by_now(prefix: str = "mw worktree add --link-deps") -> str:
    """Audit identity for `created_by`, mirroring the `_workers.parallel` origin idea."""
    try:
        user = getpass.getuser()
    except (OSError, KeyError):
        user = "unknown"
    return f"{prefix} (pid {os.getpid()}, user {user})"
