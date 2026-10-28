"""T01 contract: approved four-DP business material + one model allowlist projection.

Behaviour contracts under test (design §2, plan "最小固定跨卡接口"):

* dp1 sends exactly ``task_goal`` / ``task_requirements`` / ``task_deliverables``
  and asks one native choice over coding/research/review with the three
  user-defined explanations;
* dp2 sends those three task fields plus ``pm_decision_background`` and the
  optional ``worker_execution``; the registry question
  (``checkpoint_action`` instructions / choices / labels) is unchanged;
* dp3 sends ``question`` + the four ``background`` parts + ``handling_options``
  ({id,label,description}) and asks one native dynamic choice; fewer than two
  distinguishable, described candidates never reach the transport;
* dp25 sends the four business parts with verified/unverified evidence split
  and an explicit empty list when there is none; the old count-based facts
  (``rows_total``/``chain_ok``/...) are not model material;
* every one of the four is projected through the single registry allowlist, so
  identity/association facts stay local and the exact bytes that reach the
  backend are business-only (the digest names that projected object).

The tests use a faux backend and a synthetic, isolated HOME; no real credential,
network, model, browser, build or install is touched.
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import sys
import threading

import pytest

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]
sys.path.insert(0, str(PACKAGE_DIR))
sys.path.insert(0, str(PACKAGE_DIR / "scripts"))

import decision  # noqa: E402
import decision_book as books  # noqa: E402
import decision_context  # noqa: E402
import decision_points as dpts  # noqa: E402
import gen_decide_registry_ts as gen  # noqa: E402

DP1 = "dp1-dispatch-type"
DP2 = "dp2-checkpoint-split"
DP3 = "dp3-worker-clarify"
DP25 = "dp25-signoff-conclusion"
MODEL_DPS = (DP1, DP2, DP3, DP25)

EXPECTED_MODEL_STATE_FIELDS = {
    DP1: ("task_goal", "task_requirements", "task_deliverables"),
    DP2: (
        "task_goal",
        "task_requirements",
        "task_deliverables",
        "pm_decision_background",
        "worker_execution",
    ),
    DP3: (
        "question",
        "background.task_goal",
        "background.current_state",
        "background.decision_reason",
        "background.constraints_impact",
        "handling_options",
    ),
    DP25: (
        "delivery_goal",
        "actual_completion",
        "verification_evidence.verified",
        "verification_evidence.unverified",
        "unfinished_impact",
    ),
}

DP1_QUESTION = {
    "id": "triage_type",
    "type": "choice",
    "choices": ["coding", "research", "review"],
    "instructions": "这个任务应该派给哪一类 worker？",
    "labels": {
        "coding": "需要写代码或改代码或跑命令",
        "research": "只做检索取证不改代码",
        "review": "审计别人已完成的产出",
    },
}

# design-dp2-pm-revision-20261023.md: the question is kept byte for byte.
DP2_QUESTION = {
    "id": "checkpoint_action",
    "type": "choice",
    "choices": ["narrow", "split", "direct-exec", "escalate"],
    "instructions": "以当前进度，这一步该继续、拆小、直接执行还是上抛人？",
    "labels": {
        "narrow": "收窄到剩余预算内能完成的一小块",
        "split": "拆成多个任务重派",
        "direct-exec": "PM 自己直接做完",
        "escalate": "风险高到必须问人",
    },
}

DP3_QUESTION = {
    "id": "handling",
    "type": "choice",
    "dynamic_choices": "handling_options",
    "instructions": "针对这个问题，从候选处理方式中选出最合适的一项。",
}

DP25_QUESTION = {
    "id": "q-conclusion",
    "type": "choice",
    "choices": ["finalize", "continue", "user-confirm"],
    "instructions": (
        "按交付目标、实际完成与验证证据判断：这次交付可以收尾，还是需要继续完成，"
        "或交用户确认？不以任务数量或完成声明代替证据。"
    ),
    "labels": {
        "finalize": "可以收尾：按交付目标与验收条件直接签收",
        "continue": "继续完成：交 PM 推进未完成的缺口",
        "user-confirm": "交用户确认：由 PM 提出具体待确认项",
    },
}

DP1_MATERIAL = {
    "task_goal": "把决策材料收敛到业务事实，去掉模型不需要的审计键。",
    "task_requirements": "四个 DP 使用批准的业务字段；模型只看到业务材料；缺材料零发送。",
    "task_deliverables": "契约实现、行为测试、生成物、报告。",
}

DP2_MATERIAL = {
    "task_goal": "判断当前 checkpoint 应该收窄、拆分、PM 直执还是上抛人。",
    "task_requirements": "PM 主动触发；任务原文与决策背景齐全；worker 执行情况可选。",
    "task_deliverables": "一次 checkpoint 判断及后续 PM 处理。",
    "pm_decision_background": "剩余预算只够完成一小块，拆分后两个任务都需要重新取证。",
}

DP3_MATERIAL = {
    "question": "交付签收应该由 PM 直接写，还是必须等用户确认？",
    "background": {
        "task_goal": "让 dp25 在材料充分时一次收尾。",
        "current_state": "签收文件写入路径已实现，尚未有完整案例验证。",
        "decision_reason": "两种做法对权限边界影响不同，需要明确。",
        "constraints_impact": "等用户确认会阻塞本次收尾，但不扩大授权。",
    },
    "handling_options": [
        {
            "id": "c1",
            "label": "PM 直接写签收",
            "description": "材料与前置门都满足时立即原子写入，无需二次批准。",
        },
        {
            "id": "c2",
            "label": "先问用户再写",
            "description": "PM 给出具体待确认项，用户答复前不写签收文件。",
        },
        {
            "id": "c3",
            "label": "先补证据再判断",
            "description": "补齐未验证项后重新发起一次判断。",
        },
    ],
}

DP25_MATERIAL = {
    "delivery_goal": "四 DP 契约落地；验收条件是生产路径发送业务材料且旧断言变化被记录。",
    "actual_completion": "契约、测试与生成物已完成；报告待写。",
    "verification_evidence": {
        "verified": ["pytest test_decision_context_contract.py 全绿"],
        "unverified": ["T07 的完整 case 尚未运行"],
    },
    "unfinished_impact": ["报告缺失会让下游无法迁移", "未跑完整 case 时不能宣称整体验收"],
}

#: The 21 dps outside this card keep their question-set version (no contract churn).
UNCHANGED_QUESTIONS_VERSIONS = {
    "dp4-failure-handling": "q-b93176a8",
    "dp5-test-triage": "q-cc104f59",
    "dp6-qg-verdict": "q-16b4bb5c",
    "dp7-gate-failure": "q-c8e23cc7",
    "dp8-scope-change": "q-e5d928e8",
    "dp9-model-select": "q-bc7918b9",
    "dp10-dependency": "q-3bbd9e44",
    "dp11-credential": "q-080722b1",
    "dp12-destructive": "q-02f737ab",
    "dp13-commit-release": "q-6d26173d",
    "dp14-rule-conflict": "q-b667b8d3",
    "dp15-autopilot-gate": "q-09e25bec",
    "dp16-goal": "q-ba34304c",
    "dp17-spec-lock": "q-f81bd06d",
    "dp18-claim": "q-094db8cc",
    "dp19-foreign-write": "q-df9c727d",
    "dp20-stage-close": "q-30afd59f",
    "dp21-refine": "q-ddd23fe2",
    "dp22-debug-plan": "q-a1ed6dbc",
    "dp23-snapshot": "q-f5cecffb",
    "dp24-pi-trust": "q-20850ffa",
}

CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
)


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch):
    """Isolated HOME and a clean credential environment for every test."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in list(os.environ):
        if name in CRED_ENV_VARS or name.upper().endswith(decision._CRED_ENV_SUFFIXES):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(dpts, "ARCHIVE_WRITER", None, raising=False)
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


