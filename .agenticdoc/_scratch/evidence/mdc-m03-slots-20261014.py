"""Dump M-03's slotsUsed computation in monitor.ts + related conductor accounting."""

import pathlib
import re

ROOT = pathlib.Path(r"H:\git\Multi-Workers")
out = []

m = (ROOT / "packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts").read_text(encoding="utf-8")
lines = m.splitlines()
out.append("=== monitor.ts: slotsUsed / cap / eff / frontier context ===")
for i, ln in enumerate(lines, 1):
    if re.search(r"slotsUsed|slotsCap|slotsMax|effective|frontier|busyKeys|origin", ln):
        out.append(f"{i}: {ln.rstrip()[:150]}")

out.append("")
out.append("=== monitor.ts: the used-slot counting block (search 'busyKeys' span) ===")
idx = [i for i, ln in enumerate(lines, 1) if "slotsUsed:" in ln]
for i in idx:
    lo, hi = max(1, i - 40), min(len(lines), i + 6)
    out.append(f"--- around {i} ---")
    for j in range(lo, hi + 1):
        out.append(f"{j}: {lines[j - 1].rstrip()[:150]}")

dest = ROOT / ".agenticdoc/_scratch/evidence/mdc-m03-slots-20261014.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest, len(out), "lines")
