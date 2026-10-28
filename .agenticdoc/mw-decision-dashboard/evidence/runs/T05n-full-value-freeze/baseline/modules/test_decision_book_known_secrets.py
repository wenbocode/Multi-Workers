"""test_decision_book_known_secrets.py — T05e: the book-secret gate's known set.

Review F1 (P0): the gate recognised only env ``*_API_KEY``/``*_TOKEN``/``*_KEY``/
``*_SECRET``/``*_PASSWORD`` values, ``Bearer`` and ``sk-``. A *configured*
credential (``.mw/decide.json`` ``api_key`` -> ``extras["api_key"]``, the actual
``Authorization`` value, or the resolved timi credential from ``auth.json``) that
is neither env-named nor ``sk-``/``Bearer`` therefore passed the book gate and
was sent inside ``book_state(book)``. Review F2 (P1): the context scan read only
``text``/``label``/``source``/``path`` of an item while the whole item is sent.
Review F3 (P2): an unknown context slot / state key was echoed verbatim into the
issue path (hence stderr/outcome/ledger).

The tests are behavioural: the refusal must happen before the transport (zero
backend calls, zero ``attempt-*``/``book-snapshot`` rows) and no value may be
echoed into an issue path/detail, stderr or stdout. Every credential is
synthetic:
* config credentials come from a tmp ``.mw/decide.json`` / in-memory cfg;
* the timi credential comes from a tmp ``auth.json`` fixture reached through
  ``decision_backends._auth_json_path`` (never the real ``~/.pi`` file);
* env credential names are removed by the hermetic fixture.
"""

from __future__ import annotations

import argparse
import inspect
import json
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_backends  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire  # noqa: E402
import mw  # noqa: E402

DP3 = "dp3-worker-clarify"
DP5 = "dp5-test-triage"
SUB = "sub-t05e"
MW_PY = pathlib.Path(__file__).resolve().parent / "mw.py"

#: None of these match ``sk-``, ``Bearer`` or the ambient env heuristics: only
#: the real (configured) credential set can recognise them.
CFG_SECRET = "cfg-book-known-0123456789abcdef"
EXTRA_SECRET = "extra-book-known-0123456789"
AUTH_SECRET = "authjson-book-known-0123456789abcdef"
ROTATED_SECRET = "rotated-book-known-0123456789abcd"
SHORT_SECRET = "z9q7"  # 4 chars: the injected set's minimum length
UNKNOWN_SECRET = "unknown-looking-0123456789abcdef"

CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
)


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    for name in CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # The production resolver must never read the developer's real auth.json.
    monkeypatch.setattr(
        decision_backends, "_auth_json_path", lambda: tmp_path / "no-auth.json"
    )
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


# ---------------------------------------------------------------------------
# Fixtures: a repo-like project, a legal dp3 book, a test scope
# ---------------------------------------------------------------------------


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
    _write_decide(root, **decide_fields)
    _enable_all(root)
    return root


def _dp3_state(**overrides) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP3,
        "questions_version": dpts.get_decision_point(DP3).questions_version,
        "key": "k-t05e",
        "phase": "EXECUTE",
        "task_type": "coding",
        "risk": "mid",
        "risk_source": "pm-label",
        "authority_tier": "P2",
        "task_summary": "worker asks which file holds the decide-points table",
        "ambiguity": {"kind": "fact", "question": "which file holds the decide points?"},
        "local_candidates": [{"id": "c1", "label": ".mw/decide-points.json"}],
    }
    state.update(overrides)
    return state


def _dp5_state(**overrides) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP5,
        "questions_version": dpts.get_decision_point(DP5).questions_version,
        "test": {
            "failed_cases": ["case_a"],
            "baseline_cases": ["case_b"],
            "changed_paths": ["packages/multi-workers/x.py"],
            "repro_consistent": True,
        },
    }
    state.update(overrides)
    return state


def _book(dp_id: str, state: dict, *, context: dict | None = None) -> dict:
    evidence = {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[dp_id]}
    book = {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "state": state,
        "notes": {"evidence": evidence},
    }
    if context is not None:
        book["context"] = dict(context)
        for slot, content in context.items():
            if books._is_empty_content(content):
                continue
            evidence[books.context_evidence_key(slot)] = "cmd: true"
    return book


