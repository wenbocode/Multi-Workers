"""Extract M-02's appendix A/B probe scripts from the evidence file and run them
as the PM (independent reproduction, P-025)."""

import os
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(r"H:\git\Multi-Workers")
EV = REPO / ".agenticdoc/mw-dynamic-concurrency/evidence/M-02-conductor-frontier.md"
SCRATCH = REPO / ".agenticdoc/_scratch/evidence"
PKG = REPO / "packages/multi-workers"

text = EV.read_text(encoding="utf-8")
lines = text.splitlines()

# appendix A: fence opens at md-line 395, closes at 824 (1-based)
a_src = "\n".join(lines[395:823])
# appendix B: opens 828, closes 903
b_src = "\n".join(lines[828:903])

a_path = SCRATCH / "mdc-m02-probe-a-20261014.py"
b_path = SCRATCH / "mdc-m02-probe-b-20261014.py"
a_path.write_text(a_src, encoding="utf-8")
b_path.write_text(b_src, encoding="utf-8")
print(f"extracted A={len(a_src)}B -> {a_path.name}; B={len(b_src)}B -> {b_path.name}")

# how does the probe observe behaviour? (tautology check)
for name, src in (("A", a_src), ("B", b_src)):
    hits = [ln.strip()[:120] for ln in src.splitlines()
            if re.search(r"execute_loop|_plan_task_order|started=|len\(rows\)|def run", ln)]
    print(f"--- probe {name}: observation points ---")
    for h in hits[:14]:
        print("   ", h)

env = dict(os.environ)
env["PYTHONPATH"] = str(PKG)
env["PYTHONIOENCODING"] = "utf-8"
for name, path in (("A", a_path), ("B", b_path)):
    r = subprocess.run([sys.executable, "-X", "utf8", str(path)],
                       cwd=PKG, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    out = (r.stdout or "") + ("\n[stderr]\n" + r.stderr if r.stderr.strip() else "")
    dest = SCRATCH / f"mdc-m02-probe-{name.lower()}-out-20261014.txt"
    dest.write_text(out, encoding="utf-8")
    print(f"=== PM RERUN probe {name}: exit={r.returncode} -> {dest.name} ({len(out)}B) ===")
    print(out.strip()[-2200:])
