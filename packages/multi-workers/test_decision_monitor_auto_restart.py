"""Hermetic restart regressions: real orchestration, synthetic OS/stop boundary."""
from __future__ import annotations

import dataclasses
import inspect
import json
import os
import pathlib
import socket
import subprocess
import sys
import time
import types

import pytest

import decision_monitor as monitor
import decision_wire


@pytest.fixture
def scenario(tmp_path, monkeypatch):
    root = tmp_path / "project"
    (root / ".agenticdoc").mkdir(parents=True)
    old = monitor.InstanceIdentity(
        project_id=decision_wire.project_id_for(root), instance_id="old-instance",
        pid=424242, pid_start_ms=100000, port=43111, code_fingerprint="old-code",
    )
    monitor.publish_state(root, old)
    monitor.publish_secret(root, "synthetic-control")
    original = {p: p.read_bytes() for p in (monitor.state_path(root), monitor.secret_path(root))}
    sentinel = root / ".agenticdoc" / "history.jsonl"
    sentinel.write_bytes(b"history\r\n\xe4\xb8\xad\n")
    submissions = root / ".agenticdoc" / "submissions.jsonl"
    submissions.write_bytes(b"synthetic submission\r\n")
    monkeypatch.setattr(monitor.os, "kill", lambda *a, **k: pytest.fail("no process signal allowed"))
    monkeypatch.setattr(monitor.subprocess, "Popen", lambda *a, **k: pytest.fail("unit replacement must not spawn"))
    events = []
    state = {"alive": "alive", "start": old.pid_start_ms, "time": 0.0, "stopped": False, "server_cleanup": False, "caller_deletes": 0}
    original_unlink = pathlib.Path.unlink

    def unlink(path, *args, **kwargs):
        if path in original and not state["server_cleanup"]:
            state["caller_deletes"] += 1
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "unlink", unlink)

    def sleep(seconds):
        events.append("sleep")
        state["time"] += seconds

    def alive(pid):
        if pid == old.pid:
            events.append("exit-probe" if state["stopped"] else "liveness")
            return state["alive"]
        return "alive"

    def health(port, token, **kwargs):
        assert port == old.port and token == "synthetic-control"
        events.append("health")
        return old.as_dict()

    def stop(attached):
        assert attached.identity == old and attached.control_token == "synthetic-control"
        assert monitor.start_lock_path(root).exists()
        events.append("shutdown")
        state["server_cleanup"] = True
        try:
            monitor.state_path(root).unlink()
            monitor.secret_path(root).unlink()
        finally:
            state["server_cleanup"] = False
        state.update(alive="dead", stopped=True)
        return {"stopped": True, "detail": None, "port_probe": "refused", "state": "absent", "instance_id": old.instance_id, "port": old.port}

    fresh = dataclasses.replace(old, instance_id="new-instance", pid=434343, code_fingerprint=monitor.CODE_FINGERPRINT)

    def starter(child_root, deps, port_range, clock):
        assert child_root == root and monitor.start_lock_path(root).exists()
        assert state["alive"] == "dead"
        assert not monitor.state_path(root).exists() and not monitor.secret_path(root).exists()
        events.append("start")
        monitor.publish_secret(root, "synthetic-new")
        monitor.publish_state(root, fresh)
        return types.SimpleNamespace(port=fresh.port, control_token="synthetic-new", identity=fresh, _require_identity=lambda: fresh)

    def wait_health(*args, **kwargs):
        events.append("new-health")
        return True, None

    monkeypatch.setattr(monitor, "health", health)
    monkeypatch.setattr(monitor.AttachedInstance, "stop", stop)
    monkeypatch.setattr(monitor, "wait_health", wait_health)
    monkeypatch.setattr(monitor.time, "monotonic", lambda: state["time"])
    monkeypatch.setattr(monitor, "_move_aside", lambda *a, **k: pytest.fail("restart must not move state/secret"))
    monkeypatch.setattr(monitor, "probe_recorded_port", lambda port: {"result": "refused", "port": port})

    def ensure(opt_in=True):
        # Before implementation exercise the existing refusal, not missing-keyword TypeError.
        extra = {"replace_incompatible": opt_in} if "replace_incompatible" in inspect.signature(monitor.ensure_instance).parameters else {}
        return monitor.ensure_instance(root, deps=monitor.MonitorDeps(), starter=starter, alive_state_probe=alive, start_ms_probe=lambda pid: state["start"], sleep=sleep, **extra)

    return types.SimpleNamespace(root=root, old=old, original=original, sentinel=sentinel, events=events, state=state, ensure=ensure, starter=starter)


