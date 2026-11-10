"""test_dp_consolidation_history.py - T27: the eight-entry read-only history
projection over real producer -> writer -> history records.

Scope and honesty rules of this file:

* Every record is produced by the *production* writers
  (``decision_lifecycle``, ``decision_wire``, ``decide_archive``) inside a
  temporary control root. Nothing here writes the product tree, calls a
  provider, touches a live ledger or re-enables a retired id as an alias.
* Records are read back through the single supported entry point
  ``decision_history.load_history`` exactly like the monitor does; the payload
  is the public one (``as_dict``/``as_dict(detail=True)``), never an internal
  fold attribute.
* The retired fixtures are *synthetic stored history* written with the same
  archive writer that wrote the old rows; they are not presented as this
  project's real history. The point is that a stored retired record is read
  read-only, keeps its bytes and is never mapped onto a successor entry.
* Negative controls are marked as such. A red run against the pre-change
  ``decision_history.py`` is recorded separately in this card's evidence dir.

Mapped contracts: AC-007/VC-007 (gate note vs model basis), AC-013/VC-013
(retired read-only history), AC-014/VC-014 (producer -> writer -> consumer ->
projection links, request/record/DOM secret boundaries), AC-049/VC-049
(successors), AC-050/VC-050 (action/settlement/task links, before not
backfilled), AC-051/VC-051 (null vs [] and the sign-key arrays).
"""

from __future__ import annotations

import hashlib
import json
import pathlib
import sys

import pytest

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_DIR))  # noqa: E402

import decide_archive  # noqa: E402
import decision  # noqa: E402
import decision_history as history  # noqa: E402
import decision_lifecycle as lifecycle  # noqa: E402
import decision_monitor  # noqa: E402
import decision_playground  # noqa: E402
import decision_points as dpts  # noqa: E402
import decision_wire as wire  # noqa: E402
import test_decision_context_readable_ui as ui  # noqa: E402
import test_decision_dashboard_assets as assets_suite  # noqa: E402
import test_decision_monitor as monitor_suite  # noqa: E402
import test_dp_consolidation_materials as materials_suite  # noqa: E402
import test_dp_consolidation_signoff as signoff_suite  # noqa: E402

KEY = "mw-t27"
TASK = "t27-history"
SECRET = "T27-WRITER-KNOWN-SECRET-0123456789"
READ_SECRET = "T27-READER-ONLY-SECRET-9876543210"
BASIS_TEXT = "The submitted material supports this choice; budget and authority are unchanged."
PREPARED_AT = "2026-11-01T09:30:00+00:00"
T0 = "2026-11-01T10:00:00+00:00"
T1 = "2026-11-01T11:00:00+00:00"
T2 = "2026-11-01T12:00:00+00:00"
T3 = "2026-11-01T13:00:00+00:00"
XSS_TEXT = '<img src=x onerror="globalThis.PWNED=1">'

ACTIVE_DPS = (
    "dp-w-type",
    "dp-pm-steer",
    "dp-w-check-task",
    "dp-QG",
    "dp-gate-approve",
    "dp-sign-key",
    "dp-auto",
    "dp-route",
)


# ---------------------------------------------------------------------------
# Hermetic control root + production writers
# ---------------------------------------------------------------------------


def _root(tmp_path: pathlib.Path, name: str = "proj") -> pathlib.Path:
    root = tmp_path / name
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True, exist_ok=True)
    return root


def _warnings() -> list[str]:
    return []


def _store(root: pathlib.Path) -> lifecycle.LifecycleStore:
    return lifecycle.LifecycleStore.production(
        root, redact=wire.SubstringRedactor((SECRET,)), warn=_warnings()
    )


def _reader(*secrets: str) -> wire.SubstringRedactor:
    return wire.SubstringRedactor(secrets or (SECRET,))


def _meta(
    *,
    key: str = KEY,
    task_key: str | None = TASK,
    initiator_role: str = "pm",
    retry_of: str | None = None,
    task_before: dict | None = None,
) -> lifecycle.DecisionMeta:
    return lifecycle.DecisionMeta.create(
        key,
        task_key=task_key,
        initiator_role=initiator_role,
        retry_of=retry_of,
        task_before=task_before,
    )


def _task(
    status: str,
    observed_at: str,
    *,
    completed: list[str] | None = None,
    remaining: list[str] | None = None,
    blockers: list[str] | None = None,
    source: str = "dispatch-result",
) -> dict:
    return {
        "status": status,
        "observed_at": observed_at,
        "source": source,
        "completed": completed,
        "remaining": remaining,
        "blockers": blockers,
    }


def _material(dp_id: str) -> dict:
    base = {
        "dp-w-type": {
            "task_goal": "ship the eight-entry projection",
            "task_requirements": "read-only and honest",
            "task_deliverables": "one projection block",
        },
        "dp-pm-steer": {
            "task_goal": "converge the task",
            "task_requirements": "keep the goal",
            "task_deliverables": "a real next action",
            "pm_decision_background": "budget is tight, the main line is unchanged",
        },
        "dp-w-check-task": {
            "task_goal": "finish the assigned slice",
            "reachability_facts": "the write face is free and the budget is enough",
            "completed": "read the files",
            "remaining": "write the test",
            "blockers": "none",
            "constraints": "existing task budget only",
        },
        "dp-QG": {
            "review_requirements": "all listed acceptance checks pass",
            "review_evidence": ["cmd: python -m pytest"],
            "review_findings": "no unresolved blocking finding",
            "uncovered_scope": "live deployment is out of scope",
        },
        "dp-gate-approve": {
            "gate_background": "stage close needs one decision",
            "current_state": "required keys are signed, integration check is green",
            "condition_evidence": ["evidence/close.md:1"],
            "pm_note": {
                "subject": "close stage S1",
                "planned_action": "record the stage close only",
                "basis": {
                    "goal": "spec 1.1",
                    "evidence": "evidence/close.md:1",
                    "budget": "unchanged hard budget",
                    "authority": "existing key authorization",
                },
            },
        },
        "dp-sign-key": {
            "delivery_goal": "deliver the eight-entry protocol",
            "actual_completion": "registry and snapshot are in place",
            "verification_evidence": {"verified": [], "unverified": ["live deployment unverified"]},
            "unfinished_impact": [],
        },
        "dp-auto": {
            "question": "the worker hit a write-face conflict",
            "background": {
                "task_goal": "keep the task moving",
                "current_state": "the conflicting file is claimed by another key",
                "tried": "asked the other window, no answer yet",
                "unknowns": "whether the other claim is still live",
                "constraints": "no new write permission is available",
            },
            "handling_options": [
                {
                    "id": "rollback-now",
                    "label": "roll the conflicting write back",
                    "description": "return the file to the recorded version",
                    "consequence": "the other window keeps its claim",
                    "risk": "loses this round's partial edit",
                    "conditions": "only inside the already granted write face",
                },
                {
                    "id": "ask-the-owner",
                    "label": "ask the claim owner",
                    "description": "request a real handover of the claim",
                    "consequence": "the task waits for a real answer",
                    "risk": "no progress until the owner answers",
                    "conditions": "the owner is a real bound actor",
                },
            ],
        },
        "dp-route": {
            "decision_actor": "PM",
            "decision_object": "the next step of this task",
            "question": "which entry owns this temporary question",
        },
    }
    return json.loads(json.dumps(base[dp_id]))


def _preparation(
    dp_id: str,
    material: dict,
    applies_to: object = "all",
    *,
    text: str = BASIS_TEXT,
    prepared_at: str = PREPARED_AT,
    basis_id: str = "b-primary",
) -> dict:
    legal = list(dpts.resolve_entry_choices(dp_id, material))
    targets = legal if applies_to == "all" else list(applies_to)
    return {
        "basis_catalog": [
            {
                "id": basis_id,
                "text": text,
                "material_refs": [next(iter(material))],
                "applies_to": targets,
            }
        ],
        "prepared_at": prepared_at,
    }


def _result(
    dp_id: str,
    choice: str | None,
    *,
    basis_id: str = "b-primary",
    basis_text: str = BASIS_TEXT,
    prepared_at: str = PREPARED_AT,
    available: bool = True,
    business: int = 1,
    reason: str | None = None,
    attempts: int = 1,
    transport_attempts: int = 1,
    replayed: bool = False,
) -> dict:
    return {
        "dp": dp_id,
        "available": available,
        "replayed": replayed,
        "choice": choice if business == 1 else None,
        "basis_id": basis_id if business == 1 else None,
        "basis_text": basis_text if business == 1 else None,
        "basis_source": "pm-prepared" if business == 1 else None,
        "prepared_at": prepared_at,
        "reason": reason,
        "attempts": attempts,
        "transport_attempts": transport_attempts,
        "business_decisions": business,
    }


def _scope(root: pathlib.Path, decision_id: str | None, dp: str | None) -> wire.WireScope:
    return wire.production_scope(
        root,
        origin="producer",
        decision_id=decision_id,
        dp=dp,
        key=KEY,
        task_key=TASK,
        actor_kind="system",
        actor_id="t27-producer",
        redact=wire.SubstringRedactor((SECRET,)),
        warn=_warnings(),
    )


def _http_call(root: pathlib.Path, decision_id: str, dp: str) -> None:
    """One real attempt-start/end pair plus the call-end row (wire writers)."""
    scope = _scope(root, decision_id, dp)
    call = wire.new_call()
    wire.record_attempt_start(
        scope,
        call,
        request=b'{"model":"jev-latest","dp":"' + dp.encode("utf-8") + b'"}',
        url_path="/v1/decisions",
        model="jev-latest",
    )
    wire.record_attempt_end(
        scope,
        call,
        response=b'{"model":"jev-latest","answers":{}}',
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
            wire_attempts=1,
            latency_ms=11,
            available=True,
            answers_present=True,
            confidence=0.83,
            confidence_source="api",
            transport="timi-decisions",
            model="jev-latest",
        ),
    )


def _book(root: pathlib.Path, decision_id: str, dp: str, state: dict) -> None:
    """The stored input snapshot a real producer writes (business state only)."""
    document = {
        "kind": "input-state",
        "decision_id": decision_id,
        "dp": dp,
        "questions_version": dpts.get_decision_point(dp).questions_version,
        "state_digest": "0123456789abcdef",
        "candidates": {},
        "state": state,
    }
    body = json.dumps(document, ensure_ascii=False, sort_keys=True).encode("utf-8")
    scope = _scope(root, decision_id, dp)
    wire.append_event(
        scope,
        wire.book_snapshot_event(
            scope, book=body, book_ref="state-1", book_version="input-memory"
        ),
    )


def _start(store, meta, decision_id: str) -> None:
    result = lifecycle.record_start(store, meta, decision_id=decision_id)
    assert result.recorded, result


