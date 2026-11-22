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


@pytest.mark.parametrize("case", ["handoff", "no-review", "evidence-drift", "approval-pending", "approval-rejected"])
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
    (key_dir / "spec.md").write_text(spec, encoding="utf-8")
    (key_dir / "design.md").write_text(design, encoding="utf-8")
    contract_guard.freeze_contract(key_dir, KEY, spec, design)
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
    envelope.write_text(f"type: review\ncard_path: tasks/review.md\ncard_sha256: {pin}\n", encoding="utf-8")
    (task / "report.md").write_text(qg + "\n" + achieved, encoding="utf-8")
    started = "2026-11-22T01:00:00Z"
    (task / "run.json").write_text(json.dumps({
        "kind": "review", "owner_key": KEY, "task_key": "review-1", "status": "done", "exit": 0,
        "started_at": started, "ended_at": "2026-11-22T01:01:00Z", "run_id": f"review-1@{started}",
        "artifacts": ["report.md"],
    }), encoding="utf-8")
    (doc / "_workers.parallel").write_text(
        f"review-1 | done | pi | local | {envelope} | {started} | {started}\n", encoding="utf-8"
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
    request = {"decision_source": "pm-evidence", "review_task": "review-1", "review_source": "workers/review-1/report.md"}
    rc = mw._decide_sign(args, project) if default_done else mw._decide_sign_reviewed(args, key_dir, KEY, request)
    receipt = json.loads(capsys.readouterr().out)
    if case != "handoff":
        assert rc == 2
        expected_problem = {
            "no-review": "file is missing",
            "evidence-drift": "evidence bytes changed",
            "approval-pending": "required approval is unresolved",
            "approval-rejected": "required approval is unresolved",
        }
        assert expected_problem[case] in receipt["problems"][0]
        assert not decision_signoff_result.signoff_path(key_dir).exists()
        return
    assert rc == 0, receipt
    assert receipt["signoff_status"] == "written"
    index.write_text(f"| {KEY} | idle | DONE | - | | | |\n", encoding="utf-8")
    assert decision_signoff_result.validate_signoff(key_dir, KEY).valid
    rc = mw._decide_sign(args, project) if default_done else mw._decide_sign_reviewed(args, key_dir, KEY, request)
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["signoff_status"] == "existing"
    product.write_bytes(b"changed after signing")
    assert not decision_signoff_result.validate_signoff(key_dir, KEY).valid
