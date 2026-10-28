"""Read-only project history fold for the decision dashboard (T07).

One project-wide, read-only view over *every* recorded decision carrier. The
module never writes: there is no lock, no append and no repair path here, so a
history read cannot move an archive row, a sign-off file or a wire ledger.

Carriers (design §3, §5.4)

* archive ``.agenticdoc/_autopilot/decisions.jsonl`` - the authoritative,
  hash-chained record (``decide_archive``: ``decide`` / ``override`` /
  ``settle`` / ``authority-change``).
* wire side ledger ``.agenticdoc/_autopilot/decisions-wire.jsonl`` - schema v1
  transport capture (``decision_wire``: attempt-start/end, call-end,
  decision-end, submission-*, book-snapshot).
* lifecycle side ledger ``.agenticdoc/_autopilot/decision-lifecycle.jsonl`` -
  schema v1 ``kind=lifecycle`` rows (suggested / adopted / consumed /
  responded / steered / human-answer / human-override / authority-change /
  signoff / settled / local-decision / executed).
* human carriers ``<key>/evidence/review/sign-final.md`` (``decide_signoff``
  machine lines) and ``.agenticdoc/_autopilot/gates/gate-NNNN.md``
  (``autopilot.gates`` frontmatter).

Honesty rules (VC-002/003/013, design §2.2)

* ``actor``, ``answer_source`` and the derived ``source`` claim are three
  separate :class:`Claim` values, each with the recorded basis that supports
  it. ``authority=human`` on an archive row is an escalation marker, *not*
  evidence that a human acted (``flags`` carries ``authority-human-not-action``
  for every such row).
* Suggestion, adoption, consumption, response, execution and the human /
  sign-off / settle facts are separate stages. An absent stage is
  ``not-recorded`` (never "ok"); an attempt without an end is ``pending`` and
  an archive decision without a settle row has ``status=pending``.
* Logical calls and real HTTP attempts are counted separately. A
  ``zero_call=True`` client row is not a model request, a missing
  ``wire_attempts`` is not backfilled to 1, and a record with no ledger rows at
  all reports ``CallCounts.recorded=False`` with ``None`` counts (module
  unavailable and "nothing recorded" are both "not recorded", never 0).
* ``usage`` / ``policy`` keys can be redacted, clipped or dropped (T02c), so an
  absent counter is ``UsageFact.missing`` - never a 0 and never "the upstream
  did not send it".
* Links are never guessed: a call without ``decision_id`` is counted as
  unlinked, an unknown lifecycle word is not a stage, and a ``key:`` mismatch
  between a sign-off file and its directory is ignored with a warning.
* Detail rows are keyed by opaque ids (``h-<20 hex>``) built from
  project/scope/identity. A raw ``decision_id``, a traversal string or any
  other value is *not* a handle (no path is ever derived from a record field).
* A record field is never treated as a path: a ``key`` must be a plain
  directory name (``valid_key``) before it may join a sign-off or gate carrier,
  and every carrier read is refused *before* the read when its resolved
  (realpath) location leaves the root it belongs to - a symlinked or junctioned
  sign-off/gate/ledger outside the control root discloses nothing.
* Output safety (design §9, AC-005/VC-005): the archive ``answer`` /
  ``actual_action`` / ``override_reason`` / ``change`` / ``evidence_*`` /
  ``policy`` values, the sign-off ``claim`` and the gate ``question`` / ``note``
  / ``answered_by`` are free text, not schema. They take the same
  redact -> clip -> boundary-scrub path as the wire ledger, using the caller's
  injected known-secret set (``decision.credential_redactor``); without a
  redactor they are withheld (fail-closed) and counted. Structural fields stay
  verbatim but are validated against a closed per-carrier schema - an unnamed
  field is dropped, never echoed.

Safe output contract (T10 injection, AC-005/VC-005)

``load_history(project_dir, redact=<known-secret redactor>)`` is the only
supported entry point for the monitor/service:

* ``redact`` must be ``decision.credential_redactor(cfg, extra_secrets=...)``
  (the production known-secret set: Authorization value, ``cfg.api_key``, the
  resolved timi credential, env heuristics + Bearer/``sk-`` regexes). The
  module never reads credentials itself and never guesses from entropy.
* With a redactor: every free-text value is redacted, then clipped
  (``FREE_TEXT_LIMIT``) with the cut boundary scrubbed; each record carries
  ``redaction`` marks (``substitutions``/``redacted_fields``/
  ``truncated_fields``) and a ``basis`` string, plus the ``flags``
  ``free-text-redacted`` / ``free-text-truncated``.
* With a redactor, *every* emitted string is also scanned at the output
  boundary, not only the fields the schema calls free text: structural values
  (``model``/``transport``/``reason``/``escalated_reason``/``override_by``/
  ``key``/``task_key``/``decision_id``/capture copies/``path`` labels), any
  mapping key, and the derived ``basis``/``flags`` text (T07c). The warnings
  stream keeps its own redact-then-withhold path (``sanitize_warning``), which
  is locked by the same tests.
  A legal shape is not an exemption: a token/identity-shaped value that the
  injected known-secret set recognises is **omitted** (``None`` or a dropped
  mapping entry, never a ``<redacted>`` placeholder that a consumer could take
  for a real id) and counted as ``redaction.structural_withheld`` with the
  ``structural-secret-withheld`` flag. Omission is output-only: joins, opaque
  ids, page filters and the record's own fields keep the raw value, so the
  reader still finds the carrier it must not display.
* Without a redactor: unprovable free text is *omitted* (``None``/dropped keys)
  and counted as ``omitted_fields`` with ``free-text-omitted``; the payload says
  ``redaction.enabled=false``. Nothing is HTML-escaped - escaping is a DOM
  concern and does not stop a credential from being read.
* Free-text omission never fabricates data: an omitted value is ``None``/
  absent, never ``""`` and never a placeholder answer.

Scope separation: production rows live in the control tree, test rows in an
explicit test root (``decision_wire.test_scope``). Statistics are reported per
scope; a ``scope=="test"`` row found in the production sink is counted as
misplaced and never enters the production page.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import pathlib
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import decide_archive
import decide_signoff
import decision_wire
import mw_common
from autopilot import gates

DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200

#: Record-level stages. ``book`` (the captured book snapshot) and ``steered``
#: (dp3 injection, deliberately weaker than ``consumed``) travel alongside them
#: in :attr:`HistoryRecord.stages` but are not part of the lifecycle vocabulary.
STAGE_NAMES: tuple[str, ...] = (
    "suggested",
    "adopted",
    "consumed",
    "responded",
    "executed",
    "human_answer",
    "human_override",
    "authority_change",
    "signoff",
    "settled",
)
EXTRA_STAGES: tuple[str, ...] = ("book", "steered")

SOURCE_KINDS: tuple[str, ...] = ("human", "model", "system", "unknown")
STATUSES: tuple[str, ...] = ("pending", "ok", "rework", "rollback", "inconclusive", "unknown")
SCOPE_KINDS: tuple[str, ...] = ("production", "test")
ACTOR_KINDS: tuple[str, ...] = ("human", "system", "unknown")
STAGE_STATES: tuple[str, ...] = ("recorded", "pending", "not-recorded", "inferred", "unknown")
#: Archive row kinds this reader understands (mirrors ``decide_archive``).
ARCHIVE_KINDS: tuple[str, ...] = ("decide", "override", "settle", "authority-change")

#: The lifecycle words this reader understands. Anything else is counted in
#: ``HistoryStats.unknown_lifecycle`` and shown as a warning - it never becomes
#: a stage, because a typo must not invent a lifecycle fact.
LIFECYCLE_VOCAB: frozenset[str] = frozenset(
    {
        "suggested",
        "adopted",
        "consumed",
        "responded",
        "steered",
        "executed",
        "human-answer",
        "human-override",
        "authority-change",
        "signoff",
        "settled",
        "local-decision",
    }
)
OPAQUE_ID_PREFIX = "h-"
OPAQUE_ID_LENGTH = 20
OPAQUE_ID_PATTERN = re.compile(r"^h-[0-9a-f]{20}$")

TEST_WIRE_NAME = "wire.jsonl"
TEST_LIFECYCLE_NAME = "lifecycle.jsonl"
README_LINE_CAP_BYTES = 1024 * 1024

#: Free-text cap (UTF-8 bytes) for one emitted value. Longer text is clipped and
#: its cut boundary scrubbed, so a partial secret never survives the cut.
FREE_TEXT_LIMIT = 2048

_MAX_WARNINGS = 50
_MAX_DECISION_ID_LENGTH = 256
_CAPTURE_RANK = {None: 0, "ok": 1, "partial": 2, "failed": 3}


class HistoryError(ValueError):
    """A history request violates the read contract (bad filter/page value)."""


# ---------------------------------------------------------------------------
# Small value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Claim:
    """One provenance claim: the recorded value plus the basis that supports it.

    ``value is None`` means *not recorded*; it is never a default like
    ``"human"`` or ``"model"``.
    """

    value: str | None = None
    basis: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {"value": self.value, "basis": list(self.basis)}


@dataclass(frozen=True)
class StageFact:
    """One stage of a decision's lifecycle (design §4.4)."""

    state: str
    basis: tuple[str, ...] = ()
    ts: str | None = None
    detail: str | None = None
    event_id: str | None = None
    actor: str | None = None
    answer_source: str | None = None
    target: str | None = None
    supersedes: str | None = None
    result: str | None = None

    def as_dict(self) -> dict[str, object]:
        return {
            "state": self.state,
            "basis": list(self.basis),
            "ts": self.ts,
            "detail": self.detail,
            "event_id": self.event_id,
            "actor": self.actor,
            "answer_source": self.answer_source,
            "target": self.target,
            "supersedes": self.supersedes,
            "result": self.result,
        }


@dataclass(frozen=True)
class CallCounts:
    """Logical calls vs real HTTP attempts (AC-012, T03/T02c downstream)."""

    recorded: bool = False
    logical_calls: int | None = None
    actual_http_attempts: int | None = None
    zero_call: int | None = None
    unrecorded_wire_attempts: int = 0
    basis: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "recorded": self.recorded,
            "logical_calls": self.logical_calls,
            "actual_http_attempts": self.actual_http_attempts,
            "zero_call": self.zero_call,
            "unrecorded_wire_attempts": self.unrecorded_wire_attempts,
            "basis": list(self.basis),
        }


@dataclass(frozen=True)
class UsageFact:
    """Recorded token counters only. A missing counter is missing, never 0.

    ``counters`` is one *attempt's* recorded usage, never a total: several
    attempts overwrite each other in read order, so ``semantics`` names what the
    numbers are (``single-recorded-attempt`` / ``last-recorded-attempt``) and
    ``conflicting`` says whether the recorded attempts disagreed. The per-attempt
    values stay in ``calls[*].attempts[*].usage``; nothing is summed and nothing
    is estimated.
    """

    recorded: bool = False
    counters: dict[str, int] = field(default_factory=dict)
    missing: tuple[str, ...] = ()
    complete: bool = False
    semantics: str = "none"
    attempts_with_usage: int = 0
    conflicting: bool = False
    basis: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "recorded": self.recorded,
            "counters": dict(self.counters),
            "missing": list(self.missing),
            "complete": self.complete,
            "semantics": self.semantics,
            "attempts_with_usage": self.attempts_with_usage,
            "conflicting": self.conflicting,
            "basis": list(self.basis),
        }


