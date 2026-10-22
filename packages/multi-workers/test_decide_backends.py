"""test_decide_backends.py — hermetic tests for the single decision transport.

FIX-L contract under test: ``decision_backends.TimiDecisionsBackend`` is the
only backend — ``POST {TIMI_BASE_URL}/v1/decisions`` with model ``jev-latest``,
bare-key ``Authorization``, body exactly ``{model, state, questions}``. The glm
chat path (``LLMTransitionalBackend``) and the direct TypeSafe path
(``DirectSystemOneBackend``) are deleted, and no fallback of any kind exists:
no model switch, no transport switch, no second endpoint.

Fixtures are the documented request/response examples from
``.agenticdoc/mw-decision-substitution/jev接入.md``.

Hermetic by construction: every HTTP call goes through
``decision_backends._http_post`` (monkeypatched here) and every retry wait goes
through ``decision_backends._sleep`` (recorded, never slept). Credentials are
injected via cfg/env and the auth.json path is redirected into ``tmp_path``, so
the real ``~/.pi/agent/auth.json`` is never read. No test asserts on or prints a
key.

Run: ``cd packages/multi-workers && python -m pytest -q test_decide_backends.py``
"""
from __future__ import annotations

import json
import pathlib
import sys
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import decision  # noqa: E402
import decision_backends as db  # noqa: E402

TEST_KEY = "test-timi-key-not-real"
MODULE_SOURCE = pathlib.Path(db.__file__).read_text(encoding="utf-8")


@dataclass
class Cfg:
    """Duck-typed cfg: exercises the getattr-based config surface the client injects."""

    enabled: bool = True
    model: str = db.DEFAULT_MODEL
    base_url: str = db.TIMI_BASE_URL
    timeout_s: float = 20.0
    max_retries: int = 2
    backoff_base_s: float = 0.0
    max_tokens: int = 1024
    api_key: str | None = TEST_KEY


class FakeScript:
    """Replays one canned step per call (the last step repeats) and records calls.

    A step is a dict with ``status``/``body``/``content_type``/``headers`` or an
    exception instance to raise.
    """

    def __init__(self, steps):
        self.steps = list(steps) or [{"body": "{}"}]
        self.calls: list = []

    def __call__(self, url, headers, payload, timeout_s):
        self.calls.append(
            {"url": url, "headers": headers, "payload": payload, "timeout_s": timeout_s}
        )
        step = self.steps[min(len(self.calls), len(self.steps)) - 1]
        if isinstance(step, BaseException):
            raise step
        return db.HttpResponse(
            int(step.get("status", 200)),
            step.get("content_type", "application/json"),
            step.get("body", ""),
            dict(step.get("headers") or {}),
        )

    def install(self, monkeypatch):
        monkeypatch.setattr(db, "_http_post", self)
        return self


@pytest.fixture(autouse=True)
def _isolate(monkeypatch, tmp_path):
    """No real credential file, no ambient credential env, no real sleeping."""
    monkeypatch.delenv("TIMI_API_KEY", raising=False)
    monkeypatch.delenv("TIMI_BASE_URL", raising=False)
    monkeypatch.setattr(db, "_auth_json_path", lambda: tmp_path / "no-such-auth.json")
    sleeps: list = []
    monkeypatch.setattr(db, "_sleep", lambda seconds: sleeps.append(seconds))
    return SimpleNamespace(tmp=tmp_path, sleeps=sleeps)


def _ok(body: dict) -> dict:
    return {"body": json.dumps(body, ensure_ascii=False)}


# ── Documented fixtures (verbatim from jev接入.md) ──────────────────────────

DOC_STATE = "求助！我的提现已经失败3天了。"

DOC_NOUL_INSTRUCTIONS = "这段话是否传达了紧急性？"
DOC_NOUL_CRITERIA = {"true": "明确有时效性要求", "false": "未表达紧急性"}
DOC_NOUL_BODY = {
    "model": "jev-latest",
    "answers": {"is_urgent": {"type": "noul", "noul": 0.95}},
    "usage": {"input_tokens": 307, "output_tokens": 20},
}

DOC_CHOICE_INSTRUCTIONS = "该工单应该由哪个团队处理？"
DOC_CHOICE_CRITERIA = {
    "billing": "支付、开票、退款相关",
    "technical": "缺陷、故障、集成相关",
    "sales": "定价、升级、新账号相关",
}
DOC_CHOICE_BODY = {
    "model": "jev-latest",
    "answers": {
        "department": {
            "type": "choice",
            "choice": "billing",
            "probabilities": {"billing": 0.88, "technical": 0.12, "sales": 0},
            "confidence": 0.81,
        }
    },
    "usage": {"input_tokens": 318, "output_tokens": 34},
}

DOC_SCORE_INSTRUCTIONS = "客户的情绪激烈程度如何？"
DOC_SCORE_CRITERIA = ["平静", "不满", "非常愤怒"]
DOC_SCORE_BODY = {
    "model": "jev-latest",
    "answers": {
        "frustration": {
            "type": "score",
            "score": 1.05,
            "legend": {"0": "平静", "1": "不满", "2": "非常愤怒"},
            "probabilities": {"0": 0, "1": 0.95, "2": 0.05},
            "confidence": 0.92,
        }
    },
    "usage": {"input_tokens": 304, "output_tokens": 18},
}


