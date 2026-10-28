"""PM literal assigned command, exact added diff, and revoked-rule probe."""
from __future__ import annotations
import difflib
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime,timezone
HERE=Path(__file__).resolve().parent
KEY=HERE.parents[2]
WT=KEY/'implementation-worktree'
PKG=WT/'packages/multi-workers'
ROOT=KEY.parents[1]
assert not (HERE/'supplement.json').exists()
def sha(b):
    return hashlib.sha256(b).hexdigest()
def inventory():
    return {p.relative_to(WT).as_posix():sha(p.read_bytes()) for p in WT.rglob('*') if p.is_file()}
before=inventory()
env={k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR') if k in os.environ}
env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1','DPC_T07_FIXTURE_ROOT':str(HERE/'literal-fixture')})
for name in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR'):
    p=HERE/'literal-fixture'/name.lower()
    p.mkdir(parents=True,exist_ok=True)
    env[name]=str(p)
argv=[sys.executable,'-B','-m','pytest','-p','no:cacheprovider','-q','test_dp_consolidation_recovery.py']
r=subprocess.run(argv,cwd=PKG,env=env,capture_output=True)
(HERE/'pm-literal.stdout').write_bytes(r.stdout)
(HERE/'pm-literal.stderr').write_bytes(r.stderr)
print(r.stdout.decode('utf-8'));print(r.stderr.decode('utf-8'))
assert r.returncode==0 and b'31 passed' in r.stdout
parts=[]
for rel in ('packages/multi-workers/decision_policy.py','packages/multi-workers/test_dp_consolidation_recovery.py'):
    parts.append(''.join(difflib.unified_diff([], (WT/rel).read_text(encoding='utf-8').splitlines(keepends=True),fromfile='/dev/null',tofile='b/'+rel)))
diff=''.join(parts).encode('utf-8')
(HERE/'pm-full.diff').write_bytes(diff)
assert diff==(KEY/'evidence/implementation/dpc-t07-policy/mine.diff').read_bytes()
sys.path.insert(0,str(PKG))
import decision_policy as p
assert Path(p.__file__).resolve()==PKG/'decision_policy.py'
raw={'schema_version':1,'authority_ref':'main','scope':['key:allowed'],'hard_limits':[{'unit':'round','limit':2,'usage_source':'fixture-cumulative'}],'recovery':{'allowed_origins':['controlled'],'scope':['recovery:breaker'],'authority_ref':'rule-ref','observation_conditions':['quiet'],'stop_conditions':['repeat']}}
record,_=p.parse_authority_record({'authority_ref':'other-ref','kind':'user-grant','scope':['recovery:breaker'],'writer':'fixture-writer'},trusted_writers=('fixture-writer',))
revoked,_=p.parse_authority_record({'authority_ref':'rule-ref','kind':'user-grant','scope':['recovery:breaker'],'writer':'fixture-writer','revoked':True},trusted_writers=('fixture-writer',))
request={'channel':'isolated','tripped_chain':'auto-pass','origin':'controlled','reason_elimination_evidence':['fixture-clear'],'preauthorization_ref':'other-ref','machine_checks':{'fixture-check':True},'transport_available':True,'user_disabled':False,'required_scope':['recovery:breaker'],'choice':'approve'}
verdict=p.evaluate_breaker_recovery(p.parse_policy(raw),request=request,authority_source={'other-ref':record,'rule-ref':revoked},trusted_writers=('fixture-writer',),controlled_channels=('isolated',))
after=inventory()
assert before==after
baseline=KEY/'evidence/implementation/s2-frontier-pre-dispatch-20261026/live-before-bytes'
live_rows=[]
for path in baseline.rglob('*'):
    if path.is_file():
        rel=path.relative_to(baseline).as_posix()
        live=ROOT/rel
        live_rows.append({'path':rel,'sha256':sha(live.read_bytes()),'same_as_frontier':live.read_bytes()==path.read_bytes(),'samefile_mirror':os.path.samefile(live,WT/rel)})
result={'observed_at':datetime.now(timezone.utc).isoformat(),'argv':argv,'cwd':str(PKG),'rc':r.returncode,'pm_diff_bytes':len(diff),'pm_diff_sha256':sha(diff),'worker_diff_exact_equal':True,'literal_verification_mirror_changed':False,'live_frontier_existing_counterparts':live_rows,'revoked_policy_recovery_ref_bypassed':{'required_ref':'rule-ref','request_ref':'other-ref','rule_ref_revoked':True,'allowed':verdict.allowed,'scope':verdict.scope,'reasons':[i.text() for i in verdict.reasons]},'fixture_authority_not_production':True}
(HERE/'supplement.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2))
