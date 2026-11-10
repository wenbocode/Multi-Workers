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

Isolation: by default every fixture project, authority record and process
HOME/TEMP lives under pytest's per-run ``tmp_path``; an explicit
``DPC_T07_FIXTURE_ROOT`` remains supported. The authority records are written
by a real, byte-level fixture writer (tmp + ``os.replace``) and then parsed
back through the production
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
_EXPLICIT_FIXTURE_ROOT = os.environ.get("DPC_T07_FIXTURE_ROOT")
FIXTURE_ROOT = pathlib.Path(_EXPLICIT_FIXTURE_ROOT) if _EXPLICIT_FIXTURE_ROOT else pathlib.Path()

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
def _isolated_process_env(monkeypatch, tmp_path):
    global FIXTURE_ROOT
    FIXTURE_ROOT = (
        pathlib.Path(_EXPLICIT_FIXTURE_ROOT)
        if _EXPLICIT_FIXTURE_ROOT
        else tmp_path / "dpc-t07-policy" / "fixture"
    )
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


def test_authority_source_key_must_match_record_identity():
    project = _new_project("authority-id")
    load = _load(project, _policy_doc())
    record, issues = FixtureAuthorityWriter(project).grant(
        "grant-other", ["key:dpc-t07"]
    )
    assert issues == () and record is not None
    verdict = policy_mod.evaluate_gate(
        load,
        choice="approve",
        hard_checks={"claim": True},
        automation_enabled=True,
        required_scope=("key:dpc-t07",),
        authority_source={"grant-dpc-t07": record},
        trusted_writers=TRUSTED_WRITERS,
    )
    assert verdict.allowed is False
    assert verdict.release_scope == ()
    assert "authority-ref-mismatch" in _codes(verdict.reasons)


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


def test_gate_requires_an_explicit_nonempty_action_scope():
    project = _new_project("gate-scope")
    load = _load(project, _policy_doc())
    source = _full_grants(project)
    outcomes = [
        policy_mod.evaluate_gate(
            load,
            choice="approve",
            hard_checks={"claim": True},
            automation_enabled=True,
            required_scope=scope,
            authority_source=source,
            trusted_writers=TRUSTED_WRITERS,
        )
        for scope in ((), ("",))
    ]
    assert all(verdict.allowed is False for verdict in outcomes)
    assert all(verdict.release_scope == () for verdict in outcomes)
    assert all(
        "required-scope-missing" in _codes(verdict.reasons)
        for verdict in outcomes
    )


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


def test_ordinary_shell_cannot_enter_the_operator_recovery_callback(tmp_path):
    from autopilot import decision_recovery

    work = tmp_path / "ordinary"
    work.mkdir()
    raw = b'{"purpose":"h12","channel":"pm-controlled","authorized":true}'
    for result in (decision_recovery.prepare_operator_recovery(work, raw, {}),
                   decision_recovery.apply_operator_recovery(work, raw, {}, {"choice": "approve"})):
        assert result == {"ok": False, "reason": "operator-host-required"}
    assert not list(work.iterdir())


def test_missing_legacy_and_damaged_managed_brakes_do_not_allow_recovery(tmp_path):
    from autopilot import conductor, decision_recovery

    path = conductor.auto_brake_path(tmp_path)
    assert decision_recovery.managed_brake_state(tmp_path)["active"]
    path.parent.mkdir(parents=True)
    for value in ("reason: burst-60s\ntriggered_at: 2026-11-08T10:00:00Z\n",
                  'mw-breaker-event: {"state":"observing"}\n'):
        path.write_text(value, encoding="utf-8")
        assert decision_recovery.managed_brake_state(tmp_path)["state"] == "unknown"
        assert path.read_text(encoding="utf-8") == value


# ── T21 recovery handler: isolated operator-service fixtures ────────────────


def _recovery_note():
    return {
        "subject": "limit the H12 brake to one observing step",
        "planned_action": "observe-brake",
        "basis": {
            "goal": "resume only the authorized observation window",
            "evidence": "auto-decisions.jsonl shows no live breaker signal",
            "budget": "one round remains inside the hard limit",
            "authority": "grant-recovery recorded by the controlled writer",
        },
    }


def _recovery_preparation(prepared_at, choice="approve"):
    return {
        "prepared_at": prepared_at,
        "basis_catalog": [
            {
                "id": "b-approve",
                "text": "the original signal is gone and the policy still allows one observing step",
                "material_refs": ["condition_evidence"],
                "applies_to": [choice],
            }
        ],
    }


class _FakePreparedClient:
    def __init__(self, *, business=1, choice="approve"):
        self.calls = []
        self.business = business
        self.choice = choice

    def request_prepared(self, dp, material, preparation, *, actor_role=None, logical_id=None,
                         replay_check=None):
        self.calls.append({"dp": dp, "material": material, "preparation": preparation,
                           "actor_role": actor_role, "logical_id": logical_id})
        if self.business == 1:
            return {
                "dp": dp, "available": True, "replayed": False,
                "choice": self.choice, "basis_id": "b-approve",
                "basis_text": preparation["basis_catalog"][0]["text"],
                "basis_source": "pm-prepared", "prepared_at": preparation["prepared_at"],
                "reason": None, "attempts": 1, "transport_attempts": 1,
                "business_decisions": 1,
            }
        return {
            "dp": dp, "available": True, "replayed": False, "choice": None,
            "basis_id": None, "basis_text": None, "basis_source": None,
            "prepared_at": preparation["prepared_at"], "reason": "entry-unavailable",
            "attempts": 1, "transport_attempts": 1, "business_decisions": 0,
        }


def _recovery_fixture(tmp_path, monkeypatch, *, client=None, choice="approve",
                      real_client=None, with_ledger_sha256=True, hard_limit=2,
                      real_authorization=False):
    import os
    import socket

    from autopilot import decision_recovery, gates
    import decision
    import decision_lifecycle as lifecycle
    import decision_wire as wire

    root = tmp_path / "recovery-project"
    (root / ".agenticdoc" / "_autopilot" / "gates").mkdir(parents=True)
    key = "dpc-t21"
    claim = f"{socket.gethostname()}:{os.getpid()}"
    (root / ".agenticdoc" / "_index.parallel").write_text(
        "| Key | Status | Phase | Claim | Deps | Desc | Updated |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| {key} | active | 4 | {claim} | | T21 fixture | 2026-11-08T10:00:00Z |\n",
        encoding="utf-8",
    )
    doc = _policy_doc(scope=[
        "key:dpc-t21", "action:gate-approve", "recovery:breaker", "action:observe-brake",
    ], hard_limits=[{"unit": "round", "limit": hard_limit,
                     "usage_source": "task-card-rounds"}])
    _load(root, doc)
    (root / ".agenticdoc" / "_autopilot" / "config.json").write_text(
        json.dumps({"enabled": True, "paused": False, "auto_gate_mode": "live"}),
        encoding="utf-8",
    )
    writer = FixtureAuthorityWriter(root)
    scopes = ["key:dpc-t21", "action:gate-approve", "recovery:breaker", "action:observe-brake"]
    for ref in ("grant-dpc-t07", "grant-recovery"):
        record, issues = writer.grant(ref, scopes)
        assert issues == ()
    authority = {
        ref: json.loads((root / "authority" / f"{ref}.json").read_text(encoding="utf-8"))
        for ref in ("grant-dpc-t07", "grant-recovery")
    }
    note = _recovery_note()
    reason = "burst-60s"
    brake = root / ".agenticdoc" / "_autopilot" / "auto-brake.md"
    brake.write_text(
        "---\nreason: burst-60s\ndetail: fixture trip\ntriggered_at: 2026-11-08T09:00:00Z\n"
        "action: escalate-to-human\n---\n",
        encoding="utf-8",
    )
    trip = decision_recovery._legacy_trip(brake.read_bytes())["trip_id"]
    ledger = root / ".agenticdoc" / "_autopilot" / "auto-decisions.jsonl"
    ledger.write_text(json.dumps({
        "seq": 1, "phase": "decide", "mode": "live", "executed": False,
        "decision": "escalate", "reason_code": "breaker-tripped",
        "refusal_code": reason, "trip_id": trip,
        "decided_at": "2026-11-08T09:00:00+00:00",
    }) + "\n", encoding="utf-8")
    grant_ref = "a" * 32
    operation_id = "b" * 32
    matter = decision_recovery.recovery_matter(key, trip, reason, note, grant_ref)
    gate_path = gates.create(
        root / ".agenticdoc" / "_autopilot" / "gates", "stalled",
        "Recover one observing step after the H12 trip?",
        stage=1, key=key, pm_note=json.dumps(note, sort_keys=True),
        matter_ref=matter.matter_key, substantive_version=matter.substantive_version,
    )
    grant = {
        "project_id": wire.project_id_for(root), "key": key, "trip_id": trip,
        "grant_ref": grant_ref, "operation_id": operation_id, "claim": claim,
        "revoked": False, "recorded_at": "2026-01-01T00:00:00+00:00",
        "expires_at": "2030-01-01T00:00:00+00:00",
        "policy_sha256": hashlib.sha256(policy_mod.policy_path(root).read_bytes()).hexdigest(),
        "ledger_sha256": hashlib.sha256(ledger.read_bytes()).hexdigest(),
        "authority_source": authority, "trusted_writers": [TRUSTED_WRITER],
        "usage_sources": {"task-card-rounds": {"kind": "auto-decisions", "unit": "round"}},
        "authority_ref": "grant-recovery",
        "scope": ["recovery:breaker", "observe-brake", "key:dpc-t21", "action:observe-brake"],
        "reason": reason, "unit": "round", "amount": 1, "usage_source": "task-card-rounds",
        "observation_conditions": ["same-failure-reappears"],
        "stop_conditions": ["recovery-reason-reappears"],
    }
    preparation = _recovery_preparation("2026-11-08T10:05:00+00:00", choice)
    request = {
        "schema": 1, "purpose": "h12", "project_id": grant["project_id"],
        "key": key, "trip_id": trip, "grant_ref": grant_ref,
        "gate_id": gate_path.stem, "pm_note": note,
        "preparation": preparation, "action": "observe-brake",
    }
    frozen = json.dumps(request, ensure_ascii=False, sort_keys=True).encode("utf-8")
    store = lifecycle.LifecycleStore.production(
        root, redact=wire.SubstringRedactor(secrets=()))
    fake = client or real_client or _FakePreparedClient(choice=choice)
    if not real_authorization:
        monkeypatch.setattr(decision_recovery, "_authorized", lambda *args: True)
    if real_client is not None:
        (root / ".mw").mkdir(parents=True, exist_ok=True)
        (root / ".mw" / "decide.json").write_text(
            json.dumps({"enabled": True, "transport": "timi-decisions",
                        "max_questions": 8, "max_retries": 0}),
            encoding="utf-8",
        )
        real = decision.DecisionClient
        monkeypatch.setattr(
            decision, "DecisionClient",
            lambda cfg, **kwargs: real(cfg, backend=real_client, **kwargs))
    else:
        monkeypatch.setattr(decision_recovery, "_client_store", lambda _root: (fake, store))
    if not with_ledger_sha256:
        grant.pop("ledger_sha256", None)
    return root, grant, frozen, fake, store, gate_path, brake, ledger, trip


def _lifecycle_rows(store, kind):
    import decision_lifecycle as lifecycle

    return [row for row in lifecycle.read_lifecycle(store).events
            if row.get("kind") == kind or row.get("lifecycle") == kind]


