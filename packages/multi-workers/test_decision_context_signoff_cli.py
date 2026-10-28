"""test_decision_context_signoff_cli.py - T05 CLI envelope, lifecycle and dp25 signoff.

Behaviours locked here (card dc-t05-signoff-cli):

* ``mw decide run <dp> --stdin`` reads the local ``{material, meta}`` envelope,
  writes the ``record-start`` fact *before* the transport call, associates the
  returned ``decision_id`` with the same ``logical_id``, never sends ``meta`` to
  the model and never sends a second model call for an already processed
  ``logical_id``.
* ``mw decide lifecycle --stdin`` is the single feedback CLI: it validates the
  closed field set, calls the T02 ``record_*`` writer and returns
  ``status/recorded/error_class/error_recorded``; it never executes or
  completes anything.
* ``mw decide sign <key> --stdin`` consumes the PM's four dp25 parts, snapshots
  them, writes the valid sign-off file atomically on ``finalize`` (no second
  approval), retries only the write for the same snapshot, keeps the file bytes
  and mtime for a repeated receipt, refuses a stale conclusion when the material
  or evidence changed, and hands ``continue``/``user-confirm`` back to the PM
  with zero sign-off writes.
* ``decision_signoff_result`` exposes a credential-free validator for T06:
  exact ``logical_id`` + snapshot, and a parent-chain/symlink check that a hash
  or an id can never exempt.
* The real argv/stdin path is exercised through a loopback HTTP faux backend
  under a synthetic HOME; the production tree stays byte-identical.

No real credential, model, browser, service, build or install is touched.
"""

from __future__ import annotations

import argparse
import hashlib
import http.server
import io
import json
import os
import pathlib
import subprocess
import sys
import threading

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decide_signoff  # noqa: E402
import decide_archive  # noqa: E402
import decision  # noqa: E402
import decision_lifecycle as lifecycle  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_signoff_result as signoff_result  # noqa: E402
import mw  # noqa: E402

KEY = "mw-decision-context"
DP25 = "dp25-signoff-conclusion"
SECRET = "synthetic-t05-known-secret"
MW_PY = pathlib.Path(__file__).parent / "mw.py"
PROTECTED_SOURCES = (
    "mw.py",
    "decide_signoff.py",
    "decision_signoff_result.py",
    "decision_lifecycle.py",
    "decision_wire.py",
    "decision_points.py",
)


# ---------------------------------------------------------------------------
# Isolation: synthetic HOME/auth, no ambient credential, no real endpoint
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
    home = tmp_path / "home"
    auth = home / ".pi" / "agent" / "auth.json"
    auth.parent.mkdir(parents=True)
    auth.write_text(json.dumps({"timi": {"key": SECRET}}), encoding="utf-8")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("TIMI_BASE_URL", "http://127.0.0.1:9")
    for name in list(os.environ):
        upper = name.upper()
        if upper == "TIMI_API_KEY" or upper.endswith(
            ("_API_KEY", "_TOKEN", "_KEY", "_SECRET", "_PASSWORD")
        ):
            monkeypatch.delenv(name, raising=False)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _project(tmp_path: pathlib.Path) -> pathlib.Path:
    project = tmp_path / "proj"
    (project / ".agenticdoc" / KEY / "evidence" / "review").mkdir(parents=True)
    (project / ".mw").mkdir(parents=True)
    (project / ".mw" / "decide.json").write_text(
        json.dumps({"enabled": True}), encoding="utf-8"
    )
    return project


def _key_dir(project: pathlib.Path) -> pathlib.Path:
    return project / ".agenticdoc" / KEY


def _material(**overrides: object) -> dict:
    material = {
        "delivery_goal": "ship the approved CLI contract with evidence",
        "actual_completion": "run/lifecycle/sign CLI and validator implemented",
        "verification_evidence": {
            "verified": ["pytest test_decision_context_signoff_cli.py"],
            "unverified": ["real Jev end-to-end"],
        },
        "unfinished_impact": ["phase gate stays a separate framework gate"],
    }
    material.update(overrides)
    return material


def _envelope(
    *,
    logical_id: str = "logical-t05-001",
    role: object = "pm",
    task_key: object = None,
    material: dict | None = None,
    retry_of: object = None,
    extra_meta: dict | None = None,
) -> dict:
    meta = {
        "record_version": 2,
        "logical_id": logical_id,
        "key": KEY,
        "task_key": task_key,
        "initiator_role": role,
        "retry_of": retry_of,
    }
    if extra_meta:
        meta.update(extra_meta)
    return {"material": material if material is not None else _material(), "meta": meta}


