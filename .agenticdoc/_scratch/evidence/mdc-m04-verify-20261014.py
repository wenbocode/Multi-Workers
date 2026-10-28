"""PM verification of M-04: dump the diffs (dispatch.py / conductor.py / the test file)
and re-run the card's appendix-A probe in its original location.

Nothing here writes to the worktree except a temporary probe copy that is removed.
"""

import pathlib
import re
import shutil
import subprocess
import sys

REPO = pathlib.Path(r"H:\git\Multi-Workers")
PKG = REPO / "packages/multi-workers"
EVID = REPO / ".agenticdoc/mw-dynamic-concurrency/evidence/M-04-dispatch-dedup.md"
SCRATCH = REPO / ".agenticdoc/_scratch/evidence"

# ---------- 1) diffs ----------
out = []
for path in ("packages/multi-workers/autopilot/dispatch.py",
             "packages/multi-workers/autopilot/conductor.py",
             "packages/multi-workers/test/test_write_face_dispatch.py"):
    d = subprocess.run(["git", "diff", "-U2", "--", path], cwd=REPO,
                       capture_output=True, text=True, encoding="utf-8", errors="replace").stdout
    adds = sum(1 for l in d.splitlines() if l.startswith("+") and not l.startswith("+++"))
    dels = sum(1 for l in d.splitlines() if l.startswith("-") and not l.startswith("---"))
    out.append("=" * 78)
    out.append(f"DIFF {path}  (+{adds}/-{dels})")
    out.append(d if len(d) < 12000 else d[:12000] + "\n...[truncated]...")

dest = SCRATCH / "mdc-m04-diffs-20261014.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest, len(out), "lines")

# ---------- 2) re-run the appendix-A probe ----------
text = EVID.read_text(encoding="utf-8")
lines = text.splitlines()
fences = [i for i, l in enumerate(lines) if l.strip().startswith("```")]
appendix = [i for i, l in enumerate(lines) if "附录 A" in l]
print("appendix A at line", [i + 1 for i in appendix], "fence indexes", [f + 1 for f in fences])
if appendix:
    start = next((f for f in fences if f > appendix[0]), None)
    if start is not None:
        end = next((f for f in fences if f > start), None)
        src = "\n".join(lines[start + 1:end])
        probe = PKG / "_pm_m04_probe.py"
        probe.write_text(src, encoding="utf-8")
        try:
            r = subprocess.run([sys.executable, "-X", "utf8", probe.name], cwd=PKG,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
        finally:
            probe.unlink(missing_ok=True)
        body = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
        pdest = SCRATCH / "mdc-m04-probe-pm-rerun-20261014.txt"
        pdest.write_text(body, encoding="utf-8")
        print(f"probe exit={r.returncode} -> {pdest.name} ({len(body)}B)")
        print(body.strip()[-1800:])
