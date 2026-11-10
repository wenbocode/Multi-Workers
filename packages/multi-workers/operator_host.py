"""Local operator service. Only the Windows service bootstrap opens production IPC.

The public IPC never accepts an assertion, actor, grant issuance or executor.
The private HTTPS surface additionally requires a pinned operator client cert.

Production boundary (this module never installs any of it):
- the process must be the registered ``MultiWorkersOperatorHost`` SCM service,
  running as ``NT SERVICE\\MultiWorkersOperatorHost`` in session 0; the fixed
  service SID/PID/creation time are read from the kernel and SCM on every use
  (``operator_authority.load_trust``), never from environment or JSON;
- ``host.json``, the SQLite store, the TLS key/cert and this module's code sit
  under a protected directory tree (owner + DACL checked, no reparse points);
- the HTTPS origin is the configured ``https://localhost:<port>`` with a fixed
  server certificate the operator browser trusts, and a client certificate
  pinned by SHA-256 fingerprint for each registered operator;
- registration of accounts, service, ACLs, certificates and the first real
  grant are deployment steps. Nothing here performs them, so an isolated
  fixture proving these checks is not evidence of a deployed service.

Configuration (``host.json``, UTF-8 JSON, all paths absolute or relative to
``host.json`` and inside the protected tree)::

    {
      "schema": 1,
      "origin": "https://localhost:9443",
      "database": "host.db",
      "ttl_seconds": 300,
      "tls": {"certificate": "server.pem", "key": "server-key.pem",
              "client_ca": "operators-ca.pem"},
      "h12_clients": ["S-1-5-21-..."],
      "operators": {"<sha256 of client cert DER>": {
          "name": "operator-alice",
          "credential_b64": "<WebAuthn attested credential data bytes>",
          "roles": ["ask", "pm.bind", "h12.grant", "h12.revoke"],
          "projects": ["<16 hex project id>"]}},
      "projects": {"<16 hex>": {
          "root": "D:/projects/example",
          "pm_sids": ["S-1-5-21-..."],
          "pm_images": ["C:\\Program Files\\...\\pi.exe"],
          "policy_sha256": "<64 hex>",
          "trusted_writers": ["operator-policy"],
          "authority_records": {"<ref>": {"authority_ref": "...", "kind": "user-grant", ...}},
          "usage_sources": {"<source>": {"kind": "auto-decisions", "unit": "round"}}}}
    }

Only public attestation data enters ``credential_b64``; an authenticator private
key never reaches MW. ``configured_host`` binds ``ask_sender``/``guard`` to the
exact T24 consumer functions (``mw.operator_ask_frozen`` /
``mw.operator_ask_validate``) and ``recovery_prepare``/``recovery_apply``/
``recovery_observe`` to T21. Absent callbacks stay fail-closed.

H12 observation is a service-side entry only: ``OperatorHost.observe`` and
``OperatorHost.observations`` are never reachable through IPC or HTTP. T26's
protected watcher polls these methods; observed conditions and failed checks
come from host state (grant revocation/expiry) and the original brake object,
never from a request body.

Service entry (deployment installs this, the module never does): the SCM
service ``MultiWorkersOperatorHost`` runs this file directly with the fixed
interpreter and no wrapper::

    sc.exe create MultiWorkersOperatorHost binPath= "\"C:\\Python\\python.exe\" -B \"C:\\Program Files\\MultiWorkers\\operator_host.py\"" obj= "NT SERVICE\\MultiWorkersOperatorHost" start= demand

Service installation, the virtual service account, DACLs, certificates and the
first grant are prerequisites performed separately. ``main`` only calls
``StartServiceCtrlDispatcherW``; configuration, TLS, IPC and the observer are
initialised inside ``ServiceMain`` after ``SERVICE_START_PENDING``. The process
therefore has the fixed SCM identity that ``authority.load_trust`` re-reads on
every use. Running this module from an ordinary console returns
``ERROR_FAILED_SERVICE_CONTROLLER_CONNECT`` (1063) and never starts an
unmanaged host.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import hmac
import importlib.metadata
import json
import os
import pathlib
import re
import secrets
import socket
import sqlite3
import ssl
import sys
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import decision_policy
from autopilot import state
import decision_wire as wire
import operator_authority as authority

try:
    from fido2.server import Fido2Server
    from fido2.utils import websafe_encode
    from fido2.webauthn import AttestedCredentialData, AuthenticationResponse, PublicKeyCredentialRpEntity, UserVerificationRequirement
except ImportError:  # optional: ordinary MW imports must not need the host SDK
    Fido2Server = None
    websafe_encode = None
    AttestedCredentialData = None
    AuthenticationResponse = None
    PublicKeyCredentialRpEntity = None
    UserVerificationRequirement = None


MAX_BYTES = 1_048_576
ID = re.compile(r"[0-9a-f]{32}")
PROJECT = re.compile(r"[0-9a-f]{16}")
KEY = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}")
HASH = re.compile(r"[0-9a-f]{64}")
SID = re.compile(r"S-1-(?:[0-9]+-){1,14}[0-9]+")
ROLES = {"ask", "pm.bind", "h12.grant", "h12.revoke"}
_CALL = ContextVar("operator_call", default=None)
_MODULE = pathlib.Path(__file__).resolve()
_LOCK = pathlib.Path(__file__).with_name("requirements-operator-host.lock")
STATIC = {"/": "operator_host.html", "/operator_host.html": "operator_host.html",
          "/operator_host.js": "operator_host.js"}
_LOCKED = {"fido2", "cryptography", "cffi", "pycparser"}


class Refusal(ValueError):
    pass


def _require(condition, reason):
    if not condition:
        raise Refusal(reason)


def _unique(pairs):
    obj = dict(pairs)
    _require(len(obj) == len(pairs), "duplicate-json-key")
    return obj


def _json(raw):
    obj = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_unique,
                     parse_constant=lambda _: (_ for _ in ()).throw(Refusal("non-finite-json")))
    _require(type(obj) is dict, "expected-json-object")
    return obj


def _bytes(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def _plain(value):
    """Make fido2 option/state values JSON-safe without losing their meaning."""
    if isinstance(value, (bytes, bytearray)):
        return websafe_encode(bytes(value)) if websafe_encode else base64.urlsafe_b64encode(bytes(value)).rstrip(b"=").decode()
    if hasattr(value, "value") and type(value).__module__.startswith("fido2"):
        return value.value
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    return value


def verify_operator_dependencies() -> dict[str, str]:
    """Refuse to serve with any WebAuthn dependency outside the full-hash lock."""
    _require(Fido2Server is not None, "webauthn-runtime-unavailable")
    try:
        rows = _LOCK.read_text(encoding="utf-8").splitlines()
    except OSError:
        raise Refusal("operator-dependency-lock-unavailable") from None
    locked: dict[str, str] = {}
    for line in rows:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, sep, rest = line.partition("==")
        version, sep, hashed = rest.partition(" --hash=sha256:")
        _require(bool(sep) and name and version and HASH.fullmatch(hashed), "operator-dependency-lock-invalid")
        locked[name] = version
    _require(_LOCKED <= set(locked), "operator-dependency-lock-incomplete")
    installed = {}
    for name in sorted(_LOCKED):
        try:
            installed[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            raise Refusal("operator-dependency-missing") from None
        _require(installed[name] == locked[name], "operator-dependency-mismatch")
    return installed


def _payload(encoded):
    return authority.decode_payload(encoded).raw


def _peer(peer):
    return {"sid": peer.sid, "pid": peer.pid, "created_ns": peer.created_ns, "session_id": peer.session_id,
            "image": os.path.normcase(os.path.normpath(str(peer.image)))}


def _tokens(value):
    return isinstance(value, list) and bool(value) and all(isinstance(t, str) and t.strip() for t in value) and len(set(value)) == len(value)


def _timestamp(value):
    _require(isinstance(value, str) and len(value) <= 64, "invalid-expiry")
    moment = datetime.fromisoformat(value)
    _require(moment.utcoffset() is not None, "invalid-expiry")
    return moment.timestamp()


@dataclass(frozen=True)
class Operator:
    name: str
    credential: bytes
    roles: frozenset[str]
    projects: frozenset[str]


@dataclass(frozen=True)
class Project:
    root: pathlib.Path
    pm_sids: frozenset[str]
    pm_images: frozenset[str]
    policy_sha256: str = ""
    authority_records: dict = field(default_factory=dict)
    usage_sources: dict = field(default_factory=dict)
    trusted_writers: tuple = ()


def authorized_callback(root, purpose, frozen, grant=None) -> bool:
    frame = _CALL.get()
    if frame is None:
        return False
    try:
        registered = authority.load_trust()
        if registered.peer.pid != os.getpid():
            return False
        bound_root, op, raw, recorded, verify = frame
        return (bound_root == pathlib.Path(root).resolve() and purpose == op and type(frozen) is bytes
                and hmac.compare_digest(raw, frozen) and recorded == (_bytes(grant) if grant is not None else None)
                and verify(bound_root, op) is True)
    except Exception:
        return False


class OperatorHost:
    def __init__(self, database: pathlib.Path, *, origin: str, projects: dict[str, Project],
                 operators: dict[str, Operator], ttl_seconds: int, ask_sender: Callable | None = None,
                 recovery_prepare: Callable | None = None, recovery_apply: Callable | None = None,
                 recovery_observe: Callable | None = None,
                 brake_read: Callable | None = None, brake_trigger: Callable | None = None,
                 guard: Callable | None = None, verify_deployment: Callable | None = None, clock: Callable = time.time):
        u = urlsplit(origin)
        _require(u.scheme == "https" and u.hostname == "localhost" and origin == f"https://localhost:{u.port}"
                 and u.port and not u.username and not u.password, "invalid-fixed-operator-origin")
        _require(Fido2Server is not None, "webauthn-runtime-unavailable")
        _require(type(ttl_seconds) is int and ttl_seconds > 0, "invalid-operation-lifetime")
        self.origin, self.projects, self.operators = origin, dict(projects), dict(operators)
        self.db, self.ttl, self.clock = database, ttl_seconds, clock
        self.ask_sender, self.recovery_prepare, self.recovery_apply = ask_sender, recovery_prepare, recovery_apply
        self.recovery_observe = recovery_observe
        self.brake_read, self.brake_trigger = brake_read, brake_trigger
        self.guard = guard
        self.verify_deployment = verify_deployment
        self.server = Fido2Server(PublicKeyCredentialRpEntity(id=u.hostname, name="Multi-Workers Operator"),
                                  verify_origin=lambda observed: observed == origin)
        self._lock = threading.Lock()
        # Serializes redemption against revocation: an apply and a revoke can
        # never interleave, so the recorded order is the real order.
        self._grants = threading.Lock()
        with self.transaction() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS operations (
                id TEXT PRIMARY KEY, op TEXT NOT NULL, project TEXT NOT NULL, owner TEXT NOT NULL,
                frozen BLOB, sha TEXT NOT NULL, expires REAL NOT NULL, state TEXT NOT NULL,
                challenge TEXT, signer TEXT, result TEXT, grant_id TEXT, trip TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS credentials (
                credential BLOB PRIMARY KEY, counter INTEGER NOT NULL)""")
            db.execute("""CREATE TABLE IF NOT EXISTS bindings (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, key TEXT NOT NULL, peer TEXT NOT NULL,
                UNIQUE(project,key))""")
            db.execute("""CREATE TABLE IF NOT EXISTS grants (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, terms BLOB NOT NULL, signer TEXT NOT NULL,
                issued REAL NOT NULL, revoked REAL, trip TEXT, reservation TEXT)""")
            db.execute("""CREATE TABLE IF NOT EXISTS candidates (
                id TEXT PRIMARY KEY, project TEXT NOT NULL, key TEXT NOT NULL, peer TEXT NOT NULL, expires REAL NOT NULL)""")
            # Interrupted writes/sends require actual external reconciliation. No restart auto-retry.
            db.execute("UPDATE operations SET state='unknown',challenge=NULL WHERE state IN ('reserved','applying')")

    @contextmanager
    def transaction(self):
        with self._lock:
            db = sqlite3.connect(self.db, isolation_level=None, timeout=5)
            db.row_factory = sqlite3.Row
            try:
                db.execute("PRAGMA synchronous=FULL")
                db.execute("BEGIN IMMEDIATE")
                yield db
                db.commit()
            finally:
                db.close()

    def _operation(self, db, op, project, owner, frozen, *, grant=None, trip=None):
        oid, digest = uuid.uuid4().hex, hashlib.sha256(frozen).hexdigest()
        db.execute("""INSERT INTO operations (id,op,project,owner,frozen,sha,expires,state,grant_id,trip)
                      VALUES (?,?,?,?,?,?,?,'pending',?,?)""",
                   (oid, op, project, owner, frozen, digest, self.clock()+self.ttl, grant, trip))
        return {"ok": True, "id": oid, "state": "pending", "sha256": digest}

    def _pm(self, project_id, key, peer):
        project = self.projects[project_id]
        _require(KEY.fullmatch(key) and peer["sid"] in project.pm_sids and peer["image"] in project.pm_images
                 and type(peer["pid"]) is int and peer["pid"] > 0 and peer["created_ns"] > 0, "pm-peer-untrusted")
        claim = f"{socket.gethostname()}:{peer['pid']}"
        rows = [row for row in state.read_index(project.root) if row["key"] == key]
        _require(len(rows) == 1 and rows[0]["status"] == "active" and rows[0]["claim_id"] == claim
                 and state.claim_state(claim) == state.CLAIM_LIVE, "pm-claim-unbound")

    def _call(self, purpose, fn, root, raw, grant=None, *args, **kwargs):
        _require(fn is not None and self.verify_deployment and self.verify_deployment(root, purpose) is True,
                 "protected-executor-unavailable")
        token = _CALL.set((root, purpose, raw, _bytes(grant) if grant is not None else None, self.verify_deployment))
        try:
            return fn(root, raw, grant, *args, **kwargs) if grant is not None else fn(root, raw, *args, **kwargs)
        finally:
            _CALL.reset(token)

    def handle(self, peer, message):
        try:
            _require(type(message) is dict and type(message.get("v")) is int and message["v"] == 1, "bad-envelope")
            op, project = message["op"], message["project_id"]
            _require(isinstance(project, str) and PROJECT.fullmatch(project) and project in self.projects, "project-unavailable")
            identity = _peer(peer)
            owner = _bytes(identity).decode()
            expected = {"v", "op", "project_id"}
            _require(op in {"ask.submit", "ask.result", "ask.brake-read", "ask.brake-trigger",
                            "h12.prepare", "h12.status"}, "unknown-operation")
            if op == "ask.brake-read":
                _require(set(message) == expected, "bad-envelope")
                _require(self.brake_read is not None, "brake-read-unavailable")
                facts = self._call("ask", self.brake_read, self.projects[project].root, b"")
                _require(isinstance(facts, dict), "brake-read-unavailable")
                return {"ok": True, "facts": facts}
            if op == "ask.brake-trigger":
                _require(set(message) == expected | {"payload_b64"}, "bad-envelope")
                _require(self.brake_trigger is not None, "brake-trigger-unavailable")
                raw = _payload(message["payload_b64"])
                reply = self._call("ask", self.brake_trigger, self.projects[project].root, raw)
                _require(isinstance(reply, dict) and set(reply) ==
                         {"ok", "trip_id", "state", "created", "receipt_sha256"}
                         and reply.get("ok") is True and reply.get("state") == "tripped"
                         and type(reply.get("created")) is bool
                         and isinstance(reply.get("trip_id"), str)
                         and isinstance(reply.get("receipt_sha256"), str),
                         "invalid-brake-trigger-result")
                return reply
            if op in {"ask.result", "h12.status"}:
                _require(set(message) == expected | {"id"} and ID.fullmatch(message["id"]), "bad-envelope")
                with self.transaction() as db:
                    row = db.execute("SELECT * FROM operations WHERE id=? AND project=? AND owner=?",
                                     (message["id"], project, owner)).fetchone()
                    _require(row and row["op"] == ("ask" if op == "ask.result" else "h12"), "operation-unavailable")
                    phase = "expired" if row["state"] == "pending" and self.clock() >= row["expires"] else row["state"]
                    return {"ok": True, "id": row["id"], "state": phase,
                            "result": json.loads(row["result"]) if row["result"] else None}
            raw = _payload(message["payload_b64"])
            if op == "ask.submit":
                _require(set(message) == expected | {"payload_b64"}, "bad-envelope")
                _require(self.guard is not None, "material-guard-unavailable")
                draft = _json(raw)
                _require(draft.keys() == {"schema","purpose","project_id","transport","model","destination","questions","state"}
                         and type(draft["schema"]) is int and draft["schema"] == 1 and draft["purpose"] == "ask"
                         and draft["project_id"] == project and type(draft["questions"]) is dict and draft["questions"]
                         and all(isinstance(draft[k], str) and draft[k].strip() for k in ("transport","model","destination","state")),
                         "invalid-ask-draft")
                _require(self.guard(self.projects[project].root, raw) is True, "unsafe-material")
                with self.transaction() as db:
                    return self._operation(db, "ask", project, owner, raw)
            _require(set(message) == expected | {"payload_b64","grant_ref","trip_id","key"}, "bad-envelope")
            self._pm(project, message["key"], identity)
            recovery = _json(raw)
            _require(recovery.keys() == {"schema","purpose","project_id","key","trip_id","grant_ref","pm_note","preparation","gate_id","action"}
                     and type(recovery["schema"]) is int and recovery["schema"] == 1 and recovery["purpose"] == "h12"
                     and recovery["action"] == "observe-brake" and recovery["project_id"] == project
                     and all(recovery[k] == message[k] for k in ("key","trip_id","grant_ref")), "invalid-recovery-draft")
            candidate = hashlib.sha256(_bytes([project, message["key"], identity])).hexdigest()
            with self.transaction() as db:
                db.execute("DELETE FROM candidates WHERE expires<=?", (self.clock(),))
                pending = db.execute("SELECT COUNT(*) FROM candidates").fetchone()[0]
                _require(pending < 64, "pm-candidate-limit")
                db.execute("INSERT OR REPLACE INTO candidates VALUES (?,?,?,?,?)",
                           (candidate, project, message["key"], owner, self.clock()+self.ttl))
            return self._recover(project, message, raw, identity)
        except Exception as exc:
            return {"ok": False, "reason": str(exc) if isinstance(exc, Refusal) else "request-unavailable"}

    def _eligible(self, db, project, message, peer, *, reservation=None):
        row = db.execute("SELECT * FROM grants WHERE id=? AND project=?", (message["grant_ref"], project)).fetchone()
        _require(row and row["revoked"] is None and row["reservation"] == reservation, "grant-unavailable")
        grant = _json(row["terms"])
        _require(self.clock() < _timestamp(grant["expires_at"]) and grant["key"] == message["key"]
                 and (grant["trip_id"] == "next" or grant["trip_id"] == message["trip_id"])
                 and row["trip"] in (None, message["trip_id"]), "grant-stale")
        binding = db.execute("SELECT * FROM bindings WHERE id=? AND project=? AND key=?",
                             (grant["binding_id"], project, grant["key"])).fetchone()
        _require(binding and json.loads(binding["peer"]) == peer, "pm-binding-unavailable")
        self._pm(project, grant["key"], peer)
        pr = self.projects[project]
        return {**grant, "grant_ref": row["id"], "revoked": False, "project_id": project,
                "claim": f"{socket.gethostname()}:{peer['pid']}", "issuer": row["signer"],
                "recorded_at": datetime.fromtimestamp(row["issued"], timezone.utc).isoformat(),
                "policy_sha256": pr.policy_sha256, "authority_source": pr.authority_records,
                "trusted_writers": list(pr.trusted_writers), "usage_sources": pr.usage_sources}

    def _recover(self, project, message, raw, peer):
        with self._grants:
            return self._recover_locked(project, message, raw, peer)

    def _recover_locked(self, project, message, raw, peer):
        _require(self.recovery_prepare and self.recovery_apply, "recovery-handler-unavailable")
        _require(ID.fullmatch(message["grant_ref"]) and isinstance(message["trip_id"], str)
                 and KEY.fullmatch(message["trip_id"]), "invalid-recovery-reference")
        with self.transaction() as db:
            grant = self._eligible(db, project, message, peer)
            result = self._operation(db, "h12", project, _bytes(peer).decode(), raw, grant=message["grant_ref"], trip=message["trip_id"])
            oid = result["id"]
            # "next" is permanently bound to this generation by the first reservation.
            db.execute("UPDATE grants SET trip=?,reservation=? WHERE id=?", (message["trip_id"], oid, message["grant_ref"]))
            db.execute("UPDATE operations SET state='reserved' WHERE id=?", (oid,))
        root = self.projects[project].root
        try:
            term = {**grant, "trip_id": message["trip_id"], "operation_id": oid}
            decision = self._call("h12.prepare", self.recovery_prepare, root, raw, term)
            _require(isinstance(decision, dict), "recovery-unknown")
        except Exception as exc:
            return self._unknown(oid, exc)
        if decision.get("ok") is not True:
            # No original-file write happened, but a refused prepare may already
            # have recorded a model request. Keep the reservation (no blind retry).
            return self._unknown(oid, decision.get("reason"), decision=decision)
        if decision.get("choice") != "approve":
            # A real non-approve answer is definite: the brake stays engaged and
            # the reservation is released, but the granted trip stays bound.
            with self.transaction() as db:
                db.execute("UPDATE operations SET state='failed',result=?,frozen=NULL WHERE id=?",
                           (_bytes(decision).decode(), oid))
                db.execute("UPDATE grants SET reservation=NULL WHERE id=?", (message["grant_ref"],))
            return {"ok": False, "id": oid, "state": "failed", "reason": "recovery-not-approved"}
        try:
            _require(isinstance(decision.get("decision_ref"), str), "recovery-not-approved")
            with self.transaction() as db:
                grant = self._eligible(db, project, message, peer, reservation=oid)
                term = {**grant, "trip_id": message["trip_id"], "operation_id": oid}
                outcome = self._call("h12.apply", self.recovery_apply, root, raw, term, decision)
            # This is exactly the real consumer's receipt contract
            # (autopilot.decision_recovery.apply_operator_recovery).
            _require(isinstance(outcome, dict) and outcome.get("ok") is True
                     and outcome.get("state") == "observing"
                     and outcome.get("trip_id") == message["trip_id"]
                     and outcome.get("decision_ref") == decision["decision_ref"]
                     and isinstance(outcome.get("receipt_sha256"), str)
                     and HASH.fullmatch(outcome["receipt_sha256"]), "recovery-receipt-unavailable")
            with self.transaction() as db:
                # Keep the frozen request for the service-side observation entry:
                # T21's observe consumer needs the exact request bytes again.
                db.execute("UPDATE operations SET state='applied',result=? WHERE id=?",
                           (_bytes(outcome).decode(), oid))
            return {**result, "state": "applied"}
        except Exception as exc:
            return self._unknown(oid, exc)

    def _unknown(self, oid, reason, *, decision=None):
        if not isinstance(reason, str) or not reason:
            reason = "recovery-unknown"
        record = {"ok": False, "reason": reason}
        if decision is not None:
            record["consumer"] = {k: decision.get(k) for k in ("ok", "reason", "choice") if k in decision}
        with self.transaction() as db:
            # Keep the frozen H12 request so a real observation/reconciliation
            # can inspect the exact bytes; the state forbids a blind retry.
            db.execute("UPDATE operations SET state='unknown',result=? WHERE id=?",
                       (_bytes(record).decode(), oid))
        return {"ok": False, "id": oid, "state": "unknown", "reason": reason}

    def _require_service(self):
        """The service-side observation entry is not an IPC or HTTP route."""
        trust = authority.load_trust()
        _require(trust.peer.pid == os.getpid() and trust.peer.created_ns > 0, "host-identity-mismatch")
        return trust

    def _observation_facts(self, project, row, grant):
        """Read the actual protected facts; never accept them from a request body.

        Only facts this process can read are reported. Budget/claim/policy are
        re-read by T21's observe consumer; revocation and expiry are also kept
        here so a revoked grant cannot leave a live observing licence behind.
        """
        failed = []
        if grant.get("revoked") is not False:
            failed.append("grant-revoked")
        try:
            _require(self.clock() < _timestamp(grant["expires_at"]), "grant-expired")
        except Refusal:
            failed.append("grant-expired")
        try:
            from autopilot import decision_recovery

            state = decision_recovery.managed_brake_state(self.projects[project].root)
        except Exception:
            state = {"state": "unknown", "trip": None}
        if state.get("state") == "unknown":
            failed.append("brake-generation-unknown")
        elif state.get("trip") != row["trip"]:
            failed.append("brake-trip-changed")
        return (), tuple(failed)

    def observations(self) -> list[str]:
        """Service-side watcher input: applied H12 operations awaiting observation."""
        self._require_service()
        with self.transaction() as db:
            return [row["id"] for row in db.execute(
                "SELECT id FROM operations WHERE op='h12' AND state IN ('applied','observing')"
                " ORDER BY expires,id")]

    def observe(self, operation_id: str) -> dict:
        """One service-side observation of an applied H12; no model, no grant.

        T26's protected watcher polls :meth:`observations` and calls this. The
        consumer gets the exact frozen request plus host-owned facts, so a
        public caller cannot self-report ``observed_conditions``/``failed_checks``.
        """
        _require(isinstance(operation_id, str) and ID.fullmatch(operation_id), "invalid-operation-id")
        self._require_service()
        with self._grants:
            with self.transaction() as db:
                row = db.execute("SELECT * FROM operations WHERE id=? AND op='h12'", (operation_id,)).fetchone()
                _require(row is not None and row["state"] in ("applied", "observing"), "operation-unavailable")
                _require(row["frozen"] and hashlib.sha256(row["frozen"]).hexdigest() == row["sha"],
                         "operation-material-unavailable")
                grant_row = db.execute("SELECT * FROM grants WHERE id=? AND project=?",
                                       (row["grant_id"], row["project"])).fetchone()
                _require(grant_row is not None, "grant-unavailable")
                _require(row["project"] in self.projects, "project-unavailable")
                grant = _json(grant_row["terms"])
                binding = db.execute(
                    "SELECT peer FROM bindings WHERE id=? AND project=? AND key=?",
                    (grant.get("binding_id"), row["project"], grant.get("key"))).fetchone()
                _require(binding is not None, "pm-binding-unavailable")
                bound_peer = json.loads(binding["peer"])
                project_registration = self.projects[row["project"]]
                grant = {**grant, "grant_ref": grant_row["id"],
                         "revoked": grant_row["revoked"] is not None,
                         "project_id": row["project"], "trip_id": row["trip"],
                         "operation_id": operation_id, "issuer": grant_row["signer"],
                         "recorded_at": datetime.fromtimestamp(grant_row["issued"], timezone.utc).isoformat(),
                         "claim": f"{socket.gethostname()}:{bound_peer['pid']}",
                         "policy_sha256": project_registration.policy_sha256,
                         "authority_source": project_registration.authority_records,
                         "trusted_writers": list(project_registration.trusted_writers),
                         "usage_sources": project_registration.usage_sources}
                raw, root = row["frozen"], self.projects[row["project"]].root
            observed, failed = self._observation_facts(row["project"], row, grant)
            try:
                outcome = self._call("h12.observe", self.recovery_observe, root, raw, grant,
                                     observed_conditions=observed, failed_checks=failed)
                _require(isinstance(outcome, dict) and outcome.get("ok") is True
                         and (outcome.get("retripped") is True
                              or outcome.get("trip_id") in (None, row["trip"]))
                         and outcome.get("state") in
                         {"observing", "retripped", "clear", "tripped"}, "observation-unknown")
                final = "retripped" if outcome.get("retripped") is True else (
                    "observing" if outcome.get("state") == "observing" else "settled")
                with self.transaction() as db:
                    if final == "observing":
                        db.execute("UPDATE operations SET state='observing',result=? WHERE id=?",
                                   (_bytes(outcome).decode(), operation_id))
                    else:
                        db.execute("UPDATE operations SET state=?,result=?,frozen=NULL WHERE id=?",
                                   (final, _bytes(outcome).decode(), operation_id))
                return {"ok": True, "id": operation_id, "state": final, "consumer": outcome}
            except Exception as exc:
                # Fail closed: the operation stays un-settled and the watcher
                # must inspect the original object instead of retrying blindly.
                record = {"ok": False, "reason": str(exc) if isinstance(exc, Refusal) else "observation-unknown",
                          "failed_checks": list(failed)}
                with self.transaction() as db:
                    db.execute("UPDATE operations SET state='unknown',result=? WHERE id=?",
                               (_bytes(record).decode(), operation_id))
                return {"ok": False, "id": operation_id, "state": "unknown", "reason": record["reason"]}

    def _private_row(self, db, actor, oid):
        row = db.execute("SELECT * FROM operations WHERE id=?", (oid,)).fetchone()
        _require(row and row["project"] in actor.projects and row["op"] in actor.roles
                 and row["state"] == "pending" and self.clock() < row["expires"]
                 and row["frozen"] and hashlib.sha256(row["frozen"]).hexdigest() == row["sha"]
                 and (row["op"] == "ask" or row["owner"] == actor.name), "operation-unavailable")
        return row

    def private(self, cert_pin, route, request):
        # All confirmations take the same lock as an H12 reservation so that a
        # revocation cannot land between a signed approval and the protected write.
        if route == "confirm":
            with self._grants:
                return self._private(cert_pin, route, request)
        return self._private(cert_pin, route, request)

    def _private(self, cert_pin, route, request):
        actor = self.operators.get(cert_pin)
        _require(actor is not None, "operator-unavailable")
        if route == "list":
            with self.transaction() as db:
                db.execute("UPDATE operations SET state='expired',frozen=NULL,challenge=NULL WHERE state='pending' AND expires<=?", (self.clock(),))
                pending = [dict(row) for row in db.execute("SELECT id,project,op,sha,owner FROM operations WHERE state='pending'")
                           if row["project"] in actor.projects and row["op"] in actor.roles
                           and (row["op"] == "ask" or row["owner"] == actor.name)]
                candidates = [dict(row) for row in db.execute("SELECT * FROM candidates WHERE expires>?", (self.clock(),))
                              if row["project"] in actor.projects and "pm.bind" in actor.roles]
                bindings = [dict(row) for row in db.execute("SELECT * FROM bindings") if row["project"] in actor.projects]
                grants = [dict(row) for row in db.execute("SELECT id,project,signer,revoked,trip,reservation FROM grants")
                          if row["project"] in actor.projects]
            return {"ok": True, "operations": [{k:v for k,v in row.items() if k != "owner"} for row in pending],
                    "roles": sorted(actor.roles), "projects": sorted(actor.projects), "candidates": candidates,
                    "bindings": bindings, "grants": grants}
        if route == "propose":
            project, op, terms = request["project_id"], request["op"], request["terms"]
            _require(project in actor.projects and op in actor.roles and op in {"pm.bind","h12.grant","h12.revoke"}
                     and type(terms) is dict, "operator-scope-denied")
            with self.transaction() as db:
                if op == "pm.bind":
                    _require(set(terms) == {"candidate_id"}, "invalid-bind")
                    candidate = db.execute("SELECT * FROM candidates WHERE id=? AND project=? AND expires>?",
                                           (terms["candidate_id"], project, self.clock())).fetchone()
                    _require(candidate, "pm-candidate-unavailable")
                    terms = {"key": candidate["key"], "peer": json.loads(candidate["peer"]), **terms}
                elif op == "h12.grant":
                    self._grant_terms(db, project, terms)
                else:
                    _require(set(terms) == {"grant_ref"} and db.execute(
                        "SELECT 1 FROM grants WHERE id=? AND project=? AND revoked IS NULL",
                        (terms["grant_ref"], project)).fetchone(), "grant-unavailable")
                return self._operation(db, op, project, actor.name, _bytes(terms))
        oid = request["id"]
        with self.transaction() as db:
            row = self._private_row(db, actor, oid)
            raw = row["frozen"]
            cred = AttestedCredentialData(actor.credential)
            if route == "display":
                return {"ok": True, "id": oid, "purpose": row["op"], "project": row["project"], "sha256": row["sha"],
                        "payload_b64": base64.b64encode(raw).decode()}
            _require(hmac.compare_digest(request["sha256"], row["sha"]), "material-changed")
            if route == "edit":
                _require(row["op"] == "ask", "operation-not-editable")
                edit = _payload(request["payload_b64"])
                prev, edited = _json(raw), _json(edit)
                _require(prev.keys() == edited.keys() and all(prev[k] == edited[k] for k in prev.keys()-{"questions","state"})
                         and self.guard and self.guard(self.projects[row["project"]].root, edit) is True, "unsafe-edit")
                sha = hashlib.sha256(edit).hexdigest()
                db.execute("UPDATE operations SET frozen=?,sha=?,challenge=NULL,signer=NULL WHERE id=?", (edit,sha,oid))
                return {"ok": True, "id": oid, "sha256": sha}
            if route == "cancel":
                db.execute("UPDATE operations SET state='failed',frozen=NULL,challenge=NULL WHERE id=?", (oid,))
                return {"ok": True, "state": "failed"}
            if route == "challenge":
                binding = _bytes([row["op"], row["project"], row["id"], row["sha"], row["expires"],
                                  actor.name, self.origin, secrets.token_hex(32)])
                options, proof = self.server.authenticate_begin([cred], UserVerificationRequirement.REQUIRED,
                                                               challenge=hashlib.sha256(binding).digest())
                db.execute("UPDATE operations SET challenge=?,signer=? WHERE id=?", (_bytes(_plain(proof)).decode(),actor.name,oid))
                return {"ok": True, "options": _plain(dict(options))}
            _require(route == "confirm" and row["challenge"] and row["signer"] == actor.name, "challenge-unavailable")
            assertion = AuthenticationResponse.from_dict(request["assertion"])
            client = assertion.response.client_data
            _require(not client.cross_origin and "topOrigin" not in _json(bytes(client)), "cross-origin-assertion")
            self.server.authenticate_complete(json.loads(row["challenge"]), [cred], assertion)
            counter = assertion.response.authenticator_data.counter
            last = db.execute("SELECT counter FROM credentials WHERE credential=?", (cred.credential_id,)).fetchone()
            _require(not last or counter > last[0] or (counter == 0 and last[0] == 0),
                     "authenticator-counter-stale")
            db.execute("INSERT OR REPLACE INTO credentials VALUES (?,?)", (cred.credential_id, counter))
            terms = _json(raw)
            if row["op"] == "ask":
                _require(self.guard and self.guard(self.projects[row["project"]].root, raw) is True, "unsafe-material")
                _require(self.ask_sender is not None and self.verify_deployment is not None,
                         "isolated-query-sender-unavailable")
                db.execute("UPDATE operations SET state='reserved',challenge=NULL WHERE id=?", (oid,))
            else:
                if row["op"] == "pm.bind":
                    self._pm(row["project"], terms["key"], terms["peer"])
                    db.execute("INSERT OR REPLACE INTO bindings VALUES (?,?,?,?)",
                               (oid,row["project"],terms["key"],_bytes(terms["peer"]).decode()))
                elif row["op"] == "h12.grant":
                    self._grant_terms(db,row["project"],terms)
                    db.execute("INSERT INTO grants(id,project,terms,signer,issued) VALUES (?,?,?,?,?)",
                               (oid,row["project"],raw,actor.name,self.clock()))
                elif row["op"] == "h12.revoke":
                    cursor = db.execute("UPDATE grants SET revoked=? WHERE id=? AND project=? AND revoked IS NULL",
                                        (self.clock(),terms["grant_ref"],row["project"]))
                    _require(cursor.rowcount == 1, "grant-unavailable")
                db.execute("UPDATE operations SET state='applied',challenge=NULL,frozen=NULL WHERE id=?", (oid,))
                return {"ok": True, "id": oid, "state": "applied"}
        # Never hold the SQLite write lock during a query/provider request.
        try:
            result = self._call("ask", self.ask_sender, self.projects[row["project"]].root, raw)
            _require(isinstance(result, dict) and set(result) <= {"model","usage","latency_ms","answers"}
                     and isinstance(result.get("answers"), dict), "invalid-isolated-query-result")
            phase = "applied"
        except Exception:
            result, phase = None, "unknown"
        with self.transaction() as db:
            db.execute("UPDATE operations SET state=?,frozen=NULL,result=? WHERE id=?",
                       (phase,_bytes(result).decode() if result is not None else None,oid))
        return {"ok": True, "id": oid, "state": phase}

    def _grant_terms(self, db, project, t):
        _require(t.keys() == {"key","binding_id","trip_id","authority_ref","scope","reason","unit","amount","usage_source",
                              "observation_conditions","stop_conditions","expires_at"} and KEY.fullmatch(t["key"])
                 and ID.fullmatch(t["binding_id"]) and KEY.fullmatch(t["trip_id"])
                 and all(isinstance(t[k], str) and t[k].strip() for k in ("authority_ref","reason","unit","usage_source"))
                 and type(t["amount"]) is int and t["amount"] == 1 and _timestamp(t["expires_at"]) > self.clock()
                 and all(_tokens(t[k]) for k in ("scope","observation_conditions","stop_conditions")), "invalid-grant-terms")
        _require("recovery:breaker" in t["scope"] and "observe-brake" in t["scope"], "invalid-grant-scope")
        pr = self.projects[project]
        _require(t["authority_ref"] in pr.authority_records and t["usage_source"] in pr.usage_sources, "unbound-policy-or-usage")
        _require(db.execute("SELECT 1 FROM bindings WHERE id=? AND project=? AND key=?",
                            (t["binding_id"],project,t["key"])).fetchone(), "pm-binding-unavailable")


