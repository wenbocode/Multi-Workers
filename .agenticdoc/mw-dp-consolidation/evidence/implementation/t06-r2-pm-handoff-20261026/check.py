"""Fresh PM R2 T06 verification; no worker evidence rewrite or product writes."""
from __future__ import annotations
import ast
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
KEY=HERE.parents[2]
ROOT=KEY.parents[1]
WT=KEY/'implementation-worktree'
PKG=WT/'packages/multi-workers'
BASE=KEY/'evidence/implementation/s2-r2-pre-dispatch-20261026'
WORKER=KEY/'evidence/implementation/dpc-t06-validity/rework-r2'
assert sys.dont_write_bytecode and not (HERE/'check.json').exists()
def sha(value):
    return hashlib.sha256(value).hexdigest()
def inventory():
    return {p.relative_to(WT).as_posix():sha(p.read_bytes()) for p in WT.rglob('*') if p.is_file()}
def save(name,value):
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def keep(label,rel,data):
    p=HERE/label/rel
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes(data)
start=datetime.now(timezone.utc).isoformat()
before=inventory()
save('before-inventory.json',before)
frontier=json.loads((BASE/'check.json').read_text(encoding='utf-8'))
all_faces=set(frontier['product_paths'])
original=json.loads((BASE/'mirror-inventory.json').read_text(encoding='utf-8'))
assert set(original)==set(before)
net_changes=[p for p in before if before[p]!=original[p]]
assert set(net_changes)<=all_faces
old_evidence=json.loads((BASE/'t06-original-evidence-inventory.json').read_text(encoding='utf-8'))
old_root=KEY/'evidence/implementation/dpc-t06-validity'
assert all((old_root/p).is_file() and sha((old_root/p).read_bytes())==s for p,s in old_evidence.items())
rows=[]
worker_after=json.loads((WORKER/'after.json').read_text(encoding='utf-8'))
for name in ('decision_validity.py','test_dp_consolidation_concurrency.py'):
    rel='packages/multi-workers/'+name
    old=(BASE/'before-bytes'/rel).read_bytes()
    data=(PKG/name).read_bytes()
    assert (WORKER/'before-bytes'/name).read_bytes()==old
    assert (WORKER/'after-bytes'/name).read_bytes()==data
    assert sha(data)==worker_after[name]['after']['sha256']
    keep('before-bytes',rel,old);keep('after-bytes',rel,data)
    diff=''.join(difflib.unified_diff(old.decode('utf-8').splitlines(keepends=True),data.decode('utf-8').splitlines(keepends=True),fromfile='before/'+rel,tofile='after/'+rel))
    (HERE/(name+'.diff')).write_text(diff,encoding='utf-8',newline='\n')
    actual_diff=(WORKER/(name+'.diff')).read_bytes()
    assert sha(actual_diff)==worker_after[name]['diff_sha256']
    rows.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(data),'after_bytes':len(data),'crlf':data.count(b'\r\n'),'lf':data.count(b'\n'),'pm_diff_bytes':len(diff.encode('utf-8')),'worker_diff_actual_bytes':len(actual_diff),'worker_diff_recorded_size':worker_after[name]['diff_bytes'],'worker_diff_decoded_characters':len(actual_diff.decode('utf-8')),'worker_diff_sha256':sha(actual_diff),'worker_diff_byte_size_field_matches':len(actual_diff)==worker_after[name]['diff_bytes']})
    assert not (ROOT/rel).exists()
