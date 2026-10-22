"""test_decide_sign_auto.py - W9: the sign-off belongs to the decision model.

Spec §15 (AC-023..AC-027) / design D-064..D-071 replaced "a human signs outside
the agent session" with:

* ``.mw/decide.json`` ``signoff`` = ``auto`` (default) | ``disable``, written by
  ``mw decide sign --auto|--disable`` (fail-soft read, D-065);
* ``auto`` asks ``dp25-signoff-conclusion`` first (state assembled from
  ``decide_signoff.collect()`` facts only) and records ``signed_via:
  auto-decide``; when jev cannot answer, the caller's ``--conclusion`` is the
  LLM face (``signed_via: auto-llm`` + ``decide_fallback: <reason>``); with
  neither it is a read-only preview (exit 0);
* ``disable`` writes nothing and the ``done`` gate stops requiring
  ``sign-final.md``;
* an explicit ``--conclusion`` without a mode flag keeps the human semantics
  (``cli`` / ``tui``) and an agent session is still refused.

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
    base = {
        "subcommand": "decide",
        "decide_action": "sign",
        "project": str(project),
        "key": None,
        "conclusion": None,
        "reason": None,
        "allow_empty": False,
        "dry_run": False,
        "json": False,
        "human_confirmed": False,
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


def test_sign_auto_persists_the_mode_and_exits_zero(tmp_path: pathlib.Path, capsys) -> None:
    project = _project(tmp_path)
    _write_config(project, signoff="disable")
    assert mw.cmd_decide(_sign_args(project, key=KEY, auto=True)) == 0
    out = capsys.readouterr().out
    assert "signoff: auto" in out
    stored = json.loads((project / ".mw" / "decide.json").read_text(encoding="utf-8"))
    assert stored["signoff"] == "auto"
    assert stored["enabled"] is True, "persisting signoff must keep every other key"
    assert not _sign_file(project).exists()


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


def test_auto_decide_writes_signed_via_auto_decide(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    _append_true_engine_row(project)
    _backend(monkeypatch, conclusion="continue")

    assert mw.cmd_decide(_sign_args(project, key=KEY)) == 0
    machines = _parse_machines(project)
    assert machines["conclusion"] == "continue"
    assert machines["signed_via"] == "auto-decide"
    assert "decide_fallback" not in machines
    # AC-024: the audit row names the automatic face. `decide_archive._CHANGE_BY`
    # is frozen to `human|human:p0-confirm|signoff:<conclusion>|refresh`, so the
    # face rides the note column (`signed_via=<value>`) instead.
    rows = [row for _lineno, row in decide_archive.iter_rows(_archive(project))]
    assert rows[-1]["kind"] == "authority-change"
    assert rows[-1]["by"] == "signoff:continue"
    assert rows[-1]["note"] == "signed_via=auto-decide"
    # The dp25 decision itself is archived (advisory, nothing executed).
    assert any(
        row.get("dp") == decide_signoff.SIGNOFF_DP_ID and row.get("kind") == "decide"
        for row in rows
    )
    assert "signed_via: auto-decide" in capsys.readouterr().out


def test_auto_decide_is_allowed_inside_an_agent_session(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-026: the automatic face is exactly the one that must work in a session."""
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    _append_true_engine_row(project)
    _backend(monkeypatch, conclusion="continue")
    monkeypatch.setenv("PI_WORKER_TASK", "task.md")
    monkeypatch.setenv("PI_CODING_AGENT", "1")

    assert mw.cmd_decide(_sign_args(project, key=KEY)) == 0
    assert _parse_machines(project)["signed_via"] == "auto-decide"


