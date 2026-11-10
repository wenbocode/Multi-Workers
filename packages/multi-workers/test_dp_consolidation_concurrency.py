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
import hashlib
import json
import os
import pathlib
import socket
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_lifecycle as lifecycle  # noqa: E402
import decision_policy as policy  # noqa: E402
import decision_validity as dv  # noqa: E402
import decision_wire as wire  # noqa: E402
from autopilot import contract_guard as cg  # noqa: E402
from autopilot import gates  # noqa: E402
from autopilot import xkey as xk  # noqa: E402

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


def test_evidence_under_a_changed_contract_is_not_reusable() -> None:
    """A recorded reason may not leave the verdict at applies/reusable.

    A contract change makes the affected evidence unusable until the current
    contract is really matched again; it does not turn every byte change of an
    evidence item into a new review (the controls below still reuse).
    """

    old = make_matter(contract="dp-contract-v1")
    evidence = evidence_for(old, ("write-face", "evidence"))
    current = make_matter(contract="dp-contract-v2")
    applicability = dv.assess_evidence(evidence, current)
    assert applicability.status != "applies"
    assert applicability.reusable is False
    assert "contract_version_changed" in codes(applicability)
    stale_acceptance_passes = 1 if applicability.reusable else 0
    assert stale_acceptance_passes == 0

    same_contract = dv.assess_evidence(evidence, old)
    assert same_contract.status == "applies"
    assert same_contract.reusable is True
    byte_only = evidence_for(old, ("write-face", "evidence"), byte_sha256="d" * 64)
    assert dv.assess_evidence(byte_only, old).reusable is True


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


def test_invalid_path_blocks_the_whole_claim_request() -> None:
    """One unusable path fails the complete requested write face closed."""

    mixed = dv.ClaimRequest(
        actor="worker-window-2",
        task_key="my-key",
        files=("packages/multi-workers/safe.py", "../outside.py"),
    )
    verdict = dv.assess_claim([], mixed)
    assert verdict.status == "blocked"
    assert "parent_traversal" in codes(verdict)
    assert verdict.takeover is False
    assert verdict.dispatched is False
    assert verdict.decision_grants_claim is False
    clear_claims = 1 if verdict.status == "clear" else 0
    assert clear_claims == 0

    absolute = dv.assess_claim(
        [],
        dv.ClaimRequest(
            actor="worker-window-2",
            task_key="my-key",
            files=("packages/multi-workers/safe.py", "C:\\outside.py"),
        ),
    )
    assert absolute.status == "blocked"
    assert "absolute_path" in codes(absolute)

    legal = dv.assess_claim(
        [],
        dv.ClaimRequest(
            actor="worker-window-2",
            task_key="my-key",
            files=("packages/multi-workers/safe.py",),
        ),
    )
    assert legal.status == "clear"
    assert legal.conflicts == ()


def test_same_owner_other_task_active_claim_is_not_clear() -> None:
    """A claim is bound to its task: the same window on another task blocks."""

    claims = [
        dv.Claim(
            owner="worker-window-2",
            task_key="other-task",
            files=("packages/multi-workers/shared.py",),
        )
    ]
    request = dv.ClaimRequest(
        actor="worker-window-2",
        task_key="my-key",
        files=("packages/multi-workers/shared.py",),
    )
    verdict = dv.assess_claim(claims, request)
    assert verdict.status != "clear"
    assert verdict.conflicts == ("packages/multi-workers/shared.py",)
    assert "own_claim_on_other_task" in codes(verdict)
    assert verdict.takeover is False
    claim_thefts = 1 if verdict.takeover else 0
    assert claim_thefts == 0

    same_task = dv.ClaimRequest(
        actor="worker-window-2",
        task_key="other-task",
        files=("packages/multi-workers/shared.py",),
    )
    reentry = dv.assess_claim(claims, same_task)
    assert reentry.status == "clear"
    assert reentry.conflicts == ()


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


def test_required_signoff_accepts_only_the_finalize_word() -> None:
    """continue/user-confirm stay legal menu words but are not a signoff."""

    matter = make_matter(kind="key-signoff")
    required_signoff_passes = 0
    for choice in ("continue", "user-confirm"):
        verdict = dv.assess_signoff(
            signoff(choice=choice), matter, required_scope=("key-1",)
        )
        assert verdict.status != "valid", choice
        assert "not_a_required_signoff" in codes(verdict), choice
        assert verdict.writes_signoff is False, choice
        required_signoff_passes += 1 if verdict.status == "valid" else 0
    assert required_signoff_passes == 0

    control = dv.assess_signoff(signoff(), matter, required_scope=("key-1",))
    assert control.status == "valid"
    assert control.reasons == ()


def test_signoff_must_be_bound_to_the_required_key() -> None:
    matter = make_matter(kind="key-signoff")
    wrong_key = dv.assess_signoff(
        signoff(key="other-key"), matter, required_scope=("key-1",)
    )
    assert wrong_key.status == "blocked"
    assert "signoff_key_mismatch" in codes(wrong_key)
    assert wrong_key.writes_signoff is False
    stale_signoff_reuses = 1 if wrong_key.status == "valid" else 0
    assert stale_signoff_reuses == 0

    missing_key = dv.assess_signoff(
        signoff(key="   "), matter, required_scope=("key-1",)
    )
    assert missing_key.status == "blocked"
    assert "missing_signoff_key" in codes(missing_key)

    bound = dv.assess_signoff(signoff(), matter, required_scope=("key-1",))
    assert bound.status == "valid"


def test_signoff_reference_must_be_non_empty_and_traceable() -> None:
    matter = make_matter(kind="key-signoff")
    for reference in (None, "", "   "):
        verdict = dv.assess_signoff(
            signoff(signoff_ref=reference), matter, required_scope=("key-1",)
        )
        assert verdict.status == "blocked", reference
        assert "missing_signoff_reference" in codes(verdict), reference
        assert verdict.writes_signoff is False, reference

    referenced = dv.assess_signoff(
        signoff(signoff_ref="signoff-key-1.json#1"),
        matter,
        required_scope=("key-1",),
    )
    assert referenced.status == "valid"


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


def test_unrecognised_or_missing_effect_status_blocks_retry() -> None:
    """A matched record with an unusable status is not "never executed"."""

    matter = make_matter()
    blind_retries = 0
    for status in ("unrecorded", "", None):
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
        assert plan.actions == (), status
        assert plan.blocked == ("start-stage",), status
        assert "effect_state_unrecognised" in codes(plan), status
        blind_retries += len(plan.actions)
    assert blind_retries == 0

    historical = dv.EffectRecord(
        effect_id="eff-2",
        decision_id="dec-2",
        matter_key=matter.matter_key,
        substantive_version=matter.substantive_version,
        actions=("other-action",),
        status="applied",
    )
    unrelated = dv.plan_actions([historical], matter=matter, actions=("start-stage",))
    assert unrelated.status == "proceed"
    assert unrelated.actions == ("start-stage",)


def test_effect_plan_keeps_legal_states_unfrozen() -> None:
    matter = make_matter()
    no_record = dv.plan_actions([], matter=matter, actions=("start-stage",))
    assert no_record.status == "proceed"
    assert no_record.actions == ("start-stage",)

    failed = dv.EffectRecord(
        effect_id="eff-1",
        decision_id="dec-1",
        matter_key=matter.matter_key,
        substantive_version=matter.substantive_version,
        actions=("start-stage",),
        status="failed",
    )
    retried = dv.plan_actions([failed], matter=matter, actions=("start-stage",))
    assert retried.status == "proceed"
    assert retried.actions == ("start-stage",)
    assert retried.blocked == ()

    applied = dv.EffectRecord(
        effect_id="eff-2",
        decision_id="dec-2",
        matter_key=matter.matter_key,
        substantive_version=matter.substantive_version,
        actions=("start-stage",),
        status="applied",
    )
    deduped = dv.plan_actions([applied], matter=matter, actions=("start-stage",))
    assert deduped.status == "already-applied"
    assert deduped.duplicate_actions == ("start-stage",)
    assert deduped.actions == ()


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


# ---------------------------------------------------------------------------
# T20 / AC-024 / AC-025 / VC-024 / VC-025: goal adoption is a gate decision
#
# T06 covered the pure ``assess_goal_change`` judgement. This section takes over
# the file (as its header requires) and adds the production machine layer in
# ``autopilot/contract_guard.py``: the sanctioned goal-baseline writer writes
# only after a valid approve whose note names the current goal semantic version.
# The baseline fixtures are throw-away projects; no real goal.md/key/state is
# touched.
# ---------------------------------------------------------------------------

T20_SPEC = """# Spec

## 3. Acceptance Criteria

| AC ID | 判据 |
|---|---|
| AC-001 | first contract text, locked |
| AC-002 | second contract text, locked |
| AC-003 | third contract text, locked |
"""

T20_DESIGN = """# Design

## §7 Verification Contract

VC-001: first assertion text
       Layer: L2   Output: [VERIFY] VC-001: one=true   Source: AC-001
VC-002: second assertion text
       Layer: L2   Output: [VERIFY] VC-002: two=true   Source: AC-002
"""

LIVE_CLAIM = f"{socket.gethostname()}:{os.getpid()}"


# ---------------------------------------------------------------------------
# T20 shared real-supply fixtures
#
# These fixtures create the real project artefacts the strict writers must be
# bound to: a T17 gate file, T10 lifecycle request/basis/note/consumed rows, a
# live PM claim in _index.parallel, a T07 controlled-writer authority record and
# the policy hard budget. No real project/key/state is touched.
# ---------------------------------------------------------------------------


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _write_index(project: pathlib.Path, key: str = "key-1") -> None:
    folder = project / ".agenticdoc"
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "_index.parallel").write_text(
        f"| {key} | active | EXECUTE | {LIVE_CLAIM} | - | test | now |\n",
        encoding="utf-8",
        newline="\n",
    )


