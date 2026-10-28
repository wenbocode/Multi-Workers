"""test_dp_consolidation_recovery.py - T07: read-only decision-policy validation.

Hermetic pytest suite for :mod:`decision_policy` (AC-008, AC-020, AC-021,
AC-022, AC-034, AC-035, AC-036, AC-037 / VC-008, VC-020, VC-021, VC-022,
VC-034, VC-035, VC-036, VC-037).

What the module under test must do (and what these tests pin down):

* load ``.agenticdoc/_autopilot/decision-policy.json`` read-only; a missing file
  means *zero* permissions and an illegal file is fail-closed (never a silent
  default grant, never a fallback to the frozen 21-key autopilot config);
* resolve ``authority_ref`` against an authority source produced by a real
  controlled writer - ``preauthorized``/``token``/``origin``/``tty``/``role``
  self-assertions inside the policy are *not* authority;
* verify hard-limit unit / usage source / cumulative usage and refuse any
  spend that would overrun the hard limit, with no usage reset;
* refuse any hard-limit increase that has no concrete human authorization
  (delta + purpose + risk) - a DP choice can never raise its own limit;
* grant a soft round extension only for the explicit delta of a complete PM
  note (progress, budget basis, next goal, plan, stop criterion) - remaining
  hard budget alone is not authorization;
* treat a pending-review event as an evaluation trigger only (no automatic
  resume, no automatic human escalation);
* resume a halted stage only with a complete note, a valid approval and the
  policy's own observation/stop conditions, preserving the stop facts and the
  consumed budget;
* keep the H12 brake engaged when the channel is not isolated, the transport
  is unavailable, the preauthorization/elimination evidence is missing, a
  machine check fails or the user disabled automation - with a concrete
  authorization/information question and the breaker history preserved;
* re-trip the brake when the stop condition is observed again.

Isolation: every fixture project, authority record and process HOME/TEMP lives
under this card's evidence directory (``dpc-t07-policy/fixture``), never in the
source tree. The authority records are written by a real, byte-level fixture
writer (tmp + ``os.replace``) and then parsed back through the production
``parse_authority_record`` seam. No network, no provider, no decision CLI, no
live policy/gate/ledger, no pycache.
"""

from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import sys
import uuid

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision_policy as policy_mod  # noqa: E402

PACKAGE_ROOT = pathlib.Path(__file__).resolve().parent
EVIDENCE_ROOT = PACKAGE_ROOT.parents[2] / "evidence" / "implementation" / "dpc-t07-policy"
FIXTURE_ROOT = pathlib.Path(
    os.environ.get("DPC_T07_FIXTURE_ROOT") or (EVIDENCE_ROOT / "fixture")
)

TRUSTED_WRITER = "pm-controlled-authority-writer"
TRUSTED_WRITERS = frozenset({TRUSTED_WRITER})
CONTROLLED_CHANNELS = frozenset({"pm-controlled-recovery"})


def _verify(tag: str, **counters: int) -> None:
    print(f"[VERIFY] {tag}: " + " ".join(f"{k}={v}" for k, v in counters.items()))


def _codes(issues) -> tuple[str, ...]:
    return tuple(issue.code for issue in issues)


# ── fixture writers ──────────────────────────────────────────────────────────


class FixtureAuthorityWriter:
    """Real byte-level writer for the isolated fixture only.

    Stands in for the production controlled writer (the real user grant /
    controlled config recorder). It writes an authority record under the
    fixture project with tmp + ``os.replace`` and hands the bytes back through
    the production parser - the policy file itself never contributes authority.
    """

    def __init__(self, project: pathlib.Path, writer_id: str = TRUSTED_WRITER) -> None:
        self.root = project / "authority"
        self.root.mkdir(parents=True, exist_ok=True)
        self.writer_id = writer_id

    def grant(
        self,
        authority_ref: str,
        scopes,
        *,
        kind: str = "user-grant",
        revoked: bool = False,
        recorded_at: str = "2026-10-26T00:00:00+00:00",
        supersedes=None,
    ):
        payload = {
            "authority_ref": authority_ref,
            "kind": kind,
            "scope": list(scopes),
            "writer": self.writer_id,
            "revoked": revoked,
            "recorded_at": recorded_at,
            "supersedes": list(supersedes or ()),
        }
        path = self.root / f"{authority_ref}.json"
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
        os.replace(tmp, path)
        raw = json.loads(path.read_text(encoding="utf-8"))
        return policy_mod.parse_authority_record(raw, trusted_writers=TRUSTED_WRITERS)


def _new_project(name: str) -> pathlib.Path:
    root = FIXTURE_ROOT / f"{name}-{uuid.uuid4().hex[:10]}"
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True, exist_ok=True)
    return root


def _policy_doc(**overrides) -> dict:
    doc: dict = {
        "schema_version": 1,
        "authority_ref": "grant-dpc-t07",
        "scope": ["key:dpc-t07", "action:gate-approve"],
        "hard_limits": [
            {"unit": "round", "limit": 2, "usage_source": "task-card-rounds"},
        ],
        "soft_round_extension": {
            "allowed": True,
            "scope": ["extension:soft-round"],
            "authority_ref": "grant-soft-round",
        },
        "recovery": {
            "allowed_origins": ["pm-controlled"],
            "scope": ["recovery:halted", "recovery:breaker"],
            "authority_ref": "grant-recovery",
            "observation_conditions": ["same-failure-reappears"],
            "stop_conditions": ["recovery-reason-reappears"],
        },
    }
    doc.update(overrides)
    return doc


def _load(project: pathlib.Path, doc: dict | None = None):
    if doc is not None:
        path = policy_mod.policy_path(project)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return policy_mod.load_policy(project)


def _source(records) -> dict:
    return {record.authority_ref: record for record in records if record is not None}


def _grants(project: pathlib.Path, writer_id: str = TRUSTED_WRITER, **kwargs) -> dict:
    writer = FixtureAuthorityWriter(project, writer_id=writer_id)
    records = []
    for ref, scopes in kwargs.items():
        record, issues = writer.grant(ref, scopes)
        assert issues == (), [issue.code for issue in issues]
        records.append(record)
    return _source(records)


def _full_grants(project: pathlib.Path) -> dict:
    """The fixture's controlled writer records the whole legal surface.

    ``grant-breaker`` is a *replacement* of the policy's recovery
    authorization, so it carries the explicit ``supersedes`` relation the
    controlled writer records; nothing here is self-asserted by a request.
    """
    writer = FixtureAuthorityWriter(project)
    records = []
    specs = {
        "grant-dpc-t07": (["key:dpc-t07", "action:gate-approve"], ()),
        "grant-soft-round": (["extension:soft-round"], ()),
        "grant-recovery": (["recovery:halted", "recovery:breaker"], ()),
        "grant-breaker": (["recovery:breaker"], ("grant-recovery",)),
    }
    for ref, (scopes, supersedes) in specs.items():
        record, issues = writer.grant(ref, scopes, supersedes=supersedes)
        assert issues == (), [issue.code for issue in issues]
        records.append(record)
    return _source(records)


NOTE_OK = {
    "progress": "3 of 4 regression checks green, 1 rework",
    "budget_unit": "round",
    "budget_amount": 1,
    "budget_source": "task-card-rounds",
    "next_goal": "close the remaining VC-008 negative",
    "next_plan": "rerun the assigned test file",
    "stop_criterion": "two consecutive green runs",
}

