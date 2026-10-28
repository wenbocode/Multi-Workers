"""Read-only PM boundary reproductions: results are observations, not repairs."""
from __future__ import annotations
import copy
import json
from pathlib import Path
import socket
import sys

HERE = Path(__file__).resolve().parent
KEY = HERE.parents[2]
PKG = KEY / 'implementation-worktree/packages/multi-workers'
sys.path.insert(0, str(PKG))
def deny(*args, **kwargs):
    raise AssertionError('PM probe denies network')
socket.socket.connect = deny
socket.socket.connect_ex = deny
socket.create_connection = deny
import decision_policy as p
assert Path(p.__file__).resolve() == PKG / 'decision_policy.py'
writer = 'fixture-controlled-writer'
trusted = (writer,)
def record(ref, scope):
    result, issues = p.parse_authority_record({'authority_ref':ref,'kind':'user-grant','scope':scope,'writer':writer,'revoked':False,'recorded_at':'2026-10-26T00:00:00Z'},trusted_writers=trusted)
    assert result is not None and not issues
    return result
raw = {'schema_version':1,'authority_ref':'main','scope':['key:allowed'],'hard_limits':[{'unit':'round','limit':2,'usage_source':'fixture-cumulative'}],'recovery':{'allowed_origins':['pm-controlled'],'scope':['recovery:halted','recovery:breaker'],'authority_ref':'rule-ref','observation_conditions':['quiet'],'stop_conditions':['repeat']}}
load = p.parse_policy(raw)
assert load.usable
source = {'main':record('main',['key:allowed','key:outside']),'rule-ref':record('rule-ref',['recovery:halted','recovery:breaker']),'other-ref':record('other-ref',['recovery:halted','recovery:breaker'])}
rows=[]
def observe(name, changed_input, verdict):
    rows.append({'name':name,'changed_input':changed_input,'allowed':verdict.allowed,'scope':getattr(verdict,'scope',getattr(verdict,'resume_scope',getattr(verdict,'release_scope',()))),'reasons':[issue.text() for issue in verdict.reasons]})
base = {'pending_review':True,'goal_effective':True,'blocker_cleared':True,'evidence':['fixture-evidence'],'choice':'approve','required_scope':['key:allowed'],'budget_unit':'round','budget_amount':1}
for name, scope in [('pending-control',['key:allowed']),('pending-outside-policy',['key:outside']),('pending-missing-scope',None)]:
    state = copy.deepcopy(base)
    if scope is None:
        del state['required_scope']
    else:
        state['required_scope']=scope
    observe(name,scope,p.evaluate_pending_review(load,trigger={'kind':'new-evidence'},state=state,usage={'round':0},authority_source=source,trusted_writers=trusted))
halted={'stage_halted':True,'halt_origin':'technical','hard_guard_active':False,'choice':'approve','required_scope':['recovery:halted'],'note':{'stop_reason':'fixture-stop','elimination_evidence':['fixture-clear'],'stage_version':'v1','affected_keys':['fixture-key'],'target_plan':'bounded-fixture-action','authority_ref':'rule-ref','residual_budget':{'round':1},'stop_criterion':'repeat'}}
observe('halted-control',None,p.evaluate_halted_recovery(load,request=halted,usage={'round':1},authority_source=source,trusted_writers=trusted))
for name, changes in [('halted-unverified-guard',{'hard_guard_active':True,'hard_guard_cleared':['self-reported-clear']}),('halted-unknown-origin',{}),('halted-unrelated-authority',{})]:
    request=copy.deepcopy(halted)
    request.update(changes)
    if name=='halted-unknown-origin':
        del request['halt_origin']
    if name=='halted-unrelated-authority':
        request['note']['authority_ref']='other-ref'
    observe(name,changes,p.evaluate_halted_recovery(load,request=request,usage={'round':1},authority_source=source,trusted_writers=trusted))
breaker={'channel':'fixture-isolated','tripped_chain':'auto-pass','origin':'pm-controlled','reason_elimination_evidence':['fixture-clear'],'preauthorization_ref':'rule-ref','machine_checks':{'fixture-check':True},'transport_available':True,'user_disabled':False,'required_scope':['recovery:breaker'],'choice':'approve'}
for name in ('breaker-control','breaker-unrelated-preauthorization','breaker-unknown-disable'):
    request=copy.deepcopy(breaker)
    if name=='breaker-unrelated-preauthorization':
        request['preauthorization_ref']='other-ref'
    if name=='breaker-unknown-disable':
        del request['user_disabled']
    observe(name,request['preauthorization_ref'] if 'preauthorization' in name else None,p.evaluate_breaker_recovery(load,request=request,authority_source=source,trusted_writers=trusted,controlled_channels=('fixture-isolated',)))
result={'policy_file':str(Path(p.__file__).resolve()),'fixture_authority_in_memory_not_production':True,'results':rows}
(HERE/'probe.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
print(json.dumps(result,indent=2,ensure_ascii=False))
