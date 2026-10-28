"""
test_autopilot_conductor_stage.py — L1 tests for the stage machine + gate
lifecycle in autopilot/conductor.py (T-11, AC-001/002/003/006/024 /
VC-003/005/026).

All logic tests drive tick()/orchestrate() in-process against tmp_path
projects; stage transitions are asserted through file truth (roadmap status
lines, gate files, _workers.parallel rows) and timeline events.
"""
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common  # noqa: E402
from autopilot import config, conductor, gates, roadmap, state, timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def true_str(b: bool) -> str:
    return "true" if b else "false"


# ── fixtures ──────────────────────────────────────────────────────────────────

def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    ap = tmp_path / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agenticdoc" / "goal.md").write_text("# Goal\n\nShip it.\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(tmp_path, cfg)
    return tmp_path


def _state(project: pathlib.Path) -> conductor.ConductorState:
    tl = timeline.Timeline(timeline.timeline_path(project))
    return conductor.ConductorState(tl, conductor.goal_mtime_ns(project))


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(timeline.timeline_path(project)).events


def _roadmap(
    project: pathlib.Path,
    text: str,
) -> None:
    path = project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    path.write_text(text, encoding="utf-8")


def _two_stage_roadmap(
    *, stage1_status: str = "pending", k1_status: str = "running"
) -> str:
    return (
        "# Roadmap\n"
        "> generated_at: 2026-09-10T00:00:00+00:00\n"
        "> goal_mtime: 1789000000000\n"
        "\n"
        "## Stage 1: first\n"
        "> goal: deliver k1\n"
        f"> status: {stage1_status}\n"
        f"> key-status: k1={k1_status}\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        "| k1 | worker | - |\n"
        "\n"
        "## Stage 2: second\n"
        "> goal: follow up\n"
        "> status: pending\n"
        "> key-status: k2=running\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        "| k2 | follow | k1 |\n"
    )


def _index_row(key: str, phase: str) -> str:
    return f"| {key} | active | {phase} | — | - | desc | 2026-09-10T00:00:00 |\n"


def _rows(project: pathlib.Path, prefix: str = "ap-") -> list[dict]:
    return [
        r for r in mw_common.parse_workers_file(mw_common.workers_path(project))
        if r["task_key"].startswith(prefix)
    ]


def _finish(project: pathlib.Path, task_key: str) -> None:
    wpath = mw_common.workers_path(project)
    entries = mw_common.parse_workers_file(wpath)
    for e in entries:
        if e["task_key"] == task_key:
            e["status"] = "done"
    wpath.write_text(
        "\n".join(mw_common.serialize_entry(e) for e in entries) + "\n", encoding="utf-8"
    )


def _pending_gate(project: pathlib.Path, kind: str) -> gates.Gate:
    found = [
        g for g in gates.enumerate(conductor.gates_dir(project))
        if g.kind == kind and g.status == "pending"
    ]
    assert found, f"no pending {kind} gate"
    return found[0]


def _answer(gate: gates.Gate, decision: str, note: str = "looks good") -> None:
    text = gate.path.read_text(encoding="utf-8")
    text = text.replace("status: pending", f"status: {decision}")
    # gates.py renders an empty note as a bare `note:` line
    text = text.replace("\nnote:\n", f"\nnote: '{note}'\n")
    gate.path.write_text(text, encoding="utf-8")


def _stage_status(project: pathlib.Path, number: int) -> str:
    rm = roadmap.load_roadmap(
        project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    )
    stage = roadmap.stage_by_number(rm, number)
    assert stage is not None
    return stage.status


# ── roadmap-writer dispatch (no roadmap yet) ─────────────────────────────────

