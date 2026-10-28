from pathlib import Path
import difflib,hashlib,json,sys
root=Path(__file__).resolve().parents[3]
out=root/'.agenticdoc/mw-decision-context/evidence/t22-check'
manifest=json.loads((out/'source-hashes.json').read_text(encoding='utf-8'))
meta=json.loads((out/'metadata.json').read_text(encoding='utf-8'))
allowed={ 'packages/coding-agent/src/extensions/agent-team-loop/pm/'+name for name in ('decision-task-state.ts','decision-tool.ts','triage-client.ts','ui-bridge.ts') }|{'packages/coding-agent/test/suite/decision-task-state.test.ts'}
assert set(meta['formatter_changes'])==allowed
prepared=[]
for relative in sorted(allowed):
 path=root/relative;old=path.read_bytes();new=(out/'formatter-output'/relative).read_bytes()
 assert hashlib.sha256(old).hexdigest()==manifest[relative],relative
 diff=''.join(difflib.unified_diff(old.decode('utf-8').splitlines(keepends=True),new.decode('utf-8').splitlines(keepends=True),fromfile=relative,tofile=relative+'.formatted',n=2))
 (out/(Path(relative).name+'.format.diff')).write_text(diff,encoding='utf-8',newline='')
 print(relative,len(old),len(new))
 if Path(relative).name not in ('decision-task-state.ts','decision-task-state.test.ts'):print(diff)
 prepared.append((path,new))
if '--apply' in sys.argv:
 for path,body in prepared:path.write_bytes(body)
 print('Applied only the five reviewed T22-owned formatter diffs. No external diagnostics fixed.')
