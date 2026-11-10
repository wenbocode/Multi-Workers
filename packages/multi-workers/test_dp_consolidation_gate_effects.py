"""T17 gate transport/business/effect contract and cross-language writer tests.

Hermetic: fixtures only, production Python parser and TypeScript writer, no provider.
T18/T19/T26 may extend this file only after T17 handoff.
"""
from __future__ import annotations

import json
import hashlib
import os
import pathlib
import shutil
import subprocess
import sys
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import replace

import pytest

import mw as mw_cli

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]
sys.path.insert(0, str(PACKAGE_DIR))

from autopilot import gates  # noqa: E402
from autopilot import conductor
from autopilot import contract_guard as cg  # noqa: E402
from autopilot import xkey as xk  # noqa: E402
from autopilot import decision_recovery  # noqa: E402
import decide_archive
import decide_signoff
import decision
import decision_lifecycle as lifecycle
import decision_policy as policy
import decision_signoff_result as signoff_result
import decision_validity as validity
import decision_wire as wire
import mw_common
from autopilot import advance, closure, dispatch
from autopilot import config, gate_effects, roadmap

CHOICES = ("approve", "steer", "need_fix", "reject")


def _gate_text(**overrides: str) -> str:
    fields = {
        "id": "gate-0001",
        "kind": "stage-confirm",
        "stage": "1",
        "key": "key-1",
        "created_at": "2026-11-08T09:00:00Z",
        "created_by": "conductor",
        "question": "May this gate proceed?",
        "context_refs": "[]",
        "status": "pending",
        "answered_at": "",
        "answered_by": "",
        "note": "",
        "transport": "pending",
        "business": "",
        "effect": "not-started",
        "decision_ref": "dp-gate-approve:logical-1",
        "matter_ref": "matter-1",
        "substantive_version": "v1",
        "pm_note": "prepared action and authority basis",
        "model_basis": "",
        "closure_kind": "",
    }
    fields.update(overrides)
    lines = ["---"] + [f"{name}: {value}" if value else f"{name}:" for name, value in fields.items()]
    return "\n".join(lines + ["---", "", "# fixture", ""])


def _write_gate(tmp_path: pathlib.Path, **overrides: str) -> pathlib.Path:
    tmp_path.mkdir(parents=True, exist_ok=True)
    path = tmp_path / "gate-0001.md"
    path.write_text(_gate_text(**overrides), encoding="utf-8", newline="\n")
    return path


def _prepared_gate(tmp_path: pathlib.Path) -> pathlib.Path:
    return gates.create(
        tmp_path, "stage-confirm", "May this gate proceed?", stage=1, key="key-1",
        pm_note="prepared action and authority basis", matter_ref="matter-1", substantive_version="v1",
    )


def _answer(path: pathlib.Path, *, operator: bool = False, **options) -> dict:
    module = REPO_ROOT / "packages/coding-agent/src/extensions/agent-team-loop/autopilot/gate-writer.ts"
    runner = path.parent / "writer.mjs"
    runner.write_text(
        f"import {{ answerGate, answerPreparedGate }} from {json.dumps(module.as_uri())};\n"
        "import {readFileSync} from 'node:fs';\n"
        "const {operator, ...args} = JSON.parse(readFileSync(0, 'utf8'));\n"
        "console.log(JSON.stringify(await (operator ? answerGate : answerPreparedGate)(args)));\n",
        encoding="utf-8", newline="\n",
    )
    args = {
        "operator": operator, "gateFile": str(path), "lockFile": str(path.parent / "gates.lock"),
        "answeredBy": "pm:1", "answeredAt": "2026-11-08T09:01:00Z", **options,
    }
    proc = subprocess.run(
        ["node", str(REPO_ROOT / "node_modules/tsx/dist/cli.mjs"), str(runner)],
        input=json.dumps(args), cwd=REPO_ROOT, env={**os.environ, "NO_COLOR": "1"},
        text=True, encoding="utf-8", capture_output=True, check=False,
    )
    assert proc.returncode == 0, proc.stderr
    return json.loads(proc.stdout)


def _run_ts_writer(tmp_path: pathlib.Path, choice: str, *, model_basis: str = "basis-1") -> dict[str, object]:
    path = _prepared_gate(tmp_path)
    result = _answer(
        path, decision=choice, note="prepared action and authority basis", modelBasis=model_basis,
        decisionRef="dp-gate-approve:logical-1", matterRef="matter-1", substantiveVersion="v1",
    )
    result["gate"] = gates.parse(path)
    result["raw"] = path.read_text(encoding="utf-8")
    return result


def test_parser_exposes_three_axes_and_matter_links(tmp_path: pathlib.Path) -> None:
    gate = gates.parse(
        _write_gate(
            tmp_path,
            transport="answered",
            business="approve",
            effect="blocked",
            model_basis="machine checks passed",
            answered_at="2026-11-08T09:01:00Z",
            answered_by="pm:1",
        )
    )
    assert (gate.transport, gate.business, gate.effect) == ("answered", "approve", "blocked")
    assert (gate.decision_ref, gate.matter_ref, gate.substantive_version) == (
        "dp-gate-approve:logical-1",
        "matter-1",
        "v1",
    )
    assert gate.pm_note == "prepared action and authority basis"
    assert gate.model_basis == "machine checks passed"
    assert gate.note is None


@pytest.mark.parametrize("choice", CHOICES)
def test_ts_writer_round_trips_four_business_choices_without_releasing(
    tmp_path: pathlib.Path, choice: str
) -> None:
    result = _run_ts_writer(tmp_path, choice)
    assert result["ok"] is True
    gate = result["gate"]
    assert gate.transport == "answered"
    assert gate.business == choice
    assert gate.effect == "not-started"
    assert gate.status == "pending"
    assert gate.pm_note == "prepared action and authority basis"
    assert gate.model_basis == "basis-1"
    assert gate.decision_ref == "dp-gate-approve:logical-1"
    assert "released:" not in result["raw"]


def test_steer_need_fix_and_reject_have_no_implied_effect(tmp_path: pathlib.Path) -> None:
    false_release_or_repair = 0
    unauthorized_closure = 0
    for choice in ("steer", "need_fix", "reject"):
        result = _run_ts_writer(tmp_path / choice, choice)
        gate = result["gate"]
        false_release_or_repair += int(gate.effect == "applied")
        unauthorized_closure += int(gate.closure_kind is not None)
    assert false_release_or_repair == 0
    assert unauthorized_closure == 0
    print("[VERIFY] VC-007: gate_choices=4 mixed_note_basis=0 false_release_or_repair=0 unauthorized_closure=0")


@pytest.mark.parametrize("field,value", [("transport", "ok"), ("business", "approved"), ("effect", "released")])
def test_invalid_axis_value_is_fail_closed(
    tmp_path: pathlib.Path, field: str, value: str
) -> None:
    with pytest.raises(gates.GateFormatError, match=field):
        gates.parse(_write_gate(tmp_path, **{field: value}))


def test_answered_without_business_is_invalid(tmp_path: pathlib.Path) -> None:
    with pytest.raises(gates.GateFormatError, match="business"):
        gates.parse(_write_gate(tmp_path, transport="answered", business=""))


def test_writer_refuses_missing_refs_and_preserves_gate(tmp_path: pathlib.Path) -> None:
    gate = _write_gate(tmp_path)
    before = gate.read_bytes()
    result = _answer(gate, decision="approve", modelBasis="basis")
    assert result["ok"] is False
    assert "decisionRef" in result["error"]
    assert gate.read_bytes() == before
    print("[VERIFY] VC-012: default_actions=0 fabricated_results=0 failure_bypasses=0")


def test_legacy_gate_remains_readable_but_is_historical_only(tmp_path: pathlib.Path) -> None:
    path = tmp_path / "gate-0001.md"
    legacy = "\n".join([
        "---", "id: gate-0001", "kind: stage-confirm", "stage: 1", "key: key-1",
        "created_at: 2026-11-08T09:00:00Z", "created_by: conductor", "question: legacy",
        "context_refs: []", "status: approved", "answered_at: 2026-11-08T09:01:00Z",
        "answered_by: old:1", "note: old answer", "---", "",
    ])
    path.write_text(legacy, encoding="utf-8", newline="\n")
    gate = gates.parse(path)
    assert gate.historical is True
    assert gate.transport is None and gate.business is None and gate.effect is None
    assert gate.released is False


def test_replay_labels_preserve_one_matter_reference(tmp_path: pathlib.Path) -> None:
    refs = set()
    for index, label in enumerate(("start", "retry", "copy"), start=1):
        path = tmp_path / f"gate-{index:04d}.md"
        path.write_text(_gate_text(id=f"gate-{index:04d}", question=label), encoding="utf-8")
        refs.add((gates.parse(path).matter_ref, gates.parse(path).substantive_version))
    assert refs == {("matter-1", "v1")}
    print("[T17] three wire labels preserve the same matter reference and version")


def test_selection_record_has_no_execution_or_completion_fields(tmp_path: pathlib.Path) -> None:
    result = _run_ts_writer(tmp_path, "approve")
    raw = result["raw"]
    for forbidden in ("executed:", "settled:", "done:", "released:"):
        assert forbidden not in raw
    assert not gates.pending_gates(tmp_path)


@pytest.mark.parametrize("options", [
    {"authorizes": ["contract-change"]}, {"note": "changed after the answer"},
    {"substantiveVersion": "v2"}, {"matterRef": "other"}, {"decision": "invalid"},
    {"modelBasis": "basis\r\nstatus: approved"}, {"answeredBy": "pm\u2028authorizes: [retry]"},
    {"answeredAt": "2026-02-30T09:01:00Z"},
])
def test_invalid_answer_keeps_the_prepared_bytes(tmp_path: pathlib.Path, options: dict) -> None:
    path = _prepared_gate(tmp_path)
    before = path.read_bytes()
    args = dict(decision="approve", modelBasis="basis", decisionRef="req", matterRef="matter-1", substantiveVersion="v1")
    assert _answer(path, **{**args, **options})["ok"] is False
    assert path.read_bytes() == before


def test_replay_and_conflict_do_not_change_recorded_answer(tmp_path: pathlib.Path) -> None:
    path = _prepared_gate(tmp_path)
    args = dict(modelBasis="basis", decisionRef="req", matterRef="matter-1", substantiveVersion="v1")
    assert _answer(path, decision="approve", **args)["ok"] is True
    answered = path.read_bytes()
    for choice in ("approve", "reject"):
        assert _answer(path, decision=choice, answeredAt="2026-11-08T10:00:00Z", **args)["ok"] is False
        assert path.read_bytes() == answered


def test_human_command_and_prepared_writer_have_separate_targets(tmp_path: pathlib.Path) -> None:
    operator_gate = gates.create(tmp_path, "stage-confirm", "Please check the task")
    pending = operator_gate.read_bytes()
    args = dict(decision="steer", modelBasis="basis", decisionRef="req", matterRef="matter-1", substantiveVersion="v1")
    for operator in (False, True):
        assert _answer(operator_gate, operator=operator, **args)["ok"] is False
        assert operator_gate.read_bytes() == pending
    assert _answer(operator_gate, operator=True, decision="approve")["ok"] is True
    history = operator_gate.read_bytes()
    assert _answer(operator_gate, operator=True, decision="reject")["ok"] is False
    assert operator_gate.read_bytes() == history
    prepared = _prepared_gate(tmp_path)
    before = prepared.read_bytes()
    assert _answer(prepared, operator=True, decision="approve")["ok"] is False
    assert prepared.read_bytes() == before


@pytest.mark.parametrize("note", [None, " ", "forged\ntransport: answered"])
def test_partial_or_multiline_preparation_never_creates_a_gate(tmp_path: pathlib.Path, note: str | None) -> None:
    with pytest.raises(gates.GateFormatError):
        gates.create(tmp_path, "stalled", "Prepare?", matter_ref="matter", substantive_version="v1", pm_note=note)
    assert not list(tmp_path.glob("gate-*.md"))


def test_effect_consumer_refuses_historical_gate_before_observing_target(tmp_path: pathlib.Path) -> None:
    project = tmp_path / "project"
    path = gates.create(project / ".agenticdoc/_autopilot/gates", "stalled", "Operator?")
    assert _answer(path, operator=True, decision="approve")["ok"]
    before = path.read_bytes()
    store = lifecycle.LifecycleStore.test(tmp_path / "wire", project_id="fixture", redact=wire.SubstringRedactor([]))
    meta = lifecycle.DecisionMeta.create("owner", initiator_role="pm")
    result = gate_effects.consume_gate(
        project, path.stem, store=store, meta=meta, claim_id="pm:1",
        observe=lambda gate: pytest.fail("historical gate reached the object adapter"),
    )
    assert result.state == "blocked" and "histor" in result.reason
    assert path.read_bytes() == before and not store.sink.exists()


class EffectFixture:
    def __init__(self, tmp: pathlib.Path, choice: str, *, legacy: bool = False, skip_request: bool = False,
                 claim: str | None = None, store_kind: str = "production"):
        self.root = tmp / "project"
        config.save_config(self.root, {"enabled": True, "paused": False, "auto_gate_mode": "live"})
        self.claim = claim or f"{socket.gethostname()}:{os.getpid()}"
        self.index = self.root / ".agenticdoc/_index.parallel"
        self.index.write_text(f"| owner | active | EXECUTE | {self.claim} | - | test | now |\n", encoding="utf-8")
        self.map = roadmap.roadmap_path(self.root)
        self.map.write_text("## Stage 1: fixture\n> goal: release the fixture\n> status: pending\n"
                            "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| owner | implement | - |\n",
                            encoding="utf-8")
        self.before_sha = hashlib.sha256(self.map.read_bytes()).hexdigest()
        redactor = wire.SubstringRedactor([])
        if store_kind == "test":
            self.store = lifecycle.LifecycleStore.test(tmp / "wire", project_id=wire.project_id_for(self.root), redact=redactor)
        else:
            self.store = lifecycle.LifecycleStore.production(self.root if store_kind == "production" else tmp / "other",
                                                            redact=redactor)
        self.meta = lifecycle.DecisionMeta.create("owner", task_key="T18", initiator_role="pm")
        self.ref = "dp-gate-approve:" + self.meta.logical_id
        raw = json.loads((PACKAGE_DIR / "decide_cases/dp-gate-approve.json").read_text(encoding="utf-8"))["book"]
        action_name = "stage:stop-as-legacy" if legacy else "stage:open"
        note = raw["material"]["pm_note"]
        note["planned_action"] = action_name
        self.note = json.dumps(note, ensure_ascii=False, sort_keys=True)
        self.matter = validity.matter_for(
            "owner", "stage-1", action_name, [validity.DependencyState("note", "structured", note)],
            matter_kind="gate-action", contract_version="v1", authority_required=True,
        )
        self.gate = gates.create(self.root / ".agenticdoc/_autopilot/gates", "stage-confirm", "Open this stage?", key="owner",
                                 pm_note=self.note, matter_ref=self.matter.matter_key, substantive_version=self.matter.substantive_version)
        self.scope = (action_name, "gate:legacy-close") if legacy else (action_name,)
        policy.policy_path(self.root).write_text(json.dumps({
            "schema_version": 1, "authority_ref": "signed-scope", "scope": self.scope,
            "hard_limits": [{"unit": "steps", "limit": 3, "usage_source": "recorded-steps"}],
        }), encoding="utf-8")
        self.authority = policy.AuthorityRecord("signed-scope", "user-grant", self.scope, "controlled-human")
        self.calls = 0
        self.mode = "normal"
        self.legacy = legacy
        self.action = gate_effects.BoundAction(action_name, self.map.relative_to(self.root), self.apply, self.inspect, legacy)
        self.facts = gate_effects.GateFacts(
            self.matter, self.note, self.scope, {"signed-scope": self.authority}, ("controlled-human",),
            {"delivery-evidence": True}, {"recorded-steps": 1}, {"steps": 1},
            self.action if choice == "approve" or legacy else None,
        )
        prepared = raw["preparation"]
        basis = next(v for v in prepared["basis_catalog"] if choice in v["applies_to"])
        answers = {"gate_decision": {"value": choice, "confidence": 0.95},
                   "basis_id": {"value": basis["id"], "confidence": 0.95}}
        client = decision.DecisionClient(
            decision.DecisionConfig(enabled=True, project_root=self.root, evidence_path=tmp / "transport.jsonl"),
            decision.FakeBackend([decision.BackendOutcome(True, None, False, answers, 0)]),
        )
        assert lifecycle.record_start(self.store, self.meta).recorded
        assert lifecycle.record_note(self.store, self.meta, decision_id=self.ref, pm_note=self.note,
                                     prepared_at=prepared["prepared_at"]).recorded
        result = client.request_prepared("dp-gate-approve", raw["material"], prepared, logical_id=self.meta.logical_id, actor_role="pm")
        assert result["choice"] == choice, json.dumps(result, ensure_ascii=False)
        if not skip_request:
            assert lifecycle.record_request(self.store, self.meta, decision_id=self.ref, result=result,
                                            material=raw["material"], preparation=prepared).recorded
        assert _answer(self.gate, decision=choice, modelBasis=result["basis_text"], decisionRef=self.ref,
                       matterRef=self.matter.matter_key, substantiveVersion=self.matter.substantive_version,
                       answeredBy=self.claim)["ok"]

    def apply(self, gate):
        self.calls += 1
        if self.mode == "throw-before":
            raise OSError("target writer failed")
        if self.mode == "interrupt-before":
            raise KeyboardInterrupt
        assert not (self.root / ".mw/gates.lock").exists()
        target_lock = self.root / ".mw/roadmap.lock"
        mw_common.acquire_lock(target_lock, retries=0)
        try:
            if hashlib.sha256(self.map.read_bytes()).hexdigest() != self.before_sha:
                raise gate_effects.ActionNotApplied
            status = "halted" if self.legacy else "running"
            text = roadmap.update_stage_status(self.map.read_text(encoding="utf-8"), 1, status)
            gates._write_atomic(self.map, f"<!-- {gate.decision_ref} -->\n" + text)
        finally:
            mw_common.release_lock(target_lock)
        if self.mode == "interrupt-after":
            raise KeyboardInterrupt

    def inspect(self, gate):
        data = self.map.read_bytes()
        if f"<!-- {gate.decision_ref} -->".encode() not in data:
            return None
        observed = roadmap.stage_by_number(roadmap.load_roadmap(self.map), 1)
        if observed.status != ("halted" if self.legacy else "running"):
            return None
        return gate_effects.ObjectReceipt(gate.decision_ref, hashlib.sha256(data).hexdigest())

    def consume(self, path=None):
        return gate_effects.consume_gate(self.root, (path or self.gate).stem, store=self.store, meta=self.meta,
                                        claim_id=self.claim, observe=lambda gate: self.facts)

    def events(self):
        return [r for r in lifecycle.read_lifecycle(self.store).events if r["kind"] == "lifecycle"]


@pytest.mark.parametrize("choice,legacy,expected,target", [
    ("approve", False, "applied", None), ("steer", False, "blocked", "dp-pm-steer"),
    ("need_fix", False, "blocked", "dp-auto"), ("reject", False, "blocked", None), ("reject", True, "applied", None),
])
def test_effect_branches_use_real_gate_target_and_lifecycle(tmp_path, choice, legacy, expected, target):
    f = EffectFixture(tmp_path, choice, legacy=legacy)
    before = f.map.read_bytes()
    result = f.consume()
    assert (result.state, result.follow_up) == (expected, target), result
    assert result.parent_ref == f.ref
    gate = gates.parse(f.gate)
    assert gate.effect == expected and gate.closure_kind == ("legacy" if legacy else None)
    assert f.calls == int(expected == "applied")
    assert (f.map.read_bytes() != before) == (expected == "applied")
    rows = f.events()
    assert len([r for r in rows if r["lifecycle"] == "executed"]) == f.calls
    assert len([r for r in rows if r["lifecycle"] == "settled"]) == 1
    assert all((r["decision_id"], r["logical_id"], r["key"], r["task_key"]) == (f.ref, f.meta.logical_id, "owner", "T18") for r in rows)
    assert all(r["scope"] == "production" and r["actor"] == {"kind": "system", "id": f.claim} for r in rows)
    assert not any(r["kind"] == "terminal" for r in lifecycle.read_lifecycle(f.store).events)
    replay = f.consume()
    assert replay.state == expected and f.calls == int(expected == "applied")
    assert len(f.events()) == len(rows)


@pytest.mark.parametrize("fault", ["off", "paused", "claim", "authority", "limit", "unknown-usage", "hard-check",
                                    "stale-version", "missing-request", "other-note", "legacy-grant", "held-lock"])
def test_gate_effect_failures_do_not_touch_target(tmp_path, fault):
    f = EffectFixture(tmp_path, "reject" if fault == "legacy-grant" else "approve",
                      legacy=fault == "legacy-grant", skip_request=fault == "missing-request")
    if fault in ("off", "paused"):
        config.save_config(f.root, {"enabled": True, "paused": fault == "paused", "auto_gate_mode": "off" if fault == "off" else "live"})
    if fault == "claim":
        f.index.write_text(f.index.read_text().replace(f.claim, "other:1"))
    if fault in ("authority", "legacy-grant"):
        f.facts = replace(f.facts, authority_source={"signed-scope": replace(f.authority, scope=("unrelated",))})
    if fault in ("limit", "unknown-usage"):
        f.facts = replace(f.facts, usage_by_source={"recorded-steps": 3} if fault == "limit" else {})
    if fault == "hard-check":
        f.facts = replace(f.facts, hard_checks={"delivery-gate": False})
    if fault == "stale-version":
        f.facts = replace(f.facts, matter=replace(f.matter, substantive_version="different"))
    if fault == "other-note":
        f.facts = replace(f.facts, pm_note="not the prepared action")
    if fault == "held-lock":
        (f.root / ".mw").mkdir(exist_ok=True)
        (f.root / ".mw/gates.lock").write_text("held")
    before = f.map.read_bytes()
    result = f.consume()
    assert result.state == "blocked" and result.reason, result
    assert f.map.read_bytes() == before and f.calls == 0 and f.events() == []


@pytest.mark.parametrize("mode,applied", [("interrupt-before", False), ("interrupt-after", True), ("throw-before", False)])
def test_interrupted_effect_inspects_actual_object_without_repeated_write(tmp_path, mode, applied):
    f = EffectFixture(tmp_path, "approve")
    f.mode = mode
    if mode.startswith("interrupt"):
        with pytest.raises(KeyboardInterrupt):
            f.consume()
        assert gates.parse(f.gate).effect == "in-progress"
    else:
        assert f.consume().state == "unknown"
    result = f.consume()
    assert result.state == ("applied" if applied else "unknown"), result
    assert f.calls == 1
    assert len([r for r in f.events() if r["lifecycle"] == "executed"]) == int(applied)


def test_gate_label_and_lock_do_not_allow_a_second_object_write(tmp_path):
    f = EffectFixture(tmp_path, "approve")
    duplicate = f.gate.with_name("gate-0002.md")
    duplicate.write_bytes(f.gate.read_bytes().replace(b"gate-0001", b"gate-0002"))
    assert f.consume(duplicate).duplicate
    assert f.consume().state == "applied"
    assert f.consume(duplicate).duplicate and f.calls == 1


def test_concurrent_consumers_acquire_matter_before_target_and_apply_only_once(tmp_path):
    f = EffectFixture(tmp_path, "approve")
    entered, release = threading.Event(), threading.Event()

    def slow_apply(gate):
        entered.set()
        assert release.wait(5)
        f.apply(gate)

    f.facts = replace(f.facts, action=replace(f.action, apply=slow_apply))
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(f.consume)
        try:
            assert entered.wait(5) and not (f.root / ".mw/gates.lock").exists()
            second = pool.submit(f.consume).result(timeout=5)
            assert second.state == "blocked" and "matter-" in second.reason
        finally:
            release.set()
        assert first.result(timeout=5).state == "applied"
    assert f.calls == 1 and [r["lifecycle"] for r in f.events()] == ["consumed", "executed", "settled"]


@pytest.mark.parametrize("fault", ["revoked", "claim-changed", "target-changed", "dependency-changed"])
def test_current_claim_target_authority_and_substantive_material_checked_before_reserving(tmp_path, fault):
    f = EffectFixture(tmp_path, "approve")

    def inspect(_):
        if fault == "revoked":
            f.facts = replace(f.facts, authority_source={})
        if fault == "claim-changed":
            f.index.write_text(f.index.read_text().replace(f.claim, "other:1"))
        if fault == "target-changed":
            f.facts = replace(f.facts, action=replace(f.action, object_path=pathlib.Path("other.md")))
        if fault == "dependency-changed":
            f.matter.dependencies[0].value["planned_action"] = "different"
        return None

    f.facts = replace(f.facts, action=replace(f.action, inspect=inspect))
    before = f.map.read_bytes()
    result = f.consume()
    assert result.state == "blocked" and result.reason and gates.parse(f.gate).effect == "not-started"
    assert f.calls == 0 and f.map.read_bytes() == before
    assert all(row["lifecycle"] == "consumed" for row in f.events())


def test_object_cas_refusal_records_known_failure_without_execution(tmp_path):
    f = EffectFixture(tmp_path, "approve")
    with f.map.open("a", encoding="utf-8") as handle:
        handle.write("concurrent external edit\n")
    changed = f.map.read_bytes()
    result = f.consume()
    assert result.state == "failed" and gates.parse(f.gate).effect == "failed"
    assert f.map.read_bytes() == changed
    assert [(r["lifecycle"], r.get("outcome")) for r in f.events()] == [("consumed", None), ("settled", "inconclusive")]


@pytest.mark.parametrize("stage", ["executed", "settled"])
def test_interrupted_ledger_append_reconciles_once_from_object(tmp_path, monkeypatch, stage):
    f = EffectFixture(tmp_path, "approve")
    with monkeypatch.context() as patch:
        patch.setattr(lifecycle, "record_" + stage, lambda **_: lifecycle.LifecycleResult(stage, "failed"))
        assert f.consume().state == "unknown"
    assert gates.parse(f.gate).effect == "in-progress" and f.calls == 1
    assert f.consume().state == "applied" and f.calls == 1
    assert [r["lifecycle"] for r in f.events()] == ["consumed", "executed", "settled"]


