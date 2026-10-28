"""test_decision_points.py — card T-01: registry / config read side / decide_for.

Hermetic pytest suite for ``packages/multi-workers/decision_points.py`` (key
mw-decision-substitution). Every test runs under ``tmp_path``; transports are
:class:`decision.FakeBackend` (no spawn, no network, no credentials) and the
decision archive is either absent (exact production state while card T-03 is
still open) or a local recorder injected through ``ARCHIVE_WRITER``.

Contract sources: design.md §2.1 (registry + import-time fail-loud), §2.2
(config L0..L7 + ``(st_mtime_ns, st_size)`` hot reload), §2.3 (11-step control
flow), spec.md §4 (24 dp ids/tiers), spec.md AC-001/002/005/011.
"""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402
import decision  # noqa: E402
import decision_points as dpts  # noqa: E402

#: spec.md §4, copied verbatim (id -> tier). ``dp13-commit-release`` is the
#: composite "P1/P0" cell; this registry takes the fail-closed P0 reading (see
#: the module docstring and the card report's residual section).
SPEC_TIERS: dict[str, str] = {
    "dp1-dispatch-type": "P2",
    "dp2-checkpoint-split": "P2",
    "dp3-worker-clarify": "P2",
    "dp4-failure-handling": "P1",
    "dp5-test-triage": "P2",
    "dp6-qg-verdict": "P1",
    "dp7-gate-failure": "P2",
    "dp8-scope-change": "P0",
    "dp9-model-select": "P2",
    "dp10-dependency": "P1",
    "dp11-credential": "P0",
    "dp12-destructive": "P0",
    "dp13-commit-release": "P0",
    "dp14-rule-conflict": "P0",
    "dp15-autopilot-gate": "P0",
    "dp16-goal": "P0",
    "dp17-spec-lock": "P1",
    "dp18-claim": "P1",
    "dp19-foreign-write": "P0",
    "dp20-stage-close": "P0",
    "dp21-refine": "P2",
    "dp22-debug-plan": "P2",
    "dp23-snapshot": "P2",
    "dp24-pi-trust": "P0",
    # spec §15 AC-027 (2026-10-21 ruling D): the automatic sign-off point.
    # W11 (2026-10-21) re-tiered it P1 -> P2 so the default `mw decide sign`
    # path asks jev (`auto-llm` fallback is now the exception, not the default).
    "dp25-signoff-conclusion": "P2",
}

CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch):
    for name in CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(dpts, "ARCHIVE_WRITER", None, raising=False)
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


class ArchiveRecorder:
    """Stand-in for ``decide_archive.append_decide`` (card T-03)."""

    def __init__(self) -> None:
        self.rows: list[dict] = []

    def __call__(self, **payload):
        self.rows.append(payload)
        return {"seq": len(self.rows)}


def write_table(project: pathlib.Path, points: object, *, version: int | None = 1) -> pathlib.Path:
    table: dict = {"points": points}
    if version is not None:
        table["version"] = version
    table["updated_at"] = "2026-10-20T00:00:00Z"
    table["updated_by"] = "human"
    path = project / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(table, ensure_ascii=False), encoding="utf-8")
    return path


def configured_client(
    tmp_path: pathlib.Path,
    *,
    results: list | None = None,
    default: object = None,
    confidence_source: str = decision.CONFIDENCE_SOURCE_API,
) -> tuple[decision.DecisionClient, decision.FakeBackend]:
    backend = decision.FakeBackend(
        results, confidence_source=confidence_source, default=default
    )
    cfg = decision.DecisionConfig(enabled=True)
    client = decision.DecisionClient(
        cfg=cfg, backend=backend, evidence_path=tmp_path / "triage-decisions.jsonl"
    )
    return client, backend


def answers_for(dp_id: str, *, value: object = None, confidence: float | None = 0.9) -> dict:
    """Build a normalized-shape answer payload covering every registry question.

    ``value=None`` means "pick the first legal choice / the score floor / a
    probability" per question, so the payload always satisfies the per-question
    value check in ``decide_for`` step 8 (a fixed literal cannot fit every dp's
    choice list). Dynamic choice questions (FIX-I) take their vocabulary from
    the request state, so the fixtures always ship ``c1`` as their first
    candidate.
    """
    dp_point = dpts.get_decision_point(dp_id)
    out: dict = {}
    for question in dp_point.questions:
        if question["type"] == decision.QUESTION_CHOICE:
            if "dynamic_choices" in question:
                val = "c1" if value is None else value
            else:
                val = question["choices"][0] if value is None else value
        elif question["type"] == decision.QUESTION_SCORE:
            val = question["min"]
        elif question["type"] == decision.QUESTION_NOUL:
            val = 0.9
        else:
            val = "answer text"
        out[str(question["id"])] = {"value": val, "confidence": confidence}
    return out


def ok_outcome(dp_id: str, *, confidence: float | None = 0.9, value: object = None) -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=True,
        reason=None,
        retryable=False,
        answers=answers_for(dp_id, value=value, confidence=confidence),
        latency_ms=3,
    )


def dp1_trigger(**overrides) -> dpts.Trigger:
    data = {
        "key": "key-1",
        "phase": "TASKS",
        "task_type": "coding",
        "requested_type": "coding",
        "risk": "mid",
        "risk_source": "machine",
        "authority_tier": "P2",
        "task_summary": "dispatch a worker for the registry card",
        "scope": {"write_scope": ["packages/multi-workers"], "file_extensions": [".py"]},
    }
    data.update(overrides)
    return dpts.Trigger.from_mapping(data, key="key-1")


def dp3_trigger(**overrides) -> dpts.Trigger:
    data = {
        "key": "key-1",
        "phase": "TASKS",
        "task_type": "coding",
        "risk": "mid",
        "risk_source": "machine",
        "authority_tier": "P2",
        "task_summary": "worker asks where the decide-points table lives",
        "ambiguity": {"kind": "fact", "question": "which file holds the decide points?"},
        "local_candidates": [{"id": "c1", "label": ".mw/decide-points.json"}],
    }
    data.update(overrides)
    return dpts.Trigger.from_mapping(data, key="key-1")


def install_test_dp(
    monkeypatch: pytest.MonkeyPatch,
    *,
    dp_id: str = "dp-test-controlflow",
    tier: str = "P2",
    executor=None,
    build_state=None,
) -> dpts.DecisionPoint:
    """Inject an ad-hoc dp (test-only) so executor branches are reachable."""
    dp_point = dpts.DecisionPoint(
        id=dp_id,
        tier=tier,
        default_enabled=(tier == "P2"),
        default_mode="auto",
        questions=({"id": "answer", "type": "choice", "choices": ["narrow", "split"]},),
        build_state=build_state
        or (lambda trigger: {"schema_version": 2, "decision_point": dp_id, "key": trigger.key}),
        executor=executor,
        questions_version="q-deadbeef",
        p0_consequences="test-only consequence" if tier == "P0" else None,
        description="test-only decision point",
    )
    monkeypatch.setitem(dpts._REGISTRY_BY_ID, dp_id, dp_point)
    return dp_point


