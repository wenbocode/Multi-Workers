"""Capture the T09 after-bytes, the incremental diffs and the net-change audit.

Writes only inside this card's evidence directory:
  after-bytes/<relpath>          raw bytes of the current copy
  after-bytes.json               path/bytes/sha256/EOL/lines + before compare
  diffs/<name>.diff              unified diff before -> after
  mirror-net-changes.json        worktree vs t09-pre-dispatch mirror inventory
"""

from __future__ import annotations

import difflib
import hashlib
import json
import pathlib
import shutil
import subprocess

EVIDENCE = pathlib.Path(__file__).resolve().parent
WORKTREE = EVIDENCE.parents[2] / "implementation-worktree"
PRE_DISPATCH = EVIDENCE.parents[0] / "t09-pre-dispatch-20261027"

FILES = (
    "packages/multi-workers/decision_book.py",
    "packages/multi-workers/test_decision_context_contract.py",
)

SKIP_DIRS = {"node_modules", "dist", ".git", ".pytest_cache"}


def describe(path: pathlib.Path) -> dict:
    data = path.read_bytes()
    text = data.decode("utf-8")
    return {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "lines": text.count("\n") + (0 if text.endswith("\n") or not text else 1),
        "lf": data.count(b"\n"),
        "crlf": data.count(b"\r\n"),
        "bare_lf": data.count(b"\n") - data.count(b"\r\n"),
        "mtime": path.stat().st_mtime_ns,
    }


def inventory(root: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        out[rel.as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    return out


def main() -> int:
    before = json.loads((EVIDENCE / "before-bytes.json").read_text(encoding="utf-8"))
    before_sha = {record["relpath"]: record["sha256"] for record in before["files"]}
    out: dict = {
        "worktree": str(WORKTREE),
        "files": [],
        "verdict": {},
    }
    for rel in FILES:
        copy = WORKTREE / rel
        target = EVIDENCE / "after-bytes" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(copy, target)
        record = describe(copy)
        record["relpath"] = rel
        record["before_sha256"] = before_sha[rel]
        record["changed"] = record["sha256"] != before_sha[rel]
        record["evidence_copy"] = str(target)
        record["evidence_copy_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        out["files"].append(record)
        diff = difflib.unified_diff(
            (EVIDENCE / "before-bytes" / rel)
            .read_text(encoding="utf-8")
            .splitlines(keepends=True),
            copy.read_text(encoding="utf-8").splitlines(keepends=True),
            fromfile=f"before/{rel}",
            tofile=f"after/{rel}",
            n=3,
        )
        diff_path = EVIDENCE / "diffs" / (pathlib.Path(rel).name + ".diff")
        diff_path.parent.mkdir(parents=True, exist_ok=True)
        diff_path.write_text("".join(diff), encoding="utf-8")
    previous = json.loads((PRE_DISPATCH / "mirror-inventory.json").read_text(encoding="utf-8"))
    current = inventory(WORKTREE)
    added = sorted(set(current) - set(previous))
    removed = sorted(set(previous) - set(current))
    modified = sorted(
        path for path in set(current) & set(previous) if current[path] != previous[path]
    )
    out["mirror_net_changes"] = {
        "previous_files": len(previous),
        "current_files": len(current),
        "added": added,
        "removed": removed,
        "modified": modified,
        "outside_write_face": [
            path
            for path in added + removed + modified
            if path not in FILES
        ],
    }
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *FILES],
        cwd=str(WORKTREE),
        capture_output=True,
        text=True,
    )
    out["git_status"] = [line for line in status.stdout.splitlines() if line.strip()]
    out["git_status_rc"] = status.returncode
    (EVIDENCE / "after-bytes.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "mirror-net-changes.json").write_text(
        json.dumps(out["mirror_net_changes"], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
