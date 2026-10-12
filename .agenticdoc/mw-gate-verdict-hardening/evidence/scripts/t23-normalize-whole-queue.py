"""D-044/D-046 v2: normalise the whole queue to 8 columns in ONE locked write.

v1 looped `mw_common.upsert_worker_row` per row: N whole-file `os.replace`
calls, no lock (that function documents "the caller owns the lock"), so a
concurrent launcher write produced WinError 5 half-way through and left the
file at 130x8 + 132x9 columns - a mixed state where the nine pre-10:53 windows
see only part of the queue (IN-3's precondition).

v2: hold `.mw/workers.lock`, build the target lines in memory (strip the 9th
column when present), write once via `mw_common._write_workers_file`, retry on
transient Windows sharing violations.
"""

from __future__ import annotations

import collections
import pathlib
import sys
import time

root = pathlib.Path(".").resolve()
sys.path.insert(0, str(root / "packages/multi-workers"))

import mw_common

QUEUE = mw_common.workers_path(root)
LOCK = mw_common.lock_path(root)


def shape(lines: list[str]) -> dict[int, int]:
    counts: dict[int, int] = collections.Counter()
    for line in lines:
        if line.strip():
            counts[len(line.split("|"))] += 1
    return dict(counts)


def read_lines() -> list[str]:
    return QUEUE.read_text(encoding="utf-8").splitlines()


lines = read_lines()
print(f"before: rows={len([l for l in lines if l.strip()])} cols={shape(lines)}")

target: list[str] = []
stripped = 0
for line in lines:
    if not line.strip():
        target.append(line)
        continue
    parts = line.split("|")
    if len(parts) == 9:
        if parts[8].strip() != "manual":
            raise SystemExit(f"refusing: row {parts[0].strip()} carries origin={parts[8].strip()!r}")
        parts = parts[:8]
        stripped += 1
    if len(parts) not in (7, 8):
        raise SystemExit(f"refusing: row {parts[0].strip()} has {len(parts)} columns")
    if len(parts) == 7:
        parts = parts + [""]
    target.append("|".join(parts))

if stripped == 0:
    print("nothing to do: queue already 8 columns")
else:
    mw_common.acquire_lock(LOCK)
    try:
        for attempt in range(5):
            try:
                mw_common._write_workers_file(QUEUE, target)
                break
            except PermissionError as exc:  # WinError 5: launcher holds the file
                print(f"  attempt {attempt + 1}: {exc}")
                time.sleep(0.4 * (attempt + 1))
        else:
            raise SystemExit("refusing: could not write the queue after 5 attempts")
    finally:
        mw_common.release_lock(LOCK)
    print(f"rewrote {stripped} rows in one locked write")

after = read_lines()
print(f"after : rows={len([l for l in after if l.strip()])} cols={shape(after)}")
queue = mw_common.parse_workers_queue(QUEUE)
print(
    f"parser view: rows={len(queue['rows'])} unparsable={len(queue['unparsable'])} "
    f"version={queue.get('version')} conductor={sum(1 for r in queue['rows'] if mw_common.worker_is_conductor(r))}"
)
print("mine:", [r["task_key"] + "=" + r["status"] for r in queue["rows"] if r["task_key"].startswith("mwg-")])
