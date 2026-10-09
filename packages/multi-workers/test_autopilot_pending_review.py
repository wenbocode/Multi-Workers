"""test_autopilot_pending_review.py — T-08 `pending-review` (case 2) + legal
reopen, plus the [PM 追加] time-effectiveness defaults materialisation.

Key mw-autopilot-slot-capacity, AC-027 / AC-028 / AC-019; VC-039 / VC-040 /
VC-041 / VC-042 / VC-043. Covers:

* the `pending-review` key-status on both sides (Python enum here; the TS
  mirror is exercised by the coding-agent vitest suites) and the three
  invariants: non-terminal (blocks closure), no dependency unlock
  (`_DEP_SATISFIED`), no dispatch (`_DISPATCH_SKIP_STATUSES`);
* the closure precondition (other keys terminal AND no in-flight row) pushing
  the whole eligible batch in one tick;
* the 48h fallback reading the gate's `expires_at` (with the
  `created_at + 48h` recompute as the field-absent fallback) and leaving the
  status unchanged;
* legal reopen: `review-decided{resume|rework|escalate}` touches key-status
  only, never `done`/`closed-legacy`, and never reopens a stage (T-01's
  monotonic guard refuses with one deduplicated `stage-reopen-refused`);
* the PM-added defect fix: every gate created through the single `_create_gate`
  choke point carries `reason_code`-class defaults `expires_at` +
  `default_action`, written BEFORE the `created` evidence snapshot (so the
  T-06 replay-binding sha256 still matches) and enough to make the doctor
  healthy.

Non-vacuous counterfactuals are inline (each asserts the opposite of the
regression it guards).
"""
from __future__ import annotations

import datetime
import hashlib
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common  # noqa: E402
from autopilot import config, conductor, evidence, gates, roadmap, timeline  # noqa: E402


def _verify(tag: str, **kv: object) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _true(value: bool) -> str:
    return "true" if value else "false"


@pytest.fixture(autouse=True)
def _isolate_machine_layer(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> None:
    """No real ~/.agents/autopilot-defaults.json may leak into these cases."""
    monkeypatch.setenv("MW_AUTOPILOT_FILE", str(tmp_path / "no-machine-layer.json"))
    monkeypatch.delenv("MW_AUTOPILOT_HOME", raising=False)


# ── fixtures / helpers ────────────────────────────────────────────────────────

def _project(tmp_path: pathlib.Path, *, mode: str = "off") -> pathlib.Path:
    ap = tmp_path / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".mw").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agenticdoc" / "goal.md").write_text(
        "# Goal\n\nShip it.\n", encoding="utf-8"
    )
    cfg = config.default_config()
    cfg["enabled"] = True
    cfg["auto_gate_mode"] = mode
    config.save_config(tmp_path, cfg)
    return tmp_path


def _state(project: pathlib.Path) -> conductor.ConductorState:
    tl = timeline.Timeline(timeline.timeline_path(project))
    return conductor.ConductorState(tl, conductor.goal_mtime_ns(project))


def _events(project: pathlib.Path) -> list[dict]:
    return timeline.query_events(timeline.timeline_path(project)).events


def _roadmap(
    project: pathlib.Path,
    keys: dict[str, str],
    *,
    deps: dict[str, str] | None = None,
    stage_status: str = "running",
) -> None:
    deps = deps or {}
    key_status = ", ".join(f"{k}={v}" for k, v in keys.items())
    rows = "\n".join(f"| {k} | worker | {deps.get(k, '-')} |" for k in keys)
    text = (
        "# Roadmap\n"
        "> generated_at: 2026-09-10T00:00:00+00:00\n"
        "> goal_mtime: 1789000000000\n"
        "\n"
        "## Stage 1: first\n"
        "> goal: deliver k1\n"
        f"> status: {stage_status}\n"
        f"> key-status: {key_status}\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        f"{rows}\n"
    )
    (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        text, encoding="utf-8"
    )


def _index(project: pathlib.Path, phases: dict[str, str]) -> None:
    rows = "".join(
        f"| {key} | active | {phase} | — | - | desc | 2026-09-10T00:00:00 |\n"
        for key, phase in phases.items()
    )
    (project / ".agenticdoc" / "_index.parallel").write_text(rows, encoding="utf-8")


def _rows(project: pathlib.Path, prefix: str) -> list[dict]:
    return [
        row for row in mw_common.parse_workers_file(mw_common.workers_path(project))
        if row["task_key"].startswith(prefix)
    ]


def _key_status(project: pathlib.Path, key: str, number: int = 1) -> str:
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    stage = roadmap.stage_by_number(rm, number)
    assert stage is not None
    return stage.key_status[key]


def _stage_status(project: pathlib.Path, number: int = 1) -> str:
    rm = roadmap.load_roadmap(project / ".agenticdoc" / "_autopilot" / "_roadmap.md")
    stage = roadmap.stage_by_number(rm, number)
    assert stage is not None
    return stage.status


def _gate_kinds(project: pathlib.Path, kind: str) -> list[gates.Gate]:
    return [
        gate for gate in gates.enumerate(conductor.gates_dir(project))
        if gate.kind == kind
    ]


def _make_service_running(project: pathlib.Path) -> None:
    """Doctor's service check reads `.mw/mw.pid`; a live PID removes the
    'service not running' issue so the gate fields are the only variable."""
    mw_common.pid_file(project).parent.mkdir(parents=True, exist_ok=True)
    mw_common.pid_file(project).write_text(str(os.getpid()), encoding="utf-8")


def _answer(gate: gates.Gate, decision: str, note: str = "reviewed") -> None:
    text = gate.path.read_text(encoding="utf-8")
    text = text.replace("status: pending", f"status: {decision}")
    text = text.replace("\nnote:\n", f"\nnote: '{note}'\n")
    gate.path.write_text(text, encoding="utf-8")


# ── enum + invariants ─────────────────────────────────────────────────────────

def test_pending_review_enum_and_the_three_invariants() -> None:
    """`pending-review` exists on the Python side, is non-terminal, does not
    unlock dependencies and is not dispatched. An unknown value still fails
    closed (cross-language contract, D-021)."""
    assert "pending-review" in roadmap.KEY_STATUSES
    assert "pending-review" not in conductor._DEP_SATISFIED
    assert "pending-review" in conductor._DISPATCH_SKIP_STATUSES
    assert "pending-review" not in ("done", "closed-legacy")
    with pytest.raises(roadmap.RoadmapError) as excinfo:
        roadmap._parse_key_status("k1=pending-review2", 1, 1)
    # T-22: measured membership facts, not hand-written counts.
    _verify(
        "VC-039",
        enum=int("pending-review" in roadmap.KEY_STATUSES),
        dep_satisfied=int("pending-review" in conductor._DEP_SATISFIED),
        dispatched=int("pending-review" not in conductor._DISPATCH_SKIP_STATUSES),
        unknown_value_fail_closed=_true(excinfo.type is roadmap.RoadmapError),
    )