def test_no_roadmap_dispatches_writer_with_input_list(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    (project / ".agenticdoc" / "_index.parallel").write_text(
        _index_row("kx", "PLAN"), encoding="utf-8"
    )
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    rows = _rows(project, "ap-_scratch-")
    assert len(rows) == 1 and rows[0]["task_key"] == "ap-_scratch-roadmap-s1-a1"
    task_md = (
        project / ".agenticdoc" / "_scratch" / "workers"
        / "ap-_scratch-roadmap-s1-a1" / "task.md"
    ).read_text(encoding="utf-8")
    assert "origin: conductor" in task_md
    assert "loop: roadmap:stage-1" in task_md and "attempt: 1" in task_md
    assert "read_scope:" in task_md and "- .agenticdoc" in task_md
    # D-105 input list: goal content + key list + schema template
    assert "Ship it." in task_md
    assert "kx (phase PLAN)" in task_md
    assert "### Keys" in task_md and "key-status:" in task_md
    assert "_roadmap.md" in task_md
    # no stage-confirm gate before the roadmap exists
    assert gates.enumerate(conductor.gates_dir(project)) == []


def test_writer_in_flight_not_redispatched(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    st = _state(project)
    conductor.tick(project, st)
    before = len(_rows(project))
    conductor.tick(project, st)  # writer still pending in the queue
    assert len(_rows(project)) == before
    _verify("VC-003", writer_rows=before, second_tick_rows=0)


# ── stage-confirm gate: zero rows until approved (AC-002/VC-003) ─────────────

def test_confirm_gate_created_once_and_zero_rows_until_answered(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    _roadmap(project, _two_stage_roadmap())
    (project / ".agenticdoc" / "_index.parallel").write_text(
        _index_row("k1", "SPEC"), encoding="utf-8"
    )
    st = _state(project)
    for _ in range(3):  # ≥3 ticks with the gate unanswered
        assert conductor.tick(project, st) == "ok"
    assert _rows(project) == []  # zero dispatch rows (AC-002)
    confirms = [
        g for g in gates.enumerate(conductor.gates_dir(project))
        if g.kind == "stage-confirm"
    ]
    assert len(confirms) == 1 and confirms[0].status == "pending"
    assert confirms[0].stage == 1
    assert _stage_status(project, 1) == "pending"  # not activated yet
    _verify("VC-003", ticks=3, rows=0, pending_confirm_gates=1)


def test_confirm_approve_activates_and_dispatches(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _roadmap(project, _two_stage_roadmap())
    (project / ".agenticdoc" / "_index.parallel").write_text(
        _index_row("k1", "SPEC"), encoding="utf-8"
    )
    st = _state(project)
    conductor.tick(project, st)  # creates the confirm gate
    gate = _pending_gate(project, "stage-confirm")
    _answer(gate, "approved")
    assert conductor.tick(project, st) == "ok"
    assert _stage_status(project, 1) == "running"  # activated
    answered = [e for e in _events(project) if e["ev"] == "gate-answered"]
    assert len(answered) == 1 and "running" in answered[0]["detail"]
    assert len(_rows(project, "ap-k1-")) == 1  # first dispatch row released
    # idempotent: a later tick does not re-apply the answered gate
    _finish(project, _rows(project, "ap-k1-")[0]["task_key"])
    conductor.tick(project, st)
    answered = [e for e in _events(project) if e["ev"] == "gate-answered"]
    assert len(answered) == 1


def test_writer_done_then_confirm_gate(tmp_path: pathlib.Path) -> None:
    """Writer terminal + roadmap materialized → the confirm gate appears."""
    project = _project(tmp_path)
    st = _state(project)
    conductor.tick(project, st)  # dispatch writer a1
    _finish(project, "ap-_scratch-roadmap-s1-a1")
    # the "worker" wrote the roadmap
    _roadmap(project, _two_stage_roadmap())
    (project / ".agenticdoc" / "_index.parallel").write_text(
        _index_row("k1", "SPEC"), encoding="utf-8"
    )
    assert conductor.tick(project, st) == "ok"
    gate = _pending_gate(project, "stage-confirm")
    assert gate.stage == 1
    assert _rows(project, "ap-k1-") == []  # still zero rows until approved


# ── stage closure: dossier + stage-close gate (AC-003/VC-005) ────────────────

def _running_stage_with_keys(
    tmp_path: pathlib.Path, *, k1_status: str = "done", k2_status: str = "running"
) -> pathlib.Path:
    project = _project(tmp_path)
    _roadmap(
        project,
        _two_stage_roadmap(stage1_status="running", k1_status=k1_status),
    )
    # stage 2's key-status is on its own line; fix k2 separately
    text = (
        project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    ).read_text(encoding="utf-8")
    text = text.replace("key-status: k2=running", f"key-status: k2={k2_status}")
    (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        text, encoding="utf-8"
    )
    (project / ".agenticdoc" / "_index.parallel").write_text(
        _index_row("k1", "DONE") + _index_row("k2", "SPEC"), encoding="utf-8"
    )
    # k1 done needs an achieved.md for the dossier evidence reference
    k1_dir = project / ".agenticdoc" / "k1"
    k1_dir.mkdir(parents=True, exist_ok=True)
    (k1_dir / "achieved.md").write_text("# Achieved\n", encoding="utf-8")
    return project


def test_all_terminal_dossier_and_close_gate_one_tick(tmp_path: pathlib.Path) -> None:
    project = _running_stage_with_keys(tmp_path)
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    dossier = (
        project / ".agenticdoc" / "_autopilot" / "stages" / "stage-1-close.md"
    )
    assert dossier.is_file()
    text = dossier.read_text(encoding="utf-8")
    assert "stage: 1" in text and "goal: deliver k1" in text
    assert "generated_at:" in text
    assert "| k1 | DONE | none |" in text  # final phase + L3 verdict none (T-12)
    assert ".agenticdoc/k1/achieved.md" in text
    gate = _pending_gate(project, "stage-close")
    assert gate.stage == 1
    # next stage: zero rows before its confirm gate is answered
    assert _rows(project, "ap-k2-") == []
    assert _stage_status(project, 2) == "pending"
    _verify(
        "VC-005", dossier=1, close_gate_pending=true_str(gate.status == "pending"),
        next_stage_rows=0,
    )
    # second tick: no duplicate dossier/gate
    conductor.tick(project, st)
    assert len([
        g for g in gates.enumerate(conductor.gates_dir(project))
        if g.kind == "stage-close"
    ]) == 1


def test_stalled_pending_blocks_closure_until_rejected(tmp_path: pathlib.Path) -> None:
    project = _running_stage_with_keys(tmp_path, k1_status="running")
    st = _state(project)
    conductor.mark_stalled(project, st, "k1", "L3 below twice")
    assert conductor.tick(project, st) == "ok"
    assert not (
        project / ".agenticdoc" / "_autopilot" / "stages" / "stage-1-close.md"
    ).is_file()  # stalled pending blocks closure
    stalled_gate = _pending_gate(project, "stalled")
    _answer(stalled_gate, "rejected", note="legacy close")
    assert conductor.tick(project, st) == "ok"
    # closed-legacy unblocks closure in the same tick (AC-024)
    assert (
        project / ".agenticdoc" / "_autopilot" / "stages" / "stage-1-close.md"
    ).is_file()
    rm = roadmap.load_roadmap(
        project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    )
    assert rm.stages[0].key_status["k1"] == "closed-legacy"
    answered = [e for e in _events(project) if e["ev"] == "gate-answered"]
    assert any("closed-legacy" in e["detail"] for e in answered)
    assert _pending_gate(project, "stage-close")
    _verify("VC-026", stalled_reject_unblocks_closure=true_str(True))


# ── stage-close approve / reject ──────────────────────────────────────────────

def test_close_approve_then_next_confirm_and_running(tmp_path: pathlib.Path) -> None:
    project = _running_stage_with_keys(tmp_path)
    st = _state(project)
    conductor.tick(project, st)  # dossier + close gate
    close_gate = _pending_gate(project, "stage-close")
    _answer(close_gate, "approved")
    assert conductor.tick(project, st) == "ok"
    assert _stage_status(project, 1) == "closed"
    closes = [e for e in _events(project) if e["ev"] == "stage-close"]
    assert any("closed" in e["detail"] for e in closes)
    # next stage confirm gate auto-created; stage 2 still pending
    confirm = _pending_gate(project, "stage-confirm")
    assert confirm.stage == 2
    assert _rows(project, "ap-k2-") == []
    _answer(confirm, "approved")
    assert conductor.tick(project, st) == "ok"
    assert _stage_status(project, 2) == "running"
    assert len(_rows(project, "ap-k2-")) == 1  # released


def test_close_reject_halts_until_human_edit(tmp_path: pathlib.Path) -> None:
    project = _running_stage_with_keys(tmp_path)
    st = _state(project)
    conductor.tick(project, st)
    _answer(_pending_gate(project, "stage-close"), "rejected", note="not done")
    assert conductor.tick(project, st) == "ok"
    assert _stage_status(project, 1) == "halted"
    assert _rows(project, "ap-k2-") == []  # dispatch paused everywhere
    answered = [e for e in _events(project) if e["ev"] == "gate-answered"]
    assert any("halted" in e["detail"] for e in answered)
    # human edits the roadmap back to running → dispatch resumes (next tick)
    text = (
        project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    ).read_text(encoding="utf-8")
    (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        text.replace("status: halted", "status: running"), encoding="utf-8"
    )
    assert conductor.tick(project, st) == "ok"
    assert _stage_status(project, 1) == "running"


# ── stage-confirm reject: re-propose exactly once (AC-024/VC-026) ────────────

def test_confirm_reject_repropose_once_then_stop(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    (project / ".agenticdoc" / "_index.parallel").write_text(
        _index_row("k1", "SPEC"), encoding="utf-8"
    )
    st = _state(project)
    # real flow: writer a1 proposes, human rejects, a2 revises, second
    # rejection stops auto-proposal (AC-024)
    assert conductor.tick(project, st) == "ok"
    assert [r["task_key"] for r in _rows(project, "ap-_scratch-")] == [
        "ap-_scratch-roadmap-s1-a1"
    ]
    _finish(project, "ap-_scratch-roadmap-s1-a1")
    _roadmap(project, _two_stage_roadmap())
    assert conductor.tick(project, st) == "ok"  # confirm gate for the proposal
    gate = _pending_gate(project, "stage-confirm")
    _answer(gate, "rejected", note="too broad")
    assert conductor.tick(project, st) == "ok"
    # re-proposal dispatched (attempt 2, same loop — 2 rounds total budget)
    assert [r["task_key"] for r in _rows(project, "ap-_scratch-")] == [
        "ap-_scratch-roadmap-s1-a1", "ap-_scratch-roadmap-s1-a2",
    ]
    a2_md = (
        project / ".agenticdoc" / "_scratch" / "workers"
        / "ap-_scratch-roadmap-s1-a2" / "task.md"
    ).read_text(encoding="utf-8")
    assert "too broad" in a2_md  # rejection note carried into the revision
    _finish(project, "ap-_scratch-roadmap-s1-a2")
    # worker rewrote the roadmap → fresh proposal → new confirm gate
    _roadmap(
        project, _two_stage_roadmap().replace("deliver k1", "deliver k1 (revised)")
    )
    assert conductor.tick(project, st) == "ok"
    gate2 = _pending_gate(project, "stage-confirm")
    assert gate2.id != gate.id  # a fresh gate for the revised proposal
    _answer(gate2, "rejected", note="still no")
    assert conductor.tick(project, st) == "ok"
    # second rejection: auto-proposal stopped — no a3, no new gate
    assert _rows(project, "ap-_scratch-roadmap-s1-a3") == []
    confirms = [
        g for g in gates.enumerate(conductor.gates_dir(project))
        if g.kind == "stage-confirm"
    ]
    assert all(g.status != "pending" for g in confirms)
    assert _rows(project, "ap-k1-") == []  # and no key dispatch either
    rounds = state.used_rounds(conductor._all_workers_dirs(project))
    assert rounds.get("roadmap:stage-1") == 2
    _verify("VC-026", proposals=2, third_proposal_rows=0)


# ── corrupt gate file → skip tick ─────────────────────────────────────────────

def test_corrupt_gate_file_skips_tick(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _roadmap(project, _two_stage_roadmap())
    (project / ".agenticdoc" / "_index.parallel").write_text(
        _index_row("k1", "SPEC"), encoding="utf-8"
    )
    st = _state(project)
    conductor.tick(project, st)  # confirm gate created
    # corrupt the gate answer by hand (invalid frontmatter shape)
    gate_file = _pending_gate(project, "stage-confirm").path
    gate_file.write_text("---\nkind: stage-confirm\nstatus: ???\n", encoding="utf-8")
    assert conductor.tick(project, st) == "ok"  # skipped, loop survives
    cfg_events = [e for e in _events(project) if e["ev"] == "config"]
    assert any("corrupt" in e["detail"] for e in cfg_events)
    assert _rows(project) == []
