from __future__ import annotations
import copy
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = HERE.parents[2]
ROOT = KEY.parents[1]
DAG = KEY / 'implementation-isolated-dag.json'
CARD = KEY / 'tasks/isolated/T10-r2-verification-preparation.md'
C = KEY / 'workers/dpc-t10-r2-verification-preparation'
B = KEY / 'workers/dpc-t10-r2-product-repair'

def save(name, obj):
    with (HERE / name).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(obj, handle, ensure_ascii=False, indent=2)
        handle.write('\n')

if __name__ == '__main__':
    run_b = json.loads((B / 'run.json').read_text(encoding='utf-8'))
    run_c = json.loads((C / 'run.json').read_text(encoding='utf-8'))
    seed = (C / 'task.md').read_text(encoding='utf-8')
    card_sha = hashlib.sha256(CARD.read_bytes()).hexdigest()
    assert 'card_sha256: ' + card_sha in seed
    expected_face = (KEY / 'evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation/**').relative_to(ROOT).as_posix()
    assert next(line for line in seed.splitlines() if line.startswith('write_face: ')) == 'write_face: ' + expected_face
    before = json.loads(DAG.read_text(encoding='utf-8'))
    after = copy.deepcopy(before)
    task = next(t for t in after['tasks'] if t['id'] == 'T10')
    now = datetime.now(timezone.utc).isoformat()
    attempt = task['r2_tdd_attempts']['stage_b']
    old_b = copy.deepcopy(attempt)
    attempt.update({'status': run_b['status'], 'exit': run_b['exit'], 'ended_at': run_b['ended_at'], 'acked': True, 'observed_at': now, 'source': 'agent-report', 'previous_observation': old_b, 'completed': ['product report and diffs fully absorbed, terminal tool acked', 'only2 authorized products changed; tests/live/14pyc/744 old evidence unchanged'], 'remaining': ['assigned suites/focus/real concurrency/replay and current full EOF qualification'], 'blockers': ['machine shell-target write gaps retained; not recovery-complete', 'product correctness unverified'], 'pm_disposition_evidence': 'evidence/implementation/t10-r2-product-absorption-20261028/report.md', 'semantic_handoff_verified': False})
    assert 'stage_c' not in task['r2_tdd_attempts']
    task['r2_tdd_attempts']['stage_c'] = {'task_key': run_c['task_key'], 'run_id': run_c['run_id'], 'status': run_c['status'], 'pid': run_c.get('pid'), 'observed_at': now, 'source': 'agent-report', 'completed': None, 'remaining': None, 'blockers': None, 'card': CARD.relative_to(KEY).as_posix(), 'card_sha256': card_sha, 'evidence': 'evidence/implementation/dpc-t10-lifecycle-state/rework-r2/verification-preparation', 'write_face_verified': True}
    task['code_status'] = 'R2阶段B局部产品交付未验证；原needs-clarification/exit2/acked保持'
    task['verification_status'] = '两次真red8F122P后产品交付，阶段C独立复验脚本/并发重放边界准备中；未green/handoff'
    assert task['semantic_handoff_verified'] is False
    for old, new in zip(before['tasks'], after['tasks']):
        if old['id'] != 'T10':
            assert old == new
        else:
            for k in old:
                if k not in ('r2_tdd_attempts', 'code_status', 'verification_status'):
                    assert old[k] == new[k], k
    assert before['stages'] == after['stages']
    save('dag-before.json', before)
    DAG.write_text(json.dumps(after, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    save('dag-after.json', after)
    for name in ('task.md', 'run.json'):
        with (HERE / ('stage-c-actual-' + name)).open('xb') as handle:
            handle.write((C / name).read_bytes())
    save('sync.json', {'observed_at': now, 'source': 'agent-report', 'run_b': run_b, 'run_c': run_c, 'original_36_tasks_7_stages': True, 'other35_unchanged': True, 'original_contracts_unchanged': True, 'card_sha256': card_sha, 'single_face': expected_face, 'semantic_handoff': False})
    print(json.dumps({'run_c': run_c, 'stage_b': run_b['status'], 'stage_b_exit': run_b['exit'], 'one_face_verified': True, 'other35_equal': True}, ensure_ascii=False))
