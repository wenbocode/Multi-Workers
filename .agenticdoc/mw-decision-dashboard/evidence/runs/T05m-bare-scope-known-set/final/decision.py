"""decision.py — mw decision-client core (key mw-jev-provider-integration, card T-01a).

This module is the single contract face for "the framework needs a decision"
moments (design D-002/D-003): callers hand over ``state`` + ``questions`` and
receive ``answers`` + metadata. Transport differences (protocol, encoding,
error shapes) live behind :class:`DecisionBackend` and are absorbed here.

Design anchors (all line numbers are from the design in
``.agenticdoc/mw-jev-provider-integration/design.md``):

- D-002/D-003: request/response contract, frozen ``reason`` value set,
  ``confidence_source`` propagation (a backend that reports
  ``model-self-report`` must never be presented as ``api``).
- FIX-L (2026-10-20 user ruling): exactly one decision transport,
  ``timi-decisions`` (``timi`` / ``jev-latest``). The glm chat path and the
  direct TypeSafe path are gone; a config that still names one of them fails
  loud with ``entry-unavailable`` instead of silently falling back.
- D-004: budgets (timeout_s=20, max_retries=2, max_questions=8,
  max_state_bytes=0 = byte gate off, max_total_tokens=65536,
  max_state_plus_question_tokens=32768, max_tokens=1024), retry semantics and
  the fail-soft boundary — the only exception this module raises is
  :class:`DecisionInputError` (invalid *arguments*, mapped to CLI exit 2).
- D-005: one best-effort JSON evidence line per call appended to
  ``.agenticdoc/_autopilot/triage-decisions.jsonl``; a write failure is
  swallowed, never propagated.
- D-007: config lives in ``.mw/decide.json`` (missing = unconfigured,
  corrupt = error string), fail-soft on the read side, P-003 atomic writes
  on the write side (this module only reads).

Hard rules honoured here: no exception other than ``DecisionInputError``
escapes :meth:`DecisionClient.decide`; credentials never enter the response,
the evidence line or any detail text (defensive scrubbing included); the
``reason`` field only ever carries values from the frozen set below.

``state`` contract (2026-10-21 user ruling): a decision call carries exactly
three shapes — a structured JSON object, a plain string, or an array of
strings. **The JSON object is the best shape** (facts stay addressable by key,
nothing has to be rendered first); the string is the human surface and the
array is the endpoint's fragment list. Raw ``bytes`` are not a legal shape and
are no longer forwarded verbatim. Size is capped by tokens, not bytes:
``state`` + the longest single question must stay within
``max_state_plus_question_tokens`` (32768) and the whole request within
``max_total_tokens`` (65536); ``max_state_bytes`` defaults to ``0`` = gate off
and remains an optional project-level byte ceiling.
"""

from __future__ import annotations

import contextlib
import datetime
import json
import os
import pathlib
import re
import time
from collections.abc import Callable, Mapping, Sequence
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Any, Literal, NotRequired, Protocol, Required, TypedDict, runtime_checkable

__all__ = [
    "BackendOutcome",
    "BoxSpec",
    "ChoiceSpec",
    "CredentialSnapshot",
    "DecisionBackend",
    "DecisionClient",
    "DecisionConfig",
    "DecisionInputError",
    "DecisionState",
    "EVIDENCE_RELATIVE_PATH",
    "FakeBackend",
    "NoulSpec",
    "QUESTION_BOX",
    "QUESTION_CHOICE",
    "QUESTION_NOUL",
    "QUESTION_SCORE",
    "QUESTION_TYPES",
    "QuestionSpec",
    "QuestionType",
    "ScoreSpec",
    "REASON_BAD_RESPONSE",
    "REASON_BUDGET_EXHAUSTED",
    "REASON_CODES",
    "REASON_DISABLED",
    "REASON_ENTRY_UNAVAILABLE",
    "REASON_RATE_LIMITED",
    "REASON_TIMEOUT",
    "REASON_UNSUPPORTED_QUESTION_TYPE",
    "REASON_UPSTREAM_ERROR",
    "CONFIG_RELATIVE_PATH",
    "SIGNOFF_AUTO",
    "SIGNOFF_DISABLE",
    "SIGNOFF_MODES",
    "decide_config_path",
    "credential_redactor",
    "credential_snapshot",
    "current_credential_snapshot",
    "known_credential_values",
    "known_secret_redactor",
    "safe_path_text",
    "secret_hit",
    "set_default_backend_factory",
    "use_credential_snapshot",
]

# ---------------------------------------------------------------------------
# Frozen constants (design D-003 / D-005). Never invent new values.
# ---------------------------------------------------------------------------

CONFIG_RELATIVE_PATH = pathlib.Path(".mw") / "decide.json"

#: ``.mw/decide.json`` ``signoff`` modes (spec §15 AC-023 / design D-064).
#: ``auto`` = the decide model signs (this is the pinned default); ``disable`` =
#: never run the sign-off flow and the ``done`` gate stops requiring
#: ``sign-final.md``. There is deliberately no third state: a human sign is the
#: natural behaviour of an explicit ``--conclusion`` (spec §15.2).
SIGNOFF_AUTO = "auto"
SIGNOFF_DISABLE = "disable"
SIGNOFF_MODES = (SIGNOFF_AUTO, SIGNOFF_DISABLE)
EVIDENCE_RELATIVE_PATH = pathlib.Path(".agenticdoc") / "_autopilot" / "triage-decisions.jsonl"

REASON_DISABLED = "disabled"
REASON_ENTRY_UNAVAILABLE = "entry-unavailable"
REASON_TIMEOUT = "timeout"
REASON_RATE_LIMITED = "rate-limited"
REASON_UPSTREAM_ERROR = "upstream-error"
REASON_BAD_RESPONSE = "bad-response"
REASON_UNSUPPORTED_QUESTION_TYPE = "unsupported-question-type"
# FIX-H: `box` is TypeSafe's image-locating question type (answer = normalised
# {top,bottom,left,right} coordinates, `TypeSafe-Danger-Zone-Images: true`). It is
# not a free-text type, so a text-only decision request that carries one is
# refused before any HTTP call with its own reason instead of pretending the
# type is unknown (2026-10-20, https://api.typesafe.ai/api/system-one.md).
REASON_BOX_REQUIRES_IMAGE = "box-requires-image"
# D-003 lists budget-exhausted as a *response* reason (design.md §D-003); the
# BackendOutcome block in the task card omits it because backends only judge a
# single request. It is therefore accepted from backends but never invented.
REASON_BUDGET_EXHAUSTED = "budget-exhausted"

REASON_CODES = frozenset(
    {
        REASON_DISABLED,
        REASON_ENTRY_UNAVAILABLE,
        REASON_TIMEOUT,
        REASON_RATE_LIMITED,
        REASON_UPSTREAM_ERROR,
        REASON_BAD_RESPONSE,
        REASON_UNSUPPORTED_QUESTION_TYPE,
        REASON_BOX_REQUIRES_IMAGE,
        REASON_BUDGET_EXHAUSTED,
    }
)

#: Frozen question vocabulary (FIX-R: the constants are typed at the source so
#: ``QUESTION_TYPES`` and the :data:`QuestionSpec` union cannot drift apart).
QuestionType = Literal["noul", "choice", "score", "box"]

QUESTION_CHOICE: QuestionType = "choice"
QUESTION_SCORE: QuestionType = "score"
QUESTION_NOUL: QuestionType = "noul"
QUESTION_BOX: QuestionType = "box"
QUESTION_TYPES: frozenset[QuestionType] = frozenset(
    {QUESTION_CHOICE, QUESTION_SCORE, QUESTION_NOUL, QUESTION_BOX}
)

#: The only legal ``noul`` criteria keys (the two boolean outcomes). Mirrors
#: ``decision_points.NOUL_CRITERIA_KEYS`` (FIX-O); duplicated here because
#: ``decision_points`` imports this module, never the other way round.
_NOUL_CRITERIA_KEYS = frozenset({"true", "false"})


# ---------------------------------------------------------------------------
# Input contract (FIX-R): the question vocabulary and the accepted ``state``
# shapes as types, not only as ``_validate_input`` branches. ``state`` is
# deliberately *not* narrowed to a mapping — the decisions endpoint accepts a
# text, an object or an array payload (``decision_backends._state_payload``).
# ---------------------------------------------------------------------------


class NoulSpec(TypedDict):
    """``noul`` question: a boolean "no useful output" judgement."""

    type: Required[Literal["noul"]]
    instructions: NotRequired[str]
    criteria: NotRequired[Mapping[str, str]]


class ChoiceSpec(TypedDict):
    """``choice`` question: exactly one of ``choices`` / ``dynamic_choices``."""

    type: Required[Literal["choice"]]
    instructions: NotRequired[str]
    choices: NotRequired[Sequence[str]]
    dynamic_choices: NotRequired[str]
    labels: NotRequired[Mapping[str, str]]