def test_authenticated_replacement_waits_for_old_exit_then_starts_once(scenario):
    row = scenario.ensure()
    assert scenario.events.index("health") < scenario.events.index("shutdown") < scenario.events.index("exit-probe") < scenario.events.index("start") < scenario.events.index("new-health")
    assert scenario.events.count("shutdown") == scenario.events.count("start") == 1
    assert row.replacement["previous"]["instance_id"] == scenario.old.instance_id
    assert row.replacement["process_exit_confirmed"] is True
    assert scenario.sentinel.read_bytes() == b"history\r\n\xe4\xb8\xad\n"
    assert (scenario.root / ".agenticdoc/submissions.jsonl").read_bytes() == b"synthetic submission\r\n"
    assert "synthetic-control" not in json.dumps(row.replacement)
    print("[VERIFY] VC-003: replacement_count=1 exit_before_start=true")


def test_low_level_default_still_refuses_incompatible(scenario):
    with pytest.raises(monitor.MonitorError) as exc:
        scenario.ensure(opt_in=False)
    assert exc.value.kind == "incompatible-instance"
    assert "shutdown" not in scenario.events and "start" not in scenario.events
    for path, data in scenario.original.items():
        assert path.read_bytes() == data


@pytest.mark.parametrize("result", [
    {"stopped": False, "detail": "refused", "port_probe": "connected", "state": "unknown"},
    {"stopped": True, "detail": "request refused", "port_probe": "refused", "state": "absent"},
    {"stopped": True, "detail": None, "port_probe": "unknown", "state": "absent"},
    {"stopped": True, "detail": None, "port_probe": "refused", "state": "retained"},
    {"stopped": True, "detail": None, "port_probe": "refused", "state": "foreign"},
])
def test_non_strict_stop_results_never_start(scenario, monkeypatch, result):
    monkeypatch.setattr(monitor.AttachedInstance, "stop", lambda self: result)
    with pytest.raises(monitor.MonitorError) as exc:
        scenario.ensure()
    assert exc.value.kind == "stop-failed"
    assert "start" not in scenario.events
    assert scenario.state["caller_deletes"] == 0
    for path, data in scenario.original.items():
        assert path.read_bytes() == data
    print("[VERIFY] VC-005: replacement_count=0 kill_count=0 caller_delete_count=0")


@pytest.mark.parametrize("after", ["alive", "unknown"])
def test_closed_port_does_not_replace_a_live_or_unknown_old_process(scenario, monkeypatch, after):
    original_stop = monitor.AttachedInstance.stop

    def stop(self):
        result = original_stop(self)
        scenario.state["alive"] = after
        return result

    monkeypatch.setattr(monitor.AttachedInstance, "stop", stop)
    with pytest.raises(monitor.MonitorError) as exc:
        scenario.ensure()
    assert exc.value.kind in ("stop-failed", "instance-unknown")
    assert "start" not in scenario.events
    assert scenario.state["time"] <= 10.01


