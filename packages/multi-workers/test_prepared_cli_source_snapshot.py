"""Real CLI boundary, one paired answer and the exact cited evidence snapshot."""

from __future__ import annotations

import json
import pathlib
import sys
from io import BytesIO

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import decision
import decision_backends
import decision_points
import decide_signoff
import test_dp_consolidation_cli as cli
from test_dp_consolidation_cli import _all_entries_enabled


@pytest.fixture
def isolated_credentials(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    snapshot = decision.credential_snapshot
    monkeypatch.setattr(
        decision,
        "credential_snapshot",
        lambda cfg=None, **_kwargs: snapshot(cfg, env={}, auth_path=tmp_path / "no-auth.json"),
    )
    (tmp_path / ".mw" / "decide.json").write_text(
        json.dumps({"enabled": True, "api_key": "isolated-qg-fixture-key"}), encoding="utf-8"
    )


def test_cli_records_paired_question_and_actual_source_snapshot(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, isolated_credentials,
) -> None:
    report = tmp_path / "review.md"
    report.write_text("# Findings\nF1: FAIL ordering assertion missing\nF2: stale line anchors\n", encoding="utf-8")
    envelope = cli._envelope("dp-QG", "source-snapshot-1")
    envelope["material"]["review_evidence"] = ["review.md:1-3", "review.md:1-3"]
    envelope["material"]["review_findings"] = "F1 and F2 require source repairs; runtime remains unverified."
    envelope["preparation"]["basis_catalog"] = [
        {"id": "complete", "text": "If all applicable checks pass with independent evidence", "material_refs": ["review_requirements"], "applies_to": ["pass"]},
        {"id": "fix-order", "text": "F1 ordering assertion is absent", "material_refs": ["review_findings"], "applies_to": ["fix"]},
        {"id": "fix-both", "text": "F1 and F2 both require repair", "material_refs": ["review_findings"], "applies_to": ["fix"]},
        {"id": "standard-conflict", "text": "If review verifies a substantive conflict in the acceptance standard", "material_refs": ["review_requirements"], "applies_to": ["reopen"]},
    ]
    calls = []
    response_bytes = json.dumps({
        "id": "qg-faux-response", "model": "jev-latest",
        "usage": {"input_tokens": 521, "output_tokens": 11},
        "answers": {"decision_selection": {"type": "choice", "choice": "fixB", "confidence": 0.92}},
    }).encode("utf-8")

    def answer(request, *, timeout):
        assert request.method == "POST" and timeout > 0
        calls.append(request.data)
        payload = json.loads(request.data)
        assert "preparation" not in payload["state"]
        assert "F1: FAIL ordering assertion missing" in payload["state"]["evidence_sources"][0]["text"]
        [question] = payload["questions"].values()
        assert list(question["criteria"]) == ["passA", "fixA", "fixB", "reopenA"]
        assert "F1 and F2 both require repair" in question["criteria"]["fixB"]
        response = BytesIO(response_bytes)
        response.status = 200
        response.headers = {"Content-Type": "application/json"}
        return response

    monkeypatch.setattr(decision_backends.urllib.request, "urlopen", answer)
    rc, out, err = cli._invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope), stdin_flag=True, dp="dp-QG"
    )
    assert rc == 0, (out, err)
    result = json.loads(out)
    assert result["available"] is True, result
    assert result["choice"] == "fix"
    assert result["basis_id"] == "fix-both"
    assert result["transport_attempts"] == 1
    sent_payload = json.loads(calls[0])
    source_dependency = next(item for item in result["file_evidence"] if item["path"] == str(report.resolve()))
    assert source_dependency["sha256"] == sent_payload["state"]["evidence_sources"][0]["sha256"]
    assert result["answers"]["qg_verdict"] == {"value": "fix", "confidence": 0.92}
    assert result["snapshot_ref"]
    assert result["state_digest"] == decision_points._state_digest(sent_payload["state"])
    rows = [json.loads(line) for line in (tmp_path / ".agenticdoc" / "_autopilot" / "decisions-wire.jsonl").read_text(encoding="utf-8").splitlines()]
    snapshots = [row for row in rows if row.get("kind") == "book-snapshot"]
    assert len(snapshots) == 1
    document = json.loads(snapshots[0]["book"]["text"])
    assert document["state"] == sent_payload["state"]
    assert document["local_preparation"] == envelope["preparation"]
    assert set(document["candidates"]) == {decision_backends.PREPARED_SELECTION_QUESTION_ID}
    assert len(document["state"]["evidence_sources"]) == 1
    [start] = [row for row in rows if row.get("kind") == "attempt-start"]
    [end] = [row for row in rows if row.get("kind") == "attempt-end"]
    assert start["call_id"] == end["call_id"] == result["call_id"]
    assert start["attempt_index"] == end["attempt_index"]
    assert start["request"]["text"].encode("utf-8") == calls[0]
    assert end["response"]["text"].encode("utf-8") == response_bytes
    assert end["usage"] == {"input_tokens": 521, "output_tokens": 11}

    receipt_payload = {
        "meta": envelope["meta"], "decision_id": result["decision_id"], "dp": "dp-QG",
        "stage": "consumed", "answer": result["choice"],
        "reason": "Ordering assertion is missing and the source anchors are stale; repair remains open.",
    }
    rc, out, err = cli._invoke(
        "lifecycle", tmp_path, monkeypatch, stdin=json.dumps(receipt_payload), stdin_flag=True,
    )
    assert rc == 0, (out, err)
    assert json.loads(out)["recorded"] is True
    [consumed] = [row for row in cli._lifecycle_events(tmp_path) if row.get("lifecycle") == "consumed"]
    assert consumed["decision_id"] == result["decision_id"]
    assert consumed["event_id"]
    assert not any(row.get("lifecycle") in {"executed", "signoff"} for row in cli._lifecycle_events(tmp_path))
    rc, out, err = cli._invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope), stdin_flag=True, dp="dp-QG"
    )
    assert rc == 0, (out, err)
    assert json.loads(out)["replayed"] is True
    assert len(calls) == 1


