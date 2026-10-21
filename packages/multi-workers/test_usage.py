"""Tests for the usage ledger kernel (mw-usage-monitor T-01).

Every fixture lives under ``tmp_path`` and every path is injected through
``MW_USAGE_DIR`` / ``MW_PI_SESSIONS_DIR`` / ``MW_CLAUDE_PROJECTS_DIR``; no test
reads a real ``HOME`` session tree.
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import threading
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import usage  # noqa: E402

NOW = datetime.now(timezone.utc).replace(microsecond=0)
SINCE = NOW - timedelta(days=7)
PI_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]*[A-Za-z0-9])?$")


def _at(minutes_ago: float) -> str:
    """ISO-Z timestamp ``minutes_ago`` minutes before NOW (inside the window)."""
    return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _usage(input_tokens: int, output_tokens: int, cache_read: int, cache_write: int) -> dict:
    return {
        "input": input_tokens,
        "output": output_tokens,
        "cacheRead": cache_read,
        "cacheWrite": cache_write,
        "totalTokens": input_tokens + output_tokens + cache_read + cache_write,
    }


def _pi_header(session_id: str, timestamp: str, cwd: str = "H:/git/ProjA") -> dict:
    return {"type": "session", "version": 3, "id": session_id, "timestamp": timestamp, "cwd": cwd}


def _pi_assistant(
    timestamp: str,
    model: str = "glm-5.3-flashx",
    provider: str = "timi",
    raw_usage: dict | None = None,
) -> dict:
    return {
        "type": "message",
        "id": f"msg-{timestamp}",
        "parentId": None,
        "timestamp": timestamp,
        "message": {
            "role": "assistant",
            "content": [{"type": "text", "text": "not read"}],
            "api": "openai-responses",
            "provider": provider,
            "model": model,
            "usage": raw_usage if raw_usage is not None else _usage(1, 1, 1, 1),
            "stopReason": "stop",
            "timestamp": 0,
        },
    }


def _pi_compaction(timestamp: str, raw_usage: dict) -> dict:
    return {
        "type": "compaction",
        "id": f"cmp-{timestamp}",
        "parentId": None,
        "timestamp": timestamp,
        "summary": "not read",
        "firstKeptEntryId": "x",
        "tokensBefore": 1,
        "usage": raw_usage,
    }


def _pi_user(timestamp: str) -> dict:
    return {
        "type": "message",
        "id": f"usr-{timestamp}",
        "parentId": None,
        "timestamp": timestamp,
        "message": {"role": "user", "content": "not read", "timestamp": 0},
    }


def _write_lines(path: pathlib.Path, rows: list[dict], tail: str = "") -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        if tail:
            handle.write(tail)
    return path


def _write_pi_session(
    root: pathlib.Path,
    filename: str,
    rows: list[dict],
    tail: str = "",
    mtime: float | None = None,
) -> pathlib.Path:
    path = _write_lines(pathlib.Path(root) / "H--git-ProjA" / filename, rows, tail)
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


def _claude_line(
    session_id: str,
    message_id: str,
    timestamp: str,
    raw_usage: dict,
    model: str = "claude-opus-4-8",
    cwd: str = "H:/git/ProjB",
) -> dict:
    return {
        "type": "assistant",
        "sessionId": session_id,
        "cwd": cwd,
        "timestamp": timestamp,
        "isSidechain": False,
        "message": {"id": message_id, "model": model, "usage": raw_usage},
    }


# ── 1. usage_dir env priority ────────────────────────────────────────────────


def test_usage_dir_env_priority() -> None:
    assert usage.usage_dir({"MW_USAGE_DIR": "/tmp/ledger", "USERPROFILE": "/u", "HOME": "/h"}) == (
        pathlib.Path("/tmp/ledger")
    )
    assert usage.usage_dir({"USERPROFILE": "/u", "HOME": "/h"}) == (
        pathlib.Path("/u") / ".mw" / "usage"
    )
    assert usage.usage_dir({"HOME": "/h"}) == pathlib.Path("/h") / ".mw" / "usage"
    fallback = usage.usage_dir({})
    assert fallback.name == "usage" and fallback.parent.name == ".mw"


def test_ledger_paths_follow_usage_dir(tmp_path, monkeypatch) -> None:
    target = tmp_path / "machine-usage"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    assert usage.usage_dir() == target
    assert usage.ledger_path() == target / "runs.jsonl"
    assert usage.lock_path() == target / "runs.jsonl.lock"
    # Reading the paths must not create the directory (write side does that).
    assert not target.exists()


def test_session_root_resolution(tmp_path) -> None:
    assert usage.pi_sessions_dir({"MW_PI_SESSIONS_DIR": str(tmp_path / "pi")}) == tmp_path / "pi"
    assert usage.pi_sessions_dir({"PI_CODING_AGENT_SESSION_DIR": str(tmp_path / "sd")}) == (
        tmp_path / "sd"
    )
    assert usage.pi_sessions_dir({"PI_CODING_AGENT_DIR": str(tmp_path / "agent")}) == (
        tmp_path / "agent" / "sessions"
    )
    assert usage.claude_projects_dir({"MW_CLAUDE_PROJECTS_DIR": str(tmp_path / "c")}) == (
        tmp_path / "c"
    )
    assert usage.claude_projects_dir({"CLAUDE_CONFIG_DIR": str(tmp_path / "cfg")}) == (
        tmp_path / "cfg" / "projects"
    )


# ── 2. new_session_id ────────────────────────────────────────────────────────


def test_new_session_id_slugs_and_validates() -> None:
    assert usage.new_session_id("mw-usage-monitor", 43712, 7) == "mw-mw-usage-monitor-43712-7"
    assert usage.new_session_id("My Key/With Spaces", 12, 3) == "mw-my-key-with-spaces-12-3"
    # unrelated keys never collide: pid + monotonically increasing seq
    assert usage.new_session_id("k", 100, 1) != usage.new_session_id("k", 100, 2)
    assert usage.new_session_id("k", 100, 1) != usage.new_session_id("k", 101, 1)

    long_id = usage.new_session_id("A" * 200, 1, 1)
    assert PI_SESSION_ID_RE.match(long_id)
    assert long_id.startswith("mw-aaa") and long_id.endswith("-1-1")

    parsed = usage.new_session_id("mw-usage-monitor", 99, 4)
    assert PI_SESSION_ID_RE.match(parsed)
    assert usage._key_from_session_id(parsed) == "mw-usage-monitor"


def test_new_session_id_rejects_unslugabble_key() -> None:
    with pytest.raises(ValueError):
        usage.new_session_id("", 1, 1)
    with pytest.raises(ValueError):
        usage.new_session_id("!!!", 1, 1)
    with pytest.raises(ValueError):
        usage.new_session_id("   ", 1, 1)


# ── 3. append_event concurrency / fail-soft ──────────────────────────────────


def test_append_event_concurrent_writes_stay_parseable(tmp_path, monkeypatch) -> None:
    target = tmp_path / "usage"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))

    def writer(thread_index: int) -> None:
        for index in range(50):
            assert usage.append_event(
                {
                    "event": "start",
                    "run_id": f"run-{thread_index}-{index}",
                    "ts": _at(1),
                    "source": "worker",
                    "padding": "x" * 80,
                }
            )

    threads = [threading.Thread(target=writer, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    raw = (target / "runs.jsonl").read_bytes()
    assert raw.count(b"\n") == 200
    assert b"\r" not in raw  # newline="\n": no CRLF doubling
    lines = raw.decode("utf-8").splitlines()
    assert len(lines) == 200
    records = [json.loads(line) for line in lines]  # every line is intact JSON
    assert len({record["run_id"] for record in records}) == 200
    assert not (target / "runs.jsonl.lock").exists()  # lock always released


def test_append_event_is_fail_soft(tmp_path, monkeypatch, capsys) -> None:
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    monkeypatch.setenv("MW_USAGE_DIR", str(blocker / "nested"))

    assert usage.append_event({"event": "start", "run_id": "r", "ts": _at(1)}) is False
    captured = capsys.readouterr()
    assert "[mw usage]" in captured.err


# ── 4. parse_since ───────────────────────────────────────────────────────────


def test_parse_since_forms() -> None:
    base = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    assert usage.parse_since("7d", base) == base - timedelta(days=7)
    assert usage.parse_since("24h", base) == base - timedelta(hours=24)
    assert usage.parse_since("30m", base) == base - timedelta(minutes=30)
    day = usage.parse_since("2026-10-12", base)
    assert day.tzinfo is not None
    assert day.astimezone().strftime("%Y-%m-%d") == "2026-10-12"


def test_parse_since_rejects_garbage() -> None:
    for bad in ("", "7", "abc", "7x", "2026-13-01", "2026/10/12", "-3d"):
        with pytest.raises(ValueError):
            usage.parse_since(bad)


# ── 5. percentile ────────────────────────────────────────────────────────────


def test_percentile_requires_five_samples() -> None:
    assert usage._percentile([10, 20, 30, 40], 50) is None
    assert usage._percentile([], 90) is None
    assert usage._percentile([10, 20, 30, 40, 50], 50) == 30
    assert usage._percentile([10, 20, 30, 40, 60], 90) == pytest.approx(52.0)
    assert usage._percentile([60, 120, 180, 240, 300, 360], 50) == pytest.approx(210.0)
    assert usage._percentile([60, 120, 180, 240, 300, 360], 90) == pytest.approx(330.0)


# ── 6. scan_pi_session ───────────────────────────────────────────────────────


def test_scan_pi_session_sums_assistant_compaction_and_survives_torn_tail(tmp_path) -> None:
    root = tmp_path / "pi"
    session_id = "mw-fixture-key-1-1"
    rows = [
        _pi_header(session_id, _at(300)),
        _pi_user(_at(299)),
        _pi_assistant(_at(298), raw_usage=_usage(1000, 200, 5000, 50)),
        # assistant message without usage: not a billable response row
        {
            "type": "message",
            "id": "m-nousage",
            "timestamp": _at(297),
            "message": {"role": "assistant", "content": [], "provider": "timi", "model": "x"},
        },
        _pi_assistant(_at(296), model="deepseek-v4.1-flash", raw_usage=_usage(2000, 300, 0, 10)),
        _pi_compaction(_at(295), _usage(100, 20, 0, 0)),
    ]
    path = _write_pi_session(
        root,
        "2026-10-19T10-00-00-000Z_mw-fixture-key-1-1.jsonl",
        rows,
        tail='{"type":"message","message":{"role":"assistant","usa',
    )

    session = usage.scan_pi_session(path)

    assert session["session_id"] == session_id
    assert session["cwd"] == "H:/git/ProjA"
    assert session["started_at"] == _at(300)
    assert session["ended_at"] == _at(295)  # torn tail never becomes the end
    # compaction is attributed to the model that produced it (last assistant)
    assert session["models"]["timi/deepseek-v4.1-flash"] == {
        "input": 2100,
        "output": 320,
        "cache_read": 0,
        "cache_write": 10,
        "requests": 2,
    }
    assert session["models"]["timi/glm-5.3-flashx"] == {
        "input": 1000,
        "output": 200,
        "cache_read": 5000,
        "cache_write": 50,
        "requests": 1,
    }
    assert len(session["events"]) == 3  # 2 assistant rows with usage + 1 compaction
    assert session["events"][0][1] == "timi/glm-5.3-flashx"
    assert session["events"][0][2] == {
        "input": 1000,
        "output": 200,
        "cache_read": 5000,
        "cache_write": 50,
    }


def test_scan_pi_session_header_id_wins_over_filename(tmp_path) -> None:
    root = tmp_path / "pi"
    rows = [_pi_header("mw-real-id-9-1", _at(10)), _pi_assistant(_at(9))]
    path = _write_pi_session(root, "2026-10-19T10-00-00-000Z_filename-id.jsonl", rows)
    assert usage.scan_pi_session(path)["session_id"] == "mw-real-id-9-1"

    # No usable header: fall back to the <ts>_<id>.jsonl filename.
    headerless = _write_pi_session(
        root,
        "2026-10-19T11-00-00-000Z_filename-only-id.jsonl",
        [_pi_assistant(_at(8))],
    )
    session = usage.scan_pi_session(headerless)
    assert session["session_id"] == "filename-only-id"
    assert session["started_at"] is None
    assert session["ended_at"] == _at(8)


def test_scan_pi_session_keeps_unknown_tokens_null(tmp_path) -> None:
    root = tmp_path / "pi"
    rows = [
        _pi_header("mw-null-1-1", _at(10)),
        # only input/output reported: cache components stay unknown, not 0
        _pi_assistant(_at(9), raw_usage={"input": 7, "output": 3}),
    ]
    path = _write_pi_session(root, "2026-10-19T10-00-00-000Z_mw-null-1-1.jsonl", rows)
    models = usage.scan_pi_session(path)["models"]
    assert models["timi/glm-5.3-flashx"]["input"] == 7
    assert models["timi/glm-5.3-flashx"]["cache_read"] is None
    assert models["timi/glm-5.3-flashx"]["cache_write"] is None


# ── 7. iter_session_files ────────────────────────────────────────────────────


def test_iter_session_files_uses_mtime_then_header(tmp_path) -> None:
    root = tmp_path / "pi"
    old_mtime = (SINCE - timedelta(days=30)).timestamp()
    _write_pi_session(
        root,
        "2026-01-01T00-00-00-000Z_old-session.jsonl",
        [_pi_header("old-session", "2026-01-01T00:00:00Z"), _pi_assistant("2026-01-01T00:01:00Z")],
        mtime=old_mtime,
    )
    fresh = _write_pi_session(
        root,
        "2026-10-19T10-00-00-000Z_fresh-session.jsonl",
        [_pi_header("fresh-session", _at(30)), _pi_assistant(_at(29))],
    )
    # A long-lived session whose header predates the window but was written
    # recently must survive the coarse filter (PM windows live for weeks).
    long_lived = _write_pi_session(
        root,
        "2026-09-01T00-00-00-000Z_long-session.jsonl",
        [_pi_header("long-session", "2026-09-01T00:00:00Z"), _pi_assistant(_at(20))],
    )
    garbage = _write_pi_session(
        root,
        "2026-10-19T11-00-00-000Z_not-a-session.jsonl",
        [{"type": "message", "timestamp": _at(10)}],
    )

    found = set(usage.iter_session_files(root, SINCE))
    assert fresh in found
    assert long_lived in found
    assert garbage not in found
    assert len(found) == 2


# ── 8. scan_claude_session ───────────────────────────────────────────────────


CLAUDE_SESSION = "0fd83ff3-1a2b-4c5d-8e9f-001122334455"


def _claude_fixture(tmp_path) -> pathlib.Path:
    root = tmp_path / "claude"
    project = root / "H--git-ProjB"
    duplicated = {"input_tokens": 2, "output_tokens": 100, "cache_read_input_tokens": 5000}
    # Same message.id written three times, exactly like claude does.
    _write_lines(
        project / f"{CLAUDE_SESSION}.jsonl",
        [
            _claude_line(CLAUDE_SESSION, "msg-dup", _at(30), duplicated),
            _claude_line(CLAUDE_SESSION, "msg-dup", _at(30), duplicated),
            _claude_line(CLAUDE_SESSION, "msg-dup", _at(30), duplicated),
            _claude_line(
                CLAUDE_SESSION,
                "msg-distinct",
                _at(29),
                {
                    "input_tokens": 3,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 1000,
                    "cache_creation_input_tokens": 700,
                },
            ),
        ],
    )
    _write_lines(
        project / CLAUDE_SESSION / "subagents" / "agent-1.jsonl",
        [
            _claude_line(
                CLAUDE_SESSION,
                "msg-subagent",
                _at(28),
                {
                    "input_tokens": 1,
                    "output_tokens": 10,
                    "cache_read_input_tokens": 100,
                    "cache_creation_input_tokens": 5,
                },
            )
        ],
    )
    return root


def test_scan_claude_session_dedupes_by_message_id_and_merges_subagents(tmp_path) -> None:
    root = _claude_fixture(tmp_path)
    session = usage.scan_claude_session(CLAUDE_SESSION, [root])
    assert session is not None
    assert session["session_id"] == CLAUDE_SESSION
    assert session["cwd"] == "H:/git/ProjB"
    model = session["models"]["claude/claude-opus-4-8"]
    # 3 duplicate rows count once; the distinct message and the subagent add up.
    assert model["requests"] == 3
    assert model["input"] == 2 + 3 + 1
    assert model["output"] == 100 + 50 + 10
    assert model["cache_read"] == 5000 + 1000 + 100
    assert model["cache_write"] == 700 + 5  # missing cache_creation is not 0
    assert len(session["events"]) == 3
    # A per-cwd project dir works as a root too.
    assert usage.scan_claude_session(CLAUDE_SESSION, [root / "H--git-ProjB"]) is not None


def test_scan_claude_session_missing_returns_none(tmp_path) -> None:
    assert usage.scan_claude_session("no-such-uuid", [tmp_path / "claude"]) is None
    assert usage.scan_claude_session("", [tmp_path / "claude"]) is None


# ── 9. load_runs ─────────────────────────────────────────────────────────────


def _start(run_id: str, **overrides) -> dict:
    record = {
        "event": "start",
        "run_id": run_id,
        "ts": _at(400),
        "source": "worker",
        "project": "H:/git/ProjA",
        "key": "alpha",
        "task_key": "um-t01",
        "type": "coding",
        "role": "coding",
        "cli": "pi",
        "attribution": "exact",
        "session_id": f"mw-alpha-1-{run_id}",
        "model": "timi/glm-5.3-flashx",
        "model_source": "config:coding",
        "pid": 100,
        "cwd": "H:/git/ProjA",
    }
    record.update(overrides)
    return record


def _end(run_id: str, wall_s: float | None = 300.0, exit_code: int | None = 0, **overrides) -> dict:
    record = {
        "event": "end",
        "run_id": run_id,
        "ts": _at(390),
        "exit": exit_code,
        "wall_s": wall_s,
        "reconciled": False,
        "status": "done",
    }
    record.update(overrides)
    return record


def _write_ledger(path: pathlib.Path, records: list[dict], extra_lines: list[str] = ()) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
        for line in extra_lines:
            handle.write(line + "\n")


def test_load_runs_pairs_events_and_counts_bad_lines(tmp_path, monkeypatch) -> None:
    target = tmp_path / "usage"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    _write_ledger(
        target / "runs.jsonl",
        [
            _start("r1"),
            _end("r1", wall_s=12.5),
            _start("r2", key="beta"),
            {"event": "spawn_failed", "run_id": "r3", "ts": _at(300), "source": "worker",
             "key": "alpha", "cli": "pi"},
        ],
        extra_lines=['{"event":"start"', "[]", '{"run_id":"x"}'],
    )

    runs, meta = usage.load_runs(SINCE, {})

    assert meta["events"] == 4
    assert meta["bad_lines"] == 3
    assert meta["open_runs"] == 1
    assert meta["path"] == str(target / "runs.jsonl")
    by_id = {run["run_id"]: run for run in runs}
    assert by_id["r1"]["wall_s"] == pytest.approx(12.5)
    assert by_id["r1"]["open_run"] is False
    assert by_id["r1"]["spawned"] is True
    assert by_id["r2"]["open_run"] is True
    assert by_id["r2"]["wall_s"] is None  # never 0 for a run without end
    assert by_id["r3"]["spawned"] is False
    assert by_id["r3"]["status"] == "spawn_failed"

    only_beta, _ = usage.load_runs(SINCE, {"key": "beta"})
    assert [run["run_id"] for run in only_beta] == ["r2"]


def test_load_runs_missing_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MW_USAGE_DIR", str(tmp_path / "nothing"))
    runs, meta = usage.load_runs(SINCE, {})
    assert runs == []
    assert meta == {
        "events": 0,
        "bad_lines": 0,
        "open_runs": 0,
        "path": str(tmp_path / "nothing" / "runs.jsonl"),
    }


# ── 10. build_report ─────────────────────────────────────────────────────────


def _rich_fixture(tmp_path, monkeypatch):
    """pi worker (2 models) + open run + claude worker + codex worker + PM window."""
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    claude_root = tmp_path / "claude"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    monkeypatch.setenv("MW_CLAUDE_PROJECTS_DIR", str(claude_root))

    _write_ledger(
        target / "runs.jsonl",
        [
            _start("r1", session_id="mw-alpha-100-1", ts=_at(310)),
            _end("r1", wall_s=300.0, exit_code=0, ts=_at(300)),
            _start("r2", key="beta", type="review", session_id="mw-beta-101-1",
                   model="timi/deepseek-v4.1-flash", ts=_at(210)),
            _end("r2", wall_s=120.0, ts=_at(200)),
            _start("r3", key="alpha", type="research", cli="claude", project="H:/git/ProjB",
                   session_id=CLAUDE_SESSION, model="claude/claude-opus-4-8", ts=_at(110)),
            _end("r3", wall_s=60.0, ts=_at(100)),
            _start("r4", key="alpha", type="coding", cli="codex", project="H:/git/ProjB",
                   session_id=None, model="gpt-5-codex", attribution="unknown_cli", ts=_at(90)),
            _end("r4", wall_s=90.0, ts=_at(80)),
            _start("r5", key="beta", type="coding", project="H:/git/ProjB",
                   session_id="mw-beta-102-1", model="timi/glm-5.3-flashx", ts=_at(6)),
        ],
    )

    _write_pi_session(
        pi_root,
        "2026-10-19T10-00-00-000Z_mw-alpha-100-1.jsonl",
        [
            _pi_header("mw-alpha-100-1", _at(305)),
            _pi_assistant(_at(304), raw_usage=_usage(600_000, 150_000, 6_000_000, 20_000)),
            _pi_assistant(_at(303), raw_usage=_usage(600_000, 160_000, 5_400_000, 22_000)),
        ],
    )
    _write_pi_session(
        pi_root,
        "2026-10-19T10-01-00-000Z_mw-beta-101-1.jsonl",
        [
            _pi_header("mw-beta-101-1", _at(205), cwd="H:/git/ProjA"),
            _pi_assistant(
                _at(204),
                model="deepseek-v4.1-flash",
                raw_usage=_usage(620_000, 90_000, 2_100_000, 8_000),
            ),
            _pi_compaction(_at(203), _usage(1_000, 100, 0, 0)),
        ],
    )
    _write_pi_session(
        pi_root,
        "2026-10-19T10-02-00-000Z_mw-beta-102-1.jsonl",
        [
            _pi_header("mw-beta-102-1", _at(7), cwd="H:/git/ProjB"),
            _pi_assistant(_at(6), raw_usage=_usage(1_000, 100, 0, 0)),
        ],
    )
    # PM window session: no mw- prefix, no ledger row.
    _write_pi_session(
        pi_root,
        "2026-10-19T09-00-00-000Z_01JPMWINDOW0001.jsonl",
        [
            _pi_header("01JPMWINDOW0001", _at(110), cwd="H:/git/ProjC"),
            _pi_assistant(_at(100), raw_usage=_usage(1_000, 100, 0, 0)),
            _pi_user(_at(98)),
        ],
    )

    duplicated = {"input_tokens": 2, "output_tokens": 100, "cache_read_input_tokens": 5000}
    _write_lines(
        claude_root / "H--git-ProjB" / f"{CLAUDE_SESSION}.jsonl",
        [
            _claude_line(CLAUDE_SESSION, "msg-dup", _at(105), duplicated),
            _claude_line(CLAUDE_SESSION, "msg-dup", _at(105), duplicated),
            _claude_line(CLAUDE_SESSION, "msg-dup", _at(105), duplicated),
            _claude_line(
                CLAUDE_SESSION,
                "msg-distinct",
                _at(104),
                {
                    "input_tokens": 3,
                    "output_tokens": 50,
                    "cache_read_input_tokens": 1000,
                    "cache_creation_input_tokens": 700,
                },
            ),
        ],
    )
    _write_lines(
        claude_root / "H--git-ProjB" / CLAUDE_SESSION / "subagents" / "agent-1.jsonl",
        [
            _claude_line(
                CLAUDE_SESSION,
                "msg-subagent",
                _at(103),
                {
                    "input_tokens": 1,
                    "output_tokens": 10,
                    "cache_read_input_tokens": 100,
                    "cache_creation_input_tokens": 5,
                },
            )
        ],
    )
    return target, pi_root, claude_root


def test_build_report_groups_coverage_and_filters(tmp_path, monkeypatch) -> None:
    _rich_fixture(tmp_path, monkeypatch)

    report = usage.build_report(NOW, SINCE, {})

    assert report["generated_at"] == NOW.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert report["since"] == SINCE.strftime("%Y-%m-%dT%H:%M:%SZ")
    assert report["window"] == "7d"
    assert report["ledger"]["events"] == 9
    assert report["ledger"]["bad_lines"] == 0
    assert report["ledger"]["open_runs"] == 1
    assert report["totals"]["calls"] == 9
    assert report["totals"]["runs"] == 6  # 5 spawned ledger runs + 1 PM session
    assert report["totals"]["tokens"] == {
        "input": 1_202_000 + 621_000 + 6,
        "output": 310_200 + 90_100 + 160,
        "cache_read": 11_400_000 + 2_100_000 + 6_100,
        "cache_write": 42_000 + 8_000 + 705,
    }
    assert report["sources"] == {"worker": 5, "pm": 1}
    assert report["coverage"] == [
        {"cli": "pi", "runs": 4, "attribution": "exact"},  # 3 worker + 1 PM
        {"cli": "claude", "runs": 1, "attribution": "exact"},
        {"cli": "codex", "runs": 1, "attribution": "unknown_cli"},
    ]

    model_rows = {row["name"]: row for row in report["groups"]["model"]}
    assert set(model_rows) == {
        "timi/glm-5.3-flashx",
        "timi/deepseek-v4.1-flash",
        "claude/claude-opus-4-8",
    }  # codex contributes a run but never a token group
    assert [row["name"] for row in report["groups"]["model"]] == [
        "timi/glm-5.3-flashx",  # calls 4
        "claude/claude-opus-4-8",  # calls 3
        "timi/deepseek-v4.1-flash",  # calls 2
    ]
    glm = model_rows["timi/glm-5.3-flashx"]
    assert glm["calls"] == 4
    assert glm["runs"] == 3  # r1, open r5, PM window
    assert glm["tokens"] == {
        "input": 1_202_000,
        "output": 310_200,
        "cache_read": 11_400_000,
        "cache_write": 42_000,
    }
    # wall samples: only the run wall (r1, 300 s). The PM window span (120 s)
    # is a different source and must never join a run percentile (T-06); the
    # open run has no wall at all.
    assert glm["n"] == 1
    assert glm["wall_p50"] is None and glm["wall_p90"] is None  # n < 5 renders "-"
    assert glm["wall_kind"] == "none"  # no percentile -> no source claimed

    deepseek = model_rows["timi/deepseek-v4.1-flash"]
    assert deepseek["calls"] == 2  # assistant + compaction
    assert deepseek["tokens"]["input"] == 621_000

    type_rows = {row["name"]: row for row in report["groups"]["type"]}
    assert set(type_rows) == {"coding", "review", "research", "pm"}
    assert type_rows["coding"]["calls"] == 3  # codex run is unknown_cli -> no tokens
    assert type_rows["research"]["calls"] == 3
    assert type_rows["pm"]["calls"] == 1

    key_rows = {row["name"]: row for row in report["groups"]["key"]}
    assert set(key_rows) == {"alpha", "beta", "pm"}
    assert key_rows["alpha"]["calls"] == 5  # pi worker 2 + claude 3
    assert key_rows["beta"]["calls"] == 3

    project_rows = {row["name"]: row for row in report["groups"]["project"]}
    assert set(project_rows) == {"ProjA", "ProjB", "ProjC"}
    assert project_rows["ProjA"]["calls"] == 4
    assert project_rows["ProjB"]["calls"] == 4  # claude 3 + open pi run 1
    assert project_rows["ProjC"]["calls"] == 1

    # -- filters ----------------------------------------------------------
    by_key = usage.build_report(NOW, SINCE, {"key": "alpha"})
    assert by_key["totals"]["calls"] == 5
    assert {row["name"] for row in by_key["groups"]["model"]} == {
        "timi/glm-5.3-flashx",
        "claude/claude-opus-4-8",
    }

    by_type = usage.build_report(NOW, SINCE, {"type": "review"})
    assert by_type["totals"]["calls"] == 2
    assert [row["name"] for row in by_type["groups"]["model"]] == ["timi/deepseek-v4.1-flash"]

    by_project = usage.build_report(NOW, SINCE, {"project": "ProjA"})
    assert by_project["totals"]["calls"] == 4
    assert [row["name"] for row in by_project["groups"]["project"]] == ["ProjA"]
    # TS `runMwCliRaw` appends the control root as a full path, not a basename.
    by_project_path = usage.build_report(NOW, SINCE, {"project": "H:/git/ProjA"})
    assert by_project_path["totals"]["calls"] == 4

    by_source = usage.build_report(NOW, SINCE, {"source": "pm"})
    assert by_source["totals"]["calls"] == 1
    assert by_source["totals"]["runs"] == 1
    assert by_source["sources"] == {"worker": 0, "pm": 1}
    assert [row["name"] for row in by_source["groups"]["model"]] == ["timi/glm-5.3-flashx"]

    by_model = usage.build_report(NOW, SINCE, {"model": "claude"})
    assert by_model["totals"]["calls"] == 3
    assert [row["name"] for row in by_model["groups"]["model"]] == ["claude/claude-opus-4-8"]
    assert by_model["coverage"] == [{"cli": "claude", "runs": 1, "attribution": "exact"}]

    # -- contract: no money keys anywhere ---------------------------------
    def walk(node) -> list[str]:
        keys: list[str] = []
        if isinstance(node, dict):
            for key, value in node.items():
                keys.append(str(key))
                keys.extend(walk(value))
        elif isinstance(node, list):
            for item in node:
                keys.extend(walk(item))
        return keys

    lowered = [key.lower() for key in walk(report)]
    for forbidden in ("cost", "usd", "amount", "price", "money", "total_usd"):
        assert not any(forbidden in key for key in lowered)


def test_build_report_wall_percentiles_with_enough_samples(tmp_path, monkeypatch) -> None:
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))

    walls = [60.0, 120.0, 180.0, 240.0, 300.0, 360.0]
    ledger = []
    for index, wall in enumerate(walls, start=1):
        run_id = f"w{index}"
        session_id = f"mw-k-1-{index}"
        ledger.append(_start(run_id, key="k", type="coding", session_id=session_id, ts=_at(400)))
        ledger.append(_end(run_id, wall_s=wall, ts=_at(390)))
        _write_pi_session(
            pi_root,
            f"2026-10-19T10-0{index}-00-000Z_{session_id}.jsonl",
            [
                _pi_header(session_id, _at(60 + index)),
                _pi_assistant(_at(60 + index), raw_usage=_usage(10, 10, 10, 10)),
            ],
        )
    _write_ledger(target / "runs.jsonl", ledger)

    report = usage.build_report(NOW, SINCE, {"type": "coding"})
    row = report["groups"]["type"][0]
    assert row["n"] == 6
    assert row["runs"] == 6
    assert row["wall_p50"] == pytest.approx(210.0)
    assert row["wall_p90"] == pytest.approx(330.0)


def test_build_report_unknown_tokens_stay_null(tmp_path, monkeypatch) -> None:
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    _write_ledger(
        target / "runs.jsonl",
        [
            _start("r1", key="alpha", session_id="mw-alpha-1-1", type="coding", ts=_at(30)),
            _end("r1", wall_s=5.0, ts=_at(20)),
        ],
    )
    _write_pi_session(
        pi_root,
        "2026-10-19T10-00-00-000Z_mw-alpha-1-1.jsonl",
        [
            _pi_header("mw-alpha-1-1", _at(29)),
            _pi_assistant(_at(28), raw_usage={"input": 7, "output": 3}),
        ],
    )

    report = usage.build_report(NOW, SINCE, {})
    row = report["groups"]["model"][0]
    assert row["tokens"]["input"] == 7
    assert row["tokens"]["cache_read"] is None
    assert row["tokens"]["cache_write"] is None
    assert report["totals"]["tokens"]["cache_write"] is None  # null, never 0


def test_build_report_empty_window(tmp_path, monkeypatch) -> None:
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    _write_ledger(target / "runs.jsonl", [_start("r1", ts=_at(30)), _end("r1", wall_s=5.0)])

    report = usage.build_report(NOW, NOW + timedelta(seconds=1), {})

    assert report["totals"]["calls"] == 0
    assert report["totals"]["runs"] == 0
    assert report["totals"]["tokens"] == {
        "input": None,
        "output": None,
        "cache_read": None,
        "cache_write": None,
    }
    assert all(rows == [] for rows in report["groups"].values())
    assert report["coverage"] == []
    text = usage.format_report_text(report)
    assert "no usage in window" in text
    assert text.rstrip().endswith("coverage: none")


# ── 11. format_report_text ──────────────────────────────────────────────────


def test_format_report_text_matches_fixture(tmp_path, monkeypatch) -> None:
    fixed_now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    fixed_since = fixed_now - timedelta(days=7)
    stamp = fixed_now.timestamp()
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    monkeypatch.setenv("MW_CLAUDE_PROJECTS_DIR", str(tmp_path / "claude"))

    def at(minutes: int) -> str:
        return (fixed_now - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

    _write_ledger(
        target / "runs.jsonl",
        [
            _start("r1", key="alpha", type="coding", session_id="mw-alpha-100-1", ts=at(310)),
            _end("r1", wall_s=300.0, ts=at(300)),
            _start("r2", key="alpha", type="coding", cli="codex", session_id=None,
                   model="gpt-5-codex", attribution="unknown_cli", ts=at(90)),
            _end("r2", wall_s=90.0, ts=at(80)),
        ],
    )
    _write_pi_session(
        pi_root,
        "2026-10-19T10-00-00-000Z_mw-alpha-100-1.jsonl",
        [
            _pi_header("mw-alpha-100-1", at(305)),
            _pi_assistant(at(304), raw_usage=_usage(600_000, 150_000, 6_000_000, 20_000)),
            _pi_assistant(at(303), raw_usage=_usage(600_000, 160_000, 5_400_000, 22_000)),
        ],
        mtime=stamp,
    )

    report = usage.build_report(fixed_now, fixed_since, {"window": "7d"})
    text = usage.format_report_text(report)

    expected_lines = [
        "",
        "by model",
            "  timi/glm-5.3-flashx      calls 2     in 1.2M   out 310k   cacheR 11.4M"
            "   cacheW 42k    wall p50 -      p90 -      n 1",
            "",
            "by type",
            "  coding                   calls 2     in 1.2M   out 310k   cacheR 11.4M"
            "   cacheW 42k    wall p50 -      p90 -      n 1",
            "",
            "by key",
            "  alpha                    calls 2     in 1.2M   out 310k   cacheR 11.4M"
            "   cacheW 42k    wall p50 -      p90 -      n 1",
            "",
            "by project",
            "  ProjA                    calls 2     in 1.2M   out 310k   cacheR 11.4M"
            "   cacheW 42k    wall p50 -      p90 -      n 1",
            "",
            "coverage: pi 1 runs (exact) · codex 1 (未统计)",
    ]
    # First line now states the half-open window (R7); timestamps render in
    # local time, so the exact digits are environment dependent by design.
    text_lines = text.splitlines()
    assert text_lines[0].startswith(f"usage {usage._format_local_stamp(report['since'])} → ")
    assert text_lines[0].endswith("(7d) · ledger 4 events · runs 2 (worker 2 / pm 0)")
    assert text_lines[1:] == expected_lines


def test_format_report_text_marks_missing_ledger(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("MW_USAGE_DIR", str(tmp_path / "empty"))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(tmp_path / "pi"))
    report = usage.build_report(NOW, SINCE, {})
    text = usage.format_report_text(report)
    assert "no ledger yet" in text
    assert "no usage in window" in text


# ── 12. wall_kind: worker run walls vs PM session spans never mix (T-06) ─────

STAMP = "%Y-%m-%dT%H:%M:%SZ"
FOOTNOTE = "* = PM 会话跨度（header→末条），非 worker 墙钟"


def _pm_session(
    pi_root: pathlib.Path,
    session_id: str,
    span_s: float,
    ended_minutes_ago: float = 100.0,
) -> pathlib.Path:
    """A PM window session: no ``mw-`` id, no ledger row, span ``span_s`` seconds."""
    ended = NOW - timedelta(minutes=ended_minutes_ago)
    started = ended - timedelta(seconds=span_s)
    return _write_pi_session(
        pi_root,
        f"{started.strftime('%Y-%m-%dT%H-%M-%S')}-000Z_{session_id}.jsonl",
        [
            _pi_header(session_id, started.strftime(STAMP)),
            _pi_assistant(ended.strftime(STAMP)),
        ],
    )


def _worker_session(
    pi_root: pathlib.Path,
    session_id: str,
    index: int,
    ended_minutes_ago: float,
    span_s: float,
) -> pathlib.Path:
    """A worker session whose own header->last entry span is ``span_s`` seconds."""
    ended = NOW - timedelta(minutes=ended_minutes_ago)
    started = ended - timedelta(seconds=span_s)
    return _write_pi_session(
        pi_root,
        f"2026-10-19T10-{index:02d}-00-000Z_{session_id}.jsonl",
        [
            _pi_header(session_id, started.strftime(STAMP)),
            _pi_assistant(ended.strftime(STAMP)),
        ],
    )


def test_build_report_wall_kind_mixed_group_never_mixes_sources(tmp_path, monkeypatch) -> None:
    """5 run walls (100 s) next to 3 PM windows (100000 s): only runs count."""
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))

    ledger = []
    for index in range(1, 6):
        session_id = f"mw-k-1-{index}"
        ledger.append(
            _start(f"m{index}", key="k", type="coding", session_id=session_id, ts=_at(400))
        )
        ledger.append(_end(f"m{index}", wall_s=100.0, ts=_at(390)))
        # The worker session itself spans 200_000 s; only the ledger
        # spawn -> reap wall may count for a run.
        _worker_session(pi_root, session_id, index, ended_minutes_ago=200, span_s=200_000)
    for index in range(1, 4):
        _pm_session(pi_root, f"01JPMWINDOW{index:04d}", span_s=100_000.0)
    _write_ledger(target / "runs.jsonl", ledger)

    report = usage.build_report(NOW, SINCE, {})
    row = report["groups"]["model"][0]

    assert row["runs"] == 8  # 5 worker runs + 3 PM windows share the model group
    assert row["wall_kind"] == "run"
    assert row["n"] == 5  # PM spans never pad the run sample set
    assert row["wall_p50"] == pytest.approx(100.0)
    assert row["wall_p90"] == pytest.approx(100.0)
    assert row["wall_p90"] < 1000  # a 100_000 s PM span did not leak in

    text = usage.format_report_text(report)
    assert "wall p50 1m40s  p90 1m40s  n 5" in text
    assert "*" not in text and FOOTNOTE not in text


def test_build_report_wall_kind_does_not_backfill_runs_with_session_spans(
    tmp_path, monkeypatch
) -> None:
    """2 run walls + 6 PM spans: n stays 2 and no percentile is invented."""
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))

    ledger = []
    for index in range(1, 3):
        session_id = f"mw-k-1-{index}"
        ledger.append(
            _start(f"m{index}", key="k", type="coding", session_id=session_id, ts=_at(400))
        )
        ledger.append(_end(f"m{index}", wall_s=100.0, ts=_at(390)))
        _worker_session(pi_root, session_id, index, ended_minutes_ago=200, span_s=50_000)
    for index in range(1, 7):
        _pm_session(pi_root, f"01JPMWINDOW{index:04d}", span_s=100_000.0)
    _write_ledger(target / "runs.jsonl", ledger)

    report = usage.build_report(NOW, SINCE, {})
    row = report["groups"]["model"][0]

    assert row["wall_kind"] == "none"  # too few run samples: no source claimed
    assert row["n"] == 2  # the 6 PM spans did not top the set up to n >= 5
    assert row["wall_p50"] is None and row["wall_p90"] is None


def test_build_report_wall_kind_session_for_pm_only_and_text_marker(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    for index in range(1, 6):
        _pm_session(pi_root, f"01JPMWINDOW{index:04d}", span_s=3600.0)

    report = usage.build_report(NOW, SINCE, {})
    for rows in report["groups"].values():
        assert rows
        assert all(row["wall_kind"] == "session" for row in rows)
    row = report["groups"]["model"][0]
    assert row["n"] == 5
    assert row["wall_p50"] == pytest.approx(3600.0)
    assert row["wall_p90"] == pytest.approx(3600.0)

    text = usage.format_report_text(report)
    lines = text.splitlines()
    assert "wall p50 1h00m  p90 1h00m* n 5" in text  # marker ends the wall cell
    assert FOOTNOTE in lines
    coverage = next(index for index, line in enumerate(lines) if line.startswith("coverage:"))
    assert lines.index(FOOTNOTE) < coverage  # footnote sits right before coverage


def test_build_report_wall_kind_run_for_worker_only_keeps_old_text_shape(
    tmp_path, monkeypatch
) -> None:
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    walls = [60.0, 120.0, 180.0, 240.0, 300.0, 360.0]
    ledger = []
    for index, wall in enumerate(walls, start=1):
        session_id = f"mw-k-1-{index}"
        ledger.append(
            _start(f"w{index}", key="k", type="coding", session_id=session_id, ts=_at(400))
        )
        ledger.append(_end(f"w{index}", wall_s=wall, ts=_at(390)))
        _worker_session(pi_root, session_id, index, ended_minutes_ago=60 + index, span_s=wall)
    _write_ledger(target / "runs.jsonl", ledger)

    report = usage.build_report(NOW, SINCE, {})
    row = report["groups"]["model"][0]
    assert row["wall_kind"] == "run"
    assert row["n"] == 6
    assert row["wall_p50"] == pytest.approx(210.0)
    assert row["wall_p90"] == pytest.approx(330.0)

    text = usage.format_report_text(report)
    assert "wall p50 3m30s  p90 5m30s  n 6" in text
    assert "*" not in text and FOOTNOTE not in text


def test_build_report_wall_kind_none_without_walls(tmp_path, monkeypatch) -> None:
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    # Open run (start, no end): the ledger wall is unknown and AC-004 forbids
    # guessing it from the session log.
    _write_ledger(
        target / "runs.jsonl", [_start("r1", key="k", session_id="mw-k-1-1", ts=_at(30))]
    )
    _write_pi_session(
        pi_root,
        "2026-10-19T10-00-00-000Z_mw-k-1-1.jsonl",
        [_pi_header("mw-k-1-1", _at(29)), _pi_assistant(_at(28))],
    )

    report = usage.build_report(NOW, SINCE, {})
    row = report["groups"]["model"][0]
    assert row["wall_kind"] == "none"
    assert row["n"] == 0
    assert row["wall_p50"] is None and row["wall_p90"] is None

    text = usage.format_report_text(report)
    assert "wall p50 -      p90 -      n 0" in text
    assert "*" not in text and FOOTNOTE not in text


def test_build_report_source_pm_keeps_session_wall(tmp_path, monkeypatch) -> None:
    """AC-005 must not regress: ``--source pm`` still reports the session span."""
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))

    ledger = []
    for index in range(1, 6):
        session_id = f"mw-k-1-{index}"
        ledger.append(
            _start(f"m{index}", key="k", type="coding", session_id=session_id, ts=_at(400))
        )
        ledger.append(_end(f"m{index}", wall_s=100.0, ts=_at(390)))
        _worker_session(pi_root, session_id, index, ended_minutes_ago=200, span_s=5_000)
    _write_ledger(target / "runs.jsonl", ledger)
    for index in range(1, 6):
        _pm_session(pi_root, f"01JPMWINDOW{index:04d}", span_s=1800.0)

    everything = usage.build_report(NOW, SINCE, {})
    assert everything["groups"]["model"][0]["wall_kind"] == "run"
    assert everything["groups"]["model"][0]["wall_p90"] == pytest.approx(100.0)

    pm_only = usage.build_report(NOW, SINCE, {"source": "pm"})
    assert pm_only["sources"] == {"worker": 0, "pm": 5}
    rows = pm_only["groups"]["model"]
    assert len(rows) == 1
    assert rows[0]["wall_kind"] == "session"
    assert rows[0]["n"] == 5
    assert rows[0]["wall_p50"] == pytest.approx(1800.0)
    assert rows[0]["wall_p90"] == pytest.approx(1800.0)


# ── 13. --until (R7) and run-level detail (R8-R10) ──────────────────────────


def _iso_at(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def test_parse_until_accepts_since_forms_plus_minute() -> None:
    base = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    assert usage.parse_until("7d", base) == base - timedelta(days=7)
    assert usage.parse_until("24h", base) == base - timedelta(hours=24)
    assert usage.parse_until("30m", base) == base - timedelta(minutes=30)
    # Relative forms keep parse_since semantics: an offset back from now.
    assert usage.parse_until("24h", base) == usage.parse_since("24h", base)

    day = usage.parse_until("2026-10-12", base)
    assert day.tzinfo is not None
    assert day.astimezone().strftime("%Y-%m-%d") == "2026-10-12"
    assert day.astimezone().strftime("%H:%M") == "00:00"

    # The form only --until accepts: local wall clock of that minute.
    minute = usage.parse_until("2026-10-19T14:00", base)
    assert minute.tzinfo is not None
    assert minute.astimezone().strftime("%Y-%m-%d %H:%M") == "2026-10-19 14:00"


def test_parse_until_rejects_garbage() -> None:
    for bad in (
        "",
        "7",
        "abc",
        "7x",
        "2026-13-01",
        "2026/10/12",
        "-3d",
        "2026-10-19T25:00",
        "2026-10-19 14:00",
    ):
        with pytest.raises(ValueError):
            usage.parse_until(bad)
    # --since keeps its narrower syntax: no time-of-day form.
    with pytest.raises(ValueError):
        usage.parse_since("2026-10-19T14:00")


def test_build_report_until_window_is_half_open(tmp_path, monkeypatch) -> None:
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))

    base = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    since = base - timedelta(hours=2)
    until = base
    inside_start = base - timedelta(minutes=30)

    _write_ledger(
        target / "runs.jsonl",
        [
            # Starts exactly at the lower bound: included (half-open lower edge).
            _start("r-since", key="k", type="coding", session_id="mw-k-1-1",
                   ts=_iso_at(since)),
            _end("r-since", wall_s=60.0, ts=_iso_at(since + timedelta(seconds=60))),
            _start("r-inside", key="k", type="coding", session_id="mw-k-1-2",
                   ts=_iso_at(inside_start)),
            _end("r-inside", wall_s=60.0, ts=_iso_at(inside_start + timedelta(seconds=60))),
            # Starts exactly at the upper bound: excluded (half-open upper edge).
            _start("r-until", key="k", type="coding", session_id="mw-k-1-3",
                   ts=_iso_at(until)),
            _end("r-until", wall_s=60.0, ts=_iso_at(until + timedelta(seconds=60))),
        ],
    )
    _write_pi_session(
        pi_root,
        "2026-10-19T10-00-00-000Z_mw-k-1-1.jsonl",
        [
            _pi_header("mw-k-1-1", _iso_at(since)),
            _pi_assistant(_iso_at(since + timedelta(seconds=30)), raw_usage=_usage(10, 1, 0, 0)),
        ],
    )
    _write_pi_session(
        pi_root,
        "2026-10-19T10-01-00-000Z_mw-k-1-2.jsonl",
        [
            _pi_header("mw-k-1-2", _iso_at(inside_start)),
            _pi_assistant(
                _iso_at(inside_start + timedelta(seconds=30)), raw_usage=_usage(20, 2, 0, 0)
            ),
            # Exactly at `until`: outside the half-open window.
            _pi_assistant(_iso_at(until), raw_usage=_usage(999, 99, 0, 0)),
        ],
    )
    _write_pi_session(
        pi_root,
        "2026-10-19T10-02-00-000Z_mw-k-1-3.jsonl",
        [
            _pi_header("mw-k-1-3", _iso_at(until)),
            _pi_assistant(_iso_at(until + timedelta(seconds=30)), raw_usage=_usage(50, 5, 0, 0)),
        ],
    )

    report = usage.build_report(base, since, {}, until=until)

    assert report["since"] == _iso_at(since)
    assert report["until"] == _iso_at(until)
    assert report["window"] == "2h"
    # Window-out runs vanish from every view, not only from the detail table.
    assert [run["run_id"] for run in report["runs"]] == ["r-inside", "r-since"]
    assert report["runs_total"] == 2
    assert report["totals"]["runs"] == 2
    listed = [run["run_id"] for run in usage.load_runs(since, {}, until=until)[0]]
    assert listed == ["r-since", "r-inside"]

    # The message exactly at `until` never becomes a call.
    assert report["totals"]["calls"] == 2
    assert report["totals"]["tokens"]["input"] == 30
    by_id = {run["run_id"]: run for run in report["runs"]}
    assert by_id["r-since"]["calls"] == 1
    assert by_id["r-inside"]["calls"] == 1
    assert by_id["r-inside"]["tokens"]["input"] == 20

    # Lowering the upper bound removes the newer run from groups too.
    narrow = usage.build_report(base, since, {}, until=inside_start)
    assert narrow["runs_total"] == 1
    assert narrow["totals"]["tokens"]["input"] == 10


def test_build_report_runs_detail_fields_order_and_limit(tmp_path, monkeypatch) -> None:
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))

    ledger = []
    for index in range(1, 26):
        session_id = f"mw-k-1-{index}"
        started = NOW - timedelta(minutes=2 * index)
        ledger.append(
            _start(f"r{index}", key="k", type="coding", session_id=session_id,
                   model="timi/glm-5.3-flashx", ts=_iso_at(started))
        )
        ledger.append(_end(f"r{index}", wall_s=10.0, ts=_iso_at(started + timedelta(minutes=1))))
        _write_pi_session(
            pi_root,
            f"2026-10-19T10-{index:02d}-00-000Z_{session_id}.jsonl",
            [
                _pi_header(session_id, _iso_at(started)),
                _pi_assistant(
                    _iso_at(started + timedelta(seconds=10)),
                    raw_usage=_usage(100, 10, 1000, 5),
                ),
            ],
        )
    _write_ledger(target / "runs.jsonl", ledger)

    report = usage.build_report(NOW, SINCE, {})

    # Default limit is 20, while runs_total keeps the uncut count.
    assert report["runs_total"] == 25
    assert len(report["runs"]) == 20
    assert [run["run_id"] for run in report["runs"]] == [f"r{i}" for i in range(1, 21)]

    row = report["runs"][0]
    assert set(row) == set(usage.DETAIL_FIELDS)  # R9 field names, verbatim
    assert set(row["tokens"]) == set(usage.TOKEN_FIELDS)
    assert row["run_id"] == "r1"
    assert row["started_at"] == _iso_at(NOW - timedelta(minutes=2))
    assert row["ended_at"] == _iso_at(NOW - timedelta(minutes=1))
    assert row["key"] == "k"
    assert row["type"] == "coding"
    assert row["model"] == "timi/glm-5.3-flashx"
    assert row["calls"] == 1
    assert row["tokens"] == {"input": 100, "output": 10, "cache_read": 1000, "cache_write": 5}
    assert row["wall_s"] == pytest.approx(10.0)
    assert row["wall_kind"] == "run"
    assert row["status"] == "done"
    assert row["attribution"] == "exact"
    assert row["session_id"] == "mw-k-1-1"
    assert row["open_run"] is False

    unlimited = usage.build_report(NOW, SINCE, {}, limit=0)
    assert len(unlimited["runs"]) == 25
    assert unlimited["runs_total"] == 25
    assert len(usage.build_report(NOW, SINCE, {}, limit=None)["runs"]) == 25
    assert len(usage.build_report(NOW, SINCE, {}, limit=3)["runs"]) == 3

    with pytest.raises(ValueError):
        usage.build_report(NOW, SINCE, {}, limit=-1)


def test_build_report_runs_open_run_never_backfills_wall(tmp_path, monkeypatch) -> None:
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    # start, no end: an orphan run. Its session spans 600 s, which must never
    # become the run wall (T-06 / AC-016).
    _write_ledger(
        target / "runs.jsonl",
        [_start("r-open", key="k", type="coding", session_id="mw-open-1-1", ts=_at(30))],
    )
    _write_pi_session(
        pi_root,
        "2026-10-19T10-00-00-000Z_mw-open-1-1.jsonl",
        [
            _pi_header("mw-open-1-1", _at(20)),
            _pi_assistant(_at(10), raw_usage=_usage(7, 3, 0, 0)),
        ],
    )

    report = usage.build_report(NOW, SINCE, {})
    row = report["runs"][0]
    assert row["open_run"] is True
    assert row["wall_s"] is None  # null, not 0 and not the session span
    assert row["wall_kind"] == "none"
    assert row["status"] == "running"
    assert row["ended_at"] is None
    assert row["calls"] == 1  # tokens are still attributable
    assert row["tokens"]["input"] == 7

    text = usage.format_report_text(report, detail=True)
    assert "wall -" in text


def test_build_report_runs_missing_session_keeps_tokens_unknown(tmp_path, monkeypatch) -> None:
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    _write_ledger(
        target / "runs.jsonl",
        [
            _start("r-ghost", key="k", type="coding", session_id="mw-ghost-1-1", ts=_at(30)),
            _end("r-ghost", wall_s=5.0, ts=_at(29)),
        ],
    )

    report = usage.build_report(NOW, SINCE, {})
    row = report["runs"][0]

    assert row["run_id"] == "r-ghost"
    assert row["calls"] is None  # not 0: 0 would claim "no request happened"
    assert row["tokens"] == {
        "input": None,
        "output": None,
        "cache_read": None,
        "cache_write": None,
    }
    assert row["wall_s"] == pytest.approx(5.0)
    assert row["wall_kind"] == "run"
    assert row["session_id"] == "mw-ghost-1-1"
    # Nothing was attributable, so the totals stay unknown too.
    assert report["totals"]["tokens"]["input"] is None

    text = usage.format_report_text(report, detail=True)
    assert "calls -" in text
    assert "in -       out -       cacheR -" in text


def test_build_report_runs_tokens_sum_to_totals(tmp_path, monkeypatch) -> None:
    _rich_fixture(tmp_path, monkeypatch)

    report = usage.build_report(NOW, SINCE, {}, limit=0)

    assert report["runs_total"] == report["totals"]["runs"] == 6
    sums = dict.fromkeys(usage.TOKEN_FIELDS, 0)
    for row in report["runs"]:
        for field in usage.TOKEN_FIELDS:
            value = row["tokens"][field]
            if value is not None:
                sums[field] += value
    assert sums == report["totals"]["tokens"]  # AC-015, untruncated

    # Truncating must not corrupt runs_total or the totals.
    cut = usage.build_report(NOW, SINCE, {}, limit=2)
    assert len(cut["runs"]) == 2
    assert cut["runs_total"] == 6
    assert cut["totals"] == report["totals"]

    # A PM window session without a ledger row is a row of its own, so the
    # token sum stays self-consistent; its wall is a session span ('*').
    pm_rows = [row for row in report["runs"] if row["run_id"] is None]
    assert len(pm_rows) == 1
    assert pm_rows[0]["key"] == "pm"
    assert pm_rows[0]["type"] == "pm"
    assert pm_rows[0]["wall_kind"] == "session"
    assert pm_rows[0]["open_run"] is False


def test_format_report_text_detail_section_and_truncation(tmp_path, monkeypatch) -> None:
    target = tmp_path / "usage"
    pi_root = tmp_path / "pi"
    monkeypatch.setenv("MW_USAGE_DIR", str(target))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    fixed_now = datetime(2026, 10, 19, 12, 0, 0, tzinfo=timezone.utc)
    fixed_since = fixed_now - timedelta(days=7)

    ledger = []
    for index in range(1, 4):
        session_id = f"mw-k-1-{index}"
        started = fixed_now - timedelta(minutes=30 * index)
        ledger.append(
            _start(f"r{index}", key="mw-usage-monitor", task_key=f"um-t0{index}",
                   type="research", session_id=session_id,
                   model="timi/deepseek-v4.1-flash", ts=_iso_at(started))
        )
        ledger.append(
            _end(f"r{index}", wall_s=111.0, status="done",
                 ts=_iso_at(started + timedelta(seconds=111)))
        )
        _write_pi_session(
            pi_root,
            f"2026-10-19T10-0{index}-00-000Z_{session_id}.jsonl",
            [
                _pi_header(session_id, _iso_at(started)),
                _pi_assistant(
                    _iso_at(started + timedelta(seconds=5)),
                    model="deepseek-v4.1-flash",
                    raw_usage=_usage(31_000, 14_000, 503_000, 0),
                ),
            ],
        )
    _write_ledger(target / "runs.jsonl", ledger)

    report = usage.build_report(fixed_now, fixed_since, {}, limit=2)
    plain = usage.format_report_text(report)
    assert "runs (newest first)" not in plain
    assert "showing" not in plain

    text = usage.format_report_text(report, detail=True)
    lines = text.splitlines()
    assert lines[0].startswith("usage ")
    assert " → " in lines[0]
    assert lines[0].endswith("(7d) · ledger 6 events · runs 3 (worker 3 / pm 0)")

    head = lines.index("runs (newest first)")
    assert lines[head + 1] == "showing 2 of 3 runs (--limit 0 for all)"
    coverage_index = next(index for index, line in enumerate(lines) if line.startswith("coverage:"))
    assert head < coverage_index

    # AC-015 row content: key, task_key, type, model, calls, 4 token parts,
    # wall, status. Newest first => r1.
    row = lines[head + 2]
    assert "mw-usage-monitor" in row
    assert "um-t01" in row
    assert "research" in row
    assert "timi/deepseek-v4.1-flash" in row
    assert "calls 1" in row
    assert "in 31k" in row and "out 14k" in row
    assert "cacheR 503k" in row and "cacheW 0" in row
    assert "wall 1m51s" in row and "done" in row

    full = usage.format_report_text(
        usage.build_report(fixed_now, fixed_since, {}, limit=0), detail=True
    )
    assert "runs (newest first)" in full
    assert "showing" not in full
    assert len([line for line in full.splitlines() if "1m51s" in line]) == 3
