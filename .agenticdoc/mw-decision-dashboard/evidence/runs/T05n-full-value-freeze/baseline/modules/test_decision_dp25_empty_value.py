"""test_decision_dp25_empty_value.py — card T05h: dp25 ``p0_open: []`` is a value.

The user-confirmed rule (recorded in the card and its 改动历史) is deliberately
narrow:

* ``dp25-signoff-conclusion``'s required ``p0_open`` array uses ``[]`` for "no P0
  is open right now" (``decide_signoff.signoff_state`` writes exactly that when
  the table is absent or every P0 is disabled), so the AC-019 "empty container ==
  unreplaced placeholder" rule must not refuse it;
* the waiver is *field-level*, declared in the registry metadata
  (``STATE_FIELD_DESCRIPTIONS["p0_open"]["empty_is_value"] = True``) and consumed
  by the decision book's placeholder scan — never by hard-coding ``dp25`` in the
  book and never by weakening ``is_placeholder([])`` globally;
* everything else keeps refusing: a missing, ``null`` or wrong-typed
  ``p0_open``, placeholder text *inside* the array, and every other dp's empty
  required array (dp8 ``scope.cross_key_conflicts``, dp15
  ``gate.pending_items``, dp17 ``spec.open_questions``, dp20
  ``stage.open_blockers``). The typed / closed-key / evidence / secret gates are
  untouched, and ``[]`` is not evidence that the facts behind it were verified.

Hermetic: tmp projects, ``decision.FakeBackend``, tmp ``HOME`` / ``USERPROFILE``,
a tmp ``auth.json`` path, credential env vars removed, no network, no real
credentials, no real production archive.
"""

from __future__ import annotations

import json
import os
import pathlib
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
REGISTRY_JSON = PACKAGE_DIR / "decide_registry.json"
GENERATED_TS = (
    PACKAGE_DIR.parent
    / "coding-agent"
    / "src"
    / "extensions"
    / "agent-team-loop"
    / "shared"
    / "decide-registry.generated.ts"
)

DP8 = "dp8-scope-change"
DP15 = "dp15-autopilot-gate"
DP17 = "dp17-spec-lock"
DP20 = "dp20-stage-close"
DP25 = "dp25-signoff-conclusion"
KEY = "k-t05h"
SUB = "sub-t05h"
CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
)
TRUE_ENGINE = dict(transport="timi-decisions", model="jev-latest", confidence_source="api")


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    for name in CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    for name in tuple(os.environ):
        if name.upper().endswith(decision._CRED_ENV_SUFFIXES):
            monkeypatch.delenv(name, raising=False)
    # Never resolve the developer's real home or credential chain.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setattr(
        decision_backends, "_auth_json_path", lambda: tmp_path / "no-auth.json"
    )
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _redactor():
    redactor = decision.credential_redactor(
        extra_secrets=("sk-t05h-0123456789abcdef",),
        env={},
        auth_path=pathlib.Path("no-such-auth.json"),
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


def _dp25_answers() -> dict:
    return {"q-conclusion": {"value": "continue", "confidence": 0.9}}


def _book(dp_id: str, state: dict) -> dict:
    """A book whose evidence covers every required path (``cmd:`` needs no file)."""
    return {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "state": state,
        "notes": {"evidence": {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[dp_id]}},
    }


def _issues(book: dict) -> list[tuple[str, str]]:
    return [(issue.code, issue.path) for issue in books.check_book(book)]


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
    text = (event.get("book") or {}).get("text")
    assert isinstance(text, str) and text, f"no snapshot text in {event}"
    return json.loads(text)


def _signoff_project(tmp_path: pathlib.Path) -> pathlib.Path:
    project = tmp_path / "proj"
    (project / ".agenticdoc" / KEY / "evidence" / "review").mkdir(parents=True)
    return project


def _append_row(project: pathlib.Path, *, dp: str, trigger_id: str, available: bool) -> dict:
    return decide_archive.append_decide(
        decide_signoff.archive_path(project),
        available=available,
        reason=None,
        answer={"x": {"value": 1}} if available else None,
        authority="binding" if available else "human",
        escalated_reason=None,
        acted=available,
        actual_action="steer" if available else None,
        dp=dp,
        key=KEY,
        task_key="task-1",
        trigger_id=trigger_id,
        state={"schema_version": 2, "decision_point": dp},
        questions_version="q-0123abcd",
        mode="auto",
        **TRUE_ENGINE,
    )[0]


def _no_open_p0_state(tmp_path: pathlib.Path, *, table: str) -> tuple[pathlib.Path, dict]:
    """The *real* dp25 producer state for "no P0 open" (no hand-written guess).

    ``table="missing"``: no ``.mw/decide-points.json`` at all (the common case);
    ``table="config"``: a real table with the P0 point explicitly disabled — both
    make ``decide_signoff`` write ``p0_open: []``.
    """
    project = _signoff_project(tmp_path)
    _append_row(project, dp="dp3-worker-clarify", trigger_id="t1", available=True)
    if table == "config":
        path = project / ".mw" / "decide-points.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps({"version": 1, "points": {DP8: {"enabled": False}}}),
            encoding="utf-8",
            newline="\n",
        )
        dpts.clear_points_config_cache()
    else:
        assert table == "missing"
    facts = decide_signoff.collect(project, KEY)
    return project, decide_signoff.signoff_state(facts, KEY)