def test_auto_decide_narrow_with_no_rows_is_written(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    _backend(monkeypatch, conclusion="narrow")

    assert mw.cmd_decide(_sign_args(project, key=KEY)) == 0
    machines = _parse_machines(project)
    assert machines["conclusion"] == "narrow"
    assert machines["signed_via"] == "auto-decide"
    assert machines["counted_rows"] == "0"


def test_low_confidence_falls_back_to_llm_and_records_decide_fallback(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    _append_true_engine_row(project)
    _backend(monkeypatch, conclusion="continue", confidence=0.2)

    assert mw.cmd_decide(_sign_args(project, key=KEY, auto=True, conclusion="narrow")) == 0
    machines = _parse_machines(project)
    assert machines["conclusion"] == "narrow"
    assert machines["signed_via"] == "auto-llm"
    assert machines["decide_fallback"].startswith("low-confidence")
    rows = [row for _lineno, row in decide_archive.iter_rows(_archive(project))]
    assert rows[-1]["note"].startswith("signed_via=auto-llm; decide_fallback=low-confidence")


def test_unavailable_transport_falls_back_to_llm(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    _backend(monkeypatch, available=False)

    assert mw.cmd_decide(_sign_args(project, key=KEY, auto=True, conclusion="revoke")) == 0
    machines = _parse_machines(project)
    assert machines["signed_via"] == "auto-llm"
    assert machines["conclusion"] == "revoke"
    assert machines["decide_fallback"].startswith("unavailable")


def test_dp25_disabled_falls_back_and_names_the_reason(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    # Table exists but leaves dp25 off (P1 defaults to disabled).
    _write_points_table(project, {decide_signoff.SIGNOFF_DP_ID: {"enabled": False}})
    backend = _backend(monkeypatch, conclusion="continue")

    assert mw.cmd_decide(_sign_args(project, key=KEY, auto=True, conclusion="revoke")) == 0
    machines = _parse_machines(project)
    assert machines["signed_via"] == "auto-llm"
    assert "disabled" in machines["decide_fallback"]
    assert backend.calls == [], "a disabled point must not reach the transport"


def test_dp25_not_registered_falls_back_to_llm(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    _append_true_engine_row(project)
    backend = _backend(monkeypatch, conclusion="continue")
    monkeypatch.setattr(
        decide_signoff.decision_points,
        "get_decision_point",
        lambda dp_id: (_ for _ in ()).throw(decision.DecisionInputError("unknown dp")),
    )

    assert mw.cmd_decide(_sign_args(project, key=KEY, auto=True, conclusion="narrow")) == 0
    machines = _parse_machines(project)
    assert machines["signed_via"] == "auto-llm"
    assert "not registered" in machines["decide_fallback"]
    assert backend.calls == []


def test_auto_without_jev_and_without_conclusion_is_a_preview(
    tmp_path: pathlib.Path, capsys
) -> None:
    project = _project(tmp_path)
    assert mw.cmd_decide(_sign_args(project, key=KEY)) == 0
    out = capsys.readouterr().out
    assert "signoff=auto but no conclusion available" in out
    assert "--disable" in out
    assert "counted_rows=0" in out
    assert not _sign_file(project).exists()


def test_auto_decide_continue_still_runs_the_verdict(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    """The model's answer never bypasses the local content check."""
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    decide_archive.append_decide(
        _archive(project),
        available=True,
        answer={"answer_kind": {"value": "fact", "confidence": 0.9}},
        authority="binding",
        acted=True,
        actual_action="steer worker",
        dp="dp3-worker-clarify",
        key=KEY,
        task_key="task-1",
        trigger_id="t1",
        state={"schema_version": 2, "decision_point": "dp3-worker-clarify"},
        questions_version=QP,
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="model-self-report",
    )
    _backend(monkeypatch, conclusion="continue")

    assert mw.cmd_decide(_sign_args(project, key=KEY)) == 2
    assert "engine mismatch" in capsys.readouterr().err
    assert not _sign_file(project).exists()


def test_dp25_rows_never_enter_the_signed_counts(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The advice row cannot pad `counted_rows`/`rows_sha256` (D-067)."""
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    _append_true_engine_row(project)
    before = decide_signoff.collect(project, KEY)
    _backend(monkeypatch, conclusion="continue")
    assert mw.cmd_decide(_sign_args(project, key=KEY)) == 0
    after = decide_signoff.collect(project, KEY)
    assert len(after.rows) == len(before.rows) == 1
    assert after.sha256 == before.sha256
    assert _parse_machines(project)["counted_rows"] == "1"
    # dp25 did archive its own row, it is just not part of the signable set.
    assert any(
        row.get("dp") == decide_signoff.SIGNOFF_DP_ID
        for _lineno, row in decide_archive.iter_rows(_archive(project))
    )


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
    (key_dir / "decision-scope.md").write_text("scope\n", encoding="utf-8")
    _write_config(project, signoff="disable")
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
    (key_dir / "decision-scope.md").write_text("scope\n", encoding="utf-8")
    _write_config(project, signoff="auto")
    _passed, failures = advance.check_gate(key_dir, "done")
    assert any("sign-final.md" in failure for failure in failures), failures


# ---------------------------------------------------------------------------
# 5. The human face is unchanged (AC-026)
# ---------------------------------------------------------------------------


def test_explicit_conclusion_without_a_mode_flag_keeps_cli_semantics(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    _append_true_engine_row(project)

    assert mw.cmd_decide(_sign_args(project, key=KEY, conclusion="continue")) == 0
    machines = _parse_machines(project)
    assert machines["signed_via"] == "cli"
    assert "decide_fallback" not in machines


def test_explicit_conclusion_without_a_mode_flag_is_refused_in_an_agent_session(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    _enable_dp25(project)
    _append_true_engine_row(project)
    monkeypatch.setenv("PI_WORKER_TASK", "task.md")

    assert mw.cmd_decide(_sign_args(project, key=KEY, conclusion="continue")) == 2
    assert "agent session" in capsys.readouterr().err
    assert not _sign_file(project).exists()


def test_write_signoff_only_opens_for_the_auto_values(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.setenv("PI_CODING_AGENT", "1")
    key_dir = _key_dir(project)
    with pytest.raises(decide_signoff.SignoffError):
        decide_signoff.write_signoff(
            key_dir, KEY, "conclusion: narrow\n", allow_agent_session=True, signed_via="cli"
        )
    path = decide_signoff.write_signoff(
        key_dir,
        KEY,
        "conclusion: narrow\n",
        allow_agent_session=True,
        signed_via="auto-llm",
    )
    assert path.is_file()


# ---------------------------------------------------------------------------
# 6. The registered decision point (AC-027)
# ---------------------------------------------------------------------------


def test_dp25_is_registered_with_the_contracted_shape() -> None:
    assert len(dpts.DP_REGISTRY) == dpts.EXPECTED_DP_COUNT == 25
    point = dpts.get_decision_point(decide_signoff.SIGNOFF_DP_ID)
    # W11: P2 so the sign-off default path is on (P1 defaults to disabled).
    assert point.tier == "P2"
    assert point.default_enabled is True
    assert point.default_mode == "auto"
    # P2 requires an executor; dp25's is the side-effect-free echo, so it reads
    # `wired` (not the `_unwired_executor` placeholder that always raises).
    assert dpts._executor_kind(point.executor) == "wired"
    assert dpts.REQUIRED_STATE_FIELDS[point.id] == (
        "key",
        "rows_total",
        "rows_available",
        "chain_ok",
        "p0_open",
    )
    [question] = point.questions
    assert question["id"] == "q-conclusion"
    assert question["type"] == decision.QUESTION_CHOICE
    assert question["choices"] == ["continue", "narrow", "revoke"]
    assert set(question["labels"]) == {"continue", "narrow", "revoke"}
    assert "timi-decisions/jev-latest/api" in question["instructions"]


def test_dp25_is_on_by_default_and_the_default_signoff_path_asks_jev(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """W11: no authorization-table row => registry default (P2 => enabled)."""
    project = _project(tmp_path)
    _write_config(project)
    _append_true_engine_row(project)
    backend = _backend(monkeypatch, conclusion="continue")
    point = dpts.get_decision_point(decide_signoff.SIGNOFF_DP_ID)
    effective = dpts.load_points_config(project).effective(point)
    assert effective.source == "default", "no .mw/decide-points.json row exists yet"
    assert effective.enabled is True
    assert effective.mode == "auto"

    conclusion, detail = decide_signoff.auto_conclusion(project, KEY)
    assert conclusion == "continue", detail
    assert backend.calls, "the default path must reach the jev transport"
    assert detail.startswith(decide_signoff.SIGNOFF_DP_ID)

    # The whole default command path, not just the helper: no table row, no
    # `--conclusion`, yet the sign file is written from the jev answer.
    assert mw.cmd_decide(_sign_args(project, key=KEY)) == 0
    assert _parse_machines(project)["signed_via"] == "auto-decide"


def test_dp25_signs_any_key_not_just_the_fixture_key(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """dp25 is the per-KEY closure point: the key rides the caller, not code.

    mw-signoff-per-key ruling: every AgenticTask key can be signed with
    `mw decide sign --key <key>` (or `--project .agenticdoc/<key>`); the state
    carries that key and only that key's archive rows are counted.
    """
    other = "k-any-other-key"
    project = _project(tmp_path, key=other)
    _write_config(project)
    _append_true_engine_row(project, trigger="any-1", key=other)
    # A row for the fixture key must NOT leak into `other`'s facts.
    _append_true_engine_row(project, trigger="fixture-1")
    backend = _backend(monkeypatch, conclusion="continue")

    facts = decide_signoff.collect(project, other)
    assert facts.key == other
    assert len(facts.rows) == 1, "only the requested key's rows are counted"

    state = decide_signoff.signoff_state(facts, other)
    assert state["key"] == other
    assert state["rows_total"] == 1

    conclusion, detail = decide_signoff.auto_conclusion(project, other)
    assert conclusion == "continue", detail
    assert backend.calls, "the jev transport answers for any key"

    assert mw.cmd_decide(_sign_args(project, key=other)) == 0
    machines = _parse_machines(project, key=other)
    assert machines["key"] == other
    assert machines["signed_via"] == "auto-decide"
    assert machines["counted_rows"] == "1"


def test_dp25_executor_is_not_called_on_the_answer_path(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`intent="answer"` returns at step 9, so the executor never runs."""
    project = _project(tmp_path)
    _write_config(project)
    _append_true_engine_row(project)
    backend = _backend(monkeypatch, conclusion="narrow")
    point = dpts.get_decision_point(decide_signoff.SIGNOFF_DP_ID)
    calls: list[dict] = []

    def probe(answers: dict, trigger: dpts.Trigger) -> str:
        calls.append(answers)
        return "signoff:probe"

    monkeypatch.setitem(
        dpts._REGISTRY_BY_ID, point.id, dataclasses.replace(point, executor=probe)
    )
    conclusion, detail = decide_signoff.auto_conclusion(project, KEY)
    assert conclusion == "narrow", detail
    assert calls == [], "an answer call site must never execute the point"
    assert backend.calls, "answering still asks the transport"


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


def test_intent_act_returns_the_echo_and_never_writes_the_sign_file(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    _append_true_engine_row(project)
    backend = _backend(monkeypatch, conclusion="continue")
    config_before = (project / ".mw" / "decide.json").read_bytes()
    state = decide_signoff.signoff_state(decide_signoff.collect(project, KEY), KEY)
    trigger = dpts.Trigger.from_mapping(state, key=state["key"], trigger_id="act-1")

    outcome = dpts.decide_for(
        decide_signoff.SIGNOFF_DP_ID, trigger, project, backend=backend, intent="act"
    )
    assert outcome.status == "acted", outcome.detail
    assert outcome.actual_action == "signoff:continue"
    assert not _sign_file(project).exists(), "the write stays in `mw decide sign`"
    assert (project / ".mw" / "decide.json").read_bytes() == config_before


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


def test_signed_via_vocabulary_is_the_four_documented_faces() -> None:
    assert decide_signoff.AUTO_SIGNED_VIA == ("auto-decide", "auto-llm")
    assert decide_signoff.SIGNED_VIA_VALUES == ("auto-decide", "auto-llm", "cli", "tui")
