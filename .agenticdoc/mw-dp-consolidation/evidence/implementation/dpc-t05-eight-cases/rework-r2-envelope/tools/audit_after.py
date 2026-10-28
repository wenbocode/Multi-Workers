"""Post-change audit: inventory diff, pyc state, 28 test functions, full diffs.

Compares the implementation copy against the fresh "before" state captured in
``before-metadata.json``/``inventory-before.json``/``pyc-before.json``/
``test-functions-before.json`` and records only what really changed.
"""

from __future__ import annotations

import ast
import datetime
import difflib
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

PRODUCTS = (
    "scripts/build_decide_cases.py",
    "decide_book_template.json",
    "test_decision_context_workbench.py",
    "decide_cases/dp-w-type.json",
    "decide_cases/dp-pm-steer.json",
    "decide_cases/dp-w-check-task.json",
    "decide_cases/dp-QG.json",
    "decide_cases/dp-gate-approve.json",
    "decide_cases/dp-sign-key.json",
    "decide_cases/dp-auto.json",
    "decide_cases/dp-route.json",
)
LEGACY_CASES = ("decide_cases/dp1.json", "decide_cases/dp2.json", "decide_cases/dp3.json", "decide_cases/dp25.json")
T10_PROTECTED = (
    "decision_wire.py",
    "decision_lifecycle.py",
    "decision_task_state.py",
    "test_decision_context_lifecycle.py",
    "test_decision_task_state.py",
)

#: The declared write face of task.md: the eleven products plus this evidence
#: directory. Nothing else may appear in the inventory diff.
ALLOWED_PRODUCT_SUFFIXES = {f"packages/multi-workers/{rel}" for rel in PRODUCTS}


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def describe(path: pathlib.Path) -> dict:
    data = path.read_bytes()
    text = data.decode("utf-8")
    return {
        "rel": path.relative_to(PKG).as_posix(),
        "bytes": len(data),
        "sha256": sha256(data),
        "lines": len(text.splitlines()),
        "lf": data.count(b"\n"),
        "crlf": data.count(b"\r\n"),
        "ends_with_newline": data.endswith(b"\n"),
    }


