"""Managed-summary accounting: metadata only, full-session dedup, no real HOME."""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import usage


START = "2026-11-09T10:00:00Z"
NOW = datetime(2026, 11, 10, tzinfo=timezone.utc)
TOKENS = {"input": 101, "output": 202, "cacheRead": 303, "cacheWrite": 404}


def summary_entry(
    attempt_id: str = "summary-1",
    raw_usage: dict[str, int] | None = None,
    status: str = "unknown",
    timestamp: str = "2026-11-09T11:00:00Z",
    attempt_started_at: str = START,
) -> dict[str, object]:
    return {
        "type": "custom",
        "timestamp": timestamp,
        "customType": "mw-context-compaction-usage",
        "data": {
            "version": 1,
            "attemptId": attempt_id,
            "attemptStartedAt": attempt_started_at,
            "provider": "fixture",
            "model": "fixture-model",
            "purpose": "summary",
            "status": status,
            "usage": raw_usage,
            "taskId": "task-1",
            "providerRequestStarted": True,
        },
    }


def write_session(root: Path, entries: list[dict[str, object]]) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    file = root / "context-session.jsonl"
    rows = [{"type": "session", "version": 3, "id": "context-session", "timestamp": START, "cwd": str(root)}]
    file.write_text("\n".join(json.dumps(row) for row in [*rows, *entries]) + "\n", encoding="utf-8")
    os.utime(file, (NOW.timestamp(), NOW.timestamp()))
    return file


def test_known_failure_usage_counts_once_and_checkpoint_is_not_a_token_source(tmp_path: Path) -> None:
    entry = summary_entry(raw_usage=TOKENS, status="error")
    file = write_session(tmp_path, [entry, entry, {
        "type": "custom", "timestamp": START, "customType": "mw-context-checkpoint",
        "data": {"usage": {"input": 999999}, "summary": {"goal": "assistant compaction private text"}},
    }])
    scanned = usage.scan_pi_session(file)
    assert scanned["models"] == {"fixture/fixture-model": {
        "requests": 1, "input": 101, "output": 202, "cache_read": 303, "cache_write": 404,
    }}
    assert len(scanned["events"]) == 1


def test_unknown_usage_remains_unknown_and_still_represents_one_attempt(tmp_path: Path) -> None:
    file = write_session(tmp_path, [summary_entry(status="aborted"), summary_entry(status="aborted")])
    scanned = usage.scan_pi_session(file)
    assert scanned["models"]["fixture/fixture-model"] == {
        "requests": 1, "input": None, "output": None, "cache_read": None, "cache_write": None,
    }


def test_queued_summary_cancel_is_evidence_without_an_actual_call(tmp_path: Path) -> None:
    entry = summary_entry(status="aborted")
    data = entry["data"]
    assert isinstance(data, dict)
    data["providerRequestStarted"] = False
    assert usage.scan_pi_session(write_session(tmp_path, [entry]))["events"] == []


