"""The single Python lifecycle writer for decision feedback (design D004).

One module owns the lifecycle facts of a decision record: the creation fact
(``record-start``) and the four feedback words the design pins in §4.2:

* ``consumed`` - the consumer really received the choice (not "adopted", not
  "finished");
* ``executed`` - a declared action really happened (handed to PM, asked the
  user, ran the type read...), with an action label - never a free-text state;
* ``settled`` - this processing round finished or failed, with the outcome
  vocabulary (not "the key is done");
* ``signoff`` - the signoff file really was written (path + sha256 are
  structural evidence, not prose).

The store is the existing managed wire store (:mod:`decision_wire`): every fact
goes through ``append_event`` (lock -> dedupe -> tail repair -> append ->
fsync). Nothing here uses a bare append, a second scheduler or a transaction.

Local envelope meta
-------------------
``DecisionMeta`` is the local envelope meta only (design §4.1):
``record_version=2``, ``logical_id``, ``key``, nullable ``task_key``,
``initiator_role``, nullable ``retry_of``. It is never part of the material sent
to a model; ``as_meta()`` is the only projection and ``as_envelope()`` keeps it
under the ``meta`` key next to (not inside) ``material``.

Version and association
-----------------------
``record-start`` persists the version and the association *before* any
transport call, so:

* a new record whose capture failed is still a v2 record;
* a record without any wire row is not "legacy" - version is read from the
  creation fact, never inferred from a missing capture;
* ``retry_of`` points the new ``logical_id`` at the previous one, and the
  previous bytes are never touched.

Idempotency and failures
-----------------------
Every append is deduplicated by ``event_id`` *inside the append lock*. A caller
that retries an ambiguous write reuses the same ``event_id`` and gets
``status="duplicate"`` (nothing written, still recorded). Two real actions on
the same decision and the same word are two different events and stay two rows
- never collapsed by ``(decision_id, word)``.

A write that fails returns ``LifecycleResult(status="failed", ...)`` with
``recorded=False``; the fact is never reported as recorded. A minimal, separate
failure ledger (``<ledger>-errors.jsonl``, kind ``lifecycle-error``) records the
failure so a reader can see "feedback failed" without pretending the feedback
row exists. If that sidecar write fails too, ``error_recorded=False`` says so -
the caller/reader must show "missing", not "recorded".

Request, PM note and task terminal (T10, additive)
--------------------------------------------------
The four feedback words above stay the only feedback vocabulary. Three separate
facts carry the rest of one round, each in its own kind and with a deterministic
``event_id`` so a repeated call cannot produce a second effect:

* ``request`` - the frozen ``request_prepared`` result plus the schema-3
  ``material``/``preparation`` layers it came from. ``available``/``attempts``
  are transport facts, ``business_decisions``/``choice``/``basis_*`` are the one
  business decision; a transport success with zero business decisions is stored
  as a refusal and never as an approval, replay signal or execution permission.
  The basis is re-checked through :mod:`decision_points` and the catalogue
  digest is recorded, so "the basis came from this PM preparation" is verifiable.
* ``note`` - the PM's pre-submission note with its own ``prepared_at``. Only a
  PM-initiated record may carry it, and it never shares a row with the model's
  selected basis (AC-007 keeps the two sources separate).
* ``terminal`` - this task's real terminal observation with its real reason and
  the post snapshot. It is not ``settled`` and not "done": it requires its own
  observation, refuses to precede any recorded observation, and no reader may
  derive it from a settled round.

Both the note and the request may echo the creation fact's before snapshot, but
only by exact equality: a later "before" (the current state) is refused as a
backfill. ``None`` and ``[]`` stay distinct in every snapshot that is stored.

Safety
------
Every structural string this writer owns is checked against the injected
known-secret redactor and refused (never echoed) when it matches; free text is
redacted and clipped by the managed store. No credential discovery happens in
this module: the redactor is injected by the caller.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

import decision
import decision_points
import decision_task_state
import decision_wire

#: The record version of a decision created by this contract (design §4.1).
RECORD_VERSION = 2

#: The exact envelope meta key set, in serialization order.
META_KEYS = (
    "record_version",
    "logical_id",
    "key",
    "task_key",
    "initiator_role",
    "retry_of",
)
META_ALLOWED_KEYS = META_KEYS + ("task_before",)

#: Who initiated the decision. ``unknown`` is an explicit value, never a guess:
#: the CLI reports ``unknown`` when it cannot know the role instead of
#: impersonating the PM.
INITIATOR_ROLES = ("pm", "coding", "research", "review", "unknown")

#: ``actor.kind`` stays the history reader's closed set (identity is separate).
ACTOR_KINDS = ("human", "system", "unknown")

#: The settled outcome vocabulary (mirrors the history read contract).
OUTCOMES = ("pending", "ok", "rework", "rollback", "inconclusive")

#: Executed action labels (design §4.2 examples + the four dp1..dp25 branches).
#: A new action needs a precise addition here; it never rides in free text.
EXECUTED_ACTIONS = (
    "type-read",
    "pm-handoff",
    "clarify",
    "narrow",
    "split",
    "direct-exec",
    "escalate",
    "continue",
    "user-confirm",
    "record",
)

#: The only four feedback words this writer emits.
STAGES = ("consumed", "executed", "settled", "signoff")

#: Required keys of the frozen ``DecisionClient.request_prepared`` result this
#: writer consumes. A caller cannot hand over a look-alike mapping that lacks
#: the transport/business split, and extra frozen fields are accepted untouched.
REQUEST_RESULT_FIELDS = (
    "dp",
    "available",
    "replayed",
    "choice",
    "basis_id",
    "basis_text",
    "basis_source",
    "prepared_at",
    "reason",
    "attempts",
    "transport_attempts",
    "business_decisions",
)

#: Frozen refusal vocabulary of a prepared request (the transport module owns
#: the constants; this is the same set, never a new word).
REQUEST_REASONS = frozenset(decision.REASON_CODES | {decision.REASON_INPUT_INCOMPLETE})

#: The prepared basis of a valid business decision always comes from the PM.
BASIS_SOURCE = decision_points.BASIS_SOURCE

#: A PM note is authored by the PM before submission; nothing else qualifies.
NOTE_SOURCE = "pm-prepared"

#: This task's real terminal observation (AC-046 wording). It is not a key/
#: phase closure and never follows from ``settled``.
TASK_TERMINALS = ("completed", "incomplete", "blocked")

RESULT_STATUSES = ("written", "duplicate", "failed")

_KEY_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_TOKEN_PATTERN = decision_wire.EVENT_ID_PATTERN
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_DECISION_ID = 256


class LifecycleInputError(ValueError):
    """A lifecycle request violates the writer contract (fail-closed, no write).

    Messages name the offending *field* and the rule only: a caller value (which
    may itself be a known secret) is never echoed.
    """


@dataclass(frozen=True)
class LifecycleResult:
    """The structured outcome of one lifecycle write.

    ``recorded`` is the only signal a consumer may treat as "the fact is in the
    ledger"; ``status="failed"`` always means ``recorded=False``.
    """

    stage: str
    status: str
    event_id: str | None = None
    error_class: str | None = None
    line_bytes: int = 0
    #: ``None`` = no failure happened (no sidecar attempted); ``True`` = the
    #: independent failure fact was written; ``False`` = even that failed, so a
    #: reader may only show "feedback missing".
    error_recorded: bool | None = None

    @property
    def recorded(self) -> bool:
        return self.status in ("written", "duplicate")

    @property
    def duplicate(self) -> bool:
        return self.status == "duplicate"

    @property
    def failed(self) -> bool:
        return self.status == "failed"


# ---------------------------------------------------------------------------
# Validation helpers (structural values only; free text is the store's job)
# ---------------------------------------------------------------------------


def _refuse(field: str, rule: str) -> None:
    raise LifecycleInputError(f"{field} is not valid: {rule}")


def _check_key(field: str, value: object) -> str:
    if not isinstance(value, str) or _KEY_PATTERN.match(value) is None:
        _refuse(field, "expected one directory-name key ([A-Za-z0-9][A-Za-z0-9_.-]{0,127})")
    return value


def _check_token(field: str, value: object) -> str:
    if not isinstance(value, str) or _TOKEN_PATTERN.match(value) is None:
        _refuse(field, "expected one ledger token ([A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127})")
    return value


def _check_decision_id(field: str, value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > _MAX_DECISION_ID:
        _refuse(field, "expected a bounded decision id")
    if "\x00" in value or "/" in value or "\\" in value or ".." in value:
        _refuse(field, "expected an id value with no separators or traversal")
    if ":" not in value:
        _refuse(field, "expected the '<dp>:<id>' form")
    return value


def _check_relpath(field: str, value: object) -> str:
    if not isinstance(value, str) or not value or len(value) > 512:
        _refuse(field, "expected a bounded relative path")
    if value.startswith("/") or "\\" in value or "\x00" in value:
        _refuse(field, "expected a relative path with '/' separators only")
    if any(part in ("", "..") for part in value.split("/")):
        _refuse(field, "expected a relative path with no empty or '..' segment")
    return value


def _check_sha256(field: str, value: object) -> str:
    if not isinstance(value, str) or _SHA256_PATTERN.match(value) is None:
        _refuse(field, "expected 64 lowercase hex characters")
    return value


def _guard_secret(store: "LifecycleStore", field: str, value: str | None) -> None:
    """Refuse a structural value the injected known-secret set recognises.

    Structural values are written verbatim, so this is the last boundary that
    can keep a credential out of the ledger key/id/path columns (AC-019). A
    redactor that raises cannot prove anything, so the write is refused as
    well; the value is never part of the message.
    """
    if value is None or not value or store.redact is None:
        return
    try:
        hits = int(getattr(store.redact.redact(value), "hits", 0))
    except Exception:  # noqa: BLE001 - a broken redactor never proves text safe
        raise LifecycleInputError(f"{field} could not be proven secret-free") from None
    if hits:
        raise LifecycleInputError(f"{field} matches a known secret; the value is withheld")


def _check_actor(actor: tuple[str, str] | None) -> tuple[str, str] | None:
    if actor is None:
        return None
    if not isinstance(actor, tuple) or len(actor) != 2:
        _refuse("actor", "expected a (kind, id) pair")
    kind, actor_id = actor
    if kind not in ACTOR_KINDS:
        _refuse("actor.kind", f"expected one of {ACTOR_KINDS}")
    if not isinstance(actor_id, str) or not actor_id:
        _refuse("actor.id", "expected a non-empty declared identity")
    return actor


def _check_timestamp(field: str, value: object) -> str:
    """Validate an ISO-8601 stamp with an explicit offset; the text is kept as-is.

    The recorded value is the producer's own ``prepared_at``/``observed_at``:
    it is never normalised and never replaced by "now" (a write-time clock is
    not a preparation time).
    """
    if not isinstance(value, str) or not value or "T" not in value:
        _refuse(field, "expected an ISO-8601 timestamp with an explicit offset")
    try:
        parsed = datetime.datetime.fromisoformat(
            value[:-1] + "+00:00" if value.endswith("Z") else value
        )
    except ValueError:
        _refuse(field, "expected an ISO-8601 timestamp")
    if parsed.tzinfo is None:
        _refuse(field, "expected an explicit timezone offset (Z or +hh:mm)")
    return value


def _bounded_text(store: "LifecycleStore", field: str, text: object, limit: int) -> str:
    """Redact first, then refuse an over-long value instead of clipping it.

    A clipped note/reason looks complete while the tail is gone ("不截断理由"),
    so the storage bound is a refusal, not a truncation. The redacted form is
    what the store would persist, so the check runs on exactly that text.
    """
    if not isinstance(text, str) or not text.strip():
        _refuse(field, "expected non-empty text")
    try:
        redacted = store.redact.redact(text).text
    except Exception:  # noqa: BLE001 - a broken redactor proves nothing
        raise LifecycleInputError(f"{field} could not be proven secret-free") from None
    size = len(redacted.encode("utf-8"))
    if size > limit:
        _refuse(field, f"is {size} bytes, over the {limit}-byte storage bound; it is not truncated")
    return redacted


def _stable_event_id(prefix: str, *parts: str) -> str:
    """Deterministic idempotency key: one fact per real subject, never two."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return f"{prefix}-{digest[:32]}"


