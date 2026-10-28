"""Audit M-02's conductor.py change surface: dedup state, roadmap validation
(observation-only?), fail-closed write-face seam, execute_loop core."""

import pathlib
import subprocess

REPO = pathlib.Path(r"H:\git\Multi-Workers")
c = (REPO / "packages/multi-workers/autopilot/conductor.py").read_text(encoding="utf-8")
lines = c.splitlines()
out = []


def show(pattern, before=2, after=34, limit=4):
    hits = 0
    for i, ln in enumerate(lines):
        if pattern in ln:
            out.append(f"--- {pattern!r} @ {i+1} ---")
            for j in range(max(0, i - before), min(len(lines), i + after)):
                out.append(f"{j+1}: {lines[j].rstrip()[:150]}")
            out.append("")
            hits += 1
            if hits >= limit:
                break
    if hits == 0:
        out.append(f"--- {pattern!r}: NO HIT ---\n")


for pat in ("_ROADMAP_VALIDATION_SEEN", "_TASK_GRAPH_ALARM_SEEN", "_TASK_GRAPH_ALARM_SEEN =", "def _emit_roadmap_validation",
            "def _timed_advance", "def _declared_write_face", "def _audit_task_graph_problems",
            "def _stable_dependency_order", "class _WriteFaceWait", "_write_face_wait_reason"):
    show(pat)

out.append("=== `_is_in_flight` / `in_flight_keys` / `max_parallel_keys` current text ===")
for i, ln in enumerate(lines, 1):
    if "def _is_in_flight" in ln or "in_flight_keys = {" in ln or "max_parallel_keys" in ln or "max_workers_per_key" in ln:
        out.append(f"{i}: {ln.rstrip()[:150]}")

dest = REPO / ".agenticdoc/_scratch/evidence/mdc-m02-code-audit-20261014.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest, len(out), "lines")
