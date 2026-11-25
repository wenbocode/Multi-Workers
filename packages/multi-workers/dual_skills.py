"""Deploy the release's UE Editor skill into the active dual project roots."""

from __future__ import annotations

import errno
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

import mw_common

SOURCE = Path(__file__).resolve().parent / "skills" / "dual" / "ue-editor-ui"
SLOT = Path(".agents", "skills", "ue-editor-ui")
MARKER = ".mw-managed.json"


def _entries(directory: Path) -> dict[str, bytes]:
    entries = {}
    for path in directory.rglob("*"):
        if path == directory / MARKER:
            continue
        info = path.lstat()
        if path.is_symlink() or getattr(info, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT:
            raise ValueError(f"redirected skill entry: {path}")
        if stat.S_ISREG(info.st_mode):
            entries[path.relative_to(directory).as_posix()] = path.read_bytes()
        elif not stat.S_ISDIR(info.st_mode) or not any(path.iterdir()):
            raise ValueError(f"unsupported skill entry: {path}")
    return entries


def _digests(entries: dict[str, bytes]) -> dict[str, str]:
    return {name: hashlib.sha256(data).hexdigest() for name, data in entries.items()}


def _safe_location(path: Path) -> None:
    if path.is_symlink() or path.resolve() != path:
        raise ValueError(f"redirected skill path: {path}")


def _atomic_json(path: Path, value: dict | list) -> None:
    with tempfile.TemporaryDirectory(prefix=".dual-skills-", dir=path.parent) as temp:
        staged = Path(temp) / path.name
        staged.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(staged, path)


def _recorded_roots(receipt: Path) -> set[Path]:
    try:
        roots = json.loads(receipt.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return set()
    if not isinstance(roots, list) or any(not isinstance(root, str) or not Path(root).is_absolute() for root in roots):
        raise ValueError(f"invalid dual skill receipt: {receipt}")
    return {Path(root) for root in roots}


def _management_record(target: Path) -> dict:
    marker = target / MARKER
    if not marker.is_file() or marker.is_symlink():
        return {}
    try:
        record = json.loads(marker.read_text(encoding="utf-8"))
    except ValueError:
        return {}
    return record if isinstance(record, dict) else {}


def _sync_slot(root: Path, owner: str, source: dict[str, bytes] | None) -> None:
    target = root / SLOT
    _safe_location(target)
    exists = target.exists()
    if not exists and source is None:
        return
    record = _management_record(target) if exists and target.is_dir() else {}
    before = None
    if record:
        try:
            current = _digests(_entries(target))
        except ValueError:
            current = None
        if current is not None and record.get("files") == current:
            if record.get("owner") == owner:
                before = current
            elif source is not None:
                raise ValueError(f"skill is managed by {record.get('owner')}: {target}")
    if exists and before is None:
        if source is not None and not (target / "SKILL.md").is_file():
            raise ValueError(f"skill slot is occupied without a SKILL.md: {target}")
        print(f"[mw target skills-sync] preserving project skill at {target}")
        return
    after = _digests(source) if source is not None else None
    if before == after:
        return

    if not root.is_dir():
        raise ValueError(f"project root not found: {root}")
    # Record only directories this deployment made. Leaving an empty
    # .agents/skills directory behind can still trigger pi's trust prompt.
    parents = (target.parent, target.parent.parent)
    created = (
        [path.name for path in parents if not path.exists()]
        if before is None else record.get("created", [])
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = Path(tempfile.mkdtemp(prefix=".ue-editor-ui-", dir=target.parent))
    _safe_location(temp)
    staged = temp / "skill"
    backup = temp / "previous"
    keep_backup = False
    try:
        if source is not None:
            for name, data in source.items():
                path = staged / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(data)
            (staged / MARKER).write_text(
                json.dumps({"owner": owner, "files": after, "created": created}, sort_keys=True) + "\n",
                encoding="utf-8",
            )
        if exists:
            target.rename(backup)
        try:
            if source is not None:
                staged.rename(target)
        except OSError:
            if exists:
                try:
                    backup.rename(target)
                except OSError as error:
                    keep_backup = True
                    raise OSError(f"could not restore {target}; previous copy retained at {backup}: {error}") from error
            raise
    finally:
        if not keep_backup:
            shutil.rmtree(temp)
    if source is None and isinstance(created, list):
        for path in parents:
            if path.name in created:
                try:
                    path.rmdir()
                except OSError as error:
                    if error.errno not in (errno.ENOENT, errno.ENOTEMPTY, errno.EEXIST):
                        raise
    action = "installed" if source is not None else "removed"
    print(f"[mw target skills-sync] {action} {target}")


def sync(project: Path) -> int:
    """Reconcile project copies with the resolved mode and remember prior roots for retries."""
    receipt = project / ".mw" / "dual-skills.json"
    lock = receipt.with_suffix(".lock")
    try:
        _safe_location(receipt)
        config = mw_common.load_target_config(project)
        if config["mode"] != "dual" and not receipt.exists() and not lock.exists():
            return 0
        fd = mw_common.acquire_lock(lock, deadline_s=3, delete_on_close=os.name == "nt")
        try:
            _sync_locked(project, receipt)
        finally:
            if fd is not None:
                os.close(fd)
            else:
                mw_common.release_lock(lock)
    except (OSError, ValueError, RuntimeError, mw_common.TargetConfigError) as error:
        print(f"[mw target skills-sync] Error: {error}. Retry with mw target skills-sync.", file=sys.stderr)
        return 1
    return 0


def _deployment_scope(project: Path) -> str:
    path = project / ".agenticdoc" / "dual-skills.json"
    if not path.exists() and not path.is_symlink():
        return "both"
    _safe_location(path)
    try:
        preferences = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as error:
        raise ValueError(f"invalid dual skill preferences at {path}: {error}") from error
    if not isinstance(preferences, dict) or set(preferences) != {"ue-editor-ui"}:
        raise ValueError(f"{path} must contain only the 'ue-editor-ui' setting")
    scope = preferences["ue-editor-ui"]
    if scope not in ("control", "both"):
        raise ValueError(f"{path}: 'ue-editor-ui' must be 'control' or 'both'")
    return scope


def _sync_locked(project: Path, receipt: Path) -> None:
    config = mw_common.load_target_config(project)
    previous = _recorded_roots(receipt)
    desired = set()
    source = None
    if config["mode"] == "dual":
        desired = {project}
        if _deployment_scope(project) == "both":
            desired.add(Path(config["game_root"]))
        if config["engine_root"] is not None:
            engine = Path(config["engine_root"])
            if any((root / SLOT).is_relative_to(engine) for root in previous | desired):
                raise ValueError(f"dual skill slot overlaps the engine root: {engine}")
        source = _entries(SOURCE)
        if "SKILL.md" not in source:
            raise ValueError(f"release skill missing: {SOURCE / 'SKILL.md'}")

    pending = previous | desired
    if pending != previous:
        _atomic_json(receipt, sorted(map(str, pending)))
    for root in sorted(desired):
        _sync_slot(root, str(project), source)
    for root in sorted(previous - desired):
        _sync_slot(root, str(project), None)

    if not desired:
        receipt.unlink(missing_ok=True)
    elif desired != pending:
        _atomic_json(receipt, sorted(map(str, desired)))
