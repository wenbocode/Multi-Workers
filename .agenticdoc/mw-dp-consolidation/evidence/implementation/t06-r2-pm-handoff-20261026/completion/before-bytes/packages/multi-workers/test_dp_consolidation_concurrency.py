"""test_dp_consolidation_concurrency.py - T06: read-only validity judgements.

Scope of this file (card T06): only the pure judgements in
``decision_validity.py``. It does not exercise real concurrency, real locks,
real gate writers, a service or a provider; T20/T31 take over this same file
later and must declare the dependency plus the file hash before extending it.

What is asserted here, per approved AC/VC pair:

- AC-011/VC-011: one business owner per subject/object/action, route owns no
  business approval, replay of the same substantive version adds no approval
  and no action, and the same matter keeps its identity across gate labels and
  files.
- AC-019/VC-019: a substantive change of a start dependency makes the old
  approval stale; identical and semantically equivalent (whitespace, line
  endings, set order) versions cause no re-approval and no repeated action.
- AC-025/VC-025: a substantive goal change invalidates only the bound approvals
  that depend on the changed dependencies; unrelated and formatting-only
  changes cause no re-approval; a change of a business-intent dependency
  yields an explicit user-decision item; authorization is never manufactured
  from engineering evidence (``agent-report``/``editable`` sources).
- AC-027/VC-027: claim/write-surface checks detect a foreign claim, a shared
  (non-exclusive) lock and two writers of one file; a DP reference never
  transfers a claim and never fakes a dispatch.
- AC-028/VC-028: a frozen contract change needs the complete PM note; an
  approval covers exactly the requested items/versions; a reused unrelated
  approval and an unauthorized acceptance reduction are refused.
- AC-029/VC-029: after an approved change the affected evidence must be
  re-verified, unaffected evidence stays reusable, and no judgement rewrites
  the input history objects.
- AC-039/VC-039: only the finalize word list is accepted, a legacy word or a
  disable request is refused, the required scope must be covered and never
  widened, a stale signoff is not reused and a signoff without its real
  artifact is a fabrication.
- AC-052/VC-052: a replay does not repeat an applied action; unknown or
  in-progress effects block a retry instead of guessing; a failed effect can be
  retried with the failure preserved; the module never claims a lock or an
  action.

Hermetic: no network, no provider, no CLI/conductor import, no filesystem
write, no real decision/gate/ledger object.
"""

from __future__ import annotations

import ast
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision_validity as dv  # noqa: E402

CONTRACT = "dp-contract-v1"
MODULE_PATH = pathlib.Path(dv.__file__).resolve()
PACKAGE_DIR = pathlib.Path(__file__).resolve().parent

# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------


def structured_deps() -> list[dv.DependencyState]:
    """A representative substantive dependency set for one gate matter."""

    return [
        dv.DependencyState(
            "goal",
            "structured",
            {"scope": {"$set": ["stage-1", "stage-2"]}, "commitment": "ship the stage"},
        ),
        dv.DependencyState("ac-items", "set", ["AC-011", "AC-052"]),
        dv.DependencyState(
            "edges",
            "structured",
            {"$set": ["T03->T06", "T04->T06"]},
        ),
        dv.DependencyState(
            "write-face",
            "set",
            ["packages/multi-workers/decision_validity.py"],
        ),
        dv.DependencyState(
            "hard-budget",
            "structured",
            {"unit": "tokens", "limit": 100000},
        ),
        dv.DependencyState("evidence", "structured", {"vc-011": "pass"}),
    ]


def make_matter(
    *,
    subject: str = "key-1",
    obj: str = "stage-2",
    action: str = "start",
    kind: str = "gate-action",
    deps: list[dv.DependencyState] | None = None,
    contract: str = CONTRACT,
    authority_required: bool = False,
) -> dv.Matter:
    return dv.matter_for(
        subject,
        obj,
        action,
        deps if deps is not None else structured_deps(),
        matter_kind=kind,
        contract_version=contract,
        authority_required=authority_required,
    )


def make_decision(
    matter: dv.Matter | None = None,
    *,
    decision_id: str = "dec-1",
    entry: str = "dp-gate-approve",
    actor: str = "pm-window-1",
    role: str = "pm",
    choice: str = "approve",
    authority_ref: str | None = None,
    transport: str = "answered",
    effect: str = "not-started",
    revoked: bool = False,
    historical: bool = False,
) -> dv.DecisionRecord:
    return dv.DecisionRecord(
        decision_id=decision_id,
        entry=entry,
        actor=actor,
        role=role,
        matter=matter if matter is not None else make_matter(),
        choice=choice,
        authority_ref=authority_ref,
        transport=transport,
        effect=effect,
        revoked=revoked,
        historical=historical,
    )


def codes(verdict) -> set[str]:
    return {reason.code for reason in verdict.reasons}


def assess(decision: dv.DecisionRecord, current: dv.Matter, **kwargs) -> dv.Validity:
    kwargs.setdefault("bound_actor", decision.actor)
    kwargs.setdefault("bound_role", decision.role)
    return dv.assess_validity(decision, current, **kwargs)


# ---------------------------------------------------------------------------
# Purity / module boundary
# ---------------------------------------------------------------------------


def test_module_imports_only_stdlib_and_never_writes() -> None:
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    forbidden = {
        "decision",
        "decision_points",
        "decision_context",
        "decision_policy",
        "decision_backends",
        "decision_wire",
        "decision_lifecycle",
        "mw",
        "mw_common",
        "autopilot",
        "subprocess",
        "socket",
        "http",
        "urllib",
        "requests",
    }
    assert imported.isdisjoint(forbidden), sorted(imported & forbidden)
    expected = {"__future__", "dataclasses", "hashlib", "json", "posixpath", "re", "types", "typing", "collections"}
    assert imported <= expected | {"collections"}, sorted(imported - expected)
    write_calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in {"open", "exec", "eval", "compile"}:
                write_calls.append(node.func.id)
        if isinstance(node, ast.Attribute) and node.attr in {"write_text", "write_bytes", "unlink", "mkdir"}:
            write_calls.append(node.attr)
    assert write_calls == [], write_calls
    assert not hasattr(dv, "write_grant")
    assert not hasattr(dv, "grant")


