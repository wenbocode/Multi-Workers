"""
test_proxy_service.py — static scan (VC-011) and lifecycle supervision tests (VC-012).
"""
import argparse
import pathlib
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import mw
from mw import cmd_serve, cmd_stop, _write_stop_request, _stop_request_path

_MW_DIR = pathlib.Path(__file__).parent


# ── VC-011 static scan ────────────────────────────────────────────────────────

def test_vc011_no_codex_proxy_7002():
    """VC-011: port-7002 and --codex-port must be absent from all six public surfaces."""
    surfaces = [
        _MW_DIR / "providers.json",
        _MW_DIR / "launcher.py",
        _MW_DIR / "proxy_multi.py",
        _MW_DIR / "mw.py",
        _MW_DIR / "smoke_test.sh",
        _MW_DIR / "dispatch-table.md",
    ]
    for path in surfaces:
        content = path.read_text(encoding="utf-8")
        assert "7002" not in content, f"{path.name} still references 7002"
        assert "codex-port" not in content, f"{path.name} still references codex-port"
    print("[VERIFY] VC-011: surfaces=6 failures=0")


# ── VC-012 helpers ────────────────────────────────────────────────────────────

def _make_serve_args(project_dir: pathlib.Path) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(project_dir),
        pi_port=17001,
        claude_port=17003,
        poll_interval=5,
        max_workers=None,
        providers=None,
        deepseek_port=None,
    )


class _FakeProc:
    def __init__(self, pid: int, exits_immediately: bool = False) -> None:
        self.pid = pid
        self.returncode = 1 if exits_immediately else None

    def poll(self) -> "int | None":
        return self.returncode

    def terminate(self) -> None:
        pass

    def wait(self, timeout: "float | None" = None) -> None:
        pass

    def kill(self) -> None:
        pass


def _popen_factory(*procs: "_FakeProc"):
    queue = list(procs)

    def _popen(*args, **kwargs):  # noqa: ARG001
        return queue.pop(0)

    return _popen


# ── VC-012 serve supervision tests ────────────────────────────────────────────

class TestServeSupervision:
    def test_unexpected_proxy_exit_returns_nonzero(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        proxy = _FakeProc(1234, exits_immediately=True)
        launcher = _FakeProc(5678)
        monkeypatch.setattr(mw.subprocess, "Popen", _popen_factory(proxy, launcher))
        monkeypatch.setattr(mw.time, "sleep", lambda _x: None)
        assert cmd_serve(_make_serve_args(project_dir)) == 1

    def test_unexpected_launcher_exit_returns_nonzero(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        proxy = _FakeProc(1234)
        launcher = _FakeProc(5678, exits_immediately=True)
        monkeypatch.setattr(mw.subprocess, "Popen", _popen_factory(proxy, launcher))
        monkeypatch.setattr(mw.time, "sleep", lambda _x: None)
        assert cmd_serve(_make_serve_args(project_dir)) == 1

    def test_stop_file_shutdown_returns_zero(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        proxy = _FakeProc(1234)
        launcher = _FakeProc(5678)
        monkeypatch.setattr(mw.subprocess, "Popen", _popen_factory(proxy, launcher))

        def _write_after_delay() -> None:
            import time as _t
            _t.sleep(0.05)
            _write_stop_request(project_dir)

        threading.Thread(target=_write_after_delay, daemon=True).start()
        assert cmd_serve(_make_serve_args(project_dir)) == 0

    def test_keyboard_interrupt_returns_zero(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        proxy = _FakeProc(1234)
        launcher = _FakeProc(5678)
        monkeypatch.setattr(mw.subprocess, "Popen", _popen_factory(proxy, launcher))

        def _raise_ki(_x: float) -> None:
            raise KeyboardInterrupt

        monkeypatch.setattr(mw.time, "sleep", _raise_ki)
        assert cmd_serve(_make_serve_args(project_dir)) == 0

    def test_stale_stop_file_cleared_on_startup(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        _write_stop_request(project_dir)
        assert _stop_request_path(project_dir).exists()

        proxy = _FakeProc(1234, exits_immediately=True)
        launcher = _FakeProc(5678)
        monkeypatch.setattr(mw.subprocess, "Popen", _popen_factory(proxy, launcher))
        monkeypatch.setattr(mw.time, "sleep", lambda _x: None)
        cmd_serve(_make_serve_args(project_dir))
        assert not _stop_request_path(project_dir).exists()

    def test_pid_file_removed_after_exit(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        proxy = _FakeProc(1234, exits_immediately=True)
        launcher = _FakeProc(5678)
        monkeypatch.setattr(mw.subprocess, "Popen", _popen_factory(proxy, launcher))
        monkeypatch.setattr(mw.time, "sleep", lambda _x: None)
        cmd_serve(_make_serve_args(project_dir))
        assert not (project_dir / ".mw" / "mw.pid").exists()


# ── VC-012 stop supervision tests ─────────────────────────────────────────────

class TestStopSupervision:
    def test_stop_not_running_returns_zero(self, tmp_path: pathlib.Path) -> None:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        args = argparse.Namespace(project=str(project_dir))
        assert cmd_stop(args) == 0

    def test_stop_timeout_returns_nonzero(self, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        project_dir = tmp_path / "proj"
        project_dir.mkdir()
        pid_path = project_dir / ".mw" / "mw.pid"
        pid_path.parent.mkdir(parents=True, exist_ok=True)
        pid_path.write_text("99999", encoding="utf-8")
        monkeypatch.setattr(mw, "_check_pid", lambda _path: 99999)
        monkeypatch.setattr(mw.time, "sleep", lambda _x: None)
        args = argparse.Namespace(project=str(project_dir))
        assert cmd_stop(args) == 1
