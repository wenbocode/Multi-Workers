"""Independent assigned suite and protected snapshot verification; no product writes."""
import ast
from datetime import datetime,timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
KEY=HERE.parents[2];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';PKG=WT/'packages/multi-workers'
BASE=KEY/'evidence/implementation/s2-r2-pre-dispatch-20261026';WORKER=KEY/'evidence/implementation/dpc-t08-transport/rework-r2'
assert sys.dont_write_bytecode and not (HERE/'check.json').exists()
def sha(data):return hashlib.sha256(data).hexdigest()
def save(name,value):(HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def inventory(root):return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
start=datetime.now(timezone.utc).isoformat();before=inventory(WT);save('before-inventory.json',before)
base=json.loads((BASE/'mirror-inventory.json').read_text(encoding='utf-8'));faces=json.loads((BASE/'check.json').read_text(encoding='utf-8'))['product_paths']
assert set(before)==set(base);net=[p for p in before if before[p]!=base[p]];assert set(net)<=set(faces)
old_evidence=json.loads((BASE/'t08-original-evidence-inventory.json').read_text(encoding='utf-8'));oldroot=WORKER.parent
assert all(sha((oldroot/p).read_bytes())==s for p,s in old_evidence.items())
worker_evidence=inventory(WORKER);save('worker-evidence-inventory.json',worker_evidence)
products=[];live_before={}
expected={'decision.py':'ef9c2c68eee18bb93ad716c76c7b146279ac5f111c9f626c68a01d1c35ed691e','decision_backends.py':'a13a8597bba7abe796022148bd50d02b26fc6a85e1d7d3b1af9f5129f0a3e22b','test_dp_consolidation_materials.py':'b404fc0a9e94b35a198051ed43a8f755d6a61ab5c36b2d43919695cab6b45a1b'}
for name,s in expected.items():
    rel='packages/multi-workers/'+name;data=(PKG/name).read_bytes();old=(BASE/'before-bytes'/rel).read_bytes()
    assert sha(data)==s and (WORKER/'before-bytes'/rel).read_bytes()==old
    if name=='decision_backends.py':assert data==old
    live=ROOT/rel;live_before[rel]=sha(live.read_bytes()) if live.exists() else None
    if live.exists():assert not os.path.samefile(live,PKG/name)
    for label,value in [('before-bytes',old),('after-bytes',data)]:
        dest=HERE/label/name;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(value)
    diff=''.join(difflib.unified_diff(old.decode('utf-8').splitlines(keepends=True),data.decode('utf-8').splitlines(keepends=True),fromfile='before/'+rel,tofile='after/'+rel)).encode('utf-8');(HERE/(name+'.diff')).write_bytes(diff)
    products.append({'path':rel,'before_sha256':sha(old),'after_sha256':s,'bytes':len(data),'lf':data.count(b'\n'),'crlf':data.count(b'\r\n'),'pm_diff_sha256':sha(diff)})
def tests(path):
    return {n.name:ast.dump(n,include_attributes=False) for n in ast.parse(path.read_text(encoding='utf-8')).body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
a=tests(BASE/'before-bytes/packages/multi-workers/test_dp_consolidation_materials.py');b=tests(PKG/'test_dp_consolidation_materials.py');assert all(b.get(k)==v for k,v in a.items())
oldtree=ast.parse((BASE/'before-bytes/packages/multi-workers/decision.py').read_text(encoding='utf-8'));newtree=ast.parse((PKG/'decision.py').read_text(encoding='utf-8'))
def constants(tree):
    return {t.id:ast.dump(n.value,include_attributes=False) for n in tree.body if isinstance(n,ast.Assign) for t in n.targets if isinstance(t,ast.Name) and t.id in ('REASON_CODES','_EVIDENCE_FIELDS','_PREPARED_RESULT_FIELDS')}
assert constants(oldtree)==constants(newtree) and len(constants(newtree))==3
# Only request_prepared is changed in the transport class; all other class methods preserve AST.
def methods(tree):
    cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='DecisionClient')
    return {n.name:ast.dump(n,include_attributes=False) for n in cls.body if isinstance(n,ast.FunctionDef)}
x=methods(oldtree);y=methods(newtree);assert set(x)==set(y) and [k for k in x if x[k]!=y[k]]==['request_prepared']
env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT') if k in os.environ}
for name in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR','APPDATA','LOCALAPPDATA','PROJECT_ROOT'):
    p=HERE/'fixture'/name.lower();p.mkdir(parents=True,exist_ok=True);env[name]=str(p)
env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONNOUSERSITE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'})
commands=[]
for label,args in [('pm-bootstrap',[str(HERE/'bootstrap.py'),'tests']),('pm-literal',['-m','pytest','-p','no:cacheprovider','-q','test_dp_consolidation_materials.py']),('pm-probe',[str(HERE/'bootstrap.py'),'probes'])]:
    argv=[sys.executable,'-B',*args];r=subprocess.run(argv,cwd=PKG,env=env,capture_output=True)
    (HERE/(label+'.stdout')).write_bytes(r.stdout);(HERE/(label+'.stderr')).write_bytes(r.stderr)
    commands.append({'label':label,'argv':argv,'rc':r.returncode});save('commands.json',commands)
    print(label,'rc=',r.returncode);print(r.stdout.decode('utf-8'));print(r.stderr.decode('utf-8'));assert r.returncode==0
    if label!='pm-probe':assert b'110 passed' in r.stdout
probe=json.loads((HERE/'probe.json').read_text(encoding='utf-8'));assert len(probe['results'])==39
after=inventory(WT);save('after-inventory.json',after);assert before==after and worker_evidence==inventory(WORKER)
assert all(sha((oldroot/p).read_bytes())==s for p,s in old_evidence.items())
pyc={p:s for p,s in after.items() if p.endswith('.pyc')};assert len(pyc)==14 and all(base[p]==s for p,s in pyc.items())
assert all((sha((ROOT/p).read_bytes()) if (ROOT/p).exists() else None)==s for p,s in live_before.items())
result={'started_at':start,'observed_at':datetime.now(timezone.utc).isoformat(),'products':products,'assigned_passed':110,'assigned_rc':[0,0],'independently_asserted_fixture_count':39,'old_test_functions_ast_preserved':len(a),'new_test_functions':sorted(set(b)-set(a)),'frozen_constants_ast_unchanged':True,'backend_bytes_unchanged':True,'only_changed_client_method':'request_prepared','mirror_files':len(after),'verification_net_changes':[],'frontier_allowed_net_changes':net,'original_worker_evidence_preserved':len(old_evidence),'r2_evidence_files_unchanged':len(worker_evidence),'pyc_preserved':14,'relevant_live_paths_unchanged':live_before,'local_rework_boundary_verified':True,'semantic_handoff_verified':False,'worker_actual_status':'needs-clarification','worker_actual_exit_code':2,'runtime_ledger_recovery_resolved':False,'full_live_transient_or_exclusive_authorship_audit':False,'full_l2_qg_signoff_stage_close':False}
save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