def test_late_known_correction_dedups_before_time_window_and_retains_original_attempt_time(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MW_USAGE_DIR", str(tmp_path / "ledger"))
    write_session(tmp_path / "sessions", [
        summary_entry(status="aborted"),
        summary_entry(raw_usage=TOKENS, status="stop", timestamp="2026-11-09T13:00:00Z"),
        # A malformed correction must not move a call into the later window.
        summary_entry(raw_usage=TOKENS, status="stop", timestamp="2026-11-09T13:30:00Z", attempt_started_at="2026-11-09T13:30:00Z"),
        summary_entry(status="unknown", timestamp="2026-11-09T14:00:00Z"),
    ])
    boundary = datetime(2026, 11, 9, 11, tzinfo=timezone.utc)
    earlier = usage.build_report(now=NOW, since=boundary - timedelta(hours=2), until=boundary, pi_root=tmp_path / "sessions", claude_roots=[])
    later = usage.build_report(now=NOW, since=boundary, until=NOW, pi_root=tmp_path / "sessions", claude_roots=[])
    assert earlier["totals"]["calls"] == 1
    assert earlier["totals"]["tokens"] == {"input": 101, "output": 202, "cache_read": 303, "cache_write": 404}
    assert later["totals"]["calls"] == 0
    assert all(value is None for value in later["totals"]["tokens"].values())


@pytest.mark.parametrize("field,value", [
    ("version", True), ("version", 2), ("attemptId", ""), ("provider", None),
    ("model", ""), ("purpose", "business"), ("status", "success"),
    ("attemptStartedAt", "bad-date"), ("taskId", 2),
    ("providerRequestStarted", "false"),
])
def test_invalid_usage_metadata_is_ignored(tmp_path: Path, field: str, value: object) -> None:
    entry = summary_entry(raw_usage=TOKENS, status="stop")
    data = entry["data"]
    assert isinstance(data, dict)
    data[field] = value
    assert usage.scan_pi_session(write_session(tmp_path, [entry]))["events"] == []


@pytest.mark.parametrize("value", [True, -1, 1.5, "100", 9007199254740992, None])
def test_invalid_known_usage_components_are_not_fabricated(tmp_path: Path, value: object) -> None:
    entry = summary_entry(raw_usage=TOKENS, status="stop")
    data = entry["data"]
    assert isinstance(data, dict)
    data["usage"] = {**TOKENS, "cacheRead": value}
    assert usage.scan_pi_session(write_session(tmp_path, [entry]))["events"] == []


def test_partial_known_usage_is_not_accepted(tmp_path: Path) -> None:
    assert usage.scan_pi_session(write_session(tmp_path, [summary_entry(raw_usage={"input": 123}, status="error")]))["events"] == []


def test_no_request_policy_assistant_is_excluded_but_real_errors_and_native_usage_remain(tmp_path: Path) -> None:
    base = {"type": "message", "timestamp": START, "message": {
        "role": "assistant", "provider": "fixture", "model": "fixture-model", "stopReason": "error", "usage": TOKENS,
    }}
    policy = {**base, "message": {**base["message"], "diagnostics": [{"type": "mw_context_policy", "details": {"noProviderRequest": True}}]}}
    physical_error = {**base, "message": {**base["message"], "diagnostics": [{"type": "mw_context_policy", "details": {"noProviderRequest": False}}]}}
    file = write_session(tmp_path, [policy, physical_error,
        {"type": "compaction", "timestamp": START, "usage": TOKENS},
        {"type": "branch_summary", "timestamp": START, "usage": TOKENS},
    ])
    scanned = usage.scan_pi_session(file)
    assert scanned["models"]["fixture/fixture-model"] == {
        "requests": 3, "input": 303, "output": 606, "cache_read": 909, "cache_write": 1212,
    }


def test_typescript_production_session_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Invoked by the TS worker suite with an actual SessionManager/controller file."""
    fixture = os.environ.get("MW_CONTEXT_TS_FIXTURE")
    if not fixture:
        pytest.skip("TS suite invokes this test with a production-persisted session")
    monkeypatch.setenv("MW_USAGE_DIR", str(tmp_path / "ledger"))
    scanned = usage.scan_pi_session(Path(fixture))
    assert sum(row["requests"] for row in scanned["models"].values()) == 2
    assert sum(row["input"] for row in scanned["models"].values()) == 102
    assert sum(row["output"] for row in scanned["models"].values()) == 204
    assert sum(row["cache_read"] for row in scanned["models"].values()) == 306
    assert sum(row["cache_write"] for row in scanned["models"].values()) == 408
    stamps = [usage._parse_iso(event[0]) for event in scanned["events"]]
    assert all(stamp is not None for stamp in stamps)
    report = usage.build_report(
        now=max(stamps) + timedelta(days=1), since=min(stamps) - timedelta(days=1),
        pi_root=Path(fixture).parent, claude_roots=[], limit=0,
    )
    assert report["totals"]["calls"] == 2
    assert report["totals"]["tokens"] == {"input": 102, "output": 204, "cache_read": 306, "cache_write": 408}


def test_typescript_queued_session_fixture(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Invoked from the actual provider/limiter test after cancelling a queued summary."""
    fixture = os.environ.get("MW_CONTEXT_TS_FIXTURE")
    if not fixture:
        pytest.skip("provider integration suite supplies the queued cancellation session")
    monkeypatch.setenv("MW_USAGE_DIR", str(tmp_path / "ledger"))
    file = Path(fixture)
    scanned = usage.scan_pi_session(file)
    assert scanned["events"] == []
    started = usage._parse_iso(scanned["started_at"])
    assert started is not None
    report = usage.build_report(
        now=started + timedelta(days=1), since=started - timedelta(days=1),
        pi_root=file.parent, claude_roots=[], limit=0,
    )
    assert report["totals"]["calls"] == 0
    assert all(value is None for value in report["totals"]["tokens"].values())
