"""Typed local task-state observations; no file reads, credential discovery or model calls.

A snapshot is exactly :data:`FIELDS`. ``completed``/``remaining``/``blockers``
are either a real list (``[]`` = the producer observed "none") or ``None`` (the
producer did not record that axis); the two are never conflated. Nothing here
writes, infers a snapshot from a status, or turns an ``agent-report`` snapshot
into an execution permission - it only types the value a real producer sends.
"""
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

STATUSES = ("not-queued", "pending", "running", "done", "failed", "needs-clarification", "lost", "unknown")
SOURCES = ("worker-registry", "dispatch-result", "agent-report")
FIELDS = ("status", "observed_at", "source", "completed", "remaining", "blockers")


class TaskStateInputError(ValueError):
    """Names fields only; never echoes caller text or secrets."""


def validate_task_state(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not isinstance(value, Mapping) or set(value) != set(FIELDS):
        raise TaskStateInputError("task state requires exactly the declared fields")
    if value["status"] not in STATUSES:
        raise TaskStateInputError("task state status is invalid")
    if value["source"] not in SOURCES:
        raise TaskStateInputError("task state source is invalid")
    stamp = value["observed_at"]
    if not isinstance(stamp, str):
        raise TaskStateInputError("task state observed_at is invalid")
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        raise TaskStateInputError("task state observed_at is invalid") from None
    if parsed.tzinfo is None or "T" not in stamp:
        raise TaskStateInputError("task state observed_at requires a timezone")
    result: dict[str, object] = {"status": value["status"], "observed_at": stamp, "source": value["source"]}
    for field in ("completed", "remaining", "blockers"):
        items = value[field]
        if items is not None and (not isinstance(items, list) or any(not isinstance(item, str) or not item or "\x00" in item for item in items)):
            raise TaskStateInputError("task state progress lists are invalid")
        result[field] = list(items) if items is not None else None
    return result


def validate_observation_order(before: dict[str, object] | None, after: dict[str, object] | None) -> None:
    if before is not None and after is not None:
        if observation_time(after) < observation_time(before):
            raise TaskStateInputError("task after observation precedes task before observation")


def observation_time(snapshot: dict[str, object]) -> datetime:
    """The validated timezone-aware instant a recorded snapshot claims.

    The stored string is *never* normalised or re-rendered here: the exact
    producer text stays the recorded value, this only parses it for ordering.
    """
    stop = datetime.fromisoformat(str(snapshot["observed_at"]).replace("Z", "+00:00"))
    if stop.tzinfo is None:
        raise TaskStateInputError("task state observed_at requires a timezone")
    return stop


def same_snapshot(left: dict[str, object] | None, right: dict[str, object] | None) -> bool:
    """Exact structural equality of two validated snapshots.

    ``None`` only equals ``None``; ``completed=[]`` never equals
    ``completed=None`` and a reordered list is a different observation. This is
    what lets a writer refuse to *replace* an already-recorded before snapshot
    with the current state (a backfill) instead of silently accepting it.
    """
    if left is None or right is None:
        return left is None and right is None
    for field in FIELDS:
        if left[field] != right[field]:
            return False
    return True

