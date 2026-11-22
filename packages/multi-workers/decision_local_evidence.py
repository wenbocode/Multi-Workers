"""T03 — strict, read-only Python local-evidence reader (schema v1).

PURE MODULE BOUNDARY — read before using any API below:

* This module is the *Python* counterpart of the frozen TS pure contract
  ``shared/decision-handoff.ts`` (schema v1, source SHA
  ``92ae0276...badd04``).  It mirrors the frozen field lists / closed sets /
  parse semantics *byte-for-byte* (see ``SCHEMA_V1``); it does NOT port the
  TS free-text feedback classifier / transport-reason interpreter.
* It has three clearly separated layers:

  1. **Pure parse** (``parse_*``): shape-only.  Every success carries
     ``verification="shape-only"`` and ``host_source_verified=False``.  A
     correct JSON shape proves NOTHING about the real host source.  Unknown
     input is always ``object`` (never trusted by static type); duplicate JSON
     keys, non-finite numbers, Python ``bool``-as-``int``, unknown keys and
     DP-impersonation keys are rejected.
  2. **Read-only load** (``read_local_evidence``): derives the frozen physical
     path, refuses traversal / redirect / wrong file kind / bad JSON /
     duplicate keys / unstable snapshots / present locks, reads the record and
     parses it.  Still ``host_source_verified=False``: a safe file is not a
     live-host proof.  It NEVER writes: no directories, no locks, no records,
     no repair/overwrite of an invalid-existing file.
  3. **Strict verify** (``strict_verify``): the ONLY path that can yield
     ``host_source_verified=True``.  It requires a real *trusted host adapter*
     (``HostEvidenceAdapter``) supplying the CURRENT authoritative binding
     (unique active exact-self row, not ``_index.md``/latest/global) and the
     CURRENT expected matter/material/basis/parent/budget/target, plus real
     action/result/target-verifier evidence for execution.  Missing adapter /
     context / verifier FAILS CLOSED (never verified).  A passed owner string,
     a model self-report, mere file existence, or a boolean self-proof are
     never provenance.

* ``source`` (``pm``/``worker-local``), ``owner``, ``local_ref`` and
  ``decision_id`` are DATA, not capabilities.  A ``local_ref`` is NEVER a
  decision id and NEVER enters a DP receipt / ``available`` / model count.
  ``DecisionRef`` is discriminated (``dp`` | ``local``), never a string prefix.
* This reader grants no permission, does not implement scheduling
  reservation / ledger / execution actions, and does not replace a human-only
  gate, an independent review/QG, or the unique sign CLI.  It is a strict
  reader *primitive* for later host integration (T07/T08); production adapter
  wiring is NOT done here (see ``HostEvidenceAdapter``).  Tests inject a fake
  adapter in an isolated real-file harness — that is L1, not a product L2 VC.

Physical naming (PM integration clarification, contract-freeze-20261112.md):
the full non-empty logical ref's UTF-8 bytes are encoded with canonical
RFC4648 base64url WITHOUT padding.  PM base is
``<agenticdocRoot>/<key>/evidence/decision-handoffs/``; worker-local base is
``<agenticdocRoot>/<key>/workers/<task_key>/local-decisions/`` (bound to the
current task AND run; another run's file is a recovery clue only).  A selection
is ``<encoded>.json``; an execution is ``<encoded>.execution.json`` (same
``local_ref``, physically separate).
"""

from __future__ import annotations

import abc
import base64
import datetime as _dt
import hashlib
import json
import math
import os
import pathlib
import re
import stat
from dataclasses import dataclass
from typing import Generic, TypeVar

__all__ = [
    # schema identity / frozen closed sets / field lists
    "DECISION_HANDOFF_SCHEMA_VERSION",
    "DECISION_HANDOFF_SCHEMA_ID",
    "FEEDBACK_CATEGORIES",
    "EFFECT_STATES",
    "STOP_SCOPES",
    "PM_DISPOSITION_KINDS",
    "PM_DISPOSITION_STATUSES",
    "TOOL_NAMES",
    "READ_ONLY_TOOLS",
    "LOCAL_SOURCES",
    "HOST_ROLES",
    "EXECUTION_EFFECT_STATES",
    "FORBIDDEN_LOCAL_DP_FIELDS",
    "HOST_BINDING_FIELDS",
    "LOCAL_SELECTION_FIELDS",
    "LOCAL_EXECUTION_FIELDS",
    "MATTER_BUDGET_FIELDS",
    "HOST_IDENTITY_FIELDS",
    "DECISION_REF_KINDS",
    "AUTHORITATIVE_BINDING_KIND",
    "FAILURE_CODES",
    "SCHEMA_V1",
    # results
    "ContractIssue",
    "CheckItem",
    "ParseResult",
    "ReadResult",
    "StrictResult",
    # parsed records
    "HostBinding",
    "DpDecisionRef",
    "LocalDecisionRef",
    "LocalSelectionRecord",
    "LocalExecutionRecord",
    "MatterBudget",
    # trusted host boundary
    "TrustedBinding",
    "TrustedContext",
    "ActionResultEvidence",
    "HostEvidenceAdapter",
    "StrictJsonError",
    # helpers
    "is_json_value",
    "loads_strict_json",
    "encode_local_ref",
    # pure parse
    "parse_decision_ref",
    "route_decision_ref",
    "parse_host_binding",
    "parse_local_selection_record",
    "parse_local_execution_record",
    "validate_matter_budget",
    "parse_local_selection_json",
    "parse_local_execution_json",
    # read-only loader / strict verify
    "read_local_evidence",
    "strict_verify",
]

T = TypeVar("T")

# ── Schema identity (frozen, mirrors SCHEMA_V1 of decision-handoff.ts) ──────

DECISION_HANDOFF_SCHEMA_VERSION = 1
DECISION_HANDOFF_SCHEMA_ID = "decision-handoff/v1"

FEEDBACK_CATEGORIES = (
    "answer", "advisory", "service-unavailable", "input-gap", "uncertain-answer",
    "binding-invalid", "integrity-error", "authority-required", "effect-unknown",
    "cancelled", "budget-exhausted", "exemption", "unclassified",
)
EFFECT_STATES = ("none", "known", "unknown")
STOP_SCOPES = ("none", "service-request", "worker-run", "matter", "pm-or-key", "user-global", "unknown")
PM_DISPOSITION_KINDS = (
    "self-decide", "collect-evidence", "reconcile", "replan", "await-worker",
    "await-external", "stopped", "resource-limited",
)
PM_DISPOSITION_STATUSES = ("planned", "running", "observed", "superseded", "waiting", "stopped")
TOOL_NAMES = ("read", "find", "grep", "ls", "bash", "write", "edit", "dispatch")
READ_ONLY_TOOLS = ("read", "find", "grep", "ls")
LOCAL_SOURCES = ("pm", "worker-local")
HOST_ROLES = ("pm", "coding", "research", "review", "unknown")
EXECUTION_EFFECT_STATES = ("known", "unknown")

FORBIDDEN_LOCAL_DP_FIELDS = (
    "decision_id", "answers", "available", "business_decisions", "business_decision",
    "decision_lifecycle", "receipt", "request_ref", "model_called", "decision_ref",
)

HOST_BINDING_FIELDS = (
    "role", "owner", "claim_id", "key", "task_key", "run_id", "binding_version", "observed_at",
)
LOCAL_SELECTION_FIELDS = (
    "schema_version", "kind", "origin", "source", "local_ref", "parent_decision_ref",
    "feedback_ref", "matter_ref", "host_binding", "matter_version", "material_digest",
    "basis_digest", "selected_action", "selected_basis_id", "budget_ref", "action_state",
    "business_completed", "result_consumer", "created_at",
)
LOCAL_EXECUTION_FIELDS = (
    "schema_version", "kind", "origin", "source", "local_ref", "host_binding", "action_ref",
    "result_ref", "executor", "target_digest", "observed_effect", "effect_state",
    "verified_by", "budget_ref", "created_at",
)
MATTER_BUDGET_FIELDS = (
    "schema_version", "budget_ref", "matter_ref", "parent_matter_ref", "deadline",
    "max_steps", "no_progress_limit", "remaining_cost", "steps_consumed", "cost_consumed",
    "no_progress_count", "source_refs",
)
HOST_IDENTITY_FIELDS = ("owner", "role", "claim_id", "key", "task_key", "run_id", "binding_version")
DECISION_REF_KINDS = ("dp", "local")

#: The one accepted authoritative binding origin for strict verify.  A binding
#: taken from ``_index.md``/``latest``/``global``/model text is NOT this.
AUTHORITATIVE_BINDING_KIND = "unique-active-exact-self"

#: Concrete, documented failure codes.  A strict result NEVER invents one of
#: these into the frozen record JSON — they live only in the API result.
FAILURE_CODES = (
    "missing-trusted-adapter", "missing-trusted-context", "non-authoritative-binding",
    "binding-not-unique", "binding-not-active", "binding-drift", "source-role-mismatch",
    "worker-not-current-run", "matter-drift", "matter-version-drift", "material-drift",
    "basis-drift", "parent-drift", "budget-ref-drift", "missing-budget", "invalid-budget",
    "budget-exhausted", "scope-stop", "missing-selection", "selection-mismatch",
    "missing-action-result", "missing-verifier", "action-result-unverified",
    "verifier-mismatch", "target-drift", "self-proof-rejected", "bad-ref", "ref-too-long",
    "bad-key", "bad-task-key", "bad-source", "path-traversal", "path-redirect",
    "path-outside-base", "wrong-file-kind", "selection-not-found", "execution-not-found",
    "bad-json", "duplicate-json-key", "non-finite-number", "unknown-key",
    "unstable-read", "unstable-snapshot", "record-too-large", "record-parse-failed",
    # T03-R1: request<->record<->trusted-context association + final-state recheck
    "local-ref-mismatch", "key-mismatch", "source-mismatch", "task-mismatch",
    "budget-matter-drift", "context-drift",
)

