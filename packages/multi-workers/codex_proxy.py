"""Project-local lifecycle manager for the Codex inference relay (no credentials copied)."""
from __future__ import annotations

import argparse
import http.client
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
from urllib.parse import urlsplit

from codex_local import CodexBackend, RelayServer
from mw_common import acquire_lock, release_lock


def config_path(project: Path) -> Path:
    return project / ".mw" / "codex-local.json"


def read_config(project: Path) -> dict | None:
    file = config_path(project)
    if not file.exists():
        if not os.environ.get("MW_CODEX_LOCAL_URL"):
            return None
        value = {"version": 1, "url": os.environ["MW_CODEX_LOCAL_URL"], "token": os.environ.get("MW_CODEX_LOCAL_TOKEN", "")}
    else:
        value = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("url"), str):
        raise ValueError("Invalid .mw/codex-local.json")
    url = urlsplit(value["url"])
    if (value.get("version") != 1 or url.scheme != "http" or url.hostname != "127.0.0.1"
            or not url.port or url.username or url.password or url.path not in ("", "/") or url.query or url.fragment
            or not isinstance(value.get("token"), str) or len(value["token"]) < 24):
        raise ValueError("Invalid .mw/codex-local.json")
    return value


def write_config(project: Path, value: dict) -> None:
    file = config_path(project)
    file.parent.mkdir(parents=True, exist_ok=True)
    temporary = file.with_suffix(f".{os.getpid()}.tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream)
        os.replace(temporary, file)
    finally:
        temporary.unlink(missing_ok=True)


def call(config: dict, endpoint: str, method: str = "GET", body: dict | None = None, timeout: float = 3) -> dict:
    url = urlsplit(config["url"])
    connection = http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)
    deadline = time.monotonic() + timeout
    try:
        connection.request(method, endpoint, None if body is None else json.dumps(body),
                           {"Authorization": f'Bearer {config["token"]}', "Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status not in (200, 202):
            raise RuntimeError(f"Local Codex relay HTTP {response.status}")
        if endpoint == "/complete":
            while line := response.readline():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("Local Codex model check timed out")
                if connection.sock:
                    connection.sock.settimeout(remaining)
                event = json.loads(line)
                if event.get("type") in ("result", "error"):
                    return {"model_check": "passed" if event["type"] == "result" else "failed"}
            raise RuntimeError("Local Codex relay ended before result")
        result = json.loads(response.read(1024 * 1024))
        if endpoint != "/stop" and (result.get("backend") != "codex-cli" or result.get("protocol") != 2):
            raise RuntimeError("Incompatible local Codex relay; update and restart it")
        return result
    finally:
        connection.close()


def start(project: Path, port: int = 7010, codex: str = "codex") -> dict:
    lock = project / ".mw" / "codex-local.lock"
    acquire_lock(lock, deadline_s=12)
    try:
        config = read_config(project)
        if config:
            try:
                status = call(config, "/status")
                if status["status"] == "draining":
                    raise RuntimeError("Relay is draining; wait before starting again")
                if not config_path(project).exists():
                    write_config(project, config)
                return status
            except (ConnectionError, TimeoutError, OSError):
                pass
        executable = shutil.which(codex)
        if not executable:
            raise RuntimeError("Codex executable not found on PATH")
        backend = CodexBackend([executable])
        if backend.check_login() != "chatgpt":
            raise RuntimeError("Codex ChatGPT login unavailable; run codex login in a terminal")
        # Existing configuration keeps its token and port across restarts.
        config = config or {"version": 1, "url": f"http://127.0.0.1:{port}", "token": secrets.token_hex(32)}
        write_config(project, config)
        child = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "serve", "--project", str(project),
                                  "--codex", executable], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                 stderr=subprocess.DEVNULL,
                                 creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                 start_new_session=os.name != "nt")
        deadline = time.monotonic() + 8
        try:
            while time.monotonic() < deadline:
                if child.poll() is not None:
                    raise RuntimeError(f"Relay startup failed (exit {child.returncode}); check port {urlsplit(config['url']).port}")
                try:
                    return call(config, "/status")
                except (ConnectionError, TimeoutError, OSError):
                    time.sleep(0.1)
            raise RuntimeError("Relay startup timed out")
        except BaseException:
            # Only terminate the child we just created, never an arbitrary recorded PID.
            if child.poll() is None:
                child.terminate()
                child.wait(timeout=5)
            raise
    finally:
        release_lock(lock)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status", "check", "serve"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--port", type=int, default=7010)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--model")
    args = parser.parse_args()
    project = args.project.resolve()
    try:
        if not 1 <= args.port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        if args.action == "start":
            result = start(project, args.port, args.codex)
        else:
            config = read_config(project)
            if config is None:
                raise RuntimeError("Proxy is not configured; run /mw proxy start")
            if args.action == "serve":
                executable = shutil.which(args.codex)
                if not executable:
                    raise RuntimeError("Codex executable not found")
                server = RelayServer(("127.0.0.1", urlsplit(config["url"]).port), config["token"], CodexBackend([executable]))
                try:
                    server.serve_forever(poll_interval=0.1)
                finally:
                    server.server_close()
                return 0
            if args.action == "stop":
                try:
                    result = call(config, "/stop", "POST")
                except (ConnectionError, TimeoutError, OSError):
                    result = {"status": "offline"}
            else:
                result = call(config, "/check" if args.action == "check" else "/status", timeout=8)
                if args.deep:
                    if args.action != "check" or not args.model:
                        raise ValueError("--deep requires check --model <model>")
                    result.update(call(config, "/complete", "POST", {
                        "model": args.model, "context": {"messages": [{"role": "user", "content": "Reply exactly: proxy-ok"}]}
                    }, timeout=200))
        print(json.dumps(result))
        return 0 if result.get("login", "chatgpt") == "chatgpt" and result.get("model_check") != "failed" else 1
    except (ValueError, KeyError, TypeError, OSError, RuntimeError, http.client.HTTPException) as exc:
        # Exceptions never include config contents or raw Codex output.
        print(json.dumps({"status": "error", "error": str(exc)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
