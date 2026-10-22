"""test_decide_run_authority.py — card T-02b: `mw decide run` goes through
`decision_points.decide_for(intent="answer")`.

The CLI used to call `decision.DecisionClient` directly, so the authorization
table (`.mw/decide-points.json`), the decision archive and `mode`/`acted` never
applied on that path: AC-001 (disabled == zero spawn and zero archive write) and
AC-011 (one archive row per decision) held for library callers only, and the TS
side had to mirror the config table to derive authority (design D-036).

This suite pins the four behaviours the card asks for:

1. `dp3` off -> `available=false`, `escalated_reason=disabled`, no
   `decisions.jsonl`, `FakeBackend.calls == 0` (and no state encoding at all);
2. `dp3` on + `mode=auto` -> `mode=auto`, `acted=false`, exactly one archive row
   whose `decision_id` is `dp3-worker-clarify:<trigger>`;
3. the legacy request (payload carries `questions`) still returns the frozen
   pre-T-02b key set, and the structured path adds the authority keys without
   dropping any of them;
4. `mode=suggest` -> `acted=false` and an archive row with `mode=suggest`.

Everything runs under `tmp_path`: the transport is `decision.FakeBackend`
(patched into `decision.DecisionClient`), credentials are removed from the
environment, and the points-config cache is cleared per test. The archive is the
real `decide_archive.append_decide` writer (card T-03), not a recorder, so the
rows asserted here are the bytes production would write.
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

#: The pre-T-02b `mw decide run` response keys `triage-client.ts` parses.
LEGACY_RESPONSE_KEYS = (
    "available",
    "transport",
    "model",
    "confidence_source",
    "attempts",
    "latency_ms",
    "answers",
    "reason",
)

#: The additive authority keys (design D-035/D-036).
AUTHORITY_KEYS = ("decision_id", "mode", "acted", "escalated_reason", "state_digest")


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch):
    for name in CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


def _run_args(project: pathlib.Path, **kw) -> argparse.Namespace:
    base = {
        "subcommand": "decide",
        "decide_action": "run",
        "project": str(project),
        "json": True,
        "request_file": None,
        "dp": None,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def _write_decide_config(project: pathlib.Path, **fields) -> pathlib.Path:
    path = project / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"enabled": True, **fields}, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _write_points_table(project: pathlib.Path, points: dict) -> pathlib.Path:
    table = {
        "version": 1,
        "updated_at": "2026-10-20T00:00:00Z",
        "updated_by": "human",
        "points": points,
    }
    path = project / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    dpts.clear_points_config_cache()
    return path


def _dp3_row(*, enabled: bool, mode: str) -> dict:
    return {
        DP3: {"tier": "P2", "enabled": enabled, "mode": mode, "note": "t02b"}
    }


def _request_file(project: pathlib.Path, payload: dict) -> pathlib.Path:
    path = project / "request.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")
    return path


def _dp3_state(**overrides) -> dict:
    """A complete dp3 state (D6 Q1.1 required fields + FIX-I candidates)."""
    state: dict = {
        "schema_version": 2,
        "decision_point": DP3,
        "key": "k-1",
        "phase": "TASKS",
        "task_type": "coding",
        "risk": "mid",
        "risk_source": "machine",
        "authority_tier": "P2",
        "task_summary": "worker asks where the decide-points table lives",
        "ambiguity": {"kind": "fact", "question": "which file holds the decide points?"},
        "local_candidates": [{"id": "c1", "label": ".mw/decide-points.json"}],
    }
    state.update(overrides)
    return state


def _dp3_answers() -> dict:
    return {
        "answer_kind": {"value": "fact", "confidence": 0.9},
        "answerable": {"value": 0.9},
        "candidate": {"value": "c1", "confidence": 0.9},
    }

def _ok(answers: dict, latency_ms: int = 3) -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=True,
        reason=None,
        retryable=False,
        answers=answers,
        latency_ms=latency_ms,
        detail="",
    )


def _inject_backend(monkeypatch: pytest.MonkeyPatch, backend) -> None:
    """`_decide_run` builds the client positionally; wrap it around the fake."""
    real_client = decision.DecisionClient

    def factory(cfg, *args, **kwargs):
        return real_client(cfg, backend, *args, **kwargs)

    monkeypatch.setattr(decision, "DecisionClient", factory)


def _spy_encode_state(monkeypatch: pytest.MonkeyPatch) -> list[object]:
    calls: list[object] = []
    original = decision._encode_state

    def wrapper(state):
        calls.append(state)
        return original(state)

    monkeypatch.setattr(decision, "_encode_state", wrapper)
    return calls


def _archive_path(project: pathlib.Path) -> pathlib.Path:
    return project / dpts.DECISIONS_RELATIVE_PATH


def _archive_rows(project: pathlib.Path) -> list[dict]:
    path = _archive_path(project)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _run_structured(
    project: pathlib.Path,
    capsys: pytest.CaptureFixture,
    *,
    state: dict | None = None,
    dp: str = DP3,
    **kw,
) -> dict:
    """Run one structured `mw decide run` and return the parsed JSON."""
    request = _request_file(project, {"state": _dp3_state() if state is None else state})
    rc = mw.cmd_decide(_run_args(project, request_file=str(request), dp=dp, **kw))
    assert rc == 0, f"a completed decision exits 0 (even unavailable), got {rc}"
    return json.loads(capsys.readouterr().out)


# ---------------------------------------------------------------------------
# 1. disabled: zero spawn, zero encode, zero archive row (AC-001)
# ---------------------------------------------------------------------------


def test_dp3_off_is_zero_spawn_and_writes_no_archive(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    _write_decide_config(tmp_path, enabled=True)
    _write_points_table(tmp_path, _dp3_row(enabled=False, mode="auto"))
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    _inject_backend(monkeypatch, backend)
    encode_calls = _spy_encode_state(monkeypatch)

    result = _run_structured(tmp_path, capsys)

    assert result["available"] is False
    assert result["answers"] is None
    assert result["reason"] == "disabled", "the legacy reason vocabulary is preserved"
    assert result["escalated_reason"] == "disabled"
    assert result["acted"] is False
    assert result["mode"] == "auto", "the row's configured mode is reported, not mirrored"
    assert result["decision_id"] == f"{DP3}:k-1"
    assert result["state_digest"] is None, "the disabled path never builds the state"
    assert backend.calls == [], "disabled must not reach the backend (AC-001)"
    assert encode_calls == [], "disabled must return before _encode_state"
    assert not _archive_path(tmp_path).exists(), "disabled must write no archive row"
    assert not (tmp_path / ".agenticdoc" / "_autopilot").exists()


# ---------------------------------------------------------------------------
# 2. enabled + auto: answer only, exactly one archived advisory row (AC-011)
# ---------------------------------------------------------------------------


def test_dp3_on_auto_answers_without_acting_and_archives_one_row(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    _write_decide_config(tmp_path, enabled=True)
    _write_points_table(tmp_path, _dp3_row(enabled=True, mode="auto"))
    answers = _dp3_answers()
    backend = decision.FakeBackend([_ok(answers)])
    _inject_backend(monkeypatch, backend)

    result = _run_structured(tmp_path, capsys)

    assert result["available"] is True
    # `noul` answers carry no confidence, so normalization fills null (FIX-H).
    assert result["answers"] == {**answers, "answerable": {"value": 0.9, "confidence": None}}
    assert result["reason"] is None
    assert result["mode"] == "auto"
    assert result["acted"] is False, "intent=answer never executes an action"
    assert result["escalated_reason"] is None
    assert result["decision_id"] == f"{DP3}:k-1"
    assert isinstance(result["state_digest"], str) and len(result["state_digest"]) == 16
    assert len(backend.calls) == 1

    rows = _archive_rows(tmp_path)
    assert len(rows) == 1, "exactly one archive row per decision (AC-011)"
    row = rows[0]
    assert row["kind"] == "decide"
    assert row["dp"] == DP3
    assert row["decision_id"] == result["decision_id"]
    assert row["mode"] == "auto"
    assert row["acted"] is False
    assert row["actual_action"] is None
    assert row["authority"] == "advisory"
    assert row["escalated_reason"] is None
    assert row["state_digest"] == result["state_digest"]
    assert row["answer"] == {**answers, "answerable": {"value": 0.9, "confidence": None}}


# ---------------------------------------------------------------------------
# 3. legacy request: the old key set survives, the new keys are additive
# ---------------------------------------------------------------------------


def test_legacy_questions_request_keeps_the_old_key_set(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    _write_decide_config(tmp_path, enabled=True)
    questions = {"triage_type": {"type": "choice", "choices": ["coding", "research", "review"]}}
    backend = decision.FakeBackend([_ok({"triage_type": {"value": "research", "confidence": 0.8}})])
    _inject_backend(monkeypatch, backend)
    request = _request_file(tmp_path, {"state": "card body", "questions": questions})

    rc = mw.cmd_decide(_run_args(tmp_path, request_file=str(request), dp="dp1"))
    assert rc == 0
    legacy = json.loads(capsys.readouterr().out)

    # Byte-frozen legacy path (design D-027): every pre-T-02b key, same meaning.
    for key in LEGACY_RESPONSE_KEYS:
        assert key in legacy, f"legacy response lost the {key!r} key"
    assert legacy["available"] is True
    assert legacy["reason"] is None
    assert legacy["answers"]["triage_type"]["value"] == "research"
    assert legacy["transport"], "the transport name is still reported"
    assert legacy["confidence_source"], "confidence provenance is still reported"
    assert legacy["attempts"] == 1
    assert isinstance(legacy["latency_ms"], int) and legacy["latency_ms"] >= 0
    assert backend.calls[0]["questions"] == questions
    assert not _archive_path(tmp_path).exists(), "the frozen legacy path archives nothing"

    # The registry path keeps the same old keys and adds the authority keys on
    # top: nothing is removed, so `triage-client.ts` parses both paths.
    assert len(backend.calls) == 1
    structured = _run_structured(tmp_path, capsys)
    for key in LEGACY_RESPONSE_KEYS:
        assert key in structured, f"structured response dropped the legacy {key!r} key"
    for key in AUTHORITY_KEYS:
        assert key in structured, f"structured response is missing the {key!r} key"
    assert structured["decision_id"] == f"{DP3}:k-1"
    assert len(_archive_rows(tmp_path)) == 1


# ---------------------------------------------------------------------------
# 4. mode=suggest: acted=false and the archived row says suggest
# ---------------------------------------------------------------------------


def test_suggest_mode_archives_a_suggest_row_without_acting(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    _write_decide_config(tmp_path, enabled=True)
    _write_points_table(tmp_path, _dp3_row(enabled=True, mode="suggest"))
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    _inject_backend(monkeypatch, backend)

    result = _run_structured(tmp_path, capsys)

    assert result["available"] is True
    assert result["mode"] == "suggest"
    assert result["acted"] is False
    assert result["escalated_reason"] is None
    rows = _archive_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["mode"] == "suggest"
    assert rows[0]["acted"] is False
    assert rows[0]["authority"] == "advisory"
    assert rows[0]["note"] == "mode=suggest"


# ---------------------------------------------------------------------------
# Error surfaces the CLI already owned
# ---------------------------------------------------------------------------


def test_unknown_dp_exits_2_and_writes_nothing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_decide_config(tmp_path, enabled=True)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    _inject_backend(monkeypatch, backend)
    request = _request_file(tmp_path, {"state": _dp3_state(dp="dp99-nope")})

    assert mw.cmd_decide(_run_args(tmp_path, request_file=str(request), dp="dp99-nope")) == 2
    assert "unknown decision point id" in capsys.readouterr().err
    assert backend.calls == []
    assert not _archive_path(tmp_path).exists()


def test_unconfigured_transport_maps_to_the_legacy_disabled_reason(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """`escalated_reason=unavailable` keeps a REASON_CODES `reason` for the TS side."""
    _write_points_table(tmp_path, _dp3_row(enabled=True, mode="auto"))
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    _inject_backend(monkeypatch, backend)

    result = _run_structured(tmp_path, capsys)

    assert result["available"] is False
    assert result["escalated_reason"] == "unavailable"
    assert result["reason"] == decision.REASON_DISABLED
    assert result["acted"] is False
    assert backend.calls == []
    assert not _archive_path(tmp_path).exists(), "no transport => no archive row"
