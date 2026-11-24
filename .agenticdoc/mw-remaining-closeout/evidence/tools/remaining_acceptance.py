"""Reconcile frozen source, real regression logs, and installed runtime/adapters."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE = ROOT / '.agenticdoc/mw-remaining-closeout/evidence'
RELEASE = Path.home() / '.local/share/multi-workers/releases/mw-remaining-closeout-20261124'
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS='0', PYTHONDONTWRITEBYTECODE='1')
sys.stdout.reconfigure(encoding='utf-8')

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(repo, *args):
    return subprocess.check_output(['git', '-c', 'core.longpaths=true', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo), *args], env=ENV)

source = json.loads((EVIDENCE / 'scoped-files.json').read_bytes())
commit = json.loads((EVIDENCE / 'source-commit.json').read_bytes())['commit']
for name, sha in source['paths'].items():
    assert digest(ROOT / name) == sha and digest(RELEASE / name) == sha, name
    assert git(ROOT, 'show', f'{commit}:{name}').replace(b'\r\n', b'\n') == (ROOT / name).read_bytes().replace(b'\r\n', b'\n'), name

for suite, expected in [('python', '983 passed'), ('typescript', '436 passed'), ('duty', 'tests 30'), ('framework', '54 passed'), ('template', 'Ran 10 tests')]:
    record = json.loads((EVIDENCE / (suite + '.json')).read_bytes())
    assert record['rc'] == 0, suite
    assert expected in Path(record['log']).read_text(encoding='utf-8'), suite
check_log = (EVIDENCE / 'root-check-final.log').read_text(encoding='utf-8-sig')
assert 'check:browser-smoke' in check_log and 'is up to date' in check_log
assert 'error ' not in check_log.lower()

manifest = json.loads((RELEASE / 'release-manifest.json').read_bytes())
assert manifest['phase'] == 'user-global-installed-and-verified'
assert manifest['commit'] == commit
for name, sha in manifest['artifacts'].items():
    assert digest(RELEASE / name) == sha, name
for name, sha in manifest['global_install_sha256'].items():
    assert digest(Path(name)) == sha, name
versions = json.loads(subprocess.check_output([shutil.which('mw.cmd'), 'version', '--json'], cwd=ROOT, env=ENV))
assert versions['global']['commit'] == commit
assert versions['global_extension']['uses_global_default'] is True
assert versions['backend']['observed'] is True and versions['backend']['uses_global_default'] is True
assert subprocess.check_output([shutil.which('pi.cmd'), '--version'], env=ENV).decode().strip() == '0.83.0'

framework = json.loads((EVIDENCE / 'framework-installed.json').read_bytes())
assert framework['development_preserved'] is True and len(framework['projects']) == 8
source_repo = Path(framework['source'])
assert git(source_repo, 'diff', 'dd0e6f3', framework['commit']) == b''
tracked = git(source_repo, 'ls-files').decode().splitlines()
for row in framework['projects']:
    project = Path(row['project'])
    skill = project / '.agents/skills/agentic-task'
    assert git(skill, 'rev-parse', 'HEAD').decode().strip() == framework['commit'], project
    assert git(skill, 'status', '--porcelain') == b'', project
    for name in tracked:
        assert digest(skill / name) == digest(source_repo / name), (project, name)
    for directory in ('commands', 'agents', 'skills', 'scripts'):
        for file in (source_repo / 'claude' / directory).rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts:
                assert digest(project / '.claude' / file.relative_to(source_repo / 'claude')) == digest(file), file

dev = ROOT / 'packages/multi-workers/.tmp/agentic-task'
before = json.loads((EVIDENCE / 'framework-development-before.json').read_bytes())
assert git(dev, 'rev-parse', 'HEAD').decode().strip() == before['head']
assert digest(dev / '.git/index') == before['index']
assert all(digest(dev / name) == sha for name, sha in before['files'].items())
assert git(dev, 'diff', '--binary').decode().strip() == before['diff']
result = {'source_commit': commit, 'source_files': len(source['paths']), 'regression_tests': 1513,
          'framework_commit': framework['commit'], 'projects_verified': 8, 'development_preserved': True,
          'global': versions['global'], 'global_extension': versions['global_extension'], 'backend': versions['backend'],
          'self_verification_only': True}
(EVIDENCE / 'final-reconciliation.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
