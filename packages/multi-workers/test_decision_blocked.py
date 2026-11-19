"""Receipts correlate rejected requests without recording their inputs."""

import argparse
import io
import json
from types import SimpleNamespace

import decision_blocked
import mw


def _receipts(project):
    directory = project / ".agenticdoc" / "_autopilot" / "dp-blocked"
    return {path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in directory.glob("*.json")}


def test_repeated_unbound_requests_have_distinct_correlated_receipts(tmp_path, monkeypatch, capsys):
    meta = SimpleNamespace(key="demo", task_key="review", logical_id="attempt-7")
    monkeypatch.setattr(
        mw, "_decide_actor_binding",
        lambda *_: (None, "actor-unbound", "the key row is not active"),
    )
    ids = []
    for _ in range(2):
        outcome = mw._decide_run_prepared(
            argparse.Namespace(json=True), tmp_path, dp="dp-QG",
            material={"marker": "caller material"}, preparation={}, context=None,
            meta=meta, parent_ref=None,
        )
        assert outcome == 2
        ids.append(json.loads(capsys.readouterr().out)["blocked_event_id"])
    records = _receipts(tmp_path)
    assert len(set(ids)) == len(records) == 2
    for event_id in ids:
        event = records[event_id]
        assert (event["event_id"], event["key"], event["task_key"], event["logical_id"]) == (
            event_id, "demo", "review", "attempt-7",
        )
        assert (event["dp"], event["stage"], event["reason"], event["detail"]) == (
            "dp-QG", "identity-check", "actor-unbound", "the key row is not active",
        )
        assert event["ts"]
        assert "caller material" not in json.dumps(event)


def test_bad_json_and_gate_refusal_are_traceable(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(mw.sys, "stdin", io.StringIO("{bad"))
    assert mw._decide_run_versioned(argparse.Namespace(dp_id="dp-QG"), tmp_path) == 2
    assert "request is not valid JSON" in capsys.readouterr().err

    def refuse(*args, **kwargs):
        raise mw._ap_conductor.gate_effects.GateBlocked("current approval claim is missing")

    monkeypatch.setattr(mw._ap_conductor, "consume_pm_gate", refuse)
    args = argparse.Namespace(gate_action="consume", key="demo", gate_id="g-123")
    assert mw._ap_gate(args, tmp_path) == 2
    records = sorted(_receipts(tmp_path).values(), key=lambda event: event["source"])
    gate, cli = records
    assert (gate["gate_id"], gate["stage"], gate["detail"]) == (
        "g-123", "consume", "current approval claim is missing",
    )
    assert (cli["stage"], cli["detail"]) == ("input-validation", "request is not valid JSON")


def test_receipt_redacts_diagnostics_and_preserves_refusal_on_write_error(tmp_path, monkeypatch, capsys):
    secret = "synthetic-project-audit-secret-773"
    monkeypatch.setenv("TEST_DP_AUDIT_API_KEY", secret)
    result = {"dp": "dp-QG", "reason": "input-incomplete", "detail": f"rejected {secret}"}
    event_id = decision_blocked.record(tmp_path, source="mw-decide-run", stage="request", result=result)
    assert _receipts(tmp_path)[event_id]["detail"] == "rejected <redacted>"

    project_file = tmp_path / "not-a-directory"
    project_file.touch()
    assert decision_blocked.record(project_file, source="mw-decide-run", stage="request", result=result) is None
    assert "could not record DP block" in capsys.readouterr().err