@dataclass(frozen=True)
class RedactionMarks:
    """What the read side did to this record's free text (AC-005/VC-005).

    Empty marks with ``enabled=False`` mean every free-text value was withheld:
    the payload is provable, the text is not shown. Counters describe this
    record's own payload only.
    """

    enabled: bool = False
    substitutions: int = 0
    redacted_fields: int = 0
    truncated_fields: int = 0
    omitted_fields: int = 0
    dropped_fields: int = 0
    invalid_fields: int = 0
    #: Structural values / mapping keys omitted at the output boundary because
    #: the injected known-secret set matched them (T07c). They are never
    #: rewritten to a placeholder: ``None`` / a dropped entry is the only form.
    structural_withheld: int = 0
    fields: tuple[str, ...] = ()
    basis: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "substitutions": self.substitutions,
            "redacted_fields": self.redacted_fields,
            "truncated_fields": self.truncated_fields,
            "omitted_fields": self.omitted_fields,
            "dropped_fields": self.dropped_fields,
            "invalid_fields": self.invalid_fields,
            "structural_withheld": self.structural_withheld,
            "fields": list(self.fields),
            "basis": list(self.basis),
        }


@dataclass(frozen=True)
class HistoryRecord:
    """One folded decision (or one ledger-only / submission) record."""

    opaque_id: str
    identity: str
    record_kind: str
    scope: str
    project_id: str
    decision_id: str | None
    dp: str | None
    key: str | None
    task_key: str | None
    submission_id: str | None
    ts: str | None
    source: Claim
    actor: Claim
    answer_source: Claim
    transport: Claim
    model: Claim
    status: str
    stages: dict[str, StageFact]
    call_counts: CallCounts
    usage: UsageFact
    capture_status: str | None
    calls: tuple[dict[str, object], ...]
    archive: dict[str, object] | None
    archive_rows: tuple[dict[str, object], ...]
    signoff: dict[str, object] | None
    gates: tuple[dict[str, object], ...]
    flags: tuple[str, ...]
    missing: tuple[str, ...]
    redaction: RedactionMarks
    #: The injected known-secret set, kept so ``as_dict`` can scan every emitted
    #: string (including structural values and mapping keys) on each call. It is
    #: never serialised and never read by a join.
    redactor: decision_wire.SecretRedactor | None = field(default=None, repr=False, compare=False)

    def _payload(self, *, detail: bool = False) -> dict[str, object]:
        """The raw serialised payload, before the output policy is applied."""
        payload: dict[str, object] = {
            "opaque_id": self.opaque_id,
            "record_kind": self.record_kind,
            "scope": self.scope,
            "project_id": self.project_id,
            "decision_id": self.decision_id,
            "dp": self.dp,
            "key": self.key,
            "task_key": self.task_key,
            "submission_id": self.submission_id,
            "ts": self.ts,
            "source": self.source.as_dict(),
            "actor": self.actor.as_dict(),
            "answer_source": self.answer_source.as_dict(),
            "transport": self.transport.as_dict(),
            "model": self.model.as_dict(),
            "status": self.status,
            "stages": {name: fact.as_dict() for name, fact in self.stages.items()},
            "call_counts": self.call_counts.as_dict(),
            "usage": self.usage.as_dict(),
            "capture_status": self.capture_status,
            "calls": [dict(call) for call in self.calls] if detail else [_call_summary(call) for call in self.calls],
            "signoff": dict(self.signoff) if self.signoff is not None else None,
            "gates": [dict(item) for item in self.gates],
            "flags": list(self.flags),
            "missing": list(self.missing),
            "redaction": self.redaction.as_dict(),
        }
        if detail:
            payload["archive"] = dict(self.archive) if self.archive is not None else None
            payload["archive_rows"] = [dict(row) for row in self.archive_rows]
        return payload

    def as_dict(self, *, detail: bool = False) -> dict[str, object]:
        """JSON-safe payload; every string passes the output policy on each call.

        With an injected redactor, a structural value, a mapping key or a
        provenance/basis string that the known-secret set recognises is omitted
        (``None``/dropped entry/``<basis withheld: known secret>``), never
        echoed and never turned into a placeholder id. The record's own fields
        keep the raw value, so joins and opaque ids stay stable.
        """
        payload = self._payload(detail=detail)
        if self.redactor is not None:
            payload = _scrub_output(payload, self.redactor, withheld=[])
        return payload


def _call_summary(call: Mapping[str, object]) -> dict[str, object]:
    return {
        name: call.get(name)
        for name in (
            "call_id",
            "logical_attempts",
            "wire_attempts",
            "zero_call",
            "available",
            "reason",
            "transport",
            "model",
            "confidence_source",
            "capture_status",
            "not_recorded",
        )
    }


@dataclass(frozen=True)
class HistoryStats:
    """Read-side counters (damaged input is counted, never silently dropped)."""

    archive_rows: int = 0
    archive_damaged: int = 0
    chain_breaks: int = 0
    seq_breaks: int = 0
    wire_events: int = 0
    lifecycle_events: int = 0
    wire_damaged: int = 0
    lifecycle_damaged: int = 0
    unknown_schema: int = 0
    unknown_kind: int = 0
    unknown_scope: int = 0
    unknown_lifecycle: int = 0
    invalid_ids: int = 0
    foreign_rows: int = 0
    unlinked_call_ids: int = 0
    unlinked_events: int = 0
    production_records: int = 0
    test_records: int = 0
    misplaced_test_rows: int = 0
    gates_recorded: int = 0
    gates_keyless: int = 0
    gates_unreadable: int = 0
    invalid_keys: int = 0
    blocked_reads: int = 0

    def as_dict(self) -> dict[str, int]:
        return dataclasses.asdict(self)


@dataclass(frozen=True)
class HistoryPage:
    records: tuple[HistoryRecord, ...]
    total: int
    limit: int
    offset: int
    filters: dict[str, str]
    has_more: bool


@dataclass(frozen=True)
class HistorySnapshot:
    control_root: pathlib.Path
    project_id: str
    records: tuple[HistoryRecord, ...]
    stats: HistoryStats
    warnings: tuple[str, ...]

    def page(
        self,
        *,
        key: str | None = None,
        dp: str | None = None,
        source: str | None = None,
        status: str | None = None,
        scope: str = "production",
        limit: int = DEFAULT_PAGE_LIMIT,
        offset: int = 0,
    ) -> HistoryPage:
        """Filtered, paginated view (default: production scope, newest first)."""
        if scope not in SCOPE_KINDS:
            raise HistoryError(f"scope must be one of {SCOPE_KINDS}, got {scope!r}")
        if source is not None and source not in SOURCE_KINDS:
            raise HistoryError(f"source must be one of {SOURCE_KINDS}, got {source!r}")
        if status is not None and status not in STATUSES:
            raise HistoryError(f"status must be one of {STATUSES}, got {status!r}")
        for name, value in (("key", key), ("dp", dp)):
            if value is None:
                continue
            if not isinstance(value, str) or not value:
                raise HistoryError(f"{name} filter must be a non-empty string")
            if "/" in value or "\\" in value or ".." in value:
                raise HistoryError(f"{name} filter is a value, not a path: {value!r}")
        if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= MAX_PAGE_LIMIT:
            raise HistoryError(f"limit must be an integer in 1..{MAX_PAGE_LIMIT}")
        if not isinstance(offset, int) or isinstance(offset, bool) or offset < 0:
            raise HistoryError("offset must be a non-negative integer")

        selected: list[HistoryRecord] = []
        for record in self.records:
            if record.scope != scope:
                continue
            if key is not None and record.key != key:
                continue
            if dp is not None and record.dp != dp:
                continue
            if source is not None and record.source.value != source:
                continue
            if status is not None and record.status != status:
                continue
            selected.append(record)
        total = len(selected)
        window = selected[offset : offset + limit]
        return HistoryPage(
            records=tuple(window),
            total=total,
            limit=limit,
            offset=offset,
            filters={
                "key": key or "",
                "dp": dp or "",
                "source": source or "",
                "status": status or "",
                "scope": scope,
            },
            has_more=offset + len(window) < total,
        )

    def detail(self, opaque_id: str) -> HistoryRecord | None:
        """Look up one record by its opaque id (never by a raw id or a path)."""
        if not isinstance(opaque_id, str) or not OPAQUE_ID_PATTERN.match(opaque_id):
            return None
        for record in self.records:
            if record.opaque_id == opaque_id:
                return record
        return None


# ---------------------------------------------------------------------------
# Identity helpers
# ---------------------------------------------------------------------------


def opaque_id_for(project_id: str, scope: str, identity: str) -> str:
    """Stable path-free handle for one record within one project scope."""
    material = "\x1f".join((project_id, scope, identity))
    return OPAQUE_ID_PREFIX + hashlib.sha256(material.encode("utf-8")).hexdigest()[:OPAQUE_ID_LENGTH]


def is_human_identity(value: object) -> bool:
    """``human`` / ``human:<account>`` - the archive's own rule, mirrored here.

    A declared identity string, not OS authentication: every consumer labels it
    as declared.
    """
    if not isinstance(value, str) or not value:
        return False
    if value == "human":
        return True
    head, _sep, tail = value.partition(":")
    return head == "human" and bool(tail) and not any(ch.isspace() for ch in tail)


def _valid_decision_id(value: object) -> bool:
    """A structural id is a *value*: bounded, no separators, no traversal."""
    if not isinstance(value, str) or not value or len(value) > _MAX_DECISION_ID_LENGTH:
        return False
    if "\x00" in value or "/" in value or "\\" in value or ".." in value:
        return False
    return ":" in value


def _valid_identity_text(value: object) -> bool:
    return isinstance(value, str) and bool(value) and len(value) <= 512 and "\x00" not in value


_KEY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_TOKEN_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}$")
_SHA16_RE = re.compile(r"^[0-9a-f]{16}$")
_SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
_QVERSION_RE = re.compile(r"^q-[0-9a-f]{8}$")
_GATE_ID_RE = re.compile(r"^gate-[0-9]{1,9}$")


def valid_key(value: object) -> bool:
    """A record's ``key`` is one directory *name*, never a path fragment.

    The closed shape is what makes ``<root>/.agenticdoc/<key>/...`` safe to
    build: no separators, no ``..``, no absolute form, no leading ``_``/``.``
    (those are the ``.agenticdoc`` bookkeeping dirs).
    """
    if not isinstance(value, str) or not value:
        return False
    return bool(_KEY_RE.match(value))


def _valid_ts(value: object) -> bool:
    return isinstance(value, str) and 0 < len(value) <= 64 and "\x00" not in value


def _valid_relpath(value: object) -> bool:
    """A relative, separator-clean path label (never re-rooted by a consumer)."""
    if not isinstance(value, str) or not value or len(value) > 512:
        return False
    if value.startswith("/") or "\\" in value or "\x00" in value:
        return False
    return all(part not in ("", "..") for part in value.split("/"))


#: Closed vocabularies mirrored from the writers (``decide_archive`` /
#: ``decide_signoff`` / ``autopilot.gates``). A value outside its vocabulary is
#: not schema: it is dropped (structural) or redacted as free text.
_CLOSED_SETS: dict[str, frozenset[str]] = {
    "kind": frozenset(ARCHIVE_KINDS),
    "authority": frozenset({"advisory", "binding", "human"}),
    "outcome": frozenset({"pending", "ok", "rework", "rollback", "inconclusive"}),
    "settled_by": frozenset({"pm-auto", "human"}),
    "change_by": frozenset(
        {"human", "human:p0-confirm", "signoff:continue", "signoff:narrow", "signoff:revoke", "refresh"}
    ),
    "mode": frozenset({"auto", "suggest"}),
    "conclusion": frozenset({"continue", "narrow", "revoke"}),
    "confidence_source": frozenset({"api", "model-self-report", "unknown"}),
    "signed_via": frozenset({"auto-decide", "auto-llm", "cli", "tui"}),
}


