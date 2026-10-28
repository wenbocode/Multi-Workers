"""decision_backends.py — the single mw decision transport: timi ``/v1/decisions``.

FIX-L (2026-10-20) collapsed the decision feature onto exactly one transport.
The user ruling is: decisions go to ``timi`` / ``jev-latest`` only — no
``timi/glm-*`` chat fallback, no direct TypeSafe endpoint, no model switching,
no backup transport. This module therefore carries one HTTP path:

    POST {TIMI_BASE_URL}/v1/decisions
    Authorization: <timi key>            # bare key, no Bearer prefix
    Content-Type: application/json
    {"model": "jev-latest", "state": <str|object|array>,
     "questions": {<qid>: {"type", "instructions", "criteria"?}}}

Response shape (documented, verified by the PM against the live gateway):

    {"model": "jev-latest",
     "answers": {"<qid>": {"type": "noul|choice|score", ...}},
     "usage": {"input_tokens": N, "output_tokens": N}}

Contract source: ``.agenticdoc/mw-decision-substitution/jev接入.md``
(``/v1/decisions``, criteria required for ``choice``/``score``, answer field
table). There is no ``box`` question type and no free-text answer type on this
endpoint; ``box`` stays refused with ``box-requires-image`` and zero HTTP.

The frozen protocol (contract/validation/budget/fail-soft/evidence) lives in
``decision.py``; this module only imports the shared types from it and must
never modify the client. Retry/fallback rules honoured here:

- 429/5xx are classified as retryable; the client owns the exponential
  backoff budget (``cfg.max_retries``, ``cfg.backoff_base_s``) and never changes
  model or endpoint between attempts. When the gateway sends an explicit
  ``retry-after`` header the backend performs that wait itself (bounded by
  ``cfg.max_retries``) because the client cannot see response headers;
- once the retry budget is spent the disposition is ``rate-limited`` /
  ``upstream-error`` — there is no code path that changes ``model`` or switches
  transport, and none that returns ``available=True`` without a decoded answer.
"""

from __future__ import annotations

import http.client
import json
import os
import pathlib
import socket
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

# ── Shared frozen types (owned by decision.py) ──────────────────────────────
# Import direction is one-way (decision_backends -> decision); decision.py
# imports this module only lazily inside its factory. The frozen definitions
# below are only used when the module is imported without decision.py on the
# path (standalone import tolerance).
_DECISION_IMPORT_ERROR = ""
try:  # pragma: no cover - exercised by whichever import path is available
    from decision import BackendOutcome, DecisionBackend, DecisionConfig

    DECISION_TYPES_LOCAL = False
except ImportError as _decision_import_error:  # pragma: no cover - standalone import
    DECISION_TYPES_LOCAL = True
    _DECISION_IMPORT_ERROR = f"{type(_decision_import_error).__name__}: {_decision_import_error}"

    class DecisionBackend(Protocol):
        name: str
        confidence_source: str

        def decide(self, state: object, questions: dict, cfg: "DecisionConfig") -> "BackendOutcome": ...

    @dataclass
    class BackendOutcome:  # type: ignore[no-redef]
        available: bool
        reason: str | None
        retryable: bool
        answers: dict | None
        latency_ms: int
        detail: str = ""

    @dataclass
    class DecisionConfig:  # type: ignore[no-redef]
        """Fail-soft default mirror of decision.DecisionConfig (timi-only)."""

        enabled: bool = True
        transport: str = "timi-decisions"
        model: str = "jev-latest"
        base_url: str = "http://api.timiai.woa.com/ai_api_manage/llmproxy"
        timeout_s: float = 20.0
        max_tokens: int = 1024
        max_retries: int = 2
        backoff_base_s: float = 2.0
        api_key: str | None = None
        extras: dict = field(default_factory=dict)


# The dynamic-choices contract (state-rendered enums) has exactly one authority:
# the registry module (``decision_points``). Import direction stays acyclic:
# decision_backends -> decision_points -> decision.
import decision_points as _dpts  # noqa: E402

# The side ledger is optional for the transport: capture must never break a
# decision, so a missing/broken ``decision_wire`` degrades to zero capture.
try:  # pragma: no cover - exercised by whichever import path is available
    import decision_wire as _wire
except Exception:  # pragma: no cover - standalone import tolerance
    _wire = None


# ── Constants ───────────────────────────────────────────────────────────────

TIMI_BASE_URL = "http://api.timiai.woa.com/ai_api_manage/llmproxy"
TIMI_AUTH_JSON = "~/.pi/agent/auth.json"
TIMI_AUTH_FIELD = ("timi", "key")
#: The only decision transport (FIX-L: no alternatives, no fallback).
DECISIONS_TRANSPORT = "timi-decisions"
DECISIONS_PATH = "/v1/decisions"
DEFAULT_MODEL = "jev-latest"
MAX_DETAIL = 200

