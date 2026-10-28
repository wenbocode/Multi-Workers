"""T22 the action node tells task-before -> handling -> task-after, not receipt success."""
from __future__ import annotations

import pytest
import decision_history

import test_decision_context_readable_ui as ui
import test_decision_history_feedback as feedback
import test_decision_task_state as facts

_isolated_environment=ui._isolated_environment


@pytest.fixture(autouse=True)
def _readable_snapshot(monkeypatch):
    marker='    nodeDetail: nodeText("dag-node-detail"),'
    assert marker in ui.DOM_HARNESS_JS
    monkeypatch.setattr(ui,"DOM_HARNESS_JS",ui.DOM_HARNESS_JS.replace(marker,marker+
        '\n    nodeReadable: visibleText(document.getElementById("dag-node-detail")),'
        '\n    taskChips: findAll(documentRoot, ".task-state-chip").map(function (node) { return node.textContent; }),'
        '\n    taskItems: findAll(documentRoot, ".task-state-item").map(function (node) { return node.textContent; }),'))


def _show(tmp_path,**options):
    withhold=options.pop("withhold",False)
    root,record=facts._record(tmp_path,**options)
    if withhold: record=decision_history.load_history(root).detail(record.opaque_id)
    result=feedback._dom(tmp_path,record)
    assert result["storageWrites"]==[]
    assert all(c["method"]=="GET" or c["url"]=="/api/bootstrap" for c in result["fetchCalls"])
    return ui._snapshot(result,"action")


def test_action_default_has_task_before_handling_after_and_change(tmp_path):
    snap=_show(tmp_path,before=facts.state("not-queued",completed=["已核对任务卡"],remaining=["等待派发"],blockers=[]),after=facts.state("pending",completed=["已提交队列"],remaining=["等待 worker 启动"],blockers=[]))
    text=snap["nodeReadable"]
    for label in ("决策前","实际处理","决策后","变化说明","已完成","待处理","阻塞"):
        assert label in text
    assert text.index("决策前")<text.index("实际处理")<text.index("决策后")<text.index("变化说明")
    assert "未入队" in text and "已入队，等待执行" in text
    assert "已核对任务卡" in text and "等待 worker 启动" in text
    assert "Agent 报告" in text and "2026-10-24" in text
    assert "任务从未入队变为已入队，等待执行" in text
    assert "不代表 worker 已启动" in text


def test_legacy_missing_state_is_not_inferred_from_refused_dispatch(tmp_path):
    snap=_show(tmp_path,outcome="rework")
    text=snap["nodeReadable"]
    assert "决策前" in text and "决策后" in text
    assert "任务状态未记录" in text and "无法确认任务状态变化" in text
    assert "任务从" not in text and "任务已完成" not in text


def test_unchanged_running_state_is_not_task_completion_even_if_round_ok(tmp_path):
    text=_show(tmp_path,before=facts.state("running"),after=facts.state("running"))["nodeReadable"]
    assert "执行状态未变化：执行中" in text
    assert "本轮处理完成，不代表整个任务已交付" in text
    assert "任务已完成" not in text


def test_null_and_explicit_empty_lists_are_distinguished(tmp_path):
    text=_show(tmp_path,before=facts.state(),after=facts.state(completed=[],remaining=[],blockers=[]))["nodeReadable"]
    assert "已完成：未记录" in text and "已完成：无" in text
    assert "阻塞：未记录" in text and "阻塞：无" in text


def test_unknown_state_does_not_become_not_queued_or_failed(tmp_path):
    text=_show(tmp_path,before=facts.state("unknown",source="worker-registry"),after=facts.state("unknown",source="worker-registry"),outcome="rework")["nodeReadable"]
    assert "任务状态未知" in text and "无法确认任务状态变化" in text
    assert "任务从" not in text


def test_withheld_snapshot_is_not_described_as_unrecorded(tmp_path):
    text=_show(tmp_path,before=facts.state(completed=["private step"]),after=facts.state(),withhold=True)["nodeReadable"]
    assert "当时快照已记录，但安全过滤暂不显示" in text
    assert "没有当时快照" not in text
    assert "private step" not in text
    assert "无法确认任务状态变化" in text


def test_snapshot_progress_renders_as_structured_items_with_status_chips(tmp_path):
    snap=_show(tmp_path,before=facts.state("not-queued",completed=["已核对任务卡"],remaining=["等待派发"],blockers=[]),after=facts.state("pending",completed=["已提交队列"],remaining=[],blockers=[]))
    # Two views render the same facts (记录详情"行动与处理" + DAG 节点详情), each as a
    # status chip plus one list item per progress entry.
    assert snap["taskChips"]==["未入队","已入队，等待执行"]*2
    assert snap["taskItems"]==["已核对任务卡","等待派发","已提交队列"]*2


def test_snapshot_progress_is_xss_safe_and_secret_redacted(tmp_path):
    injected='<img src=x onerror="globalThis.PWNED=1">'
    snap=_show(tmp_path,before=facts.state(completed=[injected]),after=facts.state(blockers=[facts.backend.SECRET+" missing input"]))
    assert injected in snap["nodeReadable"]
    assert facts.backend.SECRET not in snap["nodeDetail"]
    assert snap["pwned"] is False and snap["imgCount"]==0
