"""Hermetic transport seam: real CLI parser/producer, fake backend only."""
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT / 'packages' / 'multi-workers'))
import decision
import decision_points as dpts
import mw

def answer(state, questions, cfg):
    business_id = dpts.get_decision_point('dp-sign-key').questions[0]['id']
    assert set(questions) == {business_id, 'basis_id'}, questions
    catalog = state['preparation']['basis_catalog']
    choice = catalog[0]['applies_to'][0]
    return decision.BackendOutcome(
        available=True, reason=None, retryable=False,
        answers={business_id: {'value': choice, 'confidence': 0.9},
                 'basis_id': {'value': catalog[0]['id'], 'confidence': 0.9}},
        latency_ms=1, detail='',
    )

backend = decision.FakeBackend([answer])
decision.DEFAULT_BACKEND_FACTORY = lambda cfg: backend
if __name__ == '__main__':
    args = mw._parse_args()
    assert args.subcommand == 'decide' and args.decide_action == 'sign'
    sys.exit(mw.cmd_decide(args))
