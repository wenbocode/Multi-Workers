"""Fresh source-only T09 frontier baseline and T08 handoff recheck; no product writes."""
from datetime import datetime,timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';PKG=WT/'packages/multi-workers'
T08=KEY/'evidence/implementation/t08-r2-pm-handoff-20261026'
assert not (HERE/'check.json').exists()
def sha(data):return hashlib.sha256(data).hexdigest()
def save(name,value):(HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def inventory(root):return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
def keep(label,rel,data):
    dest=HERE/label/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
started=datetime.now(timezone.utc).isoformat();before=inventory(WT)
verified=json.loads((T08/'after-inventory.json').read_text(encoding='utf-8'));assert before==verified and len(before)==1883
save('mirror-inventory.json',before)
dag=json.loads((KEY/'implementation-isolated-dag.json').read_text(encoding='utf-8'));tasks={t['id']:t for t in dag['tasks']};task=tasks['T09'];assert len(tasks)==36 and task['status']=='not-queued' and task['deps']==['T03','T04','T08']
assert tasks['T03']['semantic_handoff_verified'] and tasks['T04']['semantic_handoff_verified']
assert tasks['T10']['deps']==['T03','T04','T09']
paths=['packages/multi-workers/decision_book.py','packages/multi-workers/test_decision_context_contract.py']
assert task['source_product_write_face']==paths
card=KEY/task['card'];cardbytes=card.read_bytes();keep('original-card',card.name,cardbytes)
files=[];live={}
for rel in paths:
    data=(WT/rel).read_bytes();assert data==(KEY/'evidence/implementation/s2-r2-pre-dispatch-20261026/before-bytes'/rel).read_bytes() if (KEY/'evidence/implementation/s2-r2-pre-dispatch-20261026/before-bytes'/rel).exists() else before[rel]==verified[rel]
    keep('before-bytes',rel,data)
    lp=ROOT/rel;lv=lp.read_bytes() if lp.exists() else None;live[rel]=sha(lv) if lv is not None else None
    if lv is not None:
        assert not os.path.samefile(WT/rel,lp);keep('live-before-bytes',rel,lv)
    diff=''.join(difflib.unified_diff((lv or b'').decode('utf-8').splitlines(keepends=True),data.decode('utf-8').splitlines(keepends=True),fromfile='live/'+rel,tofile='isolated/'+rel)).encode('utf-8');keep('vs-live-diff',rel+'.diff',diff)
    files.append({'path':rel,'sha256':sha(data),'bytes':len(data),'lf':data.count(b'\n'),'crlf':data.count(b'\r\n'),'live_sha256':live[rel],'source_independent':True})
check=json.loads((T08/'check.json').read_text(encoding='utf-8'))
assert check['local_rework_boundary_verified'] and check['assigned_passed']==110
for product in check['products']:assert before[product['path']]==product['after_sha256']
protected_runs={}
for name in ('dpc-t06-validity-r2','dpc-t07-policy-r2','dpc-t08-transport-r2'):
    root=KEY/'workers'/name;protected_runs[name]=inventory(root);save(name+'-worker-history.json',protected_runs[name])
t08worker=KEY/'evidence/implementation/dpc-t08-transport';worker_history=inventory(t08worker);save('t08-evidence-inventory.json',worker_history)
env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT') if k in os.environ}
for name in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR','APPDATA','LOCALAPPDATA','PROJECT_ROOT'):
    p=HERE/'fixture'/name.lower();p.mkdir(parents=True,exist_ok=True);env[name]=str(p)
env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONNOUSERSITE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'})
argv=[sys.executable,'-B',str(T08/'bootstrap.py'),'tests'];r=subprocess.run(argv,cwd=PKG,env=env,capture_output=True)
(HERE/'t08-green.stdout').write_bytes(r.stdout);(HERE/'t08-green.stderr').write_bytes(r.stderr)
print('T08 assigned fresh rc=',r.returncode);print(r.stdout.decode('utf-8'));print(r.stderr.decode('utf-8'));assert r.returncode==0 and b'110 passed' in r.stdout
# Fresh same one-variable parser reproduction, new output only; original input/records never edited.
probe=(T08/'ledger-probe2.mjs').read_text(encoding='utf-8').replace("'ledger-probe2.json'","'t08-ledger-recheck.json'")
(HERE/'ledger-probe.mjs').write_text(probe,encoding='utf-8',newline='\n')
nodeargv=['node',str(HERE/'ledger-probe.mjs')];nr=subprocess.run(nodeargv,cwd=ROOT,env=env,capture_output=True)
(HERE/'ledger.stdout').write_bytes(nr.stdout);(HERE/'ledger.stderr').write_bytes(nr.stderr)
print('ledger recheck rc=',nr.returncode);print(nr.stdout.decode('utf-8'));print(nr.stderr.decode('utf-8'));assert nr.returncode==0
ledger=json.loads((HERE/'t08-ledger-recheck.json').read_text(encoding='utf-8'));assert ledger['original']['extra']==['packages/multi-workers'] and ledger['synthetic_header_only']['extra']==[] and ledger['evidence_report_ledger']['extra']==[]
after=inventory(WT);assert before==after
assert all(protected_runs[name]==inventory(KEY/'workers'/name) for name in protected_runs)
assert worker_history==inventory(t08worker)
assert all((sha((ROOT/p).read_bytes()) if (ROOT/p).exists() else None)==s for p,s in live.items())
pyc={p:s for p,s in after.items() if p.endswith('.pyc')};assert len(pyc)==14;save('pyc-preserved.json',pyc)
result={'started_at':started,'observed_at':datetime.now(timezone.utc).isoformat(),'source':'agent-report','card':task['card'],'card_sha256':sha(cardbytes),'logical_task':'T09','product_write_face':paths,'files':files,'mirror_files':len(after),'mirror_net_changes':[],'t08_products_match_independent_verification':True,'t08_fresh_assigned_passed':110,'t08_fresh_rc':r.returncode,'ledger_same_header_false_positive_reproduced':True,'ledger_runtime_version_verified':False,'original_runs_evidence_unchanged':True,'pyc_preserved':14,'relevant_live_baselines_unchanged':True,'whole_live_transient_or_exclusive_authorship_audit':False,'remaining_t08_process_status':'needs-clarification/exit2 preserved','disposition':'evidence/implementation/t08-r2-pm-handoff-20261026/pm-disposition-20261027.md','commands':[{'argv':argv,'rc':r.returncode},{'argv':nodeargv,'rc':nr.returncode}],'dispatch_done':False,'product_tests_for_T09_run':False}
save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