HALTED_OK = {
    "stage_halted": True,
    "halt_origin": "technical",
    "hard_guard_active": False,
    "hard_guard_cleared": [],
    "choice": "approve",
    "required_scope": ["recovery:halted"],
    "note": {
        "stop_reason": "worker wrote no activity for 10 minutes",
        "elimination_evidence": ["watchdog trace shows the hang is gone"],
        "stage_version": "stage-2:v7",
        "affected_keys": ["dpc-t07-policy"],
        "target_plan": "rerun the assigned test file",
        "authority_ref": "grant-recovery",
        "residual_budget": {"round": 1},
        "stop_criterion": "two consecutive green runs",
    },
}

BREAKER_OK = {
    "channel": "pm-controlled-recovery",
    "tripped_chain": "auto-pass",
    "origin": "pm-controlled",
    "reason_elimination_evidence": ["backend 503 absent for 30 minutes"],
    "preauthorization_ref": "grant-breaker",
    "machine_checks": {"brake-isolated": True, "policy-valid": True},
    "transport_available": True,
    "user_disabled": False,
    "required_scope": ["recovery:breaker"],
    "choice": "approve",
}


@pytest.fixture(autouse=True)
def _isolated_process_env(monkeypatch):
    for name in ("HOME", "USERPROFILE", "TMPDIR", "TEMP", "TMP"):
        target = FIXTURE_ROOT / "process-env" / name.lower()
        target.mkdir(parents=True, exist_ok=True)
        monkeypatch.setenv(name, str(target))


# ── AC-008: fail-closed policy load / gate release ───────────────────────────


