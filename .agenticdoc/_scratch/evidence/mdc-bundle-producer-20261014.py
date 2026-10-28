"""Who produces packages/multi-workers/dist/extensions/agent-team-loop.js ?"""
import pathlib
import re
import subprocess

REPO = pathlib.Path(r"H:\git\Multi-Workers")
out = subprocess.run(
    ["git", "grep", "-n", "--untracked", "-I", "-e", "agent-team-loop.js"],
    cwd=REPO, capture_output=True, text=True, encoding="utf-8", errors="replace",
).stdout
rows = [
    ln for ln in out.splitlines()
    if "node_modules" not in ln and "/dist/" not in ln and ".agenticdoc/" not in ln
]
lines = [f"{len(rows)} refs (excluding node_modules, dist, .agenticdoc)", ""]
lines += rows[:60]

# also look for the bundle-copy step in scripts and python
lines += ["", "=== scripts/ and *.py mentioning 'bundle' or copy of the extension ==="]
for pat in ("scripts/*.mjs", "packages/multi-workers/*.py", "packages/coding-agent/scripts/*"):
    for p in sorted(REPO.glob(pat)):
        text = p.read_text(encoding="utf-8", errors="replace")
        for i, ln in enumerate(text.splitlines(), 1):
            if re.search(r"agent-team-loop\.js|bundle", ln):
                lines.append(f"{p.relative_to(REPO)}:{i}: {ln.strip()[:180]}")

dest = REPO / ".agenticdoc/_scratch/evidence/mdc-bundle-producer-20261014.txt"
dest.write_text("\n".join(lines), encoding="utf-8")
print("wrote", dest.name, len(lines), "lines")
