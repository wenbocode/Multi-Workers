"""Targeted byte replacements: preserve mw.py's CRLF and every unrelated byte."""
from pathlib import Path
root=Path(__file__).resolve().parents[3]
path=root/'packages/multi-workers/mw.py'
body=path.read_bytes()
edits=[
('        "event_id",\n    }\n)\n\n\ndef _decide_lifecycle', '        "event_id",\n        "task_after",\n    }\n)\n\n\ndef _decide_lifecycle'),
('    decision_id = payload["decision_id"]\n    dp = payload["dp"]\n\n    cfg = _decide_config_snapshot(project_dir)', '    decision_id = payload["decision_id"]\n    dp = payload["dp"]\n    if payload.get("task_after") is not None and (stage not in ("executed", "settled") or meta.task_key is None):\n        _decide_print({"status": "refused", "recorded": False, "error_class": "input", "error": "task_after requires an associated task and executed/settled stage"}, as_json)\n        return 2\n\n    cfg = _decide_config_snapshot(project_dir)'),
('                    action=payload.get("action"),\n                    result=payload.get("result"),\n                    **common,', '                    action=payload.get("action"),\n                    result=payload.get("result"),\n                    task_after=payload.get("task_after"),\n                    **common,'),
('                    outcome=payload.get("outcome"),\n                    **common,', '                    outcome=payload.get("outcome"),\n                    task_after=payload.get("task_after"),\n                    **common,'),
]
for old,new in edits:
 a=old.replace('\n','\r\n').encode('utf-8');b=new.replace('\n','\r\n').encode('utf-8')
 assert body.count(a)==1,old
 body=body.replace(a,b,1)
assert body.count(b'\n')==body.count(b'\r\n')
path.write_bytes(body)
