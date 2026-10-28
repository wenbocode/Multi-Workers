"""Inspect AC-014 (task.md creation vs lock) and AC-006 (doctor/read-only refusal surface)."""

import pathlib
import re

ROOT = pathlib.Path(r"H:\git\Multi-Workers")
out = []

# ── AC-014: order inside the conductor dispatch entry ────────────────────────
d = (ROOT / "packages/multi-workers/autopilot/dispatch.py").read_text(encoding="utf-8")
lines = d.splitlines()
out.append("=== AC-014: dispatch() 相关行（含锁 / task.md 写 / 队列行）===")
pat = re.compile(r"acquire_lock|render_task_md|write_text|mkdir|upsert|queue|def dispatch\b|def _write_face_verdict")
hits = [(i + 1, ln) for i, ln in enumerate(lines) if pat.search(ln) and not ln.strip().startswith("#")]
for i, ln in hits:
    if i > 1100:
        out.append(f"{i}: {ln.rstrip()[:150]}")

# ── AC-006: any read-only surface aggregating write-face refusals ────────────
out.append("")
out.append("=== AC-006: mw.py 中与 timeline / auto-decisions / write-face 相关的行 ===")
mw = (ROOT / "packages/multi-workers/mw.py").read_text(encoding="utf-8")
for i, ln in enumerate(mw.splitlines(), 1):
    if re.search(r"timeline|auto-decisions|write.face|refus", ln):
        out.append(f"{i}: {ln.rstrip()[:150]}")

out.append("")
out.append("=== AC-006: autopilot/*.py 里读 timeline 的地方 ===")
for p in sorted((ROOT / "packages/multi-workers").rglob("*.py")):
    if "test" in p.parts and "test" != p.parent.name:
        pass
    try:
        t = p.read_text(encoding="utf-8")
    except Exception:
        continue
    for i, ln in enumerate(t.splitlines(), 1):
        if re.search(r"timeline\.jsonl|_read_timeline|load_timeline|timeline_events", ln):
            out.append(f"{p.relative_to(ROOT)}:{i}: {ln.strip()[:140]}")

out.append("")
out.append("=== AC-006: doctor_report / cmd_doctor 的 section 生成点 ===")
mwc = (ROOT / "packages/multi-workers/mw_common.py").read_text(encoding="utf-8")
for i, ln in enumerate(mwc.splitlines(), 1):
    if re.search(r"^def doctor_report|^def .*_section|report\[|report\.update", ln):
        out.append(f"mw_common.py:{i}: {ln.rstrip()[:150]}")
for i, ln in enumerate(mw.splitlines(), 1):
    if re.search(r"^def cmd_doctor|report\[|_doctor_", ln):
        out.append(f"mw.py:{i}: {ln.rstrip()[:150]}")

out.append("")
out.append("=== 现有测试文件（doctor/audit/timeline）===")
for p in sorted((ROOT / "packages/multi-workers/test").glob("*.py")):
    out.append(f"  {p.name}")

out.append("")
out.append("=== TS 侧 auto-decisions 读取面（status-model.ts:1180-1240）===")
sm = (ROOT / "packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts").read_text(encoding="utf-8").splitlines()
for i in range(1179, min(1240, len(sm))):
    out.append(f"{i + 1}: {sm[i].rstrip()[:150]}")

dest = ROOT / ".agenticdoc/_scratch/evidence/wf-ac006-ac014-probe-20261014.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print(f"wrote {dest} ({dest.stat().st_size} bytes, {len(out)} lines)")