class ScoreSpec(TypedDict):
    """``score`` question: integer ``min``/``max`` plus optional level text."""

    type: Required[Literal["score"]]
    instructions: NotRequired[str]
    min: Required[int]
    max: Required[int]
    criteria: NotRequired[Sequence[str]]


class BoxSpec(TypedDict):
    """``box`` question: image-localisation, refused before any HTTP call."""

    type: Required[Literal["box"]]
    instructions: NotRequired[str]
    properties: NotRequired[Mapping[str, object]]


QuestionSpec = NoulSpec | ChoiceSpec | ScoreSpec | BoxSpec

# ``state`` accepts exactly three shapes and no others, in order of preference:
#
# 1. a structured JSON object (``Mapping[str, object]``) — **the best shape**:
#    the backend can address facts by key and the framework can build it
#    without pre-rendering anything;
# 2. a plain ``str`` (the human surface, ``mw decide ask --state/--state-file``);
# 3. an array of strings (``Sequence[str]``, a list of text fragments).
#
# Raw ``bytes`` are **not** accepted: they are not a legal JSON value, so
# :func:`_encode_state` serialises them like any other non-JSON object
# (``json.dumps(..., default=str)``) instead of shipping the payload verbatim.
DecisionState = Mapping[str, object] | str | Sequence[str]

CONFIDENCE_SOURCE_API = "api"
CONFIDENCE_SOURCE_MODEL = "model-self-report"
CONFIDENCE_SOURCE_UNKNOWN = "unknown"

_RESPONSE_FIELDS = (
    "available",
    "transport",
    "model",
    "confidence_source",
    "attempts",
    "latency_ms",
    "answers",
    "reason",
)
_EVIDENCE_FIELDS = (
    "ts",
    "dp",
    "transport",
    "model",
    "attempts",
    "latency_ms",
    "available",
    "reason",
    "answers",
    "confidence",
    "confidence_source",
)

_DETAIL_LIMIT = 200


class DecisionInputError(ValueError):
    """Invalid arguments to :meth:`DecisionClient.decide` (CLI exit 2).

    Every other failure is normalised into an ``available=false`` response;
    this is the only exception the client is allowed to raise.
    """


@dataclass
class BackendOutcome:
    """Result of a *single* backend request (frozen protocol, design D-003).

    Backends judge one request and classify it; retrying and the overall time
    budget belong to :class:`DecisionClient`.
    """

    available: bool
    reason: str | None
    retryable: bool
    answers: dict | None
    latency_ms: int
    detail: str = ""


@runtime_checkable
class DecisionBackend(Protocol):
    """Transport backend (frozen protocol; implementations live in T-01b)."""

    name: str
    confidence_source: str

    def decide(self, state: object, questions: dict, cfg: "DecisionConfig") -> BackendOutcome: ...


# ---------------------------------------------------------------------------
# Configuration (design D-007): .mw/decide.json, fail-soft read.
# ---------------------------------------------------------------------------


def decide_config_path(project_root: pathlib.Path | str) -> pathlib.Path:
    """Return ``<project_root>/.mw/decide.json`` (kebab-case dir precedent)."""
    return pathlib.Path(project_root) / CONFIG_RELATIVE_PATH


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _parse_number(raw: Mapping, key: str, default: float, errors: list[str]) -> float:
    if key not in raw:
        return default
    value = raw[key]
    if not _is_number(value):
        errors.append(f"{key} must be a number")
        return default
    return float(value)


def _parse_int(raw: Mapping, key: str, default: int, errors: list[str]) -> int:
    if key not in raw:
        return default
    value = raw[key]
    if not _is_int(value):
        errors.append(f"{key} must be an integer")
        return default
    return int(value)


def _parse_bool(raw: Mapping, key: str, default: bool, errors: list[str]) -> bool:
    if key not in raw:
        return default
    value = raw[key]
    if not isinstance(value, bool):
        errors.append(f"{key} must be a boolean")
        return default
    return value


def _parse_str(raw: Mapping, key: str, default: str | None, errors: list[str]) -> str | None:
    if key not in raw:
        return default
    value = raw[key]
    if not isinstance(value, str):
        errors.append(f"{key} must be a string")
        return default
    return value


@dataclass
class DecisionConfig:
    """Effective decision-client configuration (defaults from design D-004/D-007).

    ``enabled`` defaults to False: merely creating ``.mw/decide.json`` is not
    enough, the file must opt in explicitly ("default off", D-007).
    """

    enabled: bool = False
    transport: str = "timi-decisions"
    model: str = "jev-latest"
    timeout_s: float = 20.0
    max_retries: int = 2
    max_questions: int = 8
    #: UTF-8 byte ceiling for ``state``; ``0`` disables the byte gate entirely
    #: (the token gates below are the real budget, this stays an optional
    #: project-level constraint).
    max_state_bytes: int = 0
    #: Whole-request token ceiling: ``state`` + every question spec.
    max_total_tokens: int = 65536
    #: Per-question ceiling: ``state`` + the longest single question spec.
    max_state_plus_question_tokens: int = 32768
    max_tokens: int = 1024
    backoff_base_s: float = 2.0
    evidence_path: str | None = None
    points: dict = field(default_factory=dict)
    triage_notify_on_unavailable: bool = False
    #: Sign-off mode (spec §15 AC-023): ``auto`` (default) or ``disable``.
    signoff: str = SIGNOFF_AUTO
    #: Admissible-value violation of ``signoff`` itself (design D-065). It is
    #: deliberately NOT part of ``config_error``: a typo in this one key must not
    #: knock all dps offline, but ``mw decide sign`` refuses on it (exit 2)
    #: instead of silently auto-signing.
    signoff_error: str | None = None
    project_root: pathlib.Path | None = None
    unconfigured: bool = False
    config_error: str | None = None
    extras: dict = field(default_factory=dict)

    @property
    def is_configured(self) -> bool:
        """True when the feature is switched on and the file parsed cleanly."""
        return bool(self.enabled) and not self.unconfigured and self.config_error is None

    @classmethod
    def from_dict(
        cls, raw: Mapping, *, project_root: pathlib.Path | None = None
    ) -> tuple["DecisionConfig", str | None]:
        """Parse a config mapping; bad field types degrade to disabled + error."""
        errors: list[str] = []
        cfg = cls(project_root=pathlib.Path(project_root) if project_root is not None else None)
        cfg.enabled = _parse_bool(raw, "enabled", False, errors)
        cfg.transport = _parse_str(raw, "transport", cfg.transport, errors) or cfg.transport
        cfg.model = _parse_str(raw, "model", cfg.model, errors) or cfg.model
        cfg.timeout_s = _parse_number(raw, "timeout_s", cfg.timeout_s, errors)
        cfg.max_retries = _parse_int(raw, "max_retries", cfg.max_retries, errors)
        cfg.max_questions = _parse_int(raw, "max_questions", cfg.max_questions, errors)
        cfg.max_state_bytes = _parse_int(raw, "max_state_bytes", cfg.max_state_bytes, errors)
        cfg.max_total_tokens = _parse_int(raw, "max_total_tokens", cfg.max_total_tokens, errors)
        cfg.max_state_plus_question_tokens = _parse_int(
            raw,
            "max_state_plus_question_tokens",
            cfg.max_state_plus_question_tokens,
            errors,
        )
        cfg.max_tokens = _parse_int(raw, "max_tokens", cfg.max_tokens, errors)
        cfg.backoff_base_s = _parse_number(raw, "backoff_base_s", cfg.backoff_base_s, errors)
        cfg.evidence_path = _parse_str(raw, "evidence_path", cfg.evidence_path, errors)
        cfg.triage_notify_on_unavailable = _parse_bool(
            raw, "triage_notify_on_unavailable", cfg.triage_notify_on_unavailable, errors
        )
        # Fail-soft, like the read side of D-007 (design D-065): an illegal
        # ``signoff`` keeps the default ``auto`` and records why, so the 25 dps
        # stay online; only the sign command turns it into an exit 2.
        raw_signoff = raw.get("signoff", SIGNOFF_AUTO)
        if isinstance(raw_signoff, str) and raw_signoff in SIGNOFF_MODES:
            cfg.signoff = raw_signoff
        else:
            cfg.signoff = SIGNOFF_AUTO
            cfg.signoff_error = (
                f"signoff must be one of {'|'.join(SIGNOFF_MODES)}, got {raw_signoff!r} "
                f"(using {SIGNOFF_AUTO})"
            )
        points = raw.get("points")
        if points is None:
            cfg.points = {}
        elif isinstance(points, Mapping):
            cfg.points = dict(points)
        else:
            errors.append("points must be an object")
            cfg.points = {}

        if cfg.timeout_s <= 0:
            errors.append("timeout_s must be > 0")
        if cfg.backoff_base_s < 0:
            errors.append("backoff_base_s must be >= 0")
        if cfg.max_retries < 0:
            errors.append("max_retries must be >= 0")
        if cfg.max_questions < 1:
            errors.append("max_questions must be >= 1")
        if cfg.max_state_bytes < 0:
            errors.append("max_state_bytes must be >= 0 (0 disables the byte gate)")
        if cfg.max_total_tokens < 1:
            errors.append("max_total_tokens must be >= 1")
        if cfg.max_state_plus_question_tokens < 1:
            errors.append("max_state_plus_question_tokens must be >= 1")
        if cfg.max_tokens < 1:
            errors.append("max_tokens must be >= 1")

        known = {
            "enabled",
            "transport",
            "model",
            "timeout_s",
            "max_retries",
            "max_questions",
            "max_state_bytes",
            "max_total_tokens",
            "max_state_plus_question_tokens",
            "max_tokens",
            "backoff_base_s",
            "evidence_path",
            "points",
            "triage_notify_on_unavailable",
            "signoff",
        }
        cfg.extras = {k: v for k, v in raw.items() if k not in known}

        if errors:
            message = "decide.json invalid: " + "; ".join(errors)
            cfg.enabled = False
            cfg.config_error = message
            return cfg, message
        return cfg, None

    @classmethod
    def from_project(
        cls, project_root: pathlib.Path | str
    ) -> tuple["DecisionConfig", str | None]:
        """Load ``.mw/decide.json`` fail-soft (missing = unconfigured).

        Returns ``(config, error)``: a missing file yields an unconfigured,
        disabled config with ``error=None``; a corrupt file yields a disabled
        config and the human-readable error string for doctor.
        """
        root = pathlib.Path(project_root)
        path = decide_config_path(root)
        if not path.exists():
            return cls(project_root=root, unconfigured=True, enabled=False), None
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            message = f"decide.json unreadable: {exc}"
            return cls(project_root=root, enabled=False, config_error=message), message
        try:
            raw = json.loads(text)
        except ValueError as exc:
            message = f"decide.json invalid JSON: {exc}"
            return cls(project_root=root, enabled=False, config_error=message), message
        if not isinstance(raw, Mapping):
            message = "decide.json must be a JSON object"
            return cls(project_root=root, enabled=False, config_error=message), message
        return cls.from_dict(raw, project_root=root)


