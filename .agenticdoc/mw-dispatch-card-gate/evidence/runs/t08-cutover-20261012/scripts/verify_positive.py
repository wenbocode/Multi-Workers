"""T-08 positive-evidence assertions on the card-form fixture task.md.

Checks the three requirement-2 assertions directly against the artifact on
disk (not the console copy):

  1. the three traceability lines really landed (`card_path:`, `card_sha256:`,
     `envelope_producer:`);
  2. the canonical sections and the `coding` extras are complete per the
     service judge (`launcher.inspect_envelope` / `launcher.type_extras_missing`);
  3. `card_audit` counts the dispatch as `dispatched` (never
     `unlisted_after_boundary`).

Run (repo root):
    python -X utf8 .../scripts/verify_positive.py
"""
from __future__ import annotations

import pathlib
import sys

REPO = pathlib.Path(__file__).resolve().parents[6]
RUN = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "packages" / "multi-workers"))

import launcher  # noqa: E402
from autopilot import card_audit  # noqa: E402

fixture = RUN / "fixture" / "pos"
task_md = (
    fixture / ".agenticdoc" / "mw-dispatch-card-gate" / "workers"
    / "T-08-cutover-and-runtime-evidence" / "task.md"
)
text = task_md.read_text(encoding="utf-8")

out: list[str] = []
out.append("$ python -X utf8 .agenticdoc/mw-dispatch-card-gate/evidence/runs/t08-cutover-20261012/scripts/verify_positive.py")
out.append(f"=== task.md: {task_md}")
out.append("=== header (first 10 lines) ===")
out.extend(text.splitlines()[:10])
out.append("=== assertion 1: three traceability lines on disk ===")
for key in ("card_path:", "card_sha256:", "envelope_producer:"):
    hits = [ln for ln in text.splitlines() if ln.startswith(key)]
    out.append(f"  {key:<20} {hits[0] if hits else '(MISSING)'}")
ok, missing, task_type, detected = launcher.inspect_envelope(text)
extras = launcher.type_extras_missing(task_type, text)
out.append("=== assertion 2: canonical sections + coding extras ===")
out.append(f"  inspect_envelope ok={ok} type={task_type} missing={missing}")
out.append(f"  detected={detected}")
out.append(f"  type_extras_missing('{task_type}')={extras}")
out.append("=== assertion 3: card_audit classification ===")
result = card_audit.audit(fixture / ".agenticdoc", "mw-dispatch-card-gate")
out.append(f"  dispatched={result['dispatched']}")
out.append(f"  unlisted_after_boundary={result['unlisted_after_boundary']}")
out.append(f"  missing_cards={result['missing_cards']} tampered_cards={result['tampered_cards']}")
verdict = card_audit.has_findings(result, strict=False)
out.append(f"  has_findings={verdict} (expect False)")

report = RUN / "positive-task-md-assertions.txt"
report.write_text("\n".join(out) + "\n", encoding="utf-8")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass
print("\n".join(out))

failed = (
    any("(MISSING)" in line for line in out)
    or not ok
    or bool(missing)
    or bool(extras)
    or bool(result["unlisted_after_boundary"])
    or verdict
)
sys.exit(1 if failed else 0)
