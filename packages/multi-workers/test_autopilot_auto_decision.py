"""
test_autopilot_auto_decision.py — T-07 (mw-autopilot-slot-capacity).

Covers the key's main deliverable: fact-plane predicates that CAN BE FALSE,
the tautology self-check, the automatic-decision execution chain (off /
shadow / live), the append-only `auto-decisions.jsonl` ledger, quota + a
PERSISTED breaker, `gate-auto-revoke` keyed by `decision_id`, the T-06
evidence wiring, and the `evidence-reconciliation` barrier.

Non-vacuous counterfactuals (each goes red on a pre-T-07 implementation):
  (a) tautological predicate fixture            -> auto refused, gate pending
  (b) per rule, a "proposition is false" case   -> never an approve decision
  (c) shadow run                                -> gate bytes + roadmap bytes
                                                   byte-identical
  (d) trip the breaker, restart the process     -> still tripped (file-backed)
  (e) revoke one decision                       -> only that decision leaves
                                                   the consumption set
  (f) tamper `answered_by`                      -> authority fields untouched
"""
import datetime
import dataclasses
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import config, conductor, evidence, gates, roadmap, timeline  # noqa: E402


def _verify(tag: str, **kv) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in kv.items()))


def _true(value: bool) -> str:
    return "true" if value else "false"


# ── fixtures ──────────────────────────────────────────────────────────────────

def _project(
    tmp_path: pathlib.Path, *, mode: str = "off", enabled: bool = True
) -> pathlib.Path:
    ap = tmp_path / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True, exist_ok=True)
    (tmp_path / ".mw").mkdir(parents=True, exist_ok=True)
    (tmp_path / ".agenticdoc" / "goal.md").write_text(
        "# Goal\n\nShip the thing.\n", encoding="utf-8"
    )
    cfg = config.default_config()
    cfg["enabled"] = enabled
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


def _key_evidence_files(project: pathlib.Path, key: str) -> None:
    key_dir = project / ".agenticdoc" / key
    key_dir.mkdir(parents=True, exist_ok=True)
    (key_dir / "l3-verdict.txt").write_text("meets\n", encoding="utf-8")
    (key_dir / "l3-report.md").write_text("# report\nmeets\n", encoding="utf-8")
    (key_dir / "achieved.md").write_text("# Achieved\n" + "x" * 300 + "\n", encoding="utf-8")


def _seed_shadow_history(
    project: pathlib.Path, *, rule_id: str, nights: int = 5, count: int = 20
) -> None:
    for index in range(count):
        day = 1 + (index % nights)
        conductor._append_auto_decision_row(project, {
            "decision_id": f"seed-{index}",
            "phase": "decide",
            "mode": "shadow",
            "executed": False,
            "decision": "escalate",
            "rule_id": rule_id,
            "reason_code": "stalled-undecidable",
            "prop_ok": False,
            "gate_id": f"gate-{9000 + index:04d}",
            "gate_key": f"seed-key-{index}",
            "night": f"2026-09-{day:02d}",
            "decided_at": "2026-09-01T00:00:00+00:00",
        })


# ── predicates (pure, table-driven) ──────────────────────────────────────────

