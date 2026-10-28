"""T10b probe/range observation script (read-only, isolated loopback only).

Run from anywhere: `python probe-observations.py`. It opens an isolated
contiguous local block outside the monitor range, never touches a shared
service, and closes every socket it opens.
"""

import os
import socket
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "packages", "multi-workers")))

import decision_monitor  # noqa: E402

HOST = decision_monitor.HOST

print("platform", sys.platform, "python", sys.version.split()[0])
print("PROBE_TIMEOUT_S", decision_monitor.PROBE_TIMEOUT_S)
print("REFUSED_ERRNOS", sorted(decision_monitor.REFUSED_ERRNOS))
print("PORT_RANGE", decision_monitor.PORT_RANGE)

sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
sock.bind((HOST, 0))
closed_port = sock.getsockname()[1]
sock.close()
started = time.time()
refused = decision_monitor.probe_recorded_port(closed_port)
print("real closed loopback", closed_port, refused, "elapsed %.2fs" % (time.time() - started))

listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
listener.bind((HOST, 0))
listener.listen(16)
serving_port = listener.getsockname()[1]
print("unrelated listener", serving_port, decision_monitor.probe_recorded_port(serving_port))
listener.close()

print("classify TimeoutError", decision_monitor.classify_connect_error(TimeoutError("t")))
print("classify ETIMEDOUT", decision_monitor.classify_connect_error(OSError(110, "t")))
print("classify EACCES", decision_monitor.classify_connect_error(OSError(13, "d")))
print("classify 10061", decision_monitor.classify_connect_error(OSError(10061, "refused")))

size = 100
chosen = None
rejected = []
for start in (25101, 30101, 35101, 40101, 45101, 47101, 52101, 55101, 28101, 38101):
    if start <= decision_monitor.PORT_RANGE[1] and start + size - 1 >= decision_monitor.PORT_RANGE[0]:
        rejected.append((start, "overlaps monitor range"))
        continue
    holders = []
    try:
        for offset in range(size):
            item = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                item.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                item.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
            item.bind((HOST, start + offset))
            item.listen(1)
            holders.append(item)
    except OSError as exc:
        for item in holders:
            item.close()
        rejected.append((start, type(exc).__name__))
        continue
    chosen = (start, holders)
    break

if chosen is None:
    print("no isolated 100-port block:", rejected)
    raise SystemExit(1)

start, holders = chosen
print("isolated block", f"{start}..{start + size - 1}", "held", len(holders), "rejected", rejected)
try:
    decision_monitor.bind_listener(project_id="T10b-evidence", port_range=(start, start + size - 1))
except decision_monitor.MonitorError as exc:
    print("bind_listener kind", exc.kind)
    print("attempted_count", exc.details["attempted_count"])
    print("attempted_echo", len(exc.details["attempted"]))
    print("error_class_sample", exc.details["attempted"][0]["error"])
alive = 0
for port in range(start, start + size):
    probe = socket.create_connection((HOST, port), timeout=3)
    probe.close()
    alive += 1
print("occupants still accepting", alive)
print("occupant sockets open", sum(1 for item in holders if item.fileno() != -1))
for item in holders:
    item.close()
