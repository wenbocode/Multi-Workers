"""
test_mwds_t10_dispatch_run_state.py — T-10 / AC-004 (DD-12, VC-012…VC-014).

The Python dispatch criterion must read the worker-written `run.json` FIRST
(T-20/D-022 single source, `mw_common.read_run_status`):

  - terminal status (RUN_TERMINAL_STATUSES) -> refuse, `run-terminal:<status>`
  - `running`                                -> refuse, `run-running`
  - no `run.json` / unreadable / no status   -> dispatch, byte-for-byte the
    historical behaviour (zero backfill)
  - unknown non-terminal status              -> dispatch + debug log (fail-open)

The refusal must happen before ANY side effect (no task dir, no task.md, no
queue row) and read the run state at most once per attempt.

Fixtures build their own project trees under tmp_path (queue file + run.json).
"""
import hashlib
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common
from autopilot import dispatch
from autopilot import timeline as timeline_mod

OWNER = "k1"
STEM = "t10"
TASK_KEY = "ap-k1-t10"
# Locked order for the VC-012 evidence line; membership is asserted against
# mw_common.RUN_TERMINAL_STATUSES (the single source of truth).
TERMINAL_ORDER = ("done", "needs-clarification", "failed", "lost")


def _verify(tag: str, body: str) -> None:
    print(f"[VERIFY] {tag}: {body}", flush=True)


def _true(b: bool) -> str:
    return "true" if b else "false"


def _task_dir(root: pathlib.Path) -> pathlib.Path:
    return root / ".agenticdoc" / OWNER / "workers" / TASK_KEY


def _write_run(root: pathlib.Path, status: str) -> pathlib.Path:
    task_dir = _task_dir(root)
    task_dir.mkdir(parents=True, exist_ok=True)
    (task_dir / "run.json").write_text(
        json.dumps({"run_id": "r-1", "status": status}), encoding="utf-8"
    )
    return task_dir


def _dispatch(root: pathlib.Path, **kwargs) -> dispatch.DispatchResult:
    return dispatch.dispatch(
        root, OWNER, STEM, "phase-writer", "Implement the change.",
        loop="exec:k1:t10", attempt=1, **kwargs,
    )


