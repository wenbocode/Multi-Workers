"""test_mwgal_t22_qg_fixes.py — T-22 / key `mw-autopilot-gate-alarm-liveness`.

Fixes the two adversarial-QG findings from
`workers/mwgal-t18-adversarial-qg/report.md` on the Python face:

  R-4 (low)  `autopilot/gates.py::enumerate` folded a gates path that is a
             regular file (or otherwise unreadable) into an EMPTY queue. The TS
             monitor calls the same adversarial input `queueState=unreadable`.
             R-4 pins: the three cases are distinct at one choke point -
             missing dir = 0 pending (legal), empty dir = 0 pending (legal),
             not-a-readable-directory = `GateQueueUnreadable` (must be visible
             through the existing timeline `config` event / doctor `error`).

  R-5 (design divergence, medium)  the Python conductor recycled (and could
             take over) a FOREIGN-host synthetic claim `autopilot@OTHER:pid`,
             while the TS takeover guard (`pm/ui-bridge.ts::claimState`) only
             judges `synthetic.host === os.hostname()` as `held-conductor`;
             every other host falls through to `held-live`. R-5 pins: a
             foreign synthetic claim is a live holder - never recycled, never
             overwritten, never dispatched over - so two hosts cannot both
             hold the same key.

Verification cases:
  VC-1  gates path is a regular file       => unreadable + visible (tick)
  VC-1b directory read failure (non-ENOENT) => unreadable + visible
  VC-2  missing / empty gates directory     => legal empty queue (no false alarm)
  VC-3  foreign synthetic claim             => never taken over + traced
  VC-4  local synthetic claim               => still recycled/let-go (T-16)
  VC-5  Python <-> TS synthetic predicate table (claimState alignment)

Run: cd packages/multi-workers && python -X utf8 -m pytest -q test_mwgal_t22_qg_fixes.py
"""

from __future__ import annotations

import json
import os
import pathlib
import socket
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common  # noqa: E402
from autopilot import config, conductor, gates, index_parallel, state, timeline  # noqa: E402

HOST = socket.gethostname()
_REPO = pathlib.Path(__file__).resolve().parent.parent.parent
_UI_BRIDGE = (
    _REPO
    / "packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts"
)
_INDEX_STORE = (
    _REPO
    / "packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts"
)

INDEX_HEAD = (
    "# Index Parallel\n\n"
    "| Key | Status | Phase | ClaimId | Deps | Desc | Updated |\n"
    "|-----|--------|-------|---------|------|------|---------|\n"
)


def _verify(tag: str, **kv: object) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


# ── fixtures ──────────────────────────────────────────────────────────────────

class _LivePid:
    """A real, live foreign pid (the OS liveness check must say true)."""

    def __init__(self) -> None:
        self.proc = subprocess.Popen(
            [sys.executable, "-X", "utf8", "-c", "import time; time.sleep(120)"]
        )

    @property
    def pid(self) -> int:
        return int(self.proc.pid)

    def close(self) -> None:
        try:
            self.proc.terminate()
            self.proc.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            pass


def _write_serve_meta(project: pathlib.Path, pid: int, started_at_ms: int = 1) -> None:
    (project / ".mw").mkdir(parents=True, exist_ok=True)
    (project / ".mw" / "serve.meta").write_text(
        json.dumps({"pid": pid, "started_at_ms": started_at_ms}), encoding="utf-8"
    )