@pytest.mark.parametrize("problem", ["missing-secret", "bad-health", "wrong-identity", "foreign-project", "unknown-liveness"])
def test_auth_and_identity_failure_before_shutdown(scenario, monkeypatch, problem):
    if problem == "missing-secret":
        monitor.secret_path(scenario.root).unlink()
    elif problem == "bad-health":
        monkeypatch.setattr(monitor, "health", lambda *a, **k: None)
    elif problem == "wrong-identity":
        monkeypatch.setattr(monitor, "health", lambda *a, **k: {**scenario.old.as_dict(), "instance_id": "different"})
    elif problem == "foreign-project":
        monitor.publish_state(scenario.root, dataclasses.replace(scenario.old, project_id="foreign"))
    else:
        scenario.state["alive"] = "unknown"
    before = {p: p.read_bytes() for p in scenario.root.joinpath(".mw").glob("decide-monitor.*")}
    with pytest.raises(monitor.MonitorError):
        scenario.ensure()
    assert "shutdown" not in scenario.events and "start" not in scenario.events
    assert all(path.read_bytes() == data for path, data in before.items())
    print("[VERIFY] VC-004: shutdown_count=0 starter_count=0 preserved=true")


def test_secret_changed_during_health_cannot_be_stopped(scenario, monkeypatch):
    def health(*args, **kwargs):
        monitor.publish_secret(scenario.root, "new-owner-control")
        return scenario.old.as_dict()
    monkeypatch.setattr(monitor, "health", health)
    with pytest.raises(monitor.MonitorError) as exc:
        scenario.ensure()
    assert exc.value.kind == "instance-unknown"
    assert "shutdown" not in scenario.events and "start" not in scenario.events
    assert monitor.read_secret(scenario.root) == "new-owner-control"


def test_foreign_state_appearing_after_stop_is_preserved(scenario, monkeypatch):
    original_stop = monitor.AttachedInstance.stop
    foreign = dataclasses.replace(scenario.old, instance_id="foreign-after-stop")

    def stop(self):
        result = original_stop(self)
        monitor.publish_state(scenario.root, foreign)
        monitor.publish_secret(scenario.root, "foreign-secret")
        return result

    monkeypatch.setattr(monitor.AttachedInstance, "stop", stop)
    with pytest.raises(monitor.MonitorError) as exc:
        scenario.ensure()
    assert exc.value.kind == "instance-unknown"
    assert "start" not in scenario.events
    assert monitor.read_state(scenario.root)[0] == foreign.as_dict()
    assert monitor.read_secret(scenario.root) == "foreign-secret"


def test_second_open_under_restart_lock_cannot_start(scenario, monkeypatch):
    original_stop = monitor.AttachedInstance.stop

    def stop(self):
        with pytest.raises(monitor.MonitorError) as exc:
            scenario.ensure()
        assert exc.value.kind == "start-lock-conflict"
        return original_stop(self)

    monkeypatch.setattr(monitor.AttachedInstance, "stop", stop)
    scenario.ensure()
    assert scenario.events.count("start") == 1
    print("[VERIFY] VC-006: active_replacement_count=1 contender_error=start-lock-conflict")


@pytest.mark.parametrize("filename", list(monitor.ASSET_FILES.values()))
def test_individual_dashboard_asset_edits_change_fingerprint(tmp_path, monkeypatch, filename):
    module = tmp_path / "decision_monitor.py"
    module.write_bytes(b"synthetic module\n")
    for name in monitor.ASSET_FILES.values():
        (tmp_path / name).write_bytes(b"synthetic asset\n")
    monkeypatch.setattr(monitor, "__file__", str(module))
    monkeypatch.setattr(monitor, "ASSET_DIR", tmp_path)
    before = monitor._compute_code_fingerprint()
    assert before == monitor._compute_code_fingerprint()
    (tmp_path / filename).write_bytes(b"edited asset\n")
    assert before != monitor._compute_code_fingerprint()


def test_missing_fingerprint_asset_fails_explicitly(tmp_path, monkeypatch):
    module = tmp_path / "decision_monitor.py"
    module.write_bytes(b"module")
    monkeypatch.setattr(monitor, "__file__", str(module))
    monkeypatch.setattr(monitor, "ASSET_DIR", tmp_path)
    with pytest.raises(monitor.MonitorError) as exc:
        monitor._compute_code_fingerprint()
    assert exc.value.kind == "instance-unknown"


