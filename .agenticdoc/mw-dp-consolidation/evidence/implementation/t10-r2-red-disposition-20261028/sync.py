from __future__ import annotations
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = HERE.parents[2]
DAG = KEY / 'implementation-isolated-dag.json'

def fresh(name, obj):
    with (HERE / name).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2)
        handle.write('\n')

if __name__ == '__main__':
    before = json.loads(DAG.read_text(encoding='utf-8'))
    after = copy.deepcopy(before)
    task = next(t for t in after['tasks'] if t['id'] == 'T10')
    assert 'r2_tdd_attempts' not in task
    run_a = json.loads((KEY / 'workers/dpc-t10-r2-test-preparation/run.json').read_text(encoding='utf-8'))
    run_b = json.loads((KEY / 'workers/dpc-t10-r2-product-repair/run.json').read_text(encoding='utf-8'))
    now = datetime.now(timezone.utc).isoformat()
    task['r2_tdd_attempts'] = {
        'stage_a': {'task_key': run_a['task_key'], 'run_id': run_a['run_id'], 'status': run_a['status'], 'acked': True, 'observed_at': now, 'source': 'agent-report', 'completed': ['terminal report absorbed and tool acked', '14 added regression items, actual PM red reproduced'], 'remaining': [], 'blockers': ['TEMP redirection then deletion disclosed; no retroauthorization'], 'evidence': 'evidence/implementation/dpc-t10-lifecycle-state/rework-r2/test-preparation/report.md'},
        'pm_red': {'observed_at': now, 'source': 'agent-report', 'full_runs': ['t10-r2-red-20261028T065500Z', 't10-r2-red-controls-20261028T064853Z'], 'collected': 130, 'failed': 8, 'passed': 122, 'focus_failed': 8, 'focus_passed': 6, 'protection_problems': [], 'evidence': 'evidence/implementation/t10-r2-red-disposition-20261028/report.md'},
        'stage_b': {'task_key': run_b['task_key'], 'run_id': run_b['run_id'], 'status': run_b['status'], 'pid': run_b.get('pid'), 'observed_at': now, 'source': 'agent-report', 'completed': None, 'remaining': None, 'blockers': None, 'card': 'tasks/isolated/T10-r2-product-repair.md', 'dispatch_evidence': 'evidence/implementation/t10-r2-red-disposition-20261028/dispatch-check.json'}
    }
    task['code_status'] = '原产品面R2进行中；原attempt done/exit0/acked保留'
    task['verification_status'] = 'PM两次130items/8F122P、focus8F6P；原116及6新增正控绿，修复后全suite/独立资格待验'
    assert task['semantic_handoff_verified'] is False
    for old, new in zip(before['tasks'], after['tasks']):
        if old['id'] != 'T10':
            assert old == new
        else:
            for k in old:
                if k not in ('code_status', 'verification_status'):
                    assert old[k] == new[k], k
    assert before['stages'] == after['stages']
    fresh('dag-before.json', before)
    DAG.write_text(json.dumps(after, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    fresh('dag-after.json', after)
    fresh('sync.json', {'observed_at': now, 'source': 'agent-report', 'only_T10_metadata_changed': True, 'other_35_equal': True, 'task_count': len(after['tasks']), 'stage_count': len(after['stages']), 'stage_b_status': run_b['status'], 'semantic_handoff': False})
    print('T10 R2 metadata appended; original contracts/history/other35 equal; S2 open')
