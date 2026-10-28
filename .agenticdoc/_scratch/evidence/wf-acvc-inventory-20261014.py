"""Dump the AC/VC inventory of mw-write-face-guard for the quality-gate report."""

import pathlib
import re

KEY = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\mw-write-face-guard")
out = []

spec = (KEY / "spec.md").read_text(encoding="utf-8")
out.append("=== spec.md AC lines ===")
for line in spec.splitlines():
    if re.match(r"^\s*[-*|]?\s*\**AC-\d{3}\**", line) or "AC-0" in line and line.strip().startswith(("-", "|", "*")):
        s = line.strip()
        if s:
            out.append(s[:400])

design = (KEY / "design.md").read_text(encoding="utf-8")
out.append("")
out.append("=== design.md VC lines ===")
for line in design.splitlines():
    if re.search(r"VC-\d{3}", line):
        out.append(line.strip()[:300])

tasks = sorted((KEY / "tasks").glob("*.md"))
out.append("")
out.append(f"=== tasks ({len(tasks)}) ac_refs/vc_refs ===")
for t in tasks:
    txt = t.read_text(encoding="utf-8")
    acs = sorted(set(re.findall(r"AC-\d{3}", txt)))
    vcs = sorted(set(re.findall(r"VC-\d{3}", txt)))
    out.append(f"{t.name}: ac={','.join(acs) if acs else '-'} vc={','.join(vcs) if vcs else '-'}")

p = KEY / "pm-state.md"
out.append("")
out.append("=== pm-state.md ===")
out.append(p.read_text(encoding="utf-8"))

dest = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\_scratch\evidence\wf-acvc-inventory-20261014.txt")
dest.write_text("\n".join(out), encoding="utf-8")
print(f"wrote {dest} ({dest.stat().st_size} bytes)")
