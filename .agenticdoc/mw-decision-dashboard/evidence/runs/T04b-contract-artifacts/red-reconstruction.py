"""T04b: reconstruct the pre-fix RED from the old inputs (no repo mutation).

The RED run itself was observed before the write (44 failed / 351 passed); this
script makes the same conclusion reproducible afterwards by feeding the *old*
probe table and the *pre-T04b* template to the same assertions:

1. with the 82 new probe values removed, every dp4..dp24 probe raises
   ``ValueError: no probe value for required state path ...``;
2. the pre-T04b template (``git show HEAD:packages/multi-workers/decide_book_template.json``)
   is not the current ``scaffold_book(dp6)`` render.

Run from packages/multi-workers.
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys

sys.path.insert(0, str(pathlib.Path.cwd()))

import decision_book as books  # noqa: E402
import mw  # noqa: E402

DP6 = "dp6-qg-verdict"
PRESERVED = {"dp1-dispatch-type", "dp2-checkpoint-split", "dp3-worker-clarify", "dp25-signoff-conclusion"}
#: The entries the shipped table carried before T04b (dp1/dp2/dp3 + dp25 facts).
OLD_PATHS = frozenset(
    {
        "schema_version",
        "key",
        "phase",
        "task_type",
        "requested_type",
        "risk",
        "risk_source",
        "scope.write_scope",
        "scope.file_extensions",
        "progress.elapsed_minutes",
        "progress.budget_minutes",
        "progress.phases_done",
        "progress.phases_total",
        "progress.artifact_present",
        "ambiguity.kind",
        "local_candidates",
        "rows_total",
        "rows_available",
        "chain_ok",
        "p0_open",
    }
)


def old_table() -> dict[str, object]:
    return {path: value for path, value in mw._DP_VERIFY_STATE_VALUES.items() if path in OLD_PATHS}


def probe_gaps() -> list[str]:
    rows: list[str] = []
    old = old_table()
    saved = dict(mw._DP_VERIFY_STATE_VALUES)
    try:
        mw._DP_VERIFY_STATE_VALUES.clear()
        mw._DP_VERIFY_STATE_VALUES.update(old)
        for point in mw._dp_export_doc()[0]["points"]:
            if point["id"] in PRESERVED:
                continue
            try:
                mw._dp_verify_state(point)
            except ValueError as exc:
                rows.append(f"{point['id']}: {exc}")
            else:
                rows.append(f"{point['id']}: no gap (unexpected)")
    finally:
        mw._DP_VERIFY_STATE_VALUES.clear()
        mw._DP_VERIFY_STATE_VALUES.update(saved)
    return rows


def template_gap() -> str:
    head = subprocess.run(
        ["git", "show", "HEAD:packages/multi-workers/decide_book_template.json"],
        cwd=pathlib.Path.cwd(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=True,
    ).stdout
    old_doc = json.loads(head)["books"][DP6]
    equal = old_doc == books.scaffold_book(DP6)
    return "pre-T04b template == scaffold_book(dp6): " + ("yes" if equal else "NO (RED)")


if __name__ == "__main__":
    gaps = probe_gaps()
    missing = sum("no probe value" in row for row in gaps)
    print(f"old_probe_table_entries={len(old_table())} dps_with_gap={missing}/{len(gaps)}")
    for row in gaps:
        print(" ", row)
    print(template_gap())
