"""Print the question table of the eight active entries (read-only)."""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(
    0,
    str(
        pathlib.Path(__file__).resolve().parents[3]
        / "implementation-worktree"
        / "packages"
        / "multi-workers"
    ),
)
sys.dont_write_bytecode = True

import decision_points as p  # noqa: E402

for entry in p.ACTIVE_DP_IDS:
    point = p.get_decision_point(entry)
    print(
        entry,
        point.kind,
        point.questions_version,
        [
            (
                q["id"],
                q.get("type"),
                q.get("dynamic_choices"),
                q.get("choices"),
            )
            for q in point.questions
        ],
    )
