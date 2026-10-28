"""Run the two T03 pytest files in a minimal, isolated environment.

usage: python run_tests.py <label> [pytest extra args...]

Writes <label>.log in this evidence dir with argv/cwd/rc/stdout/stderr.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
KEY = EVIDENCE.parents[3]
PACKAGE = KEY / "implementation-worktree" / "packages" / "multi-workers"
ISOLATED = EVIDENCE / "isolated"


def main() -> int:
    label = sys.argv[1]
    extra = sys.argv[2:]
    for name in ("home", "project", "temp"):
        (ISOLATED / name).mkdir(parents=True, exist_ok=True)
    env = {
        key: os.environ[key]
        for key in ("PATH", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "PATHEXT")
        if key in os.environ
    }
    env.update(
        {
            "HOME": str(ISOLATED / "home"),
            "USERPROFILE": str(ISOLATED / "home"),
            "APPDATA": str(ISOLATED / "home"),
            "LOCALAPPDATA": str(ISOLATED / "home"),
            "TEMP": str(ISOLATED / "temp"),
            "TMP": str(ISOLATED / "temp"),
            "TMPDIR": str(ISOLATED / "temp"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
    )
    # Strip every inherited provider/worker/project variable: only the allowlist above survives.
    argv = [
        sys.executable,
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
        *extra,
        "test_decide_registry_contract.py",
        "test_dp_consolidation_registry.py",
    ]
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
        f"cwd={PACKAGE}\n"
        f"argv={argv}\n"
        f"env_keys={sorted(env)}\n"
        f"rc={completed.returncode}\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}\n"
    )
    (EVIDENCE / f"{label}.log").write_text(log, encoding="utf-8")
    print(log)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
