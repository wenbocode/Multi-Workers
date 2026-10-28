"""Run the single assigned pytest file in a private minimal UTF-8 environment.

argv: run-tests.py <label>
Writes <label>.stdout/.stderr/.rc.json under this evidence dir and prints rc.

Isolation: no inherited PYTHON* / plugin env, plugin autoload disabled, no pytest
cache, no bytecode, private HOME/USERPROFILE/TEMP/TMP/TMPDIR and fixture root
inside this rework-r2 directory. cwd is the implementation copy only.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
KEY = HERE.parents[3]
PKG = KEY / "implementation-worktree" / "packages" / "multi-workers"


def main() -> int:
    label = sys.argv[1]
    fixture = HERE / f"fixture-{label}"
    env = {k: os.environ[k] for k in ("PATH", "SYSTEMROOT", "WINDIR") if k in os.environ}
    env.update(
        {
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
            "DPC_T07_FIXTURE_ROOT": str(fixture),
        }
    )
    for name in ("HOME", "USERPROFILE", "TEMP", "TMP", "TMPDIR"):
        target = fixture / "process-env" / name.lower()
        target.mkdir(parents=True, exist_ok=True)
        env[name] = str(target)
    argv = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
        "test_dp_consolidation_recovery.py",
    ]
    started = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(argv, cwd=PKG, env=env, capture_output=True)
    (HERE / f"{label}.stdout").write_bytes(proc.stdout)
    (HERE / f"{label}.stderr").write_bytes(proc.stderr)
    record = {
        "label": label,
        "argv": argv,
        "cwd": str(PKG),
        "env_keys": sorted(env),
        "started_at": started,
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "rc": proc.returncode,
        "stdout_bytes": len(proc.stdout),
        "stderr_bytes": len(proc.stderr),
    }
    (HERE / f"{label}.rc.json").write_text(
        json.dumps(record, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(record, indent=2))
    sys.stdout.write(proc.stdout.decode("utf-8", "replace"))
    sys.stderr.write(proc.stderr.decode("utf-8", "replace"))
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
