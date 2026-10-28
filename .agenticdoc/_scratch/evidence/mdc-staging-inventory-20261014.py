"""Precise staging inventory: which of my faces are dirty, what dist contains,
whether index.js would break if a partially-updated dist were committed."""

import pathlib
import re
import subprocess

REPO = pathlib.Path(r"H:\git\Multi-Workers")


def git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True,
                          encoding="utf-8", errors="replace").stdout


SRC = [
    "packages/multi-workers/autopilot/dispatch.py",
    "packages/multi-workers/autopilot/conductor.py",
    "packages/multi-workers/autopilot/config.py",
    "packages/multi-workers/autopilot/task_graph.py",
    "packages/multi-workers/autopilot/write_face.py",
    "packages/multi-workers/test_mdc_concurrency.py",
    "packages/multi-workers/test_mdc_e2e.py",
    "packages/multi-workers/test/fixtures/write-face-corpus.json",
    "packages/multi-workers/test/test_write_face_dispatch.py",
    "packages/multi-workers/test_rag_launcher.py",
    "packages/coding-agent/src/extensions/agent-team-loop/shared/write-face.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/autopilot/console.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts",
    "packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts",
    "packages/coding-agent/src/core/extensions/types.ts",
    "packages/coding-agent/src/modes/interactive/interactive-mode.ts",
    "packages/coding-agent/src/modes/rpc/rpc-mode.ts",
    "packages/coding-agent/src/modes/rpc/rpc-types.ts",
    "packages/coding-agent/test/suite/autopilot-concurrency-panel.test.ts",
    "packages/coding-agent/test/suite/autopilot-monitor.test.ts",
    "packages/coding-agent/test/suite/write-face.test.ts",
    "packages/coding-agent/test/interactive-mode-widget-order.test.ts",
    "packages/coding-agent/test/interactive-mode-status.test.ts",
    "packages/coding-agent/CHANGELOG.md",
    "packages/multi-workers/CHANGELOG.md",
]
out = ["## A. 计划的源码/测试面（porcelain）"]
st = {ln[3:]: ln[:2] for ln in git("status", "--porcelain=v1").splitlines() if len(ln) > 3}
for p in SRC:
    out.append(f"  {st.get(p, 'CLEAN(未改)')}  {p}")
out.append("")
out.append("## B. 我遗留在 test/suite 的临时探针（zz-*.tmp.test.ts）")
tmp = sorted(str(p.relative_to(REPO)) for p in (REPO / "packages/coding-agent/test/suite").glob("zz-*.ts"))
out += [f"  {t}  exists={ (REPO/t).is_file() }" for t in tmp] or ["  (none)"]
out.append("")
out.append("## C. .agenticdoc 里本 key 的记录状态")
for ln in git("status", "--porcelain=v1", "--", ".agenticdoc/mw-dynamic-concurrency",
              ".agenticdoc/mw-write-face-guard", ".agenticdoc/_index.parallel",
              ".agenticdoc/_project_log.md", ".agenticdoc/_pitfalls.md").splitlines():
    out.append("  " + ln)
out.append("")
out.append("## D. dist 变更统计")
for d in ("packages/coding-agent/dist", "packages/multi-workers/dist"):
    lines = [ln for ln in git("status", "--porcelain=v1", "--", d).splitlines() if ln.strip()]
    out.append(f"  {d}: {len(lines)} "
               f"(M={sum(1 for l in lines if l[:2]==' M')}, ??={sum(1 for l in lines if l[:2]=='??')})")
out.append("")
out.append("## E. dist 入口 index.js 是否 import 其它 window 的新模块（完整性判据）")
index_js = REPO / "packages/coding-agent/dist/extensions/agent-team-loop/index.js"
text = index_js.read_text(encoding="utf-8", errors="replace")
for mod in ("bash-segments", "worktree-junction-guard", "write-face", "implementation-gate"):
    out.append(f"  index.js imports {mod}: {mod in text}")
out.append("")
out.append("## F. .gitignore 命中（确认 dist 是否被忽略）")
out.append("  " + (git("check-ignore", "-v", "packages/coding-agent/dist/extensions/agent-team-loop/index.js").strip() or "(not ignored)"))

dest = REPO / ".agenticdoc/_scratch/evidence/mdc-staging-inventory-20261014.txt"
dest.write_text("\n".join(out) + "\n", encoding="utf-8")
print("wrote", dest.name)
