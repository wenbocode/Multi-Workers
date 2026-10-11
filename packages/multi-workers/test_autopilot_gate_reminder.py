"""
test_autopilot_gate_reminder.py — T-07 (mw-gate-verdict-hardening, G2).

L1 tests for the pending-gate reminder judgment in autopilot/conductor.py:
the pure three-condition decision, the `phase:"remind"` ledger count, the
`gate-reminder` timeline event, answered-is-stop, the goal-change
early-return coverage, and the non-vacuous counterfactuals recorded in the
report (see the module docstring of each test).

VC-007 pending past threshold + no in-flight -> 1 ledger row + 1 event
VC-008 the same gate is never reminded a third time — the count lives in the
       ledger, not the 200-event timeline tail (shorter than the 60-min gap)
VC-009 answered gate -> zero residual
VC-010 ANY non-terminal queue row (not just `running`) suppresses: EXECUTE's
       sparse timeline is not "blocked on human"
"""
import datetime
import dataclasses
import os
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import config, conductor, gates, timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _true(value: bool) -> str:
    return "true" if value else "false"


# ── fixtures ──────────────────────────────────────────────────────────────────

def _project(tmp_path: pathlib.Path, *, enabled: bool = True) -> pathlib.Path:
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


def _events(project: pathlib.Path, ev: str | None = None) -> list[dict]:
    events = timeline.query_events(timeline.timeline_path(project)).events
    return [e for e in events if ev is None or e.get("ev") == ev]


def _remind_rows(project: pathlib.Path) -> list[dict]:
    return [
        row for row in conductor.auto_decision_rows(project)
        if row.get("phase") == "remind"
    ]


def _create_gate(
    project: pathlib.Path, *, kind: str = "stalled", key: str | None = "k1"
) -> pathlib.Path:
    return gates.create(
        conductor.gates_dir(project), kind, "test gate", key=key
    )


def _age_gate(gate_file: pathlib.Path, minutes: float) -> None:
    """Rewrite `created_at` so the gate looks `minutes` old — the only knob
    (gates.create always stamps `now`, and the reminder anchor is the gate's
    own `created_at`)."""
    stamp = (
        datetime.datetime.now(datetime.timezone.utc)
        - datetime.timedelta(minutes=minutes)
    ).isoformat(timespec="seconds")
    text = gate_file.read_text(encoding="utf-8")
    rewritten = re.sub(
        r"^created_at:.*$", f"created_at: {stamp}", text, count=1, flags=re.MULTILINE
    )
    assert rewritten != text, "gate file has no created_at line"
    gate_file.write_text(rewritten, encoding="utf-8", newline="\n")


def _write_workers(project: pathlib.Path, *statuses: str) -> None:
    rows = [
        f"ap-k1-w{i} | {status} | pi | timi | /tmp/task.md "
        f"| 2026-01-01T00:00:00Z | 2026-01-01T00:00:00Z | m"
        for i, status in enumerate(statuses)
    ]
    (project / ".agenticdoc" / "_workers.parallel").write_text(
        "\n".join(rows) + "\n", encoding="utf-8", newline="\n"
    )


def _gate_at(
    epoch: float,
    *,
    gate_id: str = "gate-0001",
    kind: str = "stalled",
    key: str | None = "k1",
    status: str = "pending",
) -> gates.Gate:
    created = datetime.datetime.fromtimestamp(
        epoch, datetime.timezone.utc
    ).isoformat(timespec="seconds")
    return gates.Gate(
        id=gate_id,
        kind=kind,
        stage=None,
        key=key,
        created_at=created,
        created_by="conductor",
        question="q",
        context_refs=[],
        status=status,
        answered_at=None,
        answered_by=None,
        note=None,
        path=pathlib.Path("/tmp/gate.md"),
    )


# ── pure decision (injected `now`, no IO) ────────────────────────────────────

