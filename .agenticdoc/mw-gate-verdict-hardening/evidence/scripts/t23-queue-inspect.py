from __future__ import annotations

import collections
import datetime
import pathlib
import sys

root = pathlib.Path(".")
d = root / ".agenticdoc"
print("queue-related files:")
for p in sorted(d.glob("_workers*")):
    st = p.stat()
    print(f"  {p.name:40s} {st.st_size:8d} B  mtime={datetime.datetime.fromtimestamp(st.st_mtime).strftime('%H:%M:%S')}")

p = d / "_workers.parallel"
lines = [l for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
print("rows", len(lines), "cols", dict(collections.Counter(len(l.split("|")) for l in lines)))
print("9-col rows:", [l.split("|")[0].strip() for l in lines if len(l.split("|")) == 9][:3], "...")
print("mine:")
for l in lines:
    if l.split("|")[0].strip().startswith("mwg-"):
        parts = l.split("|")
        print(f"  {parts[0].strip():28s} {parts[1].strip():8s} cols={len(parts)}")

sys.path.insert(0, str(root / "packages/multi-workers"))
import mw_common  # noqa: E402

q = mw_common.parse_workers_queue(p)
print("parser view: rows", len(q["rows"]), "unparsable", len(q["unparsable"]), "version", q.get("version"))
