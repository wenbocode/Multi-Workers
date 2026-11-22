"""Consume one prepared gate answer against a controlled, bounded project operation.

The host binds the PM, ledger and object adapter. No adapter or permission comes
from the gate file. A durable in-progress reservation precedes the mutation.
On interruption only object inspection may complete a reservation.

T08-A: a host-bound ``LocalGateSource`` selects an explicit local-evidence
branch. It never constructs a DP identity/lifecycle; the original DP branch
keeps its production-ledger joins, policy/claim/budget checks and effect writer.
"""
from __future__ import annotations

import abc
import copy
import dataclasses
import hashlib
import json
import math
import ntpath
import os
import pathlib
import posixpath
import socket
import sys
import types
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from dataclasses import dataclass

import decision_lifecycle as lifecycle
import decision_local_evidence as local_evidence
import decision_policy as policy
import decision_validity as validity
import decision_wire as wire
import mw_common
from . import config, gates, state


# R9: pin native implementation descriptors at trusted import time. A generic
# type.__getattribute__(klass, "__mro__"|"__dict__") still invokes metaclass data
# descriptors; calling the pinned getset descriptors directly does not.
_NATIVE_MRO_DESCRIPTOR = type.__dict__["__mro__"]
_NATIVE_CLASS_DICT_DESCRIPTOR = type.__dict__["__dict__"]
_NATIVE_CLASS_NAME_DESCRIPTOR = type.__dict__["__name__"]
_NATIVE_CLASS_QUALNAME_DESCRIPTOR = type.__dict__["__qualname__"]
_METHOD_SELF_DESCRIPTOR = types.MethodType.__dict__["__self__"]
_METHOD_FUNC_DESCRIPTOR = types.MethodType.__dict__["__func__"]
_UNSET = object()


def _native_type_mro(klass: type) -> tuple:
    mro = _NATIVE_MRO_DESCRIPTOR.__get__(klass, type(klass))
    if type(mro) is not tuple:
        raise GateBlocked("final authority class layout is not an exact tuple")
    return mro


def _native_mro(obj: object) -> tuple:
    return _native_type_mro(type(obj))


def _native_class_namespace(klass: type) -> dict:
    proxy = _NATIVE_CLASS_DICT_DESCRIPTOR.__get__(klass, type(klass))
    if type(proxy) is not types.MappingProxyType:
        raise GateBlocked("final authority class namespace is not a builtin mappingproxy")
    keys = tuple(types.MappingProxyType.keys(proxy))
    if len(keys) > 4096:
        raise GateBlocked("final authority class namespace exceeds the bounded exact contract")
    out: dict = {}
    slotnames = _UNSET
    for key in keys:
        if type(key) is not str:
            raise GateBlocked("final authority class namespace key is not an exact str")
        value = types.MappingProxyType.__getitem__(proxy, key)
        # copyreg/pickle may cache benign __slotnames__ on a class after a
        # clone. It is not a user descriptor or part of the pinned layout.
        if str.__eq__(key, "__slotnames__"):
            slotnames = value
            continue
        dict.__setitem__(out, key, value)
    if slotnames is not _UNSET:
        if type(slotnames) is not tuple and type(slotnames) is not list:
            raise GateBlocked("controlled __slotnames__ cache is not native")
        for name in slotnames:
            if type(name) is not str:
                raise GateBlocked("controlled __slotnames__ cache is not exact")
    return out


def _native_instance_storage(obj: object, *, protected: tuple = ()) -> dict:
    """Read a plain object's exact instance dict through a pinned getset descriptor."""
    descriptor = None
    for klass in _native_mro(obj):
        namespace = _native_class_namespace(klass)
        if dict.__contains__(namespace, "__dict__"):
            candidate = dict.__getitem__(namespace, "__dict__")
            if type(candidate) is not types.GetSetDescriptorType:
                raise GateBlocked("user-defined __dict__ descriptor on a final authority value")
            descriptor = candidate
        for name in protected:
            if dict.__contains__(namespace, name):
                value = dict.__getitem__(namespace, name)
                if (type(value) is property or type(value) is types.GetSetDescriptorType
                        or type(value) is types.MemberDescriptorType):
                    raise GateBlocked("user-defined descriptor on a controlled final field:" + name)
    if descriptor is None:
        raise GateBlocked("final authority value has no controlled instance storage")
    raw = descriptor.__get__(obj, type(obj))
    if type(raw) is not dict:
        raise GateBlocked("final authority instance storage is not an exact builtin dict")
    keys = tuple(dict.keys(raw))
    if len(keys) > 4096:
        raise GateBlocked("final authority instance storage exceeds the bounded exact contract")
    for key in keys:
        if type(key) is not str:
            raise GateBlocked("final authority instance storage key is not an exact str")
    return raw


def _assert_native_type_layout(klass: type, pinned_mro: tuple,
                               pinned_keys: tuple, pinned_values: dict) -> None:
    """Compare current native class layout against trusted import-time pins."""
    mro = _native_type_mro(klass)
    if len(mro) != len(pinned_mro):
        raise GateBlocked("final authority class layout changed")
    for current, pinned in zip(mro, pinned_mro):
        if current is not pinned:
            raise GateBlocked("final authority class layout changed")
    namespace = _native_class_namespace(klass)
    keys = tuple(dict.keys(namespace))
    if len(keys) != len(pinned_keys):
        raise GateBlocked("final authority class namespace changed")
    for key in keys:
        if type(key) is not str or not any(str.__eq__(key, pinned) for pinned in pinned_keys):
            raise GateBlocked("final authority class namespace changed")
    for name, expected in pinned_values.items():
        if not dict.__contains__(namespace, name):
            raise GateBlocked("final authority class namespace changed")
        if dict.__getitem__(namespace, name) is not expected:
            raise GateBlocked("final authority class namespace changed")


def _exact_type_name(kind: type) -> str:
    name = _NATIVE_CLASS_NAME_DESCRIPTOR.__get__(kind, type(kind))
    return name if type(name) is str else "unknown"


def _exact_type_qualname(kind: type) -> str:
    name = _NATIVE_CLASS_QUALNAME_DESCRIPTOR.__get__(kind, type(kind))
    return name if type(name) is str else "unknown"


