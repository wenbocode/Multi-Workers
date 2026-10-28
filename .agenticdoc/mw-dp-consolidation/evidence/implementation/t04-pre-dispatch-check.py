"""PM source-read-only handoff snapshot; no generator or product test runs."""
from pathlib import Path
from datetime import datetime, timezone
import hashlib
import json
import os
import subprocess

KEY = Path(__file__).resolve().parents[2]
ROOT = KEY.parents[1]
WT = KEY / 'implementation-worktree'
OUT = KEY / 'evidence/implementation/t04-pre-dispatch-20261026'
assert not OUT.exists(), 'Do not overwrite a previous baseline'
DAG = json.loads((KEY / 'implementation-isolated-dag.json').read_text(encoding='utf-8'))
TASK = next(t for t in DAG['tasks'] if t['id'] == 'T04')
CHECK = json.loads((KEY / 'evidence/implementation/t03-r3-pm-handoff-20261026/check.json').read_text(encoding='utf-8'))
def sha(data):
    return hashlib.sha256(data).hexdigest()
for row in CHECK['files']:
    assert sha((WT / row['path']).read_bytes()) == row['sha256']
assert all(row['rc'] == 0 for row in CHECK['tests'])
OUT.mkdir()
records = []
for face in TASK['product_write_face']:
    path = ROOT / face
    relative = path.relative_to(WT)
    assert path.exists() and not path.is_symlink()
    live = ROOT / relative
    assert not os.path.samefile(path, live)
    data = path.read_bytes()
    dest = OUT / 'before-bytes' / relative
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    assert dest.read_bytes() == data
    original = live.read_bytes()
    saved = OUT / 'live-before-bytes' / relative
    saved.parent.mkdir(parents=True, exist_ok=True)
    saved.write_bytes(original)
    diff = subprocess.run(['git', 'diff', '--', relative.as_posix()], cwd=ROOT, capture_output=True)
    assert diff.returncode == 0
    diffpath = OUT / 'live-existing-diff' / (relative.as_posix() + '.diff')
    diffpath.parent.mkdir(parents=True, exist_ok=True)
    diffpath.write_bytes(diff.stdout)
    records.append({'path': relative.as_posix(), 'sha256': sha(data), 'bytes': len(data), 'crlf': data.count(b'\r\n'), 'bare_lf': data.count(b'\n')-data.count(b'\r\n'), 'live_sha256': sha(original), 'samefile': False})
inventory = {}
for path in WT.rglob('*'):
    if path.is_file():
        assert not path.is_symlink()
        inventory[path.relative_to(WT).as_posix()] = sha(path.read_bytes())
(OUT / 'mirror-inventory.json').write_text(json.dumps(inventory, indent=2) + '\n', encoding='utf-8')
status = subprocess.run(['git', 'status', '--short'], cwd=ROOT, capture_output=True)
assert status.returncode == 0
(OUT / 'live-git-status.txt').write_bytes(status.stdout)
card = (KEY / TASK['card']).read_bytes()
(OUT / 'card-before.md').write_bytes(card)
result = {'observed_at': datetime.now(timezone.utc).isoformat(), 'card': TASK['card'], 'card_sha256': sha(card), 'files': records, 'mirror_file_count': len(inventory), 't03_handoff_matches': True, 'product_writes': False, 'product_tests_run': False, 'generation_run': False, 'manual_writer_absence_proven': False}
(OUT / 'check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
