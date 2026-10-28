"""test_decision_full_value_freeze.py - T05n (mw-decision-dashboard).

T05l/T05m froze the *legacy timi leg* and the *sent* ``Authorization`` on a
``CredentialSnapshot``, but the rest of the known-safe set was still resolved
live on every face: :func:`decision.known_credential_values` re-read
``cfg.api_key`` / ``cfg.extras["api_key"]`` and re-scanned the ambient
``*_API_KEY|_TOKEN|_KEY|_SECRET|_PASSWORD`` environment variables each time a
redactor was built (``workers/dd-bare-scope-known-set/report.md`` R2, review
``workers/dd-review-known-set/report.md`` correction 1/P4).

That is a real divergence window, not a wording issue: the command/client
snapshot is taken *before* the book gate / capture, so a value that was known
when the unit started can be dropped from the ambient environment before the
capture redactor is built. The captured body, the arbitrary response-metadata
keys and values, and the failure output of that same unit could then store the
dropped value raw - while the snapshot, the gate of the first face and the
sending transport had all treated it as part of the unit's set.

The contract pinned here (card T05n):

* ``credential_snapshot()`` explicitly freezes the unit's complete known-safe
  values at creation - ``cfg``/``extras`` (the actual ``Authorization``),
  the ambient env credential text set and the resolved timi key;
* the legacy timi leg keeps its existing one-shot memo timing (a scope/gate
  that needs it pays one discovery; a scope-less explicit key pays none);
* a later redactor/gate of the *same* unit consumes the frozen values and does
  not re-read ``cfg``/``env``: removing or rotating an env value cannot shrink
  what that unit redacts, and the next unit refreshes from the new ambient
  state (never a cross-call cache);
* the actual ``Authorization`` still is the unit's own key; the known set is a
  superset of it, not equal to it;
* ``credential_redactor`` fail-closes on ``discovery_error`` itself (safe
  omit: no text is captured) instead of relying on the senders' call order;
* a foreign duck-typed snapshot (no frozen contract) is refused by the known
  set API with a value-free error, and fails closed in the redactor factories -
  it is never silently shrunk to an empty set and then used to send/capture.

Everything is synthetic and hermetic: the ambient credential environment is
emptied before every test, ``HOME``/``USERPROFILE`` and
``decision_backends._auth_json_path`` are redirected into ``tmp_path`` before
any read, and the only socket is a stdlib ``http.server`` on ``127.0.0.1:0``.
The fixture values are fabricated; a failing assertion quotes them verbatim in
pytest output (that quote *is* the evidence), so these logs are not masked.
"""

from __future__ import annotations

import http.server
import json
import os
import pathlib
import sys
import threading
import types

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_backends as db  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire as wire  # noqa: E402

DP3 = "dp3-worker-clarify"

#: The unit's actual ``Authorization`` (explicit cfg leg).
SECRET_SENT = "t05n-sent-a-0123456789abcdef"
#: Ambient env heuristic value B: known at the snapshot, removed before capture.
SECRET_ENV_OLD = "t05n-env-old-b-0123456789ab"
#: The env rotation C that belongs to the *next* unit only.
SECRET_ENV_NEW = "t05n-env-new-c-0123456789ab"
#: A second cfg value (``cfg.extras["api_key"]`` when ``cfg.api_key`` wins).
SECRET_CFG_OLD = "t05n-cfg-old-b-0123456789ab"
#: The cfg rotation C that belongs to the *next* unit only.
SECRET_CFG_NEW = "t05n-cfg-new-c-0123456789ab"
#: Never matches ``sk-`` / ``Bearer`` / the env heuristics.
PLAIN_MATERIAL = "plain-t05n-material-0123456789"

#: An env name the pre-existing heuristic picks up (``_TOKEN`` suffix).
ENV_NAME = "T05N_PROBE_TOKEN"

QUESTIONS = {"probe": {"type": "noul", "instructions": "Is this probe well formed?"}}
PROBE_ANSWERS = {"probe": {"type": "noul", "noul": 0.91}}
DEFAULT_USAGE = {"prompt_tokens": 7, "total_tokens": 9}


