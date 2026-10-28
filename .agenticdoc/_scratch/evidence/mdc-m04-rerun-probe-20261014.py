"""Re-extract M-04's appendix-A probe correctly (largest fenced block containing
import+def) and run it in the package dir; then report the key counts."""

import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(r"H:\git\Multi-Workers")
PKG = REPO / "packages/multi-workers"
EVID = REPO / ".agenticdoc/mw-dynamic-concurrency/evidence/M-04-dispatch-dedup.md"
SCRATCH = REPO / ".agenticdoc/_scratch/evidence"

lines = EVID.read_text(encoding="utf-8").splitlines()
fences = [i for i, l in enumerate(lines) if l.strip().startswith("```")]
blocks = []
for a, b in zip(fences[::2], fences[1::2]):
    body = "\n".join(lines[a + 1:b])
    if "import" in body and "def " in body:
        blocks.append((len(body), a, b, body))
blocks.sort(reverse=True)
print("candidate script blocks (bytes, start line, end line):",
      [(n, a + 1, b + 1) for n, a, b, _ in blocks[:4]])

if not blocks:
    raise SystemExit("no script block found")

_, a, b, body = blocks[0]
probe = PKG / "_pm_m04_probe.py"
probe.write_text(body, encoding="utf-8")
try:
    r = subprocess.run([sys.executable, "-X", "utf8", probe.name], cwd=PKG,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
finally:
    probe.unlink(missing_ok=True)
out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
dest = SCRATCH / "mdc-m04-probe-pm-rerun-20261014.txt"
dest.write_text(out, encoding="utf-8")
print(f"=== PM RERUN M-04 probe: exit={r.returncode} -> {dest.name} ({len(out)}B) ===")
print("\n".join(ln for ln in out.splitlines()
                if re.search(r"grants=|refusals=|rows=|dispatch_events|stalled|key_status|first_ok|second_ok|iter=",
                             ln))[:2500])
print("...tail...")
print(out.strip()[-500:])
