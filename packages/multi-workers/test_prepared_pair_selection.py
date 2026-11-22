"""Hermetic regression of the one-question prepared transport for all DPs."""

from __future__ import annotations

import copy
import json
import pathlib
from io import BytesIO

import pytest

import decision
import decision_backends as backends
import decision_points as points
import decision_wire


PACKAGE = pathlib.Path(__file__).resolve().parent
ROOT = PACKAGE.parents[1]


def case(dp: str) -> dict:
    return json.loads((PACKAGE / "decide_cases" / f"{dp}.json").read_text(encoding="utf-8"))["book"]


@pytest.fixture(autouse=True)
def no_network_or_auth_discovery(monkeypatch):
    monkeypatch.setattr(backends, "resolve_timi_api_key", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        backends.urllib.request,
        "urlopen",
        lambda *args, **kwargs: pytest.fail("no real network allowed"),
    )


@pytest.mark.parametrize("dp", points.ACTIVE_DP_IDS)
def test_all_prepared_entries_send_one_pair_and_normalize_business_result(dp, monkeypatch, tmp_path):
    book = case(dp)
    material, preparation = book["material"], book["preparation"]
    calls = []
    options = backends.prepared_selection_options(dp, material, preparation)
    selected_id = "fixA" if dp == "dp-QG" else next(iter(options))
    selected = options[selected_id]

    response_bytes = json.dumps({
        "model": "jev-latest",
        "answers": {
            "decision_selection": {
                "type": "choice", "choice": selected_id, "confidence": 0.87,
                "probabilities": {selected_id: 0.87},
            }
        },
    }).encode("utf-8")

    def open_fixture(request, *, timeout):
        assert request.method == "POST" and timeout > 0
        calls.append(request.data)
        payload = json.loads(request.data)
        assert set(payload["questions"]) == {"decision_selection"}
        assert payload["questions"]["decision_selection"]["criteria"] == {
            option_id: option["label"] for option_id, option in options.items()
        }
        response = BytesIO(response_bytes)
        response.status = 200
        response.headers = {"Content-Type": "application/json"}
        return response

    monkeypatch.setattr(backends.urllib.request, "urlopen", open_fixture)
    api_key = "pair-fixture-key-0123456789"
    cfg = decision.DecisionConfig(
        enabled=True, project_root=ROOT, max_questions=1,
        evidence_path=str(tmp_path / "evidence.jsonl"),
        extras={"api_key": api_key},
    )
    scope = decision_wire.test_scope(
        tmp_path, project_id=decision_wire.project_id_for(tmp_path), submission_id=f"pair-{dp}",
        redact=decision_wire.SubstringRedactor([api_key]), evidence_path=tmp_path / "evidence.jsonl",
    )
    client = decision.DecisionClient(cfg, wire_scope=scope)
    result = client.request_prepared(
        dp, material, preparation, actor_role=book["meta"]["actor_role"]
    )
    assert result["available"], result
    assert result["business_decisions"] == result["transport_attempts"] == 1
    assert len(calls) == 1
    payload = json.loads(calls[0])
    assert "preparation" not in payload["state"]
    assert b"prepared_at" not in calls[0]
    assert client.last_prepared_preparation == preparation
    assert result["choice"] == selected["choice"]
    assert result["basis_id"] == selected["basis_id"]
    business_qid = next(iter(points.questions_map(dp)))
    assert result["answers"] == {
        business_qid: {"value": selected["choice"], "confidence": 0.87},
        "basis_id": {"value": selected["basis_id"], "confidence": 0.87},
    }
    assert client.last_prepared_questions == backends.build_prepared_questions(dp, material, preparation)
    assert client.last_prepared_state == payload["state"]
    events = decision_wire.read_events(scope.sink).events
    [sent] = [event for event in events if event["kind"] == "attempt-start"]
    [received] = [event for event in events if event["kind"] == "attempt-end"]
    assert sent["call_id"] == received["call_id"] == client.last_call_id
    assert sent["attempt_index"] == received["attempt_index"] == 1
    assert sent["request"]["text"].encode("utf-8") == calls[0]
    assert received["response"]["text"].encode("utf-8") == response_bytes
    raw = json.loads((tmp_path / "evidence.jsonl").read_text(encoding="utf-8"))
    assert raw["answers"] == {"decision_selection": {"value": selected_id, "confidence": 0.87}}


def test_distinct_repair_reasons_have_distinct_fix_options():
    book = case("dp-QG")
    book["preparation"]["basis_catalog"].append({
        "id": "print-and-matrix",
        "text": "F1: print ordering assertion missing; F2: matrix anchors are stale",
        "material_refs": ["review_findings"],
        "applies_to": ["fix"],
    })
    options = backends.prepared_selection_options("dp-QG", book["material"], book["preparation"])
    assert list(options) == ["passA", "fixA", "fixB", "reopenA"]
    assert options["fixA"]["basis_id"] == "qg-fix"
    assert options["fixB"]["basis_id"] == "print-and-matrix"
    assert "F1" in options["fixB"]["label"] and "F2" in options["fixB"]["label"]