def _credential_env_names() -> tuple[str, ...]:
    names = {name for name in os.environ if name.upper().endswith(decision._CRED_ENV_SUFFIXES)}
    names.add(ENV_NAME)
    names.add("TIMI_API_KEY")
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
            # Echo the Authorization value *and* the request body back, and put
            # a caller-shaped metadata key/value pair into ``usage``: every one
            # of those surfaces is captured text.
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
    thread = threading.Thread(target=instance.serve_forever, daemon=True, name="t05n-http")
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
    """No ambient credential, no real ``~`` path, and no discovery before the spies."""
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
    # The redirected chain must point into tmp_path before any production read.
    assert db._auth_json_path() == auth
    dpts.clear_points_config_cache()
    yield auth
    dpts.clear_points_config_cache()


def _write_auth(path: pathlib.Path, key: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"timi": {"key": key}}), encoding="utf-8", newline="\n")


def _count_resolutions(
    monkeypatch: pytest.MonkeyPatch, *, error: Exception | None = None
) -> list[str | None]:
    """Record the unit's own ambient discoveries (never a real credential read)."""
    original = db.resolve_timi_api_key
    calls: list[str | None] = []

    def spy(env: dict | None = None, auth_path: pathlib.Path | None = None):
        if env is None and auth_path is None:
            redirected = db._auth_json_path()
            assert "t05n" in str(redirected.parent) or str(redirected).startswith(
                str(pathlib.Path(os.environ["HOME"]))
            ), f"the discovery would read a real auth path: {redirected}"
            if error is not None:
                raise error
            value = original(env, auth_path)
            calls.append(value)
            return value
        return original(env, auth_path)

    monkeypatch.setattr(db, "resolve_timi_api_key", spy)
    return calls


# -- config / scope plumbing -----------------------------------------------


def _cfg(server: _Server) -> decision.DecisionConfig:
    return decision.DecisionConfig(
        enabled=True,
        extras={"base_url": server.base_url, "api_key": SECRET_SENT},
        timeout_s=5.0,
        max_retries=2,
        backoff_base_s=0.0,
    )


