"""T04b evidence runner: run an argv, write full stdout+stderr to a log.

Usage (repo root):
    python .agenticdoc/mw-decision-dashboard/evidence/runs/T04b-contract-artifacts/run-log.py \
        <log-name> <cwd> -- <cmd...>

Prints the exit code and the log size so the caller can record both without
piping through PowerShell (which would re-encode the output).
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent


def main(argv: list[str]) -> int:
    log_name, cwd, _, *cmd = argv
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    log = HERE / log_name
    body = f"$ {' '.join(cmd)}\n$ cwd={cwd}\n$ exit={proc.returncode}\n\n{proc.stdout}"
    if proc.stderr:
        body += f"\n--- stderr ---\n{proc.stderr}"
    log.write_text(body, encoding="utf-8", newline="\n")
    print(f"exit={proc.returncode} log={log.name} bytes={len(body.encode('utf-8'))}")
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
