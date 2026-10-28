"""Compare the PM pre-dispatch inventory with a freshly walked file list.

Read-only. Explains exactly which files the 1891-entry window contains so the R2
capture can reproduce it byte-for-byte instead of guessing the exclusion rule.
"""

from __future__ import annotations

import json
import pathlib
import sys

ROOT = pathlib.Path("H:/git/Multi-Workers")
KEY_ROOT = pathlib.Path(__file__).resolve().parents[5]
PRE = KEY_ROOT / "evidence/implementation/t05-r2-pre-dispatch-20261027"

SKIP_DIRS = {
    ".git",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
}


def walk() -> set[str]:
    found: set[str] = set()
    for path in ROOT.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(ROOT).as_posix()
        parts = rel.split("/")
        if any(part in SKIP_DIRS for part in parts):
            continue
        found.add(rel)
    return found


def main() -> int:
    data = json.loads((PRE / "mirror-inventory.json").read_text(encoding="utf-8"))
    keys = set(data)
    walked = walk()
    missing = sorted(keys - walked)
    extra = sorted(walked - keys)
    print("inventory", len(keys), "walked", len(walked))
    print("in inventory but not walked:", len(missing))
    for rel in missing[:15]:
        print("  -", rel)
    print("walked but not inventoried:", len(extra))
    counts: dict[str, int] = {}
    for rel in extra:
        head = rel.split("/")[0]
        counts[head] = counts.get(head, 0) + 1
    for head, count in sorted(counts.items(), key=lambda item: -item[1]):
        print(f"  {head}: {count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
