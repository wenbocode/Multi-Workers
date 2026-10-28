"""PM serial targeted verification; no provider, service, build or install."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess
import tempfile

root = Path(__file__).resolve().parents[3]
out = root / '.agenticdoc/mw-decision-context/evidence/pm-stable-verify'
out.mkdir(exist_ok=True)

def now():
    return datetime.now(timezone.utc).isoformat()

# Freeze status/diff as raw subprocess bytes, not PowerShell recoding.
for name, argv in [('baseline-status', ['git','status','--porcelain']), ('baseline-diff',['git','diff','--binary'])]:
    result = subprocess.run(argv,cwd=root,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    (out/(name+'.txt')).write_bytes(result.stdout)
    assert result.returncode == 0
hash_rows = []
manifest = root / '.agenticdoc/mw-decision-context/workers/dc-t08-closure-fixes-r2/evidence/final-sha256.txt'
for line in manifest.read_text(encoding='utf-8-sig').splitlines():
    expected, size, name = line.split(maxsplit=2)
    data = (root/name).read_bytes()
    hash_rows.append({'path':name,'matches':hashlib.sha256(data).hexdigest()==expected and len(data)==int(size)})
(out/'closure-hashes.json').write_text(json.dumps(hash_rows,indent=2),encoding='utf-8')
assert all(row['matches'] for row in hash_rows)
ts = ['decision-context-integration','decision-context-pm-producers','decision-context-agent-materials','triage-client-state','triage-dispatch','decision-association','dp2-narrow','dp3-answer','decision-tool']
py = ['test_decision_context_integration','test_decision_context_contract','test_decision_context_lifecycle','test_decision_context_history','test_decision_context_signoff_cli','test_decision_context_workbench','test_decide_registry_contract','test_decision_book','test_decision_input_contract_migration','test_decision_context','test_decision_dashboard_contracts','test_decision_dashboard_assets','test_decision_monitor','test_decision_dashboard_playground','test_decide_signoff','test_decide_sign_auto','test_decide_run_authority','test_decision_dp25_empty_value','test_decision_required_refusal','test_decision_observation']
commands = [(name,root/'packages/coding-agent',['node','../../node_modules/vitest/dist/cli.js','--run',f'test/suite/{name}.test.ts','--reporter=verbose']) for name in ts]
commands += [(name,root/'packages/multi-workers',['python','-X','utf8','-m','pytest',name+'.py','-q']) for name in py]
rows = []
with tempfile.TemporaryDirectory(prefix='dc-pm-verify-') as temp:
    env = {key:value for key,value in os.environ.items() if not key.upper().endswith(('_KEY','_TOKEN','_SECRET','_PASSWORD')) and key not in ('PI_WORKER_TASK','PI_SESSION_FILE','PI_SESSION_ID')}
    for key in ('HOME','USERPROFILE','PI_CODING_AGENT_DIR'):
        env[key] = temp
    env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8',NO_COLOR='1',FORCE_COLOR='0')
    for name,cwd,argv in commands:
        start = now()
        result = subprocess.run(argv,cwd=cwd,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=180)
        header = f'UTC_START {start}\nCWD {cwd}\nARGV {json.dumps(argv)}\n--- STDOUT ---\n'.encode()
        data = header+result.stdout+b'\n--- STDERR ---\n'+result.stderr+f'\nEXIT {result.returncode}\nUTC_END {now()}\n'.encode()
        data.decode('utf-8')
        (out/(name+'.log')).write_bytes(data)
        rows.append({'name':name,'exit':result.returncode,'start':start,'end':now(),'log':name+'.log'})
        (out/'summary.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
        print(f'{name}: exit={result.returncode}',flush=True)
raise SystemExit(0 if all(row['exit']==0 for row in rows) else 1)
