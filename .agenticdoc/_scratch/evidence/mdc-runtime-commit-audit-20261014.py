"""Decide the two open items with evidence:

1. Does the built runtime actually contain this window's changes?
   (grep the shipped bundles for MDC/WFG markers + compare mtimes with src)
2. Is a per-file commit of "this window's files" possible, or do the shared
   files also carry other windows' uncommitted work?
"""

import datetime
import pathlib
import re
import subprocess

REPO = pathlib.Path(r"H:\git\Multi-Workers")

BUNDLES = [
    "packages/coding-agent/dist/extensions/agent-team-loop/index.js",
    "packages/multi-workers/dist/extensions/agent-team-loop.js",
]
MARKERS = {
    "MDC frontier (frontierSize)": "frontierSize",
    "MDC config key (max_workers_per_key)": "max_workers_per_key",
    "MDC dedup (duplicate-dispatch)": "duplicate-dispatch",
    "WFG write-face (WRITE_FACE)": "WRITE_FACE",
    "WFG parser (parseWriteFace)": "parseWriteFace",
    "widget order (widgetOrder)": "widgetOrder",
}


def mtime(p: pathlib.Path) -> str:
    return datetime.datetime.fromtimestamp(p.stat().st_mtime).strftime("%m-%d %H:%M:%S")


print("=== 1) 运行时产物是否已含本次改动 ===")
for rel in BUNDLES:
    p = REPO / rel
    if not p.exists():
        print(f"{rel}: MISSING")
        continue
    text = p.read_text(encoding="utf-8", errors="replace")
    print(f"{rel}\n  mtime={mtime(p)} size={p.stat().st_size}")
    for label, needle in MARKERS.items():
        print(f"    {label:<40} {'PRESENT' if needle in text else 'ABSENT'}")

print("\n=== 2) 源码改动面 vs 别 key 标记（提交面归因） ===")
CANDIDATES = [
    "packages/multi-workers/autopilot/config.py",
    "packages/multi-workers/autopilot/conductor.py",
    "packages/multi-workers/autopilot/dispatch.py",
    "packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts",
    "packages/multi-workers/mw.py",
]
FOREIGN = {
    "xkey (another window)": r"xkey",
    "mwgal (another window)": r"mwgal",
    "mwds (another window)": r"mwds",
    "worktree/junction (another window)": r"worktree_junction|worktree-junction|junction",
    "woc (another window)": r"\bwoc\b|readback",
    "mw-autopilot-slot-capacity": r"slot_capacity|msc-",
}
for rel in CANDIDATES:
    diff = subprocess.run(
        ["git", "diff", "-U0", "--", rel], cwd=REPO, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    ).stdout
    added = [ln[1:] for ln in diff.splitlines() if ln.startswith("+") and not ln.startswith("+++")]
    if not added:
        status = subprocess.run(["git", "status", "--porcelain", "--", rel], cwd=REPO,
                                capture_output=True, text=True, encoding="utf-8").stdout.strip()[:2]
        print(f"{rel}: no tracked diff ({status or 'clean'})")
        continue
    body = "\n".join(added)
    hits = [label for label, pat in FOREIGN.items() if re.search(pat, body, re.I)]
    print(f"{rel}: +{len(added)} lines | foreign markers: {hits or 'none'}")
