"""Exercise material semantics through preview and the formal prepared CLI."""

import json

import pytest

from autopilot import contract_guard
import test_dp_consolidation_cli as cli
from test_dp_consolidation_cli import _all_entries_enabled
from test_decision_drafts import invoke
from test_prepared_cli_source_snapshot import isolated_credentials
from test.test_dp_material_pipeline_l2 import reply_with


def submit(project, monkeypatch, dp, env, preview=None):
    _, out, _ = cli._invoke("run", project, monkeypatch, dp=dp, stdin_flag=True, stdin=json.dumps(env),
                            prepared_snapshot=preview["snapshot"] if preview else None)
    return json.loads(out)


@pytest.mark.parametrize(("selected", "remaining", "reasons", "wire", "error_field"), [
    ([], [], {}, "fixA", None),
    (None, None, {}, "passA", None),
    (None, None, {}, "reopenA", None),
    (["F1"], [], {"F1": "An assertion is missing."}, "fixA", None),
    (["F1"], ["F2"], {"F1": "An assertion is missing.", "F2": "One comparison failed."}, "fixA", None),
    (["checkpoint-a"], None, {"checkpoint-a": "An assertion is missing.", "checkpoint-b": "One comparison failed."}, "fixA", None),
    (["F1"], [], {"F1": "An assertion is missing.", "F2": "One comparison failed."}, "fixA", "remaining_ids"),
    (["F1"], ["F1"], {"F1": "An assertion is missing."}, "fixA", "remaining_ids"),
    (["F2"], [], {"F1": "An assertion is missing."}, "fixA", "finding_ids"),
    ([], [], {"F1": "An assertion is missing."}, "fixA", "finding_ids"),
    (["F1"], None, {}, "fixA", "finding_ids"),
])
def test_qg_findings_partition(tmp_path, monkeypatch, isolated_credentials, selected, remaining, reasons, wire, error_field):
    dp = "dp-QG"
    env = cli._envelope(dp, "findings")
    env["preparation"]["model_context"] = {"reasons": reasons}
    env["preparation"]["basis_catalog"] = [
        {"id": choice, "text": text, "applies_to": [choice], "material_refs": ["review_findings"]}
        for choice, text in (("pass", "Independent proof meets the contract."),
                             ("fix", "Repair the selected product findings."),
                             ("reopen", "Resolve a conflict in the contract."))
    ]
    if selected is None:
        del env["preparation"]["basis_catalog"][1]
    else:
        env["preparation"]["basis_catalog"][1]["finding_ids"] = selected
        if remaining is not None:
            env["preparation"]["basis_catalog"][1]["remaining_ids"] = remaining
    if wire == "reopenA":
        env["material"]["basis_issue"] = "The approved criteria conflict on whether the export is required."
    preview = invoke(tmp_path, monkeypatch, dp, env)
    needs_review = not reasons and wire != "reopenA" and not error_field
    ready = not error_field and not needs_review
    assert preview["status"] == ("ready" if ready else "needs-repair"), preview
    calls = reply_with(monkeypatch, wire, expect_candidate=wire != "fixA" or bool(reasons))
    result = submit(tmp_path, monkeypatch, dp, env, preview if ready else None)
    if error_field:
        assert not calls and result["reason"] == "input-incomplete"
        assert preview["issues"][0]["field"] == f"preparation.basis_catalog[1].{error_field}"
    elif needs_review:
        assert not calls and result["reason"] == "input-incomplete"
        assert preview["issues"][0]["code"] == "qg-independent-review-required"
    elif not reasons:
        assert preview["choices"] == ["reopen"]
        assert len(calls) == 1 and "fixA" not in json.loads(calls[0][0])["questions"]["decision_selection"]["criteria"]
        assert result["available"] and result["choice"] == "reopen"
    else:
        assert len(calls) == 1 and result["choice"] == "fix"
        assert result["finding_ids"] == selected and result["remaining_ids"] == sorted(set(reasons) - set(selected))


