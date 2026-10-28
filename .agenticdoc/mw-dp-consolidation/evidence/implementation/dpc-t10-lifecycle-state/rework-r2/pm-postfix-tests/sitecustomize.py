"""Per-child guard for the T10 R2 PM verification run (child-side, fail-closed).

Loaded automatically by every Python child because ``run_pm_tests.py`` puts this
directory on the child's ``PYTHONPATH``. On import it:

1. writes one verifiable sentinel line *before* installing anything else, so
   "the guard really ran in this process" is auditable per pid (a guard that
   cannot write its sentinel aborts the interpreter instead of running unguarded);
2. refuses DNS/TCP/UDP/HTTP egress by patching the real ``socket`` class (so
   ``ssl.SSLSocket`` and every other subclass inherit the refusal) and the
   resolver helpers;
3. refuses every child process/exec whose executable is not this interpreter -
   an unknown non-Python child would run outside this guard;
4. records the credential-shaped environment *names* it can see (the runner
   builds the environment from a whitelist, so this list must stay empty).

The sentinel file is named by ``DPC10_GUARD_FILE`` and the run by
``DPC10_GUARD_RUN``. No environment *value* is ever printed or written.
"""
from __future__ import annotations

import inspect
import json
import os
import socket
import subprocess
import sys
import time

_SENTINEL = os.environ.get("DPC10_GUARD_FILE")
_RUN = os.environ.get("DPC10_GUARD_RUN")

#: Provider/worker/project/credential-shaped environment names. This guard only
#: reports them; the runner is the component that guarantees none is inherited.
_CREDENTIAL_MARKERS = (
    "API_KEY",
    "APIKEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "AUTH",
    "COOKIE",
)
_CREDENTIAL_PREFIXES = (
    "PI_",
    "MW_",
    "TIMI_",
    "TYPESAFE_",
    "OPENAI_",
    "ANTHROPIC_",
    "DASHSCOPE_",
    "AWS_",
    "AZURE_",
    "GCP_",
)


class GuardRefusal(RuntimeError):
    """The guarded child refused egress or an unknown child process."""


