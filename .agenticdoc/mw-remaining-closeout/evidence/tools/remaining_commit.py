import json
from pathlib import Path
import subprocess
import hashlib

root = Path(__file__).resolve().parent.parent
evidence = root / '.agenticdoc/mw-remaining-closeout/evidence'
record = json.loads((evidence / 'scoped-files.json').read_bytes())

def git(*args):
    return subprocess.check_output(['git', '-c', 'core.longpaths=true', *args], cwd=root)

assert not git('diff', '--cached', '--name-only').strip(), 'Foreign staged changes exist'
for name, expected in record['paths'].items():
    assert hashlib.sha256((root / name).read_bytes()).hexdigest() == expected, name
paths = [*record['paths'], 'docs/mw-remaining-review-list-20261124.md']
status = git('status', '--short', '--', *paths)
(evidence / 'precommit-status.txt').write_bytes(status)
subprocess.run(['git', '-c', 'core.longpaths=true', 'add', '--', *paths], cwd=root, check=True)
staged = git('diff', '--cached', '--name-only').decode().splitlines()
assert set(staged) == set(paths), (set(staged) - set(paths), set(paths) - set(staged))
subprocess.run(['git', 'diff', '--cached', '--check'], cwd=root, check=True)
subprocess.run(['git', 'commit', '-m', 'fix(coding-agent): finish pending MW integrations and regressions'], cwd=root, check=True)
commit = git('rev-parse', 'HEAD').decode().strip()
(evidence / 'source-commit.json').write_text(json.dumps({'commit': commit, 'paths': staged}, indent=2), encoding='utf-8')
print('Committed', commit, 'files', len(staged), flush=True)