def test_pure_decision_three_conditions() -> None:
    now = 1_800_000_000.0
    gate = _gate_at(now - 31 * 60)
    under = _gate_at(now - 29 * 60, gate_id="gate-0002")
    # condition 1: age >= n * after_min
    assert conductor.pending_gate_reminders([under], [], {}, now, 30, 2) == []
    assert [g.id for g, _ in conductor.pending_gate_reminders([gate], [], {}, now, 30, 2)] == [
        "gate-0001"
    ]
    assert conductor.pending_gate_reminders([gate], [], {}, now, 30, 2)[0][1] == 1
    # condition 1, second interval: with one prior reminder, n=2 and the
    # threshold is 2 x after_min (59 min is still not due; 61 min fires n=2)
    at59 = _gate_at(now - 59 * 60)
    at61 = _gate_at(now - 61 * 60)
    assert conductor.pending_gate_reminders(
        [at59], [], {"gate-0001": 1}, now, 30, 2
    ) == []
    assert conductor.pending_gate_reminders(
        [at61], [], {"gate-0001": 1}, now, 30, 2
    )[0][1] == 2
    # condition 3: cap — already 2, never a 3rd
    assert conductor.pending_gate_reminders([gate], [], {"gate-0001": 2}, now, 30, 2) == []
    # condition 2: any non-terminal row suppresses, terminal rows do not
    assert conductor.pending_gate_reminders(
        [gate], [{"status": "pending"}], {}, now, 30, 2
    ) == []
    assert conductor.pending_gate_reminders(
        [gate], [{"status": "running"}], {}, now, 30, 2
    ) == []
    assert [
        g.id
        for g, _ in conductor.pending_gate_reminders(
            [gate], [{"status": "done"}], {}, now, 30, 2
        )
    ] == ["gate-0001"]
    # unparseable anchor never fires (fail-closed)
    broken = _gate_at(now - 31 * 60, gate_id="gate-0003")
    broken = dataclasses.replace(broken, created_at="not-a-date")
    assert conductor.pending_gate_reminders([broken], [], {}, now, 30, 2) == []
    _verify("VC-007", pure_decision="ok", cap_enforced="true", non_terminal_only="true")


# ── tick end-to-end: VC-007 / VC-008 / VC-009 / VC-010 ───────────────────────

