"""test_decision_known_set_snapshot.py - T05l (mw-decision-dashboard).

T05i froze the *sent* credential on a ``CredentialSnapshot``; T05j wired one
snapshot per command/decision into the book gate, the capture redactor and the
transport. Both left the *known set* itself split: ``decision_points`` resolved
the legacy timi leg (`known_secret_superset`) live on every face, so one
decision could hold gate={A,B} and capture={A,C} while the transport sent A
(T05j review R1/R2).

The contract pinned here (card T05l):

* a snapshot freezes the **complete** known-safe superset of its unit - the
  explicit ``cfg``/extras value(s), the actual ``Authorization``, the legacy
  timi leg (env ``TIMI_API_KEY`` -> ``~/.pi/agent/auth.json``) and the env
  heuristics - exactly once; a second caller of the same snapshot reuses that
  tuple instead of resolving a later value;
* every surface of the unit (book gate, decision gates, the production capture
  redactor *including* the client's own injection, the caller-owned scope
  verification) consumes that one tuple, so a credential rotated mid-call
  cannot make two faces disagree;
* the next logical call / command resolves a fresh superset (no cross-call
  cache) and then covers the rotated value, while the sent ``Authorization``
  stays the pinned one;
* an explicit ``cfg`` key A plus a legacy timi value B is covered **both**: the
  sent value being A never exempts captured B material;
* a caller-owned capture redactor must cover the whole frozen known set, not
  just the sent value; if it does not, the call is refused before the transport
  (zero send) and stores no book-snapshot (zero material of record);
* a discovery that *raises* leaves the known set incomplete: the decision and
  the client fail closed (zero send, zero snapshot) and the safe error text
  echoes the failure kind, never the exception message or a value;
* a callback that raises inside discovery does not turn "I cannot prove this
  text safe" into a silent "send anyway", and a capture/sink failure is still a
  fact only - it never changes a decision result (that existing semantics is
  unchanged by this card).

Everything is synthetic and hermetic: the credential lives in a tmp
``auth.json`` (``decision_backends._auth_json_path`` is patched before any test
body runs), the credential-shaped env set is removed, and the only socket is a
stdlib ``http.server`` on ``127.0.0.1:0``. The server echoes the request body it
received, so a known value that reached the wire is measured in the response
text the capture would persist.
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

#: The explicit ``cfg.extras["api_key"]`` value: also the sent Authorization.
SECRET_SENT = "timi-known-set-sent-a-0123456789"
#: The legacy timi leg (``auth.json`` timi.key) while A is sent - the second key.
SECRET_LEGACY = "timi-known-set-legacy-b-01234567"
#: Rotated into ``auth.json`` *after* the freeze (must not join this unit).
SECRET_ROTATED = "timi-known-set-rotated-c-0123456"
#: The second config's explicit key (cross-cfg pin availability check).
SECRET_OTHER_CFG = "timi-known-set-other-d-012345678"
#: Plain text that no layer (Bearer / ``sk-`` / env) can mistake for a secret.
PLAIN_MATERIAL = "plain-known-set-material-0123456789"

#: Every credential-shaped suffix the discovery rule picks up, so the known set
#: cannot depend on the developer's shell.
CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
    "TIMI_BASE_URL",
)

#: Whole-wire answer map for dp3 as the timi backend decodes it.
DP3_ANSWERS = {
    "answer_kind": {"type": "choice", "choice": "fact", "confidence": 0.9},
    "answerable": {"type": "noul", "noul": 0.9},
    "candidate": {"type": "choice", "choice": "c1", "confidence": 0.9},
}

#: A bare question set for the direct-client faces (no dp registry involved).
QUESTIONS = {"probe": {"type": "noul", "instructions": "Is this probe well formed?"}}
PROBE_ANSWERS = {"probe": {"type": "noul", "noul": 0.91}}


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
                "headers": {name: value for name, value in self.headers.items()},
                "body": body,
                "authorization": authorization,
            }
        )
        step = server.next_step()
        payload = step.get("body")
        if payload is None:
            # Echo both boundaries back: the received Authorization *and* the
            # request body, so the capture set is measured on real wire text.
            payload = json.dumps(
                {
                    "model": "jev-latest",
                    "answers": server.answers,
                    "note": f"used {authorization} body {body.decode('utf-8', 'replace')}",
                },
                ensure_ascii=False,
            ).encode("utf-8")
        elif not isinstance(payload, bytes):
            payload = str(payload).encode("utf-8")
        self.send_response(int(step.get("status", 200)))
        self.send_header("Content-Type", "application/json")
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
        self.answers: dict = DP3_ANSWERS

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
    thread = threading.Thread(target=instance.serve_forever, daemon=True, name="t05l-http")
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
    dpts.clear_points_config_cache()
    yield path
    dpts.clear_points_config_cache()


def _write_auth(path: pathlib.Path, key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"timi": {"key": key}}), encoding="utf-8", newline="\n")


def _count_resolutions(
    monkeypatch: pytest.MonkeyPatch, *, error: Exception | None = None
) -> list[str | None]:
    """Count ambient discoveries (the seam's own resolution, not a test redactor)."""
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


# -- project / config / book plumbing ---------------------------------------


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


def _write_decide(root: pathlib.Path, **fields) -> None:
    path = root / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"enabled": True, **fields}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    _write_decide(root, model="jev-latest", timeout_s=5.0, max_retries=2, backoff_base_s=0)
    _enable_all(root)
    return root


