"""test_decision_redactor_contract.py - T05p (mw-decision-dashboard).

T05o closed the two *send* entries against a pinned snapshot with no frozen
known set (``frozen_known_values() is None``). What stayed open is the redactor
factory layer itself (``workers/dd-review-pin-final/report.md`` F-R1):

* ``known_credential_values`` fell back to the *legacy live* set when handed a
  directly constructed ``CredentialSnapshot`` - i.e. it silently invented an
  authority the snapshot never froze, and a caller that treated the result as
  this unit's known set got exactly the divergence T05l/T05n removed;
* ``credential_redactor`` / ``known_secret_redactor`` propagated that fallback
  instead of applying their own "no provable set" policy;
* the *client-only* path (``DecisionClient.decide`` used without
  ``decision_points.decide_for``) never verified a caller-owned production
  capture redactor at all. The points seam has
  ``_caller_scope_coverage_issue``; a bare client did not, so a caller filter
  that covered only the sent ``Authorization`` (A) stored the legacy timi key
  (B) raw - response body, response metadata and failure output alike.

The contract pinned here (card T05p):

* the three factories reject an explicit None-base snapshot with their own safe
  policy: ``known_credential_values`` raises a fixed, value-free ``TypeError``;
  ``credential_redactor`` returns ``None`` (safe omit: metadata-only capture);
  ``known_secret_redactor`` returns a **fail-closed** gate (never ``None``,
  never a smaller set that would accept material);
* the ``CredentialSnapshot`` class stays constructible as non-send data;
* the existing policies are preserved: a duck snapshot is refused by all three,
  a snapshot whose discovery raised still yields ``None`` / fail-closed, and a
  factory snapshot (``credential_snapshot()``) stays legal everywhere;
* a client-only production scope with a caller-owned redactor that misses the
  legacy leg (or any other known value) is refused before capture/transport
  with a count-only message; the caller's redactor is never replaced;
* a caller-owned redactor that covers the complete frozen set is kept as-is and
  keeps redacting across retries (one freeze per unit, no extra discovery).

Everything is synthetic and hermetic: every credential-shaped env name is
removed before each test, ``HOME``/``USERPROFILE`` and
``decision_backends._auth_json_path`` point into ``tmp_path`` before any read,
and the only socket is a stdlib ``http.server`` bound to ``127.0.0.1:0``. The
fixture values are fabricated; a failing assertion quotes them verbatim in
pytest's output (that quote *is* the evidence), so these logs are not masked and
do not claim to be. No real credential, model, service or browser is touched.
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

DP3 = "dp3-worker-clarify"

#: The unit's actual ``Authorization`` (explicit cfg leg of the origin config).
SECRET_SENT = "t05p-sent-a-0123456789abcdef"
#: The key carried by a directly constructed (None-base) snapshot.
SECRET_NONE_BASE = "t05p-nonebase-p-0123456789ab"
#: The legacy timi leg (``auth.json`` ``timi.key``) that is never sent here.
SECRET_LEGACY = "t05p-legacy-b-0123456789abc"
#: Ambient env heuristic value (``_TOKEN`` suffix); removed by the fixture.
SECRET_ENV = "t05p-env-ambient-d-0123456789ab"
ENV_NAME = "T05P_PROBE_TOKEN"
#: Never matches ``sk-`` / ``Bearer`` / the env heuristics.
PLAIN_MATERIAL = "plain-t05p-material-0123456789"

QUESTIONS = {"probe": {"type": "noul", "instructions": "Is this probe well formed?"}}
PROBE_ANSWERS = {"probe": {"type": "noul", "noul": 0.91}}
DEFAULT_USAGE = {"prompt_tokens": 7, "total_tokens": 9}


def _credential_env_names() -> tuple[str, ...]:
    names = {name for name in os.environ if name.upper().endswith(decision._CRED_ENV_SUFFIXES)}
    names.update((ENV_NAME, "TIMI_API_KEY", "TIMI_BASE_URL"))
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
        step = server.next_step()
        status = int(step.get("status", 200))
        payload = step.get("body")
        if payload is None:
            payload = json.dumps(
                {
                    "model": "jev-latest",
                    "answers": server.answers,
                    "usage": dict(server.usage),
                    "note": f"used {authorization} body {body.decode('utf-8', 'replace')}",
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
    thread = threading.Thread(target=instance.serve_forever, daemon=True, name="t05p-http")
    thread.start()
    try:
        yield instance
    finally:
        instance.shutdown()
        instance.server_close()
        thread.join(timeout=5)


# -- hermetic credential plumbing (tmp HOME/auth.json only) -----------------


@pytest.fixture(autouse=True)
def isolated_home(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path) -> pathlib.Path:
    """No ambient credential, no real ``~/.pi/agent/auth.json``, ever."""
    for name in _credential_env_names():
        monkeypatch.delenv(name, raising=False)
    leftover = sorted(
        name for name in os.environ if name.upper().endswith(decision._CRED_ENV_SUFFIXES)
    )
    assert leftover == [], f"ambient credential env vars survived the fixture: {leftover}"
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    auth = home / ".pi" / "agent" / "auth.json"
    # Patch *before* any discovery can read: a real auth file is unreachable.
    monkeypatch.setattr(db, "_auth_json_path", lambda: auth)
    assert db._auth_json_path() == auth
    yield auth


def _write_auth(path: pathlib.Path, key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"timi": {"key": key}}), encoding="utf-8", newline="\n")


def _count_resolutions(
    monkeypatch: pytest.MonkeyPatch, *, error: Exception | None = None
) -> list[str | None]:
    """Count ambient discoveries; abort if one would leave the tmp home."""
    original = db.resolve_timi_api_key
    calls: list[str | None] = []

    def spy(env: dict | None = None, auth_path: pathlib.Path | None = None):
        if env is None and auth_path is None:
            redirected = db._auth_json_path()
            assert str(redirected).startswith(str(pathlib.Path(os.environ["HOME"]))), (
                f"the discovery would read a real auth path: {redirected}"
            )
            if error is not None:
                raise error
            value = original(env, auth_path)
            calls.append(value)
            return value
        return original(env, auth_path)

    monkeypatch.setattr(db, "resolve_timi_api_key", spy)
    return calls


# -- config / scope plumbing -----------------------------------------------


def _cfg(
    server: _Server,
    *,
    api_key: str | None = SECRET_SENT,
    extras_key: bool = True,
) -> decision.DecisionConfig:
    extras: dict = {"base_url": server.base_url}
    if extras_key and api_key is not None:
        extras["api_key"] = api_key
    return decision.DecisionConfig(
        enabled=True,
        extras=extras,
        timeout_s=5.0,
        max_retries=2,
        backoff_base_s=0.0,
    )


def _production_scope(root: pathlib.Path, *, redact: object | None = None) -> wire.WireScope:
    """A production scope; ``redact`` is the caller-owned filter when given."""
    return wire.WireScope(
        sink=root / "wire" / "wire.jsonl",
        project_id="proj-t05p",
        scope_kind="production",
        origin="t05p",
        decision_id="dec-t05p",
        dp=DP3,
        evidence_path=root / "triage.jsonl",
        redact=redact,
        warn=lambda message: None,
    )


def _client(
    cfg: decision.DecisionConfig,
    scope: wire.WireScope | None,
    **kwargs: object,
) -> decision.DecisionClient:
    return decision.DecisionClient(cfg, db.TimiDecisionsBackend(), wire_scope=scope, **kwargs)


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


def _capture_texts(rows: list[dict], kind: str, field: str) -> list[str]:
    texts: list[str] = []
    for row in _rows_of(rows, kind):
        capture = row.get(field) or {}
        if capture.get("text") is not None:
            texts.append(str(capture["text"]))
    return texts


def _covers(redactor: object, value: str) -> bool:
    """True only when the redactor provably removes ``value``."""
    try:
        result = redactor.redact(value)  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001 - a raising filter never proves coverage
        return False
    hits = getattr(result, "hits", None)
    if isinstance(hits, int):
        return hits > 0
    return getattr(result, "text", value) != value


def _assert_absent(text: str, *values: str) -> None:
    for value in values:
        assert value not in text, "credential-shaped material reached stored text"


# ---------------------------------------------------------------------------
# 1. the three known-set factories reject an explicit None-base snapshot
# ---------------------------------------------------------------------------


def test_none_base_snapshot_is_rejected_by_the_three_known_set_factories(
    server: _Server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED (T05p): ``known_credential_values`` invented the legacy live set.

    A directly constructed snapshot carries a key but froze nothing, so it
    cannot be this unit's authority. Each factory applies its own safe policy:
    a fixed value-free ``TypeError``, a safe ``None`` omit, and a fail-closed
    gate that is never ``None`` (a ``None`` gate must never read as "allow").
    """
    monkeypatch.setenv(ENV_NAME, SECRET_ENV)
    cfg = _cfg(server)
    pin = decision.CredentialSnapshot(api_key=SECRET_NONE_BASE, source="cfg")
    assert pin.frozen_known_values() is None, "fixture must be a None-base snapshot"
    assert SECRET_NONE_BASE not in repr(pin), "the snapshot repr must hide the key"

    with pytest.raises(TypeError) as excinfo:
        decision.known_credential_values(cfg, snapshot=pin)
    message = str(excinfo.value)
    assert "froze no known set" in message, message
    assert "credential_snapshot" in message, message
    _assert_absent(message, SECRET_NONE_BASE, SECRET_SENT, SECRET_ENV)
    assert "RuntimeError" not in message and "boom" not in message

    assert decision.credential_redactor(cfg, snapshot=pin) is None, (
        "a None-base snapshot must yield a safe omit, never a live fallback filter"
    )

    gate = decision.known_secret_redactor(cfg, snapshot=pin)
    assert gate is not None, "the gate factory must never return None (no implicit allow)"
    assert gate.fail_closed is True, "a None-base snapshot must not become a smaller set"
    refused = gate.redact(f"material {SECRET_LEGACY} and {PLAIN_MATERIAL}")
    assert refused.text == "<redacted>", refused.text
    assert refused.hits == 1
    _assert_absent(refused.text, SECRET_LEGACY, SECRET_NONE_BASE)


