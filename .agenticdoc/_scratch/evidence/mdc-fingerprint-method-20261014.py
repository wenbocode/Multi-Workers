"""Find how system-design computes ac_fingerprint (Step 6) so the PM can produce it correctly."""

import pathlib
import re

REPO = pathlib.Path(r"H:\git\Multi-Workers")
SKILL = REPO / ".agents/skills/agentic-task"
out = []

for rel in ("references/workflow-system-design.md", "core/workflows/system-design.md",
            "claude/skills/workflow-system-design/SKILL.md"):
    p = SKILL / rel
    if not p.is_file():
        out.append(f"MISSING {rel}")
        continue
    lines = p.read_text(encoding="utf-8").splitlines()
    out.append(f"===== {rel} ({len(lines)} lines) =====")
    for i, l in enumerate(lines, 1):
        if "ac_fingerprint" in l or re.search(r"fingerprint|sha256|sha1|md5", l, re.I):
            lo = max(0, i - 12)
            for j in range(lo, min(len(lines), i + 12)):
                out.append(f"{j+1}: {lines[j].rstrip()[:170]}")
            out.append("  ---")
            break

dest = REPO / ".agenticdoc/_scratch/evidence/mdc-fingerprint-method-20261014.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest, len(out), "lines")
