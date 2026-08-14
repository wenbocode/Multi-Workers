"""
mw.py — Multi-Workers service manager.

Subcommands:
  serve  — foreground: start proxy_multi + launcher, block until Ctrl-C/SIGTERM
  start  — background: detach and run serve
  stop   — send SIGTERM to running mw serve
  status — check if mw serve is running
  init   — install Extension bundle into project (implemented in T-14)
"""

from __future__ import annotations

import argparse
import os
import pathlib
import signal
import subprocess
import sys
import time

_SCRIPT_DIR = pathlib.Path(__file__).parent
_LAUNCHER_PY = _SCRIPT_DIR / "launcher.py"
_PROXY_MULTI_PY = _SCRIPT_DIR / "proxy_multi.py"


# ── PID helpers ──────────────────────────────────────────────────────────────

def _pid_path(project_dir: pathlib.Path) -> pathlib.Path:
    return project_dir / ".mw" / "mw.pid"


def _write_pid(pid_path: pathlib.Path) -> None:
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()), encoding="utf-8")


def _remove_pid(pid_path: pathlib.Path) -> None:
    try:
        pid_path.unlink()
    except FileNotFoundError:
        pass


def _is_alive_win32(pid: int) -> bool:
    """Read-only liveness check via Win32 OpenProcess + GetExitCodeProcess."""
    import ctypes
    import ctypes.wintypes

    _PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    _STILL_ACTIVE = 259

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return False
    try:
        exit_code = ctypes.wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return False
        return bool(exit_code.value == _STILL_ACTIVE)
    finally:
        kernel32.CloseHandle(handle)


def _check_pid(pid_path: pathlib.Path) -> int | None:
    """Return PID if file exists and process is alive, else None."""
    if not pid_path.exists():
        return None
    try:
        pid = int(pid_path.read_text(encoding="utf-8").strip())
    except (ValueError, OSError):
        return None
    try:
        if sys.platform == "win32":
            return pid if _is_alive_win32(pid) else None
        os.kill(pid, 0)
        return pid
    except (ProcessLookupError, PermissionError, OSError):
        return None


def _stop_request_path(project_dir: pathlib.Path) -> pathlib.Path:
    return project_dir / ".mw" / "mw.stop"


