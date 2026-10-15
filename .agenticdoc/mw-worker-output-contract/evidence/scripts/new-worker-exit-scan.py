#!/usr/bin/env python3
# AC-010(b) independent judge, frozen before dispatch (record its sha256).
# Reads ONLY run.json / task.md / report.md / trace.log: no analysis text.
# Usage:
#   python new-worker-exit-scan.py --root <repo>/.agenticdoc --key <key> \
#       --since 2026-10-14T12:00:00 [--assert] [--json]
import argparse, json, pathlib, re, sys
from collections import Counter

END_RE = re.compile(r'^\[END\] (\S+) exit=(\d+) ')


def header_type(task_md):
    for line in task_md.read_text(encoding='utf-8', errors='replace').splitlines():
        m = re.match(r'^type:\s*(\S*)\s*$', line)
        if m:
            v = m.group(1).strip()
            return v if v else None
        if line.strip().startswith('## '):
            break
    return None


def last_end_exit(trace):
    if not trace.is_file():
        return None
    for line in reversed(trace.read_text(encoding='utf-8', errors='replace').splitlines()):
        m = END_RE.match(line)
        if m:
            return int(m.group(2))
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--root', required=True)
    ap.add_argument('--key', required=True)
    ap.add_argument('--since', required=True, help='ISO prefix; only runs with started_at >= this')
    ap.add_argument('--assert', dest='do_assert', action='store_true')
    ap.add_argument('--json', dest='as_json', action='store_true')
    args = ap.parse_args()
    root = pathlib.Path(args.root)
    workers = root / args.key / 'workers'
    rows = []
    for task_dir in sorted(workers.glob('*')) if workers.is_dir() else []:
        rj = task_dir / 'run.json'
        tm = task_dir / 'task.md'
        if not rj.is_file() or not tm.is_file():
            continue
        try:
            run = json.loads(rj.read_text(encoding='utf-8'))
        except ValueError:
            continue
        started = str(run.get('started_at', ''))
        if started < args.since:
            continue
        report = task_dir / 'report.md'
        report_bytes = report.stat().st_size if report.is_file() else 0
        rtype = header_type(tm)
        status = run.get('status')
        exit_code = run.get('exit')
        end_exit = last_end_exit(task_dir / 'trace.log')
        ok = bool(
            rtype in ('research', 'review', 'coding')
            and report_bytes > 0
            and status == 'done'
            and exit_code == 0
            and end_exit == 0
        )
        rows.append({
            'task_key': run.get('task_key') or task_dir.name,
            'type': rtype,
            'status': status,
            'exit': exit_code,
            'end_exit': end_exit,
            'report_bytes': report_bytes,
            'started_at': started,
            'ok': ok,
        })
    kinds = Counter(r['type'] for r in rows)
    summary = {
        'since': args.since,
        'runs': len(rows),
        'passed': sum(1 for r in rows if r['ok']),
        'failed': [r['task_key'] for r in rows if not r['ok']],
        'types': dict(kinds),
        'coverage_ok': all(kinds.get(t, 0) >= 1 for t in ('research', 'review', 'coding')),
        'count_ok': len(rows) >= 6,
    }
    if args.as_json:
        print(json.dumps({'summary': summary, 'rows': rows}, ensure_ascii=False, indent=2))
    else:
        for r in rows:
            print('{ok} {task_key} [{type}] status={status} exit={exit} end_exit={end_exit} report_bytes={report_bytes} started={started_at}'.format(**r))
        print('SUMMARY ' + json.dumps(summary, ensure_ascii=False))
    verdict = summary['count_ok'] and summary['coverage_ok'] and not summary['failed']
    if args.do_assert and not verdict:
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
