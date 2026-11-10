"""Consume one prepared gate answer against a controlled, bounded project operation.

The host binds the PM, ledger and object adapter. No adapter or permission comes
from the gate file. A durable in-progress reservation precedes the mutation.
On interruption only object inspection may complete a reservation.
"""
from __future__ import annotations

import hashlib
import os
import pathlib
import socket
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

import decision_lifecycle as lifecycle
import decision_policy as policy
import decision_validity as validity
import decision_wire as wire
import mw_common
from . import config, gates, state


@dataclass(frozen=True)
class ObjectReceipt:
    """The adapter found this decision's effect on the actual bounded object."""
    decision_ref: str
    sha256: str


@dataclass(frozen=True)
class BoundAction:
    """Local handler selected by trusted product code for the PM's prepared action.

    inspect must distinguish the action's own evidence from an object that
    happened to be in the desired state. apply must use the existing object's
    lock and version checks. Neither callback may issue a model request.
    """
    name: str
    object_path: pathlib.Path
    apply: Callable[[gates.Gate], None]
    inspect: Callable[[gates.Gate], ObjectReceipt | None]
    legacy_closure: bool = False
    lifecycle_action: str = "record"


@dataclass(frozen=True)
class GateFacts:
    """Fresh facts observed by the bound host, never decoded from a model answer."""
    matter: validity.Matter
    pm_note: str
    scope: tuple[str, ...]
    authority_source: Mapping[str, policy.AuthorityRecord]
    trusted_writers: tuple[str, ...]
    hard_checks: Mapping[str, bool]
    usage_by_source: Mapping[str, int]
    spend_by_unit: Mapping[str, int]
    action: BoundAction | None = None


@dataclass(frozen=True)
class GateEffectResult:
    state: str
    reason: str
    parent_ref: str | None = None
    follow_up: str | None = None
    receipt: str | None = None
    duplicate: bool = False


class GateBlocked(ValueError):
    pass


class ActionNotApplied(Exception):
    """The trusted object writer established that its CAS made no change."""


@contextmanager
def _lock(path: pathlib.Path):
    try:
        mw_common.acquire_lock(path, retries=0)
    except RuntimeError as exc:
        raise GateBlocked(f"lock busy: {path.name}") from exc
    try:
        yield
    finally:
        mw_common.release_lock(path)


def _replace_effect(gate: gates.Gate, effect: str, *, legacy: bool = False) -> None:
    """Caller holds gates.lock and has parsed the complete original file."""
    if gate.effect == effect and (not legacy or gate.closure_kind == "legacy"):
        return
    with gate.path.open(encoding="utf-8", newline="") as handle:
        lines = handle.readlines()
    for i, line in enumerate(lines[1:], 1):
        if line.strip() == "---":
            break
        name = line.partition(":")[0]
        if name == "effect" or (name == "closure_kind" and legacy):
            ending = line[len(line.rstrip("\r\n")):]
            lines[i] = f"{name}: {effect if name == 'effect' else 'legacy'}{ending}"
    gates._write_atomic(gate.path, "".join(lines))


def _ledger_rows(store: lifecycle.LifecycleStore, meta: lifecycle.DecisionMeta, gate: gates.Gate) -> list[dict]:
    read = lifecycle.read_lifecycle(store)
    if any(getattr(read.stats, key) for key in ("bad_json", "bad_utf8", "unknown_schema", "oversized_line", "incomplete_tail")):
        raise GateBlocked("incomplete decision ledger")
    rows = [r for r in read.events if r.get("scope") == "production" and r.get("project_id") == store.project_id
            and r.get("logical_id") == meta.logical_id
            and r.get("key") == meta.key and r.get("task_key") == meta.task_key]
    starts = [r for r in rows if r.get("kind") == "record-start" and r.get("record_version") == meta.record_version
              and r.get("initiator_role") == "pm" and r.get("task_before") == meta.task_before]
    start_index = rows.index(starts[0]) if len(starts) == 1 else len(rows)
    rows = [r for r in rows[start_index + 1:] if r.get("decision_id") == gate.decision_ref]
    requests = [r for r in rows if r.get("kind") == "request" and r.get("business_decisions") == 1]
    if len(starts) != 1 or len(requests) != 1:
        raise GateBlocked("missing or conflicting PM decision record")
    request = requests[0]
    if (request.get("dp") != "dp-gate-approve" or request.get("available") is not True
            or request.get("choice") != gate.business or request.get("basis_text") != gate.model_basis
            or request.get("basis_source") != "pm-prepared" or not request.get("basis_catalog_sha256")):
        raise GateBlocked("recorded decision and gate choice or basis do not match")
    notes = [r for r in rows[:rows.index(request)] if r.get("kind") == "note"
             and r.get("note_source") == "pm-prepared" and r.get("prepared_at") == request.get("prepared_at")]
    if len(notes) != 1 or notes[0].get("pm_note") != gate.pm_note:
        raise GateBlocked("missing or changed PM note before decision submission")
    return rows


