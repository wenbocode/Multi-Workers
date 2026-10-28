"""After `mw build --install`: prove the artifacts now carry this window's work
and re-run the suites that were red *because* the dist was stale."""

import hashlib
import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(r"H:\git\Multi-Workers")
ARTIFACTS = [
    REPO / "packages/multi-workers/dist/extensions/agent-team-loop.js",
    pathlib.Path(r"C:\Users\wenbozhou\.pi\agent\extensions\agent-team-loop.js"),
]
MARKERS = {
    "MDC frontier (frontierSize)": "frontierSize",
    "MDC key (max_workers_per_key)": "max_workers_per_key",
    "MDC dedup (duplicate-dispatch)": "duplicate-dispatch",
    "WFG write-face (WRITE_FACE)": "WRITE_FACE",
    "WFG parser (parseWriteFace)": "parseWriteFace",
    "widget order (widgetOrder)": "widgetOrder",
    "MDC task graph (deps)": "TASK_GRAPH",
}
out = []
for path in ARTIFACTS:
    if not path.exists():
        out.append(f"{path}: MISSING")
        continue
    text = path.read_text(encoding="utf-8", errors="replace")
    sha = hashlib.sha256(path.read_bytes()).hexdigest().upper()
    out.append(f"{path}\n  size={path.stat().st_size} sha256={sha}")
    for label, needle in MARKERS.items():
        out.append(f"    {label:<34} {'PRESENT' if needle in text else 'ABSENT'}")

# the pinned sha in the other key's frozen test
frozen = REPO / "packages/coding-agent/test/suite/mwds-t23-cutover-recheck.test.ts"
m = re.search(r'EXPECTED_BUNDLE_SHA = "([0-9A-F]{64})"', frozen.read_text(encoding="utf-8"))
out.append(f"\npinned EXPECTED_BUNDLE_SHA = {m.group(1) if m else '?'}")

print("\n".join(out))
(REPO / ".agenticdoc/_scratch/evidence/mdc-postbuild-markers-20261014.txt").write_text(
    "\n".join(out), encoding="utf-8")

print("\n=== 复跑此前因 dist 陈旧而红的用例 ===")
runs = [
    (REPO / "packages/multi-workers", [sys.executable, "-m", "pytest", "-q", "-rf",
     "test_mwds_t27_service_envelope.py::TestCrossLanguageParity::test_python_mirror_matches_the_real_ts_judge",
     "test_mwds_t29_producer_signal.py::TestParity::test_python_judge_matches_the_real_ts_judge",
     "test_rag_launcher.py", "test_rag_init.py"]),
]
for cwd, cmd in runs:
    r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    tail = [ln for ln in (r.stdout or "").splitlines() if re.search(r"(passed|failed|error)", ln, re.I)]
    print(f"{' '.join(cmd[3:])[:90]}  -> exit={r.returncode}")
    print("   " + " | ".join(tail[-3:])[:300])