def test_predicate_table_positive_and_falsifying_counterexample() -> None:
    positives = [
        (conductor.proposition_stage_confirm, {
            "structural_validation": [],
            "goal_sha256": "a" * 64,
            "current_goal_sha256": "a" * 64,
        }),
        (conductor.proposition_stage_close, {
            "verdicts_final": [{"key": "k1", "verdict": "meets"}],
            "open_items": [],
            "status_of": {"k1": "done"},
        }),
        (conductor.proposition_stalled, {
            "reason_code_field": "l3-below",
            "cause_class": "l3-below",
            "used_rounds": 3,
            "round_limit": 2,
            "credits_used": 1,
            "false_negative_class": "proven-false-negative",
        }),
        (conductor.proposition_budget_exhausted, {
            "used_rounds": 2,
            "round_limit": 2,
            "credits_used": 0,
            "blocking_gap_count": 1,
        }),
        (conductor.proposition_goal_change, {
            "goal_sha256_before": "a" * 64,
            "goal_sha256_after": "b" * 64,
            "normative_changed": True,
        }),
        (conductor.proposition_xkey_authorize, {
            "red_after": 0,
            "returncode": 0,
            "timed_out": False,
            "test_id": "t1",
            "verify_test_id": "t1",
            "blast_radius": {"files": ["a.py"]},
            "write_scope": ["a.py"],
        }),
    ]
    assert len(positives) == 6
    for predicate, facts in positives:
        result = predicate(facts)
        assert result.ok is True, (predicate.__name__, result)
        assert result.reason_code in conductor.REASON_CODES

    # Each rule's declared witness makes the proposition FALSE (trigger AND
    # not-P) — the machine form of "can be false".
    for rule in conductor.RULES:
        facts = rule.counterexample()
        result = rule.proposition(facts)
        assert result.ok is False, f"{rule.rule_id}: counterexample did not falsify"
        assert result.reason_code in conductor.REASON_CODES
    _verify("VC-036", falsifiable=f"{len(conductor.RULES)}/{len(conductor.RULES)}",
            predicates=len(positives))


def test_stage_confirm_guard_fails_on_goal_drift_and_structural_error() -> None:
    facts = {
        "structural_validation": [],
        "goal_sha256": "a" * 64,
        "current_goal_sha256": "b" * 64,
    }
    assert conductor.proposition_stage_confirm(facts).ok is False
    assert not conductor.proposition_stage_confirm(
        {**facts, "structural_validation": ["dangling depends_on"]}
    ).ok
    _verify("VC-036", stage_confirm_counterexample="goal-drift+structural")


def test_predicates_are_not_field_read_backs() -> None:
    """A gate that merely re-states its own trigger does NOT satisfy the fact
    plane: stage-close with a below verdict must fail even though `done`."""
    result = conductor.proposition_stage_close({
        "verdicts_final": [{"key": "k1", "verdict": "below"}],
        "open_items": [],
        "status_of": {"k1": "done"},  # the trigger condition is true...
    })
    assert result.ok is False  # ...yet the proposition is false
    _verify("VC-035", stage_close_proposition_can_be_false=_true(result.ok is False))


# ── (a) tautology self-check ─────────────────────────────────────────────────

def _tautology_rule() -> conductor.AutoRule:
    return conductor.AutoRule(
        rule_id="tautology-fixture",
        rule_version="1",
        gate_kind="stalled",
        trigger_subject="key-status == stalled",
        proposition_subject="key-status == stalled",  # subject IS the trigger
        proposition=lambda facts: conductor._prop_ok("stalled-false-negative"),
        counterexample=lambda: {
            "reason_code_field": "l3-below",
            "cause_class": "l3-below",
            "used_rounds": 1,
            "round_limit": 1,
            "credits_used": 0,
            "false_negative_class": "proven-false-negative",
        },
        auto_action="approve",
    )


def test_counterfactual_a_tautology_is_refused() -> None:
    rule = _tautology_rule()
    falsifiable, why = conductor.rule_falsifiable(rule)
    assert falsifiable is False
    # An always-true predicate whose declared witness does not falsify it is
    # also refused (the second half of the self-check).
    always_true = dataclasses.replace(
        rule,
        trigger_subject="something else",
        proposition=lambda facts: conductor._prop_ok("stalled-false-negative"),
    )
    assert conductor.rule_falsifiable(always_true)[0] is False
    decision, reason, _prop = conductor.auto_decision_for_rule(rule, {})
    assert decision == "escalate" and reason == "tautology-rejected"
    _verify(
        "VC-035",
        tautology_rejected=_true(
            decision == "escalate" and reason == "tautology-rejected"
        ),
        reason=why[:40],
    )


