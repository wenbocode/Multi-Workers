"""test_decide_sign_auto.py - the sign-off belongs to the decision model only.

The 2026-10-22 decide-only ruling (spec §2 / design §3) left exactly one path:

* ``.mw/decide.json`` ``signoff`` = ``auto`` (default) | ``disable``, written by
  ``mw decide sign --auto|--disable`` (fail-soft read, D-065). The flags only
  persist the mode; the sign step itself has no caller-supplied conclusion.
* ``auto`` asks ``dp25-signoff-conclusion`` (state assembled from
  ``decide_signoff.collect()`` facts only) and records ``signed_via:
  auto-decide``;
* when jev cannot answer (no config / transport down / dp25 unregistered or
  disabled) nothing is written and the command exits 0 with
  ``decision model unavailable (<reason>); sign-off not required`` - there is
  no ``auto-llm`` fallback and no human face;
* ``disable`` writes nothing and the ``done`` gate stops requiring
  ``sign-final.md``;
* ``write_signoff`` has no agent-session gate: humans and agents walk the same
  path (AC-008).

Hermetic: a ``decision.FakeBackend`` through ``decision.DEFAULT_BACKEND_FACTORY``,
``tmp_path`` projects, no network, no credential.
"""

from __future__ import annotations

import argparse
import dataclasses
import importlib.util
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decide_archive  # noqa: E402
import decide_signoff  # noqa: E402
import decision  # noqa: E402
import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
ADVANCE_PHASE = REPO_ROOT / ".agents" / "skills" / "agentic-task" / "scripts" / "advance_phase.py"

KEY = "k-sign-auto"
QP = "q-0123abcd"
TRUE_ENGINE = dict(
    transport="timi-decisions", model="jev-latest", confidence_source="api"
)


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch):
    for name in decide_signoff.AGENT_SESSION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project(tmp_path: pathlib.Path, *, key: str = KEY) -> pathlib.Path:
    project = tmp_path / "proj"
    (project / ".agenticdoc" / key / "evidence" / "review").mkdir(parents=True)
    return project


def _key_dir(project: pathlib.Path, *, key: str = KEY) -> pathlib.Path:
    return project / ".agenticdoc" / key


def _sign_file(project: pathlib.Path, *, key: str = KEY) -> pathlib.Path:
    return decide_signoff.signoff_path(project, key)


def _archive(project: pathlib.Path) -> pathlib.Path:
    return decide_signoff.archive_path(project)


def _write_config(project: pathlib.Path, **fields) -> pathlib.Path:
    path = project / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"enabled": True, **fields}
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")
    return path


def _write_points_table(project: pathlib.Path, points: dict) -> pathlib.Path:
    path = project / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "points": points}, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    dpts.clear_points_config_cache()
    return path


def _enable_dp25(project: pathlib.Path) -> None:
    _write_points_table(project, {decide_signoff.SIGNOFF_DP_ID: {"enabled": True}})


def _append_true_engine_row(
    project: pathlib.Path, *, trigger: str = "t1", key: str = KEY
) -> dict:
    """One real jev ``kind=decide`` row for ``key`` (the signable evidence)."""
    return decide_archive.append_decide(
        _archive(project),
        available=True,
        answer={"answer_kind": {"value": "fact", "confidence": 0.9}},
        authority="binding",
        acted=True,
        actual_action="steer worker",
        dp="dp3-worker-clarify",
        key=key,
        task_key="task-1",
        trigger_id=trigger,
        state={"schema_version": 2, "decision_point": "dp3-worker-clarify"},
        questions_version=QP,
        mode="auto",
        **TRUE_ENGINE,
    )[0]


def _backend(
    monkeypatch: pytest.MonkeyPatch,
    *,
    conclusion: str = "continue",
    confidence: float = 0.9,
    confidence_source: str = decision.CONFIDENCE_SOURCE_API,
    available: bool = True,
) -> decision.FakeBackend:
    backend = decision.FakeBackend(
        results=None,
        name="timi-decisions",
        model="jev-latest",
        confidence_source=confidence_source,
        default=decision.BackendOutcome(
            available=available,
            reason=None if available else decision.REASON_UPSTREAM_ERROR,
            retryable=False,
            answers=(
                {"q-conclusion": {"value": conclusion, "confidence": confidence}}
                if available
                else None
            ),
            latency_ms=3,
        ),
    )
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: backend)
    return backend


