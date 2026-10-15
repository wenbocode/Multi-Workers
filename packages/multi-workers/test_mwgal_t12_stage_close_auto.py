"""test_mwgal_t12_stage_close_auto.py — T-12 (key mw-autopilot-gate-alarm-liveness).

`stage-close` is the **main gate**: an unanswered one keeps its stage
`running` forever, `_stage_activation` returns False and the whole project
dispatches nothing. It is also the only gate kind that is both
"deterministically machine-collectable evidence" and "not policy", so T-12
(AC-015 / D-011 中档 / D-014①) gives it an automatic release through the
existing automatic-decision engine — with **zero new fields, event names or
config keys**:

* `proposition_stage_close_credentials` — five clauses, every one recomputed
  from disk by `_stage_close_facts` (`_stage_closure` creates stage-close
  gates with no `machine_fields`, so reading the gate's own v2 fields could
  only ever refuse): stage resolvable on the roadmap, every key terminal, no
  in-flight worker row, no evidence-reconciliation dispute, dossier on disk,
  every key's terminal credentials present;
* the rule `stage-close-credentials` (`auto_action="approve"`) answers through
  the existing `answer_gate_auto`, so `answered_by="conductor-auto:<rule_id>"`
  plus the already-registered `answer_source` / `auto_policy_id` fields carry
  the trace, and the append-only ledger receives one `phase:"decide"` row;
* every refusal (a missing clause, an unreadable fact) degrades to
  `escalate` + one existing `gate-auto-decision` event whose existing `detail`
  names the missing items — a fallback is visible, both in the ledger row's
  `evidence` array (missing pointers carry `sha256: None`) and on the event;
* the existing safety rails stay intact: the shadow-to-live prerequisite, the
  `not-bound`/`replay-misbound` evidence binding, the night/key quotas and the
  persisted breaker are NOT relaxed (`P-03`);
* `stage-confirm` stays a guard (`D-014②`) and the 48h deferred-review fallback
  stays escalation-only — it never closes a stage and never rewrites a
  key-status.

Non-vacuous counterfactuals are inline (each asserts the opposite of the
regression it guards).
"""
from __future__ import annotations

import datetime
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

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


def _roadmap(project: pathlib.Path, keys: dict[str, str], *, stage_status: str = "running") -> None:
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


def _credentials(project: pathlib.Path, key: str, *, verdict: str | None = "meets") -> None:
    """The D-008 five-article terminal credential set for one key."""
    key_dir = project / ".agenticdoc" / key
    (key_dir / "evidence").mkdir(parents=True, exist_ok=True)
    if verdict is not None:
        (key_dir / "l3-verdict.txt").write_text(verdict + "\n", encoding="utf-8")
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


def _gate_kinds(project: pathlib.Path, kind: str) -> list[gates.Gate]:
    return [
        gate for gate in gates.enumerate(conductor.gates_dir(project))
        if gate.kind == kind
    ]


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


def _decide_rows(project: pathlib.Path, gate_id: str | None = None) -> list[dict]:
    rows = [
        row for row in conductor.auto_decision_rows(project)
        if row.get("phase") == "decide"
    ]
    if gate_id is not None:
        rows = [row for row in rows if str(row.get("gate_id")) == gate_id]
    return rows


def _open_stage_close_via_closure(project: pathlib.Path, st: conductor.ConductorState) -> gates.Gate:
    """Drive the real `_stage_closure` path (dossier + gate) for stage 1."""
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    stage = roadmap.stage_by_number(rm, 1)
    assert stage is not None
    status_of = {entry.key: stage.key_status[entry.key] for entry in stage.keys}
    conductor._stage_closure(
        project, st, stage, roadmap.roadmap_path(project), status_of, rows=[]
    )
    found = _gate_kinds(project, "stage-close")
    assert len(found) == 1, found
    return found[0]


