"""T08-A — strict host-bound local-source gate consumer (dedicated L1 suite).

Hermetic: isolated tmp project, real production consume_gate/gates/parser/object
writer/locks, real frozen T03 strict reader and physical v1 local evidence.
DP branch is exercised through the original EffectFixture; no real service, no
successful strict_verify stub, no fabricated DP lifecycle. A handwritten
fixture is NOT T15 L2 product-producer evidence.
"""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import os
import pathlib
import socket
import sys
from dataclasses import replace

import pytest

PACKAGE_DIR = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(PACKAGE_DIR))

import decision_lifecycle as lifecycle  # noqa: E402
import decision_local_evidence as lev  # noqa: E402
import decision_policy as policy  # noqa: E402
import decision_validity as validity  # noqa: E402
import decision_wire as wire  # noqa: E402
import mw_common  # noqa: E402
import test_dp_consolidation_gate_effects as base  # noqa: E402
from autopilot import config, gate_effects as ge, gates, roadmap  # noqa: E402

KEY = "owner"
LOCAL_REF = "local:t08a:1"
GATE_REF = "local(" + LOCAL_REF + ")"
ACTION = "stage:open"
BASIS_TEXT = "basis-local-1"
PM_NOTE = "prepared local gate action"
OBSERVED_EFFECT = "stage opened by local execution"
NOW = "2026-11-16T01:00:00+08:00"
BUDGET_REF = "budget:t08a"


def _live_budget(matter_ref: str, **overrides) -> dict:
    budget = {
        "schema_version": 1,
        "budget_ref": BUDGET_REF,
        "matter_ref": matter_ref,
        "parent_matter_ref": "matter:parent",
        "deadline": "2099-01-01T00:00:00+00:00",
        "max_steps": 5,
        "no_progress_limit": 3,
        "remaining_cost": 5,
        "steps_consumed": 1,
        "cost_consumed": 1,
        "no_progress_count": 0,
        "source_refs": ["tasks/T08-A:timeout=60", "run.json:remaining"],
    }
    budget.update(overrides)
    return budget


def _own(obj, name):
    """T08-A-R6: non-delegating read of a plain instance attribute.

    ``object.__getattribute__`` bypasses any user ``__getattribute__`` /
    ``__getattr__`` / descriptor on the authoritative owner's plain instance
    attributes. The REAL L1 producer and the consumer's final authority capture
    use this SAME controlled, non-delegating domain, so an owner with a custom
    attribute protocol cannot smuggle a late mutation into a "truthful" read.
    """
    return object.__getattribute__(obj, name)


class Host(ge.LocalGateHost):
    """Injected trusted host boundary (L1 only, not production T08-B wiring)."""

    def __init__(self, fixture: "LocalFixture", cell=None):
        self.f = fixture
        object.__setattr__(self, "_authority_cell",
                           cell if cell is not None else fixture.source.authority_cell)
        self.context_calls = 0
        self.verifier_calls = 0
        self.expectation_calls = 0
        self.disposition_calls = 0

    def authority_owner(self):
        """Retained FINAL callback; its return value is NOT authority.

        The real L1 producer and consumer share the one controlled cell owner.
        """
        return self._owner()

    def _owner(self):
        return object.__getattribute__(self, "_authority_cell").owner()

    def _owner_raw(self, name):
        raw, _ = ge._exact_storage(self._owner(), recursive=False)
        if not dict.__contains__(raw, name):
            raise ge.GateBlocked("controlled owner lacks field " + name)
        return dict.__getitem__(raw, name)

    def _owner_exact(self, name):
        return ge._exact_clone(self._owner_raw(name))

    def current_context(self):
        self.context_calls += 1
        return self._owner_exact("ctx")

    def verify_execution(self, record, target_digest):
        self.verifier_calls += 1
        return self._owner_exact("evidence")

    def gate_expectations(self, gate):
        self.expectation_calls += 1
        return self._owner_exact("expectations")

    def verify_disposition(self, gate, selection, execution, receipt):
        self.disposition_calls += 1
        return self._disposition(gate, selection, execution, receipt)

    def _disposition(self, gate, selection, execution, receipt):
        # A non-empty receipt is the actual post-apply object receipt. An
        # unverifiable disposition at that point must fail closed, never replay.
        if not self._owner_exact("disposition_ok"):
            return None
        if receipt and not self._owner_exact("recovery_disposition_ok"):
            return None
        source_obj = self._owner_raw("source")
        source_storage, _ = ge._exact_storage(source_obj, recursive=False)
        record_source = ge._exact_clone(dict.__getitem__(source_storage, "record_source"))
        task_key = ge._exact_clone(dict.__getitem__(source_storage, "task_key"))
        root = self._owner_exact("agenticdoc_root")
        read = lev.read_local_evidence(
            root, KEY, record_source, LOCAL_REF, task_key=task_key)
        return ge.LocalGateDisposition(
            local_ref=selection.local_ref,
            decision_ref=gate.decision_ref,
            effect_state=execution.effect_state,
            action_ref=execution.action_ref,
            result_ref=execution.result_ref,
            verifier_receipt_ref=execution.verified_by,
            target_receipt=receipt or "",
            selection_sha256=read.selection_sha256,
            execution_sha256=read.execution_sha256,
            confirmed=True,
        )

    # ── T08-A-R4: the REAL L1 terminal producer ──────────────────────────────
    # It reads the complete live state domain in one synchronous pass. It does
    # NOT call current_context / gate_expectations / verify_disposition /
    # verify_execution / observe, so the original callback counts and strict
    # mutation timings are untouched. Nothing here is a success stub or a
    # handwritten constant: every value comes from the live fixture, the real
    # frozen reader, the real strict records and the real object bytes.

    def _controlled_domain(self):
        """T08-A-R8: the REAL L1 producer's ONLY live-value source.

        The consumer-created controlled cell is the one owner association for
        producer and consumer. ``self.f`` is a compatibility alias only; all
        live reads go through the closed cell owner, so a property-backed f or
        a late raw-slot rebind cannot become a second authority source.
        """
        cell = object.__getattribute__(self, "_authority_cell")
        raw = cell.producer_domain()
        self._last_domain = raw
        return raw

    def _live_state_projections(self):
        domain = self._controlled_domain()
        return {
            "context": domain["ctx"],
            "expectations": domain["expectations"],
            "action_evidence": domain["evidence"],
            "facts_state": ge._facts_state(domain["facts"]),
            "execution_state": ge._frozen(domain["execution"]),
            "selection_state": ge._frozen(domain["selection"]),
            "disposition_state": ge._frozen({
                "disposition_ok": domain["disposition_ok"],
                "recovery_disposition_ok": domain["recovery_disposition_ok"],
            }),
        }

    def terminal_state_fingerprint(self):
        """Host-owned, read-only derivation of its CURRENT live state."""
        p = self._live_state_projections()
        return ge._terminal_live_fingerprint(**p)

    def terminal_sample(self, request):
        try:
            p = self._live_state_projections()
            domain = self._last_domain
            # Deep value freezing of the live objects (no borrowed mutable refs).
            context = dataclasses.replace(
                p["context"], budget=copy.deepcopy(dict(p["context"].budget)),
                binding=dataclasses.replace(p["context"].binding),
                parent_decision_ref=copy.deepcopy(p["context"].parent_decision_ref))
            expectations = dataclasses.replace(p["expectations"])
            action_evidence = dataclasses.replace(p["action_evidence"])
            # Real physical read + real strict records + real action receipt.
            read = lev.read_local_evidence(
                domain["agenticdoc_root"], request.source.key, request.source.record_source,
                request.source.decision_ref.local_ref, task_key=request.source.task_key)
            disposition = None
            if domain["disposition_ok"] and not (request.receipt and not domain["recovery_disposition_ok"]):
                disposition = ge.LocalGateDisposition(
                    local_ref=request.selection.local_ref,
                    decision_ref=request.gate.decision_ref,
                    effect_state=request.execution.effect_state,
                    action_ref=domain["execution"]["action_ref"],
                    result_ref=domain["execution"]["result_ref"],
                    verifier_receipt_ref=domain["execution"]["verified_by"],
                    target_receipt=request.receipt or "",
                    selection_sha256=read.selection_sha256,
                    execution_sha256=read.execution_sha256,
                    confirmed=True)
            project = pathlib.Path(request.source.agenticdoc_root).parent
            object_path = project / request.facts.action.object_path
            object_digest = "sha256:" + hashlib.sha256(object_path.read_bytes()).hexdigest()
            action = request.facts.action
            sample = ge.TerminalSample(
                source_key=request.source.key,
                record_source=request.source.record_source,
                task_key=request.source.task_key,
                local_ref=request.source.decision_ref.local_ref,
                gate_decision_ref=request.source.gate_decision_ref,
                claim_id=request.claim_id,
                phase=request.phase,
                context=context,
                expectations=expectations,
                disposition=disposition,
                action_evidence=action_evidence,
                facts_state=p["facts_state"],
                action_identity=(action.name, action.object_path.as_posix(),
                                 action.legacy_closure, action.lifecycle_action),
                selection=copy.deepcopy(request.selection),
                execution=copy.deepcopy(request.execution),
                selection_sha256=read.selection_sha256,
                execution_sha256=read.execution_sha256,
                object_digest=object_digest,
                receipt=request.receipt or "",
                gate_identity=(request.gate.decision_ref, request.gate.matter_ref,
                               request.gate.substantive_version, request.gate.business,
                               request.gate.pm_note),
                execution_state=p["execution_state"],
                selection_state=p["selection_state"],
                disposition_state=p["disposition_state"],
                state_fingerprint="")
            fingerprint = ge._terminal_live_fingerprint(
                context=sample.context, expectations=sample.expectations,
                action_evidence=sample.action_evidence, facts_state=sample.facts_state,
                execution_state=sample.execution_state, selection_state=sample.selection_state,
                disposition_state=sample.disposition_state)
            return replace(sample, state_fingerprint=fingerprint)
        except Exception:
            # A producer that cannot supply a complete coherent sample fails
            # closed. No "all-good" fallback and no fabricated success token.
            return None


class LocalFixture:
    def __init__(self, tmp: pathlib.Path):
        self.tmp = tmp
        self.root = tmp / "project"
        self.agenticdoc_root = self.root / ".agenticdoc"
        self.claim = f"{socket.gethostname()}:{os.getpid()}"
        config.save_config(self.root, {"enabled": True, "paused": False, "auto_gate_mode": "live"})
        self.index = self.root / ".agenticdoc/_index.parallel"
        self.index.parent.mkdir(parents=True, exist_ok=True)
        self.index.write_text(
            f"| {KEY} | active | EXECUTE | {self.claim} | - | test | now |\n", encoding="utf-8")
        self.map = roadmap.roadmap_path(self.root)
        self.map.write_text(
            "## Stage 1: fixture\n> goal: release the fixture\n> status: pending\n"
            "### Keys\n| key | role | depends_on |\n|-----|------|-----------|\n"
            f"| {KEY} | implement | - |\n", encoding="utf-8")
        self.before_sha = hashlib.sha256(self.map.read_bytes()).hexdigest()
        self.authority = policy.AuthorityRecord("signed-scope", "user-grant", (ACTION,), "controlled-human")
        policy.policy_path(self.root).write_text(json.dumps({
            "schema_version": 1, "authority_ref": "signed-scope", "scope": [ACTION],
            "hard_limits": [{"unit": "steps", "limit": 3, "usage_source": "recorded-steps"}],
        }), encoding="utf-8")
        self.note = PM_NOTE
        self.matter = validity.matter_for(
            KEY, "stage-1", ACTION, [validity.DependencyState("note", "structured", self.note)],
            matter_kind="gate-action", contract_version="v1", authority_required=True)
        self.gate = gates.create(
            self.root / ".agenticdoc/_autopilot/gates", "stage-confirm", "Open this stage?", key=KEY,
            pm_note=self.note, matter_ref=self.matter.matter_key,
            substantive_version=self.matter.substantive_version)
        answered = base._answer(
            self.gate, decision="approve", modelBasis=BASIS_TEXT, decisionRef=GATE_REF,
            matterRef=self.matter.matter_key, substantiveVersion=self.matter.substantive_version,
            answeredBy=self.claim)
        assert answered["ok"] is True, answered
        self.calls = 0
        self.action = ge.BoundAction(ACTION, self.map.relative_to(self.root), self.apply, self.inspect)
        self.facts = ge.GateFacts(
            self.matter, self.note, (ACTION,), {"signed-scope": self.authority}, ("controlled-human",),
            {"delivery-evidence": True}, {"recorded-steps": 1}, {"steps": 1}, self.action)
        host_binding = {
            "role": "pm", "owner": self.claim, "claim_id": self.claim, "key": KEY,
            "run_id": "run-t08a", "binding_version": "v1", "observed_at": NOW,
        }
        self.material_digest = "sha256:" + hashlib.sha256(self.note.encode()).hexdigest()
        self.basis_digest = "sha256:" + hashlib.sha256(BASIS_TEXT.encode()).hexdigest()
        self.selection = {
            "schema_version": 1, "kind": "local-selection", "origin": "local-decision",
            "source": "pm", "local_ref": LOCAL_REF, "matter_ref": self.matter.matter_key,
            "host_binding": host_binding, "matter_version": self.matter.substantive_version,
            "material_digest": self.material_digest, "basis_digest": self.basis_digest,
            "selected_action": ACTION, "selected_basis_id": "b1", "budget_ref": BUDGET_REF,
            "action_state": "planned", "business_completed": False, "created_at": NOW,
        }
        self.target_digest = "sha256:" + self.before_sha
        self.execution = {
            "schema_version": 1, "kind": "local-execution", "origin": "local-decision",
            "source": "pm", "local_ref": LOCAL_REF, "host_binding": host_binding,
            "action_ref": "tool_call:local:1", "result_ref": "tool_result:local:1",
            "executor": "pm-orchestrator", "target_digest": self.target_digest,
            "observed_effect": OBSERVED_EFFECT, "effect_state": "known",
            "verified_by": "target-verifier:1", "budget_ref": BUDGET_REF, "created_at": NOW,
        }
        self.handoff_dir = self.agenticdoc_root / KEY / "evidence" / "decision-handoffs"
        self.handoff_dir.mkdir(parents=True, exist_ok=True)
        encoded = lev.encode_local_ref(LOCAL_REF)
        self.selection_path = self.handoff_dir / (encoded + ".json")
        self.execution_path = self.handoff_dir / (encoded + ".execution.json")
        self._write_records()
        self.ctx = lev.TrustedContext(
            binding=lev.TrustedBinding(
                authority=lev.AUTHORITATIVE_BINDING_KIND,
                coordination_row_ref="workers.parallel:row:7", is_active=True, active_row_count=1,
                role="pm", binding_version="v1", observed_at=NOW, owner=self.claim,
                claim_id=self.claim, key=KEY, task_key=None, run_id="run-t08a"),
            matter_ref=self.matter.matter_key, matter_version=self.matter.substantive_version,
            material_digest=self.material_digest, basis_digest=self.basis_digest,
            target_digest=self.target_digest, budget=_live_budget(self.matter.matter_key),
            parent_decision_ref=None, stop_scope="none")
        self.evidence = lev.ActionResultEvidence(
            action_receipt_ref=self.execution["action_ref"],
            result_receipt_ref=self.execution["result_ref"],
            verifier_receipt_ref=self.execution["verified_by"],
            observed_object_digest=self.target_digest, confirmed=True)
        self.expectations = ge.LocalGateExpectations(
            gate_decision_ref=GATE_REF, matter_ref=self.matter.matter_key,
            substantive_version=self.matter.substantive_version, pm_note=PM_NOTE,
            model_basis=BASIS_TEXT, material_digest=self.material_digest,
            basis_digest=self.basis_digest, selected_action=ACTION, selected_basis_id="b1",
            budget_ref=BUDGET_REF, target_digest=self.target_digest,
            action_ref=self.execution["action_ref"], result_ref=self.execution["result_ref"],
            verifier_ref=self.execution["verified_by"], effect_state="known",
            observed_effect=OBSERVED_EFFECT, local_ref=LOCAL_REF, key=KEY, task_key=None,
            record_source="pm", claim_id=self.claim)
        # T08-A-R8: ONE consumer-created controlled cell is bound to the real
        # L1 producer and to the source BEFORE any host callback.
        self.cell = ge.ControlledAuthorityCell(self)
        self.host = Host(self, cell=self.cell)
        self.source = ge.LocalGateSource(
            decision_ref=lev.LocalDecisionRef(local_ref=LOCAL_REF),
            agenticdoc_root=self.agenticdoc_root, key=KEY, record_source="pm", task_key=None,
            gate_decision_ref=GATE_REF, host=self.host, owner_state=self,
            authority_cell=self.cell)
        self.disposition_ok = True
        self.recovery_disposition_ok = True

    def _write_records(self) -> None:
        self.selection_path.write_bytes(json.dumps(self.selection, ensure_ascii=False, indent=2).encode("utf-8"))
        self.execution_path.write_bytes(json.dumps(self.execution, ensure_ascii=False, indent=2).encode("utf-8"))

    def mutate_selection(self, **changes) -> None:
        self.selection.update(changes)
        self.selection_path.write_bytes(json.dumps(self.selection, ensure_ascii=False, indent=2).encode("utf-8"))

    def mutate_execution(self, **changes) -> None:
        self.execution.update(changes)
        self.execution_path.write_bytes(json.dumps(self.execution, ensure_ascii=False, indent=2).encode("utf-8"))

    def set_gate_decision_ref(self, value: str) -> None:
        lines = self.gate.read_text(encoding="utf-8").splitlines(keepends=True)
        for i, line in enumerate(lines):
            if line.startswith("decision_ref:"):
                ending = line[len(line.rstrip("\r\n")):]
                lines[i] = "decision_ref: " + value + ending
                break
        gates._write_atomic(self.gate, "".join(lines))

    def apply(self, gate):
        self.calls += 1
        assert not (self.root / ".mw/gates.lock").exists()
        target_lock = self.root / ".mw/roadmap.lock"
        mw_common.acquire_lock(target_lock, retries=0)
        try:
            if hashlib.sha256(self.map.read_bytes()).hexdigest() != self.before_sha:
                raise ge.ActionNotApplied
            text = roadmap.update_stage_status(self.map.read_text(encoding="utf-8"), 1, "running")
            gates._write_atomic(self.map, f"<!-- {gate.decision_ref} -->\n" + text)
        finally:
            mw_common.release_lock(target_lock)

    def inspect(self, gate):
        data = self.map.read_bytes()
        if f"<!-- {gate.decision_ref} -->".encode() not in data:
            return None
        observed = roadmap.stage_by_number(roadmap.load_roadmap(self.map), 1)
        if observed.status != "running":
            return None
        return ge.ObjectReceipt(gate.decision_ref, hashlib.sha256(data).hexdigest())

    def consume(self, **overrides):
        kwargs = {"source": self.source}
        kwargs.update(overrides)
        return ge.consume_gate(
            self.root, self.gate.stem, claim_id=self.claim,
            observe=lambda gate: self.facts, **kwargs)