def _sign_args(project: pathlib.Path, **kw) -> argparse.Namespace:
    """The one argv shape `mw decide sign` still has (no conclusion face)."""
    base = {
        "subcommand": "decide",
        "decide_action": "sign",
        "project": str(project),
        "key": None,
        "reason": None,
        "allow_empty": False,
        "dry_run": False,
        "json": False,
        "auto": False,
        "disable": False,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def _parse_machines(project: pathlib.Path, *, key: str = KEY) -> dict[str, str]:
    return decide_signoff.parse_signoff(_sign_file(project, key=key).read_text(encoding="utf-8"))


def _tree_bytes(root: pathlib.Path) -> dict[str, bytes]:
    """Every file under ``root`` (relative path -> bytes): the write probe."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _load_advance_phase():
    if not ADVANCE_PHASE.is_file():
        pytest.skip("AgenticTask framework clone not present under .agents/skills")
    spec = importlib.util.spec_from_file_location("advance_phase_w9", ADVANCE_PHASE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ---------------------------------------------------------------------------
# 1. The config field (AC-023)
# ---------------------------------------------------------------------------


def test_signoff_defaults_to_auto_and_is_echoed_by_show_json(tmp_path: pathlib.Path, capsys) -> None:
    project = _project(tmp_path)
    cfg, error = decision.DecisionConfig.from_project(project)
    assert error is None
    assert cfg.signoff == decision.SIGNOFF_AUTO
    assert cfg.signoff_error is None
    # `mw decide show --json` carries the effective mode (AC-023).
    args = argparse.Namespace(
        subcommand="decide", decide_action="show", project=str(project), json=True
    )
    assert mw.cmd_decide(args) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["signoff"] == "auto"
    assert payload["signoff_error"] is None


def test_invalid_signoff_sets_signoff_error_but_keeps_the_config_usable() -> None:
    cfg, error = decision.DecisionConfig.from_dict({"enabled": True, "signoff": "manual"})
    assert error is None, "an illegal signoff must not disable the configuration"
    assert cfg.is_configured is True
    assert cfg.signoff == decision.SIGNOFF_AUTO
    assert cfg.signoff_error is not None
    assert "manual" in cfg.signoff_error
    # The typo never reaches extras (it has one owner).
    assert "signoff" not in cfg.extras


def test_sign_refuses_on_signoff_error_and_writes_nothing(tmp_path: pathlib.Path, capsys) -> None:
    project = _project(tmp_path)
    _write_config(project, signoff="disabled")
    _append_true_engine_row(project)
    assert mw.cmd_decide(_sign_args(project, key=KEY)) == 2
    err = capsys.readouterr().err
    assert "signoff" in err and "nothing was written" in err
    assert not _sign_file(project).exists()


# ---------------------------------------------------------------------------
# 2. Mode persistence (`--auto` / `--disable`, AC-023)
# ---------------------------------------------------------------------------


def test_sign_disable_persists_the_mode_and_dry_run_writes_nothing(
    tmp_path: pathlib.Path, capsys
) -> None:
    project = _project(tmp_path)
    config = _write_config(project)
    before = config.read_text(encoding="utf-8")
    assert mw.cmd_decide(_sign_args(project, key=KEY, disable=True, dry_run=True)) == 0
    assert "would write" in capsys.readouterr().out
    assert config.read_text(encoding="utf-8") == before
    assert mw.cmd_decide(_sign_args(project, key=KEY, disable=True)) == 0
    stored = json.loads(config.read_text(encoding="utf-8"))
    assert stored["signoff"] == "disable"


def test_sign_auto_and_disable_are_mutually_exclusive(tmp_path: pathlib.Path, capsys) -> None:
    project = _project(tmp_path)
    assert mw.cmd_decide(_sign_args(project, key=KEY, auto=True, disable=True)) == 2
    assert "mutually exclusive" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# 3. The automatic flow (AC-024, D-066)
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# 4. `signoff=disable` (AC-025)
# ---------------------------------------------------------------------------


def test_disable_prints_and_writes_nothing(tmp_path: pathlib.Path, capsys) -> None:
    project = _project(tmp_path)
    _write_config(project, signoff="disable")
    assert mw.cmd_decide(_sign_args(project, key=KEY)) == 0
    out = capsys.readouterr().out
    assert "signoff disabled" in out
    assert not _sign_file(project).exists()
    assert not _archive(project).exists()


def test_disable_lets_the_done_gate_pass(tmp_path: pathlib.Path) -> None:
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = _key_dir(project)
    _write_config(project, signoff="disable")
    # A real jev row would normally require the file (AC-002); disable waives it.
    _append_true_engine_row(project)
    _passed, failures = advance.check_gate(key_dir, "done")
    assert not any("SIGNOFF" in failure or "sign-final" in failure for failure in failures), failures


def test_advance_phase_mirrors_are_byte_identical() -> None:
    """`scripts/` is canonical and `core|claude/scripts/` are its byte mirrors.

    The `signoff=disable` exemption has to land in the canonical copy, otherwise
    `install.py`'s sync (scripts -> mirrors) would silently drop it; this test
    locks the invariant for that edit.
    """
    copies = [
        REPO_ROOT / ".agents" / "skills" / "agentic-task" / rel
        for rel in (
            "scripts/advance_phase.py",
            "core/scripts/advance_phase.py",
            "claude/scripts/advance_phase.py",
        )
    ]
    if not all(copy.is_file() for copy in copies):
        pytest.skip("AgenticTask framework clone not present under .agents/skills")
    first = copies[0].read_bytes()
    for copy in copies[1:]:
        assert copy.read_bytes() == first, f"{copy} drifted from the canonical scripts/ copy"


def test_auto_keeps_the_gate_closed_without_the_file(tmp_path: pathlib.Path) -> None:
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = _key_dir(project)
    _write_config(project, signoff="auto")
    # AC-002: the model took part (one real jev row), so the missing file blocks.
    _append_true_engine_row(project)
    _passed, failures = advance.check_gate(key_dir, "done")
    assert any("sign-final.md" in failure for failure in failures), failures


# ---------------------------------------------------------------------------
# 5. The writer has no session gate (AC-008)
# ---------------------------------------------------------------------------


def test_write_signoff_has_no_session_gate(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every face is gone: the writer accepts any caller, agent session or not."""
    project = _project(tmp_path)
    monkeypatch.setenv("PI_CODING_AGENT", "1")
    monkeypatch.setenv("PI_WORKER_TASK", "task.md")
    key_dir = _key_dir(project)
    assert decide_signoff.agent_session_vars() == ["PI_CODING_AGENT", "PI_WORKER_TASK"]
    path = decide_signoff.write_signoff(key_dir, KEY, "conclusion: narrow\n")
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == "conclusion: narrow\n"
    # Overwrite works too: no `allow_agent_session` / `signed_via` parameter exists.
    path = decide_signoff.write_signoff(key_dir, KEY, "conclusion: revoke\n")
    assert path.read_text(encoding="utf-8") == "conclusion: revoke\n"
    with pytest.raises(TypeError):
        decide_signoff.write_signoff(
            key_dir, KEY, "conclusion: narrow\n", signed_via="auto-decide"
        )


# ---------------------------------------------------------------------------
# 6. The registered decision point (AC-027)
# ---------------------------------------------------------------------------


def test_dp25_executor_echoes_the_conclusion_and_writes_nothing(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    _append_true_engine_row(project)
    point = dpts.get_decision_point(decide_signoff.SIGNOFF_DP_ID)
    state = decide_signoff.signoff_state(decide_signoff.collect(project, KEY), KEY)
    trigger = dpts.Trigger.from_mapping(state, key=state["key"], trigger_id="echo-1")

    before = _tree_bytes(project)
    action = point.executor(
        {"q-conclusion": {"value": "continue", "confidence": 0.9}}, trigger
    )
    assert action == "signoff:continue"
    assert _tree_bytes(project) == before, "the dp25 executor must not write anything"
    assert not _sign_file(project).exists()
    # State fallback keeps the echo meaningful when the answer mapping is empty.
    assert point.executor({}, dpts.Trigger(data={"conclusion": "revoke"})) == "signoff:revoke"


def test_signoff_state_is_assembled_from_the_facts_only(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _append_true_engine_row(project, trigger="t1")
    _write_points_table(project, {"dp8-scope-change": {"enabled": True}})
    facts = decide_signoff.collect(project, KEY)
    state = decide_signoff.signoff_state(facts, KEY)
    assert state["key"] == KEY
    assert state["rows_total"] == 1
    assert state["rows_available"] == 1
    assert state["rows_escalated"] == 0
    assert state["chain_ok"] is True
    assert state["p0_open"] == ["dp8-scope-change"]
    assert state["engine_violations"] == []
    assert state["escalated_reasons"] == []
    assert state["decision_point"] == decide_signoff.SIGNOFF_DP_ID
    # Nothing outside the collected facts is part of the state.
    assert set(state) <= {
        "schema_version",
        "decision_point",
        "questions_version",
        "key",
        "rows_total",
        "rows_available",
        "rows_escalated",
        "chain_ok",
        "p0_open",
        "escalated_reasons",
        "engine_violations",
    }


# ---------------------------------------------------------------------------
# 3. The legacy count face is refused; the material face is `--stdin`
# ---------------------------------------------------------------------------

NEW_MATERIAL_KEYS = (
    "delivery_goal",
    "actual_completion",
    "verification_evidence",
    "unfinished_impact",
)

DP25_MATERIAL = {
    "delivery_goal": "prove live coverage without a model",
    "actual_completion": "the four-part material reaches the transport",
    "verification_evidence": {
        "verified": ["pytest test_decide_sign_auto.py -q"],
        "unverified": ["real Jev endpoint (not authorized)"],
    },
    "unfinished_impact": [],
}


def _assert_legacy_refusal(completed: int, capsys, project: pathlib.Path) -> None:
    assert completed == 2
    err = capsys.readouterr().err
    assert "--stdin" in err
    for part in NEW_MATERIAL_KEYS:
        assert part in err, err
    assert "nothing was written" in err
    assert not _sign_file(project).exists()
    rows = [row for _lineno, row in decide_archive.iter_rows(_archive(project))]
    assert not any(row.get("kind") == "authority-change" for row in rows)


def test_sign_auto_persists_the_mode_and_exits_zero(
    tmp_path: pathlib.Path, capsys
) -> None:
    project = _project(tmp_path)
    _write_config(project, signoff="disable")
    assert mw.cmd_decide(_sign_args(project, key=KEY, auto=True)) == 0
    out = capsys.readouterr().out
    assert "signoff: auto" in out
    stored = json.loads((project / ".mw" / "decide.json").read_text(encoding="utf-8"))
    assert stored["signoff"] == "auto"
    assert stored["enabled"] is True, "persisting signoff must keep every other key"
    # `--auto` is the mode-persist face only; the next plain invocation is the
    # legacy count face, which the approved design refuses.
    assert not _sign_file(project).exists()
    _assert_legacy_refusal(mw.cmd_decide(_sign_args(project, key=KEY)), capsys, project)


def test_legacy_face_is_refused_for_every_configuration(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    _append_true_engine_row(project)
    backend = _backend(monkeypatch, conclusion="continue")

    _assert_legacy_refusal(mw.cmd_decide(_sign_args(project, key=KEY)), capsys, project)
    assert backend.calls == [], "the refusal happens before any model call"

    # A disabled dp25 row cannot change that: the entry does not ask dp25 at all.
    _write_points_table(project, {decide_signoff.SIGNOFF_DP_ID: {"enabled": False}})
    _assert_legacy_refusal(mw.cmd_decide(_sign_args(project, key=KEY)), capsys, project)
    assert backend.calls == []

    # A missing/typod registry point cannot change it either.
    monkeypatch.setattr(
        decide_signoff.decision_points,
        "get_decision_point",
        lambda dp_id: (_ for _ in ()).throw(decision.DecisionInputError("unknown dp")),
    )
    _assert_legacy_refusal(mw.cmd_decide(_sign_args(project, key=KEY)), capsys, project)


def test_legacy_face_is_refused_inside_an_agent_session(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    monkeypatch.setenv("PI_WORKER_TASK", "task.md")
    monkeypatch.setenv("PI_CODING_AGENT", "1")
    _assert_legacy_refusal(mw.cmd_decide(_sign_args(project, key=KEY)), capsys, project)


def test_sign_without_jev_is_refused_not_a_silent_success(
    tmp_path: pathlib.Path, capsys
) -> None:
    project = _project(tmp_path)
    _assert_legacy_refusal(mw.cmd_decide(_sign_args(project, key=KEY)), capsys, project)


def test_dp25_rows_never_enter_the_signed_counts(
    tmp_path: pathlib.Path,
) -> None:
    """The advice row cannot pad `counted_rows`/`rows_sha256` (D-067)."""
    project = _project(tmp_path)
    _write_config(project)
    _append_true_engine_row(project)
    before = decide_signoff.collect(project, KEY)
    decide_archive.append_decide(
        _archive(project),
        available=True,
        answer={"q-conclusion": {"value": "finalize", "confidence": 0.9}},
        authority="advisory",
        acted=False,
        actual_action="signoff:echo",
        dp=decide_signoff.SIGNOFF_DP_ID,
        key=KEY,
        task_key="task-1",
        trigger_id="dp25-1",
        state={"delivery_goal": "g", "actual_completion": "a"},
        questions_version=QP,
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
    )
    after = decide_signoff.collect(project, KEY)
    assert len(after.rows) == len(before.rows) == 1
    assert after.sha256 == before.sha256
    assert any(
        row.get("dp") == decide_signoff.SIGNOFF_DP_ID
        for _lineno, row in decide_archive.iter_rows(_archive(project))
    )


def test_collect_counts_only_the_requested_key(tmp_path: pathlib.Path) -> None:
    other = "k-any-other-key"
    project = _project(tmp_path, key=other)
    _write_config(project)
    _append_true_engine_row(project, trigger="any-1", key=other)
    _append_true_engine_row(project, trigger="fixture-1")
    facts = decide_signoff.collect(project, other)
    assert facts.key == other
    assert len(facts.rows) == 1, "only the requested key's rows are counted"


def test_dp25_is_registered_with_the_contracted_shape() -> None:
    assert len(dpts.DP_REGISTRY) == dpts.EXPECTED_DP_COUNT == 25
    point = dpts.get_decision_point(decide_signoff.SIGNOFF_DP_ID)
    assert point.tier == "P2"
    assert point.default_enabled is True
    assert point.default_mode == "auto"
    assert dpts._executor_kind(point.executor) == "wired"
    # T01/T05: the sign-off material itself, never archive counts.
    assert dpts.REQUIRED_STATE_FIELDS[point.id] == (
        "delivery_goal",
        "actual_completion",
        "verification_evidence.verified",
        "verification_evidence.unverified",
        "unfinished_impact",
    )
    assert dpts.MODEL_STATE_FIELDS[point.id] == dpts.REQUIRED_STATE_FIELDS[point.id]
    [question] = point.questions
    assert question["id"] == "q-conclusion"
    assert question["type"] == decision.QUESTION_CHOICE
    assert question["choices"] == ["finalize", "continue", "user-confirm"]
    assert set(question["labels"]) == {"finalize", "continue", "user-confirm"}


def test_dp25_is_on_by_default(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _write_config(project)
    point = dpts.get_decision_point(decide_signoff.SIGNOFF_DP_ID)
    effective = dpts.load_points_config(project).effective(point)
    assert effective.source == "default", "no .mw/decide-points.json row exists yet"
    assert effective.enabled is True
    assert effective.mode == "auto"


def _dp25_trigger(trigger_id: str = "t1") -> "dpts.Trigger":
    return dpts.Trigger.from_mapping(dict(DP25_MATERIAL), key=KEY, trigger_id=trigger_id)


def test_dp25_executor_is_not_called_on_the_answer_path(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`intent="answer"` returns at step 9, so the executor never runs."""
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    backend = _backend(monkeypatch, conclusion="finalize")
    point = dpts.get_decision_point(decide_signoff.SIGNOFF_DP_ID)
    calls: list[dict] = []

    def probe(answers: dict, trigger: dpts.Trigger) -> str:
        calls.append(answers)
        return "signoff:probe"

    monkeypatch.setitem(
        dpts._REGISTRY_BY_ID, point.id, dataclasses.replace(point, executor=probe)
    )
    outcome = dpts.decide_for(
        point.id, _dp25_trigger(), project, backend=backend, intent="answer", archive=False
    )
    assert outcome.status in ("acted", "suggested"), outcome.detail
    assert calls == [], "an answer call site must never execute the point"
    assert backend.calls, "answering still asks the transport"


def test_intent_act_returns_the_echo_and_never_writes_the_sign_file(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    backend = _backend(monkeypatch, conclusion="finalize")
    config_before = (project / ".mw" / "decide.json").read_bytes()

    outcome = dpts.decide_for(
        decide_signoff.SIGNOFF_DP_ID, _dp25_trigger("act-1"), project, backend=backend, intent="act"
    )
    assert outcome.status == "acted", outcome.detail
    assert outcome.actual_action == "signoff:finalize"
    assert not _sign_file(project).exists(), "the write stays in `mw decide sign`"
    assert (project / ".mw" / "decide.json").read_bytes() == config_before
