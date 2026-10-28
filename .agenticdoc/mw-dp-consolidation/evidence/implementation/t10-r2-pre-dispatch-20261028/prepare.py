import ast,hashlib,json,os,sys
from datetime import datetime,timezone
from pathlib import Path
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';OSROOT=Path('C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027')
assert not (HERE/'check.json').exists();assert (HERE/'approval.md').is_file()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(n,v):p=HERE/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
mirror={p.relative_to(WT).as_posix():sha(p) for p in WT.rglob('*') if p.is_file()};assert mirror==json.loads((KEY/'evidence/implementation/t05-t10-audit-disposition-20261028/mirror-before.json').read_text(encoding='utf-8'));save('mirror-before.json',mirror);pyc={k:v for k,v in mirror.items() if k.endswith('.pyc')};assert len(pyc)==14;save('pyc-before.json',pyc)
products={};functions={}
for name in ['decision_wire.py','decision_lifecycle.py','decision_task_state.py','test_decision_context_lifecycle.py','test_decision_task_state.py']:
    rel='packages/multi-workers/'+name;p=WT/rel;data=p.read_bytes();out=HERE/'before-bytes'/rel;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data);products[rel]={'bytes':len(data),'sha256':sha(p),'live_sha256':sha(ROOT/rel),'LF':data.count(b'\n'),'CRLF':data.count(b'\r\n')}
    if name.startswith('test_'):
        text=data.decode('utf-8');tree=ast.parse(text);functions[rel]={f.name:{'line':f.lineno,'ast':ast.dump(f,include_attributes=False),'source':ast.get_source_segment(text,f),'assertions':sum(isinstance(n,ast.Assert) for n in ast.walk(f))} for f in tree.body if isinstance(f,(ast.FunctionDef,ast.AsyncFunctionDef))}
save('products-before.json',products);save('old-functions-before.json',functions)
history={}
for directory in ['dpc-t10-lifecycle-state','dpc-t05-eight-cases','t05-r2-envelope-pm-handoff-20261027','t05-t10-audit-disposition-20261028']:
    parent=KEY/'evidence/implementation'/directory
    for p in parent.rglob('*'):
        if p.is_file():history[p.relative_to(KEY).as_posix()]=sha(p)
for name in ['t05-handoff-audit-20261027.md','t10-handoff-audit-20261027.md']:
    p=KEY/'evidence/implementation'/name;history[p.relative_to(KEY).as_posix()]=sha(p)
save('history-before.json',history);dag=json.loads((KEY/'implementation-isolated-dag.json').read_text(encoding='utf-8'));assert len(dag['tasks'])==36 and len(dag['stages'])==7;assert all(next(t for t in dag['tasks'] if t['id']==id)['semantic_handoff_verified'] for id in ['T03','T04','T09']);(HERE/'dag-before.json').write_bytes((KEY/'implementation-isolated-dag.json').read_bytes())
try:os.mkdir(OSROOT)
except FileExistsError:
    save('directory-refusal.json',{'observed_at':datetime.now(timezone.utc).isoformat(),'source':'agent-report','path':str(OSROOT),'status':'blocked-existing-directory','created':False,'reused':False});raise
result={'observed_at':datetime.now(timezone.utc).isoformat(),'source':'agent-report','mkdir_exclusive_success':True,'OS_root':str(OSROOT),'prior_existing_directory_not_reused':True,'approved_by_user_reply_to_specific_question':'继续推进到任务结束','approval_evidence':'evidence/implementation/t10-r2-pre-dispatch-20261028/approval.md','worker_fixture_face':str(OSROOT/'worker-t10-r2')+'/**','PM_fixture_root':str(OSROOT/'pm-verification'),'mirror_files':len(mirror),'protected_pyc':len(pyc),'old_history_files':len(history),'five_products_before':products,'T03_T04_T09_prerequisites_true':True,'source_EOF_not_claimed_by_snapshot_AST':True,'T05_T10_full_handoffs_still_false':True,'no_live_provider_ledger_config_grant_or_deployment_writes':True};save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
