"""T07 final evidence: changed-files record + synthetic diff of the new files."""
from __future__ import annotations

import difflib
import hashlib
import json
import pathlib
import time

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[4]
WORKTREE = REPO / ".agenticdoc/mw-dp-consolidation/implementation-worktree"
PKG = WORKTREE / "packages/multi-workers"

MINE = ["decision_policy.py", "test_dp_consolidation_recovery.py"]


def main() -> int:
    changed = []
    chunks: list[str] = []
    for name in MINE:
        path = PKG / name
        data = path.read_bytes()
        text = data.decode("utf-8")
        changed.append(
            {
                "path": str(path.relative_to(REPO)).replace("\\", "/"),
                "status": "added (did not exist before this worker)",
                "bytes": len(data),
                "sha256": hashlib.sha256(data).hexdigest(),
                "eol": "crlf" if "\r\n" in text else "lf",
                "trailing_newline": text.endswith("\n"),
                "lines": text.count("\n") + (0 if text.endswith("\n") else 1),
            }
        )
        chunks.extend(
            difflib.unified_diff(
                [],
                text.splitlines(keepends=True),
                fromfile="/dev/null",
                tofile=f"b/packages/multi-workers/{name}",
                n=0,
            )
        )
    (HERE / "mine.diff").write_text(
        "".join(chunks), encoding="utf-8", newline="\n"
    )
    record = {
        "observed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "changed_files": changed,
        "note": "both files are new; the origin mirror is untouched (the copy "
        "tree is untracked in the origin repo, so file bytes above are the record)",
    }
    (HERE / "changed-files.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
