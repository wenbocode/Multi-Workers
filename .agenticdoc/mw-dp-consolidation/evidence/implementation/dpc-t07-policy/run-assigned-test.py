"""Run the assigned T07 pytest file under a minimal isolated environment.

No plugin autoload, no pycache, no pytest cache, HOME/TEMP/project pinned to
this card's evidence dir. Only the card-listed test file is executed.

Usage: python -B run-assigned-test.py <tag> [extra pytest args...]
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
PKG = HERE.parents[2] / "implementation-worktree" / "packages" / "multi-workers"
FIXTURE = HERE / "fixture"


def main(argv: list[str]) -> int:
    tag = argv[0]
    extra = argv[1:]
    env = {
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1",
        "PYTHONIOENCODING": "utf-8",
        "PYTHONHASHSEED": "0",
        "HOME": str(FIXTURE / "home"),
        "USERPROFILE": str(FIXTURE / "home"),
        "TMPDIR": str(FIXTURE / "tmp"),
        "TEMP": str(FIXTURE / "tmp"),
        "TMP": str(FIXTURE / "tmp"),
        "DPC_T07_FIXTURE_ROOT": str(FIXTURE),
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "WINDIR": os.environ.get("WINDIR", ""),
    }
    for name in ("TMPDIR", "TEMP", "TMP", "HOME"):
        env_path = pathlib.Path(env[name])
        env_path.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "-B",
        "-m",
        "pytest",
        "-p",
        "no:cacheprovider",
        "-q",
        "test_dp_consolidation_recovery.py",
        *extra,
    ]
    proc = subprocess.run(cmd, cwd=str(PKG), env=env, capture_output=True, text=True, encoding="utf-8")
    (HERE / f"{tag}.stdout").write_text(proc.stdout, encoding="utf-8", newline="\n")
    (HERE / f"{tag}.stderr").write_text(proc.stderr, encoding="utf-8", newline="\n")
    (HERE / f"{tag}.log").write_text(
        "cwd=" + str(PKG) + "\nargv=" + repr(cmd) + "\nrc=" + str(proc.returncode) + "\n"
        + "--- stdout ---\n" + proc.stdout + "\n--- stderr ---\n" + proc.stderr,
        encoding="utf-8",
        newline="\n",
    )
    print(f"tag={tag} rc={proc.returncode} cmd={' '.join(cmd)}")
    print(proc.stdout[-8000:])
    if proc.stderr:
        print("STDERR:", proc.stderr[-4000:])
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
