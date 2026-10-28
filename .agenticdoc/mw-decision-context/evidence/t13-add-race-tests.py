from pathlib import Path
p=Path(__file__).resolve().parents[3]/'packages/multi-workers/test_decision_context_readable_ui.py'
with p.open('a',encoding='utf-8',newline='') as f:
 f.write('''

@pytest.mark.parametrize("stage", ["history", "detail"])
def test_late_poll_does_not_overwrite_final_result_or_overlap(tmp_path, stage):
    scenario = _interaction_scenario()
    terminal = dict(scenario["submission"]["body"]["data"], record_status="recorded")
    running = dict(terminal, state="running")
    scenario["submit"] = {"status": 200, "body": _envelope(terminal), "defer": "submit"}
    if stage == "history":
        scenario["testHistory"] = [scenario["testHistory"],
            {"status": 200, "body": _envelope({"records": [], "total": 0}), "defer": "poll"},
            _interaction_scenario()["testHistory"]]
    else:
        scenario["submission"] = [scenario["submission"],
            {"status": 200, "body": _envelope(running), "defer": "poll"},
            {"status": 200, "body": _envelope(terminal)}]
    scenario["steps"] = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-scaffold"},
        {"type": "click", "target": "#pg-submit"},
        {"type": "tick", "snapshot": "held"},
        {"type": "tick", "snapshot": "no-overlap"},
        {"type": "release", "id": "submit", "snapshot": "finished"},
        {"type": "release", "id": "poll", "snapshot": "late"},
    ]
    result = _run_dom(tmp_path, scenario)
    held = _snapshot(result, "held")
    assert held["activeTimers"] == 0
    assert held["fetchCalls"] == _snapshot(result, "no-overlap")["fetchCalls"]
    finished, late = _snapshot(result, "finished"), _snapshot(result, "late")
    assert late["fetchCalls"] == finished["fetchCalls"]
    assert late["pgStatus"] == finished["pgStatus"] and "succeeded" in late["pgStatus"]
    assert late["pgHistory"] == finished["pgHistory"]
    assert late["pgGraph"] == finished["pgGraph"]
    assert late["activeTimers"] == 0
    assert sum(c["url"] == "/api/test/submit" for c in result["fetchCalls"]) == 1


def test_poll_read_failure_retries_reads_only_and_submit_failure_is_honest(tmp_path):
    scenario = _interaction_scenario()
    scenario["submit"] = {"status": 503, "body": {"ok": False, "error": {"code": "transport", "message": "unreadable"}}, "defer": "submit"}
    scenario["testHistory"] = [scenario["testHistory"],
        {"status": 503, "body": {"ok": False, "error": {"code": "offline", "message": "fixture"}}},
        _interaction_scenario()["testHistory"], _interaction_scenario()["testHistory"]]
    scenario["submission"] = [scenario["submission"],
        {"status": 200, "body": _envelope({"dp": "dp1-dispatch-type", "state": "running", "attempts": []})}]
    scenario["steps"] = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-scaffold"},
        {"type": "click", "target": "#pg-submit"},
        {"type": "tick", "snapshot": "failed-read"},
        {"type": "tick", "snapshot": "running"},
        {"type": "release", "id": "submit", "snapshot": "failure"},
        {"type": "tick", "snapshot": "stopped"},
    ]
    result = _run_dom(tmp_path, scenario)
    assert "状态读取失败" in _snapshot(result, "failed-read")["pgStatus"]
    assert _snapshot(result, "failed-read")["activeTimers"] == 1
    failed = _snapshot(result, "failure")
    assert "失败" in failed["pgStatus"] and "未知" in failed["bodyText"]
    assert not failed["submitDisabled"] and failed["activeTimers"] == 0
    assert failed["fetchCalls"] == _snapshot(result, "stopped")["fetchCalls"]
    assert sum(c["url"] == "/api/test/submit" for c in result["fetchCalls"]) == 1
''')
