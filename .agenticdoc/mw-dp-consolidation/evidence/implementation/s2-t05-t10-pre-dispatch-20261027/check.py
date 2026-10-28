"""Fresh original-face T05/T10 baselines and append-only T09 local qualification."""
from datetime import datetime, timezone
import copy
import difflib
import hashlib
import json
from pathlib import Path
import sys
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';DAG=KEY/'implementation-isolated-dag.json';HAND=KEY/'evidence/implementation/t09-r2-pm-handoff-20261027'
assert not (HERE/'check.json').exists()
def sha(b):return hashlib.sha256(b).hexdigest()
def save(n,v):
    p=HERE/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def inv(root):return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
now=datetime.now(timezone.utc).isoformat();mirror=inv(WT);assert len(mirror)==1883 and mirror==json.loads((HAND/'mirror-inventory.json').read_text(encoding='utf-8'));save('mirror-inventory.json',mirror)
raw=DAG.read_bytes();(HERE/'dag-before.json').write_bytes(raw);dag=json.loads(raw);old=copy.deepcopy(dag);byid={t['id']:t for t in dag['tasks']};assert len(byid)==36 and len(dag['stages'])==7
for dep in ('T03','T04','T08'):assert byid[dep]['semantic_handoff_verified'] is True
run=json.loads((KEY/'workers/dpc-t09-books-r2/run.json').read_text(encoding='utf-8'));assert run['status']=='done' and run['exit']==0
hand=json.loads((HAND/'check.json').read_text(encoding='utf-8'));assert hand['semantic_handoff_verified'] and hand['original_17_fixtures_failed']==0
row=byid['T09'];save('t09-before.json',row);row.setdefault('PM_qualification_history',[]).append({'source':'agent-report','observed_at':now,'previous_semantic_handoff_verified':row.get('semantic_handoff_verified'),'evidence':'evidence/implementation/t09-r2-pm-handoff-20261027/report.md','attempt':'dpc-t09-books-r2','actual_worker_status':'done','actual_worker_exit_code':0,'acked':True,'assigned_passed':131,'assigned_runs':2,'independent_fixtures_passed':17,'preserved_old_test_functions':43,'qualification_scope':'local original-DAG technical dependency only','read_truncation_erratum_preserved':True});row['semantic_handoff_verified']=True;row['code_status']='局部代码完成';row['verification_status']='R2局部技术交接通过；非S2/L2/QG/signoff，完整读取声明勘误见report';save('t09-after.json',row)
frontier=[];faces=[]
for taskid in ('T05','T10'):
    task=byid[taskid];assert task['status']=='not-queued' and task['deps']==['T03','T04','T09'];face=set(task['product_write_face']);assert face and not any(face&previous for previous in faces);faces.append(face)
    card=ROOT/'.agenticdoc/mw-dp-consolidation'/task['card'];body=card.read_bytes();(HERE/(taskid+'-card.md')).write_bytes(body)
    meta=[]
    for path in sorted(face):
        p=ROOT/path;rel=p.relative_to(WT).as_posix();assert not p.is_symlink();data=p.read_bytes() if p.exists() else None;live=ROOT/rel;livebytes=live.read_bytes() if live.exists() else None
        for label,b in (('before-bytes',data),('live-before-bytes',livebytes)):
            if b is not None:
                out=HERE/label/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(b)
        if data is not None and livebytes is not None:
            diff=''.join(difflib.unified_diff(livebytes.decode('utf-8').splitlines(keepends=True),data.decode('utf-8').splitlines(keepends=True),fromfile='live/'+rel,tofile='isolated/'+rel));out=HERE/'existing-diffs'/(rel+'.diff');out.parent.mkdir(parents=True,exist_ok=True);out.write_text(diff,encoding='utf-8',newline='\n')
        meta.append({'path':path,'exists':data is not None,'sha256':None if data is None else sha(data),'bytes':None if data is None else len(data),'lf':None if data is None else data.count(b'\n'),'crlf':None if data is None else data.count(b'\r\n'),'live_exists':livebytes is not None,'live_sha256':None if livebytes is None else sha(livebytes)})
    frontier.append({'id':taskid,'task_key':task['task_key'],'card':task['card'],'card_sha256':sha(body),'product_face':meta,'deps':task['deps'],'status':'not-queued'})
save('frontier.json',frontier);save('before-product-and-live-metadata.json',{t['id']:t['product_face'] for t in frontier});save('old-case-protection.json',{p:mirror[p] for p in ('packages/multi-workers/decide_cases/dp1.json','packages/multi-workers/decide_cases/dp2.json','packages/multi-workers/decide_cases/dp3.json','packages/multi-workers/decide_cases/dp25.json')});save('pyc-protection.json',{p:s for p,s in mirror.items() if p.endswith('.pyc')})
assert inv(WT)==mirror
for t in dag['tasks']:
    before=next(o for o in old['tasks'] if o['id']==t['id'])
    if t['id']!='T09':assert t==before
    else:
        for field in ('id','stage','task_key','type','execution','deps','ac_refs','vc_refs','product_write_face','commands','card','goal','requirements'):assert t.get(field)==before.get(field)
assert dag['stages']==old['stages'];DAG.write_text(json.dumps(dag,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n');(HERE/'dag-after-handoff.json').write_bytes(DAG.read_bytes())
# Find real original authorized owners; this is a coordination map, not a new grant.
seams=['decision_points.py','decision_context.py','decision_playground.py','decision_monitor.py','decision_dashboard.js','test_decision_book.py','test_decision_book_known_secrets.py','test_decision_cli_config_snapshot.py']
save('remaining-seam-owner-map.json',{name:[{'id':t['id'],'task_key':t['task_key'],'card':t['card'],'stage':t['stage'],'authorized_product_paths':[p for p in t['product_write_face'] if p.endswith('/'+name)]} for t in dag['tasks'] if any(p.endswith('/'+name) for p in t['product_write_face'])] for name in seams})
result={'source':'agent-report','observed_at':now,'phase':'EXECUTE','T09_R2_local_handoff_verified':True,'T09_original_process_history_unchanged':True,'frontier':frontier,'parallel_product_face_overlap':[],'shared_read_dependency':'T05 assigned test directly imports decision_lifecycle and indirectly wire/task_state owned by T10; coding parallel, acceptance against stable current imports with pre/post hash checks, PM fresh suites after both terminal; no shadow module or assertion weakening','mirror_file_count':1883,'mirror_net_changes_during_preparation':[],'logical_tasks':36,'stages':7,'only_T09_metadata_changed':True,'no_product_live_budget_goal_spec_or_phase_writes':True};save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