def _write_book(root: pathlib.Path, book: dict, name: str = "book.json") -> pathlib.Path:
    path = root / name
    path.write_text(
        json.dumps(book, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return path


def _redactor(tmp_path: pathlib.Path, cfg=None, *, extra=()):
    return decision.known_secret_redactor(
        cfg,
        extra_secrets=extra,
        env={},
        auth_path=tmp_path / "no-auth.json",
    )


def _scope(root: pathlib.Path):
    """A test scope whose own redactor does NOT know the configured secrets.

    That separation is the point of F1: the book gate must inject the actual
    known set, not rely on whatever the wire scope happens to redact.
    """
    redactor = decision.credential_redactor(
        extra_secrets=(), env={}, auth_path=root / "no-auth.json"
    )
    assert redactor is not None
    return decision_wire.test_scope(
        root,
        project_id=decision_wire.project_id_for(root),
        submission_id=SUB,
        redact=redactor,
        evidence_path=root / "evidence.jsonl",
        warn=lambda line: None,
    )


def _client(backend, scope, *, extras: dict | None = None) -> decision.DecisionClient:
    cfg = decision.DecisionConfig(enabled=True, extras=dict(extras or {}))
    return decision.DecisionClient(cfg=cfg, backend=backend, wire_scope=scope)


def _ok(answers: dict) -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=True,
        reason=None,
        retryable=False,
        answers=answers,
        latency_ms=2,
        detail="",
    )


def _dp3_answers() -> dict:
    return {
        "answer_kind": {"value": "fact", "confidence": 0.9},
        "answerable": {"value": 0.9},
        "candidate": {"value": "c1", "confidence": 0.9},
    }


def _secret_issues(issues) -> list[tuple[str, str]]:
    return [(issue.code, issue.path) for issue in issues if issue.code == "book-secret"]


def _rows(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _of_kind(path: pathlib.Path, kind: str) -> list[dict]:
    return [row for row in _rows(path) if row.get("kind") == kind]


def _args(action: str, root: pathlib.Path, **kw) -> argparse.Namespace:
    base = {"subcommand": "decide", "decide_action": action, "project": str(root), "json": False}
    base.update(kw)
    return argparse.Namespace(**base)


def _book_args(root: pathlib.Path, action: str, **kw) -> argparse.Namespace:
    return _args("book", root, book_action=action, **kw)


def _run_args(root: pathlib.Path, **kw) -> argparse.Namespace:
    base = {"json": True, "request_file": None, "dp": None, "book": None}
    base.update(kw)
    return _args("run", root, **base)


# ---------------------------------------------------------------------------
# F1: the gate's known set is the actual configured credential set
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("secret", [CFG_SECRET, SHORT_SECRET], ids=["long", "short"])
def test_check_book_with_the_injected_redactor_flags_a_configured_credential(
    secret: str, tmp_path: pathlib.Path
) -> None:
    project = _project(tmp_path)
    cfg = decision.DecisionConfig(enabled=True, extras={"api_key": secret})
    book = _book(DP3, _dp3_state(task_summary=f"copied {secret} into the book"))

    issues = books.check_book(book, project_dir=project, redactor=_redactor(tmp_path, cfg))
    assert _secret_issues(issues) == [("book-secret", "state.task_summary")], [
        (issue.code, issue.path) for issue in issues
    ]
    for issue in issues:
        assert secret not in issue.path and secret not in issue.detail

    # Without the injected set the same book passes: this is exactly the P0.
    assert _secret_issues(books.check_book(book, project_dir=project)) == []


def test_the_dataclass_authorization_value_is_in_the_injected_set(
    tmp_path: pathlib.Path,
) -> None:
    cfg = decision.DecisionConfig(enabled=True)
    cfg.api_key = CFG_SECRET  # the actual Authorization value the client sends
    book = _book(DP3, _dp3_state(ambiguity={"kind": "fact", "question": f"why {CFG_SECRET}"}))

    issues = books.check_book(book, project_dir=_project(tmp_path), redactor=_redactor(tmp_path, cfg))
    assert _secret_issues(issues) == [("book-secret", "state.ambiguity.question")]


def test_the_book_gate_redactor_needs_no_wire_module(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """Capture may be off; the gate must still prove the configured value."""
    cfg = decision.DecisionConfig(enabled=True, extras={"api_key": CFG_SECRET})
    monkeypatch.setattr(decision, "_WIRE_LOADED", True)
    monkeypatch.setattr(decision, "_WIRE_MODULE", None)

    assert decision.credential_redactor(cfg) is None, "capture stays off without the wire"
    redactor = decision.known_secret_redactor(
        cfg, env={}, auth_path=tmp_path / "no-auth.json"
    )
    result = redactor.redact(f"before {CFG_SECRET} after")
    assert result.hits == 1 and CFG_SECRET not in result.text


def test_known_secret_redactor_and_credential_redactor_share_one_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    """The refactor must freeze ``credential_redactor``'s behaviour exactly."""
    env = {"TIMI_API_KEY": EXTRA_SECRET, "T05E_SOME_TOKEN": "env-token-book-0123456789"}
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"timi": {"key": AUTH_SECRET}}), encoding="utf-8")
    cfg = decision.DecisionConfig(enabled=True, extras={"api_key": CFG_SECRET})
    cfg.api_key = "dataclass-authorization-0123456789"
    text = (
        f"{CFG_SECRET} dataclass-authorization-0123456789 {AUTH_SECRET} "
        f"env-token-book-0123456789 Bearer bearer-book-0123456789 sk-book-0123456789"
    )

    capture = decision.credential_redactor(cfg, env=env, auth_path=auth)
    gate = decision.known_secret_redactor(cfg, env=env, auth_path=auth)
    assert capture is not None
    assert capture.redact(text).text == gate.redact(text).text
    assert capture.redact(text).hits == gate.redact(text).hits


