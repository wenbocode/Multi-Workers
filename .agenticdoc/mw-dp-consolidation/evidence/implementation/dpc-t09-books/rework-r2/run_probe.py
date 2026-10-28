"""R2 evidence runner for the independent probe in a minimal private env.

Usage: python -B run_probe.py <label> [book-module-dir]

Rebuilds the child env from scratch (private HOME/USERPROFILE/TEMP inside this
R2 fixture, PYTHONDONTWRITEBYTECODE=1, no inherited provider/worker config) and
saves probe-<label>.stdout/.stderr/.rc under runs/.
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
extra = sys.argv[2:]
home = HERE / "fixture" / "home"
tmp = HERE / "fixture" / "tmp"
for directory in (home, tmp):
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
    "LANG": "C.UTF-8",
    "LC_ALL": "C.UTF-8",
}

argv = [sys.executable, "-B", str(HERE / "probe_r2.py"), label, *extra]
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
(runs / f"probe-{label}.stdout").write_text(proc.stdout, encoding="utf-8", newline="\n")
(runs / f"probe-{label}.stderr").write_text(proc.stderr, encoding="utf-8", newline="\n")
(runs / f"probe-{label}.rc").write_text(f"{proc.returncode}\n", encoding="utf-8", newline="\n")
(runs / f"probe-{label}.argv.json").write_text(
    json.dumps(
        {"argv": argv, "cwd": str(PKG), "env": {k: env[k] for k in sorted(env)}, "rc": proc.returncode},
        ensure_ascii=False,
        indent=2,
    )
    + "\n",
    encoding="utf-8",
    newline="\n",
)
print(f"label=probe-{label} rc={proc.returncode}")
print(proc.stdout[:2000])
if proc.stderr:
    print("STDERR:")
    print(proc.stderr[:4000])
raise SystemExit(proc.returncode)
