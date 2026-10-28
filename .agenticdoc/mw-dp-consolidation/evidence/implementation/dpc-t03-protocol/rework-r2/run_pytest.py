"""T03-R2 evidence runner: the two card test files in a minimal, isolated env.

Same isolation contract as the original T03 runner, but rooted in this card's
own evidence dir:

- cwd: the isolated copy's ``packages/multi-workers`` (imports bind ``__file__``
  there, never the source repo);
- env: built from scratch (PATH/SYSTEMROOT/... only) plus isolated
  HOME/USERPROFILE/TEMP/TMP under ``rework-r2/isolated``; provider, worker,
  project and decision config variables are not inherited;
- ``PYTHONDONTWRITEBYTECODE=1`` and ``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`` with
  ``-p no:cacheprovider`` (no pycache, no third-party plugins, no cache);
- full stdout/stderr and rc are written to ``<label>.log`` next to this script.

Usage: ``python run_pytest.py <label> [test_file ...]`` (defaults to the two
card files).
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
WORKTREE = EVIDENCE.parents[3] / "implementation-worktree"
PACKAGE = WORKTREE / "packages" / "multi-workers"
ISOLATED = EVIDENCE / "isolated"
TESTS = ("test_decide_registry_contract.py", "test_dp_consolidation_registry.py")

PASSTHROUGH = (
    "PATH",
    "SYSTEMROOT",
    "SYSTEMDRIVE",
    "WINDIR",
    "COMSPEC",
    "PATHEXT",
    "PROGRAMDATA",
    "PROGRAMFILES",
    "APPDATA",
    "LOCALAPPDATA",
    "NUMBER_OF_PROCESSORS",
    "PROCESSOR_ARCHITECTURE",
)


def main() -> int:
    label = sys.argv[1] if len(sys.argv) > 1 else "pytest"
    tests = tuple(sys.argv[2:]) or TESTS
    home = ISOLATED / "home"
    project = ISOLATED / "project"
    temp = ISOLATED / "temp"
    for path in (home, project, temp):
        path.mkdir(parents=True, exist_ok=True)
    env = {name: os.environ[name] for name in PASSTHROUGH if name in os.environ}
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "TEMP": str(temp),
            "TMP": str(temp),
            "TMPDIR": str(temp),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
    )
    argv = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", *tests]
    completed = subprocess.run(
        argv,
        cwd=PACKAGE,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    log = (
        f"# label: {label}\n"
        f"# cwd: {PACKAGE}\n"
        f"# argv: {argv}\n"
        f"# env: isolated home={home} project={project} temp={temp}; "
        "PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 -p no:cacheprovider\n"
        f"# rc: {completed.returncode}\n"
        f"## stdout\n{completed.stdout}\n## stderr\n{completed.stderr}\n"
    )
    (EVIDENCE / f"{label}.log").write_text(log, encoding="utf-8")
    print(log)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
