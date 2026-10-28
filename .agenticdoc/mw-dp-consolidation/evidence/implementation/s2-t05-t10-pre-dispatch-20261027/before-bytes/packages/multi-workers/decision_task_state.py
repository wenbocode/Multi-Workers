"""Typed local task-state observations; no file reads, credential discovery or model calls."""
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
        first = datetime.fromisoformat(str(before["observed_at"]).replace("Z", "+00:00"))
        last = datetime.fromisoformat(str(after["observed_at"]).replace("Z", "+00:00"))
        if last < first:
            raise TaskStateInputError("task after observation precedes task before observation")
