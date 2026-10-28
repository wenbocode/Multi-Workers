"""Capture the real R2-envelope "before" state (bytes/hash/EOL, 28 test ASTs, pyc).

Read-only with respect to every product: it only writes inside this evidence
directory. Run as::

    PYTHONDONTWRITEBYTECODE=1 python -B tools/capture_before.py

No network, no credential, no decision CLI, no service, no model.
"""

from __future__ import annotations

import ast
import datetime
import hashlib
import json
import pathlib
import sys

assert sys.dont_write_bytecode, "this tool must run with -B / PYTHONDONTWRITEBYTECODE=1"

HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE.parent
KEY = EVIDENCE.parents[3]  # .agenticdoc/mw-dp-consolidation
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

LEGACY_CASES = (
    "decide_cases/dp1.json",
    "decide_cases/dp2.json",
    "decide_cases/dp3.json",
    "decide_cases/dp25.json",
)

T10_PROTECTED = (
    "decision_wire.py",
    "decision_lifecycle.py",
    "decision_task_state.py",
    "test_decision_context_lifecycle.py",
    "test_decision_task_state.py",
)


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
        "trailing_bytes": data[-1:].decode("utf-8", "replace"),
    }


def main() -> int:
    rows = [describe(PKG / rel) for rel in PRODUCTS]
    legacy = [describe(PKG / rel) for rel in LEGACY_CASES]
    protected = [describe(PKG / rel) for rel in T10_PROTECTED]

    # raw bytes of every read-only face the R2 diff is measured against
    for rel in (*PRODUCTS, *LEGACY_CASES):
        target = EVIDENCE / "before-bytes" / "packages" / "multi-workers" / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((PKG / rel).read_bytes())

    test_path = PKG / "test_decision_context_workbench.py"
    test_source = test_path.read_text(encoding="utf-8")
    tree = ast.parse(test_source)
    functions = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        segment = ast.get_source_segment(test_source, node) or ""
        functions.append(
            {
                "name": node.name,
                "lineno": node.lineno,
                "end_lineno": node.end_lineno,
                "decorators": [ast.unparse(item) for item in node.decorator_list],
                "args": [arg.arg for arg in node.args.args],
                "assert_count": sum(
                    1 for child in ast.walk(node) if isinstance(child, ast.Assert)
                ),
                "ast_sha256": sha256(ast.dump(node).encode("utf-8")),
                "source_sha256": sha256(segment.encode("utf-8")),
                "source": segment,
            }
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

    payload = {
        "source": "agent-report",
        "observed_at_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "inventory_root": WT.as_posix(),
        "package_copy": PKG.as_posix(),
        "products": rows,
        "legacy_cases_read_only": legacy,
        "t10_protected": protected,
        "inventory_file_count": len(inventory),
        "pyc_file_count": len(pyc),
        "test_function_count": len(functions),
        "python": sys.version,
    }
    (EVIDENCE / "before-metadata.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (EVIDENCE / "test-functions-before.json").write_text(
        json.dumps(functions, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (EVIDENCE / "inventory-before.json").write_text(
        json.dumps(
            {"inventory_root": WT.as_posix(), "file_count": len(inventory), "files": inventory},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    (EVIDENCE / "pyc-before.json").write_text(
        json.dumps(
            {"package_copy": PKG.as_posix(), "pyc_count": len(pyc), "pyc": pyc},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    summary = {
        "products": [(row["rel"], row["bytes"], row["sha256"]) for row in rows],
        "inventory_file_count": len(inventory),
        "pyc_file_count": len(pyc),
        "test_function_count": len(functions),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