def _dp_questions(dp_id):
    """Read the real registry questions (registry is the contract, not a stub)."""
    dpts = pytest.importorskip("decision_points")
    point = dpts.get_decision_point(dp_id)
    return {question["id"]: question for question in point.questions}


# ── identity: one transport, no alternatives ───────────────────────────────

def test_only_one_backend_class_survives():
    backend_names = [name for name in dir(db) if name.endswith("Backend")]
    # DecisionBackend is the frozen protocol; TimiDecisionsBackend the only impl.
    assert sorted(backend_names) == ["DecisionBackend", "TimiDecisionsBackend"]
    assert db.TimiDecisionsBackend.name == "timi-decisions"
    assert db.TimiDecisionsBackend.confidence_source == "api"
    assert db.DECISIONS_TRANSPORT == "timi-decisions"
    assert db.DECISIONS_PATH == "/v1/decisions"
    assert db.DEFAULT_MODEL == "jev-latest"


def test_answerable_types_are_choice_score_noul_only():
    assert db.ANSWERABLE_TYPES == ("choice", "score", "noul")
    assert "box" not in db.ANSWERABLE_TYPES


def test_no_second_endpoint_or_second_model_survives():
    """No-fallback assertion at the source level (the removed paths are gone)."""
    for forbidden in ("TYPESAFE_BASE_URL", "/v1/systemone", "glm-5.3-flashx"):
        assert MODULE_SOURCE.count(forbidden) == 0, f"{forbidden} still in decision_backends.py"
    # The only transport constant in the module points at the decisions entry.
    assert db.DECISIONS_PATH in MODULE_SOURCE
    assert "/v1/messages" not in MODULE_SOURCE
    assert "/responses" not in MODULE_SOURCE
    assert "/v1/chat/completions" not in MODULE_SOURCE


def test_decision_config_defaults_point_at_the_only_transport():
    assert decision.DEFAULT_BACKEND_CLASSES == {"timi-decisions": "TimiDecisionsBackend"}
    cfg = decision.DecisionConfig()
    assert cfg.transport == "timi-decisions"
    assert cfg.model == "jev-latest"
    for class_name in decision.DEFAULT_BACKEND_CLASSES.values():
        assert hasattr(db, class_name), f"{class_name} missing in decision_backends"


# ── 1. noul: documented request/response shape ─────────────────────────────

def test_noul_request_body_matches_the_documented_shape(monkeypatch):
    """Payload keys are exactly {model,state,questions}; no criteria when absent."""
    script = FakeScript([_ok(DOC_NOUL_BODY)]).install(monkeypatch)
    questions = {"is_urgent": {"type": "noul", "instructions": DOC_NOUL_INSTRUCTIONS}}

    outcome = db.TimiDecisionsBackend().decide(DOC_STATE, questions, Cfg())

    assert outcome.available is True
    assert outcome.reason is None
    assert outcome.retryable is False
    assert outcome.answers == {"is_urgent": {"value": 0.95, "confidence": None}}

    call = script.calls[0]
    assert call["url"] == db.TIMI_BASE_URL + "/v1/decisions"
    assert set(call["payload"]) == {"model", "state", "questions"}
    assert call["payload"]["model"] == "jev-latest"
    assert call["payload"]["state"] == DOC_STATE
    # dict equality: no "criteria" key is invented for an optional criterion.
    assert call["payload"]["questions"] == {
        "is_urgent": {"type": "noul", "instructions": DOC_NOUL_INSTRUCTIONS}
    }


def test_noul_criteria_is_passed_through_verbatim(monkeypatch):
    script = FakeScript([_ok(DOC_NOUL_BODY)]).install(monkeypatch)
    questions = {
        "is_urgent": {
            "type": "noul",
            "instructions": DOC_NOUL_INSTRUCTIONS,
            "criteria": DOC_NOUL_CRITERIA,
        }
    }

    outcome = db.TimiDecisionsBackend().decide(DOC_STATE, questions, Cfg())

    assert outcome.available is True
    assert script.calls[0]["payload"]["questions"]["is_urgent"] == {
        "type": "noul",
        "instructions": DOC_NOUL_INSTRUCTIONS,
        "criteria": DOC_NOUL_CRITERIA,
    }


def test_registry_question_gets_its_own_instructions(monkeypatch):
    """FIX-O: the registry text is what reaches the wire (no placeholder)."""
    script = FakeScript([_ok({"model": "jev-latest", "answers": {
        "triage_type": {"type": "choice", "choice": "coding", "confidence": 0.9},
        "triage_risk": {"type": "choice", "choice": "low", "confidence": 0.9},
    }})]).install(monkeypatch)

    questions = _dp_questions("dp1-dispatch-type")
    outcome = db.TimiDecisionsBackend().decide("state text", questions, Cfg())

    assert outcome.available is True
    sent = script.calls[0]["payload"]["questions"]
    assert sent["triage_type"] == {
        "type": "choice",
        "instructions": "这个任务应该派给哪一类 worker？",
        "criteria": {
            "coding": "需要写代码或改代码或跑命令",
            "research": "只做检索取证不改代码",
            "review": "审计别人已完成的产出",
        },
    }
    assert sent["triage_risk"]["instructions"] == "这个任务做错了的代价有多大？"


