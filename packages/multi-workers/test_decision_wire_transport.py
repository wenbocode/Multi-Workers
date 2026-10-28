"""test_decision_wire_transport.py - T03 real transport capture (mw-decision-dashboard).

Covers the wiring slices of AC-003/AC-005/AC-012/AC-016 (VC-003/VC-005/
VC-012/VC-016/VC-017) that live on the real transport boundary:

* ``_http_post`` keeps its frozen four-parameter signature and is *not* mocked
  here: every test drives a real stdlib ``http.server`` on 127.0.0.1:0, so the
  captured request bytes are compared against what the server actually read and
  the captured response bytes against what the server actually wrote.
* the request body is captured from the exact ``data`` bytes sent, the response
  body from ``response.read()`` / ``HTTPError.read()`` *before* the existing
  ``errors="replace"`` decode; a failed read is recorded as ``response-read``
  and never presented as a genuine empty body.
* one logical ``DecisionClient.decide`` owns one ``call_id``; every real POST
  (client retry and backend ``Retry-After`` retry alike) gets its own
  ``attempt_index`` on that call.
* the known-secret set is the actual ``Authorization`` value, the cfg api key,
  the resolved timi credential (env / auth.json) and the existing env
  heuristics. Header *names* are recorded, header *values* never.
* ``capture_status`` is exposed on the client/scope, never as a new key in the
  frozen ``decide`` response dict; probe/materialised-without-call paths write
  zero ledger rows; a test scope's evidence path never falls back to the
  production triage ledger.

Every fixture is an isolated tmp tree. No production archive / authority /
signoff / triage / wire file is read or written; no external network and no
real credential file.
"""
from __future__ import annotations

import http.server
import inspect
import json
import pathlib
import sys
import threading
import time

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))

import decision  # noqa: E402
import decision_backends as db  # noqa: E402
import decision_wire as wire  # noqa: E402

SECRET = "sk-t03-auth-0123456789abcdef"
ENV_SECRET = "timi-env-secret-0123456789"
AUTH_JSON_SECRET = "timi-authjson-secret-abcdef123456"
QUESTIONS = {"probe": {"type": "noul", "instructions": "Is this probe request well formed?"}}
RESPONSE_KEYS = [
    "available",
    "transport",
    "model",
    "confidence_source",
    "attempts",
    "latency_ms",
    "answers",
    "reason",
]


# ── local stdlib HTTP transport (the real boundary, never mocked) ───────────


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(length)
        server = self.server
        server.requests.append(
            {
                "path": self.path,
                "headers": {name: value for name, value in self.headers.items()},
                "body": body,
            }
        )
        step = server.next_step()
        status = int(step.get("status", 200))
        payload = step.get("body", b"")
        if not isinstance(payload, bytes):
            payload = str(payload).encode("utf-8")
        delay = float(step.get("delay", 0.0) or 0.0)
        if delay > 0:
            time.sleep(delay)
        self.send_response(status)
        self.send_header("Content-Type", step.get("content_type", "application/json"))
        self.send_header("Content-Length", str(step.get("declared", len(payload))))
        for name, value in (step.get("headers") or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()
        if step.get("truncate"):
            # Declared length > written length: the client's read() must fail.
            self.close_connection = True

    def log_message(self, fmt: str, *args: object) -> None:
        return


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, _Handler)
        self.requests: list[dict] = []
        self.steps: list[dict] = []

    @property
    def base_url(self) -> str:
        host, port = self.server_address[:2]
        return f"http://{host}:{port}"

    def push(self, step: dict) -> None:
        self.steps.append(step)

    def next_step(self) -> dict:
        if not self.steps:
            return {}
        return self.steps.pop(0) if len(self.steps) > 1 else self.steps[0]

    def handle_error(self, request, client_address) -> None:  # noqa: ANN001 - stdlib hook
        # A client timeout closes the socket while the handler still sleeps.
        return


@pytest.fixture
def server():
    instance = _Server(("127.0.0.1", 0))
    thread = threading.Thread(target=instance.serve_forever, daemon=True, name="t03-http")
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


# ── helpers ────────────────────────────────────────────────────────────────


