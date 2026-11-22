"""T15-M3G: genuine native-review terminal observation (current-run private IPC).

Why this module exists
----------------------
A review verdict written into the worker's own tree (``review-verdict.json``,
``report.md``) is an EDITABLE FILE. Reading it for the first time after the run
exited proves only that some bytes exist now -- a model, a tool, or a shell
grandchild can write those same bytes before the host ever looks. Hash, path,
PID in a JSON row and a typed verdict are equally reconstructible, so none of
them can authenticate an independent review.

This module implements the missing producer fact:

1. the PARENT that actually spawns the worker creates a private, OS-level
   channel *before* the spawn and hands one end to that child only
   (Windows: a named-pipe server instance; POSIX: a ``socketpair`` fd);
2. the worker's own TERMINAL code path (not a tool, not the model) writes one
   framed payload through that channel: run identity, dispatch binding, typed
   verdict and the verbatim terminal ``report.md`` bytes;
3. the parent accepts it only while the connection's OS-reported CLIENT PID is
   the child PID it spawned, and only once, and only before that child's own
   exit is observed by the parent's real ``Popen.poll()``;
4. the accepted delivery is kept in CURRENT-LIFETIME MEMORY only and every
   later consumption re-checks the current claim/task/run/parent/material/basis/
   goal/execution/time/budget/stop facts plus the on-disk report bytes.

Consequences that this module makes explicit rather than presumed:

* a payload written by a *grandchild* (e.g. the model's shell tool) is refused
  because ``GetNamedPipeClientProcessId`` / ``SO_PEERCRED`` is not the child;
* a pre-written file, a pre-spawn substitution or a post-exit rewrite is not a
  delivery at all: nothing is accepted outside the live connection, and the
  terminal report bytes must still match when consumed;
* a duplicate or conflicting second delivery poisons the run (the first one is
  not silently kept);
* a restarted parent has no registry entry, so old authority is not restored;
  no signed effect token, no lifecycle query, no durable trust store.

The endpoint value handed to the child (pipe name / fd number) is NOT the
authorization secret: authorization is the parent's peer-identity check, so
knowing the value from the child environment buys a forger nothing.
"""

from __future__ import annotations

import base64
import binascii
import ctypes
import hashlib
import json
from multiprocessing.connection import Listener
import os
from pathlib import Path
import re
import socket
import struct
import sys
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Mapping

PROTOCOL = "mw-native-observation-v1"
KIND = "native-review-terminal"
SCHEMA_VERSION = 1
ENV_SPEC = "MW_NATIVE_OBSERVATION"
ENV_DISPATCH = "MW_NATIVE_REVIEW_DISPATCH"
MAX_PAYLOAD_BYTES = 1 << 20
DEFAULT_ACCEPT_TIMEOUT_S = 30.0
# How long close() waits for the reader thread to prove it has left its I/O call.
# The wait is a WITNESS, not the mechanism: cancellation (`CancelIoEx`) is.
READER_TERMINATION_TIMEOUT_S = 10.0
# A cancellable wait is served in slices so a close request is noticed promptly
# even while an overlapped operation is still pending.
WINDOWS_WAIT_SLICE_MS = 50
# Clock slack: the child stamps `delivered_at` from its own clock, the parent
# stamps the observed exit from its own. The two are the same machine, so a
# small allowance is enough; a larger gap is a real ordering violation.
CLOCK_SLACK_MS = 5_000

SHA_RE = r"^[0-9a-f]{64}$"


class ObservationRefused(Exception):
    """A delivery or a consumption that must stay insufficient.

    ``gaps`` are stable machine labels (they end up in product evidence);
    ``reason`` is the human sentence. Neither is ever a PASS.
    """

    def __init__(self, gaps: Iterable[str], reason: str) -> None:
        self.gaps = tuple(dict.fromkeys(str(gap) for gap in gaps))
        self.reason = reason
        super().__init__(reason)


# ── small strict helpers ───────────────────────────────────────────────────


def _is_sha(value: object) -> bool:
    return isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value)