def _protected(base: pathlib.Path, value: object, trust: authority.ServiceTrust, *, directory=False,
               create=False) -> pathlib.Path:
    _require(isinstance(value, str) and value and "\x00" not in value, "invalid-config")
    candidate = pathlib.Path(value)
    if not candidate.is_absolute():
        candidate = base / candidate
    candidate = pathlib.Path(os.path.normpath(str(candidate)))
    if not candidate.is_relative_to(base):
        raise Refusal("invalid-config")
    if directory:
        _require(candidate.is_dir(), "invalid-config")
        authority.trusted_path(candidate, trust, directory=True)
    else:
        _require(candidate.is_file() or (create and not candidate.exists()), "invalid-config")
        if candidate.exists():
            authority.trusted_path(candidate, trust)
    return candidate


def _config_trusted() -> authority.ServiceTrust:
    trust = authority.load_trust()
    _require(trust.peer.pid == os.getpid() and trust.peer.created_ns > 0, "host-identity-mismatch")
    authority.trusted_path(_MODULE, trust)
    return trust


def load_configuration(trust: authority.ServiceTrust) -> dict:
    """Read the protected host configuration; never mint or default a trust anchor."""
    path = authority.trusted_path(trust.config_path, trust)
    try:
        raw = path.read_bytes()
    except OSError:
        raise Refusal("host-config-unavailable") from None
    _require(0 < len(raw) <= MAX_BYTES, "invalid-config")
    cfg = _json(raw)
    base = path.parent
    authority.trusted_path(base, trust, directory=True)
    _require(cfg.get("schema") == 1 and isinstance(cfg.get("origin"), str), "invalid-config")
    _require(type(cfg.get("ttl_seconds")) is int and cfg["ttl_seconds"] > 0, "invalid-config")
    tls = cfg.get("tls")
    _require(isinstance(tls, dict) and set(tls) == {"certificate", "key", "client_ca"}, "invalid-config")
    tls = {name: _protected(base, value, trust) for name, value in tls.items()}
    database = _protected(base, cfg.get("database"), trust, create=True)
    h12_clients = cfg.get("h12_clients", [])
    _require(isinstance(h12_clients, list) and len(h12_clients) <= 64
             and all(isinstance(s, str) and SID.fullmatch(s) for s in h12_clients), "invalid-config")
    raw_projects = cfg.get("projects")
    _require(isinstance(raw_projects, dict) and raw_projects, "invalid-config")
    projects = {}
    for project_id, row in raw_projects.items():
        _require(isinstance(project_id, str) and PROJECT.fullmatch(project_id) and isinstance(row, dict), "invalid-config")
        root = _protected(base, row.get("root"), trust, directory=True)
        _require(wire.project_id_for(root) == project_id, "project-binding-mismatch")
        pm_sids = row.get("pm_sids")
        pm_images = row.get("pm_images")
        writers = row.get("trusted_writers", [])
        _require(isinstance(pm_sids, list) and pm_sids
                 and all(isinstance(s, str) and SID.fullmatch(s) for s in pm_sids), "invalid-config")
        _require(isinstance(pm_images, list) and pm_images
                 and all(isinstance(s, str) and s and "\x00" not in s for s in pm_images), "invalid-config")
        _require(isinstance(writers, list) and all(_tokens([w]) for w in writers), "invalid-config")
        records = row.get("authority_records", {})
        usage = row.get("usage_sources", {})
        _require(isinstance(records, dict) and isinstance(usage, dict), "invalid-config")
        for ref, record in records.items():
            parsed, issues = decision_policy.parse_authority_record(record, trusted_writers=writers)
            _require(isinstance(ref, str) and parsed is not None and not issues
                     and parsed.authority_ref == ref, "invalid-authority-source")
        _require(all(isinstance(desc, dict) and set(desc) == {"kind", "unit"}
                     and all(isinstance(v, str) and v for v in desc.values()) for desc in usage.values()),
                 "invalid-config")
        policy = row.get("policy_sha256", "")
        _require(policy == "" or (isinstance(policy, str) and HASH.fullmatch(policy)), "invalid-config")
        projects[project_id] = Project(root, frozenset(pm_sids),
                                       frozenset(os.path.normcase(os.path.normpath(i)) for i in pm_images),
                                       policy, dict(records), dict(usage), tuple(writers))
    raw_operators = cfg.get("operators")
    _require(isinstance(raw_operators, dict) and raw_operators, "invalid-config")
    operators = {}
    for pin, row in raw_operators.items():
        _require(isinstance(pin, str) and HASH.fullmatch(pin) and isinstance(row, dict)
                 and set(row) == {"name", "credential_b64", "roles", "projects"}, "invalid-config")
        roles, allowed = row["roles"], row["projects"]
        _require(isinstance(row["name"], str) and KEY.fullmatch(row["name"])
                 and isinstance(roles, list) and roles and set(roles) <= ROLES
                 and isinstance(allowed, list) and allowed and set(allowed) <= set(projects), "invalid-config")
        try:
            credential = AttestedCredentialData(base64.b64decode(row["credential_b64"], validate=True))
        except (ValueError, TypeError):
            raise Refusal("invalid-config") from None
        operators[pin] = Operator(row["name"], bytes(credential), frozenset(roles), frozenset(allowed))
    return {"origin": cfg["origin"], "database": database, "ttl_seconds": cfg["ttl_seconds"],
            "tls": tls, "h12_clients": tuple(h12_clients), "projects": projects, "operators": operators}


