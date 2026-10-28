"""test_decision_monitor.py - T10 monitor service base (AC-006/007/015/017).

The module under test (``decision_monitor``) owns the *process-level* half of
the dashboard: the standalone loopback service, its identity/lifecycle, and the
authentication boundary in front of the read/playground routes. This suite
locks the behaviour that the design (D-001, §9) and the T03 review's downstream
contract (F-1/F-4/F-5) require:

1. port selection is deterministic inside ``43170..43269`` and the listener is
   *bound and held* with Windows exclusivity - a full range fails explicitly
   and never kills the occupant;
2. ``.mw/decide-monitor.json`` carries identity only (project/instance/pid/
   pid-start/port/protocol/code fingerprint), the control token lives in the
   separate secret file, and publication is atomic;
3. stale recovery only moves state/secret for a *provably dead* owner, one step
   at a time, after re-reading the identity; alive, recycled-PID, malformed or
   probe-refused state stays untouched with a manual recovery guide;
4. tokens are role separated (control vs page), a boot code is single use and
   expires, long-lived secrets never appear in argv or a URL, and the page
   token cannot shut the instance down or mint a new code;
5. the HTTP boundary is a closed set: exact ``Host``, exact ``Origin`` for
   POSTs, closed ``Sec-Fetch-Site``, 256 KiB body cap, no CORS and no cookies;
6. two projects on one machine keep separate identity, ports and tokens, and
   stopping one leaves the other healthy;
7. only the explicit ``/api/test/submit`` can reach the injected playground;
   opening the page, health polls, history refresh, scaffold and validate make
   zero model calls, and the unwired playground seam answers ``unavailable``
   instead of pretending to work;
8. history responses are fail-closed (no redactor -> no body) and per-row
   ``capture_status`` is preserved while the envelope carries the worst status
   (F-4), and a capture *module* failure is presented apart from "capture not
   enabled" (F-1).

Hermetic: isolated ``tmp_path`` control roots, real stdlib HTTP over loopback,
real ``decide_archive``/``decision_wire`` writers for fixtures, simulated
browser argv only. No real browser, no shared service, no credentials, no
network, no production file touched.
"""

from __future__ import annotations

import contextlib
import errno
import http.client
import json
import os
import pathlib
import socket
import subprocess
import sys
import time

import pytest

import decide_archive
import decision_book
import decision_history
import decision_monitor
import decision_wire as wire
import mw_common

SECRET = "TEST-SECRET-abc123456789"
REDACTOR = wire.SubstringRedactor((SECRET,))

HOST = decision_monitor.HOST


# ---------------------------------------------------------------------------
# Harness
# ---------------------------------------------------------------------------


def _root(tmp_path: pathlib.Path, name: str = "proj") -> pathlib.Path:
    """An isolated control root (shape evidence: ``.agenticdoc`` below it)."""
    root = tmp_path / name
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    return root


def _closed_loopback_port() -> int:
    """A loopback port nothing listens on (the OS can prove a refusal)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.bind((HOST, 0))
        return int(sock.getsockname()[1])
    finally:
        sock.close()


def _listening_port() -> tuple[socket.socket, int]:
    """An unrelated loopback listener held by this test (never a shared service)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    else:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
    sock.bind((HOST, 0))
    sock.listen(16)
    return sock, int(sock.getsockname()[1])


def _hold_isolated_block(size: int = 100) -> tuple[int, list[socket.socket]]:
    """Bind-and-hold a contiguous local block; occupied candidates are left alone.

    The block is deliberately outside the monitor range so the test cannot
    disturb a real monitor instance; no shared service is probed or stopped.
    """
    rejected: list[tuple[int, str]] = []
    for start in (25101, 30101, 35101, 40101, 45101, 47101, 52101, 55101, 28101, 38101):
        socks: list[socket.socket] = []
        try:
            for offset in range(size):
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                try:
                    if sys.platform == "win32" and hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
                    else:
                        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
                    sock.bind((HOST, start + offset))
                    sock.listen(1)
                except OSError:
                    sock.close()
                    raise
                socks.append(sock)
        except OSError as exc:
            for sock in socks:
                sock.close()
            rejected.append((start, exc.__class__.__name__))
            continue
        return start, socks
    pytest.skip(f"no isolated {size}-port block was free; occupiers left untouched: {rejected}")


def _book(dp: str = "dp1-dispatch-type", state: dict | None = None) -> dict:
    """A decision-book-shaped payload (the provider still owns ``check_book``)."""
    fields: dict[str, object] = {
        "schema_version": decision_book.BOOK_SCHEMA_VERSION,
        "decision_point": dp,
    }
    fields.update(state or {})
    return {
        "schema_version": decision_book.BOOK_SCHEMA_VERSION,
        "decision_point": dp,
        "state": fields,
    }


def _publish_stale(root: pathlib.Path, port: int, *, instance_id: str = "stale-instance-001") -> dict:
    """A crashed instance's state/secret pair (provably dead PID + recorded port)."""
    identity = decision_monitor.InstanceIdentity(
        project_id=wire.project_id_for(root),
        instance_id=instance_id,
        pid=_spawn_exit(),
        pid_start_ms=1,
        port=port,
        code_fingerprint=decision_monitor.code_fingerprint(),
    )
    decision_monitor.publish_secret(root, "stale-control-token-value")
    decision_monitor.publish_state(root, identity)
    return identity


def _spawn_exit(script: str = "pass") -> int:
    """PID of a process that has provably exited (``dead`` per the OS probe)."""
    proc = subprocess.Popen([sys.executable, "-c", script])
    proc.wait(timeout=60)
    pid = proc.pid
    if mw_common.process_alive_state(pid) != "dead":
        pytest.skip("could not obtain a provably dead PID on this platform")
    return pid


def _http(
    port: int,
    method: str,
    path: str,
    *,
    token: str | None = None,
    headers: dict[str, str] | None = None,
    body: object = None,
    origin: str | None = None,
    host: str | None = None,
    total_payload: bytes | None = None,
) -> tuple[int, dict[str, str], dict | None, bytes]:
    """One request with full control over ``Host``/``Origin``/auth headers.

    ``total_payload`` sets ``Content-Length`` without sending the body (the
    server must reject oversized bodies before reading them).
    """
    conn = http.client.HTTPConnection(HOST, port, timeout=15)
    try:
        conn.putrequest(method, path, skip_host=True, skip_accept_encoding=True)
        conn.putheader("Host", host if host is not None else f"{HOST}:{port}")
        if token is not None:
            conn.putheader(decision_monitor.TOKEN_HEADER, token)
        if origin is not None:
            conn.putheader("Origin", origin)
        for name, value in (headers or {}).items():
            conn.putheader(name, value)
        if total_payload is not None:
            conn.putheader("Content-Length", str(len(total_payload)))
            conn.endheaders()
        else:
            payload = (
                b""
                if body is None
                else body
                if isinstance(body, bytes)
                else json.dumps(body).encode("utf-8")
            )
            conn.putheader("Content-Length", str(len(payload)))
            conn.endheaders()
            if payload:
                conn.send(payload)
        response = conn.getresponse()
        raw = response.read()
        status = response.status
        header_map = {name.lower(): value for name, value in response.getheaders()}
    finally:
        conn.close()
    parsed: dict | None = None
    if "application/json" in header_map.get("content-type", ""):
        try:
            parsed = json.loads(raw.decode("utf-8"))
        except ValueError:
            parsed = None
    return status, header_map, parsed, raw


@contextlib.contextmanager
def _running(
    root: pathlib.Path,
    *,
    deps: object = None,
    clock: object = None,
    port_range: tuple[int, int] = decision_monitor.PORT_RANGE,
):
    instance = decision_monitor.MonitorInstance(
        root, deps=deps, clock=clock, port_range=port_range
    )
    instance.start()
    try:
        yield instance
    finally:
        instance.stop()


def _page_token(instance) -> str:
    status, _headers, payload, _raw = _http(
        instance.port,
        "POST",
        "/api/bootstrap",
        origin=instance.origin,
        body={"code": instance.boot_code},
    )
    assert status == 200, payload
    return payload["data"]["page_token"]


def _envelope_error(payload: dict | None) -> dict:
    assert payload is not None, "expected a JSON envelope"
    assert payload["ok"] is False
    return payload["error"]


