"""R2 before/after capture: bytes/SHA256/EOL of the two product files + inventory.

Run with -B and PYTHONDONTWRITEBYTECODE=1; writes only inside this rework-r2 dir.
argv: capture.py before|after
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

HERE = pathlib.Path(__file__).resolve().parent
KEY = HERE.parents[3]
WT = KEY / "implementation-worktree"
PKG = WT / "packages" / "multi-workers"
PRODUCTS = (
    "packages/multi-workers/decision_policy.py",
    "packages/multi-workers/test_dp_consolidation_recovery.py",
)


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def describe(path: pathlib.Path) -> dict:
    data = path.read_bytes()
    crlf = data.count(b"\r\n")
    bare_lf = data.count(b"\n") - crlf
    return {
        "relative": path.relative_to(WT).as_posix(),
        "bytes": len(data),
        "sha256": sha256(data),
        "crlf": crlf,
        "bare_lf": bare_lf,
        "ends_with_newline": data.endswith(b"\n"),
    }


def inventory() -> dict:
    rows = {}
    for path in sorted(WT.rglob("*")):
        if path.is_file():
            rows[path.relative_to(WT).as_posix()] = sha256(path.read_bytes())
    return rows


def main() -> int:
    stage = sys.argv[1]
    assert stage in ("before", "after"), stage
    result = {
        "stage": stage,
        "worktree": str(WT),
        "products": {rel: describe(WT / rel) for rel in PRODUCTS},
        "pyc_files": sorted(
            p.relative_to(WT).as_posix() for p in WT.rglob("*.pyc")
        ),
        "inventory_count": None,
        "inventory_sha256": None,
    }
    inv = inventory()
    encoded = json.dumps(inv, indent=0, sort_keys=True).encode("utf-8")
    result["inventory_count"] = len(inv)
    result["inventory_sha256"] = sha256(encoded)
    (HERE / f"{stage}.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    (HERE / f"{stage}-inventory.json").write_text(
        json.dumps(inv, indent=0, sort_keys=True) + "\n", encoding="utf-8"
    )
    (HERE / "before-bytes").mkdir(exist_ok=True)
    if stage == "before":
        for rel in PRODUCTS:
            target = HERE / "before-bytes" / rel.replace("/", "__")
            target.write_bytes((WT / rel).read_bytes())
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
