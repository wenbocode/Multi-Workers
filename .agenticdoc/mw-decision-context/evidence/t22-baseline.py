from pathlib import Path
import hashlib,json,subprocess
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/t22-baseline'
out.mkdir(exist_ok=True)
paths=['packages/multi-workers/'+name for name in ('decision_lifecycle.py','decision_wire.py','decision_history.py','mw.py','decision_dashboard.js')]+['packages/coding-agent/src/extensions/agent-team-loop/pm/'+name for name in ('triage-client.ts','decision-tool.ts','ui-bridge.ts')]
manifest=[]
for relative in paths:
 body=(root/relative).read_bytes();dest=out/relative;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(body)
 manifest.append(dict(path=relative,bytes=len(body),sha256=hashlib.sha256(body).hexdigest(),crlf=body.count(b'\r\n')))
(out/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
(out/'status.txt').write_bytes(subprocess.run(['git','status','--short'],cwd=root,capture_output=True,check=True).stdout)
print(json.dumps(manifest,indent=2))