def _run_args(
    project: pathlib.Path,
    *,
    dp_id: str | None = DP25,
    dp: str | None = None,
    stdin: bool = True,
    json_out: bool = True,
) -> argparse.Namespace:
    return argparse.Namespace(
        subcommand="decide",
        decide_action="run",
        project=str(project),
        request_file=None,
        dp=dp,
        dp_id=dp_id,
        book=None,
        json=json_out,
        stdin=stdin,
    )


def _sign_args(project: pathlib.Path, **kw: object) -> argparse.Namespace:
    base: dict = {
        "subcommand": "decide",
        "decide_action": "sign",
        "project": str(project),
        "key": KEY,
        "key_pos": None,
        "auto": False,
        "disable": False,
        "reason": None,
        "allow_empty": False,
        "dry_run": False,
        "json": True,
        "stdin": False,
        "retry_write": None,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def _lifecycle_args(project: pathlib.Path, **kw: object) -> argparse.Namespace:
    base: dict = {
        "subcommand": "decide",
        "decide_action": "lifecycle",
        "project": str(project),
        "request_file": None,
        "json": True,
    }
    base.update(kw)
    return argparse.Namespace(**base)


def _stdin(monkeypatch: pytest.MonkeyPatch, payload: object) -> None:
    text = payload if isinstance(payload, str) else json.dumps(payload)
    monkeypatch.setattr(sys, "stdin", io.StringIO(text))


def _cli(args: argparse.Namespace, capsys: pytest.CaptureFixture) -> tuple[int, dict, str]:
    rc = mw.cmd_decide(args)
    captured = capsys.readouterr()
    payload = json.loads(captured.out) if captured.out.strip() else {}
    return rc, payload, captured.err


def _backend(monkeypatch: pytest.MonkeyPatch, *answers: str) -> decision.FakeBackend:
    results = [
        decision.BackendOutcome(
            available=True,
            reason=None,
            retryable=False,
            answers={"q-conclusion": {"value": value, "confidence": 0.9}},
            latency_ms=2,
            detail="",
        )
        for value in answers
    ]
    backend = decision.FakeBackend(results)
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: backend)
    return backend


def _lifecycle_rows(project: pathlib.Path) -> list[dict]:
    path = project / ".agenticdoc" / "_autopilot" / "decision-lifecycle.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _signoff_file(project: pathlib.Path) -> pathlib.Path:
    return _key_dir(project) / "evidence" / "review" / "sign-final.md"


def _result_dir(project: pathlib.Path) -> pathlib.Path:
    return _key_dir(project) / "evidence" / "review" / "decide-results"


def _tree_hashes() -> dict[str, str]:
    return {
        name: hashlib.sha256((pathlib.Path(__file__).parent / name).read_bytes()).hexdigest()
        for name in PROTECTED_SOURCES
    }


# ---------------------------------------------------------------------------
# 1. The minimal result record + credential-free sign-off validator (T06 face)
# ---------------------------------------------------------------------------


