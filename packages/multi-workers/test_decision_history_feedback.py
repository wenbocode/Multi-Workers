"""T20: real stored feedback -> history projection -> shipped DOM, no model calls."""
from __future__ import annotations

import json

import pytest

import decision_history as history
import decision_lifecycle as lifecycle
import decision_monitor
import decision_wire as wire
import test_decision_context_readable_backend as backend
import test_decision_context_readable_ui as ui
import test_decision_monitor as monitor
import test_decision_dashboard_assets as assets

_isolated_environment = ui._isolated_environment


def _record(tmp_path):
    root = backend._root(tmp_path)
    store = backend._store(root)
    meta = backend._meta()
    decision_id = backend._append_archive(root, dp=backend.DP1, trigger_id="t20",
        authority="advisory", escalated_reason=None, confidence=0.94)
    lifecycle.record_start(store, meta, decision_id=decision_id)
    lifecycle.record_consumed(store, meta, decision_id=decision_id, answer="research", reason="PM received the suggestion")
    lifecycle.record_executed(store, meta, decision_id=decision_id, action="type-read",
        result="kept-type:research", reason="explicit role retained")
    lifecycle.record_settled(store, meta, decision_id=decision_id, outcome="ok", reason="dispatch round finished")
    backend._add_call(root, decision_id=decision_id, dp=backend.DP1, confidence=0.94)
    backend._add_decision_end(root, decision_id=decision_id, dp=backend.DP1,
        status="suggested", escalated_reason=None, mode="suggest", intent="answer")
    snapshot = history.load_history(root, redact=wire.SubstringRedactor((backend.SECRET,)))
    record = next(r for r in snapshot.records if r.decision_id == decision_id)
    return root, record


def _dom(tmp_path, record):
    public = record.as_dict(detail=True)
    scenario = {
        "hash": "#boot=t20", "bootstrap": {"status": 200, "body": ui._envelope({"page_token": "t20-token"})},
        "history": {"status": 200, "body": ui._envelope({"records": [record.as_dict()], "total": 1, "offset": 0, "limit": 5})},
        "detailByOpaque": {record.opaque_id: {"status": 200, "body": ui._envelope(public)}},
        "steps": [{"type": "click", "target": '[data-testid="record-dag-open"]'}] + [
            {"type": "click", "target": f'[data-testid="dag-node"][data-node-id="{node}"]', "snapshot": node}
            for node in ("decide", "receipt", "action", "model")],
    }
    return ui._run_dom(tmp_path, scenario)


def test_real_writer_reasons_survive_history_projection(tmp_path):
    _, record = _record(tmp_path)
    nodes = backend._nodes(record)
    assert nodes["receipt"]["detail"]["consumed"]["reason"] == "PM received the suggestion"
    assert nodes["action"]["detail"]["executed"][0]["reason"] == "explicit role retained"


def test_real_history_selection_and_receipt_reach_shipped_dom(tmp_path):
    _, record = _record(tmp_path)
    result = _dom(tmp_path, record)
    assert "research" in ui._snapshot(result, "boot")["rows"][0]
    receipt = ui._snapshot(result, "receipt")["nodeDetail"]
    assert "research" in receipt
    assert "PM received the suggestion" in receipt
    assert "接收不代表采纳或处理完成" in receipt
    assert "answer_source" not in receipt and "actor_kind：未记录" not in receipt
    assert result["storageWrites"] == []
    assert all(call["url"] == "/api/bootstrap" or call["method"] == "GET" for call in result["fetchCalls"])


def test_suggested_and_recorded_basis_are_not_unknown(tmp_path):
    _, record = _record(tmp_path)
    text = ui._snapshot(_dom(tmp_path, record), "decide")["nodeDetail"]
    assert "模型建议（不代表已采纳或执行）" in text
    assert "suggested（未识别" not in text
    assert "ledger.call-end" in text
    assert "the recorded advice path" in text
    assert "依据：未记录" not in text
    assert "0.7" not in text  # no recorded threshold; current config is not evidence


def test_actions_and_outcomes_have_plain_explanation_and_real_reason(tmp_path):
    _, record = _record(tmp_path)
    text = ui._snapshot(_dom(tmp_path, record), "action")["nodeDetail"]
    assert "读取任务类型" in text and "本轮处理完成，不代表整个任务已交付" in text
    assert "kept-type:research" in text and "explicit role retained" in text
    assert "dispatch round finished" in text
    assert "answer_source" not in text


def test_unknown_action_and_outcome_keep_raw_values(tmp_path):
    _, record = _record(tmp_path)
    detail = record.workbench.nodes[-1].detail
    detail["executed"][0]["action"] = "future-action"
    detail["settled"]["outcome"] = "future-outcome"
    text = ui._snapshot(_dom(tmp_path, record), "action")["nodeDetail"]
    assert "future-action" in text and "future-outcome" in text
    assert "本轮处理完成" not in text


def test_not_evaluated_is_a_known_policy_disposition(tmp_path):
    _, record = _record(tmp_path)
    detail = next(n.detail for n in record.workbench.nodes if n.id == "decide")
    detail["policy_result"]["disposition"] = "not-evaluated"
    text = ui._snapshot(_dom(tmp_path, record), "decide")["nodeDetail"]
    assert "未记录策略判定" in text and "not-evaluated（未识别" not in text


def test_answer_source_is_audit_only_when_present(tmp_path):
    _, record = _record(tmp_path)
    detail = next(n.detail for n in record.workbench.nodes if n.id == "model")
    detail["answer_source"] = "api"
    text = ui._snapshot(_dom(tmp_path, record), "model")["nodeDetail"]
    assert "答案来源审计（按需查看）" in text
    assert "answer_source" in text and "api" in text


def test_default_monitor_history_withholds_stored_free_text_without_loading_credentials(tmp_path):
    root, record = _record(tmp_path)
    calls = []
    deps = decision_monitor.MonitorDeps(redactor_factory=lambda path: calls.append(path))
    snapshot = deps.load_history(root)
    folded = next(r for r in snapshot.records if r.decision_id == record.decision_id)
    assert folded.workbench.selection is None
    nodes = backend._nodes(folded)
    assert nodes["receipt"]["detail"]["consumed"]["answer"] is None
    assert nodes["action"]["detail"]["executed"][0]["result"] is None
    assert folded.redaction.omitted_fields > 0 and calls == []


def test_new_reason_projection_remains_secret_safe_and_read_only(tmp_path):
    root, record = _record(tmp_path)
    sink = wire.production_lifecycle_sink(root)
    raw = sink.read_bytes()
    # Synthetic ledger only: a wider read-side known set protects newly projected prose.
    public = history.load_history(root, redact=wire.SubstringRedactor(("explicit role retained",))).detail(record.opaque_id).as_dict(detail=True)
    assert "explicit role retained" not in json.dumps(public)
    assert sink.read_bytes() == raw


def test_injected_redactor_http_history_includes_real_selection_and_receipt(tmp_path):
    root, record = _record(tmp_path)
    deps = decision_monitor.MonitorDeps(redactor=wire.SubstringRedactor((backend.SECRET,)))
    with monitor._running(root, deps=deps) as instance:
        token = monitor._page_token(instance)
        listing = assets._capture(instance, "/api/history", token)
        detail = assets._capture(instance, f"/api/history/{record.opaque_id}", token)
    assert listing["data"]["records"][0]["workbench"]["selection"] == "research"
    nodes = {n["id"]: n for n in detail["data"]["workbench"]["nodes"]}
    assert nodes["receipt"]["detail"]["consumed"]["answer"] == "research"
