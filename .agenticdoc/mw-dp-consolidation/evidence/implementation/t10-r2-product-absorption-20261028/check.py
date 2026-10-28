from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = HERE.parents[2]
ROOT = KEY.parents[1]
WORKTREE = KEY / 'implementation-worktree'
PKG = WORKTREE / 'packages/multi-workers'
OLD = KEY / 'evidence/implementation/t10-r2-red-disposition-20261028'
DELIVERY = KEY / 'evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair'
TASK = KEY / 'workers/dpc-t10-r2-product-repair'
NAMES = ('decision_wire.py', 'decision_lifecycle.py', 'decision_task_state.py', 'test_decision_context_lifecycle.py', 'test_decision_task_state.py')
EXPECTED = {'decision_wire.py': '429201ace7028968ae18cfbcc33dbf5aa0d2fa11b8f5d2dd7604cae0dec4e7dc', 'decision_lifecycle.py': '73d0ae2efda3879668b3cf84d11f32809c6d00f76da13c3b8d065f87d4c87bb5', 'decision_task_state.py': 'b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d', 'test_decision_context_lifecycle.py': '1bca28c56c7ab039de5c3a91638fd20c1e2fa89f4a1ec996169cfd933c1e6ae9', 'test_decision_task_state.py': '30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f'}

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def save(name, value):
    with (HERE / name).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')

if __name__ == '__main__':
    before = json.loads((OLD / 'mirror-before.json').read_text(encoding='utf-8'))
    mirror = {p.relative_to(WORKTREE).as_posix(): sha(p) for p in sorted(WORKTREE.rglob('*')) if p.is_file()}
    changed = sorted(k for k in before.keys() & mirror.keys() if before[k] != mirror[k])
    assert changed == ['packages/multi-workers/decision_lifecycle.py', 'packages/multi-workers/decision_wire.py']
    assert before.keys() == mirror.keys() and len(mirror) == 1891
    pyc = {k: v for k, v in mirror.items() if k.endswith('.pyc')}
    assert pyc == json.loads((OLD / 'pyc-before.json').read_text(encoding='utf-8'))
    assert len(pyc) == 14
    actual = {name: sha(PKG / name) for name in NAMES}
    assert actual == EXPECTED
    for name in NAMES[:3]:
        assert sha(DELIVERY / 'after-bytes' / name) == actual[name]
        assert sha(DELIVERY / 'before-bytes' / name) == sha(OLD / 'before-bytes' / name)
    protected = json.loads((KEY / 'evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-controlled/runs/t10-r2-red-controls-20261028T064853Z/report.json').read_text(encoding='utf-8'))['protection']
    live = {name: sha(ROOT / 'packages/multi-workers' / name) for name in NAMES}
    assert live == protected['live']['after']
    history = {}
    for rel, digest in json.loads((KEY / 'evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-controlled/runs/t10-r2-red-controls-20261028T064853Z/old-evidence.before.json').read_text(encoding='utf-8')).items():
        history[rel] = sha(KEY / rel)
        assert history[rel] == digest, rel
    run = json.loads((TASK / 'run.json').read_text(encoding='utf-8'))
    assert run['status'] == 'needs-clarification' and run['exit'] == 2
    seed = (TASK / 'task.md').read_text(encoding='utf-8')
    assert 'product-repair/**' in seed
    declared = [line.split('`')[1] for line in (DELIVERY / 'report.md').read_text(encoding='utf-8').splitlines() if line.startswith('| `.agenticdoc/')]
    evidence = {p.relative_to(ROOT).as_posix(): sha(p) for p in sorted(DELIVERY.rglob('*')) if p.is_file()}
    outside = [p for p in evidence if not p.startswith(DELIVERY.relative_to(ROOT).as_posix() + '/')]
    assert outside == []
    trace = (TASK / 'trace.log').read_text(encoding='utf-8')
    machine = [line for line in trace.splitlines() if line.startswith('[WRITE_FILE]') or line.startswith('[WRITE_UNRESOLVED]')]
    with (HERE / 'machine-write-lines.txt').open('x', encoding='utf-8') as handle:
        handle.write('\n'.join(machine) + '\n')
    save('mirror-before-verification.json', mirror)
    save('pyc-before-verification.json', pyc)
    save('delivery-evidence-sha256.json', evidence)
    save('check.json', {'observed_at': datetime.now(timezone.utc).isoformat(), 'source': 'agent-report', 'run': run, 'acked_by_tool': True, 'mirror_files': len(mirror), 'changed_products': changed, 'products_sha256': actual, 'pyc_unchanged': True, 'live_unchanged': True, 'old_evidence_unchanged_count': len(history), 'declared_paths': declared, 'delivery_files': len(evidence), 'write_face_inside_original_envelope': True, 'machine_write_gap_remains': True, 'PM_full_source_EOF_read': False, 'semantic_handoff_verified': False, 'note': 'Byte/scope qualification only; original exit2 and unrecorded shell-target history retained. No product import or test run in this checker.'})
    print('scope snapshot: only 2 approved products changed; tests/live/14pyc/744 old evidence unchanged; original exit2 retained')
