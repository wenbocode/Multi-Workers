"""R2 negative-control probe over the current product (read-only, own fixtures).

Replays the PM handoff's seven bypass reproductions plus the supplement's
revoked-rule-reference bypass against the current decision_policy.py, and keeps
the two legal controls (non-empty scope + fresh human H11 lift). Every record is
an in-memory fixture; nothing here is a production grant.

Run with -B / PYTHONDONTWRITEBYTECODE=1. Network is denied.
"""

from __future__ import annotations

import json
import pathlib
import socket
import sys

HERE = pathlib.Path(__file__).resolve().parent
KEY = HERE.parents[3]
PKG = KEY / "implementation-worktree" / "packages" / "multi-workers"
sys.path.insert(0, str(PKG))


def deny(*args, **kwargs):
    raise AssertionError("negative-control probe denies network")


socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny

import decision_policy as p  # noqa: E402

assert pathlib.Path(p.__file__).resolve() == PKG / "decision_policy.py", p.__file__

WRITER = "fixture-controlled-writer"
TRUSTED = (WRITER,)


def record(ref, scope, *, kind="user-grant", revoked=False, supersedes=()):
    result, issues = p.parse_authority_record(
        {
            "authority_ref": ref,
            "kind": kind,
            "scope": list(scope),
            "writer": WRITER,
            "revoked": revoked,
            "recorded_at": "2026-10-26T00:00:00Z",
            "supersedes": list(supersedes),
        },
        trusted_writers=TRUSTED,
    )
    assert result is not None and not issues, (ref, [i.text() for i in issues])
    return result


RAW = {
    "schema_version": 1,
    "authority_ref": "main",
    "scope": ["key:allowed"],
    "hard_limits": [{"unit": "round", "limit": 2, "usage_source": "fixture-cumulative"}],
    "recovery": {
        "allowed_origins": ["pm-controlled"],
        "scope": ["recovery:halted", "recovery:breaker"],
        "authority_ref": "rule-ref",
        "observation_conditions": ["quiet"],
        "stop_conditions": ["repeat"],
    },
}
load = p.parse_policy(RAW)
assert load.usable

source = {
    "main": record("main", ["key:allowed", "key:outside"]),
    "rule-ref": record("rule-ref", ["recovery:halted", "recovery:breaker"]),
    "other-ref": record("other-ref", ["recovery:halted", "recovery:breaker"]),
}
revoked_source = dict(source, **{"rule-ref": record("rule-ref", ["recovery:halted", "recovery:breaker"], revoked=True)})
human_lift_source = dict(
    source,
    **{"human-lift": record("human-lift", ["recovery:user-stop", "recovery:halted"])},
)

rows = []


def observe(name, kind, request, verdict, expect_allowed):
    rows.append(
        {
            "name": name,
            "surface": kind,
            "changed_input": request,
            "expected_allowed": expect_allowed,
            "allowed": verdict.allowed,
            "scope": list(getattr(verdict, "scope", getattr(verdict, "resume_scope", ()))),
            "reasons": [issue.text() for issue in verdict.reasons],
            "questions": list(getattr(verdict, "questions", ())),
            "verdict_ok": verdict.allowed is expect_allowed,
        }
    )


base = {
    "pending_review": True,
    "goal_effective": True,
    "blocker_cleared": True,
    "evidence": ["fixture-evidence"],
    "choice": "approve",
    "budget_unit": "round",
    "budget_amount": 1,
}
for name, scope, expected in (
    ("pending-control", ["key:allowed"], True),
    ("pending-outside-policy", ["key:outside"], False),
    ("pending-missing-scope", None, False),
):
    state = dict(base)
    if scope is None:
        state.pop("required_scope", None)
    else:
        state["required_scope"] = scope
    observe(
        name,
        "pending-review",
        scope,
        p.evaluate_pending_review(
            load,
            trigger={"kind": "new-evidence"},
            state=state,
            usage={"round": 0},
            authority_source=source,
            trusted_writers=TRUSTED,
        ),
        expected,
    )

halted = {
    "stage_halted": True,
    "halt_origin": "technical",
    "hard_guard_active": False,
    "choice": "approve",
    "required_scope": ["recovery:halted"],
    "note": {
        "stop_reason": "fixture-stop",
        "elimination_evidence": ["fixture-clear"],
        "stage_version": "v1",
        "affected_keys": ["fixture-key"],
        "target_plan": "bounded-fixture-action",
        "authority_ref": "rule-ref",
        "residual_budget": {"round": 1},
        "stop_criterion": "repeat",
    },
}