def test_question_without_instructions_gets_the_fallback(monkeypatch):
    """The placeholder stays the last resort for a spec that carries no text."""
    script = FakeScript([_ok({"model": "jev-latest", "answers": {
        "route": {"type": "choice", "choice": "coding", "confidence": 0.9}
    }})]).install(monkeypatch)

    db.TimiDecisionsBackend().decide(
        "s", {"route": {"type": "choice", "choices": ["coding", "research"]}}, Cfg()
    )

    assert script.calls[0]["payload"]["questions"]["route"]["instructions"] == (
        "route: answer this question about the supplied state"
    )


def test_noul_credential_header_is_a_bare_key(monkeypatch):
    """Documented auth: the platform API key directly, no Bearer prefix."""
    script = FakeScript([_ok(DOC_NOUL_BODY)]).install(monkeypatch)
    db.TimiDecisionsBackend().decide(
        DOC_STATE, {"is_urgent": {"type": "noul", "instructions": "x"}}, Cfg()
    )
    headers = script.calls[0]["headers"]
    assert headers["Authorization"] == TEST_KEY
    assert headers["Content-Type"] == "application/json"


# ── 2. choice: criteria required, probabilities kept ───────────────────────

def test_choice_request_carries_criteria_and_decodes_the_answer(monkeypatch):
    script = FakeScript([_ok(DOC_CHOICE_BODY)]).install(monkeypatch)
    questions = {
        "department": {
            "type": "choice",
            "instructions": DOC_CHOICE_INSTRUCTIONS,
            "labels": DOC_CHOICE_CRITERIA,
        }
    }

    outcome = db.TimiDecisionsBackend().decide(DOC_STATE, questions, Cfg())

    assert outcome.available is True
    answer = outcome.answers["department"]
    assert answer["value"] == "billing"
    assert answer["confidence"] == 0.81
    assert answer["probabilities"] == {"billing": 0.88, "technical": 0.12, "sales": 0}

    sent = script.calls[0]["payload"]["questions"]["department"]
    assert sent == {
        "type": "choice",
        "instructions": DOC_CHOICE_INSTRUCTIONS,
        "criteria": DOC_CHOICE_CRITERIA,
    }


def test_choice_criteria_falls_back_to_null_labels(monkeypatch):
    script = FakeScript([_ok({"model": "jev-latest", "answers": {
        "route": {"type": "choice", "choice": "coding", "confidence": 0.5}
    }})]).install(monkeypatch)
    questions = {"route": {"type": "choice", "choices": ["coding", "research"]}}

    db.TimiDecisionsBackend().decide("s", questions, Cfg())

    assert script.calls[0]["payload"]["questions"]["route"]["criteria"] == {
        "coding": None,
        "research": None,
    }


def test_caller_supplied_choice_criteria_is_used_verbatim(monkeypatch):
    """The legacy `questions` shape carries `criteria` itself (jev接入.md)."""
    script = FakeScript([_ok({"model": "jev-latest", "answers": {
        "dept": {"type": "choice", "choice": "billing", "confidence": 0.9}
    }})]).install(monkeypatch)
    questions = {
        "dept": {
            "type": "choice",
            "instructions": "哪个团队接手？",
            "criteria": {"billing": "支付相关", "technical": None},
        }
    }

    outcome = db.TimiDecisionsBackend().decide("s", questions, Cfg())

    assert outcome.available is True
    assert script.calls[0]["payload"]["questions"]["dept"]["criteria"] == {
        "billing": "支付相关",
        "technical": None,
    }


def test_dynamic_candidates_override_declared_criteria(monkeypatch):
    """A rendered candidate set always wins: the ids exist only in `state`."""
    script = FakeScript([_ok({"model": "jev-latest", "answers": {
        "candidate": {"type": "choice", "choice": "c1", "confidence": 0.9}
    }})]).install(monkeypatch)
    questions = {
        "candidate": {
            "type": "choice",
            "instructions": "哪一条？",
            "dynamic_choices": "local_candidates",
        }
    }
    state = {"local_candidates": [{"id": "c1", "label": "a.md"}]}

    db.TimiDecisionsBackend().decide(state, questions, Cfg())

    assert script.calls[0]["payload"]["questions"]["candidate"]["criteria"] == {"c1": "a.md"}


def test_choice_outside_the_enum_is_bad_response_without_retry(monkeypatch):
    body = {"model": "jev-latest", "answers": {
        "department": {"type": "choice", "choice": "furious", "confidence": 0.5}
    }}
    script = FakeScript([_ok(body)]).install(monkeypatch)
    questions = {"department": {"type": "choice", "labels": DOC_CHOICE_CRITERIA}}

    outcome = db.TimiDecisionsBackend().decide(DOC_STATE, questions, Cfg())

    assert outcome.available is False
    assert outcome.reason == "bad-response"
    assert outcome.retryable is False
    assert outcome.answers is None
    assert "choice out of enum for department" in outcome.detail
    assert len(script.calls) == 1