class _SpyPlayground:
    """Records every call; stands in for the T06 playground (no model call)."""

    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def scaffold(self, dp: str) -> dict:
        self.calls.append(("scaffold", dp))
        return {"dp": dp, "required_state_fields": [], "optional_state_fields": []}

    def validate(self, dp: str, book: object) -> dict:
        self.calls.append(("validate", dp, book))
        return {"dp": dp, "issues": []}

    def submit(self, request: dict) -> dict:
        self.calls.append(("submit", request))
        return {"submission_id": request["submit_id"], "state": "running"}

    def submission(self, submission_id: str) -> dict | None:
        self.calls.append(("submission", submission_id))
        return {"submission_id": submission_id, "state": "running"}

    def history(self) -> dict:
        self.calls.append(("history",))
        return {"records": [], "total": 0}


# ---------------------------------------------------------------------------
# Fixtures: real archive + wire rows (no hand-built fold input)
# ---------------------------------------------------------------------------


def _append_raw_line(path: pathlib.Path, row: dict) -> None:
    """Append one schema-v1 row verbatim (a *legacy* carrier: no write-side scrub).

    The read side must treat on-disk text as unproven until its injected
    redactor proves it - the fixture therefore writes the secret unscrubbed.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write((json.dumps(row, ensure_ascii=False) + "\n").encode("utf-8"))


def _seed_legacy_lifecycle(root: pathlib.Path, decision_id: str, *, key: str = "mw-alpha") -> None:
    """An unredacted legacy lifecycle row (pre-review carrier) for one decision."""
    _append_raw_line(
        wire.production_lifecycle_sink(root),
        {
            "schema_version": wire.SCHEMA_VERSION,
            "event_id": wire.new_id(),
            "ts": "2026-10-22T10:00:30+00:00",
            "kind": "lifecycle",
            "scope": "production",
            "project_id": wire.project_id_for(root),
            "key": key,
            "task_key": None,
            "decision_id": decision_id,
            "call_id": None,
            "submission_id": None,
            "origin": "legacy",
            "actor": {"kind": "human", "id": "user-explicit"},
            "answer_source": None,
            "capture_status": None,
            "lifecycle": "human-answer",
            "target": None,
            "supersedes": None,
            "reason": None,
            "answer": None,
            "evidence": None,
            "result": f"legacy unredacted token {SECRET}",
        },
    )


def _seed_history(root: pathlib.Path) -> dict[str, str]:
    """Two production decisions: one with a failed response capture, one ok."""
    archive = root / ".agenticdoc" / "_autopilot" / "decisions.jsonl"
    project_id = wire.project_id_for(root)
    ids: dict[str, str] = {}
    for trigger, key, now in (
        ("t-fail", "mw-alpha", "2026-10-22T10:00:00+00:00"),
        ("t-ok", "mw-beta", "2026-10-22T10:05:00+00:00"),
    ):
        decision_id = f"dp1-dispatch-type:{trigger}"
        decide_archive.append_decide(
            archive,
            dp="dp1-dispatch-type",
            key=key,
            task_key=None,
            trigger_id=trigger,
            state={"a": 1},
            questions_version="q-1234abcd",
            available=True,
            authority="advisory",
            answer={"q-task": {"value": "fix", "confidence": 0.9}},
            mode="auto",
            transport="timi-decisions",
            model="jev-latest",
            attempts=1,
            latency_ms=12,
            confidence=0.9,
            confidence_source="api",
            now=now,
        )
        ids[key] = decision_id

    _seed_legacy_lifecycle(root, ids["mw-alpha"])

    def scope_for(decision_id: str, key: str) -> wire.WireScope:
        return wire.WireScope(
            sink=wire.production_wire_sink(root),
            project_id=project_id,
            scope_kind="production",
            origin="cli",
            decision_id=decision_id,
            dp="dp1-dispatch-type",
            key=key,
            redact=REDACTOR,
            warn=lambda message: None,
        )

    failing = scope_for(ids["mw-alpha"], "mw-alpha")
    call = wire.new_call()
    wire.record_attempt_start(
        failing, call, request=b'{"state":{"a":1}}', url_path="/v1/decisions", model="jev-latest"
    )
    wire.record_attempt_end(
        failing,
        call,
        response=wire.Capture.not_recorded(wire_len=12),
        latency_ms=5,
        http_status=200,
        error_class="response-read",
    )
    wire.append_event(
        failing,
        wire.call_end_event(failing, call, attempts=1, latency_ms=9, available=True),
    )
    wire.append_event(failing, wire.decision_end_event(failing, status="ok", archive="created", call=call))

    ok = scope_for(ids["mw-beta"], "mw-beta")
    call2 = wire.new_call()
    wire.record_attempt_start(
        ok, call2, request=b'{"state":{"a":1}}', url_path="/v1/decisions", model="jev-latest"
    )
    wire.record_attempt_end(
        ok,
        call2,
        response=b'{"answers":{"q-task":"fix"}}',
        latency_ms=4,
        http_status=200,
        content_type="application/json",
    )
    wire.append_event(ok, wire.call_end_event(ok, call2, attempts=1, latency_ms=8, available=True))
    wire.append_event(ok, wire.decision_end_event(ok, status="ok", archive="created", call=call2))
    return ids


# ---------------------------------------------------------------------------
# Port range: deterministic candidates, bind-and-hold, exclusive
# ---------------------------------------------------------------------------


def test_port_candidates_are_deterministic_and_in_range():
    pid = wire.project_id_for("project-a")
    first = decision_monitor.port_candidates(pid)
    second = decision_monitor.port_candidates(pid)
    assert first == second
    assert len(first) == decision_monitor.PORT_RANGE[1] - decision_monitor.PORT_RANGE[0] + 1
    assert len(set(first)) == len(first)
    assert all(decision_monitor.PORT_RANGE[0] <= port <= decision_monitor.PORT_RANGE[1] for port in first)
    other = decision_monitor.port_candidates(wire.project_id_for("project-b"))
    assert set(first) == set(other)  # same range, different starting point
    assert first[0] != other[0]


def test_bind_holds_first_free_candidate_and_skips_occupied():
    pid = wire.project_id_for("hold-test")
    candidates = decision_monitor.port_candidates(pid)
    try:
        sock, held_port = decision_monitor.bind_listener(
            project_id=pid, port_range=(candidates[0], candidates[0])
        )
    except decision_monitor.MonitorError:
        pytest.skip("the first candidate port is occupied by another process")
    try:
        sock2, port2 = decision_monitor.bind_listener(project_id=pid)
        try:
            assert port2 != held_port
            assert port2 in candidates
            # The held port is skipped, never rebound.
            assert candidates.index(port2) >= 1
        finally:
            sock2.close()
    finally:
        sock.close()


def test_single_occupied_candidate_fails_explicitly_without_touching_the_occupant():
    pid = wire.project_id_for("exhaust-test")
    holder = None
    for port in decision_monitor.port_candidates(pid):
        try:
            holder = decision_monitor.bind_listener(project_id=pid, port_range=(port, port))
        except decision_monitor.MonitorError:
            continue
        break
    assert holder is not None
    sock, held_port = holder
    try:
        with pytest.raises(decision_monitor.MonitorError) as exc:
            decision_monitor.bind_listener(project_id=pid, port_range=(held_port, held_port))
        assert exc.value.kind == "range-exhausted"
        assert str(held_port) in exc.value.message
        # The occupant is untouched and still reachable: never kill/steal.
        probe = socket.create_connection((HOST, held_port), timeout=2)
        probe.close()
        assert sock.fileno() != -1
    finally:
        sock.close()


def test_full_100_port_isolated_range_exhaustion_leaves_every_occupant_alive():
    """Exercise the whole candidate loop: 100 held ports, not one stand-in."""
    start, holders = _hold_isolated_block(100)
    assert len(holders) == 100
    try:
        with pytest.raises(decision_monitor.MonitorError) as exc:
            decision_monitor.bind_listener(
                project_id=wire.project_id_for("exhaust-100"),
                port_range=(start, start + 99),
            )
        error = exc.value
        assert error.kind == "range-exhausted"
        assert error.details["attempted_count"] == 100
        assert len(error.details["attempted"]) == 20  # echo truncates, the loop does not
        assert f"{start}..{start + 99}" in error.message
        for sock in holders:
            assert sock.fileno() != -1
        for port in range(start, start + 100):
            probe = socket.create_connection((HOST, port), timeout=3)
            probe.close()
    finally:
        for sock in holders:
            sock.close()


def test_probe_recorded_port_reports_a_real_refusal_and_maps_windows_code():
    refused = decision_monitor.probe_recorded_port(_closed_loopback_port())
    assert refused["result"] == "refused", refused
    assert refused["errno"] in (errno.ECONNREFUSED, 10061)
    # The Windows code is mapped explicitly, not guessed from a generic OSError.
    assert errno.ECONNREFUSED in decision_monitor.REFUSED_ERRNOS
    assert 10061 in decision_monitor.REFUSED_ERRNOS

    listener, port = _listening_port()
    try:
        served = decision_monitor.probe_recorded_port(port)
        assert served["result"] == "connected", served
    finally:
        listener.close()

    assert decision_monitor.classify_connect_error(TimeoutError("timed out")) == "unknown"
    assert decision_monitor.classify_connect_error(OSError(errno.ETIMEDOUT, "timed out")) == "unknown"
    assert decision_monitor.classify_connect_error(OSError(errno.EACCES, "denied")) == "unknown"
    assert decision_monitor.classify_connect_error(OSError(10061, "refused")) == "refused"


def test_listener_is_exclusive_against_a_reuseaddr_rebinder():
    pid = wire.project_id_for("exclusive-test")
    sock, port = None, None
    for candidate in decision_monitor.port_candidates(pid):
        try:
            sock, port = decision_monitor.bind_listener(
                project_id=pid, port_range=(candidate, candidate)
            )
            break
        except decision_monitor.MonitorError:
            continue
    assert sock is not None
    try:
        other = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            other.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            with pytest.raises(OSError):
                other.bind((HOST, port))
        finally:
            other.close()
    finally:
        sock.close()


# ---------------------------------------------------------------------------
# State / secret publication
# ---------------------------------------------------------------------------


def test_state_file_holds_identity_only_and_secret_stays_separate(tmp_path):
    root = _root(tmp_path)
    control_token = decision_monitor.generate_token()
    decision_monitor.publish_secret(root, control_token)
    identity = decision_monitor.InstanceIdentity(
        project_id="a" * 16,
        instance_id="b" * 16,
        pid=os.getpid(),
        pid_start_ms=1234,
        port=decision_monitor.PORT_RANGE[0],
        code_fingerprint=decision_monitor.code_fingerprint(),
    )
    decision_monitor.publish_state(root, identity)

    raw_state = decision_monitor.state_path(root).read_bytes()
    text = raw_state.decode("utf-8")
    payload = json.loads(text)
    assert payload["schema"] == decision_monitor.STATE_SCHEMA
    assert payload["instance_id"] == "b" * 16
    assert payload["protocol_version"] == decision_monitor.PROTOCOL_VERSION
    assert control_token not in text
    assert "token" not in {key.lower() for key in payload}
    assert decision_monitor.read_secret(root) == control_token
    state, problem = decision_monitor.read_state(root)
    assert problem is None
    assert state == payload
    # Atomic publication leaves no temp file behind.
    leftovers = [p.name for p in (root / ".mw").iterdir() if p.name.endswith(".tmp")]
    assert leftovers == []


def test_secret_file_is_owner_only_on_posix(tmp_path):
    root = _root(tmp_path)
    decision_monitor.publish_secret(root, decision_monitor.generate_token())
    if sys.platform == "win32":
        pytest.skip("POSIX mode bits are not the Windows isolation boundary")
    assert decision_monitor.secret_path(root).stat().st_mode & 0o777 == 0o600


# ---------------------------------------------------------------------------
# HTTP boundary: identity, roles, origin, headers, limits
# ---------------------------------------------------------------------------


def test_control_token_can_mint_a_fresh_single_use_window_code(tmp_path):
    root = _root(tmp_path)
    with _running(root) as instance:
        status, _headers, payload, _raw = _http(
            instance.port, "POST", "/api/window", token=instance.control_token, body={}
        )
        assert status == 200
        url = payload["data"]["url"]
        assert url.startswith(f"http://{HOST}:{instance.port}/#boot=")
        assert instance.control_token not in url
        fresh_code = url.split("#boot=", 1)[1]
        assert fresh_code != instance.boot_code
        status, _headers, payload, _raw = _http(
            instance.port, "POST", "/api/bootstrap", origin=instance.origin, body={"code": fresh_code}
        )
        assert status == 200
        assert payload["data"]["page_token"]


def test_health_requires_control_token_and_reports_identity(tmp_path):
    root = _root(tmp_path)
    with _running(root) as instance:
        status, _headers, payload, _raw = _http(instance.port, "GET", "/api/health")
        assert status == 401
        assert _envelope_error(payload)["code"] == "missing-token"

        status, _headers, payload, _raw = _http(
            instance.port, "GET", "/api/health", token=instance.control_token
        )
        assert status == 200
        data = payload["data"]
        assert data["project_id"] == wire.project_id_for(root)
        assert data["instance_id"] == instance.identity.instance_id
        assert data["pid"] == os.getpid()
        assert data["port"] == instance.port
        assert data["protocol_version"] == decision_monitor.PROTOCOL_VERSION
        assert data["code_fingerprint"] == decision_monitor.code_fingerprint()
        assert data["capture"]["state"] == "disabled"
        assert data["playground"]["state"] == "unavailable"

        status, _headers, payload, _raw = _http(
            instance.port, "GET", "/api/health", token="not-the-token"
        )
        assert status == 401
        assert _envelope_error(payload)["code"] == "invalid-token"


def test_capture_disabled_and_capture_module_unavailable_are_distinct(tmp_path):
    disabled_root = _root(tmp_path, "disabled")
    with _running(disabled_root) as instance:
        _status, _headers, payload, _raw = _http(
            instance.port, "GET", "/api/health", token=instance.control_token
        )
        assert payload["data"]["capture"] == {"state": "disabled", "detail": None}

    unavailable_root = _root(tmp_path, "unavailable")
    deps = decision_monitor.MonitorDeps(
        capture_state="unavailable", capture_detail="decision_wire import failed"
    )
    with _running(unavailable_root, deps=deps) as instance:
        _status, _headers, payload, _raw = _http(
            instance.port, "GET", "/api/health", token=instance.control_token
        )
        assert payload["data"]["capture"]["state"] == "unavailable"
        assert "import" in payload["data"]["capture"]["detail"]


def test_host_header_must_be_exact_loopback_and_port(tmp_path):
    root = _root(tmp_path)
    with _running(root) as instance:
        for host in ("localhost:%d" % instance.port, HOST, f"127.0.0.1:{instance.port + 1}", "evil.example"):
            status, _headers, payload, _raw = _http(
                instance.port, "GET", "/", host=host
            )
            assert status == 403, host
            assert _envelope_error(payload)["code"] == "host-not-allowed"


def test_bootstrap_is_single_use_origin_bound_and_expires(tmp_path):
    root = _root(tmp_path)
    clock = {"now": 100.0}
    with _running(root, clock=lambda: clock["now"]) as instance:
        code = instance.boot_code
        # Missing / wrong Origin are refused and do not consume the code.
        status, _headers, payload, _raw = _http(
            instance.port, "POST", "/api/bootstrap", body={"code": code}
        )
        assert status == 403
        assert _envelope_error(payload)["code"] == "origin-not-allowed"
        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/bootstrap",
            origin="http://evil.example",
            body={"code": code},
        )
        assert status == 403

        status, _headers, payload, _raw = _http(
            instance.port, "POST", "/api/bootstrap", origin=instance.origin, body={"code": code}
        )
        assert status == 200
        page_token = payload["data"]["page_token"]
        assert isinstance(page_token, str) and len(page_token) >= 32
        assert page_token != instance.control_token

        # Replay is refused: one code, one token.
        status, _headers, payload, _raw = _http(
            instance.port, "POST", "/api/bootstrap", origin=instance.origin, body={"code": code}
        )
        assert status == 401
        assert _envelope_error(payload)["code"] == "bad-boot-code"

        # A fresh code expires after BOOT_CODE_TTL_S.
        fresh = instance.new_boot_code()
        clock["now"] += decision_monitor.BOOT_CODE_TTL_S + 1
        status, _headers, payload, _raw = _http(
            instance.port, "POST", "/api/bootstrap", origin=instance.origin, body={"code": fresh}
        )
        assert status == 401
        assert _envelope_error(payload)["code"] == "bad-boot-code"


def test_window_url_keeps_the_boot_code_in_the_fragment_only(tmp_path):
    root = _root(tmp_path)
    profile = tmp_path / "profile"
    with _running(root) as instance:
        url = instance.bootstrap_url()
        assert url.startswith(f"http://{HOST}:{instance.port}/")
        pre_fragment, _, fragment = url.partition("#")
        assert instance.boot_code in fragment
        assert instance.control_token not in url
        assert instance.control_token not in pre_fragment

        argv = decision_monitor.build_chromium_argv(
            "C:/browsers/chrome.exe",
            port=instance.port,
            boot_code=instance.boot_code,
            profile_dir=profile,
        )
        assert argv[0] == "C:/browsers/chrome.exe"
        app_args = [arg for arg in argv if arg.startswith("--app=")]
        assert len(app_args) == 1
        assert "#boot=" in app_args[0]
        assert any(arg.startswith("--user-data-dir=") for arg in argv)
        assert all(instance.control_token not in arg for arg in argv)
        assert not any(arg in (instance.control_token, "--no-sandbox") for arg in argv)


def test_sec_fetch_site_closed_set_and_origin_rules(tmp_path):
    root = _root(tmp_path)
    with _running(root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        page_token = _page_token(instance)
        for site in ("cross-site", "same-site", "bogus-value"):
            status, _headers, payload, _raw = _http(
                instance.port,
                "GET",
                "/api/dps",
                token=page_token,
                headers={"Sec-Fetch-Site": site},
            )
            assert status == 403, site
            assert _envelope_error(payload)["code"] == "cross-site-blocked"
        for site in ("same-origin", "none"):
            status, _headers, payload, _raw = _http(
                instance.port,
                "GET",
                "/api/dps",
                token=page_token,
                headers={"Sec-Fetch-Site": site},
            )
            assert status == 200, site
        # A page token POST needs the exact Origin.
        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/test/scaffold",
            token=page_token,
            body={"dp": "dp1-dispatch-type"},
        )
        assert status == 403
        assert _envelope_error(payload)["code"] == "origin-not-allowed"


def test_page_token_cannot_shutdown_or_mint_a_new_code(tmp_path):
    root = _root(tmp_path)
    with _running(root) as instance:
        page_token = _page_token(instance)
        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/shutdown",
            token=page_token,
            origin=instance.origin,
            body={},
        )
        assert status == 403
        assert _envelope_error(payload)["code"] == "wrong-role"
        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/window",
            token=page_token,
            origin=instance.origin,
            body={},
        )
        assert status == 403
        assert _envelope_error(payload)["code"] == "wrong-role"
        assert decision_monitor.health(instance.port, instance.control_token) is not None


def test_control_token_cannot_use_page_routes(tmp_path):
    root = _root(tmp_path)
    with _running(root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        status, _headers, payload, _raw = _http(
            instance.port, "GET", "/api/history", token=instance.control_token
        )
        assert status == 403
        assert _envelope_error(payload)["code"] == "wrong-role"
        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/bootstrap",
            token=instance.control_token,
            origin=instance.origin,
            body={"code": "irrelevant"},
        )
        assert status == 401  # the code is what authenticates bootstrap


def test_no_cors_no_cookies_and_security_headers(tmp_path):
    root = _root(tmp_path)
    with _running(root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        responses = [
            _http(instance.port, "GET", "/"),
            _http(instance.port, "GET", "/api/health"),
            _http(instance.port, "GET", "/api/health", token=instance.control_token),
            _http(instance.port, "GET", "/nope"),
        ]
        for status, headers, _payload, raw in responses:
            assert "access-control-allow-origin" not in headers
            assert "access-control-allow-credentials" not in headers
            assert "set-cookie" not in headers
            assert headers.get("x-content-type-options") == "nosniff"
            assert headers.get("referrer-policy") == "no-referrer"
            assert headers.get("cache-control") == "no-store"
            csp = headers.get("content-security-policy", "")
            assert "default-src 'none'" in csp
            assert "frame-ancestors 'none'" in csp
            assert "base-uri 'none'" in csp
            if status != 200:
                assert raw

        status, headers, _payload, raw = responses[0]
        assert status == 200
        assert "text/html" in headers.get("content-type", "")
        assert b"<" in raw


def test_body_limit_and_chunked_rejection(tmp_path):
    root = _root(tmp_path)
    with _running(root) as instance:
        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/bootstrap",
            origin=instance.origin,
            total_payload=b"x" * (decision_monitor.BODY_LIMIT_BYTES + 1),
        )
        assert status == 413
        assert _envelope_error(payload)["code"] == "body-too-large"

        conn = http.client.HTTPConnection(HOST, instance.port, timeout=10)
        try:
            conn.putrequest("POST", "/api/bootstrap", skip_host=True, skip_accept_encoding=True)
            conn.putheader("Host", f"{HOST}:{instance.port}")
            conn.putheader("Origin", instance.origin)
            conn.putheader("Transfer-Encoding", "chunked")
            conn.endheaders()
            conn.send(b"5\r\nhello\r\n0\r\n\r\n")
            response = conn.getresponse()
            raw = response.read()
            status = response.status
        finally:
            conn.close()
        assert status == 400
        assert json.loads(raw.decode("utf-8"))["error"]["code"] == "chunked-unsupported"


def test_unknown_routes_and_wrong_methods_are_rejected(tmp_path):
    root = _root(tmp_path)
    with _running(root) as instance:
        status, _headers, payload, _raw = _http(instance.port, "GET", "/api/act")
        assert status == 404
        assert _envelope_error(payload)["code"] == "not-found"
        status, _headers, payload, _raw = _http(instance.port, "POST", "/api/history", body={})
        assert status == 405
        assert _envelope_error(payload)["code"] == "method-not-allowed"
        status, _headers, payload, _raw = _http(instance.port, "OPTIONS", "/api/health")
        assert status == 405
        status, _headers, payload, _raw = _http(instance.port, "GET", "/api/test/submit")
        assert status == 405


def test_shutdown_is_control_only_and_really_stops_the_instance(tmp_path):
    root = _root(tmp_path)
    instance = decision_monitor.MonitorInstance(root)
    instance.start()
    port = instance.port
    try:
        status, _headers, payload, _raw = _http(
            port,
            "POST",
            "/api/shutdown",
            token=instance.control_token,
            origin=instance.origin,
            body={},
        )
        assert status == 200
        assert payload["data"]["stopping"] is True
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            probe.settimeout(0.2)
            try:
                if probe.connect_ex((HOST, port)) != 0:
                    break
            finally:
                probe.close()
            time.sleep(0.02)
        else:
            pytest.fail("port still open after an authenticated shutdown")
        assert decision_monitor.read_state(root)[0] is None
        assert decision_monitor.read_secret(root) is None
        with pytest.raises(OSError):
            socket.create_connection((HOST, port), timeout=1).close()
    finally:
        instance.stop()


# ---------------------------------------------------------------------------
# History route: fail-closed redaction, per-row capture status, opaque ids
# ---------------------------------------------------------------------------


def test_history_is_fail_closed_without_a_redactor_and_redacts_with_one(tmp_path):
    """T07's free-text policy is injected, never re-implemented by the service.

    Without a redactor the fold withholds unprovable free text (counted, never
    echoed) - the service must not turn that into a crash, a fake value or a
    raw leak. With a redactor the same fixture is redacted and visibly marked.
    """
    unredacted_root = _root(tmp_path, "unredacted")
    _seed_history(unredacted_root)
    with _running(unredacted_root) as instance:
        page_token = _page_token(instance)
        status, _headers, payload, raw = _http(
            instance.port, "GET", "/api/history", token=page_token
        )
        assert status == 200
        assert SECRET.encode() not in raw
        assert payload["data"]["redaction"]["enabled"] is False
        assert payload["data"]["total"] == 2
        opaque = payload["data"]["records"][0]["opaque_id"]
        status, _headers, detail, raw_detail = _http(
            instance.port, "GET", f"/api/history/{opaque}", token=page_token
        )
        assert status == 200
        assert SECRET.encode() not in raw_detail
        assert detail["data"]["redaction"]["enabled"] is False
        assert detail["data"]["stages"]["human_answer"]["result"] is None

    redacted_root = _root(tmp_path, "redacted")
    _seed_history(redacted_root)
    with _running(redacted_root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        page_token = _page_token(instance)
        status, _headers, payload, raw = _http(
            instance.port, "GET", "/api/history", token=page_token
        )
        assert status == 200
        assert SECRET.encode() not in raw
        records = payload["data"]["records"]
        assert len(records) == 2
        assert payload["data"]["redaction"]["enabled"] is True
        assert payload["data"]["redaction"]["records_with_substitutions"] >= 1
        for record in records:
            opaque = record["opaque_id"]
            status, _headers, detail, raw_detail = _http(
                instance.port, "GET", f"/api/history/{opaque}", token=page_token
            )
            assert status == 200
            assert SECRET.encode() not in raw_detail
            assert payload["data"]["stats"]["production_records"] == 2
            human_answer = detail["data"]["stages"]["human_answer"]
            if human_answer["state"] == "recorded":
                assert "<redacted>" in human_answer["result"]
                assert SECRET not in human_answer["result"]


def test_history_filters_and_per_row_capture_status_with_worst_envelope(tmp_path):
    root = _root(tmp_path)
    _seed_history(root)
    with _running(root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        page_token = _page_token(instance)
        status, _headers, payload, _raw = _http(
            instance.port, "GET", "/api/history?key=mw-alpha", token=page_token
        )
        assert status == 200
        data = payload["data"]
        assert data["total"] == 1
        assert data["filters"]["key"] == "mw-alpha"
        record = data["records"][0]
        assert record["capture_status"] == "failed"
        assert record["calls"][0]["capture_status"] == "failed"
        # F-4: the envelope carries the worst status, the row keeps its own.
        assert payload["capture_status"] == "failed"

        status, _headers, payload, _raw = _http(
            instance.port, "GET", "/api/history?key=mw-beta", token=page_token
        )
        assert status == 200
        record = payload["data"]["records"][0]
        assert record["capture_status"] == "ok"
        assert record["calls"][0]["capture_status"] == "ok"

        status, _headers, payload, _raw = _http(
            instance.port,
            "GET",
            "/api/history?key=../../etc/passwd",
            token=page_token,
        )
        assert status == 400
        assert _envelope_error(payload)["code"] == "invalid-filter"

        status, _headers, payload, _raw = _http(
            instance.port, "GET", "/api/history?limit=500", token=page_token
        )
        assert status == 400
        status, _headers, payload, _raw = _http(
            instance.port, "GET", "/api/history?unknown=1", token=page_token
        )
        assert status == 400
        assert _envelope_error(payload)["code"] == "unknown-query"


def test_history_read_side_contract_is_jointly_verified_with_current_history_api(tmp_path):
    """T07's live ``redact=`` injection and marks, consumed through the monitor."""
    root = _root(tmp_path)
    _seed_history(root)
    redacted = decision_history.load_history(root, redact=REDACTOR)
    redacted_marks = [record.redaction for record in redacted.page(scope="production").records]
    assert redacted_marks and all(mark.enabled for mark in redacted_marks)
    assert any(mark.substitutions for mark in redacted_marks)

    withheld = decision_history.load_history(root, redact=None)
    withheld_marks = [record.redaction for record in withheld.page(scope="production").records]
    assert withheld_marks and not any(mark.enabled for mark in withheld_marks)
    assert any(mark.omitted_fields or mark.dropped_fields for mark in withheld_marks)

    with _running(root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        page_token = _page_token(instance)
        status, _headers, payload, raw = _http(
            instance.port, "GET", "/api/history", token=page_token
        )
        assert status == 200
        assert SECRET.encode() not in raw
        summary = payload["data"]["redaction"]
        assert summary["enabled"] is True
        assert summary["records_with_substitutions"] == sum(
            1 for mark in redacted_marks if mark.substitutions
        )
        assert summary["records_with_omissions"] == sum(
            1 for mark in redacted_marks if mark.omitted_fields
        )


def test_history_detail_is_opaque_id_only(tmp_path):
    root = _root(tmp_path)
    ids = _seed_history(root)
    with _running(root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        page_token = _page_token(instance)
        for path in (
            f"/api/history/{ids['mw-alpha']}",
            "/api/history/h-../../etc/passwd",
            "/api/history/h-0000000000000000000",
        ):
            status, _headers, payload, _raw = _http(
                instance.port, "GET", path, token=page_token
            )
            assert status == 404, path
            assert _envelope_error(payload)["code"] == "not-found"


# ---------------------------------------------------------------------------
# Playground seam: explicit submit only, closed keys, honest "unavailable"
# ---------------------------------------------------------------------------


def test_playground_routes_are_unavailable_without_a_provider(tmp_path):
    root = _root(tmp_path)
    with _running(root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        page_token = _page_token(instance)
        requests = [
            ("POST", "/api/test/scaffold", {"dp": "dp1-dispatch-type"}),
            ("POST", "/api/test/validate", {"dp": "dp1-dispatch-type", "book": {"dp": "dp1-dispatch-type"}}),
            (
                "POST",
                "/api/test/submit",
                {
                    "dp": "dp1-dispatch-type",
                    "book": {"dp": "dp1-dispatch-type"},
                    "submit_id": "sub-1",
                    "observe_only": True,
                },
            ),
            ("GET", "/api/test/submissions/sub-1", None),
            ("GET", "/api/test/history", None),
        ]
        for method, path, body in requests:
            status, _headers, payload, _raw = _http(
                instance.port,
                method,
                path,
                token=page_token,
                origin=instance.origin,
                body=body,
            )
            assert status == 503, path
            error = _envelope_error(payload)
            assert error["code"] == "playground-unavailable"
            assert "playground" in error["message"].lower()


def test_playground_requires_the_redactor_before_any_provider_call(tmp_path):
    root = _root(tmp_path)
    spy = _SpyPlayground()
    # A provider is injected, but no credential redactor: fail closed, zero calls.
    deps = decision_monitor.MonitorDeps(playground=spy)
    with _running(root, deps=deps) as instance:
        page_token = _page_token(instance)
        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/test/submit",
            token=page_token,
            origin=instance.origin,
            body={
                "dp": "dp1-dispatch-type",
                "book": {"dp": "dp1-dispatch-type"},
                "submit_id": "sub-1",
                "observe_only": True,
            },
        )
        assert status == 503
        assert _envelope_error(payload)["code"] == "playground-redactor-unavailable"
        assert spy.calls == []
        status, _headers, payload, _raw = _http(
            instance.port, "GET", "/api/health", token=instance.control_token
        )
        assert payload["data"]["playground"]["state"] == "unavailable"
        assert "redactor" in payload["data"]["playground"]["detail"]


def test_submit_is_closed_set_and_refuses_execution_or_authorization_fields(tmp_path):
    root = _root(tmp_path)
    spy = _SpyPlayground()
    deps = decision_monitor.MonitorDeps(redactor=REDACTOR, playground=spy)
    with _running(root, deps=deps) as instance:
        page_token = _page_token(instance)
        base = {
            "dp": "dp1-dispatch-type",
            "book": _book(),
            "submit_id": "sub-1",
            "observe_only": True,
        }

        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/test/submit",
            token=page_token,
            origin=instance.origin,
            body={**base, "act": "apply"},
        )
        assert status == 400
        assert _envelope_error(payload)["code"] == "forbidden-field"
        assert spy.calls == []

        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/test/submit",
            token=page_token,
            origin=instance.origin,
            body={**base, "unknown": 1},
        )
        assert status == 400
        assert _envelope_error(payload)["code"] == "unknown-field"
        assert spy.calls == []

        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/test/submit",
            token=page_token,
            origin=instance.origin,
            body={**base, "observe_only": False},
        )
        assert status == 400
        assert _envelope_error(payload)["code"] == "invalid-field"
        assert spy.calls == []

        missing = dict(base)
        del missing["submit_id"]
        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/test/submit",
            token=page_token,
            origin=instance.origin,
            body=missing,
        )
        assert status == 400
        assert _envelope_error(payload)["code"] == "missing-field"
        assert spy.calls == []

        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/test/submit",
            token=page_token,
            origin=instance.origin,
            body=base,
        )
        assert status == 200
        assert [call[0] for call in spy.calls] == ["submit"]
        forwarded = spy.calls[0][1]
        assert forwarded["submit_id"] == "sub-1"
        assert forwarded["observe_only"] is True
        assert "act" not in forwarded
        assert payload["data"]["submission_id"] == "sub-1"


