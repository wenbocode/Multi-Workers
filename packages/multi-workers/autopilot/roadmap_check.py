"""
roadmap_check.py — independent roadmap validator CLI (goal-autopilot T-03,
AC-001 / VC-001).

Usage:
    python autopilot/roadmap_check.py [--project <dir>]

Validates .agenticdoc/_autopilot/_roadmap.md under the project dir:
  - every stage has >= 1 key row in its Keys table,
  - every stage goal is non-empty,
  - every dependency points to a key in the same or an earlier stage,
  - a present key-status line covers exactly the stage's Keys-table keys.

Exit 0 = all stages valid (stdout summary). Exit 1 = missing/unparseable
roadmap or any violation (each problem printed to stderr). Runs standalone:
no conductor, no service, no config required.
"""

from __future__ import annotations

import argparse
import os
import sys

if __package__ in (None, ""):  # direct `python autopilot/roadmap_check.py` run
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from autopilot import roadmap


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="roadmap_check.py",
        description="Validate .agenticdoc/_autopilot/_roadmap.md (AC-001).",
    )
    parser.add_argument(
        "--project",
        default=os.getcwd(),
        help="project root containing .agenticdoc/_autopilot/_roadmap.md (default: cwd)",
    )
    args = parser.parse_args(argv)

    path = roadmap.roadmap_path(args.project)
    try:
        parsed = roadmap.load_roadmap(path)
    except roadmap.RoadmapError as e:
        print(f"roadmap parse error: {e}", file=sys.stderr)
        return 1

    problems = roadmap.validate_roadmap(parsed)
    if problems:
        for problem in problems:
            print(f"roadmap invalid: {problem}", file=sys.stderr)
        return 1

    total_keys = sum(len(stage.keys) for stage in parsed.stages)
    print(f"roadmap OK: {len(parsed.stages)} stage(s), {total_keys} key(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
