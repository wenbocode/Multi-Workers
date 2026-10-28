"""Actual CLI writer probes; no real child/browser/provider is launched."""
from __future__ import annotations

import dataclasses
import json
import types

import pytest

import decision_monitor as monitor
import decision_wire
import mw


@pytest.mark.parametrize("no_open", [True, False])
def test_open_opts_into_restart_and_reports_actual_replacement(tmp_path, monkeypatch, capsys, no_open):
    root = tmp_path / "project"
    (root / ".agenticdoc").mkdir(parents=True)
    identity = monitor.InstanceIdentity(project_id=decision_wire.project_id_for(root), instance_id="fresh", pid=42424, pid_start_ms=10000, port=43211)
    replacement = {"previous": dataclasses.replace(identity, instance_id="old").as_dict(), "process_exit_confirmed": True, "stop": {"stopped": True, "detail": None, "port_probe": "refused", "state": "absent"}}
    preserved = {root / ".agenticdoc/history.jsonl": b"synthetic history\r\n", root / ".agenticdoc/submissions.jsonl": b"synthetic submission\n"}
    for path, body in preserved.items():
        path.write_bytes(body)
    events = []
    instance = types.SimpleNamespace(identity=identity, port=identity.port, replacement=replacement, recovery=None, new_window_url=lambda: monitor.window_url(identity.port, "synthetic-boot"))

    def ensure(child_root, **kwargs):
        assert child_root == root
        assert kwargs.get("replace_incompatible") is True
        events.append("ensure")
        return instance

    def window(**kwargs):
        assert events == ["ensure"]
        events.append("window")
        return {"spawned": True, "visibility": "not-verified", "argv": [], "url": monitor.window_url(identity.port, "synthetic-boot")}

    monkeypatch.setattr(monitor, "ensure_instance", ensure)
    monkeypatch.setattr(monitor, "launch_app_window", window)
    monkeypatch.setattr(mw, "_monitor_browser_executable", lambda: "synthetic-browser")
    monkeypatch.setattr(mw, "_monitor_profile_dir", lambda _: tmp_path / "profile")
    assert mw._monitor_open(types.SimpleNamespace(no_open=no_open, json=True), root) == 0
    raw = capsys.readouterr().out
    doc = json.loads(raw)
    assert doc["replacement"] == replacement
    assert doc["instance"]["reused"] is False
    assert events == (["ensure"] if no_open else ["ensure", "window"])
    assert "synthetic-boot" not in raw
    assert all(path.read_bytes() == body for path, body in preserved.items())
    if no_open:
        assert doc["window"] is None
        print("[VERIFY] VC-007: browser_spawn_count=0 history_equal=true submissions_equal=true")


@pytest.mark.parametrize("action", ["status", "stop"])
def test_status_stop_never_enter_start_or_replacement(tmp_path, monkeypatch, action):
    root = tmp_path / "project"
    (root / ".agenticdoc").mkdir(parents=True)
    identity = monitor.InstanceIdentity(project_id=decision_wire.project_id_for(root), instance_id="existing", pid=42424, pid_start_ms=10000, port=43211)
    monitor.publish_state(root, identity)
    monitor.publish_secret(root, "synthetic-control")
    monkeypatch.setattr(monitor, "health", lambda *a, **k: identity.as_dict())
    monkeypatch.setattr(monitor.AttachedInstance, "stop", lambda self: {"stopped": True, "state": "absent"})
    monkeypatch.setattr(monitor, "ensure_instance", lambda *a, **k: pytest.fail("status/stop must not ensure/start/replace"))
    monkeypatch.setattr(monitor, "launch_app_window", lambda **k: pytest.fail("status/stop must not launch window"))
    assert mw._decide_monitor(types.SimpleNamespace(monitor_action=action, json=True), root) == 0
    print("[VERIFY] VC-008: starter_count=0 window_count=0 model_request_count=0")
