"""Offline contract for the local operator boundary. No project or service is registered.

The real WebAuthn checks use the project's optional, full-hash-pinned wheels from
the evidence cache extracted into a temporary directory. No network, real
authenticator, provider credential, Windows service or project is touched.
"""
from __future__ import annotations

import atexit
import base64
import hashlib
import json
import os
import pathlib
import shutil
import sys
import tempfile
import zipfile

import pytest

import operator_authority as oa

PROJECT = "1234567890abcdef"
ID = "8ca6db02878f4378ad9d2fcef3906d0a"
BODY = b'{ "question": "review this exact text" }'
HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[1]
CACHE = ROOT / ".agenticdoc/mw-dp-consolidation/evidence/implementation/dpc-operator-host/cache"
LOCK = HERE / "requirements-operator-host.lock"
_TRIP = "0123456789abcdef0123456789abcdef"
_KEY = "dpc-fixture-key"


def _locked_versions() -> dict[str, tuple[str, str]]:
    rows = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, rest = line.partition("==")
        version, _, digest = rest.partition(" --hash=sha256:")
        assert name and version and len(digest) == 64, line
        rows[name] = (version, digest)
    return rows


def _load_optional_runtime() -> bool:
    try:
        import fido2.server  # noqa: F401
        return True
    except ImportError:
        pass
    locked = _locked_versions()
    wheels = {path.name.split("-")[0]: path for path in CACHE.glob("*.whl")} if CACHE.is_dir() else {}
    if not wheels:
        return False
    target = tempfile.mkdtemp(prefix="mw-operator-deps-")
    atexit.register(shutil.rmtree, target, ignore_errors=True)
    for name, path in wheels.items():
        version, digest = locked[name]
        assert path.name.startswith(f"{name}-{version}-"), path.name
        assert hashlib.sha256(path.read_bytes()).hexdigest() == digest, path.name
        if name in {"fido2", "cryptography", "cffi", "pycparser"}:
            with zipfile.ZipFile(path) as archive:
                archive.extractall(target)
    sys.path.insert(0, target)
    try:
        import fido2.server  # noqa: F401
        return True
    except ImportError:
        return False


FIDO = _load_optional_runtime()
if FIDO:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID
    from fido2.cose import ES256
    from fido2.utils import websafe_encode
    from fido2.webauthn import AttestedCredentialData, AuthenticatorData, CollectedClientData

import operator_host as host  # noqa: E402
import decision_wire  # noqa: E402


def test_frozen_payload_keeps_exact_utf8_and_refuses_ambiguous_json():
    frozen = oa.freeze_payload(BODY)
    assert frozen.raw == BODY
    assert oa.decode_payload(frozen.encoded) == frozen
    assert oa.freeze_payload(BODY + b" ").sha256 != frozen.sha256
    for body in (b'{"x":1,"x":2}', b'{"n":NaN}', b'{"s":"\\ud800"}', b'[]', b'\xff', b'{', b' ' * (oa.MAX_PAYLOAD + 1)):
        with pytest.raises(oa.AuthorityError):
            oa.freeze_payload(body)
    for value in ("%%%%", base64.b64encode(BODY).decode() + "\n", 1):
        with pytest.raises(oa.AuthorityError):
            oa.decode_payload(value)


def test_separate_pipes_refuse_mixed_purposes_and_client_asserted_identity():
    ask = {"v": 1, "op": "ask.submit", "project_id": PROJECT, "payload_b64": oa.freeze_payload(BODY).encoded}
    assert oa.validate_message("ask", ask) == ask
    for op in ("h12.prepare", "grant.sign", "ask.confirm", "revoke", "register"):
        with pytest.raises(oa.AuthorityError):
            oa.validate_message("ask", {**ask, "op": op})
    for field in ("sid", "peer", "origin", "trusted_writers", "project", "executor", "accepted"):
        with pytest.raises(oa.AuthorityError):
            oa.validate_message("ask", {**ask, field: "ordinary"})
    with pytest.raises(oa.AuthorityError):
        oa.validate_message("h12", ask)


def test_no_registration_or_wrong_endpoint_never_receives_payload(monkeypatch):
    recorded = []

    def missing():
        raise oa.AuthorityError("host-unavailable")

    monkeypatch.setattr(oa, "load_trust", missing)
    monkeypatch.setattr(oa, "_exchange", lambda *args: recorded.append(args))
    assert oa.submit_ask(PROJECT, BODY) == {"ok": False, "reason": "host-unavailable"}
    assert not oa.prepare_h12(PROJECT, "mw-key", ID, "trip-1", BODY)["ok"]
    assert not recorded
    assert not oa.submit_ask("../project", BODY)["ok"]


def test_server_must_acknowledge_original_fingerprint_and_operation_identity(monkeypatch):
    monkeypatch.setattr(oa, "load_trust", lambda: object())
    frozen = oa.freeze_payload(BODY)

    def exchange(purpose, msg, trust, timeout_ms):
        assert purpose == "ask" and oa.decode_payload(msg["payload_b64"]) == frozen
        return {"ok": True, "state": "pending", "id": ID, "sha256": frozen.sha256}

    monkeypatch.setattr(oa, "_exchange", exchange)
    assert oa.submit_ask(PROJECT, BODY)["id"] == ID
    for reply in ({"ok": True, "state": "pending", "id": ID, "sha256": "0" * 64},
                  {"ok": True, "state": "pending", "id": "wrong", "sha256": frozen.sha256},
                  {"ok": True, "state": "pending", "id": ID, "sha256": frozen.sha256, "decision_id": "spoof"}):
        monkeypatch.setattr(oa, "_exchange", lambda *args: reply)
        assert not oa.submit_ask(PROJECT, BODY)["ok"]


def test_result_query_is_bound_to_same_id_and_cannot_mint_a_decision(monkeypatch):
    monkeypatch.setattr(oa, "load_trust", lambda: object())
    base = {"ok": True, "id": ID, "state": "applied", "result": {"display": "answer"}}
    monkeypatch.setattr(oa, "_exchange", lambda *args: base)
    assert oa.ask_result(PROJECT, ID) == base
    for reply in ({**base, "id": "a" * 32}, {**base, "state": "pending"}, {**base, "result": {"decision_id": "fake"}}):
        monkeypatch.setattr(oa, "_exchange", lambda *args: reply)
        assert not oa.ask_result(PROJECT, ID)["ok"]


def test_read_only_policy_source_is_reloaded_and_revocation_is_visible(monkeypatch, tmp_path):
    import os

    cfg = tmp_path / "host.json"
    trust = oa.ServiceTrust(oa.Peer("fixture", os.getpid(), 1, 0, "fixture-service"), cfg)
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    monkeypatch.setattr(oa, "trusted_path", lambda path, *_: path)
    record = {"authority_ref": "original", "kind": "preauthorization", "scope": ["recovery:breaker"], "writer": "trusted"}
    cfg_data = {"projects": {PROJECT: {"trusted_writers": ["trusted"], "authority_records": {"original": record}}}}
    import decision_policy

    record["kind"] = next(iter(sorted(decision_policy.AUTHORITY_KINDS)))
    cfg.write_text(json.dumps(cfg_data), encoding="utf-8")
    authority = oa.read_authority_source(trust, PROJECT)
    assert authority.records["original"].authority_ref == "original"
    with pytest.raises(TypeError):
        authority.records["fake"] = "fake"
    record["revoked"] = True
    cfg.write_text(json.dumps(cfg_data), encoding="utf-8")
    assert oa.read_authority_source(trust, PROJECT).records["original"].revoked
    record["writer"] = "ordinary"
    cfg.write_text(json.dumps(cfg_data), encoding="utf-8")
    with pytest.raises(oa.AuthorityError):
        oa.read_authority_source(trust, PROJECT)


@pytest.mark.skipif(oa.os.name != "nt", reason="requires the Windows named-pipe kernel")
def test_windows_local_pipe_checks_both_ends_and_carries_real_original_bytes(monkeypatch, tmp_path):
    import threading
    import uuid

    # Only this randomized ephemeral pipe is created, under this test process's
    # own SID. No service, deployment registration or production grant is touched.
    with oa.ExitStack() as handles:
        identity = oa._process_peer(os.getpid(), handles)
    assert identity.pid == os.getpid() and identity.sid.startswith("S-1-")
    trust = oa.ServiceTrust(identity, tmp_path / "unused")
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    monkeypatch.setitem(oa.PIPES, "ask", r"\\.\pipe\MW.test." + uuid.uuid4().hex)
    ready = threading.Event()
    real_connect = oa._winapi.ConnectNamedPipe

    def connecting(*args, **kw):
        ready.set()
        return real_connect(*args, **kw)

    monkeypatch.setattr(oa._winapi, "ConnectNamedPipe", connecting)
    received = []
    failed = []

    def handle(peer, msg):
        received.append((peer, oa.decode_payload(msg["payload_b64"]).raw))
        return {"ok": True, "id": ID, "state": "pending", "sha256": oa.freeze_payload(BODY).sha256}

    def server():
        try:
            oa.serve_one("ask", handle, trust=trust, timeout_ms=3000)
        except Exception as exc:
            failed.append(repr(exc))

    worker = threading.Thread(target=server)
    worker.start()
    assert ready.wait(3), failed
    reply = oa.submit_ask(PROJECT, BODY, timeout_ms=2000)
    worker.join(4)
    assert not worker.is_alive()
    assert not failed, (failed, reply)
    assert reply["ok"] and received == [(identity, BODY)]


def test_ordinary_import_and_self_constructed_context_cannot_be_the_service(monkeypatch, tmp_path):
    # A locally created context frame, including a 'successful' injected verifier.
    # The fixed SCM service still belongs to a different process.
    monkeypatch.setattr(oa, "load_trust", lambda: oa.ServiceTrust(
        oa.Peer("fixture", os.getpid() + 1, 1, 0, "other-service"), tmp_path / "unused"))
    token = host._CALL.set((tmp_path, "ask", BODY, None, lambda *_: True))
    try:
        assert not host.authorized_callback(tmp_path, "ask", BODY)
    finally:
        host._CALL.reset(token)


@pytest.mark.skipif(oa.os.name != "nt", reason="requires the Windows named-pipe kernel")
@pytest.mark.parametrize("changed", ["created_ns", "sid", "session_id", "image", "pid"])
def test_false_server_reads_no_draft_even_if_it_squats_on_the_pipe_name(changed, monkeypatch, tmp_path):
    from dataclasses import replace
    import threading
    import uuid

    with oa.ExitStack() as stack:
        peer = oa._process_peer(os.getpid(), stack)
    wrong = replace(peer, **{changed: getattr(peer, changed) + 1 if isinstance(getattr(peer, changed), int) else "not-the-service"})
    trust = oa.ServiceTrust(peer, tmp_path / "unused")
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    monkeypatch.setitem(oa.PIPES, "ask", r"\\.\pipe\MW.test." + uuid.uuid4().hex)
    ready = threading.Event()
    connect = oa._winapi.ConnectNamedPipe

    def connecting(*args, **kw):
        ready.set()
        return connect(*args, **kw)

    monkeypatch.setattr(oa._winapi, "ConnectNamedPipe", connecting)
    sent = []
    original = oa._send

    def observe(pipe, body, end):
        sent.append(body)
        return original(pipe, body, end)

    monkeypatch.setattr(oa, "_send", observe)
    received = []

    def server():
        try:
            oa.serve_one("ask", lambda *args: received.append(args), trust=trust, timeout_ms=2000)
        except (OSError, oa.AuthorityError):
            pass

    worker = threading.Thread(target=server)
    worker.start()
    assert ready.wait(2)
    msg = {"v": 1, "op": "ask.submit", "project_id": PROJECT, "payload_b64": oa.freeze_payload(BODY).encoded}
    with pytest.raises(oa.AuthorityError, match="host-identity-mismatch"):
        oa._exchange("ask", msg, replace(trust, peer=wrong), 1000)
    worker.join(3)
    assert not worker.is_alive()
    assert received == sent == []


