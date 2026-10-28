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

import json
import pathlib
import sys

import pytest

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_DIR))  # noqa: E402

import decision  # noqa: E402
import decision_backends as backends  # noqa: E402
import decision_points as dpts  # noqa: E402

COPY_ROOT = PACKAGE_DIR.parents[1]  # .../implementation-worktree
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
