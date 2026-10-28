"""Create fresh independent PM runners; never modify product or worker evidence."""
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
KEY=HERE.parents[2]
assert sys.dont_write_bytecode
old=KEY/'evidence/implementation/t07-pm-handoff-20261026'
bootstrap=(old/'bootstrap.py').read_text(encoding='utf-8')
(HERE/'bootstrap.py').write_text(bootstrap,encoding='utf-8',newline='\n')
probe=(old/'probe.py').read_text(encoding='utf-8')
anchor="result={'policy_file':str(Path(p.__file__).resolve()),'fixture_authority_in_memory_not_production':True,'results':rows}"
extra='''
revoked=p.AuthorityRecord('rule-ref','user-grant',('recovery:halted','recovery:breaker'),writer,True)
revoked_source=dict(source, **{'rule-ref':revoked})
request=copy.deepcopy(breaker);request['preauthorization_ref']='other-ref'
observe('breaker-revoked-rule-bypass',None,p.evaluate_breaker_recovery(load,request=request,authority_source=revoked_source,trusted_writers=trusted,controlled_channels=('fixture-isolated',)))
request=copy.deepcopy(halted);request['note']['authority_ref']='other-ref'
observe('halted-revoked-rule-bypass',None,p.evaluate_halted_recovery(load,request=request,usage={'round':1},authority_source=revoked_source,trusted_writers=trusted))
lift=p.AuthorityRecord('human-lift','user-grant',('recovery:user-stop','recovery:halted'),writer)
lift_source=dict(source, **{'human-lift':lift})
request=copy.deepcopy(halted);request['halt_origin']='user-stop';request['note']['authority_ref']='human-lift'
observe('h11-fresh-human-control',None,p.evaluate_halted_recovery(load,request=request,usage={'round':1},authority_source=lift_source,trusted_writers=trusted))
observe('h11-revoked-rule-unrelated-lift',None,p.evaluate_halted_recovery(load,request=request,usage={'round':1},authority_source=dict(revoked_source, **{'human-lift':lift}),trusted_writers=trusted))
replacement=p.AuthorityRecord('human-restore','user-grant',('recovery:user-stop','recovery:halted'),writer,supersedes=('rule-ref',))
request['note']['authority_ref']='human-restore'
observe('h11-explicit-restoration-control',None,p.evaluate_halted_recovery(load,request=request,usage={'round':1},authority_source=dict(revoked_source, **{'human-restore':replacement}),trusted_writers=trusted))
request=copy.deepcopy(halted);request.update(hard_guard_active=True,hard_guard_cleared=['fixture-machine-result'],hard_guard_cleared_verified=True)
observe('machine-guard-control',None,p.evaluate_halted_recovery(load,request=request,usage={'round':1},authority_source=source,trusted_writers=trusted))
for name,changes in [('halted-null-guard',{'hard_guard_active':None}),('halted-string-guard',{'hard_guard_active':'false'}),('halted-string-verified',{'hard_guard_active':True,'hard_guard_cleared':['self-report'],'hard_guard_cleared_verified':'true'})]:
    request=copy.deepcopy(halted);request.update(changes)
    observe(name,changes,p.evaluate_halted_recovery(load,request=request,usage={'round':1},authority_source=source,trusted_writers=trusted))
for name,changes in [('breaker-disabled',{'user_disabled':True}),('breaker-null-disable',{'user_disabled':None}),('breaker-string-disable',{'user_disabled':'false'}),('breaker-null-origin',{'origin':None})]:
    request=copy.deepcopy(breaker);request.update(changes)
    observe(name,changes,p.evaluate_breaker_recovery(load,request=request,authority_source=source,trusted_writers=trusted,controlled_channels=('fixture-isolated',)))
controls={'pending-control','halted-control','breaker-control','h11-fresh-human-control','h11-explicit-restoration-control','machine-guard-control'}
failures=[row for row in rows if row['allowed'] != (row['name'] in controls) or (row['name'] in controls and not row['scope'])]
result={'policy_file':str(Path(p.__file__).resolve()),'fixture_authority_in_memory_not_production':True,'results':rows,'failures':failures,'control_count':len(controls),'negative_count':len(rows)-len(controls)}
'''
assert probe.count(anchor)==1
probe=probe.replace(anchor,extra)+"\nassert not failures, failures\n"
(HERE/'probe.py').write_text(probe,encoding='utf-8',newline='\n')
print('Fresh runners created; not executed')
