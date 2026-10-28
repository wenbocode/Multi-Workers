"""Dump M-02 evidence structure + key raw-output sections; extract appendix probe."""

import pathlib
import re

ROOT = pathlib.Path(r"H:\git\Multi-Workers")
p = ROOT / ".agenticdoc/mw-dynamic-concurrency/evidence/M-02-conductor-frontier.md"
t = p.read_text(encoding="utf-8")
lines = t.splitlines()

out = []
out.append(f"bytes={len(t.encode())} lines={len(lines)}")
out.append("=== headings ===")
for i, ln in enumerate(lines, 1):
    if ln.lstrip().startswith("#"):
        out.append(f"{i}: {ln[:120]}")
out.append("")
out.append("=== all code fences (lang + first line + line no) ===")
in_fence = False
for i, ln in enumerate(lines, 1):
    if ln.strip().startswith("```"):
        if not in_fence:
            in_fence = True
            out.append(f"{i}: FENCE-OPEN {ln.strip()[:40]}")
        else:
            in_fence = False
            out.append(f"{i}: FENCE-CLOSE")
dest = ROOT / ".agenticdoc/_scratch/evidence/mdc-m02-evidence-index-20261014.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest, len(out))
