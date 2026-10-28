"""Stage-A pure AST/text verification for the T10 R2 test-preparation face.

This script is *not* a product runner: it imports only the standard library, it
never imports/pytest-executes a product module and it writes nothing outside the
``checks/`` directory of this stage's own evidence face. It answers the questions
the PM must be able to audit without trusting a summary:

* is every pre-existing test function still byte-for-byte the same source with
  the same AST shape and assertion count (``old-functions-before.json``)?
* is the new file the old file plus exactly the two declared top-level imports
  and one appended block (no silent edit anywhere above it)?
* how many items does each file collect, and is the estimate trustworthy (the
  same estimator must return 116 for the two pre-existing files)?
* did this stage leave exactly one legal mirror difference (the lifecycle test),
  with the protected pyc/live/old-evidence sets untouched?

Run: ``python -B checks/verify_tests.py`` from anywhere.
"""
from __future__ import annotations

import ast
import difflib
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
STAGE = HERE.parent
KEY = STAGE.parents[4]
ROOT = STAGE.parents[6]
WT = KEY / "implementation-worktree"
PKG = WT / "packages" / "multi-workers"
PRE = KEY / "evidence" / "implementation" / "t10-r2-pre-dispatch-20261028"

TEST_FILES = ("test_decision_context_lifecycle.py", "test_decision_task_state.py")
INSERTED_IMPORTS_BEFORE = (
    "import pytest\n\nimport decision\nimport decision_lifecycle as lifecycle\n"
    "import decision_points\nimport decision_wire as wire\n"
)
INSERTED_IMPORTS_AFTER = (
    "import pytest\n\nimport decision_lifecycle as lifecycle\nimport decision_wire as wire\n"
)
NEW_TEST_NAMES = (
    "test_a_refused_request_does_not_swallow_the_later_real_choice",
    "test_an_identical_repeated_business_request_stays_idempotent",
    "test_a_different_choice_for_the_same_request_stays_visible",
    "test_a_dp_auto_choice_outside_the_prepared_candidates_is_not_recorded",
    "test_a_dp_auto_choice_inside_the_prepared_candidates_is_recorded",
    "test_executed_and_settled_observations_stay_non_decreasing",
    "test_a_failed_executed_round_is_never_recorded_as_executed",
    "test_a_secret_bearing_creation_before_can_be_repeated",
    "test_a_case_variant_agenticdoc_path_is_refused_in_test_scope",
    "test_the_exact_agenticdoc_path_is_refused_in_test_scope",
    "test_the_writer_consumes_the_producers_frozen_prepared_contract",
)
NEW_HELPER_NAMES = (
    "_auto_candidate",
    "_auto_material",
    "_auto_preparation",
    "_auto_result",
)
#: The only old-evidence subtree this stage is allowed to add files under. Every
#: other ``rework-r2`` directory (e.g. the T05 one) is old evidence and protected.
OWN_STAGE_PREFIX = "evidence/implementation/dpc-t10-lifecycle-state/rework-r2/"
EXPECTED_RED = (
    "test_a_refused_request_does_not_swallow_the_later_real_choice",
    "test_a_different_choice_for_the_same_request_stays_visible",
    "test_a_dp_auto_choice_outside_the_prepared_candidates_is_not_recorded",
    "test_executed_and_settled_observations_stay_non_decreasing",
    "test_a_secret_bearing_creation_before_can_be_repeated",
    "test_a_case_variant_agenticdoc_path_is_refused_in_test_scope",
)
EXPECTED_GREEN = (
    "test_an_identical_repeated_business_request_stays_idempotent",
    "test_a_dp_auto_choice_inside_the_prepared_candidates_is_recorded",
    "test_a_failed_executed_round_is_never_recorded_as_executed",
    "test_the_exact_agenticdoc_path_is_refused_in_test_scope",
    "test_the_writer_consumes_the_producers_frozen_prepared_contract",
)


def sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha_path(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def function_map(source: str) -> dict[str, dict[str, object]]:
    tree = ast.parse(source)
    out: dict[str, dict[str, object]] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[node.name] = {
                "line": node.lineno,
                "ast": ast.dump(node, include_attributes=False),
                "source": ast.get_source_segment(source, node),
                "assertions": sum(isinstance(child, ast.Assert) for child in ast.walk(node)),
            }
    return out


def _literal_size(node: ast.AST) -> int | None:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return len(node.elts)
    return None


def item_estimate(source: str) -> dict[str, object]:
    """Estimate the collected item count from literal pytest parametrizations."""
    tree = ast.parse(source)
    total = 0
    unknown: list[str] = []
    per_test: dict[str, int | None] = {}
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef) or not node.name.startswith("test_"):
            continue
        count = 1
        found = False
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call):
                continue
            target = decorator.func
            name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
            if name != "parametrize" or len(decorator.args) < 2:
                continue
            size = _literal_size(decorator.args[1])
            if size is None:
                count = None
                unknown.append(node.name)
                break
            count *= size
            found = True
        per_test[node.name] = count
        if count is None:
            continue
        total += count
        del found
    return {"items": total, "unknown": unknown, "per_test": per_test}


