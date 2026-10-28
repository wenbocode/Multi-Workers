"""Dump MDC spec ACs + the 4 counting-lock files' assertions mentioning 20 keys."""

import pathlib
import re

ROOT = pathlib.Path(r"H:\git\Multi-Workers")
KEY = ROOT / ".agenticdoc/mw-dynamic-concurrency"
out = []

spec = (KEY / "spec.md").read_text(encoding="utf-8")
out.append("=== MDC spec AC lines ===")
for ln in spec.splitlines():
    if re.match(r"^\s*\|?\s*\**AC-\d{3}", ln):
        out.append(ln.strip()[:400])

out.append("")
out.append("=== counting-lock files: lines with 20 / key-count assertions ===")
for rel in [
    "packages/multi-workers/test_autopilot_config.py",
    "packages/multi-workers/test_mwgal_t12_stage_close_auto.py",
    "packages/multi-workers/test_mwgal_t15_reattest_confirm.py",
    "packages/coding-agent/test/suite/autopilot-console.test.ts",
]:
    p = ROOT / rel
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    out.append(f"--- {rel} ({len(lines)}) ---")
    n = 0
    for i, ln in enumerate(lines, 1):
        if re.search(r"\b20\b|\b13\b|max_parallel_keys|len\(.*keys|21", ln):
            out.append(f"{i}: {ln.rstrip()[:140]}")
            n += 1
            if n > 22:
                break

dest = ROOT / ".agenticdoc/_scratch/evidence/mdc-acs-20261014.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest, len(out))
