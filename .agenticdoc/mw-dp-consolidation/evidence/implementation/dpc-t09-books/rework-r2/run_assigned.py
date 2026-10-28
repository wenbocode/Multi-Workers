"""R2 evidence runner: assigned pytest file in a minimal private environment.

Usage: python -B run_assigned.py <label>

Saves <label>.stdout / <label>.stderr / <label>.rc under rework-r2/runs/ and
returns the subprocess rc. Never inherits provider/worker/project config: the
child env is rebuilt from scratch (only Windows-required keys plus a private
HOME/USERPROFILE/TEMP inside this R2 fixture).
"""
from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys

assert sys.dont_write_bytecode

HERE = pathlib.Path(__file__).resolve().parent
KEY = HERE.parents[3]
PKG = KEY / "implementation-worktree" / "packages" / "multi-workers"

label = sys.argv[1]
basetemp = HERE / "fixture" / f"basetemp-{label}"
home = HERE / "fixture" / "home"
tmp = HERE / "fixture" / "tmp"
for directory in (basetemp, home, tmp):
    directory.mkdir(parents=True, exist_ok=True)

system_root = os.environ.get("SystemRoot", r"C:\Windows")
env = {
    "PATH": str(pathlib.Path(sys.executable).parent),
    "SystemRoot": system_root,
    "SystemDrive": os.environ.get("SystemDrive", "C:"),
    "WINDIR": system_root,
    "COMSPEC": os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
    "TEMP": str(tmp),
    "TMP": str(tmp),
    "HOME": str(home),
    "USERPROFILE": str(home),
    "PYTHONPATH": str(PKG),
    "PYTHONDONTWRITEBYTECODE": "1",
    "PYTHONUTF8": "1",
    "PYTHONIOENCODING": "utf-8",
    "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
}

argv = [
    sys.executable,
    "-B",
    "-m",
    "pytest",
    "-p",
    "no:cacheprovider",
    "-q",
    "test_decision_context_contract.py",
    "--basetemp",
    str(basetemp),
]
proc = subprocess.run(
    argv,
    cwd=str(PKG),
    env=env,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)

runs = HERE / "runs"
runs.mkdir(parents=True, exist_ok=True)
(runs / f"{label}.stdout").write_text(proc.stdout, encoding="utf-8", newline="\n")
(runs / f"{label}.stderr").write_text(proc.stderr, encoding="utf-8", newline="\n")
(runs / f"{label}.rc").write_text(f"{proc.returncode}\n", encoding="utf-8", newline="\n")
(runs / f"{label}.argv.json").write_text(
    json.dumps(
        {
            "argv": argv,
            "cwd": str(PKG),
            "env": {key: env[key] for key in sorted(env)},
            "rc": proc.returncode,
        },
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
    newline="\n",
)

print(f"label={label} rc={proc.returncode}")
print(proc.stdout[-4000:])
if proc.stderr:
    print("STDERR:")
    print(proc.stderr[-4000:])
raise SystemExit(proc.returncode)
