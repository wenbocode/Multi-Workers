"""W6 context tests: slot caps, cut order, validation, redaction, state budget."""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402
import decision  # noqa: E402
import decision_context as ctx  # noqa: E402
import decision_points as dpts  # noqa: E402


def _write_points_table(project: pathlib.Path, points: object) -> None:
    path = project / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "points": points,
                "updated_at": "2026-10-21T00:00:00Z",
                "updated_by": "human",
            }
        ),
        encoding="utf-8",
    )


def _answers_for(dp_id: str) -> dict:
    out: dict = {}
    for question in dpts.get_decision_point(dp_id).questions:
        if question["type"] == decision.QUESTION_CHOICE:
            value = "c1" if "dynamic_choices" in question else question["choices"][0]
        elif question["type"] == decision.QUESTION_SCORE:
            value = question["min"]
        elif question["type"] == decision.QUESTION_NOUL:
            value = 0.9
        else:
            value = "answer text"
        out[str(question["id"])] = {"value": value, "confidence": 0.9}
    return out


def _client(tmp_path: pathlib.Path) -> decision.DecisionClient:
    backend = decision.FakeBackend(
        default=decision.BackendOutcome(
            available=True,
            reason=None,
            retryable=False,
            answers=_answers_for("dp3-worker-clarify"),
            latency_ms=1,
        )
    )
    return decision.DecisionClient(
        cfg=decision.DecisionConfig(enabled=True),
        backend=backend,
        evidence_path=tmp_path / "triage-decisions.jsonl",
    )