def _check_facts(project: pathlib.Path, meta: lifecycle.DecisionMeta, claim: str, gate: gates.Gate,
                 facts: GateFacts) -> policy.GateVerdict:
    matter = facts.matter
    current = validity.matter_for(matter.subject, matter.object, matter.action, matter.dependencies,
                                  matter_kind=matter.matter_kind, contract_version=matter.contract_version,
                                  authority_required=matter.authority_required)
    if (validity.business_owner_for(matter.matter_kind) != "dp-gate-approve" or not matter.dependencies
            or matter.unknown_dependencies or matter.matter_key != gate.matter_ref
            or current.matter_key != gate.matter_ref or current.substantive_version != gate.substantive_version
            or matter.substantive_version != gate.substantive_version or facts.pm_note != gate.pm_note):
        raise GateBlocked("matter, substantive version or bounded PM note changed")
    claims = [r for r in state.read_index(project) if r["key"] == meta.key]
    # The writable gate/index can name another live PM window. Only the
    # owner process or its direct non-worker bridge may exercise that claim.
    owner = mw_common.parse_synthetic_claim(claim)
    local_owner = {f"{socket.gethostname()}:{pid}" for pid in (os.getpid(), os.getppid())}
    process_claim = f"{owner[0]}:{owner[1]}" if owner else claim
    if (len(claims) != 1 or claims[0]["status"] != "active" or claims[0]["claim_id"] != claim
            or state.claim_state(claim) != state.CLAIM_LIVE or gate.answered_by != claim
            or process_claim not in local_owner or os.environ.get("PI_WORKER_TASK")):
        raise GateBlocked("bound PM claim is no longer the live owner")
    cfg = config.load_config(project)
    machine = dict(facts.hard_checks)
    if not machine:
        raise GateBlocked("missing target machine checks")
    loaded = policy.load_policy(project)
    granted = policy.evaluate_gate(
        loaded, choice=gate.business, hard_checks=machine,
        automation_enabled=cfg.get("enabled") is True and not cfg.get("paused") and cfg.get("auto_gate_mode") == "live",
        required_scope=facts.scope, authority_source=facts.authority_source, trusted_writers=facts.trusted_writers,
    )
    issues = [f"{i.code}:{i.field}" for i in granted.reasons if i.code != "choice-not-approve"]
    if issues:
        raise GateBlocked(", ".join(issues))
    if gate.business == "approve" and not granted.allowed:
        raise GateBlocked("policy refused release")
    if loaded.policy is None or not loaded.policy.hard_limits:
        raise GateBlocked("missing verifiable hard budget")
    units = {limit.unit for limit in loaded.policy.hard_limits}
    if set(facts.spend_by_unit) != units:
        raise GateBlocked("missing or unknown action budget units")
    for limit in loaded.policy.hard_limits:
        delta = facts.spend_by_unit[limit.unit]
        used = facts.usage_by_source.get(limit.usage_source)
        if type(delta) is not int or delta < 0 or type(used) is not int or not 0 <= used <= limit.limit:
            raise GateBlocked(f"invalid or exhausted hard budget: {limit.unit}")
        if delta and not policy.check_spend(loaded, unit=limit.unit, amount=delta, usage={limit.unit: used}).allowed:
            raise GateBlocked(f"hard budget exceeded: {limit.unit}")
    return granted


def _receipt(project: pathlib.Path, action: BoundAction, gate: gates.Gate) -> str | None:
    target = (project / action.object_path).resolve()
    if (target == project or not target.is_relative_to(project) or action.object_path.is_absolute()
            or target != project / action.object_path):
        raise GateBlocked("bounded target must be project-relative")
    receipt = action.inspect(gate)
    if receipt is None:
        return None
    if receipt.decision_ref != gate.decision_ref or not target.is_file():
        raise GateBlocked("object receipt lacks a matching decision or regular file")
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    if digest.hexdigest() != receipt.sha256:
        raise GateBlocked("object receipt does not match the decision or actual target bytes")
    return f"{target.relative_to(project).as_posix()}#{receipt.sha256}"


def _has_event(rows: list[dict], event_id: str, **fields: object) -> bool:
    matches = [row for row in rows if row.get("event_id") == event_id]
    return len(matches) == 1 and all(matches[0].get(name) == value for name, value in fields.items())


