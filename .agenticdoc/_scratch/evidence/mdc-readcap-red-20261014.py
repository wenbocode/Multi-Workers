"""Inspect the failing readcap baseline test + what M-03 changed in that file."""

import pathlib
import re
import subprocess

ROOT = pathlib.Path(r"H:\git\Multi-Workers")
out = []

p = ROOT / "packages/multi-workers/test_autopilot_readcap_injection.py"
lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
out.append(f"=== {p.name} ({len(lines)} lines): the failing test + context ===")
start = None
for i, ln in enumerate(lines, 1):
    if "def test_baseline_left_end_bound" in ln:
        start = i
        break
if start:
    lo = max(1, start - 45)
    for i in range(lo, min(len(lines), start + 30) + 1):
        out.append(f"{i}: {lines[i - 1].rstrip()[:150]}")

out.append("")
out.append("=== git diff of that file (M-03's change) ===")
r = subprocess.run(
    ["git", "diff", "--", "packages/multi-workers/test_autopilot_readcap_injection.py"],
    cwd=str(ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace",
)
out.append(r.stdout[:6000] or "(no diff)")

dest = ROOT / ".agenticdoc/_scratch/evidence/mdc-readcap-red-20261014.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest, len(out), "lines")