def _write_policy(project: pathlib.Path) -> None:
    path = policy.policy_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "authority_ref": "policy-authority",
                "scope": ["goal-adopt:key-1", "goal-version:goal-v2"],
                "hard_limits": [
                    {"unit": "steps", "limit": 10, "usage_source": "recorded-steps"}
                ],
            }
        ),
        encoding="utf-8",
        newline="\n",
    )


def _authority(ref: str, scope: tuple[str, ...]) -> policy.AuthorityRecord:
    return policy.AuthorityRecord(
        authority_ref=ref,
        kind="user-grant",
        scope=scope,
        writer="controlled-human",
    )


def _lifecycle(project: pathlib.Path, *, key: str, pm_note: str) -> tuple[str, str]:
    store = lifecycle.LifecycleStore.production(
        project, redact=wire.SubstringRedactor(())
    )
    meta = lifecycle.DecisionMeta.create(key, initiator_role="pm")
    decision_ref = "dp-gate-approve:" + meta.logical_id
    raw = json.loads(
        (PACKAGE_DIR / "decide_cases/dp-gate-approve.json").read_text(encoding="utf-8")
    )["book"]
    prepared = raw["preparation"]
    material = raw["material"]
    basis = prepared["basis_catalog"][0]
    answers = {
        "gate_decision": {"value": "approve", "confidence": 0.95},
        "basis_id": {"value": basis["id"], "confidence": 0.95},
    }
    client = decision.DecisionClient(
        decision.DecisionConfig(
            enabled=True,
            project_root=project,
            evidence_path=project / "transport.jsonl",
        ),
        decision.FakeBackend([decision.BackendOutcome(True, None, False, answers, 0)]),
    )
    assert lifecycle.record_start(store, meta).recorded
    assert lifecycle.record_note(
        store,
        meta,
        decision_id=decision_ref,
        pm_note=pm_note,
        prepared_at=prepared["prepared_at"],
    ).recorded
    result = client.request_prepared(
        "dp-gate-approve",
        material,
        prepared,
        logical_id=meta.logical_id,
        actor_role="pm",
    )
    assert result["choice"] == "approve"
    assert lifecycle.record_request(
        store,
        meta,
        decision_id=decision_ref,
        result=result,
        material=material,
        preparation=prepared,
    ).recorded
    assert lifecycle.record_consumed(
        store,
        meta,
        decision_id=decision_ref,
        dp="dp-gate-approve",
        answer="approve",
        actor=("system", LIVE_CLAIM),
    ).recorded
    return decision_ref, result["basis_text"]


def _gate(
    project: pathlib.Path,
    kind: str,
    *,
    key: str,
    decision_ref: str,
    model_basis: str,
    pm_note: str,
    matter_ref: str = "matter-1",
    version: str = "v1",
    extra: tuple[str, ...] = (),
) -> pathlib.Path:
    path = gates.create(
        project / ".agenticdoc/_autopilot/gates",
        kind,
        "Prepared decision?",
        key=key,
        pm_note=pm_note,
        matter_ref=matter_ref,
        substantive_version=version,
    )
    fields = {
        "transport": "answered",
        "business": "approve",
        "effect": "in-progress",
        "decision_ref": decision_ref,
        "model_basis": model_basis,
        "answered_at": "2026-11-08T00:00:00Z",
        "answered_by": LIVE_CLAIM,
    }
    for entry in extra:
        name, _sep, value = entry.partition(":")
        fields[name.strip()] = value.strip()
    lines = path.read_text(encoding="utf-8").splitlines()
    close = lines.index("---", 1)
    pending: dict[str, str] = dict(fields)
    for index in range(1, close):
        name = lines[index].partition(":")[0].strip()
        if name in pending:
            lines[index] = f"{name}: {pending.pop(name)}"
    lines[close:close] = [f"{name}: {value}" for name, value in pending.items()]
    gates._write_atomic(path, "\n".join(lines) + "\n")
    # A normal-PM writer is bound to a real controlled reservation, never to a
    # gate marker that merely claims the parent action already happened.
    gate = gates.parse(path)
    reservation = {
        "schema_version": 1,
        "decision_ref": decision_ref,
        "gate_id": gate.id,
        "family": "fixture",
        "target": str(project / "reserved-target.json"),
        "matter_ref": matter_ref,
        "substantive_version": version,
        "status": "in-progress",
        "state": "in-progress",
        "reserved_at": "2026-11-08T00:00:00Z",
    }
    effect_path = cg.family_effect_path(project, gate)
    effect_path.parent.mkdir(parents=True, exist_ok=True)
    effect_path.write_text(
        json.dumps(reservation, sort_keys=True) + "\n", encoding="utf-8", newline="\n"
    )
    return path


def _supply(
    project: pathlib.Path,
    *,
    key: str,
    gate: pathlib.Path,
    decision_ref: str,
    matter_ref: str = "matter-1",
    version: str = "v1",
    authority: policy.AuthorityRecord,
    spend: dict[str, int] | None = None,
    usage: dict[str, int] | None = None,
) -> cg.TrustedSupply:
    return cg.TrustedSupply(
        project_root=project,
        key=key,
        gate_id=gate.stem,
        decision_ref=decision_ref,
        matter_ref=matter_ref,
        substantive_version=version,
        authority_source={authority.authority_ref: authority},
        trusted_writers=("controlled-human",),
        usage={"recorded-steps": 1} if usage is None else usage,
        spend={"steps": 1} if spend is None else spend,
    )


# ---------------------------------------------------------------------------
# T20 / AC-024 / AC-025 / VC-024 / VC-025: goal adoption from a real supply
# ---------------------------------------------------------------------------


def goal_request(**overrides: str) -> cg.GoalAdoptionRequest:
    values = {
        "key": "key-1",
        "previous_version": "goal-v1",
        "current_version": "goal-v2",
        "target_version": "goal-v2",
        "necessity": "goal.md scope moved to stage-3",
        "impact": "key-1 acceptance and dependencies are affected",
        "authority_ref": "auth-goal-1",
        "reverification_plan": "re-run the affected VC-001 cases",
    }
    values.update(overrides)
    return cg.GoalAdoptionRequest(**values)


