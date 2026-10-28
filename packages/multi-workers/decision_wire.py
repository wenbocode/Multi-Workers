"""Append-only side ledger for real decision transport capture.

This module is the single writer for the decision side ledger (design D-002):
``.agenticdoc/_autopilot/decisions-wire.jsonl`` in production and an explicit
test sink (``<decide-test>/wire.jsonl``) for observe-only submissions. It never
touches the frozen archive row shape, the signoff snapshot key set or any
authority file, so decision idempotency and ``rows_sha256`` cannot move.

Contract for the wiring cards (T03/T05/T06/T07)

* ``WireScope`` - one explicit scope per logical unit (decision / submission).
  It carries the sink, project identity, origin, decision/dp/key/task ids, the
  injected secret redactor and the capture caps. ``scope_kind="test"`` sinks
  (and test evidence paths) must not resolve into the production tree - both
  the given and the symlink/junction-resolved path are checked - and are
  fail-closed, refused otherwise. ``project_id_for`` is realpath/case canonical
  so one control root has one identity however it is addressed.
* ``CallState`` - one per logical ``DecisionClient.decide`` (``new_call()``).
  ``call_id`` is a UUID4 hex id created *here*, never by the transport hook;
  ``CallState.next_attempt()`` is the only source of ``attempt_index``.
* ``use(scope, call)`` / ``scope_context`` / ``call_context`` - bind the pair
  through a ``ContextVar``. The variable is only an in-process transport, not
  an inheritance promise: ``None`` (or a missing binding in a worker thread)
  means zero writes. Probe paths that never bind a scope stay silent.
* ``scope.capture(raw)`` - decode, redact, byte-truncate, scrub a secret split
  at either boundary and hash the *stored* text. A missing redactor is
  fail-closed: the text is omitted (``text_omitted=True``) and only metadata is
  kept, never the raw bytes. The boundary scrub checks every secret's full
  length against the whole stored text (no fixed tail window) and also removes
  1-3 character leftovers, marking the row with ``boundary_scrubbed``.
* ``build_event`` + the ``*_event`` builders produce schema v1 rows. Free-text
  metadata (``url_path``/``model``/``error_detail``/``reason``/``answer``/
  ``evidence``/``issues``/``truncated`` and the nested ``usage``/``policy``
  containers) is redacted first and clipped second, exactly like capture text;
  without a redactor those values are omitted instead of being persisted
  unproven. Mapping *keys* inside ``usage``/``policy`` are caller/endpoint text
  too, so they take the same redact -> clip -> boundary-scrub path (a credential
  used as a usage key is still a credential). The documented token counters
  (``USAGE_COUNTER_KEYS``) stay verbatim so counting keeps working; two keys
  that sanitize to the same name, or onto a counter label, are all dropped
  instead of overwriting each other (fail-closed conflict policy: a merged
  entry would fabricate a usage number). Identity/enum fields (ids,
  ``kind``/``status``/``mode``/``intent``/``outcome``/``archive`` ...) are never
  rewritten, so ledger joins stay stable. Unknown field keys raise (a typo must
  not become a silent null).
  ``append_event`` serialises, fits the 64 KiB line budget, then appends under a
  short lock budget with tail-newline repair, a short-write loop and fsync.
  It never raises: the first failure of a logical unit (a ``call_id``, or the
  scope itself for call-less events) opens a breaker, so the remaining events
  of that unit fail immediately instead of spending the lock budget again.
  Failures aggregate into one warning per logical call and are reported through
  ``WriteResult`` / ``scope.capture_status``; the caller's business result is
  never changed.
* ``read_events`` - tolerant incremental reader (bad JSON, bad UTF-8, unknown
  schema, oversized line, half line, rotation) for the history fold.

Field naming follows design §4.4 plus the RQ5 corrections: a capture is a nested
``{"text", "encoding", "wire_len", "stored_len", "captured_redacted_sha256",
"redactions", "truncated", "read_capped", "boundary_scrubbed",
"decode_errors", "text_omitted", "byte_exact"}`` object under
``request`` / ``response`` / ``book``. ``wire_len`` is the real wire byte count,
``stored_len`` and ``captured_redacted_sha256`` describe only what was stored.

Additive T02 extension (decision lifecycle, design D004 §4.1/§4.2):

* ``record-start`` - the immutable creation fact of a decision record:
  ``logical_id`` + ``record_version`` + ``initiator_role`` + nullable
  ``retry_of`` (with ``key``/``task_key`` on the common fields). It is written
  before the transport call, so a failed capture is still a v2 record and a
  missing wire row never means "legacy".
* ``lifecycle`` rows gained the structural ``logical_id``, ``action`` (executed
  label), ``outcome`` (settled vocabulary) and ``evidence_path`` /
  ``evidence_sha256`` (the written signoff file). Closed-set/validated values
  stay structural: no state is smuggled through ``reason``/``result`` prose.
* ``lifecycle-error`` - the independent failure fact for a lifecycle write, so
  a reader can show "feedback failed" without pretending the feedback row
  exists (free text ``detail`` is redacted like every other prose field).
* ``append_event(..., dedupe_event_id=True)`` - idempotent append: the event id
  is looked up *inside the append lock* and a hit writes nothing
  (``status="duplicate"``). Deduplication is by ``event_id`` only, never by
  ``(decision_id, kind word)``: two real actions stay two rows.
"""
from __future__ import annotations

import contextlib
import copy
import datetime
import hashlib
import json
import os
import pathlib
import re
import sys
import time
import uuid
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Protocol

import mw_common
import decision_task_state

SCHEMA_VERSION = 1

LINE_CAP_BYTES = 64 * 1024
SEGMENT_CAP_BYTES = 24 * 1024
READ_WINDOW_BYTES = 4 * 1024
READER_LINE_CAP_BYTES = 1024 * 1024
READER_CHUNK_BYTES = 64 * 1024
# Any non-empty secret prefix left by a cut is scrubbed: leaving 1-3 characters
# of a credential on disk is still a credential leak (design §9 fail-closed).
MIN_SCRUB_PREFIX = 1
# Generic cap for free-text metadata that has no field-specific limit declared.
METADATA_TEXT_LIMIT = 512

LOCK_BUDGET_S = 0.25
LOCK_RETRIES = 5
LOCK_BASE_DELAY = 0.008

SCOPE_KINDS = ("production", "test")
CAPTURE_STATUSES = ("ok", "partial", "failed")
#: ``duplicate`` means: the same ``event_id`` was already in the ledger under
#: the append lock, so nothing was written (T02 lock-scoped idempotency).
WRITE_STATUSES = ("written", "failed", "skipped", "duplicate")
#: A caller-supplied ``event_id`` (the idempotency key) must be one ledger
#: token: no quotes/whitespace, so the duplicate scan can search the exact JSON
#: needle instead of inventing a fuzzy match.
EVENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}$")

# Metadata mapping keys are untrusted text as well (N-1): an endpoint (or a
# compromised one) can put a credential in a ``usage``/``policy`` key, which
# used to pass through as if it were a schema label. Keys therefore take the
# same redact -> clip -> boundary-scrub path as values, with three constraints:
#
# * ``USAGE_COUNTER_KEYS`` is the documented closed set of token counters
#   (``usage.py`` consumes exactly these). A closed-set label is structural: it
#   is never redacted and never overwritten by a sanitized key, so normal token
#   counting keeps working. The single exception is a label that is itself a
#   known credential: then the entry is dropped (AC-005 outranks counting).
# * Any other key is caller text. Without a redactor it cannot be proven safe,
#   so the entry is withheld entirely (not kept with a null value), exactly like
#   free-text values.
# * When two sanitized keys collide (including onto a counter label) every
#   colliding entry is dropped. A dict overwrite would attribute one number to
#   another key and fabricate a usage fact nobody sent (VC-016
#   fabricated_usage=0); dropping loses metadata, never invents it.
METADATA_KEY_LIMIT = 128
#: A metadata *key* clip may leave a strict prefix of a known value as its tail.
#: Only a fragment this long is a usable secret fragment: shorter tails are not
#: secrets (``decision._MIN_SECRET_LEN`` / ``_COVER_RESIDUAL_LEN`` use the same
#: floor) and scrubbing them renames fixed schema labels - ``observed_at`` ->
#: ``observed_a``, ``completed`` -> ``complete`` - which the read side then
#: rejects as an invalid snapshot instead of showing the recorded state.
METADATA_KEY_MIN_SCRUB = 4
MAX_METADATA_DEPTH = 8
USAGE_COUNTER_KEYS = frozenset(
    {
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
    }
)
_NO_CLOSED_KEYS: frozenset[str] = frozenset()
# Fields with a documented key schema may keep their labels through redaction.
# ``policy`` intentionally has no closed set until its producer (T05) pins one.
_FIELD_CLOSED_KEYS: dict[str, frozenset[str]] = {"usage": USAGE_COUNTER_KEYS}

