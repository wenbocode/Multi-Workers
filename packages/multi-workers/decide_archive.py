"""Decision archive writer/reader: ``.agenticdoc/_autopilot/decisions.jsonl``.

Append-only, hash-chained, single-writer (spec §6.1; design
``evidence/research/design-decision-archive-20261019.md`` Q1..Q6, task T-03).
Unlike triage evidence (``decision.py:940-968``, D-005 best-effort), this
archive IS a correctness dependency (idempotency + settle correlation):
``append_*`` raise :class:`DecisionArchiveError` on validation or I/O failure;
callers map that to exit 2 and escalate to a human.

Invariants (four layers, spec §6.1):

1. No update path — rows are only ever appended; a bad tail is *terminated*
   with a newline (never truncated), so existing bytes survive verbatim.
2. ``prev_sha`` hash chain — ``sha256(canonical(prev_row))[:16]`` where
   canonical = ``json.dumps(sort_keys=True, separators=(",", ":"),
   ensure_ascii=False, default=str)``; the chain is defined over the
   *parseable* row subsequence, so unparsable rows never break it.
3. ``mw_common.acquire_lock`` single writer — the whole
   "read tail -> compute sha -> append" window runs under
   ``<archive>.lock`` (``O_CREAT|O_EXCL``, ``mw_common.py:2369-2390``).
4. Undo is a negative row (``override`` / ``settle``), never a rewrite.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import os
import pathlib
import re
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any, Literal

import decision
import mw_common

ARCHIVE_RELATIVE_PATH = pathlib.Path(".agenticdoc") / "_autopilot" / "decisions.jsonl"

_LOCK_SUFFIX = ".lock"  # -> decisions.jsonl.lock, same directory
_GENESIS_PREV = "0" * 16  # first row's prev_sha
_TAIL_WINDOW_BYTES = 64 * 1024  # bounded tail read for the chain head
_SIZE_RETRIES = 3  # size re-check rounds against lock-bypassing writers

_KINDS = frozenset({"decide", "override", "settle", "authority-change"})
_AUTHORITY = frozenset({"advisory", "binding", "human"})

#: Single ``escalated_reason`` vocabulary, shared verbatim with
#: ``decision_points.ESCALATED_REASONS`` (design D-030 / D-033): the archive
#: layer never translates a reason, so the recorded value is the real cause.
_ESCALATED_REASONS_CORE = frozenset(
    {
        "disabled",
        "unavailable",
        "input-incomplete",
        "input-oversize",
        "low-confidence",
        "over-authority",
        "p0",
    }
)
#: Read-side compatibility only: rows written before the vocabulary
#: convergence carry ``input-invalid``. Validation still accepts it so an
#: existing archive stays readable, but no writer produces it any more.
_ESCALATED_REASONS_LEGACY = frozenset({"input-invalid"})
_ESCALATED_REASONS = _ESCALATED_REASONS_CORE | _ESCALATED_REASONS_LEGACY
_OUTCOMES = frozenset({"pending", "ok", "rework", "rollback", "inconclusive"})
_SETTLED_BY = frozenset({"pm-auto", "human"})
_CHANGE_BY = frozenset(
    {
        "human",
        "human:p0-confirm",
        "signoff:continue",
        "signoff:narrow",
        "signoff:revoke",
        "refresh",
    }
)
_MODES = frozenset({"auto", "suggest"})
_CONCLUSIONS = frozenset({"continue", "narrow", "revoke"})
_CONFIDENCE_SOURCES = frozenset({"api", "model-self-report", "unknown"})
# D2-S2: outcome=pending is only legal as an explicit registration row.
_PENDING_NOTES = frozenset({"lost", "needs-clarification", "deferred-to-human"})

_SHA16_RE = re.compile(r"^[0-9a-f]{16}$")
_QUESTIONS_VERSION_RE = re.compile(r"^q-[0-9a-f]{8}$")

# Field order of a written row (Q4 matrix); every row carries every key so a
# reader never has to distinguish "absent" from "not applicable for this kind".
_ROW_FIELDS = (
    "seq",
    "prev_sha",
    "kind",
    "decision_id",
    "ts",
    "dp",
    "key",
    "task_key",
    "state_digest",
    "questions_version",
    "available",
    "reason",
    "answer",
    "authority",
    "escalated_reason",
    "acted",
    "actual_action",
    "outcome",
    "settled_by",
    "evidence_ref",
    "override_by",
    "override_reason",
    "ref_seq",
    "by",
    "change",
    "conclusion",
    "config_sha_after",
    "evidence_line",
    "mode",
    "model",
    "transport",
    "attempts",
    "latency_ms",
    "confidence",
    "confidence_source",
    "cost_tokens",
    "policy",
    "note",
)

# Constant-None fields per kind (Q4 matrix `=` cells).
_NOT_APPLICABLE = {
    "decide": (
        "settled_by",
        "evidence_ref",
        "override_by",
        "override_reason",
        "ref_seq",
        "by",
        "change",
        "conclusion",
        "config_sha_after",
    ),
    "override": (
        "state_digest",
        "questions_version",
        "available",
        "reason",
        "answer",
        "authority",
        "escalated_reason",
        "acted",
        "actual_action",
        "outcome",
        "settled_by",
        "evidence_ref",
        "by",
        "change",
        "conclusion",
        "config_sha_after",
        "evidence_line",
        "mode",
        "model",
        "transport",
        "attempts",
        "latency_ms",
        "confidence",
        "confidence_source",
        "cost_tokens",
        "policy",
    ),
    "settle": (
        "state_digest",
        "questions_version",
        "available",
        "reason",
        "answer",
        "authority",
        "escalated_reason",
        "acted",
        "actual_action",
        "override_by",
        "override_reason",
        "ref_seq",
        "by",
        "change",
        "conclusion",
        "config_sha_after",
        "evidence_line",
        "mode",
        "model",
        "transport",
        "attempts",
        "latency_ms",
        "confidence",
        "confidence_source",
        "cost_tokens",
        "policy",
    ),
    "authority-change": (
        "state_digest",
        "questions_version",
        "available",
        "reason",
        "answer",
        "authority",
        "escalated_reason",
        "acted",
        "actual_action",
        "outcome",
        "settled_by",
        "evidence_ref",
        "override_by",
        "override_reason",
        "ref_seq",
        "evidence_line",
        "mode",
        "model",
        "transport",
        "attempts",
        "latency_ms",
        "confidence",
        "confidence_source",
        "cost_tokens",
        "policy",
    ),
}


class DecisionArchiveError(ValueError):
    """Contract violation or I/O failure; the CLI boundary maps this to exit 2."""


class DecisionArchiveDuplicate(DecisionArchiveError):
    """A ``kind=decide`` row already exists for this ``decision_id`` (spec §6.1)."""


# ---------------------------------------------------------------------------
# Hashing / canonical form (Q2.5, Q6.3)
# ---------------------------------------------------------------------------


def _canonical_bytes(row: Mapping) -> bytes:
    """Canonical JSON bytes of a row: key-order and whitespace independent."""
    return json.dumps(
        row,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8", errors="replace")


def _row_sha(row: Mapping) -> str:
    """Chain hash of a row: ``sha256(canonical(row))[:16]``."""
    return hashlib.sha256(_canonical_bytes(row)).hexdigest()[:16]


def state_digest(state: object) -> str:
    """``sha256(decision._encode_state(state))[:16]`` — reused, not re-implemented.

    ``_encode_state`` is the canonical, key-sorted JSON serialization used for
    size/digest accounting (D-003); it is **not** the transport payload. The
    backend serializes its own request body and card T03 captures those bytes at
    the wire boundary, so this digest identifies the canonical state a row
    refers to (and joins it to the side ledger's ``book-snapshot``) without
    proving anything about the HTTP request bytes (design §9: ``state_digest``
    is an archive correlation id, not a request-byte proof). The raw state is
    never written to the archive.
    """
    return hashlib.sha256(decision._encode_state(state)).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Small validation helpers
# ---------------------------------------------------------------------------


def _is_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _is_sha16(value: object) -> bool:
    return isinstance(value, str) and _SHA16_RE.match(value) is not None


def _is_human_identity(value: object) -> bool:
    """``human`` or ``human:<account>``; machine identities are rejected (spec §7.3)."""
    if not isinstance(value, str) or not value:
        return False
    if value == "human":
        return True
    head, _sep, tail = value.partition(":")
    return head == "human" and bool(tail) and not any(ch.isspace() for ch in tail)


def _require_text(row: Mapping, name: str) -> None:
    value = row.get(name)
    if not isinstance(value, str) or not value:
        raise DecisionArchiveError(f"{name} must be a non-empty string, got {value!r}")


def _require_optional_text(row: Mapping, name: str) -> None:
    value = row.get(name)
    if value is not None and not isinstance(value, str):
        raise DecisionArchiveError(f"{name} must be a string or None, got {value!r}")


def _require_optional_sha16(row: Mapping, name: str) -> None:
    value = row.get(name)
    if value is not None and not _is_sha16(value):
        raise DecisionArchiveError(f"{name} must be 16 lowercase hex chars, got {value!r}")


def _require_optional_count(row: Mapping, name: str) -> None:
    value = row.get(name)
    if value is not None and (not _is_int(value) or value < 0):
        raise DecisionArchiveError(f"{name} must be a non-negative integer, got {value!r}")


def _validate_answer(answer: object) -> None:
    if not isinstance(answer, Mapping):
        raise DecisionArchiveError(
            f"answer must be a mapping of qid -> {{value, confidence}}, got {type(answer).__name__}"
        )
    for qid, entry in answer.items():
        if not isinstance(qid, str) or not qid:
            raise DecisionArchiveError(f"answer question id must be a non-empty string, got {qid!r}")
        if not isinstance(entry, Mapping):
            raise DecisionArchiveError(f"answer[{qid!r}] must be a mapping, got {type(entry).__name__}")
        if "value" not in entry:
            raise DecisionArchiveError(f"answer[{qid!r}] is missing 'value'")
        confidence = entry.get("confidence")
        if confidence is not None and not _is_number(confidence):
            raise DecisionArchiveError(
                f"answer[{qid!r}].confidence must be a number or None, got {confidence!r}"
            )


def _reject_not_applicable(row: Mapping) -> None:
    """Force the Q4 `=` cells of a kind to ``None`` (no stale cross-kind fields)."""
    for name in _NOT_APPLICABLE[row["kind"]]:
        if row.get(name) is not None:
            raise DecisionArchiveError(
                f"{row['kind']} row must not carry {name} (got {row.get(name)!r})"
            )


def _validate_policy(policy: object) -> None:
    """Validate the decide-row ``policy`` echo (effective per-dp knobs, D-051).

    ``None`` means the caller did not report a policy (older rows / hand calls);
    otherwise it must be a mapping carrying the three effective values so a row
    can explain why it was acted on or escalated without re-reading config.
    """
    if policy is None:
        return
    if not isinstance(policy, Mapping):
        raise DecisionArchiveError(f"policy must be a mapping or None, got {policy!r}")
    unknown = sorted(set(policy) - {"min_confidence", "max_questions", "timeout_s"})
    if unknown:
        raise DecisionArchiveError(f"policy has unknown keys {unknown}")
    confidence = policy.get("min_confidence")
    if confidence is not None:
        if not _is_number(confidence) or not 0 <= float(confidence) <= 1:
            raise DecisionArchiveError(
                f"policy.min_confidence must be a number in [0, 1], got {confidence!r}"
            )
    for name in ("max_questions", "timeout_s"):
        value = policy.get(name)
        if value is not None and (not _is_int(value) or value < 1):
            raise DecisionArchiveError(f"policy.{name} must be a positive integer, got {value!r}")


def _validate_row(row: Mapping) -> None:
    """Validate the Q4 field matrix for one row (chain fields optional here)."""
    kind = row.get("kind")
    if kind not in _KINDS:
        raise DecisionArchiveError(f"invalid kind {kind!r}")

    seq = row.get("seq")
    if seq is not None and (not _is_int(seq) or seq < 1):
        raise DecisionArchiveError(f"seq must be a positive integer, got {seq!r}")
    prev_sha = row.get("prev_sha")
    if prev_sha is not None and not _is_sha16(prev_sha):
        raise DecisionArchiveError(f"prev_sha must be 16 hex chars, got {prev_sha!r}")

    for name in ("decision_id", "ts", "dp"):
        _require_text(row, name)
    if not isinstance(row.get("key"), str):
        raise DecisionArchiveError(f"key must be a string, got {row.get('key')!r}")
    task_key = row.get("task_key")
    if task_key is not None and not isinstance(task_key, str):
        raise DecisionArchiveError(f"task_key must be a string or None, got {task_key!r}")
    _require_optional_text(row, "note")
    _reject_not_applicable(row)

    if kind == "decide":
        questions_version = row.get("questions_version")
        if not isinstance(questions_version, str) or not _QUESTIONS_VERSION_RE.match(
            questions_version
        ):
            raise DecisionArchiveError(
                f"questions_version must match q-<8 hex>, got {questions_version!r}"
            )
        _require_optional_sha16(row, "state_digest")
        if row.get("state_digest") is None:
            raise DecisionArchiveError("decide row requires state_digest")

        available = row.get("available")
        if not isinstance(available, bool):
            raise DecisionArchiveError(f"available must be a boolean, got {available!r}")
        reason = row.get("reason")
        if not available:
            if reason not in decision.REASON_CODES:
                raise DecisionArchiveError(
                    f"unavailable decision requires reason in REASON_CODES, got {reason!r}"
                )
            if row.get("answer") is not None:
                raise DecisionArchiveError("unavailable decision must not carry answer")
        else:
            if reason is not None and reason not in decision.REASON_CODES:
                raise DecisionArchiveError(f"reason {reason!r} is not a REASON_CODES member")
            if row.get("answer") is None:
                raise DecisionArchiveError("available decision requires answer")
            _validate_answer(row.get("answer"))

        authority = row.get("authority")
        if authority not in _AUTHORITY:
            raise DecisionArchiveError(f"authority {authority!r} not in {sorted(_AUTHORITY)}")
        escalated_reason = row.get("escalated_reason")
        if authority == "human":
            if escalated_reason not in _ESCALATED_REASONS:
                raise DecisionArchiveError(
                    f"authority=human requires escalated_reason in "
                    f"{sorted(_ESCALATED_REASONS)}, got {escalated_reason!r}"
                )
        elif escalated_reason is not None:
            raise DecisionArchiveError(
                f"escalated_reason is only legal with authority=human, got {escalated_reason!r}"
            )

        acted = row.get("acted")
        if not isinstance(acted, bool):
            raise DecisionArchiveError(f"acted must be a boolean, got {acted!r}")
        actual_action = row.get("actual_action")
        if actual_action is not None and not isinstance(actual_action, str):
            raise DecisionArchiveError(f"actual_action must be a string or None, got {actual_action!r}")
        if acted:
            if authority != "binding":
                raise DecisionArchiveError("acted=True requires authority=binding")
            if not actual_action:
                raise DecisionArchiveError("acted=True requires a non-empty actual_action")

        mode = row.get("mode")
        if mode is not None and mode not in _MODES:
            raise DecisionArchiveError(f"mode {mode!r} not in {sorted(_MODES)}")
        if mode == "suggest" and acted:
            raise DecisionArchiveError("mode=suggest must not act (AC-015)")

        if row.get("outcome") != "pending":
            raise DecisionArchiveError("decide row outcome is always 'pending'")

        confidence = row.get("confidence")
        if confidence is not None and not _is_number(confidence):
            raise DecisionArchiveError(f"confidence must be a number or None, got {confidence!r}")
        confidence_source = row.get("confidence_source")
        if confidence_source is not None and confidence_source not in _CONFIDENCE_SOURCES:
            raise DecisionArchiveError(
                f"confidence_source {confidence_source!r} not in {sorted(_CONFIDENCE_SOURCES)}"
            )
        for name in ("attempts", "latency_ms"):
            value = row.get(name)
            if value is not None and (not _is_int(value) or value < 0):
                raise DecisionArchiveError(f"{name} must be a non-negative integer, got {value!r}")
        _require_optional_count(row, "cost_tokens")
        _validate_policy(row.get("policy"))
        _require_optional_text(row, "transport")
        _require_optional_text(row, "model")
        evidence_line = row.get("evidence_line")
        if evidence_line is not None and (not _is_int(evidence_line) or evidence_line < 1):
            raise DecisionArchiveError(
                f"evidence_line must be a positive integer or None, got {evidence_line!r}"
            )
        return

    if kind == "override":
        if row.get("task_key") is not None:
            raise DecisionArchiveError("override row task_key is always None")
        override_by = row.get("override_by")
        if not _is_human_identity(override_by):
            raise DecisionArchiveError(
                f"override_by must be a human identity (human / human:<account>), "
                f"machines never override (spec §7.3); got {override_by!r}"
            )
        _require_text(row, "override_reason")
        ref_seq = row.get("ref_seq")
        if ref_seq is not None and (not _is_int(ref_seq) or ref_seq < 1):
            raise DecisionArchiveError(f"ref_seq must be a positive integer or None, got {ref_seq!r}")
        return

    if kind == "settle":
        outcome = row.get("outcome")
        if outcome not in _OUTCOMES:
            raise DecisionArchiveError(f"outcome {outcome!r} not in {sorted(_OUTCOMES)}")
        settled_by = row.get("settled_by")
        if settled_by not in _SETTLED_BY:
            raise DecisionArchiveError(
                f"settled_by {settled_by!r} not in {sorted(_SETTLED_BY)}"
            )
        if outcome == "pending" and row.get("note") not in _PENDING_NOTES:
            raise DecisionArchiveError(
                f"outcome=pending is a registration row and requires note in "
                f"{sorted(_PENDING_NOTES)} (D2-S2), got {row.get('note')!r}"
            )
        _require_optional_text(row, "evidence_ref")
        return

    # kind == "authority-change"
    if row.get("task_key") is not None:
        raise DecisionArchiveError("authority-change row task_key is always None")
    by = row.get("by")
    if by not in _CHANGE_BY:
        raise DecisionArchiveError(f"by {by!r} not in {sorted(_CHANGE_BY)}")
    change = row.get("change")
    if not isinstance(change, str) or not change:
        raise DecisionArchiveError(f"change must be a non-empty string, got {change!r}")
    if "\n" in change or "\r" in change:
        raise DecisionArchiveError("change must be a single line")
    conclusion = row.get("conclusion")
    if by.startswith("signoff:"):
        if conclusion not in _CONCLUSIONS:
            raise DecisionArchiveError(
                f"by={by} requires conclusion in {sorted(_CONCLUSIONS)}, got {conclusion!r}"
            )
    elif conclusion is not None:
        raise DecisionArchiveError(f"conclusion is only legal for signoff rows, got {conclusion!r}")
    _require_optional_sha16(row, "config_sha_after")


# ---------------------------------------------------------------------------
# File primitives (tail repair, chain head, locked append)
# ---------------------------------------------------------------------------


def _now_ts() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")


def _file_size(path: pathlib.Path) -> int:
    try:
        return path.stat().st_size
    except FileNotFoundError:
        return 0


def _repair_tail_if_dangling(path: pathlib.Path) -> bool:
    """Terminate a dangling final line with ``\\n``; never truncate (Q2.4).

    A crash mid-``write`` can leave a prefix of a row with no trailing
    newline. Truncating would mutate existing bytes (breaking append-only) and
    destroy forensic evidence, so the prefix is *terminated* instead: it becomes
    an independent unparsable row that the chain scan skips. If the dangling
    tail happened to be complete JSON that only lost its ``\\n``, it simply
    becomes a valid chain head — no special case needed.
    """
    size = _file_size(path)
    if size == 0:
        return False
    with path.open("rb") as handle:
        handle.seek(size - 1)
        last = handle.read(1)
    if last == b"\n":
        return False
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write("\n")
        handle.flush()
        try:
            os.fsync(handle.fileno())
        except OSError:
            pass
    return True


def _last_parseable_row(path: pathlib.Path) -> dict | None:
    """Full-file fallback for :func:`_chain_head` (only used on tail misses)."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    for line in reversed(text.splitlines()):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            return row
    return None


def _chain_head(path: pathlib.Path) -> tuple[dict | None, int]:
    """Return ``(last parseable row, size observed before reading)``.

    The bounded tail window keeps an append O(window); the observed size lets
    the caller detect a writer that bypassed the lock between read and append.
    """
    size = _file_size(path)
    if size == 0:
        return None, size
    start = max(0, size - _TAIL_WINDOW_BYTES)
    try:
        with path.open("rb") as handle:
            handle.seek(start)
            chunk = handle.read(size - start)
    except FileNotFoundError:
        return None, 0
    if start > 0:
        newline = chunk.find(b"\n")
        chunk = chunk[newline + 1 :] if newline >= 0 else b""
    for raw in reversed(chunk.split(b"\n")):
        if not raw.strip():
            continue
        try:
            row = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            continue
        if isinstance(row, dict):
            return row, size
    if start == 0:
        return None, size
    # The window held no parseable row (huge final row): fall back to the file.
    return _last_parseable_row(path), size


def _append_row(
    path: pathlib.Path,
    row: dict,
    *,
    dedupe_decision_id: str | None = None,
    duplicate: Literal["raise", "existing"] = "raise",
    precheck: Any = None,
) -> tuple[dict, bool]:
    """Assign ``seq``/``prev_sha`` and append under the archive lock."""
    path = pathlib.Path(path)
    lock = path.with_name(path.name + _LOCK_SUFFIX)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        mw_common.acquire_lock(lock)
    except (OSError, RuntimeError) as exc:  # lock creation / contention failure
        raise DecisionArchiveError(f"cannot lock decision archive {path}: {exc}") from exc

    try:
        _repair_tail_if_dangling(path)

        if precheck is not None:
            precheck(path)

        # Detection (not convention) against writers that ignore the lock: the
        # chain head is only trusted when the size did not move while reading.
        for _attempt in range(_SIZE_RETRIES):
            head, size_before = _chain_head(path)
            if size_before == _file_size(path):
                break
        else:
            raise DecisionArchiveError(
                f"decision archive {path} kept changing under the lock; "
                "a writer bypassed acquire_lock"
            )

        # Idempotency (Q3): full scan inside the stable lock window, so the
        # answer cannot be based on a tail that moved under us.
        if dedupe_decision_id is not None:
            existing = None
            for _lineno, seen in iter_rows(path):
                if (
                    seen.get("kind") == "decide"
                    and seen.get("decision_id") == dedupe_decision_id
                ):
                    existing = seen
                    break
            if existing is not None:
                if duplicate == "existing":
                    return existing, False
                raise DecisionArchiveDuplicate(
                    f"decision_id {dedupe_decision_id!r} already has a decide row "
                    f"(seq={existing.get('seq')}); idempotency conflict escalates to a human"
                )

        row["seq"] = (int(head["seq"]) + 1) if head is not None else 1
        row["prev_sha"] = _row_sha(head) if head is not None else _GENESIS_PREV
        _validate_row(row)

        line = json.dumps(row, ensure_ascii=False, default=str)
        try:
            with path.open("a", encoding="utf-8", newline="\n") as handle:
                handle.write(line + "\n")
                handle.flush()
                try:
                    os.fsync(handle.fileno())
                except OSError:
                    pass
        except OSError as exc:
            raise DecisionArchiveError(f"cannot append to decision archive {path}: {exc}") from exc
        return dict(row), True
    except OSError as exc:
        # Any read/repair/append I/O failure is fail-loud (D2-S0): this archive
        # is a correctness dependency, never a best-effort log.
        raise DecisionArchiveError(f"decision archive I/O failed for {path}: {exc}") from exc
    finally:
        mw_common.release_lock(lock)


def _base_row(
    *,
    kind: str,
    decision_id: str,
    ts: str,
    dp: str,
    key: str,
    task_key: str | None,
) -> dict:
    row: dict[str, Any] = dict.fromkeys(_ROW_FIELDS)
    row["kind"] = kind
    row["decision_id"] = decision_id
    row["ts"] = ts
    row["dp"] = dp
    row["key"] = key
    row["task_key"] = task_key
    return row


def _split_decision_id(decision_id: str, dp: str) -> str:
    """Validate ``<dp>:<trigger_id>`` and return the trigger part.

    Split on the *first* colon so a dp id containing ``:` still works; the
    trigger may itself contain ``:`` (D2-S1 needs ISO timestamps there).
    """
    if not isinstance(decision_id, str) or not decision_id:
        raise DecisionArchiveError(f"decision_id must be a non-empty string, got {decision_id!r}")
    prefix = f"{dp}:"
    if not decision_id.startswith(prefix):
        raise DecisionArchiveError(f"decision_id {decision_id!r} must start with {prefix!r}")
    trigger_id = decision_id[len(prefix) :]
    if not trigger_id:
        raise DecisionArchiveError(f"decision_id {decision_id!r} has an empty trigger_id")
    return trigger_id


def _default_trigger(by: str, key: str, ts: str) -> str:
    """D2-S1 trigger ids: ``<ts>`` / ``refresh@<ts>`` / ``signoff@<key>@<ts>``."""
    if by.startswith("signoff:"):
        return f"signoff@{key}@{ts}"
    if by == "refresh":
        return f"refresh@{ts}"
    return ts


# ---------------------------------------------------------------------------
# Public read side
# ---------------------------------------------------------------------------


def iter_rows(path: pathlib.Path) -> Iterator[tuple[int, dict]]:
    """Yield ``(1-based physical line number, parsed row)``; skip bad lines.

    Blank lines, unparsable JSON and non-object JSON are skipped (fold counts
    the latter two). Line numbers stay physical so a report can point at the
    exact byte offset owner, including the terminated half-line rows.
    """
    try:
        text = pathlib.Path(path).read_text(encoding="utf-8")
    except FileNotFoundError:
        return
    except OSError as exc:
        raise DecisionArchiveError(f"cannot read decision archive {path}: {exc}") from exc
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if isinstance(row, dict):
            yield lineno, row


@dataclass(frozen=True)
class FoldStats:
    rows_total: int = 0
    parsed: int = 0
    skipped_unparsable: int = 0
    skipped_non_dict: int = 0
    chain_breaks: int = 0
    seq_breaks: int = 0
    groups: int = 0


@dataclass(frozen=True)
class FoldedDecision:
    decision_id: str
    dp: Any
    key: Any
    task_key: Any
    base: Mapping | None
    outcome: str
    settled_by: str | None
    evidence_ref: str | None
    human_override: bool
    override_by: str | None
    override_reason: str | None
    override_count: int
    authority_last: Mapping | None
    note: str | None
    base_missing: bool


@dataclass(frozen=True)
class FoldResult:
    groups: dict[str, FoldedDecision] = field(default_factory=dict)
    stats: FoldStats = field(default_factory=FoldStats)


def _coerce_fold_row(raw: object) -> tuple[dict | None, str]:
    """Normalise one fold input row: ``(row, status)`` with parsed/unparsable/non_dict."""
    if isinstance(raw, Mapping):
        return dict(raw), "parsed"
    if isinstance(raw, (str, bytes, bytearray)):
        try:
            loaded = json.loads(raw)
        except ValueError:
            return None, "unparsable"
        if isinstance(loaded, Mapping):
            return dict(loaded), "parsed"
        return None, "non_dict"
    return None, "non_dict"


def fold(rows: Iterable) -> FoldResult:
    """Fold archive rows into one view per ``decision_id`` (Q5).

    Pure function: no filesystem access, no registry lookup. Outcome is the
    last ``settle`` by ``seq`` (``pending`` when absent), an ``override`` row
    makes ``human_override`` true, and an immutable ``decide`` row is the base
    (``base_missing`` when the group has none). Chain/seq sanity is counted,
    never raised: a break is a fact to report, not a reason to hide rows.
    """
    stats_rows_total = 0
    stats_parsed = 0
    stats_unparsable = 0
    stats_non_dict = 0
    stats_chain_breaks = 0
    stats_seq_breaks = 0

    grouped: dict[str, list[dict]] = {}
    previous: dict | None = None
    expected_seq = 1

    for raw in rows:
        stats_rows_total += 1
        row, status = _coerce_fold_row(raw)
        if status == "non_dict":
            stats_non_dict += 1
            continue
        if status == "unparsable":
            stats_unparsable += 1
            continue
        assert row is not None
        decision_id = row.get("decision_id")
        seq = row.get("seq")
        if not isinstance(decision_id, str) or not decision_id or not _is_int(seq):
            stats_unparsable += 1
            continue
        stats_parsed += 1

        if previous is None:
            if seq != 1:
                stats_seq_breaks += 1
            if row.get("prev_sha") != _GENESIS_PREV:
                stats_chain_breaks += 1
        else:
            if row.get("prev_sha") != _row_sha(previous):
                stats_chain_breaks += 1
            if seq != expected_seq:
                stats_seq_breaks += 1
        expected_seq = seq + 1
        previous = row

        grouped.setdefault(decision_id, []).append(row)

    folded: dict[str, FoldedDecision] = {}
    for decision_id, group in grouped.items():
        ordered = sorted(group, key=lambda item: item["seq"])
        base = next((item for item in ordered if item.get("kind") == "decide"), None)
        settles = [item for item in ordered if item.get("kind") == "settle"]
        overrides = [item for item in ordered if item.get("kind") == "override"]
        authority_rows = [item for item in ordered if item.get("kind") == "authority-change"]
        last_settle = settles[-1] if settles else None
        last_override = overrides[-1] if overrides else None
        source = base if base is not None else ordered[0]

        outcome = last_settle.get("outcome") if last_settle is not None else None
        if not isinstance(outcome, str) or not outcome:
            outcome = "pending"

        folded[decision_id] = FoldedDecision(
            decision_id=decision_id,
            dp=source.get("dp"),
            key=source.get("key"),
            task_key=source.get("task_key"),
            base=base,
            outcome=outcome,
            settled_by=(last_settle.get("settled_by") if last_settle is not None else None),
            evidence_ref=(last_settle.get("evidence_ref") if last_settle is not None else None),
            human_override=bool(overrides),
            override_by=(last_override.get("override_by") if last_override is not None else None),
            override_reason=(
                last_override.get("override_reason") if last_override is not None else None
            ),
            override_count=len(overrides),
            authority_last=(authority_rows[-1] if authority_rows else None),
            note=(
                last_settle.get("note")
                if last_settle is not None and last_settle.get("note") is not None
                else (base.get("note") if base is not None else None)
            ),
            base_missing=base is None,
        )

    stats = FoldStats(
        rows_total=stats_rows_total,
        parsed=stats_parsed,
        skipped_unparsable=stats_unparsable,
        skipped_non_dict=stats_non_dict,
        chain_breaks=stats_chain_breaks,
        seq_breaks=stats_seq_breaks,
        groups=len(folded),
    )
    return FoldResult(groups=folded, stats=stats)


# ---------------------------------------------------------------------------
# Public write side (Q1.2 signatures)
# ---------------------------------------------------------------------------


def append_decide(
    path: pathlib.Path,
    *,
    dp: str,
    key: str,
    task_key: str | None,
    trigger_id: str,
    state: object,
    questions_version: str,
    available: bool,
    authority: str,
    answer: Mapping | None = None,
    reason: str | None = None,
    escalated_reason: str | None = None,
    acted: bool = False,
    actual_action: str | None = None,
    mode: str | None = None,
    transport: str | None = None,
    model: str | None = None,
    attempts: int = 0,
    latency_ms: int = 0,
    confidence: float | None = None,
    confidence_source: str | None = None,
    cost_tokens: int | None = None,
    policy: Mapping | None = None,
    note: str | None = None,
    evidence_line: int | None = None,
    now: str | None = None,
    duplicate: Literal["raise", "existing"] = "raise",
) -> tuple[dict, bool]:
    """Append one ``kind=decide`` row; returns ``(row, created)``.

    ``duplicate="raise"`` (default) escalates an existing ``decision_id`` as
    :class:`DecisionArchiveDuplicate`; ``duplicate="existing"`` returns the
    prior decide row with ``created=False`` and writes nothing (replay path).
    """
    if duplicate not in ("raise", "existing"):
        raise DecisionArchiveError(f"duplicate must be 'raise' or 'existing', got {duplicate!r}")
    if not isinstance(dp, str) or not dp:
        raise DecisionArchiveError(f"dp must be a non-empty string, got {dp!r}")
    if not isinstance(key, str):
        raise DecisionArchiveError(f"key must be a string, got {key!r}")
    if task_key is not None and not isinstance(task_key, str):
        raise DecisionArchiveError(f"task_key must be a string or None, got {task_key!r}")
    if not isinstance(trigger_id, str) or not trigger_id:
        raise DecisionArchiveError(f"trigger_id must be a non-empty string, got {trigger_id!r}")

    ts = now or _now_ts()
    decision_id = f"{dp}:{trigger_id}"
    row = _base_row(kind="decide", decision_id=decision_id, ts=ts, dp=dp, key=key, task_key=task_key)
    row["state_digest"] = state_digest(state)
    row["questions_version"] = questions_version
    row["available"] = available
    row["reason"] = reason
    row["answer"] = dict(answer) if isinstance(answer, Mapping) else answer
    row["authority"] = authority
    row["escalated_reason"] = escalated_reason
    row["acted"] = acted
    row["actual_action"] = actual_action
    row["outcome"] = "pending"  # decide rows are never backfilled (Q4)
    row["mode"] = mode
    row["model"] = model
    row["transport"] = transport
    row["attempts"] = attempts
    row["latency_ms"] = latency_ms
    row["confidence"] = confidence
    row["confidence_source"] = confidence_source
    row["cost_tokens"] = cost_tokens
    row["policy"] = dict(policy) if isinstance(policy, Mapping) else policy
    row["note"] = note
    row["evidence_line"] = evidence_line
    _validate_row(row)

    return _append_row(path, row, dedupe_decision_id=decision_id, duplicate=duplicate)


def append_override(
    path: pathlib.Path,
    *,
    decision_id: str,
    dp: str,
    key: str,
    override_by: str,
    override_reason: str,
    ref_seq: int | None = None,
    note: str | None = None,
    now: str | None = None,
) -> dict:
    """Append one ``kind=override`` row (human reversal of a decision)."""
    if not isinstance(dp, str) or not dp:
        raise DecisionArchiveError(f"dp must be a non-empty string, got {dp!r}")
    if not isinstance(key, str):
        raise DecisionArchiveError(f"key must be a string, got {key!r}")
    _split_decision_id(decision_id, dp)

    ts = now or _now_ts()
    row = _base_row(kind="override", decision_id=decision_id, ts=ts, dp=dp, key=key, task_key=None)
    row["override_by"] = override_by
    row["override_reason"] = override_reason
    row["ref_seq"] = ref_seq
    row["note"] = note
    _validate_row(row)

    def _check_ref_seq(archive: pathlib.Path) -> None:
        if ref_seq is None:
            return
        for _lineno, seen in iter_rows(archive):
            if (
                seen.get("decision_id") == decision_id
                and seen.get("kind") == "decide"
                and seen.get("seq") == ref_seq
            ):
                return
        raise DecisionArchiveError(
            f"ref_seq {ref_seq} is not a decide row of decision_id {decision_id!r}"
        )

    written, _created = _append_row(path, row, precheck=_check_ref_seq)
    return written


def append_settle(
    path: pathlib.Path,
    *,
    decision_id: str,
    dp: str,
    key: str,
    task_key: str | None,
    outcome: str,
    settled_by: str,
    evidence_ref: str | None = None,
    note: str | None = None,
    now: str | None = None,
) -> dict:
    """Append one ``kind=settle`` row (result correlation, spec §6.2)."""
    if not isinstance(dp, str) or not dp:
        raise DecisionArchiveError(f"dp must be a non-empty string, got {dp!r}")
    if not isinstance(key, str):
        raise DecisionArchiveError(f"key must be a string, got {key!r}")
    if task_key is not None and not isinstance(task_key, str):
        raise DecisionArchiveError(f"task_key must be a string or None, got {task_key!r}")
    _split_decision_id(decision_id, dp)

    ts = now or _now_ts()
    row = _base_row(
        kind="settle",
        decision_id=decision_id,
        ts=ts,
        dp=dp,
        key=key,
        task_key=task_key,
    )
    row["outcome"] = outcome
    row["settled_by"] = settled_by
    row["evidence_ref"] = evidence_ref
    row["note"] = note
    _validate_row(row)

    written, _created = _append_row(path, row)
    return written


def append_authority_change(
    path: pathlib.Path,
    *,
    dp: str,
    key: str,
    by: str,
    change: str,
    trigger_id: str | None = None,
    conclusion: str | None = None,
    config_sha_after: str | None = None,
    note: str | None = None,
    now: str | None = None,
) -> dict:
    """Append one ``kind=authority-change`` row (once per affected dp, D2-S1)."""
    if not isinstance(dp, str) or not dp:
        raise DecisionArchiveError(f"dp must be a non-empty string, got {dp!r}")
    if not isinstance(key, str):
        raise DecisionArchiveError(f"key must be a string, got {key!r}")

    ts = now or _now_ts()
    if trigger_id is None:
        trigger_id = _default_trigger(by, key, ts)
    if not isinstance(trigger_id, str) or not trigger_id:
        raise DecisionArchiveError(f"trigger_id must be a non-empty string, got {trigger_id!r}")

    row = _base_row(
        kind="authority-change",
        decision_id=f"{dp}:{trigger_id}",
        ts=ts,
        dp=dp,
        key=key,
        task_key=None,
    )
    row["by"] = by
    row["change"] = change
    row["conclusion"] = conclusion
    row["config_sha_after"] = config_sha_after
    row["note"] = note
    _validate_row(row)

    written, _created = _append_row(path, row)
    return written
