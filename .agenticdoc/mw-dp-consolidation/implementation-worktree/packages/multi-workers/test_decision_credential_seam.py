"""test_decision_credential_seam.py - T05j (mw-decision-dashboard).

T05i froze the credential *inside* the transport: one ``CredentialSnapshot`` per
logical client call, every attempt of that call reusing it, and a capture
redactor built from it. It left the caller side open (its report's "owner
澶栨帴绾?): the CLI gate resolved the timi credential in
``mw._book_secret_redactor`` *before* the client, ``decision_points`` built the
capture redactor in ``_capture_scope`` from a *second* resolution, and the
client resolved a *third* one. A credential rotated between those points gave
one command three different "actual" values: gate=A / capture=A /
Authorization=B (and, when the gate was the stale one, a value the gate never
saw reached the transport).

The contract pinned here (card T05j):

* the CLI takes **one** ``decision.credential_snapshot(cfg)`` per command,
  before the book gate, and hands that object to the gate redactor and to the
  client; ``mw decide book check`` uses the same seam offline;
* ``decision_points.decide_for`` takes **one** snapshot per decision, after the
  per-DP budget clone and before any known-set gate, the capture scope and the
  client - a caller-pinned snapshot (the CLI's) is reused instead of resolving
  a second value;
* the actual ``Authorization`` of every attempt of a command, the known-secret
  set of the book gate and the capture redactor are the **same** value; a
  rotation is picked up by the **next** command/decision;
* a caller-owned capture ledger keeps its own redactor (never replaced) but is
  verified against that snapshot: a filter that misses the credential fails
  closed instead of storing it raw, and an unpinned caller client is bound to
  the decision's snapshot for exactly one call;
* the existing refusals stay zero-send (disabled / unconfigured / missing
  credential / zero budget), and no credential value is ever logged, printed or
  written to an evidence ledger.

Everything is synthetic and hermetic: the credential lives in a tmp
``auth.json`` (``decision_backends._auth_json_path`` is patched *before* any test
body runs; the cold-start children get an isolated ``HOME``/``USERPROFILE``),
credential env names are removed, and the only socket is a stdlib
``http.server`` on ``127.0.0.1:0``. The server echoes the ``Authorization`` it
received into the response body, so capture redaction is measured on the value
that was really sent. The evidence copy of the pytest log masks both synthetic
values as ``<rot-a>`` / ``<rot-b>``.
"""

from __future__ import annotations

import argparse
import http.server
import json
import os
import pathlib
import subprocess
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_backends as db  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire as wire  # noqa: E402
import mw  # noqa: E402

DP3 = "dp3-worker-clarify"
MW_PY = pathlib.Path(__file__).resolve().parent / "mw.py"

#: The synthetic credential the command starts with (``auth.json`` timi.key).
SECRET_A = "timi-seam-a-0123456789abcdef"
#: The synthetic credential rotated in *between* the seam's resolutions.
SECRET_B = "timi-seam-b-0123456789abcdef"
#: Never matches ``sk-`` / ``Bearer`` / the ambient env heuristics.
PLAIN_MATERIAL = "plain-seam-material-0123456789"

CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
    "TIMI_BASE_URL",
)


def _credential_env_names() -> tuple[str, ...]:
    """The named credentials plus every name the discovery rule would pick up.

    ``decision._credential_values`` treats any ``*_API_KEY`` / ``*_TOKEN`` /
    ``*_KEY`` / ``*_SECRET`` / ``*_PASSWORD`` variable as a secret, so leaving
    one of those set would make this test's known set depend on the developer's
    shell. The whole suffix set is removed, not just the named few.
    """
    names = set(CRED_ENV_VARS)
    names.update(
        name for name in os.environ if name.upper().endswith(decision._CRED_ENV_SUFFIXES)
    )
    return tuple(sorted(names))

#: Whole-wire answer map for dp3 as the timi backend decodes it.
DP3_ANSWERS = {
    "answer_kind": {"type": "choice", "choice": "fact", "confidence": 0.9},
    "answerable": {"type": "noul", "noul": 0.9},
    "candidate": {"type": "choice", "choice": "c1", "confidence": 0.9},
}


# -- local stdlib HTTP transport (the real boundary, never mocked) ----------


