"""Mutant: remove the T05k ``p0_open`` bounds in-process and run the tests that
claim to bind them.

The pre-change source is the baseline itself (see logs/red-new-tests-on-baseline.log);
this mutant isolates the *bound* assertions, including the ones added to
``test_decision_dp25_empty_value.py`` after the GREEN edit, so no assertion is
credited without a failing run. Read-only: only the in-process mapping is
swapped; no file is written.
"""

from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[5]
MW = REPO / "packages" / "multi-workers"
sys.path.insert(0, str(MW))

import decision_points as dpts  # noqa: E402
import pytest  # noqa: E402

NEW_KEYS = ("max_items", "item_type", "item_max_bytes")

mapping = dict(dpts.STATE_FIELD_DESCRIPTIONS)
spec = dict(mapping["p0_open"])
for key in NEW_KEYS:
    spec.pop(key, None)
mapping["p0_open"] = spec
dpts.STATE_FIELD_DESCRIPTIONS = mapping

TARGETS = [
    "test_decision_required_refusal.py::test_p0_open_declares_the_unified_array_bounds",
    "test_decision_required_refusal.py::test_illegal_p0_open_arrays_refuse_with_zero_send_and_zero_snapshot",
    "test_decision_dp25_empty_value.py::test_p0_open_array_bounds_refuse_with_zero_send_and_zero_snapshot",
]

sys.exit(pytest.main([*TARGETS, "-q", "--no-header", "-p", "no:cacheprovider"]))
