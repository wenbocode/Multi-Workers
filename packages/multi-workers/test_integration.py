"""
test_integration.py — L1 integration tests with fake CLI injection (T-11/T-12).

Runs the REAL launcher (and for one case the real `mw serve`) against a tmp
project whose worker CLIs are fakes on PATH. Zero LLM calls, zero real
pi/claude/codex processes (AC-009/AC-010).

Fake CLI contract: the task prompt carries directives the fake understands:
  EXITCODE<n>  exit with code n
  SLEEP<ms>    sleep n milliseconds first
Each invocation appends invocation-NNN.txt under $FAKE_MARK_DIR.
"""
import json
import os
import pathlib
import subprocess
import sys
import threading
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import mw_common

PKG_DIR = pathlib.Path(__file__).parent
LAUNCHER = PKG_DIR / "launcher.py"
MW_PY = PKG_DIR / "mw.py"

_TEST_CRED_VARS = [
    "TEST_ANTHROPIC_API_KEY", "TEST_ANTHROPIC_AUTH_TOKEN",
    "TEST_DEEPSEEK_API_KEY", "TEST_TIMI_API_KEY", "TEST_DUMMY_KEY",
]

INTEGRATION_CONFIG = {
    "credentials": {
        "anthropic": {"sources": [{"env": "TEST_ANTHROPIC_API_KEY"}]},
        "anthropic-auth": {"sources": [{"env": "TEST_ANTHROPIC_AUTH_TOKEN"}]},
        "deepseek": {"sources": [{"env": "TEST_DEEPSEEK_API_KEY"}]},
        "timi": {"sources": [{"env": "TEST_TIMI_API_KEY"}]},
    },
    "providers": {
        "claude": {
            "port": 28001, "base_url_env": "TEST_ANTHROPIC_BASE_URL",
            "api_key_env": "TEST_ANTHROPIC_API_KEY", "credential": "anthropic",
        },
        "claude-cli": {
            "port": 28003, "base_url_env": "TEST_ANTHROPIC_BASE_URL",
            "api_key_env": "TEST_ANTHROPIC_AUTH_TOKEN", "credential": "anthropic-auth",
        },
        "deepseek": {
            "port": 28004, "base_url_env": "TEST_DEEPSEEK_BASE_URL",
            "api_key_env": "TEST_DEEPSEEK_API_KEY", "credential": "deepseek",
        },
        "timi": {"api_key_env": "TEST_TIMI_API_KEY", "credential": "timi"},
    },
}

_FAKE_CLI_PY = '''\
import os, pathlib, re, sys, time
mark_dir = pathlib.Path(os.environ["FAKE_MARK_DIR"])
mark_dir.mkdir(parents=True, exist_ok=True)
seq = len(list(mark_dir.glob("invocation-*.txt")))
(mark_dir / f"invocation-{seq:03d}.txt").write_text(" ".join(sys.argv[1:]), encoding="utf-8")
# Directives live in the task body: the launcher passes a short starter naming
# the task file (VC-031: the body never travels through argv). Read the task
# file via PI_WORKER_TASK (set by the launcher for pi workers) or via a
# task.md path embedded in the starter prompt.
texts = list(sys.argv[1:])
task_path = os.environ.get("PI_WORKER_TASK", "")
if not task_path:
    for a in sys.argv[1:]:
        m = re.search(r"(?:[A-Za-z]:[\\\\/]|[\\/])\\S*task\\.md", a)
        if m:
            task_path = m.group(0)
            break
if task_path and os.path.isfile(task_path):
    texts.append(pathlib.Path(task_path).read_text(encoding="utf-8", errors="replace"))
code = 0
for a in texts:
    m = re.search(r"EXITCODE(\\d+)", a)
    if m:
        code = int(m.group(1))
    m2 = re.search(r"SLEEP(\\d+)", a)
    if m2:
        time.sleep(int(m2.group(1)) / 1000.0)
sys.exit(code)
'''

_CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0


@pytest.fixture()
def proj(tmp_path: pathlib.Path) -> pathlib.Path:
    (tmp_path / ".agenticdoc").mkdir()
    (tmp_path / ".mw").mkdir()
    (tmp_path / "providers.json").write_text(json.dumps(INTEGRATION_CONFIG), encoding="utf-8")
    (tmp_path / "marks").mkdir()
    return tmp_path


@pytest.fixture()
def fakebin(tmp_path: pathlib.Path) -> pathlib.Path:
    d = tmp_path / "fakebin"
    d.mkdir()
    (d / "fake_cli.py").write_text(_FAKE_CLI_PY, encoding="utf-8")
    if sys.platform == "win32":
        (d / "pi.cmd").write_text('@python "%~dp0fake_cli.py" %*\r\n', encoding="utf-8")
    else:
        p = d / "pi"
        p.write_text('#!/bin/sh\nexec python3 "$(dirname "$0")/fake_cli.py" "$@"\n', encoding="utf-8")
        p.chmod(0o755)
    return d


