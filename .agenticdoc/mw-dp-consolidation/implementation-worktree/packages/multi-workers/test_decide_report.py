"""test_decide_report.py — T-09: `mw decide report` (fold → phase review) and
`mw decide dp apply` (validated sign-off → atomic write-back + audit rows).

Hermetic pytest suite (key mw-decision-substitution, AC-008/AC-009) for the
report generator (requirement 1) and the write-back half of `dp apply`
(requirement 4). Contract sources:
`evidence/research/design-association-report-signoff-20261019.md` Q3/Q4 and
spec §7.1/§7.2.

Coverage map:
- report markdown: all six sections, one `suggest:` line, `N<5` →
  "数据不足，不结论"
- report metrics: outcomes/N, acted/escalated ratios, nc_raw/nc_human,
  override rate and the Wilson 95% lower bound
- `--json` payload, `--key` filter, `--write` needs `--key`
- `dp apply`: promote/demote/revoke semantics, per-dp `authority-change` rows,
  `p0-open` set equality, P0 promotion refusal, narrow must not widen, and
  exit 2 with a byte-identical table when validation fails
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decide_archive  # noqa: E402
import decision_points as dpts  # noqa: E402
import mw  # noqa: E402

CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
)
AGENT_ENV_VARS = ("PI_CODING_AGENT", "AI_AGENT", "PI_WORKER_TASK")
KEY = "k-report"
QP = "q-0123abcd"


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch):
    for name in CRED_ENV_VARS + AGENT_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


def _report_args(project: pathlib.Path, **kw) -> argparse.Namespace:
    base = {
        "subcommand": "decide",
        "decide_action": "report",
        "project": str(project),
        "key": None,
        "phase": "verify",
        "write": False,
        "json": False,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def _apply_args(project: pathlib.Path, sign_file: pathlib.Path, **kw) -> argparse.Namespace:
    base = {
        "subcommand": "decide",
        "decide_action": "dp",
        "dp_action": "apply",
        "project": str(project),
        "json": False,
        "pairs": [],
        "rows": 5,
        "i_understand_p0": False,
        "sign_file": str(sign_file),
    }
    base.update(kw)
    return argparse.Namespace(**base)


def _archive_path(project: pathlib.Path) -> pathlib.Path:
    return project / dpts.DECISIONS_RELATIVE_PATH


def _archive_rows(project: pathlib.Path) -> list[dict]:
    path = _archive_path(project)
    if not path.exists():
        return []
    return [row for _lineno, row in decide_archive.iter_rows(path)]


def _record(
    project: pathlib.Path,
    *,
    dp: str = "dp3-worker-clarify",
    trigger: str = "t1",
    key: str = KEY,
    task_key: str | None = "task-1",
    outcome: str = "ok",
    override: bool = False,
    escalated: bool = False,
) -> None:
    """One valid decide row + (optionally) a settle and an override row."""
    path = _archive_path(project)
    decision_id = f"{dp}:{trigger}"
    if escalated:
        decide_archive.append_decide(
            path,
            dp=dp,
            key=key,
            task_key=task_key,
            trigger_id=trigger,
            state={"schema_version": 2, "decision_point": dp},
            questions_version=QP,
            available=False,
            reason="entry-unavailable",
            answer=None,
            authority="human",
            escalated_reason="unavailable",
            acted=False,
        )
    else:
        decide_archive.append_decide(
            path,
            dp=dp,
            key=key,
            task_key=task_key,
            trigger_id=trigger,
            state={"schema_version": 2, "decision_point": dp},
            questions_version=QP,
            available=True,
            answer={"q1": {"value": "yes", "confidence": 0.9}},
            authority="binding",
            acted=True,
            actual_action="steer worker",
        )
    if outcome:
        decide_archive.append_settle(
            path,
            decision_id=decision_id,
            dp=dp,
            key=key,
            task_key=task_key,
            outcome=outcome,
            settled_by="pm-auto",
        )
    if override:
        decide_archive.append_override(
            path,
            decision_id=decision_id,
            dp=dp,
            key=key,
            override_by="human",
            override_reason="wrong call on the dispatch type",
        )


def _record_pending(project: pathlib.Path, *, trigger: str) -> None:
    """A decide row whose settle is the explicit `pending` registration (D2-S2)."""
    path = _archive_path(project)
    dp = "dp1-dispatch-type"
    decide_archive.append_decide(
        path,
        dp=dp,
        key=KEY,
        task_key="task-pending",
        trigger_id=trigger,
        state={"schema_version": 2, "decision_point": dp},
        questions_version=QP,
        available=True,
        answer={"q1": {"value": "yes", "confidence": 0.9}},
        authority="binding",
        acted=True,
        actual_action="dispatch",
    )
    decide_archive.append_settle(
        path,
        decision_id=f"{dp}:{trigger}",
        dp=dp,
        key=KEY,
        task_key="task-pending",
        outcome="pending",
        settled_by="pm-auto",
        note="deferred-to-human",
    )


def _sign_file(project: pathlib.Path, body: str, *, key: str = KEY) -> pathlib.Path:
    path = project / ".agenticdoc" / key / "evidence" / "review" / "sign-final.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


def _table_path(project: pathlib.Path) -> pathlib.Path:
    return project / ".mw" / "decide-points.json"


def _write_table(project: pathlib.Path, points: dict) -> pathlib.Path:
    path = _table_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "updated_at": "2026-10-20T00:00:00Z",
                "updated_by": "human",
                "points": points,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    dpts.clear_points_config_cache()
    return path


def _table_rows(project: pathlib.Path) -> dict:
    return json.loads(_table_path(project).read_text(encoding="utf-8"))["points"]


# ---------------------------------------------------------------------------
# report: markdown shape + N<5 rule
# ---------------------------------------------------------------------------


def test_report_writes_the_six_sections_and_a_suggest_line(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    for index in range(5):
        _record(tmp_path, trigger=f"t{index}", outcome="ok")
    rc = mw.cmd_decide(_report_args(tmp_path, key=KEY, write=True))
    out = capsys.readouterr().out
    assert rc == 0
    reports = list((tmp_path / ".agenticdoc" / KEY / "evidence" / "review").glob("decision-review-verify-*.md"))
    assert len(reports) == 1
    text = reports[0].read_text(encoding="utf-8")
    for heading in ("## 概览", "## 判据表", "## 逐决策", "## 分歧样例", "## 候选调整", "## 无法关联项"):
        assert heading in text, heading
    assert "suggest: " in text
    assert "数据不足，不结论" not in text
    assert f"wrote {reports[0]}" in out


def test_report_below_five_settles_forces_the_insufficient_data_wording(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    _record(tmp_path, trigger="a", outcome="ok")
    _record(tmp_path, trigger="b", outcome="rework")
    assert mw.cmd_decide(_report_args(tmp_path, key=KEY, write=True)) == 0
    report = next((tmp_path / ".agenticdoc" / KEY / "evidence" / "review").glob("decision-review-verify-*.md"))
    text = report.read_text(encoding="utf-8")
    assert "数据不足，不结论" in text
    assert "N=2 < 5" in text
    assert "suggest: none (N=2 < 5, 数据不足，不结论)" in text
    assert "数据不足，不结论" in capsys.readouterr().out


def test_report_skips_inconclusive_and_pending_from_the_denominator(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    for trigger, outcome in (("a", "ok"), ("b", "ok"), ("c", "rework"), ("d", "rollback")):
        _record(tmp_path, trigger=trigger, outcome=outcome)
    _record(tmp_path, trigger="e", outcome="inconclusive")
    _record_pending(tmp_path, trigger="f")
    assert mw.cmd_decide(_report_args(tmp_path, key=KEY, json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    metrics = payload["metrics"]
    # inconclusive + pending stay counted as outcomes but never in N.
    assert metrics["n"] == 4
    assert metrics["outcomes"] == {
        "ok": 2,
        "rework": 1,
        "rollback": 1,
        "inconclusive": 1,
        "pending": 1,
    }
    assert payload["insufficient_data"] is True


def test_report_metrics_cover_nc_acted_escalated_and_the_wilson_bound(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    # dp3: 2 auto-answered + 1 escalated; dp1: 1 auto + 1 human override.
    _record(tmp_path, trigger="n1", dp="dp3-worker-clarify", outcome="ok")
    _record(tmp_path, trigger="n2", dp="dp3-worker-clarify", outcome="ok")
    _record(tmp_path, trigger="n3", dp="dp3-worker-clarify", outcome="rework", escalated=True)
    _record(tmp_path, trigger="d1", dp="dp1-dispatch-type", outcome="ok")
    _record(tmp_path, trigger="d2", dp="dp1-dispatch-type", outcome="rollback", override=True)
    assert mw.cmd_decide(_report_args(tmp_path, key=KEY, json=True)) == 0
    metrics = json.loads(capsys.readouterr().out)["metrics"]
    assert metrics["decided"] == 5
    assert metrics["acted"] == 4
    assert metrics["escalated"] == 1
    assert metrics["nc_raw"] == 3
    assert metrics["nc_human"] == 1
    assert metrics["override"] == 1
    assert metrics["override_rate"] == pytest.approx(0.2)
    assert metrics["n"] == 5
    # 4 of 5 settled decisions were not overridden: the plain rate is 0.8, the
    # lower bound must be strictly below it for this sample size.
    assert metrics["agree_wilson_lb"] is not None
    assert 0.0 < metrics["agree_wilson_lb"] < 0.8


def test_wilson_lower_bound_matches_the_closed_form() -> None:
    assert mw._wilson_lower_bound(0, 0) is None
    assert mw._wilson_lower_bound(0, 10) == 0.0
    # 10/10, z=1.96 -> 0.7225 (the classic small-sample value).
    assert mw._wilson_lower_bound(10, 10) == pytest.approx(0.7225, abs=1e-3)
    # monotone: more hits raises the bound, more n at the same rate raises it.
    assert mw._wilson_lower_bound(5, 10) < mw._wilson_lower_bound(9, 10)
    assert mw._wilson_lower_bound(5, 10) < mw._wilson_lower_bound(50, 100)
    assert mw._wilson_lower_bound(11, 10) == mw._wilson_lower_bound(10, 10)


def test_report_suggests_disabling_a_dp_over_the_override_threshold(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    for index in range(6):
        _record(
            tmp_path,
            dp="dp5-test-triage",
            trigger=f"o{index}",
            outcome="ok",
            override=index < 2,
        )
    assert mw.cmd_decide(_report_args(tmp_path, key=KEY, write=True)) == 0
    report = next((tmp_path / ".agenticdoc" / KEY / "evidence" / "review").glob("decision-review-verify-*.md"))
    text = report.read_text(encoding="utf-8")
    assert "suggest: disable dp5-test-triage, N=6 override=2" in text
    assert "suggest: disable dp5-test-triage, N=6 override=2" in capsys.readouterr().out


def test_report_key_filter_excludes_other_keys(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    _record(tmp_path, trigger="mine", key=KEY, outcome="ok")
    _record(tmp_path, trigger="other", key="other-key", outcome="ok")
    assert mw.cmd_decide(_report_args(tmp_path, key=KEY, json=True)) == 0
    filtered = json.loads(capsys.readouterr().out)["metrics"]
    assert filtered["groups"] == 1 == filtered["n"]
    assert mw.cmd_decide(_report_args(tmp_path, json=True)) == 0
    everything = json.loads(capsys.readouterr().out)["metrics"]
    assert everything["groups"] == 2


def test_report_write_without_key_is_exit_2(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture) -> None:
    assert mw.cmd_decide(_report_args(tmp_path, write=True)) == 2
    assert "--key" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# dp apply: write-back semantics
# ---------------------------------------------------------------------------


def test_dp_apply_continue_writes_promote_demote_and_audits_each_dp(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(
        tmp_path,
        {"dp4-failure-handling": {"tier": "P1", "enabled": False, "mode": "auto", "note": ""}},
    )
    before_sha = path.read_bytes()
    sign = _sign_file(
        tmp_path,
        "\n".join(
            [
                f"# Decision Signoff — {KEY} verify",
                "",
                "conclusion: continue",
                "promote: dp4-failure-handling",
                "demote: dp5-test-triage",
                "p0-open: -",
                "",
                "prose body",
                "",
            ]
        ),
    )
    rc = mw.cmd_decide(_apply_args(tmp_path, sign))
    out = capsys.readouterr().out
    assert rc == 0
    assert before_sha != path.read_bytes()
    rows = _table_rows(tmp_path)
    assert rows["dp4-failure-handling"]["enabled"] is True
    assert rows["dp5-test-triage"]["enabled"] is False
    table = json.loads(path.read_text(encoding="utf-8"))
    assert table["updated_by"] == "signoff:continue"
    archive = _archive_rows(tmp_path)
    assert [row["kind"] for row in archive] == ["authority-change", "authority-change"]
    assert {row["dp"] for row in archive} == {"dp4-failure-handling", "dp5-test-triage"}
    assert {row["by"] for row in archive} == {"signoff:continue"}
    assert {row["conclusion"] for row in archive} == {"continue"}
    assert {row["key"] for row in archive} == {KEY}
    assert "enable dp4-failure-handling" in {row["change"] for row in archive}
    assert "disable dp5-test-triage" in {row["change"] for row in archive}
    # config_sha_after is the digest of the table this apply wrote.
    import hashlib

    assert archive[0]["config_sha_after"] == hashlib.sha256(path.read_bytes()).hexdigest()[:16]
    assert f"wrote {path}" in out


def test_dp_apply_narrow_must_not_promote(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(tmp_path, {})
    before = path.read_bytes()
    sign = _sign_file(
        tmp_path,
        "conclusion: narrow\npromote: dp4-failure-handling\np0-open: -\n",
    )
    assert mw.cmd_decide(_apply_args(tmp_path, sign)) == 2
    assert "must not promote" in capsys.readouterr().err
    assert path.read_bytes() == before
    assert _archive_rows(tmp_path) == []


def test_dp_apply_revoke_disables_every_enabled_dp(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    sign = _sign_file(tmp_path, "conclusion: revoke\np0-open: -\n")
    assert mw.cmd_decide(_apply_args(tmp_path, sign)) == 0
    rows = _table_rows(tmp_path)
    enabled = {dp_id for dp_id, row in rows.items() if row["enabled"]}
    assert enabled == set()
    # One audit row for every dp the revoke closed (the P2 defaults).
    default_on = {point.id for point in dpts.DP_REGISTRY if point.default_enabled}
    archive = _archive_rows(tmp_path)
    assert {row["dp"] for row in archive} == default_on
    assert {row["change"] for row in archive} == {f"disable {dp_id}" for dp_id in default_on}
    assert "revoke" in capsys.readouterr().out


def test_dp_apply_p0_open_must_match_the_current_open_p0_set(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(
        tmp_path,
        {"dp8-scope-change": {"tier": "P0", "enabled": True, "mode": "auto", "note": "trial"}},
    )
    before = path.read_bytes()
    sign = _sign_file(tmp_path, "conclusion: continue\np0-open: -\n")
    assert mw.cmd_decide(_apply_args(tmp_path, sign)) == 2
    err = capsys.readouterr().err
    assert "p0-open" in err
    assert "dp8-scope-change" in err
    assert "nothing was written" in err
    assert path.read_bytes() == before
    assert _archive_rows(tmp_path) == []

    # Listing the open P0 makes the same sign-off valid.
    sign = _sign_file(tmp_path, "conclusion: continue\np0-open: dp8-scope-change\n")
    assert mw.cmd_decide(_apply_args(tmp_path, sign)) == 0


def test_dp_apply_refuses_to_promote_a_p0_dp(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(tmp_path, {})
    before = path.read_bytes()
    sign = _sign_file(
        tmp_path,
        "conclusion: continue\npromote: dp8-scope-change\np0-open: -\n",
    )
    assert mw.cmd_decide(_apply_args(tmp_path, sign)) == 2
    err = capsys.readouterr().err
    assert "cannot open P0" in err
    assert "--i-understand-p0" in err
    assert path.read_bytes() == before
    assert _archive_rows(tmp_path) == []


def test_dp_apply_is_atomic_when_a_dp_id_is_unknown(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(tmp_path, {})
    before = path.read_bytes()
    sign = _sign_file(
        tmp_path,
        "conclusion: continue\npromote: dp4-failure-handling, dp99-nope\np0-open: -\n",
    )
    assert mw.cmd_decide(_apply_args(tmp_path, sign)) == 2
    assert "unknown decision point id" in capsys.readouterr().err
    assert path.read_bytes() == before
    assert _archive_rows(tmp_path) == []


def test_dp_apply_continue_without_a_delta_still_audits_the_kept_authorities(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    _write_table(tmp_path, {})
    sign = _sign_file(tmp_path, "conclusion: continue\np0-open: -\n")
    assert mw.cmd_decide(_apply_args(tmp_path, sign)) == 0
    archive = _archive_rows(tmp_path)
    default_on = {point.id for point in dpts.DP_REGISTRY if point.default_enabled}
    assert {row["dp"] for row in archive} == default_on
    assert all(row["change"].startswith("keep ") for row in archive)
    assert all(row["conclusion"] == "continue" for row in archive)
    # The table is still written (updated_by/updated_at carry the verdict).
    table = json.loads(_table_path(tmp_path).read_text(encoding="utf-8"))
    assert table["updated_by"] == "signoff:continue"


def test_dp_apply_refuses_inside_an_agent_session_and_writes_nothing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    sign = _sign_file(tmp_path, "conclusion: continue\np0-open: -\n")
    monkeypatch.setenv("PI_CODING_AGENT", "true")
    assert mw.cmd_decide(_apply_args(tmp_path, sign)) == 2
    assert "agent session" in capsys.readouterr().err
    assert not _table_path(tmp_path).exists()
    assert _archive_rows(tmp_path) == []
