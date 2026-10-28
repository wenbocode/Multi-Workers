"""test_decision_dp25_empty_value.py — dp25's empty arrays are values.

T01 replaced the retired dp25 counter shape (``p0_open`` / ``rows_*`` /
``chain_ok``) with the approved four-part PM material. Two rules from the
original T05h card survive, on the new contract:

* ``dp25-signoff-conclusion``'s three required arrays
  (``verification_evidence.verified``, ``verification_evidence.unverified``,
  ``unfinished_impact``) use ``[]`` for "verified none" / "nothing unfinished",
  so the AC-019 "empty container == unreplaced placeholder" rule must not
  refuse them;
* the waiver is *field-level*, declared in the registry metadata
  (``STATE_FIELD_DESCRIPTIONS[path]["empty_is_value"] = True``) and consumed by
  the decision book's placeholder scan — never by hard-coding ``dp25`` in the
  book and never by weakening ``is_placeholder([])`` globally;
* everything else keeps refusing: a missing, ``null`` or wrong-typed required
  path, a blank element, placeholder text *inside* an array, and every other
  dp's empty required array (dp8 ``scope.cross_key_conflicts``, dp15
  ``gate.pending_items``, dp17 ``spec.open_questions``, dp20
  ``stage.open_blockers``). The typed / closed-key / evidence / secret gates are
  untouched, and ``[]`` is not evidence that the facts behind it were verified.

The three arrays declare ``item_type: string`` + ``empty_is_value`` but no
``max_items`` / ``item_max_bytes``: they are free-text evidence, bounded by the
single published material budget (``decision_points.MAX_STATE_BYTES`` = 8192B).
This suite therefore pins the honest boundary instead of an invented per-array
cap: a 33-element / 129-byte item is legal and is sent, while an over-budget
array is refused WHOLE as ``input-oversize`` with zero POST and zero truncation.

Hermetic: tmp projects, ``decision.FakeBackend``, tmp ``HOME`` / ``USERPROFILE``,
a tmp ``auth.json`` path, credential env vars removed, no network, no real
credentials, no real production archive.
"""

from __future__ import annotations

import copy
import json
import os
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_backends  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire  # noqa: E402

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
CASES_DIR = PACKAGE_DIR / "decide_cases"
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
DP25_ARRAYS = (
    "unfinished_impact",
    "verification_evidence.unverified",
    "verification_evidence.verified",
)


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
# Fixtures / helpers (the shipped four-part case is the real material)
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


def _shipped_state() -> dict:
    """The shipped `decide_cases/dp25.json` book state (the real four parts)."""
    doc = json.loads((CASES_DIR / "dp25.json").read_text(encoding="utf-8"))
    return copy.deepcopy(doc["book"]["state"])


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


def _real_state() -> dict:
    return _shipped_state()


def _decide(
    project: pathlib.Path,
    root: pathlib.Path,
    state: dict,
    *,
    book: bool,
    observation: bool = True,
):
    """Run one dp25 decision in ``plain`` or ``book`` (observation) mode."""
    scope = _scope(root)
    backend = decision.FakeBackend([_ok(_dp25_answers())])
    client = _client(backend, scope)
    obs = None
    if observation:
        obs = dpts.Observation(
            scope=scope,
            book=_book(DP25, state) if book else None,
            submission_id=SUB,
        )
    outcome = dpts.decide_for(
        DP25,
        state,
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=obs,
    )
    return outcome, backend, decision_wire.test_wire_sink(root)


# ---------------------------------------------------------------------------
# 1. The registry is the single authority for the field-level rule
# ---------------------------------------------------------------------------


