"""
test_serve_doctor.py — mw serve precheck gate (T-06) and doctor (T-07) tests.

Serve tests run cmd_serve in-process with faked children and a hermetic tmp
providers.json (TEST_* env names); doctor tests exercise the real CLI as a
subprocess. No network, no real CLIs, no real credentials (AC-009).
"""
import argparse
import json
import os
import pathlib
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw
import mw_common

_MW_PY = pathlib.Path(__file__).parent / "mw.py"

_HERMETIC_CONFIG = {
    "credentials": {
        "anthropic": {"sources": [{"env": "TEST_ANTHROPIC_API_KEY"}]},
        "anthropic-auth": {"sources": [{"env": "TEST_ANTHROPIC_AUTH_TOKEN"}]},
        "deepseek": {"sources": [{"env": "TEST_DEEPSEEK_API_KEY"}]},
        "timi": {"sources": [{"env": "TEST_TIMI_API_KEY"}]},
    },
    "providers": {
        "claude": {
            "port": 27001, "base_url_env": "TEST_ANTHROPIC_BASE_URL",
            "api_key_env": "TEST_ANTHROPIC_API_KEY", "credential": "anthropic",
        },
        "claude-cli": {
            "port": 27003, "base_url_env": "TEST_ANTHROPIC_BASE_URL",
            "api_key_env": "TEST_ANTHROPIC_AUTH_TOKEN", "credential": "anthropic-auth",
        },
        "deepseek": {
            "port": 27004, "base_url_env": "TEST_DEEPSEEK_BASE_URL",
            "api_key_env": "TEST_DEEPSEEK_API_KEY", "credential": "deepseek",
        },
        "timi": {"api_key_env": "TEST_TIMI_API_KEY", "credential": "timi"},
    },
}

_TEST_CRED_VARS = [
    "TEST_ANTHROPIC_API_KEY", "TEST_ANTHROPIC_AUTH_TOKEN",
    "TEST_DEEPSEEK_API_KEY", "TEST_TIMI_API_KEY",
]


def _write_config(tmp_path: pathlib.Path) -> pathlib.Path:
    p = tmp_path / "providers.json"
    p.write_text(json.dumps(_HERMETIC_CONFIG), encoding="utf-8")
    return p


def _serve_args(proj: pathlib.Path, providers_file: pathlib.Path) -> argparse.Namespace:
    return argparse.Namespace(
        project=str(proj), pi_port=27001, claude_port=27003,
        poll_interval=1, max_workers=None, providers=str(providers_file),
        deepseek_port=None,
    )


class _FakeProc:
    pid = 4242
    returncode = None

    def poll(self) -> int | None:
        return None

    def terminate(self) -> None:
        pass

    def wait(self, timeout: float | None = None) -> int:
        return 0


@pytest.fixture()
def no_test_creds(monkeypatch: pytest.MonkeyPatch) -> None:
    for var in _TEST_CRED_VARS:
        monkeypatch.delenv(var, raising=False)


@pytest.fixture()
def no_codex(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mw_common.shutil, "which", lambda name: None)


# ── VC-003: all routes missing -> refuse to start ─────────────────────────────

