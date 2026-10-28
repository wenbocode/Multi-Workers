"""T07 mutation check: prove the new history tests fail on reverted behaviour.

Runs in an isolated subdirectory (this evidence dir) so the working tree files
are never modified: each mutant is a copy of ``decision_history.py`` with one
behaviour reverted, next to a copy of the test module, executed with
``PYTHONPATH`` pointing at ``packages/multi-workers`` for the real dependencies.

Usage: ``python mutate_and_run.py`` (from this directory or anywhere).
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[4]
PACKAGE = REPO / "packages" / "multi-workers"
SOURCE = PACKAGE / "decision_history.py"
TESTS = PACKAGE / "test_decision_history.py"

MUTANTS = {
    "backfill-wire-attempts": (
        """            if not isinstance(wire_attempts, int) or isinstance(wire_attempts, bool):
                unrecorded += 1
                wire_attempts = None""",
        """            if not isinstance(wire_attempts, int) or isinstance(wire_attempts, bool):
                wire_attempts = 1""",
    ),
    "authority-human-is-human": (
        """    if human_basis:
        source = Claim("human", tuple(human_basis))""",
        """    if base is not None and base.get("authority") == "human":
        human_basis.append("authority=human")
    if human_basis:
        source = Claim("human", tuple(human_basis))""",
    ),
    "nearest-call-link": (
        """            elif _valid_identity_text(call_id):
                unlinked_calls.add(str(call_id))
                stats["unlinked_events"] += 1
                continue""",
        """            elif _valid_identity_text(call_id):
                identity = "decision|nearest"
                builder = builder_for(event_scope, identity)
                builder.decision_id = "dp1-dispatch-type:nearest" """,
    ),
}


def run_mutant(name: str, old: str, new: str) -> int:
    workdir = HERE / f"mutant-{name}"
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir()
    text = SOURCE.read_text(encoding="utf-8")
    if old not in text:
        print(f"[{name}] MUTATION TARGET NOT FOUND", flush=True)
        return 2
    (workdir / "decision_history.py").write_text(
        text.replace(old, new, 1), encoding="utf-8", newline="\n"
    )
    shutil.copyfile(TESTS, workdir / "test_decision_history.py")
    env = dict(os.environ)
    env["PYTHONPATH"] = str(PACKAGE)
    log = HERE / f"mutant-{name}.txt"
    with log.open("wb") as handle:
        completed = subprocess.run(
            [sys.executable, "-m", "pytest", "test_decision_history.py", "-q", "--no-header"],
            cwd=workdir,
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            check=False,
        )
    tail = log.read_text(encoding="utf-8", errors="replace").strip().splitlines()[-6:]
    print(f"[{name}] exit={completed.returncode}", flush=True)
    for line in tail:
        print("  " + line, flush=True)
    return completed.returncode


def main() -> int:
    failures = 0
    for name, (old, new) in MUTANTS.items():
        code = run_mutant(name, old, new)
        if code == 0:
            failures += 1
    if failures:
        print(f"{failures} mutant(s) survived: testing is too weak", flush=True)
        return 1
    print("all mutants killed by the behaviour tests", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
