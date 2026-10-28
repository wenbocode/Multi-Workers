"""test_decision_context_history.py - T06 workbench projection on the one history fold.

The reader under test (``decision_history``) already folds every recorded carrier
into one project history. T06 adds *one* pure projection over that same read
chain (design D006): a ``workbench`` object on every record and a ``facets``
object on the history page. There is no second store, no second API and no
inferred link:

* a record is ``record_version=2`` only when a real ``record-start`` creation
  fact (``decision_lifecycle``, T02) declares it - a missing wire row, a failed
  capture or an absent feedback row never makes a v2 record legacy, and no row
  without a creation fact is promoted to v2;
* the ten DAG nodes are ``key, role, dp, input, decide, request, model,
  response, receipt, action`` in that fixed order, each ``{id,label,status,
  detail}`` with ``status`` in ``observed/missing/failed``; every ``detail`` is
  an already-sanitised structure (the stored capture copy, the recorded
  lifecycle fact, the registry question) - the reader never composes a body;
* the association is explicit only: ``record-start`` carries ``logical_id`` /
  ``key`` / ``task_key`` / ``initiator_role`` / ``retry_of``, and any ledger row
  that carries both ``logical_id`` and ``decision_id`` (``decision_lifecycle``
  always does) ties the decision facts to the logical record. Rows are never
  joined by key or by timestamp, a retry keeps its own record pointing at the
  previous one, and two logical ids claiming the same decision are reported as
  ambiguous instead of attributed;
* ``consumed`` is receipt, not completion: only a recorded ``settled`` outcome
  (or, for dp25, a recorded signoff-file write) can make a record
  ``completed``; a feedback write failure stays visible and never revokes a real
  signoff.

The tests use the real writers for setup (``decision_lifecycle`` /
``decision_wire`` / ``decide_archive``), isolated ``tmp_path`` control roots, a
synthetic known-secret redactor and no credentials, network or production file.
"""

from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

import decide_archive
import decide_signoff
import decision_history as history
import decision_lifecycle as lifecycle
import decision_signoff_result
import decision_wire as wire

SECRET = "TEST-SECRET-abc123456789"
REDACTOR = wire.SubstringRedactor((SECRET,))

_QUIET: list[str] = []


