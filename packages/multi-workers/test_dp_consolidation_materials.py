"""test_dp_consolidation_materials.py — T08: the timi transport's same-call
business choice + prepared-basis selection.

Scope (isolated copy only, no network, no provider, no live object):

- the one POST stays ``POST /v1/decisions`` with ``model=jev-latest`` and the
  bare ``Authorization`` value, and the original retry/time budget, boundary
  refusal (``box-requires-image``) and model-substitution refusal still hold;
- one prepared request carries the entry's own business question AND a second
  choice question over the PM-prepared basis catalog, so the model's choice and
  its basis are decided in the *same* request (no second call for a reason, no
  free-form ``reason``/``rationale`` field is ever read);
- a missing answer, a basis outside the catalog, a basis that does not apply to
  the answered choice, an out-of-bounds request or a branch-contract violation
  keeps the business decision count at 0 and never falls back to a default
  choice; the complete material/basis contract is never truncated (the budget
  gate refuses instead);
- the 25 retired ids are refused before any replay lookup, backend or POST, and
  a caller-owned replay lookup hit issues zero requests;
- transport attempts (real POSTs) and business decisions are counted
  separately, and each refused entry names its concrete field issues.

The fake HTTP seam is ``decision_backends._http_post`` (the module's only
network boundary); ``urllib.request.urlopen`` is poisoned in the valid-path test
so a request can never escape to a real endpoint.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import pytest

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_DIR))  # noqa: E402

import decision  # noqa: E402
import decision_backends as backends  # noqa: E402
import decision_book  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire  # noqa: E402

COPY_ROOT = PACKAGE_DIR.parents[1]  # .../implementation-worktree
CASES_DIR = PACKAGE_DIR / "decide_cases"
API_KEY = "t08-fixture-key-0123456789"
BUSINESS_QIDS = {
    "dp-w-type": "triage_type",
    "dp-pm-steer": "checkpoint_action",
    "dp-w-check-task": "reachability",
    "dp-QG": "qg_verdict",
    "dp-gate-approve": "gate_decision",
    "dp-sign-key": "q-conclusion",
    "dp-auto": "handling",
    "dp-route": "entry",
}
PREPARED_AT = "2026-10-26T12:00:00+00:00"


# ---------------------------------------------------------------------------
# Fixtures: legal material/preparation per entry (shapes mirror the protocol
# copy's own fixtures; no cross-test import).
# ---------------------------------------------------------------------------


def _auto_candidates() -> list[dict]:
    ids = ("patch-now", "ask-user", "rollback")
    return [
        {
            "id": candidate_id,
            "label": f"candidate {candidate_id}",
            "description": f"prepared handling {candidate_id}",
            "consequence": f"what follows from {candidate_id}",
            "risk": "bounded by the existing write face",
            "conditions": "only inside the already granted budget",
        }
        for candidate_id in ids
    ]


def _material(dp_id: str) -> dict:
    base = {
        "dp-w-type": {
            "task_goal": "ship the protocol entry",
            "task_requirements": "eight entries only",
            "task_deliverables": "registry + snapshot + tests",
            "images_required": False,
        },
        "dp-pm-steer": {
            "task_goal": "converge the task",
            "task_requirements": "keep the goal",
            "task_deliverables": "a real next action",
            "pm_decision_background": "budget is tight, the main line is unchanged",
        },
        "dp-w-check-task": {
            "task_goal": "finish the assigned slice",
            "reachability_facts": "the write face is free and the budget is enough",
            "completed": "read the files",
            "remaining": "write the test",
            "blockers": "none",
            "constraints": "existing task budget only",
        },
        "dp-QG": {
            "review_requirements": "all listed acceptance checks pass",
            "review_evidence": ["cmd: python -m pytest"],
            "review_findings": "no unresolved blocking finding",
            "uncovered_scope": "live deployment is out of scope",
        },
        "dp-gate-approve": {
            "gate_background": "stage close needs one decision",
            "current_state": "required keys are signed, integration check is green",
            "condition_evidence": ["evidence/close.md:1"],
            "pm_note": {
                "subject": "close stage S1",
                "planned_action": "record the stage close only",
                "basis": {
                    "goal": "spec 1.1",
                    "evidence": "evidence/close.md:1",
                    "budget": "unchanged hard budget",
                    "authority": "existing key authorization",
                },
            },
        },
        "dp-sign-key": {
            "delivery_goal": "deliver the eight-entry protocol",
            "actual_completion": "registry and snapshot are in place",
            "verification_evidence": {"verified": [], "unverified": []},
            "unfinished_impact": [],
        },
        "dp-auto": {
            "question": "the worker hit a write-face conflict",
            "background": {
                "task_goal": "keep the task moving",
                "current_state": "the conflicting file is claimed by another key",
                "tried": "asked the other window, no answer yet",
                "unknowns": "whether the other claim is still live",
                "constraints": "no new write permission is available",
            },
            "handling_options": _auto_candidates(),
        },
        "dp-route": {
            "decision_actor": "PM",
            "decision_object": "the next step of this task",
            "question": "which entry owns this temporary question",
        },
    }
    return json.loads(json.dumps(base[dp_id]))


def _preparation(dp_id: str, material: dict, *, applies_to: object = "all", ref: str | None = None) -> dict:
    legal = list(dpts.resolve_entry_choices(dp_id, material))
    targets = legal if applies_to == "all" else list(applies_to)
    first_ref = ref if ref is not None else next(iter(material))
    return {
        "basis_catalog": [
            {
                "id": "b-primary",
                "text": "PM-prepared reason drawn from the submitted material",
                "material_refs": [first_ref],
                "applies_to": targets,
            },
            {
                "id": "b-secondary",
                "text": "PM-prepared alternative reason for another choice",
                "material_refs": [first_ref],
                "applies_to": targets[-1:],
            },
        ],
        "prepared_at": PREPARED_AT,
    }


def _legal_choice(dp_id: str, material: dict) -> str:
    return dpts.resolve_entry_choices(dp_id, material)[0]


# ---------------------------------------------------------------------------
# Fake HTTP: the only network seam of the copy.
# ---------------------------------------------------------------------------


class FakeHttp:
    def __init__(self, responder):
        self.responder = responder
        self.calls: list[dict] = []

    def __call__(self, url, headers, payload, timeout_s):
        self.calls.append(
            {
                "url": url,
                "headers": dict(headers),
                "payload": json.loads(json.dumps(payload)),
                "timeout_s": timeout_s,
            }
        )
        return self.responder(len(self.calls), url, headers, payload)


@pytest.fixture
def http(monkeypatch):
    def install(responder):
        fake = FakeHttp(responder)
        monkeypatch.setattr(backends, "_http_post", fake)
        return fake

    return install


def _body(dp_id: str, answers: dict, *, model: str = "jev-latest", extra: dict | None = None) -> backends.HttpResponse:
    payload = {"model": model, "answers": answers, "usage": {"input_tokens": 3, "output_tokens": 4}}
    if extra:
        payload.update(extra)
    return backends.HttpResponse(200, "application/json", json.dumps(payload))


def _choice_answer(choice: object, confidence: float = 0.9) -> dict:
    return {"type": "choice", "choice": choice, "confidence": confidence}


def _legal_answers(dp_id: str, material: dict) -> dict:
    return {
        BUSINESS_QIDS[dp_id]: _choice_answer(_legal_choice(dp_id, material)),
        "basis_id": _choice_answer("b-primary"),
    }


def _ok_responder(dp_id: str, material: dict, **kwargs):
    return lambda *_args: _body(dp_id, _legal_answers(dp_id, material), **kwargs)


def _make_client(tmp_path: pathlib.Path, monkeypatch, **overrides) -> decision.DecisionClient:
    monkeypatch.delenv("TIMI_API_KEY", raising=False)
    cfg = decision.DecisionConfig(
        enabled=True,
        transport="timi-decisions",
        model="jev-latest",
        project_root=tmp_path,
        evidence_path=tmp_path / "triage-decisions.jsonl",
        backoff_base_s=0.0,
        **overrides,
    )
    cfg.api_key = API_KEY
    return decision.DecisionClient(cfg, sleep=lambda _seconds: None)


# ---------------------------------------------------------------------------
# 1. The isolated copy and the single transport seam.
# ---------------------------------------------------------------------------


def test_imports_and_http_seam_bind_the_isolated_copy() -> None:
    for module in (decision, backends, dpts):
        assert pathlib.Path(module.__file__).resolve().parent == PACKAGE_DIR, module.__file__
        assert COPY_ROOT in pathlib.Path(module.__file__).resolve().parents, module.__file__
    # The transport is one POST to the documented path and nothing else.
    assert backends.TIMI_BASE_URL.endswith("/llmproxy")
    assert backends.DECISIONS_PATH == "/v1/decisions"
    assert backends.DEFAULT_MODEL == "jev-latest"
    assert backends.TimiDecisionsBackend.name == "timi-decisions"


# ---------------------------------------------------------------------------
# 2. Every active entry: one same-call business choice + basis selection.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dp_id", dpts.ACTIVE_DP_IDS)
def test_each_entry_sends_one_same_call_choice_and_basis(
    dp_id: str, tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    fake = http(_ok_responder(dp_id, material))
    client = _make_client(tmp_path, monkeypatch)

    def forbidden_urlopen(*_args, **_kwargs):
        raise AssertionError("no real HTTP may leave the transport")

    monkeypatch.setattr("urllib.request.urlopen", forbidden_urlopen)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is True, result
    assert result["replayed"] is False
    assert result["business_decisions"] == 1
    assert result["attempts"] == 1
    assert result["transport_attempts"] == 1
    assert result["choice"] == _legal_choice(dp_id, material)
    assert result["basis_id"] == "b-primary"
    assert result["basis_text"] == "PM-prepared reason drawn from the submitted material"
    assert result["basis_source"] == dpts.BASIS_SOURCE == "pm-prepared"
    assert result["prepared_at"] == PREPARED_AT
    assert result["reason"] is None
    assert result["issues"] == []
    assert len(fake.calls) == 1

    call = fake.calls[0]
    assert call["url"].endswith("/v1/decisions"), call["url"]
    assert call["headers"]["Authorization"] == API_KEY  # bare key, no Bearer
    assert "Bearer" not in call["headers"]["Authorization"]
    assert call["payload"]["model"] == "jev-latest"

    questions = call["payload"]["questions"]
    business_qid = BUSINESS_QIDS[dp_id]
    assert set(questions) == {business_qid, "basis_id"}
    assert questions[business_qid]["type"] == "choice"
    assert set(questions[business_qid]["criteria"]) == set(
        dpts.resolve_entry_choices(dp_id, material)
    )
    basis_question = questions["basis_id"]
    assert basis_question["type"] == "choice"
    assert set(basis_question["criteria"]) == {"b-primary", "b-secondary"}
    assert basis_question["criteria"]["b-primary"] == (
        "PM-prepared reason drawn from the submitted material"
    )

    state = call["payload"]["state"]
    assert set(state) == {"material", "preparation"}
    # Preparation stays a separate input and carries no material/meta/context.
    assert set(state["preparation"]) == set(dpts.PREPARATION_KEYS)
    assert state["preparation"]["prepared_at"] == PREPARED_AT
    # The business material is the full allowlist projection, not a summary.
    assert state["material"] == dpts.model_state_for(dp_id, material)
    # Local identity/association never reaches the model.
    wire = json.dumps(call["payload"], ensure_ascii=False)
    for local_only in ("actor_role", "logical_id", "task_key", "trigger_id", "schema_version"):
        assert local_only not in wire
    # The credential is only in the Authorization header, never in the body or
    # the client's evidence line.
    assert API_KEY not in wire
    assert API_KEY not in json.dumps(result, ensure_ascii=False)
    evidence = tmp_path / "triage-decisions.jsonl"
    assert evidence.is_file()
    assert API_KEY not in evidence.read_text(encoding="utf-8")


@pytest.mark.parametrize("dp_id", dpts.ACTIVE_DP_IDS)
def test_invented_choice_or_out_of_catalog_basis_is_refused(
    dp_id: str, tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    client = _make_client(tmp_path, monkeypatch)

    invented_choice = http(
        lambda *_args: _body(
            dp_id,
            {
                BUSINESS_QIDS[dp_id]: _choice_answer("definitely-not-a-choice"),
                "basis_id": _choice_answer("b-primary"),
            },
        )
    )
    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )
    assert result["available"] is False
    assert result["reason"] == "bad-response"
    assert result["business_decisions"] == 0
    assert result["choice"] is None
    assert len(invented_choice.calls) == 1

    invented_basis = http(
        lambda *_args: _body(
            dp_id,
            {
                BUSINESS_QIDS[dp_id]: _choice_answer(_legal_choice(dp_id, material)),
                "basis_id": _choice_answer("b-invented"),
            },
        )
    )
    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )
    assert result["available"] is False
    assert result["reason"] == "bad-response"
    assert result["business_decisions"] == 0
    assert result["basis_id"] is None
    assert len(invented_basis.calls) == 1


# ---------------------------------------------------------------------------
# 3. Missing answer: no default, no second reason call.
# ---------------------------------------------------------------------------


def test_missing_basis_answer_is_refused_without_default_or_second_call(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-w-type"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    fake = http(
        lambda *_args: _body(
            dp_id, {BUSINESS_QIDS[dp_id]: _choice_answer(_legal_choice(dp_id, material))}
        )
    )
    client = _make_client(tmp_path, monkeypatch)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is False
    assert result["reason"] == "bad-response"
    assert result["choice"] is None
    assert result["basis_id"] is None
    assert result["business_decisions"] == 0
    # Exactly one request: a missing reason never triggers a second "explain it"
    # call, and the failed answer is kept (no default first choice is applied).
    assert result["attempts"] == 1
    assert result["transport_attempts"] == 1
    assert len(fake.calls) == 1
    assert "basis_id" in result["detail"]


def test_free_form_reason_fields_are_never_read_as_the_basis(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-QG"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    client = _make_client(tmp_path, monkeypatch)

    answerless = http(
        lambda *_args: _body(
            dp_id,
            {BUSINESS_QIDS[dp_id]: _choice_answer("pass")},
            extra={"reason": "the model felt confident", "rationale": "free prose"},
        )
    )
    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )
    assert result["available"] is False
    assert result["basis_text"] is None
    assert result["business_decisions"] == 0
    assert len(answerless.calls) == 1

    with_free_text = http(
        lambda *_args: _body(
            dp_id,
            {
                BUSINESS_QIDS[dp_id]: _choice_answer("pass"),
                "basis_id": _choice_answer("b-primary"),
            },
            extra={"reason": "free prose must not become the basis"},
        )
    )
    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )
    assert result["available"] is True
    assert result["basis_id"] == "b-primary"
    assert result["basis_text"] == "PM-prepared reason drawn from the submitted material"
    assert "free prose" not in json.dumps(result, ensure_ascii=False)
    assert len(with_free_text.calls) == 1


# ---------------------------------------------------------------------------
# 4. Basis applicability and preparation references.
# ---------------------------------------------------------------------------


def test_basis_not_applicable_to_the_answered_choice_is_refused(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-gate-approve"
    material = _material(dp_id)
    legal = list(dpts.resolve_entry_choices(dp_id, material))
    # Only the *other* choices are covered by the prepared basis item.
    preparation = {
        "basis_catalog": [
            {
                "id": "b-primary",
                "text": "PM-prepared reason for a different choice",
                "material_refs": ["gate_background"],
                "applies_to": legal[1:],
            }
        ],
        "prepared_at": PREPARED_AT,
    }
    choice = legal[0]
    fake = http(
        lambda *_args: _body(
            dp_id,
            {
                BUSINESS_QIDS[dp_id]: _choice_answer(choice),
                "basis_id": _choice_answer("b-primary"),
            },
        )
    )
    client = _make_client(tmp_path, monkeypatch)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is False
    assert result["reason"] == "bad-response"
    assert result["business_decisions"] == 0
    assert result["choice"] is None
    assert [issue["field"] for issue in result["issues"]] == ["basis_id"]
    assert "does not apply" in result["issues"][0]["issue"]
    assert len(fake.calls) == 1


def test_catalog_referencing_absent_material_is_refused_before_any_request(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-w-type"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material, ref="not-a-material-fact")
    fake = http(_ok_responder(dp_id, material))
    client = _make_client(tmp_path, monkeypatch)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is False
    assert result["reason"] == "input-incomplete"
    assert result["business_decisions"] == 0
    assert result["attempts"] == 0
    assert result["transport_attempts"] == 0
    assert fake.calls == []
    assert any(
        "does not reference a fact present in this material" in issue["issue"]
        for issue in result["issues"]
    ), result["issues"]


@pytest.mark.parametrize("preparation", [None, {}, {"basis_catalog": [], "prepared_at": PREPARED_AT}])
def test_missing_or_empty_catalog_blocks_the_entry_with_zero_request(
    preparation: object, tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-route"
    material = _material(dp_id)
    fake = http(_ok_responder(dp_id, material))
    client = _make_client(tmp_path, monkeypatch)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is False
    assert result["reason"] == "input-incomplete"
    assert result["business_decisions"] == 0
    assert result["transport_attempts"] == 0
    assert fake.calls == []


# ---------------------------------------------------------------------------
# 5. Out of bounds: refused, never truncated.
# ---------------------------------------------------------------------------


def test_oversized_request_is_refused_without_truncation_and_zero_post(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-w-type"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    fake = http(_ok_responder(dp_id, material))
    client = _make_client(tmp_path, monkeypatch, max_state_bytes=64)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is False
    assert result["reason"] == "budget-exhausted"
    assert result["business_decisions"] == 0
    assert result["transport_attempts"] == 0
    assert fake.calls == []


def test_long_core_material_is_sent_complete(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-w-type"
    material = _material(dp_id)
    long_requirement = "R" * 2000
    material["task_requirements"] = long_requirement
    preparation = _preparation(dp_id, material)
    fake = http(_ok_responder(dp_id, material))
    client = _make_client(tmp_path, monkeypatch)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is True
    sent = fake.calls[0]["payload"]["state"]["material"]["task_requirements"]
    assert sent == long_requirement
    assert len(sent) == 2000
    assert len(fake.calls) == 1


@pytest.mark.parametrize("dp_id", dpts.ACTIVE_DP_IDS)
def test_every_legal_choice_of_every_entry_is_accepted_in_one_same_call(
    dp_id: str, tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    """All shipped choices (VC-004/VC-040/VC-042 baseline) through the transport.

    Each iteration prepares a basis item that applies to that one choice, so an
    accepted answer proves the same-call pair and not a default. The selection
    still produces no action: the result carries decision facts plus the frozen
    transport counters only, never an executed/released/settled field.
    """
    for choice in dpts.resolve_entry_choices(dp_id, _material(dp_id)):
        material = _material(dp_id)
        if dp_id == "dp-w-check-task" and choice == "investigate":
            material["investigation"] = {
                "unknown": "whether the claim is still live",
                "evidence_source": "the claim file under the project lock",
                "budget": "the current task budget only",
                "stop_condition": "the claim owner answers or the budget ends",
            }
        if dp_id == "dp-QG" and choice == "reopen":
            material["basis_issue"] = "the review requirement itself is wrong"
        preparation = {
            "basis_catalog": [
                {
                    "id": f"b-{choice}",
                    "text": f"PM-prepared reason for {choice}",
                    "material_refs": [next(iter(material))],
                    "applies_to": [choice],
                }
            ],
            "prepared_at": PREPARED_AT,
        }
        fake = http(
            lambda *_args, _choice=choice: _body(
                dp_id,
                {
                    BUSINESS_QIDS[dp_id]: _choice_answer(_choice),
                    "basis_id": _choice_answer(f"b-{_choice}"),
                },
            )
        )
        client = _make_client(tmp_path, monkeypatch)

        result = client.request_prepared(
            dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
        )

        assert result["available"] is True, (dp_id, choice, result)
        assert result["choice"] == choice
        assert result["basis_id"] == f"b-{choice}"
        assert result["business_decisions"] == 1
        assert result["transport_attempts"] == 1
        assert len(fake.calls) == 1
        assert set(result) == set(decision._PREPARED_RESULT_FIELDS)
        assert not {"action", "released", "executed", "settled", "done"} & set(result)


def test_sign_key_keeps_real_empty_arrays_and_refuses_null(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    """AC-051 at the transport gate: ``[]`` is material, null/missing is not."""
    dp_id = "dp-sign-key"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    fake = http(_ok_responder(dp_id, material))
    client = _make_client(tmp_path, monkeypatch)

    accepted = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )
    assert accepted["available"] is True
    assert accepted["business_decisions"] == 1
    assert len(fake.calls) == 1

    for path, nulled in (
        ("verification_evidence.verified", {"verified": None, "unverified": []}),
        ("verification_evidence.unverified", {"verified": [], "unverified": None}),
    ):
        broken = _material(dp_id)
        broken["verification_evidence"] = nulled
        refused = client.request_prepared(
            dp_id, broken, _preparation(dp_id, broken), actor_role=dpts.ENTRY_ROLES[dp_id]
        )
        assert refused["available"] is False
        assert refused["reason"] == "input-incomplete"
        assert refused["business_decisions"] == 0
        assert any(issue["field"] == path for issue in refused["issues"])

    missing = _material(dp_id)
    missing.pop("unfinished_impact")
    refused = client.request_prepared(
        dp_id, missing, _preparation(dp_id, missing), actor_role=dpts.ENTRY_ROLES[dp_id]
    )
    assert refused["reason"] == "input-incomplete"
    assert refused["transport_attempts"] == 0
    assert len(fake.calls) == 1  # only the one accepted request above


# ---------------------------------------------------------------------------
# 6. Retired ids and replay: zero requests, zero business decisions.
# ---------------------------------------------------------------------------


RETIRED_25 = tuple(record.id for record in dpts.RETIRED_DP_REGISTRY)


def test_retired_directory_has_the_twenty_five_old_ids() -> None:
    assert len(RETIRED_25) == 25
    assert set(RETIRED_25) == set(dpts.RETIRED_DP_IDS)


@pytest.mark.parametrize("old_id", RETIRED_25)
def test_every_retired_id_is_refused_before_any_request(
    old_id: str, tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    material = _material("dp-w-type")
    preparation = _preparation("dp-w-type", material)
    fake = http(_ok_responder("dp-w-type", material))
    client = _make_client(tmp_path, monkeypatch)

    result = client.request_prepared(
        old_id, material, preparation, actor_role="pm"
    )

    assert result["available"] is False
    assert result["reason"] == "entry-unavailable"
    assert result["business_decisions"] == 0
    assert result["attempts"] == 0
    assert result["transport_attempts"] == 0
    assert result["choice"] is None
    assert result["basis_id"] is None
    assert "retired" in result["detail"]
    assert fake.calls == []


def test_retired_ids_are_counted_as_zero_model_and_business_calls(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    material = _material("dp-w-type")
    preparation = _preparation("dp-w-type", material)
    fake = http(_ok_responder("dp-w-type", material))
    client = _make_client(tmp_path, monkeypatch)

    results = [
        client.request_prepared(old_id, material, preparation, actor_role="pm")
        for old_id in RETIRED_25
    ]

    assert len(results) == 25
    assert all(result["reason"] == "entry-unavailable" for result in results)
    assert sum(result["business_decisions"] for result in results) == 0
    assert sum(result["transport_attempts"] for result in results) == 0
    assert fake.calls == []


def test_replay_lookup_hit_issues_no_request(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-w-type"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    fake = http(_ok_responder(dp_id, material))
    client = _make_client(tmp_path, monkeypatch)
    seen: list[tuple[str, str]] = []

    def replay_hit(request_dp: str, logical_id: str) -> bool:
        seen.append((request_dp, logical_id))
        return True

    result = client.request_prepared(
        dp_id,
        material,
        preparation,
        actor_role=dpts.ENTRY_ROLES[dp_id],
        logical_id="t08-replay",
        replay_check=replay_hit,
    )

    assert seen == [(dp_id, "t08-replay")]
    assert result["replayed"] is True
    assert result["business_decisions"] == 0
    assert result["attempts"] == 0
    assert result["transport_attempts"] == 0
    assert fake.calls == []


def test_replay_lookup_miss_proceeds_with_one_request(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-w-type"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    fake = http(_ok_responder(dp_id, material))
    client = _make_client(tmp_path, monkeypatch)

    result = client.request_prepared(
        dp_id,
        material,
        preparation,
        actor_role=dpts.ENTRY_ROLES[dp_id],
        logical_id="t08-fresh",
        replay_check=lambda _dp, _logical: False,
    )

    assert result["replayed"] is False
    assert result["business_decisions"] == 1
    assert len(fake.calls) == 1


# ---------------------------------------------------------------------------
# 7. Preserved transport contract: no model switch, retries, bare key, box.
# ---------------------------------------------------------------------------


def test_foreign_model_response_is_refused_without_fallback(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-w-type"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    fake = http(
        lambda *_args: _body(
            dp_id, _legal_answers(dp_id, material), model="some-other-model"
        )
    )
    client = _make_client(tmp_path, monkeypatch)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is False
    assert result["reason"] == "bad-response"
    assert result["business_decisions"] == 0
    assert len(fake.calls) == 1


def test_retry_budget_and_bare_authorization_are_preserved(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-w-type"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    answers = _legal_answers(dp_id, material)

    def responder(index, *_args):
        if index == 1:
            return backends.HttpResponse(503, "text/plain", "service unavailable")
        return _body(dp_id, answers)

    fake = http(responder)
    client = _make_client(tmp_path, monkeypatch, max_retries=1)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is True
    assert result["business_decisions"] == 1
    assert result["attempts"] == 2
    assert result["transport_attempts"] == 2
    assert len(fake.calls) == 2
    for call in fake.calls:
        assert call["headers"]["Authorization"] == API_KEY
        assert call["payload"]["model"] == "jev-latest"
        assert call["url"].endswith("/v1/decisions")


def test_box_question_is_still_refused_with_zero_http(tmp_path: pathlib.Path, monkeypatch, http) -> None:
    fake = http(lambda *_args: pytest.fail("box must never reach HTTP"))
    monkeypatch.delenv("TIMI_API_KEY", raising=False)
    cfg = decision.DecisionConfig(enabled=True, project_root=tmp_path)
    cfg.api_key = API_KEY

    outcome = backends.TimiDecisionsBackend().decide(
        "state", {"q": {"type": "box"}}, cfg
    )

    assert outcome.available is False
    assert outcome.reason == "box-requires-image"
    assert fake.calls == []


# ---------------------------------------------------------------------------
# 8. Role and branch contracts: refused before/after the one request.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("role", [None, "", "agent", "human"])
def test_missing_or_non_eligible_role_blocks_with_zero_request(
    role: object, tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-w-check-task"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    fake = http(_ok_responder(dp_id, material))
    client = _make_client(tmp_path, monkeypatch)

    result = client.request_prepared(dp_id, material, preparation, actor_role=role)

    assert result["available"] is False
    assert result["reason"] == "input-incomplete"
    assert result["business_decisions"] == 0
    assert fake.calls == []
    assert [issue["field"] for issue in result["issues"]] == ["actor_role"]


def test_branch_contract_violation_after_the_answer_is_refused(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-QG"
    material = _material(dp_id)  # no `basis_issue`: reopen is not legal here
    preparation = _preparation(dp_id, material)
    fake = http(
        lambda *_args: _body(
            dp_id,
            {
                BUSINESS_QIDS[dp_id]: _choice_answer("reopen"),
                "basis_id": _choice_answer("b-primary"),
            },
        )
    )
    client = _make_client(tmp_path, monkeypatch)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is False
    assert result["reason"] == "bad-response"
    assert result["business_decisions"] == 0
    assert result["choice"] is None
    assert any(issue["field"] == "basis_issue" for issue in result["issues"])
    assert len(fake.calls) == 1


# ---------------------------------------------------------------------------
# 9. Attempt vs business decision: two separate counters.
# ---------------------------------------------------------------------------


def test_attempt_and_business_decision_counters_are_separate(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    dp_id = "dp-route"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    answers = _legal_answers(dp_id, material)

    def responder(index, *_args):
        if index < 3:
            return backends.HttpResponse(503, "text/plain", "service unavailable")
        return _body(dp_id, answers)

    fake = http(responder)
    client = _make_client(tmp_path, monkeypatch, max_retries=2)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is True
    assert result["attempts"] == 3
    assert result["transport_attempts"] == 3
    assert result["business_decisions"] == 1
    assert len(fake.calls) == 3

    failed = http(lambda *_args: backends.HttpResponse(503, "text/plain", "down"))
    client = _make_client(tmp_path, monkeypatch, max_retries=1)
    refused = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )
    assert refused["available"] is False
    assert refused["attempts"] == 2
    assert refused["transport_attempts"] == 2
    assert refused["business_decisions"] == 0
    assert len(failed.calls) == 2


# ---------------------------------------------------------------------------
# 10. The question ceiling of a prepared request is a refusal, not a raise.
# ---------------------------------------------------------------------------


def test_question_ceiling_is_a_prepared_refusal_not_an_exception(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    """A legal pair under ``max_questions=1`` must not escape as an exception.

    The same-call request needs two questions (the entry's business question and
    the prepared basis). The generic ``decide`` face raises ``DecisionInputError``
    above ``max_questions``; a prepared request has to report that as a visible
    refusal with zero HTTP and zero business decisions instead of letting the
    exception escape - and the configured ceiling must stay what it was, never be
    raised or loosened to make the pair fit.
    """
    dp_id = "dp-w-type"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    fake = http(_ok_responder(dp_id, material))
    client = _make_client(tmp_path, monkeypatch, max_questions=1)

    # No ``pytest.raises`` here: escaping with DecisionInputError is the defect.
    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is False
    assert result["reason"] == "budget-exhausted"
    assert result["business_decisions"] == 0
    assert result["attempts"] == 0
    assert result["transport_attempts"] == 0
    assert result["choice"] is None
    assert result["basis_id"] is None
    assert result["answers"] is None
    assert fake.calls == []
    # The refusal names the real boundary and does not pretend to have called.
    assert "max_questions=1" in result["detail"]
    # The ceiling itself is untouched by the refusal.
    assert client.cfg.max_questions == 1


def test_question_ceiling_control_still_accepts_a_legal_pair(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    """Control: at ``max_questions=2`` the pair still fits - the ceiling holds.

    This is the non-regression half of the boundary: the fix refuses above the
    configured value, it does not widen, disable or ignore the documented
    default.
    """
    dp_id = "dp-route"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    fake = http(_ok_responder(dp_id, material))
    client = _make_client(tmp_path, monkeypatch, max_questions=2)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    assert result["available"] is True, result
    assert result["business_decisions"] == 1
    assert len(fake.calls) == 1
    # The documented default is still 8: nothing in this fix widened it.
    assert decision.DecisionConfig().max_questions == 8


# ---------------------------------------------------------------------------
# 11. Replay: only an explicit bool proves hit/miss.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("lookup", [None, "unknown", "true", "false", 1, 0, [], {}])
def test_non_bool_replay_lookup_result_fails_closed(
    lookup: object, tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    """``null``/unknown/other shapes prove neither a hit nor a miss.

    Truthifying the result fabricated a replay hit for ``"unknown"`` and a
    novelty claim (one real POST, one business decision) for ``null``; neither is
    a proven lookup result, so the request fails closed with zero HTTP and zero
    business decisions.
    """
    dp_id = "dp-w-type"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)
    fake = http(_ok_responder(dp_id, material))
    client = _make_client(tmp_path, monkeypatch)
    seen: list[tuple[str, str]] = []

    def replay_illegal(request_dp: str, logical_id: str) -> object:
        seen.append((request_dp, logical_id))
        return lookup

    result = client.request_prepared(
        dp_id,
        material,
        preparation,
        actor_role=dpts.ENTRY_ROLES[dp_id],
        logical_id="t08-illegal-replay",
        replay_check=replay_illegal,
    )

    assert seen == [(dp_id, "t08-illegal-replay")]  # the lookup really ran
    assert result["available"] is False
    assert result["replayed"] is False
    assert result["reason"] == "entry-unavailable"
    assert result["business_decisions"] == 0
    assert result["attempts"] == 0
    assert result["transport_attempts"] == 0
    assert result["choice"] is None
    assert result["basis_id"] is None
    assert fake.calls == []
    assert "bool" in result["detail"]


def test_bool_replay_lookup_controls_still_prove_hit_and_miss(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    """Control: the two legal answers keep their documented meaning."""
    dp_id = "dp-w-type"
    material = _material(dp_id)
    preparation = _preparation(dp_id, material)

    hit_fake = http(_ok_responder(dp_id, material))
    hit_client = _make_client(tmp_path, monkeypatch)
    hit = hit_client.request_prepared(
        dp_id,
        material,
        preparation,
        actor_role=dpts.ENTRY_ROLES[dp_id],
        logical_id="t08-bool-hit",
        replay_check=lambda _dp, _logical: True,
    )
    assert hit["available"] is True
    assert hit["replayed"] is True
    assert hit["business_decisions"] == 0
    assert hit["transport_attempts"] == 0
    assert hit_fake.calls == []

    miss_fake = http(_ok_responder(dp_id, material))
    miss_client = _make_client(tmp_path, monkeypatch)
    miss = miss_client.request_prepared(
        dp_id,
        material,
        preparation,
        actor_role=dpts.ENTRY_ROLES[dp_id],
        logical_id="t08-bool-miss",
        replay_check=lambda _dp, _logical: False,
    )
    assert miss["available"] is True
    assert miss["replayed"] is False
    assert miss["business_decisions"] == 1
    assert len(miss_fake.calls) == 1


# ---------------------------------------------------------------------------
# 12. Retired ids are refused before replay, credential and backend.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("old_id", RETIRED_25)
def test_retired_id_is_refused_before_replay_credential_and_backend(
    old_id: str, tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    """Order guard: the retired disposition is decided before everything else.

    The refusal must land before the caller-owned replay lookup, before the
    credential snapshot and before any backend resolution, so no path of a
    retired id can spend a model call or invent a business decision.
    """
    material = _material("dp-w-type")
    preparation = _preparation("dp-w-type", material)
    fake = http(lambda *_args: pytest.fail("a retired id must never reach HTTP"))
    client = _make_client(tmp_path, monkeypatch)
    seen: list[tuple[str, str]] = []

    def replay_must_not_run(request_dp: str, logical_id: str) -> bool:
        seen.append((request_dp, logical_id))
        return True

    def credential_must_not_run(*_args, **_kwargs):
        raise AssertionError("a retired id must not resolve a credential")

    monkeypatch.setattr(decision, "credential_snapshot", credential_must_not_run)

    result = client.request_prepared(
        old_id,
        material,
        preparation,
        actor_role="pm",
        logical_id="t08-retired-order",
        replay_check=replay_must_not_run,
    )

    assert seen == []
    assert result["available"] is False
    assert result["replayed"] is False
    assert result["reason"] == "entry-unavailable"
    assert "retired" in result["detail"]
    assert result["business_decisions"] == 0
    assert result["attempts"] == 0
    assert result["transport_attempts"] == 0
    assert fake.calls == []


# ---------------------------------------------------------------------------
# 13. Transport record vs business decision: one layer each.
# ---------------------------------------------------------------------------


def test_transport_record_and_business_refusal_stay_separate_layers(
    tmp_path: pathlib.Path, monkeypatch, http
) -> None:
    """A transport answer is recorded; a refused pair adds no business decision.

    The generic evidence line is the *transport* row: it records that the answer
    came back and it structurally carries no business fields (no choice, basis,
    business-decision count, replay flag or preparation timestamp). The business
    truth lives only on the prepared result. The two coexist here - which is
    exactly why this row must never be read as "a valid business decision was
    added"; the adoption chain (store/CLI consumers) is not exercised here.
    """
    dp_id = "dp-gate-approve"
    material = _material(dp_id)
    legal = list(dpts.resolve_entry_choices(dp_id, material))
    preparation = {
        "basis_catalog": [
            {
                "id": "b-primary",
                "text": "PM-prepared reason for a different choice",
                "material_refs": ["gate_background"],
                "applies_to": legal[1:],
            }
        ],
        "prepared_at": PREPARED_AT,
    }
    choice = legal[0]
    fake = http(
        lambda *_args: _body(
            dp_id,
            {
                BUSINESS_QIDS[dp_id]: _choice_answer(choice),
                "basis_id": _choice_answer("b-primary"),
            },
        )
    )
    client = _make_client(tmp_path, monkeypatch)

    result = client.request_prepared(
        dp_id, material, preparation, actor_role=dpts.ENTRY_ROLES[dp_id]
    )

    # Business layer: binding refusal, no default, no business decision.
    assert result["available"] is False
    assert result["reason"] == "bad-response"
    assert result["business_decisions"] == 0
    assert result["choice"] is None
    # Transport layer: the answer really was fetched (one attempt, one POST).
    assert result["attempts"] == 1
    assert result["transport_attempts"] == 1
    assert len(fake.calls) == 1

    evidence = tmp_path / "triage-decisions.jsonl"
    rows = [
        json.loads(line)
        for line in evidence.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    assert len(rows) == 1
    row = rows[0]
    # The row is the frozen transport record, never a business ledger entry.
    assert set(row) == set(decision._EVIDENCE_FIELDS)
    assert not {
        "choice",
        "basis_id",
        "basis_text",
        "business_decisions",
        "replayed",
        "prepared_at",
    } & set(row)
    assert row["available"] is True  # the transport answered ...
    assert row["dp"] == dp_id
    assert row["attempts"] == 1
    # ... and the refused business layer never rewrote that transport fact.
    assert result["business_decisions"] == 0


# ---------------------------------------------------------------------------
# 14. The observation seam joins the canonical schema-3 book view (T28 R2).
#
# The seam used to require a legacy top-level ``book["state"]``, which
# ``decision_book.check_book`` refuses by contract: every schema-3 book
# (``material`` + ``preparation`` + optional ``context``) was therefore refused
# as ``input-incomplete`` before the transport (B-observation-book-join). These
# tests drive the real ``decide_for(observation=...)`` chain with the shipped
# generated case books and a ``FakeBackend`` (no live provider, no credential).
# ---------------------------------------------------------------------------


OBSERVE_SUBMISSION = "sub-t28r2"


def _case_book(dp_id: str) -> dict:
    """The shipped generated schema-3 case book, with local evidence only.

    The business ``material``, the PM-prepared ``preparation`` and the optional
    ``context`` stay the generator's real output; only ``notes.evidence`` is
    rewritten to a trivial local command so a temp control root runs the real
    typed gate (the shipped ``path:line`` references point into this checkout).
    """
    case = json.loads((CASES_DIR / f"{dp_id}.json").read_text(encoding="utf-8"))
    book = json.loads(json.dumps(case["book"], ensure_ascii=False))
    book["notes"] = {
        "evidence": {
            path: "cmd: true" for path in decision_book.required_state_paths(dp_id)
        }
    }
    return book


def _observe_project(tmp_path: pathlib.Path) -> pathlib.Path:
    project = tmp_path / "project"
    (project / ".mw").mkdir(parents=True, exist_ok=True)
    (project / ".mw" / "decide.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "transport": "timi-decisions",
                "model": "jev-latest",
                "timeout_s": 5,
                "max_retries": 0,
                "api_key": API_KEY,
            },
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return project


def _observe_scope(root: pathlib.Path):
    redactor = decision.credential_redactor(
        extra_secrets=(API_KEY,), env={}, auth_path=root / "no-auth.json"
    )
    return decision_wire.test_scope(
        root,
        project_id=decision_wire.project_id_for(root),
        submission_id=OBSERVE_SUBMISSION,
        redact=redactor,
        evidence_path=root / "evidence.jsonl",
        warn=lambda _line: None,
    )


def _observe_client(tmp_path: pathlib.Path, monkeypatch, *, scope, backend):
    monkeypatch.delenv("TIMI_API_KEY", raising=False)
    cfg = decision.DecisionConfig(
        enabled=True,
        transport="timi-decisions",
        model="jev-latest",
        project_root=tmp_path,
        evidence_path=tmp_path / "triage-decisions.jsonl",
        backoff_base_s=0.0,
    )
    cfg.api_key = API_KEY
    return decision.DecisionClient(
        cfg,
        backend=backend,
        wire_scope=scope,
        sleep=lambda _seconds: None,
    )


def _prepared_answer(dp_id: str, material: dict, preparation: dict) -> tuple[str, str]:
    """One legal (choice, basis) pair actually prepared by this generated book.

    The full registry menu stays intact, but a factual material's non-empty
    prepared basis may cover only a subset of the entry's choices (the shipped
    QG book prepares only ``fix``; the sign-key book ``continue``/``user-confirm``).
    A synthetic FakeBackend answer is read from the book's own supported pair;
    it never defaults to the registry's first choice or to a production answer.
    """
    catalog = preparation["basis_catalog"]
    for choice in dpts.resolve_entry_choices(dp_id, material):
        for item in catalog:
            if choice in item["applies_to"]:
                return choice, item["id"]
    raise AssertionError(f"no prepared choice+basis pair for {dp_id}")


def _observe_backend(dp_id: str, material: dict, preparation: dict) -> decision.FakeBackend:
    choice, basis_id = _prepared_answer(dp_id, material, preparation)
    return decision.FakeBackend(
        [
            decision.BackendOutcome(
                available=True,
                reason=None,
                retryable=False,
                answers={
                    BUSINESS_QIDS[dp_id]: {"value": choice, "confidence": 0.9},
                    "basis_id": {"value": basis_id, "confidence": 0.9},
                },
                latency_ms=2,
                detail="",
            )
        ]
    )


def _observe(
    project: pathlib.Path,
    scope,
    client: decision.DecisionClient,
    book: dict,
    dp_id: str,
    *,
    state: dict | None = None,
):
    local_state = decision_book.book_state(book) if state is None else state
    return dpts.decide_for(
        dp_id,
        dpts.Trigger.from_mapping(local_state, trigger_id=OBSERVE_SUBMISSION),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=dpts.Observation(
            scope=scope, book=book, submission_id=OBSERVE_SUBMISSION
        ),
    )


def _tree(path: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for item in sorted(path.rglob("*")):
        if item.is_file():
            out[item.relative_to(path).as_posix()] = hashlib.sha256(
                item.read_bytes()
            ).hexdigest()
    return out


def _test_events(root: pathlib.Path) -> list[dict]:
    sink = decision_wire.test_wire_sink(root)
    return list(decision_wire.read_events(sink).events)


def _assert_refused_without_send(
    outcome, backend: decision.FakeBackend, project: pathlib.Path, root: pathlib.Path
) -> None:
    assert outcome.status == "escalated", outcome
    assert outcome.escalated_reason == "input-incomplete", outcome.detail
    assert outcome.snapshot_ref is None, "refused material must not be snapshotted"
    assert backend.calls == [], "refused material must not reach the model"
    events = _test_events(root)
    assert not [event for event in events if event.get("kind") == "book-snapshot"]
    ends = [event for event in events if event.get("kind") == "decision-end"]
    assert len(ends) == 1
    assert ends[0]["book_ref"] is None, "no dangling book reference"
    assert not (project / dpts.DECISIONS_RELATIVE_PATH).exists()
    assert not decision_wire.production_wire_sink(project).exists()


@pytest.mark.parametrize("dp_id", dpts.ACTIVE_DP_IDS)
def test_observation_accepts_every_generated_schema3_case_book(
    dp_id: str, tmp_path: pathlib.Path, monkeypatch
) -> None:
    """All eight active entries: real generated book -> real observe chain.

    The book is the shipped generator output (schema 3: material + preparation),
    the state comes from ``decision_book.book_state`` and the answer from a
    ``FakeBackend``. Acceptance here proves the seam joins the canonical view
    instead of the legacy ``state`` key (the transport really ran and the book
    snapshot exists), and that the observation keeps its zero-effect contract
    (no executor, gate, signoff or production row).

    Every entry is a strict positive, ``dp-auto`` included: its dynamic
    candidate vocabulary (``patch-now``/``ask-user``/``rollback``) is resolved
    with the entry id on the answer check, so the generated book is answered
    instead of being reported as an illegal value.
    """
    book = _case_book(dp_id)
    material = book["material"]
    project = _observe_project(tmp_path)
    root = tmp_path / "test-run"
    root.mkdir()
    scope = _observe_scope(root)
    backend = _observe_backend(dp_id, material, book["preparation"])
    client = _observe_client(tmp_path, monkeypatch, scope=scope, backend=backend)
    before = _tree(project)

    outcome = _observe(project, scope, client, book, dp_id)

    # Seam facts that must hold for every entry: the book is not refused, the
    # real transport ran exactly once and the claim was snapshotted.
    assert "observation book refused" not in (outcome.detail or ""), outcome.detail
    assert len(backend.calls) == 1, "the generated book must reach the transport"
    sent = backend.calls[0]["state"]
    expected = dpts.send_state(dp_id, decision_book.book_state(book))[0]
    assert sent == {"material": expected, "preparation": book["preparation"]}
    assert backend.calls[0]["questions"]["basis_id"]["labels"] == {
        item["id"]: item["text"] for item in book["preparation"]["basis_catalog"]
    }
    assert outcome.snapshot_ref is not None
    snapshots = [e for e in _test_events(root) if e.get("kind") == "book-snapshot"]
    assert len(snapshots) == 1
    assert snapshots[0]["book_ref"] == outcome.snapshot_ref
    document = json.loads(snapshots[0]["book"]["text"])
    assert document["state"] == sent
    assert document["book"] == book
    assert document["candidates"]["basis_id"] == [
        {"id": item["id"], "label": item["text"]}
        for item in book["preparation"]["basis_catalog"]
    ]

    assert outcome.actual_action is None, "an observation never executes"
    assert outcome.observation is not None and outcome.observation["observe_only"] is True
    assert outcome.preview["executor_invoked"] is False
    assert outcome.preview["action_outcome"] == "unknown"
    assert outcome.preview["would_act"] is False or outcome.preview["mode"] != "suggest"
    assert outcome.status == "suggested", outcome.detail
    assert outcome.escalated_reason is None
    assert outcome.answer is not None
    # No production row, gate, signoff or authority artifact was written.
    assert _tree(project) == before, "an observation writes nothing into the project"


def _snapshot_candidates(root: pathlib.Path) -> dict:
    """The rendered candidate enum the decision stored for a human answer."""
    snapshots = [e for e in _test_events(root) if e.get("kind") == "book-snapshot"]
    assert len(snapshots) == 1, snapshots
    document = json.loads(snapshots[0]["book"]["text"])
    return document["candidates"]


AUTO_SHIPPED_IDS = ("wire-facets-now", "split-projection-task", "escalate-to-human")


def _auto_book(ids) -> dict:
    """The shipped dp-auto book with a different PM-prepared candidate set.

    Only the generated material changes, and every basis entry's ``applies_to``
    is rewritten with it: the book gate joins the prepared basis to the rendered
    legal choices, so a candidate edit that left the basis behind is refused
    (that join is why the two edits travel together).
    """
    book = _case_book("dp-auto")
    book["material"]["handling_options"] = [
        {
            "id": candidate_id,
            "label": f"candidate {candidate_id}",
            "description": f"prepared handling {candidate_id}",
            "consequence": f"what follows from {candidate_id}",
            "risk": "bounded by the existing write face",
            "conditions": "only inside the already granted budget",
        }
        for candidate_id in ids
    ]
    for entry in book["preparation"]["basis_catalog"]:
        entry["applies_to"] = list(ids)
    return book


def test_auto_candidates_are_resolved_with_the_entry_id_not_the_legacy_bound(
    tmp_path: pathlib.Path,
) -> None:
    """The active dynamic entry's free-form vocabulary is the one that resolves.

    Same questions, same state: with the entry id the PM-prepared candidates
    render; without it the legacy ``cN``/2..5 contract refuses the very list the
    book gate accepted, which is the defect this round closes.
    """
    state = decision_book.book_state(_auto_book(AUTO_SHIPPED_IDS))
    point = dpts.get_decision_point("dp-auto")
    questions = dpts.questions_map(point)

    rendered = dpts.dynamic_choice_labels(questions, state, dp_id="dp-auto")
    assert rendered == {
        "handling": {
            candidate_id: f"candidate {candidate_id}"
            for candidate_id in AUTO_SHIPPED_IDS
        }
    }
    assert dpts.resolve_dynamic_choices(questions, state, dp_id="dp-auto") == {
        "handling": AUTO_SHIPPED_IDS
    }
    # The same call without the id is the legacy contract: it must not render.
    assert dpts.dynamic_choice_labels(questions, state) is None
    assert dpts.resolve_dynamic_choices(questions, state) is None


@pytest.mark.parametrize(
    "ids",
    [
        AUTO_SHIPPED_IDS,
        ("review-only", "ship-it"),
        ("a", "b", "c", "d", "e"),
    ],
)
def test_observation_answers_every_pm_candidate_vocabulary(
    ids, tmp_path: pathlib.Path, monkeypatch
) -> None:
    """Non-``cN`` ids and 2..N candidates are answered, rendered and snapshotted."""
    book = _auto_book(ids)
    project = _observe_project(tmp_path)
    root = tmp_path / "test-run"
    root.mkdir()
    scope = _observe_scope(root)
    backend = _observe_backend("dp-auto", book["material"], book["preparation"])
    client = _observe_client(tmp_path, monkeypatch, scope=scope, backend=backend)
    before = _tree(project)

    outcome = _observe(project, scope, client, book, "dp-auto")

    assert outcome.status == "suggested", outcome.detail
    assert outcome.escalated_reason is None
    assert outcome.answer["handling"] == {"value": ids[0], "confidence": 0.9}
    assert outcome.answer["basis_id"]["value"] in {
        item["id"] for item in book["preparation"]["basis_catalog"] if ids[0] in item["applies_to"]
    }
    assert len(backend.calls) == 1, "the generated book must reach the transport once"
    assert outcome.actual_action is None
    assert outcome.preview["executor_invoked"] is False
    # The rendered enum is the one stored for a later human answer: the
    # candidate ids themselves, not a display-only label.
    assert _snapshot_candidates(root)["handling"] == [
        {"id": candidate_id, "label": f"candidate {candidate_id}"}
        for candidate_id in ids
    ]
    assert _tree(project) == before, "an observation writes nothing into the project"


def test_observation_refuses_an_answer_outside_the_rendered_candidates(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """A wrong or legacy ``cN`` pick is a missing answer, never an action."""
    book = _auto_book(("review-only", "ship-it"))
    project = _observe_project(tmp_path)
    root = tmp_path / "test-run"
    root.mkdir()
    scope = _observe_scope(root)
    backend = decision.FakeBackend(
        [
            decision.BackendOutcome(
                available=True,
                reason=None,
                retryable=False,
                answers={
                    "handling": {"value": "c1", "confidence": 0.99},
                    "basis_id": {
                        "value": book["preparation"]["basis_catalog"][0]["id"],
                        "confidence": 0.99,
                    },
                },
                latency_ms=2,
                detail="",
            )
        ]
    )
    client = _observe_client(tmp_path, monkeypatch, scope=scope, backend=backend)
    before = _tree(project)

    outcome = _observe(project, scope, client, book, "dp-auto")

    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "low-confidence", outcome.detail
    assert "illegal value for handling" in outcome.detail, outcome.detail
    assert outcome.actual_action is None
    assert outcome.preview["executor_invoked"] is False
    assert outcome.preview["would_act"] is False
    assert _tree(project) == before, "a refused answer writes nothing into the project"
    ends = [e for e in _test_events(root) if e.get("kind") == "decision-end"]
    assert len(ends) == 1 and ends[0]["status"] == "escalated"
    assert ends[0]["escalated_reason"] == "low-confidence"


@pytest.mark.parametrize(
    "ids",
    [
        ("review-only",),
        ("review-only", "review-only"),
    ],
)
def test_observation_refuses_an_illegal_pm_candidate_set_before_send(
    ids, tmp_path: pathlib.Path, monkeypatch
) -> None:
    """One candidate or a duplicate id is not a choice: zero HTTP, no snapshot."""
    book = _auto_book(ids)
    project = _observe_project(tmp_path)
    root = tmp_path / "test-run"
    root.mkdir()
    scope = _observe_scope(root)
    backend = _observe_backend("dp-auto", book["material"], book["preparation"])
    client = _observe_client(tmp_path, monkeypatch, scope=scope, backend=backend)

    outcome = _observe(project, scope, client, book, "dp-auto")

    _assert_refused_without_send(outcome, backend, project, root)


@pytest.mark.parametrize("dp_id", dpts.ACTIVE_DP_IDS)
def test_prepared_observation_preserves_valid_question_edits(
    dp_id: str, tmp_path: pathlib.Path, monkeypatch
) -> None:
    book = _case_book(dp_id)
    project = _observe_project(tmp_path)
    root = tmp_path / "test-run"
    root.mkdir()
    scope = _observe_scope(root)
    backend = _observe_backend(dp_id, book["material"], book["preparation"])
    client = _observe_client(tmp_path, monkeypatch, scope=scope, backend=backend)
    qid = BUSINESS_QIDS[dp_id]
    override = {qid: {"instructions": "Compare this observation using the edited instructions."}}
    if dp_id != "dp-auto":
        override[qid]["criteria"] = {
            choice: f"Edited description for {choice}"
            for choice in dpts.resolve_entry_choices(dp_id, book["material"])
        }
    before = _tree(project)

    outcome = dpts.decide_for(
        dp_id,
        dpts.Trigger.from_mapping(decision_book.book_state(book), trigger_id=OBSERVE_SUBMISSION),
        project,
        client=client,
        archive=False,
        intent="answer",
        questions=override,
        observation=dpts.Observation(scope=scope, book=book, submission_id=OBSERVE_SUBMISSION),
    )

    assert outcome.status == "suggested", outcome.detail
    assert len(backend.calls) == 1
    sent = backend.calls[0]
    assert sent["questions"][qid]["instructions"] == override[qid]["instructions"]
    if "criteria" in override[qid]:
        assert sent["questions"][qid]["criteria"] == override[qid]["criteria"]
    assert sent["state"]["preparation"] == book["preparation"]
    assert sent["questions"]["basis_id"]["labels"] == {
        item["id"]: item["text"] for item in book["preparation"]["basis_catalog"]
    }
    assert outcome.preview["executor_invoked"] is False
    assert _tree(project) == before


@pytest.mark.parametrize("boundary", ["questions", "prepared-size", "global-disabled"])
def test_prepared_observation_refuses_real_limits_without_send_or_effects(
    boundary: str, tmp_path: pathlib.Path, monkeypatch
) -> None:
    dp_id = "dp-w-type"
    book = _case_book(dp_id)
    project = _observe_project(tmp_path)
    root = tmp_path / "test-run"
    root.mkdir()
    scope = _observe_scope(root)
    backend = _observe_backend(dp_id, book["material"], book["preparation"])
    client = _observe_client(tmp_path, monkeypatch, scope=scope, backend=backend)
    if boundary == "questions":
        client.cfg.max_questions = 1
    elif boundary == "prepared-size":
        book["preparation"]["basis_catalog"][0]["text"] = "prepared fact " * dpts.MAX_STATE_BYTES
    else:
        client.cfg.enabled = False
    before = _tree(project)

    outcome = _observe(project, scope, client, book, dp_id)

    assert outcome.status == "escalated", outcome.detail
    assert backend.calls == []
    assert outcome.actual_action is None
    assert outcome.preview["executor_invoked"] is False
    assert _tree(project) == before
    if boundary == "questions":
        assert outcome.transport_reason == decision.REASON_BUDGET_EXHAUSTED
        assert client.cfg.max_questions == 1
    elif boundary == "prepared-size":
        assert outcome.escalated_reason == "input-oversize"
        assert book["preparation"]["basis_catalog"][0]["text"] == "prepared fact " * dpts.MAX_STATE_BYTES
    else:
        assert outcome.transport_reason == decision.REASON_DISABLED
        assert client.cfg.enabled is False


def test_observation_joins_a_used_context_slot_of_the_schema3_book(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """The canonical view includes the used ``context`` slots, not just material."""
    dp_id = "dp-QG"
    book = _case_book(dp_id)
    book["context"] = {"error_excerpt": "AssertionError: expected pass, got fix"}
    book["notes"] = {
        "evidence": {
            **{path: "cmd: true" for path in decision_book.required_state_paths(dp_id)},
            "context.error_excerpt": "cmd: true",
        }
    }
    project = _observe_project(tmp_path)
    root = tmp_path / "test-run"
    root.mkdir()
    scope = _observe_scope(root)
    backend = _observe_backend(dp_id, book["material"], book["preparation"])
    client = _observe_client(tmp_path, monkeypatch, scope=scope, backend=backend)

    outcome = _observe(project, scope, client, book, dp_id)

    assert outcome.status == "suggested", outcome.detail
    assert len(backend.calls) == 1
    # The accepted view really is the canonical one: it carries the used slot,
    # which the old material-only/legacy-state read could not represent.
    assert decision_book.book_state(book)["context"]["error_excerpt"] == (
        "AssertionError: expected pass, got fix"
    )


def test_observation_refuses_a_book_that_is_not_the_sent_state(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """Material and context mismatches are refused before the transport."""
    dp_id = "dp-w-type"
    book = _case_book(dp_id)
    project = _observe_project(tmp_path)
    root = tmp_path / "test-run-a"
    root.mkdir()
    scope = _observe_scope(root)
    backend = _observe_backend(dp_id, book["material"], book["preparation"])
    client = _observe_client(tmp_path, monkeypatch, scope=scope, backend=backend)
    tampered = dict(decision_book.book_state(book))
    tampered["task_goal"] = "a different goal than the book describes"

    outcome = _observe(project, scope, client, book, dp_id, state=tampered)

    assert "book.state" in outcome.detail, outcome.detail
    assert "digest join failed" in outcome.detail, outcome.detail
    _assert_refused_without_send(outcome, backend, project, root)

    # The same join covers the used context slot: a different excerpt is not the
    # state of the book under test.
    context_dp = "dp-QG"
    context_book = _case_book(context_dp)
    context_book["context"] = {"error_excerpt": "book says this failed"}
    context_book["notes"] = {
        "evidence": {
            **{path: "cmd: true" for path in decision_book.required_state_paths(context_dp)},
            "context.error_excerpt": "cmd: true",
        }
    }
    context_root = tmp_path / "test-run-b"
    context_root.mkdir()
    context_scope = _observe_scope(context_root)
    context_backend = _observe_backend(context_dp, context_book["material"], context_book["preparation"])
    context_client = _observe_client(
        tmp_path, monkeypatch, scope=context_scope, backend=context_backend
    )
    other = dict(decision_book.book_state(context_book))
    other["context"] = {"error_excerpt": "sent state says something else"}

    outcome = _observe(
        project, context_scope, context_client, context_book, context_dp, state=other
    )

    assert "book.state" in outcome.detail, outcome.detail
    _assert_refused_without_send(outcome, context_backend, project, context_root)


def test_observation_refuses_the_legacy_state_book_before_send(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """The old top-level ``state`` shape stays read-only history, never a shortcut."""
    dp_id = "dp-w-type"
    case_state = decision_book.book_state(_case_book(dp_id))
    legacy = {
        "schema_version": 2,
        "decision_point": dp_id,
        "state": case_state,
        "notes": {
            "evidence": {path: "cmd: true" for path in decision_book.required_state_paths(dp_id)}
        },
    }
    project = _observe_project(tmp_path)
    root = tmp_path / "test-run"
    root.mkdir()
    scope = _observe_scope(root)
    backend = _observe_backend(dp_id, legacy["state"], _case_book(dp_id)["preparation"])
    client = _observe_client(tmp_path, monkeypatch, scope=scope, backend=backend)

    outcome = _observe(
        project, scope, client, legacy, dp_id, state=dict(legacy["state"])
    )

    assert "legacy" in outcome.detail, outcome.detail
    _assert_refused_without_send(outcome, backend, project, root)


def test_observation_refuses_a_book_carrying_the_known_secret(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """The known-secret scan still runs on the canonical view, before the send."""
    dp_id = "dp-w-type"
    book = _case_book(dp_id)
    book["material"]["task_requirements"] = f"use the configured key {API_KEY} here"
    project = _observe_project(tmp_path)
    root = tmp_path / "test-run"
    root.mkdir()
    scope = _observe_scope(root)
    backend = _observe_backend(dp_id, book["material"], book["preparation"])
    client = _observe_client(tmp_path, monkeypatch, scope=scope, backend=backend)

    outcome = _observe(project, scope, client, book, dp_id)

    assert "book-secret" in outcome.detail, outcome.detail
    assert API_KEY not in outcome.detail
    _assert_refused_without_send(outcome, backend, project, root)
    for item in sorted(root.rglob("*")):
        if item.is_file():
            assert API_KEY not in item.read_text(encoding="utf-8", errors="replace")


def test_observation_refuses_all_retired_ids_and_the_unproven_view(
    tmp_path: pathlib.Path, monkeypatch
) -> None:
    """The 25 old ids stay uncallable, and an authority without the canonical
    view is refused instead of trusted."""
    dp_id = "dp-w-type"
    book = _case_book(dp_id)
    project = _observe_project(tmp_path)
    root = tmp_path / "test-run"
    root.mkdir()
    scope = _observe_scope(root)

    for old_id in RETIRED_25:
        backend = decision.FakeBackend([])
        client = _observe_client(tmp_path, monkeypatch, scope=scope, backend=backend)
        with pytest.raises(decision.DecisionInputError):
            _observe(project, scope, client, book, old_id)
        assert backend.calls == []
    assert not (project / dpts.DECISIONS_RELATIVE_PATH).exists()

    # Fail closed when the registered authority does not expose the canonical
    # view: no material is sent on an unproven join.
    monkeypatch.setattr(
        dpts,
        "BOOK_VALIDATOR",
        lambda _book, _project, *, redactor=None: (),
    )
    backend = _observe_backend(dp_id, book["material"], book["preparation"])
    client = _observe_client(tmp_path, monkeypatch, scope=scope, backend=backend)

    outcome = _observe(project, scope, client, book, dp_id)

    assert "no canonical book state view" in outcome.detail, outcome.detail
    _assert_refused_without_send(outcome, backend, project, root)
