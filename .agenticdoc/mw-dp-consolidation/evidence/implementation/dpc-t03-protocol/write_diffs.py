"""T03 evidence: before/after unified diffs + handoff inventory + import smoke.

Read-only w.r.t. product files. Writes only into this card's evidence dir:
- ``t03-changes.diff``: unified diff of the four approved copy files (before bytes
  captured by capture_manifest.py -> current bytes);
- ``handoff-inventory.json``: hashes of the files T04/T11/T23 must take over plus
  the untouched legacy cases/generators;
- ``import-smoke.json``: which sibling modules still import against the new
  registry (older consumers are expected to need their own card).
"""

from __future__ import annotations

import difflib
import hashlib
import importlib
import json
import pathlib
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
WORKTREE = EVIDENCE.parents[2] / "implementation-worktree"
PACKAGE = WORKTREE / "packages" / "multi-workers"
RELATIVE_FILES = (
    "packages/multi-workers/decision_points.py",
    "packages/multi-workers/decide_registry.json",
    "packages/multi-workers/test_decide_registry_contract.py",
    "packages/multi-workers/test_dp_consolidation_registry.py",
)
HANDOFF_FILES = (
    "packages/multi-workers/decision_points.py",
    "packages/multi-workers/decide_registry.json",
    "packages/multi-workers/decision_context.py",
    "packages/multi-workers/decision_book.py",
    "packages/multi-workers/decision.py",
    "packages/multi-workers/mw.py",
    "packages/multi-workers/scripts/gen_decide_registry_ts.py",
    "packages/multi-workers/decide_cases/dp1.json",
    "packages/multi-workers/decide_cases/dp2.json",
    "packages/multi-workers/decide_cases/dp3.json",
    "packages/multi-workers/decide_cases/dp25.json",
    "packages/coding-agent/src/extensions/agent-team-loop/shared/decide-registry.generated.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts",
)
MODULES = (
    "decision_points",
    "decision",
    "decision_context",
    "decision_book",
    "decide_signoff",
    "decide_archive",
    "decision_history",
    "decision_wire",
    "decision_lifecycle",
)


def sha(path: pathlib.Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def main() -> int:
    diff_chunks: list[str] = []
    summary = []
    for relative in RELATIVE_FILES:
        before_path = EVIDENCE / "before-bytes" / pathlib.PurePosixPath(relative).name
        after_path = WORKTREE / relative
        before = before_path.read_text(encoding="utf-8").splitlines(keepends=True) if before_path.is_file() else []
        after = after_path.read_text(encoding="utf-8").splitlines(keepends=True)
        diff = list(
            difflib.unified_diff(
                before,
                after,
                fromfile=f"before/{before_path.name}",
                tofile=f"after/{after_path.name}",
                n=3,
            )
        )
        diff_chunks.extend(diff)
        summary.append(
            {
                "path": relative,
                "before_lines": len(before),
                "after_lines": len(after),
                "added": sum(1 for line in diff if line.startswith("+") and not line.startswith("+++")),
                "removed": sum(1 for line in diff if line.startswith("-") and not line.startswith("---")),
                "sha_before": sha(before_path),
                "sha_after": sha(after_path),
            }
        )
    (EVIDENCE / "t03-changes.diff").write_text("".join(diff_chunks), encoding="utf-8")

    inventory = {
        "worktree": "H:/git/Multi-Workers/.agenticdoc/mw-dp-consolidation/implementation-worktree",
        "handoff_files": {
            relative: {"exists": (WORKTREE / relative).is_file(), "sha256": sha(WORKTREE / relative)}
            for relative in HANDOFF_FILES
        },
        "changed_summary": summary,
    }
    (EVIDENCE / "handoff-inventory.json").write_text(
        json.dumps(inventory, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    sys.path.insert(0, str(PACKAGE))
    smoke = {}
    for name in MODULES:
        try:
            importlib.import_module(name)
        except Exception as exc:  # noqa: BLE001 - evidence wants the real failure
            smoke[name] = f"{type(exc).__name__}: {exc}"
        else:
            smoke[name] = "ok"
    (EVIDENCE / "import-smoke.json").write_text(
        json.dumps(smoke, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"summary": summary, "imports": smoke}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
