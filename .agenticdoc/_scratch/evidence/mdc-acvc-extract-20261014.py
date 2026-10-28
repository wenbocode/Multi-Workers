"""Extract MDC spec ACs + design VCs to build the AC->VC matrix (QG prerequisite)."""

import pathlib
import re

ROOT = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-dynamic-concurrency")
out = []

for name in ("spec.md", "design.md"):
    text = (ROOT / name).read_text(encoding="utf-8")
    out.append(f"===== {name} =====")
    for ln in text.splitlines():
        s = ln.strip()
        if re.match(r"^\|?\s*\*{0,2}(AC|VC)-\d+", s):
            out.append(s[:230])
    out.append("")

dest = ROOT.parent / "_scratch/evidence/mdc-acvc-list-20261014.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest, len(out), "lines")
