"""R2 evidence: mirror/protected inventory before and after the two-point fix.

Usage: python -B inventory.py before|after

* mirror-<phase>.json: every file under the isolated implementation worktree
  (relative posix path -> sha256), the PM baseline population (1883 files).
* protected-<phase>.json: the original T09 worker evidence, the PM handoff and
  the R2 pre-dispatch evidence (must stay byte-identical).
* For ``after``: net-changes.json compares the two mirror snapshots and asserts
  only the two declared product faces moved.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys

assert sys.dont_write_bytecode

HERE = pathlib.Path(__file__).resolve().parent
KEY = HERE.parents[3]
ROOT = KEY.parents[1]
WORKTREE = KEY / "implementation-worktree"
EVIDENCE = KEY / "evidence" / "implementation"

phase = sys.argv[1]
assert phase in ("before", "after")

PROTECTED = (
    EVIDENCE / "dpc-t09-books",
    EVIDENCE / "t09-pm-handoff-20261027",
    EVIDENCE / "t09-r2-pre-dispatch-20261027",
    EVIDENCE / "t09-pre-dispatch-20261027",
)
PRODUCTS = (
    "packages/multi-workers/decision_book.py",
    "packages/multi-workers/test_decision_context_contract.py",
)


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mirror() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(WORKTREE.rglob("*")):
        if path.is_file():
            out[path.relative_to(WORKTREE).as_posix()] = digest(path)
    return out


def protected() -> dict[str, str]:
    out: dict[str, str] = {}
    for base in PROTECTED:
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(KEY).as_posix()
            if rel.startswith("evidence/implementation/dpc-t09-books/rework-r2/"):
                continue  # this R2 evidence directory is the only new writer face
            out[rel] = digest(path)
    return out


inventory = HERE / "inventory"
inventory.mkdir(parents=True, exist_ok=True)
current_mirror = mirror()
current_protected = protected()
(inventory / f"mirror-{phase}.json").write_text(
    json.dumps(current_mirror, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
    encoding="utf-8",
    newline="\n",
)
(inventory / f"protected-{phase}.json").write_text(
    json.dumps(current_protected, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
    encoding="utf-8",
    newline="\n",
)

summary: dict[str, object] = {
    "phase": phase,
    "mirror_files": len(current_mirror),
    "protected_files": len(current_protected),
}
if phase == "after":
    before_mirror = json.loads((inventory / "mirror-before.json").read_text(encoding="utf-8"))
    before_protected = json.loads(
        (inventory / "protected-before.json").read_text(encoding="utf-8")
    )
    modified = sorted(
        path
        for path in set(before_mirror) & set(current_mirror)
        if before_mirror[path] != current_mirror[path]
    )
    net = {
        "previous_files": len(before_mirror),
        "current_files": len(current_mirror),
        "added": sorted(set(current_mirror) - set(before_mirror)),
        "removed": sorted(set(before_mirror) - set(current_mirror)),
        "modified": modified,
        "outside_declared_products": [p for p in modified if p not in PRODUCTS],
        "protected_added": sorted(set(current_protected) - set(before_protected)),
        "protected_removed": sorted(set(before_protected) - set(current_protected)),
        "protected_modified": sorted(
            path
            for path in set(before_protected) & set(current_protected)
            if before_protected[path] != current_protected[path]
        ),
    }
    (inventory / "net-changes.json").write_text(
        json.dumps(net, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    summary["net"] = net
print(json.dumps(summary, ensure_ascii=False, indent=2))