def _ledger_facts(
    store: "LifecycleStore", meta: "DecisionMeta"
) -> tuple[dict[str, object], list[dict[str, object]]]:
    """The same task's single creation fact plus the readable ledger rows.

    Raises :class:`LifecycleInputError` when the creation association is not
    provable (damaged ledger, no creation fact, or a fact of another task). An
    unreadable ledger propagates ``OSError``: "cannot read" must never look like
    "nothing recorded".
    """
    prior = read_lifecycle(store)
    if any(
        (
            prior.stats.bad_json,
            prior.stats.bad_utf8,
            prior.stats.unknown_schema,
            prior.stats.oversized_line,
            prior.stats.incomplete_tail,
        )
    ):
        _refuse("logical_id", "creation association is not provable on a damaged ledger")
    starts = [
        row
        for row in prior.events
        if row.get("kind") == "record-start" and row.get("logical_id") == meta.logical_id
    ]
    if len(starts) != 1 or starts[0].get("key") != meta.key or starts[0].get("task_key") != meta.task_key:
        _refuse("logical_id", "requires the same task's creation fact")
    return starts[0], prior.events


def _check_before(
    start: Mapping[str, object], task_before: dict[str, object] | None
) -> dict[str, object] | None:
    """A later fact may repeat the recorded before, never replace it.

    The creation fact was written *before* the transport call, so its snapshot is
    the only legal before. Passing a different snapshot (typically the current
    state read later) is a backfill and is refused; passing none keeps "not
    recorded" honest instead of inventing a value.
    """
    try:
        given = decision_task_state.validate_task_state(task_before)
        stored = decision_task_state.validate_task_state(start.get("task_before"))
    except decision_task_state.TaskStateInputError as exc:
        raise LifecycleInputError(str(exc)) from None
    if given is None:
        return None
    if stored is None or not decision_task_state.same_snapshot(stored, given):
        _refuse(
            "task_before",
            "must repeat the creation fact's recorded before snapshot; a later before cannot be backfilled",
        )
    return given


