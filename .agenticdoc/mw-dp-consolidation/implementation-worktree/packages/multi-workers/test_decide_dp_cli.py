"""test_decide_dp_cli.py — T-02: `mw decide dp ...` + the structured `run` request.

Hermetic pytest suite (key mw-decision-substitution) for the CLI family design
§2.5 hangs under `decide_sub`:

* `dp list/show` — read-only views over the authorization table
  `.mw/decide-points.json` (the registry in `decision_points.DP_REGISTRY` is the
  registration authority, so an unknown id is an exit-2 argument error).
* `dp on/off/set` — the human write face (design D-001/AC-010). A P0 dp cannot
  be switched on without `--i-understand-p0` and that refusal must leave the
  table byte-identical (AC-002).
* `dp refresh` — one-way registry → table merge: add missing rows, never touch
  an existing `enabled`/`mode`, keep orphans marked, and write *nothing* when
  there is nothing to add (design D-022/AC-012).
* `dp check` — three-state health face: 0 clean, 1 warning, 2 error.
* `dp apply` — skeleton: format validation of the sign-off header plus the
  agent-session refusal (design D-016); the atomic write-back lands with T-09.
* `mw decide run` — a structured request omits `questions` (the registry is the
  authority) and names the point with `--dp` (design D-027); the legacy request
  that carries `questions` stays byte-identical.

Everything runs under `tmp_path`: no network, no `~/.pi` credentials, and the
decision backend is the `decision.FakeBackend` double.
"""

from __future__ import annotations

import argparse
import hashlib
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
#: Presence of any of these means an agent session (design D-016).
AGENT_ENV_VARS = ("PI_CODING_AGENT", "AI_AGENT", "PI_WORKER_TASK")


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


def _args(project: pathlib.Path, dp_action: str, **kw) -> argparse.Namespace:
    base = {
        "subcommand": "decide",
        "decide_action": "dp",
        "dp_action": dp_action,
        "project": str(project),
        "json": False,
        "pairs": [],
        "rows": 5,
        "i_understand_p0": False,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def _run_args(project: pathlib.Path, **kw) -> argparse.Namespace:
    base = {
        "subcommand": "decide",
        "decide_action": "run",
        "project": str(project),
        "json": False,
        "request_file": None,
        "dp": None,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def _table_path(project: pathlib.Path) -> pathlib.Path:
    return project / ".mw" / "decide-points.json"


def _write_table(project: pathlib.Path, points: object, *, version: int | None = 1) -> pathlib.Path:
    table: dict = {
        "version": version,
        "updated_at": "2026-10-20T00:00:00Z",
        "updated_by": "human",
        "points": points,
    }
    path = _table_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    dpts.clear_points_config_cache()
    return path


def _sha(path: pathlib.Path) -> str | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _signature(path: pathlib.Path) -> tuple[int, int, str | None]:
    """mtime_ns + size + sha256: any write at all breaks the tuple (D-022)."""
    st = path.stat()
    return (int(st.st_mtime_ns), int(st.st_size), _sha(path))


def _archive_path(project: pathlib.Path) -> pathlib.Path:
    return project / dpts.DECISIONS_RELATIVE_PATH


def _write_archive(project: pathlib.Path, *rows: dict) -> pathlib.Path:
    path = _archive_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def _archive_rows(project: pathlib.Path) -> list[dict]:
    path = _archive_path(project)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sign_file(project: pathlib.Path, body: str) -> pathlib.Path:
    path = project / "sign-final.md"
    path.write_text(body, encoding="utf-8", newline="\n")
    return path


def _request_file(project: pathlib.Path, payload: dict) -> pathlib.Path:
    path = project / "request.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")
    return path


def _write_decide_config(project: pathlib.Path, **fields) -> pathlib.Path:
    path = project / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"enabled": True, **fields}, ensure_ascii=False), encoding="utf-8", newline="\n"
    )
    return path


def _inject_backend(monkeypatch: pytest.MonkeyPatch, backend) -> None:
    """Make `cmd_decide run` construct a real client around the fake backend."""
    real_client = decision.DecisionClient

    def factory(cfg, *args, **kwargs):
        return real_client(cfg, backend, *args, **kwargs)

    monkeypatch.setattr(decision, "DecisionClient", factory)


def _ok(answers: dict) -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=True, reason=None, retryable=False, answers=answers, latency_ms=3, detail=""
    )


