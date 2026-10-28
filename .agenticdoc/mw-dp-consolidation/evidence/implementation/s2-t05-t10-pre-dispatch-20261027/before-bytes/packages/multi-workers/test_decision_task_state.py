"""T22 task-state facts: local envelopes, real writer, read projection, no model."""
from __future__ import annotations

import io
import json
from types import SimpleNamespace

import pytest

import decision
import decision_history as history
import decision_lifecycle as lifecycle
import decision_wire as wire
import mw
import test_decision_context_readable_backend as backend
import test_decision_context_readable_ui as ui

_isolated_environment = ui._isolated_environment


def state(status="running", *, source="agent-report", completed=None, remaining=None, blockers=None):
    return dict(status=status, source=source, observed_at="2026-10-24T08:00:00+00:00",
                completed=completed, remaining=remaining, blockers=blockers)


def _meta(before=None, task=True):
    raw=backend._meta().as_meta()
    if not task: raw["task_key"]=None
    if before is not None: raw["task_before"]=before
    return lifecycle.DecisionMeta.from_envelope({"meta":raw})


def _record(tmp_path, *, before=None, after=None, outcome="ok"):
    root=backend._root(tmp_path)
    store=backend._store(root)
    meta=_meta(before)
    decision_id=backend._append_archive(root,dp=backend.DP1,trigger_id="t22",authority="advisory",escalated_reason=None,confidence=0.94)
    assert lifecycle.record_start(store,meta,decision_id=decision_id).recorded
    assert lifecycle.record_consumed(store,meta,decision_id=decision_id,answer="research").recorded
    assert lifecycle.record_executed(store,meta,decision_id=decision_id,action="record",result="answer-returned").recorded
    kwargs={} if after is None else {"task_after":after}
    assert lifecycle.record_settled(store,meta,decision_id=decision_id,outcome=outcome,reason="dispatch-refused" if outcome=="rework" else "round finished",**kwargs).recorded
    snapshot=history.load_history(root,redact=wire.SubstringRedactor((backend.SECRET,)))
    return root, next(r for r in snapshot.records if r.decision_id==decision_id)


def test_before_is_local_metadata_and_does_not_enter_model_material():
    before=state(completed=["reviewed task card"],remaining=["dispatch worker"],blockers=[])
    envelope=_meta(before).as_envelope({"task_goal":"synthetic goal"})
    assert envelope["meta"]["task_before"]==before
    assert envelope["material"]=={"task_goal":"synthetic goal"}
    before["completed"].append("later change")
    assert envelope["meta"]["task_before"]["completed"]==["reviewed task card"]


def test_real_start_and_settled_snapshots_survive_history(tmp_path):
    before=state("not-queued",source="worker-registry")
    after=state("pending",source="worker-registry",completed=[],remaining=["worker start"],blockers=[])
    root,record=_record(tmp_path,before=before,after=after)
    action=backend._nodes(record)["action"]["detail"]
    assert action["task_before"]==before and action["task_after"]==after
    rows=[json.loads(line) for line in wire.production_lifecycle_sink(root).read_bytes().splitlines()]
    assert next(r for r in rows if r["kind"]=="record-start")["task_before"]==before
    assert next(r for r in rows if r.get("lifecycle")=="settled")["task_after"]==after


def test_no_snapshot_is_not_inferred_from_ok_or_rework(tmp_path):
    _,record=_record(tmp_path,outcome="rework")
    action=backend._nodes(record)["action"]["detail"]
    assert action.get("task_before") is None and action.get("task_after") is None


@pytest.mark.parametrize("field,value",[("status","invented"),("source","model"),("observed_at","2026-10-24T08:00:00"),("observed_at","not-time"),("completed","all done"),("blockers",[1])])
def test_invalid_snapshot_is_refused_without_echoing_value(field,value):
    snapshot=state();snapshot[field]=value
    with pytest.raises(lifecycle.LifecycleInputError) as error: _meta(snapshot)
    assert str(value) not in str(error.value)


def test_taskless_decision_cannot_claim_a_task_snapshot():
    with pytest.raises(lifecycle.LifecycleInputError): _meta(state(),task=False)


def test_consumed_cannot_record_an_after_state(tmp_path):
    root=backend._root(tmp_path)
    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.record_lifecycle(backend._store(root),_meta(),stage="consumed",decision_id=backend.DP1+":task-state",answer="research",task_after=state())


