"""Local operator IPC. A client can present a draft and inspect its own result.

The deployed trust anchor is the running Windows service, never a caller's
environment or a project file. This module registers no account, service,
credential, grant or endpoint at import time.
"""
from __future__ import annotations

import base64
import binascii
import ctypes
from contextlib import ExitStack
from ctypes import wintypes as wt
from dataclasses import dataclass
import hashlib
import json
import math
import os
from pathlib import Path
from types import MappingProxyType
from collections.abc import Mapping
import socket

import decision_policy
import re
import time

MAX_PAYLOAD = 1024 * 1024
MAX_FRAME = MAX_PAYLOAD * 2
ERROR_SERVICE_DOES_NOT_EXIST = 1060
SERVICE_NAME = "MultiWorkersOperatorHost"
PIPES = {"ask": r"\\.\pipe\MultiWorkers.OperatorHost.v1.ask",
         "h12": r"\\.\pipe\MultiWorkers.OperatorHost.v1.h12"}
_ID = re.compile(r"[0-9a-f]{32}\Z")
_PROJECT = re.compile(r"[0-9a-f]{16}\Z")
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:@-]{0,159}\Z")
_SID = re.compile(r"S-1-(?:[0-9]+-){1,14}[0-9]+\Z")
_FIELDS = {
    "ask.submit": {"payload_b64"}, "ask.result": {"id"},
    "ask.brake-read": set(), "ask.brake-trigger": {"payload_b64"},
    "h12.prepare": {"grant_ref", "key", "trip_id", "payload_b64"}, "h12.status": {"id"},
}
# The narrow ordinary-channel brake surface: one trigger and one read. A
# client never names the object path, a state transition, a trip id or any
# origin/role/trust/grant field.
_BRAKE_TRIGGER_FIELDS = {"schema", "purpose", "project_id", "reason_code",
                         "detail", "evidence", "request_id"}
_BRAKE_FACTS_FIELDS = {"state", "active", "reason", "trip_id",
                       "generation_verified", "brake_sha256", "ledger_seq"}
_BRAKE_TRIGGER_REPLY_FIELDS = {"ok", "trip_id", "state", "created", "receipt_sha256"}
# A status reply is a fact, never an authority. Only the operation that owns
# the observation lifecycle may read its observer states; ask results may not
# treat a recovery state as their own.
_RESULT_STATES = {
    "ask.result": ("pending", "expired", "reserved", "applied", "failed", "unknown"),
    "h12.status": ("pending", "expired", "reserved", "applied", "failed", "unknown",
                   "observing", "retripped", "settled"),
}
_EMPTY_RESULT_STATES = ("pending", "expired", "reserved")
# The only failure records the host itself writes for an uncertain operation.
# Anything else (a success flag, an extra field, a decision id) is refused.
_UNKNOWN_RESULT_KEYS = ({"ok", "reason"}, {"ok", "reason", "consumer"},
                        {"ok", "reason", "failed_checks"})
_CONSUMER_KEYS = {"ok", "reason", "choice"}


class AuthorityError(ValueError):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)


class ServiceNotDeployed(AuthorityError):
    """The SCM's own SERVICE_DOES_NOT_EXIST: the only unmanaged proof."""

    def __init__(self):
        super().__init__("host-not-deployed")


@dataclass(frozen=True)
class FrozenPayload:
    raw: bytes
    sha256: str

    @property
    def encoded(self) -> str:
        return base64.b64encode(self.raw).decode("ascii")


@dataclass(frozen=True)
class Peer:
    sid: str
    pid: int
    created_ns: int
    session_id: int
    image: str


@dataclass(frozen=True)
class ServiceTrust:
    peer: Peer
    config_path: Path

    @property
    def service_sid(self) -> str:
        return self.peer.sid


def _object(raw: bytes, maximum: int) -> dict:
    if not isinstance(raw, bytes) or not 0 < len(raw) <= maximum:
        raise AuthorityError("invalid-size")

    def unique(pairs):
        obj = dict(pairs)
        if len(obj) != len(pairs):
            raise ValueError()
        return obj

    try:
        value = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
        if not isinstance(value, dict):
            raise ValueError()
        # Reject non-finite numbers and escaped unpaired surrogates as well
        # as malformed input. Always retain the original bytes for display.
        json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return value
    except (ValueError, UnicodeError, RecursionError, OverflowError):
        raise AuthorityError("invalid-json") from None


def freeze_payload(raw: bytes) -> FrozenPayload:
    _object(raw, MAX_PAYLOAD)
    return FrozenPayload(raw, hashlib.sha256(raw).hexdigest())