CONFIDENCE_SOURCE_API = "api"

REASON_DISABLED = "disabled"
REASON_ENTRY_UNAVAILABLE = "entry-unavailable"
REASON_TIMEOUT = "timeout"
REASON_RATE_LIMITED = "rate-limited"
REASON_UPSTREAM_ERROR = "upstream-error"
REASON_BAD_RESPONSE = "bad-response"
REASON_UNSUPPORTED_QUESTION_TYPE = "unsupported-question-type"
REASON_INPUT_INCOMPLETE = "input-incomplete"

#: Question types this endpoint can answer. ``box`` is deliberately absent: it
#: is an image-localization question that neither the request shape nor the
#: answer shape of ``/v1/decisions`` carries.
ANSWERABLE_TYPES = ("choice", "score", "noul")
#: Independent rejection reason for ``box`` question sets (never reuse
#: ``unsupported-question-type``: the type is known and valid, it just needs an
#: image transport this endpoint does not have).
BOX_REQUIRES_IMAGE_REASON = "box-requires-image"
BOX_REQUIRES_IMAGE_DETAIL = (
    "box is an image-localization question: it requires the "
    "TypeSafe-Danger-Zone-Images header and an image asset in state.assets; "
    "the timi decisions endpoint cannot answer it"
)

#: Official criteria bounds for a ``score`` question (low -> high, 2..10).
MIN_SCORE_LEVELS = 2
MAX_SCORE_LEVELS = 10


# ── Credentials (env -> ~/.pi/agent/auth.json timi.key; never logged) ───────

def _cfg_extra(cfg: object, name: str):
    extras = getattr(cfg, "extras", None)
    return extras.get(name) if isinstance(extras, dict) else None


def _cfg_get(cfg: object, name: str, default=None):
    """Read a config field, falling back to ``DecisionConfig.extras``.

    ``decision.DecisionConfig`` carries the D-004/D-007 fields and an
    ``extras`` mapping for transport knobs it does not model (``base_url``,
    ``api_key``).
    """
    value = getattr(cfg, name, None)
    if value is not None:
        return value
    extra = _cfg_extra(cfg, name)
    return default if extra is None else extra


def _auth_json_path() -> pathlib.Path:
    return pathlib.Path(os.path.expanduser(TIMI_AUTH_JSON))


def resolve_timi_api_key(env: dict | None = None, auth_path: pathlib.Path | None = None) -> str | None:
    """Resolve the timi key via env TIMI_API_KEY then auth.json ``timi.key``.

    Mirrors the mw credential source chain (mw_common._DEFAULT_CONFIG timi
    entry). Returns None when absent; never logs the value.
    """
    env = os.environ if env is None else env
    value = env.get("TIMI_API_KEY")
    if isinstance(value, str) and value.strip():
        return value.strip()
    path = pathlib.Path(auth_path) if auth_path is not None else _auth_json_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    cur: object = data
    for part in TIMI_AUTH_FIELD:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur.strip() if isinstance(cur, str) and cur.strip() else None


def credential_status(cfg: object = None, env: dict | None = None) -> dict:
    """Boolean-only credential presence (safe to print/log).

    FIX-L: the decision feature has exactly one credential (timi), so the
    status mapping has exactly one entry.
    """
    env = os.environ if env is None else env
    cfg_key = _cfg_get(cfg, "api_key") if cfg is not None else None
    timi_present = bool((isinstance(cfg_key, str) and cfg_key.strip()) or resolve_timi_api_key(env))
    return {"timi": timi_present}


def _sanitize(text: str, secret: str | None) -> str:
    out = "" if text is None else str(text)
    if secret:
        out = out.replace(secret, "<redacted>")
    out = " ".join(out.split())
    return out[:MAX_DETAIL]


# ── HTTP transport (injectable for hermetic tests) ──────────────────────────

@dataclass
class HttpResponse:
    status: int
    content_type: str
    body: str
    headers: dict = field(default_factory=dict)


class TransportTimeout(Exception):
    """The request exceeded cfg.timeout_s."""


class TransportConnectionError(Exception):
    """Connection-level failure (DNS/refused/reset) before a response."""


def _decode_bytes(raw: bytes) -> str:
    return raw.decode("utf-8", errors="replace")


def _header(headers: object, name: str) -> str | None:
    if not headers:
        return None
    try:
        value = headers.get(name)  # type: ignore[union-attr]
    except AttributeError:
        return None
    return value if isinstance(value, str) else None


def _url_path(url: str) -> str:
    """Path only: userinfo and query strings never enter the ledger."""
    try:
        return urllib.parse.urlsplit(url).path or "/"
    except ValueError:
        return "/"