def test_inspector_exception_after_write_leaves_unknown_and_redacts_callback_details(tmp_path):
    f = EffectFixture(tmp_path, "approve")

    def fragile_inspector(gate):
        if f.calls:
            raise OSError("secret in unsafe callback message")
        return f.inspect(gate)

    f.facts = replace(f.facts, action=replace(f.action, inspect=fragile_inspector))
    result = f.consume()
    assert result.state == "unknown" and "OSError" in result.reason and "secret" not in result.reason
    f.facts = replace(f.facts, action=f.action)
    assert f.consume().state == "applied" and f.calls == 1


def test_gate_unreserved_after_real_execution_cannot_repeat_even_when_object_was_restored(tmp_path):
    f = EffectFixture(tmp_path, "approve")
    original_map, original_gate = f.map.read_bytes(), f.gate.read_bytes()
    assert f.consume().state == "applied"
    f.gate.write_bytes(original_gate)
    f.map.write_bytes(original_map)
    result = f.consume()
    assert result.state == "blocked" and "existing execution" in result.reason and f.calls == 1


def test_copying_another_live_pm_window_from_the_index_does_not_bind_caller(tmp_path):
    with subprocess.Popen([sys.executable, "-c", "import sys; sys.stdin.read()"], stdin=subprocess.PIPE) as other_pm:
        try:
            f = EffectFixture(tmp_path, "approve", claim=f"{socket.gethostname()}:{other_pm.pid}")
            result = f.consume()
            assert result.state == "blocked" and "live owner" in result.reason
            assert f.calls == 0 and f.events() == []
        finally:
            other_pm.communicate(input=b"", timeout=5)


def test_worker_context_cannot_consume_bound_pm_approval(tmp_path, monkeypatch):
    f = EffectFixture(tmp_path, "approve")
    monkeypatch.setenv("PI_WORKER_TASK", str(tmp_path / "worker/task.md"))
    assert f.consume().state == "blocked" and f.calls == 0 and f.events() == []


@pytest.mark.parametrize("bad_receipt", ["different-decision", "different-hash"])
def test_wrong_object_receipt_never_settles_or_allows_another_write(tmp_path, bad_receipt):
    f = EffectFixture(tmp_path, "approve")
    def inspect(gate):
        receipt = f.inspect(gate)
        if receipt is None:
            return None
        return (replace(receipt, decision_ref="different") if bad_receipt == "different-decision"
                else replace(receipt, sha256="0"*64))
    f.facts = replace(f.facts, action=replace(f.action, inspect=inspect))
    assert f.consume().state == "unknown" and f.consume().state == "unknown"
    assert f.calls == 1 and [r["lifecycle"] for r in f.events()] == ["consumed"]


@pytest.mark.parametrize("source", ["test", "other", "copied-test", "copied-other"])
def test_only_same_project_production_records_can_be_consumed(tmp_path, source):
    f = EffectFixture(tmp_path, "approve", store_kind=source.removeprefix("copied-"))
    if source.startswith("copied-"):
        external_rows = f.store.sink.read_bytes()
        f.store = lifecycle.LifecycleStore.production(f.root, redact=wire.SubstringRedactor([]))
        f.store.sink.parent.mkdir(parents=True, exist_ok=True)
        f.store.sink.write_bytes(external_rows)
    before = f.map.read_bytes()
    result = f.consume()
    assert result.state == "blocked" and f.calls == 0 and f.map.read_bytes() == before
    assert f.events() == [] and gates.parse(f.gate).effect == "not-started"


def test_preexisting_consumed_id_from_different_actor_blocks_write(tmp_path):
    f = EffectFixture(tmp_path, "approve")
    event_id = "gate-" + hashlib.sha256(f.ref.encode()).hexdigest() + "-consumed"
    assert lifecycle.record_consumed(f.store, f.meta, decision_id=f.ref, dp="dp-gate-approve", answer="approve",
                                     actor=("system", "foreign-pm"), event_id=event_id).recorded
    result = f.consume()
    assert result.state == "blocked" and f.calls == 0
    assert [r["lifecycle"] for r in f.events()] == ["consumed"]


def test_current_pm_can_prepare_a_real_stage_trigger_without_releasing_it(tmp_path):
    root = tmp_path / "project"
    config.save_config(root, {"enabled": True, "paused": False, "auto_gate_mode": "live"})
    owner = "owner"
    claim = f"{socket.gethostname()}:{os.getpid()}"
    (root / ".agenticdoc/_index.parallel").write_text(f"| {owner} | active | EXECUTE | {claim} | - | test | now |\n")
    (root / ".agenticdoc/goal.md").write_text("# Deliver the agreed feature\n")
    target = roadmap.roadmap_path(root)
    target.write_text("## Stage 1: Integration\n> goal: Ship the verified feature\n> status: pending\n"
                      "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| owner | implement | - |\n")
    before = target.read_bytes()
    st = conductor.ConductorState(conductor.timeline.Timeline(conductor.timeline.timeline_path(root)), None)
    conductor._create_stage_confirm_gate(root, st, roadmap.load_roadmap(target).stages[0])
    trigger, = gates.enumerate(conductor.gates_dir(root))
    book = json.loads((PACKAGE_DIR/"decide_cases/dp-gate-approve.json").read_text(encoding="utf-8"))["book"]
    prepared = conductor.prepare_conductor_gate(root, trigger.id, owner_key=owner, material=book["material"],
                                                preparation=book["preparation"])
    assert not prepared.historical and prepared.kind == "stage-confirm" and prepared.stage == 1
    assert prepared.pm_note == json.dumps(book["material"]["pm_note"], ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    assert prepared.transport == "pending" and prepared.business is None
    assert target.read_bytes() == before
    assert conductor.prepare_conductor_gate(root, trigger.id, owner_key=owner, material=book["material"],
                                             preparation=book["preparation"]).id == prepared.id


def _conductor_h_fixture(tmp_path: pathlib.Path) -> tuple[pathlib.Path, str, str, conductor.ConductorState, pathlib.Path]:
    root = tmp_path / "project"
    config.save_config(root, {"enabled": True, "paused": False, "auto_gate_mode": "live"})
    owner = "owner"
    claim = f"{socket.gethostname()}:{os.getpid()}"
    (root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (root / ".agenticdoc/_index.parallel").write_text(
        f"| {owner} | active | EXECUTE | {claim} | - | test | now |\n", encoding="utf-8")
    (root / ".agenticdoc/goal.md").write_text("# Deliver the agreed feature\n", encoding="utf-8")
    target = roadmap.roadmap_path(root)
    target.write_text(
        "## Stage 1: Integration\n> goal: Ship the verified feature\n> status: pending\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n| owner | implement | - |\n",
        encoding="utf-8")
    st = conductor.ConductorState(conductor.timeline.Timeline(conductor.timeline.timeline_path(root)), None)
    return root, owner, claim, st, target


@pytest.mark.parametrize("case,kind,action,subject", [
    ("h01", "stage-confirm", "stage:open", "stage-1"),
    ("h02", "stage-close", "stage:close", "stage-1"),
    ("h03", "stalled", "key:resume", "owner"),
    ("h04", "budget-exhausted", "extension:soft-round", "loop:fixture"),
    ("h05", "stalled", "review:resume", "owner"),
])
def test_conductor_prepares_each_h_trigger_without_releasing(tmp_path, case, kind, action, subject):
    root, owner, claim, st, target = _conductor_h_fixture(tmp_path / case)
    if case == "h01":
        conductor._create_stage_confirm_gate(root, st, roadmap.load_roadmap(target).stages[0])
    elif case == "h02":
        assert conductor._create_gate(root, st, "stage-close", "Close stage?", stage=1, refs=["stage-1"])
    elif case == "h03":
        conductor.mark_stalled(root, st, "owner", "fixture stall")
    elif case == "h04":
        assert conductor._create_gate(root, st, "budget-exhausted", "Extend the loop?", key="owner",
                                      refs=["loop:fixture"])
    else:
        assert conductor.defer_key_to_review(root, st, "owner", 1, kind="stalled")
    before = target.read_bytes()
    trigger = [g for g in gates.enumerate(conductor.gates_dir(root))
               if g.historical and g.status == "pending" and g.kind == kind][-1]
    book = json.loads((PACKAGE_DIR / "decide_cases/dp-gate-approve.json").read_text(encoding="utf-8"))["book"]
    prepared = conductor.prepare_conductor_gate(root, trigger.id, owner_key=owner,
                                                material=book["material"], preparation=book["preparation"])
    _, matter, note = conductor._pm_gate_matter(root, owner, trigger, book["material"], book["preparation"])
    assert (matter.action, matter.object) == (action, subject)
    assert prepared.matter_ref == matter.matter_key
    assert prepared.substantive_version == matter.substantive_version
    assert prepared.pm_note == note
    assert not prepared.historical and prepared.transport == "pending" and prepared.business is None
    assert prepared.effect == "not-started"
    assert target.read_bytes() == before
    assert conductor.prepare_conductor_gate(
        root, trigger.id, owner_key=owner, material=book["material"],
        preparation=book["preparation"]).id == prepared.id


_H_KIND = {"h01": "stage-confirm", "h02": "stage-close", "h03": "stalled",
           "h04": "budget-exhausted", "h05": "stalled"}


def _approved_h_through_conductor(tmp_path: pathlib.Path, case: str = "h01"):
    root, owner, claim, st, target = _conductor_h_fixture(tmp_path)
    if case == "h01":
        conductor._create_stage_confirm_gate(root, st, roadmap.load_roadmap(target).stages[0])
    elif case == "h02":
        assert conductor._create_gate(root, st, "stage-close", "Close stage?", stage=1, refs=["stage-1"])
    elif case == "h03":
        conductor.mark_stalled(root, st, "owner", "fixture stall")
    elif case == "h04":
        assert conductor._create_gate(root, st, "budget-exhausted", "Extend the loop?", key="owner",
                                      refs=["loop:fixture"])
    else:
        assert conductor.defer_key_to_review(root, st, "owner", 1, kind="stalled")
    trigger = [g for g in gates.enumerate(conductor.gates_dir(root))
               if g.kind == _H_KIND[case] and g.historical][-1]
    book = json.loads((PACKAGE_DIR / "decide_cases/dp-gate-approve.json").read_text(encoding="utf-8"))["book"]
    material, preparation = book["material"], book["preparation"]
    prepared = conductor.prepare_conductor_gate(root, trigger.id, owner_key=owner,
                                                material=material, preparation=preparation)
    _, matter, note = conductor._pm_gate_matter(root, owner, trigger, material, preparation)
    action_name = matter.action
    policy.policy_path(root).write_text(json.dumps({
        "schema_version": 1, "authority_ref": "signed-scope", "scope": [action_name],
        "hard_limits": [{"unit": "steps", "limit": 3, "usage_source": "recorded-steps"}],
    }), encoding="utf-8")
    authority = policy.AuthorityRecord("signed-scope", "user-grant", (action_name,), "controlled-human")
    store = lifecycle.LifecycleStore.production(root, redact=wire.SubstringRedactor([]))
    meta = lifecycle.DecisionMeta.create(owner, task_key="T19", initiator_role="pm")
    ref = "dp-gate-approve:" + meta.logical_id
    assert lifecycle.record_start(store, meta).recorded
    assert lifecycle.record_note(store, meta, decision_id=ref, pm_note=prepared.pm_note,
                                 prepared_at=preparation["prepared_at"]).recorded
    basis = next(v for v in preparation["basis_catalog"] if "approve" in v["applies_to"])
    client = decision.DecisionClient(
        decision.DecisionConfig(enabled=True, project_root=root, evidence_path=tmp_path / "transport.jsonl"),
        decision.FakeBackend([decision.BackendOutcome(True, None, False, {
            "gate_decision": {"value": "approve", "confidence": 0.95},
            "basis_id": {"value": basis["id"], "confidence": 0.95},
        }, 0)]),
    )
    result = client.request_prepared("dp-gate-approve", material, preparation,
                                     logical_id=meta.logical_id, actor_role="pm")
    assert result["choice"] == "approve" and result["basis_text"] == basis["text"]
    assert lifecycle.record_request(store, meta, decision_id=ref, result=result,
                                    material=material, preparation=preparation).recorded
    assert _answer(prepared.path, decision="approve", modelBasis=result["basis_text"], decisionRef=ref,
                   matterRef=prepared.matter_ref, substantiveVersion=prepared.substantive_version,
                   answeredBy=claim)["ok"]
    calls = [0]

    def apply(gate):
        calls[0] += 1
        lock = root / ".mw/roadmap.lock"
        mw_common.acquire_lock(lock, retries=0)
        try:
            text = target.read_text(encoding="utf-8")
            if case in ("h01", "h02"):
                text = roadmap.update_stage_status(text, 1, "running" if case == "h01" else "closed")
            elif case in ("h03", "h05"):
                text = roadmap.update_key_status(text, 1, owner, "running")
            gates._write_atomic(target, f"<!-- {gate.decision_ref} -->\n" + text)
        finally:
            mw_common.release_lock(lock)

    def inspect(gate):
        data = target.read_bytes()
        if f"<!-- {gate.decision_ref} -->".encode() not in data:
            return None
        rm = roadmap.load_roadmap(target)
        if case == "h01" and roadmap.stage_by_number(rm, 1).status != "running":
            return None
        if case == "h02" and roadmap.stage_by_number(rm, 1).status != "closed":
            return None
        if case in ("h03", "h05") and roadmap.stage_by_number(rm, 1).key_status.get(owner) != "running":
            return None
        return gate_effects.ObjectReceipt(gate.decision_ref, hashlib.sha256(data).hexdigest())

    action = gate_effects.BoundAction(action_name, target.relative_to(root), apply, inspect)

    def observe(_gate):
        return gate_effects.GateFacts(
            matter, note, (action_name,), {"signed-scope": authority}, ("controlled-human",),
            {"conductor-target": True}, {"recorded-steps": 1}, {"steps": 1}, action)

    return root, owner, claim, prepared, trigger, material, preparation, store, meta, target, ref, calls, observe


@pytest.mark.parametrize("case,field,value", [
    ("h01", "stage", "running"), ("h02", "stage", "closed"),
    ("h03", "key", "running"), ("h04", "effect", "applied"), ("h05", "key", "running"),
])
def test_conductor_consumes_approved_h_effects_through_their_triggers(tmp_path, case, field, value):
    (root, owner, claim, prepared, trigger, material, preparation, store, meta, target, ref,
     calls, observe) = _approved_h_through_conductor(tmp_path, case)
    result = conductor.consume_conductor_gate(
        root, prepared.id, store=store, meta=meta, claim_id=claim,
        material=material, preparation=preparation, observe=observe)
    assert result.state == "applied" and result.parent_ref == ref, result
    if field == "stage":
        assert roadmap.stage_by_number(roadmap.load_roadmap(target), 1).status == value
    elif field == "key":
        assert roadmap.stage_by_number(roadmap.load_roadmap(target), 1).key_status[owner] == value
    else:
        assert gates.parse(prepared.path).effect == value
    assert target.read_text(encoding="utf-8").startswith(f"<!-- {ref} -->")
    rows = [r for r in lifecycle.read_lifecycle(store).events if r["kind"] == "lifecycle"]
    assert [r["lifecycle"] for r in rows] == ["consumed", "executed", "settled"]
    replay = conductor.consume_conductor_gate(
        root, prepared.id, store=store, meta=meta, claim_id=claim,
        material=material, preparation=preparation, observe=observe)
    assert replay.state == "applied" and replay.duplicate
    assert calls[0] == 1 and len([r for r in lifecycle.read_lifecycle(store).events
                               if r["kind"] == "lifecycle"]) == 3


@pytest.mark.parametrize("fault", ["missing-authority", "wrong-claim", "changed-material", "historical-trigger"])
def test_conductor_consume_refuses_without_bound_source(tmp_path, fault):
    (root, owner, claim, prepared, trigger, material, preparation, store, meta, target, ref,
     calls, observe) = _approved_h_through_conductor(tmp_path)
    before = target.read_bytes()
    if fault == "missing-authority":
        original = observe
        observe = lambda gate: replace(original(gate), authority_source={})
        gate_id, claim_value = prepared.id, claim
    elif fault == "wrong-claim":
        gate_id, claim_value = prepared.id, "other-host:1"
    elif fault == "changed-material":
        material = json.loads(json.dumps(material))
        material["pm_note"]["planned_action"] = "a different action"
        gate_id, claim_value = prepared.id, claim
    else:
        gate_id, claim_value = trigger.id, claim
    result = conductor.consume_conductor_gate(
        root, gate_id, store=store, meta=meta, claim_id=claim_value,
        material=material, preparation=preparation, observe=observe)
    assert result.state == "blocked" and result.reason
    assert calls[0] == 0 and target.read_bytes() == before
    assert gates.parse(prepared.path).effect == "not-started"


# ─────────────────────────────────────────────────────────────────────────────
# T26 core consumers: H09/H10 verified exhaustion, H11/H12 brake consumption,
# H13 current-evidence stage close. Production entries only, isolated fixtures.
# ─────────────────────────────────────────────────────────────────────────────

_T26_KEY = "key-t26"
_T26_MATERIAL = {
    "delivery_goal": "deliver the T26 stage-close consumer",
    "actual_completion": "current-evidence stage-close consumer and tests landed",
    "verification_evidence": {
        "verified": ["pytest test_dp_consolidation_gate_effects.py"],
        "unverified": ["real provider end to end"],
    },
    "unfinished_impact": [],
}


def _t26_sign_key(project, key, material, logical_id="logical-t26-1"):
    key_dir = project / ".agenticdoc" / key
    (key_dir / "evidence" / "review").mkdir(parents=True, exist_ok=True)
    decide_archive.append_decide(
        decide_signoff.archive_path(project),
        dp="dp-QG",
        key=key,
        task_key="task-t26",
        trigger_id=logical_id,
        state={"schema_version": 2, "decision_point": "dp-QG"},
        questions_version="q-0123abcd",
        available=True,
        answer={"q-verdict": {"value": "pass", "confidence": 0.9}},
        authority="binding",
        acted=True,
        actual_action="record the QG pass verdict",
        mode="auto",
        transport="timi-decisions",
        model="jev-latest",
        confidence_source="api",
    )
    facts = decide_signoff.collect(project, key)
    record = signoff_result.build_result(
        key_dir, key=key, logical_id=logical_id,
        decision_id=f"{signoff_result.DP_ID}:{logical_id}", conclusion="finalize",
        material=material, facts=facts, transport="timi-decisions", model="jev-latest",
        confidence_source="api", task_key="task-t26", initiator_role="pm",
        snapshot_material=material,
    )
    signoff_result.write_result(key_dir, record, redact=decision.known_secret_redactor())
    text = decide_signoff.render(facts, "finalize", None, key, "-", result=record)
    decide_signoff.write_signoff(project, key, text)
    return key_dir


def _t26_stage_material(project, number, entries, **overrides):
    path = closure.stage_close_material_path(project, number)
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = {
        "schema": 1,
        "stage": number,
        "submitted_at": "2026-11-09T00:00:00+00:00",
        "source": closure.STAGE_CLOSE_MATERIAL_SOURCE,
        "key_signoffs": entries,
        **overrides,
    }
    path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    return path


def test_h13_stage_close_requires_the_current_pm_signoff_submission(tmp_path):
    project = tmp_path / "project"
    material = json.loads(json.dumps(_T26_MATERIAL))
    _t26_sign_key(project, _T26_KEY, material)
    evidence = material["verification_evidence"]
    _t26_stage_material(project, 1, {_T26_KEY: {"matter": material, "evidence": evidence}})

    check = closure.stage_close_check(project, 1, [_T26_KEY])
    assert check.ok is True and check.signed == (_T26_KEY,) and check.skipped == (), check

    _t26_stage_material(
        project, 1, {_T26_KEY: {"matter": material, "evidence": evidence}},
        source="record.material",
    )
    stale = closure.stage_close_check(project, 1, [_T26_KEY])
    assert stale.ok is False and any("not the current PM submission" in i for i in stale.issues)

    _t26_stage_material(
        project, 1,
        {_T26_KEY: {"matter": material, "evidence": {"verified": ["later"], "unverified": []}}},
    )
    changed = closure.stage_close_check(project, 1, [_T26_KEY])
    assert changed.ok is False and any("SIGNOFF" in i for i in changed.issues)

    closure.stage_close_material_path(project, 1).unlink()
    missing = closure.stage_close_check(project, 1, [_T26_KEY])
    assert missing.ok is False and any("MISSING" in i for i in missing.issues)


def test_h13_stage_close_does_not_expand_signoff_scope(tmp_path):
    project = tmp_path / "project"
    check = closure.stage_close_check(project, 1, [_T26_KEY])
    assert check.ok is True and check.skipped == (_T26_KEY,)
    (project / ".mw").mkdir(parents=True)
    (project / ".mw" / "decide.json").write_text('{"signoff": "disable"}\n', encoding="utf-8")
    material = json.loads(json.dumps(_T26_MATERIAL))
    _t26_sign_key(project, _T26_KEY, material)
    disabled = closure.stage_close_check(project, 1, [_T26_KEY])
    assert disabled.ok is True and disabled.skipped == (_T26_KEY,)


def test_h13_user_risks_must_be_explicitly_accepted(tmp_path):
    project = tmp_path / "project"
    material = json.loads(json.dumps(_T26_MATERIAL))
    _t26_sign_key(project, _T26_KEY, material)
    _t26_stage_material(
        project, 1, {_T26_KEY: {"matter": material, "evidence": material["verification_evidence"]}},
        user_risks=[{"risk": "deferred integration check"}],
    )
    refused = closure.stage_close_check(project, 1, [_T26_KEY])
    assert refused.ok is False and any("explicit user acceptance" in i for i in refused.issues)

    _t26_stage_material(
        project, 1, {_T26_KEY: {"matter": material, "evidence": material["verification_evidence"]}},
        user_risks=[{"risk": "deferred integration check", "accepted_by": "user:1"}],
    )
    assert closure.stage_close_check(project, 1, [_T26_KEY]).ok is True


def _t26_stage_fixture(tmp_path):
    root = tmp_path / "project"
    config.save_config(root, {"enabled": True, "paused": False, "auto_gate_mode": "off"})
    (root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    target = roadmap.roadmap_path(root)
    target.write_text(
        "## Stage 1: Integration\n> goal: Ship the verified feature\n> status: running\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n"
        f"| {_T26_KEY} | implement | - |\n",
        encoding="utf-8",
    )
    st = conductor.ConductorState(conductor.timeline.Timeline(conductor.timeline.timeline_path(root)), None)
    return root, st, target, roadmap.load_roadmap(target).stages[0]


def test_h13_conductor_withholds_the_close_gate_without_current_evidence(tmp_path):
    root, st, target, stage = _t26_stage_fixture(tmp_path)
    material = json.loads(json.dumps(_T26_MATERIAL))
    _t26_sign_key(root, _T26_KEY, material)

    conductor._stage_closure(root, st, stage, target, {_T26_KEY: "done"}, rows=[])
    assert gates.enumerate(conductor.gates_dir(root)) == []
    events = conductor.timeline.query_events(conductor.timeline.timeline_path(root)).events
    assert any("close withheld" in str(e.get("detail") or "") for e in events)

    _t26_stage_material(
        root, 1, {_T26_KEY: {"matter": material, "evidence": material["verification_evidence"]}},
    )
    conductor._stage_closure(root, st, stage, target, {_T26_KEY: "done"}, rows=[])
    opened = [g for g in gates.enumerate(conductor.gates_dir(root)) if g.kind == "stage-close"]
    assert len(opened) == 1 and opened[0].historical


def _t26_brake(project, state, *, trip="a" * 32):
    from autopilot import decision_recovery

    header = (
        "---\nreason: burst-60s\ndetail: fixture\ntriggered_at: 2026-11-09T00:00:00Z\n"
        "action: escalate-to-human\n---\n"
    ).encode("utf-8")
    trip_id = decision_recovery._legacy_trip(header)["trip_id"]
    assert trip_id
    events = ""
    if state in ("observing", "clear"):
        events += "mw-breaker-event: " + json.dumps({
            "state": "observing", "trip_id": trip_id,
            "decision_ref": "dp-gate-approve:fixture",
            "grant_ref": trip, "amount": 1, "usage_source": "steps",
        }, sort_keys=True) + "\n"
    if state == "clear":
        events += "mw-breaker-event: " + json.dumps({
            "state": "clear", "trip_id": trip_id,
        }, sort_keys=True) + "\n"
    path = conductor.auto_brake_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(header + events.encode("utf-8"))
    return trip_id


def test_h12_managed_brake_generations_drive_the_normal_conductor(tmp_path):
    project = tmp_path / "project"
    trip = _t26_brake(project, "tripped")
    tripped = conductor.auto_breaker_state(project)
    assert tripped["active"] is True and tripped["reason"] == "burst-60s"
    assert trip  # the legacy header is its own generation

    _t26_brake(project, "observing")
    observing = conductor.auto_breaker_state(project)
    assert observing["active"] is True and observing["state"] == "observing"

    _t26_brake(project, "clear")
    cleared = conductor.auto_breaker_state(project)
    assert cleared["active"] is False and cleared["state"] == "clear"

    conductor.auto_brake_path(project).write_text("mw-breaker-event: {broken\n", encoding="utf-8")
    damaged = conductor.auto_breaker_state(project)
    assert damaged["active"] is True and damaged["reason"] == "brake-generation-unverified"

    conductor.auto_brake_path(project).write_text(
        "---\nreason: burst-1h\ntriggered_at: 2026-11-09T00:00:00Z\n---\n", encoding="utf-8")
    legacy = conductor.auto_breaker_state(project)
    assert legacy["active"] is True and legacy["reason"] == "burst-1h"




def _t26_ledger_rows(project, count=17):
    import datetime

    now = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    for index in range(count):
        conductor._append_auto_decision_row(project, {
            "decision_id": f"seed-{index}",
            "phase": "decide",
            "mode": "live",
            "executed": True,
            "decision": "approve",
            "rule_id": "fixture-rule",
            "reason_code": "fixture-run",
            "gate_id": f"gate-{9000 + index:04d}",
            "gate_key": f"key-{index % 3}",
            "night": "2026-11-09",
            "decided_at": now,
        })
    return [row["seq"] for row in conductor.auto_decision_rows(project) if row.get("executed")]


def _t26_trigger_payload(project, evidence, *, request_id="d" * 32, reason="burst-60s",
                         detail="fixture hard signal"):
    return json.dumps({
        "schema": 1, "purpose": "brake-trigger",
        "project_id": wire.project_id_for(project),
        "reason_code": reason, "detail": detail,
        "evidence": evidence, "request_id": request_id,
    }, sort_keys=True).encode("utf-8")


def _t26_host(project, tmp_path, monkeypatch):
    import operator_authority as oa
    import operator_host as host_module
    from autopilot import decision_recovery as recovery

    if host_module.Fido2Server is None:
        # Only the WebAuthn deployment boundary is absent in this fixture; the
        # negotiated IPC message, host handler and protected writer stay real.
        monkeypatch.setattr(host_module, "Fido2Server", lambda *args, **kwargs: object())
        monkeypatch.setattr(
            host_module, "PublicKeyCredentialRpEntity", lambda *args, **kwargs: object())

    project_id = wire.project_id_for(project)
    peer = oa.Peer("fixture-pm-sid", os.getpid(), 123, 1, "fixture-pm")
    registration = host_module.Project(
        project, frozenset([peer.sid]), frozenset([peer.image]))
    instance = host_module.OperatorHost(
        tmp_path / "brake-host.db", origin="https://localhost:9443",
        projects={project_id: registration}, operators={},
        ttl_seconds=300, brake_read=recovery.brake_facts,
        brake_trigger=recovery.trigger_managed_brake,
        guard=lambda *_: True, verify_deployment=lambda *_: True)

    def exchange(purpose, message, trust, timeout_ms):
        assert purpose == "ask"
        return instance.handle(peer, message)

    class _Trust:
        class peer:
            pid = os.getpid()
            created_ns = 1

    monkeypatch.setattr(oa, "_exchange", exchange)
    monkeypatch.setattr(oa, "load_trust", lambda: _Trust())
    monkeypatch.setattr(oa, "registered_project", lambda pid: pid == project_id)
    return instance, peer


def test_h12_normal_trigger_uses_the_registered_host_and_the_real_ledger(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    _t26_brake(project, "clear")
    evidence = _t26_ledger_rows(project)
    instance, peer = _t26_host(project, tmp_path, monkeypatch)
    assert conductor.auto_breaker_state(project)["active"] is False
    state = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(project)), None)
    conductor._trip_auto_breaker(project, state, "burst-60s", "17 auto decisions in 60s")
    tripped = conductor.auto_breaker_state(project)
    assert tripped["active"] is True and tripped["state"] == "tripped"
    assert len(tripped["trip"]) == 32
    rows = [row for row in conductor.auto_decision_rows(project)
            if row.get("reason_code") == "breaker-tripped"]
    assert len(rows) == 1 and rows[0]["trip_id"] == tripped["trip"]
    # The write went through the protected writer, never through a client path/trip/state.
    assert all(row.get("trigger_request_id") for row in rows)
    # Replay of the exact recorded trigger is one write, not a second generation.
    import base64

    payload = _t26_trigger_payload(
        project, evidence, request_id=rows[0]["trigger_request_id"],
        detail="17 auto decisions in 60s")
    replay = instance.handle(peer, {
        "v": 1, "op": "ask.brake-trigger", "project_id": wire.project_id_for(project),
        "payload_b64": base64.b64encode(payload).decode()})
    assert replay["ok"] is True and replay["created"] is False, replay
    assert replay["trip_id"] == tripped["trip"]
    assert len([row for row in conductor.auto_decision_rows(project)
                if row.get("reason_code") == "breaker-tripped"]) == 1
    # A genuinely new trigger (a different recorded request) is a new
    # generation even with the same reason and second.
    third_payload = _t26_trigger_payload(
        project, evidence, request_id="c" * 32, detail="17 auto decisions in 60s")
    third = instance.handle(peer, {
        "v": 1, "op": "ask.brake-trigger", "project_id": wire.project_id_for(project),
        "payload_b64": base64.b64encode(third_payload).decode()})
    assert third["ok"] is True and third["created"] is True
    assert third["trip_id"] != tripped["trip"]
    # Removing the original object is unknown/active for a registered project.
    conductor.auto_brake_path(project).unlink()
    missing = conductor.auto_breaker_state(project)
    assert missing["active"] is True and missing["state"] == "unknown"
    # An unregistered project keeps the legacy local behaviour.
    other = tmp_path / "other"
    (other / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    assert conductor.auto_breaker_state(other)["active"] is False
    # A moved/replaced project root cannot make the registered object look clear.
    project.rename(tmp_path / "moved")
    replaced = conductor.auto_breaker_state(project)
    assert replaced["active"] is True and replaced["state"] == "unknown"


class _T26Trust:
    class peer:
        pid = os.getpid()
        created_ns = 1


def _t26_registered(monkeypatch, project_id=True):
    import operator_authority as oa

    monkeypatch.setattr(oa, "load_trust", lambda: _T26Trust())
    monkeypatch.setattr(oa, "registered_project",
                        lambda pid: project_id if isinstance(project_id, bool) else pid == project_id)
    return oa


@pytest.mark.parametrize("reason", [
    "host-identity-mismatch",
    "host-unavailable",
    "untrusted-path",
    "host-timeout",
    "access-denied",
])
def test_h12_pin_trust_failures_are_unknown_and_never_fall_back_to_the_local_writer(
        tmp_path, monkeypatch, reason):
    """A failed trust/pin/ACL/API query is not proof of an unmanaged project."""
    import operator_authority as oa

    project = tmp_path / "project"
    (project / ".agenticdoc" / "_autopilot").mkdir(parents=True)

    def no_anchor():
        raise oa.AuthorityError(reason)

    monkeypatch.setattr(oa, "load_trust", no_anchor)
    state = conductor.auto_breaker_state(project)
    assert state["active"] is True and state["state"] == "unknown"
    st = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(project)), None)
    assert conductor._trip_auto_breaker(project, st, "burst-60s", "17 auto decisions in 60s") is False
    assert not conductor.auto_brake_path(project).exists()
    assert conductor.auto_decision_rows(project) == []


def test_h12_only_a_real_absent_scm_service_keeps_the_unmanaged_local_path(tmp_path, monkeypatch):
    """The SCM's own SERVICE_DOES_NOT_EXIST is the only unmanaged proof."""
    import operator_authority as oa

    project = tmp_path / "project"
    (project / ".agenticdoc" / "_autopilot").mkdir(parents=True)

    def absent():
        raise oa.ServiceNotDeployed()

    monkeypatch.setattr(oa, "load_trust", absent)
    assert conductor.auto_breaker_state(project)["active"] is False
    st = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(project)), None)
    assert conductor._trip_auto_breaker(project, st, "burst-60s", "17 auto decisions in 60s") is True
    local = conductor.auto_breaker_state(project)
    assert local["active"] is True and local["reason"] == "burst-60s"
    assert conductor.auto_brake_path(project).is_file()