def _ok_body(*, note: str | None = None) -> bytes:
    payload = {
        "model": "jev-latest",
        "answers": {"probe": {"type": "noul", "noul": 0.91}},
        "usage": {"input_tokens": 7, "output_tokens": 3},
    }
    if note is not None:
        payload["note"] = note
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _cfg(server: _Server, *, api_key: str = SECRET, **overrides) -> decision.DecisionConfig:
    cfg = decision.DecisionConfig(
        enabled=True,
        extras={"api_key": api_key, "base_url": server.base_url},
        timeout_s=5.0,
        max_retries=0,
        backoff_base_s=0.0,
    )
    for name, value in overrides.items():
        setattr(cfg, name, value)
    return cfg


def _scope(
    tmp_path: pathlib.Path,
    *,
    decision_id: str = "dec-t03",
    redactor=None,
    evidence_path: pathlib.Path | None = None,
) -> wire.WireScope:
    root = tmp_path / "test"
    return wire.WireScope(
        sink=wire.test_wire_sink(root),
        project_id="proj-t03",
        scope_kind="test",
        origin="test-submission",
        decision_id=decision_id,
        dp="dp3-worker-clarify",
        task_key="t03-wire-transport",
        submission_id="sub-t03",
        evidence_path=evidence_path,
        redact=redactor,
        warn=lambda message: None,
    )


def _client(cfg: decision.DecisionConfig, scope: wire.WireScope) -> decision.DecisionClient:
    return decision.DecisionClient(cfg, db.TimiDecisionsBackend(), wire_scope=scope)


def _rows(path: pathlib.Path) -> list[dict]:
    assert path.exists(), f"missing wire ledger {path}"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _kind(rows: list[dict], kind: str) -> list[dict]:
    return [row for row in rows if row["kind"] == kind]


# ── frozen signature + real boundary capture ───────────────────────────────


def test_http_post_keeps_its_four_parameter_signature() -> None:
    assert list(inspect.signature(db._http_post).parameters) == [
        "url",
        "headers",
        "payload",
        "timeout_s",
    ]


def test_request_and_response_bytes_are_captured_at_the_wire_boundary(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _ok_body()})
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))
    client = _client(_cfg(server), scope)

    result = client.decide({"note": "plain state"}, QUESTIONS)

    assert result["available"] is True
    received = server.requests[0]
    rows = _rows(scope.sink)
    starts = _kind(rows, "attempt-start")
    ends = _kind(rows, "attempt-end")
    assert len(starts) == 1 and len(ends) == 1
    request = starts[0]["request"]
    response = ends[0]["response"]
    # The capture is the exact bytes the server read / wrote (no reconstruction).
    assert request["text"].encode("utf-8") == received["body"]
    assert request["wire_len"] == len(received["body"])
    assert request["byte_exact"] is True
    assert response["text"].encode("utf-8") == _ok_body()
    assert response["wire_len"] == len(_ok_body())
    assert ends[0]["http_status"] == 200
    assert ends[0]["usage"] == {"input_tokens": 7, "output_tokens": 3}
    assert ends[0]["usage_source"] == "response-body"
    assert starts[0]["method"] == "POST"
    assert starts[0]["url_path"] == "/v1/decisions"
    assert starts[0]["model"] == "jev-latest"
    # Header names only; values are never part of the ledger.
    assert starts[0]["header_names"] == ["Content-Type", "Authorization"]


def test_non_utf8_response_is_captured_losslessly_before_decode(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    raw = b'{"model":"jev-latest","answers":{"probe":{"type":"noul","noul":0.5}},"note":"\xff\xfe"}'
    server.push({"body": raw})
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))
    result = _client(_cfg(server), scope).decide({"note": "x"}, QUESTIONS)

    assert result["available"] is True
    ends = _kind(_rows(scope.sink), "attempt-end")
    response = ends[0]["response"]
    assert response["decode_errors"] is True
    assert response["encoding"] == "latin-1"
    # A lossless byte view: re-encoding the stored text reproduces the payload.
    assert response["text"].encode("latin-1") == raw
    assert response["byte_exact"] is False


# ── credential safety set ──────────────────────────────────────────────────