def test_the_auth_json_timi_credential_is_in_the_gate_set(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"timi": {"key": AUTH_SECRET}}), encoding="utf-8")
    monkeypatch.setattr(decision_backends, "_auth_json_path", lambda: auth)
    project = _project(tmp_path)
    book = _book(DP3, _dp3_state(task_summary=f"token {AUTH_SECRET}"))

    assert _secret_issues(books.check_book(book, project_dir=project)) == []
    issues = books.check_book(
        book,
        project_dir=project,
        redactor=decision.known_secret_redactor(env={}),
    )
    assert _secret_issues(issues) == [("book-secret", "state.task_summary")]
    for issue in issues:
        assert AUTH_SECRET not in issue.detail and AUTH_SECRET not in issue.path


def test_a_rotated_credential_is_resolved_per_call(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    auth = tmp_path / "auth.json"
    monkeypatch.setattr(decision_backends, "_auth_json_path", lambda: auth)
    project = _project(tmp_path)

    def check(secret: str):
        auth.write_text(json.dumps({"timi": {"key": secret}}), encoding="utf-8")
        book = _book(DP3, _dp3_state(task_summary=f"token {secret}"))
        return books.check_book(
            book, project_dir=project, redactor=decision.known_secret_redactor(env={})
        )

    assert _secret_issues(check(ROTATED_SECRET))
    assert _secret_issues(check(AUTH_SECRET)), "a rotated value must be re-resolved"
    # The old value is no longer known after the rotation (no cached union).
    book = _book(DP3, _dp3_state(task_summary=f"token {ROTATED_SECRET}"))
    assert _secret_issues(
        books.check_book(
            book, project_dir=project, redactor=decision.known_secret_redactor(env={})
        )
    ) == []


def test_cli_book_check_refuses_a_configured_credential_and_echoes_nothing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path, api_key=CFG_SECRET)
    path = _write_book(project, _book(DP3, _dp3_state(task_summary=f"use {CFG_SECRET}")))

    rc = mw.cmd_decide(_book_args(project, "check", file=str(path), json=True))
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert rc == 2
    assert payload["issues"][0]["code"] == "book-secret"
    assert payload["issues"][0]["path"] == "state.task_summary"
    assert CFG_SECRET not in captured.out and CFG_SECRET not in captured.err
    assert not (project / books.RECEIPTS_RELATIVE_PATH).exists()


def test_cli_run_book_with_a_configured_credential_is_refused_with_zero_http(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path, api_key=CFG_SECRET)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: backend)
    path = _write_book(project, _book(DP3, _dp3_state(task_summary=f"use {CFG_SECRET}")))

    rc = mw.cmd_decide(_run_args(project, book=str(path)))
    captured = capsys.readouterr()

    assert rc == 2
    assert backend.calls == [], "a configured credential reached the transport"
    assert "book-secret" in captured.err and CFG_SECRET not in captured.err
    assert not (project / books.RECEIPTS_RELATIVE_PATH).exists()
    assert not (project / ".agenticdoc" / "_autopilot" / "decisions.jsonl").exists()


