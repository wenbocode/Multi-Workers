"""Credential-free freshness checks for previously authorized file dependencies.

This module never discovers paths in model material or grants read scope. Its
input is the bounded lexical/canonical/hash metadata saved by the preparer.
Alias changes are reported without opening the newly resolved target.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import stat
from collections.abc import Mapping
from dataclasses import dataclass


MAX_FILE_BYTES = 8 * 1024 * 1024
# 64 citations + target config + Worker card + exact-file evidence policy.
MAX_DEPENDENCIES = 66
_SHA256 = re.compile(r"^[a-f0-9]{64}$")
_STATUSES = ("missing", "unreadable", "oversized")


class FileEvidenceError(ValueError):
    """Malformed dependency metadata; never includes caller values or text."""


@dataclass(frozen=True)
class FileEvidenceCheck:
    changed: bool
    revision: str


def parse_file_evidence(raw: object) -> list[dict[str, object]] | None:
    """Parse a response/proof wrapper; None means no dependency field was saved.

    Present malformed metadata raises before any path is opened. The canonical
    fallback and missing-status default match the TypeScript local cache reader.
    """
    if not isinstance(raw, Mapping) or "file_evidence" not in raw:
        return None
    values = raw["file_evidence"]
    if not isinstance(values, list) or len(values) > MAX_DEPENDENCIES:
        raise FileEvidenceError("file_evidence must be a bounded dependency array")
    dependencies: list[dict[str, object]] = []
    for value in values:
        if not isinstance(value, Mapping):
            raise FileEvidenceError("file_evidence dependency must be an object")
        path = value.get("path")
        if "sha256" not in value:
            raise FileEvidenceError("file_evidence dependency is missing sha256")
        digest = value["sha256"]
        if not isinstance(path, str) or not pathlib.Path(path).is_absolute():
            raise FileEvidenceError("file_evidence path must be absolute")
        if digest is not None and (not isinstance(digest, str) or not _SHA256.fullmatch(digest)):
            raise FileEvidenceError("file_evidence sha256 is invalid")
        canonical = value.get("canonical_path", path if digest is not None else None)
        if canonical is not None and (
            not isinstance(canonical, str) or not pathlib.Path(canonical).is_absolute()
        ):
            raise FileEvidenceError("file_evidence canonical_path must be absolute or null")
        if "status" in value and value["status"] is None:
            raise FileEvidenceError("file_evidence status is invalid")
        status = value.get("status", "missing" if digest is None else None)
        if status is not None and status not in _STATUSES:
            raise FileEvidenceError("file_evidence status is invalid")
        if (digest is not None and (canonical is None or status is not None)) or (
            digest is None and status is None
        ):
            raise FileEvidenceError("file_evidence hash/status combination is invalid")
        dependency: dict[str, object] = {
            "path": os.path.abspath(path),
            "canonical_path": os.path.abspath(canonical) if canonical is not None else None,
            "sha256": digest,
        }
        if status is not None:
            dependency["status"] = status
        dependencies.append(dependency)
    return dependencies


def _normalized_path(value: str) -> str:
    return os.path.normcase(os.path.abspath(value))


def _current_dependency(expected: Mapping[str, object]) -> dict[str, object]:
    lexical = pathlib.Path(str(expected["path"]))
    current: dict[str, object] = {
        "path": str(lexical), "canonical_path": None, "sha256": None, "status": "missing",
    }
    try:
        canonical = lexical.resolve(strict=True)
    except (OSError, ValueError, RuntimeError):
        return current
    current.update({"canonical_path": str(canonical), "status": "unreadable"})
    prior_canonical = expected["canonical_path"]
    if not isinstance(prior_canonical, str) or _normalized_path(str(canonical)) != _normalized_path(prior_canonical):
        # A new file or retargeted alias needs a new preparer authorization.
        return current
    try:
        before = canonical.stat()
        if not stat.S_ISREG(before.st_mode):
            return current
        if before.st_size > MAX_FILE_BYTES:
            current["status"] = "oversized"
            return current
        digest = hashlib.sha256()
        length = 0
        with canonical.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if (
                (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
                != (opened.st_dev, opened.st_ino, opened.st_size, opened.st_mtime_ns)
                or _normalized_path(str(lexical.resolve(strict=True))) != _normalized_path(str(canonical))
            ):
                return current
            while length <= MAX_FILE_BYTES:
                chunk = handle.read(min(64 * 1024, MAX_FILE_BYTES + 1 - length))
                if not chunk:
                    break
                length += len(chunk)
                digest.update(chunk)
            after = os.fstat(handle.fileno())
        if length > MAX_FILE_BYTES:
            current["status"] = "oversized"
            return current
        if (
            (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
            or _normalized_path(str(lexical.resolve(strict=True))) != _normalized_path(str(canonical))
        ):
            return current
        current["sha256"] = digest.hexdigest()
        current.pop("status")
    except (OSError, ValueError, RuntimeError):
        pass
    return current


def _signature(dependencies: list[dict[str, object]]) -> str:
    normalized = [
        {
            "path": _normalized_path(str(item["path"])),
            "canonical_path": (
                _normalized_path(str(item["canonical_path"])) if item["canonical_path"] is not None else None
            ),
            "sha256": item["sha256"],
            "status": item.get("status"),
        }
        for item in dependencies
    ]
    normalized.sort(key=lambda item: str(item["path"]))
    return hashlib.sha256(json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def check_file_evidence(dependencies: object) -> FileEvidenceCheck:
    """Compare saved dependencies to current files, without model calls/writes."""
    parsed = parse_file_evidence({"file_evidence": dependencies})
    assert parsed is not None
    current = [_current_dependency(expected) for expected in parsed]
    revision = _signature(current)
    return FileEvidenceCheck(revision != _signature(parsed), revision)