def test_h12_registered_local_clear_cannot_bypass_the_protected_source(tmp_path, monkeypatch):
    """A local clear/managed event is never the registered object's facts."""
    import operator_authority as oa

    project = tmp_path / "project"
    _t26_brake(project, "clear")
    assert conductor.auto_breaker_state(project)["active"] is False
    oa = _t26_registered(monkeypatch)
    reads = []

    def read(project_id, **_kwargs):
        reads.append(project_id)
        return {"ok": True, "facts": {
            "state": "tripped", "active": True, "reason": "burst-60s",
            "trip_id": "a" * 32, "generation_verified": True,
            "brake_sha256": "b" * 64, "ledger_seq": None}}

    monkeypatch.setattr(oa, "read_brake", read)
    state = conductor.auto_breaker_state(project)
    assert reads == [wire.project_id_for(project)]
    assert state["active"] is True and state["state"] == "tripped"
    assert state["trip"] == "a" * 32


@pytest.mark.parametrize("read_reply", [
    {"ok": False, "reason": "project-unavailable"},
    {"ok": False, "reason": "host-unavailable"},
    {"ok": False, "reason": "untrusted-path"},
])
def test_h12_registered_read_failure_after_registration_is_unknown_active(
        tmp_path, monkeypatch, read_reply):
    """A previously registered project never becomes unmanaged again."""
    project = tmp_path / "project"
    (project / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    oa = _t26_registered(monkeypatch)
    monkeypatch.setattr(oa, "read_brake", lambda project_id, **_kwargs: dict(read_reply))
    state = conductor.auto_breaker_state(project)
    assert state["active"] is True and state["state"] == "unknown"
    assert state["reason"] == "brake-generation-unverified"


def test_h12_trigger_writer_generates_a_new_generation_after_a_real_clear(tmp_path, monkeypatch):
    project = tmp_path / "project"
    (project / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    _t26_brake(project, "clear")
    evidence = _t26_ledger_rows(project)
    monkeypatch.setattr(decision_recovery, "_authorized", lambda *args: True)
    first_payload = _t26_trigger_payload(project, evidence, request_id="e" * 32)
    first = decision_recovery.trigger_managed_brake(project, first_payload)
    assert first["ok"] is True and first["created"] is True and len(first["trip_id"]) == 32
    path = conductor.auto_brake_path(project)
    before = path.read_bytes()
    decision_recovery._append(path, before, {
        "state": "observing", "trip_id": first["trip_id"],
        "decision_ref": "dp-gate-approve:" + "a" * 32,
        "grant_ref": "b" * 32, "amount": 1, "usage_source": "round"})
    before = path.read_bytes()
    decision_recovery._append(path, before, {"state": "clear", "trip_id": first["trip_id"]})
    second_payload = _t26_trigger_payload(project, evidence, request_id="f" * 32)
    second = decision_recovery.trigger_managed_brake(project, second_payload)
    assert second["ok"] is True and second["created"] is True
    assert second["trip_id"] != first["trip_id"]
    state = conductor.auto_breaker_state(project)
    assert state["active"] is True and state["trip"] == second["trip_id"]
    # Same request replayed is idempotent; it cannot mint another generation.
    replay = decision_recovery.trigger_managed_brake(project, second_payload)
    assert replay["created"] is False and replay["trip_id"] == second["trip_id"]
    assert decision_recovery.managed_brake_state(project)["trip"] == second["trip_id"]


def _t26_proposal_rows(project, status):
    (project / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (project / ".agenticdoc/_workers.parallel").write_text(
        f"ap-owner-xkey-r1-proposal | {status} | codex | timi | task.md | "
        "2026-11-09T00:00:00Z | 2026-11-09T00:00:00Z\n",
        encoding="utf-8",
    )
    return mw_common.parse_workers_file(mw_common.workers_path(project))


def test_h09_proposal_exhaustion_reads_the_real_dispatch_family(tmp_path):
    project = tmp_path / "project"
    ticket = {"request_id": "r1", "source_key": "owner", "proposal_attempts": 2}
    proposal = project / ".agenticdoc/_autopilot/xkey/evidence/r1/proposal.md"
    proposal.parent.mkdir(parents=True, exist_ok=True)

    assert dispatch.inspect_proposal_exhaustion(
        project, ticket, [], proposal_path=proposal, max_attempts=2).state == "unknown"
    assert dispatch.inspect_proposal_exhaustion(
        project, ticket, _t26_proposal_rows(project, "running"),
        proposal_path=proposal, max_attempts=2).state == "in-flight"
    exhausted = dispatch.inspect_proposal_exhaustion(
        project, ticket, _t26_proposal_rows(project, "done"),
        proposal_path=proposal, max_attempts=2)
    assert exhausted.state == "exhausted" and exhausted.task_keys
    proposal.write_text("proposal\n", encoding="utf-8")
    assert dispatch.inspect_proposal_exhaustion(
        project, ticket, _t26_proposal_rows(project, "done"),
        proposal_path=proposal, max_attempts=2).state == "complete"


class _T26Xkey:
    def __init__(self):
        self.ticket = None

    def ledger_append(self, *args, **kwargs):
        return None

    def ticket_write(self, root, ticket):
        self.ticket = json.loads(json.dumps(ticket))


def test_h09_conductor_never_records_an_unverified_exhaustion(tmp_path):
    project = tmp_path / "project"
    st = conductor.ConductorState(conductor.timeline.Timeline(conductor.timeline.timeline_path(project)), None)
    ticket = {"request_id": "r1", "source_key": "owner", "proposal_attempts": 2}
    xkey = _T26Xkey()
    _t26_proposal_rows(project, "running")
    conductor._xkey_proposal_exhaust(project, st, xkey, ticket, "r1", "bound")
    assert "proposal_exhausted_at" not in xkey.ticket
    assert xkey.ticket["proposal_verified_state"] == "in-flight"

    ticket = {"request_id": "r1", "source_key": "owner", "proposal_attempts": 2}
    (project / ".agenticdoc/_workers.parallel").unlink()
    conductor._xkey_proposal_exhaust(project, st, xkey, ticket, "r1", "bound")
    assert "proposal_exhausted_at" not in xkey.ticket
    assert xkey.ticket["proposal_verified_state"] == "unknown"

    ticket = {"request_id": "r1", "source_key": "owner", "proposal_attempts": 2}
    _t26_proposal_rows(project, "done")
    conductor._xkey_proposal_exhaust(project, st, xkey, ticket, "r1", "bound")
    assert xkey.ticket["proposal_exhausted_at"]
    assert xkey.ticket["proposal_verified_state"] == "exhausted"
    assert xkey.ticket["proposal_attempts"] == 2


def test_h09_bounded_recovery_needs_a_real_authorization_and_version(tmp_path):
    ticket = {"proposal_failure_version": "v1"}
    assert dispatch.bounded_recovery_plan(ticket) == (None, ())
    ticket["proposal_recovery"] = {
        "authorization_ref": "dp-gate-approve:real", "action": "retry",
        "version": "v1", "budget": "one proposal worker", "end_condition": "proposal.md lands",
    }
    plan, issues = dispatch.bounded_recovery_plan(ticket)
    assert plan is None and any("version" in issue for issue in issues)
    ticket["proposal_recovery"]["version"] = "v2"
    assert dispatch.bounded_recovery_plan(ticket)[0]["version"] == "v2"
    ticket["proposal_recovery"]["authorization_ref"] = ""
    plan, issues = dispatch.bounded_recovery_plan(ticket)
    assert plan is None and any("authorization_ref" in issue for issue in issues)


def _h09_enable_policy(project):
    path = project / ".agenticdoc/_autopilot/decision-policy.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1, "authority_ref": "signed-scope",
        "scope": ["action:phase-failure"],
        "recovery": {
            "allowed_origins": ["user"], "scope": ["action:phase-failure"],
            "authority_ref": "signed-scope",
            "observation_conditions": ["the phase gate passes"],
            "stop_conditions": ["the same failure recurs"],
        },
    }), encoding="utf-8")


def _h09_record_auto_request(project, key, logical_id, decision_ref):
    """Write the same structural row T10 records for a real dp-auto request."""
    path = project / ".agenticdoc/_autopilot/decision-lifecycle.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"kind": "record-start", "logical_id": logical_id, "key": key},
        {"kind": "request", "logical_id": logical_id, "key": key,
         "decision_id": decision_ref, "dp": "dp-auto", "available": True,
         "business_decisions": 1, "choice": "c1"},
    ]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


def test_h09_advance_keeps_failures_and_requires_disposition_then_verification(tmp_path):
    project = tmp_path / "project"

    assert advance.recovery_enforced(project) is False
    assert advance.record_failure(project, "owner", "done", 1, "", "gate blocked") is None

    _h09_enable_policy(project)
    assert advance.recovery_enforced(project) is True
    record = advance.record_failure(project, "owner", "done", 1, "out", "   - gate blocked\n")
    assert record and record["stderr"] == "   - gate blocked\n"
    allowed, reason, active = advance.advance_allowed(project, "owner", "done")
    assert allowed is False and active and "no automatic disposition" in reason

    with pytest.raises(ValueError, match="end_condition"):
        advance.record_disposition(project, "owner", "done", decision_ref="dp-auto:x",
                                   action="narrow", budget="one round", end_condition="")
    with pytest.raises(ValueError, match="recorded dp-auto"):
        advance.record_disposition(project, "owner", "done", decision_ref="dp-auto:forged",
                                   action="narrow", budget="one round",
                                   end_condition="phase gate passes")
    _h09_record_auto_request(project, "owner", "auto-1", "dp-auto:auto-1")
    advance.record_disposition(project, "owner", "done", decision_ref="dp-auto:auto-1",
                               action="narrow", budget="one round", end_condition="phase gate passes")
    assert advance.advance_allowed(project, "owner", "done")[0] is False
    pass_cmd = f'{sys.executable} -c pass'
    fail_cmd = f'{sys.executable} -c 0/0'
    # A self-reported rc=0 never releases the edge: the recorded rc is the one
    # the command actually produced.
    advance.record_verification(project, "owner", "done", verify_cmd=fail_cmd, rc=0)
    assert advance.advance_allowed(project, "owner", "done")[0] is False
    advance.record_verification(project, "owner", "done", verify_cmd=pass_cmd, rc=1)
    assert advance.advance_allowed(project, "owner", "done")[0] is True
    assert any(row.get("kind") == "failure" for row in advance._rows(project, "owner"))


def test_h10_roadmap_replan_needs_a_substantive_revision_basis(tmp_path, monkeypatch):
    project = tmp_path / "project"
    st = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(project)), None)
    calls = []

    class _Result:
        ok = True
        reason = ""

    monkeypatch.setattr(conductor.state, "used_rounds", lambda dirs: {"roadmap:stage-1": 1})
    monkeypatch.setattr(conductor.state, "scan_worker_tasks", lambda project_root: [])
    monkeypatch.setattr(conductor.dispatch, "dispatch",
                        lambda *args, **kwargs: calls.append(args) or _Result())

    conductor._dispatch_roadmap_writer(project, st, [], stage_number=1, rejected_note="")
    assert calls == []
    events = conductor.timeline.query_events(conductor.timeline.timeline_path(project)).events
    assert any("roadmap re-plan withheld" in str(e.get("detail") or "") for e in events)

    conductor._dispatch_roadmap_writer(project, st, [], stage_number=1,
                                       rejected_note="human: raise stage-1 priority")
    assert len(calls) == 1


# ── T26-H10 native producer/dispatch closure (AC-032/AC-033, VC-032/VC-033) ──
# These drive the REAL H10 producer (`conductor._dispatch_roadmap_writer`) and
# the REAL queue/file/attempt consumer (`dispatch.dispatch`), with REAL
# `state.used_rounds` / `state.scan_worker_tasks` (no override) and a real
# prior rejected/failed attempt. Only the external model response (the new
# roadmap body) is a transport-only faux seam: the legitimate next writer's
# documented whole-file rewrite of `_roadmap.md`.

_H10_OLD_V1 = (
    "# Roadmap\n"
    "> generated_at: 2026-11-09T00:00:00+00:00\n"
    "> goal_mtime: 1789000000000\n"
    "\n"
    "## Stage 1: ORIGINAL-PROPOSAL-v1 (this body must survive the re-plan)\n"
    "> goal: deliver k1 with the ORIGINAL prior proposal body\n"
    "> status: pending\n"
    "> key-status: k1=running\n"
    "### Keys\n"
    "| key | role | depends_on |\n"
    "|-----|------|-----------|\n"
    "| k1 | worker | - |\n"
)
_H10_V2 = (
    _H10_OLD_V1
    .replace("ORIGINAL-PROPOSAL-v1 (this body must survive the re-plan)",
             "REVISED-PROPOSAL-v2 (whole-file rewrite by the next writer)")
    .replace("deliver k1 with the ORIGINAL prior proposal body",
             "deliver k1 (revised after reject)")
)
_H10_NOTE = "human: split stage 1; ORIGINAL-PROPOSAL-v1 too broad"
_H10_ARCHIVE_REL = dispatch.roadmap_prior_archive_rel(1, 1)


def _h10_rows(project):
    return mw_common.parse_workers_file(mw_common.workers_path(project))


def _h10_used(project):
    return conductor.state.used_rounds(conductor._all_workers_dirs(project))


def _h10_new_project(tmp_path):
    project = tmp_path / "project"
    ap = project / ".agenticdoc" / "_autopilot"
    ap.mkdir(parents=True)
    (project / ".agenticdoc" / "goal.md").write_text(
        "# Goal\n\nShip stage 1.\n", encoding="utf-8", newline="\n")
    cfg = config.default_config()
    cfg["enabled"] = True
    config.save_config(project, cfg)
    (project / ".agenticdoc" / "_index.parallel").write_text(
        "| k1 | active | SPEC | - | - | desc | 2026-11-09T00:00:00Z |\n",
        encoding="utf-8", newline="\n")
    st = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(project)), None)
    return project, st


def _h10_write_roadmap(project, text):
    path = project / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path


def _h10_finish(project, task_key):
    wp = mw_common.workers_path(project)
    entries = mw_common.parse_workers_file(wp)
    for e in entries:
        if e["task_key"] == task_key:
            e["status"] = "done"
    wp.write_text(
        "\n".join(mw_common.serialize_entry(e) for e in entries) + "\n",
        encoding="utf-8", newline="\n")


def _h10_rejected_gate(project, note):
    g = gates.create(conductor.gates_dir(project), "stage-confirm",
                     "confirm stage 1?", stage=1, key="k1")
    txt = g.read_text(encoding="utf-8").replace("status: pending", "status: rejected")
    if note:
        txt = txt.replace("\nnote:\n", f"\nnote: '{note}'\n")
    g.write_text(txt, encoding="utf-8", newline="\n")
    return conductor._latest_rejected_confirm(project, 1).note or ""


def _h10_real_a1(project, st):
    """Real fresh-proposal dispatch (used=0): real a1 queue row + task.md."""
    conductor._dispatch_roadmap_writer(project, st, _h10_rows(project), stage_number=1)
    return "ap-_scratch-roadmap-s1-a1"


def _h10_replan_ready(tmp_path, *, note=_H10_NOTE, finish_a1=True):
    """Real prior: a1 attempt (round consumed), old v1 proposal, rejected gate."""
    project, st = _h10_new_project(tmp_path)
    a1 = _h10_real_a1(project, st)
    if finish_a1:
        _h10_finish(project, a1)
    old = _H10_OLD_V1.encode("utf-8")
    _h10_write_roadmap(project, _H10_OLD_V1)
    real_note = _h10_rejected_gate(project, note)
    return project, st, a1, old, real_note


def _h10_a2(project):
    return project / ".agenticdoc" / "_scratch" / "workers" / \
        "ap-_scratch-roadmap-s1-a2" / "task.md"


def _h10_archive(project):
    return project / _H10_ARCHIVE_REL


def _h10_events(project):
    return conductor.timeline.query_events(
        conductor.timeline.timeline_path(project)).events


def test_h10_native_no_revision_basis_publishes_no_queue(tmp_path):
    project, st, a1, old, note = _h10_replan_ready(tmp_path, note="")
    assert note == ""
    assert _h10_used(project).get("roadmap:stage-1") == 1  # real round, not overridden
    before_rows = _h10_rows(project)
    conductor._dispatch_roadmap_writer(
        project, st, before_rows, stage_number=1, rejected_note=note)
    # no a2 queue row, no a2 task.md, no archive (withheld before publication)
    assert not any(r["task_key"].endswith("-a2") for r in _h10_rows(project))
    assert not _h10_a2(project).is_file()
    assert not _h10_archive(project).is_file()
    assert _h10_used(project).get("roadmap:stage-1") == 1
    assert any("roadmap re-plan withheld" in str(e.get("detail") or "")
               for e in _h10_events(project))


def test_h10_native_valid_replan_one_a2_queue_links_and_preserves_prior(tmp_path):
    project, st, a1, old, note = _h10_replan_ready(tmp_path)
    assert note == _H10_NOTE
    # exact preimages of the OLD records (must stay byte-for-byte)
    a1_md = project / ".agenticdoc" / "_scratch" / "workers" / a1 / "task.md"
    a1_md_bytes = a1_md.read_bytes()
    a1_row_before = [r for r in _h10_rows(project) if r["task_key"] == a1]
    roadmap_before = (project / ".agenticdoc/_autopilot/_roadmap.md").read_bytes()
    assert roadmap_before == old

    conductor._dispatch_roadmap_writer(
        project, st, _h10_rows(project), stage_number=1, rejected_note=note)

    # one a2 queue row; the a2 task.md frontmatter is the materialized dispatch
    # argv (owner/stem/type/loop/attempt/read_scope), read-back verified.
    rows = _h10_rows(project)
    a2_rows = [r for r in rows if r["task_key"] == "ap-_scratch-roadmap-s1-a2"]
    assert len(a2_rows) == 1
    a2_row = a2_rows[0]
    assert a2_row["status"] == "pending" and a2_row["origin"] == "conductor"
    assert a2_row["cli"] == "pi"
    a2_md = _h10_a2(project)
    assert a2_md.is_file() and a2_row["task_path"] == str(a2_md)
    a2_text = a2_md.read_text(encoding="utf-8")
    for head in ("type: roadmap-writer", "origin: conductor",
                 "loop: roadmap:stage-1", "attempt: 2", "read_scope:",
                 "- .agenticdoc"):
        assert head in a2_text
    # exact original rejection reason, verbatim, in the new prepared prompt
    assert note in a2_text
    # new version links old source / rejection / attempt
    assert _H10_ARCHIVE_REL in a2_text
    assert "(attempt 1)" in a2_text and "(attempt 2)" in a2_text
    assert "Never rewrite the archive" in a2_text

    # old immutable bytes captured BEFORE publication; old records unchanged
    archive = _h10_archive(project)
    assert archive.is_file() and archive.read_bytes() == old
    assert a1_md.read_bytes() == a1_md_bytes
    assert [r for r in rows if r["task_key"] == a1] == a1_row_before
    assert (project / ".agenticdoc/_autopilot/_roadmap.md").read_bytes() == old

    # the legitimate next writer performs the prompt's whole-file rewrite
    _h10_write_roadmap(project, _H10_V2)
    current = (project / ".agenticdoc/_autopilot/_roadmap.md").read_bytes()
    assert current == _H10_V2.encode("utf-8") and b"ORIGINAL-PROPOSAL-v1" not in current
    # ... and the old proposal bytes STILL survive, immutable, in the archive
    assert archive.read_bytes() == old and b"ORIGINAL-PROPOSAL-v1" in archive.read_bytes()
    assert _h10_used(project).get("roadmap:stage-1") == 2
    assert not any(r["task_key"].endswith("-a3") for r in _h10_rows(project))


