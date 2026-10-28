"""T10 isolated test runner: minimal env, private HOME, OS-private TEMP, no pyc/cache/plugins.

Usage: python -B run_tests.py <label>

Runs the two card-owned test files inside the isolated worktree, with the
absolute worktree path as cwd, and writes ``<label>.stdout`` / ``<label>.stderr``
/ ``<label>.rc`` / ``<label>.meta.json`` next to this script. It never writes
into the worktree, the live repo or any pytest cache.

TEMP placement note: the card asks for fixture TEMP under this evidence dir, but
``decision_lifecycle.LifecycleStore.test`` correctly refuses any sink path that
resolves inside ``.agenticdoc`` (test-scope guard). ``tmp_path`` therefore lives
in a dedicated OS temp directory outside the repo; HOME/project fixtures stay in
``<evidence>/fixture`` and no production path is touched.
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile

HERE = pathlib.Path(__file__).resolve().parent
WORKTREE_ROOT = HERE.parents[2] / "implementation-worktree"
PKG = (WORKTREE_ROOT / "packages" / "multi-workers").resolve()
LIVE_PKG = (HERE.parents[4] / "packages" / "multi-workers").resolve()
FILES = ("test_decision_context_lifecycle.py", "test_decision_task_state.py")


def main(argv: list[str]) -> int:
    label = argv[1] if len(argv) > 1 else "run"
    target = argv[2] if len(argv) > 2 else "worktree"
    pkg = PKG if target == "worktree" else LIVE_PKG
    fixture = HERE / "fixture"
    home = fixture / "home"
    project = fixture / "project"
    home.mkdir(parents=True, exist_ok=True)
    project.mkdir(parents=True, exist_ok=True)
    temp_root = pathlib.Path(tempfile.gettempdir()) / "dpc-t10-lifecycle-state" / label
    basetemp = temp_root / "pytest-basetemp"
    for path in (temp_root, basetemp):
        path.mkdir(parents=True, exist_ok=True)

    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONUTF8": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "HOME": str(home),
        "USERPROFILE": str(home),
        "TEMP": str(temp_root),
        "TMP": str(temp_root),
        "XDG_CACHE_HOME": str(temp_root / "cache"),
        "PYTHONPYCACHEPREFIX": str(temp_root / "pycache"),
    }
    argv_out = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
    ]
    if len(argv) <= 3:
        argv_out += ["--basetemp", str(basetemp)]
    argv_out += list(FILES)
    completed = subprocess.run(
        argv_out,
        cwd=str(pkg),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (HERE / f"{label}.stdout").write_text(completed.stdout, encoding="utf-8", newline="\n")
    (HERE / f"{label}.stderr").write_text(completed.stderr, encoding="utf-8", newline="\n")
    (HERE / f"{label}.rc").write_text(f"{completed.returncode}\n", encoding="utf-8", newline="\n")
    meta = {
        "label": label,
        "target": target,
        "argv": argv_out,
        "cwd": str(pkg),
        "cwd_is_worktree": str(pkg).startswith(str(WORKTREE_ROOT.resolve())),
        "cwd_is_live_repo": str(pkg) == str(LIVE_PKG),
        "python": sys.version,
        "executable": sys.executable,
        "env_keys": sorted(env),
        "rc": completed.returncode,
        "home": str(home),
        "temp_root": str(temp_root),
        "basetemp": str(basetemp),
        "tmp_outside_agenticdoc": ".agenticdoc" not in str(temp_root),
    }
    (HERE / f"{label}.meta.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    print(json.dumps({"label": label, "rc": completed.returncode}, ensure_ascii=False))
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
