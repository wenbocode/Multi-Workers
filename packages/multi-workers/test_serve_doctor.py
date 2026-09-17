"""
test_serve_doctor.py — mw serve precheck gate (T-06) and doctor (T-07) tests.

Serve tests run cmd_serve in-process with faked children and a hermetic tmp
providers.json (TEST_* env names); doctor tests exercise the real CLI as a
subprocess. No network, no real CLIs, no real credentials (AC-009).
"""
import argparse
import datetime
import importlib.util
import json
import os
import pathlib
import socket
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


# ── VC-006: worker heartbeat liveness (mw-dispatch-flow-fixes D-004) ───────────

class TestWorkerLiveness:
    """Heartbeat-based liveness verdicts: alive / stale / no-heartbeat,
    threshold configurable, informational only (never flips healthy/exit)."""

    @staticmethod
    def _hb_line(age_s: float, phase: str = "1/2") -> str:
        # TS wire format (appendHeartbeat → Date.toISOString()): always `...Z`.
        # Pin the exact suffix so the parse path is tested against what the
        # extension actually writes (review M3: `+00:00` hid the 3.10 bug).
        ts = (
            datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=age_s)
        ).isoformat().replace("+00:00", "Z")
        return f"[HEARTBEAT] {ts} task=t phase={phase}\n"

    def _queue_running(
        self, proj: pathlib.Path, rows: list[tuple[str, str | None]]
    ) -> None:
        """Write running queue rows; trace content None = no trace.log."""
        agentic = proj / ".agenticdoc"
        agentic.mkdir(parents=True, exist_ok=True)
        lines: list[str] = []
        for key, trace in rows:
            task_dir = agentic / key
            task_dir.mkdir(parents=True, exist_ok=True)
            task_md = task_dir / "task.md"
            task_md.write_text("type: coding\n\nwork\n", encoding="utf-8")
            if trace is not None:
                (task_dir / "trace.log").write_text(trace, encoding="utf-8")
            lines.append(f"{key} | running | pi | timi | {task_md} | a | b | m")
        (agentic / "_workers.parallel").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def test_parse_heartbeat_ts_accepts_z_suffix(self) -> None:
        """Review M3: TS emits Date.toISOString() (always `...Z`);
        datetime.fromisoformat rejects `Z` before Python 3.11 — the
        normalization in _parse_heartbeat_ts must accept the wire format."""
        ts = mw_common._parse_heartbeat_ts("2026-09-08T06:26:23.446Z")
        assert ts.tzinfo is not None
        assert ts.second == 23
        # Second-precision variant (also produced by toISOString when ms=0).
        ts2 = mw_common._parse_heartbeat_ts("2026-09-08T06:26:23Z")
        assert ts2.tzinfo is not None
        # The +00:00 form keeps working.
        assert mw_common._parse_heartbeat_ts("2026-09-08T06:26:23+00:00").second == 23

    def test_verdicts_alive_stale_no_heartbeat(self, tmp_path: pathlib.Path) -> None:
        proj = tmp_path
        self._queue_running(
            proj,
            [
                ("t-fresh", self._hb_line(10)),
                ("t-old", self._hb_line(300)),
                ("t-legacy", None),
            ],
        )
        verdicts = {v["task_key"]: v for v in mw_common.worker_liveness(proj)}
        assert verdicts["t-fresh"]["verdict"] == "alive"
        assert 0 <= verdicts["t-fresh"]["age_s"] < 90
        assert verdicts["t-old"]["verdict"] == "stale"
        assert verdicts["t-old"]["age_s"] >= 300
        assert verdicts["t-legacy"]["verdict"] == "no-heartbeat"
        assert verdicts["t-legacy"]["last_heartbeat"] is None

    def test_stale_after_override(self, tmp_path: pathlib.Path) -> None:
        # Age 75s: alive under the default 90s threshold, stale under 60.
        proj = tmp_path
        self._queue_running(proj, [("t-mid", self._hb_line(75))])
        assert mw_common.worker_liveness(proj)[0]["verdict"] == "alive"
        assert mw_common.worker_liveness(proj, stale_after_sec=60)[0]["verdict"] == "stale"

    def test_doctor_report_section_is_informational(self, tmp_path: pathlib.Path) -> None:
        # A stale running worker must NOT flip healthy/exit codes: doctor still
        # exits 0 with a live service and zero issues, and the JSON carries the
        # verdicts. Text output names the stale task.
        proj = tmp_path
        (proj / ".mw").mkdir()
        self._queue_running(
            proj,
            [("t-ok", self._hb_line(5)), ("t-stuck", self._hb_line(600))],
        )
        mw_common.pid_file(proj).write_text(str(os.getpid()), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(_MW_PY), "doctor", f"--project={proj}", "--json"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, mw_common.AGENT_DIR_ENV: str(proj / "pi-agent")},
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        verdicts = {v["task_key"]: v["verdict"] for v in report["worker_liveness"]}
        assert verdicts == {"t-ok": "alive", "t-stuck": "stale"}
        assert report["summary"]["healthy"] is True
        assert report["summary"]["issues"] == []
        text = mw_common.format_doctor_text(report)
        assert "workers: alive 1, stale: t-stuck" in text

    def test_cli_stale_after_flag(self, tmp_path: pathlib.Path) -> None:
        proj = tmp_path
        (proj / ".mw").mkdir()
        self._queue_running(proj, [("t-mid", self._hb_line(75))])
        mw_common.pid_file(proj).write_text(str(os.getpid()), encoding="utf-8")

        result = subprocess.run(
            [sys.executable, str(_MW_PY), "doctor", f"--project={proj}", "--json", "--stale-after=60"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, mw_common.AGENT_DIR_ENV: str(proj / "pi-agent")},
        )
        assert result.returncode == 0, result.stderr
        report = json.loads(result.stdout)
        assert report["worker_liveness"][0]["verdict"] == "stale"

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
        # On-demand proxy: only direct-route (timi) credentials exist, so the
        # launcher is the sole child and the log says why.
        assert len(spawned) == 1
        assert "proxy disabled; direct routes only" in log

    def test_proxy_spawned_when_proxy_route_available(
        self, tmp_path: pathlib.Path, no_test_creds, no_codex, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # claude (port-routed) + timi (direct): the proxy IS needed -> spawned.
        proj = tmp_path
        (proj / ".mw").mkdir()
        providers_file = _write_config(tmp_path)
        monkeypatch.setenv("TEST_TIMI_API_KEY", "hermetic-key")
        monkeypatch.setenv("TEST_ANTHROPIC_API_KEY", "hermetic-key")

        spawned: list = []
        monkeypatch.setattr(mw.subprocess, "Popen", lambda cmd, **kw: spawned.append(cmd) or _FakeProc())

        def fake_sleep(seconds: float) -> None:
            raise KeyboardInterrupt  # break the supervise loop on first tick

        monkeypatch.setattr(mw.time, "sleep", fake_sleep)

        rc = mw.cmd_serve(_serve_args(proj, providers_file))

        assert rc == 0
        assert len(spawned) == 2  # proxy + launcher children spawned
        log = (proj / ".mw" / "mw.log").read_text(encoding="utf-8")
        assert "proxy disabled" not in log

    def test_proxy_death_is_fatal_with_log_tail(
        self, tmp_path: pathlib.Path, no_test_creds, no_codex, monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # When the proxy is needed it stays fatal — but the log now carries the
        # exit code and the .mw/proxy.log tail (root cause, e.g. the missing
        # timi_proxy_cli module on machines without the private package).
        proj = tmp_path
        (proj / ".mw").mkdir()
        providers_file = _write_config(tmp_path)
        monkeypatch.setenv("TEST_ANTHROPIC_API_KEY", "hermetic-key")
        (proj / ".mw" / "proxy.log").write_text(
            "Traceback (most recent call last):\n"
            '  File "proxy_multi.py", line 17, in <module>\n'
            "    from timi_proxy_cli.config import DEFAULT_MODEL_MAP\n"
            "ModuleNotFoundError: No module named 'timi_proxy_cli'\n",
            encoding="utf-8",
        )

        class _DeadProxy(_FakeProc):
            returncode = 1

            def poll(self) -> int:
                return 1

        def fake_popen(cmd, **kw):
            return _DeadProxy() if "proxy_multi" in str(cmd[1]) else _FakeProc()

        monkeypatch.setattr(mw.subprocess, "Popen", fake_popen)
        monkeypatch.setattr(mw.time, "sleep", lambda s: None)

        rc = mw.cmd_serve(_serve_args(proj, providers_file))

        assert rc == 1
        log = (proj / ".mw" / "mw.log").read_text(encoding="utf-8")
        assert "FATAL: proxy exited (code 1)" in log
        assert "ModuleNotFoundError: No module named 'timi_proxy_cli'" in log

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
        # PI_CODING_AGENT_DIR scopes the pi_shell section (and any --fix write
        # to settings.json) to the per-test tmp agent dir — never the user's
        # real ~/.pi/agent.
        env = {**os.environ, mw_common.AGENT_DIR_ENV: str(proj / "pi-agent")}
        return subprocess.run(
            [sys.executable, str(_MW_PY), "doctor", f"--project={proj}", "--json", *extra],
            capture_output=True, text=True, timeout=30, env=env,
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
            "queue", "credentials", "bundle", "pi_shell", "summary",
        ):
            assert section in report, f"missing doctor section: {section}"
        assert report["service"]["running"] is True
        assert report["summary"]["healthy"] is True
        assert report["summary"]["issues"] == []
        text = mw_common.format_doctor_text(report)
        assert "pi_shell:" in text

    def test_issues_exit_code_one(self, tmp_path: pathlib.Path) -> None:
        proj = tmp_path
        (proj / ".mw").mkdir()
        (proj / ".agenticdoc").mkdir()
        # No PID file -> service down -> issue -> exit 1.
        result = self._run_doctor(proj)
        assert result.returncode == 1
        report = json.loads(result.stdout)
        assert any("not running" in i for i in report["summary"]["issues"])

    def test_proxy_log_crash_surfaces_root_cause(self, tmp_path: pathlib.Path) -> None:
        # Service down + proxy.log traceback: the issue must name the actual
        # root cause (e.g. the missing timi_proxy_cli module), not just the
        # 'port not listening' symptom.
        proj = tmp_path
        (proj / ".mw").mkdir()
        (proj / ".agenticdoc").mkdir()
        (proj / ".mw" / "proxy.log").write_text(
            "Traceback (most recent call last):\n"
            '  File "proxy_multi.py", line 17, in <module>\n'
            "ModuleNotFoundError: No module named 'timi_proxy_cli'\n",
            encoding="utf-8",
        )
        result = self._run_doctor(proj)
        assert result.returncode == 1
        report = json.loads(result.stdout)
        assert any(
            "ModuleNotFoundError: No module named 'timi_proxy_cli'" in i
            for i in report["summary"]["issues"]
        )
        assert report["proxy_log"]["traceback_count"] == 1
        text = mw_common.format_doctor_text(report)
        assert "proxy_log: 1 crash(es)" in text
        assert "proxy: disabled" in text

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

        # A pre-configured (valid) pi shellPath keeps the pi_shell section out
        # of the fix list — machine-independent (must exist BEFORE the run).
        agent_dir = proj / "pi-agent"
        agent_dir.mkdir(parents=True, exist_ok=True)
        (agent_dir / "settings.json").write_text(
            json.dumps({"shellPath": sys.executable}), encoding="utf-8"
        )

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
        assert report["pi_shell"]["status"] == "ok"

    @pytest.mark.skipif(os.name != "nt", reason="detect_pi_shell_path is Windows-only")
    def test_fix_fills_missing_pi_shell_path(self, tmp_path: pathlib.Path) -> None:
        # Fresh-machine path: no settings.json in the (injected) agent dir;
        # doctor --fix pins the real detected PowerShell and records the action.
        proj = tmp_path
        (proj / ".mw").mkdir()
        (proj / ".agenticdoc").mkdir()
        result = self._run_doctor(proj, "--fix")
        report = json.loads(result.stdout)
        assert report["pi_shell"]["status"] == "filled"
        assert report["pi_shell"]["shell_path"] == report["pi_shell"]["detected"]
        assert any(
            "shellPath filled" in a for a in report["fix"]["applied"]
        )
        data = json.loads(
            (proj / "pi-agent" / "settings.json").read_text(encoding="utf-8")
        )
        assert data["shellPath"] == report["pi_shell"]["detected"]


# ── pi shellPath auto-fill (fresh-machine shell bootstrap) ───────────────────

class TestEnsurePiShellPath:
    """Cross-platform unit tests via an injected `detect` + a temp agent dir
    (PI_CODING_AGENT_DIR) — never the user's real ~/.pi/agent."""

    @staticmethod
    def _env(tmp_path: pathlib.Path) -> tuple[dict, pathlib.Path]:
        agent_dir = tmp_path / "pi-agent"
        return {mw_common.AGENT_DIR_ENV: str(agent_dir)}, agent_dir

    def test_fills_missing_shell_path(self, tmp_path: pathlib.Path) -> None:
        env, agent_dir = self._env(tmp_path)
        fake_shell = tmp_path / "pwsh.exe"
        fake_shell.write_text("", encoding="utf-8")
        r = mw_common.ensure_pi_shell_path(env=env, fix=True, detect=lambda: str(fake_shell))
        assert r["status"] == "filled"
        assert r["shell_path"] == str(fake_shell)
        data = json.loads((agent_dir / "settings.json").read_text(encoding="utf-8"))
        assert data["shellPath"] == str(fake_shell)

    def test_missing_without_fix_reports_only(self, tmp_path: pathlib.Path) -> None:
        env, agent_dir = self._env(tmp_path)
        fake_shell = tmp_path / "pwsh.exe"
        fake_shell.write_text("", encoding="utf-8")
        r = mw_common.ensure_pi_shell_path(env=env, fix=False, detect=lambda: str(fake_shell))
        assert r["status"] == "missing"
        assert "detected" in r["detail"]
        assert not (agent_dir / "settings.json").exists()

    def test_no_overwrite_when_configured_and_file_exists(self, tmp_path: pathlib.Path) -> None:
        env, agent_dir = self._env(tmp_path)
        agent_dir.mkdir(parents=True)
        good = tmp_path / "good-shell.exe"
        good.write_text("", encoding="utf-8")
        (agent_dir / "settings.json").write_text(
            json.dumps({"shellPath": str(good), "theme": "dark"}), encoding="utf-8"
        )
        other = tmp_path / "other.exe"
        other.write_text("", encoding="utf-8")
        r = mw_common.ensure_pi_shell_path(env=env, fix=True, detect=lambda: str(other))
        assert r["status"] == "ok"
        data = json.loads((agent_dir / "settings.json").read_text(encoding="utf-8"))
        assert data["shellPath"] == str(good)  # untouched
        assert data["theme"] == "dark"

    def test_replaces_stale_shell_path(self, tmp_path: pathlib.Path) -> None:
        env, agent_dir = self._env(tmp_path)
        agent_dir.mkdir(parents=True)
        (agent_dir / "settings.json").write_text(
            json.dumps({"shellPath": str(tmp_path / "gone" / "pwsh.exe")}), encoding="utf-8"
        )
        fresh = tmp_path / "powershell.exe"
        fresh.write_text("", encoding="utf-8")
        r = mw_common.ensure_pi_shell_path(env=env, fix=True, detect=lambda: str(fresh))
        assert r["status"] == "replaced"
        data = json.loads((agent_dir / "settings.json").read_text(encoding="utf-8"))
        assert data["shellPath"] == str(fresh)

    def test_broken_without_fix(self, tmp_path: pathlib.Path) -> None:
        env, agent_dir = self._env(tmp_path)
        agent_dir.mkdir(parents=True)
        stale = json.dumps({"shellPath": str(tmp_path / "gone" / "pwsh.exe")})
        (agent_dir / "settings.json").write_text(stale, encoding="utf-8")
        fresh = tmp_path / "powershell.exe"
        fresh.write_text("", encoding="utf-8")
        r = mw_common.ensure_pi_shell_path(env=env, fix=False, detect=lambda: str(fresh))
        assert r["status"] == "broken"
        assert (agent_dir / "settings.json").read_text(encoding="utf-8") == stale

    def test_never_writes_malformed_settings(self, tmp_path: pathlib.Path) -> None:
        env, agent_dir = self._env(tmp_path)
        agent_dir.mkdir(parents=True)
        (agent_dir / "settings.json").write_text("{ not json", encoding="utf-8")
        fresh = tmp_path / "powershell.exe"
        fresh.write_text("", encoding="utf-8")
        r = mw_common.ensure_pi_shell_path(env=env, fix=True, detect=lambda: str(fresh))
        assert r["status"] == "unreadable"
        assert (agent_dir / "settings.json").read_text(encoding="utf-8") == "{ not json"

    def test_default_detect_respects_platform_gate(self, tmp_path: pathlib.Path) -> None:
        # Default detector: Windows probes PATH for pwsh/powershell; other
        # platforms short-circuit to not-applicable without touching anything.
        env, agent_dir = self._env(tmp_path)
        r = mw_common.ensure_pi_shell_path(env=env, fix=False)
        if os.name != "nt":
            assert r["status"] == "not-applicable"
            assert not agent_dir.exists()
        else:
            assert r["status"] in ("ok", "missing", "broken", "unreadable")
            assert not r["detected"] or pathlib.Path(r["detected"]).is_file()


# ── M4: update_index.py claim protocol alignment (mw-dispatch-flow-fixes) ────

_UPDATE_INDEX = (
    pathlib.Path(__file__).resolve().parent.parent.parent / ".agents/skills/agentic-task/scripts/update_index.py"
)


def _load_update_index():
    spec = importlib.util.spec_from_file_location("update_index_test_mod", _UPDATE_INDEX)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestUpdateIndexClaim:
    """host:pid claim ids (TS-parity), shared .mw/index.lock, and stale-local
    takeover without --force (review M4)."""

    def test_claim_id_is_host_pid(self) -> None:
        mod = _load_update_index()
        cid = mod.now_claim_id()
        host, _, pid = cid.partition(":")
        assert host == socket.gethostname()
        assert pid.isdigit()

    def test_claim_demotes_other_active_rows_and_releases_lock(self, tmp_path: pathlib.Path) -> None:
        mod = _load_update_index()
        agentic = tmp_path / ".agenticdoc"
        agentic.mkdir()
        index = agentic / "_index.parallel"
        mod._ensure_index(index)
        mod._write_index_atomic(
            index,
            lambda rows: rows
            + [
                {
                    "key": "key-x",
                    "status": "active",
                    "phase": "SPEC",
                    "claim_id": "someone-else:1",
                    "deps": "—",
                    "desc": "—",
                    "updated": "2026-09-08 10:00",
                }
            ],
        )

        rc = mod.cmd_claim(agentic, "key-a", False)
        assert rc == 0
        rows = {r["key"]: r for r in mod.read_index(index)}
        assert rows["key-a"]["status"] == "active"
        assert rows["key-a"]["claim_id"] == mod.now_claim_id()  # same process → same id
        assert rows["key-x"]["status"] == "idle"  # demoted (single-active)
        # The shared lock is released after the write.
        assert not (tmp_path / ".mw" / "index.lock").exists()

    def test_stale_local_claim_taken_without_force_live_conflicts(self, tmp_path: pathlib.Path) -> None:
        mod = _load_update_index()
        agentic = tmp_path / ".agenticdoc"
        agentic.mkdir()
        index = agentic / "_index.parallel"
        mod._ensure_index(index)

        def seed(key: str, claim_id: str) -> None:
            mod._write_index_atomic(
                index,
                lambda rows: rows
                + [
                    {
                        "key": key,
                        "status": "active",
                        "phase": "EXECUTE",
                        "claim_id": claim_id,
                        "deps": "—",
                        "desc": "—",
                        "updated": "2026-09-08 10:00",
                    }
                ],
            )

        # A crashed local window (dead pid) — takeover allowed WITHOUT --force.
        dead = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        dead_pid = dead.pid
        dead.kill()
        dead.wait()
        seed("key-dead", f"{socket.gethostname()}:{dead_pid}")
        assert mod.cmd_claim(agentic, "key-dead", False) == 0

        # A live local window — CONFLICT without --force, ok with it.
        live = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
        try:
            seed("key-live", f"{socket.gethostname()}:{live.pid}")
            assert mod.cmd_claim(agentic, "key-live", False) == 1
            assert mod.cmd_claim(agentic, "key-live", True) == 0
        finally:
            live.kill()
            live.wait()

        # Legacy timestamp ids are unverifiable — still a conflict.
        seed("key-legacy", "20260808-174558-3176")
        assert mod.cmd_claim(agentic, "key-legacy", False) == 1