def _no_dp_sink(f: LocalFixture) -> bool:
    return not wire.production_lifecycle_sink(f.root).exists()


def _to_worker_local(f: LocalFixture) -> None:
    """Rebind the SAME physical v1 evidence to a worker-local task/run/claim."""
    task, run = "w-t08a", "run-t08a-w"
    worker_claim = f"worker:{os.getpid()}"
    hb = {
        "role": "coding", "owner": worker_claim, "claim_id": worker_claim, "key": KEY,
        "task_key": task, "run_id": run, "binding_version": "v1", "observed_at": NOW,
    }
    sel, ex = dict(f.selection), dict(f.execution)
    sel.update(source="worker-local", host_binding=hb)
    ex.update(source="worker-local", host_binding=hb)
    base = f.agenticdoc_root / KEY / "workers" / task / "local-decisions"
    base.mkdir(parents=True, exist_ok=True)
    encoded = lev.encode_local_ref(LOCAL_REF)
    f.selection_path = base / (encoded + ".json")
    f.execution_path = base / (encoded + ".execution.json")
    f.selection_path.write_bytes(json.dumps(sel, ensure_ascii=False, indent=2).encode("utf-8"))
    f.execution_path.write_bytes(json.dumps(ex, ensure_ascii=False, indent=2).encode("utf-8"))
    f.selection, f.execution, f.handoff_dir = sel, ex, base
    f.ctx = replace(f.ctx, binding=replace(
        f.ctx.binding, role="coding", owner=worker_claim, claim_id=worker_claim,
        key=KEY, task_key=task, run_id=run))
    f.expectations = replace(f.expectations, record_source="worker-local", task_key=task)
    f.source = replace(f.source, record_source="worker-local", task_key=task)


@pytest.fixture(autouse=True)
def _clear_worker_env(monkeypatch):
    # This L1 suite models the live PM window. The outer MW worker harness sets
    # PI_WORKER_TASK; the original _check_facts correctly refuses a worker
    # context, so a positive gate consume must clear it for the fixture only.
    monkeypatch.delenv("PI_WORKER_TASK", raising=False)


# ── positive: original DP branch is unchanged ────────────────────────────────

def test_legal_dp_gate_still_applies_once_without_a_local_source(tmp_path):
    f = base.EffectFixture(tmp_path, "approve")
    before = f.map.read_bytes()
    result = f.consume()
    assert result.state == "applied" and result.parent_ref == f.ref, result
    assert gates.parse(f.gate).effect == "applied"
    assert f.calls == 1 and f.map.read_bytes() != before
    replay = f.consume()
    assert replay.state == "applied" and replay.duplicate and f.calls == 1
    rows = [r for r in f.events() if r["lifecycle"] == "executed"]
    assert len(rows) == 1


# ── positive: strict local execution releases once, duplicate never re-applies ─

def test_verified_local_execution_releases_once_and_duplicate_does_not_reapply(tmp_path):
    f = LocalFixture(tmp_path)
    evidence_before = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    result = f.consume()
    assert result.state == "applied" and result.receipt and "#" in result.receipt, result
    assert result.parent_ref == GATE_REF
    assert gates.parse(f.gate).effect == "applied"
    assert f.calls == 1
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == evidence_before
    assert _no_dp_sink(f)
    replay = f.consume()
    assert replay.state == "applied" and replay.duplicate and replay.receipt == result.receipt, replay
    assert f.calls == 1 and gates.parse(f.gate).effect == "applied"
    assert _no_dp_sink(f)


def test_worker_local_execution_also_releases_once_without_a_dp_identity(tmp_path):
    f = LocalFixture(tmp_path)
    _to_worker_local(f)
    result = f.consume()
    assert result.state == "applied" and result.parent_ref == GATE_REF, result
    assert f.calls == 1 and gates.parse(f.gate).effect == "applied"
    assert _no_dp_sink(f)
    replay = f.consume()
    assert replay.state == "applied" and replay.duplicate and f.calls == 1


# ── negatives: no side effect, no false DP lifecycle ─────────────────────────

NEGATIVE_FAULTS = (
    "planned-only", "unknown-effect", "bad-parent", "bad-material", "bad-basis",
    "bad-claim", "bad-run", "bad-target", "bad-grant", "bad-scope",
    "hard-budget", "fake-source-string", "fake-dp-ref", "dp-shaped-local-ref",
    "gate-text-dp-ref-without-source", "pseudo-dp-gate-ref", "changed-object",
    "missing-adapter", "missing-context", "missing-expectations",
    "missing-disposition", "worker-context", "claim-index-changed",
    "stopped-scope", "budget-exhausted",
)


def _apply_fault(f: LocalFixture, fault: str, monkeypatch) -> dict:
    overrides: dict = {}
    if fault == "planned-only":
        f.execution_path.unlink()
    elif fault == "unknown-effect":
        f.mutate_execution(effect_state="unknown")
    elif fault == "bad-parent":
        f.mutate_selection(parent_decision_ref={"kind": "dp", "decision_id": "dp-auto:wrong"})
    elif fault == "bad-material":
        f.mutate_selection(material_digest="sha256:changed")
    elif fault == "bad-basis":
        f.mutate_selection(basis_digest="sha256:changed")
    elif fault == "bad-claim":
        f.ctx = replace(f.ctx, binding=replace(f.ctx.binding, claim_id="foreign:1"))
    elif fault == "bad-run":
        f.ctx = replace(f.ctx, binding=replace(f.ctx.binding, run_id="old-run"))
    elif fault == "bad-target":
        f.ctx = replace(f.ctx, target_digest="sha256:wrong")
        f.expectations = replace(f.expectations, target_digest="sha256:wrong")
    elif fault == "bad-grant":
        f.facts = replace(f.facts, authority_source={})
    elif fault == "bad-scope":
        f.facts = replace(f.facts, scope=("unrelated",))
    elif fault == "hard-budget":
        f.facts = replace(f.facts, usage_by_source={"recorded-steps": 3})
    elif fault == "fake-source-string":
        overrides["source"] = "local"
    elif fault == "fake-dp-ref":
        overrides["source"] = replace(f.source, decision_ref=lev.DpDecisionRef(decision_id="dp-gate-approve:x"))
    elif fault == "dp-shaped-local-ref":
        bad = "dp-gate-approve:evil"
        f.set_gate_decision_ref("local(" + bad + ")")
        overrides["source"] = replace(
            f.source, decision_ref=lev.LocalDecisionRef(local_ref=bad),
            gate_decision_ref="local(" + bad + ")")
    elif fault == "gate-text-dp-ref-without-source":
        f.set_gate_decision_ref("dp-gate-approve:logical-x")
        overrides.update(source=None, store=None, meta=None)
    elif fault == "pseudo-dp-gate-ref":
        f.set_gate_decision_ref("dp-gate-approve:logical-x")
    elif fault == "changed-object":
        with f.map.open("a", encoding="utf-8") as handle:
            handle.write("external edit\n")
    elif fault == "missing-adapter":
        overrides["source"] = replace(f.source, host=object())
    elif fault == "missing-context":
        f.ctx = None
    elif fault == "missing-expectations":
        f.expectations = None
    elif fault == "missing-disposition":
        f.disposition_ok = False
    elif fault == "worker-context":
        monkeypatch.setenv("PI_WORKER_TASK", str(f.tmp / "worker/task.md"))
    elif fault == "claim-index-changed":
        f.index.write_text(f.index.read_text().replace(f.claim, "other:1"))
    elif fault == "stopped-scope":
        f.ctx = replace(f.ctx, stop_scope="matter")
    elif fault == "budget-exhausted":
        f.ctx = replace(f.ctx, budget=_live_budget(f.matter.matter_key, steps_consumed=5))
    else:
        raise AssertionError(fault)
    return overrides


@pytest.mark.parametrize("fault", NEGATIVE_FAULTS)
def test_local_negative_faults_never_apply_or_write_dp_lifecycle(tmp_path, monkeypatch, fault):
    f = LocalFixture(tmp_path)
    overrides = _apply_fault(f, fault, monkeypatch)
    before_map = f.map.read_bytes()
    result = f.consume(**overrides)
    assert result.state == "blocked" and result.reason, (fault, result)
    assert f.calls == 0, fault
    assert gates.parse(f.gate).effect == "not-started", fault
    assert f.map.read_bytes() == before_map, fault
    assert _no_dp_sink(f), fault


# ── recovery: unknown/unpersisted effect is inspected read-only, never replayed ─

def test_unknown_local_effect_is_not_replayed_when_disposition_is_unverified(tmp_path):
    f = LocalFixture(tmp_path)
    # Simulate an earlier reserved write whose object marker exists, but whose
    # disposition cannot be independently verified by the host afterwards.
    f.apply(gates.parse(f.gate))
    ge._replace_effect(gates.parse(f.gate), "unknown")
    f.recovery_disposition_ok = False
    result = f.consume()
    assert result.state == "unknown" and result.reason, result
    assert f.calls == 1  # the pre-existing write only; consume never re-applies
    assert gates.parse(f.gate).effect == "unknown"
    assert _no_dp_sink(f)


def test_changed_object_hash_never_releases_a_local_gate(tmp_path):
    f = LocalFixture(tmp_path)
    with f.map.open("a", encoding="utf-8") as handle:
        handle.write("concurrent external edit\n")
    result = f.consume()
    assert result.state == "blocked" and f.calls == 0
    assert gates.parse(f.gate).effect == "not-started"
    assert _no_dp_sink(f)


def test_local_source_never_calls_dp_lifecycle_writers(tmp_path, monkeypatch):
    called = []

    def forbid(name):
        def inner(*args, **kwargs):
            called.append(name)
            raise AssertionError("DP lifecycle writer called from local branch: " + name)
        return inner

    for name in ("record_consumed", "record_executed", "record_settled"):
        monkeypatch.setattr(lifecycle, name, forbid(name))
    f = LocalFixture(tmp_path)
    result = f.consume()
    assert result.state == "applied", result
    assert called == []
    assert _no_dp_sink(f)


# ── T08-A-R1: P1-2/F2 physical terminal boundary + P2/F3 expected effect ───

@pytest.fixture
def strict_counter(monkeypatch):
    """Pass-through counter around the REAL frozen strict reader; no stub/success."""
    calls = []
    real_strict = lev.strict_verify

    def counted(*args, **kwargs):
        result = real_strict(*args, **kwargs)
        calls.append({
            "which": kwargs.get("which"),
            "verification": result.verification,
            "failure_codes": tuple(result.failure_codes),
        })
        return result

    monkeypatch.setattr(lev, "strict_verify", counted)
    return calls


def _bind_worker_local(f: LocalFixture) -> None:
    _to_worker_local(f)


@pytest.mark.parametrize("worker_local", [False, True])
def test_r1_host_expected_unknown_effect_is_rejected_before_reservation(
        tmp_path, strict_counter, worker_local):
    f = LocalFixture(tmp_path)
    if worker_local:
        _bind_worker_local(f)
    f.expectations = replace(f.expectations, effect_state="unknown")
    before_map = f.map.read_bytes()
    before_execution = f.execution_path.read_bytes()
    result = f.consume()
    assert result.state == "blocked" and "effect state" in result.reason, result
    assert f.calls == 0
    assert gates.parse(f.gate).effect == "not-started"
    assert f.map.read_bytes() == before_map
    assert f.execution_path.read_bytes() == before_execution
    assert json.loads(f.execution_path.read_text(encoding="utf-8"))["effect_state"] == "known"
    assert f.host.expectation_calls >= 1
    assert f.host.disposition_calls == 0
    assert [call["which"] for call in strict_counter][:2] == ["selection", "execution"]
    assert all(call["verification"] == "strict-verified" for call in strict_counter)
    assert _no_dp_sink(f)