def functions() -> list[dict]:
    source = (PKG / "test_decision_context_workbench.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    out = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not node.name.startswith("test_"):
            continue
        segment = ast.get_source_segment(source, node) or ""
        out.append(
            {
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "assert_count": sum(1 for child in ast.walk(node) if isinstance(child, ast.Assert)),
                "ast_sha256": sha256(ast.dump(node).encode("utf-8")),
                "source_sha256": sha256(segment.encode("utf-8")),
            }
        )
    return out


def main() -> int:
    now = datetime.datetime.now(datetime.timezone.utc).isoformat()
    after = {
        "source": "agent-report",
        "observed_at_utc": now,
        "package_copy": PKG.as_posix(),
        "products": [describe(PKG / rel) for rel in PRODUCTS],
        "legacy_cases_read_only": [describe(PKG / rel) for rel in LEGACY_CASES],
        "t10_protected": [describe(PKG / rel) for rel in T10_PROTECTED],
    }
    (EVIDENCE / "after-metadata.json").write_text(
        json.dumps(after, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )

    inventory = {}
    pyc = {}
    for path in sorted(WT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(WT).as_posix()
        digest = sha256(path.read_bytes())
        inventory[rel] = digest
        if path.suffix == ".pyc":
            pyc[rel] = {"sha256": digest, "bytes": path.stat().st_size}
    (EVIDENCE / "inventory-after.json").write_text(
        json.dumps(
            {"inventory_root": WT.as_posix(), "file_count": len(inventory), "files": inventory},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (EVIDENCE / "pyc-after.json").write_text(
        json.dumps(
            {"package_copy": PKG.as_posix(), "pyc_count": len(pyc), "pyc": pyc},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    before_inventory = json.loads((EVIDENCE / "inventory-before.json").read_text(encoding="utf-8"))["files"]
    pyc_before = json.loads((EVIDENCE / "pyc-before.json").read_text(encoding="utf-8"))["pyc"]
    changed = sorted(
        rel
        for rel in set(before_inventory) | set(inventory)
        if before_inventory.get(rel) != inventory.get(rel)
    )
    outside_face = [rel for rel in changed if rel not in ALLOWED_PRODUCT_SUFFIXES]

    before_functions = {
        item["name"]: item
        for item in json.loads((EVIDENCE / "test-functions-before.json").read_text(encoding="utf-8"))
    }
    after_functions = {item["name"]: item for item in functions()}
    (EVIDENCE / "test-functions-after.json").write_text(
        json.dumps(list(after_functions.values()), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    delta = []
    for name, before_item in before_functions.items():
        after_item = after_functions.get(name)
        delta.append(
            {
                "name": name,
                "present": after_item is not None,
                "ast_unchanged": after_item is not None and after_item["ast_sha256"] == before_item["ast_sha256"],
                "source_unchanged": after_item is not None
                and after_item["source_sha256"] == before_item["source_sha256"],
                "lineno": [before_item["lineno"], after_item["lineno"] if after_item else None],
                "end_lineno": [before_item["end_lineno"], after_item["end_lineno"] if after_item else None],
                "asserts": [before_item["assert_count"], after_item["assert_count"] if after_item else None],
            }
        )
    added = sorted(set(after_functions) - set(before_functions))
    (EVIDENCE / "test-function-delta.json").write_text(
        json.dumps(
            {
                "before_count": len(before_functions),
                "after_count": len(after_functions),
                "removed": sorted(set(before_functions) - set(after_functions)),
                "added": added,
                "original_28_all_ast_and_source_identical": all(
                    row["ast_unchanged"] and row["source_unchanged"] for row in delta
                ),
                "original_28_all_locations_identical": all(row["lineno"][0] == row["lineno"][1] for row in delta),
                "delta": delta,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )

    diff_chunks = []
    for rel in PRODUCTS:
        before_path = EVIDENCE / "before-bytes" / "packages" / "multi-workers" / rel
        before_text = before_path.read_text(encoding="utf-8").splitlines(keepends=True)
        after_text = (PKG / rel).read_text(encoding="utf-8").splitlines(keepends=True)
        if before_text == after_text:
            continue
        diff_chunks.extend(
            difflib.unified_diff(
                before_text,
                after_text,
                fromfile=f"a/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/{rel}",
                tofile=f"b/.agenticdoc/mw-dp-consolidation/implementation-worktree/packages/multi-workers/{rel}",
                n=3,
            )
        )
    (EVIDENCE / "full-diff.patch").write_text("".join(diff_chunks), encoding="utf-8", newline="\n")

    changed_rows = []
    for rel in changed:
        before_row = next((row for row in after["products"] if row["rel"] == rel), None)
        changed_rows.append(
            {
                "path": f".agenticdoc/mw-dp-consolidation/implementation-worktree/{rel}",
                "before_sha256": before_inventory.get(rel),
                "after_sha256": inventory.get(rel),
                "after_bytes": before_row["bytes"] if before_row else (WT / rel).stat().st_size,
                "in_declared_face": rel in ALLOWED_PRODUCT_SUFFIXES,
            }
        )
    (EVIDENCE / "changed-files.json").write_text(
        json.dumps(
            {
                "source": "agent-report",
                "inventory_root": WT.as_posix(),
                "before_file_count": len(before_inventory),
                "after_file_count": len(inventory),
                "changed": changed_rows,
                "outside_declared_face": outside_face,
                "pyc_before": sorted(pyc_before),
                "pyc_after": sorted(pyc),
                "pyc_unchanged": pyc_before == pyc,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        json.dumps(
            {
                "before_file_count": len(before_inventory),
                "after_file_count": len(inventory),
                "changed": changed,
                "outside_declared_face": outside_face,
                "pyc_unchanged": pyc_before == pyc,
                "pyc_count": len(pyc),
                "test_functions_before": len(before_functions),
                "test_functions_after": len(after_functions),
                "added_tests": added,
                "original_28_ast_and_source_identical": all(
                    row["ast_unchanged"] and row["source_unchanged"] for row in delta
                ),
                "diff_bytes": sum(len(chunk) for chunk in diff_chunks),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if not outside_face and pyc_before == pyc else 1


if __name__ == "__main__":
    raise SystemExit(main())