@pytest.fixture()
def start_launcher(proj: pathlib.Path, fakebin: pathlib.Path):
    """Start real launcher subprocesses; teardown terminates them all."""
    procs: list[subprocess.Popen] = []
    logs: list = []

    def _start(extra_env: dict | None = None, max_workers: int | None = None) -> subprocess.Popen:
        env = dict(os.environ)
        env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
        env["FAKE_MARK_DIR"] = str(proj / "marks")
        for var in _TEST_CRED_VARS:
            env.pop(var, None)
        if extra_env:
            env.update(extra_env)
        cmd = [
            sys.executable, str(LAUNCHER),
            "--project", str(proj),
            "--poll-interval", "1",
            "--providers", str(proj / "providers.json"),
        ]
        if max_workers:
            cmd += ["--max-workers", str(max_workers)]
        log = open(proj / "launcher-out.log", "ab")
        logs.append(log)
        proc = subprocess.Popen(
            cmd, env=env, stdout=log, stderr=subprocess.STDOUT,
            creationflags=_CREATE_NO_WINDOW,
        )
        procs.append(proc)
        return proc

    yield _start

    for proc in procs:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
    for log in logs:
        log.close()


# ── helpers ───────────────────────────────────────────────────────────────────

def _read_status(proj: pathlib.Path) -> dict[str, str]:
    return {
        e["task_key"]: e["status"]
        for e in mw_common.parse_workers_file(mw_common.workers_path(proj))
    }


def _wait_for(
    proj: pathlib.Path, key: str, statuses: set[str],
    timeout: float = 60, proc: subprocess.Popen | None = None,
) -> str:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = _read_status(proj).get(key)
        if last in statuses:
            return last
        if proc is not None and proc.poll() is not None:
            tail = ""
            log = proj / "launcher-out.log"
            if log.exists():
                tail = log.read_text(encoding="utf-8", errors="replace")[-1500:]
            raise AssertionError(
                f"launcher died (exit={proc.returncode}) while waiting for {key}; "
                f"launcher.log tail:\n{tail}"
            )
        time.sleep(0.2)
    raise AssertionError(f"task {key} never reached {statuses} within {timeout}s (last={last})")


