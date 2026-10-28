"""test_dp_consolidation_registry.py — T03: eight-entry protocol contract.

Covers, on the isolated copy only:

- the active set is exactly the eight spec §1.1 targets, and the 25 old ids are
  a separate read-only retired directory (6 migrated + 19 retired, 0 aliases);
- every old id is refused through the runtime resolver *and* through
  ``decide_for`` before the backend/executor, so the model-call count is 0;
- each entry's role/material/choice/basis contract has one source, the frozen
  choice ids and the four baseline menus are exact;
- dp-auto accepts PM-prepared candidates beyond the legacy 2..5/cN bounds and
  refuses invented ids/single-candidate sets; dp-route only names the other
  seven entries and owns no executor (a selection is not a release);
- dp-sign-key keeps ``[]`` as a real value (null/missing refused) while the
  D012A basis catalog stays a separate preparation input;
- the generated ``decide_registry.json`` equals the single-source writer output
  byte for byte and exports the retired directory as its own section.

Hermetic: read-only plus a FakeBackend client over an in-memory config; no
network, no provider, no ``.mw`` write, no service probe.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
EXPORT_PATH = PACKAGE_DIR / mw._DP_EXPORT_NAME

TARGET_EIGHT = (
    "dp-w-type",
    "dp-pm-steer",
    "dp-w-check-task",
    "dp-QG",
    "dp-gate-approve",
    "dp-sign-key",
    "dp-auto",
    "dp-route",
)
OLD_IDS_25 = (
    "dp1-dispatch-type",
    "dp2-checkpoint-split",
    "dp3-worker-clarify",
    "dp4-failure-handling",
    "dp5-test-triage",
    "dp6-qg-verdict",
    "dp7-gate-failure",
    "dp8-scope-change",
    "dp9-model-select",
    "dp10-dependency",
    "dp11-credential",
    "dp12-destructive",
    "dp13-commit-release",
    "dp14-rule-conflict",
    "dp15-autopilot-gate",
    "dp16-goal",
    "dp17-spec-lock",
    "dp18-claim",
    "dp19-foreign-write",
    "dp20-stage-close",
    "dp21-refine",
    "dp22-debug-plan",
    "dp23-snapshot",
    "dp24-pi-trust",
    "dp25-signoff-conclusion",
)
MIGRATED_SIX = {
    "dp1-dispatch-type": "dp-w-type",
    "dp2-checkpoint-split": "dp-pm-steer",
    "dp3-worker-clarify": "dp-w-check-task",
    "dp6-qg-verdict": "dp-QG",
    "dp15-autopilot-gate": "dp-gate-approve",
    "dp25-signoff-conclusion": "dp-sign-key",
}


def _auto_candidates(count: int = 3) -> list[dict]:
    ids = ("patch-now", "ask-user", "rollback", "trim-scope", "park", "renegotiate")
    return [
        {
            "id": ids[index],
            "label": f"candidate {ids[index]}",
            "description": f"prepared handling {ids[index]}",
            "consequence": f"what follows from {ids[index]}",
            "risk": "bounded by the existing write face",
            "conditions": "only inside the already granted budget",
        }
        for index in range(count)
    ]


def _material(dp_id: str) -> dict:
    """Minimal legal business material for one entry (no identity/audit keys)."""
    base: dict[str, dict] = {
        "dp-w-type": {
            "task_goal": "ship the protocol entry",
            "task_requirements": "eight entries only",
            "task_deliverables": "registry + snapshot + tests",
            "images_required": False,
        },
        "dp-pm-steer": {
            "task_goal": "converge the task",
            "task_requirements": "keep the goal",
            "task_deliverables": "a real next action",
            "pm_decision_background": "budget is tight, the main line is unchanged",
        },
        "dp-w-check-task": {
            "task_goal": "finish the assigned slice",
            "reachability_facts": "the write face is free and the budget is enough",
            "completed": "read the files",
            "remaining": "write the test",
            "blockers": "none",
            "constraints": "existing task budget only",
        },
        "dp-QG": {
            "review_requirements": "all listed acceptance checks pass",
            "review_evidence": ["cmd: python -m pytest"],
            "review_findings": "no unresolved blocking finding",
            "uncovered_scope": "live deployment is out of scope",
        },
        "dp-gate-approve": {
            "gate_background": "stage close needs one decision",
            "current_state": "required keys are signed, integration check is green",
            "condition_evidence": ["evidence/close.md:1"],
            "pm_note": {
                "subject": "close stage S1",
                "planned_action": "record the stage close only",
                "basis": {
                    "goal": "spec §1.1",
                    "evidence": "evidence/close.md:1",
                    "budget": "unchanged hard budget",
                    "authority": "existing key authorization",
                },
            },
        },
        "dp-sign-key": {
            "delivery_goal": "deliver the eight-entry protocol",
            "actual_completion": "registry and snapshot are in place",
            "verification_evidence": {"verified": [], "unverified": []},
            "unfinished_impact": [],
        },
        "dp-auto": {
            "question": "the worker hit a write-face conflict",
            "background": {
                "task_goal": "keep the task moving",
                "current_state": "the conflicting file is claimed by another key",
                "tried": "asked the other window, no answer yet",
                "unknowns": "whether the other claim is still live",
                "constraints": "no new write permission is available",
            },
            "handling_options": _auto_candidates(),
        },
        "dp-route": {
            "decision_actor": "PM",
            "decision_object": "the next step of this task",
            "question": "which entry owns this temporary question",
        },
    }
    if dp_id not in base:
        raise AssertionError(f"no base material fixture for {dp_id}")
    return json.loads(json.dumps(base[dp_id]))


def _preparation(dp_id: str, material: dict) -> dict:
    legal = list(dpts.resolve_entry_choices(dp_id, material))
    ref = next(path for path in material)
    return {
        "basis_catalog": [
            {
                "id": "b-primary",
                "text": "the prepared reason drawn from this material",
                "material_refs": [ref],
                "applies_to": legal,
            }
        ],
        "prepared_at": "2026-10-26T00:00:00Z",
    }


def _client_for(material: dict, dp_id: str) -> tuple[dict, dict, decision.DecisionClient]:
    entry = dpts.get_decision_point(dp_id)
    questions = dpts.questions_map(entry)
    state = dict(material)
    state.update(
        {
            "schema_version": dpts.STATE_SCHEMA_VERSION,
            "decision_point": dp_id,
            "questions_version": entry.questions_version,
        }
    )
    answers = {}
    for qid, spec in questions.items():
        if spec.get("dynamic_choices"):
            answers[qid] = {
                "value": material[spec["dynamic_choices"]][0]["id"],
                "confidence": 0.9,
            }
        else:
            answers[qid] = {"value": spec["choices"][0], "confidence": 0.9}
    cfg = decision.DecisionConfig(enabled=True)
    backend = decision.FakeBackend(
        [
            decision.BackendOutcome(
                available=True,
                reason=None,
                retryable=False,
                answers=answers,
                latency_ms=0,
                detail="t03 protocol probe",
            )
        ],
        name="t03-probe",
        model=cfg.model,
    )
    return state, questions, decision.DecisionClient(cfg, backend=backend)


# ---------------------------------------------------------------------------
# 1. Active set and retired directory
# ---------------------------------------------------------------------------


def test_tests_bind_the_isolated_copy_only() -> None:
    """Every import and the snapshot path must resolve inside the worktree copy."""
    package = pathlib.Path(dpts.__file__).resolve().parent
    assert package == PACKAGE_DIR
    assert PACKAGE_DIR.parents[1].name == "implementation-worktree"
    assert pathlib.Path(mw.__file__).resolve().parent == PACKAGE_DIR
    assert EXPORT_PATH.parent == PACKAGE_DIR and EXPORT_PATH.is_file()
    assert (PACKAGE_DIR / "decide_cases").is_dir()


def test_active_set_is_exactly_the_eight_targets() -> None:
    assert dpts.ACTIVE_DP_IDS == TARGET_EIGHT
    assert tuple(entry.id for entry in dpts.DP_REGISTRY) == TARGET_EIGHT
    assert dpts.EXPECTED_DP_COUNT == 8
    assert len(dpts._REGISTRY_BY_ID) == 8
    assert dpts.RETIRED_DP_IDS == frozenset(OLD_IDS_25)
    assert dpts.RETIRED_DP_IDS.isdisjoint(dpts.ACTIVE_DP_IDS)
    assert not any(entry_id.startswith(("dp1-", "dp25-")) for entry_id in dpts.ACTIVE_DP_IDS)


def test_registry_composition_is_six_migrated_nineteen_retired_two_added() -> None:
    migrated = [r for r in dpts.RETIRED_DP_REGISTRY if r.disposition == "migrated"]
    retired = [r for r in dpts.RETIRED_DP_REGISTRY if r.disposition == "retired"]
    added = [entry for entry in dpts.ACTIVE_DP_IDS if entry not in MIGRATED_SIX.values()]
    assert len(migrated) == 6
    assert len(retired) == 19
    assert added == ["dp-auto", "dp-route"]
    assert {record.id: record.migrated_to for record in migrated} == MIGRATED_SIX
    assert all(record.migrated_to is None for record in retired)


def test_retired_directory_explains_all_twenty_five_old_ids() -> None:
    assert tuple(record.id for record in dpts.RETIRED_DP_REGISTRY) == OLD_IDS_25
    for record in dpts.RETIRED_DP_REGISTRY:
        assert record.description.strip()
        assert record.note.strip()
        assert dpts.is_retired_dp(record.id) is True
        assert dpts.retired_dp(record.id) == record
        assert dpts.RETIRED_STATE_FIELDS[record.id]
    assert dpts.retired_dp("dp-w-type") is None


def test_no_retired_id_is_a_callable_alias_anywhere_in_the_active_contract() -> None:
    for entry in dpts.DP_REGISTRY:
        for question in entry.questions:
            for value in question.get("choices") or ():
                assert value not in dpts.RETIRED_DP_IDS
        assert entry.id not in dpts.RETIRED_DP_IDS
    for question in dpts.get_decision_point("dp-route").questions:
        assert not set(question["choices"]) & dpts.RETIRED_DP_IDS


# ---------------------------------------------------------------------------
# 2. Old ids are refused before any model call / business action
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("old_id", OLD_IDS_25)
def test_every_old_id_is_refused_by_the_runtime_resolver(old_id: str) -> None:
    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.get_decision_point(old_id)
    message = str(excinfo.value)
    assert "retired decision point id" in message
    assert "not callable" in message
    with pytest.raises(decision.DecisionInputError):
        dpts.require_active_dp(old_id)


@pytest.mark.parametrize("old_id", OLD_IDS_25)
def test_every_old_id_is_refused_before_the_backend_and_executor(old_id: str, tmp_path) -> None:
    _state, _questions, client = _client_for(_material("dp-w-type"), "dp-w-type")
    backend = client.backend
    trigger = dpts.Trigger(trigger_id=f"replay-{old_id}", key="mw-dp-consolidation")
    with pytest.raises(decision.DecisionInputError):
        dpts.decide_for(old_id, trigger, tmp_path, client=client, archive=False)
    assert backend.calls == [], f"{old_id}: a retired id reached the backend"


def test_retired_rejection_does_not_migrate_to_an_alias() -> None:
    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.require_active_dp("dp3-worker-clarify")
    assert "dp-w-check-task" not in str(excinfo.value)
    with pytest.raises(decision.DecisionInputError):
        dpts.require_active_dp("dp-unknown")


# ---------------------------------------------------------------------------
# 3. Roles, frozen choices and answer rendering
# ---------------------------------------------------------------------------


def test_roles_are_eligibility_only() -> None:
    assert dpts.ACTOR_ROLES == ("pm", "worker")
    for entry_id in dpts.ACTIVE_DP_IDS:
        assert dpts.role_issues(entry_id, dpts.ENTRY_ROLES[entry_id]) == ()
        wrong = "worker" if dpts.ENTRY_ROLES[entry_id] == "pm" else "pm"
        issues = dpts.role_issues(entry_id, wrong)
        assert issues and "role-forbidden" in issues[0][1], entry_id
        for unknown_role in ("agent", "human", "system", "", None):
            assert dpts.role_issues(entry_id, unknown_role), entry_id
    assert dpts.ENTRY_ROLES["dp-w-check-task"] == "worker"
    assert dpts.ENTRY_ROLES["dp-route"] == "pm"


def test_route_selection_does_not_grant_the_target_role() -> None:
    route_issues = dpts.entry_choice_issues("dp-route", "dp-w-check-task", _material("dp-route"))
    assert route_issues == ()
    # The route only names the entry; the target's own role check still applies.
    assert dpts.role_issues("dp-w-check-task", "pm")


def test_fixed_choice_ids_are_frozen_and_single_sourced() -> None:
    expected = {
        "dp-w-type": ("coding", "research", "review", "vision"),
        "dp-pm-steer": ("narrow", "split", "direct-exec", "escalate"),
        "dp-w-check-task": ("continue", "terminate", "investigate"),
        "dp-QG": ("pass", "fix", "reopen"),
        "dp-gate-approve": ("approve", "steer", "need_fix", "reject"),
        "dp-sign-key": ("finalize", "continue", "user-confirm"),
    }
    for entry_id, choices in expected.items():
        entry = dpts.get_decision_point(entry_id)
        assert dpts.ENTRY_CHOICES[entry_id] == choices
        assert entry.kind == "fixed"
        assert entry.candidate_source == "static-enum"
        assert entry.questions[0]["choices"] == list(choices)
        assert tuple(dpts.resolve_entry_choices(entry_id)) == choices


def test_w_check_task_has_three_fixed_choices_not_the_legacy_dynamic_surface() -> None:
    entry = dpts.get_decision_point("dp-w-check-task")
    question = entry.questions[0]
    assert question["type"] == "choice"
    assert question.get("dynamic_choices") is None
    assert question["choices"] == ["continue", "terminate", "investigate"]
    material = _material("dp-w-check-task")
    for choice in ("continue", "terminate"):
        assert dpts.entry_choice_issues("dp-w-check-task", choice, material) == ()
    issues = dpts.entry_choice_issues("dp-w-check-task", "investigate", material)
    assert {path for path, _detail in issues} == {
        "investigation.unknown",
        "investigation.evidence_source",
        "investigation.budget",
        "investigation.stop_condition",
    }
    plan = dict(material)
    plan.update(
        {
            "investigation": {
                "unknown": "which side owns the conflicting path",
                "evidence_source": "the claim index of the other key",
                "budget": "10 minutes of the existing task budget",
                "stop_condition": "the owner is named, or the index is missing",
            }
        }
    )
    assert dpts.entry_choice_issues("dp-w-check-task", "investigate", plan) == ()
    assert dpts.entry_choice_issues("dp-w-check-task", "stop-with-conclusion", material)


def test_qg_three_conclusions_with_conditional_basis() -> None:
    material = _material("dp-QG")
    for choice in ("pass", "fix"):
        assert dpts.entry_choice_issues("dp-QG", choice, material) == ()
    missing = dpts.entry_choice_issues("dp-QG", "reopen", material)
    assert missing and missing[0][0] == "basis_issue"
    with_issue = dict(material)
    with_issue["basis_issue"] = "the acceptance criterion contradicts the locked spec"
    assert dpts.entry_choice_issues("dp-QG", "reopen", with_issue) == ()
    assert dpts.entry_choice_issues("dp-QG", "pass", with_issue)
    assert dpts.entry_choice_issues("dp-QG", "approve", material)


def test_w_type_four_types_and_the_image_gate() -> None:
    material = _material("dp-w-type")
    assert dpts.ENTRY_CHOICES["dp-w-type"] == ("coding", "research", "review", "vision")
    needs_images = dict(material)
    needs_images["images_required"] = True
    assert dpts.vision_dispatch_issues(needs_images, "vision", "proven") == ()
    assert dpts.vision_dispatch_issues(needs_images, "vision", "unknown")
    assert dpts.vision_dispatch_issues(needs_images, "vision", "unproven")
    assert dpts.vision_dispatch_issues(needs_images, "coding", "proven")
    assert dpts.vision_dispatch_issues(material, "vision", "proven")
    assert dpts.vision_dispatch_issues(material, "coding", "unproven") == ()
    # Existing non-menu framework task types stay documented (nothing was removed).
    assert "rag-research" in dpts.STATE_FIELD_DESCRIPTIONS["task_type"]["description"]


# ---------------------------------------------------------------------------
# 4. dp-auto: PM-prepared candidates, no legacy 2..5/cN
# ---------------------------------------------------------------------------


def test_auto_has_no_static_menu_and_no_legacy_bounds() -> None:
    entry = dpts.get_decision_point("dp-auto")
    assert entry.kind == "dynamic-candidates"
    assert entry.candidate_source == "pm-supplied:handling_options"
    assert entry.questions[0]["dynamic_choices"] == "handling_options"
    bounds = dict(entry.candidate_bounds or {})
    assert bounds == {"min": 2, "max": None, "id_scheme": "free"}
    assert dpts.ENTRY_CHOICES["dp-auto"] == ()
    # The legacy cN/2..5 validator is untouched history; the new rule is not it.
    six = _auto_candidates(6)
    assert dpts.dynamic_choices_value_error(six), "fixture must be illegal for the old rule"
    assert dpts.entry_candidates_issues("dp-auto", six) == ()


def test_auto_accepts_free_ids_and_refuses_invented_choices() -> None:
    material = _material("dp-auto")
    material["handling_options"] = _auto_candidates(6)
    legal = dpts.resolve_entry_choices("dp-auto", material)
    assert legal == tuple(candidate["id"] for candidate in material["handling_options"])
    for candidate_id in legal:
        assert dpts.entry_choice_issues("dp-auto", candidate_id, material) == ()
    assert dpts.entry_choice_issues("dp-auto", "c7", material)
    assert dpts.entry_choice_issues("dp-auto", "", material)
    assert dpts.entry_choice_issues("dp-auto", None, material)
    single = dict(material)
    single["handling_options"] = _auto_candidates(1)
    assert dpts.entry_choice_issues("dp-auto", "patch-now", single)
    duplicate = _auto_candidates(2)
    duplicate[1]["id"] = duplicate[0]["id"]
    assert dpts.pm_candidate_issues(duplicate)
    missing_consequence = _auto_candidates(2)
    missing_consequence[0].pop("consequence")
    assert dpts.pm_candidate_issues(missing_consequence)
    extra_key = _auto_candidates(2)
    extra_key[0]["probability"] = "0.9"
    assert dpts.pm_candidate_issues(extra_key)


# ---------------------------------------------------------------------------
# 5. dp-route: seven targets, no business release
# ---------------------------------------------------------------------------


def test_route_targets_are_the_other_seven_entries() -> None:
    assert dpts.ROUTE_TARGETS == tuple(
        entry for entry in TARGET_EIGHT if entry != "dp-route"
    )
    assert len(dpts.ROUTE_TARGETS) == 7
    assert "dp-route" not in dpts.ROUTE_TARGETS
    entry = dpts.get_decision_point("dp-route")
    assert entry.kind == "route-targets"
    assert entry.target_entries == dpts.ROUTE_TARGETS
    assert entry.questions[0]["choices"] == list(dpts.ROUTE_TARGETS)
    material = _material("dp-route")
    for target in dpts.ROUTE_TARGETS:
        assert dpts.entry_choice_issues("dp-route", target, material) == ()
    assert dpts.entry_choice_issues("dp-route", "dp-route", material)
    assert dpts.entry_choice_issues("dp-route", "dp1-dispatch-type", material)
    assert dpts.entry_choice_issues("dp-route", "approve", material)


def test_route_and_auto_own_no_executor_so_a_selection_cannot_release() -> None:
    for entry_id in ("dp-route", "dp-auto"):
        entry = dpts.get_decision_point(entry_id)
        assert entry.executor is not None
        assert getattr(entry.executor, "unwired", False) is True
        with pytest.raises(NotImplementedError):
            entry.executor({}, dpts.Trigger())
    assert dpts._executor_kind(dpts.get_decision_point("dp-sign-key").executor) == "wired"


# ---------------------------------------------------------------------------
# 6. Materials, sign-key arrays and the separate D012A basis
# ---------------------------------------------------------------------------


def test_every_entry_material_contract_is_declared_typed_and_satisfiable() -> None:
    for entry_id in dpts.ACTIVE_DP_IDS:
        material = _material(entry_id)
        assert dpts.entry_material_issues(entry_id, material) == (), entry_id
        required = dpts.REQUIRED_STATE_FIELDS[entry_id]
        assert required
        for path in required:
            assert path in dpts.STATE_FIELD_DESCRIPTIONS
        for path in required:
            broken = json.loads(json.dumps(material))
            parts = path.split(".")
            node = broken
            for part in parts[:-1]:
                node = node[part]
            node.pop(parts[-1])
            issues = dpts.entry_material_issues(entry_id, broken)
            assert any(issue_path == path for issue_path, _ in issues), (entry_id, path)


@pytest.mark.parametrize("entry_id", dpts.ACTIVE_DP_IDS)
def test_every_entry_material_is_refused_when_illegal(entry_id: str) -> None:
    material = _material(entry_id)
    assert dpts.entry_material_issues(entry_id, None)
    assert dpts.entry_material_issues(entry_id, "not-an-object")
    unknown = json.loads(json.dumps(material))
    unknown["basis_catalog"] = []
    assert any(
        "basis_catalog" in issue_path
        for issue_path, _detail in dpts.entry_material_issues(entry_id, unknown)
    )
    prepared = json.loads(json.dumps(material))
    prepared["preparation"] = {"basis_catalog": []}
    assert any(
        "preparation" in issue_path
        for issue_path, _detail in dpts.entry_material_issues(entry_id, prepared)
    )
    wrong_type = json.loads(json.dumps(material))
    first = dpts.REQUIRED_STATE_FIELDS[entry_id][0]
    node = wrong_type
    parts = first.split(".")
    for part in parts[:-1]:
        node = node[part]
    node[parts[-1]] = 17
    assert dpts.entry_material_issues(entry_id, wrong_type)


def test_sign_key_keeps_empty_arrays_and_refuses_null_or_missing() -> None:
    material = _material("dp-sign-key")
    assert dpts.entry_material_issues("dp-sign-key", material) == ()
    for choice in ("finalize", "continue", "user-confirm"):
        assert dpts.entry_choice_issues("dp-sign-key", choice, material) == ()
    for path in (
        "verification_evidence.verified",
        "verification_evidence.unverified",
        "unfinished_impact",
    ):
        broken = json.loads(json.dumps(material))
        node = broken
        parts = path.split(".")
        for part in parts[:-1]:
            node = node[part]
        node[parts[-1]] = None
        issues = dpts.entry_material_issues("dp-sign-key", broken)
        assert any(issue_path == path for issue_path, _ in issues), path
    assert dpts.STATE_FIELD_DESCRIPTIONS["verification_evidence.verified"]["empty_is_value"] is True
    assert dpts.STATE_FIELD_DESCRIPTIONS["verification_evidence.unverified"]["empty_is_value"] is True
    assert dpts.STATE_FIELD_DESCRIPTIONS["unfinished_impact"]["empty_is_value"] is True


def test_gate_pm_note_is_its_own_input_and_never_the_model_basis() -> None:
    material = _material("dp-gate-approve")
    assert dpts.pm_note_issues(material["pm_note"]) == ()
    broken = json.loads(json.dumps(material))
    broken["pm_note"]["basis"].pop("authority")
    issues = dpts.entry_material_issues("dp-gate-approve", broken)
    assert any(issue_path == "pm_note.basis.authority" for issue_path, _ in issues)
    extra = json.loads(json.dumps(material))
    extra["pm_note"]["reason"] = "the model should say this"
    assert dpts.entry_material_issues("dp-gate-approve", extra)
    for choice in ("approve", "steer", "need_fix", "reject"):
        assert dpts.entry_choice_issues("dp-gate-approve", choice, material) == ()
    # A catalog item is prepared text, not a failure reason/probability.
    catalog = _preparation("dp-gate-approve", material)["basis_catalog"]
    assert dpts.basis_catalog_issues("dp-gate-approve", catalog, material) == ()
    polluted = json.loads(json.dumps(catalog))
    polluted[0]["probability"] = 0.9
    assert dpts.basis_catalog_issues("dp-gate-approve", polluted, material)


@pytest.mark.parametrize("entry_id", dpts.ACTIVE_DP_IDS)
def test_preparation_is_required_complete_and_separate(entry_id: str) -> None:
    material = _material(entry_id)
    preparation = _preparation(entry_id, material)
    assert dpts.preparation_issues(entry_id, preparation, material) == ()
    assert dpts.preparation_issues(entry_id, None, material)
    no_catalog = {"prepared_at": "2026-10-26T00:00:00Z"}
    assert dpts.preparation_issues(entry_id, no_catalog, material)
    no_time = {"basis_catalog": preparation["basis_catalog"]}
    assert dpts.preparation_issues(entry_id, no_time, material)
    extra = dict(preparation)
    extra["note"] = "not part of D012A"
    assert dpts.preparation_issues(entry_id, extra, material)
    legal = dpts.resolve_entry_choices(entry_id, material)
    choice = legal[0]
    assert dpts.preparation_issues(
        entry_id, preparation, material, choice=choice, basis_id="b-primary"
    ) == ()
    assert dpts.basis_selection_issues("missing", preparation["basis_catalog"], choice)
    assert dpts.basis_selection_issues("b-primary", preparation["basis_catalog"], "invented")


def test_basis_catalog_rejects_unprepared_or_unreferenced_reasons() -> None:
    material = _material("dp-w-type")
    good = _preparation("dp-w-type", material)["basis_catalog"]
    assert dpts.basis_catalog_issues("dp-w-type", good, material) == ()
    assert dpts.basis_catalog_issues("dp-w-type", [], material)
    duplicate = json.loads(json.dumps(good)) * 2
    assert dpts.basis_catalog_issues("dp-w-type", duplicate, material)
    unreferenced = json.loads(json.dumps(good))
    unreferenced[0]["material_refs"] = ["not.a.real.path"]
    issues = dpts.basis_catalog_issues("dp-w-type", unreferenced, material)
    assert any("material_refs" in issue_path for issue_path, _ in issues)
    bad_choice = json.loads(json.dumps(good))
    bad_choice[0]["applies_to"] = ["dp-route"]
    assert dpts.basis_catalog_issues("dp-w-type", bad_choice, material)
    empty_text = json.loads(json.dumps(good))
    empty_text[0]["text"] = ""
    assert dpts.basis_catalog_issues("dp-w-type", empty_text, material)


# ---------------------------------------------------------------------------
# 7. All eight entries: prepared request gate and failure contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("entry_id", dpts.ACTIVE_DP_IDS)
def test_prepared_request_passes_for_the_legal_fixture(entry_id: str) -> None:
    material = _material(entry_id)
    preparation = _preparation(entry_id, material)
    choice = dpts.resolve_entry_choices(entry_id, material)[0]
    issues = dpts.prepared_request_issues(
        entry_id,
        material,
        preparation,
        actor_role=dpts.ENTRY_ROLES[entry_id],
        choice=choice,
        basis_id="b-primary",
    )
    assert issues == (), (entry_id, issues)


@pytest.mark.parametrize("entry_id", dpts.ACTIVE_DP_IDS)
def test_every_entry_fails_closed_without_a_default(entry_id: str) -> None:
    material = _material(entry_id)
    preparation = _preparation(entry_id, material)
    wrong_role = "worker" if dpts.ENTRY_ROLES[entry_id] == "pm" else "pm"
    assert dpts.prepared_request_issues(
        entry_id,
        {},
        preparation,
        actor_role=dpts.ENTRY_ROLES[entry_id],
        choice=dpts.resolve_entry_choices(entry_id, material)[0],
        basis_id="b-primary",
    )
    assert dpts.prepared_request_issues(
        entry_id, material, preparation, actor_role=wrong_role
    )
    assert dpts.prepared_request_issues(entry_id, material, None)
    assert dpts.entry_choice_issues(entry_id, "", material)
    assert dpts.entry_choice_issues(entry_id, "definitely-not-a-choice", material)
    # A missing selection is never coerced to the first legal id or to approve.
    assert dpts.entry_choice_issues(entry_id, None, material)


def test_all_entries_render_through_the_decision_client() -> None:
    for entry_id in dpts.ACTIVE_DP_IDS:
        material = _material(entry_id)
        state, questions, client = _client_for(material, entry_id)
        response = client.decide(state, questions, dp=entry_id)
        assert response["available"] is True, (entry_id, response["reason"])
        assert set(response["answers"]) == {str(qid) for qid in questions}


# ---------------------------------------------------------------------------
# 8. Generated snapshot: one writer, eight points, separate retired section
# ---------------------------------------------------------------------------


def test_snapshot_json_is_the_single_source_writer_output() -> None:
    doc = json.loads(EXPORT_PATH.read_text(encoding="utf-8"))
    assert doc == dpts.registry_snapshot()
    assert EXPORT_PATH.read_text(encoding="utf-8") == dpts.registry_snapshot_text(doc)
    assert doc["schema"] == dpts.SNAPSHOT_SCHEMA == 4
    assert [point["id"] for point in doc["points"]] == list(TARGET_EIGHT)
    assert set(doc) == {
        "schema",
        "generated_from",
        "question_types",
        "preparation",
        "points",
        "retired",
    }
    assert [record["id"] for record in doc["retired"]] == list(OLD_IDS_25)
    assert not set(point["id"] for point in doc["points"]) & set(
        record["id"] for record in doc["retired"]
    )


def test_snapshot_exports_the_protocol_identity_per_entry() -> None:
    doc = json.loads(EXPORT_PATH.read_text(encoding="utf-8"))
    assert doc["preparation"] == {
        "keys": list(dpts.PREPARATION_KEYS),
        "basis_item_keys": list(dpts.BASIS_ITEM_KEYS),
        "basis_source": dpts.BASIS_SOURCE,
        "independent_of": "material",
    }
    for point, entry in zip(doc["points"], dpts.DP_REGISTRY):
        assert point["id"] == entry.id
        assert point["kind"] == entry.kind
        assert point["role_scope"] == entry.role_scope
        assert point["candidate_source"] == entry.candidate_source
        assert point["target_entries"] == list(entry.target_entries)
        assert point["candidate_bounds"] == (
            None if entry.candidate_bounds is None else dict(entry.candidate_bounds)
        )
        assert point["executor"] == dpts._executor_kind(entry.executor)
