"""Record the real preparation instant of this R2-envelope attempt, once.

This writes ``prepared-at-record.json``: the single recorded timestamp that
``build_decide_cases.CASE_PREPARED_AT`` is frozen to. It is the authoring
instant of the *synthetic* case set (explicit ``+00:00``), not evidence that a
real decision was prepared or authorized - no old run-start instant is reused
and no zone is guessed. Run once with ``-B``; the value is then a constant.
"""

from __future__ import annotations

import datetime
import json
import pathlib
import sys

assert sys.dont_write_bytecode

HERE = pathlib.Path(__file__).resolve().parent
EVIDENCE = HERE.parent

now = datetime.datetime.now(datetime.timezone.utc)
recorded = now.replace(microsecond=0).isoformat()
payload = {
    "source": "agent-report",
    "recorded_at_utc": recorded,
    "reading": "datetime.datetime.now(datetime.timezone.utc), truncated to the second",
    "explicit_zone": "+00:00 (UTC)",
    "clock_source": "worker host system clock, read once at this attempt's preparation step",
    "meaning": (
        "authoring instant of the eight synthetic decide_cases shipped by "
        "scripts/build_decide_cases.py in the T05-R2-envelope attempt"
    ),
    "not_evidence_of": (
        "a real decision being prepared, a granted authorization, or a historical "
        "preparation event; the cases are synthetic fixtures"
    ),
    "frozen_into": "packages/multi-workers/scripts/build_decide_cases.py::CASE_PREPARED_AT",
    "wall_clock_per_run": False,
    "backfilled_from_run_start": False,
    "python": sys.version,
}
target = EVIDENCE / "prepared-at-record.json"
assert not target.exists(), f"{target} already exists: the instant is recorded once"
target.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
print(recorded)