@pytest.mark.skipif(oa.os.name != "nt", reason="requires the Windows named-pipe kernel")
def test_delayed_pipe_creation_is_awaited_before_any_request_bytes(monkeypatch, tmp_path):
    import threading
    import uuid

    with oa.ExitStack() as stack:
        identity = oa._process_peer(os.getpid(), stack)
    trust = oa.ServiceTrust(identity, tmp_path / "unused")
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    monkeypatch.setitem(oa.PIPES, "ask", r"\\.\pipe\MW.test." + uuid.uuid4().hex)
    attempted = threading.Event()
    real_wait = oa._winapi.WaitNamedPipe

    def waiting(*args, **kwargs):
        attempted.set()
        return real_wait(*args, **kwargs)

    monkeypatch.setattr(oa._winapi, "WaitNamedPipe", waiting)
    received, replies, failed = [], [], []

    def handle(peer, msg):
        received.append(oa.decode_payload(msg["payload_b64"]).raw)
        return {"ok": True, "id": ID, "state": "pending",
                "sha256": oa.freeze_payload(BODY).sha256}

    def server():
        try:
            oa.serve_one("ask", handle, trust=trust, timeout_ms=3000)
        except Exception as exc:  # pragma: no cover - reported in the assertion
            failed.append(repr(exc))

    def client():
        try:
            replies.append(oa.submit_ask(PROJECT, BODY, timeout_ms=2000))
        except Exception as exc:  # pragma: no cover
            failed.append(repr(exc))

    # The first connect attempt is made while the listener does not exist yet.
    # Starting it afterwards is the deterministic delayed-create condition.
    thread = threading.Thread(target=client)
    thread.start()
    assert attempted.wait(2)
    assert thread.is_alive() and not received and not replies
    service = threading.Thread(target=server)
    service.start()
    thread.join(4)
    service.join(4)
    assert not thread.is_alive() and not service.is_alive()
    assert not failed, failed
    assert replies == [{"ok": True, "id": ID, "state": "pending",
                        "sha256": oa.freeze_payload(BODY).sha256}]
    assert received == [BODY]


@pytest.mark.skipif(oa.os.name != "nt", reason="requires the Windows named-pipe kernel")
def test_consecutive_pipe_instances_are_reopened_within_the_same_budget(monkeypatch, tmp_path):
    import threading
    import uuid

    with oa.ExitStack() as stack:
        identity = oa._process_peer(os.getpid(), stack)
    trust = oa.ServiceTrust(identity, tmp_path / "unused")
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    monkeypatch.setitem(oa.PIPES, "ask", r"\\.\pipe\MW.test." + uuid.uuid4().hex)
    received, failed = [], []
    created = []
    first_done = threading.Event()
    real_create = oa._winapi.CreateNamedPipe

    def create(*args, **kwargs):
        # Hold the second instance until the first round trip is really over.
        if created and not first_done.wait(3):
            raise AssertionError("first round trip did not complete")
        pipe = real_create(*args, **kwargs)
        created.append(pipe)
        return pipe

    monkeypatch.setattr(oa._winapi, "CreateNamedPipe", create)

    def handle(peer, msg):
        received.append(oa.decode_payload(msg["payload_b64"]).raw)
        return {"ok": True, "id": ID, "state": "pending",
                "sha256": oa.freeze_payload(BODY).sha256}

    def server():
        try:
            for _ in range(2):
                oa.serve_one("ask", handle, trust=trust, timeout_ms=3000)
        except Exception as exc:  # pragma: no cover - reported in the assertion
            failed.append(repr(exc))

    service = threading.Thread(target=server)
    service.start()
    first = oa.submit_ask(PROJECT, BODY, timeout_ms=2000)
    assert first["ok"] and first["state"] == "pending", first
    # No listener exists between the two serve_one instances until this point.
    first_done.set()
    second = oa.submit_ask(PROJECT, BODY, timeout_ms=2000)
    service.join(4)
    assert not service.is_alive()
    assert not failed, failed
    assert second["ok"] and second["state"] == "pending", second
    assert received == [BODY, BODY]


@pytest.mark.skipif(oa.os.name != "nt", reason="requires the Windows named-pipe kernel")
def test_connect_wait_keeps_one_deadline_and_never_reruns_an_uncertain_send(monkeypatch, tmp_path):
    import threading
    import time
    import uuid

    with oa.ExitStack() as stack:
        identity = oa._process_peer(os.getpid(), stack)
    trust = oa.ServiceTrust(identity, tmp_path / "unused")
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    endpoint = r"\\.\pipe\MW.test." + uuid.uuid4().hex
    monkeypatch.setitem(oa.PIPES, "ask", endpoint)
    msg = {"v": 1, "op": "ask.submit", "project_id": PROJECT,
           "payload_b64": oa.freeze_payload(BODY).encoded}

    # A missing listener consumes only the caller's single budget.
    started = time.monotonic()
    with pytest.raises(oa.AuthorityError, match="host-timeout"):
        oa._exchange("ask", msg, trust, 250)
    assert time.monotonic() - started < 2.0

    # A real peer accepts the request bytes, then disappears without a reply.
    # The client must not reopen the name or resend inside its remaining budget.
    served = threading.Event()
    read = []

    def server():
        pipe = oa._winapi.CreateNamedPipe(endpoint, 0x40080003, 0x0E, 1, 65536, 65536, 0, 0)
        try:
            oa._winapi.ConnectNamedPipe(pipe, None)
            read.append(oa._winapi.ReadFile(pipe, oa.MAX_FRAME)[0])
        finally:
            oa._close(pipe)
            served.set()

    service = threading.Thread(target=server)
    service.start()
    while not served.is_set():
        try:
            oa._winapi.WaitNamedPipe(endpoint, 100)
            break
        except OSError:
            pass
    opens, sends = [], []
    real_open, real_send = oa._winapi.CreateFile, oa._send

    def opening(*args, **kwargs):
        opens.append(args[0])
        return real_open(*args, **kwargs)

    def sending(pipe, body, end):
        sends.append(body)
        return real_send(pipe, body, end)

    monkeypatch.setattr(oa._winapi, "CreateFile", opening)
    monkeypatch.setattr(oa, "_send", sending)
    reply = oa.submit_ask(PROJECT, BODY, timeout_ms=1000)
    service.join(4)
    assert not service.is_alive()
    assert not reply["ok"], reply
    assert read and oa._object(read[0], oa.MAX_FRAME)["op"] == "ask.submit"
    assert opens == [endpoint]
    assert sends == [oa._encoded(msg)]


def test_h12_cannot_use_an_ask_result_or_let_a_reservation_failure_look_applied(monkeypatch):
    monkeypatch.setattr(oa, "load_trust", lambda: object())
    ref = {"ok": False, "reason": "recovery-unknown", "id": ID, "state": "unknown"}
    monkeypatch.setattr(oa, "_exchange", lambda *args: ref)
    assert oa.prepare_h12(PROJECT, "work", ID, "trip1", BODY) == ref
    assert oa.submit_ask(PROJECT, BODY) == {"ok": False, "reason": "invalid-host-response"}
    assert not oa.h12_status(PROJECT, "../../grant")["ok"]


def test_frame_limits_timeout_and_noncanonical_transfer_are_refused_before_connect(monkeypatch):
    opened = []
    monkeypatch.setattr(oa, "load_trust", lambda: opened.append("service"))
    for timeout in (0, -1, True, 31_000):
        assert oa.submit_ask(PROJECT, BODY, timeout_ms=timeout) == {"ok": False, "reason": "invalid-timeout"}
    assert not oa.submit_ask(PROJECT, b"{" + b"x" * oa.MAX_PAYLOAD)["ok"]
    for message in ({"v": True, "op": "ask.result", "project_id": PROJECT, "id": ID},
                    {"v": 1, "op": "ask.result", "project_id": PROJECT.upper(), "id": ID},
                    {"v": 1, "op": "ask.result", "project_id": PROJECT, "id": ID, "peer": True}):
        with pytest.raises(oa.AuthorityError):
            oa.validate_message("ask", message)
    assert not opened


def test_dependency_lock_matches_the_cached_wheels_and_is_fully_hashed():
    locked = _locked_versions()
    assert {"fido2", "cryptography", "cffi", "pycparser", "pywin32"} <= set(locked)
    for name, (version, digest) in locked.items():
        wheel = next(CACHE.glob(f"{name}-{version}-*.whl"), None)
        assert wheel is not None, name
        assert hashlib.sha256(wheel.read_bytes()).hexdigest() == digest
    text = LOCK.read_text(encoding="utf-8")
    assert all(" --hash=sha256:" in line for line in text.splitlines() if line and not line.startswith("#"))