def _iso_ms(value: object) -> int | None:
    """Finite ISO-8601 instant in ms, or ``None`` (never NaN/Infinity/blank)."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if not (text.endswith("Z") or len(text) >= 25 and text[-6] in "+-" and text[-3] == ":"):
        return None
    try:
        return int(round(_parse_iso(text) * 1000))
    except (TypeError, ValueError, OverflowError):
        return None


def _parse_iso(text: str) -> float:
    from datetime import datetime

    normalised = text[:-1] + "+00:00" if text.endswith("Z") else text
    return datetime.fromisoformat(normalised).timestamp()


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _require(mapping: Mapping[str, Any], key: str, gap: str) -> Any:
    value = mapping.get(key)
    if value is None or (isinstance(value, (str, list, dict)) and len(value) == 0):
        raise ObservationRefused([gap], f"native observation is missing {key}")
    return value


# ── framing ────────────────────────────────────────────────────────────────

_HEADER = struct.Struct(">I")


def frame_payload(data: bytes) -> bytes:
    """One delivery = one length-prefixed frame. Bounded before it is written."""
    if not data:
        raise ObservationRefused(["payload-empty"], "native payload is empty")
    if len(data) > MAX_PAYLOAD_BYTES:
        raise ObservationRefused(
            ["payload-too-large"], f"native payload is {len(data)} bytes, above the {MAX_PAYLOAD_BYTES} bound"
        )
    return _HEADER.pack(len(data)) + data


def _read_exact(sock: socket.socket, count: int) -> bytes:
    chunks: list[bytes] = []
    read = 0
    while read < count:
        chunk = sock.recv(count - read)
        if not chunk:
            raise ObservationRefused(["channel-disconnected"], "the private channel closed mid-frame")
        chunks.append(chunk)
        read += len(chunk)
    return b"".join(chunks)


def recv_frame(sock: socket.socket) -> bytes:
    raw = _read_exact(sock, _HEADER.size)
    (length,) = _HEADER.unpack(raw)
    if length == 0:
        raise ObservationRefused(["payload-empty"], "native payload frame declares zero bytes")
    if length > MAX_PAYLOAD_BYTES:
        raise ObservationRefused(
            ["payload-too-large"], f"native payload frame declares {length} bytes, above the {MAX_PAYLOAD_BYTES} bound"
        )
    return _read_exact(sock, length)


# ── payload schema ─────────────────────────────────────────────────────────


def parse_native_review_payload(raw: bytes) -> dict[str, Any]:
    """Strict parse of the terminal payload. Shape alone never authenticates:
    the caller must still bind it to the real child PID and exit."""
    if len(raw) > MAX_PAYLOAD_BYTES:
        raise ObservationRefused(["payload-too-large"], "native payload exceeds the size bound")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ObservationRefused(["payload-malformed"], "native payload is not UTF-8 JSON") from None
    if not isinstance(payload, dict):
        raise ObservationRefused(["payload-malformed"], "native payload is not a JSON object")
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ObservationRefused(["payload-schema"], "native payload schema_version is not current")
    if payload.get("kind") != KIND:
        raise ObservationRefused(["payload-kind"], "native payload is not a native-review terminal delivery")
    if payload.get("protocol") != PROTOCOL:
        raise ObservationRefused(["payload-protocol"], "native payload protocol does not match this build")
    if _iso_ms(payload.get("delivered_at")) is None:
        raise ObservationRefused(["payload-delivered-at"], "native payload has no finite delivered_at")

    run = _require(payload, "run", "payload-run")
    dispatch = _require(payload, "dispatch", "payload-dispatch")
    review = _require(payload, "review", "payload-review")
    report = _require(payload, "report", "payload-report")
    if not isinstance(run, dict) or not isinstance(dispatch, dict) or not isinstance(review, dict):
        raise ObservationRefused(["payload-schema"], "native payload run/dispatch/review are not objects")
    if not isinstance(report, dict):
        raise ObservationRefused(["payload-report"], "native payload report is not an object")

    for container, keys, gap in (
        (run, ("owner_key", "task_key", "run_id", "kind", "status", "started_at"), "payload-run"),
        (
            dispatch,
            (
                "claim_id",
                "parent_run_id",
                "card_path",
                "card_sha256",
                "envelope_sha256",
                "implementer_task_key",
                "implementer_run_id",
                "local_ref",
                "execution_ref",
                "tool_call_ref",
                "material_digest",
                "basis_digest",
                "goal_digest",
            ),
            "payload-dispatch",
        ),
        (review, ("verifier_ref", "verdict", "reviewed_at", "role"), "payload-review"),
    ):
        for key in keys:
            if not _nonblank(container.get(key)):
                raise ObservationRefused([gap], f"native payload {gap} is missing/blank {key}")

    if not _iso_ms(run.get("started_at")):
        raise ObservationRefused(["payload-run"], "native payload run.started_at is not a finite instant")
    if run.get("kind") != "review":
        raise ObservationRefused(["payload-role"], "native payload is not a REVIEW run terminal delivery")
    if review.get("role") != "review":
        raise ObservationRefused(["payload-role"], "native payload review role is not review")
    if run.get("owner_key") is not None and not _nonblank(run.get("owner_key")):
        raise ObservationRefused(["payload-run"], "native payload owner_key is invalid")
    for key in ("card_sha256", "envelope_sha256"):
        if not _is_sha(dispatch.get(key)):
            raise ObservationRefused(["payload-dispatch"], f"native payload dispatch.{key} is not a sha256")
    for key in ("material_digest", "basis_digest", "goal_digest"):
        if not _is_sha(dispatch.get(key)):
            raise ObservationRefused(["payload-dispatch"], f"native payload dispatch.{key} is not a sha256")
    if dispatch.get("implementer_task_key") == run.get("task_key"):
        raise ObservationRefused(["payload-self-review"], "the native review run reviewed itself")
    if dispatch.get("implementer_run_id") == run.get("run_id"):
        raise ObservationRefused(["payload-self-review"], "the native review run shares the implementer run id")

    if review.get("verdict") not in ("pass", "fix", "partial", "empty"):
        raise ObservationRefused(["payload-verdict"], "native payload verdict is not a supported business verdict")
    if _iso_ms(review.get("reviewed_at")) is None:
        raise ObservationRefused(["payload-review-time"], "native payload reviewed_at is not a finite instant")
    for key in ("findings", "unresolved_findings", "refs"):
        value = review.get(key)
        if not isinstance(value, list) or any(not _nonblank(item) for item in value):
            raise ObservationRefused(["payload-review"], f"native payload review.{key} is not a string list")

    report_path = report.get("path")
    if report_path != "report.md":
        raise ObservationRefused(["payload-report"], "the official terminal artifact is report.md")
    if not _is_sha(report.get("sha256")):
        raise ObservationRefused(["payload-report"], "native payload report.sha256 is not a sha256")
    encoded = report.get("b64")
    if not isinstance(encoded, str) or not encoded:
        raise ObservationRefused(["payload-report"], "native payload carries no terminal report bytes")
    try:
        report_bytes = base64.b64decode(encoded.encode("ascii"), validate=True)
    except (binascii.Error, ValueError):
        raise ObservationRefused(["payload-report"], "native payload report bytes are not base64") from None
    if _sha256(report_bytes) != report.get("sha256"):
        raise ObservationRefused(["payload-report-digest"], "native payload report digest does not match its bytes")
    if len(report_bytes) == 0:
        raise ObservationRefused(["payload-report"], "native terminal report is empty")
    payload["_report_bytes"] = report_bytes
    return payload


# ── endpoint (parent side) ─────────────────────────────────────────────────


@dataclass(frozen=True)
class EndpointSpec:
    kind: str  # "windows-named-pipe" | "posix-socketpair"
    value: str

    def child_env(self) -> dict[str, str]:
        return {ENV_SPEC: f"{self.kind}:{self.value}"}


def spec_from_env(env: Mapping[str, str] | None = None) -> EndpointSpec | None:
    source = os.environ if env is None else env
    raw = source.get(ENV_SPEC)
    if not raw or ":" not in raw:
        return None
    kind, _, value = raw.partition(":")
    if kind not in ("windows-named-pipe", "posix-socketpair") or not value:
        return None
    return EndpointSpec(kind, value)


@dataclass
class RefusedDelivery:
    sender_pid: int | None
    gaps: tuple[str, ...]
    reason: str
    payload_digest: str | None = None


class HostObservationChannel:
    """The parent's end. Created BEFORE the spawn, bound to the child PID after.

    ``poll()`` never blocks and never raises for a bad delivery: a refusal is
    recorded (``refusals``) and the reader keeps waiting for the real child.
    """

    def __init__(self, spec: EndpointSpec, platform: str | None = None) -> None:
        self.spec = spec
        self.platform = platform or ("windows" if sys.platform == "win32" else "posix")
        self.refusals: list[RefusedDelivery] = []
        self._closed = threading.Event()
        self._frames: list[bytes] = []
        self._sender_pid: int | None = None
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None
        self._reader_done = threading.Event()
        self._delivery_ready = threading.Event()
        self._reader_terminated = False
        self._error: ObservationRefused | None = None
        self._child_pid: int | None = None
        self._server: _WindowsPipeServer | None = None
        self._sock: socket.socket | None = None

    # -- lifecycle --------------------------------------------------------
    @classmethod
    def create(cls, platform: str | None = None) -> HostObservationChannel:
        resolved = platform or ("windows" if sys.platform == "win32" else "posix")
        if resolved == "windows":
            server = _WindowsPipeServer()
            return cls(EndpointSpec("windows-named-pipe", server.name), resolved)._attach_windows(server)
        parent, child = socket.socketpair()
        channel = cls(EndpointSpec("posix-socketpair", str(child.fileno())), resolved)
        channel._sock = parent
        channel._child_socket = child  # type: ignore[attr-defined]
        return channel

    def _attach_windows(self, server: _WindowsPipeServer) -> HostObservationChannel:
        self._server = server
        return self

    @property
    def child_env(self) -> dict[str, str]:
        return self.spec.child_env()

    def start(self, child_pid: int) -> None:
        self._child_pid = int(child_pid)
        if self._sock is not None:
            # The child end was inherited by the spawn; the parent must not keep it.
            child = getattr(self, "_child_socket", None)
            if child is not None:
                try:
                    child.close()
                except OSError:
                    pass
        self._thread = threading.Thread(target=self._read_loop, name="mw-native-observation", daemon=True)
        self._thread.start()

    def poll(self) -> bytes | None:
        """The first accepted frame for THIS child, or ``None``. Non-blocking."""
        with self._lock:
            return self._frames[0] if self._frames else None

    def wait_for_delivery(self, seconds: float) -> None:
        self._delivery_ready.wait(seconds)

    @property
    def frames(self) -> list[bytes]:
        """Every accepted frame in arrival order; a second one is a duplicate."""
        with self._lock:
            return list(self._frames)

    @property
    def sender_pid(self) -> int | None:
        with self._lock:
            return self._sender_pid

    @property
    def error(self) -> ObservationRefused | None:
        with self._lock:
            return self._error

    @property
    def reader_terminated(self) -> bool:
        """Observed fact: the reader thread left its I/O loop (no live reader)."""
        with self._lock:
            return self._reader_terminated

    def close(self) -> None:
        """Stop the reader, prove it terminated, then release the OS handle.

        Order matters. Setting ``_closed`` makes a freshly returned refusal
        harmless, then cancellation aborts any in-flight overlapped operation,
        then we WAIT on the reader's own completion event. Only after that
        witness is positive do we close the Windows handle -- closing it while
        an operation is still pending is what used to block the host.
        """
        self._closed.set()
        if self._server is not None:
            self._server.cancel()
        if self._sock is not None:
            try:
                self._sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                self._sock.close()
            except OSError:
                pass
        thread = self._thread
        terminated = True
        if thread is not None and thread is not threading.current_thread():
            terminated = self._reader_done.wait(READER_TERMINATION_TIMEOUT_S)
            if terminated:
                thread.join(timeout=1.0)
                terminated = not thread.is_alive()
        with self._lock:
            self._reader_terminated = terminated
            if not terminated:
                self._error = ObservationRefused(
                    ["reader-not-terminated"],
                    "the native channel reader did not leave its I/O loop; the handle is left open rather than closed under a pending operation",
                )
        if self._server is not None and terminated:
            self._server.close()

    # -- reader -----------------------------------------------------------
    _TERMINAL_GAPS = ("channel-disconnected", "channel-unavailable", "peer-identity-unavailable")

    def _read_loop(self) -> None:
        try:
            self._read_until_stopped()
        except Exception as exc:  # noqa: BLE001 - a reader must surface, never crash the parent
            with self._lock:
                self._error = ObservationRefused(["channel-unavailable"], f"native channel reader failed: {exc}")
        finally:
            # The termination witness the host waits on before closing the handle.
            self._reader_done.set()

    def _read_until_stopped(self) -> None:
        while not self._closed.is_set():
            try:
                raw, sender_pid = self._accept_one()
            except ObservationRefused as exc:
                if self._closed.is_set() or exc.gaps == ("channel-closed",):
                    return
                with self._lock:
                    self.refusals.append(RefusedDelivery(None, exc.gaps, exc.reason))
                if exc.gaps and exc.gaps[0] in self._TERMINAL_GAPS:
                    with self._lock:
                        self._error = exc
                    return
                self._after_refusal()
                continue
            if raw is None:
                return
            if sender_pid != self._child_pid:
                with self._lock:
                    self.refusals.append(
                        RefusedDelivery(
                            sender_pid,
                            ("channel-foreign-sender",),
                            "a delivery arrived from a process that is not the spawned child",
                        )
                    )
                self._after_refusal()
                continue
            with self._lock:
                self._frames.append(raw)
                self._sender_pid = sender_pid
            self._delivery_ready.set()
            self._after_refusal()
            if self._server is None:
                # A connected socket cannot accept a second connection; a
                # further frame is read on the same socket.
                try:
                    raw = recv_frame(self._sock)  # type: ignore[arg-type]
                except ObservationRefused:
                    return
                with self._lock:
                    self._frames.append(raw)
                return

    def _after_refusal(self) -> None:
        if self._server is not None:
            self._server.disconnect()

    def _accept_one(self) -> tuple[bytes | None, int | None]:
        if self._server is not None:
            return self._server.accept_and_read()
        return self._accept_socket()

    def _accept_socket(self) -> tuple[bytes | None, int | None]:
        assert self._sock is not None
        try:
            peer_pid = _posix_peer_pid(self._sock)
        except ObservationRefused as exc:
            raise exc
        raw = recv_frame(self._sock)
        return raw, peer_pid


def _posix_peer_pid(sock: socket.socket) -> int | None:
    """OS-reported client PID for the accepted socket, or a refusal."""
    if hasattr(socket, "SO_PEERCRED"):
        try:
            creds = sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i"))
            _pid, _uid, _gid = struct.unpack("3i", creds)
            return int(_pid)
        except OSError as exc:
            raise ObservationRefused(["peer-identity-unavailable"], f"SO_PEERCRED failed: {exc}") from None
    if hasattr(socket, "LOCAL_PEERPID"):
        try:
            pid = sock.getsockopt(0, socket.LOCAL_PEERPID, struct.calcsize("i"))
            return int(struct.unpack("i", pid)[0])
        except OSError as exc:
            raise ObservationRefused(["peer-identity-unavailable"], f"LOCAL_PEERPID failed: {exc}") from None
    raise ObservationRefused(
        ["peer-identity-unavailable"],
        "this platform exposes no peer-credential primitive; a private channel cannot authenticate a sender",
    )


class _OVERLAPPED(ctypes.Structure):
    """``OVERLAPPED`` (winnt.h), the layout ``ReadFile``/``ConnectNamedPipe`` take.

    ``Internal``/``InternalHigh`` are ``ULONG_PTR`` values (pointer sized), hence
    ``c_size_t``; ``hEvent`` is the manual-reset event each operation signals.
    """

    _fields_ = [
        ("Internal", ctypes.c_size_t),
        ("InternalHigh", ctypes.c_size_t),
        ("Offset", ctypes.c_uint32),
        ("OffsetHigh", ctypes.c_uint32),
        ("hEvent", ctypes.c_void_p),
    ]


class _WindowsPipeServer:
    """Minimal ``CreateNamedPipeW`` server instance (ctypes only, no deps).

    Identity comes from ``GetNamedPipeClientProcessId`` -- the OS says which
    process is on the other end. The pipe name is therefore not a secret; a
    forged connection from any other PID is refused and the server keeps
    waiting for the real child.

    Lifecycle (why every operation is OVERLAPPED): a *synchronous* handle makes
    ``ConnectNamedPipe``/``ReadFile`` block unmaskably in the reader thread, and
    ``CloseHandle`` on a handle with a pending synchronous I/O waits for that
    I/O -- so ``close()`` deadlocks and the reader outlives the host. The server
    is therefore created with ``FILE_FLAG_OVERLAPPED``; each operation takes an
    ``OVERLAPPED`` with its own event, and the wait is served in short slices so
    the stop flag is honoured. ``cancel()`` sets the flag and calls
    ``CancelIoEx(handle, NULL)``, which aborts *all* pending I/O on the handle
    regardless of the issuing thread; the reader then observes
    ``ERROR_OPERATION_ABORTED`` and leaves. The handle is closed only after the
    reader has proved termination, so ``CloseHandle`` never waits on I/O.
    """

    PIPE_ACCESS_INBOUND = 0x00000001
    FILE_FLAG_OVERLAPPED = 0x40000000
    PIPE_TYPE_BYTE = 0x00000000
    PIPE_READMODE_BYTE = 0x00000000
    PIPE_WAIT = 0x00000000
    PIPE_UNLIMITED_INSTANCES = 255
    ERROR_PIPE_CONNECTED = 535
    ERROR_IO_PENDING = 997
    ERROR_OPERATION_ABORTED = 995
    ERROR_BROKEN_PIPE = 109
    ERROR_NO_DATA = 232
    ERROR_PIPE_NOT_CONNECTED = 233
    INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    WAIT_OBJECT_0 = 0
    WAIT_TIMEOUT = 258
    WAIT_FAILED = 0xFFFFFFFF

    def __init__(self) -> None:
        if sys.platform != "win32":  # pragma: no cover - platform guard
            raise ObservationRefused(["channel-unavailable"], "Windows named pipes require win32")
        import ctypes.wintypes as wt  # local: Windows-only types

        self._wt = wt
        k32 = ctypes.WinDLL("kernel32", use_last_error=True)
        self._k32 = k32
        k32.CreateNamedPipeW.restype = wt.HANDLE
        k32.CreateNamedPipeW.argtypes = [
            wt.LPCWSTR,
            wt.DWORD,
            wt.DWORD,
            wt.DWORD,
            wt.DWORD,
            wt.DWORD,
            wt.DWORD,
            ctypes.c_void_p,
        ]
        k32.ConnectNamedPipe.restype = wt.BOOL
        k32.ConnectNamedPipe.argtypes = [wt.HANDLE, ctypes.POINTER(_OVERLAPPED)]
        k32.GetOverlappedResult.restype = wt.BOOL
        k32.GetOverlappedResult.argtypes = [
            wt.HANDLE,
            ctypes.POINTER(_OVERLAPPED),
            ctypes.POINTER(wt.DWORD),
            wt.BOOL,
        ]
        k32.GetNamedPipeClientProcessId.restype = wt.BOOL
        k32.GetNamedPipeClientProcessId.argtypes = [wt.HANDLE, ctypes.POINTER(wt.ULONG)]
        k32.ReadFile.restype = wt.BOOL
        k32.ReadFile.argtypes = [
            wt.HANDLE,
            ctypes.c_void_p,
            wt.DWORD,
            ctypes.POINTER(wt.DWORD),
            ctypes.POINTER(_OVERLAPPED),
        ]
        k32.CancelIoEx.restype = wt.BOOL
        k32.CancelIoEx.argtypes = [wt.HANDLE, ctypes.POINTER(_OVERLAPPED)]
        k32.DisconnectNamedPipe.restype = wt.BOOL
        k32.DisconnectNamedPipe.argtypes = [wt.HANDLE]
        k32.CloseHandle.restype = wt.BOOL
        k32.CloseHandle.argtypes = [wt.HANDLE]
        k32.CreateEventW.restype = wt.HANDLE
        k32.CreateEventW.argtypes = [ctypes.c_void_p, wt.BOOL, wt.BOOL, wt.LPCWSTR]
        k32.WaitForSingleObject.restype = wt.DWORD
        k32.WaitForSingleObject.argtypes = [wt.HANDLE, wt.DWORD]

        self._stop = threading.Event()
        self._handle_open = False
        self._connected = False
        self._name = "\\\\.\\pipe\\mw-native-observation-" + os.urandom(16).hex()
        handle = k32.CreateNamedPipeW(
            self._name,
            self.PIPE_ACCESS_INBOUND | self.FILE_FLAG_OVERLAPPED,
            self.PIPE_TYPE_BYTE | self.PIPE_READMODE_BYTE | self.PIPE_WAIT,
            self.PIPE_UNLIMITED_INSTANCES,
            0,
            MAX_PAYLOAD_BYTES,
            0,
            None,
        )
        if not handle or handle == self.INVALID_HANDLE_VALUE:
            raise ObservationRefused(
                ["channel-unavailable"], f"CreateNamedPipeW failed (win32 error {ctypes.get_last_error()})"
            )
        self._handle = handle
        self._handle_open = True

    @property
    def name(self) -> str:
        return self._name

    @property
    def cancelled(self) -> bool:
        return self._stop.is_set()

    # -- overlapped plumbing ---------------------------------------------
    def _new_overlapped(self) -> _OVERLAPPED:
        ov = _OVERLAPPED()
        ov.hEvent = self._k32.CreateEventW(None, True, False, None)
        if not ov.hEvent:
            raise ObservationRefused(
                ["channel-unavailable"], f"CreateEventW failed (win32 error {ctypes.get_last_error()})"
            )
        return ov

    def _free_overlapped(self, ov: _OVERLAPPED) -> None:
        if ov.hEvent:
            try:
                self._k32.CloseHandle(ov.hEvent)
            except Exception:  # noqa: BLE001 - best-effort cleanup
                pass
            ov.hEvent = None

    def _await(self, ov: _OVERLAPPED) -> None:
        """Wait for one pending overlapped operation in cancellable slices."""
        while True:
            if self._stop.is_set():
                self._k32.CancelIoEx(self._handle, None)
                # Drain the completion so no I/O is outstanding on the handle
                # when the caller later closes it.
                self._drain(ov)
                raise ObservationRefused(["channel-closed"], "the host closed the observation channel")
            rc = int(self._k32.WaitForSingleObject(ov.hEvent, WINDOWS_WAIT_SLICE_MS))
            if rc == self.WAIT_OBJECT_0:
                return
            if rc == self.WAIT_TIMEOUT:
                continue
            raise ObservationRefused(["channel-unavailable"], f"WaitForSingleObject failed (wait result {rc})")

    def _drain(self, ov: _OVERLAPPED) -> None:
        transferred = self._wt.DWORD(0)
        self._k32.GetOverlappedResult(self._handle, ctypes.byref(ov), ctypes.byref(transferred), True)

    def _completed_bytes(self, ov: _OVERLAPPED, *, op: str) -> int:
        transferred = self._wt.DWORD(0)
        if not self._k32.GetOverlappedResult(self._handle, ctypes.byref(ov), ctypes.byref(transferred), True):
            err = ctypes.get_last_error()
            if err == self.ERROR_OPERATION_ABORTED or self._stop.is_set():
                raise ObservationRefused(["channel-closed"], "the host closed the observation channel")
            raise ObservationRefused(["channel-disconnected"], f"{op} failed (win32 error {err})")
        return int(transferred.value)

    # -- protocol ---------------------------------------------------------
    def accept_and_read(self) -> tuple[bytes | None, int | None]:
        ov = self._new_overlapped()
        try:
            ok = self._k32.ConnectNamedPipe(self._handle, ctypes.byref(ov))
            if not ok:
                err = ctypes.get_last_error()
                if err == self.ERROR_PIPE_CONNECTED:
                    pass  # a client connected between CreateNamedPipe and here
                elif err == self.ERROR_IO_PENDING:
                    self._await(ov)
                    self._completed_bytes(ov, op="ConnectNamedPipe")
                else:
                    raise ObservationRefused(
                        ["channel-unavailable"], f"ConnectNamedPipe failed (win32 error {err})"
                    )
        finally:
            self._free_overlapped(ov)
        self._connected = True
        pid = self._wt.ULONG(0)
        if not self._k32.GetNamedPipeClientProcessId(self._handle, ctypes.byref(pid)):
            raise ObservationRefused(
                ["peer-identity-unavailable"],
                f"GetNamedPipeClientProcessId failed (win32 error {ctypes.get_last_error()})",
            )
        raw = self._read_frame()
        return raw, int(pid.value)

    def _read(self, count: int) -> bytes:
        buffer = ctypes.create_string_buffer(count)
        ov = self._new_overlapped()
        try:
            ok = self._k32.ReadFile(self._handle, buffer, count, None, ctypes.byref(ov))
            if not ok:
                err = ctypes.get_last_error()
                if err == self.ERROR_IO_PENDING:
                    self._await(ov)
                elif err in (self.ERROR_BROKEN_PIPE, self.ERROR_PIPE_NOT_CONNECTED, self.ERROR_NO_DATA):
                    raise ObservationRefused(
                        ["channel-disconnected"], f"ReadFile failed (win32 error {err})"
                    )
                elif self._stop.is_set():
                    raise ObservationRefused(["channel-closed"], "the host closed the observation channel")
                else:
                    raise ObservationRefused(
                        ["channel-disconnected"], f"ReadFile failed (win32 error {err})"
                    )
            got = self._completed_bytes(ov, op="ReadFile")
        finally:
            self._free_overlapped(ov)
        if got == 0:
            raise ObservationRefused(["channel-disconnected"], "the private channel closed mid-frame")
        return buffer.raw[:got]

    def _read_frame(self) -> bytes:
        header = self._read(4)
        if len(header) != 4:
            raise ObservationRefused(["channel-disconnected"], "the private channel closed mid-header")
        (length,) = _HEADER.unpack(header)
        if length == 0:
            raise ObservationRefused(["payload-empty"], "native payload frame declares zero bytes")
        if length > MAX_PAYLOAD_BYTES:
            raise ObservationRefused(
                ["payload-too-large"],
                f"native payload frame declares {length} bytes, above the {MAX_PAYLOAD_BYTES} bound",
            )
        chunks = []
        read = 0
        while read < length:
            chunk = self._read(min(length - read, 65536))
            chunks.append(chunk)
            read += len(chunk)
        return b"".join(chunks)

    def disconnect(self) -> None:
        """Drop the accepted client so the next instance can take a new one.

        Only called by the reader thread when no operation is in flight.
        """
        if self._connected and self._handle_open:
            try:
                self._k32.DisconnectNamedPipe(self._handle)
            finally:
                self._connected = False

    def cancel(self) -> None:
        """Ask the reader to stop: flag + abort every pending I/O on the handle."""
        self._stop.set()
        if self._handle_open:
            try:
                self._k32.CancelIoEx(self._handle, None)
            except Exception:  # noqa: BLE001 - cancellation is best effort here
                pass

    def close(self) -> bool:
        """Close the pipe instance. Only legal once no I/O is outstanding.

        Returns whether the handle was closed. A caller that could not prove the
        reader terminated must not call this: ``CloseHandle`` on a handle with a
        pending synchronous I/O is exactly the hang this type exists to avoid.
        """
        self.cancel()
        if not self._handle_open:
            return True
        self._handle_open = False
        try:
            return bool(self._k32.CloseHandle(self._handle))
        except Exception:  # noqa: BLE001 - best-effort cleanup
            return False


# ── accepted observation + current-lifetime registry ───────────────────────


@dataclass(frozen=True)
class NativeReviewObservation:
    observation_id: str
    owner_key: str
    task_key: str
    run_id: str
    claim_id: str
    parent_run_id: str
    card_sha256: str
    envelope_sha256: str
    material_digest: str
    basis_digest: str
    goal_digest: str
    local_ref: str
    execution_ref: str
    tool_call_ref: str
    implementer_task_key: str
    implementer_run_id: str
    verdict: str
    reviewed_at: str
    findings: tuple[str, ...]
    unresolved_findings: tuple[str, ...]
    refs: tuple[str, ...]
    verifier_ref: str
    report_sha256: str
    report_bytes: bytes = field(repr=False)
    delivered_at: str
    started_at: str
    ended_at: str
    exit_code: int
    child_pid: int
    sender_pid: int
    payload_digest: str
    payload_bytes: bytes = field(repr=False)


@dataclass(frozen=True)
class CurrentExpectations:
    """The CURRENT facts a later consumption must still match. Every field is a
    host-owned fact; nothing here is taken from the observation itself."""

    owner_key: str
    task_key: str
    run_id: str
    claim_id: str
    parent_run_id: str
    card_sha256: str
    material_digest: str
    basis_digest: str
    goal_digest: str
    local_ref: str
    execution_ref: str
    tool_call_ref: str
    implementer_task_key: str
    implementer_run_id: str
    execution_created_at: str
    budget_deadline: str
    stopped: bool = False


class NativeObservationRegistry:
    """CURRENT-LIFETIME memory only.

    Nothing here is persisted; a restarted process starts empty, so an old
    observation can never be replayed into authority. Insertion is decided by
    the parent that observed the real spawn/exit, and consumption re-checks
    both the registry state and the caller's current facts.
    """

    def __init__(self) -> None:
        self._records: dict[str, NativeReviewObservation] = {}
        self._by_run: dict[tuple[str, str, str], str] = {}
        self._poisoned: dict[tuple[str, str, str], str] = {}
        self._lock = threading.Lock()

    # -- insertion -------------------------------------------------------
    def apply(
        self,
        delivery_raw: bytes,
        *,
        child_pid: int,
        sender_pid: int,
        exit_code: int,
        started_at: str,
        ended_at: str,
    ) -> NativeReviewObservation:
        payload = parse_native_review_payload(delivery_raw)
        run = payload["run"]
        key = (str(run["owner_key"]), str(run["task_key"]), str(run["run_id"]))
        report_bytes: bytes = payload["_report_bytes"]
        observed = NativeReviewObservation(
            observation_id=_sha256(delivery_raw + b"|" + str(sender_pid).encode()),
            owner_key=str(run["owner_key"]),
            task_key=str(run["task_key"]),
            run_id=str(run["run_id"]),
            claim_id=str(payload["dispatch"]["claim_id"]),
            parent_run_id=str(payload["dispatch"]["parent_run_id"]),
            card_sha256=str(payload["dispatch"]["card_sha256"]),
            envelope_sha256=str(payload["dispatch"]["envelope_sha256"]),
            material_digest=str(payload["dispatch"]["material_digest"]),
            basis_digest=str(payload["dispatch"]["basis_digest"]),
            goal_digest=str(payload["dispatch"]["goal_digest"]),
            local_ref=str(payload["dispatch"]["local_ref"]),
            execution_ref=str(payload["dispatch"]["execution_ref"]),
            tool_call_ref=str(payload["dispatch"]["tool_call_ref"]),
            implementer_task_key=str(payload["dispatch"]["implementer_task_key"]),
            implementer_run_id=str(payload["dispatch"]["implementer_run_id"]),
            verdict=str(payload["review"]["verdict"]),
            reviewed_at=str(payload["review"]["reviewed_at"]),
            findings=tuple(payload["review"]["findings"]),
            unresolved_findings=tuple(payload["review"]["unresolved_findings"]),
            refs=tuple(payload["review"]["refs"]),
            verifier_ref=str(payload["review"]["verifier_ref"]),
            report_sha256=str(payload["report"]["sha256"]),
            report_bytes=report_bytes,
            delivered_at=str(payload["delivered_at"]),
            started_at=str(run["started_at"]),
            ended_at=ended_at,
            exit_code=int(exit_code),
            child_pid=int(child_pid),
            sender_pid=int(sender_pid),
            payload_digest=_sha256(delivery_raw),
            payload_bytes=delivery_raw[:256],
        )
        if observed.sender_pid != observed.child_pid:
            raise ObservationRefused(
                ["channel-foreign-sender"], "an observation never belongs to a sender that is not the spawned child"
            )
        if observed.exit_code != 0:
            raise ObservationRefused(
                ["run-exit-nonzero"], "the child exited non-zero; a failed terminal run mints no observation"
            )
        if run.get("status") != "done":
            raise ObservationRefused(["run-not-done"], "the child terminal state is not done")
        delivered_ms = _iso_ms(observed.delivered_at)
        started_ms = _iso_ms(observed.started_at)
        ended_ms = _iso_ms(observed.ended_at)
        if delivered_ms is None or started_ms is None or ended_ms is None:
            raise ObservationRefused(["run-clock"], "delivery/start/exit instants are not all finite")
        if delivered_ms < started_ms:
            raise ObservationRefused(["delivery-before-start"], "the payload claims a delivery before its run started")
        if delivered_ms > ended_ms + CLOCK_SLACK_MS:
            raise ObservationRefused(
                ["delivery-after-exit"],
                "the payload was delivered after the parent observed the child exit; that is not a live terminal delivery",
            )
        with self._lock:
            if key in self._poisoned:
                raise ObservationRefused(
                    ["observation-poisoned"], "a duplicate/conflicting delivery already invalidated this run"
                )
            existing = self._by_run.get(key)
            if existing is not None:
                previous = self._records[existing]
                same = previous.payload_digest == observed.payload_digest
                self._poisoned[key] = "duplicate" if same else "conflict"
                self._records.pop(existing, None)
                self._by_run.pop(key, None)
                raise ObservationRefused(
                    ["observation-duplicate" if same else "observation-conflict"],
                    "a second terminal delivery for this run invalidates the first one",
                )
            self._records[observed.observation_id] = observed
            self._by_run[key] = observed.observation_id
        return observed

    # -- lookup ----------------------------------------------------------
    def get(self, observation_id: str) -> NativeReviewObservation | None:
        with self._lock:
            return self._records.get(observation_id)

    def for_run(self, owner_key: str, task_key: str, run_id: str) -> NativeReviewObservation | None:
        with self._lock:
            observation_id = self._by_run.get((owner_key, task_key, run_id))
            return None if observation_id is None else self._records.get(observation_id)

    def invalidate(self, predicate: Callable[[NativeReviewObservation], bool]) -> int:
        """Drop every observation whose CURRENT facts no longer hold (claim/parent/
        task/run/budget/stop change). Returns how many were dropped."""
        removed = 0
        with self._lock:
            for observation_id, record in list(self._records.items()):
                if predicate(record):
                    self._records.pop(observation_id, None)
                    self._by_run.pop((record.owner_key, record.task_key, record.run_id), None)
                    removed += 1
        return removed

    def __len__(self) -> int:
        with self._lock:
            return len(self._records)


def consume_current_native_review(
    registry: NativeObservationRegistry,
    observation_id: str,
    expected: CurrentExpectations,
    *,
    now_ms: int,
    disk_report_bytes: bytes | None,
    on_disk_card_sha256: str | None = None,
    require_pass: bool = True,
) -> NativeReviewObservation:
    """The only way an observation becomes usable. Every current fact is
    re-checked; a mismatch is a refusal with a concrete gap, never a lower pass."""
    observation = registry.get(observation_id)
    if observation is None:
        raise ObservationRefused(
            ["observation-not-current"],
            "no current-lifetime native observation for this id; a restarted/expired host restores no authority",
        )
    for name in (
        "owner_key",
        "task_key",
        "run_id",
        "claim_id",
        "parent_run_id",
        "card_sha256",
        "material_digest",
        "basis_digest",
        "goal_digest",
        "local_ref",
        "execution_ref",
        "tool_call_ref",
        "implementer_task_key",
        "implementer_run_id",
    ):
        if getattr(observation, name) != getattr(expected, name):
            raise ObservationRefused(
                [f"currentness-{name.replace('_', '-')}"],
                f"the native observation's {name} is not the current {name}",
            )
    if expected.stopped:
        raise ObservationRefused(["stopped"], "the owning scope is stopped; a stopped scope consumes no observation")
    if on_disk_card_sha256 is not None and on_disk_card_sha256 != observation.card_sha256:
        raise ObservationRefused(["card-drift"], "the pinned card bytes drifted from the dispatched card")
    if disk_report_bytes is None:
        raise ObservationRefused(["report-missing"], "the official terminal report is not readable")
    if _sha256(disk_report_bytes) != observation.report_sha256:
        raise ObservationRefused(
            ["report-changed-after-delivery"],
            "report.md no longer matches the bytes this run delivered; a later edit is not the terminal content",
        )
    if observation.unresolved_findings and (require_pass or observation.verdict == "pass"):
        raise ObservationRefused(
            ["review-unresolved-findings"], "a review with unresolved findings is not a completed verification"
        )
    execution_ms = _iso_ms(expected.execution_created_at)
    reviewed_ms = _iso_ms(observation.reviewed_at)
    delivered_ms = _iso_ms(observation.delivered_at)
    deadline_ms = _iso_ms(expected.budget_deadline)
    for label, value in (
        ("execution-created-at", execution_ms),
        ("reviewed-at", reviewed_ms),
        ("delivered-at", delivered_ms),
        ("budget-deadline", deadline_ms),
    ):
        if value is None:
            raise ObservationRefused([f"{label}-invalid"], f"{label} is not a finite ISO instant")
    if reviewed_ms < execution_ms:
        raise ObservationRefused(["review-stale"], "the review predates the execution it claims to verify")
    if reviewed_ms > now_ms:
        raise ObservationRefused(["review-future"], "the review is dated after the current host instant")
    if delivered_ms > now_ms:
        raise ObservationRefused(["delivery-future"], "the delivery is dated after the current host instant")
    if now_ms >= deadline_ms:
        raise ObservationRefused(["budget-expired"], "the owning scope's budget deadline has passed")
    if observation.verdict == "pass" and not observation.findings:
        raise ObservationRefused(["review-empty-findings"], "a PASS with no findings carries no verification")
    if observation.verdict != "pass" and require_pass:
        raise ObservationRefused(
            ["review-not-pass"], f"the current native review verdict is {observation.verdict}; no QG pass"
        )
    return observation


_REVIEW_CARD_BLOCK = re.compile(r"^```mw-local-qg\s*\n(.*?)\n```[ \t]*$", re.MULTILINE | re.DOTALL)
_REVIEW_BINDINGS = (
    "parent_run_id", "implementer_task_key", "implementer_run_id", "local_ref",
    "execution_ref", "tool_call_ref", "material_digest", "basis_digest",
    "execution_created_at", "budget_deadline",
)
_IDENTIFIER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")


def _review_bytes(path: Path) -> bytes:
    if path.resolve(strict=True) != path:
        raise OSError("review path is redirected")
    with path.open("rb") as stream:
        data = stream.read(MAX_PAYLOAD_BYTES + 1)
    if not data or len(data) > MAX_PAYLOAD_BYTES:
        raise OSError("review input is empty or oversized")
    return data


def native_review_command(command: list[str]) -> list[str] | None:
    """Use a direct Popen identity for Pi, including the managed Windows shim.

    Unknown shell wrappers continue through normal review dispatch without
    gaining an authenticated observation.
    """
    executable = Path(command[0])
    if executable.suffix.lower() == ".exe":
        return command
    if executable.name.lower() != "pi.cmd":
        return None
    try:
        shim = _review_bytes(executable).decode("utf-8-sig")
    except (OSError, UnicodeError):
        return None
    direct = re.fullmatch(
        r'@echo off\s+"([^"\r\n]+\\node\.exe)" "([^"\r\n]+\.(?:[cm]?js|ts))" %\*\s+exit /b %errorlevel%\s*',
        shim, re.IGNORECASE,
    )
    if direct is None:
        return None
    node, cli = direct.groups()
    cli = cli.replace("%~dp0", str(executable.parent) + os.sep)
    node_path, cli_path = Path(node), Path(cli)
    if not all(p.is_absolute() and p.is_file() for p in (node_path, cli_path)):
        return None
    return [str(node_path), str(cli_path.resolve()), *command[1:]]


@dataclass
class NativeReviewLaunch:
    channel: HostObservationChannel
    project: Path
    key: str
    task: str
    envelope: Path
    card: Path
    dispatch: dict[str, str]
    started_at: str

    @property
    def child_env(self) -> dict[str, str]:
        return {**self.channel.child_env, ENV_DISPATCH: json.dumps(self.dispatch)}

    def inputs_are_current(self) -> bool:
        try:
            return (
                _sha256(_review_bytes(self.envelope)) == self.dispatch["envelope_sha256"]
                and _sha256(_review_bytes(self.card).replace(b"\r\n", b"\n")) == self.dispatch["card_sha256"]
                and _sha256(_review_bytes(self.project / ".agenticdoc" / "goal.md")) == self.dispatch["goal_digest"]
            )
        except OSError:
            return False


def prepare_native_review(
    project: Path,
    task_path: Path,
    task_key: str,
    read_header: Callable[[str, str], str | None],
    current_claim: Callable[[str], str | None],
) -> NativeReviewLaunch | None:
    if sys.platform != "win32":
        return None
    try:
        task_path = task_path.absolute()
        document = project / ".agenticdoc"
        key, workers, task, filename = task_path.relative_to(document).parts
        if (workers, task, filename) != ("workers", task_key, "task.md") or not all(
            _IDENTIFIER.fullmatch(value) for value in (key, task)
        ):
            return None
        raw = _review_bytes(task_path)
        text = raw.decode("utf-8-sig")
        if read_header(text, "type") != "review":
            return None
        card_path = read_header(text, "card_path") or ""
        if not re.fullmatch(r"tasks/(?:[\w.-]+/)*[\w.-]+\.md", card_path) or {".", ".."} & set(card_path.split("/")):
            return None
        card = document / key / card_path
        card_bytes = _review_bytes(card).replace(b"\r\n", b"\n")
        card_text = card_bytes.decode("utf-8-sig")
        card_hash = _sha256(card_bytes)
        claim = current_claim(key)
        if (
            not claim or card_hash != read_header(text, "card_sha256")
            or read_header(card_text, "type") != "review"
            or read_header(card_text, "owning_pm_claim") != claim
        ):
            return None
        blocks = _REVIEW_CARD_BLOCK.findall(card_text)
        if len(blocks) != 1:
            return None
        bound = json.loads(blocks[0])
        if not isinstance(bound, dict) or set(bound) != set(_REVIEW_BINDINGS) or not all(
            _nonblank(bound[field]) for field in _REVIEW_BINDINGS
        ):
            return None
        deadline = _iso_ms(bound["budget_deadline"])
        execution = _iso_ms(bound["execution_created_at"])
        now = int(time.time() * 1000)
        if execution is None or deadline is None or not execution <= now < deadline:
            return None
        dispatch = {
            **bound, "claim_id": claim, "card_path": card_path, "card_sha256": card_hash,
            "envelope_sha256": _sha256(raw), "goal_digest": _sha256(_review_bytes(document / "goal.md")),
        }
        channel = HostObservationChannel.create()
    except (OSError, TypeError, ValueError, ObservationRefused):
        return None
    return NativeReviewLaunch(channel, project, key, task, task_path, card, dispatch, datetime.now(timezone.utc).isoformat())


def _relay_address(project: Path, pid: int) -> str:
    project_id = _sha256(os.path.normcase(str(project.resolve())).encode())[:32]
    return rf"\\.\pipe\mw-native-review-{project_id}-{pid}"


class NativeReviewRelay:
    """A read-only, launcher-lifetime relay for already witnessed review runs."""

    def __init__(
        self, project: Path, current_claim: Callable[[str], str | None],
        *, read_current_claim: Callable[[str], str | None] | None = None,
    ) -> None:
        self.project = project
        self.current_claim = current_claim
        self.read_current_claim = read_current_claim or current_claim
        self.registry = NativeObservationRegistry()
        self.launches: dict[tuple[str, str, str], NativeReviewLaunch] = {}
        self.lock = threading.Lock()
        self.listener = Listener(_relay_address(project, os.getpid()), family="AF_PIPE")
        threading.Thread(target=self.serve, name="mw-native-review-readback", daemon=True).start()

    def reap(self, launch: NativeReviewLaunch, pid: int, returncode: int) -> None:
        ended = datetime.now(timezone.utc).isoformat()
        if returncode == 0:
            launch.channel.wait_for_delivery(0.25)
        launch.channel.close()
        frames = launch.channel.frames
        if (
            returncode != 0 or len(frames) != 1 or launch.channel.sender_pid != pid
            or not launch.channel.reader_terminated or not launch.inputs_are_current()
            or self.current_claim(launch.key) != launch.dispatch["claim_id"]
        ):
            return
        try:
            terminal = parse_native_review_payload(frames[0])
            run = terminal["run"]
            started = _iso_ms(run["started_at"])
            run_task, _, run_start = run["run_id"].partition("@")
            named_start = _iso_ms(run_start)
            start_bound, end_bound = _iso_ms(launch.started_at), _iso_ms(ended)
            if (
                terminal["dispatch"] != launch.dispatch or run["owner_key"] != launch.key
                or run["task_key"] != launch.task or run_task != launch.task
                or started is None or named_start is None or start_bound is None or end_bound is None
                or not start_bound <= named_start <= started
                or not start_bound <= started <= end_bound
            ):
                return
            observed = self.registry.apply(
                frames[0], child_pid=pid, sender_pid=pid, exit_code=returncode,
                started_at=launch.started_at, ended_at=ended,
            )
            with self.lock:
                self._prune()
                self.launches[(launch.key, launch.task, observed.run_id)] = launch
        except ObservationRefused:
            return

    def _prune(self) -> None:
        now = int(time.time() * 1000)
        expired = {key for key, launch in self.launches.items() if (_iso_ms(launch.dispatch["budget_deadline"]) or 0) <= now}
        for key in expired:
            del self.launches[key]
        if len(self.launches) >= 256:
            expired.add(next(iter(self.launches)))
            del self.launches[next(iter(self.launches))]
        self.registry.invalidate(lambda observation: (observation.owner_key, observation.task_key, observation.run_id) in expired)

    def read(self, key: str, task: str, run_id: str) -> dict | None:
        with self.lock:
            launch = self.launches.get((key, task, run_id))
        candidate = self.registry.for_run(key, task, run_id)
        if launch is None or candidate is None or not launch.inputs_are_current():
            return None
        dispatch = launch.dispatch
        if self.read_current_claim(key) != dispatch["claim_id"]:
            return None
        try:
            observed = consume_current_native_review(
                self.registry, candidate.observation_id,
                CurrentExpectations(key, task, run_id, dispatch["claim_id"], **{
                    k: v for k, v in dispatch.items() if k in (
                        "parent_run_id", "card_sha256", "material_digest", "basis_digest", "goal_digest", "local_ref",
                        "execution_ref", "tool_call_ref", "implementer_task_key", "implementer_run_id",
                        "execution_created_at", "budget_deadline",
                    )
                }),
                now_ms=int(time.time() * 1000), disk_report_bytes=_review_bytes(launch.envelope.parent / "report.md"),
                require_pass=False,
            )
        except (OSError, ObservationRefused):
            return None
        return {
            "owner_key": key, "task_key": task, "run_id": run_id, "dispatch": dispatch,
            "verdict": observed.verdict, "reviewed_at": observed.reviewed_at,
            "verifier_ref": observed.verifier_ref, "findings": observed.findings,
            "unresolved_findings": observed.unresolved_findings, "refs": observed.refs,
            "report_sha256": observed.report_sha256,
        }

    def serve(self) -> None:
        from mw import _decide_parent_pid

        while True:
            try:
                connection = self.listener.accept()
            except (OSError, EOFError):
                return
            try:
                with connection:
                    if not connection.poll(0.25):
                        continue
                    request = json.loads(connection.recv_bytes(4096))
                    if not isinstance(request, list) or len(request) != 3 or not all(
                        isinstance(value, str) and 0 < len(value) < 240 for value in request
                    ):
                        continue
                    owner = self.read_current_claim(request[0])
                    peer = _pipe_peer(connection.fileno(), server=False)
                    if not owner or peer is None or _decide_parent_pid(peer) != int(owner.rsplit(":", 1)[1]):
                        continue
                    connection.send_bytes(json.dumps(self.read(*request)).encode())
            except (OSError, EOFError, ValueError):
                continue


def _pipe_peer(handle: int, *, server: bool) -> int | None:
    kernel = ctypes.windll.kernel32
    get_pid = kernel.GetNamedPipeServerProcessId if server else kernel.GetNamedPipeClientProcessId
    get_pid.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_ulong)]
    get_pid.restype = ctypes.c_int
    peer = ctypes.c_ulong()
    return peer.value if get_pid(handle, ctypes.byref(peer)) and peer.value != 0 else None


def _relay_read(project: Path, pid: int, request: bytes) -> bytes | None:
    import _winapi
    from multiprocessing.connection import PipeConnection

    handle = _winapi.CreateFile(
        _relay_address(project, pid), _winapi.GENERIC_READ | _winapi.GENERIC_WRITE,
        0, _winapi.NULL, _winapi.OPEN_EXISTING, _winapi.FILE_FLAG_OVERLAPPED, _winapi.NULL,
    )
    with PipeConnection(handle) as connection:
        _winapi.SetNamedPipeHandleState(handle, _winapi.PIPE_READMODE_MESSAGE, None, None)
        if _pipe_peer(connection.fileno(), server=True) != pid:
            return None
        connection.send_bytes(request)
        if not connection.poll(0.5):
            return None
        response = connection.recv_bytes(MAX_PAYLOAD_BYTES)
        return None if response == b"null" else response


def read_launchers(project: Path, request: bytes) -> bytes | None:
    if sys.platform != "win32" or len(request) > 4096:
        return None
    import mw_common
    from mw import _decide_parent_pid

    # Heartbeat filenames discover candidates. The kernel relationship anchors
    # them to this local PM or to the current project service's process lifetime.
    parents = {os.getppid()}
    service = mw_common.read_serve_identity(project)
    if service is not None and mw_common.check_pid(mw_common.pid_file(project)) == service["pid"]:
        started = mw_common.process_start_ms(service["pid"])
        if started is not None and abs(started - service["started_at_ms"]) <= 60_000:
            parents.add(service["pid"])
    responses = []
    for beat in (project / ".mw").glob("launcher-beat.*"):
        try:
            if time.time() - beat.stat().st_mtime > 30:
                continue
            pid = int(beat.name.rsplit(".", 1)[1])
            if _decide_parent_pid(pid) not in parents:
                continue
            response = _relay_read(project, pid, request)
            if response is not None:
                responses.append(response)
        except (OSError, EOFError, ValueError):
            continue
    return responses[0] if len(responses) == 1 else None


if __name__ == "__main__" and len(sys.argv) == 3 and sys.argv[1] == "read":
    result = read_launchers(Path(sys.argv[2]).resolve(), sys.stdin.buffer.read(4097))
    sys.stdout.buffer.write(result or b"null")
