"""Local sign-off source boundaries and the separate DP record contract."""

from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time

import pytest

import decision_points
import decision_signoff_result
import mw
from autopilot import contract_guard, gates

KEY = "mw-pm-dp-continuity-fixture"
DP = decision_signoff_result.DP_ID


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch):
    for name in ("PI_WORKER_TASK", "PI_WORKER_ID", "PI_DECISION_MODE"):
        monkeypatch.delenv(name, raising=False)
    decision_points.clear_points_config_cache()
    yield
    decision_points.clear_points_config_cache()


def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    project = tmp_path / "proj"
    (project / ".agenticdoc" / KEY / "evidence" / "review").mkdir(parents=True)
    return project


def _points(project: pathlib.Path, rows: object, *, raw: str | None = None) -> pathlib.Path:
    path = decision_points.decide_points_config_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        raw if raw is not None else json.dumps({"version": 1, "points": rows}, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    decision_points.clear_points_config_cache()
    return path


def _entry_mode(project: pathlib.Path):
    point = decision_points.require_active_dp(DP)
    return mw._decide_entry_mode(project, point)


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
    monkeypatch.setattr(decision_signoff_result, "read_local_signoff_proof", lambda *a, **kw: pytest.fail("live proof read"))
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


def test_current_sign_entry_is_refused_when_the_point_is_disabled(tmp_path: pathlib.Path) -> None:
    """A disabled dp-sign-key blocks BEFORE any request/model call."""
    project = _project(tmp_path)
    _points(project, {DP: {"tier": "P1", "enabled": False, "mode": "auto", "note": ""}})
    mode, blocked, escalated = _entry_mode(project)
    assert mode in ("auto", "suggest")
    assert blocked == "disabled"
    assert escalated == "disabled"


def test_an_enabled_sign_point_is_not_blocked_by_the_row(tmp_path: pathlib.Path) -> None:
    """Control for the refusal above: an enabled row is not the blocker.

    A malformed table also does not raise here: it falls back to the declared
    defaults, so the real blocker for a sign entry is DP availability, not the
    points row. That is exactly why the missing zero-DP source cannot be
    faked by editing this table.
    """
    project = _project(tmp_path)
    _points(project, {DP: {"tier": "P1", "enabled": True, "mode": "auto", "note": ""}})
    mode, blocked, escalated = _entry_mode(project)
    assert mode == "auto"
    assert blocked is None
    assert escalated is None


def test_dp_result_builder_refuses_local_evidence_ids(tmp_path: pathlib.Path) -> None:
    """The local source uses a distinct record and never acquires a DP ID."""
    project = _project(tmp_path)
    facts = type("Facts", (), {"sha256": "a" * 64})()
    for decision_id in (
        f"pm-evidence:{KEY}:1",
        f"local-qg-pass:{KEY}:1",
        "dp-sign-key",
        "",
    ):
        with pytest.raises(decision_signoff_result.SignoffResultError):
            decision_signoff_result.build_result(
                project / ".agenticdoc" / KEY,
                key=KEY,
                logical_id="11111111-1111-4111-8111-111111111111",
                decision_id=decision_id,
                conclusion="finalize",
                material={"sign_material": {"verdict": "finalize"}},
                facts=facts,
                transport="local-pm-evidence",
                model="none",
                confidence_source="pm-evidence",
            )


def test_dp_result_builder_refuses_unknown_conclusion(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    facts = type("Facts", (), {"sha256": "b" * 64})()
    with pytest.raises(decision_signoff_result.SignoffResultError):
        decision_signoff_result.build_result(
            project / ".agenticdoc" / KEY,
            key=KEY,
            logical_id="22222222-2222-4222-8222-222222222222",
            decision_id=f"{DP}:22222222-2222-4222-8222-222222222222",
            conclusion="ship-it",
            material={"sign_material": {"verdict": "ship-it"}},
            facts=facts,
            transport="local-pm-evidence",
            model="none",
            confidence_source="pm-evidence",
        )


def test_official_cli_refuses_local_ref_without_private_live_proof(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    result = subprocess.run(
        [sys.executable, str(pathlib.Path(mw.__file__)), "decide", "sign", KEY, "--project",
         str(project), "--stdin", "--json"],
        input=json.dumps({"decision_source": "pm-evidence", "local_ref": "lref:foreign"}),
        capture_output=True, text=True, encoding="utf-8", timeout=15,
    )
    assert result.returncode == 2, result.stderr
    assert json.loads(result.stdout)["problems"] == ["a private live PM proof is required"]
    assert not decision_signoff_result.signoff_path(project / ".agenticdoc" / KEY).exists()


def test_editable_local_signoff_without_live_host_is_not_a_current_product(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    sign = decision_signoff_result.signoff_path(key_dir)
    sign.write_text(
        "decision_source: pm-evidence\nproduct_type: key-signoff\n"
        "logical_id: 11111111111111111111111111111111\nconclusion: finalize\n",
        encoding="utf-8",
    )
    validated = decision_signoff_result.validate_signoff(key_dir, KEY)
    assert not validated.valid
    assert validated.reason == "current PM evidence attestation is unavailable"


@pytest.mark.parametrize("state", ["intact", "changed-sign", "changed-result", "missing", "host-lost"])
def test_lost_confirmation_only_reconciles_the_original_live_publication(tmp_path, monkeypatch, capsys, state):
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    args = argparse.Namespace(json=True)
    proof_id, nonce, snapshot = "1" * 32, "2" * 32, "3" * 64
    envelope = {"decision_source": "pm-evidence", "proof_id": proof_id, "proof_nonce": nonce}
    record = {"logical_id": proof_id, "snapshot_sha256": snapshot}
    prepared = None
    publication_calls = 0
    host_available = True

    def proof(_key_dir, _key, read_id, read_nonce, *, prepared_snapshot=None, published_snapshot=None):
        nonlocal prepared, publication_calls
        assert (read_id, read_nonce) == (proof_id, nonce)
        if not host_available:
            return None
        if prepared_snapshot is not None:
            prepared = prepared_snapshot
        if published_snapshot is not None:
            publication_calls += 1
            if publication_calls == 1:  # The initial writer's confirmation was never delivered.
                return None
            return {"publication_sha256": published_snapshot}
        return {"prepared_sha256": prepared}

    monkeypatch.setattr(decision_signoff_result, "read_local_signoff_proof", proof)
    monkeypatch.setattr(decision_signoff_result, "capture_local_signoff", lambda *_: record)
    assert mw._decide_sign_local(args, key_dir, KEY, envelope) == 2
    initial = json.loads(capsys.readouterr().out)
    assert initial["signoff_status"] == "effect-unknown", initial.get("problems")
    sign = decision_signoff_result.signoff_path(key_dir)
    result = decision_signoff_result.result_path(key_dir, proof_id)
    assert sign.is_file() and result.is_file()
    if state == "changed-sign":
        sign.write_text("edited", encoding="utf-8")
    elif state == "changed-result":
        result.write_text("{}", encoding="utf-8")
    elif state == "missing":
        sign.unlink()
    elif state == "host-lost":
        host_available = False

    before = {file: (file.read_bytes(), file.stat().st_mtime_ns) for file in (sign, result) if file.exists()}
    recovered = mw._decide_sign_local(args, key_dir, KEY, {**envelope, "reconcile": True})
    receipt = json.loads(capsys.readouterr().out)
    if state == "intact":
        assert recovered == 0
        assert receipt["signoff_status"] == "reconciled" and receipt["logical_id"] == proof_id
        assert publication_calls == 2
    else:
        assert recovered == 2 and receipt["conclusion"] == "continue"
        assert publication_calls == 1
    assert {file: (file.read_bytes(), file.stat().st_mtime_ns) for file in (sign, result) if file.exists()} == before


@pytest.mark.skipif(sys.platform != "win32", reason="Windows publication lock lifecycle")
def test_publication_lock_releases_when_its_writer_is_killed(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    lock = project / ".mw" / f"contract-publication-{KEY}.lock"
    child_code = """
import pathlib
import sys
import time
from autopilot.contract_guard import contract_publication_lock

with contract_publication_lock(pathlib.Path(sys.argv[1])):
    time.sleep(30)
"""
    child = subprocess.Popen(
        [sys.executable, "-B", "-c", child_code, str(key_dir)], cwd=pathlib.Path(mw.__file__).parent,
    )
    try:
        deadline = time.monotonic() + 5
        while not lock.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.025)
        assert lock.exists()
        with pytest.raises(RuntimeError, match="Could not acquire lock"):
            mw.mw_common.acquire_lock(lock, retries=0, delete_on_close=True)
    finally:
        child.kill()
        child.wait(timeout=5)
    assert not lock.exists()
    with decision_signoff_result.contract_guard.contract_publication_lock(key_dir):
        assert lock.exists()
    assert not lock.exists()


@pytest.mark.parametrize(
    ("rows", "reason"),
    [
        ("PASS", "missing AC-001, FLOW-001, VC-001"),
        ("| AC-001 | PASS | {ref} |", "missing FLOW-001, VC-001"),
        ("| AC-001 | FAIL | {ref} |", "invalid outcome for AC-001"),
        ("| AC-001 | PASS | — |", "invalid outcome for AC-001"),
        ("| AC-001 | PASS | evidence.txt@" + "0" * 64 + " |", "evidence bytes changed for AC-001"),
    ],
)
def test_local_qg_requires_current_outcome_for_every_contract_id(
    tmp_path: pathlib.Path, rows: str, reason: str,
) -> None:
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    (key_dir.parent / "goal.md").write_text("# Goal\nVerify the target.\n", encoding="utf-8")
    (key_dir / "spec.md").write_text(
        "# Spec\n\n> Decision signoff: required\n\n| AC-001 | The target is verified. |\n", encoding="utf-8",
    )
    (key_dir / "design.md").write_text(
        "# Design\n| FLOW-001 | Verify the target. |\n\n"
        "VC-001: The target is verified.\n       Layer: L2\n"
        "       Output: [VERIFY] VC-001: target_verified=1\n       Source: AC-001\n",
        encoding="utf-8",
    )
    guard = decision_signoff_result.contract_guard
    guard.freeze_contract(
        key_dir, KEY, (key_dir / "spec.md").read_text(encoding="utf-8"),
        (key_dir / "design.md").read_text(encoding="utf-8"),
    )
    (project / "evidence.txt").write_bytes(b"current verified bytes")
    ref = "evidence.txt@" + hashlib.sha256(b"current verified bytes").hexdigest()
    with pytest.raises(decision_signoff_result.SignoffResultError, match=reason):
        decision_signoff_result._require_complete_local_qg(key_dir, rows.format(ref=ref))
