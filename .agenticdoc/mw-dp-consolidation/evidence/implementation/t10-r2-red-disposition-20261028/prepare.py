from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = HERE.parents[2]
ROOT = KEY.parents[1]
MIRROR = KEY / 'implementation-worktree'
PKG = MIRROR / 'packages/multi-workers'
CARD = KEY / 'tasks/isolated/T10-r2-product-repair.md'
NAMES = ('decision_wire.py', 'decision_lifecycle.py', 'decision_task_state.py', 'test_decision_context_lifecycle.py', 'test_decision_task_state.py')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def dump(name, value):
    target = HERE / name
    with target.open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')

if __name__ == '__main__':
    snapshot = {p.relative_to(MIRROR).as_posix(): sha(p) for p in sorted(MIRROR.rglob('*')) if p.is_file()}
    original = KEY / 'evidence/implementation/t10-r2-pre-dispatch-20261028'
    old = json.loads((original / 'mirror-before.json').read_text(encoding='utf-8'))
    # Prior snapshot shape is inspected separately; all raw manifests retained.
    dump('mirror-before.json', snapshot)
    dump('pyc-before.json', {k: v for k, v in snapshot.items() if k.endswith('.pyc')})
    products = {}
    for name in NAMES:
        p = PKG / name
        target = HERE / 'before-bytes' / name
        target.parent.mkdir(exist_ok=True)
        with target.open('xb') as handle:
            handle.write(p.read_bytes())
        products[name] = {'sha256': sha(p), 'bytes': p.stat().st_size}
    dump('products-before.json', products)
    for name in ('implementation-isolated-dag.json', 'pm-state.md'):
        with (HERE / (name + '.before')).open('xb') as handle:
            handle.write((KEY / name).read_bytes())
    red = KEY / 'evidence/implementation/dpc-t10-lifecycle-state/rework-r2/pm-controlled/runs/t10-r2-red-controls-20261028T064853Z/report.json'
    result = json.loads(red.read_text(encoding='utf-8'))
    assert result['collection']['count'] == 130
    assert result['pytest']['counts'] == {'failed': 8, 'passed': 122}
    assert result['problems'] == []
    assert len(snapshot) == 1891
    assert len([k for k in snapshot if k.endswith('.pyc')]) == 14
    dump('check.json', {'observed_at': datetime.now(timezone.utc).isoformat(), 'source': 'agent-report', 'mirror_files': len(snapshot), 'products': products, 'card_sha256': sha(CARD), 'card': CARD.relative_to(ROOT).as_posix(), 'red_report': red.relative_to(ROOT).as_posix(), 'red_report_sha256': sha(red), 'semantic_handoff_verified': False, 'PM_product_EOF_read': False, 'note': 'Actual red runs and harness reviewed; PM personally reading all products/tests to EOF remains outstanding before full qualification.'})
    print('fresh snapshot saved; red 8F122P/130; no semantic release')