def _write_stop_request(project_dir: pathlib.Path) -> None:
    p = _stop_request_path(project_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("stop", encoding="utf-8")


def _clear_stop_request(project_dir: pathlib.Path) -> None:
    try:
        _stop_request_path(project_dir).unlink()
    except FileNotFoundError:
        pass


# ── Subcommand: serve ────────────────────────────────────────────────────────

def cmd_serve(args: argparse.Namespace) -> int:
    import threading

    project_dir = pathlib.Path(args.project).resolve()
    pid_path = _pid_path(project_dir)

    existing = _check_pid(pid_path)
    if existing is not None:
        print(
            f"[mw serve] already running (PID {existing}). Use 'mw stop' first.",
            file=sys.stderr,
        )
        return 1

    _clear_stop_request(project_dir)
    _write_pid(pid_path)

    intentional_stop = threading.Event()
    exit_code = 1  # default: unexpected/error exit
    proxy_proc: subprocess.Popen[bytes] | None = None
    launcher_proc: subprocess.Popen[bytes] | None = None

    try:
        proxy_cmd = [
            sys.executable,
            str(_PROXY_MULTI_PY),
            f"--pi-port={args.pi_port}",
            f"--claude-port={args.claude_port}",
        ]
        if args.deepseek_port:
            proxy_cmd.append(f"--deepseek-port={args.deepseek_port}")
        proxy_proc = subprocess.Popen(proxy_cmd)  # noqa: S603

        launcher_cmd = [
            sys.executable,
            str(_LAUNCHER_PY),
            f"--project={project_dir}",
            f"--poll-interval={args.poll_interval}",
            f"--pi-port={args.pi_port}",
            f"--claude-port={args.claude_port}",
        ]
        if args.deepseek_port:
            launcher_cmd.append(f"--deepseek-port={args.deepseek_port}")
        if args.max_workers:
            launcher_cmd.append(f"--max-workers={args.max_workers}")
        if args.providers:
            launcher_cmd.append(f"--providers={args.providers}")

        launcher_proc = subprocess.Popen(launcher_cmd)  # noqa: S603

        print(
            f"[mw serve] started (PID {os.getpid()}) — proxy={proxy_proc.pid} launcher={launcher_proc.pid}",
            flush=True,
        )

        if sys.platform != "win32":
            def _on_sigterm(signum: int, frame: object) -> None:  # noqa: ARG001
                intentional_stop.set()
            signal.signal(signal.SIGTERM, _on_sigterm)

        try:
            while True:
                if intentional_stop.is_set():
                    break
                if _stop_request_path(project_dir).exists():
                    _clear_stop_request(project_dir)
                    intentional_stop.set()
                    break
                if proxy_proc.poll() is not None or launcher_proc.poll() is not None:
                    break
                time.sleep(1)
        except KeyboardInterrupt:
            intentional_stop.set()

        exit_code = 0 if intentional_stop.is_set() else 1

    finally:
        for proc in (launcher_proc, proxy_proc):
            if proc is not None:
                try:
                    proc.terminate()
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        pass
                except Exception:
                    pass
        _remove_pid(pid_path)
        _clear_stop_request(project_dir)
        print("[mw serve] stopped", flush=True)

    return exit_code


# ── Subcommand: start ────────────────────────────────────────────────────────

def cmd_start(args: argparse.Namespace) -> int:
    """Detach and run mw serve in the background."""
    cmd = [sys.executable, str(pathlib.Path(__file__).resolve()), "serve"]
    # Forward serve-relevant args
    cmd += [
        f"--project={args.project}",
        f"--pi-port={args.pi_port}",
        f"--claude-port={args.claude_port}",
        f"--poll-interval={args.poll_interval}",
    ]
    if args.max_workers:
        cmd.append(f"--max-workers={args.max_workers}")
    if args.providers:
        cmd.append(f"--providers={args.providers}")
    if args.deepseek_port:
        cmd.append(f"--deepseek-port={args.deepseek_port}")

    if sys.platform == "win32":
        # START /B equivalent: CREATE_NEW_PROCESS_GROUP + DETACHED_PROCESS
        import subprocess as _sp

        proc = _sp.Popen(  # noqa: S603
            cmd,
            creationflags=_sp.DETACHED_PROCESS | _sp.CREATE_NEW_PROCESS_GROUP,
            close_fds=True,
        )
    else:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            start_new_session=True,
            close_fds=True,
        )

    print(f"[mw start] background PID: {proc.pid}")
    return 0


# ── Subcommand: stop ─────────────────────────────────────────────────────────

def cmd_stop(args: argparse.Namespace) -> int:
    project_dir = pathlib.Path(args.project).resolve()
    pid_path = _pid_path(project_dir)
    pid = _check_pid(pid_path)
    if pid is None:
        print("[mw stop] not running (no PID or process not found)")
        return 0
    _write_stop_request(project_dir)
    # Wait up to 30s for serve to exit (no force-kill)
    for _ in range(60):
        time.sleep(0.5)
        if _check_pid(pid_path) is None:
            print(f"[mw stop] stopped PID {pid}")
            return 0
    print(f"[mw stop] warning: process {pid} did not exit in 30s")
    return 1


# ── Subcommand: status ───────────────────────────────────────────────────────

def cmd_status(args: argparse.Namespace) -> int:
    project_dir = pathlib.Path(args.project).resolve()
    pid_path = _pid_path(project_dir)
    pid = _check_pid(pid_path)
    if pid is not None:
        print(f"[mw status] running (PID {pid})")
        return 0
    else:
        print("[mw status] not running")
        return 1