SCHEMA_V1 = {
    "id": DECISION_HANDOFF_SCHEMA_ID,
    "schema_version": DECISION_HANDOFF_SCHEMA_VERSION,
    "records": ["decision-feedback", "pm-disposition", "local-selection", "local-execution", "matter-budget"],
    "feedback_categories": list(FEEDBACK_CATEGORIES),
    "effect_states": list(EFFECT_STATES),
    "stop_scopes": list(STOP_SCOPES),
    "pm_disposition_kinds": list(PM_DISPOSITION_KINDS),
    "pm_disposition_statuses": list(PM_DISPOSITION_STATUSES),
    "local_sources": list(LOCAL_SOURCES),
    "forbidden_dp_fields": list(FORBIDDEN_LOCAL_DP_FIELDS),
    "local_selection_fields": list(LOCAL_SELECTION_FIELDS),
    "local_execution_fields": list(LOCAL_EXECUTION_FIELDS),
    "matter_budget_fields": list(MATTER_BUDGET_FIELDS),
    "decision_ref_kinds": list(DECISION_REF_KINDS),
    "verification_scope": "shape-only",
    "host_source_verified": False,
}

_ISO_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T.+(?:Z|[+-]\d{2}:\d{2})$")
_COMPONENT_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_MAX_COMPONENT_LEN = 128
# T02 (frozen TS store) bounds a logical ref to 120 UTF-8 BYTES and the produced
# base64url name to <= 160 chars. This READER deliberately uses a looser read-side
# ceiling (200 encoded chars): a ref the writer can never produce simply has no
# on-disk record (selection-not-found), so this is a conservative read-side
# superset, NOT a claim of schema-identical ref acceptance (see implementation
# note). It is documented intent, not a separately guessed schema.
_MAX_ENCODED_LEN = 200
_MAX_RECORD_BYTES = 1 << 20  # 1 MiB bounded read
# Global/key/matter stops block EVERY current record. A ``worker-run`` stop is
# NOT global: it blocks only the current worker-local run (see _stop_blocks),
# never an unrelated PM record. service-request / none / unknown do not stop.
_GLOBAL_STOP_SCOPES = ("user-global", "pm-or-key", "matter")
# Exact T02 shared intent lock (local-selection-store.ts:sharedIntentLockPath).
_SHARED_INTENT_LOCK_BASENAME = "decision-handoff-intent.lock"


# ── Result / record dataclasses (typed) ────────────────────────────────────

@dataclass(frozen=True)
class ContractIssue:
    field: str
    rule: str


@dataclass(frozen=True)
class CheckItem:
    """One REAL check a strict verification performed, with its outcome."""
    name: str
    passed: bool
    detail: str = ""


@dataclass(frozen=True)
class ParseResult(Generic[T]):
    """Pure shape-only result.  Success: host_source_verified=False.  Failure:
    authority_required=False (a missing budget/material is a fillable fact)."""
    ok: bool
    layer: str
    value: T | None = None
    issues: tuple[ContractIssue, ...] = ()
    gaps: tuple[str, ...] = ()
    verification: str = "shape-only"
    host_source_verified: bool = False
    authority_required: bool = False


@dataclass(frozen=True)
class ReadResult:
    """Read-only, shape-only file load.  NEVER host_source_verified=True."""
    ok: bool
    verification: str = "shape-only"
    host_source_verified: bool = False
    selection: "LocalSelectionRecord | None" = None
    execution: "LocalExecutionRecord | None" = None
    selection_sha256: str | None = None
    execution_sha256: str | None = None
    checks: tuple[CheckItem, ...] = ()
    failure_codes: tuple[str, ...] = ()
    issues: tuple[ContractIssue, ...] = ()
    selection_path: str | None = None
    execution_path: str | None = None
    recovery_clues: tuple[str, ...] = ()
    # Read-only stability fingerprint (T03-R1): (present-locks, selection-bytes,
    # execution-bytes) captured at load time. strict_verify re-derives an
    # identical fingerprint before it may report verified, so a lock appearing
    # or a record changing DURING adapter/verifier cannot yield stale success.
    snapshot: tuple | None = None


@dataclass(frozen=True)
class StrictResult(Generic[T]):
    """Strict verification result.  host_source_verified=True ONLY when every
    real check passed through a trusted adapter; failure codes are concrete."""
    ok: bool
    value: T | None
    verification: str
    host_source_verified: bool
    authority_required: bool = False
    checks: tuple[CheckItem, ...] = ()
    failure_codes: tuple[str, ...] = ()


@dataclass(frozen=True)
class HostBinding:
    role: str
    binding_version: str
    observed_at: str
    owner: str | None = None
    claim_id: str | None = None
    key: str | None = None
    task_key: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class DpDecisionRef:
    decision_id: str
    kind: str = "dp"


@dataclass(frozen=True)
class LocalDecisionRef:
    local_ref: str
    kind: str = "local"


@dataclass(frozen=True)
class LocalSelectionRecord:
    schema_version: int
    source: str
    local_ref: str
    matter_ref: str
    host_binding: HostBinding
    matter_version: str
    material_digest: str
    basis_digest: str
    selected_action: str
    selected_basis_id: str
    budget_ref: str
    created_at: str
    parent_decision_ref: DpDecisionRef | None = None
    feedback_ref: str | None = None
    result_consumer: str | None = None
    kind: str = "local-selection"
    origin: str = "local-decision"
    action_state: str = "planned"
    business_completed: bool = False


@dataclass(frozen=True)
class LocalExecutionRecord:
    schema_version: int
    source: str
    local_ref: str
    host_binding: HostBinding
    action_ref: str
    result_ref: str
    executor: str
    target_digest: str
    observed_effect: str
    effect_state: str
    verified_by: str
    budget_ref: str
    created_at: str
    kind: str = "local-execution"
    origin: str = "local-decision"


@dataclass(frozen=True)
class MatterBudget:
    schema_version: int
    budget_ref: str
    matter_ref: str
    deadline: str
    max_steps: int
    no_progress_limit: int
    remaining_cost: float
    steps_consumed: int
    cost_consumed: float
    no_progress_count: int
    source_refs: tuple[str, ...]
    parent_matter_ref: str | None = None


# ── Trusted host boundary (interface; production wiring is T07/T08) ────────

@dataclass(frozen=True)
class TrustedBinding:
    """The CURRENT authoritative host binding, resolved by the host from a
    UNIQUE ACTIVE EXACT-SELF row — never from ``_index.md``/latest/global and
    never from a model-supplied owner string.  The identity coordinates mirror
    ``HostBinding`` and are compared for drift (absent <-> present included)."""
    authority: str
    coordination_row_ref: str
    is_active: bool
    active_row_count: int
    role: str
    binding_version: str
    observed_at: str
    owner: str | None = None
    claim_id: str | None = None
    key: str | None = None
    task_key: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class TrustedContext:
    """The CURRENT expected matter/material/basis/parent/budget/target plus the
    authoritative binding and host stop facts, supplied by the trusted adapter.
    ``budget`` is the real finite budget dict (validated by the reader via
    ``validate_matter_budget``); ``parent_decision_ref`` is a ``dp`` ref dict or
    None.  ``service_timeout``/``exemption_active`` are recorded but can NEVER
    override a blocking scope stop."""
    binding: TrustedBinding
    matter_ref: str
    matter_version: str
    material_digest: str
    basis_digest: str
    target_digest: str
    budget: object
    parent_decision_ref: object = None
    result_consumer: str | None = None
    stop_scope: str = "none"
    service_timeout: bool = False
    exemption_active: bool = False


@dataclass(frozen=True)
class ActionResultEvidence:
    """Host-verifier output for an execution: REAL tool_call/dispatch receipt,
    tool_result/worker-output receipt, target-verifier receipt, and the CURRENT
    object digest observed.  ``confirmed`` must be exactly ``True`` (a truthy
    non-bool or a bare boolean self-proof is rejected).  Blank refs are not
    evidence."""
    action_receipt_ref: str
    result_receipt_ref: str
    verifier_receipt_ref: str
    observed_object_digest: str
    confirmed: bool


class HostEvidenceAdapter(abc.ABC):
    """Trusted host integration point.  Only the host (later T07/T08) wires a
    concrete implementation that reads live coordination rows and real
    tool_call/dispatch/verifier receipts.  The reader requires an INSTANCE of
    this ABC — a passed owner string, a model callback, a dict or a boolean is
    rejected.  Missing adapter/feature fails closed, never ``verified=True``.
    Tests inject a fake adapter in an isolated real-file harness (L1 only)."""

    @abc.abstractmethod
    def current_context(self) -> TrustedContext | None:
        """Return the CURRENT authoritative binding + expectations, or None."""

    @abc.abstractmethod
    def verify_execution(
        self, record: LocalExecutionRecord, target_digest: str
    ) -> ActionResultEvidence | None:
        """Return REAL action/result/target-verifier evidence, or None.  A
        boolean / self-report / mere file existence must NOT be returned as
        proof; the reader re-derives the association and fails closed."""


# ── JSON primitives / strict decode ────────────────────────────────────────

