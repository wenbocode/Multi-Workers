"""test_mwgal_t16_synthetic_claim.py — T-16 / AC-014 route ① (D-013).

The conductor takes over "has work but no live claim" keys with a SYNTHETIC
claim id (`autopilot@<host>:<pid>`), written into the framework's existing
`_index.parallel` claim cell by `autopilot/index_parallel.py` — the single
claim-cell writer, under the shared `.mw/index.lock`. These tests pin the six
regressions the card asks for:

  VC-1  no live claim + work   => claim created AND dispatch still happens
        (VC-1b: the conductor only stops blocking itself because it passes
        its own id as `self_id`)
  VC-2  renewal heartbeat + reclaim (owner gone, never a wall-clock guess;
        VC-2b: a live owner is never reclaimed no matter how old `Updated` is)
  VC-3  human takeover         => synthetic claim yields, is not re-claimed,
                                  and the handover/conflict leaves a trace
                                  (VC-3b: live + foreign human claims stay)
  VC-4  serve pid changes      => the previous instance's claim is invalid
        (VC-4b: a conductor older than its serve never claims)
  VC-5  index presentation     => field-level distinct, parsers still work
        (VC-5b: a legacy 5-column row is rewritten in place)
  VC-6  idle key without work  => still skipped (never taken over)
  VC-7  single-writer invariant=> only `_index.parallel` is written, the
                                  shared lock is released, queue bytes intact
  VC-8  claim_state            => synthetic live/dead/free/stale verdicts,
                                  human semantics unchanged

Run: cd packages/multi-workers && python -X utf8 -m pytest -q test_mwgal_t16_synthetic_claim.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import socket
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common  # noqa: E402
from autopilot import config, conductor, index_parallel, state, timeline  # noqa: E402

HOST = socket.gethostname()
_REPO = pathlib.Path(__file__).resolve().parent.parent.parent
_UPDATE_INDEX = _REPO / ".agents" / "skills" / "agentic-task" / "scripts" / "update_index.py"

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


def _human_claim(pid: int) -> str:
    """The claim id a human window writes (`<host>:<pid>`)."""
    return f"{HOST}:{pid}"


def _project(
    tmp_path: pathlib.Path,
    *,
    rows: list[tuple[str, str, str]] | None = None,
    serve_pid: int | None = None,
    roadmap: bool = False,
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
    if roadmap:
        _write_roadmap(tmp_path)
    return tmp_path


def _write_roadmap(project: pathlib.Path) -> None:
    (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        "# Roadmap\n"
        "> generated_at: 2026-09-10T00:00:00+00:00\n"
        "> goal_mtime: 1789000000000\n"
        "\n"
        "## Stage 1: work\n"
        "> goal: deliver\n"
        "> status: running\n"
        "> key-status: k1=running\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        "| k1 | worker | - |\n",
        encoding="utf-8",
    )


def _add_work(
    project: pathlib.Path,
    key: str,
    task_key: str = "w1",
    *,
    output: bool = False,
    run_status: str | None = None,
    origin: str | None = None,
) -> pathlib.Path:
    d = project / ".agenticdoc" / key / "workers" / task_key
    d.mkdir(parents=True, exist_ok=True)
    front = "type: coding\n" + (f"origin: {origin}\n" if origin else "")
    (d / "task.md").write_text(front, encoding="utf-8")
    if output:
        (d / "output.md").write_text("done\n", encoding="utf-8")
    if run_status is not None:
        (d / "run.json").write_text(json.dumps({"status": run_status}), encoding="utf-8")
    return d


def _add_plan_task(project: pathlib.Path, key: str) -> None:
    key_dir = project / ".agenticdoc" / key
    key_dir.mkdir(parents=True, exist_ok=True)
    for name in ("spec.md", "design.md", "plan.md"):
        (key_dir / name).write_text(f"# {name}\n", encoding="utf-8")
    (key_dir / "tasks").mkdir(exist_ok=True)
    (key_dir / "tasks" / "T-01.md").write_text("# T-01\n", encoding="utf-8")


def _state(project: pathlib.Path) -> conductor.ConductorState:
    return conductor.ConductorState(
        timeline.Timeline(timeline.timeline_path(project)), conductor.goal_mtime_ns(project)
    )


def _events(project: pathlib.Path, ev: str | None = None) -> list[dict]:
    events = timeline.query_events(timeline.timeline_path(project)).events
    return [e for e in events if ev is None or e["ev"] == ev]


def _rows(project: pathlib.Path) -> dict[str, dict]:
    return {r["key"]: r for r in state.read_index(project)}


def _claim(project: pathlib.Path, key: str) -> str:
    return str(_rows(project)[key]["claim_id"]).strip()


def _queue(project: pathlib.Path) -> list[dict]:
    return mw_common.parse_workers_file(mw_common.workers_path(project))


def _load_update_index():
    if not _UPDATE_INDEX.is_file():
        pytest.fail(f"framework update_index.py missing: {_UPDATE_INDEX} (fail-closed)")
    spec = importlib.util.spec_from_file_location("mwgal_t16_update_index", _UPDATE_INDEX)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── VC-1: no live claim + work => claim created AND dispatch happens ─────────

def test_no_live_claim_gets_a_synthetic_claim_and_still_dispatches(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(
        tmp_path,
        rows=[("k1", "idle", "20260808-174558-3176")],  # C-35 shape: idle + legacy id
        roadmap=True,
    )
    _add_work(project, "k1")          # undispatched human task card (no output.md)
    _add_plan_task(project, "k1")     # EXECUTE plan task → conductor dispatch path
    query = _queue(project)
    assert query == []  # nothing queued yet

    st = _state(project)
    assert conductor.tick(project, st) == "ok"

    row = _rows(project)["k1"]
    own = mw_common.synthetic_claim_id(*conductor.synthetic_claim_owner(project))
    assert row["claim_id"] == own
    assert row["status"] == "active"
    assert mw_common.parse_synthetic_claim(row["claim_id"]) == (HOST, os.getpid())
    # The dispatch itself happened in the SAME tick the claim was created: the
    # EXECUTE plan task was queued while the key already held our own claim.
    assert [r["task_key"] for r in _queue(project) if r["task_key"].startswith("ap-k1-")] == [
        "ap-k1-T-01"
    ]
    creates = [e for e in _events(project, "reconcile") if e.get("key") == "k1"]
    assert len(creates) == 1 and "accepted for 1 undispatched task" in creates[0]["detail"]

    # Requirement 6: a repeat tick (and a conductor restart) must not re-create
    # the claim nor re-skip the dispatch because "no watch".
    st2 = _state(project)
    assert conductor.tick(project, st2) == "ok"
    assert _claim(project, "k1") == own
    assert len([e for e in _events(project, "reconcile") if e.get("key") == "k1"]) == 1
    assert [e for e in _events(project, "skip") if e.get("key") == "k1"] == []
    _verify(
        "VC-1",
        claim=own,
        dispatched_rows=len(_queue(project)),
        skip_events=0,
        create_events=1,
    )


def test_own_synthetic_claim_does_not_block_the_conductor(tmp_path: pathlib.Path) -> None:
    """The self-identification axis: without `self_id` our own claim reads live
    (i.e. the historical skip condition), with it the conductor proceeds."""
    project = _project(tmp_path, rows=[("k1", "idle", "—")])
    _add_work(project, "k1")
    own = mw_common.synthetic_claim_id(*conductor.synthetic_claim_owner(project))
    conductor.tick(project, _state(project))

    assert _claim(project, "k1") == own
    assert state.claim_state(own) == state.CLAIM_LIVE          # foreign caller: blocked
    assert state.claim_state(own, self_id=own) == state.CLAIM_FREE  # own claim: free
    _verify("VC-1b", own_claim_live=state.CLAIM_LIVE, self_id_free=state.CLAIM_FREE)


# ── VC-2: renewal heartbeat + reclaim ────────────────────────────────────────

def test_heartbeat_renews_and_an_expired_owner_is_reclaimed(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path, rows=[("k1", "idle", "—")])
    _add_work(project, "k1")
    st = _state(project)
    conductor.tick(project, st)
    own = _claim(project, "k1")

    # Renewal: an aged `Updated` cell is refreshed by the heartbeat, once, with
    # no extra event (requirement 6: no duplicate renewal events).
    index_path = project / ".agenticdoc" / "_index.parallel"
    assert index_parallel.set_claim(
        project, "k1", claim_id=own, updated="2000-01-01T00:00:00+00:00"
    )
    st.synthetic_renewed["k1"] = 0.0
    before_renew_events = len(_events(project, "reconcile")) + len(_events(project, "skip"))
    conductor.tick(project, st)
    assert _rows(project)["k1"]["updated"] != "2000-01-01T00:00:00+00:00"
    # The heartbeat moved the freshness cell and announced nothing (requirement 6:
    # no duplicate renewal events).
    assert len(_events(project, "reconcile")) + len(_events(project, "skip")) == before_renew_events

    # Reclaim by OWNER DISAPPEARANCE (deterministic, no wall-clock TTL): the
    # serve pid the claim is bound to is gone.
    _write_serve_meta(project, 999_999_999, started_at_ms=1)
    conductor.tick(project, st)
    assert _claim(project, "k1") == mw_common.CLAIM_PLACEHOLDERS[1]
    recycled = [e for e in _events(project, "reconcile") if "recycled" in e.get("detail", "")]
    assert len(recycled) == 1 and "stale synthetic claim recycled" in recycled[0]["detail"]
    _verify("VC-2", renewed=True, recycled=recycled[0]["detail"])


def test_reclaim_is_not_a_wall_clock_guess(tmp_path: pathlib.Path) -> None:
    """A claim whose owner is alive stays (no TTL), even if its `Updated` cell
    looks ancient — the decision is pid/serve identity only."""
    child = _LivePid()
    try:
        project = _project(tmp_path, rows=[("k1", "idle", "—")], serve_pid=child.pid)
        _add_work(project, "k1")
        st = _state(project)
        conductor.tick(project, st)
        own = _claim(project, "k1")
        assert own == mw_common.synthetic_claim_id(HOST, child.pid)
        assert index_parallel.set_claim(
            project, "k1", claim_id=own, updated="2000-01-01T00:00:00+00:00"
        )
        st.synthetic_renewed["k1"] = 0.0
        conductor.tick(project, st)
        assert _claim(project, "k1") == own  # still ours, refreshed
        assert _rows(project)["k1"]["updated"] != "2000-01-01T00:00:00+00:00"
    finally:
        child.close()
    _verify("VC-2b", no_ttl=True, bound_pid=child.pid)


# ── VC-3: human takeover wins, is traced, and is never re-claimed ────────────

def test_human_takeover_yields_and_is_not_reclaimed(tmp_path: pathlib.Path) -> None:
    child = _LivePid()
    try:
        project = _project(tmp_path, rows=[("k1", "idle", "—")])
        _add_work(project, "k1")
        st = _state(project)
        conductor.tick(project, st)
        assert mw_common.is_synthetic_claim(_claim(project, "k1"))

        # A human window takes the key over (IndexStore.claim writes host:pid).
        human = _human_claim(child.pid)
        index_parallel.set_claim(project, "k1", claim_id=human, status="active")
        for _ in range(3):
            conductor.tick(project, st)
        assert _claim(project, "k1") == human  # never grabbed back
        yields = [e for e in _events(project, "skip") if "yielded to human claim" in e.get("detail", "")]
        withheld = [e for e in _events(project, "skip") if "withheld" in e.get("detail", "")]
        assert len(yields) == 1 and withheld == []  # exactly one trace, no duplicate
        assert _rows(project)["k1"]["status"] == "active"
    finally:
        child.close()
    _verify("VC-3", yield_traces=1, reclaimed=False)


def test_live_and_foreign_human_claims_are_never_stomped(tmp_path: pathlib.Path) -> None:
    child = _LivePid()
    try:
        live = _human_claim(child.pid)
        project = _project(tmp_path, rows=[("k1", "idle", live)])
        _add_work(project, "k1")
        st = _state(project)
        conductor.tick(project, st)
        conductor.tick(project, st)
        assert _claim(project, "k1") == live
        withheld = [e for e in _events(project, "skip") if "withheld" in e.get("detail", "")]
        assert len(withheld) == 1 and "held by human claim" in withheld[0]["detail"]

        foreign = "no-such-host-xyz:4242"
        project2 = _project(tmp_path / "b", rows=[("k1", "idle", foreign)])
        _add_work(project2, "k1")
        st2 = _state(project2)
        conductor.tick(project2, st2)
        conductor.tick(project2, st2)
        assert _claim(project2, "k1") == foreign  # unverifiable holder: untouched
        assert len([e for e in _events(project2, "skip")]) == 1
    finally:
        child.close()
    _verify("VC-3b", live_claim_kept=True, foreign_claim_kept=True)


# ── VC-4: serve pid change invalidates the old claim ─────────────────────────

def test_serve_pid_change_invalidates_the_previous_claim(tmp_path: pathlib.Path) -> None:
    first = _LivePid()
    second = _LivePid()
    try:
        project = _project(tmp_path, rows=[("k1", "idle", "—")], serve_pid=first.pid)
        _add_work(project, "k1")
        st = _state(project)
        conductor.tick(project, st)
        old = _claim(project, "k1")
        assert old == mw_common.synthetic_claim_id(HOST, first.pid)

        # serve restarted: same project, new pid (T-13 identity face).
        _write_serve_meta(project, second.pid, started_at_ms=1)
        conductor.tick(project, st)
        new = _claim(project, "k1")
        assert new != old
        assert mw_common.parse_synthetic_claim(new) == (HOST, second.pid)
        assert any(
            f":{first.pid}" in e.get("detail", "") for e in _events(project, "reconcile")
        )
        _verify("VC-4", old=old, new=new, old_invalid=True)
    finally:
        first.close()
        second.close()


def test_a_conductor_older_than_its_serve_never_claims(tmp_path: pathlib.Path) -> None:
    """`serve.meta.started_at_ms` newer than this process => this conductor is a
    leftover of a replaced serve: it recycles and creates nothing."""
    project = _project(
        tmp_path,
        rows=[("k1", "idle", "—")],
        serve_pid=os.getpid(),
    )
    (project / ".mw" / "serve.meta").write_text(
        json.dumps({"pid": os.getpid(), "started_at_ms": int(time.time() * 1000) + 3_600_000}),
        encoding="utf-8",
    )
    _add_work(project, "k1")
    st = _state(project)
    assert conductor.synthetic_claims_allowed(project) is False
    conductor.tick(project, st)
    assert _claim(project, "k1") == mw_common.CLAIM_PLACEHOLDERS[1]
    assert conductor.maintain_synthetic_claims(project, st, []) == ""
    assert _claim(project, "k1") == mw_common.CLAIM_PLACEHOLDERS[1]
    _verify("VC-4b", orphan_refused=True)


# ── VC-5: index presentation + existing parsers ──────────────────────────────

def test_index_presentation_is_distinct_and_parsers_still_work(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path, rows=[("k1", "idle", "—")])
    _add_work(project, "k1")
    conductor.tick(project, _state(project))
    own = _claim(project, "k1")

    index_path = project / ".agenticdoc" / "_index.parallel"
    text = index_path.read_text(encoding="utf-8")
    data_line = next(line for line in text.splitlines() if line.startswith("| k1 "))
    cols = [c.strip() for c in data_line.strip("|").split("|")]
    assert len(cols) == 7  # column count/order unchanged
    assert cols[0] == "k1" and cols[1] == "active"
    assert cols[3] == own  # the distinction lives in the claim CELL
    assert cols[3].startswith(mw_common.SYNTHETIC_CLAIM_PREFIX)  # not a pid read
    assert not mw_common.is_synthetic_claim(f"{HOST}:{os.getpid()}")
    assert mw_common.parse_synthetic_claim(own) == (HOST, os.getpid())
    assert mw_common.parse_synthetic_claim(own[:-1] + "x") is None  # malformed → not adopted

    # Python parsers: the conductor's `state.read_index` and the framework's
    # own `_parse_row` must read the synthetic row identically.
    row = _rows(project)["k1"]
    assert (row["key"], row["status"], row["claim_id"]) == ("k1", "active", own)
    update_index = _load_update_index()
    fw_rows = {r["key"]: r for r in update_index.read_index(index_path)}
    assert fw_rows["k1"]["claim_id"] == own
    assert fw_rows["k1"]["status"] == "active"
    assert fw_rows["k1"]["updated"] == row["updated"]

    # The framework CLI reads it back through its own parser.
    proc = subprocess.run(
        [sys.executable, "-X", "utf8", str(_UPDATE_INDEX), "get-claim", "k1"],
        cwd=str(project),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=60,
    )
    assert proc.returncode == 0 and proc.stdout.strip() == own
    _verify("VC-5", columns=len(cols), cell=own, framework_readback=True)


def test_legacy_five_column_row_is_rewritten_in_place(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, rows=[])
    index_path = project / ".agenticdoc" / "_index.parallel"
    index_path.write_text(
        "# Index Parallel\n\n"
        "| Key | Status | ClaimId | Note | Updated |\n"
        "|-----|--------|---------|------|---------|\n"
        "| k1 | idle | legacy-20260101-123 | note | 2026-09-07 12:05 |\n",
        encoding="utf-8",
    )
    _add_work(project, "k1")
    own = mw_common.synthetic_claim_id(*conductor.synthetic_claim_owner(project))
    assert index_parallel.set_claim(project, "k1", claim_id=own, status="active")
    line = next(
        l for l in index_path.read_text(encoding="utf-8").splitlines() if l.startswith("| k1 ")
    )
    cols = [c.strip() for c in line.strip("|").split("|")]
    assert len(cols) == 5 and cols[2] == own and cols[1] == "active"
    _verify("VC-5b", legacy_columns=len(cols), claim=cols[2])


# ── VC-6: idle keys without work stay skipped ────────────────────────────────

def test_idle_keys_without_work_are_never_taken_over(tmp_path: pathlib.Path) -> None:
    project = _project(
        tmp_path,
        rows=[
            ("produced", "idle", "—"),      # task card WITH output.md (history)
            ("nocard", "idle", "—"),        # no workers/ dir at all
            ("ranterminal", "idle", "—"),   # run.json already terminal (T-20)
            ("ranrunning", "idle", "—"),    # run.json active (T-20)
            ("conductorwork", "idle", "—"),  # origin: conductor (D-104)
            ("queued", "idle", "—"),        # already in _workers.parallel
            ("donekey", "done", "—"),       # terminal key status
        ],    )
    _add_work(project, "produced", output=True)
    _add_work(project, "ranterminal", run_status="failed")
    _add_work(project, "ranrunning", run_status="running")
    _add_work(project, "conductorwork", origin="conductor")
    d = _add_work(project, "queued")
    mw_common.upsert_worker_row(
        mw_common.workers_path(project),
        {
            "task_key": "w1",
            "status": "pending",
            "cli": "pi",
            "provider": "",
            "task_path": str(d / "task.md"),
            "dispatched_at": mw_common.iso_now(),
            "updated_at": mw_common.iso_now(),
            "model": "",
            "origin": mw_common.WORKER_ORIGIN_MANUAL,
        },
    )
    _add_work(project, "donekey")

    st = _state(project)
    conductor.tick(project, st)
    conductor.tick(project, st)
    rows = _rows(project)
    for key in (
        "produced",
        "nocard",
        "ranterminal",
        "ranrunning",
        "conductorwork",
        "queued",
        "donekey",
    ):
        assert not mw_common.is_synthetic_claim(rows[key]["claim_id"]), key
    assert _events(project, "reconcile") == []
    assert _events(project, "skip") == []
    _verify("VC-6", untouched=7, work_cards_ignored=7)


# ── VC-7: single-writer invariant ────────────────────────────────────────────

def test_only_the_index_is_written_and_the_shared_lock_is_released(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path, rows=[("k1", "idle", "—")])
    _add_work(project, "k1")
    queue_path = mw_common.workers_path(project)
    queue_before = queue_path.read_bytes() if queue_path.exists() else b""
    index_path = project / ".agenticdoc" / "_index.parallel"
    index_before = index_path.read_bytes()

    st = _state(project)
    conductor.maintain_synthetic_claims(project, st, [])  # the T-16 pass alone
    assert not (project / ".mw" / "index.lock").exists()  # lock released
    assert (queue_path.read_bytes() if queue_path.exists() else b"") == queue_before
    assert index_path.read_bytes() != index_before
    assert mw_common.is_synthetic_claim(_claim(project, "k1"))

    # Every other line of the index survives verbatim (no whole-table rewrite).
    original_extra = index_before.decode("utf-8").splitlines()
    after = index_path.read_text(encoding="utf-8").splitlines()
    assert [l for l in after if not l.startswith("| k1 ")] == [
        l for l in original_extra if not l.startswith("| k1 ")
    ]
    # A key with no row is never created by the claim writer (no fabricated rows).
    assert index_parallel.set_claim(project, "ghost", claim_id="autopilot@x:1") is False
    assert "ghost" not in index_path.read_text(encoding="utf-8")
    _verify("VC-7", queue_bytes_unchanged=True, lock_released=True, no_row_invention=True)


def test_claim_state_reads_synthetic_ids_like_human_ids() -> None:
    own = mw_common.synthetic_claim_id(HOST, os.getpid())
    foreign = mw_common.synthetic_claim_id("no-such-host-xyz", 4242)
    dead = mw_common.synthetic_claim_id(HOST, 999_999_999)
    assert state.claim_state(own) == state.CLAIM_LIVE
    assert state.claim_state(own, self_id=own) == state.CLAIM_FREE
    assert state.claim_state(foreign) == state.CLAIM_DEAD
    assert state.claim_state(dead) == state.CLAIM_DEAD
    assert state.claim_state("autopilot@") == state.CLAIM_STALE  # malformed
    assert state.claim_state(f"{HOST}:{os.getpid()}") == state.CLAIM_LIVE  # unchanged
    _verify("VC-8", synthetic_verdicts=4, human_verdict_unchanged=True)