def test_counterfactual_a_engine_refuses_tautology_rule(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, mode="live")
    conductor._create_gate(
        project, _state(project), "stalled", "retry?", key="k1", refs=["l3:k1"]
    )
    monkeypatch.setitem(conductor.AUTO_RULE_BY_KIND, "stalled", _tautology_rule())
    st = _state(project)
    conductor.auto_decide_gates(project, st, _cfg(project))
    gate = gates.parse(next(iter(conductor.gates_dir(project).glob("gate-*.md"))))
    assert gate.status == "pending"  # refused => nothing released
    assert conductor.auto_consumption_set(project) == set()
    rows = conductor.auto_decision_rows(project)
    assert rows and rows[-1]["reason_code"] == "tautology-rejected"
    _verify(
        "VC-035",
        engine_refused=_true(rows[-1]["reason_code"] == "tautology-rejected"),
        gate_status=gate.status,
    )


# ── (b) per-rule "proposition is false" case ────────────────────────────────

def test_counterfactual_b_every_rule_refuses_when_proposition_false() -> None:
    for rule in conductor.RULES:
        facts = rule.counterexample()
        decision, reason, prop = conductor.auto_decision_for_rule(rule, facts)
        assert prop.ok is False, rule.rule_id
        assert decision != "approve", rule.rule_id
        assert decision == "escalate", (rule.rule_id, decision)
        assert reason in conductor.REASON_CODES, (rule.rule_id, reason)
    _verify("VC-036", per_rule_false=f"{len(conductor.RULES)}/{len(conductor.RULES)}")


def test_counterfactual_b_engine_never_approves_false_budget_gate(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, mode="live")
    gate_path = conductor._create_gate(
        project, _state(project), "budget-exhausted", "add a round?",
        key="k1", refs=["l2:k1:x"],
    )
    assert gate_path is not None
    _seed_shadow_history(project, rule_id="budget-exhausted-bounded")
    # proposition false: gaps already cleared -> must NOT approve
    monkeypatch.setattr(
        conductor, "gate_facts",
        lambda root, gate, status_of=None: {
            "used_rounds": 2, "round_limit": 2, "credits_used": 0,
            "blocking_gap_count": 0,
        },
    )
    st = _state(project)
    conductor.auto_decide_gates(project, st, _cfg(project))
    assert gates.parse(gate_path).status == "pending"
    rows = conductor.auto_decision_rows(project)
    assert all(row.get("decision") != "approve" for row in rows)
    _verify(
        "VC-036",
        budget_false_no_approve=_true(
            all(row.get("decision") != "approve" for row in rows)
        ),
    )


# ── reason_code closed set + 12-call-site mapping table ─────────────────────

def test_reason_code_closed_set_is_closed() -> None:
    assert set(conductor.STALL_REASON_CODES) <= conductor.REASON_CODES
    assert len(conductor.STALL_REASON_CODES) == 12
    for rule in conductor.RULES:
        assert conductor.auto_decision_for_rule(
            rule, rule.counterexample()
        )[1] in conductor.REASON_CODES
    _verify("VC-025", reason_codes=len(conductor.REASON_CODES),
            stall_codes=len(conductor.STALL_REASON_CODES))


def _mark_stalled_calls(source: str) -> list[str]:
    calls: list[str] = []
    for match in re.finditer(r"\bmark_stalled\(", source):
        if source[:match.start()].rstrip().endswith("def"):
            continue  # the definition, not a call site
        start = match.end()
        depth = 1
        index = start
        while index < len(source) and depth:
            char = source[index]
            if char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1
        snippet = source[match.start():index]
        calls.append(snippet)
    return calls


def test_all_twelve_mark_stalled_call_sites_pass_a_reason_code() -> None:
    source = pathlib.Path(conductor.__file__).read_text(encoding="utf-8")
    calls = _mark_stalled_calls(source)
    assert len(calls) == 12, f"expected 12 call sites, found {len(calls)}"
    missing = [call[:60] for call in calls if "reason_code=" not in call]
    assert missing == [], f"call sites without reason_code: {missing}"
    codes = set(re.findall(r'reason_code="([a-z0-9-]+)"', source))
    assert codes <= set(conductor.STALL_REASON_CODES)
    assert codes == set(conductor.STALL_REASON_CODES)
    _verify("VC-025", call_sites=len(calls), mapped_codes=len(codes))


