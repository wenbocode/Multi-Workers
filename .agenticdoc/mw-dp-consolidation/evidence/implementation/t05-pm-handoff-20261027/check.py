from datetime import datetime,timezone
import hashlib,json,os,subprocess,sys
from pathlib import Path
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';PKG=WT/'packages/multi-workers';PRE=KEY/'evidence/implementation/s2-t05-t10-pre-dispatch-20261027';WORKER=KEY/'evidence/implementation/dpc-t05-eight-cases'
assert not (HERE/'check.json').exists()
def sha(b):return hashlib.sha256(b).hexdigest()
def inv(p):return {f.relative_to(p).as_posix():sha(f.read_bytes()) for f in p.rglob('*') if f.is_file()}
def save(n,v):(HERE/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
before=inv(WT);protected=inv(WORKER);save('mirror-before.json',before);save('worker-evidence-protection.json',protected)
dag=json.loads((KEY/'implementation-isolated-dag.json').read_text(encoding='utf-8'));t05=next(t for t in dag['tasks'] if t['id']=='T05');t10=next(t for t in dag['tasks'] if t['id']=='T10');meta=[]
for path in t05['product_write_face']:
    p=ROOT/path;rel=p.relative_to(WT);data=p.read_bytes();out=HERE/'before-bytes'/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data);meta.append({'path':path,'bytes':len(data),'sha256':sha(data),'lf':data.count(b'\n'),'crlf':data.count(b'\r\n')})
save('t05-current-before-metadata.json',meta)
env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR','COMSPEC','PATHEXT','SYSTEMDRIVE') if k in os.environ}
for key in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR','APPDATA','LOCALAPPDATA'):
    p=HERE/'fixture'/key.lower();p.mkdir(parents=True,exist_ok=True);env[key]=str(p)
project=HERE/'fixture/project';project.mkdir(parents=True,exist_ok=True);env.update({'MW_PROJECT_DIR':str(project),'PYTHONDONTWRITEBYTECODE':'1','PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8','PYTHONNOUSERSITE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1'})
commands=[]
for mode in ('generate','probe'):
    argv=[sys.executable,'-B',str(HERE/'probe.py'),mode,str(HERE/'fixture/generator-out')];deps_before={p:sha((ROOT/p).read_bytes()) for p in t10['product_write_face']};run=subprocess.run(argv,cwd=PKG,env=env,capture_output=True);deps_after={p:sha((ROOT/p).read_bytes()) for p in t10['product_write_face']};(HERE/(mode+'.stdout')).write_bytes(run.stdout);(HERE/(mode+'.stderr')).write_bytes(run.stderr);commands.append({'mode':mode,'argv':argv,'rc':run.returncode,'deps_before':deps_before,'deps_after':deps_after,'T10_dependency_window_stable':deps_before==deps_after});print(mode,'rc',run.returncode);print(run.stdout.decode('utf-8'));print(run.stderr.decode('utf-8'))
    assert run.returncode==(0 if mode=='generate' else 1)
probe=json.loads((HERE/'probe.json').read_text(encoding='utf-8'));assert len(probe['case_checks'])==8 and len(probe['native_scaffold_positive_controls'])==8 and len(probe['template_failures'])==3 and len(probe['future_prepared_at_cases'])==8
assert inv(WORKER)==protected;after=inv(WT);assert all(after[p.relative_to(WT).as_posix()]==m['sha256'] for m in meta for p in [ROOT/m['path']]);assert {p:s for p,s in before.items() if p.endswith('.pyc')}=={p:s for p,s in after.items() if p.endswith('.pyc')};base=json.loads((PRE/'mirror-inventory.json').read_text(encoding='utf-8'));changes=[p for p in sorted(set(base)|set(after)) if base.get(p)!=after.get(p)];union={str((ROOT/p).relative_to(WT)).replace('\\','/') for t in (t05,t10) for p in t['product_write_face']};outside=[p for p in changes if p not in union];assert outside==['packages/multi-workers/__pycache__/decision.cpython-314.pyc'];assert len(after)==1891
for path,s in json.loads((PRE/'old-case-protection.json').read_text(encoding='utf-8')).items():assert after[path]==s
for front in json.loads((PRE/'frontier.json').read_text(encoding='utf-8')):
    for m in front['product_face']:
        live=ROOT/(ROOT/m['path']).relative_to(WT);assert live.exists()==m['live_exists'];assert not live.exists() or sha(live.read_bytes())==m['live_sha256']
save('mirror-after.json',after);result={'source':'agent-report','observed_at':datetime.now(timezone.utc).isoformat(),'commands':commands,'generator_output_exactly_eight_and_shipped_byte_parity':True,'offline_book_and_prepared_choice_basis_checks_8_pass':True,'native_active_scaffold_controls_8_pass':True,'independent_template_failures':3,'future_synthesis_timestamp_cases':8,'semantic_handoff_verified':False,'assigned_full_suite_still_worker_report_16P12F_not_PM_reproduced_yet':True,'workbench_test_full_read_and_stable_T10_terminal_required_before_assigned_tests':True,'mirror_files':1891,'eight_new_cases_exist_as_real_product_files':True,'verification_changed_T05_products':[],'worker_original_evidence_unchanged':True,'historical_pyc_drift_preserved_no_additional_pyc_change':True,'four_old_cases_and_relevant_live_baselines_unchanged':True,'outside_original_two_worker_faces':outside};save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
