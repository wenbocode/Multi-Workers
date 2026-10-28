"""Rerun M-02 probe A in its ORIGINAL location, so __file__-derived paths (FRAMEWORK)
resolve as they did for the worker. Temp copy is removed afterwards."""

import pathlib
import shutil
import subprocess
import sys

REPO = pathlib.Path(r"H:\git\Multi-Workers")
PKG = REPO / "packages/multi-workers"
SRC = REPO / ".agenticdoc/_scratch/evidence/mdc-m02-probe-a-20261014.py"

print("=== FRAMEWORK / HERE definitions in the probe ===")
txt = SRC.read_text(encoding="utf-8")
for i, ln in enumerate(txt.splitlines(), 1):
    if ("FRAMEWORK" in ln and "=" in ln) or "HERE" in ln:
        print(f"{i}: {ln.strip()[:140]}")

dst = PKG / "_pm_m02_probe_a.py"
shutil.copyfile(SRC, dst)
try:
    r = subprocess.run([sys.executable, "-X", "utf8", dst.name],
                       cwd=PKG, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
finally:
    dst.unlink(missing_ok=True)
out = (r.stdout or "") + (("\n[stderr]\n" + r.stderr) if r.stderr.strip() else "")
dest = REPO / ".agenticdoc/_scratch/evidence/mdc-m02-probe-a-inplace-out-20261014.txt"
dest.write_text(out, encoding="utf-8")
print(f"=== PM RERUN probe A in-place: exit={r.returncode} -> {dest.name} ({len(out)}B) ===")
i = out.find("F. AC-013")
print(out[i:i + 1200] if i >= 0 else out[-1200:])
print(f"temp copy removed: {not dst.exists()}")
