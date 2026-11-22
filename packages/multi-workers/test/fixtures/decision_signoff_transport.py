"""Run the production sign CLI with a single, offline prepared response."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import decision
import decision_backends
import mw


def answer(state, questions, _config):
    assert "preparation" not in state
    question = decision_backends.PREPARED_SELECTION_QUESTION_ID
    assert set(questions) == {question}
    wire_id = os.environ["MW_TEST_SIGN_CHOICE"] + "A"
    assert wire_id in questions[question]["choices"]
    return decision.BackendOutcome(
        available=True,
        reason=None,
        retryable=False,
        answers={question: {"value": wire_id, "confidence": 0.9}},
        latency_ms=1,
    )


if __name__ == "__main__":
    args = mw._parse_args()
    assert args.subcommand == "decide" and args.decide_action == "sign"
    decision.DEFAULT_BACKEND_FACTORY = lambda _config: decision.FakeBackend([answer])
    sys.exit(mw.cmd_decide(args))
