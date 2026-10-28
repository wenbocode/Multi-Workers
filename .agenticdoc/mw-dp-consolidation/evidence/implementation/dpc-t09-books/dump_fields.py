"""Print the declared field specs of the eight active entries (read-only)."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[3] / "implementation-worktree" / "packages" / "multi-workers"))
sys.dont_write_bytecode = True

import decision_points as p  # noqa: E402

free = {
    "task_goal",
    "task_requirements",
    "task_deliverables",
    "images_required",
    "pm_decision_background",
    "worker_execution",
    "reachability_facts",
    "completed",
    "remaining",
    "blockers",
    "constraints",
    "basis_issue",
    "gate_background",
    "current_state",
    "condition_evidence",
    "delivery_goal",
    "actual_completion",
    "unfinished_impact",
    "question",
    "decision_actor",
    "decision_object",
}
for entry in p.ACTIVE_DP_IDS:
    print("==", entry, p.ENTRY_CHOICES[entry])
    paths = list(p.REQUIRED_STATE_FIELDS[entry]) + list(p.OPTIONAL_STATE_FIELDS.get(entry, ()))
    for path in paths:
        spec = p.STATE_FIELD_DESCRIPTIONS.get(path)
        print("  ", path, "->", spec)