@pytest.fixture
def credential_snapshots(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    """Read-before spy: every production decision still freezes one snapshot."""
    calls: list[object] = []
    original = decision.credential_snapshot

    def spy(cfg: object = None, **kwargs: object):
        snapshot = original(cfg, **kwargs)
        calls.append(snapshot)
        return snapshot

    monkeypatch.setattr(decision, "credential_snapshot", spy)
    return calls


def _ok(answers: dict) -> dict:
    return {
        "available": True,
        "reason": None,
        "retryable": False,
        "answers": answers,
        "latency_ms": 1,
    }


def _answer(value: object, confidence: float = 0.9) -> dict:
    return {"value": value, "confidence": confidence}


def _client(tmp_path: pathlib.Path, backend: decision.FakeBackend) -> decision.DecisionClient:
    cfg = decision.DecisionConfig(enabled=True)
    return decision.DecisionClient(
        cfg=cfg, backend=backend, evidence_path=tmp_path / "triage-decisions.jsonl"
    )


def _run(
    tmp_path: pathlib.Path,
    dp_id: str,
    material: dict,
    answers: dict,
    *,
    key: str = "mw-decision-context",
    task_key: str | None = None,
) -> tuple[dpts.DecisionOutcome, decision.FakeBackend]:
    backend = decision.FakeBackend([_ok(answers)])
    outcome = dpts.decide_for(
        dp_id,
        dpts.Trigger(trigger_id="dc-t01", key=key, task_key=task_key, data=material),
        tmp_path,
        client=_client(tmp_path, backend),
        archive=False,
        intent="answer",
    )
    return outcome, backend


def _run_with_questions(
    tmp_path: pathlib.Path,
    dp_id: str,
    material: dict,
    answers: dict,
    questions: object,
) -> tuple[dpts.DecisionOutcome, decision.FakeBackend]:
    """One decision with an observation-only question override (T10)."""
    backend = decision.FakeBackend([_ok(answers)])
    outcome = dpts.decide_for(
        dp_id,
        dpts.Trigger(trigger_id="dc-t01", key="mw-decision-context", data=material),
        tmp_path,
        client=_client(tmp_path, backend),
        archive=False,
        intent="answer",
        questions=questions,
    )
    return outcome, backend


def _sent(backend: decision.FakeBackend) -> dict:
    assert len(backend.calls) == 1, backend.calls
    return dict(backend.calls[0]["state"])


def _questions_of(dp_id: str) -> list[dict]:
    return [dict(question) for question in dpts.get_decision_point(dp_id).questions]


# ---------------------------------------------------------------------------
# 1. The registry declares the approved material and the single model allowlist
# ---------------------------------------------------------------------------


def test_model_allowlist_is_the_approved_four_dp_table() -> None:
    assert dict(dpts.MODEL_STATE_FIELDS) == EXPECTED_MODEL_STATE_FIELDS
    assert set(dpts.MODEL_STATE_FIELDS) == set(MODEL_DPS)
    for dp_id, paths in EXPECTED_MODEL_STATE_FIELDS.items():
        declared = set(dpts.REQUIRED_STATE_FIELDS.get(dp_id, ()))
        declared |= set(dpts.OPTIONAL_STATE_FIELDS.get(dp_id, ()))
        assert set(paths) <= declared, f"{dp_id}: model path outside the declared contract"
        assert set(dpts.REQUIRED_STATE_FIELDS[dp_id]) <= set(paths), (
            f"{dp_id}: a required business field is missing from the model table"
        )


def test_dp1_one_question_with_three_user_defined_types() -> None:
    questions = _questions_of(DP1)
    assert questions == [DP1_QUESTION]
    assert {question["id"] for question in questions} == {"triage_type"}


def test_dp2_question_is_unchanged_from_the_design_revision() -> None:
    assert _questions_of(DP2) == [DP2_QUESTION]
    assert dpts.get_decision_point(DP2).questions_version == "q-ba8e970f"


def test_dp3_has_one_native_dynamic_choice() -> None:
    assert _questions_of(DP3) == [DP3_QUESTION]


def test_dp25_choices_are_finalize_continue_user_confirm() -> None:
    assert _questions_of(DP25) == [DP25_QUESTION]


def test_the_other_21_questions_versions_are_untouched() -> None:
    versions = {dp.id: dp.questions_version for dp in dpts.DP_REGISTRY}
    assert len(versions) == dpts.EXPECTED_DP_COUNT
    for dp_id, expected in UNCHANGED_QUESTIONS_VERSIONS.items():
        assert versions[dp_id] == expected, dp_id


# ---------------------------------------------------------------------------
# 2. The production decide path sends business material only
# ---------------------------------------------------------------------------


def test_dp1_sends_only_three_task_fields(
    tmp_path: pathlib.Path, credential_snapshots: list[object]
) -> None:
    outcome, backend = _run(
        tmp_path, DP1, DP1_MATERIAL, {"triage_type": _answer("coding")}
    )
    assert outcome.status == "suggested", outcome.detail
    state = _sent(backend)
    assert state == DP1_MATERIAL
    assert list(state) == list(EXPECTED_MODEL_STATE_FIELDS[DP1])
    assert set(state).isdisjoint({"schema_version", "decision_point", "questions_version"})
    assert set(state).isdisjoint({"key", "task_key", "phase", "task_type", "risk"})
    assert backend.calls[0]["questions"] == {"triage_type": DP1_QUESTION}
    assert outcome.state_digest == dpts._state_digest(state)
    assert len(credential_snapshots) == 1, "the decision did not freeze one credential snapshot"


@pytest.mark.parametrize(
    ("material", "detail"),
    [
        ({k: v for k, v in DP1_MATERIAL.items() if k != "task_requirements"}, "task_requirements"),
        ({**DP1_MATERIAL, "task_goal": ""}, "task_goal"),
        ({**DP1_MATERIAL, "task_deliverables": None}, "task_deliverables"),
        ({**DP1_MATERIAL, "task_goal": 42}, "task_goal: expected string"),
        ({**DP1_MATERIAL, "risk": "high"}, "risk"),
        ({**DP1_MATERIAL, "task_summary": "old contract"}, "task_summary"),
    ],
)
def test_dp1_refuses_illegal_material_with_zero_send(
    tmp_path: pathlib.Path, material: dict, detail: str
) -> None:
    outcome, backend = _run(
        tmp_path, DP1, material, {"triage_type": _answer("coding")}
    )
    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "input-incomplete"
    assert detail in outcome.detail
    assert backend.calls == [], "illegal material reached the transport"


def test_long_and_multibyte_material_is_sent_verbatim(tmp_path: pathlib.Path) -> None:
    goal = "目标：" + "多字节材料" * 60 + " 🚀"  # > 512 bytes, under the 2000 B budget
    material = {**DP1_MATERIAL, "task_goal": goal}
    outcome, backend = _run(
        tmp_path, DP1, material, {"triage_type": _answer("coding")}
    )
    assert outcome.status == "suggested", outcome.detail
    sent = _sent(backend)
    assert sent["task_goal"] == goal
    assert len(goal.encode("utf-8")) > dpts.STATE_STRING_MAX_BYTES
    assert outcome.truncated == (), "a necessary business field was truncated"


def test_oversized_business_material_is_refused_not_truncated(tmp_path: pathlib.Path) -> None:
    # One required string one byte over the published budget: the complete
    # material is refused whole, never silently cut.
    material = {**DP1_MATERIAL, "task_goal": "x" * (dpts.MAX_STATE_BYTES + 1)}
    outcome, backend = _run(
        tmp_path, DP1, material, {"triage_type": _answer("coding")}
    )
    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "input-oversize"
    assert backend.calls == []
    assert outcome.truncated == (), "necessary fields must not be silently cut"


def test_complete_sample_material_fits_the_existing_budget() -> None:
    """Budget evidence: the four approved samples fit the published budget.

    The numbers are reported, not replaced by a new cap: the full-case
    acceptance lives in ``test_decision_context_integration.py`` (four shipped
    cases + the measured real card material), and an over-budget necessary field
    is refused there, never truncated.
    """
    sizes = {
        dp_id: len(decision._encode_state(dpts.model_state_for(dp_id, material)))
        for dp_id, material in (
            (DP1, DP1_MATERIAL),
            (DP2, {**DP2_MATERIAL, "worker_execution": "done A; left B"}),
            (DP3, DP3_MATERIAL),
            (DP25, DP25_MATERIAL),
        )
    }
    assert all(size <= dpts.MAX_STATE_BYTES for size in sizes.values()), sizes


# ---------------------------------------------------------------------------
# 3. The real transport boundary carries the projected body
# ---------------------------------------------------------------------------


class _WireHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(length)
        self.server.requests.append({"path": self.path, "body": body})
        payload = json.dumps(
            {
                "model": "jev-latest",
                "answers": {
                    "handling": {"type": "choice", "choice": "c2", "confidence": 0.9}
                },
            },
            ensure_ascii=False,
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()

    def log_message(self, fmt: str, *args: object) -> None:
        return


class _WireServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, _WireHandler)
        self.requests: list[dict] = []

    @property
    def base_url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"

    def handle_error(self, request, client_address) -> None:  # noqa: ANN001 - stdlib hook
        return


@pytest.fixture
def loopback():
    server = _WireServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="t01-wire")
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_dp3_wire_body_is_the_projected_business_state(
    tmp_path: pathlib.Path, loopback: _WireServer, credential_snapshots: list[object]
) -> None:
    """Local loopback only: the POST body is the actual sent material, not a preview."""
    cfg = decision.DecisionConfig(
        enabled=True,
        extras={"base_url": loopback.base_url, "api_key": "synthetic-t01-key"},
        timeout_s=5.0,
        max_retries=0,
        backoff_base_s=0.0,
    )
    outcome = dpts.decide_for(
        DP3,
        dpts.Trigger(
            trigger_id="dc-t01-wire",
            key="mw-decision-context",
            task_key="dc-t01-contract",
            data=DP3_MATERIAL,
        ),
        tmp_path,
        config=cfg,
        archive=False,
        intent="answer",
    )
    assert outcome.status == "suggested", outcome.detail
    assert len(loopback.requests) == 1, loopback.requests
    body = json.loads(loopback.requests[0]["body"].decode("utf-8"))
    assert body["state"] == DP3_MATERIAL
    sent_questions = body["questions"]
    assert set(sent_questions) == {"handling"}
    handling = sent_questions["handling"]
    assert handling["type"] == "choice"
    assert handling["instructions"] == DP3_QUESTION["instructions"]
    assert handling["criteria"] == {
        item["id"]: item["label"] for item in DP3_MATERIAL["handling_options"]
    }
    assert "choices" not in handling
    assert set(body["state"]).isdisjoint(
        {"schema_version", "decision_point", "questions_version", "key", "task_key"}
    )
    assert len(credential_snapshots) == 1


