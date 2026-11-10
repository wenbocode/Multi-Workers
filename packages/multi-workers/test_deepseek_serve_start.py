"""Default native DeepSeek must not boot the optional legacy proxy."""
import argparse
import json
import pathlib

import pytest

import mw
import mw_common


@pytest.mark.parametrize("enabled,explicit_port,expected_proxy", [
    (False, None, False), (True, None, True), (False, 27004, True),
])
def test_deepseek_proxy_is_explicit(monkeypatch, tmp_path, enabled, explicit_port, expected_proxy):
    config = mw_common.load_providers(pathlib.Path(__file__).with_name("providers.json"))
    assert config["providers"]["deepseek"] == mw_common._DEFAULT_CONFIG["providers"]["deepseek"]
    assert config["providers"]["deepseek"]["proxy_autostart"] is False
    for name, credential in config["credentials"].items():
        credential["sources"] = [{"env": f"TEST_{name}"}]
        monkeypatch.delenv(f"TEST_{name}", raising=False)
    monkeypatch.setenv("TEST_deepseek", "fake-deepseek-key")
    config["providers"]["deepseek"]["proxy_autostart"] = enabled
    config_file = tmp_path / "providers.json"
    config_file.write_text(json.dumps(config), encoding="utf-8")
    monkeypatch.setattr(mw_common.shutil, "which", lambda name: None)
    monkeypatch.setattr(mw, "_serve_meta_identity", lambda: {"schema": mw.SERVE_META_SCHEMA})
    monkeypatch.setattr(mw, "_report_serve_code_drift", lambda *a, **k: None)
    monkeypatch.setattr(mw, "_port_is_bound", lambda port: False)
    monkeypatch.setattr(mw, "_conductor_supervise_step", lambda *a, **k: None)
    spawned = []

    class FakeProc:
        pid = 4242

        def poll(self):
            return None

        def terminate(self):
            pass

        def wait(self, timeout=None):
            return 0

    def spawn(cmd, **kwargs):
        spawned.append(cmd)
        return FakeProc()

    def stop_after_tick(seconds):
        raise KeyboardInterrupt

    monkeypatch.setattr(mw.subprocess, "Popen", spawn)
    monkeypatch.setattr(mw.time, "sleep", stop_after_tick)
    args = argparse.Namespace(project=str(tmp_path), providers=str(config_file), pi_port=27001,
                              claude_port=27003, deepseek_port=explicit_port, poll_interval=1, max_workers=None)
    assert mw.cmd_serve(args) == 0
    proxies = [cmd for cmd in spawned if "proxy_multi.py" in str(cmd[1])]
    assert bool(proxies) is expected_proxy
    if expected_proxy:
        assert f"--deepseek-port={explicit_port or 7004}" in proxies[0]
    assert any("launcher.py" in str(cmd[1]) for cmd in spawned)
    assert not mw_common.pid_file(tmp_path).exists()
    log = (tmp_path / ".mw/mw.log").read_text(encoding="utf-8")
    assert "route deepseek: available" in log
    if not expected_proxy:
        assert "proxy=disabled" in log


def test_doctor_marks_native_deepseek_as_not_autostarting(monkeypatch):
    config = mw_common.default_config()
    monkeypatch.setattr(mw_common, "port_is_bound", lambda port: False)
    rows = mw_common._doctor_proxy(config)
    assert next(row for row in rows if row["route"] == "deepseek")["autostart"] is False
    assert "autostart" not in next(row for row in rows if row["route"] == "claude")