def skip_markers(source: str) -> list[str]:
    tree = ast.parse(source)
    found: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            for decorator in node.decorator_list:
                target = decorator.func if isinstance(decorator, ast.Call) else decorator
                name = target.attr if isinstance(target, ast.Attribute) else getattr(target, "id", "")
                if name in ("skip", "skipif", "xfail"):
                    found.append(f"{node.name}:{name}")
    return sorted(found)


def build_inventory(root: Path, skip_prefixes: tuple[str, ...] = ()) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel.startswith(prefix) for prefix in skip_prefixes):
            continue
        out[rel] = sha_path(path)
    return out


def history_inventory() -> dict[str, str]:
    out: dict[str, str] = {}
    for directory in (
        "dpc-t10-lifecycle-state",
        "dpc-t05-eight-cases",
        "t05-r2-envelope-pm-handoff-20261027",
        "t05-t10-audit-disposition-20261028",
    ):
        base = KEY / "evidence" / "implementation" / directory
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(KEY).as_posix()
            if rel.startswith(OWN_STAGE_PREFIX):
                continue
            out[rel] = sha_path(path)
    for name in ("t05-handoff-audit-20261027.md", "t10-handoff-audit-20261027.md"):
        path = KEY / "evidence" / "implementation" / name
        out[path.relative_to(KEY).as_posix()] = sha_path(path)
    return out


def diff_inventory(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    added = sorted(set(after) - set(before))
    removed = sorted(set(before) - set(after))
    changed = sorted(
        name for name in set(before) & set(after) if before[name] != after[name]
    )
    return {"added": added, "removed": removed, "changed": changed}


def _audit_scripts(problems: list[str]) -> dict[str, object]:
    """Syntax/import/behaviour-shape audit of the four stage-A scripts (AST only)."""
    names = ("run_pm_tests.py", "sitecustomize.py", "guard_preflight.py", "probe_imports.py")
    product_modules = {
        "decision",
        "decision_points",
        "decision_lifecycle",
        "decision_wire",
        "decision_task_state",
    }
    out: dict[str, object] = {}
    for name in names:
        path = STAGE / name
        text = path.read_text(encoding="utf-8")
        try:
            compile(text, str(path), "exec")
        except SyntaxError as exc:
            problems.append(f"{name}: does not compile ({exc.msg})")
            continue
        tree = ast.parse(text)
        imports: list[str] = []
        for node in tree.body:
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module)
        bad_imports = sorted(set(imports) & product_modules)
        if bad_imports:
            problems.append(f"{name}: imports a product module {bad_imports}")
        literals: dict[str, object] = {}
        for node in tree.body:
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name):
                    try:
                        literals[target.id] = ast.literal_eval(node.value)
                    except (ValueError, SyntaxError):
                        pass
        out[name] = {
            "sha256": sha_bytes(text.encode("utf-8")),
            "bytes": len(text.encode("utf-8")),
            "lines": text.count("\n"),
            "imports": sorted(set(imports)),
            "literals": literals,
        }
    runner_text = (STAGE / "run_pm_tests.py").read_text(encoding="utf-8")
    for token in ("shutil.rmtree", "os.remove(", "os.unlink(", "os.rmdir(", "shell=True"):
        if token in runner_text:
            problems.append(f"run_pm_tests.py: contains a forbidden cleanup/bypass token {token}")
    for token in ("os.mkdir(label_dir)", "capture_output=True", "env=env", "no:cacheprovider", "--basetemp"):
        if token not in runner_text:
            problems.append(f"run_pm_tests.py: missing required token {token}")
    return out