# ---------------------------------------------------------------------------
# 4. dp2: PM background required, worker execution optional, no audit keys
# ---------------------------------------------------------------------------


def test_dp2_sends_task_material_plus_pm_background(tmp_path: pathlib.Path) -> None:
    outcome, backend = _run(
        tmp_path, DP2, DP2_MATERIAL, {"checkpoint_action": _answer("split")}
    )
    assert outcome.status == "suggested", outcome.detail
    state = _sent(backend)
    assert state == DP2_MATERIAL
    assert set(state).isdisjoint({"key", "phase", "risk", "progress.elapsed_minutes"})


def test_dp2_worker_execution_is_optional_and_no_worker_is_legal(
    tmp_path: pathlib.Path,
) -> None:
    # No task key and no worker self-assessment: explicitly legal (design revision).
    outcome, backend = _run(
        tmp_path,
        DP2,
        {**DP2_MATERIAL, "worker_execution": "已完成 A；剩余 B；阻塞 C；预算 30m"},
        {"checkpoint_action": _answer("direct-exec")},
        key="mw-decision-context",
        task_key=None,
    )
    assert outcome.status == "suggested", outcome.detail
    sent = _sent(backend)
    assert sent["worker_execution"].startswith("已完成 A")
    assert set(sent) == set(EXPECTED_MODEL_STATE_FIELDS[DP2])


