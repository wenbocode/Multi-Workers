"""T04b: self-check the shipped probe table against the typed contract.

For all 25 dps: build the probe state from the shipped table and run the real
validator (`decision_points.state_field_issues`). Also assert the template equals
the live scaffold render (the card test's premise).

Run from packages/multi-workers.
"""

from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path.cwd()))

import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

TEMPLATE = pathlib.Path("decide_book_template.json")


def main() -> int:
    problems: list[str] = []
    states = 0
    for point in mw._dp_export_doc()[0]["points"]:
        dp_id = point["id"]
        try:
            state = mw._dp_verify_state(point)
        except ValueError as exc:
            problems.append(str(exc))
            continue
        states += 1
        declared = sorted(field["name"] for field in point["required_state_fields"])
        actual = sorted(_leaves(state))
        if declared != actual:
            problems.append(f"{dp_id}: probe state paths drifted from the contract")
        for path, detail in dpts.state_field_issues(dp_id, state):
            problems.append(f"{dp_id}: {path}: {detail}")
    doc = json.loads(TEMPLATE.read_text(encoding="utf-8"))
    template_ok = True
    for dp_id in ("dp3-worker-clarify", "dp6-qg-verdict"):
        if doc["books"][dp_id] != books.scaffold_book(dp_id):
            template_ok = False
            problems.append(f"{dp_id}: template != scaffold_book render")
    print(f"probe_table_entries={len(mw._DP_VERIFY_STATE_VALUES)} dps_built={states}/25")
    print(f"template_matches_render={template_ok}")
    print(f"problems={len(problems)}")
    for problem in problems:
        print(" ", problem)
    return 0 if not problems else 1


def _leaves(node: object, prefix: str = "") -> list[str]:
    if not isinstance(node, dict):
        return [prefix]
    out: list[str] = []
    for key, value in node.items():
        out.extend(_leaves(value, f"{prefix}.{key}" if prefix else str(key)))
    return out


if __name__ == "__main__":
    raise SystemExit(main())
