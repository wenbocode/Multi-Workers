"""test_decide_signoff.py - FIX-P: `mw decide sign` + the `decision_signoff` gate.

Hermetic pytest suite (key mw-decision-substitution) for the sign-off face the
2026-10-21 decision settled on:

* (a) :mod:`decide_signoff` - ``collect`` / ``verdict`` / ``render`` /
  ``write_signoff`` - and the ``mw decide sign`` CLI: a summary first, then the
  machine lines (``counted_rows`` / ``rows_sha256``) written into
  ``<key>/evidence/review/sign-final.md`` with one ``authority-change`` row.
* (b) the ``advance_phase.py`` ``decision_signoff`` check: the rule runs for
  every key (``decision-scope.md`` is inert, AC-002b) but only *requires* a
  signed file when the key's archive carries >=1 ``kind=decide`` row (AC-001 /
  AC-002). It recomputes the archive facts, so a signed file stops matching the
  moment the archive changes. ``continue`` needs N>=1 and *every* row on the
  real jev triple (``timi-decisions`` / ``jev-latest`` / ``api``);
  ``narrow``/``revoke`` take authority away and only need an intact hash chain.

The 2026-10-22 decide-only ruling removed every human face: ``mw decide sign``
has no ``--conclusion`` / ``--human-confirmed``, ``signed_via`` is
``auto-decide`` only, and ``write_signoff`` no longer refuses inside an agent
session. Tests that asserted the removed faces are rewritten (or dropped), not
kept as compatibility.

Everything runs under ``tmp_path``; the only backend is
``decision.FakeBackend``, so no network and no credential.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import pathlib
import re
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

KEY = "k-signoff"
QP = "q-0123abcd"
TRUE_TRANSPORT = "timi-decisions"
TRUE_MODEL = "jev-latest"
TRUE_CONFIDENCE = "api"
GATE_RE = r"(?m)^conclusion:\s*(continue|narrow|revoke)\s*$"


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


def _archive(project: pathlib.Path) -> pathlib.Path:
    return decide_signoff.archive_path(project)


def _write_config(project: pathlib.Path, **fields) -> pathlib.Path:
    """`.mw/decide.json` with ``enabled: true`` (the jev path needs it)."""
    path = project / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"enabled": True, **fields}, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _backend(
    monkeypatch: pytest.MonkeyPatch,
    *,
    conclusion: str = "continue",
    confidence: float = 0.9,
    available: bool = True,
) -> decision.FakeBackend:
    """A FakeBackend answering ``q-conclusion`` (no network)."""
    backend = decision.FakeBackend(
        results=None,
        name="timi-decisions",
        model="jev-latest",
        confidence_source=decision.CONFIDENCE_SOURCE_API,
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


def _append(
    project: pathlib.Path,
    *,
    trigger: str = "t1",
    key: str = KEY,
    dp: str = "dp3-worker-clarify",
    available: bool = True,
    escalated_reason: str | None = None,
    transport: str = TRUE_TRANSPORT,
    model: str = TRUE_MODEL,
    confidence_source: str = TRUE_CONFIDENCE,
) -> dict:
    """One valid ``kind=decide`` archive row (authority consistent with `available`)."""
    common = dict(
        dp=dp,
        key=key,
        task_key="task-1",
        trigger_id=trigger,
        state={"schema_version": 2, "decision_point": dp},
        questions_version=QP,
        mode="auto",
        transport=transport,
        model=model,
        confidence_source=confidence_source,
    )
    if not available:
        return decide_archive.append_decide(
            _archive(project),
            available=False,
            reason="entry-unavailable",
            answer=None,
            authority="human",
            escalated_reason=escalated_reason or "unavailable",
            acted=False,
            **common,
        )[0]
    return decide_archive.append_decide(
        _archive(project),
        available=True,
        answer={"answer_kind": {"value": "fact", "confidence": 0.9}},
        authority="binding",
        acted=True,
        actual_action="steer worker",
        **common,
    )[0]


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


def _sign_file(project: pathlib.Path, *, key: str = KEY) -> pathlib.Path:
    return decide_signoff.signoff_path(project, key)


def _load_advance_phase():
    if not ADVANCE_PHASE.is_file():
        pytest.skip("AgenticTask framework clone not present under .agents/skills")
    if str(pathlib.Path(__file__).parent) not in sys.path:
        sys.path.insert(0, str(pathlib.Path(__file__).parent))
    spec = importlib.util.spec_from_file_location("advance_phase_fixp", ADVANCE_PHASE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_sign(
    project: pathlib.Path,
    conclusion: str,
    *,
    allow_empty: bool = False,
    key: str = KEY,
) -> pathlib.Path:
    """Write a real sign-off file from the archive's current facts."""
    facts = decide_signoff.collect(project, key)
    text = decide_signoff.render(
        facts, conclusion, None, key, "-", allow_empty=allow_empty, ts="T"
    )
    return decide_signoff.write_signoff(project, key, text)


