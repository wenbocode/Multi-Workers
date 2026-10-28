"""test_decision_coverage_safety.py - T05q (mw-decision-dashboard).

T05p refused a caller-owned capture filter that missed part of the unit's
frozen known set, but the *coverage judgement* it relied on was ``hits > 0``
(or "the text changed" when no ``hits`` counter exists). That does not prove
the value is gone (``workers/dd-review-redactor-contract/report.md`` F-1), so
these caller-owned filters all passed:

* a filter that reports ``hits`` while leaving the value in the text, or that
  only *prepends* a marker;
* a filter that replaces ``value[:8]`` and leaves the rest ("partial
  replacement"): ``value not in output`` cannot see the tail;
* a filter without any ``hits`` attribute whose output merely differs from its
  input (cosmetic change, value intact);
* a filter that covers values but has no ``scrub_tail_prefix``: coverage
  passed, ``WireScope.capture`` raised ``AttributeError``, the transport
  swallowed it and the call stored *zero* rows while the decision reported a
  complete capture (F-2).

The contract pinned here (card T05q):

* coverage is decided by a boundary probe that embeds the value *twice* between
  markers that cannot occur in the value and accepts only when no fragment of
  the value of ``_MIN_SECRET_LEN`` characters survives - that is the
  complete-value test (the old one), the tail test F-1 asked for, and a count
  test (a single replacement leaves the second copy);
* the filter must also honour the capture boundary contract
  (``scrub_tail_prefix``); a missing or non-conforming one is refused with a
  value-free, actionable detail instead of a silent zero-row capture;
* both entries consume the same judgement: client-only
  (``DecisionClient._caller_redactor_gap``) and the points seam
  (``decision_points._caller_scope_coverage_issue``), the latter delegating to
  ``decision`` so the two cannot drift;
* a legitimate complete caller filter - including one the caller *wrapped*, so
  it is not one of our classes - is never replaced and keeps redacting full
  values, long tails left by a capture cut, arbitrary metadata key/value pairs
  and 500 failure free text, on both entries.

What this does NOT claim: the probe is behaviour on synthetic text, so a
stateful or actively adversarial filter can still differ on the captured text
(report "残留与未验证"). The honest-bug classes above are the ones closed here;
the hard guarantee would need the wire boundary itself (``decision_wire``),
which is outside this card's write face.

Everything is synthetic and hermetic: every credential-shaped env name is
removed before each test, ``HOME``/``USERPROFILE`` and
``decision_backends._auth_json_path`` point into ``tmp_path`` before any read,
and the only socket is a stdlib ``http.server`` bound to ``127.0.0.1:0``. The
fixture values are fabricated; a failing assertion quotes them verbatim in
pytest's output (that quote *is* the RED evidence). No real credential, model,
service or browser is touched.
"""

from __future__ import annotations

import dataclasses
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
SECRET_SENT = "zqsent-9182736450"
#: The legacy timi leg (``auth.json`` ``timi.key``); never sent here.
SECRET_LEGACY = "zqlegacy-5647382910"
#: Ambient env heuristic value (``_TOKEN`` suffix); removed by the fixture.
SECRET_ENV = "zqenv-8273645910"
ENV_NAME = "T05Q_PROBE_TOKEN"
#: Never matches ``sk-`` / ``Bearer`` / the env heuristics, and shares no
#: 4-character window with the fixture secrets (a fragment check must be stable).
PLAIN_MATERIAL = "plain-material-abcdef"

#: The fragment length the module itself treats as material (``_MIN_SECRET_LEN``).
FRAGMENT = decision._MIN_SECRET_LEN

#: The four "weak judgement" leak classes plus the missing-boundary-scrub one.
LEAK_MODES = (
    "hits-lie-keeps-value",
    "prefix-only",
    "partial-tail",
    "no-hits-trivial-change",
)
BAD_MODES = (*LEAK_MODES, "missing-scrub")

