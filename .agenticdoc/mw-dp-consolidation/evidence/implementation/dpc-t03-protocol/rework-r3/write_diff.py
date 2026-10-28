"""Write the actual R3 diff and the before/after byte summary."""

from __future__ import annotations

import difflib
import hashlib
import json
import pathlib

EVIDENCE = pathlib.Path(__file__).resolve().parent
KEY = EVIDENCE.parents[3]
WORKTREE = KEY / "implementation-worktree"
PRODUCT = [
    "packages/multi-workers/decision_points.py",
    "packages/multi-workers/decide_registry.json",
    "packages/multi-workers/test_decide_registry_contract.py",
    "packages/multi-workers/test_dp_consolidation_registry.py",
]


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stats(data: bytes) -> dict:
    return {
        "bytes": len(data),
        "sha256": sha(data),
        "crlf": data.count(b"\r\n"),
        "bare_lf": data.count(b"\n") - data.count(b"\r\n"),
        "lines": len(data.splitlines()),
        "last_byte": data[-1],
    }


diffs: list[str] = []
summary = []
for relative in PRODUCT:
    name = pathlib.Path(relative).name
    before = (EVIDENCE / "before-bytes" / name).read_bytes()
    after = (WORKTREE / relative).read_bytes()
    before_stats = stats(before)
    after_stats = stats(after)
    changed = before != after
    added = removed = 0
    if changed:
        lines = list(
            difflib.unified_diff(
                before.decode("utf-8").splitlines(keepends=True),
                after.decode("utf-8").splitlines(keepends=True),
                fromfile=f"before/{name}",
                tofile=f"after/{name}",
                n=3,
            )
        )
        diffs.extend(lines)
        added = sum(1 for line in lines if line.startswith("+") and not line.startswith("+++"))
        removed = sum(1 for line in lines if line.startswith("-") and not line.startswith("---"))
    summary.append(
        {
            "path": relative,
            "changed": changed,
            "added_lines": added,
            "removed_lines": removed,
            "before": before_stats,
            "after": after_stats,
            "eol_style_preserved": (before_stats["crlf"] == 0)
            == (after_stats["crlf"] == 0)
            and (before_stats["bare_lf"] > 0) == (after_stats["bare_lf"] > 0)
            and before_stats["last_byte"] == after_stats["last_byte"],
        }
    )

(EVIDENCE / "r3-changes.diff").write_text("".join(diffs), encoding="utf-8")
(EVIDENCE / "change-summary.json").write_text(
    json.dumps({"files": summary}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
for record in summary:
    print(
        record["path"],
        "changed=" + str(record["changed"]),
        f"+{record['added_lines']}/-{record['removed_lines']}",
        f"bytes {record['before']['bytes']}->{record['after']['bytes']}",
        f"eol {record['before']['crlf']}/{record['before']['bare_lf']} -> {record['after']['crlf']}/{record['after']['bare_lf']}",
    )
assert [record["path"] for record in summary if record["changed"]] == [
    "packages/multi-workers/test_decide_registry_contract.py"
], "only the R3 test file may differ from the captured before state"
assert all(record["eol_style_preserved"] for record in summary)