def _good_facts(**overrides: object) -> dict:
    facts: dict = {
        "stage": 1,
        "stage_known": True,
        "keys": ["k1"],
        "keys_terminal": True,
        "not_terminal_keys": [],
        "in_flight_keys": [],
        "reconciliation_blocking": False,
        "reconciliation_keys": [],
        "dossier_written": True,
        "dossier": "/p/.agenticdoc/_autopilot/stages/stage-1-close.md",
        "missing_credentials": {},
    }
    facts.update(overrides)
    return facts


# ── the release proposition: five clauses, all falsifiable ───────────────────

def test_every_release_clause_refuses_on_its_own() -> None:
    """VC-1: the positive fixture passes and EACH clause, flipped, turns the
    proposition false with its own closed-set reason code. A predicate that
    cannot be shown false carries zero information (D1 F2)."""
    assert conductor.proposition_stage_close_credentials(_good_facts()).ok is True
    cases = [
        ({"stage_known": False}, "stage-close-stage-unknown"),
        ({"keys_terminal": False, "not_terminal_keys": ["k1"]}, "stage-close-not-terminal"),
        ({"in_flight_keys": ["k1"]}, "stage-close-in-flight"),
        (
            {
                "reconciliation_blocking": True,
                "reconciliation_keys": ["k1"],
                "missing_credentials": {"k1": ["l3-verdict.txt=meets"]},
            },
            "stage-close-reconciliation",
        ),
        ({"dossier_written": False}, "stage-close-dossier-missing"),
        (
            {"missing_credentials": {"k1": ["l3-verdict.txt=meets", "l3-report.md"]}},
            "stage-close-credentials-missing",
        ),
    ]
    for override, expected in cases:
        result = conductor.proposition_stage_close_credentials(_good_facts(**override))
        assert result.ok is False, override
        assert result.reason_code == expected, (override, result.reason_code)
        assert result.reason_code in conductor.REASON_CODES, expected

    # the registered rule is falsifiable and its own witness falsifies it
    rule = conductor.AUTO_RULE_BY_KIND["stage-close"]
    assert rule.auto_action == "approve"
    assert conductor.rule_falsifiable(rule)[0] is True
    assert rule.proposition(rule.counterexample()).ok is False
    _verify(
        "VC-1",
        clauses=len(cases),
        positive=_true(
            conductor.proposition_stage_close_credentials(_good_facts()).ok is True
        ),
        rule_falsifiable=_true(conductor.rule_falsifiable(rule)[0]),
    )


def test_facts_are_recomputed_from_disk_not_read_back_from_the_gate(
    tmp_path: pathlib.Path,
) -> None:
    """The T-08 finding: every existing stage-close gate carries
    `verdicts_final: None`. The fact plane must therefore read the roadmap /
    keys / workers file, never the gate's own v2 fields."""
    project = _project(tmp_path, mode="off")
    _roadmap(project, {"k1": "done", "k2": "running"})
    _credentials(project, "k1")
    _dossier(project)
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "stage-close", "close stage 1?", stage=1, refs=["stage-1"]
    )
    gate = gates.parse(gate_path)
    assert gate.verdicts_final is None and gate.open_items is None
    facts = conductor._stage_close_facts(project, gate)
    assert facts["stage_known"] is True
    assert facts["keys"] == ["k1", "k2"]
    assert facts["keys_terminal"] is False
    assert facts["not_terminal_keys"] == ["k2"]
    assert conductor.proposition_stage_close_credentials(facts).reason_code == (
        "stage-close-not-terminal"
    )

    # an unresolvable stage, an empty stage and a stage-less gate all refuse
    unknown = conductor._stage_close_facts(project, gates.parse(
        conductor._create_gate(
            project, st, "stage-close", "close stage 9?", stage=9, refs=["stage-9"]
        )
    ))
    assert unknown["stage_known"] is False
    assert conductor.proposition_stage_close_credentials(unknown).reason_code == (
        "stage-close-stage-unknown"
    )
    stageless = conductor._stage_close_facts(project, gates.parse(
        conductor._create_gate(project, st, "stage-close", "close?", stage=None)
    ))
    assert stageless["stage_known"] is False


