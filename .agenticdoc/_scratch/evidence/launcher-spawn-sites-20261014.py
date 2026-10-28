import pathlib
import re

src = pathlib.Path("launcher.py").read_text(encoding="utf-8").splitlines()
defs = []
for i, line in enumerate(src, 1):
    m = re.match(r"^(?:async )?def (\w+)", line)
    if m:
        defs.append((i, m.group(1)))
print("site    function                       line")
for i, line in enumerate(src, 1):
    if "PI_WORKER_TASK" in line:
        owner = [d for d in defs if d[0] < i]
        print(f"{i:5d}   {owner[-1][1] if owner else '?':30s} {line.strip()[:70]}")
print()
print("all spawn-ish call sites (Popen):")
for i, line in enumerate(src, 1):
    if "subprocess.Popen" in line or "process_log" in line or "_worker_log_path" in line:
        owner = [d for d in defs if d[0] < i]
        print(f"{i:5d}   {owner[-1][1] if owner else '?':30s} {line.strip()[:70]}")
