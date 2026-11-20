"""Select approved gates by impact; keep execution logs out of normal responses."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'agent'))
import ask

def runtime(case):
    return ask.module_config.load(ROOT).get('ue', {}).get('cases', {}).get(case, {})


def scene(case):
    return runtime(case).get('profile') == 'scene'



def select(data, impacts, full=False):
    if not full and not impacts:
        raise ValueError('Specify exact --impact T-... or explicit --full; no implicit full run')
    unknown = set(impacts) - set(data['term_map'])
    if unknown:
        raise ValueError('Unknown impact: ' + ', '.join(sorted(unknown)))
    selected = {}
    for row in data['gates']:
        if full or row['selection'] == 'always' or row['term_id'] in impacts:
            item = selected.setdefault(row['gate_id'], dict(gate=row['gate_id'], case=row['case_id'], reasons=[]))
            reason = 'full' if full else ('always' if row['selection'] == 'always' else row['term_id'])
            if reason not in item['reasons']:
                item['reasons'].append(reason)
    # Script checks first; otherwise retain the module catalog's declared order.
    return sorted(selected.values(), key=lambda r: bool(r['case']))


def failure_excerpt(log, limit=800):
    with log.open('rb') as stream:
        stream.seek(max(0, log.stat().st_size - limit * 4))
        return stream.read().decode('utf-8', errors='replace')[-limit:]


def details(summary, gate, offset=0, limit=4000, stream='runner'):
    if offset < 0 or not 1 <= limit <= 8000:
        raise ValueError('offset >= 0 and 1 <= limit <= 8000 required')
    data = json.loads(summary.read_text(encoding='utf-8'))
    row = next((r for r in data['results'] if r['gate'] == gate), None)
    if not row or row['status'] != 'failed':
        raise ValueError('Details are available only for a failed selected gate')
    path = (summary.parent / row['log']).resolve()
    if stream == 'editor':
        logs = sorted((summary.parent / row['gate'] / 'ue').glob('*/editor.log'))
        if len(logs) != 1:
            raise ValueError('No unique native editor log; inspect runner details first')
        path = logs[0].resolve()
    if not path.is_relative_to(summary.parent.resolve()):
        raise ValueError('Log escapes run directory')
    # Read only the requested byte page, even for very large native logs.
    with path.open('rb') as handle:
        handle.seek(offset)
        block = handle.read(limit)
        more = bool(handle.read(1))
    return dict(gate=gate, stream=stream, offset=offset, text=block.decode('utf-8', errors='replace'),
                next_offset=offset + len(block) if more else None)


def arguments(item, args, folder):
    if item['gate'] == 'G-ASK':
        return []
    if item['gate'] == 'G-DESIGN':
        return ['--baseline', str(args.baseline.resolve())]
    if not item['case']:
        return []
    is_scene = scene(item['case'])
    project = args.scene_project if is_scene else args.project
    return ['--editor', str(args.editor.resolve()), '--project', str(project.resolve()),
            '--map', runtime(item['case']).get('map', ask.module_config.load(ROOT).get('ue', {}).get('default_map', '/Engine/Maps/Entry')),
            '--report-root', str(folder / 'ue'), '--timeout', str(args.timeout)]


def execute(selected, args, data):
    # Validate all runtime prerequisites before starting any selected gate.
    for field in ['baseline', 'report_root']:
        if getattr(args, field) is None:
            raise ValueError('--' + field.replace('_', '-') + ' required')
    required = [args.baseline]
    if any(r['case'] for r in selected):
        required.append(args.editor)
    if any(r['case'] and not scene(r['case']) for r in selected):
        required.append(args.project)
    if any(scene(r['case']) for r in selected):
        required.append(args.scene_project)
    if args.timeout <= 0 or any(p is None or not p.is_file() for p in required):
        raise ValueError('Existing baseline/editor/project/scene-project and positive timeout required for selected gates')
    if data['stale_sources']:
        raise ValueError('Source index is stale')
    for item in selected:
        rows = [r for r in data['gates'] if r['gate_id'] == item['gate']]
        cases = [r for r in data['testcases'] if r['case_id'] == item['case']]
        if item['case'] and (not cases or any(r['runner'] != 'agent/gates/automation_gate.py' for r in rows)):
            raise ValueError('Unsupported testcase adapter: ' + item['gate'])
        if any(r['status'] != 'accepted' for r in rows + cases):
            raise ValueError('Unconfirmed gate/testcase: ' + item['gate'])
    run = args.report_root.resolve() / ('regression-' + uuid.uuid4().hex)
    run.mkdir(parents=True)
    summary = dict(mode='full' if args.full else 'impact', impacts=args.impact or [],
                   package_revision=data['revision'], source_revision=data['source_revision'],
                   selected=selected, results=[], status='running')
    summary_file = run / 'summary.json'
    def save():
        summary_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding='utf-8')
    save()
    for item in selected:
        folder = run / item['gate']
        folder.mkdir()
        log = folder / 'runner.log'
        extra = arguments(item, args, folder)
        argv = [sys.executable, '-B', str(ROOT / 'agent/gates/run.py'), '--gate', item['gate']]
        if extra:
            argv += ['--', *extra]
        start = time.monotonic()
        with log.open('wb') as output:
            try:
                code = subprocess.run(argv, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT).returncode
            except OSError as error:
                output.write(str(error).encode('utf-8'))
                code = 127
        result = dict(gate=item['gate'], status='passed' if code == 0 else 'failed',
                      exit_code=code, seconds=round(time.monotonic() - start, 2),
                      log=log.relative_to(run).as_posix(), argv=argv)
        summary['results'].append(result)
        save()
        if code:
            break
    summary['status'] = 'passed' if all(r['status'] == 'passed' for r in summary['results']) else 'failed'
    summary['not_run'] = [r['gate'] for r in selected[len(summary['results']):]]
    save()
    compact = dict(status=summary['status'], mode=summary['mode'],
                   passed=sum(r['status'] == 'passed' for r in summary['results']),
                   selected=len(selected), not_run=summary['not_run'], summary=str(summary_file))
    if summary['status'] == 'failed':
        failed = summary['results'][-1]
        compact.update(failed_gate=failed['gate'], error=failure_excerpt(run / failed['log']),
                       next=['--details', str(summary_file), '--gate', failed['gate']])
    return compact


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--impact', nargs='+', help='Exact term IDs; infer affected callers before selecting')
    mode.add_argument('--full', action='store_true')
    mode.add_argument('--details', type=Path, help='Read a failed gate log from a saved summary')
    parser.add_argument('--gate', help='Failed gate to inspect with --details; not a selection override')
    parser.add_argument('--stream', choices=['runner', 'editor'], default='runner')
    parser.add_argument('--offset', type=int, default=0)
    parser.add_argument('--limit', type=int, default=4000)
    parser.add_argument('--plan', action='store_true')
    for name in ['baseline', 'report-root', 'editor', 'project', 'scene-project']:
        parser.add_argument('--' + name, type=Path)
    parser.add_argument('--timeout', type=int, default=1200)
    args = parser.parse_args()
    try:
        if args.details:
            result = details(args.details, args.gate, args.offset, args.limit, args.stream)
        else:
            data = ask.load_package(ROOT)
            selected = select(data, args.impact or [], args.full)
            result = dict(status='planned', selected=selected) if args.plan else execute(selected, args, data)
    except (ValueError, OSError) as error:
        result = dict(status='failed', error=str(error))
    print(json.dumps(result, ensure_ascii=False))
    return 1 if result.get('status') == 'failed' else 0


if __name__ == '__main__':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.exit(main())
