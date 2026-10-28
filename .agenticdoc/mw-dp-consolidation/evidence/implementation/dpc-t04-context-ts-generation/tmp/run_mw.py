"""Run a python script inside the worktree/multi-workers with a minimal env.

Usage: python run_mw.py <label> <script.py> [args...]

The script path is resolved against the worktree multi-workers package unless it
is absolute. stdout/stderr/rc land in <label>.log next to the other logs.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(r"H:\git\Multi-Workers")
WT = REPO / ".agenticdoc/mw-dp-consolidation/implementation-worktree"
EVID = REPO / ".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-t04-context-ts-generation"
LOGS = EVID / "logs"
FIXTURE = EVID / "fixture"
MW = WT / "packages/multi-workers"


def main(argv: list[str]) -> int:
    label, script, *extra = argv
    logs = LOGS
    logs.mkdir(parents=True, exist_ok=True)
    home, temp, project = FIXTURE / "home", FIXTURE / "temp", FIXTURE / "project"
    for path in (home, temp, project):
        path.mkdir(parents=True, exist_ok=True)
    env = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONUTF8": "1",
        "HOME": str(home),
        "USERPROFILE": str(home),
        "TEMP": str(temp),
        "TMP": str(temp),
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
        "COMSPEC": os.environ.get("COMSPEC", ""),
    }
    cmd = [sys.executable, script, *extra]
    started = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(
        cmd,
        cwd=str(MW),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    body = (
        f"# command: {cmd}\n# cwd: {MW}\n# started: {started}\n# rc: {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}\n"
    )
    (logs / f"{label}.log").write_text(body, encoding="utf-8", newline="\n")
    print(f"{label}: rc={proc.returncode}")
    if proc.stdout:
        print(proc.stdout[:3000])
    if proc.stderr:
        print("STDERR:", proc.stderr[:3000])
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
