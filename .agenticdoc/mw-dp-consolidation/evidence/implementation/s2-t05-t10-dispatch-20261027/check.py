"""Record actual parallel workers and independently audit metadata-only DAG update."""
from datetime import datetime,timezone
import copy
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];PRE=KEY/'evidence/implementation/s2-t05-t10-pre-dispatch-20261027';WT=KEY/'implementation-worktree';DAG=KEY/'implementation-isolated-dag.json'
assert not (HERE/'check.json').exists()
def sha(b):return hashlib.sha256(b).hexdigest()
def save(name,value):
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def inv(root):return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
def section(text,title):
    match=re.search(r'^## '+re.escape(title)+r'\n(.*?)(?=^## |\Z)',text,re.M|re.S);assert match,title;return match[1].strip()
observed=datetime.now(timezone.utc).isoformat();raw=DAG.read_bytes();(HERE/'dag-before-record.json').write_bytes(raw);dag=json.loads(raw);old=copy.deepcopy(dag);byid={t['id']:t for t in dag['tasks']};assert len(byid)==36 and len(dag['stages'])==7
frontier=json.loads((PRE/'frontier.json').read_text(encoding='utf-8'));records=[]
for front in frontier:
    row=byid[front['id']];card=ROOT/'.agenticdoc/mw-dp-consolidation'/front['card'];ct=card.read_text(encoding='utf-8');assert sha(card.read_bytes())==front['card_sha256'];worker=KEY/'workers'/front['task_key'];task=worker/'task.md';text=task.read_text(encoding='utf-8');run=json.loads((worker/'run.json').read_text(encoding='utf-8'));assert run['status'] in ('running','done','failed','needs-clarification') and run['owner_key']==KEY.name
    header=text.split('<!-- mw-dispatch-card:',1)[0];actual=set(re.search(r'^write_face: (.+)$',header,re.M)[1].split(', '));expected=set(row['product_write_face'])|{row['evidence']+'/**'};assert actual==expected;assert 'card_sha256: '+front['card_sha256'] in header
    for title in ('上下文','要求','交付格式','写入允许面','写入禁止面','验收命令','改动历史'):assert section(ct,title)==section(text,title),(front['id'],title)
    for name in ('task.md','run.json'):(HERE/(front['id']+'-'+name)).write_bytes((worker/name).read_bytes())
    row.setdefault('observation_history',[]).append({'status':row['status'],'observed_at':None,'source':'agent-report','completed':None,'remaining':None,'blockers':None,'unrecorded_prior_observation_time':True});row['status']=run['status'];row['run_id']=run['run_id'];row['started_at']=run['started_at'];row['pid']=run['pid'];row['dispatch_card_sha256']=front['card_sha256'];row['dispatch_recorded_card_path_label']=re.search(r'^card_path: (.+)$',header,re.M)[1];row['dispatch_write_face_verified']=True;row['pre_dispatch_evidence']='evidence/implementation/s2-t05-t10-pre-dispatch-20261027/check.json';row['dispatch_evidence']='evidence/implementation/s2-t05-t10-dispatch-20261027/check.json';row['semantic_handoff_verified']=False;row['code_status']='代码进行中' if run['status']=='running' else '终态待吸收独立复验';row['verification_status']='未独立验证；共享imports由PM两终态后复验';row['observation']={'status':run['status'],'observed_at':observed,'source':'agent-report','completed':None,'remaining':None,'blockers':None};records.append({'id':front['id'],'run':run,'card_sha256':front['card_sha256'],'actual_seed_SHA256':sha(task.read_bytes()),'exact_envelope_sections_and_face_verified':True,'shortened_card_label_preserved':row['dispatch_recorded_card_path_label'],'substantive_progress':None,'decision_header_present':'decision:' in header})