def test_choice_answer_type_mismatch_is_bad_response(monkeypatch):
    body = {"model": "jev-latest", "answers": {"department": {"type": "noul", "noul": 0.4}}}
    FakeScript([_ok(body)]).install(monkeypatch)
    questions = {"department": {"type": "choice", "labels": DOC_CHOICE_CRITERIA}}
    outcome = db.TimiDecisionsBackend().decide(DOC_STATE, questions, Cfg())
    assert outcome.reason == "bad-response"
    assert "answer type mismatch for department" in outcome.detail


# ── 3. score: ordered criteria, fractional value, legend kept ──────────────

def test_score_request_carries_ordered_criteria_and_keeps_the_fraction(monkeypatch):
    script = FakeScript([_ok(DOC_SCORE_BODY)]).install(monkeypatch)
    questions = {
        "frustration": {
            "type": "score",
            "min": 0,
            "max": 2,
            "instructions": DOC_SCORE_INSTRUCTIONS,
            "criteria": DOC_SCORE_CRITERIA,
        }
    }

    outcome = db.TimiDecisionsBackend().decide(DOC_STATE, questions, Cfg())

    assert outcome.available is True
    answer = outcome.answers["frustration"]
    assert answer["value"] == 1.05
    assert isinstance(answer["value"], float)
    assert answer["confidence"] == 0.92
    assert answer["legend"] == {"0": "平静", "1": "不满", "2": "非常愤怒"}
    assert answer["probabilities"] == {"0": 0, "1": 0.95, "2": 0.05}

    sent = script.calls[0]["payload"]["questions"]["frustration"]
    assert sent["criteria"] == DOC_SCORE_CRITERIA
    assert isinstance(sent["criteria"], list)


def test_score_criteria_is_generated_from_min_max_when_absent(monkeypatch):
    script = FakeScript([_ok({"model": "jev-latest", "answers": {
        "risk": {"type": "score", "score": 2.5, "confidence": 0.4}
    }})]).install(monkeypatch)

    outcome = db.TimiDecisionsBackend().decide(
        "s", {"risk": {"type": "score", "min": 0, "max": 3}}, Cfg()
    )

    assert outcome.available is True
    assert outcome.answers["risk"]["value"] == 2.5
    assert script.calls[0]["payload"]["questions"]["risk"]["criteria"] == ["0", "1", "2", "3"]


def test_score_criteria_is_truncated_to_ten_levels(monkeypatch):
    script = FakeScript([_ok({"model": "jev-latest", "answers": {
        "risk": {"type": "score", "score": 3, "confidence": 0.4}
    }})]).install(monkeypatch)

    db.TimiDecisionsBackend().decide(
        "s", {"risk": {"type": "score", "min": 0, "max": 11}}, Cfg()
    )

    criteria = script.calls[0]["payload"]["questions"]["risk"]["criteria"]
    assert len(criteria) == db.MAX_SCORE_LEVELS == 10
    assert criteria == [str(level) for level in range(10)]


def test_score_must_be_a_number(monkeypatch):
    body = {"model": "jev-latest", "answers": {"risk": {"type": "score", "score": "high"}}}
    FakeScript([_ok(body)]).install(monkeypatch)
    outcome = db.TimiDecisionsBackend().decide(
        "s", {"risk": {"type": "score", "min": 0, "max": 2}}, Cfg()
    )
    assert outcome.reason == "bad-response"
    assert "score for risk is not a number" in outcome.detail


# ── 4. dynamic candidates rendered from state ──────────────────────────────

DP3 = "dp3-worker-clarify"
DP3_CANDIDATES = [
    {"id": "c1", "label": "docs/decision-substitution.md"},
    {"id": "c2", "label": "packages/multi-workers/decision_points.py"},
    {"id": "c3", "label": ".mw/decide-points.json"},
]


def _dp3_state(**overrides):
    state = {
        "schema_version": 2,
        "decision_point": DP3,
        "key": "k-1",
        "phase": "TASKS",
        "task_type": "coding",
        "risk": "mid",
        "risk_source": "machine",
        "authority_tier": "P2",
        "task_summary": "worker asks where the decide-points table lives",
        "questions_version": "q-fcbd3847",
        "ambiguity": {"kind": "fact", "question": "which file holds the decide points?"},
        "local_candidates": [dict(candidate) for candidate in DP3_CANDIDATES],
    }
    state.update(overrides)
    return state


def _dp3_answer(candidate: str) -> dict:
    return {
        "model": "jev-latest",
        "answers": {
            "answer_kind": {"type": "choice", "choice": "fact", "confidence": 0.9},
            "answerable": {"type": "noul", "noul": 0.9},
            "candidate": {"type": "choice", "choice": candidate, "confidence": 0.9},
        },
    }


def test_dynamic_candidates_become_the_choice_criteria(monkeypatch):
    script = FakeScript([_ok(_dp3_answer("c3"))]).install(monkeypatch)
    questions = _dp_questions(DP3)

    outcome = db.TimiDecisionsBackend().decide(_dp3_state(), questions, Cfg())

    assert outcome.available is True
    assert outcome.answers["candidate"] == {"value": "c3", "confidence": 0.9}
    sent = script.calls[0]["payload"]["questions"]
    assert sent["candidate"] == {
        "type": "choice",
        "instructions": "state.local_candidates 里哪一条最可能承载答案？",
        "criteria": {
            "c1": "docs/decision-substitution.md",
            "c2": "packages/multi-workers/decision_points.py",
            "c3": ".mw/decide-points.json",
        },
    }
    # static questions carry their registry labels as the criteria text
    assert sent["answer_kind"]["criteria"] == {
        "fact": "答案存在于给出的状态或候选条目里",
        "intent": "取决于人想要什么（材料里没有）",
        "reuse": "之前的表态或产物已经回答了它",
    }
    assert sent["answerable"]["type"] == "noul"
    assert set(sent["answerable"]["criteria"]) == {"true", "false"}


