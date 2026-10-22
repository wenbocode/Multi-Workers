"""Engineered environment context for a decide-model call (D-052..D-054).

The state a producer sends carries the *decision fields* (typed, required,
budgeted at 2000 B). ``context`` rides alongside them: free-form, optional
environment material the model needs to reason about the task but which is not
itself a decision field (dispatch-card excerpts, checkpoint summaries, artifact
status, candidate snippets).

Rules implemented here:

* :data:`CONTEXT_SLOTS` is the slot authority: type, cap, and which dps may
  emit the slot. The TS side gets the per-dp whitelist through the generated
  registry (``gen_decide_registry_ts.py``), so a producer can never invent an
  extra slot silently.
* :func:`truncate_slot` keeps the head 60% + the tail 40% of an over-long value
  and marks the cut with ``…truncated N chars…`` (a dropped middle is visible to
  the model, unlike a silent cut).
* :func:`fit_context` enforces the context budget by CUTTING whole slots in
  priority order (artifact > task > change > candidate > error, i.e. the least
  useful slot goes first). Cutting a slot beats truncating every slot: a model
  reading half of five fields is worse off than reading four complete ones.
* :func:`validate_context` reports problems as a list; it never raises (the same
  fail-soft contract as the rest of the decide layer).
* :func:`redact_context` runs ``decision._redact`` over every string so a
  context hand-off can never leak a credential the state itself would redact.
"""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import Any

import decision

#: Top-level state key the fitted context object rides under.
CONTEXT_KEY = "context"

#: Slot budget in canonical UTF-8 bytes (D-053). :func:`fit_context` defaults to
#: it; ``decision_points._fit_state`` passes the *remaining* headroom inside the
#: 2000 B state budget instead, so the context is always counted there.
CONTEXT_MAX_BYTES = 4000

#: Bytes the enclosing ``"context":`` key adds to the canonical state; the
#: caller subtracts it when computing the headroom so the fitted block really
#: fits instead of fitting "except for the key name".
CONTEXT_KEY_OVERHEAD = 16

#: Marker shape for a truncated value; ``N`` is the number of characters the cut
#: removed (never the number kept), so a reader can judge what it lost.
TRUNCATION_MARKER = "…truncated {removed} chars…"

#: Frozen slot order: also the order ``contextSlots`` renders in the generated
#: TS registry, so the same registry always produces the same bytes.
SLOT_ORDER: tuple[str, ...] = (
    "task_excerpt",
    "change_summary",
    "candidate_snippets",
    "artifact_status",
    "error_excerpt",
)

#: Slot table: ``type`` is the JSON-native kind, ``max_chars``/``max_items`` +
#: ``item_max_chars`` the caps, ``producers`` the dp ids allowed to emit it.
#: ``error_excerpt`` is produced by the failure-carrying dps (dp4/dp6/dp7) and
#: stays in the table so the cut order can name it.
CONTEXT_SLOTS: Mapping[str, Mapping[str, Any]] = MappingProxyType(
    {
        "task_excerpt": MappingProxyType(
            {
                "type": "string",
                "max_chars": 1200,
                "producers": ("dp1-dispatch-type",),
                "description": "Excerpt of the dispatch card ## 上下文 / ## 要求 sections.",
            }
        ),
        "change_summary": MappingProxyType(
            {
                "type": "string",
                "max_chars": 800,
                "producers": ("dp2-checkpoint-split", "dp3-worker-clarify"),
                "description": "One-line summary of what changed since the last checkpoint.",
            }
        ),
        "candidate_snippets": MappingProxyType(
            {
                "type": "array",
                "max_items": 5,
                "item_max_chars": 200,
                "item_required": ("text", "source"),
                "producers": ("dp3-worker-clarify",),
                "description": "Verbatim hit line (first 200 chars) + <path>:<line> source.",
            }
        ),
        "artifact_status": MappingProxyType(
            {
                "type": "array",
                "max_items": 24,
                "item_max_chars": 200,
                "item_required": ("path",),
                "producers": ("dp2-checkpoint-split",),
                "description": "Planned/observed artifacts: {path, exists, bytes}.",
            }
        ),
        "error_excerpt": MappingProxyType(
            {
                "type": "string",
                "max_chars": 1500,
                "producers": ("dp4-failure-handling", "dp6-qg-verdict", "dp7-gate-failure"),
                "description": "Tail of the failing gate/test output (head 60% + tail 40%).",
            }
        ),
    }
)

#: Cut order for :func:`fit_context`: the FIRST entry is dropped first, so the
#: list is "least decision-useful first" (the inverse of the priority order
#: error > candidate > change > task > artifact).
SLOT_CUT_ORDER: tuple[str, ...] = (
    "error_excerpt",
    "artifact_status",
    "task_excerpt",
    "change_summary",
    "candidate_snippets",
)


def slot_spec(name: str) -> Mapping[str, Any] | None:
    """The slot definition, or ``None`` for an unknown slot (never raises)."""
    return CONTEXT_SLOTS.get(name)


def slot_names_for(dp_id: str) -> tuple[str, ...]:
    """Slots one dp is allowed to emit, in :data:`SLOT_ORDER`."""
    return tuple(
        name for name in SLOT_ORDER if dp_id in CONTEXT_SLOTS[name].get("producers", ())
    )


