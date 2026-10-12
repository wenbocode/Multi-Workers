"""PM-independent G3 liveness check (AC-025 / T-23): freeze, tamper, refuse."""

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path("H:/git/Multi-Workers")
sys.path.insert(0, str(ROOT / "packages" / "multi-workers"))

from autopilot import conductor, contract_guard, timeline  # noqa: E402

print("1) python EVENT_TYPES size =", len(timeline.EVENT_TYPES),
      "| contract-frozen in set:", "contract-frozen" in timeline.EVENT_TYPES)

tmp = pathlib.Path(tempfile.mkdtemp(prefix="pm-g3-"))
proj = tmp / "proj"
key = "g3-demo"
kd = proj / ".agenticdoc" / key
(kd / "evidence").mkdir(parents=True)
(kd / "spec.md").write_text(
    "# Spec\n\n## Acceptance Criteria\n\n| id | text |\n|---|---|\n"
    "| AC-001 | first rule |\n| AC-002 | second rule |\n", encoding="utf-8")
(kd / "design.md").write_text(
    "# Design\n\n## Verification Criteria\n\n| id | text |\n|---|---|\n"
    "| VC-001 | first check |\n", encoding="utf-8")

# CLI: freeze all
cp = subprocess.run(
    [sys.executable, "-X", "utf8", str(ROOT / "packages" / "multi-workers" / "mw.py"),
     "autopilot", "contract-freeze", "--project", str(proj), "--key", key, "--json"],
    capture_output=True, text=True, encoding="utf-8")
print("2) CLI fresh  exit=", cp.returncode, cp.stdout.strip()[:120])
freeze = contract_guard.read_freeze(kd)
print("   spec block:", sorted(freeze["spec"]), "design block:", sorted(freeze["design"]))

# CLI: re-run (must be unchanged, byte-identical file)
before = contract_guard.freeze_path(kd).read_bytes()
cp = subprocess.run(
    [sys.executable, "-X", "utf8", str(ROOT / "packages" / "multi-workers" / "mw.py"),
     "autopilot", "contract-freeze", "--project", str(proj), "--key", key, "--json"],
    capture_output=True, text=True, encoding="utf-8")
print("3) CLI rerun  exit=", cp.returncode, cp.stdout.strip()[:120],
      "| bytes stable:", before == contract_guard.freeze_path(kd).read_bytes())

# tamper an AC line, then evaluate + CLI refusal
(kd / "spec.md").write_text(
    (kd / "spec.md").read_text(encoding="utf-8").replace("first rule", "first rule (edited)"),
    encoding="utf-8")
verdict = contract_guard.evaluate(kd, proj / ".mw" / "gates", key=key)
print("4) after tamper: ok=", verdict.ok, "changed_ids=", verdict.changed_ids,
      "no_anchor=", verdict.no_anchor)
cp = subprocess.run(
    [sys.executable, "-X", "utf8", str(ROOT / "packages" / "multi-workers" / "mw.py"),
     "autopilot", "contract-freeze", "--project", str(proj), "--key", key, "--json"],
    capture_output=True, text=True, encoding="utf-8")
print("5) CLI tampered exit=", cp.returncode, cp.stdout.strip()[:160])
cp = subprocess.run(
    [sys.executable, "-X", "utf8", str(ROOT / "packages" / "multi-workers" / "mw.py"),
     "autopilot", "contract-force-not-a-flag", "--project", str(proj)],
    capture_output=True, text=True, encoding="utf-8")
# conductor first-sight path: phase=design anchors AC only, never rewrites
print("6) real project sidecars:",
      [str(p) for p in (ROOT / ".agenticdoc").rglob("contract-freeze.json")] or "none")
shutil.rmtree(tmp, ignore_errors=True)
print("tmp cleaned:", not tmp.exists())