def test_ordinary_mw_import_without_the_optional_sdk_fails_closed():
    env = {key: value for key, value in os.environ.items() if key != "PYTHONPATH"}
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1")
    script = (
        "import operator_host as h, operator_authority as a\n"
        "assert h.Fido2Server is None\n"
        "try:\n"
        "    h.verify_operator_dependencies()\n"
        "except h.Refusal as exc:\n"
        "    assert str(exc) == 'webauthn-runtime-unavailable'\n"
        "else:\n"
        "    raise SystemExit('lock verified without SDK')\n"
        "assert a.submit_ask('1234567890abcdef', b'{}')['reason'] in "
        "('host-unavailable', 'host-not-deployed')\n"
        "print('fail-closed')\n"
    )
    import subprocess

    done = subprocess.run([sys.executable, "-B", "-c", script], cwd=HERE, env=env, capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, (done.stdout, done.stderr)
    assert done.stdout.strip() == "fail-closed"


# ---------------------------------------------------------------------------
# Real FIDO2/WebAuthn + operator host fixtures (isolated, no service)
# ---------------------------------------------------------------------------


def _require_fido():
    if not FIDO:
        pytest.skip("optional operator dependency wheels are not available in the evidence cache")


def _project(tmp_path, *, key=_KEY, authority=False):
    root = tmp_path / "project"
    (root / ".agenticdoc").mkdir(parents=True)
    (root / ".agenticdoc/_index.parallel").write_text(
        f"| {key} | active | EXECUTE | {socket_host()}:{os.getpid()} | - | fixture | now |\n", encoding="utf-8")
    return root


def socket_host():
    import socket

    return socket.gethostname()


class Actor:
    def __init__(self, name="fixture-operator"):
        self.name = name
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.credential = AttestedCredentialData.create(
            bytes(range(16)), os.urandom(32), ES256.from_cryptography_key(self.private.public_key()))
        self.data = bytes(self.credential)
        self.pin = "a" * 64  # the HTTP fixture reuses a real certificate fingerprint


def _assertion(actor, options, origin, *, flags=5, counter=0, key=None, cross=False):
    challenge = options["publicKey"]["challenge"]
    client = CollectedClientData.create("webauthn.get", challenge, origin, cross_origin=cross)
    auth = AuthenticatorData.create(hashlib.sha256(b"localhost").digest(), flags, counter)
    signer = key or actor.private
    signature = signer.sign(auth + client.hash, ec.ECDSA(hashes.SHA256()))
    return {"id": websafe_encode(actor.credential.credential_id),
            "rawId": websafe_encode(actor.credential.credential_id), "type": "public-key",
            "response": {"clientDataJSON": client.b64, "authenticatorData": websafe_encode(auth),
                         "signature": websafe_encode(signature)}}


def _ask_draft(project_id, *, state="original bytes", questions=None):
    draft = {"schema": 1, "purpose": "ask", "project_id": project_id, "transport": "original",
             "model": "fixture", "destination": "fixture",
             "questions": questions or {"q": {"type": "noul", "instructions": "Read this exact text"}},
             "state": state}
    return json.dumps(draft, ensure_ascii=False).encode()


class Hub:
    pass


def _ask_host(tmp_path, *, sender=None, recovery_prepare=None, recovery_apply=None, origin="https://localhost:9443"):
    _require_fido()
    root = _project(tmp_path)
    project_id = decision_wire.project_id_for(root)
    actor = Actor()
    peer = oa.Peer("fixture-pm-sid", os.getpid(), 123, 1, "fixture-pm")
    project = host.Project(root, frozenset([peer.sid]), frozenset([peer.image]), "", {}, {}, ())
    sent = []
    calls = []

    def default_sender(root, raw):
        sent.append(raw)
        return {"model": "fixture", "usage": None, "latency_ms": 0, "answers": {"q": "fixture answer"}}

    def prepare(root, raw, grant):
        calls.append(("prepare", raw, grant))
        return {"ok": True, "choice": "approve", "basis_id": "basis", "basis_text": "basis text",
                "decision_ref": "dp-gate-approve:" + grant["operation_id"], "before_sha256": "b" * 64,
                "matter_ref": "matter", "substantive_version": 1}

    def apply(root, raw, grant, decision):
        calls.append(("apply", raw, grant, decision))
        return {"ok": True, "state": "observing", "trip_id": grant["trip_id"],
                "decision_ref": decision["decision_ref"], "receipt_sha256": "c" * 64}

    hub = Hub()
    hub.root, hub.project_id, hub.actor, hub.peer = root, project_id, actor, peer
    hub.sent, hub.calls = sent, calls
    hub.host = host.OperatorHost(
        tmp_path / "host.db", origin=origin, projects={project_id: project},
        operators={actor.pin: host.Operator(actor.name, actor.data, frozenset(host.ROLES), frozenset([project_id]))},
        ttl_seconds=300, ask_sender=sender or default_sender,
        recovery_prepare=recovery_prepare or prepare, recovery_apply=recovery_apply or apply,
        guard=lambda *_: True, verify_deployment=lambda *_: True)
    return hub


def _submit(hub, raw=None):
    raw = raw or _ask_draft(hub.project_id)
    reply = hub.host.handle(hub.peer, {"v": 1, "op": "ask.submit", "project_id": hub.project_id,
                                      "payload_b64": base64.b64encode(raw).decode()})
    assert reply["ok"], reply
    return raw, {"id": reply["id"], "sha256": reply["sha256"]}


def _confirm(hub, request, *, flags=5, key=None, cross=False, counter=0, origin=None):
    options = hub.host.private("a" * 64, "challenge", request)["options"]
    assertion = _assertion(hub.actor, options, origin or hub.host.origin, flags=flags, key=key,
                           cross=cross, counter=counter)
    return hub.host.private("a" * 64, "confirm", {**request, "assertion": assertion})


def test_real_webauthn_shows_exact_frozen_bytes_and_sends_exactly_once():
    _require_fido()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mw-operator-fido-"))
    try:
        hub = _ask_host(tmp)
        raw, request = _submit(hub)
        displayed = hub.host.private("a" * 64, "display", request)
        assert base64.b64decode(displayed["payload_b64"]) == raw
        assert displayed["sha256"] == hashlib.sha256(raw).hexdigest()
        assert _confirm(hub, request)["state"] == "applied"
        assert hub.sent == [raw]
        # Replay of the same assertion/operation is refused and never resends.
        with pytest.raises(host.Refusal):
            _confirm(hub, request)
        assert hub.sent == [raw]
        result = hub.host.handle(hub.peer, {"v": 1, "op": "ask.result", "project_id": hub.project_id,
                                            "id": request["id"]})
        assert result["state"] == "applied" and result["result"]["answers"] == {"q": "fixture answer"}
        assert "decision_id" not in result["result"]
        # Another process PID is not the bound PM.
        from dataclasses import replace

        assert not hub.host.handle(replace(hub.peer, pid=os.getpid() + 1), {
            "v": 1, "op": "ask.result", "project_id": hub.project_id, "id": request["id"]})["ok"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


@pytest.mark.parametrize("bad", [{"flags": 1}, {"flags": 4}, {"origin": "https://other.invalid"},
                                 {"wrong_key": True}, {"cross": True}])
def test_real_webauthn_refuses_no_uv_wrong_origin_wrong_key_and_cross_origin(bad):
    _require_fido()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mw-operator-fido-"))
    try:
        hub = _ask_host(tmp)
        _, request = _submit(hub)
        kwargs = dict(bad)
        if kwargs.pop("wrong_key", False):
            kwargs["key"] = ec.generate_private_key(ec.SECP256R1())
        with pytest.raises(ValueError):
            _confirm(hub, request, **kwargs)
        assert hub.sent == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_edit_voids_the_challenge_and_cancel_prevents_any_send():
    _require_fido()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mw-operator-fido-"))
    try:
        hub = _ask_host(tmp)
        raw, request = _submit(hub)
        options = hub.host.private("a" * 64, "challenge", request)["options"]
        edited = raw.replace(b"original bytes", b"altered bytes")
        new_sha = hub.host.private("a" * 64, "edit", {**request, "payload_b64": base64.b64encode(edited).decode()})["sha256"]
        with pytest.raises(host.Refusal):
            hub.host.private("a" * 64, "confirm", {**request, "assertion": _assertion(hub.actor, options, hub.host.origin)})
        hub.host.private("a" * 64, "cancel", {"id": request["id"], "sha256": new_sha})
        with pytest.raises(host.Refusal):
            _confirm(hub, request)
        assert hub.sent == []
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_uncertain_send_is_persisted_unknown_and_never_retried():
    _require_fido()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mw-operator-fido-"))
    try:
        def failing(root, raw):
            calls.append(raw)
            raise RuntimeError("transport outcome unknown")

        calls = []
        hub = _ask_host(tmp, sender=failing)
        _, request = _submit(hub)
        assert _confirm(hub, request)["state"] == "unknown"
        # Restart keeps the uncertain fact; no automatic resend on recovery.
        restarted = host.OperatorHost(tmp / "host.db", origin=hub.host.origin, projects=hub.host.projects,
                                      operators=hub.host.operators, ttl_seconds=300, ask_sender=failing,
                                      guard=lambda *_: True, verify_deployment=lambda *_: True,
                                      recovery_prepare=hub.host.recovery_prepare,
                                      recovery_apply=hub.host.recovery_apply)
        for _ in range(2):
            result = restarted.handle(hub.peer, {"v": 1, "op": "ask.result", "project_id": hub.project_id,
                                                 "id": request["id"]})
            assert result["state"] == "unknown" and result["result"] is None
        assert len(calls) == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_concurrent_confirmations_emit_one_query_only():
    _require_fido()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mw-operator-fido-"))
    try:
        hub = _ask_host(tmp)
        _, request = _submit(hub)
        options = hub.host.private("a" * 64, "challenge", request)["options"]
        assertion = _assertion(hub.actor, options, hub.host.origin)
        responses = []

        def attempt():
            try:
                responses.append(hub.host.private("a" * 64, "confirm", {**request, "assertion": assertion}))
            except Exception as exc:  # one winner, typed refusals for the rest
                responses.append(exc)

        import threading

        threads = [threading.Thread(target=attempt) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        assert len(hub.sent) == 1
        assert sum(isinstance(item, dict) and item.get("state") == "applied" for item in responses) == 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _h12_draft(hub, grant_ref, trip, key=_KEY):
    draft = {"schema": 1, "purpose": "h12", "project_id": hub.project_id, "key": key, "trip_id": trip,
             "grant_ref": grant_ref, "pm_note": {"planned_action": "observe-brake"},
             "preparation": {"prepared_at": "2026-01-01T00:00:00+00:00"}, "gate_id": "gate-0001",
             "action": "observe-brake"}
    return json.dumps(draft, sort_keys=True).encode()


def _h12_handle(hub, raw, grant_ref, trip):
    return hub.host.handle(hub.peer, {"v": 1, "op": "h12.prepare", "project_id": hub.project_id,
                                      "payload_b64": base64.b64encode(raw).decode(),
                                      "grant_ref": grant_ref, "trip_id": trip, "key": _KEY})


def test_h12_grant_is_signed_by_a_real_credential_and_revocation_stops_new_reservations():
    _require_fido()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mw-operator-h12-"))
    try:
        record = {"authority_ref": "original", "kind": "user-grant", "scope": ["recovery:breaker"], "writer": "trusted"}
        root = _project(tmp)
        project_id = decision_wire.project_id_for(root)
        actor = Actor()
        peer = oa.Peer("fixture-pm-sid", os.getpid(), 123, 1, "fixture-pm")
        project = host.Project(root, frozenset([peer.sid]), frozenset([peer.image]), "", {"original": record},
                               {"round": {"kind": "auto-decisions", "unit": "round"}}, ("trusted",))
        prepared, applied = [], []

        def prepare(root, raw, grant):
            prepared.append(grant)
            return {"ok": True, "choice": "approve", "basis_id": "basis", "basis_text": "text",
                    "decision_ref": "dp-gate-approve:" + grant["operation_id"], "before_sha256": "b" * 64,
                    "matter_ref": "matter", "substantive_version": 1}

        def apply(root, raw, grant, decision):
            applied.append(grant)
            return {"ok": True, "state": "observing", "trip_id": grant["trip_id"],
                    "decision_ref": decision["decision_ref"], "receipt_sha256": "c" * 64}

        hub = Hub()
        hub.project_id, hub.actor, hub.peer, hub.root = project_id, actor, peer, root
        hub.host = host.OperatorHost(
            tmp / "host.db", origin="https://localhost:9443", projects={project_id: project},
            operators={actor.pin: host.Operator(actor.name, actor.data, frozenset(host.ROLES), frozenset([project_id]))},
            ttl_seconds=300, ask_sender=lambda *_: None, recovery_prepare=prepare, recovery_apply=apply,
            guard=lambda *_: True, verify_deployment=lambda *_: True)
        # Bootstrap: a live PM attempt records a bind candidate without a grant.
        assert not _h12_handle(hub, _h12_draft(hub, "0" * 32, _TRIP), "0" * 32, _TRIP)["ok"]
        with hub.host.transaction() as db:
            candidate = db.execute("SELECT id FROM candidates").fetchone()[0]
        bind = hub.host.private(actor.pin, "propose", {"project_id": project_id, "op": "pm.bind",
                                                      "terms": {"candidate_id": candidate}})
        assert _confirm(hub, bind)["state"] == "applied"
        terms = {"key": _KEY, "binding_id": bind["id"], "trip_id": "next", "authority_ref": "original",
                 "scope": ["recovery:breaker", "observe-brake", "key:" + _KEY, "action:observe-brake"],
                 "reason": "burst-60s", "unit": "round", "amount": 1, "usage_source": "round",
                 "observation_conditions": ["same trip only"], "stop_conditions": ["new trip"],
                 "expires_at": "2027-01-01T00:00:00+00:00"}
        grant = hub.host.private(actor.pin, "propose", {"project_id": project_id, "op": "h12.grant", "terms": terms})
        assert _confirm(hub, grant)["state"] == "applied"
        raw = _h12_draft(hub, grant["id"], _TRIP)
        import threading

        replies = []

        def reserve():
            replies.append(_h12_handle(hub, raw, grant["id"], _TRIP))

        threads = [threading.Thread(target=reserve) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(10)
        assert sum(reply.get("state") == "applied" for reply in replies) == 1
        assert len(prepared) == len(applied) == 1 and prepared[0]["trip_id"] == _TRIP
        # "next" is now permanently bound to this generation; a different trip is stale.
        assert not _h12_handle(hub, _h12_draft(hub, grant["id"], "f" * 32), grant["id"], "f" * 32)["ok"]
        revoke = hub.host.private(actor.pin, "propose", {"project_id": project_id, "op": "h12.revoke",
                                                        "terms": {"grant_ref": grant["id"]}})
        assert _confirm(hub, revoke)["state"] == "applied"
        assert not _h12_handle(hub, raw, grant["id"], _TRIP)["ok"]
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_h12_apply_failure_keeps_the_reservation_unknown():
    _require_fido()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mw-operator-h12-"))
    try:
        record = {"authority_ref": "original", "kind": "user-grant", "scope": ["recovery:breaker"], "writer": "trusted"}
        root = _project(tmp)
        project_id = decision_wire.project_id_for(root)
        actor = Actor()
        peer = oa.Peer("fixture-pm-sid", os.getpid(), 123, 1, "fixture-pm")
        project = host.Project(root, frozenset([peer.sid]), frozenset([peer.image]), "", {"original": record},
                               {"round": {"kind": "auto-decisions", "unit": "round"}}, ("trusted",))

        def prepare(root, raw, grant):
            return {"ok": True, "choice": "approve", "basis_id": "b", "basis_text": "t",
                    "decision_ref": "dp-gate-approve:" + grant["operation_id"], "before_sha256": "b" * 64,
                    "matter_ref": "m", "substantive_version": 1}

        def apply(root, raw, grant, decision):
            raise RuntimeError("brake write outcome unknown")

        hub = Hub()
        hub.project_id, hub.actor, hub.peer = project_id, actor, peer
        hub.host = host.OperatorHost(
            tmp / "host.db", origin="https://localhost:9443", projects={project_id: project},
            operators={actor.pin: host.Operator(actor.name, actor.data, frozenset(host.ROLES), frozenset([project_id]))},
            ttl_seconds=300, recovery_prepare=prepare, recovery_apply=apply, guard=lambda *_: True,
            verify_deployment=lambda *_: True)
        assert not _h12_handle(hub, _h12_draft(hub, "0" * 32, _TRIP), "0" * 32, _TRIP)["ok"]
        with hub.host.transaction() as db:
            candidate = db.execute("SELECT id FROM candidates").fetchone()[0]
        bind = hub.host.private(actor.pin, "propose", {"project_id": project_id, "op": "pm.bind",
                                                      "terms": {"candidate_id": candidate}})
        _confirm(hub, bind)
        terms = {"key": _KEY, "binding_id": bind["id"], "trip_id": _TRIP, "authority_ref": "original",
                 "scope": ["recovery:breaker", "observe-brake"], "reason": "burst-60s", "unit": "round",
                 "amount": 1, "usage_source": "round", "observation_conditions": ["same trip"],
                 "stop_conditions": ["new trip"], "expires_at": "2027-01-01T00:00:00+00:00"}
        grant = hub.host.private(actor.pin, "propose", {"project_id": project_id, "op": "h12.grant", "terms": terms})
        _confirm(hub, grant)
        reply = _h12_handle(hub, _h12_draft(hub, grant["id"], _TRIP), grant["id"], _TRIP)
        assert reply["ok"] is False and reply["state"] == "unknown" and reply["reason"]
        with hub.host.transaction() as db:
            row = db.execute("SELECT state FROM operations WHERE id=?", (reply["id"],)).fetchone()
            grant_row = db.execute("SELECT reservation,trip FROM grants WHERE id=?", (grant["id"],)).fetchone()
        assert row["state"] == "unknown" and grant_row["reservation"] == reply["id"] and grant_row["trip"] == _TRIP
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_protected_configuration_requires_bound_project_authority_and_hashed_tls():
    _require_fido()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mw-operator-config-"))
    try:
        root = _project(tmp)
        project_id = decision_wire.project_id_for(root)
        actor = Actor()
        cfg = {"schema": 1, "origin": "https://localhost:9443", "database": "host.db", "ttl_seconds": 300,
               "tls": {"certificate": "server.pem", "key": "server-key.pem", "client_ca": "ca.pem"},
               "h12_clients": [], "operators": {actor.pin: {
                   "name": actor.name, "credential_b64": base64.b64encode(actor.data).decode(),
                   "roles": sorted(host.ROLES), "projects": [project_id]}},
               "projects": {project_id: {
                   "root": str(root), "pm_sids": ["S-1-5-21-1-2-3"], "pm_images": ["C:/fixture/pm.exe"],
                   "trusted_writers": ["trusted"],
                   "authority_records": {"original": {"authority_ref": "original", "kind": "user-grant",
                                                      "scope": ["recovery:breaker"], "writer": "trusted"}},
                   "usage_sources": {"round": {"kind": "auto-decisions", "unit": "round"}}}}}
        path = tmp / "host.json"
        path.write_text(json.dumps(cfg), encoding="utf-8")
        for name in ("server.pem", "server-key.pem", "ca.pem"):
            (tmp / name).write_text("fixture-only\n", encoding="utf-8")
        trust = oa.ServiceTrust(oa.Peer("fixture", os.getpid(), 1, 0, "fixture"), path)
        original = oa.trusted_path
        oa.trusted_path = lambda candidate, *_args, **_kwargs: pathlib.Path(candidate)
        try:
            loaded = host.load_configuration(trust)
            assert loaded["projects"][project_id].root == root
            assert loaded["origin"] == "https://localhost:9443"
            # A caller-supplied authority record from an untrusted writer is refused.
            cfg["projects"][project_id]["trusted_writers"] = ["someone-else"]
            path.write_text(json.dumps(cfg), encoding="utf-8")
            with pytest.raises(host.Refusal):
                host.load_configuration(trust)
            # A root that does not hash to the declared project id is refused.
            cfg["projects"][project_id]["trusted_writers"] = ["trusted"]
            cfg["projects"][project_id]["root"] = str(tmp / "elsewhere")
            (tmp / "elsewhere").mkdir()
            path.write_text(json.dumps(cfg), encoding="utf-8")
            with pytest.raises(host.Refusal):
                host.load_configuration(trust)
        finally:
            oa.trusted_path = original
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Fixed local TLS and same-origin operator surface (isolated fixture only)
# ---------------------------------------------------------------------------


def _certificates(tmp, client_pin_out):
    ca_key = ec.generate_private_key(ec.SECP256R1())
    ca_name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "fixture-ca")])
    now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc)
    ca = (x509.CertificateBuilder().subject_name(ca_name).issuer_name(ca_name)
          .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
          .not_valid_before(now - __import__("datetime").timedelta(minutes=5))
          .not_valid_after(now + __import__("datetime").timedelta(hours=1))
          .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
          .sign(ca_key, hashes.SHA256()))

    def issue(name, usage, san=None):
        key = ec.generate_private_key(ec.SECP256R1())
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
        builder = (x509.CertificateBuilder().subject_name(subject).issuer_name(ca_name)
                   .public_key(key.public_key()).serial_number(x509.random_serial_number())
                   .not_valid_before(now - __import__("datetime").timedelta(minutes=5))
                   .not_valid_after(now + __import__("datetime").timedelta(hours=1))
                   .add_extension(x509.ExtendedKeyUsage([usage]), critical=False)
                   .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True))
        if san:
            builder = builder.add_extension(x509.SubjectAlternativeName(san), critical=False)
        cert = builder.sign(ca_key, hashes.SHA256())
        return key, cert

    server_key, server = issue("localhost", ExtendedKeyUsageOID.SERVER_AUTH,
                               [x509.DNSName("localhost"), x509.IPAddress(__import__("ipaddress").ip_address("127.0.0.1"))])
    client_key, client = issue("operator", ExtendedKeyUsageOID.CLIENT_AUTH)
    client_pin_out.append(hashlib.sha256(client.public_bytes(serialization.Encoding.DER)).hexdigest())
    paths = {"ca": tmp / "ca.pem", "certificate": tmp / "server.pem", "key": tmp / "server-key.pem",
             "client": tmp / "client.pem", "client_key": tmp / "client-key.pem"}
    paths["ca"].write_bytes(ca.public_bytes(serialization.Encoding.PEM))
    paths["certificate"].write_bytes(server.public_bytes(serialization.Encoding.PEM))
    paths["key"].write_bytes(server_key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                      serialization.NoEncryption()))
    paths["client"].write_bytes(client.public_bytes(serialization.Encoding.PEM))
    paths["client_key"].write_bytes(client_key.private_bytes(serialization.Encoding.PEM,
                                                             serialization.PrivateFormat.PKCS8,
                                                             serialization.NoEncryption()))
    return paths