def test_pending_review_does_not_unlock_dependents(tmp_path: pathlib.Path) -> None:
    """Behavioral red line (VC-D2-02): k2 depends on k1; k1 pending-review
    leaves k2 undispatched. Negative control: k1 done must dispatch k2."""
    for k1_status, expect_dispatch in (("pending-review", False), ("done", True)):
        project = _project(tmp_path / k1_status)
        _roadmap(project, {"k1": k1_status, "k2": "running"}, deps={"k2": "k1"})
        _index(project, {"k1": "DONE", "k2": "SPEC"})
        st = _state(project)
        conductor.orchestrate(project, st)
        dispatched = _rows(project, "ap-k2-")
        assert bool(dispatched) is expect_dispatch, (k1_status, dispatched)
        if not expect_dispatch:
            assert conductor._deps_satisfied(("k1",), {"k1": k1_status}) is False
    _verify(
        "VC-D2-02",
        dep_locked=_true(
            conductor._deps_satisfied(("k1",), {"k1": "pending-review"}) is False
        ),
        negative_control="dispatched",
    )


def test_pending_review_key_is_not_redispatched(tmp_path: pathlib.Path) -> None:
    """The dispatch skip tuple (conductor `_DISPATCH_SKIP_STATUSES`) must
    include `pending-review`; otherwise the key keeps burning tokens."""
    for status, expect_dispatch in (("pending-review", False), ("running", True)):
        project = _project(tmp_path / status)
        _roadmap(project, {"k1": status})
        _index(project, {"k1": "SPEC"})
        st = _state(project)
        conductor.orchestrate(project, st)
        dispatched_rows = _rows(project, "ap-k1-")
        if status == "pending-review":
            pending_review_rows = len(dispatched_rows)
        assert bool(dispatched_rows) is expect_dispatch, status
    _verify("VC-D2-03", pending_review_rows=pending_review_rows,
            negative_control="dispatched")


# ── closure precondition ──────────────────────────────────────────────────────

def test_pending_review_blocks_stage_closure(tmp_path: pathlib.Path) -> None:
    """VC-039: a pending-review key is NOT terminal, so no dossier and no
    `stage-close` gate. Counterfactual: with it done, closure happens."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "done", "k2": "done", "k3": "pending-review"})
    _index(project, {"k1": "DONE", "k2": "DONE", "k3": "SPEC"})
    for key in ("k1", "k2"):
        (project / ".agenticdoc" / key).mkdir(parents=True, exist_ok=True)
        (project / ".agenticdoc" / key / "achieved.md").write_text(
            "# Achieved\n", encoding="utf-8"
        )
    st = _state(project)
    conductor.orchestrate(project, st)
    dossier = project / ".agenticdoc" / "_autopilot" / "stages" / "stage-1-close.md"
    assert not dossier.is_file()
    assert _gate_kinds(project, "stage-close") == []
    assert all(e["ev"] != "stage-close" for e in _events(project))

    # counterfactual: k3 terminal -> dossier + close gate in the same shape
    project2 = _project(tmp_path / "all-done")
    _roadmap(project2, {"k1": "done", "k2": "done", "k3": "done"})
    _index(project2, {"k1": "DONE", "k2": "DONE", "k3": "DONE"})
    conductor.orchestrate(project2, _state(project2))
    assert (
        project2 / ".agenticdoc" / "_autopilot" / "stages" / "stage-1-close.md"
    ).is_file()
    assert len(_gate_kinds(project2, "stage-close")) == 1
    _verify(
        "VC-039",
        blocked=_true(not dossier.is_file()),
        counterfactual_dossier=int(
            (
                project2 / ".agenticdoc" / "_autopilot" / "stages" / "stage-1-close.md"
            ).is_file()
        ),
    )


def test_closure_precondition_batches_all_pending_reviews(tmp_path: pathlib.Path) -> None:
    """VC-040: once every OTHER key is terminal, the whole eligible
    pending-review batch is pushed in the same tick (one `review-escalated`
    each, trigger=closure). Counterfactual: another key running => none."""
    project = _project(tmp_path)
    _roadmap(
        project,
        {"k1": "done", "k2": "pending-review", "k3": "pending-review"},
    )
    _index(project, {"k1": "DONE", "k2": "SPEC", "k3": "SPEC"})
    st = _state(project)
    conductor.orchestrate(project, st)
    batch = [
        e for e in _events(project)
        if e["ev"] == "review-escalated" and (e.get("data") or {}).get("trigger") == "closure"
    ]
    assert sorted(e["key"] for e in batch) == ["k2", "k3"]
    assert {e["stage"] for e in batch} == {1}
    # no close gate, no status rewrite
    assert _gate_kinds(project, "stage-close") == []
    assert _key_status(project, "k2") == "pending-review"
    assert _key_status(project, "k3") == "pending-review"

    # counterfactual: k1 running -> the precondition is not met
    project2 = _project(tmp_path / "not-quiet")
    _roadmap(
        project2,
        {"k1": "running", "k2": "pending-review", "k3": "pending-review"},
    )
    _index(project2, {"k1": "SPEC", "k2": "SPEC", "k3": "SPEC"})
    conductor.orchestrate(project2, _state(project2))
    closure_events = [
        e for e in _events(project2)
        if e["ev"] == "review-escalated" and (e.get("data") or {}).get("trigger") == "closure"
    ]
    assert closure_events == []
    _verify("VC-040", batched=len(batch), counterfactual_batched=len(closure_events))


def test_in_flight_pending_review_key_is_not_pushed(tmp_path: pathlib.Path) -> None:
    """The AC-027 "该 key 无 in-flight 行" clause: a pending-review key whose
    worker is still in flight is excluded from the batch."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "done", "k2": "pending-review"})
    _index(project, {"k1": "DONE", "k2": "SPEC"})
    (project / ".agenticdoc" / "k2" / "workers" / "ap-k2-l3-a1").mkdir(parents=True)
    (project / ".agenticdoc" / "k2" / "workers" / "ap-k2-l3-a1" / "task.md").write_text(
        "type: reviewer\n", encoding="utf-8"
    )
    mw_common.workers_path(project).parent.mkdir(parents=True, exist_ok=True)
    mw_common.workers_path(project).write_text(
        mw_common.serialize_entry({
            "task_key": "ap-k2-l3-a1",
            "status": "running",
            "cli": "pi",
            "provider": "timi",
            "task_path": str(
                project / ".agenticdoc" / "k2" / "workers" / "ap-k2-l3-a1" / "task.md"
            ),
            "dispatched_at": "2026-09-10T00:00:00",
            "updated_at": "2026-09-10T00:00:00",
            "model": "",
            "origin": mw_common.WORKER_ORIGIN_CONDUCTOR,
        }) + "\n",
        encoding="utf-8",
    )
    st = _state(project)
    conductor.orchestrate(project, st)
    in_flight_escalations = [
        e for e in _events(project)
        if e["ev"] == "review-escalated" and e["key"] == "k2"
    ]
    assert not in_flight_escalations
    _verify("VC-040", in_flight_excluded=_true(not in_flight_escalations))


