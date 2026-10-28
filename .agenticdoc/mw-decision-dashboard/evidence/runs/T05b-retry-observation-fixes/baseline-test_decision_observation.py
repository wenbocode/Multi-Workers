"""test_decision_observation.py — card T05: internal observation seam.

The observe-only channel (``mw decide monitor`` / DP playground, card T06) must
reuse the production decision chain without being able to spend it:

* ``decide_for(observation=...)`` is a *paired* contract: ``intent="answer"``
  and ``archive=False`` are mandatory, the capture scope must be an explicit
  isolated ``test`` scope with its own ``evidence_path``; any other combination
  raises ``DecisionInputError`` before a state is built or a backend is touched;
* only the per-DP authorization gate (``.mw/decide-points.json`` enabled/P0)
  is bypassed.  Global transport disabled/unconfigured, missing credentials, an
  incomplete/oversized state and the answer check keep refusing with zero
  requests, exactly like production;
* the executor is never invoked, and the shared pure authorization preview
  reports what production *would* do (``would_act`` is a capability label, not
  an execution claim: ``executor_invoked=false`` / ``action_outcome=unknown``);
* the per-call material is snapshotted (book or input-state + the rendered
  candidate enum) into the side ledger through the injected redactor, so a
  stored ``state_digest`` alone never has to be "reconstructed" later; the
  snapshot is labelled ``book``/``input-state`` and never pretends to be the
  other one;
* ``decision-end`` carries the archive signal (created/replayed/skipped/failed/
  unknown/not-attempted) and a ``call_id`` join to the real ``call-end``; the
  client's ``call-end`` is not duplicated here, and a ``zero_call`` row never
  claims a real HTTP call.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).parent))  # noqa: E402

import decision  # noqa: E402
import decision_book as books  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire  # noqa: E402

CRED_ENV_VARS = (
    "TIMI_API_KEY",
    "TYPESAFE_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "TIMI_API_TOKEN",
)

DP3 = "dp3-worker-clarify"
DP4 = "dp4-failure-handling"
DP5 = "dp5-test-triage"
DP25 = "dp25-signoff-conclusion"

TEST_SECRET = "sk-t05-observation-0123456789abcdef"


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch: pytest.MonkeyPatch):
    for name in CRED_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    dpts.clear_points_config_cache()
    yield
    dpts.clear_points_config_cache()


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
        json.dumps({"version": 1, "points": points}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    dpts.clear_points_config_cache()
    return path


def _dp3_state(**overrides) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP3,
        "key": "k-obs",
        "phase": "EXECUTE",
        "task_type": "coding",
        "risk": "low",
        "risk_source": "machine",
        "authority_tier": "P2",
        "task_summary": "worker asks which file holds the decide points",
        "ambiguity": {"kind": "fact", "question": "which file holds the decide points?"},
        "local_candidates": [{"id": "c1", "label": ".mw/decide-points.json"}],
    }
    state.update(overrides)
    return state


def _dp4_state(**overrides) -> dict:
    """A legal dp4 state (identity + the four declared failure facts).

    No ``key``: dp4's registry contract does not declare it, so adding one is
    exactly the undeclared-key case the closed-key gate must refuse.
    """
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


def _dp5_state(**overrides) -> dict:
    state: dict = {
        "schema_version": 2,
        "decision_point": DP5,
        "test": {
            "failed_cases": ["case_a"],
            "baseline_cases": ["case_b"],
            "changed_paths": ["packages/multi-workers/x.py"],
            "repro_consistent": True,
        },
    }
    state.update(overrides)
    return state


def _legal_book(dp_id: str, state: dict) -> dict:
    """A book that ``decision_book.check_book`` accepts unchanged.

    The state carries the identity keys the builder writes for every dp and the
    evidence map covers every required path (``cmd:`` references need no file),
    so the only remaining question is the sent-state join.
    """
    payload = dict(state)
    payload.setdefault("questions_version", dpts.get_decision_point(dp_id).questions_version)
    payload.setdefault("schema_version", 2)
    payload.setdefault("decision_point", dp_id)
    evidence = {path: "cmd: true" for path in dpts.REQUIRED_STATE_FIELDS[dp_id]}
    return {
        "schema_version": books.BOOK_SCHEMA_VERSION,
        "decision_point": dp_id,
        "state": payload,
        "notes": {"evidence": evidence},
    }


def _enable_all(project: pathlib.Path) -> pathlib.Path:
    """Authorize every registered dp so only the gate under test can refuse."""
    return _write_points(
        project,
        {
            point.id: {"tier": point.tier, "enabled": True, "mode": "auto"}
            for point in dpts.DP_REGISTRY
        },
    )


def _dp3_answers() -> dict:
    return {
        "answer_kind": {"value": "fact", "confidence": 0.9},
        "answerable": {"value": 0.9},
        "candidate": {"value": "c1", "confidence": 0.9},
    }


def _dp25_state() -> dict:
    return {
        "schema_version": 2,
        "decision_point": DP25,
        "key": "k-obs",
        "rows_total": 3,
        "rows_available": 3,
        "chain_ok": True,
        "p0_open": [],
    }


def _dp25_answers() -> dict:
    return {"q-conclusion": {"value": "continue", "confidence": 0.9}}


def _ok(answers: dict) -> decision.BackendOutcome:
    return decision.BackendOutcome(
        available=True,
        reason=None,
        retryable=False,
        answers=answers,
        latency_ms=2,
        detail="",
    )


def _client(backend, *, wire_scope=None, evidence_path=None) -> decision.DecisionClient:
    return decision.DecisionClient(
        cfg=decision.DecisionConfig(enabled=True),
        backend=backend,
        wire_scope=wire_scope,
        evidence_path=evidence_path,
    )


def _redactor(extra: tuple[str, ...] = (TEST_SECRET,)) -> object:
    redactor = decision.credential_redactor(
        extra_secrets=extra, env={}, auth_path=pathlib.Path("no-such-auth.json")
    )
    assert redactor is not None, "the side ledger module must be importable in tests"
    return redactor


def _test_scope(root: pathlib.Path, *, submission_id: str = "sub-t05", redact=None):
    return decision_wire.test_scope(
        root,
        project_id=decision_wire.project_id_for(root),
        submission_id=submission_id,
        redact=_redactor() if redact is None else redact,
        evidence_path=root / "evidence.jsonl",
        warn=lambda line: None,
    )


def _observation(scope, *, book: dict | None = None, submission_id: str | None = "sub-t05"):
    return dpts.Observation(scope=scope, book=book, submission_id=submission_id)


def _production_decisions(project: pathlib.Path) -> pathlib.Path:
    return project / dpts.DECISIONS_RELATIVE_PATH


def _production_wire(project: pathlib.Path) -> pathlib.Path:
    return decision_wire.production_wire_sink(project)


def _rows(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _events(path: pathlib.Path) -> list[dict]:
    return list(decision_wire.read_events(path).events)


def _of_kind(path: pathlib.Path, kind: str) -> list[dict]:
    return [event for event in _events(path) if event.get("kind") == kind]


def _snapshot_body(event: dict) -> dict:
    text = (event.get("book") or {}).get("text")
    assert isinstance(text, str) and text, f"no snapshot text in {event}"
    return json.loads(text)


def _tree(path: pathlib.Path) -> dict[str, str]:
    """Every file under ``path`` as ``relative posix path -> sha256``."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for item in sorted(path.rglob("*")):
        if item.is_file():
            out[item.relative_to(path).as_posix()] = hashlib.sha256(
                item.read_bytes()
            ).hexdigest()
    return out