def test_observation_refuses_a_configured_credential_with_zero_send(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    state = _dp3_state(task_summary=f"copied {CFG_SECRET} here")
    book = _book(DP3, state)
    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])

    outcome = dpts.decide_for(
        DP3,
        state,
        project,
        client=_client(backend, scope, extras={"api_key": CFG_SECRET}),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, book=book, submission_id=SUB),
    )

    assert outcome.escalated_reason == "input-incomplete", outcome.detail
    assert "book-secret" in outcome.detail
    assert CFG_SECRET not in outcome.detail
    assert backend.calls == [], "the observation sent the configured credential"
    assert _of_kind(root / "evidence.jsonl", "book-snapshot") == []
    assert _of_kind(root / "evidence.jsonl", "attempt-start") == []
    if (root / "evidence.jsonl").exists():
        assert CFG_SECRET not in (root / "evidence.jsonl").read_text(encoding="utf-8")


def test_observation_refuses_the_auth_json_timi_credential(
    monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path
) -> None:
    auth = tmp_path / "auth.json"
    auth.write_text(json.dumps({"timi": {"key": AUTH_SECRET}}), encoding="utf-8")
    monkeypatch.setattr(decision_backends, "_auth_json_path", lambda: auth)
    project = _project(tmp_path)
    state = _dp3_state(task_summary=f"copied {AUTH_SECRET} here")
    book = _book(DP3, state)
    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])

    outcome = dpts.decide_for(
        DP3,
        state,
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, book=book, submission_id=SUB),
    )

    assert outcome.escalated_reason == "input-incomplete", outcome.detail
    assert "book-secret" in outcome.detail
    assert AUTH_SECRET not in outcome.detail
    assert backend.calls == []
    assert _of_kind(root / "evidence.jsonl", "book-snapshot") == []


def test_no_credentials_and_disabled_transport_still_send_nothing(
    tmp_path: pathlib.Path,
) -> None:
    """The secret check never becomes a network/credential probe."""
    project = tmp_path / "unconfigured"
    (project / ".git").mkdir(parents=True)
    (project / "notes.txt").write_text("line1\n", encoding="utf-8", newline="\n")
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    book = _book(DP3, _dp3_state(task_summary=f"plain {UNKNOWN_SECRET}"))
    root = tmp_path / "run"
    scope = _scope(root)
    disabled = decision.DecisionClient(
        cfg=decision.DecisionConfig(enabled=False), backend=backend, wire_scope=scope
    )

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(task_summary=f"plain {UNKNOWN_SECRET}"),
        project,
        client=disabled,
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, book=book, submission_id=SUB),
    )

    assert outcome.escalated_reason == "unavailable", outcome.detail
    assert backend.calls == []
    assert _of_kind(root / "evidence.jsonl", "book-snapshot") == []
    # An unknown value is not claimed as a secret: the gate never guesses.
    assert _secret_issues(
        books.check_book(
            book,
            project_dir=project,
            redactor=decision.known_secret_redactor(env={}, auth_path=tmp_path / "no-auth.json"),
        )
    ) == []


# ---------------------------------------------------------------------------
# F2: the scan face is exactly the send face (``book_state``)
# ---------------------------------------------------------------------------


