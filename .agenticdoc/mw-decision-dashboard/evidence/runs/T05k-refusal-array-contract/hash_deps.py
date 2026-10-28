"""sha256 snapshot of the T05k dependency surface (read-only, no writes outside log).

Usage: python hash_deps.py <label>
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[5]
MW = REPO / "packages" / "multi-workers"

PATHS = (
    "packages/multi-workers/decision_points.py",
    "packages/multi-workers/decision.py",
    "packages/multi-workers/decision_backends.py",
    "packages/multi-workers/decision_book.py",
    "packages/multi-workers/mw.py",
    "packages/multi-workers/decision_monitor.py",
    "packages/multi-workers/decide_registry.json",
    "packages/multi-workers/scripts/gen_decide_registry_ts.py",
    "packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts",
    "packages/multi-workers/test_decision_required_refusal.py",
    "packages/multi-workers/test_decision_dp25_empty_value.py",
    "packages/multi-workers/test_decision_input_contract_migration.py",
    "packages/multi-workers/test_decision_observation.py",
    "packages/multi-workers/test_decision_dashboard_contracts.py",
    "packages/multi-workers/test_decide_registry_export.py",
    "packages/multi-workers/test_decide_sign_auto.py",
)


def main() -> None:
    label = sys.argv[1] if len(sys.argv) > 1 else "deps"
    print(f"{label} (sha256, size B)")
    for rel in PATHS:
        path = REPO / rel
        if not path.exists():
            print(f"(absent)  {rel}")
            continue
        data = path.read_bytes()
        print(f"{hashlib.sha256(data).hexdigest()}  {len(data)}B  {rel}")


main()
