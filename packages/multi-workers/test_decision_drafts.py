"""Exercise durable repair and frozen material at the real CLI boundary."""

import copy
import json
from io import BytesIO

import pytest

import decision
import decision_backends
import decision_points
from autopilot import conductor, dispatch, gates, timeline
import test_dp_consolidation_cli as cli
from test_dp_consolidation_cli import _all_entries_enabled
from test_prepared_cli_source_snapshot import isolated_credentials


def invoke(project, monkeypatch, dp, envelope, **fields):
    request = {"meta": envelope["meta"], "trigger": "review", **fields}
    if "draft_ref" not in request:
        request["book"] = {k: v for k, v in envelope.items() if k != "meta"}
    rc, out, err = cli._invoke("draft", project, monkeypatch, dp=dp, stdin=json.dumps(request))
    assert rc == 0, (out, err)
    return json.loads(out)


@pytest.mark.parametrize("dp", decision_points.ACTIVE_DP_IDS)
def test_window_preview_uses_prepared_client(tmp_path, monkeypatch, isolated_credentials, dp):
    env = cli._envelope(dp, "preview-matrix")
    action, args = "run", {"dp": dp}
    if dp == "dp-QG":
        env["material"]["review_findings"] = "The ordering assertion is missing from the evidence."
        env["preparation"]["model_context"] = {"reasons": {"F1": "The ordering assertion is missing."}}
        env["preparation"]["basis_catalog"] = [
            {"id": choice, "text": text, "material_refs": [field], "applies_to": [choice]}
            for choice, field, text in (
                ("fix", "review_findings", "Repair the missing ordering assertion."),
                ("pass", "review_requirements", "If every check has independent evidence."),
                ("reopen", "review_requirements", "If the acceptance standard is inconsistent."),
            )
        ]
        env["preparation"]["basis_catalog"][0]["finding_ids"] = ["F1"]
    if dp == "dp-sign-key":
        tmp_path, _ = cli._sign_project(tmp_path)
        env = cli._sign_envelope("preview-matrix")
        action, args = "sign", cli._sign_args(tmp_path, json=True)
    def answer(state, questions, cfg):
        choice = {"dp-QG": "fixA", "dp-sign-key": "continueA"}.get(dp, questions["decision_selection"]["choices"][0])
        return decision.BackendOutcome(available=True, reason=None, retryable=False, latency_ms=1, detail="",
                                       answers={"decision_selection": {"value": choice, "confidence": 0.99}})
    backend = decision.FakeBackend([answer])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: backend)
    (tmp_path / "evidence.txt").write_text("Current gate evidence.\n", encoding="utf-8")
    ready = invoke(tmp_path, monkeypatch, dp, env)
    assert ready["status"] == "ready", ready
    assert ready["transport"] == "not-sent"
    before = cli._lifecycle_events(tmp_path)
    bad = copy.deepcopy(env)
    bad["preparation"]["basis_catalog"] = []
    bad["meta"]["logical_id"] = "invalid-input"
    negative = invoke(tmp_path, monkeypatch, dp, bad)
    assert negative["status"] == "needs-repair" and negative["issues"]
    assert cli._lifecycle_events(tmp_path) == before == []
    assert not backend.calls
    _, failure, _ = cli._invoke(action, tmp_path, monkeypatch, stdin=json.dumps(bad), stdin_flag=True, **args)
    assert not json.loads(failure).get("available") and not backend.calls
    rc, sent, err = cli._invoke(action, tmp_path, monkeypatch, stdin=json.dumps(env), stdin_flag=True,
                                prepared_snapshot=ready["snapshot"], **args)
    result = json.loads(sent)
    if dp == "dp-gate-approve":
        assert result["reason"] == "disabled" and not backend.calls
    else:
        assert len(backend.calls) == 1, (result, err)
        assert rc == 0 and (result.get("available") or result.get("conclusion")), (result, err)


