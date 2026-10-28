"""Independent PM T06-R2 private suite and exact original nine boundary probes."""
from __future__ import annotations
from dataclasses import asdict, replace
import json
from pathlib import Path
import socket
import sys
HERE = Path(__file__).resolve().parent
PKG = HERE.parents[2]/'implementation-worktree/packages/multi-workers'
assert sys.dont_write_bytecode and Path.cwd().resolve() == PKG
def deny(*args,**kwargs):
    raise AssertionError('PM T06-R2 forbids network')
socket.create_connection = deny
socket.socket.connect = deny
socket.socket.connect_ex = deny
sys.path.insert(0,str(PKG))
import decision_validity as d
assert Path(d.__file__).resolve() == PKG/'decision_validity.py'
if sys.argv[1] == 'tests':
    import pytest
    print('actual module:',d.__file__)
    raise SystemExit(pytest.main(['-p','no:cacheprovider','-q','test_dp_consolidation_concurrency.py']))
assert sys.argv[1] == 'probes' and not (HERE/'probe.json').exists()
base = d.matter_for('key-1','key-1','sign',[d.DependencyState('scope','set',['key-1'])],matter_kind='key-signoff',contract_version='v1')
sign = d.SignoffRef('sign-1','finalize','key-1',base.matter_key,base.substantive_version,('key-1',),'fixture-artifact-reference')
ev = d.evidence_for('ev-1','verification',base,('scope',))
req = d.ClaimRequest('worker-1','task-1',('safe.py',))
eff = d.EffectRecord('eff-1','dec-1',base.matter_key,base.substantive_version,('act',),'unknown')
rows=[]
controls=[]
def add(name,value,passed,target=rows):
    target.append({'name':name,'actual':asdict(value),'passed':passed})
for choice in ('continue','user-confirm'):
    v=d.assess_signoff(replace(sign,choice=choice),base,required_scope=('key-1',))
    add('signoff-'+choice,v,v.status!='valid')
for name,item in [('wrong-key',replace(sign,key='other-key')),('missing-ref',replace(sign,signoff_ref=None))]:
    v=d.assess_signoff(item,base,required_scope=('key-1',))
    add('signoff-'+name,v,v.status!='valid')
v=d.assess_evidence(ev,replace(base,contract_version='v2'))
add('evidence-contract-change',v,not v.reusable)
v=d.assess_claim([],replace(req,files=('safe.py','../outside.py')))
add('claim-mixed-traversal',v,v.status!='clear')
v=d.assess_claim([d.Claim('worker-1','other-task',('safe.py',))],req)
add('claim-other-task-same-owner',v,v.status!='clear')
for name,status in [('unrecognized','unrecorded'),('missing',None)]:
    v=d.plan_actions([replace(eff,status=status)],matter=base,actions=('act',))
    add('effect-'+name,v,not v.actions)
v=d.assess_signoff(sign,base,required_scope=('key-1',))
add('finalize-control',v,v.status=='valid',controls)
for name,item in [('same-contract',ev),('byte-only',replace(ev,byte_sha256='new-byte-trace'))]:
    v=d.assess_evidence(item,base)
    add(name,v,v.reusable,controls)
v=d.assess_claim([d.Claim('worker-1','task-1',('safe.py',))],req)
add('same-task-exclusive-reentry',v,v.status=='clear',controls)
v=d.plan_actions([],matter=base,actions=('act',))
add('no-record-control',v,v.actions==('act',),controls)
for status in ('failed','applied','unknown','in-progress'):
    v=d.plan_actions([replace(eff,status=status)],matter=base,actions=('act',))
    expected='proceed' if status=='failed' else 'already-applied' if status=='applied' else 'blocked'
    add('effect-control-'+status,v,v.status==expected,controls)
result={'module_file':d.__file__,'boundaries':rows,'controls':controls,'boundary_failures':sum(not x['passed'] for x in rows),'control_failures':sum(not x['passed'] for x in controls),'pure_calls_not_real_artifact_authority_claim_or_effect_execution':True,'signoff_contract_binding_and_real_reference_resolution_not_covered':True,'whole_claim_lock_validation_and_production_reentry_still_consumer_responsibility':True}
(HERE/'probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
raise SystemExit(1 if result['boundary_failures'] or result['control_failures'] else 0)
