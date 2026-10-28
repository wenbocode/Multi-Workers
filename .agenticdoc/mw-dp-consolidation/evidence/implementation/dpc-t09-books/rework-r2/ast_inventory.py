"""R2 evidence: prove the original contract tests survive byte-identically.

Parses the pre-fix snapshot and the current test file, keeps every module-level
``test_*`` function's exact source text (lines 0-based inclusive span of the
``def`` statement plus decorators) and compares by SHA256. Writes
inventory/test-functions-before.json, inventory/test-functions-after.json and
inventory/ast-preservation.json.
"""
from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import sys

assert sys.dont_write_bytecode

HERE = pathlib.Path(__file__).resolve().parent
SNAPSHOT = HERE / "before-bytes" / "test_decision_context_contract.py.before"
CURRENT = (
    HERE.parents[3]
    / "implementation-worktree"
    / "packages"
    / "multi-workers"
    / "test_decision_context_contract.py"
)


def inventory(path: pathlib.Path) -> dict[str, dict[str, object]]:
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines(keepends=True)
    tree = ast.parse(source)
    out: dict[str, dict[str, object]] = {}
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if not node.name.startswith("test_"):
            continue
        start = (node.decorator_list[0].lineno if node.decorator_list else node.lineno) - 1
        segment = "".join(lines[start : node.end_lineno])
        sign = ast.dump(node, annotate_fields=True, include_attributes=False)
        out[node.name] = {
            "lineno": node.lineno,
            "end_lineno": node.end_lineno,
            "source_sha256": hashlib.sha256(segment.encode("utf-8")).hexdigest(),
            "ast_sha256": hashlib.sha256(sign.encode("utf-8")).hexdigest(),
            "segment_lines": segment.count("\n"),
            "decorators": len(node.decorator_list),
            "arg_names": [arg.arg for arg in node.args.args],
        }
    return out


before = inventory(SNAPSHOT)
after = inventory(CURRENT)
missing = sorted(set(before) - set(after))
changed = sorted(
    name
    for name in set(before) & set(after)
    if before[name]["source_sha256"] != after[name]["source_sha256"]
    or before[name]["ast_sha256"] != after[name]["ast_sha256"]
)
added = sorted(set(after) - set(before))

inventory_dir = HERE / "inventory"
inventory_dir.mkdir(parents=True, exist_ok=True)
(inventory_dir / "test-functions-before.json").write_text(
    json.dumps(before, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
    newline="\n",
)
(inventory_dir / "test-functions-after.json").write_text(
    json.dumps(after, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
    encoding="utf-8",
    newline="\n",
)
result = {
    "before_functions": len(before),
    "after_functions": len(after),
    "missing": missing,
    "changed": changed,
    "added": added,
    "preserved_exactly": not missing and not changed,
}
(inventory_dir / "ast-preservation.json").write_text(
    json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
)
print(json.dumps(result, ensure_ascii=False, indent=2))
raise SystemExit(0 if result["preserved_exactly"] else 1)