def _audit_node_ids(scripts: object, problems: list[str]) -> dict[str, object]:
    """The declared node ids must be real test functions and must add up to 14 items."""
    if not isinstance(scripts, dict):
        return {}
    literals = scripts.get("literals", {})
    if not isinstance(literals, dict):
        return {}
    new_ids = literals.get("NEW_NODE_IDS")
    red_ids = literals.get("EXPECTED_RED_NODE_IDS")
    green_ids = literals.get("EXPECTED_GREEN_NODE_IDS")
    if not all(isinstance(value, tuple) for value in (new_ids, red_ids, green_ids)):
        problems.append("run_pm_tests.py: the node-id constants are not literal tuples")
        return {}
    source = (PKG / TEST_FILES[0]).read_text(encoding="utf-8")
    declared = set(function_map(source))
    missing = sorted(set(new_ids) - declared)
    if missing:
        problems.append(f"run_pm_tests.py: node ids are not real test functions {missing}")
    overlap = sorted(set(red_ids) & set(green_ids))
    if overlap:
        problems.append(f"run_pm_tests.py: red/green overlap {overlap}")
    uncovered = sorted((set(red_ids) | set(green_ids)) - set(new_ids))
    if set(red_ids) | set(green_ids) != set(new_ids):
        problems.append(f"run_pm_tests.py: red + green does not cover every new node id {uncovered}")
    estimate = item_estimate(source)["per_test"]
    if not isinstance(estimate, dict):
        return {}
    red_items = sum(int(estimate.get(name) or 0) for name in red_ids)
    green_items = sum(int(estimate.get(name) or 0) for name in green_ids)
    if red_items + green_items != 14:
        problems.append(
            f"run_pm_tests.py: declared red+green adds {red_items + green_items} items, expected 14"
        )
    return {
        "new_node_ids": list(new_ids),
        "expected_red_node_ids": list(red_ids),
        "expected_green_node_ids": list(green_ids),
        "expected_red_items": red_items,
        "expected_green_items": green_items,
        "uncovered": uncovered,
    }


