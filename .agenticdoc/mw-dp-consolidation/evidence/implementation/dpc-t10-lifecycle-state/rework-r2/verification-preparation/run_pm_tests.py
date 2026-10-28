"""PM-executable guarded runner for T10 R2 stage C (independent re-verification).

This script implements no product logic. It is the single audited entry point the
PM uses for the stage-C run after the R2 product repair:

1. refuse to reuse anything - ``<fixture-root>/<label>`` and this stage's
   ``runs/<label>`` must both be absent and are created exclusively
   (``os.mkdir``); an existing object is never cleaned, reused or deleted;
2. bind the run to the *current* bytes: the three isolated products, both
   assigned test suites, the extra boundary suite, this stage's helper scripts,
   the five protected live files, the 1891-file isolated mirror, its 14 ``.pyc``
   files and the 744 old-evidence files are hashed and compared before anything
   executes; the whole predecessor face (``pm-controlled`` + its red runs,
   ``product-repair``, ``test-preparation``) and this stage's own delivered files
   are snapshotted, so a run that mutates any of them is a reported harness
   failure instead of a silent pass;
3. prove the guard's fail-closed branches with real children (missing sentinel
   configuration and an uncreatable sentinel path must terminate the interpreter
   with ``86`` and no output), then run the in-child guard self-control, the
   import-provenance probe, the collection listings and the two test stages -
   each in its own guarded child, each with its own raw ``stdout``/``stderr``/
   ``rc``/``argv``/``cwd`` written *before* any parsing;
4. keep the four test runs separate and separately logged: the assigned two
   suites (the original acceptance command), the focused stage-A node ids, and
   the extra boundary suite in its own ``--basetemp`` - no run shares a
   ``basetemp`` with another;
5. audit the guard sentinel *per child label and per pid*, so "every Python
   child was guarded" is evidence about each launched child (including the
   preflight's grandchild), not a claim extrapolated from one process;
6. write ``report.json`` next to the raw logs and exit with a real test return
   code - a known failure is never turned into ``rc 0``.

Exit codes: ``0`` all test runs passed, ``1`` a test run reported failures (the
pytest code is propagated unchanged), ``2`` harness/precondition/protection
failure, ``3`` refused (bad or already-existing target; nothing was written).

What it never does: import or patch a product or a test module, write outside
``<fixture-root>/<label>`` and this stage's ``runs/<label>``, reuse or delete an
old artifact, run a generator/HTTP/CLI/service/model/node command, or claim
"no socket was ever opened" (there is no packet capture here; the claim is only
"the guard was installed in every child and refused egress in the self-control").
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Bindings (all values were read from the current bytes in this stage)
# ---------------------------------------------------------------------------

HERE = Path(__file__).resolve().parent

ASSIGNED_TESTS = ("test_decision_context_lifecycle.py", "test_decision_task_state.py")
PRODUCTS = {
    # decision_wire.py / decision_lifecycle.py after the R2 product repair;
    # decision_task_state.py deliberately unchanged.
    "decision_wire.py": "429201ace7028968ae18cfbcc33dbf5aa0d2fa11b8f5d2dd7604cae0dec4e7dc",
    "decision_lifecycle.py": "73d0ae2efda3879668b3cf84d11f32809c6d00f76da13c3b8d065f87d4c87bb5",
    "decision_task_state.py": "b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d",
}
ASSIGNED_TEST_SHA256 = {
    "test_decision_context_lifecycle.py": "1bca28c56c7ab039de5c3a91638fd20c1e2fa89f4a1ec996169cfd933c1e6ae9",
    "test_decision_task_state.py": "30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f",
}
LIVE_SHA256 = {
    "decision_wire.py": "076fd3dee161a038fcc3597815863609d34b181da3f9f7646a8f0ee3dd911579",
    "decision_lifecycle.py": "e4ea5183cd28167a9ef35915c054d472c12b5b474817b93436564d2958d33248",
    "decision_task_state.py": "e82fc6b94f120d1d4ee561b6160d969b5ef36a86b6e3a0e8a3774c59a37e35e9",
    "test_decision_context_lifecycle.py": "106f17198a9de3552d2dc3e43aeb1c67474a6e4cb9c597811e792640d87a24f8",
    "test_decision_task_state.py": "c3de3c0456269aa3c8d1e0dfaf3f2098d9c9c657f6673ce93dc8cd5e7e54aff5",
}
#: This stage's helper scripts: the run must not use a different guard/probe.
HELPER_SCRIPTS = {
    "sitecustomize.py": "34a7fb04db4506250211f63870e4c54b7cb769547ac11bfe99cf306a4f90e94d",
    "guard_preflight.py": "6515a78ea8bef8e76ecef815c7087f91231dd7a100e892a86638d73b79ec9bb2",
    "probe_imports.py": "f2ff1a7bf5f5b7f48f124cd1812d79c5101acc002b64c2c9656dd655179665cb",
}
EXTRA_SUITE = "test_t10_r2_boundaries.py"
EXTRA_SUITE_SHA256 = "5abd812bf5f496ae37b91888f7cb9dc90f31b0290eefd2a1f454bf30bd90f771"

#: Files of the immutable predecessor face (all of them must survive the run).
PREDECESSOR_DIRS = ("pm-controlled", "product-repair", "test-preparation")
REWORK_DIR_NAME = "rework-r2"
OWN_FACE_NAME = "verification-preparation"

OLD_EVIDENCE_DIRS = (
    "dpc-t10-lifecycle-state",
    "dpc-t05-eight-cases",
    "t05-r2-envelope-pm-handoff-20261027",
    "t05-t10-audit-disposition-20261028",
)
OLD_EVIDENCE_FILES = ("t05-handoff-audit-20261027.md", "t10-handoff-audit-20261027.md")
OWN_STAGE_PREFIX = "evidence/implementation/dpc-t10-lifecycle-state/rework-r2/"
EXPECTED_OLD_EVIDENCE_FILES = 744
EXPECTED_PYC_FILES = 14
EXPECTED_MIRROR_FILES = 1891

#: Historical number of items in the two assigned suites before stage A. It is a
#: floor, not a locked total: the count may only grow (116 -> 130 at stage A).
EXISTING_ITEM_FLOOR = 116
#: Items collected by the two assigned suites at this revision (stage-A audit for
#: these exact bytes: 105 + 25). It is asserted as a floor so that a lost
#: parametrization cannot pass silently; the pinned test digests make the exact
#: value provable, they are not a substitute for `--collect-only`.
EXPECTED_ASSIGNED_ITEMS = 130
#: Collected items of the extra boundary suite (12 test functions, two of them
#: parametrized 2x/4x; the Windows-only case is skipped on POSIX).
EXPECTED_EXTRA_ITEMS_FLOOR = 15

FOCUS_NODE_IDS = (
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
#: Node ids that were red before the R2 product repair (observation only, never
#: converted into a green claim: this runner reports what the run really did).
PRE_REPAIR_RED_NODE_IDS = (
    "test_a_refused_request_does_not_swallow_the_later_real_choice",
    "test_a_different_choice_for_the_same_request_stays_visible",
    "test_a_dp_auto_choice_outside_the_prepared_candidates_is_not_recorded",
    "test_executed_and_settled_observations_stay_non_decreasing",
    "test_a_secret_bearing_creation_before_can_be_repeated",
    "test_a_case_variant_agenticdoc_path_is_refused_in_test_scope",
)
#: Extra-suite contract items that are *expected red* before the writer fix (the
#: AC-052 replay contract). Also observation only: the extra run's rc stays real.
EXTRA_PREDICTED_RED_NODE_IDS = (
    "test_a_recorded_fact_replays_as_a_duplicate_after_a_later_observation",
)
EXTRA_EXPECTED_FUNCTIONS = (
    "test_two_writers_recording_the_same_request_add_exactly_one_fact",
    "test_a_second_real_fact_stays_visible_and_grants_no_action",
    "test_a_recorded_fact_replays_as_a_duplicate_after_a_later_observation",
    "test_a_recorded_fact_replays_as_a_duplicate_before_any_later_observation",
    "test_a_new_older_observation_is_still_refused",
    "test_a_newer_recorded_observation_blocks_an_older_append_from_a_second_writer",
    "test_two_writers_racing_the_append_lock_never_order_an_older_observation_last",
    "test_a_known_secret_before_can_be_restated_and_is_never_stored_raw",
    "test_a_before_that_is_not_the_recorded_observation_is_refused",
    "test_an_exact_before_restatement_is_accepted_with_null_and_empty_kept_apart",
    "test_the_production_path_refusal_is_the_test_scopes_rule",
    "test_the_boundary_suite_runs_isolated_from_the_live_repository",
)

APPROVED_FIXTURE_ROOT = (
    "C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/pm-verification"
)
LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
CHILD_ENV_PASSTHROUGH = ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC")
CREDENTIAL_MARKERS = (
    "API_KEY",
    "APIKEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "AUTH",
    "COOKIE",
)
CREDENTIAL_PREFIXES = (
    "PI_",
    "MW_",
    "TIMI_",
    "TYPESAFE_",
    "OPENAI_",
    "ANTHROPIC_",
    "DASHSCOPE_",
    "AWS_",
    "AZURE_",
    "GCP_",
)
GUARD_ABORT_EXIT = 86
PYTEST_OK = (0, 1)

#: Child labels that always leave a guarded sentinel row, plus the optional ones.
DIRECT_CHILD_LABELS = (
    "guard-negative-control",
    "guard-preflight",
    "import-probe",
    "collect",
    "pytest",
    "collect-extra",
)

NEGATIVE_CHECKS = (
    "dns",
    "tcp",
    "udp",
    "http",
    "non_python_child",
    "missing_B",
    "no_site",
    "no_isolated_mode",
    "no_environment",
    "lost_guard_env",
    "shell_child",
)


class HarnessSetupError(RuntimeError):
    """The runner could not resolve its own audited anchors."""


@dataclass(frozen=True)
class Harness:
    root: Path
    key: Path
    worktree: Path
    packages: Path
    live: Path
    rework: Path


def _ancestor(offset: int, marker: str) -> Path:
    candidate = HERE.parents[offset]
    if not (candidate / marker).exists():
        raise HarnessSetupError(
            f"the audited anchor {candidate} does not contain {marker!r}; "
            "refusing to guess the repository layout"
        )
    return candidate


def _resolve_harness() -> Harness:
    evidence = _ancestor(3, "implementation")
    key = _ancestor(4, "implementation-worktree")
    root = _ancestor(6, "packages")
    if HERE.name != OWN_FACE_NAME:
        raise HarnessSetupError(f"this runner must live in {OWN_FACE_NAME}/, not {HERE.name!r}")
    if key.name != "mw-dp-consolidation":
        raise HarnessSetupError(f"unexpected owner key directory {key.name!r}")
    if HERE.parent.name != REWORK_DIR_NAME:
        raise HarnessSetupError(f"unexpected rework directory {HERE.parent.name!r}")
    if evidence.name != "evidence":
        raise HarnessSetupError(f"unexpected evidence directory {evidence.name!r}")
    worktree = key / "implementation-worktree"
    packages = worktree / "packages" / "multi-workers"
    live = root / "packages" / "multi-workers"
    for path in (worktree, packages, live, HERE.parent):
        if not path.is_dir():
            raise HarnessSetupError(f"required directory missing: {path}")
    if packages == live or not packages.is_dir() or not live.is_dir():
        raise HarnessSetupError("the isolated and live package directories are not distinct")
    return Harness(
        root=root,
        key=key,
        worktree=worktree,
        packages=packages,
        live=live,
        rework=HERE.parent,
    )


# ---------------------------------------------------------------------------
# Small utilities
# ---------------------------------------------------------------------------


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _inventory(root: Path, skip_prefixes: tuple[str, ...] = ()) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if any(rel == prefix or rel.startswith(prefix + "/") for prefix in skip_prefixes):
            continue
        out[rel] = _sha256(path)
    return out


def _diff(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(name for name in set(before) & set(after) if before[name] != after[name]),
    }


def _same_path(left: object, right: object) -> bool:
    return os.path.normcase(os.path.realpath(str(left))) == os.path.normcase(
        os.path.realpath(str(right))
    )


def _credential_shaped(names) -> list[str]:
    found: list[str] = []
    for name in names:
        upper = name.upper()
        if upper.startswith(CREDENTIAL_PREFIXES) or any(
            marker in upper for marker in CREDENTIAL_MARKERS
        ):
            found.append(name)
    return sorted(found)


def _test_function_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


def _collected_ids(stdout: str) -> list[str]:
    return [line.strip() for line in stdout.splitlines() if "::" in line]


def _base_node_id(node_id: str) -> str:
    return node_id.split("::")[-1].split("[")[0]


def _parse_summary(stdout: str) -> dict[str, object]:
    lines = [line for line in stdout.splitlines() if line.strip()]
    last = lines[-1].strip() if lines else ""
    counts: dict[str, int] = {}
    for match in re.finditer(
        r"(\d+) (passed|failed|skipped|xfailed|xpassed|deselected|error|errors|warning|warnings)\b",
        last,
    ):
        counts[match.group(2)] = int(match.group(1))
    failed = re.findall(r"^FAILED (\S+)", stdout, re.MULTILINE)
    return {"last_line": last, "counts": counts, "failed_node_ids": failed}


def _sentinel_rows(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            rows.append({"stage": "unparsable"})
            continue
        rows.append(parsed if isinstance(parsed, dict) else {"stage": "unparsable"})
    return rows


# ---------------------------------------------------------------------------
# Snapshots and protection
# ---------------------------------------------------------------------------


def _old_evidence_inventory(h: Harness) -> dict[str, str]:
    out: dict[str, str] = {}
    base = h.key / "evidence" / "implementation"
    for directory in OLD_EVIDENCE_DIRS:
        for path in sorted((base / directory).rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(h.key).as_posix()
            if rel.startswith(OWN_STAGE_PREFIX):
                continue
            out[rel] = _sha256(path)
    for name in OLD_EVIDENCE_FILES:
        path = base / name
        out[path.relative_to(h.key).as_posix()] = _sha256(path)
    return out


def _snapshot(h: Harness) -> dict[str, object]:
    mirror = _inventory(h.worktree)
    return {
        "mirror": mirror,
        "mirror_files": len(mirror),
        "pyc": {rel: sha for rel, sha in mirror.items() if rel.endswith(".pyc")},
        "old_evidence": _old_evidence_inventory(h),
        "live": {name: _sha256(h.live / name) for name in LIVE_SHA256},
        "products": {name: _sha256(h.packages / name) for name in PRODUCTS},
        "assigned_tests": {name: _sha256(h.packages / name) for name in ASSIGNED_TESTS},
        "predecessors": _inventory(h.rework, skip_prefixes=(OWN_FACE_NAME,)),
        "own_face": _inventory(HERE, skip_prefixes=("runs",)),
    }


def _protection_checks(
    h: Harness, before: dict[str, object], problems: list[str]
) -> None:
    if before["mirror_files"] != EXPECTED_MIRROR_FILES:
        problems.append(
            f"the isolated mirror holds {before['mirror_files']} files "
            f"(expected {EXPECTED_MIRROR_FILES})"
        )
    pyc = before["pyc"]
    if len(pyc) != EXPECTED_PYC_FILES:
        problems.append(f"{len(pyc)} protected pyc files (expected {EXPECTED_PYC_FILES})")
    old_evidence = before["old_evidence"]
    if len(old_evidence) != EXPECTED_OLD_EVIDENCE_FILES:
        problems.append(
            f"{len(old_evidence)} old-evidence files (expected {EXPECTED_OLD_EVIDENCE_FILES})"
        )
    for name, expected in PRODUCTS.items():
        current = before["products"].get(name)
        if current != expected:
            problems.append(f"the isolated {name} is not the bound product revision")
    for name, expected in ASSIGNED_TEST_SHA256.items():
        current = before["assigned_tests"].get(name)
        if current != expected:
            problems.append(f"the assigned suite {name} is not the bound revision")
    for name, expected in LIVE_SHA256.items():
        if before["live"].get(name) != expected:
            problems.append(f"the live {name} moved away from the protected bytes")
    for name, expected in HELPER_SCRIPTS.items():
        current = _sha256(HERE / name)
        if current != expected:
            problems.append(f"the stage helper {name} is not the audited revision")
    if _sha256(HERE / EXTRA_SUITE) != EXTRA_SUITE_SHA256:
        problems.append(f"the boundary suite {EXTRA_SUITE} is not the audited revision")
    extra_declared = _test_function_names(HERE / EXTRA_SUITE)
    if tuple(extra_declared) != EXTRA_EXPECTED_FUNCTIONS:
        problems.append(
            "the boundary suite declares different test functions than the runner binds: "
            f"{extra_declared}"
        )
    audit = h.rework / "test-preparation" / "checks" / "verify_tests.result.json"
    if audit.is_file():
        audited = json.loads(audit.read_text(encoding="utf-8"))
        for name in ASSIGNED_TESTS:
            recorded = (
                audited.get("checks", {}).get("files", {}).get(name, {}).get("current_sha256")
            )
            if recorded and recorded != _sha256(h.packages / name):
                problems.append(f"{name} changed after the stage-A audit; re-audit before running")
    else:
        problems.append("the stage-A audit result is missing; the assigned items are unproven")


# ---------------------------------------------------------------------------
# Child environment and execution
# ---------------------------------------------------------------------------


def _child_env(label_dir: Path, evidence_run: Path, label: str) -> dict[str, str]:
    """Whitelisted child environment - nothing is inherited from the parent."""
    env = {
        "HOME": str(label_dir / "home"),
        "USERPROFILE": str(label_dir / "home"),
        "TEMP": str(label_dir / "temp"),
        "TMP": str(label_dir / "temp"),
        "PYTHONPYCACHEPREFIX": str(label_dir / "pycache"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONPATH": str(HERE),
        "DPC10_GUARD_FILE": str(evidence_run / "guard-sentinel.jsonl"),
        "DPC10_GUARD_RUN": label,
    }
    for name in CHILD_ENV_PASSTHROUGH:
        value = os.environ.get(name)
        if value:
            env[name] = value
    return env


def _run(
    name: str,
    argv: list[str],
    env: dict[str, str],
    cwd: Path,
    artifacts: Path,
    *,
    guard_child: str | None,
):
    started = _utc()
    child_env = dict(env)
    if guard_child is not None:
        child_env["DPC10_GUARD_CHILD"] = guard_child
    else:
        child_env.pop("DPC10_GUARD_CHILD", None)
    process = subprocess.Popen(
        [str(item) for item in argv],
        cwd=str(cwd),
        env=child_env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = process.communicate()
    ended = _utc()
    (artifacts / f"{name}.stdout").write_bytes(stdout)
    (artifacts / f"{name}.stderr").write_bytes(stderr)
    _write_json(
        artifacts / f"{name}.meta.json",
        {
            "name": name,
            "argv": [str(item) for item in argv],
            "cwd": str(cwd),
            "guard_child": guard_child,
            "pid": process.pid,
            "rc": process.returncode,
            "started": started,
            "ended": ended,
            "stdout_bytes": len(stdout),
            "stderr_bytes": len(stderr),
        },
    )
    return (
        process.returncode,
        process.pid,
        stdout.decode("utf-8", "replace"),
        stderr.decode("utf-8", "replace"),
        len(stdout),
    )


# ---------------------------------------------------------------------------
# Guard fail-closed negative controls (real children, run by the PM only)
# ---------------------------------------------------------------------------


def _guard_negative_controls(
    label_dir: Path,
    evidence_run: Path,
    artifacts: Path,
    env: dict[str, str],
    problems: list[str],
) -> dict[str, object]:
    """Prove the site hook aborts the interpreter when it cannot be proven.

    ``run_pm_tests.py`` itself is intentionally *not* guarded (it launches the
    guarded children), so it can build the two broken environments the guard's
    own Popen wrapper would refuse to hand to a child.
    """
    controls: dict[str, object] = {}
    marker = "boundary-negative-control-ran"
    probe = ["-B", "-c", f"print('{marker}')"]

    missing_env = {key: value for key, value in env.items() if key != "DPC10_GUARD_FILE"}
    rc, pid, out, err, _ = _run(
        "guard-negative-no-sentinel",
        [sys.executable, *probe],
        missing_env,
        label_dir / "project",
        artifacts,
        guard_child="guard-negative-no-sentinel",
    )
    controls["no_sentinel_configuration"] = {
        "rc": rc,
        "pid": pid,
        "stdout": out,
        "stderr_chars": len(err),
        "expected": {"rc": GUARD_ABORT_EXIT, "stdout": ""},
        "ok": rc == GUARD_ABORT_EXIT and out.strip() == "",
    }

    unreachable = label_dir / "temp" / "guard-negative-missing-dir" / "sentinel.jsonl"
    unwritable_env = dict(env)
    unwritable_env["DPC10_GUARD_FILE"] = str(unreachable)
    rc, pid, out, err, _ = _run(
        "guard-negative-unwritable-sentinel",
        [sys.executable, *probe],
        unwritable_env,
        label_dir / "project",
        artifacts,
        guard_child="guard-negative-unwritable",
    )
    controls["unwritable_sentinel"] = {
        "rc": rc,
        "pid": pid,
        "stdout": out,
        "stderr_chars": len(err),
        "sentinel_path": str(unreachable),
        "sentinel_created": unreachable.exists(),
        "parent_created": unreachable.parent.exists(),
        "expected": {"rc": GUARD_ABORT_EXIT, "stdout": ""},
        "ok": (
            rc == GUARD_ABORT_EXIT
            and out.strip() == ""
            and not unreachable.exists()
            and not unreachable.parent.exists()
        ),
    }

    rc, pid, out, err, _ = _run(
        "guard-negative-control",
        [sys.executable, *probe],
        env,
        label_dir / "project",
        artifacts,
        guard_child="guard-negative-control",
    )
    controls["guarded_control"] = {
        "rc": rc,
        "pid": pid,
        "stdout": out,
        "stderr_chars": len(err),
        "expected": {"rc": 0, "stdout_contains": marker},
        "ok": rc == 0 and marker in out,
    }

    for key, entry in controls.items():
        if not entry["ok"]:
            problems.append(
                f"the guard fail-closed control {key} did not behave as required: "
                f"rc={entry['rc']}, stdout={entry['stdout']!r}"
            )
    return controls


# ---------------------------------------------------------------------------
# Sentinel audit
# ---------------------------------------------------------------------------


def _audit_sentinels(
    rows: list[dict[str, object]],
    label: str,
    grandchild_pid: object,
    expected_labels: tuple[str, ...],
    problems: list[str],
) -> dict[str, object]:
    by_label: dict[str, dict[str, dict[str, object]]] = {}
    unparsable = 0
    wrong_run: list[object] = []
    for row in rows:
        if row.get("stage") == "unparsable":
            unparsable += 1
            continue
        if row.get("run") != label:
            wrong_run.append(row.get("run"))
        pid = row.get("pid")
        child = row.get("child")
        if not isinstance(pid, int) or not isinstance(child, str) or not child:
            continue
        entry = by_label.setdefault(child, {}).setdefault(
            str(pid), {"stages": [], "network_denied": 0, "subprocess_denied": 0}
        )
        stages = entry["stages"]
        if isinstance(stages, list) and row.get("stage") not in stages:
            stages.append(row.get("stage"))
        if row.get("stage") == "network-denied":
            entry["network_denied"] = int(entry["network_denied"]) + 1
        if row.get("stage") == "subprocess-denied":
            entry["subprocess_denied"] = int(entry["subprocess_denied"]) + 1

    if unparsable:
        problems.append(f"{unparsable} unparsable guard sentinel rows")
    if wrong_run:
        problems.append(f"guard sentinels carry another run label: {sorted({str(v) for v in wrong_run})[:5]}")
    for label_name in expected_labels:
        children = by_label.get(label_name, {})
        if not children:
            problems.append(f"no guard sentinel exists for the child {label_name!r}")
            continue
        for pid, entry in children.items():
            stages = entry.get("stages") or []
            if "import" not in stages or "guard-installed" not in stages:
                problems.append(
                    f"the child {label_name!r} (pid {pid}) did not record both guard stages"
                )
    preflight_children = by_label.get("guard-preflight", {})
    if isinstance(grandchild_pid, int):
        grandchild = preflight_children.get(str(grandchild_pid))
        if not grandchild:
            problems.append(
                "the preflight's python grandchild left no guard sentinel (guard not inherited)"
            )
        elif "guard-installed" not in (grandchild.get("stages") or []):
            problems.append("the preflight's python grandchild was not guarded")
    pids_to_labels: dict[int, set[str]] = {}
    for label_name, children in by_label.items():
        for pid_text in children:
            pids_to_labels.setdefault(int(pid_text), set()).add(label_name)
    shared = {pid: sorted(names) for pid, names in pids_to_labels.items() if len(names) > 1}
    if shared:
        problems.append(f"one pid carries two child labels: {shared}")
    return {
        "children_seen": sorted(pids_to_labels),
        "by_label": {
            name: {pid: entry for pid, entry in sorted(children.items())}
            for name, children in sorted(by_label.items())
        },
        "total_sentinel_lines": len(rows),
        "wrong_run_labels": sorted({str(value) for value in wrong_run}),
        "unparsable_rows": unparsable,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _refuse(message: str, **extra: object) -> int:
    print(json.dumps({"status": "refused", "reason": message, **extra}, ensure_ascii=False, indent=2))
    return 3


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Guarded stage-C verification runner for T10 R2: binds the current "
            "product/test bytes, proves the guard's fail-closed branches, runs the "
            "two assigned suites, the focused node ids and the extra boundary suite "
            "as separate runs, and keeps every raw artifact next to report.json."
        )
    )
    parser.add_argument("--fixture-root", required=True, help="approved PM fixture root")
    parser.add_argument("--label", required=True, help="unique run label (new directory name)")
    parser.add_argument(
        "--focus",
        action="store_true",
        help="additionally run the focused stage-A node ids (separate artifacts)",
    )
    parser.add_argument(
        "--extra",
        action="store_true",
        help="additionally run the extra boundary suite (separate artifacts, own basetemp)",
    )
    return parser.parse_args(argv)


def _stop(artifacts: Path, stage: str, problems: list[str], **extra: object) -> int:
    payload = {"status": stage, "problems": problems, **extra}
    _write_json(artifacts / "report.json", payload)
    print(json.dumps({**payload, "report": str(artifacts / "report.json")}, ensure_ascii=False, indent=2))
    return 2


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        h = _resolve_harness()
    except HarnessSetupError as exc:
        return _refuse(f"the runner anchors could not be resolved: {exc}")

    label = args.label
    if LABEL_PATTERN.fullmatch(label) is None:
        return _refuse("the label must be one safe path component ([A-Za-z0-9][A-Za-z0-9._-]{0,63})")
    if not sys.dont_write_bytecode:
        return _refuse("the PM runner requires -B")

    fixture_root = Path(os.path.abspath(args.fixture_root))
    approved_fixture = Path(APPROVED_FIXTURE_ROOT)
    if fixture_root.resolve() != approved_fixture.resolve():
        return _refuse("the fixture root is outside the specific PM authorization")

    fixture_root_created = False
    if fixture_root.exists():
        if not fixture_root.is_dir():
            return _refuse(
                "the fixture root exists but is not a directory", fixture_root=str(fixture_root)
            )
    else:
        try:
            os.mkdir(fixture_root)
        except FileExistsError:
            return _refuse("the fixture root appeared concurrently; refusing")
        except OSError as exc:
            return _refuse(
                f"the fixture root could not be created ({type(exc).__name__}); "
                "the approved OS root must exist",
                fixture_root=str(fixture_root),
            )
        fixture_root_created = True

    resolved_fixture = fixture_root.resolve()
    if ".agenticdoc" in [part.lower() for part in resolved_fixture.parts]:
        return _refuse("the fixture root must stay outside the .agenticdoc tree")
    if resolved_fixture == h.worktree or h.worktree in resolved_fixture.parents:
        return _refuse("the fixture root must stay outside the isolated worktree")

    label_dir = resolved_fixture / label
    evidence_run = HERE / "runs" / label
    if label_dir.exists():
        return _refuse("the label directory already exists; it is never reused", path=str(label_dir))
    if evidence_run.exists():
        return _refuse(
            "the evidence run directory already exists; it is never reused", path=str(evidence_run)
        )
    try:
        os.mkdir(label_dir)
    except FileExistsError:
        return _refuse("the label directory appeared concurrently; refusing", path=str(label_dir))
    for name in ("home", "temp", "project", "pycache"):
        (label_dir / name).mkdir()
    evidence_run.mkdir(parents=True)

    artifacts = evidence_run
    env = _child_env(label_dir, evidence_run, label)
    credential_keys = _credential_shaped(env)
    problems: list[str] = []
    checks: dict[str, object] = {}

    _write_json(
        artifacts / "meta.json",
        {
            "observed_at": _utc(),
            "stage": "C-verification-preparation",
            "label": label,
            "argv": [str(item) for item in (argv if argv is not None else sys.argv[1:])],
            "cwd": os.getcwd(),
            "python": sys.version,
            "executable": sys.executable,
            "dont_write_bytecode": bool(sys.dont_write_bytecode),
            "fixture_root": str(resolved_fixture),
            "fixture_root_created": fixture_root_created,
            "label_dir": str(label_dir),
            "evidence_run": str(evidence_run),
            "isolated_packages": str(h.packages),
            "live_packages": str(h.live),
            "env_keys": sorted(env),
            "env_policy": "whitelist only; nothing inherited from the parent environment",
            "credential_shaped_env_names": credential_keys,
            "runner": {
                "file": str(HERE / "run_pm_tests.py"),
                "sha256": _sha256(HERE / "run_pm_tests.py"),
                "bytes": (HERE / "run_pm_tests.py").stat().st_size,
            },
            "bindings": {
                "products": PRODUCTS,
                "assigned_tests": ASSIGNED_TEST_SHA256,
                "live": LIVE_SHA256,
                "helper_scripts": HELPER_SCRIPTS,
                "extra_suite": {EXTRA_SUITE: EXTRA_SUITE_SHA256},
            },
        },
    )

    # 1) bindings and protection (before anything executes)
    before = _snapshot(h)
    _write_json(
        artifacts / "before.json",
        {
            "mirror_files": before["mirror_files"],
            "pyc_count": len(before["pyc"]),
            "old_evidence_files": len(before["old_evidence"]),
            "live": before["live"],
            "products": before["products"],
            "assigned_tests": before["assigned_tests"],
            "predecessor_files": len(before["predecessors"]),
            "own_face_files": len(before["own_face"]),
        },
    )
    _write_json(artifacts / "mirror.before.json", before["mirror"])
    _write_json(artifacts / "old-evidence.before.json", before["old_evidence"])
    _write_json(artifacts / "predecessors.before.json", before["predecessors"])
    if credential_keys:
        problems.append(f"credential-shaped names reached the child environment: {credential_keys}")
    _protection_checks(h, before, problems)
    if problems:
        return _stop(artifacts, "precondition-failed", problems)

    # 2) guard fail-closed negative controls (real children)
    controls = _guard_negative_controls(label_dir, evidence_run, artifacts, env, problems)
    checks["guard_negative_controls"] = controls
    if problems:
        return _stop(artifacts, "guard-negative-controls-failed", problems)

    # 3) guard self-control inside a guarded child
    preflight_argv = [sys.executable, "-B", str(HERE / "guard_preflight.py")]
    preflight_rc, preflight_pid, preflight_out, preflight_err, _ = _run(
        "guard-preflight",
        preflight_argv,
        env,
        label_dir / "project",
        artifacts,
        guard_child="guard-preflight",
    )
    preflight: dict[str, object] = {}
    try:
        parsed = json.loads(preflight_out)
        preflight = parsed if isinstance(parsed, dict) else {}
    except ValueError:
        problems.append("the guard preflight did not print JSON")
    _write_json(
        artifacts / "guard-preflight.json",
        {"rc": preflight_rc, "pid": preflight_pid, "stderr": preflight_err, "report": preflight},
    )
    if preflight_rc != 0:
        problems.append(f"the guard preflight failed (rc={preflight_rc})")
    preflight_checks = preflight.get("checks", {}) if isinstance(preflight, dict) else {}
    if not isinstance(preflight_checks, dict):
        problems.append("the guard preflight reported an unexpected shape")
        preflight_checks = {}
    for name in NEGATIVE_CHECKS:
        entry = preflight_checks.get(name, {})
        if not isinstance(entry, dict) or entry.get("refused") is not True or entry.get("guard_message") is not True:
            problems.append(f"the guard did not refuse {name} inside the child")
    if preflight_checks.get("credential_env_names") != []:
        problems.append("credential-shaped environment names reached the guarded child")
    if preflight_checks.get("python_child_pid") is None:
        problems.append("the guarded child could not spawn the python grandchild")
    if problems:
        return _stop(
            artifacts, "guard-preflight-failed", problems, guard_preflight={"rc": preflight_rc}
        )

    # 4) import provenance (real interpreter, isolated tree, no cache/live stand-in)
    probe_argv = [sys.executable, "-B", str(HERE / "probe_imports.py"), str(h.packages)]
    probe_rc, probe_pid, probe_out, probe_err, _ = _run(
        "import-probe", probe_argv, env, h.packages, artifacts, guard_child="import-probe"
    )
    probe: dict[str, object] = {}
    try:
        parsed = json.loads(probe_out)
        probe = parsed if isinstance(parsed, dict) else {}
    except ValueError:
        problems.append("the import probe did not print JSON")
    _write_json(artifacts / "imports.json", {"rc": probe_rc, "pid": probe_pid, "stderr": probe_err, "report": probe})
    if probe_rc != 0:
        problems.append(f"the import probe failed (rc={probe_rc})")
    if probe:
        if probe.get("dont_write_bytecode") is not True:
            problems.append("the import probe child did not run under -B")
        if not _same_path(probe.get("packages_dir"), h.packages):
            problems.append("the import probe did not anchor on the isolated package directory")
        sys_path = probe.get("sys_path") or []
        if not sys_path or not _same_path(sys_path[0], h.packages):
            problems.append("the isolated package directory is not the first sys.path entry")
        if any(_same_path(entry, h.live) for entry in sys_path):
            problems.append("the live package directory is on the probe's sys.path")
        modules = probe.get("modules") or {}
        tests = probe.get("test_modules") or {}
        if not isinstance(modules, dict) or not isinstance(tests, dict):
            problems.append("the import probe reported an unexpected shape")
            modules, tests = {}, {}
        for name, entry in modules.items():
            if not isinstance(entry, dict):
                problems.append(f"{name} did not import cleanly")
                continue
            raw = entry.get("file")
            if not isinstance(raw, str) or not raw:
                problems.append(f"{name} did not import")
                continue
            resolved = Path(raw).resolve()
            if h.packages not in resolved.parents:
                problems.append(f"{name} was imported from outside the isolated tree")
            if h.live in resolved.parents or resolved == (h.live / resolved.name):
                problems.append(f"{name} was imported from the live repository")
            if entry.get("inside_packages_dir") is not True:
                problems.append(f"{name} reported a file outside the isolated package directory")
            if entry.get("sha256") != _sha256(h.packages / resolved.name):
                problems.append(f"{name} did not import the current isolated bytes")
        for name, entry in tests.items():
            raw = entry.get("origin") if isinstance(entry, dict) else None
            if not isinstance(raw, str) or not raw:
                problems.append(f"{name} was not locatable")
                continue
            if h.packages not in Path(raw).resolve().parents:
                problems.append(f"{name} was located outside the isolated tree")
        for name in ("decision_lifecycle", "decision_wire", "decision_task_state"):
            entry = modules.get(name, {})
            expected = PRODUCTS[f"{name}.py"]
            if not isinstance(entry, dict) or entry.get("sha256") != expected:
                problems.append(f"{name} is not the bound product revision")
    if problems:
        return _stop(artifacts, "import-provenance-failed", problems)

    # 5) collection listing of the two assigned suites
    collect_argv = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
        "--collect-only",
        *ASSIGNED_TESTS,
    ]
    collect_rc, collect_pid, collect_out, collect_err, _ = _run(
        "collect", collect_argv, env, h.packages, artifacts, guard_child="collect"
    )
    collected = _collected_ids(collect_out)
    (artifacts / "collection.node-ids.txt").write_text(
        "\n".join(collected) + ("\n" if collected else ""), encoding="utf-8", newline="\n"
    )
    collected_bases = {_base_node_id(node) for node in collected}
    lost: dict[str, list[str]] = {}
    for name in ASSIGNED_TESTS:
        declared = set(_test_function_names(h.packages / name))
        missing = sorted(declared - collected_bases)
        if missing:
            lost[name] = missing
            problems.append(f"{name} lost collected test functions: {missing}")
    if collect_rc != 0:
        problems.append(f"the collection listing failed (rc={collect_rc})")
    if len(collected) < EXISTING_ITEM_FLOOR:
        problems.append(f"only {len(collected)} items were collected (floor {EXISTING_ITEM_FLOOR})")
    if len(collected) < EXPECTED_ASSIGNED_ITEMS:
        problems.append(
            f"only {len(collected)} assigned items were collected "
            f"(the bound revisions collect {EXPECTED_ASSIGNED_ITEMS})"
        )
    missing_focus = sorted(set(FOCUS_NODE_IDS) - collected_bases)
    if missing_focus:
        problems.append(f"the focused revision items are not collected: {missing_focus}")
    if problems:
        return _stop(artifacts, "collection-failed", problems)

    # 6) the required two-file run (original acceptance command)
    pytest_argv = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
        "--basetemp",
        str(label_dir / "pytest-basetemp"),
        *ASSIGNED_TESTS,
    ]
    pytest_rc, pytest_pid, pytest_out, pytest_err, _ = _run(
        "pytest", pytest_argv, env, h.packages, artifacts, guard_child="pytest"
    )
    summary = _parse_summary(pytest_out)
    _write_json(artifacts / "pytest.summary.json", summary)
    if pytest_rc not in PYTEST_OK:
        problems.append(f"the assigned pytest run did not execute normally (rc={pytest_rc})")
    failed_bases = {_base_node_id(node) for node in summary["failed_node_ids"]}
    if "failed" not in summary["counts"] and pytest_rc == 1:
        problems.append("pytest returned a non-zero code without a parsed failure line")

    focus: dict[str, object] | None = None
    if args.focus:
        focus_argv = [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            f"--basetemp={label_dir / 'pytest-basetemp-focus'}",
            *[f"{ASSIGNED_TESTS[0]}::{name}" for name in FOCUS_NODE_IDS],
        ]
        focus_rc, focus_pid, focus_out, focus_err, _ = _run(
            "focus", focus_argv, env, h.packages, artifacts, guard_child="focus"
        )
        focus = {
            "rc": focus_rc,
            "pid": focus_pid,
            "summary": _parse_summary(focus_out),
            "stderr_chars": len(focus_err),
            "argv": focus_argv,
        }
        _write_json(artifacts / "focus.json", focus)
        if focus_rc not in PYTEST_OK:
            problems.append(f"the focused run did not execute normally (rc={focus_rc})")

    # 7) the extra boundary suite: collection first, then its own basetemp run
    extra_path = HERE / EXTRA_SUITE
    extra_collect_argv = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
        "--collect-only",
        str(extra_path),
    ]
    extra_rc_collect, extra_collect_pid, extra_collect_out, _extra_collect_err, _ = _run(
        "collect-extra",
        extra_collect_argv,
        env,
        h.packages,
        artifacts,
        guard_child="collect-extra",
    )
    extra_collected = _collected_ids(extra_collect_out)
    (artifacts / "collection-extra.node-ids.txt").write_text(
        "\n".join(extra_collected) + ("\n" if extra_collected else ""),
        encoding="utf-8",
        newline="\n",
    )
    extra_bases = {_base_node_id(node) for node in extra_collected}
    missing_extra = sorted(set(EXTRA_EXPECTED_FUNCTIONS) - extra_bases)
    if extra_rc_collect != 0:
        problems.append(f"the boundary-suite collection failed (rc={extra_rc_collect})")
    if missing_extra:
        problems.append(f"the boundary suite lost collected test functions: {missing_extra}")
    if len(extra_collected) < EXPECTED_EXTRA_ITEMS_FLOOR:
        problems.append(
            f"only {len(extra_collected)} boundary items were collected "
            f"(floor {EXPECTED_EXTRA_ITEMS_FLOOR})"
        )
    if problems:
        return _stop(artifacts, "extra-collection-failed", problems)

    extra: dict[str, object] | None = None
    if args.extra:
        extra_argv = [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            "--basetemp",
            str(label_dir / "pytest-basetemp-extra"),
            str(extra_path),
        ]
        extra_rc, extra_pid, extra_out, extra_err, _ = _run(
            "pytest-extra", extra_argv, env, h.packages, artifacts, guard_child="pytest-extra"
        )
        extra_summary = _parse_summary(extra_out)
        extra_failed = {_base_node_id(node) for node in extra_summary["failed_node_ids"]}
        extra = {
            "rc": extra_rc,
            "pid": extra_pid,
            "summary": extra_summary,
            "stderr_chars": len(extra_err),
            "argv": extra_argv,
            "basetemp": str(label_dir / "pytest-basetemp-extra"),
            "predicted_red": {
                "items": list(EXTRA_PREDICTED_RED_NODE_IDS),
                "observed_failing": sorted(set(EXTRA_PREDICTED_RED_NODE_IDS) & extra_failed),
                "unexpected_failures": sorted(extra_failed - set(EXTRA_PREDICTED_RED_NODE_IDS)),
                "note": (
                    "the AC-052 replay item is stated as an expectation, not as a "
                    "green claim; the rc stays real and is not rewritten"
                ),
            },
        }
        _write_json(artifacts / "extra.json", extra)
        if extra_rc not in PYTEST_OK:
            problems.append(f"the boundary-suite run did not execute normally (rc={extra_rc})")

    # 8) after snapshot + protection diff + per-child sentinel audit
    after = _snapshot(h)
    protection = {
        "mirror": {
            "before_files": before["mirror_files"],
            "after_files": after["mirror_files"],
            "diff": _diff(before["mirror"], after["mirror"]),
        },
        "pyc": {
            "count_before": len(before["pyc"]),
            "count_after": len(after["pyc"]),
            "diff": _diff(before["pyc"], after["pyc"]),
        },
        "old_evidence": {
            "before_files": len(before["old_evidence"]),
            "after_files": len(after["old_evidence"]),
            "diff": _diff(before["old_evidence"], after["old_evidence"]),
        },
        "predecessors": {
            "before_files": len(before["predecessors"]),
            "after_files": len(after["predecessors"]),
            "diff": _diff(before["predecessors"], after["predecessors"]),
        },
        "own_face": {
            "before_files": len(before["own_face"]),
            "after_files": len(after["own_face"]),
            "diff": _diff(before["own_face"], after["own_face"]),
        },
        "live": {
            "before": before["live"],
            "after": after["live"],
            "unchanged": before["live"] == after["live"],
        },
        "products": {
            "expected": PRODUCTS,
            "before": before["products"],
            "after": after["products"],
            "unchanged": before["products"] == after["products"],
        },
        "assigned_tests": {
            "expected": ASSIGNED_TEST_SHA256,
            "after": after["assigned_tests"],
            "unchanged": before["assigned_tests"] == after["assigned_tests"],
        },
    }
    _write_json(artifacts / "protection.json", protection)
    for name in ("mirror", "old_evidence", "predecessors", "own_face"):
        diff = protection[name]["diff"]
        if diff["added"] or diff["removed"] or diff["changed"]:
            problems.append(f"the {name} tree changed during the run: {diff}")
    if any(protection["pyc"]["diff"][key] for key in ("added", "removed", "changed")):
        problems.append(f"a protected pyc changed during the run: {protection['pyc']['diff']}")
    if not protection["live"]["unchanged"]:
        problems.append("a live product file changed during the run")
    if not protection["products"]["unchanged"]:
        problems.append("an isolated product file changed during the run")
    if not protection["assigned_tests"]["unchanged"]:
        problems.append("an assigned test suite changed during the run")

    sentinel = _sentinel_rows(artifacts / "guard-sentinel.jsonl")
    expected_labels = tuple(DIRECT_CHILD_LABELS) + tuple(
        name
        for name, present in (("focus", focus is not None), ("pytest-extra", extra is not None))
        if present
    )
    guard_audit = _audit_sentinels(
        sentinel,
        label,
        preflight_checks.get("python_child_pid"),
        expected_labels,
        problems,
    )
    checks["guard"] = guard_audit
    checks["guard_preflight"] = {"rc": preflight_rc, "pid": preflight_pid, "checks": preflight_checks}

    pre_repair_observed = sorted(set(PRE_REPAIR_RED_NODE_IDS) & failed_bases)
    pre_repair_still_failing = pre_repair_observed
    unexpected_failures = sorted(failed_bases - set(PRE_REPAIR_RED_NODE_IDS))

    report = {
        "observed_at": _utc(),
        "status": "executed" if not problems else "harness-failed",
        "stage": "C-verification-preparation",
        "label": label,
        "fixture_root": str(resolved_fixture),
        "fixture_root_created": fixture_root_created,
        "label_dir": str(label_dir),
        "evidence_run": str(evidence_run),
        "env_keys": sorted(env),
        "commands": {
            "guard_preflight": preflight_argv,
            "import_probe": probe_argv,
            "collect": collect_argv,
            "pytest": pytest_argv,
            "focus": (focus or {}).get("argv"),
            "collect_extra": extra_collect_argv,
            "pytest_extra": (extra or {}).get("argv"),
        },
        "rc": {
            "guard_preflight": preflight_rc,
            "import_probe": probe_rc,
            "collect": collect_rc,
            "pytest": pytest_rc,
            "focus": None if focus is None else focus["rc"],
            "collect_extra": extra_rc_collect,
            "pytest_extra": None if extra is None else extra["rc"],
        },
        "collection": {
            "count": len(collected),
            "historical_floor": EXISTING_ITEM_FLOOR,
            "bound_items": EXPECTED_ASSIGNED_ITEMS,
            "focus_node_ids_present": not missing_focus,
            "lost_test_functions": lost,
            "node_ids_file": "collection.node-ids.txt",
        },
        "collection_extra": {
            "count": len(extra_collected),
            "bound_functions": len(EXTRA_EXPECTED_FUNCTIONS),
            "missing_functions": missing_extra,
            "node_ids_file": "collection-extra.node-ids.txt",
            "basetemp": str(label_dir / "pytest-basetemp-extra"),
        },
        "pytest": {
            "summary_line": summary["last_line"],
            "counts": summary["counts"],
            "failed_node_ids": summary["failed_node_ids"],
            "stdout_file": "pytest.stdout",
            "stderr_file": "pytest.stderr",
            "meta_file": "pytest.meta.json",
        },
        "pytest_pre_repair_red": {
            "items": list(PRE_REPAIR_RED_NODE_IDS),
            "still_failing": pre_repair_still_failing,
            "unexpected_failures": unexpected_failures,
            "note": (
                "observation only: these were red before the R2 product repair; this "
                "runner neither asserts them green nor turns a failure into rc 0"
            ),
        },
        "focus": focus,
        "extra": extra,
        "guard_preflight": {
            "rc": preflight_rc,
            "pid": preflight_pid,
            "checks": preflight_checks,
            "file": "guard-preflight.json",
        },
        "guard_negative_controls": controls,
        "imports": {"file": "imports.json", "packages_dir": str(h.packages)},
        "protection": protection,
        "checks": checks,
        "problems": problems,
        "network_claim": (
            "the guard was installed in every guarded python child (audited per pid "
            "and child label) and refused DNS/TCP/UDP/HTTP in the self-control; there "
            "is no packet capture, so this is not a proof about the OS stack"
        ),
    }
    _write_json(artifacts / "report.json", report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "label": label,
                "rc": report["rc"],
                "collected": len(collected),
                "collected_extra": len(extra_collected),
                "counts": summary["counts"],
                "extra_counts": None if extra is None else extra["summary"]["counts"],
                "pre_repair_still_failing": pre_repair_still_failing,
                "unexpected_failures": unexpected_failures,
                "problems": problems,
                "report": str(artifacts / "report.json"),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if problems:
        return 2
    # No return code is rewritten: the assigned run is the acceptance command and
    # its code wins; the additional runs only escalate a real failure, never mask it.
    for candidate in (pytest_rc, None if focus is None else focus["rc"], None if extra is None else extra["rc"]):
        if candidate:
            return int(candidate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
