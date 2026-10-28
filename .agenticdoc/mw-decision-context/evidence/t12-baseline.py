from pathlib import Path
import hashlib,json,subprocess
r=Path(__file__).resolve().parents[3]; o=r/'.agenticdoc/mw-decision-context/evidence/t12-baseline';o.mkdir(exist_ok=True)
files=['decision_dashboard.html','decision_dashboard.js','decision_dashboard.css','test_decision_context_readable_ui.py','decision_points.py','test_decision_context_readable_backend.py','test_decision_context_contract.py']
m={}
for name in files:
 p=r/'packages/multi-workers'/name;b=p.read_bytes();(o/name).write_bytes(b);m[name]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
(o/'manifest.json').write_text(json.dumps(m,indent=2),encoding='utf-8')
(o/'git-status.txt').write_bytes(subprocess.run(['git','status','--short'],cwd=r,capture_output=True).stdout)
print('baseline frozen',len(m))
