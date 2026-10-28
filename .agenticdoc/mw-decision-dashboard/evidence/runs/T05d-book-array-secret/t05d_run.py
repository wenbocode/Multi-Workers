"""Run one command (pytest or npm) from packages/multi-workers and save its full log.

Usage: python t05d_run.py <log-name> <cwd-relative-to-repo> <argv...>

The log is written under the T05d evidence dir with the command, duration and
``EXIT_<name>=<code>`` so the reviewer can check the exit status from the
archive alone.
"""

import pathlib
import subprocess
import sys
import time

evidence = pathlib.Path(
    ".agenticdoc/mw-decision-dashboard/evidence/runs/T05d-book-array-secret"
)
evidence.mkdir(parents=True, exist_ok=True)
name = sys.argv[1]
cwd = sys.argv[2]
argv = sys.argv[3:]
started = time.time()
completed = subprocess.run(
    argv,
    cwd=cwd,
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
)
elapsed = time.time() - started
header = [
    f"# cmd: {' '.join(argv)}",
    f"# cwd: {cwd}",
    f"# started: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(started))}",
    f"# elapsed_s: {elapsed:.1f}",
    "",
]
body = header + [completed.stdout, completed.stderr, f"EXIT_{name}={completed.returncode}"]
(evidence / f"{name}.txt").write_text("\n".join(body) + "\n", encoding="utf-8", newline="\n")
print("\n".join(body))