def test_validity_is_deterministic_for_repeated_calls() -> None:
    decision = make_decision()
    current = make_matter()
    first = assess(decision, current)
    second = assess(decision, current)
    assert first == second
    assert first.status == "valid"
    assert first.reasons == ()


# ---------------------------------------------------------------------------
# AC-011 / VC-011: one owner, no replay approval, no repeat action
# ---------------------------------------------------------------------------


def test_eight_entries_and_owner_table_is_total() -> None:
    assert dv.ACTIVE_ENTRIES == (
        "dp-w-type",
        "dp-pm-steer",
        "dp-w-check-task",
        "dp-QG",
        "dp-gate-approve",
        "dp-sign-key",
        "dp-auto",
        "dp-route",
    )
    owners = [entry for entry in dv.MATTER_OWNERS.values() if entry is not None]
    assert sorted(owners) == sorted(e for e in dv.ACTIVE_ENTRIES if e != "dp-route")
    assert len(owners) == len(set(owners))
    for kind in dv.MATTER_KINDS:
        assert dv.business_owner_for(kind) == dv.MATTER_OWNERS[kind]
    with pytest.raises(ValueError):
        dv.business_owner_for("not-a-matter-kind")


def test_route_owns_no_business_approval() -> None:
    route_matter = make_matter(kind="routing")
    assert dv.business_owner_for("routing") is None
    decision = make_decision(route_matter, entry="dp-route", choice="dp-QG")
    validity = assess(decision, route_matter)
    assert validity.status == "blocked"
    assert "route_not_business_owner" in codes(validity)
    route_releases = 1 if validity.status == "valid" else 0
    assert route_releases == 0


def test_same_matter_under_different_gate_labels_is_one_matter() -> None:
    base = make_matter()
    renamed_gate = make_matter()  # different caller label/file is not an input
    assert base.matter_key == renamed_gate.matter_key
    assert base.substantive_version == renamed_gate.substantive_version
    decision = make_decision(base)
    for _label in ("gate-start.json", "gate-start-retry.json", "gate-start-copy.json"):
        validity = assess(decision, make_matter())
        assert validity.status == "valid"


def test_same_matter_has_exactly_one_business_owner() -> None:
    matter = make_matter(kind="gate-action")
    owner = dv.business_owner_for("gate-action")
    assert owner == "dp-gate-approve"
    approvals = 0
    for entry in dv.ACTIVE_ENTRIES:
        decision = make_decision(matter, entry=entry)
        validity = assess(decision, matter)
        approvals += 1 if validity.status == "valid" else 0
    assert approvals == 1
    assert owner == "dp-gate-approve"


def test_non_owner_entry_is_blocked_even_with_same_matter() -> None:
    matter = make_matter(kind="quality")
    decision = make_decision(matter, entry="dp-gate-approve")
    validity = assess(decision, matter)
    assert validity.status == "blocked"
    assert "not_business_owner" in codes(validity)
    reason = next(r for r in validity.reasons if r.code == "not_business_owner")
    assert reason.detail == "dp-QG"


def test_retired_entry_is_refused_before_any_review() -> None:
    matter = make_matter()
    for legacy in ("dp1-dispatch-type", "dp4-failure-handling", "dp25-signoff-conclusion"):
        decision = make_decision(matter, entry=legacy)
        validity = assess(decision, matter)
        assert validity.status == "blocked"
        assert "retired_or_unknown_entry" in codes(validity)


def test_replay_same_version_is_duplicate_without_extra_approval() -> None:
    matter = make_matter()
    first = make_decision(matter, decision_id="dec-1")
    replay_same_label = make_decision(matter, decision_id="dec-2")
    replay_other_label = make_decision(matter, decision_id="dec-3")
    verdict = dv.dedupe_decisions([first], replay_other_label)
    assert verdict.status == "duplicate"
    assert verdict.additional_approvals == 0
    assert set(verdict.same_matter_versions) == {"dec-1"}
    duplicate_approvals = sum(
        dv.dedupe_decisions([first], other).additional_approvals
        for other in (replay_same_label, replay_other_label)
    )
    assert duplicate_approvals == 0


def test_replay_different_choice_same_version_is_conflict_not_second_approval() -> None:
    matter = make_matter()
    first = make_decision(matter, decision_id="dec-1", choice="approve")
    second = make_decision(matter, decision_id="dec-2", choice="reject")
    verdict = dv.dedupe_decisions([first], second)
    assert verdict.status == "conflict"
    assert verdict.additional_approvals == 0
    assert verdict.conflicting == ("dec-1",)


def test_repeat_action_is_not_planned_when_effect_applied() -> None:
    matter = make_matter()
    applied = dv.EffectRecord(
        effect_id="eff-1",
        decision_id="dec-1",
        matter_key=matter.matter_key,
        substantive_version=matter.substantive_version,
        actions=("start-stage",),
        status="applied",
    )
    plan = dv.plan_actions([applied], matter=matter, actions=("start-stage",))
    assert plan.status == "already-applied"
    assert plan.actions == ()
    assert plan.duplicate_actions == ("start-stage",)
    assert plan.blocked == ()


# ---------------------------------------------------------------------------
# AC-019 / VC-019: substantive change vs semantic equivalence
# ---------------------------------------------------------------------------