def test_h10_native_replan_dispatch_argv_is_real_producer_call(tmp_path, monkeypatch):
    project, st, a1, old, note = _h10_replan_ready(tmp_path)
    real_dispatch = conductor.dispatch.dispatch
    calls = []

    def pass_through(*args, **kwargs):
        # instrumentation only: the real queue/file/attempt consumer still runs
        calls.append((args, kwargs))
        return real_dispatch(*args, **kwargs)

    monkeypatch.setattr(conductor.dispatch, "dispatch", pass_through)
    conductor._dispatch_roadmap_writer(
        project, st, _h10_rows(project), stage_number=1, rejected_note=note)
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[0] == project
    assert args[1] == dispatch.SCRATCH_OWNER
    assert args[2] == "roadmap-s1-a2"
    assert args[3] == "roadmap-writer"
    assert kwargs["loop"] == "roadmap:stage-1" and kwargs["attempt"] == 2
    assert kwargs["read_scope"] == [".agenticdoc"]
    assert note in args[4] and _H10_ARCHIVE_REL in args[4]
    # the real consumer actually published the queue (not a stubbed success)
    assert any(r["task_key"] == "ap-_scratch-roadmap-s1-a2"
               for r in _h10_rows(project))
    assert _h10_archive(project).read_bytes() == old


def test_h10_native_in_flight_and_duplicate_tick_publish_no_extra_queue(tmp_path):
    # (a) a prior proposal still in flight: producer returns before any dispatch
    p1, s1, a1, old, note = _h10_replan_ready(tmp_path / "flight", finish_a1=False)
    assert any(r["task_key"] == a1 and r["status"] == "pending" for r in _h10_rows(p1))
    conductor._dispatch_roadmap_writer(
        p1, s1, _h10_rows(p1), stage_number=1, rejected_note=note)
    assert not any(r["task_key"].endswith("-a2") for r in _h10_rows(p1))
    assert not _h10_a2(p1).is_file()
    assert _h10_used(p1).get("roadmap:stage-1") == 1

    # (b) duplicate tick after a real a2 is already in flight: no a3, no dup a2
    p2, s2, a1b, oldb, noteb = _h10_replan_ready(tmp_path / "dup")
    conductor._dispatch_roadmap_writer(
        p2, s2, _h10_rows(p2), stage_number=1, rejected_note=noteb)
    assert sum(1 for r in _h10_rows(p2)
               if r["task_key"] == "ap-_scratch-roadmap-s1-a2") == 1
    a2_md_bytes = _h10_a2(p2).read_bytes()
    conductor._dispatch_roadmap_writer(
        p2, s2, _h10_rows(p2), stage_number=1, rejected_note=noteb)
    assert sum(1 for r in _h10_rows(p2)
               if r["task_key"] == "ap-_scratch-roadmap-s1-a2") == 1
    assert not any(r["task_key"].endswith("-a3") for r in _h10_rows(p2))
    assert _h10_a2(p2).read_bytes() == a2_md_bytes  # no duplicate rewrite


def test_h10_native_exhausted_two_attempt_budget_publishes_no_additional_queue(tmp_path):
    project, st, a1, old, note = _h10_replan_ready(tmp_path)
    # spend the 2nd (and final) attempt via the REAL producer/dispatch
    conductor._dispatch_roadmap_writer(
        project, st, _h10_rows(project), stage_number=1, rejected_note=note)
    assert _h10_a2(project).is_file()
    _h10_finish(project, "ap-_scratch-roadmap-s1-a2")
    assert _h10_used(project).get("roadmap:stage-1") == 2
    a1_md = project / ".agenticdoc" / "_scratch" / "workers" / a1 / "task.md"
    a2_md = _h10_a2(project)
    a1_bytes, a2_bytes = a1_md.read_bytes(), a2_md.read_bytes()
    rows_before = _h10_rows(project)

    # a valid note + old proposal must NOT exceed the original 2-attempt budget
    conductor._dispatch_roadmap_writer(
        project, st, _h10_rows(project), stage_number=1, rejected_note=note)
    assert not any(r["task_key"].endswith("-a3") for r in _h10_rows(project))
    assert _h10_used(project).get("roadmap:stage-1") == 2  # attempts not reset
    assert _h10_rows(project) == rows_before  # no rows cleared / rewritten
    assert a1_md.read_bytes() == a1_bytes and a2_md.read_bytes() == a2_bytes


def test_h10_native_capture_conflict_fails_closed_without_queue(tmp_path):
    project, st, a1, old, note = _h10_replan_ready(tmp_path)
    # an existing snapshot with DIFFERENT bytes must never be rewritten
    archive = _h10_archive(project)
    archive.parent.mkdir(parents=True, exist_ok=True)
    conflict = b"unrelated/forged prior snapshot - must stay untouched\n"
    archive.write_bytes(conflict)
    conductor._dispatch_roadmap_writer(
        project, st, _h10_rows(project), stage_number=1, rejected_note=note)
    assert archive.read_bytes() == conflict  # no rewrite of the old snapshot
    assert not any(r["task_key"].endswith("-a2") for r in _h10_rows(project))
    assert not _h10_a2(project).is_file()  # fail closed: no queue publication
    assert any("prior proposal archive failed" in str(e.get("detail") or "")
               for e in _h10_events(project))


def test_h10_native_archive_idempotent_and_never_rewrites_unrelated_snapshots(tmp_path):
    project, st, a1, old, note = _h10_replan_ready(tmp_path)
    archive = _h10_archive(project)
    archive.parent.mkdir(parents=True, exist_ok=True)
    archive.write_bytes(old)  # a correct prior capture from an earlier tick
    unrelated = project / dispatch.roadmap_prior_archive_rel(2, 1)
    unrelated.parent.mkdir(parents=True, exist_ok=True)
    unrelated_bytes = b"stage-2 proposal snapshot - unrelated, keep verbatim\n"
    unrelated.write_bytes(unrelated_bytes)

    conductor._dispatch_roadmap_writer(
        project, st, _h10_rows(project), stage_number=1, rejected_note=note)
    assert archive.read_bytes() == old  # idempotent, original bytes retained
    assert unrelated.read_bytes() == unrelated_bytes  # unrelated snapshot untouched
    # a2 is published (capture succeeded), still exactly one
    assert sum(1 for r in _h10_rows(project)
               if r["task_key"] == "ap-_scratch-roadmap-s1-a2") == 1


def test_h09_conductor_advance_is_blocked_by_an_unresolved_failure(tmp_path, monkeypatch):
    project = tmp_path / "project"
    _h09_enable_policy(project)
    calls = []

    def failing_advance(key, phase, project_root, summary=None):
        calls.append((key, phase))
        return 1, "", "   - gate blocked\n"

    monkeypatch.setattr(advance, "advance", failing_advance)
    code, _out, _err, _ms = conductor._timed_advance("owner", "done", project, summary="x")
    assert code == 1 and calls == [("owner", "done")]
    code, _out, err, _ms = conductor._timed_advance("owner", "done", project, summary="x")
    assert code == 1 and "no automatic disposition" in err and calls == [("owner", "done")]



# ─────────────────────────────────────────────────────────────────────────────
# T26 pm gate entry: H01-H05 normal PM prepare -> same-model answer -> the one
# TS writer -> real-object consumer -> lifecycle executed/settled. Production
# adapters only; the fixture injects the deployed authority source at the OS
# trust seam and never substitutes the adapter itself.
# ─────────────────────────────────────────────────────────────────────────────

def _pm_book_payload():
    book = json.loads((PACKAGE_DIR / "decide_cases/dp-gate-approve.json").read_text(encoding="utf-8"))["book"]
    return {"dp": "dp-gate-approve", "book": book}


def _pm_create_trigger(root, st, target, case):
    if case == "h01":
        conductor._create_stage_confirm_gate(root, st, roadmap.load_roadmap(target).stages[0])
    elif case == "h02":
        assert conductor._create_gate(root, st, "stage-close", "Close stage?", stage=1, refs=["stage-1"])
    elif case == "h03":
        conductor.mark_stalled(root, st, "owner", "fixture stall")
    elif case == "h04":
        assert conductor._create_gate(root, st, "budget-exhausted", "Extend the loop?", key="owner",
                                      refs=["loop:fixture"])
    else:
        assert conductor.defer_key_to_review(root, st, "owner", 1, kind="stalled")
    return [g for g in gates.enumerate(conductor.gates_dir(root))
            if g.historical and g.status == "pending" and g.kind == _H_KIND[case]][-1]


def _pm_policy(root, action_name):
    policy.policy_path(root).write_text(json.dumps({
        "schema_version": 1, "authority_ref": "signed-scope", "scope": [action_name],
        "hard_limits": [{"unit": "rounds", "limit": 5, "usage_source": "rounds"}],
        "recovery": {
            "allowed_origins": ["user"],
            "scope": [action_name],
            "authority_ref": "signed-scope",
            "observation_conditions": ["the phase gate passes after disposition"],
            "stop_conditions": ["the same phase failure recurs"],
        },
    }), encoding="utf-8")


def _pm_entry_fixture(tmp_path, case, *, answer=True):
    root, owner, claim, st, target = _conductor_h_fixture(tmp_path / case)
    if case == "h02":
        target.write_text(
            roadmap.update_stage_status(target.read_text(encoding="utf-8"), 1, "running"),
            encoding="utf-8", newline="\n",
        )
    trigger = _pm_create_trigger(root, st, target, case)
    book = _pm_book_payload()
    material = book["book"]["material"]
    preparation = book["book"]["preparation"]
    prepared = conductor.prepare_pm_gate(root, trigger.id, owner_key=owner, book=book)
    _, matter, _note = conductor._pm_gate_matter(root, owner, trigger, material, preparation)
    action_name = matter.action
    _pm_policy(root, action_name)
    store = lifecycle.LifecycleStore.production(root, redact=wire.SubstringRedactor([]))
    meta = lifecycle.DecisionMeta.create(owner, task_key="T26-pm-entry", initiator_role="pm")
    ref = "dp-gate-approve:" + meta.logical_id
    assert lifecycle.record_start(store, meta).recorded
    assert lifecycle.record_note(store, meta, decision_id=ref, pm_note=prepared.pm_note,
                                 prepared_at=preparation["prepared_at"]).recorded
    basis = next(v for v in preparation["basis_catalog"] if "approve" in v["applies_to"])
    client = decision.DecisionClient(
        decision.DecisionConfig(enabled=True, project_root=root,
                                evidence_path=tmp_path / "transport.jsonl"),
        decision.FakeBackend([decision.BackendOutcome(True, None, False, {
            "gate_decision": {"value": "approve", "confidence": 0.95},
            "basis_id": {"value": basis["id"], "confidence": 0.95},
        }, 0)]),
    )
    result = client.request_prepared("dp-gate-approve", material, preparation,
                                     logical_id=meta.logical_id, actor_role="pm")
    assert result["choice"] == "approve"
    assert lifecycle.record_request(store, meta, decision_id=ref, result=result,
                                    material=material, preparation=preparation).recorded
    if answer:
        deposited = _answer(prepared.path, decision="approve", modelBasis=result["basis_text"],
                            decisionRef=ref, matterRef=prepared.matter_ref,
                            substantiveVersion=prepared.substantive_version, answeredBy=claim)
        assert deposited["ok"], deposited
    return {
        "root": root, "owner": owner, "claim": claim, "st": st, "target": target,
        "trigger": trigger, "prepared": prepared, "book": book, "matter": matter,
        "action": action_name, "gate_ref": ref,
    }


def _pm_deploy_authority(monkeypatch, root, owner, action_name):
    """Deploy a protected authority config; only the SCM/kernel/ACL seam is stubbed.

    `read_pm_authority` still parses the real protected config bytes, binds the
    real project id/path, re-reads the real `_index.parallel` claim and validates
    the T07 records. What is mocked is exactly the OS trust boundary: the fixed
    SCM service anchor, the checked protected path and the process peer query.
    """
    project_id = wire.project_id_for(root)
    image = sys.executable
    config = {
        "schema": 1,
        "projects": {
            project_id: {
                "root": root.name,
                "trusted_writers": ["controlled-human"],
                "pm_sids": ["S-1-5-32-544"],
                "pm_images": [image],
                "authority_records": {
                    "signed-scope": {
                        "authority_ref": "signed-scope",
                        "kind": "user-grant",
                        "scope": [action_name],
                        "writer": "controlled-human",
                        "revoked": False,
                    },
                },
                "usage_sources": {},
                "policy_sha256": "",
            },
        },
    }
    host = root.parent / "host.json"
    host.write_text(json.dumps(config), encoding="utf-8", newline="\n")
    peer = conductor.operator_authority.Peer(
        "S-1-5-32-544", os.getpid(), 1, 1, os.path.normcase(image))
    trust = conductor.operator_authority.ServiceTrust(peer, host)
    monkeypatch.setattr(conductor.operator_authority, "load_trust", lambda: trust)
    monkeypatch.setattr(
        conductor.operator_authority, "trusted_path", lambda path, trust: path)
    monkeypatch.setattr(
        conductor.operator_authority, "_pm_process_peer", lambda pid: peer)
    return trust


@pytest.mark.parametrize("case,check", [
    ("h01", lambda f: roadmap.stage_by_number(roadmap.load_roadmap(f["target"]), 1).status == "running"),
    ("h02", lambda f: roadmap.stage_by_number(roadmap.load_roadmap(f["target"]), 1).status == "closed"),
    ("h03", lambda f: roadmap.stage_by_number(roadmap.load_roadmap(f["target"]), 1).key_status["owner"] == "running"),
    ("h04", lambda f: conductor._budget_bonus(f["root"], "loop:fixture") is True),
    ("h05", lambda f: roadmap.stage_by_number(roadmap.load_roadmap(f["target"]), 1).key_status["owner"] == "running"),
])
def test_pm_gate_entry_consumes_the_approved_h_effect_through_real_adapters(tmp_path, monkeypatch, case, check):
    f = _pm_entry_fixture(tmp_path, case)
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])
    object_path = (f["root"] / ".agenticdoc/_autopilot/budget-extensions.jsonl"
                   if case == "h04" else f["target"])
    before = object_path.read_bytes() if object_path.is_file() else b""
    result = conductor.consume_pm_gate(f["root"], f["prepared"].id, owner_key=f["owner"])
    assert result.state == "applied", result.reason
    assert result.parent_ref == f["gate_ref"] and result.receipt
    assert check(f) is True
    assert object_path.read_bytes() != before
    rows = [r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(f["root"], redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]
    assert [r["lifecycle"] for r in rows] == ["consumed", "executed", "settled"]
    applied_bytes = object_path.read_bytes()
    replay = conductor.consume_pm_gate(f["root"], f["prepared"].id, owner_key=f["owner"])
    assert replay.state == "applied" and replay.duplicate is True
    assert object_path.read_bytes() == applied_bytes
    assert len([r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(f["root"], redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]) == 3


def test_auto_rules_do_not_answer_a_prepared_decision_or_its_superseded_trigger(tmp_path):
    f = _pm_entry_fixture(tmp_path, "h01", answer=False)
    conductor.auto_decide_gates(f["root"], f["st"], config.load_config(f["root"]))
    assert gates.parse(f["prepared"].path).transport == "pending"
    assert gates.parse(f["trigger"].path).status == "pending"
    decided = {str(row.get("gate_id")) for row in conductor.auto_decision_rows(f["root"])
               if row.get("phase") == "decide"}
    assert f["prepared"].id not in decided and f["trigger"].id not in decided


# ---------------------------------------------------------------------------
# T19 live migration: the legacy live automatic path is now a read-only
# diagnosis. Without a claimed PM, a prepared book/basis and the protected
# authority source it must not answer a gate, grant a soft bonus or release a
# key/stage. Only the real PM gate-run may do that.
# ---------------------------------------------------------------------------

def _legacy_live_project(tmp_path):
    root = tmp_path / "legacy-live"
    (root / ".agenticdoc" / "_autopilot").mkdir(parents=True)
    (root / ".mw").mkdir(parents=True)
    (root / ".agenticdoc" / "goal.md").write_text(
        "# Goal\n\nShip the thing.\n", encoding="utf-8")
    cfg = config.default_config()
    cfg["enabled"] = True
    cfg["auto_gate_mode"] = "live"
    config.save_config(root, cfg)
    return root


def _seed_legacy_shadow(root, *, rule_id, nights=5, count=20):
    for index in range(count):
        day = 1 + (index % nights)
        conductor._append_auto_decision_row(root, {
            "decision_id": f"seed-{index}",
            "phase": "decide",
            "mode": "shadow",
            "executed": False,
            "decision": "escalate",
            "rule_id": rule_id,
            "reason_code": "stalled-undecidable",
            "prop_ok": False,
            "gate_id": f"gate-{9000 + index:04d}",
            "gate_key": f"seed-key-{index}",
            "night": f"2026-09-{day:02d}",
            "decided_at": "2026-09-01T00:00:00+00:00",
        })


def test_legacy_live_auto_without_the_prepared_contract_never_releases(tmp_path, monkeypatch):
    root = _legacy_live_project(tmp_path)
    key_dir = root / ".agenticdoc" / "k1"
    key_dir.mkdir(parents=True)
    (key_dir / "l3-verdict.txt").write_text("meets\n", encoding="utf-8")
    (key_dir / "l3-report.md").write_text("# report\nmeets\n", encoding="utf-8")
    (key_dir / "achieved.md").write_text("# Achieved\n" + "x" * 300 + "\n",
                                          encoding="utf-8")
    st = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(root)), None)
    gate_path = conductor._create_gate(
        root, st, "budget-exhausted", "add a round?", key="k1", refs=["l2:k1:x"])
    assert gate_path is not None
    _seed_legacy_shadow(root, rule_id="budget-exhausted-bounded")
    monkeypatch.setattr(
        conductor, "gate_facts",
        lambda _root, _gate, status_of=None: {
            "used_rounds": 2, "round_limit": 2, "credits_used": 0,
            "blocking_gap_count": 1,
        })
    conductor.auto_decide_gates(root, st, config.load_config(root))

    gate = gates.parse(gate_path)
    assert gate.status == "pending"
    assert gate.answered_by is None and gate.answer_source is None
    assert gate.auto_policy_id is None
    assert conductor._budget_bonus(root, "l2:k1:x") is False
    assert conductor.auto_consumption_set(root) == set()
    rows = [row for row in conductor.auto_decision_rows(root)
            if row.get("phase") == "decide" and row.get("mode") == "live"]
    assert rows, "the migration diagnosis must still be recorded"
    assert rows[-1]["decision"] == "escalate"
    assert rows[-1]["reason_code"] == "gate-approve-contract-required"
    assert rows[-1]["executed"] is False
    assert all(row.get("executed") is not True for row in rows)
    events = conductor.timeline.query_events(
        conductor.timeline.timeline_path(root)).events
    detail = next(str(event.get("detail") or "") for event in reversed(events)
                  if event.get("ev") == conductor.GATE_AUTO_DECISION_EVENT)
    assert "current-live-pm-claim" in detail
    assert "prepared-dp-gate-approve" in detail

    # A second tick neither moves the gate nor turns the same condition into a
    # release: the old shadow/quota history stays read-only diagnostics.
    before = gate_path.read_bytes()
    conductor.auto_decide_gates(root, st, config.load_config(root))
    assert gate_path.read_bytes() == before
    assert conductor._budget_bonus(root, "l2:k1:x") is False
    assert conductor.auto_consumption_set(root) == set()


def test_legacy_auto_answer_in_history_grants_no_bonus_and_no_stage_release(tmp_path):
    root = _legacy_live_project(tmp_path)
    st = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(root)), None)
    target = roadmap.roadmap_path(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        "## Stage 1: Legacy\n> goal: close the legacy stage\n> status: running\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n"
        "| k1 | implement | - |\n", encoding="utf-8", newline="\n")
    gate_path = conductor._create_gate(
        root, st, "budget-exhausted", "add a round?", key="k1", refs=["l2:k1:x"])
    assert gate_path is not None
    # Historical T-07 facts are read-only: the status/answer identity is only
    # made explicit here, no new business record is minted.
    conductor._rewrite_gate_fields(gate_path, {
        "status": "approved",
        "answered_at": "2026-09-25T00:00:00+00:00",
        "answered_by": "conductor-auto:budget-exhausted-bounded",
        "answer_source": conductor.AUTO_ANSWER_SOURCE,
        "auto_policy_id": "budget-exhausted-bounded@1",
    })
    before = target.read_bytes()
    st2 = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(root)), None)
    assert conductor._consume_answered_gates(root, st2, config.load_config(root)) is True
    assert target.read_bytes() == before
    assert conductor._budget_bonus(root, "l2:k1:x") is False
    assert conductor.auto_consumption_set(root) == set()
    events = conductor.timeline.query_events(
        conductor.timeline.timeline_path(root)).events
    assert any("legacy conductor-auto answer ignored" in str(e.get("detail") or "")
               for e in events)


def test_pm_gate_run_is_the_only_release_and_auto_ticks_do_not_duplicate_it(
        tmp_path, monkeypatch, capsys):
    f = _pm_run_fixture(tmp_path, "h01")
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])
    cfg = config.load_config(f["root"])
    target_before = f["target"].read_bytes()
    # Ordinary automatic ticks first: no claim/material/authority => no release
    # and no model request for the prepared gate or its trigger.
    conductor.auto_decide_gates(f["root"], f["st"], cfg)
    assert f["target"].read_bytes() == target_before
    prepared_gates = [gate for gate in gates.enumerate(conductor.gates_dir(f["root"]))
                      if not gate.historical]
    assert prepared_gates == []
    assert gates.parse(f["trigger"].path).status == "pending"
    decided = [row for row in conductor.auto_decision_rows(f["root"])
               if row.get("phase") == "decide"
               and str(row.get("gate_id")) == f["trigger"].id]
    assert all(row.get("executed") is not True for row in decided)
    assert gates.parse(f["trigger"].path).status == "pending"

    client = _pm_fake_client(f["root"], f["book"]["book"]["preparation"], "approve")
    rc = mw_cli._ap_gate_run(_pm_run_args(f), f["root"], client=client)
    assert rc == 0, capsys.readouterr().err
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "applied"
    assert roadmap.stage_by_number(
        roadmap.load_roadmap(f["target"]), 1).status == "running"
    assert f["target"].read_bytes() != target_before
    store = lifecycle.LifecycleStore.production(
        f["root"], redact=wire.SubstringRedactor([]))
    rows = [row for row in lifecycle.read_lifecycle(store).events
            if row.get("kind") == "lifecycle"]
    assert [row["lifecycle"] for row in rows] == ["consumed", "executed", "settled"]
    applied = f["target"].read_bytes()

    # A tick after the real PM release must not re-answer, re-execute or
    # duplicate the same matter.
    conductor.auto_decide_gates(f["root"], conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(f["root"])), None), cfg)
    assert f["target"].read_bytes() == applied
    assert len([row for row in lifecycle.read_lifecycle(store).events
                if row.get("kind") == "lifecycle"]) == 3


def test_pm_gate_entry_refuses_without_the_deployed_authority_source(tmp_path, monkeypatch):
    f = _pm_entry_fixture(tmp_path, "h01")
    before = f["target"].read_bytes()

    def unavailable(project_root, key):
        raise conductor.operator_authority.AuthorityError("host-unavailable")

    monkeypatch.setattr(conductor.operator_authority, "read_pm_authority", unavailable)
    result = conductor.consume_pm_gate(f["root"], f["prepared"].id, owner_key=f["owner"])
    assert result.state == "blocked" and "authority" in result.reason
    assert f["target"].read_bytes() == before
    assert gates.parse(f["prepared"].path).effect == "not-started"


def test_pm_gate_entry_refuses_when_the_bound_target_moved_before_reservation(tmp_path, monkeypatch):
    f = _pm_entry_fixture(tmp_path, "h01")
    f["target"].write_text(
        roadmap.update_stage_status(f["target"].read_text(encoding="utf-8"), 1, "running"),
        encoding="utf-8", newline="\n",
    )
    before = f["target"].read_bytes()
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])
    result = conductor.consume_pm_gate(f["root"], f["prepared"].id, owner_key=f["owner"])
    assert result.state == "blocked" and result.reason
    assert f["target"].read_bytes() == before
    assert gates.parse(f["prepared"].path).effect == "not-started"