@pytest.mark.parametrize("worker_local", [False, True])
@pytest.mark.parametrize("fault", ["stop", "budget", "delete"])
def test_r1_final_pre_apply_callback_invalidation_blocks_before_writer(
        tmp_path, strict_counter, worker_local, fault):
    f = LocalFixture(tmp_path)
    if worker_local:
        _bind_worker_local(f)

    class LateHost(Host):
        def _disposition(self, gate, selection, execution, receipt):
            result = super()._disposition(gate, selection, execution, receipt)
            if self.disposition_calls == 2:
                if fault == "stop":
                    self.f.ctx = replace(self.f.ctx, stop_scope="matter")
                elif fault == "budget":
                    self.f.ctx = replace(self.f.ctx, budget=_live_budget(
                        self.f.matter.matter_key, steps_consumed=5))
                else:
                    self.f.execution_path.unlink()
            return result

    f.host = LateHost(f)
    f.source = replace(f.source, host=f.host)
    before_map = f.map.read_bytes()
    result = f.consume()
    assert result.state == "blocked" and result.reason, (fault, result)
    assert f.calls == 0, fault
    assert gates.parse(f.gate).effect == "not-started", fault
    assert f.map.read_bytes() == before_map, fault
    assert f.host.disposition_calls == 2, fault
    assert f.host.expectation_calls >= 2, fault
    assert sum(1 for call in strict_counter if call["which"] == "execution") >= 2, fault
    if fault == "stop":
        assert f.ctx.stop_scope == "matter"
        assert json.loads(f.execution_path.read_text(encoding="utf-8"))["effect_state"] == "known"
    elif fault == "budget":
        assert f.ctx.budget["steps_consumed"] == 5
        assert json.loads(f.execution_path.read_text(encoding="utf-8"))["effect_state"] == "known"
    else:
        assert not f.execution_path.exists()
    assert _no_dp_sink(f), fault


def test_r1_strict_values_must_match_final_physical_snapshot(tmp_path, monkeypatch):
    f = LocalFixture(tmp_path)
    real_strict = lev.strict_verify
    state = {"mutated": False}

    def race_after_real_strict(*args, **kwargs):
        result = real_strict(*args, **kwargs)
        if kwargs.get("which") == "execution" and not state["mutated"]:
            f.mutate_execution(effect_state="unknown")
            state["mutated"] = True
        return result

    monkeypatch.setattr(lev, "strict_verify", race_after_real_strict)
    before_map = f.map.read_bytes()
    result = f.consume()
    assert result.state == "blocked" and "strict" in result.reason, result
    assert f.calls == 0
    assert gates.parse(f.gate).effect == "not-started"
    assert f.map.read_bytes() == before_map
    assert json.loads(f.execution_path.read_text(encoding="utf-8"))["effect_state"] == "unknown"
    assert state["mutated"] is True
    assert f.host.disposition_calls == 0
    assert _no_dp_sink(f)


@pytest.mark.parametrize("worker_local", [False, True])
def test_r1_post_apply_physical_unknown_is_archived_unknown_without_replay(
        tmp_path, strict_counter, worker_local):
    f = LocalFixture(tmp_path)
    if worker_local:
        _bind_worker_local(f)

    class LateHost(Host):
        def _disposition(self, gate, selection, execution, receipt):
            result = super()._disposition(gate, selection, execution, receipt)
            if receipt:
                self.f.mutate_execution(effect_state="unknown")
            return result

    f.host = LateHost(f)
    f.source = replace(f.source, host=f.host)
    before_map = f.map.read_bytes()
    result = f.consume()
    after_map = f.map.read_bytes()
    assert after_map != before_map
    assert result.state == "unknown" and "terminal boundary" in result.reason, result
    assert gates.parse(f.gate).effect == "unknown"
    assert f.calls == 1
    assert f.host.disposition_calls == 3
    assert f.host.expectation_calls >= 3
    assert json.loads(f.execution_path.read_text(encoding="utf-8"))["effect_state"] == "unknown"
    assert sum(1 for call in strict_counter if call["which"] == "execution") >= 3
    assert _no_dp_sink(f)
    replay = f.consume()
    assert replay.state != "applied", replay
    assert gates.parse(f.gate).effect == "unknown"
    assert f.calls == 1
    assert f.map.read_bytes() == after_map
    assert _no_dp_sink(f)


def test_r1_local_terminal_recheck_uses_real_strict_without_extra_disposition(
        tmp_path, strict_counter):
    f = LocalFixture(tmp_path)
    result = f.consume()
    assert result.state == "applied", result
    assert f.calls == 1
    assert f.host.disposition_calls == 3
    assert f.host.expectation_calls >= 4
    assert sum(1 for call in strict_counter if call["which"] == "execution") >= 4
    assert all(call["verification"] == "strict-verified" for call in strict_counter)
    assert gates.parse(f.gate).effect == "applied"
    assert _no_dp_sink(f)


def test_r1_dp_branch_bypasses_local_verification_and_terminal_recheck(tmp_path, monkeypatch):
    called = []

    def forbid(name):
        def inner(*args, **kwargs):
            called.append(name)
            raise AssertionError("DP branch invoked local verification: " + name)
        return inner

    monkeypatch.setattr(ge, "_verify_local", forbid("verify_local"))
    monkeypatch.setattr(ge, "_terminal_local", forbid("terminal_local"))
    f = base.EffectFixture(tmp_path, "approve")
    result = f.consume()
    assert result.state == "applied", result
    assert f.calls == 1
    assert called == []


# ── T08-A-R2: the LAST strict callback must not outlive gate authorization ──

R2_FAULTS = ("budget", "claim", "config", "policy", "inplace-authority",
             "inplace-hard-checks", "inplace-usage")


def _r2_inject(f: LocalFixture, fault: str) -> None:
    """Change an INDEPENDENT gate-authorization fact, never evidence bytes."""
    if fault == "budget":
        f.facts.usage_by_source["recorded-steps"] = 3
    elif fault == "claim":
        f.index.write_text(
            f"| {KEY} | idle | EXECUTE | {f.claim} | - | test | now |\n", encoding="utf-8")
    elif fault == "config":
        config.save_config(f.root, {"enabled": False, "paused": False, "auto_gate_mode": "live"})
    elif fault == "policy":
        path = policy.policy_path(f.root)
        value = json.loads(path.read_text(encoding="utf-8"))
        value["scope"] = []
        path.write_text(json.dumps(value), encoding="utf-8")
    elif fault == "inplace-authority":
        f.facts.authority_source.clear()
    elif fault == "inplace-hard-checks":
        f.facts.hard_checks["delivery-evidence"] = False
    elif fault == "inplace-usage":
        f.facts.usage_by_source["recorded-steps"] = 3
    else:
        raise AssertionError(fault)


class R2LateHost(Host):
    """Real strict pass-through; invalidate gate state in a chosen LAST window."""

    def __init__(self, f: LocalFixture, *, trigger: int, window: str, fault: str):
        super().__init__(f)
        self.trigger = trigger
        self.window = window
        self.fault = fault
        self.armed = False
        self.mutations: list[dict] = []

    def verify_execution(self, record, target_digest):
        evidence = super().verify_execution(record, target_digest)
        if self.verifier_calls == self.trigger:
            if self.window == "verifier":
                self.mutations.append({"window": "verify_execution",
                                       "call": self.verifier_calls, "body": self.f.calls})
                _r2_inject(self.f, self.fault)
            else:
                self.armed = True
        return evidence

    def current_context(self):
        context = super().current_context()
        # The NEXT current_context after the armed verifier is strict_verify's
        # FINAL host callback; mutate while that window is open.
        if self.armed and not self.mutations:
            self.mutations.append({"window": "final_current_context",
                                   "call": self.context_calls, "body": self.f.calls})
            _r2_inject(self.f, self.fault)
        return context


def _r2_prepare(tmp_path, timing, fault, window, worker_local):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    trigger = 3 if timing == "pre" else 4
    host = R2LateHost(f, trigger=trigger, window=window, fault=fault)
    f.host = host
    f.source = replace(f.source, host=host)
    return f, host


@pytest.mark.parametrize("timing", ["pre", "post"])
@pytest.mark.parametrize("fault", R2_FAULTS)
@pytest.mark.parametrize("window", ["verifier", "final-context"])
def test_r2_last_strict_callback_authority_is_checked_before_reservation(
        tmp_path, timing, fault, window):
    f, host = _r2_prepare(tmp_path, timing, fault, window, False)
    before_map = f.map.read_bytes()
    result = f.consume()
    calls_before_retry = f.calls
    retry = f.consume()
    assert host.mutations, (timing, fault, window)
    assert host.mutations[0]["body"] == (0 if timing == "pre" else 1), (timing, fault, window)
    assert _no_dp_sink(f)
    assert f.calls == calls_before_retry, "an unknown effect must never replay"
    if timing == "pre":
        assert calls_before_retry == 0, (timing, fault, window, result)
        assert result.state == "blocked", (timing, fault, window, result)
        assert gates.parse(f.gate).effect == "not-started"
        assert f.map.read_bytes() == before_map
    else:
        assert calls_before_retry == 1, (timing, fault, window, result)
        assert result.state == "unknown", (timing, fault, window, result)
        assert gates.parse(f.gate).effect == "unknown"
        assert retry.state != "applied", (timing, fault, window, retry)
        assert gates.parse(f.gate).effect == "unknown"


@pytest.mark.parametrize("timing", ["pre", "post"])
@pytest.mark.parametrize("fault", ["claim", "budget", "inplace-authority"])
@pytest.mark.parametrize("window", ["verifier", "final-context"])
def test_r2_worker_local_still_requires_the_independent_live_pm_claim(
        tmp_path, timing, fault, window):
    # worker-local evidence binds a worker claim/run; it can NEVER replace the
    # gate's own live PM index/claim check at the last strict callback.
    f, host = _r2_prepare(tmp_path, timing, fault, window, True)
    before_map = f.map.read_bytes()
    result = f.consume()
    calls_before_retry = f.calls
    retry = f.consume()
    assert host.mutations, (timing, fault, window)
    assert host.mutations[0]["body"] == (0 if timing == "pre" else 1)
    assert _no_dp_sink(f)
    assert f.calls == calls_before_retry
    if timing == "pre":
        assert calls_before_retry == 0
        assert result.state == "blocked", (timing, fault, window, result)
        assert gates.parse(f.gate).effect == "not-started"
        assert f.map.read_bytes() == before_map
    else:
        assert calls_before_retry == 1
        assert result.state == "unknown", (timing, fault, window, result)
        assert gates.parse(f.gate).effect == "unknown"
        assert retry.state != "applied"


@pytest.mark.parametrize("trigger,expected_state,expected_calls", [
    (4, "blocked", 0),   # LAST observe of the pre-apply terminal boundary
    (6, "unknown", 1),   # LAST observe of the post-apply terminal boundary
])
def test_r2_final_observe_callback_change_is_checked_before_or_after_apply(
        tmp_path, trigger, expected_state, expected_calls):
    f = LocalFixture(tmp_path)
    events: list[object] = []

    def observing(gate):
        events.append(len(events) + 1)
        if len(events) == trigger:
            f.facts.usage_by_source["recorded-steps"] = 3
            events.append("mutated-in-final-observe")
        return f.facts

    before_map = f.map.read_bytes()
    result = ge.consume_gate(f.root, f.gate.stem, claim_id=f.claim,
                             observe=observing, source=f.source)
    assert "mutated-in-final-observe" in events, events
    assert result.state == expected_state, (trigger, result, events)
    assert f.calls == expected_calls, (trigger, result, events)
    assert _no_dp_sink(f)
    if expected_state == "blocked":
        assert gates.parse(f.gate).effect == "not-started"
        assert f.map.read_bytes() == before_map
    else:
        assert gates.parse(f.gate).effect == "unknown"
        retry = f.consume()
        assert retry.state != "applied"
        assert f.calls == 1


@pytest.mark.parametrize("worker_local", [False, True])
def test_r2_unchanged_l1_control_still_releases_exactly_once(tmp_path, worker_local):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    result = f.consume()
    assert result.state == "applied", result
    assert f.calls == 1
    assert gates.parse(f.gate).effect == "applied"
    assert _no_dp_sink(f)
    replay = f.consume()
    assert replay.state == "applied" and replay.duplicate
    assert f.calls == 1


# ── T08-A-R3-D: existing finite deadline after the LAST pre callback ───────

from datetime import datetime as _dt, timedelta as _timedelta, timezone as _timezone  # noqa: E402
from types import SimpleNamespace as _SimpleNamespace  # noqa: E402
import time as _time  # noqa: E402


def _r3d_patch_reader_clock(monkeypatch, now_iso_fn, readings):
    """Inject ONLY the frozen reader's clock dependency; strict stays real."""
    class Clock(_dt):
        @classmethod
        def fromisoformat(cls, text):
            return _dt.fromisoformat(str(text))

        @classmethod
        def now(cls, tz=None):
            value = _dt.fromisoformat(str(now_iso_fn()).replace("Z", "+00:00"))
            if value.tzinfo is None:
                value = value.replace(tzinfo=_timezone.utc)
            readings.append(value.isoformat())
            return value if tz is None else value.astimezone(tz)

    monkeypatch.setattr(lev, "_dt", _SimpleNamespace(datetime=Clock, timezone=_timezone))


def _r3d_realwall_observe(f, deadline, strict_counter, *, cross, classification):
    """Bounded real wall-clock callback; records enter/return and real strict."""
    event = {
        "real_wall_clock": True, "controlled_clock_only": False,
        "classification": classification, "deadline": deadline.isoformat(),
        "final_pre_observe_reached": False, "cross": cross,
    }
    count = 0

    def observing(gate):
        nonlocal count
        count += 1
        if count == 4:
            event["final_pre_observe_reached"] = True
            entered = _dt.now(_timezone.utc)
            event.update({
                "entered": entered.isoformat(),
                "entered_before_deadline": entered < deadline,
                "body_at_enter": f.calls,
                "real_strict_calls_at_enter": list(strict_counter),
                "real_verify_execution_calls": f.host.verifier_calls,
            })
            if cross:
                assert entered < deadline, (
                    "INVALID EXPERIMENT: setup crossed the deadline before the last pre observe; "
                    "strict could not have passed within the original finite budget")
                limit = _time.monotonic() + 3.0
                while _dt.now(_timezone.utc) <= deadline:
                    assert _time.monotonic() < limit, "bounded final callback delay exceeded 3s"
                    _time.sleep(0.01)
                returned = _dt.now(_timezone.utc)
                event.update({
                    "returned": returned.isoformat(),
                    "returned_after_deadline": returned > deadline,
                })
        return f.facts

    return observing, event


