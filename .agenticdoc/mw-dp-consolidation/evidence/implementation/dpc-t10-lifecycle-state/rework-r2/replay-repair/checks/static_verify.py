"""Pure AST/text verification of the R2 replay repair (no product import).

Scope of the assertions (all static, all read-only):

* the three products still parse, keep every pre-existing module-level name, and
  only the intended definitions changed (the rest is byte-equal within the AST);
* ``decision_wire.append_event`` answers a recorded ``event_id`` (the in-lock
  dedupe scan) *before* running the caller's ``guard``, and still guards every
  append that is really about to happen;
* ``decision_lifecycle`` keeps the S5 non-decreasing floor: the same comparison
  (creation before + every recorded ``task_after``) is still applied inside the
  append lock, and the fail-fast precheck stands aside only for an
  ``event_id`` this ledger already recorded (a replay);
* the replay short-circuit is by ``event_id`` only - no content equality, no
  global ``decision_id`` uniqueness, no single-terminal rule was added;
* the run did not import a product / test module / pytest (checked at exit).

Usage:
  python -B <this file> <worktree-dir> <baseline-copy-dir>

Prints one JSON document on stdout; exit code 1 when ``problems`` is non-empty.
"""

from __future__ import annotations

import ast
import hashlib
import json
import pathlib
import sys

PRODUCTS = ("decision_wire.py", "decision_lifecycle.py", "decision_task_state.py")

#: Definitions this repair is allowed to change (module docstrings aside).
ALLOWED_CHANGED = {
    "decision_wire.py": {"append_event"},
    "decision_lifecycle.py": {"_recorded_after_floor", "record_lifecycle"},
    "decision_task_state.py": set(),
}
ALLOWED_NEW = {
    "decision_wire.py": set(),
    "decision_lifecycle.py": {"_event_is_recorded", "_refuse_preceding_after"},
    "decision_task_state.py": set(),
}