def _free_port():
    import socket

    with socket.socket() as sock:
        sock.bind(("localhost", 0))
        return sock.getsockname()[1]


def test_fixed_local_tls_requires_a_pinned_client_certificate_and_matching_origin():
    _require_fido()
    tmp = pathlib.Path(tempfile.mkdtemp(prefix="mw-operator-tls-"))
    import http.client
    import ssl
    import threading

    try:
        pins = []
        paths = _certificates(tmp, pins)
        port = _free_port()
        origin = f"https://localhost:{port}"
        hub = _ask_host(tmp, origin=origin)
        hub.actor.pin = pins[0]
        hub.host.operators = {pins[0]: host.Operator(hub.actor.name, hub.actor.data, frozenset(host.ROLES),
                                                     frozenset([hub.project_id]))}
        hub.host.tls = {"certificate": paths["certificate"], "key": paths["key"], "client_ca": paths["ca"]}
        server = host.serve_https(hub.host)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        raw, request = _submit(hub)

        def client(cert=True, pin=None):
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            context.load_verify_locations(cafile=str(paths["ca"]))
            if cert:
                context.load_cert_chain(str(paths["client"]), str(paths["client_key"]))
            return http.client.HTTPSConnection("localhost", port, context=context, timeout=5)

        def post(conn, route, body, *, origin_header=origin, host_header=None):
            data = json.dumps(body).encode()
            conn.request("POST", "/api/" + route, body=data, headers={
                "Content-Type": "application/json", "Origin": origin_header,
                "Host": host_header or f"localhost:{port}"})
            return conn.getresponse()

        # No client certificate: TLS itself must refuse the connection.
        try:
            refused = post(client(cert=False), "list", {})
            assert refused.status != 200
        except (ssl.SSLError, OSError, ConnectionError):
            pass
        # Same-origin enforcement before any operation is read.
        response = post(client(), "list", {}, origin_header="https://other.invalid")
        assert response.status == 400
        # Display returns the exact frozen bytes; challenge is JSON-serialisable.
        response = post(client(), "display", request)
        assert response.status == 200
        displayed = json.loads(response.read())
        assert base64.b64decode(displayed["payload_b64"]) == raw
        response = post(client(), "challenge", request)
        assert response.status == 200
        options = json.loads(response.read())["options"]
        assert options["publicKey"]["userVerification"] == "required"
        assertion = _assertion(hub.actor, options, origin)
        response = post(client(), "confirm", {**request, "assertion": assertion})
        assert response.status == 200 and json.loads(response.read())["state"] == "applied"
        assert hub.sent == [raw]
        # Static assets are served with a strict CSP and no remote resources.
        conn = client()
        conn.request("GET", "/operator_host.js", headers={"Host": f"localhost:{port}"})
        response = conn.getresponse()
        assert response.status == 200
        assert "default-src 'none'" in response.getheader("Content-Security-Policy", "")
        body = response.read().decode()
        assert "fetch(" in body and "http://" not in body and "https://" not in body
        conn.close()
        server.shutdown()
        thread.join(5)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

def test_locked_dependency_versions_are_verified_against_installed_metadata():
    _require_fido()
    installed = host.verify_operator_dependencies()
    assert installed == {name: version for name, (version, _digest) in _locked_versions().items()
                         if name in host._LOCKED}


def test_configured_host_wires_the_real_recovery_consumer(monkeypatch, tmp_path):
    _require_fido()
    root = _project(tmp_path)
    project_id = decision_wire.project_id_for(root)
    actor = Actor()
    cfg = {"schema": 1, "origin": "https://localhost:9443", "database": "host.db", "ttl_seconds": 300,
           "tls": {"certificate": "server.pem", "key": "server-key.pem", "client_ca": "ca.pem"},
           "h12_clients": [], "operators": {actor.pin: {
               "name": actor.name, "credential_b64": base64.b64encode(actor.data).decode(),
               "roles": sorted(host.ROLES), "projects": [project_id]}},
           "projects": {project_id: {
               "root": str(root), "pm_sids": ["S-1-5-21-1-2-3"], "pm_images": ["C:/fixture/pm.exe"],
               "trusted_writers": ["trusted"],
               "authority_records": {"original": {"authority_ref": "original", "kind": "user-grant",
                                                  "scope": ["recovery:breaker"], "writer": "trusted"}},
               "usage_sources": {"round": {"kind": "auto-decisions", "unit": "round"}}}}}
    path = tmp_path / "host.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    for name in ("server.pem", "server-key.pem", "ca.pem"):
        (tmp_path / name).write_text("fixture-only\n", encoding="utf-8")
    trust = oa.ServiceTrust(oa.Peer("fixture", os.getpid(), 1, 0, "fixture"), path)
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    monkeypatch.setattr(oa, "trusted_path", lambda candidate, *_args, **_kwargs: pathlib.Path(candidate))
    configured = host.configured_host(ask_sender=lambda *_: None)
    from autopilot import decision_recovery

    assert configured.recovery_prepare is decision_recovery.prepare_operator_recovery
    assert configured.recovery_apply is decision_recovery.apply_operator_recovery
    assert configured.recovery_observe is decision_recovery.observe_operator_recovery
    assert configured.h12_clients == () and configured.trust == trust
    assert configured.tls["certificate"] == tmp_path / "server.pem"


