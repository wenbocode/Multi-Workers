"""Collect exact anchors for the MDC M-02 / M-03 cards."""

import pathlib
import re

ROOT = pathlib.Path(r"H:\git\Multi-Workers")
out = []


def dump(path, patterns, limit=400, label=""):
    p = ROOT / path
    if not p.exists():
        out.append(f"!! missing {path}")
        return
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    out.append(f"=== {path} {label} ({len(lines)} lines) ===")
    rx = re.compile("|".join(patterns))
    n = 0
    for i, ln in enumerate(lines, 1):
        if rx.search(ln):
            out.append(f"{i}: {ln.rstrip()[:150]}")
            n += 1
            if n >= limit:
                break


dump(
    "packages/multi-workers/autopilot/conductor.py",
    [r"_plan_task_order", r"def execute_loop", r"validate_roadmap", r"in_flight", r"beat\.", r"max_parallel_keys", r"13 \u952e", r"advance"],
    limit=90,
)
dump(
    "packages/multi-workers/autopilot/config.py",
    [r"max_parallel_keys", r"max_workers_per_key", r"default", r"min_value|min\b", r"_KEYS|KEY_ORDER|order"],
    limit=40,
)
dump(
    "packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts",
    [r"slotsUsed", r"max_parallel_keys|maxParallelKeys", r"parallel", r"cap"],
    limit=45,
)
dump(
    "packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts",
    [r"cap|slots|parallel|eff", r"\\u9762\\u677f|panel"],
    limit=30,
)
dump(
    "packages/multi-workers/test/fixtures/autopilot-config-corpus.json",
    [r"range-max-parallel-low", r"max_parallel_keys", r"\"id\""],
    limit=40,
)

out.append("")
out.append("=== 计数锁 20（parity/sync 测试里同时含 config 键数的文件）===")
for p in sorted((ROOT / "packages").rglob("*.test.ts")):
    try:
        t = p.read_text(encoding="utf-8", errors="replace")
    except Exception:
        continue
    if "max_parallel_keys" in t and re.search(r"\b20\b", t):
        out.append(f"{p.relative_to(ROOT)}")
for p in sorted((ROOT / "packages/multi-workers").glob("test*.py")):
    t = p.read_text(encoding="utf-8", errors="replace")
    if "max_parallel_keys" in t and re.search(r"\b20\b", t):
        out.append(f"{p.relative_to(ROOT)}")

dest = ROOT / ".agenticdoc/_scratch/evidence/mdc-anchors-20261014.txt"
dest.write_text("\n".join(out), encoding="utf-8")
print("wrote", dest, len(out), "lines")
