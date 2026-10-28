"""decision_validity.py - read-only matter / substantive-version / authority /
evidence applicability judgements for the eight consolidated decision entries.

Card T06 (key ``mw-dp-consolidation``) and design.md section 4.3 / 4.5:

* :func:`matter_for` builds a ``Matter`` from the *business* identity
  (subject, object, action) plus the declared substantive dependencies. It has
  no gate-kind / file-name / label input, so the same subject/object/action is
  one matter no matter which gate file or label replays it.
* A semantic version is derived only from the declared structure of a
  dependency (scope, AC/VC items, dependency edges, restricted file actions,
  hard-budget unit/limit, evidence results, stop/revocation reasons). Pure
  whitespace, line-ending, key-order and set-order differences keep the same
  digest; a full-file ``byte_sha256`` is traceability only and never decides
  substantive invalidation.
* Natural-language dependencies are ``prose``: a difference beyond formatting
  is *unknown*, never silently equal and never silently a definite change. The
  caller must obtain a real clarification; this module only records the
  unknown, it does not manufacture one.
* :func:`assess_validity` returns ``valid`` / ``stale`` / ``blocked`` with
  specific reasons. ``stale`` lists the affected dependencies so only the
  affected approvals/evidence are invalidated; unrelated evidence stays
  reusable. ``blocked`` is fail-closed (unknown state, revoked/missing
  authority, wrong actor/role, non-answered transport, unknown effect, a
  retired entry, a route selection, or an entry that is not the single
  business owner of the matter kind).
* :func:`assess_evidence`, :func:`assess_goal_change`,
  :func:`assess_contract_change`, :func:`assess_claim`,
  :func:`assess_write_surface`, :func:`assess_signoff` and
  :func:`plan_actions` are the remaining pure judgements. None of them writes
  a grant, a decision row, a gate, a signoff, a claim or a file.
* Fail-closed boundaries: a *required* successful signoff is only the
  ``finalize`` word (``continue`` / ``user-confirm`` stay legal menu words but
  are not a signoff), bound to the required key and to a non-empty traceable
  reference; evidence pinned to a different contract version is recorded and
  is not reusable; one unusable claimed path fails the whole request and an
  active claim on another task of the same owner is not clear; a matched effect
  record whose status is unrecognised or missing blocks instead of being read
  as "never executed".

Design section 4.3: "a decision is valid only when the current role, matter,
contract, substantive evidence and authorization still apply". Reuse of a
still-valid judgement does not create a second approval; repeating an action
is left to the real consumer (CAS/lock/reconciliation) and this module only
judges what is a duplicate.

Pure module: stdlib only, no CLI/conductor/decision/autopilot import, no I/O.
"""

from __future__ import annotations

import hashlib
import json
import posixpath
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any

#: The exact eight active decision entries (spec section 1.1 order). Repeating
#: the tuple here keeps this module importable without the decide stack; the
#: registry contract test (T03) remains the single-source authority and T31
#: can cross-check the two lists.
ACTIVE_ENTRIES: tuple[str, ...] = (
    "dp-w-type",
    "dp-pm-steer",
    "dp-w-check-task",
    "dp-QG",
    "dp-gate-approve",
    "dp-sign-key",
    "dp-auto",
    "dp-route",
)

#: Matter kind -> the one entry that owns the business approval for it.
#: ``routing`` has no business owner: ``dp-route`` only names another entry.
MATTER_OWNERS: Mapping[str, str | None] = MappingProxyType(
    {
        "dispatch-type": "dp-w-type",
        "steering": "dp-pm-steer",
        "task-check": "dp-w-check-task",
        "quality": "dp-QG",
        "gate-action": "dp-gate-approve",
        "key-signoff": "dp-sign-key",
        "dynamic-choice": "dp-auto",
        "routing": None,
    }
)
MATTER_KINDS: tuple[str, ...] = tuple(MATTER_OWNERS)

DEPENDENCY_KINDS: tuple[str, ...] = ("structured", "set", "prose", "ref")
EVIDENCE_KINDS: tuple[str, ...] = ("quality", "verification", "review", "signoff")

#: The only signoff words: the same three words as ``dp-sign-key``. They are
#: the menu the decision entry may offer, not three equivalents of a required
#: successful signoff (see ``REQUIRED_SIGNOFF_CHOICES``).
FINALIZE_CHOICES: tuple[str, ...] = ("finalize", "continue", "user-confirm")
#: The only word that satisfies a *required* successful signoff.
REQUIRED_SIGNOFF_CHOICES: tuple[str, ...] = ("finalize",)
#: Old labels that must not satisfy a required signoff by name alone.
LEGACY_SIGNOFF_WORDS: frozenset[str] = frozenset(
    {"approve", "approved", "sign", "signed", "lgtm", "done", "pass", "passed",
     "promote", "demote", "ack", "acked", "ok", "closed"}
)

TRANSPORT_ANSWERED = "answered"
EFFECT_STATES: tuple[str, ...] = (
    "not-started",
    "in-progress",
    "applied",
    "blocked",
    "failed",
    "unknown",
)

#: Sources that are never authority by themselves (design section 4.5: an
#: editable file, a boolean preauthorized flag, a page token or an agent report
#: is not a real grant).
WEAK_AUTHORITY_SOURCES: frozenset[str] = frozenset(
    {
        "",
        "true",
        "false",
        "yes",
        "no",
        "1",
        "0",
        "editable",
        "preauthorized",
        "pre-authorized",
        "token",
        "page-token",
        "agent-report",
        "self-report",
        "self",
        "report",
    }
)

_STALE_CODES: frozenset[str] = frozenset(
    {"contract_version_changed", "substantive_change", "stale_signoff"}
)
_RERUN_CODES: frozenset[str] = frozenset(
    {"contract_version_changed", "substantive_change", "unknown_substantive_change",
     "unknown_substantive_state"}
)


