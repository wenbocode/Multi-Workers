"""test_decide_signoff.py - FIX-P: `mw decide sign` + the `decision_signoff` gate.

Hermetic pytest suite (key mw-decision-substitution) for the sign-off face the
2026-10-21 decision settled on:

* (a) :mod:`decide_signoff` - ``collect`` / ``verdict`` / ``render`` /
  ``write_signoff`` - and the ``mw decide sign`` CLI: a summary first, then the
  machine lines (``counted_rows`` / ``rows_sha256``) written into
  ``<key>/evidence/review/sign-final.md`` with one ``authority-change`` row.
* (b) the ``advance_phase.py`` ``decision_signoff`` check: only keys carrying
  ``decision-scope.md`` are checked, and the check recomputes the archive facts
  so a signed file stops matching the moment the archive changes. ``continue``
  needs N>=1 and *every* row on the real jev triple
  (``timi-decisions`` / ``jev-latest`` / ``api``); ``narrow``/``revoke`` take
  authority away and only need an intact hash chain.

Everything runs under ``tmp_path``; no backend, no network, no credential.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import pathlib
import re
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decide_archive  # noqa: E402
import decide_signoff  # noqa: E402
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


def test_write_signoff_auto_face_needs_the_flag(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """AC-026: `allow_agent_session` AND an ``auto`` face, never one alone."""
    project = _project(tmp_path)
    monkeypatch.setenv("PI_WORKER_TASK", "task.md")
    with pytest.raises(decide_signoff.SignoffError):
        decide_signoff.write_signoff(project, KEY, "conclusion: narrow\n")
    with pytest.raises(decide_signoff.SignoffError):
        decide_signoff.write_signoff(
            project, KEY, "conclusion: narrow\n", signed_via="auto-decide"
        )
    path = decide_signoff.write_signoff(
        project,
        KEY,
        "conclusion: narrow\n",
        allow_agent_session=True,
        signed_via="auto-decide",
    )
    assert path.is_file()


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


def test_write_signoff_refuses_inside_an_agent_session(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.setenv("PI_CODING_AGENT", "1")
    with pytest.raises(decide_signoff.SignoffError) as excinfo:
        decide_signoff.write_signoff(project, KEY, "conclusion: continue\n")
    assert "agent session" in str(excinfo.value)
    assert not _sign_file(project).exists()


def test_write_signoff_creates_parent_dirs(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "proj"
    (project / ".agenticdoc").mkdir(parents=True)
    path = decide_signoff.write_signoff(project, KEY, "conclusion: revoke\n")
    assert path.is_file()
    assert path.read_text(encoding="utf-8") == "conclusion: revoke\n"


# ---------------------------------------------------------------------------
# CLI `mw decide sign`
# ---------------------------------------------------------------------------


def test_cli_preview_writes_nothing(tmp_path: pathlib.Path, capsys) -> None:
    project = _project(tmp_path)
    assert mw.cmd_decide(_sign_args(project, key=KEY)) == 0
    out = capsys.readouterr().out
    assert "counted_rows=0" in out
    assert "rows_sha256=" in out
    assert "conclusion: <continue|narrow|revoke>" in out
    assert not _sign_file(project).exists()


def test_cli_continue_n_zero_exits_2_and_writes_nothing(
    tmp_path: pathlib.Path, capsys
) -> None:
    project = _project(tmp_path)
    assert mw.cmd_decide(_sign_args(project, key=KEY, conclusion="continue")) == 2
    err = capsys.readouterr().err
    assert "N=0" in err
    assert "narrow/revoke" in err
    assert "nothing was written" in err
    assert not _sign_file(project).exists()
    assert not _archive(project).exists()


def test_cli_allow_empty_records_the_flag(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    code = mw.cmd_decide(
        _sign_args(project, key=KEY, conclusion="continue", allow_empty=True)
    )
    assert code == 0
    text = _sign_file(project).read_text(encoding="utf-8")
    assert "allow_empty: true" in text.splitlines()
    assert "counted_rows: 0" in text.splitlines()


def test_cli_narrow_with_n_zero_passes(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    assert mw.cmd_decide(_sign_args(project, key=KEY, conclusion="narrow")) == 0
    assert _sign_file(project).is_file()


def test_cli_continue_writes_sign_file_and_authority_row(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _append(project, trigger="t1")
    code = mw.cmd_decide(
        _sign_args(project, key=KEY, conclusion="continue", reason="dp3 held up")
    )
    assert code == 0
    text = _sign_file(project).read_text(encoding="utf-8")
    assert "conclusion: continue" in text.splitlines()
    assert "counted_rows: 1" in text.splitlines()
    rows = [row for _lineno, row in decide_archive.iter_rows(_archive(project))]
    audit = rows[-1]
    assert audit["kind"] == "authority-change"
    assert audit["by"] == "signoff:continue"
    assert audit["change"] == "signoff"
    assert audit["conclusion"] == "continue"
    assert audit["key"] == KEY
    assert audit["dp"] == "dp3-worker-clarify"
    assert audit["prev_sha"] == decide_archive._row_sha(rows[-2])


def test_cli_mixed_engine_continue_exits_2(tmp_path: pathlib.Path, capsys) -> None:
    project = _project(tmp_path)
    _append(project, trigger="t1")
    _append(project, trigger="t2", transport="llm-transitional")
    assert mw.cmd_decide(_sign_args(project, key=KEY, conclusion="continue")) == 2
    err = capsys.readouterr().err
    assert "engine mismatch" in err
    assert "seq 2" in err
    assert not _sign_file(project).exists()


def test_cli_json_key_set(tmp_path: pathlib.Path, capsys) -> None:
    project = _project(tmp_path)
    _append(project, trigger="t1")
    code = mw.cmd_decide(_sign_args(project, key=KEY, conclusion="continue", json=True))
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"conclusion", "ok", "problems", "facts", "path"}
    assert payload["ok"] is True
    assert payload["conclusion"] == "continue"
    assert pathlib.Path(payload["path"]) == _sign_file(project)
    assert set(payload["facts"]) >= {
        "counted_rows",
        "n_available",
        "n_acted",
        "n_escalated",
        "engines",
        "sha256",
        "chain_ok",
        "rows",
    }


def test_cli_json_on_failure_keeps_the_key_set(tmp_path: pathlib.Path, capsys) -> None:
    project = _project(tmp_path)
    code = mw.cmd_decide(_sign_args(project, key=KEY, conclusion="continue", json=True))
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert set(payload) == {"conclusion", "ok", "problems", "facts", "path"}
    assert payload["ok"] is False
    assert payload["path"] is None
    assert payload["problems"]


def test_cli_dry_run_writes_nothing(tmp_path: pathlib.Path, capsys) -> None:
    project = _project(tmp_path)
    _append(project, trigger="t1")
    code = mw.cmd_decide(_sign_args(project, key=KEY, conclusion="continue", dry_run=True))
    assert code == 0
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "conclusion: continue" in out
    assert not _sign_file(project).exists()
    assert all(
        row.get("kind") == "decide"
        for _lineno, row in decide_archive.iter_rows(_archive(project))
    )


def test_cli_infers_the_key_from_a_key_dir_project(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    assert mw.cmd_decide(_sign_args(key_dir, conclusion="revoke")) == 0
    assert _sign_file(project).is_file()


def test_cli_refuses_to_guess_the_key(tmp_path: pathlib.Path, capsys) -> None:
    project = _project(tmp_path)
    assert mw.cmd_decide(_sign_args(project)) == 2
    assert "cannot infer the key" in capsys.readouterr().err


def test_cli_refuses_inside_an_agent_session(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project = _project(tmp_path)
    monkeypatch.setenv("PI_WORKER_TASK", "task.md")
    assert mw.cmd_decide(_sign_args(project, key=KEY, conclusion="narrow")) == 2
    assert "agent session" in capsys.readouterr().err
    assert not _sign_file(project).exists()


# ---------------------------------------------------------------------------
# (b) the done gate
# ---------------------------------------------------------------------------


def test_gate_ignores_keys_without_decision_scope_marker(tmp_path: pathlib.Path) -> None:
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    passed, failures = advance.check_gate(key_dir, "done")
    assert not any("SIGNOFF" in failure for failure in failures), failures
    assert passed is False  # the pre-existing done rules still fail; no sign-off check ran


def test_gate_blocks_continue_with_n_zero(tmp_path: pathlib.Path) -> None:
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    (key_dir / "decision-scope.md").write_text("scope\n", encoding="utf-8")
    assert mw.cmd_decide(_sign_args(key_dir, conclusion="continue", allow_empty=True)) == 0
    _passed, failures = advance.check_gate(key_dir, "done")
    assert any("N=0" in failure for failure in failures), failures


def test_gate_passes_narrow_with_n_zero(tmp_path: pathlib.Path) -> None:
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    (key_dir / "decision-scope.md").write_text("scope\n", encoding="utf-8")
    assert mw.cmd_decide(_sign_args(key_dir, conclusion="narrow")) == 0
    _passed, failures = advance.check_gate(key_dir, "done")
    assert not any("SIGNOFF" in failure for failure in failures), failures


def test_gate_blocks_after_the_archive_is_appended(tmp_path: pathlib.Path) -> None:
    """The signature covers the counted rows: a later row invalidates the sha."""
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    (key_dir / "decision-scope.md").write_text("scope\n", encoding="utf-8")
    _append(project, trigger="t1")
    assert mw.cmd_decide(_sign_args(key_dir, conclusion="continue")) == 0
    _passed, failures = advance.check_gate(key_dir, "done")
    assert not any("SIGNOFF" in failure for failure in failures), failures

    _append(project, trigger="t2")
    _passed, failures = advance.check_gate(key_dir, "done")
    assert any("rows_sha256 不匹配" in failure for failure in failures), failures


def test_gate_blocks_a_missing_machine_line(tmp_path: pathlib.Path) -> None:
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    (key_dir / "decision-scope.md").write_text("scope\n", encoding="utf-8")
    sign = _sign_file(project)
    sign.parent.mkdir(parents=True, exist_ok=True)
    sign.write_text("conclusion: narrow\n", encoding="utf-8", newline="\n")
    _passed, failures = advance.check_gate(key_dir, "done")
    assert any("counted_rows" in failure for failure in failures), failures
    assert any("rows_sha256" in failure for failure in failures), failures


# ---------------------------------------------------------------------------
# FIX-Q: `--human-confirmed` (the /mw decide sign TUI exemption) + signed_via
# ---------------------------------------------------------------------------


def test_signed_via_line_leaves_the_gate_and_dp_apply_parse_untouched(
    tmp_path: pathlib.Path,
) -> None:
    """The new line is evidence and a machine line: every reader still agrees.

    W9 added ``signed_via`` to the column-0 vocabulary so :func:`parse_signoff`
    reads it back; the done gate and ``mw decide dp apply`` are unaffected
    because neither matches an unknown name.
    """
    advance = _load_advance_phase()
    project = _project(tmp_path)
    key_dir = project / ".agenticdoc" / KEY
    (key_dir / "decision-scope.md").write_text("scope\n", encoding="utf-8")
    facts = decide_signoff.collect(project, KEY)
    text = mw._decide_sign_signed_via(
        decide_signoff.render(facts, "narrow", None, KEY, "-", ts="T"), "tui"
    )
    assert "signed_via: tui" in text.splitlines()
    assert re.search(GATE_RE, text)
    payload, errors = mw._dp_apply_parse(text)
    assert errors == []
    assert payload["conclusion"] == "narrow"
    # W9: `signed_via` is part of the machine-line vocabulary now (render() emits
    # it), so parse_signoff reads it; `dp apply` ignores the unknown name.
    assert decide_signoff.parse_signoff(text)["signed_via"] == "tui"
    sign = _sign_file(project)
    sign.parent.mkdir(parents=True, exist_ok=True)
    sign.write_text(text, encoding="utf-8", newline="\n")
    _passed, failures = advance.check_gate(key_dir, "done")
    assert not any("SIGNOFF" in failure for failure in failures), failures


def test_cli_records_signed_via_cli_by_default(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    _append(project, trigger="t1")
    assert mw.cmd_decide(_sign_args(project, key=KEY, conclusion="continue")) == 0
    text = _sign_file(project).read_text(encoding="utf-8")
    assert "signed_via: cli" in text.splitlines()
    assert "signed_via: tui" not in text.splitlines()


def test_cli_human_confirmed_signs_inside_an_agent_session_and_records_tui(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    _append(project, trigger="t1")
    monkeypatch.setenv("PI_WORKER_TASK", "task.md")
    monkeypatch.setenv("PI_CODING_AGENT", "1")
    code = mw.cmd_decide(
        _sign_args(project, key=KEY, conclusion="continue", human_confirmed=True)
    )
    assert code == 0
    text = _sign_file(project).read_text(encoding="utf-8")
    assert "conclusion: continue" in text.splitlines()
    assert "signed_via: tui" in text.splitlines()
    # The archive `by` vocabulary is unchanged (still `signoff:<conclusion>`).
    rows = [row for _lineno, row in decide_archive.iter_rows(_archive(project))]
    assert rows[-1]["kind"] == "authority-change"
    assert rows[-1]["by"] == "signoff:continue"
    # The exemption is scoped to the write: the probe env survives it.
    assert os.environ.get("PI_WORKER_TASK") == "task.md"


def test_cli_human_confirmed_narrow_with_n_zero_inside_an_agent_session(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.setenv("AI_AGENT", "1")
    assert (
        mw.cmd_decide(
            _sign_args(project, key=KEY, conclusion="narrow", human_confirmed=True)
        )
        == 0
    )
    assert "signed_via: tui" in _sign_file(project).read_text(encoding="utf-8")


def test_cli_without_human_confirmed_still_refuses_and_writes_nothing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys
) -> None:
    project = _project(tmp_path)
    _append(project, trigger="t1")  # the verdict passes; only the session gate refuses
    monkeypatch.setenv("PI_WORKER_TASK", "task.md")
    assert mw.cmd_decide(_sign_args(project, key=KEY, conclusion="continue")) == 2
    err = capsys.readouterr().err
    assert "refusing inside an agent session" in err
    assert not _sign_file(project).exists()
    # Zero authority-change rows: the sign-off never happened.
    rows = [row for _lineno, row in decide_archive.iter_rows(_archive(project))]
    assert [row["kind"] for row in rows] == ["decide"]


def test_write_signoff_human_confirmed_is_the_only_exemption(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _project(tmp_path)
    monkeypatch.setenv("PI_CODING_AGENT", "1")
    path = mw._decide_sign_write(
        project / ".agenticdoc" / KEY, KEY, "conclusion: narrow\n", human_confirmed=True
    )
    assert path.read_text(encoding="utf-8") == "conclusion: narrow\n"
    with pytest.raises(decide_signoff.SignoffError):
        mw._decide_sign_write(
            project / ".agenticdoc" / KEY, KEY, "conclusion: revoke\n", human_confirmed=False
        )


def test_cli_preview_json_carries_every_conclusion_verdict(
    tmp_path: pathlib.Path, capsys
) -> None:
    project = _project(tmp_path)
    assert mw.cmd_decide(_sign_args(project, key=KEY, json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["path"] is None
    assert set(payload["verdicts"]) == set(decide_signoff.CONCLUSIONS)
    assert payload["verdicts"]["continue"]["ok"] is False
    assert any("N=0" in problem for problem in payload["verdicts"]["continue"]["problems"])
    assert payload["verdicts"]["narrow"] == {"ok": True, "problems": []}
    assert payload["verdicts"]["revoke"] == {"ok": True, "problems": []}


def test_cli_preview_json_honours_allow_empty_for_continue(
    tmp_path: pathlib.Path, capsys
) -> None:
    project = _project(tmp_path)
    assert mw.cmd_decide(_sign_args(project, key=KEY, json=True, allow_empty=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdicts"]["continue"] == {"ok": True, "problems": []}