def halted_call(request, authority=source):
    return p.evaluate_halted_recovery(
        load,
        request=request,
        usage={"round": 1},
        authority_source=authority,
        trusted_writers=TRUSTED,
    )


observe("halted-control", "halted-recovery", None, halted_call(dict(halted)), True)
unverified_guard = dict(halted, hard_guard_active=True, hard_guard_cleared=["self-reported-clear"])
observe("halted-unverified-guard", "halted-recovery", "self-reported-clear", halted_call(unverified_guard), False)
unknown_origin = dict(halted)
unknown_origin.pop("halt_origin")
observe("halted-unknown-origin", "halted-recovery", "halt_origin removed", halted_call(unknown_origin), False)
unrelated = json.loads(json.dumps(halted))
unrelated["note"]["authority_ref"] = "other-ref"
observe("halted-unrelated-authority", "halted-recovery", "other-ref", halted_call(unrelated), False)
revoked_rule = json.loads(json.dumps(halted))
revoked_rule["note"]["authority_ref"] = "other-ref"
observe(
    "halted-revoked-policy-ref-bypass",
    "halted-recovery",
    "rule-ref revoked + other-ref",
    halted_call(revoked_rule, revoked_source),
    False,
)
human_lift = json.loads(json.dumps(halted))
human_lift["halt_origin"] = "user-stop"
human_lift["note"]["authority_ref"] = "human-lift"
observe(
    "halted-h11-fresh-human-lift",
    "halted-recovery",
    "human-lift (recovery:user-stop)",
    halted_call(human_lift, human_lift_source),
    True,
)

breaker = {
    "channel": "fixture-isolated",
    "tripped_chain": "auto-pass",
    "origin": "pm-controlled",
    "reason_elimination_evidence": ["fixture-clear"],
    "preauthorization_ref": "rule-ref",
    "machine_checks": {"fixture-check": True},
    "transport_available": True,
    "user_disabled": False,
    "required_scope": ["recovery:breaker"],
    "choice": "approve",
}


def breaker_call(request, authority=source):
    return p.evaluate_breaker_recovery(
        load,
        request=request,
        authority_source=authority,
        trusted_writers=TRUSTED,
        controlled_channels=("fixture-isolated",),
    )


observe("breaker-control", "breaker-recovery", None, breaker_call(dict(breaker)), True)
other_preauth = dict(breaker, preauthorization_ref="other-ref")
observe("breaker-unrelated-preauthorization", "breaker-recovery", "other-ref", breaker_call(other_preauth), False)
unknown_disable = dict(breaker)
unknown_disable.pop("user_disabled")
observe("breaker-unknown-disable", "breaker-recovery", "user_disabled removed", breaker_call(unknown_disable), False)
# supplement minimal repro: policy rule reference revoked, request points elsewhere
supplement_request = {
    "channel": "fixture-isolated",
    "tripped_chain": "auto-pass",
    "origin": "pm-controlled",
    "reason_elimination_evidence": ["fixture-clear"],
    "preauthorization_ref": "other-ref",
    "machine_checks": {"fixture-check": True},
    "transport_available": True,
    "user_disabled": False,
    "required_scope": ["recovery:breaker"],
    "choice": "approve",
}
observe(
    "breaker-revoked-policy-ref-bypass",
    "breaker-recovery",
    "rule-ref revoked + other-ref",
    breaker_call(supplement_request, revoked_source),
    False,
)

failures = [row for row in rows if not row["verdict_ok"]]
result = {
    "policy_file": str(pathlib.Path(p.__file__).resolve()),
    "fixture_authority_in_memory_not_production": True,
    "rows": rows,
    "failed_expectations": [row["name"] for row in failures],
    "failclosed_bypasses": sum(
        int(row["allowed"]) for row in rows if row["expected_allowed"] is False
    ),
    "legal_controls_granted": sum(
        int(row["allowed"]) for row in rows if row["expected_allowed"] is True
    ),
}
(HERE / "negative-control.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
print(json.dumps(result, indent=2, ensure_ascii=False))
raise SystemExit(1 if failures else 0)
