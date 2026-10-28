"""Read-only re-measurement of the nine PM-reported T06 boundaries.

Same nine inputs as ``t06-pm-handoff-20261026/supplement.json`` (that file is
the *before* record and is never re-executed), plus positive controls that must
keep their old legal behaviour. Imports the actual isolated copy, writes only
``boundary-after.json`` inside this card's rework-r2 evidence directory, and
touches no network, CLI, provider, claim, lock, grant, signoff or live object.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from dataclasses import asdict, replace
from datetime import datetime, timezone

FIXTURE = pathlib.Path(__file__).resolve().parent
EVIDENCE = FIXTURE.parent
KEY_ROOT = EVIDENCE.parents[3]
PACKAGE = KEY_ROOT / "implementation-worktree" / "packages" / "multi-workers"
PM_EVIDENCE = KEY_ROOT / "evidence" / "implementation" / "t06-pm-handoff-20261026"

assert sys.dont_write_bytecode, "run with -B and PYTHONDONTWRITEBYTECODE=1"
sys.path.insert(0, str(PACKAGE))
import decision_validity as d  # noqa: E402

assert pathlib.Path(d.__file__).resolve() == PACKAGE / "decision_validity.py"


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    base = d.matter_for(
        "key-1",
        "key-1",
        "sign",
        [d.DependencyState("scope", "set", ["key-1"])],
        matter_kind="key-signoff",
        contract_version="v1",
    )
    sign = d.SignoffRef(
        "sign-1",
        "finalize",
        "key-1",
        base.matter_key,
        base.substantive_version,
        ("key-1",),
        "fixture-artifact-reference",
    )
    ev = d.evidence_for("ev-1", "verification", base, ("scope",))
    req = d.ClaimRequest("worker-1", "task-1", ("safe.py",))
    eff = d.EffectRecord(
        "eff-1", "dec-1", base.matter_key, base.substantive_version, ("act",), "unknown"
    )

    rows: list[dict[str, object]] = []

    def check(name: str, actual, expected: str, passed: bool) -> None:
        rows.append(
            {
                "name": name,
                "actual": asdict(actual),
                "expected": expected,
                "boundary_satisfied": passed,
            }
        )

    for choice in ("continue", "user-confirm"):
        verdict = d.assess_signoff(replace(sign, choice=choice), base, required_scope=("key-1",))
        check(
            f"signoff-{choice}",
            verdict,
            "not valid as required successful signoff",
            verdict.status != "valid",
        )
    for name, item in (
        ("wrong-key", replace(sign, key="other-key")),
        ("missing-ref", replace(sign, signoff_ref=None)),
    ):
        verdict = d.assess_signoff(item, base, required_scope=("key-1",))
        check(
            f"signoff-{name}",
            verdict,
            "not valid as bound signoff reference",
            verdict.status != "valid",
        )
    check(
        "evidence-contract-change",
        d.assess_evidence(ev, replace(base, contract_version="v2")),
        "not reusable without current-contract applicability proof",
        not d.assess_evidence(ev, replace(base, contract_version="v2")).reusable,
    )
    check(
        "claim-mixed-traversal",
        d.assess_claim([], replace(req, files=("safe.py", "../outside.py"))),
        "invalid requested path blocks the full requested write face",
        d.assess_claim([], replace(req, files=("safe.py", "../outside.py"))).status
        != "clear",
    )
    check(
        "claim-other-task-same-owner",
        d.assess_claim([d.Claim("worker-1", "other-task", ("safe.py",))], req),
        "task-specific overlapping active claim is not clear",
        d.assess_claim([d.Claim("worker-1", "other-task", ("safe.py",))], req).status
        != "clear",
    )
    for name, status in (("unrecognized", "unrecorded"), ("missing", None)):
        plan = d.plan_actions([replace(eff, status=status)], matter=base, actions=("act",))
        check(
            f"effect-{name}",
            plan,
            "unknown stored effect status does not permit blind retry",
            not plan.actions,
        )

    controls: list[dict[str, object]] = []

    def control(name: str, passed: bool, detail: str) -> None:
        controls.append({"name": name, "passed": passed, "detail": detail})

    finalize = d.assess_signoff(sign, base, required_scope=("key-1",))
    control(
        "signoff-finalize-valid",
        finalize.status == "valid" and finalize.reasons == (),
        f"status={finalize.status} reasons={finalize.reason_codes}",
    )
    same_contract = d.assess_evidence(ev, base)
    control(
        "evidence-same-contract-reusable",
        same_contract.status == "applies" and same_contract.reusable,
        f"status={same_contract.status} reusable={same_contract.reusable}",
    )
    byte_only = d.evidence_for(
        "ev-2", "verification", base, ("scope",), byte_sha256="e" * 64
    )
    control(
        "evidence-byte-only-reusable",
        d.assess_evidence(byte_only, base).reusable,
        "same semantics, different byte hash",
    )
    own_task_claims = [d.Claim("worker-1", "task-1", ("safe.py",))]
    reentry = d.assess_claim(own_task_claims, req)
    control(
        "claim-same-task-reentry-clear",
        reentry.status == "clear" and reentry.conflicts == (),
        f"status={reentry.status}",
    )
    no_record = d.plan_actions([], matter=base, actions=("act",))
    control(
        "effect-no-record-proceed",
        no_record.status == "proceed" and no_record.actions == ("act",),
        f"status={no_record.status}",
    )
    failed = d.plan_actions([replace(eff, status="failed")], matter=base, actions=("act",))
    control(
        "effect-failed-retry-proceed",
        failed.status == "proceed" and failed.actions == ("act",),
        f"status={failed.status}",
    )
    applied = d.plan_actions([replace(eff, status="applied")], matter=base, actions=("act",))
    control(
        "effect-applied-deduped",
        applied.status == "already-applied" and applied.actions == (),
        f"status={applied.status} duplicate={applied.duplicate_actions}",
    )
    for status in ("unknown", "in-progress"):
        plan = d.plan_actions([replace(eff, status=status)], matter=base, actions=("act",))
        control(
            f"effect-{status}-blocked",
            plan.status == "blocked" and plan.actions == (),
            f"status={plan.status}",
        )

    pm_pyc = sorted(
        sha256(path) for path in PM_EVIDENCE.joinpath("out-of-face-bytes").rglob("*.pyc")
    )
    current_pyc = sorted(
        sha256(path)
        for path in KEY_ROOT.joinpath("implementation-worktree").rglob("*.pyc")
    )

    result = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "module_file": str(PACKAGE / "decision_validity.py"),
        "module_sha256": sha256(PACKAGE / "decision_validity.py"),
        "before_record": "t06-pm-handoff-20261026/supplement.json (read-only, not re-executed)",
        "boundary_checks": rows,
        "boundary_failures": sum(not bool(row["boundary_satisfied"]) for row in rows),
        "positive_controls": controls,
        "positive_control_failures": sum(not bool(row["passed"]) for row in controls),
        "pyc_count": len(current_pyc),
        "pyc_hashes_equal_pm_record": current_pyc == pm_pyc,
        "fixture_references_not_real_authority_or_artifact_proof": True,
        "no_cli_network_provider_or_live_object": True,
    }
    (EVIDENCE / "boundary-after.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if not result["boundary_failures"] and not result["positive_control_failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
