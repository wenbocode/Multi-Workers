"""Project-local lifecycle manager for the Codex inference relay (no credentials copied)."""
from __future__ import annotations

import argparse
import errno
import http.client
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit

from codex_local import CodexBackend, RelayServer
from mw_common import acquire_lock, release_lock


def config_path(project: Path) -> Path:
    return project / ".mw" / "codex-local.json"


def resolve_codex(codex: str) -> str:
    executable = shutil.which(codex)
    if executable:
        return os.path.abspath(executable)
    if sys.platform != "win32" or codex != "codex":
        raise RuntimeError(f"Codex executable not found: {codex}")

    # pi launched outside the desktop app may not inherit its versioned CLI directory.
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    query = ("[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false); "
             "(Get-AppxPackage -Name OpenAI.Codex | Where-Object PackageFamilyName "
             "-eq 'OpenAI.Codex_2p2nqsd0c76g0').InstallLocation")
    try:
        lookup = subprocess.run([str(powershell), "-NoProfile", "-NonInteractive", "-Command", query],
                                capture_output=True, timeout=6, creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Codex missing from PATH and desktop package lookup failed; "
                           "use codex_proxy.py start --codex <path-to-codex.exe>") from exc
    location = Path(lookup.stdout.decode("utf-8-sig").strip())
    if lookup.returncode == 0 and location.is_absolute():
        bundled = location / "app/resources/codex.exe"
        if bundled.is_file():
            return str(bundled)
    raise RuntimeError("Codex CLI not found on PATH or in the registered Codex desktop package; "
                       "use codex_proxy.py start --codex <path-to-codex.exe>")


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


class RelayHTTPError(RuntimeError):
    def __init__(self, status: int):
        super().__init__(f"Local Codex relay HTTP {status}")
        self.status = status


def call(config: dict, endpoint: str, method: str = "GET", body: dict | None = None, timeout: float = 3) -> dict:
    url = urlsplit(config["url"])
    connection = http.client.HTTPConnection(url.hostname, url.port, timeout=timeout)
    deadline = time.monotonic() + timeout
    try:
        connection.request(method, endpoint, None if body is None else json.dumps(body),
                           {"Authorization": f'Bearer {config["token"]}', "Content-Type": "application/json"})
        response = connection.getresponse()
        if response.status not in (200, 202):
            raise RelayHTTPError(response.status)
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


def start(project: Path, port: int | None = None, codex: str = "codex") -> dict:
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
            except RelayHTTPError as exc:
                # A saved endpoint may now belong to another project. Explicit
                # environment connections still require the supplied credentials.
                if exc.status != 401 or not config_path(project).exists():
                    raise
            except ConnectionRefusedError:
                pass
        executable = resolve_codex(codex)
        backend = CodexBackend([executable])
        if backend.check_login() != "chatgpt":
            raise RuntimeError("Codex ChatGPT login unavailable; run codex login in a terminal")
        with tempfile.TemporaryDirectory() as directory:
            ready_dir = Path(directory)
            args = [sys.executable, str(Path(__file__).resolve()), "serve", "--project", str(project),
                    "--codex", executable, "--ready-dir", str(ready_dir)]
            if port is not None:
                args += ["--port", str(port)]
            child = subprocess.Popen(args, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                     stderr=subprocess.DEVNULL,
                                     creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
                                     start_new_session=os.name != "nt")
            try:
                deadline = time.monotonic() + 8
                while not config_path(ready_dir).exists():
                    if child.poll() is not None:
                        detail = f"; check port {port}" if port is not None else ""
                        raise RuntimeError(f"Relay startup failed (exit {child.returncode}){detail}")
                    if time.monotonic() >= deadline:
                        raise RuntimeError("Relay startup timed out")
                    time.sleep(0.1)
                bound = read_config(ready_dir)
                status = call(bound, "/status")
                if status.get("pid") != child.pid:
                    raise RuntimeError("Unexpected Codex relay on the bound port")
                write_config(project, bound)
                return status
            except BaseException:
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=5)
                raise
    finally:
        release_lock(lock)


def serve(project: Path, config: dict | None, codex: str, port: int | None, ready_dir: Path | None) -> None:
    executable = resolve_codex(codex)
    preferred_port = port or (urlsplit(config["url"]).port if config else 0)
    token = config["token"] if config else secrets.token_hex(32)
    backend = CodexBackend([executable])
    try:
        server = RelayServer(("127.0.0.1", preferred_port), token, backend)
    except OSError as exc:
        can_relocate = ready_dir is not None and port is None and config_path(project).exists()
        if not can_relocate or exc.errno not in (errno.EADDRINUSE, errno.EACCES):
            raise
        server = RelayServer(("127.0.0.1", 0), token, backend)
    with server:
        if ready_dir:
            write_config(ready_dir, {"version": 1, "url": f"http://127.0.0.1:{server.server_port}", "token": token})
        server.serve_forever(poll_interval=0.1)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status", "check", "serve"))
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--port", type=int)
    parser.add_argument("--ready-dir", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--codex", default="codex")
    parser.add_argument("--deep", action="store_true")
    parser.add_argument("--model")
    args = parser.parse_args()
    project = args.project.resolve()
    try:
        if args.port is not None and not 1 <= args.port <= 65535:
            raise ValueError("Port must be between 1 and 65535")
        if args.action == "start":
            result = start(project, args.port, args.codex)
        else:
            config = read_config(project)
            if config is None and not (args.action == "serve" and args.ready_dir):
                raise RuntimeError("Proxy is not configured; run /mw proxy start")
            if args.action == "serve":
                serve(project, config, args.codex, args.port, args.ready_dir)
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