QUESTIONS = {"probe": {"type": "noul", "instructions": "Is this probe well formed?"}}
PROBE_ANSWERS = {"probe": {"type": "noul", "noul": 0.91}}
DEFAULT_USAGE = {"prompt_tokens": 7, "total_tokens": 9}
DP3_ANSWERS = {
    "answer_kind": {"type": "choice", "choice": "fact", "confidence": 0.9},
    "answerable": {"type": "noul", "noul": 0.9},
    "candidate": {"type": "choice", "choice": "c1", "confidence": 0.9},
}

CRED_ENV_VARS = ("TIMI_API_KEY", "TIMI_BASE_URL")


def _credential_env_names() -> tuple[str, ...]:
    names = {name for name in os.environ if name.upper().endswith(decision._CRED_ENV_SUFFIXES)}
    names.update((ENV_NAME, *CRED_ENV_VARS))
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
    thread = threading.Thread(target=instance.serve_forever, daemon=True, name="t05q-http")
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
    dpts.clear_points_config_cache()
    assert db._auth_json_path() == auth
    yield auth
    dpts.clear_points_config_cache()


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


# -- caller-owned capture filters (the shapes under test) ------------------


@dataclasses.dataclass(frozen=True)
class _TextOnly:
    """A redaction result without a ``hits`` counter (the weak-judgement path)."""

    text: str


class _CallerFilter:
    """A caller-owned capture filter whose failure mode is selectable."""

    def __init__(self, mode: str, value: str) -> None:
        self.mode = mode
        self.value = value
        self.inner = wire.SubstringRedactor([value])

    def redact(self, text: str):
        if self.mode == "hits-lie-keeps-value":
            return wire.Redaction(text=text, hits=1)
        if self.mode == "prefix-only":
            return wire.Redaction(text=f"prefix:{text}", hits=1)
        if self.mode == "partial-tail":
            return wire.Redaction(text=text.replace(self.value, self.value[8:]), hits=1)
        if self.mode == "no-hits-trivial-change":
            return _TextOnly(text=text + " ")
        return self.inner.redact(text)

    def scrub_tail_prefix(self, text: str, window: int | None = None) -> tuple[str, bool]:
        return self.inner.scrub_tail_prefix(text, window)


class _CompleteRedactNoBoundaryScrub:
    """A filter that removes the complete known set but has no boundary contract (F-2)."""

    def __init__(self, values: tuple[str, ...]) -> None:
        self.inner = wire.SubstringRedactor(list(values))

    def redact(self, text: str):
        return self.inner.redact(text)


class _WrappedFilter:
    """A legitimate caller filter: the caller's own wrapper around a trusted one.

    It is deliberately *not* one of the module's classes, so "keep the caller's
    callback" is exercised on a filter the verification can only judge
    behaviourally.
    """

    def __init__(self, inner: object, prefix: str = "wrapped:") -> None:
        self.inner = inner
        self.prefix = prefix

    def redact(self, text: str):
        result = self.inner.redact(text)  # type: ignore[attr-defined]
        return wire.Redaction(text=result.text, hits=int(getattr(result, "hits", 0)))

    def scrub_tail_prefix(self, text: str, window: int | None = None) -> tuple[str, bool]:
        return self.inner.scrub_tail_prefix(text, window)  # type: ignore[attr-defined]


def _bad_filter(mode: str, value: str = SECRET_SENT) -> object:
    if mode == "missing-scrub":
        # It covers the *complete* known set, so only the missing boundary
        # contract can stand between it and a silent zero-row capture.
        return _CompleteRedactNoBoundaryScrub((value, SECRET_LEGACY))
    return _CallerFilter(mode, value)


# -- config / scope / project plumbing -------------------------------------


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