def spy_encode_state(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []
    original = decision._encode_state

    def wrapper(state):
        calls.append(state)
        return original(state)

    monkeypatch.setattr(decision, "_encode_state", wrapper)
    return calls


# ---------------------------------------------------------------------------
# 1. Registry integrity (design §2.1, spec §4)
# ---------------------------------------------------------------------------


def test_registry_has_the_25_spec_ids_with_spec_tiers() -> None:
    assert len(dpts.DP_REGISTRY) == dpts.EXPECTED_DP_COUNT == 25
    ids = [dp_point.id for dp_point in dpts.DP_REGISTRY]
    assert ids == list(SPEC_TIERS), "registry order/ids must follow spec.md §4 + §15 AC-027"
    assert len(set(ids)) == 25, "ids must be unique"
    for dp_point in dpts.DP_REGISTRY:
        assert dp_point.tier == SPEC_TIERS[dp_point.id], dp_point.id
        assert dp_point.tier in dpts.TIERS
        assert dp_point.description


def test_registry_defaults_are_derived_from_tier() -> None:
    for dp_point in dpts.DP_REGISTRY:
        assert dp_point.default_enabled is (dp_point.tier == "P2"), dp_point.id
        assert dp_point.default_mode in dpts.MODES
        assert isinstance(dp_point.questions_version, str) and dp_point.questions_version
        assert dp_point.questions and isinstance(dp_point.questions, tuple)
        spec = dpts.questions_map(dp_point)
        assert set(spec) == {question["id"] for question in dp_point.questions}


def test_p2_executors_present_and_p0_consequences_declared() -> None:
    p2 = [dp_point for dp_point in dpts.DP_REGISTRY if dp_point.tier == "P2"]
    p0 = [dp_point for dp_point in dpts.DP_REGISTRY if dp_point.tier == "P0"]
    # Derived from SPEC_TIERS (the registry is the authority, W9 added dp25 to it).
    expected_p2 = sum(1 for tier in SPEC_TIERS.values() if tier == "P2")
    expected_p0 = sum(1 for tier in SPEC_TIERS.values() if tier == "P0")
    assert len(p2) == expected_p2, "every spec P2 point must be registered as P2"
    assert len(p0) == expected_p0, "dp13 composite cell counted as P0 => 10 P0 points"
    for dp_point in p2:
        assert callable(dp_point.executor), dp_point.id
    for dp_point in p0:
        assert isinstance(dp_point.p0_consequences, str) and dp_point.p0_consequences.strip(), dp_point.id


@pytest.mark.parametrize(
    "overrides",
    [
        {"tier": "P9"},
        {"tier": "P0", "p0_consequences": None},
        {"tier": "P0", "p0_consequences": "   "},
        {"tier": "P2", "executor": None},
        {"tier": "P1", "default_enabled": True},
        {"tier": "P2", "default_mode": "shadow"},
        {"tier": "P1", "questions": ()},
        {"tier": "P1", "questions": ({"id": "q1", "type": "not-a-type"},)},
        {"tier": "P1", "questions": ({"id": "q1", "type": "choice"},)},
        {"tier": "P1", "questions": ({"id": "q1", "type": "score", "min": 5, "max": 1},)},
        {"tier": "P1", "questions_version": ""},
        {"tier": "P1", "description": ""},
    ],
)


def test_decision_point_construction_fails_loud(overrides: dict) -> None:
    kwargs = {
        "id": "dp-bad",
        "tier": "P1",
        "default_enabled": False,
        "default_mode": "auto",
        "questions": ({"id": "q1", "type": "choice", "choices": ["a"]},),
        "build_state": lambda trigger: {"schema_version": 2},
        "executor": None,
        "questions_version": "abc123",
        "p0_consequences": None,
        "description": "bad point",
    }
    kwargs.update(overrides)
    with pytest.raises(ValueError):
        dpts.DecisionPoint(**kwargs)


def test_registry_level_validation_rejects_duplicates_and_wrong_size() -> None:
    duplicated = dpts.DP_REGISTRY[:-1] + (dpts.DP_REGISTRY[0],)
    with pytest.raises(ValueError, match="duplicate"):
        dpts._validate_registry(duplicated)
    with pytest.raises(ValueError, match="25"):
        dpts._validate_registry(dpts.DP_REGISTRY[:3])


def test_questions_version_is_a_content_hash() -> None:
    same = dpts._questions_version(({"id": "q1", "type": "choice", "choices": ["a", "b"]},))
    again = dpts._questions_version(({"id": "q1", "type": "choice", "choices": ["a", "b"]},))
    changed = dpts._questions_version(({"id": "q1", "type": "choice", "choices": ["a", "c"]},))
    assert same == again
    assert same != changed
    # Shape required by the archive writer (card T-03): q-<8 hex>.
    assert same.startswith("q-") and len(same) == 10
    for dp_point in dpts.DP_REGISTRY:
        assert dp_point.questions_version.startswith("q-")


# FIX-O: the four dps whose call sites are wired; the model-facing text on every
# one of their questions is the difference between a real answer and a guess.
WIRED_DP_IDS = (
    "dp1-dispatch-type",
    "dp2-checkpoint-split",
    "dp3-worker-clarify",
    "dp8-scope-change",
)

#: ``questions_version`` values captured before FIX-O added ``instructions`` /
#: ``labels`` / ``criteria``. They must not move: the hash covers the question
#: shape only (``id``/``type``/``choices``/``dynamic_choices``), so archived rows
#: and the ``state.questions_version`` handshake stay valid.
QUESTIONS_VERSION_BEFORE_FIX_O: dict[str, str] = {
    "dp1-dispatch-type": "q-09d3aad3",
    "dp2-checkpoint-split": "q-ba8e970f",
    "dp3-worker-clarify": "q-fcbd3847",
    "dp4-failure-handling": "q-b93176a8",
    "dp5-test-triage": "q-cc104f59",
    "dp6-qg-verdict": "q-16b4bb5c",
    "dp7-gate-failure": "q-c8e23cc7",
    "dp8-scope-change": "q-e5d928e8",
    "dp9-model-select": "q-bc7918b9",
    "dp10-dependency": "q-3bbd9e44",
    "dp11-credential": "q-080722b1",
    "dp12-destructive": "q-02f737ab",
    "dp13-commit-release": "q-6d26173d",
    "dp14-rule-conflict": "q-b667b8d3",
    "dp15-autopilot-gate": "q-09e25bec",
    "dp16-goal": "q-ba34304c",
    "dp17-spec-lock": "q-f81bd06d",
    "dp18-claim": "q-094db8cc",
    "dp19-foreign-write": "q-df9c727d",
    "dp20-stage-close": "q-30afd59f",
    "dp21-refine": "q-ddd23fe2",
    "dp22-debug-plan": "q-a1ed6dbc",
    "dp23-snapshot": "q-f5cecffb",
    "dp24-pi-trust": "q-20850ffa",
    # W9 / spec §15 AC-027: new point, so there is no pre-FIX-O value to preserve.
    "dp25-signoff-conclusion": "q-cad37e2a",
}


def test_wired_questions_carry_instructions_and_choice_labels() -> None:
    """FIX-O case 1: no wired question reaches the model without real text."""
    for dp_id in WIRED_DP_IDS:
        for question in dpts.get_decision_point(dp_id).questions:
            qid = question["id"]
            instructions = question.get("instructions")
            assert isinstance(instructions, str) and instructions.strip(), (dp_id, qid)
            if question["type"] != decision.QUESTION_CHOICE:
                continue
            if question.get("dynamic_choices") is not None:
                continue
            labels = question.get("labels")
            assert isinstance(labels, dict), (dp_id, qid)
            assert set(labels) == set(question["choices"]), (dp_id, qid)
            assert all(isinstance(label, str) and label.strip() for label in labels.values())


def test_dp3_candidate_is_dynamic_without_labels_and_answerable_has_true_false() -> None:
    """FIX-O case 2: dynamic enum renders from state; noul carries both outcomes."""
    spec = dpts.questions_map("dp3-worker-clarify")

    assert spec["candidate"]["dynamic_choices"] == "local_candidates"
    assert "labels" not in spec["candidate"]
    assert spec["candidate"]["instructions"].strip()

    assert set(spec["answerable"]["criteria"]) == {"true", "false"} == dpts.NOUL_CRITERIA_KEYS
    assert all(isinstance(value, str) and value.strip() for value in spec["answerable"]["criteria"].values())
    assert spec["answerable"]["instructions"].strip()


@pytest.mark.parametrize(
    "question",
    [
        # instructions present but empty
        {"id": "q1", "type": "noul", "instructions": ""},
        # labels keys do not match choices
        {"id": "q1", "type": "choice", "choices": ["a", "b"], "labels": {"a": "x"}},
        # labels on a dynamic choice (the enum comes from state)
        {"id": "q1", "type": "choice", "dynamic_choices": "candidates", "labels": {"c1": "x"}},
        # noul criteria missing the "false" outcome
        {"id": "q1", "type": "noul", "criteria": {"true": "yes"}},
    ],
)
def test_question_text_validation_rejects_bad_shapes(question: dict) -> None:
    """FIX-O case 3: every malformed text/criteria shape fails loud."""
    with pytest.raises(ValueError):
        dpts._validate_question("dp-bad", question, set())


def test_questions_version_is_unchanged_by_the_fix_o_text() -> None:
    """FIX-O case 4: dp3 stays ``q-fcbd3847``; no other dp moves either."""
    assert dpts.get_decision_point("dp3-worker-clarify").questions_version == "q-fcbd3847"
    assert {
        dp_point.id: dp_point.questions_version for dp_point in dpts.DP_REGISTRY
    } == QUESTIONS_VERSION_BEFORE_FIX_O


# ---------------------------------------------------------------------------
# 2. Config read side: L0..L7 (design §2.2)
# ---------------------------------------------------------------------------


def test_layer_l0_missing_file_means_registry_defaults(tmp_path: pathlib.Path) -> None:
    view = dpts.load_points_config(tmp_path)
    assert view.layer == "L0"
    assert view.exists is False
    assert view.points == {}
    assert view.warnings == ()
    assert view.effective(dpts.get_decision_point("dp3-worker-clarify")).enabled is True
    assert view.effective(dpts.get_decision_point("dp8-scope-change")).enabled is False


def test_layer_l1_invalid_json_falls_back_to_defaults(tmp_path: pathlib.Path) -> None:
    path = tmp_path / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True)
    path.write_text("{ not json", encoding="utf-8")
    view = dpts.load_points_config(tmp_path)
    assert view.layer == "L1"
    assert view.exists is True
    assert any("invalid JSON" in warning for warning in view.warnings)
    assert view.effective(dpts.get_decision_point("dp3-worker-clarify")).enabled is True


