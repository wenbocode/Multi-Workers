"""decision_policy.py - read-only validation of the authorization side-car.

M05 (AC-008, AC-020, AC-021, AC-022, AC-034, AC-035, AC-036, AC-037).

This module is a *pure, read-only* judge. It never writes the policy file, the
frozen 21-key ``_autopilot/config.json``, a grant, a gate, a brake, a ledger or
a sign-off; it produces verdicts (allowed + the concrete reasons) that a
separate, already-authorized consumer may act on.

The candidate side-car ``.agenticdoc/_autopilot/decision-policy.json`` only
*references* authorization that already exists elsewhere. Its fields are
``schema_version``, ``authority_ref``, ``scope``,
``hard_limits[{unit, limit, usage_source}]``,
``soft_round_extension{allowed, scope, authority_ref}`` and
``recovery{allowed_origins, scope, authority_ref, observation_conditions,
stop_conditions}``. It is not a grant generator and not a second ledger:

* no file -> zero permissions (``status="absent"``); a broken, unreadable or
  schema-drifted file fails closed (``status="invalid"`` + reasons);
* ``authority_ref`` must resolve to an :class:`AuthorityRecord` recorded by a
  caller-declared controlled writer, unrevoked and covering the requested
  scope. Self-asserted ``preauthorized``/``token``/``origin``/``tty``/``role``
  fields are rejected as unknown policy fields - a page token, a TTY or a
  self-reported origin never proves authorization;
* ``hard_limits`` need an explicit unit and usage source. Frozen autopilot
  config knobs (``round_budget``, ``worker_timeout_min``) are *not* project
  hard authority, and rounds are never silently compared to tokens, cost or
  wall-clock. Spend is checked against the caller-supplied *cumulative* usage;
  an overrun produces no consumption and the usage is never reset;
* a hard-limit increase needs an explicit human authorization carrying the
  concrete delta, purpose and risk; a DP choice can never raise its own limit;
* a soft round extension needs the policy's own extension authorization plus a
  complete PM note (real progress, explicit budget basis, next goal, plan,
  stop criterion) and is granted only for the explicit delta. Remaining hard
  budget is not an authorization;
* a pending-review event only triggers evaluation - it never auto-resumes and
  never becomes an automatic human requirement. The resume needs an explicit,
  non-empty requested scope that the policy itself covers: a missing or
  uncovered request never resumes with an empty scope;
* a halted-stage resume needs a complete note (stop reason, elimination
  evidence, stage version, affected keys, target plan, authorization, residual
  budget, stop criterion), a valid approval and the policy's own observation
  and stop conditions; the stop facts and the consumed budget are carried
  forward verbatim. The policy rule's own ``recovery.authority_ref`` is
  resolved as well: a note may reference a different authorization only when
  the controlled writer recorded it as an explicit replacement
  (``supersedes``), so a revoked rule reference is never bypassed by pointing
  the note elsewhere. A user stop/revocation or a hard guard is never lifted
  by a technical repair, by a DP choice, by an unknown guard/origin state or
  by an unverified self-reported clearance; only an explicit human
  authorization covering ``recovery:user-stop`` lifts a recorded stop;
* an H12 breaker recovery needs an isolated controlled channel (not the
  tripped chain, not a page token), an available primary transport, a valid
  preauthorization (the rule's own reference, or a writer-recorded explicit
  replacement of it), reviewable reason-elimination evidence and passing
  machine checks. A missing/unknown user-disable or origin state is not read
  as "enabled": the brake stays engaged, the breaker history is preserved, a
  concrete authorization/information question is returned and ``reject``
  never closes the project. Observing the stop condition again re-trips the
  brake.

Consumers are expected to be the gate/recovery handlers wired in later tasks
(T21 takes over the live recovery handlers); this module deliberately imports
no CLI, conductor, autopilot config, decision client or service, so it cannot
become a second execution path.
"""

from __future__ import annotations

import json
import pathlib
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field

POLICY_SCHEMA_VERSION = 1

POLICY_RELATIVE_PATH = pathlib.Path(".agenticdoc") / "_autopilot" / "decision-policy.json"

#: Authority carriers this module can accept. Both are *references* to an
#: authorization recorded by a real controlled writer; the record itself is
#: supplied by the caller (existing user-grant / controlled-config source).
AUTHORITY_KINDS = ("user-grant", "controlled-config")
#: Raising a hard limit needs a *human* authorization, never a config record.
HUMAN_AUTHORITY_KINDS = ("user-grant",)

#: Frozen autopilot config knobs (D-110, 21 keys). They are project settings,
#: not project hard-budget authority: a policy cannot launder them into one.
FROZEN_CONFIG_UNITS = frozenset({"round_budget", "worker_timeout_min"})

#: Identities that are self-reported by the very actor asking for permission.
NON_AUTHORITATIVE_ORIGINS = frozenset(
    {
        "self-report",
        "self_reported",
        "agent-report",
        "tty",
        "terminal",
        "token",
        "page-token",
        "role",
        "worker",
        "model",
        "policy",
        "auto-pass",
    }
)

#: Budget bases that only restate the remaining hard budget.
HARD_BALANCE_SOURCES = frozenset(
    {
        "hard-balance",
        "hard_balance",
        "hard-budget",
        "hard_budget",
        "remaining",
        "budget-remaining",
    }
)

_POLICY_FIELDS = frozenset(
    {
        "schema_version",
        "authority_ref",
        "scope",
        "hard_limits",
        "soft_round_extension",
        "recovery",
    }
)
_HARD_LIMIT_FIELDS = frozenset({"unit", "limit", "usage_source"})
_SOFT_EXTENSION_FIELDS = frozenset({"allowed", "scope", "authority_ref"})
_RECOVERY_FIELDS = frozenset(
    {
        "allowed_origins",
        "scope",
        "authority_ref",
        "observation_conditions",
        "stop_conditions",
    }
)

_GATE_FOLLOW_UP = {"steer": "dp-pm-steer", "need_fix": "dp-auto"}


# ── value objects ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class PolicyIssue:
    """One concrete reason. ``code`` is stable, ``field`` locates the input."""

    code: str
    field: str = ""
    detail: str = ""

    def text(self) -> str:
        where = f" ({self.field})" if self.field else ""
        return f"{self.code}{where}" + (f": {self.detail}" if self.detail else "")


@dataclass(frozen=True)
class BudgetLimit:
    unit: str
    limit: int
    usage_source: str


@dataclass(frozen=True)
class SoftExtension:
    allowed: bool
    scope: tuple[str, ...]
    authority_ref: str


@dataclass(frozen=True)
class RecoveryRule:
    allowed_origins: tuple[str, ...]
    scope: tuple[str, ...]
    authority_ref: str
    observation_conditions: tuple[str, ...]
    stop_conditions: tuple[str, ...]


@dataclass(frozen=True)
class DecisionPolicy:
    schema_version: int
    authority_ref: str
    scope: tuple[str, ...]
    hard_limits: tuple[BudgetLimit, ...]
    soft_round_extension: SoftExtension | None
    recovery: RecoveryRule | None

    def limit_for(self, unit: str) -> BudgetLimit | None:
        for limit in self.hard_limits:
            if limit.unit == unit:
                return limit
        return None


