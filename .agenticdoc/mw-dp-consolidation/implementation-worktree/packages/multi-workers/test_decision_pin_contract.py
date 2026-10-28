"""test_decision_pin_contract.py - T05o (mw-decision-dashboard).

T05n froze the complete known-safe set of one unit on the snapshot produced by
:func:`decision.credential_snapshot`. Both send entries still only checked
``isinstance(snapshot, decision.CredentialSnapshot)``: a snapshot constructed
*by hand* (``CredentialSnapshot(api_key=..., source="cfg")``) passes that check
but froze nothing, so it reached the transport with an unprovable known set.
``workers/dd-review-full-value/report.md`` F2/F3 recorded that this path is
reachable, not theoretical, and rejected the "the sent value is added to the
live set, so the gap is covered" exemption: sending A never exempts B material.

The contract pinned here (card T05o):

* both send entries - :meth:`decision.DecisionClient.decide` and
  :func:`decision_points.decide_for` - refuse a pinned snapshot whose
  ``frozen_known_values()`` is ``None`` (no frozen set was ever taken);
  zero POST, zero attempt row, no book snapshot, and a value-free refusal text;
* the class itself stays constructible as non-send data (inspectable, ``repr``
  hides the key); only the sending path is closed;
* a factory snapshot (``credential_snapshot()``) stays legal at both entries;
* a foreign caller config still contributes its own explicit values (the
  cross-cfg union is never deleted), while the sent ``Authorization`` stays the
  snapshot's own key;
* an explicit cfg key with no capture scope still pays zero extra auth
  discovery, and ``credential_status`` / ``probe_matrix`` keep their live order;
* a *mutable* foreign config is folded into the unit's frozen set on first read,
  so the gate face and the capture face of one unit hold the same values even
  when that foreign object rotates in between. A value it gains after that
  first read belongs to the next unit's snapshot (like an env rotation).

Everything is synthetic and hermetic: every credential-shaped env name is
removed before each test, ``HOME``/``USERPROFILE`` and
``decision_backends._auth_json_path`` point into ``tmp_path`` before any read,
and the only socket is a stdlib ``http.server`` on ``127.0.0.1:0``. Fixture
values are fabricated; a failing assertion quotes them verbatim in pytest's
output (that quote *is* the evidence), so these logs are not masked.
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
import decision_points as dpts  # noqa: E402
import decision_wire as wire  # noqa: E402

DP3 = "dp3-worker-clarify"

#: The unit's actual ``Authorization`` (explicit cfg leg of the origin config).
SECRET_SENT = "t05o-sent-a-0123456789abcdef"
#: The key carried by a hand-built (None-base) snapshot.
SECRET_PIN = "t05o-nonebase-pin-p-0123456789ab"
#: A foreign/next-unit cfg value (explicit ``cfg.extras["api_key"]``).
SECRET_FOREIGN_OLD = "t05o-foreign-old-b-0123456789ab"
#: The rotation of that foreign cfg value (belongs to the next unit).
SECRET_FOREIGN_NEW = "t05o-foreign-new-c-0123456789ab"
#: Ambient env heuristic value (``_TOKEN`` suffix), removed by the fixture.
SECRET_ENV = "t05o-env-ambient-d-0123456789ab"
ENV_NAME = "T05O_PROBE_TOKEN"
#: Never matches ``sk-`` / ``Bearer`` / the env heuristics.
PLAIN_MATERIAL = "plain-t05o-material-0123456789"

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
    thread = threading.Thread(target=instance.serve_forever, daemon=True, name="t05o-http")
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
    monkeypatch.setattr(db, "_auth_json_path", lambda: auth)
    assert db._auth_json_path() == auth
    dpts.clear_points_config_cache()
    yield auth
    dpts.clear_points_config_cache()


def _count_resolutions(
    monkeypatch: pytest.MonkeyPatch, *, error: Exception | None = None
) -> list[str | None]:
    """Record the unit's own ambient discoveries (never a real credential read)."""
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