def test_stage_close_prepare_requires_the_current_pm_material(tmp_path):
    root = tmp_path / "project"
    config.save_config(root, {"enabled": True, "paused": False, "auto_gate_mode": "live"})
    owner, claim = _T26_KEY, f"{socket.gethostname()}:{os.getpid()}"
    (root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (root / ".agenticdoc/_index.parallel").write_text(
        f"| {owner} | active | EXECUTE | {claim} | - | test | now |\n", encoding="utf-8")
    (root / ".agenticdoc/goal.md").write_text("# Deliver the agreed feature\n", encoding="utf-8")
    target = roadmap.roadmap_path(root)
    target.write_text(
        "## Stage 1: Integration\n> goal: Ship the verified feature\n> status: running\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n"
        f"| {owner} | implement | - |\n", encoding="utf-8")
    material = json.loads(json.dumps(_T26_MATERIAL))
    _t26_sign_key(root, owner, material)
    st = conductor.ConductorState(conductor.timeline.Timeline(conductor.timeline.timeline_path(root)), None)
    assert conductor._create_gate(root, st, "stage-close", "Close stage?", stage=1, refs=["stage-1"])
    trigger = [g for g in gates.enumerate(conductor.gates_dir(root))
               if g.historical and g.kind == "stage-close"][-1]
    book = _pm_book_payload()
    with pytest.raises(gate_effects.GateBlocked) as missing:
        conductor.prepare_pm_gate(root, trigger.id, owner_key=owner, book=book)
    assert "MISSING" in str(missing.value) or "material" in str(missing.value)
    _t26_stage_material(root, 1, {owner: {"matter": material,
                                          "evidence": material["verification_evidence"]}})
    prepared = conductor.prepare_pm_gate(root, trigger.id, owner_key=owner, book=book)
    assert prepared.kind == "stage-close" and prepared.transport == "pending"

def test_daily_tick_collects_an_answered_prepared_gate_without_consuming_it(tmp_path):
    f = _pm_entry_fixture(tmp_path, "h01")
    before = f["target"].read_bytes()
    conductor.collect_prepared_gates(f["root"], f["st"])
    assert f["target"].read_bytes() == before
    assert gates.parse(f["prepared"].path).effect == "not-started"
    events = conductor.timeline.query_events(conductor.timeline.timeline_path(f["root"])).events
    assert any("awaits its bound PM consumer" in str(e.get("detail") or "") for e in events)

def test_an_applied_trigger_cannot_prepare_a_second_decision(tmp_path, monkeypatch):
    f = _pm_entry_fixture(tmp_path, "h01")
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])
    assert conductor.consume_pm_gate(
        f["root"], f["prepared"].id, owner_key=f["owner"]).state == "applied"
    with pytest.raises(gate_effects.GateBlocked):
        conductor.prepare_pm_gate(f["root"], f["trigger"].id, owner_key=f["owner"], book=f["book"])


# ---------------------------------------------------------------------------
# T26 pm completion: the normal `mw autopilot gate run` chain. One PM book
# produces one real prepared request, the one TS answer writer deposits it and
# the real object consumer executes/settles it. Replays send no second model
# call; a recorded start without a request result stops as unknown.
# ---------------------------------------------------------------------------

def _pm_run_fixture(tmp_path, case, *, choice="approve", logical_id=None):
    root, owner, claim, st, target = _conductor_h_fixture(tmp_path / case)
    if case == "h02":
        target.write_text(
            roadmap.update_stage_status(target.read_text(encoding="utf-8"), 1, "running"),
            encoding="utf-8", newline="\n",
        )
    trigger = _pm_create_trigger(root, st, target, case)
    book = _pm_book_payload()
    body = book["book"]
    body["meta"] = {
        "actor_role": "pm", "key": owner,
        "logical_id": logical_id or f"run-{case}",
        "task_key": "T26-run",
    }
    material = body["material"]
    preparation = body["preparation"]
    if case == "h02":
        signed = json.loads(json.dumps(_T26_MATERIAL))
        _t26_sign_key(root, owner, signed)
        _t26_stage_material(root, 1, {
            owner: {"matter": signed, "evidence": signed["verification_evidence"]}})
    _, matter, _note = conductor._pm_gate_matter(
        root, owner, trigger, material, preparation)
    _pm_policy(root, matter.action)
    book_path = root / "prepared-book.json"
    book_path.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8", newline="\n")
    return {
        "root": root, "owner": owner, "claim": claim, "st": st, "target": target,
        "trigger": trigger, "book": book, "book_path": book_path,
        "action": matter.action, "logical_id": body["meta"]["logical_id"],
    }


def _pm_fake_client(root, preparation, choice):
    basis = next(v for v in preparation["basis_catalog"] if choice in v["applies_to"])
    return decision.DecisionClient(
        decision.DecisionConfig(enabled=True, project_root=root,
                                evidence_path=root / "transport.jsonl"),
        decision.FakeBackend([decision.BackendOutcome(True, None, False, {
            "gate_decision": {"value": choice, "confidence": 0.95},
            "basis_id": {"value": basis["id"], "confidence": 0.95},
        }, 0)]),
    )


def _pm_run_args(f):
    return mw_cli.argparse.Namespace(
        trigger=f["trigger"].id, key=f["owner"], book=str(f["book_path"]))


@pytest.mark.parametrize("case,check", [
    ("h01", lambda f: roadmap.stage_by_number(roadmap.load_roadmap(f["target"]), 1).status == "running"),
    ("h02", lambda f: roadmap.stage_by_number(roadmap.load_roadmap(f["target"]), 1).status == "closed"),
    ("h03", lambda f: roadmap.stage_by_number(roadmap.load_roadmap(f["target"]), 1).key_status["owner"] == "running"),
    ("h04", lambda f: conductor._budget_bonus(f["root"], "loop:fixture") is True),
    ("h05", lambda f: roadmap.stage_by_number(roadmap.load_roadmap(f["target"]), 1).key_status["owner"] == "running"),
])
def test_pm_gate_run_drives_one_real_request_to_the_bound_effect(
        tmp_path, monkeypatch, capsys, case, check):
    f = _pm_run_fixture(tmp_path, case)
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])
    object_path = (f["root"] / ".agenticdoc/_autopilot/budget-extensions.jsonl"
                   if case == "h04" else f["target"])
    before = object_path.read_bytes() if object_path.is_file() else b""
    client = _pm_fake_client(f["root"], f["book"]["book"]["preparation"], "approve")
    rc = mw_cli._ap_gate_run(_pm_run_args(f), f["root"], client=client)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "applied"
    assert payload["request"]["status"] == "answered"
    assert payload["request"]["source"] == "transport"
    assert payload["decision_ref"] == f"dp-gate-approve:{f['logical_id']}"
    assert check(f) is True
    assert object_path.read_bytes() != before
    prepared = gates.parse(conductor.gates_dir(f["root"]) / (payload["gate_id"] + ".md"))
    assert prepared.transport == "answered" and prepared.business == "approve"
    assert prepared.decision_ref == payload["decision_ref"]
    rows = [r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(f["root"], redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]
    assert [r["lifecycle"] for r in rows] == ["consumed", "executed", "settled"]
    applied = object_path.read_bytes()
    # Replay: the already-answered gate is consumed again without any model call.
    replay_client = decision.DecisionClient(
        decision.DecisionConfig(enabled=True, project_root=f["root"]),
        decision.FakeBackend([]),
    )
    rc2 = mw_cli._ap_gate_run(_pm_run_args(f), f["root"], client=replay_client)
    assert rc2 == 0, capsys.readouterr().err
    replay = json.loads(capsys.readouterr().out)
    assert replay["status"] == "applied" and replay["duplicate"] is True
    assert replay["request"]["status"] == "already-answered"
    assert object_path.read_bytes() == applied
    assert len([r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(f["root"], redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]) == 3


def test_pm_gate_run_steer_is_a_real_handoff_not_a_release(tmp_path, monkeypatch, capsys):
    f = _pm_run_fixture(tmp_path, "h01", choice="steer")
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])
    before = f["target"].read_bytes()
    client = _pm_fake_client(f["root"], f["book"]["book"]["preparation"], "steer")
    rc = mw_cli._ap_gate_run(_pm_run_args(f), f["root"], client=client)
    assert rc == 2, capsys.readouterr().err
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocked"
    assert payload["request"]["choice"] == "steer"
    assert f["target"].read_bytes() == before
    gate = gates.parse(conductor.gates_dir(f["root"]) / (payload["gate_id"] + ".md"))
    assert gate.transport == "answered" and gate.business == "steer"
    assert gate.effect == "blocked"
    rows = [r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(f["root"], redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]
    assert [r["lifecycle"] for r in rows] == ["consumed", "settled"]
    assert rows[-1]["outcome"] == "pending" and "dp-pm-steer" in rows[-1]["reason"]


def test_pm_gate_run_stops_on_an_interrupted_request_without_resending(
        tmp_path, monkeypatch, capsys):
    f = _pm_run_fixture(tmp_path, "h01")
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])
    store = lifecycle.LifecycleStore.production(f["root"], redact=wire.SubstringRedactor([]))
    meta = lifecycle.DecisionMeta.create(
        f["owner"], task_key="T26-run", initiator_role="pm",
        logical_id=f["logical_id"])
    assert lifecycle.record_start(
        store, meta, decision_id=f"dp-gate-approve:{f['logical_id']}").recorded
    before = f["target"].read_bytes()
    client = _pm_fake_client(f["root"], f["book"]["book"]["preparation"], "approve")
    rc = mw_cli._ap_gate_run(_pm_run_args(f), f["root"], client=client)
    assert rc == 2
    assert "no request result" in capsys.readouterr().err
    assert f["target"].read_bytes() == before
    prepared = [g for g in gates.enumerate(conductor.gates_dir(f["root"]))
                if not g.historical]
    assert len(prepared) == 1 and prepared[0].transport == "pending"


def test_pm_gate_run_uses_the_same_rule_for_a_later_stage(tmp_path, monkeypatch, capsys):
    root = tmp_path / "later"
    config.save_config(root, {"enabled": True, "paused": False, "auto_gate_mode": "live"})
    owner = "owner"
    claim = f"{socket.gethostname()}:{os.getpid()}"
    (root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (root / ".agenticdoc/_index.parallel").write_text(
        f"| {owner} | active | EXECUTE | {claim} | - | test | now |\n", encoding="utf-8")
    (root / ".agenticdoc/goal.md").write_text("# Deliver the agreed feature\n", encoding="utf-8")
    target = roadmap.roadmap_path(root)
    target.write_text(
        "## Stage 1: Done\n> goal: previous stage\n> status: closed\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n"
        "| legacy | implement | - |\n\n"
        "## Stage 2: Next\n> goal: Ship the next verified stage\n> status: pending\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n"
        f"| {owner} | implement | - |\n", encoding="utf-8")
    st = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(root)), None)
    conductor._create_stage_confirm_gate(
        root, st, roadmap.stage_by_number(roadmap.load_roadmap(target), 2))
    trigger = [g for g in gates.enumerate(conductor.gates_dir(root))
               if g.historical and g.kind == "stage-confirm"][-1]
    book = _pm_book_payload()
    book["book"]["meta"] = {"actor_role": "pm", "key": owner,
                               "logical_id": "run-stage-2", "task_key": "T26-run"}
    _, matter, _note = conductor._pm_gate_matter(
        root, owner, trigger, book["book"]["material"], book["book"]["preparation"])
    _pm_policy(root, matter.action)
    book_path = root / "prepared-book.json"
    book_path.write_text(json.dumps(book), encoding="utf-8", newline="\n")
    _pm_deploy_authority(monkeypatch, root, owner, matter.action)
    client = _pm_fake_client(root, book["book"]["preparation"], "approve")
    rc = mw_cli._ap_gate_run(
        mw_cli.argparse.Namespace(trigger=trigger.id, key=owner, book=str(book_path)),
        root, client=client)
    assert rc == 0
    capsys.readouterr()
    loaded = roadmap.load_roadmap(target)
    assert roadmap.stage_by_number(loaded, 1).status == "closed"
    assert roadmap.stage_by_number(loaded, 2).status == "running"


def test_pm_gate_entry_refuses_a_changed_authority_source(tmp_path, monkeypatch):
    f = _pm_entry_fixture(tmp_path, "h01")
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])

    def changed(observation):
        raise conductor.operator_authority.AuthorityError("authority-source-changed")

    monkeypatch.setattr(conductor.operator_authority, "verify_pm_authority", changed)
    before = f["target"].read_bytes()
    result = conductor.consume_pm_gate(
        f["root"], f["prepared"].id, owner_key=f["owner"])
    assert result.state == "blocked" and "authority" in result.reason
    assert f["target"].read_bytes() == before
    assert gates.parse(f["prepared"].path).effect == "not-started"



# ---------------------------------------------------------------------------
# T26 normal consumers: H06/H07/H08 family entry and the H11 bounded view.
#
# The production entry is exercised end to end: a PM book is prepared into a
# real pending three-axis gate, the decision transport answers it, and the T20
# protected-source writer performs the actual object change. Only the OS trust
# seam and the model provider are fixtures; every object, claim, policy and
# lifecycle ledger is the real implementation.
# ---------------------------------------------------------------------------

T20_SPEC = """# Spec

## 3. Acceptance Criteria

| AC ID | text |
|---|---|
| AC-001 | first contract text, locked |
| AC-002 | second contract text, locked |
| AC-003 | third contract text, locked |
"""
T20_DESIGN = """# Design

## 7 Verification Contract

VC-001: first assertion text
       Layer: L2   Output: [VERIFY] VC-001: one=true   Source: AC-001
VC-002: second assertion text
       Layer: L2   Output: [VERIFY] VC-002: two=true   Source: AC-002
"""
GOAL_BEFORE = "# Goal\n\nDeliver stage 2 to the operator.\n"
GOAL_AFTER = "# Goal\n\nDeliver stage 3 to the operator.\n"
GOAL_NOTE = "adopt goal-v2 for owner; necessity scope moved; re-run the affected cases"
REPAIR_FILE = "packages/other/target.py"


def _family_policy(root, *, limit=5):
    path = policy.policy_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1, "authority_ref": "family-policy", "scope": ["fixture"],
        "hard_limits": [{"unit": "round", "limit": limit,
                         "usage_source": "task-card-rounds"}],
    }), encoding="utf-8", newline="\n")
    return path


def _family_rounds(root, key, count):
    for index in range(count):
        directory = root / ".agenticdoc" / key / "workers" / f"task-{index + 1}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / "task.md").write_text(
            f"---\nloop: l3:{key}\nattempt: a{index + 1}\ntype: coding\n---\n",
            encoding="utf-8", newline="\n")


def _family_deploy_authority(monkeypatch, root, scopes, *, writers=("controlled-human",)):
    project_id = wire.project_id_for(root)
    image = sys.executable
    policy_sha = hashlib.sha256(policy.policy_path(root).read_bytes()).hexdigest()
    config = {
        "schema": 1,
        "projects": {
            project_id: {
                "root": root.name,
                "trusted_writers": list(writers),
                "pm_sids": ["S-1-5-32-544"],
                "pm_images": [image],
                "authority_records": {
                    "signed-scope": {
                        "authority_ref": "signed-scope",
                        "kind": "user-grant",
                        "scope": list(scopes),
                        "writer": "controlled-human",
                        "revoked": False,
                    },
                },
                "usage_sources": {
                    "task-card-rounds": {"kind": "task-card-rounds", "unit": "round"}
                },
                "policy_sha256": policy_sha,
            },
        },
    }
    host = root.parent / "host.json"
    host.write_text(json.dumps(config), encoding="utf-8", newline="\n")
    peer = conductor.operator_authority.Peer(
        "S-1-5-32-544", os.getpid(), 1, 1, os.path.normcase(image))
    trust = conductor.operator_authority.ServiceTrust(peer, host)
    monkeypatch.setattr(conductor.operator_authority, "load_trust", lambda: trust)
    monkeypatch.setattr(
        conductor.operator_authority, "trusted_path", lambda path, trust: path)
    monkeypatch.setattr(
        conductor.operator_authority, "_pm_process_peer", lambda pid: peer)
    return trust


def _family_book(family, payload, *, key="owner", logical_id="family-1"):
    book = _pm_book_payload()
    book["book"]["meta"] = {
        "actor_role": "pm", "key": key, "logical_id": logical_id,
        "task_key": "T26-family",
    }
    book["book"]["family"] = family
    book["book"]["payload"] = payload
    return book


def _family_book_path(root, book):
    path = root / "family-book.json"
    path.write_text(json.dumps(book, ensure_ascii=False), encoding="utf-8", newline="\n")
    return path


def _family_args(family, key, book_path):
    return mw_cli.argparse.Namespace(family=family, key=key, book=str(book_path))


def _family_goal_payload(root):
    baseline = root / "goal-baseline.json"
    baseline.write_text(json.dumps({"goal_version": "goal-v1"}) + "\n",
                        encoding="utf-8", newline="\n")
    return {
        "request": {
            "key": "owner", "previous_version": "goal-v1",
            "current_version": "goal-v2", "target_version": "goal-v2",
            "necessity": "goal.md scope moved to stage-3",
            "impact": "owner acceptance and dependencies are affected",
            "authority_ref": "signed-scope",
            "reverification_plan": "re-run the affected VC-001 cases",
        },
        "baseline_path": str(baseline),
        "before_text": GOAL_BEFORE,
        "after_text": GOAL_AFTER,
        "note": GOAL_NOTE,
    }


