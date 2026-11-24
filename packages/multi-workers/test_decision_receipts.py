"""PM receipt continuation at the real writer boundary, with no provider."""

from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

import decision
import decision_lifecycle as ledger
import decision_receipts
import decision_wire


KEY = "receipt-key"
EVENT = "original-receipt"
DECISION = "dp-QG:original-decision"
PAYLOAD = {"decision_id": DECISION, "stage": "executed", "event_id": EVENT, "action": "record"}
CLI = Path(__file__).with_name("mw.py")


def accepted(root, *, key=KEY, task_key=None, role="pm", available=True):
    store = ledger.LifecycleStore.production(root, redact=decision.known_secret_redactor(decision.DecisionConfig()))
    meta = ledger.DecisionMeta(key, DECISION.split(":")[1], role, task_key)
    assert ledger.record_start(store, meta, decision_id=DECISION).recorded
    scope = store._scope(decision_id=DECISION, dp="dp-QG", key=key, task_key=task_key)
    request = decision_wire.request_event(
        scope, logical_id=meta.logical_id, dp="dp-QG", available=available, replayed=False,
        choice="pass" if available else None, basis_id="basis" if available else None,
        basis_text="Evidence passed." if available else None, basis_source="prepared" if available else None,
        prepared_at="2026-11-24T00:00:00Z", basis_catalog_sha256="a" * 64 if available else None,
        business_decisions=int(available), transport_attempts=1, attempts=1,
        reason=None if available else "input-incomplete",
    )
    assert decision_wire.append_event(scope, request).status == "written"
    return store


def receipts(store):
    return [row for row in ledger.read_lifecycle(store).events if row.get("lifecycle") in ("executed", "settled")]


def operate(root, store, **changes):
    return decision_receipts.operate(root, store, KEY, {**PAYLOAD, **changes}, lambda: True)


def test_reopen_as_current_claim_and_reuse_formal_decision(tmp_path, monkeypatch):
    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    store = accepted(tmp_path)
    index = tmp_path / ".agenticdoc" / "_index.parallel"
    index.write_text(f"| {KEY} | active | EXECUTE | {socket.gethostname()}:1 | — | Fixture | now |\n", encoding="utf-8")
    cmd = [sys.executable, "-B", str(CLI), "decide", "receipt", "--project", str(tmp_path), "--key", KEY, "--stdin"]

    def invoke(payload):
        run = subprocess.run(cmd, input=json.dumps(payload), text=True, encoding="utf-8", capture_output=True, timeout=10)
        return json.loads(run.stdout)

    assert invoke(PAYLOAD)["next"]["action"] == "recover-receipt-binding"
    assert not receipts(store)
    index.write_text(f"| {KEY} | active | EXECUTE | {socket.gethostname()}:{os.getpid()} | — | Fixture | now |\n", encoding="utf-8")
    assert invoke({**PAYLOAD, "stage": []})["next"]["field"] == "stage"
    assert invoke({**PAYLOAD, "task_after": {}})["next"]["field"] == "task_after"
    assert invoke(PAYLOAD)["status"] == "written"
    assert invoke(PAYLOAD)["status"] == "duplicate"
    assert invoke({**PAYLOAD, "action": "continue"})["code"] == "event-conflict"
    assert invoke({**PAYLOAD, "check_only": True})["status"] == "duplicate"
    events = ledger.read_lifecycle(store).events
    assert [row["event_id"] for row in receipts(store)] == [EVENT]
    assert sum(row["kind"] == "request" for row in events) == 1


@pytest.mark.parametrize("wrong", [{"key": "another-key"}, {"role": "coding"}, {"available": False}])
def test_foreign_or_unaccepted_decision_cannot_be_resumed(tmp_path, wrong):
    store = accepted(tmp_path, **wrong)
    assert operate(tmp_path, store)["next"]["action"] == "recover-receipt-binding"
    assert not receipts(store)


def test_copied_ledger_does_not_grant_a_binding(tmp_path):
    foreign = accepted(tmp_path / "foreign")
    local = ledger.LifecycleStore.production(tmp_path / "local", redact=foreign.redact)
    local.sink.parent.mkdir(parents=True)
    local.sink.write_bytes(foreign.sink.read_bytes())
    assert operate(tmp_path / "local", local)["next"]["action"] == "recover-receipt-binding"
    assert not receipts(local)


def test_writer_repair_is_bounded_and_resumes_after_valid_correction(tmp_path):
    store = accepted(tmp_path)
    for index, action in enumerate(("bad-first", "bad-second", "bad-third", "bad-fourth")):
        result = operate(tmp_path, store, action=action)
        assert result["consecutive_no_progress"] == index
        assert result["next"]["field"] == "action"
        assert operate(tmp_path, store, action="bad-first")["consecutive_no_progress"] == index
    assert result["status"] == "paused"
    assert operate(tmp_path, store, action="bad-fourth", event_id="switched")["next"]["event_id"] == EVENT
    independent = operate(tmp_path, store, stage="settled", action=None, outcome="ok", event_id="another-stage")
    assert independent["status"] == "written"
    assert operate(tmp_path, store, result=["invalid"])["consecutive_no_progress"] == 0
    assert operate(tmp_path, store)["status"] == "written"
    assert [row["event_id"] for row in receipts(store)] == ["another-stage", EVENT]


def test_unknown_effect_requires_readback_before_retry(tmp_path, monkeypatch):
    store = accepted(tmp_path)
    write = ledger.record_lifecycle
    attempts = []

    def uncertain(*args, **kwargs):
        attempts.append(kwargs["event_id"])
        return ledger.LifecycleResult(kwargs["stage"], "failed")

    monkeypatch.setattr(ledger, "record_lifecycle", uncertain)
    assert operate(tmp_path, store)["next"]["action"] == "reconcile-receipt"
    assert operate(tmp_path, store)["next"]["action"] == "reconcile-receipt"
    assert attempts == [EVENT]
    assert operate(tmp_path, store, check_only=True)["status"] == "not-recorded"
    assert not receipts(store)
    monkeypatch.setattr(ledger, "record_lifecycle", write)
    assert operate(tmp_path, store)["status"] == "written"


def test_timeout_after_write_reads_duplicate_without_resending(tmp_path, monkeypatch):
    store = accepted(tmp_path)
    write = ledger.record_lifecycle

    def uncertain(*args, **kwargs):
        assert write(*args, **kwargs).recorded
        raise TimeoutError("stopped after the ledger write")

    monkeypatch.setattr(ledger, "record_lifecycle", uncertain)
    assert operate(tmp_path, store)["next"]["action"] == "reconcile-receipt"
    assert operate(tmp_path, store, check_only=True)["status"] == "duplicate"
    assert [row["event_id"] for row in receipts(store)] == [EVENT]


def test_lost_claim_at_append_refuses_without_writing(tmp_path):
    store = accepted(tmp_path)
    permissions = iter([True, True, True, False])
    result = decision_receipts.operate(tmp_path, store, KEY, PAYLOAD, lambda: next(permissions))
    assert result["next"]["action"] == "recover-receipt-binding"
    assert not receipts(store)
