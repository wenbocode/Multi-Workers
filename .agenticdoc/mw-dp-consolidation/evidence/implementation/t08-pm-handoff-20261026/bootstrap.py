"""Evidence-only PM T08 assigned-suite runner and fake-HTTP boundary probes."""
from __future__ import annotations
import json
from pathlib import Path
import socket
import sys
import urllib.request

HERE = Path(__file__).resolve().parent
PKG = HERE.parents[2] / 'implementation-worktree/packages/multi-workers'
assert sys.dont_write_bytecode and Path.cwd().resolve() == PKG

def deny(*args, **kwargs):
    raise AssertionError('PM T08 forbids real network')
socket.create_connection = deny
socket.socket.connect = deny
socket.socket.connect_ex = deny
urllib.request.urlopen = deny
sys.path.insert(0, str(PKG))
import decision as d
import decision_backends as b
import decision_points as p
for module in (d, b, p):
    assert Path(module.__file__).resolve().parent == PKG
print('PM bound modules:', d.__file__, b.__file__, p.__file__)
if sys.argv[1] == 'tests':
    import pytest
    raise SystemExit(pytest.main(['-p','no:cacheprovider','-q','test_dp_consolidation_materials.py']))
assert sys.argv[1] == 'probes'
assert not (HERE / 'probe.json').exists()
material = {'task_goal':'verify one transport pair','task_requirements':'use only prepared basis','task_deliverables':'fixture response','images_required':False}
choices = list(p.resolve_entry_choices('dp-w-type', material))
preparation = {'basis_catalog':[{'id':'basis-control','text':'fixture prepared reason','material_refs':['task_goal'],'applies_to':choices},{'id':'basis-other','text':'fixture applicable only to another choice','material_refs':['task_goal'],'applies_to':choices[1:]}], 'prepared_at':'2026-10-26T12:00:00+00:00'}
rows = []

def run(name, *, basis='basis-control', replay_value=False, replay=False, max_questions=None, dp='dp-w-type'):
    root = HERE / 'fixture/probes' / name
    root.mkdir(parents=True, exist_ok=True)
    cfg_args = {'enabled':True,'transport':'timi-decisions','model':'jev-latest','project_root':root,'evidence_path':root / 'triage-decisions.jsonl','backoff_base_s':0.0}
    if max_questions is not None:
        cfg_args['max_questions'] = max_questions
    cfg = d.DecisionConfig(**cfg_args)
    cfg.api_key = 'pm-t08-synthetic-key-0123456789'
    client = d.DecisionClient(cfg, sleep=lambda seconds: None)
    calls = []
    lookups = []
    def fake_post(url, headers, payload, timeout_s):
        calls.append({'url':url,'model':payload.get('model'),'question_ids':list(payload.get('questions',{}))})
        body = {'model':'jev-latest','answers':{'triage_type':{'type':'choice','choice':choices[0],'confidence':0.9},'basis_id':{'type':'choice','choice':basis,'confidence':0.9}}}
        return b.HttpResponse(200,'application/json',json.dumps(body))
    def lookup(dp_id, logical_id):
        lookups.append({'dp':dp_id,'logical_id':logical_id,'returned':replay_value})
        return replay_value
    b._http_post = fake_post
    kwargs = {'actor_role':'pm'}
    if replay:
        kwargs.update({'logical_id':'fixture-logical-id','replay_check':lookup})
    try:
        result = client.request_prepared(dp, material, preparation, **kwargs)
        error = None
    except Exception as exc:
        result = None
        error = {'type':type(exc).__name__,'message':str(exc)}
    ledger = root / 'triage-decisions.jsonl'
    records = [json.loads(line) for line in ledger.read_text(encoding='utf-8').splitlines()] if ledger.exists() else []
    rows.append({'name':name,'basis':basis,'max_questions':max_questions,'result':result,'exception':error,'http_calls':calls,'replay_lookups':lookups,'fixture_transport_evidence':records})

run('valid-pair-control')
run('inapplicable-basis', basis='basis-other')
run('question-limit-one', max_questions=1)
run('replay-true-control', replay=True, replay_value=True)
run('replay-unknown-string', replay=True, replay_value='unknown')
run('replay-null', replay=True, replay_value=None)
result = {'observed_only':True,'no_business_effects_or_production_authority':True,'modules':{m.__name__:m.__file__ for m in (d,b,p)},'legal_choices':choices,'results':rows}
(HERE/'probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