# ── 48h deadline fallback (reads expires_at) ──────────────────────────────────

def test_deadline_escalation_reads_expires_at_and_keeps_status(
    tmp_path: pathlib.Path,
) -> None:
    """VC-041: a pending-review key past its gate deadline gets
    `review-escalated` and the key-status is UNCHANGED. The gate's
    `created_at` is fresh, so only `expires_at` can explain the escalation
    (proves the field is read, not `created_at + 48h`)."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "pending-review", "k2": "running"})
    _index(project, {"k1": "SPEC", "k2": "SPEC"})
    st = _state(project)
    past = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    ).isoformat(timespec="seconds")
    conductor._create_gate(
        project, st, "stalled", "review k1?", key="k1", stage=1, refs=["review:k1"],
        machine_fields={"reason_code": "l3-no-verdict", "expires_at": past},
    )
    conductor.orchestrate(project, st)
    escalated = [
        e for e in _events(project)
        if e["ev"] == "review-escalated" and e["key"] == "k1"
    ]
    assert len(escalated) == 1
    data = escalated[0]["data"]
    assert data["deadline_source"] == "expires_at"
    assert data["trigger"] == "deadline"
    assert _key_status(project, "k1") == "pending-review"

    # counterfactual: a fresh gate (not due) raises nothing
    project2 = _project(tmp_path / "not-due")
    _roadmap(project2, {"k1": "pending-review", "k2": "running"})
    _index(project2, {"k1": "SPEC", "k2": "SPEC"})
    st2 = _state(project2)
    conductor._create_gate(
        project2, st2, "stalled", "review k1?", key="k1", stage=1, refs=["review:k1"],
        machine_fields={"reason_code": "l3-no-verdict"},
    )
    conductor.orchestrate(project2, st2)
    counterfactual_escalated = [
        e for e in _events(project2) if e["ev"] == "review-escalated"
    ]
    assert not counterfactual_escalated
    _verify(
        "VC-041",
        escalated=len(escalated),
        state_unchanged=_true(_key_status(project, "k1") == "pending-review"),
        counterfactual_escalated=len(counterfactual_escalated),
    )


def test_deadline_falls_back_to_created_at_plus_48h(tmp_path: pathlib.Path) -> None:
    """Field-absent fallback: no `expires_at` => recompute `created_at + 48h`;
    the `unknown (no field)` semantics survive (source == created_at+48h)."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "pending-review", "k2": "running"})
    _index(project, {"k1": "SPEC", "k2": "SPEC"})
    gdir = conductor.gates_dir(project)
    gdir.mkdir(parents=True, exist_ok=True)
    old = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=72)
    ).isoformat(timespec="seconds")
    (gdir / "gate-0001.md").write_text(
        "---\n"
        "id: gate-0001\n"
        "gate_schema: 2\n"
        "kind: stalled\n"
        "stage: 1\n"
        "key: k1\n"
        f"created_at: {old}\n"
        "created_by: conductor\n"
        "question: review k1?\n"
        "context_refs:\n  - review:k1\n"
        "status: pending\n"
        "answered_at:\n"
        "answered_by:\n"
        "note:\n"
        "expires_at:\n"
        "default_action:\n"
        "---\n\n# Gate gate-0001 (stalled)\n\nreview k1?\n",
        encoding="utf-8",
    )
    st = _state(project)
    conductor.orchestrate(project, st)
    escalated = [
        e for e in _events(project)
        if e["ev"] == "review-escalated" and e["key"] == "k1"
    ]
    assert len(escalated) == 1
    assert escalated[0]["data"]["deadline_source"] == "created_at+48h"
    assert _key_status(project, "k1") == "pending-review"
    _verify(
        "VC-041",
        fallback=escalated[0]["data"]["deadline_source"],
        state_unchanged=_true(_key_status(project, "k1") == "pending-review"),
    )


# ── legal reopen ──────────────────────────────────────────────────────────────

def test_review_decided_has_no_done_or_closed_legacy_exit(tmp_path: pathlib.Path) -> None:
    """D-006: resume/rework -> running, escalate -> stalled. `done` and
    `closed-legacy` are unreachable from the review path."""
    observed: dict[str, str] = {}
    for outcome, expected in (
        ("resume", "running"),
        ("rework", "running"),
        ("escalate", "stalled"),
    ):
        project = _project(tmp_path / outcome)
        _roadmap(project, {"k1": "pending-review"})
        st = _state(project)
        assert conductor.apply_review_decision(project, st, "k1", 1, outcome) is True
        assert _key_status(project, "k1") == expected
        observed[outcome] = _key_status(project, "k1")
        decided = [e for e in _events(project) if e["ev"] == "review-decided"]
        assert len(decided) == 1
        assert decided[0]["data"] == {"key": "k1", "stage": 1, "outcome": outcome}
    with pytest.raises(ValueError) as done_exc:
        conductor.apply_review_decision(project, st, "k1", 1, "done")
    with pytest.raises(ValueError) as legacy_exc:
        conductor.apply_review_decision(project, st, "k1", 1, "closed-legacy")
    assert _key_status(project, "k1") == "stalled"
    _verify(
        "VC-042",
        resume=observed["resume"],
        rework=observed["rework"],
        escalate=observed["escalate"],
        done_exit="rejected" if done_exc.type is ValueError else "accepted",
        closed_legacy_exit=(
            "rejected" if legacy_exc.type is ValueError else "accepted"
        ),
    )


