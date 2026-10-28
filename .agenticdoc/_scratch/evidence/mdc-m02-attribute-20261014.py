"""Attribute the verdict_freshness red + audit M-02's conductor.py diff surface."""

import pathlib
import re
import subprocess

ROOT = pathlib.Path(r"H:\git\Multi-Workers")
out = []

# --- 1) verdict_freshness: does it involve conductor at all? ---
tf = ROOT / "packages/multi-workers/test_autopilot_verdict_freshness.py"
txt = tf.read_text(encoding="utf-8")
out.append("=== test_autopilot_verdict_freshness.py: mentions of conductor/advance/report ===")
for i, ln in enumerate(txt.splitlines(), 1):
    if re.search(r"conductor|advance|report_|_round|round", ln):
        out.append(f"{i}: {ln.strip()[:150]}")
out.append("")
out.append("=== failing test region 150-196 ===")
tfl = txt.splitlines()
for i in range(149, 196):
    out.append(f"{i+1}: {tfl[i].rstrip()[:150]}")

# --- 2) conductor.py diff hunk headers (function context) ---
diff = subprocess.run(
    ["git", "diff", "-U0", "--", "packages/multi-workers/autopilot/conductor.py"],
    cwd=ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace",
).stdout
out.append("")
out.append("=== conductor.py diff hunk headers ===")
for ln in diff.splitlines():
    if ln.startswith("@@"):
        out.append(ln[:170])
out.append("")
out.append(f"diff lines={len(diff.splitlines())} adds={sum(1 for l in diff.splitlines() if l.startswith('+') and not l.startswith('+++'))} dels={sum(1 for l in diff.splitlines() if l.startswith('-') and not l.startswith('---'))}")

# --- 3) diff surface audit: frozen vocab / in-flight predicate / new event names ---
out.append("")
out.append("=== diff: added lines touching timeline/event/in-flight/_is_in_flight ===")
for ln in diff.splitlines():
    if ln.startswith("+") and re.search(r"timeline\.append|EVENT_TYPES|_is_in_flight|_row_belongs_to|append\(\"", ln):
        out.append(ln[:170])
out.append("")
out.append("=== diff: any NEW event name string in append( ... ) first arg ===")
names = set()
for ln in diff.splitlines():
    if ln.startswith("+"):
        for m in re.finditer(r'append\(\s*"([a-z0-9-]+)"', ln):
            names.add(m.group(1))
out.append("event names introduced/kept in added lines: " + ", ".join(sorted(names)))

dest = ROOT / ".agenticdoc/_scratch/evidence/mdc-m02-attribute-20261014.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest, len(out), "lines")
