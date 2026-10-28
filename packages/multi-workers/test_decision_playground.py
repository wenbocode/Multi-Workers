"""Tests for the DP test playground provider (mw-decision-dashboard T06).

The provider sits behind ``decision_monitor``'s read/playground seam and is the
only place a *test* submission can reach the decision chain. This suite locks
the properties the card makes it responsible for:

* hidden/scripted internals only: one ``cfg`` read, one complete
  ``decision.credential_snapshot``, and that same snapshot for the book gate
  (``decision.known_secret_redactor``), the trusted capture
  ``decision.credential_redactor`` and the client pin;
* the real internal decision chain (``decide_for`` -> ``DecisionClient`` ->
  backend) with ``intent="answer"``, so the executor is never invoked;
* isolated test sinks (``.mw/decide-test/*``): production archives, sign-off and
  triage files stay byte-identical;
* explicit human submission only: opening, polling, scaffolding, validating and
  reading history never spend a model call;
* one running submission and zero queue (busy), strong de-duplication of
  ``submit_id`` inside the submission lock, a new id per retry with an explicit
  ``retry_of`` link;
* ``submission-start`` write failure means zero network; a later record failure
  is reported as ``record-failed`` instead of a fabricated success;
* invalid material is refused before the transport (zero model calls), and the
  very same review function decides ``validate`` and ``submit``;
* N2 (T10b review): descendants of a declared ``object`` subtree (dp1
  ``history``) and of object array items (dp2 ``progress.trend``) are scanned
  for execution/authorization keys, while legitimate business data passes.

No test performs real network I/O, reads the developer's credential store or
writes a production ledger.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import pathlib
import threading

import pytest

import decision
import decision_backends
import decision_book
import decision_monitor
import decision_playground
import decision_points as dpts
import decision_wire

DP1 = "dp1-dispatch-type"
DP2 = "dp2-checkpoint-split"
DP4 = "dp4-failure-handling"

TEST_SECRET = "sk-t06-playground-0123456789abcdef"


# ---------------------------------------------------------------------------
# Hermetic fixture: no ambient credential discovery, no points-config cache
# ---------------------------------------------------------------------------


def _credential_env_names() -> tuple[str, ...]:
    names: set[str] = set()
    names.update(
        name for name in os.environ if name.upper().endswith(decision._CRED_ENV_SUFFIXES)
    )
    return tuple(sorted(names))


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch, tmp_path: pathlib.Path):
    for name in _credential_env_names():
        monkeypatch.delenv(name, raising=False)
    # Credential discovery must never read the developer's real auth.json.
    monkeypatch.setattr(
        decision_backends, "_auth_json_path", lambda: tmp_path / "no-auth.json"
    )
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


# ---------------------------------------------------------------------------
# Fixtures: a control root, points config and decision books
# ---------------------------------------------------------------------------


def _make_control(root: pathlib.Path) -> pathlib.Path:
    """A control root (the ``.agenticdoc`` shape is the control evidence)."""
    project = root / "project"
    (project / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    return project


def _write_decide_config(project: pathlib.Path, **fields) -> pathlib.Path:
    path = project / ".mw" / "decide.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"enabled": True, **fields}, ensure_ascii=False),
        encoding="utf-8",
        newline="\n",
    )
    return path


def _write_points(project: pathlib.Path, points: dict) -> pathlib.Path:
    path = project / ".mw" / "decide-points.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"version": 1, "points": points}, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    dpts.clear_points_config_cache()
    return path


def _dp1_state(**overrides) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP1,
        "key": "k-t06",
        "phase": "EXECUTE",
        "task_type": "coding",
        "requested_type": "coding",
        "risk": "low",
        "risk_source": "machine",
        "authority_tier": "P2",
        "task_summary": "human requested an observation of the dispatch triage",
        "scope": {
            "write_scope": ["packages/multi-workers"],
            "file_extensions": [".py"],
        },
    }
    state.update(overrides)
    return state


def _dp2_state(**overrides) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP2,
        "key": "k-t06",
        "phase": "EXECUTE",
        "task_type": "coding",
        "risk": "mid",
        "risk_source": "machine",
        "authority_tier": "P2",
        "progress": {
            "elapsed_minutes": 12,
            "budget_minutes": 30,
            "phases_done": 1,
            "phases_total": 3,
            "artifact_present": True,
        },
    }
    state.update(overrides)
    return state


def _dp4_state(**overrides) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP4,
        "failure": {
            "kind": "transient",
            "attempt": 1,
            "limit": 2,
            "artifact_present": False,
        },
    }
    state.update(overrides)
    return state


def _book(dp_id: str, state: dict, *, context: dict | None = None) -> dict:
    """A book ``decision_book.check_book`` accepts unchanged."""
    payload = dict(state)
    payload.setdefault("questions_version", dpts.get_decision_point(dp_id).questions_version)
    evidence = {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[dp_id]}
    book = {
        "schema_version": decision_book.BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "state": payload,
        "notes": {"evidence": evidence},
    }
    if context is not None:
        book["context"] = context
    return book


def _ok(answers: dict) -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=True,
        reason=None,
        retryable=False,
        answers=answers,
        latency_ms=3,
        detail="",
    )


DP4_ANSWERS = {"failure_action": {"value": "retry", "confidence": 0.9}}
DP1_ANSWERS = {
    "triage_type": {"value": "coding", "confidence": 0.9},
    "triage_risk": {"value": "low", "confidence": 0.9},
}


class _Backends:
    """A backend factory that records every backend it creates (call counting)."""

    def __init__(self, results: list | None = None, *, answers: dict | None = None,
                 result_factory=None) -> None:
        self.created: list = []
        self._results = results
        self._answers = answers
        self._factory = result_factory

    def __call__(self, cfg):
        if self._factory is not None:
            backend = self._factory(cfg)
        else:
            results = list(self._results) if self._results is not None else [_ok(self._answers or {})]
            backend = decision.FakeBackend(results)
        self.created.append(backend)
        return backend

    @property
    def calls(self) -> int:
        return sum(len(getattr(backend, "calls", [])) for backend in self.created)


def _playground(project: pathlib.Path, *, answers: dict | None = None,
                results: list | None = None, factory=None) -> tuple:
    backends = _Backends(results=results, answers=answers, result_factory=factory)
    playground = decision_playground.DecisionPlayground(
        project, backend_factory=backends, warn=lambda line: None
    )
    return playground, backends


def _test_events(project: pathlib.Path) -> list[dict]:
    return list(
        decision_wire.read_events(decision_wire.test_wire_sink(
            project / decision_playground.TEST_ROOT_RELATIVE_PATH
        )).events
    )


def _of_kind(project: pathlib.Path, kind: str) -> list[dict]:
    return [event for event in _test_events(project) if event.get("kind") == kind]


def _tree(path: pathlib.Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for item in sorted(path.rglob("*")):
        if item.is_file():
            out[item.relative_to(path).as_posix()] = hashlib.sha256(
                item.read_bytes()
            ).hexdigest()
    return out


def _submit(playground, dp: str, book: dict, submit_id: str, **extra) -> dict:
    request = {"dp": dp, "book": book, "submit_id": submit_id, "observe_only": True}
    request.update(extra)
    return playground.submit(request)


# ---------------------------------------------------------------------------
# 1. scaffold / validate never spend a model call
# ---------------------------------------------------------------------------


def _has_path(state: object, dotted: str) -> bool:
    current = state
    for part in dotted.split("."):
        if not isinstance(current, dict) or part not in current:
            return False
        current = current[part]
    return True


def test_scaffold_covers_every_registered_dp_with_typed_fields(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    playground, backends = _playground(project)

    for point in dpts.DP_REGISTRY:
        result = playground.scaffold(point.id)
        assert result["dp"] == point.id
        book = result["book"]
        assert book["decision_point"] == point.id
        assert book["schema_version"] == decision_book.BOOK_SCHEMA_VERSION
        declared = [field["name"] for field in result["required_state_fields"]]
        assert declared == list(dpts.REQUIRED_STATE_FIELDS.get(point.id, ()))
        for name in declared:
            assert _has_path(book["state"], name), (point.id, name)
            assert name in book["notes"]["evidence"], (point.id, name)
            spec = dpts.STATE_FIELD_DESCRIPTIONS[name]
            assert spec["type"] and spec["description"].strip(), name
        assert result["observe_only"] is True
        assert result["max_state_bytes"] == dpts.MAX_STATE_BYTES

    assert backends.created == [], "scaffolding must never create a backend"


def test_scaffold_placeholder_book_is_refused_by_validate(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    playground, backends = _playground(project)

    scaffold = playground.scaffold(DP4)
    report = playground.validate(DP4, scaffold["book"])

    assert report["ok"] is False
    codes = {issue["code"] for issue in report["issues"]}
    assert "book-placeholder" in codes
    assert backends.created == []
    assert _test_events(project) == [], "validate writes no ledger row"


def test_validate_accepts_a_filled_book_and_reports_the_send_state(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    playground, backends = _playground(project)
    book = _book(DP4, _dp4_state())

    report = playground.validate(DP4, book)

    assert report["ok"] is True, report["issues"]
    assert report["issues"] == []
    assert report["state_bytes"] <= dpts.MAX_STATE_BYTES
    assert isinstance(report["state_digest"], str) and len(report["state_digest"]) == 16
    assert report["context_sent"] is False
    assert backends.created == []
    assert _test_events(project) == []


def test_validate_refuses_unknown_keys_wrong_types_and_bad_enums(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    playground, _ = _playground(project)

    unknown = _book(DP4, _dp4_state(undeclared_fact="x"))
    wrong_type = _book(DP4, _dp4_state(failure={"kind": "transient", "attempt": "1",
                                                "limit": 2, "artifact_present": False}))
    bad_enum = _book(DP4, _dp4_state(failure={"kind": "sometimes", "attempt": 1,
                                             "limit": 2, "artifact_present": False}))

    for book, needle in (
        (unknown, "undeclared_fact"),
        (wrong_type, "failure.attempt"),
        (bad_enum, "failure.kind"),
    ):
        report = playground.validate(DP4, book)
        assert report["ok"] is False, needle
        paths = " ".join(issue["path"] for issue in report["issues"])
        assert needle in paths, (needle, paths)
        assert all(issue["code"].startswith("book-") or issue["code"] == "forbidden-field"
                   for issue in report["issues"])


def test_validate_refuses_a_book_carrying_a_credential(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    playground, _ = _playground(project)
    book = _book(DP4, _dp4_state())
    book["state"]["failure"]["kind"] = TEST_SECRET

    report = playground.validate(DP4, book)

    assert report["ok"] is False
    assert any(issue["code"] == "book-secret" for issue in report["issues"])
    assert TEST_SECRET not in json.dumps(report)


# ---------------------------------------------------------------------------
# 2. The explicit submission runs the real internal chain, never the executor
# ---------------------------------------------------------------------------


def test_submit_runs_the_internal_chain_and_returns_the_real_answer(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    executor_calls: list[object] = []

    def spy_executor(answers, trigger):
        executor_calls.append(answers)
        return "acted"

    point = dpts._REGISTRY_BY_ID[DP4]
    monkeypatch.setitem(
        dpts._REGISTRY_BY_ID, DP4, dataclasses.replace(point, executor=spy_executor)
    )
    playground, backends = _playground(project, answers=DP4_ANSWERS)

    result = _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-run-1")

    assert result["state"] == "succeeded", result
    assert result["accepted"] is True
    assert result["duplicate"] is False
    assert result["zero_call"] is False
    assert result["decision_id"] == f"{DP4}:sub-run-1"
    assert isinstance(result["started_at"], str) and result["started_at"]
    assert isinstance(result["finished_at"], str) and result["finished_at"]
    assert result["started_at"] <= result["finished_at"]
    assert result["outcome"]["status"] == "suggested"
    assert result["outcome"]["answer"] == DP4_ANSWERS
    assert executor_calls == [], "an observation must never invoke the executor"
    assert backends.calls == 1

    ends = _of_kind(project, "submission-end")
    assert len(ends) == 1
    assert ends[0]["outcome"] == "succeeded"
    assert ends[0]["submission_id"] == "sub-run-1"
    assert ends[0]["scope"] == "test"


def test_submission_writes_only_the_isolated_test_sinks(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    before = _tree(project / ".agenticdoc")
    playground, _ = _playground(project, answers=DP4_ANSWERS)

    result = _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-iso-1")

    assert result["state"] == "succeeded", result
    assert _tree(project / ".agenticdoc") == before, "production evidence must stay byte-identical"
    assert not (project / dpts.DECISIONS_RELATIVE_PATH).exists()

    test_root = project / decision_playground.TEST_ROOT_RELATIVE_PATH
    assert decision_wire.test_wire_sink(test_root).is_file()
    assert decision_wire.test_evidence_sink(test_root).is_file()
    events = _test_events(project)
    assert events and all(event["scope"] == "test" for event in events)
    assert all(event["submission_id"] == "sub-iso-1" for event in events)
    assert len([e for e in events if e["kind"] == "submission-start"]) == 1
    assert len([e for e in events if e["kind"] == "book-snapshot"]) == 1
    assert len([e for e in events if e["kind"] == "decision-end"]) == 1


def test_observation_bypasses_a_disabled_dp_while_production_still_sends_nothing(
    tmp_path: pathlib.Path,
) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    # dp4 is P1: disabled by default, so only the observation exception can run it.
    playground, backends = _playground(project, answers=DP4_ANSWERS)

    observation = _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-obs-1")
    assert observation["state"] == "succeeded", observation
    assert observation["outcome"]["observation"]["bypassed"] is True
    assert backends.calls == 1

    production = decision_points_script(project, _dp4_state())
    assert production.status == "escalated"
    assert production.escalated_reason == "disabled"
    assert backends.calls == 1, "the production path of a disabled dp must not reach the backend"


def decision_points_script(project, state):
    """The same dp through the production entry point (no observation)."""
    return dpts.decide_for(
        DP4, dpts.Trigger.from_mapping(state), project, client=_pinned_client(project)
    )


def _pinned_client(project, backend=None):
    cfg, _error = decision.DecisionConfig.from_project(project)
    snapshot = decision.credential_snapshot(cfg)
    return decision.DecisionClient(
        cfg=cfg,
        backend=backend or decision.FakeBackend([_ok(DP4_ANSWERS)]),
        project_root=project,
        credential_snapshot=snapshot,
    )


# ---------------------------------------------------------------------------
# 3. De-duplication, concurrency and retries
# ---------------------------------------------------------------------------


def test_the_same_submit_id_never_spends_a_second_call(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP4_ANSWERS)
    book = _book(DP4, _dp4_state())

    first = _submit(playground, DP4, book, "sub-dup-1")
    second = _submit(playground, DP4, book, "sub-dup-1")

    assert first["state"] == "succeeded"
    assert second["duplicate"] is True
    assert second["state"] == "succeeded"
    assert second["decision_id"] == first["decision_id"]
    assert backends.calls == 1, "a duplicate submit_id must not reach the backend"
    assert len(_of_kind(project, "submission-start")) == 1
    assert len(_of_kind(project, "submission-end")) == 1


def test_a_retry_uses_a_new_id_and_keeps_the_explicit_link(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP4_ANSWERS)
    book = _book(DP4, _dp4_state())

    first = _submit(playground, DP4, book, "sub-retry-1")
    second = _submit(playground, DP4, book, "sub-retry-2", retry_of="sub-retry-1")

    assert first["state"] == "succeeded"
    assert second["state"] == "succeeded"
    assert second["retry_of"] == "sub-retry-1"
    assert second["decision_id"] != first["decision_id"]
    assert backends.calls == 2
    starts = _of_kind(project, "submission-start")
    assert [row["submission_id"] for row in starts] == ["sub-retry-1", "sub-retry-2"]
    assert starts[1]["retry_of"] == "sub-retry-1"


def test_an_unknown_retry_of_is_refused_without_a_call(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP4_ANSWERS)

    result = _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-retry-x",
                     retry_of="never-submitted")

    assert result["state"] == "rejected"
    assert result["accepted"] is False
    assert result["zero_call"] is True
    assert any("retry_of" in issue["path"] for issue in result["issues"])
    assert backends.created == []


def test_one_execution_and_zero_queue_reports_busy(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    started = threading.Event()
    release = threading.Event()

    class _BlockingBackend:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def decide(self, state, questions, cfg):
            self.calls.append({"state": state})
            started.set()
            assert release.wait(20), "the blocked submission must not hang the test"
            return _ok(DP4_ANSWERS)

    def factory(cfg):
        return _BlockingBackend()

    playground, backends = _playground(project, factory=factory)
    book = _book(DP4, _dp4_state())
    first_result: dict = {}

    def run_first() -> None:
        first_result.update(_submit(playground, DP4, book, "sub-busy-1"))

    worker = threading.Thread(target=run_first, daemon=True)
    worker.start()
    try:
        assert started.wait(20), "the first submission never reached the backend"
        busy = _submit(playground, DP4, book, "sub-busy-2")
        assert busy["state"] == "busy"
        assert busy["busy"] is True
        assert busy["accepted"] is False
        assert busy["zero_call"] is True
        assert len(backends.created) == 1, "the busy submission created no backend"
    finally:
        release.set()
        worker.join(20)

    assert first_result["state"] == "succeeded"
    starts = _of_kind(project, "submission-start")
    assert [row["submission_id"] for row in starts] == ["sub-busy-1"], "zero queue"


# ---------------------------------------------------------------------------
# 4. Honest failures: start write, invalid material, transport, record failure
# ---------------------------------------------------------------------------


def test_a_failed_submission_start_sends_nothing(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP4_ANSWERS)
    real_record = decision_wire.record_event

    def record(scope, kind, **kwargs):
        if kind == "submission-start":
            return decision_wire.WriteResult(status="failed", error_class="append")
        return real_record(scope, kind, **kwargs)

    monkeypatch.setattr(decision_wire, "record_event", record)

    result = _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-start-fail")

    assert result["state"] == "record-failed"
    assert result["zero_call"] is True
    assert result["record_status"] == "failed"
    assert backends.created == [], "no model call may happen when the start row is unwritable"
    assert _of_kind(project, "submission-end") == []


def test_invalid_material_is_refused_before_the_model(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP4_ANSWERS)
    book = _book(DP4, _dp4_state(undeclared_fact="x"))

    result = _submit(playground, DP4, book, "sub-invalid-1")

    assert result["state"] == "rejected"
    assert result["zero_call"] is True
    assert result["issues"], "the refusal must carry explicit issues"
    assert result["decision_id"] == f"{DP4}:sub-invalid-1"
    assert result["decision_ran"] is False
    assert backends.created == []
    assert _of_kind(project, "book-snapshot") == []
    starts = _of_kind(project, "submission-start")
    ends = _of_kind(project, "submission-end")
    assert starts and starts[0]["outcome"] == "started"
    assert ends and ends[0]["outcome"] == "rejected"
    assert ends[0]["zero_call"] is True
    assert any("state.undeclared_fact" in line for line in ends[0]["issues"]), (
        "the recorded refusal detail names the refused path"
    )


def test_a_missing_transport_config_is_an_explicit_unavailable(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    # No .mw/decide.json: the global transport switch stays off.
    playground, backends = _playground(project, answers=DP4_ANSWERS)

    result = _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-noconfig-1")

    assert result["state"] == "unavailable"
    assert result["zero_call"] is True
    assert result["outcome"]["escalated_reason"] == "unavailable"
    assert backends.created == []


def test_an_upstream_failure_is_reported_as_failed_not_success(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    timeout = decision.BackendOutcome(
        available=False,
        reason="timeout",
        retryable=False,
        answers=None,
        latency_ms=20,
        detail="upstream timed out",
    )
    playground, backends = _playground(project, results=[timeout])

    result = _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-timeout-1")

    assert result["state"] == "failed"
    assert result["zero_call"] is False
    assert result["outcome"]["status"] == "escalated"
    assert result["outcome"]["transport_reason"] == "timeout"
    assert result["outcome"]["answer"] is None
    assert backends.calls == 1


def test_an_unusable_answer_is_not_a_simulated_success(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, _ = _playground(project, results=[_ok({"failure_action": {"value": "nope"}})])

    result = _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-useless-1")

    assert result["state"] == "failed"
    assert result["zero_call"] is False
    assert result["outcome"]["escalated_reason"] == "low-confidence"
    assert result["outcome"]["answer"] is None


def test_a_failed_end_row_is_record_failed_not_fabricated_success(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP4_ANSWERS)
    real_record = decision_wire.record_event

    def record(scope, kind, **kwargs):
        if kind == "submission-end":
            return decision_wire.WriteResult(status="failed", error_class="append")
        return real_record(scope, kind, **kwargs)

    monkeypatch.setattr(decision_wire, "record_event", record)

    result = _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-end-fail")

    assert result["state"] == "record-failed"
    assert result["record_status"] == "failed"
    assert result["outcome"]["status"] == "suggested", "the real outcome is still reported"
    assert backends.calls == 1, "the call really happened; the record did not"
    assert _of_kind(project, "submission-end") == []


# ---------------------------------------------------------------------------
# 5. Polling / history never spend a call, and read the isolated ledger
# ---------------------------------------------------------------------------


def test_polling_and_history_never_spend_a_call(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP4_ANSWERS)
    submitted = _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-poll-1")
    assert backends.calls == 1

    for _ in range(3):
        polled = playground.submission("sub-poll-1")
        assert polled is not None
        assert polled["state"] == "succeeded"
        assert polled["submission_id"] == "sub-poll-1"

    history = playground.history()
    assert history["total"] == 1
    assert [record["submission_id"] for record in history["records"]] == ["sub-poll-1"]
    assert history["records"][0]["dp"] == DP4
    assert backends.calls == 1, "polling must never reach the decision chain"
    assert playground.submission("no-such-submission") is None
    assert submitted["state"] == "succeeded"


def test_history_covers_every_submission_and_stays_in_the_test_scope(
    tmp_path: pathlib.Path,
) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, _ = _playground(project, answers=DP4_ANSWERS)

    _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-hist-1")
    _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-hist-2",
            retry_of="sub-hist-1")

    history = playground.history()
    assert history["total"] == 2
    by_id = {record["submission_id"]: record for record in history["records"]}
    assert set(by_id) == {"sub-hist-1", "sub-hist-2"}
    assert by_id["sub-hist-2"]["retry_of"] == "sub-hist-1"
    assert all(record["state"] == "succeeded" for record in by_id.values())
    assert history["source"] == "test"
    assert all(record["scope"] == "test" for record in history["records"])


# ---------------------------------------------------------------------------
# 6. T10b N2: execution/authorization smuggling inside declared object subtrees
# ---------------------------------------------------------------------------


def test_object_subtree_smuggling_is_refused_with_zero_calls(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP1_ANSWERS)
    book = _book(DP1, _dp1_state(history={"recent_done": 2, "act": True}))

    report = playground.validate(DP1, book)
    assert report["ok"] is False
    assert any(
        issue["code"] == "forbidden-field" and issue["path"].endswith("history.act")
        for issue in report["issues"]
    ), report["issues"]

    result = _submit(playground, DP1, book, "sub-smuggle-1")
    assert result["state"] == "rejected"
    assert result["zero_call"] is True
    assert backends.created == []


def test_nested_object_smuggling_inside_array_items_is_refused(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP1_ANSWERS)
    state = _dp2_state()
    state["progress"]["trend"] = [
        {"elapsed_minutes": 1, "reads": 2, "writes": 3},
        {"elapsed_minutes": 2, "reads": 1, "writes": 0, "executor": "rm -rf"},
    ]

    report = playground.validate(DP2, _book(DP2, state))

    assert report["ok"] is False
    assert any(
        issue["code"] == "forbidden-field" and "progress.trend[1].executor" in issue["path"]
        for issue in report["issues"]
    ), report["issues"]
    assert backends.created == []


def test_legitimate_object_business_data_is_not_refused(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP1_ANSWERS)

    dp1_book = _book(
        DP1,
        _dp1_state(history={"recent_done": 3, "recent_failed": 1, "images_required": False}),
    )
    assert playground.validate(DP1, dp1_book)["ok"] is True, playground.validate(DP1, dp1_book)
    submitted = _submit(playground, DP1, dp1_book, "sub-legit-1")
    assert submitted["state"] == "succeeded", submitted
    assert backends.calls == 1

    dp2_state = _dp2_state()
    dp2_state["progress"]["trend"] = [
        {"elapsed_minutes": 1, "reads": 2, "writes": 3},
        {"elapsed_minutes": 2, "reads": 4, "writes": 5},
    ]
    report = playground.validate(DP2, _book(DP2, dp2_state))
    assert report["ok"] is True, report["issues"]


def test_the_smuggling_vocabulary_covers_the_monitor_seam() -> None:
    assert set(decision_monitor.FORBIDDEN_KEYS) <= set(decision_playground.EXECUTION_KEYS)


def test_a_request_carrying_execution_fields_is_refused_without_a_call(
    tmp_path: pathlib.Path,
) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP4_ANSWERS)
    book = _book(DP4, _dp4_state())

    for extra in ({"act": True}, {"executor": "run"}, {"observe_only": False}):
        request = {"dp": DP4, "book": book, "submit_id": "sub-act-1", "observe_only": True}
        request.update(extra)
        result = playground.submit(request)
        assert result["state"] == "rejected", extra
        assert result["accepted"] is False
        assert result["zero_call"] is True
        assert result["record_status"] == "not-recorded"

    assert backends.created == []
    assert _test_events(project) == [], "a refused request writes no submission"


def test_a_book_with_a_top_level_authority_field_is_refused(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP4_ANSWERS)
    book = _book(DP4, _dp4_state())
    book["authority"] = "human"

    result = _submit(playground, DP4, book, "sub-authority-1")

    assert result["state"] == "rejected"
    assert result["zero_call"] is True
    assert backends.created == []
    assert any("book-schema" == issue["code"] for issue in result["issues"])


def test_a_p0_dp_observation_sends_while_its_production_path_is_disabled(
    tmp_path: pathlib.Path,
) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(
        project, answers={"goal_decision": {"value": "keep", "confidence": 0.9}}
    )
    state = {
        "schema_version": 2,
        "decision_point": "dp16-goal",
        "goal": {
            "current_digest": "sha256:abc123",
            "proposed_delta": "add the ledger isolation acceptance line",
            "alignment": "aligned",
        },
    }

    observation = _submit(playground, "dp16-goal", _book("dp16-goal", state), "sub-p0-1")

    assert observation["state"] == "succeeded", observation
    assert observation["outcome"]["observation"]["bypassed"] is True
    assert observation["outcome"]["preview"]["would_act"] is False
    assert backends.calls == 1

    production = dpts.decide_for(
        "dp16-goal",
        dpts.Trigger.from_mapping(state),
        project,
        client=_pinned_client(project),
    )
    assert production.escalated_reason == "disabled"
    assert backends.calls == 1, "a P0 dp keeps its production gate"


def test_dp25_empty_p0_open_is_a_legal_value(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, _ = _playground(project)
    state = {
        "schema_version": 2,
        "decision_point": "dp25-signoff-conclusion",
        "key": "k-t06",
        "rows_total": 3,
        "rows_available": 3,
        "chain_ok": True,
        "p0_open": [],
    }

    report = playground.validate("dp25-signoff-conclusion", _book("dp25-signoff-conclusion", state))

    assert report["ok"] is True, report["issues"]


def test_a_refused_secret_never_reaches_the_test_ledger(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP4_ANSWERS)
    book = _book(DP4, _dp4_state())
    book["state"]["failure"]["kind"] = TEST_SECRET

    result = _submit(playground, DP4, book, "sub-secret-1")

    assert result["state"] == "rejected"
    assert backends.created == []
    test_root = project / decision_playground.TEST_ROOT_RELATIVE_PATH
    text = decision_wire.test_wire_sink(test_root).read_text(encoding="utf-8")
    assert TEST_SECRET not in text
    assert TEST_SECRET not in json.dumps(result)


def test_each_submission_keeps_its_own_call_rows(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, _ = _playground(project, answers=DP4_ANSWERS)

    _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-call-1")
    _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-call-2")

    calls = [event for event in _of_kind(project, "call-end")]
    decisions = _of_kind(project, "decision-end")
    assert len(calls) == 2, "one logical call row per submission (no dedup loss)"
    assert len(decisions) == 2
    assert len({event["call_id"] for event in calls}) == 2
    assert {event["submission_id"] for event in calls} == {"sub-call-1", "sub-call-2"}


def test_polling_reports_the_recorded_call_and_book_facts(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, _ = _playground(project, answers=DP4_ANSWERS)
    _submit(playground, DP4, _book(DP4, _dp4_state()), "sub-facts-1")

    polled = playground.submission("sub-facts-1")
    assert polled is not None
    assert polled["decision_id"] == f"{DP4}:sub-facts-1"
    assert polled["decision_ran"] is True
    assert isinstance(polled["book_ref"], str) and polled["book_ref"].startswith("book-")
    assert polled["zero_call"] is False
    assert isinstance(polled["call_id"], str) and polled["call_id"]
    assert polled["outcome"]["status"] == "suggested"
    assert polled["state"] == "succeeded"


def test_an_oversized_send_state_is_refused_instead_of_truncated(
    tmp_path: pathlib.Path,
) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP1_ANSWERS)
    book = _book(DP1, _dp1_state(history={"recent_done": 3, "note": "x" * 2500}))

    report = playground.validate(DP1, book)

    assert report["ok"] is False
    assert report["state_bytes"] > dpts.MAX_STATE_BYTES
    assert any(issue["code"] == "book-budget" for issue in report["issues"])
    result = _submit(playground, DP1, book, "sub-oversize-1")
    assert result["state"] == "rejected"
    assert result["zero_call"] is True
    assert backends.created == []


# ---------------------------------------------------------------------------
# 7. Same review for validate and submit, and the context contract
# ---------------------------------------------------------------------------


def test_validate_and_submit_share_one_review(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, backends = _playground(project, answers=DP4_ANSWERS)

    legal = _book(DP4, _dp4_state())
    assert playground.validate(DP4, legal)["ok"] is True
    assert _submit(playground, DP4, legal, "sub-same-1")["state"] == "succeeded"

    placeholder = playground.scaffold(DP4)["book"]
    assert playground.validate(DP4, placeholder)["ok"] is False
    assert _submit(playground, DP4, placeholder, "sub-same-2")["state"] == "rejected"
    assert backends.calls == 1


def test_a_used_context_slot_is_validated_but_not_sent(tmp_path: pathlib.Path) -> None:
    project = _make_control(tmp_path)
    _write_decide_config(project)
    playground, _ = _playground(project, answers=DP4_ANSWERS)
    book = _book(
        DP4,
        _dp4_state(),
        context={"error_excerpt": "worker-3: pytest exited 1"},
    )
    book["notes"]["evidence"]["context.error_excerpt"] = "cmd: true"

    report = playground.validate(DP4, book)

    assert report["ok"] is True, report["issues"]
    assert report["context_slots"] == ["error_excerpt"]
    assert report["context_sent"] is False
    assert report["context_note"]