def test_in_flight_row_and_missing_dossier_are_disk_facts(
    tmp_path: pathlib.Path,
) -> None:
    """Clause 3/4: an in-flight conductor row and a missing dossier each block
    the release — and both are read from the queue/directory, not the gate."""
    project = _project(tmp_path, mode="off")
    _roadmap(project, {"k1": "done"})
    _credentials(project, "k1")
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "stage-close", "close stage 1?", stage=1, refs=["stage-1"]
    )
    gate = gates.parse(gate_path)

    # no dossier yet -> clause 5 of the proposition
    facts = conductor._stage_close_facts(project, gate)
    assert facts["dossier_written"] is False
    assert conductor.proposition_stage_close_credentials(facts).reason_code == (
        "stage-close-dossier-missing"
    )
    _dossier(project)
    assert conductor._stage_close_facts(project, gate)["dossier_written"] is True

    # an in-flight conductor row owning k1 -> clause 3
    task_md = project / ".agenticdoc" / "k1" / "workers" / "ap-k1-t01" / "task.md"
    task_md.parent.mkdir(parents=True, exist_ok=True)
    task_md.write_text("type: coding\n\nwork\n", encoding="utf-8", newline="\n")
    (project / ".agenticdoc" / "_workers.parallel").write_text(
        "ap-k1-t01 | running | pi | timi | "
        f"{task_md} | 2026-10-13T00:00:00Z | 2026-10-13T00:00:00Z | "
        "timi/glm-5.3 | conductor\n",
        encoding="utf-8", newline="\n",
    )
    facts = conductor._stage_close_facts(project, gate)
    assert facts["in_flight_keys"] == ["k1"]
    assert conductor.proposition_stage_close_credentials(facts).reason_code == (
        "stage-close-in-flight"
    )
    # counterfactual: the same row marked done no longer blocks
    text = (project / ".agenticdoc" / "_workers.parallel").read_text(encoding="utf-8")
    (project / ".agenticdoc" / "_workers.parallel").write_text(
        text.replace("| running |", "| done |"), encoding="utf-8", newline="\n"
    )
    assert conductor._stage_close_facts(project, gate)["in_flight_keys"] == []
    _verify(
        "VC-1",
        dossier_clause="stage-close-dossier-missing",
        in_flight_clause="stage-close-in-flight",
        counterfactual_done_row="not-in-flight",
    )


# ── the approve branch (live, shadow prerequisite met) ───────────────────────

def test_auto_release_approves_a_complete_stage_close(tmp_path: pathlib.Path) -> None:
    """VC-2: a complete stage-close gate is auto-approved, the state change is
    real (the stage closes), and the trace is an existing-field-only record:
    gate `answered_by` + `answer_source` + `auto_policy_id`, one `decide` row,
    one `gate-auto-decision` event."""
    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "done"})
    _credentials(project, "k1")
    st = _state(project)
    gate = _open_stage_close_via_closure(project, st)
    assert gate.status == "pending"
    dossier = project / ".agenticdoc" / "_autopilot" / "stages" / "stage-1-close.md"
    assert dossier.is_file()
    _seed_shadow_history(project, conductor.STAGE_CLOSE_AUTO_RULE_ID)

    conductor.orchestrate(project, st)

    gate = gates.parse(gate.path)
    assert gate.status == "approved"
    assert gate.answered_by == f"conductor-auto:{conductor.STAGE_CLOSE_AUTO_RULE_ID}"
    assert gate.answered_at is not None
    assert gate.answer_source == conductor.AUTO_ANSWER_SOURCE
    assert gate.auto_policy_id == f"{conductor.STAGE_CLOSE_AUTO_RULE_ID}@1"
    assert _stage_status(project, 1) == "closed"  # the release really happened

    rows = _decide_rows(project, gate.id)
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["decision"] == "approve" and row["executed"] is True
    assert row["rule_id"] == conductor.STAGE_CLOSE_AUTO_RULE_ID
    assert row["rule_version"] == "1"
    assert row["gate_kind"] == "stage-close"
    assert row["gate_stage"] == 1
    assert row["reason_code"] == "stage-close-ok"
    assert row["decided_by"] == "conductor"
    assert row["gate_file_sha256_before"] != row["gate_file_sha256_after"]
    assert row["decision_id"] in conductor.auto_consumption_set(project)
    # the authority projection is exactly the frozen whitelist
    assert set(conductor.auto_authority_fields(row)) == set(
        conductor._AUTO_AUTHORITY_KEYS
    )
    assert row["evidence"] and all(
        set(entry) == {"path", "sha256", "mtime_ns"} for entry in row["evidence"]
    )
    events = [e for e in _events(project) if e["ev"] == "gate-auto-decision"]
    assert events and events[-1]["data"]["decision_id"] == row["decision_id"]
    assert "auto-approve" in events[-1]["detail"]
    _verify(
        "VC-2",
        gate=gate.status,
        stage=_stage_status(project, 1),
        answered_by=gate.answered_by,
        answer_source=gate.answer_source,
        auto_policy_id=gate.auto_policy_id,
        decide_rows=len(rows),
    )


