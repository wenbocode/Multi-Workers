"""T-07 / AC-006 / VC-030: launcher reap is product-first (run.json > exit code).

The launcher used to derive the queue terminal row from the worker exit code
only (gap G-f): an `exit 0` with no product still read as `done`. AC-006 makes
the worker-written `run.json` the product of record; the exit code stays as the
fallback so absent/unreadable/non-terminal run state is byte-identical to the
pre-AC-006 launcher (zero back-fill).

Reverse cases required by the card:
  (a) run.json=needs-clarification + exit=0 => row needs-clarification (not done)
  (b) run.json=done + exit=0               => done (no regression)
  (c) run.json missing + exit=1            => failed (verbatim as today)
  (d) run.json=lost                        => lost (T-20 semantics kept)
  (e) run state != exit code               => conflict line in .mw/launcher.log
"""

from __future__ import annotations

import contextlib
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import launcher
from launcher import _parse_workers_file, _poll_once, _reap_status, _serialize_entry


# ── Fixtures ──────────────────────────────────────────────────────────────────


def _make_task_dir(tmp_path: pathlib.Path, key: str) -> pathlib.Path:
    d = tmp_path / ".agenticdoc" / "test-key" / "workers" / key
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.md").write_text("type: coding\nDo something useful.\n", encoding="utf-8")
    return d


def _write_run_json(task_dir: pathlib.Path, status: str, **overrides) -> pathlib.Path:
    """A worker-written run.json (schema 1, mirrors shared/run-store.ts)."""
    record = {
        "schema": 1,
        "task_key": task_dir.name,
        "run_id": f"{task_dir.name}@2026-10-11T00:00:00.000Z",
        "owner_key": "test-key",
        "kind": "coding",
        "status": status,
        "started_at": "2026-10-11T00:00:00.000Z",
        "artifacts": [],
    }
    record.update(overrides)
    path = task_dir / "run.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _entry(task_file: pathlib.Path, **overrides) -> dict[str, str]:
    entry = {
        "cli": "pi",
        "provider": "timi",
        "task_path": str(task_file),
        "task_key": "t001",
        "status": "running",
        "dispatched_at": "2026-10-11T00:00:00+00:00",
        "updated_at": "2026-10-11T00:00:00+00:00",
        "model": "",
    }
    entry.update(overrides)
    return entry


class _FinishedProc:
    """A worker process that has already exited with `returncode`."""

    def __init__(self, returncode: int) -> None:
        self.returncode = returncode

    def poll(self) -> int:
        return self.returncode


def _write_queue(tmp_path: pathlib.Path, entry: dict[str, str]) -> pathlib.Path:
    q = tmp_path / ".agenticdoc" / "_workers.parallel"
    q.parent.mkdir(parents=True, exist_ok=True)
    q.write_text(_serialize_entry(entry) + "\n", encoding="utf-8")
    return q


def _row_statuses(queue_file: pathlib.Path) -> dict[str, str]:
    return {e["task_key"]: e["status"] for e in _parse_workers_file(queue_file)}


def _emit_verify(capsys: pytest.CaptureFixture[str], line: str) -> None:
    with capsys.disabled():
        print(line)


# ── Unit: the product-first decision ─────────────────────────────────────────


class TestReapStatusProductFirst:
    def test_a_run_needs_clarification_outranks_exit_zero(self, tmp_path, capsys) -> None:
        d = _make_task_dir(tmp_path, "t001")
        _write_run_json(d, "needs-clarification")
        assert _reap_status(d, 0, "t001") == "needs-clarification"
        assert "run.json=needs-clarification" in capsys.readouterr().err

    def test_b_run_done_with_exit_zero_is_done(self, tmp_path, capsys) -> None:
        d = _make_task_dir(tmp_path, "t001")
        _write_run_json(d, "done", artifacts=["report.md"])
        assert _reap_status(d, 0, "t001") == "done"
        assert capsys.readouterr().err == ""  # agreeing values stay silent

    def test_c_missing_run_json_falls_back_to_exit_code(self, tmp_path, capsys) -> None:
        d = _make_task_dir(tmp_path, "t001")
        assert _reap_status(d, 1, "t001") == "failed"  # verbatim pre-AC-006
        assert capsys.readouterr().err == ""

    def test_d_run_lost_is_preserved(self, tmp_path) -> None:
        d = _make_task_dir(tmp_path, "t001")
        _write_run_json(d, "lost")
        assert _reap_status(d, 1, "t001") == "lost"

    def test_non_terminal_running_still_falls_back(self, tmp_path, capsys) -> None:
        # A `running` run.json is not a product verdict: the exit code decides.
        d = _make_task_dir(tmp_path, "t001")
        _write_run_json(d, "running")
        assert _reap_status(d, 0, "t001") == "done"
        assert capsys.readouterr().err == ""

    def test_broken_run_json_falls_back(self, tmp_path) -> None:
        d = _make_task_dir(tmp_path, "t001")
        (d / "run.json").write_text("{ not json", encoding="utf-8")
        assert _reap_status(d, 1, "t001") == "failed"

    def test_no_task_dir_falls_back(self) -> None:
        assert _reap_status(None, 1, "t001") == "failed"
        assert _reap_status(None, 0, "t002") == "done"

    def test_reap_status_never_writes_run_json(self, tmp_path) -> None:
        d = _make_task_dir(tmp_path, "t001")
        path = _write_run_json(d, "needs-clarification")
        before = path.read_text(encoding="utf-8")
        _reap_status(d, 0, "t001")
        assert path.read_text(encoding="utf-8") == before


