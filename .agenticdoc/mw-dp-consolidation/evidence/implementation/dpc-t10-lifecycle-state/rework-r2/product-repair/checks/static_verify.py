"""Pure AST/text verification for the T10 R2 stage-B product repair.

Read-only: parses source text with ``ast`` (no import, no exec, no product
import), hashes bytes, and prints one JSON report to stdout. It never writes.

Run: python -B static_verify.py <product_dir> <before_dir> <evidence_root>
"""
from __future__ import annotations

import ast
import hashlib
import json
import sys
from pathlib import Path

PRODUCTS = ("decision_wire.py", "decision_lifecycle.py", "decision_task_state.py")
TESTS = ("test_decision_context_lifecycle.py", "test_decision_task_state.py")
#: Protected test digests from the PM's red disposition check.json.
EXPECTED_TESTS = {
    "test_decision_context_lifecycle.py": "1bca28c56c7ab039de5c3a91638fd20c1e2fa89f4a1ec996169cfd933c1e6ae9",
    "test_decision_task_state.py": "30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f",
}
#: Protected product digests (the PM red run's expected before state).
EXPECTED_BEFORE = {
    "decision_wire.py": "8863e534f0a74edec1fc0105c0619c9dd19c85a472b82db6d622c23a7f85a5e6",
    "decision_lifecycle.py": "0c0f7fffb353cc829e054dfbeec409915cb4bebce11d998c5d810feb533dc8e4",
    "decision_task_state.py": "b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d",
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _top_names(tree: ast.Module) -> list[str]:
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names


def _function_count(tree: ast.Module) -> int:
    return sum(
        1
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    )


def _imports(tree: ast.Module) -> list[str]:
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                found.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            found.add(node.module)
    return sorted(found)


def _read(path: Path) -> bytes:
    return path.read_bytes()


def main() -> int:
    product_dir = Path(sys.argv[1])
    before_dir = Path(sys.argv[2])
    report: dict[str, object] = {"files": {}, "checks": {}, "problems": []}
    checks: dict[str, object] = {}
    problems: list[str] = []

    def fail(name: str, detail: str) -> None:
        problems.append(f"{name}: {detail}")

    # -- products: protected before, current after, pure syntax/AST ----------
    for name in PRODUCTS:
        before_raw = _read(before_dir / name)
        after_raw = _read(product_dir / name)
        before_text = before_raw.decode("utf-8")
        after_text = after_raw.decode("utf-8")
        before_tree = ast.parse(before_text, filename=f"before/{name}")
        after_tree = ast.parse(after_text, filename=f"after/{name}")
        before_names = _top_names(before_tree)
        after_names = _top_names(after_tree)
        removed = [item for item in before_names if item not in after_names]
        added = [item for item in after_names if item not in before_names]
        if removed:
            fail(name, f"top-level definition(s) removed: {removed}")
        before_imports = _imports(before_tree)
        after_imports = _imports(after_tree)
        if before_imports != after_imports:
            fail(name, f"import set changed: before={before_imports} after={after_imports}")
        if _sha(before_raw) != EXPECTED_BEFORE[name]:
            fail(name, "before bytes do not match the PM-protected digest")
        report["files"][name] = {
            "before_sha256": _sha(before_raw),
            "before_bytes": len(before_raw),
            "before_lines": before_text.count("\n"),
            "after_sha256": _sha(after_raw),
            "after_bytes": len(after_raw),
            "after_lines": after_text.count("\n"),
            "after_eol": "CRLF" if b"\r\n" in after_raw else "LF",
            "after_final_newline": after_raw.endswith(b"\n"),
            "syntax_ast_parse": "ok",
            "top_level_added": added,
            "top_level_removed": removed,
            "function_defs_before": _function_count(before_tree),
            "function_defs_after": _function_count(after_tree),
            "imports_before": before_imports,
            "imports_after": after_imports,
        }

    # -- tests: read-only, byte identical to the protected digests ----------
    for name in TESTS:
        raw = _read(product_dir / name)
        digest = _sha(raw)
        ast.parse(raw.decode("utf-8"), filename=f"test/{name}")
        report["files"][name] = {
            "sha256": digest,
            "bytes": len(raw),
            "unchanged_vs_protected": digest == EXPECTED_TESTS[name],
        }
        if digest != EXPECTED_TESTS[name]:
            fail(name, "assigned test file is not byte-identical to the protected digest")

    # -- S1: content-addressed request id, no content pre-read ---------------
    wire_text = (product_dir / "decision_wire.py").read_text(encoding="utf-8")
    life_text = (product_dir / "decision_lifecycle.py").read_text(encoding="utf-8")
    checks["s1_content_addressed_request_id"] = (
        '_stable_event_id("rq", _canonical_json(recorded))' in life_text
        and 'event["event_id"] = event_id' in life_text
        and "key not in (\"event_id\", \"ts\")" in life_text
        and '_stable_event_id(\n            "rq", meta.logical_id' not in life_text
    )
    if not checks["s1_content_addressed_request_id"]:
        fail("S1", "request event id is not content-addressed over the recorded payload")
    checks["s1_dedupe_still_under_append_lock"] = (
        "present = _event_id_present(sink, event_id)" in wire_text
        and "mw_common.acquire_lock(" in wire_text
    )
    if not checks["s1_dedupe_still_under_append_lock"]:
        fail("S1", "the event-id duplicate scan is no longer inside the append lock")

    # -- S3: dynamic entry uses the decision_points single source -------------
    checks["s3_dynamic_single_source"] = (
        "def _dynamic_entry_answer_issues(" in life_text
        and "decision_points.entry_choice_issues(dp_id, choice, material)" in life_text
        and "decision_points.entry_material_issues(" in life_text
        and 'if decision_points.require_active_dp(dp_id).kind != "dynamic-candidates":' in life_text
    )
    if not checks["s3_dynamic_single_source"]:
        fail("S3", "dynamic material/choice validation does not use decision_points")
    checks["s3_no_candidate_syntax_copy"] = not any(
        token in life_text
        for token in ('"handling_options"', "CANDIDATE_ITEM_KEYS", "resolve_entry_choices(")
    )
    if not checks["s3_no_candidate_syntax_copy"]:
        fail("S3", "writer copies candidate syntax/vocabulary instead of calling decision_points")

    def _has_call(text: str, func: str) -> bool:
        return f"{func}(" in text

    # -- S5: non-decreasing after floor + lock-scoped guard -------------------
    checks["s5_recorded_after_floor"] = (
        "def _recorded_after_floor(" in life_text
        and 'row.get("task_after")' in life_text
        and "decision_task_state.validate_observation_order(prior, task_after)" in life_text
    )
    if not checks["s5_recorded_after_floor"]:
        fail("S5", "executed/settled do not compare against previously recorded after snapshots")
    checks["s5_guard_inside_append_lock"] = (
        "guard: Callable[[], None] | None = None" in wire_text
        and "if guard is not None:" in wire_text
        and "guard=None if task_after is None else lambda: _recorded_after_floor(" in life_text
        and "except LifecycleInputError:" in life_text
    )
    if not checks["s5_guard_inside_append_lock"]:
        fail("S5", "the after-order precondition is not re-checked inside the append lock")

    # -- S7: recorded representation equality, not raw-vs-masked ------------
    checks["s7_recorded_before_representation"] = (
        "def recorded_task_state(" in wire_text
        and "recorded = decision_wire.recorded_task_state(store._scope(), given)" in life_text
        and "same_snapshot(stored, recorded)" in life_text
    )
    if not checks["s7_recorded_before_representation"]:
        fail("S7", "before equality does not run on the recorded representation")
    checks["s7_before_refusal_kept"] = (
        "a later before cannot be backfilled" in life_text
        and "same_snapshot" in (product_dir / "decision_task_state.py").read_text(encoding="utf-8")
    )
    if not checks["s7_before_refusal_kept"]:
        fail("S7", "the backfill refusal was removed")

    # -- S4: platform path identity for the .agenticdoc component -----------
    checks["s4_case_insensitive_component"] = (
        "_CASE_INSENSITIVE_PATHS = os.name == \"nt\"" in wire_text
        and "def _same_path_component(" in wire_text
        and "os.path.normcase(part) == os.path.normcase(name)" in wire_text
        and 'any(_same_path_component(part, ".agenticdoc") for part in path.parts)' in wire_text
    )
    if not checks["s4_case_insensitive_component"]:
        fail("S4", "the .agenticdoc component check is not platform-aware")
    checks["s4_production_rule_intact"] = (
        "_is_production_ledger(candidate) or _is_inside_agenticdoc(candidate)" in wire_text
        and "_PRODUCTION_SINK_PARTS = (\".agenticdoc\", \"_autopilot\", \"decisions-wire.jsonl\")" in wire_text
        and "_PRODUCTION_LIFECYCLE_PARTS = (\".agenticdoc\", \"_autopilot\", \"decision-lifecycle.jsonl\")" in wire_text
    )
    if not checks["s4_production_rule_intact"]:
        fail("S4", "the production-path refusal rule was relaxed")
    checks["s4_no_live_path_probe"] = (
        ".agenticdoc" in wire_text and "getshortpathname" not in wire_text.lower()
    )
    if not checks["s4_no_live_path_probe"]:
        fail("S4", "unexpected 8.3/live-path probe added")

    # -- no unapproved semantics (S2/S6/S8) --------------------------------
    checks["no_global_decision_id_uniqueness"] = (
        "unique decision_id" not in life_text and "global unique" not in life_text.lower()
    )
    if not checks["no_global_decision_id_uniqueness"]:
        fail("scope", "an unapproved global decision_id uniqueness rule was added")
    checks["no_task_state_change"] = _sha(_read(product_dir / "decision_task_state.py")) == EXPECTED_BEFORE[
        "decision_task_state.py"
    ]
    if not checks["no_task_state_change"]:
        fail("scope", "decision_task_state.py changed although no S-item needs it")

    # -- retained controls --------------------------------------------------
    checks["control_executed_action_vocabulary"] = 'EXECUTED_ACTIONS = (' in life_text
    checks["control_outcome_vocabulary"] = 'OUTCOMES = ("pending", "ok", "rework", "rollback", "inconclusive")' in life_text
    checks["control_secret_guard_kept"] = (
        "def _guard_secret(" in life_text and "matches a known secret; the value is withheld" in life_text
    )
    checks["control_redactor_required"] = 'inject the caller\'s known-secret redactor' in life_text
    checks["control_orphan_action_label_kept"] = "def _is_inside_agenticdoc" in wire_text
    for key, ok in checks.items():
        if key.startswith("control_") and not ok:
            fail(key, "retained control is missing")

    # -- ordering/structural checks (source order is execution order) ------
    def _section(text: str, start: str, end: str) -> str:
        a = text.find(start)
        b = text.find(end, a + 1) if a >= 0 else -1
        if a < 0 or b < 0:
            return ""
        return text[a:b]

    def _between(text: str, first: str, second: str, third: str) -> bool:
        a = text.find(first)
        b = text.find(second)
        c = text.find(third)
        return -1 < a < b < c

    request_section = _section(life_text, "def record_request(", "\ndef record_terminal(")
    lifecycle_section = _section(life_text, "def record_lifecycle(", "\ndef record_consumed(")
    append_section = _section(wire_text, "def append_event(", "\ndef record_event(")
    before_section = _section(life_text, "def _check_before(", "\ndef _recorded_after_floor(")

    checks["s3_check_runs_after_preparation_inside_business_branch"] = _between(
        request_section,
        'if fields["business_decisions"] == 1:',
        "_refuse_entry_issues(",
        "elif preparation is not None:",
    )
    if not checks["s3_check_runs_after_preparation_inside_business_branch"]:
        fail("S3", "the dynamic answer check is not in the business-decision branch")
    checks["s5_floor_before_append_and_guard_inside_lock"] = (
        _between(
            lifecycle_section,
            "if task_after is not None:",
            "_recorded_after_floor(store, meta, task_after)",
            "actor = _check_actor(actor)",
        )
        and _between(append_section, "if guard is not None:", "guard()", "if dedupe_event_id:")
    )
    if not checks["s5_floor_before_append_and_guard_inside_lock"]:
        fail("S5", "the after-order floor/guard is not ordered before the append")
    checks["s7_same_sanitizer_on_both_sides"] = (
        "value = recorded_task_state(scope, value)" in wire_text
        and _between(
            before_section,
            "recorded = decision_wire.recorded_task_state",
            "same_snapshot(stored, recorded)",
            "return given",
        )
    )
    if not checks["s7_same_sanitizer_on_both_sides"]:
        fail("S7", "before equality does not use the same recorded representation as the store")
    checks["s1_id_covers_the_recorded_row"] = _between(
        request_section,
        "event = decision_wire.request_event(scope, event_id=event_id, **payload)",
        "recorded = {",
        "event[\"event_id\"] = event_id",
    )
    if not checks["s1_id_covers_the_recorded_row"]:
        fail("S1", "the content id is not derived from the built row before the append")

    report["checks"] = checks
    report["problems"] = problems
    report["ok"] = not problems
    sys.stdout.write(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    return 0 if not problems else 1


if __name__ == "__main__":
    raise SystemExit(main())
