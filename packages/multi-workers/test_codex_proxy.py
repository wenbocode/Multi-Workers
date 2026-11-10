"""Hermetic lifecycle/status tests, no real Codex account or model requests."""
import concurrent.futures
import http.client
import json
import sys
import threading
import time

import pytest

import codex_local
import codex_proxy
from test_codex_local import TOKEN, backend, server, post, request  # noqa: F401


@pytest.fixture(autouse=True)
def isolated_proxy_environment(monkeypatch):
    monkeypatch.delenv("MW_CODEX_LOCAL_URL", raising=False)
    monkeypatch.delenv("MW_CODEX_LOCAL_TOKEN", raising=False)


def settings(server):
    return {"version": 1, "url": f"http://127.0.0.1:{server.server_port}", "token": TOKEN}


def test_login_probe_uses_cli_and_removes_api_environment(backend):
    assert backend.check_login() == "chatgpt"


def test_missing_login_blocks_start_without_writing_config(tmp_path, monkeypatch):
    monkeypatch.setattr(codex_proxy.CodexBackend, "check_login", lambda self: "not-chatgpt")
    with pytest.raises(RuntimeError, match="ChatGPT login"):
        codex_proxy.start(tmp_path, codex=sys.executable)
    assert not codex_proxy.config_path(tmp_path).exists()


def test_status_check_and_secrets(server, monkeypatch):
    monkeypatch.setattr(server.backend, "check_login", lambda: "chatgpt")
    config = settings(server)
    assert codex_proxy.call(config, "/check")["login"] == "chatgpt"
    assert codex_proxy.call(config, "/status")["last_success"] is None
    post(server, request("sensitive-prompt"))
    status = codex_proxy.call(config, "/status")
    assert status["last_success"]["model"] == "test-model"
    assert status["active"] == []
    assert TOKEN not in json.dumps(status) and "sensitive-prompt" not in json.dumps(status)
    with pytest.raises(RuntimeError, match="401"):
        codex_proxy.call({**config, "token": "wrong"}, "/status")
    with pytest.raises(RuntimeError, match="401"):
        codex_proxy.call({**config, "token": "wrong"}, "/stop", "POST")
    assert not server.draining


def test_light_and_deep_calls(server, monkeypatch, tmp_path, capsys):
    calls = []
    monkeypatch.setattr(server.backend, "check_login", lambda: "chatgpt")
    def complete(value, cancel):
        calls.append(value)
        return {"text": "proxy-ok", "toolCalls": [], "usage": {}}
    monkeypatch.setattr(server.backend, "complete", complete)
    codex_proxy.write_config(tmp_path, settings(server))
    monkeypatch.setattr(sys, "argv", ["proxy", "check", "--project", str(tmp_path)])
    assert codex_proxy.main() == 0 and len(calls) == 0
    monkeypatch.setattr(sys, "argv", ["proxy", "check", "--project", str(tmp_path), "--deep", "--model", "test-model"])
    assert codex_proxy.main() == 0 and len(calls) == 1
    assert "passed" in capsys.readouterr().out


def test_drain_rejects_new_requests_and_waits(backend, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    def complete(value, cancel):
        entered.set()
        assert release.wait(5)
        return {"text": "finished", "toolCalls": []}
    monkeypatch.setattr(backend, "complete", complete)
    server = codex_local.RelayServer(("127.0.0.1", 0), TOKEN, backend, concurrency=2)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        with concurrent.futures.ThreadPoolExecutor() as pool:
            pending = pool.submit(post, server, {**request(), "caller": "worker:task-42"})
            assert entered.wait(3)
            status = codex_proxy.call(settings(server), "/status")
            assert len(status["active"]) == 1
            assert status["active"][0]["caller"] == "worker:task-42"
            assert codex_proxy.call(settings(server), "/stop", "POST")["status"] == "draining"
            for _ in range(50):
                if server.draining:
                    break
                time.sleep(.01)
            assert thread.is_alive()
            assert post(server, request())[0] == 503
            release.set()
            assert pending.result(timeout=5)[1][-1]["text"] == "finished"
        thread.join(3)
        assert not thread.is_alive()
    finally:
        release.set()
        server.shutdown()
        server.server_close()


def test_existing_start_is_idempotent_and_locked(server, tmp_path):
    codex_proxy.write_config(tmp_path, settings(server))
    before = codex_proxy.config_path(tmp_path).read_bytes()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        results = list(pool.map(lambda _: codex_proxy.start(tmp_path), range(4)))
    assert len({item["instance"] for item in results}) == 1
    assert codex_proxy.config_path(tmp_path).read_bytes() == before
    assert not (tmp_path / ".mw/codex-local.lock").exists()


def test_start_adopts_explicit_environment_service(server, tmp_path, monkeypatch):
    config = settings(server)
    monkeypatch.setenv("MW_CODEX_LOCAL_URL", config["url"])
    monkeypatch.setenv("MW_CODEX_LOCAL_TOKEN", config["token"])
    assert codex_proxy.start(tmp_path)["instance"] == server.instance
    monkeypatch.delenv("MW_CODEX_LOCAL_URL")
    monkeypatch.delenv("MW_CODEX_LOCAL_TOKEN")
    assert codex_proxy.read_config(tmp_path) == config


def test_real_manager_start_stop(tmp_path, monkeypatch):
    """Exercise real manager child process without calling an installed Codex."""
    monkeypatch.setattr(codex_proxy.CodexBackend, "check_login", lambda self: "chatgpt")
    # Python stands in for the CLI; starting/stopping the service does no inference.
    probe = codex_local.RelayServer(("127.0.0.1", 0), TOKEN, codex_local.CodexBackend([sys.executable]))
    port = probe.server_port
    probe.server_close()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        starts = list(pool.map(lambda _: codex_proxy.start(tmp_path, port, sys.executable), range(2)))
    first = starts[0]
    assert starts[1]["instance"] == first["instance"]
    config = codex_proxy.read_config(tmp_path)
    try:
        assert first["status"] == "ready"
        assert codex_proxy.start(tmp_path, port, sys.executable)["instance"] == first["instance"]
        assert codex_proxy.call(config, "/stop", "POST")["status"] == "draining"
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                codex_proxy.call(config, "/status", timeout=.2)
            except (OSError, http.client.HTTPException):
                break
            time.sleep(.1)
        else:
            pytest.fail("Service did not stop")
    finally:
        try:
            codex_proxy.call(config, "/stop", "POST")
        except (OSError, http.client.HTTPException):
            pass


@pytest.mark.parametrize("url", ["http://example.com:7010", "http://127.0.0.1:7010/path", "http://user:secret@127.0.0.1:7010"])
def test_config_rejects_non_loopback_or_extra_parts(tmp_path, url):
    codex_proxy.write_config(tmp_path, {"version": 1, "url": url, "token": TOKEN})
    with pytest.raises(ValueError):
        codex_proxy.read_config(tmp_path)