def test_actual_authorization_value_is_never_persisted(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _ok_body(note=f"echo {SECRET}")})
    cfg = _cfg(server)
    scope = _scope(tmp_path, redactor=decision.credential_redactor(cfg))
    client = _client(cfg, scope)

    result = client.decide(f"state mentions {SECRET}", QUESTIONS)

    assert result["available"] is True
    # The real transport really carried the injected credential.
    assert server.requests[0]["headers"]["Authorization"] == SECRET
    raw = scope.sink.read_bytes()
    assert SECRET.encode() not in raw
    assert b"<redacted>" in raw
    rows = _rows(scope.sink)
    assert _kind(rows, "attempt-start")[0]["request"]["redactions"] >= 1
    assert _kind(rows, "attempt-end")[0]["response"]["redactions"] >= 1
    # Header names are recorded, header values never are.
    assert "Authorization" in _kind(rows, "attempt-start")[0]["header_names"]
    assert SECRET not in json.dumps(_kind(rows, "attempt-start")[0]["header_names"])


def test_redactor_covers_cfg_env_and_auth_json_credentials(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    monkeypatch.setenv("TIMI_API_KEY", ENV_SECRET)
    auth_path = tmp_path / "auth.json"
    auth_path.write_text(json.dumps({"timi": {"key": AUTH_JSON_SECRET}}), encoding="utf-8")

    cfg = decision.DecisionConfig(
        enabled=True,
        extras={"api_key": "cfg-extra-secret-42"},
    )
    cfg.api_key = "cfg-dataclass-secret-43"

    from_env = decision.credential_redactor(
        cfg, env={"TIMI_API_KEY": ENV_SECRET}, auth_path=auth_path
    )
    from_auth = decision.credential_redactor(None, env={}, auth_path=auth_path)

    # The actual Authorization/cfg values and the ambient env credential.
    for secret in ("cfg-dataclass-secret-43", "cfg-extra-secret-42", ENV_SECRET):
        redaction = from_env.redact(f"before {secret} after")
        assert secret not in redaction.text
        assert redaction.hits >= 1
    # auth.json timi.key is resolved even with an empty env.
    redaction = from_auth.redact(f"token {AUTH_JSON_SECRET}")
    assert AUTH_JSON_SECRET not in redaction.text
    assert redaction.hits == 1


def test_http_error_body_is_captured_and_redacted(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"status": 500, "body": f"upstream failed for {SECRET}".encode()})
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))
    result = _client(_cfg(server), scope).decide({"note": "x"}, QUESTIONS)

    assert result["available"] is False
    assert result["reason"] == "upstream-error"
    ends = _kind(_rows(scope.sink), "attempt-end")
    assert len(ends) == 1
    assert ends[0]["http_status"] == 500
    assert ends[0]["error_class"] is None
    response = ends[0]["response"]
    assert "<redacted>" in response["text"]
    assert SECRET.encode() not in scope.sink.read_bytes()
    assert json.dumps(result).find(SECRET) == -1


# ── read failures are distinct from an empty body ──────────────────────────


def test_success_read_failure_is_recorded_as_response_read(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push(
        {
            "status": 200,
            "body": b'{"model":"jev-latest","ans',
            "truncate": True,
            "declared": 200,
        }
    )
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))
    result = _client(_cfg(server), scope).decide({"note": "x"}, QUESTIONS)

    assert result["available"] is False
    ends = _kind(_rows(scope.sink), "attempt-end")
    assert len(ends) == 1
    assert ends[0]["error_class"] == "response-read"
    assert ends[0]["response"] is None
    assert ends[0]["http_status"] == 200


def test_http_error_read_failure_is_recorded_as_response_read(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"status": 500, "body": b"part", "truncate": True, "declared": 100})
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))
    result = _client(_cfg(server), scope).decide({"note": "x"}, QUESTIONS)

    assert result["available"] is False
    ends = _kind(_rows(scope.sink), "attempt-end")
    assert len(ends) == 1
    assert ends[0]["error_class"] == "response-read"
    assert ends[0]["response"] is None
    assert ends[0]["http_status"] == 500


def test_genuine_empty_body_is_not_confused_with_a_read_failure(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"status": 200, "body": b""})
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))
    result = _client(_cfg(server), scope).decide({"note": "x"}, QUESTIONS)

    assert result["available"] is False
    assert result["reason"] == "bad-response"
    ends = _kind(_rows(scope.sink), "attempt-end")
    assert ends[0]["error_class"] is None
    response = ends[0]["response"]
    assert response["text"] == ""
    assert response["wire_len"] == 0
    assert response["byte_exact"] is True
    assert response["text_omitted"] is False