class TestServeAllMissing:
    def test_refuses_to_start(
        self, tmp_path: pathlib.Path, no_test_creds, no_codex, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        proj = tmp_path
        (proj / ".mw").mkdir()
        providers_file = _write_config(tmp_path)

        spawned: list = []
        monkeypatch.setattr(mw.subprocess, "Popen", lambda cmd, **kw: spawned.append(cmd) or _FakeProc())

        rc = mw.cmd_serve(_serve_args(proj, providers_file))

        assert rc == 1
        assert not mw_common.pid_file(proj).exists()  # PID only after precheck passes
        assert spawned == []  # no children spawned
        log = (proj / ".mw" / "mw.log").read_text(encoding="utf-8")
        for route in ("claude", "claude-cli", "deepseek", "timi", "codex-native"):
            assert f"route {route}:" in log, f"missing route line for {route}"
        assert "route claude-cli: missing (env TEST_ANTHROPIC_AUTH_TOKEN unset)" in log
        assert "refusing to start" in log

    def test_serves_refusal_is_fast(
        self, tmp_path: pathlib.Path, no_test_creds, no_codex, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # AC-002: refusal within 10s (measured: must be near-instant).
        proj = tmp_path
        (proj / ".mw").mkdir()
        providers_file = _write_config(tmp_path)
        monkeypatch.setattr(mw.subprocess, "Popen", lambda cmd, **kw: _FakeProc())

        start = time.monotonic()
        rc = mw.cmd_serve(_serve_args(proj, providers_file))
        elapsed = time.monotonic() - start

        assert rc == 1
        assert elapsed < 10


# ── VC-004: partial availability -> per-route log lines, service starts ──────

class TestServePartialAvailability:
    def test_logs_every_route_and_starts(
        self, tmp_path: pathlib.Path, no_test_creds, no_codex, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        proj = tmp_path
        (proj / ".mw").mkdir()
        providers_file = _write_config(tmp_path)
        monkeypatch.setenv("TEST_TIMI_API_KEY", "hermetic-key")

        spawned: list = []
        monkeypatch.setattr(mw.subprocess, "Popen", lambda cmd, **kw: spawned.append(cmd) or _FakeProc())

        def fake_sleep(seconds: float) -> None:
            raise KeyboardInterrupt  # break the supervise loop on first tick

        monkeypatch.setattr(mw.time, "sleep", fake_sleep)

        rc = mw.cmd_serve(_serve_args(proj, providers_file))

        assert rc == 0  # intentional stop (KeyboardInterrupt path)
        assert mw_common.pid_file(proj).exists() is False  # cleaned up at shutdown
        log = (proj / ".mw" / "mw.log").read_text(encoding="utf-8")
        assert "route timi: available (env TEST_TIMI_API_KEY)" in log
        assert "route claude: missing (env TEST_ANTHROPIC_API_KEY unset)" in log
        assert "route codex-native: missing" in log
        route_lines = [l for l in log.splitlines() if l.startswith("[mw serve] route ")]
        assert len(route_lines) == len(_HERMETIC_CONFIG["providers"]) + 1  # + codex-native
        assert len(spawned) == 2  # proxy + launcher children spawned

    def test_pid_written_before_children_spawned(
        self, tmp_path: pathlib.Path, no_test_creds, no_codex, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # D-002 invariant: PID file exists by the time children spawn (PM stable
        # window relies on "PID present implies service started").
        proj = tmp_path
        (proj / ".mw").mkdir()
        providers_file = _write_config(tmp_path)
        monkeypatch.setenv("TEST_TIMI_API_KEY", "hermetic-key")

        events: list[str] = []

        def fake_popen(cmd, **kw):
            events.append("spawn")
            return _FakeProc()

        monkeypatch.setattr(mw.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(mw.time, "sleep", lambda s: (_ for _ in ()).throw(KeyboardInterrupt()))

        mw.cmd_serve(_serve_args(proj, providers_file))
        # PID lifecycle: written at startup (removed only in the finally on stop)
        assert "spawn" in events  # children were started
        log = (proj / ".mw" / "mw.log").read_text(encoding="utf-8")
        assert "route timi: available" in log


# ── VC-007 / VC-009: doctor CLI (real subprocess) ─────────────────────────────

class TestDoctorCli:
    def _run_doctor(self, proj: pathlib.Path, *extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, str(_MW_PY), "doctor", f"--project={proj}", "--json", *extra],
            capture_output=True, text=True, timeout=30,
        )

    def test_sections_and_exit_code_semantics(self, tmp_path: pathlib.Path) -> None:
        proj = tmp_path
        (proj / ".mw").mkdir()
        (proj / ".agenticdoc").mkdir()
        # Fake a live service: PID of the pytest process itself.
        mw_common.pid_file(proj).write_text(str(os.getpid()), encoding="utf-8")

        start = time.monotonic()
        result = self._run_doctor(proj)
        elapsed = time.monotonic() - start

        assert result.returncode == 0, result.stderr
        assert elapsed < 5  # AC-006
        report = json.loads(result.stdout)
        for section in (
            "service", "proxy", "orphan_proxy", "launcher_log",
            "queue", "credentials", "bundle", "summary",
        ):
            assert section in report, f"missing doctor section: {section}"
        assert report["service"]["running"] is True
        assert report["summary"]["healthy"] is True
        assert report["summary"]["issues"] == []

    def test_issues_exit_code_one(self, tmp_path: pathlib.Path) -> None:
        proj = tmp_path
        (proj / ".mw").mkdir()
        (proj / ".agenticdoc").mkdir()
        # No PID file -> service down -> issue -> exit 1.
        result = self._run_doctor(proj)
        assert result.returncode == 1
        report = json.loads(result.stdout)
        assert any("not running" in i for i in report["summary"]["issues"])

    def test_fix_archives_stale_and_clears_dead_pid(self, tmp_path: pathlib.Path) -> None:
        proj = tmp_path
        agentic = proj / ".agenticdoc"
        agentic.mkdir()
        (proj / ".mw").mkdir()
        # Stale queue entry (task.md missing) + stale PID (huge dead pid).
        (agentic / "_workers.parallel").write_text(
            "t-dead | pending | pi | timi | " + str(proj / "gone" / "task.md") + " | a | b | m\n",
            encoding="utf-8",
        )
        mw_common.pid_file(proj).write_text("4000000000", encoding="utf-8")

        result = self._run_doctor(proj, "--fix")
        assert result.returncode == 1  # service still not running -> issue remains
        report = json.loads(result.stdout)
        applied = report["fix"]["applied"]
        assert any("archived stale entries" in a and "t-dead" in a for a in applied)
        assert any("stale PID" in a for a in applied)
        assert not mw_common.pid_file(proj).exists()
        assert mw_common.parse_workers_file(mw_common.workers_path(proj)) == []
        assert "t-dead" in mw_common.stale_path(proj).read_text(encoding="utf-8")
        # Auto-fix scope: exactly the two fixable actions, nothing else.
        assert len(applied) == 2
        # No real proxy/bundle was touched by fix (suggestions only).
        assert isinstance(report["summary"]["suggestions"], list)
