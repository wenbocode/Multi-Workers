"""Focused independent case/template gates. Does not run the still-shared UI suite."""
from datetime import datetime,timezone
import importlib.util
import json
from pathlib import Path
import runpy
import socket
import sys
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];WT=KEY/'implementation-worktree';PKG=WT/'packages/multi-workers';GEN=PKG/'scripts/build_decide_cases.py'
sys.path.insert(0,str(PKG))
def deny(*args,**kwargs):raise AssertionError('no real network permitted in PM isolated gate')
socket.socket.connect=deny;socket.socket.connect_ex=deny;socket.create_connection=deny
import decision_book as books
import decision_points as points
assert Path(books.__file__).resolve().parent==PKG and Path(points.__file__).resolve().parent==PKG
if sys.argv[1]=='generate':
    sys.argv=[str(GEN),'--out',sys.argv[2],'--quiet'];runpy.run_path(str(GEN),run_name='__main__');raise SystemExit(0)
assert sys.argv[1]=='probe'
spec=importlib.util.spec_from_file_location('pm_case_generator',GEN);assert spec and spec.loader;module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
active=('dp-w-type','dp-pm-steer','dp-w-check-task','dp-QG','dp-gate-approve','dp-sign-key','dp-auto','dp-route');assert set(module.CASE_IDS)==set(active)
rows=[]
for dp in active:
    case=json.loads((PKG/'decide_cases'/module.CASE_IDS[dp]).read_text(encoding='utf-8'));book=case['book'];issues=books.check_book(book,project_dir=HERE/'fixture/project',repo_root=WT);assert not issues,(dp,[i.format() for i in issues]);assert case==module.build_case(dp)
    generated=(HERE/'fixture/generator-out'/module.CASE_IDS[dp]).read_bytes();assert generated==(PKG/'decide_cases'/module.CASE_IDS[dp]).read_bytes()
    supported=[c for c in points.resolve_entry_choices(dp,book['material']) if not points.entry_choice_issues(dp,c,book['material'])]
    for choice in supported:
        matches=[i for i in book['preparation']['basis_catalog'] if choice in i['applies_to']];assert matches
        for item in matches:assert not points.prepared_request_issues(dp,book['material'],book['preparation'],choice=choice,basis_id=item['id'],actor_role=book['meta']['actor_role'])
    prepared=datetime.fromisoformat(book['preparation']['prepared_at']);future=prepared>datetime.now(timezone.utc)
    rows.append({'dp':dp,'offline_book_issues':0,'generator_byte_parity':True,'supported_choices':supported,'prepared_at':book['preparation']['prepared_at'],'future_at_PM_observation':future,'timestamp_claims_to_represent_actual_synthesis_in_generator_doc':True})
template=json.loads((PKG/'decide_book_template.json').read_text(encoding='utf-8'));actual=template['books'];failures=[]
if set(actual)!=set(active):failures.append({'code':'template-active-set','expected':list(active),'actual':list(actual)})
for label,book in actual.items():
    issues=books._schema_issues(book)
    if issues:failures.append({'code':'template-schema','label':label,'issues':[i.format() for i in issues]})
controls=[]
for dp in active:
    scaffold=books.scaffold_book(dp);issues=books._schema_issues(scaffold);assert not issues,(dp,issues);controls.append({'dp':dp,'native_scaffold_schema_issues':0})
result={'source':'agent-report','observed_at':datetime.now(timezone.utc).isoformat(),'case_checks':rows,'native_scaffold_positive_controls':controls,'template_failures':failures,'future_prepared_at_cases':[r['dp'] for r in rows if r['future_at_PM_observation']],'case_source_read':{'generator':'full 902 lines read by PM','template':'full 61 lines read by PM','workbench_test':'not read to EOF this turn; assigned suite deferred until full read and T10 terminal'},'original_assigned_suite_not_run':True,'network':'denied','product_writes':False};(HERE/'probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n');print(json.dumps(result,ensure_ascii=False,indent=2));raise SystemExit(1 if failures or any(r['future_at_PM_observation'] for r in rows) else 0)