def _all_text(path: pathlib.Path) -> str:
    chunks: list[str] = []
    for item in sorted(path.rglob("*")):
        if item.is_file():
            chunks.append(item.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


# ---------------------------------------------------------------------------
# 1. The paired observation contract (fail-closed before any work)
# ---------------------------------------------------------------------------


def test_observation_requires_answer_intent(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = _client(backend, wire_scope=scope)
    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(),
            project,
            client=client,
            archive=False,
            intent="act",
            observation=_observation(scope),
        )
    assert "intent" in str(excinfo.value)
    assert backend.calls == []
    assert _events(decision_wire.test_wire_sink(test_root)) == []


def test_observation_requires_archive_false(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = _client(backend, wire_scope=scope)
    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(),
            project,
            client=client,
            archive=True,
            intent="answer",
            observation=_observation(scope),
        )
    assert "archive" in str(excinfo.value)
    assert backend.calls == []
    assert not _production_decisions(project).exists()


def test_observation_requires_an_isolated_test_scope(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    production = decision_wire.production_scope(project, redact=_redactor(), warn=lambda line: None)
    client = _client(backend, wire_scope=production)
    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(),
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=_observation(production),
        )
    assert "test" in str(excinfo.value)
    assert backend.calls == []
    assert not _production_wire(project).exists()


def test_observation_requires_an_explicit_evidence_path(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    test_root = tmp_path / "test-run"
    scope = decision_wire.WireScope(
        sink=decision_wire.test_wire_sink(test_root),
        project_id="pid",
        scope_kind="test",
        submission_id="sub-t05",
        redact=_redactor(),
        evidence_path=None,
        warn=lambda line: None,
    )
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = _client(backend, wire_scope=scope)
    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(),
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=_observation(scope),
        )
    assert "evidence" in str(excinfo.value)
    assert backend.calls == []


def test_observe_only_must_stay_true(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    scope = _test_scope(tmp_path / "test-run")
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = _client(backend, wire_scope=scope)
    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(),
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=dpts.Observation(scope=scope, observe_only=False),
        )
    assert "observe_only" in str(excinfo.value)
    assert backend.calls == []


def test_observation_scope_must_be_the_client_scope(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    other = _test_scope(tmp_path / "test-run-b")
    client = _client(decision.FakeBackend([_ok(_dp3_answers())]), wire_scope=other)
    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(),
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=_observation(_test_scope(tmp_path / "test-run-a")),
        )
    assert "scope" in str(excinfo.value)


# ---------------------------------------------------------------------------
# 2. Only the per-DP gate is bypassed; everything else keeps refusing
# ---------------------------------------------------------------------------


def test_disabled_dp_observation_bypasses_only_the_dp_gate(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    points_path = _write_points(
        project, {DP3: {"tier": "P2", "enabled": False, "mode": "auto"}}
    )
    before = _tree(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = _client(backend, wire_scope=scope)

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    assert outcome.status == "suggested", outcome.detail
    assert outcome.escalated_reason is None
    assert outcome.answer is not None
    assert len(backend.calls) == 1, "a disabled DP is the one gate an observation bypasses"
    assert outcome.observation is not None
    assert outcome.observation["bypassed"] is True
    assert outcome.observation["observe_only"] is True
    assert outcome.observation["submission_id"] == "sub-t05"
    assert outcome.capture_channel == "test-scope"
    assert outcome.archive_state == "skipped"

    # production authority/config/ledgers are byte-identical
    assert _tree(project) == before
    assert not _production_decisions(project).exists()
    assert not (project / ".agenticdoc" / "_autopilot" / "book-receipts.jsonl").exists()
    assert points_path.exists()

    ledger = decision_wire.test_wire_sink(test_root)
    ends = _of_kind(ledger, "decision-end")
    assert len(ends) == 1
    end = ends[0]
    assert end["status"] == "suggested"
    assert end["archive"] == "skipped"
    assert end["intent"] == "answer"
    assert end["scope"] == "test"
    assert end["submission_id"] == "sub-t05"
    assert end["actor"] == {"kind": "human", "id": "user-explicit"}


def test_production_path_of_the_same_disabled_dp_still_sends_nothing(
    tmp_path: pathlib.Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": False, "mode": "auto"}})
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = _client(backend)

    outcome = dpts.decide_for(
        DP3, _dp3_state(), project, client=client, archive=True, intent="answer"
    )

    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "disabled"
    assert backend.calls == []
    assert outcome.observation is None
    assert outcome.capture_channel == "no-scope"
    assert not _production_decisions(project).exists()
    assert not _production_wire(project).exists()


def test_observation_keeps_the_global_transport_switch(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project, enabled=False)
    _write_points(project, {DP3: {"tier": "P2", "enabled": False, "mode": "auto"}})
    before = _tree(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = decision.DecisionClient(
        cfg=decision.DecisionConfig.from_project(project)[0],
        backend=backend,
        wire_scope=scope,
        evidence_path=test_root / "evidence.jsonl",
    )

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "unavailable"
    assert backend.calls == [], "the global kill switch is not an observation exception"
    assert _tree(project) == before
    ends = _of_kind(decision_wire.test_wire_sink(test_root), "decision-end")
    assert len(ends) == 1
    assert ends[0]["archive"] == "not-attempted"
    assert ends[0]["escalated_reason"] == "unavailable"


def test_observation_input_incomplete_sends_nothing(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP4: {"tier": "P1", "enabled": False, "mode": "auto"}})
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok({"failure_action": {"value": "retry"}})])
    client = _client(backend, wire_scope=scope)

    outcome = dpts.decide_for(
        DP4,
        {"key": "k-obs"},
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "input-incomplete"
    assert backend.calls == []
    assert outcome.observation["bypassed"] is True


# ---------------------------------------------------------------------------
# 3. Capture module availability is an explicit channel, never a fallback
# ---------------------------------------------------------------------------


def _break_wire(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(decision, "_WIRE_LOADED", True)
    monkeypatch.setattr(decision, "_WIRE_MODULE", None)


def test_observation_refuses_when_the_capture_module_is_unavailable(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    scope = _test_scope(tmp_path / "test-run")
    client = _client(backend, wire_scope=scope)
    _break_wire(monkeypatch)

    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(),
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=_observation(scope),
        )
    assert "capture" in str(excinfo.value)
    assert backend.calls == [], "no fallback to an unwatched production path"
    assert not _production_wire(project).exists()


def test_observation_refuses_a_broken_capture_module(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An importable module without the seam API is broken, not "absent"."""

    class BrokenWire:
        production_scope = None

    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    scope = _test_scope(tmp_path / "test-run")
    client = _client(backend, wire_scope=scope)
    monkeypatch.setattr(decision, "_WIRE_LOADED", True)
    monkeypatch.setattr(decision, "_WIRE_MODULE", BrokenWire())

    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(),
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=_observation(scope),
        )
    assert "capture" in str(excinfo.value)
    assert backend.calls == []


def test_production_keeps_the_business_result_when_capture_is_unavailable(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": True, "mode": "suggest"}})
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = _client(backend)
    _break_wire(monkeypatch)

    outcome = dpts.decide_for(
        DP3, _dp3_state(), project, client=client, archive=False, intent="answer"
    )

    assert outcome.status == "suggested", "capture never changes the decision"
    assert outcome.capture_status == "failed"
    assert outcome.capture_channel == "module-unavailable"
    assert not _production_wire(project).exists()


# ---------------------------------------------------------------------------
# 4. decision-end archive signal, preserving the original exception
# ---------------------------------------------------------------------------


def test_decision_end_reports_created_replayed_and_skipped(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": True, "mode": "suggest"}})
    client = _client(decision.FakeBackend([_ok(_dp3_answers())]))

    first = dpts.decide_for(DP3, _dp3_state(), project, client=client, intent="answer")
    second = dpts.decide_for(DP3, _dp3_state(), project, client=client, intent="answer")
    skipped = dpts.decide_for(
        DP3, _dp3_state(), project, client=client, intent="answer", archive=False
    )

    assert (first.archive_state, second.archive_state, skipped.archive_state) == (
        "created",
        "replayed",
        "skipped",
    )
    ends = _of_kind(_production_wire(project), "decision-end")
    assert [end["archive"] for end in ends] == ["created", "replayed", "skipped"]
    assert len(_rows(_production_decisions(project))) == 1, "the replay wrote no new row"


def test_archive_failure_is_recorded_then_the_original_exception_escapes(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": True, "mode": "suggest"}})
    boom = RuntimeError("archive exploded")

    def writer(**kwargs):
        raise boom

    monkeypatch.setattr(dpts, "ARCHIVE_WRITER", writer, raising=False)
    client = _client(decision.FakeBackend([_ok(_dp3_answers())]))

    with pytest.raises(RuntimeError) as excinfo:
        dpts.decide_for(DP3, _dp3_state(), project, client=client, intent="answer")
    assert excinfo.value is boom, "the archive exception must not be replaced"

    ends = _of_kind(_production_wire(project), "decision-end")
    assert len(ends) == 1
    assert ends[0]["archive"] == "failed"
    assert ends[0]["status"] is None, (
        "the decision's own outcome was never returned; only the archive failed"
    )
    assert ends[0]["state_digest"], "the input material was already known"


def test_unavailable_archive_writer_reports_unknown(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": True, "mode": "suggest"}})
    monkeypatch.setattr(dpts, "_resolve_archive_writer", lambda: None)
    client = _client(decision.FakeBackend([_ok(_dp3_answers())]))

    outcome = dpts.decide_for(DP3, _dp3_state(), project, client=client, intent="answer")

    assert outcome.archived is False
    assert outcome.archive_state == "unknown"
    assert _of_kind(_production_wire(project), "decision-end")[0]["archive"] == "unknown"


# ---------------------------------------------------------------------------
# 5. Per-call material snapshot (book or input-state + rendered candidates)
# ---------------------------------------------------------------------------


def test_book_snapshot_is_labelled_book_and_keeps_the_sent_state(
    tmp_path: pathlib.Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": False, "mode": "auto"}})
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    client = _client(decision.FakeBackend([_ok(_dp3_answers())]), wire_scope=scope)
    # A legal complete book: every required field carries evidence, so the only
    # reason it can be refused is the sent-state join (T05b F2).
    book = _legal_book(DP3, _dp3_state())

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope, book=book),
    )

    snaps = _of_kind(decision_wire.test_wire_sink(test_root), "book-snapshot")
    assert len(snaps) == 1
    snapshot = snaps[0]
    body = _snapshot_body(snapshot)
    assert body["kind"] == "book"
    assert body["decision_id"] == outcome.decision_id
    assert body["questions_version"] == dpts.get_decision_point(DP3).questions_version
    assert body["state"]["task_summary"] == _dp3_state()["task_summary"]
    assert body["candidates"]["candidate"] == [{"id": "c1", "label": ".mw/decide-points.json"}]
    assert snapshot["book_ref"] == outcome.snapshot_ref
    assert str(snapshot["book_ref"]).startswith("book-")
    assert snapshot["book_version"] == "input-memory"
    assert snapshot["file_sha256"] is None
    assert snapshot["book"]["byte_exact"] is True
    assert body["state"]["questions_version"] == dpts.get_decision_point(DP3).questions_version

    end = _of_kind(decision_wire.test_wire_sink(test_root), "decision-end")[0]
    assert end["book_ref"] == snapshot["book_ref"]


def test_input_state_snapshot_records_the_rendered_candidates(
    tmp_path: pathlib.Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": False, "mode": "auto"}})
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    client = _client(decision.FakeBackend([_ok(_dp3_answers())]), wire_scope=scope)

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    snapshot = _of_kind(decision_wire.test_wire_sink(test_root), "book-snapshot")[0]
    body = _snapshot_body(snapshot)
    assert body["kind"] == "input-state"
    assert str(snapshot["book_ref"]).startswith("state-")
    assert body["candidates"]["candidate"] == [{"id": "c1", "label": ".mw/decide-points.json"}]
    assert body["state_digest"] == outcome.state_digest
    assert body["state"]["local_candidates"][0]["id"] == "c1"


def test_no_snapshot_when_the_decision_never_built_a_state(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project, enabled=False)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    client = decision.DecisionClient(
        cfg=decision.DecisionConfig.from_project(project)[0],
        backend=decision.FakeBackend([]),
        wire_scope=scope,
        evidence_path=test_root / "evidence.jsonl",
    )

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    assert outcome.state_digest is None
    assert outcome.snapshot_ref is None, "a digest alone is never 'restored' as material"
    assert _of_kind(decision_wire.test_wire_sink(test_root), "book-snapshot") == []
    assert _of_kind(decision_wire.test_wire_sink(test_root), "decision-end")[0]["book_ref"] is None


def test_snapshot_free_text_goes_through_the_injected_redactor(
    tmp_path: pathlib.Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": False, "mode": "auto"}})
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    client = _client(decision.FakeBackend([_ok(_dp3_answers())]), wire_scope=scope)
    state = _dp3_state(
        task_summary=f"key is {TEST_SECRET} for the workspace",
        local_candidates=[{"id": "c1", "label": f"{TEST_SECRET}.json"}],
    )

    dpts.decide_for(
        DP3,
        state,
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    sink = decision_wire.test_wire_sink(test_root)
    raw = sink.read_text(encoding="utf-8")
    assert TEST_SECRET not in raw, "the snapshot is free text and must be redacted"
    assert "<redacted>" in raw
    body = _snapshot_body(_of_kind(sink, "book-snapshot")[0])
    assert "<redacted>" in body["state"]["task_summary"]
    assert "<redacted>" in body["candidates"]["candidate"][0]["label"]


def test_fresh_scope_and_redactor_per_production_decision(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": True, "mode": "suggest"}})
    first_secret = "sk-t05-rotate-first-0123456789"
    second_secret = "sk-t05-rotate-second-0123456789"
    monkeypatch.setenv("TIMI_API_KEY", first_secret)
    client = _client(decision.FakeBackend([_ok(_dp3_answers())]))

    dpts.decide_for(
        DP3,
        _dp3_state(task_summary=f"secret {first_secret}"),
        project,
        client=client,
        intent="answer",
    )
    monkeypatch.setenv("TIMI_API_KEY", second_secret)
    dpts.decide_for(
        DP3,
        _dp3_state(task_summary=f"secret {second_secret}"),
        project,
        client=client,
        intent="answer",
    )

    raw = _all_text(project)
    assert first_secret not in raw, "the first credential is still covered"
    assert second_secret not in raw, "the rotated credential needs a fresh redactor"
    bodies = [_snapshot_body(event) for event in _of_kind(_production_wire(project), "book-snapshot")]
    assert len(bodies) == 2
    assert any("<redacted>" in body["state"]["task_summary"] for body in bodies)


# ---------------------------------------------------------------------------
# 6. Call/decision joins and the zero-call distinction
# ---------------------------------------------------------------------------


def test_decision_end_joins_the_real_call_end(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": False, "mode": "auto"}})
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    client = _client(decision.FakeBackend([_ok(_dp3_answers())]), wire_scope=scope)

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    sink = decision_wire.test_wire_sink(test_root)
    calls = _of_kind(sink, "call-end")
    ends = _of_kind(sink, "decision-end")
    assert len(calls) == 1 and len(ends) == 1, "T05 never duplicates the client's call-end"
    assert calls[0]["call_id"] and calls[0]["call_id"] == ends[0]["call_id"]
    assert calls[0]["call_id"] == client.last_call_id == outcome.call_id
    assert calls[0]["zero_call"] is True, (
        "the fake backend makes no POST, so the logical call must say zero_call"
    )
    assert calls[0]["wire_attempts"] == 0
    assert decision_wire.summarize(_events(sink)).attempts == 0


def test_zero_call_client_row_is_not_a_real_http_call(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": True, "mode": "suggest"}})
    # Configured transport, but no backend resolves: the client reports the
    # logical call with zero attempts (design §4.4 `zero_call`).
    client = decision.DecisionClient(
        cfg=decision.DecisionConfig(enabled=True), backend_factory=lambda cfg: None
    )

    outcome = dpts.decide_for(DP3, _dp3_state(), project, client=client, intent="answer")

    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "unavailable"
    sink = _production_wire(project)
    calls = _of_kind(sink, "call-end")
    assert len(calls) == 1 and calls[0]["zero_call"] is True
    assert _of_kind(sink, "attempt-start") == [], "no POST happened, so no attempt row"
    assert decision_wire.summarize(_events(sink)).attempts == 0
    assert _of_kind(sink, "decision-end")[0]["archive"] == "created"


# ---------------------------------------------------------------------------
# 7. Shared pure authorization preview (never an execution claim)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("dp_id", "row", "expected"),
    [
        (DP3, {"enabled": False, "mode": "auto"}, ("escalated", "disabled")),
        (DP3, {"enabled": True, "mode": "auto"}, ("escalated", "over-authority")),
        (DP3, {"enabled": True, "mode": "suggest"}, ("suggested", None)),
        (DP25, {"enabled": True, "mode": "auto"}, ("acted", None)),
    ],
)
def test_preview_matches_the_production_verdict(
    tmp_path: pathlib.Path,
    dp_id: str,
    row: dict,
    expected: tuple[str, str | None],
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {dp_id: {"tier": "P2", **row}})
    state = _dp3_state() if dp_id == DP3 else _dp25_state()
    answers = _dp3_answers() if dp_id == DP3 else _dp25_answers()

    preview = dpts.authorization_preview(dp_id, project)
    outcome = dpts.decide_for(
        dp_id,
        state,
        project,
        client=_client(decision.FakeBackend([_ok(answers)])),
        archive=False,
        intent="act",
    )

    assert (preview["would_status"], preview["would_escalated_reason"]) == expected
    assert (outcome.status, outcome.escalated_reason) == expected
    assert preview["executor_invoked"] is False
    assert preview["action_outcome"] == "unknown"
    assert preview["would_act"] is (expected[0] == "acted")


def test_preview_reports_a_disabled_global_transport(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project, enabled=False)

    preview = dpts.authorization_preview(DP25, project)

    assert preview["transport"] == "unavailable"
    assert preview["would_status"] == "escalated"
    assert preview["would_escalated_reason"] == "unavailable"
    assert preview["would_act"] is False


def test_observation_never_invokes_the_executor(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP25: {"tier": "P2", "enabled": True, "mode": "auto"}})
    calls: list[object] = []

    def spy_executor(answers, trigger):
        calls.append(answers)
        return "signoff:continue"

    point = dpts._REGISTRY_BY_ID[DP25]
    monkeypatch.setitem(
        dpts._REGISTRY_BY_ID, DP25, dataclasses.replace(point, executor=spy_executor)
    )
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    client = _client(decision.FakeBackend([_ok(_dp25_answers())]), wire_scope=scope)

    outcome = dpts.decide_for(
        DP25,
        _dp25_state(),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    assert calls == [], "the executor is never reached on the observation path"
    assert outcome.status == "suggested"
    assert outcome.preview is not None
    assert outcome.preview["executor"] == "wired"
    assert outcome.preview["would_act"] is True
    assert outcome.preview["would_action_label"] == f"executor:{DP25}"
    assert outcome.preview["executor_invoked"] is False
    assert outcome.preview["action_outcome"] == "unknown"
    assert outcome.preview["observe_only_bypass"] is False, (
        "this dp is enabled, so the observation bypassed nothing - yet the wired "
        "executor still never ran"
    )


def test_observation_capture_failure_is_reported(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": False, "mode": "auto"}})
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    client = _client(decision.FakeBackend([_ok(_dp3_answers())]), wire_scope=scope)
    # Make every capture write fail: the sink's parent is a plain file.
    blocker = test_root / "not-a-dir"
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("x", encoding="utf-8")
    scope.sink = blocker / "wire.jsonl"

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    assert outcome.status == "suggested", "capture failure never changes the answer"
    assert outcome.capture_status == "failed"
    assert outcome.capture_channel == "test-scope"

# ---------------------------------------------------------------------------
# 8. The typed input gate runs inside the seam (T05b F1)
#
# F1 of the T05 review: step 5 only checked missing required fields; the typed
# contract (type / enum / array bounds / cross-field / closed key set) was only
# enforced by the book gate, so an observation (and every non-book structured
# `mw decide run`) sent material production would refuse. The gate now runs in
# `decide_for` itself, after the required check and before the budget/transport.
# ---------------------------------------------------------------------------


def _contracts():
    """The T04 legal-state fixture (one authority: the registry itself)."""
    import test_decision_dashboard_contracts as contracts

    return contracts


@pytest.mark.parametrize(
    "dp_id", [point.id for point in dpts.DP_REGISTRY], ids=[point.id for point in dpts.DP_REGISTRY]
)
def test_every_dp_legal_state_passes_the_shared_gate(dp_id: str) -> None:
    state = _contracts().legal_state(dp_id)
    assert dpts.state_field_issues(dp_id, state) == (), dp_id
    assert dpts.state_unknown_key_issues(dp_id, state, allow_context=True) == (), dp_id


@pytest.mark.parametrize(
    "dp_id", [point.id for point in dpts.DP_REGISTRY], ids=[point.id for point in dpts.DP_REGISTRY]
)
def test_every_dp_refuses_a_typed_violation_with_zero_send(
    dp_id: str, tmp_path: pathlib.Path
) -> None:
    contracts = _contracts()
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    identity = set(dpts.STATE_IDENTITY_PATHS)
    business = [path for path in dpts.REQUIRED_STATE_FIELDS[dp_id] if path not in identity]
    assert business, dp_id
    state = contracts.legal_state(dp_id)
    contracts._set_path(state, business[0], {"not": "a legal value"})
    backend = decision.FakeBackend([_ok({})])
    client = _client(backend)

    outcome = dpts.decide_for(dp_id, state, project, client=client, archive=False, intent="answer")

    assert outcome.status == "escalated", dp_id
    assert outcome.escalated_reason == "input-incomplete", (dp_id, outcome.detail)
    assert business[0] in outcome.detail, (dp_id, outcome.detail)
    assert backend.calls == [], f"{dp_id}: illegal material reached the transport"
    assert not _production_decisions(project).exists()


@pytest.mark.parametrize(
    "dp_id", [point.id for point in dpts.DP_REGISTRY], ids=[point.id for point in dpts.DP_REGISTRY]
)
def test_every_dp_refuses_an_undeclared_key_with_zero_send(
    dp_id: str, tmp_path: pathlib.Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    state = _contracts().legal_state(dp_id)
    state["undeclared_business_fact"] = "x"
    backend = decision.FakeBackend([_ok({})])
    client = _client(backend)

    outcome = dpts.decide_for(dp_id, state, project, client=client, archive=False, intent="answer")

    assert outcome.status == "escalated", dp_id
    assert outcome.escalated_reason == "input-incomplete", (dp_id, outcome.detail)
    assert "undeclared_business_fact" in outcome.detail, (dp_id, outcome.detail)
    assert backend.calls == [], f"{dp_id}: an undeclared key reached the transport"


def test_production_structured_path_applies_the_same_typed_gate(
    tmp_path: pathlib.Path,
) -> None:
    """The non-book production path must not rely on T06's `check_book`."""

    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    state = _dp4_state()
    state["failure"] = {**state["failure"], "kind": "boom"}
    backend = decision.FakeBackend([_ok({"failure_action": {"value": "retry"}})])
    client = _client(backend)

    outcome = dpts.decide_for(DP4, state, project, client=client, intent="answer")

    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "input-incomplete"
    assert "failure.kind" in outcome.detail
    assert backend.calls == []
    assert not _production_decisions(project).exists()
    assert outcome.observation is None


@pytest.mark.parametrize(
    ("state", "expected_path"),
    [
        (_dp4_state(), None),
        (_dp5_state(), None),
    ],
)
def test_observation_refuses_illegal_material_with_zero_send(
    state: dict, expected_path: str | None, tmp_path: pathlib.Path
) -> None:
    """Every defect class is refused in the seam, before the transport."""

    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = _client(backend, wire_scope=scope)
    dp_id = str(state["decision_point"])
    if dp_id == DP4:
        state["failure"] = {**state["failure"], "kind": "boom"}
        expected_path = "failure.kind"
    else:
        state["test"] = {**state["test"], "failed_cases": [1]}
        expected_path = "test.failed_cases"

    outcome = dpts.decide_for(
        dp_id,
        state,
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "input-incomplete"
    assert expected_path is not None and expected_path in outcome.detail, outcome.detail
    assert backend.calls == [], "illegal observation material reached the transport"
    assert outcome.observation["bypassed"] is True
    ends = _of_kind(decision_wire.test_wire_sink(test_root), "decision-end")
    assert len(ends) == 1 and ends[0]["status"] == "escalated"
    assert decision_wire.summarize(_events(decision_wire.test_wire_sink(test_root))).attempts == 0


def test_observation_refuses_an_unknown_business_key(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = _client(backend, wire_scope=scope)
    state = _dp4_state()
    state["failure"] = {**state["failure"], "expected_action": "retry"}

    outcome = dpts.decide_for(
        DP4,
        state,
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    assert outcome.escalated_reason == "input-incomplete"
    assert "failure.expected_action" in outcome.detail, outcome.detail
    assert backend.calls == []


def test_observation_refuses_an_over_limit_array(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok({})])
    client = _client(backend, wire_scope=scope)
    state = _dp5_state()
    state["test"] = {
        **state["test"],
        "failed_cases": [f"case_{index}" for index in range(40)],
    }

    outcome = dpts.decide_for(
        DP5,
        state,
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    assert outcome.escalated_reason == "input-incomplete"
    assert "test.failed_cases" in outcome.detail, outcome.detail
    assert backend.calls == []


def test_observation_refuses_a_cross_field_violation(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok({})])
    client = _client(backend, wire_scope=scope)
    state = _dp4_state()
    state["failure"] = {**state["failure"], "attempt": 5, "limit": 3}

    outcome = dpts.decide_for(
        DP4,
        state,
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    assert outcome.escalated_reason == "input-incomplete"
    assert "failure.attempt" in outcome.detail, outcome.detail
    assert backend.calls == []


def test_illegal_material_is_refused_before_the_budget_gate(tmp_path: pathlib.Path) -> None:
    """A state that is both illegal and oversized is refused as input-incomplete."""

    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    backend = decision.FakeBackend([_ok({})])
    client = _client(backend)
    state = _dp5_state()
    state["test"] = {
        "failed_cases": [f"case_{index}-" + "x" * 200 for index in range(80)],
        "baseline_cases": ["case_b"],
        "changed_paths": ["x"],
        "repro_consistent": True,
    }

    outcome = dpts.decide_for(DP5, state, project, client=client, archive=False, intent="answer")

    assert outcome.escalated_reason == "input-incomplete", outcome.detail
    assert "test.failed_cases" in outcome.detail
    assert backend.calls == []

# ---------------------------------------------------------------------------
# 9. Observation book material (T05b F2)
#
# F2 of the T05 review: a caller-supplied `Observation.book` used to be
# snapshotted as `kind="book"` with no dp check, no book validation and no join
# to the state actually sent. It is now the material-of-record claim: the book
# must belong to this dp, pass `decision_book.check_book` (schema, closed state,
# placeholders, evidence, budget, secrets) and send the state that was sent.
# Any defect refuses the observation before the transport (zero send) and no
# book-labelled snapshot is written.
# ---------------------------------------------------------------------------


def _dp3_observation_call(project: pathlib.Path, scope, backend, *, book):
    return dpts.decide_for(
        DP3,
        _dp3_state(),
        project,
        client=_client(backend, wire_scope=scope),
        archive=False,
        intent="answer",
        observation=_observation(scope, book=book),
    )


def _assert_book_refused(project: pathlib.Path, test_root: pathlib.Path, outcome) -> None:
    assert outcome.status == "escalated"
    assert outcome.escalated_reason == "input-incomplete"
    assert outcome.snapshot_ref is None
    sink = decision_wire.test_wire_sink(test_root)
    assert _of_kind(sink, "book-snapshot") == [], "refused material must not be stored"
    ends = _of_kind(sink, "decision-end")
    assert len(ends) == 1
    assert ends[0]["book_ref"] is None, "no dangling book reference"
    assert not _production_decisions(project).exists()


def test_observation_refuses_a_book_of_another_dp(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    book = _legal_book(DP25, _dp25_state())

    outcome = _dp3_observation_call(project, scope, backend, book=book)

    assert backend.calls == []
    _assert_book_refused(project, test_root, outcome)
    assert "book.decision_point" in outcome.detail, outcome.detail


def test_observation_refuses_an_incomplete_book(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    book = _legal_book(DP3, _dp3_state())
    del book["notes"]["evidence"]["task_summary"]

    outcome = _dp3_observation_call(project, scope, backend, book=book)

    assert backend.calls == []
    _assert_book_refused(project, test_root, outcome)
    assert "book.notes.evidence.task_summary" in outcome.detail, outcome.detail


def test_observation_refuses_a_book_carrying_a_credential(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    state = _dp3_state(task_summary=f"key is {TEST_SECRET} for the workspace")
    book = _legal_book(DP3, state)

    outcome = _dp3_observation_call(project, scope, backend, book=book)

    assert backend.calls == []
    _assert_book_refused(project, test_root, outcome)
    assert "book.state.task_summary" in outcome.detail, outcome.detail
    assert TEST_SECRET not in decision_wire.test_wire_sink(test_root).read_text(encoding="utf-8")


def test_observation_refuses_a_book_whose_state_is_not_the_sent_state(
    tmp_path: pathlib.Path,
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    book = _legal_book(DP3, _dp3_state(task_summary="a different summary entirely"))

    outcome = _dp3_observation_call(project, scope, backend, book=book)

    assert backend.calls == []
    _assert_book_refused(project, test_root, outcome)
    assert "book.state" in outcome.detail, outcome.detail


# ---------------------------------------------------------------------------
# 10. Snapshot references only point at real rows (T05b F4)
# ---------------------------------------------------------------------------


def test_snapshot_reference_is_dropped_when_the_snapshot_write_fails(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": False, "mode": "auto"}})
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    client = _client(decision.FakeBackend([_ok(_dp3_answers())]), wire_scope=scope)
    real_record = decision_wire.record_event

    def record(scope_arg, kind, **kwargs):
        if kind == "book-snapshot":
            return decision_wire.WriteResult(status="failed")
        return real_record(scope_arg, kind, **kwargs)

    monkeypatch.setattr(decision_wire, "record_event", record)

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope, book=_legal_book(DP3, _dp3_state())),
    )

    assert outcome.status == "suggested", "capture never changes the decision"
    assert outcome.capture_status == "failed"
    assert outcome.snapshot_ref is None, "a failed write has no snapshot row to point at"
    sink = decision_wire.test_wire_sink(test_root)
    assert _of_kind(sink, "book-snapshot") == []
    ends = _of_kind(sink, "decision-end")
    assert len(ends) == 1
    assert ends[0]["book_ref"] is None
    assert _dangling_book_refs(sink) == set()


def test_snapshot_reference_is_dropped_when_the_snapshot_write_raises(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _write_points(project, {DP3: {"tier": "P2", "enabled": False, "mode": "auto"}})
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    client = _client(decision.FakeBackend([_ok(_dp3_answers())]), wire_scope=scope)
    real_record = decision_wire.record_event

    def record(scope_arg, kind, **kwargs):
        if kind == "book-snapshot":
            raise OSError("sink vanished")
        return real_record(scope_arg, kind, **kwargs)

    monkeypatch.setattr(decision_wire, "record_event", record)

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=_observation(scope),
    )

    assert outcome.status == "suggested"
    assert outcome.capture_status == "failed"
    assert outcome.snapshot_ref is None
    sink = decision_wire.test_wire_sink(test_root)
    ends = _of_kind(sink, "decision-end")
    assert len(ends) == 1 and ends[0]["book_ref"] is None
    assert _dangling_book_refs(sink) == set()


def _dangling_book_refs(sink: pathlib.Path) -> set[str]:
    """Every ``book_ref`` the ledger claims without a matching snapshot row."""
    events = _events(sink)
    written = {
        event.get("book_ref")
        for event in events
        if event.get("kind") == "book-snapshot" and event.get("book_ref")
    }
    claimed = {
        event.get("book_ref")
        for event in events
        if event.get("kind") == "decision-end" and event.get("book_ref")
    }
    return {ref for ref in claimed if ref not in written}


# ---------------------------------------------------------------------------
# 11. Actor facts use the production closed set (T05b F5)
# ---------------------------------------------------------------------------


def test_actor_kinds_are_the_history_closed_set() -> None:
    import decision_history

    assert dpts.ACTOR_KINDS == decision_history.ACTOR_KINDS
    assert dpts.ACTOR_ID_MAX_BYTES == decision_wire.METADATA_TEXT_LIMIT


@pytest.mark.parametrize("actor_kind", ["robot", "", "HUMAN", None, 7])
def test_observation_refuses_an_illegal_actor_kind(
    actor_kind: object, tmp_path: pathlib.Path
) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = _client(backend, wire_scope=scope)

    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(),
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=dpts.Observation(scope=scope, actor_kind=actor_kind),
        )

    assert "actor_kind" in str(excinfo.value)
    assert backend.calls == []
    assert _events(decision_wire.test_wire_sink(test_root)) == [], "no fact for a refused call"


@pytest.mark.parametrize("actor_id", ["", "   ", "line\nbreak", "x" * 513])
def test_observation_refuses_an_illegal_actor_id(actor_id: str, tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = _client(backend, wire_scope=scope)

    with pytest.raises(decision.DecisionInputError) as excinfo:
        dpts.decide_for(
            DP3,
            _dp3_state(),
            project,
            client=client,
            archive=False,
            intent="answer",
            observation=dpts.Observation(scope=scope, actor_id=actor_id),
        )

    assert "actor_id" in str(excinfo.value)
    assert backend.calls == []
    assert _events(decision_wire.test_wire_sink(test_root)) == []


def test_observation_records_the_declared_actor(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    project.mkdir()
    _write_decide_config(project)
    _enable_all(project)
    test_root = tmp_path / "test-run"
    scope = _test_scope(test_root)
    backend = decision.FakeBackend([_ok(_dp3_answers())])
    client = _client(backend, wire_scope=scope)

    outcome = dpts.decide_for(
        DP3,
        _dp3_state(),
        project,
        client=client,
        archive=False,
        intent="answer",
        observation=dpts.Observation(scope=scope, actor_kind="system", actor_id="nightly"),
    )

    assert outcome.status == "suggested"
    end = _of_kind(decision_wire.test_wire_sink(test_root), "decision-end")[0]
    assert end["actor"] == {"kind": "system", "id": "nightly"}, (
        "the ledger records the declaration; it does not prove a human acted"
    )
