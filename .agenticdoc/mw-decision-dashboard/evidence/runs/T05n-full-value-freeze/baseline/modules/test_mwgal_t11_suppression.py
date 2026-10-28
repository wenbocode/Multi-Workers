"""
test_mwgal_t11_suppression.py — T-11 (key mw-autopilot-gate-alarm-liveness).

L1 tests for the per-key reminder suppression, the fail-loud dual channel and
the `gate_reminder_max` -> "interrupt budget" downgrade (AC-002 / AC-004).

The incident this card fixes: `gate-0024` burned both reminders four seconds
apart, then stayed silent for 158.3 minutes; a duplicated `stage-close` gate
stayed silent 6.78 h. Two causes: the suppression predicate was PROJECT-level
(any key's in-flight row silenced every gate) and a withheld reminder left zero
trace.

VC-002  a gate is silenced only by in-flight work on its OWN key
VC-004  a suppressed gate leaves a readable record (ledger + timeline) with
        gate id, reason and waited time; the timeline record rides the SAME
        fail-loud channel pair as the roadmap alarms (stderr + `config`)
VC-005  `gate-reminder-max` is an interrupt budget: past the cap there is no
        further interrupt but the gate stays visibly pending (`cap-reached`)
VC-006  stage-terminal suppression is recorded, not silent
VC-007  an empty/unresolvable key is never silenced (JCodingAss gate-0007/0008)
VC-008  `blocked_on_human` is per-key in the doctor surface too
"""
from __future__ import annotations

import datetime
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common  # noqa: E402
from autopilot import config, conductor, gates, timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _true(value: bool) -> str:
    return "true" if value else "false"


@pytest.fixture(autouse=True)
def _isolate_machine_layer(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """No real ~/.agents/autopilot-defaults.json may leak into these cases."""
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "no-machine-layer.json"))
    monkeypatch.delenv("MW_AUTOPILOT_HOME", raising=False)


# ── fixtures ──────────────────────────────────────────────────────────────────

def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / ".agenticdoc" / "_autopilot").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agenticdoc" / "goal.md").write_text("# Goal\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(tmp_path, cfg)
    return tmp_path


def _state(project: pathlib.Path) -> conductor.ConductorState:
    return conductor.ConductorState(
        timeline.Timeline(timeline.timeline_path(project)),
        conductor.goal_mtime_ns(project),
    )


def _remind(project: pathlib.Path) -> None:
    conductor._remind_pending_gates(  # noqa: SLF001 — the unit under test
        project, _state(project), config.default_config()
    )


def _events(project: pathlib.Path, ev: str | None = None) -> list[dict]:
    events = timeline.query_events(timeline.timeline_path(project)).events
    return [e for e in events if ev is None or e.get("ev") == ev]


def _config_events(project: pathlib.Path, needle: str) -> list[dict]:
    return [
        e for e in _events(project, "config")
        if needle in str(e.get("detail", ""))
    ]


def _ledger(project: pathlib.Path, phase: str) -> list[dict]:
    return [
        row for row in conductor.auto_decision_rows(project)
        if row.get("phase") == phase
    ]


def _suppressed(project: pathlib.Path) -> list[dict]:
    return _ledger(project, "remind-suppressed")


def _remind_rows(project: pathlib.Path) -> list[dict]:
    return _ledger(project, "remind")


def _create_gate(
    project: pathlib.Path,
    *,
    kind: str = "stalled",
    key: str | None = "k1",
    stage: int | None = None,
) -> pathlib.Path:
    return gates.create(
        conductor.gates_dir(project), kind, "test gate", stage=stage, key=key
    )


def _age_gate(gate_file: pathlib.Path, minutes: float) -> None:
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


def _write_workers(project: pathlib.Path, *specs: tuple[str, str]) -> None:
    """Rows `(status, key)` filed under `.agenticdoc/<key>/workers/...` with
    `origin: conductor` — the shape the per-key owner predicate attributes."""
    rows = [
        f"ap-{key}-w{i} | {status} | pi | timi "
        f"| {project.as_posix()}/.agenticdoc/{key}/workers/ap-{key}-w{i}/task.md "
        f"| 2026-01-01T00:00:00Z | 2026-01-01T00:00:00Z | m | conductor"
        for i, (status, key) in enumerate(specs)
    ]
    (project / ".agenticdoc" / "_workers.parallel").write_text(
        "\n".join(rows) + "\n", encoding="utf-8", newline="\n"
    )