# ---------------------------------------------------------------------------
# Credential scrubbing (task requirement 8): credentials never leave the
# client, including via backend-supplied detail strings.
# ---------------------------------------------------------------------------

_CRED_ENV_SUFFIXES = ("_API_KEY", "_TOKEN", "_KEY", "_SECRET", "_PASSWORD")
_BEARER_RE = re.compile(r"(?i)(bearer\s+)[^\s,;\"']+")
_SK_RE = re.compile(r"\bsk-[A-Za-z0-9._\-]{6,}")


def _credential_values() -> list[str]:
    import os

    values: list[str] = []
    for name, value in os.environ.items():
        if not value or len(value) < 8:
            continue
        if name.upper().endswith(_CRED_ENV_SUFFIXES):
            values.append(value)
    # Longest first so a short prefix never hides a longer match.
    return sorted(set(values), key=len, reverse=True)


def _redact(text: str) -> str:
    """Remove credential-looking material from human-readable text."""
    if not text:
        return ""
    for value in _credential_values():
        text = text.replace(value, "<redacted>")
    text = _BEARER_RE.sub(r"\1<redacted>", text)
    text = _SK_RE.sub("<redacted>", text)
    return text


def _scrub_detail(detail: object) -> str:
    text = _redact(str(detail or ""))
    text = " ".join(text.split())
    if len(text) > _DETAIL_LIMIT:
        text = text[: _DETAIL_LIMIT - 1] + "…"
    return text


# ---------------------------------------------------------------------------
# Wire capture (mw-decision-dashboard T03): the side ledger is optional for the
# decision client. Import is lazy and fail-soft: no ledger never breaks a call.
# ---------------------------------------------------------------------------

#: Secrets shorter than this are not injected into the exact-value redactor:
#: replacing one or two characters would corrupt every captured body without
#: making anything meaningfully safer.
_MIN_SECRET_LEN = 4

_WIRE_MODULE = None
_WIRE_LOADED = False
_WIRE_IMPORT_ERROR = ""


def _wire_module():
    """Lazily import ``decision_wire`` once; ``None`` when unavailable."""
    global _WIRE_MODULE, _WIRE_LOADED, _WIRE_IMPORT_ERROR
    if not _WIRE_LOADED:
        _WIRE_LOADED = True
        try:
            import decision_wire
        except Exception as exc:  # noqa: BLE001 - capture is optional
            _WIRE_IMPORT_ERROR = f"{type(exc).__name__}: {exc}"
        else:
            _WIRE_MODULE = decision_wire
    return _WIRE_MODULE


@dataclass(frozen=True)
class _CredentialRedactor:
    """Exact known-secret values plus the existing Bearer / ``sk-`` regex layers.

    The exact set is the actual ``Authorization`` value, ``cfg.api_key`` /
    ``cfg.extras["api_key"]``, the resolved timi credential and the existing env
    heuristics. It is only ever held in memory; no value is logged or stored
    (``repr`` deliberately hides the exact set too).
    """

    exact: object = field(repr=False)

    def redact(self, text: str):
        wire = _wire_module()
        result = self.exact.redact(text)
        hits = int(getattr(result, "hits", 0))
        scrubbed = result.text
        scrubbed, bearer_hits = _BEARER_RE.subn(r"\1<redacted>", scrubbed)
        scrubbed, sk_hits = _SK_RE.subn("<redacted>", scrubbed)
        if wire is None:
            return result
        return wire.Redaction(text=scrubbed, hits=hits + bearer_hits + sk_hits)

    def scrub_tail_prefix(self, text: str, window: int = 64) -> tuple[str, bool]:
        return self.exact.scrub_tail_prefix(text, window)


@dataclass(frozen=True)
class CredentialSnapshot:
    """The credential resolved **once** for one logical unit (T05i).

    ``api_key`` is the exact value the transport puts in ``Authorization``. It
    is held in memory only (``repr`` hides it) and is never logged, echoed or
    persisted. ``source`` names the discovery leg so a caller can report *where*
    the credential came from without reporting the value.

    One snapshot belongs to exactly one logical unit - one
    :meth:`DecisionClient.decide`, or one command that gates a book before
    sending. Every attempt of that unit (client retry and backend
    ``Retry-After`` retry alike) and its wire capture redactor reuse it; the next
    unit resolves a fresh one. A value rotated in *after* the snapshot is
    deliberately not part of this unit's known set and is never sent by it.

    T05l: the snapshot is also the single authority for the unit's **known-safe
    superset**. :meth:`known_superset` freezes the legacy timi leg once; the book
    gate, the decision gates, the capture redactor and the caller-owned-scope
    verification all read that one tuple, so no face can hold a set the others
    do not. The freeze is per unit - never a cross-call cache.
    """

    api_key: str | None = field(default=None, repr=False)
    source: str = "none"
    #: Safe text when the known-secret discovery raised (T05l). The known set of
    #: this unit is then *incomplete*, so no gate, capture redactor or transport
    #: may claim the material safe: the call fails closed instead of sending.
    #: Names the failure kind only - never the exception message or a value.
    #: Derived/memo state (excluded from equality, like ``_superset``) because the
    #: freeze fills it in after construction on an otherwise frozen snapshot.
    discovery_error: str | None = field(default=None, compare=False)
    #: Memoized legacy timi leg of this unit (see :meth:`known_superset`);
    #: ``None`` means "not discovered yet", ``()`` means "nothing to add".
    _superset: tuple[str, ...] | None = field(default=None, repr=False, compare=False)

    @property
    def present(self) -> bool:
        return bool(self.api_key)

    def known_superset(self) -> tuple[str, ...]:
        """The frozen legacy timi leg of this unit (T05l).

        The pre-T05e discovery always added the timi chain (env ``TIMI_API_KEY``
        then ``~/.pi/agent/auth.json``) to the known set, even when the explicit
        ``cfg`` leg supplied the sent value. T05j left that leg *live*: every
        gate/capture face resolved it again, so one unit could hold two
        different known sets while the transport sent a third value (R2).

        This method resolves it **at most once per snapshot** and freezes the
        outcome: the first consumer (book gate, decision gate, capture scope,
        wire self-injection) pays the read, every later consumer of the same
        snapshot reuses the tuple, and the next logical unit resolves afresh.
        A snapshot that is never asked for the legacy leg (an explicit ``cfg``
        key with no known-set gate, the pre-T05i client contract) reads nothing.

        A raising discovery is recorded on :attr:`discovery_error` and yields
        ``()`` - never a silent "carry on with a smaller set". The client and
        the decision gates read that flag and fail closed.

        A snapshot resolved from the timi chain itself (``env``, ``auth-json``)
        or one whose chain read found nothing (``none``) already knows this
        unit's legacy leg, so asking for it costs nothing - the chain is not
        consulted a second time (T05m: a missing credential keeps its single
        read). Only the explicit ``cfg`` legs (``cfg``, ``cfg-extras``) skipped
        the chain and therefore pay the one discovery here.

        One snapshot is shared by one single-threaded unit (see
        :class:`DecisionClient`); the memo is not a cross-call cache and not a
        lock-protected store.
        """
        if self._superset is not None:
            return self._superset
        if self.discovery_error:
            # The unit's own discovery already raised: do not read the chain again.
            object.__setattr__(self, "_superset", ())
            return self._superset
        values: tuple[str, ...] = ()
        if self.source not in ("env", "auth-json", "none"):
            try:
                import decision_backends

                resolved = decision_backends.resolve_timi_api_key()
            except Exception as exc:  # noqa: BLE001 - recorded, never silently dropped
                resolved = None
                object.__setattr__(
                    self,
                    "discovery_error",
                    f"credential discovery raised {type(exc).__name__}",
                )
            if isinstance(resolved, str) and resolved.strip():
                values = (resolved.strip(),)
        object.__setattr__(self, "_superset", values)
        return values

    def frozen_superset(self) -> tuple[str, ...]:
        """The legacy leg already frozen on this snapshot; never resolves (T05l).

        Used by the set builder so a redactor built *after* the freeze covers the
        same values as the gate, without opening a second discovery.
        """
        return self._superset if self._superset is not None else ()