def consume_gate(project_root: pathlib.Path, gate_id: str, *, store: lifecycle.LifecycleStore,
                 meta: lifecycle.DecisionMeta, claim_id: str,
                 observe: Callable[[gates.Gate], GateFacts]) -> GateEffectResult:
    """Observe the registered operation, reserve its matter and verify its real effect.

    A steer/fix result identifies the parent and target for the existing PM
    follow-up producer. No successor request is implied here. A rejected plan
    has no action unless the prepared object explicitly binds legacy closure.
    """
    project = pathlib.Path(project_root).resolve()
    if not isinstance(gate_id, str) or not gates.GATE_ID_RE.fullmatch(gate_id):
        return GateEffectResult("blocked", "invalid gate ID")
    directory = project / ".agenticdoc" / "_autopilot" / "gates"
    path = directory / (gate_id + ".md")
    gate_lock = project / ".mw" / "gates.lock"
    reserved = False
    try:
        if path.resolve() != path or not gate_lock.resolve().is_relative_to(project):
            raise GateBlocked("gate or lock path is redirected")
        initial = gates.parse(path)
        if initial.historical or initial.transport != "answered":
            raise GateBlocked("historical or unanswered gate")
        if (store.scope_kind != "production" or store.sink.resolve() != wire.production_lifecycle_sink(project)
                or store.project_id != wire.project_id_for(project)):
            raise GateBlocked("a bound production ledger in this project is required")
        if (meta.initiator_role != "pm" or initial.key not in (None, meta.key)
                or initial.decision_ref != "dp-gate-approve:" + meta.logical_id):
            raise GateBlocked("decision and bound PM identity do not match the gate")
        matter_lock = hashlib.sha256(initial.matter_ref.encode()).hexdigest()
        with _lock(project / ".mw" / f"matter-{matter_lock}.lock"):
            with _lock(gate_lock):
                gate = gates.parse(path)
                if gate != initial or gate.id != gate_id:
                    raise GateBlocked("gate changed before reservation")
                rows = _ledger_rows(store, meta, gate)
                facts = observe(gate)
                granted = _check_facts(project, meta, claim_id, gate, facts)
                peers = [g for g in gates.enumerate(directory) if g.matter_ref == gate.matter_ref]
                if any(g.substantive_version != gate.substantive_version and g.effect in ("in-progress", "unknown") for g in peers):
                    raise GateBlocked("an earlier version has an unresolved effect")
                same = [g for g in peers if g.substantive_version == gate.substantive_version and g.transport == "answered"]
                if any(g.decision_ref != gate.decision_ref or g.business != gate.business for g in same):
                    raise GateBlocked("conflicting approvals for the same substantive matter")
                action = facts.action
                plan = validity.plan_actions([
                    validity.EffectRecord(g.id, g.decision_ref, g.matter_ref, g.substantive_version,
                                          (facts.matter.action,), g.effect) for g in same
                ], matter=facts.matter, actions=(facts.matter.action,))
                owners = [g for g in same if g.effect in ("in-progress", "unknown", "applied")]
                if len(owners) > 1:
                    raise GateBlocked("multiple reserved gates require reconciliation")
                owner = owners[0] if owners else same[0]
                if owner.id != gate.id:
                    return GateEffectResult("blocked", f"same matter owned by {owner.id}", gate.decision_ref, duplicate=True)
                actor = {"kind": "system", "id": claim_id}
                common = dict(store=store, meta=meta, decision_id=gate.decision_ref, dp="dp-gate-approve",
                              actor=("system", claim_id))
                event_prefix = "gate-" + hashlib.sha256(gate.decision_ref.encode()).hexdigest()
                consumed_id = event_prefix+"-consumed"
                consumed = lifecycle.record_consumed(**common, answer=gate.business, event_id=consumed_id)
                if not consumed.recorded or (consumed.status == "duplicate" and not _has_event(
                        rows, consumed_id, kind="lifecycle", lifecycle="consumed", answer=gate.business, actor=actor)):
                    raise GateBlocked("could not record decision consumption")
                if gate.business in ("steer", "need_fix") or (gate.business == "reject" and action is None):
                    target = granted.follow_up
                    reason = f"awaiting prepared PM follow-up {target}" if target else "proposal rejected without legacy closure"
                    outcome = "pending" if target else "inconclusive"
                    disposition = lifecycle.record_settled(**common, outcome=outcome, reason=reason,
                                                          event_id=event_prefix+"-handoff")
                    if not disposition.recorded or (disposition.duplicate and not _has_event(
                            rows, event_prefix+"-handoff", lifecycle="settled", outcome=outcome, reason=reason, actor=actor)):
                        raise GateBlocked("could not record selection disposition")
                    _replace_effect(gate, "blocked")
                    return GateEffectResult("blocked", reason, gate.decision_ref, target)
                if (action is None or action.name != facts.matter.action or action.name not in facts.scope
                        or action.lifecycle_action not in lifecycle.EXECUTED_ACTIONS):
                    raise GateBlocked("no bounded action for this prepared matter and scope")
                legacy = gate.business == "reject"
                if action.legacy_closure != legacy or (legacy and "gate:legacy-close" not in facts.scope):
                    raise GateBlocked("no explicit legacy closure action and authority")
                # Validate the bound target before reservation or execution.
                recovering = plan.status in ("already-applied", "blocked")
                reserved = gate.effect in ("in-progress", "unknown")
                receipt = _receipt(project, action, gate)
                executed_id, settled_id = event_prefix+"-executed", event_prefix+"-settled"
                execution = dict(kind="lifecycle", lifecycle="executed", action=action.lifecycle_action, reason=action.name, actor=actor)
                if recovering and receipt is None:
                    if gate.effect == "in-progress":
                        _replace_effect(gate, "unknown")
                    return GateEffectResult("unknown", "actual target does not prove the reserved effect", gate.decision_ref)
                if plan.status == "already-applied":
                    if (not _has_event(rows, executed_id, **execution, result=receipt)
                            or not _has_event(rows, settled_id, kind="lifecycle", lifecycle="settled", outcome="ok", reason=receipt, actor=actor)):
                        raise GateBlocked("applied marker lacks the matching executed and settled receipts")
                    return GateEffectResult("applied", "already recorded", gate.decision_ref, receipt=receipt, duplicate=True)
                if not recovering:
                    if receipt is not None:
                        raise GateBlocked("object already changed without this gate's reservation")
                    if any(r.get("lifecycle") == "executed" or r.get("event_id") == settled_id for r in rows):
                        raise GateBlocked("existing execution record conflicts with unreserved gate")
                    # Object inspection can outlive an authorization/claim or
                    # change a target version. Resolve the live host binding
                    # once more immediately before recording the intent.
                    fresh = observe(gate)
                    _check_facts(project, meta, claim_id, gate, fresh)
                    if (fresh.action is None or fresh.action.object_path != action.object_path
                            or fresh.action.name != action.name or fresh.action.legacy_closure != legacy
                            or fresh.action.lifecycle_action != action.lifecycle_action or fresh.scope != facts.scope):
                        raise GateBlocked("bounded action changed during preparation")
                    action = fresh.action
                    _replace_effect(gate, "in-progress")
                    reserved = True
            # The matter lock serializes consumers. Release the shared gates lock
            # before the object's own bounded write; no model or queue wait here.
            refused = False
            error = ""
            if not recovering:
                try:
                    action.apply(gate)
                except ActionNotApplied:
                    refused = True
                except Exception as exc:
                    # A writer may have changed the object before reporting an
                    # error. Reconcile the actual object, never repeat apply.
                    error = " after " + type(exc).__name__
            with _lock(gate_lock):
                current = gates.parse(path)
                if (current.decision_ref, current.matter_ref, current.substantive_version, current.business,
                        current.pm_note, current.effect) != (
                        gate.decision_ref, gate.matter_ref, gate.substantive_version, gate.business,
                        gate.pm_note, "in-progress" if not recovering else gate.effect):
                    return GateEffectResult("unknown", "gate changed during object operation", gate.decision_ref)
                receipt = _receipt(project, action, current)
                if receipt is None:
                    if refused:
                        if not lifecycle.record_settled(**common, outcome="inconclusive", reason="target CAS refused",
                                event_id=event_prefix+"-cas-refused").recorded:
                            return GateEffectResult("unknown", "target refusal lacks settlement evidence", gate.decision_ref)
                        _replace_effect(current, "failed")
                        return GateEffectResult("failed", "target CAS refused without a write", gate.decision_ref)
                    _replace_effect(current, "unknown")
                    return GateEffectResult("unknown", f"actual target receipt unavailable{error}; inspect before retry", gate.decision_ref)
                executed = lifecycle.record_executed(**common, action=action.lifecycle_action, result=receipt,
                                                     reason=action.name, event_id=executed_id)
                if not executed.recorded or not _has_event(
                        _ledger_rows(store, meta, gate), executed_id, **execution, result=receipt):
                    return GateEffectResult("unknown", "actual write lacks its lifecycle receipt", gate.decision_ref)
                settled = lifecycle.record_settled(**common, outcome="ok", reason=receipt, event_id=settled_id)
                if not settled.recorded or not _has_event(
                        _ledger_rows(store, meta, gate), settled_id, kind="lifecycle", lifecycle="settled", outcome="ok", reason=receipt, actor=actor):
                    return GateEffectResult("unknown", "actual write lacks settlement evidence", gate.decision_ref)
                _replace_effect(current, "applied", legacy=legacy)
                return GateEffectResult("applied", "legacy closure" if legacy else "bounded action verified",
                                        gate.decision_ref, receipt=receipt)
    except Exception as exc:
        reason = str(exc) if isinstance(exc, GateBlocked) else f"gate observation or recording failed ({type(exc).__name__})"
        return GateEffectResult("unknown" if reserved else "blocked", reason)