def test_answered_review_gate_maps_to_review_decided(tmp_path: pathlib.Path) -> None:
    """The human answers the review gate: approve -> resume, reject -> rework
    (NOT closed-legacy). Consumption is durable (a replay is a no-op)."""
    observed: dict[str, str] = {}
    closed_legacy_produced = 0
    replay_counts: list[int] = []
    for decision, expected in (("approved", "running"), ("rejected", "running")):
        project = _project(tmp_path / decision)
        _roadmap(project, {"k1": "pending-review", "k2": "running"})
        _index(project, {"k1": "SPEC", "k2": "SPEC"})
        st = _state(project)
        gate_path = conductor.defer_key_to_review(
            project, st, "k1", 1, question="review k1?"
        )
        assert gate_path is not None
        gate = gates.parse(gate_path)
        assert gate.default_action == "escalate-to-human"
        assert gate.expires_at is not None
        _answer(gate, decision)
        conductor.orchestrate(project, st)
        assert _key_status(project, "k1") == expected
        observed[decision] = _key_status(project, "k1")
        closed_legacy_produced += int(_key_status(project, "k1") == "closed-legacy")
        decided = [e for e in _events(project) if e["ev"] == "review-decided"]
        assert len(decided) == 1
        assert decided[0]["data"]["outcome"] == (
            "resume" if decision == "approved" else "rework"
        )
        # replay: a second orchestrate must not re-apply the answer
        conductor.orchestrate(project, st)
        decided = [e for e in _events(project) if e["ev"] == "review-decided"]
        assert len(decided) == 1
        replay_counts.append(len(decided))
    _verify(
        "VC-042",
        approved=observed["approved"],
        rejected=observed["rejected"],
        closed_legacy_produced=closed_legacy_produced,
        replay_idempotent=_true(all(count == 1 for count in replay_counts)),
    )


def test_conductor_never_reopens_a_closed_stage(tmp_path: pathlib.Path) -> None:
    """VC-042: a `closed` stage cannot be written back to `running`; the
    refusal is recorded once (deduplicated) by T-01's guard."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "done"}, stage_status="closed")
    st = _state(project)
    rm_path = roadmap.roadmap_path(project)
    assert conductor._set_stage_status(project, st, rm_path, 1, "running") is False
    assert _stage_status(project) == "closed"
    refused = [e for e in _events(project) if e["ev"] == "stage-reopen-refused"]
    assert len(refused) == 1
    first_refusal_count = len(refused)
    # dedup: the same refusal is not re-logged
    assert conductor._set_stage_status(project, st, rm_path, 1, "running") is False
    refused = [e for e in _events(project) if e["ev"] == "stage-reopen-refused"]
    assert len(refused) == 1
    _verify(
        "VC-042",
        refused=len(refused),
        dedup=_true(len(refused) == first_refusal_count),
        stage=_stage_status(project),
    )


def test_replayed_answered_gate_keeps_closed_stage_and_opens_no_gate(
    tmp_path: pathlib.Path,
) -> None:
    """VC-043 (JC gate-0008 shape): an answered `stage-confirm` whose
    consumption record was lost must NOT reopen the closed stage and must NOT
    mint a new `stage-close` gate."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "done"}, stage_status="closed")
    st = _state(project)
    gdir = conductor.gates_dir(project)
    gdir.mkdir(parents=True, exist_ok=True)
    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    (gdir / "gate-0001.md").write_text(
        "---\n"
        "id: gate-0001\n"
        "gate_schema: 2\n"
        "kind: stage-confirm\n"
        "stage: 1\n"
        "key:\n"
        "created_at: 2026-09-11T00:00:00+00:00\n"
        "created_by: conductor\n"
        "question: start stage 1?\n"
        "context_refs:\n  - stage-1\n"
        "status: approved\n"
        "answered_at: 2026-09-11T00:01:00+00:00\n"
        "answered_by: human\n"
        f"note: 'replayed at {now}'\n"
        "default_action: escalate-to-human\n"
        "expires_at: 2026-09-13T00:00:00+00:00\n"
        "---\n\n# Gate gate-0001 (stage-confirm)\n\nstart stage 1?\n",
        encoding="utf-8",
    )
    conductor.orchestrate(project, st)
    assert _stage_status(project) == "closed"
    assert _gate_kinds(project, "stage-close") == []
    # the replayed answer opened no NEW gate (only the fixture itself remains)
    confirm = _gate_kinds(project, "stage-confirm")
    assert [g.id for g in confirm] == ["gate-0001"]
    _verify(
        "VC-043",
        stage=_stage_status(project),
        new_gates=len(_gate_kinds(project, "stage-close")),
    )


# ── [PM 追加] time-effectiveness defaults ─────────────────────────────────────