def credential_snapshot(
    cfg: object = None,
    *,
    env: Mapping[str, str] | None = None,
    auth_path: pathlib.Path | str | None = None,
) -> CredentialSnapshot:
    """Resolve the credential exactly once: explicit cfg leg, then the timi chain.

    The order matches the transport's pre-existing behaviour: an explicit
    ``cfg.api_key`` / ``cfg.extras["api_key"]`` wins and nothing is resolved;
    otherwise ``decision_backends.resolve_timi_api_key`` (env ``TIMI_API_KEY``
    then ``~/.pi/agent/auth.json`` ``timi.key``) is consulted once. Discovery is
    not re-implemented here - this only freezes the outcome so the gate set, the
    capture redactor and every ``Authorization`` of one unit cannot diverge.

    A discovery that *raises* is recorded as ``discovery_error`` (type name only,
    never the message or a value) instead of being treated as "no credential":
    the known set would be incomplete, so the client and the decision gates fail
    closed rather than send material they cannot prove safe (T05l).
    """
    key: str | None = None
    source = "none"
    discovery_error: str | None = None
    if cfg is not None:
        value = getattr(cfg, "api_key", None)
        if isinstance(value, str) and value:
            key, source = value, "cfg"
        else:
            extras = getattr(cfg, "extras", None)
            if isinstance(extras, Mapping):
                value = extras.get("api_key")
                if isinstance(value, str) and value:
                    key, source = value, "cfg-extras"
    if key is None:
        try:
            import decision_backends

            resolved = decision_backends.resolve_timi_api_key(
                dict(env) if env is not None else None,
                pathlib.Path(auth_path) if auth_path is not None else None,
            )
        except Exception as exc:  # noqa: BLE001 - recorded on the snapshot (T05l)
            resolved = None
            discovery_error = f"credential discovery raised {type(exc).__name__}"
        if isinstance(resolved, str) and resolved.strip():
            key = resolved.strip()
            effective_env = os.environ if env is None else env
            env_value = effective_env.get("TIMI_API_KEY")
            source = "env" if isinstance(env_value, str) and env_value.strip() else "auth-json"
    return CredentialSnapshot(api_key=key, source=source, discovery_error=discovery_error)


#: Snapshot bound to the logical call currently executing on this context
#: (not a cross-call cache: the value is set and reset around one attempt).
_CREDENTIAL_SNAPSHOT: ContextVar[CredentialSnapshot | None] = ContextVar(
    "decision_credential_snapshot", default=None
)


def current_credential_snapshot() -> CredentialSnapshot | None:
    """The frozen credential bound to this logical call, if any (transport read)."""
    return _CREDENTIAL_SNAPSHOT.get()


@contextlib.contextmanager
def use_credential_snapshot(snapshot: CredentialSnapshot | None):
    """Bind one frozen snapshot for the duration of one backend attempt.

    The token is always reset in ``finally`` (fail-soft paths included), so no
    credential stays bound after the call and nesting restores the previous
    binding exactly.
    """
    token = _CREDENTIAL_SNAPSHOT.set(snapshot)
    try:
        yield snapshot
    finally:
        _CREDENTIAL_SNAPSHOT.reset(token)


def known_credential_values(
    cfg: object = None,
    *,
    extra_secrets: Sequence[str] = (),
    env: Mapping[str, str] | None = None,
    auth_path: pathlib.Path | str | None = None,
    snapshot: CredentialSnapshot | None = None,
) -> tuple[str, ...]:
    """The actual known-secret values of this call (design §9 / RQ5).

    Single authority for *discovery*: caller extras, the existing env
    heuristics, the actual Authorization value (``cfg.api_key`` or
    ``cfg.extras["api_key"]``) and the resolved timi credential (env
    ``TIMI_API_KEY`` or ``~/.pi/agent/auth.json`` ``timi.key``).

    ``snapshot`` pins the timi leg: when a caller resolved the credential once
    (T05i), this function reuses that value instead of resolving a second, later
    one. The cfg values and the env heuristics are always included, so the set
    stays a safe superset. Values are never logged, echoed or persisted.
    :func:`credential_redactor` (wire capture) and
    :func:`known_secret_redactor` (book gate) both build on this function, so the
    two surfaces cannot drift into different sets.
    """
    secrets: list[str] = [value for value in extra_secrets if isinstance(value, str)]
    secrets.extend(_credential_values())
    if cfg is not None:
        for holder in (cfg, getattr(cfg, "extras", None)):
            if holder is None:
                continue
            if isinstance(holder, Mapping):
                value = holder.get("api_key")
            else:
                value = getattr(holder, "api_key", None)
            if isinstance(value, str):
                secrets.append(value)
    if snapshot is not None:
        # T05i: a caller that pinned the credential (gate + send) must not make
        # this redactor resolve a second, later value. T05l: the legacy timi leg
        # the snapshot already froze is part of this unit's known set, so a
        # redactor built after the freeze (the wire self-injection included)
        # covers exactly what the gate covers. ``frozen_superset`` never
        # resolves, so this cannot open a second discovery.
        frozen = getattr(snapshot, "api_key", None)
        if isinstance(frozen, str):
            secrets.append(frozen)
        frozen_leg = getattr(snapshot, "frozen_superset", None)
        if callable(frozen_leg):
            secrets.extend(frozen_leg())
    else:
        try:
            import decision_backends

            resolved = decision_backends.resolve_timi_api_key(
                dict(env) if env is not None else None,
                pathlib.Path(auth_path) if auth_path is not None else None,
            )
        except Exception:  # noqa: BLE001 - a missing credential must not break capture
            resolved = None
        if isinstance(resolved, str):
            secrets.append(resolved)
    cleaned: list[str] = []
    for value in secrets:
        if not isinstance(value, str):
            continue
        for candidate in (value, value.strip()):
            if len(candidate) >= _MIN_SECRET_LEN and candidate not in cleaned:
                cleaned.append(candidate)
    return tuple(cleaned)


def credential_redactor(
    cfg: object = None,
    *,
    extra_secrets: Sequence[str] = (),
    env: Mapping[str, str] | None = None,
    auth_path: pathlib.Path | str | None = None,
    snapshot: CredentialSnapshot | None = None,
):
    """Build the injected known-secret set for wire capture (design §9 / RQ5).

    Includes the actual Authorization value (``cfg.api_key`` or
    ``cfg.extras["api_key"]``), the resolved timi credential (env
    ``TIMI_API_KEY`` or ``~/.pi/agent/auth.json`` ``timi.key``), the existing
    env credential heuristics and the Bearer / ``sk-`` regex layers. Returns
    ``None`` when the side ledger is unavailable (capture stays off). Never
    logs, returns or persists a credential value.

    ``snapshot`` (T05i) pins the timi leg to the value resolved for this
    logical call; pass the same object the transport is given so the captured
    text and the sent ``Authorization`` cannot diverge. T05l: a snapshot that
    already froze its legacy timi leg contributes that leg too, so this redactor
    and the book/decision gates hold one set.

    Discovery lives in :func:`known_credential_values`; this wrapper only adds
    the wire module's exact matcher, so the values themselves stay one set.
    """
    wire = _wire_module()
    if wire is None:
        return None
    values = known_credential_values(
        cfg, extra_secrets=extra_secrets, env=env, auth_path=auth_path, snapshot=snapshot
    )
    return _CredentialRedactor(exact=wire.SubstringRedactor(list(values)))


