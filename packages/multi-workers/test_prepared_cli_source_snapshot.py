"""Real CLI boundary, one paired answer and the exact cited evidence snapshot."""

from __future__ import annotations

import json
import pathlib
import sys

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
        json.dumps({"enabled": True}), encoding="utf-8"
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
        {"id": "fix-order", "text": "F1 ordering assertion is absent", "material_refs": ["review_findings"], "applies_to": ["fix"]},
        {"id": "fix-both", "text": "F1 and F2 both require repair", "material_refs": ["review_findings"], "applies_to": ["fix"]},
    ]
    calls = []

    def answer(state, questions, cfg):
        calls.append({"state": state, "questions": questions})
        options = decision_backends.prepared_selection_options(
            "dp-QG", envelope["material"], envelope["preparation"]
        )
        selected = next(key for key, item in options.items() if item["basis_id"] == "fix-both")
        assert set(questions) == {decision_backends.PREPARED_SELECTION_QUESTION_ID}
        assert "F1: FAIL ordering assertion missing" in state["evidence_sources"][0]["text"]
        return decision.BackendOutcome(
            available=True, reason=None, retryable=False,
            answers={decision_backends.PREPARED_SELECTION_QUESTION_ID: {"value": selected, "confidence": 0.92}},
            latency_ms=2, detail="",
        )

    backend = decision.FakeBackend([answer])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda _cfg: backend)
    rc, out, err = cli._invoke(
        "run", tmp_path, monkeypatch, stdin=json.dumps(envelope), stdin_flag=True, dp="dp-QG"
    )
    assert rc == 0, (out, err)
    result = json.loads(out)
    assert result["available"] is True, result
    assert result["choice"] == "fix"
    assert result["basis_id"] == "fix-both"
    source_dependency = next(item for item in result["file_evidence"] if item["path"] == str(report.resolve()))
    assert source_dependency["sha256"] == calls[0]["state"]["evidence_sources"][0]["sha256"]
    assert result["answers"]["qg_verdict"] == {"value": "fix", "confidence": 0.92}
    assert result["snapshot_ref"]
    assert result["state_digest"] == decision_points._state_digest(calls[0]["state"])
    rows = [json.loads(line) for line in (tmp_path / ".agenticdoc" / "_autopilot" / "decisions-wire.jsonl").read_text(encoding="utf-8").splitlines()]
    snapshots = [row for row in rows if row.get("kind") == "book-snapshot"]
    assert len(snapshots) == 1
    document = json.loads(snapshots[0]["book"]["text"])
    assert document["state"] == calls[0]["state"]
    assert set(document["candidates"]) == {decision_backends.PREPARED_SELECTION_QUESTION_ID}
    assert len(document["state"]["evidence_sources"]) == 1
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
