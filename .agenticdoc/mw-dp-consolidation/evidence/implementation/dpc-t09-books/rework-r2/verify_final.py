"""R2 final self-check: on-disk products still match the recorded after bytes.

Recomputes the two product hashes, the 14 pyc inventory, the frozen before
snapshots and the recorded run rcs, then writes runs/verify-final.json. Exits
non-zero on any drift, so the report's claims are checked against files, not
prose.
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
PKG = KEY / "implementation-worktree" / "packages" / "multi-workers"
FILES = ("decision_book.py", "test_decision_context_contract.py")

before = json.loads((HERE / "before-bytes.json").read_text(encoding="utf-8"))
after = json.loads((HERE / "after-bytes.json").read_text(encoding="utf-8"))
net = json.loads((HERE / "inventory" / "net-changes.json").read_text(encoding="utf-8"))
ast = json.loads((HERE / "inventory" / "ast-preservation.json").read_text(encoding="utf-8"))
probe_before = json.loads((HERE / "probe-before-red.json").read_text(encoding="utf-8"))
probe_after = json.loads((HERE / "probe-after-green.json").read_text(encoding="utf-8"))


def sha(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


problems: list[str] = []
products = {}
for name in FILES:
    current = sha(PKG / name)
    snapshot = sha(HERE / "before-bytes" / f"{name}.before")
    entry = {
        "after_sha256_on_disk": current,
        "after_sha256_recorded": after["products"][name]["after_sha256"],
        "before_snapshot_sha256": snapshot,
        "before_sha256_recorded": before["products"][name]["sha256"],
        "bytes_on_disk": (PKG / name).stat().st_size,
        "bytes_recorded": after["products"][name]["after_bytes"],
    }
    if current != entry["after_sha256_recorded"]:
        problems.append(f"{name}: after sha drifted")
    if snapshot != entry["before_sha256_recorded"]:
        problems.append(f"{name}: before snapshot drifted")
    if entry["bytes_on_disk"] != entry["bytes_recorded"]:
        problems.append(f"{name}: after bytes drifted")
    products[name] = entry

pyc = sorted(PKG.rglob("*.pyc"))
if len(pyc) != before["pyc_count"]:
    problems.append("pyc population changed")
if pyc != sorted(pathlib.Path(ROOT / row["path"]) for row in before["pyc"]):
    problems.append("pyc path set changed")
if any(sha(path) != row["sha256"] for path, row in zip(pyc, before["pyc"])):
    problems.append("pyc bytes changed")

expected_runs = {
    "baseline-1": 0,
    "baseline-2": 0,
    "red-1": 1,
    "green-1": 0,
    "green-2": 0,
    "probe-before-red": 1,
    "probe-after-green": 0,
    "green-3": 0,
    "ast-inventory": 0,
    "capture-after": 0,
    "inventory-after": 0,
}
runs = {
    label: int((HERE / "runs" / f"{label}.rc").read_text(encoding="utf-8").strip())
    for label in expected_runs
}
if runs != expected_runs:
    problems.append(f"run rcs differ: {runs}")

if net["modified"] != [
    "packages/multi-workers/decision_book.py",
    "packages/multi-workers/test_decision_context_contract.py",
] or net["added"] or net["removed"] or net["outside_declared_products"]:
    problems.append("mirror net changes exceed the two declared faces")
if net["protected_added"] or net["protected_removed"] or net["protected_modified"]:
    problems.append("protected evidence changed")
if not ast["preserved_exactly"] or ast["missing"] or ast["changed"]:
    problems.append("original test functions were not preserved exactly")
if probe_before["base_17_passed"] != 4 or probe_before["base_17_failed"] != 13:
    problems.append("red probe did not reproduce the PM 4/13 baseline")
if probe_after["base_17_passed"] != 17 or probe_after["base_17_failed"] != 0:
    problems.append("green probe did not reach 17/0")

summary = {
    "source": "agent-report",
    "products": products,
    "pyc_count": len(pyc),
    "runs": runs,
    "mirror_modified": net["modified"],
    "ast_preserved_exactly": ast["preserved_exactly"],
    "ast_added_functions": len(ast["added"]),
    "probe_before": {"base_17_passed": probe_before["base_17_passed"], "base_17_failed": probe_before["base_17_failed"], "total_passed": probe_before["passed"], "total_failed": probe_before["failed"]},
    "probe_after": {"base_17_passed": probe_after["base_17_passed"], "base_17_failed": probe_after["base_17_failed"], "total_passed": probe_after["passed"], "total_failed": probe_after["failed"]},
    "problems": problems,
}
(HERE / "runs" / "verify-final.json").write_text(
    json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps(summary, ensure_ascii=False, indent=2))
raise SystemExit(1 if problems else 0)