def _answer_body(authorization: str) -> bytes:
    """A legal dp3 answer that echoes the received Authorization into the body.

    The echo is the measurement: whatever the server really received must come
    back redacted, so a capture set that misses the sent value stores it raw.
    """
    return json.dumps(
        {
            "model": "jev-latest",
            "answers": DP3_ANSWERS,
            "note": f"used {authorization}",
        },
        ensure_ascii=False,
    ).encode("utf-8")


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
            payload = _answer_body(authorization)
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
    thread = threading.Thread(target=instance.serve_forever, daemon=True, name="t05j-http")
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
    """No ambient credential and no real ``~/.pi/agent/auth.json``, ever.

    The whole ``*_API_KEY``/``*_TOKEN``/``*_KEY``/``*_SECRET``/``*_PASSWORD``
    suffix set is removed *and* checked, so neither the sent value nor the
    known set can come from the developer's shell.
    """
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


def _install_rotation(
    monkeypatch: pytest.MonkeyPatch,
    path: pathlib.Path,
    *,
    at: int = 1,
    then: str = SECRET_B,
) -> list[str | None]:
    """Count real discoveries; rotate ``auth.json`` right after the ``at``-th.

    One resolution is the GREEN contract (``at=1`` also exercises the gate ->
    client window the baseline had, ``at=2`` the capture -> client window). The
    recorded values are the *resolved* credential, never a rendered message.
    """
    original = db.resolve_timi_api_key
    calls: list[str | None] = []

    def spy(env: dict | None = None, auth_path: pathlib.Path | None = None):
        value = original(env, auth_path)
        if env is None and auth_path is None:
            # A real ambient discovery (the seam's own resolution), not a test
            # redactor built from an explicit env/path.
            calls.append(value)
            if len(calls) == at:
                _write_auth(path, then)
        return value

    monkeypatch.setattr(db, "resolve_timi_api_key", spy)
    return calls


# -- project / book / CLI plumbing ------------------------------------------


def _write_decide(root: pathlib.Path, **fields) -> pathlib.Path:
    path = root / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"enabled": True, **fields}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


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


def _project(tmp_path: pathlib.Path, **decide_fields) -> pathlib.Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "notes.txt").write_text(
        "line1\nline2\nline3\nline4\nline5\n", encoding="utf-8", newline="\n"
    )
    fields = {
        "model": "jev-latest",
        "timeout_s": 5.0,
        "max_retries": 2,
        "backoff_base_s": 0,
    }
    fields.update(decide_fields)
    _write_decide(root, **fields)
    _enable_all(root)
    return root


def _dp3_state(**overrides) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP3,
        "questions_version": dpts.get_decision_point(DP3).questions_version,
        "key": "k-t05j",
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


def _book(dp_id: str, state: dict) -> dict:
    evidence = {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[dp_id]}
    return {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "state": state,
        "notes": {"evidence": evidence},
    }