@pytest.mark.skipif(oa.os.name != "nt", reason="requires the Windows named-pipe kernel")
def test_ipc_service_loop_serves_an_ask_round_trip_then_stops(monkeypatch, tmp_path):
    _require_fido()
    import threading
    import uuid

    with oa.ExitStack() as stack:
        identity = oa._process_peer(os.getpid(), stack)
    trust = oa.ServiceTrust(identity, tmp_path / "unused")
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    monkeypatch.setitem(oa.PIPES, "ask", r"\\.\pipe\MW.test." + uuid.uuid4().hex)
    hub = _ask_host(tmp_path)
    stop = threading.Event()
    threads = host.serve_ipc(hub.host, trust, (), stop, timeout_ms=3000)
    reply = oa.submit_ask(hub.project_id, _ask_draft(hub.project_id), timeout_ms=2000)
    assert reply["ok"] and reply["state"] == "pending", reply
    stop.set()
    for thread in threads:
        thread.join(6)
    assert not any(thread.is_alive() for thread in threads)


def test_configured_host_defaults_send_real_frozen_ask_bytes_once_over_http(monkeypatch, tmp_path):
    _require_fido()
    import http.client
    import ssl
    import threading

    import decision
    import mw

    root = _project(tmp_path)
    (root / ".mw").mkdir(parents=True)
    (root / ".mw/decide.json").write_text(json.dumps({
        "enabled": True, "transport": "timi-decisions", "model": "jev-latest",
        "api_key": "fixture-api-key"}), encoding="utf-8")
    project_id = decision_wire.project_id_for(root)
    actor = Actor()
    pins = []
    paths = _certificates(tmp_path, pins)
    port = _free_port()
    origin = f"https://localhost:{port}"
    cfg = {"schema": 1, "origin": origin, "database": "host.db", "ttl_seconds": 300,
           "tls": {"certificate": "server.pem", "key": "server-key.pem", "client_ca": "ca.pem"},
           "h12_clients": [], "operators": {pins[0]: {
               "name": actor.name, "credential_b64": base64.b64encode(actor.data).decode(),
               "roles": sorted(host.ROLES), "projects": [project_id]}},
           "projects": {project_id: {
               "root": str(root), "pm_sids": ["S-1-5-21-1-2-3"], "pm_images": ["C:/fixture/pm.exe"],
               "trusted_writers": ["trusted"],
               "authority_records": {"original": {"authority_ref": "original", "kind": "user-grant",
                                                  "scope": ["recovery:breaker"], "writer": "trusted"}},
               "usage_sources": {"round": {"kind": "auto-decisions", "unit": "round"}}}}}
    path = tmp_path / "host.json"
    path.write_text(json.dumps(cfg), encoding="utf-8")
    trust = oa.ServiceTrust(oa.Peer("fixture", os.getpid(), 1, 0, "fixture"), path)
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    monkeypatch.setattr(oa, "trusted_path", lambda candidate, *_a, **_k: pathlib.Path(candidate))

    fake = decision.FakeBackend([
        decision.BackendOutcome(available=True, reason=None, retryable=False, latency_ms=0,
                                answers={"q": {"value": "fixture answer", "confidence": 0.8}}),
    ])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda _cfg: fake)

    configured = host.configured_host()
    # Non-injected construction: the default deployment is the real T24 pair.
    assert configured.ask_sender is mw.operator_ask_frozen
    assert configured.guard is mw.operator_ask_validate
    assert configured.verify_deployment is host._service_call
    configured.operators = {pins[0]: host.Operator(actor.name, actor.data, frozenset(host.ROLES),
                                                   frozenset([project_id]))}
    configured.tls = {"certificate": paths["certificate"], "key": paths["key"], "client_ca": paths["ca"]}
    server = host.serve_https(configured)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        cfg_snapshot = mw._decide_config_snapshot(root)
        state = "exact frozen text with\ttabs and \"quotes\""
        raw = mw._operator_ask_frozen_draft(root, cfg_snapshot, {"q": {"type": "noul",
                                          "instructions": "Read this exact text"}}, state, cfg_snapshot.model)
        peer = oa.Peer("fixture-pm-sid", os.getpid(), 123, 1, "fixture-pm")
        submitted = configured.handle(peer, {"v": 1, "op": "ask.submit", "project_id": project_id,
                                             "payload_b64": base64.b64encode(raw).decode()})
        assert submitted["ok"], submitted
        request = {"id": submitted["id"], "sha256": submitted["sha256"]}

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=str(paths["ca"]))
        context.load_cert_chain(str(paths["client"]), str(paths["client_key"]))
        conn = http.client.HTTPSConnection("localhost", port, context=context, timeout=5)

        def post(route, body):
            conn.request("POST", "/api/" + route, body=json.dumps(body).encode(), headers={
                "Content-Type": "application/json", "Origin": origin, "Host": f"localhost:{port}"})
            response = conn.getresponse()
            return response.status, json.loads(response.read())

        status, displayed = post("display", request)
        assert status == 200 and base64.b64decode(displayed["payload_b64"]) == raw
        options = post("challenge", request)[1]["options"]
        assert options["publicKey"]["userVerification"] == "required"
        assertion = _assertion(actor, options, origin)
        status, confirmed = post("confirm", {**request, "assertion": assertion})
        assert status == 200 and confirmed["state"] == "applied", confirmed
        # Exactly one provider call, with the exact frozen state/questions.
        assert len(fake.calls) == 1
        assert fake.calls[0]["state"] == state
        assert fake.calls[0]["questions"] == {"q": {"type": "noul", "instructions": "Read this exact text"}}
        result = configured.handle(peer, {"v": 1, "op": "ask.result", "project_id": project_id,
                                          "id": request["id"]})
        assert result["ok"] and result["state"] == "applied"
        assert result["result"]["answers"] == {"q": {"value": "fixture answer", "confidence": 0.8}}
        assert "decision_id" not in result["result"]
        conn.close()
    finally:
        server.shutdown()
        thread.join(5)


def test_h12_observe_is_a_service_only_entry_using_actual_revocation_facts(monkeypatch, tmp_path):
    _require_fido()
    record = {"authority_ref": "original", "kind": "user-grant", "scope": ["recovery:breaker"],
              "writer": "trusted"}
    root = _project(tmp_path)
    project_id = decision_wire.project_id_for(root)
    actor = Actor()
    peer = oa.Peer("fixture-pm-sid", os.getpid(), 123, 1, "fixture-pm")
    project = host.Project(root, frozenset([peer.sid]), frozenset([peer.image]), "", {"original": record},
                           {"round": {"kind": "auto-decisions", "unit": "round"}}, ("trusted",))
    prepared, applied, observed = [], [], []

    def prepare(root, raw, grant):
        prepared.append(grant)
        return {"ok": True, "choice": "approve", "basis_id": "basis", "basis_text": "text",
                "decision_ref": "dp-gate-approve:" + grant["operation_id"], "before_sha256": "b" * 64,
                "matter_ref": "matter", "substantive_version": 1}

    def apply(root, raw, grant, decision):
        applied.append(grant)
        return {"ok": True, "state": "observing", "trip_id": grant["trip_id"],
                "decision_ref": decision["decision_ref"], "receipt_sha256": "c" * 64}

    def observe(root, raw, grant, *, observed_conditions=(), failed_checks=()):
        observed.append((raw, grant, tuple(observed_conditions), tuple(failed_checks)))
        if grant["revoked"]:
            return {"ok": True, "state": "retripped", "retripped": True, "trip_id": "f" * 32,
                    "decision_ref": "dp-gate-approve:" + grant["operation_id"]}
        return {"ok": True, "state": "observing", "retripped": False, "trip_id": grant["trip_id"],
                "decision_ref": "dp-gate-approve:" + grant["operation_id"]}

    hub = Hub()
    hub.project_id, hub.actor, hub.peer, hub.root = project_id, actor, peer, root
    hub.host = host.OperatorHost(
        tmp_path / "host.db", origin="https://localhost:9443", projects={project_id: project},
        operators={actor.pin: host.Operator(actor.name, actor.data, frozenset(host.ROLES), frozenset([project_id]))},
        ttl_seconds=300, recovery_prepare=prepare, recovery_apply=apply, recovery_observe=observe,
        guard=lambda *_: True, verify_deployment=lambda *_: True)
    # OS identity is a boundary fixture; the entry still requires a live service PID.
    trust = oa.ServiceTrust(oa.Peer("fixture-service", os.getpid(), 1, 0, "fixture-service"),
                            tmp_path / "unused")
    monkeypatch.setattr(oa, "load_trust", lambda: trust)

    assert not _h12_handle(hub, _h12_draft(hub, "0" * 32, _TRIP), "0" * 32, _TRIP)["ok"]
    with hub.host.transaction() as db:
        candidate = db.execute("SELECT id FROM candidates").fetchone()[0]
    bind = hub.host.private(actor.pin, "propose", {"project_id": project_id, "op": "pm.bind",
                                                  "terms": {"candidate_id": candidate}})
    _confirm(hub, bind)
    terms = {"key": _KEY, "binding_id": bind["id"], "trip_id": _TRIP, "authority_ref": "original",
             "scope": ["recovery:breaker", "observe-brake"], "reason": "burst-60s", "unit": "round",
             "amount": 1, "usage_source": "round", "observation_conditions": ["same trip"],
             "stop_conditions": ["new trip"], "expires_at": "2027-01-01T00:00:00+00:00"}
    grant = hub.host.private(actor.pin, "propose", {"project_id": project_id, "op": "h12.grant", "terms": terms})
    _confirm(hub, grant)
    raw = _h12_draft(hub, grant["id"], _TRIP)
    replied = _h12_handle(hub, raw, grant["id"], _TRIP)
    assert replied["ok"] and replied["state"] == "applied"
    operation_id = replied["id"]
    brake = root / ".agenticdoc/_autopilot/auto-brake.md"
    brake.parent.mkdir(parents=True, exist_ok=True)
    brake.write_text(
        "mw-breaker-event: " + json.dumps({"state": "tripped", "trip_id": _TRIP, "reason": "burst-60s",
                                           "triggered_at": "2026-01-01T00:00:00+00:00"}, sort_keys=True) + "\n"
        + "mw-breaker-event: " + json.dumps({"state": "observing", "trip_id": _TRIP,
                                              "decision_ref": "dp-gate-approve:" + operation_id,
                                              "grant_ref": grant["id"], "amount": 1,
                                              "usage_source": "round"}, sort_keys=True) + "\n",
        encoding="utf-8")

    # Public IPC cannot name this entry or self-report observation facts.
    assert not hub.host.handle(peer, {"v": 1, "op": "h12.observe", "project_id": project_id,
                                      "id": operation_id})["ok"]
    assert not hub.host.handle(peer, {"v": 1, "op": "h12.status", "project_id": project_id,
                                      "id": operation_id, "observed_conditions": True})["ok"]
    with pytest.raises(host.Refusal):
        hub.host.private(actor.pin, "observe", {"id": operation_id})

    assert hub.host.observations() == [operation_id]
    first = hub.host.observe(operation_id)
    assert first["ok"] and first["state"] == "observing"
    assert observed[-1][0] == raw and observed[-1][1]["revoked"] is False
    assert observed[-1][2] == () and "brake-generation-unknown" not in observed[-1][3]
    assert hub.host.observe(operation_id)["state"] == "observing"

    revoke = hub.host.private(actor.pin, "propose", {"project_id": project_id, "op": "h12.revoke",
                                                    "terms": {"grant_ref": grant["id"]}})
    _confirm(hub, revoke)
    retripped = hub.host.observe(operation_id)
    assert retripped["ok"] and retripped["state"] == "retripped"
    assert observed[-1][1]["revoked"] is True and "grant-revoked" in observed[-1][3]
    with hub.host.transaction() as db:
        row = db.execute("SELECT state,frozen FROM operations WHERE id=?", (operation_id,)).fetchone()
    assert row["state"] == "retripped" and row["frozen"] is None
    assert hub.host.observations() == []

    # A different process identity can never drive the watcher.
    monkeypatch.setattr(oa, "load_trust", lambda: oa.ServiceTrust(
        oa.Peer("fixture-service", os.getpid() + 1, 1, 0, "fixture-service"), tmp_path / "unused"))
    with pytest.raises(host.Refusal):
        hub.host.observations()


