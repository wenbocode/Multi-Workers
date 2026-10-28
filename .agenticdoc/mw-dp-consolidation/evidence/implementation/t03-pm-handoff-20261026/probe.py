"""Pure helper probes, not business requests or production generator output."""
from __future__ import annotations
import json
from pathlib import Path
import socket
import sys

package = Path(sys.argv[1]).resolve()
evidence = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(package))

def no_network(*args, **kwargs):
    raise AssertionError('No network allowed in PM handoff verification')
socket.socket.connect = no_network
socket.create_connection = no_network
import decision_points as dp
import test_dp_consolidation_registry as tests
import test_decide_registry_contract as contract
assert Path(dp.__file__).resolve().parent == package
assert Path(tests.__file__).resolve().parent == package
assert Path(contract.__file__).resolve().parent == package

observations = []
for entry in dp.ACTIVE_DP_IDS:
    material = tests._material(entry)
    prep = tests._preparation(entry, material)
    baseline = dp.prepared_request_issues(entry, material, prep, actor_role=dp.ENTRY_ROLES[entry])
    missing_role = dp.prepared_request_issues(entry, material, prep)
    malformed = dict(prep, prepared_at='not-an-ISO-timestamp')
    malformed_time = dp.preparation_issues(entry, malformed, material)
    observations.append({'entry': entry, 'valid_pre_request_issues': baseline, 'omitted_role_issues': missing_role, 'malformed_timestamp_issues': malformed_time})

# This is a deliberately SYNTHETIC target-shaped input to the existing test,
# not execution of T04's generator and not evidence of TS product acceptance.
synthetic = evidence / 'fixture' / 'eight-entry.synthetic.ts'
synthetic.write_text('export const registry = {\n' + ''.join(f'  "{entry}": {{}},\n' for entry in dp.ACTIVE_DP_IDS) + '};\n', encoding='utf-8')
contract.GENERATED_TS = synthetic
try:
    contract.test_generated_ts_regeneration_belongs_to_t04()
except AssertionError as err:
    future_test = {'synthetic_only': True, 'result': 'rejected-eight-entry-input', 'assertion': str(err)}
else:
    future_test = {'synthetic_only': True, 'result': 'accepted-eight-entry-input'}
result = {'imports': {m.__name__: m.__file__ for m in (dp, tests, contract)}, 'pure_helpers': observations, 'generated_test_transition_probe': future_test, 'network': 'blocked', 'source_writes': False, 'business_requests': False}
(evidence / 'probe.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(json.dumps(result, ensure_ascii=False, indent=2))
