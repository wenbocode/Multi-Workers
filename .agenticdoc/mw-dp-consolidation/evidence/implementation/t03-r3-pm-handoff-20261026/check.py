"""Read-only product verification; fixtures and logs belong to this PM evidence dir."""
from pathlib import Path
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
import subprocess
import sys

EVIDENCE = Path(__file__).resolve().parent
KEY = EVIDENCE.parents[2]
ROOT = KEY.parents[1]
WORKTREE = KEY / 'implementation-worktree'
PACKAGE = WORKTREE / 'packages/multi-workers'
R3 = KEY / 'evidence/implementation/dpc-t03-protocol/rework-r3'

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

if len(sys.argv) > 1:
    sys.path.insert(0, str(PACKAGE))
    import test_decide_registry_contract as contract
    import test_dp_consolidation_registry as examples
    import decision_points as dpts
    import decision
    import mw
    imports = {module.__name__: str(Path(module.__file__).resolve()) for module in (contract, examples, dpts, decision, mw)}
    assert all(Path(path).parent == PACKAGE for path in imports.values())
    core = []
    for dp in dpts.ACTIVE_DP_IDS:
        material = examples._material(dp)
        prep = examples._preparation(dp, material)
        assert dpts.prepared_request_issues(dp, material, prep, actor_role=dpts.ENTRY_ROLES[dp]) == ()
        assert [path for path, detail in dpts.prepared_request_issues(dp, material, prep)] == ['actor_role']
        assert [path for path, detail in dpts.preparation_issues(dp, dict(prep, prepared_at='not-an-ISO-timestamp'), material)] == ['prepared_at']
        core.append(dp)
    fixture = EVIDENCE / 'fixture/probe'
    fixture.mkdir(parents=True, exist_ok=True)
    universal = ['schema_version', 'decision_point', 'key', 'phase', 'task_type', 'risk', 'risk_source', 'authority_tier', 'questions_version']
    def peer(rows, constants=''):
        return '// SYNTHETIC PARSER INPUT ONLY\nconst UNIVERSAL_REQUIRED_FIELDS = ' + json.dumps(universal) + ';\n' + constants + 'export const REQUIRED_FIELDS_BY_DP: Record<string, string[]> = {\n' + rows + '\n};\n'
    def rows(mapping):
        return ''.join(json.dumps(dp) + ': ' + json.dumps(fields) + ',\n' for dp, fields in mapping.items())
    def generated(ids):
        return '// SYNTHETIC PARSER INPUT; not actual T04 output/parity\n' + ''.join('\t' + json.dumps(dp) + ': {\n\t\trequiredStateFields: [\n\t\t],\n\t},\n' for dp in ids)
    peer_path = fixture / 'triage.synthetic.ts'
    gen_path = fixture / 'registry.synthetic.ts'
    old_peer, old_gen = contract.TRIAGE_CLIENT, contract.GENERATED_TS
    outcomes = []
    def probe(label, text, ids, should_accept, fragment=None, stage=True):
        peer_path.write_text(text, encoding='utf-8')
        gen_path.write_text(generated(ids), encoding='utf-8')
        try:
            parsed = contract._ts_required_fields()[1]
            if stage:
                contract.test_ts_required_rows_follow_the_registry_stage()
        except AssertionError as error:
            assert not should_accept, (label, str(error))
            assert fragment is None or fragment in str(error), (label, str(error))
            outcomes.append({'label': label, 'outcome': 'rejected', 'message': str(error)})
        else:
            assert should_accept, label
            outcomes.append({'label': label, 'outcome': 'accepted', 'parsed_ids': sorted(parsed)})
    try:
        contract.TRIAGE_CLIENT, contract.GENERATED_TS = peer_path, gen_path
        active = {dp: list(dpts.REQUIRED_STATE_FIELDS[dp]) for dp in dpts.ACTIVE_DP_IDS}
        legacy = contract.LEGACY_TS_ROWS
        probe('active-only-no-old-id-or-constant', peer(rows(active)), dpts.ACTIVE_DP_IDS, True)
        probe('post-t04-legacy-transition', peer(rows(legacy)), dpts.ACTIVE_DP_IDS, True)
        probe('post-t04-partial-legacy', peer(rows({'dp4-failure-handling': legacy['dp4-failure-handling']})), dpts.ACTIVE_DP_IDS, True)
        probe('pre-t04-real-legacy', peer(rows(legacy)), dpts.RETIRED_DP_IDS, True)
        renamed = dict(active)
        fields = renamed.pop('dp-w-type')
        probe('new-name-constant-key', peer('[NEW_TYPE_ID]: ' + json.dumps(fields) + ',\n' + rows(renamed), 'const NEW_TYPE_ID = "dp-w-type";\n'), dpts.ACTIVE_DP_IDS, True)
        probe('duplicate-row', peer('"dp-w-type": ["task_goal"],\n"dp-w-type": ["task_goal"],'), dpts.ACTIVE_DP_IDS, False, 'duplicate id')
        probe('unknown-id', peer('"dp99-unknown": ["task_goal"],'), dpts.ACTIVE_DP_IDS, False, 'unknown ids')
        probe('invalid-field-type', peer('"dp-w-type": [42],'), dpts.ACTIVE_DP_IDS, False, 'double-quoted')
        probe('empty-field-list', peer('"dp-w-type": [],'), dpts.ACTIVE_DP_IDS, False, 'empty or non-string')
        probe('empty-matrix', peer(''), dpts.ACTIVE_DP_IDS, False, 'no row')
        probe('truncated', peer(rows(active)).replace('\n};', ''), dpts.ACTIVE_DP_IDS, False, 'truncated')
        drifted = dict(legacy, **{'dp4-failure-handling': ['not.the.frozen.field']})
        probe('retired-row-content-drift', peer(rows(drifted)), dpts.ACTIVE_DP_IDS, False, 'legacy rows of retired ids changed')
        probe('pre-t04-active-row', peer(rows(dict(legacy, **{'dp-w-type': ['task_goal']}))), dpts.RETIRED_DP_IDS, False, 'grew a legacy TS row')
        probe('mixed-generated-ids', peer(rows(active)), (*dpts.ACTIVE_DP_IDS, 'dp4-failure-handling'), False, 'neither the frozen')
    finally:
        contract.TRIAGE_CLIENT, contract.GENERATED_TS = old_peer, old_gen
    result = {'observed_at': datetime.now(timezone.utc).isoformat(), 'imports': imports, 'core_validator_entries': core, 'real_stage': contract._generated_ts_stage(), 'synthetic_only': True, 'product_generation': False, 'outcomes': outcomes}
    (EVIDENCE / 'probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0)

before = json.loads((R3 / 'before-manifest.json').read_text(encoding='utf-8'))
after = json.loads((R3 / 'after-manifest.json').read_text(encoding='utf-8'))
verified = []
for record in after['files']:
    relative = record['path']
    path = WORKTREE / relative
    data = path.read_bytes()
    assert digest(path) == record['sha256']
    assert data == (R3 / 'after-bytes' / path.name).read_bytes()
    previous = next(row for row in before['files'] if row['path'] == relative)
    changed = record['sha256'] != previous['sha256']
    assert changed == (path.name == 'test_decide_registry_contract.py')
    live = ROOT / relative
    if record['main_tree']['exists']:
        assert digest(live) == record['main_tree']['sha256']
    else:
        assert not live.exists()
    verified.append({'path': relative, 'sha256': record['sha256'], 'bytes': len(data), 'crlf': data.count(b'\r\n'), 'bare_lf': data.count(b'\n') - data.count(b'\r\n'), 'changed_r3': changed})
for relative, record in after['handoff'].items():
    assert digest(WORKTREE / relative) == record['current_sha256'] == record['r2_after_sha256']
for group in after['evidence_boundary'].values():
    for relative, record in group['sha256'].items():
        assert digest(KEY / relative) == record['sha256']
for relative, record in after['protected_extra'].items():
    assert digest(WORKTREE / relative) == record['sha256']
file = 'test_decide_registry_contract.py'
diff = ''.join(line + '\n' for line in difflib.unified_diff((R3 / 'before-bytes' / file).read_text(encoding='utf-8').splitlines(), (PACKAGE / file).read_text(encoding='utf-8').splitlines(), fromfile='before/' + file, tofile='after/' + file, lineterm=''))
assert diff == (R3 / 'r3-changes.diff').read_text(encoding='utf-8')
hunks = sum(line.startswith('@@') for line in diff.splitlines())
for name in ('home', 'project', 'temp'):
    (EVIDENCE / 'fixture' / name).mkdir(parents=True, exist_ok=True)
env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT', 'SYSTEMDRIVE', 'WINDIR', 'COMSPEC', 'PATHEXT') if k in os.environ}
home, temp = EVIDENCE / 'fixture/home', EVIDENCE / 'fixture/temp'
env.update({'HOME': str(home), 'USERPROFILE': str(home), 'APPDATA': str(home), 'LOCALAPPDATA': str(home), 'TEMP': str(temp), 'TMP': str(temp), 'TMPDIR': str(temp), 'PYTHONDONTWRITEBYTECODE': '1', 'PYTEST_DISABLE_PLUGIN_AUTOLOAD': '1', 'PYTHONIOENCODING': 'utf-8', 'PYTHONUTF8': '1'})
commands = [('pm-green.log', [sys.executable, '-m', 'pytest', '-p', 'no:cacheprovider', '-q', 'test_decide_registry_contract.py', 'test_dp_consolidation_registry.py']), ('pm-probe.log', [sys.executable, str(Path(__file__).resolve()), 'probe'])]
results = []
for label, argv in commands:
    completed = subprocess.run(argv, cwd=PACKAGE, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    log = f'cwd={PACKAGE}\nargv={argv}\nenv_keys={sorted(env)}\nrc={completed.returncode}\nstdout:\n{completed.stdout}\nstderr:\n{completed.stderr}\n'
    (EVIDENCE / label).write_text(log, encoding='utf-8')
    print(log)
    results.append({'label': label, 'rc': completed.returncode})
for record in verified:
    assert digest(WORKTREE / record['path']) == record['sha256']
result = {'observed_at': datetime.now(timezone.utc).isoformat(), 'files': verified, 'handoff_rows': len(after['handoff']), 'evidence_boundary_files': sum(group['files'] for group in after['evidence_boundary'].values()), 'actual_diff_hunks': hunks, 'tests': results, 'product_writes': False, 'full_l2_verified': False}
(EVIDENCE / 'check.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
assert all(row['rc'] == 0 for row in results)