def test_auto_release_is_idempotent_across_ticks(tmp_path: pathlib.Path) -> None:
    """VC-3: file truth is the idempotency key — a second/third tick neither
    re-approves, nor rewrites the gate bytes, nor appends another row."""
    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "done"})
    _credentials(project, "k1")
    st = _state(project)
    gate = _open_stage_close_via_closure(project, st)
    _seed_shadow_history(project, conductor.STAGE_CLOSE_AUTO_RULE_ID)
    conductor.auto_decide_gates(project, st, _cfg(project))
    gate_bytes = gate.path.read_bytes()
    rows_first = _decide_rows(project)
    assert gates.parse(gate.path).status == "approved"

    for _ in range(3):
        conductor.auto_decide_gates(project, st, _cfg(project))

    assert gate.path.read_bytes() == gate_bytes
    assert _decide_rows(project) == rows_first
    assert len([r for r in rows_first if r["decision"] == "approve"]) == 1
    _verify(
        "VC-3",
        gate_bytes_unchanged=_true(gate.path.read_bytes() == gate_bytes),
        decide_rows=len(rows_first),
        approve_rows=len([r for r in rows_first if r["decision"] == "approve"]),
    )


def test_live_without_the_shadow_prerequisite_still_refuses(
    tmp_path: pathlib.Path,
) -> None:
    """P-03 counterfactual: T-12 must NOT weaken the existing live
    prerequisite. With no shadow history the complete gate stays pending and
    the refusal is the existing `shadow-gate-not-met`."""
    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "done"})
    _credentials(project, "k1")
    st = _state(project)
    gate = _open_stage_close_via_closure(project, st)
    conductor.auto_decide_gates(project, st, _cfg(project))
    assert gates.parse(gate.path).status == "pending"
    rows = _decide_rows(project, gate.id)
    assert len(rows) == 1
    assert rows[0]["decision"] == "escalate"
    assert rows[0]["reason_code"] == "shadow-gate-not-met"
    assert conductor.auto_consumption_set(project) == set()
    _verify(
        "VC-3",
        gate="pending",
        reason=rows[0]["reason_code"],
        shadow_nights=conductor.shadow_prerequisites(project)["nights"],
    )


# ── the fallback branch (visible, never silent) ──────────────────────────────