def _describe_exception(exc: BaseException) -> str:
    text = str(exc).strip()
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _usage_from_body(body: str) -> dict | None:
    """The documented ``usage`` block, or ``None`` (usage is never estimated)."""
    parsed = _try_json(body)
    if not isinstance(parsed, dict):
        return None
    usage = parsed.get("usage")
    if isinstance(usage, dict) and usage:
        return dict(usage)
    return None


@dataclass
class _AttemptCapture:
    """Pending attempt-start bookkeeping; no scope+call means zero writes."""

    scope: object | None = None
    call: object | None = None
    index: int | None = None
    started: float = 0.0
    finished: bool = False


def _begin_attempt(
    url: str, headers: dict, data: bytes, payload: dict, timeout_s: float
) -> _AttemptCapture:
    """Record attempt-start from the *actual* serialized request bytes.

    The four-parameter ``_http_post`` contract is frozen: the logical call (and
    therefore ``call_id``/``attempt_index``) comes from the caller's bound
    context. No binding (the diagnostic probe) means no ledger row at all.
    """
    started = time.monotonic()
    if _wire is None:
        return _AttemptCapture(started=started)
    scope = _wire.current_scope()
    call = _wire.current_call()
    if scope is None or call is None:
        return _AttemptCapture(started=started)
    try:
        index = call.next_attempt()
        _wire.record_attempt_start(
            scope,
            call,
            request=data,
            url_path=_url_path(url),
            method="POST",
            model=payload.get("model"),
            timeout_s=timeout_s,
            header_names=list(headers),
            attempt_index=index,
        )
    except Exception:  # noqa: BLE001 - capture must never break the transport
        return _AttemptCapture(started=started)
    return _AttemptCapture(scope=scope, call=call, index=index, started=started)


def _end_attempt(
    attempt: _AttemptCapture,
    *,
    response: bytes | None = None,
    http_status: int | None = None,
    content_type: str | None = None,
    retry_after: float | None = None,
    error_class: str | None = None,
    error_detail: str | None = None,
    usage: dict | None = None,
) -> None:
    """Record attempt-end exactly once per POST (guarded by ``finished``)."""
    if _wire is None or attempt.finished:
        return
    attempt.finished = True
    if attempt.scope is None or attempt.call is None or attempt.index is None:
        return
    latency_ms = max(0, int(round((time.monotonic() - attempt.started) * 1000)))
    detail = None
    if error_detail:
        try:
            detail = attempt.scope.scrub_text(error_detail)  # type: ignore[attr-defined]
        except Exception:  # noqa: BLE001 - a scrub failure must not break the call
            detail = None
    try:
        _wire.record_attempt_end(
            attempt.scope,
            attempt.call,
            response=response,
            latency_ms=latency_ms,
            http_status=http_status,
            content_type=content_type,
            retry_after_s=retry_after,
            error_class=error_class,
            error_detail=detail,
            usage=usage,
            usage_source="response-body" if usage is not None else None,
            attempt_index=attempt.index,
        )
    except Exception:  # noqa: BLE001 - capture must never break the transport
        return


def _http_post(url: str, headers: dict, payload: dict, timeout_s: float) -> HttpResponse:
    """One non-streaming POST; tests monkeypatch this function.

    Capture happens at this real boundary: the request from the exact ``data``
    bytes sent, the response from the bytes read *before* the documented
    ``errors="replace"`` decode. A failed read is marked ``response-read`` and
    is never recorded as a genuine empty body; the parsed ``HttpResponse``
    contract (and therefore the decision result) is unchanged.
    """
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    attempt = _begin_attempt(url, headers, data, payload, timeout_s)
    request = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = int(getattr(response, "status", 0))
            content_type = _header(response.headers, "Content-Type") or ""
            retry_after_raw = _header(response.headers, "retry-after")
            try:
                raw = response.read()
            except (OSError, http.client.HTTPException) as exc:
                _end_attempt(
                    attempt,
                    http_status=status,
                    content_type=content_type,
                    retry_after=_retry_after_value(retry_after_raw),
                    error_class="response-read",
                    error_detail=_describe_exception(exc),
                )
                raise
            body = _decode_bytes(raw)
            _end_attempt(
                attempt,
                response=raw,
                http_status=status,
                content_type=content_type,
                retry_after=_retry_after_value(retry_after_raw),
                usage=_usage_from_body(body),
            )
            return HttpResponse(
                status,
                content_type,
                body,
                {"retry-after": retry_after_raw or ""},
            )
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        content_type = _header(exc.headers, "Content-Type") or ""
        retry_after_raw = _header(exc.headers, "retry-after")
        try:
            raw = exc.read()
        except (OSError, http.client.HTTPException) as read_exc:
            # A read failure is not an empty body: record why, keep the old
            # fail-soft parsing behaviour (body="") unchanged.
            _end_attempt(
                attempt,
                http_status=status,
                content_type=content_type,
                retry_after=_retry_after_value(retry_after_raw),
                error_class="response-read",
                error_detail=_describe_exception(read_exc),
            )
            body = ""
        else:
            body = _decode_bytes(raw)
            _end_attempt(
                attempt,
                response=raw,
                http_status=status,
                content_type=content_type,
                retry_after=_retry_after_value(retry_after_raw),
                usage=_usage_from_body(body),
            )
        return HttpResponse(
            status,
            content_type,
            body,
            {"retry-after": retry_after_raw or ""},
        )
    except (socket.timeout, TimeoutError) as exc:
        _end_attempt(attempt, error_class="timeout", error_detail=_describe_exception(exc))
        raise TransportTimeout(str(exc)) from None
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (socket.timeout, TimeoutError)):
            _end_attempt(
                attempt, error_class="timeout", error_detail=_describe_exception(exc.reason)
            )
            raise TransportTimeout(str(exc.reason)) from None
        _end_attempt(
            attempt, error_class="connection-error", error_detail=_describe_exception(exc.reason)
        )
        raise TransportConnectionError(str(exc.reason)) from None
    except OSError as exc:
        _end_attempt(
            attempt, error_class="connection-error", error_detail=_describe_exception(exc)
        )
        raise TransportConnectionError(str(exc)) from None