t09=byid['T09'];rr=t09['rework_attempt_r2'];r2=json.loads((KEY/'workers/dpc-t09-books-r2/run.json').read_text(encoding='utf-8'));assert r2['status']=='done' and r2['exit']==0;rr['previous_observation']=copy.deepcopy(rr);rr.update({'status':'done','exit':0,'ended_at':r2['ended_at'],'acked':True,'semantic_handoff_verified':True,'pm_handoff_evidence':'evidence/implementation/t09-r2-pm-handoff-20261027/report.md','observed_at':observed});t09['previous_observation']=t09['observation'];t09['observation']={'status':'done','source':'agent-report','observed_at':observed,'completed':['R2真实终态吸收acked','指定suite PM两次131passed','原PM byte-identical17fixtures全部通过','43原测试函数AST/source保留；EOF声明勘误保留'],'remaining':['CLI及context/观察/完整集成由原authorized owners继续'],'blockers':[]};t09['pm_latest_handoff_evidence']='evidence/implementation/t09-r2-pm-handoff-20261027/report.md'
contracts=('id','task_key','card','stage','type','execution','deps','ac_refs','vc_refs','product_write_face','commands','goal','requirements')
for row in dag['tasks']:
    prev=next(r for r in old['tasks'] if r['id']==row['id'])
    assert all(row.get(field)==prev.get(field) for field in contracts)
    if row['id'] not in ('T05','T09','T10'):assert row==prev
assert dag['stages']==old['stages'];DAG.write_text(json.dumps(dag,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n');(HERE/'dag-after-record.json').write_bytes(DAG.read_bytes())
mirror=inv(WT);baseline=json.loads((PRE/'mirror-inventory.json').read_text(encoding='utf-8'));union={str((ROOT/p).relative_to(WT)).replace('\\','/') for t in frontier for p in byid[t['id']]['product_write_face']};changes=sorted(p for p in set(mirror)|set(baseline) if mirror.get(p)!=baseline.get(p));assert all(p in union for p in changes);assert all(mirror[p]==s for p,s in json.loads((PRE/'old-case-protection.json').read_text(encoding='utf-8')).items());assert {p:s for p,s in mirror.items() if p.endswith('.pyc')}==json.loads((PRE/'pyc-protection.json').read_text(encoding='utf-8'))
for front in frontier:
    for meta in front['product_face']:
        live=ROOT/(ROOT/meta['path']).relative_to(WT);assert live.exists()==meta['live_exists'];assert not live.exists() or sha(live.read_bytes())==meta['live_sha256']
state=KEY/'pm-state.md';b=state.read_bytes();assert b'- Phase: EXECUTE' in b;(HERE/'pm-state-current-before-timestamp.md').write_bytes(b);date=datetime.now(timezone.utc).astimezone().strftime('%Y-%m-%d %H:%M');s=b.decode('utf-8');s,count=re.subn(r'(?m)^- Updated: .*$', '- Updated: '+date,s,count=1);assert count==1;state.write_bytes(s.encode('utf-8'));assert b'- Phase: EXECUTE' in state.read_bytes();(HERE/'pm-state-current-after.md').write_bytes(state.read_bytes())
audit=subprocess.run([sys.executable,'-B',str(ROOT/'.agents/skills/agentic-task/scripts/audit_phase.py'),'mw-dp-consolidation'],cwd=ROOT,capture_output=True);(HERE/'audit.stdout').write_bytes(audit.stdout);(HERE/'audit.stderr').write_bytes(audit.stderr);assert audit.returncode==0;print(audit.stdout.decode('utf-8'))
result={'source':'agent-report','observed_at':observed,'actual_worker_records':records,'logical_tasks':36,'stages':7,'all_original_task_contracts_preserved':True,'only_T05_T09_T10_metadata_updated':True,'T09_original_run_exit_history_preserved':True,'R2_done_exit0_acked_currently_recorded':True,'phase':'EXECUTE','audit_rc':audit.returncode,'mirror_file_count':len(mirror),'active_workers_allowed_net_changes_at_observation':changes,'out_of_face_net_changes':[],'four_old_cases_and14pyc_protected':True,'relevant_16_live_presence_and_bytes_baselines_unchanged':True,'shared_read_dependency_coordinated_but_not_yet_qualified':True,'production_deployment_or_final_QG_signoff':False};save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