def test_fresh_gate_carries_all_decision_fields_for_every_kind(
    tmp_path: pathlib.Path,
) -> None:
    """AC-019 / AC-026: a gate created through the single choke point carries
    `expires_at` + `default_action`, so `mw_common._gate_missing_fields` is
    empty for every kind (T-20: a legal `reason_code` is still accepted for
    every kind, it is just not required outside `stalled`)."""
    project = _project(tmp_path)
    st = _state(project)
    for index, kind in enumerate(gates.GATE_KINDS):
        path = conductor._create_gate(
            project, st, kind, f"q {kind}?", key="k1", stage=1, refs=[f"k1:{kind}"],
            machine_fields={"reason_code": "stage-close-ok"},
        )
        gate = gates.parse(path)
        assert gate.default_action == "escalate-to-human", kind
        assert gate.expires_at is not None, kind
        assert mw_common._gate_missing_fields(gate) == [], kind
        created = datetime.datetime.fromisoformat(gate.created_at)
        expires = datetime.datetime.fromisoformat(gate.expires_at)
        assert expires - created == datetime.timedelta(hours=48), kind
        assert gate.expires_at[-6:] == gate.created_at[-6:], kind  # same offset form
    _verify(
        "VC-024",
        kinds=len(gates.GATE_KINDS),
        missing_fields=len(mw_common._gate_missing_fields(gate)),
        ttl_hours=int((expires - created).total_seconds() // 3600),
        default_action=gate.default_action,
    )


def test_doctor_is_healthy_for_a_project_whose_only_content_is_a_gate(
    tmp_path: pathlib.Path,
) -> None:
    """The PM defect: before the fix the doctor cried wolf on every fresh
    gate (`missing_fields=[expires_at, default_action]`, healthy=False). Now
    the same reproduction is empty and healthy."""
    project = _project(tmp_path)
    _make_service_running(project)
    st = _state(project)
    path = conductor._create_gate(
        project, st, "stalled", "review k1?", key="k1", stage=1, refs=["review:k1"],
        machine_fields={"reason_code": "l3-no-verdict"},
    )
    gate = gates.parse(path)
    assert mw_common._gate_missing_fields(gate) == []
    report = mw_common.doctor_report(project)
    assert report["summary"]["issues"] == [], report["summary"]["issues"]
    assert report["summary"]["healthy"] is True
    assert report["gates"]["missing_fields"] == []
    gates_text_lines = [
        line for line in mw_common.format_doctor_text(report).splitlines()
        if line.startswith("gates:")
    ]
    assert not gates_text_lines
    _verify(
        "VC-024",
        missing_fields=len(report["gates"]["missing_fields"]),
        healthy=_true(report["summary"]["healthy"]),
        gates_text_line=len(gates_text_lines),
    )


def test_defaults_are_written_before_the_created_evidence_snapshot(
    tmp_path: pathlib.Path,
) -> None:
    """T-06 replay binding: the defaults must land BEFORE the `created`
    snapshot or `gate_file.sha256` would not match the final file and every
    gate would read `replay-misbound`."""
    project = _project(tmp_path, mode="shadow")
    st = _state(project)
    path = conductor._create_gate(
        project, st, "stalled", "review k1?", key="k1", stage=1, refs=["review:k1"],
        machine_fields={"reason_code": "l3-no-verdict"},
    )
    gate = gates.parse(path)
    sidecar = evidence.read_sidecar(conductor.gates_dir(project), gate.id)
    assert sidecar is not None
    created = next(s for s in sidecar["snapshots"] if s["reason"] == "created")
    recorded_sha = created["gate_file"]["sha256"]
    current_sha = hashlib.sha256(path.read_bytes()).hexdigest()
    # counterfactual: had the defaults been stamped AFTER the snapshot, the
    # file would have changed and these two would differ (replay-misbound).
    assert current_sha == recorded_sha
    binding, drift, refusal = conductor.gate_evidence_state(project, gate, st)
    assert refusal != "replay-misbound", refusal
    _verify(
        "VC-045",
        snapshot_sha_matches=_true(current_sha == recorded_sha),
        replay_misbound=int(refusal == "replay-misbound"),
    )


# ── T-18: the goal-change bypass creation site ──────────────────────────────

def test_goal_change_gate_carries_time_effectiveness_defaults(
    tmp_path: pathlib.Path,
) -> None:
    """T-18 regression: `tick` creates the goal-change gate DIRECTLY (not
    through `_create_gate`), so it must stamp the same defaults itself.

    Drives the real goal-change path (a touched goal.md + `tick`), never a
    hand-built gate file. Before the T-18 fix this gate was the one "waiting
    for a human" kind with no TTL: `missing_fields=[expires_at,
    default_action]`, `healthy=False`, a `gates:` text line and doctor exit 1.
    With the fix the gate carries the two defaults (AC-019). T-20: it carries
    NO `reason_code` -- the machine renders no judgement on a goal-change gate,
    and T-18's invented `goal-md-mtime-moved` was outside the frozen set."""
    project = _project(tmp_path)
    _make_service_running(project)
    st = _state(project)
    assert conductor.tick(project, st) == "ok"  # no change yet
    os.utime(conductor.goal_path(project), None)  # touch => mtime moves
    assert conductor.tick(project, st) == "halted-goal-change"
    gate_files = sorted(conductor.gates_dir(project).glob("gate-*.md"))
    assert len(gate_files) == 1
    gate = gates.parse(gate_files[0])
    assert gate.kind == "goal-change"
    assert gate.default_action == "escalate-to-human"
    assert gate.reason_code is None, gate.reason_code
    assert "reason_code" not in gate_files[0].read_text(encoding="utf-8")
    assert mw_common._gate_missing_fields(gate) == []
    created = datetime.datetime.fromisoformat(gate.created_at)
    expires = datetime.datetime.fromisoformat(gate.expires_at)
    assert expires - created == datetime.timedelta(hours=48)
    report = mw_common.doctor_report(project)
    assert report["gates"]["missing_fields"] == []
    assert report["summary"]["healthy"] is True, report["summary"]["issues"]
    gates_text_lines = [
        line for line in mw_common.format_doctor_text(report).splitlines()
        if line.startswith("gates:")
    ]
    assert not gates_text_lines
    _verify(
        "VC-024",
        site="goal-change",
        missing_fields=len(report["gates"]["missing_fields"]),
        ttl_hours=int((expires - created).total_seconds() // 3600),
        reason_code=gate.reason_code if gate.reason_code is not None else "none",
        healthy=_true(report["summary"]["healthy"]),
        gates_text_line=len(gates_text_lines),
    )


def test_goal_change_defaults_are_written_before_the_created_snapshot(
    tmp_path: pathlib.Path,
) -> None:
    """T-18/T-06: the goal-change stamp must land BEFORE
    `snapshot_gate_created`, or `gate_file.sha256` would not match the final
    file and the gate would read `replay-misbound` on every consumption."""
    project = _project(tmp_path, mode="shadow")
    st = _state(project)
    conductor.tick(project, st)
    os.utime(conductor.goal_path(project), None)
    assert conductor.tick(project, st) == "halted-goal-change"
    gate = gates.parse(next(iter(conductor.gates_dir(project).glob("gate-*.md"))))
    assert gate.kind == "goal-change"
    sidecar = evidence.read_sidecar(conductor.gates_dir(project), gate.id)
    assert sidecar is not None
    created = next(s for s in sidecar["snapshots"] if s["reason"] == "created")
    recorded_sha = created["gate_file"]["sha256"]
    current_sha = hashlib.sha256(gate.path.read_bytes()).hexdigest()
    assert current_sha == recorded_sha
    binding, drift, refusal = conductor.gate_evidence_state(project, gate, st)
    assert refusal != "replay-misbound", refusal
    _verify(
        "VC-045",
        site="goal-change",
        snapshot_sha_matches=_true(current_sha == recorded_sha),
        replay_misbound=int(refusal == "replay-misbound"),
    )


# ── T-20: per-kind `reason_code` scope + write-side closed-set guard ────────


def test_reason_code_requirement_is_per_kind(tmp_path: pathlib.Path) -> None:
    """T-20 / VC-024: after the production stamping path, only `stalled`
    requires `reason_code`. The five human-decision / budget kinds must report
    `missing_fields == []` (each on its own project: one pending gate per
    doctor run, so the healthy assertion is not polluted by siblings)."""
    expected_empty = (
        "stage-confirm",
        "stage-close",
        "goal-change",
        "budget-exhausted",
        "xkey-authorize",
        "stalled",
    )
    for kind in expected_empty:
        project = _project(tmp_path / kind)
        _make_service_running(project)
        st = _state(project)
        machine = (
            {"reason_code": "l2-budget-rejected"} if kind == "stalled" else None
        )
        path = conductor._create_gate(
            project, st, kind, f"q {kind}?", key="k1", stage=1,
            refs=[f"k1:{kind}"], machine_fields=machine,
        )
        gate = gates.parse(path)
        assert mw_common._gate_missing_fields(gate) == [], (kind, gate.path)
        report = mw_common.doctor_report(project)
        assert report["gates"]["missing_fields"] == [], kind
        assert report["summary"]["healthy"] is True, (kind, report["summary"]["issues"])
        assert not [
            line for line in mw_common.format_doctor_text(report).splitlines()
            if line.startswith("gates:")
        ], kind
    _verify(
        "VC-024",
        kinds=len(expected_empty),
        missing_fields=len(report["gates"]["missing_fields"]),
        healthy=_true(report["summary"]["healthy"]),
    )

    # anti-vacuity: `stalled` without a reason_code still reports it.
    project = _project(tmp_path / "stalled-no-code")
    st = _state(project)
    path = conductor._create_gate(
        project, st, "stalled", "review k1?", key="k1", stage=1, refs=["review:k1"],
    )
    assert mw_common._gate_missing_fields(gates.parse(path)) == ["reason_code"]


def test_illegal_reason_code_is_dropped_and_logged(tmp_path: pathlib.Path) -> None:
    """T-20 write-side closed-set guard: a `reason_code` outside the frozen
    `REASON_CODES` set is dropped (never written), the gate is still created
    (no raise), and the caller records one `config` timeline event. A legal
    code on the same path is kept."""
    project = _project(tmp_path)
    st = _state(project)
    path = conductor._create_gate(
        project, st, "stage-close", "close stage 1?", key="k1", stage=1,
        refs=["k1:l3-verdict"], machine_fields={"reason_code": "goal-md-mtime-moved"},
    )
    assert path is not None and path.is_file()  # bad code never blocks creation
    text = path.read_text(encoding="utf-8")
    assert "goal-md-mtime-moved" not in text
    gate = gates.parse(path)
    assert gate.reason_code is None
    assert mw_common._gate_missing_fields(gate) == []  # stage-close needs no code
    dropped_events = [
        e for e in _events(project)
        if e["ev"] == "config" and "dropped out-of-set reason_code" in e["detail"]
    ]
    assert len(dropped_events) == 1, [e["detail"] for e in _events(project)]
    assert dropped_events[0]["key"] == "k1"
    assert dropped_events[0]["stage"] == 1

    # counterfactual: a legal code on the same path survives verbatim.
    legal = conductor._create_gate(
        project, st, "stalled", "why stalled?", key="k2", stage=1,
        refs=["k2:l3-verdict"], machine_fields={"reason_code": "l3-no-verdict"},
    )
    assert gates.parse(legal).reason_code == "l3-no-verdict"
    assert not [
        e for e in _events(project)
        if e["ev"] == "config" and e["key"] == "k2"
        and "dropped out-of-set" in e["detail"]
    ]
    _verify(
        "VC-026",
        illegal="dropped" if gate.reason_code is None else "kept",
        config_event=len(dropped_events),
        legal=gates.parse(legal).reason_code or "dropped",
        gate_created=_true(path is not None and path.is_file()),
    )


# ── T-19: the case-2 producer (decline → pending-review) ─────────────────────


def _done_evidence(project: pathlib.Path, key: str) -> None:
    key_dir = project / ".agenticdoc" / key
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "l3-verdict.txt").write_text("meets\n", encoding="utf-8")
    (key_dir / "l3-report.md").write_text("# report\nmeets\n", encoding="utf-8")
    (key_dir / "achieved.md").write_text(
        "# Achieved\n" + "x" * 300 + "\n", encoding="utf-8"
    )


def _declined_stalled_gate(
    project: pathlib.Path, st: conductor.ConductorState, key: str = "k1"
) -> pathlib.Path | None:
    """A `stalled` gate the fact plane CANNOT answer: its claimed reason_code
    (`l3-below`) never equals the recomputed cause (`advance-class` for a
    loop-less gate), so `auto_decision_for_rule` declines with
    `stalled-reason-drift` — the exact case-2 input."""
    return conductor._create_gate(
        project, st, "stalled", f"review {key}?", key=key, refs=[f"review:{key}"],
        machine_fields={"reason_code": "l3-below"},
    )


def _in_flight_row(project: pathlib.Path, key: str) -> None:
    worker_dir = project / ".agenticdoc" / key / "workers" / f"ap-{key}-l3-a1"
    worker_dir.mkdir(parents=True, exist_ok=True)
    task = worker_dir / "task.md"
    task.write_text("type: reviewer\n", encoding="utf-8")
    mw_common.workers_path(project).parent.mkdir(parents=True, exist_ok=True)
    mw_common.workers_path(project).write_text(
        mw_common.serialize_entry({
            "task_key": f"ap-{key}-l3-a1",
            "status": "running",
            "cli": "pi",
            "provider": "timi",
            "task_path": str(task),
            "dispatched_at": "2026-09-10T00:00:00",
            "updated_at": "2026-09-10T00:00:00",
            "model": "",
            "origin": mw_common.WORKER_ORIGIN_CONDUCTOR,
        }) + "\n",
        encoding="utf-8",
    )


def test_case2_producer_makes_pending_review_reachable_end_to_end(
    tmp_path: pathlib.Path,
) -> None:
    """T-19 core / AC-027: the decline path of the auto-decision pass is the
    production producer of `pending-review`. One fixture, three steps:

    1. a `stalled` gate whose proposition is false + `auto_gate_mode: live` ⇒
       key → `pending-review`, gate still `pending`, and exactly one
       `decision="defer", executed=true` ledger row (T-21: a deferral is a
       disposition — it IS recorded, but it is not an answer: the gate file
       carries no `consumed_at`/`answered_by` and stays sha-unchanged);
    2. once the stage's other key is terminal, a BATCH
       `review-escalated{trigger=closure}` appears and `_stage_closure` refuses;
    3. answering that gate through the review path returns `running` — there is
       no `done` exit."""
    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "stalled", "k2": "done"})
    _index(project, {"k1": "SPEC", "k2": "DONE"})
    _done_evidence(project, "k2")
    st = _state(project)
    gate_path = _declined_stalled_gate(project, st, "k1")
    assert gate_path is not None
    cfg = conductor._load_effective_config(project)
    assert cfg["auto_gate_mode"] == "live"

    # step 1: one auto-decision pass is enough to park the key
    conductor.auto_decide_gates(project, st, cfg)
    assert _key_status(project, "k1") == "pending-review"
    gate = gates.parse(gate_path)
    assert gate.status == "pending"
    assert not gate.consumed_at
    assert not gate.answered_by
    step1_status = _key_status(project, "k1")
    rows = [
        row for row in conductor.auto_decision_rows(project)
        if row.get("gate_id") == gate.id
    ]
    assert len(rows) == 1, "exactly one row per gate per pass (T-21)"
    assert (rows[0]["decision"], rows[0]["executed"], rows[0]["mode"]) == (
        "defer", True, "live"
    )
    assert rows[0]["reason_code"] in conductor.REASON_CODES
    assert (
        rows[0]["gate_file_sha256_before"] == rows[0]["gate_file_sha256_after"]
    ), "a deferral does not touch the gate file"
    assert [e for e in _events(project) if e["ev"] == "gate-auto-decision"]

    # step 2: closure precondition fires the batch escalation; closure refuses
    conductor.orchestrate(project, st)
    batch = [
        e for e in _events(project)
        if e["ev"] == "review-escalated"
        and (e.get("data") or {}).get("trigger") == "closure"
        and e["key"] == "k1"
    ]
    assert len(batch) == 1
    assert batch[0]["stage"] == 1
    assert _gate_kinds(project, "stage-close") == []
    stage_close_at_step2 = len(_gate_kinds(project, "stage-close"))
    assert not (
        project / ".agenticdoc" / "_autopilot" / "stages" / "stage-1-close.md"
    ).is_file()

    # step 3: the review answer returns the key to `running`, never `done`
    _answer(gates.parse(gate_path), "approved")
    conductor.orchestrate(project, st)
    assert _key_status(project, "k1") == "running"
    decided = [e for e in _events(project) if e["ev"] == "review-decided"]
    assert [e["data"]["outcome"] for e in decided] == ["resume"]
    assert _key_status(project, "k1") not in ("done", "closed-legacy")
    # T-22: every count here is measured from the ledger/roadmap, so a later
    # semantics change (T-21: a deferral always writes one row) moves the
    # printed value instead of emitting a stale `auto_decision_rows=0`.
    ledger_rows = conductor.auto_decision_rows(project)
    step3_status = _key_status(project, "k1")
    _verify(
        "T-19",
        step1=step1_status,
        gate=gate.status,
        defer_rows=sum(
            1 for row in ledger_rows if row.get("decision") == "defer"
        ),
        escalate_rows=sum(
            1 for row in ledger_rows if row.get("decision") == "escalate"
        ),
        step2="review-escalated{closure}",
        stage_close=stage_close_at_step2,
        step3=step3_status,
        done_exit=int(step3_status in ("done", "closed-legacy")),
    )


