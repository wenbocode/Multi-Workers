"""Run probe_r3.py under the same minimal isolated environment as the tests."""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

EVIDENCE = pathlib.Path(__file__).resolve().parent
ISOLATED = EVIDENCE / "isolated"


def main() -> int:
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
    argv = [sys.executable, str(EVIDENCE / "probe_r3.py")]
    completed = subprocess.run(
        argv,
        cwd=EVIDENCE,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    log = (
        f"cwd={EVIDENCE}\n"
        f"argv={argv}\n"
        f"env_keys={sorted(env)}\n"
        f"rc={completed.returncode}\n"
        f"stdout:\n{completed.stdout}\n"
        f"stderr:\n{completed.stderr}\n"
    )
    (EVIDENCE / "probe-r3.log").write_text(log, encoding="utf-8")
    print(f"rc={completed.returncode}")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