def test_registry_text_and_criteria_reach_the_decisions_payload(monkeypatch):
    """FIX-O case 5: ``/v1/decisions`` carries the real text, not the placeholder."""
    script = FakeScript([_ok(_dp3_answer("c1"))]).install(monkeypatch)
    questions = _dp_questions(DP3)

    outcome = db.TimiDecisionsBackend().decide(_dp3_state(), questions, Cfg())

    assert outcome.available is True
    call = script.calls[0]
    assert call["url"] == db.TIMI_BASE_URL + "/v1/decisions"
    sent = call["payload"]["questions"]
    assert sent["answer_kind"]["instructions"] == (
        "这条澄清属于哪一类：能凭已给材料查到答案、需要人的意图判断、还是已有表态可复用？"
    )
    assert sent["answer_kind"]["instructions"] == questions["answer_kind"]["instructions"]
    assert sent["answerable"]["criteria"] == {
        "true": "材料里直接有答案",
        "false": "材料不足或需要人表态",
    }
    assert sent["candidate"]["instructions"] == "state.local_candidates 里哪一条最可能承载答案？"


def test_dynamic_candidate_outside_the_rendered_enum_is_rejected(monkeypatch):
    script = FakeScript([_ok(_dp3_answer("c9"))]).install(monkeypatch)

    outcome = db.TimiDecisionsBackend().decide(_dp3_state(), _dp_questions(DP3), Cfg())

    assert outcome.available is False
    assert outcome.reason == "bad-response"
    assert outcome.answers is None
    assert "choice out of enum for candidate" in outcome.detail
    assert len(script.calls) == 1


def test_missing_dynamic_candidates_is_input_incomplete_with_zero_http(monkeypatch):
    script = FakeScript([_ok(_dp3_answer("c1"))]).install(monkeypatch)
    state = _dp3_state()
    state.pop("local_candidates")

    outcome = db.TimiDecisionsBackend().decide(state, _dp_questions(DP3), Cfg())

    assert outcome.available is False
    assert outcome.reason == "input-incomplete"
    assert outcome.retryable is False
    assert 'missing_fields=["local_candidates"]' in outcome.detail
    assert script.calls == []


@pytest.mark.parametrize(
    ("candidates", "expected"),
    [
        ([{"id": "c1", "label": "a"}, {"id": "c3", "label": "b"}], "not contiguous"),
        ([{"id": "c1", "label": "   "}], "label must be a non-empty string"),
        ({"c1": "a"}, "expected a list"),
        ([], "at least 1 candidate"),
    ],
)
def test_invalid_candidate_shapes_are_refused_with_zero_http(monkeypatch, candidates, expected):
    script = FakeScript([_ok(_dp3_answer("c1"))]).install(monkeypatch)

    outcome = db.TimiDecisionsBackend().decide(
        _dp3_state(local_candidates=candidates), _dp_questions(DP3), Cfg()
    )

    assert outcome.available is False
    assert outcome.reason == "input-incomplete"
    assert expected in outcome.detail
    assert script.calls == []


# ── 5. credentials: missing timi key means zero HTTP ───────────────────────

def test_missing_timi_credential_is_entry_unavailable_with_zero_http(monkeypatch):
    script = FakeScript([_ok(DOC_NOUL_BODY)]).install(monkeypatch)
    outcome = db.TimiDecisionsBackend().decide(
        DOC_STATE, {"is_urgent": {"type": "noul", "instructions": "x"}}, Cfg(api_key=None)
    )
    assert outcome.available is False
    assert outcome.reason == "entry-unavailable"
    assert outcome.retryable is False
    assert "TIMI_API_KEY" in outcome.detail
    assert script.calls == []


def test_resolve_timi_api_key_env_then_auth_json(monkeypatch, tmp_path):
    assert db.resolve_timi_api_key({"TIMI_API_KEY": "env-key"}) == "env-key"

    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"timi": {"key": "file-key"}}), encoding="utf-8")
    assert db.resolve_timi_api_key({}, auth_path=auth) == "file-key"
    assert db.resolve_timi_api_key({}, auth_path=tmp_path / "missing.json") is None

    auth.write_text("{broken", encoding="utf-8")
    assert db.resolve_timi_api_key({}, auth_path=auth) is None


def test_credential_status_has_only_the_timi_entry():
    assert db.credential_status(Cfg(), env={}) == {"timi": True}
    assert db.credential_status(Cfg(api_key=None), env={}) == {"timi": False}
    assert db.credential_status(Cfg(api_key=None), env={"TIMI_API_KEY": "env-key"}) == {"timi": True}


# ── 6. retries on the same endpoint (429/5xx), exhausting loud ─────────────

