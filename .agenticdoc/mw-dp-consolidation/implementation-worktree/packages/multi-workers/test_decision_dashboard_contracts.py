"""test_decision_dashboard_contracts.py — T04: the 25 DP typed business contract.

Key ``mw-decision-dashboard``, card T04 (AC-009 / AC-011, VC-009). The registry
(``decision_points``) is the single authority for *which* business facts a dp
needs, *how* they are shaped (type / enum / ``max_items`` / element length /
signedness) and *which* facts are optional. ``decision_book`` (scaffold, closed
key set, evidence, budget) and both generated artifacts (``decide_registry.json``
+ ``decide-registry.generated.ts``) derive from it, so a field added on one side
only cannot pass.

What this module locks (design §4.5, §7 VC-009):

1. every one of the 25 dps declares typed business fields (not just the three
   identity keys), each with type + description + its constraint;
2. an identity-only state is refused with ``input-incomplete`` **before** any
   transport call (the old "empty contract" virtual-test channel is closed),
   while a legally filled state still reaches the transport;
3. ``scaffold_book`` carries the business fields and is *not* directly sendable,
   and a fully filled book passes ``check_book`` for all 25 dps;
4. unknown keys / wrong element types / illegal enum values / over-limit arrays
   and elements are refused (zero HTTP through the real CLI book gate);
5. dp17 carries 17 AC ids and ``max_items=128``, plain arrays default to 32,
   new plain string elements are capped at 128 B and new strings at 512 B;
6. dp23 ``snapshot.delta_bytes`` is a signed integer (negative deltas legal);
7. dp2's real ``progress`` optional fields are part of the closed set and both
   generated artifacts stay in lockstep;
8. dp1/dp2/dp3/dp25 keep their frozen required-field tuples;
9. the 2000 B state budget stays an *independent* gate: a state that is legal
   per field limits can still be refused, and required facts are never silently
   dropped/truncated;
10. cross-field facts (attempt<=limit, failed<=total, changed⊆ids, done<=total)
    are validated by the registry.

Hermetic: ``tmp_path`` fixtures, ``decision.FakeBackend`` only, no network, no
credentials, no production authority/decisions/signoff/triage writes.
"""

from __future__ import annotations

import json
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_backends  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]
GENERATED_TS = (
    REPO_ROOT
    / "packages"
    / "coding-agent"
    / "src"
    / "extensions"
    / "agent-team-loop"
    / "shared"
    / "decide-registry.generated.ts"
)

#: The four dps whose contract predates this card (design §4.5: keep them).
PRESERVED_DP_IDS = frozenset(
    {
        "dp1-dispatch-type",
        "dp2-checkpoint-split",
        "dp3-worker-clarify",
        "dp25-signoff-conclusion",
    }
)
#: dp4..dp24 — the 21 dps that were identity-only before this card.
NEW_DP_IDS = tuple(point.id for point in dpts.DP_REGISTRY if point.id not in PRESERVED_DP_IDS)
#: Structural identity the builder always writes (book ``STRUCTURAL_STATE_FIELDS``).
IDENTITY_PATHS = ("schema_version", "decision_point", "questions_version")

#: The approved per-dp required tuples (T01 contract, copied verbatim). A
#: later one-sided change is still red: this is the frozen side of the lock.
FROZEN_REQUIRED: dict[str, tuple[str, ...]] = {
    # dp1: the complete dispatch material (no identity, no scope triple).
    "dp1-dispatch-type": (
        "task_goal",
        "task_requirements",
        "task_deliverables",
    ),
    # dp2: the same material plus the PM's checkpoint background.
    "dp2-checkpoint-split": (
        "task_goal",
        "task_requirements",
        "task_deliverables",
        "pm_decision_background",
    ),
    # dp3: the clarifying question + its background + the handling candidates.
    "dp3-worker-clarify": (
        "question",
        "background.task_goal",
        "background.current_state",
        "background.decision_reason",
        "background.constraints_impact",
        "handling_options",
    ),
    # dp25: the four-part sign-off material itself, never archive counts.
    "dp25-signoff-conclusion": (
        "delivery_goal",
        "actual_completion",
        "verification_evidence.verified",
        "verification_evidence.unverified",
        "unfinished_impact",
    ),
}

