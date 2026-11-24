"""Install the standalone module package without overwriting module design or policies."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

PACKAGE = Path(__file__).resolve().parent / 'package'


def install(target, name, sources):
    target = target.resolve()
    if (target / 'agent').exists():
        raise ValueError('agent/ already exists; refusing to overwrite module data or approvals')
    for source in sources:
        if not (target / source).resolve().is_relative_to(target):
            raise ValueError('source-root escapes module')
        if not (target / source).is_dir():
            raise ValueError('source-root directory missing: ' + source)
    target.mkdir(parents=True, exist_ok=True)
    shutil.copytree(PACKAGE / 'agent', target / 'agent', ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copyfile(PACKAGE.parent / 'MW-TASK.md', target / 'agent/MW-TASK.md')
    for file in ['GOAL.md', 'DESIGN.md']:
        if not (target / file).exists():
            (target / file).write_text((PACKAGE / file).read_text(encoding='utf-8').replace('{{MODULE}}', name), encoding='utf-8')
    entry = (PACKAGE / 'AGENTS.md').read_text(encoding='utf-8')
    existing = target / 'AGENTS.md'
    prefix = existing.read_bytes() if existing.exists() else b''
    if b'<!-- module-agent:start -->' not in prefix:
        existing.write_bytes(prefix + (b'\n\n' if prefix else b'') + entry.encode('utf-8'))
    config = json.loads((target / 'agent/module.json').read_text(encoding='utf-8'))
    config.update(module=name, source_roots=sources)
    (target / 'agent/module.json').write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    command = [sys.executable, '-B', str(target / 'agent/catalog.py'), '--write']
    result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
    catalog = 'generated' if not result.returncode else 'pending: ' + (result.stdout + result.stderr).strip()
    return {'status': 'installed_draft', 'module': str(target), 'catalog': catalog,
            'next': 'Generate agent/catalog.json terms/testcases/gates and DESIGN.md from the real source per agent/GUIDE.md, then run catalog.py --write/--check and gates/package_gate.py'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', required=True, type=Path)
    parser.add_argument('--name', required=True)
    parser.add_argument('--source-root', action='append')
    args = parser.parse_args()
    try:
        print(json.dumps(install(args.target, args.name, args.source_root or ['Source']), ensure_ascii=False))
    except (ValueError, OSError) as error:
        print(json.dumps({'status': 'failed', 'error': str(error)}, ensure_ascii=False))
        sys.exit(1)