@pytest.mark.parametrize("worker_local", [False, True])
def test_r3d_unexpired_finite_budget_still_applies_once(
        tmp_path, strict_counter, worker_local):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    deadline = _dt.now(_timezone.utc) + _timedelta(seconds=60)
    f.ctx.budget["deadline"] = deadline.isoformat()
    observing, event = _r3d_realwall_observe(
        f, deadline, strict_counter, cross=False,
        classification="valid unexpired realwall control; apply once")
    result = ge.consume_gate(f.root, f.gate.stem, claim_id=f.claim,
                             observe=observing, source=f.source)
    body = f.calls
    effect = gates.parse(f.gate).effect
    retry = f.consume()
    event.update({
        "state": result.state, "reason": result.reason, "body": body, "effect": effect,
        "retry": retry.state, "body_after_retry": f.calls,
        "real_strict_calls_after": list(strict_counter),
    })
    print(json.dumps(event, ensure_ascii=False))
    assert event["final_pre_observe_reached"] is True
    assert result.state == "applied" and body == 1 and effect == "applied", result
    assert gates.parse(f.gate).effect == "applied"
    assert _no_dp_sink(f)
    assert all(call["verification"] == "strict-verified" for call in strict_counter)
    assert retry.state == "applied" and retry.duplicate and f.calls == 1


@pytest.mark.parametrize("worker_local", [False, True])
def test_r3d_setup_already_expired_is_an_invalid_experiment_not_a_fix(
        tmp_path, strict_counter, worker_local):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    deadline = _dt.now(_timezone.utc) - _timedelta(seconds=1)
    f.ctx.budget["deadline"] = deadline.isoformat()
    observing, event = _r3d_realwall_observe(
        f, deadline, strict_counter, cross=False,
        classification="INVALID EXPERIMENT: setup already expired before real strict; not P2 fix evidence")
    result = ge.consume_gate(f.root, f.gate.stem, claim_id=f.claim,
                             observe=observing, source=f.source)
    body = f.calls
    effect = gates.parse(f.gate).effect
    retry = f.consume()
    event.update({
        "state": result.state, "reason": result.reason, "body": body, "effect": effect,
        "retry": retry.state, "body_after_retry": f.calls,
        "strict_failure_codes": [tuple(call["failure_codes"]) for call in strict_counter],
        "p2_fix_evidence": False, "invalid_experiment": True,
    })
    print(json.dumps(event, ensure_ascii=False))
    assert event["invalid_experiment"] is True and event["p2_fix_evidence"] is False
    assert event["classification"].startswith("INVALID EXPERIMENT")
    assert not event["final_pre_observe_reached"], event
    assert result.state == "blocked" and body == 0 and effect == "not-started", result
    assert "strict" in result.reason
    assert any("budget-exhausted" in tuple(call["failure_codes"]) for call in strict_counter)
    assert _no_dp_sink(f) and f.calls == 0


@pytest.mark.parametrize("worker_local", [False, True])
def test_r3d_last_pre_observe_crossing_existing_deadline_blocks_before_writer(
        tmp_path, strict_counter, worker_local):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    deadline = _dt.now(_timezone.utc) + _timedelta(seconds=2)
    f.ctx.budget["deadline"] = deadline.isoformat()
    observing, event = _r3d_realwall_observe(
        f, deadline, strict_counter, cross=True,
        classification="REAL WALL-CLOCK P2 counter-example; strict passed before the existing deadline")
    result = ge.consume_gate(f.root, f.gate.stem, claim_id=f.claim,
                             observe=observing, source=f.source)
    body = f.calls
    effect = gates.parse(f.gate).effect
    retry = f.consume()
    event.update({
        "state": result.state, "reason": result.reason, "body": body, "effect": effect,
        "retry": retry.state, "body_after_retry": f.calls,
        "real_strict_calls_after": list(strict_counter),
    })
    print(json.dumps(event, ensure_ascii=False))
    assert event["final_pre_observe_reached"] is True
    assert event["entered_before_deadline"] is True
    assert event["returned_after_deadline"] is True
    assert event["body_at_enter"] == 0
    assert event["real_verify_execution_calls"] >= 3
    assert len(event["real_strict_calls_at_enter"]) >= 3
    assert all(call["verification"] == "strict-verified"
               for call in event["real_strict_calls_at_enter"])
    assert "deadline" in result.reason
    assert result.state == "blocked" and body == 0 and effect == "not-started", result
    assert gates.parse(f.gate).effect == "not-started"
    assert _no_dp_sink(f)
    assert retry.state != "applied" and f.calls == 0


@pytest.mark.parametrize("worker_local", [False, True])
def test_r3d_controlled_clock_diagnostic_is_not_realwall_evidence(
        tmp_path, monkeypatch, strict_counter, worker_local):
    readings = []
    state = {"expired": False}

    def now_iso():
        return ("2100-01-01T00:00:00+00:00" if state["expired"]
                else "2026-01-01T00:00:00+00:00")

    _r3d_patch_reader_clock(monkeypatch, now_iso, readings)
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    count = 0
    event = {
        "controlled_clock_only": True, "real_wall_clock": False,
        "classification": "diagnostic only: injected reader clock is NOT realwall evidence; real strict pass-through, no success stub",
        "deadline": f.ctx.budget["deadline"],
    }

    def observing(gate):
        nonlocal count
        count += 1
        if count == 4:
            state["expired"] = True
            event.update({
                "observe": count, "body_at_mutation": f.calls,
                "clock_readings_before_mutation": len(readings),
                "real_strict_calls_at_mutation": list(strict_counter),
                "real_verify_execution_calls": f.host.verifier_calls,
                "mutation": "reader clock now=2100 after the final pre observe",
            })
        return f.facts

    result = ge.consume_gate(f.root, f.gate.stem, claim_id=f.claim,
                             observe=observing, source=f.source)
    body = f.calls
    effect = gates.parse(f.gate).effect
    retry = f.consume()
    event.update({
        "state": result.state, "reason": result.reason, "body": body, "effect": effect,
        "retry": retry.state, "body_after_retry": f.calls,
        "clock_readings": readings, "real_strict_calls_after": list(strict_counter),
    })
    print(json.dumps(event, ensure_ascii=False))
    assert event["controlled_clock_only"] is True and event["real_wall_clock"] is False
    assert "NOT realwall evidence" in event["classification"]
    assert event["clock_readings_before_mutation"] > 0
    assert any(item.startswith("2100-") for item in readings)
    assert event["real_verify_execution_calls"] >= 3
    assert all(call["verification"] == "strict-verified"
               for call in event["real_strict_calls_at_mutation"])
    assert "deadline" in result.reason
    assert result.state == "blocked" and body == 0 and effect == "not-started", result
    assert _no_dp_sink(f) and f.calls == 0


_R3D_BOUNDARY = (
    # deadline with a non-UTC offset: before, exact now == parsed, one us after
    ("2030-01-01T00:00:00+08:00", "2029-12-31T15:59:59.999999+00:00", False),
    ("2030-01-01T00:00:00+08:00", "2029-12-31T16:00:00+00:00", False),
    ("2030-01-01T00:00:00+08:00", "2029-12-31T16:00:00.000001+00:00", True),
    # Z and explicit +00:00 are equivalent; strict predicate stays now > parsed
    ("2030-01-01T00:00:00Z", "2029-12-31T23:59:59.999999+00:00", False),
    ("2030-01-01T00:00:00Z", "2030-01-01T00:00:00+00:00", False),
    ("2030-01-01T00:00:00Z", "2030-01-01T00:00:00.000001+00:00", True),
    ("2030-01-01T00:00:00+00:00", "2030-01-01T00:00:00+00:00", False),
)


@pytest.mark.parametrize("deadline,now_iso,expected_expired", _R3D_BOUNDARY)
def test_r3d_final_deadline_preserves_timezone_and_now_gt_boundary(
        tmp_path, monkeypatch, deadline, now_iso, expected_expired):
    readings = []
    _r3d_patch_reader_clock(monkeypatch, lambda value=now_iso: value, readings)
    f = LocalFixture(tmp_path)
    context = replace(f.ctx, budget=_live_budget(f.matter.matter_key, deadline=deadline))
    if expected_expired:
        with pytest.raises(ge.GateBlocked, match="deadline"):
            ge._assert_final_budget_deadline(context)
    else:
        ge._assert_final_budget_deadline(context)
    assert readings


def test_r3d_frozen_reader_naive_utc_and_strict_gt_are_not_redefined(
        tmp_path, monkeypatch):
    before = []
    _r3d_patch_reader_clock(monkeypatch, lambda: "2030-01-01T00:00:00+00:00", before)
    assert lev._deadline_passed("2030-01-01T00:00:00") is False
    after = []
    _r3d_patch_reader_clock(monkeypatch, lambda: "2030-01-01T00:00:00.000001+00:00", after)
    assert lev._deadline_passed("2030-01-01T00:00:00") is True
    assert before and after


@pytest.mark.parametrize("fault", ["none", "empty", "bad-deadline", "zero-steps", "null-deadline"])
def test_r3d_missing_or_invalid_final_budget_fails_closed(tmp_path, fault):
    f = LocalFixture(tmp_path)
    if fault == "none":
        budget = None
    elif fault == "empty":
        budget = {}
    elif fault == "bad-deadline":
        budget = _live_budget(f.matter.matter_key, deadline="not-a-deadline")
    elif fault == "zero-steps":
        budget = _live_budget(f.matter.matter_key, max_steps=0)
    else:
        budget = _live_budget(f.matter.matter_key, deadline=None)
    context = replace(f.ctx, budget=budget)
    with pytest.raises(ge.GateBlocked, match="finite host budget|deadline"):
        ge._assert_final_budget_deadline(context)


# ── T08-A-R4: typed COMPLETE final sample + real L1 host producer ──────────
# Appended only. All original 109 substantive assertions above are unchanged.

class _R4SpyHost(Host):
    """Records the producer's sample at the real trust boundary. No stubbing."""

    def __init__(self, f: LocalFixture):
        super().__init__(f)
        self.samples: list = []
        self.counters: list = []
        self.observe_counts: list = []
        self.fingerprints: list = []

    def terminal_sample(self, request):
        before = (self.context_calls, self.verifier_calls,
                  self.expectation_calls, self.disposition_calls)
        sample = super().terminal_sample(request)
        after = (self.context_calls, self.verifier_calls,
                 self.expectation_calls, self.disposition_calls)
        self.samples.append(sample)
        self.counters.append((before, after))
        self.observe_counts.append(getattr(self.f, "r4_observe_count", -1))
        self.fingerprints.append(self.terminal_state_fingerprint())
        return sample


@pytest.mark.parametrize("worker_local", [False, True])
def test_r4_producer_is_last_callback_and_complete_sample_releases_once(
        tmp_path, strict_counter, worker_local):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    spy = _R4SpyHost(f)
    f.host = spy
    f.source = replace(f.source, host=spy)
    f.r4_observe_count = 0

    def observing(gate):
        f.r4_observe_count += 1
        return f.facts

    evidence_before = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    result = ge.consume_gate(f.root, f.gate.stem, claim_id=f.claim,
                             observe=observing, source=f.source)
    assert result.state == "applied" and result.receipt and "#" in result.receipt, result
    assert f.calls == 1 and gates.parse(f.gate).effect == "applied"
    # The producer is invoked exactly once per terminal boundary, AFTER the
    # last (4th pre / 6th post) mutation-capable observe callback.
    assert len(spy.samples) == 2, spy.samples
    assert spy.observe_counts == [4, 6], spy.observe_counts
    read = lev.read_local_evidence(
        f.agenticdoc_root, KEY, f.source.record_source, LOCAL_REF,
        task_key=f.source.task_key)
    for sample, fp, (before, after), phase in zip(
            spy.samples, spy.fingerprints, spy.counters, ("pre", "post")):
        assert isinstance(sample, ge.TerminalSample)
        assert sample.phase == phase
        assert sample.source_key == KEY and sample.record_source == f.source.record_source
        assert sample.local_ref == LOCAL_REF and sample.gate_decision_ref == GATE_REF
        assert sample.task_key == f.source.task_key and sample.claim_id == f.claim
        assert sample.state_fingerprint == fp, "coherent host-owned live fingerprint"
        assert before == after, "producer must not call the counted host callbacks"
        assert sample.disposition is not None and sample.disposition.confirmed is True
        assert sample.selection_sha256 == read.selection_sha256
        assert sample.execution_sha256 == read.execution_sha256
        assert sample.selection.local_ref == LOCAL_REF
        assert sample.execution.effect_state == "known"
        assert sample.gate_identity[0] == GATE_REF
        assert sample.object_digest.startswith("sha256:")
        assert sample.receipt == ("" if phase == "pre" else result.receipt)
    # Real strict two sources, no success stub; independent physical readback.
    assert [c["which"] for c in strict_counter][:2] == ["selection", "execution"]
    assert all(c["verification"] == "strict-verified" for c in strict_counter)
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == evidence_before
    assert f.host.disposition_calls == 3 and f.host.expectation_calls >= 4
    assert sum(1 for c in strict_counter if c["which"] == "execution") >= 4
    retry = f.consume()
    assert retry.state == "applied" and retry.duplicate and f.calls == 1
    assert gates.parse(f.gate).effect == "applied"
    assert _no_dp_sink(f)


@pytest.mark.parametrize("timing", ["pre", "post"])
def test_r4_terminal_sample_reflects_completed_callback_mutation(tmp_path, timing):
    f = LocalFixture(tmp_path)
    spy = _R4SpyHost(f)
    f.host = spy
    f.source = replace(f.source, host=spy)
    target = 4 if timing == "pre" else 6
    count = 0

    def observing(gate):
        nonlocal count
        count += 1
        if count == target:
            f.ctx = replace(f.ctx, stop_scope="matter")
            f.expectations = replace(f.expectations, pm_note="changed")
        return f.facts

    result = ge.consume_gate(f.root, f.gate.stem, claim_id=f.claim,
                             observe=observing, source=f.source)
    sample = spy.samples[0] if timing == "pre" else spy.samples[-1]
    assert spy.samples, "the producer must actually be reached"
    # Freshness, not a frozen old getter reference: the completed callback's
    # replacements are visible in the sample captured after it returned.
    assert sample.context.stop_scope == "matter"
    assert sample.expectations.pm_note == "changed"
    assert sample.state_fingerprint == spy.fingerprints[-1]
    assert f.ctx.stop_scope == "matter" and f.expectations.pm_note == "changed"
    if timing == "pre":
        assert result.state == "blocked" and f.calls == 0, result
        assert gates.parse(f.gate).effect == "not-started"
    else:
        assert result.state == "unknown" and f.calls == 1, result
        assert gates.parse(f.gate).effect == "unknown"
    assert _no_dp_sink(f)


R4_REPLACEMENTS = ("expectations-replaced", "disposition-replaced",
                   "binding-replaced", "action-evidence-replaced")


def _r4_replace(f: LocalFixture, fault: str) -> None:
    if fault == "expectations-replaced":
        f.expectations = replace(f.expectations, selected_basis_id="forged-basis")
    elif fault == "disposition-replaced":
        # Live host state only: the real physical execution record is unchanged,
        # so a strict/physical-only check cannot see this. The producer must.
        f.execution["action_ref"] = "tool_call:forged"
    elif fault == "binding-replaced":
        f.ctx = replace(f.ctx, binding=replace(f.ctx.binding, claim_id="foreign:1"))
    elif fault == "action-evidence-replaced":
        f.evidence = replace(f.evidence, confirmed=False)
    else:
        raise AssertionError(fault)