def test_recovery_rejects_an_authority_writer_that_is_not_grant_trusted(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    root, grant, frozen, fake, store, _gate, brake, _ledger, _trip = _recovery_fixture(
        tmp_path, monkeypatch)
    before = brake.read_bytes()
    grant["authority_source"]["grant-recovery"]["writer"] = "not-the-controlled-writer"
    result = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert result["ok"] is False
    assert result["reason"] in {"invalid-protected-authority", "recovery-evidence-unavailable"}
    assert fake.calls == []
    assert brake.read_bytes() == before
    assert _lifecycle_rows(store, "request") == []
    _verify("VC-036", breaker_self_approvals=0, unauthorized_recoveries=0,
            transport_bypasses=0)


def test_recovery_gate_axis_mismatch_is_refused_before_any_model_call(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    root, grant, frozen, fake, _store, gate_path, brake, _ledger, _trip = _recovery_fixture(
        tmp_path, monkeypatch)
    text = gate_path.read_text(encoding="utf-8")
    changed = text.replace(
        "matter_ref: ",
        "matter_ref: ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff # ",
        1,
    )
    gate_path.write_text(changed, encoding="utf-8")
    before = brake.read_bytes()
    result = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert result["ok"] is False
    assert result["reason"] == "prepared-gate-mismatch"
    assert fake.calls == []
    assert brake.read_bytes() == before


def test_recovery_prepare_uses_one_real_prepared_request_and_resumes_it(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    root, grant, frozen, fake, store, _gate, brake, _ledger, _trip = _recovery_fixture(
        tmp_path, monkeypatch)
    before = brake.read_bytes()
    first = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert first["ok"] is True and first["choice"] == "approve"
    assert first["resumed"] is False
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call["dp"] == "dp-gate-approve"
    assert call["actor_role"] == "pm"
    assert call["logical_id"] == grant["operation_id"]
    assert call["material"]["pm_note"] == _recovery_note()
    assert call["preparation"]["basis_catalog"][0]["id"] == "b-approve"
    assert brake.read_bytes() == before  # preparing never writes the brake
    request_rows = _lifecycle_rows(store, "request")
    assert len(request_rows) == 1
    assert request_rows[0]["business_decisions"] == 1
    second = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert second["ok"] is True and second["resumed"] is True
    assert second["choice"] == first["choice"] and second["decision_ref"] == first["decision_ref"]
    assert len(fake.calls) == 1
    assert len(_lifecycle_rows(store, "request")) == 1


def test_recovery_unknown_or_refused_request_is_not_retried(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    root, grant, frozen, fake, store, _gate, brake, _ledger, _trip = _recovery_fixture(
        tmp_path, monkeypatch, client=_FakePreparedClient(business=0))
    first = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert first["ok"] is False and first["reason"] == "no-valid-gate-decision"
    assert len(fake.calls) == 1
    assert len(_lifecycle_rows(store, "request")) == 1
    assert _lifecycle_rows(store, "request")[0]["business_decisions"] == 0
    before = brake.read_bytes()
    second = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert second["ok"] is False and second["reason"] == "previous-request-refused"
    assert len(fake.calls) == 1
    assert brake.read_bytes() == before


def test_recovery_apply_writes_the_original_brake_once_and_resumes_a_crash(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    root, grant, frozen, _fake, store, _gate, brake, _ledger, _trip = _recovery_fixture(
        tmp_path, monkeypatch)
    prepared = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert prepared["ok"] is True
    original = brake.read_bytes()
    applied = decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)
    assert applied["ok"] is True
    assert applied["state"] == "observing" and applied["brake_state"] == "observing"
    assert applied["effect"] == "applied"
    assert applied["decision_ref"] == prepared["decision_ref"]
    assert applied["receipt"] and len(applied["receipt"]) == 64
    after = brake.read_bytes()
    assert after.startswith(original)
    assert after.count(b"mw-breaker-event:") == 1
    events = decision_recovery._rows(after)
    assert events[-1]["state"] == "observing" and events[-1]["decision_ref"] == prepared["decision_ref"]
    assert len(_lifecycle_rows(store, "request")) == 1
    assert len(_lifecycle_rows(store, "executed")) == 1
    assert len(_lifecycle_rows(store, "settled")) == 1
    replay = decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)
    assert replay["ok"] is True and replay["state"] == "observing" and replay["resumed"] is True
    assert replay["effect"] == "applied"
    assert brake.read_bytes() == after
    assert len(_lifecycle_rows(store, "executed")) == 1
    _verify("VC-052", duplicate_effects=0, duplicate_approvals=0, concurrent_writers=0,
            lock_bypasses=0, stale_releases=0, irrelevant_reapprovals=0)


def test_recovery_apply_rechecks_revocation_and_the_recovery_basis(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    root, grant, frozen, _fake, _store, _gate, brake, _ledger, _trip = _recovery_fixture(
        tmp_path, monkeypatch)
    prepared = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert prepared["ok"] is True
    before = brake.read_bytes()
    grant["revoked"] = True
    refused = decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)
    assert refused["ok"] is False
    assert refused["reason"] == "preauthorization-expired-or-revoked"
    assert brake.read_bytes() == before
    grant["revoked"] = False
    brake.write_bytes(before + b"\n")
    changed = decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)
    assert changed["ok"] is False
    assert changed["reason"] == "recovery-basis-changed"
    assert b"mw-breaker-event:" not in brake.read_bytes()


def test_recovery_observation_retrips_and_preserves_the_first_recovery(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    root, grant, frozen, _fake, _store, _gate, brake, _ledger, trip = _recovery_fixture(
        tmp_path, monkeypatch)
    prepared = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    applied = decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)
    assert applied["ok"] is True
    observed = decision_recovery.observe_operator_recovery(
        root, frozen, grant, observed_conditions=["recovery-reason-reappears"])
    assert observed["ok"] is True and observed["state"] == "retripped"
    assert observed["retripped"] is True and observed["trip_id"] != trip
    rows = decision_recovery._rows(brake.read_bytes())
    assert [row["state"] for row in rows] == ["tripped", "observing", "tripped"]
    assert rows[1]["trip_id"] == trip
    assert rows[-1]["trip_id"] == observed["trip_id"]
    state = decision_recovery.managed_brake_state(root)
    assert state["active"] is True and state["state"] == "tripped"
    _verify("VC-037", unauthorized_unlocks=0, erased_breaker_history=0,
            reject_project_closures=0, observed_retrip=1)


def test_recovery_observation_without_a_stop_condition_keeps_the_limit(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    root, grant, frozen, _fake, _store, _gate, brake, _ledger, trip = _recovery_fixture(
        tmp_path, monkeypatch)
    prepared = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)["ok"]
    before = brake.read_bytes()
    observed = decision_recovery.observe_operator_recovery(root, frozen, grant, observed_conditions=[])
    assert observed["ok"] is True and observed["retripped"] is False
    assert brake.read_bytes() == before
    assert decision_recovery.managed_brake_state(root)["trip"] == trip

# ── T21 actual-gate: real client + the one formal answer writer ─────────────


def _brake_host(project, tmp_path, monkeypatch):
    import decision_wire as wire
    import operator_authority as oa
    import operator_host as host_module
    from autopilot import conductor, decision_recovery

    if host_module.Fido2Server is None:
        monkeypatch.setattr(host_module, "Fido2Server", lambda *args, **kwargs: object())
        monkeypatch.setattr(
            host_module, "PublicKeyCredentialRpEntity", lambda *args, **kwargs: object())
    project_id = wire.project_id_for(project)
    peer = oa.Peer("fixture-pm-sid", os.getpid(), 123, 1, "fixture-pm")
    instance = host_module.OperatorHost(
        tmp_path / "recovery-brake-host.db", origin="https://localhost:9443",
        projects={project_id: host_module.Project(
            project, frozenset([peer.sid]), frozenset([peer.image]))},
        operators={}, ttl_seconds=300, brake_read=decision_recovery.brake_facts,
        brake_trigger=decision_recovery.trigger_managed_brake,
        guard=lambda *_: True, verify_deployment=lambda *_: True)

    def exchange(purpose, message, trust, timeout_ms):
        assert purpose == "ask"
        return instance.handle(peer, message)

    class _Trust:
        class peer:
            pid = os.getpid()
            created_ns = 1

    monkeypatch.setattr(oa, "_exchange", exchange)
    monkeypatch.setattr(oa, "load_trust", lambda: _Trust())
    monkeypatch.setattr(oa, "registered_project", lambda pid: pid == project_id)
    return instance, peer, conductor


def _real_operator_host(root, tmp_path, monkeypatch, grant, *, actor, peer, clock=None):
    """The real host handler/writer/private-grant surface for one fixture project."""
    import operator_authority as oa
    import operator_host as host_module
    from autopilot import decision_recovery
    import decision_wire as wire

    project_id = wire.project_id_for(root)
    registration = host_module.Project(
        root,
        pm_sids=frozenset([peer.sid]),
        pm_images=frozenset([peer.image]),
        policy_sha256=grant["policy_sha256"],
        authority_records=grant["authority_source"],
        usage_sources=grant["usage_sources"],
        trusted_writers=tuple(grant["trusted_writers"]),
    )
    instance = host_module.OperatorHost(
        tmp_path / "real-chain-host.db", origin="https://localhost:9443",
        projects={project_id: registration},
        operators={actor.pin: host_module.Operator(
            actor.name, actor.data, frozenset(host_module.ROLES), frozenset([project_id]))},
        ttl_seconds=300,
        brake_read=decision_recovery.brake_facts,
        brake_trigger=decision_recovery.trigger_managed_brake,
        recovery_prepare=decision_recovery.prepare_operator_recovery,
        recovery_apply=decision_recovery.apply_operator_recovery,
        recovery_observe=decision_recovery.observe_operator_recovery,
        guard=lambda *_: True, verify_deployment=lambda *_: True,
        clock=clock or time.time)

    def exchange(purpose, message, trust, timeout_ms):
        assert purpose == "ask"
        return instance.handle(peer, message)

    class _Trust:
        class peer:
            pid = os.getpid()
            created_ns = 1

    monkeypatch.setattr(oa, "_exchange", exchange)
    monkeypatch.setattr(oa, "load_trust", lambda: _Trust())
    monkeypatch.setattr(oa, "registered_project", lambda pid: pid == project_id)
    return instance, project_id


def _confirm_private(instance, actor, request):
    from test_operator_authority import _assertion

    options = instance.private(actor.pin, "challenge", request)["options"]
    assertion = _assertion(actor, options, instance.origin)
    return instance.private(actor.pin, "confirm", {**request, "assertion": assertion})


@pytest.mark.parametrize("stop", ["revoked", "expired"])
def test_normal_conductor_trigger_trip_is_consumed_by_the_h12_consumer(
        tmp_path, monkeypatch, stop):
    """One real chain: conductor -> IPC -> host writer -> private grant ->
    authorized_callback -> real DecisionClient(FakeBackend) -> TS gate writer
    -> H12 apply/observe. No ``_authorized``/``_client_store`` mock."""
    import base64
    import datetime
    import time

    import operator_authority as oa
    from autopilot import conductor, decision_recovery, gates
    from test_operator_authority import Actor, FIDO
    from test_operator_authority import _require_fido

    _require_fido()
    assert FIDO is True
    import operator_host as host_module

    if host_module.Fido2Server is None:
        # This test module imports operator_host before the optional runtime
        # loader runs; bind the real SDK now, not a WebAuthn stand-in.
        from fido2.server import Fido2Server
        from fido2.webauthn import (
            AttestedCredentialData, AuthenticationResponse,
            PublicKeyCredentialRpEntity, UserVerificationRequirement)

        host_module.Fido2Server = Fido2Server
        host_module.AttestedCredentialData = AttestedCredentialData
        host_module.AuthenticationResponse = AuthenticationResponse
        host_module.PublicKeyCredentialRpEntity = PublicKeyCredentialRpEntity
        host_module.UserVerificationRequirement = UserVerificationRequirement
    backend = _real_backend("approve")
    root, grant, frozen, _backend, _store, gate_path, brake, ledger, old_trip = _recovery_fixture(
        tmp_path, monkeypatch, real_client=backend, real_authorization=True, hard_limit=30)
    # The chain must not be hidden by the fixture's former blanket authorization.
    assert decision_recovery._authorized.__module__ == "autopilot.decision_recovery"

    header = brake.read_bytes()
    events = "mw-breaker-event: " + json.dumps({
        "state": "observing", "trip_id": old_trip,
        "decision_ref": "dp-gate-approve:" + "a" * 32,
        "grant_ref": "b" * 32, "amount": 1, "usage_source": "round",
    }, sort_keys=True) + "\n"
    events += "mw-breaker-event: " + json.dumps(
        {"state": "clear", "trip_id": old_trip}, sort_keys=True) + "\n"
    brake.write_bytes(header + events.encode("utf-8"))

    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    for index in range(17):
        conductor._append_auto_decision_row(root, {
            "decision_id": f"real-{index}", "phase": "decide", "mode": "live",
            "executed": True, "decision": "approve", "rule_id": "fixture-rule",
            "reason_code": "fixture-run", "gate_id": f"gate-{9100 + index:04d}",
            "gate_key": f"key-{index}", "night": "2026-11-09",
            "decided_at": now,
        })

    pre_trigger_ledger = ledger.read_bytes()
    pre_trigger_brake = brake.read_bytes()

    actor = Actor()
    peer = oa.Peer("fixture-pm-sid", os.getpid(), 123, 1, "fixture-pm")
    issued_at = [time.time()]
    instance, project_id = _real_operator_host(
        root, tmp_path, monkeypatch, grant, actor=actor, peer=peer,
        clock=lambda: issued_at[0])
    assert decision_recovery._authorized.__module__ == "autopilot.decision_recovery"

    state = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(root)), None)
    assert conductor._trip_auto_breaker(
        root, state, "burst-60s", "17 auto decisions in 60s") is True
    trip = conductor.auto_breaker_state(root)["trip"]
    assert trip and trip != old_trip
    ledger_row = [row for row in conductor.auto_decision_rows(root)
                  if row.get("reason_code") == "breaker-tripped" and row.get("trip_id") == trip]
    assert len(ledger_row) == 1

    # The normal trigger leaves a real 17-row history with real timestamps.
    trigger_ledger = ledger.read_bytes()
    trigger_brake = brake.read_bytes()
    trigger_rows = conductor.auto_decision_rows(root)
    assert trigger_brake.startswith(pre_trigger_brake)
    assert trigger_ledger.startswith(pre_trigger_ledger)
    real_history = [row for row in trigger_rows
                    if str(row.get("decision_id", "")).startswith("real-")]
    assert len(real_history) == 17
    assert [row["decided_at"] for row in real_history] == [now] * 17
    assert len(trigger_rows) == len(pre_trigger_ledger.splitlines()) + 1
    assert len(decision_recovery._read_ledger(root)[2]) == len(trigger_rows)
    trigger_ledger_lines = trigger_ledger.splitlines(keepends=True)
    trigger_brake_lines = trigger_brake.splitlines(keepends=True)

    # Advance only decision_recovery's clock boundary; the real _now/_stamp
    # logic and the real _auto_breaker_signal still run. The same 17 rows with
    # their original real timestamps simply age past the 60s burst window: no
    # ledger byte, key order or line ending is rewritten to fake history.
    class _ControlledDateTime(datetime.datetime):
        moment = datetime.datetime.now(datetime.timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.moment if tz is None else cls.moment.astimezone(tz)

    class _ControlledClock:
        pass

    _ControlledClock.datetime = _ControlledDateTime
    _ControlledClock.timezone = datetime.timezone

    monkeypatch.setattr(decision_recovery, "datetime", _ControlledClock)
    _ControlledDateTime.moment += datetime.timedelta(seconds=61)
    assert ledger.read_bytes() == trigger_ledger
    assert conductor._auto_breaker_signal(
        conductor.auto_decision_rows(root), _ControlledDateTime.moment) is None

    # Bootstrap the real bind candidate, then issue the real private grant.
    bootstrap = {
        "schema": 1, "purpose": "h12", "project_id": project_id, "key": grant["key"],
        "trip_id": trip, "grant_ref": "0" * 32, "pm_note": _recovery_note(),
        "preparation": _recovery_preparation("2026-11-08T10:05:00+00:00"),
        "gate_id": "0" * 8, "action": "observe-brake",
    }
    refused = instance.handle(peer, {
        "v": 1, "op": "h12.prepare", "project_id": project_id,
        "payload_b64": base64.b64encode(
            json.dumps(bootstrap, sort_keys=True).encode("utf-8")).decode("ascii"),
        "grant_ref": "0" * 32, "trip_id": trip, "key": grant["key"]})
    assert refused["ok"] is False
    with instance.transaction() as db:
        candidate = db.execute("SELECT id FROM candidates").fetchone()[0]
    bind = instance.private(actor.pin, "propose", {
        "project_id": project_id, "op": "pm.bind",
        "terms": {"candidate_id": candidate}})
    assert _confirm_private(instance, actor, bind)["state"] == "applied"
    issued = instance.private(actor.pin, "propose", {
        "project_id": project_id, "op": "h12.grant",
        "terms": {
            "key": grant["key"], "binding_id": bind["id"], "trip_id": trip,
            "authority_ref": grant["authority_ref"], "scope": grant["scope"],
            "reason": grant["reason"], "unit": grant["unit"], "amount": 1,
            "usage_source": grant["usage_source"],
            "observation_conditions": grant["observation_conditions"],
            "stop_conditions": grant["stop_conditions"],
            "expires_at": datetime.datetime.fromtimestamp(
                issued_at[0] + 3600, datetime.timezone.utc).isoformat()}})
    assert _confirm_private(instance, actor, issued)["state"] == "applied"
    grant_ref = issued["id"]
    with instance.transaction() as db:
        grant_issued_at = db.execute(
            "SELECT issued FROM grants WHERE id=?", (grant_ref,)).fetchone()[0]
    grant_recorded_at = datetime.datetime.fromtimestamp(
        grant_issued_at, datetime.timezone.utc)
    trigger_recorded_at = decision_recovery._stamp(
        decision_recovery._rows(trigger_brake)[-1]["triggered_at"])
    assert trigger_recorded_at <= grant_recorded_at

    note = _recovery_note()
    matter = decision_recovery.recovery_matter(
        grant["key"], trip, grant["reason"], note, grant_ref)
    new_gate = gates.create(
        root / ".agenticdoc" / "_autopilot" / "gates", "stalled",
        "Recover one observing step after the real managed trip?",
        stage=1, key=grant["key"], pm_note=json.dumps(note, sort_keys=True),
        matter_ref=matter.matter_key, substantive_version=matter.substantive_version)
    request = {
        "schema": 1, "purpose": "h12", "project_id": project_id,
        "key": grant["key"], "trip_id": trip, "grant_ref": grant_ref,
        "gate_id": new_gate.stem, "pm_note": note,
        "preparation": json.loads(frozen)["preparation"], "action": "observe-brake",
    }
    real_frozen = json.dumps(request, ensure_ascii=False, sort_keys=True).encode("utf-8")
    prepared = instance.handle(peer, {
        "v": 1, "op": "h12.prepare", "project_id": project_id,
        "payload_b64": base64.b64encode(real_frozen).decode("ascii"),
        "grant_ref": grant_ref, "trip_id": trip, "key": grant["key"]})
    assert prepared["ok"] is True and prepared["state"] == "applied", prepared
    assert len(backend.calls) == 1
    observing = conductor.auto_breaker_state(root)
    assert observing["active"] is True and observing["state"] == "observing"
    assert observing["trip"] == trip
    observing_event = decision_recovery._rows(brake.read_bytes())[-1]
    answered_at = decision_recovery._stamp(gates.parse(new_gate).answered_at)
    assert grant_recorded_at.replace(microsecond=0) <= answered_at
    assert answered_at <= decision_recovery._stamp(observing_event["at"])

    # The service-side observation keeps the limited window while authorized.
    first = instance.observe(prepared["id"])
    assert first["ok"] is True and first["state"] == "observing", first
    # Revocation or expiry through the real private/host surface re-trips a
    # new generation; neither can leave a live observing licence behind.
    if stop == "revoked":
        revoke = instance.private(actor.pin, "propose", {
            "project_id": project_id, "op": "h12.revoke",
            "terms": {"grant_ref": grant_ref}})
        assert _confirm_private(instance, actor, revoke)["state"] == "applied"
    else:
        issued_at[0] += 7200
    second = instance.observe(prepared["id"])
    assert second["ok"] is True and second["state"] == "retripped", second
    assert second["consumer"]["trip_id"] != trip
    final = conductor.auto_breaker_state(root)
    assert final["active"] is True and final["state"] == "tripped"
    assert final["trip"] == second["consumer"]["trip_id"]
    # Replaying the prepared request after revocation is refused, not re-run.
    replay = instance.handle(peer, {
        "v": 1, "op": "h12.prepare", "project_id": project_id,
        "payload_b64": base64.b64encode(real_frozen).decode("ascii"),
        "grant_ref": grant_ref, "trip_id": trip, "key": grant["key"]})
    assert replay["ok"] is False
    assert len(backend.calls) == 1

    # Nothing in the real H12 chain rewrote the original trigger history: the
    # ledger only grew and the brake only appended its new generations.
    final_ledger = ledger.read_bytes()
    final_brake = brake.read_bytes()
    assert final_ledger.startswith(trigger_ledger)
    assert final_ledger.splitlines(keepends=True)[:len(trigger_ledger_lines)] == \
        trigger_ledger_lines
    assert final_brake.startswith(trigger_brake)
    assert final_brake.splitlines(keepends=True)[:len(trigger_brake_lines)] == \
        trigger_brake_lines
    assert conductor.auto_decision_rows(root)[:len(trigger_rows)] == trigger_rows
    new_events = decision_recovery._rows(final_brake)[-3:]
    assert [row["state"] for row in new_events] == ["tripped", "observing", "tripped"]
    stamps = [decision_recovery._stamp(row.get("at") or row.get("triggered_at"))
              for row in new_events]
    assert stamps[0] <= stamps[1] <= stamps[2]


def _real_backend(choice="approve", *, business=1):
    import decision

    if business != 1:
        return decision.FakeBackend([{
            "available": True, "reason": None, "retryable": False,
            "answers": None, "latency_ms": 5,
        }], name="timi-decisions", model="fake-model", confidence_source="api")
    return decision.FakeBackend([{
        "available": True, "reason": None, "retryable": False,
        "answers": {
            "gate_decision": {"value": choice, "confidence": 0.8},
            "basis_id": {"value": "b-approve", "confidence": 0.8},
        },
        "latency_ms": 5,
    }], name="timi-decisions", model="fake-model", confidence_source="api")


@pytest.mark.parametrize("choice", ["approve", "steer", "need_fix", "reject"])
def test_prepare_writes_the_one_formal_gate_answer_with_a_real_client(
        tmp_path, monkeypatch, choice):
    from autopilot import decision_recovery, gates

    backend = _real_backend(choice)
    root, grant, frozen, _backend, _store, gate_path, brake, _ledger, _trip = _recovery_fixture(
        tmp_path, monkeypatch, real_client=backend, choice=choice, with_ledger_sha256=False)
    before = brake.read_bytes()
    prepared = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert prepared["ok"] is True, prepared
    assert prepared["choice"] == choice
    assert len(backend.calls) == 1
    assert set(backend.calls[0]["questions"]) == {"gate_decision", "basis_id"}
    gate = gates.parse(gate_path)
    assert gate.transport == "answered" and gate.business == choice
    assert gate.decision_ref == prepared["decision_ref"] == "dp-gate-approve:" + grant["operation_id"]
    assert gate.model_basis == prepared["basis_text"]
    assert gate.answered_by == grant["claim"] and gate.effect == "not-started"
    assert gate.matter_ref == prepared["matter_ref"]
    assert gate.substantive_version == prepared["substantive_version"]
    assert brake.read_bytes() == before
    answered_bytes = gate_path.read_bytes()
    replay = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert replay["ok"] is True and replay["resumed"] is True and replay["choice"] == choice
    assert len(backend.calls) == 1
    assert gate_path.read_bytes() == answered_bytes


@pytest.mark.parametrize("choice", ["steer", "need_fix", "reject"])
def test_non_approve_answers_never_write_the_original_brake(tmp_path, monkeypatch, choice):
    from autopilot import decision_recovery, gates

    backend = _real_backend(choice)
    root, grant, frozen, _backend, _store, gate_path, brake, _ledger, _trip = _recovery_fixture(
        tmp_path, monkeypatch, real_client=backend, choice=choice, with_ledger_sha256=False)
    before = brake.read_bytes()
    prepared = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert prepared["ok"] is True
    applied = decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)
    assert applied["ok"] is False and applied["reason"] == "brake-remains-engaged"
    assert brake.read_bytes() == before
    assert gates.parse(gate_path).effect == "not-started"


