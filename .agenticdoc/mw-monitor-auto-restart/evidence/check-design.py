"""Read-only draft coverage verification; no runtime actions."""
import hashlib
import json
import pathlib
import re
import subprocess
import sys

key = pathlib.Path(__file__).resolve().parent.parent
root = key.parent.parent
spec = (key / "spec.md").read_text(encoding="utf-8")
design = (key / "design.md").read_text(encoding="utf-8")
acs = sorted(set(re.findall(r"^\| (AC-\d{3}) \|", spec, re.M)))
mapping = design.split("## §8 AC → VC 映射表\n", 1)[1].split("\n## §9", 1)[0]
mapped = sorted(set(re.findall(r"^\| (AC-\d{3}) \|", mapping, re.M)))
contracts = re.findall(r"^(VC-\d{3}):[\s\S]*?Source: (AC-\d{3})", design, re.M)
assert len(acs) == 8 and mapped == acs, (acs, mapped)
assert len(contracts) == 8 and sorted(ac for _, ac in contracts) == acs
proc = subprocess.run(
    [sys.executable, "-X", "utf8", str(root / ".agents/skills/agentic-task/scripts/check_mermaid.py"), str(key / "design.md")],
    cwd=root, check=False, capture_output=True,
)
print(proc.stdout.decode("utf-8"), end="")
print(proc.stderr.decode("utf-8"), end="", file=sys.stderr)
assert proc.returncode == 0, proc.returncode
print(json.dumps({"ac_ids": acs, "mapped_ids": mapped, "vc_count": len(contracts), "ac_coverage": "8/8", "spec_sha256": hashlib.sha256((key / "spec.md").read_bytes()).hexdigest(), "design_sha256": hashlib.sha256((key / "design.md").read_bytes()).hexdigest(), "mermaid_rc": proc.returncode, "scope": "draft documents only, not implementation verification"}, ensure_ascii=False))
