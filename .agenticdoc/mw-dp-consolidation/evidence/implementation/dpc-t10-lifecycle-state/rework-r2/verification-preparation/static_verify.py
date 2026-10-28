"""Pure AST/text verifier for the T10 R2 stage-C preparation (no imports).

This checker never imports, executes or collects a product, a test module or a
runner. It only reads bytes, ``ast.parse``s them and compares text/index
positions, which is exactly the authority this worker has: everything it says
about behaviour is a *reading*, not an execution.

What it verifies (and records as evidence):

1. the read-to-EOF audit of the current bytes this stage depends on - three
   products, both assigned suites, the four audited ``pm-controlled`` scripts
   (full read) and the associated single-source surface (declared ranges only,
   never claimed as a full read);
2. that the constants the delivered runner binds are the digests of the bytes
   that are really on disk, including this stage's helper scripts, the extra
   boundary suite and the five protected live files;
3. that the protected counts the runner asserts still hold (1891 mirror files,
   14 ``.pyc``, 744 old-evidence files);
4. the AST facts the extra suite and the runner depend on: the content-addressed
   request id, ``recorded_task_state``, the in-lock ``guard`` slot, the
   ``_recorded_after_floor`` precheck that runs before ``_append`` (the recorded
   root cause of the predicted-red replay item), the unchanged closed
   vocabularies and the unchanged public helper surface;
5. that no unrelated product surface was added or removed: the top-level
   definition sets are compared against the protected ``before-bytes`` copies in
   ``product-repair``;
6. that the current products really are the delivered ``after-bytes`` copies,
   that both assigned suites still equal the stage-A audited digests and that
   every new file is UTF-8/LF with a final newline.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
CHECKS_DIR = HERE / "checks"


def _ancestor(offset: int, marker: str) -> pathlib.Path:
    candidate = HERE.parents[offset]
    if not (candidate / marker).exists():
        raise SystemExit(f"anchor {candidate} does not contain {marker!r}")
    return candidate


EVIDENCE = _ancestor(3, "implementation")
KEY = _ancestor(4, "implementation-worktree")
ROOT = _ancestor(6, "packages")
WORKTREE = KEY / "implementation-worktree"
PACKAGES = WORKTREE / "packages" / "multi-workers"
LIVE = ROOT / "packages" / "multi-workers"
REWORK = HERE.parent
PM_CONTROLLED = REWORK / "pm-controlled"
PRODUCT_REPAIR = REWORK / "product-repair"
TEST_PREPARATION = REWORK / "test-preparation"
OLD_DISPOSITION = KEY / "evidence/implementation/t10-r2-red-disposition-20261028"

PRODUCTS = (
    "decision_wire.py",
    "decision_lifecycle.py",
    "decision_task_state.py",
)
ASSIGNED_TESTS = (
    "test_decision_context_lifecycle.py",
    "test_decision_task_state.py",
)
PM_SCRIPTS = (
    "run_pm_tests.py",
    "sitecustomize.py",
    "guard_preflight.py",
    "probe_imports.py",
)
OWN_SCRIPTS = (
    "run_pm_tests.py",
    "sitecustomize.py",
    "guard_preflight.py",
    "probe_imports.py",
)
OWN_FILES = OWN_SCRIPTS + ("test_t10_r2_boundaries.py", "static_verify.py")

EXPECTED_MIRROR_FILES = 1891
EXPECTED_PYC_FILES = 14
EXPECTED_OLD_EVIDENCE_FILES = 744

OLD_EVIDENCE_DIRS = (
    "dpc-t10-lifecycle-state",
    "dpc-t05-eight-cases",
    "t05-r2-envelope-pm-handoff-20261027",
    "t05-t10-audit-disposition-20261028",
)
OLD_EVIDENCE_FILES = ("t05-handoff-audit-20261027.md", "t10-handoff-audit-20261027.md")
OWN_STAGE_PREFIX = "evidence/implementation/dpc-t10-lifecycle-state/rework-r2/"

#: Ranges actually read in files that were *not* read to EOF. They are declared
#: so that no reader mistakes a surface read for a full read.
SURFACE_READS = {
    "decision_points.py": (
        (1340, 1400),
        (2085, 2115),
        (3230, 3310),
        (3820, 4340),
    ),
    "decision.py": ((140, 210),),
    "mw_common.py": ((None, None),),  # acquire_lock/release_lock read at their definition
}

PRE_REPAIR_RED_NODE_IDS = (
    "test_a_refused_request_does_not_swallow_the_later_real_choice",
    "test_a_different_choice_for_the_same_request_stays_visible",
    "test_a_dp_auto_choice_outside_the_prepared_candidates_is_not_recorded",
    "test_executed_and_settled_observations_stay_non_decreasing",
    "test_a_secret_bearing_creation_before_can_be_repeated",
    "test_a_case_variant_agenticdoc_path_is_refused_in_test_scope",
)
EXPECTED_NEW_WIRE_FUNCTIONS = {"_same_path_component", "recorded_task_state"}
EXPECTED_NEW_LIFECYCLE_FUNCTIONS = {
    "_recorded_after_floor",
    "_canonical_json",
    "_dynamic_entry_answer_issues",
    "_refuse_entry_issues",
}


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _audit_file(path: pathlib.Path, *, read_to_eof: bool, ranges=()) -> dict[str, object]:
    data = path.read_bytes()
    text = data.decode("utf-8")
    record: dict[str, object] = {
        "path": str(path),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "lines": len(text.splitlines()),
        "lf": data.count(b"\n"),
        "crlf": data.count(b"\r\n"),
        "utf8_bom": data.startswith(b"\xef\xbb\xbf"),
        "final_newline": data.endswith(b"\n"),
        "read_to_eof": read_to_eof,
    }
    if ranges:
        record["ranges_read"] = [list(item) for item in ranges]
    return record


def _constants(path: pathlib.Path) -> dict[str, object]:
    """Top-level literal constants of a module, read without importing it."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    out: dict[str, object] = {}
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                try:
                    out[target.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            target = node.target
            if isinstance(target, ast.Name):
                try:
                    out[target.id] = ast.literal_eval(node.value)
                except (ValueError, SyntaxError):
                    continue
    return out


def _top_level_names(path: pathlib.Path) -> dict[str, set[str]]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    functions = {node.name for node in tree.body if isinstance(node, ast.FunctionDef)}
    classes = {node.name for node in tree.body if isinstance(node, ast.ClassDef)}
    return {"functions": functions, "classes": classes}


def _test_functions(path: pathlib.Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


def _imports(path: pathlib.Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def _inventory(root: pathlib.Path, skip_prefixes: tuple[str, ...] = ()) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel == prefix or rel.startswith(prefix + "/") for prefix in skip_prefixes):
            continue
        out[rel] = _sha256(path)
    return out


def _old_evidence_inventory() -> dict[str, str]:
    out: dict[str, str] = {}
    base = KEY / "evidence" / "implementation"
    for directory in OLD_EVIDENCE_DIRS:
        for path in sorted((base / directory).rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(KEY).as_posix()
            if rel.startswith(OWN_STAGE_PREFIX):
                continue
            out[rel] = _sha256(path)
    for name in OLD_EVIDENCE_FILES:
        path = base / name
        out[path.relative_to(KEY).as_posix()] = _sha256(path)
    return out


class Recorder:
    def __init__(self) -> None:
        self.checks: dict[str, object] = {}
        self.problems: list[str] = []

    def check(self, name: str, condition: bool, detail: object = None) -> None:
        self.checks[name] = {"ok": bool(condition), "detail": detail}
        if not condition:
            self.problems.append(f"{name}: {detail}")


def main() -> int:
    recorder = Recorder()
    read_audit: dict[str, object] = {}

    for name in PRODUCTS:
        read_audit[f"implementation-worktree/packages/multi-workers/{name}"] = _audit_file(
            PACKAGES / name, read_to_eof=True
        )
    for name in ASSIGNED_TESTS:
        read_audit[f"implementation-worktree/packages/multi-workers/{name}"] = _audit_file(
            PACKAGES / name, read_to_eof=True
        )
    for name in PM_SCRIPTS:
        read_audit[f"rework-r2/pm-controlled/{name}"] = _audit_file(
            PM_CONTROLLED / name, read_to_eof=True
        )
    for name, ranges in SURFACE_READS.items():
        read_audit[f"implementation-worktree/packages/multi-workers/{name}"] = _audit_file(
            PACKAGES / name, read_to_eof=False, ranges=ranges
        )
    for name in OWN_FILES:
        read_audit[f"rework-r2/verification-preparation/{name}"] = _audit_file(
            HERE / name, read_to_eof=True
        )

    # 1) the delivered files are UTF-8/LF with a final newline and parse
    for name in OWN_FILES:
        record = read_audit[f"rework-r2/verification-preparation/{name}"]
        recorder.check(f"own_file_lf:{name}", record["crlf"] == 0, record["crlf"])
        recorder.check(f"own_file_final_newline:{name}", record["final_newline"] is True, None)
        recorder.check(f"own_file_utf8_bom:{name}", record["utf8_bom"] is False, None)
        try:
            ast.parse((HERE / name).read_text(encoding="utf-8"))
            parsed = True
        except SyntaxError as exc:  # pragma: no cover - only on a broken delivery
            parsed = False
            recorder.problems.append(f"own_file_syntax:{name}: {exc}")
        recorder.check(f"own_file_syntax:{name}", parsed, None)

    # 2) the runner's bound constants are the digests of the real bytes
    runner_constants = _constants(HERE / "run_pm_tests.py")
    recorder.check(
        "runner_products_binding",
        runner_constants.get("PRODUCTS") == {name: _sha256(PACKAGES / name) for name in PRODUCTS},
        runner_constants.get("PRODUCTS"),
    )
    recorder.check(
        "runner_assigned_tests_binding",
        runner_constants.get("ASSIGNED_TEST_SHA256")
        == {name: _sha256(PACKAGES / name) for name in ASSIGNED_TESTS},
        runner_constants.get("ASSIGNED_TEST_SHA256"),
    )
    recorder.check(
        "runner_live_binding",
        runner_constants.get("LIVE_SHA256")
        == {name: _sha256(LIVE / name) for name in runner_constants.get("LIVE_SHA256", {})},
        None,
    )
    recorder.check(
        "runner_helper_scripts_binding",
        runner_constants.get("HELPER_SCRIPTS")
        == {name: _sha256(HERE / name) for name in ("sitecustomize.py", "guard_preflight.py", "probe_imports.py")},
        runner_constants.get("HELPER_SCRIPTS"),
    )
    recorder.check(
        "runner_extra_suite_binding",
        runner_constants.get("EXTRA_SUITE_SHA256") == _sha256(HERE / "test_t10_r2_boundaries.py"),
        runner_constants.get("EXTRA_SUITE_SHA256"),
    )
    recorder.check(
        "runner_expected_extra_functions",
        tuple(runner_constants.get("EXTRA_EXPECTED_FUNCTIONS", ()))
        == tuple(_test_functions(HERE / "test_t10_r2_boundaries.py")),
        None,
    )
    declared_lifecycle = set(_test_functions(PACKAGES / ASSIGNED_TESTS[0]))
    recorder.check(
        "runner_focus_node_ids_declared",
        set(runner_constants.get("FOCUS_NODE_IDS", ())) <= declared_lifecycle,
        sorted(set(runner_constants.get("FOCUS_NODE_IDS", ())) - declared_lifecycle),
    )
    recorder.check(
        "runner_pre_repair_red_declared",
        set(runner_constants.get("PRE_REPAIR_RED_NODE_IDS", ())) <= declared_lifecycle,
        None,
    )
    recorder.check(
        "runner_item_bindings",
        runner_constants.get("EXISTING_ITEM_FLOOR") == 116
        and runner_constants.get("EXPECTED_ASSIGNED_ITEMS") == 130
        and runner_constants.get("EXPECTED_EXTRA_ITEMS_FLOOR") == 15,
        {
            "floor": runner_constants.get("EXISTING_ITEM_FLOOR"),
            "assigned": runner_constants.get("EXPECTED_ASSIGNED_ITEMS"),
            "extra": runner_constants.get("EXPECTED_EXTRA_ITEMS_FLOOR"),
        },
    )
    recorder.check(
        "runner_protected_counts",
        runner_constants.get("EXPECTED_MIRROR_FILES") == EXPECTED_MIRROR_FILES
        and runner_constants.get("EXPECTED_PYC_FILES") == EXPECTED_PYC_FILES
        and runner_constants.get("EXPECTED_OLD_EVIDENCE_FILES") == EXPECTED_OLD_EVIDENCE_FILES,
        None,
    )
    recorder.check(
        "runner_imports_no_product",
        not (
            _imports(HERE / "run_pm_tests.py")
            & {
                "decision",
                "decision_lifecycle",
                "decision_wire",
                "decision_task_state",
                "decision_points",
                "pytest",
            }
        ),
        sorted(_imports(HERE / "run_pm_tests.py")),
    )
    recorder.check(
        "extra_suite_imports",
        _imports(HERE / "test_t10_r2_boundaries.py")
        == {"__future__", "json", "os", "pathlib", "sys", "threading", "pytest", "decision_lifecycle", "decision_points", "decision_task_state", "decision_wire"},
        sorted(_imports(HERE / "test_t10_r2_boundaries.py")),
    )
    extra_constants = _constants(HERE / "test_t10_r2_boundaries.py")
    recorder.check(
        "extra_suite_predicted_red",
        tuple(extra_constants.get("PREDICTED_RED", ()))
        == ("test_a_recorded_fact_replays_as_a_duplicate_after_a_later_observation",),
        extra_constants.get("PREDICTED_RED"),
    )

    # 3) the protected counts still hold on the current disk
    mirror = _inventory(WORKTREE)
    pyc = {name: sha for name, sha in mirror.items() if name.endswith(".pyc")}
    old_evidence = _old_evidence_inventory()
    recorder.check("mirror_file_count", len(mirror) == EXPECTED_MIRROR_FILES, len(mirror))
    recorder.check("pyc_file_count", len(pyc) == EXPECTED_PYC_FILES, len(pyc))
    recorder.check(
        "old_evidence_file_count", len(old_evidence) == EXPECTED_OLD_EVIDENCE_FILES, len(old_evidence)
    )

    # 4) the current products really are the delivered after-bytes copies
    for name in PRODUCTS:
        recorder.check(
            f"product_matches_delivered_after:{name}",
            _sha256(PACKAGES / name) == _sha256(PRODUCT_REPAIR / "after-bytes" / name),
            None,
        )
    stage_a_audit = json.loads(
        (TEST_PREPARATION / "checks" / "verify_tests.result.json").read_text(encoding="utf-8")
    )
    for name in ASSIGNED_TESTS:
        recorded = stage_a_audit["checks"]["files"][name]["current_sha256"]
        recorder.check(
            f"assigned_test_matches_stage_a_audit:{name}",
            recorded == _sha256(PACKAGES / name),
            recorded,
        )
    recorder.check(
        "assigned_item_estimate",
        stage_a_audit["checks"]["files"]["test_decision_context_lifecycle.py"]["new_estimate_items"]
        + stage_a_audit["checks"]["files"]["test_decision_task_state.py"]["new_estimate_items"]
        == 130,
        None,
    )
    recorder.check(
        "stage_b_products_unchanged_since_absorption",
        json.loads(
            (KEY / "evidence/implementation/t10-r2-product-absorption-20261028/check.json").read_text(
                encoding="utf-8"
            )
        )["products_sha256"]
        == {name: _sha256(PACKAGES / name) for name in PRODUCTS + ASSIGNED_TESTS},
        None,
    )

    # 5) product surface: only the expected new helpers, nothing removed
    for name, expected_new in (
        ("decision_wire.py", EXPECTED_NEW_WIRE_FUNCTIONS),
        ("decision_lifecycle.py", EXPECTED_NEW_LIFECYCLE_FUNCTIONS),
    ):
        before = _top_level_names(PRODUCT_REPAIR / "before-bytes" / name)
        after = _top_level_names(PACKAGES / name)
        added = after["functions"] - before["functions"]
        removed = before["functions"] - after["functions"]
        recorder.check(f"product_functions_added:{name}", added == expected_new, sorted(added))
        recorder.check(f"product_functions_removed:{name}", removed == set(), sorted(removed))
        recorder.check(
            f"product_classes_unchanged:{name}",
            after["classes"] == before["classes"],
            sorted(after["classes"] ^ before["classes"]),
        )
    recorder.check(
        "task_state_byte_identical",
        _sha256(PACKAGES / "decision_task_state.py")
        == _sha256(PRODUCT_REPAIR / "before-bytes" / "decision_task_state.py"),
        None,
    )

    # 6) the AST/text facts the boundary suite and the runner depend on
    wire_text = (PACKAGES / "decision_wire.py").read_text(encoding="utf-8")
    lifecycle_text = (PACKAGES / "decision_lifecycle.py").read_text(encoding="utf-8")
    wire_constants = _constants(PACKAGES / "decision_wire.py")
    lifecycle_constants = _constants(PACKAGES / "decision_lifecycle.py")
    task_state_constants = _constants(PACKAGES / "decision_task_state.py")

    recorder.check(
        "wire_recorded_task_state",
        "def recorded_task_state(" in wire_text
        and wire_text.count("recorded_task_state(scope,") >= 1,
        wire_text.count("recorded_task_state(scope,"),
    )
    recorder.check(
        "wire_guard_slot_before_dedupe",
        wire_text.find("if guard is not None:") != -1
        and wire_text.find("if guard is not None:") < wire_text.find("if dedupe_event_id:"),
        {
            "guard": wire_text.find("if guard is not None:"),
            "dedupe": wire_text.find("if dedupe_event_id:"),
        },
    )
    recorder.check(
        "wire_guard_runs_inside_the_lock",
        wire_text.find("mw_common.acquire_lock(") < wire_text.find("if guard is not None:"),
        None,
    )
    recorder.check(
        "wire_case_insensitive_components",
        "_CASE_INSENSITIVE_PATHS = os.name == \"nt\"" in wire_text
        and wire_text.count("_same_path_component(part") >= 1,
        None,
    )
    recorder.check(
        "wire_public_shape_unchanged",
        wire_constants.get("SCHEMA_VERSION") == 1
        and wire_constants.get("LOCK_BUDGET_S") is not None
        and "terminal" in wire_constants.get("_KIND_FIELDS", {})
        and "request" in wire_constants.get("_KIND_FIELDS", {}),
        sorted(wire_constants.get("_KIND_FIELDS", {}))[:12],
    )
    recorder.check(
        "lifecycle_vocabularies_unchanged",
        tuple(lifecycle_constants.get("STAGES", ())) == ("consumed", "executed", "settled", "signoff")
        and tuple(lifecycle_constants.get("OUTCOMES", ()))
        == ("pending", "ok", "rework", "rollback", "inconclusive")
        and tuple(lifecycle_constants.get("TASK_TERMINALS", ()))
        == ("completed", "incomplete", "blocked")
        and len(lifecycle_constants.get("EXECUTED_ACTIONS", ())) == 10
        and len(lifecycle_constants.get("REQUEST_RESULT_FIELDS", ())) == 12,
        {
            "stages": lifecycle_constants.get("STAGES"),
            "terminals": lifecycle_constants.get("TASK_TERMINALS"),
            "actions": len(lifecycle_constants.get("EXECUTED_ACTIONS", ())),
            "request_fields": len(lifecycle_constants.get("REQUEST_RESULT_FIELDS", ())),
        },
    )
    recorder.check(
        "lifecycle_content_addressed_request_id",
        lifecycle_text.find("event = decision_wire.request_event(scope, event_id=event_id, **payload)")
        < lifecycle_text.find('_stable_event_id("rq", _canonical_json(recorded))'),
        None,
    )
    recorder.check(
        "lifecycle_floor_precheck_before_append",
        -1
        < lifecycle_text.find("_recorded_after_floor(store, meta, task_after)")
        < lifecycle_text.find("guard=None if task_after is None else lambda: _recorded_after_floor"),
        {
            "precheck": lifecycle_text.find("_recorded_after_floor(store, meta, task_after)"),
            "guard": lifecycle_text.find(
                "guard=None if task_after is None else lambda: _recorded_after_floor"
            ),
        },
    )
    recorder.check(
        "lifecycle_before_check_uses_recorded_form",
        "recorded = decision_wire.recorded_task_state(store._scope(), given)" in lifecycle_text,
        None,
    )
    recorder.check(
        "lifecycle_dynamic_answer_gate",
        "decision_points.entry_choice_issues(" in lifecycle_text
        and "decision_points.entry_material_issues(" in lifecycle_text
        and 'kind != "dynamic-candidates"' in lifecycle_text,
        None,
    )
    recorder.check(
        "task_state_shape_unchanged",
        tuple(task_state_constants.get("FIELDS", ()))
        == ("status", "observed_at", "source", "completed", "remaining", "blockers")
        and len(task_state_constants.get("STATUSES", ())) == 8
        and tuple(task_state_constants.get("SOURCES", ()))
        == ("worker-registry", "dispatch-result", "agent-report"),
        None,
    )

    # 7) the audited predecessor scripts and the old red runner are intact
    forensics = {}
    for name in PM_SCRIPTS:
        entry = _audit_file(PM_CONTROLLED / name, read_to_eof=True)
        forensics[f"rework-r2/pm-controlled/{name}"] = entry["sha256"]
    for name in ("report.md", "check.json"):
        path = KEY / "evidence/implementation/t10-r2-red-disposition-20261028" / name
        forensics[f"evidence/implementation/t10-r2-red-disposition-20261028/{name}"] = _sha256(path)
    red_reports = sorted((PM_CONTROLLED / "runs").glob("*/report.json"))
    recorder.check("pm_controlled_runs_present", len(red_reports) >= 2, len(red_reports))
    forensics["pm-controlled/runs"] = {path.parent.name: _sha256(path) for path in red_reports}
    recorder.check(
        "disposition_products_before",
        {
            name: entry["sha256"]
            for name, entry in json.loads(
                (OLD_DISPOSITION / "products-before.json").read_text(encoding="utf-8")
            ).items()
        }
        == {
            **{
                name: _sha256(PRODUCT_REPAIR / "before-bytes" / name)
                for name in PRODUCTS
            },
            **{
                name: _sha256(OLD_DISPOSITION / "before-bytes" / name)
                for name in ASSIGNED_TESTS
            },
        },
        None,
    )

    result = {
        "observed_at": _utc(),
        "source": "agent-report",
        "role": "coding",
        "python": sys.version,
        "dont_write_bytecode": bool(sys.dont_write_bytecode),
        "anchors": {
            "root": str(ROOT),
            "key": str(KEY),
            "worktree": str(WORKTREE),
            "packages": str(PACKAGES),
            "live": str(LIVE),
            "own_face": str(HERE),
        },
        "read_audit": read_audit,
        "counts": {
            "mirror_files": len(mirror),
            "pyc_files": len(pyc),
            "old_evidence_files": len(old_evidence),
            "own_files": len(OWN_FILES),
        },
        "checks": recorder.checks,
        "forensics": forensics,
        "problems": recorder.problems,
        "ok": not recorder.problems,
        "note": (
            "Pure AST/text verification: no product/test import, no pytest, no "
            "collection, no runner execution and no write outside this stage's "
            "checks/ directory. Behaviour is predicted from the code, not observed."
        ),
    }
    CHECKS_DIR.mkdir(parents=True, exist_ok=True)
    (CHECKS_DIR / "static_verify.result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    (CHECKS_DIR / "read-audit.json").write_text(
        json.dumps(
            {
                "observed_at": result["observed_at"],
                "read_audit": read_audit,
                "surface_read_scope": (
                    "decision_points.py / decision.py / mw_common.py are declared as "
                    "surface reads: only the cited ranges/functions were read, the "
                    "whole file was not"
                ),
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
                "ok": result["ok"],
                "checks": len(recorder.checks),
                "failed_checks": sorted(
                    name for name, entry in recorder.checks.items() if entry["ok"] is not True
                ),
                "problems": recorder.problems,
                "counts": result["counts"],
                "result": str(CHECKS_DIR / "static_verify.result.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