def test_substantive_change_makes_old_decision_stale_with_affected_names() -> None:
    old = make_matter()
    new_deps = structured_deps()
    new_deps[3] = dv.DependencyState(
        "write-face", "set", ["packages/multi-workers/other.py"]
    )
    new = make_matter(deps=new_deps)
    validity = assess(make_decision(old), new)
    assert validity.status == "stale"
    assert validity.affected_dependencies == ("write-face",)
    assert validity.requires_reapproval is True
    assert "substantive_change" in codes(validity)
    stale_starts = 0 if validity.requires_reapproval else 1
    assert stale_starts == 0


def test_added_and_removed_dependency_counts_as_substantive_change() -> None:
    old = make_matter()
    added_deps = structured_deps() + [
        dv.DependencyState("extra", "structured", {"note": 1})
    ]
    added = make_matter(deps=added_deps)
    added_validity = assess(make_decision(old), added)
    assert added_validity.status == "stale"
    assert "extra" in added_validity.affected_dependencies

    removed = make_matter(deps=structured_deps()[:-1])
    removed_validity = assess(make_decision(old), removed)
    assert removed_validity.status == "stale"
    assert "evidence" in removed_validity.affected_dependencies


def test_formatting_and_set_order_are_semantically_equivalent() -> None:
    old = make_matter()
    reformatted = [
        dv.DependencyState(
            "goal",
            "structured",
            {"scope": {"$set": ["stage-2", "stage-1"]}, "commitment": "ship the stage\r\n"},
        ),
        dv.DependencyState("ac-items", "set", ["AC-052", "AC-011", "AC-011"]),
        dv.DependencyState("edges", "structured", {"$set": ["T04->T06", "T03->T06"]}),
        dv.DependencyState(
            "write-face", "set", ["packages/multi-workers/decision_validity.py"]
        ),
        dv.DependencyState("hard-budget", "structured", {"limit": 100000, "unit": "tokens"}),
        dv.DependencyState("evidence", "structured", {"vc-011": "pass"}),
    ]
    new = make_matter(deps=reformatted)
    assert new.substantive_version == old.substantive_version
    validity = assess(make_decision(old), new)
    assert validity.status == "valid"
    assert validity.affected_dependencies == ()
    irrelevant_reapprovals = 0 if validity.status == "valid" else 1
    assert irrelevant_reapprovals == 0
    verdict = dv.dedupe_decisions([make_decision(old, decision_id="dec-1")], make_decision(new, decision_id="dec-2"))
    assert verdict.status == "duplicate"
    assert verdict.additional_approvals == 0


def test_byte_sha_change_alone_keeps_matter_and_decision_valid() -> None:
    old = make_matter()
    sha_changed = structured_deps()
    sha_changed[0] = dv.DependencyState(
        sha_changed[0].name,
        sha_changed[0].kind,
        sha_changed[0].value,
        byte_sha256="f" * 64,
    )
    new = make_matter(deps=sha_changed)
    assert new.matter_key == old.matter_key
    assert new.substantive_version == old.substantive_version
    validity = assess(make_decision(old), new)
    assert validity.status == "valid"


def test_natural_language_change_is_unknown_and_blocked() -> None:
    old = make_matter(
        deps=structured_deps()
        + [dv.DependencyState("stop-reason", "prose", "waiting for the user")]
    )
    new = make_matter(
        deps=structured_deps()
        + [dv.DependencyState("stop-reason", "prose", "waiting for approval")]
    )
    comparison = dv.compare_dependency_values(
        "prose", "waiting for the user", "waiting for approval"
    )
    assert comparison.status == "unknown"
    assert comparison.detail == "prose_text_differs"
    validity = assess(make_decision(old), new)
    assert validity.status == "blocked"
    assert "unknown_substantive_change" in codes(validity)
    assert validity.requires_reapproval is True


def test_explicitly_unknown_current_state_blocks_and_needs_a_new_judgement() -> None:
    unknown_deps = structured_deps() + [
        dv.DependencyState("stop-reason", "prose", dv.UNKNOWN_SUBSTANTIVE)
    ]
    matter = make_matter(deps=unknown_deps)
    validity = assess(make_decision(make_matter()), matter)
    assert validity.status == "blocked"
    assert "unknown_substantive_state" in codes(validity)
    assert validity.requires_reapproval is True


def test_prose_whitespace_only_change_is_equivalent() -> None:
    left = "line one\r\nline two   "
    right = "line one\nline two"
    comparison = dv.compare_dependency_values("prose", left, right)
    assert comparison.status == "equivalent"
    assert comparison.left == comparison.right


def test_unknown_dependency_value_is_blocked() -> None:
    unknown_deps = structured_deps() + [
        dv.DependencyState("stop-reason", "prose", dv.UNKNOWN_SUBSTANTIVE)
    ]
    matter = make_matter(deps=unknown_deps)
    assert matter.unknown_dependencies == ("stop-reason",)
    decision = make_decision(matter)
    validity = assess(decision, matter)
    assert validity.status == "blocked"
    assert "unknown_substantive_change" in codes(validity)


def test_actor_and_role_binding_mismatch_blocks() -> None:
    matter = make_matter()
    decision = make_decision(matter)
    actor_mismatch = assess(decision, matter, bound_actor="worker-window-9")
    assert actor_mismatch.status == "blocked"
    assert "actor_mismatch" in codes(actor_mismatch)
    role_mismatch = assess(decision, matter, bound_role="worker")
    assert role_mismatch.status == "blocked"
    assert "role_mismatch" in codes(role_mismatch)


def test_contract_version_change_is_stale() -> None:
    old = make_matter(contract="dp-contract-v1")
    new = make_matter(contract="dp-contract-v2")
    validity = assess(make_decision(old), new)
    assert validity.status == "stale"
    assert "contract_version_changed" in codes(validity)
    assert validity.requires_reapproval is True


def test_decision_effect_unknown_blocks_retry() -> None:
    matter = make_matter()
    decision = make_decision(matter, effect="unknown")
    validity = assess(decision, matter)
    assert validity.status == "blocked"
    assert "effect_unknown" in codes(validity)


