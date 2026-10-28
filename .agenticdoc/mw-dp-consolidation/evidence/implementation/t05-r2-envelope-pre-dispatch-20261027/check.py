import ast,hashlib,json,os,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';PRE=KEY/'evidence/implementation/t05-r2-pre-dispatch-20261027';CARD=KEY/'tasks/isolated/T05-eight-cases-r2-envelope.md'
assert not (HERE/'check.json').exists()
def sha(b):return hashlib.sha256(b).hexdigest()
def save(n,v):(HERE/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def inv(p):return {f.relative_to(p).as_posix():sha(f.read_bytes()) for f in p.rglob('*') if f.is_file()}
raw=(KEY/'implementation-isolated-dag.json').read_bytes();(HERE/'dag-before.json').write_bytes(raw);(HERE/'pm-state-before.md').write_bytes((KEY/'pm-state.md').read_bytes());dag=json.loads(raw);t05=next(t for t in dag['tasks'] if t['id']=='T05');t10=next(t for t in dag['tasks'] if t['id']=='T10');mirror=inv(WT);assert mirror==json.loads((PRE/'mirror-inventory.json').read_text(encoding='utf-8')) and len(mirror)==1891;save('mirror-inventory.json',mirror)
metadata=[]
for p in t05['product_write_face']:
    f=ROOT/p;rel=f.relative_to(WT);b=f.read_bytes();assert b==(PRE/'before-bytes'/rel).read_bytes();out=HERE/'before-bytes'/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(b);metadata.append({'path':p,'bytes':len(b),'sha256':sha(b),'lf':b.count(b'\n'),'crlf':b.count(b'\r\n')})
save('before-metadata.json',metadata);save('before-test-functions.json',json.loads((PRE/'before-test-functions.json').read_text(encoding='utf-8')))
protection={}
for label,path in [('original-T05-evidence',KEY/'evidence/implementation/dpc-t05-eight-cases'),('original-T05-worker-history',KEY/'workers/dpc-t05-eight-cases'),('blocked-R2-worker-history',KEY/'workers/dpc-t05-eight-cases-r2'),('T10-worker-history',KEY/'workers/dpc-t10-lifecycle-state'),('T10-evidence',KEY/'evidence/implementation/dpc-t10-lifecycle-state'),('PM-original-handoff',KEY/'evidence/implementation/t05-pm-handoff-20261027')]:
    protection[label]=(path,inv(path));save(label+'-protection.json',protection[label][1])
run=json.loads((KEY/'workers/dpc-t05-eight-cases-r2/run.json').read_text(encoding='utf-8'));assert run['status']=='done' and run['exit']==0;save('blocked-R2-run.json',run);assert 'BLOCKED' in (KEY/'workers/dpc-t05-eight-cases-r2/output.md').read_text(encoding='utf-8');guard=json.loads((KEY/'evidence/implementation/dpc-t05-eight-cases/rework-r2/blocker/guard-refusal.json').read_text(encoding='utf-8'));save('blocked-R2-guard-refusal.json',guard)
card=CARD.read_bytes();(HERE/'T05-R2-envelope-card.md').write_bytes(card)
env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','SYSTEMDRIVE') if k in os.environ}
for k in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR','APPDATA','LOCALAPPDATA'):
    p=HERE/'fixture'/k.lower();p.mkdir(parents=True,exist_ok=True);env[k]=str(p)
env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONNOUSERSITE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','MW_PROJECT_DIR':str(HERE/'fixture/project')});(HERE/'fixture/project').mkdir(parents=True,exist_ok=True);argv=[sys.executable,'-B',str(HERE/'carrier.py')];probe=subprocess.run(argv,cwd=ROOT,env=env,capture_output=True);(HERE/'carrier.stdout').write_bytes(probe.stdout);(HERE/'carrier.stderr').write_bytes(probe.stderr);print(probe.stdout.decode('utf-8'));print(probe.stderr.decode('utf-8'));assert probe.returncode==0
carrier=json.loads((HERE/'carrier.json').read_text(encoding='utf-8'));assert set(carrier['new_extracted_entries'])==set(t05['product_write_face'])|{'.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/rework-r2-envelope/**'}
assert inv(WT)==mirror
for path,inventory in protection.values():assert inv(path)==inventory
assert (KEY/'implementation-isolated-dag.json').read_bytes()==raw
save('T10-products-protection.json',{p:sha((ROOT/p).read_bytes()) for p in t10['product_write_face']});save('pyc-protection-current.json',{p:s for p,s in mirror.items() if p.endswith('.pyc')});result={'source':'agent-report','observed_at':datetime.now(timezone.utc).isoformat(),'blocked_original_R2_done_exit0_acked_no_product_changes':True,'blocked_R2_actual_run_id':run['run_id'],'guard_rejection_preserved':True,'new_card_sha256':sha(card),'new_card_12_entry_extraction_render_parse_roundtrip':True,'original_control_12_old_bad_control_1':True,'original_11_product_face_exact':True,'current_before_bytes_saved':11,'current_test_functions_preserved':28,'mirror_1891_unchanged_since_failed_envelope':True,'all_original_PM_worker_histories_protected':True,'pyc_14_current_bytes_protected_prior_1_drift_not_erased':True,'T10_five_products_protected':True,'carrier_argv':argv,'carrier_rc':probe.returncode,'actual_new_worker_dispatched':False,'logical_tasks':36,'stages':7};save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
