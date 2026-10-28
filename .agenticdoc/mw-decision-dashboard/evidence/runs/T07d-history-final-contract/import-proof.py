#!/usr/bin/env python3
"""T07d import proof: which ``decision_history`` a run actually imported.

``python import-proof.py baseline`` imports the untouched pre-change copy in
``red-run/``; without the flag it imports the delivered module. It prints the
resolved file plus the T07d API surface, so a RED run cannot be explained by a
half-fixed module.
"""

from __future__ import annotations

import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
MW = HERE.parents[4] / "packages" / "multi-workers"
BASELINE = len(sys.argv) > 1 and sys.argv[1] == "baseline"

sys.path.insert(0, str(HERE / "red-run") if BASELINE else str(MW))
if BASELINE:
    sys.path.insert(1, str(MW))

import decision_history as history  # noqa: E402

print("mode:", "baseline (unmodified)" if BASELINE else "delivered")
print("imported:", history.__file__)
print("HistoryPage.filters_withheld:", hasattr(history.HistoryPage, "filters_withheld"))
print("HistoryPage.filters_basis:", hasattr(history.HistoryPage, "filters_basis"))
print("HistorySnapshot.redactor:", "redactor" in history.HistorySnapshot.__dataclass_fields__)
capture = {"text": "x", "text_omitted": False, "byte_exact": True, "stored_len": 1}
scrubbed = history._scrub_output(
    capture, __import__("decision_wire").SubstringRedactor(("x",)), withheld=[]
)
print("scrubbed capture:", scrubbed)
