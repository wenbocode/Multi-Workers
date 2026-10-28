"""Fresh PM T08 verification; private evidence writes, protected mirror/live bytes."""
from __future__ import annotations
from datetime import datetime, timezone
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
HERE = Path(__file__).resolve().parent
KEY = HERE.parents[2]
WT = KEY/'implementation-worktree'
PKG = WT/'packages/multi-workers'
ROOT = KEY.parents[1]
WORKER = KEY/'evidence/implementation/dpc-t08-transport'
OWN = {'packages/multi-workers/decision.py':'89500080e9f59c80e98b757a3a2b547b1db06985edc04a7489d068cb5f80a5e5','packages/multi-workers/decision_backends.py':'a13a8597bba7abe796022148bd50d02b26fc6a85e1d7d3b1af9f5129f0a3e22b','packages/multi-workers/test_dp_consolidation_materials.py':'2ab2d758350eb0a3b714512e9a70d81e14c645459f94cc8c850b98a4638454f8'}
FRONTIER = set(OWN) | {'packages/multi-workers/decision_validity.py','packages/multi-workers/decision_policy.py','packages/multi-workers/test_dp_consolidation_concurrency.py','packages/multi-workers/test_dp_consolidation_recovery.py'}
assert sys.dont_write_bytecode and not (HERE/'check.json').exists()
def sha(value):
    return hashlib.sha256(value).hexdigest()
def inventory():
    return {p.relative_to(WT).as_posix():sha(p.read_bytes()) for p in WT.rglob('*') if p.is_file()}
def save(name, value):
    (HERE/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def bytes_to(label, rel, value):
    dest = HERE/label/rel
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(value)
observed_start = datetime.now(timezone.utc).isoformat()
before = inventory()
save('before-inventory.json',before)
base = json.loads((KEY/'evidence/implementation/s2-frontier-pre-dispatch-20261026/mirror-inventory.json').read_text(encoding='utf-8'))
assert all(isinstance(value,str) for value in base.values())
files = []
live_before = {}
for rel, expected in OWN.items():
    value = (WT/rel).read_bytes()
    assert sha(value) == expected
    bytes_to('before-bytes',rel,value)
    live = ROOT/rel
    if rel in base:
        old = (WORKER/'before-bytes'/rel).read_bytes()
        assert sha(old) == base[rel]
        assert live.exists() and not os.path.samefile(live,WT/rel)
        live_value = live.read_bytes()
        assert live_value == old
        live_before[rel] = sha(live_value)
        bytes_to('live-before-bytes',rel,live_value)
    else:
        old = b''
        assert not live.exists()
        live_before[rel] = None
    files.append({'path':rel,'sha256':sha(value),'bytes':len(value),'crlf':value.count(b'\r\n'),'bare_lf':value.count(b'\n')-value.count(b'\r\n'),'old_bytes':len(old),'old_sha256':sha(old) if old else None,'live_sha256':live_before[rel]})
fixture = HERE/'fixture'
env = {key:os.environ[key] for key in ('PATH','SYSTEMROOT','WINDIR') if key in os.environ}
for name in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR'):
    dest = fixture/name.lower()
    dest.mkdir(parents=True,exist_ok=True)
    env[name] = str(dest)
(fixture/'project').mkdir(parents=True,exist_ok=True)
env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1'})
commands = []
for label, args in [('pm-green',[str(HERE/'bootstrap.py'),'tests']),('pm-literal',['-m','pytest','-p','no:cacheprovider','-q','test_dp_consolidation_materials.py']),('pm-probe',[str(HERE/'bootstrap.py'),'probes'])]:
    argv = [sys.executable,'-B',*args]
    completed = subprocess.run(argv,cwd=PKG,env=env,capture_output=True)
    (HERE/(label+'.stdout')).write_bytes(completed.stdout)
    (HERE/(label+'.stderr')).write_bytes(completed.stderr)
    print(label,'rc=',completed.returncode)
    print(completed.stdout.decode('utf-8'))
    print(completed.stderr.decode('utf-8'))
    commands.append({'label':label,'argv':argv,'cwd':str(PKG),'rc':completed.returncode})
    save('commands.json',commands)
    assert completed.returncode == 0
    if label != 'pm-probe':
        assert b'73 passed' in completed.stdout
    else:
        assert b'PM bound modules' in completed.stdout
after = inventory()
save('after-inventory.json',after)
assert before == after
for rel in OWN:
    bytes_to('after-bytes',rel,(WT/rel).read_bytes())
for rel, expected in live_before.items():
    live = ROOT/rel
    assert (sha(live.read_bytes()) if live.exists() else None) == expected
diff_parts = []
for rel in OWN:
    old = (WORKER/'before-bytes'/rel).read_bytes() if rel in base else b''
    current = (WT/rel).read_bytes()
    part = ''.join(difflib.unified_diff(old.decode('utf-8').splitlines(keepends=True),current.decode('utf-8').splitlines(keepends=True),fromfile='a/'+rel if old else '/dev/null',tofile='b/'+rel)).encode('utf-8')
    bytes_to('diff',rel+'.diff',part)
    diff_parts.append(part)
full_diff = b''.join(diff_parts)
(HERE/'pm-full.diff').write_bytes(full_diff)
drift = sorted(rel for rel in set(base)|set(after) if base.get(rel) != after.get(rel))
outside = [rel for rel in drift if rel not in FRONTIER]
assert len(outside) == 14 and all(rel.endswith('.pyc') for rel in outside)
for rel in outside:
    bytes_to('out-of-face-bytes',rel,(WT/rel).read_bytes())
result = {'observed_start':observed_start,'observed_at':datetime.now(timezone.utc).isoformat(),'commands':commands,'files':files,'baseline_files':len(base),'before_files':len(before),'after_files':len(after),'verification_net_changes':[],'live_exact_paths_unchanged':live_before,'full_live_or_historical_no_write_audit':False,'drift_from_frontier':drift,'out_of_face_drift':outside,'out_of_face_bytes_saved':True,'exclusive_pyc_process_authorship_verified':False,'pm_diff_bytes':len(full_diff),'pm_diff_sha256':sha(full_diff),'semantic_handoff_verified':False,'literal_command_network_hook':False,'bootstrap_network_hook':True}
save('check.json',result)
print(json.dumps(result,ensure_ascii=False,indent=2))