#: dp2's only declared optional field (the real worker execution, if any).
DP2_OPTIONAL = ("worker_execution",)

CRED_ENV_VARS = ("TIMI_API_KEY", "TYPESAFE_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY")


# ---------------------------------------------------------------------------
# Fixtures / sample-state builder
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch):
    for name in CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(dpts, "ARCHIVE_WRITER", None, raising=False)
    monkeypatch.setattr(decision_backends, "resolve_timi_api_key", lambda *a, **k: None)
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


def spec(path: str) -> dict:
    return dict(dpts.STATE_FIELD_DESCRIPTIONS[path])


def sample_value(path: str) -> object:
    """A legal value for one declared path, derived from its own spec."""
    field = spec(path)
    kind = str(field["type"])
    options = field.get("enum")
    if options:
        return options[0]
    if kind == "string":
        return "x"
    if kind == "boolean":
        return True
    if kind == "integer":
        signed = bool(field.get("signed"))
        return -256 if signed else 1
    if kind == "number":
        return 1.0
    if kind == "array":
        item_type = str(field.get("item_type") or "string")
        if item_type == "object":
            return [{"id": "x"}]
        if item_type == "boolean":
            return [True]
        if item_type == "integer":
            return [1]
        return ["x"]
    if kind == "object":
        return {"id": "x"}
    raise AssertionError(f"{path}: unhandled kind {kind!r}")


#: Values that keep the declared cross-field facts legal (attempt<=limit, ...).
CROSS_FIELD_SAMPLES: dict[str, object] = {
    "failure.attempt": 1,
    "failure.limit": 2,
    "qg.checks_total": 2,
    "qg.checks_failed": ["test_a"],
    "spec.ac_ids": [f"AC-{index:03d}" for index in range(1, 18)],
    "spec.ac_changed": [f"AC-{index:03d}" for index in range(1, 18)],
    "stage.tasks_done": 1,
    "stage.tasks_total": 2,
    "handling_options": [
        {"id": "c1", "label": ".mw/decide-points.json", "description": "the config table"},
        {"id": "c2", "label": "decide_registry.json", "description": "the registry"},
    ],
    "task_goal": "probe task goal",
    "task_requirements": "probe task requirements",
    "task_deliverables": "probe task deliverables",
    "pm_decision_background": "probe: why the PM needs this checkpoint",
    "question": "which file holds the decide points?",
    "delivery_goal": "probe delivery goal",
    "actual_completion": "probe actual completion",
    "ambiguity.kind": "fact",
    "ambiguity.question": "which file holds the decide points?",
    "scope.write_scope": ["packages/multi-worker-dashboard"],
    "scope.file_extensions": [".py"],
    "task_summary": "card T04 contract sample",
    "key": "mw-decision-dashboard",
    "phase": "EXECUTE",
    "task_type": "coding",
    "requested_type": "coding",
    "risk": "mid",
    "risk_source": "pm-label",
    "progress.elapsed_minutes": 1,
    "progress.budget_minutes": 30,
    "progress.phases_done": 1,
    "progress.phases_total": 3,
    "progress.artifact_present": True,
    "snapshot.size_bytes": 4096,
    "snapshot.delta_bytes": -256,
}


def legal_state(dp_id: str) -> dict:
    """Full, legally filled state: identity + every required business field."""
    point = {entry.id: entry for entry in dpts.DP_REGISTRY}[dp_id]
    required = dpts.REQUIRED_STATE_FIELDS[dp_id]
    state: dict = {
        "schema_version": 2,
        "decision_point": dp_id,
        "questions_version": point.questions_version,
    }
    if "key" in required:
        state["key"] = "mw-decision-dashboard"
    if "authority_tier" in required:
        state["authority_tier"] = point.tier
    for path in required:
        if path in state:
            continue
        value = CROSS_FIELD_SAMPLES.get(path, sample_value(path))
        _set_path(state, path, value)
    return state


