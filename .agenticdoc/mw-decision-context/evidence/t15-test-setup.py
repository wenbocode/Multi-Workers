from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/t15-baseline'
out.mkdir(exist_ok=False)
manifest={}
for name in ['decision_dashboard.js','decision_dashboard.css','test_decision_context_readable_ui.py']:
 b=(root/'packages/multi-workers'/name).read_bytes(); (out/name).write_bytes(b); manifest[name]=hashlib.sha256(b).hexdigest()
(out/'hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
p=root/'packages/multi-workers/test_decision_context_readable_ui.py'
with p.open('a',encoding='utf-8',newline='') as f:
 f.write('''

def test_failed_validation_items_are_red_and_offer_correct_editor_guidance(tmp_path):
    scenario = _interaction_scenario()
    issues = [
        {"code": "book-placeholder", "path": "state.task_goal", "detail": "unreplaced placeholder"},
        {"code": "book-placeholder", "path": "notes.evidence.task_goal", "detail": "provide path:line or command"},
        {"code": "future-error", "path": "unknown", "detail": "literal <failure>"},
    ]
    scenario["validate"] = {"status": 200, "body": _envelope({"ok": False, "issues": issues})}
    scenario["steps"] = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-scaffold"},
        {"type": "click", "target": "#pg-validate", "snapshot": "failed"},
        {"type": "click", "target": '[data-testid="pg-fix-issue"][data-path="state.task_goal"]', "snapshot": "business"},
        {"type": "click", "target": '[data-testid="pg-fix-issue"][data-path="notes.evidence.task_goal"]', "snapshot": "evidence"},
    ]
    result = _run_dom(tmp_path, scenario)
    failed = _snapshot(result, "failed")
    assert "error" in failed["validateHeadlineClass"]
    assert len(failed["validationRows"]) == 3
    assert all("validation-issue" in r["className"] for r in failed["validationRows"])
    assert "真实原文" in failed["validationRows"][0]["text"]
    assert "path:line" in failed["validationRows"][1]["text"]
    assert "高级" in failed["validationRows"][1]["text"]
    assert "literal <failure>" in failed["validationRows"][2]["text"]
    assert "未识别" in failed["validationRows"][2]["text"]
    assert _snapshot(result, "business")["activeElement"] == "material-editor"
    evidence = _snapshot(result, "evidence")
    assert evidence["activeElement"] == "book-editor" and evidence["advancedOpen"]
    assert evidence["editorValue"] == failed["editorValue"], "guidance never changes material"
    assert len(evidence["fetchCalls"]) == len(failed["fetchCalls"]), "fix link only focuses, no request"
    css = (ASSET_DIR / CSS_NAME).read_text(encoding="utf-8")
    assert re.search(r"\\.validation-issue\\s+td\\s*\\{[^}]*color:\\s*var\\(--error\\)", css)
''')
