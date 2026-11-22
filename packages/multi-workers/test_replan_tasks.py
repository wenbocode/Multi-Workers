"""Per-run offline recovery, real lifecycle reader/receipts and both producer identities."""
import copy
import hashlib
import json
import os
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from uuid import uuid4

import pytest

import decision
import decision_lifecycle
import decision_wire
import mw_common
import replan_tasks as rp
from autopilot import conductor, dispatch, timeline as timeline_mod


def put(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def card(name, criterion="AC-001"):
    return (f"type: coding\ntimeout: 8\n\n## 上下文\n.agenticdoc/goal.md:1\n## 要求\n{criterion} {name}\n"
            f"## 交付格式\nresult.json\n## 写入允许面\n- src/{name}.py\n## 写入禁止面\n其它\n"
            "## 验收命令\npython -m unittest\n## 改动历史\nfirst\n")


@pytest.fixture
def fixture(tmp_path):
    project = tmp_path.resolve()
    key = project / ".agenticdoc" / "demo"
    put(key.parent / "target.yml", "active: single\n")
    put(key.parent / "_index.parallel", "| demo | active | EXECUTE | host:1 | | | now |\n")
    put(key / "tasks/base.md", card("original", "AC-001 AC-002"))
    folder = key / "workers" / "old"
    put(folder / "task.md", "type: coding\ncard_path: tasks/base.md\ntimeout: 1\n\n## 要求\nold\n")
    run = {"run_id": "old@2026-11-17T00:00:00Z", "task_key": "old", "owner_key": "demo", "status": "failed",
           "started_at": "2026-11-17T00:00:00Z", "ended_at": "2026-11-17T00:01:00Z"}
    put(folder / "run.json", json.dumps(run))
    put(folder / "trace.log", "[TIMEOUT] 2026-11-17T00:01:00Z wall: budget 60s exceeded\n")
    row = {"task_key": "old", "status": "failed", "task_path": str(folder / "task.md"), "cli": "pi",
           "provider": "timi", "dispatched_at": run["started_at"], "updated_at": run["ended_at"], "model": "", "origin": "manual"}
    mw_common.upsert_worker_row(mw_common.workers_path(project), row)
    return project, key, folder, row


def tool(project, operation, **args):
    return rp.execute(project, dict({"key": "demo", "claim": "host:1", "operation": operation}, **args))


def unit(name, ac, parents=()):
    return {"id": name, "markdown": card(name, ac), "covers": [ac], "depends_on": list(parents), "resources": [],
            "reuse": "existing failing case", "first_check": "run the named case", "expected": "record the exit code"}


def prepare(project, plan=None):
    inspected = tool(project, "inspect", task="old")
    args = {k: inspected[k] for k in ("issue", "snapshot")}
    plan = plan or {"action": "split", "reason": "separate independently verifiable results",
                    "units": [unit("one", "AC-001"), unit("two", "AC-002", ["one"])]}
    return args, tool(project, "preview", **args, plan=plan)


def answer(project, prepared, choice="split", task="old"):
    logical = str(uuid4())
    ref = "dp-pm-steer:" + logical
    base = {"scope": "production", "schema_version": 1, "project_id": decision_wire.project_id_for(project),
            "key": "demo", "task_key": task, "origin": "decision-lifecycle", "logical_id": logical, "decision_id": ref}
    p = decision_wire.production_lifecycle_sink(project)
    p.parent.mkdir(parents=True, exist_ok=True)
    meta = decision_lifecycle.DecisionMeta("demo", logical, initiator_role="pm", task_key=task)
    cfg, error = decision.DecisionConfig.from_project(project)
    assert not error
    store = decision_lifecycle.LifecycleStore.production(project, redact=decision.known_secret_redactor(cfg))
    assert decision_lifecycle.record_start(store, meta, decision_id=ref).recorded
    with p.open("a", encoding="utf-8") as out:
        out.write(json.dumps({**base, "kind": "request", "dp": "dp-pm-steer", "choice": choice,
                              "basis_id": prepared["basis_id"], "business_decisions": 1, "available": True}) + "\n")
    return ref


def test_offline_recovery_parallel_apply_and_dispatch(fixture):
    project, key, folder, row = fixture
    rp.collect_terminal(project, row, "failed")
    rp.collect_terminal(project, row, "failed")
    assert len(rp.records(key)) == 1
    assert rp.admission(project, "demo", "renamed", "tasks/base.md").startswith("replan-required:")
    args, prepared = prepare(project)
    assert prepared["initial_batch"] == ["one"] and prepared["waiting"]["two"] == ["one"]
    run = lambda: tool(project, "apply", **args, version=prepared["version"], decision_id=ref)
    ref = answer(project, prepared, choice="direct-exec")
    with pytest.raises(ValueError, match="no matching"):
        run()
    ref = answer(project, prepared)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert all(r["state"] == "applied" for r in pool.map(lambda _: run(), range(2)))
    assert rp.body(folder / "run.json") and len(list((key / "tasks").glob("*.md"))) == 3
    events = decision_wire.read_events(decision_wire.production_lifecycle_sink(project)).events
    assert [e["lifecycle"] for e in events if e.get("decision_id") == ref and e.get("kind") == "lifecycle"] == ["executed", "settled"]
    def send(stem):
        return dispatch.dispatch(project, "demo", stem, "phase-writer", "check", loop="execute", attempt=1)
    assert "dependency-pending" in send("two").reason
    first = send("one")
    assert first.ok and first.row_verified and "timeout: 8" in rp.body(first.task_md)
    assert "already-dispatched" in rp.admission(project, "demo", "manual-one", "tasks/one.md")
    mw_common.update_status(project, first.task_key, "done")
    put(first.task_md.with_name("run.json"), json.dumps({"status": "done"}))
    assert send("two").ok


def deadline_plan(fixture, claim="host:1", matter="stage", deadline=None):
    project, key, folder, _ = fixture
    put(key.parent / "_index.parallel", f"| demo | active | EXECUTE | {claim} | | | now |\n")
    run = json.loads(rp.body(folder / "run.json"))
    run["stop_kind"] = "worker-deadline"
    put(folder / "run.json", json.dumps(run))
    (folder / "trace.log").unlink()
    put(folder / "report.md", "AC-001 PASS")
    progress = {
        "run_id": run["run_id"],
        "milestone": {"at": "2026-11-17T00:00:50Z", "current": "finishing", "remaining": "AC-002",
                      "completed": [{"acceptance": "AC-001", "evidence": ".agenticdoc/demo/workers/old/report.md"}],
                      "blocker": "", "next": "Verify remaining acceptance"},
        "activity": {"source": "tool_update", "at": "2026-11-17T00:00:59Z", "tools": []},
    }
    put(folder / "run-progress.json", json.dumps(progress))
    inspected = tool(project, "inspect", task="old", claim=claim)
    assert inspected["facts"]["stop_kind"] == "worker-deadline"
    assert inspected["facts"]["run_id"] == run["run_id"]
    assert inspected["progress"] == progress
    assert "output.md" not in inspected["evidence_refs"]
    assert "report.md" in inspected["evidence_refs"]
    recovery = unit("recover", "AC-001 AC-002")
    recovery["covers"] = ["AC-001", "AC-002"]
    deadline = deadline or (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(
        timespec="milliseconds").replace("+00:00", "Z")
    recovery["markdown"] = (f"parent_worker_run: {run['run_id']}\n" + recovery["markdown"] +
                            "\n## 事项预算事实\n"
                            "- `budget_ref`: `tasks/recover.md#事项预算事实` + SHA\n"
                            "- `matter_ref`: `demo/recover`\n"
                            f"- `parent_matter_ref`: `{matter}`\n"
                            f"- `deadline`: `{deadline}`\n"
                            "- `max_steps`: 2\n"
                            "- `no_progress_limit`: 2\n"
                            "- `remaining_cost`: 2（1 cost unit ≡ 1 tool call）\n"
                            "- `steps_consumed`: 0\n"
                            "- `cost_consumed`: 0\n"
                            "- `no_progress_count`: 0\n"
                            "- `source_refs`: 卡 SHA、`run.json`、`_index.parallel`\n")
    args = {k: inspected[k] for k in ("issue", "snapshot")}
    prepared = tool(project, "preview", **args, claim=claim,
                    plan={"action": "narrow", "reason": "Finish remaining verification from report.md",
                          "units": [recovery]})
    decision_ref = answer(project, prepared, choice="narrow")
    tool(project, "apply", **args, version=prepared["version"], decision_id=decision_ref, claim=claim)
    pin = dispatch.card_digest(key / "tasks/recover.md")
    return run["run_id"], pin


def deadline_grant(fixture, child, parent, pin):
    project, key, _, _ = fixture
    card_ref = "tasks/recover.md"
    approval = rp.deadline_successor(project, "demo", child, card_ref, pin, parent)
    deadline = (datetime.now(timezone.utc) + timedelta(minutes=5)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
    stage_path = key / "tasks/stage.md"
    put(stage_path, "# Stage")
    stage_pin = dispatch.card_digest(stage_path)
    channel_id = hashlib.sha256(os.path.normcase(str(project)).encode()).hexdigest()
    channel = project / ".mw-pm-channel" / channel_id
    binding = {"id": "event", "key": "demo", "claim": "host:1", "binding": "window"}
    grant_hash = "verified-stage"
    request = channel / "demo" / "window" / "event.request.json"
    receipt = request.with_name("event.receipt.json")
    put(request, json.dumps({**binding, "stage": {"deadline": deadline, "max_steps": 2, "remaining_cost": 2,
                                                  "project_ref": channel_id, "key": "demo", "card_path": "tasks/stage.md",
                                                  "card_sha256": stage_pin, "write_face": ["src/recover.py"]},
                             "duty": {"shift": "test", "until": 9_999_999_999_999, "stopHash": "missing"}}))
    put(receipt, json.dumps({**binding, "state": "started", "session": "session-a", "stage_digest": grant_hash}))
    session = project / "session.jsonl"
    data = {"unit": "stage", "kind": "event", "key": "demo", "claim_id": "host:1", "source_pin": stage_pin,
            "event": {"kind": "reserve-child",
                      "request": {"reservation_id": f'deadline:["demo","{pin}"]',
                                  "steps": 2, "cost": 2, "deadline": deadline}}}
    put(session, "\n".join(map(json.dumps, [{"type": "session", "id": "session-a"},
                                           {"type": "custom", "customType": "mw-runtime-budget-v1", "data": data}])) + "\n")
    file = key.parent / "_runtime" / "fixed-child-budgets" / "demo" / f"deadline-{pin}.json"
    grant = {"approval": approval, "task": child, "card": card_ref, "pin": pin, "steps": 2, "cost": 2, "deadline": deadline,
             "authority": {"channel": str(channel), "request": request.relative_to(channel).as_posix(),
                           "request_sha256": hashlib.sha256(request.read_bytes()).hexdigest(),
                           "receipt": receipt.relative_to(channel).as_posix(), "session": str(session),
                           "session_id": "session-a", "event_id": "event", "grant_digest": grant_hash,
                           "unit": "stage", "stage_card": "tasks/stage.md", "stage_pin": stage_pin}}
    put(file, json.dumps(grant))
    return file, receipt, session


@pytest.mark.parametrize("cancel_before_recovery", [False, True])
def test_deadline_successor_enqueues_once_and_recovers_the_same_reservation(fixture, monkeypatch, cancel_before_recovery):
    project, key, folder, _ = fixture
    monkeypatch.setattr(rp.Path, "home", lambda: project)
    parent, pin = deadline_plan(fixture)
    before = (folder / "run.json").read_bytes()
    def send(_=None):
        return dispatch.dispatch(project, "demo", "recover", "phase-writer", "check", loop="execute", attempt=1)
    assert "allocation is missing" in send().reason
    child = dispatch.task_key_for("demo", "recover")
    file, _, session = deadline_grant(fixture, child, parent, pin)
    original_budget = session.read_bytes()
    # Fail after the envelope is durable and before the worker row is published.
    with patch.object(mw_common, "upsert_worker_row", side_effect=OSError("interrupted")):
        interrupted = send()
    assert interrupted.reason.startswith("queue-write-failed")
    envelope = rp.body(interrupted.task_md)
    assert mw_common.read_task_header_scalar(envelope, "deadline_successor") == "yes"
    assert mw_common.read_task_header_scalar(envelope, "fixed_child_steps") == "2"
    assert dispatch.dispatch_parent_refusal(project, "demo", child, envelope, launching=True) is None
    timeline = timeline_mod.Timeline(timeline_mod.timeline_path(project))
    state = conductor.ConductorState(timeline, conductor.goal_mtime_ns(project))
    if cancel_before_recovery:
        put(folder / "run.json", json.dumps({**json.loads(before), "aborted": True}))
        conductor.reconcile_orphans(project, state)
        assert "parent-cancel" in dispatch.dispatch_parent_refusal(project, "demo", child, envelope, launching=True)
        assert [r["task_key"] for r in mw_common.parse_workers_file(mw_common.workers_path(project))] == ["old"]
        assert session.read_bytes() == original_budget
        return
    conductor.reconcile_orphans(project, state)
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert not any(result.ok for result in pool.map(send, range(2)))
    conductor.reconcile_orphans(project, state)
    assert [r["task_key"] for r in mw_common.parse_workers_file(mw_common.workers_path(project))].count(child) == 1
    assert file.is_file() and session.read_bytes() == original_budget
    assert (folder / "run.json").read_bytes() == before


@pytest.mark.parametrize("change,reason", [
    ("cancel", "parent-cancel"), ("revoked", "PM stage revoked"), ("duty-stop", "user-stop"),
    ("wrong-task", "allocation binding mismatch"), ("missed-reservation", "reservation is missing"),
    ("edited-card", "pinned dispatch card"), ("expired", "expired"), ("budget", "revoked or exhausted"),
    ("claim", "another claim"), ("wrong-scope", "another project"), ("source-change", "requires an applied replan"),
    ("user-cancelled", "user-stop"), ("envelope-scope", "differs from its frozen card"),
    ("missing-receipt", "decision receipt is missing"),
])
def test_deadline_successor_refusal_preserves_the_queue(fixture, change, reason, monkeypatch):
    project, key, folder, _ = fixture
    monkeypatch.setattr(rp.Path, "home", lambda: project)
    parent, pin = deadline_plan(fixture)
    child = dispatch.task_key_for("demo", "recover")
    file, receipt, session = deadline_grant(fixture, child, parent, pin)
    card_data = dispatch.dispatch_card(project, "demo", "recover")
    envelope = dispatch.render_task_md("phase-writer", "check", loop="execute", attempt=1, card=card_data)
    grant = json.loads(rp.body(file))
    if change == "cancel":
        put(folder / "run.json", json.dumps({**json.loads(rp.body(folder / "run.json")), "aborted": True}))
    elif change == "revoked":
        put(receipt, json.dumps({**json.loads(rp.body(receipt)), "state": "cancelled"}))
    elif change == "duty-stop":
        put(key / "duty" / "test" / "STOP", "stopped")
    elif change == "wrong-task":
        grant["task"] = "some-other-task"
    elif change == "missed-reservation":
        put(session, rp.body(session).splitlines()[0] + "\n")
    elif change == "edited-card":
        card_path = key / "tasks/recover.md"
        put(card_path, rp.body(card_path) + "changed")
    elif change == "expired":
        grant["deadline"] = "2026-01-01T00:00:00.000Z"
    elif change == "budget":
        grant["cost"] = 3
    elif change == "claim":
        put(key.parent / "_index.parallel", "| demo | active | EXECUTE | host:2 | | | now |\n")
    elif change == "wrong-scope":
        grant["authority"]["channel"] = str(project / ".mw-pm-channel" / ("a" * 64))
    elif change == "source-change":
        put(folder / "run-progress.json", json.dumps({"run_id": parent, "milestone": {"remaining": "changed"}}))
    elif change == "user-cancelled":
        put(file.with_suffix(".json.cancelled"), "stopped")
    elif change == "envelope-scope":
        envelope = envelope.replace("write_face: src/recover.py", "write_face: src/another.py")
    elif change == "missing-receipt":
        sink = decision_wire.production_lifecycle_sink(project)
        retained = [line for line in rp.body(sink).splitlines()
                    if json.loads(line).get("lifecycle") != "settled"]
        put(sink, "\n".join(retained) + "\n")
    put(file, json.dumps(grant))
    assert reason in dispatch.dispatch_parent_refusal(project, "demo", child, envelope, allocation={})
    assert [r["task_key"] for r in mw_common.parse_workers_file(mw_common.workers_path(project))] == ["old"]


def test_conflict_missing_ac_cycle_stale_claim_and_snapshot(fixture):
    project, key, _, _ = fixture
    args, prepared = prepare(project)
    plan = {"action": "split", "reason": "example", "units": [unit("a", "AC-001"), unit("b", "AC-002")]}
    assert tool(project, "preview", **args, plan=plan)["initial_batch"] == ["a", "b"]
    for problem in ("shared resource", "shared file", "cycle", "lost ac"):
        bad = copy.deepcopy(plan)
        a, b = bad["units"]
        if problem == "shared resource":
            a["resources"] = b["resources"] = ["shared-editor"]
        elif problem == "shared file":
            b["markdown"] = b["markdown"].replace("src/b.py", "src/a.py")
        elif problem == "cycle":
            a["depends_on"], b["depends_on"] = ["b"], ["a"]
        else:
            b["covers"] = ["AC-001"]
        with pytest.raises(ValueError):
            tool(project, "preview", **args, plan=bad)
    with pytest.raises(ValueError, match="own"):
        tool(project, "apply", **args, claim="foreign", version=prepared["version"])
    put(key / "tasks/base.md", card("updated"))
    with pytest.raises(ValueError, match="source changed"):
        tool(project, "apply", **args, version=prepared["version"])


def test_interrupted_publish_is_inadmissible_and_resumable(fixture):
    project, key, _, _ = fixture
    args, prepared = prepare(project)
    ref = answer(project, prepared)
    publish = rp.publish_new
    def interrupt(path, markdown):
        if path.name == "two.md":
            raise OSError("simulated interruption")
        publish(path, markdown)
    with patch.object(rp, "publish_new", interrupt), pytest.raises(OSError, match="interruption"):
        tool(project, "apply", **args, version=prepared["version"], decision_id=ref)
    assert (key / "tasks/one.md").is_file()
    assert rp.admission(project, "demo", "manual-one", "tasks/one.md") == "replan-plan-not-published"
    assert tool(project, "apply", **args, version=prepared["version"], decision_id=ref)["state"] == "applied"


@pytest.mark.parametrize(("status", "line", "expected"), [
    ("failed", "[TIMEOUT] 2026-11-17T00:00:59Z idle: no activity", "idle-timeout"),
    ("failed", "[TIMEOUT] 2026-11-16T00:00:59Z wall: from an older run", "failed"),
    ("failed", "[TOOL] 2026-11-17T00:00:59Z [TIMEOUT] wall: fixture", "failed"),
    ("done", "[TIMEOUT] 2026-11-17T00:00:59Z wall: stale", "done"),
])
def test_only_current_watchdog_failure_triggers(fixture, status, line, expected):
    project, key, folder, row = fixture
    put(folder / "trace.log", line)
    rp.collect_terminal(project, row, status)
    assert rp.run_facts(key, "old", status)["category"] == expected
    assert bool(rp.records(key)) == (expected == "idle-timeout")


def test_model_fallback_and_new_attempt_after_inspection(fixture):
    project, key, folder, row = fixture
    run = json.loads(rp.body(folder / "run.json"))
    put(folder / "run.json", json.dumps({**run, "model_exhausted": True, "exit": 3}))
    rp.collect_terminal(project, row, "failed")
    assert not rp.records(key)
    assert rp.admission(project, "demo", "next", "tasks/base.md").startswith("replan-required:")
    assert tool(project, "inspect", task="old")["facts"]["category"] == "model-unavailable"
    assert rp.admission(project, "demo", "next", "tasks/base.md") is None
    assert rp.admission(project, "demo", "old", "tasks/base.md").startswith("replan-required:")


def test_schedule_independent_work_preserves_timeout(fixture):
    project, key, _, _ = fixture
    put(key / "tasks/other.md", card("other"))
    args, scheduled = prepare(project, {"reason": "editor blocked", "action": "schedule",
                                         "ready_existing": ["other"], "units": []})
    assert scheduled["initial_batch"] == ["other"]
    assert tool(project, "apply", **args, version=scheduled["version"])["state"] == "applied"
    assert tool(project, "inspect")["issues"][0]["needs_attention"]
    assert rp.admission(project, "demo", "again", "tasks/base.md").startswith("replan-required:")
    assert rp.admission(project, "demo", "independent", "tasks/other.md") is None


@pytest.mark.parametrize("action", ["direct-exec", "escalate"])
def test_takeover_and_escalation_need_actual_action(fixture, action):
    project, _, _, _ = fixture
    args, proposal = prepare(project, {"reason": "PM intervention", "action": action, "units": []})
    ref = answer(project, proposal, choice=action)
    apply_args = {**args, "version": proposal["version"], "decision_id": ref, "action_evidence": "actual-action"}
    with pytest.raises(ValueError, match="executed decision_receipt"):
        tool(project, "apply", **apply_args)
    cfg, _ = decision.DecisionConfig.from_project(project)
    store = decision_lifecycle.LifecycleStore.production(project, redact=decision.known_secret_redactor(cfg))
    meta = decision_lifecycle.DecisionMeta("demo", ref.split(":")[1], initiator_role="pm", task_key="old")
    assert decision_lifecycle.record_executed(store, meta, action=action, dp="dp-pm-steer", decision_id=ref,
                                              event_id="actual-action").recorded
    assert tool(project, "apply", **apply_args)["state"] == "applied"
    events = decision_wire.read_events(decision_wire.production_lifecycle_sink(project)).events
    assert [e.get("outcome") for e in events if e.get("lifecycle") == "settled"] == [
        "pending" if action == "escalate" else "ok"]


@pytest.mark.parametrize(("one", "repair"), [("one", "repair-one"), ("One", "Repair")])
def test_replanning_a_predecessor_preserves_its_dependents(fixture, one, repair):
    project, _, _, _ = fixture
    args, prepared = prepare(project, {"action": "split", "reason": "independent checks",
        "units": [unit(one, "AC-001"), unit("two", "AC-002", [one])]})
    tool(project, "apply", **args, version=prepared["version"], decision_id=answer(project, prepared))
    first = dispatch.dispatch(project, "demo", one, "phase-writer", "check", loop="execute", attempt=1)
    assert first.ok
    mw_common.update_status(project, first.task_key, "failed")
    put(first.task_md.with_name("run.json"), json.dumps({"status": "failed"}))
    inspected = tool(project, "inspect", task=one)
    args = {key: inspected[key] for key in ("issue", "snapshot")}
    prepared = tool(project, "preview", **args, plan={"action": "narrow", "reason": "isolate first failing check",
                                                       "units": [unit(repair, "AC-001")]})
    ref = answer(project, prepared, choice="narrow", task=first.task_key)
    tool(project, "apply", **args, version=prepared["version"], decision_id=ref)
    repaired = dispatch.dispatch(project, "demo", repair, "phase-writer", "check", loop="execute", attempt=1)
    assert repaired.ok
    assert "dependency-pending" in rp.admission(project, "demo", "next", "tasks/two.md")
    mw_common.update_status(project, repaired.task_key, "done")
    put(repaired.task_md.with_name("run.json"), json.dumps({"status": "done"}))
    assert rp.admission(project, "demo", "next", "tasks/two.md") is None


def test_reviewed_model_failure_on_successor_can_retry(fixture):
    project, _, _, _ = fixture
    args, prepared = prepare(project)
    tool(project, "apply", **args, version=prepared["version"], decision_id=answer(project, prepared))
    first = dispatch.dispatch(project, "demo", "one", "phase-writer", "check", loop="execute", attempt=1)
    assert first.ok
    mw_common.update_status(project, first.task_key, "failed")
    put(first.task_md.with_name("run.json"), json.dumps({"status": "failed", "task_key": first.task_key,
        "run_id": "model-run", "started_at": "2026-11-17T00:00:00Z", "ended_at": "2026-11-17T00:01:00Z",
        "model_exhausted": True, "exit": 3}))
    assert rp.admission(project, "demo", "new", "tasks/one.md").startswith("replan-required:")
    assert tool(project, "inspect", task=first.task_key)["facts"]["category"] == "model-unavailable"
    assert rp.admission(project, "demo", "new", "tasks/one.md") is None
    assert rp.admission(project, "demo", first.task_key, "tasks/one.md").startswith("replan-required:")
    mw_common.update_status(project, first.task_key, "running")
    assert "already-dispatched" in rp.admission(project, "demo", "new", "tasks/one.md")


@pytest.mark.parametrize("change", [
    "none", "previewed", "escalate", "no receipt", "wrong receipt", "wrong basis",
    "missing settlement", "empty evidence", "remaining card", "missing coverage",
    "evidence drift", "source drift", "parent card drift",
])
def test_evidence_only_takeover_resolves_transitive_dispatch_dependency(fixture, change):
    project, key, _, _ = fixture
    args, split = prepare(project)
    tool(project, "apply", **args, version=split["version"], decision_id=answer(project, split))

    def send(stem):
        return dispatch.dispatch(project, "demo", stem, "phase-writer", "check", loop="execute", attempt=1)

    def stop(stem, status):
        result = send(stem)
        assert result.ok
        mw_common.update_status(project, result.task_key, status)
        put(result.task_md.with_name("run.json"), json.dumps({"status": status, "task_key": result.task_key}))
        return tool(project, "inspect", task=result.task_key), result.task_md.with_name("run.json")

    first, first_run = stop("one", "needs-clarification")
    args = {field: first[field] for field in ("issue", "snapshot")}
    review_unit = unit("review", "AC-001")
    if change == "missing coverage":
        review_unit["covers"].append("AC-002")
    narrow = tool(project, "preview", **args, plan={"action": "narrow", "reason": "require independent review",
        "units": [review_unit]})
    tool(project, "apply", **args, version=narrow["version"],
         decision_id=answer(project, narrow, choice="narrow", task=first["facts"]["task"]))

    review, review_run = stop("review", "failed")
    blocked = send("two")
    assert not blocked.ok and blocked.reason == "replan-dependency-pending:one"
    args = {field: review[field] for field in ("issue", "snapshot")}
    evidence = key / "evidence/accepted.md"
    put(evidence, "AC-001 PASS · independent review accepted\n")
    action = "escalate" if change == "escalate" else "direct-exec"
    retained = {"AC-001": "evidence/accepted.md"}
    if change == "empty evidence":
        retained = {}
    elif change == "remaining card":
        put(key / "tasks/remaining.md", card("remaining"))
        retained = {"AC-001": "tasks/remaining.md"}
    proposal = tool(project, "preview", **args, plan={"action": action, "reason": "record review outcome",
        "units": [], "retained": retained})
    task = review["facts"]["task"]
    ref = answer(project, proposal, choice=action, task=task)
    cfg, error = decision.DecisionConfig.from_project(project)
    assert not error
    store = decision_lifecycle.LifecycleStore.production(project, redact=decision.known_secret_redactor(cfg))
    meta = decision_lifecycle.DecisionMeta("demo", ref.split(":")[1], initiator_role="pm", task_key=task)
    assert decision_lifecycle.record_executed(store, meta, action=action, dp="dp-pm-steer", decision_id=ref,
                                              event_id="review-accepted").recorded
    if change != "previewed":
        tool(project, "apply", **args, version=proposal["version"], decision_id=ref,
             action_evidence="review-accepted")

    record_path = key / "evidence/replan" / (review["issue"] + ".json")
    record = json.loads(rp.body(record_path))
    if change in {"no receipt", "wrong receipt"}:
        if change == "no receipt":
            record.pop("action_evidence")
        else:
            record["action_evidence"] = "unrelated-action"
        rp.save(record_path, record)
    elif change == "wrong basis":
        sink = decision_wire.production_lifecycle_sink(project)
        put(sink, rp.body(sink).replace(proposal["basis_id"], "replan-wrong-basis"))
    elif change == "missing settlement":
        sink = decision_wire.production_lifecycle_sink(project)
        put(sink, "".join(line + "\n" for line in rp.body(sink).splitlines()
                          if not (json.loads(line).get("decision_id") == ref
                                  and json.loads(line).get("lifecycle") == "settled")))
    elif change == "evidence drift":
        put(evidence, "AC-001 PASS · different evidence\n")
    elif change == "source drift":
        put(review_run.with_name("report.md"), "Different report\n")
    elif change == "parent card drift":
        path = key / "tasks/review.md"
        put(path, rp.body(path) + "\nNew text\n")

    terminal_before = [p.read_bytes() for p in (first_run, review_run)]
    result = send("two")
    assert [p.read_bytes() for p in (first_run, review_run)] == terminal_before
    statuses = {r["task_key"]: r["status"] for r in rp.worker_rows(project, "demo")}
    assert statuses[first_run.parent.name] == "needs-clarification"
    assert statuses[review_run.parent.name] == "failed"
    if change == "none":
        assert result.ok and result.row_verified
    else:
        assert not result.ok and result.reason == "replan-dependency-pending:one"


def test_takeover_of_unstarted_card_waits_for_its_predecessor(fixture):
    project, key, _, _ = fixture
    args, split = prepare(project, {"action": "split", "reason": "three ordered checks", "units": [
        unit("one", "AC-001"), unit("middle", "AC-002", ["one"]), unit("last", "AC-002", ["middle"])]})
    tool(project, "apply", **args, version=split["version"], decision_id=answer(project, split))
    current = tool(project, "inspect", task="middle")
    args = {field: current[field] for field in ("issue", "snapshot")}
    put(key / "evidence/accepted.md", "AC-002 PASS · PM verification\n")
    proposal = tool(project, "preview", **args, plan={"action": "direct-exec", "reason": "verified locally",
        "units": [], "retained": {"AC-002": "evidence/accepted.md"}})
    ref = answer(project, proposal, choice="direct-exec", task=None)
    cfg, error = decision.DecisionConfig.from_project(project)
    assert not error
    store = decision_lifecycle.LifecycleStore.production(project, redact=decision.known_secret_redactor(cfg))
    meta = decision_lifecycle.DecisionMeta("demo", ref.split(":")[1], initiator_role="pm")
    assert decision_lifecycle.record_executed(store, meta, action="direct-exec", dp="dp-pm-steer",
                                              decision_id=ref, event_id="middle-accepted").recorded
    tool(project, "apply", **args, version=proposal["version"], decision_id=ref, action_evidence="middle-accepted")
    assert rp.admission(project, "demo", "new", "tasks/last.md") == "replan-dependency-pending:middle"
    first = dispatch.dispatch(project, "demo", "one", "phase-writer", "check", loop="execute", attempt=1)
    assert first.ok
    mw_common.update_status(project, first.task_key, "done")
    put(first.task_md.with_name("run.json"), json.dumps({"status": "done"}))
    assert rp.admission(project, "demo", "new", "tasks/last.md") is None


def test_windows_crlf_plan_publishes_dispatchable_cards(fixture):
    project, _, _, _ = fixture
    units = [unit("one", "AC-001"), unit("two", "AC-002")]
    for item in units:
        item["markdown"] = item["markdown"].replace("\n", "\r\n")
    args, prepared = prepare(project, {"action": "split", "reason": "Windows input", "units": units})
    tool(project, "apply", **args, version=prepared["version"], decision_id=answer(project, prepared))
    assert rp.admission(project, "demo", "new", "tasks/one.md") is None


@pytest.mark.skipif(rp.os.name != "nt", reason="Windows filesystem identity")
def test_windows_case_variation_cannot_bypass_source_or_successor(fixture):
    project, _, _, _ = fixture
    args, prepared = prepare(project)
    assert rp.admission(project, "demo", "new", "tasks/BASE.md").startswith("replan-required:")
    tool(project, "apply", **args, version=prepared["version"], decision_id=answer(project, prepared))
    assert "dependency-pending" in rp.admission(project, "demo", "new", "tasks/TWO.md")
    first = dispatch.dispatch(project, "demo", "one", "phase-writer", "check", loop="execute", attempt=1)
    assert first.ok
    assert "already-dispatched" in rp.admission(project, "demo", "new", "tasks/ONE.md")


def test_inventory_is_bounded_and_all_sections_remain_pageable(fixture):
    project, key, _, row = fixture
    for i in range(75):
        stem = f"history-{i:03}"
        put(key / f"tasks/{stem}.md", card(stem))
        source = {"task": stem, "category": "wall-timeout"}
        rp.save(key / f"evidence/replan/{stem}.json", {
            "id": stem, "state": "applied" if i % 2 else "open", "source": source,
            "version": stem, "plan": {"action": "split", "units": [unit(stem, "AC-001")]}})
        mw_common.upsert_worker_row(mw_common.workers_path(project), {
            **row, "task_key": stem, "task_path": str(key / "workers" / stem / "task.md"), "status": "done"})
    first = tool(project, "inspect")
    assert set(first) == {"issues", "counts", "page", "plan_path"}
    assert len(first["issues"]) == 20
    assert all(item["needs_attention"] for item in first["issues"])
    assert first["counts"] == {"issues": 76, "cards": 76, "workers": 76, "applied_plans": 37,
                                "needs_attention": 39}
    assert len(json.dumps(first)) < 10000
    for section in ("issues", "cards", "workers", "applied_plans"):
        offset, values = 0, []
        while offset is not None:
            page = tool(project, "inspect", section=section, offset=offset, limit=17)
            assert len(page[section]) <= 17
            assert page["page"]["total"] == first["counts"][section]
            values.extend(page[section])
            offset = page["page"]["next_offset"]
        assert len(values) == first["counts"][section]
        assert len({json.dumps(item, sort_keys=True) for item in values}) == len(values)
        empty = tool(project, "inspect", section=section, offset=1000)
        assert empty[section] == [] and empty["page"]["next_offset"] is None


@pytest.mark.parametrize("args", [
    {"limit": 0}, {"limit": 51}, {"limit": -1}, {"limit": True}, {"limit": 1.5}, {"limit": "20"},
    {"offset": -1}, {"offset": False}, {"offset": 0.5}, {"offset": None}, {"section": "all"},
])
def test_invalid_inventory_bounds_are_refused(fixture, args):
    project, _, _, _ = fixture
    with pytest.raises(ValueError):
        tool(project, "inspect", **args)


def test_task_output_is_bounded_but_preview_checks_every_live_worker(fixture):
    project, key, _, row = fixture
    for i in range(60):
        stem = f"live-{i:02}"
        folder = key / "workers" / stem
        face = dispatch.render_write_face_line(["src/one.py" if i == 59 else f"src/{stem}.py"])
        put(folder / "task.md", f"type: coding\ncard_path: tasks/{stem}.md\n{face}\n")
        mw_common.upsert_worker_row(mw_common.workers_path(project), {
            **row, "task_key": stem, "task_path": str(folder / "task.md"), "status": "running"})
    current = tool(project, "inspect", task="base")
    assert set(current) == {"issue", "snapshot", "state", "facts", "acceptance", "coverage", "evidence_refs"}
    assert current["facts"] == {"task": "old", "status": "failed", "category": "wall-timeout",
                                "run_id": "old@2026-11-17T00:00:00Z"}
    assert current["evidence_refs"]["card"] == ".agenticdoc/demo/tasks/base.md"
    assert current["evidence_refs"]["task.md"] == ".agenticdoc/demo/workers/old/task.md"
    assert "report.md" not in current["evidence_refs"]
    assert current["acceptance"] == ["AC-001", "AC-002"]
    verdict = tool(project, "preview", issue=current["issue"], snapshot=current["snapshot"], plan={
        "action": "split", "reason": "isolate results", "units": [unit("one", "AC-001"), unit("two", "AC-002")]})
    assert "live:live-59" in verdict["waiting"]["one"]
    assert "one" not in verdict["initial_batch"]
    assert "two" in verdict["initial_batch"]


@pytest.mark.parametrize("artifact", ["report.md", "output.md"])
def test_evidence_reference_preserves_full_snapshot_validation(fixture, artifact):
    project, key, folder, _ = fixture
    long_text = "evidence-" * 1000
    put(folder / artifact, long_text)
    current = tool(project, "inspect", task="old")
    assert long_text[:100] not in json.dumps(current)
    assert rp.body(project / current["evidence_refs"][artifact]) == long_text
    args, prepared = prepare(project)
    put(folder / artifact, long_text + "changed after the old excerpt boundary")
    with pytest.raises(ValueError, match="source changed"):
        tool(project, "apply", **args, version=prepared["version"])


def write_closure(key):
    put(key / "plan.md", "## 闭环覆盖\n| AC-001 | `T-base` | VC-001 |\n"
        "| FLOW-001 | `T-base` | VC-001 |\n\n## Later\n| FLOW-003 | base | VC-999 |\n")
    put(key / "design.md", "### 必要功能路径\n| FLOW-001 | command | result | VC-001, VC-002 |\n")


@pytest.mark.parametrize("missing", ["AC-002", "FLOW-001", "VC-001", "VC-002"])
def test_replan_requires_each_source_obligation(fixture, missing):
    project, key, *_ = fixture
    write_closure(key)
    current = tool(project, "inspect", task="old")
    assert current["coverage"] == ["AC-001", "AC-002", "FLOW-001", "VC-001", "VC-002"]
    child = unit("child", "AC-001")
    child["covers"] = [item for item in current["coverage"] if item != missing]
    with pytest.raises(ValueError, match=missing):
        tool(project, "preview", issue=current["issue"], snapshot=current["snapshot"],
             plan={"action": "narrow", "reason": "Focused remaining work", "units": [child]})


def test_replan_binds_retained_proof_and_refuses_unrelated_owners(fixture):
    project, key, *_ = fixture
    write_closure(key)
    current = tool(project, "inspect", task="old")
    args = {field: current[field] for field in ("issue", "snapshot")}
    child = unit("child", "AC-001")
    child["covers"] = ["AC-001", "AC-002", "VC-001"]
    put(key / "tasks/other.md", card("other"))
    plan = {"action": "narrow", "reason": "reuse a working path", "units": [child],
            "retained": {"FLOW-001": "tasks/other.md", "VC-002": "evidence/flow.md"}}
    with pytest.raises(ValueError, match="FLOW-001"):
        tool(project, "preview", **args, plan=plan)
    put(key / "tasks/other.md", card("other", "FLOW-001"))
    with pytest.raises(ValueError, match="VC-002"):
        tool(project, "preview", **args, plan=plan)
    evidence = key / "evidence/flow.md"
    put(evidence, "VC-002 PASS · ran the command and verified stdout\n")
    verdict = tool(project, "preview", **args, plan=plan)
    ref = answer(project, verdict, choice="narrow")
    put(evidence, "VC-002 PASS · observed a different run\n")
    with pytest.raises(ValueError, match="stale plan version"):
        tool(project, "apply", **args, version=verdict["version"], decision_id=ref)
    verdict = tool(project, "preview", **args, plan=plan)
    applied = tool(project, "apply", **args, version=verdict["version"],
                   decision_id=answer(project, verdict, choice="narrow"))
    assert applied["state"] == "applied"
    assert rp.admission(project, "demo", "child", "tasks/child.md") is None


def test_manual_steer_requires_current_run_and_publishes_only_once(fixture):
    project, key, folder, _ = fixture
    write_closure(key)
    before = rp.body(folder / "task.md")
    mw_common.update_status(project, "old", "running")
    run = json.loads(rp.body(folder / "run.json"))
    put(folder / "run.json", json.dumps({**run, "status": "running", "ended_at": None}))
    inspected = tool(project, "inspect", task="old")
    args = {"task": "old", "snapshot": inspected["snapshot"], "verification": "call_7",
            "remaining": "Complete both required cases", "stop": "Extra benchmarking"}
    with pytest.raises(ValueError, match="own"):
        tool(project, "trim_steer", **args, claim="foreign")
    with pytest.raises(ValueError, match="changed"):
        tool(project, "trim_steer", **dict(args, snapshot="stale"))
    assert tool(project, "trim_steer", **args)["state"] == "queued"
    target = folder / "steer-dp2.md"
    message = rp.body(target)
    assert message.startswith("[dp2-narrow-request]\n")
    assert "FLOW-001, VC-001, VC-002" in message and "call_7" in message
    assert rp.body(folder / "task.md") == before
    with pytest.raises(ValueError, match="already has a steer"):
        tool(project, "trim_steer", **args)
    assert rp.body(target) == message
    mw_common.update_status(project, "old", "done")
    with pytest.raises(ValueError, match="no longer running"):
        tool(project, "trim_steer", **args)


def test_trim_inventory_only_surfaces_active_workers(fixture):
    project, _, _, row = fixture
    assert tool(project, "trim_inventory")["workers"] == []
    mw_common.upsert_worker_row(mw_common.workers_path(project), {**row, "task_key": "live", "status": "running"})
    result = tool(project, "trim_inventory")
    assert result["workers"] == [{"task": "live", "status": "running"}]
    assert result["active_workers"] == 1
    assert result["total_workers"] == 2
