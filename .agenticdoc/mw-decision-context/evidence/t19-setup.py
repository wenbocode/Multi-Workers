from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/t19-baseline';out.mkdir(exist_ok=False)
manifest={}
for name in ['decision_dashboard.js','test_decision_context_readable_ui.py','test_decision_dashboard_playground.py']:
 b=(root/'packages/multi-workers'/name).read_bytes();(out/name).write_bytes(b);manifest[name]=hashlib.sha256(b).hexdigest()
(out/'hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
p=root/'packages/multi-workers/test_decision_context_readable_ui.py'
with p.open('a',encoding='utf-8',newline='') as f:
 f.write('''

@pytest.mark.parametrize("kind,expected", [
    ("low", "模型已返回，结果未采纳"), ("low-unknown", "本次置信度或阈值未记录"),
    ("off", "决策服务不可用"), ("duplicate", "重复提交"), ("busy", "已有观察提交进行中"),
    ("unknown", "调用是否完成未知"), ("refused", "提交被拒绝"),
])
def test_all_submit_outcomes_have_plain_feedback_not_technical_logs(tmp_path, kind, expected):
    scenario = _interaction_scenario()
    record = dict(scenario["submission"]["body"]["data"], state="failed", record_status="recorded", duplicate=False,
                  outcome={"status": "escalated", "escalated_reason": "low-confidence", "detail": "confidence=0.56 < min_confidence=0.7", "response": {"available": True}})
    status = 200
    if kind == "low-unknown": record["outcome"]["detail"] = "no decision-specific numbers recorded"
    elif kind == "off": record["outcome"] = {"status": "unavailable", "response": {"available": False}}
    elif kind == "duplicate": record.update(state="succeeded", duplicate=True)
    elif kind == "busy":
        record.update(busy=True, zero_call=True)
        status = 409
    elif kind == "refused":
        record.update(state="rejected", zero_call=True, decision_ran=False, issues=[{"code": "book-placeholder", "path": "state.task_goal", "detail": "请填写真实原文"}])
        record["outcome"] = {}
    body = _envelope(record)
    if kind == "busy": body.update(ok=False, error={"code": "busy", "message": "already running"})
    if kind == "unknown": body = {"ok": False, "error": {"code": "unreadable", "message": "response unreadable"}}
    scenario["submit"] = {"status": status, "body": body}
    scenario["steps"] = [{"type": "click", "target": "#tab-playground"}, {"type": "click", "target": "#pg-scaffold"}, {"type": "click", "target": "#pg-submit", "snapshot": "done"}]
    result = _run_dom(tmp_path, scenario)
    snap = _snapshot(result, "done")
    assert expected in snap["submitText"]
    for debug in ("HTTP", "state=", "submission_id", "call_id", "book_ref", "state_digest", "projection_sha256", "采纳判定与动作预览", "拒绝/问题项：无"):
        assert debug not in snap["submitText"], (debug, snap["submitText"])
    if kind == "low":
        assert "0.56" in snap["submitText"] and "0.7" in snap["submitText"]
        assert "人工判断" in snap["submitText"] and "接口调用失败" not in snap["submitText"]
    if kind == "low-unknown": assert "0.7" not in snap["submitText"]
    if kind == "refused": assert "state.task_goal" in snap["submitText"] and "真实原文" in snap["submitText"]
    assert "未自动重试" in snap["submitText"] or "未新增调用" in snap["submitText"] or "未发起模型调用" in snap["submitText"]
    assert len([c for c in result["fetchCalls"] if c["url"] == "/api/test/submit"]) == 1
''')
