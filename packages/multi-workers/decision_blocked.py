"""Project-local receipts for DP attempts that stopped without a result or effect."""

from __future__ import annotations

import datetime
import json
import os
import pathlib
import re
import sys
import uuid
from collections.abc import Mapping

import decision


def recall_prepared_block(project: pathlib.Path, logical_id: str, dp: str,
                       key: str, task_key: str | None) -> dict | None:
    if not re.fullmatch(r"[0-9a-f-]{36}", logical_id):
        return None
    directory = project / ".agenticdoc" / "_autopilot" / "dp-blocked"
    try:
        event_id = (directory / "by-logical-id" / logical_id).read_text(encoding="utf-8")
        if not re.fullmatch(r"[0-9a-f-]{36}", event_id):
            return None
        event = json.loads((directory / f"{event_id}.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not (
        isinstance(event, dict)
        and (event.get("logical_id"), event.get("dp"), event.get("key"), event.get("task_key"))
        == (logical_id, dp, key, task_key)
        and event.get("source") == "mw-decide-run" and event.get("stage") == "request"
    ):
        return None
    if event.get("reason") == decision.REASON_TRANSPORT_UNKNOWN:
        return event
    if (
        event.get("reason") in ("input-incomplete", "budget-exhausted")
        and isinstance(event.get("input_diagnostics"), dict)
        and event["input_diagnostics"].get("stage") == "evidence-preparation"
        and event["input_diagnostics"].get("transport") == "not-sent"
        and isinstance(event["input_diagnostics"].get("issues"), list)
        and all(isinstance(issue, dict) for issue in event["input_diagnostics"]["issues"])
    ):
        return event
    return None


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
        if isinstance(result.get("input_diagnostics"), Mapping):
            event["input_diagnostics"] = result["input_diagnostics"]
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
    logical_id = event["logical_id"]
    if (source == "mw-decide-run" and stage == "request"
            and ("input_diagnostics" in event or event["reason"] == decision.REASON_TRANSPORT_UNKNOWN)
            and isinstance(logical_id, str) and re.fullmatch(r"[0-9a-f-]{36}", logical_id)):
        index = directory / "by-logical-id"
        try:
            index.mkdir(exist_ok=True)
            with (index / logical_id).open("x", encoding="utf-8") as stream:
                stream.write(event_id)
        except OSError:
            # The public receipt remains valid even if the replay lookup cannot be saved.
            pass
    return event_id