def decode_payload(encoded: str) -> FrozenPayload:
    if not isinstance(encoded, str) or len(encoded) > 4 * ((MAX_PAYLOAD + 2) // 3):
        raise AuthorityError("invalid-base64")
    try:
        raw = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise AuthorityError("invalid-base64") from None
    frozen = freeze_payload(raw)
    if encoded != frozen.encoded:
        raise AuthorityError("invalid-base64")
    return frozen


def _matches(pattern, value):
    return isinstance(value, str) and pattern.fullmatch(value) is not None


def validate_message(purpose: str, message: dict) -> dict:
    if purpose not in PIPES or not isinstance(message, dict):
        raise AuthorityError("bad-operation")
    op = message.get("op")
    if not isinstance(op, str) or op not in _FIELDS or op.partition(".")[0] != purpose:
        raise AuthorityError("bad-operation")
    if set(message) != {"v", "op", "project_id"} | _FIELDS[op]:
        raise AuthorityError("bad-fields")
    if type(message["v"]) is not int or message["v"] != 1 or not _matches(_PROJECT, message["project_id"]):
        raise AuthorityError("bad-binding")
    for name in ("id", "grant_ref", "key", "trip_id"):
        if name in message and not _matches(_ID if name in ("id", "grant_ref") else _TOKEN, message[name]):
            raise AuthorityError("bad-binding")
    if "payload_b64" in message:
        frozen = decode_payload(message["payload_b64"])
        if op == "ask.brake-trigger":
            draft = _object(frozen.raw, MAX_PAYLOAD)
            if set(draft) != _BRAKE_TRIGGER_FIELDS or draft["schema"] != 1 \
                    or draft["purpose"] != "brake-trigger" \
                    or draft["project_id"] != message["project_id"]:
                raise AuthorityError("invalid-brake-trigger")
            if not _matches(_TOKEN, draft["reason_code"]) \
                    or not isinstance(draft["detail"], str) or not draft["detail"].strip() \
                    or not _matches(_ID, draft["request_id"]):
                raise AuthorityError("invalid-brake-trigger")
            evidence = draft["evidence"]
            if (not isinstance(evidence, list) or not evidence or len(evidence) > 64
                    or any(type(item) is not int or item < 1 for item in evidence)
                    or len(set(evidence)) != len(evidence)):
                raise AuthorityError("invalid-brake-trigger")
    return message


def _deadline(timeout_ms: int):
    if type(timeout_ms) is not int or not 0 < timeout_ms <= 30_000:
        raise AuthorityError("invalid-timeout")
    return time.monotonic() + timeout_ms / 1000


def _remaining(end: float):
    ms = math.ceil((end - time.monotonic()) * 1000)
    if ms <= 0:
        raise AuthorityError("host-timeout")
    return ms


def _safe_unknown_result(result) -> bool:
    if not isinstance(result, dict) or set(result) not in _UNKNOWN_RESULT_KEYS:
        return False
    if result.get("ok") is not False or not _matches(_TOKEN, result.get("reason")):
        return False
    if "consumer" in result:
        consumer = result["consumer"]
        if not isinstance(consumer, dict) or not set(consumer) <= _CONSUMER_KEYS:
            return False
        if "ok" in consumer and type(consumer["ok"]) is not bool:
            return False
        if any(name in consumer and not _matches(_TOKEN, consumer[name])
               for name in ("reason", "choice")):
            return False
    if "failed_checks" in result:
        checks = result["failed_checks"]
        if not isinstance(checks, list) or len(checks) > 16 or not all(_matches(_TOKEN, c) for c in checks):
            return False
    return True


def _request(op, project_id, timeout_ms, payload=None, **fields):
    try:
        _deadline(timeout_ms)
        purpose = op.partition(".")[0]
        frozen = None
        if payload is not None:
            frozen = freeze_payload(payload)
            fields["payload_b64"] = frozen.encoded
        msg = validate_message(purpose, {"v": 1, "op": op, "project_id": project_id, **fields})
        trust = load_trust()
        reply = _exchange(purpose, msg, trust, timeout_ms)
        if not isinstance(reply, dict) or type(reply.get("ok")) is not bool:
            raise AuthorityError("invalid-host-response")
        if not reply["ok"]:
            failure_fields = set(reply)
            if not _matches(_TOKEN, reply.get("reason")):
                raise AuthorityError("invalid-host-response")
            if failure_fields != {"ok","reason"}:
                # A prepared H12 always names the operation. "failed" is a
                # definite refusal; "unknown" must be reconciled before retry.
                if (op!="h12.prepare" or failure_fields!={"ok","reason","id","state"} or
                    not _matches(_ID, reply.get("id")) or reply.get("state") not in ("unknown","failed")):
                    raise AuthorityError("invalid-host-response")
            return reply
        if op == "ask.brake-read":
            # A read is a fact reply, not an operation identity and never a
            # release. Only the closed fact shape is accepted.
            facts = reply.get("facts")
            if set(reply) != {"ok", "facts"} or not isinstance(facts, dict) \
                    or set(facts) != _BRAKE_FACTS_FIELDS \
                    or type(facts["active"]) is not bool \
                    or type(facts["generation_verified"]) is not bool \
                    or facts["state"] not in ("tripped", "observing", "clear", "unknown") \
                    or (facts["reason"] is not None and not _matches(_TOKEN, facts["reason"])) \
                    or (facts["trip_id"] is not None and not _matches(_ID, facts["trip_id"])) \
                    or (facts["brake_sha256"] is not None
                        and not _matches(re.compile(r"[0-9a-f]{64}"), facts["brake_sha256"])) \
                    or (facts["ledger_seq"] is not None
                        and (type(facts["ledger_seq"]) is not int or facts["ledger_seq"] < 1)):
                raise AuthorityError("invalid-host-response")
            return reply
        if op == "ask.brake-trigger":
            if (set(reply) != _BRAKE_TRIGGER_REPLY_FIELDS
                    or not _matches(_ID, reply.get("trip_id"))
                    or reply.get("state") != "tripped"
                    or type(reply.get("created")) is not bool
                    or not _matches(re.compile(r"[0-9a-f]{64}"), reply.get("receipt_sha256"))):
                raise AuthorityError("invalid-host-response")
            return reply
        if not _matches(_ID, reply.get("id")):
            raise AuthorityError("invalid-host-response")
        if frozen:
            states=("pending","applied") if op=="h12.prepare" else ("pending",)
            if set(reply) != {"ok","id","state","sha256"} or reply["state"] not in states or reply["sha256"] != frozen.sha256:
                raise AuthorityError("draft-binding-mismatch")
        else:
            result = reply.get("result")
            if (set(reply)!={"ok","id","state","result"} or reply["id"]!=fields["id"] or
                    reply["state"] not in _RESULT_STATES.get(op, ())):
                raise AuthorityError("result-binding-mismatch")
            if reply["state"] in _EMPTY_RESULT_STATES and result is not None:
                raise AuthorityError("invalid-host-response")
            # An uncertain operation carries the host's own failure record so
            # the real reason survives. Accept only that closed failure shape.
            if (reply["state"]=="unknown" and result is not None
                    and not (op=="h12.status" and _safe_unknown_result(result))):
                raise AuthorityError("invalid-host-response")
            if op=="ask.result" and isinstance(result,dict) and "decision_id" in result:
                raise AuthorityError("invalid-host-response")
        return reply
    except AuthorityError as exc:
        return {"ok":False,"reason":exc.reason}
    except (OSError, ValueError):
        return {"ok":False,"reason":"host-unavailable"}


def submit_ask(project_id: str, payload: bytes, *, timeout_ms: int = 5000) -> dict:
    return _request("ask.submit", project_id, timeout_ms, payload=payload)


def ask_result(project_id: str, id: str, *, timeout_ms: int = 5000) -> dict:
    return _request("ask.result", project_id, timeout_ms, id=id)


def prepare_h12(project_id: str, key: str, grant_ref: str, trip_id: str, payload: bytes, *, timeout_ms: int = 5000) -> dict:
    return _request("h12.prepare", project_id, timeout_ms, payload=payload, key=key, grant_ref=grant_ref, trip_id=trip_id)


def h12_status(project_id: str, id: str, *, timeout_ms: int = 5000) -> dict:
    return _request("h12.status", project_id, timeout_ms, id=id)


def read_brake(project_id: str, *, timeout_ms: int = 5000) -> dict:
    return _request("ask.brake-read", project_id, timeout_ms)


def trigger_brake(project_id: str, payload: bytes, *, timeout_ms: int = 5000) -> dict:
    return _request("ask.brake-trigger", project_id, timeout_ms, payload=payload)

# Win32 ABI declarations live here so the ordinary CLI has no host-only dependencies.
def _signature(lib, name, result, *args):
    fn = getattr(lib, name)
    fn.argtypes = args
    fn.restype = result
    return fn


if os.name == "nt":
    import _winapi
    from contextlib import ExitStack
    import stat

    _kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    _adv = ctypes.WinDLL("advapi32", use_last_error=True)
    _shell = ctypes.WinDLL("shell32", use_last_error=True)
    _void = ctypes.c_void_p
    _p = ctypes.POINTER
    _dword = wt.DWORD
    _ulongp = _p(_dword)
    _handle = wt.HANDLE
    _phandle = _p(_handle)
    _text = wt.LPCWSTR
    _out_text = wt.LPWSTR
    _bool = wt.BOOL

    _open_process = _signature(_kernel, "OpenProcess", _handle, _dword, _bool, _dword)
    _close = _signature(_kernel, "CloseHandle", _bool, _handle)
    _times = _signature(_kernel, "GetProcessTimes", _bool, _handle, _void, _void, _void, _void)
    _image = _signature(_kernel, "QueryFullProcessImageNameW", _bool, _handle, _dword, _out_text, _ulongp)
    _thread = _signature(_kernel, "GetCurrentThread", _handle)
    _wait = _signature(_kernel, "WaitForSingleObject", _dword, _handle, _dword)
    _sid_text = _signature(_adv,"ConvertSidToStringSidW", _bool, _void, _p(_out_text))
    _local_free = _signature(_kernel, "LocalFree", _void, _void)
    _process_token = _signature(_adv, "OpenProcessToken", _bool, _handle, _dword, _phandle)
    _thread_token = _signature(_adv, "OpenThreadToken", _bool, _handle, _dword, _bool, _phandle)
    _token_info = _signature(_adv,"GetTokenInformation",_bool,_handle,ctypes.c_int,_void,_dword,_ulongp)
    _lookup = _signature(_adv,"LookupAccountNameW",_bool,_text,_text,_void,_ulongp,_out_text,_ulongp,_ulongp)
    _manager = _signature(_adv,"OpenSCManagerW",_handle,_text,_text,_dword)
    _service = _signature(_adv,"OpenServiceW",_handle,_handle,_text,_dword)
    _service_status = _signature(_adv,"QueryServiceStatusEx",_bool,_handle,ctypes.c_int,_void,_dword,_ulongp)
    _close_service = _signature(_adv,"CloseServiceHandle",_bool,_handle)
    _folder = _signature(_shell,"SHGetFolderPathW",ctypes.c_long,_handle,ctypes.c_int,_handle,_dword,_out_text)
    _server_pid = _signature(_kernel,"GetNamedPipeServerProcessId",_bool,_handle,_ulongp)
    _client_pid = _signature(_kernel,"GetNamedPipeClientProcessId",_bool,_handle,_ulongp)
    _as_client = _signature(_adv,"ImpersonateNamedPipeClient",_bool,_handle)
    _revert = _signature(_adv,"RevertToSelf",_bool)
    _security = _signature(_adv,"GetSecurityInfo",_dword,_handle,ctypes.c_int,_dword,
                           _phandle,_phandle,_phandle,_phandle,_phandle)
    _get_ace = _signature(_adv,"GetAce",_bool,_void,_dword,_phandle)
    _descriptor = _signature(_adv,"ConvertStringSecurityDescriptorToSecurityDescriptorW",_bool,
                             _text,_dword,_phandle,_ulongp)

    class _SecurityAttributes(ctypes.Structure):
        _fields_ = [("length",_dword),("descriptor",_void),("inherit",_bool)]


def _require(ok, reason="identity-unverifiable"):
    if not ok:
        raise AuthorityError(reason)


def _sid(raw):
    out = _out_text()
    _require(_sid_text(raw, ctypes.byref(out)))
    try:
        return out.value
    finally:
        _local_free(ctypes.cast(out, _void))


def _token_identity(handle):
    size = _dword()
    _token_info(handle, 1, None, 0, ctypes.byref(size))  # TokenUser
    _require(0 < size.value <= 65536)
    buf = ctypes.create_string_buffer(size.value)
    _require(_token_info(handle, 1, buf, len(buf), ctypes.byref(size)))
    sid = _sid(_void.from_buffer(buf).value)
    session = _dword()
    _require(_token_info(handle, 12, ctypes.byref(session), ctypes.sizeof(session), ctypes.byref(size)))
    return sid, session.value


def _process_peer(pid, stack):
    process = _open_process(0x101000, False, pid)  # SYNCHRONIZE | QUERY_LIMITED_INFORMATION
    _require(process)
    stack.callback(_close,process)
    _require(_wait(process,0) == 258)  # WAIT_TIMEOUT: the pinned process is still live
    token = _handle()
    _require(_process_token(process,8,ctypes.byref(token)))
    stack.callback(_close,token)
    sid,session=_token_identity(token)
    creation,exit_time,kernel,user=(ctypes.c_uint64() for _ in range(4))
    _require(_times(process,*(ctypes.byref(t) for t in (creation,exit_time,kernel,user))))
    size=_dword(32768)
    image=ctypes.create_unicode_buffer(size.value)
    _require(_image(process,0,image,ctypes.byref(size)))
    # FILETIME is UTC in 100 ns ticks since 1601. Publish a Unix timestamp.
    return Peer(sid,pid,(creation.value-116444736000000000)*100,session,os.path.normcase(image.value))


def _account_sid(name):
    n, domain_n, use = _dword(), _dword(), _dword()
    _lookup(None,name,None,ctypes.byref(n),None,ctypes.byref(domain_n),ctypes.byref(use))
    _require(0 < n.value <= 256 and domain_n.value <= 1024)
    raw = ctypes.create_string_buffer(n.value)
    domain = ctypes.create_unicode_buffer(max(1,domain_n.value))
    _require(_lookup(None,name,raw,ctypes.byref(n),domain,ctypes.byref(domain_n),ctypes.byref(use)))
    return _sid(raw)


def _checked_acl(handle, trusted, target, *, service=False):
    owner,acl,descriptor=_handle(),_handle(),_handle()
    code=_security(handle,5 if service else 1,0x5,ctypes.byref(owner),None,ctypes.byref(acl),None,ctypes.byref(descriptor))
    _require(code==0 and descriptor.value, "untrusted-path")
    try:
        _require(acl.value and owner.value and _sid(owner) in trusted,"untrusted-path")
        # ACL header: revision, sbz, size, AceCount, sbz; ACE layout is
        # type/flags/size/mask/SID. Refuse unrecognized granting ACE forms.
        count=ctypes.c_ushort.from_address(acl.value+4).value
        mutation=0x500D0150  # GENERIC_ALL/WRITE, DELETE, WRITE_DAC/OWNER, DELETE_CHILD, write attributes/EA
        if target:
            mutation |= 0x6  # file write/append; adding a directory entry at the target
        if service:
            mutation = 0x500D0002  # service CHANGE_CONFIG, DELETE, WRITE_DAC/OWNER, generic write/all
        for i in range(count):
            ace=_handle()
            _require(_get_ace(acl,i,ctypes.byref(ace)),"untrusted-path")
            typ=ctypes.c_ubyte.from_address(ace.value).value
            flags=ctypes.c_ubyte.from_address(ace.value+1).value
            if flags & 8 or typ==1:  # inherit-only or denied
                continue
            _require(typ==0,"untrusted-path")
            mask=ctypes.c_uint32.from_address(ace.value+4).value
            if mask & mutation:
                _require(_sid(ace.value+8) in trusted,"untrusted-path")
    finally:
        _local_free(descriptor)


def trusted_path(path, trust: ServiceTrust, *, directory=False) -> Path:
    """Read-only ACL check, including substitution/deletion of ancestors."""
    if os.name != "nt":
        raise AuthorityError("host-unavailable")
    candidate=Path(path)
    if not candidate.is_absolute() or candidate.drive.startswith("\\\\") or ".." in candidate.parts or any(":" in p for p in candidate.parts[1:]):
        raise AuthorityError("untrusted-path")
    trusted={"S-1-5-18","S-1-5-32-544",trust.peer.sid,
             "S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464"}  # TrustedInstaller
    try:
        with ExitStack() as handles:
            for item in (*reversed(candidate.parents),candidate):
                # OPEN_REPARSE_POINT and no FILE_SHARE_DELETE while checking the chain.
                h=_winapi.CreateFile(str(item),0x20080,3,0,3,0x02200000,0)
                handles.callback(_close,h)
                entry=item.lstat()
                _require(not entry.st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,"untrusted-path")
                _require(item.is_dir() if item!=candidate or directory else item.is_file(),"untrusted-path")
                _checked_acl(h,trusted,item==candidate)
        return candidate
    except (OSError,ValueError) as exc:
        if isinstance(exc,AuthorityError):
            raise
        raise AuthorityError("untrusted-path") from None


def _service_state_allows_trust(state: int) -> bool:
    """SCM states in which this process is the live registered service.

    ``SERVICE_START_PENDING`` is required: ServiceMain must read the protected
    configuration and TLS material after it reports start-pending but before it
    is allowed to report running. Only the own-process service PID/SID/creation
    time and protected paths establish identity; the state adds no caller input.
    """
    return state in (2, 4)  # SERVICE_START_PENDING | SERVICE_RUNNING


def load_trust() -> ServiceTrust:
    """Resolve only the fixed, local SCM own-process service and its virtual account."""
    if os.name != "nt":
        # The deployment mechanism itself does not exist off Windows; a mocked
        # anchor still takes precedence because callers patch this function.
        raise ServiceNotDeployed()
    with ExitStack() as handles:
        manager=_manager(None,None,1)
        _require(manager,"host-unavailable")
        handles.callback(_close_service,manager)
        service=_service(manager,SERVICE_NAME,0x20004)
        if not service:
            # Only the SCM's own code proves the service is not installed. An
            # access denied / API failure is unknown, never "unmanaged".
            _require(ctypes.get_last_error() == ERROR_SERVICE_DOES_NOT_EXIST,
                     "host-unavailable")
            raise ServiceNotDeployed()
        handles.callback(_close_service,service)
        status=(_dword*9)()
        size=_dword()
        _require(_service_status(service,0,status,ctypes.sizeof(status),ctypes.byref(size)),"host-unavailable")
        _require(status[0]==0x10 and _service_state_allows_trust(status[1]) and status[7]>0,"host-unavailable")
        expected=_account_sid("NT SERVICE\\"+SERVICE_NAME)
        _checked_acl(service,{"S-1-5-18","S-1-5-32-544"},False,service=True)
        peer=_process_peer(status[7],handles)
        _require(peer.sid==expected and peer.session_id==0,"host-identity-mismatch")
        common=ctypes.create_unicode_buffer(260)
        _require(_folder(None,0x23,None,0,common)==0,"untrusted-path")  # CSIDL_COMMON_APPDATA
        trust=ServiceTrust(peer,Path(common.value)/"MultiWorkers"/"OperatorHost"/"host.json")
        trusted_path(peer.image,trust)
        trusted_path(trust.config_path,trust)
        return trust


def _win_peer(pipe, *, server, stack):
    pid=_dword()
    _require((_server_pid if server else _client_pid)(pipe,ctypes.byref(pid)))
    return _process_peer(pid.value,stack)


def _io_result(ov, end, *, already_connected=False):
    try:
        if _winapi.WaitForSingleObject(ov.event,_remaining(end)) != 0:
            raise AuthorityError("host-timeout")
        count,error=ov.GetOverlappedResult(False)
        if error==996 and already_connected:
            # GetOverlappedResult cannot see a ConnectNamedPipe that the
            # kernel completed immediately as ERROR_PIPE_CONNECTED; the
            # client is already on this instance, so there is nothing to wait
            # for. No request bytes exist at this point.
            return 0
        while error==996:
            # ERROR_IO_INCOMPLETE: the completion event can be signalled a
            # little before the kernel records the result. Keep waiting for
            # the actual completion inside the same caller deadline.
            if _winapi.WaitForSingleObject(ov.event,_remaining(end))!=0:
                raise AuthorityError("host-timeout")
            count,error=ov.GetOverlappedResult(False)
        # A client that reaches the name between CreateNamedPipe and
        # ConnectNamedPipe makes the latter report ERROR_PIPE_CONNECTED; the
        # instance is usable and no bytes have been exchanged yet.
        _require(error==0 or (already_connected and error==535),"invalid-frame")
        return count
    except BaseException:
        ov.cancel()
        ov.GetOverlappedResult(True)
        raise


def _receive(pipe,end):
    ov,_=_winapi.ReadFile(pipe,MAX_FRAME+1,overlapped=True)
    count=_io_result(ov,end)
    _require(0<count<=MAX_FRAME,"invalid-size")
    return bytes(ov.getbuffer())[:count]


def _send(pipe,body,end):
    _require(0<len(body)<=MAX_FRAME,"invalid-size")
    ov,_=_winapi.WriteFile(pipe,body,overlapped=True)
    _require(_io_result(ov,end)==len(body),"invalid-frame")


def _encoded(message):
    try:
        data=json.dumps(message,ensure_ascii=False,allow_nan=False,separators=(",",":")).encode("utf-8")
    except (UnicodeError,ValueError,TypeError,RecursionError):
        raise AuthorityError("invalid-frame") from None
    _require(0<len(data)<=MAX_FRAME,"invalid-size")
    return data


def _connect(endpoint,end):
    """Open one service instance before any request bytes exist.

    A pipe name has no listener during service start and between the
    short-lived instances of a serving loop. Windows reports that window as
    FILE_NOT_FOUND, ERROR_PIPE_NOT_CONNECTED or a busy instance as
    ERROR_PIPE_BUSY; none is an exhausted request. Retry only the open, always
    against the one caller deadline, and never after an instance has been
    reached: the caller checks the kernel peer identity before sending, so a
    wrong service is final.
    """
    delay=0.005
    while True:
        remaining=_remaining(end)
        try:
            _winapi.WaitNamedPipe(endpoint,min(remaining,1000))
        except OSError as exc:
            if exc.winerror not in (2,121,231,233):  # FILE_NOT_FOUND, WAIT_TIMEOUT, BUSY, NOT_CONNECTED
                raise
        try:
            # Identification SQOS prevents the service from acting as this user.
            return _winapi.CreateFile(endpoint,0x100103,0,0,3,0x40110000,0)
        except OSError as exc:
            if exc.winerror not in (2,121,231,233):
                raise
        pause=min(delay,max(0.0,end-time.monotonic()))
        if pause<=0:
            raise AuthorityError("host-timeout")
        time.sleep(pause)
        delay=min(delay*2,0.05)


def _exchange(purpose,msg,trust,timeout_ms):
    end=_deadline(timeout_ms)
    if os.name!="nt":
        raise AuthorityError("host-unavailable")
    try:
        with ExitStack() as handles:
            endpoint=PIPES[purpose]
            pipe=_connect(endpoint,end)
            handles.callback(_close,pipe)
            _require(_win_peer(pipe,server=True,stack=handles)==trust.peer,"host-identity-mismatch")
            # Read mode must be message mode to preserve bounds and reject oversized frames.
            _winapi.SetNamedPipeHandleState(pipe,2,None,None)
            _send(pipe,_encoded(msg),end)
            reply=_object(_receive(pipe,end),MAX_FRAME)
            _send(pipe,b"\x06",end)  # complete receipt before server closes the channel
            return reply
    except OSError:
        raise AuthorityError("host-unavailable") from None


def _serve_connected(pipe,purpose,handler,end):
    with ExitStack() as handles:
        peer=_win_peer(pipe,server=False,stack=handles)
        raw=_receive(pipe,end)
        # The kernel authenticates the token of the last message on this pipe.
        # Also bind the pinned process's identity; no field from JSON identifies a peer.
        _require(_as_client(pipe),"client-identity-mismatch")
        try:
            token=_handle()
            _require(_thread_token(_thread(),8,True,ctypes.byref(token)),"client-identity-mismatch")
            with ExitStack() as tokens:
                tokens.callback(_close,token)
                _require(_token_identity(token)==(peer.sid,peer.session_id),"client-identity-mismatch")
        finally:
            if not _revert():
                # A service must never continue dispatch under an impersonated token.
                os._exit(1)
        try:
            message=validate_message(purpose,_object(raw,MAX_FRAME))
            result=handler(peer,message)
        except AuthorityError as exc:
            result={"ok":False,"reason":exc.reason}
        _send(pipe,_encoded(result),end)
        _require(_receive(pipe,end)==b"\x06","missing-response-ack")


def serve_one(purpose,handler,*,trust,timeout_ms=5000,allowed_sids=()):
    """Serve one local connection as the live registered service only.

    The protected host must separately enforce registration, current claim,
    revocation and atomic consumption in handler. This transport grants none.
    """
    if os.name!="nt" or purpose not in PIPES:
        raise AuthorityError("host-unavailable")
    end=_deadline(timeout_ms)
    fresh=load_trust()
    _require(fresh==trust and os.getpid()==trust.peer.pid,"host-identity-mismatch")
    if purpose=="h12":
        _require(isinstance(allowed_sids,(tuple,list)) and 0<len(allowed_sids)<=64 and
                 all(_matches(_SID,sid) for sid in allowed_sids),"missing-controlled-peer")
        clients=allowed_sids
    else:
        clients=("AU",)
    sd="D:P(A;;GA;;;SY)(A;;GA;;;"+trust.service_sid+")"+"".join(
        "(A;;0x100103;;;"+s+")" for s in clients)
    # FILE_WRITE_ATTRIBUTES is needed to select PIPE_READMODE_MESSAGE. Do not
    # grant FILE_APPEND_DATA / FILE_CREATE_PIPE_INSTANCE to these clients.
    descriptor=_handle()
    _require(_descriptor(sd,1,ctypes.byref(descriptor),None),"invalid-pipe-dacl")
    with ExitStack() as handles:
        handles.callback(_local_free,descriptor)
        sa=_SecurityAttributes(ctypes.sizeof(_SecurityAttributes),descriptor,False)
        pipe=_winapi.CreateNamedPipe(PIPES[purpose],0x40080003,0x0E,1,65536,65536,timeout_ms,ctypes.addressof(sa))
        handles.callback(_close,pipe)
        ov=_winapi.ConnectNamedPipe(pipe,overlapped=True)
        _io_result(ov,end,already_connected=True)
        _serve_connected(pipe,purpose,handler,end)


@dataclass(frozen=True)
class AuthoritySource:
    records: Mapping[str, decision_policy.AuthorityRecord]
    trusted_writers: tuple[str, ...]


def registered_project(project_id: str) -> bool:
    """Whether the fixed protected deployment config registers this project.

    This is a read of the deployed registration source, never a local
    ``enrolled=true`` flag. Unknown/invalid config raises, so a caller cannot
    turn a bad binding into "unregistered".
    """
    trust = load_trust()
    path = trusted_path(trust.config_path, trust)
    raw = path.read_bytes()
    cfg = _object(raw, MAX_PAYLOAD)
    projects = cfg.get("projects")
    if not isinstance(projects, dict):
        raise AuthorityError("invalid-config")
    return isinstance(project_id, str) and project_id in projects


def read_authority_source(trust: ServiceTrust, project_id: str) -> AuthoritySource:
    """Read T07's independent policy authorizations; never mint or cache one."""
    _require(_matches(_PROJECT,project_id),"bad-binding")
    fresh=load_trust()
    _require(trust==fresh and os.getpid()==fresh.peer.pid,"host-identity-mismatch")
    target=trusted_path(fresh.config_path,fresh)
    try:
        with target.open("rb") as fp:
            config=_object(fp.read(MAX_PAYLOAD+1),MAX_PAYLOAD)
        project=config["projects"][project_id]
        writers=project["trusted_writers"]
        rows=project["authority_records"]
    except (OSError,KeyError,TypeError):
        raise AuthorityError("authority-unavailable") from None
    _require(isinstance(writers,list) and writers and all(_matches(_TOKEN,w) for w in writers)
             and isinstance(rows,dict),"invalid-authority-source")
    records={}
    for ref,row in rows.items():
        item,issues=decision_policy.parse_authority_record(row,trusted_writers=writers)
        _require(item is not None and not issues and item.authority_ref==ref,"invalid-authority-source")
        records[ref]=item
    return AuthoritySource(MappingProxyType(records),tuple(writers))


# ---------------------------------------------------------------------------
# Read-only PM authority source adapter
# ---------------------------------------------------------------------------
#
# ``read_authority_source`` above is deliberately service-only: it re-reads
# the SCM own-process identity and refuses to run anywhere else. A normally
# claimed PM therefore can never resolve the authority records of its own
# protected deployment, even when a valid ``host.json`` already exists.
#
# ``read_pm_authority`` is the minimal read-only adapter for that caller. It
# keeps the same fixed SCM trust anchor and protected-path/ACL/reparse chain,
# derives the project id from the caller's real path, and requires the actual
# live PM claim of this process (or of its direct parent bridge, the existing
# T19 convention). It reuses the deployed ``pm_sids``/``pm_images`` and the
# original T07 authority records. It mints, signs, grants and writes nothing;
# the returned value is an observation, not a bearer ticket, and every consumer
# must call :func:`verify_pm_authority` (or re-read) immediately before use.

_PM_KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}\Z")
_PM_HASH = re.compile(r"[0-9a-f]{64}\Z")
_MAX_CONFIG = MAX_PAYLOAD
_USAGE_FIELDS = {"kind", "unit"}