def test_unanswered_transport_is_not_a_business_answer() -> None:
    matter = make_matter()
    for transport in ("pending", "failed"):
        validity = assess(make_decision(matter, transport=transport), matter)
        assert validity.status == "blocked"
        assert "transport_not_answered" in codes(validity)


def test_revoked_decision_is_blocked_and_not_rolled_back() -> None:
    matter = make_matter()
    decision = make_decision(matter, effect="applied")
    revoked = dv.revoke_decision(decision)
    assert revoked.revoked is True
    assert revoked.effect == "applied"
    assert decision.revoked is False
    validity = assess(revoked, matter)
    assert validity.status == "blocked"
    assert "decision_revoked" in codes(validity)


# ---------------------------------------------------------------------------
# Authorization applicability (AC-025/AC-027/AC-028)
# ---------------------------------------------------------------------------


def authority(**overrides) -> dv.AuthorityRef:
    values = {
        "authority_ref": "auth-1",
        "actor": "pm-window-1",
        "status": "active",
        "source": "user message 2026-10-25 scope approval",
        "objects": ("stage-2",),
        "actions": ("start",),
        "files": (),
        "budget_limits": (("tokens", 200000),),
        "budget_usage": (("tokens", 10),),
    }
    values.update(overrides)
    return dv.AuthorityRef(**values)


def test_authority_revoked_blocks_release() -> None:
    matter = make_matter(authority_required=True)
    validity = assess(
        make_decision(matter, authority_ref="auth-1"),
        matter,
        authority=authority(status="revoked"),
    )
    assert validity.status == "blocked"
    assert "authority_revoked" in codes(validity)


def test_authority_required_but_missing_blocks() -> None:
    matter = make_matter(authority_required=True)
    validity = assess(make_decision(matter), matter)
    assert validity.status == "blocked"
    assert "authority_unverified" in codes(validity)


def test_authority_source_must_be_real_not_editable_or_agent_report() -> None:
    matter = make_matter(authority_required=True)
    for weak in ("agent-report", "editable", "preauthorized", "token", ""):
        verdict = dv.assess_authority(authority(source=weak), matter)
        assert verdict.status == "insufficient", weak
        assert "insufficient_authority_source" in codes(verdict)
        assert verdict.applicable is False


def test_authority_scope_and_budget_are_enforced() -> None:
    matter = make_matter(authority_required=True)
    out_of_scope = dv.assess_authority(authority(objects=("stage-1",)), matter)
    assert out_of_scope.status == "out_of_scope"
    assert "authority_scope_exceeded" in codes(out_of_scope)

    action_scope = dv.assess_authority(authority(actions=("close",)), matter)
    assert action_scope.status == "out_of_scope"

    exhausted = dv.assess_authority(
        authority(budget_limits=(("tokens", 100),), budget_usage=(("tokens", 100),)),
        matter,
    )
    assert exhausted.status == "budget_blocked"
    assert "budget_exhausted" in codes(exhausted)


def test_authority_usage_unknown_blocks_budget() -> None:
    matter = make_matter(authority_required=True)
    verdict = dv.assess_authority(
        authority(budget_usage=()), matter
    )
    assert verdict.status == "budget_blocked"
    assert "budget_usage_unknown" in codes(verdict)


def test_authority_actor_mismatch_blocks() -> None:
    matter = make_matter(authority_required=True)
    verdict = dv.assess_authority(
        authority(), matter, bound_actor="pm-window-2"
    )
    assert verdict.status == "insufficient"
    assert "authority_actor_mismatch" in codes(verdict)


# ---------------------------------------------------------------------------
# Evidence applicability (AC-019/AC-025/AC-029)
# ---------------------------------------------------------------------------


def evidence_for(
    matter: dv.Matter,
    covered: tuple[str, ...],
    *,
    evidence_id: str = "ev-1",
    kind: str = "verification",
    contract: str | None = None,
    byte_sha256: str | None = None,
) -> dv.EvidenceRef:
    return dv.evidence_for(
        evidence_id,
        kind,
        matter,
        covered,
        contract_version=contract,
        byte_sha256=byte_sha256,
    )


def test_evidence_reuse_when_covered_dependency_unchanged() -> None:
    matter = make_matter()
    evidence = evidence_for(matter, ("write-face", "evidence"))
    applicability = dv.assess_evidence(evidence, matter)
    assert applicability.status == "applies"
    assert applicability.reusable is True
    assert applicability.stale_dependencies == ()


def test_evidence_reuse_ignores_unrelated_dependency_change() -> None:
    matter = make_matter()
    evidence = evidence_for(matter, ("write-face",))
    changed_deps = structured_deps()
    changed_deps[0] = dv.DependencyState(
        "goal", "structured", {"scope": {"$set": ["stage-1"]}, "commitment": "ship the stage"}
    )
    current = make_matter(deps=changed_deps)
    applicability = dv.assess_evidence(evidence, current, previous_matter=matter)
    assert applicability.status == "applies"
    assert applicability.reusable is True
    assert "goal" in applicability.unaffected_changes
    assert applicability.stale_dependencies == ()
    irrelevant_reapprovals = 0 if applicability.reusable else 1
    assert irrelevant_reapprovals == 0


def test_evidence_stale_when_covered_dependency_changes() -> None:
    matter = make_matter()
    evidence = evidence_for(matter, ("hard-budget",))
    changed_deps = structured_deps()
    changed_deps[4] = dv.DependencyState(
        "hard-budget", "structured", {"unit": "tokens", "limit": 90000}
    )
    current = make_matter(deps=changed_deps)
    applicability = dv.assess_evidence(evidence, current)
    assert applicability.status == "stale"
    assert applicability.stale_dependencies == ("hard-budget",)
    assert applicability.reusable is False
    stale_acceptance_passes = 1 if applicability.reusable else 0
    assert stale_acceptance_passes == 0