def _set_path(target: dict, dotted: str, value: object) -> None:
    parts = dotted.split(".")
    node = target
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def make_root(tmp_path: pathlib.Path) -> pathlib.Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True, exist_ok=True)
    (root / "notes.txt").write_text(
        "line1\nline2\nline3\nline4\nline5\n", encoding="utf-8", newline="\n"
    )
    return root


#: Paths dp1 already declared before this card; they keep their existing
#: (uncapped) declaration instead of gaining the new unified caps.
CARRIED_OVER_PATHS = frozenset({"scope.write_scope"})


def legal_book(dp_id: str) -> dict:
    state = legal_state(dp_id)
    evidence = {path: "notes.txt:1" for path in dpts.REQUIRED_STATE_FIELDS[dp_id]}
    return {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "state": state,
        "notes": {"evidence": evidence},
    }


def enable_all(project: pathlib.Path) -> None:
    """Enable every dp in an isolated tmp project (never a production table)."""
    table = {
        "version": 1,
        "points": {point.id: {"enabled": True, "mode": "suggest"} for point in dpts.DP_REGISTRY},
    }
    path = project / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8", newline="\n")
    dpts.clear_points_config_cache()


def answers_for(dp_id: str) -> dict:
    out: dict = {}
    for question in dpts.get_decision_point(dp_id).questions:
        if question["type"] == decision.QUESTION_CHOICE:
            value = "c1" if "dynamic_choices" in question else question["choices"][0]
        elif question["type"] == decision.QUESTION_NOUL:
            value = 0.9
        else:
            value = question.get("min", 0)
        out[str(question["id"])] = {"value": value, "confidence": 0.9}
    return out


def configured_client(tmp_path: pathlib.Path, dp_id: str):
    backend = decision.FakeBackend(
        default=decision.BackendOutcome(
            available=True,
            reason=None,
            retryable=False,
            answers=answers_for(dp_id),
            latency_ms=1,
        )
    )
    cfg = decision.DecisionConfig(enabled=True)
    client = decision.DecisionClient(
        cfg=cfg, backend=backend, evidence_path=tmp_path / "triage-decisions.jsonl"
    )
    return client, backend


def book_paths(issues, code: str) -> list[str]:
    return [issue.path for issue in issues if issue.code == code]


def check_one(dp_id: str, state: dict, tmp_path: pathlib.Path) -> list:
    book = {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "state": state,
        "notes": {"evidence": {path: "notes.txt:1" for path in dpts.REQUIRED_STATE_FIELDS[dp_id]}},
    }
    return books.check_book(book, project_dir=make_root(tmp_path))


# ---------------------------------------------------------------------------
# 1. The contract itself: 25 dps, typed, constrained, described
# ---------------------------------------------------------------------------


def test_all_25_registered_dps_have_a_business_contract() -> None:
    assert len(dpts.DP_REGISTRY) == 25
    for point in dpts.DP_REGISTRY:
        required = dpts.REQUIRED_STATE_FIELDS.get(point.id, ())
        assert required, f"{point.id}: no required_state_fields"
        if point.id in PRESERVED_DP_IDS:
            continue
        assert set(IDENTITY_PATHS) <= set(required), f"{point.id}: identity keys missing"
        business = [path for path in required if path not in IDENTITY_PATHS]
        assert len(business) >= 3, f"{point.id}: only {business} of business input"


