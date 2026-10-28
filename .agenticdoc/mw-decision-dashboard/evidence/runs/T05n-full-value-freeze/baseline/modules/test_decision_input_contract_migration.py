"""test_decision_input_contract_migration.py — card T05c: dp25 single authority.

T05b kept the live ``dp25-signoff-conclusion`` producer facts
(``rows_escalated`` / ``escalated_reasons`` / ``engine_violations``) in a
temporary side table (``LEGACY_PRODUCER_STATE_PATHS``) plus an
``allow_paths`` seam: the observation seam accepted them while the decision
book still refused them — two authorities for one state. This module pins the
migration to a single typed contract and the four safety gaps the T05b review
opened:

* **migration** — the three real ``decide_signoff.signoff_state`` facts are
  declared optional fields (integer ``>= 0`` / ``array[string]`` with the
  existing contract caps), the side table and ``allow_paths`` are gone, and the
  real producer state passes the shared typed/closed-key gates *and* can be the
  material of a legal book with no exemption;
* **N1** — the typed/unknown-key refusal path writes **no** snapshot (the
  oversize refusal intentionally keeps the truncated candidate: documented here,
  not conflated);
* **N2** — the three identity values are checked against the registry/schema by
  one pure check shared with the book (no second version authority);
* **N3** — the enum refusal detail names only the path/type/allowed set, never
  the offending value (a free-text or secret-shaped value is not echoed);
* **N4** — ``register_book_validator`` is repeatable for the same registration
  and refuses an illegal or arbitrary one; the cold-start (points only) refusal
  and the points+book acceptance are verified in isolated interpreters.

Hermetic: tmp projects, ``decision.FakeBackend``, no network, no credentials, no
real model. The dp25 fixtures come from the real producer
(``decide_signoff.collect`` over an ``decide_archive`` fixture), never from a
hand-written guess.
"""

from __future__ import annotations

import dataclasses
import inspect
import json
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decide_archive  # noqa: E402
import decide_signoff  # noqa: E402
import decision  # noqa: E402
import decision_backends  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire  # noqa: E402

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]

DP3 = "dp3-worker-clarify"
DP4 = "dp4-failure-handling"
DP5 = "dp5-test-triage"
DP25 = "dp25-signoff-conclusion"
KEY = "k-t05c"
SUB = "sub-t05c"
TEST_SECRET = "sk-t05c-migration-0123456789abcdef"
CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
)
TRUE_ENGINE = dict(transport="timi-decisions", model="jev-latest", confidence_source="api")
DP25_OPTIONAL = ("rows_escalated", "escalated_reasons", "engine_violations")
IDENTITY = ("schema_version", "decision_point", "questions_version")


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    for name in CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # The book gate resolves the production timi credential chain; the fixture
    # must never read the developer's real ~/.pi/agent/auth.json.
    monkeypatch.setattr(
        decision_backends, "_auth_json_path", lambda: tmp_path / "no-auth.json"
    )
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _write_decide(project: pathlib.Path) -> pathlib.Path:
    path = project / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"enabled": True}), encoding="utf-8", newline="\n")
    return path


def _enable_all(project: pathlib.Path) -> None:
    path = project / ".mw" / "decide-points.json"
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
        ),
        encoding="utf-8",
        newline="\n",
    )
    dpts.clear_points_config_cache()


def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide(project)
    _enable_all(project)
    return project


def _redactor():
    redactor = decision.credential_redactor(
        extra_secrets=(TEST_SECRET,), env={}, auth_path=pathlib.Path("no-such-auth.json")
    )
    assert redactor is not None, "the side ledger module must be importable in tests"
    return redactor


def _scope(root: pathlib.Path):
    return decision_wire.test_scope(
        root,
        project_id=decision_wire.project_id_for(root),
        submission_id=SUB,
        redact=_redactor(),
        evidence_path=root / "evidence.jsonl",
        warn=lambda line: None,
    )


def _client(backend, scope) -> decision.DecisionClient:
    return decision.DecisionClient(
        cfg=decision.DecisionConfig(enabled=True), backend=backend, wire_scope=scope
    )


def _ok(answers: dict) -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=True,
        reason=None,
        retryable=False,
        answers=answers,
        latency_ms=2,
        detail="",
    )


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


def _snapshot_body(event: dict) -> dict:
    """The captured snapshot document (``book.text`` is the redacted JSON)."""
    text = (event.get("book") or {}).get("text")
    assert isinstance(text, str) and text, f"no snapshot text in {event}"
    return json.loads(text)


