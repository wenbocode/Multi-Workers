from datetime import datetime,timezone
import ast,hashlib,json
from pathlib import Path
import sys
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];ROOT=KEY.parents[1];WT=KEY/'implementation-worktree';PM=KEY/'evidence/implementation/t05-pm-handoff-20261027';CARD=KEY/'tasks/isolated/T05-eight-cases-r2.md'
assert not (HERE/'check.json').exists()
def sha(b):return hashlib.sha256(b).hexdigest()
def save(n,v):(HERE/n).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
def inv(root):return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
raw=(KEY/'implementation-isolated-dag.json').read_bytes();(HERE/'dag-before.json').write_bytes(raw);(HERE/'pm-state-before.md').write_bytes((KEY/'pm-state.md').read_bytes());dag=json.loads(raw);t05=next(t for t in dag['tasks'] if t['id']=='T05');t10=next(t for t in dag['tasks'] if t['id']=='T10');mirror=inv(WT);assert len(mirror)==1891;save('mirror-inventory.json',mirror)
metadata=[]
for p in t05['product_write_face']:
    f=ROOT/p;rel=f.relative_to(WT);b=f.read_bytes();assert b==(PM/'before-bytes'/rel).read_bytes();dest=HERE/'before-bytes'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(b);metadata.append({'path':p,'bytes':len(b),'sha256':sha(b),'lf':b.count(b'\n'),'crlf':b.count(b'\r\n')})
save('before-metadata.json',metadata)
text=(WT/'packages/multi-workers/test_decision_context_workbench.py').read_text(encoding='utf-8');functions={n.name:{'AST_sha256':sha(ast.dump(n,include_attributes=False).encode('utf-8')),'source_sha256':sha(ast.get_source_segment(text,n).encode('utf-8'))} for n in ast.parse(text).body if isinstance(n,ast.FunctionDef) and n.name.startswith('test_')};save('before-test-functions.json',functions)
original=KEY/'evidence/implementation/dpc-t05-eight-cases';orig_inventory=inv(original);save('original-t05-evidence-protection.json',orig_inventory);save('original-t05-worker-history-protection.json',inv(KEY/'workers/dpc-t05-eight-cases'));save('original-PM-handoff-protection.json',inv(PM));save('T10-products-protection.json',{p:sha((ROOT/p).read_bytes()) for p in t10['product_write_face']})
run5=json.loads((KEY/'workers/dpc-t05-eight-cases/run.json').read_text(encoding='utf-8'));run10=json.loads((KEY/'workers/dpc-t10-lifecycle-state/run.json').read_text(encoding='utf-8'));assert run5['status']=='done' and run5['exit']==0 and run10['status']=='done' and run10['exit']==0;save('original-runs.json',{'T05':run5,'T10':run10});save('pyc-protection-current.json',{p:s for p,s in mirror.items() if p.endswith('.pyc')});assert len([p for p in mirror if p.endswith('.pyc')])==14
current_original={p:s for p,s in orig_inventory.items() if not p.startswith('rework-r2/')};assert current_original==orig_inventory
card=CARD.read_bytes();(HERE/'T05-R2-card.md').write_bytes(card);cf=set(line.strip()[2:] for line in card.decode('utf-8').split('ac_refs:',1)[0].splitlines() if line.strip().startswith('- '));assert cf==set(t05['product_write_face'])|{'.agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t05-eight-cases/rework-r2/**'}
assert inv(WT)==mirror and inv(original)==orig_inventory
result={'source':'agent-report','observed_at':datetime.now(timezone.utc).isoformat(),'T05_original_done_exit0_acked':True,'T10_original_done_exit0_acked':True,'T05_semantic_handoff':False,'logical_tasks':36,'stages':7,'mirror_files':1891,'original_11_product_face_unchanged':True,'R2_before_bytes_saved':11,'current_test_function_count_to_preserve':len(functions),'card_sha256':sha(card),'card_path':'tasks/isolated/T05-eight-cases-r2.md','original_PM_and_worker_evidence_protected':True,'T10_five_current_products_protected':True,'pyc_current_14_preserved_with_prior_drift_not_erased':True,'template_and_timestamp_red_evidence':'evidence/implementation/t05-pm-handoff-20261027/probe.json','no_product_or_DAG_write':True};save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
