import pathlib
import re

lines = pathlib.Path("trace.log").read_text(encoding="utf-8", errors="replace").splitlines()
starts = []
for idx, line in enumerate(lines):
    m = re.match(r"^\[START\] (\S+)", line)
    if m:
        starts.append((idx, m.group(1)))
print(f"[START] count = {len(starts)}\n")
for idx, ts in starts:
    print(f"=== START {ts} ===")
    for j in range(max(0, idx - 4), idx + 2):
        tag = ">>" if j == idx else "  "
        print(f" {tag} {lines[j][:150]}")
