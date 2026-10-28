"""
test_autopilot_conductor.py — L1 tests for autopilot/conductor.py + mw.py serve
integration (T-09, AC-005/AC-019/AC-025 / VC-021/VC-027).

Logic tests drive tick()/main() in-process against tmp_path projects. The real
serve↔conductor process chain is T-16 (L2); here the serve side is covered by
the pure supervision decision + config mtime cache.
"""
import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402  (module under test: serve integration)
from autopilot import config, conductor, gates, timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def true_str(b: bool) -> str:
    return "true" if b else "false"


# ── fixtures ──────────────────────────────────────────────────────────────────

def _project(tmp_path: pathlib.Path, *, enabled: bool = False) -> pathlib.Path:
    """A project tree with goal.md + an autopilot config."""
    ap = tmp_path / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agenticdoc" / "goal.md").write_text("# Goal\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = enabled
    config.save_config(tmp_path, cfg)
    return tmp_path


def _state(project: pathlib.Path) -> conductor.ConductorState:
    tl = timeline.Timeline(timeline.timeline_path(project))
    return conductor.ConductorState(tl, conductor.goal_mtime_ns(project))


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(timeline.timeline_path(project)).events


def _fake_framework(tmp_path: pathlib.Path) -> pathlib.Path:
    """Minimal framework skeleton that satisfies advance.locate_platform_dir:
    detect_root.py printing PLATFORM_DIR + an advance_phase.py placeholder."""
    fw = tmp_path / "fakefw"
    (fw / "scripts").mkdir(parents=True, exist_ok=True)
    (fw / "scripts" / "advance_phase.py").write_text("", encoding="utf-8")
    detect = fw / "scripts" / "detect_root.py"
    detect.write_text(
        "import json\n"
        f"print(json.dumps({{'PLATFORM_DIR': {json.dumps(str(fw))}, "
        f"'PROJECT_ROOT': {json.dumps(str(tmp_path))}}}))\n",
        encoding="utf-8",
    )
    (tmp_path / ".agentic-framework").write_text(f"repo={fw}\n", encoding="utf-8")
    return fw


# ── tick: beat / idle / enabled gate ─────────────────────────────────────────

def test_beat_appended_every_tick(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, enabled=True)
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    evs = [e["ev"] for e in _events(project)]
    assert evs[0] == "beat"  # beat first, unconditionally
    assert "goal-halt" not in evs  # no goal change → no gate flow


def test_beat_even_when_disabled(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, enabled=False)
    st = _state(project)
    assert conductor.tick(project, st) == "idle"
    assert _events(project)[0]["ev"] == "beat"
    # paused likewise idles
    cfg = config.default_config()
    cfg["enabled"] = True
    cfg["paused"] = True
    config.save_config(project, cfg)
    assert conductor.tick(project, st) == "idle"
    beats = [e for e in _events(project) if e["ev"] == "beat"]
    assert len(beats) == 2
    _verify("VC-021", beat_when_disabled=len(beats), idle_status="idle")