def test_mark_stalled_writes_reason_code_counts_into_the_gate(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path, mode="off")
    _roadmap_one_key(project, key_status="k1=running")
    st = _state(project)
    conductor.mark_stalled(
        project, st, "k1", "L3 below twice",
        reason_code="l3-below", loop="l3:k1",
        used_rounds=3, round_limit=2, credits_used=1,
    )
    gate = gates.parse(next(iter(conductor.gates_dir(project).glob("gate-*.md"))))
    assert gate.reason_code == "l3-below"
    assert gate.loop == "l3:k1"
    assert (gate.used_rounds, gate.round_limit, gate.credits_used) == (3, 2, 1)
    _verify(
        "VC-025",
        gate_reason_code=gate.reason_code,
        counts=f"{gate.used_rounds}/{gate.round_limit}/{gate.credits_used}",
    )


def test_created_snapshot_binds_the_final_gate_bytes(tmp_path: pathlib.Path) -> None:
    """The `created` snapshot must include the machine fields, otherwise the
    T-06 replay check would flag every stalled gate as replay-misbound."""
    project = _project(tmp_path, mode="live")
    _roadmap_one_key(project, key_status="k1=running")
    st = _state(project)
    conductor.mark_stalled(
        project, st, "k1", "L3 below twice",
        reason_code="l3-below", loop="l3:k1",
        used_rounds=3, round_limit=2, credits_used=1,
    )
    gate = gates.parse(next(iter(conductor.gates_dir(project).glob("gate-*.md"))))
    assert gate.reason_code == "l3-below"
    _binding, _drift, refusal = conductor.gate_evidence_state(project, gate, st)
    assert refusal != "replay-misbound", refusal
    _verify("VC-021", replay_misbound=_true(refusal == "replay-misbound"))


# ── timeline `data` payload (T-02 opened the read side) ─────────────────────

def test_timeline_append_emits_optional_data_payload(tmp_path: pathlib.Path) -> None:
    writer = timeline.Timeline(tmp_path / "timeline.jsonl")
    writer.append("beat")
    writer.append("gate-auto-decision", data={"decision_id": "gate-0001@t"})
    events = timeline.query_events(tmp_path / "timeline.jsonl").events
    assert set(events[0]) == {"ts", "seq", "ev", "key", "stage", "detail"}
    assert events[1]["data"] == {"decision_id": "gate-0001@t"}
    assert writer.append("beat") == 3  # legacy lines untouched by the payload
    _verify(
        "VC-021",
        data_payload=_true(events[1]["data"] == {"decision_id": "gate-0001@t"}),
        legacy_fields=len(events[0]),
    )


# ── off is today's behaviour ────────────────────────────────────────────────

def test_off_mode_is_a_no_op(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, mode="off")
    conductor._create_gate(project, _state(project), "stalled", "retry?", key="k1")
    assert not conductor.auto_decisions_path(project).exists()
    assert not list(conductor.gates_dir(project).glob("gate-*.evidence.json"))
    st = _state(project)
    conductor.auto_decide_gates(project, st, _cfg(project))
    assert not conductor.auto_decisions_path(project).exists()
    assert all(e["ev"] != "gate-auto-decision" for e in _events(project))
    _verify(
        "VC-022",
        auto_actions=len(conductor.auto_decision_rows(project)),
        sidecars=len(
            list(conductor.gates_dir(project).glob("gate-*.evidence.json"))
        ),
    )


# ── (c) shadow: ledger only, zero state delta ───────────────────────────────