def test_qg_criteria_keep_all_branches_and_only_applied_bases():
    book = case("dp-QG")
    book["preparation"]["basis_catalog"] = [
        {"id": "source-pass", "text": "local repairs pass", "material_refs": ["review_findings"], "applies_to": ["pass"]},
        {"id": "p2-fix", "text": "two P2 need repair", "material_refs": ["review_findings"], "applies_to": ["fix"]},
        {"id": "scope", "text": "runtime not verified", "material_refs": ["uncovered_scope"], "applies_to": ["pass", "fix", "reopen"]},
    ]
    options = backends.prepared_selection_options("dp-QG", book["material"], book["preparation"])
    pairs = {(item["choice"], item["basis_id"]) for item in options.values()}
    assert pairs == {("pass", "source-pass"), ("pass", "scope"), ("fix", "p2-fix"), ("fix", "scope"), ("reopen", "scope")}
    book["material"]["basis_issue"] = "The acceptance standard contradicts the approved goal"
    changed = backends.prepared_selection_options("dp-QG", book["material"], book["preparation"])
    assert changed == options


def test_qg_without_reopen_criterion_refuses_before_transport():
    book = case("dp-QG")
    book["preparation"]["basis_catalog"].pop()
    backend = decision.FakeBackend([])
    client = decision.DecisionClient(decision.DecisionConfig(enabled=True), backend)
    result = client.request_prepared("dp-QG", book["material"], book["preparation"], actor_role="pm")
    assert not result["available"] and result["reason"] == "input-incomplete"
    assert "missing prepared criteria for reopen" in result["issues"][0]["issue"]
    assert result["business_decisions"] == 0 and backend.calls == []


@pytest.mark.parametrize("wire, basis_issue", [("reopenA", None), ("passA", "The accepted requirement contradicts the goal")])
def test_qg_selection_does_not_bypass_substantive_basis_check(wire, basis_issue, tmp_path):
    book = case("dp-QG")
    if basis_issue:
        book["material"]["basis_issue"] = basis_issue
    backend = decision.FakeBackend([decision.BackendOutcome(
        True, None, False, {"decision_selection": {"value": wire, "confidence": 0.91}}, 1,
    )])
    client = decision.DecisionClient(
        decision.DecisionConfig(enabled=True, project_root=ROOT, evidence_path=str(tmp_path / "transport.jsonl")),
        backend,
    )
    result = client.request_prepared("dp-QG", book["material"], book["preparation"], actor_role="pm")
    assert result["reason"] == "bad-response" and result["business_decisions"] == 0
    assert result["issues"][0]["field"] == "basis_issue"
    assert len(backend.calls) == 1


@pytest.mark.parametrize("answer", [None, {}, {"qg_verdict": {"value": "fix"}, "basis_id": {"value": "qg-fix"}}, {"decision_selection": {"value": "fixZ"}}])
def test_decoder_refuses_missing_old_or_unknown_selection(answer):
    book = case("dp-QG")
    with pytest.raises(ValueError):
        backends.decode_prepared_selection("dp-QG", book["material"], book["preparation"], answer)


def test_dynamic_candidate_ids_do_not_become_wire_identifiers():
    book = case("dp-auto")
    previous = book["material"]["handling_options"][0]["id"]
    book["material"]["handling_options"][0]["id"] = "自定义/候选:one"
    for item in book["preparation"]["basis_catalog"]:
        item["applies_to"] = ["自定义/候选:one" if value == previous else value for value in item["applies_to"]]
    options = backends.prepared_selection_options("dp-auto", book["material"], book["preparation"])
    assert list(options) == ["optionA", "optionB", "optionC"]
    decoded = backends.decode_prepared_selection(
        "dp-auto", book["material"], book["preparation"],
        {"decision_selection": {"value": "optionA", "confidence": 0.8}},
    )
    assert decoded["handling"]["value"] == "自定义/候选:one"


@pytest.mark.parametrize("duplicated", [True, False])
def test_dp_auto_rejects_oversized_or_renamed_duplicate_paths_before_transport(duplicated):
    book = case("dp-auto")
    options = book["material"]["handling_options"]
    if duplicated:
        options[1] = dict(options[0], id=options[1]["id"], label=options[1]["label"])
        expected = "duplicates the action"
    else:
        for i in range(3):
            options.append(dict(options[0], id=f"new-path-{i}", label=f"Path {i}", description=f"Action {i}"))
        expected = "distinguishable prepared candidates"
    backend = decision.FakeBackend([])
    client = decision.DecisionClient(decision.DecisionConfig(enabled=True), backend=backend)
    result = client.request_prepared("dp-auto", book["material"], book["preparation"], actor_role="pm")
    assert result["reason"] == "input-incomplete"
    assert any(expected in issue["issue"] for issue in result["issues"])
    assert result["transport_attempts"] == 0 and backend.calls == []


