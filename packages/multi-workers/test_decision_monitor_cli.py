"""test_decision_monitor_cli.py — T08a: `mw decide monitor` wiring (mw-decision-dashboard).

The dashboard's monitor service already exists (T10: ``decision_monitor.py``)
and the read-only window command is already forwarded (T12a). This suite covers
the missing last mile: the *Python* CLI face.

* ``mw decide monitor`` starts (or reuses) one project-local monitor, mints a
  fresh single-use boot code and asks Chromium for an ``--app=`` window;
* ``mw decide monitor status`` is a read-only health/identity view that never
  starts a service and fails non-zero when no instance is recorded;
* ``mw decide monitor stop`` is the authenticated shutdown of *this* instance
  only (no generic kill, no fallback start);
* the hidden ``_decide_monitor_starter`` entry is the detached child that runs
  ``decision_monitor.serve`` with an explicit argv/cwd, so the user's CLI can
  exit while the monitor keeps serving.

Everything runs in ``tmp_path`` with an isolated HOME/USERPROFILE/LOCALAPPDATA,
a stub browser executable (never the user's browser) and loopback-only traffic.
The tests use real subprocesses and a real bound listener; cleanup only ever
touches the process/state published below its own temporary control root.
"""

from __future__ import annotations

import contextlib
import json
import os
import pathlib
import re
import signal
import subprocess
import sys
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision_monitor  # noqa: E402
import decision_wire  # noqa: E402
import mw  # noqa: E402
import mw_common  # noqa: E402

MW_PY = pathlib.Path(__file__).parent / "mw.py"
HOST = decision_monitor.HOST
PORT_RANGE = decision_monitor.PORT_RANGE
#: Credential variables that must not be inherited by the monitor child.
CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
)


# ---------------------------------------------------------------------------
# Isolation helpers
# ---------------------------------------------------------------------------


def _root(tmp_path: pathlib.Path, name: str = "proj") -> pathlib.Path:
    """An isolated control root (the shape ``.agenticdoc`` below it)."""
    root = tmp_path / name
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    return root


def _env(tmp_path: pathlib.Path) -> dict[str, str]:
    """A hermetic environment: isolated HOME/caches, no provider credentials."""
    env = {key: value for key, value in os.environ.items() if key not in CRED_ENV_VARS}
    home = tmp_path / "home"
    local = tmp_path / "localappdata"
    tmp = tmp_path / "tmpenv"
    for path in (home, local, tmp):
        path.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "LOCALAPPDATA": str(local),
            "APPDATA": str(home / "appdata"),
            "TMP": str(tmp),
            "TEMP": str(tmp),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    for name in ("MW_MONITOR_BROWSER", "MW_MONITOR_BROWSER_PROFILE"):
        env.pop(name, None)
    return env


def _cli(
    project: pathlib.Path,
    *argv: str,
    env: dict[str, str],
    timeout: float = 90.0,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(MW_PY), "decide", "monitor", *argv, "--project", str(project)],
        cwd=str(project),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
    )


def _json(res: subprocess.CompletedProcess[str]) -> dict:
    text = res.stdout.strip()
    assert text, f"no JSON on stdout (exit {res.returncode}):\n{res.stderr}"
    doc = json.loads(text)
    assert isinstance(doc, dict)
    return doc


def _wait_until(predicate, timeout: float = 30.0, interval: float = 0.05):
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(interval)
    raise AssertionError(f"condition not met within {timeout}s (last={last!r})")


def _wait_state(root: pathlib.Path, timeout: float = 30.0) -> dict:
    def read():
        state, problem = decision_monitor.read_state(root)
        if problem is not None:
            raise AssertionError(f"published state is unusable: {problem}")
        return state

    return _wait_until(read, timeout)


def _wait_file_text(path: pathlib.Path, timeout: float = 30.0) -> str:
    def read():
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return None

    return _wait_until(lambda: read() or None, timeout)