def _dp4_state(**overrides) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP4,
        "questions_version": dpts.get_decision_point(DP4).questions_version,
        "failure": {
            "kind": "transient",
            "attempt": 1,
            "limit": 2,
            "artifact_present": False,
        },
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


def _book(dp_id: str, state: dict) -> dict:
    """A book whose evidence covers every required path (``cmd:`` needs no file)."""
    return {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "state": state,
        "notes": {"evidence": {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[dp_id]}},
    }


def _signoff_project(tmp_path: pathlib.Path) -> pathlib.Path:
    project = tmp_path / "proj"
    (project / ".agenticdoc" / KEY / "evidence" / "review").mkdir(parents=True)
    return project


def _append_row(
    project: pathlib.Path,
    *,
    dp: str,
    trigger_id: str,
    available: bool,
    authority: str,
    escalated_reason: str | None = None,
    reason: str | None = None,
    engine: dict | None = None,
) -> dict:
    return decide_archive.append_decide(
        decide_signoff.archive_path(project),
        available=available,
        reason=reason,
        answer={"x": {"value": 1}} if available else None,
        authority=authority,
        escalated_reason=escalated_reason,
        acted=available,
        actual_action="steer" if available else None,
        dp=dp,
        key=KEY,
        task_key="task-1",
        trigger_id=trigger_id,
        state={"schema_version": 2, "decision_point": dp},
        questions_version="q-0123abcd",
        mode="auto",
        **(TRUE_ENGINE if engine is None else engine),
    )[0]


def real_signoff_state(tmp_path: pathlib.Path) -> tuple[pathlib.Path, dict]:
    """The *real* dp25 production state: ``collect`` over a real archive fixture.

    One true-engine row (``available``) and one escalated row on a different
    engine, so all three migrated facts carry real values
    (``rows_escalated=1``, ``escalated_reasons=["p0"]``,
    ``engine_violations=["other/m2/unknown"]``).
    """
    project = _signoff_project(tmp_path)
    _append_row(project, dp="dp3-worker-clarify", trigger_id="t1", available=True, authority="binding")
    _append_row(
        project,
        dp=DP4,
        trigger_id="t2",
        available=False,
        authority="human",
        escalated_reason="p0",
        reason="timeout",
        engine=dict(transport="other", model="m2", confidence_source="unknown"),
    )
    path = project / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "points": {"dp8-scope-change": {"enabled": True}}}),
        encoding="utf-8",
        newline="\n",
    )
    dpts.clear_points_config_cache()
    facts = decide_signoff.collect(project, KEY)
    return project, decide_signoff.signoff_state(facts, KEY)


def _dp25_answers() -> dict:
    return {"q-conclusion": {"value": "continue", "confidence": 0.9}}


# ---------------------------------------------------------------------------
# 1. dp25: the three real producer facts are a typed optional declaration
# ---------------------------------------------------------------------------


def test_dp25_producer_facts_are_declared_optional_fields() -> None:
    assert dpts.OPTIONAL_STATE_FIELDS[DP25] == DP25_OPTIONAL
    assert not hasattr(dpts, "LEGACY_PRODUCER_STATE_PATHS"), (
        "the temporary side table must be gone (one authority, not a seam/book split)"
    )
    counter = dpts.STATE_FIELD_DESCRIPTIONS["rows_escalated"]
    assert counter["type"] == "integer" and counter["min_value"] == 0
    for path in ("escalated_reasons", "engine_violations"):
        spec = dpts.STATE_FIELD_DESCRIPTIONS[path]
        assert spec["type"] == "array", path
        assert spec["item_type"] == "string", path
        assert spec["max_items"] == dpts.STATE_ARRAY_MAX_ITEMS, path
        assert spec["item_max_bytes"] == dpts.STATE_ARRAY_ITEM_MAX_BYTES, path


def test_unknown_key_check_has_no_string_allowance_parameter() -> None:
    """``allow_paths`` was the seam-only widening; the declaration replaces it."""
    parameters = inspect.signature(dpts.state_unknown_key_issues).parameters
    assert "allow_paths" not in parameters


def test_real_signoff_state_passes_the_shared_gates_without_an_exemption(
    tmp_path: pathlib.Path,
) -> None:
    _, state = real_signoff_state(tmp_path)
    # The real values are the producer's, not a fixture guess.
    assert state["rows_escalated"] == 1
    assert state["escalated_reasons"] == ["p0"]
    assert state["engine_violations"] == ["other/m2/unknown"]
    assert dpts.state_field_issues(DP25, state) == ()
    assert dpts.state_unknown_key_issues(DP25, state, allow_context=True) == ()


