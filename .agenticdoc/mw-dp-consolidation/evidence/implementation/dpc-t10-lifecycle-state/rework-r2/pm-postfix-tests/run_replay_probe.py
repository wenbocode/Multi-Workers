"""PM-only guarded AC052 probe, preserving the assigned-suite green artifacts."""
from __future__ import annotations
import ast
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
import run_pm_tests as harness

HERE = Path(__file__).resolve().parent
FIXTURE = Path('C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/pm-verification')
LABEL = 't10-r2-replay-probe-first'


def main():
    assert sys.dont_write_bytecode
    ast.parse((HERE / 'test_replay_probe.py').read_text(encoding='utf-8'))
    before = harness._protected_snapshot()
    assert before['products'] == harness.PRODUCTS
    assert before['live'] == harness.LIVE_SHA256
    assert before['mirror_files'] == 1891 and len(before['pyc']) == 14 and len(before['old_evidence']) == 744
    for name, digest in harness.ASSIGNED_TEST_SHA256.items():
        assert harness._sha256(harness.PACKAGES / name) == digest
    fixture = FIXTURE / LABEL
    evidence = HERE / 'runs' / LABEL
    assert not fixture.exists() and not evidence.exists()
    os.mkdir(fixture)
    evidence.mkdir()
    for name in ('home', 'temp', 'project', 'pycache'):
        (fixture / name).mkdir()
    env = harness._child_env(fixture, evidence, LABEL)
    harness._write_json(evidence / 'before.json', before)
    checks = {}
    rc, out, err = harness._run('guard-preflight', [sys.executable, '-B', str(HERE / 'guard_preflight.py')], env, fixture / 'project', evidence)
    preflight = json.loads(out) if rc == 0 else {}
    checks['preflight'] = preflight
    if rc != 0 or not preflight.get('checks', {}).get('guard_installed') or preflight.get('checks', {}).get('credential_env_names') != []:
        harness._write_json(evidence / 'report.json', {'status': 'blocked-before-product', 'preflight_rc': rc})
        return 2
    argv = [sys.executable, '-B', '-m', 'pytest', '-p', 'no:cacheprovider', '-q', '--basetemp', str(fixture / 'pytest-basetemp'), str(HERE / 'test_replay_probe.py')]
    rc, out, err = harness._run('pytest-replay', argv, env, harness.PACKAGES, evidence)
    summary = harness._parse_summary(out)
    after = harness._protected_snapshot()
    harness._write_json(evidence / 'after.json', after)
    problems = []
    for name in ('mirror', 'pyc', 'old_evidence', 'live', 'products'):
        if before[name] != after[name]:
            problems.append(name + ' changed')
    rows = harness._sentinel_rows(evidence / 'guard-sentinel.jsonl')
    for command in ('guard-preflight', 'pytest-replay'):
        pid = json.loads((evidence / (command + '.meta.json')).read_text(encoding='utf-8'))['pid']
        stages = {r.get('stage') for r in rows if r.get('pid') == pid}
        if not {'import', 'guard-installed'} <= stages:
            problems.append(command + ' guard not installed')
    if any(r.get('stage') == 'unparsable' or r.get('run') != LABEL or r.get('dont_write_bytecode') is not True for r in rows):
        problems.append('guard sentinel malformed')
    report = {'observed_at': datetime.now(timezone.utc).isoformat(), 'source': 'agent-report', 'status': 'executed' if not problems else 'harness-failed', 'argv': argv, 'cwd': str(harness.PACKAGES), 'fixture': str(fixture), 'env_names': sorted(env), 'rc': rc, 'summary': summary, 'protection_unchanged': not problems, 'problems': problems, 'product_correctness': False, 'note': 'AC052 original event-id idempotency; raw real result retained, no product changes or action authority'}
    harness._write_json(evidence / 'report.json', report)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 2 if problems else rc


if __name__ == '__main__':
    raise SystemExit(main())