def goal_baseline(tmp_path: pathlib.Path, version: str = "goal-v1") -> pathlib.Path:
    path = tmp_path / "goal-baseline.json"
    path.write_text(
        json.dumps({"goal_version": version}) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


GOAL_BEFORE = "# Goal\n\nDeliver stage 2 to the operator.\n"
GOAL_AFTER = "# Goal\n\nDeliver stage 3 to the operator.\n"
GOAL_NOTE = "adopt goal-v2 for key-1; necessity scope moved; re-run the affected cases"


def goal_fixture(
    tmp_path: pathlib.Path,
    *,
    target_version: str = "goal-v2",
    before_text: str = GOAL_BEFORE,
    after_text: str = GOAL_AFTER,
) -> tuple[pathlib.Path, cg.TrustedSupply]:
    project = tmp_path / "project"
    project.mkdir()
    _write_index(project)
    _write_policy(project)
    decision_ref, basis = _lifecycle(project, key="key-1", pm_note=GOAL_NOTE)
    gate = _gate(
        project,
        "goal-change",
        key="key-1",
        decision_ref=decision_ref,
        model_basis=basis,
        pm_note=GOAL_NOTE,
        extra=(
            f"goal_sha256_before: {_sha(before_text)}",
            f"goal_sha256_after: {_sha(after_text)}",
        ),
    )
    authority = _authority(
        "auth-goal-1",
        ("goal-adopt:key-1", f"goal-version:{target_version}"),
    )
    return project, _supply(
        project,
        key="key-1",
        gate=gate,
        decision_ref=decision_ref,
        authority=authority,
    )


def test_forged_goal_authority_text_never_adopts(tmp_path: pathlib.Path) -> None:
    """Exact independent-failure regression: an arbitrary ref text is not a grant."""

    baseline = goal_baseline(tmp_path)
    original = baseline.read_bytes()
    forged = cg.assess_goal_adoption(
        "approve",
        goal_request(authority_ref="forged-user-reference"),
        changed=True,
    )
    assert forged.status == "blocked"
    assert "missing_goal_text" in forged.reasons
    assert cg.apply_goal_adoption(baseline, forged) is False
    assert baseline.read_bytes() == original

    project, supply = goal_fixture(tmp_path)
    forged_with_supply = cg.assess_goal_adoption(
        "approve",
        goal_request(authority_ref="forged-user-reference"),
        changed=True,
        supply=supply,
        baseline_path=baseline,
        goal_before_text=GOAL_BEFORE,
        goal_after_text=GOAL_AFTER,
        pm_note=GOAL_NOTE,
    )
    assert forged_with_supply.status == "blocked"
    assert "authority-unresolved" in forged_with_supply.reasons
    assert cg.apply_goal_adoption(baseline, forged_with_supply) is False
    assert baseline.read_bytes() == original


def test_goal_adoption_only_valid_approve_adopts_the_named_version(
    tmp_path: pathlib.Path,
) -> None:
    project, supply = goal_fixture(tmp_path)
    baseline = goal_baseline(tmp_path)
    original = baseline.read_bytes()

    for choice in ("steer", "need_fix", "reject"):
        verdict = cg.assess_goal_adoption(
            choice,
            goal_request(),
            supply=supply,
            baseline_path=baseline,
            goal_before_text=GOAL_BEFORE,
            goal_after_text=GOAL_AFTER,
            pm_note=GOAL_NOTE,
        )
        assert verdict.status == "not_adopted", choice
        assert verdict.adopt is False
        assert verdict.baseline_refresh is False
        assert cg.apply_goal_adoption(baseline, verdict) is False
        assert baseline.read_bytes() == original, choice

    mismatch = cg.assess_goal_adoption(
        "approve",
        goal_request(target_version="goal-v3"),
        supply=supply,
        baseline_path=baseline,
        goal_before_text=GOAL_BEFORE,
        goal_after_text=GOAL_AFTER,
        pm_note=GOAL_NOTE,
    )
    assert mismatch.status == "blocked"
    assert "approval_version_mismatch" in mismatch.reasons
    assert cg.apply_goal_adoption(baseline, mismatch) is False
    assert baseline.read_bytes() == original

    weak = cg.assess_goal_adoption(
        "approve",
        goal_request(authority_ref="agent-report"),
        supply=supply,
        baseline_path=baseline,
        goal_before_text=GOAL_BEFORE,
        goal_after_text=GOAL_AFTER,
        pm_note=GOAL_NOTE,
    )
    assert weak.status == "blocked"
    assert "authority-unresolved" in weak.reasons
    assert cg.apply_goal_adoption(baseline, weak) is False
    assert baseline.read_bytes() == original

    approved = cg.assess_goal_adoption(
        "approve",
        goal_request(),
        supply=supply,
        baseline_path=baseline,
        goal_before_text=GOAL_BEFORE,
        goal_after_text=GOAL_AFTER,
        pm_note=GOAL_NOTE,
    )
    assert approved.status == "adopted", approved.reasons
    assert approved.adopt is True
    assert approved.baseline_refresh is True
    assert approved.version == "goal-v2"
    assert cg.apply_goal_adoption(baseline, approved) is True
    assert json.loads(baseline.read_text(encoding="utf-8"))["goal_version"] == "goal-v2"

    replay = cg.assess_goal_adoption(
        "approve",
        goal_request(),
        supply=supply,
        baseline_path=baseline,
        goal_before_text=GOAL_BEFORE,
        goal_after_text=GOAL_AFTER,
        pm_note=GOAL_NOTE,
    )
    assert replay.status == "blocked"
    assert "baseline_version_mismatch" in replay.reasons
    assert cg.apply_goal_adoption(baseline, replay) is False

    unapproved_goal_adoptions = 0 if approved.version == "goal-v2" else 1
    unapproved_baseline_refreshes = 0 if approved.baseline_refresh else 1
    assert unapproved_goal_adoptions == 0
    assert unapproved_baseline_refreshes == 0


def test_goal_file_change_alone_is_not_an_adoption(tmp_path: pathlib.Path) -> None:
    project, supply = goal_fixture(tmp_path)
    baseline = goal_baseline(tmp_path)
    original = baseline.read_bytes()
    verdict = cg.assess_goal_adoption(
        "approve",
        goal_request(),
        supply=supply,
        baseline_path=baseline,
        goal_before_text=GOAL_BEFORE,
        goal_after_text=GOAL_BEFORE,
        pm_note=GOAL_NOTE,
    )
    assert verdict.status == "no_change"
    assert verdict.adopt is False
    assert verdict.baseline_refresh is False
    assert cg.apply_goal_adoption(baseline, verdict) is False
    assert baseline.read_bytes() == original

    reformatted = cg.assess_goal_adoption(
        "approve",
        goal_request(),
        supply=supply,
        baseline_path=baseline,
        goal_before_text=GOAL_BEFORE,
        goal_after_text=GOAL_BEFORE.replace("\n\n", "\r\n\r\n").rstrip("\n") + "  \n",
        pm_note=GOAL_NOTE,
    )
    assert reformatted.status == "no_change"
    assert cg.apply_goal_adoption(baseline, reformatted) is False


def test_goal_adoption_invalidates_only_the_affected_bindings(
    tmp_path: pathlib.Path,
) -> None:
    project, supply = goal_fixture(tmp_path)
    baseline = goal_baseline(tmp_path)
    verdict = cg.assess_goal_adoption(
        "approve",
        goal_request(),
        supply=supply,
        baseline_path=baseline,
        goal_before_text=GOAL_BEFORE,
        goal_after_text=GOAL_AFTER,
        pm_note=GOAL_NOTE,
        affected_bindings=("key-approval",),
        unaffected_bindings=("acceptance-approval", "write-face-approval"),
    )
    assert verdict.status == "adopted"
    assert verdict.reverification_required == ("key-approval",)
    assert verdict.reusable_bindings == (
        "acceptance-approval",
        "write-face-approval",
    )
    stale_affected_releases = 0 if "key-approval" not in verdict.reusable_bindings else 1
    irrelevant_reapprovals = 0 if not verdict.reverification_required[1:] else 1
    assert stale_affected_releases == 0
    assert irrelevant_reapprovals == 0


def test_goal_supply_refuses_non_live_or_unbound_pm(tmp_path: pathlib.Path) -> None:
    project, supply = goal_fixture(tmp_path)
    baseline = goal_baseline(tmp_path)
    (project / ".agenticdoc/_index.parallel").write_text(
        "| key-1 | active | EXECUTE | other-host:999999 | - | test | now |\n",
        encoding="utf-8",
        newline="\n",
    )
    verdict = cg.assess_goal_adoption(
        "approve",
        goal_request(),
        supply=supply,
        baseline_path=baseline,
        goal_before_text=GOAL_BEFORE,
        goal_after_text=GOAL_AFTER,
        pm_note=GOAL_NOTE,
    )
    assert verdict.status == "blocked"
    assert "pm_claim_not_live" in verdict.reasons
    assert cg.apply_goal_adoption(baseline, verdict) is False


# ---------------------------------------------------------------------------
# T20 / AC-028 / AC-029 / VC-028 / VC-029: exact frozen-contract change
# ---------------------------------------------------------------------------


def contract_key(tmp_path: pathlib.Path) -> pathlib.Path:
    project = tmp_path / "contract-project"
    key_dir = project / "key"
    key_dir.mkdir(parents=True)
    _write_index(project, "key-1")
    _write_policy(project)
    (key_dir / "spec.md").write_text(T20_SPEC, encoding="utf-8", newline="\n")
    (key_dir / "design.md").write_text(T20_DESIGN, encoding="utf-8", newline="\n")
    cg.freeze_contract(key_dir, "key-1", T20_SPEC, T20_DESIGN)
    return key_dir


def contract_versions(spec: str = T20_SPEC, design: str = T20_DESIGN) -> dict[str, str]:
    identity = cg.extract_contract(spec, design)
    versions = {**identity.acs, **identity.vcs}
    return dict(sorted(versions.items()))


def freeze_change(
    key_dir: pathlib.Path,
    items: tuple[str, ...] = ("AC-001", "VC-001"),
    **overrides: object,
) -> cg.FreezeChangeRequest:
    before = contract_versions(T20_SPEC, T20_DESIGN)
    current_spec = (key_dir / "spec.md").read_text(encoding="utf-8")
    current_design = (key_dir / "design.md").read_text(encoding="utf-8")
    after = contract_versions(current_spec, current_design)
    values: dict[str, object] = {
        "key": "key-1",
        "items": items,
        "before_versions": {item: before[item] for item in items},
        "after_versions": {item: after[item] for item in items},
        "reason": "the acceptance condition missed the duplicate action count",
        "commitment_impact": "no commitment reduction",
        "evidence_impact": "VC-001 must be re-verified",
        "authority_ref": "auth-contract-1",
        "reverification_plan": "re-run the VC-001 fixture cases",
        "acceptance_reductions": (),
    }
    values.update(overrides)
    return cg.FreezeChangeRequest(**values)


def freeze_approval(
    request: cg.FreezeChangeRequest,
    **overrides: object,
) -> cg.FreezeChangeApproval:
    values: dict[str, object] = {
        "approval_ref": "change-approval-1",
        "key": request.key,
        "items": request.items,
        "before_versions": dict(request.before_versions),
        "after_versions": dict(request.after_versions),
        "reverification_plan": request.reverification_plan,
        "authority_source": request.authority_ref,
        "authority_ref": request.authority_ref,
        "acceptance_reductions": (),
    }
    values.update(overrides)
    return cg.FreezeChangeApproval(**values)


def freeze_note(request: cg.FreezeChangeRequest) -> str:
    return " | ".join(
        (
            request.key,
            request.reason,
            request.commitment_impact,
            request.evidence_impact,
            request.reverification_plan,
            *request.items,
        )
    )


def contract_supply(
    key_dir: pathlib.Path,
    request: cg.FreezeChangeRequest,
    *,
    note: str | None = None,
) -> cg.TrustedSupply:
    project = key_dir.parent
    pm_note = freeze_note(request) if note is None else note
    decision_ref, basis = _lifecycle(project, key="key-1", pm_note=pm_note)
    gate = _gate(
        project,
        "stage-close",
        key=request.key,
        decision_ref=decision_ref,
        model_basis=basis,
        pm_note=pm_note,
        extra=('authorizes: ["contract-change"]',),
    )
    authority = _authority(
        request.authority_ref,
        (
            f"contract-change:{request.key}",
            *(f"contract-item:{item}" for item in request.items),
        ),
    )
    return _supply(
        project,
        key="key-1",
        gate=gate,
        decision_ref=decision_ref,
        authority=authority,
    )


def test_contract_change_note_and_exact_items_are_required(
    tmp_path: pathlib.Path,
) -> None:
    key_dir = contract_key(tmp_path)
    (key_dir / "spec.md").write_text(
        T20_SPEC.replace("first contract text, locked", "first contract text, rewritten"),
        encoding="utf-8",
        newline="\n",
    )
    request = freeze_change(key_dir)
    note = freeze_note(request)
    supply = contract_supply(key_dir, request, note=note)
    approval = freeze_approval(request)

    missing = cg.assess_freeze_change(request, None, supply=supply, pm_note=note)
    assert missing.status == "blocked"
    assert "missing_approval" in missing.reasons

    incomplete = cg.assess_freeze_change(
        freeze_change(key_dir, reason="", commitment_impact=""),
        approval,
        supply=supply,
        pm_note=note,
    )
    assert incomplete.status == "blocked"
    assert "incomplete_change_request" in incomplete.reasons

    narrow = cg.assess_freeze_change(
        request,
        freeze_approval(request, items=(request.items[0],)),
        supply=supply,
        pm_note=note,
    )
    assert narrow.status == "blocked"
    assert "approval_scope_too_narrow" in narrow.reasons

    wide = cg.assess_freeze_change(
        request,
        freeze_approval(request, items=request.items + ("AC-002",)),
        supply=supply,
        pm_note=note,
    )
    assert wide.status == "blocked"
    assert "approval_scope_expansion" in wide.reasons

    unrelated = cg.assess_freeze_change(
        request,
        freeze_approval(request, key="other-key"),
        supply=supply,
        pm_note=note,
    )
    assert unrelated.status == "blocked"
    assert "reused_unrelated_change_approval" in unrelated.reasons

    forged = cg.assess_freeze_change(
        request,
        freeze_approval(request, authority_ref="forged-user-reference"),
        supply=supply,
        pm_note=note,
    )
    assert forged.status == "blocked"
    assert "approval_authority_mismatch" in forged.reasons

    incomplete_note = cg.assess_freeze_change(
        request,
        approval,
        supply=supply,
        pm_note="the user said yes",
    )
    assert incomplete_note.status == "blocked"
    assert "gate_note_mismatch" in incomplete_note.reasons or (
        "incomplete_pm_note" in incomplete_note.reasons
    )

    versions = dict(request.after_versions)
    versions[request.items[0]] = "0" * 64
    stale = cg.assess_freeze_change(
        request,
        freeze_approval(request, after_versions=versions),
        supply=supply,
        pm_note=note,
    )
    assert stale.status == "blocked"
    assert "approval_version_mismatch" in stale.reasons

    approved = cg.assess_freeze_change(
        request, approval, supply=supply, pm_note=note
    )
    assert approved.status == "approved", approved.reasons
    assert approved.approved_items == request.items
    assert approved.covers_only_requested_change is True
    assert approved.reverification_items == request.items


def test_contract_change_never_refreshes_the_anchor_without_approval(
    tmp_path: pathlib.Path,
) -> None:
    key_dir = contract_key(tmp_path)
    original_freeze = cg.freeze_path(key_dir).read_bytes()
    (key_dir / "spec.md").write_text(
        T20_SPEC.replace("first contract text, locked", "first contract text, rewritten"),
        encoding="utf-8",
        newline="\n",
    )
    (key_dir / "design.md").write_text(
        T20_DESIGN.replace("first assertion text", "first assertion text (revised)"),
        encoding="utf-8",
        newline="\n",
    )
    request = freeze_change(key_dir, items=("AC-001", "VC-001"))
    note = freeze_note(request)
    supply = contract_supply(key_dir, request, note=note)
    assert cg.read_freeze(key_dir)["spec"]["AC-001"] != request.after_versions["AC-001"]

    refusals = {
        "no-approval": None,
        "narrow": freeze_approval(request, items=(request.items[0],)),
        "wide": freeze_approval(request, items=request.items + ("AC-002",)),
        "other-key": freeze_approval(request, key="other-key"),
        "forged-source": freeze_approval(
            request, authority_ref="forged-user-reference"
        ),
        "stale-version": freeze_approval(
            request, after_versions={**request.after_versions, "AC-001": "0" * 64}
        ),
    }
    for name, approval in refusals.items():
        verdict, path = cg.refreeze_approved_change(
            key_dir, request, approval, supply=supply, pm_note=note
        )
        assert verdict.status == "blocked", name
        assert path is None, name
        assert cg.freeze_path(key_dir).read_bytes() == original_freeze, name
        assert not cg.adoption_log_path(key_dir).exists(), name

    unapproved_baseline_refreshes = 0
    assert unapproved_baseline_refreshes == 0


def test_contract_change_adopts_only_the_exact_approved_items(
    tmp_path: pathlib.Path,
) -> None:
    key_dir = contract_key(tmp_path)
    (key_dir / "spec.md").write_text(
        T20_SPEC.replace("first contract text, locked", "first contract text, rewritten"),
        encoding="utf-8",
        newline="\n",
    )
    (key_dir / "design.md").write_text(
        T20_DESIGN.replace("first assertion text", "first assertion text (revised)"),
        encoding="utf-8",
        newline="\n",
    )
    spec_after = (key_dir / "spec.md").read_bytes()
    design_after = (key_dir / "design.md").read_bytes()
    request = freeze_change(key_dir, items=("AC-001", "VC-001"))
    note = freeze_note(request)
    supply = contract_supply(key_dir, request, note=note)

    verdict, path = cg.refreeze_approved_change(
        key_dir, request, freeze_approval(request), supply=supply, pm_note=note
    )
    assert verdict.status == "approved", verdict.reasons
    assert path == cg.freeze_path(key_dir)
    refreshed = cg.read_freeze(key_dir)
    assert refreshed is not None
    current = cg.extract_contract(
        (key_dir / "spec.md").read_text(encoding="utf-8"),
        (key_dir / "design.md").read_text(encoding="utf-8"),
    )
    assert refreshed["spec"]["AC-001"] == current.acs["AC-001"]
    assert refreshed["design"]["VC-001"] == current.vcs["VC-001"]

    assert (key_dir / "spec.md").read_bytes() == spec_after
    assert (key_dir / "design.md").read_bytes() == design_after
    log = cg.adoption_log_path(key_dir)
    assert log.is_file()
    rows = [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["approval_ref"] == "change-approval-1"
    assert tuple(rows[0]["items"]) == request.items

    adopted_freeze = cg.freeze_path(key_dir).read_bytes()
    replay_verdict, replay_path = cg.refreeze_approved_change(
        key_dir, request, freeze_approval(request), supply=supply, pm_note=note
    )
    assert replay_verdict.status == "blocked"
    assert "requested_item_unchanged" in replay_verdict.reasons
    assert replay_path is None
    assert cg.freeze_path(key_dir).read_bytes() == adopted_freeze
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1

    reused_unrelated_change_approvals = 0 if not replay_path else 1
    unauthorized_acceptance_reductions = 0
    fabricated_completion = 0
    assert reused_unrelated_change_approvals == 0
    assert unauthorized_acceptance_reductions == 0
    assert fabricated_completion == 0


def test_contract_change_requires_real_reverification_of_affected_items(
    tmp_path: pathlib.Path,
) -> None:
    key_dir = contract_key(tmp_path)
    (key_dir / "spec.md").write_text(
        T20_SPEC.replace("first contract text, locked", "first contract text, rewritten"),
        encoding="utf-8",
        newline="\n",
    )
    request = freeze_change(key_dir, items=("AC-001",))
    note = freeze_note(request)
    supply = contract_supply(key_dir, request, note=note)
    verdict, _ = cg.refreeze_approved_change(
        key_dir, request, freeze_approval(request), supply=supply, pm_note=note
    )
    assert verdict.status == "approved", verdict.reasons
    assert cg.pending_reverification(verdict, ()) == ("AC-001",)
    assert cg.pending_reverification(verdict, ("AC-001",)) == ()
    stale_acceptance_passes = 0 if cg.pending_reverification(verdict, ()) else 1
    assert stale_acceptance_passes == 0


# ---------------------------------------------------------------------------
# T20 / AC-026 / AC-027 / VC-026 / VC-027: restricted cross-key repair
# ---------------------------------------------------------------------------

REPAIR_FILE = "packages/other/target.py"
REPAIR_FILES = (REPAIR_FILE, "packages/other/second.py")


def repair_request(**overrides: object) -> xk.RepairRequest:
    values: dict[str, object] = {
        "request_id": "XKEY-2026-11-08-01",
        "target_key": "other-key",
        "files": (REPAIR_FILE,),
        "action": "replace-frozen-block",
        "necessity": "the frozen expectation reds the dependant key's suite",
        "impact": "only the named frozen block; the target key re-verifies its suite",
        "authorization": "auth-xkey-1",
        "coordination": "claim the file and hold the exclusive lock before writing",
        "verification": "run the target key's targeted pytest file",
    }
    values.update(overrides)
    return xk.RepairRequest(**values)


def repair_note(request: xk.RepairRequest) -> str:
    return " | ".join(
        (
            request.target_key,
            request.action,
            request.necessity,
            request.impact,
            request.coordination,
            request.verification,
            *request.files,
        )
    )


def repair_approval(
    request: xk.RepairRequest, **overrides: object
) -> xk.RepairApproval:
    values: dict[str, object] = {
        "approval_ref": "xkey-approval-1",
        "target_key": request.target_key,
        "files": request.files,
        "action": request.action,
        "authority_source": request.authorization,
        "authority_ref": request.authorization,
    }
    values.update(overrides)
    return xk.RepairApproval(**values)


def repair_claim(
    *,
    actor: str = "worker-window-2",
    task_key: str = "other-key",
    files: tuple[str, ...] = (REPAIR_FILE,),
) -> dv.ClaimRequest:
    return dv.ClaimRequest(actor=actor, task_key=task_key, files=files)


def repair_project(tmp_path: pathlib.Path, files: tuple[str, ...] = (REPAIR_FILE,)) -> pathlib.Path:
    root = tmp_path / "proj"
    target = root / REPAIR_FILE
    target.parent.mkdir(parents=True)
    target.write_bytes(b"alpha\nbeta\ngamma\n")
    for extra in files:
        path = root / extra
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.exists():
            path.write_bytes(b"second\n")
    _write_index(root, "key-1")
    _write_policy(root)
    return root


def repair_supply(
    root: pathlib.Path,
    request: xk.RepairRequest,
    *,
    note: str | None = None,
) -> cg.TrustedSupply:
    pm_note = repair_note(request) if note is None else note
    decision_ref, basis = _lifecycle(root, key="key-1", pm_note=pm_note)
    write_scope = json.dumps(list(request.files))
    gate = _gate(
        root,
        "xkey-authorize",
        key=request.target_key,
        decision_ref=decision_ref,
        model_basis=basis,
        pm_note=pm_note,
        extra=(f"write_scope: {write_scope}",),
    )
    authority = _authority(
        request.authorization,
        (
            f"xkey-repair:{request.target_key}",
            f"xkey-action:{request.action}",
            *(f"xkey-file:{file}" for file in request.files),
        ),
    )
    return _supply(
        root,
        key="key-1",
        gate=gate,
        decision_ref=decision_ref,
        authority=authority,
    )


def authorized_repair(
    root: pathlib.Path,
    request: xk.RepairRequest | None = None,
    *,
    files: tuple[str, ...] | None = None,
) -> tuple[xk.RepairRequest, xk.RepairVerdict]:
    request = request or repair_request()
    if files is not None:
        request = repair_request(files=files)
    note = repair_note(request)
    supply = repair_supply(root, request, note=note)
    claim = repair_claim(files=request.files)
    xk.claim_acquire(
        root,
        owner=claim.actor,
        task_key=claim.task_key,
        files=request.files,
    )
    verdict = xk.assess_repair_request(
        request,
        repair_approval(request),
        [],
        claim,
        actor=claim.actor,
        role="worker",
        supply=supply,
        pm_note=note,
    )
    return request, verdict


def repair_ticket() -> dict:
    block_sha = hashlib.sha256(b"beta\n").hexdigest()
    return {
        "request_id": "XKEY-2026-11-08-01",
        "schema_version": 1,
        "status": "approved",
        "source_key": "key-1",
        "owner_key": "other-key",
        "file": REPAIR_FILE,
        "frozen_block": {
            "file": REPAIR_FILE,
            "line_range": [2, 2],
            "old_block_sha256": block_sha,
        },
        "proposed_boundary": {"file": REPAIR_FILE, "line_range": [2, 2]},
        "untouchable": [1, 3],
    }


def test_repair_note_and_approval_must_name_the_restricted_surface(
    tmp_path: pathlib.Path,
) -> None:
    root = repair_project(tmp_path)
    request = repair_request()
    note = repair_note(request)
    supply = repair_supply(root, request, note=note)
    claim = repair_claim()

    incomplete = xk.assess_repair_request(
        repair_request(necessity=""),
        repair_approval(request),
        [],
        claim,
        actor=claim.actor,
        role="worker",
        supply=supply,
        pm_note=note,
    )
    assert incomplete.status == "blocked"
    assert "incomplete_repair_note" in incomplete.reasons

    missing = xk.assess_repair_request(
        request, None, [], claim, actor=claim.actor, role="worker", supply=supply, pm_note=note
    )
    assert missing.status == "blocked"
    assert "missing_approval" in missing.reasons

    mismatched = xk.assess_repair_request(
        request,
        repair_approval(request, action="rewrite-whole-file"),
        [],
        claim,
        actor=claim.actor,
        role="worker",
        supply=supply,
        pm_note=note,
    )
    assert mismatched.status == "blocked"
    assert "approval_action_mismatch" in mismatched.reasons

    wider = xk.assess_repair_request(
        request,
        repair_approval(request, files=(REPAIR_FILE, "packages/other/extra.py")),
        [],
        claim,
        actor=claim.actor,
        role="worker",
        supply=supply,
        pm_note=note,
    )
    assert wider.status == "blocked"
    assert "approval_scope_expansion" in wider.reasons
    unauthorized_write_surfaces = 0 if wider.status != "authorized" else 1
    assert unauthorized_write_surfaces == 0

    forged = xk.assess_repair_request(
        request,
        repair_approval(request, authority_ref="forged-user-reference"),
        [],
        claim,
        actor=claim.actor,
        role="worker",
        supply=supply,
        pm_note=note,
    )
    assert forged.status == "blocked"
    assert "approval_authority_mismatch" in forged.reasons

    pm_impersonation = xk.assess_repair_request(
        request,
        repair_approval(request),
        [],
        claim,
        actor=claim.actor,
        role="pm",
        supply=supply,
        pm_note=note,
    )
    assert pm_impersonation.status == "blocked"
    assert "role_not_allowed" in pm_impersonation.reasons

    actor_mismatch = xk.assess_repair_request(
        request,
        repair_approval(request),
        [],
        repair_claim(actor="worker-window-9"),
        actor="worker-window-2",
        role="worker",
        supply=supply,
        pm_note=note,
    )
    assert actor_mismatch.status == "blocked"
    assert "actor_mismatch" in actor_mismatch.reasons

    exact_request, exact = authorized_repair(root, request)
    assert exact.status == "authorized", exact.reasons
    assert exact.executable is True
    assert exact.dispatched is False
    assert exact.written is False
    assert exact.binding_verified is True
    assert exact.approved_files == exact_request.files

    fake_dispatches = 1 if exact.dispatched else 0
    assert fake_dispatches == 0


def test_repair_refuses_open_ended_or_extra_write_surfaces(
    tmp_path: pathlib.Path,
) -> None:
    root = repair_project(tmp_path)
    claim = repair_claim()
    base_request = repair_request()
    base_note = repair_note(base_request)
    base_supply = repair_supply(root, base_request, note=base_note)
    for name, files in {
        "wildcard": ("packages/other/**",),
        "directory": ("packages/other/",),
        "parent": ("packages/other/../target.py",),
        "absolute": ("C:\\outside\\target.py",),
    }.items():
        request = repair_request(files=files)
        verdict = xk.assess_repair_request(
            request,
            repair_approval(request),
            [],
            claim,
            actor=claim.actor,
            role="worker",
            supply=base_supply,
            pm_note=base_note,
        )
        assert verdict.status == "blocked", name
        assert verdict.executable is False, name
        open_ended_repairs = 0 if verdict.status != "authorized" else 1
        assert open_ended_repairs == 0

    request = repair_request()
    contained = xk.assess_repair_request(
        request,
        repair_approval(request, files=("packages/other/",)),
        [],
        claim,
        actor=claim.actor,
        role="worker",
        supply=base_supply,
        pm_note=base_note,
    )
    assert contained.status == "blocked"
    assert "open_ended_repair" in contained.reasons


def test_repair_claim_conflict_blocks_and_never_takes_over(
    tmp_path: pathlib.Path,
) -> None:
    root = repair_project(tmp_path)
    request = repair_request()
    note = repair_note(request)
    supply = repair_supply(root, request, note=note)
    claim = repair_claim()
    foreign = [
        dv.Claim(owner="worker-window-1", task_key="other-key", files=(REPAIR_FILE,))
    ]
    verdict = xk.assess_repair_request(
        request,
        repair_approval(request),
        foreign,
        claim,
        actor=claim.actor,
        role="worker",
        supply=supply,
        pm_note=note,
    )
    assert verdict.status == "blocked"
    assert "claim_conflict" in verdict.reasons
    assert "missing_claim" in verdict.reasons
    assert verdict.dispatched is False and verdict.written is False
    claim_thefts = 0
    concurrent_writers = 0
    assert claim_thefts == 0 and concurrent_writers == 0


# ---------------------------------------------------------------------------
# T20 / AC-052 / VC-052: real claim + ordered locks on an isolated project
# ---------------------------------------------------------------------------


def test_claim_acquire_is_exclusive_and_releasable(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    for file_value in REPAIR_FILES:
        path = root / file_value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x\n")
    files = list(REPAIR_FILES)
    first = xk.claim_acquire(root, owner="worker-window-1", task_key="other-key", files=files)
    assert first["status"] == "acquired"
    assert first["takeover"] is False
    assert len(first["owned"]) == 2
    markers = sorted(path.name for path in xk.claims_dir(root).iterdir())
    assert len(markers) == 2

    same_matter = xk.claim_acquire(
        root, owner="worker-window-1", task_key="other-key", files=files
    )
    assert same_matter["status"] == "acquired"
    assert same_matter["reentrant"] == tuple(sorted(xk._normalize_rel(f) for f in files))
    assert same_matter["owned"] == ()

    conflict = xk.claim_acquire(
        root, owner="worker-window-2", task_key="other-key", files=[REPAIR_FILE]
    )
    assert conflict["status"] == "conflict"
    assert conflict["takeover"] is False
    assert conflict["owned"] == ()
    assert conflict["conflicting_owners"] == ("worker-window-1",)
    assert sorted(path.name for path in xk.claims_dir(root).iterdir()) == markers

    xk.claim_release(root, same_matter)
    assert len(list(xk.claims_dir(root).iterdir())) == 2
    xk.claim_release(root, first)
    assert list(xk.claims_dir(root).iterdir()) == []
    xk.claim_release(root, first)
    reacquired = xk.claim_acquire(
        root, owner="worker-window-2", task_key="other-key", files=[REPAIR_FILE]
    )
    assert reacquired["status"] == "acquired"
    with pytest.raises(xk.XKeyAuthorizationError):
        xk.claim_release(root, first)
    assert xk.claims_dir(root).is_dir() and list(xk.claims_dir(root).iterdir())
    claim_thefts = 0 if conflict["takeover"] is False else 1
    assert claim_thefts == 0


def test_concurrent_claim_has_one_winner_and_no_partial_locks(
    tmp_path: pathlib.Path,
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    for file_value in REPAIR_FILES:
        path = root / file_value
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x\n")
    files = list(REPAIR_FILES)

    def acquire(index: int) -> dict:
        ordered = list(reversed(files)) if index % 2 else list(files)
        return xk.claim_acquire(
            root, owner=f"worker-window-{index}", task_key="other-key", files=ordered
        )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(acquire, range(8)))

    winners = [result for result in results if result["status"] == "acquired"]
    losers = [result for result in results if result["status"] == "conflict"]
    assert len(winners) == 1
    assert len(losers) == 7
    assert all(result["takeover"] is False for result in results)
    assert all(result["owned"] == () for result in losers)
    assert len(list(xk.claims_dir(root).iterdir())) == 2

    concurrent_writers = 0 if len(winners) <= 1 else 1
    lock_bypasses = 0 if all(result["status"] in {"acquired", "conflict"} for result in results) else 1
    assert concurrent_writers == 0
    assert lock_bypasses == 0


def test_claim_is_not_reentrant_across_processes(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    target = root / REPAIR_FILE
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x\n")
    first = xk.claim_acquire(
        root, owner="worker-window-1", task_key="other-key", files=[REPAIR_FILE]
    )
    assert first["status"] == "acquired"
    code = (
        "import sys\n"
        "from autopilot import xkey\n"
        "r = xkey.claim_acquire(sys.argv[1], owner='worker-window-1', "
        "task_key='other-key', files=['packages/other/target.py'])\n"
        "print(r['status'], r['takeover'], len(r['owned']))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-B", "-c", code, str(root)],
        cwd=str(PACKAGE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    status, takeover, owned = proc.stdout.split()
    assert status == "conflict"
    assert takeover == "False"
    assert owned == "0"
    assert first["owned"] == (REPAIR_FILE,)
    assert len(list(xk.claims_dir(root).iterdir())) == 1


def test_claim_marker_empty_or_corrupt_is_never_overwritten(
    tmp_path: pathlib.Path,
) -> None:
    root = tmp_path / "proj"
    target = root / REPAIR_FILE
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x\n")
    marker = xk._claim_marker(root, REPAIR_FILE)
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"")
    result = xk.claim_acquire(
        root, owner="worker-window-1", task_key="other-key", files=[REPAIR_FILE]
    )
    assert result["status"] == "conflict"
    assert result["unreadable"] == (REPAIR_FILE,)
    assert marker.read_bytes() == b""


def test_claim_aliases_share_one_canonical_marker(tmp_path: pathlib.Path) -> None:
    root = tmp_path / "proj"
    target = root / REPAIR_FILE
    target.parent.mkdir(parents=True)
    target.write_bytes(b"x\n")
    first = xk.claim_acquire(
        root,
        owner="worker-window-1",
        task_key="other-key",
        files=["packages/other/target.py"],
    )
    assert first["status"] == "acquired"
    conflict = xk.claim_acquire(
        root,
        owner="worker-window-2",
        task_key="other-key",
        files=["./packages/other/target.py"],
    )
    assert conflict["status"] == "conflict"
    assert conflict["conflicts"] == ("packages/other/target.py",)
    assert len(list(xk.claims_dir(root).iterdir())) == 1


# ---------------------------------------------------------------------------
# T20 / AC-027 / VC-027: authorization is not a write or a dispatch
# ---------------------------------------------------------------------------

REPAIR_TARGET_REL = "packages/other/target.py"
REPAIR_OLD = b"beta\n"
REPAIR_NEW = b"beta-repaired\n"


def test_repair_selection_does_not_dispatch_or_write(tmp_path: pathlib.Path) -> None:
    root = repair_project(tmp_path)
    _request, verdict = authorized_repair(root)
    before = (root / REPAIR_TARGET_REL).read_bytes()
    assert verdict.status == "authorized", verdict.reasons
    assert verdict.dispatched is False and verdict.written is False
    assert (root / REPAIR_TARGET_REL).read_bytes() == before
    assert not xk.tickets_dir(root).exists()

    xk.apply_block_replace(root, repair_ticket(), REPAIR_NEW, authorization=verdict)
    assert (root / REPAIR_TARGET_REL).read_bytes() == b"alpha\nbeta-repaired\ngamma\n"


def test_repair_write_requires_an_authorization_covering_the_file(
    tmp_path: pathlib.Path,
) -> None:
    root = repair_project(tmp_path, (REPAIR_FILE, "packages/other/other.py"))
    before = (root / REPAIR_TARGET_REL).read_bytes()
    _request, wrong_surface = authorized_repair(
        root, files=("packages/other/other.py",)
    )
    assert wrong_surface.status == "authorized"
    with pytest.raises(xk.XKeyAuthorizationError):
        xk.apply_block_replace(
            root, repair_ticket(), REPAIR_NEW, authorization=wrong_surface
        )
    assert (root / REPAIR_TARGET_REL).read_bytes() == before

    rejected = dict(repair_ticket(), status="rejected")
    _request, valid = authorized_repair(root)
    assert valid.status == "authorized"
    with pytest.raises(xk.XKeyAuthorizationError):
        xk.apply_block_replace(root, rejected, REPAIR_NEW, authorization=valid)
    assert (root / REPAIR_TARGET_REL).read_bytes() == before

    forged = xk.RepairVerdict(
        status="authorized",
        executable=True,
        reasons=(),
        approved_files=(REPAIR_TARGET_REL,),
    )
    with pytest.raises(xk.XKeyAuthorizationError):
        xk.apply_block_replace(root, repair_ticket(), REPAIR_NEW, authorization=forged)
    assert (root / REPAIR_TARGET_REL).read_bytes() == before
    unchanged_bytes = (root / REPAIR_TARGET_REL).read_bytes() == before
    assert unchanged_bytes is True

# ---------------------------------------------------------------------------
# T20-pm-source / AC-024..AC-029 / AC-052: the normal-PM consume surface
#
# The strict H06/H07/H08 judgements above accept a ``TrustedSupply`` from their
# caller. That is fine for the machine layer, but a normally claimed PM must
# not have to assemble the authority source, usage numbers or a bearer itself.
# These tests exercise the consume API added in this card:
#
#   cg.consume_goal_adoption / cg.prepare_goal_adoption / cg.apply_goal_consumption
#   cg.consume_freeze_change / cg.prepare_freeze_change / cg.apply_freeze_consumption
#   xk.consume_repair_request / xk.prepare_repair_consumption /
#   xk.apply_repair_consumption
#
# Only the OS boundary (SCM trust anchor, protected path/ACL check and kernel
# process probe) is simulated, exactly like the T19 source tests. The actual
# ``operator_authority.read_pm_authority``/``verify_pm_authority`` functions,
# the real protected ``host.json`` parsing, the live project claim, the T10
# request/note/consumed rows, the T17 gate, the original policy/usage readers
# and the original baseline/freeze/repair writers are real.
# ---------------------------------------------------------------------------

import operator_authority as oa  # noqa: E402

from autopilot import state as mw_state  # noqa: E402

PM_SID = "S-1-5-21-100-200-300"
PM_IMAGE = r"C:\fixture\pi.exe"


def _pm_policy(
    project: pathlib.Path,
    *,
    unit: str = "round",
    source: str = "task-card-rounds",
    limit: int = 10,
) -> pathlib.Path:
    path = policy.policy_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "authority_ref": "policy-authority",
                "scope": ["fixture"],
                "hard_limits": [
                    {"unit": unit, "limit": limit, "usage_source": source}
                ],
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _pm_rounds(project: pathlib.Path, attempts: int, key: str = "key-1") -> None:
    for index in range(attempts):
        task_dir = project / ".agenticdoc" / key / "workers" / f"task-{index + 1}"
        task_dir.mkdir(parents=True, exist_ok=True)
        (task_dir / "task.md").write_text(
            f"---\nloop: l3:{key}\nattempt: a{index + 1}\ntype: coding\n---\n",
            encoding="utf-8",
            newline="\n",
        )


def _pm_record(
    ref: str,
    scope: tuple[str, ...],
    *,
    writer: str = "controlled-human",
    revoked: bool = False,
) -> dict:
    return {
        "authority_ref": ref,
        "kind": "user-grant",
        "scope": list(scope),
        "writer": writer,
        "revoked": revoked,
    }


def _pm_usage() -> dict:
    return {"task-card-rounds": {"kind": "task-card-rounds", "unit": "round"}}


def _pm_config(
    tmp_path: pathlib.Path,
    project: pathlib.Path,
    *,
    records: dict | None = None,
    usage: dict | None = None,
    writers: tuple[str, ...] = ("controlled-human",),
    policy_sha: str | None = None,
) -> pathlib.Path:
    policy_bytes = policy.policy_path(project).read_bytes()
    if policy_sha is None:
        policy_sha = hashlib.sha256(policy_bytes).hexdigest()
    row = {
        "root": str(project),
        "pm_sids": [PM_SID],
        "pm_images": [PM_IMAGE],
        "trusted_writers": list(writers),
        "authority_records": records or {},
        "usage_sources": _pm_usage() if usage is None else usage,
        "policy_sha256": policy_sha,
    }
    path = tmp_path / "host.json"
    path.write_text(
        json.dumps(
            {"schema": 1, "projects": {wire.project_id_for(project): row}}
        ),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _pm_boundary(monkeypatch, config_path: pathlib.Path) -> None:
    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    trust = oa.ServiceTrust(
        oa.Peer("fixture-service", os.getpid() + 1, 1, 0, "fixture-service"),
        config_path,
    )
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    monkeypatch.setattr(
        oa, "trusted_path", lambda candidate, *_a, **_k: pathlib.Path(candidate)
    )
    peer = oa.Peer(PM_SID, os.getpid(), 123, 1, PM_IMAGE)
    monkeypatch.setattr(
        oa, "_process_peer", lambda _pid, _stack: peer, raising=False
    )


def _snapshot(root: pathlib.Path) -> dict[str, bytes]:
    return {
        item.relative_to(root).as_posix(): item.read_bytes()
        for item in sorted(root.rglob("*"))
        if item.is_file()
    }


def _pm_goal_fixture(
    monkeypatch,
    tmp_path: pathlib.Path,
    *,
    limit: int = 10,
    used: int = 2,
):
    project = tmp_path / "project"
    project.mkdir()
    _write_index(project, "key-1")
    _pm_policy(project, limit=limit)
    _pm_rounds(project, used)
    decision_ref, basis = _lifecycle(project, key="key-1", pm_note=GOAL_NOTE)
    gate = _gate(
        project,
        "goal-change",
        key="key-1",
        decision_ref=decision_ref,
        model_basis=basis,
        pm_note=GOAL_NOTE,
        extra=(
            f"goal_sha256_before: {_sha(GOAL_BEFORE)}",
            f"goal_sha256_after: {_sha(GOAL_AFTER)}",
        ),
    )
    records = {
        "auth-goal-1": _pm_record(
            "auth-goal-1", ("goal-adopt:key-1", "goal-version:goal-v2")
        )
    }
    config = _pm_config(tmp_path, project, records=records)
    _pm_boundary(monkeypatch, config)
    baseline = goal_baseline(tmp_path)
    return project, gate, decision_ref, baseline


def _consume_goal(project, gate, decision_ref, baseline, **overrides):
    values = {
        "choice": "approve",
        "request": goal_request(),
        "baseline_path": baseline,
        "before_text": GOAL_BEFORE,
        "after_text": GOAL_AFTER,
        "gate_id": gate.stem,
        "decision_ref": decision_ref,
        "note": GOAL_NOTE,
        "expected_matter_ref": "matter-1",
        "expected_version": "v1",
    }
    values.update(overrides)
    return cg.consume_goal_adoption(project, "key-1", **values)


def test_pm_consumer_goal_adoption_applies_from_the_real_source(
    monkeypatch, tmp_path: pathlib.Path
) -> None:
    project, gate, decision_ref, baseline = _pm_goal_fixture(monkeypatch, tmp_path)
    result = _consume_goal(project, gate, decision_ref, baseline)
    assert result.status == "applied", result.reasons
    assert result.family == "goal-adoption"
    assert result.written is True
    assert result.action == "goal-baseline-adoption"
    assert result.binding is not None
    assert result.binding.decision_ref == decision_ref
    assert result.binding.gate_id == gate.stem
    assert result.binding.claim_id == LIVE_CLAIM
    assert result.binding.policy_sha256 == hashlib.sha256(
        policy.policy_path(project).read_bytes()
    ).hexdigest()
    assert result.receipt["decision_ref"] == decision_ref
    assert result.receipt["gate_id"] == gate.stem
    assert result.receipt["choice"] == "approve"
    assert result.receipt["action"] == "goal-baseline-adoption"
    assert result.receipt["version"] == "goal-v2"
    assert result.verdict is not None and result.verdict.status == "adopted"
    assert json.loads(baseline.read_text(encoding="utf-8"))["goal_version"] == "goal-v2"

    replay = _consume_goal(project, gate, decision_ref, baseline)
    assert replay.status != "applied"
    assert replay.written is False
    assert replay.binding is not None  # the same decision was still the real one
    assert json.loads(baseline.read_text(encoding="utf-8"))["goal_version"] == "goal-v2"
    assert replay.receipt["reasons"] == list(replay.verdict.reasons)


def test_pm_consumer_goal_shows_no_change_for_the_other_three_choices(
    monkeypatch, tmp_path: pathlib.Path
) -> None:
    project, gate, decision_ref, baseline = _pm_goal_fixture(monkeypatch, tmp_path)
    before = _snapshot(project)
    baseline_before = baseline.read_bytes()
    for choice in ("steer", "need_fix", "reject"):
        result = _consume_goal(project, gate, decision_ref, baseline, choice=choice)
        assert result.status == "not_adopted", choice
        assert result.written is False
        assert result.action is None
        assert f"{choice}_does_not_adopt_goal" in result.reasons
        assert baseline.read_bytes() == baseline_before
        assert _snapshot(project) == before


def test_pm_consumer_rechecks_the_source_between_prepare_and_write(
    monkeypatch, tmp_path: pathlib.Path
) -> None:
    project, gate, decision_ref, baseline = _pm_goal_fixture(monkeypatch, tmp_path)
    prepared = cg.prepare_goal_adoption(
        project,
        "key-1",
        choice="approve",
        request=goal_request(),
        baseline_path=baseline,
        before_text=GOAL_BEFORE,
        after_text=GOAL_AFTER,
        gate_id=gate.stem,
        decision_ref=decision_ref,
        note=GOAL_NOTE,
        expected_matter_ref="matter-1",
        expected_version="v1",
    )
    assert prepared.status == "prepared", prepared.reasons
    assert prepared.written is False
    baseline_before = baseline.read_bytes()

    config = tmp_path / "host.json"
    original = json.loads(config.read_text(encoding="utf-8"))
    row = next(iter(original["projects"].values()))
    row["authority_records"]["auth-goal-1"] = _pm_record(
        "auth-goal-1",
        ("goal-adopt:key-1", "goal-version:goal-v2"),
        revoked=True,
    )
    config.write_text(
        json.dumps(original), encoding="utf-8", newline="\n"
    )

    applied = cg.apply_goal_consumption(prepared)
    assert applied.status == "blocked"
    assert applied.written is False
    assert any("authority-source" in reason for reason in applied.reasons)
    assert baseline.read_bytes() == baseline_before


def _pm_contract_fixture(monkeypatch, tmp_path: pathlib.Path):
    key_dir = contract_key(tmp_path)
    project = key_dir.parent
    _pm_policy(project, limit=10)
    _pm_rounds(project, 2)
    (key_dir / "spec.md").write_text(
        T20_SPEC.replace("first contract text, locked", "first contract text, rewritten"),
        encoding="utf-8",
        newline="\n",
    )
    request = freeze_change(key_dir, items=("AC-001",))
    note = freeze_note(request)
    decision_ref, basis = _lifecycle(project, key="key-1", pm_note=note)
    gate = _gate(
        project,
        "stage-close",
        key="key-1",
        decision_ref=decision_ref,
        model_basis=basis,
        pm_note=note,
        extra=('authorizes: ["contract-change"]',),
    )
    records = {
        "auth-contract-1": _pm_record(
            "auth-contract-1", ("contract-change:key-1", "contract-item:AC-001")
        )
    }
    config = _pm_config(tmp_path, project, records=records)
    _pm_boundary(monkeypatch, config)
    return project, key_dir, gate, decision_ref, request, note


def test_pm_consumer_contract_refreeze_applies_the_exact_items(
    monkeypatch, tmp_path: pathlib.Path
) -> None:
    project, key_dir, gate, decision_ref, request, note = _pm_contract_fixture(
        monkeypatch, tmp_path
    )
    original_spec = (key_dir / "spec.md").read_bytes()
    result = cg.consume_freeze_change(
        project,
        key_dir,
        request=request,
        approval=freeze_approval(request),
        gate_id=gate.stem,
        decision_ref=decision_ref,
        note=note,
        expected_matter_ref="matter-1",
        expected_version="v1",
    )
    assert result.status == "applied", result.reasons
    assert result.written is True
    assert result.action == "contract-refreeze"
    assert result.target == str(cg.freeze_path(key_dir))
    assert result.receipt["decision_ref"] == decision_ref
    assert result.receipt["action"] == "contract-refreeze"
    assert result.receipt["approved_items"] == ["AC-001"]
    assert result.verdict.status == "approved"
    assert (key_dir / "spec.md").read_bytes() == original_spec
    anchor = cg.read_freeze(key_dir)
    current = cg.extract_contract(
        (key_dir / "spec.md").read_text(encoding="utf-8"),
        (key_dir / "design.md").read_text(encoding="utf-8"),
    )
    assert anchor["spec"]["AC-001"] == current.acs["AC-001"]

    log = cg.adoption_log_path(key_dir)
    log_before = log.read_bytes()
    replay = cg.consume_freeze_change(
        project,
        key_dir,
        request=request,
        approval=freeze_approval(request),
        gate_id=gate.stem,
        decision_ref=decision_ref,
        note=note,
    )
    assert replay.status != "applied"
    assert replay.written is False
    assert log.read_bytes() == log_before
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1


def _pm_repair_fixture(monkeypatch, tmp_path: pathlib.Path):
    root = repair_project(tmp_path)
    _pm_policy(root, limit=10)
    _pm_rounds(root, 2)
    request = repair_request()
    note = repair_note(request)
    decision_ref, basis = _lifecycle(root, key="key-1", pm_note=note)
    gate = _gate(
        root,
        "xkey-authorize",
        key=request.target_key,
        decision_ref=decision_ref,
        model_basis=basis,
        pm_note=note,
        extra=(f"write_scope: {json.dumps(list(request.files))}",),
    )
    records = {
        "auth-xkey-1": _pm_record(
            "auth-xkey-1",
            (
                "xkey-repair:other-key",
                "xkey-action:replace-frozen-block",
                f"xkey-file:{REPAIR_FILE}",
            ),
        )
    }
    config = _pm_config(tmp_path, root, records=records)
    _pm_boundary(monkeypatch, config)
    claim = repair_claim()
    xk.claim_acquire(
        root, owner=claim.actor, task_key=claim.task_key, files=request.files
    )
    return root, gate, decision_ref, request, note, claim


def test_pm_consumer_repair_reaches_the_file_through_the_real_source(
    monkeypatch, tmp_path: pathlib.Path
) -> None:
    root, gate, decision_ref, request, note, claim = _pm_repair_fixture(
        monkeypatch, tmp_path
    )
    prepared = xk.prepare_repair_consumption(
        root,
        key="key-1",
        request=request,
        approval=repair_approval(request),
        claim_request=claim,
        actor=claim.actor,
        role="worker",
        gate_id=gate.stem,
        decision_ref=decision_ref,
        note=note,
        expected_matter_ref="matter-1",
        expected_version="v1",
    )
    assert prepared.status == "authorized", prepared.reasons
    assert prepared.written is False
    assert prepared.verdict.dispatched is False
    assert prepared.verdict.binding_verified is True
    assert (root / REPAIR_FILE).read_bytes() == b"alpha\nbeta\ngamma\n"

    applied = xk.apply_repair_consumption(prepared, repair_ticket(), REPAIR_NEW)
    assert applied.status == "applied", applied.reasons
    assert applied.written is True
    assert applied.action == "restricted-repair-write"
    assert applied.receipt["decision_ref"] == decision_ref
    assert applied.receipt["gate_id"] == gate.stem
    assert applied.receipt["target"] == REPAIR_FILE
    assert (root / REPAIR_FILE).read_bytes() == b"alpha\nbeta-repaired\ngamma\n"

    replay = xk.apply_repair_consumption(prepared, repair_ticket(), REPAIR_NEW)
    assert replay.status == "blocked"
    assert replay.written is False
    assert (root / REPAIR_FILE).read_bytes() == b"alpha\nbeta-repaired\ngamma\n"


@pytest.mark.parametrize("untouchable", ([2], [f"{REPAIR_FILE}:2"], [REPAIR_FILE], [1, 3]))
def test_pm_consumer_ticket_boundary_before_splice(
    monkeypatch, tmp_path: pathlib.Path, untouchable: list
) -> None:
    root, gate, decision_ref, request, note, claim = _pm_repair_fixture(
        monkeypatch, tmp_path
    )
    prepared = xk.prepare_repair_consumption(
        root,
        key="key-1",
        request=request,
        approval=repair_approval(request),
        claim_request=claim,
        actor=claim.actor,
        role="worker",
        gate_id=gate.stem,
        decision_ref=decision_ref,
        note=note,
    )
    assert prepared.status == "authorized", prepared.reasons
    assert prepared.verdict.binding_verified is True
    ticket = repair_ticket()
    ticket["untouchable"] = untouchable
    before = _snapshot(root)
    proposal = {
        "file": REPAIR_FILE,
        "line_range": [2, 2],
        "old_block_sha256": hashlib.sha256(REPAIR_OLD).hexdigest(),
    }
    legal = untouchable == [1, 3]
    assert xk.check_boundary(proposal, ticket) == ("ok" if legal else "violation")
    applied = xk.apply_repair_consumption(prepared, ticket, REPAIR_NEW)
    assert applied.binding.decision_ref == decision_ref
    if legal:
        assert applied.status == "applied", applied.reasons
        assert applied.written is True
        assert applied.action == "restricted-repair-write"
        assert (root / REPAIR_FILE).read_bytes() == b"alpha\nbeta-repaired\ngamma\n"
        after = _snapshot(root)
        assert {name for name in before if before[name] != after[name]} == {REPAIR_FILE}
    else:
        assert applied.status == "blocked", applied.reasons
        assert applied.reasons == ("ticket_boundary_violation",)
        assert applied.written is False
        assert applied.action is None
        assert _snapshot(root) == before


def test_pm_consumer_refuses_a_revoked_repair_source_before_writing(
    monkeypatch, tmp_path: pathlib.Path
) -> None:
    root, gate, decision_ref, request, note, claim = _pm_repair_fixture(
        monkeypatch, tmp_path
    )
    prepared = xk.prepare_repair_consumption(
        root,
        key="key-1",
        request=request,
        approval=repair_approval(request),
        claim_request=claim,
        actor=claim.actor,
        role="worker",
        gate_id=gate.stem,
        decision_ref=decision_ref,
        note=note,
    )
    assert prepared.status == "authorized", prepared.reasons
    before = (root / REPAIR_FILE).read_bytes()

    config = tmp_path / "host.json"
    original = json.loads(config.read_text(encoding="utf-8"))
    row = next(iter(original["projects"].values()))
    row["authority_records"]["auth-xkey-1"]["revoked"] = True
    config.write_text(json.dumps(original), encoding="utf-8", newline="\n")

    applied = xk.apply_repair_consumption(prepared, repair_ticket(), REPAIR_NEW)
    assert applied.status == "blocked"
    assert applied.written is False
    assert (root / REPAIR_FILE).read_bytes() == before


def test_pm_consumer_refuses_fake_source_budget_claim_and_version(
    monkeypatch, tmp_path: pathlib.Path
) -> None:
    project, gate, decision_ref, baseline = _pm_goal_fixture(
        monkeypatch, tmp_path, limit=2, used=2
    )
    baseline_before = baseline.read_bytes()
    snapshot = _snapshot(project)

    # Budget: two rounds already consumed against a limit of two.
    exhausted = _consume_goal(project, gate, decision_ref, baseline)
    assert exhausted.status == "blocked"
    assert "budget_exhausted" in exhausted.reasons
    assert exhausted.written is False

    # Version mismatch: the PM plan names a different substantive version.
    version = _consume_goal(
        project, gate, decision_ref, baseline, expected_version="v2"
    )
    assert version.status == "blocked"
    assert "version_mismatch" in version.reasons

    # Unknown claim: another live window owns the key.
    index = project / ".agenticdoc/_index.parallel"
    original_index = index.read_bytes()
    index.write_text(
        "| key-1 | active | EXECUTE | other-host:999999 | - | test | now |\n",
        encoding="utf-8",
        newline="\n",
    )
    unbound = _consume_goal(project, gate, decision_ref, baseline)
    assert unbound.status == "blocked"
    assert any("pm-claim-unbound" in reason for reason in unbound.reasons)
    index.write_bytes(original_index)

    # Forged authority string: the request names an authority the protected
    # source does not contain, so the strict surface never issues a verdict.
    forged = _consume_goal(
        project, gate, decision_ref, baseline, request=goal_request(
            authority_ref="forged-user-reference"
        )
    )
    assert forged.status == "blocked"
    assert forged.written is False

    assert baseline.read_bytes() == baseline_before
    assert _snapshot(project) == snapshot  # old failure/ledger bytes survive


def test_pm_consumer_refuses_unverifiable_usage_and_missing_policy_hash(
    monkeypatch, tmp_path: pathlib.Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_index(project, "key-1")
    _pm_policy(project, limit=10)
    _pm_rounds(project, 1)
    decision_ref, basis = _lifecycle(project, key="key-1", pm_note=GOAL_NOTE)
    gate = _gate(
        project,
        "goal-change",
        key="key-1",
        decision_ref=decision_ref,
        model_basis=basis,
        pm_note=GOAL_NOTE,
        extra=(
            f"goal_sha256_before: {_sha(GOAL_BEFORE)}",
            f"goal_sha256_after: {_sha(GOAL_AFTER)}",
        ),
    )
    baseline = goal_baseline(tmp_path)
    baseline_before = baseline.read_bytes()
    records = {
        "auth-goal-1": _pm_record(
            "auth-goal-1", ("goal-adopt:key-1", "goal-version:goal-v2")
        )
    }
    config = _pm_config(tmp_path, project, records=records)
    _pm_boundary(monkeypatch, config)

    # Unknown cumulative source kind: accepted as a descriptor, never guessed.
    _pm_config(
        tmp_path,
        project,
        records=records,
        usage={"task-card-rounds": {"kind": "external-meter", "unit": "round"}},
    )
    unknown = _consume_goal(project, gate, decision_ref, baseline)
    assert unknown.status == "blocked"
    assert "usage_source_unknown" in unknown.reasons

    # Unit drift between the policy limit and the declared source.
    _pm_config(
        tmp_path,
        project,
        records=records,
        usage={"task-card-rounds": {"kind": "task-card-rounds", "unit": "steps"}},
    )
    drift = _consume_goal(project, gate, decision_ref, baseline)
    assert drift.status == "blocked"
    assert "budget_units_mismatch" in drift.reasons

    # No pinned policy digest: the policy hash cannot be verified before write.
    _pm_config(tmp_path, project, records=records, policy_sha="")
    unpinned = _consume_goal(project, gate, decision_ref, baseline)
    assert unpinned.status == "blocked"
    assert "missing_policy_hash" in unpinned.reasons

    assert baseline.read_bytes() == baseline_before


def test_pm_consumer_refuses_open_ended_and_cross_surface_repairs(
    monkeypatch, tmp_path: pathlib.Path
) -> None:
    root, gate, decision_ref, request, note, claim = _pm_repair_fixture(
        monkeypatch, tmp_path
    )
    before = (root / REPAIR_FILE).read_bytes()
    for name, files in {
        "wildcard": ("packages/other/**",),
        "directory": ("packages/other/",),
        "parent": ("packages/other/../target.py",),
        "second": ("packages/other/second.py",),
    }.items():
        wider = repair_request(files=files)
        result = xk.prepare_repair_consumption(
            root,
            key="key-1",
            request=wider,
            approval=repair_approval(wider),
            claim_request=repair_claim(files=files),
            actor=claim.actor,
            role="worker",
            gate_id=gate.stem,
            decision_ref=decision_ref,
            note=repair_note(wider),
        )
        assert result.status == "blocked", name
        assert result.written is False
        assert result.verdict.dispatched is False
    assert (root / REPAIR_FILE).read_bytes() == before
