from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/t14-baseline'
out.mkdir(exist_ok=False)
manifest={}
for name in ['decision_dashboard.html','decision_dashboard.js','test_decision_context_readable_ui.py']:
 body=(root/'packages/multi-workers'/name).read_bytes()
 (out/name).write_bytes(body)
 manifest[name]=hashlib.sha256(body).hexdigest()
(out/'hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