def _with_p0_open(state: dict, value: object) -> dict:
    """A copy of the real state with one ``p0_open`` defect."""
    payload = dict(state)
    payload["p0_open"] = value
    return payload


# ---------------------------------------------------------------------------
# 1. The registry is the single authority for the field-level rule
# ---------------------------------------------------------------------------


def test_registry_declares_empty_is_value_only_for_p0_open() -> None:
    assert "empty_is_value" in dpts.STATE_FIELD_CONSTRAINT_KEYS, (
        "an undeclared spec key would be refused by _validate_state_field_contract"
    )
    flagged = sorted(
        path
        for path, spec in dpts.STATE_FIELD_DESCRIPTIONS.items()
        if spec.get("empty_is_value")
    )
    assert flagged == ["p0_open"], f"the waiver must stay field-level: {flagged}"
    spec = dpts.STATE_FIELD_DESCRIPTIONS["p0_open"]
    assert spec["empty_is_value"] is True
    assert spec["type"] == "array"
    # T05k N5: the field now declares the same unified array boundary as every
    # other new array (the producer's real ids are shorter/fewer than these).
    assert spec["max_items"] == dpts.STATE_ARRAY_MAX_ITEMS
    assert spec["item_type"] == "string"
    assert spec["item_max_bytes"] == dpts.STATE_ARRAY_ITEM_MAX_BYTES
    assert "enum" not in spec, "the elements are dp ids, not an invented closed set"


def test_no_other_required_empty_array_field_gains_the_waiver() -> None:
    declared = {path for paths in dpts.REQUIRED_STATE_FIELDS.values() for path in paths}
    for path in sorted(declared):
        if path == "p0_open":
            continue
        assert "empty_is_value" not in dpts.STATE_FIELD_DESCRIPTIONS[path], path


def test_global_placeholder_rule_is_not_loosened() -> None:
    """``is_placeholder([])`` is the AC-019 rule every other dp depends on."""
    assert books.is_placeholder([]) is True
    assert books.is_placeholder({}) is True
    assert books.is_placeholder("") is True
    assert books.is_placeholder(None) is True


def test_export_api_carries_the_field_metadata() -> None:
    exported = dpts.snapshot_field_dict("p0_open")
    assert exported["empty_is_value"] is True
    assert exported["type"] == "array"
    assert exported["max_items"] == dpts.STATE_ARRAY_MAX_ITEMS
    assert exported["item_type"] == "string"
    assert exported["item_max_bytes"] == dpts.STATE_ARRAY_ITEM_MAX_BYTES
    conflicts = dpts.snapshot_field_dict("scope.cross_key_conflicts")
    assert "empty_is_value" not in conflicts


# ---------------------------------------------------------------------------
# 2. Other dps' empty required arrays keep their pre-existing refusal
# ---------------------------------------------------------------------------