def _request(store, meta, decision_id: str, material: dict, result: dict, **kwargs) -> None:
    written = lifecycle.record_request(
        store,
        meta,
        decision_id=decision_id,
        result=result,
        material=material,
        preparation=_preparation(
            str(result["dp"]),
            material,
            [result["choice"]] if result["business_decisions"] == 1 else "all",
            text=result["basis_text"] or BASIS_TEXT,
            prepared_at=str(result["prepared_at"]),
        ),
        **kwargs,
    )
    assert written.recorded, written


def _record(root: pathlib.Path, decision_id: str, *, redact=None):
    snapshot = history.load_history(root, redact=redact if redact is not None else _reader())
    for record in snapshot.records:
        if record.scope == "production" and record.decision_id == decision_id:
            return snapshot, record
    raise AssertionError(f"record not found: {decision_id}")


def _entry(record, *, detail: bool = True) -> dict:
    return record.as_dict(detail=detail)["entry"]


def _node(record, node_id: str) -> dict:
    payload = record.as_dict(detail=True)
    for node in payload["workbench"]["nodes"]:
        if node["id"] == node_id:
            return node
    raise AssertionError(f"missing node {node_id}")


def _all_keys(value: object) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, item in value.items():
            keys.add(str(key))
            keys |= _all_keys(item)
    elif isinstance(value, list):
        for item in value:
            keys |= _all_keys(item)
    return keys


def _tree_hashes(root: pathlib.Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)).replace("\\", "/"): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


# ---------------------------------------------------------------------------
# AC-007 / VC-007: the four gate choices, PM note and model basis apart
# ---------------------------------------------------------------------------