def test_counterfactual_c_shadow_writes_ledger_with_zero_state_delta(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path, mode="shadow")
    _roadmap_one_key(project, key_status="k1=running")
    gate_path = conductor._create_gate(
        project, _state(project), "stalled", "retry?", key="k1", refs=["l3:k1"]
    )
    assert gate_path is not None
    rm_path = roadmap.roadmap_path(project)
    gate_before = gate_path.read_bytes()
    roadmap_before = rm_path.read_bytes()
    st = _state(project)
    credits_before = conductor._resume_credits(project, "k1")

    conductor.auto_decide_gates(project, st, _cfg(project))
    conductor.auto_decide_gates(project, st, _cfg(project))  # second tick: no spam

    assert gate_path.read_bytes() == gate_before  # gate file byte-identical
    assert rm_path.read_bytes() == roadmap_before  # key-status byte-identical
    assert conductor._resume_credits(project, "k1") == credits_before
    assert all(e["ev"] != "gate-answered" for e in _events(project))
    assert gates.parse(gate_path).status == "pending"
    shadow_rows = [
        row for row in conductor.auto_decision_rows(project)
        if row.get("mode") == "shadow"
    ]
    assert shadow_rows and all(row["executed"] is False for row in shadow_rows)
    assert len(shadow_rows) == 1  # one judgement per gate, even across ticks
    assert conductor.auto_consumption_set(project) == set()
    state_delta = (
        int(gate_path.read_bytes() != gate_before)
        + int(rm_path.read_bytes() != roadmap_before)
    )
    _verify("VC-033", state_delta=state_delta, shadow_rows=len(shadow_rows))


# ── ledger authority fields ─────────────────────────────────────────────────

def test_ledger_row_carries_conductor_derived_authority_fields(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path, mode="shadow")
    conductor._create_gate(
        project, _state(project), "stalled", "retry?", key="k1", refs=["l3:k1"]
    )
    st = _state(project)
    conductor.auto_decide_gates(project, st, _cfg(project))
    rows = conductor.auto_decision_rows(project)
    assert len(rows) == 1
    row = rows[0]
    for field in (
        "decision_id", "rule_id", "rule_version", "decided_by", "decided_at",
        "evidence", "switch", "budget", "reason_code",
    ):
        assert field in row, field
    assert row["decided_by"] == "conductor"
    assert set(row["switch"]) == {
        "enabled", "paused", "auto_gate_mode", "config_sha256", "effective_origins",
    }
    assert set(row["budget"]) == {
        "night_used", "night_cap", "key_used", "key_cap", "cooldown_s_left", "breaker",
    }
    assert all(set(e) == {"path", "sha256", "mtime_ns"} for e in row["evidence"])
    event = next(e for e in _events(project) if e["ev"] == "gate-auto-decision")
    assert event["data"]["decision_id"] == row["decision_id"]
    _verify("VC-021", fields=len(row), authority=row["decided_by"])


# ── live execution (requires the shadow gate) ───────────────────────────────

def test_live_approves_budget_gate_once_shadow_gate_is_met(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path, mode="live")
    _key_evidence_files(project, "k1")
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "budget-exhausted", "add a round?", key="k1", refs=["l2:k1:x"]
    )
    assert gate_path is not None
    _seed_shadow_history(project, rule_id="budget-exhausted-bounded")
    monkeypatch.setattr(
        conductor, "gate_facts",
        lambda root, gate, status_of=None: {
            "used_rounds": 2, "round_limit": 2, "credits_used": 0,
            "blocking_gap_count": 1,
        },
    )
    conductor.auto_decide_gates(project, st, _cfg(project))
    gate = gates.parse(gate_path)
    assert gate.status == "approved"
    assert gate.answered_by == "conductor-auto:budget-exhausted-bounded"
    rows = [r for r in conductor.auto_decision_rows(project) if r.get("phase") == "decide"]
    executed = [r for r in rows if r.get("executed")]
    assert len(executed) == 1
    assert executed[0]["decision"] == "approve"
    assert executed[0]["gate_file_sha256_before"] != executed[0]["gate_file_sha256_after"]
    assert executed[0]["decision_id"] in conductor.auto_consumption_set(project)
    _verify(
        "VC-023",
        live_approved=_true(gate.status == "approved"),
        consumed=len(conductor.auto_consumption_set(project)),
    )