def test_dp2_missing_pm_background_is_refused_with_zero_send(tmp_path: pathlib.Path) -> None:
    material = {k: v for k, v in DP2_MATERIAL.items() if k != "pm_decision_background"}
    outcome, backend = _run(
        tmp_path, DP2, material, {"checkpoint_action": _answer("narrow")}
    )
    assert outcome.escalated_reason == "input-incomplete"
    assert "pm_decision_background" in outcome.detail
    assert backend.calls == []


# ---------------------------------------------------------------------------
# 5. dp3: four-part background + one dynamic choice over described candidates
# ---------------------------------------------------------------------------


def test_dp3_sends_question_background_and_described_candidates(
    tmp_path: pathlib.Path,
) -> None:
    outcome, backend = _run(
        tmp_path, DP3, DP3_MATERIAL, {"handling": _answer("c2")}
    )
    assert outcome.status == "suggested", outcome.detail
    state = _sent(backend)
    assert state == DP3_MATERIAL
    assert state["handling_options"] == DP3_MATERIAL["handling_options"]
    assert len(state["handling_options"]) == 3
    assert all(item["description"] for item in state["handling_options"])
    assert backend.calls[0]["questions"] == {"handling": DP3_QUESTION}
    assert "choices" not in backend.calls[0]["questions"]["handling"]
    assert outcome.answers["handling"]["value"] == "c2"


