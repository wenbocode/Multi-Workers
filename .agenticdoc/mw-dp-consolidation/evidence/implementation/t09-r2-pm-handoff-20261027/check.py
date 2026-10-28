"""Independent T09 R2 tests with byte-identical PM 17-fixture bootstrap in a new output dir."""
from datetime import datetime,timezone
import ast
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';PKG=WT/'packages/multi-workers';OLD=KEY/'evidence/implementation/t09-pm-handoff-20261027';PRE=KEY/'evidence/implementation/t09-r2-pre-dispatch-20261027';WORKER=KEY/'evidence/implementation/dpc-t09-books/rework-r2'
assert not (HERE/'check.json').exists()
def sha(b):return hashlib.sha256(b).hexdigest()
def inv(root):return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
def save(n,v):(HERE/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
started=datetime.now(timezone.utc).isoformat();before=inv(WT);baseline=json.loads((PRE/'mirror-inventory.json').read_text(encoding='utf-8'));paths=['packages/multi-workers/decision_book.py','packages/multi-workers/test_decision_context_contract.py'];assert set(before)==set(baseline) and len(before)==1883
assert sorted(p for p in before if before[p]!=baseline[p])==sorted(paths)
worker_inv=inv(WORKER);oldpm_inv=inv(OLD);save('worker-r2-evidence-inventory.json',worker_inv);save('original-pm-evidence-inventory.json',oldpm_inv)
original_worker=KEY/'evidence/implementation/dpc-t09-books';protected=json.loads((PRE/'t09-original-evidence-inventory.json').read_text(encoding='utf-8'));assert all(sha((original_worker/p).read_bytes())==s for p,s in protected.items())
run_roots={name:inv(KEY/'workers'/name) for name in ('dpc-t09-books','dpc-t09-books-r2')};save('worker-history-inventory.json',run_roots)
records=json.loads((WORKER/'after-bytes.json').read_text(encoding='utf-8'));products=[]
for rel in paths:
    data=(WT/rel).read_bytes();old=(PRE/'before-bytes'/rel).read_bytes();record=records['products'][Path(rel).name]
    assert sha(data)==record['after_sha256'] and len(data)==record['after_bytes'];assert old==(WORKER/'before-bytes'/(Path(rel).name+'.before')).read_bytes()
    for label,b in (('before-bytes',old),('after-bytes',data)):
        dest=HERE/label/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b)
    diff=''.join(difflib.unified_diff(old.decode('utf-8').splitlines(keepends=True),data.decode('utf-8').splitlines(keepends=True),fromfile='a/'+rel,tofile='b/'+rel));(HERE/(Path(rel).name+'.diff')).write_text(diff,encoding='utf-8',newline='\n')
    raw=(WORKER/'diffs'/(Path(rel).name+'.diff')).read_bytes();assert raw.decode('utf-8').replace('\r\n','\n')==diff
    products.append({'path':rel,'before_sha256':sha(old),'after_sha256':sha(data),'bytes':len(data),'lf':data.count(b'\n'),'crlf':data.count(b'\r\n'),'diff_hunks':sum(l.startswith('@@') for l in diff.splitlines()),'pm_utf8_lf_diff_bytes':len(diff.encode('utf-8')),'worker_raw_diff_bytes':len(raw),'worker_raw_diff_sha256':sha(raw)})
oldtext=(PRE/'before-bytes'/paths[1]).read_text(encoding='utf-8');newtext=(WT/paths[1]).read_text(encoding='utf-8')
def funcs(text):return {n.name:(ast.dump(n,include_attributes=False),ast.get_source_segment(text,n)) for n in ast.parse(text).body if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)) and n.name.startswith('test_')}
bf=funcs(oldtext);af=funcs(newtext);assert len(bf)==43 and len(af)==50 and all(af[n]==v for n,v in bf.items());save('test-ast-source-preservation.json',{'before_functions':43,'after_functions':50,'preserved_exactly':True,'added':sorted(set(af)-set(bf))})
bootstrap=(OLD/'bootstrap.py').read_bytes();(HERE/'bootstrap.py').write_bytes(bootstrap);assert sha(bootstrap)==sha((HERE/'bootstrap.py').read_bytes());save('bootstrap-parity.json',{'sha256':sha(bootstrap),'byte_identical_to_original_PM':True,'only_runtime_HERE_is_new_output_root':True})
env={n:os.environ[n] for n in ('PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','SYSTEMDRIVE') if n in os.environ}
for name in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR','APPDATA','LOCALAPPDATA','PROJECT_ROOT'):
    p=HERE/'fixture'/name.lower();p.mkdir(parents=True,exist_ok=True);env[name]=str(p)
env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONNOUSERSITE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'})
commands=[]
for label,mode,fixture in (('assigned-1','tests','basetemp-1'),('assigned-2','tests','basetemp-2'),('original-17-fixtures','probe','probe-project')):
    argv=[sys.executable,'-B',str(HERE/'bootstrap.py'),mode,str(HERE/'fixture'/fixture)];run=subprocess.run(argv,cwd=PKG,env=env,capture_output=True);(HERE/(label+'.stdout')).write_bytes(run.stdout);(HERE/(label+'.stderr')).write_bytes(run.stderr);commands.append({'label':label,'argv':argv,'rc':run.returncode,'cwd':str(PKG),'stdout':label+'.stdout','stderr':label+'.stderr'});print(label,'rc=',run.returncode);print(run.stdout.decode('utf-8'));print(run.stderr.decode('utf-8'))
    assert run.returncode==0
    if mode=='tests':assert b'131 passed' in run.stdout
probe=json.loads((HERE/'probe.json').read_text(encoding='utf-8'));assert len(probe['fixtures'])==17 and probe['passed']==17 and probe['failed']==0
assert before==inv(WT) and worker_inv==inv(WORKER) and oldpm_inv==inv(OLD)
assert all(run_roots[name]==inv(KEY/'workers'/name) for name in run_roots)
assert all(sha((original_worker/p).read_bytes())==s for p,s in protected.items())
assert all((ROOT/rel).read_bytes()==(KEY/'evidence/implementation/t09-pre-dispatch-20261027/before-bytes'/rel).read_bytes() for rel in paths)
pyc={p:s for p,s in before.items() if p.endswith('.pyc')};assert len(pyc)==14 and pyc=={p:s for p,s in baseline.items() if p.endswith('.pyc')};save('mirror-inventory.json',before)
result={'source':'agent-report','started_at':started,'observed_at':datetime.now(timezone.utc).isoformat(),'products':products,'assigned_passed':131,'assigned_runs':2,'original_PM_bootstrap_byte_identical':True,'original_17_fixtures_passed':17,'original_17_fixtures_failed':0,'prior_genuine_negative_failures_preserved':13,'old_test_function_AST_and_source_segments_preserved':43,'full_current_source_and_test_read_to_EOF_by_PM':True,'mirror_files':1883,'verification_net_changes':[],'protected_original_worker_and_PM_evidence_unchanged':True,'relevant_live_baselines_unchanged':True,'pyc_preserved':14,'commands':commands,'semantic_handoff_verified':True,'whole_live_transient_or_exclusive_authorship_audit':False,'production_CLI_context_projection_observation_and_grant_verified':False,'worker_declared_after_record_observed_at':records['observed_at'],'worker_metadata_timestamp_is_not_PM_provenance':True};save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