def test_auto_release_falls_back_when_credentials_are_missing(
    tmp_path: pathlib.Path,
) -> None:
    """VC-4 (the JCodingAss `gate-0008` shape): a done key without
    `l3-verdict.txt`/`l3-report.md` must fall back to the human gate, and the
    refusal must NAME the missing items on both existing faces — the ledger
    row (`evidence[]` entries with `sha256: None`) and the event `detail`."""
    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "done", "k2": "done"})
    _credentials(project, "k1")
    # k2 is terminal but has no L3 record at all (the historical shape)
    st = _state(project)
    _dossier(project)
    gate_path = conductor._create_gate(
        project, st, "stage-close", "close stage 1?", stage=1, refs=["stage-1"]
    )
    gate = gates.parse(gate_path)
    conductor.auto_decide_gates(project, st, _cfg(project))

    gate = gates.parse(gate_path)
    assert gate.status == "pending"
    assert gate.answered_by is None
    assert gate.answer_source is None
    rows = _decide_rows(project, gate.id)
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["decision"] == "escalate" and row["executed"] is False
    assert row["reason_code"] == "stage-close-reconciliation"
    assert row["refusal_code"] == "stage-close-reconciliation"
    assert row["reason_code"] in conductor.REASON_CODES
    missing = {
        entry["path"] for entry in row["evidence"] if entry.get("sha256") is None
    }
    assert any(path.endswith("k2/l3-verdict.txt") for path in missing), missing
    assert any(path.endswith("k2/l3-report.md") for path in missing), missing

    event = [
        e for e in _events(project) if e["ev"] == "gate-auto-decision"
    ][-1]
    assert "stage-close-reconciliation" in event["detail"]
    assert "l3-verdict.txt" in event["detail"] and "l3-report.md" in event["detail"]
    # a repeated tick records the same refusal exactly once (dedup)
    before = len(_decide_rows(project))
    conductor.auto_decide_gates(project, st, _cfg(project))
    assert len(_decide_rows(project)) == before
    _verify(
        "VC-4",
        gate=gate.status,
        reason=row["reason_code"],
        missing_evidence=len(missing),
        fallback_row=1,
        dedup=_true(len(_decide_rows(project)) == before),
    )


def test_fallback_row_is_auditable_with_the_missing_item_names(
    tmp_path: pathlib.Path,
) -> None:
    """The refusal's `detail` carries the per-key missing-credential list, so
    the "why not automatic" answer needs no new field or event name."""
    facts = _good_facts(
        reconciliation_blocking=True,
        reconciliation_keys=["llm-router"],
        missing_credentials={
            "llm-router": ["l3-verdict.txt=meets", "l3-report.md"]
        },
    )
    result = conductor.proposition_stage_close_credentials(facts)
    assert result.ok is False
    assert "llm-router" in result.detail
    assert "l3-verdict.txt=meets" in result.detail
    assert "l3-report.md" in result.detail
    _verify(
        "VC-4",
        reason=result.reason_code,
        detail_named=_true("l3-verdict.txt=meets" in result.detail),
    )


# ── D-014②: stage-confirm is never automatic ────────────────────────────────

def test_stage_confirm_stays_a_guard_never_an_answer(tmp_path: pathlib.Path) -> None:
    """VC-5: `stage-confirm` is the authorisation to START a stage
    (D-011 中档 excludes it). The rule table keeps it a guard, and even with
    the shadow prerequisite met and its fact plane TRUE it produces no answer,
    no row and no event."""
    rule = conductor.AUTO_RULE_BY_KIND["stage-confirm"]
    assert rule.auto_action == "guard"

    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "running"})
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "stage-confirm", "start stage 1?", stage=1, refs=["stage-1"],
        machine_fields={
            "roadmap_validation": "[]",
            "goal_sha256": conductor._goal_sha256(project) or "",
        },
    )
    _seed_shadow_history(project, rule.rule_id)
    conductor.auto_decide_gates(project, st, _cfg(project))

    gate = gates.parse(gate_path)
    assert gate.status == "pending"
    assert gate.answered_by is None
    assert _decide_rows(project, gate.id) == []
    assert [e for e in _events(project) if e["ev"] == "gate-auto-decision"] == []
    _verify(
        "VC-5",
        auto_action=rule.auto_action,
        gate=gate.status,
        answer_rows=len(_decide_rows(project, gate.id)),
    )


# ── D-014④: the 48h fallback stays escalation-only ──────────────────────────