@pytest.mark.parametrize(
    ("candidates", "detail"),
    [
        (DP3_MATERIAL["handling_options"][:1], "at least 2"),
        (
            [
                {**DP3_MATERIAL["handling_options"][0]},
                {**DP3_MATERIAL["handling_options"][1], "label": "PM 直接写签收"},
            ],
            "distinct",
        ),
        (
            [
                {**DP3_MATERIAL["handling_options"][0], "description": ""},
                DP3_MATERIAL["handling_options"][1],
            ],
            "description",
        ),
        (
            [
                {**DP3_MATERIAL["handling_options"][0], "id": "c2"},
                {**DP3_MATERIAL["handling_options"][1], "id": "c1"},
            ],
            "c1",
        ),
    ],
)
def test_dp3_refuses_unusable_candidates_with_zero_send(
    tmp_path: pathlib.Path, candidates: list, detail: str
) -> None:
    material = {**DP3_MATERIAL, "handling_options": candidates}
    outcome, backend = _run(tmp_path, DP3, material, {"handling": _answer("c1")})
    assert outcome.escalated_reason == "input-incomplete"
    assert detail in outcome.detail
    assert backend.calls == []


@pytest.mark.parametrize(
    ("background", "detail"),
    [
        (
            {k: v for k, v in DP3_MATERIAL["background"].items() if k != "decision_reason"},
            "background.decision_reason",
        ),
        ({**DP3_MATERIAL["background"], "extra": "not approved"}, "background.extra"),
    ],
)
def test_dp3_refuses_incomplete_or_extra_background(
    tmp_path: pathlib.Path, background: dict, detail: str
) -> None:
    material = {**DP3_MATERIAL, "background": background}
    outcome, backend = _run(tmp_path, DP3, material, {"handling": _answer("c1")})
    assert outcome.escalated_reason == "input-incomplete"
    assert detail in outcome.detail
    assert backend.calls == []


