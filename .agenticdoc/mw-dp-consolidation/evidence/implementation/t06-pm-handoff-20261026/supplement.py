"""Keep original verifier failure/evidence; fresh suite and behavioral boundary checks."""
from __future__ import annotations
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
HERE = Path(__file__).resolve().parent
PKG = HERE.parents[2]/'implementation-worktree/packages/multi-workers'
WT = PKG.parents[1]
assert sys.dont_write_bytecode and not (HERE/'supplement.json').exists()
def sha(value):
    return hashlib.sha256(value).hexdigest()
def inventory():
    return {p.relative_to(WT).as_posix():sha(p.read_bytes()) for p in WT.rglob('*') if p.is_file()}
before = inventory()
env = {k:os.environ[k] for k in ('PATH','SYSTEMROOT','WINDIR') if k in os.environ}
for name in ('HOME','USERPROFILE','TEMP','TMP','TMPDIR'):
    p = HERE/'supplement-fixture'/name.lower()
    p.mkdir(parents=True,exist_ok=True)
    env[name] = str(p)
env.update({'PYTHONDONTWRITEBYTECODE':'1','PYTEST_DISABLE_PLUGIN_AUTOLOAD':'1','PYTHONIOENCODING':'utf-8','PYTHONUTF8':'1'})
argv = [sys.executable,'-B',str(HERE/'bootstrap.py'),'tests']
r = subprocess.run(argv,cwd=PKG,env=env,capture_output=True)
(HERE/'supplement-test.stdout').write_bytes(r.stdout)
(HERE/'supplement-test.stderr').write_bytes(r.stderr)
print('fresh assigned suite rc=',r.returncode)
print(r.stdout.decode('utf-8'));print(r.stderr.decode('utf-8'))
assert r.returncode == 0 and b'65 passed' in r.stdout
# Pure stdlib-only module: no environment/provider/config lookup or I/O.
def deny(*args, **kwargs):
    raise AssertionError('PM T06 pure boundary checks forbid network')
socket.create_connection = deny
socket.socket.connect = deny
socket.socket.connect_ex = deny
sys.path.insert(0,str(PKG))
import decision_validity as d
assert Path(d.__file__).resolve() == PKG/'decision_validity.py'
base = d.matter_for('key-1','key-1','sign',[d.DependencyState('scope','set',['key-1'])],matter_kind='key-signoff',contract_version='v1')
sign = d.SignoffRef('sign-1','finalize','key-1',base.matter_key,base.substantive_version,('key-1',),'fixture-artifact-reference')
ev = d.evidence_for('ev-1','verification',base,('scope',))
req = d.ClaimRequest('worker-1','task-1',('safe.py',))
eff = d.EffectRecord('eff-1','dec-1',base.matter_key,base.substantive_version,('act',),'unknown')
rows = []
def check(name, actual, expected, passed):
    rows.append({'name':name,'actual':asdict(actual),'expected':expected,'boundary_satisfied':passed})
for choice in ('continue','user-confirm'):
    v = d.assess_signoff(replace(sign,choice=choice),base,required_scope=('key-1',))
    check('signoff-'+choice,v,'not valid as required successful signoff',v.status != 'valid')
for name, item in [('wrong-key',replace(sign,key='other-key')),('missing-ref',replace(sign,signoff_ref=None))]:
    v = d.assess_signoff(item,base,required_scope=('key-1',))
    check('signoff-'+name,v,'not valid as bound signoff reference',v.status != 'valid')
v = d.assess_evidence(ev,replace(base,contract_version='v2'))
check('evidence-contract-change',v,'not reusable without current-contract applicability proof',not v.reusable)
v = d.assess_claim([],replace(req,files=('safe.py','../outside.py')))
check('claim-mixed-traversal',v,'invalid requested path blocks the full requested write face',v.status != 'clear')
v = d.assess_claim([d.Claim('worker-1','other-task',('safe.py',))],req)
check('claim-other-task-same-owner',v,'task-specific overlapping active claim is not clear',v.status != 'clear')
for name, status in [('unrecognized','unrecorded'),('missing',None)]:
    v = d.plan_actions([replace(eff,status=status)],matter=base,actions=('act',))
    check('effect-'+name,v,'unknown stored effect status does not permit blind retry',not v.actions)
result = {'observed_at':datetime.now(timezone.utc).isoformat(),'argv':argv,'cwd':str(PKG),'assigned_suite_rc':r.returncode,'assigned_suite_stdout':r.stdout.decode('utf-8'),'boundary_checks':rows,'boundary_failures':sum(not row['boundary_satisfied'] for row in rows),'fixture_references_not_real_authority_or_artifact_proof':True,'historical_red_green_not_rewritten':True,'new_product_changes':False,'verification_net_changes':[]}
assert before == inventory()
(HERE/'supplement.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
# Nonzero is the genuine current behavioral negative result, not runner failure.
raise SystemExit(1 if result['boundary_failures'] else 0)