class _UnknownSubstantive:
    """Sentinel for "the current substantive state could not be read"."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "UNKNOWN_SUBSTANTIVE"


UNKNOWN_SUBSTANTIVE = _UnknownSubstantive()


# ---------------------------------------------------------------------------
# Reasons and values
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerdictReason:
    """One specific reason; ``code`` is stable, ``detail`` is informational."""

    code: str
    field: str | None = None
    detail: str = ""


@dataclass(frozen=True)
class SemanticVersion:
    kind: str
    digest: str

    def render(self) -> str:
        return f"{self.kind}:{self.digest}"


@dataclass(frozen=True)
class Comparison:
    """Result of comparing two substantive dependency values."""

    status: str
    left: str | None
    right: str | None
    detail: str


@dataclass(frozen=True)
class DependencyState:
    """One declared substantive dependency.

    ``byte_sha256`` is traceability only: it is deliberately excluded from both
    the matter identity and the substantive version.
    """

    name: str
    kind: str
    value: Any
    byte_sha256: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name.strip():
            raise ValueError("dependency name must be a non-empty string")
        if self.kind not in DEPENDENCY_KINDS:
            raise ValueError(f"unknown dependency kind {self.kind!r}")

    @property
    def digest(self) -> str:
        if self.value is UNKNOWN_SUBSTANTIVE:
            return "unknown"
        return semantic_version(self.kind, self.value).render()

    @property
    def unknown(self) -> bool:
        return self.value is UNKNOWN_SUBSTANTIVE


@dataclass(frozen=True, eq=False)
class Matter:
    """Business identity plus its declared substantive dependencies."""

    subject: str
    object: str
    action: str
    matter_kind: str
    dependencies: tuple[DependencyState, ...]
    contract_version: str
    authority_required: bool = False
    matter_key: str = ""
    substantive_version: str = ""

    @property
    def unknown_dependencies(self) -> tuple[str, ...]:
        return tuple(dep.name for dep in self.dependencies if dep.unknown)

    def dependency(self, name: str) -> DependencyState:
        for dep in self.dependencies:
            if dep.name == name:
                return dep
        raise KeyError(name)


@dataclass(frozen=True)
class DependencyChange:
    name: str
    status: str
    previous: str | None
    current: str | None
    detail: str = ""


@dataclass(frozen=True)
class Validity:
    status: str
    reasons: tuple[VerdictReason, ...]
    affected_dependencies: tuple[str, ...] = ()
    unaffected_dependencies: tuple[str, ...] = ()

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.reasons)

    @property
    def requires_reapproval(self) -> bool:
        """True when the judging subject must judge again before any effect."""

        return any(code in _RERUN_CODES for code in self.reason_codes)


@dataclass(frozen=True, eq=False)
class DecisionRecord:
    """A read-only snapshot of one answered decision (never written here)."""

    decision_id: str
    entry: str
    actor: str
    role: str
    matter: Matter
    choice: str
    authority_ref: str | None = None
    evidence_refs: tuple[str, ...] = ()
    transport: str = TRANSPORT_ANSWERED
    effect: str = "not-started"
    revoked: bool = False
    historical: bool = False


@dataclass(frozen=True)
class DedupeVerdict:
    status: str
    same_matter_versions: tuple[str, ...]
    additional_approvals: int
    conflicting: tuple[str, ...] = ()
    detail: str = ""


@dataclass(frozen=True, eq=False)
class EvidenceRef:
    evidence_id: str
    kind: str
    matter_key: str
    contract_version: str
    covered_dependencies: tuple[tuple[str, str], ...]
    byte_sha256: str | None = None


@dataclass(frozen=True)
class EvidenceApplicability:
    status: str
    reasons: tuple[VerdictReason, ...]
    stale_dependencies: tuple[str, ...] = ()
    unaffected_changes: tuple[str, ...] = ()
    reusable: bool = False

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.reasons)


@dataclass(frozen=True, eq=False)
class AuthorityRef:
    authority_ref: str
    actor: str
    status: str
    source: str
    objects: tuple[str, ...]
    actions: tuple[str, ...]
    files: tuple[str, ...] = ()
    budget_limits: tuple[tuple[str, float], ...] = ()
    budget_usage: tuple[tuple[str, float], ...] = ()

    @property
    def budget_usage_map(self) -> dict[str, float]:
        return dict(self.budget_usage)


@dataclass(frozen=True)
class AuthorityApplicability:
    status: str
    reasons: tuple[VerdictReason, ...]
    applicable: bool = False

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.reasons)


@dataclass(frozen=True, eq=False)
class ApprovalBinding:
    approval_id: str
    object: str
    dependency_names: tuple[str, ...]
    matter_key: str
    substantive_version: str


@dataclass(frozen=True)
class UserDecisionItem:
    dependency: str
    code: str
    detail: str


@dataclass(frozen=True)
class GoalImpact:
    status: str
    reasons: tuple[VerdictReason, ...]
    affected_dependencies: tuple[str, ...] = ()
    unaffected_dependencies: tuple[str, ...] = ()
    stale_bindings: tuple[str, ...] = ()
    reusable_bindings: tuple[str, ...] = ()
    unknown_bindings: tuple[str, ...] = ()
    user_decisions: tuple[UserDecisionItem, ...] = ()

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.reasons)


@dataclass(frozen=True, eq=False)
class ContractChange:
    key: str
    items: tuple[str, ...]
    before: str
    after: str
    reason: str
    commitment_impact: str
    evidence_impact: str
    authority_ref: str
    reverification_plan: str
    acceptance_reductions: tuple[str, ...] = ()


@dataclass(frozen=True, eq=False)
class ChangeApproval:
    approval_ref: str
    key: str
    items: tuple[str, ...]
    before: str
    after: str
    reverification_plan: str
    authority_source: str
    acceptance_reductions: tuple[str, ...] = ()


@dataclass(frozen=True)
class ContractChangeVerdict:
    status: str
    reasons: tuple[VerdictReason, ...]
    approved_items: tuple[str, ...] = ()
    reverification_items: tuple[str, ...] = ()
    covers_only_requested_change: bool = False

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.reasons)


@dataclass(frozen=True, eq=False)
class Claim:
    owner: str
    task_key: str
    files: tuple[str, ...]
    active: bool = True
    lock_mode: str = "exclusive"


@dataclass(frozen=True, eq=False)
class ClaimRequest:
    actor: str
    task_key: str
    files: tuple[str, ...]
    decision_ref: str | None = None


@dataclass(frozen=True)
class ClaimVerdict:
    status: str
    reasons: tuple[VerdictReason, ...]
    conflicts: tuple[str, ...] = ()
    conflicting_owners: tuple[str, ...] = ()
    takeover: bool = False
    lock_mode: str = "exclusive"
    decision_grants_claim: bool = False
    dispatched: bool = False

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.reasons)


@dataclass(frozen=True)
class SurfaceViolation:
    code: str
    path: str


@dataclass(frozen=True)
class SurfaceVerdict:
    status: str
    violations: tuple[SurfaceViolation, ...] = ()


@dataclass(frozen=True)
class SelectionEffects:
    contract_change: bool = False
    stage_closure: bool = False
    signoff_written: bool = False
    dispatch: bool = False
    needs_separate_authorization: bool = True


@dataclass(frozen=True, eq=False)
class SignoffRef:
    signoff_ref: str | None
    choice: str
    key: str
    matter_key: str
    substantive_version: str
    scope: tuple[str, ...]
    artifact_ref: str | None
    disable_requested: bool = False
    historical: bool = False


@dataclass(frozen=True)
class SignoffVerdict:
    status: str
    reasons: tuple[VerdictReason, ...]
    writes_signoff: bool = False
    widens_scope: bool = False

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.reasons)


@dataclass(frozen=True, eq=False)
class EffectRecord:
    effect_id: str
    decision_id: str
    matter_key: str
    substantive_version: str
    actions: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class ActionPlan:
    status: str
    reasons: tuple[VerdictReason, ...]
    actions: tuple[str, ...] = ()
    duplicate_actions: tuple[str, ...] = ()
    blocked: tuple[str, ...] = ()

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.reasons)


# ---------------------------------------------------------------------------
# Canonicalisation and comparison
# ---------------------------------------------------------------------------


def _normalise_text(text: str) -> str:
    """Formatting-insensitive text: CRLF/CR -> LF, trimmed trailing spaces,
    single spaces inside a line, no leading/trailing blank lines."""

    normalised = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [" ".join(line.split()) for line in normalised.split("\n")]
    while lines and not lines[0]:
        lines.pop(0)
    while lines and not lines[-1]:
        lines.pop()
    return "\n".join(lines)


def _stable(value: Any) -> str:
    """Deterministic canonical JSON used only for the semantic digest."""

    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        return str(int(value)) if value.is_integer() else repr(value)
    if isinstance(value, str):
        return json.dumps(_normalise_text(value), ensure_ascii=False)
    if isinstance(value, Mapping):
        if set(value) == {"$set"} and isinstance(value["$set"], (list, tuple)):
            members = sorted({_stable(item) for item in value["$set"]})
            return '{"$set":[' + ",".join(members) + "]}"
        body = ",".join(
            json.dumps(str(key), ensure_ascii=False) + ":" + _stable(value[key])
            for key in sorted(value, key=str)
        )
        return "{" + body + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_stable(item) for item in value) + "]"
    return json.dumps(_normalise_text(str(value)), ensure_ascii=False)


def _raw(value: Any) -> str:
    """Raw JSON used to distinguish identical from merely equivalent values."""

    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=False, default=str)
    except (TypeError, ValueError):
        return repr(value)


def semantic_version(kind: str, value: Any) -> SemanticVersion:
    """Semantic version of a declared dependency value.

    ``byte_sha256`` is not part of this: the caller keeps bytes only for
    integrity/traceability.
    """

    if kind not in DEPENDENCY_KINDS:
        raise ValueError(f"unknown dependency kind {kind!r}")
    if value is UNKNOWN_SUBSTANTIVE:
        raise ValueError("an unknown substantive state has no semantic version")
    if kind == "set":
        if not isinstance(value, (list, tuple, set, frozenset)):
            raise ValueError("a set dependency value must be a collection")
        canonical = '{"$set":[' + ",".join(
            sorted({_stable(item) for item in value})
        ) + "]}"
    elif kind in {"prose", "ref"}:
        canonical = json.dumps(_normalise_text(str(value)), ensure_ascii=False)
    else:
        canonical = _stable(value)
    digest = hashlib.sha256(f"{kind}\x1f{canonical}".encode("utf-8")).hexdigest()
    return SemanticVersion(kind=kind, digest=digest)


def compare_dependency_values(kind: str, left: Any, right: Any) -> Comparison:
    """Compare two values of one dependency kind.

    - ``identical``: the raw values are equal;
    - ``equivalent``: only formatting/line-ending/key-order/set-order differs;
    - ``changed``: a structural difference (structured/set/ref kinds);
    - ``unknown``: natural language differs beyond formatting, or a side is
      explicitly unknown. The caller must not treat this as equal or as a
      definite change, and must not start on it.
    """

    if kind not in DEPENDENCY_KINDS:
        raise ValueError(f"unknown dependency kind {kind!r}")
    if left is UNKNOWN_SUBSTANTIVE or right is UNKNOWN_SUBSTANTIVE:
        return Comparison("unknown", None, None, "substantive_state_unknown")
    left_version = semantic_version(kind, left)
    right_version = semantic_version(kind, right)
    if _raw(left) == _raw(right):
        return Comparison(
            "identical", left_version.render(), right_version.render(), "identical"
        )
    if left_version.digest == right_version.digest:
        return Comparison(
            "equivalent",
            left_version.render(),
            right_version.render(),
            "formatting_or_order_only",
        )
    if kind == "prose":
        return Comparison(
            "unknown",
            left_version.render(),
            right_version.render(),
            "prose_text_differs",
        )
    return Comparison(
        "changed", left_version.render(), right_version.render(), "value_changed"
    )


# ---------------------------------------------------------------------------
# Matter identity
# ---------------------------------------------------------------------------


def business_owner_for(matter_kind: str) -> str | None:
    """The single business approval owner of a matter kind (``None`` for route)."""

    if matter_kind not in MATTER_OWNERS:
        raise ValueError(f"unknown matter kind {matter_kind!r}")
    return MATTER_OWNERS[matter_kind]


def _matter_key(subject: str, object_: str, action: str) -> str:
    payload = f"{subject}\x1f{object_}\x1f{action}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _substantive_version(dependencies: Sequence[DependencyState]) -> str:
    payload = "\n".join(
        f"{dep.name}\x1f{dep.kind}\x1f{dep.digest}"
        for dep in sorted(dependencies, key=lambda dep: dep.name)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _require_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string")
    return value.strip()


def matter_for(
    subject: str,
    object: str,
    proposed_action: str,
    substantive_dependencies: Sequence[DependencyState],
    *,
    matter_kind: str,
    contract_version: str,
    authority_required: bool = False,
) -> Matter:
    """Build the read-only matter reference (design section 4.3).

    Only subject/object/action and the declared dependencies take part. No gate
    kind, file name, label, sha or model text can turn one matter into another.
    """

    normalised_subject = _require_text(subject, "subject")
    normalised_object = _require_text(object, "object")
    normalised_action = _require_text(proposed_action, "proposed_action")
    if matter_kind not in MATTER_OWNERS:
        raise ValueError(f"unknown matter kind {matter_kind!r}")
    normalised_contract = _require_text(contract_version, "contract_version")

    dependencies: list[DependencyState] = []
    seen: set[str] = set()
    for dep in substantive_dependencies:
        if not isinstance(dep, DependencyState):
            raise ValueError("dependencies must be DependencyState instances")
        if dep.name in seen:
            raise ValueError(f"duplicate dependency name {dep.name!r}")
        seen.add(dep.name)
        dependencies.append(dep)
    dependencies.sort(key=lambda dep: dep.name)

    return Matter(
        subject=normalised_subject,
        object=normalised_object,
        action=normalised_action,
        matter_kind=matter_kind,
        dependencies=tuple(dependencies),
        contract_version=normalised_contract,
        authority_required=authority_required,
        matter_key=_matter_key(
            normalised_subject, normalised_object, normalised_action
        ),
        substantive_version=_substantive_version(dependencies),
    )


def dependency_diff(
    previous: Matter, current: Matter
) -> tuple[DependencyChange, ...]:
    """One change row per declared dependency; sorted, deterministic."""

    previous_by_name = {dep.name: dep for dep in previous.dependencies}
    current_by_name = {dep.name: dep for dep in current.dependencies}
    changes: list[DependencyChange] = []
    for name in sorted(set(previous_by_name) | set(current_by_name)):
        before = previous_by_name.get(name)
        after = current_by_name.get(name)
        if before is None and after is not None:
            changes.append(
                DependencyChange(name, "added", None, after.digest, "dependency_added")
            )
        elif before is not None and after is None:
            changes.append(
                DependencyChange(
                    name, "removed", before.digest, None, "dependency_removed"
                )
            )
        else:
            assert before is not None and after is not None
            if before.kind != after.kind:
                changes.append(
                    DependencyChange(
                        name,
                        "changed",
                        before.digest,
                        after.digest,
                        "dependency_kind_changed",
                    )
                )
                continue
            comparison = compare_dependency_values(
                before.kind, before.value, after.value
            )
            changes.append(
                DependencyChange(
                    name,
                    comparison.status,
                    comparison.left,
                    comparison.right,
                    comparison.detail,
                )
            )
    return tuple(changes)


# ---------------------------------------------------------------------------
# Validity
# ---------------------------------------------------------------------------


def assess_validity(
    decision: DecisionRecord,
    current_matter: Matter,
    *,
    bound_actor: str,
    bound_role: str,
    authority: AuthorityRef | None = None,
    contract_version: str | None = None,
) -> Validity:
    """Judge whether ``decision`` still applies to ``current_matter``.

    ``valid`` means "this answered decision is still applicable"; it is not a
    release, an execution or a completion. ``stale`` invalidates only the
    affected dependencies (listed) and asks for a new judgement; ``blocked`` is
    fail-closed with specific reasons.
    """

    if not isinstance(decision, DecisionRecord):
        raise ValueError("decision must be a DecisionRecord")
    if not isinstance(current_matter, Matter):
        raise ValueError("current_matter must be a Matter")

    reasons: list[VerdictReason] = []

    if decision.historical:
        reasons.append(
            VerdictReason("historical_readonly", "decision", "retired history")
        )
    if decision.entry not in ACTIVE_ENTRIES:
        reasons.append(
            VerdictReason(
                "retired_or_unknown_entry", "entry", decision.entry
            )
        )
    if decision.revoked:
        reasons.append(
            VerdictReason("decision_revoked", "decision", decision.decision_id)
        )

    owner = MATTER_OWNERS.get(decision.matter.matter_kind)
    if owner is None:
        reasons.append(
            VerdictReason(
                "route_not_business_owner",
                "entry",
                decision.matter.matter_kind,
            )
        )
    elif decision.entry != owner:
        reasons.append(VerdictReason("not_business_owner", "entry", owner))

    if decision.actor != bound_actor:
        reasons.append(VerdictReason("actor_mismatch", "actor", bound_actor))
    if decision.role != bound_role:
        reasons.append(VerdictReason("role_mismatch", "role", bound_role))
    if decision.transport != TRANSPORT_ANSWERED:
        reasons.append(
            VerdictReason("transport_not_answered", "transport", decision.transport)
        )
    if decision.effect == "unknown":
        reasons.append(VerdictReason("effect_unknown", "effect", decision.effect))

    current_contract = contract_version or current_matter.contract_version
    if decision.matter.contract_version != current_contract:
        reasons.append(
            VerdictReason(
                "contract_version_changed",
                "contract_version",
                f"{decision.matter.contract_version} -> {current_contract}",
            )
        )
    if decision.matter.matter_key != current_matter.matter_key:
        reasons.append(
            VerdictReason("different_matter", "matter_key", current_matter.matter_key)
        )

    if current_matter.authority_required and decision.authority_ref is None:
        reasons.append(
            VerdictReason("authority_unverified", "authority", "no authority reference")
        )
    if authority is not None:
        if (
            decision.authority_ref is not None
            and decision.authority_ref != authority.authority_ref
        ):
            reasons.append(
                VerdictReason(
                    "authority_ref_mismatch",
                    "authority",
                    authority.authority_ref,
                )
            )
        applicability = assess_authority(
            authority, current_matter, bound_actor=bound_actor
        )
        if not applicability.applicable:
            reasons.extend(applicability.reasons)
    elif decision.authority_ref is not None:
        reasons.append(
            VerdictReason("authority_unverified", "authority", "authority not readable")
        )

    changes = dependency_diff(decision.matter, current_matter)
    affected = tuple(
        change.name
        for change in changes
        if change.status in {"changed", "added", "removed"}
    )
    unaffected = tuple(
        change.name
        for change in changes
        if change.status in {"identical", "equivalent"}
    )
    for change in changes:
        if change.status == "unknown":
            reasons.append(
                VerdictReason(
                    "unknown_substantive_change", change.name, change.detail
                )
            )
        elif change.status in {"changed", "added", "removed"}:
            reasons.append(
                VerdictReason("substantive_change", change.name, change.detail)
            )
    if current_matter.unknown_dependencies:
        reasons.append(
            VerdictReason(
                "unknown_substantive_state",
                "dependencies",
                ",".join(current_matter.unknown_dependencies),
            )
        )

    if any(reason.code not in _STALE_CODES for reason in reasons):
        status = "blocked"
    elif reasons:
        status = "stale"
    else:
        status = "valid"
    return Validity(
        status=status,
        reasons=tuple(reasons),
        affected_dependencies=affected,
        unaffected_dependencies=unaffected,
    )


def dedupe_decisions(
    existing: Sequence[DecisionRecord], candidate: DecisionRecord
) -> DedupeVerdict:
    """Replay/dedupe judgement for one matter.

    A second answer for the same matter and the same substantive version is a
    duplicate (or a conflict when the answers differ); it never adds a second
    approval. A new substantive version needs a real new judgement.
    """

    same_matter = [
        record
        for record in existing
        if record.matter.matter_key == candidate.matter.matter_key
    ]
    if not same_matter:
        return DedupeVerdict("new", (), 1, (), "no approval for this matter")
    same_version = [
        record
        for record in same_matter
        if record.matter.substantive_version
        == candidate.matter.substantive_version
        and record.matter.contract_version == candidate.matter.contract_version
    ]
    if not same_version:
        return DedupeVerdict(
            "new",
            tuple(record.decision_id for record in same_matter),
            1,
            (),
            "new substantive version needs a new judgement",
        )
    ids = tuple(record.decision_id for record in same_version)
    same_answer = [
        record
        for record in same_version
        if record.entry == candidate.entry and record.choice == candidate.choice
    ]
    if same_answer:
        return DedupeVerdict(
            "duplicate", ids, 0, (), "same matter and substantive version"
        )
    return DedupeVerdict(
        "conflict", ids, 0, ids, "different answers for one substantive version"
    )


# ---------------------------------------------------------------------------
# Evidence applicability
# ---------------------------------------------------------------------------


def evidence_for(
    evidence_id: str,
    kind: str,
    matter: Matter,
    covered: Sequence[str],
    *,
    contract_version: str | None = None,
    byte_sha256: str | None = None,
) -> EvidenceRef:
    """Pin the dependency versions an evidence item actually covered."""

    evidence_id = _require_text(evidence_id, "evidence_id")
    if kind not in EVIDENCE_KINDS:
        raise ValueError(f"unknown evidence kind {kind!r}")
    covered_names = tuple(sorted(set(covered)))
    for name in covered_names:
        matter.dependency(name)  # raises KeyError when undeclared
    return EvidenceRef(
        evidence_id=evidence_id,
        kind=kind,
        matter_key=matter.matter_key,
        contract_version=contract_version or matter.contract_version,
        covered_dependencies=tuple(
            (name, matter.dependency(name).digest) for name in covered_names
        ),
        byte_sha256=byte_sha256,
    )


def assess_evidence(
    evidence: EvidenceRef,
    current_matter: Matter,
    *,
    previous_matter: Matter | None = None,
) -> EvidenceApplicability:
    """Judgement for one evidence item (read-only, no re-approval by hash).

    A contract-version change is recorded *and* it stops reuse: the evidence was
    produced against a different contract, so ``applies``/``reusable`` may not
    survive it. Unaffected dependencies of the same contract and byte-only or
    formatting-only differences still reuse without a new review.
    """

    if evidence.matter_key != current_matter.matter_key:
        return EvidenceApplicability(
            "not_applicable",
            (VerdictReason("different_matter", "matter_key", current_matter.matter_key),),
        )
    reasons: list[VerdictReason] = []
    stale: list[str] = []
    unknown = False
    contract_changed = False
    if evidence.contract_version != current_matter.contract_version:
        contract_changed = True
        reasons.append(
            VerdictReason(
                "contract_version_changed",
                "contract_version",
                current_matter.contract_version,
            )
        )
    current = {dep.name: dep for dep in current_matter.dependencies}
    for name, version in evidence.covered_dependencies:
        dep = current.get(name)
        if dep is None:
            reasons.append(VerdictReason("dependency_removed", name, ""))
            stale.append(name)
            continue
        if dep.unknown:
            reasons.append(
                VerdictReason("unknown_substantive_state", name, "")
            )
            unknown = True
            continue
        if dep.digest == version:
            continue
        if dep.kind == "prose":
            reasons.append(
                VerdictReason("prose_equivalence_unverified", name, "prose_text_differs")
            )
            unknown = True
        else:
            reasons.append(VerdictReason("dependency_changed", name, ""))
            stale.append(name)

    unaffected_changes: tuple[str, ...] = ()
    if previous_matter is not None and (
        previous_matter.matter_key == current_matter.matter_key
    ):
        covered_names = {name for name, _version in evidence.covered_dependencies}
        unaffected_changes = tuple(
            change.name
            for change in dependency_diff(previous_matter, current_matter)
            if change.status in {"changed", "added", "removed", "unknown"}
            and change.name not in covered_names
        )

    if unknown:
        status = "unknown"
    elif stale or contract_changed:
        status = "stale"
    else:
        status = "applies"
    return EvidenceApplicability(
        status=status,
        reasons=tuple(reasons),
        stale_dependencies=tuple(stale),
        unaffected_changes=unaffected_changes,
        reusable=status == "applies",
    )


# ---------------------------------------------------------------------------
# Authorization applicability
# ---------------------------------------------------------------------------


def _source_is_weak(source: Any) -> bool:
    if not isinstance(source, str):
        return True
    return source.strip().lower() in WEAK_AUTHORITY_SOURCES


def _write_face_files(matter: Matter) -> tuple[str, ...]:
    files: list[str] = []
    for dep in matter.dependencies:
        if dep.name != "write-face" or dep.value is UNKNOWN_SUBSTANTIVE:
            continue
        if isinstance(dep.value, str):
            files.append(dep.value)
        elif isinstance(dep.value, (list, tuple, set, frozenset)):
            files.extend(str(item) for item in dep.value)
    return tuple(files)


def assess_authority(
    authority: AuthorityRef,
    matter: Matter,
    *,
    bound_actor: str | None = None,
) -> AuthorityApplicability:
    """Read-only check that the referenced authority still covers this matter.

    It never creates a grant and never widens a scope; a missing usage figure
    with a declared budget is a block, not a zero.
    """

    if authority.status == "revoked":
        return AuthorityApplicability(
            "revoked",
            (VerdictReason("authority_revoked", "authority", authority.authority_ref),),
        )
    if authority.status == "expired":
        return AuthorityApplicability(
            "expired",
            (VerdictReason("authority_expired", "authority", authority.authority_ref),),
        )
    if authority.status != "active":
        return AuthorityApplicability(
            "unknown",
            (
                VerdictReason(
                    "authority_unverified", "authority", authority.status or "missing"
                ),
            ),
        )

    reasons: list[VerdictReason] = []
    if _source_is_weak(authority.source):
        reasons.append(
            VerdictReason(
                "insufficient_authority_source", "authority.source", authority.source
            )
        )
    if bound_actor is not None and authority.actor != bound_actor:
        reasons.append(
            VerdictReason("authority_actor_mismatch", "authority.actor", bound_actor)
        )
    if reasons:
        return AuthorityApplicability("insufficient", tuple(reasons))

    scope_reasons: list[VerdictReason] = []
    if matter.object not in authority.objects:
        scope_reasons.append(
            VerdictReason("authority_scope_exceeded", "authority.objects", matter.object)
        )
    if matter.action not in authority.actions:
        scope_reasons.append(
            VerdictReason("authority_scope_exceeded", "authority.actions", matter.action)
        )
    if authority.files:
        for path in _write_face_files(matter):
            if path not in authority.files:
                scope_reasons.append(
                    VerdictReason("authority_scope_exceeded", "authority.files", path)
                )
    if scope_reasons:
        return AuthorityApplicability("out_of_scope", tuple(scope_reasons))

    budget_reasons: list[VerdictReason] = []
    usage = authority.budget_usage_map
    for unit, limit in authority.budget_limits:
        if unit not in usage:
            budget_reasons.append(
                VerdictReason("budget_usage_unknown", "authority.budget", unit)
            )
        elif usage[unit] >= limit:
            budget_reasons.append(
                VerdictReason("budget_exhausted", "authority.budget", unit)
            )
    if budget_reasons:
        return AuthorityApplicability("budget_blocked", tuple(budget_reasons))

    return AuthorityApplicability("applies", (), applicable=True)


# ---------------------------------------------------------------------------
# Goal / frozen-contract change impact
# ---------------------------------------------------------------------------


def assess_goal_change(
    previous: Matter,
    current: Matter,
    bindings: Sequence[ApprovalBinding],
    *,
    user_decision_dependencies: Sequence[str] = (),
) -> GoalImpact:
    """Which bound approvals survive a goal change, and what must be asked.

    A change invalidates only the bindings that depend on the changed
    dependencies. Unknown natural-language changes escalate to an authorized
    subject instead of being treated as equal or as a definite change.
    """

    if previous.matter_key != current.matter_key:
        return GoalImpact(
            "unknown",
            (VerdictReason("different_matter", "matter_key", current.matter_key),),
            unknown_bindings=tuple(binding.approval_id for binding in bindings),
        )
    changes = dependency_diff(previous, current)
    changed = tuple(
        change.name
        for change in changes
        if change.status in {"changed", "added", "removed"}
    )
    unknown = tuple(change.name for change in changes if change.status == "unknown")
    unaffected = tuple(
        change.name
        for change in changes
        if change.status in {"identical", "equivalent"}
    )
    if unknown:
        status = "unknown"
    elif changed:
        status = "affected_change"
    else:
        status = "no_substantive_change"

    stale: list[str] = []
    reusable: list[str] = []
    unknown_bindings: list[str] = []
    for binding in bindings:
        names = set(binding.dependency_names)
        if names & set(unknown):
            unknown_bindings.append(binding.approval_id)
        elif names & set(changed):
            stale.append(binding.approval_id)
        else:
            reusable.append(binding.approval_id)

    decision_names = tuple(user_decision_dependencies)
    user_decisions: list[UserDecisionItem] = []
    for name in sorted(set(decision_names) & set(changed)):
        user_decisions.append(
            UserDecisionItem(
                dependency=name,
                code="new_business_intent_required",
                detail="substantive change needs a new user intent/authority",
            )
        )
    for name in sorted(set(decision_names) & set(unknown)):
        user_decisions.append(
            UserDecisionItem(
                dependency=name,
                code="unknown_substantive_change_requires_clarification",
                detail="natural-language equivalence is unverified; clarify with the authorized subject",
            )
        )

    reasons = tuple(
        VerdictReason("substantive_change", change.name, change.detail)
        for change in changes
        if change.status in {"changed", "added", "removed"}
    ) + tuple(
        VerdictReason("unknown_substantive_change", change.name, change.detail)
        for change in changes
        if change.status == "unknown"
    )
    return GoalImpact(
        status=status,
        reasons=reasons,
        affected_dependencies=changed,
        unaffected_dependencies=unaffected,
        stale_bindings=tuple(stale),
        reusable_bindings=tuple(reusable),
        unknown_bindings=tuple(unknown_bindings),
        user_decisions=tuple(user_decisions),
    )


_CHANGE_REQUIRED_FIELDS: tuple[str, ...] = (
    "key",
    "before",
    "after",
    "reason",
    "commitment_impact",
    "evidence_impact",
    "authority_ref",
    "reverification_plan",
)


def assess_contract_change(
    change: ContractChange, approval: ChangeApproval | None
) -> ContractChangeVerdict:
    """Whether a frozen AC/VC change is approved exactly as requested."""

    reasons: list[VerdictReason] = []
    missing = [
        field
        for field in _CHANGE_REQUIRED_FIELDS
        if not isinstance(getattr(change, field), str)
        or not getattr(change, field).strip()
    ]
    if not change.items:
        missing.append("items")
    if missing:
        reasons.append(
            VerdictReason(
                "incomplete_change_request",
                "change",
                ",".join(sorted(missing)),
            )
        )
    if approval is None:
        reasons.append(VerdictReason("missing_approval", "approval", ""))
        return ContractChangeVerdict("blocked", tuple(reasons))
    if _source_is_weak(approval.authority_source):
        reasons.append(
            VerdictReason(
                "insufficient_authority_source",
                "approval.authority_source",
                approval.authority_source,
            )
        )
    if approval.key != change.key:
        reasons.append(
            VerdictReason(
                "reused_unrelated_change_approval", "approval.key", approval.key
            )
        )
    approved = set(approval.items)
    requested = set(change.items)
    too_narrow = sorted(requested - approved)
    too_wide = sorted(approved - requested)
    if too_narrow:
        reasons.append(
            VerdictReason(
                "approval_scope_too_narrow", "approval.items", ",".join(too_narrow)
            )
        )
    if too_wide:
        reasons.append(
            VerdictReason(
                "approval_scope_expansion", "approval.items", ",".join(too_wide)
            )
        )
    if _normalise_text(approval.before) != _normalise_text(change.before) or (
        _normalise_text(approval.after) != _normalise_text(change.after)
    ):
        reasons.append(
            VerdictReason("approval_version_mismatch", "approval.before/after", "")
        )
    if not isinstance(approval.reverification_plan, str) or not (
        approval.reverification_plan.strip()
    ):
        reasons.append(
            VerdictReason("missing_reverification_plan", "approval.reverification_plan", "")
        )
    unauthorized_reductions = sorted(
        set(change.acceptance_reductions) - set(approval.acceptance_reductions)
    )
    if unauthorized_reductions:
        reasons.append(
            VerdictReason(
                "unauthorized_acceptance_reduction",
                "change.acceptance_reductions",
                ",".join(unauthorized_reductions),
            )
        )
    if reasons:
        return ContractChangeVerdict("blocked", tuple(reasons))
    return ContractChangeVerdict(
        "approved",
        (),
        approved_items=tuple(change.items),
        reverification_items=tuple(change.items),
        covers_only_requested_change=True,
    )


# ---------------------------------------------------------------------------
# Claim and write surface
# ---------------------------------------------------------------------------


_ABSOLUTE_RE = re.compile(r"^(?:/|[A-Za-z]:[/\\])")


def _path_problem(path: Any) -> tuple[str | None, str | None]:
    """Return (normalised path, violation code) for one claimed path."""

    if not isinstance(path, str) or not path.strip():
        return None, "empty_write_face"
    raw = path.strip()
    if _ABSOLUTE_RE.match(raw) or raw.startswith("\\\\"):
        return None, "absolute_path"
    candidates: list[str] = []
    for part in raw.split("/"):
        for segment in part.split("\\"):
            if segment in {"", "."}:
                continue
            if segment == "..":
                return None, "parent_traversal"
            candidates.append(segment)
    if "*" in raw or "?" in raw:
        return None, "wildcard_not_allowed"
    normalised = posixpath.join(*candidates) if candidates else ""
    if not normalised:
        return None, "empty_write_face"
    return normalised, None


def _surface_covers(path: str, allowed: Sequence[str]) -> bool:
    for surface in allowed:
        if not isinstance(surface, str) or not surface.strip():
            continue
        entry = surface.strip().replace("\\", "/")
        if entry.endswith("/**"):
            prefix = entry[:-3].rstrip("/")
            if path == prefix or path.startswith(prefix + "/"):
                return True
        elif path == entry:
            return True
    return False


def assess_write_surface(
    files: Sequence[str], allowed: Sequence[str]
) -> SurfaceVerdict:
    """Read-only check that the requested files stay in the approved surface."""

    violations: list[SurfaceViolation] = []
    for path in files:
        normalised, problem = _path_problem(path)
        if problem is not None:
            violations.append(
                SurfaceViolation(problem, path if isinstance(path, str) else repr(path))
            )
            continue
        assert normalised is not None
        if not _surface_covers(normalised, allowed):
            violations.append(SurfaceViolation("outside_write_face", normalised))
    status = "violation" if violations else "ok"
    return SurfaceVerdict(status=status, violations=tuple(violations))


def assess_claim(claims: Sequence[Claim], request: ClaimRequest) -> ClaimVerdict:
    """Read-only claim check: no takeover, no double writer, no fake dispatch.

    One unusable path fails the *whole* requested write face (a partially
    readable request is not a smaller claim), and a claim is bound to its task:
    an active claim of the same owner on another task is not clear either. A
    re-entry of the same owner on the same task stays clear.
    """

    reasons: list[VerdictReason] = []
    normalised: list[str] = []
    invalid_path = False
    for path in request.files:
        candidate, problem = _path_problem(path)
        if problem is not None:
            reasons.append(VerdictReason(problem, "files", str(path)))
            invalid_path = True
            continue
        assert candidate is not None
        normalised.append(candidate)
    if invalid_path:
        reasons.append(
            VerdictReason(
                "invalid_claim_request",
                "files",
                "requested write face is not a legal path set",
            )
        )
        return ClaimVerdict("blocked", tuple(reasons))
    if not normalised:
        reasons.append(VerdictReason("empty_write_face", "files", ""))
        return ClaimVerdict("blocked", tuple(reasons))

    conflicts: list[str] = []
    owners: list[str] = []
    for claim in claims:
        if not claim.active:
            continue
        claim_files = {
            normalised_path
            for normalised_path, problem in (_path_problem(entry) for entry in claim.files)
            if problem is None and normalised_path is not None
        }
        overlap = [path for path in normalised if path in claim_files]
        if not overlap:
            continue
        same_task = claim.owner == request.actor and claim.task_key == request.task_key
        if same_task:
            continue
        if claim.lock_mode != "exclusive":
            reasons.append(
                VerdictReason("lock_mode_not_exclusive", "claims.lock_mode", claim.owner)
            )
        own_other_task = claim.owner == request.actor
        for path in overlap:
            reasons.append(
                VerdictReason(
                    "own_claim_on_other_task" if own_other_task else "foreign_claim",
                    "files",
                    path,
                )
            )
            if path not in conflicts:
                conflicts.append(path)
        if claim.owner not in owners:
            owners.append(claim.owner)
    if request.decision_ref is not None:
        reasons.append(
            VerdictReason(
                "decision_does_not_transfer_claim",
                "decision_ref",
                request.decision_ref,
            )
        )
    status = "conflict" if conflicts else "clear"
    return ClaimVerdict(
        status=status,
        reasons=tuple(reasons),
        conflicts=tuple(conflicts),
        conflicting_owners=tuple(owners),
        takeover=False,
        lock_mode="exclusive",
        decision_grants_claim=False,
        dispatched=False,
    )


# ---------------------------------------------------------------------------
# A selection is never an effect
# ---------------------------------------------------------------------------


def selection_effects(entry: str, choice: str) -> SelectionEffects:
    """Explicit statement that a decision selection has no business effect.

    Contract edits, stage closure, signoff writes and dispatch stay false for
    every entry; a new separate authorization/decision is always needed.
    """

    if entry not in ACTIVE_ENTRIES:
        raise ValueError(f"retired or unknown entry {entry!r}")
    if not isinstance(choice, str) or not choice.strip():
        raise ValueError("choice must be a non-empty string")
    return SelectionEffects()


# ---------------------------------------------------------------------------
# Signoff applicability
# ---------------------------------------------------------------------------


def assess_signoff(
    signoff: SignoffRef,
    current_matter: Matter,
    *,
    required_scope: Sequence[str],
) -> SignoffVerdict:
    """Read-only applicability of a signoff reference (never writes one).

    A required successful signoff is only ``finalize``; ``continue`` and
    ``user-confirm`` are legal menu words of the same entry but do not satisfy a
    required signoff. The reference must name the required key and carry a
    non-empty traceable signoff reference.
    """

    reasons: list[VerdictReason] = []
    if signoff.historical:
        reasons.append(
            VerdictReason("historical_readonly", "signoff", str(signoff.signoff_ref))
        )
    if signoff.disable_requested:
        reasons.append(VerdictReason("signoff_bypass", "signoff", "disable requested"))
    if signoff.choice in REQUIRED_SIGNOFF_CHOICES:
        pass
    elif signoff.choice in FINALIZE_CHOICES:
        reasons.append(
            VerdictReason("not_a_required_signoff", "choice", str(signoff.choice))
        )
    elif signoff.choice in LEGACY_SIGNOFF_WORDS:
        reasons.append(VerdictReason("legacy_word", "choice", signoff.choice))
    else:
        reasons.append(VerdictReason("unknown_choice", "choice", signoff.choice))
    if signoff.matter_key != current_matter.matter_key:
        reasons.append(
            VerdictReason("different_matter", "matter_key", current_matter.matter_key)
        )
    signoff_key = signoff.key if isinstance(signoff.key, str) else ""
    required_keys = {str(item) for item in required_scope}
    if not signoff_key.strip():
        reasons.append(VerdictReason("missing_signoff_key", "key", ""))
    elif signoff_key.strip() not in required_keys:
        reasons.append(
            VerdictReason("signoff_key_mismatch", "key", signoff_key.strip())
        )
    if not isinstance(signoff.signoff_ref, str) or not signoff.signoff_ref.strip():
        reasons.append(
            VerdictReason("missing_signoff_reference", "signoff_ref", "")
        )
    if signoff.substantive_version != current_matter.substantive_version:
        reasons.append(VerdictReason("stale_signoff", "substantive_version", ""))
    if signoff.artifact_ref is None or not str(signoff.artifact_ref).strip():
        reasons.append(
            VerdictReason("fabricated_signoff", "artifact_ref", "no real artifact")
        )
    scope = set(signoff.scope)
    required = set(required_scope)
    missing = sorted(required - scope)
    extra = sorted(scope - required)
    if missing:
        reasons.append(
            VerdictReason("incomplete_scope", "scope", ",".join(missing))
        )
    if extra:
        reasons.append(VerdictReason("scope_expansion", "scope", ",".join(extra)))

    if any(reason.code not in _STALE_CODES for reason in reasons):
        status = "blocked"
    elif reasons:
        status = "stale"
    else:
        status = "valid"
    return SignoffVerdict(status=status, reasons=tuple(reasons))


# ---------------------------------------------------------------------------
# Action replay / crash window
# ---------------------------------------------------------------------------


def plan_actions(
    effects: Sequence[EffectRecord],
    *,
    matter: Matter,
    actions: Sequence[str],
) -> ActionPlan:
    """Which requested actions may run, which are duplicates, which are blocked.

    Only an ``applied`` effect for the same matter and substantive version makes
    an action a duplicate. ``in-progress``/``unknown`` block instead of guessing
    (no blind retry after a crash); a ``failed`` effect stays recorded and the
    action may be attempted again, and a genuinely absent record leaves the
    action free. Other recognised non-effect states (``not-started``) are not
    treated as executed either. A *matched* record whose status is unrecognised
    (or missing) is not a proof of "never executed", so it blocks as well.
    """

    requested: list[str] = []
    for action in actions:
        if not isinstance(action, str) or not action.strip():
            raise ValueError("actions must be non-empty strings")
        if action not in requested:
            requested.append(action)

    duplicate: list[str] = []
    blocked: list[str] = []
    reasons: list[VerdictReason] = []
    for action in requested:
        matching = [
            effect
            for effect in effects
            if effect.matter_key == matter.matter_key
            and effect.substantive_version == matter.substantive_version
            and action in effect.actions
        ]
        if any(effect.status == "applied" for effect in matching):
            duplicate.append(action)
            continue
        ambiguous = [
            effect
            for effect in matching
            if effect.status in {"unknown", "in-progress"}
        ]
        if ambiguous:
            status = next(
                effect.status
                for effect in ambiguous
                if effect.status in {"unknown", "in-progress"}
            )
            blocked.append(action)
            reasons.append(
                VerdictReason("effect_state_unknown", "effect", status)
            )
            continue
        unrecognised = [
            effect
            for effect in matching
            if not isinstance(effect.status, str) or effect.status not in EFFECT_STATES
        ]
        if unrecognised:
            blocked.append(action)
            reasons.append(
                VerdictReason(
                    "effect_state_unrecognised",
                    "effect",
                    repr(unrecognised[0].status),
                )
            )

    remaining = [
        action
        for action in requested
        if action not in duplicate and action not in blocked
    ]
    if blocked and remaining:
        status = "partial"
    elif blocked:
        status = "blocked"
    elif remaining:
        status = "proceed"
    else:
        status = "already-applied"
    return ActionPlan(
        status=status,
        reasons=tuple(reasons),
        actions=tuple(remaining),
        duplicate_actions=tuple(duplicate),
        blocked=tuple(blocked),
    )


def revoke_decision(decision: DecisionRecord) -> DecisionRecord:
    """Mark a decision revoked. Already-applied effects are not rolled back."""

    if not isinstance(decision, DecisionRecord):
        raise ValueError("decision must be a DecisionRecord")
    return replace(decision, revoked=True)