def test_registry_declares_empty_is_value_only_for_the_dp25_arrays() -> None:
    assert "empty_is_value" in dpts.STATE_FIELD_CONSTRAINT_KEYS, (
        "an undeclared spec key would be refused by _validate_state_field_contract"
    )
    flagged = sorted(
        path
        for path, spec in dpts.STATE_FIELD_DESCRIPTIONS.items()
        if spec.get("empty_is_value")
    )
    # ``p0_open`` is the retired dp25 counter field: no dp declares it any more,
    # only its field metadata survives (legacy producer debt, reported instead of
    # edited outside this card's face). The three live required arrays carry the
    # waiver that matters.
    assert flagged == ["p0_open", *DP25_ARRAYS], f"the waiver must stay field-level: {flagged}"
    assert all(
        "p0_open" not in paths for paths in dpts.REQUIRED_STATE_FIELDS.values()
    ), "p0_open must stay retired (no required path references it)"
    for path in DP25_ARRAYS:
        spec = dpts.STATE_FIELD_DESCRIPTIONS[path]
        assert spec["empty_is_value"] is True, path
        assert spec["type"] == "array", path
        assert spec["item_type"] == "string", path
        # Free-text evidence: no invented per-array cap. The published material
        # budget (8192B) is the only bound, and it refuses the whole material.
        assert "max_items" not in spec, path
        assert "item_max_bytes" not in spec, path
        assert "enum" not in spec, path


def test_no_other_required_empty_array_field_gains_the_waiver() -> None:
    declared = {path for paths in dpts.REQUIRED_STATE_FIELDS.values() for path in paths}
    for path in sorted(declared):
        if path in DP25_ARRAYS:
            continue
        assert "empty_is_value" not in dpts.STATE_FIELD_DESCRIPTIONS[path], path


def test_global_placeholder_rule_is_not_loosened() -> None:
    """``is_placeholder([])`` is the AC-019 rule every other dp depends on."""
    assert books.is_placeholder([]) is True
    assert books.is_placeholder({}) is True
    assert books.is_placeholder("") is True
    assert books.is_placeholder(None) is True


def test_export_api_carries_the_field_metadata() -> None:
    doc = json.loads(REGISTRY_JSON.read_text(encoding="utf-8"))
    exported_point = {row["id"]: row for row in doc["points"]}[DP25]
    exported_fields = {
        row["name"]: row for row in exported_point["required_state_fields"]
    }
    for path in DP25_ARRAYS:
        exported = dpts.snapshot_field_dict(path)
        assert exported["empty_is_value"] is True, path
        assert exported["type"] == "array", path
        assert exported["item_type"] == "string", path
        assert "max_items" not in exported, path
        assert "item_max_bytes" not in exported, path
        registry_row = exported_fields[path]
        assert registry_row["empty_is_value"] is True, path
        assert registry_row["item_type"] == "string", path
    conflicts = dpts.snapshot_field_dict("scope.cross_key_conflicts")
    assert "empty_is_value" not in conflicts


def test_generated_ts_mirror_carries_the_field_metadata() -> None:
    text = GENERATED_TS.read_text(encoding="utf-8")
    for path in DP25_ARRAYS:
        start = text.index(f'name: "{path}"')
        block = text[start : text.index("},", start)]
        assert 'itemType: "string"' in block, (path, block)
        assert "emptyIsValue: true" in block, (path, block)
        assert "maxItems" not in block, (path, block)
        assert "itemMaxBytes" not in block, (path, block)


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
# 3. The real four-part dp25 state is legal material (the card's goal)
# ---------------------------------------------------------------------------