def _dp3_trigger(**overrides) -> dpts.Trigger:
    data = {
        "key": "key-1",
        "phase": "EXECUTE",
        "task_type": "coding",
        "risk": "mid",
        "risk_source": "machine",
        "authority_tier": "P2",
        "task_summary": "worker asks which registry file is authoritative",
        "ambiguity": {"kind": "scope", "question": "which file holds the dp table?"},
        "local_candidates": [{"id": "c1", "label": ".mw/decide-points.json"}],
    }
    data.update(overrides)
    return dpts.Trigger.from_mapping(data, key="key-1")


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch):
    for name in ("TIMI_API_KEY", "ANTHROPIC_API_KEY", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setattr(dpts, "ARCHIVE_WRITER", None, raising=False)
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


# ---------------------------------------------------------------------------
# Caps + truncation
# ---------------------------------------------------------------------------


def test_truncate_slot_marks_the_cut_and_keeps_head_and_tail() -> None:
    text = "HEAD" + ("x" * 2000) + "TAIL"
    out = ctx.truncate_slot("task_excerpt", text)
    assert isinstance(out, str)
    assert out.startswith("HEAD")
    assert out.endswith("TAIL")
    assert "…truncated " in out
    assert len(out) <= 1200


def test_truncate_slot_leaves_a_short_value_untouched() -> None:
    assert ctx.truncate_slot("change_summary", "short change") == "short change"


def test_truncate_slot_caps_the_array_item_count() -> None:
    items = [{"text": f"line-{index}", "source": f"f.md:{index}"} for index in range(9)]
    out = ctx.truncate_slot("candidate_snippets", items)
    assert isinstance(out, list)
    assert len(out) == 5


def test_truncate_slot_caps_each_snippet_text() -> None:
    items = [{"text": "y" * 900, "source": "f.md:3"}]
    out = ctx.truncate_slot("candidate_snippets", items)
    assert isinstance(out, list)
    text = out[0]["text"]
    assert len(text) <= 200
    assert "…truncated " in text
    assert out[0]["source"] == "f.md:3"


# ---------------------------------------------------------------------------
# fit_context: budget + cut order
# ---------------------------------------------------------------------------


def test_fit_context_keeps_everything_under_budget() -> None:
    context = {"change_summary": "ok", "artifact_status": [{"path": "task.md", "exists": True, "bytes": 3}]}
    fitted, cut = ctx.fit_context(context, budget=4000)
    assert fitted == context
    assert cut == ()


def test_fit_context_cuts_lowest_priority_slots_first() -> None:
    context = {
        "task_excerpt": "t" * 1200,
        "change_summary": "c" * 800,
        "candidate_snippets": [{"text": "s" * 200, "source": "f.md:1"}],
        "artifact_status": [{"path": "task.md", "exists": True, "bytes": 10}],
    }
    fitted, cut = ctx.fit_context(context, budget=1100)
    assert "artifact_status" not in fitted
    assert "task_excerpt" not in fitted
    assert "change_summary" in fitted, "higher-priority slots survive the cut"
    assert "candidate_snippets" in fitted, "the highest-priority slot survives longest"
    assert cut == ("artifact_status", "task_excerpt"), "cut order is lowest priority first"


def test_fit_context_zero_budget_drops_every_slot() -> None:
    fitted, cut = ctx.fit_context({"change_summary": "x"}, budget=0)
    assert fitted == {}
    assert cut == ("change_summary",)


# ---------------------------------------------------------------------------
# validate_context: reports, never raises
# ---------------------------------------------------------------------------


def test_validate_context_accepts_a_well_formed_block() -> None:
    dp2_context = {
        "change_summary": "elapsed=35m",
        "artifact_status": [{"path": "task.md", "exists": True, "bytes": 12}],
    }
    dp3_context = {
        "change_summary": "elapsed=35m",
        "candidate_snippets": [{"text": "line", "source": "f.md:7"}],
    }
    assert ctx.validate_context(dp2_context, "dp2-checkpoint-split") == []
    assert ctx.validate_context(dp3_context, "dp3-worker-clarify") == []


def test_validate_context_flags_an_unknown_slot() -> None:
    issues = ctx.validate_context({"transcript": "..."}, "dp1-dispatch-type")
    assert issues == ["context.transcript: unknown slot"]


def test_validate_context_flags_a_slot_the_dp_may_not_emit() -> None:
    issues = ctx.validate_context({"task_excerpt": "x"}, "dp3-worker-clarify")
    assert issues == ["context.task_excerpt: not a slot of dp3-worker-clarify"]


def test_validate_context_flags_a_snippet_without_a_source() -> None:
    issues = ctx.validate_context({"candidate_snippets": [{"text": "line"}]}, "dp3-worker-clarify")
    assert issues == ["context.candidate_snippets[0]: missing source"]


def test_validate_context_flags_over_cap_values() -> None:
    issues = ctx.validate_context({"change_summary": "z" * 801}, "dp2-checkpoint-split")
    assert issues == ["context.change_summary: longer than 800 chars"]
    rows = [{"path": f"f{index}.md", "exists": True, "bytes": 1} for index in range(25)]
    issues = ctx.validate_context({"artifact_status": rows}, "dp2-checkpoint-split")
    assert issues == ["context.artifact_status: more than 24 items"]


def test_validate_context_never_raises_on_a_non_object() -> None:
    assert ctx.validate_context(["nope"], "dp1-dispatch-type") == ["context: must be an object"]


# ---------------------------------------------------------------------------
# redact_context
# ---------------------------------------------------------------------------


def test_redact_context_scrubs_nested_strings_and_keeps_shape() -> None:
    secret = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"
    context = {
        "change_summary": f"token {secret} leaked",
        "candidate_snippets": [{"text": "Authorization: Bearer abcdef012345", "source": "f.md:1"}],
    }
    redacted = ctx.redact_context(context)
    dumped = json.dumps(redacted)
    assert secret not in dumped
    assert "abcdef012345" not in dumped
    assert redacted["candidate_snippets"][0]["source"] == "f.md:1"


# ---------------------------------------------------------------------------
# slot whitelist per dp (drives the generated TS registry)
# ---------------------------------------------------------------------------


def test_slot_names_match_the_card_whitelist() -> None:
    assert ctx.slot_names_for("dp1-dispatch-type") == ("task_excerpt",)
    assert ctx.slot_names_for("dp2-checkpoint-split") == ("change_summary", "artifact_status")
    assert ctx.slot_names_for("dp3-worker-clarify") == ("change_summary", "candidate_snippets")
    assert ctx.slot_names_for("dp4-failure-handling") == ("error_excerpt",)
    assert ctx.slot_names_for("dp5-test-triage") == ()


# ---------------------------------------------------------------------------
# state integration: digest, fit budget, decide path
# ---------------------------------------------------------------------------


def test_context_changes_the_state_digest() -> None:
    base = {"key": "k", "schema_version": 2}
    with_context = {**base, "context": {"change_summary": "elapsed=35m"}}
    assert dpts._state_digest(base) != dpts._state_digest(with_context)


def test_context_counts_inside_the_2000b_state_budget() -> None:
    # ~1 600 B of decision fields leave ~384 B of headroom: a 100-char summary
    # fits whole, and the combined state still respects the 2000 B cap.
    state = {"task_summary": "a" * 1580, "context": {"change_summary": "c" * 100}}
    fitted, dropped, size = dpts._fit_state(state)
    assert size <= dpts.MAX_STATE_BYTES
    assert dropped == ()
    assert fitted["context"]["change_summary"] == "c" * 100


def test_oversized_context_loses_to_the_decision_fields() -> None:
    # 1 880 B of decision fields leave ~84 B: a 600-char summary cannot fit, so
    # the whole optional slot is cut (never the required field).
    state = {"task_summary": "a" * 1880, "context": {"change_summary": "b" * 600}}
    fitted, dropped, size = dpts._fit_state(state)
    assert size <= dpts.MAX_STATE_BYTES
    assert "context" not in fitted
    assert "context.change_summary" in dropped
    assert fitted["task_summary"] == "a" * 1880


def test_context_is_dropped_when_the_state_is_already_at_the_cap() -> None:
    state = {"task_summary": "a" * (dpts.MAX_STATE_BYTES - 10), "context": {"task_excerpt": "x" * 400}}
    fitted, dropped, size = dpts._fit_state(state)
    assert size <= dpts.MAX_STATE_BYTES
    assert "context" not in fitted
    assert "context.task_excerpt" in dropped


def test_fit_state_redacts_credentials_carried_in_context() -> None:
    secret = "sk-ant-api03-abcdefghijklmnopqrstuvwxyz0123456789"
    state = {"task_summary": "small", "context": {"change_summary": f"token {secret}"}}
    fitted, _dropped, _size = dpts._fit_state(state)
    assert secret not in json.dumps(fitted)
    assert "<redacted>" in fitted["context"]["change_summary"]


def test_missing_context_does_not_change_the_decide_outcome(tmp_path: pathlib.Path) -> None:
    _write_points_table(tmp_path, {"dp3-worker-clarify": {"tier": "P2", "enabled": True, "mode": "suggest"}})
    outcome = dpts.decide_for(
        "dp3-worker-clarify", _dp3_trigger(), tmp_path, client=_client(tmp_path), archive=False
    )
    assert outcome.escalated_reason != "input-incomplete"
    assert outcome.status == "suggested"


def test_context_rides_along_and_is_listed_by_validate(tmp_path: pathlib.Path) -> None:
    _write_points_table(tmp_path, {"dp3-worker-clarify": {"tier": "P2", "enabled": True, "mode": "suggest"}})
    trigger = _dp3_trigger(
        context={"change_summary": "elapsed=35m", "candidate_snippets": [{"text": "line", "source": "f.md:1"}]}
    )
    outcome = dpts.decide_for(
        "dp3-worker-clarify", trigger, tmp_path, client=_client(tmp_path), archive=False
    )
    assert outcome.escalated_reason != "input-incomplete"
    assert ctx.validate_context(trigger.data["context"], "dp3-worker-clarify") == []