def _client(cfg: Cfg) -> decision.DecisionClient:
    """Client wired to the real backend and a config mirroring the Cfg knobs."""
    dc = decision.DecisionConfig(
        enabled=cfg.enabled,
        timeout_s=cfg.timeout_s,
        max_retries=cfg.max_retries,
        backoff_base_s=cfg.backoff_base_s,
        extras={"api_key": cfg.api_key, "base_url": cfg.base_url},
    )
    return decision.DecisionClient(cfg=dc, backend=db.TimiDecisionsBackend())


NOUL_ONE_Q = {"is_urgent": {"type": "noul", "instructions": DOC_NOUL_INSTRUCTIONS}}


def test_429_then_success_retries_on_the_same_endpoint(monkeypatch):
    script = FakeScript(
        [
            {"status": 429, "body": json.dumps({"error": {"message": "Too Many Requests"}})},
            _ok(DOC_NOUL_BODY),
        ]
    ).install(monkeypatch)

    response = _client(Cfg(max_retries=2)).decide(DOC_STATE, NOUL_ONE_Q, dp="dp1")

    assert response["available"] is True
    assert response["attempts"] >= 2
    assert response["answers"] == {"is_urgent": {"value": 0.95, "confidence": None}}
    assert len(script.calls) >= 2
    assert len({call["url"] for call in script.calls}) == 1  # never leaves the endpoint
    assert all(call["payload"]["model"] == "jev-latest" for call in script.calls)


def test_persistent_429_is_rate_limited_after_the_retry_budget(monkeypatch):
    script = FakeScript([{"status": 429, "body": "{}"}]).install(monkeypatch)

    response = _client(Cfg(max_retries=2)).decide(DOC_STATE, NOUL_ONE_Q, dp="dp1")

    assert response["available"] is False
    assert response["reason"] == "rate-limited"
    assert response["attempts"] == 3  # 1 attempt + max_retries(2)
    assert response["answers"] is None
    assert len(script.calls) == 3
    assert all(call["payload"]["model"] == "jev-latest" for call in script.calls)


def test_persistent_5xx_is_upstream_error_after_the_retry_budget(monkeypatch):
    script = FakeScript(
        [{"status": 503, "body": "upstream down", "content_type": "text/plain"}]
    ).install(monkeypatch)

    response = _client(Cfg(max_retries=1)).decide(DOC_STATE, NOUL_ONE_Q, dp="dp1")

    assert response["reason"] == "upstream-error"
    assert response["attempts"] == 2
    assert len(script.calls) == 2


def test_retry_after_header_is_honoured_by_the_backend(monkeypatch, _isolate):
    script = FakeScript(
        [
            {"status": 429, "body": "{}", "headers": {"retry-after": "7"}},
            _ok(DOC_NOUL_BODY),
        ]
    ).install(monkeypatch)
    backend = db.TimiDecisionsBackend()

    outcome = backend.decide(DOC_STATE, NOUL_ONE_Q, Cfg(max_retries=1, backoff_base_s=0.0))

    assert outcome.available is True
    assert _isolate.sleeps == [7.0]
    assert len(script.calls) == 2


def test_backend_retry_after_attempts_are_bounded(monkeypatch, _isolate):
    """retry-after never turns into an unbounded loop."""
    script = FakeScript(
        [{"status": 429, "body": "{}", "headers": {"retry-after": "1"}}]
    ).install(monkeypatch)

    outcome = db.TimiDecisionsBackend().decide(
        DOC_STATE, NOUL_ONE_Q, Cfg(max_retries=2, backoff_base_s=0.0)
    )

    assert outcome.available is False
    assert outcome.reason == "rate-limited"
    # Retry ownership for a gateway-mandated wait stays with the backend, so the
    # client cannot multiply the attempts.
    assert outcome.retryable is False
    assert len(script.calls) == 3  # 1 attempt + max_retries(2)
    assert _isolate.sleeps == [1.0, 1.0]


def test_transport_timeout_is_classified_and_stays_retryable(monkeypatch):
    script = FakeScript([db.TransportTimeout("slow")]).install(monkeypatch)

    outcome = db.TimiDecisionsBackend().decide(
        "s", {"is_urgent": {"type": "noul", "instructions": "x"}}, Cfg(max_retries=2)
    )

    assert outcome.available is False
    assert outcome.reason == "timeout"
    assert outcome.retryable is True
    assert len(script.calls) == 1


def test_transport_connection_error_is_upstream_error(monkeypatch):
    FakeScript([db.TransportConnectionError("refused")]).install(monkeypatch)
    outcome = db.TimiDecisionsBackend().decide(
        "s", {"is_urgent": {"type": "noul", "instructions": "x"}}, Cfg()
    )
    assert outcome.reason == "upstream-error"
    assert outcome.retryable is True


# ── 7. no fallback: a response from another model is refused ───────────────

def test_a_response_from_another_model_is_refused_not_retried(monkeypatch):
    body = {
        "model": "glm-5.3-flashx",
        "answers": {"is_urgent": {"type": "noul", "noul": 0.95}},
    }
    script = FakeScript([_ok(body)]).install(monkeypatch)

    outcome = db.TimiDecisionsBackend().decide(
        DOC_STATE, {"is_urgent": {"type": "noul", "instructions": "x"}}, Cfg()
    )

    assert outcome.available is False
    assert outcome.reason == "bad-response"
    assert outcome.answers is None
    assert "no model fallback" in outcome.detail
    assert len(script.calls) == 1  # no second model, no second endpoint
    assert script.calls[0]["payload"]["model"] == "jev-latest"


