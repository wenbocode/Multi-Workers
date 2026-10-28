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

Safety
------
Every structural string this writer owns is checked against the injected
known-secret redactor and refused (never echoed) when it matches; free text is
redacted and clipped by the managed store. No credential discovery happens in
this module: the redactor is injected by the caller.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

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
    ) -> "DecisionMeta":
        """Create the meta of one real decision (one fresh ``logical_id``)."""
        return cls(
            key=key,
            logical_id=logical_id if logical_id is not None else decision_wire.new_id(),
            initiator_role=initiator_role,
            task_key=task_key,
            retry_of=retry_of,
            record_version=record_version,
        )

    def as_meta(self) -> dict[str, object]:
        """The exact local meta mapping, in ``META_KEYS`` order."""
        return {
            "record_version": self.record_version,
            "logical_id": self.logical_id,
            "key": self.key,
            "task_key": self.task_key,
            "initiator_role": self.initiator_role,
            "retry_of": self.retry_of,
        }

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
        unknown = [key for key in raw if key not in META_KEYS]
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
