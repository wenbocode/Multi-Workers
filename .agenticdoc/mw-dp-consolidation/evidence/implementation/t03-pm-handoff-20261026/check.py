"""PM read-only T03 handoff verification; all runtime output stays beside this script."""
from __future__ import annotations
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

E = Path(__file__).resolve().parent
KEY = E.parents[2]
COPY = KEY / 'implementation-worktree'
PKG = COPY / 'packages' / 'multi-workers'
WORKER = E.parent / 'dpc-t03-protocol'

def main() -> int:
    fixture = E / 'fixture'
    for name in ('home', 'temp', 'project'):
        (fixture / name).mkdir(parents=True, exist_ok=True)
    env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'PATHEXT', 'SYSTEMDRIVE') if k in os.environ}
    env.update(HOME=str(fixture / 'home'), USERPROFILE=str(fixture / 'home'), TEMP=str(fixture / 'temp'), TMP=str(fixture / 'temp'), TMPDIR=str(fixture / 'temp'), PYTHONDONTWRITEBYTECODE='1', PYTEST_DISABLE_PLUGIN_AUTOLOAD='1', PYTHONUTF8='1', PYTHONIOENCODING='utf-8')
    observed = {'observed_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'files': [], 'handoff_files': []}
    after = json.loads((WORKER / 'after-manifest.json').read_text(encoding='utf-8'))
    for row in after['files']:
        actual = (COPY / row['path']).read_bytes()
        digest = hashlib.sha256(actual).hexdigest()
        saved = (WORKER / 'after-bytes' / Path(row['path']).name).read_bytes()
        assert digest == row['sha256'] and actual == saved, row['path']
        observed['files'].append({'path': row['path'], 'sha256': digest, 'bytes': len(actual), 'crlf': actual.count(b'\r\n'), 'bare_lf': actual.count(b'\n') - actual.count(b'\r\n')})
    for rel, row in json.loads((WORKER / 'handoff-inventory.json').read_text(encoding='utf-8'))['handoff_files'].items():
        assert hashlib.sha256((COPY / rel).read_bytes()).hexdigest() == row['sha256'], rel
        observed['handoff_files'].append(rel)
    argv = [sys.executable, '-m', 'pytest', '-p', 'no:cacheprovider', '-q', 'test_decide_registry_contract.py', 'test_dp_consolidation_registry.py']
    run = subprocess.run(argv, cwd=PKG, env=env, capture_output=True, text=True, encoding='utf-8', timeout=120)
    (E / 'pm-green.log').write_text(f'cwd={PKG}\nargv={argv!r}\nrc={run.returncode}\nstdout:\n{run.stdout}\nstderr:\n{run.stderr}', encoding='utf-8')
    observed['pytest_rc'] = run.returncode
    child = subprocess.run([sys.executable, str(E / 'probe.py'), str(PKG), str(E)], cwd=fixture / 'project', env=env, capture_output=True, text=True, encoding='utf-8', timeout=60)
    (E / 'probe.log').write_text(f'rc={child.returncode}\n{child.stdout}\n{child.stderr}', encoding='utf-8')
    observed['probe_rc'] = child.returncode
    (E / 'check.json').write_text(json.dumps(observed, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print((E / 'pm-green.log').read_text(encoding='utf-8'))
    print((E / 'probe.log').read_text(encoding='utf-8'))
    return run.returncode or child.returncode

if __name__ == '__main__':
    raise SystemExit(main())