def test_catalog_beyond_26_reasons_has_stable_unique_ids():
    book = case("dp-QG")
    primary = book["preparation"]["basis_catalog"][0]
    book["preparation"]["basis_catalog"] = [
        *(dict(primary, id=f"basis-{index}") for index in range(28)),
        *book["preparation"]["basis_catalog"][1:],
    ]
    options = backends.prepared_selection_options("dp-QG", book["material"], book["preparation"])
    assert [identifier for identifier in options if identifier.startswith("fix")][-2:] == ["fixAA", "fixAB"]
    assert options == backends.prepared_selection_options("dp-QG", book["material"], book["preparation"])


def test_observation_text_edits_use_same_pair_renderer():
    book = case("dp-QG")
    questions = backends.build_prepared_questions(
        "dp-QG", book["material"], book["preparation"],
        business_questions={"qg_verdict": {"instructions": "Edited review instruction", "criteria": {"fix": "Edited fix criterion"}}},
    )
    question = questions["decision_selection"]
    assert "Edited review instruction" in question["instructions"]
    assert "Edited fix criterion" in question["labels"]["fixA"]
    assert book["preparation"]["basis_catalog"][0]["text"] in question["labels"]["fixA"]


def test_unknown_pair_is_refused_after_one_call_without_default(tmp_path):
    book = case("dp-QG")
    fake = decision.FakeBackend([decision.BackendOutcome(
        available=True, reason=None, retryable=False,
        answers={"decision_selection": {"value": "fixZ", "confidence": 0.9}}, latency_ms=1,
    )])
    cfg = decision.DecisionConfig(enabled=True, project_root=ROOT, evidence_path=str(tmp_path / "evidence.jsonl"))
    result = decision.DecisionClient(cfg, backend=fake).request_prepared(
        "dp-QG", book["material"], book["preparation"], actor_role="pm"
    )
    assert not result["available"] and result["reason"] == "bad-response"
    assert result["choice"] is result["basis_id"] is None
    assert result["business_decisions"] == 0 and len(fake.calls) == 1


def test_prepared_snapshot_is_reset_on_invalid_next_call():
    book = case("dp-QG")
    client = decision.DecisionClient(decision.DecisionConfig(enabled=True, project_root=ROOT))
    client.last_prepared_state = {"previous": "state"}
    client.last_prepared_questions = {"previous": "question"}
    client.last_prepared_preparation = {"previous": "preparation"}
    client.last_file_evidence = [{"path": "previous.txt", "sha256": None}]
    result = client.request_prepared("dp-QG", {}, book["preparation"], actor_role="pm")
    assert not result["available"]
    assert client.last_prepared_state is client.last_prepared_questions is None
    assert client.last_prepared_preparation is None
    assert client.last_file_evidence == []


def test_catalog_reordering_during_call_cannot_remap_the_selected_pair(tmp_path):
    book = case("dp-QG")
    preparation = book["preparation"]
    original_basis = copy.deepcopy(preparation["basis_catalog"][0])
    original_stamp = preparation["prepared_at"]
    preparation["basis_catalog"].append(dict(original_basis, id="second-repair", text="A different repair"))

    def mutate(state, questions, cfg):
        assert questions["decision_selection"]["choices"] == ["passA", "fixA", "fixB", "reopenA"]
        preparation["basis_catalog"].reverse()
        preparation["prepared_at"] = "2026-11-16T12:00:00Z"
        assert "preparation" not in state
        questions["decision_selection"]["labels"]["fixA"] = "Mutated after send"
        return decision.BackendOutcome(True, None, False, {
            "decision_selection": {"value": "fixA", "confidence": 0.91}
        }, 1)

    client = decision.DecisionClient(
        decision.DecisionConfig(enabled=True, project_root=ROOT, evidence_path=str(tmp_path / "transport.jsonl")),
        decision.FakeBackend([mutate]),
    )
    result = client.request_prepared("dp-QG", book["material"], preparation, actor_role="pm")
    assert result["available"], result
    assert result["basis_id"] == original_basis["id"]
    assert result["basis_text"] == original_basis["text"]
    assert result["prepared_at"] == original_stamp
    assert client.last_prepared_preparation["basis_catalog"][0] == original_basis
    assert original_basis["text"] in client.last_prepared_questions["decision_selection"]["labels"]["fixA"]
