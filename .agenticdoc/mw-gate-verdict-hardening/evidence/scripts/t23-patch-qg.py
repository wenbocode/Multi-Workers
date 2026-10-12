"""Regenerate the quality-gate report with corrected VC grouping + snippet source."""

import pathlib
import re

ROOT = pathlib.Path(".agenticdoc/mw-gate-verdict-hardening")
script = pathlib.Path(".tmp/t23-quality-gate-report.py")
src = pathlib.Path(
    ".agenticdoc/mw-gate-verdict-hardening/evidence/scripts/t23-quality-gate-report.py"
).read_text(encoding="utf-8")

# fix the group map (no overlap)
src = src.replace(
    '''group = {
    "G1 (L3 流中止)": [f"VC-{i:03d}" for i in range(1, 9)],
    "G2 (闸门静默/提醒)": [f"VC-{i:03d}" for i in range(5, 12)],
    "G3 (授权范围/契约闸门)": [f"VC-{i:03d}" for i in range(12, 20)],
    "G4 (面板冻结/自证)": [f"VC-{i:03d}" for i in range(20, 24)],
}''',
    '''group = {
    "G1 (L3 流中止)": [f"VC-{i:03d}" for i in range(1, 7)],
    "G2 (闸门静默/提醒)": [f"VC-{i:03d}" for i in range(7, 12)],
    "G3 (授权范围/契约闸门)": [f"VC-{i:03d}" for i in range(12, 20)],
    "G4 (面板冻结/自证)": [f"VC-{i:03d}" for i in range(20, 24)],
}''',
)

# prefer the canonical `VC-0NN: ...` line as the snippet source
src = src.replace(
    "for line in design.splitlines():\n    for m in re.finditer(r\"(VC-0\\d\\d)\", line):",
    "for line in design.splitlines():\n    if not re.match(r\"^VC-0\\d\\d:\", line.strip()):\n        continue\n    for m in re.finditer(r\"(VC-0\\d\\d)\", line):",
)

script.write_text(src, encoding="utf-8", newline="\n")
print("patched generator")
