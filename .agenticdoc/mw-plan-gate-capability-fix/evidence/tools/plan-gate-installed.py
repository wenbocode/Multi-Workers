import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / '.agenticdoc/mw-plan-gate-capability-fix/evidence'
TAG = 'mw-plan-gate-capability-20261124'
COMMIT = '18a2f5b9c5ba7ec5be9a0f5d1c70aba71866e871'
sys.stdout.reconfigure(encoding='utf-8')
env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
version = json.loads(subprocess.check_output([shutil.which('mw.cmd'), 'version', '--json'], cwd=ROOT, env=env))
assert version['global']['release'] == TAG and version['global']['commit'] == COMMIT
assert version['global_extension']['release'] == TAG and version['global_extension']['uses_global_default']
release = Path(version['global']['root'])
manifest = json.loads((release / 'release-manifest.json').read_bytes())
assert manifest['phase'] == 'user-global-installed-and-verified'
for name, checksum in manifest['artifacts'].items():
    assert hashlib.sha256((release / name).read_bytes()).hexdigest() == checksum, name
for name, checksum in manifest['global_install_sha256'].items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest() == checksum, name
for name, checksum in manifest['source_overlay'].items():
    assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == checksum, name
module = release / 'packages/coding-agent/dist/extensions/agent-team-loop/shared/agentic-scripts.js'
subprocess.run(['node', str(ROOT / '.tmp/plan-gate-probe.cjs'), str(module), str(EVIDENCE / 'eight-projects-postinstall.json')], cwd=ROOT, env=env, check=True)
projects = json.loads((EVIDENCE / 'eight-projects-postinstall.json').read_bytes())['projects']
assert len(projects) == 8 and all(row['ok'] for row in projects)
before = json.loads((EVIDENCE / 'eight-projects-before.json').read_bytes())['projects']
assert len(before) == 8 and all(not row['ok'] for row in before)
assert subprocess.check_output([shutil.which('pi.cmd'), '--version'], env=env).decode().strip() == '0.83.0'
check_log = (EVIDENCE / 'root-check.log').read_text(encoding='utf-8-sig')
assert 'check:browser-smoke' in check_log and 'is up to date' in check_log
result = {'release': TAG, 'commit': COMMIT, 'projects_verified': 8, 'old_detection_passes': 0,
          'new_detection_passes': 8, 'global': version['global'], 'global_extension': version['global_extension'],
          'backup': manifest['backup'], 'python_restart_required': False}
(EVIDENCE / 'installed.json').write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
print(json.dumps(result, indent=2, ensure_ascii=False))