def test_oversized_response_is_marked_truncated_not_byte_exact(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    padding = "x" * (30 * 1024)
    server.push({"body": _ok_body(note=padding)})
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))
    result = _client(_cfg(server), scope).decide({"note": "x"}, QUESTIONS)

    assert result["available"] is True
    ends = _kind(_rows(scope.sink), "attempt-end")
    response = ends[0]["response"]
    assert response["truncated"] is True
    assert response["read_capped"] is True
    assert response["byte_exact"] is False
    assert response["wire_len"] == len(_ok_body(note=padding))
    assert ends[0]["capture_status"] == "partial"
    assert scope.capture_status == "partial"


# ── attempt accounting: client retry vs backend Retry-After ────────────────


def test_connection_error_is_recorded_without_a_response(tmp_path: pathlib.Path) -> None:
    # Port 0 is not connectable: the failure happens before any response.
    cfg = decision.DecisionConfig(
        enabled=True,
        extras={"api_key": SECRET, "base_url": "http://127.0.0.1:0"},
        timeout_s=2.0,
        max_retries=0,
        backoff_base_s=0.0,
    )
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))

    result = _client(cfg, scope).decide({"note": "x"}, QUESTIONS)

    assert result["available"] is False
    assert result["reason"] == "upstream-error"
    ends = _kind(_rows(scope.sink), "attempt-end")
    assert len(ends) == 1
    assert ends[0]["error_class"] == "connection-error"
    assert ends[0]["response"] is None
    assert ends[0]["http_status"] is None


def test_timeout_is_recorded_as_a_timeout_attempt(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _ok_body(), "delay": 0.5})
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))
    cfg = _cfg(server, timeout_s=0.05, max_retries=0)

    result = _client(cfg, scope).decide({"note": "x"}, QUESTIONS)

    assert result["available"] is False
    assert result["reason"] == "timeout"
    ends = _kind(_rows(scope.sink), "attempt-end")
    assert len(ends) == 1
    assert ends[0]["error_class"] == "timeout"
    assert ends[0]["response"] is None


def test_client_retry_records_every_post_as_its_own_attempt(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"status": 500, "body": b'{"error":"boom"}'})
    server.push({"body": _ok_body()})
    cfg = _cfg(server, max_retries=1, backoff_base_s=0.0)
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))
    client = _client(cfg, scope)

    result = client.decide({"note": "x"}, QUESTIONS)

    assert result["available"] is True
    assert result["attempts"] == 2
    rows = _rows(scope.sink)
    starts = _kind(rows, "attempt-start")
    assert [row["attempt_index"] for row in starts] == [1, 2]
    assert {row["call_id"] for row in rows} == {client.last_call_id}
    assert _kind(rows, "call-end")[0]["wire_attempts"] == 2
    assert _kind(rows, "call-end")[0]["attempts"] == 2
    assert _kind(rows, "call-end")[0]["zero_call"] is False
    assert len(server.requests) == 2


def test_backend_retry_after_retries_are_separate_attempts(
    server: _Server, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sleeps: list[float] = []
    monkeypatch.setattr(db, "_sleep", lambda seconds: sleeps.append(seconds))
    server.push(
        {
            "status": 429,
            "body": b'{"error":"rate limit"}',
            "headers": {"Retry-After": "0"},
        }
    )
    server.push({"body": _ok_body()})
    cfg = _cfg(server, max_retries=1, backoff_base_s=0.0)
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))
    client = _client(cfg, scope)

    result = client.decide({"note": "x"}, QUESTIONS)

    assert result["available"] is True
    # The client sees one backend attempt; the wire saw both POSTs.
    assert result["attempts"] == 1
    rows = _rows(scope.sink)
    starts = _kind(rows, "attempt-start")
    ends = _kind(rows, "attempt-end")
    assert [row["attempt_index"] for row in starts] == [1, 2]
    assert [row["attempt_index"] for row in ends] == [1, 2]
    assert ends[0]["http_status"] == 429
    assert ends[0]["retry_after_s"] == 0.0
    assert ends[1]["http_status"] == 200
    assert _kind(rows, "call-end")[0]["wire_attempts"] == 2
    assert _kind(rows, "call-end")[0]["attempts"] == 1
    assert len(server.requests) == 2
    assert sleeps  # the backend honoured the Retry-After budget


