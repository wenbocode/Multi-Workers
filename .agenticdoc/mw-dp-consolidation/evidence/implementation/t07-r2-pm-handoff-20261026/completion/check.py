"""Independent assigned suite, original boundaries, immutable evidence and net-scope checks."""
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
KEY=HERE.parents[3];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';PKG=WT/'packages/multi-workers'
BASE=KEY/'evidence/implementation/s2-r2-pre-dispatch-20261026'
WORKER=KEY/'evidence/implementation/dpc-t07-policy/rework-r2'
assert sys.dont_write_bytecode and not (HERE/'check.json').exists()
def sha(data):return hashlib.sha256(data).hexdigest()
def save(name,value):(HERE/name).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
def inventory():return {p.relative_to(WT).as_posix():sha(p.read_bytes()) for p in WT.rglob('*') if p.is_file()}
start=datetime.now(timezone.utc).isoformat();before=inventory();save('before-inventory.json',before)
original=json.loads((BASE/'mirror-inventory.json').read_text(encoding='utf-8'))
faces=json.loads((BASE/'check.json').read_text(encoding='utf-8'))['product_paths']
assert set(before)==set(original)
net=[p for p in before if before[p]!=original[p]];assert set(net)<=set(faces)
old_evidence=json.loads((BASE/'t07-original-evidence-inventory.json').read_text(encoding='utf-8'))
old_root=KEY/'evidence/implementation/dpc-t07-policy'
assert all(sha((old_root/p).read_bytes())==s for p,s in old_evidence.items())
worker_after=json.loads((WORKER/'after.json').read_text(encoding='utf-8'))['products']
products=[]
for name in ('decision_policy.py','test_dp_consolidation_recovery.py'):
    rel='packages/multi-workers/'+name;old=(BASE/'before-bytes'/rel).read_bytes();data=(PKG/name).read_bytes()
    assert (WORKER/'before-bytes'/rel.replace('/','__')).read_bytes()==old
    assert sha(data)==worker_after[rel]['sha256']
    assert not (ROOT/rel).exists()
    for label,bytes_ in [('before-bytes',old),('after-bytes',data)]:
        p=HERE/label/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(bytes_)
    diff=''.join(difflib.unified_diff(old.decode('utf-8').splitlines(keepends=True),data.decode('utf-8').splitlines(keepends=True),fromfile='before/'+rel,tofile='after/'+rel)).encode('utf-8')
    (HERE/(name+'.diff')).write_bytes(diff)
    products.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(data),'bytes':len(data),'lf':data.count(b'\n'),'crlf':data.count(b'\r\n'),'pm_diff_sha256':sha(diff)})
old_tree=ast.parse((BASE/'before-bytes/packages/multi-workers/test_dp_consolidation_recovery.py').read_text(encoding='utf-8'))
new_tree=ast.parse((PKG/'test_dp_consolidation_recovery.py').read_text(encoding='utf-8'))
def tests(tree):return {n.name:ast.dump(n,include_attributes=False) for n in tree.body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')}
a=tests(old_tree);b=tests(new_tree);assert all(b.get(k)==v for k,v in a.items())
red=[]
for label,summary in [('red-01','4 failed, 31 passed'),('red-02','4 failed, 31 passed'),('red-03','1 failed, 34 passed')]:
    text=(WORKER/(label+'.stdout')).read_text(encoding='utf-8');rc=json.loads((WORKER/(label+'.rc.json')).read_text(encoding='utf-8'))
    assert summary in text and 'ERROR collecting' not in text
    red.append({'label':label,'summary':summary,'worker_rc_record':rc})
save('worker-red-observations.json',red)
env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','SYSTEMDRIVE','COMSPEC','PATHEXT') if k in os.environ}
for name in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR','APPDATA','LOCALAPPDATA','PROJECT_ROOT'):
    p=HERE/'fixture'/name.lower();p.mkdir(parents=True,exist_ok=True);env[name]=str(p)
env.update({'DPC_T07_FIXTURE_ROOT':str(HERE/'fixture/projects'),'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONNOUSERSITE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'})
commands=[]
for label,args in [('pm-bootstrap',[str(HERE.parent/'bootstrap.py')]),('pm-literal',['-m','pytest','-p','no:cacheprovider','-q','test_dp_consolidation_recovery.py']),('pm-probe',[str(HERE.parent/'probe.py')])]:
    argv=[sys.executable,'-B',*args];r=subprocess.run(argv,cwd=PKG,env=env,capture_output=True)
    (HERE/(label+'.stdout')).write_bytes(r.stdout);(HERE/(label+'.stderr')).write_bytes(r.stderr)
    commands.append({'label':label,'argv':argv,'rc':r.returncode,'stdout':r.stdout.decode('utf-8'),'stderr':r.stderr.decode('utf-8')});save('commands.json',commands)
    print(label,r.returncode);print(r.stdout.decode('utf-8'));print(r.stderr.decode('utf-8'))
    assert r.returncode==0
    if label!='pm-probe':assert b'35 passed' in r.stdout
probe=json.loads((HERE.parent/'probe.json').read_text(encoding='utf-8'));assert probe['failures']==[]
after=inventory();save('after-inventory.json',after);assert before==after
pyc={p:s for p,s in after.items() if p.endswith('.pyc')};assert len(pyc)==14 and all(original[p]==s for p,s in pyc.items())
assert all(sha((old_root/p).read_bytes())==s for p,s in old_evidence.items())
result={'started_at':start,'observed_at':datetime.now(timezone.utc).isoformat(),'products':products,'assigned_passed':35,'assigned_rc':[0,0],'old_test_functions_ast_preserved':len(a),'new_tests':sorted(set(b)-set(a)),'negative_probes':probe['negative_count'],'positive_controls':probe['control_count'],'probe_failures':[],'mirror_files':len(after),'verification_net_changes':[],'frontier_allowed_net_changes':net,'old_worker_evidence_preserved':len(old_evidence),'pyc_preserved':14,'two_live_product_paths_absent':True,'local_rework_boundary_verified':True,'real_writer_human_h12_lock_effects_not_verified':True,'full_l2_qg_signoff_stage_close':False}
save('check.json',result);print(json.dumps(result,indent=2,ensure_ascii=False))