def test_submit_refuses_nested_execution_fields_before_any_provider_call(tmp_path):
    """Nested smuggling is refused by the seam, not only by the T06 provider."""
    root = _root(tmp_path)
    spy = _SpyPlayground()
    deps = decision_monitor.MonitorDeps(redactor=REDACTOR, playground=spy)
    smuggled = {
        "state field": _book(state={"act": "apply"}),
        "deep state field": _book(state={"nested": {"authorization": "grant"}}),
        "context slot": {**_book(), "context": {"command": "rm -rf /"}},
        "envelope": {**_book(), "executor": "spawn"},
    }
    with _running(root, deps=deps) as instance:
        page_token = _page_token(instance)
        for label, book in smuggled.items():
            status, _headers, payload, _raw = _http(
                instance.port,
                "POST",
                "/api/test/submit",
                token=page_token,
                origin=instance.origin,
                body={
                    "dp": "dp1-dispatch-type",
                    "book": book,
                    "submit_id": "sub-nested",
                    "observe_only": True,
                },
            )
            assert status == 400, label
            assert _envelope_error(payload)["code"] == "forbidden-field", label
        assert spy.calls == []


def test_submit_accepts_registered_typed_fields_whose_names_look_forbidden(tmp_path):
    """No blind recursion: dp12 action.command / dp24 project.path are real fields."""
    root = _root(tmp_path)
    spy = _SpyPlayground()
    deps = decision_monitor.MonitorDeps(redactor=REDACTOR, playground=spy)
    books = [
        (
            "dp12-destructive",
            _book(
                "dp12-destructive",
                {"action.command": "rm -rf build", "action.targets": ["build"]},
            ),
        ),
        (
            "dp24-pi-trust",
            _book("dp24-pi-trust", {"project.path": "/repo", "project.trust_state": "trusted"}),
        ),
        (
            "dp1-dispatch-type",
            _book("dp1-dispatch-type", {"history": {"command": "archived", "exec": 1}}),
        ),
    ]
    with _running(root, deps=deps) as instance:
        page_token = _page_token(instance)
        for dp, book in books:
            status, _headers, payload, _raw = _http(
                instance.port,
                "POST",
                "/api/test/submit",
                token=page_token,
                origin=instance.origin,
                body={
                    "dp": dp,
                    "book": book,
                    "submit_id": "sub-typed",
                    "observe_only": True,
                },
            )
            assert status == 200, (dp, payload)
            assert payload["ok"] is True, (dp, payload)
        assert [call[0] for call in spy.calls] == ["submit", "submit", "submit"]