@dataclass(frozen=True)
class UsageSource:
    """One declared cumulative usage source, as protected config describes it.

    The descriptor names where cumulative usage comes from; it never carries a
    numeric budget, and no budget is inferred from ``round_budget`` or
    ``worker_timeout_min``.
    """

    kind: str
    unit: str


@dataclass(frozen=True)
class PmAuthority:
    """Immutable, read-only observation of one project's original authority.

    This is data, not a capability. It contains no token, no signature and no
    writing method, and it is only valid for the exact project/key/claim it
    names. Re-read (or :func:`verify_pm_authority`) before consuming.
    """

    project_id: str
    project_root: Path
    key: str
    claim_id: str
    policy_sha256: str
    trusted_writers: tuple[str, ...]
    records: Mapping[str, decision_policy.AuthorityRecord]
    usage_sources: Mapping[str, UsageSource]


def _pm_project_root(project_root: object) -> Path:
    _require(isinstance(project_root, (str, os.PathLike)) and not isinstance(project_root, bytes),
             "invalid-project-root")
    raw = os.fspath(project_root)
    _require(isinstance(raw, str) and raw and "\x00" not in raw, "invalid-project-root")
    candidate = Path(os.path.realpath(os.path.abspath(raw)))
    _require(candidate.is_absolute() and candidate.is_dir(), "invalid-project-root")
    return candidate


