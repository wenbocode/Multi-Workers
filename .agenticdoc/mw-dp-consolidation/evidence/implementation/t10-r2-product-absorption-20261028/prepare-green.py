from __future__ import annotations
import ast
import hashlib
import inspect
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = HERE.parents[2]
BASE = KEY / 'evidence/implementation/dpc-t10-lifecycle-state/rework-r2'
OLD = BASE / 'pm-controlled'
NEW = BASE / 'pm-postfix-tests'
PKG = KEY / 'implementation-worktree/packages/multi-workers'


def replace_once(text, old, new):
    assert text.count(old) == 1, old
    return text.replace(old, new, 1)


if __name__ == '__main__':
    expected = json.loads((HERE / 'check.json').read_text(encoding='utf-8'))['products_sha256']
    for name, digest in expected.items():
        assert hashlib.sha256((PKG / name).read_bytes()).hexdigest() == digest
    assert not NEW.exists()
    NEW.mkdir()
    changes = {}
    for name in ('run_pm_tests.py', 'sitecustomize.py', 'guard_preflight.py', 'probe_imports.py'):
        source = (OLD / name).read_text(encoding='utf-8')
        target = source
        if name == 'run_pm_tests.py':
            target = replace_once(target, '8863e534f0a74edec1fc0105c0619c9dd19c85a472b82db6d622c23a7f85a5e6', expected['decision_wire.py'])
            target = replace_once(target, '0c0f7fffb353cc829e054dfbeec409915cb4bebce11d998c5d810feb533dc8e4', expected['decision_lifecycle.py'])
            target = replace_once(target, 'EXISTING_ITEM_FLOOR = 116', 'EXISTING_ITEM_FLOOR = 130')
            target = replace_once(target, '    "test_decision_context_lifecycle.py": "1bca28c56c7ab039de5c3a91638fd20c1e2fa89f4a1ec996169cfd933c1e6ae9",\n}', '    "test_decision_context_lifecycle.py": "1bca28c56c7ab039de5c3a91638fd20c1e2fa89f4a1ec996169cfd933c1e6ae9",\n    "test_decision_task_state.py": "30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f",\n}')
            target = replace_once(target, '    proc = subprocess.run(\n', '    proc = subprocess.Popen(\n')
            target = replace_once(target, '        capture_output=True,\n    )\n    ended = _utc()\n    (artifacts / f"{name}.stdout").write_bytes(proc.stdout)\n    (artifacts / f"{name}.stderr").write_bytes(proc.stderr)', '        stdout=subprocess.PIPE,\n        stderr=subprocess.PIPE,\n    )\n    stdout, stderr = proc.communicate()\n    ended = _utc()\n    (artifacts / f"{name}.stdout").write_bytes(stdout)\n    (artifacts / f"{name}.stderr").write_bytes(stderr)')
            target = replace_once(target, '            "rc": proc.returncode,\n', '            "rc": proc.returncode,\n            "pid": proc.pid,\n')
            target = replace_once(target, 'len(proc.stdout)', 'len(stdout)')
            target = replace_once(target, 'len(proc.stderr)', 'len(stderr)')
            target = replace_once(target, 'return proc.returncode, proc.stdout.decode', 'return proc.returncode, stdout.decode')
            target = replace_once(target, '    return proc.returncode, stdout.decode("utf-8", "replace"), proc.stderr.decode(', '    return proc.returncode, stdout.decode("utf-8", "replace"), stderr.decode(')
            target = replace_once(target, '    if audit.is_file():\n', '    if not audit.is_file():\n        problems.append("stage-A audit is missing; no product stage is allowed")\n    for name, expected in ASSIGNED_TEST_SHA256.items():\n        if _sha256(PACKAGES / name) != expected:\n            problems.append(f"{name} is not the immutable stage-A revision")\n    if audit.is_file():\n')
            target = replace_once(target, '    if len(collected) < EXISTING_ITEM_FLOOR:\n', '    original_ids = (HERE.parent / "pm-controlled/runs/t10-r2-red-controls-20261028T064853Z/collection.node-ids.txt").read_text(encoding="utf-8").splitlines()\n    if set(original_ids) != set(collected) or len(original_ids) != len(collected):\n        problems.append("the immutable original 130 collected items changed")\n    if len(collected) < EXISTING_ITEM_FLOOR:\n')
            target = replace_once(target, '    wrong_run = sorted(pid for pid, entry in sentinel_by_pid.items() if entry.get("run") != label)', '    command_pids = {}\n    for command in ("guard-preflight", "import-probe", "collect", "pytest", "focus"):\n        meta_path = artifacts / f"{command}.meta.json"\n        if not meta_path.exists():\n            continue\n        command_pid = json.loads(meta_path.read_text(encoding="utf-8"))["pid"]\n        command_pids[command] = command_pid\n        entry = sentinel_by_pid.get(command_pid, {})\n        if not {"import", "guard-installed"}.issubset(set(entry.get("stages", []))):\n            problems.append(f"{command} child pid has no installed guard sentinel")\n    for row in sentinel:\n        if row.get("stage") == "unparsable" or row.get("dont_write_bytecode") is not True:\n            problems.append("a malformed or non-B child guard sentinel exists")\n        if row.get("stage") == "guard-installed" and row.get("credential_env_names") != []:\n            problems.append("credential-shaped names reached a guarded child")\n    checks["command_pids"] = command_pids\n    wrong_run = sorted(pid for pid, entry in sentinel_by_pid.items() if entry.get("run") != label)')
            target = replace_once(target, '    return pytest_rc\n', '    if pytest_rc != 0:\n        return pytest_rc\n    return focus["rc"] if focus is not None else 0\n')
        elif name == 'sitecustomize.py':
            target = replace_once(target, 'import json\n', 'import inspect\nimport json\n')
            target = replace_once(target, '    if not _SENTINEL:\n', '    if not _SENTINEL or not _RUN:\n')
            target = replace_once(target, '    real_init = subprocess.Popen.__init__\n', '    real_init = subprocess.Popen.__init__\n    real_signature = inspect.signature(real_init)\n')
            target = replace_once(target, '        inherited_env = keyword.get("env")\n', '        bound = real_signature.bind(self, args, *positional, **keyword)\n        bound.apply_defaults()\n        options = bound.arguments\n        inherited_env = options.get("env")\n')
            target = replace_once(target, '        if not (same_executable and safe_args and inherited_guard and not keyword.get("shell")):', '        overridden = options.get("executable")\n        safe_override = overridden is None or (isinstance(overridden, str) and os.path.normcase(os.path.realpath(overridden)) == os.path.normcase(os.path.realpath(sys.executable)))\n        if not (same_executable and safe_override and safe_args and inherited_guard and not options.get("shell")):')
        ast.parse(target)
        with (NEW / name).open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(target)
        changes[name] = {'before': hashlib.sha256(source.encode()).hexdigest(), 'after': hashlib.sha256(target.encode()).hexdigest(), 'bytes': len(target.encode())}
    with (HERE / 'green-preparation.json').open('x', encoding='utf-8') as handle:
        json.dump({'observed_at': datetime.now(timezone.utc).isoformat(), 'source': 'agent-report', 'scripts': changes, 'products': expected, 'PM_current_five_files_full_EOF': True, 'popen_signature': str(inspect.signature(subprocess.Popen.__init__)), 'test_execution': False, 'note': 'new PM harness only; old red scripts/evidence untouched; single-source contracts unchanged in protected mirror'}, handle, ensure_ascii=False, indent=2)
    print('new SHA-bound PM runner prepared; no product import or tests executed')