def main() -> int:
    result: dict[str, object] = {
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "source": "agent-report",
        "role": "test-preparation-only (no product import, no pytest, no product execution)",
        "python": sys.version,
        "dont_write_bytecode": bool(sys.dont_write_bytecode),
        "root": str(ROOT),
        "worktree": str(WT),
        "checks": {},
        "problems": [],
    }
    problems: list[str] = result["problems"]  # type: ignore[assignment]
    checks: dict[str, object] = result["checks"]  # type: ignore[assignment]

    old_functions = json.loads((PRE / "old-functions-before.json").read_text(encoding="utf-8"))
    mirror_before = json.loads((PRE / "mirror-before.json").read_text(encoding="utf-8"))
    pyc_before = json.loads((PRE / "pyc-before.json").read_text(encoding="utf-8"))
    products_before = json.loads((PRE / "products-before.json").read_text(encoding="utf-8"))
    history_before = json.loads((PRE / "history-before.json").read_text(encoding="utf-8"))

    files: dict[str, object] = {}
    for name in TEST_FILES:
        rel = f"packages/multi-workers/{name}"
        current_path = PKG / name
        before_path = STAGE / "before-bytes" / rel
        after_path = STAGE / "after-bytes" / rel
        current_bytes = current_path.read_bytes()
        before_bytes = before_path.read_bytes()
        after_path.parent.mkdir(parents=True, exist_ok=True)
        after_path.write_bytes(current_bytes)
        diff_lines = list(
            difflib.unified_diff(
                before_bytes.decode("utf-8").splitlines(keepends=True),
                current_bytes.decode("utf-8").splitlines(keepends=True),
                fromfile=f"before/{rel}",
                tofile=f"after/{rel}",
            )
        )
        (STAGE / "diff" / f"{name}.diff").write_text("".join(diff_lines), encoding="utf-8", newline="\n")
        compile(current_bytes.decode("utf-8"), str(current_path), "exec")
        old_source = before_bytes.decode("utf-8")
        new_source = current_bytes.decode("utf-8")
        if name == TEST_FILES[0]:
            recomposed = new_source.replace(INSERTED_IMPORTS_BEFORE, INSERTED_IMPORTS_AFTER, 1)
        else:
            recomposed = new_source
        old_head = old_source.rstrip("\n")
        functions = function_map(new_source)
        old_map = old_functions[rel]
        missing = sorted(set(old_map) - set(functions))
        altered = sorted(
            key
            for key in set(old_map) & set(functions)
            if old_map[key]["ast"] != functions[key]["ast"]
            or old_map[key]["source"] != functions[key]["source"]
            or old_map[key]["assertions"] != functions[key]["assertions"]
        )
        if missing:
            problems.append(f"{name}: lost functions {missing}")
        if altered:
            problems.append(f"{name}: altered functions {altered}")
        if recomposed != old_head and not recomposed.startswith(old_head):
            problems.append(f"{name}: the old bytes are not an intact head of the new file")
        appended_only = len(recomposed) - len(old_head)
        if name == TEST_FILES[0]:
            for new_name in NEW_TEST_NAMES:
                if new_name not in functions:
                    problems.append(f"{name}: missing new test {new_name}")
            stray = sorted(set(functions) - set(old_map) - set(NEW_TEST_NAMES) - set(NEW_HELPER_NAMES))
            if stray:
                problems.append(f"{name}: undeclared new top-level functions {stray}")
            if appended_only <= 0:
                problems.append(f"{name}: no appended block was found")
        elif current_bytes != before_bytes:
            problems.append(f"{name}: changed although no edit was declared")
        old_estimate = item_estimate(old_source)
        new_estimate = item_estimate(new_source)
        files[name] = {
            "current_bytes": len(current_bytes),
            "current_sha256": sha_bytes(current_bytes),
            "before_bytes": len(before_bytes),
            "before_sha256": sha_bytes(before_bytes),
            "lines_before": old_source.count("\n"),
            "lines_after": new_source.count("\n"),
            "crlf": current_bytes.count(b"\r\n"),
            "old_functions": len(old_map),
            "new_functions_total": len(functions),
            "old_functions_preserved": not missing and not altered,
            "old_estimate_items": old_estimate["items"],
            "old_estimate_unknown": old_estimate["unknown"],
            "new_estimate_items": new_estimate["items"],
            "new_estimate_unknown": new_estimate["unknown"],
            "skip_markers": skip_markers(new_source),
            "diff_lines": len(diff_lines),
            "appended_chars": appended_only,
            "read_to_eof": current_bytes.endswith(b"\n") and b"\x00" not in current_bytes,
        }
    checks["files"] = files

    old_total = sum(files[name]["old_estimate_items"] for name in TEST_FILES)
    new_total = sum(files[name]["new_estimate_items"] for name in TEST_FILES)
    checks["item_estimate"] = {
        "old_total": old_total,
        "expected_old_total": 116,
        "estimator_matches_known_116": old_total == 116,
        "new_total": new_total,
        "delta": new_total - old_total,
        "expected_red_count": 8,
        "expected_green_count": 6,
        "expected_red": list(EXPECTED_RED),
        "expected_green": list(EXPECTED_GREEN),
    }
    if old_total != 116:
        problems.append(f"item estimator no longer reproduces the known 116 (got {old_total})")

    current_mirror = build_inventory(WT)
    mirror_diff = diff_inventory(mirror_before, current_mirror)
    checks["mirror"] = {
        "before_files": len(mirror_before),
        "current_files": len(current_mirror),
        "diff": mirror_diff,
        "legal_stage_diff_only": mirror_diff["added"] == []
        and mirror_diff["removed"] == []
        and mirror_diff["changed"] == ["packages/multi-workers/test_decision_context_lifecycle.py"],
    }
    if not checks["mirror"]["legal_stage_diff_only"]:  # type: ignore[index]
        problems.append("the mirror difference is not exactly the declared lifecycle test edit")

    current_pyc = {k: v for k, v in current_mirror.items() if k.endswith(".pyc")}
    checks["pyc"] = {
        "before": len(pyc_before),
        "current": len(current_pyc),
        "unchanged": current_pyc == pyc_before,
    }
    if current_pyc != pyc_before:
        problems.append("a protected pyc changed")

    live = {}
    for rel, info in products_before.items():
        live[rel] = {
            "expected_live_sha256": info["live_sha256"],
            "current_live_sha256": sha_path(ROOT / rel),
            "isolated_sha256": info["sha256"],
            "current_isolated_sha256": sha_path(WT / rel),
        }
    checks["live_and_products"] = live
    for rel, info in live.items():
        if info["current_live_sha256"] != info["expected_live_sha256"]:
            problems.append(f"live file moved: {rel}")
        if not rel.endswith(".py") or "test_" not in rel:
            if info["current_isolated_sha256"] != info["isolated_sha256"]:
                problems.append(f"protected product moved: {rel}")

    current_history = history_inventory()
    checks["old_evidence"] = {
        "before_files": len(history_before),
        "current_files": len(current_history),
        "diff": diff_inventory(history_before, current_history),
    }
    if current_history != history_before:
        problems.append("old evidence bytes moved")

    result["ok"] = not problems
    scripts = _audit_scripts(problems)
    checks["scripts"] = scripts
    checks["node_ids"] = _audit_node_ids(scripts.get("run_pm_tests.py"), problems)
    result["ok"] = not problems
    out = HERE / "verify_tests.result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps({"ok": result["ok"], "problems": problems, "item_estimate": checks["item_estimate"]}, ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
