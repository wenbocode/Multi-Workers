"""Prepared preview/observation share one legal pair question and source bytes."""

from __future__ import annotations

import copy
import hashlib
import json
import pathlib

import pytest

import decision
import decision_backends as backends
import decision_book
import decision_playground
import decision_points as dpts
import decision_wire


CASES_DIR = pathlib.Path(__file__).parent / "decide_cases"


def _book(dp_id: str) -> dict:
    book = copy.deepcopy(json.loads((CASES_DIR / f"{dp_id}.json").read_text(encoding="utf-8"))["book"])
    book["notes"] = {
        "evidence": {field: "cmd: fixture-result" for field in dpts.REQUIRED_STATE_FIELDS[dp_id]}
    }
    material = book["material"]
    # The shipped cases use repository references. This independent fixture
    # supplies its own actual source and leaves the business shapes intact.
    if dp_id == "dp-QG":
        material["review_evidence"] = ["evidence.md:1-3"]
    elif dp_id == "dp-gate-approve":
        material["condition_evidence"] = ["evidence.md:1-3"]
    else:
        first = dpts.REQUIRED_STATE_FIELDS[dp_id][0]
        target = material
        parts = first.split(".")
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = "evidence.md:1-3"
    return book


@pytest.mark.parametrize("dp_id", dpts.ACTIVE_DP_IDS)
def test_every_prepared_preview_contains_real_source_and_one_selection(tmp_path, dp_id):
    raw = "Confirmed source fact.\nFailure remains unresolved.\nRuntime remains UNVERIFIED.\n"
    (tmp_path / "evidence.md").write_text(raw, encoding="utf-8")
    book = _book(dp_id)
    state, questions = dpts.prepared_observation_request(
        dp_id, dpts.model_state_for(dp_id, book["material"]), book["preparation"],
        dpts.questions_map(dp_id), project_dir=tmp_path,
    )
    assert list(questions) == [backends.PREPARED_SELECTION_QUESTION_ID]
    assert len(state["evidence_sources"]) == 1
    source = state["evidence_sources"][0]
    assert "Failure remains unresolved." in source["text"]
    assert "Runtime remains UNVERIFIED." in source["text"]
    assert source["sha256"] == hashlib.sha256((tmp_path / "evidence.md").read_bytes()).hexdigest()
    options = backends.prepared_selection_options(dp_id, book["material"], book["preparation"])
    assert set(questions[backends.PREPARED_SELECTION_QUESTION_ID]["labels"]) == set(options)
    for option in options.values():
        if dp_id != "dp-QG" or option["choice"] != "reopen":
            assert not dpts.entry_choice_issues(dp_id, option["choice"], book["material"])
        assert not dpts.basis_selection_issues(
            option["basis_id"], book["preparation"]["basis_catalog"], option["choice"]
        )


def test_book_checks_actual_sources_and_notes_evidence_before_send(tmp_path):
    book = _book("dp-QG")
    (tmp_path / "evidence.md").write_text("fact\nfailed test\nunverified runtime\n", encoding="utf-8")
    book["notes"]["evidence"]["review_findings"] = "details.md:1"
    issues = decision_book.check_book(book, project_dir=tmp_path, repo_root=tmp_path)
    assert any(issue.code == "book-evidence" and "does not exist" in issue.detail for issue in issues)
    (tmp_path / "details.md").write_text("The failing assertion is in scope.\n", encoding="utf-8")
    assert decision_book.check_book(book, project_dir=tmp_path, repo_root=tmp_path) == []
    state, _ = dpts.prepared_observation_request(
        "dp-QG", book["material"], book["preparation"], dpts.questions_map("dp-QG"),
        project_dir=tmp_path, source_references=book["notes"]["evidence"],
    )
    assert any("The failing assertion is in scope." in source["text"] for source in state["evidence_sources"])