def test_every_declared_path_is_typed_and_described() -> None:
    declared = {path for paths in dpts.REQUIRED_STATE_FIELDS.values() for path in paths}
    declared |= {path for paths in dpts.OPTIONAL_STATE_FIELDS.values() for path in paths}
    for path in sorted(declared):
        field = spec(path)
        assert field["type"] in dpts.STATE_FIELD_TYPES, path
        assert isinstance(field["description"], str) and field["description"].strip(), path
        allowed = {"type", "description"} | set(dpts.STATE_FIELD_CONSTRAINT_KEYS)
        assert set(field) <= allowed, f"{path}: unexpected spec keys {sorted(set(field) - allowed)}"


def test_new_strings_and_array_elements_carry_the_unified_caps() -> None:
    """Every new plain string/element declares the design §4.5 caps."""
    new_paths = [
        path
        for dp_id in NEW_DP_IDS
        for path in dpts.REQUIRED_STATE_FIELDS[dp_id]
        if path not in IDENTITY_PATHS and path not in CARRIED_OVER_PATHS
    ]
    assert new_paths, "the 21 business contracts are empty"
    for path in new_paths:
        field = spec(path)
        kind = field["type"]
        if kind == "string":
            assert field.get("max_bytes") == dpts.STATE_STRING_MAX_BYTES, path
        elif kind == "array":
            assert field.get("max_items", 0) > 0, f"{path}: no max_items"
            if field.get("item_type", "string") == "string":
                assert field.get("item_max_bytes") == dpts.STATE_ARRAY_ITEM_MAX_BYTES, path
        elif kind == "integer":
            if not field.get("signed"):
                assert field.get("min_value") == 0, f"{path}: count/size must declare >= 0"
        elif kind == "boolean":
            assert "enum" not in field and "max_items" not in field, path


def test_dp17_covers_17_acs_and_uses_the_wide_array_cap() -> None:
    assert spec("spec.ac_ids")["max_items"] == 128
    assert spec("spec.ac_ids")["item_max_bytes"] == dpts.STATE_ARRAY_ITEM_MAX_BYTES
    assert spec("spec.ac_changed")["max_items"] == 128
    seventeen = [f"AC-{index:03d}" for index in range(1, 18)]
    assert len(seventeen) == 17
    state = legal_state("dp17-spec-lock")
    state["spec"] = {"ac_ids": seventeen, "ac_changed": seventeen, "open_questions": ["q1"]}
    assert dpts.state_field_issues("dp17-spec-lock", state) == ()
    state["spec"]["ac_ids"] = seventeen + [f"AC-{index:03d}" for index in range(18, 129)]
    assert dpts.state_field_issues("dp17-spec-lock", state) == ()
    state["spec"]["ac_ids"] = state["spec"]["ac_ids"] + ["AC-129"]
    issues = dpts.state_field_issues("dp17-spec-lock", state)
    assert any(path == "spec.ac_ids" for path, _detail in issues)


def test_plain_arrays_default_to_32_items() -> None:
    new_arrays = {
        path
        for dp_id in NEW_DP_IDS
        for path in (*dpts.REQUIRED_STATE_FIELDS[dp_id], *dpts.OPTIONAL_STATE_FIELDS.get(dp_id, ()))
        if path not in IDENTITY_PATHS and path not in CARRIED_OVER_PATHS
        and spec(path)["type"] == "array"
    }
    assert new_arrays, "no new array field declared"
    for path in sorted(new_arrays):
        if path in ("spec.ac_ids", "spec.ac_changed"):
            continue
        assert spec(path).get("max_items") == dpts.STATE_ARRAY_MAX_ITEMS, f"{path}: {spec(path)}"


def test_dp23_delta_bytes_is_a_signed_integer() -> None:
    field = spec("snapshot.delta_bytes")
    assert field["type"] == "integer"
    assert field.get("signed") is True
    state = legal_state("dp23-snapshot")
    state["snapshot"] = {"size_bytes": 8192, "delta_bytes": -512, "sections_changed": ["s1"]}
    assert dpts.state_field_issues("dp23-snapshot", state) == ()
    state["snapshot"]["delta_bytes"] = -1
    assert dpts.state_field_issues("dp23-snapshot", state) == ()
    state["snapshot"]["delta_bytes"] = "down"
    issues = dpts.state_field_issues("dp23-snapshot", state)
    assert any(path == "snapshot.delta_bytes" for path, _detail in issues)


