"""Regenerate the small evidence summaries for this card (read-only inputs)."""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import compare_logs  # noqa: E402


def comparison() -> dict:
    base = compare_logs.parse(HERE / "logs" / "baseline-red" / "stdout.txt")
    final = compare_logs.parse(HERE / "logs" / "green-08-full-final" / "stdout.txt")
    remaining = sorted(final["failures"])
    unchanged = [
        name
        for name in remaining
        if name in base["failures"] and base["failures"][name] == final["failures"][name]
    ]
    payload = {
        "baseline": {"log": "logs/baseline-red/stdout.txt", **{k: base[k] for k in ("passed", "failed")}},
        "final": {"log": "logs/green-08-full-final/stdout.txt", **{k: final[k] for k in ("passed", "failed")}},
        "fixed_by_this_change": sorted(set(base["failures"]) - set(final["failures"])),
        "remaining_failures": remaining,
        "remaining_with_identical_failure_reason": unchanged,
        "remaining_with_changed_reason": [
            name for name in remaining if name in base["failures"] and name not in unchanged
        ],
        "new_failures": [name for name in remaining if name not in base["failures"]],
        "remaining_reasons": {name: final["failures"][name] for name in remaining},
    }
    (HERE / "comparison-baseline-vs-final.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def function_delta() -> dict:
    import ast

    before = ast.parse(
        (HERE / "before-bytes" / "packages" / "multi-workers" / "test_decision_context_workbench.py").read_text(
            encoding="utf-8"
        )
    )
    after = ast.parse(
        (
            HERE.parents[2]
            / "implementation-worktree"
            / "packages"
            / "multi-workers"
            / "test_decision_context_workbench.py"
        ).read_text(encoding="utf-8")
    )

    def names(tree):
        return [node.name for node in tree.body if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")]

    old, new = names(before), names(after)
    payload = {
        "before_count": len(old),
        "after_count": len(new),
        "renamed_case_tests": {
            "test_four_offline_cases_are_complete_and_contract_shaped": "test_eight_offline_cases_are_complete_schema3_and_contract_shaped",
            "test_dp2_case_keeps_the_registry_question_vocabulary": "test_dp_pm_steer_case_keeps_the_registry_question_vocabulary",
            "test_four_cases_pass_the_offline_registry_typed_check": "test_eight_cases_pass_the_offline_registry_typed_check",
        },
        "kept_unchanged_names": [name for name in old if name in new],
        "added": [name for name in new if name not in old],
    }
    (HERE / "test-function-delta.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def mirror_integrity() -> dict:
    import datetime

    inv = json.loads(
        (
            HERE.parent
            / "s2-t05-t10-pre-dispatch-20261027"
            / "mirror-inventory.json"
        ).read_text(encoding="utf-8")
    )
    worktree = HERE.parents[2] / "implementation-worktree"
    changed = []
    missing = []
    for rel, sha in inv.items():
        path = worktree / rel
        if not path.is_file():
            missing.append(rel)
            continue
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        if actual != sha:
            changed.append({"file": rel, "before_sha256": sha, "after_sha256": actual})
    payload = {
        "captured_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "inventory_source": "evidence/implementation/s2-t05-t10-pre-dispatch-20261027/mirror-inventory.json",
        "inventory_files": len(inv),
        "missing": missing,
        "changed": changed,
        "notes": (
            "The four T10-owned files and the decision.pyc cache are not this card's "
            "writes; see report.md and pyc-deviation.md."
        ),
    }
    (HERE / "mirror-integrity.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def run_deps() -> dict:
    runs = {}
    for label in ("green-02-full", "green-04-full-rerun", "green-06-full-final", "green-08-full-final"):
        run_dir = HERE / "logs" / label
        before = json.loads((run_dir / "deps-before.json").read_text(encoding="utf-8-sig")) if (run_dir / "deps-before.json").is_file() else []
        after = json.loads((run_dir / "deps-after.json").read_text(encoding="utf-8-sig")) if (run_dir / "deps-after.json").is_file() else []
        imported = json.loads((run_dir / "imported-modules.json").read_text(encoding="utf-8-sig")) if (run_dir / "imported-modules.json").is_file() else {}
        runs[label] = {
            "deps_before": before,
            "stable_during_run": before == after,
            "imported_modules": imported,
        }
    payload = {
        "note": (
            "decision_lifecycle.py (T10 write face) changed between runs while "
            "decision_task_state.py/decision_wire.py/decision_book.py/decision_points.py "
            "stayed fixed; every run was internally stable. Results were identical "
            "across the revisions, but this window is recorded as unstable input, "
            "not as the final qualification."
        ),
        "runs": runs,
    }
    (HERE / "dependency-window.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return payload


def main() -> int:
    comp = comparison()
    delta = function_delta()
    integ = mirror_integrity()
    deps = run_deps()
    print(
        json.dumps(
            {
                "baseline": comp["baseline"],
                "final": comp["final"],
                "fixed": len(comp["fixed_by_this_change"]),
                "remaining": len(comp["remaining_failures"]),
                "remaining_same_reason": len(comp["remaining_with_identical_failure_reason"]),
                "new_failures": comp["new_failures"],
                "test_functions": {"before": delta["before_count"], "after": delta["after_count"]},
                "mirror_changed": [row["file"] for row in integ["changed"]],
                "mirror_missing": integ["missing"],
                "runs": {
                    label: {
                        "stable_during_run": info["stable_during_run"],
                        "lifecycle": next(
                            (dep["sha256"][:10] for dep in info["deps_before"] if dep["file"] == "decision_lifecycle.py"),
                            None,
                        ),
                    }
                    for label, info in deps["runs"].items()
                },
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