def test_a_context_item_extra_key_is_scanned_because_it_is_sent(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("T05E_PROBE_API_KEY", CFG_SECRET)
    project = _project(tmp_path)
    item = {
        "id": "c1",
        "path": "notes.txt",
        "line": 2,
        "text": "line2",
        "source": "notes.txt:2",
        "note": f"copied {CFG_SECRET} into an undeclared item key",
    }
    book = _book(DP3, _dp3_state(), context={"candidate_snippets": [item]})

    sent = books.book_state(book)
    assert sent["context"]["candidate_snippets"][0]["note"] == item["note"], (
        "a legal context field must not be deleted to hide a scan gap"
    )

    issues = books.check_book(book, project_dir=project)
    assert _secret_issues(issues) == [
        ("book-secret", "context.candidate_snippets[0].note")
    ], [(issue.code, issue.path) for issue in issues]
    for issue in issues:
        assert CFG_SECRET not in issue.detail and CFG_SECRET not in issue.path


def test_context_diagnostics_keep_the_context_prefix(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    book = _book(
        DP3, _dp3_state(), context={"change_summary": "token sk-abcdef123456"}
    )
    issues = books.check_book(book, project_dir=project)
    assert _secret_issues(issues) == [("book-secret", "context.change_summary")]


def test_material_outside_the_sent_state_is_not_scanned(tmp_path: pathlib.Path) -> None:
    """No over-scan: only ``book_state(book)`` reaches the transport."""
    project = _project(tmp_path)
    book = _book(DP3, _dp3_state())
    book["notes"]["diagnostic"] = f"local only {CFG_SECRET}"

    assert "diagnostic" not in books.book_state(book)
    assert _secret_issues(books.check_book(book, project_dir=project)) == []


# ---------------------------------------------------------------------------
# F3: unknown slot/key display paths never echo a credential
# ---------------------------------------------------------------------------


def test_an_unknown_context_slot_that_is_a_credential_is_not_echoed(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    cfg = decision.DecisionConfig(enabled=True, extras={"api_key": CFG_SECRET})
    book = _book(
        DP3,
        _dp3_state(),
        context={"change_summary": f"token {CFG_SECRET}", CFG_SECRET: "x"},
    )

    issues = books.check_book(book, project_dir=project, redactor=_redactor(tmp_path, cfg))
    context_issues = [(issue.code, issue.path) for issue in issues if issue.code == "book-context"]
    assert ("book-context", "context.<key>") in context_issues, context_issues
    for issue in issues:
        assert CFG_SECRET not in issue.path, issue.path
        assert CFG_SECRET not in issue.detail, issue.detail
    # The safe slot keeps its diagnostic name (only the malicious key collapses).
    assert "context.change_summary" in [
        issue.path for issue in issues if issue.code == "book-secret"
    ]


def test_an_unknown_state_key_that_is_a_credential_is_not_echoed(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    cfg = decision.DecisionConfig(enabled=True, extras={"api_key": CFG_SECRET})
    state = _dp3_state(**{CFG_SECRET: "x"})
    book = _book(DP3, state)

    direct = dpts.state_unknown_key_issues(DP3, state, redactor=_redactor(tmp_path, cfg))
    assert [path for path, _detail in direct] == ["<key>"], direct

    issues = books.check_book(book, project_dir=project, redactor=_redactor(tmp_path, cfg))
    assert ("book-state", "state.<key>") in [(issue.code, issue.path) for issue in issues]
    for issue in issues:
        assert CFG_SECRET not in issue.path and CFG_SECRET not in issue.detail


def test_the_unknown_key_refusal_does_not_echo_the_credential_through_the_seam(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    state = _dp3_state(**{CFG_SECRET: "x"})
    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])

    outcome = dpts.decide_for(
        DP3,
        state,
        project,
        client=_client(backend, scope, extras={"api_key": CFG_SECRET}),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, submission_id=SUB),
    )

    assert outcome.escalated_reason == "input-incomplete", outcome.detail
    assert "<key>" in outcome.detail
    assert CFG_SECRET not in outcome.detail
    assert backend.calls == []
    if (root / "evidence.jsonl").exists():
        assert CFG_SECRET not in (root / "evidence.jsonl").read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# Independent cold start: the CLI and the points+book import chain
# ---------------------------------------------------------------------------


def _run_child(
    argv: list[str], *, home: pathlib.Path, input_text: str | None = None
) -> subprocess.CompletedProcess:
    """Run in a child interpreter with no ambient credential and an isolated HOME.

    Redirecting ``HOME``/``USERPROFILE`` means the production auth.json resolver
    can only ever see the synthetic fixture (never the developer's real file).
    """
    env = {name: value for name, value in os.environ.items() if name not in CRED_ENV_VARS}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    return subprocess.run(
        [sys.executable, "-X", "utf8", *argv],
        input=input_text,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=300,
        env=env,
    )


def test_cold_start_cli_refuses_config_and_auth_json_credentials(
    tmp_path: pathlib.Path,
) -> None:
    home = tmp_path / "home"
    (home / ".pi" / "agent").mkdir(parents=True)
    project = _project(tmp_path)
    _write_decide(project, api_key=CFG_SECRET)
    auth = home / ".pi" / "agent" / "auth.json"

    cases = ((CFG_SECRET, None), (AUTH_SECRET, AUTH_SECRET), (ROTATED_SECRET, ROTATED_SECRET))
    for secret, auth_secret in cases:
        if auth_secret is not None:
            auth.write_text(json.dumps({"timi": {"key": auth_secret}}), encoding="utf-8")
        path = _write_book(project, _book(DP3, _dp3_state(task_summary=f"use {secret}")))
        proc = _run_child(
            [str(MW_PY), "decide", "book", "check", str(path), "--project", str(project), "--json"],
            home=home,
        )
        assert proc.returncode == 2, (secret, proc.stdout, proc.stderr)
        payload = json.loads(proc.stdout)
        assert payload["issues"][0]["code"] == "book-secret", payload
        assert secret not in proc.stdout and secret not in proc.stderr

    legal = _write_book(project, _book(DP3, _dp3_state()), "legal.json")
    passed = _run_child(
        [str(MW_PY), "decide", "book", "check", str(legal), "--project", str(project), "--json"],
        home=home,
    )
    assert passed.returncode == 0, (passed.stdout, passed.stderr)


_COLD_START_SEAM_SCRIPT = r'''
import json
import pathlib
import sys

project = pathlib.Path(sys.argv[1])
package = pathlib.Path(sys.argv[2])
secret = sys.argv[3]
sys.path.insert(0, str(package))

import decision
import decision_points as dpts
import decision_wire
import decision_book  # noqa: F401  (registers the book validator)

DP = "dp3-worker-clarify"
SUB = "sub-t05e-cold"
root = project / "run"
root.mkdir(parents=True, exist_ok=True)
redactor = decision.credential_redactor(
    extra_secrets=(), env={}, auth_path=project / "no-auth.json"
)
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
    "key": "k-cold",
    "phase": "EXECUTE",
    "task_type": "coding",
    "risk": "low",
    "risk_source": "machine",
    "authority_tier": "P2",
    "task_summary": "copied " + secret + " here",
    "ambiguity": {"kind": "fact", "question": "which file?"},
    "local_candidates": [{"id": "c1", "label": "candidate"}],
}
book = {
    "schema_version": 2,
    "decision_point": DP,
    "state": state,
    "notes": {"evidence": {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[DP]}},
}
backend = decision.FakeBackend(
    [
        decision.BackendOutcome(
            available=True,
            reason=None,
            retryable=False,
            answers={
                "answer_kind": {"value": "fact", "confidence": 0.9},
                "answerable": {"value": 0.9},
                "candidate": {"value": "c1", "confidence": 0.9},
            },
            latency_ms=2,
            detail="",
        )
    ]
)
client = decision.DecisionClient(
    cfg=decision.DecisionConfig(enabled=True, extras={"api_key": secret}),
    backend=backend,
    wire_scope=scope,
)
outcome = dpts.decide_for(
    DP,
    state,
    project,
    client=client,
    archive=False,
    intent="answer",
    observation=dpts.Observation(scope=scope, book=book, submission_id=SUB),
)
sink = root / "evidence.jsonl"
text = sink.read_text(encoding="utf-8") if sink.exists() else ""
print(
    json.dumps(
        {
            "validator": dpts.BOOK_VALIDATOR is not None,
            "status": outcome.status,
            "reason": outcome.escalated_reason,
            "detail": outcome.detail,
            "calls": len(backend.calls),
            "snapshots": [
                row
                for row in (
                    json.loads(line)
                    for line in text.splitlines()
                    if line.strip()
                )
                if row.get("kind") == "book-snapshot"
            ],
            "echoed": bool(secret and secret in text),
        }
    )
)
'''


def test_cold_start_points_and_book_chain_refuses_the_configured_credential(
    tmp_path: pathlib.Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    project = _project(tmp_path)
    script = tmp_path / "cold_start_seam.py"
    script.write_text(_COLD_START_SEAM_SCRIPT, encoding="utf-8", newline="\n")

    proc = _run_child(
        [str(script), str(project), str(pathlib.Path(__file__).resolve().parent), CFG_SECRET],
        home=home,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout.strip().splitlines()[-1])

    assert result["validator"] is True, result
    assert result["reason"] == "input-incomplete", result
    assert "book-secret" in result["detail"], result
    assert CFG_SECRET not in result["detail"], result
    assert result["calls"] == 0, result
    assert result["snapshots"] == [], result
    assert result["echoed"] is False, result


# ---------------------------------------------------------------------------
# API obligation: the known-secret set is an explicit parameter
# ---------------------------------------------------------------------------


def test_the_known_secret_set_is_an_explicit_parameter() -> None:
    assert "redactor" in inspect.signature(books.check_book).parameters
    assert "redactor" in inspect.signature(books.check_book_file).parameters
    assert "redactor" in inspect.signature(books.observation_book_issues).parameters
    assert "redactor" in inspect.signature(dpts.state_unknown_key_issues).parameters
