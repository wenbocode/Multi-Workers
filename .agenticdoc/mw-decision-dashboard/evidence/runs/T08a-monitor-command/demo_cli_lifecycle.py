"""T08a evidence: full CLI lifecycle transcript (argv/cwd/UTC/exit/dependency hashes).

Starts real isolated monitors under a temp control root (no shared `mw serve`,
no user browser), drives the private starter + `mw decide monitor` / `status` /
`stop`, and never prints the control token or a boot code.
"""

import hashlib
import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from datetime import datetime, timezone

REPO = pathlib.Path(__file__).resolve().parents[5]
PKG = REPO / "packages" / "multi-workers"
MW_PY = PKG / "mw.py"
sys.path.insert(0, str(PKG))
import decision_monitor  # noqa: E402
import decision_wire  # noqa: E402
import mw_common  # noqa: E402

HOST = decision_monitor.HOST
RANGE = decision_monitor.PORT_RANGE


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def sha256(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def env_for(tmp: pathlib.Path) -> dict[str, str]:
    env = {
        key: value
        for key, value in os.environ.items()
        if key
        not in {
            "TIMI_API_KEY",
            "OPENAI_API_KEY",
            "ANTHROPIC_API_KEY",
            "DEEPSEEK_API_KEY",
            "MW_MONITOR_BROWSER",
            "MW_MONITOR_BROWSER_PROFILE",
        }
    }
    home = tmp / "home"
    local = tmp / "localappdata"
    for path in (home, local):
        path.mkdir(parents=True, exist_ok=True)
    env.update(
        {
            "HOME": str(home),
            "USERPROFILE": str(home),
            "LOCALAPPDATA": str(local),
            "APPDATA": str(home / "appdata"),
            "PYTHONIOENCODING": "utf-8",
        }
    )
    return env


def run_cli(root: pathlib.Path, env: dict[str, str], *args: str) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(MW_PY), "decide", "monitor", *args, "--project", str(root)]
    print(f"[{now()}] argv={argv}")
    print(f"[{now()}] cwd={root}")
    started = time.monotonic()
    res = subprocess.run(
        argv,
        cwd=str(root),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )
    print(
        f"[{now()}] exit={res.returncode} elapsed_s={time.monotonic() - started:.2f}"
    )
    print(f"stdout={res.stdout.strip()}")
    print(f"stderr={res.stderr.strip()}")
    return res


def wait_state(root: pathlib.Path, timeout: float = 30.0) -> dict:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        state, problem = decision_monitor.read_state(root)
        if problem is None and state is not None:
            return state
        time.sleep(0.05)
    raise SystemExit("state was not published")


