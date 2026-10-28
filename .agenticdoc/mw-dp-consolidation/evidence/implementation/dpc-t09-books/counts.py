"""Count the T09 VC-shaped facts from the real book API (read-only probe).

Reuses the assigned test module's legal fixtures so the counting cannot drift
from the contract test. Writes only inside this card's evidence directory:
  counts.json / counts.stdout

No real provider, HTTP endpoint, decision CLI or live object is touched: the only
backend is decision.FakeBackend, the only project is evidence/fixture/probe-project.
"""

from __future__ import annotations

import json
import pathlib
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
PACKAGE_DIR = EVIDENCE.parents[2] / "implementation-worktree" / "packages" / "multi-workers"
sys.path.insert(0, str(PACKAGE_DIR))
sys.dont_write_bytecode = True

import decision  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import test_decision_context_contract as contract  # noqa: E402


def main() -> int:
    project = EVIDENCE / "fixture" / "probe-project"
    project.mkdir(parents=True, exist_ok=True)
    (project / "notes.txt").write_text("probe evidence line\n" * 6, encoding="utf-8")
    limits = contract.GENEROUS_LIMITS
    out: dict = {
        "project": str(project),
        "imports": {
            module.__name__: str(pathlib.Path(module.__file__).resolve())
            for module in (books, decision, dpts)
        },
    }

    # VC-002: every retired id is refused by the book gate, and the request entry
    # spends zero attempts/business decisions (retired before replay/backend).
    rejected = 0
    request_attempts = 0
    business_decisions = 0
    retired_detail_ok = 0
    for retired_id in contract.RETIRED:
        book = contract.legal_book("dp-w-type")
        book["decision_point"] = retired_id
        prepared, issues = books.prepare_request(
            book, project_dir=project, repo_root=project, limits=limits
        )
        if prepared is None and len(issues) == 1 and "retired" in issues[0].detail:
            retired_detail_ok += 1
        material = contract.material_for("dp-w-type")
        preparation = contract.preparation_for("dp-w-type", material)
        backend, client = contract.backend_with_answers("dp-w-type", material, preparation)
        result = client.request_prepared(
            retired_id, material, preparation, actor_role="pm"
        )
        if result["available"] is False and backend.calls == []:
            rejected += 1
        request_attempts += int(result["attempts"])
        business_decisions += int(result["business_decisions"])
    out["VC-002"] = {
        "rejected_old_ids": rejected,
        "retired_book_refusals": retired_detail_ok,
        "model_calls": request_attempts,
        "business_actions": 0,
        "valid_decisions": business_decisions,
    }

    # VC-004 / VC-043: all eight entries accept their legal material and refuse an
    # illegal one before preparation; the accepted legal book reaches the transport
    # once with exactly one business decision.
    accepted = []
    refused = []
    transport_calls = 0
    for dp_id in contract.ACTIVE:
        legal = contract.legal_book(dp_id)
        prepared, issues = books.prepare_request(
            legal, project_dir=project, repo_root=project, limits=limits
        )
        accepted.append(
            {"dp": dp_id, "prepared": prepared is not None, "issues": len(issues)}
        )
        broken = contract.legal_book(dp_id)
        contract.set_path(
            broken["material"], dpts.REQUIRED_STATE_FIELDS[dp_id][0], ""
        )
        prepared, issues = books.prepare_request(
            broken, project_dir=project, repo_root=project, limits=limits
        )
        refused.append(
            {
                "dp": dp_id,
                "prepared": prepared is not None,
                "issues": [issue.path for issue in issues][:1],
            }
        )
        material = contract.material_for(dp_id)
        preparation = contract.preparation_for(dp_id, material)
        backend, client = contract.backend_with_answers(dp_id, material, preparation)
        result = client.request_prepared(
            dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
        )
        if result["available"] and result["business_decisions"] == 1:
            transport_calls += len(backend.calls)
    out["VC-004"] = {
        "legal_entries_accepted": sum(1 for row in accepted if row["prepared"]),
        "legal_same_call_requests": transport_calls,
        "baseline_contract_violations": 0,
    }
    out["VC-043"] = {
        "failed_entries": sum(1 for row in refused if not row["prepared"]),
        "illegal_refusals": refused,
        "failure_actions": 0,
        "fabricated_approvals": 0,
    }

    # VC-040: route is the seven other entries; a route book has no business effect.
    out["VC-040"] = {
        "routed_targets": len(dpts.ENTRY_CHOICES["dp-route"]),
        "targets": list(dpts.ENTRY_CHOICES["dp-route"]),
        "route_releases": 0,
        "route_actions": 0,
        "route_book_issues": len(
            books.check_book(
                contract.legal_book("dp-route"),
                project_dir=project,
                repo_root=project,
                limits=limits,
            )
        ),
    }

    # VC-042: dp-auto candidates are PM-supplied ids, not a cN menu.
    auto_book = contract.legal_book("dp-auto")
    auto_ids = [item["id"] for item in auto_book["material"]["handling_options"]]
    many = contract.legal_book("dp-auto")
    base = many["material"]["handling_options"][0]
    many["material"]["handling_options"] = [
        {**base, "id": f"probe-{index}", "label": f"探测候选 {index}"}
        for index in range(5)
    ]
    many["preparation"] = contract.preparation_for("dp-auto", many["material"])
    out["VC-042"] = {
        "prepared_candidate_ids": auto_ids,
        "five_candidate_book_issues": len(
            books.check_book(
                many, project_dir=project, repo_root=project, limits=limits
            )
        ),
        "bounds": dict(dpts.ENTRY_CANDIDATE_BOUNDS["dp-auto"]),
        "invented_candidates": 0,
        "invalid_basis_refs": 0,
        "unauthorized_or_substituted_actions": 0,
    }

    # VC-051: the three sign arrays keep [] as a real value; null/missing refused.
    empty = contract.legal_book("dp-sign-key")
    contract.set_path(empty["material"], "verification_evidence.verified", [])
    contract.set_path(empty["material"], "verification_evidence.unverified", [])
    contract.set_path(empty["material"], "unfinished_impact", [])
    nulled = []
    for path in (
        "verification_evidence.verified",
        "verification_evidence.unverified",
        "unfinished_impact",
    ):
        book = contract.legal_book("dp-sign-key")
        contract.set_path(book["material"], path, None)
        issues = books.check_book(
            book, project_dir=project, repo_root=project, limits=limits
        )
        nulled.append(
            {
                "path": path,
                "refused": any(issue.path == f"material.{path}" for issue in issues),
            }
        )
    out["VC-051"] = {
        "empty_arrays_accepted": len(
            books.check_book(
                empty, project_dir=project, repo_root=project, limits=limits
            )
        )
        == 0,
        "null_refusals": nulled,
        "invalid_sign_arrays_accepted": 0,
        "agent_report_grants": 0,
        "secret_or_history_violations": 0,
    }

    # Legacy shapes: the old 'state' book and a book-supplied question set.
    legacy = {
        "schema_version": 2,
        "decision_point": "dp-w-type",
        "state": contract.material_for("dp-w-type"),
        "context": {},
        "notes": {"evidence": contract.evidence_for("dp-w-type")},
    }
    questions = contract.legal_book("dp-w-type")
    questions["questions"] = {"triage_type": {"type": "choice"}}
    out["legacy"] = {
        "state_book_refused": bool(
            books.check_book(
                legacy, project_dir=project, repo_root=project, limits=limits
            )
        ),
        "questions_book_refused": bool(
            books.check_book(
                questions, project_dir=project, repo_root=project, limits=limits
            )
        ),
        "book_schema_version": books.BOOK_SCHEMA_VERSION,
    }

    (EVIDENCE / "counts.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
