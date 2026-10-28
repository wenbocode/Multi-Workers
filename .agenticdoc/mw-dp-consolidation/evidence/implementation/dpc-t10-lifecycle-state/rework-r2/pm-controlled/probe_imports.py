"""Import provenance probe: the interpreter reports which files it really resolved.

Executed by ``run_pm_tests.py`` in a guarded child whose ``sys.path`` is anchored
on the isolated implementation tree. It imports the product modules through the
same interpreter that will import them during the pytest run, so a stale
``__pycache__`` entry or a live-repository module cannot stand in silently: the
runner compares every reported ``__file__``/``__cached__``/sha256 with the bytes
of the isolated tree it snapshotted itself.

The two assigned test modules are located with ``find_spec`` only, so this probe
never executes test-module code. ``sys.dont_write_bytecode`` is reported as the
proof that the child ran under ``-B``.
"""
from __future__ import annotations

import hashlib
import importlib
import importlib.util
import json
import os
import sys

PRODUCT_MODULES = (
    "decision",
    "decision_backends",
    "decision_points",
    "decision_lifecycle",
    "decision_wire",
    "decision_task_state",
    "decision_history",
    "decision_context",
    "decision_book",
)
TEST_MODULES = (
    "test_decision_context_lifecycle",
    "test_decision_task_state",
)


def _sha256(path: str) -> str:
    with open(path, "rb") as handle:
        return hashlib.sha256(handle.read()).hexdigest()


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print(json.dumps({"error": "usage: probe_imports.py <packages dir>"}))
        return 2
    packages_dir = os.path.abspath(argv[1])
    sys.path.insert(0, packages_dir)
    importlib.invalidate_caches()

    report: dict[str, object] = {
        "packages_dir": packages_dir,
        "cwd": os.getcwd(),
        "executable": sys.executable,
        "python": sys.version,
        "dont_write_bytecode": bool(sys.dont_write_bytecode),
        "sys_path": list(sys.path),
        "modules": {},
        "test_modules": {},
    }

    modules: dict[str, object] = report["modules"]  # type: ignore[assignment]
    for name in PRODUCT_MODULES:
        module = importlib.import_module(name)
        raw = getattr(module, "__file__", None)
        entry: dict[str, object] = {
            "file": os.path.realpath(raw) if raw else None,
            "cached": getattr(module, "__cached__", None),
        }
        if raw and os.path.exists(raw):
            entry["sha256"] = _sha256(raw)
        modules[name] = entry

    tests: dict[str, object] = report["test_modules"]  # type: ignore[assignment]
    for name in TEST_MODULES:
        spec = importlib.util.find_spec(name)
        origin = spec.origin if spec is not None else None
        entry = {"origin": os.path.realpath(origin) if origin else None}
        if origin and os.path.exists(origin):
            entry["sha256"] = _sha256(origin)
        tests[name] = entry

    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
