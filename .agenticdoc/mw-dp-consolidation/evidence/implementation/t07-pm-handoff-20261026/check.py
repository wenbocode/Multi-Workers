"""Fresh PM T07 verification with private artifacts and peer-aware net scope."""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
HERE=Path(__file__).resolve().parent
KEY=HERE.parents[2]
ROOT=KEY.parents[1]
WT=KEY/'implementation-worktree'
PKG=WT/'packages/multi-workers'
assert not (HERE/'check.json').exists(),'refuse overwrite'
def sha(b):
    return hashlib.sha256(b).hexdigest()
def inventory(root):
    return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
baseline=json.loads((KEY/'evidence/implementation/s2-frontier-pre-dispatch-20261026/mirror-inventory.json').read_text(encoding='utf-8'))
before=inventory(WT)
(HERE/'before-inventory.json').write_text(json.dumps(before,indent=2)+'\n',encoding='utf-8')
peer={'packages/multi-workers/'+p for p in ('decision_validity.py','test_dp_consolidation_concurrency.py','decision.py','decision_backends.py','test_dp_consolidation_materials.py')}
mine={'packages/multi-workers/decision_policy.py':'f4c44456316b8c60c7934a209de389ef6366aa864f026f9ba5fba40569dde6bb','packages/multi-workers/test_dp_consolidation_recovery.py':'434412b3ea60e60807ea23b52cdc474e892457a0a1747ecf7cb6bf809380a974'}
files=[]
for rel,expected in mine.items():
    body=(WT/rel).read_bytes()
    assert sha(body)==expected and rel not in baseline
    assert not (ROOT/rel).exists()
    dest=HERE/'after-bytes'/rel
    dest.parent.mkdir(parents=True,exist_ok=True)
    dest.write_bytes(body)
    files.append({'path':rel,'sha256':sha(body),'bytes':len(body),'crlf':body.count(b'\r\n'),'bare_lf':body.count(b'\n')-body.count(b'\r\n'),'live_exists':False})
fixture=HERE/'fixture'
fixture.mkdir()
env={name:os.environ[name] for name in ('PATH','SYSTEMROOT','WINDIR') if name in os.environ}
env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1','DPC_T07_FIXTURE_ROOT':str(fixture)})
for name in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR'):
    target=fixture/name.lower()
    target.mkdir(exist_ok=True)
    env[name]=str(target)
commands=[]
for label,script in (('pm-green','bootstrap.py'),('pm-probe','probe.py')):
    argv=[sys.executable,'-B',str(HERE/script)]
    proc=subprocess.run(argv,cwd=PKG,env=env,capture_output=True)
    (HERE/(label+'.stdout')).write_bytes(proc.stdout)
    (HERE/(label+'.stderr')).write_bytes(proc.stderr)
    print(label,'rc=',proc.returncode)
    print(proc.stdout.decode('utf-8'))
    print(proc.stderr.decode('utf-8'))
    commands.append({'label':label,'argv':argv,'cwd':str(PKG),'rc':proc.returncode})
    assert proc.returncode==0
assert b'31 passed' in (HERE/'pm-green.stdout').read_bytes()
after=inventory(WT)
(HERE/'after-inventory.json').write_text(json.dumps(after,indent=2)+'\n',encoding='utf-8')
drift=[p for p in sorted(set(baseline)|set(before)) if baseline.get(p)!=before.get(p)]
unexpected=[p for p in drift if p not in peer and p not in mine]
verification_changes=[p for p in sorted(set(before)|set(after)) if before.get(p)!=after.get(p)]
for rel,expected in mine.items():
    assert after.get(rel)==expected
assert not [p for p in verification_changes if p not in peer],verification_changes
pyc=[{'path':p,'sha256':after[p]} for p in after if p.endswith('.pyc')]
result={'observed_at':datetime.now(timezone.utc).isoformat(),'commands':commands,'files':files,'baseline_files':len(baseline),'before_files':len(before),'after_files':len(after),'drift_from_frontier':drift,'peer_authorized_face_not_authorship_proof':sorted(peer),'out_of_face_drift':unexpected,'verification_net_changes':verification_changes,'pyc':pyc,'pyc_attribution':'T08 self-reports unguarded python-c at20-16-49; independent exclusive process attribution not proven','semantic_handoff_verified':False,'whole_source_or_live_audit':False}
(HERE/'check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
