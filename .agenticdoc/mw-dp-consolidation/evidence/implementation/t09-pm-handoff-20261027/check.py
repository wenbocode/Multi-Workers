"""PM independent T09 evidence accounting/tests/negative probes; preserve all outcomes."""
from datetime import datetime,timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';PKG=WT/'packages/multi-workers';WORKER=KEY/'evidence/implementation/dpc-t09-books';BASE=KEY/'evidence/implementation/t09-pre-dispatch-20261027'
assert not (HERE/'check.json').exists()
def digest(data):return hashlib.sha256(data).hexdigest()
def save(name,value):(HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def inventory(root):return {p.relative_to(root).as_posix():digest(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
started=datetime.now(timezone.utc).isoformat();mirror=inventory(WT);original=json.loads((BASE/'mirror-inventory.json').read_text(encoding='utf-8'));paths=['packages/multi-workers/decision_book.py','packages/multi-workers/test_decision_context_contract.py']
assert set(mirror)==set(original) and len(mirror)==1883
changed=sorted(p for p in mirror if mirror[p]!=original[p]);assert changed==sorted(paths)
worker_inventory=inventory(WORKER);save('worker-evidence-inventory.json',worker_inventory)
history=inventory(KEY/'workers/dpc-t09-books');save('worker-history-inventory.json',history)
records=json.loads((WORKER/'after-bytes.json').read_text(encoding='utf-8'))['files'];products=[]
for rel in paths:
    data=(WT/rel).read_bytes();before=(BASE/'before-bytes'/rel).read_bytes();record=next(row for row in records if row['relpath']==rel)
    assert digest(data)==record['sha256'] and len(data)==record['bytes'];assert data==(WORKER/'after-bytes'/rel).read_bytes();assert before==(WORKER/'before-bytes'/rel).read_bytes();assert before==(ROOT/rel).read_bytes()
    for label,b in (('before-bytes',before),('after-bytes',data)):
        dest=HERE/label/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
    diff=''.join(difflib.unified_diff(before.decode('utf-8').splitlines(keepends=True),data.decode('utf-8').splitlines(keepends=True),fromfile='before/'+rel,tofile='after/'+rel))
    (HERE/(Path(rel).name+'.diff')).write_text(diff,encoding='utf-8',newline='\n')
    worker_diff=(WORKER/'diffs'/(Path(rel).name+'.diff')).read_bytes();assert worker_diff.decode('utf-8').replace('\r\n','\n')==diff
    products.append({'path':rel,'before_sha256':digest(before),'after_sha256':digest(data),'bytes':len(data),'lf':data.count(b'\n'),'crlf':data.count(b'\r\n'),'diff_hunks':sum(line.startswith('@@') for line in diff.splitlines()),'diff_bytes':len(diff.encode('utf-8')),'worker_diff_raw_sha256':digest(worker_diff)})
save('mirror-before.json',mirror)
env={name:os.environ[name] for name in ('PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','SYSTEMDRIVE') if name in os.environ}
for name in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR','APPDATA','LOCALAPPDATA','PROJECT_ROOT'):
    p=HERE/'fixture'/name.lower();p.mkdir(parents=True,exist_ok=True);env[name]=str(p)
env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONNOUSERSITE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'})
commands=[]
for label,mode,target in (('assigned-1','tests',HERE/'fixture/basetemp-1'),('assigned-2','tests',HERE/'fixture/basetemp-2'),('independent-negatives','probe',HERE/'fixture/probe-project')):
    argv=[sys.executable,'-B',str(HERE/'bootstrap.py'),mode,str(target)]
    run=subprocess.run(argv,cwd=PKG,env=env,capture_output=True)
    (HERE/(label+'.stdout')).write_bytes(run.stdout);(HERE/(label+'.stderr')).write_bytes(run.stderr)
    commands.append({'label':label,'argv':argv,'cwd':str(PKG),'rc':run.returncode,'stdout':label+'.stdout','stderr':label+'.stderr'})
    print(label,'rc=',run.returncode);print(run.stdout.decode('utf-8'));print(run.stderr.decode('utf-8'))
    if mode=='tests':assert run.returncode==0 and b'109 passed' in run.stdout
probe=json.loads((HERE/'probe.json').read_text(encoding='utf-8'))
assert mirror==inventory(WT);assert worker_inventory==inventory(WORKER);assert history==inventory(KEY/'workers/dpc-t09-books')
assert all((ROOT/p).read_bytes()==(BASE/'before-bytes'/p).read_bytes() for p in paths)
pyc={p:s for p,s in mirror.items() if p.endswith('.pyc')};assert pyc==json.loads((BASE/'pyc-preserved.json').read_text(encoding='utf-8'));assert len(pyc)==14
result={'source':'agent-report','started_at':started,'observed_at':datetime.now(timezone.utc).isoformat(),'assigned_passed':109,'assigned_runs':2,'products':products,'commands':commands,'mirror_files':len(mirror),'only_original_task_product_paths_changed':changed,'verification_net_changes':[],'worker_history_evidence_unchanged':True,'relevant_live_unchanged':True,'pyc_preserved':14,'full_after_source_read_by_PM':True,'probe_passed':probe['passed'],'probe_failed':probe['failed'],'semantic_handoff_verified':probe['failed']==0,'whole_live_transient_or_exclusive_authorship_audit':False}
save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(1 if probe['failed'] else 0)