def _truncate_text(text: str, max_chars: int) -> str:
    """Head 60% + tail 40%, with an explicit marker in the dropped middle."""
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    # The marker rides INSIDE the cap: head (60%) + marker + tail (40%) is the
    # budget, and the marker states how many characters the cut removed. Its
    # width is reserved pessimistically (widest possible ``removed`` value) so
    # the result can never exceed ``max_chars``.
    marker_len = len(TRUNCATION_MARKER.format(removed="9" * len(str(len(text)))))
    keep = max(0, max_chars - marker_len)
    head = max(0, int(keep * 0.6))
    tail = max(0, keep - head)
    removed = len(text) - head - tail
    return f"{text[:head]}{TRUNCATION_MARKER.format(removed=removed)}{text[len(text) - tail :] if tail else ''}"


def _truncate_item(item: object, max_chars: int) -> object:
    if isinstance(item, str):
        return _truncate_text(item, max_chars)
    if isinstance(item, Mapping):
        out = dict(item)
        if isinstance(out.get("text"), str):
            out["text"] = _truncate_text(out["text"], max_chars)
        return out
    return item


def truncate_slot(name: str, value: object) -> object:
    """Apply the slot cap; unknown slots and mismatched types pass through.

    Strings become head+marker+tail, arrays are capped by ``max_items`` and each
    item by ``item_max_chars``. Never raises: validation is a separate step.
    """
    spec = slot_spec(name)
    if spec is None:
        return value
    if spec["type"] == "string" and isinstance(value, str):
        return _truncate_text(value, int(spec["max_chars"]))
    if spec["type"] == "array" and isinstance(value, (list, tuple)):
        items = list(value)[: int(spec["max_items"])]
        return [_truncate_item(item, int(spec["item_max_chars"])) for item in items]
    return value


def _context_bytes(context: Mapping) -> int:
    return len(decision._encode_state(dict(context)))


def _cut_order(names: list[str]) -> list[str]:
    """Lowest-priority-first order; unlisted slots go first, name-sorted."""
    known = [name for name in SLOT_CUT_ORDER if name in names]
    unknown = sorted(name for name in names if name not in SLOT_CUT_ORDER)
    return unknown + known


def fit_context(
    context: Mapping | None, *, budget: int = CONTEXT_MAX_BYTES
) -> tuple[dict, tuple[str, ...]]:
    """Fit ``context`` into ``budget`` canonical bytes.

    Returns ``(fitted, cut_slots)``. Each slot is truncated to its own cap first;
    while the block is still too big, whole slots are dropped in
    :data:`SLOT_CUT_ORDER` order (never partially, never a required state field).
    ``budget <= 0`` drops everything.
    """
    fitted: dict[str, Any] = {}
    if isinstance(context, Mapping):
        for name, value in context.items():
            fitted[str(name)] = truncate_slot(str(name), value)
    cut: list[str] = []
    if budget <= 0:
        return {}, tuple(sorted(fitted))
    names = list(fitted)
    for name in _cut_order(names):
        if _context_bytes(fitted) <= budget:
            break
        if name not in fitted:
            continue
        fitted.pop(name, None)
        cut.append(name)
    return fitted, tuple(cut)


def validate_context(context: object, dp_id: str | None = None) -> list[str]:
    """Report context problems as ``path: reason`` strings (never raises).

    ``dp_id`` additionally enforces the per-dp slot whitelist; without it only
    the global :data:`CONTEXT_SLOTS` table is checked.
    """
    issues: list[str] = []
    if not isinstance(context, Mapping):
        return [f"{CONTEXT_KEY}: must be an object"]
    allowed = slot_names_for(dp_id) if dp_id is not None else None
    for raw_name, value in context.items():
        name = str(raw_name)
        spec = slot_spec(name)
        path = f"{CONTEXT_KEY}.{name}"
        if spec is None:
            issues.append(f"{path}: unknown slot")
            continue
        if allowed is not None and name not in allowed:
            issues.append(f"{path}: not a slot of {dp_id}")
        if value is None or (isinstance(value, str) and not value.strip()):
            continue
        if spec["type"] == "string":
            if not isinstance(value, str):
                issues.append(f"{path}: must be a string")
            elif len(value) > int(spec["max_chars"]):
                issues.append(f"{path}: longer than {spec['max_chars']} chars")
            continue
        if not isinstance(value, (list, tuple)):
            issues.append(f"{path}: must be an array")
            continue
        if len(value) > int(spec["max_items"]):
            issues.append(f"{path}: more than {spec['max_items']} items")
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if isinstance(item, str):
                if len(item) > int(spec["item_max_chars"]):
                    issues.append(
                        f"{item_path}: longer than {spec['item_max_chars']} chars"
                    )
                continue
            if not isinstance(item, Mapping):
                issues.append(f"{item_path}: must be a string or an object")
                continue
            for key in spec.get("item_required", ()):
                if not isinstance(item.get(key), str) or not str(item.get(key)).strip():
                    issues.append(f"{item_path}: missing {key}")
            text = item.get("text")
            if isinstance(text, str) and len(text) > int(spec["item_max_chars"]):
                issues.append(
                    f"{item_path}.text: longer than {spec['item_max_chars']} chars"
                )
    return issues


def redact_context(value: object) -> object:
    """``decision._redact`` applied recursively (strings only, shape preserved)."""
    if isinstance(value, str):
        return decision._redact(value)
    if isinstance(value, Mapping):
        return {str(key): redact_context(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact_context(item) for item in value]
    return value