@dataclass(frozen=True)
class SecretRedaction:
    """Redacted text plus the number of substitutions actually made."""

    text: str
    hits: int = 0


@dataclass(frozen=True)
class KnownSecretRedactor:
    """Exact known-secret redactor for surfaces that must work without wire.

    ``exact`` is :func:`known_credential_values` output; the existing Bearer /
    ``sk-`` regex layers are applied on top exactly like
    ``_CredentialRedactor``. Values are held in memory only and ``repr`` never
    shows them.
    """

    exact: tuple[str, ...] = field(default=(), repr=False)
    #: T05l: the known set of this unit could not be discovered, so nothing can
    #: be proven safe. Every non-empty text is then a hit (refuse, never store)
    #: instead of being accepted as clean.
    fail_closed: bool = False

    def __post_init__(self) -> None:
        raw = (self.exact,) if isinstance(self.exact, str) else tuple(self.exact)
        cleaned = sorted(
            {value for value in raw if isinstance(value, str) and value},
            key=len,
            reverse=True,
        )
        object.__setattr__(self, "exact", tuple(cleaned))

    def redact(self, text: str) -> SecretRedaction:
        if not text:
            return SecretRedaction("", 0)
        if self.fail_closed:
            return SecretRedaction("<redacted>", 1)
        hits = 0
        for secret in self.exact:
            found = text.count(secret)
            if found:
                hits += found
                text = text.replace(secret, "<redacted>")
        text, bearer_hits = _BEARER_RE.subn(r"\1<redacted>", text)
        text, sk_hits = _SK_RE.subn("<redacted>", text)
        return SecretRedaction(text=text, hits=hits + bearer_hits + sk_hits)


def known_secret_redactor(
    cfg: object = None,
    *,
    extra_secrets: Sequence[str] = (),
    env: Mapping[str, str] | None = None,
    auth_path: pathlib.Path | str | None = None,
    snapshot: CredentialSnapshot | None = None,
) -> KnownSecretRedactor:
    """The in-memory known-secret redactor for the book gate (F1/T05e).

    Same discovery and same regex layers as :func:`credential_redactor`, but it
    does **not** require the optional wire module: a disabled/absent side ledger
    must never downgrade the book gate to the env heuristics. Values stay in
    memory; nothing is logged or persisted.

    ``snapshot`` (T05i) is the credential resolved for this command before the
    gate. A caller that also hands the same object to
    :class:`DecisionClient` gets one known set and one ``Authorization`` for the
    whole command; the full wiring obligation is on that caller.

    T05l: when the snapshot already recorded a *failed* discovery, this returns a
    fail-closed redactor (every text is a hit) instead of a smaller set that
    would accept material nobody could prove clean.
    """
    if snapshot is not None and getattr(snapshot, "discovery_error", None):
        return KnownSecretRedactor(fail_closed=True)
    return KnownSecretRedactor(
        known_credential_values(
            cfg, extra_secrets=extra_secrets, env=env, auth_path=auth_path, snapshot=snapshot
        )
    )


def secret_hit(text: str, redactor: object | None = None) -> bool:
    """True when ``text`` carries material the injected redactor would redact.

    ``redactor`` is the call's actual known-secret set
    (:func:`known_secret_redactor` / :func:`credential_redactor`). ``None``
    falls back to the existing env heuristic and Bearer/``sk-`` regexes only,
    which is the offline check and does **not** claim the configured values.
    An unusable redactor is fail-closed (the text is treated as unsafe).
    """
    if not text:
        return False
    if redactor is None:
        return _redact(text) != text
    try:
        result = redactor.redact(text)
    except Exception:  # noqa: BLE001 - a broken redactor never proves text safe
        return True
    hits = getattr(result, "hits", None)
    if isinstance(hits, int):
        return hits > 0
    return getattr(result, "text", text) != text


_SAFE_PATH_SEGMENT_RE = re.compile(r"[A-Za-z0-9_-]{1,64}")


def safe_path_text(path: object, redactor: object | None = None) -> str:
    """Display-only dotted path whose segments never echo arbitrary key text.

    A segment that is not a short identifier, or that contains known-secret
    material, collapses to ``<key>``. Callers keep deciding on the raw path;
    this only shapes what may be printed into an issue/outcome detail, so a
    credential used as an object key never reaches stderr, an outcome or the
    evidence ledger.
    """
    text = path if isinstance(path, str) else str(path)
    if not text:
        return text
    return ".".join(
        segment
        if _SAFE_PATH_SEGMENT_RE.fullmatch(segment) and not secret_hit(segment, redactor)
        else "<key>"
        for segment in text.split(".")
    )


# ---------------------------------------------------------------------------
# Helpers used by the client.
# ---------------------------------------------------------------------------


def _estimate_tokens(text: str) -> int:
    """Estimate the token count of ``text`` (conservative, not a tokenizer).

    Rules: every non-ASCII character counts as one token (CJK is ~1 token per
    character for the jev models), every 4 ASCII characters count as one token
    (rounded up). The result deliberately over-counts ordinary English prose,
    which is the safe direction for a *ceiling* check: it can refuse a request
    slightly too early, never let an oversized one through. It is an estimate,
    not an exact tokenizer; do not use it for accounting or reporting.
    """
    if not text:
        return 0
    non_ascii = sum(1 for char in text if ord(char) > 0x7F)
    ascii_chars = len(text) - non_ascii
    return non_ascii + (ascii_chars + 3) // 4