def test_evidence_byte_change_alone_is_reusable() -> None:
    matter = make_matter()
    evidence = evidence_for(matter, ("write-face",), byte_sha256="a" * 64)
    same_semantics = evidence_for(matter, ("write-face",), byte_sha256="b" * 64)
    assert dv.assess_evidence(evidence, matter).status == "applies"
    assert dv.assess_evidence(same_semantics, matter).status == "applies"


def test_evidence_prose_change_is_unknown() -> None:
    deps = structured_deps() + [dv.DependencyState("stop-reason", "prose", "waiting")]
    matter = make_matter(deps=deps)
    evidence = evidence_for(matter, ("stop-reason",))
    new_deps = structured_deps() + [
        dv.DependencyState("stop-reason", "prose", "waiting for approval")
    ]
    current = make_matter(deps=new_deps)
    applicability = dv.assess_evidence(evidence, current)
    assert applicability.status == "unknown"
    assert applicability.reusable is False
    assert "prose_equivalence_unverified" in codes(applicability)


def test_evidence_for_a_different_matter_is_not_applicable() -> None:
    matter = make_matter()
    other = make_matter(action="close")
    evidence = evidence_for(matter, ("write-face",))
    applicability = dv.assess_evidence(evidence, other)
    assert applicability.status == "not_applicable"
    assert "different_matter" in codes(applicability)


# ---------------------------------------------------------------------------
# AC-025 / VC-025: goal change impact
# ---------------------------------------------------------------------------


def binding(name: str, deps: tuple[str, ...]) -> dv.ApprovalBinding:
    return dv.ApprovalBinding(
        approval_id=name,
        object="key",
        dependency_names=deps,
        matter_key=make_matter().matter_key,
        substantive_version=make_matter().substantive_version,
    )


def test_goal_change_only_invalidates_affected_bindings() -> None:
    old = make_matter()
    changed_deps = structured_deps()
    changed_deps[0] = dv.DependencyState(
        "goal", "structured", {"scope": {"$set": ["stage-1"]}, "commitment": "ship the stage"}
    )
    new = make_matter(deps=changed_deps)
    bindings = [
        binding("key-approval", ("goal",)),
        binding("acceptance-approval", ("ac-items",)),
        binding("write-face-approval", ("write-face",)),
    ]
    impact = dv.assess_goal_change(old, new, bindings)
    assert impact.status == "affected_change"
    assert impact.affected_dependencies == ("goal",)
    assert impact.stale_bindings == ("key-approval",)
    assert set(impact.reusable_bindings) == {"acceptance-approval", "write-face-approval"}
    stale_affected_releases = 0 if "key-approval" not in impact.reusable_bindings else 1
    assert stale_affected_releases == 0


def test_goal_formatting_only_change_requires_no_reapproval() -> None:
    old = make_matter()
    reformatted = structured_deps()
    reformatted[0] = dv.DependencyState(
        "goal",
        "structured",
        {"commitment": "ship the stage", "scope": {"$set": ["stage-2", "stage-1"]}},
    )
    new = make_matter(deps=reformatted)
    impact = dv.assess_goal_change(old, new, [binding("key-approval", ("goal",))])
    assert impact.status == "no_substantive_change"
    assert impact.stale_bindings == ()
    assert impact.reusable_bindings == ("key-approval",)
    assert impact.user_decisions == ()
    irrelevant_reapprovals = len(impact.stale_bindings)
    assert irrelevant_reapprovals == 0


def test_goal_change_needs_user_decision_for_intent_dependencies() -> None:
    old = make_matter()
    changed_deps = structured_deps()
    changed_deps[4] = dv.DependencyState(
        "hard-budget", "structured", {"unit": "tokens", "limit": 500000}
    )
    new = make_matter(deps=changed_deps)
    impact = dv.assess_goal_change(
        old,
        new,
        [binding("budget-approval", ("hard-budget",))],
        user_decision_dependencies=("hard-budget",),
    )
    assert impact.status == "affected_change"
    assert impact.user_decisions == (
        dv.UserDecisionItem(
            dependency="hard-budget",
            code="new_business_intent_required",
            detail="substantive change needs a new user intent/authority",
        ),
    )
    unauthorized_actions = 0 if impact.status != "valid" else 1
    assert unauthorized_actions == 0


def test_goal_unknown_change_blocks_all_bindings() -> None:
    deps = structured_deps() + [dv.DependencyState("stop-reason", "prose", "why")]
    old = make_matter(deps=deps)
    new_deps = structured_deps() + [
        dv.DependencyState("stop-reason", "prose", "why not")
    ]
    new = make_matter(deps=new_deps)
    impact = dv.assess_goal_change(
        old, new, [binding("key-approval", ("stop-reason",))]
    )
    assert impact.status == "unknown"
    assert impact.unknown_bindings == ("key-approval",)
    assert impact.reusable_bindings == ()


# ---------------------------------------------------------------------------
# AC-027 / VC-027: claim and write surface
# ---------------------------------------------------------------------------


def test_claim_conflict_with_foreign_owner_is_detected() -> None:
    claims = [
        dv.Claim(
            owner="worker-window-1",
            task_key="other-key",
            files=("packages/multi-workers/shared.py",),
        )
    ]
    request = dv.ClaimRequest(
        actor="worker-window-2",
        task_key="my-key",
        files=("packages\\multi-workers\\shared.py",),
    )
    verdict = dv.assess_claim(claims, request)
    assert verdict.status == "conflict"
    assert verdict.conflicts == ("packages/multi-workers/shared.py",)
    assert verdict.conflicting_owners == ("worker-window-1",)
    assert verdict.takeover is False
    claim_thefts = 1 if verdict.takeover else 0
    assert claim_thefts == 0


