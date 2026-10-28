import json,hashlib,sys,os,subprocess
from pathlib import Path
from datetime import datetime,timezone
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';assert not (HERE/'finish.json').exists()
a=json.loads((HERE/'dag-before.json').read_text(encoding='utf-8'));p=KEY/'implementation-isolated-dag.json';b=json.loads(p.read_text(encoding='utf-8'));assert len(a['tasks'])==len(b['tasks'])==36 and len(b['stages'])==7;assert {k:v for k,v in a.items() if k!='tasks'}=={k:v for k,v in b.items() if k!='tasks'}
for old,new in zip(a['tasks'],b['tasks']):
    if old['id'] not in ('T05','T10'):assert old==new
    else:
        assert {k:v for k,v in old.items() if k!='handoff_audit_attempt'}=={k:v for k,v in new.items() if k!='handoff_audit_attempt'}
        x=new['handoff_audit_attempt'];assert x['status']=='done' and x['exit']==0 and x['acked'];assert new['semantic_handoff_verified'] is False;assert x['previous_observation']['observed_at']==old['handoff_audit_attempt']['observed_at']
inv={p.relative_to(WT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in WT.rglob('*') if p.is_file()};assert inv==json.loads((HERE/'mirror-before.json').read_text(encoding='utf-8'))
for row in json.loads((HERE/'check.json').read_text(encoding='utf-8'))['workers']:assert hashlib.sha256((KEY/row['evidence']).read_bytes()).hexdigest()==row['sha256']
(HERE/'dag-after.json').write_bytes(p.read_bytes());(HERE/'state-after.md').write_bytes((KEY/'pm-state.md').read_bytes());env={k:v for k,v in os.environ.items() if k.upper() in {'PATH','SYSTEMROOT','WINDIR'}};env.update(PYTHONDONTWRITEBYTECODE='1',PYTHONUTF8='1',PYTHONIOENCODING='utf-8');run=subprocess.run([sys.executable,'-B',str(ROOT/'.agents/skills/agentic-task/scripts/audit_phase.py'),'mw-dp-consolidation'],cwd=ROOT,env=env,capture_output=True);(HERE/'audit.stdout').write_bytes(run.stdout);(HERE/'audit.stderr').write_bytes(run.stderr);assert run.returncode==0
result={'observed_at':datetime.now(timezone.utc).isoformat(),'source':'agent-report','two_audit_attempts_done_exit0_acked':True,'only_two_attempt_metadata_changed_original_all_contracts_and_other_34_tasks_preserved':True,'1891_product_bytes_current_14_pyc_unchanged':True,'original_two_reports_unchanged':True,'T05_T10_full_handoffs_false_S2_open':True,'new_product_runs':[],'new_OS_fixture_creation_or_use':False,'structure_audit_rc':run.returncode,'structure_audit_not_L2_QG_signoff':True};(HERE/'finish.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n');print(run.stdout.decode('utf-8'));print(json.dumps(result,ensure_ascii=False,indent=2))
