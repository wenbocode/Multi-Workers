"""Verify targeted PM metadata updates without changing tasks, source or run history."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];WT=KEY/'implementation-worktree'
assert not (HERE/'check.json').exists()
def sha(data):return hashlib.sha256(data).hexdigest()
before=json.loads((HERE/'dag.before.json').read_text(encoding='utf-8'));after=json.loads((KEY/'implementation-isolated-dag.json').read_text(encoding='utf-8'))
assert len(before['tasks'])==len(after['tasks'])==36 and before['stages']==after['stages'] and len(after['stages'])==7
original={t['id']:t for t in before['tasks']};current={t['id']:t for t in after['tasks']}
changed=[]
immutable=('id','task_key','card','stage','type','execution','deps','ac_refs','vc_refs','product_write_face','evidence','commands','goal','requirements','source_product_write_face','source_card','source_card_sha256')
for task_id,old in original.items():
    new=current[task_id]
    assert all(old.get(k)==new.get(k) for k in immutable)
    if old!=new:changed.append(task_id)
    if task_id not in ('T06','T07','T08'):assert old==new
    else:
        assert all(old.get(k)==new.get(k) for k in ('status','run_id','started_at','ended_at','pid','exit','acked','dispatch_card_sha256','dispatch_recorded_card_path_label','dispatch_write_face_verified'))
        r2=new['rework_attempt_r2'];run_path=KEY/'workers'/r2['task_key']/'run.json';run=json.loads(run_path.read_text(encoding='utf-8'))
        assert all(r2[k]==run[k] for k in ('task_key','run_id','status','exit','ended_at')) and r2['acked'] is True
        assert Path(KEY/new['pm_absorption_evidence']).exists()
        for heading in ('## 结论','## 证据','## 改动清单','## 残留与未验证','## 上下文来源'):
            assert heading in (KEY/new['pm_absorption_evidence']).read_text(encoding='utf-8')
assert changed==['T06','T07','T08']
assert current['T06']['semantic_handoff_verified'] is True and current['T07']['semantic_handoff_verified'] is True and current['T08']['semantic_handoff_verified'] is False
assert current['T09']['deps']==['T03','T04','T08'] and current['T10']['deps']==['T03','T04','T09']
for task_id in ('T05','T09','T10','T11'):assert current[task_id]['status']=='not-queued'
state=(KEY/'pm-state.md').read_text(encoding='utf-8');oldstate=(HERE/'pm-state.before.md').read_text(encoding='utf-8')
assert '- Phase: EXECUTE' in state and '- Phase: EXECUTE' in oldstate
baseline=json.loads((KEY/'evidence/implementation/t08-r2-pm-handoff-20261026/after-inventory.json').read_text(encoding='utf-8'))
actual={p.relative_to(WT).as_posix():sha(p.read_bytes()) for p in WT.rglob('*') if p.is_file()};assert baseline==actual
for source,dest in [('implementation-isolated-dag.json','dag.after.json'),('pm-state.md','pm-state.after.md')]:
    (HERE/dest).write_bytes((KEY/source).read_bytes())
result={'observed_at':datetime.now(timezone.utc).isoformat(),'source':'agent-report','logical_tasks':36,'stages':7,'changed_metadata_tasks':changed,'all_dependencies_scope_ac_vc_commands_preserved':True,'original_runs_preserved':True,'r2_actual_statuses':{k:current[k]['rework_attempt_r2']['status'] for k in changed},'semantic_handoffs':{k:current[k]['semantic_handoff_verified'] for k in changed},'successors_not_queued':True,'mirror_files':len(actual),'mirror_net_changes':[],'phase':'EXECUTE','state_before_sha256':sha((HERE/'pm-state.before.md').read_bytes()),'state_after_sha256':sha((KEY/'pm-state.md').read_bytes()),'dag_before_sha256':sha((HERE/'dag.before.json').read_bytes()),'dag_after_sha256':sha((KEY/'implementation-isolated-dag.json').read_bytes())}
(HERE/'check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(result,ensure_ascii=False,indent=2))
