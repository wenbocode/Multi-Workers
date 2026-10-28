"""Guard self-control for the T10 R2 stage-C run: the proof comes from a child.

Executed by ``run_pm_tests.py`` with the same whitelisted environment and the
same ``PYTHONPATH`` the pytest children get. Because the guard is installed by
``sitecustomize`` inside *this* process, every refusal below is evidence about a
child interpreter, not about the parent's patching:

* negative - DNS lookup, TCP connect, UDP send, an HTTP request, an unknown
  non-Python child, a child that would lose ``-B``/the guard environment
  (``-S``, ``-I``, ``-E``, popped ``PYTHONPATH``) and ``shell=True`` are all
  refused, and each refusal names the T10 R2 guard (not a network error);
* positive - a Python child is allowed and inherits the guard (it writes its own
  sentinel row under this run and child label), and ordinary file IO still works;
* environment - no credential-shaped variable name is visible.

Nothing here imports or executes a product module.
"""
from __future__ import annotations

import http.client
import json
import os
import socket
import subprocess
import sys

#: Checks the runner requires to be a refusal carrying the guard's own message.
NEGATIVE_CHECKS = (
    "dns",
    "tcp",
    "udp",
    "http",
    "non_python_child",
    "missing_B",
    "no_site",
    "no_isolated_mode",
    "no_environment",
    "lost_guard_env",
    "shell_child",
)


def _expect_refusal(action) -> dict[str, object]:
    try:
        action()
    except BaseException as exc:  # noqa: BLE001 - any refusal is the expected result
        text = f"{type(exc).__name__}: {exc}"
        return {
            "refused": True,
            "error": type(exc).__name__,
            "guard_message": "T10 R2 guard" in text or "T10 R2 guard" in repr(exc),
        }
    return {"refused": False, "error": None, "guard_message": False}


def _udp_send() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(b"t10-guard-probe", ("127.0.0.1", 9))
    finally:
        sock.close()


def _http_request() -> None:
    connection = http.client.HTTPConnection("127.0.0.1", 9, timeout=0.1)
    try:
        connection.request("GET", "/")
    finally:
        connection.close()


def main() -> int:
    checks: dict[str, object] = {}
    result: dict[str, object] = {
        "pid": os.getpid(),
        "ppid": os.getppid(),
        "child_label": os.environ.get("DPC10_GUARD_CHILD"),
        "run_label": os.environ.get("DPC10_GUARD_RUN"),
        "executable": sys.executable,
        "python": sys.version,
        "dont_write_bytecode": bool(sys.dont_write_bytecode),
        "cwd": os.getcwd(),
        "temp": os.environ.get("TEMP"),
        "home": os.environ.get("HOME"),
        "checks": checks,
    }

    guard_module = None
    try:
        import sitecustomize as guard_module  # noqa: PLC0415 - the child's own site hook
    except Exception as exc:  # noqa: BLE001 - a missing guard is the failure mode
        checks["guard_import_error"] = type(exc).__name__
    checks["guard_installed"] = bool(
        guard_module is not None and getattr(guard_module, "GUARD_INSTALLED", False)
    )
    if not checks["guard_installed"]:
        # Without the guard, do NOT attempt any real egress.
        print(json.dumps(result, ensure_ascii=False))
        return 1

    checks["credential_env_names"] = guard_module.credential_env_names()
    checks["dns"] = _expect_refusal(lambda: socket.getaddrinfo("example.invalid", 443))
    checks["tcp"] = _expect_refusal(
        lambda: socket.create_connection(("127.0.0.1", 9), timeout=0.1)
    )
    checks["udp"] = _expect_refusal(_udp_send)
    checks["http"] = _expect_refusal(_http_request)
    checks["non_python_child"] = _expect_refusal(
        lambda: subprocess.run(["cmd.exe", "/c", "echo", "t10-guard"], check=False)
    )

    for name, argv, keyword in (
        ("missing_B", [sys.executable, "-c", "print('must-not-run')"], {}),
        ("no_site", [sys.executable, "-B", "-S", "-c", "print('must-not-run')"], {}),
        ("no_isolated_mode", [sys.executable, "-B", "-I", "-c", "print('must-not-run')"], {}),
        ("no_environment", [sys.executable, "-B", "-E", "-c", "print('must-not-run')"], {}),
        (
            "shell_child",
            [sys.executable, "-B", "-c", "print('must-not-run')"],
            {"shell": True},
        ),
    ):
        checks[name] = _expect_refusal(
            lambda argv=argv, keyword=keyword: subprocess.run(argv, check=False, **keyword)
        )
    altered_env = dict(os.environ)
    altered_env.pop("PYTHONPATH", None)
    checks["lost_guard_env"] = _expect_refusal(
        lambda: subprocess.run(
            [sys.executable, "-B", "-c", "print('must-not-run')"],
            env=altered_env,
            check=False,
        )
    )

    child = subprocess.run(
        [sys.executable, "-B", "-c", "import os; print('child-ok', os.getpid())"],
        capture_output=True,
        text=True,
        check=False,
    )
    checks["python_child_rc"] = child.returncode
    checks["python_child_stdout"] = child.stdout.strip()
    parts = child.stdout.strip().split()
    checks["python_child_pid"] = int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else None

    scratch = os.path.join(os.environ.get("TEMP", os.getcwd()), "guard-preflight-scratch.txt")
    try:
        with open(scratch, "w", encoding="utf-8", newline="\n") as handle:
            handle.write("guard file io is not blocked\n")
        with open(scratch, encoding="utf-8") as handle:
            checks["file_io"] = handle.read().strip() == "guard file io is not blocked"
    except OSError as exc:
        checks["file_io"] = f"failed: {type(exc).__name__}"

    print(json.dumps(result, ensure_ascii=False))
    ok = (
        all(
            isinstance(checks.get(name), dict)
            and checks[name].get("refused") is True
            and checks[name].get("guard_message") is True
            for name in NEGATIVE_CHECKS
        )
        and checks.get("python_child_rc") == 0
        and bool(checks.get("python_child_pid"))
        and checks.get("file_io") is True
        and checks.get("credential_env_names") == []
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
