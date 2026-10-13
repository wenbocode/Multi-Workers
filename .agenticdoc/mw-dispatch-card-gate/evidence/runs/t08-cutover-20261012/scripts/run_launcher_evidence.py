"""T-08 runtime evidence driver: run the REAL service-layer launcher against a
hermetic fixture project and capture the raw result.

`launcher.py` is the service layer that owns the dispatch-envelope gate. This
driver starts it as a real child process (not an in-process mock) with a stub
``pi`` on PATH, lets it poll once or twice, then captures:

* the queue row status (`_workers.parallel`),
* whether a worker was actually spawned (the stub's spawn marker),
* the launcher's raw stderr/stdout (carries the T-14 aggregate alarm),
* the task's worker.log (carries the refusal reason + guidance).

Usage (repo root):
    python -X utf8 .../scripts/run_launcher_evidence.py <fixture-name> <evidence-tag>
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[6]
RUN = pathlib.Path(__file__).resolve().parents[1]
KEY = "mw-dispatch-card-gate"

name = sys.argv[1]
tag = sys.argv[2]
fixture = RUN / "fixture" / name
stub_dir = RUN / "stub" / name
stub_dir.mkdir(parents=True, exist_ok=True)
marker = stub_dir / "spawn-marker.txt"
if marker.exists():
    marker.unlink()

stub_cmd = (
    "@echo off\r\n"
    f'echo STUB_PI_SPAWNED> "{marker}"\r\n'
    f'echo argv=%*>> "{marker}"\r\n'
    f'echo PI_WORKER_TASK=%PI_WORKER_TASK%>> "{marker}"\r\n'
    "ping -n 9 127.0.0.1 >nul\r\n"
    "exit /b 0\r\n"
)
(stub_dir / "pi.cmd").write_text(stub_cmd, encoding="ascii")

env = dict(os.environ)
env["PATH"] = str(stub_dir) + os.pathsep + env.get("PATH", "")
env.setdefault("TIMI_API_KEY", "evidence-stub-key")
env["MW_AUTOPILOT_FILE"] = str(fixture / "absent-machine-config.json")
# The launcher writes Chinese refusal text; force UTF-8 so the captured file is
# byte-honest instead of locale-encoded (Windows cp936).
env["PYTHONIOENCODING"] = "utf-8"

launcher_log = RUN / f"{tag}.launcher.log"
queue = fixture / ".agenticdoc" / "_workers.parallel"

with launcher_log.open("w", encoding="utf-8") as log:
    proc = subprocess.Popen(
        [
            sys.executable, "-X", "utf8",
            str(REPO / "packages" / "multi-workers" / "launcher.py"),
            "--project", str(fixture),
            "--poll-interval", "1",
            "--providers", str(fixture / "providers.json"),
        ],
        stdout=log, stderr=subprocess.STDOUT, cwd=str(fixture), env=env,
    )
    deadline = time.time() + 8
    while time.time() < deadline:
        if marker.exists():
            break
        time.sleep(0.25)
    time.sleep(1.0)
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()

lines: list[str] = []
lines.append(
    "$ python -X utf8 "
    ".agenticdoc/mw-dispatch-card-gate/evidence/runs/t08-cutover-20261012/scripts/"
    f"run_launcher_evidence.py {name} {tag}"
)
lines.append(f"=== fixture: {fixture}")
lines.append("=== queue file (raw) ===")
lines.append(queue.read_text(encoding="utf-8").rstrip() if queue.exists() else "(missing)")
lines.append(f"=== spawn marker present: {marker.exists()} ===")
if marker.exists():
    lines.append(marker.read_text(encoding="utf-8").rstrip())
lines.append(f"=== launcher output ({launcher_log.name}, raw) ===")
lines.append(launcher_log.read_text(encoding="utf-8").rstrip())
for task_md in sorted((fixture / ".agenticdoc" / KEY / "workers").glob("*/task.md")):
    wlog = task_md.parent / "worker.log"
    if wlog.exists():
        lines.append(f"=== worker.log: {task_md.parent.name} (raw) ===")
        lines.append(wlog.read_text(encoding="utf-8").rstrip())

report = RUN / f"{tag}.txt"
report.write_text("\n".join(lines) + "\n", encoding="utf-8")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001 - display-only nicety
    pass
print(f"[wrote] {report}")
print("\n".join(lines))