def test_playground_preview_matches_transport_and_normalizes_business_answers(tmp_path, monkeypatch):
    (tmp_path / ".agenticdoc").mkdir()
    (tmp_path / ".mw").mkdir()
    api_key = "observation-unit-key"
    (tmp_path / ".mw" / "decide.json").write_text(json.dumps({
        "enabled": True, "api_key": api_key, "max_retries": 0,
    }), encoding="utf-8")
    monkeypatch.setattr(backends, "_auth_json_path", lambda: tmp_path / "missing-auth.json")
    monkeypatch.delenv("TIMI_API_KEY", raising=False)
    (tmp_path / "evidence.md").write_text("fact\nfailed test\nunverified runtime\n", encoding="utf-8")
    book = _book("dp-QG")
    calls = []

    def http_post(url, headers, payload, timeout_s):
        calls.append(copy.deepcopy(payload))
        book["preparation"]["basis_catalog"][0]["id"] = "changed-during-request"
        assert "preparation" not in payload["state"]
        question = payload["questions"][backends.PREPARED_SELECTION_QUESTION_ID]
        selection = "fixA"
        question["criteria"][selection] = "changed-by-backend"
        return backends.HttpResponse(200, "application/json", json.dumps({
            "model": "jev-latest", "answers": {
                backends.PREPARED_SELECTION_QUESTION_ID: {
                    "type": "choice", "choice": selection, "confidence": 0.93,
                },
            },
        }))

    monkeypatch.setattr(backends, "_http_post", http_post)
    playground = decision_playground.DecisionPlayground(tmp_path, warn=lambda line: None)
    preview = playground.validate("dp-QG", book)
    assert preview["ok"], preview["issues"]
    assert calls == []
    actual = playground.submit({
        "dp": "dp-QG", "book": book, "submit_id": "pair-source-test", "observe_only": True,
    })
    assert actual["state"] == "succeeded", actual
    assert calls == [preview["request_preview"]]
    assert actual["answer"]["qg_verdict"]["value"] == "fix"
    assert actual["answer"]["basis_id"]["value"] == "qg-fix"
    events = decision_wire.read_events(tmp_path / ".mw" / "decide-test" / "wire.jsonl").events
    snapshots = [event for event in events if event["kind"] == "book-snapshot"]
    assert len(snapshots) == 1
    captured = json.loads(snapshots[0]["book"]["text"])
    assert captured["state"] == calls[0]["state"]
    assert captured["book"]["preparation"]["basis_catalog"][0]["id"] == "qg-fix"
    assert set(captured["candidates"]) == {backends.PREPARED_SELECTION_QUESTION_ID}


def test_book_budget_counts_prepared_pair_labels_and_hydrated_sources(tmp_path):
    (tmp_path / "evidence.md").write_text("Failure must remain visible.\n" * 30, encoding="utf-8")
    book = _book("dp-QG")
    book["preparation"]["basis_catalog"][0]["text"] = "Required review basis. " * 40
    issues = decision_book.check_book(
        book, project_dir=tmp_path,
        limits={"max_state_plus_question_tokens": 60, "max_total_tokens": 70},
    )
    assert issues and any(issue.code == "book-budget" for issue in issues)


def test_hydrated_source_snapshot_above_default_segment_cap_stays_complete(tmp_path):
    state = {"material": {"review_findings": "observed source facts"}, "evidence_sources": [
        {"path": "large-report.md", "text": "Source evidence line. " * 3000},
    ]}
    scope = decision_wire.production_scope(
        tmp_path, origin="test-prepared-snapshot", dp="dp-QG", decision_id="dp-QG:large-source",
        redact=decision_wire.SubstringRedactor(()),
    )
    capture = dpts._DecisionCapture(intent="answer")
    point = dpts.get_decision_point("dp-QG")
    capture.attach(
        scope, "production-scope", dp_id=point.id, decision_id="dp-QG:large-source",
        questions_version=point.questions_version,
    )
    capture.remember_state(state, questions={backends.PREPARED_SELECTION_QUESTION_ID: {
        "type": "choice", "choices": ["fixA"], "labels": {"fixA": "fix with reported source facts"},
    }}, state_digest=dpts._state_digest(state))
    result = capture.finish(dpts._ArchiveTrace(), outcome=dpts._outcome(
        dp_point=point, trigger=dpts.Trigger(trigger_id="large-source"), status="suggested", mode="suggest",
    ))
    assert result["snapshot_ref"] is not None
    events = decision_wire.read_events(decision_wire.production_wire_sink(tmp_path)).events
    snapshot = next(event for event in events if event["kind"] == "book-snapshot")
    assert snapshot["book"]["stored_len"] > decision_wire.SEGMENT_CAP_BYTES
    assert snapshot["book"]["truncated"] is False
    assert json.loads(snapshot["book"]["text"])["state"] == state
    assert scope.segment_cap == decision_wire.SEGMENT_CAP_BYTES


@pytest.mark.parametrize("dp_id", dpts.ACTIVE_DP_IDS)
def test_active_entries_refuse_business_only_observation_before_transport(tmp_path, monkeypatch, dp_id):
    cfg = decision.DecisionConfig(enabled=True, extras={"api_key": "observation-fixture-key"})
    snapshot = decision.credential_snapshot(cfg, env={}, auth_path=tmp_path / "no-auth.json")
    monkeypatch.setattr(backends, "_auth_json_path", lambda: tmp_path / "no-auth.json")
    root = tmp_path / "test-wire"
    scope = decision_wire.test_scope(
        root, project_id=decision_wire.project_id_for(tmp_path), submission_id="unprepared-observation",
        redact=decision.credential_redactor(cfg, snapshot=snapshot), evidence_path=root / "evidence.jsonl",
        warn=lambda line: None,
    )
    backend = decision.FakeBackend([])
    client = decision.DecisionClient(cfg, backend=backend, wire_scope=scope, credential_snapshot=snapshot)
    result = dpts.decide_for(
        dp_id, dpts.Trigger.from_mapping(_book(dp_id)["material"]), tmp_path,
        client=client, archive=False, intent="answer",
        observation=dpts.Observation(scope=scope, submission_id="unprepared-observation"),
    )
    assert result.status == "escalated"
    assert result.escalated_reason == "input-incomplete"
    assert "require a prepared decision book" in result.detail
    assert backend.calls == []
    assert result.snapshot_ref is None