# ── Subcommand: init ─────────────────────────────────────────────────────────

_BUNDLE_REL = pathlib.Path("dist") / "extensions" / "agent-team-loop.js"


def _bundle_path() -> pathlib.Path:
    return _SCRIPT_DIR / _BUNDLE_REL


def _check_bundle() -> bool:
    return _bundle_path().exists()


def _sync_dir(src: pathlib.Path, dst: pathlib.Path) -> None:
    """Copy files from src into dst; only update files that exist in src. Keep dst-only files."""
    import shutil
    for item in src.rglob("*"):
        if item.is_file():
            rel = item.relative_to(src)
            target = dst / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(item), str(target))


def cmd_init(args: argparse.Namespace) -> int:
    # AC-036: bundle must exist before creating any directories
    if not _check_bundle():
        print(
            f"[mw init] Error: Extension bundle not found at {_bundle_path()}\n"
            "Run 'bash packages/multi-workers/build-extension.sh' to build it first.",
            file=sys.stderr,
        )
        return 1

    project_dir = pathlib.Path(args.project).resolve()

    # AC-020: create directory structure
    (project_dir / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (project_dir / ".mw").mkdir(parents=True, exist_ok=True)
    (project_dir / ".pi" / "extensions").mkdir(parents=True, exist_ok=True)

    # Create placeholder files
    index_md = project_dir / ".agenticdoc" / "_index.md"
    if not index_md.exists():
        index_md.write_text("# AgenticTask Index\n\nactive: \n", encoding="utf-8")

    index_parallel = project_dir / ".agenticdoc" / "_index.parallel"
    if not index_parallel.exists():
        index_parallel.write_text("", encoding="utf-8")

    # AC-036: install Extension bundle
    import shutil
    bundle_dst = project_dir / ".pi" / "extensions" / "agent-team-loop.js"
    shutil.copy2(str(_bundle_path()), str(bundle_dst))
    print(f"[mw init] Extension installed: {bundle_dst}")

    # AC-022: optional --sync-agentictask
    if args.sync_agentictask:
        src_dir = pathlib.Path(args.sync_agentictask).resolve()
        if not src_dir.is_dir():
            print(f"[mw init] Warning: --sync-agentictask source not found: {src_dir}", file=sys.stderr)
        else:
            dst_dir = project_dir / ".claude"
            _sync_dir(src_dir, dst_dir)
            print(f"[mw init] AgenticTask synced: {src_dir} → {dst_dir}")

    print(f"[mw init] Project initialized: {project_dir}")
    return 0


# ── CLI ───────────────────────────────────────────────────────────────────────

def _add_serve_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--project", required=True, help="Project directory")
    parser.add_argument("--pi-port", type=int, default=7001)
    parser.add_argument("--claude-port", type=int, default=7003)
    parser.add_argument("--deepseek-port", type=int, default=None)
    parser.add_argument("--poll-interval", type=int, default=5)
    parser.add_argument("--max-workers", type=int, default=None)
    parser.add_argument("--providers", default=None)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-Workers service manager")
    sub = parser.add_subparsers(dest="subcommand", required=True)

    _add_serve_args(sub.add_parser("serve", help="Run in foreground"))
    _add_serve_args(sub.add_parser("start", help="Run in background"))

    for name in ("stop", "status"):
        p = sub.add_parser(name)
        p.add_argument("--project", required=True)

    init_p = sub.add_parser("init", help="Initialize project and install Extension")
    init_p.add_argument("--project", required=True)
    init_p.add_argument("--sync-agentictask", default=None, metavar="SOURCE_DIR",
                        help="Sync AgenticTask platform files from SOURCE_DIR into .claude/")

    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    dispatch = {
        "serve": cmd_serve,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "init": cmd_init,
    }
    sys.exit(dispatch[args.subcommand](args))
