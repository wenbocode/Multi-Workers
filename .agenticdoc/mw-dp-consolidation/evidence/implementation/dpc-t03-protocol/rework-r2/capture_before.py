"""T03-R2 evidence helper: capture the *current* four product files before editing.

Read-only w.r.t. product files. Writes, next to this script:
- ``before-manifest.json``: sha256/bytes/CRLF/bare-LF/lines per file, plus the
  comparison with the PM handoff hashes (check.json) and the original T03
  after-bytes, and the diff-vs-main-tree dirty state;
- ``before-bytes/``: byte copies of the four files;
- ``before-dirty-vs-main-tree.diff``: unified diff of each copy against the
  same-named file in the main tree (the pre-T03 source), so the pre-existing
  uncommitted difference is recorded rather than re-derived from git (the whole
  implementation-worktree is untracked).

Usage: ``python capture_before.py``; cwd is not significant.
"""

from __future__ import annotations

import difflib
import hashlib
import json
import pathlib
import shutil
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
KEY = EVIDENCE.parents[3]
WORKTREE = KEY / "implementation-worktree"
MAIN_TREE = KEY.parents[1]
PM_CHECK = EVIDENCE.parents[1] / "t03-pm-handoff-20261026" / "check.json"
T03_AFTER = EVIDENCE.parent / "after-bytes"

FILES = (
    "packages/multi-workers/decision_points.py",
    "packages/multi-workers/decide_registry.json",
    "packages/multi-workers/test_decide_registry_contract.py",
    "packages/multi-workers/test_dp_consolidation_registry.py",
)


def measure(raw: bytes) -> dict:
    lf = raw.count(b"\n")
    crlf = raw.count(b"\r\n")
    return {
        "sha256": hashlib.sha256(raw).hexdigest(),
        "bytes": len(raw),
        "crlf": crlf,
        "bare_lf": lf - crlf,
        "lines": len(raw.splitlines()),
    }


def main() -> int:
    out_bytes = EVIDENCE / "before-bytes"
    out_bytes.mkdir(parents=True, exist_ok=True)
    pm_hashes = {
        row["path"]: row["sha256"]
        for row in json.loads(PM_CHECK.read_text(encoding="utf-8"))["files"]
    }
    manifest: dict = {
        "stage": "before-r2",
        "root": "implementation-worktree",
        "pm_handoff_check": str(PM_CHECK.relative_to(KEY)).replace("\\", "/"),
        "files": [],
    }
    diff_chunks: list[str] = []
    for relative in FILES:
        path = WORKTREE / relative
        raw = path.read_bytes()
        row = {"path": relative, **measure(raw), "exists": True}
        name = pathlib.PurePosixPath(relative).name
        shutil.copyfile(path, out_bytes / name)
        row["pm_handoff_sha256"] = pm_hashes.get(relative)
        row["matches_pm_handoff"] = row["sha256"] == pm_hashes.get(relative)
        t03 = T03_AFTER / name
        row["matches_t03_after_bytes"] = (
            t03.is_file() and t03.read_bytes() == raw
        )
        main_source = MAIN_TREE / relative
        if main_source.is_file():
            before = main_source.read_bytes()
            row["main_tree_sha256"] = hashlib.sha256(before).hexdigest()
            row["dirty_vs_main_tree"] = before != raw
            diff_chunks.extend(
                difflib.unified_diff(
                    before.decode("utf-8").splitlines(keepends=True),
                    raw.decode("utf-8").splitlines(keepends=True),
                    fromfile=f"main-tree/{relative}",
                    tofile=f"implementation-worktree/{relative}",
                )
            )
        else:
            row["main_tree_sha256"] = None
            row["dirty_vs_main_tree"] = True
        manifest["files"].append(row)
    (EVIDENCE / "before-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (EVIDENCE / "before-dirty-vs-main-tree.diff").write_text(
        "".join(diff_chunks), encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
