"""T04b: independently derive minimal legal probe values for dp4..dp24.

Reads the live typed contract (`decision_points.STATE_FIELD_DESCRIPTIONS`,
`STATE_FIELD_CROSS_CHECKS`) and derives one minimal legal value per declared
required path. It does NOT read the T04 proposal; the proposal is loaded
afterwards only to diff against the derived set.

Run from packages/multi-workers (needs mw.py + decision_points.py on sys.path):
    python ../../../.agenticdoc/.../derive-probe-values.py
"""

from __future__ import annotations

import ast
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path.cwd()))

import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

#: Values already carried by the shipped probe table before T04b (dp1/dp2/dp3
#: plus the dp25 sign-off facts); reused literally, not re-derived. Frozen here
#: (not read from `mw.py`) so this script keeps reproducing the same 82-path
#: derivation after the values were written into the table.
PRESERVED_PATHS = frozenset(
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

#: Values already carried by the shipped probe table for dp1/dp2/dp3 (and the
#: dp25 sign-off facts); reused literally, not re-derived.
DERIVED_PATHS = frozenset(
    {
        "decision_point",
        "authority_tier",
        "task_summary",
        "questions_version",
        "ambiguity.question",
    }
)

#: Cross-check facts need a deliberate (still minimal) shape, not the blind
#: "integer -> 0 / array -> []" default, so the probe exercises the check.
CROSS_CHECK_OVERRIDES = {
    "dp4-failure-handling": {"failure.attempt": 1, "failure.limit": 3},
    "dp6-qg-verdict": {"qg.checks_total": 3, "qg.checks_failed": ["test_example"]},
    "dp17-spec-lock": {"spec.ac_ids": ["AC-001"], "spec.ac_changed": ["AC-001"]},
    "dp20-stage-close": {"stage.tasks_done": 1, "stage.tasks_total": 2},
}


def minimal_value(path: str) -> object:
    spec = dpts.STATE_FIELD_DESCRIPTIONS[path]
    kind = spec["type"]
    if "enum" in spec:
        return spec["enum"][0]
    if kind == "string":
        return "probe"
    if kind == "integer":
        return -1 if spec.get("signed") else int(spec.get("min_value", 0))
    if kind == "number":
        return 0.0
    if kind == "boolean":
        return False
    if kind == "array":
        return []
    if kind == "object":
        return {}
    raise AssertionError((path, kind))


def derive() -> dict[str, object]:
    values: dict[str, object] = {}
    for dp_id, paths in dpts.REQUIRED_STATE_FIELDS.items():
        for path in paths:
            if path in DERIVED_PATHS:
                continue
            if path in PRESERVED_PATHS:
                continue
            values[path] = minimal_value(path)
        values.update(CROSS_CHECK_OVERRIDES.get(dp_id, {}))
    return values


def check(values: dict[str, object]) -> list[str]:
    """Every derived value must be legal under the real validator."""
    problems: list[str] = []
    for dp_id, paths in dpts.REQUIRED_STATE_FIELDS.items():
        state: dict = {}
        derived = {
            "decision_point": dp_id,
            "authority_tier": "P1",
            "task_summary": "probe",
            "questions_version": "q-probe",
            "ambiguity.question": "probe",
        }
        merged = {**mw._DP_VERIFY_STATE_VALUES, **values, **derived}
        for path in paths:
            if path not in merged:
                problems.append(f"{dp_id}: no value for {path}")
                continue
            mw._dp_verify_set_path(state, path, merged[path])
        for path, detail in dpts.state_field_issues(dp_id, state):
            problems.append(f"{dp_id}: {path}: {detail}")
    return problems


def load_proposal() -> dict[str, object]:
    text = (
        pathlib.Path.cwd()
        / "../../.agenticdoc/mw-decision-dashboard/workers/dd-dp-contracts/proposed-mw-probe-values.txt"
    ).read_text(encoding="utf-8")
    out: dict[str, object] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("'"):
            continue
        key, _, raw = line.partition("':")
        raw = raw.strip().rstrip(",")
        out[key.lstrip("'")] = ast.literal_eval(raw)
    return out


if __name__ == "__main__":
    derived = derive()
    problems = check(derived)
    print(f"derived_paths={len(derived)} validator_issues={len(problems)}")
    for problem in problems:
        print("ISSUE", problem)
    proposal = load_proposal()
    print(f"proposal_paths={len(proposal)}")
    only_derived = sorted(set(derived) - set(proposal))
    only_proposal = sorted(set(proposal) - set(derived))
    differing = sorted(k for k in set(derived) & set(proposal) if derived[k] != proposal[k])
    print("only_derived:", only_derived)
    print("only_proposal:", only_proposal)
    print("value_diff (derived vs proposal):")
    for key in differing:
        print(f"  {key}: derived={derived[key]!r} proposal={proposal[key]!r}")
    proposal_problems = check(proposal)
    print(f"proposal_validator_issues={len(proposal_problems)}")
    for problem in proposal_problems:
        print("PROPOSAL ISSUE", problem)
