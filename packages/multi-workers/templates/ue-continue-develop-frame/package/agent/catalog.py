"""Generate/check module CSV catalogs from source facts and reviewed design metadata."""
import argparse
import csv
import io
import json
from pathlib import Path
import sys
import uuid

import ask
import build_source_index

ROOT = Path(__file__).resolve().parents[1]
FILES = {'terms': 'terms.csv', 'testcases': 'testcase.csv', 'gates': 'gates.csv'}


def read_csv(path):
    if not path.exists():
        return []
    with path.open(encoding='utf-8-sig', newline='') as stream:
        return list(csv.DictReader(stream))


def encoded(name, rows):
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=ask.FIELDS[name].split(','))
    writer.writeheader()
    writer.writerows(rows)
    return stream.getvalue().encode('utf-8-sig')


def review(root, rows):
    lines = ['# Testcase / Gate 审阅清单', '', '由catalog.py生成。确认绑定定义与实现摘要；目录生成不代表人工批准或测试通过。', '']
    for category, key in [('testcases', 'case_id'), ('gates', 'gate_id')]:
        lines += ['## ' + category, '']
        for identity in dict.fromkeys(r[key] for r in rows[category]):
            group = [r for r in rows[category] if r[key] == identity]
            row = group[0]
            lines += ['### ' + identity, '', '- 状态：' + row['status'],
                      '- 关联术语：' + ', '.join(dict.fromkeys(r['term_id'] for r in group)),
                      '- 摘要：`' + ask.item_digest(group, root) + '`']
            fields = ['name', 'path', 'preconditions', 'steps', 'expected', 'command'] if category == 'testcases' else ['requirement', 'selection', 'trigger', 'runner', 'args', 'artifacts']
            lines += ['- ' + field + '：' + row[field] for field in fields]
            lines += ['- 确认记录：' + (row['decision_ref'] or '待人审定'), '']
    return ('\n'.join(lines) + '\n').encode('utf-8')


def generate(root):
    config = json.loads((root / 'agent/catalog.json').read_text(encoding='utf-8-sig'))
    if config.get('schema_version') != 1:
        raise ValueError('Unsupported catalog schema')
    index = build_source_index.build(root)
    rows = {name: [] for name in FILES}
    for item in config['terms']:
        matches = [n for n in index['nodes'] if n['path'] == item['path'] and n['symbol'] == item['symbol']
                   and (not item.get('qualified') or n['qualified'] == item['qualified'])]
        if not matches:
            raise ValueError('No source declaration: ' + item['symbol'])
        if len({n['qualified'] for n in matches}) > 1:
            raise ValueError('Ambiguous symbol; specify qualified: ' + item['symbol'])
        node = sorted(matches, key=lambda n: (n['has_error'], n['line']))[0]
        rows['terms'].append(dict(term_id=item['term_id'], term=node['symbol'], alias='',
            definition=item.get('definition', ''), unit=item.get('unit', ''),
            owner=node['qualified'].rsplit('::', 1)[0] if '::' in node['qualified'] else node['symbol'],
            path=node['path'], symbol=node['symbol'], ast_id=node['id']))
    terms = {r['term_id'] for r in rows['terms']}
    if len(terms) != len(rows['terms']):
        raise ValueError('Duplicate term IDs')
    for name in ['testcases', 'gates']:
        for item in config[name]:
            row = {k: item[k] for k in ask.FIELDS[name].split(',') if k not in ('status', 'decision_ref')}
            if row['term_id'] not in terms:
                raise ValueError('Unknown term: ' + row['term_id'])
            if name == 'testcases':
                path = ask.local_path(root, row['path'])
                if row['path'] not in {f['path'] for f in index['files']} or path.suffix != '.cpp' or row['name'] not in ask.module_config.registered_tests(path.read_text(encoding='utf-8-sig')):
                    raise ValueError('Missing real UE AutomationTest: ' + row['name'])
                row['command'] = 'Automation RunTests ' + row['name']
            else:
                runner = ask.local_path(root, row['runner'])
                if not runner.is_relative_to(root / 'agent/gates') or not runner.is_file():
                    raise ValueError('Gate runner must exist in agent/gates: ' + row['runner'])
                if row['selection'] not in ('always', 'conditional'):
                    raise ValueError('Invalid selection')
                args = json.loads(row['args'])
                if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
                    raise ValueError('Gate args must be a JSON string array')
            rows[name].append(dict(row, status='proposed', decision_ref=''))
    cases = {r['case_id'] for r in rows['testcases']}
    registered = {(p.relative_to(root).as_posix(), name)
                  for p in ask.module_config.source_files(root) if p.suffix == '.cpp'
                  for name in ask.module_config.registered_tests(p.read_text(encoding='utf-8-sig'))}
    missing = registered - {(r['path'], r['name']) for r in rows['testcases']}
    if missing:
        raise ValueError('Uncatalogued UE AutomationTest: ' + json.dumps(sorted(missing), ensure_ascii=False))
    for row in rows['testcases']:
        if not any(g['case_id'] == row['case_id'] and
                   (g['selection'] == 'always' or g['term_id'] == row['term_id']) for g in rows['gates']):
            raise ValueError('Testcase missing impact gate: ' + row['case_id'] + ' / ' + row['term_id'])
    if any(r['case_id'] and r['case_id'] not in cases for r in rows['gates']):
        raise ValueError('Broken gate testcase reference')
    records = read_csv(root / 'agent/records.csv')
    for record in records:
        if record['term_id'] not in terms or (record['case_id'] and record['case_id'] not in cases):
            raise ValueError('Update/archive referencing records before removal: ' + record['record_id'])
    for file in ['GOAL.md', 'DESIGN.md']:
        if set(ask.TERM_REF.findall((root / file).read_text(encoding='utf-8-sig'))) - terms:
            raise ValueError('Update design/goal term references before removal')
    # Preserve only a verifiable approval for the exact resulting rows and implementation.
    invalidated = []
    for name, key in [('testcases', 'case_id'), ('gates', 'gate_id')]:
        old = read_csv(root / 'agent' / FILES[name])
        for identity in dict.fromkeys(r[key] for r in rows[name]):
            group = [r for r in rows[name] if r[key] == identity]
            previous = [r for r in old if r[key] == identity]
            if not previous or previous[0]['status'] != 'accepted':
                continue
            ref = previous[0]['decision_ref']
            record = next((r for r in records if r['record_id'] == ref and r['kind'] == 'human_decision'), None)
            decision = json.loads(ask.local_path(root, record['path']).read_text(encoding='utf-8-sig')) if record else {}
            valid = all(decision.get(k) == v for k, v in dict(category=name, item_id=identity,
                        decision='accepted', item_sha256=ask.item_digest(group, root)).items())
            valid = valid and all(decision.get(k) for k in ['confirmed_by', 'confirmed_at', 'source_ref'])
            if valid:
                for row in group:
                    row.update(status='accepted', decision_ref=ref)
            else:
                invalidated.append(identity)
    return index, rows, invalidated