def test_main_refuses_on_non_windows(monkeypatch):
    monkeypatch.setattr(host.os, "name", "posix")
    assert host.main() == 2


# ---------------------------------------------------------------------------
# Status consumer contract: real host status round trip through the public API
# ---------------------------------------------------------------------------


def _observed_h12(tmp_path, observer):
    """One applied H12 plus the original brake the service-side observer reads."""
    _require_fido()
    record = {"authority_ref": "original", "kind": "user-grant", "scope": ["recovery:breaker"],
              "writer": "trusted"}
    root = _project(tmp_path)
    project_id = decision_wire.project_id_for(root)
    actor = Actor()
    peer = oa.Peer("fixture-pm-sid", os.getpid(), 123, 1, "fixture-pm")
    project = host.Project(root, frozenset([peer.sid]), frozenset([peer.image]), "", {"original": record},
                           {"round": {"kind": "auto-decisions", "unit": "round"}}, ("trusted",))

    def prepare(root, raw, grant):
        return {"ok": True, "choice": "approve", "basis_id": "basis", "basis_text": "text",
                "decision_ref": "dp-gate-approve:" + grant["operation_id"], "before_sha256": "b" * 64,
                "matter_ref": "matter", "substantive_version": 1}

    def apply(root, raw, grant, decision):
        return {"ok": True, "state": "observing", "trip_id": grant["trip_id"],
                "decision_ref": decision["decision_ref"], "receipt_sha256": "c" * 64}

    hub = Hub()
    hub.project_id, hub.actor, hub.peer, hub.root = project_id, actor, peer, root
    hub.host = host.OperatorHost(
        tmp_path / "host.db", origin="https://localhost:9443", projects={project_id: project},
        operators={actor.pin: host.Operator(actor.name, actor.data, frozenset(host.ROLES), frozenset([project_id]))},
        ttl_seconds=300, recovery_prepare=prepare, recovery_apply=apply, recovery_observe=observer,
        guard=lambda *_: True, verify_deployment=lambda *_: True)
    assert not _h12_handle(hub, _h12_draft(hub, "0" * 32, _TRIP), "0" * 32, _TRIP)["ok"]
    with hub.host.transaction() as db:
        candidate = db.execute("SELECT id FROM candidates").fetchone()[0]
    bind = hub.host.private(actor.pin, "propose", {"project_id": project_id, "op": "pm.bind",
                                                  "terms": {"candidate_id": candidate}})
    _confirm(hub, bind)
    terms = {"key": _KEY, "binding_id": bind["id"], "trip_id": _TRIP, "authority_ref": "original",
             "scope": ["recovery:breaker", "observe-brake"], "reason": "burst-60s", "unit": "round",
             "amount": 1, "usage_source": "round", "observation_conditions": ["same trip"],
             "stop_conditions": ["new trip"], "expires_at": "2027-01-01T00:00:00+00:00"}
    grant = hub.host.private(actor.pin, "propose", {"project_id": project_id, "op": "h12.grant", "terms": terms})
    _confirm(hub, grant)
    raw = _h12_draft(hub, grant["id"], _TRIP)
    replied = _h12_handle(hub, raw, grant["id"], _TRIP)
    assert replied["ok"] and replied["state"] == "applied", replied
    operation_id = replied["id"]
    brake = root / ".agenticdoc/_autopilot/auto-brake.md"
    brake.parent.mkdir(parents=True, exist_ok=True)
    brake.write_text(
        "mw-breaker-event: " + json.dumps({"state": "tripped", "trip_id": _TRIP, "reason": "burst-60s",
                                           "triggered_at": "2026-01-01T00:00:00+00:00"}, sort_keys=True) + "\n"
        + "mw-breaker-event: " + json.dumps({"state": "observing", "trip_id": _TRIP,
                                              "decision_ref": "dp-gate-approve:" + operation_id,
                                              "grant_ref": grant["id"], "amount": 1,
                                              "usage_source": "round"}, sort_keys=True) + "\n",
        encoding="utf-8")
    trust = oa.ServiceTrust(oa.Peer("fixture-service", os.getpid(), 1, 0, "fixture-service"),
                            tmp_path / "unused")
    return hub, grant["id"], operation_id, raw, trust


def _status_transport(hub, monkeypatch):
    """Route the real client transport into the real OperatorHost.handle."""
    seen = []

    def exchange(purpose, msg, trust, timeout_ms):
        seen.append((purpose, dict(msg)))
        return hub.host.handle(hub.peer, msg)

    monkeypatch.setattr(oa, "_exchange", exchange)
    return seen


@pytest.mark.parametrize("mode,expected", [("observing", "observing"), ("retripped", "retripped"),
                                            ("settled", "settled")])
def test_h12_status_reads_the_real_observer_states(mode, expected, monkeypatch, tmp_path):
    def observe(root, raw, grant, *, observed_conditions=(), failed_checks=()):
        ref = "dp-gate-approve:" + grant["operation_id"]
        if mode == "retripped":
            return {"ok": True, "state": "retripped", "retripped": True, "trip_id": "f" * 32,
                    "decision_ref": ref}
        if mode == "settled":
            return {"ok": True, "state": "clear", "retripped": False, "trip_id": grant["trip_id"],
                    "decision_ref": ref}
        return {"ok": True, "state": "observing", "retripped": False, "trip_id": grant["trip_id"],
                "decision_ref": ref}

    hub, grant_id, operation_id, raw, trust = _observed_h12(tmp_path, observe)
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    observed = hub.host.observe(operation_id)
    assert observed["ok"] is True and observed["state"] == expected, observed
    seen = _status_transport(hub, monkeypatch)
    reply = oa.h12_status(hub.project_id, operation_id)
    assert reply["ok"] is True, reply
    assert reply["id"] == operation_id and reply["state"] == expected
    assert reply["result"]["decision_ref"] == "dp-gate-approve:" + operation_id
    assert seen == [("h12", {"v": 1, "op": "h12.status", "project_id": hub.project_id,
                              "id": operation_id})]
    # A terminal observation keeps the fact but clears the frozen material.
    with hub.host.transaction() as db:
        row = db.execute("SELECT state,frozen FROM operations WHERE id=?", (operation_id,)).fetchone()
    assert row["state"] == expected
    assert (row["frozen"] is not None) == (expected == "observing")


def test_h12_status_keeps_the_real_unknown_failure_record(monkeypatch, tmp_path):
    def observe(root, raw, grant, *, observed_conditions=(), failed_checks=()):
        raise RuntimeError("fixture outcome lost")

    hub, grant_id, operation_id, raw, trust = _observed_h12(tmp_path, observe)
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    lost = hub.host.observe(operation_id)
    assert lost["ok"] is False and lost["state"] == "unknown"
    _status_transport(hub, monkeypatch)
    reply = oa.h12_status(hub.project_id, operation_id)
    assert reply["ok"] is True and reply["id"] == operation_id and reply["state"] == "unknown"
    assert reply["result"] == {"ok": False, "reason": "observation-unknown", "failed_checks": []}
    # The status read added no authority: the operation is still un-settled and
    # cannot be observed again through the public surface.
    assert not hub.host.handle(hub.peer, {"v": 1, "op": "h12.status", "project_id": hub.project_id,
                                         "id": operation_id, "retried": True})["ok"]
    assert hub.host.observations() == []


def test_status_unknown_results_are_a_closed_safe_failure_shape(monkeypatch):
    monkeypatch.setattr(oa, "load_trust", lambda: object())
    good = [
        {"ok": False, "reason": "observation-unknown", "failed_checks": ["grant-revoked"]},
        {"ok": False, "reason": "recovery-unknown"},
        {"ok": False, "reason": "recovery-not-approved",
         "consumer": {"ok": False, "reason": "recovery-not-approved", "choice": "deny"}},
    ]
    for record in good:
        reply = {"ok": True, "id": ID, "state": "unknown", "result": record}
        monkeypatch.setattr(oa, "_exchange", lambda *args, r=reply: r)
        assert oa.h12_status(PROJECT, ID) == reply
    bad = [
        {"ok": True, "reason": "observation-unknown"},
        {"ok": False, "reason": "observation-unknown", "arbitrary": 1},
        {"ok": False, "reason": "observation-unknown", "consumer": {"ok": "no"}},
        {"ok": False, "reason": "observation-unknown",
         "consumer": {"ok": False, "decision_id": "fake"}},
        {"ok": False, "reason": "observation-unknown", "decision_id": "fake"},
        {"ok": False, "reason": "observation-unknown", "failed_checks": ["ok", 1]},
        {"ok": False, "reason": "not a token"},
        "failure",
    ]
    for record in bad:
        reply = {"ok": True, "id": ID, "state": "unknown", "result": record}
        monkeypatch.setattr(oa, "_exchange", lambda *args, r=reply: r)
        assert oa.h12_status(PROJECT, ID) == {"ok": False, "reason": "invalid-host-response"}, record


def test_status_keeps_identity_and_ask_results_do_not_claim_recovery_states(monkeypatch):
    monkeypatch.setattr(oa, "load_trust", lambda: object())
    # A reply naming another operation is still refused, whatever its state.
    moved = {"ok": True, "id": "a" * 32, "state": "observing", "result": None}
    monkeypatch.setattr(oa, "_exchange", lambda *args: moved)
    assert oa.h12_status(PROJECT, ID) == {"ok": False, "reason": "result-binding-mismatch"}
    # An unknown observer state is not a new endpoint and is refused.
    invented = {"ok": True, "id": ID, "state": "observing-soon", "result": None}
    monkeypatch.setattr(oa, "_exchange", lambda *args: invented)
    assert oa.h12_status(PROJECT, ID) == {"ok": False, "reason": "result-binding-mismatch"}
    # Only H12 status owns the observation states; an ask result is not one.
    for state in ("observing", "retripped", "settled"):
        reply = {"ok": True, "id": ID, "state": state, "result": None}
        monkeypatch.setattr(oa, "_exchange", lambda *args, r=reply: r)
        assert not oa.ask_result(PROJECT, ID)["ok"], state
    # The same unknown result shape is not accepted on an ask result either.
    reply = {"ok": True, "id": ID, "state": "unknown",
             "result": {"ok": False, "reason": "observation-unknown", "failed_checks": []}}
    monkeypatch.setattr(oa, "_exchange", lambda *args: reply)
    assert not oa.ask_result(PROJECT, ID)["ok"]

# ---------------------------------------------------------------------------
# Windows SCM service entry point
# ---------------------------------------------------------------------------