def test_four_gate_choices_keep_pm_note_and_selected_basis_separate(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    material = _material("dp-gate-approve")
    choices = ("approve", "steer", "need_fix", "reject")
    decision_ids = {}
    for index, choice in enumerate(choices):
        task_before = _task("running", T0, completed=[], remaining=["close"], blockers=None)
        meta = _meta(task_before=task_before)
        decision_id = f"dp-gate-approve:gate-{index}"
        decision_ids[choice] = decision_id
        note_text = (
            f"事项：close stage S1；批准后动作：{choice}；"
            f"目标/证据/预算/授权依据：existing key authorization"
        )
        _start(store, meta, decision_id)
        assert lifecycle.record_note(
            store, meta, decision_id=decision_id, pm_note=note_text, prepared_at=PREPARED_AT
        ).recorded
        _request(
            store,
            meta,
            decision_id,
            material,
            _result("dp-gate-approve", choice),
        )
        _http_call(root, decision_id, "dp-gate-approve")
        _, record = _record(root, decision_id)
        detail = record.as_dict(detail=True)
        entry = detail["entry"]
        # a definition from the current registry, clearly labelled as such
        assert entry["registry_status"] == "active"
        assert entry["readonly"] is True and entry["rerun_available"] is True
        assert entry["kind"] == "fixed" and entry["role_scope"] == "pm"
        assert entry["selection_effect"] == "business-choice"
        assert entry["retired"] is None
        # two sources, neither overwriting the other
        assert entry["has_pm_note"] is True and entry["note_count"] == 1
        assert entry["note"]["pm_note"] == note_text
        assert entry["note"]["note_source"] == "pm-prepared"
        assert entry["note"]["prepared_at"] == PREPARED_AT
        assert entry["has_selected_basis"] is True
        assert entry["basis"]["choice"] == choice
        assert entry["basis"]["basis_id"] == "b-primary"
        assert entry["basis"]["basis_text"] == BASIS_TEXT
        assert entry["basis"]["basis_source"] == "pm-prepared"
        assert entry["selected_choice"] == choice
        assert entry["request"]["reason"] is None
        assert entry["note"]["pm_note"] != entry["basis"]["basis_text"]
        assert entry["basis"]["basis_text"] not in entry["note"]["pm_note"]
        assert note_text not in json.dumps(entry["basis"])
        # a selection is not a release, a repair or a task completion
        action = _node(record, "action")
        assert action["detail"]["executed"] == []
        assert action["detail"]["settled"] is None
        assert action["detail"]["terminal"] is None
        assert entry["task_terminal"] is None
        assert detail["workbench"]["processing_state"] == "processing"
        # the sources name the two carriers separately
        joined = " ".join(entry["sources"])
        assert "ledger.note.pm_note" in joined
        assert "ledger.request.basis_id/basis_text" in joined
    assert len(set(decision_ids.values())) == 4, "the four gate choices are distinct records"


def test_a_refused_request_reason_is_never_promoted_to_the_selected_basis(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    material = _material("dp-gate-approve")
    meta = _meta()
    decision_id = "dp-gate-approve:gate-refused"
    _start(store, meta, decision_id)
    assert lifecycle.record_note(
        store, meta, decision_id=decision_id, pm_note="事项：close；批准后动作：none", prepared_at=PREPARED_AT
    ).recorded
    _request(
        store,
        meta,
        decision_id,
        material,
        _result(
            "dp-gate-approve",
            None,
            available=False,
            business=0,
            reason="entry-unavailable",
        ),
    )
    _, record = _record(root, decision_id)
    entry = _entry(record)
    assert entry["requested"] is True
    assert entry["request"]["available"] is False
    assert entry["request"]["business_decisions"] == 0
    assert entry["request"]["reason"] == "entry-unavailable"
    assert entry["request_refusal"] == "entry-unavailable"
    assert entry["has_selected_basis"] is False
    assert entry["basis"] is None and entry["selected_basis_id"] is None
    # the note and the failure reason are still separate, recorded facts
    assert entry["has_pm_note"] is True
    assert "entry-unavailable" not in json.dumps(entry["note"])
    assert "promoted to the selected basis" in " ".join(entry["sources"])


# ---------------------------------------------------------------------------
# AC-013 / VC-013: retired stored history stays read-only and byte-identical
# ---------------------------------------------------------------------------


def _append_retired_record(root: pathlib.Path, dp: str, trigger: str) -> str:
    decide_archive.append_decide(
        root / ".agenticdoc" / "_autopilot" / "decisions.jsonl",
        dp=dp,
        key=KEY,
        task_key=TASK,
        trigger_id=trigger,
        state={"legacy": True},
        questions_version="q-1234abcd",
        available=True,
        authority="advisory",
        answer={"legacy_question": {"value": "fix", "confidence": 0.7}},
        reason=None,
        escalated_reason=None,
        acted=False,
        actual_action=None,
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        attempts=1,
        latency_ms=12,
        confidence=0.7,
        confidence_source="api",
        now="2026-10-22T10:00:00+00:00",
    )
    return f"{dp}:{trigger}"


def test_every_retired_id_projects_as_retired_and_never_as_a_callable_alias(tmp_path):
    root = _root(tmp_path)
    retired = list(dpts.RETIRED_DP_REGISTRY)
    decision_ids = {}
    for index, record in enumerate(retired):
        decision_ids[record.id] = _append_retired_record(root, record.id, f"legacy-{index}")
    snapshot = history.load_history(root, redact=_reader())
    assert snapshot.stats.production_records == len(retired) == 25
    seen = set()
    for record in snapshot.records:
        if record.decision_id is None:
            continue
        dp_id = record.dp
        seen.add(dp_id)
        payload = record.as_dict(detail=True)
        entry = payload["entry"]
        explanation = dpts.retired_dp(dp_id)
        assert explanation is not None, dp_id
        assert entry["registry_status"] == "retired"
        assert entry["readonly"] is True
        assert entry["rerun_available"] is False
        assert entry["selection_effect"] is None
        assert entry["kind"] is None and entry["role_scope"] is None
        assert entry["retired"]["disposition"] == explanation.disposition
        assert entry["retired"]["migrated_to"] == explanation.migrated_to
        assert entry["retired"]["note"] == explanation.note
        # the old id is kept as recorded: no successor question/contract is applied
        assert payload["dp"] == dp_id
        assert payload["workbench"]["question_summary"] is None
        # the old id remains refused as a run entry (read-only history only)
        with pytest.raises(ValueError):
            dpts.require_active_dp(dp_id)
    assert seen == {record.id for record in retired}


def test_list_and_detail_of_a_retired_record_keep_every_byte_and_differ_in_bodies(tmp_path):
    root = _root(tmp_path)
    retired_dp = "dp1-dispatch-type"
    retired_decision = _append_retired_record(root, retired_dp, "keep-bytes")
    active_material = _material("dp-w-type")
    active_meta = _meta()
    active_decision = "dp-w-type:active-beside-retired"
    store = _store(root)
    _start(store, active_meta, active_decision)
    _request(store, active_meta, active_decision, active_material, _result("dp-w-type", "coding"))
    before = _tree_hashes(root)

    snapshot = history.load_history(root, redact=_reader())
    page = snapshot.page(limit=50)
    retired_public = next(
        record.as_dict() for record in page.records if record.decision_id == retired_decision
    )
    retired_opaque = next(
        record.opaque_id for record in page.records if record.decision_id == retired_decision
    )
    detail = snapshot.detail(retired_opaque)
    assert detail is not None
    detail_public = detail.as_dict(detail=True)
    filtered = snapshot.page(dp=retired_dp)
    assert filtered.total == 1

    # the same bytes after every read path
    assert _tree_hashes(root) == before, "history reads must not rewrite a carrier"

    list_entry = retired_public["entry"]
    detail_entry = detail_public["entry"]
    assert list_entry["registry_status"] == "retired" and list_entry["readonly"] is True
    assert list_entry["rerun_available"] is False
    assert detail_entry["registry_status"] == "retired"
    # list pages carry the compact block, detail reads add the stored bodies
    for compact_only in ("note", "basis", "request", "task"):
        assert compact_only not in list_entry, compact_only
        assert compact_only in detail_entry, compact_only
    assert list_entry["note_count"] == 0 and list_entry["has_pm_note"] is False
    assert list_entry["has_selected_basis"] is False
    assert detail_entry["note"] is None and detail_entry["basis"] is None
    # the active record beside it is not affected and keeps its own status
    active_public = next(
        record.as_dict() for record in page.records if record.decision_id == active_decision
    )
    assert active_public["entry"]["registry_status"] == "active"
    # nothing is fabricated out of the current registry for the retired row
    assert retired_public["workbench"]["nodes"] == []
    assert retired_public["dp"] == retired_dp


# ---------------------------------------------------------------------------
# AC-014 / VC-014: producer -> writer -> consumer -> projection, three secret
# boundaries (request / record / DOM), and no business executor for route
# ---------------------------------------------------------------------------


def test_route_selection_names_an_entry_and_projects_no_business_executor(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    material = _material("dp-route")
    task_before = _task("running", T0, completed=[], remaining=["route"], blockers=None)
    meta = _meta(task_before=task_before)
    decision_id = "dp-route:route-1"
    _start(store, meta, decision_id)
    _request(store, meta, decision_id, material, _result("dp-route", "dp-QG"))
    assert lifecycle.record_consumed(
        store, meta, decision_id=decision_id, answer="dp-QG", reason="PM received the entry selection"
    ).recorded
    assert lifecycle.record_settled(
        store, meta, decision_id=decision_id, outcome="ok", reason="routing round finished"
    ).recorded
    _, record = _record(root, decision_id)
    entry = _entry(record)
    assert entry["kind"] == "route-targets"
    assert entry["selection_effect"] == "entry-target"
    assert entry["selected_choice"] == "dp-QG"
    assert "selects a target entry" in " ".join(entry["sources"])
    # settled names this round only; no task terminal and no business execution
    assert entry["task_terminal"] is None
    action = _node(record, "action")
    assert action["detail"]["executed"] == []
    assert action["detail"]["terminal"] is None
    assert entry["successors"] == []
    # the projection never invents an executor/business wrapper for an observation
    keys = _all_keys(record.as_dict(detail=True))
    assert "executor" not in keys
    assert "fake_executor" not in keys
    assert "business_action" not in keys


def test_secret_is_filtered_at_the_write_read_and_dom_boundaries(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    material = _material("dp-w-type")
    material["task_goal"] = f"ship {XSS_TEXT}"
    note_text = f"PM note carries {SECRET} and {READ_SECRET}"
    prepared_text = f"prepared basis mentions {SECRET} and {READ_SECRET}"
    meta = _meta()
    decision_id = "dp-w-type:secret-1"
    _start(store, meta, decision_id)
    assert lifecycle.record_note(
        store, meta, decision_id=decision_id, pm_note=note_text, prepared_at=PREPARED_AT
    ).recorded
    _request(
        store,
        meta,
        decision_id,
        material,
        _result("dp-w-type", "coding", basis_text=prepared_text),
    )
    _http_call(root, decision_id, "dp-w-type")
    _book(root, decision_id, "dp-w-type", material)

    # 1) request/write boundary: the writer's known set already removed its secret
    ledger = wire.production_lifecycle_sink(root).read_text(encoding="utf-8")
    assert SECRET not in ledger
    assert "<redacted>" in ledger
    assert READ_SECRET in ledger, "the writer only knows its own injected set"

    # a structural value the writer's known set recognises is refused, not written
    secret_meta = lifecycle.DecisionMeta.create(
        SECRET.replace("/", "-"), task_key=TASK, initiator_role="pm"
    )
    with pytest.raises(lifecycle.LifecycleInputError):
        store_key = _store(root)
        lifecycle.record_start(store_key, secret_meta, decision_id="dp-w-type:leak")

    # 2) record/read boundary: the reader's own (wider) known set scrubs the rest
    snapshot, record = _record(
        root, decision_id, redact=wire.SubstringRedactor((SECRET, READ_SECRET))
    )
    payload = record.as_dict(detail=True)
    serialized = json.dumps(payload, ensure_ascii=False)
    assert SECRET not in serialized and READ_SECRET not in serialized
    entry = payload["entry"]
    assert entry["has_pm_note"] is True and entry["has_selected_basis"] is True
    assert entry["note"]["pm_note"] is not None
    assert READ_SECRET not in entry["note"]["pm_note"]
    assert "<redacted>" in entry["note"]["pm_note"]
    assert READ_SECRET not in json.dumps(entry["basis"])
    # without an injected redactor the same text is withheld (fail-closed), never raw
    no_redactor = history.load_history(root)
    withheld = next(r for r in no_redactor.records if r.decision_id == decision_id)
    withheld_payload = withheld.as_dict(detail=True)
    assert withheld_payload["redaction"]["enabled"] is False
    assert withheld_payload["entry"]["note"]["pm_note"] is None
    assert READ_SECRET not in json.dumps(withheld_payload)
    assert SECRET not in json.dumps(withheld_payload)

    # 3) DOM boundary: the shipped dashboard receives already-scrubbed payloads
    public = record.as_dict(detail=True)
    scenario = {
        "hash": "#boot=t27",
        "bootstrap": {"status": 200, "body": ui._envelope({"page_token": "t27-token"})},
        "history": {
            "status": 200,
            "body": ui._envelope({"records": [record.as_dict()], "total": 1, "offset": 0, "limit": 5}),
        },
        "detailByOpaque": {record.opaque_id: {"status": 200, "body": ui._envelope(public)}},
        "steps": [{"type": "click", "target": '[data-testid="record-dag-open"]'}]
        + [
            {
                "type": "click",
                "target": f'[data-testid="dag-node"][data-node-id="{node}"]',
                "snapshot": node,
            }
            for node in ("input", "action")
        ],
    }
    result = ui._run_dom(tmp_path, scenario)
    assert result["storageWrites"] == []
    assert all(
        call["url"] == "/api/bootstrap" or call["method"] == "GET" for call in result["fetchCalls"]
    )
    for snapshot in result["snapshots"]:
        assert snapshot["pwned"] is False, snapshot["label"]
        assert snapshot["consoleMessages"] == []
        assert snapshot["imgCount"] == 0
        assert SECRET not in snapshot["bodyText"] and READ_SECRET not in snapshot["bodyText"]
    input_detail = ui._snapshot(result, "input")["nodeDetail"] or ""
    assert XSS_TEXT in input_detail, "the payload text is rendered as text, not markup"
    assert SECRET not in input_detail


# ---------------------------------------------------------------------------
# AC-049 / VC-049: the recorded successors, one fact per real stage
# ---------------------------------------------------------------------------


def test_successors_show_request_refusal_choice_actual_repair_and_the_unrequested(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    gate_material = _material("dp-gate-approve")
    parent_meta = _meta()
    parent_id = "dp-gate-approve:gate-parent"
    _start(store, parent_meta, parent_id)
    assert lifecycle.record_note(
        store, parent_meta, decision_id=parent_id, pm_note="事项：steer；批准后动作：successor",
        prepared_at=PREPARED_AT,
    ).recorded
    _request(store, parent_meta, parent_id, gate_material, _result("dp-gate-approve", "steer"))

    # a successor whose own request was refused (transport/business refusal)
    steer_material = _material("dp-pm-steer")
    steer_meta = _meta()
    steer_id = "dp-pm-steer:steer-1"
    _start(store, steer_meta, steer_id)
    assert lifecycle.record_note(
        store, steer_meta, decision_id=steer_id, pm_note="successor: narrow the remaining slice",
        prepared_at=PREPARED_AT, parent_ref=parent_id,
    ).recorded
    _request(
        store,
        steer_meta,
        steer_id,
        steer_material,
        _result("dp-pm-steer", None, available=False, business=0, reason="input-incomplete"),
        parent_ref=parent_id,
    )

    # a successor that really answered and really repaired (executed + settled)
    auto_material = _material("dp-auto")
    auto_meta = _meta()
    fix_id = "dp-auto:fix-1"
    _start(store, auto_meta, fix_id)
    _request(
        store,
        auto_meta,
        fix_id,
        auto_material,
        _result("dp-auto", "rollback-now"),
        parent_ref=parent_id,
    )
    assert lifecycle.record_executed(
        store, auto_meta, decision_id=fix_id, action="narrow", result="rolled the write back",
        reason="the prepared repair was executed", task_after=_task("running", T1),
    ).recorded
    assert lifecycle.record_settled(
        store, auto_meta, decision_id=fix_id, outcome="ok", reason="repair round finished",
        task_after=_task("running", T2),
    ).recorded

    # a successor that was only declared: a note link, no request at all
    declared_meta = _meta()
    declared_id = "dp-pm-steer:declared-1"
    _start(store, declared_meta, declared_id)
    assert lifecycle.record_note(
        store, declared_meta, decision_id=declared_id, pm_note="declared successor, not requested",
        prepared_at=PREPARED_AT, parent_ref=parent_id,
    ).recorded

    _, parent = _record(root, parent_id)
    entry = _entry(parent)
    successors = {item["decision_id"]: item for item in entry["successors"]}
    assert set(successors) == {steer_id, fix_id, declared_id}
    assert len(entry["successors"]) == 3, "each successor appears exactly once (no duplicates)"

    steer = successors[steer_id]
    assert steer["requested"] is True
    assert steer["available"] is False
    assert steer["business_decisions"] == 0
    assert steer["reason"] == "input-incomplete"
    assert steer["choice"] is None
    assert steer["executed_actions"] == []
    assert steer["settled_outcome"] is None

    fix = successors[fix_id]
    assert fix["requested"] is True and fix["available"] is True
    assert fix["business_decisions"] == 1
    assert fix["choice"] == "rollback-now"
    assert fix["executed_actions"] == ["narrow"]
    assert fix["settled_outcome"] == "ok"
    assert fix["terminal"] is None
    assert "ledger.lifecycle.executed of the successor (the actual repair)" in fix["sources"]

    declared = successors[declared_id]
    assert declared["requested"] is False
    assert declared["reason"] is None and declared["choice"] is None
    assert declared["recorded_stages"] == ["note"]
    assert declared["executed_actions"] == [] and declared["settled_outcome"] is None

    assert all(item["same_key"] is True for item in entry["successors"])
    # each successor states its own limits; a link is not a release
    assert any(
        "never releases the parent gate" in " ".join(item["sources"])
        for item in entry["successors"]
    )
    # the parent gate is not released and its own facts are unchanged
    assert entry["selected_choice"] == "steer"
    assert parent.as_dict(detail=True)["workbench"]["processing_state"] != "completed"
    parent_action = _node(parent, "action")
    assert parent_action["detail"]["executed"] == []
    assert parent_action["detail"]["settled"] is None

    # the successor records keep their own parent pointer (no alias, no release)
    _, steer_record = _record(root, steer_id)
    steer_entry = _entry(steer_record)
    assert steer_entry["parent_ref"] == parent_id
    assert steer_entry["successors"] == []


# ---------------------------------------------------------------------------
# AC-050 / VC-050: action + settlement keyed to the same record, task snapshots
# ---------------------------------------------------------------------------


def test_action_and_settlement_link_one_task_and_the_terminal_stays_separate(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    material = _material("dp-w-type")
    task_before = _task("running", T0, completed=["read"], remaining=["write"], blockers=None)
    meta = _meta(task_before=task_before)
    decision_id = "dp-w-type:linked-1"
    _start(store, meta, decision_id)
    _request(store, meta, decision_id, material, _result("dp-w-type", "coding"))
    assert lifecycle.record_consumed(
        store, meta, decision_id=decision_id, answer="coding", reason="PM received the suggestion"
    ).recorded
    assert lifecycle.record_executed(
        store, meta, decision_id=decision_id, action="record",
        result="the chosen type was recorded", reason="the action really happened",
        task_after=_task("running", T1, completed=["read", "write"], remaining=[], blockers=[]),
    ).recorded
    assert lifecycle.record_settled(
        store, meta, decision_id=decision_id, outcome="ok", reason="round finished",
        task_after=_task("running", T2, completed=["read", "write"], remaining=[], blockers=[]),
    ).recorded
    assert lifecycle.record_terminal(
        store, meta, decision_id=decision_id, terminal="completed",
        reason="the task slice is complete", evidence="evidence/t27.md:1",
        task_after=_task("done", T3, completed=["read", "write"], remaining=[], blockers=[]),
    ).recorded

    _, record = _record(root, decision_id)
    entry = _entry(record)
    task = entry["task"]
    assert task["before_visibility"] == "recorded"
    assert task["before"] == task_before
    assert task["before"]["completed"] == ["read"]
    assert task["after_visibility"] == "recorded"
    assert task["after"]["observed_at"] == T2, "the round's after is the settled snapshot"
    assert task["after_stage"] == "settled"
    assert [item["stage"] for item in task["observations"]] == [
        "record-start",
        "executed",
        "settled",
        "terminal",
    ]
    observed = [item["observed_at"] for item in task["observations"]]
    assert observed == [T0, T1, T2, T3]
    assert task["observation_order"] == "non-decreasing"
    assert entry["task_observation_order"] == "non-decreasing"
    assert entry["task_terminal"] == "completed"
    assert task["terminal"]["terminal"] == "completed"
    assert task["terminal"]["reason"] == "the task slice is complete"
    assert task["terminal"]["evidence"] == "evidence/t27.md:1"
    assert task["terminal"]["task_after"]["observed_at"] == T3
    assert task["terminal"]["task_after_visibility"] == "recorded"
    # before is never backfilled from a later snapshot
    assert task["before"]["status"] == "running"
    assert task["before"]["observed_at"] == T0
    assert "never means the task is done" in " ".join(_node(record, "action")["detail"]["basis"])

    # every recorded observation of this logical record carries the same association
    events = lifecycle.read_lifecycle(store).events
    linked = [row for row in events if row.get("task_after") is not None]
    assert linked, "the writer recorded the post observations"
    assert all(row.get("key") == KEY for row in linked)
    assert all(row.get("task_key") == TASK for row in linked)
    assert {row.get("logical_id") for row in linked} == {meta.logical_id}

    # settled alone is not the task done: a separate record has no terminal row
    other_meta = _meta()
    other_id = "dp-w-type:settled-only"
    _start(store, other_meta, other_id)
    _request(store, other_meta, other_id, material, _result("dp-w-type", "coding"))
    assert lifecycle.record_settled(
        store, other_meta, decision_id=other_id, outcome="ok", reason="round finished"
    ).recorded
    _, other = _record(root, other_id)
    other_entry = _entry(other)
    assert other.as_dict(detail=True)["workbench"]["processing_state"] == "completed"
    assert other_entry["task_terminal"] is None
    assert other_entry["task"]["terminal"] is None
    assert _node(other, "action")["detail"]["terminal"] is None


def test_a_failed_round_never_fabricates_a_successful_executed_action(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    material = _material("dp-w-type")
    meta = _meta()
    decision_id = "dp-w-type:failed-round"
    _start(store, meta, decision_id)
    _request(store, meta, decision_id, material, _result("dp-w-type", "coding"))
    assert lifecycle.record_settled(
        store, meta, decision_id=decision_id, outcome="rework", reason="the write face was contested"
    ).recorded
    _, record = _record(root, decision_id)
    entry = _entry(record)
    action = _node(record, "action")
    assert action["status"] == "failed"
    assert action["detail"]["executed"] == []
    assert action["detail"]["settled"]["outcome"] == "rework"
    assert entry["task_terminal"] is None
    assert record.as_dict(detail=True)["workbench"]["processing_state"] == "failed"
    assert "fabricated" not in json.dumps(entry)


# ---------------------------------------------------------------------------
# AC-051 / VC-051: null vs [], sign-key arrays, agent-report adds no authority
# ---------------------------------------------------------------------------


def test_null_and_empty_task_axes_and_sign_arrays_are_not_conflated(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    sign_material = _material("dp-sign-key")
    sign_material["verification_evidence"] = {"verified": [], "unverified": ["live run unverified"]}
    sign_material["unfinished_impact"] = []
    before = _task("running", T0, completed=[], remaining=None, blockers=[])
    meta = _meta(task_before=before)
    decision_id = "dp-sign-key:sign-1"
    _start(store, meta, decision_id)
    _book(root, decision_id, "dp-sign-key", sign_material)
    _request(store, meta, decision_id, sign_material, _result("dp-sign-key", "finalize"))

    _, record = _record(root, decision_id)
    payload = record.as_dict(detail=True)
    task = payload["entry"]["task"]
    assert task["before"]["completed"] == []
    assert task["before"]["remaining"] is None
    assert task["before"]["blockers"] == []
    assert isinstance(task["before"]["completed"], list)
    assert json.dumps(task["before"]).count('"remaining": null') == 1
    # the stored material keeps the real empty arrays and never invents a null
    material = _node(record, "input")["detail"]["material"]
    assert material["verification_evidence"]["verified"] == []
    assert material["verification_evidence"]["unverified"] == ["live run unverified"]
    assert material["unfinished_impact"] == []
    assert "unfinished_impact" in material and material["unfinished_impact"] is not None
    # a material field the producer did not send is absent, not a fabricated null
    absent = _material("dp-w-type")
    absent.pop("task_deliverables")
    absent_meta = _meta(task_key=None)
    absent_id = "dp-w-type:absent-material"
    _start(store, absent_meta, absent_id)
    _book(root, absent_id, "dp-w-type", absent)
    _, absent_record = _record(root, absent_id)
    absent_material = _node(absent_record, "input")["detail"]["material"]
    assert "task_deliverables" not in absent_material
    # the projection source keeps the writer's own array contract (AC-051): a
    # missing/null sign array is still an issue, never upgraded to a real []
    assert [name for name, _rule in dpts.sign_key_material_issues({})] == [
        "verification_evidence.verified",
        "verification_evidence.unverified",
        "unfinished_impact",
    ]
    assert [
        name
        for name, _rule in dpts.sign_key_material_issues(
            {
                "verification_evidence": {"verified": [], "unverified": None},
                "unfinished_impact": [],
            }
        )
    ] == ["verification_evidence.unverified"]


def test_a_damaged_out_of_order_post_snapshot_is_reported_invalid_not_accepted(tmp_path):
    """NEGATIVE CONTROL: the row is hand-appended, bypassing the lifecycle writer.

    The production writer refuses a post observation that precedes an earlier
    one; this fixture deliberately writes that row through the lower wire layer
    to prove the reader reports the damaged row as ``invalid`` instead of
    accepting it (or backfilling it into ``before``). It is not a producer path.
    """
    root = _root(tmp_path)
    store = _store(root)
    material = _material("dp-w-type")
    before = _task("running", T0, completed=[], remaining=["slice"], blockers=None)
    meta = _meta(task_before=before)
    decision_id = "dp-w-type:damaged-order"
    _start(store, meta, decision_id)
    _request(store, meta, decision_id, material, _result("dp-w-type", "coding"))
    scope = _scope(root, decision_id, "dp-w-type")
    wire.append_event(
        scope,
        wire.lifecycle_event(
            scope,
            lifecycle="executed",
            logical_id=meta.logical_id,
            action="record",
            result="damaged out-of-order observation (negative control)",
            reason="negative control: an earlier observed_at than the creation fact",
            task_after=_task(
                "running", "2026-11-01T09:00:00+00:00", completed=[], remaining=[], blockers=[]
            ),
        ),
    )
    _, record = _record(root, decision_id)
    entry = _entry(record)
    task = entry["task"]
    assert task["before"] == before, "before is still the creation fact, never the damaged row"
    assert task["after"] is None and task["after_visibility"] == "invalid"
    executed = [item for item in task["observations"] if item["stage"] == "executed"]
    assert executed and executed[-1]["visibility"] == "invalid"
    assert executed[-1]["observed_at"] is None
    action = _node(record, "action")
    assert action["detail"]["task_after"] is None
    assert action["detail"]["task_after_visibility"] == "invalid"
    assert entry["task_terminal"] is None


def test_agent_report_and_projection_never_grant_an_action_or_authority(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    material = _material("dp-w-type")
    task_before = _task("running", T0, completed=[], remaining=["slice"], blockers=None, source="agent-report")
    meta = _meta(task_before=task_before)
    decision_id = "dp-w-type:agent-report"
    _start(store, meta, decision_id)
    _request(store, meta, decision_id, material, _result("dp-w-type", "coding"))
    _, record = _record(root, decision_id)
    payload = record.as_dict(detail=True)
    entry = payload["entry"]
    assert entry["task"]["before"]["source"] == "agent-report"
    # the snapshot source is a fact; it grants no permission and no execution
    assert entry["readonly"] is True
    assert entry["rerun_available"] is True  # only because the entry is active today
    assert _node(record, "action")["detail"]["executed"] == []
    keys = _all_keys(payload)
    for forbidden in ("grant", "authority_grant", "permission", "write_face", "executed_by_report"):
        assert forbidden not in keys, forbidden


# ---------------------------------------------------------------------------
# All eight entries: each record projects its own definition, one at a time
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("file_state", ["missing", "invalid", "valid", "failed-feedback"])
def test_current_sign_projection_requires_the_actual_typed_file(tmp_path, monkeypatch, file_state):
    root = _root(tmp_path)
    store = _store(root)
    meta = _meta(task_before=_task("running", T0, completed=[], remaining=None, blockers=[]))
    decision_id = f"dp-sign-key:{meta.logical_id}"
    material = _material("dp-sign-key")
    _start(store, meta, decision_id)
    _book(root, decision_id, "dp-sign-key", material)
    _request(store, meta, decision_id, material, _result("dp-sign-key", "finalize"))
    assert lifecycle.record_note(
        store, meta, decision_id=decision_id, pm_note="signing round only", prepared_at=PREPARED_AT
    ).recorded
    key_dir = root / ".agenticdoc" / KEY
    if file_state != "missing":
        signoff_suite._sign(root, key_dir, material, key=KEY, logical_id=meta.logical_id)
        if file_state == "invalid":
            path = key_dir / "evidence/review/sign-final.md"
            path.write_text(path.read_text(encoding="utf-8").replace("conclusion: finalize", "conclusion: continue"), encoding="utf-8")
    if file_state in ("missing", "invalid"):
        assert lifecycle.record_settled(store, meta, decision_id=decision_id, outcome="ok", reason="round only").recorded
    if file_state == "failed-feedback":
        # Exercise the managed error writer, not a forged successful receipt.
        append = wire.append_event
        def refuse_settlement(scope, event, **kwargs):
            if event.get("lifecycle") == "settled":
                raise OSError("isolated feedback write failure")
            return append(scope, event, **kwargs)
        monkeypatch.setattr(wire, "append_event", refuse_settlement)
        failed = lifecycle.record_settled(store, meta, decision_id=decision_id, outcome="ok", reason="feedback write failure")
        monkeypatch.setattr(wire, "append_event", append)
        assert not failed.recorded
    before = _tree_hashes(root)
    _, record = _record(root, decision_id)
    payload = record.as_dict(detail=True)
    receipt = _node(record, "receipt")["detail"]
    valid = file_state in ("valid", "failed-feedback")
    assert payload["workbench"]["processing_state"] == ("completed" if valid else "processing")
    assert receipt["signoff"]["file_verified"] is valid
    assert receipt["signoff"]["recorded"] is None
    assert receipt["signoff"]["evidence_sha256"] is None
    assert payload["entry"]["task_terminal"] is None
    assert payload["entry"]["basis"]["basis_text"] == BASIS_TEXT
    assert payload["entry"]["note"]["pm_note"] == "signing round only"
    assert payload["entry"]["task"]["before"]["completed"] == []
    assert payload["entry"]["task"]["before"]["remaining"] is None
    assert _tree_hashes(root) == before


@pytest.mark.parametrize("choice", ["continue", "user-confirm"])
def test_current_sign_projection_non_signing_round_is_not_task_done(tmp_path, choice):
    root = _root(tmp_path)
    store = _store(root)
    meta = _meta()
    decision_id = f"dp-sign-key:{meta.logical_id}"
    material = _material("dp-sign-key")
    _start(store, meta, decision_id)
    _request(store, meta, decision_id, material, _result("dp-sign-key", choice))
    assert lifecycle.record_executed(store, meta, decision_id=decision_id, action=choice, result="handled round", reason="not a signature").recorded
    assert lifecycle.record_settled(store, meta, decision_id=decision_id, outcome="ok", reason="round only").recorded
    before = _tree_hashes(root)
    _, record = _record(root, decision_id)
    assert record.workbench.processing_state == "completed"
    assert _entry(record)["task_terminal"] is None
    assert _node(record, "receipt")["detail"]["signoff"]["file_verified"] is False
    assert not (root / ".agenticdoc" / KEY / "evidence/review/sign-final.md").exists()
    assert _tree_hashes(root) == before


def test_all_eight_entries_project_their_own_definition(tmp_path):
    root = _root(tmp_path)
    store = _store(root)
    assert tuple(point.id for point in dpts.DP_REGISTRY) == ACTIVE_DPS
    for dp_id in ACTIVE_DPS:
        material = _material(dp_id)
        meta = _meta()
        decision_id = f"{dp_id}:entry"
        choice = dpts.resolve_entry_choices(dp_id, material)[0]
        _start(store, meta, decision_id)
        _request(store, meta, decision_id, material, _result(dp_id, choice))
        _, record = _record(root, decision_id)
        entry = _entry(record)
        point = dpts.get_decision_point(dp_id)
        assert entry["registry_status"] == "active"
        assert entry["rerun_available"] is True and entry["readonly"] is True
        assert entry["kind"] == point.kind
        assert entry["role_scope"] == point.role_scope
        assert entry["selected_choice"] == choice
        assert entry["has_selected_basis"] is True
        expected_effect = "entry-target" if point.kind == "route-targets" else "business-choice"
        assert entry["selection_effect"] == expected_effect
        assert record.workbench.question_summary == point.questions[0]["instructions"]
        assert record.workbench.question_summary is not None

# ---------------------------------------------------------------------------
# T29: the eight generated entry forms and the entry semantics in the shipped
# faux DOM. Real loopback GET bodies feed the shipped decision_dashboard.*; the
# faux `/api/test/*` bodies are labelled contract fixtures and never claim a
# provider call. No real browser, no provider, no product write.
# ---------------------------------------------------------------------------

_ENTRY_SNAPSHOT_MARKER = '    nodeDetail: nodeText("dag-node-detail"),'

_ENTRY_SNAPSHOT_FIELDS = '''
    testIds: (function () {
      const table = Object.create(null);
      findAll(documentRoot, "[data-testid]").forEach(function (node) {
        const name = node.getAttribute("data-testid");
        (table[name] = table[name] || []).push(node.textContent);
      });
      return table;
    })(),
    entryInputs: findAll(documentRoot, '[data-testid="pg-entry-input"]').map(function (node) {
      return {
        field: node.getAttribute("data-field"),
        required: node.getAttribute("data-required"),
        kind: node.getAttribute("data-kind"),
        value: String(node.value === undefined ? "" : node.value),
      };
    }),
    entryChoices: findAll(documentRoot, '[data-testid="pg-entry-choice"]').map(function (node) {
      return {choice: node.getAttribute("data-choice"), question: node.getAttribute("data-question")};
    }),
    entryFormDp: (function () {
      const form = findFirst(documentRoot, '[data-testid="pg-entry-form-body"]');
      return form ? form.getAttribute("data-dp") : null;
    })(),
    entryFacts: findAll(documentRoot, '[data-testid="entry-facts"]').map(function (node) {
      return {status: node.getAttribute("data-registry-status"), rerun: node.getAttribute("data-rerun-available")};
    }),
    rowEntryStates: findAll(documentRoot, '[data-testid="entry-row-state"]').map(function (node) {
      return {status: node.getAttribute("data-registry-status"), rerun: node.getAttribute("data-rerun-available"),
        text: node.textContent};
    }),
    successorRows: findAll(documentRoot, '[data-testid="entry-successor"]').map(function (node) {
      return {decisionId: node.getAttribute("data-decision-id"),
        requested: node.getAttribute("data-requested"), text: node.textContent};
    }),'''


@pytest.fixture
def entry_dom(monkeypatch):
    """Extend the shipped harness snapshot with the T29 entry/form reads.

    Same harness, same parser, same fetch/timer doubles: only extra snapshot
    fields are added, so the DOM behaviour under test stays the shipped one.
    """
    assert _ENTRY_SNAPSHOT_MARKER in ui.DOM_HARNESS_JS
    monkeypatch.setattr(
        ui,
        "DOM_HARNESS_JS",
        ui.DOM_HARNESS_JS.replace(_ENTRY_SNAPSHOT_MARKER, _ENTRY_SNAPSHOT_MARKER + _ENTRY_SNAPSHOT_FIELDS),
    )


@pytest.fixture
def dom_env(tmp_path, monkeypatch):
    """No ambient credential/proxy reaches the page or the loopback monitor."""
    home = tmp_path / "home"
    home.mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("PI_CODING_AGENT_DIR", str(home / "pi-agent"))
    for name in (
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "TIMI_API_KEY",
        "TIMI_BASE_URL",
        "MW_DECIDE_API_KEY",
        "MW_DECISION_API_KEY",
        "PI_API_KEY",
        "HTTP_PROXY",
        "HTTPS_PROXY",
        "http_proxy",
        "https_proxy",
        "PI_WORKER_TASK",
    ):
        monkeypatch.delenv(name, raising=False)
    yield


def _read_monitor(root: pathlib.Path) -> dict:
    """Real loopback GET bodies: listing, every detail and the registry route."""
    deps = decision_monitor.MonitorDeps(redactor=wire.SubstringRedactor((SECRET,)))
    with monitor_suite._running(root, deps=deps) as instance:
        token = monitor_suite._page_token(instance)
        listing = assets_suite._capture(instance, "/api/history?limit=50", token)
        detail = {
            record["opaque_id"]: assets_suite._capture(
                instance, "/api/history/" + record["opaque_id"], token
            )
            for record in listing["data"]["records"]
        }
        dps = assets_suite._capture(instance, "/api/dps", token)
    return {"token": token, "listing": listing, "detail": detail, "dps": dps}


def _dom_scenario(payloads: dict, steps: list[dict], **overrides: object) -> dict:
    scenario = {
        "hash": "#boot=t29",
        "bootstrap": {"status": 200, "body": ui._envelope({"page_token": payloads["token"]})},
        "history": {"status": 200, "body": payloads["listing"]},
        "detailByOpaque": {
            opaque: {"status": 200, "body": body} for opaque, body in payloads["detail"].items()
        },
        "dps": {"status": 200, "body": payloads["dps"]},
        "testHistory": {"status": 200, "body": ui._envelope({"records": [], "total": 0, "limit": 20, "offset": 0})},
        "steps": steps,
    }
    scenario.update(overrides)
    return scenario


def _opaque_for(payloads: dict, dp_id: str) -> str:
    for record in payloads["listing"]["data"]["records"]:
        if record.get("entry", {}).get("dp_id") == dp_id:
            return record["opaque_id"]
    raise AssertionError(f"no listing row for {dp_id}")


def _detail_for(payloads: dict, dp_id: str) -> dict:
    for body in payloads["detail"].values():
        if body["data"].get("entry", {}).get("dp_id") == dp_id:
            return body["data"]
    raise AssertionError(f"no detail row for {dp_id}")


def _only_get_or_bootstrap(result: dict) -> None:
    assert all(
        call["url"] == "/api/bootstrap" or call["method"] == "GET" for call in result["fetchCalls"]
    ), result["fetchCalls"]
    assert result["storageWrites"] == []


def _open_detail_steps(payloads: dict, dp_id: str) -> list[dict]:
    """Click the row's own detail control (DAG row or legacy log-only row)."""
    detail = _detail_for(payloads, dp_id)
    dag = detail["workbench"].get("record_version") == 2
    testid = "record-dag-open" if dag else "record-open"
    opaque = _opaque_for(payloads, dp_id)
    return [{"type": "click", "target": f'[data-testid="{testid}"][data-opaque="{opaque}"]'}]


def test_eight_entry_forms_are_built_from_the_served_registry_description(
    tmp_path, dom_env, entry_dom
):
    root = _root(tmp_path)
    store = _store(root)
    meta = _meta()
    decision_id = "dp-w-type:form-1"
    _start(store, meta, decision_id)
    _request(store, meta, decision_id, _material("dp-w-type"), _result("dp-w-type", "coding"))
    # a route record beside it: its selection names an entry and executes nothing
    route_meta = _meta()
    route_id = "dp-route:route-form"
    _start(store, route_meta, route_id)
    _request(store, route_meta, route_id, _material("dp-route"), _result("dp-route", "dp-QG"))
    before = _tree_hashes(root)

    payloads = _read_monitor(root)
    points = {point["id"]: point for point in payloads["dps"]["data"]["points"]}
    assert tuple(points) == ACTIVE_DPS, "the served registry is exactly the eight entries"
    steps: list[dict] = [{"type": "click", "target": "#tab-playground", "snapshot": "playground"}]
    for dp_id in ACTIVE_DPS:
        steps.append({"type": "setValue", "target": "#dp-select", "value": dp_id})
        steps.append(
            {
                "type": "dispatch",
                "target": "#dp-select",
                "event": {"type": "change"},
                "snapshot": dp_id,
            }
        )
    steps.extend(_open_detail_steps(payloads, "dp-route"))
    steps.append({"type": "click", "target": "#record-dialog-tab-log", "snapshot": "route-log"})
    result = ui._run_dom(tmp_path, _dom_scenario(payloads, steps))

    for dp_id in ACTIVE_DPS:
        snapshot = ui._snapshot(result, dp_id)
        point = points[dp_id]
        assert snapshot["entryFormDp"] == dp_id
        expected = [
            (field["name"], "true") for field in point["required_state_fields"]
        ] + [(field["name"], "false") for field in point["optional_state_fields"]]
        assert [(item["field"], item["required"]) for item in snapshot["entryInputs"]] == expected
        served_choices = [
            str(choice)
            for question in point["questions"]
            for choice in (question.get("choices") or [])
        ]
        assert [item["choice"] for item in snapshot["entryChoices"]] == served_choices

    gate = ui._snapshot(result, "dp-gate-approve")
    assert [item["choice"] for item in gate["entryChoices"]] == ["approve", "steer", "need_fix", "reject"]
    assert [item["choice"] for item in ui._snapshot(result, "dp-route")["entryChoices"]] == list(
        dpts.ROUTE_TARGETS
    )
    assert [item["choice"] for item in ui._snapshot(result, "dp-sign-key")["entryChoices"]] == [
        "finalize",
        "continue",
        "user-confirm",
    ]
    assert [item["choice"] for item in ui._snapshot(result, "dp-w-check-task")["entryChoices"]] == [
        "continue",
        "terminate",
        "investigate",
    ]
    # dp-auto's candidates live only in the material: the form shows no menu.
    auto = ui._snapshot(result, "dp-auto")
    assert auto["entryChoices"] == []
    assert "pg-entry-dynamic" in auto["testIds"]
    assert "handling_options" in auto["testIds"]["pg-entry-dynamic"][0]
    assert "表单由服务端返回的入口描述生成" in (auto["bodyText"] or "")

    # route selects a target entry: no business choice, no execution, no task done
    route_text = ui._snapshot(result, "route-log")["logText"] or ""
    assert "仅指定目标入口" in route_text
    assert "本次选择：dp-QG" in route_text
    assert "已执行行动：未记录" in route_text and "已执行行动（" not in route_text
    assert "任务终态：未记录" in route_text

    _only_get_or_bootstrap(result)
    assert _tree_hashes(root) == before, "the read-only DOM pass writes nothing"


def test_entry_form_follows_the_served_description_with_no_local_business_menu(
    tmp_path, dom_env, entry_dom
):
    root = _root(tmp_path)
    store = _store(root)
    meta = _meta()
    decision_id = "dp-w-type:served-description"
    _start(store, meta, decision_id)
    _request(store, meta, decision_id, _material("dp-w-type"), _result("dp-w-type", "coding"))
    payloads = _read_monitor(root)

    dps = json.loads(json.dumps(payloads["dps"]))
    typed = next(point for point in dps["data"]["points"] if point["id"] == "dp-w-type")
    typed["required_state_fields"] = list(typed["required_state_fields"]) + [
        {"name": "future_field_a", "type": "integer", "description": "served-only field"}
    ]
    typed["questions"] = [
        {"id": "q-served", "type": "choice", "choices": ["coding", "future-choice-z"], "labels": {}}
    ]
    undescribed = next(point for point in dps["data"]["points"] if point["id"] == "dp-QG")
    undescribed["required_state_fields"] = []
    undescribed["optional_state_fields"] = []
    undescribed["questions"] = []

    # CONTROL: the served description is the only source of fields and choices.
    steps = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "setValue", "target": "#dp-select", "value": "dp-w-type"},
        {"type": "dispatch", "target": "#dp-select", "event": {"type": "change"}, "snapshot": "served"},
        {"type": "setValue", "target": "#dp-select", "value": "dp-QG"},
        {"type": "dispatch", "target": "#dp-select", "event": {"type": "change"}, "snapshot": "undescribed"},
    ]
    result = ui._run_dom(tmp_path, _dom_scenario(payloads, steps, dps={"status": 200, "body": dps}))

    served = ui._snapshot(result, "served")
    assert [item["field"] for item in served["entryInputs"]].count("future_field_a") == 1
    assert [item["choice"] for item in served["entryChoices"]] == ["coding", "future-choice-z"]
    assert "research" not in [item["choice"] for item in served["entryChoices"]]

    undescribed_snapshot = ui._snapshot(result, "undescribed")
    assert undescribed_snapshot["entryInputs"] == []
    assert undescribed_snapshot["entryChoices"] == []
    assert "pg-entry-fields-empty" in undescribed_snapshot["testIds"]
    assert "pg-entry-choices-empty" in undescribed_snapshot["testIds"]
    _only_get_or_bootstrap(result)


def test_the_normal_client_record_reaches_the_shipped_dom_through_real_http(
    tmp_path, dom_env, entry_dom
):
    """The real normal producer chain of this card's Python face.

    The answer comes from ``decision.DecisionClient`` + ``FakeBackend`` via the
    production ``request_prepared`` protocol; the facts are written by the
    production lifecycle writer, read by ``decision_history``, served by the
    real loopback monitor routes and rendered by the shipped assets. No business
    action is invented: only the recorded start/note/request/settled rows exist.
    """
    root = _root(tmp_path)
    store = _store(root)
    case = json.loads(
        (PACKAGE_DIR / "decide_cases" / "dp-gate-approve.json").read_text(encoding="utf-8")
    )["book"]
    material = case["material"]
    preparation = case["preparation"]
    note_text = json.dumps(material["pm_note"], ensure_ascii=False, sort_keys=True)
    before = _task("running", T0, completed=[], remaining=["close"], blockers=None)
    meta = _meta(task_before=before)
    decision_id = "dp-gate-approve:" + str(meta.logical_id)
    _start(store, meta, decision_id)
    assert lifecycle.record_note(
        store, meta, decision_id=decision_id, pm_note=note_text,
        prepared_at=str(preparation["prepared_at"]),
    ).recorded
    client = decision.DecisionClient(
        decision.DecisionConfig(
            enabled=True, project_root=root, evidence_path=tmp_path / "transport.jsonl"
        ),
        decision.FakeBackend(
            [
                decision.BackendOutcome(
                    True,
                    None,
                    False,
                    {
                        "gate_decision": {"value": "approve", "confidence": 0.95},
                        "basis_id": {"value": "gate-approve", "confidence": 0.95},
                    },
                    0,
                )
            ]
        ),
    )
    result = client.request_prepared(
        "dp-gate-approve", material, preparation,
        logical_id=meta.logical_id, actor_role="pm",
    )
    assert result["business_decisions"] == 1 and result["choice"] == "approve", result["reason"]
    assert result["basis_source"] == "pm-prepared"
    assert lifecycle.record_request(
        store, meta, decision_id=decision_id, result=result,
        material=material, preparation=preparation,
    ).recorded
    assert lifecycle.record_settled(
        store, meta, decision_id=decision_id, outcome="ok", reason="the round was closed by the PM",
        task_after=_task("running", T1, completed=[], remaining=["close"], blockers=[]),
    ).recorded

    before_hashes = _tree_hashes(root)
    payloads = _read_monitor(root)
    record = payloads["listing"]["data"]["records"][0]
    assert record["dp"] == "dp-gate-approve"
    entry = record["entry"]
    assert entry["registry_status"] == "active"
    assert entry["has_pm_note"] is True and entry["has_selected_basis"] is True
    assert entry["selected_choice"] == "approve"
    assert entry["requested"] is True and entry["request_count"] == 1
    # the stored request body is a detail-only fact (the list carries presence only)
    assert "request" not in entry
    detail_entry = _detail_for(payloads, "dp-gate-approve")["entry"]
    assert detail_entry["request"]["business_decisions"] == 1

    steps = _open_detail_steps(payloads, "dp-gate-approve") + [
        {"type": "click", "target": "#record-dialog-tab-log", "snapshot": "log"},
        {"type": "click", "target": "#tab-playground"},
        {"type": "setValue", "target": "#dp-select", "value": "dp-gate-approve"},
        {"type": "dispatch", "target": "#dp-select", "event": {"type": "change"}, "snapshot": "form"},
    ]
    dom = ui._run_dom(tmp_path, _dom_scenario(payloads, steps))
    log = ui._snapshot(dom, "log")
    text = log["logText"] or ""

    note_text_rendered = log["testIds"]["entry-note-text"][0]
    basis_text_rendered = log["testIds"]["entry-basis-text"][0]
    assert note_text_rendered == note_text
    assert basis_text_rendered == result["basis_text"] != ""
    assert note_text_rendered not in basis_text_rendered
    assert log["testIds"]["entry-note"][0].count("PM 提交前预备说明") == 1
    assert "不是模型自然产生的理由" in log["testIds"]["entry-basis"][0]
    assert "业务决策数：1" in text and "接口可用：true" in text
    # The recorded settlement is this round only; nothing claims an execution.
    assert "本轮处理完成，不代表整个任务已交付" in text
    assert "已执行行动：未记录" in text and "已执行行动（" not in text
    assert "任务终态：未记录" in text
    assert "无记录的后继请求（声明不等于发起）。" in text
    # Real recorded snapshots: before is the creation fact, after the settlement.
    assert "已完成：无（真实空列表）" in text
    assert "待处理：close" in text
    assert "阻塞：未记录" in text and "阻塞：无（真实空列表）" in text
    assert "状态：执行中" in text
    assert "观察顺序：non-decreasing" in text
    assert [item["choice"] for item in ui._snapshot(dom, "form")["entryChoices"]] == [
        "approve", "steer", "need_fix", "reject",
    ]
    _only_get_or_bootstrap(dom)
    assert _tree_hashes(root) == before_hashes, "reading history over HTTP never rewrites it"


@pytest.fixture
def live_dom(monkeypatch, entry_dom):
    """Keep the shipped faux DOM; replace only fetch and network settlement.

    Unlike the older canned scenarios, every response here comes from the
    running loopback monitor, including its one-use bootstrap. No renderer,
    business decision, successful envelope or receipt is implemented here.
    """
    harness = ui.DOM_HARNESS_JS
    replacements = {
        "const fetchCalls = [];": "const fetchCalls = [];\nconst liveResponses = [];\nlet livePending = 0;",
        "  let entry = routeFor(url);": '''  if (scenario.liveOrigin) {
    livePending += 1;
    try {
      const response = await globalThis.fetch(scenario.liveOrigin + url, {
        method: opts.method || "GET",
        headers: Object.assign({}, headers, {Origin: scenario.liveOrigin, Connection: "close"}),
        body: opts.body,
      });
      const body = await response.json();
      liveResponses.push({url, status: response.status, body});
      return responseFor({status: response.status, body});
    } finally { livePending -= 1; }
  }
  let entry = routeFor(url);''',
        "async function drain() {": '''async function drain() {
  for (let attempt = 0; attempt < 1500; attempt += 1) {
    await new Promise((resolve) => setTimeout(resolve, 10));
    if (!livePending) break;
  }
  if (livePending) throw new Error("live loopback fetch did not settle");''',
        "await new Promise((resolve) => setTimeout(resolve, 0));":
            "await new Promise((resolve) => setImmediate(resolve));",
        "return { ok: true, snapshots, fetchCalls, storageWrites, clipboardWrites };":
            "return { ok: true, snapshots, fetchCalls, storageWrites, clipboardWrites, liveResponses };",
    }
    for original, replacement in replacements.items():
        assert harness.count(original) == 1, original
        harness = harness.replace(original, replacement)
    monkeypatch.setattr(ui, "DOM_HARNESS_JS", harness)


def _live_fixture(tmp_path, dp, failure=None):
    project = materials_suite._observe_project(tmp_path / dp)
    (project / ".agenticdoc").mkdir()
    book = materials_suite._case_book(dp)
    material = book["material"]
    field = next(name for name, value in material.items() if isinstance(value, str))
    choices = list(dpts.resolve_entry_choices(dp, material))
    choice, basis = materials_suite._prepared_answer(dp, material, book["preparation"])
    answers = {
        materials_suite.BUSINESS_QIDS[dp]: {"value": choice, "confidence": 0.9},
        "basis_id": {"value": basis, "confidence": 0.9},
    }
    if failure == "missing-choice":
        answers.pop(materials_suite.BUSINESS_QIDS[dp])
    elif failure == "wrong-choice":
        answers[materials_suite.BUSINESS_QIDS[dp]]["value"] = "unprepared-choice"
    elif failure == "wrong-basis":
        answers["basis_id"]["value"] = "unprepared-basis"
    elif failure == "missing-basis":
        answers.pop("basis_id")
    elif failure == "mismatched-basis":
        book["preparation"]["basis_catalog"].append({
            "id": "prepared-for-other-choice", "text": "Prepared evidence for a different choice",
            "material_refs": [field], "applies_to": [next(other for other in choices if other != choice)],
        })
        answers["basis_id"]["value"] = "prepared-for-other-choice"
    outcome = decision.BackendOutcome(
        failure != "unavailable", "isolated-unavailable" if failure == "unavailable" else None,
        False, answers, 0,
    )
    backend = decision.FakeBackend([outcome])
    provider = decision_playground.DecisionPlayground(project, backend=backend)
    deps = decision_monitor.MonitorDeps(
        playground=provider, redactor=wire.SubstringRedactor((materials_suite.API_KEY,)),
    )
    return project, book, field, backend, provider, deps


def _live_steps(dp, book):
    return [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": "#pg-cases-load"},
        {"type": "setValue", "target": "#case-select", "value": dp},
        {"type": "click", "target": "#pg-case-open", "snapshot": "generated"},
        # Only evidence notes change to a valid local command reference. The
        # generated material/preparation/context are preserved until UI editing.
        {"type": "setValue", "target": "#book-editor", "value": json.dumps(book)},
        {"type": "dispatch", "target": "#book-editor", "event": {"type": "input"}},
    ]


def _live_response(dom, url):
    return next(row for row in dom["liveResponses"] if row["url"] == url)


def _assert_live_zero_effects(project, provider, before, dom, dp, case):
    prefix = provider.test_root.relative_to(project).as_posix() + "/"
    assert {name: value for name, value in _tree_hashes(project).items() if not name.startswith(prefix)} == before
    assert dom["storageWrites"] == []
    assert all(not row["pwned"] for row in dom["snapshots"])
    # Complete request bodies and actual API responses are captured by pytest;
    # page tokens/headers/bootstrap bodies are deliberately excluded.
    print("[LIVE-POST] " + json.dumps({
        "dp": dp, "case": case,
        "requests": [{key: row[key] for key in ("url", "method", "body")}
                     for row in dom["fetchCalls"] if row["url"] in ("/api/test/validate", "/api/test/submit")],
        "responses": [row for row in dom["liveResponses"] if row["url"].startswith("/api/test/")],
        "production_unchanged": True,
    }, ensure_ascii=False))


@pytest.mark.parametrize("dp", ACTIVE_DPS)
def test_generated_case_form_edit_real_post_and_history_chain(tmp_path, dom_env, live_dom, dp):
    project, book, field, backend, provider, deps = _live_fixture(tmp_path, dp)
    edited_value = book["material"][field] + " [edited through the real entry form]"
    with monitor_suite._running(project, deps=deps) as instance:
        before = _tree_hashes(project)
        steps = _live_steps(dp, book) + [
            {"type": "setValue", "target": f'[data-testid="pg-entry-input"][data-field="{field}"]', "value": edited_value},
            {"type": "click", "target": "#pg-entry-apply", "snapshot": "edited"},
            {"type": "click", "target": "#pg-validate", "snapshot": "validated"},
            {"type": "click", "target": "#pg-submit", "snapshot": "submitted"},
            {"type": "click", "target": '[data-testid="pg-history-open"]'},
            {"type": "click", "target": '[data-testid="pg-dag-node"][data-node-id="action"]', "snapshot": "action"},
        ]
        dom = ui._run_dom(tmp_path, {"liveOrigin": instance.origin, "hash": "#boot=" + instance.boot_code, "steps": steps})
        generated = json.loads(ui._snapshot(dom, "generated")["editorValue"])
        assert generated["schema_version"] == 3
        assert generated["material"] == book["material"]
        edited = json.loads(ui._snapshot(dom, "edited")["editorValue"])
        assert edited["material"][field] == edited_value
        assert edited["preparation"] == generated["preparation"]
        assert edited.get("context") == generated.get("context")
        assert [row["url"] for row in ui._snapshot(dom, "edited")["fetchCalls"] if row["method"] == "POST"] == ["/api/bootstrap"]
        posted = [row for row in dom["fetchCalls"] if row["url"] in ("/api/test/validate", "/api/test/submit")]
        assert len(posted) == 2 and all(row["method"] == "POST" for row in posted)
        assert all(json.loads(row["body"])["book"] == edited for row in posted)
        validated = _live_response(dom, "/api/test/validate")
        assert validated["status"] == 200 and validated["body"]["data"]["ok"] is True
        submitted = _live_response(dom, "/api/test/submit")["body"]["data"]
        assert submitted["state"] == "succeeded", submitted
        assert submitted["decision_ran"] is True and submitted["observe_only"] is True
        assert submitted["outcome"]["status"] == "suggested"
        assert submitted["outcome"]["preview"]["executor_invoked"] is False
        assert len(backend.calls) == 1
        assert edited_value in json.dumps(backend.calls[0]["state"], ensure_ascii=False)
        assert "basis_id" in backend.calls[0]["questions"]
        assert set(backend.calls[0]["questions"]["basis_id"]["choices"]) == {row["id"] for row in edited["preparation"]["basis_catalog"]}
        assert "basis_id" in submitted["answer"]
        history_rows = [row for row in dom["liveResponses"] if row["url"] == "/api/test/history"][-1]["body"]["data"]["records"]
        assert [row["submission_id"] for row in history_rows] == [submitted["submission_id"]]
        detail = _live_response(dom, "/api/test/submissions/" + submitted["submission_id"])["body"]["data"]
        assert detail["decision_id"] == submitted["decision_id"] and detail["book_ref"] == submitted["book_ref"]
        action = ui._snapshot(dom, "action")
        assert "observe_only：未执行任何业务行动" in action["pgNodeDetail"]
        assert "任务已完成" not in action["pgDetailText"]
        _assert_live_zero_effects(project, provider, before, dom, dp, "positive")


@pytest.mark.parametrize("dp", ACTIVE_DPS)
@pytest.mark.parametrize("failure", ["missing-material", "wrong-type", "retired-book", "unavailable", "missing-choice", "wrong-choice", "wrong-basis", "missing-basis", "mismatched-basis"])
def test_real_observation_post_refusals_never_execute(tmp_path, dom_env, live_dom, dp, failure):
    project, book, field, backend, provider, deps = _live_fixture(tmp_path, dp, failure)
    if failure == "missing-material":
        book["material"].pop(field)
    elif failure == "wrong-type":
        book["material"][field] = {"invalid": "expected text"}
    elif failure == "retired-book":
        book["decision_point"] = "dp1-dispatch-type"
    with monitor_suite._running(project, deps=deps) as instance:
        before = _tree_hashes(project)
        steps = _live_steps(dp, book) + [
            {"type": "click", "target": "#pg-validate", "snapshot": "validated"},
            {"type": "click", "target": "#pg-submit", "snapshot": "submitted"},
        ]
        dom = ui._run_dom(tmp_path, {"liveOrigin": instance.origin, "hash": "#boot=" + instance.boot_code, "steps": steps})
        response = _live_response(dom, "/api/test/submit")
        data = response["body"].get("data") or {}
        assert data.get("state") != "succeeded", response
        assert data.get("issues") or data.get("outcome", {}).get("escalated_reason") or response["body"].get("error"), response
        assert len(backend.calls) == (0 if failure in ("missing-material", "wrong-type", "retired-book") else 1)
        if data.get("outcome"):
            assert data["outcome"].get("preview", {}).get("executor_invoked") is not True
        assert "任务已完成" not in ui._snapshot(dom, "submitted")["pgDetailText"]
        _assert_live_zero_effects(project, provider, before, dom, dp, failure)


def test_successor_note_and_basis_are_three_separate_dom_sources(tmp_path, dom_env, entry_dom):
    root = _root(tmp_path)
    store = _store(root)
    gate_material = _material("dp-gate-approve")
    parent_meta = _meta()
    parent_id = "dp-gate-approve:gate-parent"
    _start(store, parent_meta, parent_id)
    assert lifecycle.record_note(
        store, parent_meta, decision_id=parent_id,
        pm_note="事项：steer；批准后动作：successor", prepared_at=PREPARED_AT,
    ).recorded
    _request(store, parent_meta, parent_id, gate_material, _result("dp-gate-approve", "steer"))

    steer_meta = _meta()
    steer_id = "dp-pm-steer:steer-1"
    _start(store, steer_meta, steer_id)
    assert lifecycle.record_note(
        store, steer_meta, decision_id=steer_id,
        pm_note="successor: narrow the remaining slice", prepared_at=PREPARED_AT,
        parent_ref=parent_id,
    ).recorded
    _request(
        store, steer_meta, steer_id, _material("dp-pm-steer"),
        _result("dp-pm-steer", None, available=False, business=0, reason="input-incomplete"),
        parent_ref=parent_id,
    )

    fix_meta = _meta()
    fix_id = "dp-auto:fix-1"
    _start(store, fix_meta, fix_id)
    _request(
        store, fix_meta, fix_id, _material("dp-auto"),
        _result("dp-auto", "rollback-now"), parent_ref=parent_id,
    )
    assert lifecycle.record_executed(
        store, fix_meta, decision_id=fix_id, action="narrow",
        result="rolled the write back", reason="the prepared repair was executed",
        task_after=_task("running", T1),
    ).recorded
    assert lifecycle.record_settled(
        store, fix_meta, decision_id=fix_id, outcome="ok", reason="repair round finished",
        task_after=_task("running", T2),
    ).recorded

    declared_meta = _meta()
    declared_id = "dp-pm-steer:declared-1"
    _start(store, declared_meta, declared_id)
    assert lifecycle.record_note(
        store, declared_meta, decision_id=declared_id,
        pm_note="declared successor, not requested", prepared_at=PREPARED_AT,
        parent_ref=parent_id,
    ).recorded

    payloads = _read_monitor(root)
    parent_opaque = _opaque_for(payloads, "dp-gate-approve")
    steps = [{
        "type": "click",
        "target": f'[data-testid="record-dag-open"][data-opaque="{parent_opaque}"]',
        "snapshot": "parent",
    }]
    dom = ui._run_dom(tmp_path, _dom_scenario(payloads, steps))
    snapshot = ui._snapshot(dom, "parent")
    text = snapshot["logText"] or ""

    assert snapshot["testIds"]["entry-note-text"][0] == "事项：steer；批准后动作：successor"
    assert snapshot["testIds"]["entry-basis-text"][0] == BASIS_TEXT
    assert snapshot["testIds"]["entry-note-text"][0] not in snapshot["testIds"]["entry-basis-text"][0]
    successors = {item["decisionId"]: item for item in snapshot["successorRows"]}
    assert set(successors) == {steer_id, fix_id, declared_id}
    assert successors[steer_id]["requested"] == "true"
    assert successors[fix_id]["requested"] == "true"
    assert successors[declared_id]["requested"] == "false"
    assert "input-incomplete" in successors[steer_id]["text"]
    assert "实际已执行行动：未记录（没有行动回执）" in successors[steer_id]["text"]
    assert "narrow" in successors[fix_id]["text"]
    assert "本轮结算：ok" in successors[fix_id]["text"]
    assert "否（只登记了关联，不是请求）" in successors[declared_id]["text"]
    assert all("不解除父 gate" in item["text"] for item in successors.values())
    # the parent is unchanged: its selection is not a release or a repair
    assert "本次选择：steer" in text
    assert "已执行行动：未记录" in text
    _only_get_or_bootstrap(dom)


def test_retired_history_is_read_only_in_the_list_detail_and_dom(tmp_path, dom_env, entry_dom):
    root = _root(tmp_path)
    retired_decision = _append_retired_record(root, "dp1-dispatch-type", "dom-retired")
    store = _store(root)
    active_meta = _meta()
    active_id = "dp-w-type:active-beside-retired"
    _start(store, active_meta, active_id)
    _request(store, active_meta, active_id, _material("dp-w-type"), _result("dp-w-type", "coding"))
    before = _tree_hashes(root)

    payloads = _read_monitor(root)
    retired_row = next(
        record for record in payloads["listing"]["data"]["records"] if record["dp"] == "dp1-dispatch-type"
    )
    assert retired_row["entry"]["registry_status"] == "retired"
    # the retired id stays in the read-only directory, never in the callable set
    registry = payloads["dps"]["data"]
    assert registry["callable_count"] == 8
    assert "dp1-dispatch-type" not in [point["id"] for point in registry["points"]]
    assert "dp1-dispatch-type" in [item["id"] for item in registry["retired"]]
    steps = [{
        "type": "click",
        "target": f'[data-testid="record-open"][data-opaque="{retired_row["opaque_id"]}"]',
        "snapshot": "retired",
    }]
    dom = ui._run_dom(tmp_path, _dom_scenario(payloads, steps))
    snapshot = ui._snapshot(dom, "retired")
    text = snapshot["logText"] or ""

    states = {item["status"]: item for item in snapshot["rowEntryStates"]}
    assert states["retired"]["rerun"] == "false"
    assert "不可发起新运行" in states["retired"]["text"]
    assert states["active"]["rerun"] == "true"
    assert snapshot["entryFacts"] == [{"status": "retired", "rerun": "false"}]
    assert "entry-rerun-unavailable" in snapshot["testIds"]
    assert "entry-rerun-available" not in snapshot["testIds"]
    assert "testIds" in snapshot and "entry-retired-note" in snapshot["testIds"]
    assert "退役 id 只解释旧记录" in text
    assert "不可发起新运行" in text
    _only_get_or_bootstrap(dom)
    assert _tree_hashes(root) == before, "a retired history read keeps every byte"
    with pytest.raises(ValueError):
        dpts.require_active_dp("dp1-dispatch-type")


def test_sign_sections_arrays_and_worker_null_empty_are_distinct_in_the_dom(
    tmp_path, dom_env, entry_dom
):
    root = _root(tmp_path)
    store = _store(root)
    sign_material = _material("dp-sign-key")
    before = _task("running", T0, completed=[], remaining=None, blockers=[])
    sign_meta = _meta(task_before=before)
    sign_id = "dp-sign-key:sign-dom"
    _start(store, sign_meta, sign_id)
    _book(root, sign_id, "dp-sign-key", sign_material)
    _request(store, sign_meta, sign_id, sign_material, _result("dp-sign-key", "finalize"))

    worker_material = _material("dp-w-check-task")
    worker_meta = _meta(task_before=_task("running", T0, completed=["read"], remaining=["write"], blockers=[]))
    worker_id = "dp-w-check-task:worker-dom"
    _start(store, worker_meta, worker_id)
    _request(store, worker_meta, worker_id, worker_material, _result("dp-w-check-task", "continue"))

    payloads = _read_monitor(root)
    sign_opaque = next(
        record["opaque_id"] for record in payloads["listing"]["data"]["records"]
        if record["dp"] == "dp-sign-key"
    )
    worker_opaque = next(
        record["opaque_id"] for record in payloads["listing"]["data"]["records"]
        if record["dp"] == "dp-w-check-task"
    )
    steps = [
        {"type": "click", "target": f'[data-testid="record-dag-open"][data-opaque="{sign_opaque}"]'},
        {"type": "click", "target": '[data-testid="dag-node"][data-node-id="input"]', "snapshot": "sign-input"},
        {"type": "click", "target": "#record-dialog-tab-log", "snapshot": "sign-log"},
        {"type": "click", "target": "#detail-close"},
        {"type": "click", "target": f'[data-testid="record-dag-open"][data-opaque="{worker_opaque}"]'},
        {"type": "click", "target": "#record-dialog-tab-log", "snapshot": "worker-log"},
    ]
    dom = ui._run_dom(tmp_path, _dom_scenario(payloads, steps))

    sign_input = ui._snapshot(dom, "sign-input")["nodeDetail"] or ""
    for label in ("交付目标与验收条件", "实际完成情况", "验证证据", "未完成项及影响", "已验证", "未验证"):
        assert label in sign_input, label
    assert "（空列表）" in sign_input
    assert "live deployment unverified" in sign_input

    # sign task axes keep null (not recorded) and [] (the producer's real none) apart
    sign_log = ui._snapshot(dom, "sign-log")["logText"] or ""
    assert "已完成：无（真实空列表）" in sign_log
    assert "待处理：未记录" in sign_log
    assert "阻塞：无（真实空列表）" in sign_log
    assert "本次选择：finalize" in sign_log
    assert "任务终态：未记录" in sign_log

    worker = ui._snapshot(dom, "worker-log")
    worker_text = worker["logText"] or ""
    assert "已完成：" in worker_text and "read" in worker_text
    assert "待处理：" in worker_text and "write" in worker_text
    assert "阻塞：无（真实空列表）" in worker_text
    assert "任务终态：未记录" in worker_text
    assert "本轮结算（settled）不代表任务完成" in worker_text
    _only_get_or_bootstrap(dom)


def test_observe_only_submission_detail_never_shows_business_success(
    tmp_path, dom_env, entry_dom
):
    root = _root(tmp_path)
    store = _store(root)
    meta = _meta()
    decision_id = "dp-w-type:observe-only"
    _start(store, meta, decision_id)
    _request(store, meta, decision_id, _material("dp-w-type"), _result("dp-w-type", "coding"))
    payloads = _read_monitor(root)

    # CONTRACT FIXTURE: the /api/test/* body shape the page consumes. It says a
    # captured observation succeeded; it must never read as a business action.
    submission = {
        "submission_id": "ui-observe-1",
        "dp": "dp-w-type",
        "state": "succeeded",
        "decision_ran": True,
        "decision_id": "dp-w-type:observe-only",
        "call_id": "call-observe-1",
        "zero_call": False,
        "http_attempts": 1,
        "book_ref": "book-observe",
        "state_digest": "digest-observe",
        "answer_persisted": False,
        "projection_status": "not-recorded",
        "issues": [],
        "outcome": {"status": "observed", "mode": "auto"},
        "attempts": [],
        "observe_only": True,
    }
    test_history = {
        "records": [
            {
                "submission_id": "ui-observe-1",
                "dp": "dp-w-type",
                "state": "succeeded",
                "zero_call": False,
                "http_attempts": 1,
                "answer_persisted": False,
                "projection_status": "not-recorded",
            }
        ],
        "total": 1,
        "limit": 20,
        "offset": 0,
        "observe_only": True,
        "scope": "test",
    }
    steps = [
        {"type": "click", "target": "#tab-playground"},
        {"type": "click", "target": '[data-testid="pg-history-open"][data-submission-id="ui-observe-1"]'},
        {"type": "click", "target": '[data-testid="pg-dag-node"][data-node-id="action"]', "snapshot": "action"},
    ]
    dom = ui._run_dom(
        tmp_path,
        _dom_scenario(
            payloads,
            steps,
            testHistory={"status": 200, "body": ui._envelope(test_history)},
            submission={"status": 200, "body": ui._envelope(submission)},
        ),
    )
    snapshot = ui._snapshot(dom, "action")
    node = snapshot["pgNodeDetail"] or ""
    assert "observe_only：未执行任何业务行动" in node
    assert "已执行行动：未记录" in node and "已执行行动（" not in node
    detail = snapshot["pgDetailText"] or ""
    assert "测试观察路径不执行任何业务动作" in detail
    assert "任务已完成" not in detail
    assert "本轮处理完成" not in detail
    _only_get_or_bootstrap(dom)