URL_PATH_LIMIT = 512
CONTENT_TYPE_LIMIT = 128
ERROR_CLASS_LIMIT = 64
ERROR_DETAIL_LIMIT = 512
MODEL_LIMIT = 128
REASON_LIMIT = 512
HEADER_NAME_LIMIT = 128
HEADER_NAME_COUNT = 32

_ATTEMPT_CALL_REQUIRED = frozenset({"attempt-start", "attempt-end", "call-end"})

_KIND_FIELDS: dict[str, tuple[str, ...]] = {
    "attempt-start": (
        "attempt_index",
        "method",
        "url_path",
        "model",
        "timeout_s",
        "header_names",
        "request",
    ),
    "attempt-end": (
        "attempt_index",
        "latency_ms",
        "http_status",
        "content_type",
        "retry_after_s",
        "error_class",
        "error_detail",
        "usage",
        "usage_source",
        "response",
    ),
    "call-end": (
        "attempts",
        "wire_attempts",
        "latency_ms",
        "available",
        "reason",
        "answers_present",
        "confidence",
        "confidence_source",
        "transport",
        "model",
        "policy",
        "zero_call",
    ),
    "decision-end": (
        "status",
        "escalated_reason",
        "archive",
        "state_digest",
        "questions_version",
        "truncated",
        "mode",
        "intent",
        "book_ref",
    ),
    "submission-start": ("dp", "outcome", "issues", "retry_of", "zero_call", "book_ref"),
    "submission-end": ("dp", "outcome", "issues", "retry_of", "zero_call", "book_ref"),
    "lifecycle": (
        "lifecycle",
        "logical_id",
        "target",
        "supersedes",
        "action",
        "outcome",
        "reason",
        "answer",
        "evidence",
        "result",
        "evidence_path",
        "evidence_sha256",
        "snapshot_sha256",
        "task_after",
    ),
    "lifecycle-error": (
        "logical_id",
        "stage",
        "error_class",
        "attempted_event_id",
        "detail",
    ),
    "record-start": ("logical_id", "record_version", "initiator_role", "retry_of", "task_before"),
    "book-snapshot": ("book_ref", "book", "file_sha256", "book_sha256", "book_version"),
}
EVENT_KINDS = frozenset(_KIND_FIELDS)

_COMMON_FIELDS = (
    "schema_version",
    "event_id",
    "ts",
    "kind",
    "scope",
    "project_id",
    "key",
    "task_key",
    "decision_id",
    "call_id",
    "submission_id",
    "origin",
    "actor",
    "answer_source",
    "capture_status",
)

_PRODUCTION_SINK_PARTS = (".agenticdoc", "_autopilot", "decisions-wire.jsonl")
_PRODUCTION_LIFECYCLE_PARTS = (".agenticdoc", "_autopilot", "decision-lifecycle.jsonl")
_TEST_EVIDENCE_NAME = "evidence.jsonl"
_TEST_LIFECYCLE_NAME = "lifecycle.jsonl"

# Windows os.open defaults to text mode, which would rewrite "\n" as "\r\n".
# The ledger is UTF-8 + LF only (repo P-040): always ask for binary.
_BINARY_FLAG = getattr(os, "O_BINARY", 0)


class WireScopeError(ValueError):
    """A scope/event contract violation (programmer error, fail-closed)."""


class SecretRedactor(Protocol):
    """Injected redaction contract (decision.py owns the production heuristics)."""

    def redact(self, text: str) -> "Redaction": ...

    def scrub_tail_prefix(self, text: str, window: int | None = None) -> tuple[str, bool]: ...


@dataclass(frozen=True)
class Redaction:
    """Redacted text plus the number of substitutions actually made."""

    text: str
    hits: int = 0


@dataclass(frozen=True)
class SubstringRedactor:
    """Exact-value redaction plus a secret-prefix scrub at a cut boundary.

    Only values the caller proves are secret go in ``secrets`` (the
    ``Authorization`` value, ``cfg.extras.api_key``, the resolved timi key, the
    known env values). This class deliberately does not guess from entropy:
    callers may wrap it to add the existing ``Bearer``/``sk-`` regex layers.
    """

    secrets: Sequence[str] = ()
    placeholder: str = "<redacted>"
    min_prefix: int = MIN_SCRUB_PREFIX

    def __post_init__(self) -> None:
        raw = (self.secrets,) if isinstance(self.secrets, str) else tuple(self.secrets)
        cleaned = sorted(
            {value for value in raw if isinstance(value, str) and value and value != self.placeholder},
            key=len,
            reverse=True,
        )
        object.__setattr__(self, "secrets", tuple(cleaned))

    def redact(self, text: str) -> Redaction:
        hits = 0
        for secret in self.secrets:
            found = text.count(secret)
            if found:
                hits += found
                text = text.replace(secret, self.placeholder)
        return Redaction(text=text, hits=hits)

    def scrub_tail_prefix(self, text: str, window: int | None = None) -> tuple[str, bool]:
        """Drop every trailing *partial* secret left by a read/segment cut.

        A full secret is already replaced by :meth:`redact`; only a strict
        prefix can survive a cut. The scan is over the *whole* stored text and
        tries each secret's full length down to ``min_prefix``, because a fixed
        tail window cannot prove anything about a secret longer than the window
        (design §9). The removal is marked by the caller through
        ``Capture.boundary_scrubbed``.

        ``window`` is accepted only for signature compatibility with earlier
        callers and is ignored: a bounded window is exactly the defect this
        replaces. Cost is O(sum(len(secret))) per call.
        """
        del window  # deliberately unused; see the docstring
        if not text or not self.secrets:
            return text, False
        best = 0
        for secret in self.secrets:
            limit = min(len(secret) - 1, len(text))
            if limit < self.min_prefix:
                continue
            for size in range(limit, self.min_prefix - 1, -1):
                if size <= best:
                    break
                if text.endswith(secret[:size]):
                    best = size
                    break
        if best <= 0:
            return text, False
        return text[: len(text) - best], True


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _hash_text(text: str | None, encoding: str | None) -> tuple[int, str | None]:
    if text is None:
        return 0, None
    data = text.encode(encoding or "utf-8")
    return len(data), _sha256_hex(data)


@dataclass(frozen=True)
class Capture:
    """What was actually stored for one boundary (request / response / book)."""

    text: str | None
    encoding: str | None
    wire_len: int | None
    stored_len: int
    captured_redacted_sha256: str | None
    redactions: int = 0
    truncated: bool = False
    read_capped: bool = False
    boundary_scrubbed: bool = False
    decode_errors: bool = False
    text_omitted: bool = False

    @property
    def byte_exact(self) -> bool:
        """True only when the stored text is the wire text, untouched."""
        return (
            self.text is not None
            and not self.text_omitted
            and self.redactions == 0
            and not self.truncated
            and not self.read_capped
            and not self.boundary_scrubbed
            and not self.decode_errors
        )

    @property
    def status(self) -> str:
        if self.text is None or self.text_omitted:
            return "failed"
        return "ok" if self.byte_exact else "partial"

    def as_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "encoding": self.encoding,
            "wire_len": self.wire_len,
            "stored_len": self.stored_len,
            "captured_redacted_sha256": self.captured_redacted_sha256,
            "redactions": self.redactions,
            "truncated": self.truncated,
            "read_capped": self.read_capped,
            "boundary_scrubbed": self.boundary_scrubbed,
            "decode_errors": self.decode_errors,
            "text_omitted": self.text_omitted,
            "byte_exact": self.byte_exact,
        }

    @classmethod
    def not_recorded(
        cls, *, wire_len: int | None, read_capped: bool = False, decode_errors: bool = False
    ) -> "Capture":
        """Metadata-only capture: no redactor, therefore no text (fail-closed)."""
        return cls(
            text=None,
            encoding=None,
            wire_len=wire_len,
            stored_len=0,
            captured_redacted_sha256=None,
            read_capped=read_capped,
            decode_errors=decode_errors,
            text_omitted=True,
        )