def update(root, write=False, check=False, allow_remove=False):
    root = Path(root).resolve()
    index, rows, invalidated = generate(root)
    targets = {root / 'agent' / FILES[name]: encoded(name, value) for name, value in rows.items()}
    targets[root / 'agent/source_nodes.json'] = (json.dumps(index, ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    targets[root / 'agent/REVIEW.md'] = review(root, rows)
    changed = [p for p, content in targets.items() if not p.exists() or p.read_bytes() != content]
    removed = {}
    for name, key in [('terms', 'term_id'), ('testcases', 'case_id'), ('gates', 'gate_id')]:
        old = read_csv(root / 'agent' / FILES[name])
        removed[name] = sorted({r[key] for r in old} - {r[key] for r in rows[name]})
    if removed['gates'] or removed['testcases']:
        # Shrinking the suite is a policy change, even when retained gate bodies are identical.
        invalidated.extend(r['gate_id'] for r in rows['gates'] if r['status'] == 'accepted')
        for row in rows['gates']:
            row.update(status='proposed', decision_ref='')
        targets[root / 'agent/gates.csv'] = encoded('gates', rows['gates'])
        targets[root / 'agent/REVIEW.md'] = review(root, rows)
        changed = [p for p, content in targets.items() if not p.exists() or p.read_bytes() != content]
    invalidated = sorted(set(invalidated))
    report = dict(status='drift' if changed else 'unchanged', changed=[p.relative_to(root).as_posix() for p in changed],
                  removed=removed, invalidated=invalidated,
                  pending={name: sorted({r['case_id' if name == 'testcases' else 'gate_id'] for r in rows[name]
                           if r['status'] != 'accepted'}) for name in ['testcases', 'gates']})
    if write and changed:
        if any(removed.values()) and not allow_remove:
            raise ValueError('Removal requires explicit --allow-remove: ' + json.dumps(removed))
        backup = root / 'agent/logs/catalog-updates' / uuid.uuid4().hex
        backup.mkdir(parents=True)
        previous = {p: p.read_bytes() if p.exists() else None for p in targets}
        try:
            for p in changed:
                if previous[p] is not None:
                    (backup / p.name).write_bytes(previous[p])
                p.write_bytes(targets[p])
            ask.check(root)
        except Exception:
            for p, content in previous.items():
                if content is None:
                    p.unlink(missing_ok=True)
                else:
                    p.write_bytes(content)
            raise
        report.update(status='updated', backup=backup.relative_to(root).as_posix())
        (backup / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report, 1 if check and changed else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--write', action='store_true')
    mode.add_argument('--check', action='store_true')
    mode.add_argument('--discover', action='store_true', help='List real source symbols and UE registrations without generating design metadata')
    parser.add_argument('--allow-remove', action='store_true')
    args = parser.parse_args()
    try:
        if args.discover:
            index = build_source_index.build(ROOT)
            result = dict(symbols=[{k: n[k] for k in ['symbol', 'qualified', 'path', 'line']} for n in index['nodes']],
                          testcases=[dict(path=p.relative_to(ROOT).as_posix(), name=name)
                          for p in ask.module_config.source_files(ROOT) if p.suffix == '.cpp'
                          for name in ask.module_config.registered_tests(p.read_text(encoding='utf-8-sig'))])
            code = 0
        else:
            result, code = update(ROOT, args.write, args.check, args.allow_remove)
    except (ValueError, OSError, KeyError) as error:
        result, code = dict(status='failed', error=str(error)), 2
    print(json.dumps(result, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
