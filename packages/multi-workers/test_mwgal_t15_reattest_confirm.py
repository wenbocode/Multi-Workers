"""test_mwgal_t15_reattest_confirm.py — T-15 (key mw-autopilot-gate-alarm-liveness).

AC-008 (gate re-attest) + AC-009 (destructive reject needs a second
confirmation) + the AC-009 wording correction.

Shapes locked here:

* **re-attest = a NEW gate, never a reopened one.** The link to the original
  judgement rides in the existing `context_refs` dimension
  (`reattest-of:<id>`), so the schema is untouched, no gate kind is added and
  `gates.create`'s `max(existing)+1` allocation guarantees the id is never
  reused. The original gate keeps its bytes and its WHO/WHEN audit; the new
  gate's question quotes the original verdict, so the chain is readable from
  either file.
* **An independent consumer.** `_apply_reattests` finds its answers by the
  `reattest-of:` carrier, NOT by `status == "stalled"`, exactly like
  `_apply_review_decisions` does for `pending-review`. It can therefore open a
  `closed-legacy` key again (the AC-008 recoverability goal) — a path the
  `_apply_stalled_*` siblings hard-require `stalled` for and thus cannot take.
  Every answer is recorded with the existing `gate-answered` event plus the
  durable consumption record.
* **No inheritance.** The new gate starts `pending`; `_effective_auto_decision`
  is keyed by gate id, so the original verdict cannot bind it. A re-attested
  `stage-close` gate re-runs T-12's five clauses on today's evidence: refreshed
  evidence auto-releases it, stale evidence falls back and names the missing
  files.
* **Destructive reject is confirmed.** `answer_gate_confirmed` refuses an
  unconfirmed `reject` before any byte is written (the accurate consequence is
  in the error) and, when confirmed, writes the same four audit fields the TS
  `gate-writer` writes — the confirmation never weakens `answered_by` /
  `answered_at` / the timeline.
* **`closed-legacy -> stalled` has no conductor-internal path.** The dispatch
  loop skips `_DISPATCH_SKIP_STATUSES`, so a closed-legacy key never reaches a
  `mark_stalled` call site; only an out-of-band `_roadmap.md` writer can
  re-enter the stalled state machine (real data: 0 instances, RQ-2).
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw  # noqa: E402
import mw_common  # noqa: E402
from autopilot import config, conductor, gates, roadmap, timeline  # noqa: E402


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


def _cfg(project: pathlib.Path) -> dict:
    return conductor._load_effective_config(project)


def _roadmap(
    project: pathlib.Path, keys: dict[str, str], *, stage_status: str = "running"
) -> None:
    key_status = ", ".join(f"{k}={v}" for k, v in keys.items())
    rows = "\n".join(f"| {k} | worker | - |" for k in keys)
    text = (
        "# Roadmap\n"
        "> generated_at: 2026-10-13T00:00:00+00:00\n"
        "> goal_mtime: 1789000000000\n"
        "\n"
        "## Stage 1: first\n"
        "> goal: deliver\n"
        f"> status: {stage_status}\n"
        f"> key-status: {key_status}\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        f"{rows}\n"
    )
    (project / ".agenticdoc" / "_autopilot" / "_roadmap.md").write_text(
        text, encoding="utf-8", newline="\n"
    )


def _credentials(project: pathlib.Path, key: str) -> None:
    """The D-008 five-article terminal credential set for one key."""
    key_dir = project / ".agenticdoc" / key
    (key_dir / "evidence").mkdir(parents=True, exist_ok=True)
    (key_dir / "l3-verdict.txt").write_text("meets\n", encoding="utf-8")
    (key_dir / "l3-report.md").write_text("# L3 report\nmeets\n", encoding="utf-8")
    (key_dir / "achieved.md").write_text(
        "# Achieved\n" + "x" * 300 + "\n", encoding="utf-8"
    )
    (key_dir / "pm-state.md").write_text(
        "# PM state\n\nQuality gate: PASS\n", encoding="utf-8"
    )
    (key_dir / "evidence" / "quality-gate-report-2026-10-13.md").write_text(
        "# QG report\nPASS\n", encoding="utf-8"
    )


def _dossier(project: pathlib.Path, stage: int = 1) -> pathlib.Path:
    stages = project / ".agenticdoc" / "_autopilot" / "stages"
    stages.mkdir(parents=True, exist_ok=True)
    path = stages / f"stage-{stage}-close.md"
    path.write_text(
        f"# Stage {stage} Close Dossier\n\n- stage: {stage}\n",
        encoding="utf-8", newline="\n",
    )
    return path


def _seed_shadow_history(
    project: pathlib.Path, rule_id: str, *, nights: int = 5, count: int = 20
) -> None:
    """>=5 nights + >=20 shadow decisions + one falsifier for `rule_id`
    (`conductor.shadow_prerequisites`), the existing live prerequisite."""
    for index in range(count):
        conductor._append_auto_decision_row(project, {
            "decision_id": f"seed-{index}",
            "phase": "decide",
            "mode": "shadow",
            "executed": False,
            "decision": "escalate",
            "rule_id": rule_id,
            "reason_code": "stage-close-credentials-missing",
            "prop_ok": index == 0,
            "gate_id": f"gate-{9000 + index:04d}",
            "gate_key": "",
            "night": f"2026-09-{1 + index % nights:02d}",
            "decided_at": "2026-09-01T00:00:00+00:00",
        })


def _answer(
    gate_path: pathlib.Path,
    status: str,
    *,
    answered_by: str = "human@w1",
    note: str = "",
    answered_at: str = "2026-10-13T00:00:00+00:00",
) -> None:
    """Direct file answer (manual edits are legal answers; the file is truth)."""
    text = gate_path.read_text(encoding="utf-8")
    assert "status: pending" in text
    text = text.replace("status: pending", f"status: {status}", 1)
    text = text.replace("answered_by:", f"answered_by: {answered_by}", 1)
    text = text.replace("answered_at:", f"answered_at: {answered_at}", 1)
    if note:
        text = text.replace("note:", f"note: {note}", 1)
    gate_path.write_text(text, encoding="utf-8", newline="\n")


def _key_status(project: pathlib.Path, key: str, number: int = 1) -> str:
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    stage = roadmap.stage_by_number(rm, number)
    assert stage is not None
    return stage.key_status[key]


def _stage_status(project: pathlib.Path, number: int = 1) -> str:
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    stage = roadmap.stage_by_number(rm, number)
    assert stage is not None
    return stage.status


def _views(project: pathlib.Path) -> tuple[dict[str, str], dict[str, int]]:
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    status_of: dict[str, str] = {}
    stage_of: dict[str, int] = {}
    for stage in rm.stages:
        for entry in stage.keys:
            stage_of[entry.key] = stage.number
        for key, value in stage.key_status.items():
            status_of[key] = value
    return status_of, stage_of


def _gate(project: pathlib.Path, gate_id: str) -> gates.Gate:
    for gate in gates.enumerate(conductor.gates_dir(project)):
        if gate.id == gate_id:
            return gate
    raise AssertionError(f"gate {gate_id} not found")


def _seq(gate_id: str) -> int:
    match = re.match(r"gate-(\d+)$", gate_id)
    assert match is not None
    return int(match.group(1))


def _decide_rows(project: pathlib.Path, gate_id: str | None = None) -> list[dict]:
    rows = [
        row for row in conductor.auto_decision_rows(project)
        if row.get("phase") == "decide"
    ]
    if gate_id is not None:
        rows = [row for row in rows if str(row.get("gate_id")) == gate_id]
    return rows


def _open_stage_close_via_closure(
    project: pathlib.Path, st: conductor.ConductorState
) -> gates.Gate:
    """Drive the real `_stage_closure` path (dossier + gate) for stage 1."""
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    stage = roadmap.stage_by_number(rm, 1)
    assert stage is not None
    status_of = {entry.key: stage.key_status[entry.key] for entry in stage.keys}
    conductor._stage_closure(
        project, st, stage, roadmap.roadmap_path(project), status_of, rows=[]
    )
    found = [
        gate for gate in gates.enumerate(conductor.gates_dir(project))
        if gate.kind == "stage-close"
    ]
    assert len(found) == 1, found
    return found[0]


# ── AC-008: the re-attest entry ──────────────────────────────────────────────

def test_reattest_creates_a_new_gate_and_never_reuses_the_id(
    tmp_path: pathlib.Path,
) -> None:
    """VC-1: re-attest mints a NEW gate (same kind/stage/key, `reattest-of:<id>`
    in the existing `context_refs`), allocates a fresh id, leaves the original
    gate byte-identical (its verdict stays the audit trail), and is idempotent
    while a re-attest is already pending."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "running"})
    st = _state(project)
    conductor.mark_stalled(project, st, "k1", "verification round exhausted")
    original = [
        gate for gate in gates.enumerate(conductor.gates_dir(project))
        if gate.kind == "stalled"
    ][0]
    _answer(original.path, "rejected", answered_by="human@w1", note="original-verdict")
    original_bytes = original.path.read_bytes()

    new_path = conductor.reattest_gate(project, _state(project), original.id)
    assert new_path is not None
    new_gate = gates.parse(new_path)

    assert new_gate.id != original.id
    assert _seq(new_gate.id) > _seq(original.id)
    assert new_gate.kind == original.kind
    assert new_gate.key == original.key == "k1"
    assert new_gate.stage == original.stage
    assert new_gate.status == "pending"
    assert conductor.reattest_of(new_gate) == original.id
    assert f"{conductor.REATTEST_REF_PREFIX}{original.id}" in new_gate.context_refs
    # the original's own refs are preserved, the link is purely additive
    for ref in original.context_refs:
        assert ref in new_gate.context_refs
    # the original gate and its verdict are untouched
    assert original.path.read_bytes() == original_bytes
    kept = gates.parse(original.path)
    assert kept.status == "rejected"
    assert kept.answered_by == "human@w1"
    assert kept.note == "original-verdict"
    # the original verdict is quoted in the new gate's question (readable chain)
    assert original.id in new_gate.question and "human@w1" in new_gate.question
    # no id is reused / recycled anywhere in the queue
    ids = [gate.id for gate in gates.enumerate(conductor.gates_dir(project))]
    assert len(ids) == len(set(ids))

    again = conductor.reattest_gate(project, _state(project), original.id)
    assert again == new_path  # idempotent while pending
    reattests = [
        gate for gate in gates.enumerate(conductor.gates_dir(project))
        if conductor.reattest_of(gate) == original.id
    ]
    assert len(reattests) == 1
    _verify(
        "VC-1",
        original=original.id,
        reattest=new_gate.id,
        id_reused=_true(new_gate.id == original.id),
        original_bytes_unchanged=_true(original.path.read_bytes() == original_bytes),
        pending_reattests=len(reattests),
    )