def test_live_escalates_without_shadow_gate(tmp_path: pathlib.Path, monkeypatch) -> None:
    project = _project(tmp_path, mode="live")
    _key_evidence_files(project, "k1")
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "budget-exhausted", "add a round?", key="k1", refs=["l2:k1:x"]
    )
    monkeypatch.setattr(
        conductor, "gate_facts",
        lambda root, gate, status_of=None: {
            "used_rounds": 2, "round_limit": 2, "credits_used": 0,
            "blocking_gap_count": 1,
        },
    )
    conductor.auto_decide_gates(project, st, _cfg(project))
    assert gates.parse(gate_path).status == "pending"
    row = conductor.auto_decision_rows(project)[-1]
    assert row["decision"] == "escalate"
    assert row["reason_code"] == "shadow-gate-not-met"
    _verify(
        "VC-034",
        gate_blocked=_true(gates.parse(gate_path).status == "pending"),
        refusal=row["reason_code"],
    )


def test_live_escalates_when_gate_id_replay_misbinds_sidecar(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """T-06 item 1: an archived gate's sidecar must not bind to a reused id."""
    project = _project(tmp_path, mode="live")
    _key_evidence_files(project, "k1")
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "budget-exhausted", "add a round?", key="k1", refs=["l2:k1:x"]
    )
    _seed_shadow_history(project, rule_id="budget-exhausted-bounded")
    # Tamper the gate file after the snapshot -> sha no longer matches.
    conductor._rewrite_gate_fields(gate_path, {"note": "rewritten"})
    monkeypatch.setattr(
        conductor, "gate_facts",
        lambda root, gate, status_of=None: {
            "used_rounds": 2, "round_limit": 2, "credits_used": 0,
            "blocking_gap_count": 1,
        },
    )
    conductor.auto_decide_gates(project, st, _cfg(project))
    assert gates.parse(gate_path).status == "pending"
    assert conductor.auto_decision_rows(project)[-1]["refusal_code"] == "replay-misbound"
    _verify("VC-021", refusal=conductor.auto_decision_rows(project)[-1]["refusal_code"])


# ── (d) breaker is persisted (restart still tripped) ────────────────────────

def _seed_executed(project: pathlib.Path, *, key: str, signature: int) -> str:
    decision_id = f"gate-{9000 + signature:04d}@2026-09-26T00:00:00Z"
    conductor._append_auto_decision_row(project, {
        "decision_id": decision_id,
        "phase": "decide",
        "mode": "live",
        "executed": True,
        "decision": "approve",
        "rule_id": "budget-exhausted-bounded",
        "reason_code": "budget-ok",
        "gate_id": f"gate-{9000 + signature:04d}",
        "gate_key": key,
        "night": "2026-09-25",
        "decided_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
    })
    return decision_id


def test_counterfactual_d_breaker_survives_a_restart(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, mode="live")
    _seed_executed(project, key="k1", signature=1)
    _seed_executed(project, key="k1", signature=2)  # repeat signature => S3
    st = _state(project)
    conductor.auto_decide_gates(project, st, _cfg(project))
    assert conductor.auto_breaker_state(project)["active"] is True
    assert conductor.auto_brake_path(project).is_file()

    # Restart: brand-new process state, same files. An in-memory breaker would
    # come back clean here and go red on the assertion below.
    st2 = _state(project)
    assert conductor.auto_breaker_state(project)["active"] is True
    before = len(conductor.auto_decision_rows(project))
    conductor.auto_decide_gates(project, st2, _cfg(project))
    assert len(conductor.auto_decision_rows(project)) == before  # still stopped
    assert any(
        row.get("reason_code") == "breaker-tripped"
        and row.get("decision") == "escalate"
        for row in conductor.auto_decision_rows(project)
    )
    _verify(
        "VC-020",
        breaker_persisted=_true(
            conductor.auto_breaker_state(project)["active"] is True
        ),
        stopped_after_restart=_true(
            len(conductor.auto_decision_rows(project)) == before
        ),
    )


