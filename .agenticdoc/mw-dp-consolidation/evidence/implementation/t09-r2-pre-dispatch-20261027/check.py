"""Preserve current T09 failed-handoff bytes/history before a bounded original-face R2."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
assert sys.dont_write_bytecode
HERE=Path(__file__).resolve().parent;KEY=HERE.parents[2];WT=KEY/'implementation-worktree';PM=KEY/'evidence/implementation/t09-pm-handoff-20261027'
assert not (HERE/'check.json').exists()
def sha(b):return hashlib.sha256(b).hexdigest()
def inventory(root):return {p.relative_to(root).as_posix():sha(p.read_bytes()) for p in root.rglob('*') if p.is_file()}
def save(name,data):(HERE/name).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
mirror=inventory(WT);assert mirror==json.loads((PM/'mirror-before.json').read_text(encoding='utf-8'));save('mirror-inventory.json',mirror)
assert inventory(KEY/'evidence/implementation/dpc-t09-books')==json.loads((PM/'worker-evidence-inventory.json').read_text(encoding='utf-8'))
assert inventory(KEY/'workers/dpc-t09-books')==json.loads((PM/'worker-history-inventory.json').read_text(encoding='utf-8'))
for product in json.loads((PM/'check.json').read_text(encoding='utf-8'))['products']:
    rel=product['path'];data=(WT/rel).read_bytes();assert sha(data)==product['after_sha256'];dest=HERE/'before-bytes'/rel;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(data)
for name in ('pm-state.md','implementation-isolated-dag.json'):(HERE/(name+'.before')).write_bytes((KEY/name).read_bytes())
card=KEY/'tasks/isolated/T09-books-r2.md';card_bytes=card.read_bytes();(HERE/'T09-books-r2.md').write_bytes(card_bytes)
save('t09-original-evidence-inventory.json',inventory(KEY/'evidence/implementation/dpc-t09-books'));save('t09-original-worker-inventory.json',inventory(KEY/'workers/dpc-t09-books'))
result={'source':'agent-report','observed_at':datetime.now(timezone.utc).isoformat(),'mirror_files':len(mirror),'mirror_net_changes_since_PM_verification':[],'card_sha256':sha(card_bytes),'logical_task':'T09','attempt':'R2','assigned_PM_runs_passed':109,'real_independent_fixture_failures':13,'local_handoff_verified':False,'original_attempt_status':'done/exit0/acked','original_history_preserved':True,'only_existing_two_product_faces':True,'dispatch_done':False};save('check.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))