def _service_call(root, purpose) -> bool:
    """The default deployment gate: only this live SCM service may run a consumer."""
    try:
        trust = authority.load_trust()
        return trust.peer.pid == os.getpid() and purpose in {"ask", "h12.prepare", "h12.apply", "h12.observe"}
    except authority.AuthorityError:
        return False


def configured_host(*, ask_sender: Callable | None = None, recovery_prepare: Callable | None = None,
                    recovery_apply: Callable | None = None, recovery_observe: Callable | None = None,
                    brake_read: Callable | None = None, brake_trigger: Callable | None = None,
                    guard: Callable | None = None) -> OperatorHost:
    """Load the fixed protected deployment. Installation is deliberately not performed.

    The default ask callbacks are the exact T24 functions; a caller cannot swap
    a different sender into the default deployment. Explicit arguments exist
    only for isolated tests and are not a second production path.
    """
    trust = _config_trusted()
    verify_operator_dependencies()
    cfg = load_configuration(trust)
    if ask_sender is None or guard is None:
        import mw

        ask_sender = ask_sender or mw.operator_ask_frozen
        guard = guard or mw.operator_ask_validate
    from autopilot import decision_recovery

    if (recovery_prepare is None or recovery_apply is None or recovery_observe is None
            or brake_read is None or brake_trigger is None):
        recovery_prepare = recovery_prepare or decision_recovery.prepare_operator_recovery
        recovery_apply = recovery_apply or decision_recovery.apply_operator_recovery
        recovery_observe = recovery_observe or decision_recovery.observe_operator_recovery
        brake_read = brake_read or decision_recovery.brake_facts
        brake_trigger = brake_trigger or decision_recovery.trigger_managed_brake
    host = OperatorHost(cfg["database"], origin=cfg["origin"], projects=cfg["projects"],
                        operators=cfg["operators"], ttl_seconds=cfg["ttl_seconds"],
                        ask_sender=ask_sender, recovery_prepare=recovery_prepare,
                        recovery_apply=recovery_apply, recovery_observe=recovery_observe,
                        brake_read=brake_read, brake_trigger=brake_trigger,
                        guard=guard, verify_deployment=_service_call)
    host.trust = trust
    host.tls = cfg["tls"]
    host.h12_clients = cfg["h12_clients"]
    return host