# ---------------------------------------------------------------------------
# 5b. Observation-only question override (T10)
# ---------------------------------------------------------------------------


def test_a_question_override_only_replaces_the_instructions(
    tmp_path: pathlib.Path,
) -> None:
    """Only ``instructions`` comes from an override; state stays the candidate source."""
    questions = {
        "handling": {
            "id": "handling",
            "type": "choice",
            "dynamic_choices": "handling_options",
            "instructions": "T10 edited instruction: which handling option?",
        }
    }
    outcome, backend = _run_with_questions(
        tmp_path, DP3, DP3_MATERIAL, {"handling": _answer("c2")}, questions
    )
    assert outcome.status == "suggested", outcome.detail
    sent_questions = backend.calls[0]["questions"]
    assert sent_questions["handling"]["instructions"] == (
        "T10 edited instruction: which handling option?"
    )
    assert sent_questions["handling"]["type"] == "choice"
    assert sent_questions["handling"]["dynamic_choices"] == "handling_options"
    assert "criteria" not in sent_questions["handling"], (
        "criteria stay generated from state.handling_options, never from the override"
    )
    assert backend.calls[0]["state"]["handling_options"] == DP3_MATERIAL["handling_options"]


@pytest.mark.parametrize(
    ("questions", "detail"),
    [
        (
            {"other_question": {"type": "choice", "instructions": "x"}},
            "registered question id",
        ),
        (
            {"handling": {"type": "score", "instructions": "x"}},
            "conflicts with the registered type",
        ),
        (
            {"handling": {"type": "choice", "instructions": "   "}},
            "instructions",
        ),
        (
            {
                "handling": {
                    "type": "choice",
                    "instructions": "x",
                    "criteria": {"c1": "not the rendered label"},
                }
            },
            "handling.criteria",
        ),
        (
            {"handling": {"type": "choice", "instructions": "x", "choices": ["a"]}},
            "handling.choices",
        ),
    ],
)
def test_an_illegal_question_override_is_refused_with_zero_send(
    tmp_path: pathlib.Path, questions: dict, detail: str
) -> None:
    outcome, backend = _run_with_questions(
        tmp_path, DP3, DP3_MATERIAL, {"handling": _answer("c1")}, questions
    )
    assert outcome.escalated_reason == "input-incomplete"
    assert "illegal questions" in outcome.detail
    assert detail in outcome.detail
    assert backend.calls == [], "an illegal question override never reaches the transport"