def _production_scope(root: pathlib.Path, *, redact: object | None = None) -> wire.WireScope:
    return wire.WireScope(
        sink=root / "wire" / "wire.jsonl",
        project_id="proj-t05q",
        scope_kind="production",
        origin="t05q",
        decision_id="dec-t05q",
        dp=DP3,
        evidence_path=root / "triage.jsonl",
        redact=redact,  # type: ignore[arg-type]
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


def _tree_text(root: pathlib.Path) -> str:
    chunks: list[str] = []
    if not root.exists():
        return ""
    for item in sorted(root.rglob("*")):
        if item.is_file():
            chunks.append(item.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def _fragment_visible(text: str, value: str, size: int = FRAGMENT) -> bool:
    """True when a fragment of ``value`` long enough to be material survives."""
    return any(value[start : start + size] in text for start in range(0, len(value) - size + 1))


def _assert_absent(text: str, *values: str) -> None:
    for value in values:
        assert value not in text, "credential-shaped material reached stored text"


def _assert_no_fragment(text: str, *values: str) -> None:
    for value in values:
        assert not _fragment_visible(text, value), (
            f"a {FRAGMENT}+ character fragment of a credential survived: {value[:4]}..."
        )


def _assert_rows_clean(rows: list[dict], *values: str) -> None:
    """Every stored free-text surface: body, metadata key/value, failure output.

    Only the text-bearing fields are scanned: the ledger also stores sha256
    digests and event ids, whose random hex may legitimately contain a
    4-character window of any value (that is not a leak).
    """
    for row in rows:
        for field in ("request", "response", "book"):
            capture = row.get(field)
            if isinstance(capture, dict) and capture.get("text") is not None:
                text = str(capture["text"])
                _assert_absent(text, *values)
                _assert_no_fragment(text, *values)
        for field in ("usage", "detail", "error_detail", "model", "transport", "reason"):
            raw = row.get(field)
            if raw is None:
                continue
            text = raw if isinstance(raw, str) else json.dumps(raw, ensure_ascii=False)
            _assert_absent(text, *values)
            _assert_no_fragment(text, *values)


# -- project / dp3 plumbing (points seam) ----------------------------------


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


def _write_decide(root: pathlib.Path, **fields: object) -> None:
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


def _dp3_state(**overrides: object) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP3,
        "questions_version": dpts.get_decision_point(DP3).questions_version,
        "key": "k-t05q",
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


def _observation_scope(root: pathlib.Path, *, redact: object) -> wire.WireScope:
    return wire.test_scope(
        root,
        project_id=wire.project_id_for(root),
        submission_id="sub-t05q",
        redact=redact,  # type: ignore[arg-type]
        evidence_path=root / "evidence.jsonl",
        warn=lambda line: None,
    )


def _decide_for_points(
    *,
    project: pathlib.Path,
    cfg: decision.DecisionConfig,
    snapshot: decision.CredentialSnapshot,
    scope: wire.WireScope,
) -> tuple[decision.DecisionClient, object | None, str | None]:
    """Run the points entry once; return the client, the outcome and a refusal."""
    client = _client(cfg, scope, credential_snapshot=snapshot)
    raised: str | None = None
    outcome = None
    try:
        outcome = dpts.decide_for(
            DP3,
            _dp3_state(task_summary=f"material {SECRET_LEGACY}"),
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=dpts.Observation(scope=scope, submission_id="sub-t05q"),
        )
    except decision.DecisionInputError as exc:  # the points refusal contract
        raised = str(exc)
    return client, outcome, raised


# ---------------------------------------------------------------------------
# 1. the coverage judgement itself (both consumptions, one semantics)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", BAD_MODES)
def test_coverage_judgement_rejects_an_unprovable_caller_filter(mode: str) -> None:
    """RED (T05q F-1/F-2): hits>0 / "text changed" accepted every leak class.

    The probe must catch a full value left behind (hits lie, prepend, cosmetic
    change), a long tail left by a partial replacement, and a filter that has no
    boundary scrub contract at all.
    """
    caller = _bad_filter(mode)
    assert decision._redactor_covers(caller, SECRET_SENT) is False, (
        f"the client-side coverage judgement accepted the {mode!r} filter"
    )
    assert dpts._redactor_covers(caller, SECRET_SENT) is False, (
        f"the points-side coverage judgement accepted the {mode!r} filter"
    )


def test_coverage_judgement_accepts_the_trusted_and_wrapped_shapes() -> None:
    """The stricter probe must not over-refuse a complete capture filter."""
    trusted = (
        wire.SubstringRedactor([SECRET_SENT]),
        decision._CredentialRedactor(exact=wire.SubstringRedactor([SECRET_SENT])),
        _WrappedFilter(wire.SubstringRedactor([SECRET_SENT])),
    )
    for caller in trusted:
        assert decision._redactor_covers(caller, SECRET_SENT) is True, repr(caller)
        assert dpts._redactor_covers(caller, SECRET_SENT) is True, repr(caller)


# ``KnownSecretRedactor`` is the *gate* shape (it redacts text for the book gate
# and has no capture-boundary scrub). It stays a fully working gate; it is not a
# capture filter, and using one as ``scope.redact`` never worked (the capture
# raised internally). Refusing it is the observable form of that, not a removed
# feature.
@pytest.mark.parametrize(
    "gate",
    [
        decision.KnownSecretRedactor(exact=(SECRET_SENT,)),
        decision.KnownSecretRedactor(fail_closed=True),
    ],
)
def test_coverage_judgement_rejects_a_gate_shaped_filter(gate: object) -> None:
    assert decision._capture_filter_contract_issue(gate) is not None
    assert decision._redactor_covers(gate, SECRET_SENT) is False
    assert dpts._redactor_covers(gate, SECRET_SENT) is False
    # It still redacts: the gate contract is untouched.
    assert gate.redact(SECRET_SENT).text == "<redacted>"


def test_coverage_judgement_rejects_a_value_that_is_not_covered_at_all() -> None:
    """A filter covering a different value never proved this one."""
    caller = wire.SubstringRedactor([SECRET_LEGACY])
    assert decision._redactor_covers(caller, SECRET_SENT) is False
    assert dpts._redactor_covers(caller, SECRET_SENT) is False


# ---------------------------------------------------------------------------
# 2. the client-only entry (real loopback, real capture)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", BAD_MODES)
def test_client_only_entry_refuses_an_unprovable_caller_filter(
    mode: str,
    server: _Server,
    tmp_path: pathlib.Path,
    isolated_home: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED (T05q F-1/F-2): the client sent and captured with an unprovable filter.

    ``hits``/text-change coverage passed all four leak classes, so the real
    request went out and the real ledger stored the value (or its tail) raw; the
    missing-boundary-scrub filter instead captured *zero* rows while the call
    reported success. The refusal must land before capture, attempt row or POST,
    and it must name the broken contract without a value.
    """
    _write_auth(isolated_home, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    caller = _bad_filter(mode)
    scope = _production_scope(tmp_path / f"client-{mode}", redact=caller)
    server.push({"status": 200})
    details: list[str] = []
    original_emit = decision.DecisionClient._emit

    def emit_spy(self, dp, start, available, reason, attempts, answers, detail, transport, source, backend=None):
        details.append(str(detail or ""))
        return original_emit(
            self, dp, start, available, reason, attempts, answers, detail, transport, source, backend
        )

    monkeypatch.setattr(decision.DecisionClient, "_emit", emit_spy)

    result = _client(cfg, scope).decide(
        {"note": f"carried {SECRET_SENT} and {SECRET_LEGACY} and {PLAIN_MATERIAL}"},
        QUESTIONS,
    )

    # Measured before the assertions so the RED run records the actual hole.
    raw = scope.sink.read_text(encoding="utf-8") if scope.sink.exists() else ""
    rows = _rows(scope.sink)
    assert result["available"] is False, (
        f"the client sent/captured with an unprovable caller filter (mode={mode}): "
        f"requests={len(server.requests)}, captured_rows={len(rows)}, "
        f"capture_status={scope.capture_status!r}, stored_value={SECRET_SENT in raw}, "
        f"stored_long_tail={_fragment_visible(raw, SECRET_SENT)}, "
        f"stored_legacy={SECRET_LEGACY in raw}, stored_bytes={len(raw)}"
    )
    assert result["reason"] == decision.REASON_ENTRY_UNAVAILABLE
    assert result["attempts"] == 0
    assert result["answers"] is None
    assert server.requests == [], "the unprovable capture reached the HTTP transport"
    assert scope.redact is caller, "the caller-owned filter was replaced"

    detail = " ".join(details)
    assert "capture redactor" in detail or "capture filter" in detail, detail
    if mode == "missing-scrub":
        assert "scrub_tail_prefix" in detail, detail
    else:
        assert "does not cover" in detail, detail
    _assert_absent(detail, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)
    _assert_absent(json.dumps(result), SECRET_SENT, SECRET_LEGACY, SECRET_ENV)

    assert _rows_of(rows, "attempt-start") == []
    assert _rows_of(rows, "attempt-end") == []
    assert _rows_of(rows, "book-snapshot") == []
    _assert_absent(raw, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)
    # Verifying the complete set costs exactly the one legacy read of this unit.
    assert calls == [SECRET_LEGACY], f"the refusal paid {len(calls)} discoveries"
    assert decision.current_credential_snapshot() is None, "a binding leaked"


# ---------------------------------------------------------------------------
# 3. the points entry (same judgement, same refusal, zero transport)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("mode", BAD_MODES)
def test_points_entry_refuses_an_unprovable_caller_filter(
    mode: str,
    server: _Server,
    tmp_path: pathlib.Path,
    isolated_home: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """RED (T05q F-1/F-2): the points seam shared the same weak judgement.

    ``decision_points`` kept its own copy of the check, so the same four leak
    classes stored raw material (and the missing-boundary-scrub filter stored
    nothing while reporting a complete capture). The seam must refuse with the
    same value-free detail before capture/transport, leaving the caller's filter
    and the pinned snapshot untouched.
    """
    _write_auth(isolated_home, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    project = _project(tmp_path)
    cfg = _cfg(server)
    snapshot = decision.credential_snapshot(cfg)
    caller = _bad_filter(mode)
    root = tmp_path / f"points-{mode}"
    scope = _observation_scope(root, redact=caller)
    server.answers = DP3_ANSWERS
    server.push({"status": 200})

    client, outcome, raised = _decide_for_points(
        project=project, cfg=cfg, snapshot=snapshot, scope=scope
    )

    raw = _tree_text(root)
    if raised is None:
        pytest.fail(
            f"the points entry did not refuse an unprovable caller filter (mode={mode}): "
            f"requests={len(server.requests)}, "
            f"rows={len(_rows(wire.test_wire_sink(root)))}, "
            f"status={getattr(outcome, 'status', None)!r}, stored_value={SECRET_SENT in raw}, "
            f"stored_long_tail={_fragment_visible(raw, SECRET_SENT)}, "
            f"stored_legacy={SECRET_LEGACY in raw}"
        )
    assert "unprovable capture" in raised, raised
    if mode == "missing-scrub":
        assert "scrub_tail_prefix" in raised, raised
    else:
        assert "does not cover" in raised, raised
    _assert_absent(raised, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)
    assert server.requests == [], "the unprovable capture reached the HTTP transport"
    assert scope.redact is caller, "the caller-owned filter was replaced"
    assert client._pinned_credential_snapshot is snapshot, "a pinned snapshot was rewritten"
    # The refusal is not a business refusal, so the decision row may exist; no
    # material of record (attempt/book) and no secret may.
    wire_rows = _rows(wire.test_wire_sink(root))
    assert [
        row
        for row in wire_rows
        if row.get("kind") in ("attempt-start", "attempt-end", "book-snapshot")
    ] == [], "an unprovable capture stored material of record"
    _assert_rows_clean(wire_rows, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)
    assert _rows(root / "evidence.jsonl") == []
    _assert_absent(raw, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)
    assert calls == [SECRET_LEGACY], f"the refusal paid {len(calls)} discoveries"
    assert decision.current_credential_snapshot() is None, "a binding leaked"


# ---------------------------------------------------------------------------
# 4. a legitimate (wrapped) caller filter keeps working - client entry
# ---------------------------------------------------------------------------


def test_client_entry_keeps_a_complete_wrapped_filter_and_redacts_everything(
    server: _Server,
    tmp_path: pathlib.Path,
    isolated_home: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No over-refusal, and the full value/metadata/failure text stay redacted.

    The caller filter is its own wrapper (not one of our classes); the client
    must keep it, and the 500 failure body, the arbitrary ``usage`` key/value
    and the stored request/response text must all be scrubbed.
    """
    _write_auth(isolated_home, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    snapshot = decision.credential_snapshot(cfg)
    # The caller's own freeze: the complete known set of this unit (T05l).
    assert snapshot.known_superset() == (SECRET_LEGACY,)
    inner = decision.credential_redactor(cfg, snapshot=snapshot)
    assert inner is not None
    caller = _WrappedFilter(inner)
    warnings: list[str] = []
    scope = _production_scope(tmp_path / "client-complete", redact=caller)
    scope.warn = warnings.append
    server.usage = {f"trace-{SECRET_LEGACY}": SECRET_LEGACY, "prompt_tokens": 7}
    server.push({"status": 500, "body": f"upstream failed near {SECRET_LEGACY}"})
    server.push({"status": 200})
    details: list[str] = []
    original_emit = decision.DecisionClient._emit

    def emit_spy(self, dp, start, available, reason, attempts, answers, detail, transport, source, backend=None):
        details.append(str(detail or ""))
        return original_emit(
            self, dp, start, available, reason, attempts, answers, detail, transport, source, backend
        )

    monkeypatch.setattr(decision.DecisionClient, "_emit", emit_spy)

    result = _client(cfg, scope, credential_snapshot=snapshot).decide(
        {"note": f"carried {SECRET_SENT} and {SECRET_LEGACY} and {PLAIN_MATERIAL}"},
        QUESTIONS,
    )

    assert result["available"] is True, result
    assert result["attempts"] == 2, result
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT] * 2
    assert scope.redact is caller, "the caller-owned filter was replaced"
    assert calls == [SECRET_LEGACY], "the verification re-opened the known-set discovery"
    assert decision.current_credential_snapshot() is None, "a binding leaked"

    rows = _rows(scope.sink)
    request_texts = _capture_texts(rows, "attempt-start", "request")
    response_texts = _capture_texts(rows, "attempt-end", "response")
    assert len(request_texts) == 2 and len(response_texts) == 2, rows
    _assert_rows_clean(rows, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)
    assert PLAIN_MATERIAL in "".join(request_texts), "the request was not captured at all"
    # A 500 failure body is free text; it must be redacted like any capture.
    assert "upstream failed" in response_texts[0]
    assert "<redacted>" in response_texts[0]
    ends = _rows_of(rows, "attempt-end")
    assert [row.get("http_status") for row in ends] == [500, 200], ends
    usage = json.dumps(ends[-1].get("usage"))
    _assert_absent(usage, SECRET_SENT, SECRET_LEGACY)
    assert "<redacted>" in usage, "the arbitrary metadata key/value pair was not redacted"
    # No secret in any free-text log surface of this run.
    _assert_absent("\n".join(warnings), SECRET_SENT, SECRET_LEGACY)
    _assert_absent("\n".join(details), SECRET_SENT, SECRET_LEGACY)
    _assert_absent(_tree_text(tmp_path / "client-complete"), SECRET_SENT, SECRET_LEGACY, SECRET_ENV)


def test_client_entry_keeps_a_complete_filter_scrubbing_a_long_secret_tail(
    server: _Server,
    tmp_path: pathlib.Path,
    isolated_home: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A secret cut by the capture cap must not leave a long tail on disk.

    The first call measures the real request bytes; the second call reuses the
    same state with ``segment_cap`` inside the sent secret, so the stored text
    ends mid-secret. ``scrub_tail_prefix`` of the caller's filter (verified by
    the coverage judgement) must remove it.
    """
    _write_auth(isolated_home, SECRET_LEGACY)
    _count_resolutions(monkeypatch)
    cfg = _cfg(server)
    snapshot = decision.credential_snapshot(cfg)
    assert snapshot.known_superset() == (SECRET_LEGACY,)
    inner = decision.credential_redactor(cfg, snapshot=snapshot)
    assert inner is not None
    caller = _WrappedFilter(inner)
    scope = _production_scope(tmp_path / "client-tail", redact=caller)
    state = {"note": f"carried {SECRET_SENT} and {SECRET_LEGACY}"}

    first = _client(cfg, scope, credential_snapshot=snapshot).decide(state, QUESTIONS)
    assert first["available"] is True, first
    assert len(server.requests) == 1, server.requests
    body = server.requests[0]["body"]
    offset = body.find(SECRET_SENT.encode("utf-8"))
    assert offset > 0, "fixture: the sent value must travel in the request body"

    # Cut the *read window* 8 characters into the sent secret: the head that is
    # redacted then holds only a strict prefix of it, which the caller's
    # ``scrub_tail_prefix`` has to remove.
    scope.segment_cap = max(1, offset - 32)
    read_window = offset + 8 - scope.segment_cap
    assert read_window > 0, "fixture: the read window must stay positive"
    scope.read_window = read_window
    second = _client(cfg, scope, credential_snapshot=snapshot).decide(state, QUESTIONS)
    assert second["available"] is True, second

    rows = _rows(scope.sink)
    requests_captured = [row.get("request") or {} for row in _rows_of(rows, "attempt-start")]
    assert len(requests_captured) == 2, rows
    cut = requests_captured[-1]
    stored = str(cut.get("text") or "")
    assert cut.get("read_capped") is True, cut
    assert cut.get("boundary_scrubbed") is True, cut
    assert len(stored) <= scope.segment_cap, cut
    _assert_absent(stored, SECRET_SENT, SECRET_LEGACY)
    _assert_no_fragment(stored, SECRET_SENT, SECRET_LEGACY)
    # The whole ledger of this run: no full value anywhere (hashes excluded).
    raw = _tree_text(tmp_path / "client-tail")
    _assert_absent(raw, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)
    _assert_rows_clean(rows, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)


# ---------------------------------------------------------------------------
# 5. a legitimate (wrapped) caller filter keeps working - points entry
# ---------------------------------------------------------------------------


def test_points_entry_keeps_a_complete_wrapped_filter(
    server: _Server,
    tmp_path: pathlib.Path,
    isolated_home: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The points seam must keep a complete caller filter and redact captures."""
    _write_auth(isolated_home, SECRET_LEGACY)
    calls = _count_resolutions(monkeypatch)
    project = _project(tmp_path)
    cfg = _cfg(server)
    snapshot = decision.credential_snapshot(cfg)
    assert snapshot.known_superset() == (SECRET_LEGACY,)
    inner = decision.credential_redactor(cfg, snapshot=snapshot)
    assert inner is not None
    caller = _WrappedFilter(inner)
    root = tmp_path / "points-complete"
    scope = _observation_scope(root, redact=caller)
    server.answers = DP3_ANSWERS
    server.usage = {f"trace-{SECRET_LEGACY}": SECRET_LEGACY, "prompt_tokens": 7}
    server.push({"status": 200})

    client, outcome, raised = _decide_for_points(
        project=project, cfg=cfg, snapshot=snapshot, scope=scope
    )

    assert raised is None, raised
    assert outcome is not None and outcome.response is not None, outcome
    assert outcome.response["available"] is True, outcome.detail
    assert [request["authorization"] for request in server.requests] == [SECRET_SENT]
    assert scope.redact is caller, "the caller-owned filter was replaced"
    assert client._pinned_credential_snapshot is snapshot
    assert calls == [SECRET_LEGACY], f"the verification paid {len(calls)} discoveries"

    raw = _tree_text(root)
    _assert_absent(raw, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)
    rows = _rows(wire.test_wire_sink(root))
    _assert_rows_clean(rows, SECRET_SENT, SECRET_LEGACY, SECRET_ENV)
    request_texts = _capture_texts(rows, "attempt-start", "request")
    assert request_texts, "the points entry captured no request text"
    usage = json.dumps([row.get("usage") for row in _rows_of(rows, "attempt-end")])
    _assert_absent(usage, SECRET_SENT, SECRET_LEGACY)
    assert decision.current_credential_snapshot() is None, "a binding leaked"
