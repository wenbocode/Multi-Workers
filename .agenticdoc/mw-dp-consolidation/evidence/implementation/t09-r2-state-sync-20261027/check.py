"""Read back current T09/R2 metadata, DAG contract and preserved original evidence."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];PRE=KEY/'evidence/implementation/t09-r2-pre-dispatch-20261027'
assert not (HERE/'check.json').exists()
def sha(b):return hashlib.sha256(b).hexdigest()
def inventory(root):return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
def save(n,d):(HERE/n).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
before=json.loads((PRE/'implementation-isolated-dag.json.before').read_text(encoding='utf-8'));after=json.loads((KEY/'implementation-isolated-dag.json').read_text(encoding='utf-8'));b={t['id']:t for t in before['tasks']};a={t['id']:t for t in after['tasks']}
assert a.keys()==b.keys() and len(a)==36
assert {k:v for k,v in before.items() if k!='tasks'}=={k:v for k,v in after.items() if k!='tasks'}
for task in a:
    if task!='T09':assert a[task]==b[task],task
    for field in ('id','deps','card','ac_refs','vc_refs','write_face','source_product_write_face','product_write_face','stage','commands','acceptance_commands','execution','type','role'):
        assert a[task].get(field)==b[task].get(field),(task,field)
for name in ('run_id','started_at','pid'):assert a['T09'][name]==b['T09'][name]
run=json.loads((KEY/'workers/dpc-t09-books/run.json').read_text(encoding='utf-8'));r2run=json.loads((KEY/'workers/dpc-t09-books-r2/run.json').read_text(encoding='utf-8'))
assert run['status']=='done' and run['exit']==0 and a['T09']['status']=='done' and a['T09']['acked']
assert run['ended_at']==a['T09']['ended_at']
r2=a['T09']['rework_attempt_r2'];assert r2run['status']=='running' and r2run['run_id']==r2['run_id'] and r2run['pid']==r2['pid'] and r2['exit'] is None
assert a['T09']['semantic_handoff_verified'] is False
assert all(a[t]['semantic_handoff_verified'] for t in ('T03','T04','T06','T07','T08'))
assert all(a[t]['status']=='not-queued' for t in ('T05','T10'))
card=(KEY/r2['card']).read_bytes();assert sha(card)==r2['card_sha256'];seed=(KEY/'workers/dpc-t09-books-r2/task.md').read_text(encoding='utf-8');assert 'card_sha256: '+sha(card) in seed
for path in r2['write_face']:assert path in seed
assert inventory(KEY/'workers/dpc-t09-books')==json.loads((PRE/'t09-original-worker-inventory.json').read_text(encoding='utf-8'))
original= json.loads((PRE/'t09-original-evidence-inventory.json').read_text(encoding='utf-8'));evidence=KEY/'evidence/implementation/dpc-t09-books';assert all(sha((evidence/p).read_bytes())==s for p,s in original.items())
current=inventory(KEY/'implementation-worktree');baseline=json.loads((PRE/'mirror-inventory.json').read_text(encoding='utf-8'));assert set(current)==set(baseline)
net=[p for p in current if current[p]!=baseline[p]];assert set(net)<=set(a['T09']['source_product_write_face'])
assert {p:s for p,s in current.items() if p.endswith('.pyc')}=={p:s for p,s in baseline.items() if p.endswith('.pyc')}
for rel in a['T09']['source_product_write_face']:assert sha((ROOT/rel).read_bytes())==json.loads((KEY/'evidence/implementation/t09-pre-dispatch-20261027/mirror-inventory.json').read_text(encoding='utf-8'))[rel]
state=(KEY/'pm-state.md').read_bytes();before_state=(PRE/'pm-state.md.before').read_bytes();assert b'- Phase: EXECUTE' in state
assert next(line for line in before_state.splitlines() if line.startswith(b'- Phase:'))==next(line for line in state.splitlines() if line.startswith(b'- Phase:'))
(HERE/'pm-state.after.md').write_bytes(state);(HERE/'dag.after.json').write_bytes((KEY/'implementation-isolated-dag.json').read_bytes())
cmd=[sys.executable,'-B',str(ROOT/'.agents/skills/agentic-task/scripts/audit_phase.py'),'mw-dp-consolidation'];run_audit=subprocess.run(cmd,cwd=ROOT,capture_output=True);(HERE/'audit.stdout').write_bytes(run_audit.stdout);(HERE/'audit.stderr').write_bytes(run_audit.stderr);print(run_audit.stdout.decode('utf-8'));print(run_audit.stderr.decode('utf-8'));assert run_audit.returncode==0 and b'VERDICT: PASS' in run_audit.stdout
result={'observed_at':datetime.now(timezone.utc).isoformat(),'source':'agent-report','tasks_preserved':36,'all_stage_dependency_AC_VC_faces_commands_preserved':True,'only_T09_metadata_changed':True,'original_run_status_exit_and_ack':'done/exit0/acked','original_worker_evidence_unchanged':True,'R2_actual_run':r2run,'R2_progress':{'completed':None,'remaining':None,'blockers':None},'card_sha256':sha(card),'card_body_face_verified':True,'T05_T10_not_queued':True,'mirror_files':len(current),'R2_net_changed_paths_at_observation':net,'pyc_unchanged':True,'relevant_live_unchanged':True,'phase':'EXECUTE','audit_rc':run_audit.returncode,'semantic_handoff_verified':False,'all_L2_QG_signoff_complete':False};save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
