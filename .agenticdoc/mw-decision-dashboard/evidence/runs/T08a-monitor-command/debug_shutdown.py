import json
import os
import pathlib
import subprocess
import sys
import tempfile
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[5] / "packages" / "multi-workers"))
import decision_monitor  # noqa: E402

MW_PY = pathlib.Path(__file__).resolve().parents[5] / "packages" / "multi-workers" / "mw.py"

tmp = pathlib.Path(tempfile.mkdtemp())
root = tmp / "proj"
(root / ".agenticdoc" / "_autopilot").mkdir(parents=True)
env = dict(os.environ)
for key in ("TIMI_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY"):
    env.pop(key, None)
log = tmp / "child.log"
with log.open("wb") as handle:
    proc = subprocess.Popen(
        [sys.executable, str(MW_PY), "_decide_monitor_starter", "--project", str(root)],
        cwd=str(root),
        env=env,
        stdout=handle,
        stderr=handle,
    )
state = None
for _ in range(200):
    state, problem = decision_monitor.read_state(root)
    if state:
        break
    time.sleep(0.05)
print("state", state)
token = decision_monitor.read_secret(root)
print("token?", bool(token))
request = urllib.request.Request(
    f"http://127.0.0.1:{state['port']}/api/shutdown",
    data=b"{}",
    headers={decision_monitor.TOKEN_HEADER: token, "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=10) as response:
    print("status", response.status, response.read())
print("rc", proc.wait(timeout=20))
print("state after", decision_monitor.read_state(root))
print("secret after", decision_monitor.read_secret(root))
print("log", log.read_text(errors="replace"))
print("files", sorted(path.name for path in (root / ".mw").iterdir()))