def _json_exact_tree(tree: object) -> str:
    """Serialize an already normalized exact tree; no user object is inspected."""
    try:
        return json.dumps(tree, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        raise GateBlocked("local gate snapshot is not an immutable projection") from exc


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


# ── T08-A host-bound local source (production wiring of the adapter is T08-B) ──

@dataclass(frozen=True)
class LocalGateExpectations:
    """Host-observed facts for ONE local gate decision.

    Supplied by trusted product code, never decoded from gate text. The gate
    file is only cross-checked against these facts; it never selects a source.
    """
    gate_decision_ref: str
    matter_ref: str
    substantive_version: str
    pm_note: str
    model_basis: str
    material_digest: str
    basis_digest: str
    selected_action: str
    selected_basis_id: str
    budget_ref: str
    target_digest: str
    action_ref: str
    result_ref: str
    verifier_ref: str
    effect_state: str
    observed_effect: str
    local_ref: str
    key: str
    task_key: str | None
    record_source: str
    claim_id: str
    parent_decision_ref: object | None = None


@dataclass(frozen=True)
class LocalGateDisposition:
    """Host-verified 'already disposed' fact; a read-only callback result only.

    No second business JSON is written. ``confirmed`` must be exactly True and
    ``target_receipt`` must be the actual object receipt (or empty before the
    bounded object operation)."""
    local_ref: str
    decision_ref: str
    effect_state: str
    action_ref: str
    result_ref: str
    verifier_receipt_ref: str
    target_receipt: str
    selection_sha256: str
    execution_sha256: str
    confirmed: bool


# ── T08-A-R4: typed COMPLETE final-state sample at the trusted producer boundary ──

@dataclass(frozen=True)
class TerminalRequest:
    """Bounded inputs a trusted producer may use, all from real local reads.

    The gate, strict selection/execution records, physical digest and receipt come
    from the consumer's real reader/receipt, never from gate text or model output.
    """
    gate: gates.Gate
    source: "LocalGateSource"
    claim_id: str
    phase: str
    facts: GateFacts
    selection: local_evidence.LocalSelectionRecord
    execution: local_evidence.LocalExecutionRecord
    receipt: str | None
    object_digest: str
    # T08-A-R5: the consumer-pinned owner carrier. Exposed to the producer so
    # its replacement/staleness is verifiable; the consumer's authority stays
    # in its own pinned local reference, never in a delegated host sampler.
    owner: "TerminalOwnerState" | None = None


@dataclass(frozen=True)
class TerminalSample:
    """One complete, deep-frozen final authority state, sampled AFTER the last
    mutation-capable callback. It is a value, not a bag of retained host refs.

    ``state_fingerprint`` is derived from the sample's own fields and must also
    equal the host's independently re-derived live-state fingerprint. A stale,
    hand-assembled or self-sealed sample cannot satisfy both checks.
    """
    source_key: str
    record_source: str
    task_key: str | None
    local_ref: str
    gate_decision_ref: str
    claim_id: str
    phase: str
    context: local_evidence.TrustedContext
    expectations: LocalGateExpectations
    disposition: LocalGateDisposition | None
    action_evidence: local_evidence.ActionResultEvidence
    facts_state: str
    action_identity: tuple[str, str, bool, str]
    selection: local_evidence.LocalSelectionRecord
    execution: local_evidence.LocalExecutionRecord
    selection_sha256: str
    execution_sha256: str
    object_digest: str
    receipt: str
    gate_identity: tuple[str, str, str, str, str]
    execution_state: str
    selection_state: str
    disposition_state: str
    state_fingerprint: str


class TerminalOwnerState:
    """T08-A-R5: consumer-created, pinned owner of the authoritative live state.

    The consumer creates ONE carrier per terminal boundary BEFORE the first host
    callback and keeps its own ``owner_ref`` / ``pinned_id`` locals as authority.
    ``live`` is a DIRECT reference to the source-owned live state owner object,
    not a captured value and not a host method: every permitted host callback
    (including the virtual fingerprint callback and any late in-place mutation
    or attribute replacement inside it) completes first, and only then does the
    consumer read ``live``'s plain attributes directly. The host can see this
    carrier through ``TerminalRequest.owner`` but can never replace the
    consumer's pinned identity without detection.
    """
    __slots__ = ("live", "pinned_id")

    def __init__(self, live: object, pinned_id: int):
        self.live = live
        self.pinned_id = pinned_id


def _terminal_live_fingerprint(*, context, expectations, action_evidence,
                               facts_state, execution_state, selection_state,
                               disposition_state) -> str:
    """Canonical projection of the host-owned live state domain.

    Used twice: by the producer when it captures, and by the consumer (from the
    sample's own values plus an independent live re-derivation). Equality is a
    real coherence/freshness check, not a caller-supplied version token.
    """
    return _frozen({
        "context": (_context_state(context)
                    if type(context) is local_evidence.TrustedContext
                    else _frozen({"invalid_context": _exact_type_name(type(context))})),
        "expectations": _frozen(expectations),
        "action_evidence": _frozen(action_evidence),
        "facts": facts_state,
        "execution": execution_state,
        "selection": selection_state,
        "disposition": disposition_state,
    })


class LocalGateHost(local_evidence.HostEvidenceAdapter, abc.ABC):
    """Trusted host boundary for local gate evidence.

    Extends the frozen T03 strict-reader adapter with gate-specific expectations
    and an independent disposition callback. A string/dict/bool/model callback
    is not an instance of this ABC and is rejected. The production adapter that
    reads live coordination rows, real tool/dispatch receipts and the current
    object is wired in T08-B; a missing adapter fails closed here.
    """

    @abc.abstractmethod
    def gate_expectations(self, gate: gates.Gate) -> LocalGateExpectations | None:
        """Return the CURRENT host expectations for this prepared gate, or None."""

    @abc.abstractmethod
    def verify_disposition(
        self, gate: gates.Gate,
        selection: local_evidence.LocalSelectionRecord,
        execution: local_evidence.LocalExecutionRecord,
        receipt: str | None,
    ) -> LocalGateDisposition | None:
        """Re-verify the already-disposed execution fact; never a write."""

    @abc.abstractmethod
    def terminal_sample(self, request: TerminalRequest) -> TerminalSample | None:
        """Capture the COMPLETE current authority state from actual live host state.

        Must run after all completed mutation-capable callbacks, read the live
        state domain in one synchronous pass (no nested getters/callbacks), and
        deep-freeze the result. Returning a retained old getter result or a
        self-declared sealed token is not a sample. None fails closed.
        """

    @abc.abstractmethod
    def terminal_state_fingerprint(self) -> str:
        """Read-only re-derivation of the host's CURRENT live state domain.

        Owned by the host, never self-reported by a sample. The consumer uses it
        immediately after capture to prove the sample is not stale/incoherent.
        """

    def authority_owner(self) -> object:
        """Return the producer's CURRENT authoritative live-state OWNER object
        BY REFERENCE (T08-A-R6, real producer/consumer owner association).

        Every producer read (context / expectations / action-evidence / facts /
        selection / execution / disposition / fingerprint) is bound to this exact
        object; the consumer calls this ONCE, AFTER the LAST mutation-capable
        callback, and verifies ``is``-identity with its pinned
        ``source.owner_state``. A late rebind (e.g. ``self.f = copy(...)`` inside
        the final fingerprint callback) is therefore FINALLY detected and
        rejected, not hidden by an old pinned reference, a self-comparison, a
        token, or a renamed getter. The consumer reads VALUES non-delegating from
        the identity-bound owner; this method is used for IDENTITY binding ONLY,
        never as a value source. A concrete default returns None so a host that
        does not declare its owner fails closed; the real L1 producer (S ``Host``)
        overrides it with ``return self.f``, i.e. producer and consumer use the
        SAME domain, not a test-only fake carrier.
        """
        return None


@dataclass(frozen=True)
class LocalGateSource:
    """Explicit, host-bound discriminated local source for consume_gate.

    ``decision_ref`` is the frozen T03 discriminated local ref object, NOT a
    string prefix and NOT a model-supplied gate field. ``gate_decision_ref`` is
    the exact host-issued gate identifier ``local(<local_ref>)``; the gate text
    must equal it but can never select the source branch by itself.
    """
    decision_ref: local_evidence.LocalDecisionRef
    agenticdoc_root: pathlib.Path
    key: str
    record_source: str
    task_key: str | None
    gate_decision_ref: str
    host: LocalGateHost
    # T08-A-R5: the consumer/source-owned authoritative live state owner. A
    # plain object reference (never a host method/getter) whose plain attributes
    # are read directly by the consumer AFTER every completed host callback.
    owner_state: object | None = None
    # T08-A-R7: consumer-created controlled producer-owner storage. This, not a
    # host getter or a retained plain object reference, is the authority cell.
    authority_cell: "ControlledAuthorityCell | None" = None


@dataclass(frozen=True)
class _LocalVerified:
    """One immutable strict-semantic + physical-snapshot verification package."""
    selection: local_evidence.LocalSelectionRecord
    execution: local_evidence.LocalExecutionRecord
    expectations: LocalGateExpectations
    context: local_evidence.TrustedContext
    disposition: LocalGateDisposition
    selection_sha256: str
    execution_sha256: str
    physical_shape: tuple[object, ...]
    strict_shapes: tuple[tuple[object, ...], ...]
    selection_bytes: bytes
    execution_bytes: bytes
    object_bytes: bytes
    object_digest: str
    expectations_state: str
    context_state: str
    disposition_state: str
    facts_state: str
    authority_state: str


class GateBlocked(ValueError):
    pass


def _frozen(value: object) -> str:
    """Canonical projection of an EXACT, non-delegating value tree only.

    R9: no isinstance/getattr/dataclasses.fields/str(user object) fallback.
    All consumers must pass exact builtins or pinned exact dataclasses.
    """
    return _json_exact_tree(_normalize_exact(value))


def _facts_state(facts: GateFacts) -> str:
    if type(facts) is not GateFacts:
        raise GateBlocked("final facts are not the exact controlled type")
    storage = _native_instance_storage(facts)
    names = dict.__getitem__(_EXACT_FIELD_NAMES, str(id(GateFacts)))
    for name in names:
        if not dict.__contains__(storage, name):
            raise GateBlocked("final facts lack a complete exact field set")
    action = dict.__getitem__(storage, "action")
    if action is None:
        action_projection = None
    else:
        if type(action) is not BoundAction:
            raise GateBlocked("final bounded action is not the exact controlled type")
        action_storage = _native_instance_storage(action)
        path = dict.__getitem__(action_storage, "object_path")
        name = dict.__getitem__(action_storage, "name")
        legacy = dict.__getitem__(action_storage, "legacy_closure")
        lifecycle = dict.__getitem__(action_storage, "lifecycle_action")
        if type(name) is not str or type(legacy) is not bool or type(lifecycle) is not str:
            raise GateBlocked("final bounded action metadata is not exact")
        action_projection = {
            "name": name, "object_path": _exact_path_string(path),
            "legacy_closure": legacy, "lifecycle_action": lifecycle,
        }
    return _frozen({
        "matter": dict.__getitem__(storage, "matter"),
        "pm_note": dict.__getitem__(storage, "pm_note"),
        "scope": dict.__getitem__(storage, "scope"),
        "authority_source": dict.__getitem__(storage, "authority_source"),
        "trusted_writers": dict.__getitem__(storage, "trusted_writers"),
        "hard_checks": dict.__getitem__(storage, "hard_checks"),
        "usage_by_source": dict.__getitem__(storage, "usage_by_source"),
        "spend_by_unit": dict.__getitem__(storage, "spend_by_unit"),
        "action": action_projection,
    })


def _read_shape(read: local_evidence.ReadResult) -> tuple[object, ...]:
    return (read.ok, read.verification, read.host_source_verified,
            read.selection, read.execution,
            read.selection_sha256, read.execution_sha256,
            tuple(read.checks), tuple(read.failure_codes), tuple(read.issues),
            read.selection_path, read.execution_path,
            tuple(read.recovery_clues), read.snapshot)


def _physical_bytes(read: local_evidence.ReadResult) -> tuple[bytes, bytes]:
    """Independent exact byte readback of the two physical local records."""
    if not (read.selection_path and read.execution_path
            and read.selection_sha256 and read.execution_sha256):
        raise GateBlocked("terminal physical local evidence paths or hashes are incomplete")
    try:
        selection_bytes = pathlib.Path(read.selection_path).read_bytes()
        execution_bytes = pathlib.Path(read.execution_path).read_bytes()
    except OSError as exc:
        raise GateBlocked("terminal physical local evidence could not be read back") from exc
    if (hashlib.sha256(selection_bytes).hexdigest() != read.selection_sha256
            or hashlib.sha256(execution_bytes).hexdigest() != read.execution_sha256):
        raise GateBlocked("terminal physical local evidence bytes changed")
    return selection_bytes, execution_bytes


class _StrictObserver(local_evidence.HostEvidenceAdapter):
    """Delegate every real host callback; record bounded physical reads around it.

    strict_verify remains the only verifier. These read-only observations bind
    each host callback window to the same physical snapshot used by the gate.
    """
    def __init__(self, root: pathlib.Path, source: LocalGateSource):
        self.host = source.host
        self.root = root
        self.key = source.key
        self.record_source = source.record_source
        self.local_ref = source.decision_ref.local_ref
        self.task_key = source.task_key
        self.reads: list[local_evidence.ReadResult] = []
        # T08-A-R2: immutable projections captured INSIDE the real callback
        # window. A later in-place mutation cannot rewrite a saved string.
        self.context_states: list[str] = []
        self.evidence_states: list[str] = []

    def _capture(self) -> None:
        self.reads.append(local_evidence.read_local_evidence(
            self.root, self.key, self.record_source, self.local_ref,
            task_key=self.task_key))

    def current_context(self):
        self._capture()
        context = self.host.current_context()
        self._capture()
        if type(context) is local_evidence.TrustedContext:
            self.context_states.append(_context_state(context))
        else:
            self.context_states.append(_frozen({"invalid_context": _exact_type_name(type(context))}))
        return context

    def verify_execution(self, record, target_digest):
        self._capture()
        evidence = self.host.verify_execution(record, target_digest)
        self._capture()
        self.evidence_states.append(_frozen(evidence))
        return evidence


def _strict_pair(root: pathlib.Path, source: LocalGateSource,
                 callback_states: dict | None = None):
    observer = _StrictObserver(root, source)
    selection_result = local_evidence.strict_verify(
        root, source.key, source.record_source, source.decision_ref.local_ref,
        which="selection", task_key=source.task_key, adapter=observer)
    if not (selection_result.ok and selection_result.host_source_verified is True
            and selection_result.verification == "strict-verified"
            and isinstance(selection_result.value, local_evidence.LocalSelectionRecord)
            and not selection_result.failure_codes):
        raise GateBlocked("local selection is not strictly verified: "
                          + ",".join(selection_result.failure_codes))
    execution_result = local_evidence.strict_verify(
        root, source.key, source.record_source, source.decision_ref.local_ref,
        which="execution", task_key=source.task_key, adapter=observer)
    if not (execution_result.ok and execution_result.host_source_verified is True
            and execution_result.verification == "strict-verified"
            and isinstance(execution_result.value, local_evidence.LocalExecutionRecord)
            and not execution_result.failure_codes):
        raise GateBlocked("local execution is not strictly verified: "
                          + ",".join(execution_result.failure_codes))
    if callback_states is not None:
        callback_states["contexts"] = tuple(observer.context_states)
        callback_states["evidence"] = tuple(observer.evidence_states)
    return (selection_result.value, execution_result.value,
            tuple(_read_shape(read) for read in observer.reads))


def _validate_expectations(gate: gates.Gate, source: LocalGateSource,
                           claim_id: str, expectations: object) -> str:
    if not isinstance(expectations, LocalGateExpectations):
        raise GateBlocked("missing trusted local gate expectations")
    for name in ("gate_decision_ref", "matter_ref", "substantive_version", "pm_note", "model_basis",
                 "material_digest", "basis_digest", "selected_action", "selected_basis_id", "budget_ref",
                 "target_digest", "action_ref", "result_ref", "verifier_ref", "effect_state",
                 "observed_effect", "local_ref", "key", "record_source", "claim_id"):
        if not _nonblank(getattr(expectations, name)):
            raise GateBlocked("incomplete local gate expectations: " + name)
    if (expectations.gate_decision_ref != source.gate_decision_ref
            or expectations.local_ref != source.decision_ref.local_ref
            or expectations.key != source.key
            or expectations.task_key != source.task_key
            or expectations.record_source != source.record_source
            or expectations.claim_id != claim_id):
        raise GateBlocked("host expectations do not match the bound local source")
    if gate.pm_note != expectations.pm_note or gate.model_basis != expectations.model_basis:
        raise GateBlocked("gate note or basis changed against the host expectation")
    if (gate.matter_ref != expectations.matter_ref
            or gate.substantive_version != expectations.substantive_version):
        raise GateBlocked("gate matter or substantive version changed against the host expectation")
    return _frozen(expectations)


def _context_state(context: local_evidence.TrustedContext) -> str:
    """Freeze identity/stop/budget facts; observed_at is a volatile sample time."""
    if type(context) is not local_evidence.TrustedContext:
        raise GateBlocked("final live context is not the exact controlled value type")
    tree = _normalize_exact(context)
    if type(tree) is not dict or not dict.__contains__(tree, "binding"):
        raise GateBlocked("final live context projection is malformed")
    binding = dict.__getitem__(tree, "binding")
    if type(binding) is not dict:
        raise GateBlocked("final live context binding projection is malformed")
    if not dict.__contains__(binding, "@type") or not str.__eq__(
            dict.__getitem__(binding, "@type"), str(id(local_evidence.TrustedBinding))):
        raise GateBlocked("final live context binding projection is malformed")
    if dict.__contains__(binding, "observed_at"):
        dict.pop(binding, "observed_at")
    return _json_exact_tree(tree)


def _validate_context(context: object, expectations: LocalGateExpectations,
                      source: LocalGateSource, claim_id: str) -> str:
    if not isinstance(context, local_evidence.TrustedContext):
        raise GateBlocked("missing trusted current context")
    binding = context.binding
    pm_source = source.record_source == "pm"
    if (not _nonblank(binding.claim_id) or binding.key != source.key
            or (pm_source and (binding.role != "pm" or binding.claim_id != claim_id))
            or (not pm_source and (binding.role == "pm" or not _nonblank(source.task_key)))
            or binding.task_key != source.task_key or not _nonblank(binding.owner)
            or not _nonblank(binding.run_id)):
        raise GateBlocked("current host binding is not the live source claim")
    if (context.matter_ref != expectations.matter_ref or context.matter_version != expectations.substantive_version
            or context.material_digest != expectations.material_digest
            or context.basis_digest != expectations.basis_digest
            or context.target_digest != expectations.target_digest):
        raise GateBlocked("current host matter, material, basis or target drifted")
    if _stable(context.parent_decision_ref) != _stable(expectations.parent_decision_ref):
        raise GateBlocked("current parent decision ref drifted")
    budget = local_evidence.validate_matter_budget(context.budget)
    if not budget.ok or budget.value is None:
        raise GateBlocked("missing or invalid finite host budget")
    if budget.value.budget_ref != expectations.budget_ref or budget.value.matter_ref != context.matter_ref:
        raise GateBlocked("host budget is not bound to this matter")
    if context.stop_scope in ("user-global", "pm-or-key", "matter"):
        raise GateBlocked("host scope stop blocks this gate")
    return _context_state(context)


def _assert_final_budget_deadline(context: object) -> None:
    """After the LAST host callback, apply the frozen finite-budget clock test.

    R10S: this is the ONLY helper permitted after the final native association
    suffix. Its input MUST be an already-detached, fully exact materialized
    TrustedContext whose values were just matched against the final live domain.
    The budget is read through the pinned native instance-dict getset (NOT a
    getattr/owner getter/Host callback/record parser/Path constructor), then the
    unchanged frozen reader's ``now > parsed`` deadline rule is called directly.
    A missing, invalid or unparseable finite budget fails closed. The real
    current-clock predicate and its timezone/naive-UTC/exact-boundary semantics
    are preserved; the frozen reader is not modified.
    """
    try:
        if type(context) is not local_evidence.TrustedContext:
            raise GateBlocked("final finite host budget context is not the exact controlled value type")
        raw = _native_instance_storage(context)
        if not dict.__contains__(raw, "budget"):
            raise GateBlocked("final finite host budget is missing")
        budget = dict.__getitem__(raw, "budget")
        parsed = local_evidence.validate_matter_budget(budget)
    except GateBlocked:
        raise
    except Exception as exc:
        raise GateBlocked("final finite host budget is unreadable: " + type(exc).__name__) from exc
    if not parsed.ok or parsed.value is None:
        raise GateBlocked("missing or invalid finite host budget at the final deadline check")
    try:
        expired = local_evidence._deadline_passed(parsed.value.deadline)
    except Exception as exc:
        raise GateBlocked("final host budget deadline is unusable: " + type(exc).__name__) from exc
    if expired:
        raise GateBlocked("host budget deadline passed after the last host callback")


def _validate_disposition(gate: gates.Gate, source: LocalGateSource,
                          expectations: LocalGateExpectations,
                          selection: local_evidence.LocalSelectionRecord,
                          execution: local_evidence.LocalExecutionRecord,
                          read: local_evidence.ReadResult,
                          receipt: str | None, disposition: object) -> str:
    if not isinstance(disposition, LocalGateDisposition):
        raise GateBlocked("missing independently verified local disposition")
    if (disposition.confirmed is not True or disposition.effect_state != "known"
            or disposition.effect_state != expectations.effect_state
            or disposition.effect_state != execution.effect_state
            or disposition.local_ref != source.decision_ref.local_ref
            or disposition.decision_ref != gate.decision_ref
            or disposition.action_ref != execution.action_ref
            or disposition.result_ref != execution.result_ref
            or disposition.verifier_receipt_ref != execution.verified_by
            or disposition.selection_sha256 != read.selection_sha256
            or disposition.execution_sha256 != read.execution_sha256
            or disposition.target_receipt != (receipt or "")
            or selection.local_ref != source.decision_ref.local_ref):
        raise GateBlocked("local disposition does not match the executed fact and target receipt")
    return _frozen(disposition)


def _assert_terminal_physical(root: pathlib.Path, source: LocalGateSource,
                              verified: _LocalVerified, strict_selection,
                              strict_execution, strict_shapes) -> local_evidence.ReadResult:
    read = local_evidence.read_local_evidence(
        root, source.key, source.record_source, source.decision_ref.local_ref,
        task_key=source.task_key)
    if not (read.ok and read.selection is not None and read.execution is not None
            and read.selection_sha256 and read.execution_sha256 and read.snapshot is not None
            and not read.recovery_clues and not read.failure_codes):
        raise GateBlocked("terminal physical local selection and execution evidence is incomplete")
    shape = _read_shape(read)
    if shape != verified.physical_shape:
        raise GateBlocked("terminal local physical snapshot changed")
    if any(observed != shape for observed in (*verified.strict_shapes, *strict_shapes)):
        raise GateBlocked("strict host callbacks saw a different physical snapshot")
    if (read.selection != strict_selection or read.execution != strict_execution
            or strict_selection != verified.selection or strict_execution != verified.execution):
        raise GateBlocked("strict semantic values and terminal physical records diverged")
    selection_bytes, execution_bytes = _physical_bytes(read)
    if selection_bytes != verified.selection_bytes or execution_bytes != verified.execution_bytes:
        raise GateBlocked("terminal physical record bytes diverged")
    return read


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


def _check_facts(project: pathlib.Path, key: str, claim: str, gate: gates.Gate,
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
    claims = [r for r in state.read_index(project) if r["key"] == key]
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


def _authority_projection(project: pathlib.Path, key: str, claim_id: str,
                          gate: gates.Gate, facts: GateFacts) -> str:
    """Finite immutable projection of every independent gate authorization input.

    Re-runs the complete live PM index/claim/config/policy/machine-check/
    current-authority/usage/spend verdict, then freezes its inputs as a string.
    No host callback, mutable object, cache or function name is trusted here.
    """
    granted = _check_facts(project, key, claim_id, gate, facts)
    claims = [dict(row) for row in state.read_index(project) if row.get("key") == key]
    loaded = policy.load_policy(project)
    spend_checks: list[tuple[object, ...]] = []
    if loaded.policy is not None:
        for limit in loaded.policy.hard_limits:
            delta = facts.spend_by_unit.get(limit.unit)
            used = facts.usage_by_source.get(limit.usage_source)
            ok = (type(delta) is int and type(used) is int and delta >= 0 and used >= 0
                  and policy.check_spend(loaded, unit=limit.unit, amount=delta,
                                         usage={limit.unit: used}).allowed)
            spend_checks.append((limit.unit, limit.usage_source, limit.limit, delta, used, ok))
    return _frozen({
        "index_rows": claims,
        "claim_state": state.claim_state(claim_id),
        "claim_id": claim_id,
        "worker_task_env": os.environ.get("PI_WORKER_TASK"),
        "config": config.load_config(project),
        "policy": loaded,
        "verdict": granted,
        "facts": _facts_state(facts),
        "spend_checks": spend_checks,
        "gate": (gate.business, gate.answered_by, gate.matter_ref,
                 gate.substantive_version, gate.pm_note, gate.model_basis),
    })


# ── T08-A-R7: controlled producer-owner storage + recursive exact final domain ──
#
# The R6 mechanism was not a guarantee: authority_owner() was itself the last
# overridable callback (F1); object.__getattribute__ still invoked data
# descriptors (F2); exact top-level dicts/dataclasses retained str/dict
# subclasses that delegated during the final typed comparison (F3). R7 replaces
# the association with a consumer-created controlled cell and replaces the value
# domain with a recursively verified exact-value contract. This is a bounded,
# single-thread, completed-callback guarantee, explicitly NOT OS atomicity.

_CONTROLLED_DOMAIN_NAMES = (
    "ctx", "expectations", "evidence", "facts", "selection", "execution",
    "disposition_ok", "recovery_disposition_ok", "agenticdoc_root",
)

# Exactly these dataclass types may appear inside the final domain. Their fields
# are read from controlled instance dicts, never through getattr/descriptors.
_EXACT_DATACLASSES = (
    local_evidence.TrustedContext, local_evidence.TrustedBinding,
    local_evidence.ActionResultEvidence, local_evidence.MatterBudget,
    local_evidence.LocalSelectionRecord, local_evidence.LocalExecutionRecord,
    local_evidence.LocalDecisionRef, local_evidence.DpDecisionRef,
    local_evidence.HostBinding, local_evidence.CheckItem,
    local_evidence.ContractIssue, local_evidence.ReadResult,
    LocalGateExpectations, LocalGateDisposition, GateFacts, BoundAction,
    ObjectReceipt, GateEffectResult, TerminalSample, _LocalVerified,
    validity.Matter, validity.DependencyState, policy.AuthorityRecord,
    gates.Gate,
)
def _module_exact_classes(module: object) -> tuple:
    out: list = []
    for candidate in vars(module).values():
        if not isinstance(candidate, type) or not dataclasses.is_dataclass(candidate):
            continue
        if not any(candidate is known for known in out):
            out.append(candidate)
    return tuple(out)


_EXACT_DATACLASSES = _EXACT_DATACLASSES + _module_exact_classes(local_evidence) \
    + _module_exact_classes(policy) + _module_exact_classes(validity) \
    + _module_exact_classes(lifecycle) \
    + _module_exact_classes(sys.modules[__name__])
_EXACT_PATH_CLASS = type(pathlib.Path())
_EXACT_PATHS = (_EXACT_PATH_CLASS,)
_EXACT_PATH_MRO = _native_type_mro(_EXACT_PATH_CLASS)
_PATH_SLOT_NAMES = tuple(pathlib.PurePath.__slots__)
_PATH_SLOT_DESCRIPTORS = {}
for _slot in _PATH_SLOT_NAMES:
    _descriptor = pathlib.PurePath.__dict__.get(_slot)
    if type(_descriptor) is not types.MemberDescriptorType:
        raise RuntimeError("unsupported pathlib slot layout: " + _slot)
    dict.__setitem__(_PATH_SLOT_DESCRIPTORS, _slot, _descriptor)
_PATH_FLAVOUR = pathlib.PureWindowsPath.__dict__.get("_flavour") \
    if _EXACT_PATH_CLASS is getattr(pathlib, "WindowsPath", None) \
    else pathlib.PurePosixPath.__dict__.get("_flavour")
_PATH_SEP = dict.__getitem__(_PATH_FLAVOUR.__dict__, "sep")
_PATH_ALTSEP = dict.__getitem__(_PATH_FLAVOUR.__dict__, "altsep")
if type(_PATH_SEP) is not str or (_PATH_ALTSEP is not None and type(_PATH_ALTSEP) is not str):
    raise RuntimeError("unsupported pathlib flavour layout")
_PATH_DRIVE_PROPERTY = pathlib.PurePath.__dict__["drive"]
_PATH_ROOT_PROPERTY = pathlib.PurePath.__dict__["root"]
_PATH_TAIL_PROPERTY = pathlib.PurePath.__dict__["_tail"]
_PATH_STR_NORMCASE_PROPERTY = pathlib.PurePath.__dict__["_str_normcase"]
_PATH_NAMESPACE_PINS = {}
for _base in _EXACT_PATH_MRO:
    _pins = {}
    _namespace = type.__dict__["__dict__"].__get__(_base, type(_base))
    for _name in ("_flavour", "__str__", "as_posix", "_parse_path", "_load_parts",
                  "_format_parsed_parts", *_PATH_SLOT_NAMES):
        if dict.__contains__(dict(_namespace), _name):
            dict.__setitem__(_pins, _name, types.MappingProxyType.__getitem__(_namespace, _name))
    dict.__setitem__(_PATH_NAMESPACE_PINS, str(id(_base)), _pins)
_EXACT_CALLABLES = (types.MethodType, types.FunctionType,
                    types.BuiltinFunctionType, types.BuiltinMethodType)
_EXACT_OPAQUE_TYPE = type(validity.UNKNOWN_SUBSTANTIVE)
_EXACT_OPAQUE_TOKENS = {str(id(_EXACT_OPAQUE_TYPE)): validity.UNKNOWN_SUBSTANTIVE}
# Per-process exact identity tokens. All keys/values are exact builtins; no
# user type name, __eq__ or metaclass protocol is consulted by lookup.
_EXACT_TYPE_TOKENS = {}
_EXACT_FIELD_NAMES = {}
_EXACT_SCHEMA_PINS = {}
for _klass in _EXACT_DATACLASSES:
    _token = str(id(_klass))
    dict.__setitem__(_EXACT_TYPE_TOKENS, _token, _klass)
    _fields = tuple(field.name for field in dataclasses.fields(_klass))
    for _field in _fields:
        if type(_field) is not str:
            raise RuntimeError("unsupported dataclass field name")
    dict.__setitem__(_EXACT_FIELD_NAMES, _token, _fields)
    _namespace = _native_class_namespace(_klass)
    _keys = tuple(dict.keys(_namespace))
    _pinned_values = {}
    for _name in ("__dict__", "__dataclass_fields__"):
        if dict.__contains__(_namespace, _name):
            dict.__setitem__(_pinned_values, _name, dict.__getitem__(_namespace, _name))
    dict.__setitem__(_EXACT_SCHEMA_PINS, _token, {
        "class": _klass, "mro": _native_type_mro(_klass), "keys": _keys,
        "fields": _fields, "values": _pinned_values,
    })


def _assert_pinned_dataclass_schema(klass: type) -> tuple:
    token = str(id(klass))
    if not dict.__contains__(_EXACT_SCHEMA_PINS, token):
        raise GateBlocked("unknown exact authority dataclass token")
    pin = dict.__getitem__(_EXACT_SCHEMA_PINS, token)
    _assert_native_type_layout(klass, pin["mro"], pin["keys"], pin["values"])
    for base in _native_type_mro(klass):
        namespace = _native_class_namespace(base)
        for field in pin["fields"]:
            if dict.__contains__(namespace, field):
                value = dict.__getitem__(namespace, field)
                if (type(value) is property or type(value) is types.GetSetDescriptorType
                        or type(value) is types.MemberDescriptorType):
                    raise GateBlocked("data descriptor on an exact authority field")
    return pin["fields"]


def _assert_pinned_exact_schemas() -> None:
    for token in tuple(dict.keys(_EXACT_SCHEMA_PINS)):
        klass = dict.__getitem__(_EXACT_TYPE_TOKENS, token)
        _assert_pinned_dataclass_schema(klass)


def _new_exact_dataclass(klass: type, values: dict) -> object:
    fields = _assert_pinned_dataclass_schema(klass)
    obj = object.__new__(klass)
    raw = _native_instance_storage(obj)
    for field in fields:
        if not dict.__contains__(values, field):
            raise GateBlocked("exact authority dataclass field is absent")
        dict.__setitem__(raw, field, dict.__getitem__(values, field))
    return obj


def _exact_str_sequence(value: object, *, allow_tuple: bool = True) -> tuple:
    kind = type(value)
    if kind is not list and (not allow_tuple or kind is not tuple):
        raise GateBlocked("final authority string sequence is not an exact builtin")
    if len(value) > 1024:
        raise GateBlocked("final authority string sequence exceeds the bounded exact contract")
    parts = tuple(value)
    for part in parts:
        if type(part) is not str:
            raise GateBlocked("final authority string sequence leaf is not an exact str")
    return parts


def _exact_str_sequence_equal(left: object, right: object) -> bool:
    try:
        a, b = _exact_str_sequence(left), _exact_str_sequence(right)
    except GateBlocked:
        return False
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if not str.__eq__(x, y):
            return False
    return True


def _path_slot(value: object, name: str) -> object:
    descriptor = dict.__getitem__(_PATH_SLOT_DESCRIPTORS, name)
    try:
        return descriptor.__get__(value, _EXACT_PATH_CLASS)
    except AttributeError:
        return _UNSET


def _assert_path_layout(value: object) -> None:
    if type(value) is not _EXACT_PATH_CLASS:
        raise GateBlocked("final authority Path is not the exact native concrete type")
    mro = _native_type_mro(_EXACT_PATH_CLASS)
    if len(mro) != len(_EXACT_PATH_MRO):
        raise GateBlocked("final authority Path class layout changed")
    for current, pinned in zip(mro, _EXACT_PATH_MRO):
        if current is not pinned:
            raise GateBlocked("final authority Path class layout changed")
    if type(_PATH_FLAVOUR) is not types.ModuleType:
        raise GateBlocked("final authority Path flavour is not the pinned native module")
    if (not str.__eq__(dict.__getitem__(_PATH_FLAVOUR.__dict__, "sep"), _PATH_SEP)
            or dict.__getitem__(_PATH_FLAVOUR.__dict__, "altsep") is not _PATH_ALTSEP):
        raise GateBlocked("final authority Path flavour changed")
    for base in mro:
        namespace = _native_class_namespace(base)
        pins = dict.__getitem__(_PATH_NAMESPACE_PINS, str(id(base)))
        for name, expected in pins.items():
            if not dict.__contains__(namespace, name):
                raise GateBlocked("final authority Path class layout changed")
            if dict.__getitem__(namespace, name) is not expected:
                raise GateBlocked("final authority Path class layout changed")


def _exact_path_state(value: object) -> tuple[str, object]:
    """Close exact native Path internals BEFORE any parse/str/as_posix use."""
    _assert_path_layout(value)
    raw_paths = _path_slot(value, "_raw_paths")
    if raw_paths is _UNSET or type(raw_paths) is not list:
        raise GateBlocked("final authority Path raw paths are not an exact list")
    parts = _exact_str_sequence(raw_paths, allow_tuple=False)
    for name in ("_drv", "_root", "_str", "_str_normcase_cached"):
        slot = _path_slot(value, name)
        if slot is not _UNSET and type(slot) is not str:
            raise GateBlocked("final authority Path cache leaf is not an exact str")
    for name in ("_tail_cached", "_parts_normcase_cached", "_lines_cached"):
        slot = _path_slot(value, name)
        if slot is not _UNSET:
            _exact_str_sequence(slot)
    slot = _path_slot(value, "_hash")
    if slot is not _UNSET and type(slot) is not int:
        raise GateBlocked("final authority Path hash cache is not an exact int")
    fresh = _EXACT_PATH_CLASS(*parts)
    if type(fresh) is not _EXACT_PATH_CLASS:
        raise GateBlocked("final authority Path reconstruction changed type")
    fresh_str = pathlib.PurePath.__str__(fresh)
    if type(fresh_str) is not str:
        raise GateBlocked("final authority Path string is not an exact str")
    cached_str = _path_slot(value, "_str")
    if cached_str is not _UNSET and not str.__eq__(cached_str, fresh_str):
        raise GateBlocked("final authority Path string cache is inconsistent")
    cached_drive = _path_slot(value, "_drv")
    if cached_drive is not _UNSET and not str.__eq__(
            cached_drive, _PATH_DRIVE_PROPERTY.fget(fresh)):
        raise GateBlocked("final authority Path drive cache is inconsistent")
    cached_root = _path_slot(value, "_root")
    if cached_root is not _UNSET and not str.__eq__(
            cached_root, _PATH_ROOT_PROPERTY.fget(fresh)):
        raise GateBlocked("final authority Path root cache is inconsistent")
    cached_tail = _path_slot(value, "_tail_cached")
    if cached_tail is not _UNSET and not _exact_str_sequence_equal(
            cached_tail, _PATH_TAIL_PROPERTY.fget(fresh)):
        raise GateBlocked("final authority Path tail cache is inconsistent")
    cached_normcase = _path_slot(value, "_str_normcase_cached")
    if cached_normcase is not _UNSET and not str.__eq__(
            cached_normcase, _PATH_STR_NORMCASE_PROPERTY.fget(fresh)):
        raise GateBlocked("final authority Path normcase cache is inconsistent")
    canonical = str.replace(fresh_str, _PATH_SEP, "/")
    if _PATH_ALTSEP is not None and not str.__eq__(_PATH_ALTSEP, "/"):
        canonical = str.replace(canonical, _PATH_ALTSEP, "/")
    return canonical, fresh


def _exact_path_string(value: object) -> str:
    return _exact_path_state(value)[0]


def _callable_identity(value: object) -> tuple:
    kind = type(value)
    if kind is types.MethodType:
        receiver = _METHOD_SELF_DESCRIPTOR.__get__(value, kind)
        function = _METHOD_FUNC_DESCRIPTOR.__get__(value, kind)
        return ("method", receiver, function)
    if (kind is types.FunctionType or kind is types.BuiltinFunctionType
            or kind is types.BuiltinMethodType):
        return ("function", value)
    raise GateBlocked("final authority callable is outside the exact contract")


def _exact_identity_tuple(value: object) -> tuple:
    """R10S: validate a callable-identity tuple BEFORE any len/index/comparison.

    Exact builtin tuple type, exact supported arity (3 method / 2 function),
    exact-str known tag, leaves held by reference only. A tuple subclass is
    refused without invoking user len/getitem/eq/hash/truth; no str() fallback.
    """
    if type(value) is not tuple:
        raise GateBlocked("final callable identity is not an exact builtin tuple")
    arity = tuple.__len__(value)
    if arity == 2:
        tag = tuple.__getitem__(value, 0)
        obj = tuple.__getitem__(value, 1)
        if type(tag) is not str or not str.__eq__(tag, "function"):
            raise GateBlocked("final callable identity function tag is not exact")
        return ("function", obj)
    if arity == 3:
        tag = tuple.__getitem__(value, 0)
        receiver = tuple.__getitem__(value, 1)
        function = tuple.__getitem__(value, 2)
        if type(tag) is not str or not str.__eq__(tag, "method"):
            raise GateBlocked("final callable identity method tag is not exact")
        return ("method", receiver, function)
    raise GateBlocked("final callable identity has unsupported arity")


def _callable_matches(current: object, identity: tuple) -> bool:
    try:
        candidate = _callable_identity(current)
        pinned = _exact_identity_tuple(identity)
    except GateBlocked:
        return False
    if not str.__eq__(candidate[0], pinned[0]):
        return False
    if str.__eq__(candidate[0], "method"):
        return candidate[1] is pinned[1] and candidate[2] is pinned[2]
    return candidate[1] is pinned[1]


def _callable_token(identity: tuple) -> tuple:
    pinned = _exact_identity_tuple(identity)
    if str.__eq__(pinned[0], "method"):
        return ("@method", str(id(pinned[1])), str(id(pinned[2])))
    return ("@function", str(id(pinned[1])))


def _identity_any(kind: type, choices: tuple) -> bool:
    for candidate in choices:
        if kind is candidate:
            return True
    return False


def _exact_mro(obj: object) -> tuple:
    """Pinned native __mro__ descriptor; no generic type attribute lookup."""
    return _native_mro(obj)


def _exact_class_namespace(klass: type) -> dict:
    """Pinned native class __dict__ descriptor; no metaclass data descriptor."""
    return _native_class_namespace(klass)


def _exact_storage(obj: object, *, recursive: bool = True,
                   protected: tuple = ()) -> tuple[dict, object]:
    """Close EVERY storage key/class namespace BEFORE any literal lookup."""
    raw = _native_instance_storage(obj, protected=protected)
    tree = _normalize_exact(raw) if recursive else None
    return raw, tree


def _normalize_exact(value: object, _depth: int = 0,
                     _stack: frozenset = frozenset(),
                     _nodes: list | None = None) -> object:
    """Recursively verify the COMPLETE final value domain BEFORE delegation."""
    if _nodes is None:
        _nodes = [0]
    _nodes[0] += 1
    if _depth > 16 or _nodes[0] > 4096:
        raise GateBlocked("final authority domain exceeds the bounded exact-value contract")
    kind = type(value)
    if kind is str or kind is bool or kind is int or kind is type(None):
        return value
    if kind is float:
        if not math.isfinite(value):
            raise GateBlocked("non-finite final authority number")
        return value
    if kind is bytes:
        if len(value) > 1024 * 1024:
            raise GateBlocked("final authority bytes exceed the bounded exact contract")
        return ("@bytes", bytes.hex(value))
    if kind is list or kind is tuple or kind is dict:
        ident = id(value)
        if ident in _stack or len(value) > 1024:
            raise GateBlocked("cyclic or oversized final authority container")
        stack = _stack | {ident}
        if kind is dict:
            out: dict = {}
            for key in dict.keys(value):
                if type(key) is not str:
                    raise GateBlocked("final authority mapping key is not an exact str")
                dict.__setitem__(out, key, _normalize_exact(
                    dict.__getitem__(value, key), _depth + 1, stack, _nodes))
            return {"@dict": out}
        items = tuple(_normalize_exact(part, _depth + 1, stack, _nodes)
                      for part in value)
        return ("@list" if kind is list else "@tuple", items)
    if _identity_any(kind, _EXACT_PATHS):
        return ("@path", _exact_path_string(value))
    if kind is _EXACT_OPAQUE_TYPE:
        return ("@opaque", str(id(kind)))
    if _identity_any(kind, _EXACT_DATACLASSES):
        ident = id(value)
        if ident in _stack:
            raise GateBlocked("cyclic final authority dataclass")
        stack = _stack | {ident}
        fields = _assert_pinned_dataclass_schema(kind)
        storage = _native_instance_storage(value)
        keys = tuple(dict.keys(storage))
        for key in keys:
            if not any(str.__eq__(key, field) for field in fields):
                raise GateBlocked("exact authority dataclass has an undeclared storage key")
        out = {"@type": str(id(kind))}
        for field in fields:
            if not dict.__contains__(storage, field):
                raise GateBlocked("final authority field is absent from controlled storage")
            dict.__setitem__(out, field, _normalize_exact(
                dict.__getitem__(storage, field), _depth + 1, stack, _nodes))
        return out
    if _identity_any(kind, _EXACT_CALLABLES):
        return _callable_token(_callable_identity(value))
    detail = _exact_type_qualname(kind)
    frames = []
    frame = sys._getframe(1)
    for _ in range(8):
        if frame is None:
            break
        frames.append(frame.f_code.co_name)
        frame = frame.f_back
    raise GateBlocked("final authority value is outside the recursively exact contract: "
                      + detail + ":" + str(id(kind)) + ":" + "/".join(frames))


def _materialize_exact(tree: object) -> object:
    """Rebuild exact builtins / exact whitelisted dataclasses from a closed tree."""
    kind = type(tree)
    if kind is str or kind is bool or kind is int or kind is float or kind is type(None):
        return tree
    if kind is tuple and len(tree) >= 1:
        tag = tree[0]
        if type(tag) is not str:
            raise GateBlocked("malformed exact authority tree tag")
        if tag == "@bytes" and len(tree) == 2 and type(tree[1]) is str:
            return bytes.fromhex(tree[1])
        if tag == "@path" and len(tree) == 2 and type(tree[1]) is str:
            path = _EXACT_PATH_CLASS(tree[1])
            if type(path) is not _EXACT_PATH_CLASS:
                raise GateBlocked("exact authority Path reconstruction changed type")
            return path
        if tag == "@list" and len(tree) == 2:
            return [_materialize_exact(part) for part in tree[1]]
        if tag == "@tuple" and len(tree) == 2:
            return tuple(_materialize_exact(part) for part in tree[1])
        if tag in ("@method", "@function", "@callable"):
            return tree
        if tag == "@opaque" and len(tree) == 2 and type(tree[1]) is str:
            if not dict.__contains__(_EXACT_OPAQUE_TOKENS, tree[1]):
                raise GateBlocked("unknown exact authority opaque token")
            return dict.__getitem__(_EXACT_OPAQUE_TOKENS, tree[1])
    if kind is dict:
        if dict.__contains__(tree, "@dict"):
            inner = dict.__getitem__(tree, "@dict")
            out: dict = {}
            for key in dict.keys(inner):
                if type(key) is not str:
                    raise GateBlocked("malformed exact authority mapping key")
                dict.__setitem__(out, key, _materialize_exact(dict.__getitem__(inner, key)))
            return out
        if dict.__contains__(tree, "@type"):
            token = dict.__getitem__(tree, "@type")
            if type(token) is not str or not dict.__contains__(_EXACT_TYPE_TOKENS, token):
                raise GateBlocked("unknown exact authority dataclass token")
            klass = dict.__getitem__(_EXACT_TYPE_TOKENS, token)
            fields = dict.__getitem__(_EXACT_FIELD_NAMES, token)
            values: dict = {}
            for field in fields:
                if not dict.__contains__(tree, field):
                    raise GateBlocked("exact authority dataclass field is absent")
                dict.__setitem__(values, field, _materialize_exact(dict.__getitem__(tree, field)))
            return _new_exact_dataclass(klass, values)
        out2: dict = {}
        for key in dict.keys(tree):
            if type(key) is not str:
                raise GateBlocked("malformed exact authority mapping key")
            dict.__setitem__(out2, key, _materialize_exact(dict.__getitem__(tree, key)))
        return out2
    raise GateBlocked("malformed exact authority tree")


def _exact_clone(value: object) -> object:
    return _materialize_exact(_normalize_exact(value))


def _rebuild_exact_dataclass(klass: type, values: dict) -> object:
    return _new_exact_dataclass(klass, values)


def _exact_sample(sample: object) -> TerminalSample:
    """Close the WHOLE sample and rebuild an exact TerminalSample before use."""
    if sample is None:
        raise GateBlocked("terminal sample is missing")
    mro = _native_mro(sample)
    if not any(klass is TerminalSample for klass in mro):
        raise GateBlocked("terminal sample is not the exact controlled type")
    fields = dict.__getitem__(_EXACT_FIELD_NAMES, str(id(TerminalSample)))
    raw, _ = _exact_storage(sample, recursive=True, protected=fields)
    values = {}
    for name in fields:
        if not dict.__contains__(raw, name):
            raise GateBlocked("terminal sample lacks a complete exact field set")
        dict.__setitem__(values, name, _exact_clone(dict.__getitem__(raw, name)))
    return _rebuild_exact_dataclass(TerminalSample, values)


def _exact_source(source: LocalGateSource, cell: "ControlledAuthorityCell",
                  owner_ref: object) -> LocalGateSource:
    if not any(klass is LocalGateSource for klass in _native_mro(source)):
        raise GateBlocked("local source is not the exact controlled type")
    raw = _native_instance_storage(source, protected=(
        "owner_state", "authority_cell", "host", "decision_ref", "agenticdoc_root",
        "key", "record_source", "task_key", "gate_decision_ref"))
    if (not dict.__contains__(raw, "owner_state")
            or not dict.__contains__(raw, "authority_cell")
            or dict.__getitem__(raw, "owner_state") is not owner_ref
            or dict.__getitem__(raw, "authority_cell") is not cell):
        raise GateBlocked("local source is not bound to the controlled producer owner")
    names = ("decision_ref", "agenticdoc_root", "key", "record_source",
             "task_key", "gate_decision_ref")
    values = {}
    for name in names:
        if not dict.__contains__(raw, name):
            raise GateBlocked("local source lacks a complete exact field set")
        dict.__setitem__(values, name, _exact_clone(dict.__getitem__(raw, name)))
    dict.__setitem__(values, "host", None)
    dict.__setitem__(values, "owner_state", owner_ref)
    dict.__setitem__(values, "authority_cell", cell)
    return _rebuild_exact_dataclass(LocalGateSource, values)

def _read_controlled_domain(owner: object) -> tuple[dict, str]:
    """ONE exact, non-delegating read of the complete final authority domain."""
    # R10A: the OWNER domain is read from its exact instance dict, never through
    # an attribute/descriptor lookup, so a same-named class property on the owner
    # (e.g. an ``execution`` property) is not authority and must not be invoked.
    # Reuse the existing native helper WITHOUT the protected owner-domain list:
    # it still walks the pinned native MRO/class namespaces, refuses any
    # user-defined ``__dict__`` descriptor, calls the pinned builtin getset
    # directly (no owner.__dict__ property, no getattr/object.__getattribute__
    # on a controlled field) and verifies ALL raw keys are exact str before this
    # function does any literal lookup. Missing dict/fields, bad keys and bad
    # leaves still fail closed below via dict.__contains__ and _frozen. This
    # relaxation is owner-domain specific: every other _native_instance_storage
    # caller keeps its full protected layout, and no final verification is
    # skipped.
    raw = _native_instance_storage(owner)
    domain: dict = {}
    for name in _CONTROLLED_DOMAIN_NAMES:
        if not dict.__contains__(raw, name):
            raise GateBlocked("authoritative owner lacks controlled field " + name)
        dict.__setitem__(domain, name, dict.__getitem__(raw, name))
    tree = _frozen(domain)
    return domain, tree


class ControlledAuthorityCell:
    """Consumer-private exact-slot authority cell; no virtual authority source."""
    __slots__ = ("_owner", "_generation", "_last_tree", "_invalidated",
                 "_rebinds", "_writer_pin")

    def __init__(self, owner: object):
        _CELL_SLOT_DESCRIPTORS["_owner"].__set__(self, owner)
        _CELL_SLOT_DESCRIPTORS["_generation"].__set__(self, 0)
        _CELL_SLOT_DESCRIPTORS["_last_tree"].__set__(self, None)
        _CELL_SLOT_DESCRIPTORS["_invalidated"].__set__(self, False)
        _CELL_SLOT_DESCRIPTORS["_rebinds"].__set__(self, 0)
        _CELL_SLOT_DESCRIPTORS["_writer_pin"].__set__(self, None)

    def owner(self) -> object:
        return dict.__getitem__(_read_cell_state(self), "_owner")

    def generation(self) -> int:
        return dict.__getitem__(_read_cell_state(self), "_generation")

    def invalidated(self) -> bool:
        return dict.__getitem__(_read_cell_state(self), "_invalidated")

    def rebinds(self) -> int:
        return dict.__getitem__(_read_cell_state(self), "_rebinds")

    def rebind(self, new_owner: object) -> None:
        state = _read_cell_state(self)
        _CELL_SLOT_DESCRIPTORS["_rebinds"].__set__(self, state["_rebinds"] + 1)
        _CELL_SLOT_DESCRIPTORS["_owner"].__set__(self, new_owner)
        _CELL_SLOT_DESCRIPTORS["_invalidated"].__set__(self, True)

    def producer_domain(self) -> dict:
        state = _read_cell_state(self)
        raw, tree = _read_controlled_domain(dict.__getitem__(state, "_owner"))
        if type(tree) is not str:
            raise GateBlocked("controlled producer tree is not an exact str")
        _CELL_SLOT_DESCRIPTORS["_generation"].__set__(self, state["_generation"] + 1)
        _CELL_SLOT_DESCRIPTORS["_last_tree"].__set__(self, tree)
        return raw

    def consumer_verify(self, host: object, pinned_owner: object,
                        base_generation: int) -> dict:
        state = _read_cell_state(self)
        if state["_invalidated"] is not False:
            raise GateBlocked("controlled producer-owner storage was rebound and is invalidated")
        if state["_owner"] is not pinned_owner:
            raise GateBlocked("controlled producer owner is not the consumer-pinned owner")
        host_storage = _native_instance_storage(host, protected=("f", "_authority_cell"))
        if (not dict.__contains__(host_storage, "f")
                or not dict.__contains__(host_storage, "_authority_cell")):
            raise GateBlocked("real producer host lacks its controlled owner or cell slot")
        current = dict.__getitem__(host_storage, "f")
        bound_cell = dict.__getitem__(host_storage, "_authority_cell")
        if current is not pinned_owner or bound_cell is not self:
            raise GateBlocked("real producer owner was rebound during the terminal boundary")
        raw, tree = _read_controlled_domain(pinned_owner)
        if type(base_generation) is not int or state["_generation"] < base_generation + 2:
            raise GateBlocked("real producer did not publish both terminal reads in this boundary")
        last = state["_last_tree"]
        if type(last) is not str or type(tree) is not str or not str.__eq__(last, tree):
            raise GateBlocked("final complete live authority domain changed after the last callback")
        return raw


_CELL_SLOT_NAMES = ControlledAuthorityCell.__slots__
_CELL_SLOT_DESCRIPTORS = {}
_CELL_NAMESPACE = _native_class_namespace(ControlledAuthorityCell)
_CELL_NAMESPACE_KEYS = tuple(dict.keys(_CELL_NAMESPACE))
_CELL_NAMESPACE_VALUES = {}
for _slot in _CELL_SLOT_NAMES:
    _descriptor = dict.__getitem__(_CELL_NAMESPACE, _slot)
    if type(_descriptor) is not types.MemberDescriptorType:
        raise RuntimeError("unsupported controlled cell slot layout")
    dict.__setitem__(_CELL_SLOT_DESCRIPTORS, _slot, _descriptor)
    dict.__setitem__(_CELL_NAMESPACE_VALUES, _slot, _descriptor)
_CELL_MRO = _native_type_mro(ControlledAuthorityCell)


class _WriterPin:
    """Durable consumer-private BoundAction identity pin (one per cell)."""
    __slots__ = ("name", "object_path_text", "apply", "inspect",
                 "apply_identity", "inspect_identity", "legacy_closure",
                 "lifecycle_action")


_WRITER_PIN_SLOT_NAMES = _WriterPin.__slots__
_WRITER_PIN_SLOT_DESCRIPTORS = {}
_WRITER_PIN_NAMESPACE = _native_class_namespace(_WriterPin)
_WRITER_PIN_NAMESPACE_KEYS = tuple(dict.keys(_WRITER_PIN_NAMESPACE))
_WRITER_PIN_NAMESPACE_VALUES = {}
for _slot in _WRITER_PIN_SLOT_NAMES:
    _descriptor = dict.__getitem__(_WRITER_PIN_NAMESPACE, _slot)
    if type(_descriptor) is not types.MemberDescriptorType:
        raise RuntimeError("unsupported writer pin slot layout")
    dict.__setitem__(_WRITER_PIN_SLOT_DESCRIPTORS, _slot, _descriptor)
    dict.__setitem__(_WRITER_PIN_NAMESPACE_VALUES, _slot, _descriptor)
_WRITER_PIN_MRO = _native_type_mro(_WriterPin)


def _assert_cell_layout(cell: object) -> None:
    if type(cell) is not ControlledAuthorityCell:
        raise GateBlocked("controlled producer cell is not the exact controlled type")
    _assert_native_type_layout(ControlledAuthorityCell, _CELL_MRO,
                               _CELL_NAMESPACE_KEYS, _CELL_NAMESPACE_VALUES)
    namespace = _native_class_namespace(ControlledAuthorityCell)
    for name, expected in _CELL_SLOT_DESCRIPTORS.items():
        if dict.__getitem__(namespace, name) is not expected:
            raise GateBlocked("controlled producer cell slot layout changed")


def _read_cell_state(cell: object) -> dict:
    _assert_cell_layout(cell)
    state = {}
    for name, descriptor in _CELL_SLOT_DESCRIPTORS.items():
        dict.__setitem__(state, name, descriptor.__get__(cell, ControlledAuthorityCell))
    if type(state["_generation"]) is not int or type(state["_rebinds"]) is not int:
        raise GateBlocked("controlled producer cell counter is not an exact int")
    if type(state["_invalidated"]) is not bool:
        raise GateBlocked("controlled producer cell flag is not an exact bool")
    if state["_last_tree"] is not None and type(state["_last_tree"]) is not str:
        raise GateBlocked("controlled producer cell tree is not an exact str")
    if state["_owner"] is None:
        raise GateBlocked("controlled producer cell has no owner")
    pin = state["_writer_pin"]
    if pin is not None and type(pin) is not _WriterPin:
        raise GateBlocked("controlled producer cell writer pin is not exact")
    return state


def _read_writer_pin_state(pin: object) -> tuple:
    if type(pin) is not _WriterPin:
        raise GateBlocked("independent writer pin is not the exact controlled type")
    _assert_native_type_layout(_WriterPin, _WRITER_PIN_MRO,
                               _WRITER_PIN_NAMESPACE_KEYS, _WRITER_PIN_NAMESPACE_VALUES)
    slots = {}
    for name, descriptor in _WRITER_PIN_SLOT_DESCRIPTORS.items():
        dict.__setitem__(slots, name, descriptor.__get__(pin, _WriterPin))
    if (type(slots["name"]) is not str or type(slots["object_path_text"]) is not str
            or type(slots["legacy_closure"]) is not bool
            or type(slots["lifecycle_action"]) is not str):
        raise GateBlocked("independent writer pin metadata is not exact")
    # R10S: exact-type/arity/tag/leaf guard on the two identity tuples BEFORE
    # any downstream len/index/comparison. A hostile subclass slot is refused
    # here with ZERO user protocol calls, not trusted because it is "private".
    apply_id = _exact_identity_tuple(slots["apply_identity"])
    inspect_id = _exact_identity_tuple(slots["inspect_identity"])
    return (slots["name"], slots["object_path_text"], slots["apply"], slots["inspect"],
            apply_id, inspect_id, slots["legacy_closure"], slots["lifecycle_action"])


def _identity_tuple_equal(left: tuple, right: tuple) -> bool:
    # R10S: exact type/arity/tag/leaf BEFORE any len/index, then only is/str.
    try:
        a = _exact_identity_tuple(left)
        b = _exact_identity_tuple(right)
    except GateBlocked:
        return False
    if not str.__eq__(a[0], b[0]):
        return False
    if tuple.__len__(a) == 3:
        return a[1] is b[1] and a[2] is b[2]
    return a[1] is b[1]


def _writer_pin_state_equal(left: tuple, right: tuple) -> bool:
    # R10S: exact tuple type and arity BEFORE any len/index/iteration; each leaf
    # compared only via is / str.__eq__ on exact primitives, never str()/eq/hash.
    if type(left) is not tuple or type(right) is not tuple:
        return False
    if tuple.__len__(left) != 8 or tuple.__len__(right) != 8:
        return False
    for index in range(8):
        a = tuple.__getitem__(left, index)
        b = tuple.__getitem__(right, index)
        if index == 2 or index == 3:            # raw callables: identity only
            if a is not b:
                return False
        elif index == 4 or index == 5:          # callable-identity tuples
            if not _identity_tuple_equal(a, b):
                return False
        elif index == 6:                        # exact bool flag
            if type(a) is not bool or a is not b:
                return False
        else:                                   # exact str metadata (0,1,7)
            if type(a) is not str or type(b) is not str or not str.__eq__(a, b):
                return False
    return True


def _new_writer_pin_state(action: object) -> tuple:
    if type(action) is not BoundAction:
        raise GateBlocked("pre-callback bounded action is not the exact controlled type")
    _assert_pinned_dataclass_schema(BoundAction)
    raw = _native_instance_storage(action)
    fields = dict.__getitem__(_EXACT_FIELD_NAMES, str(id(BoundAction)))
    for field in fields:
        if not dict.__contains__(raw, field):
            raise GateBlocked("pre-callback bounded action lacks an exact field")
    name = dict.__getitem__(raw, "name")
    path_text = _exact_path_string(dict.__getitem__(raw, "object_path"))
    apply = dict.__getitem__(raw, "apply")
    inspect = dict.__getitem__(raw, "inspect")
    legacy = dict.__getitem__(raw, "legacy_closure")
    lifecycle = dict.__getitem__(raw, "lifecycle_action")
    if (type(name) is not str or type(legacy) is not bool
            or type(lifecycle) is not str):
        raise GateBlocked("pre-callback bounded action metadata is not exact")
    return (name, path_text, apply, inspect, _callable_identity(apply),
            _callable_identity(inspect), legacy, lifecycle)


def _new_writer_pin(state: tuple) -> _WriterPin:
    pin = object.__new__(_WriterPin)
    for name, value in zip(_WRITER_PIN_SLOT_NAMES, state):
        dict.__getitem__(_WRITER_PIN_SLOT_DESCRIPTORS, name).__set__(pin, value)
    return pin


def _assert_action_matches_pin(action: object, state: tuple) -> None:
    if type(action) is not BoundAction:
        raise GateBlocked("final bounded action is not the exact controlled type")
    _assert_pinned_dataclass_schema(BoundAction)
    raw = _native_instance_storage(action)
    if (not str.__eq__(dict.__getitem__(raw, "name"), state[0])
            or not str.__eq__(_exact_path_string(dict.__getitem__(raw, "object_path")), state[1])
            or not _callable_matches(dict.__getitem__(raw, "apply"), state[4])
            or not _callable_matches(dict.__getitem__(raw, "inspect"), state[5])
            or dict.__getitem__(raw, "legacy_closure") is not state[6]
            or not str.__eq__(dict.__getitem__(raw, "lifecycle_action"), state[7])):
        raise GateBlocked("final bounded action changed against the independent writer pin")


def _make_pinned_action(state: tuple) -> BoundAction:
    path = _EXACT_PATH_CLASS(state[1])
    if type(path) is not _EXACT_PATH_CLASS:
        raise GateBlocked("independent writer pin cannot rebuild its exact Path")
    return _new_exact_dataclass(BoundAction, {
        "name": state[0], "object_path": path, "apply": state[2], "inspect": state[3],
        "legacy_closure": state[6], "lifecycle_action": state[7],
    })


def _writer_pin_for_source(source: LocalGateSource) -> tuple[_WriterPin, tuple]:
    """Create/reuse ONE durable pre-callback writer pin; never re-pin changed writers."""
    if not any(klass is LocalGateSource for klass in _native_mro(source)):
        raise GateBlocked("local source is not the exact controlled type")
    source_raw = _native_instance_storage(source, protected=(
        "owner_state", "authority_cell", "host"))
    owner = dict.__getitem__(source_raw, "owner_state")
    cell = dict.__getitem__(source_raw, "authority_cell")
    host = dict.__getitem__(source_raw, "host")
    cell_state = _read_cell_state(cell)
    if cell_state["_owner"] is not owner:
        raise GateBlocked("controlled cell owner is not the source owner")
    host_raw = _native_instance_storage(host, protected=("f", "_authority_cell"))
    if (dict.__getitem__(host_raw, "f") is not owner
            or dict.__getitem__(host_raw, "_authority_cell") is not cell):
        raise GateBlocked("pre-callback host/cell/owner association is not pinned")
    owner_raw = _native_instance_storage(owner)
    facts = dict.__getitem__(owner_raw, "facts")
    if type(facts) is not GateFacts:
        raise GateBlocked("pre-callback owner facts are not the exact controlled type")
    facts_raw = _native_instance_storage(facts)
    action = dict.__getitem__(facts_raw, "action")
    pin = cell_state["_writer_pin"]
    if pin is None:
        state = _new_writer_pin_state(action)
        pin = _new_writer_pin(state)
        dict.__getitem__(_CELL_SLOT_DESCRIPTORS, "_writer_pin").__set__(cell, pin)
    else:
        state = _read_writer_pin_state(pin)
        _assert_action_matches_pin(action, state)
    return pin, state


def _native_exact_dict_keys(value: object) -> tuple:
    """R11 B1: close EVERY current live dict key before a literal lookup.

    Only a builtin dict with exact-str, non-colliding keys is admitted. The
    complete key set is copied first; no dict contains/getitem or user eq/hash
    runs while the set is being closed.
    """
    if type(value) is not dict:
        raise GateBlocked("final recheck mapping is not an exact builtin dict")
    keys = tuple(dict.keys(value))
    count = tuple.__len__(keys)
    if count > 1024 or dict.__len__(value) != count:
        raise GateBlocked("final recheck mapping exceeds the bounded exact contract")
    for i in range(count):
        if type(tuple.__getitem__(keys, i)) is not str:
            raise GateBlocked("final recheck mapping key is not an exact str")
    for i in range(count):
        key = tuple.__getitem__(keys, i)
        for j in range(i):
            if str.__eq__(tuple.__getitem__(keys, j), key):
                raise GateBlocked("final recheck mapping has colliding exact keys")
    return keys


def _native_closed_dict_indices(live_keys: tuple, expected: tuple,
                                *, exact_size: bool = True) -> tuple | None:
    """Pair exact held names with the already-closed live key set, natively."""
    if type(live_keys) is not tuple or type(expected) is not tuple:
        raise GateBlocked("malformed final recheck mapping closure")
    count = tuple.__len__(expected)
    live_count = tuple.__len__(live_keys)
    if count > 1024 or live_count > 1024 or live_count < count:
        return None
    if exact_size and live_count != count:
        return None
    for i in range(count):
        name = tuple.__getitem__(expected, i)
        if type(name) is not str:
            raise GateBlocked("malformed final recheck mapping held key")
        for j in range(i):
            if str.__eq__(tuple.__getitem__(expected, j), name):
                raise GateBlocked("final recheck mapping has duplicate held keys")
    indices = []
    for i in range(count):
        name = tuple.__getitem__(expected, i)
        found = -1
        for j in range(live_count):
            if str.__eq__(name, tuple.__getitem__(live_keys, j)):
                found = j
        if found < 0:
            return None
        list.append(indices, found)
    for i in range(count):
        for j in range(i):
            if list.__getitem__(indices, i) == list.__getitem__(indices, j):
                return None
    return tuple(indices)


def _native_path_slot_projection(value: object, name: str, nodes: list) -> tuple:
    """R11 B2: detach one native Path slot without Path/user methods."""
    slot = _path_slot(value, name)
    nodes[0] += 1
    if nodes[0] > 4096:
        raise GateBlocked("final recheck Path slots exceed the bounded exact contract")
    if slot is _UNSET:
        return ("unset",)
    kind = type(slot)
    if kind is type(None):
        return ("none",)
    if kind is str:
        return ("str", slot)
    if kind is int:
        return ("int", slot)
    if kind is list or kind is tuple:
        exact_list = kind is list
        count = list.__len__(slot) if exact_list else tuple.__len__(slot)
        if count > 1024:
            raise GateBlocked("final recheck Path slot exceeds the bounded exact contract")
        nodes[0] += count
        if nodes[0] > 4096:
            raise GateBlocked("final recheck Path slots exceed the bounded exact contract")
        parts = []
        for i in range(count):
            part = (list.__getitem__(slot, i) if exact_list
                    else tuple.__getitem__(slot, i))
            if type(part) is not str:
                raise GateBlocked("final recheck Path slot leaf is not an exact str")
            list.append(parts, part)
        return ("list" if exact_list else "tuple", tuple(parts))
    raise GateBlocked("final recheck Path slot is outside the exact native contract")


def _native_path_slot_snapshot(value: object, nodes: list) -> tuple:
    if type(value) is not _EXACT_PATH_CLASS:
        raise GateBlocked("final recheck Path is not the exact native concrete type")
    slots = []
    for i in range(tuple.__len__(_PATH_SLOT_NAMES)):
        list.append(slots, _native_path_slot_projection(
            value, tuple.__getitem__(_PATH_SLOT_NAMES, i), nodes))
    return ("path", value, tuple(slots))


def _native_path_projection_equal(live: object, held: object) -> bool:
    if type(live) is not tuple or type(held) is not tuple:
        raise GateBlocked("malformed final recheck Path slot")
    count = tuple.__len__(live)
    if count < 1 or tuple.__len__(held) != count:
        return False
    tag = tuple.__getitem__(live, 0)
    held_tag = tuple.__getitem__(held, 0)
    if type(tag) is not str or type(held_tag) is not str or not str.__eq__(tag, held_tag):
        return False
    if str.__eq__(tag, "unset") or str.__eq__(tag, "none"):
        return count == 1
    if str.__eq__(tag, "str"):
        if count != 2:
            return False
        a, b = tuple.__getitem__(live, 1), tuple.__getitem__(held, 1)
        return type(a) is str and type(b) is str and str.__eq__(a, b)
    if str.__eq__(tag, "int"):
        if count != 2:
            return False
        a, b = tuple.__getitem__(live, 1), tuple.__getitem__(held, 1)
        return type(a) is int and type(b) is int and int.__eq__(a, b)
    if str.__eq__(tag, "list") or str.__eq__(tag, "tuple"):
        if count != 2:
            return False
        a, b = tuple.__getitem__(live, 1), tuple.__getitem__(held, 1)
        if type(a) is not tuple or type(b) is not tuple:
            return False
        size = tuple.__len__(a)
        if size > 1024 or tuple.__len__(b) != size:
            return False
        for i in range(size):
            x, y = tuple.__getitem__(a, i), tuple.__getitem__(b, i)
            if type(x) is not str or type(y) is not str or not str.__eq__(x, y):
                return False
        return True
    raise GateBlocked("unknown final recheck Path slot tag")


def _native_path_slots_match(live: object, held_slots: object) -> bool:
    if type(live) is not _EXACT_PATH_CLASS or type(held_slots) is not tuple:
        return False
    count = tuple.__len__(held_slots)
    if count != tuple.__len__(_PATH_SLOT_NAMES):
        raise GateBlocked("malformed final recheck Path slot set")
    nodes = [0]
    for i in range(count):
        fresh = _native_path_slot_projection(
            live, tuple.__getitem__(_PATH_SLOT_NAMES, i), nodes)
        if not _native_path_projection_equal(fresh, tuple.__getitem__(held_slots, i)):
            return False
    return True


def _native_recheck_snapshot(value: object, _depth: int = 0,
                             _nodes: list | None = None) -> tuple:
    """R10S PREPARATION: bounded, exact-type-guarded, non-delegating recursive
    snapshot of a live authority value. Scalar/Path/callable/bytes/opaque leaves
    are HELD BY REFERENCE for the final identity recheck; containers are copied
    into exact builtin tuples. Every read is a pinned builtin with an exact-type
    /key guard BEFORE the literal lookup: no user len/getitem/eq/hash/truth/
    iteration is invoked. Called BEFORE the final association suffix only."""
    if _nodes is None:
        _nodes = [0]
    _nodes[0] += 1
    if _depth > 16 or _nodes[0] > 4096:
        raise GateBlocked("final recheck domain exceeds the bounded exact-value contract")
    kind = type(value)
    if kind is str or kind is bool or kind is int or kind is type(None):
        return ("prim", value)
    if kind is float:
        if not math.isfinite(value):
            raise GateBlocked("non-finite final recheck number")
        return ("prim", value)
    if _identity_any(kind, _EXACT_PATHS):
        return _native_path_slot_snapshot(value, _nodes)
    if (kind is bytes or _identity_any(kind, _EXACT_CALLABLES)
            or kind is _EXACT_OPAQUE_TYPE):
        return ("ref", value)
    if kind is list or kind is tuple or kind is dict:
        if kind is dict:
            keys = _native_exact_dict_keys(value)
            children = []
            for i in range(tuple.__len__(keys)):
                key = tuple.__getitem__(keys, i)
                children.append((key, _native_recheck_snapshot(
                    dict.__getitem__(value, key), _depth + 1, _nodes)))
            return ("dict", tuple(children))
        count = list.__len__(value) if kind is list else tuple.__len__(value)
        if count > 1024:
            raise GateBlocked("oversized final recheck container")
        items = []
        for i in range(count):
            part = (list.__getitem__(value, i) if kind is list
                    else tuple.__getitem__(value, i))
            items.append(_native_recheck_snapshot(part, _depth + 1, _nodes))
        return ("list" if kind is list else "tuple", tuple(items))
    if _identity_any(kind, _EXACT_DATACLASSES):
        fields = _assert_pinned_dataclass_schema(kind)
        storage = _native_instance_storage(value)
        keys = _native_exact_dict_keys(storage)
        indices = _native_closed_dict_indices(keys, fields)
        if indices is None:
            raise GateBlocked("final recheck dataclass has an undeclared storage key")
        children = []
        for i in range(tuple.__len__(fields)):
            field = tuple.__getitem__(fields, i)
            live_key = tuple.__getitem__(keys, tuple.__getitem__(indices, i))
            children.append((field, _native_recheck_snapshot(
                dict.__getitem__(storage, live_key), _depth + 1, _nodes)))
        return ("type", str(id(kind)), tuple(children))
    raise GateBlocked("final recheck value is outside the recursively exact contract")


def _native_recheck_matches(live: object, held: object) -> bool:
    """R10S SUFFIX: bounded, exact-type-guarded, non-delegating re-read of a
    freshly re-read LIVE value against a held snapshot node. Uses ONLY builtin
    reads (dict/tuple/list __getitem__/__contains__/__len__), exact-type guards,
    `is` and str.__eq__. No clone/parse/normalize/Path rebuild/getattr and no
    user eq/hash/len/getitem/truth/iteration. Called ONLY in the final suffix."""
    if type(held) is not tuple or tuple.__len__(held) < 1:
        raise GateBlocked("malformed final recheck snapshot")
    tag = tuple.__getitem__(held, 0)
    if type(tag) is not str:
        raise GateBlocked("malformed final recheck snapshot tag")
    if str.__eq__(tag, "path"):
        if (tuple.__len__(held) != 3
                or type(tuple.__getitem__(held, 2)) is not tuple):
            raise GateBlocked("malformed final recheck Path")
        ref = tuple.__getitem__(held, 1)
        if type(ref) is not _EXACT_PATH_CLASS:
            raise GateBlocked("malformed final recheck Path reference")
        if type(live) is not _EXACT_PATH_CLASS or live is not ref:
            return False
        return _native_path_slots_match(live, tuple.__getitem__(held, 2))
    if str.__eq__(tag, "prim") or str.__eq__(tag, "ref"):
        if tuple.__len__(held) != 2:
            raise GateBlocked("malformed final recheck leaf")
        ref = tuple.__getitem__(held, 1)
        return type(live) is type(ref) and live is ref
    if str.__eq__(tag, "list") or str.__eq__(tag, "tuple"):
        if tuple.__len__(held) != 2 or type(tuple.__getitem__(held, 1)) is not tuple:
            raise GateBlocked("malformed final recheck container")
        children = tuple.__getitem__(held, 1)
        expected = list if str.__eq__(tag, "list") else tuple
        if type(live) is not expected:
            return False
        count = tuple.__len__(children)
        length = list.__len__(live) if expected is list else tuple.__len__(live)
        if length != count:
            return False
        for i in range(count):
            item = (list.__getitem__(live, i) if expected is list
                    else tuple.__getitem__(live, i))
            if not _native_recheck_matches(item, tuple.__getitem__(children, i)):
                return False
        return True
    if str.__eq__(tag, "dict"):
        if tuple.__len__(held) != 2 or type(tuple.__getitem__(held, 1)) is not tuple:
            raise GateBlocked("malformed final recheck mapping")
        children = tuple.__getitem__(held, 1)
        if type(live) is not dict:
            return False
        try:
            live_keys = _native_exact_dict_keys(live)
        except GateBlocked:
            return False
        count = tuple.__len__(children)
        names = []
        for i in range(count):
            entry = tuple.__getitem__(children, i)
            if type(entry) is not tuple or tuple.__len__(entry) != 2:
                raise GateBlocked("malformed final recheck mapping entry")
            key = tuple.__getitem__(entry, 0)
            if type(key) is not str:
                raise GateBlocked("malformed final recheck mapping key")
            list.append(names, key)
        indices = _native_closed_dict_indices(live_keys, tuple(names))
        if indices is None:
            return False
        for i in range(count):
            entry = tuple.__getitem__(children, i)
            live_key = tuple.__getitem__(live_keys, tuple.__getitem__(indices, i))
            if not _native_recheck_matches(dict.__getitem__(live, live_key),
                                           tuple.__getitem__(entry, 1)):
                return False
        return True
    if str.__eq__(tag, "type"):
        if (tuple.__len__(held) != 3
                or type(tuple.__getitem__(held, 1)) is not str
                or type(tuple.__getitem__(held, 2)) is not tuple):
            raise GateBlocked("malformed final recheck typed value")
        token = tuple.__getitem__(held, 1)
        if not dict.__contains__(_EXACT_TYPE_TOKENS, token):
            raise GateBlocked("unknown final recheck dataclass token")
        klass = dict.__getitem__(_EXACT_TYPE_TOKENS, token)
        if type(live) is not klass:
            return False
        storage = _native_instance_storage(live)
        try:
            storage_keys = _native_exact_dict_keys(storage)
        except GateBlocked:
            return False
        children = tuple.__getitem__(held, 2)
        count = tuple.__len__(children)
        names = []
        for i in range(count):
            entry = tuple.__getitem__(children, i)
            if type(entry) is not tuple or tuple.__len__(entry) != 2:
                raise GateBlocked("malformed final recheck field entry")
            field = tuple.__getitem__(entry, 0)
            if type(field) is not str:
                raise GateBlocked("malformed final recheck field name")
            list.append(names, field)
        indices = _native_closed_dict_indices(storage_keys, tuple(names))
        if indices is None:
            return False
        for i in range(count):
            entry = tuple.__getitem__(children, i)
            live_key = tuple.__getitem__(storage_keys, tuple.__getitem__(indices, i))
            if not _native_recheck_matches(dict.__getitem__(storage, live_key),
                                           tuple.__getitem__(entry, 1)):
                return False
        return True
    raise GateBlocked("unknown final recheck snapshot tag")


def _final_native_suffix(source: LocalGateSource, owner_ref: object,
                         cell: ControlledAuthorityCell, base_generation: int,
                         writer_pin: _WriterPin, writer_pin_state: tuple,
                         prepared_tree: str, held_snapshot: tuple) -> None:
    """R10S FINAL native association/value suffix, executed LAST.

    Re-reads the ORIGINAL live source/host/cell/owner associations, native
    slots, the exact-type-guarded writer-pin identity and the complete live
    domain VALUES, then compares them against the held prepared exact
    projection. This is a purely native read; NO clone/parse/normalize/
    materialize/Path rebuild/getattr/user protocol runs inside or after it (the
    only later helper is the bounded frozen current-clock predicate)."""
    source_raw = _native_instance_storage(source, protected=(
        "owner_state", "authority_cell", "host"))
    if (dict.__getitem__(source_raw, "owner_state") is not owner_ref
            or dict.__getitem__(source_raw, "authority_cell") is not cell):
        raise GateBlocked("final local source owner or cell association changed")
    real_host = dict.__getitem__(source_raw, "host")
    cell_state = _read_cell_state(cell)
    durable_pin = cell_state["_writer_pin"]
    # exact-type/arity/tag guard runs BEFORE any len/index of an identity leaf.
    if durable_pin is not writer_pin or not _writer_pin_state_equal(
            _read_writer_pin_state(durable_pin), writer_pin_state):
        raise GateBlocked("independent writer pin changed inside a terminal boundary")
    if (cell_state["_invalidated"] is not False or cell_state["_rebinds"] != 0
            or cell_state["_owner"] is not owner_ref):
        raise GateBlocked("controlled producer cell was rebound or invalidated")
    host_raw = _native_instance_storage(real_host, protected=("f", "_authority_cell"))
    if (not dict.__contains__(host_raw, "f")
            or not dict.__contains__(host_raw, "_authority_cell")):
        raise GateBlocked("real producer host lacks its controlled owner or cell slot")
    if (dict.__getitem__(host_raw, "f") is not owner_ref
            or dict.__getitem__(host_raw, "_authority_cell") is not cell):
        raise GateBlocked("real producer host/cell/owner association changed")
    if type(base_generation) is not int or cell_state["_generation"] < base_generation + 2:
        raise GateBlocked("real producer did not publish both terminal reads in this boundary")
    last = cell_state["_last_tree"]
    if type(last) is not str or type(prepared_tree) is not str or not str.__eq__(last, prepared_tree):
        raise GateBlocked("final complete live authority domain changed after the last callback")
    # Re-read the LIVE complete-domain values natively (bounded, exact-type-
    # guarded) and compare with the held prepared exact snapshot. No Path
    # rebuild / clone / parse here: this is the final freshness recheck.
    if (type(held_snapshot) is not tuple or tuple.__len__(held_snapshot) != 2
            or not str.__eq__(tuple.__getitem__(held_snapshot, 0), "dict")):
        raise GateBlocked("malformed held final authority snapshot")
    children = tuple.__getitem__(held_snapshot, 1)
    if type(children) is not tuple:
        raise GateBlocked("malformed held final authority snapshot")
    fresh_raw = _native_instance_storage(owner_ref)
    fresh_keys = _native_exact_dict_keys(fresh_raw)
    names = []
    for i in range(tuple.__len__(children)):
        entry = tuple.__getitem__(children, i)
        if type(entry) is not tuple or tuple.__len__(entry) != 2:
            raise GateBlocked("malformed held final authority entry")
        name = tuple.__getitem__(entry, 0)
        if type(name) is not str:
            raise GateBlocked("malformed held final authority field name")
        list.append(names, name)
    indices = _native_closed_dict_indices(fresh_keys, tuple(names), exact_size=False)
    if indices is None:
        raise GateBlocked("final live authority domain lost a controlled field")
    for i in range(tuple.__len__(children)):
        entry = tuple.__getitem__(children, i)
        live_key = tuple.__getitem__(fresh_keys, tuple.__getitem__(indices, i))
        if not _native_recheck_matches(dict.__getitem__(fresh_raw, live_key),
                                       tuple.__getitem__(entry, 1)):
            raise GateBlocked("final complete live authority domain value changed after the last callback")


@dataclass(frozen=True)
class _FinalAuthority:
    """Non-delegating, COMPLETE, immutable final authority projection (R6).

    This frozen value IS the controlled storage for the final decision: exact
    ``str``/``bool`` projections plus exact builtin ``dict`` records and exact
    typed local records. There is NO retained user attribute/container/comparison
    reference that could delegate during the final comparison. Producer and
    consumer are bound to ONE authoritative owner (see ``authority_owner``);
    after the last callback the consumer captures that owner's WHOLE declared
    authority domain here in a SINGLE ``object.__getattribute__`` /
    exact-type-guarded pass. Reads/writes do not delegate:

      * ``object.__getattribute__(owner, name)`` bypasses any user
        ``__getattribute__`` / ``__getattr__`` / descriptor on the plain instance
        attributes, so the F2 ``__getattribute__("execution")`` hook never runs;
      * selection/execution MUST be ``type(x) is dict`` (an overridden
        ``.get`` / ``__iter__`` dict subclass is REFUSED, never invoked), so the
        F2 ``dict.get("schema_version")`` hook never runs; typed records are then
        built by the frozen reader over plain builtin dict operations;
      * context/expectations/action-evidence/facts MUST be the exact local
        dataclass types, whose plain-field freeze uses no user delegation;
      * the disposition condition MUST be an exact ``bool``.

    Every derived field is an immutable str/bool. The final determination then
    compares only these immutable values, so NO user attribute / container /
    comparison callback can run after an earlier field was validated. This is the
    completed-callback contract, bounded best effort, NOT OS-level atomicity.
    """
    context: local_evidence.TrustedContext
    selection: dict
    execution: dict
    selection_typed: local_evidence.LocalSelectionRecord
    execution_typed: local_evidence.LocalExecutionRecord
    context_state: str
    expectations_state: str
    action_evidence_state: str
    facts_state: str
    selection_state: str
    execution_state: str
    disposition_state: str
    state_fingerprint: str


def _capture_final_authority(domain: dict, source: LocalGateSource,
                             claim_id: str) -> _FinalAuthority:
    """Read the COMPLETE authoritative domain from the identity-bound owner in
    ONE non-delegating pass, BEFORE any final comparison. Rejects (GateBlocked)
    any delegating container / attribute boundary instead of invoking it. Covers
    ctx/budget/binding/stop (via _validate_context + deadline), typed
    selection/execution full semantics (frozen reader over exact dicts),
    expectations, action-evidence, disposition condition and facts/action.
    """
    def raw(name: str) -> object:
        try:
            return dict.__getitem__(domain, name)
        except KeyError as exc:
            raise GateBlocked("controlled final domain lacks " + name) from exc

    context = raw("ctx")
    expectations = raw("expectations")
    action_evidence = raw("evidence")
    facts = raw("facts")
    selection = raw("selection")
    execution = raw("execution")
    disposition_ok = raw("disposition_ok")
    recovery_disposition_ok = raw("recovery_disposition_ok")

    # Narrow EXACT-type boundary: no user container/attribute/descriptor /
    # comparison delegation is ever CALLED below (only these exact types pass).
    if type(context) is not local_evidence.TrustedContext:
        raise GateBlocked("final live context is not the exact controlled value type")
    if type(expectations) is not LocalGateExpectations:
        raise GateBlocked("final live expectations are not the exact controlled value type")
    if type(action_evidence) is not local_evidence.ActionResultEvidence:
        raise GateBlocked("final live action evidence is not the exact controlled value type")
    if type(facts) is not GateFacts:
        raise GateBlocked("final live facts are not the exact controlled value type")
    if type(selection) is not dict or type(execution) is not dict:
        raise GateBlocked("final live typed records must be exact builtin dicts; delegating containers refused")
    if type(disposition_ok) is not bool or type(recovery_disposition_ok) is not bool:
        raise GateBlocked("final live disposition condition is not an exact bool")

    # Exact-typed values only from here: every operation is a builtin / frozen-
    # reader call over plain dicts and exact dataclasses (non-delegating).
    context_state = _validate_context(context, expectations, source, claim_id)
    _assert_final_budget_deadline(context)
    sel = local_evidence.parse_local_selection_record(selection)
    exr = local_evidence.parse_local_execution_record(execution)
    if not sel.ok or sel.value is None or not exr.ok or exr.value is None:
        raise GateBlocked("final live selection/execution are not valid typed semantic records")
    disposition_state = _frozen({"disposition_ok": disposition_ok,
                                 "recovery_disposition_ok": recovery_disposition_ok})
    selection_state = _frozen(selection)
    execution_state = _frozen(execution)
    expectations_state = _frozen(expectations)
    action_evidence_state = _frozen(action_evidence)
    facts_state = _facts_state(facts)
    fingerprint = _terminal_live_fingerprint(
        context=context, expectations=expectations, action_evidence=action_evidence,
        facts_state=facts_state, execution_state=execution_state,
        selection_state=selection_state, disposition_state=disposition_state)
    return _FinalAuthority(
        context, selection, execution, sel.value, exr.value, context_state,
        expectations_state, action_evidence_state, facts_state, selection_state,
        execution_state, disposition_state, fingerprint)


def _assert_final_authority(
        project: pathlib.Path, gate: gates.Gate, source: LocalGateSource,
        claim_id: str, facts: GateFacts, verified: _LocalVerified,
        sample: TerminalSample, live_fingerprint: str,
        callback_states: Mapping[str, tuple[str, ...]], gate_bytes: bytes,
        expected_action: BoundAction, receipt: str | None, pre_apply: bool,
        root: pathlib.Path, strict_selection, strict_execution,
        strict_shapes: tuple[tuple[object, ...], ...], phase: str,
        owner: "TerminalOwnerState", owner_ref: object, pinned_id: int,
        base_generation: int, cell: "ControlledAuthorityCell | None",
        writer_pin: _WriterPin, writer_pin_state: tuple) -> None:
    """Complete, finite, local-only authorization check after the LAST callback.

    T08-A-R4: the host producer's complete terminal sample (captured after the
    last mutation-capable callback) is the ONLY source of host context,
    expectations, disposition and action-result facts here. No host callback is
    made in this function; the independently re-derived live fingerprint is
    passed in. Bounded best effort, not OS-level atomicity/TOCTOU elimination.
    """
    # T08-A-R8: after ALL permitted callbacks completed, close BOTH comparison
    # sides and every later operand in ONE exact pass. No sample/Path/user leaf
    # is read after this closure: the old checks below operate on exact clones.
    if cell is None:
        raise GateBlocked("missing controlled producer-owner storage")
    if type(owner) is not TerminalOwnerState:
        raise GateBlocked("owner carrier is not the exact controlled type")
    owner_live = object.__getattribute__(owner, "live")
    owner_pinned = object.__getattribute__(owner, "pinned_id")
    if (type(owner_pinned) is not int or owner_live is None
            or owner_live is not owner_ref or id(owner_live) != pinned_id):
        raise GateBlocked("owner carrier live state was replaced or is stale")
    # R9: the durable writer pin is local to THIS consume and is never rebuilt
    # at a later terminal boundary. Validate raw callables before exact clones
    # turn them into identity tuples.
    _assert_pinned_exact_schemas()
    _assert_action_matches_pin(facts.action, writer_pin_state)
    _assert_action_matches_pin(expected_action, writer_pin_state)
    original_source = source
    # ALL clone/conversion/parse-like inputs are closed BEFORE the final live
    # capture. No clone runs after the association suffix.
    sample = _exact_sample(sample)
    source = _exact_source(source, cell, owner_ref)
    gate = _exact_clone(gate)
    facts = _exact_clone(facts)
    verified = _exact_clone(verified)
    live_fingerprint = _exact_clone(live_fingerprint)
    callback_states = _exact_clone(callback_states)
    gate_bytes = _exact_clone(gate_bytes)
    expected_action = _exact_clone(expected_action)
    receipt = _exact_clone(receipt)
    root = _exact_clone(root)
    project = _exact_clone(project)
    strict_selection = _exact_clone(strict_selection)
    strict_execution = _exact_clone(strict_execution)
    strict_shapes = _exact_clone(strict_shapes)
    for value, name in ((claim_id, "claim"), (phase, "phase"),
                        (live_fingerprint, "fingerprint"), (pinned_id, "pinned id"),
                        (base_generation, "generation")):
        if type(value) is not str and type(value) is not int:
            raise GateBlocked("final " + name + " is not an exact primitive")
    if type(pre_apply) is not bool:
        raise GateBlocked("final pre-apply flag is not an exact bool")
    if receipt is not None and type(receipt) is not str:
        raise GateBlocked("final receipt is not an exact primitive")
    # 0. Typed complete sample trust boundary. Source/phase identity, internal
    #    coherence and freshness against the host's current live state domain.
    if type(sample) is not TerminalSample:
        raise GateBlocked("missing complete trusted terminal sample")
    if (sample.source_key != source.key or sample.record_source != source.record_source
            or sample.task_key != source.task_key
            or sample.local_ref != source.decision_ref.local_ref
            or sample.gate_decision_ref != source.gate_decision_ref
            or sample.claim_id != claim_id or sample.phase != phase):
        raise GateBlocked("terminal sample is not bound to this source and phase")
    if sample.state_fingerprint != _terminal_live_fingerprint(
            context=sample.context, expectations=sample.expectations,
            action_evidence=sample.action_evidence, facts_state=sample.facts_state,
            execution_state=sample.execution_state, selection_state=sample.selection_state,
            disposition_state=sample.disposition_state):
        raise GateBlocked("terminal sample is internally incoherent")
    if sample.state_fingerprint != live_fingerprint:
        raise GateBlocked("terminal sample is stale or incoherent with live host state")
    if sample.disposition_state == "none" or sample.disposition is None:
        raise GateBlocked("terminal sample lacks a real disposition")
    if sample.facts_state != _facts_state(facts) or sample.facts_state != verified.facts_state:
        raise GateBlocked("terminal sample facts are not the final observed facts")

    # 1. Full live authorization re-evaluation: real PM index/claim, config,
    #    policy, machine checks, current authority and usage/spend.
    _check_facts(project, source.key, claim_id, gate, facts)
    if _authority_projection(project, source.key, claim_id, gate, facts) != verified.authority_state:
        raise GateBlocked("final gate authorization state changed after the last host callback")
    if _facts_state(facts) != verified.facts_state:
        raise GateBlocked("final host facts changed after the last host callback")

    # 2. Existing bindings revalidated from the SAMPLE's fresh immutable values.
    if (_validate_expectations(gate, source, claim_id, sample.expectations) != verified.expectations_state
            or sample.expectations.effect_state != "known"):
        raise GateBlocked("final host expectations changed after the last host callback")
    if _validate_context(sample.context, sample.expectations, source, claim_id) != verified.context_state:
        raise GateBlocked("final host context, stop or budget changed after the last host callback")
    # T08-A-R3-D: the final host callback can finish AFTER the existing finite
    # deadline. Re-run the frozen reader's real current-clock predicate after
    # that callback, before reservation/apply; shape/equality alone is not a
    # clock check. No new host callback or frozen-file edit is made here.
    _assert_final_budget_deadline(sample.context)
    contexts = callback_states.get("contexts", ())
    if not contexts or contexts[-1] != verified.context_state:
        raise GateBlocked("final strict current_context callback saw a different host context")
    evidences = callback_states.get("evidence", ())
    expected_evidence = _frozen(local_evidence.ActionResultEvidence(
        action_receipt_ref=verified.execution.action_ref,
        result_receipt_ref=verified.execution.result_ref,
        verifier_receipt_ref=verified.execution.verified_by,
        observed_object_digest=verified.execution.target_digest,
        confirmed=True))
    if not evidences or any(item != expected_evidence for item in evidences):
        raise GateBlocked("strict verify_execution callbacks saw different action evidence")
    if _frozen(sample.action_evidence) != expected_evidence:
        raise GateBlocked("terminal sample action evidence does not match strict action evidence")

    # 3. Bounded action plus the SAME physical/semantic package after the last
    #    callback; gate bytes, object bytes and receipt are local reads only.
    action = facts.action
    if action is None or not str.__eq__(_frozen(action), _frozen(expected_action)):
        raise GateBlocked("final bounded action changed")
    if sample.action_identity != (expected_action.name,
                                  _exact_path_string(expected_action.object_path),
                                  expected_action.legacy_closure,
                                  expected_action.lifecycle_action):
        raise GateBlocked("terminal sample bounded action changed")
    read = _assert_terminal_physical(root, source, verified, strict_selection,
                                     strict_execution, strict_shapes)
    if (sample.selection != strict_selection or sample.execution != strict_execution
            or sample.selection_sha256 != read.selection_sha256
            or sample.execution_sha256 != read.execution_sha256):
        raise GateBlocked("terminal sample does not match the physical strict package")
    if (_validate_disposition(gate, source, sample.expectations, strict_selection,
                              strict_execution, read, receipt, sample.disposition)
            != verified.disposition_state):
        raise GateBlocked("final disposition no longer matches the physical package")
    try:
        if gate.path.read_bytes() != gate_bytes:
            raise GateBlocked("final gate bytes changed after the last host callback")
        target = _bounded_target(project, action)
        object_bytes = target.read_bytes()
    except OSError as exc:
        raise GateBlocked("final bounded object bytes could not be read back") from exc
    if object_bytes != verified.object_bytes:
        raise GateBlocked("final bounded object bytes changed")
    digest = "sha256:" + hashlib.sha256(object_bytes).hexdigest()
    if pre_apply and (digest != sample.context.target_digest or digest != verified.object_digest):
        raise GateBlocked("final pre-image object digest changed")
    if sample.object_digest != digest or sample.receipt != (receipt or ""):
        raise GateBlocked("terminal sample object digest or receipt changed")
    if sample.gate_identity != (gate.decision_ref, gate.matter_ref,
                                gate.substantive_version, gate.business, gate.pm_note):
        raise GateBlocked("terminal sample gate identity changed")
    if receipt:
        relpath, separator, sha = receipt.partition("#")
        if (not separator or relpath != target.relative_to(project).as_posix()
                or digest != "sha256:" + sha):
            raise GateBlocked("final object bytes no longer match the receipt")

    # ── T08-A-R5: FINAL authority = non-delegating local reads of the pinned ──
    # T08-A-R6: FINAL authority = ONE real producer/consumer owner + a
    # non-delegating COMPLETE final domain, taken AFTER every permitted host
    # callback (producer sample AND the virtual fingerprint, including any late
    # in-place mutation / attribute / owner replacement inside them) COMPLETED.
    # Bounded best effort (single-threaded), NOT a new OS-atomicity/TOCTOU claim.
    # R8: identity checks already ran in the exact closure above. The cell and
    # complete live domain were captured BEFORE the first final comparison; no
    # host getter, raw-dict slot, owner attribute or sample leaf is read here.
    if owner_live is None:
        raise GateBlocked("owner carrier has no live state")
    # ── R10S PHASE 1 (prepare, BEFORE the final association/value suffix): ONE
    # non-delegating native live-domain read + complete recursive exact closure
    # / normalize / Path rebuild / fingerprint, the bounded native recheck
    # snapshot, the exact clone, and ALL materialize / parse / freeze in
    # _capture_final_authority. Every detached exact value is prepared here,
    # while the association is NOT yet trusted; any still-possible user protocol
    # therefore runs BEFORE the association is pinned. No clone/parse/Path runs
    # after the suffix below. ──
    _assert_pinned_exact_schemas()
    raw_domain, prepared_tree = _read_controlled_domain(owner_ref)
    held_snapshot = _native_recheck_snapshot(raw_domain)
    detached_domain = _exact_clone(raw_domain)
    domain = _capture_final_authority(detached_domain, source, claim_id)
    final_context = domain.context   # exact, detached, live-matched below

    # comparisons ONLY: immutable values, no owner attribute/container access
    # and no user delegation after an earlier field was validated. Post-sample
    # mutations (late expectations/evidence/facts/disposition/ctx, F1/F2-ctx/F3)
    # change the freshly re-derived live fingerprint while
    # sample.state_fingerprint == live_fingerprint are truthful pre-callback.
    if (domain.state_fingerprint != sample.state_fingerprint
            or domain.state_fingerprint != live_fingerprint):
        raise GateBlocked("final complete live authority domain changed after the last callback")
    if domain.context_state != verified.context_state:
        raise GateBlocked("final live host context, stop or budget changed after the last callback")
    if domain.expectations_state != verified.expectations_state:
        raise GateBlocked("final live host expectations changed after the last callback")
    if domain.action_evidence_state != _frozen(sample.action_evidence):
        raise GateBlocked("final live host action evidence changed after the last callback")
    if domain.facts_state != verified.facts_state:
        raise GateBlocked("final live host facts changed after the last callback")
    if domain.disposition_state != sample.disposition_state:
        raise GateBlocked("final live disposition condition changed after the last callback")
    # Pre-sample live typed drift (R5 F2) bound to the SAME strict physical
    # package by these kept complete typed-field checks, now fed by the exact-
    # dict non-delegating capture rather than a delegating getattr/parse.
    sel_value, exr_value = domain.selection_typed, domain.execution_typed
    if sel_value != strict_selection or exr_value != strict_execution:
        raise GateBlocked("final live selection/execution drifted from the strict physical package")
    d = sample.disposition
    if (exr_value.source != source.record_source
            or exr_value.local_ref != source.decision_ref.local_ref
            or exr_value.effect_state != "known"
            or exr_value.effect_state != d.effect_state
            or exr_value.action_ref != d.action_ref
            or exr_value.result_ref != d.result_ref
            or exr_value.verified_by != d.verifier_receipt_ref
            or exr_value.target_digest != sample.context.target_digest
            or exr_value.budget_ref != sample.expectations.budget_ref
            or d.selection_sha256 != read.selection_sha256
            or d.execution_sha256 != read.execution_sha256
            or sel_value.source != source.record_source
            or sel_value.local_ref != source.decision_ref.local_ref
            or sel_value.matter_ref != sample.expectations.matter_ref
            or sel_value.matter_version != sample.expectations.substantive_version
            or sel_value.material_digest != sample.expectations.material_digest
            or sel_value.basis_digest != sample.expectations.basis_digest
            or sel_value.selected_action != sample.expectations.selected_action
            or sel_value.selected_basis_id != sample.expectations.selected_basis_id
            or sel_value.budget_ref != sample.expectations.budget_ref):
        raise GateBlocked("final live typed fields are not bound to the strict physical package")

    # ── R10S PHASE 2: FINAL native association/value suffix, executed LAST.
    # Re-reads the ORIGINAL live source/host/cell/owner associations, native
    # slots, exact-type-guarded writer-pin identity and the complete live domain
    # VALUES; compares with the held prepared exact projection/snapshot. Purely
    # native reads + closed comparisons: NO clone/parse/normalize/Path rebuild/
    # getattr/user protocol inside or after this suffix. ──
    _final_native_suffix(original_source, owner_ref, cell, base_generation,
                         writer_pin, writer_pin_state, prepared_tree, held_snapshot)
    # ── R10S PHASE 3: the ONLY permitted post-suffix exceptional helper: the
    # frozen real current-clock predicate over the already-detached, fully
    # exact materialized context whose values the suffix just matched against
    # the final live domain. validate_matter_budget/_deadline_passed are the
    # unchanged frozen reader; the clock check is preserved, not deleted. ──
    _assert_final_budget_deadline(final_context)


def _bounded_target(project: pathlib.Path, action: BoundAction) -> pathlib.Path:
    target = (project / action.object_path).resolve()
    if (target == project or not target.is_relative_to(project) or action.object_path.is_absolute()
            or target != project / action.object_path):
        raise GateBlocked("bounded target must be project-relative")
    return target


def _object_digest(project: pathlib.Path, action: BoundAction) -> str:
    """Real pre-image digest of the bounded object (host expectation anchor)."""
    target = _bounded_target(project, action)
    if not target.is_file():
        raise GateBlocked("bounded target is not a regular file")
    digest = hashlib.sha256()
    with target.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return "sha256:" + digest.hexdigest()


def _receipt(project: pathlib.Path, action: BoundAction, gate: gates.Gate) -> str | None:
    target = _bounded_target(project, action)
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


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _stable(value: object) -> str:
    try:
        return json.dumps(value, sort_keys=True, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return "<non-json:" + type(value).__name__ + ">"


def _verify_local(project: pathlib.Path, gate: gates.Gate, source: LocalGateSource,
                  claim_id: str, facts: GateFacts, *, receipt: str | None,
                  pre_apply: bool, authority_state: str) -> _LocalVerified:
    """Strict T03 reader + independent host context/callback for a local source.

    No DP DecisionMeta/request/answer/lifecycle is constructed or written. All
    identity, parent, material, basis, budget, execution and disposition facts
    are re-verified against the CURRENT host binding and real files.
    """
    ref = source.decision_ref
    if not isinstance(ref, local_evidence.LocalDecisionRef) or ref.kind != "local" or not _nonblank(ref.local_ref):
        raise GateBlocked("missing discriminated local decision ref")
    parsed_ref = local_evidence.parse_decision_ref({"kind": ref.kind, "local_ref": ref.local_ref})
    if not parsed_ref.ok or not isinstance(parsed_ref.value, local_evidence.LocalDecisionRef):
        raise GateBlocked("invalid frozen local decision ref")
    if ref.local_ref.startswith("dp-"):
        raise GateBlocked("a DP-shaped local_ref is not a local decision")
    if source.record_source not in local_evidence.LOCAL_SOURCES:
        raise GateBlocked("unknown local record source")
    if not _nonblank(source.key):
        raise GateBlocked("missing host-bound key")
    if source.task_key is not None and not _nonblank(source.task_key):
        raise GateBlocked("invalid host-bound task key")
    canonical_ref = "local(" + ref.local_ref + ")"
    if source.gate_decision_ref != canonical_ref:
        raise GateBlocked("gate decision ref is not the host-issued local ref")
    if not isinstance(source.host, LocalGateHost):
        raise GateBlocked("missing trusted local gate host")
    root = pathlib.Path(source.agenticdoc_root)
    if root.resolve() != (project / ".agenticdoc").resolve():
        raise GateBlocked("local evidence root is not this project")
    if gate.decision_ref != source.gate_decision_ref or gate.key not in (None, source.key):
        raise GateBlocked("gate is not bound to this local decision and key")
    if gate.business != "approve":
        raise GateBlocked("local gate release requires an approve business choice")
    if facts.action is None:
        raise GateBlocked("no host-bound object action for local evidence")

    expectations = source.host.gate_expectations(gate)
    expectations_state = _validate_expectations(gate, source, claim_id, expectations)
    ctx = source.host.current_context()
    context_state = _validate_context(ctx, expectations, source, claim_id)
    binding = ctx.binding

    selection, execution, strict_shapes = _strict_pair(root, source)
    read = local_evidence.read_local_evidence(
        root, source.key, source.record_source, ref.local_ref, task_key=source.task_key)
    if not (read.ok and read.selection is not None and read.execution is not None
            and read.selection_sha256 and read.execution_sha256 and read.snapshot is not None
            and not read.recovery_clues and not read.failure_codes):
        raise GateBlocked("physical local selection and execution evidence is incomplete")
    physical_shape = _read_shape(read)
    if any(observed != physical_shape for observed in strict_shapes):
        raise GateBlocked("strict host callbacks did not observe the final physical snapshot")
    if read.selection != selection or read.execution != execution:
        raise GateBlocked("strict semantic records and physical records diverged")
    selection_bytes, execution_bytes = _physical_bytes(read)
    try:
        object_path = _bounded_target(project, facts.action)
        object_bytes = object_path.read_bytes()
    except OSError as exc:
        raise GateBlocked("bounded object bytes could not be read back") from exc
    object_digest = "sha256:" + hashlib.sha256(object_bytes).hexdigest()
    if pre_apply and ctx.target_digest != object_digest:
        raise GateBlocked("current object does not match the verified execution target")

    def same(actual: object, expected: object, label: str) -> None:
        if actual != expected:
            raise GateBlocked("local record " + label + " does not match the host expectation")

    same(selection.local_ref, ref.local_ref, "local_ref")
    same(selection.source, source.record_source, "source")
    same(selection.matter_ref, expectations.matter_ref, "matter_ref")
    same(selection.matter_version, expectations.substantive_version, "matter_version")
    same(selection.material_digest, expectations.material_digest, "material_digest")
    same(selection.basis_digest, expectations.basis_digest, "basis_digest")
    same(selection.selected_action, expectations.selected_action, "selected_action")
    same(selection.selected_basis_id, expectations.selected_basis_id, "selected_basis_id")
    same(selection.budget_ref, expectations.budget_ref, "budget_ref")
    same(selection.action_state, "planned", "action_state")
    same(selection.business_completed, False, "business_completed")
    same(selection.selected_action, facts.matter.action, "matter action")
    same(selection.selected_action, facts.action.name, "bound action")
    same(selection.host_binding.claim_id, binding.claim_id, "selection claim")
    same(selection.host_binding.key, source.key, "selection key")
    same(selection.host_binding.owner, binding.owner, "selection owner")
    same(selection.host_binding.role, binding.role, "selection role")
    same(selection.host_binding.task_key, source.task_key, "selection task")
    same(selection.host_binding.run_id, binding.run_id, "selection run")
    same(selection.host_binding.binding_version, binding.binding_version, "selection binding version")
    if expectations.parent_decision_ref is None:
        if selection.parent_decision_ref is not None:
            raise GateBlocked("unexpected parent decision ref on local selection")
    elif not (isinstance(selection.parent_decision_ref, local_evidence.DpDecisionRef)
              and _stable({"kind": "dp", "decision_id": selection.parent_decision_ref.decision_id})
              == _stable(expectations.parent_decision_ref)):
        raise GateBlocked("local selection parent does not match the host expectation")

    same(execution.local_ref, ref.local_ref, "execution local_ref")
    same(execution.source, source.record_source, "execution source")
    same(execution.budget_ref, expectations.budget_ref, "execution budget_ref")
    same(execution.action_ref, expectations.action_ref, "action_ref")
    same(execution.result_ref, expectations.result_ref, "result_ref")
    same(execution.verified_by, expectations.verifier_ref, "verified_by")
    if expectations.effect_state != "known":
        raise GateBlocked("host expected effect state is not a releasable known effect")
    same(execution.effect_state, "known", "effect_state")
    same(execution.effect_state, expectations.effect_state, "expected effect_state")
    same(execution.observed_effect, expectations.observed_effect, "observed_effect")
    same(execution.target_digest, ctx.target_digest, "target_digest")

    disposition = source.host.verify_disposition(gate, selection, execution, receipt)
    disposition_state = _validate_disposition(
        gate, source, expectations, selection, execution, read, receipt, disposition)
    return _LocalVerified(
        selection, execution, expectations, ctx, disposition,
        read.selection_sha256, read.execution_sha256,
        physical_shape, strict_shapes, selection_bytes, execution_bytes,
        object_bytes, object_digest, expectations_state, context_state,
        disposition_state, _facts_state(facts), authority_state)


def _terminal_local(project: pathlib.Path, live_gate: gates.Gate, source: LocalGateSource,
                    claim_id: str, observe: Callable[[gates.Gate], GateFacts],
                    expected_action: BoundAction, verified: _LocalVerified, *,
                    writer_pin: _WriterPin, writer_pin_state: tuple,
                    receipt: str | None, pre_apply: bool, phase: str) -> None:
    """Rebuild the complete terminal boundary after the last application callback.

    T08-A-R2: every host callback belongs to the fixed finite schedule below.
    The LAST one is a single ``observe``; after it only bounded local reads and
    comparisons against immutable projections run. No host callback follows the
    final authorization check, so a change made inside the final
    verify_execution / final current_context / final observe window cannot reach
    reservation/apply unexamined. Bounded best effort, not OS-level atomicity.
    """
    root = pathlib.Path(source.agenticdoc_root)
    # T08-A-R5: pin the consumer/source-owned authoritative live state owner
    # BEFORE any terminal host callback and hold it locally for this boundary.
    source_raw = _native_instance_storage(source, protected=(
        "owner_state", "authority_cell", "host"))
    owner_ref = dict.__getitem__(source_raw, "owner_state")
    pinned_id = id(owner_ref)
    owner = TerminalOwnerState(live=owner_ref, pinned_id=pinned_id)
    cell = dict.__getitem__(source_raw, "authority_cell")
    base_generation = (dict.__getitem__(_read_cell_state(cell), "_generation")
                       if cell is not None else 0)
    try:
        gate_bytes = live_gate.path.read_bytes()
        parsed_gate = gates.parse(live_gate.path)
    except Exception as exc:
        raise GateBlocked("terminal gate could not be read back") from exc
    if (parsed_gate != live_gate or parsed_gate.id != live_gate.id
            or parsed_gate.decision_ref != source.gate_decision_ref):
        raise GateBlocked("terminal gate identity changed")

    # ── finite host-callback schedule; all real, none trusted by reference ──
    fresh = observe(live_gate)
    _check_facts(project, source.key, claim_id, live_gate, fresh)
    if _facts_state(fresh) != verified.facts_state:
        raise GateBlocked("terminal host facts changed")
    if fresh.action is None:
        raise GateBlocked("terminal host action is missing")
    _assert_action_matches_pin(fresh.action, writer_pin_state)
    _assert_action_matches_pin(expected_action, writer_pin_state)
    expectations = source.host.gate_expectations(live_gate)
    if (_validate_expectations(live_gate, source, claim_id, expectations)
            != verified.expectations_state or expectations.effect_state != "known"):
        raise GateBlocked("terminal host expectations changed")
    context = source.host.current_context()
    if _validate_context(context, expectations, source, claim_id) != verified.context_state:
        raise GateBlocked("terminal host context, stop or budget changed")
    if pre_apply and context.target_digest != verified.object_digest:
        raise GateBlocked("terminal pre-image target digest changed")
    if receipt and _receipt(project, expected_action, live_gate) != receipt:
        raise GateBlocked("terminal object receipt no longer matches")
    callback_states: dict = {}
    strict_selection, strict_execution, strict_shapes = _strict_pair(
        root, source, callback_states)
    # Re-read the host context AFTER the strict pair's last current_context
    # callback; a callback that replaced the host's context in place is caught
    # here, before the final authorization boundary.
    context_after_strict = source.host.current_context()
    if _validate_context(context_after_strict, expectations, source, claim_id) != verified.context_state:
        raise GateBlocked("post-strict host context, stop or budget changed")

    # LAST MUTATION-CAPABLE host callback. Everything after it is read-only.
    final_facts = observe(live_gate)
    _assert_action_matches_pin(final_facts.action, writer_pin_state)
    # T08-A-R4: the trusted producer reads the COMPLETE current host state after
    # that completed callback. It is the last host callback; the consumer then
    # re-derives the host's live-state fingerprint once, and the final authority
    # check is purely local. No stale getter reference is consulted afterwards.
    request = TerminalRequest(
        gate=live_gate, source=source, claim_id=claim_id, phase=phase,
        facts=final_facts, selection=strict_selection, execution=strict_execution,
        receipt=receipt, object_digest=verified.object_digest, owner=owner)
    sample = source.host.terminal_sample(request)
    live_fingerprint = source.host.terminal_state_fingerprint()
    # The last permitted mutation-capable callback stays in the fixed finite
    # schedule (original callback paths are preserved). T08-A-R7: its virtual
    # return value is NO LONGER an authority source; the controlled cell below
    # independently verifies the real producer owner slot and the complete exact
    # final domain after this callback has fully completed.
    source.host.authority_owner()
    _assert_final_authority(
        project, live_gate, source, claim_id, final_facts, verified,
        sample, live_fingerprint, callback_states, gate_bytes, expected_action,
        receipt, pre_apply, root, strict_selection, strict_execution, strict_shapes, phase,
        owner, owner_ref, pinned_id, base_generation, cell,
        writer_pin, writer_pin_state)


def consume_gate(project_root: pathlib.Path, gate_id: str, *,
                 claim_id: str, observe: Callable[[gates.Gate], GateFacts],
                 store: lifecycle.LifecycleStore | None = None,
                 meta: lifecycle.DecisionMeta | None = None,
                 source: LocalGateSource | None = None) -> GateEffectResult:
    """Observe the registered operation, reserve its matter and verify its real effect.

    A steer/fix result identifies the parent and target for the existing PM
    follow-up producer. No successor request is implied here. A rejected plan
    has no action unless the prepared object explicitly binds legacy closure.

    ``source`` is the ONLY source discriminator. A host-bound ``LocalGateSource``
    selects the strict local-evidence branch; ``None`` keeps the original DP
    branch (bound by ``store``/``meta``) byte-for-byte. Gate text, prefixes or a
    ``source=pm`` string never select a branch or grant authority.
    """
    project = pathlib.Path(project_root).resolve()
    if not isinstance(gate_id, str) or not gates.GATE_ID_RE.fullmatch(gate_id):
        return GateEffectResult("blocked", "invalid gate ID")
    local = source is not None
    if local and not isinstance(source, LocalGateSource):
        return GateEffectResult("blocked", "unbound decision source")
    if not local and (store is None or meta is None):
        return GateEffectResult("blocked", "a bound production ledger and PM identity are required")
    directory = project / ".agenticdoc" / "_autopilot" / "gates"
    path = directory / (gate_id + ".md")
    gate_lock = project / ".mw" / "gates.lock"
    reserved = False
    authority_state = ""
    writer_pin = None
    writer_pin_state = None
    pinned_action = None
    try:
        if path.resolve() != path or not gate_lock.resolve().is_relative_to(project):
            raise GateBlocked("gate or lock path is redirected")
        initial = gates.parse(path)
        if initial.historical or initial.transport != "answered":
            raise GateBlocked("historical or unanswered gate")
        if local:
            if initial.key not in (None, source.key) or initial.decision_ref != source.gate_decision_ref:
                raise GateBlocked("decision and bound local identity do not match the gate")
            host_key = source.key
            # R9: durable independent writer identity BEFORE the first observe or
            # any other mutation-capable host callback. Reused across boundaries.
            writer_pin, writer_pin_state = _writer_pin_for_source(source)
            pinned_action = _make_pinned_action(writer_pin_state)
        else:
            if (store.scope_kind != "production" or store.sink.resolve() != wire.production_lifecycle_sink(project)
                    or store.project_id != wire.project_id_for(project)):
                raise GateBlocked("a bound production ledger in this project is required")
            if (meta.initiator_role != "pm" or initial.key not in (None, meta.key)
                    or initial.decision_ref != "dp-gate-approve:" + meta.logical_id):
                raise GateBlocked("decision and bound PM identity do not match the gate")
            host_key = meta.key
        matter_lock = hashlib.sha256(initial.matter_ref.encode()).hexdigest()
        with _lock(project / ".mw" / f"matter-{matter_lock}.lock"):
            with _lock(gate_lock):
                gate = gates.parse(path)
                if gate != initial or gate.id != gate_id:
                    raise GateBlocked("gate changed before reservation")
                rows: list[dict] = []
                if not local:
                    rows = _ledger_rows(store, meta, gate)
                facts = observe(gate)
                granted = _check_facts(project, host_key, claim_id, gate, facts)
                if local:
                    _assert_action_matches_pin(facts.action, writer_pin_state)
                    # Immutable authorization baseline BEFORE any host callback.
                    # A final strict callback cannot rewrite this string.
                    authority_state = _authority_projection(
                        project, host_key, claim_id, gate, facts)
                    _verify_local(project, gate, source, claim_id, facts, receipt="",
                                  pre_apply=False, authority_state=authority_state)
                peers = [g for g in gates.enumerate(directory) if g.matter_ref == gate.matter_ref]
                if any(g.substantive_version != gate.substantive_version and g.effect in ("in-progress", "unknown") for g in peers):
                    raise GateBlocked("an earlier version has an unresolved effect")
                same = [g for g in peers if g.substantive_version == gate.substantive_version and g.transport == "answered"]
                if any(g.decision_ref != gate.decision_ref or g.business != gate.business for g in same):
                    raise GateBlocked("conflicting approvals for the same substantive matter")
                action = pinned_action if local else facts.action
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
                common: dict = {}
                event_prefix = ""
                consumed_id = ""
                executed_id = ""
                settled_id = ""
                execution: dict = {}
                if not local:
                    common = dict(store=store, meta=meta, decision_id=gate.decision_ref, dp="dp-gate-approve",
                                  actor=("system", claim_id))
                    event_prefix = "gate-" + hashlib.sha256(gate.decision_ref.encode()).hexdigest()
                    consumed_id = event_prefix+"-consumed"
                    consumed = lifecycle.record_consumed(**common, answer=gate.business, event_id=consumed_id)
                    if not consumed.recorded or (consumed.status == "duplicate" and not _has_event(
                            rows, consumed_id, kind="lifecycle", lifecycle="consumed", answer=gate.business, actor=actor)):
                        raise GateBlocked("could not record decision consumption")
                if gate.business in ("steer", "need_fix") or (gate.business == "reject" and action is None):
                    if local:
                        raise GateBlocked("local gate release requires an approve business choice")
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
                receipt = _receipt(project, pinned_action if local else action, gate)
                if not local:
                    executed_id, settled_id = event_prefix+"-executed", event_prefix+"-settled"
                    execution = dict(kind="lifecycle", lifecycle="executed", action=action.lifecycle_action, reason=action.name, actor=actor)
                if recovering and receipt is None:
                    if gate.effect == "in-progress":
                        _replace_effect(gate, "unknown")
                    return GateEffectResult("unknown", "actual target does not prove the reserved effect", gate.decision_ref)
                if plan.status == "already-applied":
                    if local:
                        try:
                            verified = _verify_local(project, gate, source, claim_id, facts,
                                                     receipt=receipt, pre_apply=False,
                                                     authority_state=authority_state)
                            _terminal_local(project, gate, source, claim_id, observe,
                                            pinned_action if local else action, verified,
                                            writer_pin=writer_pin, writer_pin_state=writer_pin_state,
                                            receipt=receipt, pre_apply=False, phase="recovery")
                        except GateBlocked as exc:
                            return GateEffectResult("unknown", "local applied state lacks verified evidence: " + str(exc),
                                                    gate.decision_ref, receipt=receipt, duplicate=True)
                    else:
                        if (not _has_event(rows, executed_id, **execution, result=receipt)
                                or not _has_event(rows, settled_id, kind="lifecycle", lifecycle="settled", outcome="ok", reason=receipt, actor=actor)):
                            raise GateBlocked("applied marker lacks the matching executed and settled receipts")
                    return GateEffectResult("applied", "already recorded", gate.decision_ref, receipt=receipt, duplicate=True)
                if not recovering:
                    if receipt is not None:
                        raise GateBlocked("object already changed without this gate's reservation")
                    if not local:
                        if any(r.get("lifecycle") == "executed" or r.get("event_id") == settled_id for r in rows):
                            raise GateBlocked("existing execution record conflicts with unreserved gate")
                    # Object inspection can outlive an authorization/claim or
                    # change a target version. Resolve the live host binding
                    # once more immediately before recording the intent.
                    fresh = observe(gate)
                    _check_facts(project, host_key, claim_id, gate, fresh)
                    if local:
                        _assert_action_matches_pin(fresh.action, writer_pin_state)
                    elif (fresh.action is None or fresh.action.object_path != action.object_path
                            or fresh.action.name != action.name or fresh.action.legacy_closure != legacy
                            or fresh.action.lifecycle_action != action.lifecycle_action or fresh.scope != facts.scope):
                        raise GateBlocked("bounded action changed during preparation")
                    if fresh.scope != facts.scope:
                        raise GateBlocked("bounded action changed during preparation")
                    action = pinned_action if local else fresh.action
                    if local:
                        verified = _verify_local(project, gate, source, claim_id, fresh,
                                                 receipt="", pre_apply=True,
                                                 authority_state=authority_state)
                        _terminal_local(project, gate, source, claim_id, observe, pinned_action,
                                        verified, writer_pin=writer_pin, writer_pin_state=writer_pin_state,
                                        receipt="", pre_apply=True, phase="pre")
                    _replace_effect(gate, "in-progress")
                    reserved = True
            # The matter lock serializes consumers. Release the shared gates lock
            # before the object's own bounded write; no model or queue wait here.
            refused = False
            error = ""
            if not recovering:
                try:
                    (writer_pin_state[2] if local else action.apply)(gate)
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
                receipt = _receipt(project, pinned_action if local else action, current)
                if receipt is None:
                    if refused:
                        if local:
                            # Precise gap: the frozen local API has no DP-style
                            # settled row. The controlled gate effect writer is
                            # the only legal record for a refused CAS here.
                            _replace_effect(current, "failed")
                            return GateEffectResult("failed", "target CAS refused without a write", gate.decision_ref)
                        if not lifecycle.record_settled(**common, outcome="inconclusive", reason="target CAS refused",
                                event_id=event_prefix+"-cas-refused").recorded:
                            return GateEffectResult("unknown", "target refusal lacks settlement evidence", gate.decision_ref)
                        _replace_effect(current, "failed")
                        return GateEffectResult("failed", "target CAS refused without a write", gate.decision_ref)
                    _replace_effect(current, "unknown")
                    return GateEffectResult("unknown", f"actual target receipt unavailable{error}; inspect before retry", gate.decision_ref)
                if local:
                    try:
                        verified = _verify_local(project, gate, source, claim_id, facts,
                                                 receipt=receipt, pre_apply=False,
                                                 authority_state=authority_state)
                        _terminal_local(project, current, source, claim_id, observe, pinned_action,
                                        verified, writer_pin=writer_pin, writer_pin_state=writer_pin_state,
                                        receipt=receipt, pre_apply=False, phase="post")
                    except GateBlocked as exc:
                        _replace_effect(current, "unknown")
                        return GateEffectResult("unknown", "local terminal boundary is unknown: " + str(exc),
                                                gate.decision_ref, receipt=receipt)
                else:
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
