"""Readonly close checks: evidence consistency, unchanged products, no phase/authority change."""
from __future__ import annotations
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
HERE = Path(__file__).resolve().parent
KEY = HERE.parents[2]
WT = KEY/'implementation-worktree'
ROOT = KEY.parents[1]
T06 = KEY/'evidence/implementation/t06-pm-handoff-20261026'
assert sys.dont_write_bytecode and not (HERE/'close-verification.json').exists()
def sha(value):
    return hashlib.sha256(value).hexdigest()
def load(path):
    return json.loads(path.read_text(encoding='utf-8'))
expected = load(HERE/'after-inventory.json')
current = {p.relative_to(WT).as_posix():sha(p.read_bytes()) for p in WT.rglob('*') if p.is_file()}
assert current == expected
manifest = load(KEY/'implementation-isolated-dag.json')
# Inspect existing task list rather than change it or rewrite historical observations.
tasks = manifest['tasks']
assert len(tasks) == 36
frontier = [task for task in tasks if task['id'] in ('T06','T07','T08')]
assert len(frontier) == 3
assert all(task['status']=='done' and task['acked'] and not task['semantic_handoff_verified'] for task in frontier)
state = (KEY/'pm-state.md').read_text(encoding='utf-8')
assert '- Phase: EXECUTE' in state and '- Updated: 2026-10-26 20:46' in state
supplement = load(T06/'supplement.json')
assert supplement['assigned_suite_rc'] == 0 and supplement['boundary_failures'] == 9
probes = {item['name']:item for item in load(HERE/'probe.json')['results']}
assert probes['question-limit-one']['exception']['type'] == 'DecisionInputError'
assert probes['question-limit-one']['http_calls'] == []
assert probes['inapplicable-basis']['result']['business_decisions'] == 0
assert probes['inapplicable-basis']['result']['available'] is False
assert probes['inapplicable-basis']['fixture_transport_evidence'][0]['available'] is True
assert probes['replay-unknown-string']['result']['replayed'] is True
assert len(probes['replay-null']['http_calls']) == 1
headers = ('## 结论','## 证据','## 残留与未验证','## 上下文来源','## 改动清单')
reports = {}
for folder in (T06,HERE):
    raw = (folder/'report.md').read_bytes()
    text = raw.decode('utf-8')
    assert all(header in text for header in headers)
    reports[folder.name] = {'bytes':len(raw),'sha256':sha(raw),'required_sections_present':True}
live = {}
for rel in ('packages/multi-workers/decision.py','packages/multi-workers/decision_backends.py','packages/multi-workers/decision_validity.py','packages/multi-workers/decision_policy.py','packages/multi-workers/test_dp_consolidation_concurrency.py','packages/multi-workers/test_dp_consolidation_recovery.py','packages/multi-workers/test_dp_consolidation_materials.py'):
    path = ROOT/rel
    if rel in ('packages/multi-workers/decision.py','packages/multi-workers/decision_backends.py'):
        value = path.read_bytes()
        assert value == (HERE/'live-before-bytes'/rel).read_bytes()
        live[rel] = sha(value)
    else:
        assert not path.exists()
        live[rel] = None
result = {'observed_at':datetime.now(timezone.utc).isoformat(),'rc':0,'mirror_files':len(current),'mirror_equals_t08_after_inventory':True,'verification_net_product_changes':[],'logical_tasks':36,'frontier_semantic_handoff_verified':False,'all_frontier_done_acked':True,'phase':'EXECUTE','reports':reports,'live_exact_seven_paths':live,'full_live_or_historical_no_write_audit':False,'existing_manifest_pending_verification_prose_not_rewritten':True,'new_dispatch_or_rework_or_cleanup':False,'decision_retry_or_receipt':False}
(HERE/'close-verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(result,ensure_ascii=False,indent=2))