def _encode_state(state: object) -> bytes:
    """Serialise ``state`` to UTF-8 bytes (fail-soft; never raises).

    ``str`` is used verbatim; everything else (mapping, array, and any object
    that is not a legal JSON value, including ``bytes``) goes through
    ``json.dumps(..., default=str)``. Raw bytes are never forwarded as-is.
    """
    if isinstance(state, str):
        return state.encode("utf-8", errors="replace")
    try:
        serialized = json.dumps(state, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:  # noqa: BLE001 - fail-soft: never raise out of state encoding
        try:
            serialized = str(state)
        except Exception:  # noqa: BLE001
            serialized = f"<unencodable state: {type(state).__name__}>"
    return serialized.encode("utf-8", errors="replace")


def _aggregate_confidence(answers: Mapping | None) -> float | None:
    """Conservative single-number confidence for the evidence line.

    Minimum of the answer confidences (weakest link), ``None`` when the
    backend reported none. Never used for gating (D-002 hard rule).
    """
    if not answers:
        return None
    values: list[float] = []
    for entry in answers.values():
        if not isinstance(entry, Mapping):
            continue
        confidence = entry.get("confidence")
        if _is_number(confidence):
            values.append(float(confidence))
    if not values:
        return None
    return min(values)


def _outcome_from_exception(exc: BaseException) -> BackendOutcome:
    """Normalise a backend exception into a BackendOutcome (fail-soft)."""
    kind = type(exc).__name__
    if isinstance(exc, TimeoutError):
        return BackendOutcome(
            available=False,
            reason=REASON_TIMEOUT,
            retryable=True,
            answers=None,
            latency_ms=0,
            detail=f"backend raised {kind}",
        )
    if isinstance(exc, (ConnectionError, OSError)):
        return BackendOutcome(
            available=False,
            reason=REASON_UPSTREAM_ERROR,
            retryable=True,
            answers=None,
            latency_ms=0,
            detail=f"backend raised {kind}",
        )
    if isinstance(exc, ValueError):  # includes json.JSONDecodeError
        return BackendOutcome(
            available=False,
            reason=REASON_BAD_RESPONSE,
            retryable=False,
            answers=None,
            latency_ms=0,
            detail=f"backend raised {kind}",
        )
    # Unknown exception: fail-soft but do not burn the budget retrying a bug.
    return BackendOutcome(
        available=False,
        reason=REASON_UPSTREAM_ERROR,
        retryable=False,
        answers=None,
        latency_ms=0,
        detail=f"backend raised {kind}",
    )


DefaultBackendFactory = Callable[["DecisionConfig"], DecisionBackend | None]

#: Transport name (design D-002) -> backend class name. FIX-L collapsed this to
#: the single surviving transport: ``timi`` / ``jev-latest`` decisions, no
#: alternatives. Only consulted by the guarded default resolver; explicit
#: injection always wins.
DEFAULT_BACKEND_CLASSES = {
    "timi-decisions": "TimiDecisionsBackend",
}

#: Integration point for wiring the concrete backends (T-01b / CLI). Set via
#: :func:`set_default_backend_factory` or by assigning this module attribute.
DEFAULT_BACKEND_FACTORY: DefaultBackendFactory | None = None


def set_default_backend_factory(factory: DefaultBackendFactory | None) -> None:
    """Install (or clear) the module-level default backend factory."""
    global DEFAULT_BACKEND_FACTORY
    DEFAULT_BACKEND_FACTORY = factory


class _UnknownTransportBackend:
    """Fail-loud stand-in for a transport that no longer exists (FIX-L).

    Never issues a request and never answers: it only renames the disposition
    so the caller sees *why* nothing happened (``unknown decision transport
    <x>``) instead of a generic "no backend resolved". It is deliberately not a
    fallback — the removed transports are not emulated in any way.
    """

    confidence_source = CONFIDENCE_SOURCE_UNKNOWN

    def __init__(self, transport: str) -> None:
        self.name = str(transport)

    def decide(self, state: object, questions: dict, cfg: "DecisionConfig") -> BackendOutcome:
        return BackendOutcome(
            available=False,
            reason=REASON_ENTRY_UNAVAILABLE,
            retryable=False,
            answers=None,
            latency_ms=0,
            detail=f"unknown decision transport {self.name}",
        )


def _imported_backend_factory(cfg: DecisionConfig) -> DecisionBackend | None:
    """Guarded lookup of the backend class named by ``cfg.transport`` (D-002).

    The frozen protocol is shared; nothing is imported at module-import time.
    When the module is absent, exposes no factory and no class for the selected
    transport, or fails to construct, the client degrades to
    ``entry-unavailable`` instead of raising. A transport that is simply not in
    :data:`DEFAULT_BACKEND_CLASSES` (the removed glm / typesafe names) resolves
    to :class:`_UnknownTransportBackend` so the failure detail names it.
    """
    transport = cfg.transport or "timi-decisions"
    try:
        import decision_backends  # type: ignore[import-not-found]  # sibling
    except Exception:
        return None
    for attr in ("resolve_backend", "build_backend"):
        factory = getattr(decision_backends, attr, None)
        if callable(factory):
            try:
                backend = factory(cfg)
            except Exception:
                backend = None
            if backend is not None:
                return backend
    class_name = DEFAULT_BACKEND_CLASSES.get(transport)
    if class_name is None:
        return _UnknownTransportBackend(transport)
    backend_class = getattr(decision_backends, class_name, None)
    if backend_class is None:
        return None
    try:
        return backend_class()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Fake backend (tests / caller injection).
# ---------------------------------------------------------------------------


class FakeBackend:
    """Programmable backend: a queue of outcomes, exceptions or callables.

    ``results`` is consumed in order. Each item may be a :class:`BackendOutcome`,
    a ``dict`` of its fields, an exception instance (raised), or a callable
    ``(state, questions, cfg) -> BackendOutcome | dict | exception``. When the
    queue runs dry, ``default`` is used (or ``RuntimeError`` is raised, which
    the client normalises as ``upstream-error``).
    """

    def __init__(
        self,
        results: list | None = None,
        *,
        name: str = "fake",
        model: str = "fake-model",
        confidence_source: str = CONFIDENCE_SOURCE_MODEL,
        default: object = None,
    ) -> None:
        self.name = name
        self.model = model
        self.confidence_source = confidence_source
        self._results = list(results or [])
        self._default = default
        self.calls: list[dict] = []

    @property
    def remaining(self) -> int:
        return len(self._results)

    def push(self, item: object) -> None:
        self._results.append(item)

    def decide(self, state: object, questions: dict, cfg: DecisionConfig) -> BackendOutcome:
        self.calls.append({"state": state, "questions": questions, "cfg": cfg})
        if self._results:
            item = self._results.pop(0)
        elif self._default is not None:
            item = self._default
        else:
            raise RuntimeError("FakeBackend has no programmed result")
        if callable(item) and not isinstance(item, type):
            item = item(state, questions, cfg)
        if isinstance(item, BaseException):
            raise item
        if isinstance(item, BackendOutcome):
            return item
        if isinstance(item, Mapping):
            return BackendOutcome(**dict(item))
        raise TypeError(f"FakeBackend cannot interpret programmed result {item!r}")


# ---------------------------------------------------------------------------
# Decision client: validation, budget, retry, normalisation, evidence.
# ---------------------------------------------------------------------------


class DecisionClient:
    """Contract face for decision calls (design D-002/D-003/D-004/D-005).

    :meth:`decide` raises only :class:`DecisionInputError`; any other failure —
    backend exceptions, unusable answers, an unwritable evidence file — is
    reported as ``available=false`` plus a frozen ``reason``.

    One client serves one unit at a time: the credential pin
    (:attr:`_pinned_credential_snapshot`), the injected capture redactor and the
    bound snapshot of an attempt are per-call state, deliberately without a lock
    (the concurrent-capture feature is not reduced by this card). Two threads
    that share one client would overwrite each other's pin/redactor; give each
    thread its own client (or serialize the calls).
    """

    def __init__(
        self,
        cfg: DecisionConfig | None = None,
        backend: DecisionBackend | None = None,
        *,
        project_root: pathlib.Path | str | None = None,
        evidence_path: pathlib.Path | str | None = None,
        clock: Callable[[], float] | None = None,
        sleep: Callable[[float], None] | None = None,
        backend_factory: DefaultBackendFactory | None = None,
        wire_scope: object | None = None,
        credential_snapshot: CredentialSnapshot | None = None,
    ) -> None:
        if cfg is None:
            root = pathlib.Path(project_root) if project_root is not None else None
            cfg = DecisionConfig(project_root=root)
        if project_root is not None:
            cfg.project_root = pathlib.Path(project_root)
        self.cfg = cfg
        self.backend = backend
        self.backend_factory = backend_factory
        self._evidence_override = pathlib.Path(evidence_path) if evidence_path is not None else None
        self._clock = clock or time.monotonic
        self._sleep = sleep or time.sleep
        # Wire capture state (T03). ``capture_status`` is deliberately an
        # attribute/property here, not a key in the frozen ``decide`` dict.
        self._wire_scope = wire_scope
        self._active_scope = wire_scope
        self.capture_status: str | None = None
        self.last_call_id: str | None = None
        self.last_wire_attempts: int = 0
        # T05i: a caller that already resolved the credential for this command
        # (gate + send from one object) pins it here. Without a pin, ``decide``
        # resolves exactly once per logical call - never once per attempt.
        self._pinned_credential_snapshot = credential_snapshot
        self.last_credential_source: str | None = None
        self._injected_redactor: object | None = None

    # -- public API ---------------------------------------------------------

    def decide(
        self,
        state: DecisionState,
        questions: Mapping[str, QuestionSpec],
        *,
        dp: str = "unspecified",
    ) -> dict:
        """Ask one decision point; always returns a response dict (never raises
        except for :class:`DecisionInputError` on invalid arguments).

        ``state`` is one of the three accepted shapes — a structured JSON
        object (**preferred**), a plain string, or an array of strings; see
        ``decision.DecisionState``. ``questions`` is the typed
        :data:`QuestionSpec` mapping.

        Response keys (design D-003): ``available``, ``transport``, ``model``,
        ``confidence_source``, ``attempts``, ``latency_ms``, ``answers``,
        ``reason``.
        """
        self._validate_input(state, questions)
        wire = _wire_module()
        if wire is None:
            return self._decide(state, questions, dp=dp)
        # One logical call id per decide; the transport owns attempt_index.
        call = wire.new_call()
        scope = self._wire_scope if self._wire_scope is not None else wire.current_scope()
        self._active_scope = scope
        self.last_call_id = call.call_id
        self.last_wire_attempts = 0
        self.capture_status = None
        context = wire.use(scope, call) if scope is not None else wire.call_context(call)
        with context:
            return self._decide(state, questions, dp=dp)

    def _decide(
        self,
        state: DecisionState,
        questions: Mapping[str, QuestionSpec],
        *,
        dp: str = "unspecified",
    ) -> dict:
        cfg = self.cfg
        start = self._clock()
        transport = self._backend_name()
        confidence_source = self._backend_confidence_source()

        if not cfg.is_configured:
            if cfg.config_error:
                detail = cfg.config_error
            elif not cfg.enabled and not cfg.unconfigured:
                detail = "decision disabled by config"
            else:
                detail = "decision config missing (.mw/decide.json)"
            return self._emit(dp, start, False, REASON_DISABLED, 0, None, detail, transport, confidence_source)

        # Step 3 — size gates, in this order: optional byte ceiling, then the
        # per-question token ceiling, then the whole-request token ceiling.
        state_bytes = _encode_state(state)
        state_tokens = _estimate_tokens(state_bytes.decode("utf-8"))
        question_tokens = {
            qid: _estimate_tokens(json.dumps(spec, ensure_ascii=False, default=str))
            for qid, spec in questions.items()
        }
        if cfg.max_state_bytes > 0 and len(state_bytes) > cfg.max_state_bytes:
            detail = f"state is {len(state_bytes)} bytes > max_state_bytes={cfg.max_state_bytes}"
            return self._emit(
                dp, start, False, REASON_BUDGET_EXHAUSTED, 0, None, detail, transport, confidence_source
            )
        longest_question_tokens = max(question_tokens.values())
        state_plus_question = state_tokens + longest_question_tokens
        if state_plus_question > cfg.max_state_plus_question_tokens:
            detail = (
                f"state+longest question is {state_plus_question} tokens > "
                f"max_state_plus_question_tokens={cfg.max_state_plus_question_tokens} "
                f"(state={state_tokens}, longest={longest_question_tokens})"
            )
            return self._emit(
                dp, start, False, REASON_BUDGET_EXHAUSTED, 0, None, detail, transport, confidence_source
            )
        questions_tokens = sum(question_tokens.values())
        request_tokens = state_tokens + questions_tokens
        if request_tokens > cfg.max_total_tokens:
            detail = (
                f"request is {request_tokens} tokens > max_total_tokens={cfg.max_total_tokens} "
                f"(state={state_tokens}, questions={questions_tokens})"
            )
            return self._emit(
                dp, start, False, REASON_BUDGET_EXHAUSTED, 0, None, detail, transport, confidence_source
            )

        # One credential resolution per logical call (T05i): every attempt below
        # and the capture redactor reuse this frozen snapshot.
        snapshot = self._pinned_credential_snapshot or credential_snapshot(cfg)
        self.last_credential_source = snapshot.source
        # T05m: the capture path freezes the unit's *complete* known set before it
        # records anything, so a bare production scope with an explicit cfg key
        # no longer captures a legacy timi leg raw (T05l R1). A caller-owned
        # redactor is never replaced, and a snapshot that already covered the
        # timi chain is not read twice.
        self._ensure_wire_redactor(snapshot)
        discovery_error = getattr(snapshot, "discovery_error", None)
        if discovery_error:
            # Fail closed (T05l/T05m): the known-secret discovery raised, so this
            # unit's set is incomplete and no captured text could be proven
            # safe. Send nothing; the safe detail names the failure kind only.
            return self._emit(
                dp,
                start,
                False,
                REASON_ENTRY_UNAVAILABLE,
                0,
                None,
                f"{discovery_error}; refusing to send (known-secret set incomplete)",
                transport,
                confidence_source,
            )

        backend = self._resolve_backend()
        if backend is None:
            return self._emit(
                dp,
                start,
                False,
                REASON_ENTRY_UNAVAILABLE,
                0,
                None,
                "no decision backend resolved",
                transport,
                confidence_source,
            )

        transport = self._backend_name(backend)
        confidence_source = self._backend_confidence_source(backend)
        deadline = start + float(cfg.timeout_s)
        attempts = 0
        last_reason: str | None = None

        while True:
            if self._clock() >= deadline:
                detail = f"time budget {cfg.timeout_s:g}s exhausted after {attempts} attempt(s)"
                if last_reason:
                    detail += f"; last={last_reason}"
                return self._emit(
                    dp,
                    start,
                    False,
                    REASON_BUDGET_EXHAUSTED,
                    attempts,
                    None,
                    detail,
                    transport,
                    confidence_source,
                    backend,
                )
            attempts += 1
            with use_credential_snapshot(snapshot):
                outcome = self._call_backend(backend, state, questions, cfg)
            if outcome.available:
                answers = self._normalize_answers(outcome.answers, questions)
                if answers is None:
                    return self._emit(
                        dp,
                        start,
                        False,
                        REASON_BAD_RESPONSE,
                        attempts,
                        None,
                        f"backend {backend.name} reported available without usable answers: {outcome.detail}",
                        transport,
                        confidence_source,
                        backend,
                    )
                return self._emit(
                    dp,
                    start,
                    True,
                    None,
                    attempts,
                    answers,
                    outcome.detail,
                    transport,
                    confidence_source,
                    backend,
                )
            reason = outcome.reason if outcome.reason in REASON_CODES else REASON_UPSTREAM_ERROR
            last_reason = reason
            if not outcome.retryable or attempts > cfg.max_retries:
                return self._emit(
                    dp,
                    start,
                    False,
                    reason,
                    attempts,
                    None,
                    outcome.detail,
                    transport,
                    confidence_source,
                    backend,
                )
            delay = float(cfg.backoff_base_s) * (2 ** (attempts - 1))
            now = self._clock()
            if now + delay > deadline:
                detail = (
                    f"retry backoff {delay:g}s exceeds time budget {cfg.timeout_s:g}s "
                    f"after {attempts} attempt(s); last={reason}"
                )
                return self._emit(
                    dp,
                    start,
                    False,
                    REASON_BUDGET_EXHAUSTED,
                    attempts,
                    None,
                    detail,
                    transport,
                    confidence_source,
                    backend,
                )
            try:
                self._sleep(delay)
            except Exception:  # noqa: BLE001 - fail-soft: a failed wait must not escape
                return self._emit(
                    dp,
                    start,
                    False,
                    REASON_BUDGET_EXHAUSTED,
                    attempts,
                    None,
                    "retry backoff sleep failed",
                    transport,
                    confidence_source,
                    backend,
                )

    # -- validation (the only raising path) ---------------------------------

    def _validate_input(self, state: object, questions: object) -> None:
        cfg = self.cfg
        if state is None:
            raise DecisionInputError("state must not be None")
        if not isinstance(questions, Mapping):
            raise DecisionInputError("questions must be an object mapping question id -> spec")
        if not questions:
            raise DecisionInputError("questions must not be empty")
        if len(questions) > cfg.max_questions:
            raise DecisionInputError(
                f"questions has {len(questions)} entries > max_questions={cfg.max_questions}"
            )
        for qid, spec in questions.items():
            if not isinstance(qid, str) or not qid:
                raise DecisionInputError("question id must be a non-empty string")
            if not isinstance(spec, Mapping):
                raise DecisionInputError(f"question {qid!r} spec must be an object")
            qtype = spec.get("type")
            if qtype not in QUESTION_TYPES:
                raise DecisionInputError(f"question {qid!r} has unknown type {qtype!r}")
            if qtype == QUESTION_CHOICE:
                # A choice question declares its vocabulary either inline
                # (`choices`) or per request (`dynamic_choices`, the name of a
                # state key rendered by the backend). Exactly one of the two.
                choices = spec.get("choices")
                dynamic = spec.get("dynamic_choices")
                if dynamic is not None:
                    if not isinstance(dynamic, str) or not dynamic.strip():
                        raise DecisionInputError(
                            f"question {qid!r} 'dynamic_choices' must be a non-empty state key"
                        )
                    if choices is not None:
                        raise DecisionInputError(
                            f"question {qid!r} must declare either 'choices' or 'dynamic_choices', not both"
                        )
                    if "labels" in spec:
                        # FIX-R: `labels` only describes static `choices`; a
                        # dynamic choice renders its candidate labels from the
                        # state key, so accepting both would silently drop
                        # `labels`. Refuse instead of half-applying the spec.
                        raise DecisionInputError(
                            f"question {qid!r} cannot declare both 'labels' and 'dynamic_choices': "
                            "dynamic_choices renders the candidates (and their labels) from state, "
                            "'labels' only describes static 'choices'"
                        )
                elif not isinstance(choices, list) or not choices:
                    raise DecisionInputError(
                        f"question {qid!r} type 'choice' requires a non-empty 'choices' list"
                    )
            elif qtype == QUESTION_SCORE:
                low, high = spec.get("min"), spec.get("max")
                if not _is_int(low) or not _is_int(high):
                    raise DecisionInputError(
                        f"question {qid!r} type 'score' requires integer 'min' and 'max'"
                    )
                if low > high:
                    raise DecisionInputError(
                        f"question {qid!r} 'min' ({low}) exceeds 'max' ({high})"
                    )
            elif qtype == QUESTION_NOUL:
                # FIX-R: an optional noul criteria must spell out exactly the
                # two boolean outcomes, each with usable text (silently sending
                # `{"yes": ...}` would let the criterion text vanish).
                if "criteria" in spec:
                    criteria = spec.get("criteria")
                    if not isinstance(criteria, Mapping):
                        raise DecisionInputError(
                            f"question {qid!r} type 'noul' criteria must be exactly "
                            f"{{true, false}}, got {type(criteria).__name__}"
                        )
                    if set(criteria) != _NOUL_CRITERIA_KEYS:
                        keys = sorted(str(key) for key in criteria)
                        raise DecisionInputError(
                            f"question {qid!r} type 'noul' criteria must be exactly "
                            f"{{true, false}}, got keys {keys}"
                        )
                    if not all(
                        isinstance(value, str) and value.strip() for value in criteria.values()
                    ):
                        raise DecisionInputError(
                            f"question {qid!r} type 'noul' criteria must be exactly "
                            f"{{true, false}} with non-empty string values"
                        )
            # 'box' carries no required fields; it is a known type that T-01b
            # rejects with unsupported-question-type.

    # -- backend plumbing ---------------------------------------------------

    def _resolve_backend(self) -> DecisionBackend | None:
        if self.backend is not None:
            return self.backend
        factory = self.backend_factory or DEFAULT_BACKEND_FACTORY
        try:
            if factory is not None:
                return factory(self.cfg)
            return _imported_backend_factory(self.cfg)
        except Exception:
            return None

    def _backend_name(self, backend: DecisionBackend | None = None) -> str:
        target = backend if backend is not None else self.backend
        name = getattr(target, "name", None)
        if isinstance(name, str) and name:
            return name
        if target is None and self.cfg.transport:
            return str(self.cfg.transport)
        return "none"

    def _backend_confidence_source(self, backend: DecisionBackend | None = None) -> str:
        target = backend if backend is not None else self.backend
        source = getattr(target, "confidence_source", None)
        if source in (CONFIDENCE_SOURCE_API, CONFIDENCE_SOURCE_MODEL):
            return source
        return CONFIDENCE_SOURCE_UNKNOWN

    def _backend_model(self, backend: DecisionBackend | None = None) -> str | None:
        target = backend if backend is not None else self.backend
        model = getattr(target, "model", None)
        if isinstance(model, str) and model:
            return model
        return self.cfg.model or None

    def _call_backend(
        self, backend: DecisionBackend, state: object, questions: dict, cfg: DecisionConfig
    ) -> BackendOutcome:
        try:
            outcome = backend.decide(state, questions, cfg)
        except Exception as exc:  # noqa: BLE001 - fail-soft boundary (D-004)
            return _outcome_from_exception(exc)
        if not isinstance(outcome, BackendOutcome):
            return BackendOutcome(
                available=False,
                reason=REASON_BAD_RESPONSE,
                retryable=False,
                answers=None,
                latency_ms=0,
                detail=f"backend {backend.name} returned {type(outcome).__name__}, not BackendOutcome",
            )
        return outcome

    # -- normalisation ------------------------------------------------------

    def _normalize_answers(
        self, answers: object, questions: Mapping[str, QuestionSpec]
    ) -> dict | None:
        """Filter to requested ids, coerce confidence, validate shape.

        Returns ``None`` when the payload cannot be trusted (→ bad-response).
        """
        if not isinstance(answers, Mapping):
            return None
        normalized: dict[str, dict] = {}
        for qid in questions:
            entry = answers.get(qid)
            if not isinstance(entry, Mapping) or "value" not in entry:
                return None
            confidence = entry.get("confidence")
            if _is_number(confidence):
                confidence = min(1.0, max(0.0, float(confidence)))
            else:
                confidence = None
            normalized[qid] = {"value": entry.get("value"), "confidence": confidence}
        return normalized

    # -- response + evidence ------------------------------------------------

    def _emit(
        self,
        dp: str,
        start: float,
        available: bool,
        reason: str | None,
        attempts: int,
        answers: dict | None,
        detail: object,
        transport: str,
        confidence_source: str,
        backend: DecisionBackend | None = None,
    ) -> dict:
        latency_ms = max(0, int(round((self._clock() - start) * 1000)))
        if available:
            reason = None
        elif reason not in REASON_CODES:
            reason = REASON_UPSTREAM_ERROR
        response: dict[str, Any] = dict.fromkeys(_RESPONSE_FIELDS)
        response["available"] = bool(available)
        response["transport"] = _redact(str(transport or "none"))
        model = self._backend_model(backend)
        response["model"] = _redact(str(model)) if model else None
        response["confidence_source"] = confidence_source
        response["attempts"] = int(attempts)
        response["latency_ms"] = latency_ms
        response["answers"] = answers if available else None
        response["reason"] = reason
        self._record_call_end(response, attempts)
        self._append_evidence(dp, response)
        return response

    def _ensure_wire_redactor(self, snapshot: CredentialSnapshot) -> None:
        """Fill (or refresh) this call's capture redactor from the credential set.

        The transport is the component that knows the real Authorization value,
        so it injects the redactor for production capture. A test scope keeps
        the side ledger's fail-closed contract (no redactor -> metadata only)
        and must be given one explicitly by its creator.

        A redactor this client injected is rebuilt from the current call's
        snapshot, so a credential rotated between two logical calls is redacted
        by the second call instead of leaking through a stale set (T05i). A
        caller-owned redactor is never replaced - pinning stays the caller's
        contract.

        T05m: this is the capture path, so it freezes the unit's complete known
        set *before* anything is recorded. Relying on a gate to have frozen it
        first made a bare client persist the legacy timi leg raw (T05l R1); the
        freeze here is per snapshot (retries reuse it, the next call refreshes)
        and a discovery that raises leaves ``discovery_error`` set, which
        ``_decide`` turns into a fail-closed refusal before any POST.
        """
        scope = self._active_scope
        if scope is None:
            return
        if getattr(scope, "scope_kind", "production") != "production":
            return
        current = getattr(scope, "redact", None)
        if current is not None and current is not self._injected_redactor:
            return
        snapshot.known_superset()
        if getattr(snapshot, "discovery_error", None):
            return
        redactor = credential_redactor(self.cfg, snapshot=snapshot)
        if redactor is not None:
            scope.redact = redactor
            self._injected_redactor = redactor

    def _record_call_end(self, response: Mapping, attempts: int) -> None:
        """Append the client's ``call-end`` row and expose its capture status.

        ``attempts`` is the client's logical backend-attempt count;
        ``wire_attempts`` is the real POST count (backend Retry-After retries
        included). This is the only place the logical call is closed.
        """
        wire = _wire_module()
        self.capture_status = None
        if wire is None:
            return
        scope = wire.current_scope()
        call = wire.current_call()
        if call is None:
            return
        self.last_call_id = call.call_id
        self.last_wire_attempts = call.attempts_started
        if scope is None:
            return
        answers = response.get("answers")
        available = bool(response.get("available"))
        try:
            event = wire.call_end_event(
                scope,
                call,
                attempts=attempts,
                latency_ms=response.get("latency_ms"),
                available=available,
                reason=response.get("reason"),
                answers_present=bool(answers),
                confidence=_aggregate_confidence(answers if available else None),
                confidence_source=response.get("confidence_source"),
                transport=response.get("transport"),
                model=response.get("model"),
            )
            wire.append_event(scope, event)
        except Exception:  # noqa: BLE001 - capture must never break the decision
            return
        self.capture_status = scope.capture_status

    def _evidence_file(self) -> pathlib.Path | None:
        if self._evidence_override is not None:
            return self._evidence_override
        scope = self._active_scope
        if scope is not None and getattr(scope, "scope_kind", "production") == "test":
            # A test scope never falls back to the production triage ledger.
            evidence = getattr(scope, "evidence_path", None)
            return pathlib.Path(evidence) if evidence is not None else None
        cfg = self.cfg
        root = cfg.project_root
        if cfg.evidence_path:
            path = pathlib.Path(cfg.evidence_path)
            if path.is_absolute():
                return path
            return (root / path) if root is not None else path
        if root is None:
            return None
        return root / EVIDENCE_RELATIVE_PATH

    def _append_evidence(self, dp: str, response: Mapping) -> None:
        """Best-effort append (D-005 item 1); never raises."""
        path = self._evidence_file()
        if path is None:
            return
        record: dict[str, Any] = dict.fromkeys(_EVIDENCE_FIELDS)
        record["ts"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
        record["dp"] = dp
        record["transport"] = _redact(str(response.get("transport") or "none"))
        model = response.get("model")
        record["model"] = _redact(str(model)) if model else None
        record["attempts"] = int(response.get("attempts") or 0)
        record["latency_ms"] = int(response.get("latency_ms") or 0)
        record["available"] = bool(response.get("available"))
        record["reason"] = response.get("reason")
        record["answers"] = response.get("answers") if response.get("available") else None
        record["confidence"] = _aggregate_confidence(
            response.get("answers") if response.get("available") else None
        )
        record["confidence_source"] = response.get("confidence_source")
        if record["reason"] is not None and record["reason"] not in REASON_CODES:
            record["reason"] = REASON_UPSTREAM_ERROR
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            line = json.dumps(record, ensure_ascii=False)
            with path.open("a", encoding="utf-8", newline="\n") as fh:
                fh.write(line + "\n")
        except Exception:  # noqa: BLE001 - best-effort contract (D-005)
            return

    # -- helper used by tests / diagnostics ---------------------------------

    def evidence_path(self) -> pathlib.Path | None:
        """Resolved evidence path (may be ``None`` when no project root is known)."""
        return self._evidence_file()
