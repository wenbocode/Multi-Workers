from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/t16-baseline'
out.mkdir(exist_ok=False)
manifest={}
for name in ['decision_dashboard.js','test_decision_context_readable_ui.py']:
 b=(root/'packages/multi-workers'/name).read_bytes(); (out/name).write_bytes(b); manifest[name]=hashlib.sha256(b).hexdigest()
(out/'hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
p=root/'packages/multi-workers/test_decision_context_readable_ui.py'
with p.open('a',encoding='utf-8',newline='') as f:
 f.write('''

@pytest.mark.parametrize("dp", list(CASES))
def test_scaffold_prefills_loaded_native_case_without_request(tmp_path, dp):
    cases = _published_cases_payload()
    case = next(c for c in cases["body"]["data"]["cases"] if c["dp"] == dp)
    before = {p: p.read_bytes() for p in CASES_DIR.glob("*.json")}
    scenario = _interaction_scenario()
    scenario["cases"] = cases
    scenario["steps"] = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-cases-load"},
        {"type": "setValue", "target": "#case-select", "value": dp},
        {"type": "click", "target": "#pg-case-open", "snapshot": "opened"},
        {"type": "setValue", "target": "#material-editor", "value": "{}"},
        {"type": "dispatch", "target": "#material-editor", "event": {"type": "input"}},
        {"type": "click", "target": "#pg-scaffold", "snapshot": "generated"},
        {"type": "click", "target": "#pg-questions-reset", "snapshot": "reset"},
    ]
    result = _run_dom(tmp_path, scenario)
    opened, generated = _snapshot(result, "opened"), _snapshot(result, "generated")
    assert json.loads(generated["editorValue"]) == case["book"]
    assert json.loads(generated["materialValue"]) == case["book"]["state"]
    assert generated["questions"] == opened["questions"]
    assert _snapshot(result, "reset")["questions"] == opened["questions"]
    assert "case" in generated["pgStatus"] and "未调用模型" in generated["pgStatus"]
    assert generated["fetchCalls"] == opened["fetchCalls"], "loaded case generation is local"
    assert before == {p: p.read_bytes() for p in before}


@pytest.mark.parametrize("loaded", [False, True])
def test_scaffold_without_matching_loaded_case_uses_selected_dp_server_scaffold(tmp_path, loaded):
    scenario = _interaction_scenario()
    scenario["cases"] = _published_cases_payload()
    empty = {"schema_version": 2, "decision_point": "dp2-checkpoint-split", "state": {"task_goal": "<string: required>"}, "notes": {}}
    scenario["scaffold"] = {"status": 200, "body": _envelope({"book": empty})}
    scenario["steps"] = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-cases-load"},
        {"type": "setValue", "target": "#case-select", "value": "dp1-dispatch-type"},
    ]
    if loaded:
        scenario["steps"].append({"type": "click", "target": "#pg-case-open"})
    scenario["steps"] += [
        {"type": "setValue", "target": "#dp-select", "value": "dp2-checkpoint-split"},
        {"type": "dispatch", "target": "#dp-select", "event": {"type": "change"}},
        {"type": "click", "target": "#pg-scaffold", "snapshot": "generated"},
    ]
    result = _run_dom(tmp_path, scenario)
    assert json.loads(_snapshot(result, "generated")["editorValue"]) == empty
    calls = [c for c in result["fetchCalls"] if c["url"] == "/api/test/scaffold"]
    assert len(calls) == 1 and json.loads(calls[0]["body"]) == {"dp": "dp2-checkpoint-split"}
    assert not any(c["url"] == "/api/test/submit" for c in result["fetchCalls"])
''')
