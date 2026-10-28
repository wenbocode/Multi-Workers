from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/ui-recovery'
out.mkdir(exist_ok=True)
face=['decision_dashboard.html','decision_dashboard.js','decision_dashboard.css','test_decision_context_workbench.py','test_decision_dashboard_assets.py','test_decision_dashboard_contracts.py','test_decision_context_readable_ui.py']
manifest={}
for name in face:
 p=root/'packages/multi-workers'/name
 b=p.read_bytes(); (out/name).write_bytes(b)
 manifest[name]={'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
(out/'baseline.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
for cmd,name in [(['git','status','--short'],'status.txt'),(['git','diff','--binary'],'diff.txt')]:
 r=subprocess.run(cmd,cwd=root,capture_output=True); (out/name).write_bytes(r.stdout)
evidence=root/'.agenticdoc/mw-decision-context/workers/dc-t11-readable-ui/evidence'
for name in ['green7-existing.log','green7-readable-ui.log','red-readable-ui.log']:
 b=(evidence/name).read_bytes()
 text=b.decode('utf-16') if b[:2] in (b'\xff\xfe',b'\xfe\xff') else b.decode('utf-8',errors='replace')
 (out/name).write_text(text,encoding='utf-8')
 print(name, len(text), text[-6000:] if name=='green7-existing.log' else text[-700:])
