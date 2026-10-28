"""Scan the worktree for files modified at/after the real R3 start.

mtime is evidence only: it cannot prove exclusive authorship (another writer
could share the window), so the manifest only names what changed in this window.
"""

from __future__ import annotations

import json
import pathlib
from datetime import datetime, timezone

EVIDENCE = pathlib.Path(__file__).resolve().parent
KEY = EVIDENCE.parents[3]
WORKTREE = KEY / "implementation-worktree"
before = json.loads((EVIDENCE / "before-manifest.json").read_text(encoding="utf-8"))
start = datetime.fromisoformat(before["observed_at_utc"])
start_ns = int(start.timestamp() * 1_000_000_000)

rows = []
for path in sorted(WORKTREE.rglob("*")):
    if not path.is_file():
        continue
    if path.suffix in (".pyc",) or "__pycache__" in path.parts:
        continue
    relative = path.relative_to(WORKTREE).as_posix()
    stat = path.stat()
    if stat.st_mtime_ns >= start_ns:
        rows.append(
            {
                "path": relative,
                "mtime_ns": stat.st_mtime_ns,
                "mtime_utc": datetime.fromtimestamp(
                    stat.st_mtime_ns / 1_000_000_000, timezone.utc
                ).isoformat(),
                "bytes": stat.st_size,
            }
        )

doc = {
    "start_utc": before["observed_at_utc"],
    "observed_at_utc": datetime.now(timezone.utc).isoformat(),
    "caveat": "mtime scan only; not proof of exclusive authorship or of a clean tree",
    "files": rows,
}
(EVIDENCE / "mtime-scan.json").write_text(
    json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps({"files": [row["path"] for row in rows]}, ensure_ascii=False))