def test_real_signoff_state_is_a_legal_decision_book(tmp_path: pathlib.Path) -> None:
    project, state = real_signoff_state(tmp_path)
    assert books.check_book(_book(DP25, state), project_dir=project) == []


def test_empty_p0_open_is_a_legal_book_under_the_confirmed_field_rule(
    tmp_path: pathlib.Path,
) -> None:
    """No escalation and no open P0: the *common* real state is a legal book.

    T05c recorded the opposite behaviour (``('book-placeholder',
    'state.p0_open')``): AC-019's "empty container == unreplaced placeholder"
    rule hit dp25's *required* ``p0_open``, while the producer deliberately
    writes ``[]`` for "no P0 open", so a real book could not exist. The
    user-confirmed rule (card T05h) declares ``empty_is_value`` for exactly this
    field and the book's placeholder scan consumes it, so the producer's own
    value is accepted while the rule stays unchanged for every other dp (the
    migrated optional arrays were never placeholder-checked either).
    """
    project = _signoff_project(tmp_path)
    _append_row(project, dp="dp3-worker-clarify", trigger_id="t1", available=True, authority="binding")
    dpts.clear_points_config_cache()
    state = decide_signoff.signoff_state(decide_signoff.collect(project, KEY), KEY)
    assert state["p0_open"] == []
    assert state["escalated_reasons"] == [] and state["engine_violations"] == []
    assert dpts.state_field_issues(DP25, state) == ()
    assert dpts.state_unknown_key_issues(DP25, state, allow_context=True) == ()
    assert dpts.STATE_FIELD_DESCRIPTIONS["p0_open"]["empty_is_value"] is True
    assert books.check_book(_book(DP25, state), project_dir=project) == []


def test_real_signoff_state_is_accepted_as_observation_book_material(
    tmp_path: pathlib.Path,
) -> None:
    project, state = real_signoff_state(tmp_path)
    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok(_dp25_answers())])

    outcome = dpts.decide_for(
        DP25,
        state,
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, book=_book(DP25, state), submission_id=SUB),
    )

    assert outcome.status == "suggested", outcome.detail
    assert len(backend.calls) == 1
    assert backend.calls[0]["state"] == state, "the book must carry the state that was sent"
    snapshots = _of_kind(decision_wire.test_wire_sink(root), "book-snapshot")
    assert len(snapshots) == 1
    assert _snapshot_body(snapshots[0])["state"] == state
    assert outcome.snapshot_ref is not None
    assert snapshots[0]["book_ref"] == outcome.snapshot_ref


@pytest.mark.parametrize(
    ("path", "value"),
    [
        ("rows_escalated", -1),
        ("rows_escalated", "3"),
        ("rows_escalated", True),
        ("escalated_reasons", "p0"),
        ("escalated_reasons", [1]),
        ("escalated_reasons", [f"reason_{index}" for index in range(33)]),
        ("escalated_reasons", ["x" * 129]),
        ("engine_violations", {"a": 1}),
        ("engine_violations", [None]),
    ],
)
def test_real_dp25_state_refuses_an_illegal_optional_value_with_zero_send(
    path: str, value: object, tmp_path: pathlib.Path
) -> None:
    project, state = real_signoff_state(tmp_path)
    state[path] = value
    issues = dpts.state_field_issues(DP25, state)
    assert issues, (path, value)
    assert any(issue_path == path or issue_path.startswith(path + "[") for issue_path, _ in issues)
    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok(_dp25_answers())])

    outcome = dpts.decide_for(
        DP25,
        state,
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, submission_id=SUB),
    )

    assert outcome.escalated_reason == "input-incomplete", outcome.detail
    assert path in outcome.detail, outcome.detail
    assert backend.calls == [], "illegal dp25 material reached the transport"
    assert _of_kind(decision_wire.test_wire_sink(root), "book-snapshot") == []
    ends = _of_kind(decision_wire.test_wire_sink(root), "decision-end")
    assert len(ends) == 1 and ends[0]["book_ref"] is None


def test_dp25_book_carrying_a_secret_is_refused_with_zero_send(
    tmp_path: pathlib.Path,
) -> None:
    project, state = real_signoff_state(tmp_path)
    state["key"] = f"key {TEST_SECRET}"
    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok(_dp25_answers())])

    outcome = dpts.decide_for(
        DP25,
        state,
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, book=_book(DP25, state), submission_id=SUB),
    )

    assert outcome.escalated_reason == "input-incomplete", outcome.detail
    assert "book-secret" in outcome.detail, outcome.detail
    assert backend.calls == []
    sink = decision_wire.test_wire_sink(root)
    assert _of_kind(sink, "book-snapshot") == []
    assert TEST_SECRET not in sink.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# 2. N1: refused material is never snapshotted (typed vs oversize difference)