def _wait_transition_at(proj: pathlib.Path, key: str, statuses: set[str], timeout: float = 30) -> float:
    """Monotonic timestamp when key first observed in statuses."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _read_status(proj).get(key) in statuses:
            return time.monotonic()
        time.sleep(0.05)
    raise AssertionError(f"task {key} never reached {statuses}")


def _make_task(
    proj: pathlib.Path, key: str, prompt: str,
    cli: str = "pi", provider: str = "timi", model: str = "",
) -> pathlib.Path:
    task_dir = proj / ".agenticdoc" / key
    task_dir.mkdir(parents=True, exist_ok=True)
    task_md = task_dir / "task.md"
    task_md.write_text(f"type: coding\n\n{prompt}\n", encoding="utf-8")
    now = mw_common.iso_now()
    row = mw_common.serialize_entry({
        "task_key": key, "status": "pending", "cli": cli, "provider": provider,
        "task_path": str(task_md), "dispatched_at": now, "updated_at": now,
        "model": model,
    })
    with mw_common.workers_path(proj).open("a", encoding="utf-8") as fh:
        fh.write(row + "\n")
    return task_md


def _add_raw_row(proj: pathlib.Path, key: str, status: str, task_path: pathlib.Path) -> None:
    now = mw_common.iso_now()
    row = mw_common.serialize_entry({
        "task_key": key, "status": status, "cli": "pi", "provider": "timi",
        "task_path": str(task_path), "dispatched_at": now, "updated_at": now,
        "model": "",
    })
    with mw_common.workers_path(proj).open("a", encoding="utf-8") as fh:
        fh.write(row + "\n")


# ── VC-011: exit-code state machine through the real launcher ────────────────

class TestExitCodeStateMachine:
    def test_exit0_done_exit1_failed_with_worker_logs(
        self, proj: pathlib.Path, start_launcher,
    ) -> None:
        _make_task(proj, "t-ok", "do work EXITCODE0")
        _make_task(proj, "t-bad", "do work EXITCODE1")
        proc = start_launcher({"TEST_TIMI_API_KEY": "hermetic"})

        assert _wait_for(proj, "t-ok", {"done"}, proc=proc) == "done"
        assert _wait_for(proj, "t-bad", {"failed"}, proc=proc) == "failed"
        assert (proj / ".agenticdoc" / "t-ok" / "worker.log").exists()
        assert (proj / ".agenticdoc" / "t-bad" / "worker.log").exists()
        time.sleep(1.5)
        assert proc.poll() is None  # launcher alive after both tasks

    def test_exit2_needs_clarification(self, proj: pathlib.Path, start_launcher) -> None:
        _make_task(proj, "t-cl", "do work EXITCODE2")
        proc = start_launcher({"TEST_TIMI_API_KEY": "hermetic"})
        assert _wait_for(proj, "t-cl", {"needs-clarification"}, proc=proc) == "needs-clarification"
        assert proc.poll() is None


# ── VC-012: max_workers=1 serializes ─────────────────────────────────────────

class TestMaxWorkersSerialization:
    def test_second_task_waits_for_first_terminal(
        self, proj: pathlib.Path, start_launcher,
    ) -> None:
        _make_task(proj, "s1", "work SLEEP1500 EXITCODE0")
        _make_task(proj, "s2", "work EXITCODE0")
        start_launcher({"TEST_TIMI_API_KEY": "hermetic"}, max_workers=1)

        s1_done_at = _wait_transition_at(proj, "s1", {"done"})
        s2_running_at = _wait_transition_at(proj, "s2", {"running", "done"})
        # 50ms polling tolerance; the invariant is ordering, not exact timing.
        assert s2_running_at >= s1_done_at - 0.1


# ── VC-013: concurrent writes lose no rows ────────────────────────────────────

class TestConcurrentWrites:
    def test_eight_concurrent_upserts_survive_launcher_rewrites(
        self, proj: pathlib.Path, start_launcher,
    ) -> None:
        _make_task(proj, "base", "work SLEEP800 EXITCODE0")
        proc = start_launcher({"TEST_TIMI_API_KEY": "hermetic"})

        def upsert(i: int) -> None:
            wfile = mw_common.workers_path(proj)
            lock = mw_common.lock_path(proj)
            mw_common.acquire_lock(lock)
            try:
                entries = mw_common.parse_workers_file(wfile)
                now = mw_common.iso_now()
                entries.append({
                    "task_key": f"c{i}", "status": "done", "cli": "pi", "provider": "timi",
                    "task_path": str(proj / ".agenticdoc" / f"c{i}" / "task.md"),
                    "dispatched_at": now, "updated_at": now, "model": "",
                })
                tmp = wfile.with_name(wfile.name + ".upsert.tmp")
                tmp.write_text(
                    "\n".join(mw_common.serialize_entry(e) for e in entries) + "\n",
                    encoding="utf-8",
                )
                tmp.replace(wfile)
            finally:
                mw_common.release_lock(lock)

        threads = [threading.Thread(target=upsert, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert _wait_for(proj, "base", {"done"}, proc=proc) == "done"
        keys = {e["task_key"] for e in mw_common.parse_workers_file(mw_common.workers_path(proj))}
        assert {f"c{i}" for i in range(8)} <= keys, f"lost rows; present={sorted(keys)}"
        assert "base" in keys


# ── VC-001/VC-002: missing-credential isolation end-to-end ───────────────────

class TestCredentialIsolation:
    def test_missing_credential_task_fails_others_dispatch(
        self, proj: pathlib.Path, start_launcher,
    ) -> None:
        # claude route needs TEST_ANTHROPIC_AUTH_TOKEN — deliberately unset.
        _make_task(proj, "iso-claude", "review something", cli="claude", provider="")
        _make_task(proj, "iso-pi", "work EXITCODE0", cli="pi", provider="timi")
        proc = start_launcher({"TEST_TIMI_API_KEY": "hermetic"})

        assert _wait_for(proj, "iso-claude", {"failed"}, proc=proc) == "failed"
        worker_log = proj / ".agenticdoc" / "iso-claude" / "worker.log"
        assert "TEST_ANTHROPIC_AUTH_TOKEN" in worker_log.read_text(encoding="utf-8")

        assert _wait_for(proj, "iso-pi", {"done"}, proc=proc) == "done"
        time.sleep(2)
        assert proc.poll() is None  # launcher survived the failed sibling
        launcher_log = (proj / "launcher-out.log").read_text(encoding="utf-8", errors="replace")
        assert "iso-claude" in launcher_log  # failure is visible in the log too


# ── VC-005: stale entry archived within 10s (AC-004) ──────────────────────────

class TestStaleArchiveIntegration:
    def test_stale_pending_archived_within_10s(
        self, proj: pathlib.Path, start_launcher,
    ) -> None:
        _add_raw_row(proj, "dead1", "pending", proj / ".agentic" / "dead1" / "task.md")
        _make_task(proj, "live1", "work EXITCODE0")
        proc = start_launcher({"TEST_TIMI_API_KEY": "hermetic"})

        deadline = time.monotonic() + 10
        archived = False
        while time.monotonic() < deadline:
            statuses = _read_status(proj)
            stale_rows = (
                mw_common.stale_path(proj).read_text(encoding="utf-8")
                if mw_common.stale_path(proj).exists() else ""
            )
            if "dead1" not in statuses and "dead1" in stale_rows:
                archived = True
                break
            time.sleep(0.2)
        assert archived, "stale entry was not archived within 10s"
        assert "task.md not found" in stale_rows
        assert mw_common.STALE_REASON in stale_rows
        # The live task is untouched by the archival sweep.
        assert _wait_for(proj, "live1", {"done"}, proc=proc) == "done"


# ── VC-004 (integration level): real mw serve with partial credentials ──────

class TestServeIntegration:
    def test_serve_precheck_logs_routes_and_dispatches(
        self, proj: pathlib.Path, fakebin: pathlib.Path,
    ) -> None:
        env = dict(os.environ)
        env["PATH"] = str(fakebin) + os.pathsep + env.get("PATH", "")
        env["FAKE_MARK_DIR"] = str(proj / "marks")
        for var in _TEST_CRED_VARS:
            env.pop(var, None)
        env["TEST_TIMI_API_KEY"] = "hermetic"

        cmd = [
            sys.executable, str(MW_PY), "serve",
            "--project", str(proj),
            "--pi-port=28001", "--claude-port=28003",
            "--providers", str(proj / "providers.json"),
            "--poll-interval", "1",
        ]
        proc = subprocess.Popen(
            cmd, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            creationflags=_CREATE_NO_WINDOW,
        )
        try:
            # PID file appears once precheck passed (timi available).
            pid_path = mw_common.pid_file(proj)
            deadline = time.monotonic() + 15
            while not pid_path.exists() and time.monotonic() < deadline:
                time.sleep(0.2)
            assert pid_path.exists(), "mw serve did not start (precheck failed?)"

            log = (proj / ".mw" / "mw.log").read_text(encoding="utf-8")
            route_lines = [l for l in log.splitlines() if l.startswith("[mw serve] route ")]
            assert len(route_lines) == len(INTEGRATION_CONFIG["providers"]) + 1  # + codex-native
            assert "route timi: available (env TEST_TIMI_API_KEY)" in log
            assert "route claude: missing" in log
            assert "route claude-cli: missing" in log

            # A task dispatched through the queue completes end-to-end.
            _make_task(proj, "serve-t1", "work EXITCODE0")
            assert _wait_for(proj, "serve-t1", {"done"}, proc=proc) == "done"
        finally:
            subprocess.run(
                [sys.executable, str(MW_PY), "stop", "--project", str(proj)],
                capture_output=True, timeout=30,
            )
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()


# ── VC-018: config-only route extension (AC-017) ─────────────────────────────

class TestConfigOnlyRouteExtension:
    def test_dummy_route_appears_in_precheck_and_doctor_without_code_changes(
        self, proj: pathlib.Path,
    ) -> None:
        config = json.loads(json.dumps(INTEGRATION_CONFIG))
        config["credentials"]["dummy"] = {"sources": [{"env": "TEST_DUMMY_KEY"}]}
        config["providers"]["dummy"] = {
            "port": 28099, "base_url_env": "TEST_DUMMY_BASE_URL",
            "api_key_env": "TEST_DUMMY_KEY", "credential": "dummy",
        }
        providers_file = proj / "providers.json"
        providers_file.write_text(json.dumps(config), encoding="utf-8")

        loaded = mw_common.load_providers(providers_file)
        precheck = mw_common.route_precheck(loaded, {"TEST_DUMMY_KEY": "x"})
        routes = {r["route"]: r for r in precheck["routes"]}
        assert routes["dummy"]["available"] is True

        env = dict(os.environ)
        env["TEST_DUMMY_KEY"] = "x"
        for var in _TEST_CRED_VARS[:-1]:
            env.pop(var, None)
        result = subprocess.run(
            [sys.executable, str(MW_PY), "doctor", f"--project={proj}",
             f"--providers={providers_file}", "--json"],
            capture_output=True, text=True, timeout=30, env=env,
        )
        assert result.returncode in (0, 1)
        report = json.loads(result.stdout)
        doctor_routes = {r["route"] for r in report["credentials"]["routes"]}
        assert "dummy" in doctor_routes

        # And the launcher-side env building resolves the new route too.
        route = mw_common.route_for(loaded, "pi", "dummy")
        assert route["port"] == 28099
        assert route["api_key_env"] == "TEST_DUMMY_KEY"