def test_foreign_listener_after_old_exit_reports_partial_truth(scenario, monkeypatch):
    monkeypatch.setattr(monitor, "probe_recorded_port", lambda port: {"result": "connected"})
    with pytest.raises(monitor.MonitorError) as exc:
        scenario.ensure()
    assert exc.value.kind == "instance-unknown"
    assert "start" not in scenario.events
    assert exc.value.details["replacement"]["process_exit_confirmed"] is True


def test_delayed_old_exit_is_waited_for_before_start(scenario, monkeypatch):
    original = monitor._identity_liveness
    count = {"post_stop": 0}

    def liveness(identity, **kwargs):
        if scenario.state["stopped"]:
            count["post_stop"] += 1
            if count["post_stop"] <= 3:
                return "alive"
        return original(identity, **kwargs)

    monkeypatch.setattr(monitor, "_identity_liveness", liveness)
    scenario.ensure()
    assert scenario.state["time"] >= 0.15
    assert scenario.events.count("start") == 1


def test_starter_failure_does_not_claim_old_instance_is_running(scenario, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("synthetic starter refusal")
    monkeypatch.setattr(monitor, "_default_starter", fail)
    with pytest.raises(monitor.MonitorError) as exc:
        monitor.ensure_instance(
            scenario.root, deps=monitor.MonitorDeps(), replace_incompatible=True,
            alive_state_probe=lambda pid: scenario.state["alive"],
            start_ms_probe=lambda pid: scenario.old.pid_start_ms,
        )
    assert exc.value.kind == "starter-failed"
    assert exc.value.details["replacement"]["process_exit_confirmed"] is True
    assert not monitor.state_path(scenario.root).exists()


def test_secret_existence_uncertainty_does_not_overwrite_foreign_material(scenario, monkeypatch):
    original_stop = monitor.AttachedInstance.stop
    original_exists = pathlib.Path.exists

    def stop(self):
        result = original_stop(self)
        monitor.publish_secret(scenario.root, "foreign-secret")
        return result

    # Python exists() can suppress metadata errors; it is not an absence proof.
    def exists(path):
        return False if path == monitor.secret_path(scenario.root) else original_exists(path)

    monkeypatch.setattr(monitor.AttachedInstance, "stop", stop)
    monkeypatch.setattr(pathlib.Path, "exists", exists)
    with pytest.raises(monitor.MonitorError) as exc:
        scenario.ensure()
    assert exc.value.kind == "instance-unknown"
    assert "start" not in scenario.events
    assert monitor.read_secret(scenario.root) == "foreign-secret"


def test_automatic_self_process_replacement_refuses_before_shutdown(scenario, monkeypatch):
    self_identity = dataclasses.replace(scenario.old, pid=os.getpid())
    monitor.publish_state(scenario.root, self_identity)
    monkeypatch.setattr(monitor, "health", lambda *a, **k: self_identity.as_dict())
    with pytest.raises(monitor.MonitorError) as exc:
        scenario.ensure()
    assert exc.value.kind == "instance-unknown"
    assert "shutdown" not in scenario.events and "start" not in scenario.events


def test_empty_project_starts_then_compatible_instance_reuses(tmp_path):
    root = tmp_path / "project"
    (root / ".agenticdoc").mkdir(parents=True)
    with socket.socket() as sock:
        sock.bind((monitor.HOST, 0))
        port = sock.getsockname()[1]
    instance = monitor.ensure_instance(root, deps=monitor.MonitorDeps(), port_range=(port, port), replace_incompatible=True)
    try:
        original_state = monitor.state_path(root).read_bytes()
        original_secret = monitor.secret_path(root).read_bytes()
        reused = monitor.ensure_instance(root, deps=monitor.MonitorDeps(), replace_incompatible=True)
        assert isinstance(reused, monitor.AttachedInstance)
        assert reused.identity == instance.identity
        assert monitor.state_path(root).read_bytes() == original_state
        assert monitor.secret_path(root).read_bytes() == original_secret
        print("[VERIFY] VC-001: starter_count=1 healthy=true")
        print("[VERIFY] VC-002: reused=true shutdown_count=0 starter_count=0")
    finally:
        instance.stop()


def test_detached_synthetic_old_server_exits_before_real_replacement(tmp_path):
    # Synthetic stand-in, random loopback port, no provider/credential factories.
    root = tmp_path / "project"
    (root / ".agenticdoc").mkdir(parents=True)
    sentinel = root / ".agenticdoc/history.jsonl"
    sentinel.write_bytes(b"synthetic history\r\n")
    script = tmp_path / "old_server.py"
    script.write_text('''import http.server
import json
import os
import pathlib
import sys
import threading
sys.path.insert(0, sys.argv[2])
import decision_monitor as monitor
import decision_wire
import mw_common
root = pathlib.Path(sys.argv[1])
token = "synthetic-old-control"
identity = None
class Handler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass
    def reply(self, data):
        if self.headers.get(monitor.TOKEN_HEADER) != token:
            self.send_error(401)
            return False
        payload = json.dumps({"ok": True, "data": data}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()
        return True
    def do_GET(self):
        if self.path == "/api/health":
            self.reply(identity.as_dict())
        else:
            self.send_error(404)
    def do_POST(self):
        if self.path == "/api/shutdown" and self.reply({"stopping": True}):
            threading.Thread(target=server.shutdown, daemon=True).start()
        else:
            self.send_error(404)
server = http.server.ThreadingHTTPServer((monitor.HOST, 0), Handler)
identity = monitor.InstanceIdentity(project_id=decision_wire.project_id_for(root), instance_id="synthetic-old", pid=os.getpid(), pid_start_ms=mw_common.process_start_ms(os.getpid()), port=server.server_port, code_fingerprint="synthetic-old-code")
monitor.publish_secret(root, token)
monitor.publish_state(root, identity)
timer = threading.Timer(15, server.shutdown)
timer.daemon = True
timer.start()
try:
    server.serve_forever(poll_interval=0.02)
finally:
    timer.cancel()
    recorded, problem = monitor.read_state(root)
    if problem is None and recorded is not None and recorded["instance_id"] == identity.instance_id:
        monitor.state_path(root).unlink()
        monitor.secret_path(root).unlink()
    server.server_close()
''', encoding="utf-8", newline="\n")
    proc = subprocess.Popen([sys.executable, "-X", "utf8", str(script), str(root), str(pathlib.Path(monitor.__file__).parent)], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    fresh = None
    try:
        deadline = time.monotonic() + 10
        while True:
            old_state, problem = monitor.read_state(root)
            if old_state is not None:
                break
            assert proc.poll() is None, "synthetic old server exited before publication"
            assert time.monotonic() < deadline
            time.sleep(0.01)
        old = monitor.identity_from_state(old_state)
        assert old.pid == proc.pid
        with socket.socket() as sock:
            sock.bind((monitor.HOST, 0))
            port = sock.getsockname()[1]

        def alive(pid):
            if pid == proc.pid:
                proc.poll()  # reap our own test child on POSIX too
            return monitor.mw_common.process_alive_state(pid)

        def starter(child_root, deps, port_range, clock):
            assert proc.poll() == 0, "new listener must not start before old child exits"
            return monitor.MonitorInstance(child_root, deps=deps, port_range=(port, port)).start()

        fresh = monitor.ensure_instance(root, deps=monitor.MonitorDeps(), starter=starter, alive_state_probe=alive, replace_incompatible=True)
        assert fresh.replacement["process_exit_confirmed"] is True
        assert fresh.identity.instance_id != old.instance_id
        assert monitor.health(fresh.port, fresh.control_token)["instance_id"] == fresh.identity.instance_id
        assert sentinel.read_bytes() == b"synthetic history\r\n"
        print("[VERIFY] VC-003: detached_old_exit_before_start=true")
    finally:
        if fresh is not None:
            fresh.stop()
        # Timer gives a bounded graceful exit on assertion failure; never kill.
        stdout, stderr = proc.communicate(timeout=25)
        assert proc.returncode == 0, (stdout, stderr)
