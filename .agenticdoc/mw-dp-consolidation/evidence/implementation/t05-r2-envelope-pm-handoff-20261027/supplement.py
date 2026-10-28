from datetime import datetime,timezone
import importlib.util,json,socket,sys
from pathlib import Path
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];WT=KEY/'implementation-worktree';PKG=WT/'packages/multi-workers';GEN=PKG/'scripts/build_decide_cases.py'
def deny(*args,**kwargs):raise AssertionError('PM isolated verification denies network')
socket.socket.connect=deny;socket.socket.connect_ex=deny;socket.create_connection=deny;sys.path.insert(0,str(PKG))
import decision_book as books
spec=importlib.util.spec_from_file_location('pm_template_generator',GEN);assert spec and spec.loader;module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
assert Path(books.__file__).resolve().parent==PKG
raw=(PKG/'decide_book_template.json').read_bytes();template=json.loads(raw);assert set(template)=={'books'} and len(template['books'])==8;assert template==module.build_template();assert raw==module.render_template().encode('utf-8')
private=HERE/'fixture/template.json';module.write_template(private);assert private.read_bytes()==raw
rows=[]
for dp,book in template['books'].items():
    assert book==books.scaffold_book(dp);assert not books._schema_issues(book);assert 'meta' not in book and 'state' not in book
    issues=books.check_book(book,project_dir=HERE/'fixture/project',repo_root=WT);assert issues
    for path in books.required_state_paths(dp):
        value=book['material']
        for part in path.split('.'):value=value[part]
        assert books.is_placeholder(value),(dp,path)
    assert book['preparation']['prepared_at']==books.PREPARED_AT_PLACEHOLDER;assert all(books.is_placeholder(v) for v in book['notes']['evidence'].values())
    rows.append({'dp':dp,'exact_native_scaffold':True,'schema_issues':0,'blank_send_refused':True,'refusal_issues':[i.format() for i in issues]})
record=json.loads((KEY/'evidence/implementation/dpc-t05-eight-cases/rework-r2-envelope/prepared-at-record.json').read_text(encoding='utf-8'));assert module.CASE_PREPARED_AT==record['recorded_at_utc'];assert datetime.fromisoformat(module.CASE_PREPARED_AT)<=datetime.now(timezone.utc);assert not record['wall_clock_per_run'] and not record['backfilled_from_run_start']
result={'source':'agent-report','observed_at':datetime.now(timezone.utc).isoformat(),'template_byte_exact_native_generator':True,'private_template_writer_byte_parity':True,'template_controls':rows,'time_matches_preserved_worker_clock_record':True,'record_is_synthetic_fixture_authoring_not_production_authority':True,'no_claim_of_external_clock_attestation_or_exact_historical_authorship':True,'network':'denied','live_products_touched':False};(HERE/'supplement.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n');print(json.dumps(result,ensure_ascii=False,indent=2))