def _production_scope(root: pathlib.Path) -> wire.WireScope:
    """A production scope without a redactor: the client must inject one."""
    return wire.WireScope(
        sink=root / "wire" / "wire.jsonl",
        project_id="proj-t05o",
        scope_kind="production",
        origin="t05o",
        decision_id="dec-t05o",
        dp=DP3,
        evidence_path=root / "triage.jsonl",
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


def _covers(redactor: object, value: str) -> bool:
    """True only when the redactor provably removes ``value``."""
    try:
        result = redactor.redact(value)
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
# 1. a hand-built (None-base) pin is refused at the client entry
# ---------------------------------------------------------------------------


def test_none_base_pin_is_refused_at_the_client_entry(
    server: _Server,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED (T05o): ``isinstance`` alone let a snapshot with no frozen set send.

    The directly constructed object is constructible on purpose (it is a data
    carrier), but it cannot be this unit's known-set authority: refuse before
    the transport, with no attempt row and no value in the text.
    """
    monkeypatch.setenv(ENV_NAME, SECRET_ENV)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    pin = decision.CredentialSnapshot(api_key=SECRET_PIN, source="cfg")
    assert pin.frozen_known_values() is None, "fixture must be a None-base snapshot"
    assert SECRET_PIN not in repr(pin), "the snapshot repr must hide the key"

    scope = _production_scope(tmp_path / "nonebase-client")
    server.push({"status": 200})
    result = _client(cfg, scope, credential_snapshot=pin).decide(
        {"note": f"carried {SECRET_PIN} and {SECRET_ENV}"}, QUESTIONS
    )

    assert result["available"] is False, "a pin with no frozen known set was sent"
    assert result["reason"] == decision.REASON_ENTRY_UNAVAILABLE
    assert result["attempts"] == 0
    assert result["answers"] is None
    assert calls == [], "refusing the pin must not open a credential discovery"
    assert server.requests == [], "the None-base pin reached the HTTP transport"

    rows = _rows(scope.sink)
    assert _rows_of(rows, "attempt-start") == []
    assert _rows_of(rows, "attempt-end") == []
    assert _rows_of(rows, "book-snapshot") == []
    text = json.dumps(result) + (scope.sink.read_text(encoding="utf-8") if rows else "")
    _assert_absent(text, SECRET_PIN, SECRET_SENT, SECRET_ENV)
    assert decision.current_credential_snapshot() is None, "a binding leaked"


# ---------------------------------------------------------------------------
# 2. the same pin is refused at the decision-point entry
# ---------------------------------------------------------------------------


def test_none_base_pin_is_refused_at_the_points_entry(
    server: _Server,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED: the points seam only checked ``isinstance`` and sent the pin.

    The refusal must happen before the gates/capture: no POST, no attempt row,
    no book snapshot, and a value-free error.
    """
    monkeypatch.setenv(ENV_NAME, SECRET_ENV)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    pin = decision.CredentialSnapshot(api_key=SECRET_PIN, source="cfg")
    assert pin.frozen_known_values() is None

    project = _project(tmp_path)
    scope = _production_scope(tmp_path / "nonebase-points")
    client = decision.DecisionClient(
        cfg, db.TimiDecisionsBackend(), wire_scope=scope, credential_snapshot=pin
    )
    server.push({"status": 200})

    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(task_summary=f"material {SECRET_PIN} and {SECRET_ENV}"),
            project,
            client=client,
            archive=False,
            intent="answer",
        )
    message = str(excinfo.value)
    _assert_absent(message, SECRET_PIN, SECRET_SENT, SECRET_ENV)
    assert calls == [], "the refusal opened a credential discovery"
    assert server.requests == [], "the None-base pin reached the HTTP transport"
    rows = _rows(scope.sink)
    assert _rows_of(rows, "attempt-start") == []
    assert _rows_of(rows, "attempt-end") == []
    assert _rows_of(rows, "book-snapshot") == []


# ---------------------------------------------------------------------------
# 3. a factory snapshot stays legal at both entries
# ---------------------------------------------------------------------------


def test_factory_snapshot_remains_legal_at_both_entries(
    server: _Server,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The refusal is about the missing freeze, never about the class."""
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    pin = decision.credential_snapshot(cfg)
    assert pin.frozen_known_values() is not None
    assert calls == [], "the explicit cfg leg must not read the timi chain"

    # Client entry: one POST with the snapshot's own key.
    client_scope = _production_scope(tmp_path / "factory-client")
    server.push({"status": 200})
    result = _client(cfg, client_scope, credential_snapshot=pin).decide(
        {"note": f"material {SECRET_SENT}"}, QUESTIONS
    )
    assert result["available"] is True, result
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT]
    assert len(calls) <= 1, "the capture scope paid more than the one legacy leg"

    # Points entry: the same factory pin is accepted and reaches the transport.
    project = _project(tmp_path)
    points_scope = _production_scope(tmp_path / "factory-points")
    client = decision.DecisionClient(
        cfg, db.TimiDecisionsBackend(), wire_scope=points_scope, credential_snapshot=pin
    )
    server.answers = {
        "answer_kind": {"type": "choice", "choice": "fact", "confidence": 0.9},
        "answerable": {"type": "noul", "noul": 0.9},
        "candidate": {"type": "choice", "choice": "c1", "confidence": 0.9},
    }
    server.push({"status": 200})
    discoveries_before_points = len(calls)
    outcome = dpts.decide_for(
        DP3,
        _dp3_state(task_summary=f"material {SECRET_SENT}"),
        project,
        client=client,
        archive=False,
        intent="answer",
    )
    assert outcome.transport_reason is None, outcome
    assert server.requests[-1]["authorization"] == SECRET_SENT
    raw = points_scope.sink.read_text(encoding="utf-8")
    _assert_absent(raw, SECRET_SENT)
    assert len(calls) == discoveries_before_points, (
        "a legal factory pin paid an extra discovery"
    )


# ---------------------------------------------------------------------------
# 4. the cross-cfg union still contributes its own values
# ---------------------------------------------------------------------------


def test_cross_cfg_union_contributes_while_the_sent_key_stays_the_origin(
    server: _Server,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sending A never exempts a foreign config's B material from capture."""
    calls = _count_resolutions(monkeypatch)
    origin = _cfg(server)
    pin = decision.credential_snapshot(origin)
    assert calls == []
    foreign = _cfg(server, api_key=SECRET_FOREIGN_OLD)

    values = decision.known_credential_values(foreign, snapshot=pin)
    assert SECRET_FOREIGN_OLD in values, "the cross-cfg union was deleted"
    assert SECRET_SENT in values
    redactor = decision.credential_redactor(foreign, snapshot=pin)
    assert redactor is not None and _covers(redactor, SECRET_FOREIGN_OLD)
    assert calls == [], "the cross-cfg union opened a credential discovery"

    scope = _production_scope(tmp_path / "union")
    server.usage = {"probe": SECRET_FOREIGN_OLD, "prompt_tokens": 7}
    server.push({"status": 200})
    result = _client(foreign, scope, credential_snapshot=pin).decide(
        {"note": f"foreign material {SECRET_FOREIGN_OLD}"}, QUESTIONS
    )

    assert result["available"] is True, result
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT]
    raw = scope.sink.read_text(encoding="utf-8")
    _assert_absent(raw, SECRET_SENT, SECRET_FOREIGN_OLD)
    assert "<redacted>" in raw


# ---------------------------------------------------------------------------
# 5. an explicit key without a scope keeps zero discovery; probe unchanged
# ---------------------------------------------------------------------------


def test_explicit_key_without_scope_keeps_zero_discovery_and_probe(
    server: _Server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The pin contract adds no ambient read to scope-less calls or diagnostics."""
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    pin = decision.credential_snapshot(cfg)
    assert calls == []

    result = _client(cfg, None, credential_snapshot=pin).decide(
        {"note": f"material {SECRET_SENT}"}, QUESTIONS
    )
    assert result["available"] is True, result
    assert calls == [], "a scope-less explicit key resolved the timi chain"

    assert db.credential_status(cfg) == {"timi": True}
    assert calls == []

    server.push({"status": 200})
    rows = db.probe_matrix(cfg)
    assert [row["path"] for row in rows] == [db.DECISIONS_PATH], rows
    assert rows[0]["status"] == 200 and rows[0]["verdict"] == "ok", rows
    assert server.requests[-1]["authorization"] == SECRET_SENT
    assert calls == [], "the probe gained an extra credential resolution"


# ---------------------------------------------------------------------------
# 6. a mutable foreign cfg is frozen across the gate and capture faces
# ---------------------------------------------------------------------------


def test_mutable_foreign_cfg_is_frozen_across_gate_and_capture_faces(
    server: _Server,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED (T05o): the cross-cfg union was re-read live on every face.

    The gate face of one unit covers the foreign value B; a mutation of that
    foreign object before the capture face is built must not drop B from the
    unit's set (the capture would store B raw). The union is folded into the
    same frozen set on first read; a value the object gains afterwards belongs
    to the next unit's snapshot, exactly like an env rotation.
    """
    calls = _count_resolutions(monkeypatch)
    origin = _cfg(server)
    pin = decision.credential_snapshot(origin)
    assert calls == []
    foreign = _cfg(server, api_key=SECRET_FOREIGN_OLD)

    # Gate face: the foreign cfg contributes B_OLD to this unit.
    gate = dpts.command_known_secret_redactor(foreign, snapshot=pin)
    gate_values = dpts._command_known_values(foreign, pin)
    assert SECRET_FOREIGN_OLD in gate_values and _covers(gate, SECRET_FOREIGN_OLD)
    # The production gate pays at most the one legacy timi leg (T05m); the
    # freeze below must not add a second discovery.
    assert len(calls) <= 1
    discoveries_after_gate = len(calls)

    # The foreign source object mutates between the two faces.
    foreign.extras["api_key"] = SECRET_FOREIGN_NEW

    # Capture face: same unit, so it must still hold the same frozen set.
    capture = decision.credential_redactor(foreign, snapshot=pin)
    assert capture is not None
    capture_values = decision.known_credential_values(foreign, snapshot=pin)
    assert capture_values == gate_values, (
        "raw set drift: the capture face lost a value the gate face covered"
    )
    assert _covers(capture, SECRET_FOREIGN_OLD), (
        "the capture face dropped the foreign value the gate face had frozen"
    )
    scrubbed = capture.redact(f"upstream failure near {SECRET_FOREIGN_OLD}")
    assert SECRET_FOREIGN_OLD not in scrubbed.text, "the capture stored B_OLD raw"
    assert not _covers(capture, SECRET_FOREIGN_NEW), (
        "the capture face re-read the mutated foreign cfg (next unit's value)"
    )
    assert len(calls) == discoveries_after_gate, "the freeze opened a credential discovery"

    # Next unit: a fresh snapshot covers the rotation of that same object.
    fresh = decision.credential_snapshot(foreign)
    fresh_values = fresh.frozen_known_values()
    assert fresh_values is not None
    assert SECRET_FOREIGN_NEW in fresh_values
    assert SECRET_FOREIGN_OLD not in fresh_values
    fresh_redactor = decision.credential_redactor(foreign, snapshot=fresh)
    assert fresh_redactor is not None and _covers(fresh_redactor, SECRET_FOREIGN_NEW)
    assert len(calls) == discoveries_after_gate, (
        "the next unit opened an extra credential discovery"
    )


# ---------------------------------------------------------------------------
# project/config plumbing for the decision seam (dp3)
# ---------------------------------------------------------------------------


def _enable_all(root: pathlib.Path) -> None:
    path = root / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "points": {
                    point.id: {"tier": point.tier, "enabled": True, "mode": "auto"}
                    for point in dpts.DP_REGISTRY
                },
            }
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    dpts.clear_points_config_cache()


def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    decide = root / ".mw" / "decide.json"
    decide.parent.mkdir(parents=True, exist_ok=True)
    decide.write_text(
        json.dumps(
            {"enabled": True, "model": "jev-latest", "timeout_s": 5.0, "backoff_base_s": 0}
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    _enable_all(root)
    return root


def _dp3_state(**overrides: object) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP3,
        "questions_version": dpts.get_decision_point(DP3).questions_version,
        "key": "k-t05o",
        "phase": "EXECUTE",
        "task_type": "coding",
        "risk": "low",
        "risk_source": "machine",
        "authority_tier": "P2",
        "task_summary": "worker asks which file holds the decide-points table",
        "ambiguity": {"kind": "fact", "question": "which file holds the decide points?"},
        "local_candidates": [{"id": "c1", "label": ".mw/decide-points.json"}],
    }
    state.update(overrides)
    return state
