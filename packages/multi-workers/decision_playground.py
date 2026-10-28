"""decision_playground.py - the DP test playground provider (T06 of mw-decision-dashboard).

The dashboard's "DP 测试" tab must let a human pick any registered decision
point, generate and fill a decision book, validate it without spending a model
call, and then *explicitly* submit it through the real internal decision chain
while everything production stays untouched. This module is that provider. It
is injected into ``decision_monitor.MonitorDeps.playground`` and implements the
seam's protocol exactly::

    scaffold(dp) -> dict                 # registry-typed book skeleton, no call
    validate(dp, book) -> dict           # in-memory review, no call, no write
    submit(request) -> dict              # explicit human observe-only submission
    submission(submission_id) -> dict|None   # one submission's status/result
    history() -> dict                    # this project's isolated test records

Only ``/api/test/submit`` ever reaches :meth:`submit`; opening, scrolling,
scaffolding, validating, polling and reading history spend zero model calls.

Design decisions implemented here (design.md D-002/D-003, §4.2, §5.3, §9):

* **one credential snapshot per submission.** ``decision.credential_snapshot``
  is resolved once, and that same object feeds the book gate
  (``decision.known_secret_redactor``), the trusted capture redactor
  (``decision.credential_redactor``) and the client pin. The redactors are
  built internally from that snapshot; no HTTP payload, third-party callback or
  caller-supplied redactor is ever accepted (the any-callback wire hardening
  stays T13 debt - this module does not claim it).
* **the real internal chain, never the executor.** ``decide_for(..., intent=
  "answer", archive=False, observation=Observation(...))`` is the only call
  path: the typed/closed-key/budget/answer gates stay in force, the per-dp
  authorization gate is the one documented observation bypass, and the
  executor is never reached. ``acquire``/``consume`` facts are not manufactured.
* **isolated test sinks.** Everything is written to
  ``<control>/.mw/decide-test/{wire,evidence}.jsonl`` through a ``scope_kind=
  "test"`` :class:`decision_wire.WireScope` that refuses production paths; no
  archive, sign-off, triage or authorization file is touched.
* **start before send, dedupe in the lock.** ``submit_id`` de-duplication and
  the ``submission-start`` row are done while holding the submission lock, then
  the lock is released (no network under a file lock). A failed start row means
  zero network. A later record failure returns ``record-failed`` with the real
  outcome attached, never a fabricated success.
* **one running submission, zero queue.** A second ``submit`` while one runs
  answers ``busy`` without writing a submission or spending a call.
* **validation == submission security.** :meth:`validate` and :meth:`submit`
  call the very same :meth:`_review`: ``decision_book.check_book`` (closed keys,
  declared types/enums, placeholders, evidence, budget, secrets), a descendant
  scan of declared ``object`` subtrees (T10b N2) and the registry gate on the
  exact state that would be sent. A book it refuses never reaches the transport.
* **no ambiguous joins.** A submission is identified by its ``submit_id``
  (``decision_id`` is the deterministic ``<dp>:<submit_id>`` slot); every
  ledger row carries it via the scope, so history never guesses "the most
  recent call". ``book_ref`` comes from the decision's own snapshot row.

Two limits are deliberate and reported rather than papered over:

* the book's top-level ``context`` block is validated (slots, sizes, evidence,
  secrets) but **not sent**: the T05 observation book gate joins
  ``book["state"]`` with the sent state, and design D-003 declares context
  "discardable prose". ``validate``/``submit`` report ``context_sent: false``
  plus the used slots, so nothing silently disappears.
* the answer text is returned by the live ``submit`` response; the wire ledger
  records ``answers_present``/confidence only, so polling cannot re-join an
  answer without guessing (T02 would have to store it on ``call-end``).
"""

from __future__ import annotations

import dataclasses
import datetime
import hashlib
import json
import os
import pathlib
import re
import threading
from typing import Callable, Mapping

import decision
import decision_book
import decision_points
import decision_wire
import mw_common

#: Isolated test side-ledger root, relative to the control root (design D-002).
TEST_ROOT_RELATIVE_PATH = pathlib.Path(".mw") / "decide-test"
#: Submission lock (de-duplication + start row); never held across the network.
SUBMISSION_LOCK_NAME = "submissions.lock"
SUBMISSION_LOCK_RETRIES = 5
SUBMISSION_LOCK_BASE_DELAY = 0.008
SUBMISSION_LOCK_BUDGET_S = 0.25

#: Explicit human observe-only submission (design §4.3/§4.4).
OBSERVE_ONLY = True
SUBMIT_ACTOR: tuple[str, str] = ("human", "user-explicit")

#: Closed submission states (``running`` = start row only, ``unfinished`` = a
#: start row from a process that is gone).
SUBMISSION_STATES = (
    "running",
    "unfinished",
    "succeeded",
    "rejected",
    "unavailable",
    "failed",
    "record-failed",
    "busy",
)

#: Closed set of the submit request (the monitor enforces the same set).
#: Request keys accepted by :meth:`DecisionPlayground.submit`.
REQUEST_KEYS = frozenset({"dp", "book", "submit_id", "observe_only", "retry_of", "questions"})

#: Execution/authorization key vocabulary (AC-017). Same closed set the monitor
#: applies structurally; this module owns the *depth* coverage inside declared
#: ``object`` subtrees that the monitor leaves to the provider (T10b N2). The
#: parity is locked by ``test_the_smuggling_vocabulary_covers_the_monitor_seam``.
EXECUTION_KEYS = frozenset(
    {
        "act",
        "acted",
        "action",
        "apply",
        "args",
        "archive",
        "authority",
        "authorization",
        "authorize",
        "executor",
        "exec",
        "project",
        "project_id",
        "actor",
        "write_path",
        "book_path",
        "command",
    }
)

#: Issue codes this provider may report: the seven book codes plus its own two
#: (a refused execution/authorization key, and an unprovable capture) and the
#: request-contract refusal. No second book vocabulary is invented.
PLAYGROUND_ISSUE_CODES = frozenset(
    {
        *decision_book.ISSUE_CODES,
        "forbidden-field",
        "capture-unavailable",
        "invalid-request",
        "record-failed",
        # T10: the observation-only question override gate. ``question-field``
        # is an illegal shape/value; ``question-conflict`` is a second-authority
        # disagreement (the one candidate source stays state/registry);
        # ``question-secret`` means the edited text matched the known-secret gate.
        "question-field",
        "question-conflict",
        "question-secret",
    }
)

#: How many isolated test records ``history()`` returns (newest last).
HISTORY_LIMIT = 50

#: Per-submission result projection (T11b). The wire ledger's closed
#: ``submission-end`` schema has no answer field, so the playground persists the
#: *safe* projection of that one submission next to the ledger: one file per
#: ``submission_id``, written at ``submission-end`` time, redacted with the
#: submission's frozen redactors before anything is serialised. Nothing raw is
#: copied: no request body, no response body, no credential, no book text.
RESULTS_DIR_NAME = "submission-results"
PROJECTION_VERSION = 1
#: Character ceiling per free-text leaf of the projection (redact, then clip).
PROJECTION_TEXT_LIMIT = 2048
#: Outcome keys copied into the projection (the same safe view ``_outcome_view``
#: returns; ``observation``/book internals are deliberately not copied).
PROJECTION_OUTCOME_KEYS = (
    "status",
    "escalated_reason",
    "mode",
    "confidence_source",
    "latency_ms",
    "truncated",
    "archive_state",
    "capture_channel",
    "transport_reason",
    "detail",
    "preview",
    "response",
    "answers_present",
    "call_id",
    "book_ref",
    "state_digest",
    "decision_id",
)

_SUBMIT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_MISSING = object()


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclasses.dataclass(frozen=True)
class PlaygroundIssue:
    """One explicit refusal/validation issue (value-free detail text)."""

    code: str
    path: str
    detail: str

    def __post_init__(self) -> None:
        if self.code not in PLAYGROUND_ISSUE_CODES:
            raise ValueError(f"unknown playground issue code {self.code!r}")

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "path": self.path, "detail": self.detail}