def _production_scope(root: pathlib.Path) -> wire.WireScope:
    """A production scope without a redactor: the client must inject one."""
    return wire.WireScope(
        sink=root / "wire" / "wire.jsonl",
        project_id="proj-t05n",
        scope_kind="production",
        origin="t05n",
        decision_id="dec-t05n",
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


def _attempt_texts(rows: list[dict], side: str) -> list[str]:
    texts: list[str] = []
    for row in _rows_of(rows, "attempt-start" if side == "request" else "attempt-end"):
        capture = row.get(side) or {}
        if capture.get("text") is not None:
            texts.append(str(capture["text"]))
    return texts


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
# 1. the snapshot freezes the complete env text set of its unit
# ---------------------------------------------------------------------------


def test_env_value_frozen_on_the_snapshot_still_covers_after_env_change(
    server: _Server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED (T05n): the later redactor re-scanned env and lost the removed B.

    B is ambient when the unit's snapshot is taken, then removed and replaced
    by C before the redactor is built. The unit's known set must not shrink:
    B stays covered, C belongs to the next unit only.
    """
    monkeypatch.setenv(ENV_NAME, SECRET_ENV_OLD)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)

    snapshot = decision.credential_snapshot(cfg)
    assert snapshot.api_key == SECRET_SENT and snapshot.source == "cfg-extras"
    assert calls == [], "the explicit cfg leg must not read the timi chain"

    # The ambient value is gone before the capture redactor of this same unit.
    monkeypatch.setenv(ENV_NAME, SECRET_ENV_NEW)

    redactor = decision.credential_redactor(cfg, snapshot=snapshot)
    assert redactor is not None
    assert _covers(redactor, SECRET_ENV_OLD), "the frozen env value was lost"
    assert _covers(redactor, SECRET_SENT), "the unit's own Authorization was lost"
    assert not _covers(redactor, SECRET_ENV_NEW), "the redactor re-read the live env"
    assert calls == [], "building the redactor opened an auth discovery"
    frozen = getattr(snapshot, "frozen_known_values", None)
    assert callable(frozen), "the snapshot must expose the explicitly frozen known set"
    assert SECRET_ENV_OLD in frozen(), "the ambient env value was not frozen"

    # The next unit resolves afresh: it covers C and no longer claims B.
    fresh = decision.credential_snapshot(cfg)
    fresh_frozen = fresh.frozen_known_values()
    assert SECRET_ENV_NEW in fresh_frozen and SECRET_ENV_OLD not in fresh_frozen
    fresh_redactor = decision.credential_redactor(cfg, snapshot=fresh)
    assert fresh_redactor is not None
    assert _covers(fresh_redactor, SECRET_ENV_NEW)
    assert not _covers(fresh_redactor, SECRET_ENV_OLD)


# ---------------------------------------------------------------------------
# 2. the snapshot freezes cfg/extras the same way
# ---------------------------------------------------------------------------


def test_cfg_extras_value_frozen_on_the_snapshot_still_covers_after_mutation(
    server: _Server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED: ``cfg.extras["api_key"]`` was re-read live and B was dropped.

    ``cfg.api_key`` (A) is the actual ``Authorization``; the extras value B is
    also part of this unit's known set. Mutating extras to C before capture must
    not un-know B; the next unit is the one that covers C.
    """
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    cfg.api_key = SECRET_SENT
    cfg.extras["api_key"] = SECRET_CFG_OLD

    snapshot = decision.credential_snapshot(cfg)
    assert snapshot.api_key == SECRET_SENT and snapshot.source == "cfg"
    assert calls == []

    cfg.extras["api_key"] = SECRET_CFG_NEW

    redactor = decision.credential_redactor(cfg, snapshot=snapshot)
    assert redactor is not None
    assert _covers(redactor, SECRET_CFG_OLD), "the frozen cfg value was lost"
    assert _covers(redactor, SECRET_SENT)
    assert not _covers(redactor, SECRET_CFG_NEW), "the redactor re-read the live cfg"
    assert SECRET_CFG_OLD in snapshot.frozen_known_values()
    assert SECRET_CFG_NEW not in snapshot.frozen_known_values()

    fresh = decision.credential_snapshot(cfg)
    fresh_redactor = decision.credential_redactor(cfg, snapshot=fresh)
    assert fresh_redactor is not None
    assert _covers(fresh_redactor, SECRET_CFG_NEW)
    assert not _covers(fresh_redactor, SECRET_CFG_OLD)


# ---------------------------------------------------------------------------
# 3. body + arbitrary metadata keys/values of the unit stay clean
# ---------------------------------------------------------------------------


def test_capture_text_and_metadata_do_not_store_a_frozen_env_value(
    server: _Server,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED: the response body and ``usage`` metadata stored the removed B raw."""
    monkeypatch.setenv(ENV_NAME, SECRET_ENV_OLD)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    snapshot = decision.credential_snapshot(cfg)
    assert calls == []

    # The value is no longer ambient when the capture redactor is built.
    monkeypatch.setenv(ENV_NAME, SECRET_ENV_NEW)
    server.usage = {f"trace-{SECRET_ENV_OLD}": SECRET_ENV_OLD, "prompt_tokens": 7}
    scope = _production_scope(tmp_path / "capture")
    server.push({"status": 200})

    result = _client(cfg, scope, credential_snapshot=snapshot).decide(
        {"note": f"carried {SECRET_ENV_OLD} and {PLAIN_MATERIAL}"}, QUESTIONS
    )

    assert result["available"] is True, result
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT]

    raw = scope.sink.read_bytes()
    _assert_absent(raw.decode("utf-8", "replace"), SECRET_SENT, SECRET_ENV_OLD)
    assert b"<redacted>" in raw

    rows = _rows(scope.sink)
    for text in _attempt_texts(rows, "request") + _attempt_texts(rows, "response"):
        _assert_absent(text, SECRET_SENT, SECRET_ENV_OLD)
    assert PLAIN_MATERIAL in "".join(_attempt_texts(rows, "request")), (
        "the request was not captured at all; the redaction above proves nothing"
    )
    usage = _rows_of(rows, "attempt-end")[0].get("usage")
    assert isinstance(usage, dict), usage
    serialized = json.dumps(usage)
    _assert_absent(serialized, SECRET_SENT, SECRET_ENV_OLD)
    assert "<redacted>" in serialized, "the metadata key/value pair was not redacted"


# ---------------------------------------------------------------------------
# 4. failure output of the unit stays clean
# ---------------------------------------------------------------------------


def test_failure_output_does_not_store_a_frozen_cfg_value(
    server: _Server,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED: a 500 body carrying the mutated-away cfg value B was persisted raw."""
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    cfg.api_key = SECRET_SENT
    cfg.extras["api_key"] = SECRET_CFG_OLD
    snapshot = decision.credential_snapshot(cfg)
    assert calls == []
    cfg.extras["api_key"] = SECRET_CFG_NEW

    scope = _production_scope(tmp_path / "failure")
    server.push({"status": 500, "body": f"upstream failed near {SECRET_CFG_OLD}"})
    server.push({"status": 200})

    result = _client(cfg, scope, credential_snapshot=snapshot).decide(
        {"note": f"material {SECRET_CFG_OLD}"}, QUESTIONS
    )

    assert result["available"] is True and result["attempts"] == 2, result
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT] * 2
    raw = scope.sink.read_bytes().decode("utf-8", "replace")
    _assert_absent(raw, SECRET_SENT, SECRET_CFG_OLD)
    assert "<redacted>" in raw
    ends = _rows_of(_rows(scope.sink), "attempt-end")
    assert [row.get("http_status") for row in ends] == [500, 200], ends
    for text in _attempt_texts(ends, "response"):
        _assert_absent(text, SECRET_SENT, SECRET_CFG_OLD)


# ---------------------------------------------------------------------------
# 5. the next unit covers the rotation; the old unit keeps its own set
# ---------------------------------------------------------------------------


def test_the_next_unit_covers_the_rotated_value_and_the_old_one_keeps_its_set(
    server: _Server,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per-unit refresh, never a cross-call cache; the sent key never changes."""
    monkeypatch.setenv(ENV_NAME, SECRET_ENV_OLD)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    first = decision.credential_snapshot(cfg)
    monkeypatch.setenv(ENV_NAME, SECRET_ENV_NEW)
    second = decision.credential_snapshot(cfg)
    assert calls == []

    first_redactor = decision.credential_redactor(cfg, snapshot=first)
    second_redactor = decision.credential_redactor(cfg, snapshot=second)
    assert first_redactor is not None and second_redactor is not None
    # The old unit's set did not change when the ambient value rotated ...
    assert _covers(first_redactor, SECRET_ENV_OLD)
    assert not _covers(first_redactor, SECRET_ENV_NEW)
    # ... and the new unit covers the rotation, not the removed value.
    assert _covers(second_redactor, SECRET_ENV_NEW)
    assert not _covers(second_redactor, SECRET_ENV_OLD)

    for index, (snapshot, value) in enumerate(
        ((first, SECRET_ENV_OLD), (second, SECRET_ENV_NEW)),
        start=1,
    ):
        scope = _production_scope(tmp_path / f"unit-{index}")
        server.push({"status": 200})
        result = _client(cfg, scope, credential_snapshot=snapshot).decide(
            {"note": f"unit {index} carried {value}"}, QUESTIONS
        )
        assert result["available"] is True, result
        # The actual Authorization stays this unit's own key - the known set is
        # a superset of it, never an equality claim about the sent value.
        assert [request["authorization"] for request in server.requests[-1:]] == [SECRET_SENT]
        raw = scope.sink.read_bytes().decode("utf-8", "replace")
        _assert_absent(raw, SECRET_SENT, value)
        assert "<redacted>" in raw


# ---------------------------------------------------------------------------
# 6. the redactor factory itself fails closed on a discovery error
# ---------------------------------------------------------------------------


def test_credential_redactor_fails_closed_on_a_discovery_error_snapshot(
    server: _Server,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED: the capture redactor ignored ``discovery_error`` and kept capturing.

    Safety must not depend on the two senders checking the flag first: the
    factory that builds the capture filter has to fail closed itself.
    """
    _count_resolutions(monkeypatch, error=RuntimeError("synthetic discovery failure"))
    cfg = _cfg(server)
    snapshot = decision.credential_snapshot(cfg)
    assert dpts.known_secret_superset(snapshot) == ()
    assert snapshot.discovery_error, "the snapshot did not record the discovery failure"

    assert decision.credential_redactor(cfg, snapshot=snapshot) is None, (
        "an incomplete known set still produced a capture redactor"
    )
    gate = decision.known_secret_redactor(cfg, snapshot=snapshot)
    assert gate.fail_closed is True
    for text in (PLAIN_MATERIAL, f"material {SECRET_SENT}"):
        assert gate.redact(text).hits >= 1


# ---------------------------------------------------------------------------
# 7. a foreign duck snapshot is refused, never shrunk to an empty set
# ---------------------------------------------------------------------------


def _duck_snapshot() -> object:
    return types.SimpleNamespace(api_key=SECRET_SENT, source="cfg", discovery_error=None)


def test_a_foreign_duck_snapshot_is_refused_with_a_value_free_error(
    server: _Server,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED: a duck snapshot was silently treated as "no known set" and used.

    The known-set authority requires the frozen ``CredentialSnapshot`` contract;
    a duck object cannot prove anything and must be refused (API error) or fail
    closed (redactor factories) - never shrunk to ``()`` and then sent.
    """
    _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    duck = _duck_snapshot()

    # The known-set authority: a type-safe error, naming no value.
    with pytest.raises(TypeError) as excinfo:
        decision.known_credential_values(cfg, snapshot=duck)
    message = str(excinfo.value)
    assert "snapshot" in message.lower()
    _assert_absent(message, SECRET_SENT, SECRET_ENV_OLD, SECRET_ENV_NEW)

    # The capture factory: safe omit (no text can be captured).
    assert decision.credential_redactor(cfg, snapshot=duck) is None
    # The gate factory: fail closed (refuse every text).
    gate = decision.known_secret_redactor(cfg, snapshot=duck)
    assert gate.fail_closed is True
    assert gate.redact(PLAIN_MATERIAL).hits >= 1

    # The decision seam: type-safe refusal, zero POST, zero material of record.
    with pytest.raises(decision.DecisionInputError) as seam:
        dpts.known_secret_superset(duck)
    _assert_absent(str(seam.value), SECRET_SENT, SECRET_ENV_OLD, SECRET_ENV_NEW)

    project = _project(tmp_path)
    scope = _production_scope(tmp_path / "duck")
    client = decision.DecisionClient(
        cfg, db.TimiDecisionsBackend(), wire_scope=scope, credential_snapshot=duck
    )
    server.push({"status": 200})
    with pytest.raises(decision.DecisionInputError) as pinned:
        dpts.decide_for(
            DP3,
            _dp3_state(task_summary=f"material {SECRET_SENT}"),
            project,
            client=client,
            archive=False,
            intent="answer",
        )
    _assert_absent(str(pinned.value), SECRET_SENT, SECRET_ENV_OLD, SECRET_ENV_NEW)
    assert server.requests == [], "a foreign snapshot still reached the transport"
    rows = _rows(scope.sink)
    assert _rows_of(rows, "attempt-start") == [] and _rows_of(rows, "book-snapshot") == []


# ---------------------------------------------------------------------------
# 8. the preserved contracts of the seam
# ---------------------------------------------------------------------------


def test_caller_owned_redactor_and_contextvar_contract_are_unchanged(
    server: _Server,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A caller redactor is verified, never replaced; the binding always resets."""
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    snapshot = decision.credential_snapshot(cfg)
    caller_redactor = decision.credential_redactor(cfg, snapshot=snapshot)
    assert caller_redactor is not None and calls == []
    scope = wire.WireScope(
        sink=tmp_path / "caller" / "wire.jsonl",
        project_id="proj-t05n",
        scope_kind="test",
        origin="t05n",
        decision_id="dec-t05n",
        dp=DP3,
        submission_id="sub-t05n",
        evidence_path=tmp_path / "caller" / "evidence.jsonl",
        redact=caller_redactor,
        warn=lambda message: None,
    )
    client = decision.DecisionClient(
        cfg, db.TimiDecisionsBackend(), wire_scope=scope, credential_snapshot=snapshot
    )
    server.push({"status": 200})

    result = client.decide({"note": f"material {SECRET_SENT}"}, QUESTIONS)

    assert result["available"] is True, result
    assert scope.redact is caller_redactor, "the caller-owned redactor was replaced"
    assert decision.current_credential_snapshot() is None, "the binding leaked"
    raw = scope.sink.read_text(encoding="utf-8")
    _assert_absent(raw, SECRET_SENT, SECRET_ENV_OLD)


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
        "key": "k-t05n",
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