def post(port: int, path: str, token: str) -> tuple[int, dict]:
    request = urllib.request.Request(
        f"http://{HOST}:{int(port)}{path}",
        data=b"{}",
        headers={decision_monitor.TOKEN_HEADER: token, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310 - loopback
        return response.status, json.loads(response.read().decode("utf-8"))


def listening_addresses(port: int) -> list[str]:
    out = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=30,
    ).stdout
    found = []
    for line in out.splitlines():
        parts = line.split()
        if (
            len(parts) >= 4
            and parts[0].upper() == "TCP"
            and parts[3].upper() == "LISTENING"
            and parts[1].upper().endswith(f":{port}")
        ):
            found.append(parts[1].rsplit(":", 1)[0])
    return sorted(set(found))


def main() -> int:
    print(f"[{now()}] python={sys.version.split()[0]} platform={sys.platform}")
    print(f"[{now()}] git_head={subprocess.run(['git', '-C', str(REPO), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()}")
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="t08a-"))
    root = tmp / "proj"
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    env = env_for(tmp)
    print(f"[{now()}] control_root={root}")
    print(f"[{now()}] project_id={decision_wire.project_id_for(root)}")

    # 1) Private starter, directly: real detached-ish monitor lifecycle.
    starter_argv = [
        sys.executable,
        str(MW_PY.resolve()),
        "_decide_monitor_starter",
        "--project",
        str(root),
    ]
    starter_cwd = root
    log_path = root / ".mw" / "decide-monitor.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[{now()}] starter_argv={starter_argv}")
    print(f"[{now()}] starter_cwd={starter_cwd}")
    with log_path.open("ab") as log_handle:
        proc = subprocess.Popen(
            starter_argv,
            cwd=str(starter_cwd),
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=log_handle,
            stderr=log_handle,
        )
    try:
        state = wait_state(root)
        print(f"[{now()}] starter_pid={proc.pid} state={json.dumps(state, sort_keys=True)}")
        assert state["pid"] == proc.pid
        assert RANGE[0] <= state["port"] <= RANGE[1]
        print(f"[{now()}] listening_addresses={listening_addresses(state['port'])}")
        token = decision_monitor.read_secret(root)
        health = decision_monitor.health(state["port"], token)
        print(f"[{now()}] health_identity_matches={decision_monitor.identity_matches(health, decision_monitor.identity_from_state(state))}")
        status, body = post(state["port"], "/api/shutdown", token)
        print(f"[{now()}] shutdown_http={status} body={json.dumps(body, sort_keys=True)}")
        print(f"[{now()}] starter_exit={proc.wait(timeout=30)}")
        print(f"[{now()}] state_after_shutdown={decision_monitor.read_state(root)}")
        print(f"[{now()}] secret_after_shutdown={decision_monitor.read_secret(root)}")
        print(f"[{now()}] log_text={log_path.read_text(encoding='utf-8', errors='replace')!r}")
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=10)

    # 2) User command: ensure + reuse + status + stop (no browser).
    before = {
        name: sha256(pkg)
        for name, pkg in {
            "mw.py": MW_PY,
            "test_decision_monitor_cli.py": PKG / "test_decision_monitor_cli.py",
            "decision_monitor.py": PKG / "decision_monitor.py",
            "decision_wire.py": PKG / "decision_wire.py",
            "decision_history.py": PKG / "decision_history.py",
            "decision_points.py": PKG / "decision_points.py",
            "decision_book.py": PKG / "decision_book.py",
            "mw_common.py": PKG / "mw_common.py",
            "decision_dashboard.html": PKG / "decision_dashboard.html",
            "decision_dashboard.js": PKG / "decision_dashboard.js",
            "decision_dashboard.css": PKG / "decision_dashboard.css",
        }.items()
    }
    for name, digest in before.items():
        print(f"[{now()}] dependency_sha256 {name}={digest}")

    first = run_cli(root, env, "--json", "--no-open")
    try:
        first_doc = json.loads(first.stdout)
        port = first_doc["instance"]["port"]
        print(f"[{now()}] listening_addresses_after_open={listening_addresses(port)}")
        secret = decision_monitor.read_secret(root)
        assert secret and secret not in first.stdout and secret not in first.stderr
        assert "#boot=" not in first.stdout
        assert re.search(r"[0-9a-f]{64}", first.stdout) is None
        print(f"[{now()}] secret_in_stdout={secret in first.stdout} boot_fragment_in_stdout={'#boot=' in first.stdout}")
        state_bytes = decision_monitor.state_path(root).read_bytes()
        secret_bytes = decision_monitor.secret_path(root).read_bytes()

        run_cli(root, env, "--json", "--no-open")
        print(f"[{now()}] state_unchanged_on_reuse={decision_monitor.state_path(root).read_bytes() == state_bytes}")
        print(f"[{now()}] secret_unchanged_on_reuse={decision_monitor.secret_path(root).read_bytes() == secret_bytes}")
        run_cli(root, env, "status", "--json")
        print(f"[{now()}] state_unchanged_on_status={decision_monitor.state_path(root).read_bytes() == state_bytes}")
        run_cli(root, env, "stop", "--json")
        print(f"[{now()}] state_after_stop={decision_monitor.read_state(root)}")
        print(f"[{now()}] secret_after_stop={decision_monitor.read_secret(root)}")
        print(f"[{now()}] port_probe_after_stop={decision_monitor.probe_recorded_port(port)}")

        # 3) A window attempt with no Chromium configured: explicit, never a false success.
        no_browser_env = dict(env)
        no_browser_env["MW_MONITOR_BROWSER"] = str(tmp / "missing-chromium")
        no_browser_env["MW_MONITOR_BROWSER_PROFILE"] = str(tmp / "profile")
        window = run_cli(root, no_browser_env, "--json")
        window_doc = json.loads(window.stdout)
        print(f"[{now()}] window={json.dumps(window_doc['window'], sort_keys=True)}")
        leaked_boot = re.search(r"#boot=(?!<redacted>)[0-9a-f]{8,}", window.stdout)
        print(f"[{now()}] boot_code_in_window_output={bool(leaked_boot)}")
        print(f"[{now()}] window_url_has_fragment={'#' in str(window_doc['window']['url'])}")
        assert leaked_boot is None
        assert "#" not in str(window_doc["window"]["url"])
        secret_now = decision_monitor.read_secret(root)
        print(f"[{now()}] secret_in_window_output={secret_now in window.stdout}")
    finally:
        # Best-effort cleanup of only this temp root's monitor.
        subprocess.run(
            [sys.executable, str(MW_PY), "decide", "monitor", "stop", "--json", "--project", str(root)],
            cwd=str(root),
            env=env,
            capture_output=True,
            timeout=60,
        )

    after = {name: sha256(pkg) for name, pkg in {
        "mw.py": MW_PY,
        "test_decision_monitor_cli.py": PKG / "test_decision_monitor_cli.py",
        "decision_monitor.py": PKG / "decision_monitor.py",
        "decision_wire.py": PKG / "decision_wire.py",
        "decision_history.py": PKG / "decision_history.py",
        "decision_points.py": PKG / "decision_points.py",
        "decision_book.py": PKG / "decision_book.py",
        "mw_common.py": PKG / "mw_common.py",
        "decision_dashboard.html": PKG / "decision_dashboard.html",
        "decision_dashboard.js": PKG / "decision_dashboard.js",
        "decision_dashboard.css": PKG / "decision_dashboard.css",
    }.items()}
    print(f"[{now()}] dependency_hashes_stable={before == after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