def test_submit_refuses_an_unregistered_dp_before_any_provider_call(tmp_path):
    root = _root(tmp_path)
    spy = _SpyPlayground()
    deps = decision_monitor.MonitorDeps(redactor=REDACTOR, playground=spy)
    with _running(root, deps=deps) as instance:
        page_token = _page_token(instance)
        status, _headers, payload, _raw = _http(
            instance.port,
            "POST",
            "/api/test/submit",
            token=page_token,
            origin=instance.origin,
            body={
                "dp": "dp99-not-registered",
                "book": _book("dp99-not-registered"),
                "submit_id": "sub-unknown",
                "observe_only": True,
            },
        )
        assert status == 400
        assert _envelope_error(payload)["code"] == "invalid-field"
        assert spy.calls == []


def test_playground_seam_declares_the_provider_book_obligations():
    """The seam text pins T06's mandatory check_book duties (closed/type/enum/secret)."""
    obligations = " ".join(decision_monitor.PLAYGROUND_PROVIDER_OBLIGATIONS).lower()
    assert "check_book" in obligations
    for requirement in ("closed", "type", "enum", "secret"):
        assert requirement in obligations
    assert callable(decision_book.check_book)


def test_passive_routes_never_reach_submit(tmp_path):
    root = _root(tmp_path)
    _seed_history(root)
    spy = _SpyPlayground()
    deps = decision_monitor.MonitorDeps(redactor=REDACTOR, playground=spy)
    with _running(root, deps=deps) as instance:
        page_token = _page_token(instance)
        for _ in range(3):
            _http(instance.port, "GET", "/")
            _http(instance.port, "GET", "/api/health", token=instance.control_token)
            _http(instance.port, "GET", "/api/history", token=page_token)
            _http(instance.port, "GET", "/api/dps", token=page_token)
        _http(
            instance.port,
            "POST",
            "/api/test/scaffold",
            token=page_token,
            origin=instance.origin,
            body={"dp": "dp1-dispatch-type"},
        )
        _http(
            instance.port,
            "POST",
            "/api/test/validate",
            token=page_token,
            origin=instance.origin,
            body={"dp": "dp1-dispatch-type", "book": {"dp": "dp1-dispatch-type"}},
        )
        names = [call[0] for call in spy.calls]
        assert "submit" not in names
        assert names.count("scaffold") == 1
        assert names.count("validate") == 1