@pytest.mark.parametrize("timing", ["pre", "post"])
@pytest.mark.parametrize("fault", R4_REPLACEMENTS)
def test_r4_last_callback_replacements_are_bound_by_complete_sample(
        tmp_path, timing, fault):
    f = LocalFixture(tmp_path)
    spy = _R4SpyHost(f)
    f.host = spy
    f.source = replace(f.source, host=spy)
    target = 4 if timing == "pre" else 6
    count = 0

    def observing(gate):
        nonlocal count
        count += 1
        if count == target:
            _r4_replace(f, fault)
        return f.facts

    before_map = f.map.read_bytes()
    result = ge.consume_gate(f.root, f.gate.stem, claim_id=f.claim,
                             observe=observing, source=f.source)
    body = f.calls
    retry = f.consume()
    assert spy.samples, "producer trust boundary must be reached"
    assert _no_dp_sink(f) and f.calls == body
    if timing == "pre":
        assert body == 0 and result.state == "blocked", (fault, result)
        assert gates.parse(f.gate).effect == "not-started"
        assert f.map.read_bytes() == before_map
    else:
        assert body == 1 and result.state == "unknown", (fault, result)
        assert gates.parse(f.gate).effect == "unknown"
        assert retry.state != "applied"


class _R4StaleRefsHost(Host):
    """The forbidden implementation: build the sample from retained old refs.

    ``trigger`` selects the first terminal boundary at which the stale refs are
    used; from that boundary on the producer stays stale (so a retry cannot
    silently apply). Other boundaries use the real live-state producer.
    """

    def __init__(self, f: LocalFixture, trigger: int = 1):
        super().__init__(f)
        self.trigger = trigger
        self.calls = 0
        self.samples: list = []
        self.saved = (f.ctx, f.expectations, f.evidence, f.execution, f.selection,
                      f.facts, f.disposition_ok, f.recovery_disposition_ok)

    def terminal_sample(self, request):
        self.calls += 1
        if self.calls < self.trigger:
            sample = super().terminal_sample(request)
            self.samples.append(sample)
            return sample
        f = self.f
        live = (f.ctx, f.expectations, f.evidence, f.execution, f.selection,
                f.facts, f.disposition_ok, f.recovery_disposition_ok)
        (f.ctx, f.expectations, f.evidence, f.execution, f.selection,
         f.facts, f.disposition_ok, f.recovery_disposition_ok) = self.saved
        try:
            sample = super().terminal_sample(request)
        finally:
            (f.ctx, f.expectations, f.evidence, f.execution, f.selection,
             f.facts, f.disposition_ok, f.recovery_disposition_ok) = live
        self.samples.append(sample)
        return sample


def _r4_bad_host(kind: str):
    if kind == "oldsample":
        return _R4StaleRefsHost

    class Bad(Host):
        def __init__(self, f, trigger=1):
            super().__init__(f)
            self.trigger = trigger
            self.calls = 0

        def terminal_sample(self, request):
            self.calls += 1
            sample = super().terminal_sample(request)
            if self.calls < self.trigger or sample is None:
                return sample
            if kind == "wrongsource":
                return replace(sample, source_key="wrong-key")
            if kind == "incoherent":
                return replace(sample, selection_sha256="sha256:wrong")
            if kind == "missingproducer":
                return None
            raise AssertionError(kind)
    return Bad


R4_REJECTIONS = ("wrongsource", "oldsample", "incoherent", "missingproducer")


@pytest.mark.parametrize("trigger,expected_state,expected_body", [
    (1, "blocked", 0),   # producer already fails at the pre-apply boundary
    (2, "unknown", 1),   # pre boundary passes; post boundary rejects the write
])
@pytest.mark.parametrize("kind", R4_REJECTIONS)
def test_r4_wrongsource_oldsample_incoherent_and_missingproducer_are_rejected(
        tmp_path, kind, trigger, expected_state, expected_body):
    f = LocalFixture(tmp_path)
    host = _r4_bad_host(kind)(f, trigger=trigger)
    f.host = host
    f.source = replace(f.source, host=host)
    target = 4 if trigger == 1 else 6
    count = 0

    def observing(gate):
        nonlocal count
        count += 1
        if count == target and kind == "oldsample":
            # A completed callback mutation makes a retained-ref sample stale.
            f.ctx = replace(f.ctx, stop_scope="matter")
        return f.facts

    result = ge.consume_gate(f.root, f.gate.stem, claim_id=f.claim,
                             observe=observing, source=f.source)
    body = f.calls
    retry = f.consume()
    assert _no_dp_sink(f) and f.calls == body, (kind, trigger)
    assert result.state == expected_state and body == expected_body, (kind, trigger, result)
    if expected_state == "blocked":
        assert gates.parse(f.gate).effect == "not-started"
    else:
        assert gates.parse(f.gate).effect == "unknown"
        assert retry.state != "applied"
    assert "terminal sample" in result.reason, (kind, trigger, result)


def test_r4_stale_retained_refs_sample_is_proven_stale_not_accepted(tmp_path):
    f = LocalFixture(tmp_path)
    host = _R4StaleRefsHost(f, trigger=1)
    f.host = host
    f.source = replace(f.source, host=host)
    count = 0

    def observing(gate):
        nonlocal count
        count += 1
        if count == 4:
            f.ctx = replace(f.ctx, stop_scope="matter")
        return f.facts

    result = ge.consume_gate(f.root, f.gate.stem, claim_id=f.claim,
                             observe=observing, source=f.source)
    assert host.samples and host.samples[0] is not None
    stale = host.samples[0]
    # The stale sample itself still matches the ORIGINAL baseline; only the
    # host-owned live fingerprint proves it is not the current state.
    assert stale.context.stop_scope == "none"
    assert f.ctx.stop_scope == "matter"
    assert stale.state_fingerprint != host.terminal_state_fingerprint()
    assert result.state == "blocked" and f.calls == 0, result
    assert "terminal sample" in result.reason, result


def test_r4_terminal_sample_is_deep_frozen_not_a_borrowed_ref(tmp_path):
    f = LocalFixture(tmp_path)
    spy = _R4SpyHost(f)
    f.host = spy
    f.source = replace(f.source, host=spy)
    result = f.consume()
    assert result.state == "applied" and f.calls == 1, result
    sample = spy.samples[0]
    assert sample.context is not f.ctx
    assert sample.context.binding is not f.ctx.binding
    assert sample.context.budget is not f.ctx.budget
    assert sample.expectations is not f.expectations
    before = ge._context_state(sample.context)
    f.ctx.budget["steps_consumed"] = 5
    f.expectations = replace(f.expectations, pm_note="later-change")
    assert ge._context_state(sample.context) == before
    assert sample.expectations.pm_note == PM_NOTE


def test_r4_reject_all_producer_is_not_a_valid_repair(tmp_path):
    f = LocalFixture(tmp_path)

    class RejectAll(Host):
        def terminal_sample(self, request):
            return None

    f.host = RejectAll(f)
    f.source = replace(f.source, host=f.host)
    result = f.consume()
    assert result.state != "applied" and f.calls == 0, result
    assert "terminal sample" in result.reason, result
    # The real producer must still release a legitimate, unchanged L1 exactly
    # once. A reject-all implementation fails this control and is not accepted.
    g = LocalFixture(tmp_path / "control")
    positive = g.consume()
    assert positive.state == "applied" and g.calls == 1, positive
    replay = g.consume()
    assert replay.state == "applied" and replay.duplicate and g.calls == 1
    assert _no_dp_sink(g)


# ── T08-A-R5: fixed-owner local reads + typed live selection/execution ─────────
# The FINAL authority is sampled by the consumer from a pinned owner-state
# carrier via non-delegating local reads AFTER every completed host callback;
# live selection/execution are typed values bound to the same strict physical
# package. No new final getter, no skipped callbacks, no blanket Host rejection.


class _R5LateFingerprintHost(Host):
    """Last completed virtual fingerprint callback mutates the LIVE owner after
    super() truthfully computed the fingerprint: no fabricated fp, no Spy."""

    def __init__(self, f, *, timing, fault):
        super().__init__(f)
        self.timing = timing
        self.fault = fault
        self.phase = None
        self.fp_calls = 0
        self.mutations = []

    def terminal_sample(self, request):
        self.phase = request.phase
        return super().terminal_sample(request)

    def terminal_state_fingerprint(self):
        fp = super().terminal_state_fingerprint()
        self.fp_calls += 1
        if self.phase == self.timing and not self.mutations:
            self.mutations.append({"phase": self.phase, "fp_call": self.fp_calls,
                                   "body_at_mutation": self.f.calls})
            if self.fault == "stop":
                self.f.ctx = replace(self.f.ctx, stop_scope="matter")
            else:
                self.f.ctx.budget["steps_consumed"] = 5
        return fp


@pytest.mark.parametrize("worker_local", [False, True])
@pytest.mark.parametrize("timing", ["pre", "post", "recovery"])
@pytest.mark.parametrize("fault", ["stop", "budget"])
def test_r5_last_completed_fingerprint_live_owner_mutation_is_rejected(
        tmp_path, worker_local, timing, fault):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    if timing == "recovery":
        original = f.consume()
        assert original.state == "applied" and f.calls == 1, original
    host = _R5LateFingerprintHost(f, timing=timing, fault=fault)
    f.host = host
    f.source = replace(f.source, host=host)
    result = f.consume()
    body = f.calls
    assert host.mutations, "the last completed fingerprint callback must be reached"
    assert host.mutations[0]["body_at_mutation"] == (0 if timing == "pre" else 1)
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f) and f.calls == body
    if timing == "pre":
        assert result.state == "blocked" and body == 0, result
        assert gates.parse(f.gate).effect == "not-started"
        assert f.map.read_bytes() == before
    else:
        assert result.state == "unknown" and body == 1, result


_R5_F2_FAULTS = ("unknown", "basis", "target", "source", "budget_ref")


@pytest.mark.parametrize("worker_local", [False, True])
@pytest.mark.parametrize("timing", ["pre", "post"])
@pytest.mark.parametrize("fault", _R5_F2_FAULTS)
def test_r5_live_typed_field_drift_is_rejected(tmp_path, worker_local, timing, fault):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    assert type(f.host) is Host, "unchanged REAL base producer"
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    seen = []
    count = 0
    target = 4 if timing == "pre" else 6

    def observing(gate):
        nonlocal count
        count += 1
        if count == target:
            seen.append({"observe": count, "body_at_mutation": f.calls})
            if fault == "unknown":
                f.execution["effect_state"] = "unknown"
            elif fault == "basis":
                f.selection["selected_basis_id"] = "forged-basis"
            elif fault == "target":
                f.execution["target_digest"] = "sha256:wrong-live-target"
            elif fault == "source":
                f.execution["source"] = "worker-local" if not worker_local else "pm"
            else:
                f.execution["budget_ref"] = "budget:wrong-live"
        return f.facts

    result = ge.consume_gate(f.root, f.gate.stem, claim_id=f.claim,
                             observe=observing, source=f.source)
    body = f.calls
    assert seen and seen[0]["body_at_mutation"] == (0 if timing == "pre" else 1)
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f) and f.calls == body
    if timing == "pre":
        assert result.state == "blocked" and body == 0, result
        assert gates.parse(f.gate).effect == "not-started"
        assert f.map.read_bytes() == before
    else:
        assert result.state == "unknown" and body == 1, result


def test_r5_recovery_live_typed_drift_returns_unknown_without_replay(tmp_path):
    f = LocalFixture(tmp_path)
    original = f.consume()
    assert original.state == "applied" and f.calls == 1, original
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    f.execution["effect_state"] = "unknown"  # live-only; physical unchanged
    result = f.consume()
    assert result.state == "unknown" and f.calls == 1, result
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert f.map.read_bytes() == before
    assert _no_dp_sink(f)


class _R5CarrierHost(Host):
    """Producer-visible carrier tampering; the consumer keeps its own pin."""

    def __init__(self, f, *, kind):
        super().__init__(f)
        self.kind = kind
        self.snapshot = None

    def terminal_sample(self, request):
        if self.kind == "replacement":
            request.owner.live = copy.copy(self.f)  # clean but a DIFFERENT object
        elif self.kind == "stale":
            self.snapshot = copy.copy(self.f)
            request.owner.live = self.snapshot
        return super().terminal_sample(request)

    def terminal_state_fingerprint(self):
        fp = super().terminal_state_fingerprint()
        if self.kind == "stale":
            self.f.ctx = replace(self.f.ctx, stop_scope="matter")  # late real-owner change
        return fp


@pytest.mark.parametrize("kind", ["none", "replacement", "stale", "incoherent"])
def test_r5_owner_carrier_none_replacement_stale_incoherent_fail_closed(tmp_path, kind):
    f = LocalFixture(tmp_path)
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    if kind == "none":
        f.source = replace(f.source, owner_state=None)
    elif kind == "incoherent":
        # Same pinned owner, but a live typed value is not a valid semantic value.
        f.execution["effect_state"] = 123
    else:
        host = _R5CarrierHost(f, kind=kind)
        f.host = host
        f.source = replace(f.source, host=host)
    result = f.consume()
    assert result.state == "blocked" and f.calls == 0, (kind, result)
    assert gates.parse(f.gate).effect == "not-started", (kind,)
    assert f.map.read_bytes() == before
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)


@pytest.mark.parametrize("worker_local", [False, True])
def test_r5_owner_carrier_positive_releases_once_and_replay_is_noop(tmp_path, worker_local):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    assert f.source.owner_state is f, "the authoritative live owner is pinned on the source"
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    result = f.consume()
    replay = f.consume()
    assert result.state == "applied" and replay.state == "applied" and replay.duplicate
    assert f.calls == 1
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)


# ── T08-A-R6: real producer/consumer owner + non-delegating COMPLETE domain ──
# Appended only. All 171 original substantive assertions above are UNCHANGED.
# The complete final domain is captured by the consumer from the ONE identity-
# bound authoritative owner after the last callback; the real L1 producer reads
# the same domain non-delegating (Host._live_state_projections / _own). These
# cases are INDEPENDENT of the byte-for-byte PM probes run in the own run dir.


class _R6LateFingerprintHost(Host):
    """Last completed virtual fingerprint callback mutates the LIVE owner after
    super() truthfully computed the fingerprint (real owner rebind or a late
    complete-domain change). No fabricated sample/fp, no strict stub."""

    def __init__(self, f, *, timing, kind):
        super().__init__(f)
        self.timing = timing
        self.kind = kind
        self.phase = None
        self.fired = False

    def terminal_sample(self, request):
        self.phase = request.phase
        return super().terminal_sample(request)

    def terminal_state_fingerprint(self):
        fp = super().terminal_state_fingerprint()
        if self.phase == self.timing and not self.fired:
            self.fired = True
            f = self.f
            if self.kind == "owner-swap":
                new = copy.copy(f)
                new.ctx = replace(new.ctx, stop_scope="matter")
                self.f = new                       # REAL producer owner rebind
            elif self.kind == "ctx-stop":
                f.ctx = replace(f.ctx, stop_scope="matter")
            elif self.kind == "expectations":
                f.expectations = replace(f.expectations, selected_basis_id="forged-basis")
            elif self.kind == "evidence":
                f.evidence = replace(f.evidence, confirmed=False)
            elif self.kind == "facts":
                f.facts = replace(f.facts, hard_checks={"delivery-evidence": False})
            elif self.kind == "disposition":
                f.disposition_ok = False
        return fp