# ---------------------------------------------------------------------------
# 6. dp25: four business parts, evidence split, no counts as evidence
# ---------------------------------------------------------------------------


def test_dp25_sends_four_parts_with_verified_and_unverified_split(
    tmp_path: pathlib.Path,
) -> None:
    outcome, backend = _run(
        tmp_path, DP25, DP25_MATERIAL, {"q-conclusion": _answer("finalize")}
    )
    assert outcome.status == "suggested", outcome.detail
    state = _sent(backend)
    assert state == DP25_MATERIAL
    assert state["verification_evidence"]["verified"] == ["pytest test_decision_context_contract.py 全绿"]
    assert state["verification_evidence"]["unverified"] == ["T07 的完整 case 尚未运行"]
    assert set(state).isdisjoint({"key", "rows_total", "rows_available", "chain_ok", "p0_open"})
    assert backend.calls[0]["questions"] == {"q-conclusion": DP25_QUESTION}


def test_dp25_empty_evidence_and_unfinished_lists_are_values(tmp_path: pathlib.Path) -> None:
    material = {
        **DP25_MATERIAL,
        "verification_evidence": {"verified": ["a"], "unverified": []},
        "unfinished_impact": [],
    }
    outcome, backend = _run(
        tmp_path, DP25, material, {"q-conclusion": _answer("continue")}
    )
    assert outcome.status == "suggested", outcome.detail
    sent = _sent(backend)
    assert sent["verification_evidence"]["unverified"] == []
    assert sent["unfinished_impact"] == []


@pytest.mark.parametrize(
    "material",
    [
        {k: v for k, v in DP25_MATERIAL.items() if k != "unfinished_impact"},
        {
            **DP25_MATERIAL,
            "verification_evidence": {"verified": ["a"]},
        },
        {**DP25_MATERIAL, "delivery_goal": ""},
        {**DP25_MATERIAL, "rows_total": 3},
    ],
)
def test_dp25_refuses_incomplete_material_with_zero_send(
    tmp_path: pathlib.Path, material: dict
) -> None:
    outcome, backend = _run(
        tmp_path, DP25, material, {"q-conclusion": _answer("finalize")}
    )
    assert outcome.escalated_reason == "input-incomplete", outcome.detail
    assert backend.calls == []


# ---------------------------------------------------------------------------
# 7. Projection is the single allowlist; the other 21 dps keep their contract
# ---------------------------------------------------------------------------


def test_projection_strips_identity_and_local_audit() -> None:
    local = {
        **DP3_MATERIAL,
        "schema_version": 2,
        "decision_point": DP3,
        "questions_version": "q-test1234",
        "key": "mw-decision-context",
        "task_key": "dc-t01-contract",
        "trigger_id": "dc-t01",
    }
    projected = dpts.model_state_for(DP3, local)
    assert projected == DP3_MATERIAL
    # Nested values are copied, not aliased to the caller's material.
    projected["handling_options"][0]["label"] = "mutated"
    assert local["handling_options"][0]["label"] == "PM 直接写签收"


def test_projection_leaves_the_other_21_dps_unchanged() -> None:
    legacy = {"schema_version": 2, "decision_point": "dp4-failure-handling", "failure": {"kind": "x"}}
    assert dpts.model_state_for("dp4-failure-handling", legacy) == legacy
    assert dpts.model_state_for("dp4-failure-handling", legacy) is not legacy
    assert dpts.MODEL_STATE_FIELDS.keys() == set(MODEL_DPS)


# ---------------------------------------------------------------------------
# 8. Generated artifacts carry the same table (no hand-edited TS)
# ---------------------------------------------------------------------------


def test_registry_snapshot_exports_the_model_table_for_four_dps() -> None:
    snapshot = dpts.registry_snapshot()
    by_id = {point["id"]: point for point in snapshot["points"]}
    for dp_id, paths in EXPECTED_MODEL_STATE_FIELDS.items():
        assert by_id[dp_id]["model_state_fields"] == list(paths), dp_id
    for dp_id in (point["id"] for point in snapshot["points"]):
        if dp_id not in MODEL_DPS:
            assert "model_state_fields" not in by_id[dp_id], dp_id