def test_dp15_gate_kind_enum_is_the_gate_authority() -> None:
    from autopilot import gates

    assert spec("gate.kind")["enum"] == gates.GATE_KINDS
    assert dpts.GATE_KIND_ENUM == gates.GATE_KINDS


def test_dp11_never_takes_a_credential_value() -> None:
    paths = dpts.REQUIRED_STATE_FIELDS["dp11-credential"]
    assert not any("value" in path or "secret" in path or "token" in path for path in paths)
    assert "credential.provider" in paths and "credential.exposed_to" in paths


def test_preserved_dps_keep_their_frozen_required_tuples() -> None:
    for dp_id, frozen in FROZEN_REQUIRED.items():
        assert dpts.REQUIRED_STATE_FIELDS[dp_id] == frozen, dp_id


def test_dp2_optional_progress_fields_are_a_declared_closed_set() -> None:
    assert dpts.OPTIONAL_STATE_FIELDS["dp2-checkpoint-split"] == DP2_OPTIONAL
    assert dpts.OPTIONAL_STATE_FIELDS.get("dp1-dispatch-type", ()) == ()
    # The drop order used by `_fit_state` is derived from the registry, not a
    # second hard-coded tuple.
    for path in DP2_OPTIONAL:
        assert path in dpts.OPTIONAL_STATE_PATHS


# ---------------------------------------------------------------------------
# 2. Identity-only states are refused before any transport call
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dp_id", NEW_DP_IDS, ids=list(NEW_DP_IDS))
def test_identity_only_state_is_refused_with_zero_send(dp_id: str, tmp_path: pathlib.Path) -> None:
    enable_all(tmp_path)
    client, backend = configured_client(tmp_path, dp_id)
    outcome = dpts.decide_for(
        dp_id, {"key": "k1"}, tmp_path, client=client, archive=False, intent="answer"
    )
    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "input-incomplete"
    business = [path for path in dpts.REQUIRED_STATE_FIELDS[dp_id] if path not in IDENTITY_PATHS]
    assert any(path in outcome.detail for path in business), outcome.detail
    assert backend.calls == [], f"{dp_id}: identity-only state reached the transport"


@pytest.mark.parametrize("dp_id", [point.id for point in dpts.DP_REGISTRY], ids=[point.id for point in dpts.DP_REGISTRY])
def test_a_legally_filled_state_still_reaches_the_transport(dp_id: str, tmp_path: pathlib.Path) -> None:
    enable_all(tmp_path)
    client, backend = configured_client(tmp_path, dp_id)
    outcome = dpts.decide_for(
        dp_id,
        legal_state(dp_id),
        tmp_path,
        client=client,
        archive=False,
        intent="answer",
    )
    assert outcome.escalated_reason != "input-incomplete", outcome.detail
    assert outcome.escalated_reason != "input-oversize", outcome.detail
    assert backend.calls, f"{dp_id}: legal business facts were not sent"


@pytest.mark.parametrize("dp_id", [point.id for point in dpts.DP_REGISTRY], ids=[point.id for point in dpts.DP_REGISTRY])
def test_scaffold_carries_the_business_fields_and_is_not_sendable(dp_id: str) -> None:
    book = books.scaffold_book(dp_id)
    flat = set(books._flatten(book["state"]))
    required = set(dpts.REQUIRED_STATE_FIELDS[dp_id])
    assert required <= flat, f"{dp_id}: scaffold state misses {sorted(required - flat)}"
    issues = books.check_book(book)
    assert issues, f"{dp_id}: a scaffold book must not pass check_book"
    assert "book-placeholder" in {issue.code for issue in issues}
    evidence = book["notes"]["evidence"]
    assert list(evidence) == list(dpts.REQUIRED_STATE_FIELDS[dp_id])