def build_tls_context(certificate, key, client_ca) -> ssl.SSLContext:
    """Fixed local TLS with mandatory, CA-verified client certificates."""
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.options |= ssl.OP_NO_COMPRESSION
    context.load_cert_chain(str(certificate), str(key))
    context.verify_mode = ssl.CERT_REQUIRED
    context.load_verify_locations(cafile=str(client_ca))
    return context


class OperatorHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def __init__(self, host: OperatorHost, tls: dict, static: pathlib.Path):
        u = urlsplit(host.origin)
        self.origin = host.origin
        self.host = host
        self.static = pathlib.Path(static)
        self.tls = build_tls_context(tls["certificate"], tls["key"], tls["client_ca"])
        super().__init__((u.hostname, u.port), _OperatorHandler)
        self.socket = self.tls.wrap_socket(self.socket, server_side=True)

    def handle_error(self, request, client_address):
        # Never print certificate material, assertions or payloads.
        return


_CSP = ("default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
        "img-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'")


class _OperatorHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = ""
    sys_version = ""

    def log_message(self, fmt, *args):
        return

    def _send(self, status, body: bytes, kind: str):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy", _CSP)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status, obj):
        self._send(status, json.dumps(obj, ensure_ascii=False, allow_nan=False).encode(), "application/json")

    def _pin(self):
        cert = self.connection.getpeercert(binary_form=True)
        _require(cert, "operator-unavailable")
        pin = hashlib.sha256(cert).hexdigest()
        _require(pin in self.server.host.operators, "operator-unavailable")
        return pin

    def _origin_ok(self):
        _require(self.headers.get("Host") == urlsplit(self.server.origin).netloc, "origin-mismatch")

    def do_GET(self):
        try:
            self._origin_ok()
            _require("?" not in self.path and "#" not in self.path, "bad-route")
            name = STATIC.get(self.path)
            _require(name is not None, "bad-route")
            self._pin()
            body = (self.server.static / name).read_bytes()
            self._send(200, body, "text/html; charset=utf-8" if name.endswith(".html") else "text/javascript; charset=utf-8")
        except Refusal as exc:
            self._json(403, {"ok": False, "reason": str(exc)})
        except OSError:
            self._json(503, {"ok": False, "reason": "static-unavailable"})

    def do_POST(self):
        try:
            self._origin_ok()
            _require(self.headers.get("Origin") == self.server.origin, "origin-mismatch")
            _require(self.headers.get("Content-Type", "").split(";")[0].strip() == "application/json", "bad-content-type")
            route = self.path.removeprefix("/api/")
            _require(self.path.startswith("/api/") and route in {"list", "propose", "display", "edit", "cancel", "challenge", "confirm"}, "bad-route")
            length = self.headers.get("Content-Length")
            _require(length and length.isdigit() and 0 < int(length) <= MAX_BYTES, "invalid-size")
            request = _json(self.rfile.read(int(length)))
            self._json(200, self.server.host.private(self._pin(), route, request))
        except Refusal as exc:
            self._json(400, {"ok": False, "reason": str(exc)})
        except (OSError, ValueError):
            self._json(400, {"ok": False, "reason": "request-unavailable"})
        except Exception:
            self._json(400, {"ok": False, "reason": "request-unavailable"})


