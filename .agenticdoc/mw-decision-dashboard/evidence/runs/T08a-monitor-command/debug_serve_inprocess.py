import json
import pathlib
import sys
import tempfile
import threading
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[5] / "packages" / "multi-workers"))
import decision_monitor  # noqa: E402

tmp = pathlib.Path(tempfile.mkdtemp())
root = tmp / "proj"
(root / ".agenticdoc" / "_autopilot").mkdir(parents=True)

result: dict[str, object] = {}


def run() -> None:
    try:
        result["rc"] = decision_monitor.serve(root)
    except BaseException as exc:  # noqa: BLE001
        result["exc"] = repr(exc)


thread = threading.Thread(target=run, daemon=True)
thread.start()
state = None
for _ in range(200):
    state, problem = decision_monitor.read_state(root)
    if state:
        break
    time.sleep(0.05)
print("state", state)
token = decision_monitor.read_secret(root)
print("token?", bool(token))
instance_identity = state["instance_id"]
request = urllib.request.Request(
    f"http://127.0.0.1:{state['port']}/api/shutdown",
    data=b"{}",
    headers={decision_monitor.TOKEN_HEADER: token, "Content-Type": "application/json"},
    method="POST",
)
with urllib.request.urlopen(request, timeout=10) as response:
    print("status", response.status, response.read())
thread.join(timeout=30)
print("alive", thread.is_alive(), result)
print("state after", decision_monitor.read_state(root))
print("secret after", decision_monitor.read_secret(root))
print("files", sorted(path.name for path in (root / ".mw").iterdir()))