# owner rebind (F1) + ctx/budget/stop + the FOUR previously-missing F3 domains,
# each x pre/post/recovery x PM/worker-local. All must REALLY trigger and be
# rejected by the final complete-domain capture.
_R6_LATE_KINDS = ("owner-swap", "ctx-stop", "expectations", "evidence", "facts", "disposition")


@pytest.mark.parametrize("worker_local", [False, True])
@pytest.mark.parametrize("timing", ["pre", "post", "recovery"])
@pytest.mark.parametrize("kind", _R6_LATE_KINDS)
def test_r6_real_owner_and_complete_final_domain_reject_late_mutation(
        tmp_path, worker_local, timing, kind):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    if timing == "recovery":
        first = f.consume()
        assert first.state == "applied" and f.calls == 1, first
    host = _R6LateFingerprintHost(f, timing=timing, kind=kind)
    f.host = host
    f.source = replace(f.source, host=host)
    result = f.consume()
    body = f.calls
    assert host.fired, "the last completed fingerprint callback must be reached"
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)
    if timing == "pre":
        assert result.state == "blocked" and body == 0, result
        assert gates.parse(f.gate).effect == "not-started"
        assert f.map.read_bytes() == before
    else:
        assert result.state == "unknown" and body == 1, result
    replay = f.consume()
    assert replay.state != "applied", replay
    assert f.calls == body, "never replay the business writer"


# Requirement 4 dedicated evidence: the 12 unsafe-delegation triggers of the PM
# 44-probe no longer fire because BOTH the real producer and the consumer use a
# non-delegating exact-typed domain. Prove the same safety objective with real
# strict/physical and ZERO delegation calls (no .get hook, no __getattribute__
# hook ever invoked). This is NOT the 44-probe itself and does not claim it green.

class _R6LateDict(dict):
    """Same values, but .get would delegate (would-be late stop)."""
    def __init__(self, base, log):
        super().__init__(base)
        self._log = log

    def get(self, key, default=None):
        self._log.append(("get", key))
        return super().get(key, default)


def test_r6_dict_subclass_refused_without_invoking_container_delegation(tmp_path, strict_counter):
    f = LocalFixture(tmp_path)
    log = []
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    f.execution = _R6LateDict(f.execution, log)   # delegating container, same values
    result = f.consume()
    # Exact-builtin-dict boundary refuses the container; its .get is NEVER
    # called by the non-delegating final capture (nor by the producer).
    assert not any(c[0] == "get" for c in log), log
    assert result.state in ("blocked", "unknown") and f.calls == 0, result
    assert gates.parse(f.gate).effect == "not-started"
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert f.map.read_bytes() == before
    assert _no_dp_sink(f)
    assert any(c["which"] == "execution" and c["verification"] == "strict-verified"
               for c in strict_counter), "real strict verification, no success stub"


class _R6AttrFixture(LocalFixture):
    """Owner with a would-be unsafe __getattribute__('execution') hook."""
    def __getattribute__(self, name):
        if name == "execution":
            log = object.__getattribute__(self, "_r6_log")
            if log is not None:
                log.append(("getattribute", name))
        return super().__getattribute__(name)


@pytest.mark.parametrize("late_stop", [False, True])
def test_r6_getattribute_owner_never_delegates_and_genuine_stop_still_detected(
        tmp_path, strict_counter, late_stop):
    f = LocalFixture(tmp_path)
    log = []
    f.__class__ = _R6AttrFixture          # same identity, delegating attribute protocol
    f._r6_log = log
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    if late_stop:
        host = _R6LateFingerprintHost(f, timing="pre", kind="ctx-stop")
        f.host = host
        f.source = replace(f.source, host=host)
    result = f.consume()
    # The unsafe attribute hook is NEVER invoked anywhere (producer + consumer
    # both read via object.__getattribute__).
    assert log == [], log
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)
    assert any(c["which"] == "execution" and c["verification"] == "strict-verified"
               for c in strict_counter)
    if late_stop:
        # A GENUINE late mutation (completed fingerprint callback, NOT via
        # delegation) is still detected by the non-delegating complete-domain
        # capture: the fixed consumer is not blind to real state changes.
        assert result.state == "blocked" and f.calls == 0, result
        assert gates.parse(f.gate).effect == "not-started"
        assert f.map.read_bytes() == before
    else:
        # Pristine state + no unsafe delegation => exactly one legitimate apply.
        assert result.state == "applied" and f.calls == 1, result
        replay = f.consume()
        assert replay.state == "applied" and replay.duplicate and f.calls == 1


@pytest.mark.parametrize("worker_local", [False, True])
def test_r6_legitimate_dual_source_strict_physical_apply1_no_replay(
        tmp_path, strict_counter, worker_local):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    result = f.consume()
    replay = f.consume()
    assert result.state == "applied" and result.receipt and f.calls == 1, result
    assert replay.state == "applied" and replay.duplicate and f.calls == 1
    assert [c["which"] for c in strict_counter][:2] == ["selection", "execution"]
    assert all(c["verification"] == "strict-verified" and not c["failure_codes"]
               for c in strict_counter)
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert f.map.read_bytes() != before, "exactly one real object write"
    assert _no_dp_sink(f)


def test_r6_final_authority_domain_field_mapping_is_complete():
    """Document/verify the COMPLETE final domain field set required by the card."""
    names = {fld.name for fld in dataclasses.fields(ge._FinalAuthority)}
    assert {"context", "selection", "execution", "selection_typed", "execution_typed",
            "context_state", "expectations_state", "action_evidence_state",
            "facts_state", "selection_state", "execution_state", "disposition_state",
            "state_fingerprint"} <= names


# ── T08-A-R7: controlled producer-owner storage + recursively exact final domain ──
# Appended only. All 213 original substantive assertions above are UNCHANGED.
# The three R6-RV P1 mechanisms (virtual authority_owner return value,
# object.__getattribute__ raw reads, top-level exact typed comparison) are NOT
# authority sources any more. Independent no-delegation / same-safety-target /
# genuine-late-mutation / legal dual-source controls are proven here.


def _r7_string(log):
    class SameString(str):
        def __eq__(self, other):
            log.append("str.__eq__")
            return str.__eq__(self, other)

        def __ne__(self, other):
            log.append("str.__ne__")
            return str.__ne__(self, other)
        __hash__ = str.__hash__
    return SameString


def _r7_mapping(log):
    class SameMapping(dict):
        def get(self, key, default=None):
            log.append("dict.get")
            return dict.get(self, key, default)

        def items(self):
            log.append("dict.items")
            return dict.items(self)
    return SameMapping


class _R7LastCallbackRebindHost(Host):
    """Last retained callback: rebind the REAL producer owner storage.

    ``host-slot`` is the E191 F1 rebind (``self.f = copy(...)`` after a truthful
    super result); ``controlled-cell`` uses the real controlled-storage rebind
    API. Both must be detected by the consumer's independent association.
    """

    def __init__(self, f, *, timing, kind):
        super().__init__(f)
        self.timing = timing
        self.kind = kind
        self.phase = None
        self.events = []

    def terminal_sample(self, request):
        self.phase = request.phase
        return super().terminal_sample(request)

    def authority_owner(self):
        owner = super().authority_owner()   # retained callback; result ignored
        if self.phase == self.timing and not self.events:
            f = self.f
            new = copy.copy(f)
            new.ctx = replace(new.ctx, stop_scope="matter")
            if self.kind == "host-slot":
                self.f = new                       # real producer alias rebind
            else:
                f.source.authority_cell.rebind(new)  # actual controlled storage rebind
            self.events.append({"hook": self.kind, "body": f.calls, "phase": self.timing})
        return owner


@pytest.mark.parametrize("worker_local", [False, True])
@pytest.mark.parametrize("timing", ["pre", "post", "recovery"])
@pytest.mark.parametrize("kind", ["host-slot", "controlled-cell"])
def test_r7_last_callback_real_owner_rebind_is_detected(
        tmp_path, strict_counter, worker_local, timing, kind):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    if timing == "recovery":
        first = f.consume()
        assert first.state == "applied" and f.calls == 1, first
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    host = _R7LastCallbackRebindHost(f, timing=timing, kind=kind)
    f.host = host
    f.source = replace(f.source, host=host)
    result = f.consume()
    body = f.calls
    assert host.events and host.events[0]["body"] == (0 if timing == "pre" else 1)
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)
    assert any(c["verification"] == "strict-verified" for c in strict_counter)
    if timing == "pre":
        assert result.state == "blocked" and body == 0, result
        assert gates.parse(f.gate).effect == "not-started"
        assert f.map.read_bytes() == before
    else:
        assert result.state == "unknown" and body == 1, result
    replay = f.consume()
    assert replay.state != "applied" and f.calls == body
    if kind == "controlled-cell":
        assert f.cell.invalidated() and f.cell.rebinds() == 1


def test_r7_virtual_authority_owner_return_is_not_an_authority_source(tmp_path):
    """A pointless/dishonest virtual return cannot decide authority by itself."""
    f = LocalFixture(tmp_path)

    class GetterOnly(Host):
        def authority_owner(self):
            return object()

    f.host = GetterOnly(f)
    f.source = replace(f.source, host=f.host)
    result = f.consume()
    replay = f.consume()
    assert result.state == "applied" and f.calls == 1, result
    assert replay.state == "applied" and replay.duplicate and f.calls == 1
    assert _no_dp_sink(f)


class _R7DescriptorFixture(LocalFixture):
    """Same identity, genuine data descriptor on a live domain field."""
    @property
    def execution(self):
        log = object.__getattribute__(self, "_r7_log")
        if object.__getattribute__(self, "_r7_armed"):
            log.append("descriptor execution.__get__")
        return self.__dict__["execution"]

    @execution.setter
    def execution(self, value):
        self.__dict__["execution"] = value


class _R7LateRecursiveValuesHost(Host):
    """Install delegating recursive leaves in the LAST completed callback."""

    def __init__(self, f, *, timing, log):
        super().__init__(f)
        self.timing = timing
        self.log = log
        self.phase = None
        self.events = []

    def terminal_sample(self, request):
        self.phase = request.phase
        return super().terminal_sample(request)

    def authority_owner(self):
        owner = super().authority_owner()
        if self.phase == self.timing and not self.events:
            f = self.f
            S, D = _r7_string(self.log), _r7_mapping(self.log)
            f.selection = dict(f.selection, selected_basis_id=S(f.selection["selected_basis_id"]))
            f.execution = dict(f.execution)
            f.execution["host_binding"] = D(f.execution["host_binding"])
            f.ctx = replace(f.ctx, budget=D(f.ctx.budget))
            f._r7_armed = True   # from here on, ANY attribute read of execution logs
            self.events.append({"hook": "recursive delegating leaves", "body": f.calls})
        return owner


@pytest.mark.parametrize("timing", ["pre", "post"])
def test_r7_recursive_delegation_is_refused_before_any_user_call(
        tmp_path, strict_counter, timing):
    f = LocalFixture(tmp_path)
    log = []
    f.__class__ = _R7DescriptorFixture
    f._r7_log = log
    f._r7_armed = False
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    host = _R7LateRecursiveValuesHost(f, timing=timing, log=log)
    f.host = host
    f.source = replace(f.source, host=host)
    result = f.consume()
    body = f.calls
    assert host.events and host.events[0]["body"] == (0 if timing == "pre" else 1)
    # The exact-value contract refuses the str subclass, the nested dict
    # subclass and the descriptor BEFORE any .get/.items/__eq__/property call.
    assert log == [], log
    _ = f.execution   # the data descriptor IS live, but the final domain never used it
    assert log == ["descriptor execution.__get__"], log
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)
    assert any(c["verification"] == "strict-verified" for c in strict_counter)
    if timing == "pre":
        assert result.state == "blocked" and body == 0, result
        assert gates.parse(f.gate).effect == "not-started"
        assert f.map.read_bytes() == before
    else:
        assert result.state == "unknown" and body == 1, result
    replay = f.consume()
    assert replay.state != "applied" and f.calls == body


def test_r7_genuine_late_stop_without_delegation_is_still_detected(
        tmp_path, strict_counter):
    """No blanket reject: a REAL completed-callback stop is still caught."""
    f = LocalFixture(tmp_path)
    log = []
    f.__class__ = _R7DescriptorFixture
    f._r7_log = log
    f._r7_armed = False
    host = _R6LateFingerprintHost(f, timing="pre", kind="ctx-stop")
    f.host = host
    f.source = replace(f.source, host=host)
    result = f.consume()
    assert host.fired and log == []
    assert result.state == "blocked" and f.calls == 0, result
    assert gates.parse(f.gate).effect == "not-started"
    assert _no_dp_sink(f)
    assert any(c["verification"] == "strict-verified" for c in strict_counter)


def test_r7_recursive_exact_contract_unit_refuses_before_delegation():
    log = []
    S, D = _r7_string(log), _r7_mapping(log)

    class IntSub(int):
        def __eq__(self, other):
            log.append("int.__eq__")
            return int.__eq__(self, other)
        __hash__ = int.__hash__

    for value in (S("x"), D({"a": 1}), {"nested": {"deeper": S("y")}},
                  [1, (2, D({"z": 3}))], object(), IntSub(1)):
        with pytest.raises(ge.GateBlocked):
            ge._normalize_exact(value)
    assert log == [], "no user comparison/container method may run before refusal"
    tree = ge._normalize_exact({"a": ["x", (1, True, None, 2.5)], "b": {"c": "d"}})
    assert ge._frozen(tree)
    cyclic = []
    cyclic.append(cyclic)
    with pytest.raises(ge.GateBlocked):
        ge._normalize_exact(cyclic)
    with pytest.raises(ge.GateBlocked):
        ge._normalize_exact({"k": float("nan")})


def test_r7_controlled_cell_lifecycle_and_independent_association(tmp_path):
    f = LocalFixture(tmp_path)
    cell = f.cell
    assert cell.owner() is f and f.source.authority_cell is cell
    assert not cell.invalidated() and cell.rebinds() == 0
    base = cell.generation()
    first = cell.producer_domain()
    second = cell.producer_domain()
    assert cell.generation() == base + 2
    assert set(ge._CONTROLLED_DOMAIN_NAMES) <= set(first) == set(second)
    verified = cell.consumer_verify(f.host, f, base)
    assert set(verified) == set(first)
    # A raw host owner-slot change is detected without any virtual getter.
    g = LocalFixture(tmp_path / "g")
    g.cell.producer_domain()
    g.cell.producer_domain()
    g.host.f = copy.copy(g)
    with pytest.raises(ge.GateBlocked, match="rebound"):
        g.cell.consumer_verify(g.host, g, 0)
    # The controlled rebind API invalidates the cell permanently.
    cell.rebind(copy.copy(f))
    assert cell.invalidated() and cell.rebinds() == 1
    with pytest.raises(ge.GateBlocked, match="invalidated"):
        cell.consumer_verify(f.host, f, 0)