def _sentinel(stage: str, **fields: object) -> None:
    if not _SENTINEL or not _RUN:
        # Fail closed: a child that cannot prove the guard ran must not run.
        raise GuardRefusal("guard sentinel is not configured; refusing to run unguarded")
    row: dict[str, object] = {
        "stage": stage,
        "run": _RUN,
        "pid": os.getpid(),
        "executable": sys.executable,
        "python": "%d.%d.%d" % sys.version_info[:3],
        "dont_write_bytecode": bool(sys.dont_write_bytecode),
        "ts_ns": time.time_ns(),
    }
    row.update(fields)
    line = (json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND | getattr(os, "O_BINARY", 0)
    handle = os.open(_SENTINEL, flags, 0o644)
    try:
        view = memoryview(line)
        while view:
            written = os.write(handle, view)
            if written <= 0:
                raise GuardRefusal("guard sentinel write returned 0 bytes")
            view = view[written:]
        os.fsync(handle)
    finally:
        os.close(handle)


def credential_env_names() -> list[str]:
    """Credential-shaped environment names visible to this process (values never read)."""
    names: list[str] = []
    for name in os.environ:
        upper = name.upper()
        if upper.startswith(_CREDENTIAL_PREFIXES) or any(
            marker in upper for marker in _CREDENTIAL_MARKERS
        ):
            names.append(name)
    return sorted(names)


def _refusal(kind: str, detail: str) -> GuardRefusal:
    _sentinel("network-denied", kind=kind, detail=detail)
    return GuardRefusal(f"network egress is refused by the T10 R2 guard: {kind} ({detail})")


def _install_network_guard() -> None:
    def deny_connect(self, address, *args, **kwargs):
        raise _refusal("connect", type(self).__name__)

    def deny_connect_ex(self, address, *args, **kwargs):
        raise _refusal("connect_ex", type(self).__name__)

    def deny_bind(self, address, *args, **kwargs):
        raise _refusal("bind", type(self).__name__)

    def deny_sendto(self, data, *args, **kwargs):
        raise _refusal("sendto", type(self).__name__)

    socket.socket.connect = deny_connect
    socket.socket.connect_ex = deny_connect_ex
    socket.socket.bind = deny_bind
    socket.socket.sendto = deny_sendto
    if hasattr(socket.socket, "sendmsg"):
        def deny_sendmsg(self, *args, **kwargs):
            raise _refusal("sendmsg", type(self).__name__)

        socket.socket.sendmsg = deny_sendmsg

    def deny_create_connection(address, *args, **kwargs):
        raise _refusal("create_connection", "socket.create_connection")

    def deny_getaddrinfo(host, *args, **kwargs):
        raise _refusal("dns", "socket.getaddrinfo")

    def deny_gethostbyname(host):
        raise _refusal("dns", "socket.gethostbyname")

    def deny_gethostbyname_ex(host):
        raise _refusal("dns", "socket.gethostbyname_ex")

    def deny_gethostbyaddr(host):
        raise _refusal("dns", "socket.gethostbyaddr")

    socket.create_connection = deny_create_connection
    socket.getaddrinfo = deny_getaddrinfo
    socket.gethostbyname = deny_gethostbyname
    socket.gethostbyname_ex = deny_gethostbyname_ex
    socket.gethostbyaddr = deny_gethostbyaddr


def _is_this_python_family(target: object) -> bool:
    if isinstance(target, bytes):
        try:
            target = os.fsdecode(target)
        except (TypeError, ValueError):
            return False
    if isinstance(target, os.PathLike):
        try:
            target = os.fspath(target)
        except TypeError:
            return False
    if not isinstance(target, str) or not target:
        return False
    name = os.path.basename(target).lower()
    return name.startswith("python") or name in ("py", "py.exe")


def _install_subprocess_guard() -> None:
    real_init = subprocess.Popen.__init__
    real_signature = inspect.signature(real_init)

    def guarded_init(self, args, *positional, **keyword):
        target = args[0] if isinstance(args, (list, tuple)) and args else args
        bound = real_signature.bind(self, args, *positional, **keyword)
        bound.apply_defaults()
        options = bound.arguments
        inherited_env = options.get("env")
        guarded_env = inherited_env if inherited_env is not None else os.environ
        safe_args = isinstance(args, (list, tuple)) and "-B" in args and not any(
            flag in args for flag in ("-S", "-I", "-E")
        )
        same_executable = isinstance(target, str) and os.path.normcase(os.path.realpath(target)) == os.path.normcase(os.path.realpath(sys.executable))
        inherited_guard = all(guarded_env.get(name) == os.environ.get(name) for name in (
            "PYTHONPATH", "DPC10_GUARD_FILE", "DPC10_GUARD_RUN", "PYTHONDONTWRITEBYTECODE"
        ))
        overridden = options.get("executable")
        safe_override = overridden is None or (isinstance(overridden, str) and os.path.normcase(os.path.realpath(overridden)) == os.path.normcase(os.path.realpath(sys.executable)))
        if not (same_executable and safe_override and safe_args and inherited_guard and not options.get("shell")):
            _sentinel("subprocess-denied", kind="popen")
            raise GuardRefusal(
                "an unknown non-Python child process is refused by the T10 R2 guard"
            )
        return real_init(self, args, *positional, **keyword)

    subprocess.Popen.__init__ = guarded_init

    def refuse(name: str):
        def _denied(*args, **kwargs):
            _sentinel("subprocess-denied", kind=name)
            raise GuardRefusal(
                f"{name} would leave this guarded interpreter; refused by the T10 R2 guard"
            )

        return _denied

    for name in (
        "system",
        "popen",
        "execv",
        "execve",
        "execvp",
        "execvpe",
        "execl",
        "execle",
        "execlp",
        "execlpe",
        "spawnv",
        "spawnve",
        "spawnvp",
        "spawnvpe",
        "spawnl",
        "spawnle",
        "spawnlp",
        "spawnlpe",
        "posix_spawn",
        "posix_spawnp",
        "startfile",
    ):
        if hasattr(os, name):
            setattr(os, name, refuse("os." + name))


try:
    _sentinel("import", note="guard entering; nothing installed yet")
    _CREDENTIAL_NAMES = credential_env_names()
    _install_network_guard()
    _install_subprocess_guard()
    GUARD_INSTALLED = True
    _sentinel(
        "guard-installed",
        credential_env_names=_CREDENTIAL_NAMES,
        network="dns/tcp/udp/http-denied",
        child_processes="same-interpreter-with-inherited-guard-only",
    )
except BaseException:
    # Python normally reports sitecustomize exceptions and continues startup.
    # A failed safety hook must terminate before any product can execute.
    os._exit(86)
