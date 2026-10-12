"""D-044: normalise the freshly dispatched rows to the queue's 8-column shape.

Why: the TS store always writes 9 columns (`origin` last), while nine long-lived
pi windows started before 2026-10-10 10:53 still run the pre-`b8bc115ff` reader
that accepts 7..8 columns and silently drops 9-column rows. Keeping the file
homogeneous at 8 columns makes every live codec able to read every row.

The write itself goes through the T-18 slot-preserving writer, so nothing else
in the file is touched. `origin=""` is semantically identical to `manual` for
every consumer (missing origin normalises to manual in the TS store and is
treated as non-conductor in Python).
"""

from __future__ import annotations

import pathlib
import sys

sys.path.insert(0, str(pathlib.Path("packages/multi-workers")))

import mw_common

TASK_KEYS = [
    "mwg-t01-l3-aborted",
    "mwg-t02-config-keys",
    "mwg-t03-event-names",
    "mwg-t04-contract-guard",
    "mwg-t05-ts-mirror",
]

queue_path = mw_common.workers_path(pathlib.Path(".").resolve())


def shape() -> dict[int, int]:
    counts: dict[int, int] = {}
    for line in queue_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            cols = len(line.split("|"))
            counts[cols] = counts.get(cols, 0) + 1
    return counts


before = shape()
rows = {row["task_key"]: row for row in mw_common.parse_workers_queue(queue_path)["rows"]}

missing = [key for key in TASK_KEYS if key not in rows]
if missing:
    raise SystemExit(f"refusing: rows not found yet: {missing}")

for key in TASK_KEYS:
    row = dict(rows[key])
    row["origin"] = ""
    mw_common.upsert_worker_row(queue_path, row)
    print(f"normalised {key}: {row['status']} cols->8")

after = shape()
print(f"columns before: {before}")
print(f"columns after : {after}")

dupes = [key for key in TASK_KEYS if sum(1 for line in queue_path.read_text(encoding='utf-8').splitlines() if line.split('|')[0].strip() == key) > 1]
print(f"duplicate rows for my keys: {dupes if dupes else 'none'}")
print(f"my rows: {len(TASK_KEYS)}, all 8 columns: {after.get(8) == sum(after.values())}")