def test_recovery_observation_retrips_when_the_grant_is_revoked(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    root, grant, frozen, _fake, _store, _gate, brake, _ledger, trip = _recovery_fixture(
        tmp_path, monkeypatch)
    prepared = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)["ok"]
    grant["revoked"] = True
    observed = decision_recovery.observe_operator_recovery(
        root, frozen, grant, observed_conditions=[])
    assert observed["ok"] is True and observed["state"] == "retripped"
    assert observed["retripped"] is True and observed["trip_id"] != trip
    rows = decision_recovery._rows(brake.read_bytes())
    assert [row["state"] for row in rows] == ["tripped", "observing", "tripped"]
    assert rows[1]["trip_id"] == trip and rows[1]["decision_ref"] == prepared["decision_ref"]
    assert decision_recovery.managed_brake_state(root)["active"] is True


def test_recovery_apply_completes_the_gate_marker_after_a_crash(tmp_path, monkeypatch):
    from autopilot import decision_recovery, gate_effects, gates

    root, grant, frozen, _fake, _store, gate_path, brake, _ledger, _trip = _recovery_fixture(
        tmp_path, monkeypatch)
    prepared = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    assert decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)["ok"]
    after = brake.read_bytes()
    gate_effects._replace_effect(gates.parse(gate_path), "in-progress")
    replay = decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)
    assert replay["ok"] is True and replay["effect"] == "applied" and replay["resumed"] is True
    assert brake.read_bytes() == after
    assert gates.parse(gate_path).effect == "applied"