def _snapshot(root: pathlib.Path) -> dict[str, str]:
    """Every file under root -> sha256, so a refusal can be proven inert."""
    return {
        p.relative_to(root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(root.rglob("*"))
        if p.is_file()
    }


def _queue_bytes(root: pathlib.Path) -> bytes | None:
    path = mw_common.workers_path(root)
    return path.read_bytes() if path.exists() else None


# ── VC-012: terminal run.json refuses dispatch ────────────────────────────────

@pytest.mark.parametrize("status", sorted(mw_common.RUN_TERMINAL_STATUSES))
def test_terminal_run_status_refuses_dispatch(
    tmp_path: pathlib.Path, status: str
) -> None:
    tl = timeline_mod.Timeline(
        tmp_path / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
    )
    task_dir = _write_run(tmp_path, status)
    run_bytes = (task_dir / "run.json").read_bytes()

    result = _dispatch(tmp_path, timeline=tl)

    assert result.ok is False
    assert result.reason == f"run-terminal:{status}"
    assert result.task_key == TASK_KEY
    assert result.task_md is None and result.row_verified is False
    # Zero side effects: no task.md, no queue file, run.json untouched.
    assert not (task_dir / "task.md").exists()
    assert _queue_bytes(tmp_path) is None
    assert (task_dir / "run.json").read_bytes() == run_bytes
    # The refusal is observable on the timeline (same bucket as other
    # pre-dispatch refusals; no new event vocabulary).
    events = timeline_mod.query_events(tl.path).events
    assert [e["ev"] for e in events] == ["type-rejected"]
    assert TASK_KEY in events[0]["detail"] and status in events[0]["detail"]


def test_terminal_check_runs_before_type_validation(tmp_path: pathlib.Path) -> None:
    """AC-004 says FIRST criterion: a settled run wins over a bad type."""
    _write_run(tmp_path, "done")
    result = dispatch.dispatch(
        tmp_path, OWNER, STEM, "not-a-registered-type", "x",
        loop="exec:k1:t10", attempt=1,
    )
    assert result.ok is False
    assert result.reason == "run-terminal:done"


# ── VC-013: live run.json refuses dispatch ────────────────────────────────────

def test_running_run_status_refuses_dispatch(tmp_path: pathlib.Path) -> None:
    task_dir = _write_run(tmp_path, "running")
    result = _dispatch(tmp_path)
    assert result.ok is False
    assert result.reason == "run-running"
    assert result.task_md is None and result.row_verified is False
    assert not (task_dir / "task.md").exists()
    assert _queue_bytes(tmp_path) is None


def test_running_and_pending_are_distinct(tmp_path: pathlib.Path) -> None:
    """Only `running` blocks: a future non-terminal status stays fail-open."""
    _write_run(tmp_path, "pending")
    result = _dispatch(tmp_path)
    assert result.ok is True and result.row_verified is True


# ── VC-014: missing run.json dispatches unchanged (zero backfill) ─────────────

def test_missing_run_json_dispatches_byte_identically(tmp_path: pathlib.Path) -> None:
    result = _dispatch(tmp_path)
    assert result.ok is True and result.row_verified is True
    assert result.task_md is not None and result.task_md.is_file()
    # Literal from render_task_md (no phase/model/scope/target.yml): proving
    # the no-run.json path is word-for-word the pre-change rendering.
    assert result.task_md.read_text(encoding="utf-8") == (
        "---\n"
        "type: phase-writer\n"
        "origin: conductor\n"
        "loop: exec:k1:t10\n"
        "attempt: 1\n"
        "---\n"
        "\n"
        "Implement the change.\n"
        "\n"
    )
    rows = mw_common.parse_workers_file(mw_common.workers_path(tmp_path))
    assert [r["task_key"] for r in rows] == [TASK_KEY]
    assert rows[0]["status"] == "pending"


def test_broken_run_json_is_no_information(tmp_path: pathlib.Path) -> None:
    """Unreadable/empty run.json is `None`, so it keeps the fail-open path."""
    task_dir = _task_dir(tmp_path)
    task_dir.mkdir(parents=True)
    (task_dir / "run.json").write_text("{not json", encoding="utf-8")
    assert _dispatch(tmp_path).ok is True


def test_refusal_leaves_directory_and_queue_bytes_unchanged(
    tmp_path: pathlib.Path,
) -> None:
    """(e) The refusal path is a byte-level no-op (no timeline writer)."""
    wpath = mw_common.workers_path(tmp_path)
    wpath.parent.mkdir(parents=True, exist_ok=True)
    manual_row = mw_common.serialize_entry({
        "task_key": "manual-task", "status": "done", "cli": "pi", "provider": "",
        "task_path": str(tmp_path / "x" / "task.md"),
        "dispatched_at": "t0", "updated_at": "t0", "model": "",
    }) + "\n"
    wpath.write_text(manual_row, encoding="utf-8", newline="\n")
    _write_run(tmp_path, "done")

    before_tree = _snapshot(tmp_path)
    before_queue = _queue_bytes(tmp_path)
    result = _dispatch(tmp_path)
    after_tree = _snapshot(tmp_path)
    after_queue = _queue_bytes(tmp_path)

    assert result.ok is False and result.reason == "run-terminal:done"
    assert before_tree == after_tree
    assert before_queue == after_queue == manual_row.encode("utf-8")
    assert not (_task_dir(tmp_path) / "task.md").exists()
    assert not mw_common.lock_path(tmp_path).exists()


# ── read discipline + unknown status ─────────────────────────────────────────

@pytest.mark.parametrize("status", ["done", "running", None])
def test_run_status_is_read_exactly_once(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, status: str | None
) -> None:
    if status is not None:
        _write_run(tmp_path, status)
    calls: list[pathlib.Path] = []
    real = mw_common.read_run_status

    def counting_reader(task_dir: pathlib.Path) -> str | None:
        calls.append(pathlib.Path(task_dir))
        return real(task_dir)

    monkeypatch.setattr(mw_common, "read_run_status", counting_reader)
    _dispatch(tmp_path)

    assert len(calls) == 1, calls
    assert calls[0] == _task_dir(tmp_path)


def test_unknown_non_terminal_status_dispatches_with_debug(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Forward-compatible value: dispatch (fail-open) and log for diagnosis."""
    _write_run(tmp_path, "queued")
    result = _dispatch(tmp_path)
    assert result.ok is True and result.row_verified is True
    err = capsys.readouterr().err
    assert "unknown run.json status 'queued'" in err
    assert TASK_KEY in err


# ── [VERIFY] VC-012…VC-014 summary ───────────────────────────────────────────

def test_verify_vc012_vc013_vc014(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("MW_TARGET_GAME", raising=False)
    monkeypatch.delenv("MW_TARGET_ENGINE", raising=False)
    calls: list[pathlib.Path] = []
    real = mw_common.read_run_status

    def counting_reader(task_dir: pathlib.Path) -> str | None:
        calls.append(pathlib.Path(task_dir))
        return real(task_dir)

    monkeypatch.setattr(mw_common, "read_run_status", counting_reader)

    # VC-012: every terminal status blocks with a named reason.
    assert set(TERMINAL_ORDER) == set(mw_common.RUN_TERMINAL_STATUSES)
    blocked: list[str] = []
    for status in TERMINAL_ORDER:
        root = tmp_path / "terminal" / status
        root.mkdir(parents=True)
        _write_run(root, status)
        result = _dispatch(root)
        if not result.ok and result.reason == f"run-terminal:{status}":
            blocked.append(status)
    assert blocked == list(TERMINAL_ORDER)

    # VC-013: `running` blocks, one read.
    running_root = tmp_path / "running"
    running_root.mkdir()
    _write_run(running_root, "running")
    calls.clear()
    running = _dispatch(running_root)
    running_block = (not running.ok) and running.reason == "run-running"
    running_reads = len(calls)
    assert running_block and running_reads == 1

    # VC-014: missing run.json dispatches, one read, and the refusal path
    # (over the same queue) is byte-inert.
    missing_root = tmp_path / "missing"
    missing_root.mkdir()
    calls.clear()
    missing = _dispatch(missing_root)
    missing_dispatches = (
        missing.ok and missing.row_verified
        and missing.task_md is not None and missing.task_md.is_file()
    )
    missing_reads = len(calls)
    assert missing_dispatches and missing_reads == 1

    inert_root = tmp_path / "inert"
    inert_root.mkdir()
    wpath = mw_common.workers_path(inert_root)
    wpath.parent.mkdir(parents=True, exist_ok=True)
    wpath.write_text(
        mw_common.serialize_entry({
            "task_key": "manual-task", "status": "done", "cli": "pi",
            "provider": "", "task_path": str(inert_root / "x" / "task.md"),
            "dispatched_at": "t0", "updated_at": "t0", "model": "",
        }) + "\n",
        encoding="utf-8",
    )
    _write_run(inert_root, "done")
    before = _snapshot(inert_root)
    inert_result = _dispatch(inert_root)
    zero_side_effect = before == _snapshot(inert_root) and not inert_result.ok
    assert zero_side_effect

    _verify("VC-012", f"terminal_statuses_block={len(blocked)} ({','.join(blocked)})")
    _verify("VC-013", f"running_block={_true(running_block)}")
    _verify(
        "VC-014",
        f"missing_run_dispatches={_true(missing_dispatches)} "
        f"zero_side_effect={_true(zero_side_effect)} read_calls={missing_reads}",
    )
