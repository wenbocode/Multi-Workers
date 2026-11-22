"""Current DP endpoints, with offline wire replies and actual local effects."""

from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess
import sys
from io import BytesIO

import pytest

PACKAGE = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PACKAGE))

import decision
import decide_archive
import decision_backends
import decision_points
import decision_signoff_result
import decision_wire
import mw_common
import test_dp_consolidation_cli as cli
import test_dp_consolidation_gate_effects as gate_fixtures
from autopilot import conductor, contract_guard, dispatch
from test_autopilot_conductor_exec import _set_index_phase_file, _state
from test_dp_consolidation_cli import _all_entries_enabled
from test_prepared_cli_source_snapshot import isolated_credentials


FIXTURES = pathlib.Path(__file__).parent / "fixtures"
REFERENCES = PACKAGE.parents[1] / ".agenticdoc" / "mw-dp-material-pipeline" / "docs" / "reference-records"
KEY = "key-1"


def save_json(path: pathlib.Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def lifecycle(project, monkeypatch, envelope, decision_id, stage, *, worker_task=None, **fields):
    payload = {
        "meta": envelope["meta"], "decision_id": decision_id,
        "dp": decision_id.split(":", 1)[0], "stage": stage, **fields,
    }
    rc, out, err = cli._invoke(
        "lifecycle", project, monkeypatch, stdin=json.dumps(payload), stdin_flag=True,
        worker_task=worker_task,
    )
    assert rc == 0, (out, err)
    result = json.loads(out)
    assert result["recorded"] and result["event_id"]
    return result


def reply_with(monkeypatch, wire_id):
    calls = []

    def reply(request, *, timeout):
        assert request.method == "POST" and timeout > 0
        [question] = json.loads(request.data)["questions"].values()
        assert wire_id in question["criteria"]
        raw = json.dumps({"id": f"offline-{wire_id}", "model": "jev-latest", "answers": {
            "decision_selection": {"type": "choice", "choice": wire_id, "confidence": 0.92},
        }}).encode()
        calls.append((request.data, raw))
        response = BytesIO(raw)
        response.status = 200
        response.headers = {"Content-Type": "application/json"}
        return response

    monkeypatch.setattr(decision_backends.urllib.request, "urlopen", reply)
    return calls


def verify_context(body, desc):
    state = json.loads(body)["state"]
    assert state["desc"] == desc
    assert isinstance(state["terminology"], dict) and "preparation" not in state
    assert "field_trace" not in state and "pair_map" not in state
    assert state["enum_meanings"]
    return state


def reference_state(case):
    return json.loads((REFERENCES / case / "model-input.json").read_bytes())["state"]


def add_reference_sources(project, case, context, *, include_findings=False):
    state = reference_state(case)
    context["enum_meanings"] = state["enum_meanings"]
    context["terminology"] = {
        name: f"{row['full_name']}: {row['meaning']}" for name, row in state["terminology"].items()
    }
    references = {}
    for name, row in state["references"].items():
        if name.startswith(("AC-", "VC-")) or row["kind"] == "review_finding" and not include_findings:
            continue
        # Extract only the authorized sample row, with its origin left in the book.
        path = project / f"v05-reference-{name}.txt"
        path.write_text(row["content"] + "\n", encoding="utf-8")
        references[name] = {"kind": row["kind"], "path": path.name, "lines": {"start": 1, "end": 1}}
    if references:
        context["references"] = references


def use_reference_catalog(env, dp, case, material_ref):
    chain = json.loads((REFERENCES / case / "reference-chain.json").read_bytes())
    catalog = []
    choices = decision_points.resolve_entry_choices(dp, env["material"])
    context = env["preparation"]["model_context"]
    for pair in chain["pair_map"]:
        if pair["choice"] not in choices:
            continue
        catalog.append({
            "id": pair["basis_id"], "text": pair["criterion"], "applies_to": [pair["choice"]],
            "material_refs": [material_ref], "finding_ids": pair["finding_ids"], "remaining_ids": pair["remaining_ids"],
        })
        for name in [*pair["finding_ids"], *pair["remaining_ids"]]:
            context.setdefault("reasons", {})[name] = chain["model_input"]["state"]["references"][name]["content"]
    env["preparation"]["basis_catalog"] = catalog


PM_DIRECTIONS = {
    "dp-w-type": "Adopt coding for the export repair and CSV round-trip checks for commas and quotes. "
                 "Keep the format protocol and write scope. Verify model, permission and budget before drafting dispatch. No worker started.",
    "dp-pm-steer": "Adopt split as a planning direction. W1 and W2 are unfinished and write distinct tests with a shared interface. "
                   "18 plus 18 worker minutes leaves 14 of 50 before independent review. Recheck review cost, roles and scope before preparing the two cards. No dispatch.",
    "dp-w-check-task": "Accept the assigned worker's bounded investigation. Permit one encoding-note read, at most 1024 bytes and within the original 8 minutes. "
                       "Report the observed encoding, retain the non-ASCII check as unfinished and stop on the original boundary.",
    "dp-route": "Prepare QG for this deliverable with its current criteria and independent review source. "
                "The chosen target still requires its own role, material and original budget checks. No QG request or verdict.",
    "dp-auto-optimized": "Accept the bounded retry direction. The 300 seconds are the preparation-time allowance. "
                         "Check authority, cancellation and the current remaining budget before one 60-second retry. Only on failure and with 120 seconds plus 30 reserved may a health read follow. No retry or health request ran.",
}


@pytest.mark.parametrize(("case", "dp", "choice"), [
    ("dp-w-type", "dp-w-type", "coding"), ("dp-pm-steer", "dp-pm-steer", "split"),
    ("dp-w-check-task", "dp-w-check-task", "investigate"), ("dp-auto-optimized", "dp-auto", "retry"),
    ("dp-auto-original", "dp-auto", "retry"), ("dp-route", "dp-route", "dp-QG"),
])
def test_current_decision_consumers_write_same_request_receipts(case, dp, choice, tmp_path, monkeypatch, isolated_credentials):
    worker_task = cli._worker_task_path(tmp_path) if dp == "dp-w-check-task" else None
    env = cli._envelope(dp, "current-receipt-1", task_key="task-1" if worker_task else None)
    material = env["material"]
    desc = {
        "dp-w-type": ["Ship the decision entry, registry and tests.", "The task does not require images."],
        "dp-pm-steer": ["Keep the original convergence goal.", "The PM reports tight budget under the current scope."],
        "dp-w-check-task": ["Complete the test within the current task budget.", "The files were read and the test is still unwritten.",
                             "One evidence read can identify the input encoding."],
        "dp-auto": ["Obtain a trustworthy read-only result.", "The first attempt did not answer the question.",
                    "Current evidence leaves a choice between two bounded diagnostic paths."],
        "dp-route": ["Identify the DP that handles the current temporary question.", "The PM has not yet chosen an entry."],
    }[dp]
    if dp == "dp-w-type":
        material.update(task_goal="Repair the CSV export so special characters round-trip unchanged.",
                        task_requirements="Touch the exporter and its tests only. Preserve the format protocol.",
                        task_deliverables="Exporter escape fix and regression assertions for commas and double quotes.")
        desc = ["Repair CSV export round trips for special characters.", "Deliver an escape fix and regression tests without changing the format."]
    if dp == "dp-pm-steer":
        material.update(task_goal="Cover two independent rejection cases without side effects.",
                        task_deliverables="W1 unauthorized request regression and W2 stale version conflict regression.",
                        pm_decision_background="Both remain unfinished. They target different test files with a shared interface and no ordering dependency. 18 worker minutes each, 50 remaining and independent review additional.")
        desc = ["Cover both negative cases.", "The remaining cases are independent and each is estimated at 18 minutes.",
                "There are 50 worker minutes left and independent review is additional."]
    if dp == "dp-w-check-task":
        (tmp_path / "encoding-note.txt").write_text("UTF-8 is required for this isolated input.\n", encoding="utf-8")
        material.update(task_goal="Verify non-ASCII fields against the actual encoding contract.",
                        completed="ASCII parsing passed in the reference fixture.", remaining="Non-ASCII validation.",
                        blockers="Input encoding not yet established.", constraints="One read, at most 1024 bytes and within the original 8 minutes.")
        material["investigation"] = {
            "unknown": "which input encoding the test uses", "evidence_source": "encoding-note.txt:1",
            "budget": "one read, 1024 bytes and 8 minutes remaining", "stop_condition": "stop after the read or at the original host boundary",
        }
        desc = ["ASCII parsing passed in the reference fixture.", "The worker still needs to verify non-ASCII fields.",
                "A single authorized read can establish the encoding within the original budget."]
    if dp == "dp-route":
        material.update(decision_object="the current deliverable and its accepted quality standards",
                        question="Which entry judges whether this deliverable satisfies accepted quality standards?")
    if case == "dp-auto-optimized":
        (tmp_path / "timeout.txt").write_text("One request connected, timed out awaiting the body, and produced no current status.\n", encoding="utf-8")
        material["question"] = "Retry the status request first or read the service health snapshot first?"
        material["background"] = {
            "task_goal": "Prefer the first verified current status within the original read-only allowance. Diagnosis is secondary.",
            "current_state": "No current status or proof of unavailability.",
            "tried": "One read-only request, as recorded in timeout.txt:1.",
            "unknowns": "Actual health snapshot sampling time, scope applicability, and outcome of a retry.",
            "constraints": "300 seconds remaining at preparation time, reserve 30 for the report, one retry and one health read.",
        }
        material["handling_options"] = [
            {"id": "retry", "label": "Retry the status request once", "description": "Read current status within 60 seconds.",
             "consequence": "A valid status completes the goal.", "risk": "The request can time out again.",
             "conditions": "Read-only scope, original allowance, and reserve for the report."},
            {"id": "diagnose", "label": "Read the health snapshot first", "description": "Read the service health snapshot within 120 seconds.",
             "consequence": "A fresh applicable offline result supports a blocker.", "risk": "Service evidence may be stale or not apply.",
             "conditions": "Check time and applicability before relying on the result."},
        ]
        desc = ["Get current read-only status before diagnosing the cause.", "The first request connected but timed out awaiting its body.",
                "There is no evidence of service outage or of snapshot freshness.",
                "Keep the original 300-second allowance and reserve 30 seconds to report."]
        env["preparation"] = cli._preparation(dp, material)
    elif case == "dp-auto-original":
        material["question"] = "After the first read-only timeout, retry once or read the health snapshot first?"
        material["background"] = {
            "task_goal": "Get a trustworthy read-only status or a definite failure within five minutes.",
            "current_state": "First request timed out; service availability is unknown.",
            "tried": "One read-only request.",
            "unknowns": "No preference between latency and diagnosis has been provided.",
            "constraints": "Read-only, one retry, existing five minutes; no renewed budget.",
        }
        material["handling_options"] = [
            {"id": "retry", "label": "Retry once", "description": "Repeat the read-only request once",
             "consequence": "Possibly receive current data", "risk": "Another timeout", "conditions": "Read-only"},
            {"id": "diagnose", "label": "Read the health snapshot", "description": "Use the authorized health snapshot first",
             "consequence": "Obtain diagnostic facts", "risk": "Data may be stale", "conditions": "Read-only"},
        ]
        env["preparation"] = cli._preparation(dp, material)
        desc = ["Get a trustworthy result or a definite failure in five minutes.", "The first request timed out.",
                "No preference between response time and diagnosis is available."]
    context = env["preparation"]["model_context"] = {"desc": desc}
    add_reference_sources(tmp_path, case, context)
    use_reference_catalog(env, dp, case, {
        "dp-w-type": "task_deliverables", "dp-pm-steer": "pm_decision_background",
        "dp-w-check-task": "remaining", "dp-auto": "background.constraints", "dp-route": "question",
    }[dp])
    if case == "dp-auto-optimized":
        context["auto_comparison"] = {
            "priority": {"source": "background.task_goal", "rule": "Obtain current status first within the original read-only allowance."},
            "budget": {"remaining_seconds": 300, "reserve_seconds": 30},
            "paths": {
                "retry": {"max_seconds": 180, "observation": "One 60-second retry for the current status.",
                          "stop": "Stop on a valid status, lost scope, cancellation, or exhausted allowance.",
                          "successor": "On failure, read health once only if 120 seconds plus the 30-second reserve remain.",
                          "steps": [
                              {"id": "status", "max_seconds": 60, "on_success": None, "on_failure": "health"},
                              {"id": "health", "max_seconds": 120, "on_success": None, "on_failure": None},
                          ]},
                "diagnose": {"max_seconds": 180, "observation": "One 120-second read of the service snapshot.",
                             "stop": "Stop on current applicable proof of outage, lost scope, cancellation, or exhausted allowance.",
                             "successor": "If inconclusive, retry status once only if 60 seconds plus the 30-second reserve remain.",
                             "steps": [
                                 {"id": "health", "max_seconds": 120, "on_success": None, "on_failure": "status"},
                                 {"id": "status", "max_seconds": 60, "on_success": None, "on_failure": None},
                             ]},
            },
            "pairs": [{"candidates": ["retry", "diagnose"], "criterion": "The retry can give current interface status directly.",
                       "reversal": "An applicable, fresh outage observation makes an immediate retry unnecessary."}],
        }
    book = tmp_path / "decision-book.json"
    save_json(book, env)
    option = next(wire_id for wire_id, pair in decision_backends.prepared_selection_options(dp, material, env["preparation"]).items()
                  if pair["choice"] == choice)
    calls = reply_with(monkeypatch, option)
    rc, out, err = cli._invoke("run", tmp_path, monkeypatch, stdin=json.dumps(env), stdin_flag=True, dp=dp, worker_task=worker_task)
    if case == "dp-auto-original":
        result = json.loads(out)
        assert rc == 2 and result["reason"] == "input-incomplete" and result["transport_attempts"] == 0
        assert result["business_decisions"] == 0 and not calls
        assert any(issue["field"] == "preparation.model_context.auto_comparison" for issue in result["issues"])
        events = decision_wire.read_events(decision_wire.production_wire_sink(tmp_path)).events
        assert not any(row["kind"] in ("attempt-start", "attempt-end") for row in events)
        assert not any(row.get("lifecycle") in ("consumed", "executed") for row in cli._lifecycle_events(tmp_path))
        save_json(tmp_path / "pipeline-evidence.json", {
            "case_id": case, "dp": dp, "preflight": result, "receipts": {},
            "pm_reason": "Return to preparation. The original case has two legal paths and no goal preference. "
                         "Clarify priority, timeout stage, source freshness, the hard stop and successors in the original allowance. No retry or renewed budget.",
        })
        return
    assert rc == 0, (out, err)
    result = json.loads(out)
    assert result["available"] and result["choice"] == choice and len(calls) == 1, result
    assert result["desc_measurement"]["exact_count"] is None
    assert result["desc_measurement"]["exact_limit_passed"] is None
    state = verify_context(calls[0][0], desc)
    if case == "dp-auto-optimized":
        assert state["path_comparison"] == context["auto_comparison"]
    if dp == "dp-route":
        assert state["terminology"]["DP"].casefold().startswith("decision point")
    did = result["decision_id"]
    consumed = lifecycle(tmp_path, monkeypatch, env, did, "consumed", worker_task=worker_task, answer=choice)
    observed = None
    if dp == "dp-w-check-task":
        with (tmp_path / "encoding-note.txt").open("rb") as source:
            observed = source.read(1024).decode("utf-8").splitlines()[0]
        assert observed
    elif dp == "dp-route":
        assert decision_points.get_decision_point(choice).id == choice
        observed = f"Selected registry target {choice}; target invocation has its own authority check."
    elif dp == "dp-w-type":
        observed = f"Read the selected worker type {result['answers']['triage_type']['value']}."
    note = PM_DIRECTIONS[case]
    outcome = "pending"
    if observed:
        lifecycle(tmp_path, monkeypatch, env, did, "executed", worker_task=worker_task,
                  action="type-read" if dp == "dp-w-type" else "record", result=observed)
    settled = lifecycle(tmp_path, monkeypatch, env, did, "settled", worker_task=worker_task,
                        event_id=f"settlement-{dp}", outcome=outcome, reason=note)
    rows = cli._lifecycle_events(tmp_path)
    assert all(row["decision_id"] == did for row in rows)
    observed_rows = [row for row in rows if row.get("lifecycle") == "executed"]
    assert [row["result"] for row in observed_rows] == ([observed] if observed else [])
    wire = decision_wire.read_events(decision_wire.production_wire_sink(tmp_path)).events
    [request] = [row for row in wire if row["kind"] == "attempt-start"]
    [response] = [row for row in wire if row["kind"] == "attempt-end"]
    assert request["decision_id"] == response["decision_id"] == did
    assert request["call_id"] == response["call_id"] == result["call_id"]
    assert calls[0] == (request["request"]["text"].encode(), response["response"]["text"].encode())
    save_json(tmp_path / "pipeline-evidence.json", {
        "case_id": case, "dp": dp, "decision_id": did, "call_id": result["call_id"], "writer": "mw decide lifecycle",
        "normalized": {key: result[key] for key in ("choice", "basis_id", "finding_ids", "remaining_ids")},
        "desc_measurement": result["desc_measurement"],
        "choice": choice, "basis_id": result["basis_id"], "observed": observed, "pm_reason": note,
        "consumer_role": env["meta"]["initiator_role"],
        "receipts": {"consumed": consumed["event_id"], "settled": settled["event_id"]},
    })


def test_qg_incomplete_historical_menu_refuses_before_transport(tmp_path, monkeypatch, isolated_credentials):
    env = cli._envelope("dp-QG", "missing-reopen-v05-shape", task_key=None)
    for item in env["preparation"]["basis_catalog"]:
        item["applies_to"] = [choice for choice in item["applies_to"] if choice != "reopen"] or ["fix"]
    calls = reply_with(monkeypatch, "fixB")
    _rc, out, _err = cli._invoke("run", tmp_path, monkeypatch, stdin=json.dumps(env), stdin_flag=True, dp="dp-QG")
    refusal = json.loads(out)
    assert refusal["reason"] == "input-incomplete" and refusal["transport_attempts"] == 0
    assert "missing prepared criteria for reopen" in json.dumps(refusal["issues"]) and calls == []
    save_json(tmp_path / "historical-menu-negative.json", {"book": env, "refusal": refusal})


@pytest.mark.parametrize(("context", "issue_suffix"), [
    ({"desc": ["One. Two. Three. Four. Five. Six. Seven. Eight. Nine. Ten. Eleven."]}, ".desc"),
    ({"desc": ["界" * 1001]}, ".desc"),
    ({"desc": ["The XYZ protocol has no definition."]}, ".terminology.XYZ"),
])
def test_invalid_authored_context_refuses_before_transport(context, issue_suffix, tmp_path, monkeypatch, isolated_credentials):
    env = cli._envelope("dp-w-type", "context-refusal", task_key=None)
    env["preparation"]["model_context"] = context
    calls = reply_with(monkeypatch, "codingA")
    _rc, out, _err = cli._invoke("run", tmp_path, monkeypatch, stdin=json.dumps(env), stdin_flag=True, dp="dp-w-type")
    result = json.loads(out)
    assert result["reason"] == "input-incomplete" and result["transport_attempts"] == 0 and not calls
    assert any(item["field"].endswith(issue_suffix) for item in result["issues"])


@pytest.mark.parametrize(("case", "dp", "field"), [
    ("single-choice", "dp-w-type", "basis_catalog"),
    ("undefined-term", "dp-w-type", "preparation.model_context.terminology.XRAY"),
    ("over-budget", "dp-auto", "preparation.model_context.auto_comparison.paths.patch-now.max_seconds"),
    ("raised-budget", "dp-auto", "preparation.model_context.auto_comparison.budget.remaining_seconds"),
    ("fractional-budget", "dp-auto", "preparation.model_context.auto_comparison.budget.remaining_seconds"),
    ("cyclic-step", "dp-auto", "preparation.model_context.auto_comparison.paths.patch-now.steps"),
])
def test_t09_preflight_refuses_before_transport(case, dp, field, tmp_path, monkeypatch, isolated_credentials):
    env = cli._envelope(dp, f"t09-{case}", task_key=None)
    if case == "single-choice":
        env["preparation"]["basis_catalog"] = [dict(env["preparation"]["basis_catalog"][0], applies_to=["coding"])]
    elif case == "undefined-term":
        env["material"]["task_goal"] = "用XRAY检查当前输出"
    else:
        comparison = env["preparation"]["model_context"]["auto_comparison"]
        path = comparison["paths"]["patch-now"]
        if case == "over-budget":
            path["max_seconds"] = 3600
        elif case == "raised-budget":
            comparison["budget"]["remaining_seconds"] = 3600
        elif case == "fractional-budget":
            env["material"]["background"]["constraints"] = "0.5 minutes remaining"
        else:
            path["steps"][0]["on_failure"] = "patch-now"
    calls = reply_with(monkeypatch, "unused")
    _rc, out, _err = cli._invoke("run", tmp_path, monkeypatch, stdin=json.dumps(env), stdin_flag=True, dp=dp)
    result = json.loads(out)
    assert result["reason"] == "input-incomplete" and result["transport_attempts"] == 0 and not calls
    assert any(item["field"] == field for item in result["issues"]), result


def test_quality_reference_without_current_criterion_does_not_send(tmp_path, monkeypatch, isolated_credentials):
    env = cli._envelope("dp-QG", "missing-current-criterion", task_key=None)
    for item in env["preparation"]["basis_catalog"]:
        if "fix" in item["applies_to"]:
            item["finding_ids"] = ["F1"]
    env["preparation"]["model_context"] = {
        "desc": ["Quality review found one problem."],
        "review": {"VC-987": {"status": "unverified", "evidence": "Source check is missing."}},
        "reasons": {"F1": "The current criterion is missing."},
    }
    calls = reply_with(monkeypatch, "fixA")
    _rc, out, _err = cli._invoke("run", tmp_path, monkeypatch, stdin=json.dumps(env), stdin_flag=True, dp="dp-QG")
    result = json.loads(out)
    assert result["reason"] == "input-incomplete" and result["transport_attempts"] == 0 and not calls
    assert result["issues"][0]["field"] == "model_context.references.VC-987"


@pytest.mark.parametrize("dp", decision_points.ACTIVE_DP_IDS)
def test_all_prepared_dps_bind_desc_and_hydrated_criteria(dp, tmp_path):
    actual_key = REFERENCES.parents[1]
    key = actual_key.name
    contract = tmp_path / ".agenticdoc" / key
    contract.mkdir(parents=True)
    for filename in ("spec.md", "design.md"):
        (contract / filename).write_bytes((actual_key / filename).read_bytes())
    freeze = contract_guard.freeze_path(contract)
    freeze.parent.mkdir()
    freeze.write_bytes(contract_guard.freeze_path(actual_key).read_bytes())
    (tmp_path / "evidence.txt").write_text("The isolated check is ready.\n", encoding="utf-8")
    source = tmp_path / "criterion-note.txt"
    source.write_text("按VC-005核对请求里的引用。\n", encoding="utf-8")

    envelope = cli._envelope(dp, "criterion-coverage", key=key)
    material, preparation = envelope["material"], envelope["preparation"]
    context = preparation.setdefault("model_context", {})
    context.update(desc=["核对AC-005的引用。"], references={"proof": {"kind": "evidence", "path": source.name}})
    if dp == "dp-QG":
        for basis in preparation["basis_catalog"]:
            if "fix" in basis["applies_to"]:
                basis["finding_ids"] = ["F1"]
        context["reasons"] = {"F1": "One finding in the current review scope."}
    options = decision_backends.prepared_selection_options(dp, material, preparation)
    questions = decision_backends.build_prepared_questions(dp, material, preparation, options=options)
    projected = decision_points.model_state_for(dp, material)

    def request(**limits):
        return decision_points.prepared_model_request(dp, projected, preparation, questions, tmp_path,
                                                      key=key, options=options, **limits)

    state = request()
    expected = contract_guard.parse_acs((contract / "spec.md").read_text(encoding="utf-8"))["AC-005"]
    assert state["references"]["AC-005"]["text"] == expected
    assert state["references"]["VC-005"]["source_criteria"] == ["AC-005"]
    assert {pathlib.Path(row["path"]).name for row in state.file_evidence} >= {"spec.md", "design.md", freeze.name, source.name}
    assert state.field_trace["fields"]["/state/references/AC-005"]["sources"] == [f"contract:{key}/spec.md#AC-005"]
    source_index = next(i for i, row in enumerate(state["evidence_sources"]) if pathlib.Path(row["path"]) == source)
    source.write_text("Check VC-999 in the evidence.\n", encoding="utf-8")
    with pytest.raises(decision_points.decision_material_sources.SourceMaterialError) as refused:
        request()
    assert refused.value.diagnostics[0]["source_field"] == f"state.evidence_sources[{source_index}].text"
    assert refused.value.diagnostics[0]["criterion"] == "VC-999"
    if dp == "dp-w-type":
        note = contract / "evidence" / "criterion-note.md"
        filler = "Calibration waveform observed in the sample window.\n" * 500
        note.write_text(f"{filler}See [AC-005](../spec.md#ac-005) with VC-005.\n{filler}", encoding="utf-8")
        context["desc"] = ["Review ./spec.md#AC-005 for this delivery."]
        context["references"]["proof"]["path"] = note.relative_to(tmp_path).as_posix()
        compressed = request(max_state_bytes=8000)
        [excerpt] = compressed["evidence_sources"]
        assert excerpt["representation"] == "excerpt" and excerpt["omitted_lines"]
        assert "../spec.md#ac-005) with VC-005" in excerpt["text"]
        context["terminology"] = {"AC": "Audio control channel"}
        with pytest.raises(decision_points.decision_material_sources.SourceMaterialError, match="conflicts with the bound contract"):
            request()
        del context["terminology"]
        spec = contract / "spec.md"
        spec.write_text(spec.read_text(encoding="utf-8").replace(expected, "Unreviewed criterion wording."), encoding="utf-8")
        with pytest.raises(decision_points.decision_material_sources.SourceMaterialError, match="criterion text differs from the bound contract freeze"):
            request()


def test_named_file_reference_cannot_be_rebound_by_an_external_selector(tmp_path, monkeypatch, isolated_credentials):
    env = cli._envelope("dp-w-type", "named-reference-rebinding", task_key=None)
    (tmp_path / "original.txt").write_text("Original review evidence.\n", encoding="utf-8")
    (tmp_path / "different.txt").write_text("Different matter evidence.\n", encoding="utf-8")
    env["preparation"]["model_context"] = {
        "desc": ["Choose the worker type for the current export task."],
        "references": {"W1": {"kind": "remaining_work", "path": "original.txt"}},
    }
    env["evidence_refs"] = [{"field": "preparation.model_context.references.W1.path", "path": "different.txt"}]
    calls = reply_with(monkeypatch, "codingA")
    _rc, out, _err = cli._invoke("run", tmp_path, monkeypatch, stdin=json.dumps(env), stdin_flag=True, dp="dp-w-type")
    result = json.loads(out)
    assert result["reason"] == "input-incomplete" and result["transport_attempts"] == 0 and not calls
    assert result["input_diagnostics"]["issues"][0] == {
        "field": "evidence_refs[0].field", "code": "invalid-evidence-reference",
    }


@pytest.mark.parametrize("named", [True, False])
def test_t09_file_prose_with_undefined_term_refuses_before_transport(named, tmp_path, monkeypatch, isolated_credentials):
    env = cli._envelope("dp-w-type", "named-reference-undefined-term", task_key=None)
    (tmp_path / "review-note.txt").write_text("用XRAY检查当前输出\n", encoding="utf-8")
    env["preparation"]["model_context"] = {"desc": ["Choose the worker type for the current export task."]}
    if named:
        env["preparation"]["model_context"]["references"] = {"W1": {"kind": "remaining_work", "path": "review-note.txt"}}
    else:
        env["material"]["task_requirements"] = "review-note.txt:1"
    calls = reply_with(monkeypatch, "codingA")
    _rc, out, _err = cli._invoke("run", tmp_path, monkeypatch, stdin=json.dumps(env), stdin_flag=True, dp="dp-w-type")
    result = json.loads(out)
    assert result["reason"] == "input-incomplete" and result["transport_attempts"] == 0 and not calls
    assert result["issues"][0]["field"] == "preparation.model_context.terminology.XRAY"


@pytest.mark.parametrize(("dp", "choice", "wire_id"), [
    ("dp-QG", "fix", "fixB"), ("dp-gate-approve", "approve", "approveA"),
])
def test_original_quality_and_gate_scope(dp, choice, wire_id, tmp_path, monkeypatch, isolated_credentials):
    source = reference_state(dp)
    env = cli._envelope(dp, "v05-original-scope", task_key=None)
    context = env["preparation"]["model_context"] = {}
    add_reference_sources(tmp_path, dp, context, include_findings=True)
    if dp == "dp-QG":
        key_dir = tmp_path / ".agenticdoc" / KEY
        key_dir.mkdir(exist_ok=True)
        (key_dir / "spec.md").write_text("".join(
            f"| {name} | {row['content']} |\n" for name, row in source["references"].items() if name.startswith("AC-")
        ), encoding="utf-8")
        (key_dir / "design.md").write_text("\n".join(
            f"{name}: {row['content']}\n  Layer: L2\n  Output: [VERIFY] {row['expected_result']}\n"
            f"  Source: {row['ac_ids'][0]}\n"
            for name, row in source["references"].items() if name.startswith("VC-")
        ), encoding="utf-8")
        (tmp_path / "review.txt").write_text(
            "The duplicate key was rejected but one insertion was observed. The concurrency check did not run.\n", encoding="utf-8",
        )
        env["material"] = {
            "review_requirements": "AC-001 and AC-002 of the scoped import transaction adapter.",
            "review_evidence": ["review.txt:1"],
            "review_findings": "F1 duplicate rejection still inserts once. F2 concurrency order remains unverified.",
            "uncovered_scope": "VC-002 concurrency order check did not run.",
        }
        context.update(
            desc=["Review duplicate rejection and import ordering.", "The fixture recorded a write on rejection.",
                  "The concurrency ordering check has not run."],
            review={name: {"status": "unmet" if name.endswith("001") else "unverified", "evidence": "review.txt:1"}
                    for name in ("AC-001", "AC-002", "VC-001", "VC-002")},
            reasons={name: source["references"][name]["content"] for name in ("F1", "F2")},
        )
        env["preparation"]["basis_catalog"] = [
            {"id": "pass-basis", "text": "Both criteria have current independent passing evidence.",
             "applies_to": ["pass"], "material_refs": ["review_requirements"]},
            {"id": "fixA-basis", "text": "Address F1 and leave F2 open.", "applies_to": ["fix"],
             "material_refs": ["review_findings"], "finding_ids": ["F1"], "remaining_ids": ["F2"]},
            {"id": "fixB-basis", "text": "Repair the duplicate rejection side effect and add the missing concurrency check.",
             "applies_to": ["fix"], "material_refs": ["review_findings"], "finding_ids": ["F1", "F2"], "remaining_ids": []},
            {"id": "reopen-basis", "text": "Escalate a substantive contradiction in the accepted requirements.",
             "applies_to": ["reopen"], "material_refs": ["review_requirements"]},
        ]
        note = ("The historical option set omitted reopen, so return that material for preparation. In the corrected fixture fixB covers F1 and F2. "
                "AC-002 and VC-002 remain unverified and not run. Recheck the scope, then independently verify the repair and the concurrency check. No repair, dispatch or formal quality pass in this case.")
    else:
        cli._write_policy(tmp_path, scope=["key:key-1", "action:gate-approve"])
        (tmp_path / "replay-plan.txt").write_text(
            "The fixture replay is read-only and configured to preserve the full diff. Scope is one frozen sample.\n", encoding="utf-8",
        )
        env["material"].update(
            gate_background="Approve one frozen read-only replay under the existing gate.",
            current_state="C1 read-only and C2 full diff preservation are configured. Estimated 10 minutes, 20 minutes available.",
            condition_evidence=["replay-plan.txt:1"],
            pm_note={"subject": "One frozen read-only replay", "planned_action": "Read only and retain the full diff.",
                     "basis": {"goal": "Obtain a reviewable diff for one sample", "evidence": "replay-plan.txt:1",
                               "budget": "10 minutes estimated with 20 remaining", "authority": "existing scoped replay authorization"}},
        )
        context["desc"] = ["Compare the gate conditions for one frozen replay.", "The fixture records read-only mode and complete diff retention.",
                           "Verify actual remaining authorization and budget before any execution."]
        use_reference_catalog(env, dp, dp, "condition_evidence")
        note = ("Accept one read-only replay of the frozen sample after checking the original authorization and remaining budget. "
                "Preserve the full diff and keep the coverage limited to this sample. No new permission and no execution.")
    save_json(tmp_path / "decision-book.json", env)
    calls = reply_with(monkeypatch, wire_id)
    rc, out, err = cli._invoke("run", tmp_path, monkeypatch, stdin=json.dumps(env), stdin_flag=True, dp=dp)
    assert rc == 0, (out, err)
    result = json.loads(out)
    assert result.get("choice") == choice and len(calls) == 1, result
    did = result["decision_id"]
    consumed = lifecycle(tmp_path, monkeypatch, env, did, "consumed", answer=choice)
    settled = lifecycle(tmp_path, monkeypatch, env, did, "settled", outcome="pending", reason=note)
    assert not any(row.get("lifecycle") == "executed" for row in cli._lifecycle_events(tmp_path))
    save_json(tmp_path / "pipeline-evidence.json", {
        "dp": dp, "decision_id": did, "call_id": result["call_id"], "writer": "mw decide lifecycle",
        "normalized": {key: result[key] for key in ("choice", "basis_id", "finding_ids", "remaining_ids")},
        "desc_measurement": result["desc_measurement"], "choice": choice, "pm_reason": note,
        "receipts": {"consumed": consumed["event_id"], "settled": settled["event_id"]},
    })


def test_gate_actual_effect_and_receipts_from_same_call(tmp_path, monkeypatch, capsys):
    f = gate_fixtures._pm_run_fixture(tmp_path, "h01")
    project = f["root"]
    f["book"]["book"]["meta"]["task_key"] = None
    desc = ["Review the requested gate change against the current authority and evidence.",
            "A successful application must update the target and leave a gate receipt."]
    f["book"]["book"]["preparation"]["model_context"] = {"desc": desc}
    save_json(f["book_path"], f["book"])
    gate_fixtures._pm_deploy_authority(monkeypatch, project, f["owner"], f["action"])
    gate_fixtures._seed_gate_case_sources(project)
    calls = reply_with(monkeypatch, "approveA")
    save_json(project / ".mw" / "decide.json", {"enabled": True, "api_key": "offline-gate-fixture-0123456789"})
    snapshot = decision.credential_snapshot
    monkeypatch.setattr(decision, "credential_snapshot", lambda cfg=None, **_kwargs: snapshot(
        cfg, env={}, auth_path=project / "absent-auth.json",
    ))
    before = f["target"].read_bytes()
    rc = gate_fixtures.mw_cli._ap_gate_run(gate_fixtures._pm_run_args(f), project)
    output = capsys.readouterr()
    assert rc == 0, output
    result = json.loads(output.out)
    assert result["status"] == "applied" and result["receipt"] and len(calls) == 1
    assert f["target"].read_bytes() != before
    records = cli._lifecycle_events(project)
    rows = [row for row in records if row.get("lifecycle")]
    assert [row["lifecycle"] for row in rows] == ["consumed", "executed", "settled"]
    assert all(row["decision_id"] == result["decision_ref"] for row in rows)
    captures = decision_wire.read_events(decision_wire.production_wire_sink(project)).events
    [start] = [row for row in captures if row["kind"] == "attempt-start"]
    [end] = [row for row in captures if row["kind"] == "attempt-end"]
    assert start["decision_id"] == end["decision_id"] == result["decision_ref"]
    assert start["call_id"] == end["call_id"] and start["key"] == end["key"] == f["owner"]
    assert calls[0] == (start["request"]["text"].encode(), end["response"]["text"].encode())
    verify_context(calls[0][0], desc)
    save_json(project / "pipeline-supplement.json", {
        "dp": "dp-gate-approve", "decision_id": result["decision_ref"], "call_id": start["call_id"],
        "writer": "mw autopilot gate run", "effect": result, "choice": "approve",
        "effect_sha256": hashlib.sha256(f["target"].read_bytes()).hexdigest(),
        "receipts": {row["lifecycle"]: row["event_id"] for row in rows},
    })


def test_sign_current_continue_matches_raw_response_and_official_disposition(tmp_path, monkeypatch, isolated_credentials):
    project, key_dir = cli._sign_project(tmp_path)
    cfg = project / ".mw" / "decide.json"
    settings = json.loads(cfg.read_text(encoding="utf-8"))
    settings["api_key"] = "isolated-sign-fixture-0123456789"
    save_json(cfg, settings)
    env = cli._sign_envelope("current-sign-continue")
    env["meta"]["task_key"] = None
    source = reference_state("dp-sign-key")
    contract = source["references"]
    env["material"].update(
        delivery_goal=source["material"]["goal"],
        actual_completion="Special-character round trip was checked. The interruption scenario has not run.",
        verification_evidence={"verified": ["AC-001: Special-character round-trip passed."],
                               "unverified": ["AC-002: Interruption and partial-output behavior were not tested."]},
        unfinished_impact=["The current QG is fix. Interruption behavior is open and can be checked within the existing scope."],
    )
    (key_dir / "spec.md").write_text(
        "".join(f"| {name} | {row['content']} |\n" for name, row in contract.items()), encoding="utf-8",
    )
    (key_dir / "design.md").write_text(
        "VC-001: Round-trip special characters and compare the result.\n"
        "  Layer: L2\n  Output: [VERIFY] round-trip\n  Source: AC-001\n", encoding="utf-8",
    )
    decide_archive.append_decide(
        project / ".agenticdoc" / "_autopilot" / "decisions.jsonl", dp="dp-QG",
        key=env["meta"]["key"], task_key=None, trigger_id="v05-current-qg-fix", state=source["material"],
        questions_version="q-0123abcd", available=True, answer={"q-verdict": {"value": "fix", "confidence": 0.9}},
        authority="binding", acted=True, actual_action="record unmatched interruption criterion",
        mode="auto", transport="timi-decisions", model="jev-latest", confidence_source="api",
    )
    desc = ["Deliver stable export of special characters.", "The round trip passed in the fixture.",
            "QG recorded fix because interruption and partial-output handling remain unverified."]
    env["preparation"]["model_context"] = {
        "desc": desc,
        "review": {
            "AC-001": {"status": "met", "evidence": "The fixture records a successful round trip."},
            "AC-002": {"status": "unverified", "evidence": "The interruption check has not run."},
            "VC-001": {"status": "met", "evidence": "The fixture records matching round-trip values."},
        },
    }
    add_reference_sources(project, "dp-sign-key", env["preparation"]["model_context"])
    use_reference_catalog(env, "dp-sign-key", "dp-sign-key", "verification_evidence")
    save_json(project / "decision-book.json", env)
    calls = reply_with(monkeypatch, "continueA")
    rc, out, err = cli._invoke("sign", project, monkeypatch, stdin=json.dumps(env), stdin_flag=True,
                               **cli._sign_args(project, json=True))
    assert rc == 0, (out, err)
    result = json.loads(out)
    assert result["conclusion"] == "continue" and result["signoff_status"] == "not-required"
    assert not decision_signoff_result.signoff_path(key_dir).exists()
    wire = decision_wire.read_events(decision_wire.production_wire_sink(project)).events
    [start] = [row for row in wire if row["kind"] == "attempt-start"]
    [end] = [row for row in wire if row["kind"] == "attempt-end"]
    assert start["call_id"] == end["call_id"] and start["decision_id"] == end["decision_id"]
    assert len(calls) == 1 and calls[0] == (start["request"]["text"].encode(), end["response"]["text"].encode())
    state = verify_context(calls[0][0], desc)
    assert state["references"]["AC-001"]["text"] == contract["AC-001"]["content"]
    assert state["references"]["AC-002"]["review"]["status"] == "unverified"
    assert state["references"]["VC-001"]["source_criteria"] == ["AC-001"]
    assert result["remaining_ids"] == []
    rows = [row for row in cli._lifecycle_events(project) if row.get("lifecycle")]
    assert rows and all(row["decision_id"] == start["decision_id"] for row in rows)
    save_json(project / "pipeline-evidence.json", {
        "dp": "dp-sign-key", "decision_id": start["decision_id"], "call_id": start["call_id"],
        "choice": result["conclusion"], "writer": "mw decide sign", "disposition": result,
        "normalized": {key: result[key] for key in ("choice", "basis_id", "finding_ids", "remaining_ids")},
        "desc_measurement": result["desc_measurement"],
        "receipts": {row["lifecycle"]: row["event_id"] for row in rows},
    })


def test_qg_fix_run_independent_review_and_formal_receipt(tmp_path, monkeypatch, isolated_credentials):
    project = tmp_path
    doc = project / ".agenticdoc"
    key_dir = doc / KEY
    key_dir.mkdir(exist_ok=True)
    (doc / "target.yml").write_text("active: single\n", encoding="utf-8")
    (doc / "goal.md").write_text("# Goal\n\nVerify the ordered import and its evidence anchor.\n", encoding="utf-8")
    spec = ("# Spec\n\n> Decision signoff: required\n\n"
            "| AC-001 | The check detects reordering of imported rows. |\n"
            "| AC-002 | The evidence index points to the exact ordering assertion. |\n")
    design = ("# Design\n\n| FLOW-001 | Import rows in supplied order. |\n\n"
              "VC-001: Run the check against the implementation and against a reordered mutant.\n"
              "       Layer: L2\n       Output: [VERIFY] ordering\n       Source: AC-001\n\n"
              "VC-002: Resolve the indexed path and line against the actual assertion.\n"
              "       Layer: L2\n       Output: [VERIFY] anchor\n       Source: AC-002\n")
    (key_dir / "spec.md").write_text(spec, encoding="utf-8")
    (key_dir / "design.md").write_text(design, encoding="utf-8")
    contract_guard.freeze_contract(key_dir, KEY, spec, design)
    (project / "ordered_rows.py").write_text("def ordered_rows(rows):\n    return tuple(rows)\n", encoding="utf-8")
    checks = project / "checks.py"
    checks.write_text(
        'from ordered_rows import ordered_rows\n\nrows = ("z", "a", "m")\nassert len(ordered_rows(rows)) == len(rows)\n',
        encoding="utf-8",
    )
    anchors = project / "anchors.json"
    save_json(anchors, {"ordering_assertion": {"path": "checks.py", "line": 2}})
    before = subprocess.run(
        [sys.executable, "-B", str(FIXTURES / "qg_chain_review.py"), str(project)],
        cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=20,
    )
    assert before.returncode != 0 and "AC-001" in before.stderr and "AC-002" in before.stderr, before
    (project / "review-before.txt").write_text(before.stderr, encoding="utf-8")

    env = cli._envelope("dp-QG", "qg-repair-and-review-1", task_key=None)
    env["material"] = {
        "review_requirements": "AC-001: Detect row reordering. AC-002: Cite the ordering assertion at its actual line.",
        "review_evidence": ["review-before.txt", "checks.py", "anchors.json"],
        "review_findings": "F1: Missing ordering assertion. F2: Stale assertion anchor.",
        "uncovered_scope": "Application runtime outside the isolated import remains unverified.",
    }
    env["preparation"] = {
        "prepared_at": cli.PREPARED_AT,
        "model_context": {
            "desc": ["Verify that imports preserve row order and that the evidence anchor reaches that assertion.",
                     "The independent check found missing ordering coverage and a stale anchor.",
                     "The check output and current files provide the review evidence."],
            "review": {name: {"status": "unmet", "evidence": "review-before.txt:1"}
                       for name in ("AC-001", "AC-002", "VC-001", "VC-002")},
            "reasons": {"F1": "The existing assertion checks length only.", "F2": "The evidence anchor points at the wrong line."},
        },
        "basis_catalog": [
            {"id": "pass-review", "applies_to": ["pass"], "material_refs": ["review_requirements"],
             "text": "All current ACs and the independent evidence checks pass."},
            {"id": "order-only", "applies_to": ["fix"], "material_refs": ["review_findings"],
             "finding_ids": ["F1"], "remaining_ids": ["F2"],
             "text": "F1: Add the missing ordering assertion, with F2 outstanding."},
            {"id": "order-and-anchor", "applies_to": ["fix"], "material_refs": ["review_findings"],
             "finding_ids": ["F1", "F2"], "remaining_ids": [],
             "text": "F1: Add the ordering assertion. F2: Update the stale evidence anchor."},
            {"id": "reopen-contract", "applies_to": ["reopen"], "material_refs": ["review_requirements"],
             "text": "A substantive conflict in the accepted quality requirements needs adjudication."},
        ],
    }
    save_json(project / "decision-book.json", env)
    wire = []

    def offline_response(request, *, timeout):
        assert request.method == "POST" and timeout > 0
        raw = json.dumps({"id": "qg-repair-fixture", "model": "jev-latest", "answers": {
            "decision_selection": {"type": "choice", "choice": "fixB", "confidence": 0.93},
        }}).encode()
        wire.append((request.data, raw))
        response = BytesIO(raw)
        response.status = 200
        response.headers = {"Content-Type": "application/json"}
        return response

    monkeypatch.setattr(decision_backends.urllib.request, "urlopen", offline_response)
    rc, out, err = cli._invoke("run", project, monkeypatch, stdin=json.dumps(env), stdin_flag=True, dp="dp-QG")
    assert rc == 0, (out, err)
    selected = json.loads(out)
    assert (selected["choice"], selected["basis_id"], selected["transport_attempts"]) == ("fix", "order-and-anchor", 1)
    state = verify_context(wire[0][0], env["preparation"]["model_context"]["desc"])
    assert state["references"]["AC-001"]["text"] == "The check detects reordering of imported rows."
    assert state["references"]["VC-002"]["review"]["status"] == "unmet"
    assert any("preparation.model_context.review.VC-002.evidence" in row["references"] for row in state["evidence_sources"])
    assert (selected["finding_ids"], selected["remaining_ids"]) == (["F1", "F2"], [])
    result_id = selected["decision_id"]
    consumed = lifecycle(project, monkeypatch, env, result_id, "consumed", answer="fix",
                         reason="Independent inspection found missing ordering assertion F1 and stale anchor F2.")
    ledger_before = cli._lifecycle_events(project)
    for meta, receipt_id, answer in (
        (dict(env["meta"], task_key="task-1"), result_id, "fix"),
        (env["meta"], "dp-QG:other-attempt", "fix"),
        (env["meta"], result_id, "pass"),
        (dict(env["meta"], key="key-worker"), result_id, "fix"),
    ):
        payload = {"meta": meta, "decision_id": receipt_id, "dp": "dp-QG", "stage": "consumed", "answer": answer}
        denied, out, _ = cli._invoke("lifecycle", project, monkeypatch, stdin=json.dumps(payload), stdin_flag=True)
        assert denied == 2 and json.loads(out)["recorded"] is False
    reused = {"meta": env["meta"], "decision_id": result_id, "dp": "dp-QG", "stage": "settled",
              "event_id": consumed["event_id"], "outcome": "ok"}
    denied, out, _ = cli._invoke("lifecycle", project, monkeypatch, stdin=json.dumps(reused), stdin_flag=True)
    assert denied == 2 and json.loads(out)["recorded"] is False
    assert cli._lifecycle_events(project) == ledger_before

    checks.write_text(checks.read_text(encoding="utf-8") + "assert ordered_rows(rows) == rows\n", encoding="utf-8")
    save_json(anchors, {"ordering_assertion": {"path": "checks.py", "line": 5}})
    repair = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in (checks, anchors)}
    executed = lifecycle(project, monkeypatch, env, result_id, "executed", action="record",
                         result=f"F1/F2 repaired on exact bytes {json.dumps(repair, sort_keys=True)}")

    _set_index_phase_file(project, KEY, "VERIFY")
    st = _state(project)
    review = dispatch.dispatch(
        project, KEY, "l3-a1", "reviewer", f"Independently verify repaired evidence for {result_id}.",
        loop=f"l3:{KEY}", attempt=1, read_scope=["checks.py", "ordered_rows.py", "anchors.json", f".agenticdoc/{KEY}"],
        timeline=st.timeline,
    )
    assert review.ok and review.row_verified and review.task_md, review
    worker_dir = review.task_md.parent
    process = subprocess.run(
        ["node", str(FIXTURES / "qg_review_worker.mjs"), sys.executable, str(FIXTURES / "qg_chain_review.py"),
         str(project), str(worker_dir), KEY, review.task_key],
        cwd=project, capture_output=True, text=True, encoding="utf-8", timeout=25,
    )
    assert process.returncode == 0, (process.stdout, process.stderr, (worker_dir / "trace.log").read_text())
    mw_common.update_status(project, review.task_key, "done")
    run = json.loads((worker_dir / "run.json").read_text(encoding="utf-8"))
    output = worker_dir / "output.md"
    assert run["pid"] and run["status"] == "done" and run["artifacts"] == ["output.md"]
    assert all(f"{name}@{digest}" in output.read_text(encoding="utf-8") for name, digest in repair.items())

    # Exercise the actual QG publication and sign-off writers. The final SDD
    # phase transition is outside this isolated review transaction.
    monkeypatch.setattr(conductor, "_timed_advance", lambda *_args, **_kwargs: (2, "", "phase advance outside fixture", 0))
    status, detail = conductor._done_transaction(project, st, KEY, output)
    assert (status, detail) == ("gated", "phase advance outside fixture"), (status, detail)
    [report] = (key_dir / "evidence").glob("quality-gate-report-*.md")
    assert output.relative_to(project).as_posix() in report.read_text(encoding="utf-8")
    binding = decision_signoff_result.current_review_binding(key_dir, KEY)
    model_gate = decision_signoff_result.model_quality_gate(key_dir, KEY, binding)
    assert (model_gate["status"], model_gate["conclusion"], model_gate["object"]) == ("verified", "pass", KEY)
    assert model_gate["scope"]["kind"] == "whole-key"
    assert {criterion["id"] for criterion in model_gate["scope"]["criteria"]} == {
        "AC-001", "AC-002", "VC-001", "VC-002", "FLOW-001",
    }
    assert model_gate["independent_review"]["run_id"] == run["run_id"]
    assert model_gate["version"]["artifact"] == report.relative_to(key_dir).as_posix()
    assert conductor._parse_l3_output(project, KEY, 1) == "meets"
    signoff = decision_signoff_result.validate_signoff(key_dir, KEY)
    assert signoff.valid and signoff.native_basis_verified, signoff
    report_hash = hashlib.sha256(report.read_bytes()).hexdigest()
    settlement_fields = {
        "outcome": "ok", "event_id": "qg-repair-reviewed-settlement",
        "reason": f"{report.relative_to(project).as_posix()}@{report_hash}; review run {run['run_id']}",
    }
    settled = lifecycle(project, monkeypatch, env, result_id, "settled", **settlement_fields)
    repeated = lifecycle(project, monkeypatch, env, result_id, "settled", **settlement_fields)
    assert repeated["duplicate"] and repeated["event_id"] == settled["event_id"]
    events = cli._lifecycle_events(project)
    assert {row["event_id"] for row in events if row.get("lifecycle")} == {
        receipt["event_id"] for receipt in (consumed, executed, settled)
    }
    assert all(row["decision_id"] == result_id for row in events)
    captures = decision_wire.read_events(decision_wire.production_wire_sink(project)).events
    [attempt] = [row for row in captures if row["kind"] == "attempt-start"]
    [response] = [row for row in captures if row["kind"] == "attempt-end"]
    assert attempt["decision_id"] == response["decision_id"] == result_id
    assert attempt["call_id"] == response["call_id"] == selected["call_id"]
    assert (attempt["request"]["text"].encode(), response["response"]["text"].encode()) == wire[0]
    save_json(project / "pipeline-supplement.json", {
        "dp": "dp-QG", "choice": selected["choice"], "basis_id": selected["basis_id"],
        "normalized": {key: selected[key] for key in ("choice", "basis_id", "finding_ids", "remaining_ids")},
        "desc_measurement": selected["desc_measurement"],
        "writer": "L3 done transaction and mw decide lifecycle",
        "decision_id": result_id, "call_id": selected["call_id"], "repair_hashes": repair,
        "review_run_id": run["run_id"], "qg_path": report.relative_to(project).as_posix(),
        "qg_sha256": report_hash, "local_signoff_id": signoff.logical_id,
        "receipts": {receipt["stage"]: receipt["event_id"] for receipt in (consumed, executed, settled)},
    })
