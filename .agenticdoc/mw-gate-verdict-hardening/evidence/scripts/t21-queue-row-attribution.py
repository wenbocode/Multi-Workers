"""Read-only: which task dirs have no queue row (the IN-3 predicate input)."""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(".agenticdoc")
queue_rows: set[str] = set()
for line in (ROOT / "_workers.parallel").read_text(encoding="utf-8").splitlines():
    if line.strip():
        queue_rows.add(line.split("|")[0].strip())

missing: list[str] = []
total = 0
for key_dir in sorted(p for p in ROOT.iterdir() if p.is_dir()):
    workers = key_dir / "workers"
    if not workers.is_dir():
        continue
    for task_dir in sorted(p for p in workers.iterdir() if p.is_dir()):
        if not (task_dir / "task.md").exists():
            continue
        total += 1
        if task_dir.name not in queue_rows:
            missing.append(f"{key_dir.name}/{task_dir.name}")

print(f"task dirs on disk : {total}")
print(f"queue rows        : {len(queue_rows)}")
print(f"dirs without a row: {len(missing)}")
for item in missing:
    print("   MISSING-ROW:", item)
orphan_rows = sorted(k for k in queue_rows if not (ROOT / k.split("-", 1)[0]).exists())
print(f"rows whose key dir is gone (informational): {len(orphan_rows)}")
