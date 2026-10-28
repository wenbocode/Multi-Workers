"""PM closure check: CHANGELOG [Unreleased] content + commit-surface attribution."""

import pathlib
import subprocess

REPO = pathlib.Path(r"H:\git\Multi-Workers")
NL = chr(10)

for rel in ("packages/coding-agent/CHANGELOG.md", "packages/multi-workers/CHANGELOG.md"):
    t = (REPO / rel).read_text(encoding="utf-8")
    parts = t.split("## [Unreleased]", 1)
    body = parts[1].split(NL + "## [", 1)[0] if len(parts) > 1 else "(no [Unreleased] section)"
    print("=" * 74)
    print(f"{rel}  | Unreleased section = {len(body.strip())} B")
    print(body.strip()[:1500])

print("=" * 74)
print("=== 本 key 相关改动面（git status --porcelain）===")
out = subprocess.run(
    ["git", "status", "--porcelain"], cwd=REPO, capture_output=True, text=True,
    encoding="utf-8", errors="replace",
).stdout
for line in out.splitlines():
    print(line)

print("=" * 74)
print("=== dist 场景核查 ===")
dtest = REPO / "packages/coding-agent/test/suite/mwds-t23-cutover-recheck.test.ts"
if dtest.exists():
    for i, ln in enumerate(dtest.read_text(encoding="utf-8").splitlines(), 1):
        if "sha" in ln.lower() and len(ln) < 200:
            print(f"{i}: {ln.strip()[:150]}")
dist = REPO / "packages/multi-workers/dist/extensions/agent-team-loop.js"
if dist.exists():
    import datetime, hashlib
    print("dist size:", dist.stat().st_size,
          "mtime:", datetime.datetime.fromtimestamp(dist.stat().st_mtime).strftime("%m-%d %H:%M:%S"))
    print("dist sha256:", hashlib.sha256(dist.read_bytes()).hexdigest().upper())
