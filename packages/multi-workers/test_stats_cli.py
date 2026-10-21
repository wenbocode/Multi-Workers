"""Tests for the `mw stats` CLI surface (mw-usage-monitor T-03).

Every fixture is written under ``tmp_path`` and every root is injected through
``MW_USAGE_DIR`` / ``MW_PI_SESSIONS_DIR`` / ``MW_CLAUDE_PROJECTS_DIR``, so no
test ever reads the developer's real session tree.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import pathlib
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import mw  # noqa: E402
import usage  # noqa: E402

MW_PY = pathlib.Path(mw.__file__)
NOW = datetime.now(timezone.utc).replace(microsecond=0)

WORKER_KEY = "mw-usage-monitor"
WORKER_SESSION_ID = "mw-mw-usage-monitor-4242-1"
PM_SESSION_ID = "pm-session-1"
PROJECT = "H:/git/ProjA"

#: design 5 + spec §11.2: the fixed `--json` contract, exact key sets (extras are failures).
TOP_KEYS = {
    "generated_at",
    "since",
    "until",
    "window",
    "ledger",
    "totals",
    "groups",
    "coverage",
    "sources",
    "runs_total",
    "runs",
}
LEDGER_KEYS = {"path", "events", "bad_lines", "open_runs"}
TOTALS_KEYS = {"calls", "tokens", "runs"}
GROUP_ROW_KEYS = {"name", "calls", "tokens", "runs", "wall_p50", "wall_p90", "n", "wall_kind"}
COVERAGE_KEYS = {"cli", "runs", "attribution"}


def _at(minutes_ago: float) -> str:
    return (NOW - timedelta(minutes=minutes_ago)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _usage(input_tokens: int, output_tokens: int, cache_read: int, cache_write: int) -> dict:
    return {
        "input": input_tokens,
        "output": output_tokens,
        "cacheRead": cache_read,
        "cacheWrite": cache_write,
        "totalTokens": input_tokens + output_tokens + cache_read + cache_write,
    }


def _write_jsonl(path: pathlib.Path, rows: list[dict]) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def _write_ledger(usage_dir: pathlib.Path, run_rows: list[list[dict]]) -> pathlib.Path:
    rows = [row for run in run_rows for row in run]
    return _write_jsonl(pathlib.Path(usage_dir) / usage.LEDGER_NAME, rows)


def _worker_run(run_id: str = "run-1", wall_s: float | None = 3000) -> list[dict]:
    start = {"event": "start", "run_id": run_id, "ts": _at(180), "source": "worker",
             "project": PROJECT, "key": WORKER_KEY, "task_key": WORKER_KEY,
             "type": "coding", "role": "coding", "cli": "pi", "attribution": "exact",
             "session_id": WORKER_SESSION_ID, "model": "timi/glm-5.3-flashx"}
    end = {"event": "end", "run_id": run_id, "ts": _at(120), "wall_s": wall_s,
           "exit": 0, "status": "done", "reconciled": False}
    return [start, end]


def _pi_session(
    root: pathlib.Path,
    session_id: str,
    filename: str | None = None,
    model: str = "glm-5.3-flashx",
    provider: str = "timi",
    at_minutes: float | None = None,
) -> pathlib.Path:
    # `at_minutes` shifts the whole session (header + 2 entries) so a test can
    # place it inside a `[since, until)` window; the default reproduces the
    # original -180/-170/-150 min layout byte for byte.
    head = 180 if at_minutes is None else at_minutes
    rows = [
        {"type": "session", "version": 3, "id": session_id, "timestamp": _at(head), "cwd": PROJECT},
        {"type": "message", "id": "msg-1", "parentId": None, "timestamp": _at(head - 10),
         "message": {"role": "assistant", "content": [{"type": "text", "text": "x"}],
                     "api": "openai-responses", "provider": provider, "model": model,
                     "usage": _usage(1200, 340, 5600, 120), "stopReason": "stop",
                     "timestamp": 0}},
        {"type": "message", "id": "msg-2", "parentId": None, "timestamp": _at(head - 30),
         "message": {"role": "user", "content": "not read", "timestamp": 0}},
    ]
    name = filename or f"2026-10-19T10-00-00-000Z_{session_id}.jsonl"
    return _write_jsonl(pathlib.Path(root) / "H--git-ProjA" / name, rows)


def _run_at(
    run_id: str,
    start_min: float,
    end_min: float,
    session_id: str,
    key: str = WORKER_KEY,
) -> list[dict]:
    """One ledger run+reap pair at arbitrary offsets (window-boundary tests)."""
    start = {"event": "start", "run_id": run_id, "ts": _at(start_min), "source": "worker",
             "project": PROJECT, "key": key, "task_key": key,
             "type": "coding", "role": "coding", "cli": "pi", "attribution": "exact",
             "session_id": session_id, "model": "timi/glm-5.3-flashx"}
    end = {"event": "end", "run_id": run_id, "ts": _at(end_min),
           "wall_s": (start_min - end_min) * 60,
           "exit": 0, "status": "done", "reconciled": False}
    return [start, end]


@pytest.fixture()
def env_dirs(tmp_path, monkeypatch):
    """Injected roots: empty ledger dir, pi sessions, claude projects."""
    usage_dir = tmp_path / "usage"
    pi_root = tmp_path / "pi-sessions"
    claude_root = tmp_path / "claude-projects"
    claude_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("MW_USAGE_DIR", str(usage_dir))
    monkeypatch.setenv("MW_PI_SESSIONS_DIR", str(pi_root))
    monkeypatch.setenv("MW_CLAUDE_PROJECTS_DIR", str(claude_root))
    return usage_dir, pi_root, claude_root


def _run_stats(argv: list[str] | None = None) -> tuple[int, str, str]:
    args = mw._parse_args(["stats", *(argv or [])])
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = mw.cmd_stats(args)
    return code, out.getvalue(), err.getvalue()


# -- 1. argparse surface (RQ4 2: TS always appends --project=<dir>) ----------


def test_parse_args_stats_defaults() -> None:
    args = mw._parse_args(["stats"])
    assert args.subcommand == "stats"
    assert args.since == "7d"
    assert args.key is None
    assert args.type is None
    assert args.model is None
    assert args.project is None  # None = whole machine, not an error
    assert args.source is None
    assert args.json is False
    # spec §11.2 R7-R10: window upper bound / run detail / row cut.
    assert args.until is None  # None = now
    assert args.detail is False
    assert args.limit == 20


def test_parse_args_stats_accepts_runner_appended_project() -> None:
    args = mw._parse_args(
        ["stats", "--project", "X", "--json", "--since", "24h", "--source", "pm"]
    )
    assert (args.project, args.json, args.since, args.source) == ("X", True, "24h", "pm")

    # runMwCliRaw appends a single `--project=<dir>` token.
    equal_form = mw._parse_args(["stats", "--project=H:/git/ProjA"])
    assert equal_form.project == "H:/git/ProjA"


def test_parse_args_stats_rejects_unknown_source() -> None:
    with pytest.raises(SystemExit) as excinfo:
        mw._parse_args(["stats", "--source", "bogus"])
    assert excinfo.value.code == 2


# -- 2. text path -----------------------------------------------------------


def test_cmd_stats_text_matches_format_report(env_dirs, monkeypatch) -> None:
    usage_dir, pi_root, _claude = env_dirs
    _write_ledger(usage_dir, [_worker_run()])
    _pi_session(pi_root, WORKER_SESSION_ID)

    captured: dict = {}
    real_build = usage.build_report

    def spy_build(*args, **kwargs):
        report = real_build(*args, **kwargs)
        captured["report"] = report
        captured["filters"] = kwargs.get("filters")
        return report

    monkeypatch.setattr(usage, "build_report", spy_build)

    code, out, err = _run_stats([])
    assert code == 0, err
    assert captured["filters"]["project"] is None
    assert captured["filters"]["window"] == "7d"
    report = captured["report"]
    # The text path is exactly the shared renderer, not a re-implementation.
    assert out == usage.format_report_text(report) + "\n"

    assert out.startswith("usage ")
    # spec §11.2 R7: both window bounds are printed, half-open `[since, until)`.
    assert " → " in out
    assert "(7d)" in out
    assert "ledger 2 events" in out
    assert "runs 1 (worker 1 / pm 0)" in out
    assert "by model" in out
    assert "timi/glm-5.3-flashx" in out
    assert "by type" in out and "coding" in out
    assert "by key" in out and WORKER_KEY in out
    assert "by project" in out and "ProjA" in out
    assert "coverage: pi 1 runs (exact)" in out
    # n=1 samples: p50/p90 stay unknown (design 5: n<5 renders `-`).
    assert "wall p50 -" in out and "n 1" in out


def test_cmd_stats_text_passes_filters_through(env_dirs, monkeypatch) -> None:
    usage_dir, pi_root, _claude = env_dirs
    _write_ledger(usage_dir, [_worker_run()])
    _pi_session(pi_root, WORKER_SESSION_ID)

    captured: dict = {}
    real_build = usage.build_report

    def spy_build(*args, **kwargs):
        captured["filters"] = kwargs.get("filters")
        return real_build(*args, **kwargs)

    monkeypatch.setattr(usage, "build_report", spy_build)
    code, _out, err = _run_stats(
        ["--since", "24h", "--key", WORKER_KEY, "--type", "coding",
         "--model", "glm", "--project", "ProjA", "--source", "worker"]
    )
    assert code == 0, err
    assert captured["filters"] == {
        "window": "24h",
        "key": WORKER_KEY,
        "type": "coding",
        "model": "glm",
        "project": "ProjA",
        "source": "worker",
    }


# -- 3. --json contract (design 5) -----------------------------------------


def _all_keys(node) -> set[str]:
    keys: set[str] = set()
    if isinstance(node, dict):
        for key, value in node.items():
            keys.add(str(key))
            keys |= _all_keys(value)
    elif isinstance(node, list):
        for item in node:
            keys |= _all_keys(item)
    return keys


def test_cmd_stats_json_contract(env_dirs) -> None:
    usage_dir, pi_root, _claude = env_dirs
    _write_ledger(usage_dir, [_worker_run()])
    _pi_session(pi_root, WORKER_SESSION_ID)

    code, out, err = _run_stats(["--json"])
    assert code == 0, err
    report = json.loads(out)

    assert set(report) == TOP_KEYS
    assert set(report["ledger"]) == LEDGER_KEYS
    assert set(report["totals"]) == TOTALS_KEYS
    assert set(report["totals"]["tokens"]) == {"input", "output", "cache_read", "cache_write"}
    assert set(report["groups"]) == {"model", "type", "key", "project"}
    for rows in report["groups"].values():
        for row in rows:
            assert set(row) == GROUP_ROW_KEYS
            assert set(row["tokens"]) == {"input", "output", "cache_read", "cache_write"}
    for item in report["coverage"]:
        assert set(item) == COVERAGE_KEYS
    assert set(report["sources"]) == {"worker", "pm"}

    # AC-008: no money anywhere in the contract.
    forbidden = ("cost", "usd", "amount", "price", "spend")
    for key in _all_keys(report):
        assert not any(token in key.lower() for token in forbidden), key

    assert report["window"] == "7d"
    assert report["ledger"]["events"] == 2
    assert report["ledger"]["bad_lines"] == 0
    assert report["ledger"]["open_runs"] == 0
    assert report["totals"]["calls"] == 1
    assert report["totals"]["runs"] == 1
    assert report["totals"]["tokens"] == {
        "input": 1200, "output": 340, "cache_read": 5600, "cache_write": 120,
    }
    assert report["sources"] == {"worker": 1, "pm": 0}
    assert report["coverage"] == [{"cli": "pi", "runs": 1, "attribution": "exact"}]
    model_rows = report["groups"]["model"]
    assert [row["name"] for row in model_rows] == ["timi/glm-5.3-flashx"]
    assert model_rows[0]["n"] == 1
    assert model_rows[0]["wall_p50"] is None  # n<5 never guesses a percentile
    assert model_rows[0]["wall_p90"] is None


def test_cmd_stats_json_wall_from_ledger_when_enough_samples(env_dirs) -> None:
    """5 joined runs: the ledger spawn->reap wall drives p50/p90 (AC-004)."""
    usage_dir, pi_root, _claude = env_dirs
    runs = []
    for index in range(5):
        session_id = f"mw-mw-usage-monitor-4242-{index}"
        runs.append(_worker_run(run_id=f"run-{index}"))
        # No ':' in the name: Windows would turn it into an NTFS stream and
        # rglob('*.jsonl') would never see the file.
        _pi_session(pi_root, session_id, filename=f"2026-10-19T10-0{index}-00-000Z_{session_id}.jsonl")
    # Each ledger row carries the session id of its own session file.
    for index, run in enumerate(runs):
        run[0]["session_id"] = f"mw-mw-usage-monitor-4242-{index}"
    _write_ledger(usage_dir, runs)

    code, out, err = _run_stats(["--json"])
    assert code == 0, err
    report = json.loads(out)
    assert report["totals"]["runs"] == 5
    row = report["groups"]["model"][0]
    assert (row["n"], row["wall_p50"], row["wall_p90"]) == (5, 3000.0, 3000.0)


# -- 4. design 7 error / boundary rows -------------------------------------


def test_cmd_stats_invalid_since_rc2(env_dirs) -> None:
    code, out, err = _run_stats(["--since", "yesterday"])
    assert code == 2
    assert out == ""
    assert "invalid --since" in err
    assert "7d / 24h / 30m / YYYY-MM-DD" in err


def test_cmd_stats_missing_ledger_rc0_still_scans_sessions(env_dirs) -> None:
    usage_dir, pi_root, _claude = env_dirs
    assert not (usage_dir / usage.LEDGER_NAME).exists()
    _pi_session(pi_root, PM_SESSION_ID)

    code, out, err = _run_stats([])
    assert code == 0, err
    assert "no ledger yet" in out
    assert "no usage in window" not in out
    # PM session data is still attributed even without a ledger row.
    assert "by model" in out
    assert "timi/glm-5.3-flashx" in out
    assert "by key" in out and "pm" in out
    assert "runs 1 (worker 0 / pm 1)" in out

    # The JSON path stays parseable and reports the missing ledger as 0 events.
    code, out, err = _run_stats(["--json"])
    assert code == 0, err
    report = json.loads(out)
    assert report["ledger"]["events"] == 0
    assert report["ledger"]["path"] == str(usage_dir / usage.LEDGER_NAME)
    assert report["totals"]["calls"] == 1
    assert report["sources"] == {"worker": 0, "pm": 1}


def test_cmd_stats_empty_window_rc0(env_dirs) -> None:
    usage_dir, pi_root, _claude = env_dirs
    old = (NOW - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _write_jsonl(
        usage_dir / usage.LEDGER_NAME,
        [
            {"event": "start", "run_id": "old-run", "ts": old, "source": "worker",
             "project": PROJECT, "key": WORKER_KEY, "type": "coding", "cli": "pi",
             "session_id": "mw-old-run-1-1"},
            {"event": "end", "run_id": "old-run", "ts": old, "wall_s": 60, "exit": 0},
        ],
    )
    pi_root.mkdir(parents=True, exist_ok=True)

    code, out, err = _run_stats([])
    assert code == 0, err
    assert "no usage in window" in out
    assert "runs 0 (worker 0 / pm 0)" in out


# -- 4b. --until / --detail / --limit (spec §11 v0.3, AC-014..AC-017) ------


def test_cmd_stats_until_drops_runs_outside_window(env_dirs) -> None:
    """AC-014: a run after `until` leaves totals/groups/runs, not just the table."""
    usage_dir, pi_root, _claude = env_dirs
    _write_ledger(
        usage_dir,
        [
            # Inside the last 7d but newer than `--until 6h`.
            _run_at("run-recent", 180, 120, "mw-mw-usage-monitor-4242-1"),
            # 10h ago: before `--until 6h`.
            _run_at("run-earlier", 600, 540, "mw-mw-usage-monitor-4242-2"),
        ],
    )
    _pi_session(pi_root, "mw-mw-usage-monitor-4242-1", at_minutes=180)
    _pi_session(pi_root, "mw-mw-usage-monitor-4242-2", at_minutes=600)

    code, out, err = _run_stats(["--since", "7d", "--until", "6h", "--json"])
    assert code == 0, err
    report = json.loads(out)
    assert report["totals"]["runs"] == 1
    assert report["sources"] == {"worker": 1, "pm": 0}
    assert [row["run_id"] for row in report["runs"]] == ["run-earlier"]
    assert report["runs_total"] == 1
    # The recent run's events are outside the window, so its tokens are gone too.
    assert report["totals"]["calls"] == 1
    assert report["totals"]["tokens"] == {
        "input": 1200, "output": 340, "cache_read": 5600, "cache_write": 120,
    }
    assert [row["runs"] for rows in report["groups"].values() for row in rows] == [1, 1, 1, 1]

    code, out, err = _run_stats(["--since", "7d", "--until", "6h"])
    assert code == 0, err
    assert "runs 1 (worker 1 / pm 0)" in out
    assert "usage " in out and " → " in out


def test_cmd_stats_until_before_since_rc2(env_dirs) -> None:
    """R7: an inverted window is a CLI error; the kernel only yields an empty one."""
    code, out, err = _run_stats(["--since", "7d", "--until", "2020-01-01"])
    assert code == 2
    assert out == ""
    assert "--until must be after --since" in err


def test_cmd_stats_invalid_until_rc2(env_dirs) -> None:
    code, out, err = _run_stats(["--until", "yesterday"])
    assert code == 2
    assert out == ""
    assert "invalid --until" in err
    assert "YYYY-MM-DDTHH:MM" in err


def test_cmd_stats_detail_text_appends_run_table(env_dirs) -> None:
    """R8/AC-015: `--detail` is text-only, one row per run, all R9 fields."""
    usage_dir, pi_root, _claude = env_dirs
    _write_ledger(usage_dir, [_worker_run()])
    _pi_session(pi_root, WORKER_SESSION_ID)

    code, out, err = _run_stats([])
    assert code == 0, err
    assert "runs (newest first)" not in out

    code, out, err = _run_stats(["--detail"])
    assert code == 0, err
    assert "runs (newest first)" in out
    table = out.split("runs (newest first)", 1)[1]
    assert WORKER_KEY in table and "coding" in table
    assert "timi/glm-5.3-flashx" in table
    assert "calls 1" in table
    assert "in 1.2k" in table and "out 340" in table  # four token components
    assert "wall 50m00s" in table and "done" in table


def test_cmd_stats_limit_cuts_detail_and_json(env_dirs) -> None:
    """R10: the cut is stated in text and `runs_total` keeps the real count."""
    usage_dir, pi_root, _claude = env_dirs
    runs = []
    for index in range(3):
        session_id = f"mw-mw-usage-monitor-4242-{index}"
        start_min = 600 - index * 60
        runs.append(_run_at(f"run-{index}", start_min, start_min - 60, session_id))
        _pi_session(pi_root, session_id, at_minutes=start_min)
    _write_ledger(usage_dir, runs)

    code, out, err = _run_stats(["--detail", "--limit", "1"])
    assert code == 0, err
    assert "runs (newest first)" in out
    assert "showing 1 of 3 runs" in out

    code, out, err = _run_stats(["--json", "--limit", "1"])
    assert code == 0, err
    report = json.loads(out)
    assert len(report["runs"]) == 1
    assert report["runs_total"] == 3 > 1
    # newest first (run-2 started last), and `--limit` never touches the totals.
    assert report["runs"][0]["run_id"] == "run-2"
    assert report["totals"]["runs"] == 3


def test_cmd_stats_negative_limit_rc2(env_dirs) -> None:
    code, out, err = _run_stats(["--limit", "-1"])
    assert code == 2
    assert out == ""
    assert "--limit must be >= 0" in err


def test_cmd_stats_json_carries_runs_without_detail(env_dirs) -> None:
    """R8/AC-016: `runs[]` is part of the JSON contract, not a `--detail` effect."""
    usage_dir, pi_root, _claude = env_dirs
    _write_ledger(usage_dir, [_worker_run()])
    _pi_session(pi_root, WORKER_SESSION_ID)

    code, out, err = _run_stats(["--json"])
    assert code == 0, err
    report = json.loads(out)
    assert set(report) == TOP_KEYS
    assert isinstance(report["runs"], list) and len(report["runs"]) == 1
    assert report["runs_total"] == 1
    row = report["runs"][0]
    assert set(row) == set(usage.DETAIL_FIELDS)  # R9, verbatim
    assert row["run_id"] == "run-1" and row["key"] == WORKER_KEY
    assert row["calls"] == 1 and row["open_run"] is False
    assert row["wall_kind"] == "run" and row["wall_s"] == 3000.0


# -- 5. dispatch + machine-level CLI smoke ---------------------------------


def test_dispatch_maps_stats_to_cmd_stats() -> None:
    source = MW_PY.read_text(encoding="utf-8")
    block = re.search(r"\n    dispatch = \{(.*?)\n    \}", source, re.S)
    assert block is not None
    assert '"stats": cmd_stats,' in block.group(1)
    # anchored right after the status row, not floating in the middle
    assert re.search(r'"status": cmd_status,\s*\n\s*"stats": cmd_stats,', block.group(1))


def test_cli_stats_json_smoke(env_dirs) -> None:
    usage_dir, pi_root, _claude = env_dirs
    _write_ledger(usage_dir, [_worker_run()])
    _pi_session(pi_root, WORKER_SESSION_ID)

    env = dict(os.environ)
    env.update(
        {
            "MW_USAGE_DIR": str(usage_dir),
            "MW_PI_SESSIONS_DIR": str(pi_root),
            "MW_CLAUDE_PROJECTS_DIR": str(env_dirs[2]),
        }
    )
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(MW_PY), "stats", "--json", f"--project={PROJECT}"],
        capture_output=True,
        encoding="utf-8",
        timeout=300,
        env=env,
    )
    assert proc.returncode == 0, proc.stderr
    report = json.loads(proc.stdout)
    assert set(report) == TOP_KEYS
    assert report["totals"]["calls"] == 1
    assert report["sources"] == {"worker": 1, "pm": 0}
