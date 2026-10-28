"""test_decision_timi_credential_snapshot.py - T05i (mw-decision-dashboard).

Review N1 (dd-review-cli-config, P3/边界, not waived): the book gate's known
secret set resolved the timi credential at gate time (``decision.py``
``known_credential_values``), the wire capture redactor resolved it once per
logical call (``credential_redactor``), and ``decision_backends`` re-resolved it
on *every* attempt. A credential rotated between those resolutions produced
three different "actual" values for one command: gate=A, capture=A,
Authorization=A then B on retry. T05g closed the ``cfg`` leg only.

The contract pinned here (card T05i, transport slice):

* the timi credential is resolved **once per logical client call**; every real
  POST of that call (client retry / backend ``Retry-After`` retry alike) sends
  the same Authorization value;
* a rotation is picked up by the **next** logical call: dynamic refresh is kept,
  only the granularity moves from per-attempt to per-call;
* the capture redactor of a call is built from that same snapshot, so the next
  call's rotated value is redacted instead of leaking through a stale redactor;
* a caller can pin the snapshot *before* the gate and hand the same object to
  the book gate redactor and to ``DecisionClient`` - the wiring the CLI
  (``mw.py``) and the observation seam (``decision_points.py``) still owe;
* the existing explicit ``cfg`` ``api_key`` leg still wins without resolving
  anything; missing credential / disabled config / zero global budget still send
  nothing and do not resolve; the frozen four-parameter ``_http_post`` signature
  and the ``decide`` response keys are unchanged.

Everything is synthetic and hermetic: the timi credential lives in a tmp
``auth.json`` (``decision_backends._auth_json_path`` is patched *before* any
test body runs), credential env names are removed, the only socket is a stdlib
``http.server`` on 127.0.0.1:0, and no real credential file is read. The
synthetic values are never logged by the code under test; the evidence copy of
the pytest log masks them as ``<rot-a>`` / ``<rot-b>``.
"""

from __future__ import annotations

import http.server
import inspect
import json
import pathlib
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_backends as db  # noqa: E402
import decision_wire as wire  # noqa: E402

SECRET_A = "timi-rotate-a-0123456789abcdef"
SECRET_B = "timi-rotate-b-0123456789abcdef"
CFG_SECRET = "timi-cfg-key-0123456789abcdef"
ENV_SECRET = "timi-env-key-0123456789abcdef"
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
CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
    "TIMI_BASE_URL",
)


# ── local stdlib HTTP transport (the real boundary, never mocked) ───────────


class _Handler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(length)
        authorization = self.headers.get("Authorization") or ""
        server = self.server
        request = {
            "path": self.path,
            "headers": {name: value for name, value in self.headers.items()},
            "body": body,
            "authorization": authorization,
        }
        server.requests.append(request)
        hook = server.on_request
        if hook is not None:
            hook(request, len(server.requests))
        step = server.next_step()
        status = int(step.get("status", 200))
        payload = step.get("body")
        if payload is None:
            # Echo the Authorization value the server actually received: the
            # capture must redact it with the same snapshot the request used.
            payload = json.dumps(
                {
                    "model": "jev-latest",
                    "answers": {"probe": {"type": "noul", "noul": 0.91}},
                    "note": f"used {authorization}",
                },
                ensure_ascii=False,
            ).encode("utf-8")
        elif not isinstance(payload, bytes):
            payload = str(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", step.get("content_type", "application/json"))
        self.send_header("Content-Length", str(len(payload)))
        for name, value in (step.get("headers") or {}).items():
            self.send_header(name, value)
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
    thread = threading.Thread(target=instance.serve_forever, daemon=True, name="t05i-http")
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


# ── hermetic credential plumbing (synthetic tmp auth.json only) ────────────


@pytest.fixture(autouse=True)
def auth_json(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    """No ambient credential and no real ``~/.pi/agent/auth.json``, ever."""
    for name in CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    path = tmp_path / "home" / ".pi" / "agent" / "auth.json"
    monkeypatch.setattr(db, "_auth_json_path", lambda: path)
    return path


def _write_auth(path: pathlib.Path, key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"timi": {"key": key}}), encoding="utf-8", newline="\n")


def _rotate_on_first_request(path: pathlib.Path, rotated: str):
    """Hook: rotate the auth.json the moment the first POST arrives mid-call."""

    def hook(request: dict, count: int) -> None:
        if count == 1:
            _write_auth(path, rotated)

    return hook


def _count_resolutions(monkeypatch: pytest.MonkeyPatch) -> list[str | None]:
    """Count real env/auth.json resolutions (the credential discovery step)."""
    original = db.resolve_timi_api_key
    calls: list[str | None] = []

    def spy(env: dict | None = None, auth_path: pathlib.Path | None = None):
        value = original(env, auth_path)
        calls.append(value)
        return value

    monkeypatch.setattr(db, "resolve_timi_api_key", spy)
    return calls


