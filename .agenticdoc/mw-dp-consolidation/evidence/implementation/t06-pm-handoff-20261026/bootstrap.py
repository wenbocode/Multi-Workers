"""PM private T06 pytest bootstrap and observational pure-function probes."""
from __future__ import annotations
from dataclasses import asdict, replace
import json
from pathlib import Path
import socket
import sys

HERE = Path(__file__).resolve().parent
PKG = HERE.parents[2] / 'implementation-worktree/packages/multi-workers'
assert Path.cwd().resolve() == PKG
assert sys.dont_write_bytecode

def deny(*args, **kwargs):
    raise AssertionError('PM T06 verification forbids network')

socket.create_connection = deny
socket.socket.connect = deny
socket.socket.connect_ex = deny
sys.path.insert(0, str(PKG))
import decision_validity as dv
assert Path(dv.__file__).resolve() == PKG / 'decision_validity.py'
print('PM actual imported module:', dv.__file__)
if sys.argv[1] == 'tests':
    import pytest
    raise SystemExit(pytest.main(['-p', 'no:cacheprovider', '-q', 'test_dp_consolidation_concurrency.py']))
assert sys.argv[1] == 'probes'
base = dv.matter_for('key-1', 'key-1', 'sign', [dv.DependencyState('scope', 'set', ['key-1'])], matter_kind='key-signoff', contract_version='v1')
sign = dv.SignoffRef('sign-1', 'finalize', 'key-1', base.matter_key, base.substantive_version, ('key-1',), 'fixture-artifact-reference')
evidence = dv.evidence_for('ev-1', 'verification', base, ('scope',))
rows = []
def add(name, changed_input, result):
    rows.append({'name':name, 'changed_input':changed_input, 'verdict':asdict(result)})
add('evidence-control', None, dv.assess_evidence(evidence, base))
add('evidence-contract-only-changed', {'contract_version':'v2'}, dv.assess_evidence(evidence, replace(base, contract_version='v2')))
add('signoff-control', None, dv.assess_signoff(sign, base, required_scope=('key-1',)))
for choice in ('continue', 'user-confirm'):
    add('signoff-nonfinalize-'+choice, {'choice':choice}, dv.assess_signoff(replace(sign, choice=choice), base, required_scope=('key-1',)))
add('signoff-wrong-key', {'key':'other-key'}, dv.assess_signoff(replace(sign, key='other-key'), base, required_scope=('key-1',)))
add('signoff-missing-reference', {'signoff_ref':None}, dv.assess_signoff(replace(sign, signoff_ref=None), base, required_scope=('key-1',)))
add('signoff-contract-only-changed', {'current_contract_version':'v2'}, dv.assess_signoff(sign, replace(base, contract_version='v2'), required_scope=('key-1',)))
req = dv.ClaimRequest('worker-1', 'task-1', ('safe.py',))
add('claim-control', None, dv.assess_claim([], req))
add('claim-mixed-traversal', {'files':['safe.py','../outside.py']}, dv.assess_claim([], replace(req, files=('safe.py','../outside.py'))))
add('claim-same-owner-other-task', {'claims':[{'owner':'worker-1','task_key':'other-task','files':['safe.py']}]}, dv.assess_claim([dv.Claim('worker-1','other-task',('safe.py',))], req))
effect = dv.EffectRecord('eff-1','dec-1',base.matter_key,base.substantive_version,('act',),'unknown')
add('effect-unknown-control', {'status':'unknown'}, dv.plan_actions([effect], matter=base, actions=('act',)))
add('effect-unrecognized-state', {'status':'unrecorded'}, dv.plan_actions([replace(effect,status='unrecorded')], matter=base, actions=('act',)))
add('effect-missing-state', {'status':None}, dv.plan_actions([replace(effect,status=None)], matter=base, actions=('act',)))
result = {'module_file':dv.__file__, 'fixture_refs_not_real_authority_or_artifacts':True, 'observations_only_no_effect_execution':True, 'results':rows}
assert not (HERE/'probe.json').exists()
(HERE/'probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