@pytest.mark.parametrize("worker_local", [False, True])
@pytest.mark.parametrize("benign_subclass", [False, True])
def test_r7_legal_dual_source_benign_subclass_strict_physical_apply_once(
        tmp_path, strict_counter, worker_local, benign_subclass):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    if benign_subclass:
        class PlainOwnerSubclass(LocalFixture):
            pass
        f.__class__ = PlainOwnerSubclass
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    result = f.consume()
    replay = f.consume()
    assert result.state == "applied" and result.receipt and f.calls == 1, result
    assert replay.state == "applied" and replay.duplicate and f.calls == 1
    assert [c["which"] for c in strict_counter][:2] == ["selection", "execution"]
    assert all(c["verification"] == "strict-verified" and not c["failure_codes"]
               for c in strict_counter)
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert f.map.read_bytes() != before
    assert _no_dp_sink(f)
    assert not f.cell.invalidated() and f.cell.generation() >= 4


def test_r7_final_domain_field_mapping_is_complete():
    assert set(ge._CONTROLLED_DOMAIN_NAMES) == {
        "ctx", "expectations", "evidence", "facts", "selection", "execution",
        "disposition_ok", "recovery_disposition_ok", "agenticdoc_root",
    }
    names = {fld.name for fld in dataclasses.fields(ge._FinalAuthority)}
    assert {"context", "selection", "execution", "selection_typed", "execution_typed",
            "context_state", "expectations_state", "action_evidence_state",
            "facts_state", "selection_state", "execution_state", "disposition_state",
            "state_fingerprint"} <= names


# ── T08-A-R8: four separated final-domain mechanisms, dual source x 3 phases ──
# Appended only. Each negative axis is independent, real strict/physical, and
# checks no delegation OR a genuine controlled-cell rejection, plus body/effect/
# replay. The old probes are copied byte-for-byte and run separately in ownrun.

_R8_AXES = ("storage-key", "producer-property",
            "owner-metaclass-mro", "sample-third-evidence")


def _r8_new_owner(f, log):
    new = copy.copy(f)
    new.ctx = replace(new.ctx, stop_scope="matter")
    new.cell = ge.ControlledAuthorityCell(new)
    new.source = replace(new.source, owner_state=new, authority_cell=new.cell)
    return new


class _R8ExecutionKey(str):
    def __new__(cls, base, log):
        return str.__new__(cls, base)

    def __init__(self, base, log):
        self._log = log

    def __eq__(self, other):
        self._log.append("storage-key.__eq__")
        return str.__eq__(self, other)
    __hash__ = str.__hash__


class _R8LateSample(ge.TerminalSample):
    @property
    def action_evidence(self):
        log = object.__getattribute__(self, "_r8_log")
        log.append("sample.action_evidence")
        if len(log) == 3:
            f = object.__getattribute__(self, "_r8_fixture")
            f.ctx = replace(f.ctx, stop_scope="matter")
        return object.__getattribute__(self, "__dict__")["action_evidence"]


class _R8AttackHost(Host):
    def __init__(self, f, *, kind, timing, log, strict_counter_ref):
        super().__init__(f, cell=f.cell)
        self.kind = kind
        self.timing = timing
        self.log = log
        self.strict_counter_ref = strict_counter_ref
        self.phase = None
        self.events = []

    def terminal_sample(self, request):
        self.phase = request.phase
        sample = super().terminal_sample(request)
        if self.kind == "sample-third-evidence" and request.phase == self.timing and sample is not None:
            object.__setattr__(sample, "__class__", _R8LateSample)
            object.__setattr__(sample, "_r8_log", self.log)
            object.__setattr__(sample, "_r8_fixture", self.f)
            self.events.append({"hook": "sample property armed", "phase": self.timing,
                                "body": self.f.calls})
        return sample

    def authority_owner(self):
        owner = super().authority_owner()
        if self.phase == self.timing and not any("installed" in e for e in self.events):
            f = self.f
            if self.kind == "storage-key":
                storage = object.__getattribute__(f, "__dict__")
                value = dict.pop(storage, "execution")
                key = _R8ExecutionKey("execution", self.log)
                assert hash(key) == hash("execution")
                dict.__setitem__(storage, key, value)
                self.events.append({"hook": "colliding storage key installed", "installed": True,
                                    "body": f.calls, "phase": self.timing})
            elif self.kind == "producer-property":
                new = _r8_new_owner(f, self.log)
                object.__setattr__(self, "__class__", _R8PropertyHost)
                self.f = new
                self.events.append({"hook": "property-backed producer owner rebind", "installed": True,
                                    "body": f.calls, "phase": self.timing,
                                    "new_cell_owner": new.cell.owner() is new})
            elif self.kind == "owner-metaclass-mro":
                new = _r8_new_owner(f, self.log)
                f.cell.rebind(new)
                self.events.append({"hook": "controlled-cell rebind after host-slot check", "installed": True,
                                    "body": f.calls, "phase": self.timing,
                                    "new_cell_owner": new.cell.owner() is new})
            elif self.kind == "sample-third-evidence":
                self.events.append({"hook": "third-read property armed", "installed": True,
                                    "body": f.calls, "phase": self.timing})
        return owner


class _R8PropertyHost(_R8AttackHost):
    @property
    def f(self):
        return self.__dict__["_producer_owner"]

    @f.setter
    def f(self, value):
        self.__dict__["_producer_owner"] = value
        if "f" not in self.__dict__:
            self.__dict__["f"] = value


def _r8_prepare(tmp_path, worker_local, timing, kind, log, strict_counter_ref):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    if timing == "recovery":
        first = f.consume()
        assert first.state == "applied" and f.calls == 1, first
    if kind == "owner-metaclass-mro":
        calls = []

        class OwnerMeta(type):
            def __getattribute__(cls, name):
                if name == "__mro__":
                    log.append("owner metaclass.__getattribute__(__mro__)")
                return type.__getattribute__(cls, name)

        class MetaFixture(LocalFixture, metaclass=OwnerMeta):
            pass

        f.__class__ = MetaFixture
    host = _R8AttackHost(f, kind=kind, timing=timing, log=log,
                         strict_counter_ref=strict_counter_ref)
    f.host = host
    f.source = replace(f.source, host=host)
    return f, host


@pytest.mark.parametrize("worker_local", [False, True])
@pytest.mark.parametrize("timing", ["pre", "post", "recovery"])
@pytest.mark.parametrize("kind", _R8_AXES)
def test_r8_four_separated_mechanisms_never_delegate_or_false_apply(
        tmp_path, strict_counter, worker_local, timing, kind):
    log = []
    f, host = _r8_prepare(tmp_path, worker_local, timing, kind, log, strict_counter)
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    result = f.consume()
    body = f.calls
    effect = gates.parse(f.gate).effect
    replay = f.consume()
    # Target mutation really reached the intended last-callback boundary.
    assert host.events and host.events[0]["body"] == (0 if timing == "pre" else 1)
    # NO unsafe delegation is invoked by the final authority domain, including
    # the storage key equality, metaclass MRO lookup and sample third read.
    assert log == [], (kind, timing, worker_local, log)
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)
    assert any(c["which"] == "execution" and c["verification"] == "strict-verified"
               and not c["failure_codes"] for c in strict_counter)
    if timing == "pre":
        assert result.state == "blocked" and body == 0, (kind, result)
        assert effect == "not-started" and f.map.read_bytes() == before
    else:
        assert result.state == "unknown" and body == 1, (kind, result)
        if timing != "recovery":
            assert effect == "unknown"
        else:
            assert effect == "applied", (kind, effect)
    assert replay.state != "applied" and f.calls == body, (kind, replay)
    if kind in ("producer-property", "owner-metaclass-mro"):
        assert any(e.get("new_cell_owner") for e in host.events)


@pytest.mark.parametrize("worker_local", [False, True])
@pytest.mark.parametrize("benign_subclass", [False, True])
def test_r8_legal_dual_source_benign_owner_subclass_strict_physical_apply_once(
        tmp_path, strict_counter, worker_local, benign_subclass):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    if benign_subclass:
        class PlainOwnerSubclass(LocalFixture):
            pass
        f.__class__ = PlainOwnerSubclass
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    result = f.consume()
    replay = f.consume()
    assert result.state == "applied" and result.receipt and f.calls == 1, result
    assert replay.state == "applied" and replay.duplicate and f.calls == 1
    assert [c["which"] for c in strict_counter][:2] == ["selection", "execution"]
    assert all(c["verification"] == "strict-verified" and not c["failure_codes"]
               for c in strict_counter)
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert f.map.read_bytes() != before
    assert _no_dp_sink(f)
    assert not f.cell.invalidated() and f.cell.generation() >= 4


def test_r8_exact_storage_key_is_refused_before_any_user_equality(tmp_path):
    f = LocalFixture(tmp_path / "exact")
    log = []
    storage = object.__getattribute__(f, "__dict__")
    value = dict.pop(storage, "execution")
    key = _R8ExecutionKey("execution", log)
    assert hash(key) == hash("execution")
    dict.__setitem__(storage, key, value)
    with pytest.raises(ge.GateBlocked):
        ge._read_controlled_domain(f)
    assert log == [], log


def test_r8_type_dispatch_and_mro_layout_never_call_user_protocols():
    calls = []

    class M(type):
        def __eq__(cls, other):
            calls.append("metaclass.__eq__")
            return False
        __hash__ = type.__hash__

    class Unknown(metaclass=M):
        pass

    with pytest.raises(ge.GateBlocked):
        ge._normalize_exact(Unknown())
    assert calls == [], calls

    class Meta(type):
        def __getattribute__(cls, name):
            if name == "__mro__":
                calls.append("metaclass.__getattribute__(__mro__)")
            return type.__getattribute__(cls, name)

    class Benign(metaclass=Meta):
        pass

    mro = ge._exact_mro(Benign())
    assert type(mro) is tuple and Benign in [k for k in mro if k is Benign]
    assert calls == [], calls


# ── T08-A-R10A: independent owner-raw-domain storage regressions ───────────
# APPENDED ONLY. The 53 original test functions, the two R7 recursive-hook
# functions and the genuine late-stop function above are byte/AST unchanged.
# These cases exercise the owner's EXACT instance dict directly through the
# real fixture / real strict / real physical / no-DP sink. They are neither
# reader-success stubs nor relaxed assertions: a same-named owner class
# property is not authority and is never invoked, while bad raw keys and
# delegating recursive leaves still fail closed before any user protocol.


class _R10ABenignPropertyOwner(LocalFixture):
    """Live class-level property on a controlled domain name (pass-through)."""
    @property
    def execution(self):
        log = object.__getattribute__(self, "_r10a_log")
        log.append("execution.__get__")
        return object.__getattribute__(self, "__dict__")["execution"]

    @execution.setter
    def execution(self, value):
        object.__getattribute__(self, "__dict__")["execution"] = value


class _R10AShadowingPropertyOwner(LocalFixture):
    """Property WOULD return a forged value; the raw dict must still win."""
    @property
    def execution(self):
        log = object.__getattribute__(self, "_r10a_log")
        log.append("execution.__get__")
        return {"forged": True}


class _R10AStorageKey(str):
    def __new__(cls, base, log):
        return str.__new__(cls, base)

    def __init__(self, base, log):
        self._log = log

    def __eq__(self, other):
        self._log.append("storage-key.__eq__")
        return str.__eq__(self, other)
    __hash__ = str.__hash__


class _R10ABadKeyHost(Host):
    """Install a colliding str-subclass raw key in the LAST retained callback."""
    def __init__(self, f, *, log, timing="pre"):
        super().__init__(f, cell=f.cell)
        self.log = log
        self.timing = timing
        self.phase = None
        self.events = []

    def terminal_sample(self, request):
        self.phase = request.phase
        return super().terminal_sample(request)

    def authority_owner(self):
        owner = super().authority_owner()
        if self.phase == self.timing and not self.events:
            f = self.f
            storage = object.__getattribute__(f, "__dict__")
            value = dict.pop(storage, "execution")
            key = _R10AStorageKey("execution", self.log)
            assert hash(key) == hash("execution")
            dict.__setitem__(storage, key, value)
            self.events.append({"hook": "colliding raw storage key",
                                "body": f.calls, "phase": self.timing})
        return owner


def _r10a_delegating_leaves(f, log):
    """Delegating recursive leaves in the LIVE owner raw domain only."""
    S, D = _r7_string(log), _r7_mapping(log)
    f.selection = dict(f.selection)
    f.selection["host_binding"] = dict(f.selection["host_binding"])
    f.selection["host_binding"]["run_id"] = S(f.selection["host_binding"]["run_id"])
    f.selection["selected_basis_id"] = S(f.selection["selected_basis_id"])
    f.execution = dict(f.execution)
    f.execution["host_binding"] = D(f.execution["host_binding"])


def test_r10a_benign_owner_domain_property_never_invoked_and_releases_once(
        tmp_path, strict_counter):
    f = LocalFixture(tmp_path)
    log = []
    f.__class__ = _R10ABenignPropertyOwner
    f._r10a_log = log
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    result = f.consume()
    replay = f.consume()
    assert result.state == "applied" and result.receipt and f.calls == 1, result
    assert replay.state == "applied" and replay.duplicate and f.calls == 1
    assert gates.parse(f.gate).effect == "applied"
    assert f.map.read_bytes() != before, "exactly one real object write"
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)
    assert [c["which"] for c in strict_counter][:2] == ["selection", "execution"]
    assert all(c["verification"] == "strict-verified" and not c["failure_codes"]
               for c in strict_counter), "real strict, no success stub"
    # Producer AND consumer read the exact instance dict; the property is dead.
    assert log == [], log
    raw, tree = ge._read_controlled_domain(f)
    assert set(ge._CONTROLLED_DOMAIN_NAMES) <= set(raw) and type(tree) is str
    assert log == [], log
    _ = f.execution   # the descriptor really IS live, but never used by the gate
    assert log == ["execution.__get__"], log


def test_r10a_owner_raw_dict_is_authority_not_same_named_property(tmp_path):
    f = LocalFixture(tmp_path)
    log = []
    f.__class__ = _R10AShadowingPropertyOwner
    f._r10a_log = log
    raw, tree = ge._read_controlled_domain(f)
    assert log == [], log
    assert type(tree) is str
    actual = dict.__getitem__(raw, "execution")
    assert actual is object.__getattribute__(f, "__dict__")["execution"]
    assert "action_ref" in actual, "raw domain value, not the forged property"
    forged = f.execution
    assert log == ["execution.__get__"], log
    assert forged == {"forged": True}


def test_r10a_bad_owner_storage_key_refused_before_user_equality(
        tmp_path, strict_counter):
    f = LocalFixture(tmp_path)
    log = []
    host = _R10ABadKeyHost(f, log=log, timing="pre")
    f.host = host
    f.source = replace(f.source, host=host)
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    result = f.consume()
    assert host.events and host.events[0]["body"] == 0, host.events
    assert result.state == "blocked" and f.calls == 0, result
    assert gates.parse(f.gate).effect == "not-started"
    assert f.map.read_bytes() == before
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)
    assert log == [], (log, "no user __eq__ may run before the exact-str refusal")
    assert any(c["which"] == "execution" and c["verification"] == "strict-verified"
               and not c["failure_codes"] for c in strict_counter), "real strict ran"
    with pytest.raises(ge.GateBlocked):
        ge._read_controlled_domain(f)
    assert log == [], log
    replay = f.consume()
    assert replay.state != "applied" and f.calls == 0