def test_only_the_bound_matter_can_resume_and_repair(tmp_path, monkeypatch, isolated_credentials):
    dp = "dp-pm-steer"
    env = cli._envelope(dp, "initial")
    env["preparation"]["prepared_at"] = "invalid"
    (tmp_path / "note.md").write_text("One line.\n", encoding="utf-8")
    env["evidence_refs"] = [{"field": "material.task_goal", "path": "note.md", "lines": {"start": 1, "end": 3}}]
    draft = invoke(tmp_path, monkeypatch, dp, env)
    line = next(edit for issue in draft["issues"] for edit in issue.get("repairs", [])
                if edit["field"].endswith("lines.end"))
    field = next(edit for issue in draft["issues"] for edit in issue.get("repairs", [])
                 if edit["field"].endswith("prepared_at"))
    foreign = {"meta": env["meta"], "trigger": "another-matter", "draft_ref": draft["draft_ref"]}
    rc, out, _ = cli._invoke("draft", tmp_path, monkeypatch, dp=dp, stdin=json.dumps(foreign))
    assert rc and json.loads(out)["status"] == "unavailable" and "book" not in json.loads(out)
    ready = invoke(tmp_path, monkeypatch, dp, env, draft_ref=draft["draft_ref"],
                   changes=[{"repair_id": field["repair_id"], "value": cli.PREPARED_AT},
                            {"repair_id": line["repair_id"], "value": 1}])
    assert ready["status"] == "ready"
    assert ready["book"]["material"] == env["material"] and "prepared_at" not in ready["book"]["material"]


def test_merge_conflict_drift_and_one_actual_post(tmp_path, monkeypatch, isolated_credentials):
    dp = "dp-pm-steer"
    env = cli._envelope(dp, "original-submission")
    file = tmp_path / "design.md"
    file.write_text("First recorded fact.\nSecond recorded fact.\n", encoding="utf-8")
    env["material"]["task_goal"] = "Explain XYZ using the verified design."
    env["evidence_refs"] = [{"field": "material.task_goal", "path": "design.md", "lines": {"start": 1, "end": 3}}]
    original = copy.deepcopy(env)
    rejected = invoke(tmp_path, monkeypatch, dp, env)
    assert rejected["status"] == "needs-repair", rejected
    handles = {r["field"]: r["repair_id"] for issue in rejected["issues"] for r in issue.get("repairs", [])}
    end = next(val for field, val in handles.items() if field.endswith("lines.end"))
    term = handles["preparation.model_context.terminology.XYZ"]

    def repair(handle, value):
        return invoke(tmp_path, monkeypatch, dp, env, draft_ref=rejected["draft_ref"],
                      changes=[{"repair_id": handle, "value": value}])

    assert repair(term, "A project measurement.")["status"] == "needs-repair"
    fixed = repair(end, 2)
    assert fixed["status"] == "ready", fixed
    assert repair(end, 2)["snapshot"] == fixed["snapshot"]
    assert repair(end, 1)["status"] == "review"
    env.update(fixed["book"])
    original["evidence_refs"][0]["lines"]["end"] = 2
    original["preparation"].setdefault("model_context", {})["terminology"] = {"XYZ": "A project measurement."}
    assert env == original

    calls = []

    def answer(request, *, timeout):
        body = json.loads(request.data)
        calls.append(body)
        choice = next(iter(body["questions"]["decision_selection"]["criteria"]))
        reply = BytesIO(json.dumps({"id": "test-reply", "model": "jev-latest", "answers": {
            "decision_selection": {"type": "choice", "choice": choice, "confidence": 0.95}}}).encode())
        reply.status = 200
        reply.headers = {"Content-Type": "application/json"}
        return reply

    monkeypatch.setattr(decision_backends.urllib.request, "urlopen", answer)
    file.write_text("Changed source.\nSecond recorded fact.\n", encoding="utf-8")
    changed = invoke(tmp_path, monkeypatch, dp, env, draft_ref=fixed["draft_ref"])
    assert changed["status"] == "review"
    rc, out, _ = cli._invoke("run", tmp_path, monkeypatch, dp=dp, stdin_flag=True,
                             prepared_snapshot=fixed["snapshot"], stdin=json.dumps(env))
    assert not json.loads(out)["available"] and not calls
    env["meta"]["logical_id"] = "current-source"
    rc, out, err = cli._invoke("run", tmp_path, monkeypatch, dp=dp, stdin_flag=True,
                               prepared_snapshot=changed["snapshot"], stdin=json.dumps(env))
    assert rc == 0 and json.loads(out)["available"], (out, err)
    assert len(calls) == 1
    assert calls[0]["state"]["terminology"]["XYZ"] == "A project measurement."
    assert "Changed source." in calls[0]["state"]["evidence_sources"][0]["text"]


