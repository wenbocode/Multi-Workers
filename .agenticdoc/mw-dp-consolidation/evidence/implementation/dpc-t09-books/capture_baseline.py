"""Capture the T09 before-bytes (copy-local, never the live tree).

Writes only inside this card's evidence directory:
  before-bytes/<relpath>        raw bytes of the current copy
  before-bytes.json             path/bytes/sha256/EOL/lines/mtime + live compare
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import shutil
import subprocess
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
WORKTREE = EVIDENCE.parents[2] / "implementation-worktree"
LIVE_ROOT = EVIDENCE.parents[4]

FILES = (
    "packages/multi-workers/decision_book.py",
    "packages/multi-workers/test_decision_context_contract.py",
)


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


def main() -> int:
    out: dict = {
        "worktree": str(WORKTREE),
        "live_root": str(LIVE_ROOT),
        "python": sys.version,
        "files": [],
        "live_compare": [],
        "git_status": [],
    }
    for rel in FILES:
        copy = WORKTREE / rel
        target = EVIDENCE / "before-bytes" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(copy, target)
        record = describe(copy)
        record["relpath"] = rel
        record["evidence_copy"] = str(target)
        record["evidence_copy_sha256"] = hashlib.sha256(target.read_bytes()).hexdigest()
        out["files"].append(record)
        live = LIVE_ROOT / rel
        if live.exists():
            live_record = describe(live)
            out["live_compare"].append(
                {
                    "relpath": rel,
                    "live_sha256": live_record["sha256"],
                    "copy_sha256": record["sha256"],
                    "equal": live_record["sha256"] == record["sha256"],
                    "samefile": live.resolve() == copy.resolve(),
                }
            )
        else:
            out["live_compare"].append({"relpath": rel, "live": "absent"})
    status = subprocess.run(
        ["git", "status", "--porcelain", "--", *FILES],
        cwd=str(WORKTREE),
        capture_output=True,
        text=True,
    )
    out["git_status"] = [line for line in status.stdout.splitlines() if line.strip()]
    out["git_status_rc"] = status.returncode
    (EVIDENCE / "before-bytes.json").write_text(
        json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