def _dp8_state(empty: list) -> dict:
    return {
        "schema_version": 2,
        "decision_point": DP8,
        "questions_version": dpts.get_decision_point(DP8).questions_version,
        "scope": {
            "requested_paths": ["packages/multi-workers/x.py"],
            "write_scope": ["packages/multi-workers/x.py"],
            "cross_key_conflicts": empty,
            "requirement_delta": "one new path",
        },
    }


def _dp15_state(empty: list) -> dict:
    return {
        "schema_version": 2,
        "decision_point": DP15,
        "questions_version": dpts.get_decision_point(DP15).questions_version,
        "gate": {
            "kind": "stage-confirm",
            "pending_items": empty,
            "age_minutes": 5,
            "evidence_refs": ["cmd: true"],
        },
    }


def _dp17_state(empty: list) -> dict:
    return {
        "schema_version": 2,
        "decision_point": DP17,
        "questions_version": dpts.get_decision_point(DP17).questions_version,
        "spec": {
            "ac_ids": ["AC-001"],
            "ac_changed": ["AC-001"],
            "open_questions": empty,
        },
    }


def _dp20_state(empty: list) -> dict:
    return {
        "schema_version": 2,
        "decision_point": DP20,
        "questions_version": dpts.get_decision_point(DP20).questions_version,
        "stage": {
            "id": "S1",
            "tasks_done": 1,
            "tasks_total": 2,
            "open_blockers": empty,
            "evidence_refs": ["cmd: true"],
        },
    }


OTHER_EMPTY_ARRAYS = (
    (DP8, _dp8_state, "scope.cross_key_conflicts"),
    (DP15, _dp15_state, "gate.pending_items"),
    (DP17, _dp17_state, "spec.open_questions"),
    (DP20, _dp20_state, "stage.open_blockers"),
)


@pytest.mark.parametrize(
    ("dp_id", "build", "path"), OTHER_EMPTY_ARRAYS, ids=[item[0] for item in OTHER_EMPTY_ARRAYS]
)
def test_other_empty_required_arrays_are_still_refused(
    dp_id: str, build, path: str
) -> None:
    state = build(["real-item"])
    assert dpts.state_field_issues(dp_id, state) == (), dp_id
    assert _issues(_book(dp_id, state)) == [], f"{dp_id}: a filled book must pass"
    empty_state = build([])
    assert dpts.state_field_issues(dp_id, empty_state) == (), (
        f"{dp_id}: an empty array is still a legal *typed* value"
    )
    assert _issues(_book(dp_id, empty_state)) == [("book-placeholder", f"state.{path}")]


# ---------------------------------------------------------------------------
# 3. The real dp25 "no open P0" state is a legal book (the card's goal)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("table", ["missing", "config"])
def test_real_no_open_p0_state_is_a_legal_book(
    table: str, tmp_path: pathlib.Path
) -> None:
    project, state = _no_open_p0_state(tmp_path, table=table)
    assert state["p0_open"] == [], "the real producer writes [] for no open P0"
    assert dpts.state_field_issues(DP25, state) == ()
    assert dpts.state_unknown_key_issues(DP25, state, allow_context=True) == ()
    assert books.check_book(_book(DP25, state), project_dir=project) == []
    assert books.observation_book_issues(_book(DP25, state), project) == ()


def test_real_no_open_p0_state_is_accepted_as_observation_book_material(
    tmp_path: pathlib.Path,
) -> None:
    project, state = _no_open_p0_state(tmp_path, table="missing")
    root = tmp_path / "run"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok(_dp25_answers())])
    book = _book(DP25, state)

    outcome = dpts.decide_for(
        DP25,
        state,
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, book=book, submission_id=SUB),
    )

    assert outcome.status == "suggested", outcome.detail
    assert len(backend.calls) == 1
    assert backend.calls[0]["state"] == state, "the book must carry the state that was sent"
    assert backend.calls[0]["state"]["p0_open"] == []
    snapshots = _of_kind(decision_wire.test_wire_sink(root), "book-snapshot")
    assert len(snapshots) == 1
    assert _snapshot_body(snapshots[0])["state"] == state
    assert outcome.snapshot_ref is not None
    assert snapshots[0]["book_ref"] == outcome.snapshot_ref