def test_production_scope_gets_the_credential_redactor_injected(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _ok_body(note=f"echo {SECRET}")})
    cfg = _cfg(server)
    scope = wire.WireScope(
        sink=tmp_path / "prod-wire.jsonl",
        project_id="proj-t03",
        scope_kind="production",
        decision_id="dec-prod",
        evidence_path=tmp_path / "triage.jsonl",
        warn=lambda message: None,
    )
    assert scope.redact is None
    client = _client(cfg, scope)

    result = client.decide(f"state mentions {SECRET}", QUESTIONS)

    assert result["available"] is True
    assert scope.redact is not None
    assert SECRET.encode() not in scope.sink.read_bytes()
    assert b"<redacted>" in scope.sink.read_bytes()


def test_test_scope_without_redactor_stays_fail_closed(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _ok_body(note=f"echo {SECRET}")})
    scope = _scope(tmp_path, redactor=None)
    result = _client(_cfg(server), scope).decide(f"state mentions {SECRET}", QUESTIONS)

    assert result["available"] is True
    assert SECRET.encode() not in scope.sink.read_bytes()
    starts = _kind(_rows(scope.sink), "attempt-start")
    request = starts[0]["request"]
    assert request["text"] is None
    assert request["text_omitted"] is True
    assert request["wire_len"] > 0


def test_two_logical_calls_keep_separate_call_ids_on_one_decision(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _ok_body()})
    scope = _scope(tmp_path, decision_id="dec-same", redactor=wire.SubstringRedactor([SECRET]))
    client = _client(_cfg(server), scope)

    first = client.decide({"note": "one"}, QUESTIONS)
    first_call = client.last_call_id
    second = client.decide({"note": "two"}, QUESTIONS)
    second_call = client.last_call_id

    assert first["available"] is True and second["available"] is True
    assert first_call and second_call and first_call != second_call
    rows = _rows(scope.sink)
    assert {row["call_id"] for row in rows} == {first_call, second_call}
    assert {row["decision_id"] for row in rows} == {"dec-same"}
    counts = wire.summarize(rows)
    assert counts.calls == 2
    assert counts.attempts == 2
    # decision-end is the decide_for/playground writer (T05), not the client.
    assert counts.decisions == 0


# ── capture_status exposure, zero-write paths, isolated test evidence ──────


def test_capture_status_is_exposed_without_touching_response_keys(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _ok_body()})
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))
    client = _client(_cfg(server), scope)

    result = client.decide({"note": "x"}, QUESTIONS)

    assert list(result.keys()) == RESPONSE_KEYS
    assert client.capture_status == scope.capture_status
    assert client.capture_status in ("ok", "partial")
    assert client.last_call_id == _kind(_rows(scope.sink), "call-end")[0]["call_id"]
    assert client.last_wire_attempts == 1


def test_probe_without_a_call_writes_no_ledger(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _ok_body()})
    scope = _scope(tmp_path, redactor=wire.SubstringRedactor([SECRET]))

    with wire.scope_context(scope):
        rows = db.probe_matrix(_cfg(server))

    assert rows[0]["status"] == 200
    assert len(server.requests) == 1
    assert not scope.sink.exists()
    assert scope.capture_status is None
    assert scope.errors == []


def test_client_without_wire_scope_writes_nothing(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _ok_body()})
    client = decision.DecisionClient(_cfg(server), db.TimiDecisionsBackend(), project_root=tmp_path)

    result = client.decide({"note": "x"}, QUESTIONS)

    assert result["available"] is True
    assert client.capture_status is None
    assert not (tmp_path / "test").exists()
    # No ledger anywhere under the isolated root.
    assert list(tmp_path.rglob("wire.jsonl")) == []


def test_test_scope_evidence_never_falls_back_to_production(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _ok_body()})
    project_root = tmp_path / "project"
    (project_root / ".mw").mkdir(parents=True)
    cfg = _cfg(server)
    cfg.project_root = project_root
    redactor = decision.credential_redactor(cfg)

    without_evidence = _scope(tmp_path, redactor=redactor, evidence_path=None)
    client = _client(cfg, without_evidence)
    assert client.decide({"note": "x"}, QUESTIONS)["available"] is True
    assert client.evidence_path() is None
    assert not (project_root / ".agenticdoc").exists()

    server.push({"body": _ok_body()})
    helper_scope = wire.test_scope(
        tmp_path / "iso2",
        project_id="proj-t03",
        submission_id="sub-2",
        redact=redactor,
    )
    helper_client = _client(cfg, helper_scope)
    assert helper_client.decide({"note": "y"}, QUESTIONS)["available"] is True
    assert (tmp_path / "iso2" / "evidence.jsonl").exists()
    assert not (project_root / ".agenticdoc").exists()


