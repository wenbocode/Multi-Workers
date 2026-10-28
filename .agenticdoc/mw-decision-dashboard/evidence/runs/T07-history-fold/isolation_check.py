"""T07 isolation evidence: production ledgers must not change across a history run.

Reads the four production ledgers under ``.agenticdoc/_autopilot`` (read-only),
runs the history test suite, then re-reads them. The log is written next to this
script inside the T07 evidence dir; nothing is written to the ledgers.
"""

from __future__ import annotations

import hashlib
import pathlib
import subprocess
import sys

HERE = pathlib.Path(__file__).resolve().parent
REPO = HERE.parents[4]
PACKAGE = REPO / "packages" / "multi-workers"
LEDGERS = REPO / ".agenticdoc" / "_autopilot"


def hashes() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted(LEDGERS.glob("*.jsonl")):
        found[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return found


def main() -> int:
    before = hashes()
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "test_decision_history.py", "-q"],
        cwd=PACKAGE,
        capture_output=True,
        text=True,
        check=False,
    )
    after = hashes()
    lines = [
        f"cwd={PACKAGE}",
        "cmd=python -m pytest test_decision_history.py -q (via this isolation check)",
        f"pytest_exit={completed.returncode}",
        completed.stdout.strip(),
    ]
    for name in sorted(before):
        lines.append(f"before {name} {before[name]}")
        lines.append(f"after  {name} {after[name]}")
    lines.append(f"unchanged={before == after}")
    (HERE / "production-bytes-isolation.txt").write_text(
        "\n".join(lines) + "\n", encoding="utf-8", newline="\n"
    )
    print("\n".join(lines))
    return 0 if before == after and completed.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