def test_write_and_read_redaction_cover_snapshot_lists_and_keys(tmp_path):
    before=state(completed=[backend.SECRET+" t22-private-progress"],remaining=[],blockers=[])
    root,record=_record(tmp_path,before=before,after=state("unknown"))
    sink=wire.production_lifecycle_sink(root)
    raw=sink.read_bytes()
    assert backend.SECRET.encode() not in raw
    wider=history.load_history(root,redact=wire.SubstringRedactor(("t22-private-progress",))).detail(record.opaque_id).as_dict(detail=True)
    assert "t22-private-progress" not in json.dumps(wider.get("workbench",{}).get("nodes",[]))
    assert sink.read_bytes()==raw


def test_reader_without_redactor_withholds_snapshot_prose(tmp_path):
    root,record=_record(tmp_path,before=state(completed=["private step"]),after=state())
    folded=history.load_history(root).detail(record.opaque_id)
    detail=backend._nodes(folded)["action"]["detail"]
    assert "private step" not in json.dumps(detail)
    assert detail["task_before_visibility"]=="withheld"


def test_real_cli_freezes_before_locally_and_passes_only_material_to_decision_boundary(tmp_path, monkeypatch, capsys):
    root=backend._root(tmp_path);store=backend._store(root);meta=_meta(state(completed=[backend.SECRET+" synthetic progress"]))
    material={"task_goal":"synthetic", "task_requirements":"synthetic", "task_deliverables":"synthetic"}
    monkeypatch.setattr(mw.sys,"stdin",io.StringIO(json.dumps(meta.as_envelope(material))))
    monkeypatch.setattr(mw,"_decide_config_snapshot",lambda root:object())
    monkeypatch.setattr(mw.decision,"credential_snapshot",lambda cfg:None)
    monkeypatch.setattr(mw,"_decide_lifecycle_store",lambda *args:store)
    monkeypatch.setattr(mw.decision,"DecisionClient",lambda *args,**kwargs:object())
    calls=[]
    def fake_decide(dp,trigger,project_dir,**kwargs):
        calls.append(trigger.data)
        rows=lifecycle.read_lifecycle(store).events
        assert rows[0]["task_before"]["status"]=="running"
        assert backend.SECRET.encode() not in store.sink.read_bytes()
        return SimpleNamespace(decision_id=dp+":"+meta.logical_id,status="escalated",answer=None,detail="synthetic unavailable")
    monkeypatch.setattr(mw.decision_points,"decide_for",fake_decide)
    monkeypatch.setattr(mw,"_decide_run_payload",lambda outcome:{"available":False})
    assert mw._decide_run_versioned(SimpleNamespace(dp_id=backend.DP1,json=True),root)==0
    assert calls==[material]
    capsys.readouterr()


def test_after_observation_cannot_precede_before_observation(tmp_path):
    root=backend._root(tmp_path);store=backend._store(root);meta=_meta(state())
    after=state();after["observed_at"]="2026-10-23T08:00:00Z"
    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.record_settled(store,meta,decision_id=backend.DP1+":out-of-order",outcome="ok",task_after=after)
    assert not store.sink.exists()


def test_after_requires_the_same_tasks_creation_fact(tmp_path):
    root=backend._root(tmp_path);store=backend._store(root);meta=_meta()
    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.record_settled(store,meta,decision_id=backend.DP1+":orphan",outcome="ok",task_after=state())
    assert not store.sink.exists()
    lifecycle.record_start(store,meta,decision_id=backend.DP1+":bound")
    raw=meta.as_meta();raw["task_key"]="other-task"
    foreign=lifecycle.DecisionMeta.from_envelope({"meta":raw})
    original=store.sink.read_bytes()
    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.record_settled(store,foreign,decision_id=backend.DP1+":bound",outcome="ok",task_after=state("done"))
    assert store.sink.read_bytes()==original


def test_reader_does_not_attribute_another_tasks_after_snapshot(tmp_path):
    root,record=_record(tmp_path,before=state("running"),after=state("done"))
    sink=wire.production_lifecycle_sink(root)
    rows=[json.loads(line) for line in sink.read_bytes().splitlines()]
    rows[-1]["task_key"]="other-task"
    sink.write_bytes(b"".join(json.dumps(row).encode()+b"\n" for row in rows))
    saved=sink.read_bytes()
    projected=history.load_history(root,redact=wire.SubstringRedactor((backend.SECRET,))).detail(record.opaque_id)
    action=backend._nodes(projected)["action"]["detail"]
    assert action["task_after"] is None and action["task_after_visibility"]=="invalid"
    assert sink.read_bytes()==saved