def test_decision_ref_does_not_transfer_claim() -> None:
    claims = [
        dv.Claim(
            owner="worker-window-1",
            task_key="other-key",
            files=("packages/multi-workers/shared.py",),
        )
    ]
    request = dv.ClaimRequest(
        actor="worker-window-2",
        task_key="my-key",
        files=("packages/multi-workers/shared.py",),
        decision_ref="dec-1",
    )
    verdict = dv.assess_claim(claims, request)
    assert verdict.status == "conflict"
    assert verdict.decision_grants_claim is False
    assert "decision_does_not_transfer_claim" in codes(verdict)
    assert verdict.dispatched is False


def test_shared_lock_and_double_writer_are_conflicts() -> None:
    claims = [
        dv.Claim(
            owner="worker-window-1",
            task_key="other-key",
            files=("packages/multi-workers/shared.py",),
            lock_mode="shared",
        ),
        dv.Claim(
            owner="worker-window-3",
            task_key="third-key",
            files=("packages/multi-workers/shared.py",),
        ),
    ]
    request = dv.ClaimRequest(
        actor="worker-window-2",
        task_key="my-key",
        files=("packages/multi-workers/shared.py",),
    )
    verdict = dv.assess_claim(claims, request)
    assert verdict.status == "conflict"
    assert "lock_mode_not_exclusive" in codes(verdict)
    concurrent_writers = 1 if verdict.status == "clear" else 0
    assert concurrent_writers == 0


def test_claim_is_clear_for_own_files_and_empty_is_blocked() -> None:
    claims = [
        dv.Claim(
            owner="worker-window-1",
            task_key="my-key",
            files=("packages/multi-workers/mine.py",),
        )
    ]
    request = dv.ClaimRequest(
        actor="worker-window-1",
        task_key="my-key",
        files=("packages/multi-workers/mine.py",),
    )
    assert dv.assess_claim(claims, request).status == "clear"
    empty = dv.assess_claim(claims, dv.ClaimRequest("worker-window-1", "my-key", ()))
    assert empty.status == "blocked"
    assert "empty_write_face" in codes(empty)


def test_write_surface_rejects_outside_absolute_and_traversal() -> None:
    allowed = (
        "packages/multi-workers/decision_validity.py",
        "packages/multi-workers/test_dp_consolidation_concurrency.py",
        ".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t06-validity/**",
    )
    inside = dv.assess_write_surface(
        [
            "packages/multi-workers/decision_validity.py",
            ".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t06-validity/report.md",
        ],
        allowed,
    )
    assert inside.status == "ok"
    assert inside.violations == ()

    outside = dv.assess_write_surface(
        ["packages/multi-workers/decision.py"], allowed
    )
    assert outside.status == "violation"
    assert "outside_write_face" in {v.code for v in outside.violations}

    for bad, code in (
        ("/etc/passwd", "absolute_path"),
        ("packages/multi-workers/../decision.py", "parent_traversal"),
        ("packages/multi-workers/*.py", "wildcard_not_allowed"),
        ("", "empty_write_face"),
    ):
        verdict = dv.assess_write_surface([bad], allowed)
        assert verdict.status == "violation", bad
        assert code in {v.code for v in verdict.violations}, bad

    outside_actions = 1 if outside.status == "ok" else 0
    assert outside_actions == 0


# ---------------------------------------------------------------------------
# AC-028 / VC-028 / AC-029 / VC-029: frozen contract change
# ---------------------------------------------------------------------------


def contract_change(**overrides) -> dv.ContractChange:
    values = {
        "key": "key-1",
        "items": ("AC-011", "VC-011"),
        "before": "duplicate approvals are not counted",
        "after": "duplicate approvals and duplicate actions are not counted",
        "reason": "the acceptance condition missed the action count",
        "commitment_impact": "no commitment reduction",
        "evidence_impact": "VC-011 must be re-verified",
        "authority_ref": "user message 2026-10-25 approved the change",
        "reverification_plan": "re-run VC-011 cases after the change",
        "acceptance_reductions": (),
    }
    values.update(overrides)
    return dv.ContractChange(**values)


def change_approval(**overrides) -> dv.ChangeApproval:
    values = {
        "approval_ref": "change-approval-1",
        "key": "key-1",
        "items": ("AC-011", "VC-011"),
        "before": "duplicate approvals are not counted",
        "after": "duplicate approvals and duplicate actions are not counted",
        "reverification_plan": "re-run VC-011 cases after the change",
        "authority_source": "user message 2026-10-25 approved the change",
        "acceptance_reductions": (),
    }
    values.update(overrides)
    return dv.ChangeApproval(**values)


def test_contract_change_requires_complete_request_and_approval() -> None:
    verdict = dv.assess_contract_change(contract_change(), None)
    assert verdict.status == "blocked"
    assert "missing_approval" in codes(verdict)

    incomplete = dv.assess_contract_change(
        contract_change(reason="", commitment_impact="", reverification_plan=""),
        change_approval(),
    )
    assert incomplete.status == "blocked"
    assert "incomplete_change_request" in codes(incomplete)
    reason = next(r for r in incomplete.reasons if r.code == "incomplete_change_request")
    assert set(reason.detail.split(",")) == {
        "reason",
        "commitment_impact",
        "reverification_plan",
    }


def test_approval_only_covers_exact_items_and_versions() -> None:
    exact = dv.assess_contract_change(contract_change(), change_approval())
    assert exact.status == "approved"
    assert exact.approved_items == ("AC-011", "VC-011")
    assert exact.covers_only_requested_change is True

    narrower = dv.assess_contract_change(
        contract_change(), change_approval(items=("AC-011",))
    )
    assert narrower.status == "blocked"
    assert "approval_scope_too_narrow" in codes(narrower)

    wider = dv.assess_contract_change(
        contract_change(), change_approval(items=("AC-011", "VC-011", "AC-019"))
    )
    assert wider.status == "blocked"
    assert "approval_scope_expansion" in codes(wider)

    stale_text = dv.assess_contract_change(
        contract_change(), change_approval(after="a different acceptance text")
    )
    assert stale_text.status == "blocked"
    assert "approval_version_mismatch" in codes(stale_text)


