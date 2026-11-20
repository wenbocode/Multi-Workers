"""Direct Python replay and sign-off consumers refuse stale cited files."""

from __future__ import annotations

import json
import pathlib

import pytest

import decision
import decision_signoff_result
import test_dp_consolidation_cli as cli
from test_dp_consolidation_cli import _all_entries_enabled


@pytest.fixture
def isolated_client(tmp_path, monkeypatch):
    snapshot = decision.credential_snapshot
    monkeypatch.setattr(decision, "credential_snapshot", lambda cfg=None, **_kwargs: snapshot(
        cfg, env={}, auth_path=tmp_path / "no-auth.json"
    ))
    (tmp_path / ".mw" / "decide.json").write_text(json.dumps({"enabled": True}), encoding="utf-8")
    calls = []

    def answer(state, questions, cfg):
        calls.append(state)
        selected = questions["decision_selection"]["choices"][0]
        return decision.BackendOutcome(True, None, False, {
            "decision_selection": {"value": selected, "confidence": 0.94}
        }, 1)

    backend = decision.FakeBackend(default=answer)
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda _cfg: backend)
    return calls


def test_same_logical_id_unchanged_source_replays_without_model(tmp_path, monkeypatch, isolated_client):
    path = tmp_path / "review.md"
    path.write_text("Source reviewed; missing assertion requires fix.\n", encoding="utf-8")
    envelope = cli._envelope("dp-QG", "fresh-replay")
    envelope["material"]["review_evidence"] = ["review.md:1"]
    for _ in range(2):
        rc, out, err = cli._invoke("run", tmp_path, monkeypatch, stdin=json.dumps(envelope), stdin_flag=True, dp="dp-QG")
        assert rc == 0, (out, err)
        assert json.loads(out)["available"]
    assert json.loads(out)["replayed"]
    assert len(isolated_client) == 1


def test_same_logical_id_changed_source_is_stale_without_resend(tmp_path, monkeypatch, isolated_client):
    path = tmp_path / "review.md"
    path.write_text("Original review\n", encoding="utf-8")
    envelope = cli._envelope("dp-QG", "stale-replay")
    envelope["material"]["review_evidence"] = ["review.md:1"]
    rc, out, err = cli._invoke("run", tmp_path, monkeypatch, stdin=json.dumps(envelope), stdin_flag=True, dp="dp-QG")
    assert rc == 0 and json.loads(out)["available"], (out, err)
    ledger = tmp_path / ".agenticdoc" / "_autopilot" / "decisions-wire.jsonl"
    preserved = ledger.read_bytes()
    path.write_text("FAILED: new issue after that judgment\n", encoding="utf-8")
    rc, out, err = cli._invoke("run", tmp_path, monkeypatch, stdin=json.dumps(envelope), stdin_flag=True, dp="dp-QG")
    result = json.loads(out)
    assert rc == 0 and not result["available"], (out, err)
    assert result["replayed"] and result["attempts"] == 0
    assert result["business_decisions"] == 0 and result["choice"] is None
    assert "new logical_id" in result["detail"]
    assert ledger.read_bytes() == preserved
    assert len(isolated_client) == 1


def test_signoff_consumer_invalidates_source_changed_after_signing(tmp_path, monkeypatch, isolated_client):
    project, key_dir = cli._sign_project(tmp_path)
    source = project / "proof.md"
    source.write_text("All original bounded checks passed.\n", encoding="utf-8")
    envelope = cli._sign_envelope("consumer-freshness")
    material = envelope["material"]
    material["verification_evidence"]["verified"] = ["proof.md:1"]
    rc, out, err = cli._invoke("sign", project, monkeypatch, stdin=json.dumps(envelope), stdin_flag=True,
                               **cli._sign_args(project, json=True))
    assert rc == 0, (out, err)
    before = decision_signoff_result.validate_signoff(key_dir, cli._SIGN_KEY)
    assert before.valid, before.reason
    assert decision_signoff_result.validate_key_signoff(
        key_dir, cli._SIGN_KEY, material, material["verification_evidence"]
    ).signs_key
    source.write_text("FAIL: the cited checks are no longer the same.\n", encoding="utf-8")
    after = decision_signoff_result.validate_signoff(key_dir, cli._SIGN_KEY)
    assert not after.valid and "cited file evidence changed" in after.reason
    typed = decision_signoff_result.validate_key_signoff(
        key_dir, cli._SIGN_KEY, material, material["verification_evidence"]
    )
    assert not typed.valid and not typed.signs_key
    assert len(isolated_client) == 1