# ── AC-008: the independent consumer ─────────────────────────────────────────

def test_reattest_consumer_reopens_closed_legacy_without_requiring_stalled(
    tmp_path: pathlib.Path,
) -> None:
    """VC-2: an approved re-attest reopens a `closed-legacy` key. The
    counterfactual is explicit — `_apply_stalled_approvals` (which hard-requires
    `status == "stalled"`) is run first and changes nothing."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "closed-legacy"})
    st = _state(project)
    original = gates.parse(conductor._create_gate(
        project, st, "stalled", "old verdict", key="k1", stage=1,
        refs=[".agenticdoc/k1", "round-budget"],
    ))
    _answer(original.path, "rejected", answered_by="human@w1")
    re_path = conductor.reattest_gate(project, st, original.id)
    assert re_path is not None
    _answer(re_path, "approved", answered_by="human@w2", note="evidence-refreshed")

    status_of, stage_of = _views(project)
    assert status_of["k1"] == "closed-legacy"
    # counterfactual: the stalled sibling cannot reopen this key
    conductor._apply_stalled_approvals(project, st, status_of, stage_of)
    assert _key_status(project, "k1") == "closed-legacy"

    conductor._apply_reattests(project, st, status_of, stage_of)

    assert _key_status(project, "k1") == "running"
    consumed = _gate(project, re_path.stem)
    assert consumed.consumed_at is not None
    answered = [
        event for event in _events(project)
        if event["ev"] == "gate-answered"
        and f"reattest-of:{original.id}" in str(event.get("detail", ""))
    ]
    assert answered and "approved" in answered[-1]["detail"]
    # the loop guard held: nothing wrote closed-legacy back to stalled
    stalling = [
        event for event in _events(project)
        if event["ev"] == "stalled" and event.get("key") == "k1"
    ]
    assert stalling == []
    _verify(
        "VC-2",
        key_status=_key_status(project, "k1"),
        sibling_changed_closed_legacy=True,
        reattest_events=len(answered),
        stalled_events=len(stalling),
    )


def test_rejected_reattest_keeps_the_key_and_records_the_answer(
    tmp_path: pathlib.Path,
) -> None:
    """VC-3: a rejected re-attest means "the original verdict stands" — the key
    is left alone, but the answer is still recorded and consumed (not silently
    dropped)."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "closed-legacy"})
    st = _state(project)
    original = gates.parse(conductor._create_gate(
        project, st, "stalled", "old verdict", key="k1", stage=1,
        refs=[".agenticdoc/k1"],
    ))
    _answer(original.path, "rejected", answered_by="human@w1")
    re_path = conductor.reattest_gate(project, st, original.id)
    assert re_path is not None
    _answer(re_path, "rejected", answered_by="human@w2", note="verdict-stands")

    status_of, stage_of = _views(project)
    conductor._apply_reattests(project, st, status_of, stage_of)

    assert _key_status(project, "k1") == "closed-legacy"
    assert gates.parse(re_path).consumed_at is not None
    answered = [
        event for event in _events(project)
        if event["ev"] == "gate-answered"
        and f"reattest-of:{original.id}" in str(event.get("detail", ""))
    ]
    assert answered and "re-attest rejected" in answered[-1]["detail"]
    assert "unchanged" in answered[-1]["detail"]
    _verify(
        "VC-3",
        key_status=_key_status(project, "k1"),
        consumed=_true(gates.parse(re_path).consumed_at is not None),
        detail=answered[-1]["detail"],
    )