# ---------------------------------------------------------------------------
# 2. duck / discovery-failure / legal factory policies are preserved
# ---------------------------------------------------------------------------


def test_duck_and_discovery_failure_policies_are_unchanged(
    server: _Server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The new None-base refusal must not change the neighbouring policies."""
    cfg = _cfg(server)

    class Duck:
        api_key = SECRET_SENT

    duck = Duck()
    with pytest.raises(TypeError):
        decision.known_credential_values(cfg, snapshot=duck)
    assert decision.credential_redactor(cfg, snapshot=duck) is None
    duck_gate = decision.known_secret_redactor(cfg, snapshot=duck)
    assert duck_gate is not None and duck_gate.fail_closed is True

    # A discovery that raised is still recorded, and both factories stay safe.
    _count_resolutions(monkeypatch, error=RuntimeError(f"boom {SECRET_LEGACY}"))
    broken = decision.credential_snapshot(_cfg(server, api_key=None))
    assert broken.discovery_error is not None
    assert broken.frozen_known_values() is not None, "the factory always freezes a base"
    assert decision.credential_redactor(cfg, snapshot=broken) is None
    broken_gate = decision.known_secret_redactor(cfg, snapshot=broken)
    assert broken_gate is not None and broken_gate.fail_closed is True
    assert isinstance(decision.known_credential_values(cfg, snapshot=broken), tuple)
    assert SECRET_LEGACY not in json.dumps(broken.discovery_error)
    assert "boom" not in str(broken.discovery_error), "the exception message is echoed"

    # A legal factory snapshot stays usable through all three APIs.
    snapshot = decision.credential_snapshot(cfg)
    values = decision.known_credential_values(cfg, snapshot=snapshot)
    assert SECRET_SENT in values
    redactor = decision.credential_redactor(cfg, snapshot=snapshot)
    assert redactor is not None and _covers(redactor, SECRET_SENT)
    gate = decision.known_secret_redactor(cfg, snapshot=snapshot)
    assert gate.fail_closed is False
    assert _covers(gate, SECRET_SENT)
    assert not _covers(gate, PLAIN_MATERIAL)


# ---------------------------------------------------------------------------
# 3. client-only caller-owned redactor that misses the legacy leg: refused
# ---------------------------------------------------------------------------


def test_client_only_caller_owned_redactor_missing_the_legacy_leg_is_refused(
    server: _Server,
    tmp_path: pathlib.Path,
    isolated_home: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED (T05p): a bare client never verified a caller-owned capture filter.

    The caller filter covers exactly the sent value A, while ``auth.json`` holds
    B and the upstream echoes/mentions B in its body, metadata and failure text.
    Before this card the client sent and stored B raw - this is the "client-only
    caller-owned scope" mis-combination F-R1 named as reachable. The filter is
    never replaced; the call is refused before capture/transport instead.
    """
    _write_auth(isolated_home, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    caller_redactor = wire.SubstringRedactor([SECRET_SENT])
    scope = _production_scope(tmp_path / "caller-gap", redact=caller_redactor)
    server.usage = {f"trace-{SECRET_LEGACY}": SECRET_LEGACY, "prompt_tokens": 7}
    server.push({"status": 500, "body": f"upstream failed near {SECRET_LEGACY}"})
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

    result = _client(cfg, scope).decide(
        {"note": f"carried {SECRET_LEGACY} and {PLAIN_MATERIAL}"}, QUESTIONS
    )

    # Computed before the refusals so the RED run records the actual leak: the
    # pre-fix client sent A and persisted the legacy B raw.
    leaked_raw = scope.sink.read_text(encoding="utf-8") if scope.sink.exists() else ""
    stored_legacy = SECRET_LEGACY in leaked_raw
    assert result["available"] is False, (
        "an incomplete caller filter still sent/captured "
        f"(stored_legacy={stored_legacy}, stored_bytes={len(leaked_raw)})"
    )
    assert result["reason"] == decision.REASON_ENTRY_UNAVAILABLE
    assert result["attempts"] == 0
    assert result["answers"] is None
    assert server.requests == [], "the unprovable capture reached the HTTP transport"
    assert scope.redact is caller_redactor, "the caller-owned redactor was replaced"

    detail = " ".join(details)
    assert "caller-owned capture redactor" in detail, detail
    assert "does not cover" in detail, detail
    _assert_absent(detail, SECRET_SENT, SECRET_LEGACY, SECRET_ENV, SECRET_NONE_BASE)
    _assert_absent(json.dumps(result), SECRET_SENT, SECRET_LEGACY, SECRET_ENV)

    rows = _rows(scope.sink)
    assert _rows_of(rows, "attempt-start") == []
    assert _rows_of(rows, "attempt-end") == []
    assert _rows_of(rows, "book-snapshot") == []
    raw = scope.sink.read_text(encoding="utf-8") if scope.sink.exists() else ""
    _assert_absent(raw, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)
    # Verifying the complete known set costs exactly the one legacy read this
    # production capture needs - not a per-face or per-retry one.
    assert calls == [SECRET_LEGACY], f"the refusal paid {len(calls)} discoveries"
    assert decision.current_credential_snapshot() is None, "a binding leaked"


# ---------------------------------------------------------------------------
# 4. a complete caller-owned redactor is kept and redacts across retries
# ---------------------------------------------------------------------------


def test_client_only_caller_owned_complete_redactor_is_kept_across_retries(
    server: _Server,
    tmp_path: pathlib.Path,
    isolated_home: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The verification must not over-refuse: a complete filter keeps working.

    The caller resolves the same snapshot (including its legacy leg) and builds
    the filter from it. The client verifies it, never replaces it, and one
    logical unit pays exactly one freeze - retries included.
    """
    _write_auth(isolated_home, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    snapshot = decision.credential_snapshot(cfg)
    assert snapshot.known_superset() == (SECRET_LEGACY,)
    caller_redactor = decision.credential_redactor(cfg, snapshot=snapshot)
    assert caller_redactor is not None and _covers(caller_redactor, SECRET_LEGACY)
    assert calls == [SECRET_LEGACY], "the caller's own freeze read the chain twice"

    scope = _production_scope(tmp_path / "caller-complete", redact=caller_redactor)
    server.usage = {f"trace-{SECRET_LEGACY}": SECRET_LEGACY, "prompt_tokens": 7}
    server.push({"status": 500, "body": f"upstream failed near {SECRET_LEGACY}"})
    server.push({"status": 200})

    result = _client(cfg, scope, credential_snapshot=snapshot).decide(
        {"note": f"carried {SECRET_LEGACY} and {PLAIN_MATERIAL}"}, QUESTIONS
    )

    assert result["available"] is True, result
    assert result["attempts"] == 2, result
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT] * 2
    assert scope.redact is caller_redactor, "the caller-owned redactor was replaced"
    assert calls == [SECRET_LEGACY], "verification re-opened the known-set discovery"

    rows = _rows(scope.sink)
    raw = scope.sink.read_text(encoding="utf-8")
    _assert_absent(raw, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)
    assert "<redacted>" in raw
    request_texts = _capture_texts(rows, "attempt-start", "request")
    response_texts = _capture_texts(rows, "attempt-end", "response")
    assert len(request_texts) == 2 and len(response_texts) == 2, rows
    assert PLAIN_MATERIAL in "".join(request_texts), "the request was not captured at all"
    for text in request_texts + response_texts:
        _assert_absent(text, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)
    # A 500 failure body is free text; it must be redacted like any capture.
    assert "upstream failed" in response_texts[0]
    assert "<redacted>" in response_texts[0]
    ends = _rows_of(rows, "attempt-end")
    assert [row.get("http_status") for row in ends] == [500, 200], ends
    usage = json.dumps(ends[-1].get("usage"))
    _assert_absent(usage, SECRET_SENT, SECRET_LEGACY)
    assert "<redacted>" in usage, "the arbitrary metadata key/value pair was not redacted"


# ---------------------------------------------------------------------------
# 5. None-base factory results stay safe in a client-only production scope
# ---------------------------------------------------------------------------


def test_none_base_factory_results_are_safe_in_a_client_only_production_scope(
    server: _Server,
    tmp_path: pathlib.Path,
    isolated_home: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A ``None`` wire factory result must never read as "capture anything".

    The caller derives both factories from a None-base snapshot and hands the
    redactor result (``None``) to its production scope. That is the safe omit:
    the client injects a complete filter from its own factory snapshot, so
    failure output and metadata are still redacted - nothing is exempted - while
    the book gate built from the same None-base snapshot refuses every text.
    """
    _write_auth(isolated_home, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    pin = decision.CredentialSnapshot(api_key=SECRET_NONE_BASE, source="cfg")
    omitted = decision.credential_redactor(cfg, snapshot=pin)
    gate = decision.known_secret_redactor(cfg, snapshot=pin)
    assert omitted is None and gate.fail_closed is True
    assert decision.secret_hit(f"material {SECRET_LEGACY}", gate) is True, (
        "the fail-closed gate accepted material"
    )

    scope = _production_scope(tmp_path / "nonebase-factory", redact=omitted)
    server.usage = {f"trace-{SECRET_SENT}": SECRET_SENT, "prompt_tokens": 7}
    server.push({"status": 500, "body": f"upstream failed near {SECRET_SENT}"})
    server.push({"status": 200})
    result = _client(cfg, scope).decide(
        {"note": f"carried {SECRET_SENT} and {PLAIN_MATERIAL}"}, QUESTIONS
    )

    assert result["available"] is True, result
    assert scope.redact is not None, "the client did not inject a capture filter"
    raw = scope.sink.read_text(encoding="utf-8")
    _assert_absent(raw, SECRET_SENT, SECRET_LEGACY, SECRET_NONE_BASE)
    assert "<redacted>" in raw
    rows = _rows(scope.sink)
    for text in _capture_texts(rows, "attempt-start", "request"):
        _assert_absent(text, SECRET_SENT, SECRET_LEGACY, SECRET_NONE_BASE)
    for text in _capture_texts(rows, "attempt-end", "response"):
        _assert_absent(text, SECRET_SENT, SECRET_LEGACY, SECRET_NONE_BASE)
    ends = _rows_of(rows, "attempt-end")
    assert [row.get("http_status") for row in ends] == [500, 200], ends
    usage = json.dumps(ends[-1].get("usage"))
    _assert_absent(usage, SECRET_SENT, SECRET_LEGACY)
    assert "<redacted>" in usage, "the arbitrary metadata key/value pair was not redacted"
    assert calls == [SECRET_LEGACY], f"the injection paid {len(calls)} discoveries"
    assert decision.current_credential_snapshot() is None, "a binding leaked"
