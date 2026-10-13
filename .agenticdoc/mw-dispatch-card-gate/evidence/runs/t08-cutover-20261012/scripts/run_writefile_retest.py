"""T-08 requirement 3: runtime retest of the ``[WRITE_FILE]`` change event.

The change-ledger event is emitted by the worker-mode extension at runtime. The
resident pi window that dispatched this worker loaded the pre-cutover bundle, so
its own ``trace.log`` cannot show the event; a FRESH pi process loads the
freshly installed global bundle (``mw build --install``).  This driver therefore
spawns one tiny real coding worker on a hermetic fixture and watches its
``trace.log`` for the machine event.

It writes nothing into the repo tree: the fixture lives under this evidence run
directory.  The worker is asked to perform exactly one ``write`` and is killed
as soon as ``[WRITE_FILE]`` appears, so the retest is bounded and minimal.

Run (repo root):
    python -X utf8 .../scripts/run_writefile_retest.py
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[6]
RUN = pathlib.Path(__file__).resolve().parents[1]
KEY = "mw-dispatch-card-gate"
WORKER = "mwd-writefile-retest"
MODEL = "deepseek-v4.1-flash"

fixture = RUN / "fixture" / "writefile"
task_dir = fixture / ".agenticdoc" / KEY / "workers" / WORKER
if fixture.exists():
    shutil.rmtree(fixture)
task_dir.mkdir(parents=True)

task_md = task_dir / "task.md"
rel_scope = f".agenticdoc/{KEY}/workers/{WORKER}"
task_md.write_text(
    "---\n"
    "type: coding\n"
    "phase: EXECUTE\n"
    f"write_scope: {rel_scope}\n"
    "---\n"
    "\n"
    "<!-- mw-write-surface: v1 -->\n"
    f"- 允许写：本任务目录下的任何文件（write_scope: {rel_scope}）\n"
    "- 不得写：本任务目录之外的任何路径\n"
    "- 越界后果：运行期写面守卫 block + [TOOL_ERR]\n"
    "<!-- /mw-write-surface: v1 -->\n"
    "\n"
    "## 上下文\n"
    "\n"
    "cutover 后 [WRITE_FILE] 变更事件的运行期复测。极小任务：仅需一次成功写入。\n"
    "\n"
    "## 要求\n"
    "\n"
    "用 write 工具在本任务目录内新建 notes.txt，内容为一行 `cutover-writefile-retest`。\n"
    "不要做其它事，完成后立即结束。\n"
    "\n"
    "## 交付格式\n"
    "\n"
    "- 产物：本任务目录下的 notes.txt。\n"
    f"- 写入允许面：{rel_scope}\n"
    "- 写入禁止面：本任务目录之外\n"
    "- 验收命令：读取 trace.log，须含 `[WRITE_FILE] path=...notes.txt`\n"
    "- 改动历史：trace.log 的写入事件\n",
    encoding="utf-8",
    newline="\n",
)

env = {k: v for k, v in os.environ.items() if not k.startswith("PI_")}
env["PI_WORKER_TASK"] = str(task_md)
env["TIMI_API_KEY"] = os.environ.get("TIMI_API_KEY", "")
env["PYTHONIOENCODING"] = "utf-8"

pi = shutil.which("pi")
assert pi, "pi CLI not found on PATH"

starter = (
    f"Read your task file at {task_md.resolve()} and execute it end-to-end. "
    "It is self-contained: full instructions, context and acceptance criteria. "
    "Do not ask for the task body; report results when done. "
    "Your final reply MUST open with a one-line conclusion: status plus key result or blocker."
)

stdout_path = RUN / "writefile-retest.worker-stdout.log"
trace_path = task_dir / "trace.log"
started = time.time()
with stdout_path.open("w", encoding="utf-8") as out:
    proc = subprocess.Popen(
        [pi, "--provider", "timi", "--model", MODEL, "-p", starter],
        stdout=out, stderr=subprocess.STDOUT, cwd=str(fixture), env=env,
    )
    found = False
    deadline = time.time() + 240
    while time.time() < deadline:
        if trace_path.exists() and "[WRITE_FILE]" in trace_path.read_text(
            encoding="utf-8", errors="replace"
        ):
            found = True
            break
        if proc.poll() is not None:
            break
        time.sleep(2)
    rc = proc.poll()
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()

lines = [
    f"$ python -X utf8 {RUN.name}/scripts/run_writefile_retest.py",
    f"=== fresh pi process (new global bundle) pid={proc.pid} rc={rc} found_write_file={found} elapsed={time.time() - started:.1f}s",
    f"=== fixture task.md: {task_md}",
    "=== trace.log (raw) ===",
    trace_path.read_text(encoding="utf-8").rstrip() if trace_path.exists() else "(missing)",
    "=== worker stdout (raw, tail) ===",
]
stdout = stdout_path.read_text(encoding="utf-8", errors="replace")
lines.append("\n".join(stdout.rstrip().splitlines()[-40:]))
report = RUN / "writefile-retest.txt"
report.write_text("\n".join(lines) + "\n", encoding="utf-8")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001
    pass
print(f"[wrote] {report} (found_write_file={found})")
print("\n".join(lines))
