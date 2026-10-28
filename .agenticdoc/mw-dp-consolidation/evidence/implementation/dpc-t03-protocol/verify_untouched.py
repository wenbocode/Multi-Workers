"""T03 evidence: verify the other approved copy files still match the setup baseline.

Compares every ``implementation_path`` sha in
``isolation-baseline-20261026/approved-file-baselines.json`` with the current
worktree file and reports differences. T03 may only have changed its four card
files; any other difference would be an unexpected write (or an earlier session's
state) and must be reported, not silently accepted.

Read-only; writes only ``untouched-files-check.json`` here.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

EVIDENCE = pathlib.Path(__file__).resolve().parent
REPO = EVIDENCE.parents[4]
BASELINE = (
    REPO
    / ".agenticdoc"
    / "mw-dp-consolidation"
    / "evidence"
    / "implementation"
    / "isolation-baseline-20261026"
    / "approved-file-baselines.json"
)
T03 = {
    ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decision_points.py",
    ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/decide_registry.json",
    ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/test_decide_registry_contract.py",
}


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    rows = json.loads(BASELINE.read_text(encoding="utf-8"))
    same = 0
    changed = []
    missing = []
    for row in rows:
        path = row.get("implementation_path")
        expected = row.get("sha256")
        if not path or not expected:
            continue
        full = REPO / path.replace("\\", "/")
        if not full.is_file():
            missing.append(path)
            continue
        current = sha(full)
        if current == expected:
            same += 1
        else:
            changed.append(
                {"path": path.replace("\\", "/"), "baseline": expected, "current": current}
            )
    report = {
        "baseline": str(BASELINE.relative_to(REPO)).replace("\\", "/"),
        "identical": same,
        "changed": changed,
        "missing": missing,
        "changed_is_t03_write_face": sorted(item["path"] for item in changed) == sorted(T03),
    }
    (EVIDENCE / "untouched-files-check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