def _valid_field(kind: str, value: object) -> bool:
    """Validate one structural value against its schema kind."""
    if kind in _CLOSED_SETS:
        return isinstance(value, str) and value in _CLOSED_SETS[kind]
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "digits":
        return isinstance(value, str) and value.isdigit()
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "bool":
        return isinstance(value, bool)
    if kind == "token":
        return isinstance(value, str) and bool(_TOKEN_RE.match(value))
    if kind == "key":
        return valid_key(value)
    if kind == "decision_id":
        return _valid_decision_id(value)
    if kind == "ts":
        return _valid_ts(value)
    if kind == "sha16":
        return isinstance(value, str) and bool(_SHA16_RE.match(value))
    if kind == "sha256":
        return isinstance(value, str) and bool(_SHA256_RE.match(value))
    if kind == "qversion":
        return isinstance(value, str) and bool(_QVERSION_RE.match(value))
    if kind == "gate_id":
        return isinstance(value, str) and bool(_GATE_ID_RE.match(value))
    if kind == "relpath":
        return _valid_relpath(value)
    if kind == "identity":
        return _valid_identity_text(value)
    return False


# ---------------------------------------------------------------------------
# Output safety: redact -> clip -> refuse (AC-005 / VC-005, design §9)
# ---------------------------------------------------------------------------

#: Archive row schema. Structural fields are validated and kept verbatim;
#: free-text fields take the redact/clip/withhold path; an unnamed field is not
#: trusted schema and is dropped (counted). Mirrors ``decide_archive._ROW_FIELDS``
#: without importing it: the read side must not adopt a writer change silently.
_ARCHIVE_STRUCT: dict[str, str] = {
    "seq": "int",
    "prev_sha": "sha16",
    "kind": "kind",
    "decision_id": "decision_id",
    "ts": "ts",
    "dp": "token",
    "key": "key",
    "task_key": "token",
    "state_digest": "sha16",
    "questions_version": "qversion",
    "available": "bool",
    "authority": "authority",
    "escalated_reason": "token",
    "acted": "bool",
    "outcome": "outcome",
    "settled_by": "settled_by",
    "ref_seq": "int",
    "by": "change_by",
    "conclusion": "conclusion",
    "config_sha_after": "sha16",
    "mode": "mode",
    "model": "token",
    "transport": "token",
    "attempts": "int",
    "latency_ms": "number",
    "confidence": "number",
    "confidence_source": "confidence_source",
    "cost_tokens": "int",
    "override_by": "identity",
    "reason": "token",
}
_ARCHIVE_FREE: frozenset[str] = frozenset(
    {
        "answer",
        "actual_action",
        "evidence_ref",
        "override_reason",
        "change",
        "evidence_line",
        "policy",
        # ``note`` is caller prose (the writer only bounds it as text); it is
        # *not* the ``pending`` registration vocabulary.
        "note",
    }
)

_SIGNOFF_STRUCT: dict[str, str] = {
    "key": "key",
    "conclusion": "conclusion",
    "signed_via": "signed_via",
    "decide_fallback": "token",
    "counted_rows": "digits",
    "rows_sha256": "sha256",
    "ts": "ts",
    "path": "relpath",
}
_SIGNOFF_FREE: frozenset[str] = frozenset({"claim"})

_GATE_STRUCT: dict[str, str] = {
    "id": "gate_id",
    "kind": "token",
    "stage": "int",
    "key": "key",
    "status": "token",
    "created_at": "ts",
    "answered_at": "ts",
    "path": "relpath",
}
_GATE_FREE: frozenset[str] = frozenset({"question", "note", "answered_by"})

#: T10 injection contract: the free-text fields the output policy covers, per
#: carrier. A field not listed here is either validated schema, a structural
#: identifier or a counter - and never caller prose.
FREE_TEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "archive": tuple(sorted(_ARCHIVE_FREE)),
    "archive_rows": tuple(sorted(_ARCHIVE_FREE)),
    "signoff": tuple(sorted(_SIGNOFF_FREE)),
    "gates": tuple(sorted(_GATE_FREE)),
    "stage_detail": (
        "adopted.detail",
        "authority_change.detail",
        "executed.detail",
        "human_override.detail",
        "lifecycle.detail",
        "lifecycle.result",
        "suggested.detail",
    ),
    "calls": ("attempts[].error_detail",),
    "warnings": ("<message>",),
}


_STRUCTURAL_WITHHELD_BASIS = (
    "structural output strings and mapping keys matching the injected known-secret set "
    "were omitted (never rewritten to a placeholder id)"
)
_STRUCTURAL_WITHHELD_FLAG = "structural-secret-withheld"
#: A provenance list must not look empty after an omission: the entry is
#: replaced by this fixed, non-secret label (never by the value it described).
_BASIS_WITHHELD_MARK = "<basis withheld: known secret>"


def _scrub_output(
    value: object,
    redactor: decision_wire.SecretRedactor,
    *,
    withheld: list[str],
    label: str = "record",
    marker: str | None = None,
) -> object:
    """Omit every emitted string/mapping key the known-secret set recognises.

    The policy is *omit*, never substitute: a structural value must not become a
    ``<redacted>`` placeholder that a consumer could treat as an id, a key or a
    path. ``withheld`` collects label-only marks (``archive.model``,
    ``archive.<key>``) so the record can report what was dropped without
    repeating it. Capture copies whose ``text`` is omitted are marked
    ``text_omitted`` / ``byte_exact=False`` instead of still claiming byte
    fidelity.
    """
    if isinstance(value, str):
        if value and int(getattr(redactor.redact(value), "hits", 0)):
            if label not in withheld:
                withheld.append(label)
            return marker
        return value
    if isinstance(value, Mapping):
        result: dict[object, object] = {}
        text_omitted = False
        for name, item in value.items():
            if isinstance(name, str) and name:
                if int(getattr(redactor.redact(name), "hits", 0)):
                    mark = f"{label}.<key>"
                    if mark not in withheld:
                        withheld.append(mark)
                    if name == "text":
                        text_omitted = True
                    continue
                child = f"{label}.{name}"
            else:
                child = f"{label}[]"
            cleaned = _scrub_output(
                item,
                redactor,
                withheld=withheld,
                label=child,
                marker=_BASIS_WITHHELD_MARK if name == "basis" else None,
            )
            if name == "text" and item is not None and cleaned is None:
                text_omitted = True
            result[name] = cleaned
        if text_omitted and "text_omitted" in value:
            # A capture copy must not keep claiming the stored bytes are exact.
            result["text_omitted"] = True
            if "byte_exact" in value:
                result["byte_exact"] = False
        return result
    if isinstance(value, (list, tuple)):
        items: list[object] = []
        for item in value:
            cleaned = _scrub_output(
                item, redactor, withheld=withheld, label=f"{label}[]", marker=marker
            )
            if cleaned is None and item is not None:
                # an omitted entry is dropped from a list, never kept as a hole
                continue
            items.append(cleaned)
        return items
    return value


def _with_output_policy(record: "HistoryRecord") -> "HistoryRecord":
    """Count output-level omissions once, at build time (marks are per record).

    ``as_dict`` re-applies the same scan on every call (the payload is rebuilt
    from the raw fields), but the marks/flags must be stable and present on the
    record itself, so they are computed here from the widest payload.
    """
    if record.redactor is None:
        return record
    withheld: list[str] = []
    _scrub_output(record._payload(detail=True), record.redactor, withheld=withheld)
    if not withheld:
        return record
    marks = dataclasses.replace(
        record.redaction,
        structural_withheld=len(withheld),
        fields=record.redaction.fields + tuple(withheld),
        basis=record.redaction.basis + (_STRUCTURAL_WITHHELD_BASIS,),
    )
    flags = tuple(sorted(set(record.flags) | {_STRUCTURAL_WITHHELD_FLAG}))
    return dataclasses.replace(record, redaction=marks, flags=flags)


class _Sanitizer:
    """One record's free-text policy: redact, clip, scrub the cut, or withhold.

    Mirrors ``decision_wire``'s free-text policy (design §9) without importing
    its private helpers: with a redactor every string is redacted before it is
    clipped, a clip boundary never keeps a partial secret, mapping keys are
    caller text too, and colliding sanitized keys are dropped instead of
    overwriting one another. Without a redactor the text is unprovable, so it is
    omitted and counted - never emitted raw.
    """

    def __init__(
        self,
        redactor: decision_wire.SecretRedactor | None,
        *,
        limit: int = FREE_TEXT_LIMIT,
    ) -> None:
        self.redactor = redactor
        self.limit = limit
        self.substitutions = 0
        self.redacted = 0
        self.truncated = 0
        self.omitted = 0
        self.dropped = 0
        self.invalid = 0
        self._labels: list[str] = []
        self._seen: set[str] = set()

    @property
    def enabled(self) -> bool:
        return self.redactor is not None

    def _label(self, label: str) -> None:
        if label not in self._seen:
            self._seen.add(label)
            self._labels.append(label)

    def drop(self, label: str) -> None:
        """A field the schema does not name: not schema, not echoed."""
        self.dropped += 1
        self._label(label)

    def invalid_field(self, label: str) -> None:
        """A structural field failed validation: kept as ``None``, counted."""
        self.invalid += 1
        self._label(label)

    def _withhold(self, label: str) -> None:
        self.omitted += 1
        self._label(label)

    def text(self, label: str, value: object) -> str | None:
        """Redacted, clipped text, or ``None`` when it cannot be proven safe."""
        if value is None:
            return None
        if not isinstance(value, str):
            self._withhold(label)
            return None
        if not value:
            return ""
        if self.redactor is None:
            self._withhold(label)
            return None
        result = self.redactor.redact(value)
        text = result.text
        hits = int(getattr(result, "hits", 0))
        if hits:
            self.substitutions += hits
            self.redacted += 1
            self._label(label)
        data = text.encode("utf-8")
        if len(data) <= self.limit:
            return text
        clipped = data[: self.limit].decode("utf-8", errors="ignore")
        scrubbed, boundary = self.redactor.scrub_tail_prefix(clipped)
        if boundary:
            self.substitutions += 1
            self._label(label)
        self.truncated += 1
        self._label(label)
        kept = len(scrubbed.encode("utf-8"))
        return f"{scrubbed} [truncated: kept {kept} of {len(data)} bytes]"

    def payload(self, label: str, value: object) -> object:
        """Redact a nested free-text value (``answer`` / ``policy``)."""
        if value is None:
            return None
        if isinstance(value, bool) or isinstance(value, (int, float)):
            return value
        if self.redactor is None:
            self._withhold(label)
            return None
        if isinstance(value, str):
            return self.text(label, value)
        if isinstance(value, Mapping):
            order: list[str] = []
            entries: dict[str, list[object]] = {}
            for raw_key, item in value.items():
                if not isinstance(raw_key, str):
                    self._withhold(f"{label}.<key>")
                    continue
                if int(getattr(self.redactor.redact(raw_key), "hits", 0)):
                    # A credential used as a mapping key is still a credential:
                    # the entry is omitted, never emitted under a placeholder
                    # key that a consumer could take for a real one.
                    self._withhold(f"{label}.<key>")
                    continue
                clean = self.text(f"{label}.<key>", raw_key)
                if not clean:
                    continue
                if clean not in entries:
                    entries[clean] = []
                    order.append(clean)
                entries[clean].append(item)
            sanitized: dict[str, object] = {}
            for clean in order:
                items = entries[clean]
                if len(items) > 1:
                    # Never overwrite one entry with another (fabricated value).
                    self._withhold(f"{label}.{clean}")
                    continue
                sanitized[clean] = self.payload(f"{label}.{clean}", items[0])
            return sanitized
        if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
            return [self.payload(f"{label}[]", item) for item in value]
        self._withhold(label)
        return None

    def marks(self) -> RedactionMarks:
        basis: list[str] = []
        if self.redactor is None:
            basis.append("no redactor injected: unprovable free text omitted (fail-closed)")
        else:
            basis.append(
                "injected known-secret redactor (decision.credential_redactor) before clip"
            )
        if self.truncated:
            basis.append(f"free text clipped at {self.limit} bytes with boundary scrub")
        return RedactionMarks(
            enabled=self.redactor is not None,
            substitutions=self.substitutions,
            redacted_fields=self.redacted,
            truncated_fields=self.truncated,
            omitted_fields=self.omitted,
            dropped_fields=self.dropped,
            invalid_fields=self.invalid,
            fields=tuple(self._labels),
            basis=tuple(basis),
        )