def test_response_without_an_answers_map_is_bad_response(monkeypatch):
    FakeScript([_ok({"model": "jev-latest", "usage": {}})]).install(monkeypatch)
    outcome = db.TimiDecisionsBackend().decide(
        "s", {"is_urgent": {"type": "noul", "instructions": "x"}}, Cfg()
    )
    assert outcome.reason == "bad-response"
    assert "no answers map" in outcome.detail


def test_non_json_success_is_bad_response(monkeypatch):
    FakeScript([{"status": 200, "body": "<html>nope</html>", "content_type": "text/html"}]).install(
        monkeypatch
    )
    outcome = db.TimiDecisionsBackend().decide(
        "s", {"is_urgent": {"type": "noul", "instructions": "x"}}, Cfg()
    )
    assert outcome.reason == "bad-response"
    assert outcome.retryable is False


# ── 8. legacy transport names fail loud ────────────────────────────────────

@pytest.mark.parametrize(
    "transport", ["llm-transitional", "llmproxy-anthropic", "direct-systemone", "made-up"]
)
def test_legacy_transport_is_entry_unavailable_and_never_falls_back(
    monkeypatch, transport
):
    script = FakeScript([_ok(DOC_NOUL_BODY)]).install(monkeypatch)
    cfg = decision.DecisionConfig(
        enabled=True, transport=transport, extras={"api_key": TEST_KEY}
    )
    client = decision.DecisionClient(cfg=cfg, evidence_path=None)

    response = client.decide(
        DOC_STATE, {"is_urgent": {"type": "noul", "instructions": "x"}}, dp="dp1"
    )

    assert response["available"] is False
    assert response["reason"] == "entry-unavailable"
    assert response["answers"] is None
    assert response["transport"] == transport
    assert script.calls == []  # zero HTTP, no silent timi fallback


def test_legacy_transport_detail_names_the_unknown_transport():
    backend = decision._imported_backend_factory(
        decision.DecisionConfig(transport="llm-transitional")
    )
    assert backend is not None
    outcome = backend.decide("s", {"is_urgent": {"type": "noul"}}, decision.DecisionConfig())
    assert outcome.reason == "entry-unavailable"
    assert outcome.detail == "unknown decision transport llm-transitional"
    assert outcome.retryable is False


def test_default_transport_resolves_to_the_timi_backend(monkeypatch):
    FakeScript([_ok(DOC_NOUL_BODY)]).install(monkeypatch)
    backend = decision._imported_backend_factory(decision.DecisionConfig())
    assert isinstance(backend, db.TimiDecisionsBackend)
    assert backend.name == "timi-decisions"


# ── refusals that never reach the wire ─────────────────────────────────────

BOX_Q = {"clarifying_answer": {"type": "box"}}


def test_box_question_is_box_requires_image_with_zero_http(monkeypatch):
    script = FakeScript([_ok(DOC_NOUL_BODY)]).install(monkeypatch)

    outcome = db.TimiDecisionsBackend().decide("s", BOX_Q, Cfg())

    assert outcome.available is False
    assert outcome.reason == "box-requires-image"
    assert outcome.retryable is False
    assert "TypeSafe-Danger-Zone-Images" in outcome.detail
    assert script.calls == []


def test_box_with_image_assets_is_still_not_a_decisions_question(monkeypatch):
    script = FakeScript([_ok(DOC_NOUL_BODY)]).install(monkeypatch)
    state = {"assets": {"img-1": {"type": "image", "format": "png", "data_base64": "AA=="}}}

    outcome = db.TimiDecisionsBackend().decide(state, BOX_Q, Cfg())

    assert outcome.available is False
    assert outcome.reason == "unsupported-question-type"
    assert script.calls == []


def test_unknown_question_type_never_enters_the_request(monkeypatch):
    script = FakeScript([_ok(DOC_NOUL_BODY)]).install(monkeypatch)
    outcome = db.TimiDecisionsBackend().decide("s", {"weird": {"type": "weird"}}, Cfg())
    assert outcome.reason == "unsupported-question-type"
    assert outcome.retryable is False
    assert script.calls == []


def test_disabled_configuration_makes_no_request(monkeypatch):
    script = FakeScript([_ok(DOC_NOUL_BODY)]).install(monkeypatch)
    outcome = db.TimiDecisionsBackend().decide(
        "s", {"is_urgent": {"type": "noul", "instructions": "x"}}, Cfg(enabled=False)
    )
    assert outcome.available is False
    assert outcome.reason == "disabled"
    assert script.calls == []


def test_state_is_sent_as_documented_type(monkeypatch):
    script = FakeScript([_ok(DOC_NOUL_BODY)]).install(monkeypatch)
    questions = {"is_urgent": {"type": "noul", "instructions": "x"}}
    backend = db.TimiDecisionsBackend()
    for state in ({"a": 1}, [1, 2], "text"):
        backend.decide(state, questions, Cfg())
    assert [call["payload"]["state"] for call in script.calls] == [{"a": 1}, [1, 2], "text"]