def test_layer_l1_non_object_points_falls_back_to_defaults(tmp_path: pathlib.Path) -> None:
    path = tmp_path / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"version": 1, "points": []}), encoding="utf-8")
    view = dpts.load_points_config(tmp_path)
    assert view.layer == "L1"
    assert view.points == {}


def test_layer_l2_non_object_row_disables_only_that_dp(tmp_path: pathlib.Path) -> None:
    write_table(tmp_path, {"dp3-worker-clarify": True})
    view = dpts.load_points_config(tmp_path)
    assert view.layer == "L2"
    dp3 = dpts.get_decision_point("dp3-worker-clarify")
    assert view.effective(dp3).enabled is False
    # untouched dp keeps the registry default
    dp9 = dpts.get_decision_point("dp9-model-select")
    assert view.effective(dp9).enabled is True
    assert view.effective(dp9).source == "default"


def test_layer_l3_field_type_error_disables_that_dp(tmp_path: pathlib.Path) -> None:
    write_table(tmp_path, {"dp3-worker-clarify": {"tier": "P2", "enabled": True, "mode": 5}})
    view = dpts.load_points_config(tmp_path)
    assert view.layer == "L3"
    assert view.effective(dpts.get_decision_point("dp3-worker-clarify")).enabled is False
    assert any("mode" in warning for warning in view.warnings)


def test_layer_l4_illegal_tier_keeps_registry_tier(tmp_path: pathlib.Path) -> None:
    write_table(tmp_path, {"dp4-failure-handling": {"tier": "P9", "enabled": True, "mode": "suggest"}})
    view = dpts.load_points_config(tmp_path)
    assert view.layer == "L4"
    effective = view.effective(dpts.get_decision_point("dp4-failure-handling"))
    assert effective.enabled is True
    assert effective.mode == "suggest"
    assert effective.tier == "P1", "registry tier wins over the table column"
    assert effective.table_tier == "P9"


