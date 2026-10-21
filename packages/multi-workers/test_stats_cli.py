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
import time
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
    # spec §12: HTML sidecar + browser toggle (default off/off).
    assert args.html is None
    assert args.no_open is False


def test_parse_args_stats_html_flag_forms() -> None:
    """spec §12 R11: `--html` alone means the default path, `--html P` that path."""
    assert mw._parse_args(["stats", "--html"]).html == ""
    assert mw._parse_args(["stats", "--html", "out/r.html"]).html == "out/r.html"
    both = mw._parse_args(["stats", "--html", "--no-open"])
    assert (both.html, both.no_open) == ("", True)


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

    code, out, err = _run_stats(["--detail", "--no-open"])
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

    code, out, err = _run_stats(["--detail", "--no-open", "--limit", "1"])
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


# -- 4c. static HTML sidecar + browser (spec §12, AC-018/AC-019) ----------


def _html_report_text(usage_dir: pathlib.Path, pi_root: pathlib.Path, monkeypatch) -> None:
    """One worker run + its session, so all four group tables are populated."""
    _write_ledger(usage_dir, [_worker_run()])
    _pi_session(pi_root, WORKER_SESSION_ID)
    monkeypatch.delenv("MW_STATS_NO_OPEN", raising=False)


def test_cmd_stats_html_writes_self_contained_report(env_dirs, tmp_path, monkeypatch) -> None:
    """AC-018: `--html <path>` writes the file; `--no-open` never opens it."""
    usage_dir, pi_root, _claude = env_dirs
    _html_report_text(usage_dir, pi_root, monkeypatch)

    def _explode(*_args, **_kwargs):
        raise AssertionError("webbrowser.open must not run under --no-open")

    monkeypatch.setattr(mw.webbrowser, "open", _explode)

    # No --html and no --detail: no sidecar at all (the text path is unchanged).
    code, out, _err = _run_stats([])
    assert code == 0
    assert "html:" not in out
    assert not (usage_dir / "reports").exists()

    target = tmp_path / "nested" / "dir" / "r.html"  # parents are created
    code, out, err = _run_stats(["--html", str(target), "--no-open"])
    assert code == 0, err
    assert target.exists()
    html = target.read_text(encoding="utf-8")
    # Four group tables + the run table are the anchors, not the text brief.
    for heading in ("by model", "by type", "by key", "by project"):
        assert f"<h2>{heading}</h2>" in html
    # spec §13.2 R15: once the table *is* the whole window the heading states
    # its size (`runs (newest first) · N`) instead of the legacy `showing` note.
    assert '<h2>runs (newest first) \u00b7 1</h2>' in html
    assert "showing" not in html
    for header in ("started_at", "task_key", "cacheR", "session_id"):
        assert f"<th>{header}</th>" in html or f'<th class="num">{header}</th>' in html
    assert html.startswith("<!doctype html>")
    assert 'http://' not in html and 'https://' not in html
    # Text mode: the report prefix is untouched, the path is the last line.
    assert out.rstrip("\n").splitlines()[-1] == f"html: {target}"
    assert "by model" in out and "no ledger yet" not in out


def test_cmd_stats_detail_writes_default_path(env_dirs, monkeypatch) -> None:
    """R12: `--detail` keeps the text bytes and adds the default HTML sidecar."""
    usage_dir, pi_root, _claude = env_dirs
    _html_report_text(usage_dir, pi_root, monkeypatch)
    monkeypatch.setattr(mw.webbrowser, "open", lambda _uri: False)

    code, plain, _err = _run_stats(["--no-open"])
    assert code == 0
    assert "html:" not in plain  # no --html and no --detail ⇒ no sidecar

    code, out, err = _run_stats(["--detail", "--no-open"])
    assert code == 0, err
    # AC-019: suppressing the browser changes neither text nor rc.
    code, out_open, _err_open = _run_stats(["--detail"])
    stamp = re.compile(r"usage-\d{8}-\d{6}\.html")
    assert code == 0
    assert stamp.sub("STAMP", out_open) == stamp.sub("STAMP", out)
    path = pathlib.Path(out.rstrip("\n").splitlines()[-1].split("html: ", 1)[1])
    assert path.parent == usage_dir / "reports"
    assert re.fullmatch(r"usage-\d{8}-\d{6}\.html", path.name)
    assert path.exists() and path.read_text(encoding="utf-8").startswith("<!doctype html>")

    # A second refresh is a second file: history is never overwritten.
    time.sleep(1.1)  # the default name has one-second resolution
    code, out2, err2 = _run_stats(["--detail", "--no-open"])
    assert code == 0, err2
    path2 = pathlib.Path(out2.rstrip("\n").splitlines()[-1].split("html: ", 1)[1])
    assert path2 != path and path2.exists()


