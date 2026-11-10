"""test_decide_cli.py — T-02: `mw decide` CLI + `.mw/decide.json` + doctor `triage:` row.

Hermetic pytest suite (key mw-jev-provider-integration) for the decision
service's operational face:

* `mw decide <run|ask|probe|show|set>` (design D-001/D-003): request state/questions
  come from a file or stdin (never argv); exit 0 even when the service is
  unavailable, exit 2 only for invalid arguments. `decide ask` (FIX-M) is the
  human face: state + `--noul`/`--choice`/`--score` on argv, no dp authorization,
  a readable answer table (or `--json`) and exit 2 on `available=false`.
* `.mw/decide.json` (design D-007): fail-soft reads, P-003 atomic writes
  (temp + os.replace, utf-8, '\\n'), unknown keys refused.
* doctor `triage:` row (design D-005): silent for an unconfigured project
  (zero-perturbation: the text body is byte-identical with and without the new
  section) and purely informational when present.

Everything runs under `tmp_path`; the transport is a
:class:`decision.FakeBackend` and the credential resolvers are patched, so no
network call or ~/.pi credential is ever touched.
"""

from __future__ import annotations

import argparse
import io
import json
import os
import pathlib
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decide_signoff  # noqa: E402
import decision_backends  # noqa: E402
import mw  # noqa: E402
import mw_common  # noqa: E402

MW_PY = pathlib.Path(__file__).parent / "mw.py"
CHOICE_QUESTIONS = {
    "triage_type": {"type": "choice", "choices": ["coding", "research", "review"]},
}
#: FIX-L removed the TypeSafe/Anthropic transports; `timi` is the only credential
#: route the decision service can use any more.
CRED_ENV_VARS = ("TIMI_API_KEY",)


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    # Never read ~/.pi/agent/auth.json and never let probe_matrix hit the wire.
    # (`resolve_typesafe_api_key` no longer exists after FIX-L.)
    monkeypatch.setattr(decision_backends, "resolve_timi_api_key", lambda *a, **k: None)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _args(action: str, project: pathlib.Path, **kw) -> argparse.Namespace:
    base = {
        "subcommand": "decide",
        "decide_action": action,
        "project": str(project),
        "json": False,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def _config_path(root: pathlib.Path) -> pathlib.Path:
    return root / ".mw" / "decide.json"


def _write_config(root: pathlib.Path, **fields) -> pathlib.Path:
    path = _config_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(fields, ensure_ascii=False), encoding="utf-8", newline="\n")
    return path


def _evidence_path(root: pathlib.Path) -> pathlib.Path:
    return root / ".agenticdoc" / "_autopilot" / "triage-decisions.jsonl"


def _write_evidence(root: pathlib.Path, *records: dict) -> pathlib.Path:
    path = _evidence_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return path


def _request_file(root: pathlib.Path, payload: dict) -> pathlib.Path:
    path = root / "request.json"
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8", newline="\n")
    return path


def _inject_backend(monkeypatch: pytest.MonkeyPatch, backend) -> None:
    """Wire a fake backend through the client's documented factory seam.

    `decision.DEFAULT_BACKEND_FACTORY` is the client's own integration point and
    is read at call time, so this covers both `decide run` (a plain
    `DecisionClient`) and `decide ask` (a `DecisionClient` subclass).
    """
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: backend)


def _ok(answers: dict) -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=True, reason=None, retryable=False, answers=answers, latency_ms=7, detail=""
    )


def _fail(reason: str) -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=False, reason=reason, retryable=False, answers=None, latency_ms=7, detail="programmed failure"
    )


#: 32-hex id the registered operator host returns for a frozen submission.
_PENDING_ID = "0123456789abcdef0123456789abcdef"
_PENDING_SHA = "b" * 64


def _capture_submit(
    monkeypatch: pytest.MonkeyPatch, captured: list, *, reply: dict | None = None
) -> None:
    """Replace only the host IPC: capture the exact frozen bytes it receives."""

    def fake_submit(project_id: str, payload: bytes, *, timeout_ms: int = 5000) -> dict:
        captured.append((project_id, bytes(payload)))
        if reply is not None:
            return dict(reply)
        return {
            "ok": True,
            "id": _PENDING_ID,
            "state": "pending",
            "sha256": _PENDING_SHA,
        }

    monkeypatch.setattr(mw.operator_authority, "submit_ask", fake_submit)


def _forbid_direct_backend(monkeypatch: pytest.MonkeyPatch) -> list:
    """Record (and fail on) any provider built by the ordinary CLI process."""
    calls: list = []

    def factory(cfg):
        calls.append(cfg)
        raise AssertionError("the ordinary CLI must never build a provider backend")

    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", factory)
    return calls


def _frozen_draft(frozen: bytes) -> dict:
    return json.loads(frozen.decode("utf-8"))


def _authorized_send(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, frozen: bytes, answers: dict
) -> tuple[decision.FakeBackend, dict]:
    """The registered host callback replays the same frozen bytes exactly once."""
    fake = decision.FakeBackend([_ok(answers)])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: fake)
    monkeypatch.setattr(mw.operator_host, "authorized_callback", lambda *args, **kwargs: True)
    result = mw.operator_ask_frozen(tmp_path, frozen)
    assert len(fake.calls) == 1
    return fake, result


def _apply_result(
    monkeypatch: pytest.MonkeyPatch, result: dict, *, state: str = "applied"
) -> None:
    """The host's confirmed result, read back only by `ask --result`."""
    monkeypatch.setattr(
        mw.operator_authority,
        "ask_result",
        lambda *args, **kwargs: {
            "ok": True,
            "id": _PENDING_ID,
            "state": state,
            "result": result,
        },
    )


# ---------------------------------------------------------------------------
# run: contract + exit-code semantics (operator host only, no direct send)
# ---------------------------------------------------------------------------