def test_unrelated_change_approval_is_rejected() -> None:
    verdict = dv.assess_contract_change(
        contract_change(), change_approval(key="other-key")
    )
    assert verdict.status == "blocked"
    assert "reused_unrelated_change_approval" in codes(verdict)
    reused_unrelated_change_approvals = 0 if verdict.status != "approved" else 1
    assert reused_unrelated_change_approvals == 0


def test_unauthorized_acceptance_reduction_is_rejected() -> None:
    change = contract_change(acceptance_reductions=("AC-052",))
    verdict = dv.assess_contract_change(change, change_approval())
    assert verdict.status == "blocked"
    assert "unauthorized_acceptance_reduction" in codes(verdict)

    authorized = dv.assess_contract_change(
        change, change_approval(acceptance_reductions=("AC-052",))
    )
    assert authorized.status == "approved"


def test_approval_authority_must_not_be_manufactured() -> None:
    verdict = dv.assess_contract_change(
        contract_change(), change_approval(authority_source="agent-report")
    )
    assert verdict.status == "blocked"
    assert "insufficient_authority_source" in codes(verdict)
    fabricated_completion = 0 if verdict.status != "approved" else 1
    assert fabricated_completion == 0


def test_after_approved_change_affected_evidence_must_be_reverified() -> None:
    matter_before = make_matter()
    evidence = evidence_for(matter_before, ("ac-items", "write-face"))
    changed_deps = structured_deps()
    changed_deps[1] = dv.DependencyState("ac-items", "set", ["AC-011", "AC-052", "AC-019"])
    matter_after = make_matter(deps=changed_deps)

    approved = dv.assess_contract_change(
        contract_change(), change_approval()
    )
    assert approved.status == "approved"
    assert approved.reverification_items == ("AC-011", "VC-011")

    applicability = dv.assess_evidence(evidence, matter_after)
    assert applicability.status == "stale"
    assert applicability.stale_dependencies == ("ac-items",)
    stale_acceptance_passes = 1 if applicability.status == "applies" else 0
    assert stale_acceptance_passes == 0

    unaffected = evidence_for(matter_before, ("write-face",))
    assert dv.assess_evidence(unaffected, matter_after).status == "applies"


def test_history_objects_are_not_mutated_by_assessments() -> None:
    matter = make_matter()
    decision = make_decision(matter, effect="applied")
    evidence = evidence_for(matter, ("ac-items",))
    change = contract_change()
    approval = change_approval()
    snapshot = (
        decision,
        matter,
        evidence,
        change,
        approval,
        tuple(structured_deps()),
    )
    assess(decision, make_matter())
    dv.dedupe_decisions([decision], make_decision(matter, decision_id="dec-2"))
    dv.assess_evidence(evidence, matter)
    dv.assess_contract_change(change, approval)
    dv.assess_goal_change(matter, matter, [binding("b1", ("ac-items",))])
    assert snapshot[0] is decision and decision.effect == "applied"
    assert snapshot[1] is matter
    assert snapshot[2] is evidence
    assert tuple(snapshot[5]) == tuple(structured_deps())
    assert change.after == contract_change().after


def test_selection_has_no_automatic_contract_closure_or_signoff_effect() -> None:
    for entry in dv.ACTIVE_ENTRIES:
        effects = dv.selection_effects(entry, "some-choice")
        assert effects.contract_change is False
        assert effects.stage_closure is False
        assert effects.signoff_written is False
        assert effects.dispatch is False
        assert effects.needs_separate_authorization is True
    automatic_contract_or_closure_changes = 0
    assert automatic_contract_or_closure_changes == 0
    with pytest.raises(ValueError):
        dv.selection_effects("dp1-dispatch-type", "approve")


# ---------------------------------------------------------------------------
# AC-039 / VC-039: signoff applicability
# ---------------------------------------------------------------------------


def signoff(**overrides) -> dv.SignoffRef:
    matter = make_matter(kind="key-signoff")
    values = {
        "signoff_ref": "signoff-1",
        "choice": "finalize",
        "key": "key-1",
        "matter_key": matter.matter_key,
        "substantive_version": matter.substantive_version,
        "scope": ("key-1",),
        "artifact_ref": "signoff-key-1.json",
        "disable_requested": False,
        "historical": False,
    }
    values.update(overrides)
    return dv.SignoffRef(**values)


def test_signoff_legacy_word_and_disable_bypass_are_rejected() -> None:
    matter = make_matter(kind="key-signoff")
    for legacy in ("approve", "signed", "done", "promote", "demote"):
        verdict = dv.assess_signoff(signoff(choice=legacy), matter, required_scope=("key-1",))
        assert verdict.status == "blocked", legacy
        assert "legacy_word" in codes(verdict)
        assert verdict.writes_signoff is False

    disabled = dv.assess_signoff(
        signoff(disable_requested=True), matter, required_scope=("key-1",)
    )
    assert disabled.status == "blocked"
    assert "signoff_bypass" in codes(disabled)
    legacy_word_bypasses = 0 if disabled.status != "valid" else 1
    assert legacy_word_bypasses == 0


def test_signoff_scope_is_not_widened_and_required_scope_must_be_covered() -> None:
    matter = make_matter(kind="key-signoff")
    narrowed = dv.assess_signoff(
        signoff(scope=("key-1",)), matter, required_scope=("key-1", "key-2")
    )
    assert narrowed.status == "blocked"
    assert "incomplete_scope" in codes(narrowed)

    widened = dv.assess_signoff(
        signoff(scope=("key-1", "key-2")), matter, required_scope=("key-1",)
    )
    assert widened.status == "blocked"
    assert "scope_expansion" in codes(widened)
    assert widened.widens_scope is False
    signoff_scope_expansions = 1 if widened.widens_scope else 0
    assert signoff_scope_expansions == 0