def test_cmd_stats_detail_opens_browser(env_dirs, monkeypatch) -> None:
    """AC-019: `--detail` opens the file:// URI exactly once by default."""
    usage_dir, pi_root, _claude = env_dirs
    _html_report_text(usage_dir, pi_root, monkeypatch)
    calls: list[str] = []
    monkeypatch.setattr(mw.webbrowser, "open", lambda uri: calls.append(uri) or True)

    code, out, err = _run_stats(["--detail"])
    assert code == 0, err
    assert len(calls) == 1
    assert calls[0].startswith("file:///")
    assert calls[0].endswith(".html")
    assert "warning" not in err
    assert "runs (newest first)" in out


def test_cmd_stats_no_open_env_suppresses_browser(env_dirs, monkeypatch) -> None:
    """AC-019: `MW_STATS_NO_OPEN=1` is the automation switch (`0` = open)."""
    usage_dir, pi_root, _claude = env_dirs
    _html_report_text(usage_dir, pi_root, monkeypatch)

    def _explode(*_args, **_kwargs):
        raise AssertionError("MW_STATS_NO_OPEN must suppress webbrowser.open")

    monkeypatch.setattr(mw.webbrowser, "open", _explode)
    monkeypatch.setenv("MW_STATS_NO_OPEN", "1")
    code, out, err = _run_stats(["--detail"])
    assert code == 0, err
    assert "html:" in out

    # `0` is not "set": it restores the default open behaviour.
    opened: list[str] = []
    monkeypatch.setattr(mw.webbrowser, "open", lambda uri: opened.append(uri) or True)
    monkeypatch.setenv("MW_STATS_NO_OPEN", "0")
    code, _out, err = _run_stats(["--detail"])
    assert code == 0, err
    assert len(opened) == 1


def test_cmd_stats_json_detail_keeps_stdout_pure(env_dirs, monkeypatch) -> None:
    """`--json` never lets the HTML path leak into the JSON document."""
    usage_dir, pi_root, _claude = env_dirs
    _html_report_text(usage_dir, pi_root, monkeypatch)
    monkeypatch.setattr(mw.webbrowser, "open", lambda _uri: True)

    code, out, err = _run_stats(["--json", "--detail", "--no-open"])
    assert code == 0, err
    report = json.loads(out)  # the whole stdout is one JSON document
    assert set(report) == TOP_KEYS
    assert "html" not in out
    assert "[mw stats] html: " in err
    assert err.strip().splitlines()[-1].endswith(".html")


def test_cmd_stats_open_failure_warns_rc0(env_dirs, monkeypatch) -> None:
    """AC-019: no default browser is a warning; rc stays 0 and text is intact."""
    usage_dir, pi_root, _claude = env_dirs
    _html_report_text(usage_dir, pi_root, monkeypatch)

    def _boom(_uri):
        raise RuntimeError("no browser")

    monkeypatch.setattr(mw.webbrowser, "open", _boom)
    code, out, err = _run_stats(["--detail"])
    assert code == 0
    assert "runs (newest first)" in out
    assert "[mw stats] warning: cannot open" in err
    path = pathlib.Path(out.rstrip("\n").splitlines()[-1].split("html: ", 1)[1])
    assert path.exists()


def test_cmd_stats_html_empty_window_renders_placeholder(
    env_dirs, tmp_path, monkeypatch
) -> None:
    """A report with no runs still renders the table (no exception, explicit gap)."""
    usage_dir, pi_root, _claude = env_dirs
    pi_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.delenv("MW_STATS_NO_OPEN", raising=False)
    monkeypatch.setattr(mw.webbrowser, "open", lambda _uri: True)

    target = tmp_path / "empty.html"
    code, _out, err = _run_stats(["--html", str(target), "--no-open"])
    assert code == 0, err
    assert "窗口内没有运行" in target.read_text(encoding="utf-8")


# -- 4d. HTML = whole window, `--json` never pops a browser (spec §13) -----


