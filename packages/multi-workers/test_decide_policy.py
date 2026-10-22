"""test_decide_policy.py — W5b: per-dp policy knobs (spec §14 AC-016).

Hermetic pytest suite (key mw-decision-substitution) for the AC-016 resolver in
`decision_points.py` plus the CLI faces that must print EFFECTIVE values:

* ``resolve_policy`` / ``resolve_policy_origins`` — per-dp row >
  ``.mw/decide.json`` > built-in ``0.7 / 8 / 20``; illegal values are dropped
  (never raised) so the next layer speaks.
* ``mw decide dp show`` / ``mw decide dp check`` — one line per dp with the
  deciding layer in parens, plus the existing L8 issue text as the fallback
  reason of a dropped raw value.
* ``mw decide show --json`` — the effective policy table next to the raw config.
* the archive seam — a ``kind=decide`` row echoes the three effective values.
* the Python<->TS parity fixture (`PARITY-FIXTURE-BEGIN/END` below): the SAME
  JSON blob is extracted and resolved by
  `packages/coding-agent/test/suite/dp3-answer.test.ts`, so the two
  implementations cannot drift on "which layer wins".

Everything runs under ``tmp_path``: no network, no credentials, and the decision
archive is a local recorder injected through ``decision_points.ARCHIVE_WRITER``.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402
import decision  # noqa: E402
import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
)

DP3 = "dp3-worker-clarify"
DP2 = "dp2-checkpoint-split"
DP4 = "dp4-failure-handling"

#: Shared Python<->TS parity fixture — SINGLE SOURCE.
#:
#: The TS suites (`test/suite/dp3-answer.test.ts`) read THIS file, slice the
#: block between the two markers and `JSON.parse` it, then resolve the same
#: config through `shared/decide-policy.ts`. Keep the payload pure JSON (no
#: Python literals, no comments inside the markers).
# PARITY-FIXTURE-BEGIN
PARITY_FIXTURE_JSON = r"""
{
  "decide": {
    "enabled": true,
    "min_confidence": 0.62,
    "max_questions": 6,
    "timeout_s": 45
  },
  "points": {
    "dp3-worker-clarify": {
      "tier": "P2",
      "enabled": true,
      "mode": "auto",
      "min_confidence": 0.85,
      "max_questions": 3,
      "timeout_s": 90
    },
    "dp2-checkpoint-split": {
      "min_confidence": 1.5,
      "max_questions": 0,
      "timeout_s": "fast"
    },
    "dp1-dispatch-type": {
      "min_confidence": "high"
    }
  },
  "expected": {
    "dp3-worker-clarify": {
      "min_confidence": 0.85,
      "max_questions": 3,
      "timeout_s": 90
    },
    "dp2-checkpoint-split": {
      "min_confidence": 0.62,
      "max_questions": 6,
      "timeout_s": 45
    },
    "dp1-dispatch-type": {
      "min_confidence": 0.62,
      "max_questions": 6,
      "timeout_s": 45
    },
    "dp4-failure-handling": {
      "min_confidence": 0.62,
      "max_questions": 6,
      "timeout_s": 45
    }
  }
}
"""
# PARITY-FIXTURE-END

PARITY_FIXTURE: dict = json.loads(PARITY_FIXTURE_JSON)


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


def write_points(project: pathlib.Path, points: object) -> pathlib.Path:
    path = project / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "points": points}, ensure_ascii=False), encoding="utf-8"
    )
    dpts.clear_points_config_cache()
    return path


def write_decide(project: pathlib.Path, **fields) -> pathlib.Path:
    path = project / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8")
    dpts.clear_points_config_cache()
    return path


def row_config(project: pathlib.Path, dp_id: str) -> dpts.PointConfig:
    return dpts.load_points_config(project).effective(dpts.get_decision_point(dp_id))


def resolved(project: pathlib.Path, dp_id: str) -> dict:
    cfg, _err = decision.DecisionConfig.from_project(project)
    return dpts.resolve_policy(dp_id, row_config(project, dp_id), cfg)


def origins(project: pathlib.Path, dp_id: str) -> dict:
    cfg, _err = decision.DecisionConfig.from_project(project)
    return dpts.resolve_policy_origins(dp_id, row_config(project, dp_id), cfg)


def dp_args(project: pathlib.Path, action: str, **kw) -> argparse.Namespace:
    base = {
        "subcommand": "decide",
        "decide_action": "dp",
        "dp_action": action,
        "project": str(project),
        "json": False,
        "pairs": [],
        "rows": 5,
        "i_understand_p0": False,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def args(project: pathlib.Path, action: str, **kw) -> argparse.Namespace:
    base = {
        "subcommand": "decide",
        "decide_action": action,
        "project": str(project),
        "json": True,
    }
    base.update(kw)
    return argparse.Namespace(**base)


# ---------------------------------------------------------------------------
# 1. Built-in layer
# ---------------------------------------------------------------------------


def test_builtin_defaults_when_no_file_declares_a_value(tmp_path: pathlib.Path) -> None:
    assert resolved(tmp_path, DP3) == {
        "min_confidence": 0.7,
        "max_questions": 8,
        "timeout_s": 20,
    }
    assert origins(tmp_path, DP3) == {
        "min_confidence": "builtin",
        "max_questions": "builtin",
        "timeout_s": "builtin",
    }


def test_builtin_defaults_are_the_same_for_every_dp(tmp_path: pathlib.Path) -> None:
    for dp_id in (DP2, DP3, DP4):
        values = resolved(tmp_path, dp_id)
        assert values["min_confidence"] == 0.7, dp_id
        assert values["max_questions"] == 8, dp_id
        assert values["timeout_s"] == 20, dp_id


# ---------------------------------------------------------------------------
# 2. Three-layer precedence
# ---------------------------------------------------------------------------


def test_decide_json_layer_beats_builtin(tmp_path: pathlib.Path) -> None:
    write_decide(tmp_path, enabled=True, min_confidence=0.55, max_questions=5, timeout_s=30)
    assert resolved(tmp_path, DP3) == {
        "min_confidence": 0.55,
        "max_questions": 5,
        "timeout_s": 30,
    }
    assert set(origins(tmp_path, DP3).values()) == {"decide.json"}


def test_row_layer_beats_decide_json(tmp_path: pathlib.Path) -> None:
    write_decide(tmp_path, enabled=True, min_confidence=0.55, max_questions=5, timeout_s=30)
    write_points(tmp_path, {DP3: {"enabled": True, "min_confidence": 0.9, "max_questions": 2, "timeout_s": 120}})
    assert resolved(tmp_path, DP3) == {
        "min_confidence": 0.9,
        "max_questions": 2,
        "timeout_s": 120,
    }
    assert set(origins(tmp_path, DP3).values()) == {"row"}


def test_row_partial_override_falls_through_per_key(tmp_path: pathlib.Path) -> None:
    write_decide(tmp_path, enabled=True, min_confidence=0.55, max_questions=5, timeout_s=30)
    write_points(tmp_path, {DP3: {"enabled": True, "min_confidence": 0.9}})
    assert resolved(tmp_path, DP3) == {
        "min_confidence": 0.9,
        "max_questions": 5,
        "timeout_s": 30,
    }
    assert origins(tmp_path, DP3) == {
        "min_confidence": "row",
        "max_questions": "decide.json",
        "timeout_s": "decide.json",
    }


def test_other_dp_rows_do_not_leak(tmp_path: pathlib.Path) -> None:
    write_points(tmp_path, {DP2: {"enabled": True, "min_confidence": 0.4}})
    assert resolved(tmp_path, DP3)["min_confidence"] == 0.7
    assert resolved(tmp_path, DP2)["min_confidence"] == 0.4


# ---------------------------------------------------------------------------
# 3. Fail-soft: illegal row values drop to the next layer with a warning
# ---------------------------------------------------------------------------


def test_row_out_of_range_falls_back_to_next_layer(tmp_path: pathlib.Path) -> None:
    write_decide(tmp_path, enabled=True, min_confidence=0.6, max_questions=6, timeout_s=40)
    write_points(
        tmp_path,
        {DP3: {"enabled": True, "min_confidence": 1.5, "max_questions": 0, "timeout_s": 999}},
    )
    assert resolved(tmp_path, DP3) == {
        "min_confidence": 0.6,
        "max_questions": 6,
        "timeout_s": 40,
    }
    config = dpts.load_points_config(tmp_path)
    issues = "\n".join(config.row(DP3).issues)
    assert "L8: min_confidence 1.5 is outside [0, 1]" in issues
    assert "L8: max_questions 0 is outside [1, 8]" in issues
    assert "L8: timeout_s 999 is outside [1, 300]" in issues
    # L8 is advisory: it must not disable the dp (only L2/L3/L5 do).
    assert config.row(DP3).enabled is True


def test_row_bad_type_falls_back_to_next_layer(tmp_path: pathlib.Path) -> None:
    write_points(
        tmp_path,
        {
            DP3: {
                "enabled": True,
                "min_confidence": "high",
                "max_questions": True,
                "timeout_s": None,
            }
        },
    )
    assert resolved(tmp_path, DP3) == {
        "min_confidence": 0.7,
        "max_questions": 8,
        "timeout_s": 20,
    }
    issues = "\n".join(dpts.load_points_config(tmp_path).row(DP3).issues)
    assert "L8: min_confidence must be a number" in issues
    assert "L8: max_questions must be a number" in issues
    assert "L8: timeout_s must be a number" in issues


def test_row_fractional_budget_is_rejected(tmp_path: pathlib.Path) -> None:
    write_points(tmp_path, {DP3: {"enabled": True, "max_questions": 2.5}})
    assert resolved(tmp_path, DP3)["max_questions"] == 8
    issues = "\n".join(dpts.load_points_config(tmp_path).row(DP3).issues)
    assert "L8: max_questions must be an integer" in issues


def test_decide_json_bad_values_fall_back_to_builtin(tmp_path: pathlib.Path) -> None:
    write_decide(tmp_path, enabled=True, min_confidence=2, max_questions=0, timeout_s=-5)
    assert resolved(tmp_path, DP3) == {
        "min_confidence": 0.7,
        "max_questions": 8,
        "timeout_s": 20,
    }
    assert set(origins(tmp_path, DP3).values()) == {"builtin"}


def test_decide_json_null_is_not_a_declaration(tmp_path: pathlib.Path) -> None:
    write_decide(tmp_path, enabled=True, min_confidence=None, max_questions=4)
    values = resolved(tmp_path, DP3)
    assert values["min_confidence"] == 0.7
    assert values["max_questions"] == 4
    assert origins(tmp_path, DP3)["min_confidence"] == "builtin"


def test_decide_json_needs_no_enabled_flag_to_supply_policy(tmp_path: pathlib.Path) -> None:
    # AC-016 resolves policy independently of the transport gate: `enabled` is
    # read by `decide_for`, not by the resolver.
    write_decide(tmp_path, enabled=False, min_confidence=0.65)
    assert resolved(tmp_path, DP3)["min_confidence"] == 0.65


# ---------------------------------------------------------------------------
# 4. CLI faces print EFFECTIVE values
# ---------------------------------------------------------------------------


def test_dp_show_prints_effective_policy_and_fallback_reason(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    write_decide(tmp_path, enabled=True, min_confidence=0.6)
    write_points(tmp_path, {DP3: {"enabled": True, "min_confidence": 3}})
    assert mw.cmd_decide(dp_args(tmp_path, "show", dp=DP3)) == 0
    out = capsys.readouterr().out
    assert "policy: min_confidence=0.6(decide.json) max_questions=8(builtin) timeout_s=20(builtin)" in out
    assert "L8: min_confidence 3 is outside [0, 1]" in out


def test_dp_show_json_carries_policy(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture) -> None:
    write_points(tmp_path, {DP3: {"enabled": True, "timeout_s": 77}})
    assert mw.cmd_decide(dp_args(tmp_path, "show", dp=DP3, json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["policy"]["timeout_s"] == 77
    assert payload["policy"]["origin"]["timeout_s"] == "row"


def test_dp_check_prints_effective_values_for_every_row(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    write_points(tmp_path, {DP3: {"enabled": True, "min_confidence": 9}})
    assert mw.cmd_decide(dp_args(tmp_path, "check")) == 1
    out = capsys.readouterr().out
    assert f"policy {DP3}: min_confidence=0.7(builtin)" in out
    assert f"policy {DP2}: min_confidence=0.7(builtin)" in out
    assert f"policy {DP4}: min_confidence=0.7(builtin)" in out


def test_dp_check_json_carries_policy(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture) -> None:
    write_decide(tmp_path, enabled=True, max_questions=4)
    assert mw.cmd_decide(dp_args(tmp_path, "check", json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["policy"][DP3] == {
        "min_confidence": 0.7,
        "max_questions": 4,
        "timeout_s": 20,
        "origin": {"min_confidence": "builtin", "max_questions": "decide.json", "timeout_s": "builtin"},
    }


def test_dp_set_still_rejects_unknown_row_keys(tmp_path: pathlib.Path) -> None:
    write_points(tmp_path, {})
    assert mw.cmd_decide(dp_args(tmp_path, "set", dp=DP3, pairs=["bogus=1"])) == 2
    # The three AC-016 knobs are read-only table content for now; `dp set` is
    # unchanged and still refuses them (W5b scope: resolver + read faces only).
    assert mw.cmd_decide(dp_args(tmp_path, "set", dp=DP3, pairs=["min_confidence=0.9"])) == 2


def test_decide_show_json_carries_effective_policy(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    write_decide(tmp_path, enabled=True)
    write_points(tmp_path, {DP3: {"enabled": True, "min_confidence": 0.83}})
    assert mw.cmd_decide(args(tmp_path, "show")) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["policy"][DP3]["min_confidence"] == 0.83
    assert payload["policy"][DP3]["origin"]["min_confidence"] == "row"


# ---------------------------------------------------------------------------
# 5. Archive seam echoes the effective policy
# ---------------------------------------------------------------------------


def dp3_trigger() -> dpts.Trigger:
    return dpts.Trigger.from_mapping(
        {
            "key": "key-1",
            "phase": "TASKS",
            "task_type": "coding",
            "risk": "mid",
            "risk_source": "machine",
            "authority_tier": "P2",
            "task_summary": "worker asks where the decide-points table lives",
            "ambiguity": {"kind": "fact", "question": "which file holds the decide points?"},
            "local_candidates": [{"id": "c1", "label": ".mw/decide-points.json"}],
        },
        key="key-1",
    )


def dp3_answers() -> dict:
    """A legal normalized answer payload for every dp3 registry question."""
    out: dict = {}
    for question in dpts.get_decision_point(DP3).questions:
        if question["type"] == decision.QUESTION_CHOICE:
            value: object = "c1" if "dynamic_choices" in question else question["choices"][0]
        elif question["type"] == decision.QUESTION_SCORE:
            value = question["min"]
        elif question["type"] == decision.QUESTION_NOUL:
            value = 0.9
        else:
            value = "answer text"
        out[str(question["id"])] = {"value": value, "confidence": 0.9}
    return out


def dp3_client() -> decision.DecisionClient:
    backend = decision.FakeBackend(
        [],
        default=decision.BackendOutcome(
            available=True, reason=None, retryable=False, answers=dp3_answers(), latency_ms=1
        ),
    )
    return decision.DecisionClient(cfg=decision.DecisionConfig(enabled=True), backend=backend)


# ---------------------------------------------------------------------------
# 5b. Archive row echoes the effective policy
# ---------------------------------------------------------------------------


def test_archive_decide_row_carries_policy(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    recorder = ArchiveRecorder()
    monkeypatch.setattr(dpts, "ARCHIVE_WRITER", recorder, raising=False)
    write_points(
        tmp_path,
        {DP3: {"enabled": True, "mode": "suggest", "min_confidence": 0.9, "max_questions": 4, "timeout_s": 60}},
    )
    outcome = dpts.decide_for(DP3, dp3_trigger(), tmp_path, client=dp3_client())
    assert outcome.status == "suggested"
    assert recorder.rows, "the decide row must be archived for a suggestion"
    assert recorder.rows[0]["policy"] == {
        "min_confidence": 0.9,
        "max_questions": 4,
        "timeout_s": 60,
    }


def test_archive_row_omits_policy_when_the_writer_rejects_it(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    rows: list[dict] = []

    class LegacyWriter:
        """Pre-AC-016 ``append_decide`` signature: no ``policy``, no ``**kwargs``."""

        def __call__(
            self,
            path,
            dp,
            key,
            task_key,
            trigger_id,
            state,
            questions_version,
            available,
            authority,
            answer,
            reason,
            escalated_reason,
            acted,
            actual_action,
            mode,
            transport,
            model,
            attempts,
            latency_ms,
            confidence,
            confidence_source,
            note,
            duplicate,
        ):
            rows.append({"dp": dp, "duplicate": duplicate})
            return {"seq": len(rows)}

    monkeypatch.setattr(dpts, "ARCHIVE_WRITER", LegacyWriter(), raising=False)
    dpts._archive_decision(
        dp_point=dpts.get_decision_point(DP3),
        trigger=dp3_trigger(),
        project_dir=tmp_path,
        state={},
        mode="suggest",
        response={"available": False, "reason": "disabled"},
        authority="human",
        escalated_reason="unavailable",
        acted=False,
        actual_action=None,
        policy={"min_confidence": 0.9, "max_questions": 4, "timeout_s": 60},
    )
    assert rows, "the legacy writer still receives the row"
    assert "policy" not in rows[0], "an old writer must keep working (AC-016 fail-soft)"


# ---------------------------------------------------------------------------
# 6. Python<->TS parity (single fixture, two implementations)
# ---------------------------------------------------------------------------


def test_parity_fixture_resolves_to_the_expected_effective_values(tmp_path: pathlib.Path) -> None:
    fixture = PARITY_FIXTURE
    write_decide(tmp_path, **fixture["decide"])
    write_points(tmp_path, fixture["points"])
    for dp_id, expected in fixture["expected"].items():
        assert resolved(tmp_path, dp_id) == expected, dp_id