@pytest.mark.skipif(oa.os.name != "nt", reason="requires the Windows SCM dispatcher")
def test_ordinary_process_is_not_the_service_and_initialises_nothing(tmp_path):
    import subprocess

    home = tmp_path / "home"
    home.mkdir()
    script = r"""
import socket
import operator_authority
import operator_host as host

touched = []


def forbidden(name):
    def fail(*args, **kwargs):
        touched.append(name)
        raise AssertionError(name)
    return fail


host.configured_host = forbidden("configured_host")
host.serve_https = forbidden("serve_https")
host.serve_ipc = forbidden("serve_ipc")
host.serve_observer = forbidden("serve_observer")
host.build_tls_context = forbidden("tls")
operator_authority.load_trust = lambda *args, **kwargs: touched.append("trust")
original_socket = socket.socket
opened = []


def tracking(*args, **kwargs):
    opened.append(args)
    return original_socket(*args, **kwargs)


socket.socket = tracking
code = host.main()
assert code == 2, code
assert touched == [], touched
assert opened == [], opened
print("not-service")
"""
    env = {key: value for key, value in os.environ.items()
           if key in ("PATH", "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
                      "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE")}
    env.update(PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1", HOME=str(home),
               USERPROFILE=str(home), APPDATA=str(home), LOCALAPPDATA=str(home),
               TEMP=str(home), TMP=str(home))
    done = subprocess.run([sys.executable, "-B", "-c", script], cwd=HERE, env=env,
                          capture_output=True, text=True, timeout=60)
    assert done.returncode == 0, (done.stdout, done.stderr)
    assert done.stdout.strip() == "not-service"
    assert "1063" in done.stderr
    # A refused console run leaves no state behind, not even a database.
    assert list(home.iterdir()) == []


@pytest.mark.skipif(oa.os.name != "nt", reason="requires the Windows SCM types")
def test_service_main_reports_stopped_without_running_when_initialisation_fails(monkeypatch):
    statuses = []
    sentinel = object()
    monkeypatch.setattr(host, "_register_service_handler", lambda name, handler: sentinel)
    monkeypatch.setattr(host, "_set_service_status",
                        lambda handle, status: statuses.append({
                            "state": status.dwCurrentState,
                            "exit": status.dwWin32ExitCode,
                            "specific": status.dwServiceSpecificExitCode}) or True)

    def failing_configured_host():
        # Startup trust/config work runs after start-pending, never after running.
        assert statuses and statuses[-1]["state"] == host.SERVICE_START_PENDING
        raise host.Refusal("fixture-initialisation-failed")

    monkeypatch.setattr(host, "configured_host", failing_configured_host)

    def dispatcher(table):
        assert table[0].lpServiceName == oa.SERVICE_NAME
        table[0].lpServiceProc(0, None)
        return True

    monkeypatch.setattr(host, "_start_service_dispatcher", dispatcher)
    code = host.main()
    assert code != 0
    assert [row["state"] for row in statuses] == [host.SERVICE_START_PENDING, host.SERVICE_STOPPED]
    assert host.SERVICE_RUNNING not in [row["state"] for row in statuses]
    assert statuses[-1]["exit"] == host.ERROR_SERVICE_SPECIFIC_ERROR
    assert statuses[-1]["specific"] == host._SERVICE_SPECIFIC_START_FAILURE


@pytest.mark.skipif(oa.os.name != "nt", reason="requires the Windows SCM types")
def test_service_main_runs_only_after_startup_and_releases_threads_and_socket(monkeypatch):
    import socket
    import threading

    statuses = []
    handlers = {}
    sentinel = object()

    def register(name, handler):
        handlers["handler"] = handler
        return sentinel

    def set_status(handle, status):
        statuses.append({"state": status.dwCurrentState, "accepted": status.dwControlsAccepted,
                         "exit": status.dwWin32ExitCode})
        return True

    monkeypatch.setattr(host, "_register_service_handler", register)
    monkeypatch.setattr(host, "_set_service_status", set_status)

    class Server:
        def __init__(self):
            self.socket = socket.socket()
            self.socket.bind(("127.0.0.1", 0))
            self.socket.listen(1)
            self.wake = threading.Event()

        def serve_forever(self):
            self.wake.wait()

        def shutdown(self):
            self.wake.set()

        def server_close(self):
            self.socket.close()

    server = Server()

    class Service:
        trust = object()
        h12_clients = ()

    ipc_threads = []
    observer_threads = []

    def ipc(service, trust, clients, stop):
        thread = threading.Thread(target=stop.wait, daemon=True)
        thread.start()
        ipc_threads.append(thread)
        return [thread]

    def observer(service, stop):
        thread = threading.Thread(target=stop.wait, daemon=True)
        thread.start()
        observer_threads.append(thread)
        return thread

    monkeypatch.setattr(host, "serve_https", lambda service: server)
    monkeypatch.setattr(host, "serve_ipc", ipc)
    monkeypatch.setattr(host, "serve_observer", observer)

    def configured_service():
        assert statuses and statuses[-1]["state"] == host.SERVICE_START_PENDING
        assert not any(row["state"] == host.SERVICE_RUNNING for row in statuses)
        return Service()

    monkeypatch.setattr(host, "configured_host", configured_service)

    def dispatcher(table):
        done = threading.Event()

        def stop_after_running():
            while not done.wait(0.01):
                if any(row["state"] == host.SERVICE_RUNNING for row in statuses):
                    handlers["handler"](host.SERVICE_CONTROL_STOP, 0, None, None)
                    return

        watcher = threading.Thread(target=stop_after_running, daemon=True)
        watcher.start()
        table[0].lpServiceProc(0, None)
        done.set()
        watcher.join(2)
        return True

    monkeypatch.setattr(host, "_start_service_dispatcher", dispatcher)
    code = host.main()
    assert code == 0
    assert [row["state"] for row in statuses] == [
        host.SERVICE_START_PENDING, host.SERVICE_RUNNING,
        host.SERVICE_STOP_PENDING, host.SERVICE_STOPPED]
    assert statuses[1]["accepted"] == host.SERVICE_ACCEPT_STOP | host.SERVICE_ACCEPT_SHUTDOWN
    assert statuses[-1]["exit"] == 0
    assert server.socket.fileno() == -1
    assert all(not thread.is_alive() for thread in ipc_threads + observer_threads)
    assert not any(t.name == "operator-https" and t.is_alive() for t in threading.enumerate())

def test_service_trust_gate_accepts_start_pending_for_startup_only():
    for state in (2, 4):  # SERVICE_START_PENDING, SERVICE_RUNNING
        assert oa._service_state_allows_trust(state)
    for state in (0, 1, 3, 5, 6, 7):  # stopped/stop-pending/pause/etc.
        assert not oa._service_state_allows_trust(state)

@pytest.mark.skipif(oa.os.name != "nt", reason="requires the Windows SCM types")
def test_startup_failure_after_binding_closes_the_listener_and_never_reports_running(monkeypatch):
    import socket

    statuses = []
    monkeypatch.setattr(host, "_register_service_handler", lambda name, handler: object())
    monkeypatch.setattr(host, "_set_service_status",
                        lambda handle, status: statuses.append({
                            "state": status.dwCurrentState,
                            "exit": status.dwWin32ExitCode}) or True)

    class Server:
        def __init__(self):
            self.socket = socket.socket()
            self.socket.bind(("127.0.0.1", 0))
            self.socket.listen(1)

        def serve_forever(self):
            raise AssertionError("must not serve after a failed initialisation")

        def shutdown(self):
            raise AssertionError("must not shut down an unstarted server")

        def server_close(self):
            self.socket.close()

    server = Server()

    class Service:
        trust = object()
        h12_clients = ()

    monkeypatch.setattr(host, "configured_host", lambda: Service())
    monkeypatch.setattr(host, "serve_https", lambda service: server)

    def failing_ipc(service, trust, clients, stop):
        raise host.Refusal("fixture-pipe-failed")

    monkeypatch.setattr(host, "serve_ipc", failing_ipc)
    monkeypatch.setattr(host, "serve_observer", lambda service, stop: None)

    def dispatcher(table):
        table[0].lpServiceProc(0, None)
        return True

    monkeypatch.setattr(host, "_start_service_dispatcher", dispatcher)
    code = host.main()
    assert code != 0
    assert [row["state"] for row in statuses] == [host.SERVICE_START_PENDING, host.SERVICE_STOPPED]
    assert statuses[-1]["exit"] == host.ERROR_SERVICE_SPECIFIC_ERROR
    assert server.socket.fileno() == -1


# ---------------------------------------------------------------------------
# Read-only PM authority source adapter (dpc-pm-authority-source)
#
# Only the OS boundary is a fixture here: the SCM trust anchor, the protected
# path/ACL check and (where stated) the kernel process probe. Project claim
# parsing, record parsing and the re-read path are the real functions.
# ---------------------------------------------------------------------------


def _pm_record(ref="original", *, kind="user-grant", scope=("recovery:breaker",),
               writer="trusted", revoked=False):
    return {"authority_ref": ref, "kind": kind, "scope": list(scope), "writer": writer,
            "revoked": revoked}


def _pm_usage():
    return {"task-card-rounds": {"kind": "auto-decisions", "unit": "round"}}


def _pm_config(tmp_path, *, root, sid, image, records=None, writers=("trusted",), usage=None,
               policy=b"", policy_sha=None, project_id=None, root_value=None, schema=1):
    project_id = project_id or decision_wire.project_id_for(root)
    if policy_sha is None:
        policy_sha = hashlib.sha256(policy).hexdigest() if policy else ""
    row = {"root": root_value if root_value is not None else str(root),
           "pm_sids": [sid], "pm_images": [image],
           "trusted_writers": list(writers),
           "authority_records": {"original": _pm_record()} if records is None else records,
           "usage_sources": _pm_usage() if usage is None else usage,
           "policy_sha256": policy_sha}
    path = tmp_path / "host.json"
    path.write_text(json.dumps({"schema": schema, "projects": {project_id: row}}),
                    encoding="utf-8", newline="\n")
    return path, project_id


def _pm_claim(root, pid, key=_KEY):
    import socket

    path = root / ".agenticdoc/_index.parallel"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"| {key} | active | EXECUTE | {socket.gethostname()}:{pid} | - | fixture | now |\n",
                    encoding="utf-8", newline="\n")
    return path


def _pm_policy(root, raw=b'{"schema_version": 1}\n'):
    path = root / ".agenticdoc/_autopilot/decision-policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return path


def _pm_boundary(monkeypatch, path, *, sid, image, pid=None):
    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    trust = oa.ServiceTrust(oa.Peer("fixture-service", os.getpid() + 1, 1, 0, "fixture-service"), path)
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    monkeypatch.setattr(oa, "trusted_path", lambda candidate, *_a, **_k: pathlib.Path(candidate))
    peer = oa.Peer(sid, os.getpid() if pid is None else pid, 123, 1, image)
    monkeypatch.setattr(oa, "_process_peer", lambda _pid, _stack: peer, raising=False)
    return trust


def test_pm_authority_source_is_typed_immutable_and_preserves_protected_bytes(monkeypatch, tmp_path):
    import socket

    sid, image = "S-1-5-21-1-2-3", r"C:\fixture\pi.exe"
    root = tmp_path / "project"
    root.mkdir()
    policy = b'{"schema_version": 1, "authority_ref": "original"}\n'
    policy_path = _pm_policy(root, policy)
    path, project_id = _pm_config(tmp_path, root=root, sid=sid, image=image, policy=policy)
    index = _pm_claim(root, os.getpid())
    _pm_boundary(monkeypatch, path, sid=sid, image=image)
    protected = (path, index, policy_path)
    before = {item: item.read_bytes() for item in protected}

    observed = oa.read_pm_authority(root, _KEY)
    assert observed.project_id == project_id
    assert observed.project_root == root
    assert observed.key == _KEY
    assert observed.claim_id == f"{socket.gethostname()}:{os.getpid()}"
    assert observed.policy_sha256 == hashlib.sha256(policy).hexdigest()
    assert observed.trusted_writers == ("trusted",)
    assert observed.records["original"].authority_ref == "original"
    assert observed.records["original"].revoked is False
    assert observed.usage_sources["task-card-rounds"].kind == "auto-decisions"
    assert observed.usage_sources["task-card-rounds"].unit == "round"
    with pytest.raises(TypeError):
        observed.records["fake"] = "fake"
    with pytest.raises(TypeError):
        observed.usage_sources["fake"] = "fake"
    # The observation is re-readable from the OS/config; it is not a bearer token.
    assert oa.reread_pm_authority(observed) == observed
    assert oa.verify_pm_authority(observed) == observed
    assert {item: item.read_bytes() for item in protected} == before