def _dp3_state(**overrides) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP3,
        "questions_version": dpts.get_decision_point(DP3).questions_version,
        "key": "k-t05l",
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


def _cfg(server: _Server, *, api_key: str | None = None) -> decision.DecisionConfig:
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
        project_id="proj-t05l",
        scope_kind="production",
        origin="t05l",
        decision_id="dec-t05l",
        dp=DP3,
        evidence_path=root / "triage.jsonl",
        warn=lambda message: None,
    )


def _observation_scope(root: pathlib.Path, *, redactor: object = None) -> wire.WireScope:
    return wire.test_scope(
        root,
        project_id=wire.project_id_for(root),
        submission_id="sub-t05l",
        redact=redactor,
        evidence_path=root / "evidence.jsonl",
        warn=lambda line: None,
    )


def _rows(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _tree_text(root: pathlib.Path) -> str:
    chunks: list[str] = []
    if not root.exists():
        return ""
    for item in sorted(root.rglob("*")):
        if item.is_file():
            chunks.append(item.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _assert_values_absent(root: pathlib.Path, *values: str) -> None:
    text = _tree_text(root)
    for value in values:
        assert value not in text, f"credential material under {root}"


# ---------------------------------------------------------------------------
# 1. one snapshot freezes the complete known set; a later rotation waits
# ---------------------------------------------------------------------------


def test_snapshot_freezes_the_legacy_timi_leg_and_refreshes_per_call(
    auth_json: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """RED (T05j R2): every face resolved the legacy leg itself.

    The snapshot must carry the legacy leg it discovered for its own unit; a
    value rotated in afterwards belongs to the *next* snapshot, not to this one.
    """
    _write_auth(auth_json, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(_NoServer(), api_key=SECRET_SENT)  # type: ignore[arg-type]

    snapshot = decision.credential_snapshot(cfg)
    assert snapshot.api_key == SECRET_SENT and snapshot.source == "cfg-extras"
    assert calls == [], "the explicit cfg leg must not read the timi chain"

    first = dpts.known_secret_superset(snapshot)
    assert first == (SECRET_LEGACY,)
    assert calls == [SECRET_LEGACY], "the legacy leg is discovered exactly once"

    # A rotation after the freeze must not rewrite this unit's known set.
    _write_auth(auth_json, SECRET_ROTATED)
    assert dpts.known_secret_superset(snapshot) == (SECRET_LEGACY,)
    assert dpts.known_secret_superset(snapshot) == (SECRET_LEGACY,)
    assert calls == [SECRET_LEGACY], "the snapshot re-resolved its own known set"

    # The next unit resolves afresh (no cross-call cache).
    fresh = decision.credential_snapshot(cfg)
    assert dpts.known_secret_superset(fresh) == (SECRET_ROTATED,)
    assert calls == [SECRET_LEGACY, SECRET_ROTATED]


class _NoServer:
    """Placeholder for helpers that only need ``base_url`` placeholder text."""

    base_url = "http://127.0.0.1:1"


# ---------------------------------------------------------------------------
# 2. the wire self-injection consumes the same frozen known set
# ---------------------------------------------------------------------------


def test_wire_self_injection_covers_the_frozen_legacy_leg(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED (T05j R1): the client-built production redactor lacked the legacy leg.

    The CLI order is reproduced: the command takes the snapshot, the book gate
    freezes the known set, then the client injects the capture redactor. The
    value that is *sent* is A (explicit cfg), while B (legacy timi) travels in
    the state - sending A never exempts B from redaction.
    """
    _write_auth(auth_json, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server, api_key=SECRET_SENT)
    snapshot = decision.credential_snapshot(cfg)

    gate = dpts.command_known_secret_redactor(cfg, snapshot=snapshot)
    assert gate.redact(f"material {SECRET_LEGACY}").hits >= 1
    assert gate.redact(f"material {SECRET_SENT}").hits >= 1
    assert calls == [SECRET_LEGACY]

    # Rotation after the gate: this unit keeps {A, B}.
    _write_auth(auth_json, SECRET_ROTATED)

    server.answers = PROBE_ANSWERS
    scope = _production_scope(tmp_path / "run")
    client = decision.DecisionClient(
        cfg,
        db.TimiDecisionsBackend(),
        wire_scope=scope,
        credential_snapshot=snapshot,
    )
    server.push({"status": 200})

    result = client.decide({"note": f"carried {SECRET_LEGACY}"}, QUESTIONS)

    assert result["available"] is True, result
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT]
    assert calls == [SECRET_LEGACY], "the wire injection resolved the legacy leg again"
    raw = scope.sink.read_bytes()
    assert SECRET_SENT.encode() not in raw, "the sent Authorization was captured raw"
    assert SECRET_LEGACY.encode() not in raw, "the frozen legacy leg was captured raw"
    assert SECRET_ROTATED.encode() not in raw
    assert b"<redacted>" in raw


# ---------------------------------------------------------------------------
# 3. one decision: gate, capture and transport share the frozen set
# ---------------------------------------------------------------------------


def test_points_decision_freezes_one_known_set_for_gate_capture_and_client(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Explicit cfg A + legacy timi B on a real loopback decision.

    The whole decision must discover the legacy leg once, redact A *and* B out
    of the captured request/response text, and send A.
    """
    _write_auth(auth_json, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    project = _project(tmp_path)
    cfg = _cfg(server, api_key=SECRET_SENT)
    server.push({"status": 200})

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(task_summary=f"material {SECRET_LEGACY} with {SECRET_SENT}"),
        project,
        config=cfg,
        archive=False,
        intent="answer",
    )

    assert outcome.response is not None and outcome.response["available"] is True, outcome.detail
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT]
    assert calls == [SECRET_LEGACY], f"the decision discovered the legacy leg {len(calls)}x"
    sink = wire.production_wire_sink(project)
    raw = sink.read_bytes()
    assert SECRET_SENT.encode() not in raw
    assert SECRET_LEGACY.encode() not in raw, "the frozen legacy leg was captured raw"
    assert b"<redacted>" in raw
    rows = _rows(sink)
    assert [row for row in rows if row.get("kind") == "book-snapshot"], rows
    _assert_values_absent(project, SECRET_SENT, SECRET_LEGACY)


# ---------------------------------------------------------------------------
# 4./5. caller-owned scope: the whole known set must be covered
# ---------------------------------------------------------------------------


def test_caller_scope_must_cover_the_frozen_known_set_not_only_the_sent_value(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
) -> None:
    """RED (T05j R2): coverage was verified against ``snapshot.api_key`` only.

    The caller's ledger covers A (the value that is sent) but not B (the frozen
    legacy leg). Sending A must not exempt captured B material: refuse before
    the transport, keep the caller's redactor untouched and store no snapshot.
    """
    _write_auth(auth_json, SECRET_LEGACY)
    project = _project(tmp_path)
    cfg = _cfg(server, api_key=SECRET_SENT)
    caller_redactor = decision.known_secret_redactor(
        cfg, extra_secrets=(SECRET_SENT,), env={}, auth_path=tmp_path / "no-auth.json"
    )
    root = tmp_path / "test-run"
    scope = _observation_scope(root, redactor=caller_redactor)
    client = decision.DecisionClient(cfg, db.TimiDecisionsBackend(), wire_scope=scope)

    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(task_summary=f"material {SECRET_LEGACY}"),
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=dpts.Observation(scope=scope, submission_id="sub-t05l"),
        )

    message = str(excinfo.value)
    assert "unprovable capture" in message
    assert SECRET_SENT not in message and SECRET_LEGACY not in message
    assert server.requests == [], "an unprovable capture still reached the transport"
    rows = _rows(root / "evidence.jsonl")
    assert [row for row in rows if row.get("kind") in ("attempt-start", "book-snapshot")] == [], (
        "an unprovable capture stored material of record"
    )
    assert scope.redact is caller_redactor, "the caller-owned redactor was replaced"
    assert client._pinned_credential_snapshot is None
    _assert_values_absent(root, SECRET_SENT, SECRET_LEGACY)


def test_a_caller_scope_covering_the_whole_frozen_set_is_kept(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A complete caller redactor is never replaced and the pin is reset."""
    _write_auth(auth_json, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    project = _project(tmp_path)
    cfg = _cfg(server, api_key=SECRET_SENT)
    snapshot = decision.credential_snapshot(cfg)
    # A wire-compatible caller redactor (the scope contract needs
    # ``scrub_tail_prefix``) that covers the *whole* frozen known set.
    caller_redactor = decision.credential_redactor(
        cfg, extra_secrets=dpts.known_secret_superset(snapshot), snapshot=snapshot
    )
    assert caller_redactor is not None
    root = tmp_path / "test-run"
    scope = _observation_scope(root, redactor=caller_redactor)
    client = decision.DecisionClient(
        cfg, db.TimiDecisionsBackend(), wire_scope=scope, credential_snapshot=snapshot
    )
    server.push({"status": 200})

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(task_summary=f"material {SECRET_LEGACY}"),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, submission_id="sub-t05l"),
    )

    assert outcome.response is not None and outcome.response["available"] is True, outcome.detail
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT]
    assert calls == [SECRET_LEGACY], "the pinned snapshot discovered the legacy leg again"
    assert scope.redact is caller_redactor, "the caller-owned redactor was replaced"
    assert client._pinned_credential_snapshot is snapshot, "a pinned client was rewritten"
    captured = wire.test_wire_sink(root).read_text(encoding="utf-8")
    assert SECRET_SENT not in captured and SECRET_LEGACY not in captured
    assert "<redacted>" in captured


# ---------------------------------------------------------------------------
# 6. a discovery that raises fails closed (zero send, zero snapshot)
# ---------------------------------------------------------------------------


def test_discovery_failure_fails_closed_with_zero_send_and_zero_snapshot(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED: the raising legacy leg was swallowed and the material was sent.

    An incomplete known set cannot prove the captured text safe, so the decision
    refuses. The safe error names the failure kind, never the message or a value.
    """
    _write_auth(auth_json, SECRET_LEGACY)
    _count_resolutions(monkeypatch, error=RuntimeError(f"boom {SECRET_LEGACY}"))
    project = _project(tmp_path)
    cfg = _cfg(server, api_key=SECRET_SENT)
    server.push({"status": 200})

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(task_summary=f"material {SECRET_LEGACY}"),
        project,
        config=cfg,
        archive=False,
        intent="answer",
    )

    assert server.requests == [], "an incomplete known set still reached the transport"
    assert outcome.status == "escalated" and outcome.escalated_reason == "unavailable"
    detail = f"{outcome.detail} {outcome.response}"
    assert "discovery" in outcome.detail.lower()
    assert "RuntimeError" in outcome.detail, "the failure kind must stay visible"
    assert "boom" not in detail, "the exception message is echoed"
    assert SECRET_SENT not in detail and SECRET_LEGACY not in detail
    sink = wire.production_wire_sink(project)
    rows = _rows(sink)
    assert [row for row in rows if row.get("kind") == "book-snapshot"] == [], (
        "material of record was stored while the known set was unknown"
    )
    assert [row for row in rows if row.get("kind") == "attempt-start"] == []
    _assert_values_absent(project, SECRET_SENT, SECRET_LEGACY)


def test_client_refuses_an_incomplete_snapshot_pinned_by_a_gate(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The direct client face fails closed on the same frozen snapshot."""
    _write_auth(auth_json, SECRET_LEGACY)
    _count_resolutions(monkeypatch, error=OSError(f"unreadable {SECRET_LEGACY}"))
    cfg = _cfg(server, api_key=SECRET_SENT)
    snapshot = decision.credential_snapshot(cfg)
    assert dpts.known_secret_superset(snapshot) == ()
    assert snapshot.discovery_error, "the snapshot did not record the discovery failure"

    server.answers = PROBE_ANSWERS
    scope = _production_scope(tmp_path / "run")
    client = decision.DecisionClient(
        cfg, db.TimiDecisionsBackend(), wire_scope=scope, credential_snapshot=snapshot
    )
    server.push({"status": 200})

    result = client.decide({"note": f"carried {SECRET_LEGACY}"}, QUESTIONS)

    assert result["available"] is False
    assert result["reason"] == decision.REASON_ENTRY_UNAVAILABLE
    assert result["attempts"] == 0
    assert server.requests == []
    raw = scope.sink.read_bytes() if scope.sink.exists() else b""
    assert SECRET_LEGACY.encode() not in raw and SECRET_SENT.encode() not in raw


def test_the_book_gate_redactor_is_fail_closed_when_discovery_raised(
    auth_json: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An incomplete known set turns the known-set gate into "refuse everything".

    No value can be proven absent from the material, so every text is a hit;
    nothing is echoed and nothing crashes.
    """
    _write_auth(auth_json, SECRET_LEGACY)
    _count_resolutions(monkeypatch, error=RuntimeError("synthetic discovery failure"))
    cfg = _cfg(_NoServer(), api_key=SECRET_SENT)  # type: ignore[arg-type]

    redactor = dpts.command_known_secret_redactor(
        cfg, snapshot=decision.credential_snapshot(cfg)
    )

    for text in (PLAIN_MATERIAL, f"material {SECRET_LEGACY}", f"material {SECRET_SENT}"):
        hit = redactor.redact(text)
        assert hit.hits >= 1, "an incomplete known set accepted text as safe"
        assert SECRET_LEGACY not in hit.text and SECRET_SENT not in hit.text


# ---------------------------------------------------------------------------
# 7. cross-cfg pin: availability only, never a mis-send
# ---------------------------------------------------------------------------


def test_a_cross_cfg_pin_sends_the_pinned_value_and_covers_both(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A snapshot pinned from config 1 under config 2 never sends the wrong key.

    The sent Authorization stays the pinned A1 while the known set is the union
    (A1, A2, legacy B): neither face can claim the other value safe.
    """
    _write_auth(auth_json, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    project = _project(tmp_path)
    pin_cfg = _cfg(server, api_key=SECRET_SENT)
    snapshot = decision.credential_snapshot(pin_cfg)
    host_cfg = _cfg(server, api_key=SECRET_OTHER_CFG)
    client = decision.DecisionClient(
        host_cfg,
        db.TimiDecisionsBackend(),
        credential_snapshot=snapshot,
    )
    server.push({"status": 200})

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(task_summary=f"material {SECRET_OTHER_CFG} {SECRET_LEGACY}"),
        project,
        client=client,
        archive=False,
        intent="answer",
    )

    assert outcome.response is not None and outcome.response["available"] is True, outcome.detail
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT]
    assert calls == [SECRET_LEGACY]
    sink = wire.production_wire_sink(project)
    raw = sink.read_bytes()
    for value in (SECRET_SENT, SECRET_OTHER_CFG, SECRET_LEGACY):
        assert value.encode() not in raw, "a known value of the union was captured raw"
    assert b"<redacted>" in raw
