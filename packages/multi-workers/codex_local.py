"""Loopback inference relay using the locally signed-in Codex CLI.

The /complete protocol carries pi Context, not OpenAI Responses payloads.
Codex produces a structured next assistant message; pi executes its tools.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hmac
import json
import math
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MAX_BODY = 8 * 1024 * 1024
INSTRUCTIONS = """You are an inference adapter for another agent, not its executor.
Produce exactly the next assistant response for the conversation in the supplied
JSON context. Follow context.systemPrompt and the conversation's instructions.
Tools listed in context.tools belong to the caller. NEVER execute tools yourself.
To request a caller tool, return its name and JSON-encoded argument object in
tool_calls; the caller will execute it and include the result on the next request.
Return text for user-facing content. Return an empty tool_calls array when done.
Do not invent tool results or claim actions were performed. Use only listed tools.
"""


class RelayError(Exception):
    pass


def codex_environment() -> dict[str, str]:
    return {key: value for key, value in os.environ.items()
            if not key.startswith(("PI_WORKER_", "MW_CODEX_LOCAL_"))
            and key not in ("OPENAI_API_KEY", "CODEX_API_KEY", "OPENAI_BASE_URL", "CODEX_THREAD_ID")}


def validate_request(value: object) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Expected a JSON object")
    model = value.get("model")
    if not isinstance(model, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,199}", model):
        raise ValueError("Invalid model id")
    caller = value.get("caller", "unknown")
    if not isinstance(caller, str) or len(caller) > 100 or any(ord(char) < 32 for char in caller):
        raise ValueError("Invalid caller label")
    context = value.get("context")
    if not isinstance(context, dict) or not isinstance(context.get("messages"), list):
        raise ValueError("context.messages must be an array")
    if not context["messages"]:
        raise ValueError("context.messages must not be empty")
    if "systemPrompt" in context and not isinstance(context["systemPrompt"], str):
        raise ValueError("systemPrompt must be text")
    for message in context["messages"]:
        if not isinstance(message, dict) or message.get("role") not in ("user", "assistant", "toolResult"):
            raise ValueError("Invalid message role")
        content = message.get("content")
        if isinstance(content, str):
            continue
        if not isinstance(content, list):
            raise ValueError("Invalid message content")
        for block in content:
            if not isinstance(block, dict) or block.get("type") not in ("text", "thinking", "toolCall"):
                raise ValueError("Local Codex relay supports text only; images are not supported")
    tools = context.get("tools", [])
    if not isinstance(tools, list):
        raise ValueError("context.tools must be an array")
    names = set()
    for tool in tools:
        if (not isinstance(tool, dict) or not isinstance(tool.get("name"), str)
                or not tool["name"] or not isinstance(tool.get("parameters"), dict)):
            raise ValueError("Invalid tool definition")
        if tool["name"] in names:
            raise ValueError("Duplicate tool name")
        names.add(tool["name"])
    effort = value.get("reasoning")
    if effort is not None and effort not in ("minimal", "low", "medium", "high", "xhigh", "max"):
        raise ValueError("Invalid reasoning effort")
    return value


def response_schema() -> dict:
    return {
        "type": "object", "additionalProperties": False,
        "properties": {
            "text": {"type": "string"},
            "tool_calls": {"type": "array", "items": {
                "type": "object", "additionalProperties": False,
                "properties": {"name": {"type": "string"}, "arguments": {"type": "string"}},
                "required": ["name", "arguments"],
            }},
        },
        "required": ["text", "tool_calls"],
    }


def parse_result(text: str, request: dict) -> dict:
    try:
        result = json.loads(text)
        if not isinstance(result, dict) or not isinstance(result.get("text"), str):
            raise ValueError("Missing text")
        if not isinstance(result.get("tool_calls"), list):
            raise ValueError("Missing tool_calls")
        names = {tool["name"] for tool in request["context"].get("tools", [])}
        calls = []
        for call in result["tool_calls"]:
            if not isinstance(call, dict) or call.get("name") not in names:
                raise ValueError("Unknown tool")
            args = json.loads(call["arguments"])
            if not isinstance(args, dict):
                raise ValueError("Tool arguments must be an object")
            calls.append({"id": f"call_{uuid.uuid4().hex}", "name": call["name"], "arguments": args})
        if not result["text"] and not calls:
            raise ValueError("Empty assistant response")
        return {"text": result["text"], "toolCalls": calls}
    except (ValueError, KeyError, TypeError) as exc:
        raise RelayError(f"Invalid Codex structured response: {exc}") from exc


def kill_process(process: subprocess.Popen) -> None:
    if process.poll() is not None:
        return
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           creationflags=subprocess.CREATE_NO_WINDOW, timeout=10, check=False)
        except (OSError, subprocess.TimeoutExpired):
            process.kill()
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)


class CodexBackend:
    def __init__(self, command: list[str], timeout: float = 180):
        self.command = command
        self.timeout = timeout

    def check_login(self) -> str:
        try:
            result = subprocess.run([*self.command, "login", "status"], capture_output=True, env=codex_environment(),
                                    timeout=5, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
            text = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            return "chatgpt" if result.returncode == 0 and "ChatGPT" in text else "not-chatgpt"
        except (OSError, subprocess.TimeoutExpired):
            return "unavailable"

    def complete(self, request: dict, cancel: threading.Event) -> dict:
        with tempfile.TemporaryDirectory(prefix="mw-codex-") as directory:
            root = Path(directory)
            schema = root / "response-schema.json"
            output = root / "response.json"
            schema.write_text(json.dumps(response_schema()), encoding="utf-8")
            command = [*self.command, "-a", "never", "exec", "--ignore-user-config",
                       "--ephemeral", "--skip-git-repo-check", "--sandbox", "read-only",
                       "--cd", directory, "--color", "never", "--json",
                       "--output-schema", str(schema), "--output-last-message", str(output),
                       "--model", request["model"]]
            for setting in ("features.shell_tool=false", "features.multi_agent=false",
                            "features.apps=false", "features.plugins=false",
                            'web_search="disabled"'):
                command.extend(["-c", setting])
            if request.get("reasoning"):
                command.extend(["-c", f'model_reasoning_effort="{request["reasoning"]}"'])
            command.append("-")
            env = codex_environment()
            prompt = (INSTRUCTIONS + "\nCONTEXT JSON:\n" +
                      json.dumps(request["context"], ensure_ascii=False)).encode("utf-8")
            if cancel.is_set():
                raise RelayError("Request cancelled")
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE, cwd=directory, env=env,
                                       creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                       start_new_session=os.name != "nt")
            deadline = time.monotonic() + self.timeout
            try:
                first = True
                while True:
                    if cancel.is_set():
                        raise RelayError("Request cancelled")
                    if time.monotonic() >= deadline:
                        raise RelayError(f"Codex timed out after {self.timeout:g}s")
                    try:
                        stdout, _stderr = process.communicate(input=prompt if first else None, timeout=0.2)
                        break
                    except subprocess.TimeoutExpired:
                        first = False
                if process.returncode != 0:
                    # Do not return raw stderr: it may contain auth/config or prompt data.
                    raise RelayError(f"Codex exited with code {process.returncode}; check codex login status and model access")
                if not output.exists() or output.stat().st_size > MAX_BODY:
                    raise RelayError("Codex did not produce a bounded structured response")
                result = parse_result(output.read_text(encoding="utf-8"), request)
                usage = {}
                for line in stdout.decode("utf-8", errors="replace").splitlines():
                    try:
                        event = json.loads(line)
                    except ValueError:
                        continue
                    if event.get("type") == "turn.failed" or event.get("type") == "error":
                        raise RelayError("Codex reported a failed turn")
                    if event.get("type") == "turn.completed":
                        usage = event.get("usage", {})
                result["usage"] = usage
                return result
            finally:
                kill_process(process)
                for pipe in (process.stdin, process.stdout, process.stderr):
                    if pipe:
                        pipe.close()


class RelayServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], token: str, backend: CodexBackend, concurrency: int = 2):
        if address[0] != "127.0.0.1":
            raise ValueError("Relay must bind to 127.0.0.1")
        if len(token) < 24 or concurrency < 1:
            raise ValueError("Token must have at least 24 characters; concurrency must be positive")
        self.token = token
        self.backend = backend
        self.slots = threading.BoundedSemaphore(concurrency)
        self.cancel_all = threading.Event()
        self.state_lock = threading.Lock()
        self.draining = False
        self.active: dict[str, dict] = {}
        self.last_success: dict | None = None
        self.last_error: dict | None = None
        self.started_at = time.time()
        self.instance = uuid.uuid4().hex
        self.concurrency = concurrency
        super().__init__(address, RelayHandler)

    def snapshot(self) -> dict:
        with self.state_lock:
            now = time.time()
            return {"status": "draining" if self.draining else "ready", "backend": "codex-cli",
                    "protocol": 2, "instance": self.instance, "pid": os.getpid(),
                    "uptime_s": now - self.started_at, "concurrency": self.concurrency,
                    "timeout_s": self.backend.timeout,
                    "active": [{**entry, "age_s": now - entry["started_at"]} for entry in self.active.values()],
                    "last_success": self.last_success, "last_error": self.last_error}

    def drain(self) -> None:
        with self.state_lock:
            if self.draining:
                return
            self.draining = True

        def wait_and_stop() -> None:
            while True:
                with self.state_lock:
                    if not self.active:
                        break
                time.sleep(0.1)
            self.shutdown()

        threading.Thread(target=wait_and_stop, daemon=True).start()


class RelayHandler(BaseHTTPRequestHandler):
    server: RelayServer

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, format: str, *args: object) -> None:
        pass  # Prompts, credentials and paths never enter access logs.

    def send_json(self, status: int, value: dict) -> None:
        body = json.dumps(value).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/health":
            self.send_json(200, {"status": "ok", "backend": "codex-cli", "protocol": 1})
        elif self.path in ("/status", "/check"):
            if not self.authorized():
                return
            value = self.server.snapshot()
            if self.path == "/check":
                value["login"] = self.server.backend.check_login()
            self.send_json(200, value)
        else:
            self.send_json(404, {"error": "Not found"})

    def authorized(self) -> bool:
        if self.headers.get("Origin") or not hmac.compare_digest(
                self.headers.get("Authorization", "").encode("utf-8"),
                f"Bearer {self.server.token}".encode("utf-8")):
            self.send_json(401, {"error": "Local relay authentication required"})
            return False
        return True

    def do_POST(self) -> None:
        if not self.authorized():
            return
        if self.path == "/stop":
            self.send_json(202, {"status": "draining"})
            self.server.drain()
            return
        if self.path != "/complete":
            self.send_json(404, {"error": "Not found"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if self.headers.get("Transfer-Encoding") or not 0 < length <= MAX_BODY:
                self.send_json(413, {"error": "Request must have a Content-Length between 1 and 8 MiB"})
                return
            raw = self.rfile.read(length)
            if len(raw) != length:
                raise ValueError("Incomplete request")
            request = validate_request(json.loads(raw))
        except (ValueError, UnicodeError, OSError) as exc:
            self.send_json(400, {"error": str(exc)})
            return
        if not self.server.slots.acquire(blocking=False):
            self.send_json(429, {"error": "Local Codex relay is busy; retry later"})
            return
        request_id = uuid.uuid4().hex
        with self.server.state_lock:
            if self.server.draining:
                self.server.slots.release()
                self.send_json(503, {"error": "Local Codex relay is draining"})
                return
            self.server.active[request_id] = {"id": request_id, "model": request["model"],
                                              "caller": request.get("caller", "unknown"), "started_at": time.time()}
        cancel = threading.Event()
        outcome = "connection closed or cancelled"
        try:
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(self.server.backend.complete, request, cancel)
                try:
                    while not future.done():
                        if self.server.cancel_all.is_set():
                            cancel.set()
                        self.wfile.write(b'{"type":"heartbeat"}\n')
                        self.wfile.flush()
                        try:
                            future.result(timeout=1)
                        except concurrent.futures.TimeoutError:
                            continue
                        except Exception:
                            break
                    try:
                        event = {"type": "result", **future.result()}
                        outcome = "success"
                    except (RelayError, OSError) as exc:
                        event = {"type": "error", "error": str(exc)}
                        outcome = str(exc) if isinstance(exc, RelayError) else "CLI process unavailable"
                    except Exception:
                        event = {"type": "error", "error": "Unexpected local relay failure"}
                        outcome = "Unexpected local relay failure"
                    self.wfile.write((json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8"))
                    self.wfile.flush()
                finally:
                    cancel.set()
        except (BrokenPipeError, ConnectionError, OSError):
            cancel.set()
        finally:
            with self.server.state_lock:
                entry = self.server.active.pop(request_id)
                record = {"at": time.time(), "model": entry["model"], "duration_s": time.time() - entry["started_at"]}
                if outcome == "success":
                    self.server.last_success = record
                else:
                    self.server.last_error = {**record, "error": outcome}
            self.server.slots.release()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=7010)
    parser.add_argument("--codex", default="codex", help="Codex executable path (not a shell command)")
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument("--concurrency", type=int, default=2)
    args = parser.parse_args()
    executable = shutil.which(args.codex)
    if not executable:
        parser.error("Codex executable not found; install Codex and run codex login")
    if not math.isfinite(args.timeout) or args.timeout <= 0 or not 0 <= args.port <= 65535:
        parser.error("Invalid timeout or port")
    token = os.environ.get("MW_CODEX_LOCAL_TOKEN", "")
    try:
        server = RelayServer(("127.0.0.1", args.port), token,
                             CodexBackend([executable], args.timeout), args.concurrency)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Codex local relay: http://127.0.0.1:{server.server_port} (text/tools, CLI login)", flush=True)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.cancel_all.set()
        server.server_close()


if __name__ == "__main__":
    main()