class StrictJsonError(ValueError):
    """Strict JSON decode failure carrying a concrete ``code``."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def is_json_value(value: object, seen: set[int] | None = None) -> bool:
    """Recursive, cycle-safe finite JSON-value guard (parity with TS
    ``isJsonValue``).  Untrusted input is always ``object``."""
    if value is None or isinstance(value, (str, bool)):
        return True
    if isinstance(value, int):  # Python bigint is exact and always finite
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    if seen is None:
        seen = set()
    if isinstance(value, (list, dict)):
        if id(value) in seen:
            return False
        seen.add(id(value))
        if isinstance(value, list):
            return all(is_json_value(item, seen) for item in value)
        return all(is_json_value(k, seen) and is_json_value(v, seen) for k, v in value.items())
    return False


def _unique_pairs(pairs: list[tuple[str, object]]) -> dict:
    result: dict = {}
    for key, val in pairs:
        if key in result:
            raise StrictJsonError("duplicate-json-key")
        result[key] = val
    return result


def _parse_float(text: str) -> float:
    value = float(text)
    if not math.isfinite(value):
        raise StrictJsonError("non-finite-number")
    return value


def _reject_constant(_text: str) -> object:
    raise StrictJsonError("non-finite-number")


def loads_strict_json(raw: bytes | bytearray | str) -> object:
    """Decode ONE JSON value, refusing duplicate keys, NaN/Infinity/-Infinity,
    non-finite floats (e.g. ``1e400``), bad UTF-8 and trailing content.  Raises
    ``StrictJsonError`` with a concrete ``code``."""
    if isinstance(raw, (bytes, bytearray)):
        try:
            text = bytes(raw).decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise StrictJsonError("bad-json") from exc
    elif isinstance(raw, str):
        text = raw
    else:
        raise StrictJsonError("bad-json")
    try:
        value = json.loads(
            text,
            object_pairs_hook=_unique_pairs,
            parse_float=_parse_float,
            parse_constant=_reject_constant,
        )
    except StrictJsonError:
        raise
    except (ValueError, RecursionError, OverflowError) as exc:
        raise StrictJsonError("bad-json") from exc
    if not is_json_value(value):
        raise StrictJsonError("non-finite-number")
    return value


def encode_local_ref(ref: object) -> str:
    """Canonical RFC4648 base64url of the FULL non-empty ref's UTF-8 bytes, NO
    padding.  Never uses the raw ref as a path and never truncates it.  Raises
    ``StrictJsonError`` for a bad/oversize ref (a concrete failure, not a
    truncated collision-prone name)."""
    if not isinstance(ref, str) or ref.strip() == "" or "\x00" in ref:
        raise StrictJsonError("bad-ref")
    encoded = base64.urlsafe_b64encode(ref.encode("utf-8")).rstrip(b"=").decode("ascii")
    if len(encoded) > _MAX_ENCODED_LEN:
        raise StrictJsonError("ref-too-long")
    # round-trip to prove canonicality
    pad = "=" * (-len(encoded) % 4)
    if base64.urlsafe_b64decode(encoded + pad).decode("utf-8") != ref:
        raise StrictJsonError("bad-ref")
    return encoded


# ── shape helpers (TS parity) ──────────────────────────────────────────────

def _accepted(layer: str, value: T) -> ParseResult[T]:
    return ParseResult(ok=True, layer=layer, value=value, verification="shape-only", host_source_verified=False)


def _rejected(layer: str, issues: list[ContractIssue], gaps: list[str] | None = None) -> ParseResult[T]:
    return ParseResult(
        ok=False, layer=layer, issues=tuple(issues), gaps=tuple(gaps or []),
        verification="shape-only", host_source_verified=False, authority_required=False,
    )


def _issue(field_name: str, rule: str) -> ContractIssue:
    return ContractIssue(field_name, rule)


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _iso_timestamp(value: object) -> bool:
    if not _nonblank(value) or not _ISO_RE.match(value):  # type: ignore[arg-type]
        return False
    try:
        _dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return False
    return True


def _is_schema_version_one(value: object) -> bool:
    # Python bool is a subclass of int: ``True == 1``.  Reject it explicitly.
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value == 1


def _finite_number(value: object) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, int):
        return True
    if isinstance(value, float):
        return math.isfinite(value)
    return False


def _safe_int_at_least(value: object, minimum: int) -> bool:
    if not _finite_number(value):
        return False
    if isinstance(value, float) and not value.is_integer():
        return False
    if not (-(2**53 - 1) <= value <= 2**53 - 1):
        return False
    return value >= minimum


def _require_str(obj: dict, key: str, issues: list[ContractIssue], gaps: list[str], prefix: str) -> str | None:
    value = obj.get(key)
    if not _nonblank(value):
        issues.append(_issue(prefix + key, "missing or blank"))
        gaps.append(prefix + key)
        return None
    return value


def _optional_str(obj: dict, key: str, issues: list[ContractIssue], prefix: str) -> str | None:
    if key not in obj:
        return None
    value = obj[key]
    if not _nonblank(value):
        # A present null/empty is NOT "absent/unknown": TS rejects it rather
        # than silently treating it as a missing optional field.
        issues.append(_issue(prefix + key, "must be a nonblank string when present"))
        return None
    return value


def _check_declared_keys(obj: dict, allowed: tuple[str, ...], issues: list[ContractIssue], prefix: str) -> None:
    for key in obj:
        if not isinstance(key, str):
            # A direct Python object may carry int/tuple/None dict keys; JSON
            # text cannot. Reject the whole structure instead of concatenating
            # a non-string key (TypeError) or silently dropping the key.
            issues.append(_issue(prefix + "<non-string-key:" + type(key).__name__ + ">",
                                 "dict keys must be JSON strings"))
        elif key in FORBIDDEN_LOCAL_DP_FIELDS:
            issues.append(_issue(prefix + key, "forbidden DP impersonation field in a local record"))
        elif key not in allowed:
            issues.append(_issue(prefix + key, "not a declared schema v1 field"))


# ── pure parse: DecisionRef / HostBinding ──────────────────────────────────

def parse_decision_ref(value: object) -> ParseResult[DpDecisionRef | LocalDecisionRef]:
    layer = "decision-ref-schema"
    if not isinstance(value, dict):
        return _rejected(layer, [_issue("decision_ref", "must be an object")], ["decision_ref"])
    keys = set(value)
    if value.get("kind") == "dp" and keys == {"kind", "decision_id"} and _nonblank(value.get("decision_id")):
        return _accepted(layer, DpDecisionRef(decision_id=value["decision_id"]))
    if value.get("kind") == "local" and keys == {"kind", "local_ref"} and _nonblank(value.get("local_ref")):
        return _accepted(layer, LocalDecisionRef(local_ref=value["local_ref"]))
    return _rejected(
        layer,
        [_issue("decision_ref", "must be {kind:'dp',decision_id} or {kind:'local',local_ref}")],
        ["decision_ref"],
    )


def route_decision_ref(value: object) -> ParseResult[str]:
    """Consumer helper: route a discriminated ref to ``'dp'`` (original strict
    receipt join) or ``'local'`` (this reader).  A ``local_ref`` NEVER becomes a
    decision id and NEVER routes to the DP branch."""
    parsed = parse_decision_ref(value)
    if not parsed.ok or parsed.value is None:
        return _rejected("decision-ref-route", list(parsed.issues), list(parsed.gaps))
    return _accepted("decision-ref-route", parsed.value.kind)


def parse_host_binding(value: object) -> ParseResult[HostBinding]:
    layer = "host-binding-schema"
    if not isinstance(value, dict):
        return _rejected(layer, [_issue("host_binding", "must be an object")], ["host_binding"])
    issues: list[ContractIssue] = []
    gaps: list[str] = []
    _check_declared_keys(value, HOST_BINDING_FIELDS, issues, "host_binding.")
    role = value.get("role")
    if role not in HOST_ROLES:
        issues.append(_issue("host_binding.role", "unknown role"))
        gaps.append("host_binding.role")
    owner = _optional_str(value, "owner", issues, "host_binding.")
    claim_id = _optional_str(value, "claim_id", issues, "host_binding.")
    key = _optional_str(value, "key", issues, "host_binding.")
    task_key = _optional_str(value, "task_key", issues, "host_binding.")
    run_id = _optional_str(value, "run_id", issues, "host_binding.")
    version = _require_str(value, "binding_version", issues, gaps, "host_binding.")
    observed_at = value.get("observed_at")
    if not _iso_timestamp(observed_at):
        issues.append(_issue("host_binding.observed_at", "must be an ISO timestamp with timezone"))
        gaps.append("host_binding.observed_at")
    if issues or role not in HOST_ROLES or version is None or not _iso_timestamp(observed_at):
        return _rejected(layer, issues, gaps)
    return _accepted(layer, HostBinding(
        role=role, binding_version=version, observed_at=observed_at,
        owner=owner, claim_id=claim_id, key=key, task_key=task_key, run_id=run_id,
    ))


# ── pure parse: local-selection ────────────────────────────────────────────

def parse_local_selection_record(value: object) -> ParseResult[LocalSelectionRecord]:
    layer = "local-selection-schema"
    if not isinstance(value, dict):
        return _rejected(layer, [_issue("local_selection", "must be an object")], ["local_selection"])
    issues: list[ContractIssue] = []
    gaps: list[str] = []
    p = "local_selection."
    _check_declared_keys(value, LOCAL_SELECTION_FIELDS, issues, p)
    if not _is_schema_version_one(value.get("schema_version")):
        issues.append(_issue(p + "schema_version", "must be 1"))
    if value.get("kind") != "local-selection":
        issues.append(_issue(p + "kind", "must be local-selection"))
    if value.get("origin") != "local-decision":
        issues.append(_issue(p + "origin", "must be local-decision"))
    if value.get("source") not in LOCAL_SOURCES:
        issues.append(_issue(p + "source", "unknown source"))
    local_ref = _require_str(value, "local_ref", issues, gaps, p)
    matter_ref = _require_str(value, "matter_ref", issues, gaps, p)
    version = _require_str(value, "matter_version", issues, gaps, p)
    material_digest = _require_str(value, "material_digest", issues, gaps, p)
    basis_digest = _require_str(value, "basis_digest", issues, gaps, p)
    selected_action = _require_str(value, "selected_action", issues, gaps, p)
    selected_basis_id = _require_str(value, "selected_basis_id", issues, gaps, p)
    budget_ref = _require_str(value, "budget_ref", issues, gaps, p)
    feedback_ref = _optional_str(value, "feedback_ref", issues, p)
    result_consumer = _optional_str(value, "result_consumer", issues, p)
    created_at = value.get("created_at")
    if not _iso_timestamp(created_at):
        issues.append(_issue(p + "created_at", "must be an ISO timestamp with timezone"))
    if value.get("action_state") != "planned":
        issues.append(_issue(p + "action_state", "selection must remain planned"))
    if value.get("business_completed") is not False:
        issues.append(_issue(p + "business_completed", "selection must be false"))
    host_binding: HostBinding | None = None
    if "host_binding" in value:
        parsed = parse_host_binding(value["host_binding"])
        if not parsed.ok or parsed.value is None:
            issues.extend(_issue(p + i.field, i.rule) for i in parsed.issues)
        else:
            host_binding = parsed.value
    else:
        issues.append(_issue(p + "host_binding", "required"))
    parent_ref: DpDecisionRef | None = None
    if "parent_decision_ref" in value:
        parsed_ref = parse_decision_ref(value["parent_decision_ref"])
        if not parsed_ref.ok or parsed_ref.value is None or parsed_ref.value.kind != "dp":
            issues.append(_issue(p + "parent_decision_ref", "must be a separate dp ref"))
        else:
            parent_ref = parsed_ref.value  # type: ignore[assignment]
    if issues:
        return _rejected(layer, issues, gaps)
    return _accepted(layer, LocalSelectionRecord(
        schema_version=DECISION_HANDOFF_SCHEMA_VERSION, source=value["source"],
        local_ref=local_ref, matter_ref=matter_ref, host_binding=host_binding,  # type: ignore[arg-type]
        matter_version=version, material_digest=material_digest, basis_digest=basis_digest,
        selected_action=selected_action, selected_basis_id=selected_basis_id, budget_ref=budget_ref,
        created_at=created_at, parent_decision_ref=parent_ref, feedback_ref=feedback_ref,
        result_consumer=result_consumer,
    ))


def parse_local_execution_record(value: object) -> ParseResult[LocalExecutionRecord]:
    layer = "local-execution-schema"
    if not isinstance(value, dict):
        return _rejected(layer, [_issue("local_execution", "must be an object")], ["local_execution"])
    issues: list[ContractIssue] = []
    gaps: list[str] = []
    p = "local_execution."
    _check_declared_keys(value, LOCAL_EXECUTION_FIELDS, issues, p)
    if not _is_schema_version_one(value.get("schema_version")):
        issues.append(_issue(p + "schema_version", "must be 1"))
    if value.get("kind") != "local-execution":
        issues.append(_issue(p + "kind", "must be local-execution"))
    if value.get("origin") != "local-decision":
        issues.append(_issue(p + "origin", "must be local-decision"))
    if value.get("source") not in LOCAL_SOURCES:
        issues.append(_issue(p + "source", "unknown source"))
    local_ref = _require_str(value, "local_ref", issues, gaps, p)
    action_ref = _require_str(value, "action_ref", issues, gaps, p)
    result_ref = _require_str(value, "result_ref", issues, gaps, p)
    executor = _require_str(value, "executor", issues, gaps, p)
    target_digest = _require_str(value, "target_digest", issues, gaps, p)
    observed_effect = _require_str(value, "observed_effect", issues, gaps, p)
    verified_by = _require_str(value, "verified_by", issues, gaps, p)
    budget_ref = _require_str(value, "budget_ref", issues, gaps, p)
    effect_state = value.get("effect_state")
    if effect_state not in EXECUTION_EFFECT_STATES:
        issues.append(_issue(p + "effect_state", "must be known or unknown"))
    created_at = value.get("created_at")
    if not _iso_timestamp(created_at):
        issues.append(_issue(p + "created_at", "must be an ISO timestamp with timezone"))
    host_binding: HostBinding | None = None
    if "host_binding" in value:
        parsed = parse_host_binding(value["host_binding"])
        if not parsed.ok or parsed.value is None:
            issues.extend(_issue(p + i.field, i.rule) for i in parsed.issues)
        else:
            host_binding = parsed.value
    else:
        issues.append(_issue(p + "host_binding", "required"))
    if issues:
        return _rejected(layer, issues, gaps)
    return _accepted(layer, LocalExecutionRecord(
        schema_version=DECISION_HANDOFF_SCHEMA_VERSION, source=value["source"],
        local_ref=local_ref, host_binding=host_binding, action_ref=action_ref,  # type: ignore[arg-type]
        result_ref=result_ref, executor=executor, target_digest=target_digest,
        observed_effect=observed_effect, effect_state=effect_state, verified_by=verified_by,
        budget_ref=budget_ref, created_at=created_at,
    ))


# ── pure parse: matter budget ──────────────────────────────────────────────

def validate_matter_budget(value: object) -> ParseResult[MatterBudget]:
    layer = "matter-budget"
    if not isinstance(value, dict):
        return _rejected(layer, [_issue("budget", "must be an object")], ["budget"])
    issues: list[ContractIssue] = []
    gaps: list[str] = []
    p = "budget."
    _check_declared_keys(value, MATTER_BUDGET_FIELDS, issues, p)
    if not _is_schema_version_one(value.get("schema_version")):
        issues.append(_issue(p + "schema_version", "must be 1"))
    budget_ref = _require_str(value, "budget_ref", issues, gaps, p)
    matter_ref = _require_str(value, "matter_ref", issues, gaps, p)
    parent_matter_ref = _optional_str(value, "parent_matter_ref", issues, p)
    if not _iso_timestamp(value.get("deadline")):
        issues.append(_issue(p + "deadline", "must be a finite ISO deadline with timezone"))
        gaps.append("deadline")
    for key, minimum, integer in (
        ("max_steps", 1, True), ("no_progress_limit", 0, True), ("remaining_cost", 0, False),
        ("steps_consumed", 0, True), ("cost_consumed", 0, False), ("no_progress_count", 0, True),
    ):
        v = value.get(key)
        ok = _safe_int_at_least(v, minimum) if integer else (_finite_number(v) and v >= minimum)
        if not ok:
            issues.append(_issue(p + key, "must be a finite non-negative number" if not integer else "must be a finite non-negative integer"))
            gaps.append(key)
    source_refs = value.get("source_refs")
    if not (isinstance(source_refs, list) and source_refs and all(_nonblank(x) for x in source_refs)):
        issues.append(_issue(p + "source_refs", "real card/run provenance required; no invented default"))
        gaps.append("source_refs")
    if _safe_int_at_least(value.get("steps_consumed"), 0) and _safe_int_at_least(value.get("max_steps"), 1):
        if value["steps_consumed"] > value["max_steps"]:
            issues.append(_issue(p + "steps_consumed", "cannot exceed max_steps"))
    if issues:
        return _rejected(layer, issues, gaps)
    return _accepted(layer, MatterBudget(
        schema_version=DECISION_HANDOFF_SCHEMA_VERSION, budget_ref=budget_ref,
        matter_ref=matter_ref, deadline=value["deadline"], max_steps=value["max_steps"],
        no_progress_limit=value["no_progress_limit"], remaining_cost=value["remaining_cost"],
        steps_consumed=value["steps_consumed"], cost_consumed=value["cost_consumed"],
        no_progress_count=value["no_progress_count"], source_refs=tuple(source_refs),
        parent_matter_ref=parent_matter_ref,
    ))


# ── raw-JSON pure parse variants (strict decode + shape) ───────────────────

def parse_local_selection_json(raw: bytes | str) -> ParseResult[LocalSelectionRecord]:
    try:
        value = loads_strict_json(raw)
    except StrictJsonError as exc:
        return _rejected("local-selection-schema", [_issue("<json>", exc.code)], ["<json>"])
    return parse_local_selection_record(value)


def parse_local_execution_json(raw: bytes | str) -> ParseResult[LocalExecutionRecord]:
    try:
        value = loads_strict_json(raw)
    except StrictJsonError as exc:
        return _rejected("local-execution-schema", [_issue("<json>", exc.code)], ["<json>"])
    return parse_local_execution_record(value)


# ── read-only safe path / stable read ──────────────────────────────────────

class _StrictFailure(Exception):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(code)
        self.code = code
        self.detail = detail


def _validate_component(value: object, label: str) -> str:
    if not isinstance(value, str) or value in (".", "..") or "\x00" in value or "/" in value or "\\" in value:
        raise _StrictFailure("bad-" + label)
    if len(value) > _MAX_COMPONENT_LEN or not _COMPONENT_RE.match(value):
        raise _StrictFailure("bad-" + label)
    return value


def _is_redirect(path: str) -> bool:
    try:
        st = os.lstat(path)
    except OSError:
        return False
    if stat.S_ISLNK(st.st_mode):
        return True
    attrs = getattr(st, "st_file_attributes", 0)
    if attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        return True
    return False


def _fp_tuple(st: os.stat_result) -> tuple:
    return (st.st_dev, st.st_ino, st.st_size, getattr(st, "st_mtime_ns", int(st.st_mtime * 1e9)))


def _fingerprint(path: str) -> tuple:
    """Module-level seam so an L1 test can simulate a concurrent mutation
    between the two lstat reads (read-stability only, never a trust source)."""
    return _fp_tuple(os.lstat(path))


def _assert_path_chain_safe(root: pathlib.Path, path: pathlib.Path) -> None:
    root_real = os.path.realpath(str(root))
    target = os.path.abspath(str(path))
    try:
        rel = os.path.relpath(target, root_real)
    except ValueError as exc:
        raise _StrictFailure("path-outside-base") from exc
    if rel == os.curdir or rel.startswith(".." + os.sep) or rel == "..":
        raise _StrictFailure("path-outside-base")
    current = root_real
    for comp in pathlib.PurePath(rel).parts:
        current = os.path.join(current, comp)
        if _is_redirect(current):
            raise _StrictFailure("path-redirect", comp)
    parent_real = os.path.realpath(os.path.dirname(target))
    if parent_real != root_real and not parent_real.startswith(root_real + os.sep):
        raise _StrictFailure("path-traversal")


def _stable_read_bytes(path: pathlib.Path) -> bytes:
    """Bounded, symlink-free, stable read.  Compares lstat before/after, the
    fd's own fstat, and a full re-read; any drift rejects ``unstable-read``.
    A lookup only (not a TOCTOU-free pure-lstat guarantee)."""
    p = str(path)
    if _is_redirect(p):
        raise _StrictFailure("path-redirect")
    try:
        st = os.lstat(p)
    except OSError as exc:
        raise _StrictFailure("wrong-file-kind") from exc
    if not stat.S_ISREG(st.st_mode):
        raise _StrictFailure("wrong-file-kind")
    fp1 = _fingerprint(p)
    try:
        fd = os.open(p, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    except OSError as exc:
        raise _StrictFailure("selection-not-found") from exc
    try:
        fstat1 = _fp_tuple(os.fstat(fd))
        data = b""
        while True:
            chunk = os.read(fd, 65536)
            if not chunk:
                break
            data += chunk
            if len(data) > _MAX_RECORD_BYTES:
                raise _StrictFailure("record-too-large")
        fstat2 = _fp_tuple(os.fstat(fd))
    finally:
        os.close(fd)
    fp2 = _fingerprint(p)
    if fstat1 != fstat2 or fp1 != fp2 or fp1 != fstat1:
        raise _StrictFailure("unstable-read")
    # second independent read must yield identical bytes
    try:
        with open(p, "rb") as handle:
            if handle.read() != data:
                raise _StrictFailure("unstable-read")
    except OSError as exc:
        raise _StrictFailure("unstable-read") from exc
    return data


def _canonical_root(agenticdoc_root: pathlib.Path | str) -> pathlib.Path:
    """Normalize the host-provided root ONCE so a Windows 8.3 short-name <->
    long-name alias cannot make a legitimate derived path look
    ``path-outside-base`` (T03-R1 item 7). realpath resolves the short->long
    NAME alias; it does NOT make a real symlink/junction trusted: the per-
    component lstat redirect checks in ``_assert_path_chain_safe`` still reject
    any reparse point in the input-controlled key/task/filename chain below the
    root. The root is the host-chosen container, not an untrusted input."""
    return pathlib.Path(os.path.realpath(str(agenticdoc_root)))


def _file_kind(path: pathlib.Path) -> str:
    """lstat-based classification of a path: 'absent' | 'file' | 'redirect' |
    'invalid' | 'error'. A directory, symlink/junction, broken link or special
    file is NEVER silently treated as an absent OPTIONAL execution (T03-R1
    PY07). Read-only, never raises."""
    try:
        st = os.lstat(str(path))
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "error"
    if stat.S_ISLNK(st.st_mode):
        return "redirect"
    attrs = getattr(st, "st_file_attributes", 0)
    if attrs & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0):
        return "redirect"
    if not stat.S_ISREG(st.st_mode):
        return "invalid"
    return "file"


def _file_hash(path: pathlib.Path) -> str:
    """Read-only sha256 of a REG file (or a state marker). Never writes, never
    raises. Used only for before/after/final snapshot stability, never as
    provenance."""
    try:
        st = os.lstat(str(path))
    except FileNotFoundError:
        return "absent"
    except OSError:
        return "error"
    if stat.S_ISLNK(st.st_mode) or (
        getattr(st, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0)
    ):
        return "redirect"
    if not stat.S_ISREG(st.st_mode):
        return "invalid"
    try:
        fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_BINARY", 0))
        try:
            data = b""
            while True:
                chunk = os.read(fd, 65536)
                if not chunk:
                    break
                data += chunk
                if len(data) > _MAX_RECORD_BYTES:
                    return "too-large"
            return "sha256:" + hashlib.sha256(data).hexdigest()
        finally:
            os.close(fd)
    except OSError:
        return "error"


def _present_locks(
    root: pathlib.Path, base: pathlib.Path, selection: pathlib.Path, execution: pathlib.Path,
) -> tuple[str, ...]:
    """Read-only detection of the EXACT T02 write locks (T03-R1 PY06):
      * shared intent lock  <agenticdocRoot>/../.mw/decision-handoff-intent.lock
      * per-record locks    <selection>.lock and <execution>.lock
    Plus a conservative sibling ``*.lock`` scan as a fail-closed superset.
    Uses ``lexists`` so even a broken-symlink lock counts as present. NEVER
    creates / removes / breaks a lock or file; OSError -> present (unstable)."""
    present: list[str] = []
    candidates = (
        str(root.parent / ".mw" / _SHARED_INTENT_LOCK_BASENAME),
        str(selection) + ".lock",
        str(execution) + ".lock",
    )
    for candidate in candidates:
        try:
            if os.path.lexists(candidate):
                present.append(candidate)
        except OSError:
            present.append(candidate)  # cannot inspect -> fail closed
    try:
        if base.is_dir():
            for name in os.listdir(str(base)):
                if name.endswith(".lock"):
                    p = str(base / name)
                    if p not in present:
                        present.append(p)
    except OSError:
        present.append("<lock-scan-error>")
    return tuple(sorted(present))


def _snapshot_fingerprint(
    root: pathlib.Path, base: pathlib.Path, selection: pathlib.Path, execution: pathlib.Path,
) -> tuple:
    """Hashable, read-only snapshot of lock presence + selection/execution bytes.
    Never raises (state markers on error). Compared before/after load and again
    before strict success. Best-effort stability check, NOT a claim of a fully
    race-free / TOCTOU-free handle protocol."""
    return (
        _present_locks(root, base, selection, execution),
        _file_hash(selection),
        _file_hash(execution),
    )


def _resolve_paths(
    agenticdoc_root: pathlib.Path, key: str, source: str, local_ref: str, task_key: str | None,
) -> tuple[pathlib.Path, pathlib.Path, pathlib.Path, str]:
    key = _validate_component(key, "key")
    if source not in LOCAL_SOURCES:
        raise _StrictFailure("bad-source")
    try:
        encoded = encode_local_ref(local_ref)
    except StrictJsonError as exc:
        # surface a bad/oversize ref as a concrete reader failure code, never
        # a leaked exception.
        raise _StrictFailure(exc.code) from exc
    if source == "pm":
        base = agenticdoc_root / key / "evidence" / "decision-handoffs"
    else:
        if task_key is None:
            raise _StrictFailure("bad-task-key")
        task_key = _validate_component(task_key, "task-key")
        base = agenticdoc_root / key / "workers" / task_key / "local-decisions"
    selection = base / (encoded + ".json")
    execution = base / (encoded + ".execution.json")
    return selection, execution, base, encoded


def _scan_recovery_clues(
    agenticdoc_root: pathlib.Path, key: str, task_key: str | None, encoded: str, current_base: pathlib.Path,
) -> tuple[str, ...]:
    """Worker source: files with the same encoded ref under OTHER task dirs are
    OLD-run recovery clues only — listed, never parsed or verified, never a
    current capability.  Read-only and bounded."""
    clues: list[str] = []
    if task_key is None:
        return ()
    workers = agenticdoc_root / key / "workers"
    try:
        if not workers.is_dir():
            return ()
        for entry in os.listdir(str(workers)):
            if entry == task_key or not _COMPONENT_RE.match(entry):
                continue
            candidate = workers / entry / "local-decisions" / (encoded + ".json")
            if candidate.is_file() and candidate != current_base / (encoded + ".json"):
                clues.append(str(candidate))
    except OSError:
        return tuple(clues)
    return tuple(sorted(clues))


def _read_one(path: pathlib.Path, root: pathlib.Path, parser) -> tuple[object | None, str, list[ContractIssue]]:
    _assert_path_chain_safe(root, path)
    data = _stable_read_bytes(path)
    digest = hashlib.sha256(data).hexdigest()
    parsed = parser(data)
    if not parsed.ok or parsed.value is None:
        return None, digest, list(parsed.issues)
    return parsed.value, digest, []


def read_local_evidence(
    agenticdoc_root: pathlib.Path | str,
    key: str,
    source: str,
    local_ref: str,
    *,
    task_key: str | None = None,
) -> ReadResult:
    """Strict READ-ONLY load of one selection (and its execution, if present).

    Derives the frozen physical path, refuses traversal/redirect/wrong file
    kind/bad JSON/duplicate keys/unstable reads, parses shape-only, and records
    real checks + a SHA256 of each raw record. It read-only detects the EXACT
    T02 write locks (<root>/../.mw/decision-handoff-intent.lock and
    <record>.lock) plus a conservative sibling ``*.lock`` scan, and captures a
    before/after lock+bytes snapshot (T03-R1 PY06/PY08). An EXISTING invalid
    execution path (directory/redirect/broken link) is refused, never silently
    treated as absent (PY07). The Windows 8.3 short/long root alias is handled
    by canonicalizing the host root, while lstat redirect checks still reject a
    real symlink/junction in the record chain. NEVER writes: no directory, lock
    or record, no repair/overwrite of an invalid-existing file; never creates or
    breaks a lock. ``host_source_verified`` stays False here.
    """
    root = _canonical_root(agenticdoc_root)
    checks: list[CheckItem] = []
    codes: list[str] = []
    issues: list[ContractIssue] = []
    try:
        selection_path, execution_path, base, encoded = _resolve_paths(root, key, source, local_ref, task_key)
    except _StrictFailure as exc:
        checks.append(CheckItem("path-derivation", False, exc.code))
        return ReadResult(ok=False, checks=tuple(checks), failure_codes=(exc.code,))
    checks.append(CheckItem("path-derivation", True, str(selection_path)))

    # BEFORE snapshot: exact T02 locks + selection/execution byte identity.
    # A present lock makes the whole snapshot unstable (fail closed).
    snap_before = _snapshot_fingerprint(root, base, selection_path, execution_path)
    if snap_before[0]:
        checks.append(CheckItem("lock-absent", False, "lock present"))
        return ReadResult(
            ok=False, checks=tuple(checks), failure_codes=("unstable-snapshot",),
            selection_path=str(selection_path), execution_path=str(execution_path),
            snapshot=snap_before,
        )
    checks.append(CheckItem("lock-absent", True))

    selection: LocalSelectionRecord | None = None
    selection_sha: str | None = None
    sel_kind = _file_kind(selection_path)
    if sel_kind == "absent":
        codes.append("selection-not-found")
        checks.append(CheckItem("selection-file", False, "missing"))
    elif sel_kind != "file":
        # redirect / invalid / error: an existing wrong-kind selection is NOT
        # absent and is never repaired or overwritten (PY07 hardening).
        code = "path-redirect" if sel_kind == "redirect" else "wrong-file-kind"
        codes.append(code)
        checks.append(CheckItem("selection-file", False, sel_kind))
    else:
        try:
            selection, selection_sha, sel_issues = _read_one(selection_path, root, parse_local_selection_json)
            issues.extend(sel_issues)
            if selection is None:
                codes.append("record-parse-failed")
                checks.append(CheckItem("selection-shape", False, "; ".join(i.rule for i in sel_issues)))
            else:
                checks.append(CheckItem("selection-shape", True))
        except _StrictFailure as exc:
            codes.append(exc.code)
            checks.append(CheckItem("selection-file", False, exc.code))

    execution: LocalExecutionRecord | None = None
    execution_sha: str | None = None
    exec_kind = _file_kind(execution_path)
    if exec_kind == "absent":
        pass  # optional execution: a genuinely absent file is fine
    elif exec_kind != "file":
        # PY07: an EXISTING directory / redirect / broken link / special file at
        # the optional execution path must NOT be silently treated as absent.
        code = "path-redirect" if exec_kind == "redirect" else "wrong-file-kind"
        codes.append(code)
        checks.append(CheckItem("execution-file", False, exec_kind + " (not absent)"))
    else:
        try:
            execution, execution_sha, exec_issues = _read_one(execution_path, root, parse_local_execution_json)
            issues.extend(exec_issues)
            if execution is None:
                codes.append("record-parse-failed")
                checks.append(CheckItem("execution-shape", False, "; ".join(i.rule for i in exec_issues)))
            else:
                checks.append(CheckItem("execution-shape", True))
        except _StrictFailure as exc:
            codes.append(exc.code)
            checks.append(CheckItem("execution-file", False, exc.code))

    # AFTER snapshot: a lock appearing or a record changing DURING the read
    # rejects the snapshot (read-only, fail closed).
    snap_after = _snapshot_fingerprint(root, base, selection_path, execution_path)
    if snap_after != snap_before:
        codes.append("unstable-snapshot")
        checks.append(CheckItem("stable-snapshot", False, "snapshot changed during read"))
    else:
        checks.append(CheckItem("stable-snapshot", True))

    recovery = _scan_recovery_clues(root, key, task_key, encoded, base) if source == "worker-local" else ()
    ok = not codes
    return ReadResult(
        ok=ok, verification="shape-only", host_source_verified=False,
        selection=selection, execution=execution,
        selection_sha256=selection_sha, execution_sha256=execution_sha,
        checks=tuple(checks), failure_codes=tuple(codes), issues=tuple(issues),
        selection_path=str(selection_path), execution_path=str(execution_path),
        recovery_clues=recovery, snapshot=snap_before,
    )


# ── strict verify (the only path to host_source_verified=True) ──────────────

def _identity(binding: object, field_name: str) -> object:
    return getattr(binding, field_name, None)


def _check(condition: bool, code: str, name: str, checks: list[CheckItem], codes: list[str], detail: str = "") -> None:
    checks.append(CheckItem(name, condition, detail or ("ok" if condition else code)))
    if not condition:
        codes.append(code)


def _verify_request_identity(
    record: LocalSelectionRecord | LocalExecutionRecord,
    ctx: TrustedContext,
    checks: list[CheckItem],
    codes: list[str],
    *,
    key: str,
    source: str,
    local_ref: str,
    task_key: str | None,
) -> None:
    """Bind the REQUESTED identity (key/source/local_ref/task) to the LOADED
    record AND the trusted host binding (T03-R1 PY01/PY02/PY03). A shape-valid
    record at the requested filename is NOT proof of association: a swapped
    local_ref (PY01), a foreign host_binding.key that the adapter also matches
    (PY02), or a worker-local record under a PM path (PY03) must all be
    refused. The input identity is the anchor; an adapter that agrees with the
    wrong record cannot substitute for it. Absent <-> present key/task is a
    mismatch. Shape-only parse cannot stand in for this association."""
    _check(record.local_ref == local_ref, "local-ref-mismatch",
           "request-local-ref", checks, codes,
           detail="" if record.local_ref == local_ref else "record local_ref != requested")
    _check(record.source == source, "source-mismatch",
           "request-source", checks, codes)
    key_ok = (record.host_binding.key == key) and (ctx.binding.key == key)
    _check(key_ok, "key-mismatch", "request-key", checks, codes,
           detail="" if key_ok else "record/trusted key != requested key")
    if source == "worker-local":
        task_ok = (
            task_key is not None
            and record.host_binding.task_key == task_key
            and ctx.binding.task_key == task_key
        )
        _check(task_ok, "task-mismatch", "request-task", checks, codes)


def _canonical_json(value: object) -> str:
    """Immutable strict-JSON semantic projection for a mutable trusted field.
    A non-JSON value gets a stable marker, never a permissive stringification;
    the normal budget/plan validators still reject that value with their own
    concrete code. The returned string cannot be mutated by a later callback."""
    if value is None:
        return "null"
    try:
        return json.dumps(value, sort_keys=True, allow_nan=False, ensure_ascii=False)
    except (TypeError, ValueError, OverflowError, RecursionError) as exc:
        return "<non-json:" + type(exc).__name__ + ":" + type(value).__name__ + ">"


def _context_state(ctx: TrustedContext) -> tuple:
    """Immutable semantic projection captured BEFORE any later adapter call.
    Volatile ``observed_at`` (a snapshot time, not identity) is excluded so a
    re-fetched, otherwise-equal context is legitimate. Nested budget/parent
    values become canonical strings immediately; a later in-place mutation
    cannot rewrite this captured state."""
    b = ctx.binding
    return (
        b.authority, b.coordination_row_ref, b.is_active, b.active_row_count,
        b.role, b.binding_version, b.owner, b.claim_id, b.key, b.task_key, b.run_id,
        ctx.matter_ref, ctx.matter_version, ctx.material_digest, ctx.basis_digest,
        ctx.target_digest,
        _canonical_json(ctx.budget), _canonical_json(ctx.parent_decision_ref),
        ctx.result_consumer, ctx.stop_scope, ctx.service_timeout, ctx.exemption_active,
    )


def _stop_blocks(
    ctx: TrustedContext, record: LocalSelectionRecord | LocalExecutionRecord, scope_task_key: str | None,
) -> bool:
    """Whether ``ctx.stop_scope`` blocks THIS record (T03-R1 PY05).
    Global/key/matter stops block everything. A ``worker-run`` stop blocks ONLY
    the current worker-local run, never an unrelated PM record; the record must
    be worker-local AND bound to the current task/run. service_timeout /
    exemption_active are recorded but never override a blocking stop."""
    scope = ctx.stop_scope
    if scope in _GLOBAL_STOP_SCOPES:
        return True
    if scope == "worker-run":
        if record.source != "worker-local":
            return False
        return (
            _nonblank(record.host_binding.task_key)
            and _nonblank(record.host_binding.run_id)
            and record.host_binding.task_key == ctx.binding.task_key
            and record.host_binding.run_id == ctx.binding.run_id
            and (scope_task_key is None or ctx.binding.task_key == scope_task_key)
        )
    return False


def _verify_binding(
    record: LocalSelectionRecord | LocalExecutionRecord,
    ctx: TrustedContext,
    checks: list[CheckItem],
    codes: list[str],
    *,
    scope_task_key: str | None,
) -> None:
    """Binding / budget / stop checks that apply to BOTH record kinds (both
    have host_binding, source and budget_ref; neither has matter/material/basis
    fields on an execution row)."""
    binding = ctx.binding
    _check(binding.authority == AUTHORITATIVE_BINDING_KIND, "non-authoritative-binding",
           "binding-authority", checks, codes)
    _check(_nonblank(binding.coordination_row_ref), "non-authoritative-binding",
           "binding-row-ref", checks, codes)
    _check(binding.is_active is True, "binding-not-active", "binding-active", checks, codes)
    _check(binding.active_row_count == 1, "binding-not-unique", "binding-unique", checks, codes)

    # 7 identity coordinates; absent <-> present drift is a failure.
    for name in HOST_IDENTITY_FIELDS:
        same = _identity(record.host_binding, name) == _identity(binding, name)
        _check(same, "binding-drift", "binding-drift:" + name, checks, codes,
               detail="" if same else name)

    # source/role consistency (TS compareLocalSelectionToHost).
    role_ok = (
        (record.source == "pm" and binding.role == "pm")
        or (record.source == "worker-local" and binding.role != "pm")
    )
    _check(role_ok, "source-role-mismatch", "source-role", checks, codes)

    # worker-local strictly bound to the CURRENT task/run; an old claim/run is
    # only a recovery clue, never a current capability.
    if record.source == "worker-local":
        current = (
            _nonblank(record.host_binding.task_key)
            and _nonblank(record.host_binding.run_id)
            and record.host_binding.task_key == binding.task_key
            and record.host_binding.run_id == binding.run_id
            and (scope_task_key is None or binding.task_key == scope_task_key)
        )
        _check(current, "worker-not-current-run", "worker-current-run", checks, codes)

    # budget: real finite shape, no exhaustion, matching ref; a scope stop is
    # never overridden by service timeout or exemption.
    if ctx.budget is None:
        codes.append("missing-budget")
        checks.append(CheckItem("budget-shape", False, "missing budget"))
    else:
        parsed_budget = validate_matter_budget(ctx.budget)
        _check(parsed_budget.ok and parsed_budget.value is not None, "invalid-budget",
               "budget-shape", checks, codes)
        if parsed_budget.ok and parsed_budget.value is not None:
            budget = parsed_budget.value
            _check(record.budget_ref == budget.budget_ref, "budget-ref-drift",
                   "budget-ref", checks, codes)
            # T03-R1 PY04: the finite budget must belong to the CURRENT matter.
            # A budget for another matter that happens to share the same
            # budget_ref is NOT the applicable parent/finite budget and must not
            # be waved through on provenance alone.
            _check(budget.matter_ref == ctx.matter_ref, "budget-matter-drift",
                   "budget-matter-ref", checks, codes)
            exhausted = (
                budget.remaining_cost <= 0
                or budget.steps_consumed >= budget.max_steps
                or budget.no_progress_count >= budget.no_progress_limit
                or _deadline_passed(budget.deadline)
            )
            _check(not exhausted, "budget-exhausted", "budget-not-exhausted", checks, codes)

    stop = _stop_blocks(ctx, record, scope_task_key)
    _check(not stop, "scope-stop", "scope-not-stopped", checks, codes,
           detail=f"stop_scope={ctx.stop_scope} timeout={ctx.service_timeout} exemption={ctx.exemption_active}")


def _verify_plan(
    selection: LocalSelectionRecord,
    ctx: TrustedContext,
    checks: list[CheckItem],
    codes: list[str],
) -> None:
    """Matter/material/basis/parent drift checks against the CURRENT host
    expectations (selection only; an execution row carries none of these)."""
    _check(selection.matter_ref == ctx.matter_ref, "matter-drift", "matter-ref", checks, codes)
    _check(selection.matter_version == ctx.matter_version, "matter-version-drift",
           "matter-version", checks, codes)
    _check(selection.material_digest == ctx.material_digest, "material-drift",
           "material-digest", checks, codes)
    _check(selection.basis_digest == ctx.basis_digest, "basis-drift",
           "basis-digest", checks, codes)
    rec_parent = selection.parent_decision_ref
    ctx_parent = ctx.parent_decision_ref
    if rec_parent is None and ctx_parent is None:
        parent_ok = True
    elif isinstance(rec_parent, DpDecisionRef):
        # The trusted parent is data from the adapter interface, not a proof.
        # The FIRST and FINAL context must both pass the SAME frozen
        # parse_decision_ref discriminated shape: exactly {kind:'dp',decision_id}.
        # Mixed dp+local / extra keys / pure local / absent / wrong id fail closed.
        parsed_parent = parse_decision_ref(ctx_parent)
        parent_ok = (
            parsed_parent.ok
            and isinstance(parsed_parent.value, DpDecisionRef)
            and parsed_parent.value.decision_id == rec_parent.decision_id
        )
    else:
        parent_ok = False  # absent <-> present parent drift
    _check(parent_ok, "parent-drift", "parent-decision-ref", checks, codes)


def _deadline_passed(deadline: str) -> bool:
    try:
        parsed = _dt.datetime.fromisoformat(str(deadline).replace("Z", "+00:00"))
        now = _dt.datetime.now(_dt.timezone.utc)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=_dt.timezone.utc)
        return now > parsed
    except ValueError:
        return True  # unparseable deadline is not a usable budget


def _verify_selection_matches_execution(
    execution: LocalExecutionRecord,
    selection: LocalSelectionRecord | None,
    checks: list[CheckItem],
    codes: list[str],
) -> None:
    if selection is None:
        codes.append("missing-selection")
        checks.append(CheckItem("original-selection", False, "missing"))
        return
    same = (
        selection.local_ref == execution.local_ref
        and selection.source == execution.source
        and selection.budget_ref == execution.budget_ref
    )
    for name in HOST_IDENTITY_FIELDS:
        same = same and _identity(selection.host_binding, name) == _identity(execution.host_binding, name)
    _check(same, "selection-mismatch", "original-selection", checks, codes)


def _check_action_result_evidence(
    execution: LocalExecutionRecord,
    ctx: TrustedContext,
    evidence: ActionResultEvidence | None,
    checks: list[CheckItem],
    codes: list[str],
) -> None:
    if evidence is None:
        codes.append("missing-verifier")
        checks.append(CheckItem("host-action-result", False, "no verifier evidence"))
        return
    if not isinstance(evidence, ActionResultEvidence):
        # A bare bool / dict / string from the model is a self-proof, not host
        # verifier evidence; reject with an explicit code.
        codes.append("self-proof-rejected")
        checks.append(CheckItem("host-action-result", False, type(evidence).__name__))
        return
    action_result_present = (
        _nonblank(evidence.action_receipt_ref) and _nonblank(evidence.result_receipt_ref)
    )
    _check(action_result_present, "missing-action-result", "host-action-result-present", checks, codes)
    # ``confirmed`` must be exactly True (reject truthy non-bool self-proof).
    confirmed = evidence.confirmed is True
    verifier_present = (
        _nonblank(evidence.verifier_receipt_ref) and _nonblank(evidence.observed_object_digest)
    )
    _check(confirmed and verifier_present, "action-result-unverified",
           "host-action-result-confirmed", checks, codes)
    assoc = (
        evidence.action_receipt_ref == execution.action_ref
        and evidence.result_receipt_ref == execution.result_ref
        and evidence.verifier_receipt_ref == execution.verified_by
    )
    _check(assoc, "verifier-mismatch", "host-action-result-association", checks, codes)
    target_ok = (
        evidence.observed_object_digest == execution.target_digest == ctx.target_digest
    )
    _check(target_ok, "target-drift", "current-object-evidence", checks, codes)


def _verify_action_result(
    execution: LocalExecutionRecord,
    ctx: TrustedContext,
    adapter: HostEvidenceAdapter,
    checks: list[CheckItem],
    codes: list[str],
) -> ActionResultEvidence | None:
    """One host verifier call; return an INDEPENDENT immutable evidence snapshot
    so the final recheck can revalidate it without another host callback."""
    try:
        evidence = adapter.verify_execution(execution, ctx.target_digest)
    except Exception as exc:  # a host verifier failure is never a proof
        codes.append("action-result-unverified")
        checks.append(CheckItem("host-action-result", False, type(exc).__name__))
        return None
    _check_action_result_evidence(execution, ctx, evidence, checks, codes)
    if not isinstance(evidence, ActionResultEvidence):
        return None
    return ActionResultEvidence(
        action_receipt_ref=evidence.action_receipt_ref,
        result_receipt_ref=evidence.result_receipt_ref,
        verifier_receipt_ref=evidence.verifier_receipt_ref,
        observed_object_digest=evidence.observed_object_digest,
        confirmed=evidence.confirmed,
    )


def _verify_final_context(
    record: LocalSelectionRecord | LocalExecutionRecord,
    read: ReadResult,
    ctx: TrustedContext,
    evidence: ActionResultEvidence | None,
    checks: list[CheckItem],
    codes: list[str],
    *,
    key: str,
    source: str,
    local_ref: str,
    task_key: str | None,
) -> None:
    """Re-run the REAL semantic checks against the newly returned context, not
    just a hash/equality comparison. This re-evaluates the finite budget and
    deadline against the current clock, stop scope, and all associations."""
    _verify_request_identity(record, ctx, checks, codes, key=key, source=source,
                             local_ref=local_ref, task_key=task_key)
    _verify_binding(record, ctx, checks, codes, scope_task_key=task_key)
    if isinstance(record, LocalSelectionRecord):
        _verify_plan(record, ctx, checks, codes)
        return
    _verify_selection_matches_execution(record, read.selection, checks, codes)
    if read.selection is not None:
        _verify_request_identity(read.selection, ctx, checks, codes, key=key,
                                 source=source, local_ref=local_ref, task_key=task_key)
        _verify_binding(read.selection, ctx, checks, codes, scope_task_key=task_key)
        _verify_plan(read.selection, ctx, checks, codes)
    _check_action_result_evidence(record, ctx, evidence, checks, codes)


def _verify_final_path_state(
    root: pathlib.Path,
    read: ReadResult,
    checks: list[CheckItem],
    codes: list[str],
    *,
    key: str,
    source: str,
    local_ref: str,
    task_key: str | None,
) -> None:
    """After the LAST host callback, re-derive the real path chain, ancestor
    kinds, real redirect state, locks and both record byte streams. A matching
    hash is never a substitute for path identity. All operations are read-only;
    no lock, directory or invalid target is created, removed or repaired."""
    try:
        selection_path, execution_path, base, _ = _resolve_paths(
            root, key, source, local_ref, task_key
        )
    except _StrictFailure as exc:
        _check(False, exc.code, "final-path-derivation", checks, codes)
        return
    same_paths = (
        read.selection_path == str(selection_path)
        and read.execution_path == str(execution_path)
    )
    _check(same_paths, "path-outside-base", "final-derived-path", checks, codes)
    if not same_paths:
        return

    chain_code = ""
    try:
        for candidate in (base, selection_path, execution_path):
            _assert_path_chain_safe(root, candidate)
        root_real = os.path.realpath(str(root))
        base_rel = os.path.relpath(os.path.abspath(str(base)), root_real)
        current = root_real
        for comp in pathlib.PurePath(base_rel).parts:
            current = os.path.join(current, comp)
            st = os.lstat(current)
            if _is_redirect(current) or not stat.S_ISDIR(st.st_mode):
                raise _StrictFailure("wrong-file-kind", comp)
    except _StrictFailure as exc:
        chain_code = exc.code
    except OSError:
        chain_code = "wrong-file-kind"
    _check(not chain_code, chain_code or "unstable-snapshot",
           "final-path-chain", checks, codes, detail=chain_code)
    if chain_code:
        return

    selection_kind = _file_kind(selection_path)
    selection_code = "path-redirect" if selection_kind == "redirect" else "wrong-file-kind"
    expected_execution_kind = "absent" if read.execution_sha256 is None else "file"
    execution_kind = _file_kind(execution_path)
    execution_code = "path-redirect" if execution_kind == "redirect" else "wrong-file-kind"
    _check(selection_kind == "file", selection_code,
           "final-selection-kind", checks, codes, detail=selection_kind)
    _check(execution_kind == expected_execution_kind, execution_code,
           "final-execution-kind", checks, codes, detail=execution_kind)
    locks = _present_locks(root, base, selection_path, execution_path)
    _check(not locks, "unstable-snapshot", "final-locks-absent", checks, codes,
           detail="locks present" if locks else "")
    if selection_kind != "file" or execution_kind != expected_execution_kind or locks:
        return

    selection_bytes_ok = False
    selection_bytes_code = "unstable-snapshot"
    if read.selection_sha256 is not None:
        try:
            selection_bytes_ok = (
                hashlib.sha256(_stable_read_bytes(selection_path)).hexdigest()
                == read.selection_sha256
            )
        except _StrictFailure as exc:
            selection_bytes_code = exc.code
    _check(selection_bytes_ok, selection_bytes_code,
           "final-selection-bytes", checks, codes)

    execution_bytes_ok = expected_execution_kind == "absent"
    execution_bytes_code = "unstable-snapshot"
    if expected_execution_kind == "file" and read.execution_sha256 is not None:
        try:
            execution_bytes_ok = (
                hashlib.sha256(_stable_read_bytes(execution_path)).hexdigest()
                == read.execution_sha256
            )
        except _StrictFailure as exc:
            execution_bytes_code = exc.code
    _check(execution_bytes_ok, execution_bytes_code,
           "final-execution-bytes", checks, codes)

    try:
        snap_final = _snapshot_fingerprint(root, base, selection_path, execution_path)
        snap_ok = read.snapshot is not None and snap_final == read.snapshot
    except Exception as exc:
        checks.append(CheckItem("final-snapshot", False, "recheck error: " + type(exc).__name__))
        snap_ok = False
    _check(snap_ok, "unstable-snapshot", "final-snapshot", checks, codes)


def strict_verify(
    agenticdoc_root: pathlib.Path | str,
    key: str,
    source: str,
    local_ref: str,
    *,
    which: str = "selection",
    task_key: str | None = None,
    adapter: HostEvidenceAdapter | None = None,
) -> StrictResult:
    """Strict, read-only verification of a selection or an execution.

    ``which='selection'`` verifies the selection; ``which='execution'`` ALSO
    requires the original selection, the host action/result/target-verifier
    association and current object evidence.  A real ``HostEvidenceAdapter``
    is REQUIRED: without it the result is unverified (fail closed), regardless
    of how correct the JSON shape is.  Records real checks + concrete failure
    codes; the frozen record JSON is never extended.
    """
    root = _canonical_root(agenticdoc_root)
    if which not in ("selection", "execution"):
        return StrictResult(ok=False, value=None, verification="unverified",
                            host_source_verified=False, failure_codes=("bad-source",))

    read = read_local_evidence(root, key, source, local_ref, task_key=task_key)
    checks: list[CheckItem] = list(read.checks)
    codes: list[str] = list(read.failure_codes)

    # A present/appearing lock or an unstable read makes the snapshot unusable:
    # fail closed here rather than running host checks on untrustworthy bytes
    # (and avoid a misleading secondary selection/execution-not-found code).
    if "unstable-snapshot" in codes or "unstable-read" in codes:
        return StrictResult(ok=False, value=None, verification="unverified",
                            host_source_verified=False, checks=tuple(checks),
                            failure_codes=tuple(dict.fromkeys(codes)))

    # Trusted adapter is mandatory — a string/dict/bool/model self-report is not.
    if adapter is None or not isinstance(adapter, HostEvidenceAdapter):
        checks.append(CheckItem("trusted-adapter", False, "missing or wrong type"))
        return StrictResult(ok=False, value=None, verification="unverified",
                            host_source_verified=False, checks=tuple(checks),
                            failure_codes=tuple(codes + ["missing-trusted-adapter"]))
    checks.append(CheckItem("trusted-adapter", True))
    try:
        ctx = adapter.current_context()
    except Exception as exc:
        checks.append(CheckItem("trusted-context", False, type(exc).__name__))
        return StrictResult(ok=False, value=None, verification="unverified",
                            host_source_verified=False, checks=tuple(checks),
                            failure_codes=tuple(codes + ["missing-trusted-context"]))
    if ctx is None or not isinstance(ctx, TrustedContext):
        checks.append(CheckItem("trusted-context", False, "missing"))
        return StrictResult(ok=False, value=None, verification="unverified",
                            host_source_verified=False, checks=tuple(checks),
                            failure_codes=tuple(codes + ["missing-trusted-context"]))
    checks.append(CheckItem("trusted-context", True))
    # T03-R2: capture an IMMUTABLE semantic projection before any later host
    # callback can mutate nested budget/parent values in place. Reprojecting
    # the same shared object after the callback would erase the drift.
    try:
        initial_state = _context_state(ctx)
    except Exception as exc:
        checks.append(CheckItem("trusted-context", False,
                               "unserializable context: " + type(exc).__name__))
        return StrictResult(ok=False, value=None, verification="unverified",
                            host_source_verified=False, checks=tuple(checks),
                            failure_codes=tuple(codes + ["context-drift"]))
    action_evidence: ActionResultEvidence | None = None

    if which == "selection":
        record = read.selection
        if record is None:
            return StrictResult(ok=False, value=None, verification="unverified",
                                host_source_verified=False, checks=tuple(checks),
                                failure_codes=tuple(codes + ["selection-not-found"]))
        # T03-R1 PY01/02/03: the REQUEST identity must bind to the loaded
        # record AND the trusted host, not merely to a shape-valid file.
        _verify_request_identity(record, ctx, checks, codes, key=key, source=source,
                                 local_ref=local_ref, task_key=task_key)
        _verify_binding(record, ctx, checks, codes, scope_task_key=task_key)
        _verify_plan(record, ctx, checks, codes)
        value: object = record
    else:
        record = read.execution
        if record is None:
            return StrictResult(ok=False, value=None, verification="unverified",
                                host_source_verified=False, checks=tuple(checks),
                                failure_codes=tuple(codes + ["execution-not-found"]))
        _verify_request_identity(record, ctx, checks, codes, key=key, source=source,
                                 local_ref=local_ref, task_key=task_key)
        _verify_binding(record, ctx, checks, codes, scope_task_key=task_key)
        _verify_selection_matches_execution(record, read.selection, checks, codes)
        if read.selection is not None:
            # verify the ORIGINAL selection's binding + matter/material/basis/
            # parent/budget against the same current context: an execution
            # cannot outlive a stale plan. The request must ALSO bind to the
            # original selection, not just the execution.
            _verify_request_identity(read.selection, ctx, checks, codes, key=key,
                                     source=source, local_ref=local_ref, task_key=task_key)
            _verify_binding(read.selection, ctx, checks, codes, scope_task_key=task_key)
            _verify_plan(read.selection, ctx, checks, codes)
        action_evidence = _verify_action_result(record, ctx, adapter, checks, codes)
        value = record

    # T03-R2 FINAL recheck. This is the LAST host callback: afterwards the new
    # context is fully revalidated against the real current clock, budget,
    # stop and associations, then the real path chain, ancestor/file kinds,
    # redirects, locks and both byte streams are rechecked locally. No host
    # call follows these checks and no stale prior conclusion is reused. This
    # is a best-effort final recheck, NOT a fully race-free / TOCTOU-free
    # handle protocol.
    if not codes:
        ctx2: object = None
        ctx_state_ok = False
        try:
            ctx2 = adapter.current_context()
            ctx_state_ok = (
                isinstance(ctx2, TrustedContext)
                and _context_state(ctx2) == initial_state
            )
        except Exception as exc:
            checks.append(CheckItem("final-context", False,
                                   "recheck error: " + type(exc).__name__))
        _check(ctx_state_ok, "context-drift", "final-context", checks, codes)
        if isinstance(ctx2, TrustedContext):
            try:
                _verify_final_context(record, read, ctx2, action_evidence, checks, codes,
                                      key=key, source=source, local_ref=local_ref,
                                      task_key=task_key)
            except Exception as exc:
                checks.append(CheckItem("final-context-checks", False,
                                       "recheck error: " + type(exc).__name__))
                codes.append("context-drift")
        else:
            _check(False, "missing-trusted-context", "final-context-instance",
                   checks, codes)
        try:
            _verify_final_path_state(root, read, checks, codes, key=key,
                                     source=source, local_ref=local_ref,
                                     task_key=task_key)
        except Exception as exc:
            checks.append(CheckItem("final-path-checks", False,
                                   "recheck error: " + type(exc).__name__))
            codes.append("unstable-snapshot")

    verified = not codes and adapter is not None
    return StrictResult(
        ok=not codes, value=value,
        verification="strict-verified" if verified else "unverified",
        host_source_verified=verified, authority_required=False,
        checks=tuple(checks), failure_codes=tuple(dict.fromkeys(codes)),
    )