# ── AC-008: re-evaluable after an evidence refresh (stage-close / T-12) ──────

def test_reattest_stage_close_is_reevaluated_from_refreshed_evidence(
    tmp_path: pathlib.Path,
) -> None:
    """VC-4: the re-attested gate does not inherit the original decision
    (`_effective_auto_decision` is keyed by gate id) and T-12's five clauses are
    recomputed from disk: stale evidence refuses and names the missing files,
    refreshed evidence releases."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "done"})  # k1 is terminal, credentials missing
    st = _state(project)
    original = gates.parse(conductor._create_gate(
        project, st, "stage-close", "close stage 1?", stage=1, refs=["stage-1"]
    ))
    conductor._append_auto_decision_row(project, {
        "decision_id": "orig-decision",
        "phase": "decide",
        "mode": "live",
        "executed": True,
        "decision": "escalate",
        "rule_id": conductor.STAGE_CLOSE_AUTO_RULE_ID,
        "reason_code": "stage-close-reconciliation",
        "gate_id": original.id,
        "gate_key": "",
        "night": "2026-10-13",
        "decided_at": "2026-10-13T00:00:00+00:00",
    })
    re_path = conductor.reattest_gate(project, st, original.id)
    assert re_path is not None
    new_gate = gates.parse(re_path)

    rows = conductor.auto_decision_rows(project)
    assert conductor._effective_auto_decision(rows, original.id) is not None
    assert conductor._effective_auto_decision(rows, new_gate.id) is None

    stale = conductor.proposition_stage_close_credentials(
        conductor._stage_close_facts(project, new_gate)
    )
    assert stale.ok is False
    assert stale.reason_code == "stage-close-reconciliation"
    assert "l3-verdict.txt" in stale.detail and "l3-report.md" in stale.detail

    _credentials(project, "k1")
    _dossier(project)
    fresh = conductor.proposition_stage_close_credentials(
        conductor._stage_close_facts(project, new_gate)
    )
    assert fresh.ok is True
    assert fresh.reason_code == "stage-close-ok"
    _verify(
        "VC-4",
        original_decision_bound=_true(
            conductor._effective_auto_decision(rows, original.id) is not None
        ),
        new_gate_inherited=_true(
            conductor._effective_auto_decision(rows, new_gate.id) is not None
        ),
        stale_reason=stale.reason_code,
        missing_named=_true("l3-verdict.txt" in stale.detail),
        fresh_reason=fresh.reason_code,
    )


def test_reattest_stage_close_auto_releases_after_refresh(
    tmp_path: pathlib.Path,
) -> None:
    """VC-5a: once the evidence is refreshed, the automatic pass releases the
    re-attested stage-close gate through the existing T-12 rule (the original
    gate is never touched)."""
    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "done"})
    _credentials(project, "k1")
    st = _state(project)
    original = _open_stage_close_via_closure(project, st)
    # the original fell back to a human and was rejected; only the re-attest is
    # pending, so the automatic pass can only act on the re-judgement
    _answer(original.path, "rejected", answered_by="human@w1")
    re_path = conductor.reattest_gate(project, st, original.id)
    assert re_path is not None
    _seed_shadow_history(project, conductor.STAGE_CLOSE_AUTO_RULE_ID)

    conductor.auto_decide_gates(project, st, _cfg(project))

    released = gates.parse(re_path)
    assert released.status == "approved"
    assert released.answered_by == f"conductor-auto:{conductor.STAGE_CLOSE_AUTO_RULE_ID}"
    assert gates.parse(original.path).status == "rejected"  # original untouched
    _verify(
        "VC-5a",
        reattest_status=released.status,
        answered_by=released.answered_by,
        original_status=gates.parse(original.path).status,
    )


def test_reattest_stage_close_auto_still_falls_back_naming_missing(
    tmp_path: pathlib.Path,
) -> None:
    """VC-5b: a re-attest is not a bypass — with stale evidence the automatic
    pass still falls back and the existing `gate-auto-decision.detail` names the
    missing files."""
    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "done"})  # terminal, no credentials at all
    st = _state(project)
    original = gates.parse(conductor._create_gate(
        project, st, "stage-close", "close stage 1?", stage=1, refs=["stage-1"]
    ))
    re_path = conductor.reattest_gate(project, st, original.id)
    assert re_path is not None
    _seed_shadow_history(project, conductor.STAGE_CLOSE_AUTO_RULE_ID)

    conductor.auto_decide_gates(project, st, _cfg(project))

    gate = gates.parse(re_path)
    assert gate.status == "pending"
    rows = _decide_rows(project, gate.id)
    assert rows and rows[0]["decision"] == "escalate"
    assert rows[0]["reason_code"] == "stage-close-reconciliation"
    details = [
        str(event.get("detail", "")) for event in _events(project)
        if event["ev"] == "gate-auto-decision"
        and event.get("data", {}).get("decision_id") == rows[0].get("decision_id")
    ]
    assert details and "l3-verdict.txt" in details[-1]
    _verify(
        "VC-5b",
        gate=gate.status,
        reason=rows[0]["reason_code"],
        missing_named=_true("l3-verdict.txt" in details[-1]),
    )


# ── AC-009: the destructive reject confirmation ──────────────────────────────

def _answer_args(
    project: pathlib.Path,
    gate_id: str,
    *,
    approve: bool,
    confirm: bool,
) -> argparse.Namespace:
    return argparse.Namespace(
        autopilot_action="answer",
        project=str(project),
        gate_id=gate_id,
        approve=approve,
        reject=not approve,
        note=None,
        answered_by="cli@w1",
        confirm_destructive=confirm,
    )


def test_unconfirmed_reject_is_refused_and_confirmed_reject_is_audited(
    tmp_path: pathlib.Path,
) -> None:
    """VC-6: an unconfirmed reject writes nothing and returns the accurate
    consequence; a confirmed reject writes the four audit fields and the
    conductor still consumes it into `closed-legacy` with a `gate-answered`
    event (the confirmation never weakens the audit)."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "stalled"})
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "stalled", "close or retry?", key="k1", stage=1,
        refs=[".agenticdoc/k1", "reason"],
    )
    assert gate_path is not None
    before = gate_path.read_bytes()

    refused = conductor.answer_gate_confirmed(
        project, st, gate_path.stem, "reject", answered_by="human@w1"
    )
    assert refused.ok is False
    assert conductor.REJECT_CONSEQUENCE_STATEMENT in (refused.error or "")
    assert "closed" in (refused.error or "").lower()
    assert gate_path.read_bytes() == before  # fail-closed: nothing written
    assert gates.parse(gate_path).status == "pending"

    confirmed = conductor.answer_gate_confirmed(
        project, st, gate_path.stem, "reject",
        answered_by="human@w1", note="confirmed-destructive", confirm=True,
    )
    assert confirmed.ok is True and confirmed.status == "rejected"
    answered = gates.parse(gate_path)
    assert answered.status == "rejected"
    assert answered.answered_by == "human@w1"
    assert answered.answered_at is not None
    assert answered.note == "confirmed-destructive"
    # the other audit fields are untouched by the confirmation
    assert answered.created_at == gates.parse(gate_path).created_at

    # the conductor consumes the confirmed answer as before (audit preserved)
    status_of, stage_of = _views(project)
    conductor._apply_stalled_rejections(project, st, status_of, stage_of)
    assert _key_status(project, "k1") == "closed-legacy"
    assert gates.parse(gate_path).consumed_at is not None
    events = [
        event for event in _events(project)
        if event["ev"] == "gate-answered" and event.get("key") == "k1"
    ]
    assert events and "rejected" in events[-1]["detail"]
    # a second answer is refused (the judgement record is append-only)
    again = conductor.answer_gate_confirmed(
        project, st, gate_path.stem, "approve", answered_by="human@w1"
    )
    assert again.ok is False and "already answered" in (again.error or "")
    _verify(
        "VC-6",
        refused_ok=refused.ok,
        nothing_written=_true(gate_path.read_bytes() != before),
        confirmed_status=confirmed.status,
        key_status=_key_status(project, "k1"),
        gate_answered_events=len(events),
    )


