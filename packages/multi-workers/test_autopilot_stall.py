"""
test_autopilot_stall.py — bounded advance retry + stall escalation + human
resume + L3 no-verdict separation (spec AC-002/003/004/005/012/013).

Harness reuse: test_autopilot_conductor_exec.py owns the project fixtures and
the gate-validating advance fake; this module imports them so both files
assert the same contract.
"""
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import test_autopilot_conductor_exec as harness  # noqa: E402
from autopilot import conductor, gates, roadmap, state, timeline  # noqa: E402

_project = harness._project
_key_project = harness._key_project
_state = harness._state
_events = harness._events
_rows = harness._rows
_set_row = harness._set_row
_worker_output = harness._worker_output
_tasks = harness._tasks
_fake_advance_factory = harness._fake_advance_factory
_verify_key_project = harness._verify_key_project
_L3_MEETS = harness._L3_MEETS
_L3_BELOW = harness._L3_BELOW

_E2FEATURE_ERROR = (
    "ERROR: feature-params-service/pm-state.md has unknown phase "
    "'execute（T-014 结案完成，待 PM 侧 `advance_phase … done`）'. "
    "Valid: spec, design, plan, tasks, execute, verify, done"
)


def _failing_advance(message: str):
    def fake_advance(key, phase, root, summary=None):
        return 1, "", message

    return fake_advance


def _advance_events(project: pathlib.Path, key: str = "k1") -> list[dict]:
    return [e for e in _events(project) if e["ev"] == "advance" and e["key"] == key]


def _gate_paths(project: pathlib.Path) -> list[pathlib.Path]:
    return sorted(conductor.gates_dir(project).glob("gate-*.md"))


def _answer_gate(path: pathlib.Path, status: str) -> None:
    """Simulate the human answer (what the TS /autopilot gate command writes)."""
    text = path.read_text(encoding="utf-8")
    assert "status: pending" in text
    text = text.replace("status: pending", f"status: {status}", 1)
    text = text.replace(
        "answered_at:", "answered_at: 2026-09-22T00:00:00+00:00", 1
    )
    path.write_text(text, encoding="utf-8", newline="\n")


def _grant_stalled_credit(project: pathlib.Path, key: str = "k1") -> None:
    """A human-approved stalled gate = one extra round for the key."""
    path = gates.create(
        conductor.gates_dir(project), "stalled",
        f"key {key} 已 stalled——遗留关闭（closed-legacy），还是人工介入后重试？",
        context_refs=[f".agenticdoc/{key}"], key=key,
    )
    _answer_gate(path, "approved")


# ── AC-002: classification ───────────────────────────────────────────────────

def test_classify_advance_failure_four_classes() -> None:
    assert conductor._classify_advance_failure(_E2FEATURE_ERROR) == "interface-drift"
    assert conductor._classify_advance_failure(
        "GATE BLOCKED: achieved.md 必须存在且 >= 200 bytes"
    ) == "gate-blocked"
    assert conductor._classify_advance_failure(
        "TimeoutExpired: subprocess timed out"
    ) == "timeout-env"
    assert conductor._classify_advance_failure("stdout missing") == "other"
    assert conductor._classify_advance_failure("") == "other"


def test_advance_stall_ticks_default_and_override() -> None:
    assert conductor._advance_stall_ticks({}) == 5
    assert conductor._advance_stall_ticks({"advance_stall_ticks": 9}) == 9
    assert conductor._advance_stall_ticks({"advance_stall_ticks": "bad"}) == 5
    assert conductor._advance_stall_ticks({"advance_stall_ticks": 0}) == 1


# ── AC-002/AC-005: streak derivation from the timeline tail ──────────────────