def _seed_reminder(project: pathlib.Path, gate_id: str, n: int, kind: str = "stalled",
                   key: str = "k1") -> None:
    conductor._append_auto_decision_row(project, {
        "phase": "remind", "gate_id": gate_id, "gate_kind": kind,
        "gate_key": key, "reminder_n": n, "reminded_at": "2026-01-01T00:00:00Z",
        "detail": "seed",
    })


def _write_beat(project: pathlib.Path) -> None:
    path = project / ".agenticdoc" / "_autopilot" / "timeline.jsonl"
    ts = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    path.write_text(
        __import__("json").dumps(
            {"ts": ts, "seq": 1, "ev": "beat", "key": "-", "stage": None, "detail": ""}
        ) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _roadmap_text(stages: list[tuple[int, str, list[str]]]) -> str:
    lines = ["# Roadmap", "> generated_at: 2026-09-10T00:00:00+00:00", "> goal_mtime: 1", ""]
    for number, status, keys in stages:
        lines += [
            f"## Stage {number}: stage-{number}",
            f"> goal: deliver stage {number}",
            f"> status: {status}",
            "> key-status: " + ", ".join(f"{k}=running" for k in keys),
            "### Keys",
            "| key | role | depends_on |",
            "|-----|------|-----------|",
            *[f"| {k} | worker | - |" for k in keys],
            "",
        ]
    return "\n".join(lines)


def _write_roadmap(project: pathlib.Path, text: str) -> None:
    (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        text, encoding="utf-8", newline="\n"
    )


def _doctor_gates(project: pathlib.Path) -> dict:
    report = mw_common.doctor_report(
        project, fix=False, config=mw_common.load_providers(None)
    )
    return report["gates"]


# ── VC-002: per-key suppression ───────────────────────────────────────────────

def test_in_flight_key_suppresses_only_its_own_gate(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _age_gate(_create_gate(project, key="k1"), 31)
    _age_gate(_create_gate(project, key="k2"), 31)
    _write_workers(project, ("running", "k1"))
    _remind(project)
    reminded = {row["gate_key"] for row in _remind_rows(project)}
    suppressed = {(row["gate_key"], row["reason"]) for row in _suppressed(project)}
    assert reminded == {"k2"}, reminded
    assert suppressed == {("k1", "key-in-flight")}, suppressed
    _verify("VC-002", k2_reminded=_true(reminded == {"k2"}), k1_silenced=1)


def test_empty_key_gate_is_never_silenced(tmp_path: pathlib.Path) -> None:
    """JCodingAss `gate-0007`/`gate-0008` shape: `kind: stage-close`, empty key,
    while other keys are in flight. It must still remind."""
    project = _project(tmp_path)
    gate_file = _create_gate(project, kind="stage-close", key=None, stage=1)
    _age_gate(gate_file, 31)
    _write_workers(project, ("running", "k1"), ("pending", "k2"))
    _remind(project)
    rows = _remind_rows(project)
    assert len(rows) == 1 and rows[0]["gate_kind"] == "stage-close"
    assert rows[0]["gate_key"] == ""
    assert _suppressed(project) == []
    _verify("VC-007", empty_key_reminders=len(rows), fail_open=_true(True))


def test_unresolvable_stage_does_not_silence(tmp_path: pathlib.Path) -> None:
    """A gate whose stage resolves to a status outside the rank table is not
    provably terminal -> fail-open, the reminder fires."""
    project = _project(tmp_path)
    _write_roadmap(project, _roadmap_text([(1, "running", ["k1"])]))
    gate_file = _create_gate(project, kind="stalled", key="k1", stage=None)
    _age_gate(gate_file, 31)
    # an unknown status (not in _STAGE_STATUS_RANK) is not a terminal family
    _write_roadmap(project, _roadmap_text([(1, "weird-status", ["k1"])]))
    _remind(project)
    assert len(_remind_rows(project)) == 1
    assert _suppressed(project) == []
    _verify("VC-002", unknown_stage_status_reminds=_true(True))


# ── VC-004: suppressed means recorded, on the fail-loud channels ─────────────

def test_suppression_record_is_visible_and_actionable(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path)
    _age_gate(_create_gate(project, key="k1"), 31)
    _write_workers(project, ("running", "k1"))
    _remind(project)
    captured = capsys.readouterr()

    rows = _suppressed(project)
    assert len(rows) == 1
    row = rows[0]
    assert row["gate_id"] == "gate-0001" and row["gate_kind"] == "stalled"
    assert row["gate_key"] == "k1" and row["reason"] == "key-in-flight"
    assert row["waited_min"] >= 31
    assert "act: /autopilot gate gate-0001" in row["detail"]

    err = [ln for ln in captured.err.splitlines() if "gate reminder suppressed" in ln]
    assert len(err) == 1, captured.err
    assert "gate-0001" in err[0] and "reason=key-in-flight" in err[0]
    assert "act: /autopilot gate gate-0001" in err[0]

    events = _config_events(project, "gate reminder suppressed")
    assert len(events) == 1, events
    assert events[0]["data"]["reason"] == "key-in-flight"
    assert events[0]["data"]["waited_min"] >= 31
    # the interruption channel stays untouched by a suppression
    assert _events(project, "gate-reminder") == []
    _verify(
        "VC-004",
        ledger=len(rows),
        stderr=len(err),
        timeline=len(events),
        actionable=_true("act:" in err[0]),
    )


def test_suppression_record_is_rate_limited_per_window(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    _age_gate(gate_file, 31)
    _write_workers(project, ("running", "k1"))
    _remind(project)
    _remind(project)  # same 30-min window: no duplicate line
    assert len(_suppressed(project)) == 1
    _age_gate(gate_file, 61)  # next window
    _remind(project)
    rows = _suppressed(project)
    assert [row["bucket"] for row in rows] == [1, 2]
    assert len(_config_events(project, "gate reminder suppressed")) == 2
    _verify("VC-004", records=len(rows), buckets="1,2", deduped_in_window=_true(True))


# ── VC-005: the cap is an interrupt budget, not a silence switch ─────────────

def test_cap_reached_records_without_extra_interrupt(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    for n in (1, 2):
        _seed_reminder(project, "gate-0001", n)
    _age_gate(gate_file, 120)
    _remind(project)
    assert len(_remind_rows(project)) == 2  # no third interrupt
    assert _events(project, "gate-reminder") == []
    rows = _suppressed(project)
    assert len(rows) == 1 and rows[0]["reason"] == "cap-reached"
    assert "已达打断上限，仍待处理" in rows[0]["detail"]
    assert conductor._reminder_count(conductor.auto_decision_rows(project), "gate-0001") == 2
    _verify("VC-005", interrupts=2, cap_record=rows[0]["reason"], still_pending=_true(True))


def test_below_cap_still_interrupts(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    _seed_reminder(project, "gate-0001", 1)
    _age_gate(gate_file, 61)
    _remind(project)
    assert [row["reminder_n"] for row in _remind_rows(project)] == [1, 2]
    assert _suppressed(project) == []
    assert len(_events(project, "gate-reminder")) == 1


def test_cap_reached_detail_marks_still_pending_on_stdout(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path)
    gate_file = _create_gate(project, key="k1")
    for n in (1, 2):
        _seed_reminder(project, "gate-0001", n)
    _age_gate(gate_file, 120)
    _remind(project)
    captured = capsys.readouterr()
    assert "已达打断上限，仍待处理" in captured.err
    _verify("VC-005", cap_marked_in_stderr=_true(True))


# ── VC-006: stage-terminal suppression is recorded ───────────────────────────

def test_stage_terminal_suppression_leaves_a_record(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_roadmap(project, _roadmap_text([(1, "closed", ["k1"])]))
    gate_file = _create_gate(project, kind="stage-close", key="k1", stage=1)
    _age_gate(gate_file, 31)
    _remind(project)
    assert _remind_rows(project) == []
    assert _events(project, "gate-reminder") == []
    rows = _suppressed(project)
    assert len(rows) == 1 and rows[0]["reason"] == "stage-terminal"
    assert rows[0]["gate_id"] == "gate-0001"
    assert len(_config_events(project, "reason=stage-terminal")) == 1
    _verify("VC-006", stage_terminal_records=len(rows), silent=_true(False))


# ── VC-004: the funnel order is the attribution priority ─────────────────────

def test_suppression_reason_funnel_priority() -> None:
    import time

    now = time.time()

    class _G:
        def __init__(self, gid: str, key: str, stage: int | None):
            self.id = gid
            self.kind = "stalled"
            self.key = key
            self.stage = stage
            stamp = datetime.datetime.fromtimestamp(
                now - 400 * 60, datetime.timezone.utc
            ).isoformat(timespec="seconds")
            self.created_at = stamp

    rows = [{
        "status": "running",
        "task_path": f"/x/.agenticdoc/{key}/workers/w/task.md",
        "origin": "conductor",
    } for key in ("ka",)]
    terminal = {1: "closed"}
    of_key = {key: 1 for key in ("ka", "kb", "kc")}
    counts = {"g-inflight": 2, "g-cap": 2, "g-stage": 0, "g-due": 0}

    g_inflight = _G("g-inflight", "ka", 1)   # in-flight AND cap AND terminal
    g_cap = _G("g-cap", "kb", 1)             # cap AND terminal, no in-flight
    g_stage = _G("g-stage", "kc", 1)         # terminal only
    g_due = _G("g-due", "kd", None)          # stage/key off-roadmap -> due
    silenced: list[tuple] = []
    due = conductor.pending_gate_reminders(
        [g_inflight, g_cap, g_stage, g_due],
        rows,
        counts,
        now,
        30,
        2,
        stage_status=terminal,
        stage_of_key=of_key,
        silenced=silenced,
    )
    reasons = {gate.id: reason for gate, _, reason in silenced}
    assert reasons == {
        "g-inflight": "key-in-flight",
        "g-cap": "cap-reached",
        "g-stage": "stage-terminal",
    }, reasons
    assert [g.id for g, _ in due] == ["g-due"]
    _verify(
        "VC-004",
        funnel="key-in-flight>cap-reached>stage-terminal>due",
        attributed=len(reasons),
        due=len(due),
    )


# ── VC-002/VC-004: emission is fail-loud on both channels ────────────────────

def test_reminder_emission_is_fail_loud_dual_channel(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture[str]
) -> None:
    project = _project(tmp_path)
    _age_gate(_create_gate(project, key="k1"), 31)
    _remind(project)
    captured = capsys.readouterr()
    rows = _remind_rows(project)
    events = _events(project, "gate-reminder")
    err = [ln for ln in captured.err.splitlines() if "gate reminder:" in ln]
    assert len(rows) == 1 and len(events) == 1 and len(err) == 1, (rows, events, err)
    assert "gate-0001" in err[0] and "stalled" in err[0] and "key=k1" in err[0]
    assert "reason=-" in err[0] and "act: /autopilot gate gate-0001" in err[0]
    assert events[0]["data"]["waited_s"] >= 31 * 60
    _verify("VC-004", ledger=1, timeline=1, stderr=1)


# ── VC-008: blocked_on_human is per-key in the doctor surface ────────────────

def test_blocked_on_human_is_per_key(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_beat(project)
    _create_gate(project, key="k1")

    # axis 2 holds for k1: no in-flight row under k1 -> blocked
    assert _doctor_gates(project)["blocked_on_human"] is True

    # another key's in-flight row no longer explains this gate away
    _write_workers(project, ("running", "k2"))
    assert _doctor_gates(project)["blocked_on_human"] is True

    # the gate's own key in flight does clear it
    _write_workers(project, ("running", "k1"))
    assert _doctor_gates(project)["blocked_on_human"] is False

    # a terminal row is history, not in flight
    _write_workers(project, ("done", "k1"))
    assert _doctor_gates(project)["blocked_on_human"] is True
    _verify("VC-008", per_key="k1/k2", other_key_clears=_true(False))


def test_blocked_on_human_empty_key_is_never_cleared(tmp_path: pathlib.Path) -> None:
    """A key-less (`stage-close`) gate can never be explained away by any key's
    work — the doctor axis and the reminder judgment agree (fail-open)."""
    project = _project(tmp_path)
    _write_beat(project)
    _create_gate(project, kind="stage-close", key=None, stage=1)
    _write_workers(project, ("running", "k1"))
    assert _doctor_gates(project)["blocked_on_human"] is True