def _pm_process_peer(pid: int) -> Peer:
    probe = globals().get("_process_peer")
    _require(probe is not None, "host-unavailable")
    with ExitStack() as handles:
        return probe(pid, handles)


def _pm_config_root(config_path: Path, value: object) -> Path:
    _require(isinstance(value, str) and value and "\x00" not in value, "invalid-authority-source")
    declared = Path(value)
    if not declared.is_absolute():
        declared = config_path.parent / declared
    declared = Path(os.path.normpath(str(declared)))
    # The protected deployment keeps project roots inside the protected tree;
    # a config that points elsewhere is not this reader's source.
    _require(declared.is_absolute() and declared.is_relative_to(config_path.parent),
             "untrusted-path")
    return declared


def read_pm_authority(project_root: object, key: object) -> PmAuthority:
    """Read the protected deployment's original authority for a live PM.

    Returns an immutable typed observation of ``authority_records``,
    ``trusted_writers``, ``policy_sha256`` and the declared ``usage_sources``
    descriptors. The caller cannot pass a trust/config path, records, writers,
    usage numbers or a role: all of them come from the fixed protected config
    and the real OS process/claim. Nothing is minted, signed or written, and no
    TLS key, database or other user data is opened.

    Raises :class:`AuthorityError` with a concrete reason when no real source
    exists or the current identity does not own the claim.
    """
    _require(isinstance(key, str) and _matches(_PM_KEY, key), "bad-binding")
    candidate = _pm_project_root(project_root)
    _require(not os.environ.get("PI_WORKER_TASK"), "pm-worker-not-pm")
    # Imported lazily in this order: an ordinary MW side import must not create
    # the decision_wire/mw_common bootstrap cycle for this read-only module.
    import mw_common
    import decision_wire
    from autopilot import state as mw_state

    # Same fixed SCM SID/PID/creation/session anchor, protected host.json path
    # and ancestor ACL/reparse chain as the service-only reader.
    trust = load_trust()
    _require(trust.peer.pid > 0 and trust.peer.sid and trust.peer.created_ns > 0,
             "host-identity-mismatch")
    config_path = trusted_path(trust.config_path, trust)
    try:
        raw = config_path.read_bytes()
    except PermissionError:
        raise AuthorityError("authority-source-unreadable") from None
    except OSError:
        raise AuthorityError("authority-source-unavailable") from None
    _require(0 < len(raw) <= _MAX_CONFIG, "invalid-authority-source")
    try:
        config = _object(raw, _MAX_CONFIG)
    except AuthorityError:
        raise AuthorityError("invalid-authority-source") from None
    _require(config.get("schema") == 1, "invalid-authority-source")
    projects = config.get("projects")
    _require(isinstance(projects, dict), "invalid-authority-source")

    # The id must hash from this caller's real current path, and the configured
    # root must resolve to exactly that path. A snapshot of another path is not
    # this project's source.
    project_id = decision_wire.project_id_for(candidate)
    row = projects.get(project_id)
    _require(isinstance(row, dict), "project-unregistered")
    declared = _pm_config_root(config_path, row.get("root"))
    _require(Path(os.path.realpath(declared)) == candidate, "project-binding-mismatch")

    pm_sids = row.get("pm_sids")
    pm_images = row.get("pm_images")
    _require(isinstance(pm_sids, list) and pm_sids
             and all(_matches(_SID, sid) for sid in pm_sids), "invalid-authority-source")
    _require(isinstance(pm_images, list) and pm_images
             and all(isinstance(image, str) and image and "\x00" not in image
                     for image in pm_images), "invalid-authority-source")

    # Actual live PM claim: one active row for this key, claimed by this very
    # process or by its direct non-worker bridge parent (T19 convention).
    rows = [item for item in mw_state.read_index(candidate) if item.get("key") == key]
    _require(len(rows) == 1 and rows[0].get("status") == "active", "pm-claim-unbound")
    claim_id = rows[0].get("claim_id") or ""
    synthetic = mw_common.parse_synthetic_claim(claim_id)
    identity = f"{synthetic[0]}:{synthetic[1]}" if synthetic else claim_id
    host = socket.gethostname()
    local = {f"{host}:{os.getpid()}", f"{host}:{os.getppid()}"}
    _require(identity in local, "pm-claim-unbound")
    _require(mw_state.claim_state(claim_id) == mw_state.CLAIM_LIVE, "pm-claim-unbound")
    claimed_pid = int(identity.rpartition(":")[2])
    _require(claimed_pid in (os.getpid(), os.getppid()), "pm-claim-unbound")

    # The OS process that owns the claim (never a Worker, another window, a
    # restarted PID or a process outside the registered SID/image set).
    peer = _pm_process_peer(claimed_pid)
    _require(peer.pid == claimed_pid and peer.created_ns > 0, "pm-peer-untrusted")
    _require(peer.sid in pm_sids, "pm-peer-untrusted")
    images = {os.path.normcase(os.path.normpath(image)) for image in pm_images}
    _require(os.path.normcase(os.path.normpath(peer.image)) in images, "pm-peer-untrusted")

    writers = row.get("trusted_writers")
    _require(isinstance(writers, list) and writers
             and all(_matches(_TOKEN, writer) for writer in writers), "invalid-authority-source")
    trusted_writers = tuple(writers)

    raw_records = row.get("authority_records")
    _require(isinstance(raw_records, dict), "invalid-authority-source")
    records: dict[str, decision_policy.AuthorityRecord] = {}
    for ref, payload in raw_records.items():
        _require(isinstance(ref, str) and _matches(_TOKEN, ref), "invalid-authority-source")
        parsed, issues = decision_policy.parse_authority_record(payload,
                                                                trusted_writers=trusted_writers)
        _require(parsed is not None and not issues and parsed.authority_ref == ref,
                 "invalid-authority-source")
        records[ref] = parsed

    raw_usage = row.get("usage_sources", {})
    _require(isinstance(raw_usage, dict), "invalid-usage-source")
    usage_sources: dict[str, UsageSource] = {}
    for name, description in raw_usage.items():
        _require(isinstance(name, str) and _matches(_TOKEN, name), "invalid-usage-source")
        _require(isinstance(description, dict) and set(description) == _USAGE_FIELDS
                 and all(isinstance(description[field], str)
                         and _matches(_TOKEN, description[field])
                         for field in ("kind", "unit")), "invalid-usage-source")
        # Self-reported or config-knob "metering" is not a cumulative source and
        # would otherwise be guessed into a hard budget.
        _require(description["kind"] not in decision_policy.NON_AUTHORITATIVE_ORIGINS,
                 "invalid-usage-source")
        _require(description["unit"] not in decision_policy.FROZEN_CONFIG_UNITS,
                 "invalid-usage-source")
        usage_sources[name] = UsageSource(description["kind"], description["unit"])

    policy_sha256 = row.get("policy_sha256", "")
    _require(policy_sha256 == "" or (isinstance(policy_sha256, str)
                                      and _matches(_PM_HASH, policy_sha256)),
             "invalid-authority-source")
    if policy_sha256:
        # A pinned version must still be the version actually on disk.
        try:
            policy_raw = decision_policy.policy_path(candidate).read_bytes()
        except OSError:
            raise AuthorityError("policy-version-changed") from None
        _require(hashlib.sha256(policy_raw).hexdigest() == policy_sha256,
                 "policy-version-changed")

    return PmAuthority(
        project_id=project_id,
        project_root=candidate,
        key=key,
        claim_id=claim_id,
        policy_sha256=policy_sha256,
        trusted_writers=trusted_writers,
        records=MappingProxyType(dict(records)),
        usage_sources=MappingProxyType(dict(usage_sources)),
    )


def reread_pm_authority(observation: PmAuthority) -> PmAuthority:
    """Re-read the same project/key/claim from OS + protected config.

    The returned object is a fresh observation. An old observation is never a
    reusable bearer: the identity fields must still match, otherwise the source
    changed under the caller.
    """
    _require(isinstance(observation, PmAuthority), "invalid-observation")
    fresh = read_pm_authority(observation.project_root, observation.key)
    _require(fresh.project_id == observation.project_id
             and fresh.project_root == observation.project_root
             and fresh.key == observation.key
             and fresh.claim_id == observation.claim_id,
             "authority-source-changed")
    return fresh


def verify_pm_authority(observation: PmAuthority) -> PmAuthority:
    """Re-read before consumption and refuse if any observed fact changed."""
    fresh = reread_pm_authority(observation)
    _require(fresh.policy_sha256 == observation.policy_sha256
             and fresh.trusted_writers == observation.trusted_writers
             and dict(fresh.records) == dict(observation.records)
             and dict(fresh.usage_sources) == dict(observation.usage_sources),
             "authority-source-changed")
    return fresh