def test_repair_loop_counts_distinct_failed_revisions_and_resumes_on_new_evidence(
    tmp_path, monkeypatch, isolated_credentials,
):
    dp = "dp-pm-steer"
    env = cli._envelope(dp, "bounded-repair")
    for name in ("first.md", "second.md"):
        (tmp_path / name).write_text("One line.\nTwo lines.\n", encoding="utf-8")
    env["evidence_refs"] = [
        {"field": field, "path": name, "lines": {"start": 1, "end": 3}}
        for field, name in (("material.task_goal", "first.md"),
                            ("material.task_requirements", "second.md"))
    ]
    initial = invoke(tmp_path, monkeypatch, dp, env, repair_loop=True)
    assert initial["consecutive_no_progress"] == 0
    assert initial["next"]["action"] == "repair-material" and initial["next"]["owner"] == "pm"
    ref = initial["draft_ref"]

    def repair(result, index, end):
        field = f"evidence_refs[{index}].lines.end"
        handle = next(item["repair_id"] for issue in result["issues"]
                      for item in issue.get("repairs", []) if item["field"] == field)
        return invoke(tmp_path, monkeypatch, dp, env, draft_ref=ref, repair_loop=True,
                      changes=[{"repair_id": handle, "value": end}])

    first = repair(initial, 0, 4)
    second = repair(first, 0, 5)
    repeated = repair(second, 0, 4)
    assert repeated["replayed"] and repeated["consecutive_no_progress"] == 2
    assert repeated["draft_ref"] == ref
    progress = repair(repeated, 0, 2)
    third = repair(progress, 1, 4)
    fourth = repair(third, 1, 5)
    paused = repair(fourth, 1, 6)
    assert [reply["consecutive_no_progress"] for reply in
            (initial, first, second, progress, third, fourth, paused)] == [0, 1, 2, 0, 1, 2, 3]
    assert paused["status"] == "paused" and paused["next"]["action"] == "review-material-recovery"
    assert len(paused["attempts"]) == 3 and all(attempt["changes"] for attempt in paused["attempts"])
    assert not cli._lifecycle_events(tmp_path)

    rewritten = copy.deepcopy(env)
    rewritten["evidence_refs"][0]["lines"]["end"] = 2
    rewritten["evidence_refs"][1]["lines"]["end"] = 2
    blocked = invoke(tmp_path, monkeypatch, dp, rewritten, repair_loop=True, trigger="new-trigger")
    assert blocked["status"] == "paused" and blocked["draft_ref"] == ref
    (tmp_path / "first.md").write_text("An unrelated change to the cleared reference.\nTwo lines.\n", encoding="utf-8")
    blocked = invoke(tmp_path, monkeypatch, dp, env, repair_loop=True, draft_ref=ref)
    assert blocked["status"] == "paused"
    (tmp_path / "second.md").write_text("".join(f"Line {i}.\n" for i in range(1, 7)), encoding="utf-8")
    resumed = invoke(tmp_path, monkeypatch, dp, env, repair_loop=True, draft_ref=ref)
    assert resumed["status"] == "review" and resumed["draft_ref"] == ref
    ready = invoke(tmp_path, monkeypatch, dp, env, repair_loop=True, draft_ref=ref)
    assert ready["status"] == "ready" and ready["consecutive_no_progress"] == 0 and "next" not in ready


