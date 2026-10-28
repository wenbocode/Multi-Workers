"""Network-denied fresh tests/probes bound to the isolated copy, never live CLI."""
import copy
import json
import pathlib
import socket
import sys
HERE=pathlib.Path(__file__).resolve().parent
KEY=HERE.parents[2];PKG=KEY/'implementation-worktree/packages/multi-workers'
assert sys.dont_write_bytecode
sys.path.insert(0,str(PKG))
def deny(*args,**kwargs):raise AssertionError('PM probe forbids real network')
socket.socket.connect=deny;socket.socket.connect_ex=deny;socket.create_connection=deny
import decision
import decision_book as books
import decision_context
import decision_points as points
for module in (decision,books,decision_context,points):assert pathlib.Path(module.__file__).resolve().parent==PKG
print('BOUND',*[str(m.__file__) for m in (books,decision,points)],flush=True)
if sys.argv[1]=='tests':
    import pytest
    raise SystemExit(pytest.main(['-p','no:cacheprovider','-q',str(PKG/'test_decision_context_contract.py'),'--basetemp',sys.argv[2]]))
assert sys.argv[1]=='probe'
PROJECT=pathlib.Path(sys.argv[2]);PROJECT.mkdir(parents=True,exist_ok=True);(PROJECT/'.git').mkdir(exist_ok=True)
(PROJECT/'notes.txt').write_text('PM independent source\n'*4,encoding='utf-8')
material={'task_goal':'Validate book stdin refusals with full layered requests','task_requirements':'Illegal JSON shapes produce issues, never filesystem lookup or escaped exception','task_deliverables':'Book gate boundary red-green evidence','images_required':False}
preparation={'basis_catalog':[{'id':'pm-checked','text':'Input shape and complete material are the cited business facts','material_refs':['task_goal'],'applies_to':list(points.resolve_entry_choices('dp-w-type',material))}],'prepared_at':'2026-10-27T09:10:00+00:00'}
book={'schema_version':3,'decision_point':'dp-w-type','material':material,'preparation':preparation,'notes':{'evidence':{path:'notes.txt:1' for path in points.REQUIRED_STATE_FIELDS['dp-w-type']}}}
kwargs={'project_dir':PROJECT,'repo_root':PROJECT}
rows=[]
def record(label,fn,predicate):
    try:
        result=fn();ok=predicate(result);rows.append({'label':label,'passed':ok,'result':repr(result)})
    except Exception as exc:
        rows.append({'label':label,'passed':False,'exception':type(exc).__name__,'detail':str(exc)})
record('legal-full-book-positive',lambda:books.prepare_stdin_request(json.dumps(book),**kwargs),lambda pair:pair[0] is not None and pair[1]==())
for value in (None,[],[book],True,17,3.14):
    record('stdin-shape-'+type(value).__name__,lambda v=value:books.prepare_stdin_request(json.dumps(v),**kwargs),lambda pair:pair[0] is None and bool(pair[1]) and pair[1][0].code=='book-schema')
# A JSON string is data, not authority to load a file (one-input-object stdin contract).
path=PROJECT/'book.json';path.write_text(json.dumps(book),encoding='utf-8')
record('stdin-string-is-not-file-authority',lambda:books.prepare_stdin_request(json.dumps(str(path)),**kwargs),lambda pair:pair[0] is None and bool(pair[1]))
record('stdin-bundle-refusal-control',lambda:books.prepare_stdin_request(json.dumps({'books':{'one':book}}),**kwargs),lambda pair:pair[0] is None and bool(pair[1]))
record('stdin-bad-json-refusal-control',lambda:books.prepare_stdin_request('{broken',**kwargs),lambda pair:pair[0] is None and bool(pair[1]))
legacy=PROJECT/'legacy.json';legacy.write_text(json.dumps({'schema_version':2,'decision_point':'dp-w-type','state':material}),encoding='utf-8')
record('invalid-file-report-as-dict-safe',lambda:books.check_book_file(legacy,**kwargs).as_dict(),lambda data:data['ok'] is False and bool(data['issues']))
# Synthetic known-secret sentinels only. A schema refusal must not echo a secret key/value.
known='pm-known-opaque-business-secret'
redactor=decision.known_secret_redactor(extra_secrets=[known])
for layer in ('unknown-top-key','unknown-notes-key','bad-version','unknown-dp'):
    changed=copy.deepcopy(book)
    if layer=='unknown-top-key':changed[known]='x'
    elif layer=='unknown-notes-key':changed['notes'][known]='x'
    elif layer=='bad-version':changed['schema_version']=known
    else:changed['decision_point']=known
    record('schema-secret-refusal-'+layer,lambda b=changed:books.check_book(b,redactor=redactor,**kwargs),lambda issues:bool(issues) and all(known not in issue.format() for issue in issues))
# Exact shape format: boolean and fractional schema must not silently become a legal integer.
for value in (True,3.0):
    changed=copy.deepcopy(book);changed['schema_version']=value
    record('schema-type-'+type(value).__name__,lambda b=changed:books.check_book(b,**kwargs),lambda issues:bool(issues))
result={'fixtures':rows,'passed':sum(row['passed'] for row in rows),'failed':sum(not row['passed'] for row in rows),'product_write_performed':False,'network':'denied'}
(HERE/'probe.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
raise SystemExit(1 if result['failed'] else 0)
