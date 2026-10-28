"""Mutant: make the snapshot writer ignore ``material_refused`` (the pre-T05k
N1 behaviour, where the required-refusal branch stored its candidate).

The authoritative pre-fix evidence is the real baseline RED run
(``logs/red-new-tests-on-baseline.log``); this in-process mutant additionally
proves the N1 assertions fail when the flag stops being honoured. Read-only.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[5]
MW = REPO / "packages" / "multi-workers"
sys.path.insert(0, str(MW))

import decision_points as dpts  # noqa: E402
import pytest  # noqa: E402

original = dpts._DecisionCapture._snapshot_document


def ignoring_flag(self):
    flag = self.material_refused
    self.material_refused = False
    try:
        return original(self)
    finally:
        self.material_refused = flag


dpts._DecisionCapture._snapshot_document = ignoring_flag

TARGETS = [
    "test_decision_required_refusal.py::test_required_refusal_stores_no_snapshot_and_keeps_the_decision_end_fact",
    "test_decision_required_refusal.py::test_required_refusal_and_typed_refusal_share_the_same_ledger_shape",
    "test_decision_required_refusal.py::test_required_refusal_never_reads_or_stores_a_real_credential",
    "test_decision_dp25_empty_value.py::test_missing_or_null_p0_open_refuses_with_zero_send",
]

sys.exit(pytest.main([*TARGETS, "-q", "--no-header", "-p", "no:cacheprovider"]))
