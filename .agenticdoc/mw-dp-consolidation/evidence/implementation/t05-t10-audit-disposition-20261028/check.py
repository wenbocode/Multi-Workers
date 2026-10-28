import json,hashlib,sys
from pathlib import Path
from datetime import datetime,timezone
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];WT=KEY/'implementation-worktree';assert not (HERE/'check.json').exists()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,v):(HERE/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
inv={p.relative_to(WT).as_posix():sha(p) for p in WT.rglob('*') if p.is_file()};assert inv==json.loads((KEY/'evidence/implementation/handoff-audit-dispatch-20261027/mirror-current.json').read_text(encoding='utf-8'));save('mirror-before.json',inv)
rows=[]
for task,filename in [('dpc-t05-handoff-audit','t05-handoff-audit-20261027.md'),('dpc-t10-handoff-audit','t10-handoff-audit-20261027.md')]:
    runp=KEY/f'workers/{task}/run.json';run=json.loads(runp.read_text(encoding='utf-8'));assert run['status']=='done' and run['exit']==0;p=KEY/'evidence/implementation'/filename;text=p.read_text(encoding='utf-8');assert all(f'## {h}' in text for h in ['结论','证据','改动清单','残留与未验证','上下文来源']);(HERE/f'{task}.run.json').write_bytes(runp.read_bytes());rows.append({'task_key':task,'run_id':run['run_id'],'status':run['status'],'exit':run['exit'],'ended_at':run['ended_at'],'acked_by_PM_tool':True,'source':'agent-report','evidence':p.relative_to(KEY).as_posix(),'sha256':sha(p),'bytes':p.stat().st_size,'logical_lines':len(text.splitlines()),'PM_actual_read':'whole evidence to EOF; T05 1..end; T10 1..110 +111..end; not production EOF'})
(HERE/'dag-before.json').write_bytes((KEY/'implementation-isolated-dag.json').read_bytes());(HERE/'state-before.md').write_bytes((KEY/'pm-state.md').read_bytes())
result={'source':'agent-report','observed_at':datetime.now(timezone.utc).isoformat(),'workers':rows,'both_terminal_reports_absorbed_and_acked':True,'new_product_tests_or_production_imports_run':[],'mirror_count':len(inv),'mirror_and_14_pyc_unchanged_since_dispatch':True,'T05_full_handoff':False,'T10_full_handoff':False,'S2_closed':False,'OS_permission_requested_not_granted':True};save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