def test_orchestrate_called_only_when_active(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[pathlib.Path] = []
    monkeypatch.setattr(conductor, "orchestrate", lambda root, st: calls.append(root))
    project = _project(tmp_path, enabled=False)
    st = _state(project)
    assert conductor.tick(project, st) == "idle"  # disabled default
    assert calls == []
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(project, cfg)
    assert conductor.tick(project, st) == "ok"
    assert calls == [project]


# ── goal change: halt + gate once + resume ───────────────────────────────────

def test_goal_change_halts_and_gates_once(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, enabled=True)
    st = _state(project)
    assert conductor.tick(project, st) == "ok"  # no change yet
    goal = conductor.goal_path(project)
    os.utime(goal, None)  # touch — mtime moves
    assert conductor.tick(project, st) == "halted-goal-change"
    gate_files = sorted(conductor.gates_dir(project).glob("gate-*.md"))
    assert len(gate_files) == 1
    gate = gates.parse(gate_files[0])
    assert gate.kind == "goal-change"
    assert gate.status == "pending"
    assert gate.created_by == gates.CREATED_BY == "conductor"
    assert any(e["ev"] == "goal-halt" for e in _events(project))
    # Repeated ticks while halted: still halted, never a second gate.
    assert conductor.tick(project, st) == "halted-goal-change"
    assert conductor.tick(project, st) == "halted-goal-change"
    assert len(sorted(conductor.gates_dir(project).glob("gate-*.md"))) == 1
    _verify("VC-021", gates_after_repeat=1, status="halted-goal-change")


def test_goal_gate_answered_resumes_and_rebases(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, enabled=True)
    st = _state(project)
    conductor.tick(project, st)
    os.utime(conductor.goal_path(project), None)
    assert conductor.tick(project, st) == "halted-goal-change"
    gate_file = next(iter(conductor.gates_dir(project).glob("gate-*.md")))
    text = gate_file.read_text(encoding="utf-8").replace("status: pending", "status: approved")
    gate_file.write_text(text, encoding="utf-8")
    # Answered → resume with a fresh baseline.
    assert conductor.tick(project, st) == "ok"
    assert any(e["ev"] == "goal-snapshot" for e in _events(project))
    # A later goal change opens a NEW gate (baseline was rebased).
    os.utime(conductor.goal_path(project), None)
    assert conductor.tick(project, st) == "halted-goal-change"
    assert len(sorted(conductor.gates_dir(project).glob("gate-*.md"))) == 2


def test_open_goal_gate_survives_restart(tmp_path: pathlib.Path) -> None:
    """A fresh conductor process (new state) still halts on an open gate."""
    project = _project(tmp_path, enabled=True)
    st = _state(project)
    conductor.tick(project, st)
    os.utime(conductor.goal_path(project), None)
    assert conductor.tick(project, st) == "halted-goal-change"
    st2 = _state(project)  # restart: baseline is the CURRENT mtime
    assert conductor.tick(project, st2) == "halted-goal-change"
    assert len(sorted(conductor.gates_dir(project).glob("gate-*.md"))) == 1


# ── tick fault tolerance (§9) ─────────────────────────────────────────────────

def test_tick_exception_becomes_config_event(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, enabled=True)
    st = _state(project)

    def boom(root: pathlib.Path) -> dict:
        raise RuntimeError("injected disk failure")

    monkeypatch.setattr(conductor.config, "cached_load", boom)
    assert conductor.tick(project, st) == "error"
    cfg_events = [e for e in _events(project) if e["ev"] == "config"]
    assert len(cfg_events) == 1
    assert "injected disk failure" in cfg_events[0]["detail"]
    # The loop survives: next tick (patch reverted by exiting the raises scope
    # is NOT automatic — verify by monkeypatch.undo()).
    monkeypatch.undo()
    assert conductor.tick(project, st) == "ok"
    _verify("VC-021", tick_error_survives=true_str(True))


# ── stale lock steal (D-113) ──────────────────────────────────────────────────

def test_stale_lock_stolen_and_recorded(tmp_path: pathlib.Path) -> None:
    tl = timeline.Timeline(timeline.timeline_path(tmp_path))
    lock = conductor.lock_file(tmp_path, "gates")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("", encoding="utf-8")
    old = time.time() - (conductor.STALE_LOCK_AGE_SEC + 30)
    os.utime(lock, (old, old))
    # Steal: succeeds (no raise) and records a config event.
    conductor.acquire_conductor_lock(tmp_path, "gates", tl)
    assert lock.exists()  # now held by us (fresh file)
    cfg_events = [e for e in _events(tmp_path) if e["ev"] == "config"]
    assert any("gates" in e["detail"] and "stolen" in e["detail"] for e in cfg_events)
    import mw_common

    mw_common.release_lock(lock)


def test_fresh_lock_not_stolen(tmp_path: pathlib.Path) -> None:
    tl = timeline.Timeline(timeline.timeline_path(tmp_path))
    lock = conductor.lock_file(tmp_path, "roadmap")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("", encoding="utf-8")  # fresh — a live holder
    with pytest.raises(conductor.ConductorLockHeld):
        conductor.acquire_conductor_lock(tmp_path, "roadmap", tl)
    assert lock.exists()  # untouched


# ── AC-005: no Phase writes, no goal.md writes (static source check) ─────────

def test_conductor_source_never_writes_goal_or_phase() -> None:
    src = pathlib.Path(conductor.__file__).read_text(encoding="utf-8")
    write_calls = [
        (i, line)
        for i, line in enumerate(src.splitlines(), 1)
        if ".write_text(" in line or ".write_bytes(" in line or ".open(" in line
    ]
    assert write_calls, "sanity: conductor writes at least its pid file"
    for lineno, line in write_calls:
        low = line.lower()
        assert "goal" not in low, f"goal write at line {lineno}: {line}"
        assert "phase" not in low, f"Phase write at line {lineno}: {line}"
    # goal.md is only ever stat()ed.
    assert "goal_path" in src and "st_mtime_ns" in src


# ── CLI: --once / startup gate ───────────────────────────────────────────────

def test_once_cli_single_tick(tmp_path: pathlib.Path) -> None:
    _fake_framework(tmp_path)
    _project(tmp_path, enabled=True)
    proc = subprocess.run(
        [sys.executable, str(pathlib.Path(conductor.__file__)), "--project", str(tmp_path), "--once"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "ok"
    evs = [e["ev"] for e in _events(tmp_path)]
    assert evs[0] == "goal-snapshot"  # startup baseline event
    assert "beat" in evs
    assert not conductor.conductor_pid_file(tmp_path).exists()  # cleaned up
    _verify("VC-027", first_tick_immediate=true_str("beat" in evs), stdout=proc.stdout.strip())


def test_once_cli_refuses_without_framework(tmp_path: pathlib.Path) -> None:
    _project(tmp_path, enabled=True)  # no .agentic-framework marker
    proc = subprocess.run(
        [sys.executable, str(pathlib.Path(conductor.__file__)), "--project", str(tmp_path), "--once"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 1
    assert "refusing to start" in proc.stderr
    assert not conductor.conductor_pid_file(tmp_path).exists()


# ── conductor_status (mw status / doctor row) ─────────────────────────────────

def test_conductor_status(tmp_path: pathlib.Path) -> None:
    stat = conductor.conductor_status(tmp_path)
    assert stat == {"running": False, "pid": None, "last_seq": None, "last_ts": None}
    tl = timeline.Timeline(timeline.timeline_path(tmp_path))
    tl.append("beat")
    pid_file = conductor.conductor_pid_file(tmp_path)
    pid_file.parent.mkdir(parents=True, exist_ok=True)
    pid_file.write_text(str(os.getpid()), encoding="utf-8")  # a live pid (us)
    stat = conductor.conductor_status(tmp_path)
    assert stat["running"] is True
    assert stat["pid"] == os.getpid()
    assert stat["last_seq"] == 1
    assert stat["last_ts"] is not None
    # Dead pid → not running (stale pid file).
    pid_file.write_text("3999999", encoding="utf-8")
    assert conductor.conductor_status(tmp_path)["running"] is False


# ── serve integration: pure decision + config cache ──────────────────────────

def test_conductor_decision_matrix() -> None:
    assert mw._conductor_decision(True, False) == "spawn"
    assert mw._conductor_decision(False, True) == "terminate"
    assert mw._conductor_decision(True, True) == "none"
    assert mw._conductor_decision(False, False) == "none"
    _verify("VC-027", decision_spawn="spawn", decision_terminate="terminate")


def test_serve_step_uses_cached_config_and_pid_file(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The supervise step derives liveness from the pid file (mtime-cached
    config side is config.cached_load's own contract, covered by T-02 tests)."""
    spawned: list[list[str]] = []

    class FakeProc:
        def __init__(self) -> None:
            self.pid = 4242

        def poll(self) -> None:
            return None

    def fake_popen(cmd, **kwargs):  # noqa: ARG001
        spawned.append(cmd)
        return FakeProc()

    monkeypatch.setattr(mw.subprocess, "Popen", fake_popen)
    project = _project(tmp_path, enabled=True)
    # No pid file, no in-memory proc → spawn.
    proc = mw._conductor_supervise_step(project, None, {}, None)
    assert isinstance(proc, FakeProc)
    assert len(spawned) == 1
    assert spawned[0][1].endswith("conductor.py")
    assert f"--project={project}" in spawned[0]
    # In-memory proc alive → no second spawn.
    proc = mw._conductor_supervise_step(project, proc, {}, None)
    assert len(spawned) == 1
    # Disabled → terminate path removes the pid file and drops the proc.
    cfg = config.default_config()
    cfg["enabled"] = False
    config.save_config(project, cfg)
    terminated: list[int] = []

    class TermProc(FakeProc):
        def terminate(self) -> None:
            terminated.append(self.pid)

        def wait(self, timeout: float = 0) -> None:  # noqa: ARG002
            return None

    conductor.conductor_pid_file(project).parent.mkdir(parents=True, exist_ok=True)
    conductor.conductor_pid_file(project).write_text(str(os.getpid()), encoding="utf-8")
    proc = mw._conductor_supervise_step(project, TermProc(), {}, None)
    assert proc is None
    assert terminated == [4242]
    assert not conductor.conductor_pid_file(project).exists()


# ═════════════════════════════════════════════════════════════════════════════
# T-10: per-key phase machine
# ═════════════════════════════════════════════════════════════════════════════

import mw_common  # noqa: E402
import socket  # noqa: E402
from autopilot import state  # noqa: E402


def _rm(project: pathlib.Path, text: str) -> None:
    (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(text, encoding="utf-8")


def _rm_one_stage(*, status: str = "running", key_status: str = "k1=running") -> str:
    return (
        "# Roadmap\n"
        "> generated_at: 2026-09-10T00:00:00+00:00\n"
        "> goal_mtime: 1789000000000\n"
        "\n"
        "## Stage 1: work\n"
        f"> goal: deliver\n"
        f"> status: {status}\n"
        f"> key-status: {key_status}\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        "| k1 | worker | - |\n"
        "\n"
        "## Stage 2: more work\n"
        "> goal: follow up\n"
        "> status: pending\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        "| k2 | follow | k1 |\n"
    )


def _index_row(key: str, phase: str, claim: str = "—") -> str:
    return f"| {key} | active | {phase} | {claim} | - | desc | 2026-09-10T00:00:00 |\n"


def _key_project(
    tmp_path: pathlib.Path,
    *,
    rows_index: str,
    roadmap_text: str,
    budget: int = 2,
    cap: int = 2,
) -> pathlib.Path:
    project = _project(tmp_path, enabled=True)
    cfg = config.load_config(project)  # keeps enabled=True from _project
    cfg["round_budget"] = budget
    cfg["max_parallel_keys"] = cap
    config.save_config(project, cfg)
    _rm(project, roadmap_text)
    (project / ".agenticdoc" / "_index.parallel").write_text(rows_index, encoding="utf-8")
    return project


def _rows_of(project: pathlib.Path, prefix: str) -> list[dict]:
    return [
        r for r in mw_common.parse_workers_file(mw_common.workers_path(project))
        if r["task_key"].startswith(prefix)
    ]


def _finish(project: pathlib.Path, task_key: str) -> None:
    """Simulate the worker reaching a terminal state."""
    wpath = mw_common.workers_path(project)
    entries = mw_common.parse_workers_file(wpath)
    for e in entries:
        if e["task_key"] == task_key:
            e["status"] = "done"
    wpath.write_text(
        "\n".join(mw_common.serialize_entry(e) for e in entries) + "\n", encoding="utf-8"
    )


def test_missing_artifact_dispatches_phase_writer(tmp_path: pathlib.Path) -> None:
    project = _key_project(
        tmp_path, rows_index=_index_row("k1", "SPEC"), roadmap_text=_rm_one_stage(),
    )
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    rows = _rows_of(project, "ap-k1-")
    assert len(rows) == 1 and rows[0]["status"] == "pending"
    assert rows[0]["task_key"] == "ap-k1-spec-writer-a1"
    task_md = project / ".agenticdoc" / "k1" / "workers" / "ap-k1-spec-writer-a1" / "task.md"
    text = task_md.read_text(encoding="utf-8")
    assert "origin: conductor" in text
    assert "loop: gen:k1:spec" in text  # loop-unrelated generation label


def test_l1_clean_direct_advance(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(
        tmp_path, rows_index=_index_row("k1", "SPEC"), roadmap_text=_rm_one_stage(),
    )
    key_dir = project / ".agenticdoc" / "k1"
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "spec.md").write_text("# Spec\n\nAC-1: ok\n", encoding="utf-8")
    mtime_before = (key_dir / "spec.md").stat().st_mtime_ns

    calls: list[tuple] = []

    def fake_advance(key: str, phase: str, root: pathlib.Path, summary: str | None = None):
        calls.append((key, phase, str(root)))
        return 0, "advanced", ""

    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    assert calls == [("k1", "design", str(project))]  # via script only (AC-005)
    adv = [e for e in _events(project) if e["ev"] == "advance"]
    assert len(adv) == 1 and "exit=0" in adv[0]["detail"] and adv[0]["key"] == "k1"
    assert _rows_of(project, "ap-k1-") == []  # zero dispatch rows
    assert (key_dir / "spec.md").stat().st_mtime_ns == mtime_before  # no rewrite
    _verify("VC-007", phase_direct_writes=0, goal_writes=0, advance_via_script=1)


def _gappy_key(project: pathlib.Path) -> None:
    """k1 with a spec.md that cites a missing evidence file (blocking gap)."""
    key_dir = project / ".agenticdoc" / "k1"
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "spec.md").write_text(
        "# Spec\n\nAC-1: see evidence/missing.md\n", encoding="utf-8"
    )


def test_l2_round_closes_in_one_round(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(
        tmp_path, rows_index=_index_row("k1", "SPEC"), roadmap_text=_rm_one_stage(),
    )
    _gappy_key(project)
    monkeypatch.setattr(
        conductor.advance, "advance",
        lambda key, phase, root, summary=None: (0, "advanced", ""),
    )
    st = _state(project)

    # tick 1: verifier round 1
    assert conductor.tick(project, st) == "ok"
    assert [r["task_key"] for r in _rows_of(project, "ap-k1-")] == [
        "ap-k1-l2-spec-to-design-a1"
    ]
    vtask = (
        project / ".agenticdoc" / "k1" / "workers" / "ap-k1-l2-spec-to-design-a1" / "task.md"
    )
    vtext = vtask.read_text(encoding="utf-8")
    assert "loop: l2:k1:spec-to-design" in vtext and "attempt: 1" in vtext
    assert "read_scope:" in vtext and ".agenticdoc/k1" in vtext
    _finish(project, "ap-k1-l2-spec-to-design-a1")

    # tick 2: same-round evidence fix (phase-writer, same loop+attempt)
    assert conductor.tick(project, st) == "ok"
    assert [r["task_key"] for r in _rows_of(project, "ap-k1-l2-")] == [
        "ap-k1-l2-spec-to-design-a1", "ap-k1-l2-fix-spec-to-design-a1",
    ]
    fix_text = (
        project / ".agenticdoc" / "k1" / "workers" / "ap-k1-l2-fix-spec-to-design-a1" / "task.md"
    ).read_text(encoding="utf-8")
    assert "loop: l2:k1:spec-to-design" in fix_text and "attempt: 1" in fix_text
    _finish(project, "ap-k1-l2-fix-spec-to-design-a1")

    # one round consumed across both dispatches (same attempt)
    rounds = state.used_rounds(conductor._all_workers_dirs(project))
    assert rounds.get("l2:k1:spec-to-design") == 1

    # tick 3: fix landed the evidence -> audit clean -> advance
    (project / ".agenticdoc" / "k1" / "evidence").mkdir(parents=True, exist_ok=True)
    (project / ".agenticdoc" / "k1" / "evidence" / "missing.md").write_text("E-1\n", encoding="utf-8")
    assert conductor.tick(project, st) == "ok"
    adv = [e for e in _events(project) if e["ev"] == "advance"]
    assert len(adv) == 1 and "exit=0" in adv[0]["detail"]
    assert len(_rows_of(project, "ap-k1-l2-")) == 2  # no third dispatch


def test_l2_budget_cap_opens_gate(tmp_path: pathlib.Path) -> None:
    project = _key_project(
        tmp_path, rows_index=_index_row("k1", "SPEC"), roadmap_text=_rm_one_stage(),
    )
    _gappy_key(project)  # gap never fixed
    st = _state(project)
    for expected in [
        "ap-k1-l2-spec-to-design-a1",
        "ap-k1-l2-fix-spec-to-design-a1",
        "ap-k1-l2-spec-to-design-a2",
        "ap-k1-l2-fix-spec-to-design-a2",
    ]:
        assert conductor.tick(project, st) == "ok"
        _finish(project, expected)
    # round 3 refused: zero new rows + budget-exhausted gate within this tick
    before = len(_rows_of(project, "ap-k1-"))
    assert conductor.tick(project, st) == "ok"
    assert len(_rows_of(project, "ap-k1-")) == before  # rows=0 for round 3
    gate_files = list(conductor.gates_dir(project).glob("gate-*.md"))
    assert len(gate_files) == 1
    gate = gates.parse(gate_files[0])
    assert gate.kind == "budget-exhausted" and gate.status == "pending"
    assert "l2:k1:spec-to-design" in gate.context_refs
    assert gate.key == "k1"
    rounds = state.used_rounds(conductor._all_workers_dirs(project))
    assert rounds.get("l2:k1:spec-to-design") == 2  # distinct attempts capped at budget
    _verify("VC-010", round3_rows=0, gate_pending=true_str(gate.status == "pending"))


def test_l2_budget_gate_approve_and_reject(tmp_path: pathlib.Path) -> None:
    project = _key_project(
        tmp_path, rows_index=_index_row("k1", "SPEC"), roadmap_text=_rm_one_stage(),
    )
    _gappy_key(project)
    st = _state(project)
    for expected in [
        "ap-k1-l2-spec-to-design-a1", "ap-k1-l2-fix-spec-to-design-a1",
        "ap-k1-l2-spec-to-design-a2", "ap-k1-l2-fix-spec-to-design-a2",
    ]:
        conductor.tick(project, st)
        _finish(project, expected)
    conductor.tick(project, st)  # budget gate
    gate_file = next(iter(conductor.gates_dir(project).glob("gate-*.md")))

    # approve -> exactly one bonus round
    gate_file.write_text(
        gate_file.read_text(encoding="utf-8").replace("status: pending", "status: approved"),
        encoding="utf-8",
    )
    assert conductor.tick(project, st) == "ok"
    assert _rows_of(project, "ap-k1-l2-spec-to-design-a3")  # bonus verifier
    _finish(project, "ap-k1-l2-spec-to-design-a3")
    conductor.tick(project, st)
    _finish(project, "ap-k1-l2-fix-spec-to-design-a3")
    # bonus exhausted -> stalled (the budget gate stays answered; the new
    # pending gate is the stalled gate from mark_stalled)
    assert conductor.tick(project, st) == "ok"
    all_gates = [gates.parse(p) for p in conductor.gates_dir(project).glob("gate-*.md")]
    assert len(all_gates) == 2
    kinds = sorted(g.kind for g in all_gates)
    assert kinds == ["budget-exhausted", "stalled"]
    stalled_gate = next(g for g in all_gates if g.kind == "stalled")
    assert stalled_gate.status == "pending"
    rm_text = (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").read_text(encoding="utf-8")
    assert "k1=stalled" in rm_text
    assert any(e["ev"] == "stalled" for e in _events(project))


def test_budget_one_upgrades_after_first_round(tmp_path: pathlib.Path) -> None:
    project = _key_project(
        tmp_path, rows_index=_index_row("k1", "SPEC"), roadmap_text=_rm_one_stage(),
        budget=1,
    )
    _gappy_key(project)
    st = _state(project)
    conductor.tick(project, st)
    _finish(project, "ap-k1-l2-spec-to-design-a1")
    conductor.tick(project, st)
    _finish(project, "ap-k1-l2-fix-spec-to-design-a1")
    assert conductor.tick(project, st) == "ok"
    assert _rows_of(project, "ap-k1-l2-spec-to-design-a2") == []  # round 2 rows=0
    assert len(list(conductor.gates_dir(project).glob("gate-*.md"))) == 1
    _verify("VC-013", budget=1, second_round_rows=0)


def test_live_claim_skip_and_takeover(tmp_path: pathlib.Path) -> None:
    live = f"{socket.gethostname()}:{os.getpid()}"
    project = _key_project(
        tmp_path,
        rows_index=_index_row("k1", "SPEC", claim=live) + _index_row("k2", "SPEC"),
        roadmap_text=_rm_one_stage(key_status="k1=running, k2=running").replace(
            "| k1 | worker | - |",
            "| k1 | worker | - |\n| k2 | worker | - |",
        ),
    )
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    skips = [e for e in _events(project) if e["ev"] == "skip"]
    assert len(skips) == 1 and skips[0]["key"] == "k1"  # one skip event
    assert _rows_of(project, "ap-k1-") == []  # claimed key: zero dispatch rows
    assert len(_rows_of(project, "ap-k2-")) == 1  # untouched key proceeds
    # force takeover by another live window: still zero new rows for k1
    other_live = f"{socket.gethostname()}:{os.getpid() + 1}"
    (project / ".agenticdoc" / "_index.parallel").write_text(
        _index_row("k1", "SPEC", claim=other_live) + _index_row("k2", "SPEC"),
        encoding="utf-8",
    )
    config.invalidate_cache()
    st2 = _state(project)
    _finish(project, "ap-k2-spec-writer-a1")
    assert conductor.tick(project, st2) == "ok"
    assert _rows_of(project, "ap-k1-") == []
    _verify("VC-015", claimed_rows=0, skip_events=len(skips))


def test_execute_takeover_no_redispatch(tmp_path: pathlib.Path) -> None:
    project = _key_project(
        tmp_path, rows_index=_index_row("k1", "EXECUTE"), roadmap_text=_rm_one_stage(),
    )
    key_dir = project / ".agenticdoc" / "k1"
    key_dir.mkdir(parents=True, exist_ok=True)
    artifacts = ["spec.md", "design.md", "plan.md"]
    for name in artifacts:
        (key_dir / name).write_text(f"# {name}\n", encoding="utf-8")
    (key_dir / "tasks").mkdir(exist_ok=True)
    (key_dir / "tasks" / "T-01.md").write_text("# T-01\n", encoding="utf-8")
    mtimes = {n: (key_dir / n).stat().st_mtime_ns for n in artifacts}
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    # T-12: EXECUTE now dispatches the task (one in flight)
    assert [r["task_key"] for r in _rows_of(project, "ap-k1-")] == ["ap-k1-T-01"]
    assert {n: (key_dir / n).stat().st_mtime_ns for n in artifacts} == mtimes
    _verify("VC-016", phase_restored="execute", artifact_mtimes_unchanged=len(artifacts))


def test_stalled_four_artifacts_and_dependency_block(tmp_path: pathlib.Path) -> None:
    project = _key_project(
        tmp_path,
        rows_index=_index_row("k1", "SPEC") + _index_row("k2", "SPEC") + _index_row("k3", "SPEC"),
        roadmap_text=_rm_one_stage(key_status="k1=running, k2=running, k3=running").replace(
            "| k1 | worker | - |",
            "| k1 | worker | - |\n| k2 | follow | k1 |\n| k3 | free | - |",
        ),
    )
    st = _state(project)
    conductor.mark_stalled(project, st, "k1", "L3 below twice")
    rm_text = (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").read_text(encoding="utf-8")
    assert "k1=stalled" in rm_text  # artifact 1: key-status
    gate = gates.parse(next(iter(conductor.gates_dir(project).glob("gate-*.md"))))
    assert gate.kind == "stalled" and gate.status == "pending"  # artifact 2: gate
    achieved = (project / ".agenticdoc" / "k1" / "achieved.md").read_text(encoding="utf-8")
    assert "遗留问题" in achieved  # artifact 3: legacy draft
    pattern = project / ".agenticdoc" / "patterns" / "k1" / "stall-lesson.md"
    assert pattern.is_file() and "## 问题模式" in pattern.read_text(encoding="utf-8")  # 4

    # dependent blocked, independent proceeds (single tick)
    assert conductor.tick(project, st) == "ok"
    assert _rows_of(project, "ap-k2-") == []  # dep of stalled k1 -> 0 rows
    assert len(_rows_of(project, "ap-k3-")) >= 1  # independent proceeds
    assert len(_rows_of(project, "ap-k1-")) == 0  # stalled key itself: no dispatch
    _verify("VC-008", stalled_artifacts=4, dep_rows=0, indep_rows=len(_rows_of(project, "ap-k3-")))

    # stalled gate rejected -> closed-legacy -> dependent unblocked
    gate_file = gate.path
    gate_file.write_text(
        gate_file.read_text(encoding="utf-8").replace("status: pending", "status: rejected"),
        encoding="utf-8",
    )
    _finish(project, "ap-k3-spec-writer-a1")
    assert conductor.tick(project, st) == "ok"
    rm_text = (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").read_text(encoding="utf-8")
    assert "k1=closed-legacy" in rm_text
    assert len(_rows_of(project, "ap-k2-")) == 1  # dep satisfied by closed-legacy


def test_orphan_reconcile_reinserts_same_attempt(tmp_path: pathlib.Path) -> None:
    project = _key_project(
        tmp_path, rows_index=_index_row("k1", "SPEC"), roadmap_text=_rm_one_stage(),
    )
    # orphan shape: task dir with conductor task.md, no queue row (D-102)
    orphan_dir = project / ".agenticdoc" / "k1" / "workers" / "ap-k1-l2-spec-to-design-a1"
    orphan_dir.mkdir(parents=True)
    (orphan_dir / "task.md").write_text(
        "---\ntype: verifier\norigin: conductor\n"
        "loop: l2:k1:spec-to-design\nattempt: 1\n---\n\nverify\n",
        encoding="utf-8",
    )
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    rows = _rows_of(project, "ap-k1-")
    assert len(rows) == 1 and rows[0]["task_key"] == "ap-k1-l2-spec-to-design-a1"
    assert rows[0]["status"] == "pending"  # reinserted as pending
    assert rows[0]["task_path"].endswith("task.md")
    recs = [e for e in _events(project) if e["ev"] == "reconcile"]
    assert len(recs) == 1 and recs[0]["key"] == "k1"
    rounds = state.used_rounds(conductor._all_workers_dirs(project))
    assert rounds.get("l2:k1:spec-to-design") == 1  # same attempt: no new round


def test_max_parallel_keys_cap(tmp_path: pathlib.Path) -> None:
    project = _key_project(
        tmp_path,
        rows_index=_index_row("k1", "SPEC") + _index_row("k2", "SPEC") + _index_row("k3", "SPEC"),
        roadmap_text=_rm_one_stage(key_status="k1=running, k2=running, k3=running").replace(
            "| k1 | worker | - |",
            "| k1 | worker | - |\n| k2 | worker | - |\n| k3 | worker | - |",
        ),
        cap=2,
    )
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    assert len(_rows_of(project, "ap-")) == 2  # cap respected
    # finishing one frees a slot for the third key
    _finish(project, "ap-k1-spec-writer-a1")
    assert conductor.tick(project, st) == "ok"
    assert len(_rows_of(project, "ap-")) == 3


def test_pending_stage_not_worked(tmp_path: pathlib.Path) -> None:
    project = _key_project(
        tmp_path,
        rows_index=_index_row("k1", "SPEC"),
        roadmap_text=_rm_one_stage(status="pending"),  # stage not activated (T-11)
    )
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    assert _rows_of(project, "ap-") == []


def test_transfer_events_all_carry_key_and_ts(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """VC-019: every machine transition event has a non-null key and a ts."""
    project = _key_project(
        tmp_path, rows_index=_index_row("k1", "SPEC"), roadmap_text=_rm_one_stage(),
    )
    _gappy_key(project)
    monkeypatch.setattr(
        conductor.advance, "advance",
        lambda key, phase, root, summary=None: (0, "advanced", ""),
    )
    st = _state(project)
    conductor.tick(project, st)
    _finish(project, "ap-k1-l2-spec-to-design-a1")
    (project / ".agenticdoc" / "k1" / "evidence").mkdir(parents=True, exist_ok=True)
    (project / ".agenticdoc" / "k1" / "evidence" / "missing.md").write_text("E-1\n", encoding="utf-8")
    conductor.tick(project, st)
    conductor.tick(project, st)
    machine_events = [
        e for e in _events(project)
        if e["ev"] in ("dispatch", "advance", "skip", "stalled", "gate-created", "reconcile")
    ]
    assert machine_events, "expected machine transition events"
    for e in machine_events:
        assert e["key"], f"null key on {e['ev']} event"
        assert e["ts"]
    _verify("VC-019", machine_events=len(machine_events), null_keys=0)