def _six_runs(usage_dir: pathlib.Path, pi_root: pathlib.Path) -> None:
    """Six joined runs inside the default 7d window, so `--limit 3` really cuts."""
    runs = []
    for index in range(6):
        session_id = f"mw-mw-usage-monitor-4242-{index}"
        start_min = 600 - index * 60
        runs.append(_run_at(f"run-{index}", start_min, start_min - 60, session_id))
        _pi_session(pi_root, session_id, at_minutes=start_min)
    _write_ledger(usage_dir, runs)


def _runs_tbody_rows(html: str) -> int:
    """Data rows of the runs table (group tables precede it, header sits in thead)."""
    tail = html.split("<h2>runs (newest first)", 1)[1]
    tbody = tail.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    return tbody.count("<tr>")


def test_cmd_stats_html_detail_is_whole_window(env_dirs, tmp_path, monkeypatch) -> None:
    """AC-022: `--limit` cuts the text/JSON table only; the HTML page is every run."""
    usage_dir, pi_root, _claude = env_dirs
    _six_runs(usage_dir, pi_root)
    monkeypatch.delenv("MW_STATS_NO_OPEN", raising=False)

    def _explode(*_args, **_kwargs):
        raise AssertionError("webbrowser.open must not run under --no-open")

    monkeypatch.setattr(mw.webbrowser, "open", _explode)

    target = tmp_path / "all.html"
    code, out, err = _run_stats(
        ["--since", "7d", "--detail", "--no-open", "--limit", "3",
         "--html", str(target)]
    )
    assert code == 0, err
    # R16: the text table keeps the cut and says so; runs_total stays the truth.
    assert "showing 3 of 6 runs" in out
    assert "runs 6 (worker 6 / pm 0)" in out
    html = target.read_text(encoding="utf-8")
    assert _runs_tbody_rows(html) == 6  # == runs_total, not the --limit slice
    assert "showing" not in html
    assert '<h2>runs (newest first) \u00b7 6</h2>' in html


def test_cmd_stats_json_detail_never_builds_runs_all(env_dirs, monkeypatch) -> None:
    """AC-023: `runs_all` is an HTML-only channel; the JSON key set does not widen."""
    usage_dir, pi_root, _claude = env_dirs
    _html_report_text(usage_dir, pi_root, monkeypatch)

    def _explode(*_args, **_kwargs):
        raise AssertionError("webbrowser.open must not run under --json")

    monkeypatch.setattr(mw.webbrowser, "open", _explode)

    code, out, err = _run_stats(["--json", "--detail", "--no-open"])
    assert code == 0, err
    report = json.loads(out)  # the whole stdout is still one JSON document
    assert "runs_all" not in report
    assert set(report) == TOP_KEYS


def test_cmd_stats_json_does_not_open_browser(env_dirs, monkeypatch) -> None:
    """`--json` implies `--no-open`: an automation run never pops a window."""
    usage_dir, pi_root, _claude = env_dirs
    _html_report_text(usage_dir, pi_root, monkeypatch)
    opened: list[str] = []
    monkeypatch.setattr(mw.webbrowser, "open", lambda uri: opened.append(uri) or True)

    code, out, err = _run_stats(["--json", "--detail"])
    assert code == 0, err
    assert opened == []
    json.loads(out)
    # The file is still written and its path is diagnostics on stderr, and the
    # suppressed full table is disclosed exactly once (no silent downgrade).
    assert "[mw stats] html: " in err
    path = pathlib.Path(err.strip().splitlines()[-1].split("html: ", 1)[1])
    assert path.exists() and path.name.endswith(".html")
    assert err.count("[mw stats] note: --json suppresses the full run table") == 1


def test_cmd_stats_json_explicit_html_still_opens(env_dirs, tmp_path, monkeypatch) -> None:
    """An explicit `--json --html PATH` is a file request: write it and open it."""
    usage_dir, pi_root, _claude = env_dirs
    _html_report_text(usage_dir, pi_root, monkeypatch)
    opened: list[str] = []
    monkeypatch.setattr(mw.webbrowser, "open", lambda uri: opened.append(uri) or True)

    target = tmp_path / "r.html"
    code, out, err = _run_stats(["--json", "--detail", "--html", str(target)])
    assert code == 0, err
    json.loads(out)
    assert target.exists()
    assert opened == [target.as_uri()]


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
