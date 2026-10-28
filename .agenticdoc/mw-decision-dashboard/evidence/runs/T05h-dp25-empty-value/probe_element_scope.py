"""What the *typed* gate does with p0_open element type / length after T05h.

``p0_open`` is one of the "existing arrays" that keep their pre-contract shape
(no ``item_type`` / ``max_items``), so this probe records the actual verdict for
an int element and for an over-long array instead of asserting a guarantee the
registry does not make.
"""

from __future__ import annotations

import pathlib
import sys

MW = pathlib.Path("packages/multi-workers")
sys.path.insert(0, str(MW))

import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402

DP25 = "dp25-signoff-conclusion"


def state(p0):
    return {
        "schema_version": 2,
        "decision_point": DP25,
        "questions_version": dpts.get_decision_point(DP25).questions_version,
        "key": "k-probe",
        "rows_total": 1,
        "rows_available": 1,
        "chain_ok": True,
        "p0_open": p0,
        "rows_escalated": 0,
        "escalated_reasons": [],
        "engine_violations": [],
    }


def book(p0):
    return {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": DP25,
        "state": state(p0),
        "notes": {"evidence": {p: "cmd: true" for p in dpts.REQUIRED_STATE_FIELDS[DP25]}},
    }


for label, value in (
    ("[]", []),
    ("[1]", [1]),
    ("[{}]", [{}]),
    ("33 dp ids", [f"dp{index}" for index in range(33)]),
    ('["<tbd>"]', ["<tbd>"]),
):
    print(
        label,
        "| typed:", dpts.state_field_issues(DP25, state(value)),
        "| book:", [(issue.code, issue.path) for issue in books.check_book(book(value))],
    )

print(
    "p0_open spec:",
    {k: v for k, v in dpts.STATE_FIELD_DESCRIPTIONS["p0_open"].items() if k != "description"},
)