# ---------------------------------------------------------------------------
# 3. check_book: a fully filled book passes; each defect class is refused
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("dp_id", [point.id for point in dpts.DP_REGISTRY], ids=[point.id for point in dpts.DP_REGISTRY])
def test_a_fully_filled_book_passes_check_book(dp_id: str, tmp_path: pathlib.Path) -> None:
    issues = books.check_book(legal_book(dp_id), project_dir=make_root(tmp_path))
    assert issues == [], f"{dp_id}: {[issue.format() for issue in issues]}"


def test_unknown_business_key_is_refused(tmp_path: pathlib.Path) -> None:
    state = legal_state("dp4-failure-handling")
    state["failure"]["expected_action"] = "retry"
    issues = check_one("dp4-failure-handling", state, tmp_path)
    assert "state.failure.expected_action" in book_paths(issues, "book-state")
    assert any("closed key set" in issue.detail for issue in issues)


def test_wrong_array_element_type_is_refused(tmp_path: pathlib.Path) -> None:
    state = legal_state("dp5-test-triage")
    state["test"] = {
        "failed_cases": [1],
        "baseline_cases": ["x"],
        "changed_paths": ["x"],
        "repro_consistent": True,
    }
    issues = check_one("dp5-test-triage", state, tmp_path)
    assert "state.test.failed_cases[0]" in book_paths(issues, "book-state")
    assert any("expected string" in issue.detail for issue in issues)


def test_illegal_enum_value_is_refused(tmp_path: pathlib.Path) -> None:
    state = legal_state("dp4-failure-handling")
    state["failure"]["kind"] = "boom"
    issues = check_one("dp4-failure-handling", state, tmp_path)
    assert "state.failure.kind" in book_paths(issues, "book-state")
    assert any("must be one of" in issue.detail for issue in issues)


def test_over_limit_array_is_refused(tmp_path: pathlib.Path) -> None:
    state = legal_state("dp5-test-triage")
    state["test"] = {
        "failed_cases": [f"case_{index}" for index in range(33)],
        "baseline_cases": ["x"],
        "changed_paths": ["x"],
        "repro_consistent": True,
    }
    issues = check_one("dp5-test-triage", state, tmp_path)
    assert "state.test.failed_cases" in book_paths(issues, "book-state")
    assert any("33 items > max_items 32" in issue.detail for issue in issues)


def test_over_long_element_and_string_are_refused(tmp_path: pathlib.Path) -> None:
    state = legal_state("dp5-test-triage")
    state["test"] = {
        "failed_cases": ["c" * 129],
        "baseline_cases": ["x"],
        "changed_paths": ["x"],
        "repro_consistent": True,
    }
    issues = check_one("dp5-test-triage", state, tmp_path)
    assert "state.test.failed_cases[0]" in book_paths(issues, "book-state")
    assert any("129 B > 128 B" in issue.detail for issue in issues)

    state = legal_state("dp7-gate-failure")
    state["gate"]["name"] = "g" * 513
    issues = check_one("dp7-gate-failure", state, tmp_path)
    assert "state.gate.name" in book_paths(issues, "book-state")
    assert any("513 B > 512 B" in issue.detail for issue in issues)


def test_negative_count_is_refused_but_signed_delta_is_not(tmp_path: pathlib.Path) -> None:
    state = legal_state("dp20-stage-close")
    state["stage"]["tasks_done"] = -1
    issues = check_one("dp20-stage-close", state, tmp_path)
    assert "state.stage.tasks_done" in book_paths(issues, "book-state")
    assert any(">= 0" in issue.detail for issue in issues)

    state = legal_state("dp23-snapshot")
    state["snapshot"] = {"size_bytes": 10, "delta_bytes": -1024, "sections_changed": ["s"]}
    assert books.check_book(
        {
            "schema_version": books.BOOK_SCHEMA_VERSION,
            "decision_point": "dp23-snapshot",
            "state": state,
            "notes": {"evidence": {path: "notes.txt:1" for path in dpts.REQUIRED_STATE_FIELDS["dp23-snapshot"]}},
        },
        project_dir=make_root(tmp_path),
    ) == []