# ── End-to-end: the reap path inside one poll ────────────────────────────────


class TestReapProductFirstEndToEnd:
    def test_a_needs_clarification_row_written_by_reap(self, tmp_path) -> None:
        d = _make_task_dir(tmp_path, "t001")
        _write_run_json(d, "needs-clarification")
        q = _write_queue(tmp_path, _entry(d / "task.md", task_key="t001"))

        running: dict = {"t001": _FinishedProc(0)}
        _poll_once(tmp_path, {}, running, {}, [], None)

        assert running == {}
        assert _row_statuses(q)["t001"] == "needs-clarification"

    def test_b_done_row_written_by_reap(self, tmp_path) -> None:
        d = _make_task_dir(tmp_path, "t001")
        _write_run_json(d, "done", artifacts=["report.md"])
        q = _write_queue(tmp_path, _entry(d / "task.md", task_key="t001"))

        _poll_once(tmp_path, {}, {"t001": _FinishedProc(0)}, {}, [], None)

        assert _row_statuses(q)["t001"] == "done"

    def test_c_missing_run_json_exit_one_is_failed(self, tmp_path) -> None:
        d = _make_task_dir(tmp_path, "t001")
        q = _write_queue(tmp_path, _entry(d / "task.md", task_key="t001"))

        _poll_once(tmp_path, {}, {"t001": _FinishedProc(1)}, {}, [], None)

        assert _row_statuses(q)["t001"] == "failed"

    def test_d_lost_row_written_by_reap(self, tmp_path) -> None:
        d = _make_task_dir(tmp_path, "t001")
        _write_run_json(d, "lost")
        q = _write_queue(tmp_path, _entry(d / "task.md", task_key="t001"))

        _poll_once(tmp_path, {}, {"t001": _FinishedProc(1)}, {}, [], None)

        assert _row_statuses(q)["t001"] == "lost"

    def test_e_conflict_line_lands_in_launcher_log(self, tmp_path) -> None:
        # `mw serve` runs the launcher with stderr redirected to
        # `.mw/launcher.log` (mw.py:334). Redirect identically here so the
        # conflict line is proven to land in the real log file, not just on a
        # captured stream.
        d = _make_task_dir(tmp_path, "t001")
        _write_run_json(d, "needs-clarification")
        q = _write_queue(tmp_path, _entry(d / "task.md", task_key="t001"))
        mw_dir = tmp_path / ".mw"
        mw_dir.mkdir(parents=True, exist_ok=True)
        log_path = mw_dir / "launcher.log"

        with log_path.open("w", encoding="utf-8") as fh, contextlib.redirect_stderr(fh):
            _poll_once(tmp_path, {}, {"t001": _FinishedProc(0)}, {}, [], None)

        text = log_path.read_text(encoding="utf-8")
        assert "reap status conflict" in text
        assert "run.json=needs-clarification" in text
        assert "exit=0" in text
        assert "used=needs-clarification" in text
        assert _row_statuses(q)["t001"] == "needs-clarification"

    def test_conflict_never_prints_to_stdout(self, tmp_path, capsys) -> None:
        # `mw doctor` JSON contract: the conflict line goes to stderr (captured
        # into launcher.log), never to stdout.
        d = _make_task_dir(tmp_path, "t001")
        _write_run_json(d, "done")  # run=done vs exit=1 => conflict
        q = _write_queue(tmp_path, _entry(d / "task.md", task_key="t001"))

        _poll_once(tmp_path, {}, {"t001": _FinishedProc(1)}, {}, [], None)

        captured = capsys.readouterr()
        assert "reap status conflict" in captured.err
        assert captured.out == ""
        assert _row_statuses(q)["t001"] == "done"


# ── VC-030 evidence line ─────────────────────────────────────────────────────


def test_vc030_verify_line(tmp_path: pathlib.Path, capsys) -> None:
    nc = _make_task_dir(tmp_path, "t_nc")
    _write_run_json(nc, "needs-clarification")
    done = _make_task_dir(tmp_path, "t_done")
    _write_run_json(done, "done")
    missing = _make_task_dir(tmp_path, "t_missing")
    lost = _make_task_dir(tmp_path, "t_lost")
    _write_run_json(lost, "lost")

    nc_row = _reap_status(nc, 0, "t_nc")
    conflict_err = capsys.readouterr().err
    done_row = _reap_status(done, 0, "t_done")
    missing_row = _reap_status(missing, 1, "t_missing")
    lost_row = _reap_status(lost, 1, "t_lost")

    assert nc_row == "needs-clarification"
    assert done_row == "done"
    assert missing_row == "failed"
    assert lost_row == "lost"
    conflict_logged = (
        "run.json=needs-clarification" in conflict_err and "exit=0" in conflict_err
    )
    assert conflict_logged
    _emit_verify(
        capsys,
        "[VERIFY] VC-030: "
        f"nc_exit0_row={nc_row} done_exit0={done_row} "
        f"missing_run_exit1={missing_row} lost={lost_row} "
        f"conflict_logged={str(conflict_logged).lower()}",
    )
