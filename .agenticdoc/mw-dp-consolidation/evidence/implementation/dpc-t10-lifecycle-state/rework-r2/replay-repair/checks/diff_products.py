"""Read-only unified diff: stage-B baseline copy -> current worktree product.

Usage:
  python -B <this file> <baseline-copy-dir> <worktree-dir> <file-name>

Prints one unified diff (``---``/``+++`` with canonical paths) on stdout and
prints nothing when the bytes are identical except a one-line ``identical``
marker. Reads bytes only; no product import, no pytest, no writes.
"""

from __future__ import annotations

import difflib
import hashlib
import pathlib
import sys

BASELINE_LABEL = ".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t10-lifecycle-state/rework-r2/product-repair/after-bytes"
WORKTREE_LABEL = ".agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers"


def main(argv: list[str]) -> int:
    baseline = pathlib.Path(argv[1])
    worktree = pathlib.Path(argv[2])
    name = argv[3]
    old = (baseline / name).read_bytes()
    new = (worktree / name).read_bytes()
    old_sha = hashlib.sha256(old).hexdigest()
    new_sha = hashlib.sha256(new).hexdigest()
    if old == new:
        print(f"identical: {name} {len(old)} bytes sha256 {old_sha}")
        return 0
    diff = difflib.unified_diff(
        old.decode("utf-8").splitlines(keepends=True),
        new.decode("utf-8").splitlines(keepends=True),
        fromfile=f"{BASELINE_LABEL}/{name} ({len(old)} bytes, sha256 {old_sha})",
        tofile=f"{WORKTREE_LABEL}/{name} ({len(new)} bytes, sha256 {new_sha})",
        n=3,
    )
    sys.stdout.write("".join(diff))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