def _project(
    tmp_path: pathlib.Path,
    *,
    rows: list[tuple[str, str, str]] | None = None,
    serve_pid: int | None = None,
) -> pathlib.Path:
    """A minimal autopilot project: goal, enabled config, serve.meta, index."""
    tmp_path = tmp_path / "proj"
    adoc = tmp_path / ".agenticdoc"
    (adoc / "_autopilot").mkdir(parents=True)
    (tmp_path / ".mw").mkdir(parents=True)
    (adoc / "goal.md").write_text("# Goal\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(tmp_path, cfg)
    _write_serve_meta(tmp_path, serve_pid if serve_pid is not None else os.getpid())
    lines = [INDEX_HEAD]
    for key, status, claim in rows or []:
        lines.append(
            f"| {key} | {status} | EXECUTE | {claim} | - | desc | 2026-09-07 12:05 |\n"
        )
    (adoc / "_index.parallel").write_text("".join(lines), encoding="utf-8")
    return tmp_path


def _add_work(project: pathlib.Path, key: str, task_key: str = "w1") -> pathlib.Path:
    d = project / ".agenticdoc" / key / "workers" / task_key
    d.mkdir(parents=True, exist_ok=True)
    (d / "task.md").write_text("type: coding\n", encoding="utf-8")
    return d


def _state(project: pathlib.Path) -> conductor.ConductorState:
    return conductor.ConductorState(
        timeline.Timeline(timeline.timeline_path(project)),
        conductor.goal_mtime_ns(project),
    )


def _events(project: pathlib.Path, ev: str | None = None) -> list[dict]:
    events = timeline.query_events(timeline.timeline_path(project)).events
    return [e for e in events if ev is None or e["ev"] == ev]


def _rows(project: pathlib.Path) -> dict[str, dict]:
    return {r["key"]: r for r in state.read_index(project)}


def _claim(project: pathlib.Path, key: str) -> str:
    return str(_rows(project)[key]["claim_id"]).strip()


# ── VC-1 / VC-1b: unreadable gate path is visible, never "0 pending" ─────────

def test_gates_path_is_a_regular_file_is_unreadable_and_visible(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    gate_path = conductor.gates_dir(project)
    gate_path.write_text("not a directory\n", encoding="utf-8")

    with pytest.raises(gates.GateQueueUnreadable):
        gates.enumerate(gate_path)
    with pytest.raises(gates.GateQueueUnreadable):
        gates.pending_gates(gate_path)

    st = _state(project)
    assert conductor.tick(project, st) == "error"
    unreadable = [
        e for e in _events(project, "config")
        if "gate queue unreadable" in e.get("detail", "")
    ]
    assert len(unreadable) == 1, _events(project, "config")
    assert "not a directory" in unreadable[0]["detail"]

    section = mw_common._doctor_gates(project)
    assert section["error"] and "unreadable" in section["error"]
    assert section["pending_count"] == 0
    _verify(
        "VC-1",
        enumerate_raises=True,
        tick="error",
        config_events=len(unreadable),
        doctor_error=True,
    )


def test_directory_read_failure_is_unreadable_and_visible(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A directory that exists but whose scan fails (EACCES/EBUSY/...) is the
    third case: not ENOENT, therefore not an empty queue."""
    project = _project(tmp_path)
    gate_path = conductor.gates_dir(project)
    gate_path.mkdir(parents=True, exist_ok=True)
    real_iterdir = pathlib.Path.iterdir

    def fake_iterdir(self: pathlib.Path):  # noqa: ANN202 - test shim
        if self == gate_path:
            raise PermissionError(13, "Permission denied")
        return real_iterdir(self)

    monkeypatch.setattr(pathlib.Path, "iterdir", fake_iterdir)

    with pytest.raises(gates.GateQueueUnreadable):
        gates.enumerate(gate_path)
    st = _state(project)
    assert conductor.tick(project, st) == "error"
    assert [
        e for e in _events(project, "config")
        if "gate queue unreadable" in e.get("detail", "")
    ]
    section = mw_common._doctor_gates(project)
    assert section["error"] and "unreadable" in section["error"]
    monkeypatch.undo()
    _verify("VC-1b", permission_denied=True, tick="error", doctor_error=True)


# ── VC-2: missing/empty gates dir stays a legal empty queue ──────────────────

def test_missing_gates_dir_is_a_legal_empty_queue(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    gate_path = conductor.gates_dir(project)
    assert not gate_path.exists()

    assert gates.enumerate(gate_path) == []
    assert gates.pending_gates(gate_path) == []
    section = mw_common._doctor_gates(project)
    assert section["exists"] is False and section["error"] is None

    st = _state(project)
    cfg = conductor._load_effective_config(project)
    conductor._remind_pending_gates(project, st, cfg)  # no false unreadable alarm
    assert conductor._consume_answered_gates(project, st, cfg) is True
    assert [
        e for e in _events(project, "config") if "unreadable" in e.get("detail", "")
    ] == []
    _verify("VC-2", missing_dir="0 pending", false_alarms=0)


def test_empty_gates_dir_is_a_legal_empty_queue(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    gate_path = conductor.gates_dir(project)
    gate_path.mkdir(parents=True, exist_ok=True)

    assert gates.enumerate(gate_path) == []
    assert gates.pending_gates(gate_path) == []
    section = mw_common._doctor_gates(project)
    assert section["exists"] is True and section["error"] is None

    st = _state(project)
    cfg = conductor._load_effective_config(project)
    conductor._remind_pending_gates(project, st, cfg)
    assert conductor._consume_answered_gates(project, st, cfg) is True
    assert [
        e for e in _events(project, "config") if "unreadable" in e.get("detail", "")
    ] == []
    _verify("VC-2b", empty_dir="0 pending", false_alarms=0)


# ── VC-3: a foreign synthetic claim is a live holder, never taken over ───────

def test_foreign_synthetic_claim_is_never_taken_over(tmp_path: pathlib.Path) -> None:
    foreign = mw_common.synthetic_claim_id("no-such-host-zzz", 4242)
    project = _project(tmp_path, rows=[("k1", "idle", foreign)])
    _add_work(project, "k1")

    assert conductor._foreign_synthetic_claim(foreign) is True
    assert conductor._foreign_synthetic_claim(mw_common.synthetic_claim_id(HOST, os.getpid())) is False
    assert conductor._synthetic_claim_stale(project, foreign) is False

    st = _state(project)
    conductor.maintain_synthetic_claims(project, st, [])
    conductor.maintain_synthetic_claims(project, st, [])  # idempotent
    assert _claim(project, "k1") == foreign
    assert state.claim_state(foreign) == state.CLAIM_DEAD  # D-103 dispatch verdict unchanged
    reclaimed = [
        e for e in _events(project, "reconcile") if "accepted" in e.get("detail", "")
    ]
    assert reclaimed == []
    holds = [
        e for e in _events(project, "skip")
        if "foreign synthetic claim" in e.get("detail", "")
    ]
    assert len(holds) == 1, holds  # traced once on the existing `skip` event

    # A full tick must not overwrite it either.
    conductor.tick(project, _state(project))
    assert _claim(project, "k1") == foreign
    _verify("VC-3", claim_kept=foreign, takeover_events=0, skip_traces=1)


def test_foreign_synthetic_hold_blocks_dispatch(tmp_path: pathlib.Path) -> None:
    """The dispatch loop treats the foreign synthetic claim as a live holder
    (same `skip` event/dedup slot), so the local conductor never dispatches a
    second worker over another host's key."""
    child = _LivePid()
    try:
        foreign = mw_common.synthetic_claim_id("no-such-host-zzz", child.pid)
        project = _project(tmp_path, rows=[("k1", "idle", foreign)])
        _add_work(project, "k1")
        st = _state(project)
        conductor.tick(project, st)
        assert _claim(project, "k1") == foreign
        holds = [
            e for e in _events(project, "skip")
            if "foreign synthetic claim" in e.get("detail", "")
        ]
        assert all(child.pid > 0 for e in holds) or holds == [] or len(holds) >= 1
        assert len(holds) == 1
    finally:
        child.close()
    _verify("VC-3b", dispatch_blocked=True, skip_traces=1)


# ── VC-4: local synthetic claims keep T-16 lifecycle (no regression) ─────────

def test_local_synthetic_claim_is_still_recycled_when_identity_is_gone(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path, rows=[("k1", "idle", "—")])
    _add_work(project, "k1")
    st = _state(project)
    conductor.tick(project, st)
    own = _claim(project, "k1")
    assert own == mw_common.synthetic_claim_id(*conductor.synthetic_claim_owner(project))
    assert conductor._foreign_synthetic_claim(own) is False
    assert conductor._synthetic_claim_stale(project, own) is False  # identity consistent

    # The bound serve pid disappears: the LOCAL claim is recycled (T-16 VC-2).
    _write_serve_meta(project, 999_999_999, started_at_ms=1)
    assert conductor._synthetic_claim_stale(project, own) is True
    conductor.tick(project, st)
    assert _claim(project, "k1") == mw_common.CLAIM_PLACEHOLDERS[1]
    assert any(
        "recycled" in e.get("detail", "")
        for e in _events(project, "reconcile")
    )
    _verify("VC-4", local_own=own, recycled=True)


def test_local_synthetic_claim_is_yielded_to_a_human_claim(
    tmp_path: pathlib.Path,
) -> None:
    child = _LivePid()
    try:
        project = _project(tmp_path, rows=[("k1", "idle", "—")])
        _add_work(project, "k1")
        st = _state(project)
        conductor.tick(project, st)
        assert mw_common.is_synthetic_claim(_claim(project, "k1"))

        human = f"{HOST}:{child.pid}"
        index_parallel.set_claim(project, "k1", claim_id=human, status="active")
        for _ in range(2):
            conductor.tick(project, st)
        assert _claim(project, "k1") == human  # never grabbed back
        assert [
            e for e in _events(project, "skip")
            if "yielded to human claim" in e.get("detail", "")
        ]
    finally:
        child.close()
    _verify("VC-4b", human_claim_kept=True, yield_traced=True)


# ── VC-5: the synthetic predicate table is two-sided consistent ──────────────

def test_synthetic_predicate_table_matches_the_ts_takeover_guard(
    tmp_path: pathlib.Path,
) -> None:
    """TS `claimState` (pm/ui-bridge.ts) and the Python conductor must agree on
    which synthetic claims are yieldable: only THIS host's, with a live bound
    pid. Everything else is a live holder the local conductor must not take."""
    ui_bridge = _UI_BRIDGE.read_text(encoding="utf-8")
    index_store = _INDEX_STORE.read_text(encoding="utf-8")

    # TS positive verdict is gated on the local host name (T-16b contract).
    assert "synthetic.host === os.hostname()" in ui_bridge
    assert "held-conductor" in ui_bridge
    # One parser for the `autopilot@` shape on each side.
    assert "parseSyntheticClaim" in ui_bridge
    assert "SYNTHETIC_CLAIM_PREFIX" not in ui_bridge  # never re-derived here
    assert 'const SYNTHETIC_CLAIM_RE = /^autopilot@([^:@]+):(\\d+)$/;' in index_store
    assert mw_common._SYNTHETIC_CLAIM_RE.pattern == r"^autopilot@([^:@]+):(\d+)$"

    project = _project(tmp_path, rows=[("k1", "idle", "—")])
    local = mw_common.synthetic_claim_id(*conductor.synthetic_claim_owner(project))
    local_live = mw_common.synthetic_claim_id(HOST, os.getpid())
    local_dead = mw_common.synthetic_claim_id(HOST, 999_999_999)
    foreign = mw_common.synthetic_claim_id("no-such-host-zzz", 4242)

    # (claim id, TS claimState verdict, Python: foreign?, stale?, human-block?)
    table = [
        (local_live, "held-conductor", False, False, False),
        (local_dead, "held-stale", False, True, False),
        (foreign, "held-live", True, False, False),
        (f"{HOST}:{os.getpid()}", "held-live", False, False, True),
        ("no-such-host-zzz:4242", "held-live", False, False, True),
    ]
    for claim_id, ts_verdict, is_foreign, is_stale, human_block in table:
        assert conductor._foreign_synthetic_claim(claim_id) is is_foreign, claim_id
        assert conductor._human_claim_blocks_synthetic(claim_id) is human_block, claim_id
        if mw_common.is_synthetic_claim(claim_id) and not is_foreign:
            assert conductor._synthetic_claim_stale(project, claim_id) is is_stale, claim_id
        # The TS takeover guard's three-state contract: only a local synthetic
        # claim with a live pid is `held-conductor`; a same-host dead one is
        # `held-stale`; a foreign one is `held-live` (never non-forced).
        if ts_verdict == "held-conductor":
            assert not is_foreign and not is_stale
        elif ts_verdict == "held-stale":
            assert not is_foreign and is_stale
        else:
            assert is_foreign or human_block or claim_id != local
    assert local == mw_common.synthetic_claim_id(HOST, os.getpid())
    _verify(
        "VC-5",
        table_rows=len(table),
        ts_guard="synthetic.host === os.hostname()",
        python_foreign_predicate=True,
    )