@pytest.fixture(autouse=True)
def _isolated_env(tmp_path, monkeypatch: pytest.MonkeyPatch):
    """No test here may read a real home config or a real credential.

    The reader itself never discovers credentials (the known-secret set is
    injected), so this fixture is the belt-and-braces guarantee: a temp HOME /
    ``USERPROFILE`` / ``PI_CODING_AGENT_DIR`` and no provider credentials in the
    process environment.
    """
    home = tmp_path / "home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(tmp_path / "pi-agent"))
    for name in (
        "ANTHROPIC_API_KEY",
        "ANTHROPIC_AUTH_TOKEN",
        "OPENAI_API_KEY",
        "GOOGLE_API_KEY",
        "TIMI_API_KEY",
        "MW_TIMI_API_KEY",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def _quiet(message: str) -> None:
    _QUIET.append(message)


# ---------------------------------------------------------------------------
# Harness: real writers, isolated roots
# ---------------------------------------------------------------------------


def _root(tmp_path: pathlib.Path, name: str = "proj") -> pathlib.Path:
    root = tmp_path / name
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    return root


def _store(root: pathlib.Path) -> lifecycle.LifecycleStore:
    return lifecycle.LifecycleStore.production(root, redact=REDACTOR, warn=_quiet)


def _meta(
    *,
    key: str = "mw-alpha",
    task_key: str | None = "dc-t1",
    initiator_role: str = "pm",
    retry_of: str | None = None,
) -> lifecycle.DecisionMeta:
    return lifecycle.DecisionMeta.create(
        key, task_key=task_key, initiator_role=initiator_role, retry_of=retry_of
    )


def _scope(
    root: pathlib.Path,
    *,
    decision_id: str | None,
    dp: str | None = None,
    key: str | None = "mw-alpha",
    task_key: str | None = None,
    sink: pathlib.Path | None = None,
    redact: object = REDACTOR,
) -> wire.WireScope:
    return wire.WireScope(
        sink=sink or wire.production_wire_sink(root),
        project_id=wire.project_id_for(root),
        scope_kind="production",
        origin="producer",
        decision_id=decision_id,
        dp=dp,
        key=key,
        task_key=task_key,
        actor_kind="system",
        actor_id="producer",
        redact=redact,
        warn=_quiet,
    )


def _add_call(
    root: pathlib.Path,
    *,
    decision_id: str,
    dp: str,
    key: str | None = "mw-alpha",
    request: bytes = b'{"material":{"question":"which option?"}}',
    response: bytes = b'{"answer":"pm-handoff"}',
    available: bool = True,
    model: str = "jev-latest",
    transport: str = "timi-decisions",
    redact: object = REDACTOR,
) -> str:
    """One real transport attempt through the managed wire writer."""
    scope = _scope(root, decision_id=decision_id, dp=dp, key=key, redact=redact)
    call = wire.new_call()
    wire.record_attempt_start(
        scope, call, request=request, url_path="/v1/decisions", model=model
    )
    wire.record_attempt_end(
        scope,
        call,
        response=response,
        latency_ms=11,
        http_status=200,
        content_type="application/json",
        usage={"input_tokens": 5, "output_tokens": 3},
    )
    wire.append_event(
        scope,
        wire.call_end_event(
            scope,
            call,
            attempts=1,
            latency_ms=11,
            available=available,
            answers_present=available,
            confidence=0.9 if available else None,
            confidence_source="api" if available else None,
            transport=transport,
            model=model,
        ),
    )
    return call.call_id


def _add_decision_end(
    root: pathlib.Path,
    *,
    decision_id: str,
    dp: str,
    state_digest: str = "0123456789abcdef",
) -> None:
    scope = _scope(root, decision_id=decision_id, dp=dp)
    wire.append_event(
        scope,
        wire.decision_end_event(
            scope,
            status="ok",
            archive="created",
            state_digest=state_digest,
            questions_version="q-1234abcd",
            mode="auto",
            intent="decide",
        ),
    )


def _add_book(
    root: pathlib.Path,
    *,
    decision_id: str,
    dp: str,
    body: bytes,
) -> None:
    scope = _scope(root, decision_id=decision_id, dp=dp)
    wire.append_event(
        scope,
        wire.book_snapshot_event(
            scope,
            book=body,
            book_ref="input-memory",
            book_version="v1",
            file_sha256="0" * 64,
            book_sha256="1" * 64,
        ),
    )


def _by_decision(snapshot: history.HistorySnapshot) -> dict[str, history.HistoryRecord]:
    return {
        record.decision_id: record
        for record in snapshot.records
        if record.scope == "production" and record.decision_id
    }


def _by_key(snapshot: history.HistorySnapshot, key: str) -> list[history.HistoryRecord]:
    return [
        record
        for record in snapshot.records
        if record.scope == "production" and record.key == key
    ]


def _workbench(record: history.HistoryRecord, *, detail: bool = True) -> dict[str, object]:
    payload = record.as_dict(detail=detail)
    workbench = payload["workbench"]
    assert isinstance(workbench, dict)
    return workbench


def _node_map(record: history.HistoryRecord, *, detail: bool = True) -> dict[str, dict]:
    nodes = _workbench(record, detail=detail)["nodes"]
    assert isinstance(nodes, list)
    return {node["id"]: node for node in nodes}


def _all_payloads(snapshot: history.HistorySnapshot) -> str:
    parts = [repr(record.as_dict(detail=True)) for record in snapshot.records]
    page = snapshot.page(limit=200)
    parts.append(repr([record.as_dict() for record in page.records]))
    parts.append(repr(page.facets.as_dict()))
    parts.append(repr(snapshot.warnings))
    return "\n".join(parts)


def _sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_signoff(
    root: pathlib.Path,
    key: str,
    meta: lifecycle.DecisionMeta,
    decision_id: str,
) -> tuple[decision_signoff_result.SignoffResult, pathlib.Path, str]:
    """Write a real (valid) dp25 sign-off file + result record; return the facts.

    Uses the shipped writers (``build_result`` / ``write_result`` /
    ``decide_signoff.render`` + ``write_signoff``), so the file is exactly what
    the production path writes — never a hand-written fixture line set.
    """
    key_dir = root / ".agenticdoc" / key
    key_dir.mkdir(parents=True, exist_ok=True)
    facts = decide_signoff.collect(key_dir, key)
    material = {
        "delivery_goal": "prove the file is the completion authority",
        "actual_completion": "the history reader validates the written file",
        "verification_evidence": {"verified": [], "unverified": []},
        "unfinished_impact": [],
    }
    result = decision_signoff_result.build_result(
        key_dir,
        key=key,
        logical_id=meta.logical_id,
        decision_id=decision_id,
        conclusion="finalize",
        material=material,
        facts=facts,
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
        task_key=meta.task_key,
        initiator_role=meta.initiator_role,
        retry_of=meta.retry_of,
    )
    decision_signoff_result.write_result(key_dir, result, redact=REDACTOR)
    text = decide_signoff.render(facts, "finalize", None, key, None, result=result)
    path = decide_signoff.write_signoff(key_dir, key, text)
    return result, path, hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 1. the fixed ten-node DAG (PM-published schema)
# ---------------------------------------------------------------------------


def test_v2_record_exposes_the_fixed_ten_node_workbench(tmp_path):
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    assert lifecycle.record_start(store, meta).recorded
    decision_id = "dp3-worker-clarify:abc123"
    _add_call(root, decision_id=decision_id, dp="dp3-worker-clarify")
    _add_decision_end(root, decision_id=decision_id, dp="dp3-worker-clarify")
    lifecycle.record_consumed(
        store, meta, decision_id=decision_id, dp="dp3-worker-clarify", answer="pm-handoff"
    )
    lifecycle.record_executed(
        store,
        meta,
        decision_id=decision_id,
        dp="dp3-worker-clarify",
        action="pm-handoff",
        result="handed the choice back to the PM",
    )
    lifecycle.record_settled(
        store, meta, decision_id=decision_id, dp="dp3-worker-clarify", outcome="ok"
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]
    workbench = _workbench(record)

    assert set(workbench) == {
        "record_version",
        "processing_state",
        "key",
        "task_key",
        "question_summary",
        "dp_id",
        "selection",
        "initiator_role",
        "nodes",
    }
    assert workbench["record_version"] == 2
    assert workbench["processing_state"] == "completed"
    assert workbench["key"] == "mw-alpha"
    assert workbench["task_key"] == "dc-t1"
    assert workbench["initiator_role"] == "pm"
    assert workbench["dp_id"] == "dp3-worker-clarify"
    assert workbench["selection"] == "pm-handoff"
    assert isinstance(workbench["question_summary"], str) and workbench["question_summary"]

    node_ids = [node["id"] for node in workbench["nodes"]]
    assert node_ids == list(history.WORKBENCH_NODE_IDS)
    assert node_ids == [
        "key",
        "role",
        "dp",
        "input",
        "decide",
        "request",
        "model",
        "response",
        "receipt",
        "action",
    ]
    for node in workbench["nodes"]:
        assert set(node) == {"id", "label", "status", "detail"}
        assert node["status"] in history.NODE_STATUSES
        assert node["label"] == history.WORKBENCH_NODE_LABELS[node["id"]]
        assert isinstance(node["detail"], dict)
        basis = node["detail"]["basis"]
        assert isinstance(basis, list) and basis
        assert all(isinstance(item, str) for item in basis)

    nodes = _node_map(record)
    assert all(nodes[name]["status"] == "observed" for name in history.WORKBENCH_NODE_IDS)
    assert nodes["key"]["detail"]["logical_id"] == meta.logical_id
    assert nodes["key"]["detail"]["retry_of"] is None
    assert nodes["role"]["detail"]["initiator_role"] == "pm"
    assert nodes["dp"]["detail"]["dp_id"] == "dp3-worker-clarify"
    assert nodes["input"]["detail"]["state_digest"] == "0123456789abcdef"
    assert nodes["decide"]["detail"]["available"] is True
    assert nodes["model"]["detail"]["model"] == "jev-latest"
    assert nodes["model"]["detail"]["transport"] == "timi-decisions"
    assert nodes["response"]["detail"]["attempts"][0]["usage"] == {
        "input_tokens": 5,
        "output_tokens": 3,
    }
    assert nodes["receipt"]["detail"]["consumed"]["answer"] == "pm-handoff"
    assert nodes["receipt"]["detail"]["signoff"] is None
    assert nodes["action"]["detail"]["settled"]["outcome"] == "ok"
    assert nodes["action"]["detail"]["executed"][0]["action"] == "pm-handoff"


# ---------------------------------------------------------------------------
# 2. list vs detail: the real capture only in the single-record read
# ---------------------------------------------------------------------------


def test_detail_carries_the_stored_capture_and_the_list_does_not(tmp_path):
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    lifecycle.record_start(store, meta)
    decision_id = "dp1-dispatch-type:req-1"
    request = b'{"material":{"task_goal":"reach the goal"}}'
    response = b'{"answers":{"triage_type":"coding"}}'
    _add_call(root, decision_id=decision_id, dp="dp1-dispatch-type", request=request, response=response)
    lifecycle.record_consumed(
        store, meta, decision_id=decision_id, dp="dp1-dispatch-type", answer="coding"
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]

    listed = _node_map(record, detail=False)
    assert listed == {}, "the list projection never carries node bodies"
    assert _workbench(record, detail=False)["nodes"] == []

    nodes = _node_map(record)
    attempt = nodes["request"]["detail"]["attempts"][0]
    assert attempt["request"]["text"] == request.decode("utf-8")
    assert attempt["method"] == "POST"
    assert attempt["url_path"] == "/v1/decisions"
    assert nodes["response"]["detail"]["attempts"][0]["response"]["text"] == response.decode(
        "utf-8"
    )
    assert nodes["response"]["detail"]["attempts"][0]["http_status"] == 200
    assert nodes["receipt"]["detail"]["consumed"]["answer"] == "coding"


def test_book_snapshot_body_is_read_as_the_recorded_input(tmp_path):
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    lifecycle.record_start(store, meta)
    decision_id = "dp3-worker-clarify:book-1"
    body = b'{"dp":"dp3-worker-clarify","question":"which option?"}'
    _add_book(root, decision_id=decision_id, dp="dp3-worker-clarify", body=body)
    lifecycle.record_consumed(
        store, meta, decision_id=decision_id, dp="dp3-worker-clarify", answer="a"
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    nodes = _node_map(_by_decision(snapshot)[decision_id])
    book = nodes["input"]["detail"]["book"]
    assert book["text"] == body.decode("utf-8"), "the stored book body, not a summary"
    assert book["byte_exact"] is True
    assert nodes["input"]["detail"]["book_ref"] == "input-memory"
    assert nodes["input"]["status"] == "observed"


# ---------------------------------------------------------------------------
# 2b. Readable policy facts + input material (T10)
# ---------------------------------------------------------------------------


def test_policy_facts_and_material_are_detail_only_and_never_guessed(tmp_path):
    """T10: the decide/input node details carry the recorded facts, list does not."""
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    lifecycle.record_start(store, meta)
    decision_id = "dp1-dispatch-type:readable-1"
    state = {"task_goal": "readable goal", "task_deliverables": "report.md"}
    document = {
        "kind": "input-state",
        "decision_id": decision_id,
        "dp": "dp1-dispatch-type",
        "questions_version": "q-ac4a6184",
        "state_digest": "0123456789abcdef",
        "candidates": {},
        "state": state,
        "policy": {"min_confidence": 0.66, "max_questions": 8, "timeout_s": 20},
    }
    _add_book(
        root,
        decision_id=decision_id,
        dp="dp1-dispatch-type",
        body=json.dumps(document, ensure_ascii=False).encode("utf-8"),
    )
    _add_call(root, decision_id=decision_id, dp="dp1-dispatch-type")
    decide_archive.append_decide(
        root / ".agenticdoc" / "_autopilot" / "decisions.jsonl",
        dp="dp1-dispatch-type",
        key="mw-alpha",
        task_key="dc-t1",
        trigger_id="readable-1",
        state=state,
        questions_version="q-ac4a6184",
        available=True,
        authority="human",
        answer={"triage_type": {"value": "research", "confidence": 0.5}},
        reason=None,
        escalated_reason="low-confidence",
        acted=False,
        actual_action=None,
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        attempts=1,
        latency_ms=12,
        confidence=0.5,
        confidence_source="api",
        policy={"min_confidence": 0.8, "max_questions": 8, "timeout_s": 20},
        now="2026-10-23T10:00:00+00:00",
    )
    lifecycle.record_consumed(
        store, meta, decision_id=decision_id, dp="dp1-dispatch-type", answer="research"
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]
    nodes = _node_map(record)
    policy_result = nodes["decide"]["detail"]["policy_result"]
    assert policy_result["disposition"] == "not-adopted"
    assert policy_result["confidence"] == 0.5
    assert policy_result["selection"] == "research"
    assert policy_result["min_confidence"] == 0.66, (
        "the snapshot the decision wrote is the most exact recorded threshold"
    )
    assert nodes["input"]["detail"]["material"] == state

    page = snapshot.page(limit=10)
    listed = [item.as_dict() for item in page.records]
    assert all(item["workbench"]["nodes"] == [] for item in listed)
    assert "policy_result" not in repr(listed), "the list page carries no node bodies"


# ---------------------------------------------------------------------------
# 3. legacy rows stay legacy and get no DAG
# ---------------------------------------------------------------------------


def test_legacy_record_is_legacy_with_no_nodes(tmp_path):
    root = _root(tmp_path)
    # An archive row + wire capture written without any v2 creation fact: the
    # old producers are still readable, but nothing here is promoted to v2.
    decide_archive.append_decide(
        root / ".agenticdoc" / "_autopilot" / "decisions.jsonl",
        dp="dp1-dispatch-type",
        key="mw-legacy",
        task_key=None,
        trigger_id="old-1",
        state={"a": 1},
        questions_version="q-1234abcd",
        available=True,
        authority="advisory",
        answer={"triage_type": {"value": "coding", "confidence": 0.9}},
        reason=None,
        escalated_reason=None,
        acted=False,
        actual_action=None,
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        attempts=1,
        latency_ms=12,
        confidence=0.9,
        confidence_source="api",
        now="2026-10-22T10:00:00+00:00",
    )
    _add_call(root, decision_id="dp1-dispatch-type:old-1", dp="dp1-dispatch-type", key=None)

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)["dp1-dispatch-type:old-1"]
    workbench = _workbench(record)

    assert workbench["record_version"] is None
    assert workbench["processing_state"] == "legacy"
    assert workbench["initiator_role"] is None
    assert workbench["nodes"] == [], "no v2 creation fact -> no DAG, not even in detail"
    assert _node_map(record) == {}
    assert workbench["key"] == "mw-legacy"
    assert workbench["dp_id"] == "dp1-dispatch-type"
    assert workbench["selection"] is not None, "the recorded answer is still readable"


# ---------------------------------------------------------------------------
# 4. facets are one snapshot, not the filtered window
# ---------------------------------------------------------------------------


def test_facets_cover_the_whole_snapshot_not_the_page(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    for key, dp, trigger in (
        ("mw-alpha", "dp1-dispatch-type", "one"),
        ("mw-alpha", "dp2-checkpoint-split", "two"),
        ("mw-beta", "dp3-worker-clarify", "three"),
    ):
        meta = _meta(key=key, task_key=None, initiator_role="coding")
        lifecycle.record_start(store, meta)
        decision_id = f"{dp}:{trigger}"
        lifecycle.record_consumed(store, meta, decision_id=decision_id, dp=dp, answer="x")

    snapshot = history.load_history(root, redact=REDACTOR)
    page = snapshot.page(key="mw-beta", limit=1)

    assert page.total == 1
    assert page.facets.as_dict() == {
        "keys": ["mw-alpha", "mw-beta"],
        "dps": ["dp1-dispatch-type", "dp2-checkpoint-split", "dp3-worker-clarify"],
    }
    narrowed = snapshot.page(limit=1, offset=0)
    assert narrowed.facets.as_dict() == page.facets.as_dict(), (
        "facets are one snapshot computation: pagination does not change them"
    )


# ---------------------------------------------------------------------------
# 5. consumed is receipt, not completion
# ---------------------------------------------------------------------------


def test_consumed_alone_is_processing(tmp_path):
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    lifecycle.record_start(store, meta)
    decision_id = "dp1-dispatch-type:consumed-only"
    _add_call(root, decision_id=decision_id, dp="dp1-dispatch-type")
    lifecycle.record_consumed(
        store, meta, decision_id=decision_id, dp="dp1-dispatch-type", answer="coding"
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]
    workbench = _workbench(record)
    nodes = _node_map(record)

    assert workbench["processing_state"] == "processing", (
        "receipt is not completion (AC-014)"
    )
    assert nodes["receipt"]["status"] == "observed"
    assert nodes["action"]["status"] == "missing"
    assert nodes["action"]["detail"]["settled"] is None


# ---------------------------------------------------------------------------
# 6. the settled outcome owns completed / failed
# ---------------------------------------------------------------------------


def test_settled_outcome_decides_completed_or_failed(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    outcomes = {}
    for trigger, outcome in (("ok-1", "ok"), ("rework-1", "rework")):
        meta = _meta()
        lifecycle.record_start(store, meta)
        decision_id = f"dp2-checkpoint-split:{trigger}"
        _add_call(root, decision_id=decision_id, dp="dp2-checkpoint-split")
        lifecycle.record_consumed(store, meta, decision_id=decision_id, dp="dp2-checkpoint-split")
        lifecycle.record_settled(
            store, meta, decision_id=decision_id, dp="dp2-checkpoint-split", outcome=outcome
        )
        outcomes[decision_id] = outcome

    snapshot = history.load_history(root, redact=REDACTOR)
    by_decision = _by_decision(snapshot)
    ok_record = by_decision["dp2-checkpoint-split:ok-1"]
    rework_record = by_decision["dp2-checkpoint-split:rework-1"]

    assert _workbench(ok_record)["processing_state"] == "completed"
    assert _workbench(rework_record)["processing_state"] == "failed"
    assert _node_map(ok_record)["action"]["detail"]["settled"]["outcome"] == "ok"
    assert _node_map(rework_record)["action"]["status"] == "failed"


def test_archive_settle_is_a_real_settlement_fact(tmp_path):
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    lifecycle.record_start(store, meta)
    decision_id = "dp1-dispatch-type:arch-1"
    _add_call(root, decision_id=decision_id, dp="dp1-dispatch-type")
    lifecycle.record_consumed(
        store, meta, decision_id=decision_id, dp="dp1-dispatch-type", answer="coding"
    )
    decide_archive.append_settle(
        root / ".agenticdoc" / "_autopilot" / "decisions.jsonl",
        decision_id=decision_id,
        dp="dp1-dispatch-type",
        key="mw-alpha",
        task_key="dc-t1",
        outcome="ok",
        settled_by="pm-auto",
        now="2026-10-22T11:00:00+00:00",
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]
    assert _workbench(record)["processing_state"] == "completed"
    assert _node_map(record)["action"]["detail"]["settled"]["outcome"] == "ok"


# ---------------------------------------------------------------------------
# 7. dp25 signoff: a real file write completes, feedback failure stays visible
# ---------------------------------------------------------------------------


def test_signoff_completes_and_a_feedback_failure_does_not_revoke_it(tmp_path):
    root = _root(tmp_path)
    meta = _meta(initiator_role="pm")
    store = _store(root)
    lifecycle.record_start(store, meta, decision_id=f"dp25-signoff-conclusion:{meta.logical_id}")
    decision_id = f"dp25-signoff-conclusion:{meta.logical_id}"
    _add_call(root, decision_id=decision_id, dp="dp25-signoff-conclusion")
    lifecycle.record_consumed(
        store, meta, decision_id=decision_id, dp="dp25-signoff-conclusion", answer="finalize"
    )
    result, path, file_sha = _write_signoff(root, meta.key, meta, decision_id)
    written = lifecycle.record_signoff(
        store,
        meta,
        decision_id=decision_id,
        dp="dp25-signoff-conclusion",
        evidence_path="evidence/review/sign-final.md",
        evidence_sha256=file_sha,
        snapshot_sha256=result.snapshot_sha256,
    )
    assert written.recorded
    # The independent failure fact of a later feedback write: it must be shown,
    # never used to roll the real signoff back. It lives in the managed failure
    # sidecar (``<ledger>-errors.jsonl``), not in the feedback ledger.
    error_scope = _scope(
        root,
        decision_id=decision_id,
        dp="dp25-signoff-conclusion",
        sink=store.error_sink,
    )
    wire.append_event(
        error_scope,
        wire.lifecycle_error_event(
            error_scope,
            logical_id=meta.logical_id,
            stage="settled",
            error_class="append",
            attempted_event_id="se-1",
            detail="settled write failed: append",
        ),
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]
    workbench = _workbench(record)
    nodes = _node_map(record)

    assert workbench["processing_state"] == "completed"
    assert nodes["receipt"]["status"] == "observed"
    signoff = nodes["receipt"]["detail"]["signoff"]
    assert signoff["evidence_path"] == "evidence/review/sign-final.md"
    assert signoff["evidence_sha256"] == file_sha
    assert signoff["file_verified"] is True, (
        "the approval is the validated file (logical id + recorded snapshot), not the row"
    )
    assert signoff["file_sha256"] == file_sha
    assert signoff["file_matches_recorded_evidence"] is True
    assert signoff["snapshot_sha256"] == result.snapshot_sha256
    assert signoff["recorded"] is not None
    assert nodes["action"]["detail"]["errors"], "the feedback failure is visible"
    assert nodes["action"]["detail"]["errors"][0]["stage"] == "settled"
    assert workbench["record_version"] == 2

    # A file written for ANOTHER logical id never completes this record: the
    # expected id is exact, not "the latest sign-off file".
    other = _meta(initiator_role="pm")
    _write_signoff(root, other.key, other, f"dp25-signoff-conclusion:{other.logical_id}")
    again = history.load_history(root, redact=REDACTOR)
    other_nodes = _node_map(_by_decision(again)[decision_id])
    mismatched = other_nodes["receipt"]["detail"]["signoff"]
    assert mismatched["file_verified"] is False
    assert "expected decision" in (mismatched["file_reason"] or "")
    assert _workbench(_by_decision(again)[decision_id])["processing_state"] == "failed"


def test_dp25_finalize_without_a_recorded_signoff_is_not_completed(tmp_path):
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    lifecycle.record_start(store, meta)
    decision_id = "dp25-signoff-conclusion:finalize-nosign"
    _add_call(root, decision_id=decision_id, dp="dp25-signoff-conclusion")
    lifecycle.record_consumed(
        store, meta, decision_id=decision_id, dp="dp25-signoff-conclusion", answer="finalize"
    )
    lifecycle.record_settled(
        store, meta, decision_id=decision_id, dp="dp25-signoff-conclusion", outcome="ok"
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]
    nodes = _node_map(record)

    assert _workbench(record)["processing_state"] == "processing", (
        "dp25 finalize is only completed by a validated sign-off file"
    )
    signoff = nodes["receipt"]["detail"]["signoff"]
    assert signoff["recorded"] is None
    assert signoff["file_verified"] is False
    assert "missing" in signoff["file_reason"]
    assert nodes["action"]["detail"]["settled"]["outcome"] == "ok"
    assert nodes["action"]["status"] == "observed"


def test_continue_and_user_confirm_do_not_fabricate_a_signoff(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    for trigger, action in (("cont-1", "continue"), ("confirm-1", "user-confirm")):
        meta = _meta()
        lifecycle.record_start(store, meta)
        decision_id = f"dp25-signoff-conclusion:{trigger}"
        _add_call(root, decision_id=decision_id, dp="dp25-signoff-conclusion")
        lifecycle.record_consumed(
            store, meta, decision_id=decision_id, dp="dp25-signoff-conclusion", answer=action
        )
        lifecycle.record_executed(
            store,
            meta,
            decision_id=decision_id,
            dp="dp25-signoff-conclusion",
            action=action,
            result=f"PM handled the {action} branch",
        )
        lifecycle.record_settled(
            store, meta, decision_id=decision_id, dp="dp25-signoff-conclusion", outcome="ok"
        )

    snapshot = history.load_history(root, redact=REDACTOR)
    by_decision = _by_decision(snapshot)
    for trigger in ("cont-1", "confirm-1"):
        record = by_decision[f"dp25-signoff-conclusion:{trigger}"]
        nodes = _node_map(record)
        signoff = nodes["receipt"]["detail"]["signoff"]
        assert signoff["recorded"] is None, "no signoff write was recorded"
        assert signoff["file_verified"] is False, "no signoff file was written"
        assert nodes["action"]["status"] == "observed"
        assert _workbench(record)["processing_state"] == "completed"


# ---------------------------------------------------------------------------
# 8. new data whose capture failed is still new data
# ---------------------------------------------------------------------------


def test_creation_fact_without_a_decision_link_is_still_v2(tmp_path):
    root = _root(tmp_path)
    meta = _meta(initiator_role="pm")
    store = _store(root)
    lifecycle.record_start(store, meta)
    # No decision_id was ever recorded: a failed feedback write is the only
    # later fact. It must not turn the record into a legacy row.
    error_scope = _scope(root, decision_id=None, sink=store.error_sink)
    wire.append_event(
        error_scope,
        wire.lifecycle_error_event(
            error_scope,
            logical_id=meta.logical_id,
            stage="settled",
            error_class="append",
            attempted_event_id=None,
            detail="settled write failed: append",
        ),
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    records = _by_key(snapshot, "mw-alpha")
    assert len(records) == 1
    record = records[0]
    workbench = _workbench(record)
    nodes = _node_map(record)

    assert workbench["record_version"] == 2
    assert workbench["processing_state"] == "failed"
    assert workbench["key"] == "mw-alpha"
    assert workbench["task_key"] == "dc-t1"
    assert nodes["key"]["status"] == "observed"
    assert nodes["role"]["status"] == "observed"
    assert nodes["dp"]["status"] == "missing"
    assert nodes["request"]["status"] == "missing"
    assert nodes["action"]["status"] == "failed"
    assert "feedback" in " ".join(nodes["action"]["detail"]["basis"]).lower()


# ---------------------------------------------------------------------------
# 9. retry: new logical id, previous bytes untouched
# ---------------------------------------------------------------------------


def test_retry_gets_its_own_record_and_keeps_the_previous_bytes(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    first = _meta()
    lifecycle.record_start(store, first)
    first_decision = "dp1-dispatch-type:first"
    _add_call(root, decision_id=first_decision, dp="dp1-dispatch-type")
    lifecycle.record_consumed(
        store, first, decision_id=first_decision, dp="dp1-dispatch-type", answer="coding"
    )
    lifecycle.record_settled(
        store, first, decision_id=first_decision, dp="dp1-dispatch-type", outcome="rework"
    )
    wire_path = wire.production_wire_sink(root)
    lifecycle_path = wire.production_lifecycle_sink(root)
    wire_bytes = wire_path.read_bytes()
    lifecycle_bytes = lifecycle_path.read_bytes()

    retry = _meta(retry_of=first.logical_id)
    lifecycle.record_start(store, retry)
    retry_decision = "dp1-dispatch-type:retry"
    _add_call(root, decision_id=retry_decision, dp="dp1-dispatch-type")
    lifecycle.record_consumed(
        store, retry, decision_id=retry_decision, dp="dp1-dispatch-type", answer="coding"
    )
    lifecycle.record_settled(
        store, retry, decision_id=retry_decision, dp="dp1-dispatch-type", outcome="ok"
    )

    assert wire_path.read_bytes().startswith(wire_bytes), "previous wire rows untouched"
    assert lifecycle_path.read_bytes().startswith(lifecycle_bytes), (
        "previous lifecycle rows untouched"
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    by_decision = _by_decision(snapshot)
    first_record = by_decision[first_decision]
    retry_record = by_decision[retry_decision]

    assert first_record.opaque_id != retry_record.opaque_id
    assert _node_map(retry_record)["key"]["detail"]["retry_of"] == first.logical_id
    assert _node_map(first_record)["key"]["detail"]["retry_of"] is None
    assert _node_map(first_record)["key"]["detail"]["logical_id"] == first.logical_id
    assert _node_map(retry_record)["key"]["detail"]["logical_id"] == retry.logical_id
    assert _workbench(first_record)["processing_state"] == "failed"
    assert _workbench(retry_record)["processing_state"] == "completed"


# ---------------------------------------------------------------------------
# 10. an ambiguous association is reported, never attributed
# ---------------------------------------------------------------------------


def test_ambiguous_decision_link_is_not_attributed(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    shared = "dp3-worker-clarify:shared"
    first = _meta(key="mw-alpha", task_key=None)
    second = _meta(key="mw-alpha", task_key=None)
    lifecycle.record_start(store, first)
    lifecycle.record_start(store, second)
    _add_call(root, decision_id=shared, dp="dp3-worker-clarify")
    lifecycle.record_consumed(
        store, first, decision_id=shared, dp="dp3-worker-clarify", answer="from-first"
    )
    lifecycle.record_consumed(
        store, second, decision_id=shared, dp="dp3-worker-clarify", answer="from-second"
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)[shared]
    workbench = _workbench(record)

    assert workbench["record_version"] is None, (
        "two logical ids claim one decision: no version is claimed for the row"
    )
    assert workbench["processing_state"] == "failed"
    assert workbench["nodes"] == []
    assert "workbench-association-ambiguous" in record.flags
    assert any("ambiguous" in warning for warning in snapshot.warnings)
    assert "from-first" not in repr(record.as_dict(detail=True))
    assert "from-second" not in repr(record.as_dict(detail=True))


# ---------------------------------------------------------------------------
# 11. no redactor: node free text is withheld, structure survives
# ---------------------------------------------------------------------------


def test_without_a_redactor_node_free_text_is_withheld(tmp_path):
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    lifecycle.record_start(store, meta)
    decision_id = "dp3-worker-clarify:no-redactor"
    _add_call(root, decision_id=decision_id, dp="dp3-worker-clarify")
    lifecycle.record_consumed(
        store, meta, decision_id=decision_id, dp="dp3-worker-clarify", answer="pm-handoff"
    )
    lifecycle.record_executed(
        store,
        meta,
        decision_id=decision_id,
        dp="dp3-worker-clarify",
        action="pm-handoff",
        result="handed back to the PM",
    )

    snapshot = history.load_history(root)
    record = _by_decision(snapshot)[decision_id]
    nodes = _node_map(record)

    assert record.redaction.enabled is False
    assert nodes["receipt"]["detail"]["consumed"]["answer"] is None, (
        "unprovable free text is omitted, never echoed"
    )
    assert nodes["action"]["detail"]["executed"][0]["result"] is None
    assert record.redaction.omitted_fields >= 1
    # Structural facts and the writer-stored capture are not free text.
    assert nodes["receipt"]["detail"]["consumed"]["ts"] is not None
    assert nodes["request"]["status"] == "observed"


# ---------------------------------------------------------------------------
# 12. missing captures are missing, never reconstructed
# ---------------------------------------------------------------------------


def test_missing_request_or_response_is_not_fabricated(tmp_path):
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    lifecycle.record_start(store, meta)
    decision_id = "dp1-dispatch-type:no-body"
    # A write scope without a redactor stores no request text (not_recorded).
    no_body = _scope(root, decision_id=decision_id, dp="dp1-dispatch-type", redact=None)
    call = wire.new_call()
    wire.record_attempt_start(
        no_body, call, request=b'{"material":"not provable"}', url_path="/v1/decisions"
    )
    lifecycle.record_consumed(
        store, meta, decision_id=decision_id, dp="dp1-dispatch-type", answer="coding"
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    nodes = _node_map(_by_decision(snapshot)[decision_id])

    attempt = nodes["request"]["detail"]["attempts"][0]
    assert attempt["request"]["text"] is None, "no body is invented"
    assert attempt["request"]["wire_len"] == len(b'{"material":"not provable"}')
    assert nodes["request"]["status"] == "failed", "the capture really failed"
    assert nodes["response"]["status"] == "missing"
    assert nodes["response"]["detail"]["attempts"] == []


# ---------------------------------------------------------------------------
# 13. the signoff path is not read (T05 owns file verification)
# ---------------------------------------------------------------------------


def test_out_of_root_failure_sidecar_is_refused_before_read(tmp_path):
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    lifecycle.record_start(store, meta)
    outside = tmp_path / "outside-errors.jsonl"
    row = (
        '{"schema_version":1,"event_id":"e1","ts":"2026-10-22T10:00:00+00:00",'
        '"kind":"lifecycle-error","scope":"production","project_id":"'
        + wire.project_id_for(root)
        + '","key":"mw-alpha","task_key":null,"decision_id":null,"call_id":null,'
        '"submission_id":null,"origin":"x","actor":null,"answer_source":null,'
        '"capture_status":null,"logical_id":"outside1","stage":"settled",'
        '"error_class":"append","attempted_event_id":null,"detail":"outside row"}\n'
    )
    outside.write_text(row, encoding="utf-8", newline="\n")
    link = store.error_sink
    try:
        link.parent.mkdir(parents=True, exist_ok=True)
        link.symlink_to(outside)
    except (OSError, NotImplementedError) as exc:  # pragma: no cover - platform
        pytest.skip(f"symlink unavailable: {type(exc).__name__}")

    snapshot = history.load_history(root, redact=REDACTOR)

    assert snapshot.stats.blocked_reads >= 1
    assert any("refused before read" in warning for warning in snapshot.warnings)
    assert "outside row" not in repr(
        [record.as_dict(detail=True) for record in snapshot.records]
    )
    assert snapshot.stats.lifecycle_error_events == 0


def test_a_recorded_path_elsewhere_never_completes_the_record(
    tmp_path, monkeypatch: pytest.MonkeyPatch
):
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    lifecycle.record_start(store, meta, decision_id=f"dp25-signoff-conclusion:{meta.logical_id}")
    decision_id = f"dp25-signoff-conclusion:{meta.logical_id}"
    _add_call(root, decision_id=decision_id, dp="dp25-signoff-conclusion")
    lifecycle.record_signoff(
        store,
        meta,
        decision_id=decision_id,
        dp="dp25-signoff-conclusion",
        evidence_path="workers/t/evidence/sign-final.md",
        evidence_sha256="b" * 64,
    )
    reads: list[str] = []
    original_text = pathlib.Path.read_text
    original_bytes = pathlib.Path.read_bytes

    def spy_text(self, *args, **kwargs):
        reads.append(str(self))
        return original_text(self, *args, **kwargs)

    def spy_bytes(self, *args, **kwargs):
        reads.append(str(self))
        return original_bytes(self, *args, **kwargs)

    monkeypatch.setattr(pathlib.Path, "read_text", spy_text)
    monkeypatch.setattr(pathlib.Path, "read_bytes", spy_bytes)

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]
    nodes = _node_map(record)

    assert not [
        path for path in reads if path.replace("\\", "/").endswith(
            "workers/t/evidence/sign-final.md"
        )
    ], "a recorded write path is a fact, never a path the reader follows"
    signoff = nodes["receipt"]["detail"]["signoff"]
    assert signoff["file_verified"] is False
    assert "missing" in signoff["file_reason"]
    assert _workbench(record)["processing_state"] == "failed", (
        "a recorded write with no valid file is not completion"
    )


# ---------------------------------------------------------------------------
# 14. known secrets stay out of the new public surface
# ---------------------------------------------------------------------------


def test_new_record_with_a_failed_capture_is_not_legacy(tmp_path):
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    lifecycle.record_start(store, meta)
    decision_id = "dp1-dispatch-type:capture-failed"
    # No redactor on the write scope: the request body could not be stored.
    _add_call(root, decision_id=decision_id, dp="dp1-dispatch-type", redact=None)
    lifecycle.record_settled(
        store, meta, decision_id=decision_id, dp="dp1-dispatch-type", outcome="inconclusive"
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]
    workbench = _workbench(record)
    nodes = _node_map(record)

    assert workbench["record_version"] == 2, "a failed capture is still new data"
    assert workbench["processing_state"] == "failed"
    assert nodes["request"]["status"] == "failed"
    assert nodes["request"]["detail"]["attempts"][0]["request"]["text"] is None
    assert nodes["action"]["detail"]["settled"]["outcome"] == "inconclusive"


def test_known_secret_is_absent_from_workbench_and_facets(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    # The T02 writer refuses a secret-bearing task_key, so the row is written by
    # the real wire writer (a fixture row) to exercise the *output* boundary.
    scope = _scope(root, decision_id=None, key="mw-alpha", task_key=SECRET)
    wire.append_event(
        scope,
        wire.record_start_event(
            scope,
            logical_id="logicalmanual1",
            record_version=2,
            initiator_role="pm",
            retry_of=None,
        ),
    )
    decision_id = "dp1-dispatch-type:secret-1"
    _add_call(
        root,
        decision_id=decision_id,
        dp="dp1-dispatch-type",
        request=f'{{"material":"{SECRET}"}}'.encode("utf-8"),
        response=f'{{"answer":"{SECRET}"}}'.encode("utf-8"),
    )
    other_scope = _scope(root, decision_id=decision_id, dp="dp1-dispatch-type")
    wire.append_event(
        other_scope,
        wire.lifecycle_event(
            other_scope,
            lifecycle="consumed",
            logical_id="logicalmanual1",
            answer=f"chose {SECRET}",
        ),
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]
    payload = record.as_dict(detail=True)
    page = snapshot.page(limit=200)

    assert SECRET not in repr(payload)
    assert SECRET not in repr([item.as_dict() for item in page.records])
    assert SECRET not in repr(page.facets.as_dict())
    assert SECRET not in _all_payloads(snapshot)
    assert payload["workbench"]["task_key"] is None, "a structural secret is omitted"
    assert record.workbench.task_key == SECRET, "the join value itself is kept internally"
    assert "structural-secret-withheld" in record.flags

    nodes = _node_map(record)
    request_text = nodes["request"]["detail"]["attempts"][0]["request"]["text"]
    assert request_text is None or SECRET not in request_text
    response_text = nodes["response"]["detail"]["attempts"][0]["response"]["text"]
    assert response_text is None or SECRET not in response_text


# ---------------------------------------------------------------------------
# 15. the read stays read-only and the old payload shape is preserved
# ---------------------------------------------------------------------------


def test_workbench_is_additive_and_the_read_writes_nothing(tmp_path):
    root = _root(tmp_path)
    meta = _meta()
    store = _store(root)
    lifecycle.record_start(store, meta)
    decision_id = "dp1-dispatch-type:additive"
    _add_call(root, decision_id=decision_id, dp="dp1-dispatch-type")
    lifecycle.record_consumed(
        store, meta, decision_id=decision_id, dp="dp1-dispatch-type", answer="coding"
    )
    wire_path = wire.production_wire_sink(root)
    lifecycle_path = wire.production_lifecycle_sink(root)
    before = (
        _sha256(wire_path),
        _sha256(lifecycle_path),
        sorted(str(path) for path in root.rglob("*") if path.is_file()),
    )

    snapshot = history.load_history(root, redact=REDACTOR)
    record = _by_decision(snapshot)[decision_id]
    payload = record.as_dict(detail=True)

    for name in ("opaque_id", "status", "stages", "calls", "usage", "capture_status", "archive"):
        assert name in payload, "the pre-existing record shape is preserved"
    assert payload["status"] == record.status
    page = snapshot.page()
    assert page.records and page.facets.keys == ("mw-alpha",)
    after = (
        _sha256(wire_path),
        _sha256(lifecycle_path),
        sorted(str(path) for path in root.rglob("*") if path.is_file()),
    )
    assert before == after, "the history read never writes or creates a path"


# ---------------------------------------------------------------------------
# 16. a test-scope v2 record never enters the production page
# ---------------------------------------------------------------------------


def test_test_scope_workbench_stays_out_of_the_production_page(tmp_path):
    root = _root(tmp_path)
    test_root = tmp_path / "test-runs" / "t1"
    test_root.mkdir(parents=True)
    test_store = lifecycle.LifecycleStore.test(
        test_root, project_id=wire.project_id_for(root), redact=REDACTOR, warn=_quiet
    )
    meta = lifecycle.DecisionMeta.create("mw-test", task_key=None, initiator_role="unknown")
    lifecycle.record_start(test_store, meta)
    test_decision = "dp1-dispatch-type:test-1"
    test_scope = wire.WireScope(
        sink=test_root / "wire.jsonl",
        project_id=wire.project_id_for(root),
        scope_kind="test",
        origin="playground",
        decision_id=test_decision,
        dp="dp1-dispatch-type",
        key="mw-test",
        redact=REDACTOR,
        warn=_quiet,
    )
    wire.append_event(
        test_scope,
        wire.lifecycle_event(
            test_scope,
            lifecycle="consumed",
            logical_id=meta.logical_id,
            answer="coding",
        ),
    )

    snapshot = history.load_history(root, redact=REDACTOR, test_roots=[test_root])
    production = snapshot.page()
    test_page = snapshot.page(scope="test")

    assert production.total == 0
    assert production.facets.as_dict() == {"keys": [], "dps": []}
    assert test_page.total == 1
    test_record = test_page.records[0]
    assert _workbench(test_record)["record_version"] == 2
    assert test_page.facets.as_dict() == {"keys": ["mw-test"], "dps": ["dp1-dispatch-type"]}