def _cfg(server: _Server, **overrides) -> decision.DecisionConfig:
    cfg = decision.DecisionConfig(
        enabled=True,
        extras={"base_url": server.base_url},
        timeout_s=5.0,
        max_retries=2,
        backoff_base_s=0.0,
    )
    for name, value in overrides.items():
        if name == "api_key":
            cfg.extras["api_key"] = value
        else:
            setattr(cfg, name, value)
    return cfg


def _production_scope(tmp_path: pathlib.Path) -> wire.WireScope:
    """A production scope without a redactor: the client must inject one."""
    return wire.WireScope(
        sink=tmp_path / "wire" / "wire.jsonl",
        project_id="proj-t05i",
        scope_kind="production",
        origin="t05i",
        decision_id="dec-t05i",
        dp="dp3-worker-clarify",
        evidence_path=tmp_path / "triage.jsonl",
        warn=lambda message: None,
    )


def _client(
    cfg: decision.DecisionConfig, scope: wire.WireScope, **kwargs
) -> decision.DecisionClient:
    return decision.DecisionClient(cfg, db.TimiDecisionsBackend(), wire_scope=scope, **kwargs)


def _rows(path: pathlib.Path) -> list[dict]:
    assert path.exists(), f"missing wire ledger {path}"
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _response_notes(path: pathlib.Path) -> list[str]:
    notes: list[str] = []
    for row in _rows(path):
        if row["kind"] != "attempt-end":
            continue
        response = row.get("response") or {}
        notes.append(str(response.get("text") or ""))
    return notes


# ── one logical call: one resolution, one Authorization for every attempt ──


