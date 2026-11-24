"""Install the exact published sign-off tree while preserving the development clone."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / '.mw/agentictask-signoff-review'
DEV = ROOT / 'packages/multi-workers/.tmp/agentic-task'
COMMIT = '84bbc2788c9555b350821056f206a698dc6db375'
EVIDENCE = ROOT / '.agenticdoc/mw-remaining-closeout/evidence'
PROJECTS = [Path(row['project']) for row in json.loads((ROOT / '.agenticdoc/agentictask-df8ecf6-rollout/evidence/installed.json').read_bytes())['projects']]
ENV = dict(os.environ, GIT_OPTIONAL_LOCKS='0', PYTHONDONTWRITEBYTECODE='1', PYTHONUTF8='1')

def git(repo, *args):
    return subprocess.check_output(['git', '-c', 'core.longpaths=true', '-c', 'safe.directory=' + repo.as_posix(), '-C', str(repo), *args], env=ENV).decode('utf-8').strip()

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def snapshot_dev():
    files = git(DEV, 'ls-files').splitlines()
    return {'head': git(DEV, 'rev-parse', 'HEAD'), 'index': digest(DEV / '.git/index'),
            'files': {name: digest(DEV / name) for name in files},
            'diff': git(DEV, 'diff', '--binary')}

def save(name, value):
    (EVIDENCE / name).write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')

assert git(SOURCE, 'rev-parse', 'HEAD') == COMMIT
assert not git(SOURCE, 'status', '--porcelain')
assert git(SOURCE, 'diff', 'dd0e6f3', COMMIT) == ''
source_files = git(SOURCE, 'ls-files').splitlines()
expected = {name: digest(SOURCE / name) for name in source_files}
before = snapshot_dev()
save('framework-development-before.json', before)
results = []

for project in PROJECTS:
    assert project.is_dir(), project
    backup = project / '.mw/agentictask-signoff-rollout-20261124'
    assert not backup.exists(), backup
    backup.mkdir(parents=True)
    skill = project / '.agents/skills/agentic-task'
    claude = project / '.claude'
    manifest = project / '.agentic-framework'
    old = {'project': str(project), 'old_skill_head': git(skill, 'rev-parse', 'HEAD'),
           'old_skill_status': git(skill, 'status', '--porcelain'),
           'old_skill_target': str(skill.resolve()), 'junction': skill.is_junction()}
    (backup / 'before.json').write_text(json.dumps(old, indent=2), encoding='utf-8')
    if manifest.exists():
        shutil.copyfile(manifest, backup / 'agentic-framework-before')
    # Rename the junction itself. Its development target is never traversed or moved.
    assert skill.absolute().is_relative_to(project.absolute() / '.agents/skills')
    os.rename(skill, backup / 'skill-before')
    for name in ('commands', 'agents', 'skills', 'scripts'):
        target = claude / name
        if target.exists():
            assert target.absolute().is_relative_to(project.absolute() / '.claude')
            os.rename(target, backup / ('claude-' + name + '-before'))
    subprocess.run(['git', '-c', 'safe.directory=' + SOURCE.as_posix(), 'clone', '--no-hardlinks', '--quiet', str(SOURCE), str(skill)], check=True, env=ENV)
    subprocess.run(['git', '-C', str(skill), 'remote', 'set-url', 'origin', 'https://github.com/wenbocode/AgenticTask.git'], check=True, env=ENV)
    # The skill is already cloned and pinned above. Avoid an unpinned pull during adapter copy.
    command = [sys.executable, '-X', 'utf8', '-B', str(SOURCE / 'install.py'), str(project), '--skip-codex']
    run = subprocess.run(command, capture_output=True, encoding='utf-8', errors='replace', env=ENV)
    (backup / 'install.log').write_text(run.stdout + run.stderr, encoding='utf-8')
    if run.returncode:
        raise RuntimeError(f'Adapter installation failed; originals retained in {backup}: {run.stderr}')
    assert git(skill, 'rev-parse', 'HEAD') == COMMIT
    assert not git(skill, 'status', '--porcelain')
    assert all(digest(skill / name) == sha for name, sha in expected.items()), project
    claude_count = 0
    for directory in ('commands', 'agents', 'skills', 'scripts'):
        for file in (SOURCE / 'claude' / directory).rglob('*'):
            if file.is_file() and '__pycache__' not in file.parts:
                assert digest(claude / file.relative_to(SOURCE / 'claude')) == digest(file), file
                claude_count += 1
    assert 'commit=84bbc27' in manifest.read_text(encoding='utf-8')
    result = {'project': str(project), 'skill_commit': COMMIT, 'claude_commit': '84bbc27',
              'skill_files_checked': len(expected), 'claude_files_checked': claude_count,
              'claude_advance_sha256': digest(claude / 'scripts/advance_phase.py'),
              'backup': str(backup), 'verified': True}
    results.append(result)
    save('framework-installed.json', {'commit': COMMIT, 'source': str(SOURCE), 'projects': results, 'development_preserved': False})
    print('Verified ' + str(project), flush=True)

assert snapshot_dev() == before, 'Development clone changed during rollout'
assert not git(SOURCE, 'status', '--porcelain'), 'Installer changed the source clone'
save('framework-installed.json', {'commit': COMMIT, 'review_commit': 'dd0e6f36cb3d5183b672b0c35aa46592c3700ca7',
     'identical_remote_tree': True, 'source': str(SOURCE), 'projects': results, 'development_preserved': True})
print('Verified all eight projects; development HEAD, index, tracked bytes and diff preserved', flush=True)