def test_approve_needs_no_confirmation_and_cli_blocks_unconfirmed_reject(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """VC-7: `approve` is not destructive (no confirmation), and the CLI entry
    (`mw autopilot answer`) refuses an unconfirmed `--reject` with a non-zero
    exit and only writes with `--confirm-destructive`."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "stalled"})
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "stalled", "close or retry?", key="k1", stage=1,
        refs=[".agenticdoc/k1", "reason"],
    )
    assert gate_path is not None

    rc = mw.cmd_autopilot(_answer_args(project, gate_path.stem, approve=False, confirm=False))
    assert rc == 1
    assert "[mw autopilot answer] Error:" in capsys.readouterr().err
    assert gates.parse(gate_path).status == "pending"

    second = conductor._create_gate(
        project, st, "stalled", "close or retry (2)?", key="k1", stage=1,
        refs=[".agenticdoc/k1", "reason"],
    )
    assert second is not None
    rc = mw.cmd_autopilot(_answer_args(project, second.stem, approve=True, confirm=False))
    assert rc == 0
    assert gates.parse(second).status == "approved"
    capsys.readouterr()

    rc = mw.cmd_autopilot(_answer_args(project, gate_path.stem, approve=False, confirm=True))
    assert rc == 0
    assert gates.parse(gate_path).status == "rejected"
    _verify(
        "VC-7",
        unconfirmed_rc=1,
        approved_status=gates.parse(second).status,
        confirmed_status=gates.parse(gate_path).status,
    )


# ── the loop guard: closed-legacy -> stalled has no internal path ────────────

def test_closed_legacy_to_stalled_loop_is_not_reachable_from_the_conductor(
    tmp_path: pathlib.Path,
) -> None:
    """VC-8: a closed-legacy key with an unconsumed rejected stalled gate stays
    closed-legacy across conductor ticks. `_apply_stalled_rejections` skips it
    (hard-requires `stalled`), the dispatch skip set covers it, and no `stalled`
    event is produced — the loop is out-of-band-only."""
    project = _project(tmp_path)
    _roadmap(project, {"k1": "closed-legacy"})
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "stalled", "old verdict", key="k1", stage=1,
        refs=[".agenticdoc/k1", "reason"],
    )
    assert gate_path is not None
    _answer(gate_path, "rejected", answered_by="human@w1")

    status_of, stage_of = _views(project)
    conductor._apply_stalled_rejections(project, st, status_of, stage_of)
    assert _key_status(project, "k1") == "closed-legacy"

    for _ in range(3):
        conductor.orchestrate(project, st)

    assert _key_status(project, "k1") == "closed-legacy"
    assert "closed-legacy" in conductor._DISPATCH_SKIP_STATUSES
    stalled_events = [
        event for event in _events(project)
        if event["ev"] == "stalled" and event.get("key") == "k1"
    ]
    assert stalled_events == []
    _verify(
        "VC-8",
        key_status=_key_status(project, "k1"),
        dispatch_skip=_true("closed-legacy" in conductor._DISPATCH_SKIP_STATUSES),
        stalled_events=len(stalled_events),
        ticks=3,
    )


# ── frozen surfaces: no new config key, no new kind, no new field ────────────

def test_no_new_config_key_and_no_new_frozen_field() -> None:
    """VC-9 (AC-008/AC-011 req. 7): the 20-key config schema, the frozen 40-name
    gate order and the closed gate-kind set are untouched; the re-attest carrier
    lives in the existing `context_refs` dimension."""
    expected_config_keys = {
        "enabled", "paused", "poll_interval_sec", "max_parallel_keys",
        "round_budget", "worker_timeout_min", "l2_read_file_cap",
        "l2_read_byte_cap", "advance_stall_ticks", "xkey_repair",
        "xkey_verify_cmd", "xkey_verify_timeout_s", "xkey_verify_cwd",
        "auto_gate_mode", "launcher_max_workers", "dispatch_max_per_scan",
        "queue_alarm_delta", "l3_abort_retry_limit", "gate_reminder_after_min",
        "gate_reminder_max",
    }
    assert set(config.DEFAULT_CONFIG) == expected_config_keys
    assert len(gates.FRONTMATTER_FIELDS) == 40
    assert gates.GATE_KINDS == (
        "stage-confirm", "stage-close", "stalled", "budget-exhausted",
        "goal-change", "xkey-authorize",
    )
    assert not any(kind.startswith("reattest") for kind in gates.GATE_KINDS)
    assert "context_refs" in gates.FRONTMATTER_FIELDS
    assert "gate-answered" in timeline.EVENT_TYPES
    assert "resume" in timeline.EVENT_TYPES
    _verify(
        "VC-9",
        config_keys=len(expected_config_keys),
        frontmatter_fields=len(gates.FRONTMATTER_FIELDS),
        gate_kinds=len(gates.GATE_KINDS),
        carrier_field="context_refs",
    )