def _decode_wire(data: bytes) -> tuple[str, str, bool]:
    """Strict UTF-8, else a lossless latin-1 byte view (RQ5: no ``replace``)."""
    try:
        return data.decode("utf-8"), "utf-8", False
    except UnicodeDecodeError:
        return data.decode("latin-1"), "latin-1", True


def _trim_to_bytes(text: str, encoding: str, cap: int) -> tuple[str, bytes, bool]:
    data = text.encode(encoding)
    if len(data) <= cap:
        return text, data, False
    trimmed = data[:cap].decode(encoding, errors="ignore")
    return trimmed, trimmed.encode(encoding), True


def _clip_text(value: object, limit: int) -> str | None:
    if value is None:
        return None
    text = str(value)
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    return data[:limit].decode("utf-8", errors="ignore")


def project_id_for(control_root: pathlib.Path | str) -> str:
    """Stable, case/relative/symlink independent local project identity (no secret)."""
    normalized = os.path.normcase(
        os.path.realpath(os.path.abspath(str(control_root)))
    )
    return _sha256_hex(normalized.encode("utf-8"))[:16]


def _is_production_ledger(path: pathlib.Path) -> bool:
    parts = tuple(path.parts[-3:])
    return parts in (_PRODUCTION_SINK_PARTS, _PRODUCTION_LIFECYCLE_PARTS)


def canonical_path(path: pathlib.Path | str) -> pathlib.Path:
    """Absolute, symlink/junction-resolved form (no traversal, no mkdir).

    ``realpath`` resolves every existing ancestor and leaves a non-existent
    final component in place, so validating a sink that does not exist yet
    still resolves the directory that would be created.
    """
    return pathlib.Path(os.path.realpath(os.path.abspath(str(path))))


def _is_inside_agenticdoc(path: pathlib.Path) -> bool:
    return any(part == ".agenticdoc" for part in path.parts)



@dataclass
class WireScope:
    """One explicit capture scope (production decision or isolated test run)."""

    sink: pathlib.Path
    project_id: str
    scope_kind: str = "production"
    origin: str = "unknown"
    decision_id: str | None = None
    dp: str | None = None
    key: str | None = None
    task_key: str | None = None
    submission_id: str | None = None
    evidence_path: pathlib.Path | None = None
    actor_kind: str | None = None
    actor_id: str | None = None
    redact: SecretRedactor | None = None
    fail_closed: bool | None = None
    line_cap: int = LINE_CAP_BYTES
    segment_cap: int = SEGMENT_CAP_BYTES
    read_window: int = READ_WINDOW_BYTES
    lock_budget_s: float = LOCK_BUDGET_S
    lock_retries: int = LOCK_RETRIES
    lock_base_delay: float = LOCK_BASE_DELAY
    warn: Callable[[str], None] | None = None
    errors: list[dict[str, object]] = field(default_factory=list)
    last_call_id: str | None = None
    _warned: set[str] = field(default_factory=set)
    _failed_units: set[str] = field(default_factory=set)
    _writes_ok: int = 0
    _writes_partial: int = 0
    _writes_failed: int = 0
    _tail_repaired: int = 0

    def __post_init__(self) -> None:
        if self.sink is None:
            raise WireScopeError("WireScope requires an explicit sink (production or test)")
        self.sink = pathlib.Path(self.sink)
        if not isinstance(self.project_id, str) or not self.project_id.strip():
            raise WireScopeError("WireScope requires a non-empty project_id")
        if self.scope_kind not in SCOPE_KINDS:
            raise WireScopeError(
                f"scope_kind must be one of {SCOPE_KINDS}, got {self.scope_kind!r}"
            )
        if self.scope_kind == "test":
            self._refuse_production_paths(self.sink)
            if self.evidence_path is not None:
                self._refuse_production_paths(self.evidence_path)
            if self.fail_closed is None:
                self.fail_closed = True
        elif self.fail_closed is None:
            self.fail_closed = False
        if self.line_cap < 1:
            raise WireScopeError(f"line_cap must be >= 1, got {self.line_cap!r}")
        if self.segment_cap < 1:
            raise WireScopeError(f"segment_cap must be >= 1, got {self.segment_cap!r}")
        if self.read_window < 0:
            raise WireScopeError(f"read_window must be >= 0, got {self.read_window!r}")
        if self.lock_budget_s <= 0:
            raise WireScopeError(f"lock_budget_s must be > 0, got {self.lock_budget_s!r}")
        if self.evidence_path is not None:
            self.evidence_path = pathlib.Path(self.evidence_path)
        self.fail_closed = bool(self.fail_closed)

    @staticmethod
    def _refuse_production_paths(path: pathlib.Path) -> None:
        """Fail closed when a test write target *resolves* into production.

        Path parts alone miss a symlink/junction whose target is
        ``<control>/.agenticdoc/_autopilot``: the accidental (or misconfigured)
        layout has no ``.agenticdoc`` component but still writes the production
        ledger. Both the given and the canonical path must be isolated. This is
        a lookup only - nothing is created, so a missing final file stays
        missing.
        """
        given = pathlib.Path(path)
        canonical = canonical_path(given)
        for candidate in (given, canonical):
            if _is_production_ledger(candidate) or _is_inside_agenticdoc(candidate):
                raise WireScopeError(
                    f"test scope refuses the production path {candidate} (resolved from "
                    f"{given}); pass an isolated test root"
                )

    # -- capture ----------------------------------------------------------

    def capture(self, raw: bytes | bytearray | memoryview | str | None) -> Capture | None:
        """Capture one wire boundary; ``None`` input means "not recorded"."""
        if raw is None:
            return None
        if isinstance(raw, str):
            data = raw.encode("utf-8")
        elif isinstance(raw, (bytes, bytearray, memoryview)):
            data = bytes(raw)
        else:
            raise WireScopeError(f"unsupported capture input {type(raw).__name__}")

        wire_len = len(data)
        head_cap = self.segment_cap + self.read_window
        read_capped = wire_len > head_cap
        head = data[:head_cap]
        text, encoding, decode_errors = _decode_wire(head)

        if self.redact is None:
            return Capture.not_recorded(
                wire_len=wire_len, read_capped=read_capped, decode_errors=decode_errors
            )

        redaction = self.redact.redact(text)
        text = redaction.text
        boundary_scrubbed = False
        if read_capped:
            text, scrubbed = self.redact.scrub_tail_prefix(text)
            boundary_scrubbed = boundary_scrubbed or scrubbed
        text, full_bytes, truncated = _trim_to_bytes(text, encoding, self.segment_cap)
        text, scrubbed = self.redact.scrub_tail_prefix(text)
        boundary_scrubbed = boundary_scrubbed or scrubbed
        stored_len, sha = _hash_text(text, encoding)
        return Capture(
            text=text,
            encoding=encoding,
            wire_len=wire_len,
            stored_len=stored_len,
            captured_redacted_sha256=sha,
            redactions=redaction.hits,
            truncated=truncated or len(full_bytes) > self.segment_cap,
            read_capped=read_capped,
            boundary_scrubbed=boundary_scrubbed,
            decode_errors=decode_errors,
            text_omitted=False,
        )

    # -- failure aggregation ---------------------------------------------

    def scrub_text(self, text: str) -> str:
        if self.redact is None:
            return "<unavailable>"
        return self.redact.redact(text).text

    def note_error(
        self, error_class: str, message: str, *, call_id: str | None = None
    ) -> None:
        """Record one failure; warn at most once per logical call (no storm)."""
        self.errors.append(
            {"error_class": error_class, "message": message, "call_id": call_id}
        )
        key = call_id or "<scope>"
        if key in self._warned:
            return
        self._warned.add(key)
        line = f"decision-wire: {error_class}: {message} (call {call_id or '-'})"
        try:
            if self.warn is not None:
                self.warn(line)
            else:
                sys.stderr.write(line + "\n")
        except Exception:  # noqa: BLE001 - a warning sink must not break the caller
            pass

    @property
    def capture_status(self) -> str | None:
        """Aggregated status: ``failed`` > ``partial`` > ``ok``, ``None`` = nothing."""
        if self._writes_failed:
            return "failed"
        if self._writes_partial:
            return "partial"
        if self._writes_ok:
            return "ok"
        return None

    def _record_write(self, status: str | None, *, tail_repaired: bool) -> None:
        if status == "failed":
            self._writes_failed += 1
        elif status == "partial":
            self._writes_partial += 1
        else:
            self._writes_ok += 1
        if tail_repaired:
            self._tail_repaired += 1