def test_policy_absent_yields_zero_permissions():
    project = _new_project("absent")
    load = _load(project)
    assert load.status == "absent"
    assert load.usable is False
    assert "policy-absent" in _codes(load.issues)

    verdict = policy_mod.evaluate_gate(
        load,
        choice="approve",
        hard_checks={"claim": True, "write-face": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07", "action:gate-approve"),
        authority_source={},
        trusted_writers=TRUSTED_WRITERS,
    )
    assert verdict.allowed is False
    assert verdict.release_scope == ()
    assert verdict.project_closed is False
    assert "policy-absent" in _codes(verdict.reasons)
    _verify(
        "VC-008",
        unauthorized_releases=int(verdict.allowed),
        unauthorized_effects=int(bool(verdict.release_scope)),
        missing_failure_reasons=int("policy-absent" not in _codes(verdict.reasons)),
    )


def test_illegal_policy_json_is_fail_closed():
    project = _new_project("badjson")
    path = policy_mod.policy_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8")
    load = _load(project)
    assert load.status == "invalid"
    assert load.usable is False
    assert "policy-not-json" in _codes(load.issues)
    verdict = policy_mod.evaluate_gate(
        load,
        choice="approve",
        hard_checks={"claim": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07",),
        authority_source={},
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not verdict.allowed
    assert "policy-not-json" in _codes(verdict.reasons)


def test_self_reported_authority_fields_are_not_authority():
    project = _new_project("selfreport")
    doc = _policy_doc(
        preauthorized=True,
        token="page-token-123",
        origin="tty",
        role="PM",
    )
    load = _load(project, doc)
    assert load.usable is False
    codes = _codes(load.issues)
    assert codes.count("policy-unknown-field") == 4
    fields = {issue.field for issue in load.issues if issue.code == "policy-unknown-field"}
    assert fields == {"preauthorized", "token", "origin", "role"}

    verdict = policy_mod.evaluate_gate(
        load,
        choice="approve",
        hard_checks={"claim": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07",),
        authority_source={},
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not verdict.allowed
    _verify(
        "VC-008",
        unauthorized_releases=int(verdict.allowed),
        unauthorized_effects=int(bool(verdict.release_scope)),
        missing_failure_reasons=int("policy-unknown-field" not in _codes(verdict.reasons)),
    )


def test_hard_limit_needs_explicit_unit_source_and_not_a_config_knob():
    project = _new_project("units")
    missing_source = _policy_doc(
        hard_limits=[{"unit": "round", "limit": 2}],
    )
    load = _load(project, missing_source)
    assert "policy-usage-source-missing" in _codes(load.issues)

    config_knob = _policy_doc(
        hard_limits=[{"unit": "round_budget", "limit": 2, "usage_source": "config"}],
    )
    load = _load(project, config_knob)
    assert "policy-unit-not-authority" in _codes(load.issues)

    worker_timeout = _policy_doc(
        hard_limits=[{"unit": "worker_timeout_min", "limit": 30, "usage_source": "config"}],
    )
    load = _load(project, worker_timeout)
    assert "policy-unit-not-authority" in _codes(load.issues)


def test_recovery_rule_missing_conditions_blocks_only_recovery():
    project = _new_project("recovrule")
    doc = _policy_doc()
    del doc["recovery"]["observation_conditions"]
    load = _load(project, doc)
    assert load.usable is True
    assert "recovery-observation-missing" in _codes(load.recovery_issues)

    verdict = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK),
        authority_source=_full_grants(project),
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not verdict.allowed
    assert "recovery-observation-missing" in _codes(verdict.reasons)

    stop_missing = _policy_doc()
    del stop_missing["recovery"]["stop_conditions"]
    load2 = _load(project, stop_missing)
    assert "recovery-stop-missing" in _codes(load2.recovery_issues)
    # the budget surface stays usable: only the recovery path is closed
    spend = policy_mod.check_spend(load2, unit="round", amount=1, usage={"round": 1})
    assert spend.allowed is True

    wildcard = _policy_doc()
    wildcard["recovery"]["allowed_origins"] = ["*"]
    assert "recovery-origin-wildcard" in _codes(_load(project, wildcard).recovery_issues)


def test_authority_ref_must_resolve_to_a_trusted_controlled_writer():
    project = _new_project("authority")
    load = _load(project, _policy_doc())

    missing = policy_mod.evaluate_gate(
        load,
        choice="approve",
        hard_checks={"claim": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07",),
        authority_source={},
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not missing.allowed
    assert "authority-unresolved" in _codes(missing.reasons)

    writer = FixtureAuthorityWriter(project, writer_id="worker-self-report")
    record, issues = writer.grant("grant-dpc-t07", ["key:dpc-t07"])
    assert record is None
    assert "authority-writer-untrusted" in _codes(issues)

    untrusted = policy_mod.evaluate_gate(
        load,
        choice="approve",
        hard_checks={"claim": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07",),
        authority_source={},
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not untrusted.allowed

    good = policy_mod.evaluate_gate(
        load,
        choice="approve",
        hard_checks={"claim": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07",),
        authority_source=_grants(project, **{"grant-dpc-t07": ["key:dpc-t07"]}),
        trusted_writers=TRUSTED_WRITERS,
    )
    assert good.allowed is True
    assert good.release_scope == ("key:dpc-t07",)


def test_revoked_and_out_of_scope_authority_blocks_release():
    project = _new_project("revoked")
    load = _load(project, _policy_doc())

    writer = FixtureAuthorityWriter(project)
    revoked, issues = writer.grant("grant-dpc-t07", ["key:dpc-t07"], revoked=True)
    assert issues == ()
    verdict = policy_mod.evaluate_gate(
        load,
        choice="approve",
        hard_checks={"claim": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07",),
        authority_source=_source([revoked]),
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not verdict.allowed
    assert "authority-revoked" in _codes(verdict.reasons)

    narrow = _grants(project, **{"grant-dpc-t07": ["key:dpc-other"]})
    scoped = policy_mod.evaluate_gate(
        load,
        choice="approve",
        hard_checks={"claim": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07",),
        authority_source=narrow,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not scoped.allowed
    assert "authority-scope-uncovered" in _codes(scoped.reasons)


def test_gate_missing_or_failed_conditions_never_release():
    project = _new_project("gate")
    load = _load(project, _policy_doc())
    source = _full_grants(project)

    outcomes = [
        policy_mod.evaluate_gate(
            load,
            choice="approve",
            hard_checks={"claim": True},
            automation_enabled=False,
            required_scope=("key:dpc-t07",),
            authority_source=source,
            trusted_writers=TRUSTED_WRITERS,
        ),
        policy_mod.evaluate_gate(
            load,
            choice="approve",
            hard_checks={},
            automation_enabled=True,
            required_scope=("key:dpc-t07",),
            authority_source=source,
            trusted_writers=TRUSTED_WRITERS,
        ),
        policy_mod.evaluate_gate(
            load,
            choice="approve",
            hard_checks={"claim": False, "write-face": True},
            automation_enabled=True,
            required_scope=("key:dpc-t07",),
            authority_source=source,
            trusted_writers=TRUSTED_WRITERS,
        ),
        policy_mod.evaluate_gate(
            load,
            choice="reject",
            hard_checks={"claim": True},
            automation_enabled=True,
            required_scope=("key:dpc-t07",),
            authority_source=source,
            trusted_writers=TRUSTED_WRITERS,
        ),
        policy_mod.evaluate_gate(
            load,
            choice="approve",
            hard_checks={"claim": True},
            automation_enabled=True,
            required_scope=("key:dpc-t07", "action:cross-key-repair"),
            authority_source=source,
            trusted_writers=TRUSTED_WRITERS,
        ),
    ]
    codes = [set(_codes(v.reasons)) for v in outcomes]
    assert "automation-disabled" in codes[0]
    assert "hard-checks-missing" in codes[1]
    assert "hard-check-failed" in codes[2]
    failed_fields = {i.field for i in outcomes[2].reasons if i.code == "hard-check-failed"}
    assert failed_fields == {"claim"}
    assert "choice-not-approve" in codes[3]
    assert outcomes[3].follow_up is None  # reject never maps to a follow-up action
    assert "scope-not-granted" in codes[4]
    assert all(v.allowed is False for v in outcomes)
    assert all(v.project_closed is False for v in outcomes)
    _verify(
        "VC-008",
        unauthorized_releases=sum(int(v.allowed) for v in outcomes),
        unauthorized_effects=sum(int(bool(v.release_scope)) for v in outcomes),
        missing_failure_reasons=sum(int(not v.reasons) for v in outcomes),
    )


def test_steer_and_need_fix_do_not_release():
    project = _new_project("followup")
    load = _load(project, _policy_doc())
    source = _full_grants(project)
    steer = policy_mod.evaluate_gate(
        load,
        choice="steer",
        hard_checks={"claim": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07",),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    need_fix = policy_mod.evaluate_gate(
        load,
        choice="need_fix",
        hard_checks={"claim": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07",),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    reject = policy_mod.evaluate_gate(
        load,
        choice="reject",
        hard_checks={"claim": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07",),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert steer.allowed is False and steer.follow_up == "dp-pm-steer"
    assert need_fix.allowed is False and need_fix.follow_up == "dp-auto"
    assert reject.allowed is False and reject.follow_up is None
    assert all(v.project_closed is False for v in (steer, need_fix, reject))
    _verify(
        "VC-008",
        unauthorized_releases=sum(int(v.allowed) for v in (steer, need_fix, reject)),
        unauthorized_effects=sum(int(bool(v.release_scope)) for v in (steer, need_fix, reject)),
        missing_failure_reasons=sum(int(not v.reasons) for v in (steer, need_fix, reject)),
    )


# ── AC-021: hard budget, cumulative usage, no self-granted limits ────────────


def test_spend_blocks_unknown_unit_and_unknown_usage():
    project = _new_project("spend")
    load = _load(project, _policy_doc())

    unknown_unit = policy_mod.check_spend(load, unit="token", amount=1, usage={"round": 0})
    assert not unknown_unit.allowed
    assert "budget-unit-unknown" in _codes(unknown_unit.reasons)

    unknown_usage = policy_mod.check_spend(load, unit="round", amount=1, usage={})
    assert not unknown_usage.allowed
    assert "budget-usage-unknown" in _codes(unknown_usage.reasons)

    invalid_amount = policy_mod.check_spend(load, unit="round", amount=0, usage={"round": 0})
    assert not invalid_amount.allowed
    assert "budget-amount-invalid" in _codes(invalid_amount.reasons)

    bad_usage = policy_mod.check_spend(load, unit="round", amount=1, usage={"round": -1})
    assert not bad_usage.allowed
    assert "budget-usage-unknown" in _codes(bad_usage.reasons)


def test_spend_accumulates_and_never_resets_usage():
    project = _new_project("cumulative")
    load = _load(project, _policy_doc())

    first = policy_mod.check_spend(load, unit="round", amount=1, usage={"round": 0})
    assert first.allowed is True
    assert (first.used_before, first.requested, first.used_after) == (0, 1, 1)
    assert first.limit == 2
    assert first.usage_source == "task-card-rounds"

    second = policy_mod.check_spend(load, unit="round", amount=1, usage={"round": first.used_after})
    assert second.allowed is True
    assert second.used_after == 2

    overrun = policy_mod.check_spend(load, unit="round", amount=1, usage={"round": second.used_after})
    assert overrun.allowed is False
    assert "budget-overrun" in _codes(overrun.reasons)
    assert overrun.used_before == 2
    assert overrun.used_after is None  # the overrunning spend produced no consumption
    _verify(
        "VC-021",
        hard_budget_overruns=int(overrun.used_after is not None),
        self_granted_limits=0,
        reset_usage=int(
            min(first.used_after, second.used_after, overrun.used_before) < 0
            or second.used_after < first.used_after
        ),
    )


def test_limit_increase_requires_concrete_human_authorization():
    project = _new_project("limit")
    load = _load(project, _policy_doc())
    human = _grants(project, **{"grant-limit": ["budget:increase"]})

    no_grant = policy_mod.check_limit_change(
        load,
        unit="round",
        new_limit=4,
        grant=None,
        authority_source=human,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not no_grant.allowed
    assert "limit-grant-missing" in _codes(no_grant.reasons)
    assert no_grant.limit_after is None

    incompletes = {
        "limit-grant-purpose-missing": {"delta": 2},
        "limit-grant-risk-missing": {"delta": 2, "purpose": "close the stage"},
        "limit-grant-delta-mismatch": {
            "delta": 1,
            "purpose": "close the stage",
            "risk": "one extra round of spend",
        },
        "limit-grant-unit-mismatch": {
            "unit": "token",
            "delta": 2,
            "purpose": "close the stage",
            "risk": "one extra round of spend",
        },
    }
    for expected, extra in incompletes.items():
        grant = {"authority_ref": "grant-limit", **extra}
        verdict = policy_mod.check_limit_change(
            load,
            unit="round",
            new_limit=4,
            grant=grant,
            authority_source=human,
            trusted_writers=TRUSTED_WRITERS,
        )
        assert not verdict.allowed, expected
        assert expected in _codes(verdict.reasons), (expected, _codes(verdict.reasons))

    # a controlled-config record is not a human authorization for a hard limit
    config_grant = {
        "authority_ref": "grant-config",
        "delta": 2,
        "purpose": "close the stage",
        "risk": "one extra round of spend",
    }
    writer = FixtureAuthorityWriter(project)
    record, issues = writer.grant("grant-config", ["budget:increase"], kind="controlled-config")
    assert issues == ()
    controlled = _source([record])
    not_human = policy_mod.check_limit_change(
        load,
        unit="round",
        new_limit=4,
        grant=config_grant,
        authority_source=controlled,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not not_human.allowed
    assert "limit-grant-not-human" in _codes(not_human.reasons)

    allowed = policy_mod.check_limit_change(
        load,
        unit="round",
        new_limit=4,
        grant={
            "authority_ref": "grant-limit",
            "delta": 2,
            "purpose": "close the remaining VC-008 negative",
            "risk": "up to two extra rounds of spend",
        },
        authority_source=human,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert allowed.allowed is True
    assert (allowed.limit_before, allowed.limit_after) == (2, 4)

    lowered = policy_mod.check_limit_change(
        load,
        unit="round",
        new_limit=1,
        grant=None,
        authority_source={},
        trusted_writers=TRUSTED_WRITERS,
    )
    assert lowered.allowed is True
    assert lowered.limit_after == 1

    _verify(
        "VC-021",
        hard_budget_overruns=0,
        self_granted_limits=sum(
            int(v.allowed) for v in (no_grant, not_human)
        ),
        reset_usage=0,
    )


# ── AC-020: soft round extension ────────────────────────────────────────────


def test_soft_extension_needs_policy_authorization():
    project = _new_project("extauth")
    source = _full_grants(project)

    disabled = _policy_doc(
        soft_round_extension={
            "allowed": False,
            "scope": ["extension:soft-round"],
            "authority_ref": "grant-soft-round",
        }
    )
    verdict = policy_mod.evaluate_soft_extension(
        _load(project, disabled),
        note=dict(NOTE_OK),
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not verdict.allowed
    assert "extension-not-authorized" in _codes(verdict.reasons)

    unresolvable = _policy_doc()
    unresolvable["soft_round_extension"]["authority_ref"] = "grant-missing"
    verdict = policy_mod.evaluate_soft_extension(
        _load(project, unresolvable),
        note=dict(NOTE_OK),
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not verdict.allowed
    assert "authority-unresolved" in _codes(verdict.reasons)


def test_soft_extension_needs_a_complete_pm_note():
    project = _new_project("extnote")
    load = _load(project, _policy_doc())
    source = _full_grants(project)

    cases = {
        "note-progress-missing": "progress",
        "note-goal-missing": "next_goal",
        "note-plan-missing": "next_plan",
        "note-stop-missing": "stop_criterion",
        "note-budget-source-missing": "budget_source",
    }
    for expected, key in cases.items():
        note = dict(NOTE_OK)
        note.pop(key)
        verdict = policy_mod.evaluate_soft_extension(
            load,
            note=note,
            usage={"round": 1},
            authority_source=source,
            trusted_writers=TRUSTED_WRITERS,
        )
        assert not verdict.allowed, expected
        assert expected in _codes(verdict.reasons), (expected, _codes(verdict.reasons))

    no_budget = dict(NOTE_OK)
    no_budget.pop("budget_unit")
    verdict = policy_mod.evaluate_soft_extension(
        load,
        note=no_budget,
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert "note-budget-missing" in _codes(verdict.reasons)


def test_hard_balance_alone_cannot_extend_rounds():
    project = _new_project("hardbalance")
    load = _load(project, _policy_doc())
    source = _full_grants(project)
    note = dict(NOTE_OK, budget_source="hard-balance")
    verdict = policy_mod.evaluate_soft_extension(
        load,
        note=note,
        usage={"round": 0},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not verdict.allowed
    assert "note-budget-source-hard-balance" in _codes(verdict.reasons)
    assert verdict.granted is None

    overrun = policy_mod.evaluate_soft_extension(
        load,
        note=dict(NOTE_OK),
        usage={"round": 2},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not overrun.allowed
    assert "budget-overrun" in _codes(overrun.reasons)
    assert overrun.granted is None
    _verify(
        "VC-020",
        unbounded_extensions=int(any(v.granted is not None for v in (verdict, overrun))),
        unsupported_extensions=sum(int(v.allowed) for v in (verdict, overrun)),
    )


def test_soft_extension_is_limited_to_the_explicit_delta():
    project = _new_project("extdelta")
    load = _load(project, _policy_doc())
    source = _full_grants(project)

    verdict = policy_mod.evaluate_soft_extension(
        load,
        note=dict(NOTE_OK),
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert verdict.allowed is True
    assert verdict.granted == 1
    assert verdict.granted == NOTE_OK["budget_amount"]
    assert verdict.used_after == 2
    assert verdict.unit == "round"

    unbounded = policy_mod.evaluate_soft_extension(
        load,
        note=dict(NOTE_OK, budget_amount=None),
        usage={"round": 0},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not unbounded.allowed
    assert "note-budget-missing" in _codes(unbounded.reasons)
    assert unbounded.granted is None
    _verify(
        "VC-020",
        unbounded_extensions=int(unbounded.granted is not None),
        unsupported_extensions=0,
    )


# ── AC-022: pending-review recheck ──────────────────────────────────────────


def test_pending_review_event_only_triggers_evaluation():
    project = _new_project("pending")
    load = _load(project, _policy_doc())
    source = _full_grants(project)
    state = {
        "pending_review": True,
        "goal_effective": True,
        "blocker_cleared": True,
        "evidence": ["fresh integration run"],
        "choice": None,
        "required_scope": ["key:dpc-t07"],
        "budget_unit": "round",
        "budget_amount": 1,
        "usage": {"round": 0},
    }
    verdict = policy_mod.evaluate_pending_review(
        load,
        trigger={"kind": "expiry"},
        state=state,
        usage=state["usage"],
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert verdict.allowed is False
    assert verdict.resume_scope == ()
    assert verdict.requires_human is False  # an event never *forces* a human wait
    assert "decision-missing" in _codes(verdict.reasons)
    _verify(
        "VC-022",
        event_only_resumes=int(verdict.allowed),
        unsupported_resumes=0,
        mandatory_human_waits=int(verdict.requires_human),
    )


def test_pending_review_resume_needs_valid_goal_clearance_evidence_and_budget():
    project = _new_project("pendingresume")
    load = _load(project, _policy_doc())
    source = _full_grants(project)
    base = {
        "pending_review": True,
        "goal_effective": True,
        "blocker_cleared": True,
        "evidence": ["fresh integration run"],
        "choice": "approve",
        "required_scope": ["key:dpc-t07"],
        "budget_unit": "round",
        "budget_amount": 1,
        "usage": {"round": 0},
    }

    negatives = {
        "goal-not-effective": dict(base, goal_effective=False),
        "blocker-not-cleared": dict(base, blocker_cleared=False),
        "review-evidence-missing": dict(base, evidence=[]),
        "budget-not-sufficient": dict(base, budget_amount=9),
    }
    outcomes = []
    for expected, state in negatives.items():
        verdict = policy_mod.evaluate_pending_review(
            load,
            trigger={"kind": "dependency-delivery"},
            state=state,
            usage=state["usage"],
            authority_source=source,
            trusted_writers=TRUSTED_WRITERS,
        )
        assert not verdict.allowed, expected
        assert expected in _codes(verdict.reasons), (expected, _codes(verdict.reasons))
        outcomes.append(verdict)

    positive = policy_mod.evaluate_pending_review(
        load,
        trigger={"kind": "new-evidence"},
        state=base,
        usage=base["usage"],
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert positive.allowed is True
    assert positive.resume_scope == ("key:dpc-t07",)
    assert positive.requires_human is False
    _verify(
        "VC-022",
        event_only_resumes=0,
        unsupported_resumes=sum(int(v.allowed) for v in outcomes),
        mandatory_human_waits=0,
    )


def test_pending_review_requires_policy_and_request_scope():
    project = _new_project("pendingscope")
    # the policy grants only key:dpc-t07 while its authority covers both keys, so
    # only the policy's own scope can keep the outside request closed
    load = _load(
        project, _policy_doc(scope=["key:dpc-t07"], authority_ref="grant-wide")
    )
    wide, wide_issues = FixtureAuthorityWriter(project).grant(
        "grant-wide", ["key:dpc-t07", "key:outside"]
    )
    assert wide_issues == ()
    source = _full_grants(project)
    source.update(_source([wide]))
    base = {
        "pending_review": True,
        "goal_effective": True,
        "blocker_cleared": True,
        "evidence": ["fresh integration run"],
        "choice": "approve",
        "budget_unit": "round",
        "budget_amount": 1,
    }

    outside = policy_mod.evaluate_pending_review(
        load,
        trigger={"kind": "new-evidence"},
        state=dict(base, required_scope=["key:outside"]),
        usage={"round": 0},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert outside.allowed is False
    assert "review-scope-uncovered" in _codes(outside.reasons)
    assert outside.resume_scope == ()  # an uncovered request never resumes

    missing = policy_mod.evaluate_pending_review(
        load,
        trigger={"kind": "dependency-delivery"},
        state=dict(base),
        usage={"round": 0},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert missing.allowed is False
    assert "required-scope-missing" in _codes(missing.reasons)
    assert missing.resume_scope == ()  # a missing requirement is not a free pass

    positive = policy_mod.evaluate_pending_review(
        load,
        trigger={"kind": "new-evidence"},
        state=dict(base, required_scope=["key:dpc-t07"]),
        usage={"round": 0},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert positive.allowed is True
    assert positive.resume_scope == ("key:dpc-t07",)
    assert positive.requires_human is False
    _verify(
        "VC-022",
        event_only_resumes=0,
        unsupported_resumes=sum(int(v.allowed) for v in (outside, missing)),
        mandatory_human_waits=int(any(v.requires_human for v in (outside, missing))),
    )


# ── AC-034 / AC-035: halted stage recovery ─────────────────────────────────


def test_halted_recovery_requires_a_complete_note():
    project = _new_project("haltnote")
    load = _load(project, _policy_doc())
    source = _full_grants(project)

    cases = {
        "recovery-note-stop-reason-missing": "stop_reason",
        "recovery-note-elimination-missing": "elimination_evidence",
        "recovery-note-stage-version-missing": "stage_version",
        "recovery-note-keys-missing": "affected_keys",
        "recovery-note-plan-missing": "target_plan",
        "recovery-note-authority-missing": "authority_ref",
        "recovery-note-budget-missing": "residual_budget",
        "recovery-note-stop-criterion-missing": "stop_criterion",
    }
    outcomes = []
    for expected, key in cases.items():
        request = json.loads(json.dumps(HALTED_OK))
        request["note"].pop(key)
        verdict = policy_mod.evaluate_halted_recovery(
            load,
            request=request,
            usage={"round": 1},
            authority_source=source,
            trusted_writers=TRUSTED_WRITERS,
        )
        assert not verdict.allowed, expected
        assert expected in _codes(verdict.reasons), (expected, _codes(verdict.reasons))
        outcomes.append(verdict)

    _verify(
        "VC-034",
        erased_stop_facts=0,
        reset_usage=0,
        unsupported_resumes=sum(int(v.allowed) for v in outcomes),
    )

    not_halted = policy_mod.evaluate_halted_recovery(
        load,
        request=dict(HALTED_OK, stage_halted=False),
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not not_halted.allowed
    assert "not-halted" in _codes(not_halted.reasons)


def test_halted_recovery_requires_approve_and_valid_authority():
    project = _new_project("haltapprove")
    load = _load(project, _policy_doc())
    source = _full_grants(project)

    steer = policy_mod.evaluate_halted_recovery(
        load,
        request=dict(HALTED_OK, choice="steer"),
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not steer.allowed
    assert "recovery-choice-not-approve" in _codes(steer.reasons)

    no_authority = policy_mod.evaluate_halted_recovery(
        load,
        request=HALTED_OK,
        usage={"round": 1},
        authority_source={},
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not no_authority.allowed
    assert "authority-unresolved" in _codes(no_authority.reasons)

    inconsistent = json.loads(json.dumps(HALTED_OK))
    inconsistent["note"]["residual_budget"] = {"round": 5}
    residual = policy_mod.evaluate_halted_recovery(
        load,
        request=inconsistent,
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not residual.allowed
    assert "recovery-residual-exceeds" in _codes(residual.reasons)

    unknown_unit = json.loads(json.dumps(HALTED_OK))
    unknown_unit["note"]["residual_budget"] = {"token": 5}
    residual = policy_mod.evaluate_halted_recovery(
        load,
        request=unknown_unit,
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert "recovery-residual-unknown" in _codes(residual.reasons)

    _verify(
        "VC-034",
        erased_stop_facts=0,
        reset_usage=0,
        unsupported_resumes=sum(int(v.allowed) for v in (steer, no_authority, residual)),
    )


def test_halted_recovery_preserves_stop_facts_and_usage():
    project = _new_project("haltpositive")
    load = _load(project, _policy_doc())
    source = _full_grants(project)
    usage = {"round": 1}
    verdict = policy_mod.evaluate_halted_recovery(
        load,
        request=HALTED_OK,
        usage=usage,
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert verdict.allowed is True
    assert verdict.scope == ("recovery:halted",)
    assert verdict.observation_conditions == ("same-failure-reappears",)
    assert verdict.stop_conditions == ("recovery-reason-reappears",)
    facts = " | ".join(verdict.preserved_facts)
    assert HALTED_OK["note"]["stop_reason"] in facts
    assert HALTED_OK["note"]["elimination_evidence"][0] in facts
    assert "stage-2:v7" in facts
    assert dict(verdict.usage_after) == usage  # consumed budget is carried, never reset
    assert verdict.project_closed is False
    _verify(
        "VC-034",
        erased_stop_facts=int(not verdict.preserved_facts),
        reset_usage=int(dict(verdict.usage_after) != usage),
        unsupported_resumes=0,
    )


def test_user_stop_and_hard_guard_cannot_be_lifted_by_a_technical_fix():
    project = _new_project("userstop")
    load = _load(project, _policy_doc())
    source = _full_grants(project)

    user_stop = policy_mod.evaluate_halted_recovery(
        load,
        request=dict(HALTED_OK, halt_origin="user-stop"),
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not user_stop.allowed
    assert "user-stop-requires-explicit-authorization" in _codes(user_stop.reasons)
    assert user_stop.questions  # a concrete authorization question stays visible

    guard = policy_mod.evaluate_halted_recovery(
        load,
        request=dict(HALTED_OK, hard_guard_active=True),
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not guard.allowed
    assert "hard-guard-bypass" in _codes(guard.reasons)

    unverified = policy_mod.evaluate_halted_recovery(
        load,
        request=dict(HALTED_OK, hard_guard_active=True, hard_guard_cleared=[""]),
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not unverified.allowed
    assert "guard-clearance-unverified" in _codes(unverified.reasons)

    # A genuine user grant still cannot replace a *hard* guard check.
    guard_with_grant = policy_mod.evaluate_halted_recovery(
        load,
        request=dict(HALTED_OK, halt_origin="user-stop", hard_guard_active=True),
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert not guard_with_grant.allowed
    assert "hard-guard-bypass" in _codes(guard_with_grant.reasons)
    _verify(
        "VC-035",
        unauthorized_user_stop_unlocks=sum(
            int(v.allowed) for v in (user_stop, guard, unverified, guard_with_grant)
        ),
        hard_guard_bypasses=sum(int(v.allowed) for v in (guard, guard_with_grant)),
        false_resumes=sum(int(bool(v.scope)) for v in (user_stop, guard, unverified)),
    )


def test_halted_recovery_verifies_the_policy_rule_authority_and_supersession():
    project = _new_project("haltrule")
    load = _load(project, _policy_doc())
    writer = FixtureAuthorityWriter(project)
    unrelated, unrelated_issues = writer.grant("grant-unrelated", ["recovery:halted"])
    revoked_rule, revoked_issues = writer.grant(
        "grant-recovery", ["recovery:halted", "recovery:breaker"], revoked=True
    )
    assert unrelated_issues == () and revoked_issues == ()

    def request_with(ref: str) -> dict:
        request = json.loads(json.dumps(HALTED_OK))
        request["note"]["authority_ref"] = ref
        return request

    # a revoked policy recovery reference is not bypassed by pointing the note
    # at another (even scope-identical) record
    bypass = policy_mod.evaluate_halted_recovery(
        load,
        request=request_with("grant-unrelated"),
        usage={"round": 1},
        authority_source=_source([unrelated, revoked_rule]),
        trusted_writers=TRUSTED_WRITERS,
    )
    assert bypass.allowed is False
    assert "recovery-authority-unrelated" in _codes(bypass.reasons)
    assert "authority-revoked" in _codes(bypass.reasons)
    assert bypass.scope == ()

    # valid rule reference + an unrelated valid grant is still not a resume
    source = _full_grants(project)
    other, other_issues = writer.grant("grant-other-recovery", ["recovery:halted"])
    assert other_issues == ()
    source.update(_source([other]))
    unrelated_ok = policy_mod.evaluate_halted_recovery(
        load,
        request=request_with("grant-other-recovery"),
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert unrelated_ok.allowed is False
    assert "recovery-authority-unrelated" in _codes(unrelated_ok.reasons)
    assert unrelated_ok.scope == ()

    # an explicit, writer-recorded replacement is a legal new authorization
    replacement, replacement_issues = writer.grant(
        "grant-recovery-r2", ["recovery:halted"], supersedes=["grant-recovery"]
    )
    assert replacement_issues == ()
    source.update(_source([replacement]))
    resumed = policy_mod.evaluate_halted_recovery(
        load,
        request=request_with("grant-recovery-r2"),
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    assert resumed.allowed is True
    assert resumed.scope == ("recovery:halted",)
    assert "superseded-authority:grant-recovery" in resumed.preserved_facts
    _verify(
        "VC-034",
        erased_stop_facts=int(not resumed.preserved_facts),
        reset_usage=int(dict(resumed.usage_after) != {"round": 1}),
        unsupported_resumes=sum(int(v.allowed) for v in (bypass, unrelated_ok)),
    )


def test_halted_recovery_unknown_guard_and_halt_origin_stay_blocked():
    project = _new_project("haltguard")
    load = _load(project, _policy_doc())
    source = _full_grants(project)
    writer = FixtureAuthorityWriter(project)

    def verdict(request: dict, authority=None):
        return policy_mod.evaluate_halted_recovery(
            load,
            request=request,
            usage={"round": 1},
            authority_source=source if authority is None else authority,
            trusted_writers=TRUSTED_WRITERS,
        )

    # an active guard cleared only by a self-reported string is still active
    self_reported = verdict(
        dict(HALTED_OK, hard_guard_active=True, hard_guard_cleared=["self-reported-clear"])
    )
    assert self_reported.allowed is False
    assert "guard-clearance-unverified" in _codes(self_reported.reasons)
    assert self_reported.scope == ()

    non_bool_verdict = verdict(
        dict(
            HALTED_OK,
            hard_guard_active=True,
            hard_guard_cleared=["cargo check passed"],
            hard_guard_cleared_verified="yes",
        )
    )
    assert non_bool_verdict.allowed is False
    assert "guard-clearance-unverified" in _codes(non_bool_verdict.reasons)

    # a machine-verified clearance still resumes (the guard is not blindly fatal)
    verified = verdict(
        dict(
            HALTED_OK,
            hard_guard_active=True,
            hard_guard_cleared=["cargo check exit 0"],
            hard_guard_cleared_verified=True,
        )
    )
    assert verified.allowed is True
    assert verified.scope == ("recovery:halted",)

    missing_guard = json.loads(json.dumps(HALTED_OK))
    del missing_guard["hard_guard_active"]
    unknown_guard = verdict(missing_guard)
    assert unknown_guard.allowed is False
    assert "hard-guard-unknown" in _codes(unknown_guard.reasons)
    assert unknown_guard.scope == ()
    assert "hard-guard-unknown" in _codes(
        verdict(dict(HALTED_OK, hard_guard_active="unknown")).reasons
    )

    # an unknown stop origin is never assumed to be a plain technical stop
    missing_origin = json.loads(json.dumps(HALTED_OK))
    del missing_origin["halt_origin"]
    unknown_origin = verdict(missing_origin)
    assert unknown_origin.allowed is False
    assert "halt-origin-unknown" in _codes(unknown_origin.reasons)
    assert unknown_origin.scope == ()

    # a revocation needs an explicit *human* lift, not a controlled-config record
    config_lift, config_issues = writer.grant(
        "grant-config-lift",
        ["recovery:user-stop", "recovery:halted"],
        kind="controlled-config",
    )
    assert config_issues == ()
    config_source = dict(source)
    config_source.update(_source([config_lift]))
    revoked_origin = verdict(
        dict(HALTED_OK, halt_origin="revoked"), authority=config_source
    )
    assert revoked_origin.allowed is False
    assert "user-stop-requires-explicit-authorization" in _codes(revoked_origin.reasons)
    assert revoked_origin.scope == ()

    # a real new human authorization restores the stop and keeps the stop facts
    human_lift, human_issues = writer.grant(
        "grant-human-lift", ["recovery:user-stop", "recovery:halted"]
    )
    assert human_issues == ()
    human_source = dict(source)
    human_source.update(_source([human_lift]))
    lifted_request = json.loads(json.dumps(HALTED_OK))
    lifted_request["halt_origin"] = "user-stop"
    lifted_request["note"]["authority_ref"] = "grant-human-lift"
    lifted = verdict(lifted_request, authority=human_source)
    assert lifted.allowed is True
    assert lifted.scope == ("recovery:halted",)
    assert HALTED_OK["note"]["stop_reason"] in " | ".join(lifted.preserved_facts)

    # the policy rule reference itself stays verified: a revoked rule cannot be
    # restored by a human lift that does not say what it replaces
    revoked_rule, revoked_rule_issues = writer.grant(
        "grant-recovery", ["recovery:halted", "recovery:breaker"], revoked=True
    )
    assert revoked_rule_issues == ()
    revoked_source = dict(human_source)
    revoked_source.update(_source([revoked_rule]))
    silent_lift = verdict(lifted_request, authority=revoked_source)
    assert silent_lift.allowed is False
    assert "authority-revoked" in _codes(silent_lift.reasons)
    assert silent_lift.scope == ()

    restoring, restoring_issues = writer.grant(
        "grant-human-restore",
        ["recovery:user-stop", "recovery:halted"],
        supersedes=["grant-recovery"],
    )
    assert restoring_issues == ()
    restoring_source = dict(revoked_source)
    restoring_source.update(_source([restoring]))
    restored_request = json.loads(json.dumps(lifted_request))
    restored_request["note"]["authority_ref"] = "grant-human-restore"
    restored = verdict(restored_request, authority=restoring_source)
    assert restored.allowed is True
    assert restored.scope == ("recovery:halted",)
    assert "superseded-authority:grant-recovery" in restored.preserved_facts
    _verify(
        "VC-035",
        unauthorized_user_stop_unlocks=sum(
            int(v.allowed)
            for v in (
                self_reported,
                non_bool_verdict,
                unknown_guard,
                unknown_origin,
                revoked_origin,
                silent_lift,
            )
        ),
        hard_guard_bypasses=int(self_reported.allowed or non_bool_verdict.allowed),
        false_resumes=sum(
            int(bool(v.scope))
            for v in (
                self_reported,
                unknown_guard,
                unknown_origin,
                revoked_origin,
                silent_lift,
            )
        ),
    )


# ── AC-036 / AC-037: H12 breaker recovery ──────────────────────────────────


def test_breaker_recovery_rejects_the_tripped_chain_and_bypass_channels():
    project = _new_project("breakerneg")
    load = _load(project, _policy_doc())
    source = _full_grants(project)

    self_approval = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, channel="auto-pass", origin="auto-pass"),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not self_approval.allowed
    assert "breaker-self-approval" in _codes(self_approval.reasons)

    bypass = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, channel="conductor-tick"),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not bypass.allowed
    assert "transport-not-controlled" in _codes(bypass.reasons)

    pseudo_origin = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, origin="page-token"),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not pseudo_origin.allowed
    assert "breaker-origin-not-authoritative" in _codes(pseudo_origin.reasons)

    not_allowed_origin = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, origin="worker-self-report"),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not not_allowed_origin.allowed
    assert (
        "breaker-origin-not-authoritative" in _codes(not_allowed_origin.reasons)
        or "breaker-origin-not-allowed" in _codes(not_allowed_origin.reasons)
    )

    outcomes = [self_approval, bypass, pseudo_origin, not_allowed_origin]
    _verify(
        "VC-036",
        breaker_self_approvals=int(self_approval.allowed),
        unauthorized_recoveries=sum(int(v.allowed) for v in outcomes),
        transport_bypasses=int(bool(bypass.scope)),
    )


def test_breaker_recovery_requires_evidence_and_machine_checks():
    project = _new_project("breakerevidence")
    load = _load(project, _policy_doc())
    source = _full_grants(project)

    no_preauth = dict(BREAKER_OK)
    no_preauth.pop("preauthorization_ref")
    missing_preauth = policy_mod.evaluate_breaker_recovery(
        load,
        request=no_preauth,
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not missing_preauth.allowed
    assert "breaker-preauth-missing" in _codes(missing_preauth.reasons)
    assert missing_preauth.questions

    missing_evidence = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, reason_elimination_evidence=[]),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not missing_evidence.allowed
    assert "breaker-elimination-missing" in _codes(missing_evidence.reasons)
    assert missing_evidence.questions

    no_checks = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, machine_checks={}),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not no_checks.allowed
    assert "machine-checks-missing" in _codes(no_checks.reasons)

    failed_check = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, machine_checks={"brake-isolated": False}),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not failed_check.allowed
    assert "machine-check-failed" in _codes(failed_check.reasons)
    assert {i.field for i in failed_check.reasons if i.code == "machine-check-failed"} == {
        "brake-isolated"
    }

    unresolved = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, preauthorization_ref="grant-missing"),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not unresolved.allowed
    assert "authority-unresolved" in _codes(unresolved.reasons)

    outcomes = [missing_preauth, missing_evidence, no_checks, failed_check, unresolved]
    _verify(
        "VC-036",
        breaker_self_approvals=0,
        unauthorized_recoveries=sum(int(v.allowed) for v in outcomes),
        transport_bypasses=sum(int(bool(v.scope)) for v in outcomes),
    )


def test_breaker_recovery_transport_unavailable_keeps_brake():
    project = _new_project("breakertransport")
    load = _load(project, _policy_doc())
    source = _full_grants(project)
    verdict = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, transport_available=False),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not verdict.allowed
    assert "transport-unavailable" in _codes(verdict.reasons)
    assert verdict.scope == ()  # no alternate channel is opened
    assert verdict.questions
    assert verdict.project_closed is False
    _verify(
        "VC-036",
        breaker_self_approvals=0,
        unauthorized_recoveries=int(verdict.allowed),
        transport_bypasses=int(bool(verdict.scope)),
    )


def test_breaker_recovery_positive_is_limited_and_keeps_history():
    project = _new_project("breakerpositive")
    load = _load(project, _policy_doc())
    source = _full_grants(project)
    verdict = policy_mod.evaluate_breaker_recovery(
        load,
        request=BREAKER_OK,
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert verdict.allowed is True
    assert verdict.scope == ("recovery:breaker",)
    assert verdict.observation_conditions == ("same-failure-reappears",)
    assert verdict.stop_conditions == ("recovery-reason-reappears",)
    assert verdict.questions == ()
    assert verdict.project_closed is False
    assert verdict.preserved_facts
    assert "auto-pass" in " | ".join(verdict.preserved_facts)

    # a wider recovery scope than the rule grants is refused
    wider = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, required_scope=["recovery:breaker", "recovery:project-close"]),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not wider.allowed
    assert "recovery-scope-uncovered" in _codes(wider.reasons)
    _verify(
        "VC-036",
        breaker_self_approvals=0,
        unauthorized_recoveries=int(wider.allowed),
        transport_bypasses=0,
    )


def test_user_disabled_keeps_brake_with_a_concrete_question_and_no_closure():
    project = _new_project("userdisabled")
    load = _load(project, _policy_doc())
    source = _full_grants(project)

    disabled = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, user_disabled=True),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not disabled.allowed
    assert "user-disabled" in _codes(disabled.reasons)
    assert disabled.questions
    assert any("authoriz" in q.lower() for q in disabled.questions)
    assert disabled.preserved_facts  # the original breaker record is not erased
    assert disabled.project_closed is False

    reject = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, choice="reject"),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert not reject.allowed
    assert "recovery-choice-not-approve" in _codes(reject.reasons)
    assert reject.project_closed is False
    _verify(
        "VC-037",
        unauthorized_unlocks=sum(int(v.allowed) for v in (disabled, reject)),
        erased_breaker_history=sum(int(not v.preserved_facts) for v in (disabled, reject)),
        reject_project_closures=int(reject.project_closed),
        observed_retrip=0,
    )


def test_breaker_recovery_verifies_the_policy_rule_authority_and_disable_state():
    project = _new_project("breakerrule")
    load = _load(project, _policy_doc())
    writer = FixtureAuthorityWriter(project)
    revoked_rule, revoked_issues = writer.grant(
        "grant-recovery", ["recovery:breaker"], revoked=True
    )
    other, other_issues = writer.grant("grant-other-preauth", ["recovery:breaker"])
    assert revoked_issues == () and other_issues == ()

    # revoked policy recovery reference + another preauthorization: still engaged
    bypass = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, preauthorization_ref="grant-other-preauth"),
        authority_source=_source([revoked_rule, other]),
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert bypass.allowed is False
    assert "recovery-authority-unrelated" in _codes(bypass.reasons)
    assert "authority-revoked" in _codes(bypass.reasons)
    assert bypass.scope == ()

    source = _full_grants(project)
    source.update(_source([other]))
    unrelated = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, preauthorization_ref="grant-other-preauth"),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert unrelated.allowed is False
    assert "recovery-authority-unrelated" in _codes(unrelated.reasons)
    assert unrelated.scope == ()

    # a missing or non-boolean user state is unknown, not "enabled"
    unknown_disable = json.loads(json.dumps(BREAKER_OK))
    del unknown_disable["user_disabled"]
    missing_disable = policy_mod.evaluate_breaker_recovery(
        load,
        request=unknown_disable,
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert missing_disable.allowed is False
    assert "breaker-disable-unknown" in _codes(missing_disable.reasons)
    assert missing_disable.scope == ()
    assert missing_disable.questions

    non_bool_disable = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, user_disabled="unknown"),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert non_bool_disable.allowed is False
    assert "breaker-disable-unknown" in _codes(non_bool_disable.reasons)

    # the legal disable stays a hard block, and the legal replacement resumes
    disabled = policy_mod.evaluate_breaker_recovery(
        load,
        request=dict(BREAKER_OK, user_disabled=True),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert disabled.allowed is False
    assert "user-disabled" in _codes(disabled.reasons)

    resumed = policy_mod.evaluate_breaker_recovery(
        load,
        request=BREAKER_OK,
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert resumed.allowed is True
    assert resumed.scope == ("recovery:breaker",)
    assert "superseded-authority:grant-recovery" in resumed.preserved_facts
    _verify(
        "VC-036",
        breaker_self_approvals=0,
        unauthorized_recoveries=sum(
            int(v.allowed) for v in (bypass, unrelated, missing_disable, non_bool_disable, disabled)
        ),
        transport_bypasses=sum(
            int(bool(v.scope)) for v in (bypass, unrelated, missing_disable, non_bool_disable)
        ),
    )


def test_observed_retrip_engages_the_brake_again():
    project = _new_project("retrip")
    load = _load(project, _policy_doc())
    source = _full_grants(project)
    recovery = policy_mod.evaluate_breaker_recovery(
        load,
        request=BREAKER_OK,
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )
    assert recovery.allowed is True

    quiet = policy_mod.observe_recovery(recovery, observed_conditions=("nothing-new",))
    assert quiet.retrip is False
    assert quiet.brake == "released"
    assert quiet.preserved_history is True

    retrip = policy_mod.observe_recovery(
        recovery,
        observed_conditions=("recovery-reason-reappears",),
    )
    assert retrip.retrip is True
    assert retrip.brake == "engaged"
    assert retrip.preserved_history is True
    assert "stop-condition-observed" in _codes(retrip.reasons)

    check_fail = policy_mod.observe_recovery(
        recovery,
        failed_checks=("brake-isolated",),
    )
    assert check_fail.retrip is True
    assert check_fail.brake == "engaged"
    _verify(
        "VC-037",
        unauthorized_unlocks=0,
        erased_breaker_history=int(not retrip.preserved_history),
        reject_project_closures=0,
        observed_retrip=int(retrip.retrip),
    )


# ── structural / isolation guarantees ──────────────────────────────────────


def test_module_is_pure_and_imports_no_cli_conductor_or_config():
    source = (PACKAGE_ROOT / "decision_policy.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "json", "pathlib", "dataclasses", "collections", "typing"}, imported
    forbidden = {
        "argparse",
        "subprocess",
        "socket",
        "urllib",
        "requests",
        "autopilot",
        "mw",
        "mw_common",
        "decision",
        "decision_points",
        "decision_wire",
        "conductor",
    }
    assert not (imported & forbidden)


def test_frozen_config_keys_are_not_an_authority_source():
    from autopilot import config as autopilot_config

    assert len(autopilot_config.DEFAULT_CONFIG) == 21
    assert policy_mod.FROZEN_CONFIG_UNITS == {"round_budget", "worker_timeout_min"}
    assert policy_mod.FROZEN_CONFIG_UNITS <= set(autopilot_config.DEFAULT_CONFIG)


def test_policy_reads_are_read_only_and_side_effect_free():
    project = _new_project("readonly")
    load = _load(project, _policy_doc())
    source = _full_grants(project)
    path = policy_mod.policy_path(project)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    before_files = sorted(
        str(p.relative_to(project)).replace("\\", "/")
        for p in project.rglob("*")
        if p.is_file()
    )

    policy_mod.evaluate_gate(
        load,
        choice="approve",
        hard_checks={"claim": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07",),
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    policy_mod.check_spend(load, unit="round", amount=1, usage={"round": 1})
    policy_mod.evaluate_soft_extension(
        load,
        note=dict(NOTE_OK),
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    policy_mod.evaluate_halted_recovery(
        load,
        request=HALTED_OK,
        usage={"round": 1},
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
    )
    policy_mod.evaluate_breaker_recovery(
        load,
        request=BREAKER_OK,
        authority_source=source,
        trusted_writers=TRUSTED_WRITERS,
        controlled_channels=CONTROLLED_CHANNELS,
    )

    after = hashlib.sha256(path.read_bytes()).hexdigest()
    after_files = sorted(
        str(p.relative_to(project)).replace("\\", "/")
        for p in project.rglob("*")
        if p.is_file()
    )
    assert before == after
    assert before_files == after_files
