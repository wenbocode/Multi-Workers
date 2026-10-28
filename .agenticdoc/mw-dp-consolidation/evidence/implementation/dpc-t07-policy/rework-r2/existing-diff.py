"""Reconstruct the existing (pre-R2) diff for the two product files and hash it.

The two files do not exist in the live tree; the existing diff is therefore the
whole added content, exactly as PM reconstructed it (pm-full.diff). This script
recomputes it from the saved before-bytes so the before state has its own diff.
Run with -B / PYTHONDONTWRITEBYTECODE=1.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
PRODUCTS = (
    "packages/multi-workers/decision_policy.py",
    "packages/multi-workers/test_dp_consolidation_recovery.py",
)

parts: list[str] = []
for rel in PRODUCTS:
    raw = (HERE / "before-bytes" / rel.replace("/", "__")).read_bytes()
    text = raw.decode("utf-8")
    parts.append(
        "".join(
            difflib.unified_diff(
                [],
                text.splitlines(keepends=True),
                fromfile="/dev/null",
                tofile="b/" + rel,
            )
        )
    )
diff = "".join(parts).encode("utf-8")
(HERE / "before-full.diff").write_bytes(diff)
pm_sha = "120b978c475d86145eaffe26f4bd94b1551ddb0d7c7d24a63e8f61f9c253b62f"
result = {
    "bytes": len(diff),
    "sha256": hashlib.sha256(diff).hexdigest(),
    "pm_handoff_diff_sha256": pm_sha,
    "equal_to_pm_diff": hashlib.sha256(diff).hexdigest() == pm_sha,
}
(HERE / "existing-diff.json").write_text(
    json.dumps(result, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps(result, indent=2))