# -- sinks -----------------------------------------------------------------

def production_wire_sink(control_root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(control_root).joinpath(*_PRODUCTION_SINK_PARTS)


def production_lifecycle_sink(control_root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(control_root).joinpath(*_PRODUCTION_LIFECYCLE_PARTS)


def test_wire_sink(test_root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(test_root) / "wire.jsonl"


def test_lifecycle_sink(test_root: pathlib.Path | str) -> pathlib.Path:
    """Isolated lifecycle ledger for one test run (matches the history reader)."""
    return pathlib.Path(test_root) / _TEST_LIFECYCLE_NAME


def test_evidence_sink(test_root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(test_root) / _TEST_EVIDENCE_NAME


def production_scope(
    control_root: pathlib.Path | str,
    *,
    project_id: str | None = None,
    origin: str = "unknown",
    decision_id: str | None = None,
    dp: str | None = None,
    key: str | None = None,
    task_key: str | None = None,
    actor_kind: str | None = None,
    actor_id: str | None = None,
    redact: SecretRedactor | None = None,
    warn: Callable[[str], None] | None = None,
) -> WireScope:
    root = pathlib.Path(control_root)
    return WireScope(
        sink=production_wire_sink(root),
        project_id=project_id or project_id_for(root),
        scope_kind="production",
        origin=origin,
        decision_id=decision_id,
        dp=dp,
        key=key,
        task_key=task_key,
        actor_kind=actor_kind,
        actor_id=actor_id,
        redact=redact,
        warn=warn,
    )


def test_scope(
    test_root: pathlib.Path | str,
    *,
    project_id: str,
    submission_id: str,
    origin: str = "test-submission",
    dp: str | None = None,
    key: str | None = None,
    task_key: str | None = None,
    evidence_path: pathlib.Path | str | None = None,
    redact: SecretRedactor | None = None,
    warn: Callable[[str], None] | None = None,
) -> WireScope:
    root = pathlib.Path(test_root)
    return WireScope(
        sink=test_wire_sink(root),
        project_id=project_id,
        scope_kind="test",
        origin=origin,
        dp=dp,
        key=key,
        task_key=task_key,
        submission_id=submission_id,
        evidence_path=pathlib.Path(evidence_path) if evidence_path is not None else test_evidence_sink(root),
        redact=redact,
        warn=warn,
    )


# -- call state and context -------------------------------------------------

def new_id() -> str:
    return uuid.uuid4().hex


@dataclass
class CallState:
    """One logical ``client.decide``; owns the call id and attempt numbering."""

    call_id: str = field(default_factory=new_id)
    attempts_started: int = 0
    started_ms: float = field(default_factory=time.monotonic)

    def next_attempt(self) -> int:
        self.attempts_started += 1
        return self.attempts_started

    def ensure_attempt(self, index: int) -> int:
        if index > self.attempts_started:
            self.attempts_started = index
        return index


def new_call() -> CallState:
    return CallState()


_CALL: ContextVar[CallState | None] = ContextVar("decision_wire_call", default=None)
_SCOPE: ContextVar[WireScope | None] = ContextVar("decision_wire_scope", default=None)


def current_call() -> CallState | None:
    return _CALL.get()


def current_scope() -> WireScope | None:
    return _SCOPE.get()


@contextlib.contextmanager
def scope_context(scope: WireScope) -> Iterator[WireScope]:
    token = _SCOPE.set(scope)
    try:
        yield scope
    finally:
        _SCOPE.reset(token)


@contextlib.contextmanager
def call_context(state: CallState | None = None) -> Iterator[CallState]:
    call = state if state is not None else new_call()
    token = _CALL.set(call)
    try:
        yield call
    finally:
        _CALL.reset(token)


@contextlib.contextmanager
def use(
    scope: WireScope, call: CallState | None = None
) -> Iterator[tuple[WireScope, CallState | None]]:
    """Bind scope (and optionally the call) for the duration of the block."""
    scope_token = _SCOPE.set(scope)
    call_token = _CALL.set(call) if call is not None else None
    try:
        yield scope, call
    finally:
        if call_token is not None:
            _CALL.reset(call_token)
        _SCOPE.reset(scope_token)


# -- event construction -----------------------------------------------------

def _now_ts() -> str:
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds")


def _coerce_capture(
    scope: WireScope, value: Capture | bytes | bytearray | memoryview | str | None
) -> Capture | None:
    if value is None or isinstance(value, Capture):
        return value
    return scope.capture(value)


def _capture_dict_status(capture: Mapping[str, object]) -> str:
    if capture.get("text") is None or capture.get("text_omitted"):
        return "failed"
    return "ok" if capture.get("byte_exact") else "partial"


def merge_capture_status(*statuses: str | None) -> str | None:
    """Worst-wins merge; ``None`` means "no capture to report"."""
    rank = {None: 0, "ok": 1, "partial": 2, "failed": 3}
    best: str | None = None
    for status in statuses:
        if rank.get(status, 0) > rank[best]:
            best = status
    return best


def _row_capture_status(row: Mapping[str, object]) -> str | None:
    statuses: list[str | None] = []
    for name in ("request", "response", "book"):
        capture = row.get(name)
        if isinstance(capture, Mapping):
            if capture.get("text") is None or capture.get("text_omitted"):
                statuses.append("failed")
            else:
                statuses.append("ok" if capture.get("byte_exact") else "partial")
    return merge_capture_status(*statuses)


# Free-text metadata per kind (P1-1). These are the only kind fields the store
# treats as caller prose: they are redacted first, then byte-clipped, and when
# the scope carries no redactor they are omitted instead of persisting text the
# store cannot prove secret-free. Mapping keys inside such a container are prose
# too (N-1) and follow the same rule. Every other kind field is structural:
# identifiers (call_id/decision_id/submission_id/book_ref/retry_of/target/
# supersedes), closed-set enums owned by the caller (kind/status/mode/intent/
# outcome/lifecycle/archive/usage_source/method), numbers or capture objects.
# Structural fields are never rewritten, which is what keeps ledger joins
# (project_id + decision_id + call_id + submission_id) stable across redaction.
_FREE_TEXT_FIELDS: dict[str, tuple[str, ...]] = {
    "attempt-start": ("url_path", "model", "header_names"),
    "attempt-end": ("content_type", "error_class", "error_detail", "usage"),
    "call-end": ("reason", "confidence_source", "transport", "model", "policy"),
    "decision-end": ("escalated_reason", "truncated"),
    "submission-start": ("issues",),
    "submission-end": ("issues",),
    "lifecycle": ("reason", "answer", "evidence", "result", "task_after"),
    "lifecycle-error": ("detail",),
    "record-start": ("task_before",),
    "book-snapshot": (),
}

_FREE_TEXT_LIMITS: dict[str, int] = {
    "url_path": URL_PATH_LIMIT,
    "model": MODEL_LIMIT,
    "content_type": CONTENT_TYPE_LIMIT,
    "error_class": ERROR_CLASS_LIMIT,
    "error_detail": ERROR_DETAIL_LIMIT,
    "reason": REASON_LIMIT,
    "escalated_reason": REASON_LIMIT,
    "transport": MODEL_LIMIT,
    "detail": ERROR_DETAIL_LIMIT,
}


def _sanitize_text(scope: WireScope, value: object, limit: int) -> str | None:
    """Redact, then byte-clip one free-text value (``None`` when unprovable)."""
    if value is None:
        return None
    if scope.redact is None:
        return None  # no redactor: the store cannot prove the text is safe
    text = scope.redact.redact(value if isinstance(value, str) else str(value)).text
    return _clip_text(text, limit)


def _sanitize_metadata_key(scope: WireScope, key: object) -> str | None:
    """Redact, clip and boundary-scrub one untrusted metadata mapping key.

    ``None`` means "withhold the whole entry": without a redactor nothing about
    a caller-chosen key is provable, and a non-string key is not a schema label
    either (JSON would silently coerce it). The clip is a cut boundary exactly
    like a capture cut, so a partial secret must not survive as the key's tail -
    but only a fragment of ``METADATA_KEY_MIN_SCRUB`` characters or more is a
    secret at all; a shorter tail is kept, because scrubbing it would rewrite
    ordinary labels (``observed_at``) instead of removing a leak.
    """
    if scope.redact is None or not isinstance(key, str):
        return None
    clipped = _clip_text(scope.redact.redact(key).text, METADATA_KEY_LIMIT)
    if not clipped:
        return None
    scrubbed, _scrubbed_flag = scope.redact.scrub_tail_prefix(clipped)
    if not scrubbed:
        return None
    trimmed = len(clipped) - len(scrubbed)
    if not clipped.startswith(scrubbed) or trimmed < METADATA_KEY_MIN_SCRUB:
        # Not a boundary cut of this key: keep the redacted, clipped label.
        return clipped
    return scrubbed


def _sanitize_mapping(
    scope: WireScope,
    value: Mapping[object, object],
    *,
    limit: int,
    depth: int,
    closed_keys: frozenset[str],
) -> dict[str, object]:
    """Sanitize a metadata mapping's keys *and* values (N-1).

    Closed-set labels are structural and win over any sanitized key. A
    sanitized key that collides with another sanitized key, or with a closed-set
    label, is dropped together with all of its peers: never an overwrite, never
    a fabricated value.
    """
    structural: dict[str, object] = {}
    untrusted: dict[str, list[object]] = {}
    order: list[str] = []
    for key, item in value.items():
        if isinstance(key, str) and key in closed_keys:
            # The label is structural, but only while it is not itself a known
            # credential: AC-005 (zero original occurrences) outranks token
            # counting in that pathological case.
            if scope.redact is not None and scope.redact.redact(key).hits:
                continue
            structural[key] = _sanitize_metadata(
                scope, item, limit=limit, depth=depth + 1, closed_keys=closed_keys
            )
            continue
        clean = _sanitize_metadata_key(scope, key)
        if clean is None:
            continue
        if clean not in untrusted:
            untrusted[clean] = []
            order.append(clean)
        untrusted[clean].append(item)
    for clean in order:
        items = untrusted[clean]
        if len(items) > 1 or clean in structural:
            continue  # fail-closed conflict: drop every colliding entry
        structural[clean] = _sanitize_metadata(
            scope, items[0], limit=limit, depth=depth + 1, closed_keys=closed_keys
        )
    return structural


def _sanitize_metadata(
    scope: WireScope,
    value: object,
    *,
    limit: int,
    depth: int = 0,
    closed_keys: frozenset[str] = _NO_CLOSED_KEYS,
) -> object:
    """Redact strings and mapping *keys* inside a metadata container.

    ``closed_keys`` names the labels that are schema, not caller text; it
    follows the container through nested mappings/lists so one field has one
    policy.
    """
    if isinstance(value, str):
        return _sanitize_text(scope, value, limit)
    if depth >= MAX_METADATA_DEPTH:
        return None
    if isinstance(value, Mapping):
        return _sanitize_mapping(
            scope, value, limit=limit, depth=depth, closed_keys=closed_keys
        )
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray, str)):
        return [
            _sanitize_metadata(
                scope, item, limit=limit, depth=depth + 1, closed_keys=closed_keys
            )
            for item in value
        ]
    return value


def _contains_text(value: object) -> bool:
    """True when a value carries at least one string leaf or mapping key."""
    if isinstance(value, str):
        return True
    if isinstance(value, Mapping):
        return any(
            isinstance(key, str) or _contains_text(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (bytes, bytearray)):
        return any(_contains_text(item) for item in value)
    return False


def _sanitize_free_text(scope: WireScope, name: str, value: object) -> object:
    """Apply the free-text policy to one kind field.

    With a redactor: redact (values *and* mapping keys), then clip. Without one:
    text is omitted (a mapping keeps only its closed-set structural entries, so
    numeric facts such as token counts survive and every untrusted key/value is
    withheld), because the store cannot prove any of it is safe.
    """
    if value is None:
        return None
    limit = _FREE_TEXT_LIMITS.get(name, METADATA_TEXT_LIMIT)
    closed_keys = _FIELD_CLOSED_KEYS.get(name, _NO_CLOSED_KEYS)
    if name == "header_names":
        if scope.redact is None:
            return None
        names: list[str] = []
        for item in list(value)[:HEADER_NAME_COUNT]:
            clipped = _sanitize_text(scope, item, HEADER_NAME_LIMIT)
            if clipped is not None:
                names.append(clipped)
        return names
    if scope.redact is None:
        if isinstance(value, Mapping):
            return _sanitize_metadata(
                scope, value, limit=limit, closed_keys=closed_keys
            )
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
            if _contains_text(value):
                return None
            return _sanitize_metadata(
                scope, value, limit=limit, closed_keys=closed_keys
            )
        return None if _contains_text(value) else value
    if isinstance(value, (Mapping, Sequence)) and not isinstance(value, (str, bytes, bytearray)):
        return _sanitize_metadata(scope, value, limit=limit, closed_keys=closed_keys)
    return _sanitize_text(scope, value, limit)


def build_event(
    scope: WireScope,
    kind: str,
    *,
    call: CallState | None = None,
    fields: Mapping[str, object] | None = None,
    actor: tuple[str, str] | None = None,
    answer_source: str | None = None,
    origin: str | None = None,
    capture_status: str | None = None,
    event_id: str | None = None,
) -> dict[str, object]:
    """Build one schema-v1 row; unknown fields and kind-specific keys are refused.

    Unknown keys raise (they used to be dropped silently, which turned a typo
    into a permanent null = lost provenance). Free-text values go through
    ``redact`` -> clip here, never in the builders, so a clip can never cut a
    secret out of the redacted text or run before redaction.

    ``event_id`` is the caller's idempotency key (T02). When omitted the row
    gets a fresh UUID4 hex id; when supplied it must be one ledger token, so a
    retry of an ambiguous append can reuse it and ``append_event(...,
    dedupe_event_id=True)`` can find the exact needle under the lock.
    """
    if kind not in EVENT_KINDS:
        raise WireScopeError(f"unknown event kind {kind!r}; expected one of {sorted(EVENT_KINDS)}")
    if kind in _ATTEMPT_CALL_REQUIRED and call is None:
        raise WireScopeError(f"{kind} requires a CallState (call_id/attempt_index)")
    if event_id is not None and (
        not isinstance(event_id, str) or EVENT_ID_PATTERN.match(event_id) is None
    ):
        # Never echo the value: an idempotency key is caller text.
        raise WireScopeError(
            "explicit event_id must be one ledger token ([A-Za-z0-9][A-Za-z0-9_.:@+-]{0,127}); "
            "the value is withheld"
        )
    known = _KIND_FIELDS[kind]
    if fields:
        unknown = sorted(set(fields) - set(known))
        if unknown:
            raise WireScopeError(
                f"unknown field(s) {unknown} for kind {kind!r}; expected a subset of {list(known)}"
            )
    if call is not None:
        scope.last_call_id = call.call_id

    row: dict[str, object] = {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id if event_id is not None else new_id(),
        "ts": _now_ts(),
        "kind": kind,
        "scope": scope.scope_kind,
        "project_id": scope.project_id,
        "key": scope.key,
        "task_key": scope.task_key,
        "decision_id": scope.decision_id,
        "call_id": call.call_id if call is not None else scope.last_call_id,
        "submission_id": scope.submission_id,
        "origin": origin if origin is not None else scope.origin,
        "actor": _actor_of(scope, actor),
        "answer_source": answer_source,
        "capture_status": None,
    }
    free_text = _FREE_TEXT_FIELDS[kind]
    for name in known:
        value = fields.get(name) if fields else None
        if name in ("request", "response", "book"):
            if isinstance(value, Capture):
                value = value.as_dict()
        elif name in ("task_before", "task_after"):
            try:
                value = decision_task_state.validate_task_state(value)
            except decision_task_state.TaskStateInputError as exc:
                raise WireScopeError(str(exc)) from None
            value = _sanitize_free_text(scope, name, value)
        elif name in free_text:
            value = _sanitize_free_text(scope, name, value)
        row[name] = value
    if capture_status is not None:
        row["capture_status"] = capture_status
    else:
        row["capture_status"] = _row_capture_status(row)
    return row


def _actor_of(scope: WireScope, actor: tuple[str, str] | None) -> dict[str, str | None] | None:
    """Actor kind is a closed set; the id is free text (redacted, fail-closed)."""
    if actor is None and scope.actor_kind is None and scope.actor_id is None:
        return None
    kind, actor_id = (
        (actor[0], actor[1])
        if actor is not None
        else (scope.actor_kind or "unknown", scope.actor_id or "unknown")
    )
    return {"kind": kind, "id": _sanitize_text(scope, actor_id, METADATA_TEXT_LIMIT)}


def attempt_start_event(
    scope: WireScope,
    call: CallState | None,
    *,
    request: Capture | bytes | bytearray | memoryview | str | None,
    url_path: str,
    method: str = "POST",
    model: str | None = None,
    timeout_s: float | None = None,
    header_names: Sequence[object] | None = None,
    attempt_index: int | None = None,
    origin: str | None = None,
) -> dict[str, object]:
    if call is None:
        raise WireScopeError("attempt-start requires a CallState")
    index = call.next_attempt() if attempt_index is None else call.ensure_attempt(attempt_index)
    capture = _coerce_capture(scope, request)
    return build_event(
        scope,
        "attempt-start",
        call=call,
        origin=origin,
        fields={
            "attempt_index": index,
            "method": method,
            "url_path": url_path,
            "model": model,
            "timeout_s": timeout_s,
            "header_names": list(header_names) if header_names is not None else None,
            "request": capture.as_dict() if capture is not None else None,
        },
    )


def attempt_end_event(
    scope: WireScope,
    call: CallState | None,
    *,
    response: Capture | bytes | bytearray | memoryview | str | None,
    latency_ms: float | int | None,
    http_status: int | None = None,
    content_type: str | None = None,
    retry_after_s: float | None = None,
    error_class: str | None = None,
    error_detail: str | None = None,
    usage: Mapping[str, object] | None = None,
    usage_source: str | None = None,
    attempt_index: int | None = None,
    origin: str | None = None,
) -> dict[str, object]:
    if call is None:
        raise WireScopeError("attempt-end requires a CallState")
    # An end may only reference an attempt that was actually started: an orphan
    # end must not raise ``attempts_started`` (that would fake a wire attempt the
    # client never made). ``attempt_index == 0`` marks "no matching start".
    index = call.attempts_started
    if attempt_index is not None and 0 <= attempt_index <= call.attempts_started:
        index = attempt_index
    capture = _coerce_capture(scope, response)
    return build_event(
        scope,
        "attempt-end",
        call=call,
        origin=origin,
        fields={
            "attempt_index": index,
            "latency_ms": latency_ms,
            "http_status": http_status,
            "content_type": content_type,
            "retry_after_s": retry_after_s,
            "error_class": error_class,
            "error_detail": error_detail,
            "usage": dict(usage) if usage is not None else None,
            "usage_source": usage_source or ("response-body" if usage is not None else "not-recorded"),
            "response": capture.as_dict() if capture is not None else None,
        },
    )


def call_end_event(
    scope: WireScope,
    call: CallState,
    *,
    attempts: int | None,
    latency_ms: float | int | None,
    available: bool | None = None,
    reason: str | None = None,
    answers_present: bool | None = None,
    confidence: float | None = None,
    confidence_source: str | None = None,
    transport: str | None = None,
    model: str | None = None,
    policy: Mapping[str, object] | None = None,
    wire_attempts: int | None = None,
    origin: str | None = None,
) -> dict[str, object]:
    return build_event(
        scope,
        "call-end",
        call=call,
        origin=origin,
        fields={
            "attempts": attempts,
            "wire_attempts": call.attempts_started if wire_attempts is None else wire_attempts,
            "latency_ms": latency_ms,
            "available": available,
            "reason": reason,
            "answers_present": answers_present,
            "confidence": confidence,
            "confidence_source": confidence_source,
            "transport": transport,
            "model": model,
            "policy": dict(policy) if policy is not None else None,
            "zero_call": call.attempts_started == 0,
        },
    )


def decision_end_event(
    scope: WireScope,
    *,
    status: str | None,
    archive: str | None = None,
    escalated_reason: str | None = None,
    state_digest: str | None = None,
    questions_version: str | None = None,
    truncated: Sequence[str] | None = None,
    mode: str | None = None,
    intent: str | None = None,
    book_ref: str | None = None,
    call: CallState | None = None,
    origin: str | None = None,
) -> dict[str, object]:
    return build_event(
        scope,
        "decision-end",
        call=call,
        origin=origin,
        fields={
            "status": status,
            "escalated_reason": escalated_reason,
            "archive": archive,
            "state_digest": state_digest,
            "questions_version": questions_version,
            "truncated": list(truncated) if truncated is not None else None,
            "mode": mode,
            "intent": intent,
            "book_ref": book_ref,
        },
    )


def submission_start_event(
    scope: WireScope,
    *,
    dp: str | None = None,
    outcome: str | None = "started",
    issues: Sequence[str] | None = None,
    retry_of: str | None = None,
    zero_call: bool | None = None,
    book_ref: str | None = None,
) -> dict[str, object]:
    return build_event(
        scope,
        "submission-start",
        fields={
            "dp": dp if dp is not None else scope.dp,
            "outcome": outcome,
            "issues": list(issues) if issues is not None else None,
            "retry_of": retry_of,
            "zero_call": zero_call,
            "book_ref": book_ref,
        },
    )


def submission_end_event(
    scope: WireScope,
    *,
    outcome: str | None,
    dp: str | None = None,
    issues: Sequence[str] | None = None,
    retry_of: str | None = None,
    zero_call: bool | None = None,
    book_ref: str | None = None,
) -> dict[str, object]:
    return build_event(
        scope,
        "submission-end",
        fields={
            "dp": dp if dp is not None else scope.dp,
            "outcome": outcome,
            "issues": list(issues) if issues is not None else None,
            "retry_of": retry_of,
            "zero_call": zero_call,
            "book_ref": book_ref,
        },
    )


def lifecycle_event(
    scope: WireScope,
    *,
    lifecycle: str,
    logical_id: str | None = None,
    target: str | None = None,
    supersedes: str | None = None,
    action: str | None = None,
    outcome: str | None = None,
    reason: str | None = None,
    answer: str | None = None,
    evidence: str | None = None,
    result: str | None = None,
    evidence_path: str | None = None,
    evidence_sha256: str | None = None,
    snapshot_sha256: str | None = None,
    task_after: dict[str, object] | None = None,
    actor: tuple[str, str] | None = None,
    answer_source: str | None = None,
    call: CallState | None = None,
    event_id: str | None = None,
) -> dict[str, object]:
    return build_event(
        scope,
        "lifecycle",
        call=call,
        actor=actor,
        answer_source=answer_source,
        event_id=event_id,
        fields={
            "lifecycle": lifecycle,
            "logical_id": logical_id,
            "target": target,
            "supersedes": supersedes,
            "action": action,
            "outcome": outcome,
            "reason": reason,
            "answer": answer,
            "evidence": evidence,
            "result": result,
            "evidence_path": evidence_path,
            "evidence_sha256": evidence_sha256,
            "snapshot_sha256": snapshot_sha256,
            "task_after": task_after,
        },
    )


def record_start_event(
    scope: WireScope,
    *,
    logical_id: str,
    record_version: int,
    initiator_role: str,
    retry_of: str | None = None,
    task_before: dict[str, object] | None = None,
    actor: tuple[str, str] | None = None,
    event_id: str | None = None,
) -> dict[str, object]:
    """The immutable creation fact of one decision record (T02 §4.1).

    ``record_version`` lives in this fact, not in a wire-capture absence probe:
    a v2 record whose transport failed is still v2, and a legacy row without
    this fact is never promoted. ``key``/``task_key`` ride on the scope's common
    fields; ``task_key=None`` stays null instead of being inferred.
    """
    return build_event(
        scope,
        "record-start",
        actor=actor,
        event_id=event_id,
        fields={
            "logical_id": logical_id,
            "record_version": record_version,
            "initiator_role": initiator_role,
            "retry_of": retry_of,
            "task_before": task_before,
        },
    )


def lifecycle_error_event(
    scope: WireScope,
    *,
    logical_id: str | None,
    stage: str | None,
    error_class: str | None,
    attempted_event_id: str | None = None,
    detail: str | None = None,
    event_id: str | None = None,
) -> dict[str, object]:
    """The independent failure fact for a lifecycle write (T02 error sidecar).

    Kept in its own ledger so a failed feedback write is visible to a reader
    without pretending the feedback row exists (design §4.2). ``detail`` is
    free text (redacted -> clipped); every other field is structural.
    """
    return build_event(
        scope,
        "lifecycle-error",
        event_id=event_id,
        fields={
            "logical_id": logical_id,
            "stage": stage,
            "error_class": error_class,
            "attempted_event_id": attempted_event_id,
            "detail": detail,
        },
    )


def book_snapshot_event(
    scope: WireScope,
    *,
    book: Capture | bytes | bytearray | memoryview | str | None,
    book_ref: str | None = None,
    file_sha256: str | None = None,
    book_sha256: str | None = None,
    book_version: str | None = None,
) -> dict[str, object]:
    capture = _coerce_capture(scope, book)
    return build_event(
        scope,
        "book-snapshot",
        fields={
            "book_ref": book_ref,
            "book": capture.as_dict() if capture is not None else None,
            "file_sha256": file_sha256,
            "book_sha256": book_sha256,
            "book_version": book_version,
        },
    )


# -- serialization and line budget -----------------------------------------

def _encode_row(row: Mapping[str, object]) -> bytes:
    body = json.dumps(row, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return body.encode("utf-8") + b"\n"


def _text_holders(row: Mapping[str, object]) -> list[dict[str, object]]:
    holders: list[dict[str, object]] = []
    for value in row.values():
        if isinstance(value, dict) and "text" in value and "text_omitted" in value:
            holders.append(value)
    return holders


def _refresh_capture_metrics(holder: dict[str, object]) -> None:
    text = holder.get("text")
    encoding = holder.get("encoding")
    if isinstance(text, str):
        stored_len, sha = _hash_text(text, encoding if isinstance(encoding, str) else "utf-8")
        holder["stored_len"] = stored_len
        holder["captured_redacted_sha256"] = sha
    else:
        holder["stored_len"] = 0
        holder["captured_redacted_sha256"] = None


def serialize_event(
    scope: WireScope, event: Mapping[str, object]
) -> tuple[bytes, dict[str, object]]:
    """Fit ``event`` into the scope's line budget (serialized UTF-8 bytes).

    Returns ``(line, fitted_row)``. The line always ends with ``\\n``. Text is
    shrunk in deterministic 25% steps and finally omitted; when even the
    metadata cannot fit, a minimal ``capture-failed`` row is returned (the
    identity floor can itself exceed a pathological ``line_cap``).
    """
    row = copy.deepcopy(dict(event))
    line = _encode_row(row)
    if len(line) <= scope.line_cap:
        return line, row

    def _fits(current: bytes, candidate: dict[str, object]) -> tuple[bytes, dict[str, object]]:
        # A shrunk line is no longer byte exact, so the row status must move with
        # the capture it describes (P2-1): worst-wins, never a silent downgrade
        # of an explicit status.
        candidate["capture_status"] = merge_capture_status(
            candidate.get("capture_status") if isinstance(candidate.get("capture_status"), str) else None,
            _row_capture_status(candidate),
        )
        return _encode_row(candidate), candidate

    holders = _text_holders(row)
    for _round in range(8):
        shrunk = False
        for holder in holders:
            text = holder.get("text")
            if not isinstance(text, str) or not text:
                continue
            shrunk_text = text[: (len(text) * 3) // 4]
            if scope.redact is not None:
                shrunk_text, scrubbed = scope.redact.scrub_tail_prefix(shrunk_text)
                if scrubbed:
                    holder["boundary_scrubbed"] = True
            holder["text"] = shrunk_text
            holder["truncated"] = True
            holder["byte_exact"] = False
            _refresh_capture_metrics(holder)
            shrunk = True
        if not shrunk:
            break
        line = _encode_row(row)
        if len(line) <= scope.line_cap:
            return _fits(line, row)

    for holder in holders:
        holder["text"] = None
        holder["text_omitted"] = True
        holder["truncated"] = True
        holder["byte_exact"] = False
        _refresh_capture_metrics(holder)
    if holders:
        row["capture_status"] = "failed"
    line = _encode_row(row)
    if len(line) <= scope.line_cap:
        return line, row

    minimal: dict[str, object] = {}
    for name in (
        "schema_version",
        "event_id",
        "ts",
        "kind",
        "scope",
        "project_id",
        "decision_id",
        "call_id",
        "submission_id",
        "origin",
    ):
        minimal[name] = row.get(name)
    minimal["capture_status"] = "failed"
    minimal["line_error"] = "line-cap"
    for name in ("request", "response", "book"):
        capture = row.get(name)
        if isinstance(capture, Mapping):
            minimal["wire_len"] = capture.get("wire_len")
            break
    return _encode_row(minimal), minimal


# -- append (lock, tail repair, short write, fsync) -------------------------

@dataclass(frozen=True)
class WriteResult:
    status: str
    error_class: str | None = None
    event_id: str | None = None
    line_bytes: int = 0
    capture_status: str | None = None
    tail_repaired: bool = False

    @property
    def written(self) -> bool:
        return self.status == "written"

    @property
    def duplicated(self) -> bool:
        """True when the event_id was already recorded (nothing appended)."""
        return self.status == "duplicate"

    @property
    def recorded(self) -> bool:
        """True only for a fact that really is in the ledger."""
        return self.status in ("written", "duplicate")


def _describe_exception(exc: BaseException) -> str:
    """No payload, no exception message that could embed a secret value."""
    if isinstance(exc, OSError) and exc.strerror:
        return f"{type(exc).__name__}: {exc.strerror}"
    return type(exc).__name__


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError("short write returned 0 bytes")
        view = view[written:]


def _terminate_dangling_tail(sink: pathlib.Path) -> bool:
    """Append ``\\n`` to a half-written tail; never truncate existing bytes."""
    try:
        size = sink.stat().st_size
    except FileNotFoundError:
        return False
    if size == 0:
        return False
    with sink.open("rb") as handle:
        handle.seek(size - 1)
        if handle.read(1) == b"\n":
            return False
    fd = os.open(str(sink), os.O_WRONLY | os.O_APPEND | _BINARY_FLAG)
    try:
        _write_all(fd, b"\n")
        os.fsync(fd)
    finally:
        os.close(fd)
    return True


# One logical unit per write: the logical call when the event belongs to one,
# otherwise the scope itself (submission/decision/book events). A failed write
# opens the breaker for the rest of that unit (design §9: "每逻辑调用采集失败后
# 停止反复等锁").
_SCOPE_UNIT = "<scope>"


def _write_unit(event: Mapping[str, object]) -> str:
    call_id = event.get("call_id")
    return call_id if isinstance(call_id, str) and call_id else _SCOPE_UNIT


def _fail(
    scope: WireScope, error_class: str, exc: BaseException, event: Mapping[str, object]
) -> WriteResult:
    scope._writes_failed += 1
    scope._failed_units.add(_write_unit(event))
    call_id = event.get("call_id")
    scope.note_error(
        error_class,
        scope.scrub_text(_describe_exception(exc)),
        call_id=call_id if isinstance(call_id, str) else None,
    )
    event_id = event.get("event_id")
    return WriteResult(
        status="failed",
        error_class=error_class,
        event_id=event_id if isinstance(event_id, str) else None,
        capture_status="failed",
    )


def _event_id_present(sink: pathlib.Path, event_id: str) -> bool:
    """True when ``sink`` already holds a row with this exact ``event_id``.

    Called *inside* the append lock, so a retry of an ambiguous append cannot
    create a second fact. The needle is the exact JSON member
    ``"event_id":"<id>"``; ``event_id`` is a token (``EVENT_ID_PATTERN``), so a
    matching byte sequence cannot be a substring of escaped caller text. The
    scan is streaming and bounded by the ledger size; a read error propagates
    and the caller must NOT append (it cannot prove the fact is absent).
    """
    needle = b'"event_id":"' + event_id.encode("utf-8") + b'"'
    try:
        handle = sink.open("rb")
    except FileNotFoundError:
        return False
    keep = len(needle) - 1
    overlap = b""
    with handle:
        while True:
            chunk = handle.read(READER_CHUNK_BYTES)
            if not chunk:
                return False
            window = overlap + chunk
            if needle in window:
                return True
            overlap = window[-keep:] if keep else b""


def append_event(
    scope: WireScope, event: Mapping[str, object], *, dedupe_event_id: bool = False
) -> WriteResult:
    """Append one event; never raises into the caller's business result.

    ``dedupe_event_id=True`` makes the append idempotent *under the same lock*:
    if a row with this ``event_id`` is already present, nothing is written and
    ``status="duplicate"`` is returned. Deduplication is by ``event_id`` only -
    never by ``(decision_id, kind word)``: the same word twice is two real
    actions and must stay two rows.
    """
    if event.get("schema_version") != SCHEMA_VERSION:
        return _fail(scope, "schema", WireScopeError("schema_version mismatch"), event)
    unit = _write_unit(event)
    if unit in scope._failed_units:
        # Already failed once for this unit: do not spend the lock budget again.
        scope._writes_failed += 1
        scope.note_error(
            "circuit-open",
            f"skipping write: an earlier capture for {unit} already failed",
            call_id=None if unit == _SCOPE_UNIT else unit,
        )
        event_id = event.get("event_id")
        return WriteResult(
            status="failed",
            error_class="circuit-open",
            event_id=event_id if isinstance(event_id, str) else None,
            capture_status="failed",
        )
    try:
        line, row = serialize_event(scope, event)
    except Exception as exc:  # noqa: BLE001 - capture must never break the caller
        return _fail(scope, "serialize", exc, event)

    sink = scope.sink
    try:
        sink.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return _fail(scope, "mkdir", exc, event)

    lock = sink.with_name(sink.name + ".lock")
    try:
        mw_common.acquire_lock(
            lock,
            retries=scope.lock_retries,
            base_delay=scope.lock_base_delay,
            deadline_s=scope.lock_budget_s,
        )
    except (OSError, RuntimeError) as exc:
        return _fail(scope, "lock-timeout", exc, event)

    tail_repaired = False
    try:
        if dedupe_event_id:
            event_id = event.get("event_id")
            if not isinstance(event_id, str) or not event_id:
                return _fail(
                    scope,
                    "dedupe",
                    WireScopeError("dedupe_event_id requires an explicit event_id"),
                    event,
                )
            try:
                present = _event_id_present(sink, event_id)
            except OSError as exc:
                # Cannot prove the fact is absent -> do not append a possible duplicate.
                return _fail(scope, "dedupe", exc, event)
            if present:
                scope._record_write(None, tail_repaired=False)
                status = row.get("capture_status")
                return WriteResult(
                    status="duplicate",
                    event_id=event_id,
                    capture_status=status if isinstance(status, str) else None,
                )
        tail_repaired = _terminate_dangling_tail(sink)
        fd = os.open(
            str(sink), os.O_WRONLY | os.O_CREAT | os.O_APPEND | _BINARY_FLAG, 0o644
        )
        try:
            _write_all(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)
    except OSError as exc:
        return _fail(scope, "append", exc, event)
    finally:
        # We only ever release a lock this call acquired itself.
        mw_common.release_lock(lock)

    status = row.get("capture_status")
    capture_status = status if isinstance(status, str) else None
    scope._record_write(capture_status, tail_repaired=tail_repaired)
    event_id = row.get("event_id")
    return WriteResult(
        status="written",
        event_id=event_id if isinstance(event_id, str) else None,
        line_bytes=len(line),
        capture_status=capture_status,
        tail_repaired=tail_repaired,
    )


def record_event(
    scope: WireScope | None,
    kind: str,
    *,
    call: CallState | None = None,
    fields: Mapping[str, object] | None = None,
    actor: tuple[str, str] | None = None,
    answer_source: str | None = None,
    origin: str | None = None,
    capture_status: str | None = None,
) -> WriteResult:
    if scope is None:
        return WriteResult(status="skipped")
    event = build_event(
        scope,
        kind,
        call=call,
        fields=fields,
        actor=actor,
        answer_source=answer_source,
        origin=origin,
        capture_status=capture_status,
    )
    return append_event(scope, event)


def record_attempt_start(
    scope: WireScope | None,
    call: CallState | None,
    *,
    request: Capture | bytes | bytearray | memoryview | str | None,
    url_path: str,
    method: str = "POST",
    model: str | None = None,
    timeout_s: float | None = None,
    header_names: Sequence[object] | None = None,
    attempt_index: int | None = None,
    origin: str | None = None,
) -> WriteResult:
    """Transport hook: zero writes when no scope and call are bound (probe)."""
    if scope is None or call is None:
        return WriteResult(status="skipped")
    event = attempt_start_event(
        scope,
        call,
        request=request,
        url_path=url_path,
        method=method,
        model=model,
        timeout_s=timeout_s,
        header_names=header_names,
        attempt_index=attempt_index,
        origin=origin,
    )
    return append_event(scope, event)


def record_attempt_end(
    scope: WireScope | None,
    call: CallState | None,
    *,
    response: Capture | bytes | bytearray | memoryview | str | None,
    latency_ms: float | int | None,
    http_status: int | None = None,
    content_type: str | None = None,
    retry_after_s: float | None = None,
    error_class: str | None = None,
    error_detail: str | None = None,
    usage: Mapping[str, object] | None = None,
    usage_source: str | None = None,
    attempt_index: int | None = None,
    origin: str | None = None,
) -> WriteResult:
    if scope is None or call is None:
        return WriteResult(status="skipped")
    event = attempt_end_event(
        scope,
        call,
        response=response,
        latency_ms=latency_ms,
        http_status=http_status,
        content_type=content_type,
        retry_after_s=retry_after_s,
        error_class=error_class,
        error_detail=error_detail,
        usage=usage,
        usage_source=usage_source,
        attempt_index=attempt_index,
        origin=origin,
    )
    return append_event(scope, event)


# -- read side --------------------------------------------------------------

@dataclass
class ReadStats:
    lines: int = 0
    rows: int = 0
    bad_json: int = 0
    bad_utf8: int = 0
    unknown_schema: int = 0
    oversized_line: int = 0
    incomplete_tail: int = 0
    rotated: int = 0


@dataclass(frozen=True)
class ReadResult:
    events: list[dict[str, object]]
    stats: ReadStats
    offset: int


def _consume_line(line: bytes, events: list[dict[str, object]], stats: ReadStats) -> None:
    if not line.strip():
        return
    stats.lines += 1
    try:
        text = line.decode("utf-8")
    except UnicodeDecodeError:
        stats.bad_utf8 += 1
        return
    try:
        parsed = json.loads(text)
    except ValueError:
        stats.bad_json += 1
        return
    if not isinstance(parsed, dict):
        stats.bad_json += 1
        return
    row: dict[str, object] = parsed
    if row.get("schema_version") != SCHEMA_VERSION:
        stats.unknown_schema += 1
        return
    stats.rows += 1
    events.append(row)


def read_events(
    path: pathlib.Path | str, *, offset: int = 0, line_cap: int = READER_LINE_CAP_BYTES
) -> ReadResult:
    """Incrementally read valid schema-v1 rows; damaged input is counted, not raised."""
    sink = pathlib.Path(path)
    events: list[dict[str, object]] = []
    stats = ReadStats()
    try:
        size = sink.stat().st_size
    except FileNotFoundError:
        return ReadResult(events, stats, 0)
    start = max(0, offset)
    if start > size:
        stats.rotated += 1
        start = 0

    position = start
    pending = b""
    discarding = False
    with sink.open("rb") as handle:
        handle.seek(start)
        while True:
            chunk = handle.read(READER_CHUNK_BYTES)
            if not chunk:
                break
            pending += chunk
            while True:
                newline = pending.find(b"\n")
                if newline < 0:
                    break
                line = pending[:newline]
                position += newline + 1
                pending = pending[newline + 1 :]
                if discarding:
                    discarding = False
                    continue
                if len(line) > line_cap:
                    stats.oversized_line += 1
                    continue
                _consume_line(line, events, stats)
            if discarding:
                position += len(pending)
                pending = b""
            elif len(pending) > line_cap:
                stats.oversized_line += 1
                discarding = True
                position += len(pending)
                pending = b""
    if pending and not discarding:
        stats.incomplete_tail += 1
    return ReadResult(events, stats, position)


@dataclass(frozen=True)
class WireCounts:
    events: int
    calls: int
    attempts: int
    decisions: int
    capture_failed: int


def summarize(events: Sequence[Mapping[str, object]]) -> WireCounts:
    """Count calls / attempts / decisions separately (AC-012), no inference."""
    calls = {
        event["call_id"]
        for event in events
        if isinstance(event.get("call_id"), str) and event.get("call_id")
    }
    attempts = sum(1 for event in events if event.get("kind") == "attempt-start")
    decisions = {
        event["decision_id"]
        for event in events
        if event.get("kind") == "decision-end"
        and isinstance(event.get("decision_id"), str)
        and event.get("decision_id")
    }
    failed = sum(1 for event in events if event.get("capture_status") == "failed")
    return WireCounts(
        events=len(events),
        calls=len(calls),
        attempts=attempts,
        decisions=len(decisions),
        capture_failed=failed,
    )
