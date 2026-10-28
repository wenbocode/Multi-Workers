"""Guard self-control: the positive/negative proof has to come from a child.

Executed by ``run_pm_tests.py`` with the same whitelisted environment and the
same ``PYTHONPATH`` the pytest child gets. Because the guard is installed by
``sitecustomize`` inside *this* process, every refusal below is evidence about a
child interpreter, not about the parent's patching:

* negative - DNS lookup, TCP connect, UDP send and an unknown non-Python child
  are all refused, and the refusal names the T10 R2 guard (not a network error);
* positive - a Python child is allowed and inherits the guard (it writes its own
  sentinel line), and ordinary file IO still works;
* environment - no credential-shaped variable name is visible.

Nothing here imports or executes a product module.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys


def _expect_refusal(action) -> dict[str, object]:
    try:
        action()
    except BaseException as exc:  # noqa: BLE001 - any refusal is the expected result
        text = f"{type(exc).__name__}: {exc}"
        return {
            "refused": True,
            "error": type(exc).__name__,
            "guard_message": "T10 R2 guard" in text,
        }
    return {"refused": False, "error": None, "guard_message": False}


def _udp_send() -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(b"t10-guard-probe", ("127.0.0.1", 9))
    finally:
        sock.close()


def main() -> int:
    checks: dict[str, object] = {}
    result: dict[str, object] = {
        "pid": os.getpid(),
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

    checks["credential_env_names"] = sorted(
        name
        for name in os.environ
        if any(
            marker in name.upper()
            for marker in ("API_KEY", "APIKEY", "TOKEN", "SECRET", "PASSWORD", "CREDENTIAL")
        )
    )
    checks["dns"] = _expect_refusal(lambda: socket.getaddrinfo("example.invalid", 443))
    checks["tcp"] = _expect_refusal(
        lambda: socket.create_connection(("127.0.0.1", 9), timeout=0.1)
    )
    checks["udp"] = _expect_refusal(_udp_send)
    checks["non_python_child"] = _expect_refusal(
        lambda: subprocess.run(["cmd.exe", "/c", "echo", "t10-guard"], check=False)
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
        checks.get("dns", {}).get("refused") is True
        and checks.get("tcp", {}).get("refused") is True
        and checks.get("udp", {}).get("refused") is True
        and checks.get("non_python_child", {}).get("refused") is True
        and all(
            checks.get(name, {}).get("guard_message") is True
            for name in ("dns", "tcp", "udp", "non_python_child")
        )
        and checks.get("python_child_rc") == 0
        and checks.get("python_child_pid")
        and checks.get("file_io") is True
        and checks.get("credential_env_names") == []
    )
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
