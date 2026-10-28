"""R2 after-state diff + inventory delta. Run with -B / PYTHONDONTWRITEBYTECODE=1."""

from __future__ import annotations

import difflib
import hashlib
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
PRODUCTS = (
    "packages/multi-workers/decision_policy.py",
    "packages/multi-workers/test_dp_consolidation_recovery.py",
)


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


before_inv = json.loads((HERE / "before-inventory.json").read_text(encoding="utf-8"))
after_inv = json.loads((HERE / "after-inventory.json").read_text(encoding="utf-8"))

changed = sorted(
    rel
    for rel in set(before_inv) | set(after_inv)
    if before_inv.get(rel) != after_inv.get(rel)
)
added = sorted(set(after_inv) - set(before_inv))
removed = sorted(set(before_inv) - set(after_inv))

parts: list[str] = []
per_file = {}
for rel in PRODUCTS:
    before = (HERE / "before-bytes" / rel.replace("/", "__")).read_bytes()
    after = (HERE.parents[3] / "implementation-worktree" / rel).read_bytes()
    text = "".join(
        difflib.unified_diff(
            before.decode("utf-8").splitlines(keepends=True),
            after.decode("utf-8").splitlines(keepends=True),
            fromfile="a/" + rel,
            tofile="b/" + rel,
        )
    )
    parts.append(text)
    per_file[rel] = {
        "before_bytes": len(before),
        "before_sha256": sha(before),
        "after_bytes": len(after),
        "after_sha256": sha(after),
        "after_crlf": after.count(b"\r\n"),
        "after_bare_lf": after.count(b"\n") - after.count(b"\r\n"),
        "added_lines": sum(
            1 for line in text.splitlines() if line.startswith("+") and not line.startswith("+++")
        ),
        "removed_lines": sum(
            1 for line in text.splitlines() if line.startswith("-") and not line.startswith("---")
        ),
    }

diff = "".join(parts).encode("utf-8")
(HERE / "r2-increment.diff").write_bytes(diff)
result = {
    "products": per_file,
    "increment_diff_bytes": len(diff),
    "increment_diff_sha256": sha(diff),
    "inventory_changed": changed,
    "inventory_added": added,
    "inventory_removed": removed,
    "inventory_only_products_changed": changed == list(PRODUCTS),
    "pyc_unchanged": before_inv.get("pyc-snapshot") is None,
}
result.pop("pyc_unchanged", None)
result["pyc_before_count"] = sum(1 for rel in before_inv if rel.endswith(".pyc"))
result["pyc_after_count"] = sum(1 for rel in after_inv if rel.endswith(".pyc"))
result["pyc_byte_identical"] = all(
    before_inv[rel] == after_inv.get(rel)
    for rel in before_inv
    if rel.endswith(".pyc")
)
(HERE / "after-summary.json").write_text(
    json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
)
print(json.dumps(result, indent=2, ensure_ascii=False))
