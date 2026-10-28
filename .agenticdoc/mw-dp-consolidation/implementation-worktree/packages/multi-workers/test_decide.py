"""test_decide.py — T-01a: decision-client core (contract / budget / fail-soft).

Hermetic pytest suite for ``packages/multi-workers/decision.py`` (key
mw-jev-provider-integration). Everything runs under ``tmp_path`` with
``monkeypatch``; all file I/O is explicitly utf-8. The transport backends
(T-01b) are replaced by :class:`decision.FakeBackend`, so no network or
credential is ever touched.

Contract sources: design.md D-003 (response/reason), D-004 (budgets, retry,
fail-soft), D-005 (evidence line), D-007 (`.mw/decide.json`).
"""

from __future__ import annotations

import collections.abc
import json
import pathlib
import sys
import typing

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402
import decision  # noqa: E402

EVIDENCE_KEYS = [
    "ts",
    "dp",
    "transport",
    "model",
    "attempts",
    "latency_ms",
    "available",
    "reason",
    "answers",
    "confidence",
    "confidence_source",
]
RESPONSE_KEYS = [
    "available",
    "transport",
    "model",
    "confidence_source",
    "attempts",
    "latency_ms",
    "answers",
    "reason",
]

CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
)


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # Never let the guarded default resolver build a real (network) backend.
    monkeypatch.setattr(decision, "_imported_backend_factory", lambda cfg: None)
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", None)


class FakeClock:
    """Deterministic monotonic clock; ``sleep`` advances it."""

    def __init__(self, start: float = 0.0) -> None:
        self.t = float(start)
        self.sleeps: list[float] = []

    def __call__(self) -> float:
        return self.t

    def advance(self, delta: float) -> None:
        self.t += float(delta)

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(float(seconds))
        self.advance(seconds)


def ok(answers: dict | None = None, *, confidence: float | None = 0.8, detail: str = "") -> dict:
    if answers is None:
        answers = {}
    return {
        "available": True,
        "reason": None,
        "retryable": False,
        "answers": answers,
        "latency_ms": 5,
        "detail": detail,
    }


def fail(reason: str, *, retryable: bool = False, detail: str = "") -> dict:
    return {
        "available": False,
        "reason": reason,
        "retryable": retryable,
        "answers": None,
        "latency_ms": 3,
        "detail": detail,
    }


def answer(value, confidence: float | None = 0.8) -> dict:
    return {"value": value, "confidence": confidence}


