"""Bind module-local engineering records to a change baseline and current inputs."""
import argparse
import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import ask


def inputs(root):
    paths = set(ask.module_config.source_files(root))
    paths.update(p for p in (root / 'agent').rglob('*.py') if '__pycache__' not in p.parts)
    paths.update(root / p for p in ('agent/catalog.json', 'agent/module.json', 'agent/GUIDE.md', 'AGENTS.md', 'GOAL.md'))
    return dict(module=ask.module_config.load(root)['module'],
                source_sha256=ask.fingerprint(root, ask.module_config.source_files(root)),
                design_sha256=hashlib.sha256((root / 'DESIGN.md').read_bytes()).hexdigest(),
                implementation_sha256=ask.fingerprint(root, sorted(paths)))


def records(root):
    with (root / 'agent/records.csv').open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def record_hash(root, row):
    return hashlib.sha256(json.dumps(row, sort_keys=True).encode() + ask.local_path(root, row['path']).read_bytes()).hexdigest()


def snapshot(root):
    return dict(inputs(root), records={r['record_id']: record_hash(root, r) for r in records(root)})


def validate(root, baseline):
    current = inputs(root)
    if 'implementation_sha256' not in baseline or 'records' not in baseline:
        raise ValueError('Baseline lacks engineering-record tracking; use a pre-change v2 snapshot')
    before = {k: baseline[k] for k in current}
    if before == current:
        return []
    valid = []
    for row in records(root):
        if row['kind'] != 'development' or baseline['records'].get(row['record_id']) == record_hash(root, row):
            continue
        try:
            entry = json.loads(ask.local_path(root, row['path']).read_text(encoding='utf-8-sig'))
        except (ValueError, OSError):
            continue
        if entry.get('baseline') != before or entry.get('current') != current:
            continue
        if row['source_revision'] != current['source_sha256'] or not entry.get('summary') or not entry.get('validation'):
            continue
        if any(not ask.local_path(root, a['path']).is_file() or
               hashlib.sha256(ask.local_path(root, a['path']).read_bytes()).hexdigest() != a['sha256']
               for a in entry.get('artifacts', [])):
            continue
        valid.append(row['record_id'])
    if not valid:
        raise ValueError('Missing current engineering record: index a development JSON bound to this baseline and current inputs')
    return valid


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--id', required=True)
    parser.add_argument('--term', required=True)
    parser.add_argument('--summary', required=True)
    parser.add_argument('--validation', required=True, help='Actual state, including pending confirmation; never invent a pass')
    parser.add_argument('--artifact', action='append', default=[], help='Module-relative evidence file')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    data = ask.load_package(root)
    if args.term not in data['term_map'] or any(r['record_id'] == args.id for r in records(root)):
        raise ValueError('Unknown term or duplicate record ID')
    baseline = json.loads(args.baseline.read_text(encoding='utf-8-sig'))
    if 'records' not in baseline or 'implementation_sha256' not in baseline:
        raise ValueError('Use a pre-change v2 baseline')
    current = inputs(root)
    before = {k: baseline[k] for k in current}
    if before['module'] != current['module']:
        raise ValueError('Baseline belongs to another module')
    path = ask.local_path(root, 'agent/logs/' + args.id + '.json')
    entry = dict(baseline=before, current=current, summary=args.summary, validation=args.validation,
                 artifacts=[dict(path=value, sha256=hashlib.sha256(ask.local_path(root, value).read_bytes()).hexdigest())
                            for value in args.artifact])
    with path.open('x', encoding='utf-8') as stream:
        json.dump(entry, stream, ensure_ascii=False, indent=2)
    with (root / 'agent/records.csv').open('a', encoding='utf-8', newline='') as stream:
        csv.writer(stream).writerow([args.id, args.term, '', 'development', datetime.now(timezone.utc).isoformat(),
                                    current['source_sha256'], path.relative_to(root).as_posix(), args.summary])
    print(json.dumps(dict(status='recorded', record=args.id, path=path.relative_to(root).as_posix())))


if __name__ == '__main__':
    main()