def test_historical_scope_is_provenance_not_current_review(tmp_path, monkeypatch, isolated_credentials):
    key_dir = tmp_path / ".agenticdoc" / "key-1"
    key_dir.mkdir()
    spec = ("| AC-304 | Verify the current interface obligations. |\n\n"
            "| v3要求 | v4去向 | 事实与调度处理 |\n| --- | --- | --- |\n"
            "| v3 203 / 原VC-206 | AC-304 | The old certification is retired. |\n")
    (key_dir / "spec.md").write_text(spec, encoding="utf-8")
    freeze = contract_guard.freeze_path(key_dir)
    freeze.parent.mkdir()
    freeze.write_text(json.dumps(contract_guard.build_freeze("key-1", spec, "")), encoding="utf-8")
    log = key_dir / "old.log"
    log.write_text("The previous report mentioned AC-203, VC-206 and AC-999.\n", encoding="utf-8")
    env = cli._envelope("dp-pm-steer", "historical-steer")
    env["preparation"]["model_context"] = {"references": {
        "previous": {"kind": "file", "path": log.relative_to(tmp_path).as_posix()}
    }}
    calls = reply_with(monkeypatch, "narrowA")
    ready = invoke(tmp_path, monkeypatch, "dp-pm-steer", env)
    assert ready["status"] == "ready" and not calls, ready
    assert "AC-203" not in ready["criteria"] and ready["historical_references"]["AC-203"]["superseded_by"] == ["AC-304"]
    assert submit(tmp_path, monkeypatch, "dp-pm-steer", env, ready)["available"]
    refs = json.loads(calls[0][0])["state"]["references"]
    assert refs["AC-203"]["superseded_by"] == ["AC-304"]
    assert refs["AC-203"]["source"].endswith("spec.md:5")
    assert refs["VC-206"]["kind"] == "historical-criterion" and "AC-999" not in refs

    dp = "dp-QG"
    env = cli._envelope(dp, "historical-qg")
    env["material"]["basis_issue"] = "The fixture acceptance obligations are inconsistent."
    for basis in env["preparation"]["basis_catalog"]:
        basis.update(finding_ids=[], remaining_ids=[])
    context = env["preparation"]["model_context"] = {"review": {
        "AC-203": {"status": "met", "evidence": "The old log was checked."}
    }}
    rejected = invoke(tmp_path, monkeypatch, dp, env)
    assert rejected["status"] == "needs-repair" and rejected["issues"][0]["criterion"] == "AC-203"
    assert not submit(tmp_path, monkeypatch, dp, env)["available"] and len(calls) == 1
    context["review"]["AC-304"] = context["review"].pop("AC-203")
    assert invoke(tmp_path, monkeypatch, dp, env)["status"] == "ready"
    context["references"] = {"invented": {"kind": "historical-criterion", "text": "AC-203 was replaced."}}
    assert invoke(tmp_path, monkeypatch, dp, env)["status"] == "needs-repair"
    del context["references"]
    context["review"]["AC-304"]["evidence"] = ".agenticdoc/other/spec.md#AC-304"
    assert invoke(tmp_path, monkeypatch, dp, env)["issues"][0]["code"] == "criterion-reference-other-object"


def test_multi_layer_contract_and_source_diagnostics(tmp_path, monkeypatch, isolated_credentials):
    dp = "dp-QG"
    env = cli._envelope(dp, "layered")
    env["material"]["basis_issue"] = "The fixture contains inconsistent sample requirements."
    for basis in env["preparation"]["basis_catalog"]:
        basis.update(finding_ids=[], remaining_ids=[])
    env["material"]["review_findings"] = "PID62144 wrote README.md. The archived label VC001 and run_id=XRAY are traceable."
    key_dir = tmp_path / ".agenticdoc" / "key-1"
    key_dir.mkdir()
    spec = "| AC-001 | Verify one sample. |\n"
    design = "".join(f"VC-{i:03d}: Sample behavior.\n  Layer: {layer}\n"
                     f"  Output: [VERIFY] VC-{i:03d}: met\n  Source: AC-001\n\n"
                     for i, layer in enumerate(("L2", "L1 + L2", "L1 + L2", "L1 + L2", "L2", "L0 + L1 + L2"), 1))
    (key_dir / "spec.md").write_text(spec, encoding="utf-8")
    (key_dir / "design.md").write_text(design, encoding="utf-8")
    freeze = contract_guard.freeze_path(key_dir)
    freeze.parent.mkdir()
    freeze.write_text(json.dumps(contract_guard.build_freeze("key-1", spec, design)), encoding="utf-8")
    context = env["preparation"]["model_context"] = {"review": {
        name: {"status": "unverified", "evidence": "Independent check not recorded."}
        for name in contract_guard.parse_vcs(design)
    }}
    assert len(context["review"]) == 6
    ready = invoke(tmp_path, monkeypatch, dp, env)
    assert ready["status"] == "ready" and "VC-006" in ready["criteria"], ready
    env["material"]["review_findings"] += " Verify XRAY calibration."
    issue = invoke(tmp_path, monkeypatch, dp, env)["issues"][0]
    assert issue["field"].endswith(".XRAY") and issue["source_field"] == "material.review_findings"
    context["terminology"] = {"XRAY": "Calibration measurement for this sample."}
    env["evidence_refs"] = [{"field": "material.review_findings", "path": ".agenticdoc/key-1/design.md",
                             "lines": {"start": 1, "end": 100}}]
    issue = invoke(tmp_path, monkeypatch, dp, env)["issues"][0]
    assert issue["code"] == "evidence-range-out-of-bounds" and issue["file_line_count"] == 30
    del env["evidence_refs"]
    (key_dir / "design.md").write_text(design.replace("Layer: L1 + L2", "Broken layer", 1), encoding="utf-8")
    issue = invoke(tmp_path, monkeypatch, dp, env)["issues"][0]
    assert issue["criterion"] == "VC-002" and issue["source_line"] == 6