# ---------------------------------------------------------------------------


def test_typed_refusal_writes_no_snapshot_with_a_real_scope(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok({})])
    state = _dp4_state()
    state["failure"] = {**state["failure"], "kind": "boom"}

    outcome = dpts.decide_for(
        DP4,
        state,
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, submission_id=SUB),
    )

    assert outcome.escalated_reason == "input-incomplete"
    assert backend.calls == []
    sink = decision_wire.test_wire_sink(root)
    assert _of_kind(sink, "book-snapshot") == [], "a typed refusal must not store the material"
    ends = _of_kind(sink, "decision-end")
    assert len(ends) == 1 and ends[0]["book_ref"] is None


def test_unknown_key_refusal_writes_no_snapshot_with_a_real_scope(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok({})])
    state = _dp4_state()
    state["failure"] = {**state["failure"], "expected_action": "retry"}

    outcome = dpts.decide_for(
        DP4,
        state,
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, submission_id=SUB),
    )

    assert outcome.escalated_reason == "input-incomplete"
    assert backend.calls == []
    sink = decision_wire.test_wire_sink(root)
    assert _of_kind(sink, "book-snapshot") == []
    assert _of_kind(sink, "decision-end")[0]["book_ref"] is None


def test_oversize_refusal_keeps_the_truncated_candidate_on_purpose(
    tmp_path: pathlib.Path,
) -> None:
    """Deliberate difference from a typed refusal: the state is *legal*.

    An oversize state is complete and legal, it just cannot be sent whole, so
    the post-truncation candidate is snapshotted (a human can see what *would*
    have been sent). A typed/undeclared-key refusal is illegal material and is
    never stored. The two must not be described by one blanket rule.
    """
    project = _project(tmp_path)
    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok({})])
    state = _dp5_state()
    # Legal per its own contract (32 items, 88 B each) but over the 2000 B budget.
    state["test"] = {
        **state["test"],
        "failed_cases": [f"case_{index:02d}-" + "x" * 80 for index in range(32)],
    }
    assert dpts.state_field_issues(DP5, state) == ()

    outcome = dpts.decide_for(
        DP5,
        state,
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, submission_id=SUB),
    )

    assert outcome.escalated_reason == "input-oversize", outcome.detail
    assert backend.calls == []
    sink = decision_wire.test_wire_sink(root)
    snapshots = _of_kind(sink, "book-snapshot")
    assert len(snapshots) == 1, "the refused-for-size candidate is kept for the human"
    assert _snapshot_body(snapshots[0])["kind"] == "input-state"
    assert _of_kind(sink, "decision-end")[0]["book_ref"] == outcome.snapshot_ref


# ---------------------------------------------------------------------------
# 3. N2: one identity check, shared by the seam and the book
# ---------------------------------------------------------------------------


def test_state_identity_issues_compares_with_the_registry_and_schema() -> None:
    assert dpts.STATE_SCHEMA_VERSION == 2
    assert dpts.state_identity_issues(DP4, _dp4_state()) == ()
    assert dpts.state_identity_issues(DP4, {}) == (), "missing identity keeps builder defaults"

    cases = (
        ("schema_version", 1),
        ("schema_version", "2"),
        ("schema_version", True),
        ("decision_point", DP5),
        ("questions_version", "q-deadbeef"),
        ("questions_version", 7),
    )
    for field, value in cases:
        state = _dp4_state()
        state[field] = value
        assert field in dict(dpts.state_identity_issues(DP4, state)), (field, value)

    arbitrary = _dp4_state()
    arbitrary["questions_version"] = TEST_SECRET
    detail = dict(dpts.state_identity_issues(DP4, arbitrary))["questions_version"]
    assert TEST_SECRET not in detail, "an arbitrary identity value is never echoed"
    assert dpts.get_decision_point(DP4).questions_version in detail, (
        "the registry value is a closed-set fact and may be named"
    )


@pytest.mark.parametrize("field", IDENTITY)
def test_seam_refuses_a_wrong_identity_value_with_zero_send(
    field: str, tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok({"failure_action": {"value": "retry"}})])
    state = _dp4_state()
    state[field] = {"schema_version": 1, "decision_point": DP5, "questions_version": "q-deadbeef"}[
        field
    ]
    dp_point = dpts.get_decision_point(DP4)
    monkeypatch.setitem(
        dpts._REGISTRY_BY_ID, DP4, dataclasses.replace(dp_point, build_state=lambda trigger: dict(state))
    )

    outcome = dpts.decide_for(
        DP4,
        {"key": "k"},
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, submission_id=SUB),
    )

    assert outcome.escalated_reason == "input-incomplete", outcome.detail
    assert field in outcome.detail, outcome.detail
    assert backend.calls == []
    sink = decision_wire.test_wire_sink(root)
    assert _of_kind(sink, "book-snapshot") == []
    assert _of_kind(sink, "decision-end")[0]["book_ref"] is None


