from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = HERE.parents[2]
TASK = KEY / 'workers/dpc-t10-r2-product-repair'
CARD = KEY / 'tasks/isolated/T10-r2-product-repair.md'

def write_new(name, value):
    with (HERE / name).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')

if __name__ == '__main__':
    seed = (TASK / 'task.md').read_text(encoding='utf-8')
    expected_sha = hashlib.sha256(CARD.read_bytes()).hexdigest()
    assert 'card_sha256: ' + expected_sha in seed
    line = next(s for s in seed.splitlines() if s.startswith('write_face: '))
    faces = line.removeprefix('write_face: ').split(', ')
    expected = [str((KEY / 'implementation-worktree/packages/multi-workers' / name).relative_to(KEY.parents[1])).replace('\\', '/') for name in ('decision_wire.py', 'decision_lifecycle.py', 'decision_task_state.py')]
    expected.append(str((KEY / 'evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/**').relative_to(KEY.parents[1])).replace('\\', '/'))
    assert faces == expected
    run_path = TASK / 'run.json'
    run = json.loads(run_path.read_text(encoding='utf-8')) if run_path.exists() else None
    for name in ('task.md', 'run.json'):
        p = TASK / name
        if p.exists():
            with (HERE / ('actual-' + name)).open('xb') as handle:
                handle.write(p.read_bytes())
    dag = json.loads((KEY / 'implementation-isolated-dag.json').read_text(encoding='utf-8'))
    task = next(t for t in dag['tasks'] if t['id'] == 'T10')
    write_new('t10-current.json', task)
    write_new('dispatch-check.json', {'observed_at': datetime.now(timezone.utc).isoformat(), 'source': 'agent-report', 'card_sha256': expected_sha, 'faces': faces, 'seed_label': 'tasks/T10-r2-product-repair.md', 'actual_card': CARD.relative_to(KEY).as_posix(), 'run': run, 'completed': None, 'remaining': None, 'blockers': None, 'task_count': len(dag['tasks']), 'stage_count': len(dag['stages'])})
    print(json.dumps({'run': run, 'faces_verified': True, 'original_tasks': len(dag['tasks']), 'original_stages': len(dag['stages'])}, ensure_ascii=False))