@pytest.mark.skipif(oa.os.name != "nt", reason="requires the real Windows process identity")
def test_pm_read_accepts_the_claimed_pm_and_its_direct_bridge_only(monkeypatch, tmp_path):
    import socket
    import subprocess

    with oa.ExitStack() as stack:
        me = oa._process_peer(os.getpid(), stack)
        parent = oa._process_peer(os.getppid(), stack)
    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    root = tmp_path / "project"
    root.mkdir()
    path, _ = _pm_config(tmp_path, root=root, sid=me.sid, image=me.image)
    _pm_claim(root, os.getpid())
    trust = oa.ServiceTrust(oa.Peer("fixture-service", os.getpid() + 1, 1, 0, "fixture-service"), path)
    monkeypatch.setattr(oa, "load_trust", lambda: trust)
    monkeypatch.setattr(oa, "trusted_path", lambda candidate, *_a, **_k: pathlib.Path(candidate))

    assert oa.read_pm_authority(root, _KEY).claim_id == f"{socket.gethostname()}:{os.getpid()}"

    # T19 direct-parent bridge: the invoking child reads for the claimed PM parent.
    path, _ = _pm_config(tmp_path, root=root, sid=parent.sid, image=parent.image)
    _pm_claim(root, os.getppid())
    assert oa.read_pm_authority(root, _KEY).claim_id == f"{socket.gethostname()}:{os.getppid()}"

    # A worker environment is refused even when the live claim names this process.
    path, _ = _pm_config(tmp_path, root=root, sid=me.sid, image=me.image)
    _pm_claim(root, os.getpid())
    monkeypatch.setenv("PI_WORKER_TASK", "fixture-worker")
    with pytest.raises(oa.AuthorityError, match="pm-worker-not-pm"):
        oa.read_pm_authority(root, _KEY)
    monkeypatch.delenv("PI_WORKER_TASK")

    # Another live window's claim is not this caller, even on the same host.
    other = subprocess.Popen([sys.executable, "-B", "-c", "import time; time.sleep(30)"])
    try:
        _pm_claim(root, other.pid)
        with pytest.raises(oa.AuthorityError, match="pm-claim-unbound"):
            oa.read_pm_authority(root, _KEY)
    finally:
        other.terminate()
        other.wait(10)

    # A claim left by a restarted PM (old, dead PID) is never inherited.
    gone = subprocess.Popen([sys.executable, "-B", "-c", "pass"])
    gone.wait(10)
    _pm_claim(root, gone.pid)
    with pytest.raises(oa.AuthorityError, match="pm-claim-unbound"):
        oa.read_pm_authority(root, _KEY)

    # Unregistered project SID / image never inherit the registration.
    _pm_claim(root, os.getpid())
    path, _ = _pm_config(tmp_path, root=root, sid="S-1-5-21-9-9-9", image=me.image)
    with pytest.raises(oa.AuthorityError, match="pm-peer-untrusted"):
        oa.read_pm_authority(root, _KEY)
    path, _ = _pm_config(tmp_path, root=root, sid=me.sid, image=r"C:\fixture\other.exe")
    with pytest.raises(oa.AuthorityError, match="pm-peer-untrusted"):
        oa.read_pm_authority(root, _KEY)


def test_pm_read_refuses_bad_policy_wrong_root_and_unregistered_project(monkeypatch, tmp_path):
    sid, image = "S-1-5-21-1-2-3", r"C:\fixture\pi.exe"
    root = tmp_path / "project"
    root.mkdir()
    other = tmp_path / "other"
    other.mkdir()
    policy = b'{"schema_version": 1}\n'
    _pm_policy(root, policy)
    path, project_id = _pm_config(tmp_path, root=root, sid=sid, image=image, policy=policy)
    index = _pm_claim(root, os.getpid())
    _pm_boundary(monkeypatch, path, sid=sid, image=image)
    before = {item: item.read_bytes() for item in (path, index)}
    assert oa.read_pm_authority(root, _KEY)

    # A pinned policy digest that does not match the real policy file is stale.
    _pm_config(tmp_path, root=root, sid=sid, image=image, policy_sha="0" * 64)
    with pytest.raises(oa.AuthorityError, match="policy-version-changed"):
        oa.read_pm_authority(root, _KEY)
    # A malformed digest is not a version.
    _pm_config(tmp_path, root=root, sid=sid, image=image, policy_sha="nothex")
    with pytest.raises(oa.AuthorityError, match="invalid-authority-source"):
        oa.read_pm_authority(root, _KEY)
    # The declared root must be the caller's real current path.
    _pm_config(tmp_path, root=root, sid=sid, image=image, root_value=str(other))
    with pytest.raises(oa.AuthorityError, match="project-binding-mismatch"):
        oa.read_pm_authority(root, _KEY)
    # An unregistered project id is not a source.
    _pm_config(tmp_path, root=root, sid=sid, image=image, project_id="0" * 16)
    with pytest.raises(oa.AuthorityError, match="project-unregistered"):
        oa.read_pm_authority(root, _KEY)
    # A corrupt protected file is refused, not defaulted.
    path.write_text("{", encoding="utf-8", newline="\n")
    with pytest.raises(oa.AuthorityError, match="invalid-authority-source"):
        oa.read_pm_authority(root, _KEY)
    # An unavailable source keeps the concrete reason.
    path.unlink()
    with pytest.raises(oa.AuthorityError, match="authority-source-unavailable"):
        oa.read_pm_authority(root, _KEY)
    # An ACL/reparse refusal from the existing protected-path check survives.
    path, _ = _pm_config(tmp_path, root=root, sid=sid, image=image)

    def refused(*_args, **_kwargs):
        raise oa.AuthorityError("untrusted-path")

    monkeypatch.setattr(oa, "trusted_path", refused)
    with pytest.raises(oa.AuthorityError, match="untrusted-path"):
        oa.read_pm_authority(root, _KEY)
    assert index.read_bytes()


def test_pm_read_refuses_tampered_records_untrusted_writers_and_unknown_metering(monkeypatch, tmp_path):
    sid, image = "S-1-5-21-1-2-3", r"C:\fixture\pi.exe"
    root = tmp_path / "project"
    root.mkdir()
    path, _ = _pm_config(tmp_path, root=root, sid=sid, image=image)
    _pm_claim(root, os.getpid())
    _pm_boundary(monkeypatch, path, sid=sid, image=image)
    assert oa.read_pm_authority(root, _KEY)

    # Mapping key and the record's own id must agree.
    _pm_config(tmp_path, root=root, sid=sid, image=image,
               records={"original": _pm_record("forged")})
    with pytest.raises(oa.AuthorityError, match="invalid-authority-source"):
        oa.read_pm_authority(root, _KEY)
    # A record from a writer outside the configured controlled set is refused.
    _pm_config(tmp_path, root=root, sid=sid, image=image,
               records={"original": _pm_record(writer="outsider")})
    with pytest.raises(oa.AuthorityError, match="invalid-authority-source"):
        oa.read_pm_authority(root, _KEY)
    # Revocation is a visible fact, not a reason to mint a replacement.
    _pm_config(tmp_path, root=root, sid=sid, image=image,
               records={"original": _pm_record(revoked=True)})
    revoked = oa.read_pm_authority(root, _KEY)
    assert revoked.records["original"].revoked is True
    # Unknown or guessed metering is refused; only the declared descriptor survives.
    for usage in ({"round": {"kind": "auto-decisions", "unit": "round", "amount": 1}},
                  {"round": {"kind": "auto-decisions"}},
                  {"round": {"kind": "auto-decisions", "unit": "round_budget"}},
                  {"round": {"kind": "self-report", "unit": "round"}}):
        _pm_config(tmp_path, root=root, sid=sid, image=image, usage=usage)
        with pytest.raises(oa.AuthorityError, match="invalid-usage-source"):
            oa.read_pm_authority(root, _KEY)


def test_pm_observation_is_not_a_reusable_bearer_and_revocation_is_reread(monkeypatch, tmp_path):
    sid, image = "S-1-5-21-1-2-3", r"C:\fixture\pi.exe"
    root = tmp_path / "project"
    root.mkdir()
    path, _ = _pm_config(tmp_path, root=root, sid=sid, image=image)
    _pm_claim(root, os.getpid())
    _pm_boundary(monkeypatch, path, sid=sid, image=image)
    observed = oa.read_pm_authority(root, _KEY)
    assert observed.records["original"].revoked is False

    _pm_config(tmp_path, root=root, sid=sid, image=image,
               records={"original": _pm_record(revoked=True)})
    with pytest.raises(oa.AuthorityError, match="authority-source-changed"):
        oa.verify_pm_authority(observed)
    fresh = oa.reread_pm_authority(observed)
    assert fresh.records["original"].revoked is True
    assert observed.records["original"].revoked is False


def test_pm_read_does_not_add_public_ipc_operations_or_callbacks():
    assert set(oa.PIPES) == {"ask", "h12"}
    assert set(oa._FIELDS) == {"ask.submit", "ask.result", "ask.brake-read",
                               "ask.brake-trigger", "h12.prepare", "h12.status"}
    assert not hasattr(oa, "PM_AUTHORITY_OP")


def test_brake_operations_live_on_the_existing_ask_pipe_and_refuse_client_authority():
    project = "a" * 16
    read = {"v": 1, "op": "ask.brake-read", "project_id": project}
    assert oa.validate_message("ask", read) == read
    payload = base64.b64encode(json.dumps({
        "schema": 1, "purpose": "brake-trigger", "project_id": project,
        "reason_code": "burst-60s", "detail": "fixture",
        "evidence": [1], "request_id": "b" * 32,
    }, sort_keys=True).encode()).decode()
    trigger = {"v": 1, "op": "ask.brake-trigger", "project_id": project,
               "payload_b64": payload}
    assert oa.validate_message("ask", trigger) == trigger
    # No third purpose, and no client-chosen path/state/trip/origin fields.
    for bad in ({**read, "path": "C:/x"}, {**read, "trip_id": "c" * 32},
                {**read, "state": "clear"}, {**read, "origin": "pm"},
                {**trigger, "trip_id": "c" * 32}, {**trigger, "state": "clear"},
                {**trigger, "grant_ref": "d" * 32}):
        with pytest.raises(oa.AuthorityError):
            oa.validate_message("ask", bad)
    with pytest.raises(oa.AuthorityError):
        oa.validate_message("h12", trigger)
    assert set(oa.PIPES) == {"ask", "h12"}


def test_pm_read_creates_nothing_and_reads_no_private_material(monkeypatch, tmp_path):
    sid, image = "S-1-5-21-1-2-3", r"C:\fixture\pi.exe"
    root = tmp_path / "project"
    root.mkdir()
    policy = b'{"schema_version": 1}\n'
    _pm_policy(root, policy)
    path, _ = _pm_config(tmp_path, root=root, sid=sid, image=image, policy=policy)
    _pm_claim(root, os.getpid())
    (tmp_path / "server-key.pem").write_bytes(b"PRIVATE FIXTURE KEY\n")
    (tmp_path / "server.pem").write_bytes(b"FIXTURE CERT\n")
    (tmp_path / "host.db").write_bytes(b"FIXTURE DB\n")
    _pm_boundary(monkeypatch, path, sid=sid, image=image)

    def snapshot():
        return sorted((item.relative_to(tmp_path).as_posix(), item.read_bytes())
                      for item in tmp_path.rglob("*") if item.is_file())

    before = snapshot()
    oa.read_pm_authority(root, _KEY)
    oa.verify_pm_authority(oa.read_pm_authority(root, _KEY))
    assert snapshot() == before
    assert not (root / ".agenticdoc/_autopilot/_grants").exists()