def test_scaffold_p0_open_is_legal_but_the_scaffold_is_still_not_signable(
    tmp_path: pathlib.Path,
) -> None:
    scaffold = books.scaffold_book(DP25)
    assert scaffold["state"]["p0_open"] == []
    issues = _issues(scaffold)
    assert ("book-placeholder", "state.p0_open") not in issues, (
        "the editor scaffold writes [] for this field, which the new rule accepts"
    )
    assert issues, "yet the scaffold is still an unfilled book, not an approval"


# ---------------------------------------------------------------------------
# 4. Missing / null / wrong type / placeholder elements still refuse
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("case", "value"),
    [
        ("string", "dp8-scope-change"),
        ("object", {"dp8-scope-change": True}),
        ("integer", 0),
    ],
)
def test_wrong_typed_p0_open_refuses_with_zero_send_and_zero_snapshot(
    case: str, value: object, tmp_path: pathlib.Path
) -> None:
    """A wrong-typed ``p0_open`` is illegal material: refused, never stored.

    The flag only waives the empty-container rule, so the typed gate still owns
    this field: no transport call, no snapshot (the same rule the typed refusal
    path has for every dp).
    """
    project, real = _no_open_p0_state(tmp_path, table="missing")
    state = dict(real)
    state["p0_open"] = value
    book = _book(DP25, state)
    codes = _issues(book)
    assert ("book-state", "state.p0_open") in codes, (case, codes)

    root = tmp_path / f"run-{case}"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok(_dp25_answers())])

    # (a) the plain production/observation path (no book): typed gate.
    direct = dpts.decide_for(
        DP25,
        state,
        project,
        client=_client(backend, _scope(tmp_path / f"run-{case}-direct")),
        archive=False,
        intent="answer",
    )
    assert direct.escalated_reason == "input-incomplete", direct.detail
    assert "p0_open" in direct.detail, direct.detail

    # (b) the book path: the book is refused before the transport too.
    book_outcome = dpts.decide_for(
        DP25,
        state,
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, book=book, submission_id=SUB),
    )
    assert book_outcome.escalated_reason == "input-incomplete", book_outcome.detail
    assert "p0_open" in book_outcome.detail, book_outcome.detail
    assert backend.calls == [], f"{case}: illegal p0_open reached the transport"
    sink = decision_wire.test_wire_sink(root)
    assert _of_kind(sink, "book-snapshot") == [], f"{case}: illegal material was stored"
    assert _of_kind(sink, "decision-end")[0]["book_ref"] is None


ILLEGAL_P0_OPEN_BOUNDS = (
    ("non-string-item", [1]),
    ("too-many", [f"dp{index}-item" for index in range(33)]),
    ("item-too-long", ["x" * 129]),
)


@pytest.mark.parametrize(
    ("case", "value"),
    ILLEGAL_P0_OPEN_BOUNDS,
    ids=[item[0] for item in ILLEGAL_P0_OPEN_BOUNDS],
)
def test_p0_open_array_bounds_refuse_with_zero_send_and_zero_snapshot(
    case: str, value: object, tmp_path: pathlib.Path
) -> None:
    """T05k N5: the field declares item type / item count / item bytes.

    ``[1]``, 33 elements and a 129 B element were all legal before the array
    boundary existed; they are now illegal material at the typed gate, so the
    same zero-send / zero-snapshot rule applies as for the wrong-typed field.
    """
    project, real = _no_open_p0_state(tmp_path, table="missing")
    state = _with_p0_open(real, value)
    issues = dpts.state_field_issues(DP25, state)
    assert issues, (case, issues)
    assert any(
        path == "p0_open" or path.startswith("p0_open[") for path, _detail in issues
    ), (case, issues)
    book_codes = _issues(_book(DP25, state))
    assert any(
        code == "book-state" and (path == "state.p0_open" or path.startswith("state.p0_open["))
        for code, path in book_codes
    ), (case, book_codes)

    root = tmp_path / f"run-bounds-{case}"
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
    assert "p0_open" in outcome.detail, outcome.detail
    assert backend.calls == [], f"{case}: illegal p0_open reached the transport"
    sink = decision_wire.test_wire_sink(root)
    assert _of_kind(sink, "book-snapshot") == [], f"{case}: illegal material was stored"
    assert _of_kind(sink, "decision-end")[0]["book_ref"] is None


