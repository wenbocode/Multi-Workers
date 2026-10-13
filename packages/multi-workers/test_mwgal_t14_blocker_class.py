"""
T-14 / AC-007 - `blocker_class` out-of-order scalar registration + fail-closed.

Covers the five fail-closed forms the dispatch card names (T-A..T-E) plus the
registration counterfactual (removing the registration makes the WHOLE queue
fail closed, not just one field unreadable) and the materialize point.

Fixtures are pure files under tmp_path; nothing touches a real project.
"""
from __future__ import annotations

import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

from autopilot import closure, conductor, gates

# Minimal fully-satisfied stalled fact plane: proposition ok AND the
# `stalled-false-negative` approve_extra satisfied. Only blocker_class differs.
APPROVABLE_STALLED_FACTS = {
    "reason_code_field": "l3-below",
    "cause_class": "l3-below",
    "used_rounds": 1,
    "round_limit": 1,
    "credits_used": 0,
    "false_negative_class": "proven-false-negative",
}


def _write(
    tmp_path: pathlib.Path,
    *,
    extra: list[str] | None = None,
    name: str = "gate-0001.md",
    kind: str = "stalled",
    status: str = "pending",
) -> pathlib.Path:
    d = tmp_path / "gates"
    d.mkdir(parents=True, exist_ok=True)
    stem = name[:-3] if name.endswith(".md") else name
    lines = [
        f"id: {stem}",
        f"kind: {kind}",
        "stage: 2",
        "key: k3",
        "created_at: 2026-09-10T08:00:00+00:00",
        "created_by: conductor",
        "question: Is this gate valid?",
        "context_refs: []",
        f"status: {status}",
        "answered_at:",
        "answered_by:",
        "note:",
    ]
    lines.extend(extra or [])
    p = d / name
    p.write_text("---\n" + "\n".join(lines) + "\n---\n\nbody\n", encoding="utf-8", newline="\n")
    return p


def _stalled_rule() -> conductor.AutoRule:
    return conductor.AUTO_RULE_BY_KIND["stalled"]


# --- registration shape -------------------------------------------------------


def test_blocker_class_is_an_out_of_order_closed_scalar() -> None:
    # Declared as a parallel SCALAR set, never via the list/JSON mechanisms.
    assert "blocker_class" in gates._SCALAR_EXTENSION_FIELDS
    assert "blocker_class" not in gates._JSON_LIST_FIELDS
    assert "blocker_class" not in gates._JSON_OBJ_FIELDS
    assert "blocker_class" not in gates._LIST_FIELDS
    # Frozen 40-name order untouched; stays optional.
    assert "blocker_class" not in gates.FRONTMATTER_FIELDS
    assert len(gates.FRONTMATTER_FIELDS) == 40
    assert "blocker_class" not in gates._REQUIRED_FIELDS
    # Closed value set, exact members.
    assert set(gates.BLOCKER_CLASSES) == {"paperwork", "judgment"}


def test_valid_values_parse_and_absent_stays_none(tmp_path: pathlib.Path) -> None:
    for value in ("paperwork", "judgment"):
        gate = gates.parse(_write(tmp_path, extra=[f"blocker_class: {value}"]))
        assert gate.blocker_class == value
    # Absent (and bare-empty) keeps None - the parser never folds.
    assert gates.parse(_write(tmp_path)).blocker_class is None
    assert gates.parse(_write(tmp_path, extra=["blocker_class:"])).blocker_class is None
    print("[VERIFY] T-14: parser_preserves_none=true closed_set=2")


# --- T-A: malformed value -----------------------------------------------------


