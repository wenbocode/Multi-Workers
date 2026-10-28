#!/usr/bin/env python3
"""Write the full unified diff of the allowed test file (before -> after).

Also cross-checks this attempt's before bytes against the PM pre-dispatch copy
reported in evidence/implementation/t04-r2-pre-dispatch-20261026/.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve()
REWORK = HERE.parent.parent
EVIDENCE = REWORK.parents[1]
PM_BEFORE = EVIDENCE / "t04-r2-pre-dispatch-20261026"
REL = "packages/multi-workers/test_decide_registry_ts_lock.py"


def main() -> int:
    before_path = REWORK / "before" / "allowed-test.bytes.py"
    after_path = REWORK / "after" / "allowed-test.bytes.py"
    before = before_path.read_bytes()
    after = after_path.read_bytes()
    before_lines = before.decode("utf-8").splitlines(keepends=True)
    after_lines = after.decode("utf-8").splitlines(keepends=True)
    diff = difflib.unified_diff(
        before_lines,
        after_lines,
        fromfile=f"a/{REL}",
        tofile=f"b/{REL}",
        n=3,
    )
    text = "".join(diff)
    (REWORK / "after" / "full.diff").write_text(text, encoding="utf-8", newline="\n")

    added = sum(1 for line in text.splitlines() if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in text.splitlines() if line.startswith("-") and not line.startswith("---"))

    pm = PM_BEFORE / "before-bytes"
    pm_file = pm / REL
    cross = {
        "pm_before_path": str(pm_file),
        "pm_before_exists": pm_file.exists(),
        "pm_before_sha256": (
            hashlib.sha256(pm_file.read_bytes()).hexdigest() if pm_file.exists() else None
        ),
        "own_before_sha256": hashlib.sha256(before).hexdigest(),
        "same_bytes": pm_file.read_bytes() == before if pm_file.exists() else None,
        "before_sha256": hashlib.sha256(before).hexdigest(),
        "after_sha256": hashlib.sha256(after).hexdigest(),
        "before_bytes": len(before),
        "after_bytes": len(after),
        "before_eol": {
            "crlf": before.count(b"\r\n"),
            "bare_lf": before.count(b"\n") - before.count(b"\r\n"),
        },
        "after_eol": {
            "crlf": after.count(b"\r\n"),
            "bare_lf": after.count(b"\n") - after.count(b"\r\n"),
        },
        "diff_lines_added": added,
        "diff_lines_removed": removed,
        "diff_hunks": sum(1 for line in text.splitlines() if line.startswith("@@")),
    }
    (REWORK / "after" / "diff-summary.json").write_text(
        json.dumps(cross, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(json.dumps(cross, indent=1, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
