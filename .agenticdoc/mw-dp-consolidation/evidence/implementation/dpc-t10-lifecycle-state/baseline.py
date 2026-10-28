"""T10 baseline capture: bytes/SHA256/EOL and the existing diff for the 5 write-face files.

Read-only. Writes one JSON document to stdout (the caller redirects it into this
evidence directory). Never writes into the worktree or the live repo.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import subprocess

REPO = pathlib.Path(r"H:/git/Multi-Workers")
WT = REPO / ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers"
LIVE = REPO / "packages/multi-workers"
FILES = (
    "decision_wire.py",
    "decision_lifecycle.py",
    "decision_task_state.py",
    "test_decision_context_lifecycle.py",
    "test_decision_task_state.py",
)


def _info(path: pathlib.Path) -> dict[str, object]:
    if not path.exists():
        return {"exists": False, "bytes": None, "sha256": None, "lf": None, "crlf": None}
    data = path.read_bytes()
    return {
        "exists": True,
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "lf": data.count(b"\n"),
        "crlf": data.count(b"\r\n"),
        "ends_with_lf": data.endswith(b"\n"),
    }


out: dict[str, object] = {"files": {}}
files: dict[str, object] = {}
for name in FILES:
    wt = _info(WT / name)
    live = _info(LIVE / name)
    diff = subprocess.run(
        ["git", "-C", str(REPO), "diff", "--no-color", "--", str((WT / name).relative_to(REPO))],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    files[name] = {
        "worktree": wt,
        "live": live,
        "worktree_equals_live": wt.get("sha256") == live.get("sha256"),
        "existing_worktree_tracked_diff_rc": diff.returncode,
        "existing_worktree_tracked_diff_bytes": len(diff.stdout.encode("utf-8")),
        "existing_worktree_tracked_diff_head": "\n".join(diff.stdout.splitlines()[:12]),
    }
out["files"] = files
out_path = pathlib.Path(__file__).with_name("baseline.json")
out_path.write_bytes((json.dumps(out, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
print(out_path)
