from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/t20-startup-baseline'
out.mkdir(exist_ok=False)
manifest={}
for name in ('decision_monitor.py','test_decision_dashboard_playground.py'):
 b=(root/'packages/multi-workers'/name).read_bytes()
 (out/name).write_bytes(b)
 manifest[name]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'crlf':b.count(b'\r\n')}
(out/'hashes.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