old_test=ast.parse((BASE/'before-bytes/packages/multi-workers/test_dp_consolidation_concurrency.py').read_text(encoding='utf-8'))
new_test=ast.parse((PKG/'test_dp_consolidation_concurrency.py').read_text(encoding='utf-8'))
old_funcs={n.name:ast.dump(n,include_attributes=False) for n in old_test.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
new_funcs={n.name:ast.dump(n,include_attributes=False) for n in new_test.body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef))}
assert all(new_funcs.get(k)==v for k,v in old_funcs.items())
red=(WORKER/'red-r2.stdout').read_text(encoding='utf-8')
assert '7 failed, 66 passed' in red and 'ERROR collecting' not in red
assert (WORKER/'red-r2.rc').read_text().strip()=='1'
for stem in ('green-r2','green-r2-final','green-r2-repeat'):
    assert '73 passed' in (WORKER/(stem+'.stdout')).read_text(encoding='utf-8')
    assert (WORKER/(stem+'.rc')).read_text().strip()=='0'
env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','SYSTEMDRIVE','WINDIR','COMSPEC','PATHEXT') if k in os.environ}
fixture=HERE/'fixture'
for name in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR','APPDATA','LOCALAPPDATA','PROJECT_ROOT'):
    p=fixture/name.lower();p.mkdir(parents=True,exist_ok=True);env[name]=str(p)
env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONNOUSERSITE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','LANG':'C.UTF-8','LC_ALL':'C.UTF-8'})
commands=[]
for label,args in [('pm-green',[str(HERE/'bootstrap.py'),'tests']),('pm-literal',['-m','pytest','-p','no:cacheprovider','-q','test_dp_consolidation_concurrency.py']),('pm-probe',[str(HERE/'bootstrap.py'),'probes'])]:
    argv=[sys.executable,'-B',*args]
    r=subprocess.run(argv,cwd=PKG,env=env,capture_output=True)
    (HERE/(label+'.stdout')).write_bytes(r.stdout);(HERE/(label+'.stderr')).write_bytes(r.stderr)
    commands.append({'label':label,'argv':argv,'cwd':str(PKG),'rc':r.returncode,'stdout':r.stdout.decode('utf-8'),'stderr':r.stderr.decode('utf-8')})
    print(label,'rc=',r.returncode);print(r.stdout.decode('utf-8'));print(r.stderr.decode('utf-8'))
    assert r.returncode==0
    if label!='pm-probe':assert b'73 passed' in r.stdout
save('commands.json',commands)
after=inventory();save('after-inventory.json',after)
assert before==after
probes=json.loads((HERE/'probe.json').read_text(encoding='utf-8'))
assert probes['boundary_failures']==probes['control_failures']==0
original_probe=json.loads((KEY/'evidence/implementation/t06-pm-handoff-20261026/supplement.json').read_text(encoding='utf-8'))
assert [x['name'] for x in probes['boundaries']]==[x['name'] for x in original_probe['boundary_checks']]
pyc={p:s for p,s in after.items() if p.endswith('.pyc')}
assert len(pyc)==14 and all(original[p]==s for p,s in pyc.items())
result={'started_at':start,'observed_at':datetime.now(timezone.utc).isoformat(),'assigned_suite_rc':[x['rc'] for x in commands if x['label']!='pm-probe'],'assigned_suite_passed':73,'same_original_test_function_asts':True,'old_test_functions_preserved':len(old_funcs),'new_test_functions':sorted(set(new_funcs)-set(old_funcs)),'worker_real_red_summary':'7 failed, 66 passed / rc1, seven business assertion failures','exact_original_boundary_checks':9,'boundary_failures':probes['boundary_failures'],'positive_controls':len(probes['controls']),'control_failures':probes['control_failures'],'products':rows,'mirror_files':len(after),'frontier_allowed_net_changes':net_changes,'verification_net_changes':[],'original_worker_evidence_hashes_unchanged':len(old_evidence),'pyc_preserved':len(pyc),'three_live_original_paths_absent':False,'two_live_t06_paths_absent':True,'local_rework_boundary_verified':True,'whole_claim_lock_and_real_signoff_contract_reference_resolution_not_verified':True,'whole_live_or_historical_transient_no_write_not_proved':True,'full_l2_qg_signature_or_stage_close':False}
save('check.json',result)
print(json.dumps(result,ensure_ascii=False,indent=2))
