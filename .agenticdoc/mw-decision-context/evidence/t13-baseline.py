from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/t13-baseline'
out.mkdir(exist_ok=False)
paths=['decision_dashboard.html','decision_dashboard.js','decision_dashboard.css','test_decision_context_readable_ui.py','test_decision_dashboard_assets.py','test_decision_dashboard_playground.py']
manifest={}
for name in paths:
 body=(root/'packages/multi-workers'/name).read_bytes()
 (out/name).write_bytes(body)
 manifest[name]=hashlib.sha256(body).hexdigest()
(out/'hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(out/'status.txt').write_bytes(subprocess.run(['git','status','--short'],cwd=root,capture_output=True,check=True).stdout)
