"""Assemble check.json for the T10 evidence directory from the real artifacts."""
from __future__ import annotations

import json
import pathlib
import re

HERE = pathlib.Path(__file__).resolve().parent


def summary(label: str) -> dict[str, object]:
    stdout = (HERE / f"{label}.stdout").read_text(encoding="utf-8")
    rc = int((HERE / f"{label}.rc").read_text(encoding="utf-8").strip())
    meta = json.loads((HERE / f"{label}.meta.json").read_text(encoding="utf-8"))
    tail = [line for line in stdout.splitlines() if re.search(r"\d+ (passed|failed)", line)]
    failures = sorted(
        line.split("::", 1)[1]
        for line in stdout.splitlines()
        if line.startswith("FAILED ")
    )
    return {
        "label": label,
        "argv": meta["argv"],
        "cwd": meta["cwd"],
        "rc": rc,
        "summary": tail[-1] if tail else "",
        "failed_tests": failures,
        "stdout": f"{label}.stdout",
        "stderr": f"{label}.stderr",
    }


after = json.loads((HERE / "after.json").read_text(encoding="utf-8"))
products = {
    name: {
        "before_sha256": value["before"]["sha256"],
        "before_bytes": value["before"]["bytes"],
        "after_sha256": value["after"]["sha256"],
        "after_bytes": value["after"]["bytes"],
        "after_eol": value["after"]["eol"],
        "after_ends_with_lf": value["after"]["ends_with_lf"],
        "diff_hunks": value["diff_hunks"],
        "diff_bytes": value["diff_bytes"],
        "diff_file": f"diff-{name}.diff",
    }
    for name, value in after["files"].items()
}
payload = {
    "source": "agent-report",
    "task_key": "dpc-t10-lifecycle-state",
    "products": products,
    "runs": {
        label: summary(label)
        for label in (
            "baseline-green",
            "live-repo-baseline",
            "red-prefix",
            "final-green",
            "final-green-2",
            "exact-acceptance",
        )
    },
    "baseline_worktree_red_6": [
        "test_real_start_and_settled_snapshots_survive_history",
        "test_no_snapshot_is_not_inferred_from_ok_or_rework",
        "test_write_and_read_redaction_cover_snapshot_lists_and_keys",
        "test_reader_without_redactor_withholds_snapshot_prose",
        "test_real_cli_freezes_before_locally_and_passes_only_material_to_decision_boundary",
        "test_reader_does_not_attribute_another_tasks_after_snapshot",
    ],
    "baseline_worktree_red_cause": (
        "the retired dp1 id (T03 protocol migration) was used as the fixture entry; "
        "assertions were unchanged, only the fixture id moved to an active entry"
    ),
    "ast_preserved": {
        name: {
            "before_functions": value["before_functions"],
            "after_functions": value["after_functions"],
            "missing_original_functions": value["missing_original_functions"],
            "changed_original_functions": value["changed_original_functions"],
            "added_functions": len(value["added_functions"]),
        }
        for name, value in after["ast"].items()
    },
    "mirror": after["mirror"],
    "pyc": {key: after["pyc"][key] for key in (
        "protected_paths",
        "protected_present",
        "protected_missing",
        "protected_changed",
        "worktree_pyc_count",
    )},
    "imports": after["imports"],
    "pre_existing_failures_preserved": True,
    "whole_repo_source_audit": False,
    "cli_wiring_verified": False,
    "history_projection_of_new_facts_verified": False,
    "real_provider_or_http_used": False,
    "full_npm_check_run": False,
    "human_or_h12_grant_verified": False,
    "signoff_or_key_closure_verified": False,
}
(HERE / "check.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps({"ok": True}))
