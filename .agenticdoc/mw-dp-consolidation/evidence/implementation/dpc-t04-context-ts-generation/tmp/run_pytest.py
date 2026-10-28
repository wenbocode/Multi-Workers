"""Run one card-listed pytest file in the isolated worktree with a minimal env.

Usage: python run_pytest.py <label> <test-file> [extra pytest args...]

Writes <label>.log (stdout+stderr, rc) into the card evidence logs dir and
prints a one-line summary. Never inherits provider/worker/project config: the
child env is built from scratch with a private HOME/TEMP under the card
evidence dir.
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
    label, test_file, *extra = argv
    logs = LOGS
    logs.mkdir(parents=True, exist_ok=True)
    home = FIXTURE / "home"
    temp = FIXTURE / "temp"
    project = FIXTURE / "project"
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
    cmd = [sys.executable, "-m", "pytest", "-p", "no:cacheprovider", "-q", test_file, *extra]
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
        f"# command: {' '.join(cmd)}\n"
        f"# cwd: {MW}\n"
        f"# env: PYTHONDONTWRITEBYTECODE=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 "
        f"HOME/TEMP under card evidence fixture\n"
        f"# started: {started}\n"
        f"# rc: {proc.returncode}\n"
        f"--- stdout ---\n{proc.stdout}\n--- stderr ---\n{proc.stderr}\n"
    )
    (logs / f"{label}.log").write_text(body, encoding="utf-8", newline="\n")
    (logs / f"{label}.json").write_text(
        json.dumps(
            {
                "label": label,
                "argv": cmd,
                "cwd": str(MW),
                "started": started,
                "finished": datetime.now(timezone.utc).isoformat(),
                "rc": proc.returncode,
                "stdout_tail": proc.stdout.strip().splitlines()[-25:],
                "stderr_tail": proc.stderr.strip().splitlines()[-25:],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"{label}: rc={proc.returncode}")
    tail = (proc.stdout + proc.stderr).strip().splitlines()
    for line in tail[-15:]:
        print("  " + line)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
