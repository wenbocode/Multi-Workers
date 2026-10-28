"""T21 readable provenance and the native dispatch-refused/rework shape."""
from __future__ import annotations

import pytest

import test_decision_context_readable_ui as ui
import test_decision_history_feedback as feedback

_isolated_environment = ui._isolated_environment


@pytest.fixture(autouse=True)
def _visible_node_snapshot(monkeypatch):
    marker = '    nodeDetail: nodeText("dag-node-detail"),'
    assert marker in ui.DOM_HARNESS_JS
    monkeypatch.setattr(ui, "DOM_HARNESS_JS", ui.DOM_HARNESS_JS.replace(marker, marker + '''
    nodeReadable: visibleText(document.getElementById("dag-node-detail")),
    basisAudits: findAll(documentRoot, '[data-testid="basis-audit"]').map((node) => ({text: node.textContent, open: node.hasAttribute("open")})),'''))


def _show(tmp_path, node, basis=None, mutate=None):
    _, record = feedback._record(tmp_path)
    detail = next(n.detail for n in record.workbench.nodes if n.id == node)
    if basis is not None:
        detail["basis"] = basis
    if mutate is not None:
        mutate(detail)
    result = ui._run_dom(tmp_path, {
        "hash": "#boot=t21", "bootstrap": {"status": 200, "body": ui._envelope({"page_token": "t21-fake"})},
        "history": {"status": 200, "body": ui._envelope({"records": [record.as_dict()], "total": 1, "offset": 0, "limit": 5})},
        "detailByOpaque": {record.opaque_id: {"status": 200, "body": ui._envelope(record.as_dict(detail=True))}},
        "steps": [{"type": "click", "target": '[data-testid="record-dag-open"]'},
            {"type": "click", "target": f'[data-testid="dag-node"][data-node-id="{node}"]', "snapshot": "selected"}],
    })
    snapshot = ui._snapshot(result, "selected")
    assert result["storageWrites"] == []
    assert all(c["method"] == "GET" or c["url"] == "/api/bootstrap" for c in result["fetchCalls"])
    return snapshot, result


@pytest.mark.parametrize("node,basis,explanation", [
    ("key", "record-start.key", "创建记录登记了所属项目"),
    ("role", "record-start.initiator_role", "创建记录登记了发起角色"),
    ("dp", "decision_id prefix (a value, not a path)", "决策编号标明了判断类型"),
    ("input", "ledger.book-snapshot (the stored input body)", "存储的输入副本记录了本次提交内容"),
    ("model", "ledger.call-end", "调用结束记录确认了模型和返回情况"),
    ("request", "ledger.attempt-start (the stored request copy)", "请求记录保存了实际发送内容"),
    ("response", "ledger.attempt-end (the stored response copy)", "返回记录保存了实际响应内容"),
    ("receipt", "consumed is receipt only: it never means completed", "接收回执只证明答案已被接收，不证明任务已完成"),
    ("action", "ledger.lifecycle.executed (a declared action really happened)", "行动回执记录了某个动作；是否完成还需看结算结果"),
])
def test_basis_has_plain_meaning_and_raw_source_is_closed_audit(tmp_path, node, basis, explanation):
    selected, _ = _show(tmp_path, node, [basis])
    assert explanation in selected["nodeReadable"]
    assert basis not in selected["nodeReadable"]
    assert any(basis in a["text"] for a in selected["basisAudits"])
    assert all(a["open"] is False for a in selected["basisAudits"])


def test_recorded_policy_threshold_basis_explains_which_configuration_is_evidence(tmp_path):
    raw = "ledger.book-snapshot.policy.min_confidence (the effective threshold this decision applied)"
    def policy(detail):
        detail["policy_result"]["min_confidence"] = 0.7
        detail["policy_result"]["basis"] = [raw]
    selected, _ = _show(tmp_path, "decide", ["ledger.decision-end"], policy)
    assert "输入快照记录了本次生效阈值，未使用当前配置补猜" in selected["nodeReadable"]
    assert raw not in selected["nodeReadable"]
    assert raw in selected["nodeDetail"]


def test_dispatch_rework_does_not_claim_the_answer_or_worker_failed(tmp_path):
    def refused(detail):
        detail["executed"][0]["action"] = "record"
        detail["executed"][0]["result"] = "answer-returned"
        detail["settled"]["outcome"] = "rework"
        detail["settled"]["reason"] = "dispatch-refused"
    selected, _ = _show(tmp_path, "action", ["settled outcome from ledger.lifecycle.settled"], refused)
    text = selected["nodeReadable"]
    assert "仅记录了模型返回，不代表 worker 已启动" in text
    assert "派发被拒绝，需要处理派发阻塞；不代表模型答案被判错" in text
    assert "D-003" not in text and "写入允许面" not in text  # not recorded in this receipt
    assert "answer-returned" in text and "dispatch-refused" in text  # raw result codes retained


def test_unknown_basis_is_not_guessed_and_xss_stays_text(tmp_path):
    raw = 'unknown.source.<img src=x onerror="globalThis.PWNED=1">'
    selected, _ = _show(tmp_path, "key", [raw])
    assert "原始依据已记录，但其含义尚未识别；不据此推断执行结果" in selected["nodeReadable"]
    assert raw not in selected["nodeReadable"]
    assert raw in selected["nodeDetail"]
    assert selected["pwned"] is False and selected["imgCount"] == 0


def test_missing_basis_is_not_filled_from_node_status(tmp_path):
    selected, _ = _show(tmp_path, "key", [])
    assert "依据：未记录" in selected["nodeReadable"]
    assert selected["basisAudits"] == []


def test_rework_with_other_reason_retains_the_actual_record_without_dispatch_guess(tmp_path):
    def other(detail):
        detail["settled"]["outcome"] = "rework"
        detail["settled"]["reason"] = "actual review found missing tests"
    selected, _ = _show(tmp_path, "action", [], other)
    assert "actual review found missing tests" in selected["nodeReadable"]
    assert "派发被拒绝" not in selected["nodeReadable"]