def test_layer_l5_non_boolean_enabled_disables_that_dp(tmp_path: pathlib.Path) -> None:
    write_table(tmp_path, {"dp3-worker-clarify": {"tier": "P2", "enabled": "yes", "mode": "auto"}})
    view = dpts.load_points_config(tmp_path)
    assert view.layer == "L5"
    effective = view.effective(dpts.get_decision_point("dp3-worker-clarify"))
    assert effective.enabled is False
    assert any("enabled" in warning for warning in view.warnings)


def test_layer_l6_unknown_dp_is_kept_and_marked_orphaned(tmp_path: pathlib.Path) -> None:
    write_table(tmp_path, {"dp99-retired": {"tier": "P2", "enabled": True, "mode": "auto"}})
    view = dpts.load_points_config(tmp_path)
    assert view.layer == "L6"
    orphan = view.row("dp99-retired")
    assert orphan is not None and orphan.orphaned is True and orphan.enabled is True
    assert view.orphaned_ids() == ("dp99-retired",)
    # orphan rows never leak into registered lookups
    assert view.effective(dpts.get_decision_point("dp3-worker-clarify")).enabled is True
    with pytest.raises(decision.DecisionInputError):
        dpts.decide_for("dp99-retired", {"key": "k"}, tmp_path, archive=False)


def test_layer_l7_tier_conflict_keeps_registry_tier(tmp_path: pathlib.Path) -> None:
    write_table(tmp_path, {"dp3-worker-clarify": {"tier": "P0", "enabled": True, "mode": "auto"}})
    view = dpts.load_points_config(tmp_path)
    assert view.layer == "L7"
    effective = view.effective(dpts.get_decision_point("dp3-worker-clarify"))
    assert effective.tier == "P2"
    assert effective.table_tier == "P0"
    assert any("registry" in warning for warning in view.warnings)


def test_missing_version_is_reported_but_harmless(tmp_path: pathlib.Path) -> None:
    write_table(tmp_path, {"dp3-worker-clarify": {"tier": "P2", "enabled": False}}, version=None)
    view = dpts.load_points_config(tmp_path)
    assert view.layer == "OK", "a missing version is advisory, not a degradation layer"
    assert any("version" in warning for warning in view.warnings)
    assert view.version is None
    assert view.effective(dpts.get_decision_point("dp3-worker-clarify")).enabled is False


def test_l6_orphan_with_non_object_row_is_kept(tmp_path: pathlib.Path) -> None:
    write_table(tmp_path, {"dp99-retired": "yes"})
    view = dpts.load_points_config(tmp_path)
    orphan = view.row("dp99-retired")
    assert orphan is not None and orphan.orphaned is True and orphan.enabled is False


def test_reader_never_raises_on_undecodable_bytes(tmp_path: pathlib.Path) -> None:
    path = tmp_path / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff\xfe\x00\x00not utf-8")
    view = dpts.load_points_config(tmp_path)  # must not raise
    assert view.layer == "L1"
    assert view.effective(dpts.get_decision_point("dp3-worker-clarify")).enabled is True


def test_reader_never_raises_when_project_dir_is_missing(tmp_path: pathlib.Path) -> None:
    view = dpts.load_points_config(tmp_path / "does" / "not" / "exist")
    assert view.layer == "L0"
    assert view.effective(dpts.get_decision_point("dp3-worker-clarify")).enabled is True


# ---------------------------------------------------------------------------
# 3. Hot reload: (st_mtime_ns, st_size) with same-second rewrites (design D-022)
# ---------------------------------------------------------------------------


def _ns(second: int, fraction_ns: int = 0) -> int:
    return second * 1_000_000_000 + fraction_ns


def test_same_second_same_size_rewrite_is_observed(tmp_path: pathlib.Path) -> None:
    project = tmp_path
    base = _ns(1_700_000_000, 100_000_000)
    # "false" -> "true " keeps st_size identical, so st_mtime_ns must do the work.
    text_off = '{"version": 1, "points": {"dp3-worker-clarify": {"tier": "P2", "enabled": false}}}'
    text_on = '{"version": 1, "points": {"dp3-worker-clarify": {"tier": "P2", "enabled": true }}}'
    assert len(text_off) == len(text_on)
    path = project / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True)
    path.write_text(text_off, encoding="utf-8")
    import os

    os.utime(path, ns=(base, base))
    first = dpts.load_points_config(project)
    assert first.layer == "OK"
    assert first.effective(dpts.get_decision_point("dp3-worker-clarify")).enabled is False

    path.write_text(text_on, encoding="utf-8")
    later = base + 400_000_000  # same wall-clock second, different nanosecond
    os.utime(path, ns=(later, later))
    second = dpts.load_points_config(project)
    assert second.signature is not None and first.signature is not None
    assert second.signature[1] == first.signature[1], "sizes must match for this proof"
    assert second.signature[0] != first.signature[0]
    assert second.effective(dpts.get_decision_point("dp3-worker-clarify")).enabled is True


def test_cache_hit_reuses_the_parsed_view(tmp_path: pathlib.Path) -> None:
    write_table(tmp_path, {"dp3-worker-clarify": {"tier": "P2", "enabled": False}})
    first = dpts.load_points_config(tmp_path)
    second = dpts.load_points_config(tmp_path)
    assert first is second
    dpts.clear_points_config_cache()
    third = dpts.load_points_config(tmp_path)
    assert third is not first
    assert third.layer == "OK"


def test_cache_invalidated_when_file_appears(tmp_path: pathlib.Path) -> None:
    project = tmp_path
    assert dpts.load_points_config(project).layer == "L0"
    write_table(project, {"dp3-worker-clarify": {"tier": "P2", "enabled": False}})
    view = dpts.load_points_config(project)
    assert view.layer == "OK"
    assert view.effective(dpts.get_decision_point("dp3-worker-clarify")).enabled is False


# ---------------------------------------------------------------------------
# 4. decide_for: the 11-step control flow (design §2.3)
# ---------------------------------------------------------------------------


def test_step1_unknown_dp_id_raises_input_error(tmp_path: pathlib.Path) -> None:
    with pytest.raises(decision.DecisionInputError):
        dpts.decide_for("dp1", {"key": "k"}, tmp_path, archive=False)