@dataclass(frozen=True)
class PolicyLoad:
    """Result of reading the side-car. Only ``status="valid"`` carries a policy."""

    status: str
    policy: DecisionPolicy | None
    issues: tuple[PolicyIssue, ...]
    #: Recovery-rule problems: they close the recovery surface only, because a
    #: brake that cannot be verified must stay engaged without freezing the
    #: unrelated budget/authority checks.
    recovery_issues: tuple[PolicyIssue, ...] = ()

    @property
    def usable(self) -> bool:
        return self.status == "valid" and self.policy is not None

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return tuple(issue.code for issue in self.issues)


@dataclass(frozen=True)
class AuthorityRecord:
    """A read-only view of an authorization recorded by a controlled writer."""

    authority_ref: str
    kind: str
    scope: tuple[str, ...]
    writer: str
    revoked: bool = False
    recorded_at: str = ""
    #: References this record explicitly replaces/restores. Recorded by the same
    #: controlled writer as the rest of the record, never self-asserted by the
    #: request that consumes it.
    supersedes: tuple[str, ...] = ()


@dataclass(frozen=True)
class AuthorityResolution:
    record: AuthorityRecord | None
    issues: tuple[PolicyIssue, ...]

    @property
    def valid(self) -> bool:
        return self.record is not None and not self.issues


@dataclass(frozen=True)
class SpendVerdict:
    allowed: bool
    unit: str | None
    requested: int | None
    used_before: int | None
    limit: int | None
    used_after: int | None
    usage_source: str = ""
    reasons: tuple[PolicyIssue, ...] = ()


@dataclass(frozen=True)
class LimitVerdict:
    allowed: bool
    unit: str | None
    limit_before: int | None
    limit_after: int | None
    reasons: tuple[PolicyIssue, ...] = ()


@dataclass(frozen=True)
class ExtensionVerdict:
    allowed: bool
    unit: str | None
    granted: int | None
    used_after: int | None
    reasons: tuple[PolicyIssue, ...] = ()


@dataclass(frozen=True)
class GateVerdict:
    allowed: bool
    release_scope: tuple[str, ...]
    follow_up: str | None
    project_closed: bool
    reasons: tuple[PolicyIssue, ...] = ()


@dataclass(frozen=True)
class PendingReviewVerdict:
    allowed: bool
    resume_scope: tuple[str, ...]
    requires_human: bool
    reasons: tuple[PolicyIssue, ...] = ()


@dataclass(frozen=True)
class RecoveryVerdict:
    allowed: bool
    scope: tuple[str, ...]
    observation_conditions: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    preserved_facts: tuple[str, ...]
    usage_after: tuple[tuple[str, int], ...]
    questions: tuple[str, ...]
    project_closed: bool
    reasons: tuple[PolicyIssue, ...] = ()


@dataclass(frozen=True)
class ObservationVerdict:
    retrip: bool
    brake: str
    preserved_history: bool
    reasons: tuple[PolicyIssue, ...] = ()


# ── small helpers ────────────────────────────────────────────────────────────