def test_dps_route_is_read_only_registry_and_authorization(tmp_path):
    root = _root(tmp_path)
    with _running(root, deps=decision_monitor.MonitorDeps(redactor=REDACTOR)) as instance:
        page_token = _page_token(instance)
        status, _headers, payload, _raw = _http(
            instance.port, "GET", "/api/dps", token=page_token
        )
        assert status == 200
        data = payload["data"]
        assert len(data["points"]) == 25
        assert {point["id"] for point in data["points"]} >= {
            "dp1-dispatch-type",
            "dp25-signoff-conclusion",
        }
        first = data["points"][0]
        for name in ("tier", "enabled", "mode", "config_source"):
            assert name in first
        assert data["transport"]["state"] == "unknown"


# ---------------------------------------------------------------------------
# Lifecycle: reuse, start lock, stale recovery, project isolation
# ---------------------------------------------------------------------------


def test_two_projects_keep_identity_tokens_and_ports_separate(tmp_path):
    root_a = _root(tmp_path, "a")
    root_b = _root(tmp_path, "b")
    with _running(root_a) as first, _running(root_b) as second:
        assert first.port != second.port
        assert first.identity.project_id != second.identity.project_id
        assert first.control_token != second.control_token
        # A's token does not authenticate B.
        status, _headers, payload, _raw = _http(
            second.port, "GET", "/api/health", token=first.control_token
        )
        assert status == 401
        # A's state file is its own.
        state_a, _problem = decision_monitor.read_state(root_a)
        state_b, _problem = decision_monitor.read_state(root_b)
        assert state_a["instance_id"] == first.identity.instance_id
        assert state_b["instance_id"] == second.identity.instance_id
        assert state_a["port"] == first.port
        assert state_b["port"] == second.port

        first.stop()
        assert decision_monitor.health(second.port, second.control_token) is not None
        assert decision_monitor.read_state(root_a)[0] is None
        assert decision_monitor.read_state(root_b)[0] is not None