def test_checked_in_registry_json_carries_the_model_table() -> None:
    doc = json.loads((PACKAGE_DIR / "decide_registry.json").read_text(encoding="utf-8"))
    by_id = {point["id"]: point for point in doc["points"]}
    for dp_id, paths in EXPECTED_MODEL_STATE_FIELDS.items():
        assert by_id[dp_id]["model_state_fields"] == list(paths), dp_id
    assert [q["id"] for q in by_id[DP2]["questions"]] == ["checkpoint_action"]
    assert by_id[DP2]["questions"][0]["instructions"] == DP2_QUESTION["instructions"]


def test_generated_ts_is_fresh_and_carries_the_model_table() -> None:
    path = gen.output_path()
    text = path.read_text(encoding="utf-8")
    assert text == gen.render(), (
        "decide-registry.generated.ts is stale; regenerate it instead of editing it"
    )
    for dp_id, paths in EXPECTED_MODEL_STATE_FIELDS.items():
        start = text.index(f'\t"{dp_id}": {{')
        end = text.index("\n\t},", start)
        block = text[start:end]
        rendered = ", ".join(f'"{path}"' for path in paths)
        assert (
            f"modelStateFields: [{rendered}]" in block
            or f"modelStateFields: [\n\t\t\t" in block
        ), f"{dp_id}: generated model table is missing"
        for path in paths:
            assert f'"{path}"' in block, f"{dp_id}/{path}: missing from the generated entry"


def test_the_four_dps_no_longer_advertise_old_context_slots() -> None:
    for dp_id in (DP1, DP2, DP3):
        assert decision_context.slot_names_for(dp_id) == (), dp_id


# ---------------------------------------------------------------------------
# 9. Book surface reads the same registry contract
# ---------------------------------------------------------------------------


def _write_evidence_file(root: pathlib.Path) -> pathlib.Path:
    path = root / "notes.txt"
    path.write_text("synthetic evidence line\n" * 5, encoding="utf-8")
    return path


def _book(dp_id: str, state: dict) -> dict:
    required = dpts.REQUIRED_STATE_FIELDS[dp_id]
    return {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "state": state,
        "context": {},
        "notes": {"evidence": {path: "notes.txt:1" for path in required}},
    }


def _generous_limits() -> dict[str, int]:
    return {
        "max_state_bytes": 100_000,
        "max_state_plus_question_tokens": 100_000,
        "max_total_tokens": 100_000,
    }


def test_book_accepts_the_new_dp3_state(tmp_path: pathlib.Path) -> None:
    _write_evidence_file(tmp_path)
    state = {
        **DP3_MATERIAL,
        "schema_version": dpts.STATE_SCHEMA_VERSION,
        "decision_point": DP3,
        "questions_version": dpts.get_decision_point(DP3).questions_version,
    }
    issues = books.check_book(
        _book(DP3, state),
        project_dir=tmp_path,
        repo_root=tmp_path,
        limits=_generous_limits(),
    )
    assert issues == [], [issue.format() for issue in issues]


def test_book_refuses_the_replaced_dp3_business_contract(tmp_path: pathlib.Path) -> None:
    _write_evidence_file(tmp_path)
    state = {
        **DP3_MATERIAL,
        "ambiguity": {"kind": "scope", "question": "old key"},
        "local_candidates": [{"id": "c1", "label": "old"}],
        "schema_version": dpts.STATE_SCHEMA_VERSION,
        "decision_point": DP3,
    }
    issues = books.check_book(
        _book(DP3, state),
        project_dir=tmp_path,
        repo_root=tmp_path,
        limits=_generous_limits(),
    )
    codes = {issue.code for issue in issues}
    assert "book-state" in codes, [issue.format() for issue in issues]


def test_book_template_matches_the_new_scaffold(tmp_path: pathlib.Path) -> None:
    template = json.loads(
        (PACKAGE_DIR / "decide_book_template.json").read_text(encoding="utf-8")
    )
    assert template["books"][DP3] == books.scaffold_book(DP3)
    assert template["books"]["dp6-qg-verdict"] == books.scaffold_book("dp6-qg-verdict")
    proposed = books.scaffold_book(DP3)["state"]
    assert "question" in proposed
    assert "background" in proposed
    assert "handling_options" in proposed
    assert set(proposed).isdisjoint({"ambiguity", "local_candidates", "task_summary"})
