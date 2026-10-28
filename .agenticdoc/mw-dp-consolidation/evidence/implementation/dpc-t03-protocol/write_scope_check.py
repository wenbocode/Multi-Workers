"""T03 write-scope check: which worktree files changed after this card started.

Compares mtimes against the worker run start (2026-10-26T02:35:17Z, from the
card's run.json) and lists every file at/after it, marking the four approved copy
files and their evidence dir. Also proves the four legacy cases are byte-identical
to the source-repo copies (they must stay read-only).

Read-only; writes only ``write-scope-check.json`` in this evidence dir.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import pathlib

EVIDENCE = pathlib.Path(__file__).resolve().parent
REPO = EVIDENCE.parents[4]
WORKTREE = EVIDENCE.parents[2] / "implementation-worktree"
START = datetime.datetime(2026, 10, 26, 2, 35, 17, tzinfo=datetime.timezone.utc)
ALLOWED = {
    "packages/multi-workers/decision_points.py",
    "packages/multi-workers/decide_registry.json",
    "packages/multi-workers/test_decide_registry_contract.py",
    "packages/multi-workers/test_dp_consolidation_registry.py",
}
CASES = ("dp1.json", "dp2.json", "dp3.json", "dp25.json")


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    changed = []
    allowed_seen = set()
    for path in WORKTREE.rglob("*"):
        if not path.is_file():
            continue
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        relative = path.relative_to(WORKTREE).as_posix()
        if mtime >= START.timestamp() - 1:
            changed.append(relative)
            if relative in ALLOWED:
                allowed_seen.add(relative)
    cases = {}
    for name in CASES:
        source = REPO / "packages" / "multi-workers" / "decide_cases" / name
        copy = WORKTREE / "packages" / "multi-workers" / "decide_cases" / name
        cases[name] = {
            "source_sha256": sha(source) if source.is_file() else None,
            "copy_sha256": sha(copy) if copy.is_file() else None,
            "identical": (
                source.is_file() and copy.is_file() and sha(source) == sha(copy)
            ),
        }
    report = {
        "start_utc": START.isoformat(),
        "worktree_files_at_or_after_start": sorted(changed),
        "approved_files_seen": sorted(allowed_seen),
        "unexpected_files": sorted(set(changed) - ALLOWED),
        "legacy_cases_read_only": cases,
    }
    (EVIDENCE / "write-scope-check.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
