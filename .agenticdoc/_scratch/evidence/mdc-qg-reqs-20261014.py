"""Dump the QG workflow's requirements about evidence artifacts (AC->VC, evidence-requirement, fingerprint, baseline/runs)."""

import pathlib
import re

REPO = pathlib.Path(r"H:\git\Multi-Workers")
p = REPO / ".agents/skills/agentic-task/references/workflow-quality-gate.md"
lines = p.read_text(encoding="utf-8").splitlines()

out = [f"lines={len(lines)}"]
for i, l in enumerate(lines, 1):
    if re.search(r"evidence-requirement|ac_fingerprint|baseline|runs/|AC\s*→\s*VC|AC->VC|矩阵|fingerprint", l):
        out.append(f"{i}: {l.strip()[:180]}")

# plus the section headers so we know where these live
out.append("")
out.append("=== headings ===")
for i, l in enumerate(lines, 1):
    if l.strip().startswith("#"):
        out.append(f"{i}: {l.strip()[:120]}")

dest = REPO / ".agenticdoc/_scratch/evidence/mdc-qg-reqs-20261014.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest, len(out), "lines")
