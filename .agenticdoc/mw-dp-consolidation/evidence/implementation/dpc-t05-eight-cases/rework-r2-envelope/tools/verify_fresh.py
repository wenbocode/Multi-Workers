"""Verify the freshly captured "before" against the PM pre-dispatch baseline.

Proves the R2-envelope attempt starts from the exact bytes the PM dispatched on
(no drift since ``t05-r2-envelope-pre-dispatch-20261027``), and that the
read-only faces (four legacy cases, T10 products/tests) are untouched.

Read-only; writes only ``fresh-before-check.json`` in this evidence directory.
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

assert sys.dont_write_bytecode

HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE.parent
KEY = EVIDENCE.parents[3]
WT = KEY / "implementation-worktree"
PKG = WT / "packages" / "multi-workers"
PM = KEY / "evidence" / "implementation" / "t05-r2-envelope-pre-dispatch-20261027"

LEGACY_SHA = {
    "dp1.json": "3131c02f4830b96994e3bea94efe1be8511fd7936f8c983cf579596218a6c9ff",
    "dp2.json": "a03e1a29540ba9636a0a37bf478598bb530c357fc65d54b5eaaf6326e16342ea",
    "dp3.json": "82ff47e50ab5f24cfd84c793c07e2d15484ea89c24a90c8595306c468f407f2d",
    "dp25.json": "bda25144a8c5cd73978603a3dc4c9b429d8d451485679d99ef46cfcc4c2cc7fd",
}


def digest(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    before = json.loads((EVIDENCE / "before-metadata.json").read_text(encoding="utf-8"))
    baseline = json.loads((PM / "before-metadata.json").read_text(encoding="utf-8"))
    baseline_rows = {row["path"].rsplit("multi-workers/", 1)[1]: row for row in baseline}
    rows = []
    for row in before["products"]:
        expected = baseline_rows[row["rel"]]
        rows.append(
            {
                "rel": row["rel"],
                "bytes": row["bytes"],
                "sha256": row["sha256"],
                "matches_pre_dispatch": row["sha256"] == expected["sha256"]
                and row["bytes"] == expected["bytes"],
                "pre_dispatch_sha256": expected["sha256"],
            }
        )

    legacy = {
        name: {"sha256": digest(PKG / "decide_cases" / name), "expected": sha}
        for name, sha in LEGACY_SHA.items()
    }
    t10 = json.loads((PM / "T10-products-protection.json").read_text(encoding="utf-8"))
    t10_rows = []
    for key, expected in sorted(t10.items()):
        candidate = KEY.parents[1] / key
        if not candidate.is_file():
            t10_rows.append({"path": key, "sha256": None, "matches": False})
            continue
        t10_rows.append(
            {
                "path": key,
                "sha256": digest(candidate),
                "expected": expected,
                "matches": digest(candidate) == expected,
            }
        )
    inventory = json.loads((EVIDENCE / "inventory-before.json").read_text(encoding="utf-8"))
    pyc = json.loads((EVIDENCE / "pyc-before.json").read_text(encoding="utf-8"))

    result = {
        "source": "agent-report",
        "observed_at": before["observed_at_utc"],
        "products_match_pre_dispatch": all(row["matches_pre_dispatch"] for row in rows),
        "products": rows,
        "legacy_cases": legacy,
        "legacy_cases_match": all(item["sha256"] == item["expected"] for item in legacy.values()),
        "t10_protection_rows": t10_rows,
        "t10_matches": all(row["matches"] for row in t10_rows) and len(t10_rows) == 5,
        "inventory_root": inventory["inventory_root"],
        "inventory_file_count": inventory["file_count"],
        "pyc_count": pyc["pyc_count"],
        "pyc": sorted(pyc["pyc"]),
        "test_function_count": len(
            json.loads((EVIDENCE / "test-functions-before.json").read_text(encoding="utf-8"))
        ),
    }
    (EVIDENCE / "fresh-before-check.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        json.dumps(
            {
                "products_match_pre_dispatch": result["products_match_pre_dispatch"],
                "legacy_cases_match": result["legacy_cases_match"],
                "inventory_file_count": result["inventory_file_count"],
                "pyc_count": result["pyc_count"],
                "test_function_count": result["test_function_count"],
                "t10_rows": len(t10_rows),
                "t10_matches": result["t10_matches"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return (
        0
        if result["products_match_pre_dispatch"]
        and result["legacy_cases_match"]
        and result["t10_matches"]
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())
