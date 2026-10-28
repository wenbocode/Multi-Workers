from pathlib import Path
import hashlib,json
root=Path(__file__).resolve().parents[3]
p=root/'packages/multi-workers/decision_dashboard.js'
b=p.read_bytes()
assert b.decode('utf-8').encode('utf-8')==b
fixed=b.replace(b'\r\n',b'\n')
assert fixed.decode('utf-8')==b.decode('utf-8').replace('\r\n','\n')
p.write_bytes(fixed)
(root/'.agenticdoc/mw-decision-context/evidence/ui-recovery/newline-recovery.json').write_text(json.dumps({'before_sha256':hashlib.sha256(b).hexdigest(),'after_sha256':hashlib.sha256(fixed).hexdigest(),'crlf_removed':b.count(b'\r\n'),'text_changes':0},indent=2),encoding='utf-8')
