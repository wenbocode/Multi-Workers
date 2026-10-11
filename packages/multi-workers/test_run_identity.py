"""T-20 (AC-022/D-022): the Python side of the product-carried run record.

The worker (TS, ``shared/run-store.ts``) owns ``running`` and every terminal
state; the launcher may only ever ADD ``lost`` when a process that recorded
itself as running is gone with no verified outcome. These tests pin that
division, the record shape the launcher must read, and the fail-safe behaviour
of ``mw_common.mark_run_lost``.
"""

import json
import pathlib

import mw_common
import pytest

# The TS `RunStatus` union end (shared/run-store.ts RUN_TERMINAL_STATUSES).
# Asserted literally on both sides, which is what makes it a cross-language
# contract instead of two drifting copies.
TS_TERMINAL_STATUSES = {"done", "failed", "needs-clarification", "lost"}


def _run_json(task_dir: pathlib.Path, status: str, **overrides) -> pathlib.Path:
    record = {
        "schema": 1,
        "task_key": overrides.pop("task_key", task_dir.name),
        "run_id": f"{task_dir.name}@2026-10-10T02:00:00.000Z",
        "owner_key": "k",
        "kind": "coding",
        "status": status,
        "started_at": "2026-10-10T02:00:00.000Z",
        "artifacts": ["output.md"],
    }
    record.update(overrides)
    path = task_dir / "run.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def test_terminal_status_sets_are_identical_across_languages() -> None:
    assert set(mw_common.RUN_TERMINAL_STATUSES) == TS_TERMINAL_STATUSES


def test_lost_is_terminal_for_the_ledger() -> None:
    assert "lost" in mw_common._TERMINAL_STATUSES


def test_read_run_status_accepts_the_worker_written_shape(tmp_path: pathlib.Path) -> None:
    _run_json(tmp_path, "running")
    assert mw_common.read_run_status(tmp_path) == "running"


@pytest.mark.parametrize("payload", ["{ not json", "[1, 2]", '{"task_key": "t"}'])
def test_read_run_status_is_no_information_for_broken_records(
    tmp_path: pathlib.Path, payload: str
) -> None:
    (tmp_path / "run.json").write_text(payload, encoding="utf-8")
    assert mw_common.read_run_status(tmp_path) is None


def test_mark_run_lost_preserves_the_scene(tmp_path: pathlib.Path) -> None:
    path = _run_json(
        tmp_path,
        "running",
        supersedes="t-0",
        pid=4242,
        last_heartbeat_at="2026-10-10T02:05:00.000Z",
    )

    assert mw_common.mark_run_lost(tmp_path) == "lost"

    record = json.loads(path.read_text(encoding="utf-8"))
    assert record["status"] == "lost"
    assert record["ended_at"]
    # Identity and evidence survive: the launcher adds a status, nothing else.
    assert record["run_id"] == f"{tmp_path.name}@2026-10-10T02:00:00.000Z"
    assert record["artifacts"] == ["output.md"]
    assert record["supersedes"] == "t-0"
    assert record["pid"] == 4242
    assert record["last_heartbeat_at"] == "2026-10-10T02:05:00.000Z"
    assert not (tmp_path / "run.json.tmp").exists()


def test_mark_run_lost_drops_a_stale_exit_code(tmp_path: pathlib.Path) -> None:
    # A record that claims to be running must not keep an exit code from an
    # earlier write: `lost` means "no verified outcome".
    path = _run_json(tmp_path, "running", exit=0)
    mw_common.mark_run_lost(tmp_path)
    assert "exit" not in json.loads(path.read_text(encoding="utf-8"))


def test_mark_run_lost_is_fail_safe(tmp_path: pathlib.Path) -> None:
    # No record at all.
    assert mw_common.mark_run_lost(tmp_path) is None
    # A directory in the file slot: unreadable and unwritable, never raising.
    broken = tmp_path / "broken"
    (broken / "run.json").mkdir(parents=True)
    assert mw_common.mark_run_lost(broken) is None