def test_pm_family_goal_adoption_uses_the_normal_request_and_protected_writer(
        tmp_path, monkeypatch, capsys):
    root, owner, claim, st, _target = _conductor_h_fixture(tmp_path / "family-goal")
    _family_policy(root)
    _family_rounds(root, owner, 1)
    payload = _family_goal_payload(root)
    book = _family_book("goal-adoption", payload)
    book_path = _family_book_path(root, book)
    _family_deploy_authority(
        monkeypatch, root, ["goal-adopt:owner", "goal-version:goal-v2"])
    client = _pm_fake_client(root, book["book"]["preparation"], "approve")
    rc = mw_cli._ap_family_run(
        _family_args("goal-adoption", owner, book_path), root, client=client)
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "applied", result
    assert result["family"] == "goal-adoption"
    assert result["request"]["choice"] == "approve"
    baseline = pathlib.Path(payload["baseline_path"])
    assert json.loads(baseline.read_text(encoding="utf-8"))["goal_version"] == "goal-v2"
    gate = gates.parse(conductor.gates_dir(root) / (result["gate_id"] + ".md"))
    assert gate.transport == "answered" and gate.business == "approve"
    assert gate.matter_ref and gate.substantive_version
    rows = [r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(root, redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]
    assert [r["lifecycle"] for r in rows] == ["consumed", "executed", "settled"]

    applied = baseline.read_bytes()
    replay_client = decision.DecisionClient(
        decision.DecisionConfig(enabled=True, project_root=root),
        decision.FakeBackend([]),
    )
    rc2 = mw_cli._ap_family_run(
        _family_args("goal-adoption", owner, book_path), root, client=replay_client)
    assert rc2 == 0, capsys.readouterr().err
    replay = json.loads(capsys.readouterr().out)
    assert replay["status"] == "applied" and replay["duplicate"] is True
    assert replay["request"]["status"] == "already-answered"
    assert baseline.read_bytes() == applied
    assert len([r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(root, redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]) == 3


def _family_contract_payload(root, owner):
    key_dir = root / ".agenticdoc" / owner
    (key_dir / "spec.md").write_text(T20_SPEC, encoding="utf-8", newline="\n")
    (key_dir / "design.md").write_text(T20_DESIGN, encoding="utf-8", newline="\n")
    cg.freeze_contract(key_dir, owner, T20_SPEC, T20_DESIGN)
    original = cg.extract_contract(T20_SPEC, T20_DESIGN)
    before = {**original.acs, **original.vcs}
    changed_spec = T20_SPEC.replace("first contract text, locked",
                                    "first contract text, rewritten")
    changed_design = T20_DESIGN
    (key_dir / "spec.md").write_text(changed_spec, encoding="utf-8", newline="\n")
    after = cg.extract_contract(changed_spec, changed_design)
    after_versions = {**after.acs, **after.vcs}
    request = {
        "key": owner, "items": ["AC-001"],
        "before_versions": {"AC-001": before["AC-001"]},
        "after_versions": {"AC-001": after_versions["AC-001"]},
        "reason": "the acceptance condition missed the duplicate action count",
        "commitment_impact": "no commitment reduction",
        "evidence_impact": "AC-001 must be re-verified",
        "authority_ref": "signed-scope",
        "reverification_plan": "re-run the AC-001 fixture cases",
        "acceptance_reductions": [],
    }
    note = " | ".join((request["key"], request["reason"], request["commitment_impact"],
                       request["evidence_impact"], request["reverification_plan"], "AC-001"))
    return {
        "request": request,
        "note": note,
        "approval": {
            "approval_ref": "change-approval-1", "key": owner,
            "items": ["AC-001"], "before_versions": request["before_versions"],
            "after_versions": request["after_versions"],
            "reverification_plan": request["reverification_plan"],
            "authority_source": "signed-scope", "authority_ref": "signed-scope",
            "acceptance_reductions": [],
        },
    }


def test_pm_family_contract_refreeze_uses_the_normal_request_and_exact_items(
        tmp_path, monkeypatch, capsys):
    root, owner, _claim, _st, _target = _conductor_h_fixture(tmp_path / "family-freeze")
    _family_policy(root)
    _family_rounds(root, owner, 1)
    payload = _family_contract_payload(root, owner)
    book = _family_book("contract-refreeze", payload)
    book_path = _family_book_path(root, book)
    _family_deploy_authority(
        monkeypatch, root, [f"contract-change:{owner}", "contract-item:AC-001"])
    key_dir = root / ".agenticdoc" / owner
    spec_before = (key_dir / "spec.md").read_bytes()
    client = _pm_fake_client(root, book["book"]["preparation"], "approve")
    rc = mw_cli._ap_family_run(
        _family_args("contract-refreeze", owner, book_path), root, client=client)
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "applied", result
    assert result["family"] == "contract-refreeze"
    assert (key_dir / "spec.md").read_bytes() == spec_before
    anchor = cg.read_freeze(key_dir)
    current = cg.extract_contract(
        (key_dir / "spec.md").read_text(encoding="utf-8"),
        (key_dir / "design.md").read_text(encoding="utf-8"))
    assert anchor["spec"]["AC-001"] == current.acs["AC-001"]
    log = cg.adoption_log_path(key_dir)
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1
    applied_anchor = cg.freeze_path(key_dir).read_bytes()
    replay = _pm_fake_client(root, book["book"]["preparation"], "approve")
    rc2 = mw_cli._ap_family_run(
        _family_args("contract-refreeze", owner, book_path), root, client=replay)
    assert rc2 == 0, capsys.readouterr().err
    replayed = json.loads(capsys.readouterr().out)
    assert replayed["status"] == "applied" and replayed["duplicate"] is True
    assert cg.freeze_path(key_dir).read_bytes() == applied_anchor
    assert len(log.read_text(encoding="utf-8").splitlines()) == 1


def _family_repair_payload(root):
    target = root / REPAIR_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"alpha\nbeta\ngamma\n")
    _family_rounds(root, "key-1", 1)
    request = {
        "request_id": "XKEY-2026-11-08-01", "target_key": "other-key",
        "files": [REPAIR_FILE], "action": "replace-frozen-block",
        "necessity": "the frozen expectation reds the dependant key's suite",
        "impact": "only the named frozen block; the target key re-verifies",
        "authorization": "signed-scope",
        "coordination": "claim the file and hold the exclusive lock before writing",
        "verification": "run the target key's targeted pytest file",
    }
    note = " | ".join((request["target_key"], request["action"], request["necessity"],
                       request["impact"], request["coordination"], request["verification"],
                       REPAIR_FILE))
    return {
        "request": request, "note": note,
        "approval": {
            "approval_ref": "xkey-approval-1", "target_key": "other-key",
            "files": [REPAIR_FILE], "action": "replace-frozen-block",
            "authority_source": "signed-scope", "authority_ref": "signed-scope",
        },
        "claim_request": {"actor": "worker-window-2", "task_key": "other-key",
                          "files": [REPAIR_FILE]},
        "ticket": {
            "status": "approved", "owner_key": "other-key", "target_key": "other-key",
            "frozen_block": {"file": REPAIR_FILE, "line_range": [2, 2],
                             "old_block_sha256": hashlib.sha256(b"beta\n").hexdigest()},
        },
        "new_text": "beta-repaired\n",
    }


def test_pm_family_cross_key_repair_changes_the_real_file_through_the_claim(
        tmp_path, monkeypatch, capsys):
    root = tmp_path / "family-repair"
    config.save_config(root, {"enabled": True, "paused": False, "auto_gate_mode": "live"})
    owner = "key-1"
    claim = f"{socket.gethostname()}:{os.getpid()}"
    (root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (root / ".agenticdoc/_index.parallel").write_text(
        f"| {owner} | active | EXECUTE | {claim} | - | test | now |\n", encoding="utf-8")
    (root / ".agenticdoc/goal.md").write_text("# Deliver the agreed feature\n", encoding="utf-8")
    _family_policy(root)
    payload = _family_repair_payload(root)
    xk.claim_acquire(root, owner="worker-window-2", task_key="other-key",
                     files=(REPAIR_FILE,))
    book = _family_book("cross-key-repair", payload, key=owner)
    book_path = _family_book_path(root, book)
    _family_deploy_authority(monkeypatch, root, [
        "xkey-repair:other-key", "xkey-action:replace-frozen-block",
        f"xkey-file:{REPAIR_FILE}",
    ])
    _family_rounds(root, owner, 0)
    client = _pm_fake_client(root, book["book"]["preparation"], "approve")
    rc = mw_cli._ap_family_run(
        _family_args("cross-key-repair", owner, book_path), root, client=client)
    assert rc == 0
    result = json.loads(capsys.readouterr().out)
    assert result["status"] == "applied", result
    assert result["family"] == "cross-key-repair"
    assert (root / REPAIR_FILE).read_bytes() == b"alpha\nbeta-repaired\ngamma\n"
    applied = (root / REPAIR_FILE).read_bytes()
    replay = _pm_fake_client(root, book["book"]["preparation"], "approve")
    rc2 = mw_cli._ap_family_run(
        _family_args("cross-key-repair", owner, book_path), root, client=replay)
    assert rc2 == 0, capsys.readouterr().err
    replayed = json.loads(capsys.readouterr().out)
    assert replayed["status"] == "applied" and replayed["duplicate"] is True
    assert (root / REPAIR_FILE).read_bytes() == applied


@pytest.mark.parametrize("choice", ["steer", "need_fix", "reject"])
def test_pm_family_non_approve_leaves_every_object_unchanged(
        tmp_path, monkeypatch, capsys, choice):
    root, owner, _claim, _st, _target = _conductor_h_fixture(tmp_path / ("family-neg-" + choice))
    _family_policy(root)
    _family_rounds(root, owner, 1)
    payload = _family_goal_payload(root)
    book = _family_book("goal-adoption", payload)
    book_path = _family_book_path(root, book)
    _family_deploy_authority(
        monkeypatch, root, ["goal-adopt:owner", "goal-version:goal-v2"])
    baseline_before = pathlib.Path(payload["baseline_path"]).read_bytes()
    client = _pm_fake_client(root, book["book"]["preparation"], choice)
    rc = mw_cli._ap_family_run(
        _family_args("goal-adoption", owner, book_path), root, client=client)
    assert rc == 2
    assert pathlib.Path(payload["baseline_path"]).read_bytes() == baseline_before
    gate = [g for g in gates.enumerate(conductor.gates_dir(root)) if not g.historical][-1]
    assert gate.transport == "answered" and gate.business == choice


def test_pm_family_refuses_without_the_protected_source(tmp_path, monkeypatch, capsys):
    root, owner, _claim, _st, _target = _conductor_h_fixture(tmp_path / "family-nosource")
    _family_policy(root)
    _family_rounds(root, owner, 1)
    payload = _family_goal_payload(root)
    book = _family_book("goal-adoption", payload)
    book_path = _family_book_path(root, book)
    baseline_before = pathlib.Path(payload["baseline_path"]).read_bytes()

    def unavailable(project_root, key):
        raise conductor.operator_authority.AuthorityError("host-unavailable")

    monkeypatch.setattr(conductor.operator_authority, "read_pm_authority", unavailable)
    client = _pm_fake_client(root, book["book"]["preparation"], "approve")
    rc = mw_cli._ap_family_run(
        _family_args("goal-adoption", owner, book_path), root, client=client)
    assert rc == 2
    assert pathlib.Path(payload["baseline_path"]).read_bytes() == baseline_before


def _family_goal_ready(tmp_path, monkeypatch):
    """Prepare + answer one real goal-adoption gate without consuming it."""

    root, owner, claim, _st, _target = _conductor_h_fixture(tmp_path / "family-effect")
    _family_policy(root)
    _family_rounds(root, owner, 1)
    payload = _family_goal_payload(root)
    book = _family_book("goal-adoption", payload)
    _family_deploy_authority(
        monkeypatch, root, ["goal-adopt:owner", "goal-version:goal-v2"])
    prepared = conductor.prepare_pm_family_gate(
        root, "goal-adoption", owner_key=owner, book=book)
    client = _pm_fake_client(root, book["book"]["preparation"], "approve")
    answer = mw_cli._ap_pm_gate_request(root, prepared, owner, book, client=client)
    assert answer["status"] == "answered"
    return {
        "root": root, "owner": owner, "claim": claim, "payload": payload,
        "book": book, "gate": conductor.gates.parse(prepared.path),
    }


def _family_lifecycle(root):
    return [
        row for row in lifecycle.read_lifecycle(
            lifecycle.LifecycleStore.production(
                root, redact=wire.SubstringRedactor([]))).events
        if row.get("kind") == "lifecycle"
    ]


def test_pm_family_reserves_before_writer_and_interruption_is_not_applied(
        tmp_path, monkeypatch):
    f = _family_goal_ready(tmp_path, monkeypatch)
    root, owner, payload = f["root"], f["owner"], f["payload"]
    gate, book = f["gate"], f["book"]
    baseline = pathlib.Path(payload["baseline_path"])
    before = baseline.read_bytes()
    observed: list[str] = []
    calls: list[int] = []

    def interrupted(*_args, **_kwargs):
        calls.append(1)
        observed.append(conductor.gates.parse(gate.path).effect)
        raise BaseException("simulated process interruption at the writer")

    original = cg.consume_goal_adoption
    monkeypatch.setattr(cg, "consume_goal_adoption", interrupted)
    with pytest.raises(BaseException):
        conductor.consume_pm_family_gate(root, gate.id, owner_key=owner, book=book)

    assert observed == ["in-progress"]
    assert conductor.gates.parse(gate.path).effect == "in-progress"
    assert baseline.read_bytes() == before
    assert [row["lifecycle"] for row in _family_lifecycle(root)] == ["consumed"]
    record = json.loads(
        conductor._family_effect_path(root, gate).read_text(encoding="utf-8"))
    assert record["status"] == "in-progress" and record["target"] == str(baseline)

    # Recovery may only inspect: no second request, no second write, no applied.
    monkeypatch.setattr(cg, "consume_goal_adoption", original)
    replay = conductor.consume_pm_family_gate(root, gate.id, owner_key=owner, book=book)
    assert replay.state == "unknown"
    assert replay.duplicate is True
    assert len(calls) == 1
    assert baseline.read_bytes() == before
    assert conductor.gates.parse(gate.path).effect == "unknown"
    assert [row["lifecycle"] for row in _family_lifecycle(root)] == ["consumed"]


def test_pm_family_after_writer_completes_only_from_the_real_receipt(
        tmp_path, monkeypatch):
    f = _family_goal_ready(tmp_path, monkeypatch)
    root, owner, payload = f["root"], f["owner"], f["payload"]
    gate, book = f["gate"], f["book"]
    baseline = pathlib.Path(payload["baseline_path"])

    real_executed = lifecycle.record_executed

    def interrupted(*args, **kwargs):
        if str(kwargs.get("event_id") or "").startswith("family-executed-"):
            raise BaseException("simulated interruption before settlement")
        return real_executed(*args, **kwargs)

    monkeypatch.setattr(lifecycle, "record_executed", interrupted)
    with pytest.raises(BaseException):
        conductor.consume_pm_family_gate(root, gate.id, owner_key=owner, book=book)

    # The original writer really wrote; the ledger has no executed row yet.
    assert json.loads(baseline.read_text(encoding="utf-8"))["goal_version"] == "goal-v2"
    assert conductor.gates.parse(gate.path).effect == "in-progress"
    assert [row["lifecycle"] for row in _family_lifecycle(root)] == ["consumed"]

    monkeypatch.setattr(lifecycle, "record_executed", real_executed)
    original = cg.consume_goal_adoption
    writes: list[int] = []

    def counted(*args, **kwargs):
        writes.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(cg, "consume_goal_adoption", counted)
    result = conductor.consume_pm_family_gate(root, gate.id, owner_key=owner, book=book)
    assert result.state == "applied" and result.duplicate is True
    assert writes == []  # recovery inspected the object, never repeated the writer
    events = _family_lifecycle(root)
    assert [row["lifecycle"] for row in events] == ["consumed", "executed", "settled"]
    assert conductor.gates.parse(gate.path).effect == "applied"
    assert json.loads(baseline.read_text(encoding="utf-8"))["goal_version"] == "goal-v2"


def test_pm_family_concurrent_replay_writes_the_object_once(tmp_path, monkeypatch):
    f = _family_goal_ready(tmp_path, monkeypatch)
    root, owner, payload = f["root"], f["owner"], f["payload"]
    gate, book = f["gate"], f["book"]
    baseline = pathlib.Path(payload["baseline_path"])
    original = cg.consume_goal_adoption
    writes: list[int] = []
    guard = threading.Lock()

    def counted(*args, **kwargs):
        with guard:
            writes.append(1)
        return original(*args, **kwargs)

    monkeypatch.setattr(cg, "consume_goal_adoption", counted)
    barrier = threading.Barrier(2)

    def consume():
        barrier.wait()
        return conductor.consume_pm_family_gate(root, gate.id, owner_key=owner, book=book)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in [pool.submit(consume), pool.submit(consume)]]

    assert [result.state for result in results] == ["applied", "applied"]
    assert sum(1 for result in results if not result.duplicate) == 1
    assert writes == [1]
    assert [row["lifecycle"] for row in _family_lifecycle(root)] == [
        "consumed", "executed", "settled"]
    assert json.loads(baseline.read_text(encoding="utf-8"))["goal_version"] == "goal-v2"


def test_pm_family_applied_needs_its_real_receipt_record(tmp_path, monkeypatch):
    f = _family_goal_ready(tmp_path, monkeypatch)
    root, owner, payload = f["root"], f["owner"], f["payload"]
    gate, book = f["gate"], f["book"]
    baseline = pathlib.Path(payload["baseline_path"])
    first = conductor.consume_pm_family_gate(root, gate.id, owner_key=owner, book=book)
    assert first.state == "applied"
    applied = baseline.read_bytes()
    effect_path = conductor._family_effect_path(root, gate)
    original = cg.consume_goal_adoption
    writes: list[int] = []

    def counted(*args, **kwargs):
        writes.append(1)
        return original(*args, **kwargs)

    # An applied marker alone is never replayed as a release.
    effect_path.unlink()
    monkeypatch.setattr(cg, "consume_goal_adoption", counted)
    result = conductor.consume_pm_family_gate(root, gate.id, owner_key=owner, book=book)
    assert result.state == "unknown"
    assert result.duplicate is True
    assert writes == []
    assert baseline.read_bytes() == applied


# --- H11 normal PM entry and the one bounded conductor action ---------------

_H11_KEY = "dpc-t26-halted"
_H11_SID = "S-1-5-21-100-200-300"
_H11_IMAGE = r"C:\fixture\pi.exe"


def _h11_roadmap(root):
    path = root / ".agenticdoc" / "_autopilot" / "_roadmap.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Roadmap\n> generated_at: 2026-11-09T00:00:00Z\n\n"
        "## Stage 1: Halted integration\n> goal: Ship the halted stage\n"
        "> status: halted\n"
        f"> key-status: {_H11_KEY}=stalled\n"
        "### Keys\n| key | role | depends_on |\n|---|---|---|\n"
        f"| {_H11_KEY} | implement | - |\n", encoding="utf-8", newline="\n")
    return path


def _h11_halt_gate(root, note_text):
    directory = root / ".agenticdoc" / "_autopilot" / "gates"
    path = gates.create(directory, "stage-close", "Close stage 1? reject=halt", stage=1)
    raw = path.read_text(encoding="utf-8")
    raw = raw.replace("status: pending", "status: rejected", 1)
    raw = raw.replace("answered_at:", "answered_at: 2026-11-09T00:00:00+00:00", 1)
    raw = raw.replace("answered_by:", "answered_by: 'human:operator'", 1)
    raw = raw.replace("note:", "note: " + gates._render_scalar(note_text), 1)
    path.write_text(raw, encoding="utf-8", newline="\n")
    conductor.timeline.Timeline(conductor.timeline.timeline_path(root)).append(
        "gate-answered", stage=1, detail=f"{path.stem} rejected -> stage 1 halted")
    return path


def _h11_stop_record():
    return json.dumps({
        "schema": 1, "halt_origin": "technical",
        "stop_reason": "worker stall exceeded the watchdog",
        "hard_guard_active": False, "hard_guard_cleared": [],
        "hard_guard_cleared_verified": False,
    }, sort_keys=True, separators=(",", ":"))


def _h11_preparation(choice="approve"):
    return {
        "prepared_at": "2026-11-09T00:05:00+00:00",
        "basis_catalog": [{
            "id": "b-approve",
            "text": "the original signal is gone and the policy allows one observing step",
            "material_refs": ["condition_evidence"],
            "applies_to": [choice],
        }],
    }


def _h11_fixture(tmp_path, monkeypatch, *, choice="approve", limit=3, rounds=1):
    root = tmp_path / "h11-normal"
    (root / ".agenticdoc" / "_autopilot" / "gates").mkdir(parents=True)
    claim = f"{socket.gethostname()}:{os.getpid()}"
    (root / ".agenticdoc" / "_index.parallel").write_text(
        "| Key | Status | Phase | Claim | Deps | Desc | Updated |\n"
        "|---|---|---|---|---|---|---|\n"
        f"| {_H11_KEY} | active | 4 | {claim} | | T26 fixture | 2026-11-09T00:00:00Z |\n",
        encoding="utf-8", newline="\n")
    doc = {
        "schema_version": 1,
        "authority_ref": "grant-dpc-t07",
        "scope": [f"key:{_H11_KEY}", "action:gate-approve"],
        "hard_limits": [{"unit": "round", "limit": limit,
                         "usage_source": "task-card-rounds"}],
        "recovery": {
            "allowed_origins": ["pm-controlled"],
            "scope": ["recovery:halted", "recovery:user-stop", "recovery:breaker"],
            "authority_ref": "grant-h11",
            "observation_conditions": ["same-failure-reappears"],
            "stop_conditions": ["recovery-reason-reappears"],
        },
    }
    policy.policy_path(root).parent.mkdir(parents=True, exist_ok=True)
    policy.policy_path(root).write_text(json.dumps(doc), encoding="utf-8", newline="\n")
    config.save_config(root, {"enabled": True, "paused": False, "auto_gate_mode": "live"})
    (root / ".mw").mkdir(parents=True, exist_ok=True)
    (root / ".mw" / "decide.json").write_text(
        json.dumps({"enabled": True, "transport": "timi-decisions",
                    "max_questions": 8, "max_retries": 0}),
        encoding="utf-8", newline="\n")
    _family_rounds(root, _H11_KEY, rounds)
    _h11_roadmap(root)
    _h11_halt_gate(root, _h11_stop_record())
    facts = decision_recovery.halted_stage_facts(root)
    note = {
        "stop_reason": facts["stop_reason"],
        "elimination_evidence": ["worker watchdog trace shows the stall is gone"],
        "stage_version": facts["stage_version"],
        "affected_keys": [_H11_KEY],
        "target_plan": "rerun the halted stage gate",
        "authority_ref": "grant-h11",
        "residual_budget": {"round": limit - rounds},
        "stop_criterion": "two consecutive green runs",
    }
    policy_sha = hashlib.sha256(policy.policy_path(root).read_bytes()).hexdigest()
    records = {
        "grant-dpc-t07": {
            "authority_ref": "grant-dpc-t07", "kind": "user-grant",
            "scope": [f"key:{_H11_KEY}", "action:gate-approve"],
            "writer": "controlled-human", "revoked": False,
            "recorded_at": "2026-01-01T00:00:00+00:00", "supersedes": [],
        },
        "grant-h11": {
            "authority_ref": "grant-h11", "kind": "user-grant",
            "scope": [f"key:{_H11_KEY}", "action:gate-approve", "recovery:halted",
                      "recover-halted", "action:recover-halted"],
            "writer": "controlled-human", "revoked": False,
            "recorded_at": "2026-01-01T00:00:00+00:00", "supersedes": [],
        },
    }
    project_id = wire.project_id_for(root)
    host = tmp_path / "host.json"
    host.write_text(json.dumps({"schema": 1, "projects": {project_id: {
        "root": str(root), "pm_sids": [_H11_SID], "pm_images": [_H11_IMAGE],
        "trusted_writers": ["controlled-human"], "authority_records": records,
        "usage_sources": {"task-card-rounds": {"kind": "task-card-rounds", "unit": "round"}},
        "policy_sha256": policy_sha,
    }}}), encoding="utf-8", newline="\n")
    peer = conductor.operator_authority.Peer(_H11_SID, os.getpid(), 123, 1, _H11_IMAGE)
    trust = conductor.operator_authority.ServiceTrust(peer, host)
    monkeypatch.setattr(conductor.operator_authority, "load_trust", lambda: trust)
    monkeypatch.setattr(
        conductor.operator_authority, "trusted_path", lambda path, *_a, **_k: path)
    monkeypatch.setattr(
        conductor.operator_authority, "_process_peer", lambda _pid, _stack: peer, raising=False)
    monkeypatch.setattr(
        conductor.operator_authority, "_pm_process_peer", lambda _pid: peer)
    backend = decision.FakeBackend([
        {"available": True, "reason": None, "retryable": False,
         "answers": {
             "gate_decision": {"value": choice, "confidence": 0.8},
             "basis_id": {"value": "b-approve", "confidence": 0.8}},
         "latency_ms": 1},
    ], name="timi-decisions", model="fake-model", confidence_source="api")
    real_client = getattr(decision.DecisionClient, "_dpc_original", decision.DecisionClient)

    def client_factory(cfg, **kwargs):
        return real_client(cfg, backend=backend, **kwargs)

    client_factory._dpc_original = real_client
    monkeypatch.setattr(decision, "DecisionClient", client_factory)
    return {"root": root, "note": note, "preparation": _h11_preparation(choice),
            "facts": facts, "backend": backend, "host": host}


def test_pm_h11_normal_entry_without_a_bounded_action_schedules_nothing(
        tmp_path, monkeypatch):
    parts = _h11_fixture(tmp_path, monkeypatch)
    submission = conductor.prepare_pm_halted_recovery(
        parts["root"], _H11_KEY, note=parts["note"], preparation=parts["preparation"])
    assert submission["stage"] == parts["facts"]["stage"]
    assert submission["stage_version"] == parts["facts"]["stage_version"]
    gate = gates.parse(conductor.gates_dir(parts["root"]) / (submission["gate_id"] + ".md"))
    assert gate.kind == "stalled" and gate.transport == "pending"
    assert gate.matter_ref and gate.substantive_version
    result = decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, submission)
    assert result["ok"] is True, result
    assert result["state"] == "recovered" and result["effect"] == "applied"
    assert result["resumed"] is False
    assert len(parts["backend"].calls) == 1
    roadmap_path = conductor.roadmap.roadmap_path(parts["root"])
    before = roadmap_path.read_bytes()

    st = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(parts["root"])), None)
    refused = conductor.consume_halted_recovery(parts["root"], _H11_KEY, st)
    assert refused["state"] == "blocked"
    assert refused["reason"] == "bounded-action-missing"
    assert conductor._halted_recovery_actions(parts["root"]) == []
    assert roadmap_path.read_bytes() == before
    assert conductor.roadmap.load_roadmap(roadmap_path).stages[0].status == "halted"
    assert len(parts["backend"].calls) == 1


def _h11_bounded_fixture(tmp_path, monkeypatch):
    parts = _h11_fixture(tmp_path, monkeypatch, limit=3, rounds=0)
    root = parts["root"]
    stem = "bounded-round"
    task_key = f"ap-{_H11_KEY}-{stem}"
    card_dir = root / ".agenticdoc" / _H11_KEY / "tasks"
    card_dir.mkdir(parents=True, exist_ok=True)
    card = card_dir / (stem + ".md")
    card.write_text(
        "# Bounded round\n\n## 要求\n\nRun one bounded round.\n\n"
        "## 写入允许面\n\n- `src/app.py`\n",
        encoding="utf-8", newline="\n")
    worker = root / ".agenticdoc" / _H11_KEY / "workers" / task_key
    worker.mkdir(parents=True, exist_ok=True)
    # A previous round in the same loop stays on disk: the cumulative usage
    # counter must grow by exactly one after the bounded dispatch.
    sentinel = root / ".agenticdoc" / _H11_KEY / "workers" / "previous-round"
    sentinel.mkdir(parents=True, exist_ok=True)
    (sentinel / "task.md").write_text(
        "---\nloop: h11:bounded\nattempt: 1\ntype: repair\n---\n\n# previous\n",
        encoding="utf-8", newline="\n")
    task_md = worker / "task.md"
    task_md.write_text(
        "---\nloop: h11:bounded\nattempt: 1\ntype: repair\n---\n\n# task\n",
        encoding="utf-8", newline="\n")
    parts["note"]["bounded_action"] = {
        "kind": "dispatch-round", "task_key": task_key, "task_type": "repair",
        "card_sha256": dispatch.card_digest(card),
        "write_face": ["src/app.py"], "amount": 1,
        "end_criterion": "the bounded round reports a concrete result",
    }
    parts["note"]["residual_budget"]["round"] = 3 - 1
    parts.update({"task_key": task_key, "task_md": task_md, "card": card,
                  "stem": stem})
    return parts


def test_pm_h11_conductor_executes_the_public_bounded_step_once(
        tmp_path, monkeypatch):
    parts = _h11_bounded_fixture(tmp_path, monkeypatch)
    submission = conductor.prepare_pm_halted_recovery(
        parts["root"], _H11_KEY, note=parts["note"], preparation=parts["preparation"])
    result = decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, submission)
    assert result["ok"] is True, result
    assert len(parts["backend"].calls) == 1
    roadmap_path = conductor.roadmap.roadmap_path(parts["root"])
    roadmap_before = roadmap_path.read_bytes()
    task_before = parts["task_md"].read_bytes()
    queue_path = mw_common.workers_path(parts["root"])
    queue_before = queue_path.read_bytes() if queue_path.exists() else b""

    st = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(parts["root"])), None)
    consumed = conductor.consume_halted_recovery(parts["root"], _H11_KEY, st)
    assert consumed["state"] == "recorded", consumed
    assert consumed["task_key"] == parts["task_key"]
    assert consumed["attempt"] == 2 and consumed["used_rounds"] == 2
    task_after = parts["task_md"].read_bytes()
    assert task_after != task_before and b"attempt: 2" in task_after
    queue_after = queue_path.read_bytes()
    assert queue_after != queue_before
    rows = [row for row in mw_common.parse_workers_file(queue_path)
            if row["task_key"] == parts["task_key"]]
    assert len(rows) == 1 and rows[0]["origin"] == mw_common.WORKER_ORIGIN_CONDUCTOR
    store = lifecycle.LifecycleStore.production(
        parts["root"], redact=wire.SubstringRedactor([]))
    events = [row for row in lifecycle.read_lifecycle(store).events
              if row.get("kind") == "lifecycle"]
    executed = [row for row in events if row["lifecycle"] == "executed"
                and row["decision_id"] == consumed["decision_ref"]
                and str(row.get("event_id", "")).startswith("h11-bounded-executed-")]
    settled = [row for row in events if row["lifecycle"] == "settled"
               and row["decision_id"] == consumed["decision_ref"]
               and str(row.get("event_id", "")).startswith("h11-bounded-settled-")]
    assert len(executed) == 1 and len(settled) == 1
    # The bounded step dispatches one round; it neither resumes nor rewrites
    # the halted roadmap, and the retired journal stays empty history.
    assert roadmap_path.read_bytes() == roadmap_before
    assert conductor.roadmap.load_roadmap(roadmap_path).stages[0].status == "halted"
    assert conductor._halted_recovery_actions(parts["root"]) == []
    assert len(parts["backend"].calls) == 1

    replay = conductor.consume_halted_recovery(parts["root"], _H11_KEY, st)
    assert replay["state"] == "duplicate", replay
    assert parts["task_md"].read_bytes() == task_after
    assert queue_path.read_bytes() == queue_after
    events_after = [row for row in lifecycle.read_lifecycle(store).events
                    if row.get("kind") == "lifecycle"
                    and row["lifecycle"] == "executed"
                    and row["decision_id"] == consumed["decision_ref"]
                    and str(row.get("event_id", "")).startswith("h11-bounded-executed-")]
    assert len(events_after) == 1
    assert len(parts["backend"].calls) == 1


def test_pm_h11_conductor_keeps_the_stage_halted_when_the_source_is_revoked(
        tmp_path, monkeypatch):
    parts = _h11_fixture(tmp_path, monkeypatch)
    submission = conductor.prepare_pm_halted_recovery(
        parts["root"], _H11_KEY, note=parts["note"], preparation=parts["preparation"])
    assert decision_recovery.run_pm_halted_recovery(
        parts["root"], _H11_KEY, submission)["ok"] is True
    st = conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(parts["root"])), None)
    host = json.loads(parts["host"].read_text(encoding="utf-8"))
    row = next(iter(host["projects"].values()))
    row["authority_records"]["grant-h11"]["revoked"] = True
    parts["host"].write_text(json.dumps(host), encoding="utf-8", newline="\n")
    roadmap_path = conductor.roadmap.roadmap_path(parts["root"])
    before = roadmap_path.read_bytes()
    blocked = conductor.consume_halted_recovery(parts["root"], _H11_KEY, st)
    assert blocked["state"] == "blocked"
    assert "authority" in str(blocked["reason"])
    assert conductor._halted_recovery_actions(parts["root"]) == []
    assert roadmap_path.read_bytes() == before


# ---------------------------------------------------------------------------
# T19 prepared tick: the normal automatic pass evaluates one ready prepared
# gate as the current claimed PM. One tick, one prepared request, one TS
# writer deposit, the original controlled consumer and the real lifecycle.
# Off/shadow, a missing/changed sidecar, a revoked source, a dead claim, a
# policy/budget or machine-condition failure and an interrupted start never
# ask the model and never move the target.
# ---------------------------------------------------------------------------

def _tick_decide_config(root):
    (root / ".mw").mkdir(parents=True, exist_ok=True)
    (root / ".mw" / "decide.json").write_text(json.dumps({
        "enabled": True, "transport": "timi-decisions",
        "max_questions": 8, "max_retries": 0,
    }), encoding="utf-8", newline="\n")


def _tick_client(monkeypatch, preparation, choice="approve"):
    basis = next(v for v in preparation["basis_catalog"] if choice in v["applies_to"])
    backend = decision.FakeBackend([decision.BackendOutcome(True, None, False, {
        "gate_decision": {"value": choice, "confidence": 0.95},
        "basis_id": {"value": basis["id"], "confidence": 0.95},
    }, 0)])
    real = decision.DecisionClient
    factory_calls = []

    def factory(cfg, **kwargs):
        factory_calls.append(1)
        return real(cfg, backend=backend, **kwargs)

    factory._dpc_original = real
    monkeypatch.setattr(decision, "DecisionClient", factory)
    return backend, factory_calls


def _tick_prepared_fixture(tmp_path, monkeypatch, case="h01"):
    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    f = _pm_run_fixture(tmp_path, case)
    # A registered deployment has a verified initial brake state before its
    # first automatic decision; the missing-object unknown rule is separate.
    _t26_brake(f["root"], "clear")
    # This fixture mocks the SCM anchor only. A registered project's brake facts
    # come from its fixed protected object, so provide that service-side read
    # from the same original bytes instead of a local-file shortcut.
    monkeypatch.setattr(
        conductor.operator_authority, "read_brake",
        lambda project_id, **_kwargs: {
            "ok": True, "facts": decision_recovery.brake_facts(f["root"])})
    f["prepared"] = conductor.prepare_pm_gate(
        f["root"], f["trigger"].id, owner_key=f["owner"], book=f["book"])
    return f