def test_ensure_instance_reuses_a_healthy_instance_without_rewriting_state(tmp_path):
    root = _root(tmp_path)
    instance = decision_monitor.ensure_instance(root)
    try:
        state_before = decision_monitor.state_path(root).read_bytes()
        secret_before = decision_monitor.secret_path(root).read_bytes()
        again = decision_monitor.ensure_instance(root)
        try:
            assert isinstance(again, decision_monitor.AttachedInstance)
            assert again.identity.instance_id == instance.identity.instance_id
            assert again.port == instance.port
            assert again.new_window_url().startswith(
                f"http://{HOST}:{instance.port}/#boot="
            )
            assert decision_monitor.state_path(root).read_bytes() == state_before
            assert decision_monitor.secret_path(root).read_bytes() == secret_before
        finally:
            stop_result = again.stop()
            assert stop_result["stopped"] is True
            assert stop_result["port_probe"] == "refused"
    finally:
        instance.stop()
    assert decision_monitor.read_state(root)[0] is None


def test_start_lock_conflict_keeps_state_and_reports_a_recovery_guide(tmp_path):
    root = _root(tmp_path)
    instance = decision_monitor.ensure_instance(root)
    try:
        state_before = decision_monitor.state_path(root).read_bytes()
        secret_before = decision_monitor.secret_path(root).read_bytes()
        lock = decision_monitor.start_lock_path(root)
        mw_common.acquire_lock(lock)
        mw_common.write_lock_owner(lock)
        try:
            with pytest.raises(decision_monitor.MonitorError) as exc:
                decision_monitor.ensure_instance(root)
            assert exc.value.kind == "start-lock-conflict"
            assert exc.value.guide
            assert decision_monitor.state_path(root).read_bytes() == state_before
            assert decision_monitor.secret_path(root).read_bytes() == secret_before
        finally:
            mw_common.release_lock(lock)
    finally:
        instance.stop()


