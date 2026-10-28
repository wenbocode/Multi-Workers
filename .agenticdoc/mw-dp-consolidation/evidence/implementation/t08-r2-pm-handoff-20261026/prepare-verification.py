"""Create new evidence-only scripts; preserve original probes and worker records."""
from pathlib import Path
import sys
assert sys.dont_write_bytecode
here=Path(__file__).resolve().parent
source=(here.parent/'t08-pm-handoff-20261026/bootstrap.py').read_text(encoding='utf-8')
source=source.replace("for module in (d, b, p):", "for module in (d, b, p):")
source=source.replace("'fixture_transport_evidence':records}", "'fixture_transport_evidence':records,'ceiling_after':client.cfg.max_questions}")
needle="result = {'observed_only':True"
assert needle in source
extra='''
for index, value in enumerate(('true','false',1,0,[],{})):
    run('nonbool-'+str(index), replay=True, replay_value=value)
run('replay-false-control', replay=True, replay_value=False)
run('ceiling-two-control', max_questions=2)
for index in range(1,26):
    run('retired-'+str(index), dp=str(p.RETIRED_DP_IDS[index-1]) if hasattr(p,'RETIRED_DP_IDS') else 'dp'+str(index), replay=True, replay_value=True)
failures=[]
for row in rows:
    name=row['name'];r=row['result'];calls=row['http_calls'];records=row['fixture_transport_evidence']
    ok=row['exception'] is None and isinstance(r,dict)
    if name=='question-limit-one':
        ok=ok and r['available'] is False and r['reason']=='budget-exhausted' and r['business_decisions']==0 and r['attempts']==0 and r['transport_attempts']==0 and not calls and row['ceiling_after']==1
    elif name.startswith('nonbool-') or name in ('replay-unknown-string','replay-null'):
        ok=ok and r['available'] is False and r['reason']=='entry-unavailable' and r['replayed'] is False and r['business_decisions']==0 and not calls and len(row['replay_lookups'])==1
    elif name.startswith('retired-'):
        ok=ok and r['available'] is False and r['reason']=='entry-unavailable' and 'retired' in r['detail'] and r['business_decisions']==0 and not calls and not row['replay_lookups']
    elif name=='replay-true-control':
        ok=ok and r['available'] is True and r['replayed'] is True and r['business_decisions']==0 and not calls
    elif name=='inapplicable-basis':
        ok=ok and r['available'] is False and r['reason']=='bad-response' and r['business_decisions']==0 and len(calls)==1 and len(records)==1 and records[0]['available'] is True and set(records[0])==set(d._EVIDENCE_FIELDS)
    else:
        ok=ok and r['available'] is True and r['business_decisions']==1 and len(calls)==1 and calls[0]['model']=='jev-latest' and len(calls[0]['question_ids'])==2 and calls[0]['url'].endswith('/v1/decisions')
    if not ok:failures.append(name)
assert not failures,failures
'''
# Use the authoritative retired identity list, not invented shortened ids.
extra=extra.replace("str(p.RETIRED_DP_IDS[index-1]) if hasattr(p,'RETIRED_DP_IDS') else 'dp'+str(index)", "list(p.retired_dp_ids())[index-1]") if 'def retired_dp_ids(' in (here.parents[2]/'implementation-worktree/packages/multi-workers/decision_points.py').read_text(encoding='utf-8') else extra
# The assigned test owns the exact historical identity inventory; parse its literal.
import ast
pkg=here.parents[2]/'implementation-worktree/packages/multi-workers'
tree=ast.parse((pkg/'test_dp_consolidation_materials.py').read_text(encoding='utf-8'))
retired=None
for node in tree.body:
    if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='RETIRED_25' for t in node.targets):
        retired=ast.literal_eval(node.value)
assert retired is not None and len(retired)==25
extra=extra.replace("list(p.retired_dp_ids())[index-1]",repr(list(retired))+"[index-1]").replace("str(p.RETIRED_DP_IDS[index-1]) if hasattr(p,'RETIRED_DP_IDS') else 'dp'+str(index)",repr(list(retired))+"[index-1]")
source=source.replace(needle,extra+'\n'+needle)
dest=here/'bootstrap.py';assert not dest.exists();dest.write_text(source,encoding='utf-8',newline='\n')
print('created evidence bootstrap with 39 independently asserted fixtures')
