"""Readonly completion of state audit, preserving the real out-of-face pyc drift."""
from datetime import datetime,timezone
import hashlib,json,subprocess,sys
from pathlib import Path
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';PRE=KEY/'evidence/implementation/s2-t05-t10-pre-dispatch-20261027';HAND=KEY/'evidence/implementation/t09-r2-pm-handoff-20261027'
assert not (HERE/'completion.json').exists()
def sha(data):return hashlib.sha256(data).hexdigest()
def inv(root):return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
def save(name,data):(HERE/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
old=json.loads((HERE/'dag-before-record.json').read_text(encoding='utf-8'));dag=json.loads((KEY/'implementation-isolated-dag.json').read_text(encoding='utf-8'));assert len(dag['tasks'])==36 and len(dag['stages'])==7 and old['stages']==dag['stages'];contracts=('id','task_key','card','stage','type','execution','deps','ac_refs','vc_refs','product_write_face','commands','goal','requirements')
for row in dag['tasks']:
    prev=next(p for p in old['tasks'] if p['id']==row['id']);assert all(row.get(f)==prev.get(f) for f in contracts)
    if row['id'] not in ('T05','T09','T10'):assert row==prev
run_records=[]
for taskid in ('T05','T10'):
    row=next(p for p in dag['tasks'] if p['id']==taskid);run=json.loads((KEY/'workers'/row['task_key']/'run.json').read_text(encoding='utf-8'));assert row['run_id']==run['run_id'] and not row['semantic_handoff_verified'];run_records.append({'id':taskid,'run':run,'seed_and_exact_face_checked_before_manifest_write_in':'check.py + '+taskid+'-task.md','product_progress':None})
base=json.loads((PRE/'mirror-inventory.json').read_text(encoding='utf-8'));now=inv(WT);union={str((ROOT/p).relative_to(WT)).replace('\\','/') for row in dag['tasks'] if row['id'] in ('T05','T10') for p in row['product_write_face']};changes=[{'path':p,'before':base.get(p),'after':now.get(p),'authorized_product':p in union} for p in sorted(set(base)|set(now)) if base.get(p)!=now.get(p)];outside=[r for r in changes if not r['authorized_product']];assert {r['path'] for r in outside}=={'packages/multi-workers/__pycache__/decision.cpython-314.pyc'}
cache=outside[0];before_cache=None  # This audit has the preserved before hash, not a claimed before raw-byte snapshot.
(HERE/'decision.cpython-314.current.pyc.bytes').write_bytes((WT/cache['path']).read_bytes());save('pyc-change.json',{'source':'agent-report','observed_at':datetime.now(timezone.utc).isoformat(),'drift':cache,'original_before_byte_copy_found':None if before_cache is None else str(before_cache.relative_to(KEY)),'original_before_sha_preserved':cache['before'],'deleted_or_restored':False,'only_this_one_of_original14_changed':True,'exclusive_author_and_transient_history_not_proved':True})
for path,s in json.loads((PRE/'old-case-protection.json').read_text(encoding='utf-8')).items():assert now[path]==s
pyc={p:s for p,s in now.items() if p.endswith('.pyc')};orig=json.loads((PRE/'pyc-protection.json').read_text(encoding='utf-8'));assert len(pyc)==14 and set(pyc)==set(orig) and all(pyc[p]==s for p,s in orig.items() if p!=cache['path'])
for front in json.loads((PRE/'frontier.json').read_text(encoding='utf-8')):
    for meta in front['product_face']:
        live=ROOT/(ROOT/meta['path']).relative_to(WT);assert live.exists()==meta['live_exists'];assert not live.exists() or sha(live.read_bytes())==meta['live_sha256']
for record in json.loads((HAND/'check.json').read_text(encoding='utf-8'))['products']:assert now[record['path']]==record['after_sha256']
for name in ('original-pm-evidence-inventory.json','worker-r2-evidence-inventory.json'):
    target=KEY/'evidence/implementation'/('t09-pm-handoff-20261027' if name.startswith('original') else 'dpc-t09-books/rework-r2');assert inv(target)==json.loads((HAND/name).read_text(encoding='utf-8'))
for taskid in ('T05','T10'):
    taskkey=next(p for p in dag['tasks'] if p['id']==taskid)['task_key'];trace=KEY/'workers'/taskkey/'trace.log'
    if trace.exists():
        b=trace.read_bytes();(HERE/(taskid+'-trace-observation.log')).write_bytes(b)
        save(taskid+'-python-trace-lines.json',[{'line':i,'text':line} for i,line in enumerate(b.decode('utf-8').splitlines(),1) if 'python' in line.lower() or 'pyc' in line.lower()])
audit=subprocess.run([sys.executable,'-B',str(ROOT/'.agents/skills/agentic-task/scripts/audit_phase.py'),'mw-dp-consolidation'],cwd=ROOT,capture_output=True);(HERE/'completion-audit.stdout').write_bytes(audit.stdout);(HERE/'completion-audit.stderr').write_bytes(audit.stderr);assert audit.returncode==0
result={'source':'agent-report','observed_at':datetime.now(timezone.utc).isoformat(),'records':run_records,'logical_tasks':36,'stages':7,'contracts_preserved':True,'phase':'EXECUTE','phase_audit_rc':0,'T09_R2_local_handoff_true':True,'T05_T10_handoff_false_pending_terminal_and_independent_tests':True,'mirror_files':len(now),'changes':changes,'out_of_face_changes':outside,'write_surface_audit_pass':False,'14_cache_names_exist_13_bytes_unchanged_1_changed':True,'no_cache_cleanup_or_restore_authority_used':True,'16_relevant_live_baselines_unchanged':True,'prior_T09_products_and_original_PM_R2_worker_evidence_protected':True,'no_deployment_or_final_QG_signoff':True};save('completion.json',result);print(json.dumps(result,ensure_ascii=False,indent=2));print(audit.stdout.decode('utf-8'))