@dataclasses.dataclass(frozen=True)
class Credentials:
    """One submission's resolved credential facts (in memory only).

    ``snapshot`` is the single object the book gate, the capture redactor and
    the client pin all read (T05j/T05n/T05o/T05p); nothing here is persisted or
    echoed. ``capture_redactor`` may be ``None`` (metadata-only capture) - the
    submit path then refuses instead of sending material it cannot prove safe.
    """

    cfg: decision.DecisionConfig
    snapshot: decision.CredentialSnapshot
    gate_redactor: object
    capture_redactor: object | None


@dataclasses.dataclass(frozen=True)
class Review:
    """The shared verdict of ``validate`` and ``submit`` (one authority).

    ``questions`` is the normalised observation-only question override (``None``
    when the caller sent none: the registry set is used), so submit hands
    ``decide_for`` exactly the set this review validated.
    """

    dp: str
    issues: tuple[PlaygroundIssue, ...]
    sent_state: dict | None
    state_bytes: int | None
    state_digest: str | None
    context_slots: tuple[str, ...]
    credentials: Credentials | None
    questions: dict[str, dict] | None = None

    @property
    def ok(self) -> bool:
        return not self.issues


@dataclasses.dataclass(frozen=True)
class _Start:
    """Outcome of the locked de-duplicate + ``submission-start`` step."""

    kind: str  # "written" | "duplicate" | "failed" | "invalid-retry"
    record: dict | None = None
    error_class: str | None = None
    detail: str | None = None
    started_at: str | None = None


def _now_ts() -> str:
    """Same timestamp shape the side ledger writes (UTC, millisecond)."""
    return datetime.datetime.now(datetime.UTC).isoformat(timespec="milliseconds")


# ---------------------------------------------------------------------------
# Result projection sanitising (T11b)
# ---------------------------------------------------------------------------


class _ProjectionError(Exception):
    """The projection cannot be proven safe; nothing is persisted."""


#: Words indicating a *consistency* conflict (a second authority disagreeing
#: with the registry/state), as opposed to an illegal shape/value.
_QUESTION_CONFLICT_MARKERS = ("conflict", "one candidate source", "must name exactly")


def _question_issue_code(issue: str) -> str:
    """Map one override issue text onto the closed playground issue code set."""
    return (
        "question-conflict"
        if any(marker in issue for marker in _QUESTION_CONFLICT_MARKERS)
        else "question-field"
    )


def _questions_secret_issue(
    questions: Mapping[str, Mapping], redactor: object
) -> PlaygroundIssue | None:
    """Refuse an edited question set the known-secret gate recognizes.

    The gate sees the *normalised* set (what would actually be sent). The issue
    carries no value: only the fact and the field label, so a refusal never
    echoes the secret it refused.
    """
    redact = getattr(redactor, "redact", None)
    if not callable(redact):
        return PlaygroundIssue(
            "question-secret",
            "questions",
            "the known-secret gate is unavailable, so the edited questions cannot be "
            "proven safe; nothing is sent",
        )
    try:
        text = json.dumps(questions, ensure_ascii=False, sort_keys=True, default=str)
        hits = int(getattr(redact(text), "hits", 0) or 0)
    except Exception:  # noqa: BLE001 - an unusable filter proves nothing
        hits = 1
    if not hits:
        return None
    return PlaygroundIssue(
        "question-secret",
        "questions",
        "the edited questions match the known-secret gate; nothing is sent",
    )


def _frozen_redactors(credentials: Credentials | None) -> tuple[object, ...]:
    """The submission's frozen redactor legs (gate first, then capture)."""
    if credentials is None:
        return ()
    legs = (credentials.gate_redactor, credentials.capture_redactor)
    return tuple(leg for leg in legs if leg is not None)


def _redact_all(redactors: tuple[object, ...], text: str) -> tuple[str | None, int]:
    """Apply every frozen leg until it is stable (``None`` = fail closed)."""
    hits = 0
    current = text
    for redactor in redactors:
        for _ in range(3):
            try:
                result = redactor.redact(current)  # type: ignore[attr-defined]
            except Exception:  # noqa: BLE001 - an unusable filter proves nothing
                return None, hits
            found = int(getattr(result, "hits", 0) or 0)
            hits += found
            candidate = getattr(result, "text", None)
            if not isinstance(candidate, str):
                return None, hits
            if candidate == current:
                break
            current = candidate
    return current, hits


def _clip_projection_text(
    redactors: tuple[object, ...], text: str
) -> tuple[str, bool]:
    """Clip to the projection budget, scrubbing the cut boundary first."""
    if len(text) <= PROJECTION_TEXT_LIMIT:
        return text, False
    clipped = text[:PROJECTION_TEXT_LIMIT]
    for redactor in redactors:
        scrub = getattr(redactor, "scrub_tail_prefix", None)
        if callable(scrub):
            try:
                clipped, _flag = scrub(clipped)
            except Exception:  # noqa: BLE001 - an unprovable tail is dropped
                return "", True
    return clipped, True


def _sanitize_projection(
    redactors: tuple[object, ...],
    value: object,
    marks: dict[str, object],
    path: str,
) -> object:
    """Redact (then clip) every string leaf *and* mapping key of the projection."""
    if isinstance(value, str):
        clean, hits = _redact_all(redactors, value)
        if clean is None:
            raise _ProjectionError("redaction failed")
        clipped, truncated = _clip_projection_text(redactors, clean)
        marks["hits"] = int(marks["hits"]) + hits
        if truncated:
            truncated_fields = marks["truncated_fields"]
            assert isinstance(truncated_fields, list)
            truncated_fields.append(path or "<root>")
        return clipped
    if isinstance(value, Mapping):
        out: dict[str, object] = {}
        for key, item in value.items():
            name, key_hits = _redact_all(redactors, str(key))
            if name is None:
                raise _ProjectionError("key redaction failed")
            name, _truncated = _clip_projection_text(redactors, name)
            marks["hits"] = int(marks["hits"]) + key_hits
            child = f"{path}.{name}" if path else name
            if name in out:
                # A redacted key collided with another key: withhold both
                # (never overwrite, never fabricate a value).
                out.pop(name, None)
                continue
            out[name] = _sanitize_projection(redactors, item, marks, child)
        return out
    if isinstance(value, (list, tuple)):
        return [
            _sanitize_projection(redactors, item, marks, f"{path}[{index}]")
            for index, item in enumerate(value)
        ]
    return value


# ---------------------------------------------------------------------------
# Declared free-object subtrees (T10b N2)
# ---------------------------------------------------------------------------


def _declared_paths(dp: str) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            (
                *decision_points.REQUIRED_STATE_FIELDS.get(dp, ()),
                *decision_points.OPTIONAL_STATE_FIELDS.get(dp, ()),
            )
        )
    )


def free_object_paths(dp: str) -> tuple[str, ...]:
    """Declared paths whose *whole subtree* is free-form.

    ``object`` fields (dp1 ``history``) and arrays of ``object`` (dp2
    ``progress.trend``) accept undeclared descendants, so the closed-key gate
    cannot see inside them: they are exactly the subtrees this module scans.
    """
    paths: list[str] = []
    for path in _declared_paths(dp):
        spec = decision_points.STATE_FIELD_DESCRIPTIONS.get(path) or {}
        kind = spec.get("type")
        if kind == "object" or (kind == "array" and spec.get("item_type") == "object"):
            paths.append(path)
    return tuple(paths)


def _lookup(state: object, dotted: str) -> object:
    current = state
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _scan_execution_keys(
    node: object,
    path: str,
    display: str,
    redactor: object | None,
    found: list[str],
) -> None:
    """Collect display paths of execution/authorization keys at any depth.

    ``path`` decides membership on the raw keys; ``display`` is the value-free
    form (array indices stay readable, arbitrary key text collapses).
    """
    if isinstance(node, Mapping):
        for key, value in node.items():
            name = str(key)
            child_path = f"{path}.{name}"
            child_display = f"{display}.{decision.safe_path_text(name, redactor)}"
            if isinstance(key, str) and key in EXECUTION_KEYS:
                found.append(child_display)
            _scan_execution_keys(value, child_path, child_display, redactor, found)
        return
    if isinstance(node, (list, tuple)):
        for index, item in enumerate(node):
            _scan_execution_keys(
                item, f"{path}[{index}]", f"{display}[{index}]", redactor, found
            )


