"""Capture the R2 product/input state (``before`` or ``after``) as evidence.

Read-only over the isolated implementation copy: nothing outside this card's
``rework-r2`` evidence directory is written. Every record is bytes + SHA256 +
EOL counts, so a later diff is byte-exact instead of a re-render.

Usage (always bytecode-free)::

    PYTHONDONTWRITEBYTECODE=1 python -B tools/capture_state.py before
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import sys
from datetime import datetime, timezone

EVIDENCE = pathlib.Path(__file__).resolve().parents[1]
KEY_ROOT = EVIDENCE.parents[3]  # .agenticdoc/mw-dp-consolidation
COPY_ROOT = KEY_ROOT / "implementation-worktree"
PKG_REL = "packages/multi-workers"

#: The eleven product files of this card's write face (the exact copy products).
PRODUCTS = [
    f"{PKG_REL}/scripts/build_decide_cases.py",
    f"{PKG_REL}/decide_book_template.json",
    f"{PKG_REL}/test_decision_context_workbench.py",
    f"{PKG_REL}/decide_cases/dp-w-type.json",
    f"{PKG_REL}/decide_cases/dp-pm-steer.json",
    f"{PKG_REL}/decide_cases/dp-w-check-task.json",
    f"{PKG_REL}/decide_cases/dp-QG.json",
    f"{PKG_REL}/decide_cases/dp-gate-approve.json",
    f"{PKG_REL}/decide_cases/dp-sign-key.json",
    f"{PKG_REL}/decide_cases/dp-auto.json",
    f"{PKG_REL}/decide_cases/dp-route.json",
]

#: Byte-locked read-only history: never generated or edited here.
LEGACY = [
    f"{PKG_REL}/decide_cases/dp1.json",
    f"{PKG_REL}/decide_cases/dp2.json",
    f"{PKG_REL}/decide_cases/dp3.json",
    f"{PKG_REL}/decide_cases/dp25.json",
]

#: T10's current write face (protected input, never written from this card).
T10_PRODUCTS = [
    f"{PKG_REL}/decision_wire.py",
    f"{PKG_REL}/decision_lifecycle.py",
    f"{PKG_REL}/decision_task_state.py",
    f"{PKG_REL}/test_decision_context_lifecycle.py",
    f"{PKG_REL}/test_decision_task_state.py",
]

#: Shared read-only inputs the workbench suite consumes (drift is instability).
SHARED_INPUTS = [
    f"{PKG_REL}/decision_book.py",
    f"{PKG_REL}/decision_points.py",
    f"{PKG_REL}/decision_context.py",
    f"{PKG_REL}/decision_history.py",
    f"{PKG_REL}/decision_monitor.py",
    f"{PKG_REL}/decision_playground.py",
    f"{PKG_REL}/decide_registry.json",
]

WORKBENCH_TEST = f"{PKG_REL}/test_decision_context_workbench.py"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def describe(rel: str) -> dict:
    path = COPY_ROOT / rel
    if not path.is_file():
        return {"path": rel, "exists": False, "bytes": None, "sha256": None, "lf": None, "crlf": None}
    data = path.read_bytes()
    return {
        "path": rel,
        "exists": True,
        "bytes": len(data),
        "sha256": sha256(data),
        "lf": data.count(b"\n") - data.count(b"\r\n"),
        "crlf": data.count(b"\r\n"),
    }


def test_functions() -> dict:
    source = (COPY_ROOT / WORKBENCH_TEST).read_text(encoding="utf-8")
    tree = ast.parse(source)
    rows: dict[str, dict] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        segment = ast.get_source_segment(source, node)
        assert segment is not None
        rows[node.name] = {
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "args": [arg.arg for arg in node.args.args],
            "decorators": [ast.unparse(item) for item in node.decorator_list],
            "ast_sha256": sha256(ast.dump(node, include_attributes=False).encode("utf-8")),
            "source_sha256": sha256(segment.encode("utf-8")),
            "source": segment,
        }
    return rows


def inventory() -> dict[str, str]:
    rows: dict[str, str] = {}
    for path in sorted(COPY_ROOT.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(COPY_ROOT).as_posix()
        rows[rel] = sha256(path.read_bytes())
    return rows


def pyc_rows() -> dict[str, dict]:
    rows: dict[str, dict] = {}
    for path in sorted(COPY_ROOT.rglob("*.pyc")):
        rel = path.relative_to(COPY_ROOT).as_posix()
        data = path.read_bytes()
        rows[rel] = {"sha256": sha256(data), "bytes": len(data)}
    return rows


def main(argv: list[str]) -> int:
    if len(argv) != 2 or argv[1] not in ("before", "after"):
        raise SystemExit("usage: capture_state.py before|after")
    label = argv[1]

    before_meta_path = EVIDENCE / "before-metadata.json"
    before_meta = (
        json.loads(before_meta_path.read_text(encoding="utf-8"))
        if before_meta_path.is_file()
        else None
    )

    products = [describe(rel) for rel in PRODUCTS]
    legacy = [describe(rel) for rel in LEGACY]
    t10 = [describe(rel) for rel in T10_PRODUCTS]
    shared = [describe(rel) for rel in SHARED_INPUTS]

    # Byte copies (before/after) so the diff is against real bytes, not a render.
    for row in products + legacy:
        if row["exists"]:
            target = EVIDENCE / f"{label}-bytes" / row["path"]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes((COPY_ROOT / row["path"]).read_bytes())

    functions = test_functions()
    (EVIDENCE / f"test-functions-{label}.json").write_text(
        json.dumps(functions, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    inv = inventory()
    inv_payload = {
        "source": "agent-report",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "root": str(COPY_ROOT),
        "file_count": len(inv),
        "files": inv,
    }
    (EVIDENCE / f"inventory-{label}.json").write_text(
        json.dumps(inv_payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    pyc = pyc_rows()
    (EVIDENCE / f"pyc-{label}.json").write_text(
        json.dumps(pyc, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    payload = {
        "source": "agent-report",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "label": label,
        "copy_root": str(COPY_ROOT),
        "products": products,
        "legacy": legacy,
        "t10_products": t10,
        "shared_inputs": shared,
        "test_function_count": len(functions),
        "inventory_file_count": len(inv),
        "pyc_file_count": len(pyc),
    }
    (EVIDENCE / f"{label}-metadata.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    # Comparison against the captured before-image (or the PM pre-dispatch file).
    report: dict = {"label": label, "product_changes": [], "legacy_changes": [], "t10_changes": [], "shared_changes": []}
    if label == "after" and before_meta is not None:
        for key, rows in (
            ("products", products),
            ("legacy", legacy),
            ("t10_products", t10),
            ("shared_inputs", shared),
        ):
            old = {row["path"]: row["sha256"] for row in before_meta[key]}
            report[key.replace("_products", "").replace("_inputs", "") + "_changes"] = [
                {"path": row["path"], "before": old.get(row["path"]), "after": row["sha256"]}
                for row in rows
                if old.get(row["path"]) != row["sha256"]
            ]
        old_functions = json.loads(
            (EVIDENCE / "test-functions-before.json").read_text(encoding="utf-8")
        )
        report["test_function_changes"] = {
            "removed": sorted(set(old_functions) - set(functions)),
            "added": sorted(set(functions) - set(old_functions)),
            "ast_changed": sorted(
                name
                for name in set(old_functions) & set(functions)
                if old_functions[name]["ast_sha256"] != functions[name]["ast_sha256"]
            ),
        }
        old_inv = json.loads((EVIDENCE / "inventory-before.json").read_text(encoding="utf-8"))["files"]
        report["inventory_changes"] = sorted(
            rel for rel in set(old_inv) | set(inv) if old_inv.get(rel) != inv.get(rel)
        )
        old_pyc = json.loads((EVIDENCE / "pyc-before.json").read_text(encoding="utf-8"))
        report["pyc_changes"] = sorted(
            rel
            for rel in set(old_pyc) | set(pyc)
            if (old_pyc.get(rel) or {}).get("sha256") != (pyc.get(rel) or {}).get("sha256")
        )
        (EVIDENCE / "state-delta.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    print(json.dumps({k: v for k, v in payload.items() if k not in ("products", "legacy", "t10_products", "shared_inputs")}, ensure_ascii=False, indent=2))
    for row in products + legacy:
        print(f"  {row['sha256']}  {row['bytes']:>7}  {row['path']}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