def _answers_for(dp_id: str) -> dict:
    """Valid answer payload covering every registered question of one dp."""
    out: dict = {}
    for question in dpts.get_decision_point(dp_id).questions:
        if question["type"] == decision.QUESTION_CHOICE:
            value = "c1" if "dynamic_choices" in question else question["choices"][0]
        elif question["type"] == decision.QUESTION_SCORE:
            value = question["min"]
        elif question["type"] == decision.QUESTION_NOUL:
            value = 0.9
        else:
            value = "registered answer text"
        out[str(question["id"])] = {"value": value, "confidence": 0.9}
    return out


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


def test_dp_list_prints_the_registered_points(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    rc = mw.cmd_decide(_args(tmp_path, "list"))
    out = capsys.readouterr().out
    assert rc == 0
    for point in dpts.DP_REGISTRY:
        assert point.id in out
    # Count derived from the registry (not a literal): W9 added dp25, and the
    # registry is the authority for how many points exist.
    registered = len(dpts.DP_REGISTRY)
    assert sum(1 for line in out.splitlines() if " source=" in line) == registered
    assert f"{registered} decision point(s)" in out
    assert "layer=L0" in out  # no table yet: registry defaults


def test_dp_list_reports_p0_on_and_row_source(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    _write_table(
        tmp_path,
        {"dp8-scope-change": {"tier": "P0", "enabled": True, "mode": "auto", "note": "trial"}},
    )
    assert mw.cmd_decide(_args(tmp_path, "list")) == 0
    out = capsys.readouterr().out
    assert "P0-ON" in out
    assert "source=config" in out

    rc = mw.cmd_decide(_args(tmp_path, "list", json=True))
    payload = json.loads(capsys.readouterr().out)
    entries = {entry["id"]: entry for entry in payload["points"]}
    assert rc == 0
    assert len(entries) == len(dpts.DP_REGISTRY)
    assert entries["dp8-scope-change"]["p0_on"] is True
    assert entries["dp8-scope-change"]["source"] == "config"
    assert entries["dp8-scope-change"]["note"] == "trial"
    assert entries["dp1-dispatch-type"]["source"] == "default"
    assert entries["dp1-dispatch-type"]["enabled"] is True
    assert entries["dp11-credential"]["enabled"] is False
    # W11: dp25 is P2, so with no row it resolves to the registry default (on).
    assert entries["dp25-signoff-conclusion"]["tier"] == "P2"
    assert entries["dp25-signoff-conclusion"]["source"] == "default"
    assert entries["dp25-signoff-conclusion"]["enabled"] is True


def test_dp_list_flags_orphaned_rows_in_text_and_json(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    _write_table(
        tmp_path,
        {"dp99-legacy": {"tier": "P2", "enabled": True, "mode": "auto", "note": "old id"}},
    )
    assert mw.cmd_decide(_args(tmp_path, "list")) == 0
    out = capsys.readouterr().out
    assert "dp99-legacy" in out
    assert "ORPHANED" in out

    assert mw.cmd_decide(_args(tmp_path, "list", json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    orphans = [entry for entry in payload["points"] if entry["orphaned"]]
    assert [entry["id"] for entry in orphans] == ["dp99-legacy"]


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_dp_show_prints_registered_detail(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    rc = mw.cmd_decide(_args(tmp_path, "show", dp="dp3-worker-clarify"))
    out = capsys.readouterr().out
    assert rc == 0
    assert "dp3-worker-clarify" in out
    assert dpts.get_decision_point("dp3-worker-clarify").description in out
    assert "answer_kind" in out


def test_dp_show_unknown_id_exit_2(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture) -> None:
    assert mw.cmd_decide(_args(tmp_path, "show", dp="dp99-nope")) == 2
    assert "unknown decision point id" in capsys.readouterr().err


def test_dp_show_includes_the_archive_tail(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    _write_archive(
        tmp_path,
        {"seq": 1, "kind": "decide", "dp": "dp3-worker-clarify", "decision_id": "dp3-worker-clarify:a"},
        {"seq": 2, "kind": "decide", "dp": "dp4-failure-handling", "decision_id": "dp4-failure-handling:b"},
        {"seq": 3, "kind": "settle", "dp": "dp3-worker-clarify", "decision_id": "dp3-worker-clarify:a"},
    )
    assert mw.cmd_decide(_args(tmp_path, "show", dp="dp3-worker-clarify", json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [row["seq"] for row in payload["archive_rows"]] == [1, 3]
    assert payload["archive_error"] is None

    assert mw.cmd_decide(_args(tmp_path, "show", dp="dp3-worker-clarify", rows=1, json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert [row["seq"] for row in payload["archive_rows"]] == [3]


# ---------------------------------------------------------------------------
# on / off: P0 gate + authority-change audit row
# ---------------------------------------------------------------------------


def test_dp_on_p0_without_flag_exits_2_and_leaves_the_table_untouched(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(
        tmp_path, {"dp8-scope-change": {"tier": "P0", "enabled": False, "mode": "auto", "note": ""}}
    )
    before = _signature(path)
    rc = mw.cmd_decide(_args(tmp_path, "on", dp="dp8-scope-change"))
    err = capsys.readouterr().err
    assert rc == 2
    assert "--i-understand-p0" in err
    assert "nothing was written" in err
    assert _signature(path) == before  # same mtime_ns, size and sha256


def test_dp_on_p0_with_flag_writes_and_audits_human_p0_confirm(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(tmp_path, {})
    rc = mw.cmd_decide(_args(tmp_path, "on", dp="dp8-scope-change", i_understand_p0=True))
    assert rc == 0
    table = json.loads(path.read_text(encoding="utf-8"))
    row = table["points"]["dp8-scope-change"]
    assert row["enabled"] is True
    assert row["tier"] == "P0"
    assert table["updated_by"] == "human:p0-confirm"
    rows = _archive_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["kind"] == "authority-change"
    assert rows[0]["dp"] == "dp8-scope-change"
    assert rows[0]["by"] == "human:p0-confirm"
    assert len(rows[0]["config_sha_after"]) == 16
    assert _sha(path)[:16] == rows[0]["config_sha_after"]


def test_dp_on_p2_needs_no_flag_and_is_idempotent(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(tmp_path, {})
    assert mw.cmd_decide(_args(tmp_path, "on", dp="dp4-failure-handling")) == 0
    assert json.loads(path.read_text(encoding="utf-8"))["points"]["dp4-failure-handling"]["enabled"] is True
    assert len(_archive_rows(tmp_path)) == 1
    before = _signature(path)
    assert mw.cmd_decide(_args(tmp_path, "on", dp="dp4-failure-handling")) == 0
    assert "no change" in capsys.readouterr().out
    assert _signature(path) == before
    assert len(_archive_rows(tmp_path)) == 1


def test_dp_off_disables_and_keeps_the_other_columns(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(
        tmp_path,
        {"dp4-failure-handling": {"tier": "P1", "enabled": True, "mode": "suggest", "note": "trial"}},
    )
    assert mw.cmd_decide(_args(tmp_path, "off", dp="dp4-failure-handling")) == 0
    row = json.loads(path.read_text(encoding="utf-8"))["points"]["dp4-failure-handling"]
    assert row == {"tier": "P1", "enabled": False, "mode": "suggest", "note": "trial"}
    rows = _archive_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["by"] == "human"
    assert rows[0]["change"] == "disable dp4-failure-handling"


def test_dp_on_unknown_id_exit_2(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture) -> None:
    assert mw.cmd_decide(_args(tmp_path, "on", dp="dp99-nope", i_understand_p0=True)) == 2
    assert "unknown decision point id" in capsys.readouterr().err
    assert not _table_path(tmp_path).exists()


def test_dp_on_refuses_to_clobber_an_unparsable_table(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _table_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8", newline="\n")
    dpts.clear_points_config_cache()
    before = _signature(path)
    assert mw.cmd_decide(_args(tmp_path, "on", dp="dp4-failure-handling")) == 2
    assert "dp check" in capsys.readouterr().err
    assert _signature(path) == before


# ---------------------------------------------------------------------------
# set: tier|enabled|mode|note only
# ---------------------------------------------------------------------------


def test_dp_set_updates_the_whitelisted_columns(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(tmp_path, {})
    rc = mw.cmd_decide(
        _args(tmp_path, "set", dp="dp4-failure-handling", pairs=["mode=suggest", "note=first phase trial"])
    )
    assert rc == 0
    row = json.loads(path.read_text(encoding="utf-8"))["points"]["dp4-failure-handling"]
    assert row == {"tier": "P1", "enabled": False, "mode": "suggest", "note": "first phase trial"}
    rows = _archive_rows(tmp_path)
    assert len(rows) == 1
    assert rows[0]["by"] == "human"
    assert "mode='suggest'" in rows[0]["change"]


def test_dp_set_refuses_unknown_keys_and_bad_values(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(tmp_path, {})
    before = _signature(path)
    assert mw.cmd_decide(_args(tmp_path, "set", dp="dp4-failure-handling", pairs=["bogus=1"])) == 2
    assert mw.cmd_decide(_args(tmp_path, "set", dp="dp4-failure-handling", pairs=["mode=auto2"])) == 2
    assert mw.cmd_decide(_args(tmp_path, "set", dp="dp4-failure-handling", pairs=["tier=P3"])) == 2
    assert mw.cmd_decide(_args(tmp_path, "set", dp="dp4-failure-handling", pairs=["enabled=maybe"])) == 2
    assert mw.cmd_decide(_args(tmp_path, "set", dp="dp4-failure-handling", pairs=["note"])) == 2
    assert mw.cmd_decide(_args(tmp_path, "set", dp="dp99-nope", pairs=["mode=suggest"])) == 2
    assert mw.cmd_decide(_args(tmp_path, "set", dp="dp4-failure-handling", pairs=[])) == 2
    assert _signature(path) == before


def test_dp_set_enabled_true_on_p0_requires_the_flag(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(tmp_path, {})
    before = _signature(path)
    assert mw.cmd_decide(_args(tmp_path, "set", dp="dp11-credential", pairs=["enabled=true"])) == 2
    assert "--i-understand-p0" in capsys.readouterr().err
    assert _signature(path) == before
    assert mw.cmd_decide(
        _args(tmp_path, "set", dp="dp11-credential", pairs=["enabled=true"], i_understand_p0=True)
    ) == 0
    table = json.loads(path.read_text(encoding="utf-8"))
    assert table["points"]["dp11-credential"]["enabled"] is True
    assert _archive_rows(tmp_path)[0]["by"] == "human:p0-confirm"


# ---------------------------------------------------------------------------
# refresh: one-way merge, no write when unchanged, idempotent
# ---------------------------------------------------------------------------


def test_dp_refresh_adds_missing_rows_and_preserves_existing_ones(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_table(
        tmp_path,
        {
            "dp4-failure-handling": {"tier": "P1", "enabled": True, "mode": "suggest", "note": "trial"},
            "dp99-legacy": {"tier": "P2", "enabled": True, "mode": "auto", "note": "keep me"},
        },
    )
    before = json.loads(path.read_text(encoding="utf-8"))
    rc = mw.cmd_decide(_args(tmp_path, "refresh", json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["written"] is True
    assert len(payload["added"]) == len(dpts.DP_REGISTRY) - 1
    assert payload["kept"] == 1
    assert payload["orphaned"] == ["dp99-legacy"]

    table = json.loads(path.read_text(encoding="utf-8"))
    points = table["points"]
    assert set(points) == {point.id for point in dpts.DP_REGISTRY} | {"dp99-legacy"}
    assert points["dp4-failure-handling"]["enabled"] is True
    assert points["dp4-failure-handling"]["mode"] == "suggest"
    assert points["dp99-legacy"]["note"] == "keep me"
    assert points["dp1-dispatch-type"] == {"tier": "P2", "enabled": True, "mode": "auto", "note": ""}
    assert points["dp8-scope-change"]["enabled"] is False
    assert table["updated_by"] == "refresh"
    # QG MINOR-3: the header stamp tracks the last write, not table creation.
    assert table["updated_at"] != before["updated_at"]

    rows = _archive_rows(tmp_path)
    assert len(rows) == len(payload["added"])
    assert {row["by"] for row in rows} == {"refresh"}
    assert {row["dp"] for row in rows} == set(payload["added"])


def test_dp_refresh_is_idempotent_and_writes_nothing_when_unchanged(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _table_path(tmp_path)
    assert mw.cmd_decide(_args(tmp_path, "refresh")) == 0
    capsys.readouterr()
    first = _signature(path)
    archive_rows = len(_archive_rows(tmp_path))

    assert mw.cmd_decide(_args(tmp_path, "refresh", json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["added"] == []
    assert payload["kept"] == len(dpts.DP_REGISTRY)
    assert payload["written"] is False
    assert _signature(path) == first  # no rewrite at all (D-022)
    assert len(_archive_rows(tmp_path)) == archive_rows


# ---------------------------------------------------------------------------
# check: 0 clean / 1 warning / 2 error
# ---------------------------------------------------------------------------


def test_dp_check_missing_table_is_clean_exit_0(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    rc = mw.cmd_decide(_args(tmp_path, "check", json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "ok"
    assert payload["exists"] is False
    assert payload["layer"] == "L0"


def test_dp_check_refreshed_table_is_clean_exit_0(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    assert mw.cmd_decide(_args(tmp_path, "refresh")) == 0
    capsys.readouterr()
    rc = mw.cmd_decide(_args(tmp_path, "check", json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["status"] == "ok"
    assert payload["counts"] == {"error": 0, "warning": 0}


def test_dp_check_orphan_and_tier_conflict_are_warnings_exit_1(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    _write_table(
        tmp_path,
        {
            "dp99-legacy": {"tier": "P2", "enabled": True, "mode": "auto", "note": ""},
            "dp8-scope-change": {"tier": "P2", "enabled": False, "mode": "auto", "note": ""},
        },
    )
    rc = mw.cmd_decide(_args(tmp_path, "check", json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 1
    assert payload["status"] == "warning"
    assert payload["counts"]["error"] == 0
    codes = {(issue["code"], issue["dp"]) for issue in payload["issues"]}
    assert ("L6", "dp99-legacy") in codes
    assert ("L7", "dp8-scope-change") in codes
    assert payload["orphaned"] == ["dp99-legacy"]


def test_dp_check_bad_row_is_an_error_exit_2(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    _write_table(
        tmp_path,
        {"dp4-failure-handling": {"tier": "P1", "enabled": "yes", "mode": "auto", "note": ""}},
    )
    rc = mw.cmd_decide(_args(tmp_path, "check", json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "error"
    assert payload["counts"]["error"] == 1
    assert payload["issues"][0]["code"] == "L5"
    assert payload["issues"][0]["dp"] == "dp4-failure-handling"


def test_dp_check_unparsable_table_is_an_error_exit_2(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _table_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json", encoding="utf-8", newline="\n")
    dpts.clear_points_config_cache()
    rc = mw.cmd_decide(_args(tmp_path, "check", json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 2
    assert payload["status"] == "error"
    assert payload["issues"][0]["code"] == "L1"


# ---------------------------------------------------------------------------
# apply: skeleton validation + agent-session refusal
# ---------------------------------------------------------------------------


def test_dp_apply_refuses_inside_an_agent_session(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    path = _sign_file(tmp_path, "conclusion: continue\n")
    monkeypatch.setenv("PI_WORKER_TASK", "task.md")
    assert mw.cmd_decide(_args(tmp_path, "apply", sign_file=str(path))) == 2
    assert "agent session" in capsys.readouterr().err
    assert not _table_path(tmp_path).exists()


def test_dp_apply_valid_signoff_writes_the_table_and_audits(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    """Q4 write-back: a validated sign-off is applied, not just echoed.

    The earlier dry-run contract ("nothing was written") is superseded by
    design Q4: `continue`/`narrow`/`revoke` produce `authority-change` rows and
    then replace the table through the shared P-003 protocol.
    """
    path = _sign_file(
        tmp_path,
        "\n".join(
            [
                "# Decision Signoff",
                "",
                "conclusion: continue",
                "promote: dp4-failure-handling, dp9-model-select",
                "demote: dp5-test-triage",
                "p0-open: -",
                "",
                "prose body",
                "",
            ]
        ),
    )
    assert mw.cmd_decide(_args(tmp_path, "apply", sign_file=str(path))) == 0
    out = capsys.readouterr().out
    assert "conclusion: continue" in out

    table_path = _table_path(tmp_path)
    assert table_path.exists()
    table = json.loads(table_path.read_text(encoding="utf-8"))
    assert table["updated_by"] == "signoff:continue"
    points = table["points"]
    assert points["dp4-failure-handling"]["enabled"] is True
    assert points["dp9-model-select"]["enabled"] is True
    assert points["dp5-test-triage"]["enabled"] is False

    rows = _archive_rows(tmp_path)
    assert {row["dp"] for row in rows} == {
        "dp4-failure-handling",
        "dp9-model-select",
        "dp5-test-triage",
    }
    assert {row["kind"] for row in rows} == {"authority-change"}
    assert {row["by"] for row in rows} == {"signoff:continue"}
    assert all(row["config_sha_after"] == _sha(table_path)[:16] for row in rows)
    assert f"wrote {table_path}" in out
    assert f"authority-change: {len(rows)} row(s)" in out


def test_dp_apply_requires_a_valid_conclusion(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    for body in (
        "promote: dp4-failure-handling\n",
        "conclusion: maybe\n",
        "conclusion: continue # ok\n",
        "conclusion : continue\n",
    ):
        path = _sign_file(tmp_path, body)
        assert mw.cmd_decide(_args(tmp_path, "apply", sign_file=str(path))) == 2
    assert not _table_path(tmp_path).exists()


def test_dp_apply_rejects_bad_dp_id_lists(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    bodies = (
        "conclusion: continue\npromote: dp99-nope\n",
        "conclusion: continue\npromote: dp4-failure-handling, dp4-failure-handling\n",
        "conclusion: continue\npromote: dp4-failure-handling\ndemote: dp4-failure-handling\n",
        "conclusion: continue\np0-open: dp4-failure-handling\n",
        "conclusion: continue\npromote: -\ndemote: -\np0-open: dp8-scope-change\nconclusion: revoke\n",
    )
    for body in bodies:
        path = _sign_file(tmp_path, body)
        assert mw.cmd_decide(_args(tmp_path, "apply", sign_file=str(path))) == 2
    assert not _table_path(tmp_path).exists()


def test_dp_apply_missing_sign_file_exit_2(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    assert mw.cmd_decide(_args(tmp_path, "apply", sign_file=str(tmp_path / "nope.md"))) == 2
    assert "cannot read" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# decide run: structured request (no `questions`) resolves the registry set
# ---------------------------------------------------------------------------


def test_run_structured_request_fills_questions_from_the_registry(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_decide_config(tmp_path, enabled=True)
    backend = decision.FakeBackend([_ok(_answers_for("dp3-worker-clarify"))])
    _inject_backend(monkeypatch, backend)
    request = _request_file(
        tmp_path,
        {
            "state": {
                "schema_version": 2,
                "decision_point": "dp3-worker-clarify",
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
        },
    )
    rc = mw.cmd_decide(
        _run_args(tmp_path, request_file=str(request), dp="dp3-worker-clarify")
    )
    response = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert response["available"] is True
    assert backend.calls[0]["questions"] == dpts.questions_map(
        dpts.get_decision_point("dp3-worker-clarify")
    )
    evidence = (tmp_path / ".agenticdoc" / "_autopilot" / "triage-decisions.jsonl").read_text(
        encoding="utf-8"
    )
    assert json.loads(evidence.splitlines()[0])["dp"] == "dp3-worker-clarify"


def test_run_unknown_dp_without_questions_exit_2(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    request = _request_file(tmp_path, {"state": {"schema_version": 2, "decision_point": "dp99-nope"}})
    assert mw.cmd_decide(_run_args(tmp_path, request_file=str(request), dp="dp99-nope")) == 2
    assert "unknown decision point id" in capsys.readouterr().err


def test_run_without_dp_and_without_questions_exit_2(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    request = _request_file(tmp_path, {"state": {"schema_version": 2}})
    assert mw.cmd_decide(_run_args(tmp_path, request_file=str(request))) == 2
    err = capsys.readouterr().err
    assert "--dp" in err
    assert "questions" in err


def test_run_rejects_a_dp_that_disagrees_with_state_dp(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    request = _request_file(tmp_path, {"state": {"schema_version": 2, "decision_point": "dp1-dispatch-type"}})
    rc = mw.cmd_decide(
        _run_args(tmp_path, request_file=str(request), dp="dp3-worker-clarify")
    )
    assert rc == 2
    assert "disagrees" in capsys.readouterr().err


def test_run_legacy_questions_request_is_unchanged(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_decide_config(tmp_path, enabled=True)
    questions = {"triage_type": {"type": "choice", "choices": ["coding", "research", "review"]}}
    backend = decision.FakeBackend(
        [_ok({"triage_type": {"value": "research", "confidence": 0.8}})]
    )
    _inject_backend(monkeypatch, backend)
    request = _request_file(tmp_path, {"state": "card body", "questions": questions})
    rc = mw.cmd_decide(_run_args(tmp_path, request_file=str(request)))
    response = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert backend.calls[0]["questions"] == questions
    assert response["answers"]["triage_type"]["value"] == "research"
    evidence = (tmp_path / ".agenticdoc" / "_autopilot" / "triage-decisions.jsonl").read_text(
        encoding="utf-8"
    )
    assert json.loads(evidence.splitlines()[0])["dp"] == "dp1"