def test_duplicate_after_write_does_not_replace_first_snapshot(tmp_path):
    root=backend._root(tmp_path);store=backend._store(root);meta=_meta(state())
    decision_id=backend.DP1+":snapshot-dedupe"
    lifecycle.record_start(store,meta,decision_id=decision_id)
    one=lifecycle.record_settled(store,meta,decision_id=decision_id,outcome="ok",event_id="t22-same",task_after=state("pending"))
    raw=wire.production_lifecycle_sink(root).read_bytes()
    two=lifecycle.record_settled(store,meta,decision_id=decision_id,outcome="ok",event_id="t22-same",task_after=state("done"))
    assert one.recorded and two.duplicate and wire.production_lifecycle_sink(root).read_bytes()==raw


def _production_capture(*secrets):
    return decision.credential_redactor(decision.DecisionConfig(enabled=True,extras={}),extra_secrets=tuple(secrets),env={})


def test_the_store_filter_is_a_capture_filter_while_the_gate_shape_stays_refused(tmp_path):
    """RED before the fix: the injected gate filter had no boundary scrub.

    ``known_secret_redactor`` is the book-gate shape by design and stays refused as
    a capture filter (T05q); the lifecycle store must receive the wire-compatible
    wrapper instead of a filter the sanitizer cannot call.
    """
    cfg=decision.DecisionConfig(enabled=True,extras={})
    store=mw._decide_lifecycle_store(tmp_path/"project",cfg,decision.credential_snapshot(cfg,env={}))
    assert decision._capture_filter_contract_issue(store.redact) is None
    assert callable(getattr(store.redact,"scrub_tail_prefix",None))
    gate=decision.known_secret_redactor(cfg,extra_secrets=("t22-partial-secret-value",),env={})
    assert decision._capture_filter_contract_issue(gate) is not None


def test_production_filter_writes_the_six_field_snapshot_unchanged(tmp_path):
    """RED before the fix: the key scrub renamed ``observed_at``/``completed``."""
    capture=_production_capture("t22-partial-secret-value","d22-known-value")
    assert capture is not None and decision._capture_filter_contract_issue(capture) is None
    root=tmp_path/"project"
    store=lifecycle.LifecycleStore.production(root,redact=capture)
    before=state("not-queued",source="worker-registry",completed=["reviewed task card"],remaining=["dispatch worker"],blockers=[])
    after=state("pending",source="dispatch-result",completed=[],remaining=["worker start"],blockers=[])
    meta=_meta(before)
    decision_id=backend.DP1+":production"
    assert lifecycle.record_start(store,meta,decision_id=decision_id).recorded
    assert lifecycle.record_executed(store,meta,decision_id=decision_id,action="direct-exec",result="worker queued").recorded
    assert lifecycle.record_settled(store,meta,decision_id=decision_id,outcome="ok",task_after=after).recorded
    rows=[json.loads(line) for line in store.sink.read_bytes().splitlines()]
    start=next(r for r in rows if r.get("kind")=="record-start")
    settled=next(r for r in rows if r.get("lifecycle")=="settled")
    assert start["task_before"]==before
    assert set(start["task_before"])=={"status","source","observed_at","completed","remaining","blockers"}
    assert settled["task_after"]==after
    # The same rows must read back as recorded facts (not withheld/illegal).
    projected=history.load_history(root,redact=capture)
    record=next(r for r in projected.records if r.decision_id==decision_id)
    detail=history.load_history(root,redact=capture).detail(record.opaque_id).as_dict(detail=True)
    action=next(node["detail"] for node in detail["workbench"]["nodes"] if node.get("id")=="action")
    assert action["task_before"]==before and action["task_before_visibility"]=="recorded"
    assert action["task_after"]==after and action["task_after_visibility"]=="recorded"


def test_an_unprovable_capture_filter_refuses_the_store(tmp_path,monkeypatch):
    monkeypatch.setattr(mw.decision,"credential_redactor",lambda *args,**kwargs: None)
    with pytest.raises(lifecycle.LifecycleInputError):
        mw._decide_lifecycle_store(tmp_path/"project",None,None)


def test_metadata_key_scrub_keeps_labels_but_still_cuts_a_real_tail():
    scope=SimpleNamespace(redact=wire.SubstringRedactor(("t22-partial-secret-value","d22-known-value")))
    for label in ("status","source","observed_at","completed","remaining","blockers"):
        assert wire._sanitize_metadata_key(scope,label)==label
    assert wire._sanitize_metadata_key(scope,"observed_at")=="observed_at"
    assert wire._sanitize_metadata_key(scope,"progress-t22-partial-sec")=="progress-"


def test_an_unrecordable_control_key_is_refused_at_the_creation_fact():
    raw=backend._meta().as_meta();raw["key"]="_scratch"
    with pytest.raises(lifecycle.LifecycleInputError):
        lifecycle.DecisionMeta.from_envelope({"meta":raw})
    raw["key"]="t22-redactor-fix"
    assert lifecycle.DecisionMeta.from_envelope({"meta":raw}).task_key is not None

