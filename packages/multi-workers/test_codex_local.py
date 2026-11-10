"""Hermetic relay integration tests: real HTTP and fake CLI processes, no paid API."""
import concurrent.futures
import http.client
import json
from pathlib import Path
import subprocess
import sys
import threading

import pytest

import codex_local as relay
import launcher

TOKEN = "local-test-token-with-at-least-24-characters"
FAKE_CLI = '''import json, os, pathlib, sys, time
args = sys.argv[1:]
if args == ["login", "status"]:
    assert "OPENAI_API_KEY" not in os.environ
    print("Logged in using ChatGPT")
    sys.exit(0)
prompt = sys.stdin.buffer.read().decode("utf-8")
context = json.loads(prompt.split("CONTEXT JSON:\\n", 1)[1])
mode = context["messages"][-1]["content"]
if mode == "sleep":
    time.sleep(30)
if mode == "fail":
    print("sensitive-stderr", file=sys.stderr)
    sys.exit(7)
assert args[args.index("--model") + 1] == "test-model"
assert "--ignore-user-config" in args and "--ephemeral" in args
assert "features.shell_tool=false" in args and "read-only" in args
assert "OPENAI_API_KEY" not in os.environ and "PI_WORKER_TASK" not in os.environ
result = {"text": json.dumps({"cwd": os.getcwd(), "context": context}), "tool_calls": []}
if mode == "tool":
    result = {"text": "", "tool_calls": [{"name": "read", "arguments": '{"path":"hello.txt"}'}]}
pathlib.Path(args[args.index("--output-last-message") + 1]).write_text(json.dumps(result), encoding="utf-8")
print(json.dumps({"type": "turn.completed", "usage": {"input_tokens": 12, "cached_input_tokens": 2, "output_tokens": 3}}))
'''


def request(message="hello"):
    return {"model": "test-model", "context": {"systemPrompt": "test system", "messages": [
        {"role": "user", "content": message, "timestamp": 1}
    ], "tools": [{"name": "read", "parameters": {"type": "object"}, "description": "read"}]}}


@pytest.fixture
def backend(tmp_path, monkeypatch):
    script = tmp_path / "fake_codex.py"
    script.write_text(FAKE_CLI, encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-cli")
    monkeypatch.setenv("PI_WORKER_TASK", "must-not-reach-cli")
    return relay.CodexBackend([sys.executable, str(script)], timeout=5)


@pytest.fixture
def server(backend):
    instance = relay.RelayServer(("127.0.0.1", 0), TOKEN, backend, concurrency=1)
    thread = threading.Thread(target=instance.serve_forever, daemon=True)
    thread.start()
    yield instance
    instance.cancel_all.set()
    instance.shutdown()
    instance.server_close()
    thread.join(timeout=5)


def post(server, body, token=TOKEN, extra_headers=None):
    connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=10)
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    headers.update(extra_headers or {})
    connection.request("POST", "/complete", json.dumps(body).encode(), headers)
    response = connection.getresponse()
    data = response.read().decode()
    status = response.status
    connection.close()
    return status, [json.loads(line) for line in data.splitlines()]


def test_http_context_and_independent_cli(server):
    results = []
    for message in ("first 中文", "second"):
        original = request(message)
        status, events = post(server, original)
        assert status == 200 and events[0]["type"] == "heartbeat"
        result = events[-1]
        assert result["type"] == "result" and result["usage"]["input_tokens"] == 12
        payload = json.loads(result["text"])
        assert payload["context"] == original["context"]
        assert not Path(payload["cwd"]).exists()
        results.append(payload)
    assert results[0]["cwd"] != results[1]["cwd"]


def test_tool_round_trip(server):
    _, events = post(server, request("tool"))
    tool = events[-1]["toolCalls"][0]
    assert tool["name"] == "read" and tool["arguments"] == {"path": "hello.txt"}
    following = request("continue")
    following["context"]["messages"].insert(0, {
        "role": "toolResult", "toolCallId": tool["id"], "toolName": "read",
        "content": [{"type": "text", "text": "file contents"}], "isError": False,
    })
    _, events = post(server, following)
    assert json.loads(events[-1]["text"])["context"] == following["context"]