def test_streak_counts_only_consecutive_same_edge_failures(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    tl = timeline.Timeline(timeline.timeline_path(project))
    tl.append("beat")
    for _ in range(3):
        tl.append("beat")
        tl.append("advance", key="k1", detail="execute->verify exit=1 class=interface-drift")
        tl.append("config", key="k1", detail=f"advance execute->verify failed: {_E2FEATURE_ERROR}")
    count, hist, snippet = conductor._advance_failure_streak(
        project, "k1", "execute->verify"
    )
    assert count == 3
    assert hist == {"interface-drift": 3}
    assert "unknown phase" in snippet
    other_edge = conductor._advance_failure_streak(project, "k1", "tasks->execute")
    assert other_edge == (0, {}, "")


def test_streak_broken_by_success_or_other_activity(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    tl = timeline.Timeline(timeline.timeline_path(project))
    # newest → oldest: 1 failure, then a success (breaks the walk)
    tl.append("advance", key="k1", detail="execute->verify exit=1 class=other")
    tl.append("advance", key="k1", detail="execute->verify exit=0")
    tl.append("advance", key="k1", detail="execute->verify exit=1 class=other")
    assert conductor._advance_failure_streak(project, "k1", "execute->verify")[0] == 1
    # a dispatch for the same key proves progress → streak resets
    tl.append("advance", key="k1", detail="execute->verify exit=1 class=other")
    tl.append("dispatch", key="k1", detail="ap-k1-T-01-first type=phase-writer")
    tl.append("advance", key="k1", detail="execute->verify exit=1 class=other")
    tl.append("advance", key="k1", detail="execute->verify exit=1 class=other")
    assert conductor._advance_failure_streak(project, "k1", "execute->verify")[0] == 2


def test_streak_other_key_does_not_interfere(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    tl = timeline.Timeline(timeline.timeline_path(project))
    tl.append("advance", key="k1", detail="execute->verify exit=1 class=other")
    tl.append("advance", key="k2", detail="execute->verify exit=1 class=interface-drift")
    tl.append("advance", key="k1", detail="execute->verify exit=1 class=other")
    assert conductor._advance_failure_streak(project, "k1", "execute->verify")[0] == 2


def test_beat_flood_does_not_break_streak(tmp_path: pathlib.Path) -> None:
    """The derived count has to survive long beat runs between failures.

    The streak is re-derived from a bounded timeline tail, so the window must
    hold the whole run. The worst realistic case is a per-tick failure loop
    (2 events per tick: the failing advance plus its config); this feeds 100
    interleaved beats per gap — far more than a real conductor emits between
    two 4 s ticks — and the run still counts to the threshold. Shrinking
    ``timeline.tail_events`` below the run's own span fails here first.
    """
    project = _project(tmp_path)
    tl = timeline.Timeline(timeline.timeline_path(project))
    edge = "execute->verify"
    for _ in range(3):
        for _ in range(100):
            tl.append("beat", key="-", detail="")
        tl.append("advance", key="k1", detail=f"{edge} exit=1 class=other")
    count, hist, _snippet = conductor._advance_failure_streak(project, "k1", edge)
    assert (count, hist) == (3, {"other": 3})


# ── AC-003: bounded retry escalates to the stalled four-artifact path ────────

def test_repeated_advance_failure_stalls_instead_of_spinning(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(tmp_path, phases={"k1": "EXECUTE"})
    _tasks(project, "k1", ["T-01-first"])
    cfg = harness.config.load_config(project)
    cfg["advance_stall_ticks"] = 3
    harness.config.save_config(project, cfg)
    st = _state(project)
    conductor.tick(project, st)  # dispatch the exec task
    _set_row(project, "ap-k1-T-01-first", "done")
    monkeypatch.setattr(
        conductor.advance, "advance", _failing_advance(_E2FEATURE_ERROR)
    )
    # two failures: still under the threshold → keeps retrying (old behaviour)
    conductor.tick(project, st)
    conductor.tick(project, st)
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "running"
    assert len(_advance_events(project)) == 2
    # third failure hits advance_stall_ticks → stalled, four artifacts present
    conductor.tick(project, st)
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "stalled"
    key_dir = project / ".agenticdoc" / "k1"
    assert "## 遗留问题" in (key_dir / "achieved.md").read_text(encoding="utf-8")
    assert (
        project / ".agenticdoc" / "patterns" / "k1" / "stall-lesson.md"
    ).is_file()
    gate = gates.enumerate(conductor.gates_dir(project))
    assert [g.kind for g in gate] == ["stalled"]
    assert "interface-drift" in gate[0].question
    assert "连续 3 次失败" in gate[0].question
    assert "\n" not in gate[0].question
    # frozen: later ticks never call advance for that key again
    before = len(_advance_events(project))
    for _ in range(4):
        assert conductor.tick(project, st) == "ok"
    assert len(_advance_events(project)) == before
    failed_events = [e for e in _advance_events(project) if "exit=1" in e["detail"]]
    assert all("class=interface-drift" in e["detail"] for e in failed_events)


# ── AC-004/AC-013: human approve resumes the key with one extra round ────────

def test_approved_stalled_gate_resumes_key(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(tmp_path, phases={"k1": "EXECUTE"})
    _tasks(project, "k1", ["T-01-first"])
    cfg = harness.config.load_config(project)
    cfg["advance_stall_ticks"] = 2
    harness.config.save_config(project, cfg)
    monkeypatch.setattr(
        conductor.advance, "advance", _failing_advance(_E2FEATURE_ERROR)
    )
    st = _state(project)
    conductor.tick(project, st)
    _set_row(project, "ap-k1-T-01-first", "done")
    conductor.tick(project, st)
    conductor.tick(project, st)  # second failure → stalled
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "stalled"
    gate_path = _gate_paths(project)[0]
    _answer_gate(gate_path, "approved")
    # approve → resume: key-status back to running, durable consumption events
    assert conductor.tick(project, st) == "ok"
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "running"
    answered = [e for e in _events(project) if e["ev"] == "gate-answered"]
    assert any("approved → k1 running" in e["detail"] for e in answered)
    assert any(e["ev"] == "resume" and e["key"] == "k1" for e in _events(project))
    assert conductor._resume_credits(project, "k1") == 1
    # the key is actually retried (a fresh advance attempt happened in-tick)
    assert len(_advance_events(project)) == 3
    # the granted credit buys a window, not a permanent exemption: once the
    # same edge fails again up to the threshold the key escalates again
    assert conductor.tick(project, st) == "ok"
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "stalled"
    assert len(_advance_events(project)) == 4
    resumes = [e for e in _events(project) if e["ev"] == "resume"]
    assert len(resumes) == 1  # the earlier approval never re-fires
    assert len(gates.enumerate(conductor.gates_dir(project))) == 2  # re-escalated


def test_resume_credit_lifts_execute_retry_limit(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(tmp_path, phases={"k1": "EXECUTE"})
    _tasks(project, "k1", ["T-01-first"])
    cfg = harness.config.load_config(project)
    cfg["round_budget"] = 1
    harness.config.save_config(project, cfg)
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    conductor.tick(project, st)  # attempt 1
    _set_row(project, "ap-k1-T-01-first", "failed")
    # budget 1 and no credit: the attempt is spent → stalled
    conductor.tick(project, st)
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "stalled"
    # resume with one credit → the retry is dispatched (a2)
    _answer_gate(_gate_paths(project)[0], "approved")
    assert conductor.tick(project, st) == "ok"
    assert "ap-k1-T-01-first-a2" in [r["task_key"] for r in _rows(project, "ap-k1-")]
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "running"


def test_resume_credit_lifts_l2_and_l3_limits(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # L2: a plan-referenced missing task is a synthetic blocking gap
    project = _key_project(tmp_path, phases={"k1": "TASKS"})
    cfg = harness.config.load_config(project)
    cfg["round_budget"] = 1
    harness.config.save_config(project, cfg)
    _tasks(project, "k1", ["T-01-there"], plan="# Plan\n\n1. T-01-there\n2. T-99-missing\n")
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    _grant_stalled_credit(project, "k1")
    st = _state(project)
    conductor.tick(project, st)
    l2 = [r["task_key"] for r in _rows(project, "ap-k1-l2-")]
    assert l2 == ["ap-k1-l2-tasks-to-execute-a1"], l2
    _set_row(project, "ap-k1-l2-tasks-to-execute-a1", "done")
    # round 1 verifier terminal → the same-round evidence fix goes out first
    conductor.tick(project, st)
    assert "ap-k1-l2-fix-tasks-to-execute-a1" in [
        r["task_key"] for r in _rows(project, "ap-k1-l2-")
    ]
    _set_row(project, "ap-k1-l2-fix-tasks-to-execute-a1", "done")
    # round 2 fits inside the granted credit (budget 1 + 1); without it this
    # tick would open a budget-exhausted gate instead
    conductor.tick(project, st)
    l2 = [r["task_key"] for r in _rows(project, "ap-k1-l2-")]
    assert "ap-k1-l2-tasks-to-execute-a2" in l2, l2
    assert not [g for g in gates.enumerate(conductor.gates_dir(project)) if g.kind == "budget-exhausted"]


def test_resume_credit_lifts_l3_and_repair_limits(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _verify_key_project(tmp_path)
    cfg = harness.config.load_config(project)
    cfg["round_budget"] = 1
    harness.config.save_config(project, cfg)
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    _grant_stalled_credit(project, "k1")
    st = _state(project)
    conductor.tick(project, st)  # l3-a1
    _worker_output(project, "k1", "ap-k1-l3-a1", _L3_BELOW)
    _set_row(project, "ap-k1-l3-a1", "done")
    # budget 1 + 1 credit → the below verdict still buys a repair round
    conductor.tick(project, st)
    assert [r["task_key"] for r in _rows(project, "ap-k1-repair-")] == ["ap-k1-repair-a1"]
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "running"
    # a failed repair retry also fits inside the credit (a2, not stalled)
    _set_row(project, "ap-k1-repair-a1", "failed")
    conductor.tick(project, st)
    assert "ap-k1-repair-a1-a2" in [r["task_key"] for r in _rows(project, "ap-k1-")]
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "running"


def test_one_credit_is_spent_by_one_round_per_loop(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An approved stalled gate buys exactly one more round: the credit is
    consumed by the round that uses it, not reusable forever (AC-013).

    budget 1 + 1 credit → l3_limit 2: rounds a1 (budget) and a2 (credit); the
    third round is refused and the key escalates again, the credit count
    unchanged (a further round needs another human approval).
    """
    project = _verify_key_project(tmp_path)
    cfg = harness.config.load_config(project)
    cfg["round_budget"] = 1
    harness.config.save_config(project, cfg)
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    _grant_stalled_credit(project, "k1")
    st = _state(project)
    conductor.tick(project, st)  # l3-a1: the budget round
    _worker_output(project, "k1", "ap-k1-l3-a1", _L3_BELOW)
    _set_row(project, "ap-k1-l3-a1", "done")
    conductor.tick(project, st)  # repair-a1
    _set_row(project, "ap-k1-repair-a1", "done")
    conductor.tick(project, st)  # l3-a2: the credit round
    assert "ap-k1-l3-a2" in [r["task_key"] for r in _rows(project, "ap-k1-")]
    _worker_output(project, "k1", "ap-k1-l3-a2", _L3_BELOW)
    _set_row(project, "ap-k1-l3-a2", "done")
    conductor.tick(project, st)  # used 2 >= limit 2 → spent, escalate again
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "stalled"
    assert "ap-k1-l3-a3" not in [r["task_key"] for r in _rows(project, "ap-k1-")]
    assert conductor._resume_credits(project, "k1") == 1  # not re-granted


def test_rejected_stalled_gate_still_closes_legacy(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _key_project(tmp_path, phases={"k1": "EXECUTE"})
    _tasks(project, "k1", ["T-01-first"])
    cfg = harness.config.load_config(project)
    cfg["advance_stall_ticks"] = 2
    harness.config.save_config(project, cfg)
    monkeypatch.setattr(
        conductor.advance, "advance", _failing_advance(_E2FEATURE_ERROR)
    )
    st = _state(project)
    conductor.tick(project, st)
    _set_row(project, "ap-k1-T-01-first", "done")
    conductor.tick(project, st)
    conductor.tick(project, st)  # second failure → stalled
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "stalled"
    _answer_gate(_gate_paths(project)[0], "rejected")
    assert conductor.tick(project, st) == "ok"
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "closed-legacy"
    assert conductor._resume_credits(project, "k1") == 0


# ── AC-012: a crashed L3 worker is not a `below` verdict ─────────────────────

def test_l3_worker_failure_is_no_verdict(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _verify_key_project(tmp_path)
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    conductor.tick(project, st)  # l3-a1
    _set_row(project, "ap-k1-l3-a1", "failed")  # crashed: no output.md
    conductor.tick(project, st)
    # no repair against a missing report — the next review round is dispatched
    assert _rows(project, "ap-k1-repair-a1") == []
    assert [r["task_key"] for r in _rows(project, "ap-k1-l3-")] == [
        "ap-k1-l3-a1", "ap-k1-l3-a2",
    ]
    no_verdict = [e for e in _events(project) if e["ev"] == "l3-no-verdict"]
    assert no_verdict and "status=failed" in no_verdict[0]["detail"]
    # a meets report in round 2 still closes the key normally
    _worker_output(project, "k1", "ap-k1-l3-a2", _L3_MEETS)
    _set_row(project, "ap-k1-l3-a2", "done")
    conductor.tick(project, st)
    assert state.read_key_states(project)["k1"].phase == "DONE"


def test_l3_failed_worker_with_placeholder_output_is_still_no_verdict(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The worker harness writes a placeholder output.md even when the process
    died (live case: reviewer killed by a provider 403 left a 181-byte
    template) — the queue status wins over the file, otherwise the conductor
    repairs against a template and reports `below`."""
    project = _verify_key_project(tmp_path)
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    conductor.tick(project, st)  # l3-a1
    _worker_output(
        project, "k1", "ap-k1-l3-a1",
        "# Task completed\n\nTools used: 0\n",  # harness placeholder on crash
    )
    _set_row(project, "ap-k1-l3-a1", "failed")
    conductor.tick(project, st)
    assert _rows(project, "ap-k1-repair-a1") == []
    assert "ap-k1-l3-a2" in [r["task_key"] for r in _rows(project, "ap-k1-l3-")]
    no_verdict = [e for e in _events(project) if e["ev"] == "l3-no-verdict"]
    assert no_verdict and "status=failed" in no_verdict[0]["detail"]


def test_l3_no_verdict_stall_reason_names_worker(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _verify_key_project(tmp_path)
    cfg = harness.config.load_config(project)
    cfg["round_budget"] = 1
    harness.config.save_config(project, cfg)
    fake_advance, _calls = _fake_advance_factory(project)
    monkeypatch.setattr(conductor.advance, "advance", fake_advance)
    st = _state(project)
    conductor.tick(project, st)  # l3-a1
    _set_row(project, "ap-k1-l3-a1", "failed")
    conductor.tick(project, st)  # budget spent without a verdict
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    assert rm.stages[0].key_status["k1"] == "stalled"
    gate = gates.enumerate(conductor.gates_dir(project))[0]
    assert "L3 无裁决" in gate.question
    assert "worker failed" in gate.question
    assert "ap-k1-l3-a1" in gate.question
    assert _rows(project, "ap-k1-repair-") == []


# ── timeline tail reads (AC-006/AC-007 data source) ──────────────────────────

def test_tail_events_bounded_and_tolerant(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "timeline.jsonl"
    tl = timeline.Timeline(path)
    for i in range(50):
        tl.append("beat", detail=f"b{i}")
    with path.open("a", encoding="utf-8", newline="\n") as fh:
        fh.write("{not json\n")
    tl.append("advance", key="k1", detail="execute->verify exit=1 class=other")
    events = timeline.tail_events(path, limit=10)
    assert len(events) == 10
    assert events[-1]["ev"] == "advance"
    assert [e["seq"] for e in events] == sorted(e["seq"] for e in events)
    # bounded read on a small file still returns everything parseable
    everything = timeline.tail_events(path, max_bytes=100_000, limit=0)
    assert len(everything) == 51
    assert timeline.tail_events(tmp_path / "missing.jsonl") == []