def _sanitize_carrier(
    row: Mapping[str, object],
    struct: Mapping[str, str],
    free: frozenset[str],
    prefix: str,
    sanitizer: _Sanitizer,
) -> dict[str, object]:
    """Apply one carrier's closed schema and free-text policy to a raw row."""
    out: dict[str, object] = {}
    for name, value in row.items():
        if not isinstance(name, str):
            sanitizer.drop(f"{prefix}.<key>")
            continue
        if name in free:
            out[name] = sanitizer.payload(f"{prefix}.{name}", value)
            continue
        kind = struct.get(name)
        if kind is None:
            sanitizer.drop(f"{prefix}.{name}")
            continue
        if value is None:
            out[name] = None
            continue
        if _valid_field(kind, value):
            out[name] = value
        else:
            sanitizer.invalid_field(f"{prefix}.{name}")
            out[name] = None
    return out


def _struct_text(value: object, kind: str) -> str | None:
    """A structural string or ``None`` (never a half-valid identifier)."""
    return value if isinstance(value, str) and _valid_field(kind, value) else None


def _worst_capture_status(statuses: Sequence[str | None]) -> str | None:
    best: str | None = None
    for status in statuses:
        if _CAPTURE_RANK.get(status, 0) > _CAPTURE_RANK.get(best, 0):
            best = status
    return best


# ---------------------------------------------------------------------------
# Tolerant file reads (no writes, no repair)
# ---------------------------------------------------------------------------


@dataclass
class _Damaged:
    damaged: int = 0
    oversized: int = 0
    incomplete_tail: int = 0


def _read_archive_rows(path: pathlib.Path) -> tuple[list[tuple[int, dict[str, Any]]], _Damaged]:
    """Parse archive rows with physical line numbers; damaged lines counted."""
    damage = _Damaged()
    rows: list[tuple[int, dict[str, Any]]] = []
    try:
        data = path.read_bytes()
    except FileNotFoundError:
        return rows, damage
    except OSError:
        damage.damaged += 1
        return rows, damage
    for lineno, raw in enumerate(data.split(b"\n"), start=1):
        if not raw.strip():
            continue
        if len(raw) > README_LINE_CAP_BYTES:
            damage.oversized += 1
            continue
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            damage.damaged += 1
            continue
        try:
            parsed = json.loads(text)
        except ValueError:
            damage.damaged += 1
            continue
        if not isinstance(parsed, dict):
            damage.damaged += 1
            continue
        rows.append((lineno, parsed))
    return rows, damage


def _read_ledger(path: pathlib.Path) -> tuple[list[dict[str, Any]], _Damaged, int]:
    """Schema-v1 ledger read via ``decision_wire.read_events`` (counters kept)."""
    damage = _Damaged()
    result = decision_wire.read_events(path)
    damage.damaged = result.stats.bad_json + result.stats.bad_utf8
    damage.oversized = result.stats.oversized_line
    damage.incomplete_tail = result.stats.incomplete_tail
    return list(result.events), damage, result.stats.unknown_schema


# ---------------------------------------------------------------------------
# Record builders
# ---------------------------------------------------------------------------


