from __future__ import annotations
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = HERE.parents[2]
ROOT = KEY.parents[1]
BASE = KEY / 'evidence/implementation/dpc-t10-lifecycle-state/rework-r2'
PKG = KEY / 'implementation-worktree/packages/multi-workers'
WORKTREE = KEY / 'implementation-worktree'
ABSORB = KEY / 'evidence/implementation/t10-r2-product-absorption-20261028'
C = BASE / 'verification-preparation'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(name, value):
    with (HERE / name).open('x', encoding='utf-8', newline='\n') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)
        handle.write('\n')


if __name__ == '__main__':
    products = json.loads((ABSORB / 'check.json').read_text(encoding='utf-8'))['products_sha256']
    for name, digest in products.items():
        assert sha(PKG / name) == digest
    mirror = {p.relative_to(WORKTREE).as_posix(): sha(p) for p in sorted(WORKTREE.rglob('*')) if p.is_file()}
    assert mirror == json.loads((ABSORB / 'mirror-before-verification.json').read_text(encoding='utf-8')) and len(mirror) == 1891
    green_runs = {}
    for label in ('t10-r2-postfix-first', 't10-r2-postfix-second'):
        run = BASE / 'pm-postfix-tests/runs' / label
        report = json.loads((run / 'report.json').read_text(encoding='utf-8'))
        assert report['problems'] == [] and report['collection']['count'] == 130
        assert report['pytest']['counts'] == {'passed': 130} and report['rc']['pytest'] == 0
        assert report['focus']['rc'] == 0 and report['focus']['summary']['counts'] == {'passed': 14}
        for kind in ('mirror', 'pyc', 'old_evidence'):
            assert report['protection'][kind]['diff'] == {'added': [], 'removed': [], 'changed': []}
        assert report['protection']['live']['unchanged'] and report['protection']['products']['unchanged']
        assert report['expected_red']['observed'] == [] and report['expected_red']['unexpected_failures'] == []
        meta = json.loads((run / 'pytest.meta.json').read_text(encoding='utf-8'))
        assert meta['rc'] == 0 and Path(meta['cwd']).resolve() == PKG.resolve()
        assert meta['argv'][1] == '-B'
        green_runs[label] = {'pytest': report['pytest'], 'focus': report['focus'], 'actual_pytest_meta': meta, 'command_pids': report['checks']['command_pids'], 'env_names': report['env_keys']}
    replay_path = BASE / 'pm-postfix-tests/runs/t10-r2-replay-probe-first'
    replay = json.loads((replay_path / 'report.json').read_text(encoding='utf-8'))
    assert replay['rc'] == 1 and replay['summary']['counts'] == {'failed': 1} and replay['problems'] == []
    assert replay['protection_unchanged']
    assert 'record_lifecycle' in (replay_path / 'pytest-replay.stdout').read_text(encoding='utf-8')
    deliveries = {}
    for record in json.loads((C / 'checks/delivery.json').read_text(encoding='utf-8'))['files']:
        path = ROOT / record['file']
        assert path.is_relative_to(C) and path.is_file()
        assert sha(path) == record['sha256'] and path.stat().st_size == record['bytes'], record['file']
        deliveries[record['file']] = record['sha256']
    assert sha(C / 'report.md') == sha(C / 'output.md')
    assert len(deliveries) == 13
    c_run = json.loads((KEY / 'workers/dpc-t10-r2-verification-preparation/run.json').read_text(encoding='utf-8'))
    assert c_run['status'] == 'needs-clarification' and c_run['exit'] == 2
    old_delivery = json.loads((ABSORB / 'delivery-evidence-sha256.json').read_text(encoding='utf-8'))
    assert all(sha(ROOT / path) == digest for path, digest in old_delivery.items())
    static = json.loads((C / 'checks/static_verify.result.json').read_text(encoding='utf-8'))
    assert static['ok'] is True and static['problems'] == []
    before = HERE / 'before-bytes'
    before.mkdir()
    for name in products:
        with (before / name).open('xb') as handle:
            handle.write((PKG / name).read_bytes())
    save('mirror-before.json', mirror)
    save('pyc-before.json', {p: digest for p, digest in mirror.items() if p.endswith('.pyc')})
    save('old-stage-b-evidence-before.json', old_delivery)
    save('stage-c-evidence-before.json', {p.relative_to(ROOT).as_posix(): sha(p) for p in C.rglob('*') if p.is_file()})
    save('pm-postfix-evidence-before.json', {p.relative_to(ROOT).as_posix(): sha(p) for p in (BASE / 'pm-postfix-tests').rglob('*') if p.is_file()})
    save('live-before.json', {name: sha(ROOT / 'packages/multi-workers' / name) for name in products})
    save('check.json', {'observed_at': datetime.now(timezone.utc).isoformat(), 'source': 'agent-report', 'PM_current_five_files_full_EOF': True, 'PM_runner_guard_complete_EOF': True, 'products': products, 'green_runs': green_runs, 'replay': replay, 'stage_c_run': c_run, 'stage_c_manifest_verified': 13, 'stage_c_machine_json_gaps_remain': True, 'stage_c_acked_by_tool': True, 'stage_c_full_extra_suite_executed': False, 'mirror_unchanged': True, 'old_stage_b_evidence_unchanged': True, 'semantic_handoff': False, 'note': 'current source reading completed before these green/probe runs; old red read-order deviation remains historical, not backfilled'})
    print('PM 130P twice/focus14P twice; actual replay1F; current bytes/protected history stable; C exit2 acked, gaps retained')
