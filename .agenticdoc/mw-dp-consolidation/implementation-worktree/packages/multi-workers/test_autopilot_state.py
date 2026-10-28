"""
test_autopilot_state.py — L1 tests for autopilot/state.py (T-07, AC-013/014/
018/022 derivation sources; VC-015/VC-016/VC-020/VC-024 prerequisites).

All fixtures build their own project trees under tmp_path; the claim tests
use this process's own pid (live) and a genuinely exited child pid (dead —
on Windows an exited pid still opens via OpenProcess, which is exactly the
quirk mw_common._is_alive handles).
"""
import os
import pathlib
import socket
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common
from autopilot import state


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


HOST = socket.gethostname()


@pytest.fixture()
def dead_pid() -> int:
    """A pid that has really exited (Windows: OpenProcess succeeds but the
    exit code is no longer STILL_ACTIVE)."""
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _write_task(workers_dir: pathlib.Path, task_key: str, labels: dict[str, str]) -> pathlib.Path:
    task_dir = workers_dir / task_key
    task_dir.mkdir(parents=True, exist_ok=True)
    lines = ["---"]
    for name, value in labels.items():
        lines.append(f"{name}: {value}")
    lines += ["---", "", "body"]
    (task_dir / "task.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return task_dir


# ── claim_state: live / dead / stale / free (conductor-side rule) ─────────────

def test_claim_states(dead_pid: int) -> None:
    assert state.claim_state(f"{HOST}:{os.getpid()}") == state.CLAIM_LIVE
    assert state.claim_state(f"{HOST}:{dead_pid}") == state.CLAIM_DEAD
    assert state.claim_state(f"{HOST}:0") == state.CLAIM_STALE  # pid must be > 0
    assert state.claim_state(f"{HOST}:notanumber") == state.CLAIM_STALE
    assert state.claim_state("legacy-20260101-123") == state.CLAIM_STALE  # F9
    assert state.claim_state("") == state.CLAIM_FREE
    assert state.claim_state("—") == state.CLAIM_FREE
    # Deliberate conductor-side asymmetry vs TS claimState: a foreign host is
    # NOT live for the conductor (T-07/D-103; TS treats it as held-live).
    assert state.claim_state("no-such-host-xyz:4242") == state.CLAIM_DEAD
    # Own claim does not block the caller.
    self_id = f"{HOST}:{os.getpid()}"
    assert state.claim_state(self_id, self_id=self_id) == state.CLAIM_FREE
    _verify(
        "VC-015",
        live=1, dead=1, stale=1, free=1,
        host_mismatch_dead=true_str(state.claim_state("no-such-host-xyz:4242") == state.CLAIM_DEAD),
        self_not_blocking=true_str(state.claim_state(self_id, self_id=self_id) == state.CLAIM_FREE),
    )


def true_str(b: bool) -> str:
    return "true" if b else "false"


# ── key phase/claim derivation from _index.parallel ──────────────────────────

INDEX_TEXT = f"""| Key | Status | Phase | Claim-Id | Deps | Desc | Updated |
|---|---|---|---|---|---|---|
| k1 | active | EXECUTE | {HOST}:{{LIVE}} | — | d1 | 2026-09-10T00:00:00Z |
| k2 | idle | PLAN | {HOST}:{{DEAD}} | k1 | d2 | 2026-09-10T00:00:00Z |

| k3 | active | legacy-20260101-123 | legacy five col | 2026-09-09 |
"""


def _write_index(project: pathlib.Path, live_pid: int, dead_pid: int) -> None:
    text = INDEX_TEXT.replace("{LIVE}", str(live_pid)).replace("{DEAD}", str(dead_pid))
    # Trailing spaces on one row exercise the tolerance rule.
    text = text.replace("d1 | 2026-09-10T00:00:00Z |", "d1 | 2026-09-10T00:00:00Z |   ")
    index = project / ".agenticdoc" / "_index.parallel"
    index.parent.mkdir(parents=True, exist_ok=True)
    index.write_text(text, encoding="utf-8")


def test_read_key_states(tmp_path: pathlib.Path, dead_pid: int) -> None:
    _write_index(tmp_path, os.getpid(), dead_pid)
    states = state.read_key_states(tmp_path)
    assert set(states) == {"k1", "k2", "k3"}
    assert states["k1"].phase == "EXECUTE"
    assert states["k1"].status == "active"
    assert states["k1"].claim == state.CLAIM_LIVE
    assert states["k2"].claim == state.CLAIM_DEAD
    # Legacy 5-column row migrates: claim_id from col 3, phase placeholder.
    assert states["k3"].claim_id == "legacy-20260101-123"
    assert states["k3"].claim == state.CLAIM_STALE
    assert states["k3"].phase == "—"
    _verify("VC-016", phase_rows=len(states), legacy_5col=true_str(states["k3"].claim_id == "legacy-20260101-123"))


def test_read_key_states_missing_index(tmp_path: pathlib.Path) -> None:
    assert state.read_key_states(tmp_path) == {}
    assert state.read_index(tmp_path) == []


# ── loop round counting (D-102/D-111 round unit table) ────────────────────────

def _rounds_fixture(project: pathlib.Path) -> None:
    k1w = project / ".agenticdoc" / "k1" / "workers"
    _write_task(k1w, "verifier-1", {"loop": "l2:k1:spec-to-design", "attempt": "1"})
    # Same-round repair dispatch (phase-writer evidence patch): same loop,
    # same attempt -> not a new round.
    _write_task(k1w, "patch-1", {"loop": "l2:k1:spec-to-design", "attempt": "1"})
    _write_task(k1w, "verifier-2", {"loop": "l2:k1:spec-to-design", "attempt": "2"})
    _write_task(k1w, "t-05", {"loop": "exec:k1:t-05", "attempt": "1"})
    _write_task(k1w, "fix-1", {"loop": "repair:k1", "attempt": "1"})
    scratch_w = project / ".agenticdoc" / "_scratch" / "workers"
    _write_task(scratch_w, "rw-1", {"loop": "roadmap:stage-1", "attempt": "1"})
    # No loop label (manual task): invisible to round budgets.
    _write_task(k1w, "manual-task", {"type": "coding"})


def test_used_rounds(tmp_path: pathlib.Path) -> None:
    _rounds_fixture(tmp_path)
    rounds = state.used_rounds([
        tmp_path / ".agenticdoc" / "k1" / "workers",
        tmp_path / ".agenticdoc" / "_scratch" / "workers",
    ])
    assert rounds == {
        "l2:k1:spec-to-design": 2,  # 2 distinct attempts (repair shared attempt 1)
        "exec:k1:t-05": 1,
        "repair:k1": 1,
        "roadmap:stage-1": 1,
    }
    _verify(
        "VC-020",
        l2_rounds=rounds["l2:k1:spec-to-design"],
        repair_same_round_not_counted=true_str(rounds["l2:k1:spec-to-design"] == 2),
        exec_rounds=rounds["exec:k1:t-05"],
        roadmap_rounds=rounds["roadmap:stage-1"],
        manual_invisible=true_str("manual-task" not in str(rounds)),
    )


def test_used_rounds_attempt_fallback(tmp_path: pathlib.Path) -> None:
    """Missing attempt labels degrade to per-directory counting (D-102's
    original file-count semantics); rewriting a dir never double-counts."""
    k1w = tmp_path / ".agenticdoc" / "k1" / "workers"
    _write_task(k1w, "a", {"loop": "l3:k1"})
    _write_task(k1w, "b", {"loop": "l3:k1"})
    rounds = state.used_rounds([k1w])
    assert rounds == {"l3:k1": 2}
    _write_task(k1w, "a", {"loop": "l3:k1"})  # rewrite same dir
    assert state.used_rounds([k1w]) == {"l3:k1": 2}
    _verify("VC-020", attempt_fallback_dirs=2)


def test_used_rounds_missing_dir(tmp_path: pathlib.Path) -> None:
    assert state.used_rounds([tmp_path / ".agenticdoc" / "nope" / "workers"]) == {}


# ── [START] process observation (D-115) ───────────────────────────────────────

def test_start_pids(tmp_path: pathlib.Path, dead_pid: int) -> None:
    task_dir = tmp_path / "task"
    task_dir.mkdir()
    trace = task_dir / "trace.log"
    trace.write_text(
        f"noise\n"
        f"[START] pid={os.getpid()}\n"
        f"[START] pid={dead_pid}\n"
        f"[START] pid=notapid\n"  # malformed: ignored
        f"[START] pid={dead_pid} extra\n"  # trailing junk: ignored
        f"more noise\n",
        encoding="utf-8",
    )
    assert state.start_pids(task_dir) == [os.getpid(), dead_pid]
    assert state.live_start_pids(task_dir) == [os.getpid()]
    assert state.start_pids(tmp_path / "absent") == []
    _verify(
        "VC-024",
        start_lines=len(state.start_pids(task_dir)),
        live_pids=len(state.live_start_pids(task_dir)),
        malformed_ignored=true_str(len(state.start_pids(task_dir)) == 2),
    )


# ── orphan reconciliation (D-102) ─────────────────────────────────────────────

def _queue_row(task_key: str, task_path: pathlib.Path) -> dict[str, str]:
    return {
        "task_key": task_key,
        "status": "running",
        "cli": "pi",
        "provider": "",
        "task_path": str(task_path),
        "dispatched_at": "2026-09-10T00:00:00Z",
        "updated_at": "2026-09-10T00:00:00Z",
        "model": "",
    }


def test_find_orphans(tmp_path: pathlib.Path) -> None:
    agenticdoc = tmp_path / ".agenticdoc"
    k1w = agenticdoc / "k1" / "workers"
    # Orphan: conductor origin, no queue row (never spawned).
    orphan_dir = _write_task(
        k1w, "ap-k1-t06", {"origin": "conductor", "loop": "exec:k1:t-06", "attempt": "1"}
    )
    # Not an orphan: conductor origin, row present (forward slashes in the
    # row path exercise the normalization).
    tracked_dir = _write_task(
        k1w, "ap-k1-t05", {"origin": "conductor", "loop": "exec:k1:t-05", "attempt": "1"}
    )
    # Manual task without a row: not conductor's business.
    _write_task(k1w, "manual-1", {"type": "coding"})
    # _scratch conductor task with a row: not an orphan.
    scratch_tracked = _write_task(
        agenticdoc / "_scratch" / "workers", "ap--scratch-rw",
        {"origin": "conductor", "loop": "roadmap:stage-1", "attempt": "1"},
    )

    wpath = mw_common.workers_path(tmp_path)
    wpath.parent.mkdir(parents=True, exist_ok=True)
    wpath.write_text(
        "\n".join([
            mw_common.serialize_entry(_queue_row("ap-k1-t05", tracked_dir / "task.md")),
            mw_common.serialize_entry(
                _queue_row("ap--scratch-rw", scratch_tracked / "task.md")
            ).replace("\\", "/"),  # slash-style row path must still match
        ]) + "\n",
        encoding="utf-8",
    )

    orphans = state.find_orphans(tmp_path)
    assert [o.task_key for o in orphans] == ["ap-k1-t06"]
    assert orphans[0].loop == "exec:k1:t-06"
    assert orphans[0].attempt == 1
    assert orphans[0].origin == "conductor"
    assert orphans[0].task_dir == orphan_dir
    _verify(
        "VC-024",
        orphans=len(orphans),
        slash_path_match=true_str(len(orphans) == 1),
        manual_not_orphan=true_str(all(o.task_key != "manual-1" for o in orphans)),
    )


def test_find_orphans_no_queue_file(tmp_path: pathlib.Path) -> None:
    k1w = tmp_path / ".agenticdoc" / "k1" / "workers"
    _write_task(k1w, "ap-k1-x", {"origin": "conductor"})
    orphans = state.find_orphans(tmp_path)
    assert [o.task_key for o in orphans] == ["ap-k1-x"]


# ── artifact mtime snapshots (AC-014/AC-022) ──────────────────────────────────

def test_artifact_mtimes(tmp_path: pathlib.Path) -> None:
    key_dir = tmp_path / "goal-key"
    key_dir.mkdir()
    for name in ("spec.md", "design.md"):
        (key_dir / name).write_text("x", encoding="utf-8")
    tasks = key_dir / "tasks"
    tasks.mkdir()
    (tasks / "T-01-alpha.md").write_text("x", encoding="utf-8")
    (tasks / "T-02-beta.md").write_text("x", encoding="utf-8")

    snap1 = state.artifact_mtimes(key_dir)
    assert snap1.spec is not None and snap1.design is not None
    assert snap1.plan is None  # absent -> None, not an error
    assert list(snap1.tasks) == ["T-01-alpha", "T-02-beta"]
    assert all(v is not None for v in snap1.tasks.values())

    # Stable across re-reads; changes when a file is touched.
    snap2 = state.artifact_mtimes(key_dir)
    assert snap1 == snap2
    (tasks / "T-01-alpha.md").write_text("changed", encoding="utf-8")
    snap3 = state.artifact_mtimes(key_dir)
    assert snap3.tasks["T-01-alpha"] >= snap1.tasks["T-01-alpha"]
    assert snap3.tasks["T-02-beta"] == snap1.tasks["T-02-beta"]

    # Empty key dir: all None, no crash.
    empty = state.artifact_mtimes(tmp_path / "nope")
    assert empty.spec is None and empty.tasks == {}
    _verify("VC-024", artifact_snapshot=true_str(snap1 == snap2), tasks_tracked=len(snap1.tasks))


# ── task label parsing tolerance ──────────────────────────────────────────────

def test_parse_task_labels_tolerant(tmp_path: pathlib.Path) -> None:
    task = tmp_path / "task.md"
    # Missing frontmatter entirely.
    task.write_text("no frontmatter here\n", encoding="utf-8")
    assert state.parse_task_labels(task) == {}
    # Garbled frontmatter: lenient, labels that parse still surface.
    task.write_text(
        "---\nloop: exec:k1:t-07  \nattempt: 3\nread_scope:\n  - .agenticdoc/x\n?? bad line\n---\n",
        encoding="utf-8",
    )
    labels = state.parse_task_labels(task)
    assert labels["loop"] == "exec:k1:t-07"  # trailing space tolerated
    assert labels["attempt"] == "3"
    assert "read_scope" in labels  # nested block value is skipped, key kept
    assert state.parse_task_labels(tmp_path / "absent.md") == {}