def test_irreversible_and_policy_gate_kinds_are_never_deferred(
    tmp_path: pathlib.Path,
) -> None:
    """Counterfactual (b) judgement: widening `DEFERRABLE_GATE_KINDS` with an
    irreversible kind must turn this red. `stage-confirm`/`stage-close` gate an
    irreversible stage transition and `goal-change`/`xkey-authorize` are policy
    authorisations ⇒ case 3 = immediate human review, never a deferral."""
    assert tuple(conductor.DEFERRABLE_GATE_KINDS) == ("stalled", "budget-exhausted")
    assert set(conductor.DEFERRABLE_GATE_KINDS).isdisjoint(
        {"stage-confirm", "stage-close", "goal-change", "xkey-authorize"}
    )

    # behavioural: `xkey-authorize` is policy AND key-bearing — the shape that
    # would silently become a deferral if the allowlist were widened.
    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "stalled", "k2": "done"})
    _index(project, {"k1": "SPEC", "k2": "DONE"})
    _done_evidence(project, "k2")
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "xkey-authorize", "authorize?", key="k1", refs=["req-1"]
    )
    conductor.auto_decide_gates(
        project, st, conductor._load_effective_config(project)
    )
    assert _key_status(project, "k1") == "stalled"
    assert gates.parse(gate_path).status == "pending"
    # case 3 keeps T-07's decline audit (the escalate row)
    rows = conductor.auto_decision_rows(project)
    assert rows and rows[-1]["decision"] == "escalate"
    irreversible_kinds = {
        "stage-confirm", "stage-close", "goal-change", "xkey-authorize",
    }
    _verify(
        "T-19",
        irreversible_kinds=len(
            irreversible_kinds - set(conductor.DEFERRABLE_GATE_KINDS)
        ),
        xkey_status=_key_status(project, "k1"),
        escalate_record=sum(
            1 for row in rows if row.get("decision") == "escalate"
        ),
    )