def test_cross_field_facts_are_validated(tmp_path: pathlib.Path) -> None:
    state = legal_state("dp20-stage-close")
    state["stage"]["tasks_done"] = 4
    state["stage"]["tasks_total"] = 2
    issues = check_one("dp20-stage-close", state, tmp_path)
    assert "state.stage.tasks_done" in book_paths(issues, "book-state")
    assert any("tasks_done" in issue.detail and "tasks_total" in issue.detail for issue in issues)

    state = legal_state("dp4-failure-handling")
    state["failure"]["attempt"] = 5
    state["failure"]["limit"] = 3
    issues = check_one("dp4-failure-handling", state, tmp_path)
    assert "state.failure.attempt" in book_paths(issues, "book-state")

    state = legal_state("dp6-qg-verdict")
    state["qg"] = {"checks_total": 1, "checks_failed": ["a", "b"], "blocking": ["a"], "scope": "impl"}
    issues = check_one("dp6-qg-verdict", state, tmp_path)
    assert "state.qg.checks_failed" in book_paths(issues, "book-state")

    state = legal_state("dp17-spec-lock")
    state["spec"] = {
        "ac_ids": ["AC-001"],
        "ac_changed": ["AC-999"],
        "open_questions": ["q"],
    }
    issues = check_one("dp17-spec-lock", state, tmp_path)
    assert "state.spec.ac_changed" in book_paths(issues, "book-state")


def test_optional_fields_are_legal_and_need_no_evidence(tmp_path: pathlib.Path) -> None:
    state = legal_state("dp2-checkpoint-split")
    # The only declared optional field of the approved dp2 contract.
    state["worker_execution"] = "done A; left B; blocked on C"
    root = make_root(tmp_path)
    book = {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": "dp2-checkpoint-split",
        "state": state,
        "notes": {"evidence": {path: "notes.txt:1" for path in dpts.REQUIRED_STATE_FIELDS["dp2-checkpoint-split"]}},
    }
    assert books.check_book(book, project_dir=root) == []

    state["worker_execution_mystery"] = "invented"
    issues = check_one("dp2-checkpoint-split", state, tmp_path)
    assert "state.worker_execution_mystery" in book_paths(issues, "book-state")


# ---------------------------------------------------------------------------
# 4. Budget is an independent gate; required facts are never silently cut
# ---------------------------------------------------------------------------


def test_total_budget_stays_independent_of_the_field_limits(tmp_path: pathlib.Path) -> None:
    enable_all(tmp_path)
    client, backend = configured_client(tmp_path, "dp17-spec-lock")
    wide = [f"AC-{index:03d}-" + "x" * 90 for index in range(1, 129)]
    state = legal_state("dp17-spec-lock")
    state["spec"] = {"ac_ids": wide, "ac_changed": wide[:1], "open_questions": ["q"]}
    # Field contract: legal (128 items, each under the element cap).
    assert dpts.state_field_issues("dp17-spec-lock", state) == ()
    outcome = dpts.decide_for(
        "dp17-spec-lock",
        state,
        tmp_path,
        client=client,
        archive=False,
        intent="answer",
    )
    assert outcome.escalated_reason == "input-oversize", outcome.detail
    assert f"{dpts.MAX_STATE_BYTES}B" in outcome.detail
    assert backend.calls == []
    # Required facts are not part of any silent truncation stage.
    required = set(dpts.REQUIRED_STATE_FIELDS["dp17-spec-lock"])
    assert not required & set(dpts.OPTIONAL_STATE_PATHS)
    assert not required & set(dpts.TRUNCATABLE_STATE_PATHS)
    assert not [path for path in outcome.truncated if path in required]


