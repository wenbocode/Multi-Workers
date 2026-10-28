"""T06 evidence runner: the assigned test file in a minimal, isolated env.

- cwd: the isolated copy's ``packages/multi-workers`` so every import binds
  ``__file__`` inside the implementation worktree, never the live repo;
- env built from scratch (PATH/SYSTEMROOT/... only) plus isolated
  HOME/USERPROFILE/TEMP/TMP under this card's evidence dir; provider, worker,
  project and decision config variables are not inherited;
- ``PYTHONDONTWRITEBYTECODE=1`` + ``PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`` and
  ``-p no:cacheprovider`` (no pycache, no third-party plugins, no cache);
- the full stdout/stderr/rc are written to ``<label>.log`` here, so the red and
  green runs are evidence rather than a claim.

Usage: python run_pytest.py <label> [pytest args...]
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
WORKTREE = EVIDENCE.parents[2] / "implementation-worktree"
PACKAGE = WORKTREE / "packages" / "multi-workers"
ISOLATED = EVIDENCE / "isolated"
TEST = "test_dp_consolidation_concurrency.py"

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
    extra = sys.argv[2:]
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
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
    ]
    if "-v" not in extra:
        argv.append("-q")
    argv.append(TEST)
    argv.extend(extra)
    completed = subprocess.run(
        argv,
        cwd=PACKAGE,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    probe = {
        "test_file": str(PACKAGE / TEST),
        "test_exists": (PACKAGE / TEST).is_file(),
        "module_file": str(PACKAGE / "decision_validity.py"),
        "module_exists": (PACKAGE / "decision_validity.py").is_file(),
        "cwd": str(PACKAGE),
        "argv": argv,
        "rc": completed.returncode,
    }
    log = (
        f"# label: {label}\n"
        f"# cwd: {PACKAGE}\n"
        f"# argv: {argv}\n"
        f"# env: isolated home={home} project={project} temp={temp}; "
        "PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 -p no:cacheprovider\n"
        f"# probe: {probe}\n"
        f"# rc: {completed.returncode}\n"
        f"## stdout\n{completed.stdout}\n## stderr\n{completed.stderr}\n"
    )
    (EVIDENCE / f"{label}.log").write_text(log, encoding="utf-8")
    print(log)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