# ── Error classification (design D-004, 8 classes) ──────────────────────────

_RETRYABLE_STATUS = frozenset({408, 409, 425, 429})
_NON_RETRYABLE_STATUS = frozenset({400, 401, 403, 405, 413, 415, 422})

_RATE_LIMIT_MARKERS = ("rate_limit", "rate limit", "too many requests", "429")
_TIMEOUT_MARKERS = ("timeout", "timed out", "deadline exceeded")
_OVERLOAD_MARKERS = (
    "overloaded",
    "internal server error",
    "server error",
    "bad gateway",
    "service unavailable",
    "temporarily unavailable",
    "upstream connect",
    "529",
    "500 ",
    "502",
    "503",
    "504",
)


def _try_json(text: str):
    try:
        return json.loads(text)
    except (TypeError, ValueError):
        return None


def _classify_body_error(text: str) -> tuple[str, bool]:
    """Classify a 2xx response whose body carries an error (litellm pass-through)."""
    lowered = (text or "").lower()
    if any(marker in lowered for marker in _RATE_LIMIT_MARKERS):
        return REASON_RATE_LIMITED, True
    if any(marker in lowered for marker in _TIMEOUT_MARKERS):
        return REASON_TIMEOUT, True
    if any(marker in lowered for marker in _OVERLOAD_MARKERS):
        return REASON_UPSTREAM_ERROR, True
    # Unmapped provider / model unavailable / bad request: config-level, permanent.
    return REASON_UPSTREAM_ERROR, False


def _classify(status: int, content_type: str, body: str) -> tuple[str | None, bool]:
    """Return (reason, retryable); reason None means 2xx JSON success body."""
    if status == 404:
        return REASON_ENTRY_UNAVAILABLE, False
    if status in _NON_RETRYABLE_STATUS:
        return REASON_UPSTREAM_ERROR, False
    if status == 429:
        return REASON_RATE_LIMITED, True
    if status == 408:
        return REASON_TIMEOUT, True
    if status in _RETRYABLE_STATUS or status >= 500:
        return REASON_UPSTREAM_ERROR, True
    if 200 <= status < 300:
        parsed = _try_json(body)
        if parsed is None:
            # Success status but not JSON: protocol error, not retryable.
            return REASON_BAD_RESPONSE, False
        if isinstance(parsed, dict) and parsed.get("error") not in (None, {}, "", False, []):
            return _classify_body_error(body)
        if "litellm." in body and "Error" in body:
            return _classify_body_error(body)
        return None, False
    # Unmapped/other 3xx/4xx: treat as a routing problem, do not retry.
    return REASON_ENTRY_UNAVAILABLE, False


def _status_detail(resp: HttpResponse) -> str:
    ctype = (resp.content_type or "").split(";")[0].strip() or "unknown"
    kind = "html" if "html" in ctype.lower() else ("json" if "json" in ctype.lower() else ctype)
    return f"HTTP {resp.status} content-type={kind} body={resp.body}"