def test_real_four_part_state_is_a_legal_book(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    state = _real_state()
    assert isinstance(state["unfinished_impact"], list)
    assert state["verification_evidence"]["verified"]
    assert dpts.state_field_issues(DP25, state) == ()
    assert dpts.state_unknown_key_issues(DP25, state, allow_context=True) == ()
    assert books.check_book(_book(DP25, state), project_dir=project) == []
    assert books.observation_book_issues(_book(DP25, state), project) == ()


def test_real_state_is_accepted_as_observation_material(
    tmp_path: pathlib.Path,
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    state = _real_state()
    root = tmp_path / "run"
    outcome, backend, sink = _decide(project, root, state, book=True)

    assert outcome.status == "suggested", outcome.detail
    assert len(backend.calls) == 1
    sent = backend.calls[0]["state"]
    assert sent == dpts.model_state_for(DP25, state), (
        "the sent state must be the registry projection (identity/audit stripped)"
    )
    assert sent["unfinished_impact"] == state["unfinished_impact"]
    snapshots = _of_kind(sink, "book-snapshot")
    assert len(snapshots) == 1
    body = _snapshot_body(snapshots[0])
    assert body["state"] == sent
    assert body["candidates"] == {}
    assert outcome.snapshot_ref is not None
    assert snapshots[0]["book_ref"] == outcome.snapshot_ref


def test_scaffold_arrays_are_legal_but_the_scaffold_is_still_not_signable() -> None:
    scaffold = books.scaffold_book(DP25)
    for path in DP25_ARRAYS:
        value = dpts._lookup(scaffold["state"], path)
        assert value == [], path
        assert (
            "book-placeholder",
            f"state.{path}",
        ) not in _issues(scaffold), (
            "the editor scaffold writes [] for these arrays, which the rule accepts"
        )
    issues = _issues(scaffold)
    assert issues, "yet the scaffold is still an unfilled book, not an approval"


# ---------------------------------------------------------------------------
# 4. Missing / null / wrong type / placeholder / blank items still refuse
# ---------------------------------------------------------------------------


WRONG_TYPED_ARRAYS = (
    ("verified-string", "verification_evidence.verified", "no"),
    ("unverified-object", "verification_evidence.unverified", {"x": 1}),
    ("unfinished-object", "unfinished_impact", {"x": 1}),
)


@pytest.mark.parametrize(
    ("case", "path", "value"),
    WRONG_TYPED_ARRAYS,
    ids=[item[0] for item in WRONG_TYPED_ARRAYS],
)
def test_wrong_typed_dp25_array_refuses_with_zero_send_and_zero_snapshot(
    case: str, path: str, value: object, tmp_path: pathlib.Path
) -> None:
    """A wrong-typed array is illegal material: refused, never stored.

    The waiver only covers the empty-container rule, so the typed gate still
    owns the field: no transport call and no snapshot (the same rule the typed
    refusal path has for every dp).
    """
    project = tmp_path / "proj"
    project.mkdir()
    state = _real_state()
    dpts._set_path(state, path, value)
    assert any(issue[0] == path for issue in dpts.state_field_issues(DP25, state)), (
        case,
        dpts.state_field_issues(DP25, state),
    )
    assert any(
        code == "book-state" and issue_path == f"state.{path}"
        for code, issue_path in _issues(_book(DP25, state))
    ), case

    for book in (False, True):
        root = tmp_path / f"run-{case}-{book}"
        outcome, backend, sink = _decide(project, root, state, book=book)
        assert outcome.escalated_reason == "input-incomplete", (case, book, outcome.detail)
        assert path in outcome.detail, (case, book, outcome.detail)
        assert backend.calls == [], f"{case}/{book}: illegal material reached the transport"
        assert _of_kind(sink, "book-snapshot") == [], f"{case}/{book}: illegal material stored"
        end = _of_kind(sink, "decision-end")
        assert len(end) == 1 and end[0]["book_ref"] is None, (case, book, end)
        assert outcome.snapshot_ref is None


REQUIRED_DEFECTS = (
    ("missing-verified", "verification_evidence.verified", "missing"),
    ("null-verified", "verification_evidence.verified", "null"),
    ("missing-unfinished", "unfinished_impact", "missing"),
    ("null-unfinished", "unfinished_impact", "null"),
)


@pytest.mark.parametrize(
    ("case", "path", "defect"),
    REQUIRED_DEFECTS,
    ids=[item[0] for item in REQUIRED_DEFECTS],
)
def test_missing_or_null_dp25_array_refuses_with_zero_send_and_zero_snapshot(
    case: str, path: str, defect: str, tmp_path: pathlib.Path
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    state = _real_state()
    parent, _, leaf = path.rpartition(".")
    container = dpts._lookup(state, parent) if parent else state
    if defect == "missing":
        container.pop(leaf)
    else:
        container[leaf] = None
    root = tmp_path / f"run-{case}"
    outcome, backend, sink = _decide(project, root, state, book=True)

    assert outcome.escalated_reason == "input-incomplete", (case, outcome.detail)
    assert path in outcome.detail, (case, outcome.detail)
    assert backend.calls == [], f"{case}: refused material reached the transport"
    assert _of_kind(sink, "book-snapshot") == [], f"{case}: refused material stored"
    end = _of_kind(sink, "decision-end")
    assert len(end) == 1 and end[0]["book_ref"] is None, (case, end)
    assert end[0]["status"] == "escalated"
    assert outcome.snapshot_ref is None


@pytest.mark.parametrize("path", ["verification_evidence.verified", "unfinished_impact"])
def test_blank_item_inside_a_dp25_array_is_refused(path: str, tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    state = _real_state()
    dpts._set_path(state, path, [""])
    issues = dpts.state_field_issues(DP25, state)
    assert any(issue_path == f"{path}[0]" for issue_path, _detail in issues), issues
    assert any(
        code == "book-state" and issue_path == f"state.{path}[0]"
        for code, issue_path in _issues(_book(DP25, state))
    )
    root = tmp_path / "run-blank"
    outcome, backend, sink = _decide(project, root, state, book=True)
    assert outcome.escalated_reason == "input-incomplete"
    assert path in outcome.detail
    assert backend.calls == []
    assert _of_kind(sink, "book-snapshot") == []


def test_placeholder_text_inside_a_dp25_array_is_refused(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    for value in ("<none>", "", "TBD", -1):
        state = _real_state()
        state["unfinished_impact"] = [value]
        issues = _issues(_book(DP25, state))
        assert ("book-placeholder", "state.unfinished_impact[0]") in issues, (value, issues)
        for issue in books.check_book(_book(DP25, state), project_dir=project):
            if str(value):
                assert str(value) not in issue.detail, (value, issue.detail)

    state = _real_state()
    state["unfinished_impact"] = ["documented follow-up: no impact on delivery"]
    assert _issues(_book(DP25, state)) == [], "a real evidence item is still legal"


# ---------------------------------------------------------------------------
# 5. No invented array caps: the 8192B material budget is the honest boundary
# ---------------------------------------------------------------------------


def test_no_invented_array_caps_and_the_material_budget_still_binds(
    tmp_path: pathlib.Path,
) -> None:
    project = tmp_path / "proj"
    project.mkdir()

    # The retired "33 items / 129 B item" cases were legal before T05h invented
    # caps and are legal again: the arrays are free-text evidence.
    many = _real_state()
    many["unfinished_impact"] = [f"item-{index}" for index in range(33)]
    assert dpts.state_field_issues(DP25, many) == ()
    assert _issues(_book(DP25, many)) == []
    root = tmp_path / "run-many"
    outcome, backend, sink = _decide(project, root, many, book=True)
    assert outcome.status == "suggested", outcome.detail
    assert len(backend.calls) == 1
    assert len(backend.calls[0]["state"]["unfinished_impact"]) == 33
    assert _snapshot_body(_of_kind(sink, "book-snapshot")[0])["state"] == backend.calls[0]["state"]

    long_item = _real_state()
    long_item["verification_evidence"]["verified"] = ["x" * 129]
    assert dpts.state_field_issues(DP25, long_item) == ()
    assert _issues(_book(DP25, long_item)) == []

    # The ONE published bound: the whole material over 8192B is refused whole.
    oversize = _real_state()
    oversize["unfinished_impact"] = ["x" * 9000]
    assert dpts.state_field_issues(DP25, oversize) == ()
    assert _issues(_book(DP25, oversize)) == []

    root = tmp_path / "run-oversize"
    outcome, backend, sink = _decide(project, root, oversize, book=True)
    assert outcome.escalated_reason == "input-oversize", outcome.detail
    assert f"> {dpts.MAX_STATE_BYTES}B" in outcome.detail, outcome.detail
    assert backend.calls == [], "over-budget material must never reach the transport"
    assert list(outcome.truncated or ()) == [], "the material is never truncated"
    snapshots = _of_kind(sink, "book-snapshot")
    assert len(snapshots) == 1, "an oversize candidate is legal material and is kept for the human"
    assert _snapshot_body(snapshots[0])["state"] == dpts.model_state_for(DP25, oversize)


# ---------------------------------------------------------------------------
# 6. ``[]`` means "no open item", never "the facts behind it were verified"
# ---------------------------------------------------------------------------


def test_empty_arrays_are_not_assumed_verified(tmp_path: pathlib.Path) -> None:
    """Evidence stays mandatory for every array, even when it is empty."""
    project = tmp_path / "proj"
    project.mkdir()
    state = _real_state()
    book = _book(DP25, state)
    del book["notes"]["evidence"]["unfinished_impact"]
    issues = _issues(book)
    assert ("book-evidence", "notes.evidence.unfinished_impact") in issues, issues
    assert ("book-placeholder", "state.unfinished_impact") not in issues
    assert dpts.state_field_issues(DP25, state) == ()
