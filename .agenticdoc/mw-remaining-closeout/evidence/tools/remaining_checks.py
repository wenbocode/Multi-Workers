import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding='utf-8')
EVIDENCE = ROOT / '.agenticdoc/mw-remaining-closeout/evidence'
EVIDENCE.mkdir(parents=True, exist_ok=True)

def paths():
    raw = subprocess.check_output(['git', '-c', 'core.longpaths=true', 'ls-files', '-m', '-o', '--exclude-standard', '--', 'packages', 'AGENTS.md', 'biome.json'], cwd=ROOT)
    return sorted(set(p for p in raw.decode().splitlines() if '/dist/' not in p and '/_r8_tmp_exact/' not in p and '/fixtures/' not in p and '/.agenticdoc/' not in p and '/.tmp/' not in p))

def run(name, command, cwd):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    start = time.time()
    result = subprocess.run(command, cwd=cwd, env=env, capture_output=True, encoding='utf-8', errors='replace')
    log = EVIDENCE / (name + '.log')
    log.write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
    record = {'command': command, 'cwd': str(cwd), 'rc': result.returncode, 'seconds': round(time.time()-start, 2), 'log': str(log), 'at': datetime.now(timezone.utc).isoformat()}
    (EVIDENCE / (name + '.json')).write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record), flush=True)
    if result.returncode:
        print('\n'.join((result.stdout + result.stderr).splitlines()[-100:]), flush=True)
    else:
        print('\n'.join(result.stdout.splitlines()[-5:]), flush=True)
    return result.returncode

parser = argparse.ArgumentParser()
parser.add_argument('suite', choices=['inventory', 'typescript', 'python', 'framework', 'duty', 'template'])
args = parser.parse_args()
files = paths()
if args.suite == 'inventory':
    record = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files if (ROOT / p).is_file()}
    (EVIDENCE / 'input-source-sha256.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    print(json.dumps(record, indent=2))
    sys.exit(0)
if args.suite == 'typescript':
    tests = [p.removeprefix('packages/coding-agent/') for p in files if p.startswith('packages/coding-agent/test/') and p.endswith('.test.ts')]
    command = ['node', '../../node_modules/vitest/dist/cli.js', '--run', '--no-file-parallelism', '--cache=false', *tests]
    sys.exit(run('typescript', command, ROOT / 'packages/coding-agent'))
if args.suite == 'python':
    tests = [p for p in files if p.startswith('packages/multi-workers/') and Path(p).name.startswith('test_') and p.endswith('.py') and '/templates/' not in p]
    base = ROOT / '.tmp' / ('rcp-' + uuid.uuid4().hex[:8])
    assert not base.exists()
    command = [sys.executable, '-X', 'utf8', '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', '--tb=short', '--basetemp', str(base), *tests]
    sys.exit(run('python', command, ROOT))
if args.suite == 'framework':
    framework = ROOT / 'packages/multi-workers/.tmp/agentic-task'
    sys.exit(run('framework', [sys.executable, '-X', 'utf8', '-B', '-m', 'pytest', '-q', '-p', 'no:cacheprovider', 'scripts/test_advance_phase.py'], framework))
if args.suite == 'template':
    sys.exit(run('template', [sys.executable, '-X', 'utf8', '-B', '-m', 'unittest', 'discover', '-s', 'packages/multi-workers/templates/ue-continue-develop-frame/tests', '-v'], ROOT))
sys.exit(run('duty', ['node', '--experimental-strip-types', '--test', 'packages/multi-workers/test_duty_followup.ts'], ROOT))
