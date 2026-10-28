"""Independent, bounded PM verification; no production writes."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
PKG = ROOT / 'packages' / 'multi-workers'
FILES = ['decision_history.py', 'test_decision_history.py', 'decision_monitor.py', 'test_decision_monitor.py', 'decide_archive.py', 'decide_signoff.py']
def hashes():
    return {name: hashlib.sha256((PKG / name).read_bytes()).hexdigest() for name in FILES}
meta = {'started_at': datetime.now(timezone.utc).isoformat(), 'before': hashes()}
cmd = [sys.executable, '-m', 'pytest', 'test_decision_history.py', 'test_decide_archive.py', 'test_decide_signoff.py', 'test_decision_monitor.py', '-q']
with (OUT / 'pytest-current.log').open('w', encoding='utf-8') as log:
    result = subprocess.run(cmd, cwd=PKG, stdout=log, stderr=subprocess.STDOUT, timeout=180)
meta.update(rc=result.returncode, command=cmd, cwd=str(PKG), after=hashes(), ended_at=datetime.now(timezone.utc).isoformat())
(OUT / 'result.json').write_text(json.dumps(meta, indent=2), encoding='utf-8')
print((OUT / 'pytest-current.log').read_text(encoding='utf-8'))
print(json.dumps(meta, indent=2))
sys.exit(result.returncode)