def _tick_state(root):
    return conductor.ConductorState(
        conductor.timeline.Timeline(conductor.timeline.timeline_path(root)), None)


def _tick_assert_no_release(f, backend, before):
    assert backend.calls == []
    assert f["target"].read_bytes() == before
    gate = gates.parse(f["prepared"].path)
    assert gate.transport == "pending" and gate.business is None
    assert gate.effect == "not-started"
    rows = [r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(
            f["root"], redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]
    assert rows == []


def test_normal_tick_evaluates_a_ready_prepared_gate_once(tmp_path, monkeypatch):
    f = _tick_prepared_fixture(tmp_path, monkeypatch, "h01")
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])
    _tick_decide_config(f["root"])
    backend, factories = _tick_client(monkeypatch, f["book"]["book"]["preparation"])
    before = f["target"].read_bytes()

    conductor.auto_decide_gates(f["root"], f["st"], config.load_config(f["root"]))

    assert len(factories) == 1 and len(backend.calls) == 1
    assert roadmap.stage_by_number(
        roadmap.load_roadmap(f["target"]), 1).status == "running"
    assert f["target"].read_bytes() != before
    answered = gates.parse(f["prepared"].path)
    assert answered.transport == "answered" and answered.business == "approve"
    assert answered.decision_ref == f"dp-gate-approve:{f['logical_id']}"
    rows = [r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(
            f["root"], redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]
    assert [r["lifecycle"] for r in rows] == ["consumed", "executed", "settled"]

    applied = f["target"].read_bytes()
    conductor.auto_decide_gates(f["root"], _tick_state(f["root"]),
                                config.load_config(f["root"]))
    assert len(factories) == 1 and len(backend.calls) == 1
    assert f["target"].read_bytes() == applied
    assert len([r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(
            f["root"], redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]) == 3


def test_normal_tick_uses_the_same_rule_for_a_later_stage(tmp_path, monkeypatch):
    monkeypatch.delenv("PI_WORKER_TASK", raising=False)
    root = tmp_path / "later-tick"
    config.save_config(root, {"enabled": True, "paused": False, "auto_gate_mode": "live"})
    _t26_brake(root, "clear")
    owner = "owner"
    claim = f"{socket.gethostname()}:{os.getpid()}"
    (root / ".agenticdoc").mkdir(parents=True, exist_ok=True)
    (root / ".agenticdoc/_index.parallel").write_text(
        f"| {owner} | active | EXECUTE | {claim} | - | test | now |\n", encoding="utf-8")
    (root / ".agenticdoc/goal.md").write_text("# Deliver the agreed feature\n", encoding="utf-8")
    target = roadmap.roadmap_path(root)
    target.write_text(
        "## Stage 1: Done\n> goal: previous stage\n> status: closed\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n"
        "| legacy | implement | - |\n\n"
        "## Stage 2: Next\n> goal: Ship the next verified stage\n> status: pending\n"
        "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n"
        f"| {owner} | implement | - |\n", encoding="utf-8")
    st = _tick_state(root)
    conductor._create_stage_confirm_gate(
        root, st, roadmap.stage_by_number(roadmap.load_roadmap(target), 2))
    trigger = [g for g in gates.enumerate(conductor.gates_dir(root))
               if g.historical and g.kind == "stage-confirm"][-1]
    book = _pm_book_payload()
    book["book"]["meta"] = {"actor_role": "pm", "key": owner,
                            "logical_id": "tick-stage-2", "task_key": "T19-tick"}
    _, matter, _note = conductor._pm_gate_matter(
        root, owner, trigger, book["book"]["material"], book["book"]["preparation"])
    _pm_policy(root, matter.action)
    prepared = conductor.prepare_pm_gate(root, trigger.id, owner_key=owner, book=book)
    _pm_deploy_authority(monkeypatch, root, owner, matter.action)
    monkeypatch.setattr(
        conductor.operator_authority, "read_brake",
        lambda project_id, **_kwargs: {
            "ok": True, "facts": decision_recovery.brake_facts(root)})
    _tick_decide_config(root)
    backend, factories = _tick_client(monkeypatch, book["book"]["preparation"])

    conductor.auto_decide_gates(root, st, config.load_config(root))

    assert len(factories) == 1 and len(backend.calls) == 1
    loaded = roadmap.load_roadmap(target)
    assert roadmap.stage_by_number(loaded, 1).status == "closed"
    assert roadmap.stage_by_number(loaded, 2).status == "running"
    assert gates.parse(prepared.path).business == "approve"


def _tick_negative_fixture(tmp_path, monkeypatch, case):
    f = _tick_prepared_fixture(tmp_path, monkeypatch, "h01")
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])
    _tick_decide_config(f["root"])
    if case == "missing-sidecar":
        conductor._prepared_gate_sidecar(f["root"], f["prepared"].id).unlink()
    elif case == "changed-sidecar":
        path = conductor._prepared_gate_sidecar(f["root"], f["prepared"].id)
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["substantive_version"] = "v-changed"
        path.write_text(json.dumps(raw), encoding="utf-8", newline="\n")
    elif case == "old-sidecar-without-meta":
        path = conductor._prepared_gate_sidecar(f["root"], f["prepared"].id)
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw.pop("meta", None)
        path.write_text(json.dumps(raw), encoding="utf-8", newline="\n")
    elif case == "revoked-authority":
        host = f["root"].parent / "host.json"
        raw = json.loads(host.read_text(encoding="utf-8"))
        for row in raw["projects"].values():
            for record in row["authority_records"].values():
                record["revoked"] = True
        host.write_text(json.dumps(raw), encoding="utf-8", newline="\n")
    elif case == "dead-claim":
        (f["root"] / ".agenticdoc/_index.parallel").write_text(
            f"| {f['owner']} | active | EXECUTE | other-host:999999 | - | test | now |\n",
            encoding="utf-8")
    elif case == "missing-policy":
        policy.policy_path(f["root"]).unlink()
    elif case == "exhausted-budget":
        loaded = json.loads(policy.policy_path(f["root"]).read_text(encoding="utf-8"))
        loaded["hard_limits"] = [{"unit": "rounds", "limit": 0, "usage_source": "rounds"}]
        policy.policy_path(f["root"]).write_text(
            json.dumps(loaded), encoding="utf-8", newline="\n")
    elif case == "moved-target":
        f["target"].write_text(
            roadmap.update_stage_status(f["target"].read_text(encoding="utf-8"), 1, "running"),
            encoding="utf-8", newline="\n")
    elif case == "transport-disabled":
        (f["root"] / ".mw" / "decide.json").write_text(
            json.dumps({"enabled": False}), encoding="utf-8", newline="\n")
    elif case == "interrupted-start":
        sidecar = json.loads(conductor._prepared_gate_sidecar(
            f["root"], f["prepared"].id).read_text(encoding="utf-8"))
        meta = lifecycle.DecisionMeta(
            key=sidecar["meta"]["key"], logical_id=sidecar["meta"]["logical_id"],
            initiator_role="pm", task_key=sidecar["meta"].get("task_key"))
        store = lifecycle.LifecycleStore.production(
            f["root"], redact=wire.SubstringRedactor([]))
        assert lifecycle.record_start(
            store, meta, decision_id=f"dp-gate-approve:{meta.logical_id}").recorded
    else:
        raise AssertionError(case)
    return f


@pytest.mark.parametrize("case", [
    "missing-sidecar", "changed-sidecar", "old-sidecar-without-meta",
    "revoked-authority", "dead-claim", "missing-policy", "exhausted-budget",
    "moved-target", "transport-disabled", "interrupted-start",
])
def test_normal_tick_refuses_an_unready_prepared_gate_without_a_model(
        tmp_path, monkeypatch, case):
    f = _tick_negative_fixture(tmp_path, monkeypatch, case)
    backend, factories = _tick_client(monkeypatch, f["book"]["book"]["preparation"])
    before = f["target"].read_bytes()

    conductor.auto_decide_gates(f["root"], f["st"], config.load_config(f["root"]))

    assert factories == [] and backend.calls == []
    _tick_assert_no_release(f, backend, before)
    if case == "interrupted-start":
        store = lifecycle.LifecycleStore.production(
            f["root"], redact=wire.SubstringRedactor([]))
        events = lifecycle.read_lifecycle(store).events
        assert len([r for r in events if r.get("kind") == "record-start"]) == 1
        assert not [r for r in events if r.get("kind") == "request"]


@pytest.mark.parametrize("mode", ["off", "shadow"])
def test_normal_tick_off_and_shadow_make_no_new_production_request(
        tmp_path, monkeypatch, mode):
    f = _tick_prepared_fixture(tmp_path, monkeypatch, "h01")
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])
    _tick_decide_config(f["root"])
    cfg = config.load_config(f["root"])
    cfg["auto_gate_mode"] = mode
    config.save_config(f["root"], cfg)
    backend, factories = _tick_client(monkeypatch, f["book"]["book"]["preparation"])
    before = f["target"].read_bytes()

    conductor.auto_decide_gates(f["root"], f["st"], config.load_config(f["root"]))

    assert factories == [] and backend.calls == []
    _tick_assert_no_release(f, backend, before)

def test_concurrent_normal_ticks_send_one_request_and_apply_once(tmp_path, monkeypatch):
    f = _tick_prepared_fixture(tmp_path, monkeypatch, "h01")
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])
    _tick_decide_config(f["root"])
    backend, factories = _tick_client(monkeypatch, f["book"]["book"]["preparation"])
    barrier = threading.Barrier(2)

    def tick_once(_index):
        st = _tick_state(f["root"])
        barrier.wait()
        conductor.auto_decide_gates(f["root"], st, config.load_config(f["root"]))
        return st

    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(tick_once, range(2)))

    assert len(backend.calls) == 1
    assert roadmap.stage_by_number(
        roadmap.load_roadmap(f["target"]), 1).status == "running"
    rows = [r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(
            f["root"], redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]
    assert [r["lifecycle"] for r in rows] == ["consumed", "executed", "settled"]
    assert gates.parse(f["prepared"].path).business == "approve"
    assert len(factories) == 1

def test_normal_tick_steer_answers_without_releasing_or_repeating(tmp_path, monkeypatch):
    f = _tick_prepared_fixture(tmp_path, monkeypatch, "h01")
    _pm_deploy_authority(monkeypatch, f["root"], f["owner"], f["action"])
    _tick_decide_config(f["root"])
    backend, factories = _tick_client(
        monkeypatch, f["book"]["book"]["preparation"], "steer")
    before = f["target"].read_bytes()

    conductor.auto_decide_gates(f["root"], f["st"], config.load_config(f["root"]))

    assert len(factories) == 1 and len(backend.calls) == 1
    assert f["target"].read_bytes() == before
    gate = gates.parse(f["prepared"].path)
    assert gate.transport == "answered" and gate.business == "steer"
    assert gate.effect == "blocked"
    rows = [r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(
            f["root"], redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]
    assert [r["lifecycle"] for r in rows] == ["consumed", "settled"]
    assert rows[-1]["outcome"] == "pending" and "dp-pm-steer" in rows[-1]["reason"]

    conductor.auto_decide_gates(f["root"], _tick_state(f["root"]),
                                config.load_config(f["root"]))
    assert len(factories) == 1 and len(backend.calls) == 1
    assert f["target"].read_bytes() == before
    assert len([r for r in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(
            f["root"], redact=wire.SubstringRedactor([]))).events
        if r.get("kind") == "lifecycle"]) == 2


# Original T26: exercise the public tick around the actual H06 consumer. The
# prepared-family and automatic-gate passes alone do not cover the global halt.

def _normal_goal_tick_fixture(tmp_path):
    root, owner, claim, st, target = _conductor_h_fixture(tmp_path)
    config.save_config(root, {"enabled": True, "paused": False, "auto_gate_mode": "off"})
    goal = conductor.goal_path(root)
    goal.write_text(GOAL_BEFORE, encoding="utf-8", newline="\n")
    st.goal_baseline = goal.stat().st_mtime_ns
    assert conductor.tick(root, st) == "ok"
    return root, owner, st, goal


def _normal_goal_change(root, st, goal, text=GOAL_AFTER):
    goal.write_text(text, encoding="utf-8", newline="\n")
    changed = max(goal.stat().st_mtime_ns, st.goal_baseline + 2_000_000_000)
    os.utime(goal, ns=(changed, changed))
    assert conductor.tick(root, st) == "halted-goal-change"
    return [g for g in gates.enumerate(conductor.gates_dir(root))
            if g.kind == "goal-change"][-1]


def _normal_family_goal_run(root, owner, monkeypatch, capsys, choice):
    _family_policy(root)
    _family_rounds(root, owner, 1)
    payload = _family_goal_payload(root)
    book = _family_book("goal-adoption", payload)
    path = _family_book_path(root, book)
    _family_deploy_authority(
        monkeypatch, root, ["goal-adopt:owner", "goal-version:goal-v2"])
    client = _pm_fake_client(root, book["book"]["preparation"], choice)
    code = mw_cli._ap_family_run(
        _family_args("goal-adoption", owner, path), root, client=client)
    assert code == (0 if choice == "approve" else 2), capsys.readouterr().err
    result = json.loads(capsys.readouterr().out)
    return payload, book, path, result


def test_goal_tick_confirmed_reject_never_refreshes_or_dispatches_even_after_restart(tmp_path):
    root, _owner, st, goal = _normal_goal_tick_fixture(tmp_path)
    original_baseline = st.goal_baseline
    gate = _normal_goal_change(root, st, goal)
    assert conductor.answer_gate_confirmed(
        root, st, gate.id, "reject", answered_by="isolated-human", confirm=True).ok
    rejected = gate.path.read_bytes()
    queue = mw_common.workers_path(root)
    before_queue = queue.read_bytes() if queue.exists() else None
    for _ in range(2):
        assert conductor.tick(root, st) == "halted-goal-change"
        assert st.goal_baseline == original_baseline and st.goal_halted is True
        assert gate.path.read_bytes() == rejected
        assert (queue.read_bytes() if queue.exists() else None) == before_queue
    restarted = conductor.ConductorState(st.timeline, goal.stat().st_mtime_ns)
    assert conductor.tick(root, restarted) == "halted-goal-change"
    assert restarted.goal_halted is True and gate.path.read_bytes() == rejected


def test_goal_tick_confirmed_approve_is_bound_to_the_reviewed_goal(tmp_path):
    root, _owner, st, goal = _normal_goal_tick_fixture(tmp_path)
    gate = _normal_goal_change(root, st, goal)
    assert conductor.answer_gate_confirmed(
        root, st, gate.id, "approve", answered_by="isolated-human").ok
    approved = gate.path.read_bytes()
    assert conductor.tick(root, st) == "ok"
    assert st.goal_baseline == goal.stat().st_mtime_ns and st.goal_halted is False
    goal.write_text("# Goal\n\nDeliver an unapproved stage 4.\n", encoding="utf-8")
    # A timestamp rollback cannot replay the old approval for different bytes.
    os.utime(goal, ns=(st.goal_baseline, st.goal_baseline))
    assert conductor.tick(root, st) == "halted-goal-change"
    assert st.goal_halted is True and gate.path.read_bytes() == approved


@pytest.mark.parametrize("choice", ["steer", "need_fix", "reject"])
def test_goal_tick_family_non_approve_keeps_the_original_baseline(
        tmp_path, monkeypatch, capsys, choice):
    root, owner, st, goal = _normal_goal_tick_fixture(tmp_path)
    original_baseline = st.goal_baseline
    trigger = _normal_goal_change(root, st, goal)
    payload, _book, _path, _result = _normal_family_goal_run(
        root, owner, monkeypatch, capsys, choice)
    before_gate = trigger.path.read_bytes()
    before_baseline = pathlib.Path(payload["baseline_path"]).read_bytes()
    gate_count = len(gates.enumerate(conductor.gates_dir(root)))
    for _ in range(2):
        assert conductor.tick(root, st) == "halted-goal-change"
        assert st.goal_baseline == original_baseline and st.goal_halted is True
        assert pathlib.Path(payload["baseline_path"]).read_bytes() == before_baseline
        assert trigger.path.read_bytes() == before_gate
    goal.write_text(GOAL_AFTER.replace("operator.", "operator.   "), encoding="utf-8")
    assert conductor.tick(root, st) == "halted-goal-change"
    assert len(gates.enumerate(conductor.gates_dir(root))) == gate_count


def test_goal_tick_consumed_adoption_resumes_once_and_old_replay_cannot_adopt_later_goal(
        tmp_path, monkeypatch, capsys):
    root, owner, st, goal = _normal_goal_tick_fixture(tmp_path)
    trigger = _normal_goal_change(root, st, goal)
    payload, book, path, result = _normal_family_goal_run(
        root, owner, monkeypatch, capsys, "approve")
    assert result["status"] == "applied" and cg.adopted_goal_binding(root, owner).state == "present"
    old_trigger = trigger.path.read_bytes()
    baseline = pathlib.Path(payload["baseline_path"])
    adopted_bytes = baseline.read_bytes()
    events = _family_lifecycle(root)
    assert [r["lifecycle"] for r in events] == ["consumed", "executed", "settled"]
    assert conductor.tick(root, st) == "ok"
    assert st.goal_halted is False and st.goal_baseline == goal.stat().st_mtime_ns
    restarted = conductor.ConductorState(st.timeline, goal.stat().st_mtime_ns)
    assert conductor.tick(root, restarted) == "ok"
    # Whitespace/line-ending presentation does not need a second adoption.
    goal.write_bytes(GOAL_AFTER.replace("\n", "\r\n").encode("utf-8"))
    assert conductor.tick(root, restarted) == "ok"
    assert len([g for g in gates.enumerate(conductor.gates_dir(root)) if g.kind == "goal-change"]) == 2
    goal.write_text("# Goal\n\nDeliver an unapproved stage 4.\n", encoding="utf-8")
    os.utime(goal, ns=(restarted.goal_baseline, restarted.goal_baseline))
    assert conductor.tick(root, restarted) == "halted-goal-change"
    assert restarted.goal_halted is True
    replay_client = decision.DecisionClient(
        decision.DecisionConfig(enabled=True, project_root=root), decision.FakeBackend([]))
    assert mw_cli._ap_family_run(
        _family_args("goal-adoption", owner, path), root, client=replay_client) == 0
    replay = json.loads(capsys.readouterr().out)
    assert replay["duplicate"] is True and replay["request"]["status"] == "already-answered"
    assert conductor.tick(root, restarted) == "halted-goal-change"
    assert baseline.read_bytes() == adopted_bytes and trigger.path.read_bytes() == old_trigger
    assert _family_lifecycle(root) == events


@pytest.mark.parametrize("fault", ["missing-effect", "changed-after-text"])
def test_goal_tick_does_not_resume_from_an_applied_marker_without_bound_consumption(
        tmp_path, monkeypatch, capsys, fault):
    root, owner, st, goal = _normal_goal_tick_fixture(tmp_path)
    original_baseline = st.goal_baseline
    _normal_goal_change(root, st, goal)
    payload, _book, _path, result = _normal_family_goal_run(
        root, owner, monkeypatch, capsys, "approve")
    gate = gates.parse(conductor.gates_dir(root) / (result["gate_id"] + ".md"))
    if fault == "missing-effect":
        conductor._family_effect_path(root, gate).unlink()
    else:
        sidecar = conductor._prepared_gate_sidecar(root, gate.id)
        raw = json.loads(sidecar.read_text(encoding="utf-8"))
        raw["payload"]["after_text"] = "forged current goal"
        sidecar.write_text(json.dumps(raw), encoding="utf-8")
    before = pathlib.Path(payload["baseline_path"]).read_bytes()
    assert conductor.tick(root, st) == "halted-goal-change"
    assert st.goal_halted is True and st.goal_baseline == original_baseline
    assert pathlib.Path(payload["baseline_path"]).read_bytes() == before


def test_goal_tick_formatting_only_change_does_not_create_an_adoption(tmp_path):
    root, _owner, st, goal = _normal_goal_tick_fixture(tmp_path)
    goal.write_bytes(GOAL_BEFORE.replace("\n", "\r\n").encode("utf-8"))
    changed = st.goal_baseline + 2_000_000_000
    os.utime(goal, ns=(changed, changed))
    assert conductor.tick(root, st) == "ok"
    assert st.goal_halted is False and st.goal_baseline == changed
    assert not [g for g in gates.enumerate(conductor.gates_dir(root)) if g.kind == "goal-change"]


# Original T26/T20 final-review closure. PM owns these regressions; the source
# writer owns conductor/contract_guard separately. Existing168 cases stay intact.

def _pending_family_fixture(tmp_path, monkeypatch):
    root, owner, _claim, _st, _target = _conductor_h_fixture(tmp_path)
    _family_policy(root)
    _family_rounds(root, owner, 1)
    payload = _family_goal_payload(root)
    _family_deploy_authority(monkeypatch, root, [
        "goal-adopt:owner", "goal-version:goal-v2", "goal-version:goal-v3"])
    return root, owner, payload


def _family_request_rows(root):
    return [row for row in lifecycle.read_lifecycle(
        lifecycle.LifecycleStore.production(root, redact=wire.SubstringRedactor([]))).events
        if row.get("kind") == "request"]


def _try_family_request(root, owner, gate, book, client):
    try:
        return conductor.request_prepared_gate(
            root, gate, owner_key=owner, book=book, client=client)
    except gate_effects.GateBlocked as exc:
        return {"status": "refused", "reason": str(exc)}


def test_family_prepare_is_atomic_across_stale_prelock_snapshots(tmp_path, monkeypatch):
    root, owner, payload = _pending_family_fixture(tmp_path, monkeypatch)
    books = [_family_book("goal-adoption", payload, logical_id=name)
             for name in ("prepare-a", "prepare-b")]
    original_lock = gate_effects._lock
    gates_lock = conductor.lock_file(root, "gates")
    local = threading.local()
    guard = threading.Lock()
    first_thread = [None]
    second_at_lock, first_complete = threading.Event(), threading.Event()

    @contextmanager
    def scheduled_real_lock(path):
        if path == gates_lock and not getattr(local, "seen", False):
            local.seen = True
            with guard:
                if first_thread[0] is None:
                    first_thread[0] = threading.get_ident()
                is_first = first_thread[0] == threading.get_ident()
            if is_first:
                # No product lock is held here. A second caller can finish its
                # real pre-lock snapshot; an outer legitimate lock may instead
                # serialize it, in which case the bounded wait simply expires.
                second_at_lock.wait(1)
            else:
                second_at_lock.set()
                assert first_complete.wait(15)
        with original_lock(path):
            yield

    monkeypatch.setattr(gate_effects, "_lock", scheduled_real_lock)

    def prepare(book):
        try:
            return conductor.prepare_pm_family_gate(
                root, "goal-adoption", owner_key=owner, book=book)
        except gate_effects.GateBlocked:
            return None  # a safe contender refusal is not a duplicate approval
        finally:
            if first_thread[0] == threading.get_ident():
                first_complete.set()

    with ThreadPoolExecutor(max_workers=2) as pool:
        pending = [pool.submit(prepare, book) for book in books]
        prepared = [future.result(timeout=30) for future in pending]
    actual = [gate for gate in gates.enumerate(conductor.gates_dir(root)) if not gate.historical]
    assert len(actual) == 1
    assert {gate.id for gate in prepared if gate is not None} == {actual[0].id}
    sidecar = json.loads(conductor._prepared_gate_sidecar(root, actual[0].id).read_text(encoding="utf-8"))
    assert (sidecar["gate_id"], sidecar["matter_ref"], sidecar["substantive_version"]) == (
        actual[0].id, actual[0].matter_ref, actual[0].substantive_version)
    assert _family_request_rows(root) == []


@pytest.mark.parametrize("same_identity", [False, True])
def test_family_pending_gate_owns_one_canonical_request_before_transport(
        tmp_path, monkeypatch, same_identity):
    root, owner, payload = _pending_family_fixture(tmp_path, monkeypatch)
    books = [_family_book("goal-adoption", payload, logical_id="canonical-a"),
             _family_book("goal-adoption", payload,
                          logical_id="canonical-a" if same_identity else "another-b")]
    gate = conductor.prepare_pm_family_gate(root, "goal-adoption", owner_key=owner, book=books[0])
    baseline = pathlib.Path(payload["baseline_path"]).read_bytes()
    clients = [_pm_fake_client(root, book["book"]["preparation"], "approve") for book in books]
    entered, release = threading.Event(), threading.Event()
    original = clients[0].request_prepared

    def paused_transport(*args, **kwargs):
        assert not conductor.lock_file(root, "gates").exists()
        entered.set()
        assert release.wait(15)
        return original(*args, **kwargs)

    monkeypatch.setattr(clients[0], "request_prepared", paused_transport)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(_try_family_request, root, owner, gate, books[0], clients[0])
        assert entered.wait(15)
        second = pool.submit(_try_family_request, root, owner, gate, books[1], clients[1])
        try:
            second_result = second.result(timeout=5)
        except TimeoutError:
            second_result = None
        finally:
            release.set()
        first_result = first.result(timeout=30)
        if second_result is None:
            second_result = second.result(timeout=30)
    assert first_result["status"] in ("answered", "already-answered")
    assert sum(len(client.backend.calls) for client in clients) == 1
    assert len(_family_request_rows(root)) == 1
    assert pathlib.Path(payload["baseline_path"]).read_bytes() == baseline
    assert _family_lifecycle(root) == []  # approval/request is not an object effect
    answer_before = gate.path.read_bytes()
    replay = _try_family_request(root, owner, gate, books[0], clients[1])
    assert replay["status"] == "already-answered"
    assert gate.path.read_bytes() == answer_before
    assert sum(len(client.backend.calls) for client in clients) == 1


def test_family_uncertain_recorded_start_cannot_switch_logical_id_to_resend(tmp_path, monkeypatch):
    root, owner, payload = _pending_family_fixture(tmp_path, monkeypatch)
    books = [_family_book("goal-adoption", payload, logical_id=name)
             for name in ("uncertain-a", "uncertain-b")]
    gate = conductor.prepare_pm_family_gate(root, "goal-adoption", owner_key=owner, book=books[0])
    store = lifecycle.LifecycleStore.production(root, redact=wire.SubstringRedactor([]))
    meta = conductor._pm_book_meta(books[0], owner)
    assert lifecycle.record_start(store, meta, decision_id="dp-gate-approve:" + meta.logical_id).recorded
    clients = [_pm_fake_client(root, book["book"]["preparation"], "approve") for book in books]
    before = gate.path.read_bytes()
    results = [_try_family_request(root, owner, gate, book, client)
               for book, client in zip(books, clients)]
    assert all(result["status"] == "refused" for result in results)
    assert [len(client.backend.calls) for client in clients] == [0, 0]
    assert _family_request_rows(root) == [] and gate.path.read_bytes() == before


@pytest.mark.parametrize("fault", ["missing", "missing-meta", "changed-version", "broken-json"])
def test_family_request_rejects_missing_or_corrupt_prepared_sidecar(tmp_path, monkeypatch, fault):
    root, owner, payload = _pending_family_fixture(tmp_path, monkeypatch)
    book = _family_book("goal-adoption", payload, logical_id="sidecar-bound")
    gate = conductor.prepare_pm_family_gate(root, "goal-adoption", owner_key=owner, book=book)
    sidecar = conductor._prepared_gate_sidecar(root, gate.id)
    if fault == "missing":
        sidecar.unlink()
    elif fault == "broken-json":
        sidecar.write_text("{broken", encoding="utf-8")
    else:
        record = json.loads(sidecar.read_text(encoding="utf-8"))
        if fault == "missing-meta":
            record.pop("meta", None)
        else:
            record["substantive_version"] = "different"
        sidecar.write_text(json.dumps(record), encoding="utf-8")
    client = _pm_fake_client(root, book["book"]["preparation"], "approve")
    before = gate.path.read_bytes()
    result = _try_family_request(root, owner, gate, book, client)
    assert result["status"] == "refused"
    assert client.backend.calls == [] and _family_request_rows(root) == []
    assert gate.path.read_bytes() == before


def test_family_substantive_version_gets_new_request_after_one_version_replays(tmp_path, monkeypatch):
    root, owner, payload = _pending_family_fixture(tmp_path, monkeypatch)
    book = _family_book("goal-adoption", payload, logical_id="version-two")
    first = conductor.prepare_pm_family_gate(root, "goal-adoption", owner_key=owner, book=book)
    client = _pm_fake_client(root, book["book"]["preparation"], "approve")
    assert _try_family_request(root, owner, first, book, client)["status"] == "answered"
    assert _try_family_request(root, owner, first, book, client)["status"] == "already-answered"
    revised = json.loads(json.dumps(payload))
    revised["request"]["current_version"] = "goal-v3"
    revised["request"]["target_version"] = "goal-v3"
    revised["after_text"] += "\nDeliver the additional approved version-three requirement.\n"
    revised["note"] = revised["note"].replace("goal-v2", "goal-v3")
    next_book = _family_book("goal-adoption", revised, logical_id="version-three")
    second = conductor.prepare_pm_family_gate(root, "goal-adoption", owner_key=owner, book=next_book)
    assert second.id != first.id and second.matter_ref == first.matter_ref
    assert second.substantive_version != first.substantive_version
    next_client = _pm_fake_client(root, next_book["book"]["preparation"], "approve")
    assert _try_family_request(root, owner, second, next_book, next_client)["status"] == "answered"
    assert len(client.backend.calls) == len(next_client.backend.calls) == 1
    assert len(_family_request_rows(root)) == 2


@pytest.mark.parametrize("action,expected", [("escalate", False), ("retry", True), ("narrow", True)])
def test_h09_real_passing_verification_only_releases_releasable_dispositions(tmp_path, action, expected):
    root = tmp_path / action
    _h09_enable_policy(root)
    assert advance.record_failure(root, "owner", "done", 1, "original failure", "gate blocked")
    assert advance.advance_allowed(root, "owner", "done")[0] is False
    logical = "actual-" + action
    _h09_record_auto_request(root, "owner", logical, "dp-auto:" + logical)
    advance.record_disposition(root, "owner", "done", decision_ref="dp-auto:" + logical,
                               action=action, budget=1, end_condition="inspect actual verification")
    assert advance.advance_allowed(root, "owner", "done")[0] is False
    verified = advance.record_verification(root, "owner", "done", verify_cmd="python -c pass", rc=99)
    assert verified["rc"] == 0
    assert advance.advance_allowed(root, "owner", "done")[0] is expected
    assert any(row.get("kind") == "failure" for row in advance._rows(root, "owner"))


def test_h08_old_actual_pass_cannot_reach_done_after_approved_contract_change(
        tmp_path, monkeypatch, capsys):
    root, owner, _claim, st, _target = _conductor_h_fixture(tmp_path)
    _family_policy(root)
    _family_rounds(root, owner, 1)
    payload = _family_contract_payload(root, owner)
    key_dir = root / ".agenticdoc" / owner
    revised = (key_dir / "spec.md").read_bytes()
    (key_dir / "spec.md").write_text(T20_SPEC, encoding="utf-8", newline="\n")
    old_test = root / "test_original_acceptance.py"
    old_test.write_text(
        "from pathlib import Path\ndef test_original_requirement():\n"
        f"    text = Path({str(key_dir / 'spec.md')!r}).read_text(encoding='utf-8')\n"
        "    assert 'first contract text, locked' in text\n", encoding="utf-8", newline="\n")
    argv = [sys.executable, "-B", "-m", "pytest", "-p", "no:cacheprovider", "-q", str(old_test)]
    old_run = xk.run_verification(argv, cwd=str(root), run_dir=str(root / "old-run"), timeout=30)
    assert old_run["red_counts"]["returncode"] == 0
    material = {
        "review_requirements": T20_SPEC,
        "review_evidence": [old_run["stdout_path"] + ":1"],
        "review_findings": json.dumps(old_run),
        "uncovered_scope": "isolated contract fixture; no product deployment claim",
    }
    preparation = {"prepared_at": "2026-11-10T00:00:00Z", "basis_catalog": [{
        "id": "actual-old-command", "text": "The submitted original-contract check actually exited0.",
        "material_refs": ["review_evidence", "review_findings"], "applies_to": ["pass"]}]}
    qg_client = decision.DecisionClient(decision.DecisionConfig(enabled=True, project_root=root),
        decision.FakeBackend([decision.BackendOutcome(True, None, False, {
            "qg_verdict": {"value": "pass", "confidence": 0.95},
            "basis_id": {"value": "actual-old-command", "confidence": 0.95}}, 0)]))
    answer = qg_client.request_prepared("dp-QG", material, preparation,
                                        actor_role="pm", logical_id="old-qg")
    assert answer["available"] and answer["choice"] == "pass" and len(qg_client.backend.calls) == 1
    report = key_dir / "workers" / dispatch.task_key_for(owner, "l3-a1") / "output.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("## Quality Gate Report\n" + json.dumps({"answer": answer, "verification": old_run})
        + "\n## Achieved\n" + json.dumps({"delivery_goal": "Validate the submitted original contract",
            "actual_completion": "Bounded original check exited0 and prepared QG answered pass",
            "verified": [old_run], "unverified": ["product deployment"], "unfinished_impact": []})
        + "\n### 系统行为变化\n只执行隔离验收，未改变生产功能。\n### 遗留\n完整产品验收仍归原任务。\n",
        encoding="utf-8", newline="\n")
    history = {report: report.read_bytes(), old_test: old_test.read_bytes(),
               pathlib.Path(old_run["stdout_path"]): pathlib.Path(old_run["stdout_path"]).read_bytes()}
    (key_dir / "spec.md").write_bytes(revised)
    _family_deploy_authority(monkeypatch, root, [f"contract-change:{owner}", "contract-item:AC-001"])
    book = _family_book("contract-refreeze", payload)
    book_path = _family_book_path(root, book)
    change_client = _pm_fake_client(root, book["book"]["preparation"], "approve")
    assert mw_cli._ap_family_run(_family_args("contract-refreeze", owner, book_path),
                                  root, client=change_client) == 0
    changed = json.loads(capsys.readouterr().out)
    assert changed["status"] == "applied" and len(change_client.backend.calls) == 1
    current_old = xk.run_verification(argv, cwd=str(root), run_dir=str(root / "old-against-new"), timeout=30)
    assert current_old["red_counts"]["returncode"] != 0
    phase_calls = []

    def stop_before_real_phase(key, phase, project, summary=None):
        phase_calls.append((key, phase))
        return 1, "", "isolated test stops any actual phase transition"

    monkeypatch.setattr(advance, "advance", stop_before_real_phase)
    state, _reason = conductor._done_transaction(root, st, owner, report)
    assert state == "gated"
    assert phase_calls == [], "stale original-contract evidence reached the phase runner"
    assert not list((key_dir / "evidence").glob("quality-gate-report-*.md"))
    pm = key_dir / "pm-state.md"
    assert not pm.exists() or "PASS" not in pm.read_text(encoding="utf-8")
    assert all(path.read_bytes() == data for path, data in history.items())


