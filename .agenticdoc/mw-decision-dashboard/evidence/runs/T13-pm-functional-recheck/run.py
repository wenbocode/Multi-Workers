from __future__ import annotations
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

root = Path(__file__).resolve().parents[5]
pkg = root / 'packages' / 'multi-workers'
run = Path(__file__).resolve().parent
files = ['decision_monitor.py', 'decision_playground.py', 'decision_dashboard.html', 'decision_dashboard.js', 'decision_dashboard.css', 'mw.py', 'test_decision_dashboard_playground.py', 'test_decision_dashboard_assets.py', 'test_decision_monitor_cli.py']
def hashes():
    return {name: hashlib.sha256((pkg / name).read_bytes()).hexdigest() for name in files}
before = hashes()
argv = [sys.executable, '-m', 'pytest', 'test_decision_dashboard_playground.py', 'test_decision_playground.py', 'test_decision_dashboard_assets.py', 'test_decision_monitor.py', 'test_decision_monitor_cli.py', '-q']
with tempfile.TemporaryDirectory(prefix='pm-dashboard-recheck-') as home:
    env = {k: v for k, v in os.environ.items() if not k.upper().endswith(('_API_KEY', '_TOKEN', '_SECRET', '_PASSWORD', '_AUTH', '_KEY'))}
    env.update(HOME=home, USERPROFILE=home, PI_CODING_AGENT_DIR=str(Path(home) / 'pi'))
    start = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with (run / 'pytest.log').open('w', encoding='utf-8') as log:
        log.write(json.dumps({'cwd': str(pkg), 'argv': argv, 'UTC_START': start, 'DEPS_BEFORE': before, 'isolation': 'temporary HOME/USERPROFILE/PI_CODING_AGENT_DIR; credential suffix environment removed'}, ensure_ascii=False) + '\n')
        log.flush()
        proc = subprocess.run(argv, cwd=pkg, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=240)
        after = hashes()
        result = {'rc': proc.returncode, 'UTC_END': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'DEPS_AFTER': after, 'unchanged': before == after}
        log.write('\n' + json.dumps(result) + '\n')
    (run / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result))
    sys.exit(proc.returncode)