def test_off_mode_key_status_is_byte_identical(tmp_path: pathlib.Path) -> None:
    """Counterfactual (c): `auto_gate_mode: off` stays byte-identical to
    today — the SAME declined `stalled` scenario leaves the roadmap untouched
    (the hard user constraint and T-07's gating convention)."""
    project = _project(tmp_path, mode="off")
    _roadmap(project, {"k1": "stalled", "k2": "done"})
    _index(project, {"k1": "SPEC", "k2": "DONE"})
    _done_evidence(project, "k2")
    st = _state(project)
    _declined_stalled_gate(project, st, "k1")
    rm_path = roadmap.roadmap_path(project)
    before = rm_path.read_bytes()
    before_line = next(
        line for line in before.decode("utf-8").splitlines()
        if line.startswith("> key-status:")
    )
    conductor.auto_decide_gates(
        project, st, conductor._load_effective_config(project)
    )
    assert rm_path.read_bytes() == before
    conductor.orchestrate(project, st)
    after = rm_path.read_bytes()
    assert after == before
    assert _key_status(project, "k1") == "stalled"
    assert not [e for e in _events(project) if e["ev"] == "gate-auto-decision"]
    assert not [e for e in _events(project) if e["ev"] == "review-escalated"]
    _verify(
        "T-19",
        off_bytes_identical=_true(after == before),
        key_status_line=before_line.strip(),
    )


def test_decline_skips_a_key_with_an_in_flight_worker_row(
    tmp_path: pathlib.Path,
) -> None:
    """T-19 item 5: a key whose worker is still in flight is NOT parked (its
    case-3 escalation stands) — no duplicate gate and no key-status clobber."""
    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "stalled", "k2": "done"})
    _index(project, {"k1": "SPEC", "k2": "DONE"})
    _done_evidence(project, "k2")
    _in_flight_row(project, "k1")
    st = _state(project)
    _declined_stalled_gate(project, st, "k1")
    conductor.auto_decide_gates(
        project, st, conductor._load_effective_config(project)
    )
    assert _key_status(project, "k1") == "stalled"
    rows = conductor.auto_decision_rows(project)
    assert rows and rows[-1]["decision"] == "escalate"
    _verify(
        "T-19",
        in_flight_skips_deferral=_true(
            not any(row.get("decision") == "defer" for row in rows)
        ),
        key_status=_key_status(project, "k1"),
    )