def test_rotation_inside_one_logical_call_never_changes_the_authorization(
    server: _Server, tmp_path: pathlib.Path, auth_json: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """500, 500, 200 with the auth.json rotated after the first POST.

    Baseline (card N1): attempt 2 and 3 re-resolved and sent B while the gate
    set and the capture redactor still held A. The transport must now keep the
    call's one frozen value.
    """
    _write_auth(auth_json, SECRET_A)
    resolutions = _count_resolutions(monkeypatch)
    server.on_request = _rotate_on_first_request(auth_json, SECRET_B)
    server.push({"status": 500})
    server.push({"status": 500})
    server.push({"status": 200})
    scope = _production_scope(tmp_path)
    cfg = _cfg(server)

    result = _client(cfg, scope).decide({"note": "t05i"}, QUESTIONS)

    assert result["available"] is True
    assert set(result) == set(RESPONSE_KEYS)
    assert result["attempts"] == 3
    # Every real POST of one logical call carries the same Authorization.
    assert [request["authorization"] for request in server.requests] == [SECRET_A] * 3
    # ... and it was resolved exactly once for the whole call.
    assert len(resolutions) == 1
    raw = scope.sink.read_bytes()
    assert SECRET_A.encode() not in raw, "the call's own Authorization leaked into capture"
    assert SECRET_B.encode() not in raw, "the rotated credential leaked into capture"
    assert b"<redacted>" in raw
    notes = _response_notes(scope.sink)
    assert len(notes) == 3
    assert all("<redacted>" in note for note in notes)


def test_a_new_logical_call_re_resolves_and_capture_follows_the_rotation(
    server: _Server, tmp_path: pathlib.Path, auth_json: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Refresh granularity: per logical call (not per attempt, not never).

    Baseline: call 2 sent the rotated B but the client had already injected
    call 1's redactor, so the echoed B was persisted raw - the exact "later
    rotation leaks into capture" case.
    """
    _write_auth(auth_json, SECRET_A)
    resolutions = _count_resolutions(monkeypatch)
    server.push({"status": 200})
    scope = _production_scope(tmp_path)
    cfg = _cfg(server)
    client = _client(cfg, scope)

    first = client.decide({"note": "one"}, QUESTIONS)
    assert first["available"] is True
    assert server.requests[0]["authorization"] == SECRET_A

    _write_auth(auth_json, SECRET_B)
    server.push({"status": 200})
    second = client.decide({"note": "two"}, QUESTIONS)
    assert second["available"] is True
    assert server.requests[1]["authorization"] == SECRET_B

    raw = scope.sink.read_bytes()
    assert SECRET_A.encode() not in raw
    assert SECRET_B.encode() not in raw, "call 2's rotated value was captured unredacted"
    assert b"<redacted>" in raw
    # Exactly one resolution per logical call (baseline: redactor + attempt).
    assert len(resolutions) == 2
    assert client.last_credential_source == "auth-json"


# ── the snapshot object callers pin *before* the gate ──────────────────────


def test_pinned_snapshot_aligns_gate_set_capture_and_authorization(
    server: _Server, tmp_path: pathlib.Path, auth_json: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The CLI/observation wiring: resolve once, gate and send with that object.

    A rotation between the snapshot and the send must not produce gate=A /
    Authorization=B: the pinned value is sent, and the rotated value is neither
    sent nor part of this command's known set (a value rotated in after the
    snapshot is not claimed by it).
    """
    _write_auth(auth_json, SECRET_A)
    resolutions = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    snapshot = decision.credential_snapshot(cfg)
    assert snapshot.present is True
    assert snapshot.api_key == SECRET_A
    assert snapshot.source == "auth-json"
    assert len(resolutions) == 1

    # Rotation after the snapshot, before the first POST.
    _write_auth(auth_json, SECRET_B)
    gate = decision.known_secret_redactor(cfg, snapshot=snapshot)
    gate_a = gate.redact(f"material {SECRET_A}")
    gate_b = gate.redact(f"material {SECRET_B}")
    assert gate_a.hits >= 1 and SECRET_A not in gate_a.text
    assert gate_b.hits == 0 and SECRET_B in gate_b.text

    server.push({"status": 500})
    server.push({"status": 200})
    scope = _production_scope(tmp_path)
    client = _client(cfg, scope, credential_snapshot=snapshot)

    result = client.decide({"note": f"state carries {SECRET_A}"}, QUESTIONS)

    assert result["available"] is True
    assert result["attempts"] == 2
    assert [request["authorization"] for request in server.requests] == [SECRET_A, SECRET_A]
    # The pinned snapshot is authoritative: the client resolved nothing again.
    assert len(resolutions) == 1
    raw = scope.sink.read_bytes()
    assert SECRET_A.encode() not in raw
    assert SECRET_B.encode() not in raw
    assert b"<redacted>" in raw


def test_explicit_cfg_api_key_leg_wins_and_is_frozen_per_call(
    server: _Server, tmp_path: pathlib.Path, auth_json: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The pre-existing explicit ``cfg``/extras ``api_key`` transport still wins.

    T05m: a capture scope is a known-set face, so the production scope below
    freezes the *complete* known set before its first capture - one synthetic
    legacy timi discovery (B), never a second read of the sent value, and the
    rotation after that is still invisible to this call. Without a capture scope
    the explicit key keeps the pre-T05i zero-discovery contract.
    """
    _write_auth(auth_json, SECRET_B)
    resolutions = _count_resolutions(monkeypatch)
    cfg = _cfg(server, api_key=CFG_SECRET)
    snapshot = decision.credential_snapshot(cfg)
    assert snapshot.api_key == CFG_SECRET
    assert snapshot.source == "cfg-extras"
    assert resolutions == []

    server.on_request = _rotate_on_first_request(auth_json, SECRET_A)
    server.push({"status": 500})
    server.push({"status": 200})
    scope = _production_scope(tmp_path)
    client = _client(cfg, scope, credential_snapshot=snapshot)
    gate = decision.known_secret_redactor(cfg, snapshot=snapshot)
    assert gate.redact(CFG_SECRET).hits == 1

    result = client.decide({"note": "cfg leg"}, QUESTIONS)

    assert result["available"] is True
    assert result["attempts"] == 2
    assert [request["authorization"] for request in server.requests] == [CFG_SECRET, CFG_SECRET]
    # T05m: the production capture freezes the unit's complete known set, which
    # discovers the legacy timi leg exactly once (snapshot creation itself still
    # resolved nothing, see above). The rotation on the first POST is not part
    # of this call, and the sent value never triggers a discovery.
    assert resolutions == [SECRET_B]
    raw = scope.sink.read_bytes()
    assert CFG_SECRET.encode() not in raw
    assert SECRET_A.encode() not in raw and SECRET_B.encode() not in raw

    # No capture scope: the explicit cfg leg still resolves nothing at all.
    server.push({"status": 200})
    scope_less = _client(cfg, None)
    assert scope_less.decide({"note": "cfg leg, no scope"}, QUESTIONS)["available"] is True
    assert resolutions == [SECRET_B], "a scope-less explicit cfg call resolved the timi chain"


def test_snapshot_source_is_named_and_repr_hides_the_value(
    tmp_path: pathlib.Path, auth_json: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The snapshot is safe to hold and to report: source only, never the value."""
    cfg_extras = decision.DecisionConfig(enabled=True, extras={"api_key": CFG_SECRET})
    cfg_attr = decision.DecisionConfig(enabled=True)
    cfg_attr.api_key = CFG_SECRET
    _write_auth(auth_json, SECRET_A)

    from_extras = decision.credential_snapshot(cfg_extras)
    from_attr = decision.credential_snapshot(cfg_attr)
    from_env = decision.credential_snapshot(None, env={"TIMI_API_KEY": ENV_SECRET})
    from_auth = decision.credential_snapshot(None, env={})
    from_none = decision.credential_snapshot(
        None, env={}, auth_path=tmp_path / "absent-auth.json"
    )

    assert from_extras.source == "cfg-extras"
    assert from_attr.source == "cfg"
    assert from_env.source == "env"
    assert from_auth.source == "auth-json"
    assert from_none.source == "none" and from_none.present is False
    for snapshot, secret in (
        (from_extras, CFG_SECRET),
        (from_attr, CFG_SECRET),
        (from_env, ENV_SECRET),
        (from_auth, SECRET_A),
    ):
        assert snapshot.api_key == secret
        assert secret not in repr(snapshot)
    assert decision.current_credential_snapshot() is None


# ── regressions: zero send / zero resolution on the existing refusals ──────


def test_missing_credential_is_entry_unavailable_with_zero_http(
    server: _Server, tmp_path: pathlib.Path, auth_json: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    resolutions = _count_resolutions(monkeypatch)
    server.push({"status": 200})
    scope = _production_scope(tmp_path)
    cfg = _cfg(server)

    result = _client(cfg, scope).decide({"note": "no credential"}, QUESTIONS)

    assert result["available"] is False
    assert result["reason"] == "entry-unavailable"
    assert result["attempts"] == 1
    assert server.requests == []
    assert len(resolutions) == 1
    assert SECRET_A.encode() not in scope.sink.read_bytes()


def test_disabled_config_and_zero_global_budget_send_nothing_and_resolve_nothing(
    server: _Server, tmp_path: pathlib.Path, auth_json: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_auth(auth_json, SECRET_A)
    resolutions = _count_resolutions(monkeypatch)
    server.push({"status": 200})

    disabled_scope = _production_scope(tmp_path / "disabled")
    disabled = _client(_cfg(server, enabled=False), disabled_scope)
    disabled_result = disabled.decide({"note": "disabled"}, QUESTIONS)
    assert disabled_result["available"] is False
    assert disabled_result["reason"] == "disabled"
    assert disabled_result["attempts"] == 0

    budget_scope = _production_scope(tmp_path / "budget")
    budget = _client(_cfg(server, max_total_tokens=1), budget_scope)
    budget_result = budget.decide({"note": "over budget"}, QUESTIONS)
    assert budget_result["available"] is False
    assert budget_result["reason"] == "budget-exhausted"
    assert budget_result["attempts"] == 0

    assert server.requests == []
    # Both refusals happen before the credential is ever resolved.
    assert resolutions == []
    for scope in (disabled_scope, budget_scope):
        attempts = (
            [row for row in _rows(scope.sink) if row["kind"].startswith("attempt-")]
            if scope.sink.exists()
            else []
        )
        assert attempts == []


def test_capture_failure_does_not_change_the_business_result_and_binding_resets(
    server: _Server, tmp_path: pathlib.Path, auth_json: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _write_auth(auth_json, SECRET_A)
    _count_resolutions(monkeypatch)
    server.push({"status": 200})
    sink_dir = tmp_path / "sink-is-a-directory"
    sink_dir.mkdir()
    scope = wire.WireScope(
        sink=sink_dir,
        project_id="proj-t05i",
        scope_kind="production",
        origin="t05i",
        decision_id="dec-t05i-fail",
        evidence_path=tmp_path / "triage-fail.jsonl",
        warn=lambda message: None,
    )
    client = _client(_cfg(server), scope)

    result = client.decide({"note": "capture fails"}, QUESTIONS)

    assert result["available"] is True
    assert result["attempts"] == 1
    assert client.capture_status == "failed"
    assert decision.current_credential_snapshot() is None

    snapshot = decision.credential_snapshot(None, env={}, auth_path=auth_json)
    assert decision.current_credential_snapshot() is None
    with decision.use_credential_snapshot(snapshot):
        assert decision.current_credential_snapshot() is snapshot
        with decision.use_credential_snapshot(None):
            assert decision.current_credential_snapshot() is None
        assert decision.current_credential_snapshot() is snapshot
    assert decision.current_credential_snapshot() is None


def test_frozen_transport_and_response_contract_is_unchanged() -> None:
    assert list(inspect.signature(db._http_post).parameters) == [
        "url",
        "headers",
        "payload",
        "timeout_s",
    ]
    assert decision.REASON_DISABLED == "disabled"
    assert decision.REASON_ENTRY_UNAVAILABLE == "entry-unavailable"