@pytest.mark.parametrize("case", ["missing", "null"])
def test_missing_or_null_p0_open_refuses_with_zero_send(
    case: str, tmp_path: pathlib.Path
) -> None:
    """Missing / null is the *required-field* gate, not the new flag.

    Both are refused before the transport with ``input-incomplete``. That gate
    now follows the same material rule as the typed/book refusals (T05k N1): the
    refused candidate is neither sent nor stored as a ``book-snapshot``, and the
    ``decision-end`` row keeps the refusal fact with ``book_ref=None``. The
    required-field *refusal* itself is unchanged, only its ledger material is.
    """
    project, real = _no_open_p0_state(tmp_path, table="missing")
    state = dict(real)
    if case == "missing":
        state.pop("p0_open")
    else:
        state["p0_open"] = None
    # The book itself names the defect (required-field / placeholder).
    codes = _issues(_book(DP25, state))
    assert any(path.startswith("state.p0_open") for _code, path in codes), (case, codes)

    root = tmp_path / f"run-{case}"
    scope = _scope(root)
    backend = decision.FakeBackend([_ok(_dp25_answers())])
    book_outcome = dpts.decide_for(
        DP25,
        state,
        project,
        client=_client(backend, scope),
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, book=_book(DP25, state), submission_id=SUB),
    )
    assert book_outcome.escalated_reason == "input-incomplete", book_outcome.detail
    assert "p0_open" in book_outcome.detail, book_outcome.detail
    assert backend.calls == [], f"{case}: p0_open without a value reached the transport"
    sink = decision_wire.test_wire_sink(root)
    assert _of_kind(sink, "book-snapshot") == [], (
        f"{case}: the refused candidate must not be stored (T05k N1)"
    )
    assert book_outcome.snapshot_ref is None
    end = _of_kind(sink, "decision-end")
    assert len(end) == 1 and end[0]["archive"] in (None, "not-attempted"), end
    assert end[0]["status"] == "escalated", end
    assert end[0]["book_ref"] is None, end


def test_placeholder_text_inside_p0_open_is_refused(tmp_path: pathlib.Path) -> None:
    project, real = _no_open_p0_state(tmp_path, table="missing")
    for value in ("<dp-id>", "", "TBD", -1):
        state = _with_p0_open(real, [value])
        issues = _issues(_book(DP25, state))
        assert ("book-placeholder", "state.p0_open[0]") in issues, (value, issues)
        for issue in books.check_book(_book(DP25, state), project_dir=project):
            if str(value):
                assert str(value) not in issue.detail, (value, issue.detail)

    state = _with_p0_open(real, ["dp8-scope-change"])
    assert _issues(_book(DP25, state)) == [], "a real dp id element is still legal"


def test_empty_p0_open_without_the_flag_still_would_not_be_assumed_verified(
    tmp_path: pathlib.Path,
) -> None:
    """``[]`` means "no open P0"; it is not a claim that the facts were verified.

    Evidence stays mandatory for the field, and the producer's real
    zero-escalation facts stay what they are (``rows_escalated == 0``): the flag
    waives exactly the empty-container placeholder rule, no fact is inferred.
    """
    project, state = _no_open_p0_state(tmp_path, table="missing")
    assert state["rows_escalated"] == 0
    assert state["escalated_reasons"] == [] and state["engine_violations"] == []
    book = _book(DP25, state)
    del book["notes"]["evidence"]["p0_open"]
    issues = _issues(book)
    assert ("book-evidence", "notes.evidence.p0_open") in issues, issues
    assert ("book-placeholder", "state.p0_open") not in issues
    assert dpts.state_field_issues(DP25, state) == ()