def test_dead_start_lock_owner_is_moved_aside_not_deleted(tmp_path):
    root = _root(tmp_path)
    dead_pid = _spawn_exit()
    lock = decision_monitor.start_lock_path(root)
    mw_common.acquire_lock(lock)
    mw_common.write_lock_owner(lock, pid=dead_pid, start_ms=1)

    instance = decision_monitor.ensure_instance(root)
    try:
        stale_locks = list((root / ".mw").glob(lock.name + ".stale-*"))
        assert len(stale_locks) == 1
        owner = json.loads(stale_locks[0].read_text(encoding="utf-8"))
        assert owner["pid"] == dead_pid
        assert decision_monitor.health(instance.port, instance.control_token) is not None
        assert not lock.exists()
    finally:
        instance.stop()


def test_stale_state_and_secret_are_moved_stepwise_after_proven_death(tmp_path):
    root = _root(tmp_path)
    dead_pid = _spawn_exit()
    recorded_port = _closed_loopback_port()
    identity = decision_monitor.InstanceIdentity(
        project_id=wire.project_id_for(root),
        instance_id="old-instance-0001",
        pid=dead_pid,
        pid_start_ms=1,
        port=recorded_port,
        code_fingerprint=decision_monitor.code_fingerprint(),
    )
    decision_monitor.publish_secret(root, "old-control-token-value")
    decision_monitor.publish_state(root, identity)
    state_bytes = decision_monitor.state_path(root).read_bytes()
    secret_bytes = decision_monitor.secret_path(root).read_bytes()

    instance = decision_monitor.ensure_instance(root)
    try:
        assert instance.recovery["recovered"] is True
        assert instance.recovery["instance_id"] == "old-instance-0001"
        assert instance.recovery["moved"] == ["state", "secret"]
        assert instance.recovery["liveness"] == "dead"
        assert instance.recovery["port_probe"]["result"] == "refused"
        assert instance.recovery["port_probe"]["port"] == recorded_port
        stale_state = decision_monitor.state_path(root).with_name(
            decision_monitor.state_path(root).name + ".stale-old-instance-0001"
        )
        stale_secret = decision_monitor.secret_path(root).with_name(
            decision_monitor.secret_path(root).name + ".stale-old-instance-0001"
        )
        assert stale_state.read_bytes() == state_bytes
        assert stale_secret.read_bytes() == secret_bytes
        fresh_state, problem = decision_monitor.read_state(root)
        assert problem is None
        assert fresh_state["instance_id"] != "old-instance-0001"
        assert decision_monitor.read_secret(root) != "old-control-token-value"
    finally:
        instance.stop()


def test_recover_stale_bare_call_takes_and_releases_the_start_lock(tmp_path):
    root = _root(tmp_path)
    _publish_stale(root, _closed_loopback_port())
    report = decision_monitor.recover_stale(root)
    assert report["recovered"] is True
    assert report["moved"] == ["state", "secret"]
    assert report["liveness"] == "dead"
    assert report["port_probe"]["result"] == "refused"
    assert not decision_monitor.start_lock_path(root).exists()


def test_recover_stale_runs_under_a_verified_guard(tmp_path):
    root = _root(tmp_path)
    _publish_stale(root, _closed_loopback_port())
    with decision_monitor.start_lock(root) as guard:
        report = decision_monitor.recover_stale(root, guard=guard)
    assert report["recovered"] is True
    assert report["moved"] == ["state", "secret"]
    assert not decision_monitor.start_lock_path(root).exists()


def test_recover_stale_refuses_a_guard_whose_lock_was_lost(tmp_path):
    root = _root(tmp_path)
    _publish_stale(root, _closed_loopback_port())
    state_before = decision_monitor.state_path(root).read_bytes()
    secret_before = decision_monitor.secret_path(root).read_bytes()
    with decision_monitor.start_lock(root) as guard:
        mw_common.release_lock(guard.path)
        with pytest.raises(decision_monitor.MonitorError) as exc:
            decision_monitor.recover_stale(root, guard=guard, port_probe=lambda port: "refused")
    assert exc.value.kind == "start-lock-conflict"
    assert decision_monitor.state_path(root).read_bytes() == state_before
    assert decision_monitor.secret_path(root).read_bytes() == secret_before


def test_recover_stale_keeps_state_when_the_recorded_port_serves_another_process(tmp_path):
    root = _root(tmp_path)
    listener, port = _listening_port()
    try:
        _publish_stale(root, port)
        state_before = decision_monitor.state_path(root).read_bytes()
        secret_before = decision_monitor.secret_path(root).read_bytes()
        with pytest.raises(decision_monitor.MonitorError) as exc:
            decision_monitor.recover_stale(root)
        assert exc.value.kind == "instance-unknown"
        assert exc.value.details["port_probe"]["result"] == "connected"
        assert exc.value.guide
        assert decision_monitor.state_path(root).read_bytes() == state_before
        assert decision_monitor.secret_path(root).read_bytes() == secret_before
        # The unrelated listener is untouched and still reachable (never killed).
        probe = socket.create_connection((HOST, port), timeout=2)
        probe.close()
        assert listener.fileno() != -1
    finally:
        listener.close()


def test_recover_stale_keeps_state_when_the_port_probe_is_inconclusive(tmp_path):
    root = _root(tmp_path, "inconclusive")
    _publish_stale(root, decision_monitor.PORT_RANGE[0])
    state_before = decision_monitor.state_path(root).read_bytes()
    with pytest.raises(decision_monitor.MonitorError) as exc:
        decision_monitor.recover_stale(root, port_probe=lambda port: "unknown")
    assert exc.value.kind == "instance-unknown"
    assert exc.value.details["port_probe"]["result"] == "unknown"
    assert exc.value.guide
    assert decision_monitor.state_path(root).read_bytes() == state_before

    raising_root = _root(tmp_path, "raising")
    _publish_stale(raising_root, decision_monitor.PORT_RANGE[0])

    def broken_probe(port: int) -> str:
        raise OSError("probe failed")

    with pytest.raises(decision_monitor.MonitorError) as exc2:
        decision_monitor.recover_stale(raising_root, port_probe=broken_probe)
    assert exc2.value.kind == "instance-unknown"
    assert exc2.value.details["port_probe"]["result"] == "unknown"
    assert exc2.value.guide
    assert decision_monitor.state_path(raising_root).exists()
    assert decision_monitor.secret_path(raising_root).exists()


def test_recover_stale_never_moves_a_fresh_secret_published_after_the_state_move(
    tmp_path, monkeypatch
):
    root = _root(tmp_path)
    _publish_stale(root, _closed_loopback_port())
    fresh = decision_monitor.InstanceIdentity(
        project_id=wire.project_id_for(root),
        instance_id="fresh-instance-001",
        pid=os.getpid(),
        pid_start_ms=mw_common.process_start_ms(os.getpid()),
        port=_closed_loopback_port(),
        code_fingerprint=decision_monitor.code_fingerprint(),
    )
    real_move = decision_monitor._move_aside

    def move_then_publish(path, *, suffix):
        result = real_move(path, suffix=suffix)
        if pathlib.Path(path).name == decision_monitor.STATE_NAME:
            # Simulate a bare publisher outside the guard's discipline: the
            # recovery must re-read the state and leave the new secret alone.
            decision_monitor.publish_secret(root, "fresh-control-token-value")
            decision_monitor.publish_state(root, fresh)
        return result

    monkeypatch.setattr(decision_monitor, "_move_aside", move_then_publish)
    with decision_monitor.start_lock(root) as guard:
        with pytest.raises(decision_monitor.MonitorError) as exc:
            decision_monitor.recover_stale(root, guard=guard, port_probe=lambda port: "refused")
    assert exc.value.kind in ("instance-unknown", "start-lock-conflict")
    assert exc.value.details["moved"] == ["state"]
    assert exc.value.details["secret_preserved"] is True
    assert decision_monitor.read_secret(root) == "fresh-control-token-value"
    fresh_state, problem = decision_monitor.read_state(root)
    assert problem is None
    assert fresh_state["instance_id"] == "fresh-instance-001"