PROTECTED_TESTS = {
    "test_decision_context_lifecycle.py": "1bca28c56c7ab039de5c3a91638fd20c1e2fa89f4a1ec996169cfd933c1e6ae9",
    "test_decision_task_state.py": "30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f",
}
DECLARED_BEFORE = {
    "decision_wire.py": "429201ace7028968ae18cfbcc33dbf5aa0d2fa11b8f5d2dd7604cae0dec4e7dc",
    "decision_lifecycle.py": "73d0ae2efda3879668b3cf84d11f32809c6d00f76da13c3b8d065f87d4c87bb5",
    "decision_task_state.py": "b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d",
}
FORBIDDEN_IMPORTS = {"decision_lifecycle", "decision_wire", "decision_task_state", "decision", "decision_points", "pytest"}


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def definitions(tree: ast.Module) -> dict[str, ast.AST]:
    """Top-level definitions (functions/classes/assignments) by name."""
    found: dict[str, ast.AST] = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            found[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    found[target.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            found[node.target.id] = node
    return found


def function_source(tree: ast.Module, name: str) -> str:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            return ast.unparse(node)
    return ""


def function_node(tree: ast.Module, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    return None


def binds_recorded_floor_as_guard(tree: ast.Module, name: str) -> bool:
    """True when ``name`` still passes ``_recorded_after_floor`` as ``_append``'s guard."""
    node = function_node(tree, name)
    if node is None:
        return False
    for call in ast.walk(node):
        if not isinstance(call, ast.Call):
            continue
        if not (isinstance(call.func, ast.Name) and call.func.id == "_append"):
            continue
        for keyword in call.keywords:
            if keyword.arg != "guard":
                continue
            value = keyword.value
            if not isinstance(value, ast.IfExp):
                continue
            target = value.orelse
            if isinstance(target, ast.Lambda) and "_recorded_after_floor" in ast.unparse(target.body):
                return True
    return False


def module_docstring(tree: ast.Module) -> str:
    return ast.get_docstring(tree) or ""


def _stage_c_expected_new_lifecycle() -> set[str]:
    """The stage-C expectation constant, read from the (unmodified) stage-C file."""
    stage_c = pathlib.Path(__file__).resolve().parents[2] / "verification-preparation" / "static_verify.py"
    if not stage_c.exists():
        return set()
    tree = ast.parse(stage_c.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "EXPECTED_NEW_LIFECYCLE_FUNCTIONS"
            for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            return set(value) if isinstance(value, (set, frozenset, tuple, list)) else set()
    return set()


def main(argv: list[str]) -> int:
    worktree = pathlib.Path(argv[1])
    baseline = pathlib.Path(argv[2])
    problems: list[str] = []
    report: dict[str, object] = {"checker": "static_verify.py", "products": {}}

    parsed: dict[str, ast.Module] = {}
    for name in PRODUCTS:
        current_bytes = (worktree / name).read_bytes()
        base_bytes = (baseline / name).read_bytes()
        try:
            current_tree = ast.parse(current_bytes.decode("utf-8"), filename=name)
            base_tree = ast.parse(base_bytes.decode("utf-8"), filename=name)
        except SyntaxError as exc:  # a product that does not parse is a hard failure
            problems.append(f"{name}: does not parse: {exc.msg} line {exc.lineno}")
            continue
        parsed[name] = current_tree
        if sha(base_bytes) != DECLARED_BEFORE[name]:
            problems.append(f"{name}: baseline copy is not the declared before bytes")
        now_defs = definitions(current_tree)
        was_defs = definitions(base_tree)
        removed = sorted(set(was_defs) - set(now_defs))
        if removed:
            problems.append(f"{name}: removed module-level definition(s) {removed}")
        changed = sorted(
            key for key in set(was_defs) & set(now_defs)
            if ast.unparse(was_defs[key]) != ast.unparse(now_defs[key])
        )
        added = sorted(set(now_defs) - set(was_defs))
        if set(changed) - ALLOWED_CHANGED[name]:
            problems.append(f"{name}: unexpected changed definition(s) {sorted(set(changed) - ALLOWED_CHANGED[name])}")
        if set(added) - ALLOWED_NEW[name]:
            problems.append(f"{name}: unexpected new definition(s) {sorted(set(added) - ALLOWED_NEW[name])}")
        report["products"][name] = {
            "bytes": len(current_bytes),
            "lines": current_bytes.count(b"\n"),
            "before_sha256": sha(base_bytes),
            "after_sha256": sha(current_bytes),
            "changed_definitions": changed,
            "added_definitions": added,
            "removed_definitions": removed,
            "module_docstring_changed": module_docstring(current_tree) != module_docstring(base_tree),
        }

    # -- S5 floor still present, both as precheck and as the in-lock guard ------
    lifecycle_tree = parsed.get("decision_lifecycle.py")
    if lifecycle_tree is not None:
        floor = function_source(lifecycle_tree, "_refuse_preceding_after")
        guard = function_source(lifecycle_tree, "_recorded_after_floor")
        replay = function_source(lifecycle_tree, "_event_is_recorded")
        writer = function_source(lifecycle_tree, "record_lifecycle")
        checks = {
            "floor_compares_creation_before": "validate_observation_order(stored_before, task_after)" in floor,
            "floor_compares_every_prior_after": floor.count("validate_observation_order(prior, task_after)") == 1,
            "floor_validates_prior_snapshot": "validate_task_state(row.get('task_after'))" in floor,
            "floor_skips_other_logical_ids": "row.get('logical_id') != meta.logical_id" in floor,
            "floor_raises_input_error": "raise LifecycleInputError(str(exc))" in floor,
            "guard_reads_ledger_in_lock": "_ledger_facts(store, meta)" in guard
            and "_refuse_preceding_after(start, events, meta, task_after)" in guard,
            "replay_is_event_id_only": "_event_id_of(row) == event_id" in replay
            and "same_snapshot" not in replay
            and "content" not in replay,
            "precheck_skips_only_recorded_event": "_event_is_recorded(events, event_id)" in writer
            and "_refuse_preceding_after(start, events, meta, task_after)" in writer,
            "guard_still_bound_at_append": binds_recorded_floor_as_guard(lifecycle_tree, "record_lifecycle"),
        }
        for label, ok in checks.items():
            if not ok:
                problems.append(f"decision_lifecycle.py: {label}")
        report["lifecycle_order_checks"] = checks

    # -- wire: dedupe before guard, both still inside the append lock ----------
    wire_tree = parsed.get("decision_wire.py")
    if wire_tree is not None:
        append = function_source(wire_tree, "append_event")
        dedupe_at = append.find("if dedupe_event_id:")
        guard_at = append.find("if guard is not None:")
        append_at = append.find("_terminate_dangling_tail(sink)")
        dedupe_hit = append.find("_event_id_present(sink, event_id)")
        duplicate_at = append.find("status='duplicate'")
        checks = {
            "dedupe_branch_before_guard": -1 < dedupe_at < guard_at,
            "guard_before_the_real_append": -1 < guard_at < append_at,
            "dedupe_scan_is_the_in_lock_one": -1 < dedupe_at < dedupe_hit < duplicate_at,
            "duplicate_returns_before_guard": -1 < duplicate_at < guard_at,
            "append_still_opens_the_locked_sink": "os.O_WRONLY | os.O_CREAT | os.O_APPEND" in append,
            "append_releases_the_lock": "mw_common.release_lock(lock)" in append,
            "no_second_lock_added": append.count("mw_common.acquire_lock(") == 1,
        }
        for label, ok in checks.items():
            if not ok:
                problems.append(f"decision_wire.py: {label}")
        report["wire_order_checks"] = checks
        report["wire_helpers_kept"] = {
            "dedupe_scan_defined": "_event_id_present" in definitions(wire_tree),
            "recorded_task_state_defined": "recorded_task_state" in definitions(wire_tree),
            "append_uses_the_scope_sink": "sink = scope.sink" in append,
        }

    # -- the stage-C preparation-time static oracle has pinned facts this round
    # -- necessarily supersedes (informational: it is not an acceptance oracle).
    if lifecycle_tree is not None and wire_tree is not None:
        wire_text = (worktree / "decision_wire.py").read_text(encoding="utf-8")
        lifecycle_text = (worktree / "decision_lifecycle.py").read_text(encoding="utf-8")
        stage_c_expected = _stage_c_expected_new_lifecycle()
        before_names = set(definitions(ast.parse((baseline / "decision_lifecycle.py").read_text(encoding="utf-8"))))
        now_names = set(definitions(lifecycle_tree))
        report["stage_c_pinned_expectations_now_superseded"] = {
            "wire_guard_slot_before_dedupe": wire_text.find("if guard is not None:")
            < wire_text.find("if dedupe_event_id:"),
            "lifecycle_floor_precheck_before_append": -1
            < lifecycle_text.find("_recorded_after_floor(store, meta, task_after)")
            < lifecycle_text.find("guard=None if task_after is None else lambda: _recorded_after_floor"),
            "product_matches_delivered_after": {
                name: sha((worktree / name).read_bytes()) == sha((baseline / name).read_bytes())
                for name in PRODUCTS
            },
            "new_lifecycle_helpers_not_in_stage_c_expectation": sorted(
                (now_names - before_names) - set(stage_c_expected)
            ),
            "note": (
                "each False/extra above is the intended state: stage C pinned the "
                "stage-B bytes, the guard-before-dedupe order and its own helper set; "
                "its 16 behavioural boundary items, not this preparation-time "
                "checker, are the acceptance oracle for this round"
            ),
        }

    # -- protected suites unchanged -------------------------------------------
    tests = {}
    for name, expected in PROTECTED_TESTS.items():
        got = sha((worktree / name).read_bytes())
        tests[name] = {"sha256": got, "equal_to_protected": got == expected}
        if got != expected:
            problems.append(f"{name}: sha {got} != protected {expected}")
    report["protected_tests"] = tests

    # -- no product import happened in this process ---------------------------
    report["forbidden_modules_imported"] = sorted(FORBIDDEN_IMPORTS & set(sys.modules))
    if report["forbidden_modules_imported"]:
        problems.append(f"checker imported forbidden module(s) {report['forbidden_modules_imported']}")

    report["problems"] = problems
    print(json.dumps(report, indent=2, sort_keys=True, ensure_ascii=False))
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
