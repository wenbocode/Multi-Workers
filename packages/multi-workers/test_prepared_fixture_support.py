"""Explicit bounded comparison facts for synthetic prepared-decision fixtures."""

from itertools import combinations


def auto_context(material: dict) -> dict:
    background = material["background"]
    allowance = "Remaining time: 300 seconds (synthetic test allowance)."
    if allowance not in background["constraints"]:
        background["constraints"] += " " + allowance
    ids = [option["id"] for option in material["handling_options"]]
    return {
        "desc": [background["task_goal"], background["current_state"], "Compare the isolated fixture candidates."],
        "terminology": {},
        "auto_comparison": {
            "priority": {"source": "background.task_goal", "rule": "Prefer evidence within the stated fixture goal."},
            "budget": {"remaining_seconds": 300, "reserve_seconds": 30},
            "paths": {
                name: {
                    "max_seconds": 60,
                    "observation": f"The recorded result for candidate {name}",
                    "stop": f"Stop after inspecting candidate {name} once.",
                    "successor": "Return the observation to the fixture owner; no automatic retry.",
                    "steps": [{"id": "inspect", "max_seconds": 60, "on_success": None, "on_failure": None}],
                }
                for name in ids
            },
            "pairs": [
                {"candidates": [left, right], "criterion": f"Compare observed evidence for {left} and {right}.",
                 "reversal": "Reverse the preference when the other candidate has stronger observed evidence."}
                for left, right in combinations(ids, 2)
            ],
        },
    }