@pytest.mark.parametrize(("current", "verification", "unknown", "layer"), [
    ("AC-741", "VC-416", "AC-912", "L1 + L2"),
    ("AC-528", "VC-163", "VC-887", "L0 + L1 + L2"),
])
def test_unseen_contract_with_interleaved_repairs(tmp_path, monkeypatch, isolated_credentials,
                                                  current, verification, unknown, layer):
    dp = "dp-QG"
    env = cli._envelope(dp, "unseen-contract")
    key_dir = tmp_path / ".agenticdoc" / "key-1"
    key_dir.mkdir()
    spec = f"| {current} | Keep the public export readable. |\n"
    design = (f"{verification}: Check the exported record.\n  Layer: {layer}\n"
              f"  Output: [VERIFY] {verification}: readable\n  Source: {current}\n")
    (key_dir / "spec.md").write_text(spec, encoding="utf-8")
    (key_dir / "design.md").write_text(design, encoding="utf-8")
    freeze = contract_guard.freeze_path(key_dir)
    freeze.parent.mkdir()
    freeze.write_text(json.dumps(contract_guard.build_freeze("key-1", spec, design)), encoding="utf-8")
    log = key_dir / "archived.log"
    log.write_text(f"Old runs mentioned {unknown}.\nA report records the current dispute.\n", encoding="utf-8")
    env["material"].update(review_findings="Check the export against ZETA.",
                           basis_issue="The contract has inconsistent export requirements.")
    env["preparation"]["model_context"] = {
        "reasons": {}, "review": {verification: {"status": "unverified", "evidence": "Review is incomplete."}}
    }
    env["preparation"]["basis_catalog"] = [
        {"id": choice, "text": text, "applies_to": [choice], "material_refs": ["review_findings"]}
        for choice, text in (("pass", "Independent review meets the contract."),
                             ("reopen", "Resolve inconsistent contract requirements."))
    ]
    env["evidence_refs"] = [{"field": "material.review_findings", "path": log.relative_to(tmp_path).as_posix(),
                             "lines": {"start": 1, "end": 5}}]

    calls = reply_with(monkeypatch, "reopenA")
    preview = invoke(tmp_path, monkeypatch, dp, env)
    rejected = submit(tmp_path, monkeypatch, dp, env)
    assert preview["status"] == "needs-repair" and not calls
    assert {i["code"] for i in preview["issues"]} == {i["code"] for i in rejected["input_diagnostics"]["issues"]}
    repairs = {item["field"]: item["repair_id"] for issue in preview["issues"] for item in issue.get("repairs", [])}

    def repair(field, value):
        return invoke(tmp_path, monkeypatch, dp, env, draft_ref=preview["draft_ref"],
                      changes=[{"repair_id": repairs[field], "value": value}])

    assert repair("preparation.model_context.terminology.ZETA", "The export preservation check.")["status"] == "needs-repair"
    ready = repair("evidence_refs[0].lines.end", 2)
    assert ready["status"] == "ready" and not calls
    env.update(ready["book"])
    log.write_text(f"Old runs mentioned {unknown}.\nAn updated report records the current dispute.\n", encoding="utf-8")
    env["meta"]["logical_id"] = "unseen-contract-stale-snapshot"
    assert not submit(tmp_path, monkeypatch, dp, env, ready)["available"] and not calls
    draft = {"draft_ref": ready["draft_ref"]}
    drifted = invoke(tmp_path, monkeypatch, dp, env, **draft)
    assert drifted["status"] == "review" and drifted["snapshot"] != ready["snapshot"]
    ready = invoke(tmp_path, monkeypatch, dp, env, **draft)
    assert ready["status"] == "ready"
    env["meta"]["logical_id"] = "unseen-contract-repaired"
    assert submit(tmp_path, monkeypatch, dp, env, ready)["choice"] == "reopen" and len(calls) == 1
    state = json.loads(calls[0][0])["state"]
    assert state["references"][verification]["layer"] == layer
    assert unknown not in state["references"] and unknown in state["evidence_sources"][0]["text"]

    env["preparation"]["model_context"]["review"][unknown] = {"status": "met", "evidence": "Old logs mention it."}
    env["meta"]["logical_id"] = "unseen-contract-missing"
    assert invoke(tmp_path, monkeypatch, dp, env)["issues"][0]["criterion"] == unknown
    assert not submit(tmp_path, monkeypatch, dp, env)["available"] and len(calls) == 1