# ---------------------------------------------------------------------------
# collect
# ---------------------------------------------------------------------------


def test_collect_empty_archive_is_zero_rows_and_intact_chain(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    facts = decide_signoff.collect(project, KEY)
    assert len(facts.rows) == 0
    assert facts.n_available == 0
    assert facts.chain_ok is True
    assert facts.sha256 == decide_signoff.rows_sha256([])
    assert facts.p0_source == "missing"


def test_collect_counts_and_engines(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _append(project, trigger="t1")
    _append(project, trigger="t2", available=False, escalated_reason="low-confidence")
    _append(project, trigger="t3", dp="dp1-dispatch-type")
    facts = decide_signoff.collect(project, KEY)
    assert len(facts.rows) == 3
    assert facts.n_available == 2
    assert facts.n_acted == 2
    assert facts.n_escalated == 1
    assert facts.engines == {"timi-decisions/jev-latest/api": 3}
    assert [row["dp"] for row in facts.rows] == [
        "dp3-worker-clarify",
        "dp3-worker-clarify",
        "dp1-dispatch-type",
    ]


def test_collect_matches_key_from_decision_id_suffix(tmp_path: pathlib.Path) -> None:
    """A row without a `key` column is matched by the `:<key>` decision_id suffix."""
    project = _project(tmp_path)
    _append(project, trigger=f"t1:{KEY}", key="")
    _append(project, trigger="t2", key="other-key")
    facts = decide_signoff.collect(project, KEY)
    assert len(facts.rows) == 1


# ---------------------------------------------------------------------------
# verdict
# ---------------------------------------------------------------------------


def test_continue_is_refused_with_n_zero(tmp_path: pathlib.Path) -> None:
    facts = decide_signoff.collect(_project(tmp_path), KEY)
    ok, problems = decide_signoff.verdict(facts, "continue")
    assert ok is False
    assert any("N=0" in problem for problem in problems)
    assert any("narrow/revoke" in problem for problem in problems)


def test_continue_passes_with_one_true_jev_row(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _append(project, trigger="t1")
    facts = decide_signoff.collect(project, KEY)
    ok, problems = decide_signoff.verdict(facts, "continue")
    assert ok is True
    assert problems == []


def test_continue_refuses_a_mixed_engine_row_and_names_its_seq(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _append(project, trigger="t1")
    _append(
        project,
        trigger="t2",
        transport="llm-transitional",
        confidence_source="model-self-report",
    )
    facts = decide_signoff.collect(project, KEY)
    ok, problems = decide_signoff.verdict(facts, "continue")
    assert ok is False
    assert any("seq 2" in problem for problem in problems)
    assert any("llm-transitional" in problem for problem in problems)


def test_continue_refuses_a_broken_chain(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    archive = _archive(project)
    archive.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "seq": 1,
        "prev_sha": "0" * 16,
        "kind": "decide",
        "decision_id": "dp3-worker-clarify:t1",
        "dp": "dp3-worker-clarify",
        "key": KEY,
        "available": True,
        "acted": True,
        "mode": "auto",
        "escalated_reason": None,
        "transport": TRUE_TRANSPORT,
        "model": TRUE_MODEL,
        "confidence_source": TRUE_CONFIDENCE,
        "ts": "2026-10-21T00:00:00+00:00",
    }
    broken = dict(row, seq=2, prev_sha="f" * 16, decision_id="dp3-worker-clarify:t2")
    archive.write_text(
        json.dumps(row) + "\n" + json.dumps(broken) + "\n", encoding="utf-8", newline="\n"
    )
    facts = decide_signoff.collect(project, KEY)
    assert facts.chain_ok is False
    ok, problems = decide_signoff.verdict(facts, "continue")
    assert ok is False
    assert any("hash chain" in problem for problem in problems)


@pytest.mark.parametrize("conclusion", ["narrow", "revoke"])
def test_narrow_and_revoke_pass_with_n_zero(
    tmp_path: pathlib.Path, conclusion: str
) -> None:
    facts = decide_signoff.collect(_project(tmp_path), KEY)
    ok, problems = decide_signoff.verdict(facts, conclusion)
    assert ok is True
    assert problems == []


def test_allow_empty_only_waives_the_continue_n_zero_rule(tmp_path: pathlib.Path) -> None:
    facts = decide_signoff.collect(_project(tmp_path), KEY)
    assert decide_signoff.verdict(facts, "continue", allow_empty=True)[0] is True
    # still refuses a broken chain / wrong engine: allow_empty is scoped to N=0
    assert decide_signoff.verdict(facts, "narrow", allow_empty=True)[0] is True


def test_invalid_conclusion_is_refused(tmp_path: pathlib.Path) -> None:
    facts = decide_signoff.collect(_project(tmp_path), KEY)
    ok, problems = decide_signoff.verdict(facts, "approve")
    assert ok is False
    assert any("invalid conclusion" in problem for problem in problems)


# ---------------------------------------------------------------------------
# render
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("conclusion", list(decide_signoff.CONCLUSIONS))
def test_render_conclusion_line_matches_the_gate_regex(
    tmp_path: pathlib.Path, conclusion: str
) -> None:
    facts = decide_signoff.collect(_project(tmp_path), KEY)
    text = decide_signoff.render(facts, conclusion, None, KEY, "-", ts="T")
    assert re.search(GATE_RE, text)
    assert f"conclusion: {conclusion}" in text.splitlines()
    assert "counted_rows: 0" in text.splitlines()
    assert f"rows_sha256: {facts.sha256}" in text.splitlines()
    assert "engine: timi-decisions/jev-latest/api" in text.splitlines()
    # machine lines `mw decide dp apply` parses must be present
    assert "promote: -" in text.splitlines()
    assert "demote: -" in text.splitlines()
    assert "p0-open: -" in text.splitlines()
    # human body: the P0 list says `none` when the table file is absent
    assert "none (.mw/decide-points.json 缺失)" in text


def test_render_marks_allow_empty_true(tmp_path: pathlib.Path) -> None:
    facts = decide_signoff.collect(_project(tmp_path), KEY)
    text = decide_signoff.render(
        facts, "continue", "no jev run yet", KEY, "claim-1", allow_empty=True, ts="T"
    )
    assert "allow_empty: true" in text.splitlines()
    assert "counted_rows: 0" in text.splitlines()
    assert "reason: no jev run yet" in text.splitlines()
    assert "claim: claim-1" in text.splitlines()
    assert decide_signoff.parse_signoff(text)["allow_empty"] == "true"


def test_render_is_consumable_by_dp_apply(tmp_path: pathlib.Path) -> None:
    """The same file the gate reads must still parse as a `dp apply` sign-off."""
    facts = decide_signoff.collect(_project(tmp_path), KEY)
    text = decide_signoff.render(facts, "narrow", None, KEY, "-", ts="T")
    payload, errors = mw._dp_apply_parse(text)
    assert errors == []
    assert payload["conclusion"] == "narrow"
    assert payload["promote"] == [] and payload["demote"] == []
    assert payload["p0-open"] == []


def test_render_counts_escalations_and_p0(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    table = project / ".mw" / "decide-points.json"
    table.parent.mkdir(parents=True)
    table.write_text(
        json.dumps({"version": 1, "points": {"dp8-scope-change": {"enabled": True}}}),
        encoding="utf-8",
    )
    dpts.clear_points_config_cache()
    _append(project, trigger="t1", available=False, escalated_reason="low-confidence")
    facts = decide_signoff.collect(project, KEY)
    assert facts.p0_open == ("dp8-scope-change",)
    text = decide_signoff.render(facts, "narrow", None, KEY, "-", ts="T")
    assert "| low-confidence | 1 |" in text
    assert "p0-open: dp8-scope-change" in text.splitlines()


@pytest.mark.parametrize("signed_via", list(decide_signoff.SIGNED_VIA_VALUES))
def test_render_signed_via_is_a_parseable_machine_line(
    tmp_path: pathlib.Path, signed_via: str
) -> None:
    """W9: every face is recorded at column 0 and read back by parse_signoff."""
    facts = decide_signoff.collect(_project(tmp_path), KEY)
    text = decide_signoff.render(facts, "narrow", None, KEY, "-", ts="T", signed_via=signed_via)
    assert f"signed_via: {signed_via}" in text.splitlines()
    assert decide_signoff.parse_signoff(text)["signed_via"] == signed_via
    payload, errors = mw._dp_apply_parse(text)
    assert errors == [] and payload["conclusion"] == "narrow"


def test_render_decide_fallback_is_one_parseable_line(tmp_path: pathlib.Path) -> None:
    facts = decide_signoff.collect(_project(tmp_path), KEY)
    text = decide_signoff.render(
        facts,
        "narrow",
        None,
        KEY,
        "-",
        ts="T",
        signed_via="auto-llm",
        decide_fallback="low-confidence: dp25-signoff-conclusion: confidence=0.2 < 0.7",
    )
    machines = decide_signoff.parse_signoff(text)
    assert machines["signed_via"] == "auto-llm"
    assert machines["decide_fallback"].startswith("low-confidence")
    # A newline in the reason must never forge a second machine line.
    forged = decide_signoff.render(
        facts, "narrow", None, KEY, "-", ts="T", decide_fallback="a\nconclusion: continue"
    )
    assert "conclusion: narrow" in forged.splitlines()
    assert "conclusion: continue" not in forged.splitlines()


# ---------------------------------------------------------------------------
# sha determinism
# ---------------------------------------------------------------------------


def test_rows_sha256_is_deterministic_and_changes_with_a_new_row(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    _append(project, trigger="t1")
    first = decide_signoff.collect(project, KEY).sha256
    second = decide_signoff.collect(project, KEY).sha256
    assert first == second
    _append(project, trigger="t2")
    assert decide_signoff.collect(project, KEY).sha256 != first


# ---------------------------------------------------------------------------
# write_signoff
# ---------------------------------------------------------------------------


def test_write_signoff_works_inside_an_agent_session(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-008: the writer has no agent-session gate; humans and agents walk one path."""
    project = _project(tmp_path)
    for name in decide_signoff.AGENT_SESSION_ENV_VARS:
        monkeypatch.setenv(name, "1")
    assert decide_signoff.agent_session_vars() == list(decide_signoff.AGENT_SESSION_ENV_VARS)

    path = decide_signoff.write_signoff(project, KEY, "conclusion: narrow\n")
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == "conclusion: narrow\n"
    # AGENT_SESSION_ENV_VARS stays exported for `mw decide dp apply`, not for this write.
    assert decide_signoff.AGENT_SESSION_ENV_VARS == (
        "PI_CODING_AGENT",
        "AI_AGENT",
        "PI_WORKER_TASK",
    )


def test_write_signoff_creates_parent_dirs(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    (project / ".agenticdoc").mkdir(parents=True)
    path = decide_signoff.write_signoff(project, KEY, "conclusion: revoke\n")
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == "conclusion: revoke\n"


# ---------------------------------------------------------------------------
# CLI `mw decide sign`
# ---------------------------------------------------------------------------


NEW_MATERIAL_KEYS = (
    "delivery_goal",
    "actual_completion",
    "verification_evidence",
    "unfinished_impact",
)


def _assert_legacy_refusal(
    completed: int, capsys, project: pathlib.Path
) -> None:
    """The one contract of a legacy (no ``--stdin``) invocation: refuse, write 0."""
    assert completed == 2
    err = capsys.readouterr().err
    assert "--stdin" in err
    for part in NEW_MATERIAL_KEYS:
        assert part in err, err
    assert "nothing was written" in err
    assert not _sign_file(project).exists()
    rows = [row for _lineno, row in decide_archive.iter_rows(_archive(project))]
    assert not any(row.get("kind") == "authority-change" for row in rows)


def test_cli_legacy_count_face_is_refused_with_zero_writes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    _append(project)
    backend = _backend(monkeypatch, conclusion="continue")
    _assert_legacy_refusal(mw.cmd_decide(_sign_args(project, key=KEY)), capsys, project)
    assert backend.calls == [], "the refusal happens before any model call"


def test_cli_legacy_dry_run_is_refused_too(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    backend = _backend(monkeypatch, conclusion="continue")
    _assert_legacy_refusal(
        mw.cmd_decide(_sign_args(project, key=KEY, dry_run=True)), capsys, project
    )
    assert backend.calls == []


def test_cli_json_refusal_keeps_a_stable_key_set(
    tmp_path: pathlib.Path, capsys
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    assert mw.cmd_decide(_sign_args(project, key=KEY, json=True)) == 2
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert set(payload) == {"conclusion", "ok", "problems", "facts", "path"}
    assert payload["conclusion"] is None
    assert payload["ok"] is False
    assert payload["facts"] is None
    assert payload["path"] is None
    assert any("--stdin" in problem for problem in payload["problems"])
    assert not _sign_file(project).exists()


def test_cli_infers_the_key_from_a_key_dir_project(
    tmp_path: pathlib.Path, capsys
) -> None:
    project = _project(tmp_path)
    _write_config(project)
    # `--project .agenticdoc/<key>` still resolves the key from the path, and the
    # migrated contract refuses the legacy face (never a silent count sign).
    args = _sign_args(project / ".agenticdoc" / KEY, key=None)
    assert mw.cmd_decide(args) == 2
    err = capsys.readouterr().err
    assert KEY in err or "--stdin" in err
    assert not _sign_file(project).exists()


def test_module_verdicts_still_gate_the_framework_face(tmp_path: pathlib.Path) -> None:
    """`decide_signoff.verdict` stays the gate's content check (unchanged)."""
    project = _project(tmp_path)
    facts = decide_signoff.collect(project / ".agenticdoc" / KEY, KEY)
    assert decide_signoff.verdict(facts, "continue")[0] is False
    assert decide_signoff.verdict(facts, "narrow") == (True, [])
    assert decide_signoff.verdict(facts, "revoke") == (True, [])


def test_cli_refuses_to_guess_the_key(tmp_path: pathlib.Path, capsys) -> None:
    project = _project(tmp_path)
    assert mw.cmd_decide(_sign_args(project)) == 2
    assert "cannot infer the key" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# (b) the done gate
# ---------------------------------------------------------------------------


def test_gate_passes_a_key_without_any_decide_row(tmp_path: pathlib.Path) -> None:
    """AC-002b: `decision-scope.md` is inert; no decide row means no sign-off."""
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    (key_dir / "decision-scope.md").write_text("scope\n", encoding="utf-8")
    assert advance._key_has_decide_rows(key_dir) is False
    assert advance._decision_signoff_problems(key_dir) == []
    passed, failures = advance.check_gate(key_dir, "done")
    assert not any("SIGNOFF" in failure for failure in failures), failures
    assert passed is False  # the pre-existing done rules still fail; no sign-off check ran


def test_gate_blocks_continue_with_n_zero(tmp_path: pathlib.Path) -> None:
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    (key_dir / "decision-scope.md").write_text("scope\n", encoding="utf-8")
    # The gate only looks when a real decide row exists; this one escalated, so
    # counted_rows=1 while N (available rows) stays 0.
    _append(project, trigger="t1", available=False, escalated_reason="low-confidence")
    _write_sign(project, "continue", allow_empty=True)
    _passed, failures = advance.check_gate(key_dir, "done")
    assert advance._key_has_decide_rows(key_dir) is True
    assert any("N=0" in failure for failure in failures), failures


def test_gate_passes_narrow_with_n_zero(tmp_path: pathlib.Path) -> None:
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    _append(project, trigger="t1", available=False, escalated_reason="low-confidence")
    _write_sign(project, "narrow")
    # Not a vacuous pass: the key has a decide row, so the full check really ran.
    assert advance._key_has_decide_rows(key_dir) is True
    assert advance._decision_signoff_problems(key_dir) == []
    _passed, failures = advance.check_gate(key_dir, "done")
    assert not any("SIGNOFF" in failure for failure in failures), failures


def test_gate_blocks_after_the_archive_is_appended(tmp_path: pathlib.Path) -> None:
    """The signature covers the counted rows: a later row invalidates the sha."""
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    _append(project, trigger="t1")
    _write_sign(project, "continue")
    _passed, failures = advance.check_gate(key_dir, "done")
    assert not any("SIGNOFF" in failure for failure in failures), failures

    _append(project, trigger="t2")
    _passed, failures = advance.check_gate(key_dir, "done")
    assert any("rows_sha256 不匹配" in failure for failure in failures), failures


def test_gate_blocks_a_missing_machine_line(tmp_path: pathlib.Path) -> None:
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    _append(project, trigger="t1")
    sign = _sign_file(project)
    sign.parent.mkdir(parents=True, exist_ok=True)
    sign.write_text("conclusion: narrow\n", encoding="utf-8", newline="\n")
    _passed, failures = advance.check_gate(key_dir, "done")
    assert any("counted_rows" in failure for failure in failures), failures
    assert any("rows_sha256" in failure for failure in failures), failures


def test_gate_fails_a_key_with_decide_rows_and_no_file(
    tmp_path: pathlib.Path,
) -> None:
    """AC-002: the model took part, so the missing file is a locatable blocker."""
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    _append(project, trigger="t1")
    _passed, failures = advance.check_gate(key_dir, "done")
    assert any(
        "MISSING" in failure and "sign-final.md" in failure for failure in failures
    ), failures


def test_gate_ignores_rows_for_other_keys(tmp_path: pathlib.Path) -> None:
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    _append(project, trigger="other-1", key="other-key")
    assert advance._key_has_decide_rows(key_dir) is False
    _passed, failures = advance.check_gate(key_dir, "done")
    assert not any(
        "SIGNOFF" in failure or "sign-final.md" in failure for failure in failures
    ), failures


def test_gate_treats_an_unreadable_archive_as_having_rows(
    tmp_path: pathlib.Path,
) -> None:
    """UnicodeDecodeError is fail-loud: "cannot read" must not read as "no rows"."""
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    archive = _archive(project)
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(b"\xff\xfe not utf-8\n")
    assert advance._key_has_decide_rows(key_dir) is True
    _passed, failures = advance.check_gate(key_dir, "done")
    assert any(
        "MISSING" in failure and "sign-final.md" in failure for failure in failures
    ), failures


# ---------------------------------------------------------------------------
# The machine-line vocabulary the readers share
# ---------------------------------------------------------------------------


def test_signed_via_vocabulary_is_auto_decide_only() -> None:
    """AC-006: the decision model is the only authority, so one value is writable."""
    assert decide_signoff.SIGNED_VIA_VALUES == ("auto-decide",)


def test_signed_via_line_leaves_the_gate_and_dp_apply_parse_untouched(
    tmp_path: pathlib.Path,
) -> None:
    """The line is evidence and a machine line: every reader still agrees."""
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    _append(project, trigger="t1")
    facts = decide_signoff.collect(project, KEY)
    text = decide_signoff.render(
        facts, "narrow", None, KEY, "-", ts="T", signed_via="auto-decide"
    )
    assert "signed_via: auto-decide" in text.splitlines()
    assert re.search(GATE_RE, text)
    payload, errors = mw._dp_apply_parse(text)
    assert errors == []
    assert payload["conclusion"] == "narrow"
    # `signed_via` is part of the machine-line vocabulary now (render() emits
    # it), so parse_signoff reads it; `dp apply` ignores the unknown name.
    assert decide_signoff.parse_signoff(text)["signed_via"] == "auto-decide"
    decide_signoff.write_signoff(project, KEY, text)
    # The check really ran (the key has a decide row) and the extra line is inert.
    assert advance._key_has_decide_rows(key_dir) is True
    _passed, failures = advance.check_gate(key_dir, "done")
    assert not any("SIGNOFF" in failure for failure in failures), failures


# ---------------------------------------------------------------------------
# `--dry-run --json`: the zero-write pre-judge (AC-003)
# ---------------------------------------------------------------------------