def test_run_available_writes_evidence_and_exits_zero(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """`run` submits pending; the confirmed host replay writes the evidence."""
    _write_config(tmp_path, enabled=True)
    captured: list = []
    _capture_submit(monkeypatch, captured)
    backend_calls = _forbid_direct_backend(monkeypatch)
    request = _request_file(tmp_path, {"state": "card body", "questions": CHOICE_QUESTIONS})
    rc = mw.cmd_decide(_args("run", tmp_path, request_file=str(request), dp="dp1"))
    assert rc == 0
    response = json.loads(capsys.readouterr().out)
    # The ordinary CLI freezes and submits; it never invents an answer.
    assert response["state"] == "pending"
    assert response["id"] == _PENDING_ID
    assert "--result" in response["next"]
    assert "available" not in response and "answers" not in response
    assert len(captured) == 1
    frozen = captured[0][1]
    draft = _frozen_draft(frozen)
    assert draft["purpose"] == "ask"
    assert draft["questions"] == CHOICE_QUESTIONS
    assert draft["state"] == "card body"
    assert mw.operator_ask_validate(tmp_path, frozen) is True
    assert not _evidence_path(tmp_path).exists()
    assert backend_calls == []

    fake, result = _authorized_send(
        tmp_path,
        monkeypatch,
        frozen,
        {"triage_type": {"value": "research", "confidence": 0.8}},
    )
    assert fake.calls[0]["state"] == "card body"
    assert fake.calls[0]["questions"] == CHOICE_QUESTIONS
    assert result["answers"]["triage_type"]["value"] == "research"

    _apply_result(monkeypatch, result)
    assert mw.cmd_decide(_ask_args(tmp_path, result=_PENDING_ID, json=True)) == 0
    answered = json.loads(capsys.readouterr().out)
    assert answered["answers"]["triage_type"]["value"] == "research"
    lines = _evidence_path(tmp_path).read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["dp"] == "dp-human-ask"
    assert record["available"] is True
    assert record["ts"].endswith("+00:00")


def test_run_unavailable_refuses_and_reports_the_transport_failure(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """An unavailable host sends nothing; the failure is observed, not invented."""
    _write_config(tmp_path, enabled=True)
    captured: list = []
    _capture_submit(monkeypatch, captured, reply={"ok": False, "reason": "host-unavailable"})
    backend_calls = _forbid_direct_backend(monkeypatch)
    request = _request_file(tmp_path, {"state": "card body", "questions": CHOICE_QUESTIONS})
    rc = mw.cmd_decide(_args("run", tmp_path, request_file=str(request)))
    first = capsys.readouterr()
    assert rc == 2
    assert first.out.strip() == ""
    assert "host-unavailable" in first.err
    assert "nothing was sent" in first.err
    assert len(captured) == 1  # only the host guard/sender ever gets the draft
    assert backend_calls == []

    frozen = captured[0][1]
    fake = decision.FakeBackend([_fail("upstream-error")])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: fake)
    monkeypatch.setattr(mw.operator_host, "authorized_callback", lambda *args, **kwargs: True)
    with pytest.raises(mw._OperatorAskError) as excinfo:
        mw.operator_ask_frozen(tmp_path, frozen)
    assert "upstream-error" in str(excinfo.value)
    assert len(fake.calls) == 1  # the confirmed replay sends exactly once

    _apply_result(monkeypatch, None, state="failed")
    rc = mw.cmd_decide(_ask_args(tmp_path, result=_PENDING_ID))
    failed = capsys.readouterr()
    assert rc == 2
    assert failed.out.strip() == ""
    assert "failed" in failed.err and "no answer" in failed.err


def test_run_unconfigured_refuses_and_show_reports_disabled(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    captured: list = []
    _capture_submit(monkeypatch, captured)
    backend_calls = _forbid_direct_backend(monkeypatch)
    request = _request_file(tmp_path, {"state": "card body", "questions": CHOICE_QUESTIONS})
    rc = mw.cmd_decide(_args("run", tmp_path, request_file=str(request)))
    refused = capsys.readouterr()
    assert rc == 2
    assert "not configured/enabled" in refused.err
    assert captured == [] and backend_calls == []

    # The original observability checkpoint stays: `show` reports disabled.
    assert mw.cmd_decide(_args("show", tmp_path, json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["enabled"] is False


def test_run_reads_request_from_stdin(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_config(tmp_path, enabled=True)
    captured: list = []
    _capture_submit(monkeypatch, captured)
    backend_calls = _forbid_direct_backend(monkeypatch)
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"state": "card body", "questions": CHOICE_QUESTIONS}))
    )
    rc = mw.cmd_decide(_args("run", tmp_path, request_file=None))
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["state"] == "pending"
    assert payload["id"] == _PENDING_ID
    assert len(captured) == 1
    draft = _frozen_draft(captured[0][1])
    assert draft["state"] == "card body"
    assert draft["questions"] == CHOICE_QUESTIONS
    assert mw.operator_ask_validate(tmp_path, captured[0][1]) is True
    assert backend_calls == []


def test_run_request_missing_questions_exit2(tmp_path: pathlib.Path) -> None:
    request = _request_file(tmp_path, {"state": "card body"})
    assert mw.cmd_decide(_args("run", tmp_path, request_file=str(request))) == 2


def test_run_missing_request_file_exit2(tmp_path: pathlib.Path) -> None:
    assert mw.cmd_decide(_args("run", tmp_path, request_file=str(tmp_path / "nope.json"))) == 2


def test_run_invalid_question_type_exit2(tmp_path: pathlib.Path) -> None:
    _write_config(tmp_path, enabled=True)
    request = _request_file(tmp_path, {"state": "card body", "questions": {"q": {"type": "bogus"}}})
    assert mw.cmd_decide(_args("run", tmp_path, request_file=str(request))) == 2


def test_unknown_action_exit2(tmp_path: pathlib.Path) -> None:
    assert mw.cmd_decide(_args("bogus", tmp_path)) == 2


# ---------------------------------------------------------------------------
# set: P-003 atomic write + unknown-key refusal
# ---------------------------------------------------------------------------


def test_set_writes_config_atomically(tmp_path: pathlib.Path) -> None:
    rc = mw.cmd_decide(
        _args("set", tmp_path, pairs=["enabled=true", "transport=timi-decisions", "timeout_s=5"])
    )
    assert rc == 0
    raw = _config_path(tmp_path).read_bytes()
    assert raw.endswith(b"\n")
    assert b"\r\n" not in raw
    data = json.loads(raw.decode("utf-8"))
    assert data["enabled"] is True
    assert data["transport"] == "timi-decisions"
    assert data["timeout_s"] == 5.0
    assert not list((tmp_path / ".mw").glob("*.tmp")), "temp file left behind"
    assert not list((tmp_path / ".mw").glob("*.lock")), "lock file left behind"


def test_set_merges_points_into_existing_config(tmp_path: pathlib.Path) -> None:
    _write_config(tmp_path, enabled=True)
    rc = mw.cmd_decide(
        _args(
            "set",
            tmp_path,
            pairs=["points.dp1.enabled=true", "points.dp1.alert_on_disagreement=false"],
        )
    )
    assert rc == 0
    data = json.loads(_config_path(tmp_path).read_text(encoding="utf-8"))
    assert data["enabled"] is True
    assert data["points"] == {"dp1": {"enabled": True, "alert_on_disagreement": False}}


def test_set_unknown_key_exit2_and_no_file(tmp_path: pathlib.Path) -> None:
    assert mw.cmd_decide(_args("set", tmp_path, pairs=["bogus=1"])) == 2
    assert not _config_path(tmp_path).exists()


def test_set_unknown_point_key_exit2(tmp_path: pathlib.Path) -> None:
    assert mw.cmd_decide(_args("set", tmp_path, pairs=["points.dp1.nope=true"])) == 2
    assert not _config_path(tmp_path).exists()


def test_set_bad_value_exit2_leaves_file_untouched(tmp_path: pathlib.Path) -> None:
    path = _write_config(tmp_path, enabled=True)
    before = path.read_bytes()
    assert mw.cmd_decide(_args("set", tmp_path, pairs=["timeout_s=abc"])) == 2
    assert path.read_bytes() == before


def test_set_without_pairs_exit2(tmp_path: pathlib.Path) -> None:
    assert mw.cmd_decide(_args("set", tmp_path, pairs=[])) == 2


# ---------------------------------------------------------------------------
# set/show: the W1 token gates (max_total_tokens / max_state_plus_question_tokens)
# ---------------------------------------------------------------------------


def test_set_writes_the_token_gate_keys(tmp_path: pathlib.Path) -> None:
    """The W1 transport knobs are now part of the strict write face."""
    rc = mw.cmd_decide(
        _args(
            "set",
            tmp_path,
            pairs=[
                "enabled=true",
                "max_total_tokens=4096",
                "max_state_plus_question_tokens=2048",
                "max_state_bytes=0",
            ],
        )
    )
    assert rc == 0
    data = json.loads(_config_path(tmp_path).read_text(encoding="utf-8"))
    assert data["max_total_tokens"] == 4096
    assert data["max_state_plus_question_tokens"] == 2048
    assert data["max_state_bytes"] == 0  # 0 disables the byte gate
    assert data["max_total_tokens"] is not True  # a real int, not a bool
    cfg, err = decision.DecisionConfig.from_project(tmp_path)
    assert err is None
    assert cfg.max_total_tokens == 4096
    assert cfg.max_state_plus_question_tokens == 2048


def test_set_rejects_out_of_range_token_gates_without_writing(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    path = _write_config(tmp_path, enabled=True)
    before = path.read_bytes()
    for pair in (
        "max_total_tokens=0",
        "max_total_tokens=abc",
        "max_state_plus_question_tokens=0",
        "max_state_plus_question_tokens=-2",
        "max_state_bytes=-1",
    ):
        assert mw.cmd_decide(_args("set", tmp_path, pairs=[pair])) == 2, pair
        assert path.read_bytes() == before, f"{pair}: the refused value reached the file"
    err = capsys.readouterr().err
    assert "max_total_tokens" in err
    assert "max_state_bytes" in err


def test_show_prints_the_token_gate_keys(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    """Defaults are printed too: a missing key is never silently absent."""
    assert mw.cmd_decide(_args("show", tmp_path)) == 0
    out = capsys.readouterr().out
    assert "max_state_bytes: 0" in out
    assert "max_total_tokens: 65536" in out
    assert "max_state_plus_question_tokens: 32768" in out

    _write_config(
        tmp_path, enabled=True, max_total_tokens=4096, max_state_plus_question_tokens=2048
    )
    assert mw.cmd_decide(_args("show", tmp_path)) == 0
    out = capsys.readouterr().out
    assert "max_total_tokens: 4096" in out
    assert "max_state_plus_question_tokens: 2048" in out

    assert mw.cmd_decide(_args("show", tmp_path, json=True)) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["max_total_tokens"] == 4096
    assert payload["max_state_plus_question_tokens"] == 2048
    assert payload["max_state_bytes"] == 0


# ---------------------------------------------------------------------------
# show
# ---------------------------------------------------------------------------


def test_show_disabled_when_unconfigured(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    rc = mw.cmd_decide(_args("show", tmp_path))
    out = capsys.readouterr().out
    assert rc == 0
    assert "decide: disabled" in out
    assert "last: none" in out


def test_show_json_reports_disabled(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    rc = mw.cmd_decide(_args("show", tmp_path, json=True))
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["exists"] is False
    assert payload["enabled"] is False
    assert payload["last"] is None


def test_show_includes_config_and_last_evidence_ts(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    _write_config(
        tmp_path, enabled=True, transport="timi-decisions", points={"dp1": {"enabled": True}}
    )
    _write_evidence(tmp_path, {"ts": "2026-10-16T00:00:00+00:00", "available": True, "reason": None})
    rc = mw.cmd_decide(_args("show", tmp_path))
    out = capsys.readouterr().out
    assert rc == 0
    assert "decide: enabled" in out
    assert "transport: timi-decisions" in out
    assert "points: dp1.enabled=True" in out
    assert "2026-10-16T00:00:00+00:00" in out


def test_set_redacts_api_key_in_json_echo(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture) -> None:
    """M2 (QG 20261016): `set --json` must not echo a plaintext key it just wrote."""
    rc = mw.cmd_decide(
        _args("set", tmp_path, json=True, pairs=["enabled=true", "api_key=sk-secret-value-123456"])
    )
    out = capsys.readouterr().out
    assert rc == 0
    assert "sk-secret-value-123456" not in out
    assert json.loads(out)["config"]["api_key"] == "<redacted>"
    # The on-disk write is unaffected: the operator asked for that value.
    assert json.loads(_config_path(tmp_path).read_text(encoding="utf-8"))["api_key"] == "sk-secret-value-123456"


def test_show_redacts_api_key(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture) -> None:
    _write_config(tmp_path, enabled=True, api_key="sk-secret-value-123456")
    rc = mw.cmd_decide(_args("show", tmp_path, json=True))
    out = capsys.readouterr().out
    assert rc == 0
    assert "sk-secret-value-123456" not in out
    assert json.loads(out)["extras"]["api_key"] == "<redacted>"


# ---------------------------------------------------------------------------
# probe (hermetic: no key resolved -> no HTTP)
# ---------------------------------------------------------------------------


def test_probe_human_summary_is_short_and_hermetic(
    tmp_path: pathlib.Path, capsys: pytest.CaptureFixture
) -> None:
    _write_config(tmp_path, enabled=True)
    rc = mw.cmd_decide(_args("probe", tmp_path))
    out = capsys.readouterr().out
    assert rc == 0
    lines = out.strip().splitlines()
    assert 1 < len(lines) <= 20, f"probe output must stay <= 20 lines, got {len(lines)}"
    assert lines[0].startswith("probe: ")
    # FIX-L: one transport, one endpoint shape -- no probe matrix any more.
    assert decision_backends.PROBE_TARGETS == (("/v1/decisions", "timi-decisions"),)
    assert out.count("entry-unavailable") == 1
    assert "/v1/decisions" in out


def test_probe_json_matrix(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture) -> None:
    rc = mw.cmd_decide(_args("probe", tmp_path, json=True))
    rows = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert len(rows) == 1  # PROBE_TARGETS collapsed to `timi-decisions` (FIX-L)
    assert {"target", "method", "path", "status", "verdict"} <= set(rows[0])
    assert rows[0]["path"] == "/v1/decisions"
    assert rows[0]["target"].startswith("timi-decisions:")
    assert all(row["verdict"] == "entry-unavailable" for row in rows)


# ---------------------------------------------------------------------------
# doctor: triage row + zero-perturbation
# ---------------------------------------------------------------------------


def test_doctor_unconfigured_is_zero_perturbation(tmp_path: pathlib.Path) -> None:
    report = mw_common.doctor_report(tmp_path)
    assert report["decide"] == {"exists": False}
    text = mw_common.format_doctor_text(report)
    assert "triage:" not in text
    without_section = {key: value for key, value in report.items() if key != "decide"}
    assert mw_common.format_doctor_text(without_section) == text


def test_doctor_enabled_row_reports_last_suggestion(tmp_path: pathlib.Path) -> None:
    _write_config(tmp_path, enabled=True, transport="timi-decisions")
    _write_evidence(tmp_path, {"ts": "2026-10-16T00:00:00+00:00", "available": True, "reason": None})
    report = mw_common.doctor_report(tmp_path)
    assert report["decide"]["last_suggestion"] == 1
    assert report["decide"]["last_unavailable"] is None
    assert (
        "triage: enabled timi-decisions last_suggestion=1 last_unavailable=none"
        in mw_common.format_doctor_text(report)
    )


def test_doctor_row_reports_last_unavailable(tmp_path: pathlib.Path) -> None:
    _write_config(tmp_path, enabled=True)
    _write_evidence(
        tmp_path,
        {"ts": "2026-10-16T00:00:00+00:00", "available": True, "reason": None},
        {"ts": "2026-10-16T00:01:00+00:00", "available": False, "reason": "timeout"},
    )
    report = mw_common.doctor_report(tmp_path)
    assert report["decide"]["last_suggestion"] is None
    assert report["decide"]["last_unavailable"] == "timeout"
    assert (
        "triage: enabled timi-decisions last_suggestion=none last_unavailable=timeout"
        in mw_common.format_doctor_text(report)
    )


def test_doctor_disabled_row(tmp_path: pathlib.Path) -> None:
    _write_config(tmp_path, enabled=False)
    report = mw_common.doctor_report(tmp_path)
    assert report["decide"]["enabled"] is False
    assert "triage: disabled" in mw_common.format_doctor_text(report)


def test_doctor_broken_config_is_informational_only(tmp_path: pathlib.Path) -> None:
    clean = mw_common.doctor_report(tmp_path)
    assert "triage:" not in mw_common.format_doctor_text(clean)
    path = _config_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8", newline="\n")
    broken = mw_common.doctor_report(tmp_path)
    assert "error" in broken["decide"]
    assert broken["summary"]["issues"] == clean["summary"]["issues"]
    assert broken["summary"]["healthy"] == clean["summary"]["healthy"]
    assert "triage: ERROR" in mw_common.format_doctor_text(broken)


# ---------------------------------------------------------------------------
# ask: the human face (FIX-M) — question assembly + output, fake backend only
# ---------------------------------------------------------------------------


def _ask_args(project: pathlib.Path, **kw) -> argparse.Namespace:
    base = {
        "state": None,
        "state_file": None,
        "noul": [],
        "noul_criteria": [],
        "choice": [],
        "score": [],
        "model": None,
        "result": None,
    }
    base.update(kw)
    return _args("ask", project, **base)


def _wire_questions(questions: dict) -> dict:
    """The `questions` map the timi backend actually puts in the request body."""
    return decision_backends.TimiDecisionsBackend().build_questions(questions)


def test_ask_noul_and_choice_questions_match_the_contract(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_config(tmp_path, enabled=True)
    captured: list = []
    _capture_submit(monkeypatch, captured)
    backend_calls = _forbid_direct_backend(monkeypatch)
    rc = mw.cmd_decide(
        _ask_args(
            tmp_path,
            state="提现失败3天",
            noul=["urgent=是否紧急"],
            choice=["dept=billing:支付,technical:技术"],
        )
    )
    assert rc == 0, capsys.readouterr().err
    pending = capsys.readouterr().out
    assert "operator confirmation pending" in pending
    assert _PENDING_ID in pending
    assert len(captured) == 1
    draft = _frozen_draft(captured[0][1])
    assert draft["state"] == "提现失败3天"
    # `noul` without --noul-criteria must not carry the optional key at all.
    assert draft["questions"]["urgent"] == {"type": "noul", "instructions": "是否紧急"}
    assert draft["questions"]["dept"]["criteria"] == {"billing": "支付", "technical": "技术"}
    assert list(draft["questions"]["dept"]["criteria"]) == ["billing", "technical"]
    wire = _wire_questions(draft["questions"])
    assert set(wire["urgent"]) == {"type", "instructions"}
    assert wire["urgent"] == {"type": "noul", "instructions": "是否紧急"}
    assert set(wire["dept"]) == {"type", "instructions", "criteria"}
    assert wire["dept"]["type"] == "choice"
    assert wire["dept"]["instructions"]
    assert wire["dept"]["criteria"] == {"billing": "支付", "technical": "技术"}
    assert mw.operator_ask_validate(tmp_path, captured[0][1]) is True
    assert backend_calls == []

    # Only the confirmed host replay reaches the original backend, once.
    fake, result = _authorized_send(
        tmp_path,
        monkeypatch,
        captured[0][1],
        {
            "urgent": {"value": 0.87, "confidence": None},
            "dept": {
                "value": "billing",
                "confidence": 0.98,
                "probabilities": {"billing": 0.99, "technical": 0.01},
            },
        },
    )
    assert fake.calls[0]["state"] == "提现失败3天"
    # The evidence row is the legacy client's, tagged as the human face.
    record = json.loads(_evidence_path(tmp_path).read_text(encoding="utf-8").splitlines()[0])
    assert record["dp"] == "dp-human-ask"
    assert record["available"] is True

    _apply_result(monkeypatch, result)
    assert mw.cmd_decide(_ask_args(tmp_path, result=_PENDING_ID, json=True)) == 0
    answered = json.loads(capsys.readouterr().out)
    assert answered["answers"]["dept"]["value"] == "billing"
    assert mw.cmd_decide(_ask_args(tmp_path, result=_PENDING_ID)) == 0
    human = capsys.readouterr().out
    assert "[noul]" in human and "[choice]" in human


def test_ask_choice_without_label_yields_null(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_config(tmp_path, enabled=True)
    captured: list = []
    _capture_submit(monkeypatch, captured)
    backend_calls = _forbid_direct_backend(monkeypatch)
    rc = mw.cmd_decide(_ask_args(tmp_path, state="s", choice=["dept=billing"]))
    assert rc == 0, capsys.readouterr().err
    assert len(captured) == 1
    draft = _frozen_draft(captured[0][1])
    assert draft["questions"]["dept"]["criteria"] == {"billing": None}
    assert _wire_questions(draft["questions"])["dept"]["criteria"] == {"billing": None}
    assert backend_calls == []


def test_ask_score_levels_are_ordered_criteria(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_config(tmp_path, enabled=True)
    captured: list = []
    _capture_submit(monkeypatch, captured)
    backend_calls = _forbid_direct_backend(monkeypatch)
    rc = mw.cmd_decide(_ask_args(tmp_path, state="s", score=["effort=小,中,大"]))
    assert rc == 0, capsys.readouterr().err
    assert len(captured) == 1
    draft = _frozen_draft(captured[0][1])
    spec = draft["questions"]["effort"]
    assert spec["criteria"] == ["小", "中", "大"]
    assert (spec["min"], spec["max"]) == (0, 2)
    wire = _wire_questions(draft["questions"])["effort"]
    assert set(wire) == {"type", "instructions", "criteria"}
    assert wire["criteria"] == ["小", "中", "大"]
    assert backend_calls == []


@pytest.mark.parametrize("levels", ["小", ",".join("abcdefghijk")])
def test_ask_score_level_count_exit2_and_no_backend_call(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    levels: str,
) -> None:
    _write_config(tmp_path, enabled=True)
    fake = decision.FakeBackend([])
    _inject_backend(monkeypatch, fake)
    rc = mw.cmd_decide(_ask_args(tmp_path, state="s", score=[f"effort={levels}"]))
    assert rc == 2
    assert "2..10" in capsys.readouterr().err
    assert fake.calls == []


def test_ask_without_any_question_exit2_with_usage(tmp_path: pathlib.Path, capsys: pytest.CaptureFixture) -> None:
    rc = mw.cmd_decide(_ask_args(tmp_path, state="some state"))
    err = capsys.readouterr().err
    assert rc == 2
    for flag in ("--noul", "--choice", "--score"):
        assert flag in err


def test_ask_unavailable_prints_reason_and_no_answer(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_config(tmp_path, enabled=True)
    captured: list = []
    _capture_submit(monkeypatch, captured)
    backend_calls = _forbid_direct_backend(monkeypatch)
    rc = mw.cmd_decide(_ask_args(tmp_path, state="s", noul=["urgent=是否紧急"]))
    assert rc == 0, capsys.readouterr().err
    assert len(captured) == 1 and backend_calls == []
    capsys.readouterr()  # consume the pending submission notice

    # The formal guarded replay passes the transport failure through, once.
    frozen = captured[0][1]
    fake = decision.FakeBackend([_fail("upstream-error")])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: fake)
    monkeypatch.setattr(mw.operator_host, "authorized_callback", lambda *args, **kwargs: True)
    with pytest.raises(mw._OperatorAskError) as excinfo:
        mw.operator_ask_frozen(tmp_path, frozen)
    assert "upstream-error" in str(excinfo.value)
    assert len(fake.calls) == 1

    # The human-facing client keeps the backend detail for that transport seam.
    cfg = mw._decide_config_snapshot(tmp_path)
    assert cfg is not None
    client = mw._AskDecisionClient(
        cfg, project_root=tmp_path, credential_snapshot=decision.credential_snapshot(cfg)
    )
    monkeypatch.setattr(
        decision,
        "DEFAULT_BACKEND_FACTORY",
        lambda _cfg: decision.FakeBackend([_fail("upstream-error")]),
    )
    response = client.decide(
        "s", {"urgent": {"type": "noul", "instructions": "是否紧急"}}, dp=mw._ASK_DP
    )
    assert response["available"] is False
    assert response["reason"] == "upstream-error"
    assert client.ask_detail == "programmed failure"  # the backend detail is passed through

    _apply_result(monkeypatch, None, state="failed")
    failed = mw.cmd_decide(_ask_args(tmp_path, result=_PENDING_ID))
    captured_io = capsys.readouterr()
    assert failed == 2
    assert "failed" in captured_io.err and "no answer" in captured_io.err
    assert captured_io.out.strip() == ""


def test_ask_without_a_host_never_sends_and_never_falls_back(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_config(tmp_path, enabled=True)
    captured: list = []
    _capture_submit(monkeypatch, captured, reply={"ok": False, "reason": "host-unavailable"})
    backend_calls = _forbid_direct_backend(monkeypatch)
    rc = mw.cmd_decide(_ask_args(tmp_path, state="s", noul=["urgent=是否紧急"]))
    io = capsys.readouterr()
    assert rc == 2
    assert io.out.strip() == ""
    assert "host-unavailable" in io.err
    assert "no direct fallback" in io.err
    assert len(captured) == 1  # the draft only reaches the host guard/sender
    assert backend_calls == []


@pytest.mark.parametrize("state", ["failed", "expired", "reserved", "unknown"])
def test_ask_result_cancelled_or_replaced_never_sends(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    state: str,
) -> None:
    """A cancelled/expired/replaced submission is an observation, not an answer."""
    _write_config(tmp_path, enabled=True)
    backend_calls = _forbid_direct_backend(monkeypatch)
    submitted: list = []
    _capture_submit(monkeypatch, submitted)
    _apply_result(monkeypatch, None, state=state)
    rc = mw.cmd_decide(_ask_args(tmp_path, result=_PENDING_ID))
    io = capsys.readouterr()
    assert rc == 2
    assert io.out.strip() == ""
    assert state in io.err and "no answer" in io.err
    assert submitted == []  # reading a result never submits a new request
    assert backend_calls == []


def test_ask_json_is_machine_readable(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_config(tmp_path, enabled=True)
    captured: list = []
    _capture_submit(monkeypatch, captured)
    backend_calls = _forbid_direct_backend(monkeypatch)
    rc = mw.cmd_decide(
        _ask_args(tmp_path, json=True, state="s", choice=["dept=billing:支付,technical:技术"])
    )
    pending = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert pending["state"] == "pending"
    assert pending["id"] == _PENDING_ID
    assert "answers" not in pending  # no invented `available` answer
    assert len(captured) == 1 and backend_calls == []

    _, result = _authorized_send(
        tmp_path,
        monkeypatch,
        captured[0][1],
        {
            "dept": {
                "value": "billing",
                "confidence": 0.98,
                "probabilities": {"billing": 0.99, "technical": 0.01},
            }
        },
    )
    _apply_result(monkeypatch, result)
    rc = mw.cmd_decide(_ask_args(tmp_path, result=_PENDING_ID, json=True))
    out = capsys.readouterr().out
    assert rc == 0
    payload = json.loads(out)
    assert payload["answers"]["dept"]["value"] == "billing"
    assert payload["answers"]["dept"]["probabilities"] == {"billing": 0.99, "technical": 0.01}
    assert payload["model"] == "fake-model"
    assert "usage" in payload
    assert isinstance(payload["latency_ms"], int)
    assert "[choice]" not in out


def test_ask_human_rows_show_type_confidence_probs_and_legend(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_config(tmp_path, enabled=True)
    captured: list = []
    _capture_submit(monkeypatch, captured)
    backend_calls = _forbid_direct_backend(monkeypatch)
    rc = mw.cmd_decide(
        _ask_args(
            tmp_path,
            state="提现失败3天",
            noul=["urgent=是否紧急"],
            choice=["dept=billing:支付,technical:技术"],
            score=["effort=小,中,大"],
        )
    )
    assert rc == 0, capsys.readouterr().err
    assert len(captured) == 1 and backend_calls == []
    capsys.readouterr()  # consume the pending submission notice

    _, result = _authorized_send(
        tmp_path,
        monkeypatch,
        captured[0][1],
        {
            "dept": {
                "value": "billing",
                "confidence": 0.98,
                "probabilities": {"billing": 0.99, "technical": 0.01},
            },
            "urgent": {"value": 0.87, "confidence": None},
            "effort": {
                "value": 1.05,
                "confidence": 0.92,
                "legend": {"0": "小", "1": "中", "2": "大"},
            },
        },
    )
    _apply_result(monkeypatch, result)
    rc = mw.cmd_decide(_ask_args(tmp_path, result=_PENDING_ID))
    out = capsys.readouterr().out
    assert rc == 0
    lines = out.splitlines()
    assert lines[0].endswith("ms")  # model · N questions · latency header
    choice_row = next(line for line in lines if "[choice]" in line)
    assert "confidence 0.98" in choice_row
    assert "probs: billing 0.99, technical 0.01" in choice_row
    noul_row = next(line for line in lines if "[noul]" in line)
    assert "0.87" in noul_row
    assert 'probability of "yes"' in noul_row
    score_row = next(line for line in lines if "[score]" in line)
    assert "confidence 0.92" in score_row
    assert "legend: 0=小, 1=中, 2=大" in score_row
    # Keys are left-aligned so the type column starts at one column.
    assert len({line.index("[") for line in (choice_row, noul_row, score_row)}) == 1


def test_ask_state_from_at_file_and_conflicting_state_flags(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_config(tmp_path, enabled=True)
    state_file = tmp_path / "state.txt"
    state_file.write_text("工单正文", encoding="utf-8", newline="\n")
    captured: list = []
    _capture_submit(monkeypatch, captured)
    backend_calls = _forbid_direct_backend(monkeypatch)
    rc = mw.cmd_decide(_ask_args(tmp_path, state=f"@{state_file}", choice=["dept=billing"]))
    assert rc == 0, capsys.readouterr().err
    assert len(captured) == 1
    assert _frozen_draft(captured[0][1])["state"] == "工单正文"
    rc = mw.cmd_decide(
        _ask_args(tmp_path, state="s", state_file=str(state_file), choice=["dept=billing"])
    )
    assert rc == 2
    assert "mutually exclusive" in capsys.readouterr().err
    rc = mw.cmd_decide(_ask_args(tmp_path, choice=["dept=billing"]))
    assert rc == 2
    assert "--state" in capsys.readouterr().err
    assert len(captured) == 1  # local argument refusals never reach the host
    assert backend_calls == []


def test_ask_duplicate_choice_key_exit2(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_config(tmp_path, enabled=True)
    fake = decision.FakeBackend([])
    _inject_backend(monkeypatch, fake)
    rc = mw.cmd_decide(
        _ask_args(tmp_path, state="s", choice=["dept=billing:支付,billing:技术"])
    )
    assert rc == 2
    assert "duplicate key" in capsys.readouterr().err
    assert fake.calls == []


def test_ask_noul_criteria_and_model_passthrough(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    _write_config(tmp_path, enabled=True)
    captured: list = []
    _capture_submit(monkeypatch, captured)
    backend_calls = _forbid_direct_backend(monkeypatch)
    rc = mw.cmd_decide(
        _ask_args(
            tmp_path,
            state="s",
            noul=["urgent=是否紧急"],
            noul_criteria=["urgent=true:明确有时效性;false:未表达紧急性"],
            model="jev-latest-canary",
        )
    )
    assert rc == 0, capsys.readouterr().err
    assert len(captured) == 1
    draft = _frozen_draft(captured[0][1])
    assert draft["questions"]["urgent"]["criteria"] == {
        "true": "明确有时效性",
        "false": "未表达紧急性",
    }
    assert _wire_questions(draft["questions"])["urgent"]["criteria"] == {
        "true": "明确有时效性",
        "false": "未表达紧急性",
    }
    # --model only overrides the config value; the server stays the authority on
    # whether the name exists (unknown names are sent as-is).
    assert draft["model"] == "jev-latest-canary"
    assert backend_calls == []

    fake, _ = _authorized_send(
        tmp_path, monkeypatch, captured[0][1], {"urgent": {"value": 0.87, "confidence": None}}
    )
    assert fake.calls[0]["cfg"].model == "jev-latest-canary"


# ---------------------------------------------------------------------------
# CLI smoke (argparse registration + dispatch + machine exit)
# ---------------------------------------------------------------------------


def _run_cli(
    *argv: str, input_text: str | None = None, home: pathlib.Path | None = None
) -> subprocess.CompletedProcess:
    """Run `mw.py <argv>` in a child process with a credential-free env.

    `home` (when given) redirects HOME/USERPROFILE so the child can never read
    the developer's real ~/.pi/agent/auth.json: a configured project then
    degrades to `entry-unavailable` without touching the network.
    """
    env = {name: value for name, value in os.environ.items() if name not in CRED_ENV_VARS}
    if home is not None:
        env["HOME"] = str(home)
        env["USERPROFILE"] = str(home)
    return subprocess.run(
        [sys.executable, "-X", "utf8", str(MW_PY), *argv],
        input=input_text,
        capture_output=True,
        encoding="utf-8",
        timeout=300,
        env=env,
    )


def test_cli_decide_show_smoke_unconfigured(tmp_path: pathlib.Path) -> None:
    proc = _run_cli("decide", "show", "--project", str(tmp_path))
    assert proc.returncode == 0, proc.stderr
    assert "decide: disabled" in proc.stdout


def test_cli_decide_set_then_run_stdin_smoke(tmp_path: pathlib.Path) -> None:
    proc = _run_cli("decide", "set", "--project", str(tmp_path), "enabled=true")
    assert proc.returncode == 0, proc.stderr
    assert json.loads(_config_path(tmp_path).read_text(encoding="utf-8"))["enabled"] is True
    proc = _run_cli(
        "decide",
        "run",
        "--project",
        str(tmp_path),
        input_text=json.dumps({"state": "card body", "questions": CHOICE_QUESTIONS}),
        home=tmp_path,
    )
    # A bare child process has no registered host: it refuses, sends nothing and
    # never fabricates an answer.
    assert proc.returncode == 2, proc.stderr
    assert "registered operator host is not available" in proc.stderr
    assert "nothing was sent" in proc.stderr
    assert proc.stdout.strip() == ""


def test_cli_doctor_json_has_decide_section(tmp_path: pathlib.Path) -> None:
    _write_config(tmp_path, enabled=True)
    _write_evidence(tmp_path, {"ts": "2026-10-16T00:00:00+00:00", "available": True, "reason": None})
    proc = _run_cli("doctor", "--project", str(tmp_path), "--json")
    assert proc.returncode in (0, 1), proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["decide"]["exists"] is True
    assert payload["decide"]["enabled"] is True
    assert payload["decide"]["last_suggestion"] == 1


# ---------------------------------------------------------------------------
# 决策本（W7）：`--book` 与 `book new/check` 的参数解析
# ---------------------------------------------------------------------------


def test_parse_book_new_prints_by_default() -> None:
    args = mw._parse_args(["decide", "book", "new", "dp3-worker-clarify"])
    assert args.decide_action == "book"
    assert args.book_action == "new"
    assert args.dp == "dp3-worker-clarify"
    # 默认只打印到 stdout：没有 --out 就没有写出目标。
    assert args.out is None
    assert args.project == "."
    assert args.json is False


def test_parse_run_book_flag(tmp_path: pathlib.Path) -> None:
    args = mw._parse_args(
        ["decide", "run", "--project", str(tmp_path), "--book", "dp3.json"]
    )
    assert args.book == "dp3.json"
    assert args.request_file is None
    # 没有 --book 时该属性仍然存在且为 None（先验后发是可选面）。
    assert mw._parse_args(["decide", "run", "--project", str(tmp_path)]).book is None


def test_parse_ask_book_flag_and_book_check_json(tmp_path: pathlib.Path) -> None:
    ask = mw._parse_args(
        ["decide", "ask", "--book", "dp6.json", "--noul", "urgent=是否紧急"]
    )
    assert ask.book == "dp6.json"
    assert ask.state is None
    check = mw._parse_args(
        ["decide", "book", "check", "dp6.json", "--json", "--project", str(tmp_path)]
    )
    assert check.book_action == "check"
    assert check.file == "dp6.json"
    assert check.json is True


# ---------------------------------------------------------------------------
# 签收模式（W9 / spec §15 AC-023）：`mw decide sign --auto|--disable`
# ---------------------------------------------------------------------------


def test_parse_sign_auto_and_disable_flags(tmp_path: pathlib.Path) -> None:
    plain = mw._parse_args(["decide", "sign", "--project", str(tmp_path)])
    assert plain.auto is False and plain.disable is False
    # AC-006: the caller-supplied conclusion and the human-confirmation flag are
    # gone from argv reachable surface, not merely ignored.
    assert not hasattr(plain, "conclusion")
    assert not hasattr(plain, "human_confirmed")
    auto = mw._parse_args(["decide", "sign", "--project", str(tmp_path), "--auto"])
    assert auto.auto is True and auto.disable is False
    disable = mw._parse_args(
        ["decide", "sign", "--project", str(tmp_path), "--disable"]
    )
    assert disable.disable is True and disable.auto is False


def test_sign_rejects_the_removed_conclusion_and_human_confirmed_flags(
    tmp_path: pathlib.Path,
) -> None:
    for flag in ("--conclusion", "--human-confirmed"):
        with pytest.raises(SystemExit) as excinfo:
            mw._parse_args(
                ["decide", "sign", "--project", str(tmp_path), flag, "continue"]
            )
        assert excinfo.value.code == 2, flag


def test_cli_sign_auto_persists_the_mode(tmp_path: pathlib.Path) -> None:
    _write_config(tmp_path, enabled=True, signoff="disable")
    proc = _run_cli(
        "decide", "sign", "--project", str(tmp_path), "--key", "k-cli-auto", "--auto"
    )
    assert proc.returncode == 0, proc.stderr
    assert "signoff: auto" in proc.stdout
    stored = json.loads(_config_path(tmp_path).read_text(encoding="utf-8"))
    assert stored["signoff"] == "auto"
    assert stored["enabled"] is True


def test_cli_sign_disable_persists_the_mode_and_show_echoes_it(
    tmp_path: pathlib.Path,
) -> None:
    proc = _run_cli(
        "decide", "sign", "--project", str(tmp_path), "--key", "k-cli-off", "--disable"
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(_config_path(tmp_path).read_text(encoding="utf-8"))["signoff"] == "disable"
    show = _run_cli("decide", "show", "--project", str(tmp_path), "--json")
    assert show.returncode == 0, show.stderr
    payload = json.loads(show.stdout)
    assert payload["signoff"] == "disable"
    assert payload["signoff_error"] is None


def test_cli_sign_dry_run_does_not_persist_the_mode(tmp_path: pathlib.Path) -> None:
    _write_config(tmp_path, enabled=True)
    before = _config_path(tmp_path).read_text(encoding="utf-8")
    proc = _run_cli(
        "decide",
        "sign",
        "--project",
        str(tmp_path),
        "--key",
        "k-cli-dry",
        "--disable",
        "--dry-run",
    )
    assert proc.returncode == 0, proc.stderr
    assert "would write" in proc.stdout
    assert _config_path(tmp_path).read_text(encoding="utf-8") == before


def test_cli_signed_via_coverage() -> None:
    """AC-006: the decision model is the only authority, so the write face is one value."""
    assert decide_signoff.SIGNED_VIA_VALUES == ("auto-decide",)
