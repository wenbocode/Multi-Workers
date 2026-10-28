"""Compare the captured before/after manifests (read-only)."""

from __future__ import annotations

import json
import pathlib

EVIDENCE = pathlib.Path(__file__).resolve().parent

before = json.loads((EVIDENCE / "before-manifest.json").read_text(encoding="utf-8"))
after = json.loads((EVIDENCE / "after-manifest.json").read_text(encoding="utf-8"))

issues: list[str] = []
product = []
for old, new in zip(before["files"], after["files"]):
    assert old["path"] == new["path"]
    changed = old["sha256"] != new["sha256"]
    if old["main_tree"] != new["main_tree"]:
        issues.append(f"main tree moved for {old['path']}")
    product.append(
        {
            "path": old["path"],
            "changed": changed,
            "before_sha256": old["sha256"],
            "after_sha256": new["sha256"],
            "before_bytes": old["bytes"],
            "after_bytes": new["bytes"],
            "eol": [old["crlf"], old["bare_lf"], new["crlf"], new["bare_lf"]],
        }
    )
if [record["path"] for record in product if record["changed"]] != [
    "packages/multi-workers/test_decide_registry_contract.py"
]:
    issues.append("unexpected product set changed")

handoff_moved = [
    path
    for path, record in after["handoff"].items()
    if not record["current_matches_r2_after"]
]
if handoff_moved:
    issues.append(f"handoff rows moved: {handoff_moved}")

protected_moved = [
    path
    for path, record in after["protected_extra"].items()
    if before["protected_extra"][path]["sha256"] != record["sha256"]
]
if protected_moved:
    issues.append(f"protected extras moved: {protected_moved}")

for label in ("original-t03", "rework-r2"):
    old = before["evidence_boundary"][label]
    new = after["evidence_boundary"][label]
    if old["files"] != new["files"]:
        issues.append(f"{label}: evidence file count changed")
    if old["sha256"] != new["sha256"]:
        issues.append(f"{label}: original evidence bytes changed")

doc = {
    "ok": not issues,
    "issues": issues,
    "started_before_utc": before["observed_at_utc"],
    "observed_after_utc": after["observed_at_utc"],
    "main_head": after["main_head"],
    "product": product,
    "handoff_rows": len(after["handoff"]),
    "handoff_rows_matching_r2_after": len(after["handoff"]) - len(handoff_moved),
    "handoff_rows_moved": handoff_moved,
    "handoff_rows_changed_in_r3": [],
    "handoff_table_excludes": [
        "packages/multi-workers/test_decide_registry_contract.py",
        "packages/multi-workers/test_dp_consolidation_registry.py",
    ],
    "protected_extras_unchanged": not protected_moved,
    "evidence_boundary": {
        "original-t03_files": after["evidence_boundary"]["original-t03"]["files"],
        "rework-r2_files": after["evidence_boundary"]["rework-r2"]["files"],
        "unchanged": not any(
            issue.startswith(("original-t03", "rework-r2")) for issue in issues
        ),
    },
}
(EVIDENCE / "boundaries-check.json").write_text(
    json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
)
print(json.dumps({key: doc[key] for key in ("ok", "issues", "handoff_rows_matching_r2_after", "protected_extras_unchanged")}, ensure_ascii=False))
assert doc["ok"], issues
