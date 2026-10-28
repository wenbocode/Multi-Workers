"""T08 integration: the Python side of the decision-context closed loop.

What this module proves, in the fixed-gap order of
``.agenticdoc/mw-decision-context/evidence/integration-handoff.md``:

1. **budget** (§4): the four shipped workbench cases and the measured real T03
   card material fit the published state budget, and a state one byte over it is
   refused whole (never truncated, never sent);
2. **ids** (§1): a new record that is disabled, whose transport failed, or whose
   feedback write failed still carries the exact ``<dp>:<logical_id>`` decision
   id and is never mis-read as legacy;
3. **dp25 sign-off** (§2): completion needs the valid sign-off *file*
   (``decision_signoff_result.validate_signoff`` with this logical id + the
   snapshot actually recorded); a missing/invalid file never completes, and a
   successful file with a failed feedback write stays completed with the failure
   reported honestly;
4. **four cases** (§3): edit a shipped case -> a real observe-only
   ``POST /api/test/submit`` -> the loopback ``/v1/decisions`` body is asserted
   field by field (not by hash), the one submission returns through the test
   record chain, and production archive/sign-off bytes plus every business
   executor stay untouched;
5. **CLI contract** (§5): ``mw decide dp verify`` probes the four new
   contracts offline, and the legacy non-``--stdin`` ``mw decide sign`` entry
   refuses explicitly (new material + ``--stdin``) with zero writes.

Only loopback HTTP, synthetic credentials and tmp projects are used. No real
provider, browser, build or service start/stop happens here.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import shutil
import subprocess
import sys
import uuid

import pytest

sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent))

import decision  # noqa: E402
import decision_backends  # noqa: E402
import decision_book  # noqa: E402
import decision_history  # noqa: E402
import decision_lifecycle  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire  # noqa: E402
import mw  # noqa: E402

import test_decision_dashboard_playground as pg  # noqa: E402

ASSET_DIR = __import__("pathlib").Path(__file__).parent
#: The four shipped offline workbench cases (``decide_cases/dp*.json``).
CASE_NAMES = ("dp1", "dp2", "dp3", "dp25")


def case(name: str) -> dict:
    """One shipped case exactly as it is written on disk."""
    path = ASSET_DIR / "decide_cases" / f"{name}.json"
    assert path.is_file(), path
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Hermetic fixture: no ambient credential, tmp HOME/profile/agent dir, and a
# discovery spy installed *before* anything may read a credential.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: __import__("pathlib").Path):
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "pi-agent"))
    monkeypatch.setenv("PYTHONIOENCODING", "utf-8")
    for name in sorted(os.environ):
        if name.upper().endswith(decision._CRED_ENV_SUFFIXES):
            monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(
        decision_backends, "_auth_json_path", lambda: tmp_path / "no-auth.json"
    )
    discoveries: list[str] = []

    def _spy(env=None, auth_path=None):
        discoveries.append("resolve_timi_api_key")
        return None

    monkeypatch.setattr(decision_backends, "resolve_timi_api_key", _spy)
    monkeypatch.setattr(
        decision_backends, "_AUTH_DISCOVERY_SPY", discoveries, raising=False
    )
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _write_json(path: __import__("pathlib").Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )


def _project(tmp_path: __import__("pathlib").Path, **config: object):
    project = tmp_path / "proj"
    (project / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    payload: dict[str, object] = {
        "enabled": True,
        "transport": "timi-decisions",
        "model": "jev-latest",
        "timeout_s": 5,
        "max_retries": 0,
    }
    payload.update(config)
    _write_json(project / ".mw" / "decide.json", payload)
    return project


def _run_mw(*args: str, stdin_text: str | None = None):
    mw = __import__("pathlib").Path(__file__).parent / "mw.py"
    return subprocess.run(
        [sys.executable, str(mw), *args],
        cwd=str(mw.parent),
        input=stdin_text,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def _lifecycle_rows(project: __import__("pathlib").Path) -> list[dict]:
    sink = decision_wire.production_lifecycle_sink(project)
    if not sink.exists():
        return []
    return [dict(event) for event in decision_wire.read_events(sink).events]


def _feedback_rows(project: __import__("pathlib").Path) -> list[dict]:
    sink = decision_wire.production_lifecycle_sink(project)
    errors = sink.with_name(sink.name[: -len(".jsonl")] + "-errors.jsonl")
    if not errors.exists():
        return []
    return [dict(event) for event in decision_wire.read_events(errors).events]


def _read_json_stdout(completed: subprocess.CompletedProcess) -> dict:
    assert completed.returncode == 0, (completed.returncode, completed.stdout, completed.stderr)
    return json.loads(completed.stdout)


def _tree(path: __import__("pathlib").Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for item in sorted(path.rglob("*")):
        if item.is_file():
            out[item.relative_to(path).as_posix()] = hashlib.sha256(
                item.read_bytes()
            ).hexdigest()
    return out


# ---------------------------------------------------------------------------
# 1. Budget: measured complete materials fit; over-budget is refused whole
# ---------------------------------------------------------------------------

#: The T03 producer's real dp1 card material (上下文 / 要求 / 交付格式, verbatim).
#: Measured canonical bytes 2570 (the T03 log reports 2559 after its
#: trailing-newline strip; the difference is the same text, never a field cap).
T03_REAL_CARD_MATERIAL = {
    'task_deliverables': '\n'
    'report.md+自身evidence '
    'RED/GREEN原日志/UTC/exit/hash、dp1最终材料原文与实际stdin例子、去自动dp2证据/告警仍在、consumer回执接线坐标/需T05精确CLI约束、局部 '
    'vs全链分列。低影响债集中报告不研究。',
    'task_goal': '\n'
    '目标`.agenticdoc/goal.md:1`，批准spec/design/plan '
    '`.agenticdoc/mw-decision-context/`；源锚`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:528` '
    'buildDp1DispatchState、`pm/pm-orchestrator.ts:2336`旧dp2调用/auto narrow。T01 '
    'Python契约/T02反馈正在实现，T04后续独占decision-tool/index/worker-mode。不双写。',
    'task_requirements': '\n'
    '按用户批准修改dp1 '
    'producer用任务目标/要求/交付物完整原文，类型问题仅coding/research/review，不加risk/reason问；vision/rag等原生角色边界保留，派发建议不扩大自动改type授权。三固定说明用户原定义。\n'
    'dp2只PM主动：去pm-orchestrator自动dp2调用及其旧自动narrow任务执行分支，保留通用watchdog/checkpoint告警，不新增自评产物/等待/异常阈值。PM手动入口由T04受管工具负责，你不写decision-tool。删除已明确替换路径获用户授权，无需重复问。\n'
    'CLI T05将实现`mw decide run <dp> '
    "--stdin`（本地envelope），Producer材料`{material:{task_goal,task_requirements,task_deliverables},meta:{record_version:2,logical_id,key,task_key,initiator_role:'PM',retry_of:null}}`，独立UUID生产，task派发前预留真实id、不猜最新。如现triage "
    'transport必须复用现stdin wrapper，按现架构精准接线并报告T05要求；identity绝不进model。\n'
    '现Python CLI稳定前验证真实TS producer→stdin或loopback '
    'mock边界，后续集成T05一轮统一。dp1实际consumer收到及派发/保留类型/不一致告警结束后的真实反馈，T02唯一Python '
    'writer/T05 '
    'CLI精确签名交付后接，不TS裸append、不consumed当settled。先独立producer/去自动路径实现，不等接口空转。\n'
    '正确行为RED先于实现；使用suite/harness.ts+faux，不激活真实provider/token/真实凭证。首写保存允许面基线hash/diff含untracked，外来review-split/claims功能保留，别覆盖。大文件完整分页read≤120行，不无限dump/研究；10分钟内产出行为RED计划。已批准设计最高优先，低影响债集中账。\n'
    '不改extension '
    'API，无需核心改动；若涉及API时先读pi对应完整docs/examples，禁止猜类型/内联imports/any，现node_modules类型可查。配置键绑定不能硬编码。',
}


def test_complete_case_and_real_card_materials_fit_the_published_budget() -> None:
    measured: list[tuple[str, int]] = []
    for name in CASE_NAMES:
        case_data = case(name)
        sent = dpts.model_state_for(case_data["dp"], case_data["book"]["state"])
        measured.append((name, len(decision._encode_state(sent))))
        assert len(decision._encode_state(sent)) <= dpts.MAX_STATE_BYTES, name
    real = len(decision._encode_state(T03_REAL_CARD_MATERIAL))
    measured.append(("real-card:T03", real))
    assert real == 2570, "the measured real card material changed"
    assert real <= dpts.MAX_STATE_BYTES
    # The published budget is the smallest 2^n at/above twice the largest measured
    # complete material: evidence, not a new arbitrary per-field cap.
    assert dpts.MAX_STATE_BYTES == 8192
    largest = max(size for _name, size in measured)
    assert largest * 2 <= dpts.MAX_STATE_BYTES
    assert dpts.MAX_STATE_BYTES < largest * 4


def test_over_budget_state_is_refused_whole_and_never_sent(
    tmp_path: __import__("pathlib").Path,
) -> None:
    point = dpts.get_decision_point("dp1-dispatch-type")
    questions = dpts.questions_map(point)
    state = {
        "task_goal": "probe goal",
        "task_requirements": "",
        "task_deliverables": "probe deliverables",
    }
    empty = len(decision._encode_state(dpts.model_state_for(point.id, state)))
    padding = dpts.MAX_STATE_BYTES - empty + 1
    assert padding > 0
    state["task_requirements"] = "x" * padding
    sent = dpts.model_state_for(point.id, state)
    assert len(decision._encode_state(sent)) == dpts.MAX_STATE_BYTES + 1

    backend = decision.FakeBackend(
        default=decision.BackendOutcome(
            available=True,
            reason=None,
            retryable=False,
            answers={qid: {"value": spec["choices"][0]} for qid, spec in questions.items()},
            latency_ms=1,
        )
    )
    client = decision.DecisionClient(
        cfg=decision.DecisionConfig(enabled=True),
        backend=backend,
        evidence_path=tmp_path / "triage-decisions.jsonl",
    )
    outcome = dpts.decide_for(
        point.id,
        dpts.Trigger.from_mapping(state, trigger_id="over-budget-1", key="k-t08"),
        tmp_path / "empty-project",
        client=client,
        archive=False,
    )
    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "input-oversize"
    assert f"> {dpts.MAX_STATE_BYTES}B" in (outcome.detail or "")
    assert outcome.truncated == ()
    assert backend.calls == [], "an over-budget state must be refused before any send"


# ---------------------------------------------------------------------------
# 2. Exact logical_id <-> decision_id association on disabled/failed records
# ---------------------------------------------------------------------------


def _envelope(dp: str, material: dict, logical_id: str, key: str = "k-t08") -> str:
    del dp
    return json.dumps(
        {
            "material": material,
            "meta": {
                "record_version": 2,
                "logical_id": logical_id,
                "key": key,
                "task_key": None,
                "initiator_role": "pm",
                "retry_of": None,
            },
        },
        ensure_ascii=False,
    )


DP1_MATERIAL = {
    "task_goal": "prove the association of a failed new record",
    "task_requirements": "no legacy guess, exact decision id",
    "task_deliverables": "one lifecycle row with the id",
}


def test_disabled_record_keeps_the_exact_decision_id(
    tmp_path: __import__("pathlib").Path,
) -> None:
    project = _project(tmp_path)
    # Disable only dp1 (a global `enabled=false` is "unconfigured", not
    # "disabled"); the record must still carry the exact decision id.
    _write_json(
        project / ".mw" / "decide-points.json",
        {
            "version": 1,
            "points": {"dp1-dispatch-type": {"tier": "P2", "enabled": False, "mode": "auto"}},
            "updated_at": "2026-10-23T00:00:00Z",
            "updated_by": "human",
        },
    )
    logical_id = str(uuid.uuid4())
    expected = f"dp1-dispatch-type:{logical_id}"
    completed = _run_mw(
        "decide",
        "run",
        "dp1-dispatch-type",
        "--project",
        str(project),
        "--stdin",
        "--json",
        stdin_text=_envelope("dp1-dispatch-type", DP1_MATERIAL, logical_id),
    )
    payload = _read_json_stdout(completed)
    assert payload["record_start"] == "written"
    assert payload["decision_id"] == expected
    rows = _lifecycle_rows(project)
    starts = [row for row in rows if row.get("kind") == "record-start"]
    assert len(starts) == 1
    assert starts[0]["logical_id"] == logical_id
    assert starts[0]["decision_id"] == expected, "the creation fact must carry the id"
    assert starts[0]["key"] == "k-t08"

    snapshot = decision_history.load_history(project, redact=None)
    records = [record for record in snapshot.records if record.decision_id == expected]
    assert len(records) == 1, [record.decision_id for record in snapshot.records]
    record = records[0]
    assert record.workbench.processing_state != "legacy"
    assert record.workbench.record_version == decision_lifecycle.RECORD_VERSION
    assert record.workbench.dp_id == "dp1-dispatch-type"
    # The ledger holds only the creation fact, so the reader must not invent a
    # decision observation or a completion: it is "processing" with a missing
    # decide node, and the exact decision id is still the join.
    assert record.workbench.processing_state == "processing"
    decide_node = next(node for node in record.workbench.nodes if node.id == "decide")
    assert decide_node.status == "missing"
    assert decide_node.detail["available"] is None


def test_failed_transport_record_keeps_the_exact_decision_id(
    tmp_path: __import__("pathlib").Path,
) -> None:
    fixture = pg._FixtureServer()
    fixture.status = 500
    fixture.start()
    try:
        project = _project(
            tmp_path, base_url=fixture.url, api_key="sk-t08-fixture-0123456789abcdef"
        )
        logical_id = str(uuid.uuid4())
        expected = f"dp1-dispatch-type:{logical_id}"
        completed = _run_mw(
            "decide",
            "run",
            "dp1-dispatch-type",
            "--project",
            str(project),
            "--stdin",
            "--json",
            stdin_text=_envelope("dp1-dispatch-type", DP1_MATERIAL, logical_id),
        )
        payload = _read_json_stdout(completed)
        assert payload["decision_id"] == expected
        assert fixture.calls == 1, "the fixture is the real (failing) endpoint"
        starts = [
            row for row in _lifecycle_rows(project) if row.get("kind") == "record-start"
        ]
        assert len(starts) == 1 and starts[0]["decision_id"] == expected

        snapshot = decision_history.load_history(project, redact=None)
        record = next(r for r in snapshot.records if r.decision_id == expected)
        assert record.workbench.processing_state == "failed"
        assert record.workbench.record_version == 2
    finally:
        fixture.stop()


def test_failed_feedback_write_keeps_the_exact_decision_id(
    tmp_path: __import__("pathlib").Path,
) -> None:
    root = tmp_path / "p"
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    project_id = decision_wire.project_id_for(root)
    redact = decision_wire.SubstringRedactor(())
    meta = decision_lifecycle.DecisionMeta.create(
        "k-t08", logical_id=str(uuid.uuid4()), initiator_role="pm"
    )
    expected = f"dp1-dispatch-type:{meta.logical_id}"

    sink = root / "lifecycle.jsonl"
    store = decision_lifecycle.LifecycleStore(
        sink=sink,
        project_id=project_id,
        redact=redact,
        scope_kind="test",
        error_sink=root / "lifecycle-errors.jsonl",
    )
    start = decision_lifecycle.record_start(store, meta, decision_id=expected)
    assert start.recorded, start
    start_rows = list(decision_wire.read_events(sink).events)
    assert [row["decision_id"] for row in start_rows] == [expected]

    # A feedback write that cannot land: the sink is a directory, the failure
    # sidecar still gets the exact association (never a legacy/unlinked row).
    broken = tmp_path / "broken" / "lifecycle.jsonl"
    broken.mkdir(parents=True)
    broken_store = decision_lifecycle.LifecycleStore(
        sink=broken,
        project_id=project_id,
        redact=redact,
        scope_kind="test",
        error_sink=root / "lifecycle-errors.jsonl",
    )
    failed = decision_lifecycle.record_executed(
        broken_store, meta, decision_id=expected, action="record", result="answer-returned"
    )
    assert failed.recorded is False
    assert failed.error_recorded is True
    errors = list(decision_wire.read_events(root / "lifecycle-errors.jsonl").events)
    assert len(errors) == 1
    assert errors[0]["logical_id"] == meta.logical_id
    assert errors[0]["decision_id"] == expected
    assert errors[0]["stage"] == "executed"


# ---------------------------------------------------------------------------
# 3. dp25: the valid file is the completion authority
# ---------------------------------------------------------------------------


DP25_MATERIAL = {
    "delivery_goal": "Prove that the dp25 completion is the valid sign-off file.",
    "actual_completion": "The Python integration loop is implemented and tested.",
    "verification_evidence": {
        "verified": ["pytest test_decision_context_integration.py -q"],
        "unverified": ["real Jev endpoint (not authorized)"],
    },
    "unfinished_impact": [],
}


def _sign(project: __import__("pathlib").Path, key: str, logical_id: str):
    envelope = json.dumps(
        {
            "material": DP25_MATERIAL,
            "meta": {
                "record_version": 2,
                "logical_id": logical_id,
                "key": key,
                "task_key": None,
                "initiator_role": "coding",
                "retry_of": None,
            },
        },
        ensure_ascii=False,
    )
    return _run_mw(
        "decide",
        "sign",
        key,
        "--project",
        str(project),
        "--stdin",
        "--json",
        stdin_text=envelope,
    )


def test_valid_signoff_file_is_the_completion_authority(
    tmp_path: __import__("pathlib").Path,
) -> None:
    fixture = pg._FixtureServer().start()
    try:
        project = _project(
            tmp_path, base_url=fixture.url, api_key="sk-t08-fixture-0123456789abcdef"
        )
        key = "dc-t08-integration"
        (project / ".agenticdoc" / key).mkdir(parents=True)
        logical_id = str(uuid.uuid4())
        completed = _sign(project, key, logical_id)
        payload = _read_json_stdout(completed)
        assert payload["logical_id"] == logical_id
        assert payload["conclusion"] == "finalize"
        assert payload["signoff_status"] == "written"
        assert payload["feedback_status"] == "recorded"
        signoff_path = __import__("pathlib").Path(payload["signoff_path"])
        assert signoff_path.is_file()
        expected_id = f"dp25-signoff-conclusion:{logical_id}"

        rows = _lifecycle_rows(project)
        starts = [row for row in rows if row.get("kind") == "record-start"]
        assert [row["decision_id"] for row in starts] == [expected_id]
        signoff_rows = [row for row in rows if row.get("lifecycle") == "signoff"]
        assert len(signoff_rows) == 1
        assert signoff_rows[0]["decision_id"] == expected_id
        assert signoff_rows[0]["snapshot_sha256"] == payload["snapshot_sha256"]

        snapshot = decision_history.load_history(project, redact=None)
        record = next(r for r in snapshot.records if r.decision_id == expected_id)
        bench = record.workbench
        assert bench.processing_state == "completed"
        assert bench.record_version == 2
        assert len(bench.nodes) == 10
        receipt = next(node for node in bench.nodes if node.id == "receipt")
        signoff = receipt.detail["signoff"]
        assert signoff["file_verified"] is True
        assert signoff["snapshot_sha256"] == payload["snapshot_sha256"]
        assert signoff["file_sha256"] == hashlib.sha256(signoff_path.read_bytes()).hexdigest()

        # A current-material mismatch never erases the recorded historical fact:
        # the file stays the authority for this logical id + snapshot.
        signoff_path.unlink()
        after = decision_history.load_history(project, redact=None)
        gone = next(r for r in after.records if r.decision_id == expected_id)
        assert gone.workbench.processing_state != "completed"
        node = next(n for n in gone.workbench.nodes if n.id == "receipt")
        assert node.detail["signoff"]["file_verified"] is False
        assert "missing" in node.detail["signoff"]["file_reason"]
    finally:
        fixture.stop()


def test_completed_survives_a_failed_signoff_feedback_write(
    tmp_path: __import__("pathlib").Path,
) -> None:
    fixture = pg._FixtureServer().start()
    try:
        project = _project(
            tmp_path, base_url=fixture.url, api_key="sk-t08-fixture-0123456789abcdef"
        )
        key = "dc-t08-integration"
        key_dir = project / ".agenticdoc" / key
        key_dir.mkdir(parents=True)
        logical_id = str(uuid.uuid4())
        first = _sign(project, key, logical_id)
        payload = _read_json_stdout(first)
        assert payload["feedback_status"] == "recorded"

        # Retry the same persisted logical id (zero model calls) with the
        # lifecycle ledger closed for writes: the file write is already done, so
        # the record must stay completed while the failed feedback is reported.
        sink = decision_wire.production_lifecycle_sink(project)
        saved = tmp_path / "lifecycle.saved"
        shutil.copy2(sink, saved)
        sink.unlink()
        sink.mkdir()
        try:
            retried = _sign(project, key, logical_id)
        finally:
            sink.rmdir()
            shutil.copy2(saved, sink)
        retry_payload = _read_json_stdout(retried)
        assert retry_payload["record_status"] == "existing"
        assert retry_payload["model_called"] is False
        assert retry_payload["signoff_status"] == "existing"
        assert retry_payload["feedback_status"] == "failed"

        snapshot = decision_history.load_history(project, redact=None)
        record = next(
            r
            for r in snapshot.records
            if r.decision_id == f"dp25-signoff-conclusion:{logical_id}"
        )
        assert record.workbench.processing_state == "completed"
        receipt = next(node for node in record.workbench.nodes if node.id == "receipt")
        assert receipt.detail["signoff"]["file_verified"] is True
        assert receipt.detail["errors"], "the failed feedback write must be reported"
        assert any(row["stage"] == "signoff" for row in receipt.detail["errors"])
        errors = _feedback_rows(project)
        assert errors, "the independent failure ledger must keep the fact"
        assert all(
            row["decision_id"] == f"dp25-signoff-conclusion:{logical_id}"
            for row in errors
        )
    finally:
        fixture.stop()


# ---------------------------------------------------------------------------
# 4. The four shipped cases: edit -> real observe submit -> exact HTTP body
# ---------------------------------------------------------------------------


EDIT_PATH = {
    "dp1-dispatch-type": "task_goal",
    "dp2-checkpoint-split": "task_goal",
    "dp3-worker-clarify": "question",
    "dp25-signoff-conclusion": "delivery_goal",
}


def _edited_state(case: dict) -> tuple[dict, str]:
    state = copy.deepcopy(case["book"]["state"])
    marker = f" [t08-observed-{case['dp']}]"
    path = EDIT_PATH[case["dp"]]
    assert isinstance(state[path], str)
    state[path] = state[path].rstrip() + marker
    return state, marker


def test_four_shipped_cases_submit_real_material_and_stay_observe_only(
    tmp_path: __import__("pathlib").Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executor_calls: list[tuple[str, object]] = []

    def _spy(dp_id: str):
        def executor(answers, trigger):
            executor_calls.append((dp_id, answers))
            return "acted"

        return executor

    for point in dpts.DP_REGISTRY:
        monkeypatch.setitem(
            dpts._REGISTRY_BY_ID,
            point.id,
            __import__("dataclasses").replace(point, executor=_spy(point.id)),
        )

    with pg._live(tmp_path) as (project, instance, fixture, created):
        token = pg._page_token(instance)
        production_before = _tree(project / ".agenticdoc")
        config_before = (project / ".mw" / "decide.json").read_bytes()
        for index, name in enumerate(CASE_NAMES, start=1):
            case_data = case(name)
            dp = case_data["dp"]
            state, marker = _edited_state(case_data)
            # The material stays the shipped case verbatim (state only, one appended
            # marker). The book's *evidence notes* are local commands: the shipped
            # notes point at repo files that do not exist in this tmp project, and
            # the evidence note is not decision material.
            book = {
                "schema_version": decision_book.BOOK_SCHEMA_VERSION,
                "decision_point": dp,
                "state": state,
                "notes": {
                    "evidence": {
                        path: "cmd: true"
                        for path in dpts.REQUIRED_STATE_FIELDS[dp]
                    }
                },
            }
            submit_id = f"t08-{index}-{dp}"
            status, payload = pg._post(
                instance,
                "/api/test/submit",
                {"dp": dp, "book": book, "submit_id": submit_id, "observe_only": True},
                token,
            )
            assert status == 200, (dp, payload)
            result = pg._ok_data(payload)
            assert result["state"] == "succeeded", (dp, result)
            assert result["observe_only"] is True
            assert result["decision_id"] == f"{dp}:{submit_id}"
            assert fixture.calls == index, dp

            body = json.loads(fixture.requests[-1]["body"].decode("utf-8"))
            assert set(body) == {"model", "state", "questions"}, dp
            expected_state = dpts.model_state_for(dp, state)
            assert body["state"] == expected_state, dp
            assert marker in json.dumps(body["state"], ensure_ascii=False)
            questions = dpts.questions_map(dpts.get_decision_point(dp))
            assert set(body["questions"]) == set(questions), dp
            for qid, spec in questions.items():
                wire_q = body["questions"][qid]
                assert wire_q["type"] == spec["type"], (dp, qid)
                assert wire_q["instructions"] == spec["instructions"], (dp, qid)
                if spec["type"] == decision.QUESTION_CHOICE:
                    if "dynamic_choices" in spec:
                        options = [item["id"] for item in state[spec["dynamic_choices"]]]
                    else:
                        options = list(spec["choices"])
                    assert list(wire_q["criteria"]) == options, (dp, qid)

            # One real submission, joined by ids (never "the latest call").
            detail_status, detail_payload = pg._get(
                instance, f"/api/test/submissions/{submit_id}", token
            )
            assert detail_status == 200
            detail = pg._ok_data(detail_payload)
            assert detail["dp"] == dp
            assert detail["state"] == "succeeded"
            assert detail["book_ref"]
            attempts = detail["attempts"]
            assert len(attempts) == 1, dp
            attempt = attempts[0]
            assert attempt["url_path"] == "/v1/decisions"
            request_copy = attempt["request"]
            assert request_copy.get("output_omitted") is not True, dp
            assert json.loads(request_copy["text"]) == body, dp
            assert attempt["http_status"] == 200

        # The test record list is a real chain with the same answer, not a shell.
        history_status, history_payload = pg._get(instance, "/api/test/history", token)
        assert history_status == 200
        history = pg._ok_data(history_payload)
        assert history["scope"] == "test"
        assert len(history["records"]) == len(CASE_NAMES)
        for record in history["records"]:
            assert record["state"] == "succeeded"
            assert record["answer_persisted"] is True
            assert record["attempts"], record["submission_id"]

        assert executor_calls == [], "observe-only submissions never run a business action"
        assert _tree(project / ".agenticdoc") == production_before
        assert (project / ".mw" / "decide.json").read_bytes() == config_before
        assert created != [], "the shared provider was created for this control root"


# ---------------------------------------------------------------------------
# 5. CLI contract: the offline probe and the explicit legacy refusal
# ---------------------------------------------------------------------------


def test_dp_verify_probes_the_four_new_contracts_offline(
    tmp_path: __import__("pathlib").Path,
) -> None:
    project = _project(tmp_path, enabled=False)
    completed = _run_mw("decide", "dp", "verify", "--project", str(project), "--json")
    payload = _read_json_stdout(completed)
    assert payload["ok"] == len(payload["points"])
    by_id = {row["id"]: row for row in payload["points"]}
    for dp in EDIT_PATH:
        row = by_id[dp]
        assert row["ok"] is True, (dp, row["failures"])
        assert row["failures"] == []
        assert row["questions"] >= 1
    exported = {point["id"]: point for point in mw._dp_export_doc()[0]["points"]}
    for dp in EDIT_PATH:
        probe = mw._dp_verify_state(exported[dp])
        required = [field["name"] for field in exported[dp]["required_state_fields"]]
        assert sorted(_leaves(probe)) == sorted(required), dp


def _leaves(state: object, prefix: str = "") -> list[str]:
    if not isinstance(state, dict):
        return [prefix]
    out: list[str] = []
    for key, value in state.items():
        out.extend(_leaves(value, f"{prefix}.{key}" if prefix else str(key)))
    return out


def test_legacy_sign_without_stdin_refuses_with_the_new_material_contract(
    tmp_path: __import__("pathlib").Path,
) -> None:
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / "dc-t08-integration"
    key_dir.mkdir(parents=True)
    before = _tree(project)
    completed = _run_mw(
        "decide", "sign", "dc-t08-integration", "--project", str(project), "--json"
    )
    assert completed.returncode == 2
    message = completed.stderr
    assert "--stdin" in message
    for part in (
        "delivery_goal",
        "actual_completion",
        "verification_evidence",
        "unfinished_impact",
    ):
        assert part in message, message
    assert _tree(project) == before, "a refusal writes nothing"