@pytest.mark.parametrize("result", [
    {"text": "", "tool_calls": []},
    {"text": "", "tool_calls": [{"name": "unknown", "arguments": "{}"}]},
    {"text": "", "tool_calls": [{"name": "read", "arguments": "[]"}]},
    {"text": "", "tool_calls": [{"name": "read", "arguments": "broken"}]},
])
def test_bad_cli_result(result):
    with pytest.raises(relay.RelayError):
        relay.parse_result(json.dumps(result), request())


def test_pre_spawn_refusals(server, monkeypatch):
    def forbidden(*args):
        pytest.fail("Invalid request reached CLI")
    monkeypatch.setattr(server.backend, "complete", forbidden)
    assert post(server, request(), token="wrong")[0] == 401
    assert post(server, request(), extra_headers={"Origin": "https://example.com"})[0] == 401
    assert post(server, request(), extra_headers={"Content-Length": str(relay.MAX_BODY + 1)})[0] == 413
    image_request = request()
    image_request["context"]["messages"][0]["content"] = [{"type": "image", "data": "x"}]
    assert post(server, image_request)[0] == 400
    assert post(server, {"model": "--flag", "context": {}})[0] == 400
    server.slots.acquire()
    try:
        assert post(server, request())[0] == 429
    finally:
        server.slots.release()


def test_cli_failure_redacts_stderr(server):
    _, events = post(server, request("fail"))
    assert events[-1]["type"] == "error"
    assert "code 7" in events[-1]["error"]
    assert "sensitive-stderr" not in json.dumps(events)


@pytest.mark.parametrize("cancelled", [False, True])
def test_timeout_and_cancel_reap_process(backend, monkeypatch, cancelled):
    processes = []
    started = threading.Event()
    real_popen = subprocess.Popen
    def capture(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        processes.append(process)
        started.set()
        return process
    monkeypatch.setattr(relay.subprocess, "Popen", capture)
    backend.timeout = 5 if cancelled else 0.3
    cancel = threading.Event()
    with concurrent.futures.ThreadPoolExecutor() as pool:
        future = pool.submit(backend.complete, request("sleep"), cancel)
        assert started.wait(3)
        if cancelled:
            cancel.set()
        with pytest.raises(relay.RelayError, match="cancelled" if cancelled else "timed out"):
            future.result(timeout=8)
    assert processes[0].poll() is not None


def test_disconnect_cancels_backend(server, monkeypatch):
    cancelled = threading.Event()
    def wait_for_cancel(request, cancel):
        assert cancel.wait(8)
        cancelled.set()
        raise relay.RelayError("cancelled")
    monkeypatch.setattr(server.backend, "complete", wait_for_cancel)
    conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
    conn.request("POST", "/complete", json.dumps(request()), {"Authorization": f"Bearer {TOKEN}"})
    response = conn.getresponse()
    assert b"heartbeat" in response.readline()
    response.close()
    conn.close()
    assert cancelled.wait(6)


def test_worker_route_inherits_relay_settings(tmp_path, monkeypatch):
    monkeypatch.setenv("MW_CODEX_LOCAL_URL", "http://127.0.0.1:7010")
    monkeypatch.setenv("MW_CODEX_LOCAL_TOKEN", TOKEN)
    monkeypatch.setenv("OPENAI_API_KEY", "unrelated")
    entry = launcher._effective_entry(
        {"cli": "pi", "task_path": str(tmp_path / "task.md")}, "codex/test-model")
    env = launcher._build_env(entry, {"credentials": {}, "providers": {}})
    assert entry["provider"] == "openai-codex"
    assert env["MW_CODEX_LOCAL_TOKEN"] == TOKEN
    assert env["MW_CODEX_LOCAL_URL"] == "http://127.0.0.1:7010"
    assert "OPENAI_API_KEY" not in env


def test_server_rejects_public_bind(backend):
    with pytest.raises(ValueError, match="127.0.0.1"):
        relay.RelayServer(("0.0.0.0", 0), TOKEN, backend)