def _norm(path: object) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(str(path))))


def _spawn_exit(script: str = "pass") -> int:
    """PID of a process that provably exited (``dead`` per the OS probe)."""
    proc = subprocess.Popen([sys.executable, "-c", script])
    proc.wait(timeout=60)
    pid = proc.pid
    if mw_common.process_alive_state(pid) != "dead":
        pytest.skip("could not obtain a provably dead PID on this platform")
    return pid


def _closed_loopback_port() -> int:
    """A loopback port nothing listens on (the OS can prove a refusal)."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _listen_addresses(port: int) -> list[str]:
    """The local addresses a port listens on (best effort, skipped if unknown)."""
    try:
        if sys.platform == "win32":
            out = subprocess.run(
                ["netstat", "-ano", "-p", "tcp"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            ).stdout
            addresses: list[str] = []
            for line in out.splitlines():
                parts = line.split()
                if (
                    len(parts) >= 4
                    and parts[0].upper() == "TCP"
                    and parts[1].upper().endswith(f":{port}")
                    and parts[3].upper() == "LISTENING"
                ):
                    addresses.append(parts[1].rsplit(":", 1)[0])
            return addresses
        out = subprocess.run(
            ["ss", "-ltn"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        ).stdout
        return [
            line.split()[3].rsplit(":", 1)[0]
            for line in out.splitlines()[1:]
            if len(line.split()) >= 4 and line.split()[3].endswith(f":{port}")
        ]
    except (OSError, subprocess.SubprocessError, IndexError):
        return []


def _browser_stub(tmp_path: pathlib.Path) -> pathlib.Path:
    """A stub 'Chromium' that records its argv; never a real browser."""
    if sys.platform == "win32":
        path = tmp_path / "chromium-stub.cmd"
        path.write_text(
            '@echo off\r\n>>"%MW_MONITOR_STUB_LOG%" echo %*\r\n',
            encoding="utf-8",
            newline="",
        )
    else:
        path = tmp_path / "chromium-stub.sh"
        path.write_text(
            '#!/bin/sh\nprintf \'%s\\n\' "$@" >> "$MW_MONITOR_STUB_LOG"\n',
            encoding="utf-8",
            newline="\n",
        )
        path.chmod(0o755)
    return path


def _force_cleanup(root: pathlib.Path, env: dict[str, str]) -> None:
    """Stop only the instance this test started under ``root`` (never shared ones)."""
    state, _problem = decision_monitor.read_state(root)
    if state is not None:
        with contextlib.suppress(OSError, subprocess.SubprocessError):
            subprocess.run(
                [
                    sys.executable,
                    str(MW_PY),
                    "decide",
                    "monitor",
                    "stop",
                    "--json",
                    "--project",
                    str(root),
                ],
                cwd=str(root),
                env=env,
                capture_output=True,
                timeout=45,
            )
        state, _problem = decision_monitor.read_state(root)
    if state is None:
        return
    pid = state.get("pid")
    if (
        isinstance(pid, int)
        and not isinstance(pid, bool)
        and state.get("project_id") == decision_wire.project_id_for(root)
        and mw_common.process_alive_state(pid) == "alive"
    ):
        with contextlib.suppress(OSError):
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.2)


@pytest.fixture
def monitor_env(tmp_path: pathlib.Path):
    env = _env(tmp_path)
    roots: list[pathlib.Path] = []

    def make(name: str = "proj") -> pathlib.Path:
        root = _root(tmp_path, name)
        roots.append(root)
        return root

    yield make, env
    for root in roots:
        _force_cleanup(root, env)


# ---------------------------------------------------------------------------
# RED shape: the CLI surface exists and the hidden entry stays hidden
# ---------------------------------------------------------------------------


def test_monitor_parser_accepts_open_status_and_stop() -> None:
    help_res = subprocess.run(
        [sys.executable, str(MW_PY), "decide", "monitor", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    assert help_res.returncode == 0, help_res.stderr
    for word in ("status", "stop", "--project", "--no-open", "--json"):
        assert word in help_res.stdout
    assert "_decide_monitor_starter" not in help_res.stdout


def test_private_starter_argv_and_cwd_are_explicit(monitor_env) -> None:
    make, _env_map = monitor_env
    root = make()
    expected_argv = [
        sys.executable,
        str(pathlib.Path(mw.__file__).resolve()),
        "_decide_monitor_starter",
        "--project",
        str(root),
    ]
    assert mw._monitor_starter_argv(root) == expected_argv
    assert pathlib.Path(mw._monitor_starter_cwd(root)) == pathlib.Path(root)


# ---------------------------------------------------------------------------
# The hidden child runs a real, isolated monitor (real subprocess lifecycle)
# ---------------------------------------------------------------------------


def test_private_starter_serves_one_isolated_monitor_and_shuts_down(monitor_env) -> None:
    make, env = monitor_env
    root = make()
    proc = subprocess.Popen(
        [
            sys.executable,
            str(MW_PY),
            "_decide_monitor_starter",
            "--project",
            str(root),
        ],
        cwd=str(root),
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    try:
        state = _wait_state(root)
        assert state["pid"] == proc.pid
        assert PORT_RANGE[0] <= state["port"] <= PORT_RANGE[1]
        assert state["project_id"] == decision_wire.project_id_for(root)
        token = decision_monitor.read_secret(root)
        assert token
        identity = decision_monitor.identity_from_state(state, control_root=root)
        data = _wait_until(lambda: decision_monitor.health(state["port"], token), 30)
        assert decision_monitor.identity_matches(data, identity)
        addresses = _listen_addresses(state["port"])
        if addresses:
            assert set(addresses) == {HOST}, addresses

        status, payload = _post_control(state["port"], "/api/shutdown", token)
        assert status == 200, payload
        assert proc.wait(timeout=30) == 0
        assert _wait_until(lambda: decision_monitor.read_state(root)[0] is None, 20) is True
        assert decision_monitor.read_secret(root) is None
        assert decision_monitor.probe_recorded_port(state["port"])["result"] == "refused"
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)


def _post_control(port: int, path: str, token: str) -> tuple[int, dict | None]:
    import urllib.request

    request = urllib.request.Request(
        f"http://{HOST}:{int(port)}{path}",
        data=b"{}",
        headers={decision_monitor.TOKEN_HEADER: token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - loopback
        raw = response.read()
        status = response.status
    try:
        return status, json.loads(raw.decode("utf-8"))
    except ValueError:
        return status, None


# ---------------------------------------------------------------------------
# User command: start/reuse/status/stop plus secret hygiene
# ---------------------------------------------------------------------------


def test_user_monitor_starts_reuses_reports_status_and_stops(monitor_env) -> None:
    make, env = monitor_env
    root = make()
    state_path = decision_monitor.state_path(root)
    secret_path = decision_monitor.secret_path(root)
    lock_path = decision_monitor.start_lock_path(root)

    first = _cli(root, "--json", "--no-open", env=env)
    assert first.returncode == 0, first.stdout + first.stderr
    doc = _json(first)
    assert doc["ok"] is True and doc["action"] == "open"
    instance = doc["instance"]
    assert instance["reused"] is False
    assert PORT_RANGE[0] <= instance["port"] <= PORT_RANGE[1]
    assert doc["window"] is None
    assert _norm(instance["starter"]["cwd"]) == _norm(root)
    assert _norm(instance["starter"]["argv"][1]) == _norm(MW_PY)
    assert instance["starter"]["argv"][2:] == ["_decide_monitor_starter", "--project", str(root)]
    token = decision_monitor.read_secret(root)
    assert token
    assert token not in first.stdout
    assert token not in first.stderr
    assert state_path.exists() and secret_path.exists()
    assert not lock_path.exists(), "the start lock must be released after startup"
    # The monitor is detached: it is still alive after the CLI exited.
    assert mw_common.process_alive_state(instance["pid"]) == "alive"

    state_before = state_path.read_bytes()
    secret_before = secret_path.read_bytes()
    second = _cli(root, "--json", "--no-open", env=env)
    assert second.returncode == 0, second.stdout + second.stderr
    again = _json(second)["instance"]
    assert again["reused"] is True
    assert again["instance_id"] == instance["instance_id"]
    assert again["port"] == instance["port"]
    assert again.get("starter") is None
    assert state_path.read_bytes() == state_before
    assert secret_path.read_bytes() == secret_before

    status = _cli(root, "status", "--json", env=env)
    assert status.returncode == 0, status.stdout + status.stderr
    status_doc = _json(status)
    assert status_doc["ok"] is True and status_doc["action"] == "status"
    assert status_doc["instance"]["instance_id"] == instance["instance_id"]
    assert status_doc["instance"]["healthy"] is True
    assert status_doc["instance"]["compatible"] is True
    assert token not in status.stdout
    assert state_path.read_bytes() == state_before

    stop = _cli(root, "stop", "--json", env=env)
    assert stop.returncode == 0, stop.stdout + stop.stderr
    stop_doc = _json(stop)
    assert stop_doc["ok"] is True and stop_doc["action"] == "stop"
    assert stop_doc["stop"]["stopped"] is True
    assert stop_doc["stop"]["port_probe"] == "refused"
    assert token not in stop.stdout
    assert _wait_until(lambda: decision_monitor.read_state(root)[0] is None, 20) is True
    assert decision_monitor.read_secret(root) is None
    assert _wait_until(
        lambda: mw_common.process_alive_state(instance["pid"]) == "dead", 20
    ) is True
    assert decision_monitor.probe_recorded_port(instance["port"])["result"] == "refused"
    log_text = (root / ".mw" / "decide-monitor.log").read_text(
        encoding="utf-8", errors="replace"
    )
    assert token not in log_text


# ---------------------------------------------------------------------------
# Window: stub browser, redacted boot code, honest visibility
# ---------------------------------------------------------------------------


def test_monitor_window_uses_stub_browser_and_redacts_the_boot_code(monitor_env, tmp_path) -> None:
    make, env = monitor_env
    root = make()
    stub = _browser_stub(tmp_path)
    stub_log = tmp_path / "browser-argv.log"
    profile = tmp_path / "browser-profile"
    env = dict(env)
    env["MW_MONITOR_BROWSER"] = str(stub)
    env["MW_MONITOR_BROWSER_PROFILE"] = str(profile)
    env["MW_MONITOR_STUB_LOG"] = str(stub_log)

    res = _cli(root, "--json", env=env)
    assert res.returncode == 0, res.stdout + res.stderr
    doc = _json(res)
    window = doc["window"]
    assert window is not None
    assert window["spawned"] is True
    assert window["visibility"] == "not-verified"
    assert window["mode"] == "app"
    assert window["argv"][0] == str(stub)
    assert f"--user-data-dir={profile}" in window["argv"]
    port = doc["instance"]["port"]
    assert any(
        str(item) == f"--app=http://{HOST}:{port}/#boot=<redacted>" for item in window["argv"]
    ), window["argv"]

    recorded = _wait_file_text(stub_log)
    match = re.search(r"#boot=([0-9a-f]+)", recorded)
    assert match, recorded
    boot_code = match.group(1)
    assert boot_code in recorded
    assert boot_code not in res.stdout
    assert boot_code not in res.stderr
    assert boot_code not in json.dumps(doc)
    # The printed URL never carries the fragment.
    assert f"http://{HOST}:{port}/" in res.stdout
    assert "#boot=" not in window["url"]

    # A second open reuses the instance but mints a different single-use code.
    second = _cli(root, "--json", env=env)
    assert second.returncode == 0, second.stdout + second.stderr
    second_doc = _json(second)
    assert second_doc["instance"]["port"] == port
    _wait_until(lambda: len(re.findall(r"#boot=([0-9a-f]+)", _wait_file_text(stub_log))) >= 2, 20)
    codes = re.findall(r"#boot=([0-9a-f]+)", _wait_file_text(stub_log))
    assert len(codes) >= 2 and codes[0] != codes[1]
    for code in codes:
        assert code not in second.stdout
        assert code not in second.stderr
        assert code not in (root / ".mw" / "decide-monitor.log").read_text(
            encoding="utf-8", errors="replace"
        )
    assert second_doc["window"]["spawned"] is True


# ---------------------------------------------------------------------------
# Human output and an explicit window failure (no false success)
# ---------------------------------------------------------------------------


def test_human_output_names_the_instance_without_a_boot_code(monitor_env) -> None:
    make, env = monitor_env
    root = make()
    opened = _cli(root, "--no-open", env=env)
    assert opened.returncode == 0, opened.stdout + opened.stderr
    assert f"[mw decide monitor] instance http://{HOST}:" in opened.stdout
    assert "stop it with 'mw decide monitor stop'" in opened.stdout
    assert "#boot=" not in opened.stdout

    status = _cli(root, "status", env=env)
    assert status.returncode == 0, status.stdout + status.stderr
    assert "[mw decide monitor] healthy" in status.stdout

    stop = _cli(root, "stop", env=env)
    assert stop.returncode == 0, stop.stdout + stop.stderr
    assert "[mw decide monitor] stopped" in stop.stdout
    assert _wait_until(lambda: decision_monitor.read_state(root)[0] is None, 20) is True


def test_window_failure_is_explicit_and_keeps_the_service(monitor_env, tmp_path) -> None:
    make, env = monitor_env
    root = make()
    env = dict(env)
    env["MW_MONITOR_BROWSER"] = str(tmp_path / "missing-chromium")
    env["MW_MONITOR_BROWSER_PROFILE"] = str(tmp_path / "profile")

    res = _cli(root, "--json", env=env)
    assert res.returncode == 0, res.stdout + res.stderr
    doc = _json(res)
    window = doc["window"]
    assert window["spawned"] is False
    assert window["visibility"] == "not-opened"
    assert window["mode"] is None
    assert window["reason"]
    assert window["guide"]

    status = _cli(root, "status", "--json", env=env)
    assert status.returncode == 0
    assert _json(status)["instance"]["healthy"] is True


# ---------------------------------------------------------------------------
# status/stop never start a service; unknown roots fail closed
# ---------------------------------------------------------------------------


def test_status_and_stop_never_start_a_service(monitor_env) -> None:
    make, env = monitor_env
    root = make()
    state_path = decision_monitor.state_path(root)
    secret_path = decision_monitor.secret_path(root)
    lock_path = decision_monitor.start_lock_path(root)

    for argv in (("status",), ("stop",)):
        res = _cli(root, *argv, "--json", env=env)
        assert res.returncode != 0, res.stdout
        doc = _json(res)
        assert doc["ok"] is False
        assert doc["error"]["kind"] == "no-instance"
        assert doc["error"]["guide"]
        assert not state_path.exists()
        assert not secret_path.exists()
        assert not lock_path.exists()
        assert not (root / ".mw" / "decide-monitor.log").exists()

    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text("{not a state document", encoding="utf-8")
    malformed = state_path.read_bytes()
    for argv in (("status",), ("stop",)):
        res = _cli(root, *argv, "--json", env=env)
        assert res.returncode != 0, res.stdout
        doc = _json(res)
        assert doc["ok"] is False
        assert doc["error"]["kind"] == "instance-unknown"
        assert state_path.read_bytes() == malformed
        assert not secret_path.exists()
        assert not list((root / ".mw").glob("*.stale-*"))
        assert not lock_path.exists()


def test_status_and_stop_do_not_recover_a_stale_instance(monitor_env) -> None:
    make, env = monitor_env
    root = make()
    identity = decision_monitor.InstanceIdentity(
        project_id=decision_wire.project_id_for(root),
        instance_id="stale-monitor-001",
        pid=_spawn_exit(),
        pid_start_ms=1,
        port=_closed_loopback_port(),
        code_fingerprint=decision_monitor.code_fingerprint(),
    )
    decision_monitor.publish_secret(root, "stale-control-token-value")
    decision_monitor.publish_state(root, identity)
    state_before = decision_monitor.state_path(root).read_bytes()
    secret_before = decision_monitor.secret_path(root).read_bytes()

    status = _cli(root, "status", "--json", env=env)
    assert status.returncode != 0
    assert _json(status)["error"]["kind"] == "instance-unresponsive"
    assert decision_monitor.state_path(root).read_bytes() == state_before
    assert decision_monitor.secret_path(root).read_bytes() == secret_before
    assert not list((root / ".mw").glob("*.stale-*"))

    stop = _cli(root, "stop", "--json", env=env)
    assert stop.returncode == 0, stop.stdout + stop.stderr
    stop_doc = _json(stop)
    assert stop_doc["stop"]["stopped"] is True
    assert stop_doc["stop"]["state"] == "retained"
    assert stop_doc["guide"], "a retained state needs a manual recovery guide"
    assert decision_monitor.state_path(root).read_bytes() == state_before
    assert decision_monitor.secret_path(root).read_bytes() == secret_before
    assert not list((root / ".mw").glob("*.stale-*"))
    assert not decision_monitor.start_lock_path(root).exists()


def test_foreign_project_state_is_refused_without_touching_it(monitor_env) -> None:
    make, env = monitor_env
    root = make()
    identity = decision_monitor.InstanceIdentity(
        project_id="f" * 16,
        instance_id="foreign-monitor-01",
        pid=os.getpid(),
        pid_start_ms=mw_common.process_start_ms(os.getpid()),
        port=decision_monitor.PORT_RANGE[0],
        code_fingerprint=decision_monitor.code_fingerprint(),
    )
    decision_monitor.publish_secret(root, "foreign-control-token-value")
    decision_monitor.publish_state(root, identity)
    state_before = decision_monitor.state_path(root).read_bytes()
    secret_before = decision_monitor.secret_path(root).read_bytes()
    for action in ("status", "stop"):
        res = _cli(root, action, "--json", env=env)
        assert res.returncode == 1, res.stdout + res.stderr
        doc = _json(res)
        assert doc["error"]["kind"] == "incompatible-instance"
        assert doc["error"]["guide"]
        assert decision_monitor.state_path(root).read_bytes() == state_before
        assert decision_monitor.secret_path(root).read_bytes() == secret_before
        assert not list((root / ".mw").glob("*.stale-*"))
        assert not decision_monitor.start_lock_path(root).exists()


def test_unknown_control_root_fails_closed(monitor_env, tmp_path) -> None:
    _make, env = monitor_env
    plain = tmp_path / "plain"
    plain.mkdir()
    for argv in ((), ("status",), ("stop",)):
        res = _cli(plain, *argv, "--json", env=env)
        assert res.returncode == 2, res.stdout + res.stderr
        doc = _json(res)
        assert doc["ok"] is False
        assert doc["error"]["kind"] in {"not-control", "ambiguous-root"}
        assert doc["error"]["guide"]
        assert not (plain / ".mw").exists()


# ---------------------------------------------------------------------------
# Narrow regression: the existing decide faces still parse
# ---------------------------------------------------------------------------


def test_existing_decide_run_and_sign_help_still_parse() -> None:
    for sub in ("run", "sign"):
        res = subprocess.run(
            [sys.executable, str(MW_PY), "decide", sub, "--help"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        assert res.returncode == 0, res.stderr
    assert "monitor" in subprocess.run(
        [sys.executable, str(MW_PY), "decide", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    ).stdout
