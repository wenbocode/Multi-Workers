"""Prove the refused card changed nothing: re-hash the products and the copy.

Read-only. Every row is compared with the ``before`` capture taken at the start
of this R2 attempt (same bytes, same SHA256), and the whole-copy inventory and
the 14 legacy ``.pyc`` files are compared byte-for-byte as well.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

EVIDENCE = pathlib.Path(__file__).resolve().parents[1]
COPY_ROOT = EVIDENCE.parents[3] / "implementation-worktree"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def inventory() -> dict[str, str]:
    rows: dict[str, str] = {}
    for path in sorted(COPY_ROOT.rglob("*")):
        if path.is_file():
            rows[path.relative_to(COPY_ROOT).as_posix()] = sha256(path.read_bytes())
    return rows


def main() -> int:
    before = json.loads((EVIDENCE / "before-metadata.json").read_text(encoding="utf-8"))
    rows: list[dict] = []
    changed: list[str] = []
    for key in ("products", "legacy", "t10_products", "shared_inputs"):
        for row in before[key]:
            current = sha256((COPY_ROOT / row["path"]).read_bytes())
            same = current == row["sha256"]
            rows.append({"path": row["path"], "level": key, "unchanged": same, "sha256": current})
            if not same:
                changed.append(row["path"])

    old_inv = json.loads((EVIDENCE / "inventory-before.json").read_text(encoding="utf-8"))["files"]
    now_inv = inventory()
    inventory_changed = sorted(
        rel for rel in set(old_inv) | set(now_inv) if old_inv.get(rel) != now_inv.get(rel)
    )
    old_pyc = json.loads((EVIDENCE / "pyc-before.json").read_text(encoding="utf-8"))
    now_pyc = {
        path.relative_to(COPY_ROOT).as_posix(): sha256(path.read_bytes())
        for path in sorted(COPY_ROOT.rglob("*.pyc"))
    }
    pyc_changed = sorted(
        rel
        for rel in set(old_pyc) | set(now_pyc)
        if (old_pyc.get(rel) or {}).get("sha256") != now_pyc.get(rel)
    )

    payload = {
        "source": "agent-report",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "copy_root": str(COPY_ROOT),
        "product_rows_checked": len(rows),
        "changed_products": changed,
        "inventory_file_count": len(now_inv),
        "inventory_changed": inventory_changed,
        "pyc_file_count": len(now_pyc),
        "pyc_changed": pyc_changed,
        "all_products_unchanged": not changed,
        "rows": rows,
    }
    (EVIDENCE / "blocker").mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "blocker" / "unmodified.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "product_rows_checked": len(rows),
                "all_products_unchanged": not changed,
                "changed_products": changed,
                "inventory_file_count": len(now_inv),
                "inventory_changed": inventory_changed,
                "pyc_file_count": len(now_pyc),
                "pyc_changed": pyc_changed,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
