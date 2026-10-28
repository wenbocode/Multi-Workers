"""test_decision_history.py - T07 read-only history fold (AC-002/003/012/013/014).

The module under test (``decision_history``) is the *only* reader that merges
the four recorded carriers into one project-wide history:

* the authoritative archive ``.agenticdoc/_autopilot/decisions.jsonl``
  (``decide_archive``: decide / override / settle / authority-change),
* the wire side ledger ``decisions-wire.jsonl`` (``decision_wire`` schema v1:
  attempt-start/end, call-end, decision-end, submission-*, book-snapshot),
* the lifecycle side ledger ``decision-lifecycle.jsonl`` (schema v1
  ``kind=lifecycle``), and
* the human carriers ``<key>/evidence/review/sign-final.md`` and
  ``.agenticdoc/_autopilot/gates/gate-NNNN.md``.

What this suite locks (design §2.2/§4.4, VC-002/003/013/018):

1. the default history is cross-key **production** history; test-scope rows are
   counted separately and never enter the production page;
2. ``actor``, ``answer_source`` and the derived ``source`` claim are three
   separate facts, each with its recorded basis - ``authority=human`` on an
   archive row is *not* proof that a human acted;
3. suggestion / adoption / consumption / response / execution are separate
   stages; an absent stage is ``not-recorded``, an unfinished attempt is
   ``pending`` and a decision without a settle row has ``status=pending``;
4. logical calls and real HTTP attempts are counted separately, a
   ``zero_call=True`` client row is not an HTTP attempt and a missing
   ``wire_attempts`` is *not* backfilled to 1;
5. metadata that was redacted/clipped/dropped is ``not recorded`` - never 0 and
   never "the upstream did not send it";
6. missing links are never guessed: an unlinked call is not attached to the
   nearest decision, an unknown lifecycle word is not a stage, a ``key:``
   mismatch on a sign-off file is not silently attached;
7. opaque ids are stable, path-free handles: a raw ``decision_id`` or a
   traversal string never resolves, and no fixture record is ever written;
8. the new lifecycle ledger is invisible to the *old* consumers
   (``decide_archive.fold`` / ``decide_signoff.collect``): their rows, stats and
   ``rows_sha256`` are byte-identical before and after lifecycle rows appear.

Hermetic: every fixture is an isolated ``tmp_path`` control root, the real
``decide_archive``/``decision_wire``/``gates`` writers are used for setup, no
network, no credentials, no production file is touched.
"""

from __future__ import annotations

import json
import hashlib
import pathlib

import pytest

import decide_archive
import decide_signoff
import decision_history as history
import decision_wire as wire
from autopilot import gates

SECRET = "TEST-SECRET-abc123456789"
REDACTOR = wire.SubstringRedactor((SECRET,))

_QUIET_WARNINGS: list[str] = []


def _quiet(message: str) -> None:
    _QUIET_WARNINGS.append(message)


# ---------------------------------------------------------------------------
# Harness: real writers, isolated roots
# ---------------------------------------------------------------------------


def _root(tmp_path: pathlib.Path, name: str = "proj") -> pathlib.Path:
    """A control root with an empty archive directory (no other record)."""
    root = tmp_path / name
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    return root


def _pid(root: pathlib.Path) -> str:
    return wire.project_id_for(root)


def _archive_path(root: pathlib.Path) -> pathlib.Path:
    return root / ".agenticdoc" / "_autopilot" / "decisions.jsonl"


def _wire_path(root: pathlib.Path) -> pathlib.Path:
    return wire.production_wire_sink(root)


def _lifecycle_path(root: pathlib.Path) -> pathlib.Path:
    return wire.production_lifecycle_sink(root)


def _scope(
    root: pathlib.Path,
    *,
    decision_id: str | None = None,
    dp: str | None = None,
    key: str | None = None,
    sink: pathlib.Path | None = None,
    redact: object = REDACTOR,
    project_id: str | None = None,
    submission_id: str | None = None,
    origin: str = "cli",
    actor_kind: str | None = "human",
    actor_id: str | None = "user-explicit",
    segment_cap: int | None = None,
    scope_kind: str = "production",
) -> wire.WireScope:
    kwargs: dict[str, object] = {"segment_cap": segment_cap} if segment_cap is not None else {}
    return wire.WireScope(
        sink=sink or wire.production_wire_sink(root),
        project_id=project_id or _pid(root),
        scope_kind=scope_kind,
        origin=origin,
        decision_id=decision_id,
        dp=dp,
        key=key,
        submission_id=submission_id,
        actor_kind=actor_kind,
        actor_id=actor_id,
        redact=redact,
        warn=_quiet,
        **kwargs,
    )


def _add_decision(
    root: pathlib.Path,
    *,
    dp: str = "dp1-dispatch-type",
    key: str = "mw-alpha",
    trigger: str = "t1",
    now: str = "2026-10-22T10:00:00+00:00",
    available: bool = True,
    answer: dict | None = None,
    authority: str = "advisory",
    escalated_reason: str | None = None,
    acted: bool = False,
    actual_action: str | None = None,
    transport: str | None = "timi-decisions",
    model: str | None = "jev-latest",
    confidence_source: str | None = "api",
    mode: str = "auto",
    task_key: str | None = None,
) -> str:
    if answer is None and available:
        answer = {"q-task": {"value": "fix", "confidence": 0.9}}
    decide_archive.append_decide(
        _archive_path(root),
        dp=dp,
        key=key,
        task_key=task_key,
        trigger_id=trigger,
        state={"a": 1},
        questions_version="q-1234abcd",
        available=available,
        authority=authority,
        answer=answer,
        reason=None if available else "disabled",
        escalated_reason=escalated_reason,
        acted=acted,
        actual_action=actual_action,
        mode=mode,
        transport=transport,
        model=model,
        attempts=1,
        latency_ms=12,
        confidence=0.9 if available else None,
        confidence_source=confidence_source,
        now=now,
    )
    return f"{dp}:{trigger}"


def _add_call(
    root: pathlib.Path,
    *,
    decision_id: str | None,
    dp: str | None = "dp1-dispatch-type",
    key: str | None = "mw-alpha",
    attempts: int = 1,
    available: bool = True,
    answer_source: str | None = None,
    usage: dict | None = None,
    redact: object = REDACTOR,
    scope: wire.WireScope | None = None,
    response: bytes | None = b'{"answers":{"q-task":"fix"}}',
    confidence: float | None = None,
) -> str:
    scope = scope or _scope(root, decision_id=decision_id, dp=dp, key=key, redact=redact)
    call = wire.new_call()
    for _index in range(attempts):
        wire.record_attempt_start(
            scope,
            call,
            request=b'{"state":{"a":1}}',
            url_path="/v1/decisions",
            model="jev-latest",
        )
        wire.record_attempt_end(
            scope,
            call,
            response=response,
            latency_ms=5,
            http_status=200,
            content_type="application/json",
            usage=usage,
        )
    event = wire.call_end_event(
        scope,
        call,
        attempts=attempts,
        latency_ms=9,
        available=available,
        reason=None if available else "disabled",
        answers_present=available,
        confidence=confidence,
        confidence_source="api" if available else None,
        transport="timi-decisions",
        model="jev-latest",
    )
    if answer_source is not None:
        event["answer_source"] = answer_source
    wire.append_event(scope, event)
    return call.call_id


def _add_zero_call(root: pathlib.Path, *, decision_id: str, dp: str = "dp1-dispatch-type", key: str = "mw-alpha") -> str:
    scope = _scope(root, decision_id=decision_id, dp=dp, key=key)
    call = wire.new_call()
    wire.append_event(
        scope,
        wire.call_end_event(
            scope,
            call,
            attempts=0,
            latency_ms=0,
            available=False,
            reason="disabled",
        ),
    )
    return call.call_id


def _add_lifecycle(
    root: pathlib.Path,
    *,
    lifecycle: str,
    decision_id: str | None,
    dp: str | None = "dp1-dispatch-type",
    key: str | None = "mw-alpha",
    actor: tuple[str, str] | None = ("human", "user-explicit"),
    answer_source: str | None = None,
    target: str | None = None,
    supersedes: str | None = None,
    reason: str | None = None,
    answer: str | None = None,
    result: str | None = None,
    sink: pathlib.Path | None = None,
    project_id: str | None = None,
) -> None:
    scope = _scope(
        root,
        decision_id=decision_id,
        dp=dp,
        key=key,
        sink=sink or _lifecycle_path(root),
        project_id=project_id,
    )
    wire.append_event(
        scope,
        wire.lifecycle_event(
            scope,
            lifecycle=lifecycle,
            target=target,
            supersedes=supersedes,
            reason=reason,
            answer=answer,
            result=result,
            actor=actor,
            answer_source=answer_source,
        ),
    )


def _add_submission(root: pathlib.Path, test_root: pathlib.Path, *, submission_id: str = "sub-1") -> None:
    scope = _scope(
        root,
        sink=test_root / "wire.jsonl",
        scope_kind="test",
        submission_id=submission_id,
        dp="dp4-failure-handling",
        key="mw-alpha",
        origin="test-submission",
        actor_kind="human",
        actor_id="user-explicit",
    )
    wire.append_event(scope, wire.submission_start_event(scope, dp="dp4-failure-handling"))
    wire.append_event(
        scope, wire.submission_end_event(scope, dp="dp4-failure-handling", outcome="ok")
    )


def _add_signoff(
    root: pathlib.Path,
    key: str,
    *,
    signed_via: str = "cli",
    conclusion: str = "continue",
    claim: str = "claim-1",
    key_line: str | None = None,
    monkeypatch: pytest.MonkeyPatch | None = None,
) -> pathlib.Path:
    """Write a real ``sign-final.md`` through the production writer.

    ``monkeypatch`` is accepted for call-site compatibility only: the writer has
    no agent-session gate any more (decide-only ruling), so the env scrub it
    used to perform is unnecessary. ``signed_via`` stays a *rendered* value so
    the read-side history assertions keep covering the archived vocabulary
    (``cli`` / ``tui`` / ``auto-llm`` / ``auto-decide``).
    """
    facts = decide_signoff.collect(root, key)
    text = decide_signoff.render(
        facts,
        conclusion,
        "recorded reason",
        key_line if key_line is not None else key,
        claim,
        signed_via=signed_via,
    )
    if monkeypatch is not None:
        for name in decide_signoff.AGENT_SESSION_ENV_VARS:
            monkeypatch.delenv(name, raising=False)
    return decide_signoff.write_signoff(root, key, text)