def test_48h_fallback_escalates_but_never_closes_the_stage(
    tmp_path: pathlib.Path,
) -> None:
    """VC-6 regression (required by T-12 requirement 6): the existing 48h
    deferred-review fallback is an ESCALATION signal, never a closure path —
    it neither opens a stage-close gate, nor writes a dossier, nor rewrites a
    key-status, nor touches the deferrable gate's bytes."""
    project = _project(tmp_path, mode="off")
    _roadmap(project, {"k1": "pending-review", "k2": "done"})
    _credentials(project, "k2")
    st = _state(project)
    past = (
        datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=1)
    ).isoformat(timespec="seconds")
    gate_path = conductor._create_gate(
        project, st, "stalled", "review k1?", key="k1", stage=1, refs=["review:k1"],
        machine_fields={"reason_code": "l3-no-verdict", "expires_at": past},
    )
    gate_bytes = gate_path.read_bytes()
    roadmap_path = roadmap.roadmap_path(project)
    roadmap_bytes = roadmap_path.read_bytes()

    conductor.orchestrate(project, st)

    escalated = [
        e for e in _events(project)
        if e["ev"] == "review-escalated" and e["key"] == "k1"
    ]
    triggers = {e["data"]["trigger"] for e in escalated}
    assert "deadline" in triggers and "closure" in triggers, triggers
    assert _key_status(project, "k1") == "pending-review"
    assert roadmap_path.read_bytes() == roadmap_bytes
    assert gate_path.read_bytes() == gate_bytes
    assert _gate_kinds(project, "stage-close") == []
    assert not (
        project / ".agenticdoc" / "_autopilot" / "stages" / "stage-1-close.md"
    ).is_file()
    # the two TTL constants remain one and the same 48h value
    assert conductor.GATE_DEFAULT_TTL_SEC == 48 * 3600
    assert conductor.REVIEW_DEADLINE_SEC == conductor.GATE_DEFAULT_TTL_SEC
    # and the documented "escalation-only" contract text is untouched
    docstring = conductor._process_deferred_reviews.__doc__ or ""
    assert "It NEVER closes the stage and NEVER rewrites a key" in docstring
    _verify(
        "VC-6",
        triggers=sorted(triggers),
        key_status=_key_status(project, "k1"),
        stage_close_gates=len(_gate_kinds(project, "stage-close")),
        key_status_bytes_unchanged=_true(roadmap_path.read_bytes() == roadmap_bytes),
    )


# ── frozen surfaces: no new field / event / config key ──────────────────────

