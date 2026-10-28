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
CARD = KEY / 'tasks/isolated/T10-r2-replay-repair.md'
D = KEY / 'workers/dpc-t10-r2-replay-repair'
C = KEY / 'workers/dpc-t10-r2-verification-preparation'


def save(name, value):
    with (HERE / name).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


if __name__ == '__main__':
    run = json.loads((D / 'run.json').read_text(encoding='utf-8'))
    seed = (D / 'task.md').read_text(encoding='utf-8')
    digest = hashlib.sha256(CARD.read_bytes()).hexdigest()
    assert 'card_sha256: ' + digest in seed
    header = next(line for line in seed.splitlines() if line.startswith('write_face: '))
    faces = [part.strip() for part in header.split(': ', 1)[1].split(',')]
    expected = ['.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/' + name for name in ('decision_wire.py', 'decision_lifecycle.py', 'decision_task_state.py')] + ['.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/replay-repair/**']
    assert sorted(faces) == sorted(expected)
    check = json.loads((HERE / 'check.json').read_text(encoding='utf-8'))
    before = json.loads(DAG.read_text(encoding='utf-8'))
    after = copy.deepcopy(before)
    task = next(t for t in after['tasks'] if t['id'] == 'T10')
    previous_c = copy.deepcopy(task['r2_tdd_attempts']['stage_c'])
    now = datetime.now(timezone.utc).isoformat()
    task['r2_tdd_attempts']['stage_c'].update({'previous_observation': previous_c, 'status': check['stage_c_run']['status'], 'exit': 2, 'ended_at': check['stage_c_run']['ended_at'], 'acked': True, 'source': 'agent-report', 'observed_at': now, 'completed': ['static preparation absorbed and tool acked', '13 delivery digests independently verified'], 'remaining': ['PM full EOF and execution of entire new C runner/boundary suite'], 'blockers': ['2 JSON machine-write gaps retained; no formal recovery-complete'], 'semantic_handoff_verified': False})
    assert 'stage_d' not in task['r2_tdd_attempts']
    task['r2_tdd_attempts']['stage_d'] = {'task_key': run['task_key'], 'run_id': run['run_id'], 'status': run['status'], 'pid': run.get('pid'), 'source': 'agent-report', 'observed_at': now, 'completed': None, 'remaining': None, 'blockers': None, 'card': CARD.relative_to(KEY).as_posix(), 'card_sha256': digest, 'write_face_verified': True}
    task['r2_tdd_attempts']['pm_postfix_observation'] = {'source': 'agent-report', 'observed_at': now, 'assigned_runs': check['green_runs'], 'replay_probe': check['replay'], 'evidence': 'evidence/implementation/t10-r2-green-replay-disposition-20261028/check.json', 'PM_current_five_files_EOF': True, 'full_semantic_handoff_verified': False}
    task['code_status'] = '阶段B原130套件绿后独立AC052重放真1红；阶段D原面修复已派'
    task['verification_status'] = 'PM双130P/focus双14P；AC052独立真1F；C全部16边界仍未执行/handofffalse'
    for old, new in zip(before['tasks'], after['tasks']):
        if old['id'] != 'T10':
            assert old == new
        else:
            for name in old:
                if name not in ('r2_tdd_attempts', 'code_status', 'verification_status'):
                    assert old[name] == new[name], name
    assert before['stages'] == after['stages']
    save('dag-before.json', before)
    DAG.write_text(json.dumps(after, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    save('dag-after.json', after)
    for name in ('task.md', 'run.json'):
        with (HERE / ('stage-d-actual-' + name)).open('xb') as handle:
            handle.write((D / name).read_bytes())
    save('sync.json', {'observed_at': now, 'source': 'agent-report', 'stage_d_run': run, 'card_sha256': digest, 'four_faces': faces, 'other35_equal': True, '36_tasks_7_stages_unchanged': True, 'original_contracts_unchanged': True, 'semantic_handoff': False})
    print(json.dumps({'stage_d': run, 'faces': len(faces), 'other35_equal': True}, ensure_ascii=False))