def _add_gate(
    root: pathlib.Path,
    *,
    gate_id: str = "gate-0001",
    key: str,
    status: str = "approved",
    answered_by: str = "human",
    kind: str = "stage-confirm",
    question: str = "proceed?",
) -> pathlib.Path:
    """Create a real gate (``gates.create``) and answer it like the TS side does."""
    directory = root / ".agenticdoc" / "_autopilot" / "gates"
    path = gates.create(directory, kind, question, key=key, stage=1)
    assert path.name == f"{gate_id}.md"
    text = path.read_text(encoding="utf-8")
    text = text.replace("status: pending", f"status: {status}", 1)
    text = text.replace("answered_at:\n", "answered_at: 2026-10-22T09:05:00+00:00\n", 1)
    text = text.replace("answered_by:\n", f"answered_by: {answered_by}\n", 1)
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _append_raw(path: pathlib.Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as handle:
        handle.write(data)


def _snapshot(root: pathlib.Path, **kwargs: object) -> history.HistorySnapshot:
    return history.load_history(root, **kwargs)


def _by_decision(snapshot: history.HistorySnapshot) -> dict[str, history.HistoryRecord]:
    return {record.decision_id: record for record in snapshot.records if record.decision_id}


# ---------------------------------------------------------------------------
# 1. cross-key production default, test rows kept apart
# ---------------------------------------------------------------------------


def test_default_history_is_cross_key_production_only(tmp_path):
    root = _root(tmp_path)
    first = _add_decision(root, key="mw-alpha", trigger="t1", now="2026-10-22T10:00:00+00:00")
    second = _add_decision(root, key="mw-alpha", trigger="t2", now="2026-10-22T11:00:00+00:00")
    third = _add_decision(root, key="mw-beta", trigger="t3", now="2026-10-22T12:00:00+00:00")
    _add_lifecycle(root, lifecycle="adopted", decision_id=first)
    test_root = tmp_path / "test"
    test_root.mkdir()
    _add_submission(root, test_root)

    snapshot = _snapshot(root, test_roots=[test_root])

    production = snapshot.page()
    assert production.filters["scope"] == "production"
    assert production.total == 3
    assert {record.key for record in production.records} == {"mw-alpha", "mw-beta"}
    assert {record.decision_id for record in production.records} == {first, second, third}
    assert all(record.scope == "production" for record in production.records)
    stamps = [record.ts for record in production.records]
    assert stamps == sorted(stamps, reverse=True), "newest first, deterministic order"
    assert snapshot.stats.production_records == 3
    assert snapshot.stats.test_records == 1
    assert snapshot.page(scope="test").total == 1
    assert snapshot.page(scope="test").records[0].submission_id == "sub-1"


# ---------------------------------------------------------------------------
# 2. actor / answer_source / derived source are three separate facts
# ---------------------------------------------------------------------------


def test_actor_answer_source_and_source_are_separate_claims(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    _add_call(root, decision_id=decision_id, answer_source="api")
    _add_lifecycle(
        root,
        lifecycle="human-answer",
        decision_id=decision_id,
        actor=("human", "user-explicit"),
        answer_source="api",
        target=decision_id,
        answer="ship it",
    )

    record = _by_decision(_snapshot(root))[decision_id]

    assert record.source.value == "human"
    assert record.source.basis and all(isinstance(item, str) for item in record.source.basis)
    assert record.actor.value == "human"
    assert record.actor.basis
    assert record.answer_source.value == "api"
    assert record.answer_source.basis
    # the three claims answer different questions and are not copied into one
    assert record.source.basis != record.actor.basis
    assert record.stages["human_answer"].state == "recorded"
    assert record.stages["human_answer"].answer_source == "api"


def test_authority_human_is_not_proof_of_a_human_action(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(
        root,
        key="mw-gate",
        available=False,
        authority="human",
        escalated_reason="p0",
        answer=None,
    )

    record = _by_decision(_snapshot(root))[decision_id]

    # P2-1: available=false carries answer=None, so the recorded engine echo is
    # *not* model output. No source can be claimed - only its absence, with basis.
    assert record.source.value == "unknown"
    assert record.source.value != "human"
    assert any("no answer was recorded" in item for item in record.source.basis)
    assert any("authority=human" in item for item in record.source.basis)
    assert "authority-human-not-action" in record.flags
    assert record.actor.value is None, "no actor was recorded, so none may be claimed"
    assert record.stages["suggested"].state == "not-recorded"
    assert record.stages["suggested"].detail == "p0"


# ---------------------------------------------------------------------------
# 3. stage separation, explicit not-recorded and pending
# ---------------------------------------------------------------------------


def test_stages_are_separate_and_missing_ones_are_not_recorded(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)

    record = _by_decision(_snapshot(root))[decision_id]

    assert set(history.STAGE_NAMES) <= set(record.stages)
    assert record.stages["suggested"].state == "recorded"
    for name in ("adopted", "consumed", "responded", "executed", "human_answer", "human_override", "authority_change", "signoff"):
        assert record.stages[name].state == "not-recorded", name
    assert record.stages["settled"].state == "pending"
    assert record.status == "pending"
    assert "consumed" in record.missing and "responded" in record.missing
    assert "book" in record.missing
    # no wire ledger exists at all -> counts are unrecorded, not zero
    assert record.call_counts.recorded is False
    assert record.call_counts.logical_calls is None
    assert record.call_counts.actual_http_attempts is None
    assert record.call_counts.basis


def test_adopted_does_not_imply_consumed_or_executed(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    _add_lifecycle(root, lifecycle="adopted", decision_id=decision_id, target=decision_id)

    record = _by_decision(_snapshot(root))[decision_id]

    assert record.stages["adopted"].state == "recorded"
    assert record.stages["consumed"].state == "not-recorded"
    assert record.stages["responded"].state == "not-recorded"
    assert record.stages["executed"].state == "not-recorded"


def test_open_attempt_without_end_is_pending_not_delivered(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    scope = _scope(root, decision_id=decision_id)
    call = wire.new_call()
    wire.record_attempt_start(scope, call, request=b'{"a":1}', url_path="/v1/decisions")

    record = _by_decision(_snapshot(root))[decision_id]

    assert record.stages["responded"].state == "not-recorded"
    call_detail = record.calls[0]
    assert call_detail["attempts"][0]["unfinished"] is True
    assert call_detail["not_recorded"], "an unfinished attempt has no response yet"
    assert call_detail["attempts"][0]["response"] is None


# ---------------------------------------------------------------------------
# 4. logical calls vs real HTTP attempts
# ---------------------------------------------------------------------------


def test_logical_calls_and_http_attempts_are_counted_separately(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    _add_zero_call(root, decision_id=decision_id)
    _add_call(root, decision_id=decision_id, attempts=2)

    record = _by_decision(_snapshot(root))[decision_id]

    counts = record.call_counts
    assert counts.recorded is True
    assert counts.logical_calls == 2
    assert counts.actual_http_attempts == 2
    assert counts.zero_call == 1
    assert counts.unrecorded_wire_attempts == 0
    assert record.calls[0]["zero_call"] is True
    assert record.calls[0]["wire_attempts"] == 0
    assert record.calls[1]["wire_attempts"] == 2


def test_missing_wire_attempts_is_not_backfilled(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    scope = _scope(root, decision_id=decision_id)
    call = wire.new_call()
    event = wire.call_end_event(scope, call, attempts=1, latency_ms=3, available=True)
    del event["wire_attempts"]
    wire.append_event(scope, event)

    record = _by_decision(_snapshot(root))[decision_id]

    assert record.call_counts.logical_calls == 1
    assert record.call_counts.actual_http_attempts == 0
    assert record.call_counts.unrecorded_wire_attempts == 1
    assert record.calls[0]["wire_attempts"] is None
    assert "wire_attempts" in record.calls[0]["not_recorded"]


# ---------------------------------------------------------------------------
# 5. no guessed links
# ---------------------------------------------------------------------------


def test_unlinked_calls_are_not_attached_to_the_nearest_decision(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    _add_call(root, decision_id=None, key=None, dp=None)

    snapshot = _snapshot(root)
    record = _by_decision(snapshot)[decision_id]

    assert record.call_counts.recorded is False, "a call without a decision id is not linked"
    assert record.call_counts.logical_calls is None
    assert snapshot.stats.unlinked_call_ids == 1
    assert snapshot.stats.unlinked_events >= 1


def test_unknown_lifecycle_word_is_not_a_stage(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    _add_lifecycle(root, lifecycle="made-up", decision_id=decision_id)

    snapshot = _snapshot(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]

    assert snapshot.stats.unknown_lifecycle == 1
    assert "made-up" not in record.stages
    assert all(fact.state == "not-recorded" for name, fact in record.stages.items() if name != "suggested" and name != "settled")
    assert any("made-up" in warning for warning in snapshot.warnings)


# ---------------------------------------------------------------------------
# 6. foreign / damaged rows, opaque ids, no writes
# ---------------------------------------------------------------------------


def test_foreign_and_damaged_rows_are_counted_not_crashing(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    _add_call(root, decision_id=decision_id)
    wire_path = _wire_path(root)
    foreign = {
        "schema_version": 1,
        "event_id": "e-foreign",
        "ts": "2026-10-22T10:05:00+00:00",
        "kind": "call-end",
        "scope": "production",
        "project_id": "another-project",
        "decision_id": decision_id,
        "call_id": "c-foreign",
        "attempts": 1,
        "wire_attempts": 1,
    }
    unknown_kind = dict(foreign, event_id="e-kind", project_id=_pid(root), kind="bogus-kind")
    unknown_schema = dict(foreign, event_id="e-schema", project_id=_pid(root), schema_version=99)
    for row in (foreign, unknown_kind, unknown_schema):
        _append_raw(wire_path, json.dumps(row).encode("utf-8") + b"\n")
    _append_raw(wire_path, b'{"schema_version":1,"kind"\n')
    _append_raw(wire_path, b"\xff\xfe not utf8\n")

    before = wire_path.read_bytes()
    snapshot = _snapshot(root)
    record = _by_decision(snapshot)[decision_id]

    assert snapshot.stats.foreign_rows == 1
    assert snapshot.stats.unknown_kind == 1
    assert snapshot.stats.unknown_schema == 1
    assert snapshot.stats.wire_damaged >= 2, "bad JSON and bad UTF-8 are both counted"
    assert record.call_counts.logical_calls == 1, "only the in-project row is counted"
    assert wire_path.read_bytes() == before, "the reader never writes"


def test_opaque_ids_are_stable_path_free_handles(tmp_path):
    root = _root(tmp_path)
    trap = "dp1-dispatch-type:../../evil"
    _add_decision(root, trigger="t1")
    scope = _scope(root, decision_id=trap)
    wire.append_event(
        scope,
        wire.call_end_event(scope, wire.new_call(), attempts=0, latency_ms=0, available=False, reason="disabled"),
    )

    snapshot = _snapshot(root)
    second = _snapshot(root)

    assert snapshot.stats.invalid_ids == 1, "a traversal-shaped id is a value, not a path"
    record = next(item for item in snapshot.records if item.decision_id)
    assert history.OPAQUE_ID_PATTERN.match(record.opaque_id)
    assert record.opaque_id != record.decision_id
    assert history.opaque_id_for(record.project_id, record.scope, record.identity) == record.opaque_id
    assert record.opaque_id == next(
        item.opaque_id for item in second.records if item.decision_id == record.decision_id
    )
    assert snapshot.detail(record.opaque_id) is not None
    assert snapshot.detail(record.decision_id) is None
    assert snapshot.detail("../etc/passwd") is None
    assert snapshot.detail("h-" + "0" * 20) is None
    assert not (tmp_path / "evil").exists()


def test_history_reads_only_the_control_root(tmp_path):
    root = _root(tmp_path)
    _add_decision(root, key="mw-alpha")
    nested = root / "workspace" / "nested"
    (nested / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    decide_archive.append_decide(
        nested / ".agenticdoc" / "_autopilot" / "decisions.jsonl",
        dp="dp1-dispatch-type",
        key="mw-nested",
        task_key=None,
        trigger_id="nested",
        state={"a": 1},
        questions_version="q-1234abcd",
        available=True,
        authority="advisory",
        answer={"q-task": {"value": "x", "confidence": 0.5}},
    )

    snapshot = _snapshot(root)
    from_key_dir = _snapshot(root / ".agenticdoc" / "mw-alpha")

    assert snapshot.page().total == 1
    assert {record.key for record in snapshot.page().records} == {"mw-alpha"}
    assert [record.opaque_id for record in from_key_dir.page().records] == [
        record.opaque_id for record in snapshot.page().records
    ], "key-dir and control-root calls resolve to one archive root"


# ---------------------------------------------------------------------------
# 7. filters and pagination
# ---------------------------------------------------------------------------


def _filter_fixture(tmp_path: pathlib.Path) -> tuple[pathlib.Path, dict[str, str]]:
    root = _root(tmp_path)
    ledger_only = "dp5-test-triage:ledger-only"
    ids = {
        "model": _add_decision(root, key="mw-a", trigger="t1", now="2026-10-22T10:00:00+00:00"),
        "human": _add_decision(root, key="mw-a", dp="dp2-checkpoint-split", trigger="t2", now="2026-10-22T10:01:00+00:00"),
        "pending": _add_decision(root, key="mw-b", dp="dp3-worker-clarify", trigger="t3", now="2026-10-22T10:02:00+00:00"),
        "settled": _add_decision(root, key="mw-b", dp="dp4-failure-handling", trigger="t4", now="2026-10-22T10:03:00+00:00"),
        "ledger": ledger_only,
        "system": "dp5-test-triage:auto-only",
    }
    decide_archive.append_settle(
        _archive_path(root),
        decision_id=ids["settled"],
        dp="dp4-failure-handling",
        key="mw-b",
        task_key=None,
        outcome="ok",
        settled_by="pm-auto",
    )
    decide_archive.append_settle(
        _archive_path(root),
        decision_id=ids["system"],
        dp="dp5-test-triage",
        key="mw-c",
        task_key=None,
        outcome="ok",
        settled_by="pm-auto",
    )
    _add_lifecycle(root, lifecycle="human-answer", decision_id=ids["human"], dp="dp2-checkpoint-split", key="mw-a", target=ids["human"])
    _add_lifecycle(root, lifecycle="suggested", decision_id=ids["system"], dp="dp5-test-triage", key="mw-c", actor=("system", "conductor"))
    _add_lifecycle(root, lifecycle="consumed", decision_id=ledger_only, dp="dp5-test-triage", key="mw-d", actor=("system", "pm-orchestrator"))
    return root, ids


def test_filters_are_exact_and_pagination_is_lossless(tmp_path):
    root, ids = _filter_fixture(tmp_path)
    snapshot = _snapshot(root)
    total = snapshot.page().total
    assert total == 6

    def decision_ids(**filters: object) -> set[str]:
        return {record.decision_id for record in snapshot.page(**filters).records}

    assert decision_ids(key="mw-a") == {ids["model"], ids["human"]}
    assert decision_ids(key="mw-b") == {ids["pending"], ids["settled"]}
    assert decision_ids(dp="dp2-checkpoint-split") == {ids["human"]}
    assert decision_ids(dp="dp5-test-triage") == {ids["ledger"], ids["system"]}
    assert decision_ids(source="human") == {ids["human"]}
    assert decision_ids(source="system") == {ids["system"], ids["ledger"]}
    assert decision_ids(source="model") == {ids["model"], ids["pending"], ids["settled"]}
    assert decision_ids(status="pending") == {ids["model"], ids["human"], ids["pending"]}
    assert decision_ids(status="ok") == {ids["settled"], ids["system"]}
    assert decision_ids(status="unknown") == {ids["ledger"]}

    seen: list[str] = []
    offset = 0
    while True:
        page = snapshot.page(limit=2, offset=offset)
        seen.extend(record.opaque_id for record in page.records)
        if not page.has_more:
            break
        offset += 2
    assert len(seen) == total == len(set(seen)), "pages cover every record exactly once"

    for bad in ({"source": "bogus"}, {"status": "bogus"}, {"scope": "bogus"}, {"limit": 0}, {"limit": 201}, {"offset": -1}):
        with pytest.raises(ValueError):
            snapshot.page(**bad)
    with pytest.raises(ValueError):
        snapshot.page(key="../escape")


# ---------------------------------------------------------------------------
# 8. metadata holes are "not recorded", never 0
# ---------------------------------------------------------------------------


def test_missing_metadata_is_unrecorded_not_zero(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    _add_call(root, decision_id=decision_id, usage={"input_tokens": 5}, confidence=0.4)
    _add_call(root, decision_id=decision_id, usage=None, confidence=None)

    record = _by_decision(_snapshot(root))[decision_id]

    assert record.usage.recorded is True
    assert record.usage.counters == {"input_tokens": 5}
    assert "output_tokens" in record.usage.missing
    assert record.usage.complete is False
    assert 0 not in record.usage.counters.values(), "an absent counter is never written as 0"
    second = record.calls[1]
    assert second["usage"] is None
    assert "usage" in second["not_recorded"]
    assert second["confidence"] is None
    assert "confidence" in second["not_recorded"]
    assert record.calls[0]["confidence"] == 0.4


# ---------------------------------------------------------------------------
# 9. human vs machine provenance, sign-off and gate joins
# ---------------------------------------------------------------------------


def test_machine_rows_are_never_labelled_human(tmp_path, monkeypatch):
    root = _root(tmp_path)
    decision_id = _add_decision(root, key="mw-human")
    decide_archive.append_authority_change(
        _archive_path(root),
        dp="dp1-dispatch-type",
        key="mw-human",
        by="signoff:continue",
        change="dp1 on",
        conclusion="continue",
    )
    _add_lifecycle(
        root,
        lifecycle="human-override",
        decision_id=decision_id,
        key="mw-human",
        target=decision_id,
        supersedes=decision_id,
        reason="human says no",
        actor=("human", "user-explicit"),
    )
    _add_signoff(root, "mw-human", signed_via="cli", monkeypatch=monkeypatch)

    record = _by_decision(_snapshot(root))[decision_id]

    assert record.stages["authority_change"].state == "recorded"
    assert record.stages["authority_change"].actor == "system", "signoff:* is a machine writer"
    assert record.stages["human_override"].state == "recorded"
    assert record.stages["human_override"].actor == "human"
    assert record.stages["human_override"].supersedes == decision_id
    assert record.stages["signoff"].state == "recorded"
    assert record.stages["signoff"].detail == "cli"
    assert record.source.value == "human"
    assert record.stages["authority_change"].actor != "human"


def test_signoff_and_gate_join_by_key_only(tmp_path, monkeypatch):
    root = _root(tmp_path)
    alpha = _add_decision(root, key="mw-alpha", trigger="a1")
    beta = _add_decision(root, key="mw-beta", trigger="b1")
    _add_gate(root, gate_id="gate-0001", key="mw-alpha", answered_by="human")
    _add_signoff(root, "mw-beta", signed_via="cli", monkeypatch=monkeypatch)
    # a sign-off file in alpha's dir that claims another key must not attach
    stray = decide_signoff.signoff_path(root, "mw-alpha")
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text("conclusion: continue\nkey: mw-beta\nsigned_via: cli\n", encoding="utf-8", newline="\n")

    snapshot = _snapshot(root, redact=REDACTOR)
    records = _by_decision(snapshot)

    assert [gate["id"] for gate in records[alpha].gates] == ["gate-0001"]
    assert records[beta].gates == ()
    assert records[alpha].stages["signoff"].state == "not-recorded"
    assert records[beta].stages["signoff"].state == "recorded"
    assert any("signoff" in warning and "mw-alpha" in warning for warning in snapshot.warnings)
    # a gate answer is human evidence for the stage, not a decision answer source
    assert records[alpha].source.value == "model"


def test_signoff_only_key_is_still_recorded(tmp_path, monkeypatch):
    root = _root(tmp_path)
    decision_id = _add_decision(root, key="mw-alpha")
    key_dir = root / ".agenticdoc" / "mw-empty"
    key_dir.mkdir(parents=True)
    text = decide_signoff.render(
        decide_signoff.collect(root, "mw-empty"),
        "narrow",
        "nothing to continue",
        "mw-empty",
        "claim-empty",
        signed_via="cli",
    )
    for name in decide_signoff.AGENT_SESSION_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
    decide_signoff.write_signoff(root, "mw-empty", text)

    snapshot = _snapshot(root)
    by_key = {record.key: record for record in snapshot.records}

    assert decision_id
    assert by_key["mw-alpha"].stages["signoff"].state == "not-recorded"
    assert "mw-empty" in by_key
    assert by_key["mw-empty"].record_kind == "signoff"
    assert by_key["mw-empty"].stages["signoff"].state == "recorded"
    assert by_key["mw-empty"].source.value == "human"
    assert by_key["mw-empty"].status == "unknown"


# ---------------------------------------------------------------------------
# 10. production / test split and misplaced test rows
# ---------------------------------------------------------------------------


def test_production_and_test_statistics_are_split(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    test_root = tmp_path / "test"
    test_root.mkdir()
    _add_submission(root, test_root)
    # A test-scope row inside the production sink. The writer refuses this
    # (fail-closed), so the fixture is the stray line itself: the reader must
    # count it as misplaced instead of folding it into production.
    _append_raw(
        _wire_path(root),
        json.dumps(
            {
                "schema_version": 1,
                "event_id": "e-misplaced",
                "ts": "2026-10-22T10:30:00+00:00",
                "kind": "submission-start",
                "scope": "test",
                "project_id": _pid(root),
                "submission_id": "sub-misplaced",
                "dp": "dp4-failure-handling",
                "outcome": "started",
            }
        ).encode("utf-8")
        + b"\n",
    )

    snapshot = _snapshot(root, test_roots=[test_root])

    production = snapshot.page()
    assert production.total == 1
    assert production.records[0].decision_id == decision_id
    assert snapshot.stats.misplaced_test_rows == 1
    assert snapshot.stats.test_records == 1
    assert snapshot.page(scope="test").total == 1


# ---------------------------------------------------------------------------
# 11. capture markers, row-level status, no fabricated original
# ---------------------------------------------------------------------------


def test_capture_markers_are_per_row_and_never_relabelled(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    # call 1: no redactor -> text withheld (fail-closed) => row "failed"
    bare = _scope(root, decision_id=decision_id, redact=None)
    call_one = wire.new_call()
    wire.record_attempt_start(bare, call_one, request=b'{"a":1}', url_path="/v1/decisions")
    wire.record_attempt_end(bare, call_one, response=b'{"b":2}', latency_ms=1, http_status=200)
    wire.append_event(bare, wire.call_end_event(bare, call_one, attempts=1, latency_ms=1, available=True))
    # call 2: tiny segment cap -> truncated (partial)
    tiny = _scope(root, decision_id=decision_id, segment_cap=16)
    call_two = wire.new_call()
    wire.record_attempt_start(tiny, call_two, request=b'{"a":1}', url_path="/v1/decisions")
    wire.record_attempt_end(tiny, call_two, response=b'{"answer":"' + b"x" * 64 + b'"}', latency_ms=2, http_status=200)
    wire.append_event(tiny, wire.call_end_event(tiny, call_two, attempts=1, latency_ms=2, available=True))
    # call 3: clean and redacted-free -> row "ok"
    clean = _scope(root, decision_id=decision_id)
    call_three = wire.new_call()
    wire.record_attempt_start(clean, call_three, request=b'{"a":1}', url_path="/v1/decisions")
    wire.record_attempt_end(clean, call_three, response=b'{"ok":true}', latency_ms=3, http_status=200)
    wire.append_event(clean, wire.call_end_event(clean, call_three, attempts=1, latency_ms=3, available=True))

    record = _by_decision(_snapshot(root))[decision_id]
    statuses = [call["capture_status"] for call in record.calls]
    assert statuses == ["failed", "partial", "ok"], "each row keeps its own status"
    assert record.capture_status == "failed"

    omitted = record.calls[0]["attempts"][0]["response"]
    assert omitted["text"] is None and omitted["text_omitted"] is True
    assert omitted["byte_exact"] is False
    truncated = record.calls[1]["attempts"][0]["response"]
    assert truncated["truncated"] is True
    assert truncated["byte_exact"] is False
    assert truncated["stored_len"] <= truncated["wire_len"]
    clean_payload = record.calls[2]["attempts"][0]["response"]
    assert clean_payload["byte_exact"] is True
    assert "request_reconstructed" not in record.as_dict(detail=True)


# ---------------------------------------------------------------------------
# 12. book snapshot linkage and the old consumers staying untouched
# ---------------------------------------------------------------------------


def test_book_snapshot_is_linked_and_absence_is_unrecorded(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    scope = _scope(root, decision_id=decision_id)
    wire.append_event(
        scope,
        wire.book_snapshot_event(scope, book=json.dumps({"dp": "dp1-dispatch-type"}).encode("utf-8"), book_ref="input-memory", book_version="v1"),
    )

    with_book = _by_decision(_snapshot(root))[decision_id]

    assert with_book.stages["book"].state == "recorded"
    assert with_book.stages["book"].detail == "input-memory"
    assert "book" not in with_book.missing

    other = _add_decision(root, trigger="t2")
    without_book = _by_decision(_snapshot(root))[other]
    assert without_book.stages["book"].state == "not-recorded"
    assert "book" in without_book.missing


def test_new_lifecycle_rows_never_reach_the_old_consumers(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root, key="mw-old")
    decide_archive.append_settle(
        _archive_path(root),
        decision_id=decision_id,
        dp="dp1-dispatch-type",
        key="mw-old",
        task_key=None,
        outcome="ok",
        settled_by="pm-auto",
    )
    rows_before = [row for _lineno, row in decide_archive.iter_rows(_archive_path(root))]
    before = decide_signoff.collect(root, "mw-old")
    fold_before = decide_archive.fold(rows_before)

    _add_lifecycle(root, lifecycle="suggested", decision_id=decision_id, target=decision_id, actor=("system", "conductor"))
    _add_lifecycle(root, lifecycle="adopted", decision_id=decision_id, target=decision_id, actor=("system", "pm-orchestrator"))
    _add_lifecycle(root, lifecycle="consumed", decision_id=decision_id, target=decision_id, actor=("system", "pm-orchestrator"))
    _add_lifecycle(root, lifecycle="responded", decision_id=decision_id, target=decision_id, answer="done")

    rows_after = [row for _lineno, row in decide_archive.iter_rows(_archive_path(root))]
    after = decide_signoff.collect(root, "mw-old")
    fold_after = decide_archive.fold(rows_after)

    assert rows_after == rows_before
    assert after.sha256 == before.sha256
    assert after.rows == before.rows
    assert fold_after.groups == fold_before.groups
    assert fold_after.stats == fold_before.stats
    assert len(rows_before) == 2, "the new ledger never becomes an archive row"

    record = _by_decision(_snapshot(root))[decision_id]
    assert record.stages["adopted"].state == "recorded"
    assert record.stages["consumed"].state == "recorded"
    assert record.stages["responded"].state == "recorded"


# ---------------------------------------------------------------------------
# 13. detail view contract
# ---------------------------------------------------------------------------


def test_detail_view_exposes_explicit_links_and_missing_markers(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root)
    call_id = _add_call(root, decision_id=decision_id, attempts=2, usage={"input_tokens": 1, "output_tokens": 2, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0})
    _add_lifecycle(root, lifecycle="adopted", decision_id=decision_id, target=decision_id, actor=("system", "pm-orchestrator"))

    snapshot = _snapshot(root)
    record = _by_decision(snapshot)[decision_id]
    detail = snapshot.detail(record.opaque_id)
    payload = detail.as_dict(detail=True)

    assert payload["opaque_id"] == record.opaque_id
    assert payload["decision_id"] == decision_id
    assert payload["scope"] == "production"
    assert payload["calls"][0]["call_id"] == call_id
    assert [attempt["attempt_index"] for attempt in payload["calls"][0]["attempts"]] == [1, 2]
    assert payload["calls"][0]["attempts"][0]["not_recorded"] == []
    assert payload["stages"]["adopted"]["state"] == "recorded"
    assert payload["stages"]["responded"]["state"] == "not-recorded"
    assert payload["source"]["basis"]
    assert payload["missing"]
    json.dumps(payload), "the detail payload must be JSON-safe for the monitor"


# ---------------------------------------------------------------------------
# 14. output safety: redact -> clip -> withhold across every carrier (P1-1)
# ---------------------------------------------------------------------------


def _carrier_fixture(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[pathlib.Path, str]:
    """One fixture with the known secret in every free-text carrier."""
    root = _root(tmp_path)
    plain = _add_decision(root, key="mw-secret", trigger="s1")
    _add_decision(
        root,
        key="mw-secret",
        trigger="s2",
        authority="binding",
        acted=True,
        actual_action=f"wrote {SECRET} to notes",
        answer={"q-task": {"value": SECRET, "confidence": 0.9}},
    )
    decide_archive.append_override(
        _archive_path(root),
        decision_id=plain,
        dp="dp1-dispatch-type",
        key="mw-secret",
        override_by="human",
        override_reason=f"undo {SECRET}",
    )
    decide_archive.append_settle(
        _archive_path(root),
        decision_id=plain,
        dp="dp1-dispatch-type",
        key="mw-secret",
        task_key=None,
        outcome="ok",
        settled_by="human",
        evidence_ref=f"evidence/{SECRET}/run.txt",
    )
    _add_gate(root, gate_id="gate-0001", key="mw-secret", question=f"proceed with {SECRET}?")
    _add_signoff(
        root, "mw-secret", signed_via="cli", claim=f"claim {SECRET}", monkeypatch=monkeypatch
    )
    return root, plain


def _all_payloads(snapshot: history.HistorySnapshot) -> str:
    """Every list/detail payload plus the warnings, as the monitor would see it."""
    dumped = [record.as_dict() for record in snapshot.records] + [
        record.as_dict(detail=True) for record in snapshot.records
    ]
    return json.dumps(dumped) + json.dumps(list(snapshot.warnings))


def test_free_text_is_redacted_across_every_carrier(tmp_path, monkeypatch):
    root, decision_id = _carrier_fixture(tmp_path, monkeypatch)

    snapshot = _snapshot(root, redact=REDACTOR)
    payload = _all_payloads(snapshot)

    assert SECRET not in payload, "no carrier may echo a known credential"
    assert "<redacted>" in payload
    assert history.FREE_TEXT_FIELDS["signoff"] == ("claim",)
    assert "answer" in history.FREE_TEXT_FIELDS["archive"]
    record = _by_decision(snapshot)[decision_id]
    assert record.redaction.enabled is True
    assert record.redaction.substitutions >= 4
    assert "free-text-redacted" in record.flags
    # free text is redacted, structural identifiers stay verbatim for the joins
    assert record.signoff["claim"] == "claim <redacted>"
    assert record.signoff["key"] == "mw-secret"
    assert record.gates[0]["question"] == "proceed with <redacted>?"
    assert record.gates[0]["id"] == "gate-0001"
    acted = _by_decision(snapshot)["dp1-dispatch-type:s2"]
    assert acted.archive["answer"]["q-task"]["value"] == "<redacted>"
    assert acted.archive["actual_action"] == "wrote <redacted> to notes"
    assert acted.archive["authority"] == "binding"
    assert any("override_reason" in name for name in record.redaction.fields)


def test_missing_redactor_withholds_free_text_instead_of_echoing(tmp_path, monkeypatch):
    root, decision_id = _carrier_fixture(tmp_path, monkeypatch)

    snapshot = _snapshot(root)  # no redactor injected -> fail closed
    payload = _all_payloads(snapshot)

    assert SECRET not in payload
    record = _by_decision(snapshot)[decision_id]
    assert record.redaction.enabled is False
    assert record.redaction.omitted_fields >= 4
    assert "free-text-omitted" in record.flags
    assert record.signoff["claim"] is None
    assert record.gates[0]["question"] is None
    assert record.gates[0]["id"] == "gate-0001", "structural gate fields survive"
    assert record.gates[0]["status"] == "approved"
    acted = _by_decision(snapshot)["dp1-dispatch-type:s2"]
    assert acted.archive["answer"] is None
    assert acted.archive["actual_action"] is None
    assert acted.archive["authority"] == "binding"
    assert any("withheld" in warning for warning in snapshot.warnings)


def test_unknown_carrier_fields_are_not_treated_as_schema(tmp_path):
    root = _root(tmp_path)
    _add_decision(root, key="mw-alpha", trigger="t1")
    raw_row = {
        "seq": 2,
        "prev_sha": "0" * 16,
        "kind": "decide",
        "decision_id": "dp2-checkpoint-split:extra",
        "ts": "2026-10-22T10:00:00+00:00",
        "dp": "dp2-checkpoint-split",
        "key": "mw-alpha",
        "task_key": None,
        "state_digest": "0" * 16,
        "questions_version": "q-1234abcd",
        "available": True,
        "reason": None,
        "answer": {"q-task": "x"},
        "authority": "advisory",
        "escalated_reason": None,
        "acted": False,
        "actual_action": None,
        "outcome": "pending",
        "settled_by": None,
        "evidence_ref": None,
        "override_by": None,
        "override_reason": None,
        "ref_seq": None,
        "by": None,
        "change": None,
        "conclusion": None,
        "config_sha_after": None,
        "evidence_line": None,
        "mode": "auto",
        "model": "jev-latest",
        "transport": "timi-decisions",
        "attempts": 1,
        "latency_ms": 1,
        "confidence": 0.9,
        "confidence_source": "api",
        "cost_tokens": None,
        "policy": None,
        "note": None,
        "unexpected_field": f"raw {SECRET}",
    }
    _append_raw(_archive_path(root), json.dumps(raw_row).encode("utf-8") + b"\n")

    snapshot = _snapshot(root, redact=REDACTOR)
    record = _by_decision(snapshot)["dp2-checkpoint-split:extra"]

    assert "unexpected_field" not in record.archive
    assert record.redaction.dropped_fields >= 1
    assert "schema-fields-dropped" in record.flags
    assert SECRET not in _all_payloads(snapshot)


def test_long_free_text_is_clipped_with_honest_markers(tmp_path):
    root = _root(tmp_path)
    body = "x" * (history.FREE_TEXT_LIMIT + 500)
    decision_id = _add_decision(
        root,
        key="mw-long",
        available=True,
        authority="binding",
        acted=True,
        actual_action=f"{body}{SECRET}",
    )

    record = _by_decision(_snapshot(root, redact=REDACTOR))[decision_id]

    text = record.archive["actual_action"]
    assert SECRET not in text
    assert "[truncated: kept" in text
    assert text.endswith("bytes]")
    assert record.redaction.truncated_fields >= 1
    assert "free-text-truncated" in record.flags
    assert len(text.split(" [truncated")[0].encode("utf-8")) <= history.FREE_TEXT_LIMIT


def test_clip_boundary_never_keeps_a_partial_secret(tmp_path):
    root = _root(tmp_path)
    # The cut lands inside the first characters of the secret, so only the
    # boundary scrub can remove it (a full match would have been redacted).
    value = "y" * (history.FREE_TEXT_LIMIT - 1) + SECRET[:3] + "tail"
    decision_id = _add_decision(
        root,
        key="mw-boundary",
        available=True,
        authority="binding",
        acted=True,
        actual_action=value,
    )

    record = _by_decision(_snapshot(root, redact=REDACTOR))[decision_id]

    clipped = record.archive["actual_action"]
    kept = clipped.split(" [truncated")[0]
    assert not kept.endswith(SECRET[:1])
    assert len(kept.encode("utf-8")) == history.FREE_TEXT_LIMIT - 1
    assert record.redaction.truncated_fields >= 1


# ---------------------------------------------------------------------------
# 15. record keys are values, carriers are read inside their root (P1-2)
# ---------------------------------------------------------------------------


def _read_spy(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    seen: list[str] = []
    original = pathlib.Path.read_text

    def spy(self, *args, **kwargs):
        seen.append(str(self))
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", spy)
    return seen


def test_record_key_is_validated_before_any_path_is_built(tmp_path, monkeypatch):
    root = _root(tmp_path)
    victim = root / "victim" / "evidence" / "review"
    victim.mkdir(parents=True)
    (victim / "sign-final.md").write_text(
        f"conclusion: continue\nkey: victim\nsigned_via: cli\nclaim: {SECRET}\n",
        encoding="utf-8",
        newline="\n",
    )
    decision_id = _add_decision(root, key="../victim", trigger="t1")
    # An empty key is "not recorded" (nothing to join), not a traversal attempt.
    empty_key = _add_decision(root, key="", trigger="t2")
    reads = _read_spy(monkeypatch)

    snapshot = _snapshot(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]

    assert SECRET not in _all_payloads(snapshot)
    assert str(victim / "sign-final.md") not in reads
    assert record.key is None, "a traversal-shaped key is not a key"
    assert _by_decision(snapshot)[empty_key].key is None
    assert record.stages["signoff"].state == "not-recorded"
    assert snapshot.stats.invalid_keys == 1, "only the traversal-shaped key is invalid"
    assert any("not a directory name" in warning for warning in snapshot.warnings)


def test_out_of_root_signoff_symlink_is_refused_before_read(tmp_path, monkeypatch):
    root = _root(tmp_path)
    decision_id = _add_decision(root, key="mw-alpha", trigger="t1")
    outside = tmp_path / "outside-sign-final.md"
    outside.write_text(
        f"conclusion: continue\nkey: mw-alpha\nsigned_via: cli\nclaim: {SECRET}\n",
        encoding="utf-8",
        newline="\n",
    )
    link = decide_signoff.signoff_path(root, "mw-alpha")
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform
        pytest.skip(f"symlink unavailable: {type(exc).__name__}")
    reads = _read_spy(monkeypatch)

    snapshot = _snapshot(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]

    assert str(outside) not in reads, "an out-of-root link must not be read"
    assert SECRET not in _all_payloads(snapshot)
    assert record.signoff is None
    assert record.stages["signoff"].state == "not-recorded"
    assert snapshot.stats.blocked_reads >= 1
    assert any("refused before read" in warning for warning in snapshot.warnings)


def test_out_of_root_gate_and_test_ledger_are_refused(tmp_path):
    root = _root(tmp_path)
    _add_decision(root, key="mw-alpha")
    gate_path = _add_gate(root, gate_id="gate-0001", key="mw-alpha")
    outside_gate = tmp_path / "outside-gate.md"
    outside_gate.write_text(gate_path.read_text(encoding="utf-8"), encoding="utf-8", newline="\n")
    link = gate_path.parent / "gate-0002.md"
    test_root = tmp_path / "test"
    test_root.mkdir()
    outside_ledger = tmp_path / "outside-wire.jsonl"
    outside_ledger.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "event_id": "e-outside",
                "ts": "2026-10-22T10:30:00+00:00",
                "kind": "submission-start",
                "scope": "test",
                "project_id": _pid(root),
                "submission_id": "sub-outside",
                "dp": "dp4-failure-handling",
                "outcome": "started",
            }
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    try:
        link.symlink_to(outside_gate)
        (test_root / "wire.jsonl").symlink_to(outside_ledger)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform
        pytest.skip(f"symlink unavailable: {type(exc).__name__}")

    snapshot = _snapshot(root, test_roots=[test_root], redact=REDACTOR)

    assert snapshot.stats.blocked_reads >= 2
    assert snapshot.stats.gates_recorded == 1, "the in-root gate is still read"
    assert snapshot.page(scope="test").total == 0
    assert all("gate-0002" not in json.dumps(record.as_dict()) for record in snapshot.records)
    assert any("refused before read" in warning for warning in snapshot.warnings)


def test_history_read_never_writes_or_creates_paths(tmp_path, monkeypatch):
    root = _root(tmp_path)
    decision_id = _add_decision(root, key="mw-alpha")
    _add_call(root, decision_id=decision_id)
    _add_lifecycle(root, lifecycle="adopted", decision_id=decision_id, target=decision_id)
    _add_gate(root, gate_id="gate-0001", key="mw-alpha")
    test_root = tmp_path / "test"
    test_root.mkdir()
    _add_submission(root, test_root)

    def inventory() -> dict[str, str]:
        found: dict[str, str] = {}
        for path in sorted(root.rglob("*")):
            if path.is_file():
                found[path.relative_to(root).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
        return found

    writes: list[str] = []
    mkdirs: list[str] = []
    original_open = pathlib.Path.open
    original_mkdir = pathlib.Path.mkdir
    watched = {root.resolve(), test_root.resolve()}

    def inside(path: pathlib.Path) -> bool:
        try:
            resolved = path.resolve()
        except OSError:
            return False
        return any(resolved == item or item in resolved.parents for item in watched)

    def open_spy(self, mode="r", *args, **kwargs):
        if any(flag in mode for flag in ("w", "a", "x", "+")) and inside(self):
            writes.append(str(self))
        return original_open(self, mode, *args, **kwargs)

    def mkdir_spy(self, *args, **kwargs):
        if inside(self):
            mkdirs.append(str(self))
        return original_mkdir(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "open", open_spy)
    monkeypatch.setattr(pathlib.Path, "mkdir", mkdir_spy)
    before = inventory()
    snapshot = _snapshot(root, test_roots=[test_root])
    second = _snapshot(root, test_roots=[test_root])
    for record in snapshot.records:
        record.as_dict(detail=True)
    snapshot.page(limit=1)
    snapshot.detail(snapshot.records[0].opaque_id)
    after = inventory()

    assert after == before, "a history read must not move any carrier byte"
    assert writes == [], "the reader opens no file for writing"
    assert mkdirs == [], "the reader creates no directory"
    assert second.page().total == snapshot.page().total


# ---------------------------------------------------------------------------
# 16. no-answer records: source is unknown with basis (P2-1)
# ---------------------------------------------------------------------------


def test_ledger_call_without_answer_does_not_claim_a_model_source(tmp_path):
    root = _root(tmp_path)
    decision_id = "dp1-dispatch-type:ledger-only"
    _add_zero_call(root, decision_id=decision_id)

    record = _by_decision(_snapshot(root))[decision_id]

    assert record.source.value == "unknown"
    assert any("available=false" in item for item in record.source.basis)
    assert record.stages["suggested"].state == "not-recorded"


# ---------------------------------------------------------------------------
# 17. record usage names its semantics, per-attempt values survive (P2-2)
# ---------------------------------------------------------------------------


def test_record_usage_names_its_semantics_and_keeps_per_attempt_values(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root, trigger="u1")
    scope = _scope(root, decision_id=decision_id)
    call = wire.new_call()
    wire.record_attempt_start(scope, call, request=b'{"a":1}', url_path="/v1/decisions")
    wire.record_attempt_end(
        scope,
        call,
        response=b'{"b":2}',
        latency_ms=1,
        http_status=200,
        usage={"input_tokens": 5},
    )
    wire.record_attempt_start(scope, call, request=b'{"a":1}', url_path="/v1/decisions")
    wire.record_attempt_end(
        scope,
        call,
        response=b'{"b":3}',
        latency_ms=2,
        http_status=200,
        usage={"output_tokens": 7},
    )
    wire.append_event(
        scope, wire.call_end_event(scope, call, attempts=2, latency_ms=3, available=True)
    )

    record = _by_decision(_snapshot(root))[decision_id]

    usage = record.usage
    assert usage.recorded is True
    assert usage.semantics == "last-recorded-attempt", "never passed off as a total"
    assert usage.attempts_with_usage == 2
    assert usage.conflicting is True
    assert usage.counters == {"output_tokens": 7}, "the last recorded attempt, not a sum"
    assert "input_tokens" in usage.missing
    assert 0 not in usage.counters.values(), "an absent counter is never written as 0"
    assert any("never a sum" in item for item in usage.basis)
    assert "usage-last-attempt-only" in record.flags
    assert "usage-attempts-disagree" in record.flags
    usages = [attempt["usage"] for attempt in record.calls[0]["attempts"]]
    assert usages == [{"input_tokens": 5}, {"output_tokens": 7}]
    assert record.calls[0]["usage_semantics"] == "last-recorded-attempt"

    single = _add_decision(root, trigger="u2")
    _add_call(root, decision_id=single, usage={"input_tokens": 3})
    single_record = _by_decision(_snapshot(root))[single]
    assert single_record.usage.semantics == "single-recorded-attempt"
    assert single_record.usage.conflicting is False
    assert "usage-last-attempt-only" not in single_record.flags


# ---------------------------------------------------------------------------
# 18. repeated settled events: the last event owns status and stage (P2-3)
# ---------------------------------------------------------------------------


def test_repeated_settled_events_agree_with_the_stage(tmp_path):
    root = _root(tmp_path)
    decision_id = "dp1-dispatch-type:repeated-settle"
    _add_lifecycle(
        root, lifecycle="suggested", decision_id=decision_id, actor=("system", "conductor")
    )
    _add_lifecycle(
        root, lifecycle="settled", decision_id=decision_id, result="ok", actor=("system", "pm-auto")
    )
    _add_lifecycle(
        root,
        lifecycle="settled",
        decision_id=decision_id,
        result="rollback",
        actor=("human", "user-explicit"),
    )

    record = _by_decision(_snapshot(root))[decision_id]

    assert record.status == "rollback", "status must not come from the first settled event"
    assert record.stages["settled"].state == "recorded"
    assert record.stages["settled"].result == "rollback"
    assert record.status == record.stages["settled"].result


# ---------------------------------------------------------------------------
# 19. gate visibility: keyless counts, gate-only keys, no guessed key (P2-4)
# ---------------------------------------------------------------------------


def test_keyless_gate_is_counted_and_gate_only_key_stays_visible(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root, key="mw-alpha", trigger="t1")
    _add_gate(root, gate_id="gate-0001", key="mw-alpha")
    # stage-level gate: no key at all -> attribution unknown, never guessed
    directory = root / ".agenticdoc" / "_autopilot" / "gates"
    keyless = gates.create(directory, "stage-confirm", "continue stage?", key=None, stage=2)
    assert keyless.name == "gate-0002.md"
    _add_gate(root, gate_id="gate-0003", key="mw-gate-only")

    snapshot = _snapshot(root, redact=REDACTOR)

    assert snapshot.stats.gates_recorded == 3
    assert snapshot.stats.gates_keyless == 1
    assert any("gate-keyless" in warning for warning in snapshot.warnings)
    by_key = {record.key: record for record in snapshot.records if record.key}
    assert [gate["id"] for gate in by_key["mw-alpha"].gates] == ["gate-0001"]
    assert decision_id
    assert by_key["mw-gate-only"].record_kind == "gate"
    assert [gate["id"] for gate in by_key["mw-gate-only"].gates] == ["gate-0003"]
    assert by_key["mw-gate-only"].source.value == "unknown"
    # the keyless gate is not silently attached to any record
    every_gate = json.dumps([record.as_dict() for record in snapshot.records])
    assert "gate-0002" not in every_gate


# ---------------------------------------------------------------------------
# 20. provenance coverage: auto sign-off, refresh, dp-level authority (P2-5)
# ---------------------------------------------------------------------------


def test_auto_signoff_is_system_not_a_human_answer(tmp_path):
    root = _root(tmp_path)
    escalated = _add_decision(
        root,
        key="mw-auto",
        trigger="a1",
        available=False,
        authority="human",
        escalated_reason="p0",
        answer=None,
    )
    _add_signoff(root, "mw-auto", signed_via="auto-decide", claim="auto claim")
    model_backed = _add_decision(root, key="mw-model", trigger="m1")
    _add_signoff(root, "mw-model", signed_via="auto-llm", claim="auto llm claim")

    snapshot = _snapshot(root, redact=REDACTOR)
    records = _by_decision(snapshot)

    assert records[escalated].source.value == "system"
    assert any("auto-decide" in item for item in records[escalated].source.basis)
    assert records[escalated].stages["signoff"].detail == "auto-decide"
    assert records[escalated].actor.value is None, "a machine sign-off is not an actor"
    assert records[model_backed].source.value == "model", "the answer came from the model"
    assert records[model_backed].stages["signoff"].detail == "auto-llm"
    assert records[model_backed].source.value != "human"


def test_refresh_authority_change_is_system(tmp_path):
    root = _root(tmp_path)
    decision_id = _add_decision(root, key="mw-refresh")
    decide_archive.append_authority_change(
        _archive_path(root),
        dp="dp1-dispatch-type",
        key="mw-refresh",
        by="refresh",
        change="config refresh",
    )

    record = _by_decision(_snapshot(root))[decision_id]

    assert record.stages["authority_change"].state == "recorded"
    assert record.stages["authority_change"].actor == "system"
    assert any("by=refresh" in item for item in record.stages["authority_change"].basis)
    assert record.stages["authority_change"].result is None
    assert record.source.value != "human"
    assert record.status == "pending"


def test_dp_level_authority_change_reaches_every_decision_of_the_key(tmp_path):
    root = _root(tmp_path)
    first = _add_decision(root, key="mw-both", trigger="b1", now="2026-10-22T10:00:00+00:00")
    second = _add_decision(root, key="mw-both", trigger="b2", now="2026-10-22T10:01:00+00:00")
    decide_archive.append_authority_change(
        _archive_path(root),
        dp="dp1-dispatch-type",
        key="mw-both",
        by="signoff:continue",
        change="p0 confirmed",
        conclusion="continue",
    )

    snapshot = _snapshot(root, redact=REDACTOR)
    records = _by_decision(snapshot)

    for decision_id in (first, second):
        stage = records[decision_id].stages["authority_change"]
        assert stage.state == "recorded", decision_id
        assert stage.actor == "system", "signoff:* is a machine writer"
        assert any("dp-level" in item for item in stage.basis)
        assert stage.result == "continue"
    authority_records = [
        record for record in snapshot.records if record.record_kind == "authority"
    ]
    assert len(authority_records) == 1
    assert authority_records[0].key == "mw-both"


# ---------------------------------------------------------------------------
# 21. output surface: a legal shape is not a known-secret exemption (T07c)
# ---------------------------------------------------------------------------
#
# AC-005/design section 9 covers *every* string the reader emits, not only the fields
# the schema calls free text. ``SECRET`` below is a legal token / key /
# identity / decision-id shape, so every structural schema (``token``, ``key``,
# ``identity``, ``decision_id``, ``relpath``) accepts it verbatim. A value that
# the injected known-secret redactor recognises must still not be echoed: the
# reader omits it (``None``/dropped key + ``redaction.structural_withheld`` +
# the ``structural-secret-withheld`` flag) instead of emitting a placeholder
# that a consumer could mistake for a real id. Internal joins, opaque ids and
# the page filters keep using the *raw* value, so omission is output-only.


def _by_identity(snapshot: history.HistorySnapshot) -> dict[str, history.HistoryRecord]:
    return {record.identity: record for record in snapshot.records}


def _structural_fixture(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[pathlib.Path, str, str, str]:
    """The credential in structural fields, nested keys, captures and labels.

    The wire rows are written with a redactor that does *not* know the secret
    (a read-side known-secret set is allowed to be wider than the write-side
    one), so the stored capture text really holds it.
    """
    root = _root(tmp_path)
    shaped = _add_decision(
        root,
        key=SECRET,
        task_key=SECRET,
        trigger="a1",
        model=SECRET,
        transport=SECRET,
        answer={SECRET: {"value": "x", "confidence": 0.5}},
        now="2026-10-22T10:00:00+00:00",
    )
    unreachable = f"dp2-checkpoint-split:{SECRET}"
    # A legacy/foreign decide row: the writer refuses these shapes today, so the
    # reader's *own* closed schema is exercised on its documented token/identity
    # shapes (reason/escalated_reason are ``token``, policy is an echo mapping).
    raw_row = {
        "seq": 99,
        "prev_sha": "0" * 16,
        "kind": "decide",
        "decision_id": unreachable,
        "ts": "2026-10-22T10:01:00+00:00",
        "dp": "dp2-checkpoint-split",
        "key": "mw-reason",
        "task_key": SECRET,
        "state_digest": "0" * 16,
        "questions_version": "q-1234abcd",
        "available": False,
        "reason": SECRET,
        "answer": None,
        "authority": "human",
        "escalated_reason": SECRET,
        "acted": False,
        "actual_action": None,
        "outcome": "pending",
        "settled_by": None,
        "evidence_ref": None,
        "override_by": None,
        "override_reason": None,
        "ref_seq": None,
        "by": None,
        "change": None,
        "conclusion": None,
        "config_sha_after": None,
        "evidence_line": None,
        "mode": "auto",
        "model": SECRET,
        "transport": SECRET,
        "attempts": 1,
        "latency_ms": 4,
        "confidence": None,
        "confidence_source": None,
        "cost_tokens": None,
        "policy": {SECRET: 1, "safe_key": 2},
        "note": None,
    }
    _append_raw(_archive_path(root), json.dumps(raw_row).encode("utf-8") + b"\n")
    decide_archive.append_override(
        _archive_path(root),
        decision_id=shaped,
        dp="dp1-dispatch-type",
        key=SECRET,
        override_by=f"human:{SECRET}",
        override_reason=f"undo {SECRET}",
    )
    # human carriers under the credential-shaped key: the carrier path label
    # itself carries the credential
    _add_gate(root, gate_id="gate-0001", key=SECRET)
    _add_signoff(root, SECRET, signed_via="cli", claim=f"claim {SECRET}", monkeypatch=monkeypatch)
    # transport rows written by a redactor that does not know this value
    foreign = wire.SubstringRedactor(("foreign-redactor-value",))
    scope = _scope(root, decision_id=shaped, dp="dp1-dispatch-type", key=SECRET, redact=foreign)
    call = wire.new_call()
    wire.record_attempt_start(
        scope,
        call,
        request=f'{{"state":"{SECRET}"}}'.encode(),
        url_path=f"/v1/{SECRET}",
        model=SECRET,
    )
    wire.record_attempt_end(
        scope,
        call,
        response=f'{{"answers":{{"q-task":"{SECRET}"}}}}'.encode(),
        latency_ms=5,
        http_status=200,
        content_type="application/json",
        error_class=SECRET,
        error_detail=f"boom {SECRET}",
        usage={SECRET: 3, "input_tokens": 7},
    )
    wire.append_event(
        scope,
        wire.call_end_event(
            scope,
            call,
            attempts=1,
            latency_ms=9,
            available=True,
            reason=SECRET,
            confidence_source=SECRET,
            transport=SECRET,
            model=SECRET,
        ),
    )
    # a model-source record without human carriers: the derived provenance basis
    # quotes transport/model, so it is the value-quoting basis channel
    model_only = _add_decision(
        root,
        key="mw-model",
        trigger="m1",
        model=SECRET,
        transport=SECRET,
        now="2026-10-22T10:02:00+00:00",
    )
    return root, shaped, unreachable, model_only


def test_structural_known_secret_is_omitted_from_output(tmp_path, monkeypatch):
    root, shaped, unreachable, model_only = _structural_fixture(tmp_path, monkeypatch)

    snapshot = _snapshot(root, redact=REDACTOR)

    assert SECRET not in _all_payloads(snapshot), "no output string may echo the credential"
    records = _by_identity(snapshot)
    record = records["decision|" + shaped]
    payload = record.as_dict(detail=True)
    # structural fields with a legal shape are still not echoed
    assert payload["key"] is None
    assert payload["task_key"] is None
    assert payload["model"]["value"] is None and payload["transport"]["value"] is None
    assert payload["archive"]["model"] is None and payload["archive"]["transport"] is None
    assert payload["archive"]["answer"] == {}, "a credential-shaped mapping key is dropped"
    assert payload["archive_rows"][0]["override_by"] is None
    # a basis quoting the value is replaced by a fixed mark, never the value
    assert payload["source"]["value"] == "human"
    assert payload["source"]["basis"] == ["archive.override", "signoff:signed_via=cli (declared)"]
    assert payload["model"]["basis"] == ["archive.decide.model"]
    model_payload = records["decision|" + model_only].as_dict(detail=True)
    assert model_payload["source"]["value"] == "model"
    assert model_payload["source"]["basis"] == ["<basis withheld: known secret>"]
    assert model_payload["model"]["value"] is None
    assert model_payload["transport"]["value"] is None
    other_payload = records["decision|" + unreachable].as_dict(detail=True)
    assert other_payload["decision_id"] is None, "a credential-shaped decision id is not a handle"
    assert other_payload["dp"] == "dp2-checkpoint-split"
    assert other_payload["task_key"] is None
    assert other_payload["archive"]["reason"] is None
    assert other_payload["archive"]["escalated_reason"] is None
    assert other_payload["archive"]["policy"] == {"safe_key": 2}
    assert other_payload["stages"]["suggested"]["detail"] is None
    assert not any("escalated_reason=" in item for item in other_payload["source"]["basis"])
    # honest marks: counted, labelled by field name only, flagged, explained
    assert record.redaction.enabled is True
    assert record.redaction.structural_withheld >= 4
    assert "structural-secret-withheld" in record.flags
    assert any("structural" in item for item in record.redaction.basis)
    labels = " ".join(record.redaction.fields)
    assert "archive.model" in labels and "archive.transport" in labels
    assert SECRET not in labels
    assert other_payload["redaction"]["structural_withheld"] >= 4


def test_nested_capture_and_usage_copy_is_scrubbed(tmp_path, monkeypatch):
    root, shaped, _unreachable, _model_only = _structural_fixture(tmp_path, monkeypatch)

    snapshot = _snapshot(root, redact=REDACTOR)
    record = _by_identity(snapshot)["decision|" + shaped]

    assert SECRET not in _all_payloads(snapshot)
    payload = record.as_dict(detail=True)
    attempt = payload["calls"][0]["attempts"][0]
    assert attempt["request"]["text"] is None, "a capture copy is output text too"
    assert attempt["request"]["text_omitted"] is True
    assert attempt["request"]["byte_exact"] is False, "an omitted copy is never byte-exact"
    assert attempt["response"]["text"] is None
    assert attempt["response"]["text_omitted"] is True
    assert attempt["url_path"] is None
    assert attempt["model"] is None
    assert attempt["error_class"] is None
    assert attempt["error_detail"] == "boom <redacted>", "free text keeps its placeholder"
    assert attempt["usage"] == {"input_tokens": 7}, "a credential-shaped usage key is dropped"
    call = payload["calls"][0]
    assert call["reason"] is None and call["transport"] is None
    assert call["model"] is None and call["confidence_source"] is None
    # the counters themselves are still reported (only the key is not)
    assert payload["usage"]["counters"] == {"input_tokens": 7}
    # the fold itself is untouched: only the emitted copy was omitted
    assert record.call_counts.logical_calls == 1
    assert record.calls[0]["attempts"][0]["request"]["text"], "raw copies stay internal"


def test_structural_omission_keeps_internal_joins_and_handles(tmp_path, monkeypatch):
    root, shaped, _unreachable, _model_only = _structural_fixture(tmp_path, monkeypatch)

    snapshot = _snapshot(root, redact=REDACTOR)
    record = _by_identity(snapshot)["decision|" + shaped]
    payload = record.as_dict(detail=True)

    # internal joins ran on the raw value: the carriers were still read
    assert record.signoff is not None, "the raw join happened"
    assert record.key == SECRET, "internal fields are not rewritten"
    assert payload["key"] is None
    assert payload["signoff"]["key"] is None
    assert payload["signoff"]["path"] is None, "a path label carrying the credential is omitted"
    assert payload["signoff"]["conclusion"] == "continue"
    assert [gate["id"] for gate in payload["gates"]] == ["gate-0001"]
    assert payload["gates"][0]["key"] is None
    assert payload["stages"]["signoff"]["state"] == "recorded"
    assert payload["stages"]["human_override"]["state"] == "recorded"
    # internal ids are not rewritten by the output policy
    assert history.OPAQUE_ID_PATTERN.match(payload["opaque_id"])
    assert payload["opaque_id"] == history.opaque_id_for(
        record.project_id, record.scope, record.identity
    )
    assert snapshot.detail(record.opaque_id) is not None
    # ...and the page filter still selects by the raw value
    assert snapshot.page(key=SECRET).total == 1
    assert snapshot.page(key=SECRET).records[0].opaque_id == record.opaque_id
    # a placeholder is never a handle or a structural id
    assert "<redacted>" not in str(payload["decision_id"])
    assert "<redacted>" not in str(payload["opaque_id"])
    assert snapshot.detail("<redacted>") is None


def test_no_redactor_keeps_the_structural_contract(tmp_path, monkeypatch):
    root, shaped, _unreachable, _model_only = _structural_fixture(tmp_path, monkeypatch)

    snapshot = _snapshot(root)  # no injected known-secret set
    record = _by_identity(snapshot)["decision|" + shaped]
    other = _by_identity(snapshot)["decision|dp2-checkpoint-split:" + SECRET]

    # the documented fail-closed mode: free text omitted, structural values keep
    # their existing closed-shape contract (the reader never reads credentials
    # itself, so it cannot know which values are secret)
    assert record.redaction.enabled is False
    assert record.redaction.structural_withheld == 0
    assert "structural-secret-withheld" not in record.flags
    assert record.key == SECRET
    assert record.model.value == SECRET and record.transport.value == SECRET
    assert other.decision_id == "dp2-checkpoint-split:" + SECRET
    assert record.signoff["claim"] is None, "free text stays withheld"
    payload = record.as_dict(detail=True)
    assert payload["key"] == SECRET, "structural values keep their contract"
    assert payload["redaction"]["structural_withheld"] == 0
    assert "structural-secret-withheld" not in payload["flags"]
    assert record.signoff["path"].endswith("evidence/review/sign-final.md")


def test_secret_bearing_warning_is_not_echoed(tmp_path, monkeypatch):
    root, _shaped, _unreachable, _model_only = _structural_fixture(tmp_path, monkeypatch)
    # a sign-off file in another key dir that declares the credential as its key
    stray = decide_signoff.signoff_path(root, "mw-alpha")
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_text(
        f"conclusion: continue\nkey: {SECRET}\nsigned_via: cli\nclaim: x\n",
        encoding="utf-8",
        newline="\n",
    )

    snapshot = _snapshot(root, redact=REDACTOR)
    joined = "\n".join(snapshot.warnings)

    assert SECRET not in joined, "a warning never echoes the field value it reports"
    assert "signoff" in joined, "the mismatch is still reported"
    assert SECRET not in _all_payloads(snapshot)
    assert any("signoff" in warning for warning in snapshot.warnings)


def test_repeated_serialization_is_stable(tmp_path, monkeypatch):
    root, shaped, _unreachable, _model_only = _structural_fixture(tmp_path, monkeypatch)

    snapshot = _snapshot(root, redact=REDACTOR)
    record = _by_identity(snapshot)["decision|" + shaped]
    first = record.as_dict(detail=True)
    second = record.as_dict(detail=True)
    list_view = record.as_dict()

    assert first == second, "the output policy must not accumulate across calls"
    assert list_view == record.as_dict()
    assert first["redaction"]["structural_withheld"] == record.redaction.structural_withheld
    assert first["flags"] == second["flags"]
    # a page render and a detail render agree on the same record
    page_record = next(
        item for item in snapshot.page(limit=50).records if item.opaque_id == record.opaque_id
    )
    assert page_record.as_dict()["redaction"]["structural_withheld"] == first["redaction"][
        "structural_withheld"
    ]


# ---------------------------------------------------------------------------
# 22. page filters and the stored-vs-output capture layers (T07d)
# ---------------------------------------------------------------------------
#
# P2-b: ``HistoryPage.filters`` is a public output face. A filter value the
# injected known-secret set recognises is not echoed there either - while the
# *selection* keeps the raw value, so ``page(key=<secret>)`` still returns its
# one record. P2-a: an emitted capture copy carries two layers -
# ``capture_status``/``stored_len``/``captured_redacted_sha256`` describe what
# the writer stored, ``text_omitted``/``byte_exact``/``output_omitted`` describe
# this read's copy. P3-a: an empty free-text mapping key is dropped *and*
# counted. P3-b: raw record attributes are internal; only ``as_dict()`` /
# ``page()`` are safe for a consumer.


def _page_output(page: history.HistoryPage) -> str:
    """The whole page as a consumer may serialise it (records + filters)."""
    return json.dumps(
        {
            "records": [record.as_dict(detail=True) for record in page.records],
            "total": page.total,
            "limit": page.limit,
            "offset": page.offset,
            "has_more": page.has_more,
            "filters": page.filters,
            "filters_withheld": list(page.filters_withheld),
            "filters_basis": list(page.filters_basis),
        }
    )


def test_page_filters_omit_a_known_secret_without_changing_selection(tmp_path, monkeypatch):
    root, shaped, _unreachable, _model_only = _structural_fixture(tmp_path, monkeypatch)

    snapshot = _snapshot(root, redact=REDACTOR)
    page = snapshot.page(key=SECRET)
    record = _by_identity(snapshot)["decision|" + shaped]

    assert SECRET not in _page_output(page)
    assert page.total == 1, "the selection still uses the raw value"
    assert [item.opaque_id for item in page.records] == [record.opaque_id]
    assert page.filters["key"] is None, "a known secret is omitted, never echoed"
    assert page.filters_withheld == ("key",)
    assert all(SECRET not in name for name in page.filters_withheld), "names only, never values"
    assert any("known-secret" in item for item in page.filters_basis)
    # the other filter slots are emitted normally
    assert page.filters["dp"] == ""
    assert page.filters["scope"] == "production"
    # every filter slot takes the same policy, whether or not it selected a row
    dp_page = snapshot.page(dp=SECRET)
    assert dp_page.total == 0
    assert dp_page.filters["dp"] is None
    assert dp_page.filters_withheld == ("dp",)
    assert SECRET not in _page_output(dp_page)
    # internal fields keep the raw value (omission is output-only)
    assert record.key == SECRET
    assert snapshot.page(key=SECRET).filters == page.filters, "repeatable, no accumulation"


def test_page_filters_keep_legal_values_and_the_no_redactor_contract(tmp_path, monkeypatch):
    root, _shaped, _unreachable, _model_only = _structural_fixture(tmp_path, monkeypatch)

    snapshot = _snapshot(root, redact=REDACTOR)
    legal = snapshot.page(key="mw-model", source="model")
    assert legal.total == 1
    assert legal.filters == {
        "key": "mw-model",
        "dp": "",
        "source": "model",
        "status": "",
        "scope": "production",
    }, "a legal filter value is neither clipped nor rewritten"
    assert legal.filters_withheld == ()
    assert snapshot.page(key="mw-model", source="model").filters == legal.filters

    raw_snapshot = _snapshot(root)  # no redactor: the documented raw contract stays
    raw_page = raw_snapshot.page(key=SECRET)
    assert raw_page.total == 1
    assert raw_page.filters["key"] == SECRET
    assert raw_page.filters_withheld == ()
    assert any("no redactor" in item for item in raw_page.filters_basis)


def test_invalid_filter_errors_do_not_echo_the_value(tmp_path, monkeypatch):
    root, _shaped, _unreachable, _model_only = _structural_fixture(tmp_path, monkeypatch)

    snapshot = _snapshot(root, redact=REDACTOR)
    # A rejected filter value is caller input a browser may carry: the error
    # names the filter and its allowed set, never the value.
    with pytest.raises(history.HistoryError) as status_error:
        snapshot.page(status=SECRET)
    assert SECRET not in str(status_error.value)
    assert "status" in str(status_error.value)
    with pytest.raises(history.HistoryError) as path_error:
        snapshot.page(key=f"a/{SECRET}")
    assert SECRET not in str(path_error.value)
    assert "key" in str(path_error.value)
    for bad in ({"source": SECRET}, {"scope": SECRET}, {"dp": f"../{SECRET}"}):
        with pytest.raises(history.HistoryError) as raised:
            snapshot.page(**bad)
        assert SECRET not in str(raised.value)


def test_capture_status_stays_a_stored_fact_while_output_omission_is_marked(tmp_path, monkeypatch):
    root, shaped, _unreachable, _model_only = _structural_fixture(tmp_path, monkeypatch)

    snapshot = _snapshot(root, redact=REDACTOR)
    record = _by_identity(snapshot)["decision|" + shaped]
    payload = record.as_dict(detail=True)
    attempt = payload["calls"][0]["attempts"][0]
    copy = attempt["request"]
    stored = record.calls[0]["attempts"][0]["request"]

    # storage facts: written by decision_wire, read-only here
    assert attempt["capture_status"] == "ok"
    assert record.capture_status == "ok"
    assert copy["stored_len"] > 0
    assert copy["wire_len"] is not None
    assert len(copy["captured_redacted_sha256"]) == 64
    assert copy["captured_redacted_sha256"] == stored["captured_redacted_sha256"]
    # output facts: this read's copy
    assert copy["text"] is None
    assert copy["text_omitted"] is True
    assert copy["byte_exact"] is False
    assert copy["output_omitted"] is True, "an output-only omission has its own closed-set field"
    # the layers are not conflated: a stored "ok" is not re-claimed as complete output
    assert "capture-incomplete" not in record.flags, "the stored row is still ok"
    assert "capture-output-omitted" in record.flags
    assert "capture-output-omitted" in payload["flags"]
    # the internal fold keeps the stored copy untouched
    assert stored["text"]
    assert stored["text_omitted"] is False
    assert "output_omitted" not in stored
    # repeated serialisation does not accumulate the marker
    assert record.as_dict(detail=True) == payload


def test_empty_free_text_mapping_key_is_counted_and_not_echoed(tmp_path):
    root = _root(tmp_path)
    _add_decision(root, key="mw-alpha", trigger="t1")
    raw_row = {
        "seq": 2,
        "prev_sha": "0" * 16,
        "kind": "decide",
        "decision_id": "dp2-checkpoint-split:keys",
        "ts": "2026-10-22T10:00:00+00:00",
        "dp": "dp2-checkpoint-split",
        "key": "mw-keys",
        "task_key": None,
        "state_digest": "0" * 16,
        "questions_version": "q-1234abcd",
        "available": True,
        "reason": None,
        "answer": {"q-task": "x"},
        "authority": "advisory",
        "escalated_reason": None,
        "acted": False,
        "actual_action": None,
        "outcome": "pending",
        "settled_by": None,
        "evidence_ref": None,
        "override_by": None,
        "override_reason": None,
        "ref_seq": None,
        "by": None,
        "change": None,
        "conclusion": None,
        "config_sha_after": None,
        "evidence_line": None,
        "mode": "auto",
        "model": "jev-latest",
        "transport": "timi-decisions",
        "attempts": 1,
        "latency_ms": 1,
        "confidence": 0.9,
        "confidence_source": "api",
        "cost_tokens": None,
        "policy": {"": 1, "safe_key": 2},
        "note": None,
    }
    _append_raw(_archive_path(root), json.dumps(raw_row).encode("utf-8") + b"\n")

    snapshot = _snapshot(root, redact=REDACTOR)
    record = _by_decision(snapshot)["dp2-checkpoint-split:keys"]
    payload = record.as_dict(detail=True)

    assert payload["archive"]["policy"] == {"safe_key": 2}, "an empty key is not echoed"
    assert "" not in payload["archive"]["policy"]
    assert record.redaction.omitted_fields >= 1, "the dropped entry is counted"
    assert any("<key>" in name for name in record.redaction.fields)
    assert "free-text-omitted" in record.flags


def test_output_policy_documents_capture_layers_and_raw_attributes():
    module_doc = history.__doc__ or ""
    record_doc = history.HistoryRecord.__doc__ or ""

    # P2-a: one place states which fields describe storage, which the output copy
    assert "capture_status" in module_doc
    assert "stored_len" in module_doc
    assert "output_omitted" in module_doc
    # P2-b: the filter output policy is documented next to the record policy
    assert "filters_withheld" in module_doc
    # P3-b: raw attributes are internal; as_dict()/page() are the safe serialisation
    assert "as_dict()" in record_doc
    assert "raw" in record_doc
    assert "internal" in record_doc
