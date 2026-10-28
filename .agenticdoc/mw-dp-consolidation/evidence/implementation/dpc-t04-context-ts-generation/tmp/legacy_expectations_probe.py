"""Static probe of the pre-consolidation expectations that T04 changed.

Read-only: it imports the worktree modules and evaluates the exact assertions the
unmapped legacy test files still make, so the residual debt is recorded with
concrete expected/actual values instead of a claim. It does not run those test
files (they are outside the card's command list).
"""

from __future__ import annotations

import json
import pathlib
import sys

MW = pathlib.Path(__file__).resolve()
WT = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation\implementation-worktree")
PKG = WT / "packages/multi-workers"
sys.path.insert(0, str(PKG))
sys.path.insert(0, str(PKG / "scripts"))

import decision_context as ctx  # noqa: E402
import decision_points as dpts  # noqa: E402
import gen_decide_registry_ts as gen  # noqa: E402

rows = []


def record(label: str, expected: object, actual: object) -> None:
    rows.append(
        {
            "label": label,
            "legacy_expected": expected,
            "actual_after_t04": actual,
            "same": expected == actual,
        }
    )


record(
    "test_decision_context.py::test_slot_names_match_the_card_whitelist[dp4]",
    ("error_excerpt",),
    ctx.slot_names_for("dp4-failure-handling"),
)
record(
    "test_decision_context.py::test_validate_context_accepts_a_well_formed_block[dp4]",
    [],
    ctx.validate_context({"error_excerpt": "pytest exited 1"}, "dp4-failure-handling"),
)
record(
    "test_decision_context.py::test_validate_context_accepts_a_well_formed_block[dp6]",
    [],
    ctx.validate_context({"error_excerpt": "2 blocking findings"}, "dp6-qg-verdict"),
)
record(
    "test_decision_context.py::test_slot_names_match_the_card_whitelist[dp1]",
    (),
    ctx.slot_names_for("dp1-dispatch-type"),
)
record(
    "test_decision_context.py::test_validate_context_flags_a_slot_the_dp_may_not_emit",
    ["context.task_excerpt: not a slot of dp3-worker-clarify"],
    ctx.validate_context({"task_excerpt": "x"}, "dp3-worker-clarify"),
)

text = gen.output_path().read_text(encoding="utf-8")
legacy_model_dps = {
    "dp1-dispatch-type": ["task_goal", "task_requirements", "task_deliverables"],
    "dp2-checkpoint-split": [
        "task_goal",
        "task_requirements",
        "task_deliverables",
        "pm_decision_background",
        "worker_execution",
    ],
    "dp3-worker-clarify": [
        "task_goal",
        "background.task_goal",
        "background.current_state",
        "background.decision_reason",
        "background.constraints_impact",
        "question",
        "handling_options",
    ],
    "dp25-signoff-conclusion": [
        "delivery_goal",
        "actual_completion",
        "verification_evidence.verified",
        "verification_evidence.unverified",
        "unfinished_impact",
    ],
}
for dp_id in legacy_model_dps:
    anchor = f'\t"{dp_id}": {{'
    rows.append(
        {
            "label": f"test_decision_context_contract.py::test_generated_ts_is_fresh_and_carries_the_model_table[{dp_id}]",
            "legacy_expected": f"entry anchor {anchor!r} present",
            "actual_after_t04": f"present={anchor in text}",
            "same": anchor in text,
        }
    )

doc = dpts.registry_snapshot()
rows.append(
    {
        "label": "active entries / retired records / slot producers",
        "legacy_expected": "pre-T04 25 numbered dps",
        "actual_after_t04": {
            "active": list(dpts.ACTIVE_DP_IDS),
            "retired": len(doc["retired"]),
            "slot_producers": sorted(
                {
                    producer
                    for slot in ctx.SLOT_ORDER
                    for producer in ctx.CONTEXT_SLOTS[slot].get("producers", ())
                }
            ),
        },
        "same": False,
    }
)

out = pathlib.Path(__file__).resolve().parent.parent / "logs" / "legacy-expectations-probe.json"
out.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
print(json.dumps(rows, indent=2, ensure_ascii=False))
