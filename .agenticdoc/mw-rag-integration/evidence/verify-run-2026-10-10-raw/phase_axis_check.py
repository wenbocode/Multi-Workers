"""Independent T-14 phase-axis re-check for T-11 (mw-rag-integration re-verification)."""
import pathlib
import sys

REPO = pathlib.Path(r"H:/git/Multi-Workers")
sys.path.insert(0, str(REPO / "packages" / "multi-workers"))

from autopilot import dispatch as d  # noqa: E402

base = d.render_task_md("coding", "hello", loop="t", attempt=1)
empty_phase = d.render_task_md("coding", "hello", loop="t", attempt=1, phase="")
with_phase = d.render_task_md("coding", "hello", loop="t", attempt=1, phase="DESIGN")

print("[VERIFY] T11-phase: empty_identical=%s" % (base == empty_phase))
head = [ln for ln in with_phase.splitlines()[:6]]
print("[VERIFY] T11-phase: phase_written_head=%r" % (head,))
type_idx = next(i for i, ln in enumerate(with_phase.splitlines()) if ln.startswith("type:"))
phase_idx = next(i for i, ln in enumerate(with_phase.splitlines()) if ln.startswith("phase:"))
print("[VERIFY] T11-phase: order_type_before_phase=%s type_idx=%d phase_idx=%d"
      % (type_idx < phase_idx, type_idx, phase_idx))

print("[VERIFY] T11-phase: owner_phase_mw_rag=%r" % d._owner_phase(REPO, "mw-rag-integration"))
print("[VERIFY] T11-phase: owner_phase_scratch=%r" % d._owner_phase(REPO, "_scratch"))
print("[VERIFY] T11-phase: owner_phase_missing=%r" % d._owner_phase(REPO, "no-such-key-xyz"))