def serve_https(host: OperatorHost) -> OperatorHTTPServer:
    return OperatorHTTPServer(host, host.tls, _MODULE.parent)


def serve_ipc(host: OperatorHost, trust: authority.ServiceTrust, h12_clients: tuple[str, ...],
              stop: threading.Event, *, timeout_ms: int = 30_000) -> list[threading.Thread]:
    def loop(purpose):
        sids = tuple(h12_clients) if purpose == "h12" else ()
        while not stop.is_set():
            try:
                authority.serve_one(purpose, host.handle, trust=trust, timeout_ms=timeout_ms, allowed_sids=sids)
            except (authority.AuthorityError, OSError):
                if stop.wait(0.05):
                    return
    purposes = ["ask"] + (["h12"] if h12_clients else [])
    threads = [threading.Thread(target=loop, args=(purpose,), name="operator-ipc-" + purpose, daemon=True)
               for purpose in purposes]
    for thread in threads:
        thread.start()
    return threads


def serve_observer(host: OperatorHost, stop: threading.Event, *, interval_s: float = 30.0,
                   fail: Callable | None = None) -> threading.Thread:
    """Service-side watcher: poll host facts, observe one applied H12 per run.

    No caller-supplied conditions and no model call. ``fail`` receives a short
    typed reason so the service can report a real gap without printing payloads.
    """
    _require(isinstance(interval_s, (int, float)) and not isinstance(interval_s, bool) and interval_s > 0,
             "invalid-observation-interval")

    def loop():
        while not stop.is_set():
            try:
                for operation_id in host.observations():
                    outcome = host.observe(operation_id)
                    if outcome.get("ok") is not True and fail is not None:
                        fail(outcome.get("reason") or "observation-unknown")
            except Exception as exc:  # noqa: BLE001 - one failed poll must not kill the service
                if fail is not None:
                    fail(str(exc) if isinstance(exc, Refusal) else "observation-unavailable")
            if stop.wait(interval_s):
                return

    thread = threading.Thread(target=loop, name="operator-observer", daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# Windows Service Control Manager entry point
# ---------------------------------------------------------------------------
# The service runs as its own process (SERVICE_WIN32_OWN_PROCESS). SCM waits
# up to 30 seconds for StartServiceCtrlDispatcherW, so main() does nothing but
# build the dispatch table. All deployment work happens in ServiceMain after
# SERVICE_START_PENDING, and SERVICE_RUNNING is published only after the fixed
# TLS endpoint, IPC pipes and observer are actually serving.

ERROR_FAILED_SERVICE_CONTROLLER_CONNECT = 1063
ERROR_SERVICE_SPECIFIC_ERROR = 1066
SERVICE_WIN32_OWN_PROCESS = 0x00000010
SERVICE_STOPPED = 1
SERVICE_START_PENDING = 2
SERVICE_STOP_PENDING = 3
SERVICE_RUNNING = 4
SERVICE_ACCEPT_STOP = 0x00000001
SERVICE_ACCEPT_SHUTDOWN = 0x00000004
SERVICE_CONTROL_STOP = 1
SERVICE_CONTROL_INTERROGATE = 4
SERVICE_CONTROL_SHUTDOWN = 5
_SERVICE_SPECIFIC_START_FAILURE = 1
_SERVICE_START_WAIT_HINT_MS = 30_000
_SERVICE_STOP_WAIT_HINT_MS = 30_000
_RUNTIME: "_ServiceRuntime | None" = None


class _ServiceRuntime:
    """Real SCM status transitions and stop handling for this process."""

    def __init__(self):
        self.handle = None
        self.stop = threading.Event()
        self.state = SERVICE_STOPPED
        self.accepted = 0
        self.failure = None
        self.exit_code = 0
        self.server = None
        self.serving = False
        self.threads: list[threading.Thread] = []
        self._lock = threading.Lock()
        self._checkpoint = 0
        self._stopping = False

    def report(self, state, *, accepted=0, exit_code=0, specific=0, wait_hint=0):
        with self._lock:
            self.state, self.accepted = state, accepted
            self._checkpoint += 1
            status = _SERVICE_STATUS()
            status.dwServiceType = SERVICE_WIN32_OWN_PROCESS
            status.dwCurrentState = state
            status.dwControlsAccepted = accepted
            status.dwWin32ExitCode = exit_code
            status.dwServiceSpecificExitCode = specific
            status.dwCheckPoint = self._checkpoint
            status.dwWaitHint = wait_hint
            if self.handle is None:
                return False
            return _set_service_status(self.handle, status)

    def request_stop(self):
        with self._lock:
            if self.state == SERVICE_STOPPED or self._stopping:
                return
            self._stopping = True
        # Publish STOP_PENDING before dropping the listeners so SCM never sees
        # a stopped process without the transition.
        self.report(SERVICE_STOP_PENDING, wait_hint=_SERVICE_STOP_WAIT_HINT_MS)
        self.stop.set()

    def interrogate(self):
        with self._lock:
            state, accepted = self.state, self.accepted
        if state != SERVICE_STOPPED:
            self.report(state, accepted=accepted)


def _service_control_handler(control, event_type, event_data, context):
    """SCM HandlerEx. Exceptions must never cross the Win32 callback boundary."""
    runtime = _RUNTIME
    if runtime is None:
        return 0
    try:
        if control in (SERVICE_CONTROL_STOP, SERVICE_CONTROL_SHUTDOWN):
            runtime.request_stop()
        elif control == SERVICE_CONTROL_INTERROGATE:
            runtime.interrogate()
    except Exception:
        return 0
    return 0


def _service_reason(exc):
    if isinstance(exc, Refusal):
        return str(exc)
    if isinstance(exc, authority.AuthorityError):
        return exc.reason
    return "service-initialization-failed"


def _service_run(runtime):
    handle = _register_service_handler(authority.SERVICE_NAME, _SERVICE_HANDLER_PROC)
    if not handle:
        runtime.failure = "service-handler-unavailable"
        runtime.exit_code = 3
        return
    runtime.handle = handle
    if not runtime.report(SERVICE_START_PENDING, wait_hint=_SERVICE_START_WAIT_HINT_MS):
        runtime.failure = "service-status-unavailable"
        runtime.exit_code = 3
        return
    failure = None
    try:
        service = configured_host()
        server = serve_https(service)
        runtime.server = server
        runtime.threads.extend(serve_ipc(service, service.trust, service.h12_clients, runtime.stop))
        runtime.threads.append(serve_observer(service, runtime.stop))
        https = threading.Thread(target=server.serve_forever, name="operator-https", daemon=True)
        https.start()
        runtime.threads.append(https)
        runtime.serving = True
        # Only now can the fixed deployment actually answer IPC and TLS.
        runtime.report(SERVICE_RUNNING, accepted=SERVICE_ACCEPT_STOP | SERVICE_ACCEPT_SHUTDOWN)
        runtime.stop.wait()
    except BaseException as exc:  # never report RUNNING over a failed initialisation
        failure = _service_reason(exc)
    finally:
        runtime.stop.set()
        if runtime.server is not None:
            if runtime.serving:
                try:
                    runtime.server.shutdown()
                except Exception:
                    pass
            try:
                runtime.server.server_close()
            except Exception:
                pass
        current = threading.current_thread()
        for thread in runtime.threads:
            if thread is current:
                continue
            try:
                thread.join(10)
            except Exception:
                pass
    if failure is not None:
        runtime.failure = failure
        runtime.exit_code = 3
        try:
            print("operator host service failed: " + failure, file=sys.stderr)
        except Exception:
            pass
        runtime.report(SERVICE_STOPPED, exit_code=ERROR_SERVICE_SPECIFIC_ERROR,
                       specific=_SERVICE_SPECIFIC_START_FAILURE)
    else:
        runtime.report(SERVICE_STOPPED)


def _service_main(argc, argv):
    runtime = _RUNTIME
    if runtime is None:
        return
    try:
        _service_run(runtime)
    except BaseException as exc:
        # A ctypes callback must not let an exception escape. Report the real
        # stop and a safe reason rather than pretending the service is running.
        runtime.failure = runtime.failure or _service_reason(exc)
        runtime.exit_code = 3
        try:
            runtime.report(SERVICE_STOPPED, exit_code=ERROR_SERVICE_SPECIFIC_ERROR,
                           specific=_SERVICE_SPECIFIC_START_FAILURE)
        except Exception:
            pass


if os.name == "nt":
    from ctypes import wintypes as wt

    _advapi = ctypes.WinDLL("advapi32", use_last_error=True)
    _SERVICE_MAIN_TYPE = ctypes.WINFUNCTYPE(None, wt.DWORD, ctypes.POINTER(wt.LPWSTR))
    _SERVICE_HANDLER_TYPE = ctypes.WINFUNCTYPE(wt.DWORD, wt.DWORD, wt.DWORD, ctypes.c_void_p,
                                               ctypes.c_void_p)

    class _SERVICE_STATUS(ctypes.Structure):
        _fields_ = [("dwServiceType", wt.DWORD), ("dwCurrentState", wt.DWORD),
                    ("dwControlsAccepted", wt.DWORD), ("dwWin32ExitCode", wt.DWORD),
                    ("dwServiceSpecificExitCode", wt.DWORD), ("dwCheckPoint", wt.DWORD),
                    ("dwWaitHint", wt.DWORD)]

    class _SERVICE_TABLE_ENTRY(ctypes.Structure):
        _fields_ = [("lpServiceName", wt.LPWSTR), ("lpServiceProc", _SERVICE_MAIN_TYPE)]

    _StartServiceCtrlDispatcherW = _advapi.StartServiceCtrlDispatcherW
    _StartServiceCtrlDispatcherW.argtypes = [ctypes.POINTER(_SERVICE_TABLE_ENTRY)]
    _StartServiceCtrlDispatcherW.restype = wt.BOOL
    _RegisterServiceCtrlHandlerExW = _advapi.RegisterServiceCtrlHandlerExW
    _RegisterServiceCtrlHandlerExW.argtypes = [wt.LPCWSTR, _SERVICE_HANDLER_TYPE, ctypes.c_void_p]
    _RegisterServiceCtrlHandlerExW.restype = wt.HANDLE
    _SetServiceStatus = _advapi.SetServiceStatus
    _SetServiceStatus.argtypes = [wt.HANDLE, ctypes.POINTER(_SERVICE_STATUS)]
    _SetServiceStatus.restype = wt.BOOL

    _SERVICE_HANDLER_PROC = _SERVICE_HANDLER_TYPE(_service_control_handler)
    _SERVICE_MAIN_PROC = _SERVICE_MAIN_TYPE(_service_main)

    def _register_service_handler(name, handler):
        return _RegisterServiceCtrlHandlerExW(name, handler, None)

    def _set_service_status(handle, status):
        return bool(_SetServiceStatus(handle, ctypes.byref(status)))

    def _start_service_dispatcher(table):
        return bool(_StartServiceCtrlDispatcherW(table))
else:
    _SERVICE_STATUS = None
    _SERVICE_TABLE_ENTRY = None
    _SERVICE_HANDLER_PROC = None
    _SERVICE_MAIN_PROC = None

    def _register_service_handler(name, handler):
        return None

    def _set_service_status(handle, status):
        return False

    def _start_service_dispatcher(table):
        return False


def main() -> int:
    """Connect to SCM; refuse ordinary console execution with error 1063."""
    if os.name != "nt":
        print("operator host requires the registered Windows service", file=sys.stderr)
        return 2
    global _RUNTIME
    runtime = _ServiceRuntime()
    _RUNTIME = runtime
    table = (_SERVICE_TABLE_ENTRY * 2)()
    table[0].lpServiceName = authority.SERVICE_NAME
    table[0].lpServiceProc = _SERVICE_MAIN_PROC
    # The second entry is already the zero terminator (name NULL, no proc).
    try:
        dispatched = _start_service_dispatcher(table)
        error = ctypes.get_last_error()
    finally:
        _RUNTIME = None
    if not dispatched:
        if error == ERROR_FAILED_SERVICE_CONTROLLER_CONNECT:
            print("operator host is not connected to the Service Control Manager "
                  "(ERROR_FAILED_SERVICE_CONTROLLER_CONNECT 1063); start it as the "
                  "registered Windows service", file=sys.stderr)
        else:
            print("operator host service dispatcher unavailable (Win32 error "
                  + str(error) + ")", file=sys.stderr)
        return 2
    return runtime.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
