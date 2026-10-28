"""PM-executable guarded runner for the two assigned T10 suites (R2 stage A).

This script implements no product logic. It is the audited, single entry point
the PM uses to obtain the real red run and, later, the post-fix run:

1. refuse to reuse anything - ``<fixture-root>/<label>`` and the
   ``runs/<label>`` evidence directory must both be absent and are created
   exclusively (``os.mkdir``); an existing object is never cleaned or reused;
2. snapshot the protected trees before the run (the isolated mirror, the 14
   protected ``pyc`` files, the 744 old-evidence files, the live five) and
   repeat the snapshot afterwards, so a run that writes a product file becomes a
   reported harness failure instead of a silent pass;
3. build a from-scratch whitelisted child environment (nothing inherited: no
   provider / worker / ``PI_*`` / project / credential variable, no
   ``PYTHONSTARTUP``); HOME/USERPROFILE, TEMP/TMP, the pycache prefix, the
   project root and pytest's ``--basetemp`` all live under the approved PM
   fixture directory;
4. run, each in its own guarded child (see ``sitecustomize.py``): the guard
   self-control, the import-provenance probe, the collection listing, the
   required two-file ``pytest`` command and, with ``--focus``, the added
   node ids only. Every raw stdout/stderr/rc/argv/cwd is written *before* any
   parsing happens;
5. write ``report.json`` next to those raw logs and exit with the pytest return
   code - a known failure is never turned into rc 0.

Exit codes: ``0`` pytest passed, ``1`` pytest failed, ``2`` harness/protection
failure, ``3`` refused (bad or already-existing target, nothing was written).

What it never does: import or patch the product itself, write outside
``<fixture-root>/<label>`` and this stage's ``runs/<label>``, reuse or delete an
old artifact, run a generator/HTTP/CLI/service/model/node command, or claim
"no socket was ever opened" (there is no packet capture here; the claim is only
"the guard was installed in every child and refused egress").
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
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
KEY = HERE.parents[4]
ROOT = HERE.parents[6]
WORKTREE = KEY / "implementation-worktree"
PACKAGES = WORKTREE / "packages" / "multi-workers"
LIVE = ROOT / "packages" / "multi-workers"

ASSIGNED_TESTS = ("test_decision_context_lifecycle.py", "test_decision_task_state.py")
PRODUCTS = {
    "decision_wire.py": "429201ace7028968ae18cfbcc33dbf5aa0d2fa11b8f5d2dd7604cae0dec4e7dc",
    "decision_lifecycle.py": "73d0ae2efda3879668b3cf84d11f32809c6d00f76da13c3b8d065f87d4c87bb5",
    "decision_task_state.py": "b01e08b0cb223d572f8c1b1ef50aa92c0cd02d6cd598e82b3abe829f5805836d",
}
LIVE_SHA256 = {
    "decision_wire.py": "076fd3dee161a038fcc3597815863609d34b181da3f9f7646a8f0ee3dd911579",
    "decision_lifecycle.py": "e4ea5183cd28167a9ef35915c054d472c12b5b474817b93436564d2958d33248",
    "decision_task_state.py": "e82fc6b94f120d1d4ee561b6160d969b5ef36a86b6e3a0e8a3774c59a37e35e9",
    "test_decision_context_lifecycle.py": "106f17198a9de3552d2dc3e43aeb1c67474a6e4cb9c597811e792640d87a24f8",
    "test_decision_task_state.py": "c3de3c0456269aa3c8d1e0dfaf3f2098d9c9c657f6673ce93dc8cd5e7e54aff5",
}
#: Authoring-time sha256 of the appended lifecycle test file (stage-A audit).
ASSIGNED_TEST_SHA256 = {
    "test_decision_context_lifecycle.py": "1bca28c56c7ab039de5c3a91638fd20c1e2fa89f4a1ec996169cfd933c1e6ae9",
    "test_decision_task_state.py": "30c6e4dd34e459b9c6533065777cf606f8e9215d4a2ebde737a405d6d39dc23f",
}
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
EXISTING_ITEM_FLOOR = 130

NEW_NODE_IDS = (
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
EXPECTED_RED_NODE_IDS = (
    "test_a_refused_request_does_not_swallow_the_later_real_choice",
    "test_a_different_choice_for_the_same_request_stays_visible",
    "test_a_dp_auto_choice_outside_the_prepared_candidates_is_not_recorded",
    "test_executed_and_settled_observations_stay_non_decreasing",
    "test_a_secret_bearing_creation_before_can_be_repeated",
    "test_a_case_variant_agenticdoc_path_is_refused_in_test_scope",
)
EXPECTED_GREEN_NODE_IDS = (
    "test_an_identical_repeated_business_request_stays_idempotent",
    "test_a_dp_auto_choice_inside_the_prepared_candidates_is_recorded",
    "test_a_failed_executed_round_is_never_recorded_as_executed",
    "test_the_exact_agenticdoc_path_is_refused_in_test_scope",
    "test_the_writer_consumes_the_producers_frozen_prepared_contract",
)

LABEL_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")
CHILD_ENV_PASSTHROUGH = ("SYSTEMROOT", "WINDIR", "PATH", "PATHEXT", "COMSPEC")


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
        if any(rel.startswith(prefix) for prefix in skip_prefixes):
            continue
        out[rel] = _sha256(path)
    return out


def _old_evidence_inventory() -> dict[str, str]:
    out: dict[str, str] = {}
    for directory in OLD_EVIDENCE_DIRS:
        base = KEY / "evidence" / "implementation" / directory
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(KEY).as_posix()
            if rel.startswith(OWN_STAGE_PREFIX):
                continue
            out[rel] = _sha256(path)
    for name in OLD_EVIDENCE_FILES:
        path = KEY / "evidence" / "implementation" / name
        out[path.relative_to(KEY).as_posix()] = _sha256(path)
    return out


def _diff(before: dict[str, str], after: dict[str, str]) -> dict[str, list[str]]:
    return {
        "added": sorted(set(after) - set(before)),
        "removed": sorted(set(before) - set(after)),
        "changed": sorted(name for name in set(before) & set(after) if before[name] != after[name]),
    }


def _protected_snapshot() -> dict[str, object]:
    mirror = _inventory(WORKTREE)
    return {
        "mirror": mirror,
        "mirror_files": len(mirror),
        "pyc": {rel: sha for rel, sha in mirror.items() if rel.endswith(".pyc")},
        "old_evidence": _old_evidence_inventory(),
        "live": {name: _sha256(LIVE / name) for name in LIVE_SHA256},
        "products": {name: _sha256(PACKAGES / name) for name in PRODUCTS},
    }


def _child_env(label_dir: Path, evidence_run: Path, label: str) -> dict[str, str]:
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


def _run(name: str, argv: list[str], env: dict[str, str], cwd: Path, artifacts: Path):
    started = _utc()
    proc = subprocess.Popen(
        argv,
        cwd=str(cwd),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    stdout, stderr = proc.communicate()
    ended = _utc()
    (artifacts / f"{name}.stdout").write_bytes(stdout)
    (artifacts / f"{name}.stderr").write_bytes(stderr)
    _write_json(
        artifacts / f"{name}.meta.json",
        {
            "name": name,
            "argv": [str(item) for item in argv],
            "cwd": str(cwd),
            "rc": proc.returncode,
            "pid": proc.pid,
            "started": started,
            "ended": ended,
            "stdout_bytes": len(stdout),
            "stderr_bytes": len(stderr),
        },
    )
    return proc.returncode, stdout.decode("utf-8", "replace"), stderr.decode(
        "utf-8", "replace"
    )


def _collected_ids(stdout: str) -> list[str]:
    ids: list[str] = []
    for line in stdout.splitlines():
        line = line.strip()
        if "::" in line:
            ids.append(line)
    return ids


def _base_node_id(node_id: str) -> str:
    tail = node_id.split("::")[-1]
    return tail.split("[")[0]


def _test_function_names(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [
        node.name
        for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name.startswith("test_")
    ]


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
            rows.append(json.loads(line))
        except ValueError:
            rows.append({"stage": "unparsable"})
    return rows


def _refuse(message: str, **extra: object) -> int:
    print(json.dumps({"status": "refused", "reason": message, **extra}, ensure_ascii=False, indent=2))
    return 3


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Guarded two-file pytest runner for T10 R2 stage A. Creates a fresh "
            "<fixture-root>/<label> tree, runs the guard self-control, the import "
            "probe, the collection listing and the assigned two suites, and keeps "
            "every raw artifact next to report.json."
        )
    )
    parser.add_argument("--fixture-root", required=True, help="approved PM fixture root")
    parser.add_argument("--label", required=True, help="unique run label (new directory name)")
    parser.add_argument(
        "--focus",
        action="store_true",
        help="additionally run only the added node ids (separate artifacts, same rc contract)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    label = args.label
    if LABEL_PATTERN.fullmatch(label) is None:
        return _refuse("the label must be one safe path component ([A-Za-z0-9][A-Za-z0-9._-]{0,63})")

    fixture_root = Path(os.path.abspath(args.fixture_root))
    approved_fixture = Path("C:/Users/wenbozhou/AppData/Local/Temp/dpc-t10-pm-verify-20261027/pm-verification")
    if fixture_root.resolve() != approved_fixture.resolve():
        return _refuse("the fixture root is outside the specific PM authorization")
    if not sys.dont_write_bytecode:
        return _refuse("the PM runner requires -B")
    fixture_root_created = False
    if fixture_root.exists():
        if not fixture_root.is_dir():
            return _refuse(
                "the fixture root exists but is not a directory",
                fixture_root=str(fixture_root),
            )
    else:
        # The approved OS root already exists; this creates only the named
        # PM-private sub-face once, exclusively. A label path is never reused.
        try:
            os.mkdir(fixture_root)
        except FileExistsError:
            return _refuse(
                "the fixture root appeared concurrently; refusing",
                fixture_root=str(fixture_root),
            )
        except OSError as exc:
            return _refuse(
                f"the fixture root could not be created ({type(exc).__name__}); the approved OS root must exist",
                fixture_root=str(fixture_root),
            )
        fixture_root_created = True
    resolved_fixture = fixture_root.resolve()
    if ".agenticdoc" in [part.lower() for part in resolved_fixture.parts]:
        return _refuse("the fixture root must stay outside the .agenticdoc tree")
    if resolved_fixture == WORKTREE or WORKTREE in resolved_fixture.parents:
        return _refuse("the fixture root must stay outside the isolated worktree")

    label_dir = resolved_fixture / label
    evidence_run = HERE / "runs" / label
    if label_dir.exists():
        return _refuse("the label directory already exists; it is never reused", path=str(label_dir))
    if evidence_run.exists():
        return _refuse("the evidence run directory already exists; it is never reused", path=str(evidence_run))

    try:
        os.mkdir(label_dir)
    except FileExistsError:
        return _refuse("the label directory appeared concurrently; refusing", path=str(label_dir))
    for name in ("home", "temp", "project", "pycache"):
        (label_dir / name).mkdir()
    evidence_run.mkdir(parents=True)

    artifacts = evidence_run
    env = _child_env(label_dir, evidence_run, label)
    problems: list[str] = []
    checks: dict[str, object] = {}

    _write_json(
        artifacts / "meta.json",
        {
            "observed_at": _utc(),
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
            "env_keys": sorted(env),
            "env_policy": "whitelist only; nothing inherited from the parent environment",
            "scripts": {
                name: {"sha256": _sha256(HERE / name), "bytes": (HERE / name).stat().st_size}
                for name in ("run_pm_tests.py", "sitecustomize.py", "guard_preflight.py", "probe_imports.py")
            },
        },
    )

    before = _protected_snapshot()
    _write_json(artifacts / "before.json", {"mirror_files": before["mirror_files"], "pyc": before["pyc"], "live": before["live"], "products": before["products"], "old_evidence_files": len(before["old_evidence"])})
    _write_json(artifacts / "mirror.before.json", before["mirror"])
    _write_json(artifacts / "old-evidence.before.json", before["old_evidence"])

    if before["mirror_files"] != EXPECTED_MIRROR_FILES:
        problems.append(f"the isolated mirror holds {before['mirror_files']} files (expected {EXPECTED_MIRROR_FILES})")
    if len(before["pyc"]) != EXPECTED_PYC_FILES:
        problems.append(f"{len(before['pyc'])} protected pyc files (expected {EXPECTED_PYC_FILES})")
    if len(before["old_evidence"]) != EXPECTED_OLD_EVIDENCE_FILES:
        problems.append(
            f"{len(before['old_evidence'])} old-evidence files (expected {EXPECTED_OLD_EVIDENCE_FILES})"
        )
    for name, expected in PRODUCTS.items():
        if before["products"].get(name) != expected:
            problems.append(f"the isolated {name} is not the frozen stage-A product")
    for name, expected in LIVE_SHA256.items():
        if before["live"].get(name) != expected:
            problems.append(f"the live {name} moved away from the protected bytes")
    audit = HERE.parent / "test-preparation" / "checks" / "verify_tests.result.json"
    if not audit.is_file():
        problems.append("stage-A audit is missing; no product stage is allowed")
    for name, expected in ASSIGNED_TEST_SHA256.items():
        if _sha256(PACKAGES / name) != expected:
            problems.append(f"{name} is not the immutable stage-A revision")
    if audit.is_file():
        audited = json.loads(audit.read_text(encoding="utf-8"))
        for name in ASSIGNED_TESTS:
            recorded = audited.get("checks", {}).get("files", {}).get(name, {}).get("current_sha256")
            current = _sha256(PACKAGES / name)
            if recorded and recorded != current:
                problems.append(f"{name} changed after the stage-A audit; re-audit before running")
            elif name in ASSIGNED_TEST_SHA256 and ASSIGNED_TEST_SHA256[name] != current:
                problems.append(f"{name} is not the audited revision")

    if problems:
        _write_json(artifacts / "report.json", {"status": "precondition-failed", "problems": problems})
        print(json.dumps({"status": "precondition-failed", "problems": problems}))
        return 2

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
    commands = {
        "guard_preflight": [sys.executable, "-B", str(HERE / "guard_preflight.py")],
        "import_probe": [sys.executable, "-B", str(HERE / "probe_imports.py"), str(PACKAGES)],
        "collect": [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q", "--collect-only", *ASSIGNED_TESTS],
        "pytest": pytest_argv,
        "focus": [
            sys.executable,
            "-B",
            "-m",
            "pytest",
            "-p",
            "no:cacheprovider",
            "-q",
            f"--basetemp={label_dir / 'pytest-basetemp-focus'}",
            *[f"{ASSIGNED_TESTS[0]}::{name}" for name in NEW_NODE_IDS],
        ],
    }

    # 1) guard self-control (child-side proof: refusals + inheritance + no creds)
    preflight_rc, preflight_out, preflight_err = _run(
        "guard-preflight", commands["guard_preflight"], env, label_dir / "project", artifacts
    )
    preflight: dict[str, object] = {}
    try:
        preflight = json.loads(preflight_out)
    except ValueError:
        problems.append("the guard preflight did not print JSON")
    (artifacts / "guard-preflight.json").write_text(
        json.dumps({"rc": preflight_rc, "stderr": preflight_err, "report": preflight}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    if preflight_rc != 0:
        problems.append(f"the guard preflight failed (rc={preflight_rc})")
    preflight_checks = preflight.get("checks", {}) if isinstance(preflight, dict) else {}
    for name in ("dns", "tcp", "udp", "non_python_child"):
        entry = preflight_checks.get(name, {}) if isinstance(preflight_checks, dict) else {}
        if not isinstance(entry, dict) or entry.get("refused") is not True or entry.get("guard_message") is not True:
            problems.append(f"the guard did not refuse {name} inside the child")
    if preflight_checks.get("credential_env_names") != []:
        problems.append("credential-shaped environment names reached the guarded child")
    if preflight_checks.get("python_child_pid") is None:
        problems.append("the guarded child could not spawn the python grandchild")

    if problems:
        _write_json(artifacts / "report.json", {"status": "preflight-failed", "problems": problems})
        print(json.dumps({"status": "preflight-failed", "problems": problems}))
        return 2

    # 2) import provenance (real interpreter, isolated tree, no cache/live stand-in)
    probe_rc, probe_out, probe_err = _run(
        "import-probe", commands["import_probe"], env, PACKAGES, artifacts
    )
    probe: dict[str, object] = {}
    try:
        probe = json.loads(probe_out)
    except ValueError:
        problems.append("the import probe did not print JSON")
    _write_json(artifacts / "imports.json", {"rc": probe_rc, "stderr": probe_err, "report": probe})
    if probe_rc != 0:
        problems.append(f"the import probe failed (rc={probe_rc})")
    if isinstance(probe, dict) and probe:
        if probe.get("dont_write_bytecode") is not True:
            problems.append("the import probe child did not run under -B")
        modules = probe.get("modules", {}) or {}
        tests = probe.get("test_modules", {}) or {}
        if not isinstance(modules, dict) or not isinstance(tests, dict):
            problems.append("the import probe reported an unexpected shape")
            modules, tests = {}, {}
        for name, entry in modules.items():
            raw = entry.get("file") if isinstance(entry, dict) else None
            if not isinstance(raw, str) or not raw:
                problems.append(f"{name} did not import")
                continue
            resolved = Path(raw).resolve()
            if PACKAGES not in resolved.parents:
                problems.append(f"{name} was imported from outside the isolated tree")
            if resolved == (LIVE / resolved.name) or LIVE in resolved.parents:
                problems.append(f"{name} was imported from the live repository")
            expected = _sha256(PACKAGES / resolved.name)
            if entry.get("sha256") != expected:
                problems.append(f"{name} did not import the current isolated bytes")
        for name, entry in tests.items():
            raw = entry.get("origin") if isinstance(entry, dict) else None
            if not isinstance(raw, str) or not raw:
                problems.append(f"{name} was not locatable")
                continue
            if PACKAGES not in Path(raw).resolve().parents:
                problems.append(f"{name} was located outside the isolated tree")
        for name in ("decision_lifecycle", "decision_wire", "decision_task_state"):
            entry = modules.get(name, {})
            expected = PRODUCTS[f"{name}.py"]
            if not isinstance(entry, dict) or entry.get("sha256") != expected:
                problems.append(f"{name} is not the frozen product revision")

    if problems:
        _write_json(artifacts / "report.json", {"status": "import-provenance-failed", "problems": problems})
        print(json.dumps({"status": "import-provenance-failed", "problems": problems}))
        return 2

    # 3) collection listing (the old items must all still be collected)
    collect_rc, collect_out, collect_err = _run(
        "collect", commands["collect"], env, PACKAGES, artifacts
    )
    collected = _collected_ids(collect_out)
    (artifacts / "collection.node-ids.txt").write_text(
        "\n".join(collected) + ("\n" if collected else ""), encoding="utf-8", newline="\n"
    )
    collected_bases = {_base_node_id(node) for node in collected}
    missing_functions: dict[str, list[str]] = {}
    for name in ASSIGNED_TESTS:
        declared = set(_test_function_names(PACKAGES / name))
        missing = sorted(declared - collected_bases)
        if missing:
            missing_functions[name] = missing
            problems.append(f"{name} lost collected test functions: {missing}")
    if collect_rc != 0:
        problems.append(f"the collection listing failed (rc={collect_rc})")
    original_ids = (HERE.parent / "pm-controlled/runs/t10-r2-red-controls-20261028T064853Z/collection.node-ids.txt").read_text(encoding="utf-8").splitlines()
    if set(original_ids) != set(collected) or len(original_ids) != len(collected):
        problems.append("the immutable original 130 collected items changed")
    if len(collected) < EXISTING_ITEM_FLOOR:
        problems.append(f"only {len(collected)} items were collected (floor {EXISTING_ITEM_FLOOR})")
    missing_new = sorted(set(NEW_NODE_IDS) - collected_bases)
    if missing_new:
        problems.append(f"the stage-A regressions are not collected: {missing_new}")

    if problems:
        _write_json(artifacts / "report.json", {"status": "collection-failed", "problems": problems})
        print(json.dumps({"status": "collection-failed", "problems": problems}))
        return 2

    # 4) the required two-file run
    pytest_rc, pytest_out, pytest_err = _run(
        "pytest", pytest_argv, env, PACKAGES, artifacts
    )
    summary = _parse_summary(pytest_out)
    (artifacts / "pytest.summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    failed_bases = {_base_node_id(node) for node in summary["failed_node_ids"]}
    if "failed" not in summary["counts"] and pytest_rc != 0:
        problems.append("pytest returned a non-zero code without a parsed failure line")

    # 5) optional focused run over the added node ids
    focus: dict[str, object] | None = None
    if args.focus:
        focus_rc, focus_out, focus_err = _run(
            "focus", commands["focus"], env, PACKAGES, artifacts
        )
        focus = {
            "rc": focus_rc,
            "summary": _parse_summary(focus_out),
            "stderr_chars": len(focus_err),
        }
        _write_json(artifacts / "focus.json", focus)

    # 6) after snapshot + protection diff
    after = _protected_snapshot()
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
        "live": {"before": before["live"], "after": after["live"], "unchanged": before["live"] == after["live"]},
        "products": {
            "expected": PRODUCTS,
            "before": before["products"],
            "after": after["products"],
            "unchanged": before["products"] == after["products"],
        },
    }
    checks["protection"] = protection
    for name in ("mirror", "old_evidence"):
        diff = protection[name]["diff"]
        if diff["added"] or diff["removed"] or diff["changed"]:
            problems.append(f"the {name} tree changed during the run: {diff}")
    if protection["pyc"]["diff"]["added"] or protection["pyc"]["diff"]["removed"] or protection["pyc"]["diff"]["changed"]:
        problems.append(f"a protected pyc changed during the run: {protection['pyc']['diff']}")
    if not protection["live"]["unchanged"]:
        problems.append("a live product file changed during the run")
    if not protection["products"]["unchanged"]:
        problems.append("an isolated product file changed during the run")

    # 7) per-child guard sentinel audit
    sentinel = _sentinel_rows(artifacts / "guard-sentinel.jsonl")
    sentinel_by_pid: dict[int, dict[str, object]] = {}
    for row in sentinel:
        pid = row.get("pid")
        if not isinstance(pid, int):
            continue
        entry = sentinel_by_pid.setdefault(pid, {"stages": [], "network_denied": 0, "subprocess_denied": 0, "run": row.get("run")})
        stages = entry["stages"]
        if isinstance(stages, list) and row.get("stage") not in stages:
            stages.append(row.get("stage"))
        if row.get("stage") == "network-denied":
            entry["network_denied"] = int(entry["network_denied"]) + 1
        if row.get("stage") == "subprocess-denied":
            entry["subprocess_denied"] = int(entry["subprocess_denied"]) + 1
    command_pids = {}
    for command in ("guard-preflight", "import-probe", "collect", "pytest", "focus"):
        meta_path = artifacts / f"{command}.meta.json"
        if not meta_path.exists():
            continue
        command_pid = json.loads(meta_path.read_text(encoding="utf-8"))["pid"]
        command_pids[command] = command_pid
        entry = sentinel_by_pid.get(command_pid, {})
        if not {"import", "guard-installed"}.issubset(set(entry.get("stages", []))):
            problems.append(f"{command} child pid has no installed guard sentinel")
    for row in sentinel:
        if row.get("stage") == "unparsable" or row.get("dont_write_bytecode") is not True:
            problems.append("a malformed or non-B child guard sentinel exists")
        if row.get("stage") == "guard-installed" and row.get("credential_env_names") != []:
            problems.append("credential-shaped names reached a guarded child")
    checks["command_pids"] = command_pids
    wrong_run = sorted(pid for pid, entry in sentinel_by_pid.items() if entry.get("run") != label)
    if wrong_run:
        problems.append(f"guard sentinels carry another run label: {wrong_run[:5]}")
    preflight_pid = preflight.get("pid") if isinstance(preflight, dict) else None
    preflight_entry = sentinel_by_pid.get(preflight_pid) if isinstance(preflight_pid, int) else None
    if not preflight_entry:
        problems.append("no guard sentinel exists for the preflight child")
    else:
        stages = preflight_entry.get("stages") or []
        if "import" not in stages or "guard-installed" not in stages:
            problems.append("the preflight child did not record the guard stages")
        if int(preflight_entry.get("network_denied", 0)) < 3:
            problems.append("the preflight child did not record its network refusals")
        if int(preflight_entry.get("subprocess_denied", 0)) < 1:
            problems.append("the preflight child did not record its subprocess refusal")
        grandchild_pid = preflight_checks.get("python_child_pid") if isinstance(preflight_checks, dict) else None
        grandchild = sentinel_by_pid.get(grandchild_pid) if isinstance(grandchild_pid, int) else None
        if not grandchild:
            problems.append("the python grandchild left no guard sentinel (guard not inherited)")
    checks["guard"] = {
        "children_seen": sorted(sentinel_by_pid),
        "preflight_pid": preflight_pid,
        "sentinels": {str(pid): entry for pid, entry in sorted(sentinel_by_pid.items())},
        "total_sentinel_lines": len(sentinel),
    }

    expected_red_observed = sorted(set(EXPECTED_RED_NODE_IDS) & failed_bases)
    expected_red_missing = sorted(set(EXPECTED_RED_NODE_IDS) - failed_bases)
    unexpected_failures = sorted(failed_bases - set(EXPECTED_RED_NODE_IDS))

    report = {
        "observed_at": _utc(),
        "status": "executed" if not problems else "harness-failed",
        "label": label,
        "fixture_root": str(resolved_fixture),
        "fixture_root_created": fixture_root_created,
        "label_dir": str(label_dir),
        "evidence_run": str(evidence_run),
        "env_keys": sorted(env),
        "commands": commands,
        "rc": {"guard_preflight": preflight_rc, "import_probe": probe_rc, "collect": collect_rc, "pytest": pytest_rc},
        "collection": {
            "count": len(collected),
            "existing_floor": EXISTING_ITEM_FLOOR,
            "new_node_ids_present": not missing_new,
            "missing_new_node_ids": missing_new,
            "lost_test_functions": missing_functions,
            "node_ids_file": "collection.node-ids.txt",
        },
        "pytest": {
            "summary_line": summary["last_line"],
            "counts": summary["counts"],
            "failed_node_ids": summary["failed_node_ids"],
            "stdout_file": "pytest.stdout",
            "stderr_file": "pytest.stderr",
            "meta_file": "pytest.meta.json",
        },
        "focus": focus,
        "expected_red": {
            "items": 8,
            "observed": expected_red_observed,
            "missing": expected_red_missing,
            "unexpected_failures": unexpected_failures,
            "note": (
                "S1/S3/S5/S7/S4 regressions are expected red before the product fix and green "
                "after it; the controls stay green in both runs"
            ),
        },
        "guard_preflight": {
            "rc": preflight_rc,
            "checks": preflight_checks,
            "file": "guard-preflight.json",
        },
        "imports": {"file": "imports.json", "packages_dir": str(PACKAGES)},
        "protection": protection,
        "checks": checks,
        "problems": problems,
        "network_claim": (
            "the guard was installed in every python child and refused DNS/TCP/UDP in the "
            "self-control; there is no packet capture, so this is not a proof about the OS stack"
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
                "counts": summary["counts"],
                "expected_red_observed": expected_red_observed,
                "expected_red_missing": expected_red_missing,
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
    if pytest_rc != 0:
        return pytest_rc
    return focus["rc"] if focus is not None else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