# ── T-21: the deferral ledger row (shadow + live share one row, T-07 kept) ──


def _sha256_file(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _gate_rows(project: pathlib.Path, gate_id: str) -> list[dict]:
    return [
        row for row in conductor.auto_decision_rows(project)
        if str(row.get("gate_id")) == str(gate_id)
    ]


def test_t21_shadow_deferral_records_one_row_with_zero_state_change(
    tmp_path: pathlib.Path,
) -> None:
    """T-21 / AC-027: `shadow` must show what `live` would DO. A declined
    deferrable gate is recorded as `decision="defer", executed=false`, while
    the gate file AND the roadmap stay byte-identical (T-07's hard contract,
    the basis of the shadow-first rollout decision)."""
    project = _project(tmp_path, mode="shadow")
    _roadmap(project, {"k1": "stalled", "k2": "done"})
    _index(project, {"k1": "SPEC", "k2": "DONE"})
    st = _state(project)
    gate_path = _declined_stalled_gate(project, st, "k1")
    assert gate_path is not None
    rm_path = roadmap.roadmap_path(project)
    gate_sha = _sha256_file(gate_path)
    roadmap_sha = _sha256_file(rm_path)

    conductor.auto_decide_gates(
        project, st, conductor._load_effective_config(project)
    )

    gate = gates.parse(gate_path)
    rows = _gate_rows(project, gate.id)
    assert len(rows) == 1, rows  # exactly one row per gate per pass
    row = rows[0]
    assert (row["decision"], row["executed"], row["mode"]) == (
        "defer", False, "shadow"
    )
    assert row["reason_code"] in conductor.REASON_CODES
    assert row["gate_file_sha256_before"] == row["gate_file_sha256_after"]
    assert _sha256_file(gate_path) == gate_sha, "shadow must not touch the gate"
    assert _sha256_file(rm_path) == roadmap_sha, "shadow must not touch the roadmap"
    assert gate.status == "pending" and not gate.consumed_at and not gate.answered_by
    assert _key_status(project, "k1") == "stalled"
    _verify(
        "T-21",
        shadow_row=(
            f"{row['decision']}/executed={str(row['executed']).lower()}"
            f"/mode={row['mode']}"
        ),
        gate_sha256_unchanged=_true(_sha256_file(gate_path) == gate_sha),
        roadmap_sha256_unchanged=_true(_sha256_file(rm_path) == roadmap_sha),
        decision_rows=len(rows),
    )


def test_t21_live_deferral_records_executed_row_and_no_escalate(
    tmp_path: pathlib.Path,
) -> None:
    """T-21 / AC-027: `live` performs the state change first, then records
    exactly one `decision="defer", executed=true` row — and the escalate row
    for that gate is now gone (mutually exclusive)."""
    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "stalled", "k2": "done"})
    _index(project, {"k1": "SPEC", "k2": "DONE"})
    st = _state(project)
    gate_path = _declined_stalled_gate(project, st, "k1")
    assert gate_path is not None

    conductor.auto_decide_gates(
        project, st, conductor._load_effective_config(project)
    )

    assert _key_status(project, "k1") == "pending-review"
    gate = gates.parse(gate_path)
    rows = _gate_rows(project, gate.id)
    assert len(rows) == 1, rows
    row = rows[0]
    assert (row["decision"], row["executed"], row["mode"]) == (
        "defer", True, "live"
    )
    assert row["reason_code"] in conductor.REASON_CODES
    assert row["gate_file_sha256_before"] == row["gate_file_sha256_after"]
    assert not [r for r in rows if r["decision"] == "escalate"]
    assert gate.status == "pending" and not gate.consumed_at and not gate.answered_by
    _verify(
        "T-21",
        live_row=(
            f"{row['decision']}/executed={str(row['executed']).lower()}"
            f"/mode={row['mode']}"
        ),
        key_status=_key_status(project, "k1"),
        escalate_rows=sum(
            1 for candidate in rows if candidate.get("decision") == "escalate"
        ),
        decision_rows=len(rows),
    )


def test_t21_shadow_deferral_counts_toward_the_shadow_window(
    tmp_path: pathlib.Path,
) -> None:
    """T-21 item 6: the shadow deferral row is a shadow `decide` row, so the
    shadow->live window (>= 20 shadow decisions) counts it exactly once."""
    project = _project(tmp_path, mode="shadow")
    _roadmap(project, {"k1": "stalled", "k2": "done"})
    _index(project, {"k1": "SPEC", "k2": "DONE"})
    st = _state(project)
    _declined_stalled_gate(project, st, "k1")
    before = conductor.shadow_prerequisites(project)
    conductor.auto_decide_gates(
        project, st, conductor._load_effective_config(project)
    )
    after = conductor.shadow_prerequisites(project)
    assert after["decisions"] == before["decisions"] + 1 == 1
    # counterexample witness: the row carries prop_ok=False, so the rule is
    # eligible after a single deferral (the window needs >= 1 falsifier).
    assert before["decisions"] == 0
    _verify(
        "T-21", shadow_decisions_before=before["decisions"],
        shadow_decisions_after=after["decisions"],
        nights_before=before["nights"], nights_after=after["nights"],
    )


def test_t21_non_deferrable_stage_close_keeps_case_3_escalate(
    tmp_path: pathlib.Path,
) -> None:
    """T-21 judgement 4: `stage-close` gates an irreversible transition, so it
    still routes to case 3 — the existing `escalate` row, and no `defer` row
    exists anywhere in the ledger."""
    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "running", "k2": "done"})
    _index(project, {"k1": "EXECUTE", "k2": "DONE"})
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "stage-close", "close stage 1?", key="k1", stage=1,
        refs=["k1:l3-verdict"],
    )
    assert gate_path is not None

    conductor.auto_decide_gates(
        project, st, conductor._load_effective_config(project)
    )

    assert _key_status(project, "k1") == "running"  # no state change
    gate = gates.parse(gate_path)
    rows = _gate_rows(project, gate.id)
    assert len(rows) == 1, rows
    assert rows[0]["decision"] == "escalate"
    assert rows[0]["reason_code"] in conductor.REASON_CODES
    assert not [
        row for row in conductor.auto_decision_rows(project)
        if row.get("decision") == "defer"
    ]
    _verify(
        "T-21",
        stage_close=rows[0]["decision"],
        defer_rows=sum(
            1 for candidate in conductor.auto_decision_rows(project)
            if candidate.get("decision") == "defer"
        ),
        decision_rows=len(rows),
    )