def test_dp25_state_without_identity_values_still_passes_the_gate(
    tmp_path: pathlib.Path,
) -> None:
    """dp25's required set is business-only: a missing identity keeps builder defaults."""
    project, state = real_signoff_state(tmp_path)
    for field in IDENTITY:
        state.pop(field)
    assert dpts.state_identity_issues(DP25, state) == ()
    assert dpts.state_unknown_key_issues(DP25, state, allow_context=True) == ()
    backend = decision.FakeBackend([_ok(_dp25_answers())])

    outcome = dpts.decide_for(
        DP25, state, project, client=_client(backend, None), archive=False, intent="answer"
    )

    assert outcome.status == "suggested", outcome.detail
    assert len(backend.calls) == 1, "a missing identity is not a refusal"
    assert "schema_version" in backend.calls[0]["state"], "the builder normalizes identity"


def test_book_and_seam_use_the_same_identity_verdict(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    state = _dp4_state()
    state["schema_version"] = 1
    state["questions_version"] = "q-deadbeef"
    book_issues = [
        (issue.path, issue.detail)
        for issue in books.check_book(_book(DP4, state), project_dir=project)
        if issue.path.removeprefix("state.") in IDENTITY
    ]
    shared = [
        (f"state.{path}", detail) for path, detail in dpts.state_identity_issues(DP4, state)
    ]
    assert book_issues == shared, "the book must not keep its own identity authority"


def test_state_field_issues_stays_one_defect_one_code_for_identity() -> None:
    """Identity is checked once per call, not twice through two checkers."""
    state = _dp4_state()
    state["questions_version"] = "q-deadbeef"
    fields = [path for path, _ in dpts.state_field_issues(DP4, state)]
    identity = [path for path, _ in dpts.state_identity_issues(DP4, state)]
    assert identity == ["questions_version"]
    assert "questions_version" not in fields


# ---------------------------------------------------------------------------
# 4. N3: enum refusal detail is a safe closed set (no value echo)
# ---------------------------------------------------------------------------


def test_enum_refusal_detail_does_not_echo_a_secret_or_free_text() -> None:
    for bad in (TEST_SECRET, "customer password hunter2 should not be echoed at all"):
        state = _dp4_state()
        state["failure"] = {**state["failure"], "kind": bad}
        issues = dpts.state_field_issues(DP4, state)
        assert len(issues) == 1
        path, detail = issues[0]
        assert path == "failure.kind"
        assert "must be one of" in detail
        assert "transient" in detail, "the allowed set stays in the detail (a closed set)"
        assert bad not in detail, "the offending free-text value must never be echoed"


def test_enum_refusal_through_the_seam_does_not_echo_the_value(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    backend = decision.FakeBackend([_ok({})])
    state = _dp4_state()
    state["failure"] = {**state["failure"], "kind": TEST_SECRET}

    outcome = dpts.decide_for(
        DP4, state, project, client=_client(backend, None), archive=False, intent="answer"
    )

    assert outcome.escalated_reason == "input-incomplete"
    assert "failure.kind" in outcome.detail
    assert TEST_SECRET not in outcome.detail
    assert backend.calls == []


# ---------------------------------------------------------------------------
# 5. N4: one immutable, repeatable book-validator registration
# ---------------------------------------------------------------------------


def test_register_book_validator_rejects_an_illegal_validator() -> None:
    registered = dpts.BOOK_VALIDATOR
    assert registered is not None, "importing decision_book registers the validator"
    for illegal in (None, 7, "books", object()):
        with pytest.raises((TypeError, ValueError)):
            dpts.register_book_validator(illegal)
        assert dpts.BOOK_VALIDATOR is registered


def test_register_book_validator_is_repeatable_for_the_same_registration() -> None:
    registered = dpts.BOOK_VALIDATOR
    assert registered is not None
    dpts.register_book_validator(registered)
    assert dpts.BOOK_VALIDATOR is registered


def test_register_book_validator_refuses_an_arbitrary_override() -> None:
    registered = dpts.BOOK_VALIDATOR
    assert registered is not None

    def other(book, project_dir):
        return ()

    with pytest.raises((TypeError, ValueError)):
        dpts.register_book_validator(other)
    assert dpts.BOOK_VALIDATOR is registered, "a silent replacement would change the book authority"


_COLD_START_SCRIPT = r'''
import json
import pathlib
import sys

mode, project_arg, package_arg = sys.argv[1:4]
project = pathlib.Path(project_arg)
sys.path.insert(0, package_arg)

import decision
import decision_points as dpts
import decision_wire

DP = "dp4-failure-handling"
SUB = "sub-t05c-cold"

project.mkdir(parents=True, exist_ok=True)
(project / ".mw").mkdir(parents=True, exist_ok=True)
(project / ".mw" / "decide.json").write_text(json.dumps({"enabled": True}), encoding="utf-8")
(project / ".mw" / "decide-points.json").write_text(
    json.dumps({"version": 1, "points": {DP: {"tier": "P1", "enabled": True, "mode": "auto"}}}),
    encoding="utf-8",
)
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
    "failure": {"kind": "transient", "attempt": 1, "limit": 2, "artifact_present": False},
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
            answers={"failure_action": {"value": "retry", "confidence": 0.9}},
            latency_ms=2,
            detail="",
        )
    ]
)
client = decision.DecisionClient(
    cfg=decision.DecisionConfig(enabled=True), backend=backend, wire_scope=scope
)
if mode == "with-book":
    import decision_book  # noqa: F401  (registers the validator at import time)
outcome = dpts.decide_for(
    DP,
    state,
    project,
    client=client,
    archive=False,
    intent="answer",
    observation=dpts.Observation(scope=scope, book=book, submission_id=SUB),
)
print(
    json.dumps(
        {
            "book_validator": dpts.BOOK_VALIDATOR is not None,
            "status": outcome.status,
            "reason": outcome.escalated_reason,
            "detail": outcome.detail,
            "calls": len(backend.calls),
        }
    )
)
'''


def _run_cold_start(tmp_path: pathlib.Path, mode: str) -> dict:
    script = tmp_path / f"cold_start_{mode}.py"
    script.write_text(_COLD_START_SCRIPT, encoding="utf-8", newline="\n")
    project = tmp_path / f"project-{mode}"
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    env = {name: value for name, value in os.environ.items()}
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    completed = subprocess.run(
        [sys.executable, str(script), mode, str(project), str(PACKAGE_DIR)],
        cwd=str(PACKAGE_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    return json.loads(completed.stdout.strip().splitlines()[-1])


def test_cold_start_with_points_only_refuses_a_legal_book(tmp_path: pathlib.Path) -> None:
    result = _run_cold_start(tmp_path, "points-only")
    assert result["book_validator"] is False
    assert result["reason"] == "input-incomplete", result
    assert "no book validator is registered" in result["detail"]
    assert result["calls"] == 0


def test_cold_start_with_points_and_book_accepts_the_same_legal_book(
    tmp_path: pathlib.Path,
) -> None:
    result = _run_cold_start(tmp_path, "with-book")
    assert result["book_validator"] is True
    assert result["status"] == "suggested", result
    assert result["reason"] is None, result
    assert result["calls"] == 1


# ---------------------------------------------------------------------------
# 6. Export surface: the declaration is derived, the artifacts agree
# ---------------------------------------------------------------------------


def test_exports_carry_the_dp25_optional_declaration() -> None:
    doc = json.loads((PACKAGE_DIR / "decide_registry.json").read_text(encoding="utf-8"))
    by_id = {point["id"]: point for point in doc["points"]}
    exported = [field["name"] for field in by_id[DP25]["optional_state_fields"]]
    assert exported == list(DP25_OPTIONAL)
    assert [field["name"] for field in by_id["dp2-checkpoint-split"]["optional_state_fields"]] == list(
        dpts.OPTIONAL_STATE_FIELDS["dp2-checkpoint-split"]
    )
    assert len(by_id) == dpts.EXPECTED_DP_COUNT

    ts_path = (
        REPO_ROOT
        / "packages"
        / "coding-agent"
        / "src"
        / "extensions"
        / "agent-team-loop"
        / "shared"
        / "decide-registry.generated.ts"
    )
    text = ts_path.read_text(encoding="utf-8")
    assert '"dp25-signoff-conclusion": {' in text
    for path in DP25_OPTIONAL:
        assert f'name: "{path}"' in text, path
    assert "minValue: 0" in text


def test_dp25_manifest_is_unchanged_by_the_optional_declaration() -> None:
    """The book template only scaffolds dp3/dp6: the migration derives nothing there."""
    template = json.loads((PACKAGE_DIR / "decide_book_template.json").read_text(encoding="utf-8"))
    assert set(template["books"]) == {"dp3-worker-clarify", "dp6-qg-verdict"}
    for dp_id, book in template["books"].items():
        assert book == books.scaffold_book(dp_id), dp_id


# ---------------------------------------------------------------------------
# 7. Wire-owned finding: identical submissions share one snapshot reference
# ---------------------------------------------------------------------------


def test_identical_observations_in_one_scope_share_a_snapshot_ref(
    tmp_path: pathlib.Path,
) -> None:
    """Documented behaviour, not a wire fix (``book_ref`` uniqueness is wire-owned).

    ``_snapshot_ref`` is derived from content, so two identical calls inside one
    scope append two ``book-snapshot`` rows that claim the same ``book_ref``.
    T06 flagged uniqueness as an open question; the fix belongs to the wire
    owner, so this test only pins what the seam does today.
    """
    project = _project(tmp_path)
    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend(
        [_ok({"failure_action": {"value": "retry"}}), _ok({"failure_action": {"value": "retry"}})]
    )
    client = _client(backend, scope)

    trigger = dpts.Trigger(trigger_id="t-dup", data=_dp4_state())
    first = dpts.decide_for(
        DP4, trigger, project, client=client, archive=False, intent="answer",
        observation=dpts.Observation(scope=scope, submission_id=SUB),
    )
    second = dpts.decide_for(
        DP4, trigger, project, client=client, archive=False, intent="answer",
        observation=dpts.Observation(scope=scope, submission_id=SUB),
    )

    assert first.snapshot_ref is not None and second.snapshot_ref is not None
    snapshots = _of_kind(decision_wire.test_wire_sink(root), "book-snapshot")
    assert len(snapshots) == 2
    assert snapshots[0]["book_ref"] == snapshots[1]["book_ref"] == first.snapshot_ref


# ---------------------------------------------------------------------------
# 8. P0 (T05d): the book-secret gate reaches array elements, nested values and
#    object keys, without changing the typed/closed flatten contract
# ---------------------------------------------------------------------------

#: A legal dp5 item: 105 B, under the declared ``item_max_bytes`` (128 B), and
#: plain text (nothing a credential rule recognises).
LONG_PLAIN_ITEM = "case_" + "x" * 100
ENV_SECRET = "t05d-env-known-0123456789abcdef"


def _dp3_state(**overrides) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP3,
        "questions_version": dpts.get_decision_point(DP3).questions_version,
        "key": "k-t05d",
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


def _secret_issues(issues) -> list[tuple[str, str]]:
    return [(issue.code, issue.path) for issue in issues if issue.code == "book-secret"]


@pytest.mark.parametrize(
    ("path", "secret"),
    [
        ("escalated_reasons", f"escalated for {TEST_SECRET}"),
        ("engine_violations", "other/m2/unknown Bearer t05d-bearer-token-0123456789"),
    ],
)
def test_real_dp25_arrays_are_scanned_and_a_secret_refuses_with_zero_send(
    path: str, secret: str, tmp_path: pathlib.Path
) -> None:
    """The P0: both migrated dp25 arrays are real send material.

    The secret sits *inside* a legal array element (right type, right size), so
    only a scan that walks array elements can see it. Refusal must happen before
    the transport and must store neither a snapshot nor the credential.
    """
    project, state = real_signoff_state(tmp_path)
    state[path] = [secret]
    book = _book(DP25, state)
    assert dpts.state_field_issues(DP25, state) == (), "the array shape itself is legal"

    issues = books.check_book(book, project_dir=project)
    assert _secret_issues(issues) == [("book-secret", f"state.{path}[0]")], (
        path,
        [(issue.code, issue.path) for issue in issues],
    )
    for issue in issues:
        assert secret not in issue.detail and secret not in issue.path

    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok(_dp25_answers())])
    outcome = dpts.decide_for(
        DP25,
        state,
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, book=book, submission_id=SUB),
    )

    assert outcome.escalated_reason == "input-incomplete", outcome.detail
    assert "book-secret" in outcome.detail, outcome.detail
    assert f"state.{path}[0]" in outcome.detail, outcome.detail
    assert secret not in outcome.detail
    assert backend.calls == [], "a credential inside an array reached the transport"
    sink = decision_wire.test_wire_sink(root)
    assert _of_kind(sink, "book-snapshot") == []
    assert secret not in sink.read_text(encoding="utf-8")


@pytest.mark.parametrize(
    ("case", "item", "env"),
    [
        ("sk-pattern", f"use {TEST_SECRET} here", None),
        ("bearer-pattern", "call with Bearer t05d-bearer-0123456789abcdef", None),
        ("env-known-value", f"copied {ENV_SECRET}", ("T05D_PROBE_API_KEY", ENV_SECRET)),
    ],
)
def test_array_scan_reuses_the_existing_three_recognition_classes(
    case: str,
    item: str,
    env: tuple[str, str] | None,
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Coverage is exactly the reused redactor: env *_API_KEY known values, Bearer, sk-.

    Unknown secrets that match none of the three are *not* claimed to be caught.
    """
    if env is not None:
        monkeypatch.setenv(*env)
    project = _project(tmp_path)
    state = _dp5_state()
    state["test"] = {**state["test"], "failed_cases": ["case_a", item]}
    assert dpts.state_field_issues(DP5, state) == (), case

    issues = books.check_book(_book(DP5, state), project_dir=project)
    assert _secret_issues(issues) == [("book-secret", "state.test.failed_cases[1]")], (
        case,
        [(issue.code, issue.path) for issue in issues],
    )
    for issue in issues:
        assert item not in issue.detail


def test_nested_objects_and_arrays_of_arrays_inside_a_legal_array_are_scanned(
    tmp_path: pathlib.Path,
) -> None:
    """dp3 ``local_candidates`` is a legal array with no declared element type.

    A nested object and a nested array are therefore legal send material, and
    the scan must recurse into both (array-of-array included).
    """
    project = _project(tmp_path)
    state = _dp3_state(
        local_candidates=[
            [f"nested list {TEST_SECRET}"],
            {"label": "wrapped Bearer t05d-nested-token-0123456789abcdef"},
        ]
    )
    book = _book(DP3, state)
    assert dpts.state_field_issues(DP3, state) == ()

    issues = books.check_book(book, project_dir=project)
    assert _secret_issues(issues) == [
        ("book-secret", "state.local_candidates[0][0]"),
        ("book-secret", "state.local_candidates[1].label"),
    ], [(issue.code, issue.path) for issue in issues]

    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok(_dp25_answers())])
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
    assert "book-secret" in outcome.detail, outcome.detail
    assert backend.calls == []
    assert _of_kind(decision_wire.test_wire_sink(root), "book-snapshot") == []


def test_a_credential_in_a_legal_array_item_key_is_scanned_without_echo(
    tmp_path: pathlib.Path,
) -> None:
    """Object keys reach the sent body; item keys under a legal array are unchecked.

    The closed-key gate flattens arrays as leaves, so an item key is *not* seen
    by it -- the secret scan is the only gate that can and must look at it. The
    refusal path must not echo the key text or the credential.
    """
    project = _project(tmp_path)
    state = _dp3_state(
        local_candidates=[{"id": "c1", "label": "candidate", f"note-{TEST_SECRET}": "x"}]
    )
    assert dpts.state_field_issues(DP3, state) == ()
    assert dpts.state_unknown_key_issues(DP3, state) == ()

    issues = books.check_book(_book(DP3, state), project_dir=project)
    assert _secret_issues(issues) == [("book-secret", "state.local_candidates[0].<key>")], (
        [(issue.code, issue.path) for issue in issues]
    )
    for issue in issues:
        assert TEST_SECRET not in issue.path and TEST_SECRET not in issue.detail
        assert "note-" not in issue.path, "the key text itself is not echoed either"


def test_legal_arrays_and_long_plain_items_still_pass_and_a_full_book_still_sends(
    tmp_path: pathlib.Path,
) -> None:
    """GREEN guard: the fix must not refuse legal arrays or a legal complete book."""
    project = _project(tmp_path)
    state = _dp5_state()
    state["test"] = {
        **state["test"],
        "failed_cases": [LONG_PLAIN_ITEM],
        "baseline_cases": ["case_" + "y" * 60] * 3,
    }
    book = _book(DP5, state)
    assert books.check_book(book, project_dir=project) == []

    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok({"test_category": {"value": "regression"}})])
    outcome = dpts.decide_for(
        DP5,
        state,
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, book=book, submission_id=SUB),
    )

    assert outcome.status == "suggested", outcome.detail
    assert len(backend.calls) == 1
    assert len(_of_kind(decision_wire.test_wire_sink(root), "book-snapshot")) == 1


def test_secret_scan_is_separate_from_the_typed_closed_flatten_contract() -> None:
    """``_flatten`` keeps treating arrays as leaves on both surfaces (T05c)."""
    state = {"a": ["x"], "b": {"c": [1]}, "d": {}}
    expected = {"a": ["x"], "b.c": [1], "d": {}}
    assert books._flatten(state) == expected
    assert dpts._flatten_state(state) == expected
