import json,hashlib,subprocess,os,sys
from pathlib import Path
from datetime import datetime,timezone
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';dag=KEY/'implementation-isolated-dag.json'
assert not (HERE/'finish.json').exists()
a=json.loads((HERE/'dag-before.json').read_text(encoding='utf-8'));b=json.loads(dag.read_text(encoding='utf-8'));assert len(a['tasks'])==len(b['tasks'])==36 and len(a['stages'])==len(b['stages'])==7;assert {k:v for k,v in a.items() if k!='tasks'}=={k:v for k,v in b.items() if k!='tasks'}
contracts=('id','task_key','card','stage','type','execution','deps','ac_refs','vc_refs','product_write_face','evidence','commands','goal','requirements','source_product_write_face','source_card','source_card_sha256')
for x,y in zip(a['tasks'],b['tasks']):
    assert all(x.get(k)==y.get(k) for k in contracts),x['id']
    if x['id'] not in ('T05','T10'):assert x==y,x['id']
    else:assert y['semantic_handoff_verified'] is False;assert y['handoff_audit_attempt']['type']=='research'
t05=next(t for t in b['tasks'] if t['id']=='T05');assert t05['current_rework_attempt']['status']=='done' and t05['current_rework_attempt']['exit']==0 and t05['current_rework_attempt']['acked'];assert t05['previous_observation']==next(t for t in a['tasks'] if t['id']=='T05')['observation']
inv={p.relative_to(WT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in WT.rglob('*') if p.is_file()};assert inv==json.loads((HERE/'mirror-current.json').read_text(encoding='utf-8'))
(HERE/'dag-after.json').write_bytes(dag.read_bytes());(HERE/'pm-state-after.md').write_bytes((KEY/'pm-state.md').read_bytes());rc=subprocess.run([sys.executable,'-B',str(ROOT/'.agents/skills/agentic-task/scripts/audit_phase.py'),'mw-dp-consolidation'],cwd=ROOT,capture_output=True,env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'});(HERE/'audit.stdout').write_bytes(rc.stdout);(HERE/'audit.stderr').write_bytes(rc.stderr);assert rc.returncode==0
result={'source':'agent-report','observed_at':datetime.now(timezone.utc).isoformat(),'original_36_tasks_7_stages_all_contracts_preserved':True,'only_T05_T10_metadata_changed':True,'all_other_34_task_objects_byte_semantically_equal':True,'historical_T05_running_observation_preserved_as_previous':True,'T05_R2_done_exit0_acked_two_roots_locally_verified':True,'T05_T10_full_handoffs_false':True,'PM_product_writes':[],'mirror_1891_current_pyc_14_unchanged':True,'structure_audit_rc':rc.returncode,'structure_audit_not_product_L2_QG_or_write_history_acceptance':True};(HERE/'finish.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n');print(rc.stdout.decode('utf-8'));print(json.dumps(result,ensure_ascii=False,indent=2))