def policy_path(project_root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(project_root) / POLICY_RELATIVE_PATH


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _nonempty_str(value: object) -> bool:
    return isinstance(value, str) and value.strip() != ""


def _str_tuple(value: object) -> tuple[str, ...] | None:
    """Tuple of non-empty strings, ``()`` for an empty list, ``None`` if bad."""
    if not isinstance(value, (list, tuple)):
        return None
    items: list[str] = []
    for item in value:
        if not _nonempty_str(item):
            return None
        items.append(item.strip())
    return tuple(items)


def _scope_covers(granted: Sequence[str], requested: str) -> bool:
    for token in granted:
        if token == requested:
            return True
        if token.endswith(":*") and requested.startswith(token[:-1]):
            return True
    return False


def _covered_scope(granted: Sequence[str], requested: Iterable[str]) -> tuple[str, ...]:
    return tuple(token for token in requested if _scope_covers(granted, token))


#: Halt origins this judge recognises. An unknown origin is *not* a plain
#: technical stop: it keeps the stage halted and asks for the recorded origin.
HALT_ORIGINS = ("technical", "user-stop", "revoked")

#: Origins whose lift needs an explicit *human* authorization, not a technical
#: repair and not a DP choice.
_HUMAN_HALT_ORIGINS = frozenset({"user-stop", "revoked"})


def _required_scope(
    value: object, field: str
) -> tuple[tuple[str, ...], PolicyIssue | None]:
    """Explicit, non-empty scope: an empty requirement never passes vacuously."""
    scope = _str_tuple(value)
    if not scope:
        return (), PolicyIssue(
            "required-scope-missing",
            field,
            "an explicit non-empty scope is required; an empty requirement is not a grant",
        )
    return scope, None


def _usage_map(usage: object) -> Mapping[str, object] | None:
    if isinstance(usage, Mapping):
        return usage
    return None


# ── policy parsing ───────────────────────────────────────────────────────────


def load_policy(project_root: pathlib.Path | str) -> PolicyLoad:
    """Read the side-car. Missing file = zero permissions, illegal = closed."""
    path = policy_path(project_root)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return PolicyLoad(
            status="absent",
            policy=None,
            issues=(
                PolicyIssue(
                    "policy-absent",
                    "",
                    "no decision-policy.json: zero permissions, no default grant",
                ),
            ),
        )
    except (OSError, UnicodeDecodeError) as exc:
        return PolicyLoad(
            "invalid",
            None,
            (PolicyIssue("policy-unreadable", str(path), str(exc)),),
        )
    except json.JSONDecodeError as exc:
        return PolicyLoad(
            "invalid",
            None,
            (PolicyIssue("policy-not-json", str(path), str(exc)),),
        )
    return parse_policy(raw)


def parse_policy(raw: object) -> PolicyLoad:
    """Validate the raw JSON value. Any structural defect is fail-closed."""
    if not isinstance(raw, Mapping):
        return PolicyLoad(
            "invalid",
            None,
            (PolicyIssue("policy-not-object", "", "policy root must be a JSON object"),),
        )

    issues: list[PolicyIssue] = []
    for name in sorted(set(raw) - _POLICY_FIELDS):
        issues.append(
            PolicyIssue(
                "policy-unknown-field",
                str(name),
                "unknown policy field: only referenced authorization is accepted",
            )
        )

    schema = raw.get("schema_version")
    if "schema_version" not in raw:
        issues.append(PolicyIssue("policy-field-missing", "schema_version", "required"))
    elif not _is_int(schema) or schema != POLICY_SCHEMA_VERSION:
        issues.append(
            PolicyIssue(
                "policy-schema-unsupported",
                "schema_version",
                f"expected {POLICY_SCHEMA_VERSION}, got {schema!r}",
            )
        )

    authority_ref = raw.get("authority_ref")
    if not _nonempty_str(authority_ref):
        issues.append(
            PolicyIssue("policy-field-missing", "authority_ref", "required reference")
        )

    scope = _str_tuple(raw.get("scope"))
    if scope is None:
        issues.append(PolicyIssue("policy-field-invalid", "scope", "list of scope tokens"))
    elif not scope:
        issues.append(PolicyIssue("policy-scope-empty", "scope", "at least one scope token"))
    else:
        for token in scope:
            if token == "*":
                issues.append(
                    PolicyIssue(
                        "policy-scope-wildcard",
                        "scope",
                        "an unbounded scope is never granted by this policy",
                    )
                )

    hard_limits, limit_issues = _parse_hard_limits(raw.get("hard_limits"))
    issues.extend(limit_issues)

    extension, extension_issues = _parse_soft_extension(raw.get("soft_round_extension"))
    issues.extend(extension_issues)

    recovery, recovery_issues = _parse_recovery(raw.get("recovery"))

    if issues:
        return PolicyLoad("invalid", None, tuple(issues), tuple(recovery_issues))

    policy = DecisionPolicy(
        schema_version=POLICY_SCHEMA_VERSION,
        authority_ref=str(authority_ref).strip(),
        scope=scope,
        hard_limits=hard_limits,
        soft_round_extension=extension,
        recovery=recovery,
    )
    return PolicyLoad("valid", policy, (), tuple(recovery_issues))


def _parse_hard_limits(value: object) -> tuple[tuple[BudgetLimit, ...], list[PolicyIssue]]:
    issues: list[PolicyIssue] = []
    if value is None:
        return (), issues
    if not isinstance(value, list):
        issues.append(
            PolicyIssue("policy-field-invalid", "hard_limits", "list of limit objects")
        )
        return (), issues
    limits: list[BudgetLimit] = []
    seen: set[str] = set()
    for index, item in enumerate(value):
        prefix = f"hard_limits[{index}]"
        if not isinstance(item, Mapping):
            issues.append(PolicyIssue("policy-field-invalid", prefix, "limit object"))
            continue
        for name in sorted(set(item) - _HARD_LIMIT_FIELDS):
            issues.append(
                PolicyIssue("policy-unknown-field", f"{prefix}.{name}", "unknown limit field")
            )
        unit = item.get("unit")
        limit = item.get("limit")
        source = item.get("usage_source")
        ok = True
        if not _nonempty_str(unit):
            issues.append(
                PolicyIssue(
                    "policy-field-missing",
                    f"{prefix}.unit",
                    "an explicit unit is required (rounds are not tokens/cost/wall-clock)",
                )
            )
            ok = False
        elif unit in FROZEN_CONFIG_UNITS:
            issues.append(
                PolicyIssue(
                    "policy-unit-not-authority",
                    f"{prefix}.unit",
                    f"{unit} is a frozen autopilot config knob, not a hard-budget authority",
                )
            )
            ok = False
        elif unit in seen:
            issues.append(PolicyIssue("policy-duplicate-unit", f"{prefix}.unit", unit))
            ok = False
        if not _is_int(limit) or limit <= 0:
            issues.append(
                PolicyIssue(
                    "policy-field-invalid", f"{prefix}.limit", "positive integer required"
                )
            )
            ok = False
        if not _nonempty_str(source):
            issues.append(
                PolicyIssue(
                    "policy-usage-source-missing",
                    f"{prefix}.usage_source",
                    "a resolvable cumulative usage source is required",
                )
            )
            ok = False
        if ok:
            seen.add(str(unit))
            limits.append(BudgetLimit(str(unit), int(limit), str(source)))
    return tuple(limits), issues


def _parse_soft_extension(value: object) -> tuple[SoftExtension | None, list[PolicyIssue]]:
    issues: list[PolicyIssue] = []
    if value is None:
        return None, issues
    if not isinstance(value, Mapping):
        return None, [
            PolicyIssue(
                "policy-field-invalid", "soft_round_extension", "object required"
            )
        ]
    for name in sorted(set(value) - _SOFT_EXTENSION_FIELDS):
        issues.append(
            PolicyIssue(
                "policy-unknown-field", f"soft_round_extension.{name}", "unknown field"
            )
        )
    allowed = value.get("allowed")
    if not isinstance(allowed, bool):
        issues.append(
            PolicyIssue(
                "policy-field-invalid",
                "soft_round_extension.allowed",
                "true/false required",
            )
        )
    scope = _str_tuple(value.get("scope"))
    authority_ref = value.get("authority_ref")
    if allowed is True:
        if not scope:
            issues.append(
                PolicyIssue(
                    "policy-field-missing",
                    "soft_round_extension.scope",
                    "an allowed extension needs an explicit scope",
                )
            )
        if not _nonempty_str(authority_ref):
            issues.append(
                PolicyIssue(
                    "policy-field-missing",
                    "soft_round_extension.authority_ref",
                    "an allowed extension needs its own authority reference",
                )
            )
    if issues:
        return None, issues
    return (
        SoftExtension(
            allowed=bool(allowed),
            scope=scope or (),
            authority_ref=str(authority_ref).strip() if _nonempty_str(authority_ref) else "",
        ),
        issues,
    )


def _parse_recovery(value: object) -> tuple[RecoveryRule | None, list[PolicyIssue]]:
    """Recovery is surface-scoped: its defects block recovery, nothing else."""
    if value is None:
        return None, []
    issues: list[PolicyIssue] = []
    if not isinstance(value, Mapping):
        return None, [
            PolicyIssue("recovery-field-invalid", "recovery", "object required")
        ]
    for name in sorted(set(value) - _RECOVERY_FIELDS):
        issues.append(
            PolicyIssue("recovery-unknown-field", f"recovery.{name}", "unknown field")
        )
    origins = _str_tuple(value.get("allowed_origins"))
    if origins is None or not origins:
        issues.append(
            PolicyIssue(
                "recovery-origin-missing", "recovery.allowed_origins", "explicit origins"
            )
        )
        origins = ()
    else:
        for origin in origins:
            if origin == "*":
                issues.append(
                    PolicyIssue(
                        "recovery-origin-wildcard",
                        "recovery.allowed_origins",
                        "a wildcard origin is not an isolated channel",
                    )
                )
            elif origin in NON_AUTHORITATIVE_ORIGINS:
                issues.append(
                    PolicyIssue(
                        "recovery-origin-not-authoritative",
                        "recovery.allowed_origins",
                        f"{origin} is self-reported, not an authorized origin",
                    )
                )
    scope = _str_tuple(value.get("scope"))
    if not scope:
        issues.append(
            PolicyIssue("recovery-scope-missing", "recovery.scope", "explicit scope")
        )
        scope = ()
    authority_ref = value.get("authority_ref")
    if not _nonempty_str(authority_ref):
        issues.append(
            PolicyIssue(
                "recovery-authority-missing",
                "recovery.authority_ref",
                "a recovery needs its own authority reference",
            )
        )
    observations = _str_tuple(value.get("observation_conditions"))
    if not observations:
        issues.append(
            PolicyIssue(
                "recovery-observation-missing",
                "recovery.observation_conditions",
                "no observable condition: recovery cannot be verified",
            )
        )
        observations = ()
    stops = _str_tuple(value.get("stop_conditions"))
    if not stops:
        issues.append(
            PolicyIssue(
                "recovery-stop-missing",
                "recovery.stop_conditions",
                "no stop condition: recovery cannot be bounded",
            )
        )
        stops = ()
    if issues:
        return None, issues
    return (
        RecoveryRule(
            allowed_origins=origins,
            scope=scope,
            authority_ref=str(authority_ref).strip(),
            observation_conditions=observations,
            stop_conditions=stops,
        ),
        issues,
    )


# ── authority ────────────────────────────────────────────────────────────────


def parse_authority_record(
    payload: object,
    *,
    trusted_writers: Iterable[str],
) -> tuple[AuthorityRecord | None, tuple[PolicyIssue, ...]]:
    """Validate one record handed over by the caller's controlled writer.

    ``writer`` must be one of the caller-declared trusted writers; a record
    whose kind is not an authorization carrier, whose scope is empty, or that
    has been revoked never yields a record.
    """
    trusted = frozenset(trusted_writers)
    if not isinstance(payload, Mapping):
        return None, (
            PolicyIssue("authority-not-object", "", "authority record must be an object"),
        )
    issues: list[PolicyIssue] = []
    authority_ref = payload.get("authority_ref")
    if not _nonempty_str(authority_ref):
        issues.append(
            PolicyIssue("authority-field-missing", "authority_ref", "required")
        )
    kind = payload.get("kind")
    if kind not in AUTHORITY_KINDS:
        issues.append(
            PolicyIssue(
                "authority-kind-not-authority",
                "kind",
                f"{kind!r} is not one of {', '.join(AUTHORITY_KINDS)}",
            )
        )
    scope = _str_tuple(payload.get("scope"))
    if not scope:
        issues.append(PolicyIssue("authority-scope-missing", "scope", "explicit scope"))
        scope = ()
    writer = payload.get("writer")
    writer_ok = _nonempty_str(writer) and str(writer) in trusted
    if not writer_ok:
        issues.append(
            PolicyIssue(
                "authority-writer-untrusted",
                "writer",
                f"{writer!r} is not a caller-declared controlled writer",
            )
        )
    revoked = payload.get("revoked", False)
    if not isinstance(revoked, bool):
        issues.append(PolicyIssue("authority-field-invalid", "revoked", "true/false"))
        revoked = True
    supersedes = _str_tuple(payload.get("supersedes", ()))
    if supersedes is None:
        issues.append(
            PolicyIssue(
                "authority-field-invalid", "supersedes", "list of authority references"
            )
        )
        supersedes = ()
    recorded_at = payload.get("recorded_at", "")
    if not isinstance(recorded_at, str):
        recorded_at = ""
    if issues:
        return None, tuple(issues)
    return (
        AuthorityRecord(
            authority_ref=str(authority_ref).strip(),
            kind=str(kind),
            scope=scope,
            writer=str(writer),
            revoked=revoked,
            recorded_at=recorded_at,
            supersedes=supersedes,
        ),
        (),
    )


def _resolve_authority(
    authority_ref: object,
    authority_source: object,
    required_scope: Sequence[str],
    trusted_writers: Iterable[str],
) -> AuthorityResolution:
    trusted = frozenset(trusted_writers)
    if not _nonempty_str(authority_ref):
        return AuthorityResolution(
            None, (PolicyIssue("authority-ref-missing", "", "no authority reference"),)
        )
    source = authority_source if isinstance(authority_source, Mapping) else {}
    record = source.get(str(authority_ref))
    if not isinstance(record, AuthorityRecord):
        return AuthorityResolution(
            None,
            (
                PolicyIssue(
                    "authority-unresolved",
                    str(authority_ref),
                    "no record was produced by a controlled writer",
                ),
            ),
        )
    issues: list[PolicyIssue] = []
    if record.revoked:
        issues.append(
            PolicyIssue("authority-revoked", record.authority_ref, "authorization revoked")
        )
    if record.kind not in AUTHORITY_KINDS:
        issues.append(
            PolicyIssue(
                "authority-kind-not-authority",
                record.authority_ref,
                f"kind {record.kind!r} is not an authorization carrier",
            )
        )
    if record.writer not in trusted:
        issues.append(
            PolicyIssue(
                "authority-writer-untrusted",
                record.writer,
                "record does not come from a caller-declared controlled writer",
            )
        )
    uncovered = tuple(
        token for token in required_scope if not _scope_covers(record.scope, token)
    )
    if uncovered:
        issues.append(
            PolicyIssue(
                "authority-scope-uncovered",
                record.authority_ref,
                "not covered: " + ", ".join(uncovered),
            )
        )
    return AuthorityResolution(record if not issues else None, tuple(issues))


# ── hard budget ──────────────────────────────────────────────────────────────


def check_spend(
    load: PolicyLoad,
    *,
    unit: object,
    amount: object,
    usage: object,
) -> SpendVerdict:
    """Check one bounded spend against the policy's cumulative hard limit."""
    if not load.usable:
        return SpendVerdict(
            False,
            unit if _nonempty_str(unit) else None,
            None,
            None,
            None,
            None,
            reasons=load.issues,
        )
    policy = load.policy
    assert policy is not None
    limit = policy.limit_for(str(unit)) if _nonempty_str(unit) else None
    if limit is None:
        return SpendVerdict(
            False,
            unit if _nonempty_str(unit) else None,
            None,
            None,
            None,
            None,
            reasons=(
                PolicyIssue(
                    "budget-unit-unknown",
                    str(unit),
                    "unit has no explicit hard limit in the policy",
                ),
            ),
        )
    usage_map = _usage_map(usage)
    used = usage_map.get(limit.unit) if usage_map is not None else None
    if not _is_int(used) or int(used) < 0:
        return SpendVerdict(
            False,
            limit.unit,
            None,
            None,
            limit.limit,
            None,
            limit.usage_source,
            (
                PolicyIssue(
                    "budget-usage-unknown",
                    limit.unit,
                    f"cumulative usage from {limit.usage_source!r} is not verifiable",
                ),
            ),
        )
    used_before = int(used)
    if not _is_int(amount) or int(amount) <= 0:
        return SpendVerdict(
            False,
            limit.unit,
            None,
            used_before,
            limit.limit,
            None,
            limit.usage_source,
            (
                PolicyIssue(
                    "budget-amount-invalid",
                    limit.unit,
                    "an explicit positive amount is required",
                ),
            ),
        )
    requested = int(amount)
    used_after = used_before + requested
    if used_after > limit.limit:
        return SpendVerdict(
            False,
            limit.unit,
            requested,
            used_before,
            limit.limit,
            None,
            limit.usage_source,
            (
                PolicyIssue(
                    "budget-overrun",
                    limit.unit,
                    f"{used_after} would exceed the hard limit {limit.limit}",
                ),
            ),
        )
    return SpendVerdict(
        True,
        limit.unit,
        requested,
        used_before,
        limit.limit,
        used_after,
        limit.usage_source,
    )


def check_limit_change(
    load: PolicyLoad,
    *,
    unit: object,
    new_limit: object,
    grant: object,
    authority_source: object,
    trusted_writers: Iterable[str],
) -> LimitVerdict:
    """A raise needs a concrete human grant; a lower limit only ever closes."""
    if not load.usable:
        return LimitVerdict(
            False, unit if _nonempty_str(unit) else None, None, None, load.issues
        )
    policy = load.policy
    assert policy is not None
    current = policy.limit_for(str(unit)) if _nonempty_str(unit) else None
    if current is None:
        return LimitVerdict(
            False,
            unit if _nonempty_str(unit) else None,
            None,
            None,
            (
                PolicyIssue(
                    "limit-unit-unknown",
                    str(unit),
                    "unit has no explicit hard limit in the policy",
                ),
            ),
        )
    if not _is_int(new_limit) or int(new_limit) <= 0:
        return LimitVerdict(
            False,
            current.unit,
            current.limit,
            None,
            (PolicyIssue("limit-value-invalid", current.unit, "positive integer required"),),
        )
    target = int(new_limit)
    if target <= current.limit:
        # Lowering never grants new investment, so it needs no new authority.
        return LimitVerdict(True, current.unit, current.limit, target)

    reasons: list[PolicyIssue] = []
    if not isinstance(grant, Mapping):
        return LimitVerdict(
            False,
            current.unit,
            current.limit,
            None,
            (
                PolicyIssue(
                    "limit-grant-missing",
                    "limit-grant",
                    "raising a hard limit needs an explicit human authorization",
                ),
            ),
        )
    grant_unit = grant.get("unit", current.unit)
    delta = grant.get("delta")
    purpose = grant.get("purpose")
    risk = grant.get("risk")
    if not _nonempty_str(grant_unit) or str(grant_unit) != current.unit:
        reasons.append(
            PolicyIssue(
                "limit-grant-unit-mismatch",
                "limit-grant.unit",
                f"expected {current.unit}, got {grant_unit!r}",
            )
        )
    if not _is_int(delta) or int(delta) != target - current.limit:
        reasons.append(
            PolicyIssue(
                "limit-grant-delta-mismatch",
                "limit-grant.delta",
                f"expected exactly {target - current.limit}, got {delta!r}",
            )
        )
    if not _nonempty_str(purpose):
        reasons.append(
            PolicyIssue(
                "limit-grant-purpose-missing",
                "limit-grant.purpose",
                "the concrete purpose of the extra investment is required",
            )
        )
    if not _nonempty_str(risk):
        reasons.append(
            PolicyIssue(
                "limit-grant-risk-missing",
                "limit-grant.risk",
                "the concrete risk of the extra investment is required",
            )
        )
    resolution = _resolve_authority(
        grant.get("authority_ref"), authority_source, ("budget:increase",), trusted_writers
    )
    reasons.extend(resolution.issues)
    if resolution.record is not None and resolution.record.kind not in HUMAN_AUTHORITY_KINDS:
        reasons.append(
            PolicyIssue(
                "limit-grant-not-human",
                resolution.record.authority_ref,
                "only an explicit human authorization may raise a hard limit",
            )
        )
    if reasons:
        return LimitVerdict(False, current.unit, current.limit, None, tuple(reasons))
    return LimitVerdict(True, current.unit, current.limit, target)


# ── soft round extension ─────────────────────────────────────────────────────


def evaluate_soft_extension(
    load: PolicyLoad,
    *,
    note: object,
    usage: object,
    authority_source: object,
    trusted_writers: Iterable[str],
    required_scope: Sequence[str] = ("extension:soft-round",),
) -> ExtensionVerdict:
    """Grant exactly the note's explicit delta, only under a real authorization."""
    if not load.usable:
        return ExtensionVerdict(False, None, None, None, load.issues)
    policy = load.policy
    assert policy is not None
    extension = policy.soft_round_extension
    if extension is None or not extension.allowed:
        return ExtensionVerdict(
            False,
            None,
            None,
            None,
            (
                PolicyIssue(
                    "extension-not-authorized",
                    "soft_round_extension",
                    "the policy does not authorize a soft round extension",
                ),
            ),
        )
    note_map = note if isinstance(note, Mapping) else {}
    reasons: list[PolicyIssue] = []
    resolution = _resolve_authority(
        extension.authority_ref, authority_source, required_scope, trusted_writers
    )
    reasons.extend(resolution.issues)
    uncovered = [
        token
        for token in required_scope
        if not _scope_covers(extension.scope, token)
    ]
    if uncovered:
        reasons.append(
            PolicyIssue(
                "extension-scope-uncovered",
                "soft_round_extension.scope",
                "not covered: " + ", ".join(uncovered),
            )
        )
    if not _nonempty_str(note_map.get("progress")):
        reasons.append(
            PolicyIssue(
                "note-progress-missing",
                "note.progress",
                "real progress evidence is required",
            )
        )
    unit = note_map.get("budget_unit")
    amount = note_map.get("budget_amount")
    if not _nonempty_str(unit) or not _is_int(amount):
        reasons.append(
            PolicyIssue(
                "note-budget-missing",
                "note.budget",
                "an explicit budget unit and delta are required",
            )
        )
    source = note_map.get("budget_source")
    if not _nonempty_str(source):
        reasons.append(
            PolicyIssue(
                "note-budget-source-missing",
                "note.budget_source",
                "the budget basis must name its source",
            )
        )
    elif str(source) in HARD_BALANCE_SOURCES:
        reasons.append(
            PolicyIssue(
                "note-budget-source-hard-balance",
                "note.budget_source",
                "remaining hard budget is not an authorization for extra rounds",
            )
        )
    if not _nonempty_str(note_map.get("next_goal")):
        reasons.append(
            PolicyIssue("note-goal-missing", "note.next_goal", "next-round goal required")
        )
    if not _nonempty_str(note_map.get("next_plan")):
        reasons.append(
            PolicyIssue("note-plan-missing", "note.next_plan", "next-round plan required")
        )
    if not _nonempty_str(note_map.get("stop_criterion")):
        reasons.append(
            PolicyIssue(
                "note-stop-missing",
                "note.stop_criterion",
                "an end criterion is required",
            )
        )
    if reasons:
        return ExtensionVerdict(False, None, None, None, tuple(reasons))
    spend = check_spend(load, unit=unit, amount=amount, usage=usage)
    if not spend.allowed:
        return ExtensionVerdict(False, spend.unit, None, None, spend.reasons)
    return ExtensionVerdict(True, spend.unit, spend.requested, spend.used_after)


# ── gate release ─────────────────────────────────────────────────────────────


def evaluate_gate(
    load: PolicyLoad,
    *,
    choice: object,
    hard_checks: object,
    automation_enabled: object,
    required_scope: Sequence[str],
    authority_source: object,
    trusted_writers: Iterable[str],
) -> GateVerdict:
    """No release without enablement, authority, hard checks and an approve."""
    reasons: list[PolicyIssue] = []
    follow_up = _GATE_FOLLOW_UP.get(str(choice)) if choice is not None else None
    if automation_enabled is not True:
        reasons.append(
            PolicyIssue(
                "automation-disabled",
                "automation_enabled",
                "automatic processing is disabled; no choice can release",
            )
        )
    if not load.usable:
        reasons.extend(load.issues)
    if not isinstance(hard_checks, Mapping) or not hard_checks:
        reasons.append(
            PolicyIssue(
                "hard-checks-missing",
                "hard_checks",
                "machine hard checks must be evaluated, not assumed",
            )
        )
    else:
        for name in sorted(hard_checks):
            if hard_checks[name] is not True:
                reasons.append(
                    PolicyIssue(
                        "hard-check-failed",
                        str(name),
                        f"machine hard check {name} did not pass",
                    )
                )
    release_scope: tuple[str, ...] = ()
    if load.usable:
        policy = load.policy
        assert policy is not None
        coverage = _covered_scope(policy.scope, required_scope)
        uncovered = [token for token in required_scope if token not in coverage]
        if uncovered:
            reasons.append(
                PolicyIssue(
                    "scope-not-granted",
                    "scope",
                    "policy does not grant: " + ", ".join(uncovered),
                )
            )
        resolution = _resolve_authority(
            policy.authority_ref, authority_source, required_scope, trusted_writers
        )
        reasons.extend(resolution.issues)
        release_scope = coverage
    if str(choice) != "approve":
        reasons.append(
            PolicyIssue(
                "choice-not-approve",
                "choice",
                f"{choice!r} is not an approval; nothing is released",
            )
        )
    if release_scope and required_scope and not release_scope:
        reasons.append(PolicyIssue("released-scope-empty", "scope", "empty release"))
    if reasons:
        return GateVerdict(False, (), follow_up, False, tuple(reasons))
    return GateVerdict(True, release_scope, follow_up, False)


# ── pending-review recheck ───────────────────────────────────────────────────


def evaluate_pending_review(
    load: PolicyLoad,
    *,
    trigger: object,
    state: object,
    usage: object,
    authority_source: object,
    trusted_writers: Iterable[str],
) -> PendingReviewVerdict:
    """An event only triggers evaluation; resume still needs an approve."""
    state_map = state if isinstance(state, Mapping) else {}
    trigger_map = trigger if isinstance(trigger, Mapping) else {}
    reasons: list[PolicyIssue] = []
    if state_map.get("pending_review") is not True:
        reasons.append(
            PolicyIssue(
                "pending-review-not-pending",
                "pending_review",
                "not in pending-review: nothing to recheck",
            )
        )
    if not load.usable:
        reasons.extend(load.issues)
    required_scope, scope_issue = _required_scope(
        state_map.get("required_scope"), "required_scope"
    )
    if scope_issue is not None:
        reasons.append(scope_issue)
    if not _nonempty_str(state_map.get("choice")):
        reasons.append(
            PolicyIssue(
                "decision-missing",
                "choice",
                f"review trigger {trigger_map.get('kind')!r} needs a real decision; "
                "it never auto-resumes",
            )
        )
    elif str(state_map.get("choice")) != "approve":
        reasons.append(
            PolicyIssue(
                "choice-not-approve",
                "choice",
                f"{state_map.get('choice')!r} does not resume the pending review",
            )
        )
    if state_map.get("goal_effective") is not True:
        reasons.append(
            PolicyIssue("goal-not-effective", "goal_effective", "goal version is not valid")
        )
    if state_map.get("blocker_cleared") is not True:
        reasons.append(
            PolicyIssue("blocker-not-cleared", "blocker_cleared", "blocker still present")
        )
    evidence = _str_tuple(state_map.get("evidence"))
    if not evidence:
        reasons.append(
            PolicyIssue(
                "review-evidence-missing",
                "evidence",
                "reviewable evidence is required before resuming",
            )
        )
    spend = check_spend(
        load,
        unit=state_map.get("budget_unit"),
        amount=state_map.get("budget_amount"),
        usage=usage,
    )
    if not spend.allowed:
        reasons.append(
            PolicyIssue(
                "budget-not-sufficient",
                "budget",
                "no verified remaining budget for the resumed step",
            )
        )
        reasons.extend(spend.reasons)
    if load.usable:
        policy = load.policy
        assert policy is not None
        uncovered = [
            token for token in required_scope if not _scope_covers(policy.scope, token)
        ]
        if uncovered:
            reasons.append(
                PolicyIssue(
                    "review-scope-uncovered",
                    "scope",
                    "policy does not grant: " + ", ".join(uncovered),
                )
            )
        resolution = _resolve_authority(
            policy.authority_ref, authority_source, required_scope, trusted_writers
        )
        reasons.extend(resolution.issues)
    if reasons:
        return PendingReviewVerdict(False, (), False, tuple(reasons))
    policy = load.policy
    assert policy is not None
    resume_scope = _covered_scope(policy.scope, required_scope)
    if not resume_scope:
        # fail closed: an allowed resume always carries a concrete scope
        return PendingReviewVerdict(
            False,
            (),
            False,
            (
                PolicyIssue(
                    "resume-scope-empty",
                    "required_scope",
                    "an empty resume scope is never granted",
                ),
            ),
        )
    return PendingReviewVerdict(True, resume_scope, False)


# ── recovery ─────────────────────────────────────────────────────────────────


_RECOVERY_NOTE_FIELDS = (
    ("stop_reason", "recovery-note-stop-reason-missing"),
    ("elimination_evidence", "recovery-note-elimination-missing"),
    ("stage_version", "recovery-note-stage-version-missing"),
    ("affected_keys", "recovery-note-keys-missing"),
    ("target_plan", "recovery-note-plan-missing"),
    ("authority_ref", "recovery-note-authority-missing"),
    ("residual_budget", "recovery-note-budget-missing"),
    ("stop_criterion", "recovery-note-stop-criterion-missing"),
)


def _recovery_blocked(
    reasons: Sequence[PolicyIssue],
    *,
    questions: Sequence[str] = (),
    preserved_facts: Sequence[str] = (),
    usage: object = None,
) -> RecoveryVerdict:
    return RecoveryVerdict(
        False,
        (),
        (),
        (),
        tuple(preserved_facts),
        _usage_pairs(usage),
        tuple(questions),
        False,
        tuple(reasons),
    )


def _usage_pairs(usage: object) -> tuple[tuple[str, int], ...]:
    usage_map = _usage_map(usage)
    if usage_map is None:
        return ()
    pairs = [
        (str(unit), int(amount))
        for unit, amount in usage_map.items()
        if _is_int(amount)
    ]
    return tuple(sorted(pairs))


def evaluate_halted_recovery(
    load: PolicyLoad,
    *,
    request: object,
    usage: object,
    authority_source: object,
    trusted_writers: Iterable[str],
) -> RecoveryVerdict:
    """Resume a halted stage inside the policy's own scope, preserving history."""
    request_map = request if isinstance(request, Mapping) else {}
    note = request_map.get("note")
    note_map = note if isinstance(note, Mapping) else {}
    preserved: list[str] = []
    if _nonempty_str(note_map.get("stop_reason")):
        preserved.append(str(note_map["stop_reason"]))
    evidence = _str_tuple(note_map.get("elimination_evidence")) or ()
    preserved.extend(evidence)
    if _nonempty_str(note_map.get("stage_version")):
        preserved.append(str(note_map["stage_version"]))

    if request_map.get("stage_halted") is not True:
        return _recovery_blocked(
            (
                PolicyIssue(
                    "not-halted",
                    "stage_halted",
                    "recovery applies only to a halted stage",
                ),
            ),
            preserved_facts=preserved,
            usage=usage,
        )
    if not load.usable:
        return _recovery_blocked(load.issues, preserved_facts=preserved, usage=usage)
    policy = load.policy
    assert policy is not None
    rule = policy.recovery
    if rule is None:
        reasons = load.recovery_issues or (
            PolicyIssue("recovery-not-configured", "recovery", "no recovery rule"),
        )
        return _recovery_blocked(reasons, preserved_facts=preserved, usage=usage)

    reasons: list[PolicyIssue] = []
    for name, code in _RECOVERY_NOTE_FIELDS:
        value = note_map.get(name)
        if name in ("elimination_evidence", "affected_keys"):
            valid = bool(_str_tuple(value))
        elif name == "residual_budget":
            valid = isinstance(value, Mapping) and bool(value)
        else:
            valid = _nonempty_str(value)
        if not valid:
            reasons.append(
                PolicyIssue(code, f"note.{name}", "required for a bounded resume")
            )

    halt_origin = str(request_map.get("halt_origin") or "")
    required_scope, scope_issue = _required_scope(
        request_map.get("required_scope"), "required_scope"
    )
    if scope_issue is not None:
        reasons.append(scope_issue)
    uncovered = [token for token in required_scope if not _scope_covers(rule.scope, token)]
    if uncovered:
        reasons.append(
            PolicyIssue(
                "recovery-scope-uncovered",
                "recovery.scope",
                "not covered: " + ", ".join(uncovered),
            )
        )

    questions: list[str] = []
    if halt_origin not in HALT_ORIGINS:
        reasons.append(
            PolicyIssue(
                "halt-origin-unknown",
                "halt_origin",
                f"{request_map.get('halt_origin')!r} is not a recorded halt origin "
                f"({', '.join(HALT_ORIGINS)}); an unknown stop stays in force",
            )
        )
        questions.append(
            "which recorded halt origin applies (technical stop, user stop or "
            "revocation), and who recorded it?"
        )

    authority_ref = note_map.get("authority_ref")
    request_ref = str(authority_ref).strip() if _nonempty_str(authority_ref) else ""
    human_lift = halt_origin in _HUMAN_HALT_ORIGINS
    request_required = (
        ("recovery:user-stop", *required_scope)
        if human_lift
        else ("recovery:halted", *required_scope)
    )
    resolution = _resolve_authority(
        authority_ref, authority_source, request_required, trusted_writers
    )
    reasons.extend(resolution.issues)
    replaces_rule = (
        resolution.record is not None
        and rule.authority_ref in resolution.record.supersedes
    )
    if replaces_rule:
        # the original link survives as a preserved fact, never erased
        preserved.append(f"superseded-authority:{rule.authority_ref}")
    elif request_ref != rule.authority_ref:
        # the policy rule's own authorization is verified too: another reference
        # must be a writer-recorded explicit replacement, never a free alias
        rule_resolution = _resolve_authority(
            rule.authority_ref,
            authority_source,
            ("recovery:halted", *required_scope),
            trusted_writers,
        )
        reasons.extend(rule_resolution.issues)
        if not human_lift:
            reasons.append(
                PolicyIssue(
                    "recovery-authority-unrelated",
                    "note.authority_ref",
                    "the request authorization is neither the policy recovery "
                    "authorization nor an explicitly recorded replacement of it",
                )
            )
    if human_lift:
        # a user stop/revocation is lifted only by an explicit human authorization
        if (
            resolution.record is None
            or resolution.record.kind not in HUMAN_AUTHORITY_KINDS
        ):
            reasons.append(
                PolicyIssue(
                    "user-stop-requires-explicit-authorization",
                    "note.authority_ref",
                    "a technical fix or a DP choice cannot lift a user stop/revocation",
                )
            )
            questions.append(
                "which explicit human authorization (authority_ref + scope "
                "recovery:user-stop) lifts the recorded user stop/revocation?"
            )

    raw_guard = request_map.get("hard_guard_active")
    if not isinstance(raw_guard, bool):
        reasons.append(
            PolicyIssue(
                "hard-guard-unknown",
                "hard_guard_active",
                f"{raw_guard!r} is not a verified guard state; the stop stays in force",
            )
        )
        questions.append(
            "which machine hard check reports the guard state (active/cleared) "
            "before any resume?"
        )
    elif raw_guard is True:
        raw_cleared = request_map.get("hard_guard_cleared")
        cleared = _str_tuple(raw_cleared)
        if not raw_cleared:
            reasons.append(
                PolicyIssue(
                    "hard-guard-bypass",
                    "hard_guard_active",
                    "an active hard guard cannot be bypassed by a decision or a note",
                )
            )
            questions.append(
                "which machine hard check cleared the active guard, with the "
                "command and result that shows it is gone?"
            )
        elif not cleared or request_map.get("hard_guard_cleared_verified") is not True:
            # a clearance string is a claim; only a machine-verified result counts
            reasons.append(
                PolicyIssue(
                    "guard-clearance-unverified",
                    "hard_guard_cleared",
                    "guard clearance needs a machine-verified result, not a self-report",
                )
            )

    if str(request_map.get("choice")) != "approve":
        reasons.append(
            PolicyIssue(
                "recovery-choice-not-approve",
                "choice",
                f"{request_map.get('choice')!r} is not an approval",
            )
        )

    residual = note_map.get("residual_budget")
    if isinstance(residual, Mapping):
        usage_map = _usage_map(usage) or {}
        for raw_unit, raw_amount in residual.items():
            unit = str(raw_unit)
            limit = policy.limit_for(unit)
            if limit is None:
                reasons.append(
                    PolicyIssue(
                        "recovery-residual-unknown",
                        f"note.residual_budget.{unit}",
                        "residual budget names a unit without a hard limit",
                    )
                )
                continue
            used = usage_map.get(unit)
            if not _is_int(used) or int(used) < 0:
                reasons.append(
                    PolicyIssue(
                        "budget-usage-unknown",
                        unit,
                        "cumulative usage is not verifiable",
                    )
                )
                continue
            if not _is_int(raw_amount):
                reasons.append(
                    PolicyIssue(
                        "recovery-residual-exceeds",
                        f"note.residual_budget.{unit}",
                        "residual budget must be a non-negative integer",
                    )
                )
                continue
            remaining = limit.limit - int(used)
            if int(raw_amount) < 0 or int(raw_amount) > remaining:
                reasons.append(
                    PolicyIssue(
                        "recovery-residual-exceeds",
                        f"note.residual_budget.{unit}",
                        f"{raw_amount} exceeds the verified remaining {remaining}",
                    )
                )

    if reasons:
        return _recovery_blocked(
            reasons, questions=questions, preserved_facts=preserved, usage=usage
        )

    granted_scope = _covered_scope(rule.scope, required_scope)
    if not granted_scope:
        return _recovery_blocked(
            (
                PolicyIssue(
                    "resume-scope-empty",
                    "required_scope",
                    "an empty resume scope is never granted",
                ),
            ),
            questions=questions,
            preserved_facts=preserved,
            usage=usage,
        )
    return RecoveryVerdict(
        True,
        granted_scope,
        rule.observation_conditions,
        rule.stop_conditions,
        tuple(preserved),
        _usage_pairs(usage),
        (),
        False,
    )


def evaluate_breaker_recovery(
    load: PolicyLoad,
    *,
    request: object,
    authority_source: object,
    trusted_writers: Iterable[str],
    controlled_channels: Iterable[str],
) -> RecoveryVerdict:
    """H12: only an isolated controlled channel may limit-release the brake."""
    request_map = request if isinstance(request, Mapping) else {}
    channels = frozenset(controlled_channels)
    channel = str(request_map.get("channel") or "")
    tripped = str(request_map.get("tripped_chain") or "")
    origin = str(request_map.get("origin") or "")
    preserved: list[str] = []
    if tripped:
        preserved.append(f"tripped-chain:{tripped}")
    if _nonempty_str(request_map.get("preauthorization_ref")):
        preserved.append(f"preauthorization:{request_map['preauthorization_ref']}")

    reasons: list[PolicyIssue] = []
    questions: list[str] = []

    raw_disabled = request_map.get("user_disabled")
    if not isinstance(raw_disabled, bool):
        # an unknown state is not "automation enabled"
        reasons.append(
            PolicyIssue(
                "breaker-disable-unknown",
                "user_disabled",
                f"{raw_disabled!r} is not a recorded user state; "
                "the brake stays engaged",
            )
        )
        questions.append(
            "which recorded user state (automation enabled / disabled by the user) "
            "applies before this recovery?"
        )
    elif raw_disabled is True:
        reasons.append(
            PolicyIssue(
                "user-disabled",
                "user_disabled",
                "the user disabled or revoked automation; the brake stays engaged",
            )
        )
        questions.append(
            "which explicit user authorization lifts the recorded disable/revocation, "
            "and for which scope?"
        )
    if request_map.get("transport_available") is not True:
        reasons.append(
            PolicyIssue(
                "transport-unavailable",
                "transport_available",
                "the primary decision transport is unavailable; no alternate channel",
            )
        )
        questions.append(
            "which machine check shows the primary decision transport is available "
            "again before any recovery?"
        )
    if tripped and channel and channel == tripped:
        reasons.append(
            PolicyIssue(
                "breaker-self-approval",
                "channel",
                "the chain that tripped the breaker cannot approve its own recovery",
            )
        )
    elif channel not in channels:
        reasons.append(
            PolicyIssue(
                "transport-not-controlled",
                "channel",
                f"{channel!r} is not a caller-declared isolated recovery channel",
            )
        )
    if not origin:
        reasons.append(
            PolicyIssue(
                "breaker-origin-unknown",
                "origin",
                "no recorded recovery origin; the brake stays engaged",
            )
        )
    elif origin in NON_AUTHORITATIVE_ORIGINS:
        reasons.append(
            PolicyIssue(
                "breaker-origin-not-authoritative",
                "origin",
                f"{origin!r} is self-reported and proves nothing",
            )
        )

    rule: RecoveryRule | None = None
    if not load.usable:
        reasons.extend(load.issues)
    else:
        policy = load.policy
        assert policy is not None
        rule = policy.recovery
        if rule is None:
            reasons.extend(
                load.recovery_issues
                or (PolicyIssue("recovery-not-configured", "recovery", "no recovery rule"),)
            )
        else:
            if origin not in rule.allowed_origins:
                reasons.append(
                    PolicyIssue(
                        "breaker-origin-not-allowed",
                        "origin",
                        f"{origin!r} is not an allowed recovery origin",
                    )
                )

    if not _nonempty_str(request_map.get("preauthorization_ref")):
        reasons.append(
            PolicyIssue(
                "breaker-preauth-missing",
                "preauthorization_ref",
                "no preauthorization reference for this recovery",
            )
        )
        questions.append(
            "which explicit preauthorization (authority_ref + recorded_at) precedes "
            "this recovery request?"
        )
    evidence = _str_tuple(request_map.get("reason_elimination_evidence"))
    if not evidence:
        reasons.append(
            PolicyIssue(
                "breaker-elimination-missing",
                "reason_elimination_evidence",
                "no reviewable evidence that the breaker reason is gone",
            )
        )
        questions.append(
            "which reviewable evidence shows the breaker reason is eliminated?"
        )
    checks = request_map.get("machine_checks")
    if not isinstance(checks, Mapping) or not checks:
        reasons.append(
            PolicyIssue(
                "machine-checks-missing",
                "machine_checks",
                "machine checks must run and pass, never be assumed",
            )
        )
    else:
        for name in sorted(checks):
            if checks[name] is not True:
                reasons.append(
                    PolicyIssue(
                        "machine-check-failed",
                        str(name),
                        f"machine check {name} did not pass",
                    )
                )
    if str(request_map.get("choice")) != "approve":
        reasons.append(
            PolicyIssue(
                "recovery-choice-not-approve",
                "choice",
                f"{request_map.get('choice')!r} is not an approval; reject never closes",
            )
        )

    required_scope, scope_issue = _required_scope(
        request_map.get("required_scope"), "required_scope"
    )
    if scope_issue is not None:
        reasons.append(scope_issue)
    if rule is not None:
        uncovered = [
            token for token in required_scope if not _scope_covers(rule.scope, token)
        ]
        if uncovered:
            reasons.append(
                PolicyIssue(
                    "recovery-scope-uncovered",
                    "recovery.scope",
                    "not covered: " + ", ".join(uncovered),
                )
            )
        preauth_ref = request_map.get("preauthorization_ref")
        preauth = str(preauth_ref).strip() if _nonempty_str(preauth_ref) else ""
        resolution = _resolve_authority(
            preauth_ref,
            authority_source,
            ("recovery:breaker", *required_scope),
            trusted_writers,
        )
        reasons.extend(resolution.issues)
        if preauth != rule.authority_ref:
            # the policy rule's own preauthorization is verified too: another
            # reference must be a writer-recorded explicit replacement
            if (
                resolution.record is not None
                and rule.authority_ref in resolution.record.supersedes
            ):
                preserved.append(f"superseded-authority:{rule.authority_ref}")
            else:
                rule_resolution = _resolve_authority(
                    rule.authority_ref,
                    authority_source,
                    ("recovery:breaker", *required_scope),
                    trusted_writers,
                )
                reasons.extend(rule_resolution.issues)
                reasons.append(
                    PolicyIssue(
                        "recovery-authority-unrelated",
                        "preauthorization_ref",
                        "the preauthorization is neither the policy recovery "
                        "authorization nor an explicitly recorded replacement of it",
                    )
                )
        if (
            resolution.record is not None
            and resolution.record.writer
            not in frozenset(trusted_writers)
        ):
            reasons.append(
                PolicyIssue(
                    "authority-writer-untrusted",
                    resolution.record.writer,
                    "the preauthorization does not come from a controlled writer",
                )
            )

    if reasons or rule is None:
        return _recovery_blocked(
            reasons, questions=questions, preserved_facts=preserved
        )
    granted_scope = _covered_scope(rule.scope, required_scope)
    if not granted_scope:
        return _recovery_blocked(
            (
                PolicyIssue(
                    "resume-scope-empty",
                    "required_scope",
                    "an empty resume scope is never granted",
                ),
            ),
            questions=questions,
            preserved_facts=preserved,
        )
    return RecoveryVerdict(
        True,
        granted_scope,
        rule.observation_conditions,
        rule.stop_conditions,
        tuple(preserved),
        (),
        (),
        False,
    )


def observe_recovery(
    recovery: RecoveryVerdict,
    *,
    observed_conditions: Iterable[str] = (),
    failed_checks: Iterable[str] = (),
) -> ObservationVerdict:
    """Observation after a limited recovery: any stop condition re-trips."""
    if not recovery.allowed:
        return ObservationVerdict(
            False,
            "engaged",
            True,
            (
                PolicyIssue(
                    "recovery-not-active",
                    "",
                    "no recovery was granted; the brake stays engaged",
                ),
            ),
        )
    hits = tuple(
        condition
        for condition in observed_conditions
        if condition in recovery.stop_conditions
    )
    failures = tuple(str(check) for check in failed_checks)
    reasons: list[PolicyIssue] = []
    if hits:
        reasons.append(
            PolicyIssue(
                "stop-condition-observed",
                ",".join(hits),
                "the recovery reason reappeared; re-engage the original brake",
            )
        )
    for name in failures:
        reasons.append(
            PolicyIssue(
                "machine-check-failed",
                name,
                "a post-recovery machine check failed; re-engage the brake",
            )
        )
    if reasons:
        return ObservationVerdict(True, "engaged", True, tuple(reasons))
    return ObservationVerdict(False, "released", True)