# ---------------------------------------------------------------------------
# 5. Generated artifacts: registry JSON + type-safe TS module
# ---------------------------------------------------------------------------


def test_exported_fields_carry_every_declared_constraint() -> None:
    doc = dpts.registry_snapshot()
    by_id = {point["id"]: point for point in doc["points"]}
    for point in dpts.DP_REGISTRY:
        exported = by_id[point.id]
        assert [field["name"] for field in exported["required_state_fields"]] == list(
            dpts.REQUIRED_STATE_FIELDS[point.id]
        )
        for field in exported["required_state_fields"]:
            assert field["description"] == dpts.STATE_FIELD_DESCRIPTIONS[field["name"]]["description"]
            for key in dpts.STATE_FIELD_CONSTRAINT_KEYS:
                expected = dpts.STATE_FIELD_DESCRIPTIONS[field["name"]].get(key)
                if key == "enum" and expected is not None:
                    expected = list(expected)
                if expected is None:
                    assert key not in field, f"{field['name']}: spurious {key}"
                else:
                    assert field[key] == expected, f"{field['name']}: {key} drifted"
        optional = [field["name"] for field in exported["optional_state_fields"]]
        assert optional == list(dpts.OPTIONAL_STATE_FIELDS.get(point.id, ()))


def test_generated_ts_module_is_type_safe_and_carries_the_contract() -> None:
    text = GENERATED_TS.read_text(encoding="utf-8")
    # No `any` in a type position (descriptions may legitimately contain the word).
    assert re.search(r":\s*any\b", text) is None, "the generated module must not use `any`"
    assert "as any" not in text and "<any>" not in text and "any[]" not in text
    assert "import(" not in text, "no inline/dynamic imports in the generated module"
    assert "export interface DecideRegistryField {" in text
    assert "type: DecideRegistryFieldType;" in text
    assert "enum?: readonly string[];" in text
    assert "maxItems?: number;" in text
    assert "optionalStateFields: DecideRegistryField[];" in text
    for dp_id in NEW_DP_IDS:
        assert f'"{dp_id}": {{' in text
    assert 'name: "spec.ac_ids",' in text
    assert "maxItems: 128" in text
    assert 'enum: ["transient", "deterministic", "infra", "unknown"],' in text
    assert "signed: true" in text
    assert 'optionalStateFields: [' in text


def test_generated_ts_and_json_agree_on_the_optional_fields() -> None:
    doc = dpts.registry_snapshot()
    by_id = {point["id"]: point for point in doc["points"]}
    text = GENERATED_TS.read_text(encoding="utf-8")
    assert by_id["dp2-checkpoint-split"]["optional_state_fields"]
    for point in doc["points"]:
        for field in point["optional_state_fields"]:
            assert f'name: "{field["name"]}"' in text, field["name"]


# ---------------------------------------------------------------------------
# 6. AC-011: an invalid book sends nothing through the real CLI gate
# ---------------------------------------------------------------------------


def test_invalid_business_book_sends_nothing_via_cli(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    root = make_root(tmp_path)
    (root / ".mw").mkdir(parents=True, exist_ok=True)
    (root / ".mw" / "decide.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8", newline="\n"
    )
    backend = decision.FakeBackend([], default=None)
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: backend)

    book = legal_book("dp4-failure-handling")
    book["state"]["failure"]["kind"] = "boom"
    path = root / "book.json"
    path.write_text(json.dumps(book, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")

    args = type(
        "Args",
        (),
        {
            "subcommand": "decide",
            "decide_action": "run",
            "project": str(root),
            "json": False,
            "request_file": None,
            "dp": None,
            "book": str(path),
        },
    )()
    assert mw.cmd_decide(args) == 2
    assert backend.calls == [], "an invalid business book must not reach the transport"
    assert "zero HTTP" in capsys.readouterr().err
