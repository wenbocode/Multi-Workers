from pathlib import Path
p=Path(__file__).resolve().parents[3]/'packages/multi-workers/test_decision_context_readable_ui.py'
with p.open('a',encoding='utf-8',newline='') as f:
 f.write('''

def _interaction_scenario():
    payloads = _published_payloads()
    return {
        "hash": "#boot=fixture", "bootstrap": wb._bootstrap(payloads["token"]),
        "history": payloads["default"], "dps": payloads["dps"],
        "testHistory": payloads["testHistory"], "submission": payloads["submission"],
        "scaffold": {"status": 200, "body": _envelope({"book": CASES["dp1-dispatch-type"]["book"]})},
        "validate": {"status": 200, "body": _envelope({"ok": True, "request_preview": {"model": "jev-latest", "state": {"task_goal": "preview-only"}, "questions": {}}})},
    }


def test_test_tab_and_explicit_refresh_load_only_test_reads_and_switch_dag(tmp_path):
    scenario = _interaction_scenario()
    scenario["steps"] = [
        {"type": "click", "target": '[data-testid="record-dag-open"]'},
        {"type": "click", "target": "#tab-playground", "snapshot": "test"},
        {"type": "click", "target": "#dashboard-refresh", "snapshot": "refresh"},
    ]
    result = _run_dom(tmp_path, scenario)
    switched = _snapshot(result, "test")
    assert switched["dialogVisible"] is False
    assert [n["id"] for n in switched["pgGraph"]["nodes"]] == NODE_IDS
    assert any(c["url"] == "/api/test/history" for c in switched["fetchCalls"])
    assert len(_snapshot(result, "refresh")["fetchCalls"]) > len(switched["fetchCalls"])
    assert all(c["method"] == "GET" or c["url"] == "/api/bootstrap" for c in result["fetchCalls"])


def test_scaffold_preview_and_refusal_have_local_feedback_without_fake_api_capture(tmp_path):
    scenario = _interaction_scenario()
    scenario["steps"] = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-scaffold", "snapshot": "scaffold"},
        {"type": "click", "target": "#pg-validate", "snapshot": "preview"},
        {"type": "click", "target": '[data-testid="pg-dag-node"][data-node-id="request"]', "snapshot": "request"},
        {"type": "setValue", "target": "#material-editor", "value": "{bad"},
        {"type": "dispatch", "target": "#material-editor", "event": {"type": "input"}},
        {"type": "click", "target": "#pg-submit", "snapshot": "refused"},
    ]
    result = _run_dom(tmp_path, scenario)
    assert "骨架" in _snapshot(result, "scaffold")["pgOperations"]
    assert "预览" in _snapshot(result, "preview")["pgOperations"]
    assert "preview-only" in _snapshot(result, "request")["pgNodeDetail"]
    assert "未发送" in _snapshot(result, "request")["pgNodeDetail"]
    assert not _snapshot(result, "request")["captures"]
    assert "拒绝" in _snapshot(result, "refused")["pgOperations"]
    assert not any(c["url"] == "/api/test/submit" for c in result["fetchCalls"])


def test_submission_polls_each_second_until_terminal_and_retry_uses_new_id(tmp_path):
    scenario = _interaction_scenario()
    terminal = dict(scenario["submission"]["body"]["data"], record_status="recorded")
    running = dict(terminal, state="running", decision_ran=False, http_attempts=0, call_id=None)
    scenario["submit"] = [
        {"status": 200, "body": _envelope(terminal), "defer": "submit"},
        {"status": 200, "body": _envelope(terminal)},
    ]
    scenario["submission"] = [scenario["submission"],
        {"status": 200, "body": _envelope(running)},
        {"status": 200, "body": _envelope(terminal)},
        {"status": 200, "body": _envelope(terminal)},
    ]
    scenario["steps"] = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-scaffold"},
        {"type": "click", "target": "#pg-submit", "snapshot": "start"},
        {"type": "tick", "snapshot": "running"},
        {"type": "click", "target": '[data-testid="pg-dag-node"][data-node-id="dp"]'},
        {"type": "tick", "snapshot": "terminal"},
        {"type": "release", "id": "submit", "snapshot": "done"},
        {"type": "tick", "snapshot": "stopped"},
        {"type": "click", "target": "#pg-retry", "snapshot": "retried"},
    ]
    result = _run_dom(tmp_path, scenario)
    start = _snapshot(result, "start")
    assert start["submitDisabled"] and start["activeTimers"] == 1
    assert "进行" in start["pgStatus"]
    running = _snapshot(result, "running")
    assert len(running["fetchCalls"]) > len(start["fetchCalls"])
    assert running["pgHistory"] and running["pgOperations"]
    terminal_snap = _snapshot(result, "terminal")
    assert terminal_snap["activeTimers"] == 0
    assert "节点 dp" in terminal_snap["pgNodeDetail"]
    done, stopped = _snapshot(result, "done"), _snapshot(result, "stopped")
    assert len(done["fetchCalls"]) == len(stopped["fetchCalls"])
    assert not done["submitDisabled"] and "succeeded" in done["pgStatus"]
    bodies = [json.loads(c["body"]) for c in result["fetchCalls"] if c["url"] == "/api/test/submit"]
    assert len(bodies) == 2 and bodies[0]["submit_id"] != bodies[1]["submit_id"]
    assert bodies[1]["retry_of"] == bodies[0]["submit_id"]
    assert all(b["observe_only"] is True for b in bodies)
    assert all(d == 1000 for d in stopped["timerDelays"])
    assert result["storageWrites"] == []
''')