@dataclass
class _Builder:
    scope: str
    identity: str
    kind_hint: str | None = None
    decision_id: str | None = None
    submission_id: str | None = None
    archive_base: dict[str, Any] | None = None
    archive_rows: list[dict[str, Any]] = field(default_factory=list)
    archive_override: list[dict[str, Any]] = field(default_factory=list)
    archive_authority: list[dict[str, Any]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    signoff: dict[str, Any] | None = None
    gates: list[dict[str, Any]] = field(default_factory=list)
    key: str | None = None
    dp: str | None = None
    task_key: str | None = None
    ts: str | None = None
    flags: set[str] = field(default_factory=set)


@dataclass
class _FoldedCalls:
    calls: list[dict[str, Any]] = field(default_factory=list)
    counts: CallCounts = field(default_factory=CallCounts)
    usage: UsageFact = field(default_factory=UsageFact)
    capture_status: str | None = None
    last_call_end: dict[str, Any] | None = None


def _usage_semantics(variants: Sequence[tuple[tuple[str, int], ...]]) -> str:
    """Name what the record-level counters are (never "a total")."""
    if not variants:
        return "none"
    if len(variants) == 1:
        return "single-recorded-attempt"
    return "last-recorded-attempt"


def _usage_basis(variants: Sequence[tuple[tuple[str, int], ...]]) -> tuple[str, ...]:
    """State the recorded basis of the counters; no value is summed or guessed."""
    if not variants:
        return ("no attempt-end usage row recorded",)
    basis: list[str] = ["counters are one attempt's recorded usage, never a sum"]
    if len(variants) > 1:
        basis.append(f"{len(variants)} attempts recorded usage; the last one is shown")
    if len(set(variants)) > 1:
        basis.append("recorded attempts disagree; per-attempt values stay in calls[].attempts[]")
    return tuple(basis)


def _fold_calls(
    events: Sequence[Mapping[str, Any]],
    sanitizer: _Sanitizer,
) -> _FoldedCalls:
    """Fold attempt/call rows into per-call detail plus separate counters."""
    order: list[str] = []
    calls: dict[str, dict[str, Any]] = {}
    for event in events:
        kind = event.get("kind")
        if kind not in ("attempt-start", "attempt-end", "call-end"):
            continue
        call_id = event.get("call_id")
        if not isinstance(call_id, str) or not call_id:
            continue
        if call_id not in calls:
            calls[call_id] = {
                "call_id": call_id,
                "call_end": None,
                "starts": {},
                "ends": {},
                "order": [],
            }
            order.append(call_id)
        entry = calls[call_id]
        index = event.get("attempt_index")
        if not isinstance(index, int) or isinstance(index, bool):
            index = 0
        if kind == "attempt-start":
            entry["starts"][index] = event
            entry["order"].append(index)
        elif kind == "attempt-end":
            entry["ends"][index] = event
            if index not in entry["order"]:
                entry["order"].append(index)
        else:
            entry["call_end"] = event

    logical = 0
    attempts = 0
    zero_call = 0
    unrecorded = 0
    last_end: dict[str, Any] | None = None
    detail_calls: list[dict[str, Any]] = []
    usage_counters: dict[str, int] = {}
    usage_recorded = False
    usage_variants: list[tuple[tuple[str, int], ...]] = []

    for call_id in order:
        entry = calls[call_id]
        indexes = sorted(set(entry["starts"]) | set(entry["ends"]))
        attempt_rows: list[dict[str, Any]] = []
        attempt_statuses: list[str | None] = []
        call_not_recorded: list[str] = []
        for index in indexes:
            start = entry["starts"].get(index)
            end = entry["ends"].get(index)
            status_raw = (end or {}).get("capture_status")
            status = status_raw if isinstance(status_raw, str) else None
            start_status_raw = (start or {}).get("capture_status")
            start_status = start_status_raw if isinstance(start_status_raw, str) else None
            # One attempt exists on two rows: a failed/partial request capture
            # must not be hidden by a clean response row.
            status = _worst_capture_status([item for item in (start_status, status) if item is not None])
            attempt_statuses.append(status)
            usage = end.get("usage") if end else None
            attempt_usage: dict[str, int] = {}
            if isinstance(usage, Mapping):
                usage_recorded = True
                for name, value in usage.items():
                    if isinstance(name, str) and isinstance(value, int) and not isinstance(value, bool):
                        attempt_usage[name] = value
                if attempt_usage:
                    # One attempt's counters, never merged with a sibling attempt:
                    # merging would attribute one number to a different request.
                    usage_counters = dict(attempt_usage)
                    usage_variants.append(tuple(sorted(attempt_usage.items())))
            not_recorded = [
                name
                for name, present in (
                    ("request", bool((start or {}).get("request"))),
                    ("response", bool((end or {}).get("response"))),
                    ("http_status", (end or {}).get("http_status") is not None),
                    ("latency_ms", (end or {}).get("latency_ms") is not None),
                    ("usage", usage is not None),
                )
                if not present
            ]
            attempt_rows.append(
                {
                    "attempt_index": index if index else None,
                    "method": (start or {}).get("method"),
                    "url_path": (start or {}).get("url_path"),
                    "model": (start or {}).get("model"),
                    "http_status": (end or {}).get("http_status"),
                    "latency_ms": (end or {}).get("latency_ms"),
                    "retry_after_s": (end or {}).get("retry_after_s"),
                    "error_class": (end or {}).get("error_class"),
                    "error_detail": sanitizer.text(
                        "calls.*.attempts[].error_detail", (end or {}).get("error_detail")
                    ),
                    "usage": dict(usage) if isinstance(usage, Mapping) else None,
                    "usage_source": (end or {}).get("usage_source"),
                    "capture_status": status,
                    "unfinished": end is None,
                    "start_not_recorded": start is None,
                    "request": (start or {}).get("request"),
                    "response": (end or {}).get("response"),
                    "not_recorded": not_recorded,
                }
            )
            if start is not None:
                attempts += 1

        call_end = entry["call_end"]
        if call_end is not None:
            logical += 1
            if call_end.get("zero_call") is True:
                zero_call += 1
            wire_attempts = call_end.get("wire_attempts")
            if not isinstance(wire_attempts, int) or isinstance(wire_attempts, bool):
                unrecorded += 1
                wire_attempts = None
            last_end = call_end
        else:
            wire_attempts = None
        if call_end is None:
            call_not_recorded.append("call-end")
        if wire_attempts is None and call_end is not None:
            call_not_recorded.append("wire_attempts")
        if call_end is not None and call_end.get("confidence") is None:
            call_not_recorded.append("confidence")
        if not attempt_rows:
            call_not_recorded.append("attempts")
        call_usage: dict[str, int] = {}
        for attempt in attempt_rows:
            usage_row = attempt.get("usage")
            if isinstance(usage_row, Mapping):
                call_usage = {
                    name: value
                    for name, value in usage_row.items()
                    if isinstance(name, str) and isinstance(value, int) and not isinstance(value, bool)
                }
        if not call_usage:
            call_not_recorded.append("usage")
        detail_calls.append(
            {
                "call_id": call_id,
                "logical_attempts": (call_end or {}).get("attempts"),
                "wire_attempts": wire_attempts,
                "zero_call": (call_end or {}).get("zero_call"),
                "available": (call_end or {}).get("available"),
                "reason": (call_end or {}).get("reason"),
                "answers_present": (call_end or {}).get("answers_present"),
                "confidence": (call_end or {}).get("confidence"),
                "confidence_source": (call_end or {}).get("confidence_source"),
                "transport": (call_end or {}).get("transport"),
                "model": (call_end or {}).get("model"),
                "answer_source": (call_end or {}).get("answer_source"),
                "latency_ms": (call_end or {}).get("latency_ms"),
                "usage": dict(sorted(call_usage.items())) if call_usage else None,
                "usage_semantics": "last-recorded-attempt" if call_usage else "none",
                "attempts": attempt_rows,
                "capture_status": _worst_capture_status(attempt_statuses) if attempt_statuses else None,
                "not_recorded": call_not_recorded,
            }
        )

    recorded = logical > 0 or bool(calls)
    counters = dict(sorted(usage_counters.items()))
    missing = tuple(
        name for name in sorted(decision_wire.USAGE_COUNTER_KEYS) if name not in counters
    )
    counts = CallCounts(
        recorded=recorded,
        logical_calls=logical if recorded else None,
        actual_http_attempts=attempts if recorded else None,
        zero_call=zero_call if recorded else None,
        unrecorded_wire_attempts=unrecorded,
        basis=(
            ("ledger call rows (logical=call-end, attempts=attempt-start)",)
            if recorded
            else ("no wire ledger rows for this record",)
        ),
    )
    usage = UsageFact(
        recorded=usage_recorded,
        counters=counters,
        missing=missing if usage_recorded else (),
        complete=usage_recorded and not missing,
        semantics=_usage_semantics(usage_variants),
        attempts_with_usage=len(usage_variants),
        conflicting=len(set(usage_variants)) > 1,
        basis=_usage_basis(usage_variants),
    )
    statuses = [call["capture_status"] for call in detail_calls]
    return _FoldedCalls(
        calls=detail_calls,
        counts=counts,
        usage=usage,
        capture_status=_worst_capture_status([s for s in statuses if isinstance(s, str)]),
        last_call_end=last_end,
    )


def _last_lifecycle(events: Sequence[Mapping[str, Any]], name: str) -> dict[str, Any] | None:
    found: dict[str, Any] | None = None
    for event in events:
        if event.get("kind") == "lifecycle" and event.get("lifecycle") == name:
            found = event
    return found


def _lifecycle_stage(event: Mapping[str, Any], sanitizer: _Sanitizer) -> StageFact:
    actor = event.get("actor")
    actor_kind = actor.get("kind") if isinstance(actor, Mapping) else None
    if actor_kind not in ACTOR_KINDS:
        actor_kind = "unknown"
    answer_source = event.get("answer_source")
    result = event.get("result")
    if event.get("lifecycle") == "settled":
        # A settled result is the outcome vocabulary, not caller prose: it must
        # survive redaction so ``status`` and the stage always agree.
        detail = _struct_text(result, "outcome")
        result_value = detail
    else:
        detail = sanitizer.text("stages.lifecycle.detail", result)
        result_value = sanitizer.text("stages.lifecycle.result", result)
    return StageFact(
        state="recorded",
        basis=("ledger.lifecycle",),
        ts=_struct_text(event.get("ts"), "ts"),
        detail=detail,
        event_id=_struct_text(event.get("event_id"), "token"),
        actor=actor_kind,
        answer_source=_struct_text(answer_source, "token"),
        target=_struct_text(event.get("target"), "decision_id"),
        supersedes=_struct_text(event.get("supersedes"), "decision_id"),
        result=result_value,
    )


_NOT_RECORDED = StageFact(state="not-recorded")


def _build_stages(
    builder: _Builder,
    folded_calls: _FoldedCalls,
    decision_end: Mapping[str, Any] | None,
    book_event: Mapping[str, Any] | None,
    sanitizer: _Sanitizer,
) -> dict[str, StageFact]:
    events = builder.events
    base = builder.archive_base
    stages: dict[str, StageFact] = {}

    # suggested: the model's recorded suggestion (or its explicit escalation).
    if base is not None:
        available = base.get("available")
        if available is True:
            stages["suggested"] = StageFact(
                state="recorded",
                basis=("archive.decide",),
                ts=base.get("ts") if isinstance(base.get("ts"), str) else None,
                detail=None,
                actor=None,
                result="available",
            )
        else:
            detail = base.get("escalated_reason") or base.get("reason")
            stages["suggested"] = StageFact(
                state="not-recorded",
                basis=("archive.decide.available=false",),
                ts=_struct_text(base.get("ts"), "ts"),
                detail=_struct_text(detail, "token")
                if isinstance(detail, str)
                else sanitizer.text("stages.suggested.detail", detail),
            )
    elif folded_calls.last_call_end is not None:
        call_end = folded_calls.last_call_end
        if call_end.get("available") is True:
            stages["suggested"] = StageFact(
                state="recorded",
                basis=("ledger.call-end",),
                ts=call_end.get("ts") if isinstance(call_end.get("ts"), str) else None,
            )
        else:
            reason = call_end.get("reason")
            stages["suggested"] = StageFact(
                state="not-recorded",
                basis=("ledger.call-end.available=false",),
                detail=_struct_text(reason, "token") if isinstance(reason, str) else None,
            )
    elif folded_calls.counts.actual_http_attempts:
        stages["suggested"] = StageFact(state="pending", basis=("ledger.attempt-start",))
    elif decision_end is not None and decision_end.get("status") not in ("disabled", "unavailable"):
        stages["suggested"] = StageFact(
            state="recorded",
            basis=("ledger.decision-end",),
            ts=decision_end.get("ts") if isinstance(decision_end.get("ts"), str) else None,
        )
    else:
        stages["suggested"] = _NOT_RECORDED

    # adopted / consumed / responded / steered / executed
    adopted = _last_lifecycle(events, "adopted")
    if adopted is not None:
        stages["adopted"] = _lifecycle_stage(adopted, sanitizer)
    elif base is not None and base.get("acted") is True:
        stages["adopted"] = StageFact(
            state="recorded",
            basis=("archive.decide.acted",),
            ts=_struct_text(base.get("ts"), "ts"),
            detail=sanitizer.text("stages.adopted.detail", base.get("actual_action")),
            result="acted",
        )
    else:
        stages["adopted"] = _NOT_RECORDED

    consumed = _last_lifecycle(events, "consumed")
    stages["consumed"] = (
        _lifecycle_stage(consumed, sanitizer) if consumed is not None else _NOT_RECORDED
    )

    responded = _last_lifecycle(events, "responded")
    stages["responded"] = (
        _lifecycle_stage(responded, sanitizer) if responded is not None else _NOT_RECORDED
    )

    steered = _last_lifecycle(events, "steered")
    stages["steered"] = (
        _lifecycle_stage(steered, sanitizer) if steered is not None else _NOT_RECORDED
    )

    executed = _last_lifecycle(events, "executed")
    if executed is not None:
        stages["executed"] = _lifecycle_stage(executed, sanitizer)
    elif base is not None and base.get("acted") is True and base.get("actual_action"):
        stages["executed"] = StageFact(
            state="recorded",
            basis=("archive.decide.actual_action",),
            ts=_struct_text(base.get("ts"), "ts"),
            detail=sanitizer.text("stages.executed.detail", base.get("actual_action")),
        )
    else:
        stages["executed"] = _NOT_RECORDED

    # human answer / override
    human_answer = _last_lifecycle(events, "human-answer")
    stages["human_answer"] = (
        _lifecycle_stage(human_answer, sanitizer) if human_answer is not None else _NOT_RECORDED
    )
    human_override = _last_lifecycle(events, "human-override")
    if human_override is not None:
        stages["human_override"] = _lifecycle_stage(human_override, sanitizer)
    elif builder.archive_override:
        last = builder.archive_override[-1]
        declared = last.get("override_by")
        stages["human_override"] = StageFact(
            state="recorded",
            basis=("archive.override",),
            ts=_struct_text(last.get("ts"), "ts"),
            detail=sanitizer.text("stages.human_override.detail", last.get("override_reason")),
            actor="human" if is_human_identity(declared) else "unknown",
            target=_struct_text(last.get("decision_id"), "decision_id"),
            result=sanitizer.text("stages.human_override.result", declared)
            if isinstance(declared, str)
            else None,
        )
    else:
        stages["human_override"] = _NOT_RECORDED

    # authority change (machine or human, never assumed)
    authority_event = _last_lifecycle(events, "authority-change")
    if authority_event is not None:
        stages["authority_change"] = _lifecycle_stage(authority_event, sanitizer)
    elif builder.archive_authority:
        last = builder.archive_authority[-1]
        by = last.get("by")
        basis: list[str] = ["archive.authority-change (dp-level)"]
        by_text = _struct_text(by, "change_by")
        if by_text is not None:
            basis.append(f"by={by_text}")
        stages["authority_change"] = StageFact(
            state="recorded",
            basis=tuple(basis),
            ts=_struct_text(last.get("ts"), "ts"),
            detail=sanitizer.text("stages.authority_change.detail", last.get("change")),
            event_id=None,
            actor="human" if is_human_identity(by) else "system",
            result=_struct_text(last.get("conclusion"), "conclusion"),
        )
    else:
        stages["authority_change"] = _NOT_RECORDED

    # sign-off (machine lines of sign-final.md, or a lifecycle signoff event)
    signoff_event = _last_lifecycle(events, "signoff")
    if signoff_event is not None:
        stages["signoff"] = _lifecycle_stage(signoff_event, sanitizer)
    elif builder.signoff is not None:
        stages["signoff"] = StageFact(
            state="recorded",
            basis=("signoff.machine-lines",),
            ts=_struct_text(builder.signoff.get("ts"), "ts"),
            detail=_struct_text(builder.signoff.get("signed_via"), "signed_via"),
            result=_struct_text(builder.signoff.get("conclusion"), "conclusion"),
        )
    else:
        stages["signoff"] = _NOT_RECORDED

    # settled: recorded outcome, explicit pending, or not recorded
    settles = [row for row in builder.archive_rows if row.get("kind") == "settle"]
    settled_event = _last_lifecycle(events, "settled")
    if settles:
        last = settles[-1]
        settled_by = last.get("settled_by")
        stages["settled"] = StageFact(
            state="recorded",
            basis=("archive.settle",),
            ts=_struct_text(last.get("ts"), "ts"),
            detail=_struct_text(last.get("outcome"), "outcome"),
            actor="human" if is_human_identity(settled_by) or settled_by == "human" else "system",
            result=_struct_text(last.get("outcome"), "outcome"),
        )
    elif settled_event is not None:
        stages["settled"] = _lifecycle_stage(settled_event, sanitizer)
    elif base is not None:
        stages["settled"] = StageFact(state="pending", basis=("archive.decide.outcome=pending",))
    else:
        stages["settled"] = _NOT_RECORDED

    # book snapshot
    if book_event is not None:
        stages["book"] = StageFact(
            state="recorded",
            basis=("ledger.book-snapshot",),
            ts=_struct_text(book_event.get("ts"), "ts"),
            detail=_struct_text(book_event.get("book_ref"), "token")
            if isinstance(book_event.get("book_ref"), str)
            else None,
            event_id=_struct_text(book_event.get("event_id"), "token"),
            result=_struct_text(book_event.get("book_version"), "token")
            if isinstance(book_event.get("book_version"), str)
            else None,
        )
    else:
        stages["book"] = _NOT_RECORDED
    return stages


def _claims(
    builder: _Builder,
    folded_calls: _FoldedCalls,
    stages: Mapping[str, StageFact],
) -> tuple[Claim, Claim, Claim, Claim, Claim]:
    """Build ``(source, actor, answer_source, transport, model)`` independently."""
    base = builder.archive_base
    events = builder.events

    human_basis: list[str] = []
    if stages["human_answer"].state == "recorded":
        human_basis.append("lifecycle:human-answer")
    if stages["human_override"].state == "recorded":
        human_basis.append(
            "lifecycle:human-override"
            if _last_lifecycle(events, "human-override") is not None
            else "archive.override"
        )
    signed_via = None
    if builder.signoff is not None:
        raw = builder.signoff.get("signed_via")
        signed_via = raw if isinstance(raw, str) else None
        if signed_via in ("cli", "tui"):
            human_basis.append(f"signoff:signed_via={signed_via} (declared)")

    model_basis: list[str] = []
    if base is not None and base.get("available") is True:
        # The engine echo only proves model output when an answer was recorded.
        # ``available=false`` rows carry ``answer=None`` (decide_archive:425), so
        # their transport/model fields are the attempted engine, not a model
        # answer - claiming "model" there would fabricate provenance.
        parts = [
            f"{name}={_struct_text(base[name], 'token')}"
            for name in ("transport", "model", "confidence_source")
            if _struct_text(base.get(name), "token")
        ]
        if parts:
            model_basis.append("archive.decide:" + ",".join(parts))
    if folded_calls.last_call_end is not None and folded_calls.last_call_end.get("available") is True:
        parts = [
            f"{name}={_struct_text(folded_calls.last_call_end[name], 'token')}"
            for name in ("transport", "model")
            if _struct_text(folded_calls.last_call_end.get(name), "token")
        ]
        if parts:
            model_basis.append("ledger.call-end:" + ",".join(parts))
    for event in events:
        if event.get("kind") != "lifecycle":
            continue
        source = event.get("answer_source")
        if source in ("api", "model-self-report"):
            model_basis.append(f"lifecycle.answer_source={source}")

    system_basis: list[str] = []
    settles = [row for row in builder.archive_rows if row.get("kind") == "settle"]
    if settles and settles[-1].get("settled_by") == "pm-auto":
        system_basis.append("archive.settle.settled_by=pm-auto")
    for row in builder.archive_authority:
        by = row.get("by")
        if isinstance(by, str) and (by.startswith("signoff:") or by == "refresh"):
            system_basis.append(f"archive.authority-change.by={by}")
    if signed_via in ("auto-decide", "auto-llm"):
        system_basis.append(f"signoff:signed_via={signed_via}")
    for event in events:
        actor = event.get("actor")
        kind = actor.get("kind") if isinstance(actor, Mapping) else None
        if kind == "system":
            system_basis.append("ledger.actor=system")

    if human_basis:
        source = Claim("human", tuple(human_basis))
    elif model_basis:
        source = Claim("model", tuple(model_basis))
    elif system_basis:
        source = Claim("system", tuple(system_basis))
    else:
        source = Claim("unknown", _unknown_basis(builder, folded_calls))

    # actor: who initiated - only a recorded actor.kind may answer this.
    actor_claim = Claim(None, ())
    for event in events:
        actor = event.get("actor")
        if not isinstance(actor, Mapping):
            continue
        kind = actor.get("kind")
        kind = kind if kind in ACTOR_KINDS else "unknown"
        actor_claim = Claim(kind, (f"ledger.actor={kind}",))
    if builder.signoff is not None and is_human_identity(builder.signoff.get("answered_by")):
        actor_claim = Claim("human", ("signoff.answered_by (declared)",))
    # answer_source: the backend branch that produced the answer, kept apart.
    answer_source = Claim(None, ())
    last_call_end = folded_calls.last_call_end
    if last_call_end is not None and isinstance(last_call_end.get("answer_source"), str):
        value = last_call_end["answer_source"]
        answer_source = Claim(value, ("ledger.call-end.answer_source",))
    else:
        for event in events:
            if event.get("kind") == "lifecycle" and isinstance(event.get("answer_source"), str):
                value = event["answer_source"]
                answer_source = Claim(value, ("ledger.lifecycle.answer_source",))
    if answer_source.value is None and base is not None:
        answer_source = Claim(None, ("archive has no answer_source field",))

    transport = Claim(None, ())
    model = Claim(None, ())
    if base is not None:
        base_transport = _struct_text(base.get("transport"), "token")
        base_model = _struct_text(base.get("model"), "token")
        if base_transport is not None:
            transport = Claim(base_transport, ("archive.decide.transport",))
        if base_model is not None:
            model = Claim(base_model, ("archive.decide.model",))
    elif last_call_end is not None:
        call_transport = _struct_text(last_call_end.get("transport"), "token")
        call_model = _struct_text(last_call_end.get("model"), "token")
        if call_transport is not None:
            transport = Claim(call_transport, ("ledger.call-end.transport",))
        if call_model is not None:
            model = Claim(call_model, ("ledger.call-end.model",))
    return source, actor_claim, answer_source, transport, model


def _unknown_basis(builder: _Builder, folded_calls: _FoldedCalls) -> tuple[str, ...]:
    """Why no source could be claimed - including the explicit no-answer case."""
    basis: list[str] = []
    base = builder.archive_base
    if base is not None and base.get("available") is not True:
        basis.append("archive.decide.available=false: no answer was recorded")
        escalated = _struct_text(base.get("escalated_reason"), "token")
        if escalated is not None:
            basis.append(f"escalated_reason={escalated}")
        if base.get("authority") == "human":
            basis.append("authority=human is an escalation marker, not a human answer")
    if folded_calls.last_call_end is not None and folded_calls.last_call_end.get("available") is not True:
        basis.append("ledger.call-end.available=false: no answer was recorded")
    if basis:
        return tuple(basis)
    if builder.signoff is not None or builder.gates or builder.archive_rows or builder.archive_authority:
        return ("recorded, but no answer/actor provenance",)
    return ("recorded without answer/actor provenance",)


def _record_status(builder: _Builder) -> str:
    settles = [row for row in builder.archive_rows if row.get("kind") == "settle"]
    if settles:
        outcome = settles[-1].get("outcome")
        return outcome if outcome in STATUSES else "unknown"
    if builder.archive_base is not None:
        return "pending"
    # Repeated settled events: the *last* one owns the status, exactly like the
    # ``settled`` stage - otherwise status and stage describe different events.
    settled_event = _last_lifecycle(builder.events, "settled")
    if settled_event is not None:
        result = settled_event.get("result")
        return result if result in STATUSES else "unknown"
    return "unknown"


def _record_ts(builder: _Builder) -> str | None:
    stamps: list[str] = []
    if builder.archive_base is not None and isinstance(builder.archive_base.get("ts"), str):
        stamps.append(builder.archive_base["ts"])
    for row in builder.archive_rows:
        if isinstance(row.get("ts"), str):
            stamps.append(row["ts"])
    for event in builder.events:
        if isinstance(event.get("ts"), str):
            stamps.append(event["ts"])
    if builder.signoff is not None and isinstance(builder.signoff.get("ts"), str):
        stamps.append(builder.signoff["ts"])
    for gate in builder.gates:
        if isinstance(gate.get("created_at"), str):
            stamps.append(gate["created_at"])
    for row in builder.archive_authority:
        if isinstance(row.get("ts"), str):
            stamps.append(row["ts"])
    return min(stamps) if stamps else None


def _finalize(
    builder: _Builder,
    project_id: str,
    *,
    redact: decision_wire.SecretRedactor | None,
) -> HistoryRecord:
    decision_end = None
    book_event = None
    for event in builder.events:
        if event.get("kind") == "decision-end":
            decision_end = event
        elif event.get("kind") == "book-snapshot":
            book_event = event
    sanitizer = _Sanitizer(redact)
    folded = _fold_calls(builder.events, sanitizer)
    stages = _build_stages(builder, folded, decision_end, book_event, sanitizer)
    source, actor, answer_source, transport, model = _claims(builder, folded, stages)

    archive = (
        _sanitize_carrier(
            builder.archive_base, _ARCHIVE_STRUCT, _ARCHIVE_FREE, "archive", sanitizer
        )
        if builder.archive_base is not None
        else None
    )
    archive_rows = tuple(
        _sanitize_carrier(row, _ARCHIVE_STRUCT, _ARCHIVE_FREE, "archive_rows[]", sanitizer)
        for row in builder.archive_rows
    )
    signoff = (
        _sanitize_carrier(builder.signoff, _SIGNOFF_STRUCT, _SIGNOFF_FREE, "signoff", sanitizer)
        if builder.signoff is not None
        else None
    )
    gates_out = tuple(
        _sanitize_carrier(gate, _GATE_STRUCT, _GATE_FREE, "gates[]", sanitizer)
        for gate in builder.gates
    )

    if builder.kind_hint is not None:
        record_kind = builder.kind_hint
    elif builder.archive_base is not None:
        record_kind = "decision"
    elif builder.submission_id is not None:
        record_kind = "submission"
    else:
        record_kind = "ledger"

    marks = sanitizer.marks()
    flags: set[str] = set(builder.flags)
    if builder.archive_base is not None and builder.archive_base.get("authority") == "human":
        flags.add("authority-human-not-action")
    if folded.usage.recorded and not folded.usage.complete:
        flags.add("metadata-keys-unrecorded")
    if folded.usage.semantics == "last-recorded-attempt":
        flags.add("usage-last-attempt-only")
    if folded.usage.conflicting:
        flags.add("usage-attempts-disagree")
    if any(
        isinstance(call.get("capture_status"), str) and call["capture_status"] != "ok"
        for call in folded.calls
    ):
        flags.add("capture-incomplete")
    if marks.redacted_fields:
        flags.add("free-text-redacted")
    if marks.truncated_fields:
        flags.add("free-text-truncated")
    if marks.omitted_fields:
        flags.add("free-text-omitted")
    if marks.dropped_fields:
        flags.add("schema-fields-dropped")
    if marks.invalid_fields:
        flags.add("structural-fields-invalid")

    missing = tuple(
        sorted(
            name
            for name, fact in stages.items()
            if fact.state == "not-recorded" and name != "steered"
        )
    )
    decision_id = builder.decision_id
    if decision_id is None and builder.archive_base is not None:
        raw = builder.archive_base.get("decision_id")
        decision_id = raw if isinstance(raw, str) else None
    if not _valid_decision_id(decision_id):
        decision_id = None
    dp = _struct_text(builder.dp, "token")
    key = builder.key if valid_key(builder.key) else None
    task_key = _struct_text(builder.task_key, "token")
    if dp is None and isinstance(decision_id, str) and ":" in decision_id:
        # ``decision_id`` is defined as ``<dp>:<trigger>`` (decide_archive), so
        # the dp prefix is schema, not a guess about which dp this is.
        dp = decision_id.split(":", 1)[0]
    if builder.archive_base is not None:
        dp = dp or _struct_text(builder.archive_base.get("dp"), "token")
        base_key = builder.archive_base.get("key")
        key = key or (base_key if valid_key(base_key) else None)
        task_key = task_key or _struct_text(builder.archive_base.get("task_key"), "token")

    identity = builder.identity
    record = HistoryRecord(
        opaque_id=opaque_id_for(project_id, builder.scope, identity),
        identity=identity,
        record_kind=record_kind,
        scope=builder.scope,
        project_id=project_id,
        decision_id=decision_id,
        dp=dp,
        key=key,
        task_key=task_key,
        submission_id=builder.submission_id,
        ts=_record_ts(builder),
        source=source,
        actor=actor,
        answer_source=answer_source,
        transport=transport,
        model=model,
        status=_record_status(builder),
        stages=stages,
        call_counts=folded.counts,
        usage=folded.usage,
        capture_status=folded.capture_status,
        calls=tuple(folded.calls),
        archive=archive,
        archive_rows=archive_rows,
        signoff=signoff,
        gates=gates_out,
        flags=tuple(sorted(flags)),
        missing=missing,
        redaction=marks,
        redactor=redact,
    )
    return _with_output_policy(record)


# ---------------------------------------------------------------------------
# Human carriers
# ---------------------------------------------------------------------------


def _real_root(root: pathlib.Path) -> pathlib.Path | None:
    """The resolved (realpath) root, or ``None`` when it cannot be resolved."""
    try:
        return root.resolve()
    except OSError:
        return None


def _inside(root_real: pathlib.Path | None, path: pathlib.Path) -> bool:
    """True only when ``path``'s real location stays inside ``root_real``.

    ``Path.resolve`` follows symlinks and junctions, so a sign-off/gate/ledger
    file replaced by a link to an out-of-root target is refused *before* any
    read. ``relative_to`` is wrapped: a mismatch is a refusal, never a crash.
    """
    if root_real is None:
        return False
    try:
        candidate = path.resolve()
    except OSError:
        return False
    try:
        candidate.relative_to(root_real)
    except ValueError:
        return False
    return True


def _rel_label(root_real: pathlib.Path | None, path: pathlib.Path) -> str | None:
    """Root-relative POSIX label of a guarded path (never an absolute path)."""
    if root_real is None:
        return None
    try:
        return path.resolve().relative_to(root_real).as_posix()
    except (OSError, ValueError):
        return None


def _read_signoff(
    control_root: pathlib.Path,
    key: str,
    *,
    root_real: pathlib.Path | None,
    blocked: list[str],
) -> tuple[dict[str, Any] | None, list[str]]:
    """Parsed machine lines of ``sign-final.md``; ``key:`` mismatches are refused.

    The key is validated as a directory *name* first and the resolved path must
    stay inside the control root: an out-of-root symlink/junction is refused
    before the read and counted in ``blocked`` (AC-005/VC-018).
    """
    warnings: list[str] = []
    if not valid_key(key):
        blocked.append("key")
        return None, [f"signoff skipped: key {key!r} is not a directory name"]
    path = decide_signoff.signoff_path(control_root, key)
    if not _inside(root_real, path):
        blocked.append("signoff")
        return None, [
            f"signoff for key {key} refused before read: resolved path leaves the control root"
        ]
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, warnings
    except OSError as exc:
        warnings.append(f"signoff unreadable for key {key}: {type(exc).__name__}")
        return None, warnings
    lines = decide_signoff.parse_signoff(text)
    declared = lines.get("key")
    if declared is not None and declared != key:
        warnings.append(
            f"signoff ignored: {path.name} in key {key} declares key {declared!r}"
        )
        return None, warnings
    conclusion = lines.get("conclusion")
    if conclusion is not None and conclusion not in decide_signoff.CONCLUSIONS:
        warnings.append(f"signoff for key {key} has unknown conclusion {conclusion!r}")
    signed_via = lines.get("signed_via")
    if signed_via is not None and signed_via not in decide_signoff.SIGNED_VIA_VALUES:
        warnings.append(f"signoff for key {key} has unknown signed_via {signed_via!r}")
    parsed: dict[str, Any] = {
        "key": key,
        "conclusion": conclusion,
        "signed_via": signed_via,
        "decide_fallback": lines.get("decide_fallback"),
        "counted_rows": lines.get("counted_rows"),
        "rows_sha256": lines.get("rows_sha256"),
        "ts": lines.get("ts"),
        "claim": lines.get("claim"),
        "path": _rel_label(root_real, path),
    }
    return parsed, warnings


def _iter_signoff_keys(
    control_root: pathlib.Path,
    *,
    root_real: pathlib.Path | None = None,
    blocked: list[str] | None = None,
) -> list[str]:
    """Keys carrying ``evidence/review/sign-final.md`` (scan is read-only)."""
    blocked = blocked if blocked is not None else []
    docs = control_root / ".agenticdoc"
    if root_real is None:
        root_real = _real_root(control_root)
    if not docs.is_dir() or not _inside(root_real, docs):
        return []
    found: list[str] = []
    try:
        entries = sorted(docs.iterdir())
    except OSError:
        return []
    for entry in entries:
        if not entry.is_dir() or entry.name.startswith(("_", ".")):
            continue
        if not valid_key(entry.name):
            blocked.append("key")
            continue
        candidate = entry / "evidence" / "review" / "sign-final.md"
        if not _inside(root_real, candidate):
            blocked.append("signoff")
            continue
        if candidate.is_file():
            found.append(entry.name)
    return found


def _read_gates(
    control_root: pathlib.Path,
    *,
    stats: dict[str, int],
    warn: Callable[[str, str], None],
) -> dict[str, list[dict[str, Any]]]:
    """Key -> gate frontmatter, read through ``autopilot.gates.parse``.

    A gate without a key is *not* silently dropped: it is counted
    (``gates_keyless``) and warned about, because stage-level gates belong to the
    whole history but their attribution is unknown - the reader never guesses a
    key. Out-of-root gate files are refused before the read.
    """
    by_key: dict[str, list[dict[str, Any]]] = {}
    directory = control_root / ".agenticdoc" / "_autopilot" / "gates"
    root_real = _real_root(control_root)
    if directory.exists() and not _inside(root_real, directory):
        stats["blocked_reads"] += 1
        warn("gate-root-outside", "gate queue refused before read: resolved path leaves the control root")
        return by_key
    try:
        entries = gates.queue_entries(directory)
    except gates.GateQueueUnreadable as exc:
        stats["gates_unreadable"] += 1
        warn("gate-queue-unreadable", f"gate queue unreadable: {type(exc).__name__}")
        return by_key
    if entries is None:
        return by_key
    for entry in entries:
        match = gates.GATE_FILE_RE.match(entry.name)
        if match is None or not entry.is_file():
            continue
        if not _inside(root_real, entry):
            stats["blocked_reads"] += 1
            warn("gate-outside-root", f"gate {entry.name} refused before read: resolved path leaves the control root")
            continue
        try:
            gate = gates.parse(entry)
        except (gates.GateFormatError, OSError) as exc:
            stats["gates_unreadable"] += 1
            warn("gate-unreadable", f"gate ignored: {entry.name}: {type(exc).__name__}")
            continue
        stats["gates_recorded"] += 1
        if gate.key is None:
            stats["gates_keyless"] += 1
            warn(
                "gate-keyless",
                f"gate {gate.id} has no key: attribution unknown, not folded into a key record",
            )
            continue
        if not valid_key(gate.key):
            stats["invalid_keys"] += 1
            warn("gate-key-invalid", f"gate {gate.id} key {gate.key!r} is not a directory name")
            continue
        by_key.setdefault(gate.key, []).append(
            {
                "id": gate.id,
                "kind": gate.kind,
                "stage": gate.stage,
                "key": gate.key,
                "status": gate.status,
                "question": gate.question,
                "created_at": gate.created_at,
                "answered_at": gate.answered_at,
                "answered_by": gate.answered_by,
                "note": gate.note,
                "path": _rel_label(root_real, entry),
            }
        )
    return by_key


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def _add_ledger_row(
    builder: _Builder,
    event: Mapping[str, Any],
) -> None:
    builder.events.append(dict(event))
    if builder.dp is None and isinstance(event.get("dp"), str):
        builder.dp = event["dp"]
    if builder.key is None and isinstance(event.get("key"), str):
        builder.key = event["key"]
    if builder.task_key is None and isinstance(event.get("task_key"), str):
        builder.task_key = event["task_key"]


def load_history(
    project_dir: pathlib.Path | str,
    *,
    test_roots: Sequence[pathlib.Path | str] = (),
    require_control: bool = True,
    redact: decision_wire.SecretRedactor | None = None,
) -> HistorySnapshot:
    """Fold one project's recorded history (read-only, no writes anywhere).

    ``redact`` is the injected known-secret set (``decision.credential_redactor``
    in production; any ``decision_wire.SecretRedactor`` in tests). It governs
    every free-text value in the returned payload and the returned warnings.
    Passing ``None`` is legal and fail-closed: unprovable free text is withheld
    and counted (``redaction.enabled=false``), never echoed raw.
    """
    control_root, _source = mw_common.resolve_control_root(
        project_dir, require_control=require_control
    )
    control_root = pathlib.Path(control_root)
    root_real = _real_root(control_root)
    project_id = decision_wire.project_id_for(control_root)
    warning_sanitizer = _Sanitizer(redact)
    warnings: list[str] = []

    def sanitize_warning(code: str, message: str) -> str:
        rendered = warning_sanitizer.text(f"warning.{code}", message)
        if rendered is None:
            return f"{code}: details withheld (no redactor injected)"
        return f"{code}: {rendered}" if rendered else code

    def warn(code: str, message: str) -> None:
        if len(warnings) < _MAX_WARNINGS:
            warnings.append(sanitize_warning(code, message))

    stats = {
        "archive_rows": 0,
        "archive_damaged": 0,
        "chain_breaks": 0,
        "seq_breaks": 0,
        "wire_events": 0,
        "lifecycle_events": 0,
        "wire_damaged": 0,
        "lifecycle_damaged": 0,
        "unknown_schema": 0,
        "unknown_kind": 0,
        "unknown_scope": 0,
        "unknown_lifecycle": 0,
        "invalid_ids": 0,
        "foreign_rows": 0,
        "unlinked_call_ids": 0,
        "unlinked_events": 0,
        "misplaced_test_rows": 0,
        "gates_recorded": 0,
        "gates_keyless": 0,
        "gates_unreadable": 0,
        "invalid_keys": 0,
        "blocked_reads": 0,
    }

    builders: dict[tuple[str, str], _Builder] = {}
    unlinked_calls: set[str] = set()

    def builder_for(scope: str, identity: str) -> _Builder:
        key = (scope, identity)
        if key not in builders:
            builders[key] = _Builder(scope=scope, identity=identity)
        return builders[key]

    def guard(path: pathlib.Path, label: str) -> bool:
        """Refuse a carrier read whose resolved target leaves its root."""
        if _inside(root_real, path):
            return True
        stats["blocked_reads"] += 1
        warn(
            "read-outside-root",
            f"{label} refused before read: resolved path leaves the control root",
        )
        return False

    # -- archive -----------------------------------------------------------
    archive_path = control_root / ".agenticdoc" / "_autopilot" / "decisions.jsonl"
    archive_rows, archive_damage = _read_archive_rows(archive_path) if guard(
        archive_path, "decision archive"
    ) else ([], _Damaged())
    stats["archive_rows"] = len(archive_rows)
    stats["archive_damaged"] = archive_damage.damaged + archive_damage.oversized
    if archive_damage.incomplete_tail:
        warn("archive-incomplete-tail", "archive has an unterminated final line (counted, not repaired)")
    folded = decide_archive.fold([row for _lineno, row in archive_rows])
    stats["chain_breaks"] = folded.stats.chain_breaks
    stats["seq_breaks"] = folded.stats.seq_breaks
    if folded.stats.skipped_unparsable:
        stats["archive_damaged"] += folded.stats.skipped_unparsable
    if folded.stats.skipped_non_dict:
        stats["archive_damaged"] += folded.stats.skipped_non_dict

    by_decision: dict[str, list[dict[str, Any]]] = {}
    by_authority: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for _lineno, row in archive_rows:
        decision_id = row.get("decision_id")
        if not _valid_decision_id(decision_id):
            stats["invalid_ids"] += 1
            continue
        if row.get("kind") not in ARCHIVE_KINDS:
            stats["unknown_kind"] += 1
            warn("archive-kind", f"archive row kind {row.get('kind')!r} is not a known kind")
            continue
        if row.get("kind") == "authority-change":
            # ``authority-change`` is a per-dp fact (design §4.3), not a decision:
            # it is folded into a dp-level record and joined by (dp, key), never
            # by a guessed decision id.
            dp = row.get("dp")
            key = row.get("key")
            if not isinstance(dp, str) or not dp or not isinstance(key, str):
                stats["invalid_ids"] += 1
                continue
            by_authority.setdefault((dp, key), []).append(row)
            continue
        by_decision.setdefault(decision_id, []).append(row)

    for decision_id, rows in by_decision.items():
        rows.sort(key=lambda item: item.get("seq") if isinstance(item.get("seq"), int) else 0)
        base = next((row for row in rows if row.get("kind") == "decide"), None)
        builder = builder_for("production", "decision|" + decision_id)
        builder.decision_id = decision_id
        builder.archive_base = dict(base) if base is not None else None
        builder.archive_rows = [dict(row) for row in rows if row.get("kind") != "decide"]
        builder.archive_override = [dict(row) for row in rows if row.get("kind") == "override"]
        builder.archive_authority = [
            dict(row) for row in rows if row.get("kind") == "authority-change"
        ]
        source = base if base is not None else rows[0]
        builder.dp = source.get("dp") if isinstance(source.get("dp"), str) else None
        builder.key = source.get("key") if isinstance(source.get("key"), str) else None
        builder.task_key = (
            source.get("task_key") if isinstance(source.get("task_key"), str) else None
        )

    for (dp, key), rows in by_authority.items():
        rows.sort(key=lambda item: item.get("seq") if isinstance(item.get("seq"), int) else 0)
        builder = builder_for("production", f"authority|{dp}|{key}")
        builder.kind_hint = "authority"
        builder.dp = dp
        builder.key = key
        builder.archive_authority = [dict(row) for row in rows]

    # Authority changes are dp-level: every decision of that (key, dp) sees them.
    for builder in builders.values():
        if builder.kind_hint == "authority" or builder.scope != "production":
            continue
        if builder.dp is None:
            continue
        rows = by_authority.get((builder.dp, builder.key or ""), ())
        if rows:
            builder.archive_authority = [dict(row) for row in rows]

    # A record's ``key`` is joined against carrier paths, so it must be a plain
    # directory name before it is used for anything (P1-2): an invalid key is
    # counted, warned about and never turned into a path.
    for builder in builders.values():
        if builder.scope != "production" or not builder.key:
            # An absent/empty key is "not recorded", not a traversal attempt:
            # it simply has no carrier to join.
            continue
        if not valid_key(builder.key):
            stats["invalid_keys"] += 1
            warn(
                "record-key-invalid",
                f"record key {builder.key!r} is not a directory name; no sign-off/gate join",
            )
            builder.key = None

    # -- ledgers -----------------------------------------------------------
    def read_ledger_into(
        path: pathlib.Path,
        scope: str,
        label: str,
        misplaced_scope: str | None,
        *,
        root_real_for_guard: pathlib.Path | None = root_real,
        guard_label: str | None = None,
    ) -> None:
        if not _inside(root_real_for_guard, path):
            stats["blocked_reads"] += 1
            warn(
                "read-outside-root",
                f"{guard_label or label + ' ledger'} refused before read: "
                "resolved path leaves its root",
            )
            return
        events, damage, unknown_schema = _read_ledger(path)
        stats[f"{label}_events"] += len(events)
        stats[f"{label}_damaged"] += damage.damaged + damage.oversized
        stats["unknown_schema"] += unknown_schema
        if damage.incomplete_tail:
            warn(
                "ledger-incomplete-tail",
                f"{label} ledger has an unterminated final line (counted, not repaired)",
            )
        for event in events:
            kind = event.get("kind")
            if kind not in decision_wire.EVENT_KINDS:
                stats["unknown_kind"] += 1
                warn("ledger-kind", f"{label} row kind {kind!r} is not a schema-v1 kind")
                continue
            event_project = event.get("project_id")
            if event_project != project_id:
                stats["foreign_rows"] += 1
                continue
            event_scope = event.get("scope")
            if event_scope not in SCOPE_KINDS:
                stats["unknown_scope"] += 1
                warn("ledger-scope", f"{label} row has unknown scope {event_scope!r}")
                continue
            if misplaced_scope is not None and event_scope != misplaced_scope:
                # A test-scope row inside the production sink: never folded into
                # production, never counted as a test record either.
                stats["misplaced_test_rows"] += 1
                warn("ledger-misplaced", f"{label} row has scope {event_scope!r} in the production sink")
                continue
            decision_id = event.get("decision_id")
            if decision_id is not None and not _valid_decision_id(decision_id):
                stats["invalid_ids"] += 1
                warn("ledger-invalid-id", f"{label} row has an invalid decision_id (a value, not a path)")
                continue
            if event.get("kind") == "lifecycle" and event.get("lifecycle") not in LIFECYCLE_VOCAB:
                stats["unknown_lifecycle"] += 1
                warn("ledger-lifecycle", f"lifecycle word {event.get('lifecycle')!r} is not in the vocabulary")
                continue
            dp = event.get("dp")
            if isinstance(dp, str) and isinstance(decision_id, str) and not decision_id.startswith(dp + ":"):
                stats["invalid_ids"] += 1
                warn("ledger-id-dp", f"{label} row decision_id does not belong to dp {dp!r}")
                continue
            submission_id = event.get("submission_id")
            call_id = event.get("call_id")
            if isinstance(decision_id, str) and decision_id:
                identity = "decision|" + decision_id
                builder = builder_for(event_scope, identity)
                builder.decision_id = builder.decision_id or decision_id
            elif _valid_identity_text(submission_id):
                identity = "submission|" + str(submission_id)
                builder = builder_for(event_scope, identity)
                builder.submission_id = str(submission_id)
            elif _valid_identity_text(call_id):
                unlinked_calls.add(str(call_id))
                stats["unlinked_events"] += 1
                continue
            else:
                stats["unlinked_events"] += 1
                continue
            _add_ledger_row(builder, event)

    read_ledger_into(
        decision_wire.production_wire_sink(control_root), "production", "wire", "production"
    )
    read_ledger_into(
        decision_wire.production_lifecycle_sink(control_root),
        "production",
        "lifecycle",
        "production",
    )
    for raw_root in test_roots:
        test_root = pathlib.Path(raw_root)
        test_root_real = _real_root(test_root)
        read_ledger_into(
            test_root / TEST_WIRE_NAME,
            "test",
            "wire",
            "test",
            root_real_for_guard=test_root_real,
            guard_label="test wire ledger",
        )
        read_ledger_into(
            test_root / TEST_LIFECYCLE_NAME,
            "test",
            "lifecycle",
            "test",
            root_real_for_guard=test_root_real,
            guard_label="test lifecycle ledger",
        )

    stats["unlinked_call_ids"] = len(unlinked_calls)

    # -- human carriers ----------------------------------------------------
    keys = {
        builder.key
        for builder in builders.values()
        if builder.scope == "production" and valid_key(builder.key)
    }
    blocked_signoff_keys: list[str] = []
    signoff_keys = set(
        _iter_signoff_keys(control_root, root_real=root_real, blocked=blocked_signoff_keys)
    )
    if blocked_signoff_keys:
        warn(
            "signoff-key-refused",
            f"{len(blocked_signoff_keys)} sign-off key(s) refused before read "
            "(not a directory name or outside the control root)",
        )
    signoffs: dict[str, dict[str, Any]] = {}
    for key in sorted(keys | signoff_keys):
        parsed, signoff_warnings = _read_signoff(
            control_root, key, root_real=root_real, blocked=blocked_signoff_keys
        )
        for message in signoff_warnings:
            warn("signoff", message)
        if parsed is not None:
            signoffs[key] = parsed
    if blocked_signoff_keys:
        stats["blocked_reads"] += len(blocked_signoff_keys)
    gates_by_key = _read_gates(control_root, stats=stats, warn=warn)
    for builder in builders.values():
        if builder.scope != "production" or not builder.key:
            continue
        if builder.key in signoffs:
            builder.signoff = signoffs[builder.key]
        builder.gates = list(gates_by_key.get(builder.key, ()))

    # A key with a sign-off or a gate but no folded record still happened: it is
    # recorded as its own human-carrier row instead of disappearing from the
    # history (P2-4 - a gate-only key must not be invisible).
    recorded_keys = {
        builder.key
        for builder in builders.values()
        if builder.scope == "production" and builder.key
    }
    for key in sorted(signoff_keys - recorded_keys):
        builder = builder_for("production", f"signoff|{key}")
        builder.kind_hint = "signoff"
        builder.key = key
        builder.signoff = signoffs.get(key)
    for key in sorted(set(gates_by_key) - recorded_keys - signoff_keys):
        builder = builder_for("production", f"gate|{key}")
        builder.kind_hint = "gate"
        builder.key = key
        builder.gates = list(gates_by_key.get(key, ()))

    # -- freeze ------------------------------------------------------------
    records = [
        _finalize(builder, project_id, redact=redact) for builder in builders.values()
    ]
    withheld = sum(1 for record in records if record.redaction.omitted_fields)
    redacted = sum(1 for record in records if record.redaction.substitutions)
    truncated = sum(1 for record in records if record.redaction.truncated_fields)
    if redacted:
        warn(
            "free-text-redacted",
            f"{redacted} record(s) carried known-secret matches in free text; values were redacted",
        )
    if truncated:
        warn(
            "free-text-truncated",
            f"{truncated} record(s) carried free text longer than "
            f"{FREE_TEXT_LIMIT} bytes; clipped and boundary-scrubbed",
        )
    if withheld and redact is None:
        warn(
            "free-text-withheld",
            f"{withheld} record(s) had free text withheld: no redactor was injected (fail-closed)",
        )
    dropped = sum(record.redaction.dropped_fields for record in records)
    invalid = sum(record.redaction.invalid_fields for record in records)
    if dropped:
        warn(
            "schema-fields-dropped",
            f"{dropped} carrier field(s) were outside the read schema and not echoed",
        )
    if invalid:
        warn(
            "structural-fields-invalid",
            f"{invalid} structural carrier field(s) failed validation and are reported as not recorded",
        )
    records.sort(key=lambda record: (record.ts or "", record.opaque_id), reverse=True)
    stats["production_records"] = sum(1 for record in records if record.scope == "production")
    stats["test_records"] = sum(1 for record in records if record.scope == "test")

    return HistorySnapshot(
        control_root=control_root,
        project_id=project_id,
        records=tuple(records),
        stats=HistoryStats(**stats),
        warnings=tuple(warnings),
    )