def test_pause_is_scoped_and_accepts_a_current_human_recovery_approval(tmp_path, monkeypatch, isolated_credentials):
    dp = "dp-pm-steer"
    primary = cli._envelope(dp, "repair-primary", task_key="task-primary")
    cli._write_worker_runtime(tmp_path, owner="key-1", task="task-primary")
    (tmp_path / ".agenticdoc" / "target.yml").write_text("active: single\n", encoding="utf-8")
    (tmp_path / "first.md").write_text("One line.\n", encoding="utf-8")
    primary["evidence_refs"] = [
        {"field": "material.task_goal", "path": "first.md", "lines": {"start": 1, "end": 2}},
    ]
    result = invoke(tmp_path, monkeypatch, dp, primary, repair_loop=True)
    ref = result["draft_ref"]
    for end in (3, 4, 5):
        handle = next(item["repair_id"] for item in result["next"]["repairs"] if item["field"].endswith(".end"))
        result = invoke(tmp_path, monkeypatch, dp, primary, draft_ref=ref, repair_loop=True,
                        changes=[{"repair_id": handle, "value": end}])
    assert result["status"] == "paused"
    launched = dispatch.dispatch(tmp_path, "key-1", "independent", "reviewer", "Independently review this file.",
                                 loop="l3:key-1", attempt=1, read_scope=("first.md",))
    assert launched.ok and launched.row_verified, launched
    independent = cli._envelope(dp, "send-independent", task_key=launched.task_key)

    def answer(state, questions, cfg):
        choice = questions["decision_selection"]["choices"][0]
        return decision.BackendOutcome(available=True, reason=None, retryable=False, latency_ms=1, detail="",
                                       answers={"decision_selection": {"value": choice, "confidence": 0.99}})

    backend = decision.FakeBackend([answer])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: backend)
    ready = invoke(tmp_path, monkeypatch, dp, independent, repair_loop=True)
    assert ready["status"] == "ready" and ref != ready["draft_ref"]
    _, result, _ = cli._invoke("run", tmp_path, monkeypatch, dp=dp, stdin_flag=True,
                               stdin=json.dumps(independent), prepared_snapshot=ready["snapshot"])
    assert json.loads(result)["available"] and len(backend.calls) == 1
    assert invoke(tmp_path, monkeypatch, dp, primary, draft_ref=ref, repair_loop=True)["status"] == "paused"

    gate = gates.create(conductor.gates_dir(tmp_path), "stalled", "Resume this specific repair.",
                        [f"decision-draft:{ref}"], key="key-1")
    controller = conductor.ConductorState(timeline.Timeline(timeline.timeline_path(tmp_path)), None)
    approval = conductor.answer_gate_confirmed(tmp_path, controller, gate.stem, "approve", answered_by="human")
    assert approval.ok, approval.error
    resumed = invoke(tmp_path, monkeypatch, dp, primary, draft_ref=ref, repair_loop=True, recovery_approval=gate.stem)
    assert resumed["status"] == "needs-repair" and resumed["consecutive_no_progress"] == 0


def test_a_durable_result_resolves_the_hold_and_replays_without_a_post(tmp_path, monkeypatch, isolated_credentials):
    dp = "dp-pm-steer"
    env = cli._envelope(dp, "original-action", task_key=None)
    selected = decision.BackendOutcome(available=True, reason=None, retryable=False, latency_ms=1, detail="",
                                       answers={"decision_selection": {"value": "narrowA", "confidence": 0.99}})
    backend = decision.FakeBackend([selected])
    monkeypatch.setattr(decision, "DEFAULT_BACKEND_FACTORY", lambda cfg: backend)
    argv = {"dp": dp, "stdin_flag": True, "stdin": json.dumps(env)}
    _, sent, _ = cli._invoke("run", tmp_path, monkeypatch, **argv)
    action_ref = json.loads(sent)["decision_id"]
    held = invoke(tmp_path, monkeypatch, dp, env, repair_loop=True, hold_action=action_ref)
    assert held["status"] == "effect-unknown" and held["next"]["action_ref"] == action_ref
    resumed = invoke(tmp_path, monkeypatch, dp, env, repair_loop=True, draft_ref=held["draft_ref"])
    assert resumed["status"] == "review" and resumed["next"]["action_ref"] == action_ref
    ready = invoke(tmp_path, monkeypatch, dp, env, repair_loop=True, draft_ref=held["draft_ref"])
    assert ready["recorded_action"] == action_ref
    _, existing, _ = cli._invoke("run", tmp_path, monkeypatch, **argv, prepared_snapshot=ready["snapshot"])
    assert json.loads(existing)["available"] and len(backend.calls) == 1


def test_existing_draft_and_repair_handle_continue_under_the_scoped_loop(tmp_path, monkeypatch, isolated_credentials):
    dp = "dp-pm-steer"
    env = cli._envelope(dp, "old-draft")
    env["preparation"]["prepared_at"] = "invalid"
    previous = invoke(tmp_path, monkeypatch, dp, env)
    field = next(item["repair_id"] for issue in previous["issues"] for item in issue.get("repairs", [])
                 if item["field"].endswith("prepared_at"))
    repaired = invoke(tmp_path, monkeypatch, dp, env, repair_loop=True, draft_ref=previous["draft_ref"],
                      changes=[{"repair_id": field, "value": cli.PREPARED_AT}])
    assert repaired["status"] == "ready" and repaired["draft_ref"] != previous["draft_ref"]
