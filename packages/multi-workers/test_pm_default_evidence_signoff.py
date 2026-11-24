"""Default MW PM closure reuses durable independent evidence."""

import argparse
import hashlib
import json
import pathlib

import pytest

import decision_signoff_result
import mw
from autopilot import contract_guard, gates

KEY = "evidence-signoff"

def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    project = tmp_path / "proj"
    (project / ".agenticdoc" / KEY / "evidence" / "review").mkdir(parents=True)
    return project


@pytest.mark.parametrize("case", ["handoff", "conductor-output", "legacy-freeze", "legacy-drift", "no-review", "evidence-drift", "approval-pending", "approval-rejected"])
@pytest.mark.parametrize("default_done", [False, True])
def test_reviewed_evidence_signoff_survives_handoff(tmp_path, monkeypatch, capsys, case, default_done):
    project = _project(tmp_path)
    doc = project / ".agenticdoc"
    key_dir = doc / KEY
    index = doc / "_index.parallel"
    index.write_text(f"| {KEY} | active | VERIFY | old-pm:1 | | | |\n", encoding="utf-8")
    (doc / "goal.md").write_text("# Goal\nShip the reviewed result.\n", encoding="utf-8")
    spec = "# Spec\n\n> Decision signoff: required\n\n| AC-001 | Ship the result |\n"
    design = (
        "# Design\n\n| FLOW-001 | Check the result |\n\nVC-001: Checked result\n"
        "       Layer: L2\n       Output: [VERIFY] checked\n       Source: AC-001\n"
    )
    (key_dir / "design.md").write_text(design, encoding="utf-8")
    freeze_args = argparse.Namespace(key=KEY, block="all", force=False, as_json=True)
    if case.startswith("legacy-"):
        (key_dir / "spec.md").write_text(spec.replace("> Decision signoff: required\n", ""), encoding="utf-8")
        assert mw._ap_contract_freeze(freeze_args, project) == 0
        capsys.readouterr()
        cfg = project / ".mw"
        cfg.mkdir(exist_ok=True)
        (cfg / "decide-points.json").write_text(json.dumps({
            "points": {"dp-sign-key": {"enabled": False}},
        }), encoding="utf-8")
        assert mw.decision_points.load_points_config(project).row("dp-sign-key").enabled is False
    else:
        contract_guard.freeze_contract(key_dir, KEY, spec, design)
    freeze_path = contract_guard.freeze_path(key_dir)
    original_freeze = freeze_path.read_bytes()
    if case == "legacy-drift":
        design = design.replace("Check the result", "Check the changed result")
        (key_dir / "design.md").write_text(design, encoding="utf-8")
    (key_dir / "spec.md").write_text(spec, encoding="utf-8")
    product = project / "result.txt"
    product.write_bytes(b"checked")
    digest = hashlib.sha256(product.read_bytes()).hexdigest()
    qg = "## Quality Gate Report\n\n" + "".join(
        f"| {item} | PASS | result.txt@{digest} |\n" for item in ("AC-001", "FLOW-001", "VC-001")
    )
    achieved = "## Achieved\n\nThe checked result shipped.\n"
    (key_dir / "achieved.md").write_text(achieved, encoding="utf-8")
    (key_dir / "evidence/quality-gate-report-test.md").write_text(qg, encoding="utf-8")
    task = key_dir / "workers/review-1"
    task.mkdir(parents=True)
    (key_dir / "tasks").mkdir()
    card = b"# Independent review\n"
    (key_dir / "tasks/review.md").write_bytes(card)
    pin = hashlib.sha256(card).hexdigest()
    envelope = task / "task.md"
    conductor_review = case == "conductor-output"
    kind = "reviewer" if conductor_review else "review"
    artifact = "output.md" if conductor_review else "report.md"
    head = f"type: reviewer\norigin: conductor\nloop: l3:{KEY}\n" if conductor_review else (
        f"type: review\ncard_path: tasks/review.md\ncard_sha256: {pin}\n"
    )
    envelope.write_text(head, encoding="utf-8")
    (task / artifact).write_text(qg + "\n" + achieved, encoding="utf-8")
    if conductor_review:
        (task / "trace.log").write_text("verified terminal review\n", encoding="utf-8")
    started = "2026-11-22T01:00:00Z"
    (task / "run.json").write_text(json.dumps({
        "kind": kind, "owner_key": KEY, "task_key": "review-1", "status": "done", "exit": 0,
        "started_at": started, "ended_at": "2026-11-22T01:01:00Z", "run_id": f"review-1@{started}",
        "artifacts": [artifact],
    }), encoding="utf-8")
    (doc / "_workers.parallel").write_text(
        f"review-1 | done | pi | local | {envelope} | {started} | {started} | | "
        + ("conductor\n" if conductor_review else "manual\n"), encoding="utf-8"
    )
    if case == "no-review":
        (task / "run.json").unlink()
    if case == "evidence-drift":
        product.write_bytes(b"changed")
    if case.startswith("approval"):
        gate = gates.create(doc / "_autopilot/gates", "stage-close", "Approve closure?", key=KEY, stage=1)
        if case == "approval-rejected":
            text = gate.read_text(encoding="utf-8").replace("status: pending", "status: rejected")
            gate.write_text(text, encoding="utf-8")
    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    index.write_text(f"| {KEY} | active | VERIFY | new-pm:2 | | | |\n", encoding="utf-8")
    args = argparse.Namespace(json=True, retry_write=None, for_done=True, key=KEY, key_pos=None)
    request = {"decision_source": "pm-evidence", "review_task": "review-1", "review_source": f"workers/review-1/{artifact}"}
    if case == "legacy-freeze":
        with pytest.raises(decision_signoff_result.SignoffResultError, match="decision_signoff: required"):
            decision_signoff_result.capture_reviewed_signoff(key_dir, KEY, "review-1", request["review_source"])
        assert not decision_signoff_result.signoff_path(key_dir).exists()
        assert freeze_path.read_bytes() == original_freeze
    rc = mw._decide_sign(args, project) if default_done else mw._decide_sign_reviewed(args, key_dir, KEY, request)
    receipt = json.loads(capsys.readouterr().out)
    if case not in {"handoff", "conductor-output", "legacy-freeze"}:
        assert rc == 2
        expected_problem = {
            "legacy-drift": "differs from the frozen sign-off contract",
            "no-review": "file is missing",
            "evidence-drift": "evidence bytes changed",
            "approval-pending": "required approval is unresolved",
            "approval-rejected": "required approval is unresolved",
        }
        assert expected_problem[case] in receipt["problems"][0]
        assert not decision_signoff_result.signoff_path(key_dir).exists()
        assert freeze_path.read_bytes() == original_freeze
        return
    assert rc == 0, receipt
    assert receipt["signoff_status"] == "written"
    if case == "legacy-freeze":
        assert contract_guard.read_freeze(key_dir) == {**json.loads(original_freeze), "decision_signoff": "required"}
    index.write_text(f"| {KEY} | idle | DONE | - | | | |\n", encoding="utf-8")
    assert decision_signoff_result.validate_signoff(key_dir, KEY).valid
    rc = mw._decide_sign(args, project) if default_done else mw._decide_sign_reviewed(args, key_dir, KEY, request)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["signoff_status"] == "existing"
    product.write_bytes(b"changed after signing")
    assert not decision_signoff_result.validate_signoff(key_dir, KEY).valid
