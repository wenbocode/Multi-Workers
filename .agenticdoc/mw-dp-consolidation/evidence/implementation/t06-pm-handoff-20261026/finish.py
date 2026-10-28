"""Complete PM inventory evidence after check.py's schema-assumption error.
Do not rerun or overwrite original test/probe logs or the failing verifier.
"""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
HERE=Path(__file__).resolve().parent
KEY=HERE.parents[2]
WT=KEY/'implementation-worktree'
assert sys.dont_write_bytecode and not (HERE/'check.json').exists()
def sha(b):
    return hashlib.sha256(b).hexdigest()
before=json.loads((HERE/'before-inventory.json').read_text(encoding='utf-8'))
after=json.loads((HERE/'after-inventory.json').read_text(encoding='utf-8'))
current={p.relative_to(WT).as_posix():sha(p.read_bytes()) for p in WT.rglob('*') if p.is_file()}
assert before==after==current
base=json.loads((KEY/'evidence/implementation/s2-frontier-pre-dispatch-20261026/mirror-inventory.json').read_text(encoding='utf-8'))
assert all(isinstance(v,str) and len(v)==64 for v in base.values())
faces={'packages/multi-workers/decision_validity.py','packages/multi-workers/test_dp_consolidation_concurrency.py','packages/multi-workers/decision_policy.py','packages/multi-workers/test_dp_consolidation_recovery.py','packages/multi-workers/decision.py','packages/multi-workers/decision_backends.py','packages/multi-workers/test_dp_consolidation_materials.py'}
drift=sorted(p for p in set(base)|set(current) if base.get(p)!=current.get(p))
outside=[p for p in drift if p not in faces]
assert len(outside)==14 and all(p.endswith('.pyc') for p in outside)
for rel in outside:
    p=HERE/'out-of-face-bytes'/rel
    p.parent.mkdir(parents=True,exist_ok=True)
    p.write_bytes((WT/rel).read_bytes())
for label in ('pm-green','pm-literal'):
    assert b'65 passed' in (HERE/(label+'.stdout')).read_bytes()
    assert (HERE/(label+'.stderr')).read_bytes()==b''
probe=json.loads((HERE/'probe.json').read_text(encoding='utf-8'))
assert len(probe['results'])==14
files=[]
for rel in sorted(faces):
    if 'decision_validity.py' in rel or 'test_dp_consolidation_concurrency.py' in rel:
        b=(WT/rel).read_bytes()
        assert b==(HERE/'before-bytes'/rel).read_bytes()==(HERE/'after-bytes'/rel).read_bytes()
        files.append({'path':rel,'sha256':sha(b),'bytes':len(b),'crlf':b.count(b'\r\n'),'bare_lf':b.count(b'\n')-b.count(b'\r\n')})
result={'observed_at':datetime.now(timezone.utc).isoformat(),'initial_verifier_rc':1,'initial_verifier_failure':'check.py:71 TypeError: string indices must be integers, not str; incorrectly expected metadata records where baseline stores SHA strings','original_verifier_source_sha256':sha((HERE/'check.py').read_bytes()),'original_test_and_probe_command_rc':{'pm-green':0,'pm-literal':0,'pm-probe':0},'tests':{'pm-green':'65 passed in 0.12s','pm-literal':'65 passed in 0.14s'},'finish_reruns_tests':False,'files':files,'baseline_files':len(base),'before_files':len(before),'after_files':len(after),'finish_current_files':len(current),'verification_net_changes':[],'drift_from_frontier':drift,'out_of_face_drift':[{'path':p,'sha256':current[p]} for p in outside],'out_of_face_bytes_saved':True,'pyc_attribution':'existence independently observed; T08 self-report, not exclusive process authorship','pm_diff_bytes':len((HERE/'pm-full.diff').read_bytes()),'pm_diff_sha256':sha((HERE/'pm-full.diff').read_bytes()),'semantic_handoff_verified':False,'full_live_or_historical_no_write_audit':False}
(HERE/'check.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