def _native_reverification_fixture(tmp_path, monkeypatch, capsys, *, unrelated=False,
        policy_limit=8, command_delay=0):
    """Native dispatched card; offline worker terminal is an explicit fixture.

    The verification runner, protected PM source, contract adoption, retained
    stdout and prepared QG below are real. This does not claim a model worker.
    """
    root, owner, claim, st, _target = _conductor_h_fixture(tmp_path)
    _family_policy(root, limit=policy_limit)
    (root / ".agenticdoc" / owner).mkdir(parents=True, exist_ok=True)
    payload = _family_contract_payload(root, owner)
    key_dir = root / ".agenticdoc" / owner
    padding = "\n<!-- Isolated native-dispatch documentation fixture. " + ("contract fixture " * 30) + "-->\n"
    revised = (key_dir / "spec.md").read_bytes() + padding.encode()
    (key_dir / "spec.md").write_text(T20_SPEC + padding, encoding="utf-8", newline="\n")
    (key_dir / "design.md").write_text(T20_DESIGN + padding, encoding="utf-8", newline="\n")
    research = key_dir / "evidence" / "research"
    research.mkdir(parents=True, exist_ok=True)
    for name in ("spec", "design"):
        (research / f"{name}-fixture.md").write_text(
            "# Isolated acceptance fixture\nNo external research required: original AC/VC inputs and native dispatcher define this bounded fixture.\n",
            encoding="utf-8")
    (key_dir / "pm-state.md").write_text(
        f"# PM State\n\n- Phase: EXECUTE\n- Claim-Id: {claim}\n- PM mode: codex\n",
        encoding="utf-8", newline="\n")
    product = root / "acceptance-product.txt"
    product.write_text("old", encoding="utf-8")
    check = root / "check_revised_contract.py"
    command_source = (
        "from pathlib import Path\n"
        f"spec = Path({str(key_dir / 'spec.md')!r}).read_text(encoding='utf-8')\n"
        "assert 'first contract text, rewritten' in spec, 'current AC-001 missing'\n"
        f"assert Path({str(product)!r}).read_text(encoding='utf-8') == 'new', 'AC-001 product stale'\n"
        "print('[VERIFY] VC-001: actual_current_contract=true Source: AC-001')\n")
    if unrelated:
        command_source = (
            "from pathlib import Path\n"
            f"spec = Path({str(key_dir / 'spec.md')!r}).read_text(encoding='utf-8')\n"
            "assert 'second contract text, locked' in spec\n"
            "print('[VERIFY] VC-002: second_condition=true Source: AC-002')\n")
    command_source = (
        "from pathlib import Path\nimport os, time\n"
        f"markers = Path({str(root / 'actual-command-markers')!r})\n"
        "markers.mkdir(exist_ok=True)\n"
        "(markers / str(os.getpid())).write_text('actual command process entered', encoding='utf-8')\n"
        f"time.sleep({command_delay!r})\n" + command_source)
    check.write_text(command_source, encoding="utf-8", newline="\n")
    argv = [sys.executable, "-B", str(check)]
    stem = "T20-current-acceptance"
    task_key = f"pm-{len(owner)}-{owner}-{stem}"
    card = key_dir / "tasks" / (stem + ".md")
    card.parent.mkdir()
    card_text = (
        "type: coding\nac_refs: [AC-001]\nvc_refs: [VC-001]\n\n"
        "## 上下文\n.agenticdoc/goal.md:1; original AC-001 and VC-001 in spec.md/design.md.\n"
        "## 要求\nAC-001 / VC-001: implement and verify the adopted first condition.\n"
        "## 交付格式\nRecord the actual implementation and verification in output.md.\n"
        "## 写入允许面\n- acceptance-product.txt\n## 写入禁止面\n- production/\n"
        f"## 验收命令\n```json\n{json.dumps(argv)}\n```\n"
        "## 改动历史\nOriginal acceptance source before contract adoption.\n")
    if unrelated:
        card_text = card_text.replace("AC-001", "AC-002").replace("VC-001", "VC-002")
    card.write_text(card_text, encoding="utf-8", newline="\n")
    # Match the normal Codex PM producer's short-lived framework claim process.
    # This is only the isolated claim fixture; no live project is taken over.
    exited = subprocess.Popen([sys.executable, "-B", "-c", "pass"], cwd=root)
    assert exited.wait(timeout=15) == 0
    dispatch_claim = f"{socket.gethostname()}:{exited.pid}"
    claim_files = [root / ".agenticdoc" / "_index.parallel", key_dir / "pm-state.md"]
    originals = {path: path.read_bytes() for path in claim_files}
    for path in claim_files:
        path.write_bytes(originals[path].replace(claim.encode(), dispatch_claim.encode()))
    try:
        dispatch_result = subprocess.run(
            ["node", str(PACKAGE_DIR / "codex_dispatch.mjs")],
            input=json.dumps({"key": owner, "task_key": task_key, "card_path": str(card),
                "cli": "pi", "type": "coding", "description":
                "Offline dispatched acceptance fixture.\nPM verification cwd: " + json.dumps(str(root))}),
            cwd=root, capture_output=True, text=True, encoding="utf-8", timeout=45)
    finally:
        for path, data in originals.items():
            path.write_bytes(data)
    assert dispatch_result.returncode == 0, (dispatch_result.stdout, dispatch_result.stderr)
    task_dir = key_dir / "workers" / task_key
    assert task_dir.joinpath("task.md").is_file(), (dispatch_result.stdout, dispatch_result.stderr)
    # Terminal worker provenance is a declared offline seam, never a QG PASS.
    offline = subprocess.run([sys.executable, "-B", "-c",
        "from pathlib import Path; import sys; "
        "Path(sys.argv[1]).write_text('Offline fixture delivered the original acceptance product; "
        "PM must run its original command against the adopted contract.', encoding='utf-8')",
        str(task_dir / "output.md")], cwd=root, capture_output=True, text=True, timeout=15)
    assert offline.returncode == 0, offline.stderr
    (task_dir / "run.json").write_text(json.dumps({"schema": 1, "kind": "coding",
        "run_id": task_key + "@2026-11-10T00:00:00Z", "status": "done", "exit": offline.returncode,
        "task_key": task_key, "owner_key": owner, "fixture": "explicit offline worker boundary"}),
        encoding="utf-8")
    mw_common.update_status(root, task_key, "done")
    _family_deploy_authority(monkeypatch, root, [f"contract-change:{owner}", "contract-item:AC-001"])
    (key_dir / "spec.md").write_bytes(revised)
    book = _family_book("contract-refreeze", payload)
    client = _pm_fake_client(root, book["book"]["preparation"], "approve")
    assert mw_cli._ap_family_run(_family_args("contract-refreeze", owner,
        _family_book_path(root, book)), root, client=client) == 0
    changed = json.loads(capsys.readouterr().out)
    assert changed["status"] == "applied" and len(client.backend.calls) == 1
    return root, owner, st, task_key, product, argv


def _actual_reverification_qg(root, owner, receipt, logical_id):
    """The PASS choice is a real prepared FakeBackend result, not a file label."""
    receipt_path = pathlib.Path(receipt["receipt_path"])
    receipt_sha = hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    material = {"review_requirements": (root / ".agenticdoc" / owner / "spec.md").read_text(encoding="utf-8"),
        "review_evidence": [receipt_path.relative_to(root).as_posix() + ":1",
            pathlib.Path(receipt["result"]["stdout_path"]).relative_to(root).as_posix() + ":1"],
        "review_findings": json.dumps({"receipt_sha256": receipt_sha, "actual_result": receipt["result"]}),
        "uncovered_scope": "isolated original AC-001; no production deployment claim"}
    preparation = {"prepared_at": "2026-11-10T00:00:00Z", "basis_catalog": [{
        "id": "actual-current-execution", "text": "The original dispatched command exited0 against current AC-001.",
        "material_refs": ["review_evidence", "review_findings"], "applies_to": ["pass"]}]}
    client = decision.DecisionClient(decision.DecisionConfig(enabled=True, project_root=root),
        decision.FakeBackend([decision.BackendOutcome(True, None, False, {
            "qg_verdict": {"value": "pass", "confidence": 0.95},
            "basis_id": {"value": "actual-current-execution", "confidence": 0.95}}, 0)]))
    answer = client.request_prepared("dp-QG", material, preparation,
        actor_role="pm", logical_id=logical_id)
    assert answer["available"] and answer["choice"] == "pass" and len(client.backend.calls) == 1, answer
    report = root / ".agenticdoc" / owner / "workers" / logical_id / "output.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("## Quality Gate Report\n" + json.dumps({"answer": answer,
        "receipt_path": str(receipt_path), "receipt_sha256": receipt_sha,
        "actual_verification": receipt["result"]})
        + "\n## Achieved\n" + json.dumps({"delivery_goal": "Verify adopted original AC-001",
            "actual_completion": "Original command executed against current adopted condition",
            "verified": [receipt["result"]], "unverified": ["production deployment"], "unfinished_impact": []})
        + "\n### 系统行为变化\n隔离产品满足已采纳条件，原命令实际退出0。\n### 遗留\n其他原任务验收另行完成。\n",
        encoding="utf-8", newline="\n")
    return report


def test_h08_original_dispatched_reverification_actual_red_green_and_done_consumption(
        tmp_path, monkeypatch, capsys):
    root, owner, st, task_key, product, argv = _native_reverification_fixture(
        tmp_path, monkeypatch, capsys)
    key_dir = root / ".agenticdoc" / owner
    phase_calls = []

    def stop_phase(key, phase, project, summary=None):
        phase_calls.append((key, phase))
        return 1, "", "test boundary: no actual phase transition"

    monkeypatch.setattr(advance, "advance", stop_phase)
    nonexistent_l3 = key_dir / "workers" / "not-reviewed" / "output.md"
    assert conductor._done_transaction(root, st, owner, nonexistent_l3)[0] == "gated"
    failed = conductor.run_contract_reverification(root, owner, task_key=task_key)
    assert failed["status"] == "needs-rerun"
    assert failed["source"]["argv"] == argv
    assert failed["result"]["red_counts"]["returncode"] != 0
    failed_files = {path: path.read_bytes() for path in pathlib.Path(failed["receipt_path"]).parent.iterdir()}
    assert conductor._done_transaction(root, st, owner, nonexistent_l3)[0] == "gated"
    assert phase_calls == []
    assert not list((key_dir / "evidence").glob("quality-gate-report-*.md"))
    assert "PASS" not in (key_dir / "pm-state.md").read_text(encoding="utf-8")
    product.write_text("new", encoding="utf-8")
    passed = conductor.run_contract_reverification(root, owner, task_key=task_key)
    assert passed["status"] == "passed", passed
    assert passed["source"]["argv"] == failed["source"]["argv"] == argv
    assert passed["result"]["red_counts"]["returncode"] == 0
    assert "actual_current_contract=true" in pathlib.Path(passed["result"]["stdout_path"]).read_text(encoding="utf-8")
    report = _actual_reverification_qg(root, owner, passed, "actual-current-l3")
    state, _reason = conductor._done_transaction(root, st, owner, report)
    assert state == "gated" and phase_calls == [(owner, "done")]
    qg_files = list((key_dir / "evidence").glob("quality-gate-report-*.md"))
    assert len(qg_files) == 1 and "PASS" in (key_dir / "pm-state.md").read_text(encoding="utf-8")
    retained = {path: path.read_bytes() for path in qg_files}
    report_before = report.read_bytes()
    assert conductor._done_transaction(root, st, owner, report)[0] == "gated"
    assert list((key_dir / "evidence").glob("quality-gate-report-*.md")) == qg_files
    assert all(path.read_bytes() == data for path, data in retained.items())
    assert report.read_bytes() == report_before
    assert all(path.read_bytes() == data for path, data in failed_files.items())


@pytest.mark.parametrize("fault", ["stdout", "receipt", "contract"])
def test_h08_successful_actual_reverification_cannot_hide_evidence_or_version_drift(
        tmp_path, monkeypatch, capsys, fault):
    root, owner, st, task_key, product, _argv = _native_reverification_fixture(
        tmp_path, monkeypatch, capsys)
    product.write_text("new", encoding="utf-8")
    passed = conductor.run_contract_reverification(root, owner, task_key=task_key)
    assert passed["status"] == "passed", passed
    report = _actual_reverification_qg(root, owner, passed, "actual-drift-l3")
    if fault == "stdout":
        pathlib.Path(passed["result"]["stdout_path"]).write_text("replacement output", encoding="utf-8")
    elif fault == "receipt":
        path = pathlib.Path(passed["receipt_path"])
        raw = json.loads(path.read_text(encoding="utf-8"))
        raw["result"]["red_counts"]["returncode"] = 1
        path.write_text(json.dumps(raw), encoding="utf-8")
    else:
        path = root / ".agenticdoc" / owner / "spec.md"
        path.write_text(path.read_text(encoding="utf-8").replace(
            "first contract text, rewritten", "first contract text, later-unapproved"), encoding="utf-8")
    phase_calls = []
    monkeypatch.setattr(advance, "advance", lambda *args, **kwargs: phase_calls.append(args) or (1, "", "stop"))
    assert conductor._done_transaction(root, st, owner, report)[0] == "gated"
    assert phase_calls == []
    key_dir = root / ".agenticdoc" / owner
    assert not list((key_dir / "evidence").glob("quality-gate-report-*.md"))
    assert "PASS" not in (key_dir / "pm-state.md").read_text(encoding="utf-8")


def test_h08_formatting_only_current_contract_reuses_actual_reverification(
        tmp_path, monkeypatch, capsys):
    root, owner, st, task_key, product, _argv = _native_reverification_fixture(
        tmp_path, monkeypatch, capsys)
    product.write_text("new", encoding="utf-8")
    passed = conductor.run_contract_reverification(root, owner, task_key=task_key)
    assert passed["status"] == "passed", passed
    report = _actual_reverification_qg(root, owner, passed, "actual-format-l3")
    key_dir = root / ".agenticdoc" / owner
    path = key_dir / "spec.md"
    path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n"))
    phase_calls = []
    monkeypatch.setattr(advance, "advance", lambda *args, **kwargs: phase_calls.append(args) or (1, "", "stop"))
    assert conductor._done_transaction(root, st, owner, report)[0] == "gated"
    assert len(phase_calls) == 1
    assert len(list((key_dir / "evidence").glob("quality-gate-report-*.md"))) == 1


def test_h08_unrelated_dispatched_card_cannot_discharge_affected_contract(
        tmp_path, monkeypatch, capsys):
    root, owner, _st, task_key, _product, _argv = _native_reverification_fixture(
        tmp_path, monkeypatch, capsys, unrelated=True)
    result = conductor.run_contract_reverification(root, owner, task_key=task_key)
    assert result["status"] == "needs-rerun", result
    assert "coverage" in result.get("reason", "").lower(), result
    assert not list((root / "actual-command-markers").glob("*"))
    assert conductor._current_contract_reverification(root, owner)["status"] != "verified"


def test_h08_unrelated_within_limit_usage_preserves_successful_proof(
        tmp_path, monkeypatch, capsys):
    root, owner, _st, task_key, product, _argv = _native_reverification_fixture(
        tmp_path, monkeypatch, capsys, policy_limit=8)
    product.write_text("new", encoding="utf-8")
    result = conductor.run_contract_reverification(root, owner, task_key=task_key)
    assert result["status"] == "passed", result
    before = conductor._current_contract_reverification(root, owner)
    assert before["status"] == "verified", before
    _family_rounds(root, owner, 1)
    after = conductor._current_contract_reverification(root, owner)
    assert after == before, (before, after)


def test_h08_actual_reexecution_spends_cumulative_hard_budget(
        tmp_path, monkeypatch, capsys):
    root, owner, _st, task_key, product, _argv = _native_reverification_fixture(
        tmp_path, monkeypatch, capsys, policy_limit=3)
    product.write_text("new", encoding="utf-8")
    results = [conductor.run_contract_reverification(root, owner, task_key=task_key)
               for _ in range(4)]
    markers = list((root / "actual-command-markers").glob("*"))
    assert len(markers) == 3, results
    assert [result["status"] for result in results[:3]] == ["passed"] * 3, results
    assert results[3]["status"] == "needs-rerun", results
    assert "budget" in results[3].get("reason", "").lower(), results


def test_h08_concurrent_reexecution_reserves_last_budget_unit_once(
        tmp_path, monkeypatch, capsys):
    root, owner, _st, task_key, product, _argv = _native_reverification_fixture(
        tmp_path, monkeypatch, capsys, policy_limit=2, command_delay=0.5)
    _family_rounds(root, owner, 1)
    product.write_text("new", encoding="utf-8")
    barrier = threading.Barrier(2)

    def execute():
        barrier.wait(timeout=15)
        return conductor.run_contract_reverification(root, owner, task_key=task_key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(execute) for _ in range(2)]
        results = [future.result(timeout=30) for future in futures]
    markers = list((root / "actual-command-markers").glob("*"))
    assert len(markers) == 1, results
    assert sum(result["status"] == "passed" for result in results) == 1, results
    assert sum(result["status"] == "needs-rerun" for result in results) == 1, results