def test_recovery_apply_never_repeats_an_unproven_reserved_effect(tmp_path, monkeypatch):
    from autopilot import decision_recovery, gate_effects, gates

    root, grant, frozen, _fake, _store, gate_path, brake, _ledger, _trip = _recovery_fixture(
        tmp_path, monkeypatch)
    prepared = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    before = brake.read_bytes()
    gate_effects._replace_effect(gates.parse(gate_path), "in-progress")
    applied = decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)
    assert applied["ok"] is False and applied["reason"] == "recovery-effect-unknown"
    assert brake.read_bytes() == before
    assert b"mw-breaker-event:" not in brake.read_bytes()
    assert gates.parse(gate_path).effect == "unknown"


def test_recovery_apply_refuses_a_changed_answered_gate(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    root, grant, frozen, _fake, _store, gate_path, brake, _ledger, _trip = _recovery_fixture(
        tmp_path, monkeypatch)
    prepared = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    changed = gate_path.read_text(encoding="utf-8").replace(
        "model_basis: ", "model_basis: 'other basis' # ", 1)
    gate_path.write_text(changed, encoding="utf-8")
    before = brake.read_bytes()
    applied = decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)
    assert applied["ok"] is False
    assert applied["reason"] in {"gate-answer-mismatch", "recovery-evidence-unavailable"}
    assert brake.read_bytes() == before

def test_recovery_apply_never_reapplies_an_already_applied_gate(tmp_path, monkeypatch):
    from autopilot import decision_recovery, gates

    root, grant, frozen, _fake, _store, gate_path, brake, _ledger, _trip = _recovery_fixture(
        tmp_path, monkeypatch)
    prepared = decision_recovery.prepare_operator_recovery(root, frozen, grant)
    original = brake.read_bytes()
    assert decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)["ok"]
    assert gates.parse(gate_path).effect == "applied"
    brake.write_bytes(original)  # the object receipt is gone/rolled back
    after = brake.read_bytes()
    replay = decision_recovery.apply_operator_recovery(root, frozen, grant, prepared)
    assert replay["ok"] is False and replay["reason"] == "recovery-effect-unknown"
    assert replay["effect"] == "applied"
    assert brake.read_bytes() == after


# ── T21 halted consumer: H11 real handler over the actual roadmap stage ────

_H11_KEY = "dpc-t21-halted"


def _h11_roadmap(root):
    path = root / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Roadmap\n> generated_at: 2026-11-09T00:00:00Z\n\n"
        "## Stage 1: Halted integration\n"
        "> goal: Ship the halted stage\n"
        "> status: halted\n"
        f"> key-status: {_H11_KEY}=stalled\n"
        "### Keys\n| key | role | depends_on |\n|---|---|---|\n"
        f"| {_H11_KEY} | implement | - |\n\n"
        "## Stage 2: Next\n> goal: Follow-up\n> status: pending\n"
        "### Keys\n| key | role | depends_on |\n|---|---|---|\n"
        f"| next-key | implement | {_H11_KEY} |\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _h11_halt_gate(root, note_text):
    from autopilot import conductor, gates

    directory = root / ".agenticdoc" / "_autopilot" / "gates"
    path = gates.create(directory, "stage-close", "Close stage 1? reject=halt", stage=1)
    raw = path.read_text(encoding="utf-8")
    raw = raw.replace("status: pending", "status: rejected", 1)
    raw = raw.replace("answered_at:", "answered_at: 2026-11-09T00:00:00+00:00", 1)
    raw = raw.replace("answered_by:", "answered_by: 'human:operator'", 1)
    raw = raw.replace("note:", "note: " + gates._render_scalar(note_text), 1)
    path.write_text(raw, encoding="utf-8", newline="\n")
    conductor.timeline.Timeline(conductor.timeline.timeline_path(root)).append(
        "gate-answered", stage=1, detail=f"{path.stem} rejected -> stage 1 halted"
    )
    return path


def _h11_stop_record(origin="technical", *, hard_guard_active=False, cleared=(), verified=False):
    return json.dumps(
        {
            "schema": 1,
            "halt_origin": origin,
            "stop_reason": "worker stall exceeded the watchdog",
            "hard_guard_active": hard_guard_active,
            "hard_guard_cleared": list(cleared),
            "hard_guard_cleared_verified": verified,
        },
        sort_keys=True,
        separators=(",", ":"),
    )


def _h11_fixture(
    tmp_path,
    monkeypatch,
    *,
    stop_origin="technical",
    note_text=None,
    hard_guard_active=False,
    hard_guard_cleared=(),
    hard_guard_verified=False,
    limit=3,
    rounds=1,
    human=False,
    choice="approve",
    real_client=None,
    client=None,
    with_policy_sha=True,
):
    from autopilot import decision_recovery, gates
    import decision
    import decision_lifecycle as lifecycle
    import decision_wire as wire
    import socket

    root = tmp_path / "h11-project"
    (root / ".agenticdoc" / "_autopilot" / "gates").mkdir(parents=True)
    claim = f"{socket.gethostname()}:{os.getpid()}"
    (root / ".agenticdoc" / "_index.parallel").write_text(
        "| Key | Status | Phase | Claim | Deps | Desc | Updated |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| {_H11_KEY} | active | 4 | {claim} | | T21 H11 fixture | 2026-11-09T00:00:00Z |\n",
        encoding="utf-8",
        newline="\n",
    )
    doc = _policy_doc(
        scope=[
            f"key:{_H11_KEY}",
            "action:gate-approve",
            "recovery:halted",
            "recovery:user-stop",
            "recover-halted",
            "action:recover-halted",
        ],
        hard_limits=[{"unit": "round", "limit": limit, "usage_source": "task-card-rounds"}],
    )
    doc["recovery"] = {
        "allowed_origins": ["pm-controlled"],
        "scope": ["recovery:halted", "recovery:user-stop", "recovery:breaker"],
        "authority_ref": "grant-h11",
        "observation_conditions": ["same-failure-reappears"],
        "stop_conditions": ["recovery-reason-reappears"],
    }
    _load(root, doc)
    (root / ".agenticdoc" / "_autopilot" / "config.json").write_text(
        json.dumps({"enabled": True, "paused": False, "auto_gate_mode": "live"}),
        encoding="utf-8",
    )
    writer = FixtureAuthorityWriter(root)
    base_scope = [
        f"key:{_H11_KEY}",
        "action:gate-approve",
        "recovery:halted",
        "recover-halted",
        "action:recover-halted",
    ]
    records = []
    for ref, scopes, supersedes in (
        ("grant-dpc-t07", [f"key:{_H11_KEY}", "action:gate-approve"], ()),
        ("grant-h11", base_scope, ()),
        ("grant-human", base_scope + ["recovery:user-stop"], ("grant-h11",)),
    ):
        record, issues = writer.grant(ref, scopes, supersedes=supersedes)
        assert issues == (), [issue.code for issue in issues]
        records.append(record)
    authority = {
        ref: json.loads((root / "authority" / f"{ref}.json").read_text(encoding="utf-8"))
        for ref in ("grant-dpc-t07", "grant-h11", "grant-human")
    }
    for index in range(rounds):
        directory = root / ".agenticdoc" / _H11_KEY / "workers" / f"worker-{index}"
        directory.mkdir(parents=True)
        (directory / "task.md").write_text(
            f"---\nloop: L1\nattempt: {index + 1}\n---\n", encoding="utf-8"
        )
    _h11_roadmap(root)
    if note_text is None:
        note_text = _h11_stop_record(
            stop_origin,
            hard_guard_active=hard_guard_active,
            cleared=hard_guard_cleared,
            verified=hard_guard_verified,
        )
    halt_gate = _h11_halt_gate(root, note_text)
    facts = decision_recovery.halted_stage_facts(root)
    note = {
        "stop_reason": facts["stop_reason"],
        "elimination_evidence": ["worker watchdog trace shows the stall is gone"],
        "stage_version": facts["stage_version"],
        "affected_keys": [_H11_KEY],
        "target_plan": "rerun the halted stage gate",
        "authority_ref": "grant-human" if human else "grant-h11",
        "residual_budget": {"round": limit - rounds},
        "stop_criterion": "two consecutive green runs",
    }
    grant_ref = "a" * 32
    operation_id = "b" * 32
    matter = decision_recovery.halted_recovery_matter(_H11_KEY, facts, note, grant_ref)
    gate_path = gates.create(
        root / ".agenticdoc" / "_autopilot" / "gates",
        "stalled",
        "Recover the halted stage inside the approved observation?",
        stage=1,
        key=_H11_KEY,
        pm_note=json.dumps(note, sort_keys=True),
        matter_ref=matter.matter_key,
        substantive_version=matter.substantive_version,
    )
    grant = {
        "project_id": wire.project_id_for(root),
        "key": _H11_KEY,
        "stage": 1,
        "stage_version": facts["stage_version"],
        "stop_sha256": facts["stop_sha256"],
        "halt_gate_id": halt_gate.stem,
        "grant_ref": grant_ref,
        "operation_id": operation_id,
        "claim": claim,
        "revoked": False,
        "recorded_at": "2026-01-01T00:00:00+00:00",
        "expires_at": "2030-01-01T00:00:00+00:00",
        "authority_source": authority,
        "trusted_writers": [TRUSTED_WRITER],
        "usage_sources": {"task-card-rounds": {"kind": "task-card-rounds", "unit": "round"}},
        "authority_ref": "grant-human" if human else "grant-h11",
        "scope": base_scope + ["recovery:user-stop"] if human else base_scope,
        "reason": facts["stop_reason"],
        "unit": "round",
        "amount": 1,
        "usage_source": "task-card-rounds",
    }
    if with_policy_sha:
        grant["policy_sha256"] = hashlib.sha256(
            policy_mod.policy_path(root).read_bytes()
        ).hexdigest()
    preparation = _recovery_preparation("2026-11-09T00:05:00+00:00", choice)
    request = {
        "schema": 1,
        "purpose": "h11",
        "project_id": grant["project_id"],
        "key": _H11_KEY,
        "stage": 1,
        "stage_version": facts["stage_version"],
        "stop_sha256": facts["stop_sha256"],
        "grant_ref": grant_ref,
        "gate_id": gate_path.stem,
        "pm_note": note,
        "preparation": preparation,
        "action": "recover-halted",
    }
    frozen = json.dumps(request, ensure_ascii=False, sort_keys=True).encode("utf-8")
    store = lifecycle.LifecycleStore.production(
        root, redact=wire.SubstringRedactor(secrets=())
    )
    fake = client or real_client or _FakePreparedClient(choice=choice)
    monkeypatch.setattr(decision_recovery, "_authorized", lambda *args: True)
    if real_client is not None:
        (root / ".mw").mkdir(parents=True, exist_ok=True)
        (root / ".mw" / "decide.json").write_text(
            json.dumps(
                {
                    "enabled": True,
                    "transport": "timi-decisions",
                    "max_questions": 8,
                    "max_retries": 0,
                }
            ),
            encoding="utf-8",
        )
        real = decision.DecisionClient
        monkeypatch.setattr(
            decision,
            "DecisionClient",
            lambda cfg, **kwargs: real(cfg, backend=real_client, **kwargs),
        )
    else:
        monkeypatch.setattr(decision_recovery, "_client_store", lambda _root: (fake, store))
    return {
        "root": root,
        "grant": grant,
        "frozen": frozen,
        "fake": fake,
        "store": store,
        "gate_path": gate_path,
        "roadmap": root / ".agenticdoc" / "_autopilot" / "_roadmap.md",
        "facts": facts,
        "note": note,
        "halt_gate": halt_gate,
        "matter": matter,
    }


