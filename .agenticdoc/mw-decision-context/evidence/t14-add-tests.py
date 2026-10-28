from pathlib import Path
p=Path(__file__).resolve().parents[3]/'packages/multi-workers/test_decision_context_readable_ui.py'
with p.open('a',encoding='utf-8',newline='') as f:
 f.write('''

@pytest.mark.parametrize("local", [True, False])
def test_screenshot_log_blocks_are_not_default_test_content(tmp_path, local):
    scenario = _interaction_scenario()
    if local:
        scenario["testHistory"] = {"status": 200, "body": _envelope({"records": [], "total": 0})}
    scenario["steps"] = [{"type": "click", "target": "#tab-playground", "snapshot": "test"}]
    if not local:
        scenario["steps"].append({"type": "dispatch", "target": "#pg-submission-log", "event": {"type": "toggle"}})
        scenario["steps"].append({"type": "click", "target": '[data-testid="pg-dag-node"][data-node-id="dp"]', "snapshot": "node"})
    result = _run_dom(tmp_path, scenario)
    snap = _snapshot(result, "test")
    for field in ("默认模式", "配置来源", "questions_version", "executor", "wired", "配置层", "submission_id", "decision_ran", "state_digest", "projection_sha256", "当次答案（来自该 submission", "拒绝/问题项：无", "采纳判定与动作预览"):
        assert field not in snap["pgVisible"], (field, snap["pgVisible"])
    assert [n["id"] for n in snap["pgGraph"]["nodes"]] == NODE_IDS
    if local:
        assert "未持久化" not in snap["pgDetailText"]
        assert "submission_id" not in snap["pgDetailText"]
    else:
        assert "submission_id" in snap["pgDetailText"], "facts remain in closed explicit log"
        assert "decision_id" in _snapshot(result, "node")["pgNodeDetail"]
    assert all(c["method"] == "GET" or c["url"] == "/api/bootstrap" for c in result["fetchCalls"])
''')
