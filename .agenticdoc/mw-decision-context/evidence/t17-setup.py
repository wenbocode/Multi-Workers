from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/t17-baseline';out.mkdir(exist_ok=False)
manifest={}
for name in ['decision_dashboard.js','test_decision_context_readable_ui.py','test_decision_dashboard_playground.py']:
 b=(root/'packages/multi-workers'/name).read_bytes();(out/name).write_bytes(b);manifest[name]=hashlib.sha256(b).hexdigest()
(out/'hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
p=root/'packages/multi-workers/test_decision_context_readable_ui.py'
with p.open('a',encoding='utf-8',newline='') as f:
 f.write('''

def test_successful_submit_feedback_omits_logs_but_keeps_detail_and_warnings(tmp_path):
    scenario = _interaction_scenario()
    terminal = dict(scenario["submission"]["body"]["data"], state="succeeded", record_status="recorded", duplicate=False,
                    issues=[{"code": "safe-warning", "path": "projection", "detail": "安全提示保留"}], message="记录提示保留")
    scenario["submit"] = {"status": 200, "body": _envelope(terminal)}
    scenario["steps"] = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-scaffold"},
        {"type": "click", "target": "#pg-submit", "snapshot": "done"},
    ]
    result = _run_dom(tmp_path, scenario)
    snap = _snapshot(result, "done")
    assert "真实模型调用成功" in snap["submitText"]
    assert "未执行任何业务动作" in snap["submitText"]
    assert "安全提示保留" in snap["submitText"] and "记录提示保留" in snap["submitText"]
    for field in ("submission_id", "call_id", "book_ref", "projection_sha256", "当次答案", "动作预览", "拒绝/问题项：无"):
        assert field not in snap["submitText"]
    assert "submission_id" in snap["pgDetailText"] and snap["pgGraph"]["nodes"]
    assert len([c for c in result["fetchCalls"] if c["url"] == "/api/test/submit"]) == 1
''')