def test_missing_cited_source_refuses_before_backend(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, isolated_credentials,
) -> None:
    envelope = cli._envelope("dp-QG", "missing-source-1")
    envelope["material"]["review_evidence"] = ["missing-report.md:1"]
    backend = decision.FakeBackend([])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda _cfg: backend)
    _rc, out, _err = cli._invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope), stdin_flag=True, dp="dp-QG"
    )
    result = json.loads(out)
    assert result["available"] is False
    assert result["reason"] == "input-incomplete"
    assert result["transport_attempts"] == 0
    assert result["issues"]
    assert backend.calls == []


@pytest.mark.parametrize("dp", decision_points.ACTIVE_DP_IDS)
def test_legacy_active_cli_shape_cannot_bypass_preparation(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, isolated_credentials, dp: str,
) -> None:
    legacy = {"state": cli._material(dp)}
    backend = decision.FakeBackend([])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda _cfg: backend)
    rc, out, err = cli._invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(legacy), dp=dp
    )
    assert rc == 2, (out, err)
    result = json.loads(out)
    assert result["available"] is False
    assert result["reason"] == "input-incomplete"
    assert result["issues"][0]["field"] == "preparation"
    assert backend.calls == []


@pytest.mark.parametrize("mutate_source", [False, True])
def test_signoff_binds_file_evidence_and_refuses_a_changed_source(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, isolated_credentials,
    mutate_source: bool,
) -> None:
    project, key_dir = cli._sign_project(tmp_path)
    evidence = project / "proof.md"
    evidence.write_text("All bounded source assertions pass.\n", encoding="utf-8", newline="\n")
    envelope = cli._sign_envelope("file-signoff-1")
    envelope["material"]["verification_evidence"]["verified"] = ["proof.md:1"]

    def answer(state, questions, cfg):
        assert state["evidence_sources"][0]["text"] == "All bounded source assertions pass.\n"
        if mutate_source:
            evidence.write_text("Failure: the checked source has changed.\n", encoding="utf-8", newline="\n")
        return decision.BackendOutcome(
            available=True, reason=None, retryable=False,
            answers={"decision_selection": {"value": "finalizeA", "confidence": 0.93}},
            latency_ms=1, detail="",
        )

    backend = decision.FakeBackend([answer])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda _cfg: backend)
    rc, out, err = cli._invoke(
        "sign", project, monkeypatch, stdin=json.dumps(envelope), stdin_flag=True,
        **cli._sign_args(project, json=True),
    )
    result = json.loads(out)
    assert len(backend.calls) == 1
    assert result["file_evidence"]
    if mutate_source:
        assert rc == 2, (out, err)
        assert "cited file evidence changed" in " ".join(result["problems"])
        assert not decide_signoff.signoff_path(project, cli._SIGN_KEY).exists()
    else:
        assert rc == 0, (out, err)
        assert result["signoff_status"] == "written"
        assert decide_signoff.signoff_path(project, cli._SIGN_KEY).is_file()


def test_sign_missing_source_reports_refusal_without_archive_error(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, isolated_credentials,
) -> None:
    project, _key_dir = cli._sign_project(tmp_path)
    envelope = cli._sign_envelope("missing-file-signoff")
    envelope["material"]["verification_evidence"]["verified"] = ["missing.md:1"]
    backend = decision.FakeBackend([])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda _cfg: backend)
    rc, out, err = cli._invoke(
        "sign", project, monkeypatch, stdin=json.dumps(envelope), stdin_flag=True,
        **cli._sign_args(project, json=True),
    )
    result = json.loads(out)
    assert rc == 2, (out, err)
    assert result["signoff_status"] == "failed"
    assert result["file_evidence"]
    assert "input-incomplete" in " ".join(result["problems"])
    assert not decide_signoff.signoff_path(project, cli._SIGN_KEY).exists()
    assert backend.calls == []