def object_smuggle_paths(
    dp: str, state: object, redactor: object | None = None
) -> tuple[str, ...]:
    """Execution/authorization keys found inside a declared free subtree.

    Legitimate business data (dp1 counter keys, dp2 trend points) is untouched:
    only the closed execution/authorization vocabulary is refused, at any
    depth, as a key. Display paths never echo arbitrary or credential-looking
    key text (``decision.safe_path_text``), so a refusal cannot leak material.
    """
    found: list[str] = []
    for path in free_object_paths(dp):
        value = _lookup(state, path)
        if value is _MISSING or value is None:
            continue
        _scan_execution_keys(value, path, path, redactor, found)
    seen: list[str] = []
    for path in found:
        if path not in seen:
            seen.append(path)
    return tuple(seen)


# ---------------------------------------------------------------------------
# The provider
# ---------------------------------------------------------------------------


class DecisionPlayground:
    """The DP test playground behind ``decision_monitor``'s seam.

    ``control_root`` is resolved through ``mw_common.resolve_control_root``
    (fail-closed: no second archive tree). ``backend`` / ``backend_factory`` are
    the transport injection points (production leaves both ``None`` so the real
    configured backend is used; tests inject a scripted backend and never touch
    the network). One instance serves one control root; calls are serialized to
    "one running submission, zero queue".
    """

    def __init__(
        self,
        control_root: pathlib.Path | str,
        *,
        backend: decision.DecisionBackend | None = None,
        backend_factory: Callable[[decision.DecisionConfig], decision.DecisionBackend | None]
        | None = None,
        warn: Callable[[str], None] | None = None,
        lock_budget_s: float = SUBMISSION_LOCK_BUDGET_S,
    ) -> None:
        self.raw_root = pathlib.Path(control_root)
        resolved, self.root_source = mw_common.resolve_control_root(
            control_root, require_control=True
        )
        self.control_root = pathlib.Path(resolved)
        self.project_id = decision_wire.project_id_for(self.control_root)
        self.test_root = self.control_root / TEST_ROOT_RELATIVE_PATH
        self._backend = backend
        self._backend_factory = backend_factory
        self._warn = warn
        self._lock_budget_s = float(lock_budget_s)
        #: "one executing + zero queued": a second concurrent submit is refused.
        self._exec_lock = threading.Lock()
        self._inflight: set[str] = set()

    # -- diagnostics -------------------------------------------------------

    def _notify(self, message: str) -> None:
        if self._warn is None:
            return
        try:
            self._warn(message)
        except Exception:  # noqa: BLE001 - a warning sink never breaks the provider
            pass

    def _config(self) -> decision.DecisionConfig:
        cfg, _error = decision.DecisionConfig.from_project(self.control_root)
        return cfg

    def _credentials(self) -> Credentials:
        """Resolve the single credential snapshot of one submission."""
        cfg = self._config()
        snapshot = decision.credential_snapshot(cfg)
        legacy = decision_points.known_secret_superset(snapshot)
        return Credentials(
            cfg=cfg,
            snapshot=snapshot,
            gate_redactor=decision.known_secret_redactor(
                cfg, extra_secrets=legacy, snapshot=snapshot
            ),
            capture_redactor=decision.credential_redactor(
                cfg, extra_secrets=legacy, snapshot=snapshot
            ),
        )

    @staticmethod
    def _transport_state(cfg: decision.DecisionConfig | None) -> dict[str, str]:
        if cfg is None or not cfg.is_configured:
            detail = (cfg.config_error if cfg is not None else None) or (
                "decision transport disabled (.mw/decide.json missing or enabled=false)"
            )
            return {"state": "unavailable", "detail": detail}
        return {
            "state": "unknown",
            "detail": (
                "transport configured but not probed: the playground never calls "
                "before an explicit submit"
            ),
        }

    # -- protocol: scaffold ------------------------------------------------

    def scaffold(self, dp: str) -> dict:
        """Registry-typed book skeleton for one dp (no model call, no write).

        Raises ``decision.DecisionInputError`` for an unknown dp id; the monitor
        refuses unknown ids before it reaches this provider.
        """
        point = decision_points.get_decision_point(dp)
        cfg = self._config()
        effective = decision_points.load_points_config(self.control_root).effective(point)
        return {
            "dp": point.id,
            "book": decision_book.scaffold_book(point.id),
            "questions": decision_points.questions_map(point),
            "questions_version": point.questions_version,
            "tier": point.tier,
            "description": point.description,
            "default_enabled": point.default_enabled,
            "default_mode": point.default_mode,
            "enabled": effective.enabled,
            "mode": effective.mode,
            "config_source": effective.source,
            "required_state_fields": decision_book.required_fields(point.id),
            "optional_state_fields": decision_book.optional_fields(point.id),
            "context_slots": list(decision_book.context_slots(point.id)),
            "max_state_bytes": decision_points.MAX_STATE_BYTES,
            "transport": self._transport_state(cfg),
            "observe_only": OBSERVE_ONLY,
        }

    # -- the shared review -------------------------------------------------

    def _review(
        self,
        dp: str,
        book: object,
        credentials: Credentials | None = None,
        questions: Mapping[str, object] | None = None,
    ) -> Review:
        """The single validation used by ``validate`` *and* ``submit``.

        Order: dp identity, the closed book contract (``check_book``), the
        execution/authorization scan of declared free-object subtrees (T10b
        N2), then the registry gate on the exact state that would be sent plus
        the no-truncation budget. A refused book never reaches the transport.
        """
        credentials = credentials if credentials is not None else self._credentials()
        try:
            point = decision_points.get_decision_point(dp)
        except decision.DecisionInputError:
            return Review(
                dp=dp,
                issues=(
                    PlaygroundIssue(
                        "book-schema", "decision_point", f"unknown decision point {dp!r}"
                    ),
                ),
                sent_state=None,
                state_bytes=None,
                state_digest=None,
                context_slots=(),
                credentials=credentials,
            )
        issues: list[PlaygroundIssue] = []
        if not isinstance(book, Mapping):
            return Review(
                dp=dp,
                issues=(
                    PlaygroundIssue(
                        "book-schema",
                        "book",
                        f"book must be a JSON object, got {type(book).__name__}",
                    ),
                ),
                sent_state=None,
                state_bytes=None,
                state_digest=None,
                context_slots=(),
                credentials=credentials,
            )
        if book.get("decision_point") != dp:
            issues.append(
                PlaygroundIssue(
                    "book-schema",
                    "decision_point",
                    f"book is for {book.get('decision_point')!r}, not {dp!r}",
                )
            )
        for issue in decision_book.check_book(
            book, project_dir=self.control_root, redactor=credentials.gate_redactor
        ):
            issues.append(PlaygroundIssue(issue.code, issue.path, issue.detail))

        state = book.get("state")
        sent_state: dict | None = None
        state_bytes: int | None = None
        state_digest: str | None = None
        reviewed_questions: dict[str, dict] | None = None
        if isinstance(state, Mapping):
            for path in object_smuggle_paths(dp, state, credentials.gate_redactor):
                issues.append(
                    PlaygroundIssue(
                        "forbidden-field",
                        f"state.{path}",
                        "execution/authorization key inside a declared object subtree; "
                        "the playground never executes or authorizes",
                    )
                )
            sent_state = point.build_state(decision_points.Trigger.from_mapping(dict(state)))
            # Defense in depth over the send surface itself: the book contract
            # above is the authority, this re-runs the same registry gate on the
            # exact object the transport would receive.
            for path, detail in decision_points.state_field_issues(dp, sent_state):
                issues.append(PlaygroundIssue("book-state", f"state.{path}", detail))
            for path, detail in decision_points.state_identity_issues(dp, sent_state):
                issues.append(PlaygroundIssue("book-state", f"state.{path}", detail))
            for path, detail in decision_points.state_unknown_key_issues(
                dp, sent_state, allow_context=True, redactor=credentials.gate_redactor
            ):
                issues.append(PlaygroundIssue("book-state", f"state.{path}", detail))
            state_bytes = len(decision._encode_state(sent_state))
            state_digest = decision_book.state_digest(sent_state)
            if state_bytes > decision_points.MAX_STATE_BYTES:
                issues.append(
                    PlaygroundIssue(
                        "book-budget",
                        "state",
                        f"{state_bytes} bytes > {decision_points.MAX_STATE_BYTES} bytes; the "
                        "observation send state must fit without truncation (a truncated "
                        "state would no longer be the book state)",
                    )
                )

        context_slots: tuple[str, ...] = ()
        merged = decision_book.book_state(book)
        context = merged.get("context")
        if isinstance(context, Mapping):
            context_slots = tuple(str(name) for name in context)

        # T10: the observation-only question override. The DP mapping, legal
        # types, bounded instructions, legal criteria and the legal choice set
        # are validated against the state that would be sent; dp3 keeps
        # state.handling_options as its only candidate source. A refused
        # override adds issues here, so submit can never send a set validate
        # did not accept.
        if questions is not None:
            override = decision_points.resolve_question_override(
                dp, questions, sent_state if sent_state is not None else {}
            )
            if override.issues:
                for path, issue in override.issues:
                    issues.append(
                        PlaygroundIssue(_question_issue_code(issue), path, issue)
                    )
            else:
                reviewed_questions = override.questions
                if credentials is not None and reviewed_questions is not None:
                    secret_issue = _questions_secret_issue(
                        reviewed_questions, credentials.gate_redactor
                    )
                    if secret_issue is not None:
                        issues.append(secret_issue)

        unique: list[PlaygroundIssue] = []
        seen: set[tuple[str, str, str]] = set()
        for issue in issues:
            key = (issue.code, issue.path, issue.detail)
            if key in seen:
                continue
            seen.add(key)
            unique.append(issue)
        return Review(
            dp=dp,
            issues=tuple(unique),
            sent_state=sent_state,
            state_bytes=state_bytes,
            state_digest=state_digest,
            context_slots=context_slots,
            credentials=credentials,
            questions=reviewed_questions,
        )

    # -- protocol: validate ------------------------------------------------

    def validate(
        self,
        dp: str,
        book: object,
        questions: Mapping[str, object] | None = None,
    ) -> dict:
        """In-memory book review: no model call, no ledger write, no send.

        ``questions`` (T10) is the optional observation-only question override;
        omitting it keeps the registry question set, exactly as before. The
        returned ``request_preview`` is ``{model, state, questions}`` built by
        the *same* payload builder the send path uses (the resolved backend's
        ``build_payload``), with the same model projection
        (``decision_points.send_state``); nothing is sent and no model is
        called. A preview that cannot be built says so in
        ``request_preview_reason`` instead of approximating a request.
        """
        review = self._review(dp, book, questions=questions)
        payload: dict[str, object] = {
            "dp": dp,
            "ok": review.ok,
            "issues": [issue.as_dict() for issue in review.issues],
            "state_bytes": review.state_bytes,
            "max_state_bytes": decision_points.MAX_STATE_BYTES,
            "state_digest": review.state_digest,
            "context_slots": list(review.context_slots),
            "context_sent": False,
            "transport": self._transport_state(
                review.credentials.cfg if review.credentials is not None else None
            ),
            "observe_only": OBSERVE_ONLY,
        }
        try:
            point = decision_points.get_decision_point(dp)
        except decision.DecisionInputError:
            point = None
        if point is not None:
            final_questions = review.questions or decision_points.questions_map(point)
            payload["questions"] = final_questions
            payload["questions_source"] = "override" if review.questions else "registry"
            payload["questions_version"] = point.questions_version
            preview, reason = self._request_preview(review, final_questions)
            payload["request_preview"] = preview
            payload["request_preview_reason"] = reason
        if review.context_slots:
            payload["context_note"] = (
                "the validated context slots are not sent: the observation book gate "
                "joins book.state with the sent state and design D-003 declares context "
                "discardable prose"
            )
        return payload

    def _request_preview(
        self, review: Review, questions: Mapping[str, dict]
    ) -> tuple[dict | None, str | None]:
        """The final ``{model, state, questions}`` body this submission would send.

        Deliberately the production path, not a lookalike: the state is
        ``decision_points.send_state`` (the projection + budget fit
        ``decide_for`` applies) and the body is the resolved backend's
        ``build_payload`` - the same call ``decide`` makes before its HTTP POST.
        Nothing here dials, sends or invokes a model.
        """
        if review.credentials is None:
            return None, "no credential unit was resolved for this review"
        if not review.ok:
            return None, "the book/questions were refused, so no request would be built"
        if review.sent_state is None:
            return None, "no sent state was built from the book"
        cfg = review.credentials.cfg
        if not cfg.is_configured:
            return None, "the decision transport is not configured; nothing would be sent"
        projected, _dropped, size = decision_points.send_state(review.dp, review.sent_state)
        if size > decision_points.MAX_STATE_BYTES:
            return None, "the projected state exceeds the send budget; nothing would be sent"
        dynamic = decision_points.dynamic_choice_labels(questions, projected)
        if dynamic is None:
            return None, "the dynamic candidates cannot be rendered from the projected state"
        # The client owns the one backend-resolution path (never a second
        # resolver here): a preview may not describe a different backend than
        # the send would use.
        client = self._client(review.credentials, None)
        backend = client._resolve_backend()
        build_payload = getattr(backend, "build_payload", None)
        if not callable(build_payload):
            return None, "the resolved transport exposes no payload builder"
        try:
            payload = build_payload(projected, dict(questions), cfg, dynamic=dynamic)
        except Exception as exc:  # noqa: BLE001 - a preview never crashes the page
            return None, f"the payload builder refused the material ({type(exc).__name__})"
        if not isinstance(payload, Mapping):
            return None, "the payload builder returned no request body"
        preview = {
            "model": payload.get("model"),
            "state": payload.get("state"),
            "questions": payload.get("questions"),
        }
        redactors = _frozen_redactors(review.credentials)
        if redactors:
            stats: dict[str, object] = {"hits": 0, "truncated_fields": []}
            try:
                safe = _sanitize_projection(redactors, preview, stats, "request_preview")
            except _ProjectionError:
                return None, "the preview could not be proven safe; nothing is sent"
            if isinstance(safe, Mapping):
                preview = dict(safe)
        return preview, None

    # -- protocol: submit --------------------------------------------------

    def submit(self, request: Mapping[str, object]) -> dict:
        """Explicit human observe-only submission of one validated book."""
        refusal = self._request_refusal(request)
        if refusal is not None:
            return refusal
        dp = str(request["dp"])
        book = request["book"]
        submit_id = str(request["submit_id"])
        retry_of = request.get("retry_of")
        questions = request.get("questions")

        if not self._exec_lock.acquire(blocking=False):
            payload = self._base_payload(dp=dp, submit_id=submit_id, retry_of=retry_of)
            payload.update(
                state="busy",
                accepted=False,
                busy=True,
                zero_call=True,
                record_status="not-recorded",
                message=(
                    "one submission is already running: nothing was queued and no model "
                    "call was made"
                ),
            )
            return payload

        self._inflight.add(submit_id)
        try:
            scope = self._scope(dp, submit_id)
            start = self._start(scope, dp, submit_id, retry_of)
            if start.kind == "duplicate" and start.record is not None:
                return self._record_payload(start.record, duplicate=True)
            if start.kind == "invalid-retry":
                payload = self._base_payload(dp=dp, submit_id=submit_id, retry_of=retry_of)
                payload.update(
                    state="rejected",
                    accepted=False,
                    zero_call=True,
                    record_status="not-recorded",
                    issues=[
                        PlaygroundIssue(
                            "invalid-request",
                            "retry_of",
                            start.detail or "retry_of must name an earlier submission",
                        ).as_dict()
                    ],
                )
                return payload
            if start.kind == "failed":
                payload = self._base_payload(dp=dp, submit_id=submit_id, retry_of=retry_of)
                payload.update(
                    state="record-failed",
                    accepted=False,
                    zero_call=True,
                    record_status="failed",
                    issues=[
                        PlaygroundIssue(
                            "record-failed",
                            "submission-start",
                            "the submission-start row could not be written "
                            f"({start.error_class or 'append'}); no model call was made",
                        ).as_dict()
                    ],
                )
                return payload

            # The start row is durable: from here on every exit is finished with
            # an explicit submission-end row (or record-failed).
            try:
                credentials = self._credentials()
            except Exception as exc:  # noqa: BLE001 - fail closed, zero send
                return self._finish(
                    scope,
                    dp=dp,
                    submit_id=submit_id,
                    retry_of=retry_of,
                    state="failed",
                    zero_call=True,
                    started_at=start.started_at,
                    issues=[
                        PlaygroundIssue(
                            "capture-unavailable",
                            "credentials",
                            f"credential setup raised {type(exc).__name__}; nothing was sent",
                        )
                    ],
                )
            if credentials.capture_redactor is None:
                return self._finish(
                    scope,
                    dp=dp,
                    submit_id=submit_id,
                    retry_of=retry_of,
                    state="rejected",
                    zero_call=True,
                    started_at=start.started_at,
                    issues=[
                        PlaygroundIssue(
                            "capture-unavailable",
                            "credentials",
                            "no trusted capture redactor could be built from this "
                            "submission's credential snapshot, so captured text cannot be "
                            "proven safe; nothing was sent",
                        )
                    ],
                )
            scope.redact = credentials.capture_redactor

            review = self._review(dp, book, credentials, questions)
            if not review.ok:
                return self._finish(
                    scope,
                    dp=dp,
                    submit_id=submit_id,
                    retry_of=retry_of,
                    state="rejected",
                    zero_call=True,
                    issues=list(review.issues),
                    state_digest=review.state_digest,
                    started_at=start.started_at,
                )

            client = self._client(credentials, scope)
            observation = decision_points.Observation(
                scope=scope,
                submission_id=submit_id,
                book=dict(book),
                actor_kind=SUBMIT_ACTOR[0],
                actor_id=SUBMIT_ACTOR[1],
            )
            trigger = decision_points.Trigger.from_mapping(
                dict(review.sent_state or {}), trigger_id=submit_id
            )
            try:
                outcome = decision_points.decide_for(
                    dp,
                    trigger,
                    self.control_root,
                    client=client,
                    archive=False,
                    intent="answer",
                    observation=observation,
                    # The *normalised* set this review accepted: only the
                    # instructions can differ, everything else is regenerated
                    # by the registry/state builder on the send path.
                    questions=review.questions,
                )
            except Exception as exc:  # noqa: BLE001 - an explicit failure, never a crash
                detail = str(exc)
                try:
                    detail = credentials.gate_redactor.redact(detail).text
                except Exception:  # noqa: BLE001 - a broken filter never leaks text
                    detail = type(exc).__name__
                self._notify(
                    f"decision-playground: submission {submit_id} raised {type(exc).__name__}"
                )
                return self._finish(
                    scope,
                    dp=dp,
                    submit_id=submit_id,
                    retry_of=retry_of,
                    state="failed",
                    zero_call=None,
                    started_at=start.started_at,
                    issues=[
                        PlaygroundIssue(
                            "invalid-request",
                            "submission",
                            f"{type(exc).__name__}: {detail}"[:400],
                        )
                    ],
                )

            state = self._classify(outcome)
            http_attempts = int(getattr(client, "last_wire_attempts", 0) or 0)
            view = self._outcome_view(outcome)
            issues: list[PlaygroundIssue] = []
            if state == "rejected":
                detail = outcome.detail
                try:
                    detail = credentials.gate_redactor.redact(detail).text
                except Exception:  # noqa: BLE001
                    detail = "illegal material"
                issues.append(
                    PlaygroundIssue(
                        "book-state",
                        "state",
                        detail[:400] or "the decision refused the material before sending",
                    )
                )
            return self._finish(
                scope,
                dp=dp,
                submit_id=submit_id,
                retry_of=retry_of,
                state=state,
                zero_call=outcome.call_id is None,
                issues=issues,
                outcome=view,
                book_ref=outcome.snapshot_ref,
                state_digest=outcome.state_digest,
                http_attempts=http_attempts,
                capture_status=outcome.capture_status,
                decision_id=outcome.decision_id,
                decision_ran=True,
                started_at=start.started_at,
                credentials=credentials,
            )
        finally:
            self._inflight.discard(submit_id)
            self._exec_lock.release()

    # -- protocol: status / history ---------------------------------------

    def submission(self, submission_id: str) -> dict | None:
        """One submission's recorded status (no model call, no write)."""
        if not isinstance(submission_id, str) or not _SUBMIT_ID_RE.match(submission_id):
            return None
        record = self._submission_records().get(submission_id)
        if record is None:
            return None
        return self._record_payload(record)

    def history(self) -> dict:
        """This control root's isolated test records (newest last).

        The list view carries the same facts as ``submission()`` except the
        captured request/response *bodies*: those are replaced by an
        ``output_omitted`` mark so one page of records stays bounded. The bodies
        stay readable on the single submission detail (the ledger is still the
        only writer).
        """
        records = list(self._submission_records().values())
        records.sort(key=lambda record: (record.get("started_at") or "",))
        records = records[-HISTORY_LIMIT:]
        return {
            "source": "test",
            "scope": "test",
            "observe_only": OBSERVE_ONLY,
            "records": [self._history_record(record) for record in records],
            "total": len(records),
            "limit": HISTORY_LIMIT,
            "warnings": self._ledger_warnings(),
        }

    @staticmethod
    def _history_record(record: Mapping[str, object]) -> dict:
        """List view of one record: capture bodies replaced by an omit mark."""
        out = dict(record)
        attempts: list[dict] = []
        for entry in record.get("attempts") or []:  # type: ignore[union-attr]
            item = dict(entry)
            for key in ("request", "response"):
                capture = item.get(key)
                if isinstance(capture, Mapping) and capture.get("text") is not None:
                    stripped = {
                        name: value for name, value in capture.items() if name != "text"
                    }
                    stripped["output_omitted"] = True
                    item[key] = stripped
            attempts.append(item)
        out["attempts"] = attempts
        return out

    # -- request contract --------------------------------------------------

    def _request_refusal(self, request: object) -> dict | None:
        if not isinstance(request, Mapping):
            return self._refusal(
                "request", f"request must be a JSON object, got {type(request).__name__}"
            )
        raw_dp = request.get("dp")
        labelled_dp = raw_dp if isinstance(raw_dp, str) and raw_dp.strip() else ""
        unknown = sorted(str(name) for name in set(request) - REQUEST_KEYS)
        if unknown:
            return self._refusal(
                "request",
                "unknown field(s): "
                + ", ".join(_safe_names(unknown))
                + " (execution/authorization fields are never accepted)",
                dp=labelled_dp,
            )
        missing = [name for name in ("dp", "book", "submit_id") if name not in request]
        if missing:
            return self._refusal(
                "request",
                "missing field(s): " + ", ".join(_safe_names(missing)),
                dp=labelled_dp,
            )
        if not labelled_dp:
            return self._refusal("dp", "must be a non-empty string")
        submit_id = request.get("submit_id")
        if not isinstance(submit_id, str) or not _SUBMIT_ID_RE.match(submit_id):
            return self._refusal(
                "submit_id", "must be a short opaque identifier", dp=labelled_dp
            )
        if request.get("observe_only") is not True:
            return self._refusal(
                "observe_only",
                "must be true: the playground never executes a business action or edits "
                "authorization",
                dp=labelled_dp,
            )
        retry_of = request.get("retry_of")
        if retry_of is not None and (
            not isinstance(retry_of, str) or not _SUBMIT_ID_RE.match(retry_of)
        ):
            return self._refusal(
                "retry_of", "must be an earlier submission id", dp=labelled_dp
            )
        try:
            decision_points.get_decision_point(labelled_dp)
        except decision.DecisionInputError:
            return self._refusal(
                "dp", "is not a registered decision point", dp=labelled_dp
            )
        return None

    def _refusal(self, path: str, detail: str, *, dp: str = "") -> dict:
        payload = self._base_payload(dp=dp, submit_id="")
        payload.update(
            state="rejected",
            accepted=False,
            zero_call=True,
            record_status="not-recorded",
            issues=[PlaygroundIssue("invalid-request", path, detail).as_dict()],
        )
        return payload

    # -- locked start ------------------------------------------------------

    def _start(self, scope: decision_wire.WireScope, dp: str, submit_id: str,
               retry_of: object) -> _Start:
        """De-duplicate ``submit_id`` and append ``submission-start`` under lock."""
        lock = self.test_root / SUBMISSION_LOCK_NAME
        try:
            mw_common.acquire_lock(
                lock,
                retries=SUBMISSION_LOCK_RETRIES,
                base_delay=SUBMISSION_LOCK_BASE_DELAY,
                deadline_s=self._lock_budget_s,
            )
        except (OSError, RuntimeError) as exc:
            self._notify(
                f"decision-playground: submission lock unavailable ({type(exc).__name__}); "
                "refusing to send without a proven de-duplication"
            )
            return _Start(kind="failed", error_class="lock-timeout")
        try:
            records = self._submission_records()
            existing = records.get(submit_id)
            if existing is not None:
                return _Start(kind="duplicate", record=existing)
            if retry_of is not None:
                if retry_of == submit_id:
                    return _Start(
                        kind="invalid-retry", detail="a retry must use a new submission id"
                    )
                if not isinstance(retry_of, str) or retry_of not in records:
                    return _Start(
                        kind="invalid-retry",
                        detail="retry_of must name an existing submission of this project",
                    )
            started_at = _now_ts()
            result = decision_wire.record_event(
                scope,
                "submission-start",
                fields={
                    "dp": dp,
                    "outcome": "started",
                    "issues": None,
                    "retry_of": retry_of if isinstance(retry_of, str) else None,
                    "zero_call": False,
                    "book_ref": None,
                },
                actor=SUBMIT_ACTOR,
            )
            if not bool(getattr(result, "written", False)):
                return _Start(
                    kind="failed", error_class=getattr(result, "error_class", None) or "append"
                )
            return _Start(kind="written", started_at=started_at)
        finally:
            mw_common.release_lock(lock)

    # -- decision chain ----------------------------------------------------

    def _scope(self, dp: str, submit_id: str) -> decision_wire.WireScope:
        """Isolated test scope for one submission (production paths refused)."""
        scope = decision_wire.test_scope(
            self.test_root,
            project_id=self.project_id,
            submission_id=submit_id,
            dp=dp,
            evidence_path=decision_wire.test_evidence_sink(self.test_root),
            warn=self._notify,
        )
        # ``test_scope`` has no decision_id parameter; the submission id *is* the
        # explicit decision identity here (never "the most recent call"). Stamping
        # it on the scope makes every row of this submission carry the same
        # deterministic decision_id.
        scope.decision_id = f"{dp}:{submit_id}"
        return scope

    def _client(
        self, credentials: Credentials, scope: decision_wire.WireScope | None
    ) -> decision.DecisionClient:
        # ``backend_factory`` is handed to the client (not called here), so an
        # unconfigured/disabled transport never builds a backend at all - exactly
        # the production laziness. ``scope=None`` is the pure preview client: no
        # wire scope, no evidence sink, no call.
        return decision.DecisionClient(
            cfg=credentials.cfg,
            backend=self._backend,
            backend_factory=self._backend_factory,
            project_root=self.control_root,
            evidence_path=scope.evidence_path if scope is not None else None,
            wire_scope=scope,
            credential_snapshot=credentials.snapshot,
        )

    @staticmethod
    def _classify(outcome: decision_points.DecisionOutcome) -> str:
        """Map a real decision outcome onto the closed submission states."""
        if outcome.status in ("suggested", "acted"):
            return "succeeded"
        reason = outcome.escalated_reason
        if reason in ("input-incomplete", "input-oversize"):
            return "rejected"
        if reason == "unavailable":
            if outcome.call_id is None:
                return "unavailable"
            if outcome.transport_reason in (
                decision.REASON_DISABLED,
                decision.REASON_ENTRY_UNAVAILABLE,
            ):
                return "unavailable"
        return "failed"

    @staticmethod
    def _outcome_view(outcome: decision_points.DecisionOutcome) -> dict:
        """Serializable decision facts (no credential; monitor redacts again)."""
        response = dict(outcome.response or {})
        return {
            "status": outcome.status,
            "escalated_reason": outcome.escalated_reason,
            "mode": outcome.mode,
            "decision_id": outcome.decision_id,
            "answer": outcome.answer if isinstance(outcome.answer, Mapping) else None,
            "answers_present": outcome.answer is not None,
            "confidence_source": outcome.confidence_source,
            "latency_ms": outcome.latency_ms,
            "state_digest": outcome.state_digest,
            "truncated": list(outcome.truncated),
            "archive_state": outcome.archive_state,
            "capture_status": outcome.capture_status,
            "capture_channel": outcome.capture_channel,
            "call_id": outcome.call_id,
            "book_ref": outcome.snapshot_ref,
            "observation": dict(outcome.observation or {}) or None,
            "preview": dict(outcome.preview or {}) or None,
            "transport_reason": outcome.transport_reason,
            "detail": outcome.detail,
            "response": {
                key: response.get(key)
                for key in (
                    "available",
                    "transport",
                    "model",
                    "attempts",
                    "latency_ms",
                    "reason",
                    "confidence_source",
                )
                if key in response
            },
        }

    # -- submission result projection -------------------------------------

    def _projection_path(self, submission_id: str) -> pathlib.Path | None:
        if not isinstance(submission_id, str) or not _SUBMIT_ID_RE.match(submission_id):
            return None
        return self.test_root / RESULTS_DIR_NAME / f"{submission_id}.json"

    def _persist_projection(
        self,
        *,
        dp: str,
        submit_id: str,
        state: str,
        zero_call: bool | None,
        outcome: Mapping[str, object] | None,
        issues: tuple[PlaygroundIssue, ...],
        book_ref: str | None,
        state_digest: str | None,
        http_attempts: int | None,
        capture_status: str | None,
        decision_id: str | None,
        decision_ran: bool,
        started_at: str | None,
        finished_at: str,
        credentials: Credentials | None,
    ) -> dict[str, object]:
        """Persist the safe result projection of one finished submission.

        This runs at the same point as the ``submission-end`` row (the only
        persistence the playground is allowed to add). The wire ledger's closed
        schema has no answer field, so polling/``submission()``/``history()``
        could not otherwise read back *this* submission's answer without
        guessing "the latest call" - which the playground never does.
        """
        marks: dict[str, object] = {
            "answer_persisted": False,
            "projection_status": "not-recorded",
            "projection_sha256": None,
            "projection_redactions": None,
            "projection_truncated_fields": [],
            "result_projection": None,
        }
        redactors = _frozen_redactors(credentials)
        if outcome is None or not redactors:
            return marks
        view: dict[str, object] = {}
        for key in PROJECTION_OUTCOME_KEYS:
            if key in outcome:
                view[key] = outcome[key]
        answer = outcome.get("answer")
        body: dict[str, object] = {
            "version": PROJECTION_VERSION,
            "submission_id": submit_id,
            "dp": dp,
            "state": state,
            "decision_id": decision_id or f"{dp}:{submit_id}",
            "call_id": view.get("call_id") if isinstance(view.get("call_id"), str) else None,
            "book_ref": book_ref or view.get("book_ref"),
            "state_digest": state_digest or view.get("state_digest"),
            "http_attempts": http_attempts,
            "capture_status": capture_status,
            "capture_channel": view.get("capture_channel"),
            "decision_ran": decision_ran,
            "zero_call": zero_call,
            "started_at": started_at,
            "finished_at": finished_at,
            "answer": dict(answer) if isinstance(answer, Mapping) else None,
            "answer_present": isinstance(answer, Mapping),
            "outcome": view,
            "issues": [f"{issue.code} {issue.path}: {issue.detail}" for issue in issues],
        }
        stats: dict[str, object] = {"hits": 0, "truncated_fields": []}
        try:
            safe = _sanitize_projection(redactors, body, stats, "")
        except _ProjectionError:
            marks["projection_status"] = "failed"
            self._notify(
                f"decision-playground: submission {submit_id} result projection could not "
                "be redacted; nothing was persisted"
            )
            return marks
        assert isinstance(safe, dict)
        safe["redaction"] = {
            "legs": ["known-secret", "capture"],
            "hits": int(stats["hits"]),
            "truncated_fields": list(stats["truncated_fields"]),  # type: ignore[arg-type]
            "placeholder": "<redacted>",
        }
        try:
            text = json.dumps(safe, ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError):
            marks["projection_status"] = "failed"
            return marks
        # Final whole-document pass: no frozen leg may still match anything.
        final, hits = _redact_all(redactors, text)
        if final is None:
            marks["projection_status"] = "failed"
            return marks
        if hits:
            safe["redaction"]["hits"] = int(safe["redaction"]["hits"]) + hits  # type: ignore[index]
            text = final
        try:
            checked = json.loads(text)
        except ValueError:
            marks["projection_status"] = "failed"
            return marks
        if not isinstance(checked, dict):
            marks["projection_status"] = "failed"
            return marks
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        path = self._projection_path(submit_id)
        if path is None:
            marks["projection_status"] = "failed"
            return marks
        wrapper = {"schema": PROJECTION_VERSION, "projection_sha256": digest, "projection": checked}
        tmp = path.with_name(f"{path.name}.{os.getpid()}.{threading.get_ident()}.tmp")
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(tmp, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(json.dumps(wrapper, ensure_ascii=False, sort_keys=True) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(tmp, path)
        except OSError:
            try:
                tmp.unlink()
            except OSError:
                pass
            marks["projection_status"] = "failed"
            self._notify(
                f"decision-playground: submission {submit_id} result projection could not "
                "be written"
            )
            return marks
        redaction = checked.get("redaction") if isinstance(checked.get("redaction"), Mapping) else {}
        marks.update(
            answer_persisted=checked.get("answer_present") is True,
            projection_status="recorded",
            projection_sha256=digest,
            projection_redactions=redaction.get("hits"),
            projection_truncated_fields=list(redaction.get("truncated_fields") or []),
            result_projection=checked,
        )
        return marks

    def _read_projection(self, submission_id: str) -> tuple[dict, str] | None:
        """Read one persisted projection (hash-verified, never guessed)."""
        path = self._projection_path(submission_id)
        if path is None:
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except (OSError, ValueError):
            return None
        try:
            wrapper = json.loads(raw)
        except ValueError:
            return None
        if not isinstance(wrapper, Mapping):
            return None
        projection = wrapper.get("projection")
        digest = wrapper.get("projection_sha256")
        if not isinstance(projection, dict) or not isinstance(digest, str):
            return None
        if projection.get("submission_id") != submission_id:
            return None
        try:
            text = json.dumps(projection, ensure_ascii=False, sort_keys=True, default=str)
        except (TypeError, ValueError):
            return None
        if hashlib.sha256(text.encode("utf-8")).hexdigest() != digest:
            return None
        return projection, digest

    def _merge_projection(self, record: dict, submission_id: str) -> None:
        """Add this submission's persisted answer/ids to its ledger record."""
        stored = self._read_projection(submission_id)
        ended = record.get("finished_at") is not None
        if stored is None:
            if ended and record.get("decision_ran"):
                record["projection_status"] = "missing"
            return
        projection, digest = stored
        redaction = (
            projection.get("redaction")
            if isinstance(projection.get("redaction"), Mapping)
            else {}
        )
        record["answer"] = projection.get("answer")
        record["answer_persisted"] = projection.get("answer_present") is True
        record["projection_status"] = "recorded"
        record["projection_sha256"] = digest
        record["projection_redactions"] = redaction.get("hits")
        record["projection_truncated_fields"] = list(
            redaction.get("truncated_fields") or []
        )
        record["result_projection"] = projection
        for key in (
            "call_id",
            "book_ref",
            "state_digest",
            "http_attempts",
            "capture_status",
            "decision_id",
        ):
            if record.get(key) is None and projection.get(key) is not None:
                record[key] = projection.get(key)
        view = dict(record.get("outcome") or {})
        stored_view = (
            projection.get("outcome")
            if isinstance(projection.get("outcome"), Mapping)
            else {}
        )
        for key, value in stored_view.items():
            if value is not None and view.get(key) is None:
                view[key] = value
        if projection.get("answer") is not None:
            view["answer"] = projection.get("answer")
        if view:
            record["outcome"] = view

    # -- payloads ----------------------------------------------------------

    @staticmethod
    def _base_payload(*, dp: str, submit_id: str, retry_of: object = None) -> dict:
        return {
            "submission_id": submit_id,
            "dp": dp,
            "state": "rejected",
            "accepted": False,
            "duplicate": False,
            "busy": False,
            "observe_only": OBSERVE_ONLY,
            "retry_of": retry_of if isinstance(retry_of, str) else None,
            "decision_id": None,
            "decision_ran": False,
            "call_id": None,
            "zero_call": None,
            "http_attempts": None,
            "book_ref": None,
            "state_digest": None,
            "capture_status": None,
            "record_status": "not-recorded",
            "issues": [],
            "outcome": None,
            "started_at": None,
            "finished_at": None,
            "message": None,
            "answer": None,
            "answer_persisted": False,
            "projection_status": "not-recorded",
            "projection_sha256": None,
            "projection_redactions": None,
            "attempts": [],
            "projection_truncated_fields": [],
            "result_projection": None,
        }

    def _finish(
        self,
        scope: decision_wire.WireScope,
        *,
        dp: str,
        submit_id: str,
        retry_of: object,
        state: str,
        zero_call: bool | None,
        issues: list[PlaygroundIssue] | tuple[PlaygroundIssue, ...] = (),
        outcome: dict | None = None,
        book_ref: str | None = None,
        state_digest: str | None = None,
        http_attempts: int | None = None,
        capture_status: str | None = None,
        decision_id: str | None = None,
        decision_ran: bool = False,
        started_at: str | None = None,
        credentials: Credentials | None = None,
    ) -> dict:
        """Append ``submission-end`` and return the honest result payload.

        When a decision actually ran and this submission's frozen redactors are
        available, the safe result projection is persisted here as well - the
        only place the playground may add persistence (T11b): the wire
        ``submission-end`` schema has no answer field, so this is what lets
        polling and a re-opened detail read back *this* submission's answer
        without guessing a call.
        """
        assert state in SUBMISSION_STATES, state
        finished_at = _now_ts()
        note = [f"{issue.code} {issue.path}: {issue.detail}" for issue in issues]
        result = decision_wire.record_event(
            scope,
            "submission-end",
            fields={
                "dp": dp,
                "outcome": state,
                "issues": note or None,
                "retry_of": retry_of if isinstance(retry_of, str) else None,
                "zero_call": zero_call,
                "book_ref": book_ref,
            },
            actor=SUBMIT_ACTOR,
            capture_status=capture_status,
        )
        recorded = bool(getattr(result, "written", False))
        payload = self._base_payload(dp=dp, submit_id=submit_id, retry_of=retry_of)
        projection_marks: dict[str, object] = {}
        if recorded and outcome is not None and credentials is not None:
            projection_marks = self._persist_projection(
                dp=dp,
                submit_id=submit_id,
                state=state,
                zero_call=zero_call,
                outcome=outcome,
                issues=tuple(issues),
                book_ref=book_ref,
                state_digest=state_digest,
                http_attempts=http_attempts,
                capture_status=capture_status,
                decision_id=decision_id,
                decision_ran=decision_ran,
                started_at=started_at,
                finished_at=finished_at,
                credentials=credentials,
            )
        payload.update(
            state=state if recorded else "record-failed",
            accepted=True,
            zero_call=zero_call,
            issues=[issue.as_dict() for issue in issues],
            outcome=outcome,
            book_ref=book_ref,
            state_digest=state_digest,
            capture_status=capture_status,
            decision_id=decision_id or f"{dp}:{submit_id}",
            decision_ran=decision_ran,
            http_attempts=http_attempts,
            record_status="recorded" if recorded else "failed",
            started_at=started_at,
            finished_at=finished_at,
            message=None
            if recorded
            else (
                "the model call outcome above could not be recorded "
                f"({getattr(result, 'error_class', None) or 'append'}); it is not a "
                "recorded test fact until the ledger is repaired"
            ),
        )
        live_answer = (outcome or {}).get("answer") if isinstance(outcome, Mapping) else None
        if isinstance(live_answer, Mapping):
            payload["answer"] = dict(live_answer)
        live_call = (outcome or {}).get("call_id") if isinstance(outcome, Mapping) else None
        if isinstance(live_call, str) and live_call:
            payload["call_id"] = live_call
        payload.update(projection_marks)
        if not recorded:
            self._notify(
                f"decision-playground: submission {submit_id} finished but its "
                "submission-end row could not be written"
            )
        return payload

    def _record_payload(self, record: Mapping[str, object], *, duplicate: bool = False) -> dict:
        payload = self._base_payload(
            dp=str(record.get("dp") or ""),
            submit_id=str(record.get("submission_id") or ""),
            retry_of=record.get("retry_of"),
        )
        payload.update(dict(record))
        payload.update(
            accepted=True,
            duplicate=duplicate,
            busy=False,
            observe_only=OBSERVE_ONLY,
            record_status=record.get("record_status") or "recorded",
        )
        return payload

    # -- ledger read side --------------------------------------------------

    def _ledger_warnings(self) -> list[str]:
        path = decision_wire.test_wire_sink(self.test_root)
        stats = decision_wire.read_events(path).stats
        warnings: list[str] = []
        for name in (
            "bad_json",
            "bad_utf8",
            "unknown_schema",
            "oversized_line",
            "incomplete_tail",
            "rotated",
        ):
            count = getattr(stats, name, 0)
            if count:
                warnings.append(f"{name}={count}")
        return warnings

    def _submission_records(self) -> dict[str, dict]:
        """Group this project's test ledger by ``submission_id`` (no guessing)."""
        read = decision_wire.read_events(decision_wire.test_wire_sink(self.test_root))
        records: dict[str, dict] = {}
        for event in read.events:
            submission_id = event.get("submission_id")
            if not isinstance(submission_id, str) or not submission_id:
                continue
            record = records.get(submission_id)
            if record is None:
                record = {
                    "submission_id": submission_id,
                    "dp": None,
                    "state": "running",
                    "retry_of": None,
                    "started_at": None,
                    "finished_at": None,
                    "decision_id": None,
                    "decision_ran": False,
                    "call_id": None,
                    "zero_call": None,
                    "http_attempts": None,
                    "book_ref": None,
                    "state_digest": None,
                    "capture_status": None,
                    "issues": [],
                    "outcome": None,
                    "scope": event.get("scope"),
                    "record_status": "recorded",
                    "answer": None,
                    "answer_persisted": False,
                    "projection_status": "not-recorded",
                    "projection_sha256": None,
                    "projection_redactions": None,
                    "projection_truncated_fields": [],
                    "result_projection": None,
                    "attempts_map": {},
                    "attempts": [],
                }
                records[submission_id] = record
            kind = event.get("kind")
            if kind == "submission-start":
                record["dp"] = event.get("dp") or record["dp"]
                record["retry_of"] = event.get("retry_of") or record["retry_of"]
                record["started_at"] = event.get("ts")
                record["state"] = "running"
            elif kind == "submission-end":
                record["state"] = str(event.get("outcome") or "failed")
                raw_issues = event.get("issues")
                record["issues"] = [str(item) for item in raw_issues] if raw_issues else []
                record["zero_call"] = event.get("zero_call")
                record["retry_of"] = event.get("retry_of") or record["retry_of"]
                record["finished_at"] = event.get("ts")
                record["capture_status"] = event.get("capture_status")
                record["book_ref"] = event.get("book_ref") or record["book_ref"]
            elif kind == "decision-end":
                record["decision_ran"] = True
                record["decision_id"] = event.get("decision_id") or record["decision_id"]
                record["book_ref"] = event.get("book_ref") or record["book_ref"]
                record["call_id"] = event.get("call_id") or record["call_id"]
                record["state_digest"] = event.get("state_digest") or record["state_digest"]
                view = dict(record.get("outcome") or {})
                for key in ("status", "escalated_reason", "mode", "truncated", "archive"):
                    view[key] = event.get(key)
                record["outcome"] = view
            elif kind == "call-end":
                record["call_id"] = event.get("call_id") or record["call_id"]
                view = dict(record.get("outcome") or {})
                for key in (
                    "attempts",
                    "wire_attempts",
                    "latency_ms",
                    "available",
                    "reason",
                    "confidence",
                    "confidence_source",
                    "transport",
                    "model",
                    "answers_present",
                ):
                    view[key] = event.get(key)
                record["outcome"] = view
                if isinstance(event.get("wire_attempts"), int):
                    record["http_attempts"] = event.get("wire_attempts")
            elif kind == "book-snapshot":
                record["book_ref"] = event.get("book_ref") or record["book_ref"]
            elif kind == "attempt-start":
                index = event.get("attempt_index")
                entry = record["attempts_map"].setdefault(
                    str(index), {"attempt_index": index, "unfinished": True}
                )
                entry.update(
                    method=event.get("method"),
                    url_path=event.get("url_path"),
                    model=event.get("model"),
                    timeout_s=event.get("timeout_s"),
                    request=event.get("request"),
                    started_at=event.get("ts"),
                )
            elif kind == "attempt-end":
                index = event.get("attempt_index")
                entry = record["attempts_map"].setdefault(
                    str(index), {"attempt_index": index}
                )
                entry.update(
                    unfinished=False,
                    http_status=event.get("http_status"),
                    latency_ms=event.get("latency_ms"),
                    content_type=event.get("content_type"),
                    usage=event.get("usage"),
                    error_class=event.get("error_class"),
                    error_detail=event.get("error_detail"),
                    response=event.get("response"),
                    finished_at=event.get("ts"),
                )
            elif kind == "lifecycle":
                continue
        for submission_id, record in records.items():
            attempts = sorted(
                record.pop("attempts_map", {}).values(),
                key=lambda entry: (
                    str(entry.get("attempt_index")) if entry.get("attempt_index") is None else "",
                    entry.get("started_at") or "",
                ),
            )
            record["attempts"] = attempts
            if record["state"] == "running" and submission_id not in self._inflight:
                record["state"] = "unfinished"
            self._merge_projection(record, submission_id)
        return records


def _safe_names(names: list[str]) -> list[str]:
    """Only short identifier-shaped names reach a refusal message."""
    return [name for name in names if _SUBMIT_ID_RE.match(name)] or ["<field>"]


__all__ = [
    "Credentials",
    "DecisionPlayground",
    "EXECUTION_KEYS",
    "HISTORY_LIMIT",
    "OBSERVE_ONLY",
    "PLAYGROUND_ISSUE_CODES",
    "PlaygroundIssue",
    "REQUEST_KEYS",
    "Review",
    "SUBMISSION_STATES",
    "SUBMIT_ACTOR",
    "TEST_ROOT_RELATIVE_PATH",
    "free_object_paths",
    "object_smuggle_paths",
]