def test_t_a_malformed_value_is_not_silently_healthy(tmp_path: pathlib.Path) -> None:
    malformed = [
        "'  '",                     # whitespace-only (quoted so it survives)
        "paper work",               # embedded space
        "paperwork" * 40,           # overlong
        "'paper\\nwork'",           # embedded newline escape
        "'Paperwork'",              # case is not normalized
    ]
    for raw in malformed:
        p = _write(tmp_path, extra=[f"blocker_class: {raw}"])
        with pytest.raises(gates.GateFormatError) as exc:
            gates.parse(p)
        assert "blocker_class" in str(exc.value), raw
    # A bare empty value is "unclassified" (None), which is fail-closed too:
    # it must never be read as healthy.
    quiet = gates.parse(_write(tmp_path, extra=["blocker_class:"]))
    assert quiet.blocker_class is None
    assert conductor.blocker_class_of(quiet) != "paperwork"
    print("[VERIFY] T-14 T-A: malformed=5 unclassified=not-paperwork")


# --- T-B: out-of-enum ---------------------------------------------------------


def test_t_b_out_of_enum_fails_closed(tmp_path: pathlib.Path) -> None:
    p = _write(tmp_path, extra=["blocker_class: bogus"])
    with pytest.raises(gates.GateFormatError) as exc:
        gates.parse(p)
    assert "unknown blocker_class 'bogus'" in str(exc.value)
    # The error names the legal closed set.
    assert "judgment, paperwork" in str(exc.value)
    print("[VERIFY] T-14 T-B: out_of_enum=false closed_set_listed=true")


# --- T-C: type error (list) ---------------------------------------------------


def test_t_c_list_typed_value_fails_explicitly(tmp_path: pathlib.Path) -> None:
    list_shapes = ["[paperwork]", "[paperwork, judgment]", "'[\"paperwork\"]'"]
    for raw in list_shapes:
        p = _write(tmp_path, extra=[f"blocker_class: {raw}"])
        with pytest.raises(gates.GateFormatError):
            gates.parse(p)
    # YAML block-list under a scalar name is a malformed frontmatter line.
    p = _write(tmp_path, extra=["blocker_class:", "  - paperwork"])
    with pytest.raises(gates.GateFormatError):
        gates.parse(p)
    print("[VERIFY] T-14 T-C: list_shapes_rejected=4")


# --- T-D: legacy v1 gate (field absent) ---------------------------------------


def test_t_d_legacy_v1_gate_absent_field_is_readable_and_not_auto_approved(
    tmp_path: pathlib.Path,
) -> None:
    p = _write(tmp_path)  # real legacy shape: no blocker_class at all
    gate = gates.parse(p)  # must NOT raise: backward compatible readable
    assert gate.blocker_class is None
    # Judgment layer folds None -> judgment (fail-safe, not "no blockage").
    assert conductor.blocker_class_of(gate) == "judgment"
    facts = {**APPROVABLE_STALLED_FACTS, "blocker_class": conductor.blocker_class_of(gate)}
    decision, reason, prop = conductor.auto_decision_for_rule(_stalled_rule(), facts)
    assert prop.ok is True  # the stalled proposition itself holds
    assert decision == "escalate"
    assert reason == "blocker-class-not-paperwork"
    print("[VERIFY] T-14 T-D: legacy_none=true folded=judgment auto_approve=false")


# --- T-E: blocker_class and the stalled judgment coexist ----------------------


def test_t_e_judgment_wins_over_an_approvable_stalled_proposition(tmp_path: pathlib.Path) -> None:
    gate = gates.parse(_write(tmp_path, extra=["blocker_class: judgment"]))
    facts = {**APPROVABLE_STALLED_FACTS, "blocker_class": conductor.blocker_class_of(gate)}
    decision, reason, prop = conductor.auto_decision_for_rule(_stalled_rule(), facts)
    assert prop.ok is True
    assert (decision, reason) == ("escalate", "blocker-class-not-paperwork")