def test_pending_past_threshold_reminds_once(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    _age_gate(gate_file, 31)
    st = _state(project)
    assert conductor.tick(project, st) in ("ok", "halted-goal-change")
    rows = _remind_rows(project)
    events = _events(project, "gate-reminder")
    assert len(rows) == 1 and rows[0]["reminder_n"] == 1
    assert rows[0]["gate_id"] == "gate-0001" and rows[0]["gate_kind"] == "stalled"
    assert rows[0]["gate_key"] == "k1"
    assert len(events) == 1
    data = events[0]["data"]
    assert data["gate_id"] == "gate-0001"
    assert data["gate_kind"] == "stalled"
    assert data["gate_key"] == "k1"
    assert data["reminder_n"] == 1
    assert data["waited_s"] >= 31 * 60
    assert data["after_min"] == 30
    # the gate file is untouched (count lives in the ledger, D-006)
    assert gates.parse(gate_file).expires_at is None
    _verify("VC-007", ledger=len(rows), event=len(events), reminder_n=rows[0]["reminder_n"])


def test_under_threshold_is_silent(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    _age_gate(gate_file, 29)
    assert conductor.tick(project, _state(project)) in ("ok", "halted-goal-change")
    assert _remind_rows(project) == []
    assert _events(project, "gate-reminder") == []


def test_second_reminder_at_two_times_threshold(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    conductor._append_auto_decision_row(project, {
        "phase": "remind", "gate_id": "gate-0001", "gate_kind": "stalled",
        "gate_key": "k1", "reminder_n": 1, "reminded_at": "2026-01-01T00:00:00Z",
        "detail": "seed",
    })
    _age_gate(gate_file, 61)
    assert conductor.tick(project, _state(project)) in ("ok", "halted-goal-change")
    rows = _remind_rows(project)
    assert [r["reminder_n"] for r in rows] == [1, 2]
    assert [e["data"]["reminder_n"] for e in _events(project, "gate-reminder")] == [2]


def test_third_reminder_blocked(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    for n in (1, 2):
        conductor._append_auto_decision_row(project, {
            "phase": "remind", "gate_id": "gate-0001", "gate_kind": "stalled",
            "gate_key": "k1", "reminder_n": n, "reminded_at": "2026-01-01T00:00:00Z",
            "detail": "seed",
        })
    _age_gate(gate_file, 120)
    assert conductor.tick(project, _state(project)) in ("ok", "halted-goal-change")
    assert len(_remind_rows(project)) == 2
    assert _events(project, "gate-reminder") == []
    _verify("VC-008", rows=len(_remind_rows(project)), blocked_third=_true(True))


def test_third_reminder_blocked_after_timeline_tail_eviction(
    tmp_path: pathlib.Path,
) -> None:
    """Counterfactual seat: the count must survive the 200-event timeline
    tail. A `_timeline_has_event`-based counter loses the n=1/n=2 events
    here (~20 min tail < 60 min interval) and re-fires n=1, which this test
    would catch as a third row + a new event."""
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    for n in (1, 2):
        conductor._append_auto_decision_row(project, {
            "phase": "remind", "gate_id": "gate-0001", "gate_kind": "stalled",
            "gate_key": "k1", "reminder_n": n, "reminded_at": "2026-01-01T00:00:00Z",
            "detail": "seed",
        })
    st = _state(project)
    for n in (1, 2):
        st.timeline.append(
            "gate-reminder", key="k1",
            detail=f"gate-0001 stalled (reminder {n}/2)",
            data={"gate_id": "gate-0001", "gate_kind": "stalled", "gate_key": "k1",
                  "reminder_n": n, "waited_s": 0, "after_min": 30},
        )
    for _ in range(260):  # evict both reminder events from tail_events(limit=200)
        st.timeline.append("beat")
    _age_gate(gate_file, 120)
    assert conductor.tick(project, _state(project)) in ("ok", "halted-goal-change")
    assert len(_remind_rows(project)) == 2
    assert len(_events(project, "gate-reminder")) == 2
    assert [e["data"]["reminder_n"] for e in _events(project, "gate-reminder")] == [1, 2]


def test_answered_gate_leaves_zero_residual(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    _age_gate(gate_file, 31)
    text = gate_file.read_text(encoding="utf-8").replace(
        "status: pending", "status: approved"
    )
    gate_file.write_text(text, encoding="utf-8", newline="\n")
    assert conductor.tick(project, _state(project)) in ("ok", "halted-goal-change")
    assert _remind_rows(project) == []
    assert _events(project, "gate-reminder") == []
    _verify("VC-009", residual=len(_remind_rows(project)))


def test_running_row_suppresses_reminder(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(conductor, "orchestrate", lambda root, st: None)
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    _age_gate(gate_file, 31)
    _write_workers(project, "running")
    assert conductor.tick(project, _state(project)) in ("ok", "halted-goal-change")
    assert _remind_rows(project) == []
    assert _events(project, "gate-reminder") == []
    _verify("VC-010", in_flight_silent=_true(True))


def test_pending_row_also_suppresses_reminder(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counterfactual seat: condition 2 must be "non-terminal", not
    `status == "running"`. A `pending` row means the next tick launches it, so
    a `running`-only predicate would wrongly fire here."""
    monkeypatch.setattr(conductor, "orchestrate", lambda root, st: None)
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    _age_gate(gate_file, 31)
    _write_workers(project, "pending")
    assert conductor.tick(project, _state(project)) in ("ok", "halted-goal-change")
    assert _remind_rows(project) == []
    assert _events(project, "gate-reminder") == []
    _verify("VC-010", blocked_only_on_human_silent=_true(True))


def test_terminal_rows_do_not_suppress(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    _age_gate(gate_file, 31)
    _write_workers(project, "done", "failed")
    assert conductor.tick(project, _state(project)) in ("ok", "halted-goal-change")
    assert len(_remind_rows(project)) == 1


def test_goal_change_gate_reminds_while_halted(tmp_path: pathlib.Path) -> None:
    """Counterfactual seat: the hook must be in `tick`, before the goal
    detection — a hook in `orchestrate` never runs while
    `halted-goal-change` early-returns, and this test would stay silent."""
    project = _project(tmp_path)
    st = _state(project)
    assert conductor.tick(project, st) == "ok"
    os.utime(conductor.goal_path(project), None)
    assert conductor.tick(project, st) == "halted-goal-change"
    gate_file = next(iter(sorted(conductor.gates_dir(project).glob("gate-*.md"))))
    assert gates.parse(gate_file).kind == "goal-change"
    # `orchestrate` dispatched a `_scratch-roadmap` pending row on the way to
    # the halt; AC-007 reads the real queue, so clear it to model an otherwise
    # idle project (the reminder question is about gates, not scratch work).
    (project / ".agenticdoc" / "_workers.parallel").unlink(missing_ok=True)
    _age_gate(gate_file, 31)
    assert conductor.tick(project, st) == "halted-goal-change"
    rows = _remind_rows(project)
    events = _events(project, "gate-reminder")
    assert len(rows) == 1 and rows[0]["gate_kind"] == "goal-change"
    assert rows[0]["gate_key"] == ""
    assert len(events) == 1 and events[0]["data"]["gate_kind"] == "goal-change"
    _verify("VC-007", goal_change_reminder=len(events))


# ── ledger audit: remind rows are invisible to the decide consumers (D-006) ──

def test_remind_rows_are_invisible_to_decide_consumers(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    conductor._append_auto_decision_row(project, {
        "phase": "remind", "gate_id": "gate-0001", "gate_kind": "stalled",
        "gate_key": "k1", "reminder_n": 1, "reminded_at": "2026-01-01T00:00:00Z",
        "detail": "seed",
    })
    rows = conductor.auto_decision_rows(project)
    assert conductor._effective_auto_decision(rows, "gate-0001") is None
    assert conductor._escalate_recorded(rows, "gate-0001", "stalled-undecidable") is False
    assert conductor._shadow_decision_recorded(rows, "gate-0001") is False
    assert conductor._defer_recorded(rows, "gate-0001") is False
    assert conductor.auto_consumption_set(project) == set()
    assert conductor._reminder_count(rows, "gate-0001") == 1