def test_no_new_config_key_and_no_new_frozen_field() -> None:
    """AC-011 / T-12 req. 8: the 21-key config schema, the frozen 40-name gate
    order and the gate-kind set are untouched by this change."""
    expected_config_keys = {
        "enabled", "paused", "poll_interval_sec", "max_parallel_keys",
        "max_workers_per_key",
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
    # the trace fields used are registered ones, not additions
    assert "answer_source" in gates.FRONTMATTER_FIELDS
    assert "auto_policy_id" in gates.FRONTMATTER_FIELDS
    assert "gate-auto-decision" in timeline.EVENT_TYPES
    _verify(
        "VC-7",
        config_keys=len(expected_config_keys),
        frontmatter_fields=len(gates.FRONTMATTER_FIELDS),
        gate_kinds=len(gates.GATE_KINDS),
    )


# ── field evidence: the real JCodingAss pending gates (read-only) ───────────

_JC_AG_ROOT = pathlib.Path("H:/git/JCodingAss")
_JC_AG_GATES = _JC_AG_ROOT / ".agenticdoc" / "_autopilot" / "gates"


@pytest.mark.skipif(
    not _JC_AG_GATES.is_dir(), reason="JCodingAss evidence repo not present"
)
def test_field_evidence_gate_0007_releases_and_gate_0008_falls_back() -> None:
    """VC-8 (T-08 verified, re-derived read-only): JCodingAss `gate-0007`
    (stage 2, complete credentials) satisfies the release proposition, while
    `gate-0008` (stage 1, `llm-router` missing `l3-verdict.txt`/`l3-report.md`)
    refuses and names those files. Read-only: nothing under the repo is
    written."""
    probes: dict[str, tuple[bool, str, str]] = {}
    for gate in gates.enumerate(conductor.gates_dir(_JC_AG_ROOT)):
        if gate.kind != "stage-close":
            continue
        result = conductor.proposition_stage_close_credentials(
            conductor._stage_close_facts(_JC_AG_ROOT, gate)
        )
        probes[gate.id] = (result.ok, result.reason_code, result.detail)
    if "gate-0007" not in probes or "gate-0008" not in probes:
        pytest.skip("JCodingAss stage-close gates moved; field evidence not re-checkable")
    assert probes["gate-0007"][0] is True, probes["gate-0007"]
    assert probes["gate-0008"][0] is False, probes["gate-0008"]
    assert "l3-verdict.txt=meets" in probes["gate-0008"][2]
    assert "l3-report.md" in probes["gate-0008"][2]
    _verify(
        "VC-8",
        gate_0007=probes["gate-0007"][1],
        gate_0008=probes["gate-0008"][1],
        gate_0008_missing_named=_true("l3-verdict.txt=meets" in probes["gate-0008"][2]),
    )


def test_hermetic_mirror_of_the_jcodingass_field_shape(tmp_path: pathlib.Path) -> None:
    """VC-8 hermetic twin: the gate-0007/0008 outcome is locked with local
    fixtures even when the external evidence repo is absent."""
    # gate-0007 shape: single key, complete terminal credentials
    ready = _project(tmp_path / "ready", mode="off")
    _roadmap(ready, {"e2e-validation": "done"})
    _credentials(ready, "e2e-validation")
    st = _state(ready)
    _dossier(ready, 1)
    gate_path = conductor._create_gate(
        ready, st, "stage-close", "close stage 1?", stage=1, refs=["stage-1"]
    )
    ready_result = conductor.proposition_stage_close_credentials(
        conductor._stage_close_facts(ready, gates.parse(gate_path))
    )
    assert ready_result.ok is True, ready_result

    # gate-0008 shape: one of several keys lacks the L3 record
    broken = _project(tmp_path / "broken", mode="off")
    _roadmap(broken, {"llm-router": "done", "plugin-ui": "done"})
    _credentials(broken, "plugin-ui")
    st2 = _state(broken)
    _dossier(broken, 1)
    gate_path2 = conductor._create_gate(
        broken, st2, "stage-close", "close stage 1?", stage=1, refs=["stage-1"]
    )
    broken_result = conductor.proposition_stage_close_credentials(
        conductor._stage_close_facts(broken, gates.parse(gate_path2))
    )
    assert broken_result.ok is False
    assert broken_result.reason_code == "stage-close-reconciliation"
    assert "llm-router" in broken_result.detail
    assert "l3-verdict.txt=meets" in broken_result.detail
    _verify(
        "VC-8",
        ready=ready_result.reason_code,
        broken=broken_result.reason_code,
        broken_names_missing=_true("l3-report.md" in broken_result.detail),
    )


# ── the ledger phase is `decide` and the row shape is the T-07 contract ─────

def test_ledger_row_is_a_decide_phase_row_with_stage_and_rule(
    tmp_path: pathlib.Path,
) -> None:
    """VC-9: the production ledger (0 `decide` rows before this change) now
    receives an auditable `phase:"decide"` row carrying gate id, stage and
    rule id — the exact three fields requirement 3 names."""
    project = _project(tmp_path, mode="live")
    _roadmap(project, {"k1": "done"})
    _credentials(project, "k1")
    st = _state(project)
    gate = _open_stage_close_via_closure(project, st)
    assert conductor.auto_decision_rows(project) == []  # pre-change baseline
    _seed_shadow_history(project, conductor.STAGE_CLOSE_AUTO_RULE_ID)
    conductor.auto_decide_gates(project, st, _cfg(project))
    decided = [
        row for row in conductor.auto_decision_rows(project)
        if row.get("phase") == "decide" and row.get("gate_id") == gate.id
    ]
    assert len(decided) == 1
    row = decided[0]
    assert row["gate_id"] == gate.id
    assert row["gate_stage"] == 1
    assert row["rule_id"] == conductor.STAGE_CLOSE_AUTO_RULE_ID
    assert row["reason_code"] == "stage-close-ok"
    assert row["evidence"]  # the 依据摘要: path/sha256/mtime_ns per pointer
    _verify(
        "VC-9",
        gate_id=row["gate_id"],
        gate_stage=row["gate_stage"],
        rule_id=row["rule_id"],
        evidence=len(row["evidence"]),
    )