def test_cfg_model_and_base_url_overrides_are_honoured(monkeypatch):
    script = FakeScript([_ok({"model": "jev-next", "answers": {
        "is_urgent": {"type": "noul", "noul": 0.5}
    }})]).install(monkeypatch)

    outcome = db.TimiDecisionsBackend().decide(
        "s",
        {"is_urgent": {"type": "noul", "instructions": "x"}},
        Cfg(model="jev-next", base_url="http://example.invalid/proxy", timeout_s=3.5),
    )

    assert outcome.available is True
    assert script.calls[0]["url"] == "http://example.invalid/proxy/v1/decisions"
    assert script.calls[0]["payload"]["model"] == "jev-next"
    assert script.calls[0]["timeout_s"] == 3.5


def test_detail_is_scrubbed_and_truncated(monkeypatch):
    body = json.dumps({"error": {"message": f"leaked {TEST_KEY} " + "x" * 400}})
    FakeScript([{"status": 400, "body": body}]).install(monkeypatch)
    outcome = db.TimiDecisionsBackend().decide(
        "s", {"is_urgent": {"type": "noul", "instructions": "x"}}, Cfg()
    )
    assert TEST_KEY not in outcome.detail
    assert len(outcome.detail) <= db.MAX_DETAIL


def test_noul_probability_bounds_are_enforced(monkeypatch):
    for probability in (0.0, 1.0):
        FakeScript([_ok({"model": "jev-latest", "answers": {
            "is_urgent": {"type": "noul", "noul": probability}
        }})]).install(monkeypatch)
        ok = db.TimiDecisionsBackend().decide(
            "s", {"is_urgent": {"type": "noul", "instructions": "x"}}, Cfg()
        )
        assert ok.available is True
        assert ok.answers == {"is_urgent": {"value": probability, "confidence": None}}

    FakeScript([_ok({"model": "jev-latest", "answers": {
        "is_urgent": {"type": "noul", "noul": 1.01}
    }})]).install(monkeypatch)
    bad = db.TimiDecisionsBackend().decide(
        "s", {"is_urgent": {"type": "noul", "instructions": "x"}}, Cfg()
    )
    assert bad.available is False
    assert "noul for is_urgent is not a probability" in bad.detail


# ── decision.py integration ────────────────────────────────────────────────

def test_client_end_to_end_reports_the_only_transport(monkeypatch, tmp_path):
    FakeScript([_ok(DOC_CHOICE_BODY)]).install(monkeypatch)
    cfg = decision.DecisionConfig(
        enabled=True, extras={"api_key": TEST_KEY}, project_root=tmp_path
    )
    client = decision.DecisionClient(
        cfg=cfg,
        backend=db.TimiDecisionsBackend(),
        evidence_path=tmp_path / "triage-decisions.jsonl",
    )
    questions = {
        "department": {
            "type": "choice",
            "choices": list(DOC_CHOICE_CRITERIA),
            "instructions": DOC_CHOICE_INSTRUCTIONS,
        }
    }

    response = client.decide(DOC_STATE, questions, dp="dp1")

    assert response["available"] is True
    assert response["transport"] == "timi-decisions"
    assert response["model"] == "jev-latest"
    assert response["confidence_source"] == "api"
    assert response["answers"] == {"department": {"value": "billing", "confidence": 0.81}}
    assert response["reason"] is None


def test_frozen_outcome_shape_is_exported():
    outcome = db.BackendOutcome(
        available=False, reason="bad-response", retryable=True, answers=None, latency_ms=7
    )
    assert (outcome.available, outcome.reason, outcome.retryable, outcome.answers) == (
        False,
        "bad-response",
        True,
        None,
    )
    assert outcome.latency_ms == 7 and outcome.detail == ""
    assert db.DECISION_TYPES_LOCAL in (True, False)
    assert bool(db._DECISION_IMPORT_ERROR) is db.DECISION_TYPES_LOCAL


# ── probe: single transport, never raises ──────────────────────────────────

def test_probe_targets_collapsed_to_the_decisions_endpoint():
    assert db.PROBE_TARGETS == (("/v1/decisions", "timi-decisions"),)


def test_probe_matrix_reports_the_decisions_row(monkeypatch):
    FakeScript([_ok(DOC_NOUL_BODY)]).install(monkeypatch)
    rows = db.probe_matrix(Cfg())
    assert rows == [
        {
            "target": "timi-decisions:jev-latest",
            "method": "POST",
            "path": "/v1/decisions",
            "status": 200,
            "verdict": "ok",
        }
    ]
    assert TEST_KEY not in json.dumps(rows)


def test_probe_matrix_without_credential_is_hermetic(monkeypatch):
    def boom(*args, **kwargs):  # pragma: no cover - must never be called
        raise AssertionError("probe must not hit the network without a credential")

    monkeypatch.setattr(db, "_http_post", boom)
    rows = db.probe_matrix(Cfg(api_key=None))
    assert rows == [
        {
            "target": "timi-decisions:jev-latest",
            "method": "POST",
            "path": "/v1/decisions",
            "status": None,
            "verdict": "entry-unavailable",
        }
    ]