def test_step2_disabled_p1_returns_before_state_or_backend(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    encode_calls = spy_encode_state(monkeypatch)
    build_calls: list[object] = []
    dp_point = dpts.get_decision_point("dp4-failure-handling")
    spied = dpts.DecisionPoint(
        id=dp_point.id,
        tier=dp_point.tier,
        default_enabled=dp_point.default_enabled,
        default_mode=dp_point.default_mode,
        questions=dp_point.questions,
        build_state=lambda trigger: build_calls.append(trigger) or {},
        executor=dp_point.executor,
        questions_version=dp_point.questions_version,
        p0_consequences=dp_point.p0_consequences,
        description=dp_point.description,
    )
    monkeypatch.setitem(dpts._REGISTRY_BY_ID, dp_point.id, spied)
    client, backend = configured_client(tmp_path, default=ok_outcome(dp_point.id))

    outcome = dpts.decide_for(
        dp_point.id, {"key": "k1"}, tmp_path, client=client, archive=False
    )

    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "disabled"
    assert outcome.decision_id == "dp4-failure-handling:k1"
    assert backend.calls == [], "disabled path must not reach the backend (AC-001)"
    assert encode_calls == [], "disabled path must return before _encode_state"
    assert build_calls == [], "disabled path must return before build_state"
    assert not (tmp_path / dpts.DECISIONS_RELATIVE_PATH).exists()
    assert not (tmp_path / "triage-decisions.jsonl").exists(), "no transport evidence line either"


def test_step2_explicit_enabled_false_on_p2_dp(tmp_path: pathlib.Path) -> None:
    client, backend = configured_client(tmp_path, default=ok_outcome("dp3-worker-clarify"))
    write_table(tmp_path, {"dp3-worker-clarify": {"tier": "P2", "enabled": False, "mode": "auto"}})
    outcome = dpts.decide_for(
        "dp3-worker-clarify", dp3_trigger(), tmp_path, client=client, archive=False
    )
    assert outcome.escalated_reason == "disabled"
    assert backend.calls == []


def test_step3_row_mode_is_used(tmp_path: pathlib.Path) -> None:
    write_table(tmp_path, {"dp3-worker-clarify": {"tier": "P2", "enabled": True, "mode": "suggest"}})
    client, backend = configured_client(tmp_path, default=ok_outcome("dp3-worker-clarify"))
    outcome = dpts.decide_for(
        "dp3-worker-clarify", dp3_trigger(), tmp_path, client=client, archive=False
    )
    assert outcome.mode == "suggest"
    assert outcome.status == "suggested"
    assert backend.calls, "suggest mode still asks the transport"


def test_step4_transport_disabled_escalates_without_asking(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    encode_calls = spy_encode_state(monkeypatch)
    outcome = dpts.decide_for("dp3-worker-clarify", dp3_trigger(), tmp_path, archive=False)
    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "unavailable"
    assert outcome.transport_reason == decision.REASON_DISABLED
    assert encode_calls == []
    assert "decide.json" in outcome.detail
    assert not (tmp_path / "triage-decisions.jsonl").exists()


def test_step5_missing_required_fields_lists_names_only(tmp_path: pathlib.Path) -> None:
    client, backend = configured_client(tmp_path, default=ok_outcome("dp3-worker-clarify"))
    trigger = dp3_trigger(task_summary="   ")  # blank == missing (spec Q5.5)
    outcome = dpts.decide_for(
        "dp3-worker-clarify", trigger, tmp_path, client=client, archive=False
    )
    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "input-incomplete"
    assert "task_summary" in outcome.detail
    assert backend.calls == []
    assert not (tmp_path / "triage-decisions.jsonl").exists()
    assert "which file holds the decide points?" not in outcome.detail


def test_step5_missing_nested_field_and_builder_crash(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client, backend = configured_client(tmp_path, default=ok_outcome("dp3-worker-clarify"))
    trigger = dp3_trigger(ambiguity={"kind": "fact"})
    outcome = dpts.decide_for(
        "dp3-worker-clarify", trigger, tmp_path, client=client, archive=False
    )
    assert outcome.escalated_reason == "input-incomplete"
    assert "ambiguity.question" in outcome.detail
    assert backend.calls == []

    classes = dpts.DecisionPoint(
        id="dp-broken-builder",
        tier="P1",
        default_enabled=False,
        default_mode="auto",
        questions=({"id": "answer", "type": "choice", "choices": ["a"]},),
        build_state=lambda trigger: (_ for _ in ()).throw(RuntimeError("boom")),
        executor=None,
        questions_version="deadbeef",
        p0_consequences=None,
        description="builder raises",
    )
    monkeypatch.setitem(dpts._REGISTRY_BY_ID, classes.id, classes)
    write_table(tmp_path, {classes.id: {"tier": "P1", "enabled": True, "mode": "auto"}})
    crash = dpts.decide_for(classes.id, {"key": "k"}, tmp_path, client=client, archive=False)
    assert crash.escalated_reason == "input-incomplete"
    assert "RuntimeError" in crash.detail
    assert "boom" not in crash.detail


def test_step6_drops_optional_l1_before_sending(tmp_path: pathlib.Path) -> None:
    client, backend = configured_client(tmp_path, default=ok_outcome("dp1-dispatch-type"))
    trigger = dp1_trigger(history={"events": ["e" * 3000]})
    outcome = dpts.decide_for(
        "dp1-dispatch-type", trigger, tmp_path, client=client, archive=False
    )
    assert outcome.status == "acted" or outcome.status == "escalated"
    assert backend.calls, "optional L1 must be dropped so the call still happens"
    sent = backend.calls[0]["state"]
    assert "history" not in sent
    assert "history" in outcome.truncated
    assert len(decision._encode_state(sent)) <= dpts.MAX_STATE_BYTES


def test_step6_halves_required_l1_when_still_oversized(tmp_path: pathlib.Path) -> None:
    client, backend = configured_client(tmp_path, default=ok_outcome("dp1-dispatch-type"))
    trigger = dp1_trigger(task_summary="s" * 1800)
    outcome = dpts.decide_for(
        "dp1-dispatch-type", trigger, tmp_path, client=client, archive=False
    )
    assert backend.calls, outcome.detail
    sent = backend.calls[0]["state"]
    assert len(sent["task_summary"]) < 1800
    assert any("task_summary" in path for path in outcome.truncated)
    assert len(decision._encode_state(sent)) <= dpts.MAX_STATE_BYTES


def test_step6_refuses_when_required_input_stays_oversized(tmp_path: pathlib.Path) -> None:
    client, backend = configured_client(tmp_path, default=ok_outcome("dp1-dispatch-type"))
    trigger = dp1_trigger(task_summary="s" * 5000)
    outcome = dpts.decide_for(
        "dp1-dispatch-type", trigger, tmp_path, client=client, archive=False
    )
    # design §2.3 step 6 / D-028: an oversized payload is its own reason, not a
    # disguised input-incomplete (the state is complete, it just cannot be sent).
    assert outcome.escalated_reason == "input-oversize"
    assert f"{dpts.MAX_STATE_BYTES}" in outcome.detail
    assert "task_summary" in outcome.detail
    assert any("task_summary" in path for path in outcome.truncated)
    assert backend.calls == []


def test_step7_transport_unavailable_passes_reason_through(tmp_path: pathlib.Path) -> None:
    recorder = ArchiveRecorder()
    dpts.ARCHIVE_WRITER = recorder
    results = [
        decision.BackendOutcome(
            available=False,
            reason=decision.REASON_TIMEOUT,
            retryable=False,
            answers=None,
            latency_ms=20_000,
            detail="hard timeout",
        )
    ]
    client, backend = configured_client(tmp_path, results=results)
    outcome = dpts.decide_for(
        "dp3-worker-clarify", dp3_trigger(), tmp_path, client=client, archive=True
    )
    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "unavailable"
    assert outcome.transport_reason == decision.REASON_TIMEOUT
    assert len(backend.calls) == 1
    assert outcome.archived is True
    row = recorder.rows[-1]
    assert row["available"] is False
    assert row["authority"] == "human"
    assert row["escalated_reason"] == "unavailable"
    assert row["acted"] is False
    assert row["reason"] == decision.REASON_TIMEOUT
    assert str(row["path"]).endswith("decisions.jsonl")


# ---------------------------------------------------------------------------
# 4b. escalated_reason: one vocabulary across the two modules (design D-030)
# ---------------------------------------------------------------------------


ESCALATED_REASONS_SPEC = frozenset(
    {
        "disabled",
        "unavailable",
        "input-incomplete",
        "input-oversize",
        "low-confidence",
        "over-authority",
        "p0",
    }
)


def test_escalated_reason_vocabulary_is_frozen() -> None:
    assert dpts.ESCALATED_REASONS == ESCALATED_REASONS_SPEC
    assert not hasattr(dpts, "_ARCHIVE_ESCALATED_REASONS"), (
        "the archive translation table must be gone: it disguised disabled as unavailable"
    )


def test_escalated_reason_vocabulary_matches_the_archive_layer() -> None:
    decide_archive = pytest.importorskip("decide_archive")
    legacy = decide_archive._ESCALATED_REASONS_LEGACY
    assert legacy == frozenset({"input-invalid"}), "only input-invalid may be legacy read compat"
    assert decide_archive._ESCALATED_REASONS == dpts.ESCALATED_REASONS | legacy, (
        "decide_for and append_decide must validate the same vocabulary"
    )
    assert not (dpts.ESCALATED_REASONS & legacy), (
        "decision_points must never produce the legacy read-only value"
    )
    assert decide_archive._ESCALATED_REASONS_CORE == dpts.ESCALATED_REASONS


def test_archive_payload_forwards_the_reason_verbatim(tmp_path: pathlib.Path) -> None:
    """No translation: the archived reason equals the escalation reason."""
    recorder = ArchiveRecorder()
    dpts.ARCHIVE_WRITER = recorder
    client, _backend = configured_client(
        tmp_path, results=[ok_outcome("dp3-worker-clarify", confidence=0.1)]
    )
    outcome = dpts.decide_for(
        "dp3-worker-clarify", dp3_trigger(), tmp_path, client=client, archive=True
    )
    assert outcome.escalated_reason == "low-confidence"
    row = recorder.rows[-1]
    assert row["escalated_reason"] == outcome.escalated_reason
    assert row["duplicate"] == "existing", "design D-032: replay instead of raising"


def test_step8_api_confidence_below_floor_escalates(tmp_path: pathlib.Path) -> None:
    client, backend = configured_client(
        tmp_path, results=[ok_outcome("dp3-worker-clarify", confidence=0.2)]
    )
    outcome = dpts.decide_for(
        "dp3-worker-clarify", dp3_trigger(), tmp_path, client=client, archive=False
    )
    assert outcome.escalated_reason == "low-confidence"
    assert "min_confidence" in outcome.detail
    assert len(backend.calls) == 1


def test_step8_model_self_report_confidence_is_ignored_and_acts(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """design D-031: ``confidence_source != api`` must not gate nor escalate.

    B2 backends return ``model-self-report``; escalating there would make every
    P2 auto decision dead on arrival.
    """
    recorder = ArchiveRecorder()
    dpts.ARCHIVE_WRITER = recorder
    install_test_dp(monkeypatch, executor=lambda answers, trigger: "narrow")
    write_table(tmp_path, {"dp-test-controlflow": {"tier": "P2", "enabled": True, "mode": "auto"}})
    client, backend = configured_client(
        tmp_path,
        results=[ok_outcome("dp-test-controlflow", confidence=0.01)],
        confidence_source=decision.CONFIDENCE_SOURCE_MODEL,
    )
    outcome = dpts.decide_for(
        "dp-test-controlflow",
        dpts.Trigger(trigger_id="selfreport1", key="k1"),
        tmp_path,
        client=client,
        archive=True,
    )
    assert outcome.status == "acted", outcome.detail
    assert outcome.escalated_reason is None
    assert outcome.actual_action == "narrow"
    assert len(backend.calls) == 1
    row = recorder.rows[-1]
    assert row["authority"] == "binding"
    assert row["acted"] is True
    assert row["escalated_reason"] is None


def test_step8_unknown_confidence_source_is_ignored_and_suggests(tmp_path: pathlib.Path) -> None:
    client, _backend = configured_client(
        tmp_path,
        results=[ok_outcome("dp3-worker-clarify", confidence=None)],
        confidence_source=decision.CONFIDENCE_SOURCE_UNKNOWN,
    )
    write_table(tmp_path, {"dp3-worker-clarify": {"tier": "P2", "enabled": True, "mode": "suggest"}})
    outcome = dpts.decide_for(
        "dp3-worker-clarify", dp3_trigger(), tmp_path, client=client, archive=False
    )
    assert outcome.status == "suggested", outcome.detail
    assert outcome.escalated_reason is None


def test_step8_illegal_choice_value_escalates_low_confidence(tmp_path: pathlib.Path) -> None:
    recorder = ArchiveRecorder()
    dpts.ARCHIVE_WRITER = recorder
    bad_answers = {
        "answer_kind": {"value": "not-a-choice", "confidence": 0.99},
        "answerable": {"value": 0.9},
        "candidate": {"value": "c1", "confidence": 0.99},
    }
    client, backend = configured_client(
        tmp_path,
        results=[
            decision.BackendOutcome(
                available=True,
                reason=None,
                retryable=False,
                answers=bad_answers,
                latency_ms=2,
            )
        ],
    )
    outcome = dpts.decide_for(
        "dp3-worker-clarify", dp3_trigger(), tmp_path, client=client, archive=True
    )
    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "low-confidence"
    assert "answer_kind" in outcome.detail
    assert "not-a-choice" not in outcome.detail, "answer values are L2 material"
    assert len(backend.calls) == 1
    row = recorder.rows[-1]
    assert row["escalated_reason"] == "low-confidence"
    assert row["available"] is False and row["answer"] is None
    assert row["reason"] == decision.REASON_BAD_RESPONSE


def test_step8_missing_confidence_escalates(tmp_path: pathlib.Path) -> None:
    client, _backend = configured_client(
        tmp_path, results=[ok_outcome("dp3-worker-clarify", confidence=None)]
    )
    outcome = dpts.decide_for(
        "dp3-worker-clarify", dp3_trigger(), tmp_path, client=client, archive=False
    )
    assert outcome.escalated_reason == "low-confidence"


def test_step9_suggest_archives_advice_without_acting(tmp_path: pathlib.Path) -> None:
    recorder = ArchiveRecorder()
    dpts.ARCHIVE_WRITER = recorder
    write_table(tmp_path, {"dp3-worker-clarify": {"tier": "P2", "enabled": True, "mode": "suggest"}})
    client, _backend = configured_client(
        tmp_path, results=[ok_outcome("dp3-worker-clarify")]
    )
    outcome = dpts.decide_for(
        "dp3-worker-clarify", dp3_trigger(), tmp_path, client=client, archive=True
    )
    assert outcome.status == "suggested"
    assert outcome.escalated_reason is None
    assert outcome.actual_action is None
    assert outcome.state_digest and len(outcome.state_digest) == 16
    row = recorder.rows[-1]
    assert row["authority"] == "advisory"
    assert row["acted"] is False
    assert row["mode"] == "suggest"
    assert row["actual_action"] is None
    assert row["answer"]


def test_step10_auto_executes_and_archives_binding_row(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = ArchiveRecorder()
    dpts.ARCHIVE_WRITER = recorder
    seen: list[tuple] = []

    def executor(answers: dict, trigger: dpts.Trigger) -> str:
        seen.append((answers, trigger))
        return "narrow"

    install_test_dp(monkeypatch, executor=executor)
    write_table(tmp_path, {"dp-test-controlflow": {"tier": "P2", "enabled": True, "mode": "auto"}})
    client, backend = configured_client(
        tmp_path, results=[ok_outcome("dp-test-controlflow", value="narrow")]
    )
    outcome = dpts.decide_for(
        "dp-test-controlflow",
        dpts.Trigger(trigger_id="ckpt1", key="k1"),
        tmp_path,
        client=client,
        archive=True,
    )
    assert outcome.status == "acted"
    assert outcome.escalated_reason is None
    assert outcome.actual_action == "narrow"
    assert outcome.decision_id == "dp-test-controlflow:ckpt1"
    assert seen and seen[-1][1].trigger_id == "ckpt1"
    assert len(backend.calls) == 1
    row = recorder.rows[-1]
    assert row["authority"] == "binding"
    assert row["acted"] is True
    assert row["actual_action"] == "narrow"
    assert row["mode"] == "auto"
    assert row["available"] is True
    assert row["state"]


def test_step11_executor_failure_escalates_over_authority(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    recorder = ArchiveRecorder()
    dpts.ARCHIVE_WRITER = recorder

    def executor(answers: dict, trigger: dpts.Trigger) -> str:
        raise RuntimeError("executor exploded")

    install_test_dp(monkeypatch, executor=executor)
    write_table(tmp_path, {"dp-test-controlflow": {"tier": "P2", "enabled": True, "mode": "auto"}})
    client, _backend = configured_client(
        tmp_path, results=[ok_outcome("dp-test-controlflow")]
    )
    outcome = dpts.decide_for(
        "dp-test-controlflow", {"key": "k"}, tmp_path, client=client, archive=True
    )
    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "over-authority"
    assert outcome.actual_action is None
    assert "RuntimeError" in outcome.detail
    row = recorder.rows[-1]
    assert row["authority"] == "human"
    assert row["acted"] is False
    assert row["escalated_reason"] == "over-authority"


def test_auto_mode_without_executor_escalates(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    install_test_dp(monkeypatch, tier="P1", executor=None)
    write_table(tmp_path, {"dp-test-controlflow": {"tier": "P1", "enabled": True, "mode": "auto"}})
    client, _backend = configured_client(
        tmp_path, results=[ok_outcome("dp-test-controlflow")]
    )
    outcome = dpts.decide_for(
        "dp-test-controlflow", {"key": "k"}, tmp_path, client=client, archive=False
    )
    assert outcome.escalated_reason == "over-authority"
    assert "no executor" in outcome.detail


def test_archive_import_error_degrades_to_no_row(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # ``None`` in sys.modules makes ``import decide_archive`` raise ImportError.
    monkeypatch.setitem(sys.modules, "decide_archive", None)
    install_test_dp(monkeypatch, executor=lambda answers, trigger: "narrow")
    write_table(tmp_path, {"dp-test-controlflow": {"tier": "P2", "enabled": True, "mode": "auto"}})
    client, _backend = configured_client(
        tmp_path, results=[ok_outcome("dp-test-controlflow")]
    )
    outcome = dpts.decide_for(
        "dp-test-controlflow", {"key": "k"}, tmp_path, client=client, archive=True
    )
    assert outcome.status == "acted"
    assert outcome.archived is False
    assert not (tmp_path / dpts.DECISIONS_RELATIVE_PATH).exists()


def test_archive_writer_integration_writes_one_decide_row(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    pytest.importorskip("decide_archive")
    install_test_dp(monkeypatch, executor=lambda answers, trigger: "narrow")
    write_table(tmp_path, {"dp-test-controlflow": {"tier": "P2", "enabled": True, "mode": "auto"}})
    client, _backend = configured_client(
        tmp_path, results=[ok_outcome("dp-test-controlflow")]
    )
    outcome = dpts.decide_for(
        "dp-test-controlflow", dpts.Trigger(trigger_id="run1", key="k"), tmp_path,
        client=client, archive=True,
    )
    assert outcome.status == "acted"
    assert outcome.archived is True
    archive = tmp_path / dpts.DECISIONS_RELATIVE_PATH
    rows = [json.loads(line) for line in archive.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == 1
    row = rows[0]
    assert row["kind"] == "decide"
    assert row["decision_id"] == "dp-test-controlflow:run1"
    assert row["authority"] == "binding" and row["acted"] is True
    assert row["questions_version"] == "q-deadbeef"
    assert row["state_digest"] == outcome.state_digest
    assert row["outcome"] == "pending"


def test_repeated_trigger_replays_the_existing_row(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """design D-032: a replay returns the prior row, appends nothing, raises nothing."""
    pytest.importorskip("decide_archive")
    install_test_dp(monkeypatch, executor=lambda answers, trigger: "narrow")
    write_table(tmp_path, {"dp-test-controlflow": {"tier": "P2", "enabled": True, "mode": "auto"}})
    client, backend = configured_client(
        tmp_path, default=ok_outcome("dp-test-controlflow")
    )
    trigger = dpts.Trigger(trigger_id="replay1", key="k")
    archive = tmp_path / dpts.DECISIONS_RELATIVE_PATH

    first = dpts.decide_for("dp-test-controlflow", trigger, tmp_path, client=client, archive=True)
    assert first.status == "acted" and first.archived is True
    assert "note=duplicate-replay" not in first.detail
    size_before = archive.stat().st_size
    rows_before = [line for line in archive.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows_before) == 1

    second = dpts.decide_for("dp-test-controlflow", trigger, tmp_path, client=client, archive=True)

    assert second.status == "acted", "a replay must not raise or escalate"
    assert second.decision_id == first.decision_id == "dp-test-controlflow:replay1"
    assert second.archived is True
    assert "note=duplicate-replay" in second.detail
    assert archive.stat().st_size == size_before, "a replay must not append a row"
    rows_after = [line for line in archive.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows_after) == 1
    assert json.loads(rows_after[0])["decision_id"] == "dp-test-controlflow:replay1"
    assert len(backend.calls) == 2, "the replay still asks the transport once more"


def test_pre_transport_escalations_write_no_archive_row(tmp_path: pathlib.Path) -> None:
    recorder = ArchiveRecorder()
    dpts.ARCHIVE_WRITER = recorder
    dpts.decide_for("dp4-failure-handling", {"key": "k"}, tmp_path, archive=True)
    dpts.decide_for("dp3-worker-clarify", dp3_trigger(task_summary=""), tmp_path, archive=True)
    assert recorder.rows == []


def test_state_digest_is_python_computed_sha16(tmp_path: pathlib.Path) -> None:
    import hashlib

    client, backend = configured_client(
        tmp_path, results=[ok_outcome("dp3-worker-clarify")]
    )
    outcome = dpts.decide_for(
        "dp3-worker-clarify", dp3_trigger(), tmp_path, client=client, archive=False
    )
    sent = backend.calls[0]["state"]
    expected = hashlib.sha256(decision._encode_state(sent)).hexdigest()[:16]
    assert outcome.state_digest == expected
    assert len(outcome.state_digest) == 16


def test_conflict_free_off_path_is_zero_spawn(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-001: disable == zero perturbation — no subprocess, no state encoding."""
    spawns: list[tuple] = []

    def guard(name):
        def wrapper(*args, **kwargs):
            spawns.append((name, args))
            raise AssertionError(f"disabled decision attempted {name}")

        return wrapper

    monkeypatch.setattr("subprocess.Popen", guard("Popen"))
    monkeypatch.setattr("subprocess.run", guard("run"))
    encode_calls = spy_encode_state(monkeypatch)

    outcome = dpts.decide_for("dp4-failure-handling", {"key": "k"}, tmp_path, archive=True)
    assert outcome.escalated_reason == "disabled"
    assert spawns == []
    assert encode_calls == []


# ---------------------------------------------------------------------------
# intent="answer" (card T-02b / design D-035)
# ---------------------------------------------------------------------------


def test_intent_answer_skips_the_executor_and_archives_an_advisory_row(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``intent="answer"`` skips steps 10/11 but still writes the step-9 row."""
    recorder = ArchiveRecorder()
    dpts.ARCHIVE_WRITER = recorder
    executed: list[str] = []
    install_test_dp(
        monkeypatch, executor=lambda answers, trigger: executed.append("act") or "narrow"
    )
    write_table(tmp_path, {"dp-test-controlflow": {"tier": "P2", "enabled": True, "mode": "auto"}})
    client, backend = configured_client(
        tmp_path, results=[ok_outcome("dp-test-controlflow", value="narrow")]
    )

    outcome = dpts.decide_for(
        "dp-test-controlflow",
        dpts.Trigger(trigger_id="answer1", key="k1"),
        tmp_path,
        client=client,
        archive=True,
        intent="answer",
    )

    assert executed == [], "intent=answer must never run the executor (steps 10/11 skipped)"
    assert outcome.status == "suggested"
    assert outcome.escalated_reason is None
    assert outcome.actual_action is None
    assert outcome.answer is not None
    assert outcome.answers == outcome.answer
    assert outcome.confidence_source == decision.CONFIDENCE_SOURCE_API
    assert isinstance(outcome.latency_ms, int) and outcome.latency_ms >= 0
    assert outcome.mode == "auto"
    assert outcome.decision_id == "dp-test-controlflow:answer1"
    assert outcome.state_digest and len(outcome.state_digest) == 16
    assert len(backend.calls) == 1, "the answer face still asks the transport once"
    row = recorder.rows[-1]
    assert row["authority"] == "advisory"
    assert row["acted"] is False
    assert row["actual_action"] is None
    assert row["escalated_reason"] is None
    assert row["mode"] == "auto"
    assert row["note"] == "intent=answer"
    assert row["answer"]


def test_intent_act_still_executes_and_answers_are_populated(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The default/act intent is unchanged: the executor runs and the row binds."""
    recorder = ArchiveRecorder()
    dpts.ARCHIVE_WRITER = recorder
    executed: list[str] = []
    install_test_dp(
        monkeypatch, executor=lambda answers, trigger: executed.append("act") or "narrow"
    )
    write_table(tmp_path, {"dp-test-controlflow": {"tier": "P2", "enabled": True, "mode": "auto"}})
    client, _backend = configured_client(
        tmp_path, results=[ok_outcome("dp-test-controlflow", value="narrow")]
    )

    outcome = dpts.decide_for(
        "dp-test-controlflow",
        dpts.Trigger(trigger_id="act1", key="k1"),
        tmp_path,
        client=client,
        archive=True,
        intent="act",
    )

    assert executed == ["act"]
    assert outcome.status == "acted"
    assert outcome.actual_action == "narrow"
    assert outcome.answers == outcome.answer
    assert outcome.confidence_source == decision.CONFIDENCE_SOURCE_API
    assert recorder.rows[-1]["authority"] == "binding"
    assert recorder.rows[-1]["acted"] is True


def test_unknown_intent_is_an_input_error(tmp_path: pathlib.Path) -> None:
    with pytest.raises(decision.DecisionInputError):
        dpts.decide_for("dp4-failure-handling", {"key": "k"}, tmp_path, intent="execute")