def capture_emit_details(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Record the ``detail`` argument of every ``_emit`` call.

    The response dict has no ``detail`` field (frozen 8-field contract), so the
    only way to assert that a budget refusal names its numbers is to spy on the
    internal emit call.
    """
    details: list[object] = []
    original = decision.DecisionClient._emit

    def wrapper(
        self,
        dp,
        start,
        available,
        reason,
        attempts,
        answers,
        detail,
        transport,
        confidence_source,
        backend=None,
    ):
        details.append(detail)
        return original(
            self,
            dp,
            start,
            available,
            reason,
            attempts,
            answers,
            detail,
            transport,
            confidence_source,
            backend,
        )

    monkeypatch.setattr(decision.DecisionClient, "_emit", wrapper)
    return details


def make_client(
    tmp_path: pathlib.Path,
    backend: decision.FakeBackend | None = None,
    *,
    clock: FakeClock | None = None,
    **cfg_kwargs,
) -> decision.DecisionClient:
    cfg_kwargs.setdefault("enabled", True)
    cfg = decision.DecisionConfig(project_root=tmp_path, **cfg_kwargs)
    clock = clock or FakeClock()
    return decision.DecisionClient(cfg, backend, clock=clock, sleep=clock.sleep)


def evidence_lines(root: pathlib.Path) -> list[dict]:
    path = root / ".agenticdoc" / "_autopilot" / "triage-decisions.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


CHOICE_Q = {"q": {"type": "choice", "choices": ["a", "b"]}}


# ---------------------------------------------------------------------------
# Contract (D-003): response shape, answer normalisation, confidence_source.
# ---------------------------------------------------------------------------


def test_success_response_has_exact_contract_fields(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a", 0.7)})], model="fake-model")
    client = make_client(tmp_path, backend)
    result = client.decide("state text", CHOICE_Q)
    assert list(result.keys()) == RESPONSE_KEYS
    assert result == {
        "available": True,
        "transport": "fake",
        "model": "fake-model",
        "confidence_source": "model-self-report",
        "attempts": 1,
        "latency_ms": 0,
        "answers": {"q": {"value": "a", "confidence": 0.7}},
        "reason": None,
    }


def test_success_reason_is_always_none(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["reason"] is None


def test_confidence_source_api_is_propagated_verbatim(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend(
        [ok({"q": answer("a")})], name="timi-decisions", confidence_source="api"
    )
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["confidence_source"] == "api"
    assert result["transport"] == "timi-decisions"


def test_model_self_report_is_never_presented_as_api(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a")})], confidence_source="model-self-report")
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["confidence_source"] == "model-self-report"
    assert result["confidence_source"] != "api"


def test_unknown_backend_confidence_source_is_not_fabricated(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a")})], name="mystery")
    del backend.confidence_source  # backend does not declare a source
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["confidence_source"] == "unknown"


def test_answers_are_filtered_to_requested_ids_and_confidence_clamped(
    tmp_path: pathlib.Path,
) -> None:
    backend = decision.FakeBackend(
        [ok({"q": answer("a", 2.5), "extra": answer("x"), "q2": answer(1, -3)})]
    )
    questions = {"q": {"type": "choice", "choices": ["a"]}, "q2": {"type": "noul"}}
    result = make_client(tmp_path, backend).decide("s", questions)
    assert set(result["answers"]) == {"q", "q2"}
    assert result["answers"]["q"]["confidence"] == 1.0
    assert result["answers"]["q2"]["confidence"] == 0.0


def test_non_numeric_confidence_becomes_none(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": {"value": "a", "confidence": "high"}})])
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["answers"]["q"]["confidence"] is None


# ---------------------------------------------------------------------------
# Question validation (card requirement 6).
# ---------------------------------------------------------------------------


def test_all_wave1_question_types_accepted(tmp_path: pathlib.Path) -> None:
    questions = {
        "q_choice": {"type": "choice", "choices": ["a", "b"]},
        "q_score": {"type": "score", "min": 0, "max": 10},
        "q_noul": {"type": "noul"},
    }
    backend = decision.FakeBackend(
        [ok({qid: answer(1) for qid in questions})]
    )
    result = make_client(tmp_path, backend).decide("s", questions)
    assert result["available"] is True
    assert set(result["answers"]) == set(questions)


def test_box_type_is_forwarded_to_backend(tmp_path: pathlib.Path) -> None:
    """'box' is known but unsupported; T-01b answers unsupported-question-type."""
    backend = decision.FakeBackend([fail("unsupported-question-type")])
    result = make_client(tmp_path, backend).decide(
        "s", {"q": {"type": "box", "properties": {}}}
    )
    assert result["available"] is False
    assert result["reason"] == "unsupported-question-type"
    assert len(backend.calls) == 1


@pytest.mark.parametrize(
    "questions",
    [
        {"q": {"type": "textarea"}},
        {"q": {"type": "choice"}},
        {"q": {"type": "choice", "choices": []}},
        {"q": {"type": "score", "min": 0}},
        {"q": {"type": "score", "min": "0", "max": 5}},
        {"q": {"type": "score", "min": 5, "max": 1}},
        {"q": "not-an-object"},
        {"q": {"type": "noul"}, "q2": {"type": "noul"}, "q3": {"type": "noul"}},
    ],
)
def test_invalid_questions_raise_input_error(tmp_path: pathlib.Path, questions: dict) -> None:
    backend = decision.FakeBackend([ok({})])
    client = make_client(tmp_path, backend, max_questions=2)
    with pytest.raises(decision.DecisionInputError):
        client.decide("s", questions)
    assert backend.calls == [], "invalid input must not reach the backend"


def test_empty_questions_is_input_error(tmp_path: pathlib.Path) -> None:
    with pytest.raises(decision.DecisionInputError):
        make_client(tmp_path, decision.FakeBackend([ok({})])).decide("s", {})


def test_non_mapping_questions_is_input_error(tmp_path: pathlib.Path) -> None:
    with pytest.raises(decision.DecisionInputError):
        make_client(tmp_path, decision.FakeBackend([ok({})])).decide("s", ["q"])


def test_state_none_is_input_error(tmp_path: pathlib.Path) -> None:
    with pytest.raises(decision.DecisionInputError):
        make_client(tmp_path, decision.FakeBackend([ok({})])).decide(None, CHOICE_Q)


def test_question_id_must_be_non_empty_string(tmp_path: pathlib.Path) -> None:
    with pytest.raises(decision.DecisionInputError):
        make_client(tmp_path, decision.FakeBackend([ok({})])).decide("s", {"": {"type": "noul"}})


# ---------------------------------------------------------------------------
# FIX-R: real input annotations + two extra fail-loud validation rules.
# ---------------------------------------------------------------------------


def test_decide_accepts_text_and_mapping_state(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a")}), ok({"q": answer("a")})])
    client = make_client(tmp_path, backend)
    assert client.decide("plain text state", CHOICE_Q)["available"] is True
    mapping_state = {"candidates": ["a", "b"]}
    assert client.decide(mapping_state, CHOICE_Q)["available"] is True
    assert [call["state"] for call in backend.calls] == ["plain text state", mapping_state]


def test_noul_criteria_exactly_true_false_is_accepted(tmp_path: pathlib.Path) -> None:
    questions = {
        "q": {
            "type": "noul",
            "criteria": {"true": "no useful output", "false": "usable output"},
        }
    }
    backend = decision.FakeBackend([ok({"q": answer(0.9)})])
    result = make_client(tmp_path, backend).decide("s", questions)
    assert result["available"] is True
    assert len(backend.calls) == 1


def test_noul_criteria_with_other_keys_is_input_error(tmp_path: pathlib.Path) -> None:
    questions = {"q": {"type": "noul", "criteria": {"yes": "no useful output", "false": "usable"}}}
    backend = decision.FakeBackend([ok({})])
    with pytest.raises(decision.DecisionInputError) as excinfo:
        make_client(tmp_path, backend).decide("s", questions)
    assert "criteria must be exactly {true, false}" in str(excinfo.value)
    assert backend.calls == [], "invalid input must not reach the backend"


def test_noul_criteria_with_blank_value_is_input_error(tmp_path: pathlib.Path) -> None:
    questions = {"q": {"type": "noul", "criteria": {"true": "   ", "false": "usable"}}}
    backend = decision.FakeBackend([ok({})])
    with pytest.raises(decision.DecisionInputError):
        make_client(tmp_path, backend).decide("s", questions)
    assert backend.calls == []


def test_choice_labels_with_static_choices_is_accepted(tmp_path: pathlib.Path) -> None:
    questions = {
        "q": {"type": "choice", "choices": ["a", "b"], "labels": {"a": "Alpha", "b": "Beta"}}
    }
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    result = make_client(tmp_path, backend).decide("s", questions)
    assert result["available"] is True
    assert len(backend.calls) == 1


def test_choice_labels_with_dynamic_choices_is_input_error(tmp_path: pathlib.Path) -> None:
    questions = {
        "q": {"type": "choice", "dynamic_choices": "candidates", "labels": {"c1": "a.md"}}
    }
    backend = decision.FakeBackend([ok({})])
    with pytest.raises(decision.DecisionInputError) as excinfo:
        make_client(tmp_path, backend).decide("s", questions)
    message = str(excinfo.value)
    assert "'labels'" in message and "'dynamic_choices'" in message
    assert backend.calls == [], "invalid input must not reach the backend"


def test_decide_input_annotations_are_not_bare_object_or_dict() -> None:
    """Guard the FIX-R contract: the annotations must stay real types."""
    hints = typing.get_type_hints(decision.DecisionClient.decide)
    assert hints["state"] is not object
    assert hints["questions"] is not dict

    state_origins = {typing.get_origin(arg) for arg in typing.get_args(hints["state"])}
    assert collections.abc.Mapping in state_origins
    assert collections.abc.Sequence in state_origins
    # W1 (2026-10-21): the three legal shapes are JSON object, string and
    # array-of-strings; raw bytes are no longer part of the contract.
    state_args = typing.get_args(hints["state"])
    assert str in state_args
    assert bytes not in state_args
    assert {typing.get_origin(arg) for arg in state_args if typing.get_origin(arg)} == {
        collections.abc.Mapping,
        collections.abc.Sequence,
    }
    sequence_arg = next(
        arg for arg in state_args if typing.get_origin(arg) is collections.abc.Sequence
    )
    assert typing.get_args(sequence_arg) == (str,)

    assert typing.get_origin(hints["questions"]) is collections.abc.Mapping
    qid_type, spec_type = typing.get_args(hints["questions"])
    assert qid_type is str
    assert set(typing.get_args(spec_type)) == {
        decision.NoulSpec,
        decision.ChoiceSpec,
        decision.ScoreSpec,
        decision.BoxSpec,
    }
    assert typing.get_args(decision.QuestionType) == ("noul", "choice", "score", "box")


# ---------------------------------------------------------------------------
# fail-soft matrix (D-004): nothing but DecisionInputError escapes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("item", "expected_reason", "expected_attempts", "expected_retryable"),
    [
        (RuntimeError("boom"), "upstream-error", 1, False),
        (ValueError("not json"), "bad-response", 1, False),
        (json.JSONDecodeError("bad", "x", 0), "bad-response", 1, False),
        (OSError("dial failed"), "upstream-error", 3, True),
        (TimeoutError("slow"), "timeout", 3, True),
    ],
)
def test_backend_failure_matrix_is_normalized(
    tmp_path: pathlib.Path,
    item: object,
    expected_reason: str,
    expected_attempts: int,
    expected_retryable: bool,
) -> None:
    backend = decision.FakeBackend([item, item, item, item])
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["available"] is False
    assert result["reason"] == expected_reason
    assert result["attempts"] == expected_attempts
    assert result["answers"] is None
    # retryable means more than one attempt happened (max_retries default 2)
    assert (result["attempts"] > 1) is expected_retryable


def test_backend_returning_non_outcome_is_bad_response(tmp_path: pathlib.Path) -> None:
    class _RawBackend:
        name = "raw"
        confidence_source = "api"

        def decide(self, state, questions, cfg):
            return "not-a-BackendOutcome"

    client = decision.DecisionClient(
        decision.DecisionConfig(project_root=tmp_path, enabled=True), _RawBackend()
    )
    result = client.decide("s", CHOICE_Q)
    assert result["available"] is False
    assert result["reason"] == "bad-response"


def test_non_retryable_outcome_is_not_retried(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([fail("rate-limited", retryable=False)])
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["reason"] == "rate-limited"
    assert result["attempts"] == 1
    assert len(backend.calls) == 1


def test_unavailable_answer_payload_is_bad_response(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({})])
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["available"] is False
    assert result["reason"] == "bad-response"


def test_partial_answers_are_bad_response(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    questions = {"q": {"type": "noul"}, "q2": {"type": "noul"}}
    result = make_client(tmp_path, backend).decide("s", questions)
    assert result["available"] is False
    assert result["reason"] == "bad-response"


def test_available_without_answers_key_is_bad_response(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([{"available": True, "reason": None, "retryable": False, "answers": None, "latency_ms": 1}])
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["available"] is False
    assert result["reason"] == "bad-response"


def test_unknown_backend_reason_is_normalized_to_frozen_value(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([fail("invented-reason")])
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["reason"] == "upstream-error"
    assert result["reason"] in decision.REASON_CODES


def test_entry_unavailable_is_surfaced(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([fail("entry-unavailable", detail="llmproxy entry not exposed")])
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["reason"] == "entry-unavailable"
    assert result["attempts"] == 1


def test_backend_exception_never_escapes_even_with_buggy_str(tmp_path: pathlib.Path) -> None:
    class Exploding(Exception):
        def __str__(self) -> str:
            raise RuntimeError("str() broke")

    backend = decision.FakeBackend([Exploding()])
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["available"] is False
    assert result["reason"] in decision.REASON_CODES


# ---------------------------------------------------------------------------
# Budget (D-004): max_questions, state bytes, retries, wall-clock.
# ---------------------------------------------------------------------------


def test_max_questions_budget_is_input_error(tmp_path: pathlib.Path) -> None:
    questions = {f"q{i}": {"type": "noul"} for i in range(3)}
    with pytest.raises(decision.DecisionInputError):
        make_client(tmp_path, decision.FakeBackend([ok({})]), max_questions=2).decide("s", questions)


def test_state_byte_budget_returns_budget_exhausted(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    result = make_client(tmp_path, backend, max_state_bytes=8).decide("123456789", CHOICE_Q)
    assert result["available"] is False
    assert result["reason"] == "budget-exhausted"
    assert result["attempts"] == 0
    assert backend.calls == []


def test_state_byte_budget_counts_utf8_bytes(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    # 4 CJK chars = 12 bytes in utf-8
    result = make_client(tmp_path, backend, max_state_bytes=12).decide("决策状态", CHOICE_Q)
    assert result["available"] is True


# ---------------------------------------------------------------------------
# W1 (2026-10-21): state shapes + token budgets.
# ---------------------------------------------------------------------------


def test_estimate_tokens_ascii_is_one_token_per_four_chars_rounded_up() -> None:
    assert decision._estimate_tokens("") == 0
    assert decision._estimate_tokens("abc") == 1
    assert decision._estimate_tokens("abcd") == 1
    assert decision._estimate_tokens("abcde") == 2
    assert decision._estimate_tokens("x" * 4000) == 1000


def test_estimate_tokens_cjk_is_one_token_per_character() -> None:
    assert decision._estimate_tokens("中文") == 2
    assert decision._estimate_tokens("字" * 20000) == 20000


def test_estimate_tokens_mixed_text_applies_both_rules() -> None:
    # 3 ASCII chars -> ceil(3/4) = 1; 2 CJK chars -> 2
    assert decision._estimate_tokens("abc中文") == 3
    # 8 ASCII -> 2; 5 CJK -> 5
    assert decision._estimate_tokens("abcdefgh决策点状态") == 7


def test_state_accepts_object_string_and_string_array(tmp_path: pathlib.Path) -> None:
    states = [
        {"candidates": ["a", "b"], "phase": "EXECUTE"},
        "plain text state",
        ["fragment one", "fragment two"],
    ]
    backend = decision.FakeBackend([ok({"q": answer("a")}) for _ in states])
    client = make_client(tmp_path, backend)
    for state in states:
        assert client.decide(state, CHOICE_Q)["available"] is True
    assert [call["state"] for call in backend.calls] == states


def test_bytes_state_is_no_longer_encoded_verbatim(tmp_path: pathlib.Path) -> None:
    encoded = decision._encode_state(b"raw-bytes-state")
    assert encoded != b"raw-bytes-state"
    assert json.loads(encoded.decode("utf-8")) == "b'raw-bytes-state'"
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    result = make_client(tmp_path, backend).decide(b"raw-bytes-state", CHOICE_Q)
    assert result["available"] is True
    assert len(backend.calls) == 1


def test_state_plus_longest_question_token_budget_returns_budget_exhausted(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    details = capture_emit_details(monkeypatch)
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    # The card's literal example (20000 CJK chars) is ~20k tokens, i.e. *under*
    # the 32768 gate; 40000 chars is what actually crosses it while staying
    # below max_total_tokens, so this test isolates the per-question gate.
    assert decision._estimate_tokens(json.dumps({"blob": "字" * 20000})) < 32768
    state = {"blob": "字" * 40000}
    result = make_client(tmp_path, backend).decide(state, CHOICE_Q)
    assert result["available"] is False
    assert result["reason"] == "budget-exhausted"
    assert result["attempts"] == 0
    assert backend.calls == []
    detail = str(details[0])
    assert "max_state_plus_question_tokens=32768" in detail
    assert "state=" in detail and "longest=" in detail
    numbers = [int(chunk) for chunk in detail.replace("=", " ").split() if chunk.isdigit()]
    assert len(numbers) >= 2


def test_total_request_token_budget_returns_budget_exhausted(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    details = capture_emit_details(monkeypatch)
    # 8 questions of ~9000 CJK tokens each: every single question stays under the
    # 32768 per-question gate, the sum (~72k) crosses max_total_tokens.
    spec = {"type": "choice", "instructions": "字" * 9000, "choices": ["a"]}
    questions = {f"q{i}": dict(spec) for i in range(8)}
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    result = make_client(tmp_path, backend).decide({"phase": "EXECUTE"}, questions)
    assert result["available"] is False
    assert result["reason"] == "budget-exhausted"
    assert result["attempts"] == 0
    assert backend.calls == []
    detail = str(details[0])
    assert "max_total_tokens=65536" in detail
    assert "state=" in detail and "questions=" in detail
    numbers = [int(chunk) for chunk in detail.replace("=", " ").split() if chunk.isdigit()]
    assert len(numbers) >= 2


def test_default_byte_gate_is_off_so_20kb_state_passes(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    state = {"blob": "x" * 20000}
    client = make_client(tmp_path, backend)
    assert client.cfg.max_state_bytes == 0
    assert len(decision._encode_state(state)) > 16384
    result = client.decide(state, CHOICE_Q)
    assert result["available"] is True
    assert len(backend.calls) == 1


def test_explicit_max_state_bytes_16384_still_gates(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    details = capture_emit_details(monkeypatch)
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    state = {"blob": "x" * 20000}
    result = make_client(tmp_path, backend, max_state_bytes=16384).decide(state, CHOICE_Q)
    assert result["available"] is False
    assert result["reason"] == "budget-exhausted"
    assert result["attempts"] == 0
    assert backend.calls == []
    assert "max_state_bytes=16384" in str(details[0])


def test_token_budgets_are_read_from_decide_json(tmp_path: pathlib.Path) -> None:
    path = tmp_path / ".mw" / "decide.json"
    path.parent.mkdir(parents=True)
    path.write_text(
        json.dumps(
            {
                "enabled": True,
                "max_state_bytes": 0,
                "max_total_tokens": 4096,
                "max_state_plus_question_tokens": 2048,
            }
        ),
        encoding="utf-8",
        newline="\n",
    )
    cfg, error = decision.DecisionConfig.from_project(tmp_path)
    assert error is None
    assert cfg.is_configured is True
    assert cfg.max_state_bytes == 0
    assert cfg.max_total_tokens == 4096
    assert cfg.max_state_plus_question_tokens == 2048
    # The new keys are known fields, not passthrough extras.
    assert cfg.extras == {}


@pytest.mark.parametrize(
    ("raw", "field"),
    [
        ({"max_total_tokens": 0}, "max_total_tokens"),
        ({"max_total_tokens": "big"}, "max_total_tokens"),
        ({"max_state_plus_question_tokens": 0}, "max_state_plus_question_tokens"),
        ({"max_state_plus_question_tokens": None}, "max_state_plus_question_tokens"),
        ({"max_state_bytes": -1}, "max_state_bytes"),
    ],
)
def test_invalid_token_budgets_fail_soft(raw: dict, field: str) -> None:
    cfg, error = decision.DecisionConfig.from_dict({"enabled": True, **raw})
    assert error and field in error
    assert cfg.enabled is False
    assert cfg.is_configured is False


# ---------------------------------------------------------------------------
# Budget (D-004): retries and wall-clock.
# ---------------------------------------------------------------------------


def test_max_retries_bounds_attempts(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([fail("rate-limited", retryable=True)] * 4)
    clock = FakeClock()
    client = decision.DecisionClient(
        decision.DecisionConfig(project_root=tmp_path, enabled=True, max_retries=2),
        backend,
        clock=clock,
        sleep=clock.sleep,
    )
    result = client.decide("s", CHOICE_Q)
    assert result["attempts"] == 3
    assert len(backend.calls) == 3
    assert result["reason"] == "rate-limited"


def test_max_retries_zero_means_single_attempt(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([fail("rate-limited", retryable=True)] * 4)
    clock = FakeClock()
    client = decision.DecisionClient(
        decision.DecisionConfig(project_root=tmp_path, enabled=True, max_retries=0),
        backend,
        clock=clock,
        sleep=clock.sleep,
    )
    result = client.decide("s", CHOICE_Q)
    assert result["attempts"] == 1
    assert result["reason"] == "rate-limited"


def test_retry_backoff_is_exponential_base_2(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([fail("rate-limited", retryable=True)] * 3)
    clock = FakeClock()
    client = decision.DecisionClient(
        decision.DecisionConfig(project_root=tmp_path, enabled=True, max_retries=2),
        backend,
        clock=clock,
        sleep=clock.sleep,
    )
    client.decide("s", CHOICE_Q)
    assert clock.sleeps == [2.0, 4.0]


def test_retry_backoff_base_is_configurable(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([fail("rate-limited", retryable=True)] * 3)
    clock = FakeClock()
    client = decision.DecisionClient(
        decision.DecisionConfig(
            project_root=tmp_path, enabled=True, max_retries=2, backoff_base_s=0.5
        ),
        backend,
        clock=clock,
        sleep=clock.sleep,
    )
    client.decide("s", CHOICE_Q)
    assert clock.sleeps == [0.5, 1.0]


def test_retry_is_skipped_when_backoff_exceeds_time_budget(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([fail("rate-limited", retryable=True)] * 3)
    clock = FakeClock()
    client = decision.DecisionClient(
        decision.DecisionConfig(
            project_root=tmp_path, enabled=True, max_retries=2, timeout_s=20, backoff_base_s=25
        ),
        backend,
        clock=clock,
        sleep=clock.sleep,
    )
    result = client.decide("s", CHOICE_Q)
    assert result["reason"] == "budget-exhausted"
    assert result["attempts"] == 1
    assert clock.sleeps == []
    assert len(backend.calls) == 1


def test_deadline_stops_retrying_after_sleep(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([fail("rate-limited", retryable=True)] * 4)
    clock = FakeClock()
    client = decision.DecisionClient(
        decision.DecisionConfig(
            project_root=tmp_path, enabled=True, max_retries=5, timeout_s=20, backoff_base_s=10
        ),
        backend,
        clock=clock,
        sleep=clock.sleep,
    )
    result = client.decide("s", CHOICE_Q)
    assert result["reason"] == "budget-exhausted"
    assert result["attempts"] == 2
    assert clock.sleeps == [10.0]


def test_unencodable_state_does_not_leak(tmp_path: pathlib.Path) -> None:
    class Unencodable:
        def __str__(self) -> str:
            raise RuntimeError("cannot stringify")

        def __repr__(self) -> str:
            raise RuntimeError("cannot repr")

    backend = decision.FakeBackend([ok({"q": answer("a")})])
    result = make_client(tmp_path, backend).decide(Unencodable(), CHOICE_Q)
    assert result["available"] is True
    assert len(backend.calls) == 1


def test_sleep_failure_does_not_leak(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([fail("rate-limited", retryable=True)])
    clock = FakeClock()

    def broken_sleep(seconds: float) -> None:
        raise RuntimeError("sleep failed")

    client = decision.DecisionClient(
        decision.DecisionConfig(project_root=tmp_path, enabled=True),
        backend,
        clock=clock,
        sleep=broken_sleep,
    )
    result = client.decide("s", CHOICE_Q)
    assert result["available"] is False
    assert result["reason"] == "budget-exhausted"


def test_latency_ms_is_non_negative_int(tmp_path: pathlib.Path) -> None:
    clock = FakeClock()

    def slow_sleep(seconds: float) -> None:
        clock.advance(seconds)

    backend = decision.FakeBackend(
        [lambda s, q, c: (clock.advance(1.25), fail("rate-limited", retryable=False))[1]]
    )
    client = decision.DecisionClient(
        decision.DecisionConfig(project_root=tmp_path, enabled=True),
        backend,
        clock=clock,
        sleep=slow_sleep,
    )
    result = client.decide("s", CHOICE_Q)
    assert isinstance(result["latency_ms"], int)
    assert result["latency_ms"] == 1250


# ---------------------------------------------------------------------------
# Config (D-007): missing / corrupt / disabled.
# ---------------------------------------------------------------------------


def test_missing_config_is_unconfigured_disabled(tmp_path: pathlib.Path) -> None:
    cfg, error = decision.DecisionConfig.from_project(tmp_path)
    assert error is None
    assert cfg.unconfigured is True
    assert cfg.enabled is False
    assert cfg.is_configured is False
    assert cfg.timeout_s == 20
    assert cfg.max_retries == 2
    assert cfg.max_questions == 8
    # W1: the byte gate is off by default (0); the token gates carry the budget.
    assert cfg.max_state_bytes == 0
    assert cfg.max_total_tokens == 65536
    assert cfg.max_state_plus_question_tokens == 32768
    assert cfg.max_tokens == 1024


def test_corrupt_config_returns_error_string(tmp_path: pathlib.Path) -> None:
    path = tmp_path / ".mw" / "decide.json"
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8", newline="\n")
    cfg, error = decision.DecisionConfig.from_project(tmp_path)
    assert error and "decide.json" in error
    assert cfg.enabled is False
    assert cfg.config_error == error


def test_bad_field_type_disables_and_reports(tmp_path: pathlib.Path) -> None:
    path = tmp_path / ".mw" / "decide.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"enabled": True, "timeout_s": "soon"}), encoding="utf-8", newline="\n")
    cfg, error = decision.DecisionConfig.from_project(tmp_path)
    assert error and "timeout_s" in error
    assert cfg.enabled is False


def test_out_of_range_value_is_config_error(tmp_path: pathlib.Path) -> None:
    cfg, error = decision.DecisionConfig.from_dict({"enabled": True, "max_retries": -1})
    assert error and "max_retries" in error
    assert cfg.enabled is False


def test_config_values_are_all_overridable(tmp_path: pathlib.Path) -> None:
    raw = {
        "enabled": True,
        "transport": "timi-decisions",
        "model": "jev-next",
        "timeout_s": 3,
        "max_retries": 1,
        "max_questions": 2,
        "max_state_bytes": 64,
        "max_total_tokens": 4096,
        "max_state_plus_question_tokens": 2048,
        "max_tokens": 128,
        "backoff_base_s": 0.25,
        "evidence_path": "custom/evidence.jsonl",
        "points": {"dp1": {"enabled": True}},
    }
    cfg, error = decision.DecisionConfig.from_dict(raw, project_root=tmp_path)
    assert error is None
    assert cfg.enabled is True
    assert cfg.transport == "timi-decisions"
    assert cfg.model == "jev-next"
    assert cfg.timeout_s == 3
    assert cfg.max_retries == 1
    assert cfg.max_questions == 2
    assert cfg.max_state_bytes == 64
    assert cfg.max_total_tokens == 4096
    assert cfg.max_state_plus_question_tokens == 2048
    assert cfg.max_tokens == 128
    assert cfg.backoff_base_s == 0.25
    assert cfg.evidence_path == "custom/evidence.jsonl"
    assert cfg.points["dp1"]["enabled"] is True


def test_disabled_config_returns_disabled_without_backend_call(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    client = decision.DecisionClient(
        decision.DecisionConfig(project_root=tmp_path, enabled=False), backend
    )
    result = client.decide("s", CHOICE_Q)
    assert result["available"] is False
    assert result["reason"] == "disabled"
    assert result["attempts"] == 0
    assert backend.calls == []


def test_unconfigured_project_returns_disabled(tmp_path: pathlib.Path) -> None:
    cfg, _ = decision.DecisionConfig.from_project(tmp_path)
    result = decision.DecisionClient(cfg, decision.FakeBackend([ok({})])).decide("s", CHOICE_Q)
    assert result["reason"] == "disabled"


def test_config_error_detail_is_client_visible(tmp_path: pathlib.Path) -> None:
    cfg = decision.DecisionConfig(
        project_root=tmp_path, enabled=True, config_error="decide.json invalid: boom"
    )
    result = decision.DecisionClient(cfg, decision.FakeBackend([ok({})])).decide("s", CHOICE_Q)
    assert result["reason"] == "disabled"


def test_no_backend_resolves_to_entry_unavailable(tmp_path: pathlib.Path) -> None:
    client = decision.DecisionClient(
        decision.DecisionConfig(project_root=tmp_path, enabled=True), None
    )
    result = client.decide("s", CHOICE_Q)
    assert result["available"] is False
    assert result["reason"] == "entry-unavailable"
    assert result["attempts"] == 0


def test_backend_factory_injection_is_used(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    client = decision.DecisionClient(
        decision.DecisionConfig(project_root=tmp_path, enabled=True),
        backend_factory=lambda cfg: backend,
    )
    result = client.decide("s", CHOICE_Q)
    assert result["available"] is True
    assert len(backend.calls) == 1


def test_default_backend_factory_hook_is_used(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: backend)
    client = decision.DecisionClient(decision.DecisionConfig(project_root=tmp_path, enabled=True))
    assert client.decide("s", CHOICE_Q)["available"] is True
    assert len(backend.calls) == 1


def test_config_defaults_name_the_only_decision_transport() -> None:
    cfg = decision.DecisionConfig()
    assert cfg.transport == "timi-decisions"
    assert cfg.model == "jev-latest"
    assert decision.DEFAULT_BACKEND_CLASSES == {"timi-decisions": "TimiDecisionsBackend"}


def test_default_resolver_maps_transport_to_backend_class(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import types

    monkeypatch.undo()  # bypass the autouse neutralisation for this branch

    class DummyBackend:
        name = "timi-decisions"
        confidence_source = "api"

        def decide(self, state, questions, cfg):
            return None

    fake_module = types.SimpleNamespace(TimiDecisionsBackend=DummyBackend)
    monkeypatch.setitem(sys.modules, "decision_backends", fake_module)
    resolved = decision._imported_backend_factory(
        decision.DecisionConfig(transport="timi-decisions")
    )
    assert isinstance(resolved, DummyBackend)

    # FIX-L: a removed transport value fails loud instead of falling back.
    unknown = decision._imported_backend_factory(
        decision.DecisionConfig(transport="llm-transitional")
    )
    assert unknown is not None
    outcome = unknown.decide("s", {"q": {"type": "noul"}}, decision.DecisionConfig())
    assert outcome.available is False
    assert outcome.reason == "entry-unavailable"
    assert outcome.detail == "unknown decision transport llm-transitional"


# ---------------------------------------------------------------------------
# Evidence line (D-005) + credential hygiene (requirement 8).
# ---------------------------------------------------------------------------


def test_evidence_line_written_on_success(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a", 0.9)})], confidence_source="api")
    make_client(tmp_path, backend).decide("s", CHOICE_Q, dp="dp-1")
    lines = evidence_lines(tmp_path)
    assert len(lines) == 1
    record = lines[0]
    assert list(record.keys()) == EVIDENCE_KEYS
    assert isinstance(record["ts"], str) and record["ts"].endswith("+00:00")
    assert record["dp"] == "dp-1"
    assert record["available"] is True
    assert record["reason"] is None
    assert record["answers"] == {"q": {"value": "a", "confidence": 0.9}}
    assert record["confidence"] == 0.9
    assert record["confidence_source"] == "api"
    assert record["attempts"] == 1
    assert isinstance(record["latency_ms"], int)


def test_evidence_line_on_failure_has_no_answers_or_confidence(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([fail("upstream-error")])
    make_client(tmp_path, backend).decide("s", CHOICE_Q, dp="dp-2")
    record = evidence_lines(tmp_path)[0]
    assert record["available"] is False
    assert record["reason"] == "upstream-error"
    assert record["answers"] is None
    assert record["confidence"] is None
    assert record["dp"] == "dp-2"


def test_evidence_appends_one_line_per_call(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a")}), fail("timeout")])
    client = make_client(tmp_path, backend)
    client.decide("s1", CHOICE_Q)
    client.decide("s2", CHOICE_Q)
    lines = evidence_lines(tmp_path)
    assert len(lines) == 2
    assert [line["available"] for line in lines] == [True, False]


def test_evidence_write_failure_is_swallowed(tmp_path: pathlib.Path) -> None:
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    backend = decision.FakeBackend([ok({"q": answer("a")})])
    client = decision.DecisionClient(
        decision.DecisionConfig(project_root=tmp_path, enabled=True),
        backend,
        evidence_path=blocker / "sub" / "triage-decisions.jsonl",
    )
    result = client.decide("s", CHOICE_Q)
    assert result["available"] is True


def test_evidence_path_override_is_honoured(tmp_path: pathlib.Path) -> None:
    override = tmp_path / "custom" / "ev.jsonl"
    client = decision.DecisionClient(
        decision.DecisionConfig(project_root=tmp_path, enabled=True),
        decision.FakeBackend([ok({"q": answer("a")})]),
        evidence_path=override,
    )
    client.decide("s", CHOICE_Q)
    assert override.exists()
    assert len(override.read_text(encoding="utf-8").splitlines()) == 1


def test_no_project_root_means_no_evidence_file(tmp_path: pathlib.Path) -> None:
    client = decision.DecisionClient(
        decision.DecisionConfig(enabled=True), decision.FakeBackend([ok({"q": answer("a")})])
    )
    result = client.decide("s", CHOICE_Q)
    assert result["available"] is True
    assert client.evidence_path() is None


def test_confidence_aggregate_is_min_of_answers(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([ok({"q": answer("a", 0.9), "q2": answer(1, 0.4)})])
    questions = {"q": {"type": "noul"}, "q2": {"type": "noul"}}
    make_client(tmp_path, backend).decide("s", questions)
    assert evidence_lines(tmp_path)[0]["confidence"] == 0.4


def test_credentials_never_reach_evidence_or_detail(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    secret = "sk-supersecretvalue12345"
    monkeypatch.setenv("TIMI_API_KEY", secret)
    backend = decision.FakeBackend([fail("upstream-error", detail=f"auth failed for {secret}")])
    backend.name = secret
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    raw = (tmp_path / ".agenticdoc" / "_autopilot" / "triage-decisions.jsonl").read_text(
        encoding="utf-8"
    )
    assert secret not in raw
    assert result["transport"] == "<redacted>"
    assert secret not in json.dumps(result)


def test_scrub_detail_truncates_and_redacts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    secret = "sk-abcdefghijklmnop"
    monkeypatch.setenv("TIMI_API_KEY", secret)
    scrubbed = decision._scrub_detail(f"Bearer {secret} " + "x" * 500)
    assert secret not in scrubbed
    assert "Bearer <redacted>" in scrubbed
    assert len(scrubbed) <= decision._DETAIL_LIMIT


# ---------------------------------------------------------------------------
# FakeBackend behaviour (used by every test above and by callers).
# ---------------------------------------------------------------------------


def test_fake_backend_records_calls_and_default(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend(default=ok({"q": answer("a")}))
    client = make_client(tmp_path, backend)
    client.decide("state-1", CHOICE_Q)
    client.decide("state-2", CHOICE_Q)
    assert [call["state"] for call in backend.calls] == ["state-1", "state-2"]
    assert backend.calls[0]["questions"] == CHOICE_Q
    assert backend.calls[0]["cfg"] is client.cfg


def test_fake_backend_queue_is_consumed_in_order(tmp_path: pathlib.Path) -> None:
    backend = decision.FakeBackend([fail("rate-limited", retryable=True), ok({"q": answer("a")})])
    result = make_client(tmp_path, backend).decide("s", CHOICE_Q)
    assert result["available"] is True
    assert result["attempts"] == 2
    assert backend.remaining == 0
