"""Isolated control experiment: does test_autopilot_verdict_freshness pass with the
HEAD (pre-M-02) conductor.py? Copies the package to TEMP, swaps conductor.py, runs
the single test there. The worktree is never modified."""

import os
import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(r"H:\git\Multi-Workers")
SRC = REPO / "packages/multi-workers"
DST = pathlib.Path(os.environ["TEMP"]) / "mw-m02-baseline"
TEST = "test_autopilot_verdict_freshness.py::test_true_below_without_resume_stays_below"

if DST.exists():
    shutil.rmtree(DST, ignore_errors=True)
shutil.copytree(
    SRC,
    DST,
    ignore=shutil.ignore_patterns("dist", "__pycache__", ".pytest_cache", "*.pyc"),
)
print("copied ->", DST)

# overwrite conductor.py with the committed HEAD bytes
head = subprocess.run(
    ["git", "show", "HEAD:packages/multi-workers/autopilot/conductor.py"],
    cwd=REPO, capture_output=True,
).stdout
target = DST / "autopilot/conductor.py"
worktree_bytes = target.read_bytes()
target.write_bytes(head)
print(f"conductor.py: worktree={len(worktree_bytes)}B -> HEAD={len(head)}B")

r = subprocess.run(
    [sys.executable, "-m", "pytest", "-q", "--tb=line", "-rf", TEST],
    cwd=DST, capture_output=True, text=True, encoding="utf-8", errors="replace",
)
print("=== HEAD-conductor control run ===")
print((r.stdout or "").strip()[-1500:])
print("exit=", r.returncode)

# and the same test with the worktree conductor in the same copy (sanity)
target.write_bytes(worktree_bytes)
r2 = subprocess.run(
    [sys.executable, "-m", "pytest", "-q", "--tb=line", "-rf", TEST],
    cwd=DST, capture_output=True, text=True, encoding="utf-8", errors="replace",
)
print("=== worktree-conductor run (same copy) ===")
print((r2.stdout or "").strip()[-900:])
print("exit=", r2.returncode)