def test_t_e_paperwork_does_not_override_a_failing_stalled_proposition(tmp_path: pathlib.Path) -> None:
    gate = gates.parse(_write(tmp_path, extra=["blocker_class: paperwork"]))
    bad_facts = {
        "reason_code_field": "l3-below",
        "cause_class": "l3-suspect",  # reason drift => proposition false
        "used_rounds": 3,
        "round_limit": 2,
        "credits_used": 1,
        "false_negative_class": "proven-false-negative",
        "blocker_class": conductor.blocker_class_of(gate),
    }
    decision, reason, prop = conductor.auto_decision_for_rule(_stalled_rule(), bad_facts)
    assert prop.ok is False
    assert decision == "escalate"
    assert reason == "stalled-reason-drift"  # NOT blocker-class-not-paperwork
    print("[VERIFY] T-14 T-E: judgment_priority=true paperwork_not_sufficient=true")


def test_t_e_blocker_class_never_mutates_kind_or_status(tmp_path: pathlib.Path) -> None:
    gate = gates.parse(_write(tmp_path, extra=["blocker_class: paperwork"]))
    assert (gate.kind, gate.status) == ("stalled", "pending")
    # Only one rule per kind exists: registering the scalar adds no rule.
    assert len([r for r in conductor.RULES if r.gate_kind == "stalled"]) == 1


def test_paperwork_proceeds_only_when_the_rule_still_holds(tmp_path: pathlib.Path) -> None:
    gate = gates.parse(_write(tmp_path, extra=["blocker_class: paperwork"]))
    facts = {**APPROVABLE_STALLED_FACTS, "blocker_class": conductor.blocker_class_of(gate)}
    decision, reason, prop = conductor.auto_decision_for_rule(_stalled_rule(), facts)
    assert prop.ok is True
    assert (decision, reason) == ("approve", "stalled-false-negative")
    print("[VERIFY] T-14: paperwork_necessary_not_sufficient=true")


# --- registration counterfactual: the whole queue fails closed ---------------


def test_removing_the_registration_fails_the_whole_queue_closed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    carrier = _write(tmp_path, extra=["blocker_class: paperwork"])
    assert gates.parse(carrier).blocker_class == "paperwork"  # registered: passes
    # A clean gate in the same queue, to prove the blast radius is the queue.
    gates.create(tmp_path / "gates", "stalled", "clean", [], key="k1")

    monkeypatch.setattr(gates, "_SCALAR_EXTENSION_FIELDS", frozenset())
    with pytest.raises(gates.GateFormatError) as exc:
        gates.parse(carrier)
    assert "unknown frontmatter field 'blocker_class'" in str(exc.value)
    with pytest.raises(gates.GateFormatError):
        gates.pending_gates(tmp_path / "gates")
    print("[VERIFY] T-14 counterfactual: queue_wide_fail_closed=true")


# --- materialize point --------------------------------------------------------


def test_stall_blocker_class_materializes_fail_safe(tmp_path: pathlib.Path) -> None:
    key_dir = tmp_path / ".agenticdoc" / "k1"
    key_dir.mkdir(parents=True)
    # No marker => judgment (never optimistic).
    assert conductor._stall_blocker_class(tmp_path, "k1") == "judgment"
    # Deterministic achieved.md bad-draft criterion => paperwork.
    (key_dir / "achieved.md").write_text("# Achieved\n", encoding="utf-8", newline="\n")
    closure.write_bad_draft_marker(key_dir, ["NO MATCH: achieved.md missing pattern 'x'"])
    assert conductor._stall_blocker_class(tmp_path, "k1") == "paperwork"
    print("[VERIFY] T-14 materialize: no_marker=judgment bad_draft=paperwork")


def test_stamp_defaults_drops_out_of_set_blocker_class(tmp_path: pathlib.Path) -> None:
    p = gates.create(tmp_path / "gates", "stalled", "q", [], key="k1")
    dropped = conductor._stamp_gate_defaults(p, {"blocker_class": "bogus"})
    assert "blocker_class" in dropped
    # The out-of-set value never reaches the file; the field stays absent.
    assert gates.parse(p).blocker_class is None
    print("[VERIFY] T-14 write-guard: out_of_set_dropped=true")