def _h11_gate(parts):
    from autopilot import gates

    return gates.parse(parts["gate_path"])


def _h11_recovery_rows(parts):
    from autopilot import decision_recovery

    return decision_recovery.halted_recovery_rows(parts["roadmap"].read_text(encoding="utf-8"), 1)


def test_h11_ordinary_shell_cannot_enter_the_halted_recovery_callback(tmp_path):
    from autopilot import decision_recovery

    work = tmp_path / "ordinary-h11"
    work.mkdir()
    raw = b'{"purpose":"h11","authorized":true}'
    assert decision_recovery.prepare_halted_recovery(work, raw, {}) == {
        "ok": False,
        "reason": "operator-host-required",
    }
    assert decision_recovery.apply_halted_recovery(
        work, raw, {}, {"choice": "approve"}
    ) == {"ok": False, "reason": "operator-host-required"}
    assert not list(work.iterdir())


def test_h11_prepare_uses_the_real_halted_stage_and_the_one_gate_writer(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    backend = _real_backend("approve")
    parts = _h11_fixture(tmp_path, monkeypatch, real_client=backend)
    original = parts["roadmap"].read_bytes()
    prepared = decision_recovery.prepare_halted_recovery(
        parts["root"], parts["frozen"], parts["grant"]
    )
    assert prepared["ok"] is True, prepared
    assert prepared["choice"] == "approve"
    assert prepared["stage_version"] == parts["facts"]["stage_version"]
    assert prepared["stop_sha256"] == parts["facts"]["stop_sha256"]
    assert prepared["decision_ref"] == "dp-gate-approve:" + parts["grant"]["operation_id"]
    assert len(backend.calls) == 1
    assert set(backend.calls[0]["questions"]) == {"gate_decision", "basis_id"}
    gate = _h11_gate(parts)
    assert gate.transport == "answered" and gate.business == "approve"
    assert gate.effect == "not-started"
    assert gate.matter_ref == parts["matter"].matter_key
    assert gate.substantive_version == parts["matter"].substantive_version
    assert gate.answered_by == parts["grant"]["claim"]
    assert parts["roadmap"].read_bytes() == original
    assert len(_lifecycle_rows(parts["store"], "request")) == 1
    answered = parts["gate_path"].read_bytes()
    replay = decision_recovery.prepare_halted_recovery(
        parts["root"], parts["frozen"], parts["grant"]
    )
    assert replay["ok"] is True and replay["resumed"] is True
    assert replay["choice"] == "approve"
    assert len(backend.calls) == 1
    assert parts["gate_path"].read_bytes() == answered
    _verify("VC-034", erased_stop_facts=0, reset_usage=0, unsupported_resumes=0)


def test_h11_apply_appends_a_recovery_version_and_keeps_the_stop_facts(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    parts = _h11_fixture(tmp_path, monkeypatch)
    prepared = decision_recovery.prepare_halted_recovery(
        parts["root"], parts["frozen"], parts["grant"]
    )
    assert prepared["ok"] is True
    original = parts["roadmap"].read_bytes()
    applied = decision_recovery.apply_halted_recovery(
        parts["root"], parts["frozen"], parts["grant"], prepared
    )
    assert applied["ok"] is True, applied
    assert applied["state"] == "recovered" and applied["effect"] == "applied"
    after = parts["roadmap"].read_bytes()
    assert after.startswith(original)
    assert hashlib.sha256(after).hexdigest() == applied["receipt_sha256"]
    rows = _h11_recovery_rows(parts)
    assert len(rows) == 1
    row = rows[0]
    assert row["decision_ref"] == prepared["decision_ref"]
    assert row["from_version"] == parts["facts"]["stage_version"]
    assert row["to_version"] != row["from_version"]
    assert row["stop_reason"] == parts["facts"]["stop_reason"]
    assert row["halt_origin"] == "technical"
    assert row["consumed"] == {"round": 1}
    text = after.decode("utf-8")
    assert "status: halted" in text
    assert parts["facts"]["halt_gate_id"] in text
    assert len(_lifecycle_rows(parts["store"], "executed")) == 1
    assert len(_lifecycle_rows(parts["store"], "settled")) == 1
    replay = decision_recovery.apply_halted_recovery(
        parts["root"], parts["frozen"], parts["grant"], prepared
    )
    assert replay["ok"] is True and replay["resumed"] is True
    assert replay["receipt_sha256"] == applied["receipt_sha256"]
    assert len(_h11_recovery_rows(parts)) == 1
    assert len(_lifecycle_rows(parts["store"], "executed")) == 1
    _verify("VC-034", erased_stop_facts=0, reset_usage=0, unsupported_resumes=0)
    _verify("VC-052", duplicate_effects=0, duplicate_approvals=0, concurrent_writers=0,
            lock_bypasses=0, stale_releases=0, irrelevant_reapprovals=0)


def test_h11_user_stop_needs_an_explicit_human_recovery_grant(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    parts = _h11_fixture(tmp_path, monkeypatch, stop_origin="user-stop")
    refused = decision_recovery.prepare_halted_recovery(
        parts["root"], parts["frozen"], parts["grant"]
    )
    assert refused["ok"] is False
    assert "user-stop-requires-explicit-authorization" in refused["reason"] or "scope" in refused["reason"]
    assert parts["fake"].calls == []
    assert _h11_gate(parts).transport == "pending"

    lifted = _h11_fixture(tmp_path / "lift", monkeypatch, stop_origin="user-stop", human=True)
    prepared = decision_recovery.prepare_halted_recovery(
        lifted["root"], lifted["frozen"], lifted["grant"]
    )
    assert prepared["ok"] is True, prepared
    applied = decision_recovery.apply_halted_recovery(
        lifted["root"], lifted["frozen"], lifted["grant"], prepared
    )
    assert applied["ok"] is True, applied
    row = _h11_recovery_rows(lifted)[0]
    assert row["halt_origin"] == "user-stop"
    assert row["stop_reason"] == lifted["facts"]["stop_reason"]
    assert "status: halted" in lifted["roadmap"].read_text(encoding="utf-8")
    _verify("VC-035", unauthorized_user_stop_unlocks=0, hard_guard_bypasses=0, false_resumes=0)


def test_h11_hard_guard_and_legacy_unknown_origin_stay_halted(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    guard = _h11_fixture(
        tmp_path, monkeypatch, hard_guard_active=True, hard_guard_cleared=[],
        hard_guard_verified=False,
    )
    refused = decision_recovery.prepare_halted_recovery(
        guard["root"], guard["frozen"], guard["grant"]
    )
    assert refused["ok"] is False and "hard-guard" in refused["reason"]
    assert guard["fake"].calls == []
    assert guard["roadmap"].read_text(encoding="utf-8").count("status: halted") == 1

    legacy = _h11_fixture(
        tmp_path / "legacy", monkeypatch, note_text="stage close rejected for quality"
    )
    unknown = decision_recovery.prepare_halted_recovery(
        legacy["root"], legacy["frozen"], legacy["grant"]
    )
    assert unknown["ok"] is False and "hard-guard-unknown" in unknown["reason"]
    assert legacy["fake"].calls == []
    _verify("VC-035", unauthorized_user_stop_unlocks=0, hard_guard_bypasses=0, false_resumes=0)


def test_h11_revoked_grant_and_changed_stop_facts_are_refused_before_the_model(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    revoked = _h11_fixture(tmp_path / "revoked", monkeypatch)
    revoked["grant"]["revoked"] = True
    refused = decision_recovery.prepare_halted_recovery(
        revoked["root"], revoked["frozen"], revoked["grant"]
    )
    assert refused["ok"] is False
    assert refused["reason"] == "preauthorization-expired-or-revoked"
    assert revoked["fake"].calls == []

    changed = _h11_fixture(tmp_path / "changed", monkeypatch)
    text = changed["roadmap"].read_text(encoding="utf-8")
    changed["roadmap"].write_text(
        text.replace("Ship the halted stage", "Ship a different halted stage"),
        encoding="utf-8",
    )
    stale = decision_recovery.prepare_halted_recovery(
        changed["root"], changed["frozen"], changed["grant"]
    )
    assert stale["ok"] is False
    assert "stop-fact-changed" in stale["reason"] or "stop-record" in stale["reason"]
    assert changed["fake"].calls == []


def test_h11_budget_uses_real_cumulative_worker_rounds_and_never_resets(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    exhausted = _h11_fixture(tmp_path / "exhausted", monkeypatch, limit=3, rounds=3)
    refused = decision_recovery.prepare_halted_recovery(
        exhausted["root"], exhausted["frozen"], exhausted["grant"]
    )
    assert refused["ok"] is False
    assert "hard-budget" in refused["reason"] or "budget" in refused["reason"]
    assert exhausted["fake"].calls == []

    positive = _h11_fixture(tmp_path / "ok", monkeypatch, limit=3, rounds=2)
    prepared = decision_recovery.prepare_halted_recovery(
        positive["root"], positive["frozen"], positive["grant"]
    )
    assert prepared["ok"] is True, prepared
    assert positive["note"]["residual_budget"] == {"round": 1}
    _verify("VC-021", hard_budget_overruns=0, self_granted_limits=0, reset_usage=0)


def test_h11_apply_never_repeats_an_unproven_reserved_effect(tmp_path, monkeypatch):
    from autopilot import decision_recovery, gate_effects, gates

    parts = _h11_fixture(tmp_path, monkeypatch)
    prepared = decision_recovery.prepare_halted_recovery(
        parts["root"], parts["frozen"], parts["grant"]
    )
    before = parts["roadmap"].read_bytes()
    gate_effects._replace_effect(gates.parse(parts["gate_path"]), "in-progress")
    applied = decision_recovery.apply_halted_recovery(
        parts["root"], parts["frozen"], parts["grant"], prepared
    )
    assert applied["ok"] is False and applied["reason"] == "recovery-effect-unknown"
    assert parts["roadmap"].read_bytes() == before
    assert _h11_recovery_rows(parts) == []
    assert gates.parse(parts["gate_path"]).effect == "unknown"


@pytest.mark.parametrize("choice", ["steer", "need_fix", "reject"])
def test_h11_non_approve_answers_leave_the_stage_halted(tmp_path, monkeypatch, choice):
    from autopilot import decision_recovery, gates

    parts = _h11_fixture(tmp_path / choice, monkeypatch, real_client=_real_backend(choice),
                        choice=choice)
    before = parts["roadmap"].read_bytes()
    prepared = decision_recovery.prepare_halted_recovery(
        parts["root"], parts["frozen"], parts["grant"]
    )
    assert prepared["ok"] is True, prepared
    applied = decision_recovery.apply_halted_recovery(
        parts["root"], parts["frozen"], parts["grant"], prepared
    )
    assert applied["ok"] is False and applied["reason"] == "stage-remains-halted"
    assert applied["choice"] == choice
    assert parts["roadmap"].read_bytes() == before
    assert gates.parse(parts["gate_path"]).effect == "not-started"
    assert len(_h11_recovery_rows(parts)) == 0
    assert len(_lifecycle_rows(parts["store"], "settled")) == 1
    _verify("VC-035", unauthorized_user_stop_unlocks=0, hard_guard_bypasses=0, false_resumes=0)


def test_h11_a_second_recovery_needs_the_first_observation(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    parts = _h11_fixture(tmp_path, monkeypatch)
    prepared = decision_recovery.prepare_halted_recovery(
        parts["root"], parts["frozen"], parts["grant"]
    )
    assert prepared["ok"] is True
    assert decision_recovery.apply_halted_recovery(
        parts["root"], parts["frozen"], parts["grant"], prepared
    )["ok"] is True
    calls = len(parts["fake"].calls)
    after = parts["roadmap"].read_bytes()
    second = dict(parts["grant"])
    second["operation_id"] = "d" * 32
    request = json.loads(parts["frozen"])
    refused = decision_recovery.prepare_halted_recovery(
        parts["root"], json.dumps(request, sort_keys=True).encode("utf-8"), second
    )
    assert refused["ok"] is False and refused["reason"] == "recovery-already-recorded"
    assert len(parts["fake"].calls) == calls
    assert parts["roadmap"].read_bytes() == after
    _verify("VC-034", erased_stop_facts=0, reset_usage=0, unsupported_resumes=0)


def test_h11_h12_grant_and_request_are_not_an_h11_authorization(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    parts = _h11_fixture(tmp_path, monkeypatch)
    h12_request = json.loads(parts["frozen"])
    h12_request.update(purpose="h12", action="observe-brake")
    h12_request.pop("stop_sha256")
    h12_request["trip_id"] = "c" * 32
    refused = decision_recovery.prepare_halted_recovery(
        parts["root"],
        json.dumps(h12_request, sort_keys=True).encode("utf-8"),
        parts["grant"],
    )
    assert refused["ok"] is False
    assert "invalid-recovery-request" in refused["reason"]

    narrow = dict(parts["grant"])
    narrow["scope"] = ["recovery:breaker", "observe-brake", parts["grant"]["key"]]
    refused_scope = decision_recovery.prepare_halted_recovery(
        parts["root"], parts["frozen"], narrow
    )
    assert refused_scope["ok"] is False
    assert refused_scope["reason"] == "grant-scope-mismatch"
    assert parts["fake"].calls == []
    _verify("VC-036", breaker_self_approvals=0, unauthorized_recoveries=0, transport_bypasses=0)

# ── T21 pm-source: normal PM entry over the protected authority source ──────

_PM_H11_SID = "S-1-5-21-1-2-3"
_PM_H11_IMAGE = r"C:\fixture\pi.exe"


def _pm_h11_record(ref, scope, *, kind="user-grant", revoked=False, supersedes=()):
    return {
        "authority_ref": ref,
        "kind": kind,
        "scope": list(scope),
        "writer": TRUSTED_WRITER,
        "revoked": revoked,
        "recorded_at": "2026-01-01T00:00:00+00:00",
        "supersedes": list(supersedes),
    }


def _pm_h11_host(tmp_path, root, records, policy_sha, *, pid=None):
    import socket

    import decision_wire as wire

    project_id = wire.project_id_for(root)
    row = {
        "root": str(root),
        "pm_sids": [_PM_H11_SID],
        "pm_images": [_PM_H11_IMAGE],
        "trusted_writers": [TRUSTED_WRITER],
        "authority_records": records,
        "usage_sources": {"task-card-rounds": {"kind": "task-card-rounds", "unit": "round"}},
        "policy_sha256": policy_sha,
    }
    path = tmp_path / "host.json"
    path.write_text(
        json.dumps({"schema": 1, "projects": {project_id: row}}),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _pm_h11_boundary(monkeypatch, host_path):
    import os

    import operator_authority as oa

    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    trust = oa.ServiceTrust(
        oa.Peer("fixture-service", os.getpid() + 1, 1, 0, "fixture-service"), host_path
    )
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    monkeypatch.setattr(oa, "trusted_path", lambda candidate, *_a, **_k: pathlib.Path(candidate))
    peer = oa.Peer(_PM_H11_SID, os.getpid(), 123, 1, _PM_H11_IMAGE)
    monkeypatch.setattr(oa, "_process_peer", lambda _pid, _stack: peer, raising=False)
    return oa


def _pm_h11_fixture(
    tmp_path,
    monkeypatch,
    *,
    stop_origin="technical",
    human=False,
    limit=3,
    rounds=1,
    choice="approve",
    on_decision=None,
    note_overrides=None,
    extra_records=(),
    policy_sha_pinned=True,
):
    import socket

    import decision
    import operator_authority as oa
    from autopilot import decision_recovery, gates

    root = tmp_path / "project"
    (root / ".agenticdoc" / "_autopilot" / "gates").mkdir(parents=True)
    claim = f"{socket.gethostname()}:{os.getpid()}"
    (root / ".agenticdoc" / "_index.parallel").write_text(
        "| Key | Status | Phase | Claim | Deps | Desc | Updated |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| {_H11_KEY} | active | 4 | {claim} | | T21 PM source fixture | 2026-11-09T00:00:00Z |\n",
        encoding="utf-8",
        newline="\n",
    )
    base_scope = [
        f"key:{_H11_KEY}",
        "action:gate-approve",
        "recovery:halted",
        "recover-halted",
        "action:recover-halted",
    ]
    doc = _policy_doc(
        scope=[f"key:{_H11_KEY}", "action:gate-approve"],
        hard_limits=[{"unit": "round", "limit": limit, "usage_source": "task-card-rounds"}],
    )
    doc["recovery"] = {
        "allowed_origins": ["pm-controlled"],
        "scope": ["recovery:halted", "recovery:user-stop", "recovery:breaker"],
        "authority_ref": "grant-h11",
        "observation_conditions": ["same-failure-reappears"],
        "stop_conditions": ["recovery-reason-reappears"],
    }
    _load(root, doc)
    (root / ".agenticdoc" / "_autopilot" / "config.json").write_text(
        json.dumps({"enabled": True, "paused": False, "auto_gate_mode": "live"}),
        encoding="utf-8",
    )
    for index in range(rounds):
        directory = root / ".agenticdoc" / _H11_KEY / "workers" / f"worker-{index}"
        directory.mkdir(parents=True)
        (directory / "task.md").write_text(
            f"---\nloop: L1\nattempt: {index + 1}\n---\n", encoding="utf-8"
        )
    _h11_roadmap(root)
    halt_gate = _h11_halt_gate(root, _h11_stop_record(stop_origin))
    facts = decision_recovery.halted_stage_facts(root)
    note = {
        "stop_reason": facts["stop_reason"],
        "elimination_evidence": ["worker watchdog trace shows the stall is gone"],
        "stage_version": facts["stage_version"],
        "affected_keys": [_H11_KEY],
        "target_plan": "rerun the halted stage gate",
        "authority_ref": "grant-human" if human else "grant-h11",
        "residual_budget": {"round": limit - rounds},
        "stop_criterion": "two consecutive green runs",
    }
    if note_overrides:
        note.update(note_overrides)
    policy_sha = hashlib.sha256(policy_mod.policy_path(root).read_bytes()).hexdigest()
    records = {
        "grant-dpc-t07": _pm_h11_record(
            "grant-dpc-t07", [f"key:{_H11_KEY}", "action:gate-approve"]
        ),
        "grant-h11": _pm_h11_record("grant-h11", base_scope),
        "grant-h12": _pm_h11_record("grant-h12", ["recovery:breaker"]),
        "grant-human": _pm_h11_record(
            "grant-human", base_scope + ["recovery:user-stop"], supersedes=["grant-h11"]
        ),
    }
    records.update({row["authority_ref"]: row for row in extra_records})
    host = _pm_h11_host(
        tmp_path, root, records, policy_sha if policy_sha_pinned else ""
    )
    _pm_h11_boundary(monkeypatch, host)
    grant_ref = decision_recovery.pm_halted_recovery_ref(facts, note)
    matter = decision_recovery.halted_recovery_matter(_H11_KEY, facts, note, grant_ref)

    gate_path = gates.create(
        root / ".agenticdoc" / "_autopilot" / "gates",
        "stalled",
        "Recover the halted stage from its protected PM authority?",
        stage=1,
        key=_H11_KEY,
        pm_note=json.dumps(note, sort_keys=True),
        matter_ref=matter.matter_key,
        substantive_version=matter.substantive_version,
    )
    submission = {
        "stage": 1,
        "stage_version": facts["stage_version"],
        "gate_id": gate_path.stem,
        "pm_note": note,
        "preparation": _recovery_preparation("2026-11-09T00:05:00+00:00", choice),
    }
    (root / ".mw").mkdir(parents=True, exist_ok=True)
    (root / ".mw" / "decide.json").write_text(
        json.dumps({"enabled": True, "transport": "timi-decisions",
                    "max_questions": 8, "max_retries": 0}),
        encoding="utf-8",
    )
    backend = decision.FakeBackend(
        [on_decision if on_decision is not None else {
            "available": True, "reason": None, "retryable": False,
            "answers": {
                "gate_decision": {"value": choice, "confidence": 0.8},
                "basis_id": {"value": "b-approve", "confidence": 0.8},
            },
            "latency_ms": 1,
        }],
        name="timi-decisions", model="fake-model", confidence_source="api",
    )
    real_client = getattr(decision.DecisionClient, "_dpc_original", decision.DecisionClient)

    def client_factory(cfg, **kwargs):
        return real_client(cfg, backend=backend, **kwargs)

    client_factory._dpc_original = real_client
    monkeypatch.setattr(decision, "DecisionClient", client_factory)
    return {
        "root": root,
        "host": host,
        "submission": submission,
        "facts": facts,
        "note": note,
        "gate_path": gate_path,
        "halt_gate": halt_gate,
        "roadmap": root / ".agenticdoc" / "_autopilot" / "_roadmap.md",
        "backend": backend,
        "record": records["grant-human" if human else "grant-h11"],
        "authority": oa,
    }


def _pm_h11_rows(parts):
    from autopilot import decision_recovery

    return decision_recovery.halted_recovery_rows(
        parts["roadmap"].read_text(encoding="utf-8"), 1
    )


def test_pm_h11_positive_technical_recovery_uses_the_protected_source_once(tmp_path, monkeypatch):
    from autopilot import decision_recovery, gates

    parts = _pm_h11_fixture(tmp_path, monkeypatch)
    original = parts["roadmap"].read_bytes()
    result = decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, parts["submission"]
    )
    assert result["ok"] is True, result
    assert result["choice"] == "approve"
    assert result["state"] == "recovered" and result["effect"] == "applied"
    assert len(parts["backend"].calls) == 1
    assert gates.parse(parts["gate_path"]).business == "approve"
    rows = _pm_h11_rows(parts)
    assert len(rows) == 1
    row = rows[0]
    assert row["authority_ref"] == "grant-h11"
    assert row["halt_origin"] == "technical"
    assert row["stop_reason"] == parts["facts"]["stop_reason"]
    assert row["stop_sha256"] == parts["facts"]["stop_sha256"]
    assert row["consumed"] == {"round": 1}
    assert parts["roadmap"].read_bytes().startswith(original)
    assert "status: halted" in parts["roadmap"].read_text(encoding="utf-8")

    replayed = decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, parts["submission"]
    )
    assert replayed["ok"] is True and replayed["resumed"] is True
    assert len(parts["backend"].calls) == 1
    assert len(_pm_h11_rows(parts)) == 1

    view = decision_recovery.read_halted_recovery_view(parts["root"], _H11_KEY)
    assert view["ok"] is True, view
    assert view["state"] == "bounded-recovery"
    assert view["stage_status"] == "halted"
    assert view["effective_version"] == row["to_version"]
    assert view["from_version"] == parts["facts"]["stage_version"]
    assert view["stop"]["stop_sha256"] == parts["facts"]["stop_sha256"]
    assert view["consumed"] == {"round": 1}
    assert view["remaining"] == {"round": 2}
    assert view["authority_ref"] == "grant-h11"
    _verify("VC-034", erased_stop_facts=0, reset_usage=0, unsupported_resumes=0)


def test_pm_h11_rejects_caller_supplied_authority_and_grant_material(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    parts = _pm_h11_fixture(tmp_path, monkeypatch)
    before = parts["roadmap"].read_bytes()
    for extra in ("grant", "authority_source", "trusted_writers", "usage", "hard_checks"):
        submission = dict(parts["submission"], **{extra: {"authorized": True}})
        refused = decision_recovery.run_pm_halted_recovery(
            parts["root"], _H11_KEY, submission
        )
        assert refused == {"ok": False, "reason": "invalid-pm-submission"}, refused
    forged = dict(parts["submission"])
    forged["pm_note"] = dict(parts["note"], stop_reason="a different stop")
    refused = decision_recovery.run_pm_halted_recovery(parts["root"], _H11_KEY, forged)
    assert refused["ok"] is False
    assert parts["backend"].calls == []
    assert parts["roadmap"].read_bytes() == before


def test_pm_h11_user_stop_without_a_human_source_stays_halted(tmp_path, monkeypatch):
    from autopilot import decision_recovery, gates

    parts = _pm_h11_fixture(tmp_path, monkeypatch, stop_origin="user-stop")
    before = parts["roadmap"].read_bytes()
    refused = decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, parts["submission"]
    )
    assert refused["ok"] is False
    assert "user-stop-requires-explicit-authorization" in refused["reason"]
    assert parts["backend"].calls == []
    assert parts["roadmap"].read_bytes() == before
    assert gates.parse(parts["gate_path"]).transport == "pending"
    _verify("VC-035", unauthorized_user_stop_unlocks=0, hard_guard_bypasses=0,
            false_resumes=0)


def test_pm_h11_user_stop_with_a_human_source_is_limited_and_preserved(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    parts = _pm_h11_fixture(tmp_path, monkeypatch, stop_origin="user-stop", human=True)
    result = decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, parts["submission"]
    )
    assert result["ok"] is True, result
    row = _pm_h11_rows(parts)[0]
    assert row["authority_ref"] == "grant-human"
    assert row["halt_origin"] == "user-stop"
    assert row["stop_reason"] == parts["facts"]["stop_reason"]
    assert "status: halted" in parts["roadmap"].read_text(encoding="utf-8")
    _verify("VC-035", unauthorized_user_stop_unlocks=0, hard_guard_bypasses=0,
            false_resumes=0)


def test_pm_h11_revoked_or_changed_source_refuses_before_the_model(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    revoked = _pm_h11_fixture(tmp_path / "revoked", monkeypatch, extra_records=[
        _pm_h11_record("grant-h11", [
            f"key:{_H11_KEY}", "action:gate-approve", "recovery:halted",
        ], revoked=True),
    ])
    refused = decision_recovery.run_pm_halted_recovery(
        revoked["root"], _H11_KEY, revoked["submission"]
    )
    assert refused == {"ok": False, "reason": "authority-revoked"}
    assert revoked["backend"].calls == []

    changed = _pm_h11_fixture(tmp_path / "policy", monkeypatch)
    path = policy_mod.policy_path(changed["root"])
    path.write_bytes(path.read_bytes().replace(b'"schema_version": 1', b'"schema_version": 1 '))
    refused = decision_recovery.run_pm_halted_recovery(
        changed["root"], _H11_KEY, changed["submission"]
    )
    assert refused["ok"] is False
    assert refused["reason"] == "policy-version-changed"
    assert changed["backend"].calls == []

    unclaimed = _pm_h11_fixture(tmp_path / "claim", monkeypatch)
    index = unclaimed["root"] / ".agenticdoc" / "_index.parallel"
    index.write_text(
        index.read_text(encoding="utf-8").replace(str(os.getpid()), str(os.getpid() + 1)),
        encoding="utf-8",
    )
    refused = decision_recovery.run_pm_halted_recovery(
        unclaimed["root"], _H11_KEY, unclaimed["submission"]
    )
    assert refused["ok"] is False
    assert refused["reason"] == "pm-claim-unbound"
    assert unclaimed["backend"].calls == []


def test_pm_h11_source_revoked_during_the_model_call_blocks_the_effect(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    holder = {}

    def decide(_state, _questions, _cfg):
        host = holder["parts"]["host"]
        payload = json.loads(host.read_text(encoding="utf-8"))
        for row in payload["projects"].values():
            row["authority_records"]["grant-h11"]["revoked"] = True
        host.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
        return {
            "available": True, "reason": None, "retryable": False,
            "answers": {
                "gate_decision": {"value": "approve", "confidence": 0.8},
                "basis_id": {"value": "b-approve", "confidence": 0.8},
            },
            "latency_ms": 1,
        }

    holder["parts"] = _pm_h11_fixture(tmp_path, monkeypatch, on_decision=decide)
    parts = holder["parts"]
    before = parts["roadmap"].read_bytes()
    refused = decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, parts["submission"]
    )
    assert refused["ok"] is False
    assert refused["reason"] in {"authority-source-changed", "authority-revoked"}
    assert len(parts["backend"].calls) == 1
    assert parts["roadmap"].read_bytes() == before
    assert _pm_h11_rows(parts) == []


def test_pm_h11_unknown_reserved_effect_is_not_applied_on_replay(tmp_path, monkeypatch):
    from autopilot import decision_recovery, gate_effects, gates

    holder = {}

    def decide(_state, _questions, _cfg):
        host = holder["parts"]["host"]
        holder["host_bytes"] = host.read_bytes()
        payload = json.loads(host.read_text(encoding="utf-8"))
        for row in payload["projects"].values():
            row["authority_records"]["grant-h11"]["revoked"] = True
        host.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
        return {
            "available": True, "reason": None, "retryable": False,
            "answers": {
                "gate_decision": {"value": "approve", "confidence": 0.8},
                "basis_id": {"value": "b-approve", "confidence": 0.8},
            },
            "latency_ms": 1,
        }

    holder["parts"] = _pm_h11_fixture(tmp_path, monkeypatch, on_decision=decide)
    parts = holder["parts"]
    assert decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, parts["submission"]
    )["ok"] is False
    assert _pm_h11_rows(parts) == []
    parts["host"].write_bytes(holder["host_bytes"])
    gate_effects._replace_effect(gates.parse(parts["gate_path"]), "in-progress")
    before = parts["roadmap"].read_bytes()
    applied = decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, parts["submission"]
    )
    assert applied["ok"] is False and applied["reason"] == "recovery-effect-unknown"
    assert len(parts["backend"].calls) == 1
    assert parts["roadmap"].read_bytes() == before
    assert gates.parse(parts["gate_path"]).effect == "unknown"


def test_pm_h11_view_refuses_a_revoked_authority_an_exhausted_budget_or_a_changed_stop(
    tmp_path, monkeypatch
):
    from autopilot import decision_recovery

    revoked = _pm_h11_fixture(tmp_path / "revoked", monkeypatch)
    assert decision_recovery.run_pm_halted_recovery(
        revoked["root"], _H11_KEY, revoked["submission"]
    )["ok"] is True
    payload = json.loads(revoked["host"].read_text(encoding="utf-8"))
    for row in payload["projects"].values():
        row["authority_records"]["grant-h11"]["revoked"] = True
    revoked["host"].write_text(json.dumps(payload), encoding="utf-8", newline="\n")
    view = decision_recovery.read_halted_recovery_view(revoked["root"], _H11_KEY)
    assert view == {"ok": False, "reason": "authority-revoked"}

    exhausted = _pm_h11_fixture(tmp_path / "budget", monkeypatch, limit=2, rounds=1)
    exhausted_result = decision_recovery.run_pm_halted_recovery(
        exhausted["root"], _H11_KEY, exhausted["submission"]
    )
    assert exhausted_result["ok"] is True, exhausted_result
    for label in ("extra-a", "extra-b"):
        directory = exhausted["root"] / ".agenticdoc" / _H11_KEY / "workers" / label
        directory.mkdir(parents=True)
        (directory / "task.md").write_text("---\nloop: L2\n---\n", encoding="utf-8")
    view = decision_recovery.read_halted_recovery_view(exhausted["root"], _H11_KEY)
    assert view == {"ok": False, "reason": "hard-budget-exhausted"}

    changed = _pm_h11_fixture(tmp_path / "stop", monkeypatch)
    assert decision_recovery.run_pm_halted_recovery(
        changed["root"], _H11_KEY, changed["submission"]
    )["ok"] is True
    text = changed["roadmap"].read_text(encoding="utf-8")
    changed["roadmap"].write_text(
        text.replace("Ship the halted stage", "Ship a different halted stage"),
        encoding="utf-8",
    )
    view = decision_recovery.read_halted_recovery_view(changed["root"], _H11_KEY)
    assert view["ok"] is False
    assert view["reason"] in {"stop-fact-changed", "recovery-basis-changed"}
    _verify("VC-052", duplicate_effects=0, duplicate_approvals=0, concurrent_writers=0,
            lock_bypasses=0, stale_releases=0, irrelevant_reapprovals=0)


def test_pm_h11_a_breaker_only_source_is_not_an_h11_authorization(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    parts = _pm_h11_fixture(
        tmp_path, monkeypatch,
        note_overrides={"authority_ref": "grant-h12"},
    )
    before = parts["roadmap"].read_bytes()
    refused = decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, parts["submission"]
    )
    assert refused == {"ok": False, "reason": "grant-scope-mismatch"}
    assert parts["backend"].calls == []
    assert parts["roadmap"].read_bytes() == before
    _verify("VC-036", breaker_self_approvals=0, unauthorized_recoveries=0,
            transport_bypasses=0)


# ── T21 bounded step: one real dispatch round from the approved H11 note ────

_PM_H11_STEM = "bounded-round"
_PM_H11_TASK_KEY = f"ap-{_H11_KEY}-{_PM_H11_STEM}"


def _pm_h11_bounded_fixture(
    tmp_path,
    monkeypatch,
    *,
    create_card=True,
    create_task=True,
    queue_status="done",
    card_sha=None,
    **kwargs,
):
    """PM H11 fixture plus one already-existing card-backed task round.

    The card, the original task.md and the original queue row are written to
    the isolated fixture project before the recovery gate is prepared, so the
    bounded action is bound into the same note/matter the model sees. Nothing
    here starts a worker or a provider.
    """
    import mw_common
    from autopilot import dispatch as dispatch_writer

    root = tmp_path / "project"
    key_dir = root / ".agenticdoc" / _H11_KEY
    card = key_dir / "tasks" / f"{_PM_H11_STEM}.md"
    card.parent.mkdir(parents=True)
    card.write_text(
        "# Bounded round card\n\n"
        "## 要求\n\nContinue the original bounded task round.\n\n"
        "## 交付格式\n\nWrite output.md with the required sections.\n\n"
        "## 写入允许面\n\n- evidence/**\n",
        encoding="utf-8",
        newline="\n",
    )
    digest = card_sha or dispatch_writer.card_digest(card)
    target = key_dir / "workers" / _PM_H11_TASK_KEY
    if create_task:
        target.mkdir(parents=True)
        (target / "task.md").write_text(
            "---\ntype: roadmap-writer\norigin: conductor\nloop: L1\nattempt: 1\n---\n\n"
            "Run the original bounded round.\n",
            encoding="utf-8",
            newline="\n",
        )
        queue = mw_common.workers_path(root)
        queue.parent.mkdir(parents=True, exist_ok=True)
        queue.write_text(
            "# mw-queue:v2\n"
            + mw_common.serialize_entry({
                "task_key": _PM_H11_TASK_KEY,
                "status": queue_status,
                "cli": "pi",
                "provider": "default",
                "task_path": str(target / "task.md"),
                "dispatched_at": "2026-11-01T00:00:00+00:00",
                "updated_at": "2026-11-01T00:00:00+00:00",
                "model": "",
                "origin": "conductor",
            })
            + "\n",
            encoding="utf-8",
            newline="\n",
        )
    action = {
        "kind": "dispatch-round",
        "task_key": _PM_H11_TASK_KEY,
        "task_type": "roadmap-writer",
        "card_sha256": digest,
        "write_face": ["evidence/**"],
        "amount": 1,
        "end_criterion": "the one dispatched round leaves a queue row and task labels",
    }
    parts = _pm_h11_fixture(
        tmp_path, monkeypatch,
        note_overrides={"bounded_action": action},
        **kwargs,
    )
    parts.update({
        "bounded_action": action,
        "task_key": _PM_H11_TASK_KEY,
        "task_dir": target,
        "task_path": target / "task.md",
        "card_path": card,
        "queue_path": mw_common.workers_path(root),
    })
    return parts


def _bounded_queue(parts):
    import mw_common

    return mw_common.parse_workers_file(parts["queue_path"])


def _bounded_labels(parts):
    from autopilot import state as mw_state

    return mw_state.parse_task_labels(parts["task_path"])


def test_h11_bounded_step_consumes_one_real_dispatch_round(tmp_path, monkeypatch):
    from autopilot import decision_recovery, state as mw_state

    parts = _pm_h11_bounded_fixture(tmp_path, monkeypatch)
    original_queue = parts["queue_path"].read_bytes()
    result = decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, parts["submission"]
    )
    assert result["ok"] is True, result
    row = _pm_h11_rows(parts)[0]
    baseline = row["bounded_step"]
    assert baseline["task_key"] == _PM_H11_TASK_KEY
    assert baseline["card_sha256"] == parts["bounded_action"]["card_sha256"]
    assert baseline["base_attempt"] == 1
    assert baseline["base_used"] == 1
    assert parts["queue_path"].read_bytes() == original_queue

    used_before = mw_state.used_rounds([
        parts["root"] / ".agenticdoc" / _H11_KEY / "workers"])
    consumed = decision_recovery.consume_bounded_halted_step(parts["root"], _H11_KEY)
    assert consumed["ok"] is True, consumed
    assert consumed["state"] == "bounded-step-consumed"
    assert consumed["dispatched"] is True
    assert consumed["task_key"] == _PM_H11_TASK_KEY
    assert consumed["attempt"] == 2
    assert consumed["used_rounds"] == used_before["L1"] + 1
    assert consumed["decision_ref"] == row["decision_ref"]

    labels = _bounded_labels(parts)
    assert labels["loop"] == "L1" and labels["attempt"] == "2"
    assert labels["type"] == "roadmap-writer"
    queue = _bounded_queue(parts)
    assert len(queue) == 1
    assert queue[0]["task_key"] == _PM_H11_TASK_KEY
    assert queue[0]["status"] == "pending"
    assert queue[0]["origin"] == "conductor"
    assert queue[0]["task_path"] == str(parts["task_path"])
    used_after = mw_state.used_rounds([
        parts["root"] / ".agenticdoc" / _H11_KEY / "workers"])
    assert used_after["L1"] == used_before["L1"] + 1
    assert len(parts["backend"].calls) == 1  # no new model call for the step

    executed = [event for event in _lifecycle_rows(
                    decision_recovery._client_store(parts["root"])[1], "executed")
                if event.get("action") == "direct-exec"]
    assert len(executed) == 1
    assert consumed["receipt_sha256"] in json.dumps(executed[0])
    settled = [event for event in _lifecycle_rows(
                   decision_recovery._client_store(parts["root"])[1], "settled")
               if "not complete" in str(event.get("reason") or "")]
    assert len(settled) == 1

    queue_after = parts["queue_path"].read_bytes()
    task_after = parts["task_path"].read_bytes()
    replay = decision_recovery.consume_bounded_halted_step(parts["root"], _H11_KEY)
    assert replay["ok"] is True, replay
    assert replay["resumed"] is True
    assert replay["task_key"] == _PM_H11_TASK_KEY
    assert replay["attempt"] == 2
    assert parts["queue_path"].read_bytes() == queue_after
    assert parts["task_path"].read_bytes() == task_after
    assert len(_pm_h11_rows(parts)) == 1
    assert len(parts["backend"].calls) == 1
    assert "status: halted" in parts["roadmap"].read_text(encoding="utf-8")
    view = decision_recovery.read_halted_recovery_view(parts["root"], _H11_KEY)
    assert view["ok"] is True and view["stage_status"] == "halted"
    assert view["current_consumed"] == {"round": 2}
    assert view["remaining"] == {"round": 1}
    _verify("VC-034", erased_stop_facts=0, reset_usage=0, unsupported_resumes=0)
    _verify("VC-052", duplicate_effects=0, duplicate_approvals=0, concurrent_writers=0,
            lock_bypasses=0, stale_releases=0, irrelevant_reapprovals=0)
    _verify("VC-021", hard_budget_overruns=0, self_granted_limits=0, reset_usage=0)


def test_h11_bounded_step_requires_a_concrete_approved_action(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    parts = _pm_h11_fixture(tmp_path, monkeypatch)
    assert decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, parts["submission"]
    )["ok"] is True
    queue = parts["root"] / ".agenticdoc" / "_workers.parallel"
    before = queue.read_bytes() if queue.exists() else None
    refused = decision_recovery.consume_bounded_halted_step(parts["root"], _H11_KEY)
    assert refused == {"ok": False, "reason": "bounded-action-missing"}
    assert (queue.read_bytes() if queue.exists() else None) == before
    _verify("VC-034", erased_stop_facts=0, reset_usage=0, unsupported_resumes=0)


def test_h11_bounded_step_refuses_a_missing_or_changed_target_before_the_model(
    tmp_path, monkeypatch
):
    from autopilot import decision_recovery

    missing_card = _pm_h11_bounded_fixture(tmp_path / "card", monkeypatch)
    missing_card["card_path"].unlink()
    refused = decision_recovery.run_pm_halted_recovery(
        missing_card["root"], _H11_KEY, missing_card["submission"]
    )
    assert refused["ok"] is False
    assert "bounded" in refused["reason"] or "target" in refused["reason"]
    assert missing_card["backend"].calls == []

    changed_card = _pm_h11_bounded_fixture(tmp_path / "changed", monkeypatch)
    changed_card["card_path"].write_text(
        changed_card["card_path"].read_text(encoding="utf-8") + "\nchanged\n",
        encoding="utf-8",
    )
    refused = decision_recovery.run_pm_halted_recovery(
        changed_card["root"], _H11_KEY, changed_card["submission"]
    )
    assert refused["ok"] is False
    assert "bounded" in refused["reason"] or "card" in refused["reason"]
    assert changed_card["backend"].calls == []

    missing_task = _pm_h11_bounded_fixture(
        tmp_path / "task", monkeypatch, create_task=False
    )
    refused = decision_recovery.run_pm_halted_recovery(
        missing_task["root"], _H11_KEY, missing_task["submission"]
    )
    assert refused["ok"] is False
    assert "bounded" in refused["reason"] or "target" in refused["reason"]
    assert missing_task["backend"].calls == []

    in_flight = _pm_h11_bounded_fixture(tmp_path / "flight", monkeypatch,
                                        queue_status="running")
    refused = decision_recovery.run_pm_halted_recovery(
        in_flight["root"], _H11_KEY, in_flight["submission"]
    )
    assert refused["ok"] is False
    assert "bounded" in refused["reason"]
    assert in_flight["backend"].calls == []


def test_h11_bounded_step_respects_revocation_budget_and_crash_unknown(
    tmp_path, monkeypatch
):
    from autopilot import decision_recovery

    revoked = _pm_h11_bounded_fixture(tmp_path / "revoked", monkeypatch)
    assert decision_recovery.run_pm_halted_recovery(
        revoked["root"], _H11_KEY, revoked["submission"]
    )["ok"] is True
    payload = json.loads(revoked["host"].read_text(encoding="utf-8"))
    for row in payload["projects"].values():
        row["authority_records"]["grant-h11"]["revoked"] = True
    revoked["host"].write_text(json.dumps(payload), encoding="utf-8", newline="\n")
    queue_before = revoked["queue_path"].read_bytes()
    refused = decision_recovery.consume_bounded_halted_step(revoked["root"], _H11_KEY)
    assert refused == {"ok": False, "reason": "authority-revoked"}
    assert revoked["queue_path"].read_bytes() == queue_before

    exhausted = _pm_h11_bounded_fixture(tmp_path / "budget", monkeypatch)
    assert decision_recovery.run_pm_halted_recovery(
        exhausted["root"], _H11_KEY, exhausted["submission"]
    )["ok"] is True
    for label in ("extra-a", "extra-b"):
        directory = exhausted["root"] / ".agenticdoc" / _H11_KEY / "workers" / label
        directory.mkdir(parents=True)
        (directory / "task.md").write_text(
            "---\nloop: L2\nattempt: " + ("1" if label == "extra-a" else "2")
            + "\n---\n", encoding="utf-8")
    queue_before = exhausted["queue_path"].read_bytes()
    refused = decision_recovery.consume_bounded_halted_step(exhausted["root"], _H11_KEY)
    assert refused["ok"] is False and "budget" in refused["reason"]
    assert exhausted["queue_path"].read_bytes() == queue_before

    crashed = _pm_h11_bounded_fixture(tmp_path / "crash", monkeypatch)
    assert decision_recovery.run_pm_halted_recovery(
        crashed["root"], _H11_KEY, crashed["submission"]
    )["ok"] is True
    # The task.md write happened, the queue row never did: that is an unknown
    # crash window, never a reason to dispatch the round a second time.
    crashed["task_path"].write_text(
        crashed["task_path"].read_text(encoding="utf-8").replace(
            "attempt: 1", "attempt: 2"),
        encoding="utf-8",
    )
    queue_before = crashed["queue_path"].read_bytes()
    refused = decision_recovery.consume_bounded_halted_step(crashed["root"], _H11_KEY)
    assert refused["ok"] is False and refused["reason"] == "bounded-step-unknown"
    assert crashed["queue_path"].read_bytes() == queue_before
    crashed_store = decision_recovery._client_store(crashed["root"])[1]
    assert not [event for event in _lifecycle_rows(crashed_store, "executed")
                if event.get("action") == "direct-exec"]
    _verify("VC-030", unknown_state_redispatches=0, conflicting_redispatches=0,
            unbounded_recoveries=0)
    _verify("VC-021", hard_budget_overruns=0, self_granted_limits=0, reset_usage=0)


def test_h11_bounded_step_never_dispatches_from_a_non_approve_answer(tmp_path, monkeypatch):
    from autopilot import decision_recovery

    parts = _pm_h11_bounded_fixture(tmp_path, monkeypatch, choice="reject")
    before = parts["queue_path"].read_bytes()
    result = decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, parts["submission"]
    )
    assert result["ok"] is False and result["reason"] == "stage-remains-halted"
    refused = decision_recovery.consume_bounded_halted_step(parts["root"], _H11_KEY)
    assert refused == {"ok": False, "reason": "no-recorded-recovery"}
    assert parts["queue_path"].read_bytes() == before
    assert _bounded_labels(parts)["attempt"] == "1"