def _write_book(root: pathlib.Path, book: dict, name: str = "book.json") -> pathlib.Path:
    path = root / name
    path.write_text(
        json.dumps(book, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _args(action: str, root: pathlib.Path, **kw) -> argparse.Namespace:
    base = {"subcommand": "decide", "decide_action": action, "project": str(root), "json": False}
    base.update(kw)
    return argparse.Namespace(**base)


def _run_args(root: pathlib.Path, **kw) -> argparse.Namespace:
    base = {"json": True, "request_file": None, "dp": None, "book": None}
    base.update(kw)
    return _args("run", root, **base)


def _book_args(root: pathlib.Path, action: str, **kw) -> argparse.Namespace:
    return _args("book", root, book_action=action, **kw)


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


def _assert_no_secret_anywhere(*roots: pathlib.Path, values: tuple[str, ...] = (SECRET_A, SECRET_B)):
    for root in roots:
        text = _tree_text(root)
        for value in values:
            assert value not in text, f"credential material under {root}"


def _observation_scope(
    root: pathlib.Path,
    *,
    redactor: object,
    submission_id: str = "sub-t05j",
) -> wire.WireScope:
    return wire.test_scope(
        root,
        project_id=wire.project_id_for(root),
        submission_id=submission_id,
        redact=redactor,
        evidence_path=root / "evidence.jsonl",
        warn=lambda line: None,
    )


def _cfg(server: _Server) -> decision.DecisionConfig:
    """A project-shaped config pointing at the loopback transport."""
    return decision.DecisionConfig(
        enabled=True,
        extras={"base_url": server.base_url},
        timeout_s=5.0,
        max_retries=2,
        backoff_base_s=0.0,
    )


# ---------------------------------------------------------------------------
# 1. CLI `decide run --book`: gate, capture and Authorization, one snapshot
# ---------------------------------------------------------------------------


def test_cli_run_book_gate_capture_and_authorization_share_one_snapshot(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """Rotate A -> B right after the first discovery (the gate/client window).

    Baseline: the book gate resolved A, the capture redactor resolved B and the
    client resolved B again - so the command's gate set was {A} while the
    transport sent B, and the echoed B was persisted raw (the capture set no
    longer contained the sent value). The contract: one snapshot, one value.
    """
    _write_auth(auth_json, SECRET_A)
    project = _project(tmp_path, base_url=server.base_url)
    calls = _install_rotation(monkeypatch, auth_json, at=1, then=SECRET_B)
    server.push({"status": 500})
    server.push({"status": 200})
    path = _write_book(project, _book(DP3, _dp3_state()))

    rc = mw.cmd_decide(_run_args(project, book=str(path)))
    captured = capsys.readouterr()

    assert rc == 0, captured.err
    # One discovery for the whole command, not one per surface.
    assert calls == [SECRET_A], f"the command resolved the credential {len(calls)} time(s)"
    # Every attempt of the one logical call carries the frozen value.
    assert [request["authorization"] for request in server.requests] == [SECRET_A, SECRET_A]
    sink = wire.production_wire_sink(project)
    raw = sink.read_bytes()
    assert SECRET_A.encode() not in raw, "the sent Authorization leaked into capture"
    assert SECRET_B.encode() not in raw, "the rotated credential leaked into capture"
    assert b"<redacted>" in raw
    assert SECRET_A not in captured.out + captured.err
    assert SECRET_B not in captured.out + captured.err
    _assert_no_secret_anywhere(tmp_path / "repo")


def test_cli_run_book_gate_uses_the_command_snapshot_and_sends_nothing(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """The book gate's known set *is* the command's snapshot (API + behaviour).

    Baseline took no snapshot at the CLI at all (``decision.credential_snapshot``
    was never called from ``mw.py``), so the gate resolved its own value; this
    pins the one-snapshot-per-command wiring and its zero-send refusal.
    """
    _write_auth(auth_json, SECRET_A)
    project = _project(tmp_path, base_url=server.base_url)
    snapshots: list[object] = []
    original = decision.credential_snapshot

    def snapshot_spy(cfg: object = None, **kwargs: object):
        snapshot = original(cfg, **kwargs)
        snapshots.append(snapshot)
        return snapshot

    monkeypatch.setattr(decision, "credential_snapshot", snapshot_spy)
    gate_snapshots: list[object] = []
    original_redactor = dpts.command_known_secret_redactor

    def gate_spy(cfg: object = None, *, snapshot: object = None):
        gate_snapshots.append(snapshot)
        return original_redactor(cfg, snapshot=snapshot)

    monkeypatch.setattr(dpts, "command_known_secret_redactor", gate_spy)
    path = _write_book(
        tmp_path, _book(DP3, _dp3_state(task_summary=f"copied {SECRET_A} here"))
    )

    rc = mw.cmd_decide(_run_args(project, book=str(path)))
    captured = capsys.readouterr()

    assert rc == 2, captured.out
    assert snapshots, "the CLI took no credential snapshot before the book gate"
    assert gate_snapshots and gate_snapshots[0] is snapshots[0], (
        "the book gate was not built from the command's credential snapshot"
    )
    assert "book-secret" in captured.err
    assert SECRET_A not in captured.out + captured.err
    assert server.requests == [], "a refused book reached the transport"
    assert not (project / books.RECEIPTS_RELATIVE_PATH).exists()
    assert _rows(wire.production_wire_sink(project)) == []
    _assert_no_secret_anywhere(tmp_path / "repo")


def test_cli_book_check_uses_the_command_snapshot_offline(
    auth_json: pathlib.Path,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """`book check` gates offline with the same one-snapshot seam (no client).

    One discovery per command: the value known at command start is refused, the
    value rotated in afterwards is *not* claimed by this command, and nothing is
    ever echoed.
    """
    _write_auth(auth_json, SECRET_A)
    project = _project(tmp_path)
    calls = _install_rotation(monkeypatch, auth_json, at=1, then=SECRET_B)
    path = _write_book(project, _book(DP3, _dp3_state(task_summary=f"copied {SECRET_A} here")))

    rc = mw.cmd_decide(_book_args(project, "check", file=str(path), json=True))
    captured = capsys.readouterr()

    assert rc == 2
    payload = json.loads(captured.out)
    assert payload["issues"][0]["code"] == "book-secret"
    assert calls == [SECRET_A], "the offline gate must resolve the credential once"
    assert SECRET_A not in captured.out + captured.err
    assert SECRET_B not in captured.out + captured.err

    # The next command resolves the rotated value (dynamic refresh kept).
    rotated = _write_book(
        project,
        _book(DP3, _dp3_state(task_summary=f"copied {SECRET_B} here")),
        "book-rotated.json",
    )
    rc_rotated = mw.cmd_decide(
        _book_args(project, "check", file=str(rotated), json=True)
    )
    captured_rotated = capsys.readouterr()
    assert rc_rotated == 2
    assert "book-secret" in captured_rotated.out
    assert SECRET_B not in captured_rotated.out + captured_rotated.err


# ---------------------------------------------------------------------------
# 2. decision_points: one snapshot per decision, capture and client share it
# ---------------------------------------------------------------------------


def test_points_production_decision_pins_capture_and_authorization(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No caller client: the decision's snapshot feeds capture *and* transport.

    Baseline resolved twice (capture redactor A, then the client B after the
    rotation), so the request went out with B while the capture set held A - the
    echoed B was stored raw in the production ledger.
    """
    _write_auth(auth_json, SECRET_A)
    project = _project(tmp_path, base_url=server.base_url)
    calls = _install_rotation(monkeypatch, auth_json, at=1, then=SECRET_B)
    server.push({"status": 500})
    server.push({"status": 200})

    outcome = dpts.decide_for(DP3, _dp3_state(), project, intent="answer")

    assert outcome.response is not None and outcome.response["available"] is True, outcome.detail
    assert calls == [SECRET_A], f"the decision resolved the credential {len(calls)} time(s)"
    assert [request["authorization"] for request in server.requests] == [SECRET_A, SECRET_A]
    sink = wire.production_wire_sink(project)
    raw = sink.read_bytes()
    assert SECRET_A.encode() not in raw
    assert SECRET_B.encode() not in raw, "the rotated credential was captured unredacted"
    assert b"<redacted>" in raw
    _assert_no_secret_anywhere(tmp_path / "repo")


def test_points_observation_refuses_a_caller_redactor_that_misses_the_credential(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
) -> None:
    """A caller-owned redactor is never replaced - an incomplete one is refused.

    The caller built its test-scope redactor while ``auth.json`` held A, then the
    credential rotated to B before the decision ran. Baseline sent B through the
    client while the caller's ledger could only redact A (B stored raw) and still
    called that an isolated observation. Fail closed instead.
    """
    _write_auth(auth_json, SECRET_A)
    project = _project(tmp_path, base_url=server.base_url)
    cfg = _cfg(server)
    root = tmp_path / "test-run"
    caller_redactor = decision.credential_redactor(
        cfg, extra_secrets=(SECRET_A,), env={}, auth_path=tmp_path / "no-auth.json"
    )
    scope = _observation_scope(root, redactor=caller_redactor)
    client = decision.DecisionClient(
        cfg=cfg, backend=db.TimiDecisionsBackend(), wire_scope=scope
    )
    # Rotation between the caller's set and the decision's own snapshot.
    _write_auth(auth_json, SECRET_B)

    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(),
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=dpts.Observation(scope=scope, submission_id="sub-t05j"),
        )

    message = str(excinfo.value)
    assert "unprovable capture" in message
    assert SECRET_A not in message and SECRET_B not in message
    assert server.requests == [], "an unprovable capture still reached the transport"
    rows = _rows(root / "evidence.jsonl")
    assert [row for row in rows if row.get("kind") in ("attempt-start", "book-snapshot")] == []
    _assert_no_secret_anywhere(tmp_path / "test-run")
    # The caller-owned redactor and the caller's client are left alone.
    assert scope.redact is caller_redactor
    assert client._pinned_credential_snapshot is None


def test_points_observation_binds_the_snapshot_to_a_caller_client(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unpinned caller client must send the decision's frozen value.

    The caller's redactor covers A and the decision's first discovery is A; the
    rotation happens right after it. Without binding, the client would resolve B
    at call time and its ``Authorization`` (B) would land raw in the caller's
    ledger - the "client B, caller A" pair this card forbids.
    """
    _write_auth(auth_json, SECRET_A)
    project = _project(tmp_path, base_url=server.base_url)
    calls = _install_rotation(monkeypatch, auth_json, at=1, then=SECRET_B)
    cfg = _cfg(server)
    root = tmp_path / "test-run"
    caller_redactor = decision.credential_redactor(
        cfg, extra_secrets=(SECRET_A,), env={}, auth_path=tmp_path / "no-auth.json"
    )
    scope = _observation_scope(root, redactor=caller_redactor)
    client = decision.DecisionClient(
        cfg=cfg, backend=db.TimiDecisionsBackend(), wire_scope=scope
    )
    server.push({"status": 500})
    server.push({"status": 200})

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, submission_id="sub-t05j"),
    )

    assert outcome.response is not None and outcome.response["available"] is True, outcome.detail
    assert calls == [SECRET_A], f"the decision resolved the credential {len(calls)} time(s)"
    assert [request["authorization"] for request in server.requests] == [SECRET_A, SECRET_A]
    text = _tree_text(root)
    assert SECRET_A not in text and SECRET_B not in text
    assert "<redacted>" in text
    # The caller's client is caller-owned: the binding is scoped to this call.
    assert client._pinned_credential_snapshot is None


# ---------------------------------------------------------------------------
# 3. Zero-send refusals keep their semantics through the new seam
# ---------------------------------------------------------------------------


def test_disabled_unconfigured_and_over_budget_commands_send_nothing(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """The global switch, a missing config and a zero budget stay zero HTTP."""
    _write_auth(auth_json, SECRET_A)
    book = _book(DP3, _dp3_state(task_summary=f"plain {PLAIN_MATERIAL}"))

    disabled = tmp_path / "disabled"
    disabled.mkdir()
    (disabled / ".git").mkdir()
    _write_decide(disabled, enabled=False)
    _enable_all(disabled)
    disabled_path = _write_book(disabled, book)
    rc_disabled = mw.cmd_decide(_run_args(disabled, book=str(disabled_path)))
    captured_disabled = capsys.readouterr()

    unconfigured = tmp_path / "unconfigured"
    unconfigured.mkdir()
    (unconfigured / ".git").mkdir()
    _enable_all(unconfigured)
    unconfigured_path = _write_book(unconfigured, book)
    rc_unconfigured = mw.cmd_decide(_run_args(unconfigured, book=str(unconfigured_path)))
    captured_unconfigured = capsys.readouterr()

    budget = tmp_path / "budget"
    budget.mkdir()
    (budget / ".git").mkdir()
    _write_decide(budget, max_total_tokens=1)
    _enable_all(budget)
    budget_path = _write_book(budget, book)
    rc_budget = mw.cmd_decide(_run_args(budget, book=str(budget_path)))
    captured_budget = capsys.readouterr()

    assert (rc_disabled, rc_unconfigured) == (0, 0)
    # The zero budget is refused by the *offline* book validator (book-budget),
    # so that command exits 2 - also before any transport access.
    assert rc_budget == 2
    assert server.requests == [], "a refused command reached the transport"
    for root in (disabled, unconfigured, budget):
        rows = _rows(wire.production_wire_sink(root))
        assert [row for row in rows if str(row.get("kind", "")).startswith("attempt-")] == []
        _assert_no_secret_anywhere(root)
    for captured in (captured_disabled, captured_unconfigured, captured_budget):
        assert SECRET_A not in captured.out + captured.err
        assert PLAIN_MATERIAL not in captured.out + captured.err


# ---------------------------------------------------------------------------
# 4. Cold start: fresh interpreter, isolated HOME, real loopback
# ---------------------------------------------------------------------------


def _run_child(
    argv: list[str], *, home: pathlib.Path, cwd: pathlib.Path | None = None
) -> subprocess.CompletedProcess:
    """Run in a child interpreter with no ambient credential and an isolated HOME."""
    env = {name: value for name, value in os.environ.items() if name not in _credential_env_names()}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return subprocess.run(
        [sys.executable, "-X", "utf8", *argv],
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        env=env,
        cwd=str(cwd) if cwd is not None else None,
    )


def test_cold_start_cli_chain_sends_one_credential_and_rotates_next_command(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    """The production CLI wiring, proven from a fresh interpreter.

    Run 1: ``auth.json`` holds A, the book passes, 500 then 200 - both POSTs
    carry A and the capture redacts it. Run 2 (new process, rotated B): the next
    command picks B up and redacts it. No hand-made events, no injected scope.
    """
    home = tmp_path / "home"
    auth = home / ".pi" / "agent" / "auth.json"
    _write_auth(auth, SECRET_A)
    project = _project(tmp_path, base_url=server.base_url)
    path = _write_book(project, _book(DP3, _dp3_state()))

    server.push({"status": 500})
    server.push({"status": 200})
    first = _run_child(
        [
            str(MW_PY),
            "decide",
            "run",
            "--book",
            str(path),
            "--project",
            str(project),
            "--json",
        ],
        home=home,
    )
    assert first.returncode == 0, first.stderr
    assert [request["authorization"] for request in server.requests] == [SECRET_A, SECRET_A]
    sink = wire.production_wire_sink(project)
    raw = sink.read_bytes()
    assert SECRET_A.encode() not in raw and b"<redacted>" in raw
    assert SECRET_A not in first.stdout + first.stderr

    _write_auth(auth, SECRET_B)
    server.steps.clear()
    server.push({"status": 500})
    server.push({"status": 200})
    second = _run_child(
        [
            str(MW_PY),
            "decide",
            "run",
            "--book",
            str(path),
            "--project",
            str(project),
            "--json",
        ],
        home=home,
    )
    assert second.returncode == 0, second.stderr
    assert [request["authorization"] for request in server.requests[2:]] == [SECRET_B, SECRET_B]
    raw = sink.read_bytes()
    assert SECRET_B.encode() not in raw, "the rotated credential was captured unredacted"
    assert SECRET_B not in second.stdout + second.stderr
    _assert_no_secret_anywhere(project)


_COLD_START_POINTS_BOOK = r'''
import json
import pathlib
import sys

project = pathlib.Path(sys.argv[1])
package = pathlib.Path(sys.argv[2])
sys.path.insert(0, str(package))

import decision
import decision_book  # noqa: F401  (registers the book validator)
import decision_points as dpts
import decision_wire

DP = "dp3-worker-clarify"
SUB = "sub-t05j-cold"
root = project / "run"
root.mkdir(parents=True, exist_ok=True)
cfg = decision.DecisionConfig(enabled=True)
# The ledger filter is the documented one: built from the timi chain (the
# isolated HOME auth.json of this process), not from a hand-passed value.
redactor = decision.credential_redactor(cfg)
scope = decision_wire.test_scope(
    root,
    project_id=decision_wire.project_id_for(root),
    submission_id=SUB,
    redact=redactor,
    evidence_path=root / "evidence.jsonl",
    warn=lambda line: None,
)
state = {
    "schema_version": 2,
    "decision_point": DP,
    "questions_version": dpts.get_decision_point(DP).questions_version,
    "key": "k-cold-t05j",
    "phase": "EXECUTE",
    "task_type": "coding",
    "risk": "low",
    "risk_source": "machine",
    "authority_tier": "P2",
    "task_summary": "cold start seam probe",
    "ambiguity": {"kind": "fact", "question": "which file holds the points?"},
    "local_candidates": [{"id": "c1", "label": "candidate"}],
}
book = {
    "schema_version": 2,
    "decision_point": DP,
    "state": state,
    "notes": {"evidence": {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[DP]}},
}
outcome = dpts.decide_for(
    DP,
    state,
    project,
    archive=False,
    intent="answer",
    observation=dpts.Observation(scope=scope, book=book, submission_id=SUB),
)
sink = root / "wire.jsonl"
text = sink.read_text(encoding="utf-8") if sink.exists() else ""
print(
    json.dumps(
        {
            "available": bool((outcome.response or {}).get("available")),
            "reason": outcome.escalated_reason,
            "detail": outcome.detail,
            "capture_channel": outcome.capture_channel,
            "capture_status": outcome.capture_status,
            "attempts": len([row for row in text.splitlines() if "attempt-start" in row]),
            "redacted": "<redacted>" in text,
        }
    )
)
'''


def test_cold_start_points_book_chain_sends_the_gated_credential(
    server: _Server, tmp_path: pathlib.Path
) -> None:
    """The points + book chain, proven from a fresh interpreter.

    No client and no injected snapshot: ``decide_for`` resolves the credential
    of the isolated HOME itself, the book gate sees it (it is not in the book),
    the capture scope is built from the same object and the transport sends it.
    """
    home = tmp_path / "home"
    auth = home / ".pi" / "agent" / "auth.json"
    _write_auth(auth, SECRET_A)
    project = _project(tmp_path, base_url=server.base_url)
    script = tmp_path / "cold_start_points_book.py"
    script.write_text(_COLD_START_POINTS_BOOK, encoding="utf-8", newline="\n")
    server.push({"status": 500})
    server.push({"status": 200})

    proc = _run_child(
        [str(script), str(project), str(pathlib.Path(__file__).resolve().parent)],
        home=home,
    )

    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])
    assert result["available"] is True, result
    assert result["capture_channel"] == "test-scope"
    assert result["attempts"] == 2, result
    assert result["redacted"] is True, result
    assert [request["authorization"] for request in server.requests] == [SECRET_A, SECRET_A]
    _assert_no_secret_anywhere(project)
    assert SECRET_A not in proc.stdout + proc.stderr


# ---------------------------------------------------------------------------
# 5. Frozen contracts this card must not have changed
# ---------------------------------------------------------------------------


def test_the_seam_snapshot_is_the_only_authority(
    auth_json: pathlib.Path, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The shared seam helpers stay pure: one snapshot, no value in the repr."""
    _write_auth(auth_json, SECRET_A)
    cfg = decision.DecisionConfig(enabled=True)
    snapshot = decision.credential_snapshot(cfg)
    assert snapshot.api_key == SECRET_A and snapshot.source == "auth-json"
    assert SECRET_A not in repr(snapshot)
    # An auth-json snapshot already *is* the timi discovery: no second resolve.
    assert dpts.known_secret_superset(snapshot) == ()
    # The seam redactor covers the snapshot value and the pre-existing layers.
    redactor = dpts.command_known_secret_redactor(cfg, snapshot=snapshot)
    hit = redactor.redact(f"material {SECRET_A}")
    assert hit.hits >= 1 and SECRET_A not in hit.text
    assert redactor.redact("credentials in plain text").hits == 0
    # No credential is bound outside the call.
    assert decision.current_credential_snapshot() is None


def test_the_evidence_ledgers_written_here_carry_no_credential(
    server: _Server,
    tmp_path: pathlib.Path,
    auth_json: pathlib.Path,
    capsys: pytest.CaptureFixture,
) -> None:
    """A legal command's whole output surface (stdout/stderr/ledgers) is clean."""
    _write_auth(auth_json, SECRET_A)
    project = _project(tmp_path, base_url=server.base_url)
    server.push({"status": 200})
    path = _write_book(project, _book(DP3, _dp3_state()))

    rc = mw.cmd_decide(_run_args(project, book=str(path)))
    captured = capsys.readouterr()

    assert rc == 0, captured.err
    assert len(server.requests) == 1
    assert SECRET_A not in captured.out + captured.err
    _assert_no_secret_anywhere(tmp_path / "repo")
    sink = wire.production_wire_sink(project)
    rows = _rows(sink)
    assert [row for row in rows if row.get("kind") == "book-snapshot"], rows
    # The evidence rows carry a hash of the redacted text, never the text.
    for row in rows:
        assert SECRET_A not in json.dumps(row, ensure_ascii=False)
