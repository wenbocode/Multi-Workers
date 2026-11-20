"""Module-local configuration and source discovery; no workspace-global registry."""
import json
from pathlib import Path


def local(root, value):
    root = Path(root).resolve()
    path = (root / value).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Path escapes module: ' + value)
    return path


def load(root):
    config = json.loads((Path(root) / 'agent/module.json').read_text(encoding='utf-8-sig'))
    if config.get('schema_version') != 1 or not config.get('module') or not config.get('source_roots'):
        raise ValueError('module.json requires schema_version=1, module and source_roots')
    for value in config['source_roots']:
        local(root, value)
    return config


def source_files(root):
    paths = set()
    for value in load(root)['source_roots']:
        path = local(root, value)
        paths.update([path] if path.is_file() else (p for p in path.rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix != '.pyc'))
    return sorted(paths)


def registered_tests(source):
    import re
    # Keep quoted strings, discard comments so commented-out registrations are not accepted.
    tokens = re.compile(r'"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*.*?\*/', re.S)
    clean = tokens.sub(lambda m: '' if m.group().startswith(('//', '/*')) else m.group(), source)
    return re.findall(r'IMPLEMENT_\w*AUTOMATION_TEST\s*\(\s*\w+\s*,\s*"([^"]+)"', clean)
