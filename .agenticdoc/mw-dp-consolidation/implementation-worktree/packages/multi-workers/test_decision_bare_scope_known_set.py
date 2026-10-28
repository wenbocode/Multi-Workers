"""test_decision_bare_scope_known_set.py - T05m (mw-decision-dashboard).

T05l froze the *complete* known-safe set on a ``CredentialSnapshot`` and made
every face of one decision consume it - but the freeze itself had to be paid for
by someone: the book gate, a decision gate, or an explicit caller. A **bare**
``DecisionClient`` handed a production capture scope and an explicit
``cfg.extras["api_key"]`` (legacy timi credential B present in ``auth.json`` but
never sent) self-injected a redactor from ``frozen_superset()`` *before* anything
had frozen it, i.e. from ``()``. The client then sent A and persisted B raw -
response body, response metadata (``usage`` keys/values) and failure output
alike. ``workers/dd-known-set-snapshot/report.md`` R1 recorded this as
``bare_production_scope.cold_capture_stores_frozen_leg_raw=true``.

The contract pinned here (card T05m, transport slice):

* the **capture path itself** freezes the unit's complete known set immediately
  before it records anything: one logical call, one legacy discovery, the
  client self-injects the full superset - no gate has to run first;
* an explicit ``cfg`` key keeps its precedence (A is sent, never B) and the
  transport still resolves it once per logical call;
* retries of that call (client backoff and backend ``Retry-After`` alike) reuse
  the frozen set: no second discovery, and the same ``Authorization``;
* the *next* logical call builds a fresh snapshot and covers a value rotated in
  between (per-call refresh, not a cross-call cache);
* a discovery that raises during that freeze behaves like the gate failure of
  T05l: zero POST, zero attempt/snapshot row, ``entry-unavailable``, and the
  safe detail names the failure kind - never the exception message or a value;
* a client with **no** capture scope and an explicit ``cfg`` key keeps the
  pre-T05i zero-discovery contract, and ``credential_status`` / ``probe_matrix``
  gain no extra auth read (their own live order is unchanged).

Everything is synthetic and hermetic: the credential lives in a tmp
``auth.json`` (``decision_backends._auth_json_path`` is patched before any test
body runs), every credential-shaped env name is removed, and the only socket is
a stdlib ``http.server`` on ``127.0.0.1:0`` that echoes the ``Authorization``
value **and** the request body, so a known value that reached the wire is
measured in the text the capture would persist. No real credential file is read
and the code under test never logs a credential. The fixture values below are
fabricated; a failing assertion quotes them verbatim in pytest's output (that
quote *is* the evidence), so the evidence logs are not masked and do not claim
to be.
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_backends as db  # noqa: E402
import decision_wire as wire  # noqa: E402

#: The explicit ``cfg.extras["api_key"]`` value: also the sent Authorization.
SECRET_SENT = "timi-bare-sent-a-0123456789abcdef"
#: The legacy timi leg (``auth.json`` timi.key) while A is sent.
SECRET_LEGACY = "timi-bare-legacy-b-0123456789ab"
#: Rotated into ``auth.json`` *after* the first unit froze its set.
SECRET_ROTATED = "timi-bare-rotated-c-0123456789a"
#: Plain text no layer (Bearer / ``sk-`` / env) can mistake for a secret.
PLAIN_MATERIAL = "plain-bare-scope-material-0123456789"

#: Every credential-shaped suffix the discovery rule picks up, plus the explicit
#: names, so the known set cannot depend on the developer's shell.
CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
    "TIMI_BASE_URL",
)

QUESTIONS = {"probe": {"type": "noul", "instructions": "Is this probe well formed?"}}
PROBE_ANSWERS = {"probe": {"type": "noul", "noul": 0.91}}
#: Default response metadata: an arbitrary caller-shaped key/value pair.
DEFAULT_USAGE = {"prompt_tokens": 7, "total_tokens": 9}


def _credential_env_names() -> tuple[str, ...]:
    names = set(CRED_ENV_VARS)
    names.update(
        name for name in os.environ if name.upper().endswith(decision._CRED_ENV_SUFFIXES)
    )
    return tuple(sorted(names))


# -- local stdlib HTTP transport (the real boundary, never mocked) ----------


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(length)
        authorization = self.headers.get("Authorization") or ""
        server = self.server
        server.requests.append(
            {
                "path": self.path,
                "headers": {name: value for name, value in self.headers.items()},
                "body": body,
                "authorization": authorization,
            }
        )
        hook = server.on_request
        if hook is not None:
            hook(len(server.requests))
        step = server.next_step()
        status = int(step.get("status", 200))
        payload = step.get("body")
        if payload is None:
            # Echo the Authorization value *and* the request body back: the
            # capture must redact material that reached the real wire.
            payload = json.dumps(
                {
                    "model": "jev-latest",
                    "answers": server.answers,
                    "usage": dict(server.usage),
                    "note": (
                        f"used {authorization} body {body.decode('utf-8', 'replace')}"
                    ),
                },
                ensure_ascii=False,
            ).encode("utf-8")
        elif not isinstance(payload, bytes):
            payload = str(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", step.get("content_type", "application/json"))
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()

    def log_message(self, fmt: str, *args: object) -> None:
        return


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, _Handler)
        self.requests: list[dict] = []
        self.steps: list[dict] = []
        self.answers: dict = PROBE_ANSWERS
        self.usage: dict = dict(DEFAULT_USAGE)
        self.on_request = None

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
        return


@pytest.fixture
def server():
    instance = _Server(("127.0.0.1", 0))
    thread = threading.Thread(target=instance.serve_forever, daemon=True, name="t05m-http")
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


# -- hermetic credential plumbing (synthetic tmp auth.json only) ------------


@pytest.fixture(autouse=True)
def auth_json(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    """No ambient credential and no real ``~/.pi/agent/auth.json``, ever."""
    for name in _credential_env_names():
        monkeypatch.delenv(name, raising=False)
    leftover = [
        name for name in os.environ if name.upper().endswith(decision._CRED_ENV_SUFFIXES)
    ]
    assert leftover == [], f"ambient credential env vars survived the fixture: {leftover}"
    path = tmp_path / "home" / ".pi" / "agent" / "auth.json"
    monkeypatch.setattr(db, "_auth_json_path", lambda: path)
    return path


def _write_auth(path: pathlib.Path, key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"timi": {"key": key}}), encoding="utf-8", newline="\n")


def _count_resolutions(
    monkeypatch: pytest.MonkeyPatch, *, error: Exception | None = None
) -> list[str | None]:
    """Count ambient discoveries (the unit's own reads, not explicit-env calls)."""
    original = db.resolve_timi_api_key
    calls: list[str | None] = []

    def spy(env: dict | None = None, auth_path: pathlib.Path | None = None):
        if env is None and auth_path is None:
            if error is not None:
                raise error
            value = original(env, auth_path)
            calls.append(value)
            return value
        return original(env, auth_path)

    monkeypatch.setattr(db, "resolve_timi_api_key", spy)
    return calls


def _cfg(server: _Server, *, api_key: str | None = SECRET_SENT) -> decision.DecisionConfig:
    extras: dict = {"base_url": server.base_url}
    if api_key is not None:
        extras["api_key"] = api_key
    return decision.DecisionConfig(
        enabled=True,
        extras=extras,
        timeout_s=5.0,
        max_retries=2,
        backoff_base_s=0.0,
    )


def _production_scope(root: pathlib.Path) -> wire.WireScope:
    """A production scope without a redactor: the client must inject one."""
    return wire.WireScope(
        sink=root / "wire" / "wire.jsonl",
        project_id="proj-t05m",
        scope_kind="production",
        origin="t05m",
        decision_id="dec-t05m",
        dp="dp3-worker-clarify",
        evidence_path=root / "triage.jsonl",
        warn=lambda message: None,
    )


def _client(
    cfg: decision.DecisionConfig,
    scope: wire.WireScope | None,
    **kwargs: object,
) -> decision.DecisionClient:
    return decision.DecisionClient(
        cfg, db.TimiDecisionsBackend(), wire_scope=scope, **kwargs
    )


def _rows(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _rows_of(rows: list[dict], kind: str) -> list[dict]:
    return [row for row in rows if row.get("kind") == kind]


def _attempt_response_texts(rows: list[dict]) -> list[str]:
    texts: list[str] = []
    for row in _rows_of(rows, "attempt-end"):
        capture = row.get("response") or {}
        if capture.get("text") is not None:
            texts.append(str(capture["text"]))
    return texts


def _attempt_request_texts(rows: list[dict]) -> list[str]:
    texts: list[str] = []
    for row in _rows_of(rows, "attempt-start"):
        capture = row.get("request") or {}
        if capture.get("text") is not None:
            texts.append(str(capture["text"]))
    return texts


def _assert_no_value(text: str, *values: str) -> None:
    for value in values:
        assert value not in text, "credential-shaped material reached stored text"


# ---------------------------------------------------------------------------
# 1. cold bare production scope: the capture freezes the complete known set
# ---------------------------------------------------------------------------


def test_cold_bare_scope_capture_redacts_the_complete_known_set(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED (T05l R1): no gate ran, so the client injected only the sent value A.

    ``auth.json`` holds B; the state carries B and the response echoes both the
    Authorization value and the request body, plus a metadata (``usage``) key and
    value equal to B. Sending A must not exempt B: the unit's own freeze covers
    ``{A, B}`` before the first capture, so nothing of B is persisted.
    """
    _write_auth(auth_json, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    server.usage = {f"trace-{SECRET_LEGACY}": SECRET_LEGACY, "prompt_tokens": 7}
    scope = _production_scope(tmp_path / "cold")
    server.push({"status": 200})

    result = _client(cfg, scope).decide(
        {"note": f"carried {SECRET_LEGACY} and {PLAIN_MATERIAL}"}, QUESTIONS
    )

    assert result["available"] is True, result
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT]

    raw = scope.sink.read_bytes()
    assert SECRET_SENT.encode() not in raw, "the sent Authorization was captured raw"
    assert SECRET_LEGACY.encode() not in raw, "the frozen legacy leg was captured raw"
    assert b"<redacted>" in raw
    # The capture path froze the legacy leg itself: exactly one discovery for
    # the one logical call, none of them a second read of the sent value.
    assert calls == [SECRET_LEGACY], f"the capture froze {len(calls)} time(s)"

    rows = _rows(scope.sink)
    for text in _attempt_request_texts(rows) + _attempt_response_texts(rows):
        _assert_no_value(text, SECRET_SENT, SECRET_LEGACY)
    assert PLAIN_MATERIAL in "".join(_attempt_request_texts(rows)), (
        "the request was not captured at all; the redaction above proves nothing"
    )
    usage = _rows_of(rows, "attempt-end")[0].get("usage")
    assert isinstance(usage, dict), usage
    serialized = json.dumps(usage)
    _assert_no_value(serialized, SECRET_SENT, SECRET_LEGACY)
    assert "<redacted>" in serialized, "the metadata key/value pair was not redacted"


# ---------------------------------------------------------------------------
# 2. retries of one call reuse the frozen set (no second discovery)
# ---------------------------------------------------------------------------


def test_retry_of_one_call_reuses_the_frozen_known_set(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED: the failure output of attempt 1 (a 500 body carrying B) went raw."""
    _write_auth(auth_json, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    scope = _production_scope(tmp_path / "retry")
    server.push({"status": 500, "body": f"upstream failed near {SECRET_LEGACY}"})
    server.push({"status": 200})
    client = _client(cfg, scope)

    result = client.decide({"note": f"material {SECRET_LEGACY}"}, QUESTIONS)

    assert result["available"] is True, result
    assert result["attempts"] == 2
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT] * 2
    assert client.last_wire_attempts == 2

    raw = scope.sink.read_bytes()
    assert SECRET_SENT.encode() not in raw
    assert SECRET_LEGACY.encode() not in raw, "the failure output was persisted raw"
    assert calls == [SECRET_LEGACY], "a retry re-opened the known-set discovery"
    ends = _rows_of(_rows(scope.sink), "attempt-end")
    assert [row.get("http_status") for row in ends] == [500, 200], ends
    for text in _attempt_response_texts(ends):
        _assert_no_value(text, SECRET_SENT, SECRET_LEGACY)


# ---------------------------------------------------------------------------
# 3. the next logical call refreshes the frozen set
# ---------------------------------------------------------------------------


def test_the_next_call_refreshes_and_covers_the_rotated_value(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-call refresh: call 2 freezes and redacts the rotated C."""
    _write_auth(auth_json, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    scope = _production_scope(tmp_path / "refresh")
    client = _client(cfg, scope)

    server.push({"status": 200})
    first = client.decide({"note": f"material {SECRET_LEGACY}"}, QUESTIONS)
    assert first["available"] is True, first

    _write_auth(auth_json, SECRET_ROTATED)
    server.push({"status": 200})
    second = client.decide({"note": f"material {SECRET_ROTATED}"}, QUESTIONS)
    assert second["available"] is True, second

    raw = scope.sink.read_bytes()
    for value in (SECRET_SENT, SECRET_LEGACY, SECRET_ROTATED):
        assert value.encode() not in raw, "a known value of a unit was captured raw"
    assert b"<redacted>" in raw
    assert calls == [SECRET_LEGACY, SECRET_ROTATED], "call 2 did not refresh its known set"
    texts = _attempt_response_texts(_rows(scope.sink))
    assert len(texts) == 2, texts
    for text in texts:
        _assert_no_value(text, SECRET_SENT, SECRET_LEGACY, SECRET_ROTATED)


# ---------------------------------------------------------------------------
# 4. a discovery that raises during the capture freeze: zero send, zero row
# ---------------------------------------------------------------------------


def test_discovery_failure_at_the_capture_freeze_sends_nothing(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An incomplete known set cannot prove captured text safe: refuse first."""
    _write_auth(auth_json, SECRET_LEGACY)
    _count_resolutions(monkeypatch, error=RuntimeError(f"boom {SECRET_LEGACY}"))
    cfg = _cfg(server)
    scope = _production_scope(tmp_path / "fail")
    server.push({"status": 200})
    details: list[str] = []
    original_emit = decision.DecisionClient._emit

    def emit_spy(
        self: decision.DecisionClient,
        dp: str,
        start: float,
        available: bool,
        reason: str | None,
        attempts: int,
        answers: dict | None,
        detail: object,
        transport: str,
        confidence_source: str,
        backend: db.DecisionBackend | None = None,
    ) -> dict:
        details.append(str(detail or ""))
        return original_emit(
            self,
            dp,
            start,
            available,
            reason,
            attempts,
            answers,
            detail,
            transport,
            confidence_source,
            backend,
        )

    monkeypatch.setattr(decision.DecisionClient, "_emit", emit_spy)

    result = _client(cfg, scope).decide({"note": f"material {SECRET_LEGACY}"}, QUESTIONS)

    assert result["available"] is False
    assert result["reason"] == decision.REASON_ENTRY_UNAVAILABLE
    assert result["attempts"] == 0
    assert server.requests == [], "an incomplete known set still reached the transport"
    detail = " ".join(details)
    assert "RuntimeError" in detail, "the failure kind must stay visible"
    assert "known-secret set incomplete" in detail
    assert "boom" not in detail, "the exception message is echoed"
    _assert_no_value(detail, SECRET_SENT, SECRET_LEGACY)
    _assert_no_value(json.dumps(result), SECRET_SENT, SECRET_LEGACY)

    rows = _rows(scope.sink)
    assert _rows_of(rows, "attempt-start") == []
    assert _rows_of(rows, "attempt-end") == []
    assert _rows_of(rows, "book-snapshot") == []
    raw = scope.sink.read_bytes() if scope.sink.exists() else b""
    _assert_no_value(raw.decode("utf-8", "replace"), SECRET_SENT, SECRET_LEGACY, "boom")


# ---------------------------------------------------------------------------
# 5. no capture scope: the explicit cfg leg still resolves nothing
# ---------------------------------------------------------------------------


def test_no_scope_explicit_key_keeps_zero_discovery(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pre-T05i explicit-key contract, and no extra global auth read."""
    _write_auth(auth_json, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    server.push({"status": 200})

    result = _client(cfg, None).decide({"note": "no capture scope"}, QUESTIONS)

    assert result["available"] is True, result
    assert calls == [], "a scope-less explicit cfg key must resolve nothing"
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT]

    # Diagnostics keep their own pre-existing live order: none at all with an
    # explicit key, exactly one (their own) without it.
    assert db.credential_status(cfg) == {"timi": True}
    assert calls == []
    server.push({"status": 200})
    probe_rows = db.probe_matrix(cfg)
    assert probe_rows and probe_rows[0]["verdict"] == "ok", probe_rows
    assert calls == []

    keyless = _cfg(server, api_key=None)
    server.push({"status": 200})
    db.probe_matrix(keyless)
    assert calls == [SECRET_LEGACY], "probe gained an extra auth read"