def test_lock_timeout_does_not_change_the_business_result(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _ok_body()})
    warnings: list[str] = []
    scope = wire.WireScope(
        sink=tmp_path / "locked" / "wire.jsonl",
        project_id="proj-t03",
        scope_kind="test",
        submission_id="sub-lock",
        evidence_path=tmp_path / "evidence.jsonl",
        redact=wire.SubstringRedactor([SECRET]),
        warn=warnings.append,
    )
    lock = scope.sink.with_name(scope.sink.name + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text("foreign owner", encoding="utf-8")
    client = _client(_cfg(server), scope)

    result = client.decide({"note": "x"}, QUESTIONS)

    assert result["available"] is True
    assert result["attempts"] == 1
    assert client.capture_status == "failed"
    # A lock this call never acquired is never removed by the capture path.
    assert lock.read_text(encoding="utf-8") == "foreign owner"
    assert not scope.sink.exists()
    assert len(warnings) == 1


def test_ledger_write_failure_does_not_change_the_business_result(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _ok_body()})
    sink_dir = tmp_path / "sink-is-a-directory"
    sink_dir.mkdir()
    scope = wire.WireScope(
        sink=sink_dir,
        project_id="proj-t03",
        scope_kind="test",
        submission_id="sub-fail",
        evidence_path=tmp_path / "evidence.jsonl",
        redact=wire.SubstringRedactor([SECRET]),
        warn=lambda message: None,
    )
    client = _client(_cfg(server), scope)

    result = client.decide({"note": "x"}, QUESTIONS)

    assert result["available"] is True
    assert result["attempts"] == 1
    assert client.capture_status == "failed"
    assert scope.capture_status == "failed"


# ── N-1: a credential used as a usage *key* never reaches disk ─────────────


def _leaky_usage_body() -> bytes:
    """Real response with the credential in a usage key, a value and body text."""
    return json.dumps(
        {
            "model": "jev-latest",
            "note": f"echo {SECRET}",
            "answers": {"probe": {"type": "noul", "noul": 0.91}},
            "usage": {
                "input_tokens": 7,
                "output_tokens": 3,
                f"label-{SECRET}": 5,
            },
        },
        ensure_ascii=False,
    ).encode("utf-8")


def _persisted_files(root: pathlib.Path) -> list[pathlib.Path]:
    return sorted(path for path in root.rglob("*") if path.is_file())


def test_usage_key_from_a_real_response_is_never_persisted(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    server.push({"body": _leaky_usage_body()})
    cfg = _cfg(server)
    scope = _scope(
        tmp_path,
        redactor=decision.credential_redactor(cfg),
        evidence_path=tmp_path / "test" / "evidence.jsonl",
    )

    result = _client(cfg, scope).decide(f"state mentions {SECRET}", QUESTIONS)

    assert result["available"] is True
    # The server really did send the credential in the usage key + value + note.
    assert SECRET.encode() in _leaky_usage_body()
    files = _persisted_files(tmp_path)
    assert {path.name for path in files} >= {"wire.jsonl", "evidence.jsonl"}
    for path in files:
        assert SECRET.encode() not in path.read_bytes(), path

    ends = _kind(_rows(scope.sink), "attempt-end")
    usage = ends[0]["usage"]
    # Token counting still works: the closed-set counters survive the key pass.
    assert usage["input_tokens"] == 7
    assert usage["output_tokens"] == 3
    assert "<redacted>" in json.dumps(usage)
    assert ends[0]["usage_source"] == "response-body"


def test_usage_key_from_a_real_response_is_withheld_without_a_redactor(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    # Input trust is not waived because the endpoint is "malicious": with no
    # redactor the unknown key and the string values are dropped, only the
    # documented counters remain.
    server.push({"body": _leaky_usage_body()})
    scope = _scope(
        tmp_path,
        redactor=None,
        evidence_path=tmp_path / "test" / "evidence.jsonl",
    )

    result = _client(_cfg(server), scope).decide(f"state mentions {SECRET}", QUESTIONS)

    assert result["available"] is True
    for path in _persisted_files(tmp_path):
        assert SECRET.encode() not in path.read_bytes(), path
    ends = _kind(_rows(scope.sink), "attempt-end")
    assert ends[0]["response"]["text"] is None
    assert ends[0]["usage"] == {"input_tokens": 7, "output_tokens": 3}