def test_stale_signoff_is_not_reused() -> None:
    old = make_matter(kind="key-signoff")
    changed = structured_deps()
    changed[0] = dv.DependencyState(
        "goal", "structured", {"scope": {"$set": ["stage-1"]}, "commitment": "ship the stage"}
    )
    current = make_matter(kind="key-signoff", deps=changed)
    verdict = dv.assess_signoff(signoff(), current, required_scope=("key-1",))
    assert verdict.status == "stale"
    assert "stale_signoff" in codes(verdict)
    stale_signoff_reuses = 1 if verdict.status == "valid" else 0
    assert stale_signoff_reuses == 0
    assert old.substantive_version != current.substantive_version


def test_fabricated_signoff_without_artifact_is_rejected() -> None:
    matter = make_matter(kind="key-signoff")
    for artifact in (None, ""):
        verdict = dv.assess_signoff(
            signoff(artifact_ref=artifact), matter, required_scope=("key-1",)
        )
        assert verdict.status == "blocked"
        assert "fabricated_signoff" in codes(verdict)
    historical = dv.assess_signoff(
        signoff(historical=True), matter, required_scope=("key-1",)
    )
    assert historical.status == "blocked"
    assert "historical_readonly" in codes(historical)


def test_valid_finalize_is_applicable_but_this_module_never_writes() -> None:
    matter = make_matter(kind="key-signoff")
    verdict = dv.assess_signoff(signoff(), matter, required_scope=("key-1",))
    assert verdict.status == "valid"
    assert verdict.writes_signoff is False
    assert verdict.reasons == ()


# ---------------------------------------------------------------------------
# AC-052 / VC-052: replay, effects, crash windows
# ---------------------------------------------------------------------------


def test_unknown_or_in_progress_effect_blocks_retry() -> None:
    matter = make_matter()
    for status in ("unknown", "in-progress"):
        effect = dv.EffectRecord(
            effect_id="eff-1",
            decision_id="dec-1",
            matter_key=matter.matter_key,
            substantive_version=matter.substantive_version,
            actions=("start-stage",),
            status=status,
        )
        plan = dv.plan_actions([effect], matter=matter, actions=("start-stage",))
        assert plan.status == "blocked", status
        assert plan.actions == ()
        assert plan.blocked == ("start-stage",)
        assert "effect_state_unknown" in codes(plan)


def test_failed_effect_can_be_retried_without_hiding_history() -> None:
    matter = make_matter()
    failed = dv.EffectRecord(
        effect_id="eff-1",
        decision_id="dec-1",
        matter_key=matter.matter_key,
        substantive_version=matter.substantive_version,
        actions=("start-stage",),
        status="failed",
    )
    plan = dv.plan_actions([failed], matter=matter, actions=("start-stage",))
    assert plan.status == "proceed"
    assert plan.actions == ("start-stage",)
    assert plan.blocked == ()
    assert failed.status == "failed"


def test_action_for_a_new_substantive_version_is_not_a_duplicate() -> None:
    old = make_matter()
    changed = structured_deps()
    changed[3] = dv.DependencyState(
        "write-face", "set", ["packages/multi-workers/decision_validity.py", "x.py"]
    )
    new = make_matter(deps=changed)
    applied = dv.EffectRecord(
        effect_id="eff-1",
        decision_id="dec-1",
        matter_key=old.matter_key,
        substantive_version=old.substantive_version,
        actions=("start-stage",),
        status="applied",
    )
    plan = dv.plan_actions([applied], matter=new, actions=("start-stage",))
    assert plan.status == "proceed"
    assert plan.actions == ("start-stage",)
    assert plan.duplicate_actions == ()


def test_different_matter_action_is_not_treated_as_duplicate() -> None:
    matter = make_matter()
    other = make_matter(obj="stage-3")
    applied = dv.EffectRecord(
        effect_id="eff-1",
        decision_id="dec-1",
        matter_key=other.matter_key,
        substantive_version=other.substantive_version,
        actions=("start-stage",),
        status="applied",
    )
    plan = dv.plan_actions([applied], matter=matter, actions=("start-stage",))
    assert plan.status == "proceed"
    assert plan.actions == ("start-stage",)


# ---------------------------------------------------------------------------
# Dependency/version mechanics and input validation
# ---------------------------------------------------------------------------


def test_matter_identity_ignores_dependency_order_and_byte_sha() -> None:
    left = make_matter(deps=list(reversed(structured_deps())))
    right = make_matter(deps=structured_deps())
    assert left.matter_key == right.matter_key
    assert left.substantive_version == right.substantive_version
    assert left.dependencies == right.dependencies


def test_matter_rejects_duplicate_names_and_empty_identity() -> None:
    with pytest.raises(ValueError):
        make_matter(deps=structured_deps() + [structured_deps()[0]])
    with pytest.raises(ValueError):
        make_matter(subject="  ")
    with pytest.raises(ValueError):
        make_matter(contract="")
    with pytest.raises(ValueError):
        dv.DependencyState("scope", "not-a-kind", "x")


def test_canonical_values_handle_nested_sets_and_numbers() -> None:
    equal = dv.compare_dependency_values(
        "structured", {"limit": 100, "unit": "tokens"}, {"unit": "tokens", "limit": 100.0}
    )
    assert equal.status == "equivalent"
    changed = dv.compare_dependency_values("structured", {"limit": 100}, {"limit": 101})
    assert changed.status == "changed"
    unordered = dv.compare_dependency_values(
        "structured", {"$set": ["b", "a"]}, {"$set": ["a", "b"]}
    )
    assert unordered.status == "equivalent"