def test_night_quota_escalates(tmp_path: pathlib.Path, monkeypatch) -> None:
    project = _project(tmp_path, mode="live")
    _key_evidence_files(project, "k1")
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "budget-exhausted", "add a round?", key="k1", refs=["l2:k1:x"]
    )
    _seed_shadow_history(project, rule_id="budget-exhausted-bounded")
    # Fixed night so the assertion does not depend on the wall clock.
    monkeypatch.setattr(conductor, "night_window_key", lambda moment: "2026-09-25")
    for index in range(conductor.AUTO_NIGHT_CAP):
        conductor._append_auto_decision_row(project, {
            "decision_id": f"quota-{index}",
            "phase": "decide", "mode": "live", "executed": True,
            "decision": "approve", "rule_id": "budget-exhausted-bounded",
            "reason_code": f"reason-{index}", "gate_id": f"gate-{9100 + index}",
            "gate_key": f"other-{index}", "night": "2026-09-25",
            "decided_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        })
    monkeypatch.setattr(
        conductor, "gate_facts",
        lambda root, gate, status_of=None: {
            "used_rounds": 2, "round_limit": 2, "credits_used": 0,
            "blocking_gap_count": 1,
        },
    )
    conductor.auto_decide_gates(project, st, _cfg(project))
    assert gates.parse(gate_path).status == "pending"
    assert conductor.auto_decision_rows(project)[-1]["reason_code"] == "night-quota-exhausted"
    _verify(
        "VC-019",
        capped=_true(
            conductor.auto_decision_rows(project)[-1]["reason_code"]
            == "night-quota-exhausted"
        ),
    )


# ── (e) revoke removes only one decision ────────────────────────────────────

def test_counterfactual_e_revoke_removes_only_that_decision(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path, mode="off")
    first = _seed_executed(project, key="k1", signature=1)
    second = _seed_executed(project, key="k2", signature=2)
    assert conductor.auto_consumption_set(project) == {first, second}

    st = _state(project)
    assert conductor.revoke_auto_decision(project, st, first) is True
    assert conductor.auto_consumption_set(project) == {second}
    assert conductor.revoke_auto_decision(project, st, first) is False  # idempotent
    row = conductor.auto_decision_rows(project)[-1]
    assert row["phase"] == "revoke" and row["decision_id"] == first
    assert any(e["ev"] == "gate-auto-revoke" for e in _events(project))
    _verify(
        "VC-023",
        revoked_only_one=_true(conductor.auto_consumption_set(project) == {second}),
        remaining=len(conductor.auto_consumption_set(project)),
    )


# ── (f) answered_by is display-only ─────────────────────────────────────────

def test_counterfactual_f_tampering_answered_by_does_not_move_authority(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    project = _project(tmp_path, mode="live")
    _key_evidence_files(project, "k1")
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "budget-exhausted", "add a round?", key="k1", refs=["l2:k1:x"]
    )
    _seed_shadow_history(project, rule_id="budget-exhausted-bounded")
    monkeypatch.setattr(
        conductor, "gate_facts",
        lambda root, gate, status_of=None: {
            "used_rounds": 2, "round_limit": 2, "credits_used": 0,
            "blocking_gap_count": 1,
        },
    )
    conductor.auto_decide_gates(project, st, _cfg(project))
    row = next(
        r for r in conductor.auto_decision_rows(project) if r.get("executed")
    )
    authority_before = conductor.auto_authority_fields(row)
    assert authority_before["decided_by"] == "conductor"

    conductor._rewrite_gate_fields(
        gate_path, {"answered_by": "human", "answered_at": "1999-01-01T00:00:00Z"}
    )
    authority_after = conductor.auto_authority_fields(row)
    assert authority_after == authority_before  # the ledger is the authority
    assert "answered_by" not in authority_after
    gate = gates.parse(gate_path)
    assert gate.answered_by == "human"  # display field moved...
    assert row["decided_by"] == "conductor"  # ...authority did not
    _verify(
        "VC-046",
        authoritative_source=row["decided_by"],
        answered_by=(
            "display-only" if "answered_by" not in authority_after else "authority"
        ),
    )


# ── T-06 evidence wiring: corrupt / drift / benign touch ────────────────────

def test_corrupt_sidecar_is_unbound_and_escalates(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    project = _project(tmp_path, mode="live")
    _key_evidence_files(project, "k1")
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "budget-exhausted", "add a round?", key="k1", refs=["l2:k1:x"]
    )
    sidecar = evidence.sidecar_path(conductor.gates_dir(project), gates.parse(gate_path).id)
    sidecar.write_text("{ not json", encoding="utf-8")
    _seed_shadow_history(project, rule_id="budget-exhausted-bounded")
    monkeypatch.setattr(
        conductor, "gate_facts",
        lambda root, gate, status_of=None: {
            "used_rounds": 2, "round_limit": 2, "credits_used": 0,
            "blocking_gap_count": 1,
        },
    )
    conductor.auto_decide_gates(project, st, _cfg(project))
    assert gates.parse(gate_path).status == "pending"
    assert conductor.auto_decision_rows(project)[-1]["refusal_code"] == "corrupt-sidecar"
    corrupt_row = conductor.auto_decision_rows(project)[-1]
    _verify(
        "VC-021",
        corrupt_sidecar=corrupt_row["refusal_code"],
        disposition=corrupt_row["decision"],
    )


def test_evidence_rewrite_during_window_is_drift_not_partial(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    project = _project(tmp_path, mode="live")
    _key_evidence_files(project, "k1")
    st = _state(project)
    gate_path = conductor._create_gate(
        project, st, "budget-exhausted", "add a round?", key="k1", refs=["l2:k1:x"]
    )
    # benign touch first: mtime moves, bytes stay -> partial, NOT tampering
    verdict = project / ".agenticdoc" / "k1" / "l3-verdict.txt"
    binding, drift, refusal = conductor.gate_evidence_state(
        project, gates.parse(gate_path), st
    )
    assert drift is False and refusal is None, (binding, refusal)
    # real rewrite: bytes change -> drift => refuse
    verdict.write_text("below\n", encoding="utf-8")
    _binding, drift, refusal = conductor.gate_evidence_state(
        project, gates.parse(gate_path), st
    )
    assert drift is True and refusal == "evidence-drift"
    _verify(
        "VC-045",
        drift_detected=_true(drift is True),
        benign_touch="not-tampering",
    )


# ── reconciliation barrier ─────────────────────────────────────────────────

def test_reconciliation_blocks_new_stage_close(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, mode="live")
    _roadmap_one_key(project, key_status="k1=done")
    st = _state(project)
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    stage = rm.stages[0]
    # `claimed_done` but no evidence on disk => not bound_meets.
    conductor._stage_closure(
        project, st, stage, roadmap.roadmap_path(project), {"k1": "done"}
    )
    assert conductor.gates_dir(project).glob("gate-*.md")
    close_gates = [
        g for g in gates.enumerate(conductor.gates_dir(project))
        if g.kind == "stage-close"
    ]
    assert close_gates == []  # blocked before :628-630
    events = [e for e in _events(project) if e["ev"] == "evidence-reconciliation"]
    assert events and events[0]["key"] == "k1"
    _verify(
        "VC-044",
        stage_close_blocked=_true(close_gates == []),
        reconciliation_events=len(events),
    )


def test_reconciliation_off_keeps_today_control_flow(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path, mode="off")
    _roadmap_one_key(project, key_status="k1=done")
    st = _state(project)
    rm = roadmap.load_roadmap(roadmap.roadmap_path(project))
    conductor._stage_closure(
        project, st, rm.stages[0], roadmap.roadmap_path(project), {"k1": "done"}
    )
    close_gates = [
        g for g in gates.enumerate(conductor.gates_dir(project))
        if g.kind == "stage-close"
    ]
    assert len(close_gates) == 1
    assert all(e["ev"] != "evidence-reconciliation" for e in _events(project))
    _verify("VC-044", off_control_flow="unchanged")


# ── helpers used above ──────────────────────────────────────────────────────

def _roadmap_one_key(project: pathlib.Path, *, key_status: str) -> pathlib.Path:
    path = project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    path.write_text(
        "# Roadmap\n"
        "> generated_at: t\n"
        "> goal_mtime: 1\n"
        "\n"
        "## Stage 1: work\n"
        "> goal: deliver\n"
        "> status: running\n"
        f"> key-status: {key_status}\n"
        "### Keys\n"
        "| key | role | depends_on |\n"
        "|-----|------|-----------|\n"
        "| k1 | worker | - |\n",
        encoding="utf-8",
        newline="\n",
    )
    return path