def test_r10a_recursive_delegating_leaf_refused_before_any_user_protocol(
        tmp_path, strict_counter):
    f = LocalFixture(tmp_path)
    log = []
    _r10a_delegating_leaves(f, log)
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    result = f.consume()
    assert result.state == "blocked" and f.calls == 0, result
    assert gates.parse(f.gate).effect == "not-started"
    assert f.map.read_bytes() == before
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)
    assert log == [], (log, "no .get/.items/__eq__/property call before refusal")
    assert any(c["which"] == "execution" and c["verification"] == "strict-verified"
               and not c["failure_codes"] for c in strict_counter), "real strict ran"
    with pytest.raises(ge.GateBlocked):
        ge._read_controlled_domain(f)
    assert log == [], log



# ── T08-A-R11: B1 live-key closure, B2 native Path slots, identity refusals ──
# APPENDED ONLY. The original 57 test functions and their assertions above are
# byte-identical. No schema/global-class defense, module-function replacement,
# tracing/frame mutation, thread or arbitrary-memory exploit is used.


class _R11StrKey(str):
    """A real str-subclass key whose user protocols must NEVER be called."""

    def __new__(cls, base, log):
        return str.__new__(cls, base)

    def __init__(self, base, log):
        self._log = log

    def __eq__(self, other):
        list.append(self._log, "eq")
        return str.__eq__(self, other)

    def __hash__(self):
        list.append(self._log, "hash")
        return str.__hash__(self)

    def __len__(self):
        list.append(self._log, "len")
        return str.__len__(self)

    def __bool__(self):
        list.append(self._log, "bool")
        return str.__bool__(self)


class _R11CollidingKey(_R11StrKey):
    """Same hash as an exact key but denies equality so both keys coexist."""

    def __eq__(self, other):
        list.append(self._log, "eq")
        return False

    def __hash__(self):
        list.append(self._log, "hash")
        return str.__hash__(self)


def test_r11_b1_live_key_closure_refuses_with_zero_user_protocols():
    log = []
    live = {"k": "v"}
    held = ge._native_recheck_snapshot(live)
    live.clear()
    live[_R11StrKey("k", log)] = "v"
    assert type(tuple.__getitem__(tuple(dict.keys(live)), 0)) is _R11StrKey
    log.clear()
    assert ge._native_recheck_matches(live, held) is False
    assert log == [], log
    with pytest.raises(ge.GateBlocked):
        ge._native_recheck_snapshot(live)
    assert log == [], log

    live2 = {"k": "v"}
    held2 = ge._native_recheck_snapshot(live2)
    live2[_R11CollidingKey("k", log)] = "v"
    keys2 = tuple(dict.keys(live2))
    assert tuple.__len__(keys2) == 2
    assert any(type(key) is str and str.__eq__(key, "k") for key in keys2)
    assert any(type(key) is _R11CollidingKey for key in keys2)
    log.clear()
    assert ge._native_recheck_matches(live2, held2) is False
    assert log == [], log
    with pytest.raises(ge.GateBlocked):
        ge._native_recheck_snapshot(live2)
    assert log == [], log

    ordinary = {"k": ["v", 2, True], "nested": {"x": "y"}}
    held3 = ge._native_recheck_snapshot(ordinary)
    assert ge._native_recheck_matches(ordinary, held3) is True
    ordinary["k"][0] = "changed"
    assert ge._native_recheck_matches(ordinary, held3) is False
    ordinary["k"][0] = "v"
    ordinary["extra"] = "added"
    assert ge._native_recheck_matches(ordinary, held3) is False
    dict.pop(ordinary, "nested")
    assert ge._native_recheck_matches(ordinary, held3) is False
    assert ge._native_recheck_matches({"nested": {"x": "y"}, "k": ["v", 2, True]}, held3) is True


def _r11_slot_index(name):
    for i in range(tuple.__len__(ge._PATH_SLOT_NAMES)):
        if str.__eq__(tuple.__getitem__(ge._PATH_SLOT_NAMES, i), name):
            return i
    raise AssertionError(name)


def test_r11_b2_native_path_values_are_detached_and_fresh():
    # Independent axes: mutable raw parts, mutable tail cache, exact str cache,
    # exact int hash cache. One changed slot per snapshot; no combined bad leaf.
    axes = (
        ("_raw_paths", ["alpha/beta"], "changed/target"),
        ("_tail_cached", ["alpha", "beta"], "changed"),
        ("_str", "alpha\\beta", "changed"),
        ("_hash", 7, 8),
    )
    for name, initial, changed in axes:
        path = pathlib.Path("alpha/beta")
        descriptor = dict.__getitem__(ge._PATH_SLOT_DESCRIPTORS, name)
        if name != "_raw_paths":
            descriptor.__set__(path, initial)
        held = ge._native_recheck_snapshot(path)
        assert tuple.__getitem__(held, 0) == "path" and tuple.__len__(held) == 3
        slots = tuple.__getitem__(held, 2)
        assert type(slots) is tuple
        slot = tuple.__getitem__(slots, _r11_slot_index(name))
        assert type(tuple.__getitem__(slot, 0)) is str
        if type(initial) is list:
            live_slot = ge._path_slot(path, name)
            held_parts = tuple.__getitem__(slot, 1)
            assert type(held_parts) is tuple and held_parts is not live_slot
            assert all(type(part) is str for part in held_parts)
            assert ge._native_recheck_matches(path, held) is True
            list.__setitem__(live_slot, 0, changed)
        else:
            assert type(tuple.__getitem__(slot, 1)) is type(initial)
            assert ge._native_recheck_matches(path, held) is True
            descriptor.__set__(path, changed)
        assert ge._native_recheck_matches(path, held) is False

    ordinary = pathlib.Path("alpha/beta")
    held = ge._native_recheck_snapshot(ordinary)
    assert ge._native_recheck_matches(ordinary, held) is True
    assert ge._native_recheck_matches(pathlib.Path("alpha/beta"), held) is False


class _R11B1StorageHost(Host):
    """Install a colliding owner-storage key in the actual retained callback."""

    def __init__(self, f, log):
        super().__init__(f)
        self.log = log
        self.events = []
        self.cell = None

    def terminal_sample(self, request):
        self.cell = request.source.authority_cell
        return super().terminal_sample(request)

    def authority_owner(self):
        owner = super().authority_owner()
        if not self.events:
            assert self.cell is f_owner(self)
            storage = object.__getattribute__(owner, "__dict__")
            value = dict.pop(storage, "execution")
            key = _R11StrKey("execution", self.log)
            dict.__setitem__(storage, key, value)
            installed = tuple(dict.keys(storage))
            assert any(type(item) is _R11StrKey for item in installed)
            self.events.append({"installed": True, "body": self.f.calls,
                                "keys": tuple.__len__(installed)})
            self.log.clear()
        return owner


def f_owner(host):
    return object.__getattribute__(host, "_authority_cell")


def test_r11_b1_fixture_preparation_route_is_closed_before_suffix(
        tmp_path, strict_counter):
    f = LocalFixture(tmp_path)
    log = []
    host = _R11B1StorageHost(f, log)
    f.host = host
    f.source = replace(f.source, host=host)
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    result = f.consume()
    assert host.events and host.events[0]["installed"] and host.events[0]["body"] == 0
    assert result.state == "blocked" and f.calls == 0, result
    assert gates.parse(f.gate).effect == "not-started"
    assert f.map.read_bytes() == before
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)
    assert any(c["which"] == "execution" and c["verification"] == "strict-verified"
               and not c["failure_codes"] for c in strict_counter)
    assert log == [], log
    with pytest.raises(ge.GateBlocked):
        ge._read_controlled_domain(f)
    assert log == [], log
    replay = f.consume()
    assert replay.state != "applied" and f.calls == 0
    assert log == [], log


class _R11B2PathHost(Host):
    """Mutate a Host-reachable action Path in the actual retained callback."""

    def __init__(self, f):
        super().__init__(f)
        self.events = []
        self.action = None
        self.cell = None

    def terminal_sample(self, request):
        self.action = request.facts.action
        self.cell = request.source.authority_cell
        sample = super().terminal_sample(request)
        if not self.events:
            raw = ge._native_instance_storage(self.action)
            path = dict.__getitem__(raw, "object_path")
            parts = ge._path_slot(path, "_raw_paths")
            before = tuple(parts)
            list.__setitem__(parts, 0, "changed/target")
            after = tuple(parts)
            self.events.append({"before": before, "after": after,
                                "body": self.f.calls, "cell": self.cell is self.f.cell,
                                "source_cell": self.cell is request.source.authority_cell,
                                "action": self.action is self.f.action is request.facts.action,
                                "path": path is self.f.action.object_path,
                                "installed": tuple(ge._path_slot(path, "_raw_paths")),
                                "sample": type(sample) is ge.TerminalSample,
                                "phase": request.phase})
        return sample


def test_r11_b2_fixture_preparation_route_is_closed_before_suffix(
        tmp_path, strict_counter):
    f = LocalFixture(tmp_path)
    host = _R11B2PathHost(f)
    f.host = host
    f.source = replace(f.source, host=host)
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    result = f.consume()
    assert host.events and host.events[0]["before"] != host.events[0]["after"]
    assert host.events[0]["body"] == 0 and host.events[0]["cell"] is True
    assert host.events[0]["source_cell"] is True
    assert host.events[0]["action"] is True and host.action is f.action is f.facts.action
    assert host.events[0]["path"] is True
    assert host.events[0]["installed"] == host.events[0]["after"]
    assert host.events[0]["after"][0] == "changed/target"
    assert host.events[0]["sample"] is True and host.events[0]["phase"] == "pre"
    assert host.cell is f.cell is f.source.authority_cell
    # This real retained callback precedes preparation. The existing native
    # Path-cache consistency guard rejects the installed mutation BEFORE the
    # final suffix; only the separate primitive test proves suffix freshness.
    assert result.reason == "final authority Path string cache is inconsistent", result
    with pytest.raises(ge.GateBlocked, match="^final authority Path string cache is inconsistent$"):
        ge._exact_path_state(f.action.object_path)
    assert result.state == "blocked" and f.calls == 0, result
    assert gates.parse(f.gate).effect == "not-started"
    assert f.map.read_bytes() == before
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)
    assert any(c["which"] == "execution" and c["verification"] == "strict-verified"
               and not c["failure_codes"] for c in strict_counter)
    replay = f.consume()
    assert replay.state != "applied" and f.calls == 0


def _r11_identity_class(axis, log):
    class Hooks(tuple):
        def __eq__(self, other):
            list.append(log, "eq")
            return tuple.__eq__(self, other)

        def __hash__(self):
            list.append(log, "hash")
            return tuple.__hash__(self)

        def __bool__(self):
            list.append(log, "bool")
            return tuple.__bool__(self)

        def __iter__(self):
            list.append(log, "iter")
            return tuple.__iter__(self)

    class LenHostile(Hooks):
        def __len__(self):
            list.append(log, "len")
            return tuple.__len__(self)

    class IndexHostile(Hooks):
        def __getitem__(self, index):
            list.append(log, "index")
            return tuple.__getitem__(self, index)

    return LenHostile if axis == "len" else IndexHostile


class _R11IdentityHost(Host):
    """Install ONE hostile identity tuple through request.source.authority_cell."""

    def __init__(self, f, *, timing, axis, log):
        super().__init__(f)
        self.timing = timing
        self.axis = axis
        self.log = log
        self.phase = None
        self.cell = None
        self.events = []
        self.pin = None
        self.hostile = None
        self.hostile_class = None

    def terminal_sample(self, request):
        self.phase = request.phase
        self.cell = request.source.authority_cell
        return super().terminal_sample(request)

    def authority_owner(self):
        owner = super().authority_owner()
        if self.phase == self.timing and not self.events:
            state = ge._read_cell_state(self.cell)
            pin = dict.__getitem__(state, "_writer_pin")
            base = tuple.__getitem__(ge._read_writer_pin_state(pin), 4)
            cls = _r11_identity_class(self.axis, self.log)
            hostile = cls(base)
            descriptor = dict.__getitem__(ge._WRITER_PIN_SLOT_DESCRIPTORS,
                                          "apply_identity")
            descriptor.__set__(pin, hostile)
            current = descriptor.__get__(pin, ge._WriterPin)
            assert current is hostile and type(current) is cls
            self.pin, self.hostile, self.hostile_class = pin, hostile, cls
            self.events.append({"installed": True, "axis": self.axis,
                                "phase": self.phase, "body": self.f.calls})
            self.log.clear()
        return owner


@pytest.mark.parametrize("worker_local", [False, True])
@pytest.mark.parametrize("timing", ["pre", "post", "recovery"])
@pytest.mark.parametrize("axis", ["len", "index"])
def test_r11_identity_len_index_refusal_pre_post_recovery_dual_source(
        tmp_path, strict_counter, worker_local, timing, axis):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    if timing == "recovery":
        first = f.consume()
        assert first.state == "applied" and f.calls == 1, first
    log = []
    host = _R11IdentityHost(f, timing=timing, axis=axis, log=log)
    f.host = host
    f.source = replace(f.source, host=host)
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    result = f.consume()
    body = f.calls
    # The hostile identity really reached the durable cell slot; no stub.
    assert host.events and host.events[0]["installed"], host.events
    assert host.events[0]["body"] == (0 if timing == "pre" else 1)
    assert host.events[0]["phase"] == timing
    state = ge._read_cell_state(f.cell)
    pin = dict.__getitem__(state, "_writer_pin")
    current = dict.__getitem__(ge._WRITER_PIN_SLOT_DESCRIPTORS,
                               "apply_identity").__get__(pin, ge._WriterPin)
    assert current is host.hostile and type(current) is host.hostile_class
    assert log == [], log
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)
    assert any(c["which"] == "execution" and c["verification"] == "strict-verified"
               and not c["failure_codes"] for c in strict_counter)
    if timing == "pre":
        assert result.state == "blocked" and body == 0, result
        assert gates.parse(f.gate).effect == "not-started"
        assert f.map.read_bytes() == before
    elif timing == "post":
        assert result.state == "unknown" and body == 1, result
        assert gates.parse(f.gate).effect == "unknown"
    else:
        assert result.state == "unknown" and body == 1, result
        assert gates.parse(f.gate).effect == "applied"
    replay = f.consume()
    assert replay.state != "applied" and f.calls == body
    assert log == [], log


@pytest.mark.parametrize("worker_local", [False, True])
@pytest.mark.parametrize("property_owner", [False, True])
def test_r11_ordinary_property_owner_dual_source_apply1_replay0_control(
        tmp_path, strict_counter, worker_local, property_owner):
    f = LocalFixture(tmp_path)
    if worker_local:
        _to_worker_local(f)
    log = []
    if property_owner:
        f.__class__ = _R10ABenignPropertyOwner
        f._r10a_log = log
    physical = (f.selection_path.read_bytes(), f.execution_path.read_bytes())
    before = f.map.read_bytes()
    result = f.consume()
    replay = f.consume()
    assert result.state == "applied" and result.receipt and f.calls == 1, result
    assert replay.state == "applied" and replay.duplicate and f.calls == 1
    assert gates.parse(f.gate).effect == "applied"
    assert f.map.read_bytes() != before
    assert (f.selection_path.read_bytes(), f.execution_path.read_bytes()) == physical
    assert _no_dp_sink(f)
    assert [c["which"] for c in strict_counter][:2] == ["selection", "execution"]
    assert all(c["verification"] == "strict-verified" and not c["failure_codes"]
               for c in strict_counter)
    assert log == [], log