def _retry_after_value(raw: object) -> float | None:
    """Parse a raw ``retry-after`` header value; ``None`` when absent/invalid."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        seconds = float(raw.strip())
    except ValueError:
        return None
    return seconds if seconds >= 0 else None


def _retry_after_s(resp: HttpResponse) -> float | None:
    """Parse the response ``retry-after`` seconds; ``None`` when absent/invalid."""
    return _retry_after_value((resp.headers or {}).get("retry-after"))


def _sleep(seconds: float) -> None:
    """Retry wait, injectable so tests never sleep for real."""
    if seconds > 0:
        time.sleep(seconds)


# ── Request encoding helpers ────────────────────────────────────────────────

def _timi_base_url(cfg: object) -> str:
    return str(
        _cfg_get(cfg, "base_url")
        or os.environ.get("TIMI_BASE_URL")
        or TIMI_BASE_URL
    ).rstrip("/")


def _serialize_state(state: object) -> str:
    if isinstance(state, str):
        return state
    try:
        return json.dumps(state, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        return str(state)


def _state_payload(state: object) -> object:
    """``state`` is documented as string / object / array; everything else is JSON text."""
    if isinstance(state, (str, dict, list)):
        return state
    return _serialize_state(state)


def _question_instructions(qid: str, spec: Mapping) -> object:
    """Question text: ``spec["instructions"]`` when present, else a fallback.

    The wired dps (dp1/dp2/dp3/dp8) carry real per-question ``instructions``
    (FIX-O), so the endpoint's required field is normally the registry text. The
    deterministic placeholder only covers dps that are not wired yet: it keeps
    the request valid without inventing semantics for a question nobody wrote.
    """
    instructions = spec.get("instructions")
    if isinstance(instructions, str) and instructions.strip():
        return instructions
    if isinstance(instructions, (dict, list)) and instructions:
        return instructions
    return f"{qid}: answer this question about the supplied state"


def _choice_criteria(spec: Mapping, rendered: Mapping[str, str] | None) -> dict:
    """``{option: label_or_null}`` — caller criteria first, then rendered, then ``labels``.

    A caller may hand in the wire shape directly (``criteria``: the documented
    ``{option: label_or_null}`` mapping, see jev接入.md); that mapping is used
    verbatim. A registry spec instead names ``choices`` and supplies
    ``spec["labels"]`` for their descriptions (a labels-only spec still
    contributes its keys). `rendered` is the dynamic-candidate mapping.
    """
    declared = spec.get("criteria")
    if isinstance(declared, Mapping) and declared:
        return dict(declared)
    if rendered is not None:
        return dict(rendered)
    labels = spec.get("labels")
    labels = labels if isinstance(labels, Mapping) else {}
    options = [str(choice) for choice in spec.get("choices", [])]
    if not options and labels:
        options = [str(option) for option in labels]
    criteria: dict = {}
    for option in options:
        label = labels.get(option)
        criteria[option] = label if isinstance(label, str) else None
    return criteria


def _score_criteria(spec: Mapping) -> list:
    """Ordered score levels (low -> high): ``spec["criteria"]``, else 0..N-1.

    The documented ``score`` answer is a (possibly fractional) legend index, so
    the generated fallback labels are exactly those indices. ``min``/``max``
    only size the list here; a caller that needs textual levels supplies
    ``criteria``.
    """
    criteria = spec.get("criteria")
    if isinstance(criteria, list) and len(criteria) >= MIN_SCORE_LEVELS:
        return list(criteria[:MAX_SCORE_LEVELS])
    low, high = spec.get("min"), spec.get("max")
    levels = high - low + 1 if isinstance(low, int) and isinstance(high, int) and high >= low else 0
    levels = max(MIN_SCORE_LEVELS, min(MAX_SCORE_LEVELS, levels))
    return [str(level) for level in range(levels)]


def _box_questions(questions: dict) -> list:
    return [
        str(qid)
        for qid, spec in questions.items()
        if isinstance(spec, dict) and spec.get("type") == "box"
    ]


def _has_image_assets(state: object) -> bool:
    """True only when ``state`` carries a TypeSafe image asset (``assets``)."""
    if not isinstance(state, dict):
        return False
    assets = state.get("assets")
    if not isinstance(assets, dict):
        return False
    return any(
        isinstance(asset, dict) and asset.get("type") == "image"
        for asset in assets.values()
    )


def _unsupported_types(questions: dict) -> list:
    bad = []
    for qid, spec in questions.items():
        qtype = spec.get("type") if isinstance(spec, dict) else None
        if qtype not in ANSWERABLE_TYPES:
            bad.append(str(qid))
    return bad


def _dynamic_choice_problem(questions: dict, state: object) -> str:
    """``""`` when every dynamic question renders; else the refusal detail.

    ``missing_fields=[...]`` names the absent state key (the caller turns this
    into ``input-incomplete`` before any HTTP call); an illegal candidate list
    reports the concrete shape violation instead, so the caller can fix the
    producer rather than guess.
    """
    for qid, spec in questions.items():
        spec = spec if isinstance(spec, dict) else {}
        key = spec.get("dynamic_choices")
        if not isinstance(key, str):
            continue
        if not isinstance(state, Mapping) or key not in state:
            return f'{qid}: missing_fields=["{key}"] (dynamic_choices)'
        reason = _dpts.dynamic_choices_value_error(state[key])
        if reason:
            return f"{qid}: {key} invalid: {reason}"
    return ""


def _dynamic_labels(questions: dict, state: object) -> dict[str, dict[str, str]]:
    """Rendered ``{qid: {candidate_id: label}}`` (``{}`` when none is dynamic)."""
    rendered = _dpts.dynamic_choice_labels(questions, state)
    return rendered or {}


def _choice_enum(spec: Mapping, rendered: Mapping[str, str] | None) -> list[str]:
    """Legal answer values for one ``choice``: rendered ids, choices, else labels."""
    if rendered is not None:
        return list(rendered.keys())
    choices = [str(choice) for choice in spec.get("choices", [])]
    if choices:
        return choices
    labels = spec.get("labels")
    if isinstance(labels, Mapping):
        return [str(option) for option in labels]
    return []


def _coerce_confidence(raw) -> float | None:
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    return float(raw)


# ── Outcome helpers ─────────────────────────────────────────────────────────

def _elapsed_ms(start: float) -> int:
    return max(0, int((time.monotonic() - start) * 1000))


def _outcome(
    start: float,
    available: bool,
    reason: str | None,
    retryable: bool,
    answers: dict | None,
    detail: str = "",
    secret: str | None = None,
) -> "BackendOutcome":
    return BackendOutcome(
        available=available,
        reason=reason,
        retryable=retryable,
        answers=answers,
        latency_ms=_elapsed_ms(start),
        detail=_sanitize(detail, secret),
    )


# ── The only backend: timi-decisions ────────────────────────────────────────

class TimiDecisionsBackend:
    """``POST /v1/decisions`` with model ``jev-latest`` (the only transport).

    ``confidence_source`` is ``api``: ``confidence`` is an official field of the
    documented answer shape, not a model self-report.
    """

    name = DECISIONS_TRANSPORT
    confidence_source = CONFIDENCE_SOURCE_API

    def endpoint(self, cfg: object) -> str:
        return _timi_base_url(cfg) + DECISIONS_PATH

    def headers(self, key: str) -> dict:
        # The platform docs and the live probe both use the bare personal API
        # key; a ``Bearer`` prefix is not part of this contract.
        return {"Content-Type": "application/json", "Authorization": key}

    def build_questions(
        self, questions: dict, dynamic: Mapping[str, Mapping[str, str]] | None = None
    ) -> dict:
        dynamic = dynamic or {}
        out: dict = {}
        for qid, spec in questions.items():
            spec = spec if isinstance(spec, Mapping) else {}
            qtype = spec.get("type")
            instructions = _question_instructions(str(qid), spec)
            if qtype == "noul":
                question: dict = {"type": "noul", "instructions": instructions}
                criteria = spec.get("criteria")
                if isinstance(criteria, Mapping) and criteria:
                    # Documented optional shape: {"true": "...", "false": "..."}.
                    question["criteria"] = dict(criteria)
            elif qtype == "choice":
                question = {
                    "type": "choice",
                    "instructions": instructions,
                    "criteria": _choice_criteria(spec, dynamic.get(str(qid))),
                }
            elif qtype == "score":
                question = {
                    "type": "score",
                    "instructions": instructions,
                    "criteria": _score_criteria(spec),
                }
            else:
                # ``box`` and unknown types never enter the request; ``decide``
                # refuses them before this builder runs.
                continue
            out[str(qid)] = question
        return out

    def build_payload(
        self,
        state: object,
        questions: dict,
        cfg: object,
        dynamic: Mapping[str, Mapping[str, str]] | None = None,
    ) -> dict:
        """Exactly the documented body: ``{model, state, questions}``."""
        model = _cfg_get(cfg, "model", DEFAULT_MODEL) or DEFAULT_MODEL
        return {
            "model": str(model),
            "state": _state_payload(state),
            "questions": self.build_questions(questions, dynamic),
        }

    def _decode_answers(
        self,
        parsed: object,
        questions: dict,
        dynamic: Mapping[str, Mapping[str, str]] | None = None,
        expected_model: str | None = None,
    ) -> tuple[dict | None, str]:
        """Decode the documented ``answers`` map into ``{value, confidence}``.

        ``choice`` answers must be a member of the rendered/static enum,
        ``score`` keeps the (possibly fractional) value, ``noul`` is a
        probability in 0..1 with no separate confidence. ``probabilities`` and
        ``legend`` are carried through untouched so callers can inspect the
        distribution instead of trusting a single number.

        ``expected_model`` is the model the request asked for: a response from
        any other model is refused (``bad-response``) — there is no model
        fallback, so accepting it would silently mask a gateway substitution.
        """
        dynamic = dynamic or {}
        if not isinstance(parsed, dict):
            return None, "response is not a JSON object"
        if expected_model is not None:
            answered_model = parsed.get("model")
            if isinstance(answered_model, str) and answered_model != expected_model:
                return None, (
                    f"response model {answered_model!r} != requested model "
                    f"{expected_model!r} (no model fallback)"
                )
        if not isinstance(parsed.get("answers"), dict):
            return None, "response has no answers map"
        raw = parsed["answers"]
        answers: dict = {}
        for qid, spec in questions.items():
            spec = spec if isinstance(spec, dict) else {}
            qtype = spec.get("type")
            entry = raw.get(qid)
            if not isinstance(entry, dict):
                return None, f"missing answer for {qid}"
            if entry.get("type") != qtype:
                return None, (
                    f"answer type mismatch for {qid}: expected {qtype!r}, "
                    f"got {entry.get('type')!r}"
                )
            if qtype == "choice":
                if "choice" not in entry:
                    return None, f"missing choice for {qid}"
                value = str(entry["choice"])
                choices = _choice_enum(spec, dynamic.get(qid))
                if choices and value not in choices:
                    return None, f"choice out of enum for {qid}: {value!r}"
                confidence = _coerce_confidence(entry.get("confidence"))
            elif qtype == "score":
                raw_score = entry.get("score")
                if isinstance(raw_score, bool) or not isinstance(raw_score, (int, float)):
                    return None, f"score for {qid} is not a number: {raw_score!r}"
                # The documented score is a probability-weighted level index and
                # may fall between two levels: keep it exactly as sent.
                value = raw_score
                confidence = _coerce_confidence(entry.get("confidence"))
            elif qtype == "noul":
                raw_noul = entry.get("noul")
                if isinstance(raw_noul, bool) or not isinstance(raw_noul, (int, float)):
                    return None, f"noul for {qid} is not a probability: {raw_noul!r}"
                if not 0.0 <= float(raw_noul) <= 1.0:
                    return None, f"noul for {qid} is not a probability: {raw_noul!r}"
                value = float(raw_noul)
                confidence = None  # documented: noul carries no separate confidence
            elif qtype == "box":
                # Image localization, refused in ``decide`` before any request;
                # decoding it as text here would silently fabricate an answer.
                return None, f"unsupported question type for {qid}: box requires image assets"
            else:
                return None, f"unsupported question type for {qid}: {qtype}"
            answer: dict = {"value": value, "confidence": confidence}
            probabilities = entry.get("probabilities")
            if isinstance(probabilities, Mapping):
                answer["probabilities"] = dict(probabilities)
            if qtype == "score":
                legend = entry.get("legend")
                if isinstance(legend, Mapping):
                    answer["legend"] = dict(legend)
            answers[str(qid)] = answer
        return answers, ""

    def _retry_delay(self, cfg: object, attempt: int, resp: HttpResponse | None) -> float:
        base = float(_cfg_get(cfg, "backoff_base_s", 2.0) or 0.0)
        delay = base * (2 ** (attempt - 1))
        retry_after = _retry_after_s(resp) if resp is not None else None
        if retry_after is not None:
            delay = max(delay, retry_after)
        return max(0.0, delay)

    def _post(
        self, payload: dict, cfg: object, key: str
    ) -> tuple[object | None, tuple[str, bool, str] | None]:
        """One POST, plus the ``retry-after``-driven retries the client cannot do.

        ``(resp, None)`` on a clean 2xx JSON body, else ``(None, (reason,
        retryable, detail))``. The client owns the plain exponential-backoff
        budget (same endpoint, same model); the backend only repeats when the
        response carries an explicit ``retry-after`` header, which the client
        has no way of seeing. Either way the retry count is bounded by
        ``cfg.max_retries``.
        """
        timeout_s = float(_cfg_get(cfg, "timeout_s", 20.0) or 20.0)
        max_retries = max(0, int(_cfg_get(cfg, "max_retries", 0) or 0))
        attempt = 0
        while True:
            attempt += 1
            try:
                resp = _http_post(self.endpoint(cfg), self.headers(key), payload, timeout_s)
            except TransportTimeout as exc:
                return None, (REASON_TIMEOUT, True, f"request timeout: {exc}")
            except TransportConnectionError as exc:
                return None, (REASON_UPSTREAM_ERROR, True, f"connection error: {exc}")
            except Exception as exc:  # noqa: BLE001 - fail-soft boundary
                return None, (REASON_UPSTREAM_ERROR, True, f"transport error: {exc}")
            reason, retryable = _classify(resp.status, resp.content_type, resp.body)
            if reason is None:
                return resp, None
            retry_after = _retry_after_s(resp)
            if retryable and retry_after is not None:
                # An explicit ``retry-after`` hands this retry to the backend
                # (the client cannot see response headers). Once that budget is
                # spent the disposition is final so the client cannot multiply
                # the attempts.
                if attempt <= max_retries:
                    _sleep(self._retry_delay(cfg, attempt, resp))
                    continue
                return None, (reason, False, _status_detail(resp))
            return None, (reason, retryable, _status_detail(resp))

    def decide(self, state: object, questions: dict, cfg: object) -> "BackendOutcome":
        start = time.monotonic()
        if not getattr(cfg, "enabled", True):
            return _outcome(start, False, REASON_DISABLED, False, None, "decision feature disabled")
        box_ids = _box_questions(questions)
        if box_ids and not _has_image_assets(state):
            return _outcome(
                start,
                False,
                BOX_REQUIRES_IMAGE_REASON,
                False,
                None,
                f"cannot answer {','.join(box_ids)}: {BOX_REQUIRES_IMAGE_DETAIL}",
            )
        unsupported = _unsupported_types(questions)
        if unsupported:
            return _outcome(
                start,
                False,
                REASON_UNSUPPORTED_QUESTION_TYPE,
                False,
                None,
                f"cannot answer: {','.join(unsupported)}",
            )
        dynamic_problem = _dynamic_choice_problem(questions, state)
        if dynamic_problem:
            # FIX-I: an unrenderable dynamic enum is an input defect, not a
            # transport failure. Refuse before the credential is read so this
            # path can never issue a request.
            return _outcome(start, False, REASON_INPUT_INCOMPLETE, False, None, dynamic_problem)
        dynamic = _dynamic_labels(questions, state)
        key = _cfg_get(cfg, "api_key") or resolve_timi_api_key()
        if not key:
            return _outcome(
                start,
                False,
                REASON_ENTRY_UNAVAILABLE,
                False,
                None,
                "TIMI_API_KEY not configured (env TIMI_API_KEY or ~/.pi/agent/auth.json timi.key)",
            )

        payload = self.build_payload(state, questions, cfg, dynamic)
        resp, failure = self._post(payload, cfg, key)
        if failure is not None:
            reason, retryable, detail = failure
            return _outcome(start, False, reason, retryable, None, detail, key)

        answers, err = self._decode_answers(
            _try_json(resp.body), questions, dynamic, expected_model=payload["model"]
        )
        if answers is None:
            return _outcome(start, False, REASON_BAD_RESPONSE, False, None, err, key)
        return _outcome(start, True, None, False, answers, "", key)


# ── Diagnostics: endpoint probe (single transport, never raises) ────────────

#: FIX-L: the probe matrix collapsed to the one surviving transport.
PROBE_TARGETS = ((DECISIONS_PATH, DECISIONS_TRANSPORT),)
#: Minimal valid probe question (``noul`` needs no ``criteria``).
_PROBE_QUESTIONS = {
    "probe": {"type": "noul", "instructions": "Is this probe request well formed?"}
}


def probe_matrix(cfg: object, questions: dict | None = None) -> list:
    """Probe the decisions endpoint; return ``{target,method,path,status,verdict}``.

    Reads the timi credential only to build the Authorization header. Never
    returns or prints the key, never raises: any failure becomes a
    ``status=None`` row with a verdict.
    """
    questions = questions or dict(_PROBE_QUESTIONS)
    backend = TimiDecisionsBackend()
    base = _timi_base_url(cfg)
    timeout_s = float(_cfg_get(cfg, "timeout_s", 20.0) or 20.0)
    key = _cfg_get(cfg, "api_key") or resolve_timi_api_key()
    payload = backend.build_payload("ping", questions, cfg)
    rows: list = []
    for path, transport in PROBE_TARGETS:
        row = {
            "target": f"{transport}:{payload['model']}",
            "method": "POST",
            "path": path,
            "status": None,
            "verdict": REASON_ENTRY_UNAVAILABLE,
        }
        if not key:
            rows.append(row)
            continue
        try:
            resp = _http_post(base + path, backend.headers(key), payload, timeout_s)
            row["status"] = resp.status
            reason, _retryable = _classify(resp.status, resp.content_type, resp.body)
            row["verdict"] = reason or "ok"
        except TransportTimeout:
            row["verdict"] = REASON_TIMEOUT
        except TransportConnectionError:
            row["verdict"] = REASON_UPSTREAM_ERROR
        except Exception:  # noqa: BLE001 - diagnostics must never raise
            row["verdict"] = REASON_UPSTREAM_ERROR
        rows.append(row)
    return rows


__all__ = [
    "ANSWERABLE_TYPES",
    "BackendOutcome",
    "BOX_REQUIRES_IMAGE_DETAIL",
    "BOX_REQUIRES_IMAGE_REASON",
    "CONFIDENCE_SOURCE_API",
    "DECISIONS_PATH",
    "DECISIONS_TRANSPORT",
    "DEFAULT_MODEL",
    "DecisionBackend",
    "DecisionConfig",
    "DECISION_TYPES_LOCAL",
    "_DECISION_IMPORT_ERROR",
    "HttpResponse",
    "PROBE_TARGETS",
    "TIMI_AUTH_FIELD",
    "TIMI_AUTH_JSON",
    "TIMI_BASE_URL",
    "TimiDecisionsBackend",
    "TransportConnectionError",
    "TransportTimeout",
    "credential_status",
    "probe_matrix",
    "resolve_timi_api_key",
]