def test_result_record_round_trips_and_is_atomically_published(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    key_dir = _key_dir(project)
    material = _material()
    facts = decide_signoff.collect(key_dir, KEY)
    record = signoff_result.build_result(
        key_dir,
        key=KEY,
        logical_id="logical-t05-001",
        decision_id=f"{DP25}:logical-t05-001",
        conclusion="finalize",
        material=material,
        facts=facts,
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
        initiator_role="pm",
        task_key=None,
        retry_of=None,
    )
    path = signoff_result.write_result(
        key_dir, record, redact=decision.known_secret_redactor()
    )
    assert path.is_file()
    assert not list(path.parent.glob("*.tmp"))
    loaded = signoff_result.read_result(key_dir, "logical-t05-001")
    assert loaded is not None
    assert loaded.logical_id == record.logical_id
    assert loaded.snapshot_sha256 == record.snapshot_sha256
    assert loaded.material_sha256 == record.material_sha256
    assert loaded.conclusion == "finalize"


def test_result_path_refuses_a_non_filename_logical_id(tmp_path: pathlib.Path) -> None:
    key_dir = _key_dir(_project(tmp_path))
    with pytest.raises(signoff_result.SignoffResultError):
        signoff_result.result_path(key_dir, "logical:colon:not-a-file-name")


def test_result_record_never_stores_a_known_secret(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TIMI_API_KEY", SECRET)
    project = _project(tmp_path)
    key_dir = _key_dir(project)
    text = signoff_result.write_result(
        key_dir,
        signoff_result.build_result(
            key_dir,
            key=KEY,
            logical_id="logical-secret",
            decision_id=f"{DP25}:logical-secret",
            conclusion="finalize",
            material=_material(actual_completion=f"pasted {SECRET} here"),
            facts=decide_signoff.collect(key_dir, KEY),
            transport="timi-decisions",
            model="jev-latest",
            confidence_source="api",
        ),
        redact=decision.known_secret_redactor(),
    ).read_text(encoding="utf-8")
    assert SECRET not in text
    assert "<redacted>" in text


def test_result_record_refuses_a_symlinked_result_parent(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    key_dir = _key_dir(project)
    outside = tmp_path / "outside"
    outside.mkdir()
    results_dir = key_dir / "evidence" / "review" / "decide-results"
    if results_dir.exists():
        results_dir.rmdir()
    link = results_dir
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")
    record = signoff_result.build_result(
        key_dir,
        key=KEY,
        logical_id="logical-link",
        decision_id=f"{DP25}:logical-link",
        conclusion="finalize",
        material=_material(),
        facts=decide_signoff.collect(key_dir, KEY),
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
    )
    with pytest.raises(signoff_result.SignoffResultError):
        signoff_result.write_result(
            key_dir, record, redact=decision.known_secret_redactor()
        )
    assert not list(outside.iterdir())


def test_validator_accepts_the_exact_logical_id_and_snapshot(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    key_dir = _key_dir(project)
    material = _material()
    facts = decide_signoff.collect(key_dir, KEY)
    record = signoff_result.build_result(
        key_dir,
        key=KEY,
        logical_id="logical-valid",
        decision_id=f"{DP25}:logical-valid",
        conclusion="finalize",
        material=material,
        facts=facts,
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
    )
    signoff_result.write_result(key_dir, record, redact=decision.known_secret_redactor())
    text = decide_signoff.render(
        facts,
        "finalize",
        None,
        KEY,
        "-",
        result=record,
    )
    decide_signoff.write_signoff(key_dir, KEY, text)
    validation = signoff_result.validate_signoff(
        key_dir, KEY, expected_logical_id="logical-valid", expected_snapshot=record.snapshot_sha256
    )
    assert validation.valid is True, validation.reason
    assert validation.logical_id == "logical-valid"
    assert validation.snapshot_sha256 == record.snapshot_sha256
    assert validation.file_sha256 == hashlib.sha256(_signoff_file(project).read_bytes()).hexdigest()


def test_validator_rejects_a_different_logical_id_or_snapshot(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    key_dir = _key_dir(project)
    facts = decide_signoff.collect(key_dir, KEY)
    record = signoff_result.build_result(
        key_dir,
        key=KEY,
        logical_id="logical-a",
        decision_id=f"{DP25}:logical-a",
        conclusion="finalize",
        material=_material(),
        facts=facts,
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
    )
    signoff_result.write_result(key_dir, record, redact=decision.known_secret_redactor())
    decide_signoff.write_signoff(
        key_dir, KEY, decide_signoff.render(facts, "finalize", None, KEY, "-", result=record)
    )
    assert signoff_result.validate_signoff(key_dir, KEY, expected_logical_id="logical-b").valid is False
    assert signoff_result.validate_signoff(key_dir, KEY, expected_snapshot="0" * 64).valid is False


def test_validator_rejects_a_legacy_file_without_a_logical_id(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    key_dir = _key_dir(project)
    decide_signoff.write_signoff(
        key_dir,
        KEY,
        decide_signoff.render(
            decide_signoff.collect(key_dir, KEY), "continue", None, KEY, "-"
        ),
    )
    validation = signoff_result.validate_signoff(key_dir, KEY)
    assert validation.valid is False
    assert "logical_id" in validation.reason


def test_validator_rejects_a_result_record_alone(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    key_dir = _key_dir(project)
    record = signoff_result.build_result(
        key_dir,
        key=KEY,
        logical_id="logical-alone",
        decision_id=f"{DP25}:logical-alone",
        conclusion="finalize",
        material=_material(),
        facts=decide_signoff.collect(key_dir, KEY),
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
    )
    signoff_result.write_result(key_dir, record, redact=decision.known_secret_redactor())
    validation = signoff_result.validate_signoff(key_dir, KEY)
    assert validation.valid is False


def test_validator_refuses_a_symlinked_signoff_file(tmp_path: pathlib.Path) -> None:
    project = _project(tmp_path)
    key_dir = _key_dir(project)
    outside = tmp_path / "outside-signoff.md"
    outside.write_text("forged", encoding="utf-8")
    target = _signoff_file(project)
    try:
        target.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")
    validation = signoff_result.validate_signoff(key_dir, KEY)
    assert validation.valid is False
    assert "unsafe" in validation.reason or "symbolic" in validation.reason


# ---------------------------------------------------------------------------
# 2. mw decide run <dp> --stdin: creation fact, association, no duplicate send
# ---------------------------------------------------------------------------


def test_run_stdin_records_start_before_the_call_and_associates_decision_id(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize")
    _stdin(monkeypatch, _envelope())
    rc, payload, err = _cli(_run_args(project), capsys)
    assert rc == 0, err
    assert payload["available"] is True
    assert payload["logical_id"] == "logical-t05-001"
    assert payload["decision_id"] == f"{DP25}:logical-t05-001"
    assert payload["record_start"] == "written"
    # meta never reaches the model
    assert backend.calls[0]["state"] == _material()
    rows = _lifecycle_rows(project)
    assert rows[0]["kind"] == "record-start"
    assert rows[0]["logical_id"] == "logical-t05-001"
    assert rows[0]["task_key"] is None
    linked = [row for row in rows if row.get("kind") == "lifecycle"]
    assert linked, rows
    assert linked[-1]["decision_id"] == f"{DP25}:logical-t05-001"
    assert linked[-1]["logical_id"] == "logical-t05-001"


def test_run_stdin_duplicate_logical_id_makes_no_second_model_call(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize", "continue")
    _stdin(monkeypatch, _envelope())
    rc, _payload, err = _cli(_run_args(project), capsys)
    assert rc == 0, err
    _stdin(monkeypatch, _envelope())
    rc, payload, err = _cli(_run_args(project), capsys)
    assert rc == 0, err
    assert len(backend.calls) == 1, "an already processed logical_id was sent again"
    assert payload["replayed"] is True
    assert payload["decision_id"] == f"{DP25}:logical-t05-001"


def test_run_stdin_known_role_is_lowercased_and_never_guesses_pm(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    _backend(monkeypatch, "finalize")
    _stdin(monkeypatch, _envelope(role="PM"))
    rc, _payload, err = _cli(_run_args(project), capsys)
    assert rc == 0, err
    assert _lifecycle_rows(project)[0]["initiator_role"] == "pm"

    project2 = _project(tmp_path / "second")
    _backend(monkeypatch, "finalize")
    _stdin(monkeypatch, _envelope(logical_id="logical-unknown", role="mystery-caller"))
    rc, _payload, err = _cli(_run_args(project2), capsys)
    assert rc == 0, err
    assert _lifecycle_rows(project2)[0]["initiator_role"] == "unknown"


def test_run_stdin_empty_task_is_null_and_real_task_is_recorded(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    _backend(monkeypatch, "finalize")
    _stdin(monkeypatch, _envelope(task_key="dc-t05-signoff-cli"))
    rc, _payload, err = _cli(_run_args(project), capsys)
    assert rc == 0, err
    assert _lifecycle_rows(project)[0]["task_key"] == "dc-t05-signoff-cli"

    project2 = _project(tmp_path / "second")
    _backend(monkeypatch, "finalize")
    _stdin(monkeypatch, _envelope(logical_id="logical-null-task", task_key=None))
    rc, _payload, err = _cli(_run_args(project2), capsys)
    assert rc == 0, err
    assert _lifecycle_rows(project2)[0]["task_key"] is None


@pytest.mark.parametrize(
    "material, expected",
    [
        (_material(rows_total=3), "rows_total"),
        ({"delivery_goal": "x", "actual_completion": "y"}, "verification_evidence"),
    ],
)
def test_run_stdin_invalid_material_is_refused_with_zero_post(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    material: dict,
    expected: str,
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize")
    _stdin(monkeypatch, _envelope(material=material))
    rc, payload, err = _cli(_run_args(project), capsys)
    assert rc == 0, err
    assert payload["available"] is False
    assert expected in (payload.get("reason") or "") or expected in (payload.get("detail") or "")
    assert backend.calls == []


def test_run_stdin_concurrent_duplicate_start_never_sends(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize")
    monkeypatch.setattr(
        lifecycle,
        "record_start",
        lambda *a, **k: lifecycle.LifecycleResult(
            stage="record-start", status="duplicate", event_id="rs-existing"
        ),
    )
    _stdin(monkeypatch, _envelope())
    rc, payload, err = _cli(_run_args(project), capsys)
    assert rc == 0, err
    assert payload["replayed"] is True
    assert payload["available"] is False
    assert backend.calls == [], "a concurrent duplicate must never reach the model"


def test_run_stdin_same_key_different_logical_id_is_a_new_decision(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize", "continue")
    _stdin(monkeypatch, _envelope(logical_id="logical-a"))
    rc, _payload, err = _cli(_run_args(project), capsys)
    assert rc == 0, err
    _stdin(monkeypatch, _envelope(logical_id="logical-b", retry_of="logical-a"))
    rc, payload, err = _cli(_run_args(project), capsys)
    assert rc == 0, err
    assert len(backend.calls) == 2, "a new logical id must be a new decision"
    assert payload["logical_id"] == "logical-b"
    assert payload["decision_id"] == f"{DP25}:logical-b"


def test_run_stdin_freezes_exactly_one_credential_snapshot(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    _backend(monkeypatch, "finalize")
    calls: list[object] = []
    original = decision.credential_snapshot

    def spy(cfg: object = None, **kwargs: object):
        snapshot = original(cfg, **kwargs)
        calls.append(snapshot)
        return snapshot

    monkeypatch.setattr(decision, "credential_snapshot", spy)
    _stdin(monkeypatch, _envelope())
    rc, _payload, err = _cli(_run_args(project), capsys)
    assert rc == 0, err
    assert len(calls) == 1, "the command must freeze one credential snapshot"


def test_run_stdin_disabled_never_posts(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    (project / ".mw" / "decide.json").write_text(
        json.dumps({"enabled": False}), encoding="utf-8"
    )
    backend = _backend(monkeypatch, "finalize")
    _stdin(monkeypatch, _envelope())
    rc, payload, err = _cli(_run_args(project), capsys)
    assert rc == 0, err
    assert payload["available"] is False
    assert payload["reason"] == "disabled"
    assert backend.calls == []


def test_run_stdin_oversized_material_is_refused_with_zero_post(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize")
    _stdin(
        monkeypatch,
        _envelope(
            material=_material(delivery_goal="x" * (dpts.MAX_STATE_BYTES + 1))
        ),
    )
    rc, payload, err = _cli(_run_args(project), capsys)
    assert rc == 0, err
    assert payload["available"] is False
    assert payload["escalated_reason"] == "input-oversize"
    assert backend.calls == []


def test_run_stdin_record_start_failure_refuses_to_send(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize")
    monkeypatch.setattr(
        lifecycle,
        "record_start",
        lambda *a, **k: lifecycle.LifecycleResult(
            stage="record-start", status="failed", error_class="append", error_recorded=True
        ),
    )
    _stdin(monkeypatch, _envelope())
    rc, payload, err = _cli(_run_args(project), capsys)
    assert rc == 2, err
    assert payload["available"] is False
    assert payload["recorded"] is False
    assert backend.calls == []


def test_run_stdin_rejects_unknown_envelope_keys(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize")
    envelope = _envelope()
    envelope["questions"] = {"triage_type": {"type": "noul"}}
    _stdin(monkeypatch, envelope)
    rc, _payload, _err = _cli(_run_args(project), capsys)
    assert rc == 2
    assert backend.calls == []


def test_run_stdin_positional_dp_is_the_command_contract(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    _backend(monkeypatch, "finalize")
    _stdin(monkeypatch, _envelope())
    rc, payload, err = _cli(_run_args(project, dp_id=DP25, dp=None), capsys)
    assert rc == 0, err
    assert payload["dp"] == DP25


# ---------------------------------------------------------------------------
# 3. mw decide lifecycle --stdin: closed schema, T02 writer, status contract
# ---------------------------------------------------------------------------


def _lifecycle_payload(**overrides: object) -> dict:
    payload = {
        "meta": _envelope()["meta"],
        "decision_id": f"{DP25}:logical-t05-001",
        "dp": DP25,
        "stage": "consumed",
        "answer": "finalize",
    }
    payload.update(overrides)
    return payload


def test_lifecycle_consumed_records_receipt_only(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    _stdin(monkeypatch, _lifecycle_payload())
    rc, payload, err = _cli(_lifecycle_args(project), capsys)
    assert rc == 0, err
    assert payload["status"] == "written"
    assert payload["recorded"] is True
    assert payload["error_class"] is None
    assert payload["error_recorded"] is None
    rows = _lifecycle_rows(project)
    assert [row.get("lifecycle") for row in rows] == ["consumed"]
    assert rows[0]["decision_id"] == f"{DP25}:logical-t05-001"
    assert not _signoff_file(project).exists()


def test_lifecycle_executed_requires_a_declared_action_and_writes_nothing_on_refusal(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    _stdin(monkeypatch, _lifecycle_payload(stage="executed"))
    rc, payload, err = _cli(_lifecycle_args(project), capsys)
    assert rc == 2, err
    assert payload["recorded"] is False
    assert payload["status"] == "refused"
    assert _lifecycle_rows(project) == []


def test_lifecycle_settled_requires_an_outcome(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    _stdin(monkeypatch, _lifecycle_payload(stage="settled", answer=None))
    rc, payload, err = _cli(_lifecycle_args(project), capsys)
    assert rc == 2, err
    assert payload["recorded"] is False


def test_lifecycle_rejects_unknown_fields_without_echoing_values(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    payload = _lifecycle_payload()
    payload["secr3t"] = "do-not-echo-this-value"
    _stdin(monkeypatch, payload)
    rc, out, err = _cli(_lifecycle_args(project), capsys)
    assert rc == 2
    assert "do-not-echo-this-value" not in json.dumps(out) + err
    assert _lifecycle_rows(project) == []


def test_lifecycle_known_secret_in_a_structural_value_is_refused_without_echo(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    payload = _lifecycle_payload(decision_id=f"{DP25}:{SECRET}")
    _stdin(monkeypatch, payload)
    rc, out, err = _cli(_lifecycle_args(project), capsys)
    assert rc == 2
    assert SECRET not in json.dumps(out) + err
    assert _lifecycle_rows(project) == []


def test_lifecycle_event_id_is_idempotent(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    payload = _lifecycle_payload(event_id="evt-consumed-1")
    _stdin(monkeypatch, payload)
    rc, _payload, err = _cli(_lifecycle_args(project), capsys)
    assert rc == 0, err
    _stdin(monkeypatch, payload)
    rc, payload, err = _cli(_lifecycle_args(project), capsys)
    assert rc == 0, err
    assert payload["status"] == "duplicate"
    assert payload["recorded"] is True
    assert len(_lifecycle_rows(project)) == 1


def test_lifecycle_signoff_stage_records_the_file_fact(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    payload = _lifecycle_payload(
        stage="signoff",
        answer=None,
        evidence_path="evidence/review/sign-final.md",
        evidence_sha256="a" * 64,
        event_id="evt-signoff-1",
    )
    _stdin(monkeypatch, payload)
    rc, out, err = _cli(_lifecycle_args(project), capsys)
    assert rc == 0, err
    assert out["status"] == "written"
    rows = _lifecycle_rows(project)
    assert rows[0]["lifecycle"] == "signoff"
    assert rows[0]["evidence_sha256"] == "a" * 64


def test_lifecycle_write_failure_is_reported_and_not_faked(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    monkeypatch.setattr(
        lifecycle,
        "record_consumed",
        lambda *a, **k: lifecycle.LifecycleResult(
            stage="consumed",
            status="failed",
            error_class="append",
            error_recorded=True,
        ),
    )
    _stdin(monkeypatch, _lifecycle_payload())
    rc, payload, err = _cli(_lifecycle_args(project), capsys)
    assert rc == 1, err
    assert payload["recorded"] is False
    assert payload["status"] == "failed"
    assert payload["error_class"] == "append"
    assert payload["error_recorded"] is True


# ---------------------------------------------------------------------------
# 4. mw decide sign <key> --stdin: minimal dp25 finalize/continue/user-confirm
# ---------------------------------------------------------------------------


def _sign_stdin(monkeypatch: pytest.MonkeyPatch, **changes: object) -> None:
    _stdin(monkeypatch, _envelope(**changes))


def test_sign_finalize_writes_the_valid_signoff_without_a_second_approval(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize")
    _sign_stdin(monkeypatch)
    rc, payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 0, err
    assert payload["conclusion"] == "finalize"
    assert payload["signoff_status"] == "written"
    assert payload["feedback_status"] == "recorded"
    assert payload["second_approval"] == 0
    validation = signoff_result.validate_signoff(
        _key_dir(project), KEY, expected_logical_id="logical-t05-001"
    )
    assert validation.valid is True, validation.reason
    assert validation.conclusion == "finalize"
    assert len(backend.calls) == 1
    rows = _lifecycle_rows(project)
    assert rows[0]["kind"] == "record-start"
    assert any(row.get("lifecycle") == "signoff" for row in rows)
    # dp25 is judged from the PM's four business parts, never from old counts.
    sent = backend.calls[0]["state"]
    assert sent == _material()
    assert set(sent).isdisjoint(
        {"rows_total", "rows_available", "chain_ok", "p0_open", "counted_rows"}
    )
    # the result record is the retry face, the file is the success authority
    assert signoff_result.read_result(_key_dir(project), "logical-t05-001") is not None


def test_sign_finalize_repeat_keeps_the_file_bytes_and_time_and_skips_the_model(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize", "continue")
    _sign_stdin(monkeypatch)
    rc, _payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 0, err
    path = _signoff_file(project)
    before = (path.read_bytes(), path.stat().st_mtime_ns)
    _sign_stdin(monkeypatch)
    rc, payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 0, err
    assert payload["signoff_status"] == "existing"
    assert (path.read_bytes(), path.stat().st_mtime_ns) == before
    assert len(backend.calls) == 1


def test_sign_finalize_write_failure_retries_the_write_only(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize")
    real_write = decide_signoff.write_signoff

    def failing_write(*args: object, **kwargs: object) -> pathlib.Path:
        raise OSError("programmed write failure")

    monkeypatch.setattr(decide_signoff, "write_signoff", failing_write)
    _sign_stdin(monkeypatch)
    rc, payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 2, err
    assert payload["signoff_status"] == "failed"
    assert payload["write_error_class"] == "OSError"
    assert not _signoff_file(project).exists()
    assert signoff_result.read_result(_key_dir(project), "logical-t05-001") is not None
    assert len(backend.calls) == 1

    monkeypatch.setattr(decide_signoff, "write_signoff", real_write)
    rc, payload, err = _cli(_sign_args(project, retry_write="logical-t05-001"), capsys)
    assert rc == 0, err
    assert payload["signoff_status"] == "written"
    assert len(backend.calls) == 1, "the retry write must not call the model again"
    assert signoff_result.validate_signoff(_key_dir(project), KEY).valid is True


def test_sign_material_change_rejects_the_old_conclusion_without_a_model_call(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize", "finalize")
    _sign_stdin(monkeypatch)
    rc, _payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 0, err
    path = _signoff_file(project)
    before = path.read_bytes()
    _sign_stdin(
        monkeypatch,
        material=_material(actual_completion="different completion after the model call"),
    )
    rc, payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 2, err
    assert "material" in (payload.get("problems") or [""])[0].lower()
    assert path.read_bytes() == before
    assert len(backend.calls) == 1


@pytest.mark.parametrize("conclusion", ["continue", "user-confirm"])
def test_sign_continue_and_user_confirm_write_zero_signoff_and_hand_off_to_pm(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
    conclusion: str,
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, conclusion)
    _sign_stdin(monkeypatch)
    rc, payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 0, err
    assert payload["conclusion"] == conclusion
    assert payload["signoff_status"] == "not-required"
    assert payload["handoff"]["owner"] == "pm"
    assert not _signoff_file(project).exists()
    assert len(backend.calls) == 1
    # the retained result makes a repeated receipt zero-model
    _sign_stdin(monkeypatch)
    rc, payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 0, err
    assert len(backend.calls) == 1
    assert payload["handoff"]["kind"] == conclusion


def test_sign_a_new_decision_is_not_skipped_because_the_key_was_signed(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize", "finalize")
    _sign_stdin(monkeypatch, logical_id="logical-first")
    rc, _payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 0, err
    _sign_stdin(
        monkeypatch,
        logical_id="logical-second",
        retry_of="logical-first",
        material=_material(delivery_goal="a second, explicitly new judgment"),
    )
    rc, payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 0, err
    assert len(backend.calls) == 2
    assert payload["logical_id"] == "logical-second"
    validation = signoff_result.validate_signoff(
        _key_dir(project), KEY, expected_logical_id="logical-second"
    )
    assert validation.valid is True, validation.reason


def test_sign_feedback_failure_is_separate_from_a_real_signoff(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    _backend(monkeypatch, "finalize")
    real_record_signoff = lifecycle.record_signoff

    def failing_record_signoff(*args: object, **kwargs: object):
        return lifecycle.LifecycleResult(
            stage="signoff", status="failed", error_class="append", error_recorded=True
        )

    monkeypatch.setattr(lifecycle, "record_signoff", failing_record_signoff)
    _sign_stdin(monkeypatch)
    rc, payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 0, err
    assert payload["signoff_status"] == "written", "a feedback failure must not revoke a real file write"
    assert payload["signoff_status"] == "written"
    assert payload["feedback_status"] == "partial"
    assert payload["feedback_error_class"] == "append"
    assert _signoff_file(project).is_file()
    monkeypatch.setattr(lifecycle, "record_signoff", real_record_signoff)


def test_sign_evidence_only_change_also_requires_a_new_judgment(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize", "finalize")
    _sign_stdin(monkeypatch)
    rc, _payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 0, err
    changed = _material(
        verification_evidence={
            "verified": ["a newer verification run"],
            "unverified": [],
        }
    )
    _sign_stdin(monkeypatch, material=changed)
    rc, payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 2, err
    assert any("evidence" in problem for problem in payload["problems"])
    assert len(backend.calls) == 1


def test_sign_unrecoverable_result_readback_refuses_to_guess(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize")
    target = _result_dir(project) / "logical-t05-001.json"
    target.parent.mkdir(parents=True)
    target.write_text("{not json", encoding="utf-8")
    _sign_stdin(monkeypatch)
    rc, payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 2, err
    assert payload["signoff_status"] == "failed"
    assert backend.calls == []


def test_sign_refuses_an_unsafe_signoff_path_before_the_model(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    key_dir = _key_dir(project)
    review = key_dir / "evidence" / "review"
    review.rmdir()
    outside = tmp_path / "outside-review"
    outside.mkdir()
    try:
        review.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks are not available on this platform")
    backend = _backend(monkeypatch, "finalize")
    _sign_stdin(monkeypatch)
    rc, payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 2, err
    assert payload["signoff_status"] == "failed"
    assert backend.calls == []
    assert not (outside / "sign-final.md").exists()


def test_sign_stdin_requires_the_envelope_key_to_match_the_command_key(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    backend = _backend(monkeypatch, "finalize")
    envelope = _envelope()
    envelope["meta"]["key"] = "some-other-key"
    _stdin(monkeypatch, envelope)
    rc, _payload, _err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 2
    assert backend.calls == []


def test_sign_refuses_a_broken_archive_chain_before_the_model(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    project = _project(tmp_path)
    archive = project / ".agenticdoc" / "_autopilot" / "decisions.jsonl"
    archive.parent.mkdir(parents=True)
    archive.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "seq": 5,
                "kind": "decide",
                "dp": "dp1-dispatch-type",
                "key": KEY,
                "prev_sha": "0" * 16,
            }
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    backend = _backend(monkeypatch, "finalize")
    _sign_stdin(monkeypatch)
    rc, payload, err = _cli(_sign_args(project, stdin=True), capsys)
    assert rc == 2, err
    assert any("chain" in problem.lower() for problem in payload["problems"])
    assert backend.calls == []
    assert not _signoff_file(project).exists()


# ---------------------------------------------------------------------------
# 5. Real argv/stdin through a loopback HTTP faux backend
# ---------------------------------------------------------------------------


class _LoopbackHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self) -> None:  # noqa: N802 - stdlib API
        length = int(self.headers.get("Content-Length") or "0")
        body = self.rfile.read(length)
        self.server.requests.append(body)  # type: ignore[attr-defined]
        payload = json.dumps(
            {
                "model": "jev-latest",
                "answers": {
                    "q-conclusion": {
                        "type": "choice",
                        "choice": "finalize",
                        "confidence": 0.9,
                    }
                },
            }
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)
        self.wfile.flush()

    def log_message(self, fmt: str, *args: object) -> None:
        return


class _LoopbackServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, address: tuple[str, int]) -> None:
        super().__init__(address, _LoopbackHandler)
        self.requests: list[bytes] = []

    def handle_error(self, request, client_address) -> None:  # noqa: ANN001
        return


@pytest.fixture
def loopback() -> _LoopbackServer:
    server = _LoopbackServer(("127.0.0.1", 0))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _subprocess(project: pathlib.Path, *argv: str, stdin: dict) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["TIMI_BASE_URL"] = "http://127.0.0.1:9"
    env.pop("TIMI_API_KEY", None)
    return subprocess.run(
        [sys.executable, str(MW_PY), *argv, "--project", str(project)],
        input=json.dumps(stdin),
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=str(pathlib.Path(__file__).parent),
        env=env,
        timeout=90,
        check=False,
    )


def _loopback_config(project: pathlib.Path, server: _LoopbackServer) -> None:
    (project / ".mw" / "decide.json").write_text(
        json.dumps(
            {
                "enabled": True,
                "base_url": f"http://127.0.0.1:{server.server_address[1]}",
                "api_key": "synthetic-t05-loopback-key",
                "timeout_s": 5.0,
                "max_retries": 0,
                "backoff_base_s": 0.0,
            }
        ),
        encoding="utf-8",
    )


def test_real_argv_run_posts_the_material_only_and_keeps_the_production_tree(
    tmp_path: pathlib.Path, loopback: _LoopbackServer
) -> None:
    project = _project(tmp_path)
    _loopback_config(project, loopback)
    before = _tree_hashes()
    result = _subprocess(
        project, "decide", "run", DP25, "--stdin", "--json", stdin=_envelope()
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["available"] is True
    assert payload["logical_id"] == "logical-t05-001"
    assert len(loopback.requests) == 1
    body = json.loads(loopback.requests[0].decode("utf-8"))
    state = body["state"]
    assert state == _material()
    assert set(state).isdisjoint({"logical_id", "key", "task_key", "initiator_role"})
    assert _tree_hashes() == before


def test_real_argv_lifecycle_records_through_the_cli(
    tmp_path: pathlib.Path,
) -> None:
    project = _project(tmp_path)
    before = _tree_hashes()
    result = _subprocess(
        project,
        "decide",
        "lifecycle",
        "--stdin",
        "--json",
        stdin=_lifecycle_payload(),
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["recorded"] is True
    assert payload["status"] == "written"
    assert _tree_hashes() == before


def test_real_argv_sign_finalize_writes_the_file_from_stdin_material(
    tmp_path: pathlib.Path, loopback: _LoopbackServer
) -> None:
    project = _project(tmp_path)
    _loopback_config(project, loopback)
    before = _tree_hashes()
    result = _subprocess(
        project, "decide", "sign", KEY, "--stdin", "--json", stdin=_envelope()
    )
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["signoff_status"] == "written"
    assert payload["conclusion"] == "finalize"
    assert signoff_result.validate_signoff(
        _key_dir(project), KEY, expected_logical_id="logical-t05-001"
    ).valid is True
    assert len(loopback.requests) == 1
    assert _tree_hashes() == before