def _check_parent_ref(
    parent_ref: str | None,
    decision_id: str,
    meta: "DecisionMeta",
    events: Sequence[Mapping[str, object]],
) -> str | None:
    """A successor link must point at a decision this ledger really recorded.

    The parent and the successor belong to the same key (one gate's steering is
    the same key's next request); an unrecorded or cross-key reference is refused
    instead of stored as an unverifiable link. The parent's own rows are never
    rewritten, so the gate selection is not evidence that the parent released.
    """
    if parent_ref is None:
        return None
    parent_ref = _check_decision_id("parent_ref", parent_ref)
    if parent_ref == decision_id:
        _refuse("parent_ref", "a decision cannot be its own parent")
    rows = [row for row in events if row.get("decision_id") == parent_ref]
    if not rows:
        _refuse("parent_ref", "must name a decision already recorded in this ledger")
    keys = {row.get("key") for row in rows if isinstance(row.get("key"), str)}
    if keys and meta.key not in keys:
        _refuse("parent_ref", "must belong to the same key as the successor record")
    return parent_ref


def _count(field: str, value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        _refuse(field, "expected a non-negative integer")
    return value


def _request_fields(result: object) -> dict[str, object]:
    """Validate the frozen prepared-request result and the transport/business split.

    The pair is decoded once: ``available``/``attempts`` are wire facts, and a
    business choice only exists when ``business_decisions == 1``. A transport
    success with zero business decisions therefore stays a refusal (with its
    frozen reason) and can never be read as an approval, a replay signal or an
    execution permission.
    """
    if not isinstance(result, Mapping):
        _refuse("result", "expected the frozen prepared-request result mapping")
    missing = [name for name in REQUEST_RESULT_FIELDS if name not in result]
    if missing:
        _refuse("result", f"missing prepared-request field(s) {missing}")
    available = result["available"]
    replayed = result["replayed"]
    if not isinstance(available, bool) or not isinstance(replayed, bool):
        _refuse("result", "available/replayed must be booleans")
    business = _count("business_decisions", result["business_decisions"])
    if business > 1:
        _refuse("business_decisions", "expected 0 or 1 for one prepared request")
    attempts = _count("attempts", result["attempts"])
    transport_attempts = _count("transport_attempts", result["transport_attempts"])
    dp = _check_token("dp", result["dp"])
    prepared_at = _check_timestamp("prepared_at", result["prepared_at"])
    reason = result["reason"]
    if reason is not None:
        reason = _check_token("reason", reason)
        if reason not in REQUEST_REASONS:
            _refuse("reason", "is not in the frozen prepared-request reason vocabulary")
    choice = result["choice"]
    basis_id = result["basis_id"]
    basis_text = result["basis_text"]
    basis_source = result["basis_source"]

    if business == 0:
        if choice is not None or basis_id is not None or basis_text is not None or basis_source is not None:
            _refuse(
                "choice",
                "a request without a valid business decision cannot claim a choice or a basis",
            )
        if replayed:
            # A replay answers from the recorded decision: it is neither a new
            # business decision nor a failure, and it sends nothing.
            if reason is not None:
                _refuse("reason", "a replayed request carries no failure reason")
            if transport_attempts != 0 or attempts != 0:
                _refuse("transport_attempts", "a replayed request makes no transport attempt")
        elif reason is None:
            _refuse("reason", "a request without a business decision must record its frozen reason")
    else:
        if not available:
            _refuse("available", "a valid business decision requires an available transport")
        if replayed:
            _refuse("replayed", "a replay is not a new business decision")
        if attempts < 1:
            _refuse("attempts", "a valid business decision requires a real request attempt")
        if reason is not None:
            _refuse("reason", "a valid business decision cannot also carry a failure reason")
        choice = _check_token("choice", choice)
        basis_id = _check_token("basis_id", basis_id)
        if not isinstance(basis_text, str) or not basis_text.strip():
            _refuse("basis_text", "a valid business decision requires the selected basis text")
        if basis_source != BASIS_SOURCE:
            _refuse("basis_source", f"expected {BASIS_SOURCE!r} (the PM-prepared catalog)")
    return {
        "dp": dp,
        "available": available,
        "replayed": replayed,
        "choice": choice,
        "basis_id": basis_id,
        "basis_text": basis_text,
        "basis_source": basis_source,
        "prepared_at": prepared_at,
        "reason": reason,
        "attempts": attempts,
        "transport_attempts": transport_attempts,
        "business_decisions": business,
    }


def _preparation_provenance(
    store: "LifecycleStore", fields: Mapping[str, object], material: object, preparation: object
) -> str:
    """Re-validate the schema-3 ``preparation``/``material`` pair via the authority.

    The single source of the preparation contract is :mod:`decision_points`:
    this writer does not carry a second copy of the catalogue rules. It adds the
    two facts the writer owns - the result's ``prepared_at`` must be the
    preparation's own stamp (no write-time clock), and the recorded
    ``basis_text`` must be the selected catalogue item's text (never free text
    from the model or the transport). Returns the catalogue digest.
    """
    if not isinstance(preparation, Mapping):
        _refuse("preparation", f"expected the prepared object {list(decision_points.PREPARATION_KEYS)}")
    if not isinstance(material, Mapping) or not material:
        _refuse("material", "a valid business decision requires the material it was prepared from")
    try:
        issues = decision_points.preparation_issues(
            str(fields["dp"]),
            preparation,
            material,
            choice=fields["choice"],
            basis_id=fields["basis_id"],
        )
    except decision.DecisionInputError:
        _refuse("dp", "is not an active eight-entry decision point")
    if issues:
        name, rule = issues[0]
        # The authority's message is caller-derived text (it can name
        # caller-chosen preparation keys), so it is echoed only when the injected
        # redactor proves it safe; otherwise only the field name is reported.
        if store.redact is not None and store.redact.redact(rule).hits:
            rule = "does not satisfy the prepared-basis contract; the value is withheld"
        _refuse(name, rule)
    if preparation.get("prepared_at") != fields["prepared_at"]:
        _refuse(
            "prepared_at",
            "must be the preparation's recorded prepared_at; the write clock is not a preparation time",
        )
    catalog = preparation.get("basis_catalog")
    selected = next(
        (
            item
            for item in catalog
            if isinstance(item, Mapping) and item.get("id") == fields["basis_id"]
        ),
        None,
    )
    if selected is None or selected.get("text") != fields["basis_text"]:
        _refuse("basis_text", "must be the selected prepared item's text, not caller-provided prose")
    try:
        body = json.dumps(
            preparation, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
        )
    except (TypeError, ValueError):
        _refuse("preparation", "must be serialisable (canonical digest for provenance)")
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Local envelope meta (never model material)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionMeta:
    """The local envelope meta of one real decision (design §4.1)."""

    key: str
    logical_id: str
    initiator_role: str = "unknown"
    task_key: str | None = None
    retry_of: str | None = None
    record_version: int = RECORD_VERSION
    task_before: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if isinstance(self.record_version, bool) or self.record_version != RECORD_VERSION:
            _refuse("record_version", f"expected {RECORD_VERSION}")
        _check_key("key", self.key)
        _check_token("logical_id", self.logical_id)
        if self.initiator_role not in INITIATOR_ROLES:
            _refuse("initiator_role", f"expected one of {INITIATOR_ROLES}")
        if self.task_key is not None:
            _check_token("task_key", self.task_key)
        if self.retry_of is not None:
            _check_token("retry_of", self.retry_of)
        if self.task_before is not None and self.task_key is None:
            _refuse("task_before", "requires an associated task")
        try:
            object.__setattr__(self, "task_before", decision_task_state.validate_task_state(self.task_before))
        except decision_task_state.TaskStateInputError as exc:
            raise LifecycleInputError(str(exc)) from None

    @classmethod
    def create(
        cls,
        key: str,
        *,
        task_key: str | None = None,
        initiator_role: str = "unknown",
        retry_of: str | None = None,
        logical_id: str | None = None,
        record_version: int = RECORD_VERSION,
        task_before: dict[str, object] | None = None,
    ) -> "DecisionMeta":
        """Create the meta of one real decision (one fresh ``logical_id``)."""
        return cls(
            key=key,
            logical_id=logical_id if logical_id is not None else decision_wire.new_id(),
            initiator_role=initiator_role,
            task_key=task_key,
            retry_of=retry_of,
            record_version=record_version,
            task_before=task_before,
        )

    def as_meta(self) -> dict[str, object]:
        """The exact local meta mapping, in ``META_KEYS`` order."""
        result = {
            "record_version": self.record_version,
            "logical_id": self.logical_id,
            "key": self.key,
            "task_key": self.task_key,
            "initiator_role": self.initiator_role,
            "retry_of": self.retry_of,
        }
        if self.task_before is not None:
            result["task_before"] = decision_task_state.validate_task_state(self.task_before)
        return result

    def as_envelope(self, material: Mapping[str, object]) -> dict[str, object]:
        """``{"material": ..., "meta": ...}`` - the meta never enters material."""
        if not isinstance(material, Mapping):
            _refuse("material", "expected a mapping (the business material)")
        return {"material": dict(material), "meta": self.as_meta()}

    @classmethod
    def from_envelope(cls, envelope: Mapping[str, object]) -> "DecisionMeta":
        """Read and validate the meta of a local envelope (no defaulting)."""
        if not isinstance(envelope, Mapping):
            _refuse("envelope", "expected a mapping")
        raw = envelope.get("meta")
        if not isinstance(raw, Mapping):
            _refuse("envelope.meta", "required for a versioned record")
        unknown = [key for key in raw if key not in META_ALLOWED_KEYS]
        if unknown:
            # Count only: a caller-chosen key must not be echoed into an error.
            _refuse("envelope.meta", f"carries {len(unknown)} unknown key(s)")
        for required in ("record_version", "logical_id", "key", "initiator_role"):
            if required not in raw:
                _refuse("envelope.meta", f"missing required key {required}")
        return cls(
            key=raw["key"],
            logical_id=raw["logical_id"],
            initiator_role=raw["initiator_role"],
            task_key=raw.get("task_key"),
            retry_of=raw.get("retry_of"),
            record_version=raw["record_version"],
            task_before=raw.get("task_before"),
        )


# ---------------------------------------------------------------------------
# Store: the managed ledger plus its independent failure ledger
# ---------------------------------------------------------------------------


def _refuse_link(path: pathlib.Path, name: str) -> None:
    """Refuse a symbolic-link ledger path (the final component only).

    A linked ledger would write through to a target this store does not own.
    This is a lookup, not a race-free guarantee: an attacker that swaps the
    path between the check and ``os.open`` is not prevented here (design §9
    does not claim TOCTOU-free pure-lstat checks).
    """
    try:
        linked = os.path.islink(path)
    except OSError:
        linked = False
    if linked:
        raise decision_wire.WireScopeError(
            f"{name} is a symbolic link; refusing a link target outside this store"
        )


def _failure_sink_for(sink: pathlib.Path) -> pathlib.Path:
    if sink.name.endswith(".jsonl"):
        return sink.with_name(sink.name[: -len(".jsonl")] + "-errors.jsonl")
    return sink.with_name(sink.name + "-errors.jsonl")


@dataclass(frozen=True)
class LifecycleStore:
    """One managed lifecycle ledger (production or isolated test root)."""

    sink: pathlib.Path
    project_id: str
    redact: decision_wire.SecretRedactor
    scope_kind: str = "test"
    error_sink: pathlib.Path | None = None
    warn: Callable[[str], None] | None = None
    line_cap: int = decision_wire.LINE_CAP_BYTES
    segment_cap: int = decision_wire.SEGMENT_CAP_BYTES
    lock_budget_s: float = decision_wire.LOCK_BUDGET_S
    lock_retries: int = decision_wire.LOCK_RETRIES
    lock_base_delay: float = decision_wire.LOCK_BASE_DELAY
    origin: str = "decision-lifecycle"

    def __post_init__(self) -> None:
        if self.redact is None:
            # No known set -> structural values cannot be proven safe; there is
            # deliberately no "unproven text" mode for feedback.
            _refuse("redact", "required: inject the caller's known-secret redactor")
        sink = pathlib.Path(self.sink)
        object.__setattr__(self, "sink", sink)
        if not isinstance(self.project_id, str) or not self.project_id:
            _refuse("project_id", "expected a non-empty local project identity")
        if self.scope_kind not in decision_wire.SCOPE_KINDS:
            _refuse("scope_kind", f"expected one of {decision_wire.SCOPE_KINDS}")
        if self.scope_kind == "test":
            # Same rule the managed store applies per scope: an isolated sink
            # must not resolve into the production tree.
            decision_wire.WireScope._refuse_production_paths(sink)
        _refuse_link(sink, "sink")
        error_sink = self.error_sink if self.error_sink is not None else _failure_sink_for(sink)
        error_sink = pathlib.Path(error_sink)
        object.__setattr__(self, "error_sink", error_sink)
        _refuse_link(error_sink, "error_sink")

    @classmethod
    def production(
        cls,
        control_root: pathlib.Path | str,
        *,
        redact: decision_wire.SecretRedactor,
        project_id: str | None = None,
        warn: Callable[[str], None] | None = None,
        **options: object,
    ) -> "LifecycleStore":
        root = pathlib.Path(control_root)
        return cls(
            sink=decision_wire.production_lifecycle_sink(root),
            project_id=project_id or decision_wire.project_id_for(root),
            redact=redact,
            scope_kind="production",
            warn=warn,
            **options,
        )

    @classmethod
    def test(
        cls,
        test_root: pathlib.Path | str,
        *,
        project_id: str,
        redact: decision_wire.SecretRedactor,
        warn: Callable[[str], None] | None = None,
        **options: object,
    ) -> "LifecycleStore":
        return cls(
            sink=decision_wire.test_lifecycle_sink(test_root),
            project_id=project_id,
            redact=redact,
            scope_kind="test",
            warn=warn,
            **options,
        )

    def _scope(
        self,
        *,
        decision_id: str | None = None,
        dp: str | None = None,
        key: str | None = None,
        task_key: str | None = None,
        actor: tuple[str, str] | None = None,
        origin: str | None = None,
        sink: pathlib.Path | None = None,
    ) -> decision_wire.WireScope:
        """One fresh managed scope per write (no stale failure breaker)."""
        return decision_wire.WireScope(
            sink=sink if sink is not None else self.sink,
            project_id=self.project_id,
            scope_kind=self.scope_kind,
            origin=origin or self.origin,
            decision_id=decision_id,
            dp=dp,
            key=key,
            task_key=task_key,
            actor_kind=actor[0] if actor is not None else None,
            actor_id=actor[1] if actor is not None else None,
            redact=self.redact,
            warn=self.warn,
            line_cap=self.line_cap,
            segment_cap=self.segment_cap,
            lock_budget_s=self.lock_budget_s,
            lock_retries=self.lock_retries,
            lock_base_delay=self.lock_base_delay,
        )


# ---------------------------------------------------------------------------
# Write path
# ---------------------------------------------------------------------------


def _event_id_of(event: Mapping[str, object]) -> str | None:
    event_id = event.get("event_id")
    return event_id if isinstance(event_id, str) else None


def _start_event_id(meta: DecisionMeta) -> str:
    """Deterministic creation-fact id: one start fact per logical record."""
    digest = hashlib.sha256(f"{meta.logical_id}|{meta.record_version}".encode("ascii"))
    return "rs-" + digest.hexdigest()[:32]


def _write_failure_fact(
    store: LifecycleStore,
    meta: DecisionMeta,
    *,
    stage: str,
    error_class: str,
    attempted_event_id: str | None,
    decision_id: str | None,
) -> bool:
    """Best effort, independent failure fact; never masks the original failure."""
    if store.error_sink is None:
        return False
    try:
        scope = store._scope(
            decision_id=decision_id,
            key=meta.key,
            task_key=meta.task_key,
            origin=f"{store.origin}-error",
            sink=store.error_sink,
        )
        event = decision_wire.lifecycle_error_event(
            scope,
            logical_id=meta.logical_id,
            stage=stage,
            error_class=error_class,
            attempted_event_id=attempted_event_id,
            detail=f"{stage} write failed: {error_class}",
        )
        return decision_wire.append_event(scope, event).written
    except Exception:  # noqa: BLE001 - the sidecar must not break the caller
        return False


def _append(
    store: LifecycleStore,
    meta: DecisionMeta,
    *,
    stage: str,
    scope: decision_wire.WireScope,
    event: Mapping[str, object],
    decision_id: str | None,
) -> LifecycleResult:
    event_id = _event_id_of(event)
    try:
        append = decision_wire.append_event(scope, event, dedupe_event_id=True)
    except Exception:  # noqa: BLE001 - the managed store reports, never raises
        error_class = "unexpected"
        recorded = _write_failure_fact(
            store,
            meta,
            stage=stage,
            error_class=error_class,
            attempted_event_id=event_id,
            decision_id=decision_id,
        )
        return LifecycleResult(
            stage=stage,
            status="failed",
            event_id=event_id,
            error_class=error_class,
            error_recorded=recorded,
        )
    if append.recorded:
        return LifecycleResult(
            stage=stage,
            status=append.status,
            event_id=append.event_id or event_id,
            line_bytes=append.line_bytes,
        )
    error_class = append.error_class or "failed"
    recorded = _write_failure_fact(
        store,
        meta,
        stage=stage,
        error_class=error_class,
        attempted_event_id=event_id,
        decision_id=decision_id,
    )
    return LifecycleResult(
        stage=stage,
        status="failed",
        event_id=event_id,
        error_class=error_class,
        error_recorded=recorded,
    )


def record_start(
    store: LifecycleStore,
    meta: DecisionMeta,
    *,
    decision_id: str | None = None,
    actor: tuple[str, str] | None = None,
    event_id: str | None = None,
) -> LifecycleResult:
    """Persist the creation fact (``record_version`` + association) first.

    Call this before the transport call: the fact is what makes a failed
    capture a new v2 record instead of an unproven legacy row.

    ``decision_id`` is the real id the caller already knows (the CLI derives it
    as ``<dp>:<logical_id>`` before the model call). When given, the creation
    fact — and any failure fact derived from this write — carries it, so a
    disabled/failed record is associated by a recorded value instead of being
    re-read as an unversioned legacy row. It is optional only for callers that
    genuinely have no id yet; nothing here infers one from a key or a clock.
    """
    if not isinstance(meta, DecisionMeta):
        _refuse("meta", "expected a DecisionMeta")
    actor = _check_actor(actor)
    if decision_id is not None:
        decision_id = _check_decision_id("decision_id", decision_id)
    for field, value in (
        ("key", meta.key),
        ("task_key", meta.task_key),
        ("logical_id", meta.logical_id),
        ("retry_of", meta.retry_of),
        ("decision_id", decision_id),
    ):
        _guard_secret(store, field, value)
    if event_id is not None:
        event_id = _check_token("event_id", event_id)
        _guard_secret(store, "event_id", event_id)

    scope = store._scope(
        decision_id=decision_id, key=meta.key, task_key=meta.task_key, actor=actor
    )
    event = decision_wire.record_start_event(
        scope,
        logical_id=meta.logical_id,
        record_version=meta.record_version,
        initiator_role=meta.initiator_role,
        retry_of=meta.retry_of,
        task_before=meta.task_before,
        actor=actor,
        event_id=event_id if event_id is not None else _start_event_id(meta),
    )
    return _append(
        store,
        meta,
        stage="record-start",
        scope=scope,
        event=event,
        decision_id=decision_id,
    )


def record_lifecycle(
    store: LifecycleStore,
    meta: DecisionMeta,
    *,
    stage: str,
    decision_id: str,
    dp: str | None = None,
    action: str | None = None,
    outcome: str | None = None,
    reason: str | None = None,
    answer: str | None = None,
    result: str | None = None,
    evidence_path: str | None = None,
    evidence_sha256: str | None = None,
    snapshot_sha256: str | None = None,
    task_after: dict[str, object] | None = None,
    answer_source: str | None = None,
    actor: tuple[str, str] | None = None,
    event_id: str | None = None,
) -> LifecycleResult:
    """Write one feedback fact for a recorded decision (core of the four APIs).

    Stage-specific schema is enforced here, so no state is smuggled through free
    text: ``executed`` needs an ``action`` label, ``settled`` needs an
    ``outcome``, ``signoff`` needs the written file's ``evidence_path`` and
    ``evidence_sha256`` (plus the optional ``snapshot_sha256`` of the exact
    dp25 snapshot the file signs).
    """
    if not isinstance(meta, DecisionMeta):
        _refuse("meta", "expected a DecisionMeta")
    if stage not in STAGES:
        _refuse("stage", f"expected one of {STAGES}")
    if task_after is not None and (stage not in ("executed", "settled") or meta.task_key is None):
        _refuse("task_after", "requires an associated task and executed/settled stage")
    try:
        task_after = decision_task_state.validate_task_state(task_after)
        decision_task_state.validate_observation_order(meta.task_before, task_after)
        if task_after is not None:
            prior = read_lifecycle(store)
            if any((prior.stats.bad_json, prior.stats.bad_utf8, prior.stats.unknown_schema, prior.stats.oversized_line, prior.stats.incomplete_tail)):
                _refuse("task_after", "creation association is not provable")
            starts = [row for row in prior.events if row.get("kind") == "record-start" and row.get("logical_id") == meta.logical_id]
            if len(starts) != 1 or starts[0].get("key") != meta.key or starts[0].get("task_key") != meta.task_key:
                _refuse("task_after", "requires the same task's creation fact")
            saved_before = decision_task_state.validate_task_state(starts[0].get("task_before"))
            decision_task_state.validate_observation_order(saved_before, task_after)
    except decision_task_state.TaskStateInputError as exc:
        raise LifecycleInputError(str(exc)) from None
    actor = _check_actor(actor)
    decision_id = _check_decision_id("decision_id", decision_id)
    if dp is not None:
        dp = _check_token("dp", dp)
        if not decision_id.startswith(dp + ":"):
            _refuse("dp", "does not match the decision_id prefix")
    if answer_source is not None:
        answer_source = _check_token("answer_source", answer_source)
    if event_id is not None:
        event_id = _check_token("event_id", event_id)

    if stage == "settled":
        if action is not None:
            _refuse("action", "only valid for stage executed")
        if evidence_path is not None or evidence_sha256 is not None:
            _refuse("evidence_path", "only valid for stage signoff")
        if snapshot_sha256 is not None:
            _refuse("snapshot_sha256", "only valid for stage signoff")
        if outcome not in OUTCOMES:
            _refuse("outcome", f"expected one of {OUTCOMES}")
        # The current reader validates ``settled.result`` as the outcome
        # vocabulary; the structural ``outcome`` field carries it as well.
        result = outcome
    elif stage == "executed":
        if outcome is not None:
            _refuse("outcome", "only valid for stage settled")
        if evidence_path is not None or evidence_sha256 is not None:
            _refuse("evidence_path", "only valid for stage signoff")
        if snapshot_sha256 is not None:
            _refuse("snapshot_sha256", "only valid for stage signoff")
        if action not in EXECUTED_ACTIONS:
            _refuse("action", f"expected one of {EXECUTED_ACTIONS}")
    elif stage == "signoff":
        if outcome is not None or action is not None:
            _refuse("action", "signoff records the successful file write only")
        evidence_path = _check_relpath("evidence_path", evidence_path)
        evidence_sha256 = _check_sha256("evidence_sha256", evidence_sha256)
        if snapshot_sha256 is not None:
            snapshot_sha256 = _check_sha256("snapshot_sha256", snapshot_sha256)
    else:  # consumed
        if action is not None or outcome is not None:
            _refuse("action", "consumed records receipt only")
        if evidence_path is not None or evidence_sha256 is not None:
            _refuse("evidence_path", "only valid for stage signoff")
        if snapshot_sha256 is not None:
            _refuse("snapshot_sha256", "only valid for stage signoff")

    for field, value in (
        ("key", meta.key),
        ("task_key", meta.task_key),
        ("logical_id", meta.logical_id),
        ("retry_of", meta.retry_of),
        ("decision_id", decision_id),
        ("dp", dp),
        ("event_id", event_id),
        ("evidence_path", evidence_path),
    ):
        _guard_secret(store, field, value)

    for field, value in (
        ("reason", reason),
        ("answer", answer),
        ("result", result),
    ):
        if value is not None and not isinstance(value, str):
            _refuse(field, "expected text")

    scope = store._scope(
        decision_id=decision_id,
        dp=dp,
        key=meta.key,
        task_key=meta.task_key,
        actor=actor,
    )
    event = decision_wire.lifecycle_event(
        scope,
        lifecycle=stage,
        logical_id=meta.logical_id,
        action=action,
        outcome=outcome,
        reason=reason,
        answer=answer,
        result=result,
        evidence_path=evidence_path,
        evidence_sha256=evidence_sha256,
        snapshot_sha256=snapshot_sha256,
        task_after=task_after,
        answer_source=answer_source,
        actor=actor,
        event_id=event_id,
    )
    return _append(
        store,
        meta,
        stage=stage,
        scope=scope,
        event=event,
        decision_id=decision_id,
    )


def record_consumed(
    store: LifecycleStore,
    meta: DecisionMeta,
    *,
    decision_id: str,
    dp: str | None = None,
    answer: str | None = None,
    reason: str | None = None,
    answer_source: str | None = None,
    event_id: str | None = None,
    actor: tuple[str, str] | None = None,
) -> LifecycleResult:
    """``consumed``: the consumer really received the choice (not completion)."""
    return record_lifecycle(
        store,
        meta,
        stage="consumed",
        decision_id=decision_id,
        dp=dp,
        answer=answer,
        reason=reason,
        answer_source=answer_source,
        event_id=event_id,
        actor=actor,
    )


def record_executed(
    store: LifecycleStore,
    meta: DecisionMeta,
    *,
    decision_id: str,
    action: str,
    dp: str | None = None,
    task_after: dict[str, object] | None = None,
    result: str | None = None,
    reason: str | None = None,
    answer_source: str | None = None,
    event_id: str | None = None,
    actor: tuple[str, str] | None = None,
) -> LifecycleResult:
    """``executed``: a declared action really happened (``action`` + basis)."""
    return record_lifecycle(
        store,
        meta,
        stage="executed",
        decision_id=decision_id,
        dp=dp,
        task_after=task_after,
        action=action,
        result=result,
        reason=reason,
        answer_source=answer_source,
        event_id=event_id,
        actor=actor,
    )


def record_settled(
    store: LifecycleStore,
    meta: DecisionMeta,
    *,
    decision_id: str,
    outcome: str,
    dp: str | None = None,
    task_after: dict[str, object] | None = None,
    reason: str | None = None,
    event_id: str | None = None,
    actor: tuple[str, str] | None = None,
) -> LifecycleResult:
    """``settled``: this processing round's real outcome (never "key done")."""
    return record_lifecycle(
        store,
        meta,
        stage="settled",
        decision_id=decision_id,
        dp=dp,
        task_after=task_after,
        outcome=outcome,
        reason=reason,
        event_id=event_id,
        actor=actor,
    )


def record_signoff(
    store: LifecycleStore,
    meta: DecisionMeta,
    *,
    decision_id: str,
    evidence_path: str,
    evidence_sha256: str,
    snapshot_sha256: str | None = None,
    dp: str | None = None,
    reason: str | None = None,
    event_id: str | None = None,
    actor: tuple[str, str] | None = None,
) -> LifecycleResult:
    """``signoff``: the signoff file write really succeeded (path + sha256)."""
    return record_lifecycle(
        store,
        meta,
        stage="signoff",
        decision_id=decision_id,
        dp=dp,
        evidence_path=evidence_path,
        evidence_sha256=evidence_sha256,
        snapshot_sha256=snapshot_sha256,
        reason=reason,
        event_id=event_id,
        actor=actor,
    )


# ---------------------------------------------------------------------------
# T10 facts: PM note, real request with basis provenance, task terminal
# ---------------------------------------------------------------------------


def record_note(
    store: LifecycleStore,
    meta: DecisionMeta,
    *,
    decision_id: str,
    pm_note: str,
    prepared_at: str,
    parent_ref: str | None = None,
    task_before: dict[str, object] | None = None,
    actor: tuple[str, str] | None = None,
    event_id: str | None = None,
) -> LifecycleResult:
    """Store the PM's pre-submission note as its own fact (spec AC-007).

    Only a PM-initiated record may carry a PM note: a coding/research/review
    record (or an ``unknown`` initiator) is refused instead of impersonating the
    PM. ``prepared_at`` is the note's own pre-submission time and is required -
    the write clock is never used as a substitute. The note never shares a row
    with the model's selected basis, so the two sources stay separable.
    """
    if not isinstance(meta, DecisionMeta):
        _refuse("meta", "expected a DecisionMeta")
    if meta.initiator_role != "pm":
        _refuse("initiator_role", "a PM note requires a PM-initiated record")
    decision_id = _check_decision_id("decision_id", decision_id)
    prepared_at = _check_timestamp("prepared_at", prepared_at)
    text = _bounded_text(store, "pm_note", pm_note, decision_wire.NOTE_TEXT_BYTES)
    actor = _check_actor(actor)
    start, events = _ledger_facts(store, meta)
    before = _check_before(start, task_before)
    parent_ref = _check_parent_ref(parent_ref, decision_id, meta, events)
    if event_id is not None:
        event_id = _check_token("event_id", event_id)
    else:
        event_id = _stable_event_id("nt", meta.logical_id, prepared_at)
    for field, value in (
        ("key", meta.key),
        ("task_key", meta.task_key),
        ("logical_id", meta.logical_id),
        ("retry_of", meta.retry_of),
        ("decision_id", decision_id),
        ("prepared_at", prepared_at),
        ("parent_ref", parent_ref),
        ("event_id", event_id),
    ):
        _guard_secret(store, field, value)

    scope = store._scope(
        decision_id=decision_id, key=meta.key, task_key=meta.task_key, actor=actor
    )
    event = decision_wire.note_event(
        scope,
        logical_id=meta.logical_id,
        pm_note=text,
        prepared_at=prepared_at,
        note_source=NOTE_SOURCE,
        parent_ref=parent_ref,
        task_before=before,
        event_id=event_id,
    )
    return _append(
        store, meta, stage="note", scope=scope, event=event, decision_id=decision_id
    )


def record_request(
    store: LifecycleStore,
    meta: DecisionMeta,
    *,
    decision_id: str,
    result: Mapping[str, object],
    material: Mapping[str, object] | None = None,
    preparation: Mapping[str, object] | None = None,
    parent_ref: str | None = None,
    task_before: dict[str, object] | None = None,
    actor: tuple[str, str] | None = None,
    event_id: str | None = None,
) -> LifecycleResult:
    """Store the one real prepared request (transport, choice and basis apart).

    The input is the frozen :meth:`decision.DecisionClient.request_prepared`
    result plus the schema-3 ``material``/``preparation`` layers it was prepared
    from. It is *not* an approval: ``available``/``attempts`` are wire facts,
    ``business_decisions``/``choice`` are the single business decision, and a
    transport success with zero business decisions is recorded as a refusal
    (its frozen ``reason``, no choice, no basis). A replayed result records no
    new business decision and no transport attempt.

    Basis provenance is re-checked through :mod:`decision_points` (the single
    preparation authority) and the catalogue digest is recorded, so a reader can
    join this row back to the exact prepared revision. ``basis_text`` is stored
    whole or refused - never clipped.
    """
    if not isinstance(meta, DecisionMeta):
        _refuse("meta", "expected a DecisionMeta")
    decision_id = _check_decision_id("decision_id", decision_id)
    fields = _request_fields(result)
    try:
        decision_points.require_active_dp(str(fields["dp"]))
    except decision.DecisionInputError:
        _refuse("dp", "is not an active eight-entry decision point")
    if not decision_id.startswith(str(fields["dp"]) + ":"):
        _refuse("dp", "does not match the decision_id prefix")
    basis_catalog_sha256: str | None = None
    basis_text: str | None = None
    if fields["business_decisions"] == 1:
        basis_catalog_sha256 = _preparation_provenance(store, fields, material, preparation)
        basis_text = _bounded_text(
            store, "basis_text", fields["basis_text"], decision_wire.BASIS_TEXT_BYTES
        )
    elif preparation is not None:
        # A refused request can still cite the preparation it attempted; only
        # the stamp is provable without the material, and no basis is adopted.
        if not isinstance(preparation, Mapping):
            _refuse("preparation", f"expected the prepared object {list(decision_points.PREPARATION_KEYS)}")
        if preparation.get("prepared_at") != fields["prepared_at"]:
            _refuse("prepared_at", "must be the preparation's recorded prepared_at")
    actor = _check_actor(actor)
    start, events = _ledger_facts(store, meta)
    before = _check_before(start, task_before)
    parent_ref = _check_parent_ref(parent_ref, decision_id, meta, events)
    if event_id is not None:
        event_id = _check_token("event_id", event_id)
    else:
        event_id = _stable_event_id(
            "rq", meta.logical_id, str(fields["dp"]), parent_ref or "-"
        )
    for field, value in (
        ("key", meta.key),
        ("task_key", meta.task_key),
        ("logical_id", meta.logical_id),
        ("retry_of", meta.retry_of),
        ("decision_id", decision_id),
        ("choice", fields["choice"] if isinstance(fields["choice"], str) else None),
        ("basis_id", fields["basis_id"] if isinstance(fields["basis_id"], str) else None),
        ("parent_ref", parent_ref),
        ("event_id", event_id),
    ):
        _guard_secret(store, field, value)

    scope = store._scope(
        decision_id=decision_id,
        dp=str(fields["dp"]),
        key=meta.key,
        task_key=meta.task_key,
        actor=actor,
    )
    event = decision_wire.request_event(
        scope,
        logical_id=meta.logical_id,
        dp=str(fields["dp"]),
        available=bool(fields["available"]),
        replayed=bool(fields["replayed"]),
        choice=fields["choice"] if isinstance(fields["choice"], str) else None,
        basis_id=fields["basis_id"] if isinstance(fields["basis_id"], str) else None,
        basis_text=basis_text,
        basis_source=fields["basis_source"] if isinstance(fields["basis_source"], str) else None,
        prepared_at=str(fields["prepared_at"]),
        basis_catalog_sha256=basis_catalog_sha256,
        business_decisions=int(fields["business_decisions"]),
        transport_attempts=int(fields["transport_attempts"]),
        attempts=int(fields["attempts"]),
        reason=fields["reason"] if isinstance(fields["reason"], str) else None,
        parent_ref=parent_ref,
        task_before=before,
        event_id=event_id,
    )
    return _append(
        store, meta, stage="request", scope=scope, event=event, decision_id=decision_id
    )


def record_terminal(
    store: LifecycleStore,
    meta: DecisionMeta,
    *,
    decision_id: str,
    terminal: str,
    reason: str,
    task_after: dict[str, object] | None,
    evidence: str | None = None,
    parent_ref: str | None = None,
    actor: tuple[str, str] | None = None,
    event_id: str | None = None,
) -> LifecycleResult:
    """Store this task's real terminal observation (never derived from settled).

    The stamp is the producer's own ``observed_at``, it must not precede the
    creation fact's before snapshot nor any already recorded after snapshot, and
    the real reason is required. A terminal fact does not close the key, phase,
    claim or sign-off: a ``settled`` row alone never produces one.
    """
    if not isinstance(meta, DecisionMeta):
        _refuse("meta", "expected a DecisionMeta")
    if terminal not in TASK_TERMINALS:
        _refuse("terminal", f"expected one of {TASK_TERMINALS}")
    if meta.task_key is None:
        _refuse("task_key", "a task terminal requires an associated task")
    decision_id = _check_decision_id("decision_id", decision_id)
    note = _bounded_text(store, "reason", reason, decision_wire.REASON_LIMIT)
    evidence_text: str | None = None
    if evidence is not None:
        # Same bound the managed store applies to ``lifecycle.evidence``: the
        # value is refused over the limit, never silently clipped afterwards.
        evidence_text = _bounded_text(
            store, "evidence", evidence, decision_wire.METADATA_TEXT_LIMIT
        )
    after = decision_task_state.validate_task_state(task_after)
    if after is None:
        _refuse("task_after", "a task terminal requires the real post observation")
    actor = _check_actor(actor)
    start, events = _ledger_facts(store, meta)
    try:
        stored_before = decision_task_state.validate_task_state(start.get("task_before"))
        decision_task_state.validate_observation_order(stored_before, after)
        for row in events:
            if row.get("logical_id") != meta.logical_id:
                continue
            prior = decision_task_state.validate_task_state(row.get("task_after"))
            if prior is not None:
                decision_task_state.validate_observation_order(prior, after)
    except decision_task_state.TaskStateInputError as exc:
        raise LifecycleInputError(str(exc)) from None
    parent_ref = _check_parent_ref(parent_ref, decision_id, meta, events)
    if event_id is not None:
        event_id = _check_token("event_id", event_id)
    else:
        event_id = _stable_event_id("tm", meta.logical_id, terminal)
    for field, value in (
        ("key", meta.key),
        ("task_key", meta.task_key),
        ("logical_id", meta.logical_id),
        ("retry_of", meta.retry_of),
        ("decision_id", decision_id),
        ("parent_ref", parent_ref),
        ("event_id", event_id),
    ):
        _guard_secret(store, field, value)

    scope = store._scope(
        decision_id=decision_id, key=meta.key, task_key=meta.task_key, actor=actor
    )
    event = decision_wire.terminal_event(
        scope,
        logical_id=meta.logical_id,
        terminal=terminal,
        reason=note,
        evidence=evidence_text,
        parent_ref=parent_ref,
        task_after=after,
        event_id=event_id,
    )
    return _append(
        store, meta, stage="terminal", scope=scope, event=event, decision_id=decision_id
    )


# ---------------------------------------------------------------------------
# Read side (the same managed ledger)
# ---------------------------------------------------------------------------


def read_lifecycle(
    store: LifecycleStore, *, offset: int = 0
) -> decision_wire.ReadResult:
    """Read valid schema-v1 rows from the lifecycle ledger (tolerant, no writes).

    A damaged row is counted in ``ReadResult.stats``; an unreadable ledger
    raises (``OSError``) instead of returning an empty result, because "cannot
    read" must never look like "nothing recorded".
    """
    _refuse_link(store.sink, "sink")
    return decision_wire.read_events(store.sink, offset=offset)


def versioned_logical_ids(
    events: Sequence[Mapping[str, object]],
) -> frozenset[str]:
    """Logical ids whose ``record-start`` fact declares this record version.

    This is the *only* legacy test for a stored record: a missing wire row, a
    failed capture or a missing lifecycle stage never makes a v2 record legacy,
    and no row without the creation fact becomes v2.
    """
    found: set[str] = set()
    for event in events:
        if not isinstance(event, Mapping):
            continue
        if event.get("kind") != "record-start":
            continue
        version = event.get("record_version")
        if isinstance(version, bool) or not isinstance(version, int):
            continue
        if version < RECORD_VERSION:
            continue
        logical_id = event.get("logical_id")
        if isinstance(logical_id, str) and logical_id:
            found.add(logical_id)
    return frozenset(found)