def test_attached_stop_reports_a_refusal_instead_of_silent_success(tmp_path):
    root = _root(tmp_path)
    with _running(root) as instance:
        state_before = decision_monitor.state_path(root).read_bytes()
        attached = decision_monitor.AttachedInstance(
            control_root=root, identity=instance.identity, control_token="wrong-control-token"
        )
        result = attached.stop()
        assert result["stopped"] is False
        assert result["detail"] and "refused" in result["detail"].lower()
        assert result["port_probe"] == "connected"
        # No kill and no state removal: the live instance keeps serving.
        assert decision_monitor.health(instance.port, instance.control_token) is not None
        assert decision_monitor.state_path(root).read_bytes() == state_before
        assert decision_monitor.secret_path(root).exists()


def test_attached_stop_reports_success_and_leaves_no_state(tmp_path):
    root = _root(tmp_path)
    instance = decision_monitor.ensure_instance(root)
    attached = decision_monitor.ensure_instance(root)
    assert isinstance(attached, decision_monitor.AttachedInstance)
    try:
        result = attached.stop()
        assert result["stopped"] is True
        assert result["detail"] is None
        assert result["port_probe"] == "refused"
        assert decision_monitor.read_state(root)[0] is None
        assert decision_monitor.read_secret(root) is None
    finally:
        instance.stop()


def test_foreign_project_state_is_a_conflict_and_is_not_moved(tmp_path):
    root = _root(tmp_path, "foreign")
    dead_pid = _spawn_exit()
    identity = decision_monitor.InstanceIdentity(
        project_id="f" * 16,  # not this root's project id
        instance_id="foreign-state-01",
        pid=dead_pid,
        pid_start_ms=1,
        port=decision_monitor.PORT_RANGE[0],
        code_fingerprint=decision_monitor.code_fingerprint(),
    )
    decision_monitor.publish_secret(root, decision_monitor.generate_token())
    decision_monitor.publish_state(root, identity)
    state_bytes = decision_monitor.state_path(root).read_bytes()
    with pytest.raises(decision_monitor.MonitorError) as exc:
        decision_monitor.ensure_instance(root)
    assert exc.value.kind == "incompatible-instance"
    assert decision_monitor.state_path(root).read_bytes() == state_bytes
    assert list(decision_monitor.state_path(root).parent.glob("*.stale-*")) == []


def test_alive_but_unhealthy_instance_is_kept_with_a_guide(tmp_path):
    root = _root(tmp_path)
    # A listener that we bind only to produce a free port, then close: the state
    # points at a port nothing serves.
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.bind((HOST, 0))
    free_port = probe.getsockname()[1]
    probe.close()
    identity = decision_monitor.InstanceIdentity(
        project_id=wire.project_id_for(root),
        instance_id="alive-instance-01",
        pid=os.getpid(),
        pid_start_ms=mw_common.process_start_ms(os.getpid()),
        port=free_port,
        code_fingerprint=decision_monitor.code_fingerprint(),
    )
    decision_monitor.publish_secret(root, decision_monitor.generate_token())
    decision_monitor.publish_state(root, identity)
    state_bytes = decision_monitor.state_path(root).read_bytes()
    secret_bytes = decision_monitor.secret_path(root).read_bytes()

    with pytest.raises(decision_monitor.MonitorError) as exc:
        decision_monitor.ensure_instance(root)
    assert exc.value.kind == "instance-unresponsive"
    assert exc.value.guide
    assert decision_monitor.state_path(root).read_bytes() == state_bytes
    assert decision_monitor.secret_path(root).read_bytes() == secret_bytes


def test_malformed_and_pid_reuse_state_stay_unknown_and_untouched(tmp_path):
    malformed_root = _root(tmp_path, "malformed")
    decision_monitor.state_path(malformed_root).parent.mkdir(parents=True, exist_ok=True)
    decision_monitor.state_path(malformed_root).write_text("not json\n", encoding="utf-8")
    malformed_bytes = decision_monitor.state_path(malformed_root).read_bytes()
    with pytest.raises(decision_monitor.MonitorError) as exc:
        decision_monitor.ensure_instance(malformed_root)
    assert exc.value.kind == "instance-unknown"
    assert decision_monitor.state_path(malformed_root).read_bytes() == malformed_bytes

    reuse_root = _root(tmp_path, "reuse")
    identity = decision_monitor.InstanceIdentity(
        project_id=wire.project_id_for(reuse_root),
        instance_id="recycled-pid-001",
        pid=os.getpid(),
        pid_start_ms=1,  # cannot match this process' real start
        port=decision_monitor.PORT_RANGE[0],
        code_fingerprint=decision_monitor.code_fingerprint(),
    )
    decision_monitor.publish_secret(reuse_root, decision_monitor.generate_token())
    decision_monitor.publish_state(reuse_root, identity)
    state_bytes = decision_monitor.state_path(reuse_root).read_bytes()
    with pytest.raises(decision_monitor.MonitorError) as exc2:
        decision_monitor.ensure_instance(reuse_root)
    assert exc2.value.kind == "instance-unknown"
    assert decision_monitor.state_path(reuse_root).read_bytes() == state_bytes


def test_incompatible_protocol_or_code_identity_is_a_conflict(tmp_path):
    root = _root(tmp_path, "incompatible")
    identity = decision_monitor.InstanceIdentity(
        project_id=wire.project_id_for(root),
        instance_id="old-protocol-001",
        pid=os.getpid(),
        pid_start_ms=mw_common.process_start_ms(os.getpid()),
        port=decision_monitor.PORT_RANGE[0],
        protocol_version=decision_monitor.PROTOCOL_VERSION + 1,
        code_fingerprint=decision_monitor.code_fingerprint(),
    )
    decision_monitor.publish_secret(root, decision_monitor.generate_token())
    decision_monitor.publish_state(root, identity)
    state_bytes = decision_monitor.state_path(root).read_bytes()
    with pytest.raises(decision_monitor.MonitorError) as exc:
        decision_monitor.ensure_instance(root)
    assert exc.value.kind == "incompatible-instance"
    assert str(decision_monitor.PROTOCOL_VERSION + 1) in json.dumps(exc.value.details)
    assert exc.value.guide
    assert decision_monitor.state_path(root).read_bytes() == state_bytes


# ---------------------------------------------------------------------------
# Browser primitives: argv only, explicit failure, never a false success
# ---------------------------------------------------------------------------


def test_detect_browser_absent_reports_an_explicit_reason(tmp_path):
    assert decision_monitor.detect_browser(candidates=(), exists=lambda path: False) is None
    assert (
        decision_monitor.detect_browser(
            candidates=("C:/browsers/chrome.exe",), exists=lambda path: path.endswith("chrome.exe")
        )
        == "C:/browsers/chrome.exe"
    )

    result = decision_monitor.launch_app_window(
        executable=None,
        port=decision_monitor.PORT_RANGE[0],
        boot_code="code",
        profile_dir=tmp_path / "profile",
    )
    assert result["spawned"] is False
    assert result["visibility"] == "not-opened"
    assert result["url"]
    assert result["guide"]
    assert "chrome" in result["reason"].lower() or "edge" in result["reason"].lower()


def test_launch_app_window_reports_failures_without_claiming_a_window(tmp_path):
    launched: list[list[str]] = []

    def spawn(argv):
        launched.append(list(argv))
        return object()

    ok = decision_monitor.launch_app_window(
        executable="C:/browsers/chrome.exe",
        port=decision_monitor.PORT_RANGE[0],
        boot_code="boot-code-value",
        profile_dir=tmp_path / "profile",
        spawn=spawn,
    )
    assert "ok" not in ok  # a spawn is never reported as a verified window
    assert ok["spawned"] is True
    assert ok["visibility"] == "not-verified"
    assert ok["mode"] == "app"
    assert launched and launched[0] == ok["argv"]
    assert "#boot=boot-code-value" in ok["url"]

    def failing_spawn(argv):
        raise OSError("no such executable")

    failed = decision_monitor.launch_app_window(
        executable="C:/browsers/chrome.exe",
        port=decision_monitor.PORT_RANGE[0],
        boot_code="boot-code-value",
        profile_dir=tmp_path / "profile",
        spawn=failing_spawn,
    )
    assert failed["spawned"] is False
    assert failed["visibility"] == "not-opened"
    assert failed["mode"] is None
    assert "no such executable" in failed["reason"]
    assert failed["guide"]
