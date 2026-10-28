"""Minimal-environment runner for the single assigned T06 suite (R2).

Runs exactly ``python -B -m pytest -p no:cacheprovider -q
test_dp_consolidation_concurrency.py`` inside the isolated implementation copy
with an explicit, minimal child environment (private HOME/USERPROFILE/TEMP,
UTF-8, no bytecode, no pytest plugin autoload, no pytest cache). No network, no
provider, no CLI, no live object.

Usage: python -B envrun.py <label>
Writes <label>.stdout / <label>.stderr / <label>.rc next to this script.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys

FIXTURE = pathlib.Path(__file__).resolve().parent
EVIDENCE = FIXTURE.parent
COPY_ROOT = (
    EVIDENCE.parents[3] / "implementation-worktree" / "packages" / "multi-workers"
)
TARGET = "test_dp_consolidation_concurrency.py"

HOME = FIXTURE / "home"
TMP = FIXTURE / "tmp"
PROJECT = FIXTURE / "project"


def child_env() -> dict[str, str]:
    for directory in (HOME, TMP, PROJECT):
        directory.mkdir(parents=True, exist_ok=True)
    keep = {
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", r"C:\Windows"),
        "SYSTEMDRIVE": os.environ.get("SYSTEMDRIVE", "C:"),
        "WINDIR": os.environ.get("WINDIR", r"C:\Windows"),
        "PATH": os.environ.get("PATH", ""),
        "PATHEXT": os.environ.get("PATHEXT", ".COM;.EXE;.BAT;.CMD"),
        "COMSPEC": os.environ.get("COMSPEC", r"C:\Windows\System32\cmd.exe"),
    }
    keep.update(
        {
            "HOME": str(HOME),
            "USERPROFILE": str(HOME),
            "TEMP": str(TMP),
            "TMP": str(TMP),
            "APPDATA": str(HOME / "AppData"),
            "LOCALAPPDATA": str(HOME / "AppData" / "Local"),
            "PROJECT_ROOT": str(PROJECT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUTF8": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONPYCACHEPREFIX": "",
            "PYTHONNOUSERSITE": "1",
            "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
            "LANG": "C.UTF-8",
            "LC_ALL": "C.UTF-8",
            "TZ": "UTC",
        }
    )
    return keep


def main(argv: list[str]) -> int:
    label = argv[1] if len(argv) > 1 else "run"
    command = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
        TARGET,
    ]
    completed = subprocess.run(
        command,
        cwd=str(COPY_ROOT),
        env=child_env(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    (EVIDENCE / f"{label}.stdout").write_text(completed.stdout, encoding="utf-8")
    (EVIDENCE / f"{label}.stderr").write_text(completed.stderr, encoding="utf-8")
    (EVIDENCE / f"{label}.rc").write_text(f"{completed.returncode}\n", encoding="utf-8")
    print(f"label={label} rc={completed.returncode} cwd={COPY_ROOT}")
    print(completed.stdout.strip())
    if completed.stderr.strip():
        print("STDERR:", completed.stderr.strip())
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
