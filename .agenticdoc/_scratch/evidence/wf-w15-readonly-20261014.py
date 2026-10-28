"""Read-only discipline check for the new mw.py write_face doctor section."""

import pathlib
import re

t = pathlib.Path(r"H:\git\Multi-Workers\packages\multi-workers\mw.py").read_text(encoding="utf-8")
names = [
    "_write_face_detail_parts",
    "_parse_write_face_event",
    "_parse_write_face_ledger_row",
    "_doctor_write_face",
    "_format_write_face_doctor_line",
]
bad = re.compile(r"write_text|open\([^)]*[\"']w|acquire_lock|summary\[|issues\.append|mkdir|appendFile|os\.remove|unlink")
out = []
for n in names:
    m = re.search(r"^def " + n + r"\(.*?(?=^def |\Z)", t, re.S | re.M)
    body = m.group(0) if m else ""
    hits = [ln.strip()[:110] for ln in body.splitlines() if bad.search(ln)]
    out.append(f"{n}: {len(body.splitlines())} lines, violations={hits}")

out.append("")
out.append("cmd_doctor write_face lines:")
for i, ln in enumerate(t.splitlines(), 1):
    if "write_face" in ln and ("report[" in ln or "format_write_face" in ln):
        out.append(f"  {i}: {ln.strip()[:130]}")

dest = pathlib.Path(r"H:\git\Multi-Workers\.agenticdoc\_scratch\evidence\wf-w15-readonly-20261014.txt")
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest)
