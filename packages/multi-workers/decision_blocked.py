"""Project-local receipts for DP attempts that stopped without a result or effect."""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import sys
import uuid
from collections.abc import Mapping

import decision


def record(
    project: pathlib.Path,
    *,
    source: str,
    stage: str,
    result: Mapping,
    key: str | None = None,
    task_key: str | None = None,
    gate_id: str | None = None,
    config: object = None,
    snapshot: decision.CredentialSnapshot | None = None,
) -> str | None:
    """Publish a single receipt atomically, even when several windows block at once."""
    event_id = str(uuid.uuid4())
    directory = project / ".agenticdoc" / "_autopilot" / "dp-blocked"
    temporary = directory / f".{event_id}.tmp"
    try:
        if config is None:
            config, _ = decision.DecisionConfig.from_project(project)
        redactor = decision.known_secret_redactor(config, snapshot=snapshot)

        def clean(value: object, limit: int) -> str | None:
            if not isinstance(value, str) or not value:
                return None
            return " ".join(redactor.redact(value).text.split())[:limit] or None

        issues = result.get("issues")
        event = {
            "schema_version": 1,
            "event_id": event_id,
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "source": source,
            "stage": stage,
            "dp": clean(result.get("dp"), 120),
            "key": clean(key, 120),
            "task_key": clean(task_key, 160),
            "logical_id": clean(result.get("logical_id"), 160),
            "decision_id": clean(result.get("decision_id"), 180),
            "gate_id": clean(gate_id, 160),
            "reason": clean(result.get("reason"), 120) or "unavailable",
            "escalated_reason": clean(result.get("escalated_reason"), 120),
            "detail": clean(result.get("detail"), 400),
            "issues": [
                {"field": clean(issue.get("field"), 120), "issue": clean(issue.get("issue"), 200)}
                for issue in issues[:8] if isinstance(issue, Mapping)
            ] if isinstance(issues, list) else [],
        }
        directory.mkdir(parents=True, exist_ok=True)
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(event, stream, ensure_ascii=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(directory / f"{event_id}.json")
    except Exception as exc:  # noqa: BLE001 - recording must preserve the original refusal
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        print(f"[mw decide] could not record DP block ({type(exc).__name__})", file=sys.stderr)
        return None
    return event_id
