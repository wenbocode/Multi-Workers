"""decision_points.py — dp registry (single authority) + config read side + decide_for.

Key ``mw-decision-substitution``, card T-01 (``tasks/T-01-registry-controlflow.md``).
Contract anchors (do not re-invent values):

- design.md §2.1 — frozen :class:`DecisionPoint` shape (10 fields) and the
  import-time fail-loud rules (duplicate id / illegal tier / P0 without
  ``p0_consequences`` / P2 without ``executor``).
- design.md §2.2 — ``.mw/decide-points.json`` read side with the eight
  degradation layers L0..L7, plus the in-process cache keyed by
  ``(st_mtime_ns, st_size)`` (a same-second rewrite must be observed).
  L8 is the advisory layer added by spec §14 AC-016: a per-dp policy value
  (``min_confidence``/``max_questions``/``timeout_s``) that is out of range has
  no effect beyond falling back to the next layer, so it is a warning, never a
  degradation that disables the point.
- design.md §2.3 — :func:`decide_for` 11-step control flow. Step 2 (disabled)
  returns before any state encoding or backend resolution, therefore the
  disabled path cannot spawn a process or touch the network.
- spec.md §4 — the 24 dp ids and tiers (ids are frozen; never renamed), plus
  §15 AC-027 — ``dp25-signoff-conclusion`` (the automatic sign-off point).

Archive integration (design.md §1 / §2.4): every decision that reached the
transport layer gets one ``decide`` row written through
``decide_archive.append_decide``. That module is delivered by card T-03 and may
not exist yet; a missing module degrades to "no archive row, log only"
(``ImportError`` only — any other archive failure is fail-loud per D-005).
Pre-transport escalations (disabled / transport-unavailable / input-incomplete /
input-oversize) write no archive row, matching the row column of the Q2
control-flow table in
``evidence/research/design-registry-config-20261019.md``.

Eight-entry protocol (key ``mw-dp-consolidation``, card T03, design §10 D-001A /
D-002A / D-003A / D-009A / D-012A): :data:`DP_REGISTRY` holds exactly the eight
active entries of spec §1.1 (``ACTIVE_DP_IDS``). The 25 pre-consolidation ids
live in the read-only :data:`RETIRED_DP_REGISTRY`; :func:`require_active_dp`
refuses them before any replay lookup, backend resolution, credential snapshot
or archive write, so an old id can never produce a model call or a business
action. The six migrated responsibilities (dp1/dp2/dp3/dp6/dp15/dp25) and the
19 that exit as independent dps are recorded there separately; no old id is a
callable alias. Each entry also declares its ``kind`` / ``role_scope`` /
``candidate_source`` / ``candidate_bounds`` / ``target_entries``, so the answer
enum, the initiating role and the prepared-basis contract have one Python
source (exported by :func:`registry_snapshot`). dp-route only names one of the
other seven entries and dp-auto only picks an id from the PM-prepared
candidates: neither owns an executor, so a selection can never be a release.

Four-DP contract (key ``mw-decision-context``, design §2): the migrated
w-type/pm-steer/w-check-task/sign-key entries declare the approved business
material only. :data:`MODEL_STATE_FIELDS` is the
single per-dp model key table (exported to JSON/TS) and :func:`model_state_for`
is the one projection the decide path applies before the budget, the snapshot
and the transport, so identity (``schema_version``/``decision_point``/
``questions_version``) and local association facts (``key``/``task_key``/
``trigger_id``) never reach the model. The other 21 dps have no allowlist entry
and keep their existing contract unchanged.

Observation seam (card T05, design §5.3 / D-003): ``decide_for(observation=...)``
is the explicit human observe-only channel. It validates the paired contract
(``intent="answer"``, ``archive=False``, an isolated ``test`` scope with its own
``evidence_path``) before doing any work, bypasses **only** the per-DP
authorization gate, and never reaches the executor. Every decision that gets a
capture scope also writes a ``decision-end`` row (status plus the archive
signal ``created``/``replayed``/``skipped``/``failed``/``unknown``/
``not-attempted``; an archive exception is recorded as ``failed`` and then
re-raised unchanged) and, when state material existed, a ``book-snapshot`` row
(``book`` or ``input-state`` plus the rendered candidate enum) through the
injected redactor. ``authorization_preview`` is the shared pure verdict used by
the monitor: it never claims an act, let alone a successful one.
"""

from __future__ import annotations

import contextlib
import copy
import datetime
import hashlib
import inspect
import json
import logging
import math
import pathlib
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any

import decision
import decision_context

__all__ = [
    "ACTIVE_DP_IDS",
    "ACTOR_ID_MAX_BYTES",
    "ACTOR_KINDS",
    "ACTOR_ROLES",
    "ARCHIVE_STATES",
    "BASIS_ITEM_KEYS",
    "BASIS_SOURCE",
    "CAPTURE_CHANNELS",
    "CANDIDATE_ITEM_KEYS",
    "CANDIDATE_LABEL_MAX",
    "DECISIONS_RELATIVE_PATH",
    "DECIDE_POINTS_RELATIVE_PATH",
    "DP_REGISTRY",
    "ENTRY_CHOICES",
    "ENTRY_IDS",
    "ENTRY_KINDS",
    "ENTRY_ROLES",
    "ESCALATED_REASONS",
    "EXPECTED_DP_COUNT",
    "GATE_KIND_ENUM",
    "INTENTS",
    "MAX_STATE_BYTES",
    "CONTEXT_MAX_BYTES",
    "CONTEXT_SLOTS",
    "MIN_CONFIDENCE",
    "MODES",
    "POLICY_DEFAULTS",
    "POLICY_KEYS",
    "POLICY_LAYERS",
    "POLICY_ROW_BOUNDS",
    "PREPARATION_KEYS",
    "RETIRED_DP_IDS",
    "RETIRED_DP_REGISTRY",
    "RETIRED_STATE_FIELDS",
    "ROUTE_TARGETS",
    "SNAPSHOT_WIRING_KEYS",
    "STATE_ARRAY_ITEM_MAX_BYTES",
    "STATE_ARRAY_MAX_ITEMS",
    "STATE_ARRAY_MAX_ITEMS_WIDE",
    "STATE_FIELD_CONSTRAINT_KEYS",
    "STATE_FIELD_CROSS_CHECKS",
    "STATE_FIELD_DESCRIPTIONS",
    "STATE_FIELD_TYPES",
    "STATE_STRING_MAX_BYTES",
    "DecisionOutcome",
    "DecisionPoint",
    "Observation",
    "RetiredDecisionPoint",
    "MODEL_STATE_FIELDS",
    "AUDIT_STATE_PATHS",
    "NON_MATERIAL_STATE_KEYS",
    "QUESTION_INSTRUCTIONS_MAX_BYTES",
    "QUESTION_OVERRIDE_FIELDS",
    "QuestionOverride",
    "apply_question_override",
    "basis_catalog_issues",
    "basis_selection_issues",
    "entry_candidates_issues",
    "entry_choice_issues",
    "entry_material_issues",
    "is_retired_dp",
    "pm_candidate_issues",
    "pm_note_issues",
    "preparation_issues",
    "prepared_request_issues",
    "question_override_issues",
    "require_active_dp",
    "resolve_entry_choices",
    "retired_dp",
    "role_issues",
    "sign_key_material_issues",
    "vision_dispatch_issues",
    "resolve_question_override",
    "send_state",
    "model_state_for",
    "PointConfig",
    "PointsConfig",
    "SNAPSHOT_KINDS",
    "TIERS",
    "Trigger",
    "UNWIRED_SNAPSHOT_WIRING",
    "OPTIONAL_STATE_FIELDS",
    "authorization_preview",
    "clear_points_config_cache",
    "decide_for",
    "decide_points_config_path",
    "dynamic_choice_labels",
    "dynamic_choices_value_error",
    "get_decision_point",
    "load_points_config",
    "questions_map",
    "registry_snapshot",
    "registry_snapshot_text",
    "coerce_policy_value",
    "resolve_dynamic_choices",
    "resolve_policy",
    "resolve_policy_origins",
    "snapshot_field_dict",
    "state_field_issues",
    "state_identity_issues",
    "state_unknown_key_issues",
    "register_book_validator",
]

_LOGGER = logging.getLogger("multi_workers.decision_points")

#: Authorization table (design D-001: the only authority source).
DECIDE_POINTS_RELATIVE_PATH = pathlib.Path(".mw") / "decide-points.json"
#: Decision archive (design §2.4; single writer = decide_archive.py, card T-03).
DECISIONS_RELATIVE_PATH = pathlib.Path(".agenticdoc") / "_autopilot" / "decisions.jsonl"

TIERS = ("P0", "P1", "P2")
MODES = ("auto", "suggest")
STATUSES = ("acted", "suggested", "escalated")

#: ``decide_for`` intent (design D-035): ``act`` runs the executor (steps 10/11),
#: ``answer`` returns the advice only (executor skipped, ``acted=false`` row).
INTENTS = ("act", "answer")

#: Structured input budget (spec §5.4 / design D-019). Measured, not guessed:
#: the four shipped complete cases encode to 385/1095/831/856 B and the real
#: T03 pm-producers card material (its `## 上下文` / `## 要求` / `## 交付格式`
#: sections, verbatim) encodes to 2570 B — every real worker card on disk since
#: then stays at or below 3868 B. 8192 B is the smallest power of two at least
#: twice that measured maximum, so a complete real material fits with headroom
#: while a genuinely oversized state is still refused whole (never truncated)
#: by :func:`_fit_state` / ``decide_for``. The transport keeps its own real
#: gates in ``decision.DecisionConfig`` (``max_state_plus_question_tokens``
#: default 32768, ``max_total_tokens`` 65536, optional project byte ceiling
#: ``max_state_bytes`` default 0 = off); 8192 B is far inside them: the measured
#: real card is 769 estimated tokens, and even 8192 all-ASCII bytes are ~2048.
MAX_STATE_BYTES = 8192
#: The state ``schema_version`` the builder writes and every producer must echo.
#: Single authority for the state identity (the decision book delegates to the
#: same constant/check instead of keeping a second version table).
STATE_SCHEMA_VERSION = 2
#: Context budget (W6 / D-053): the ``context`` block alone never exceeds 4000 B,
#: and inside a state it is fitted to the headroom under :data:`MAX_STATE_BYTES`.
CONTEXT_MAX_BYTES = decision_context.CONTEXT_MAX_BYTES
#: Slot table authority (type/caps/producers); the TS registry is generated from
#: :func:`decision_context.slot_names_for`, so it is re-exported here for callers.
CONTEXT_SLOTS = decision_context.CONTEXT_SLOTS
#: Confidence gate floor when ``confidence_source == "api"`` (design §2.3 step 8);
#: overridable through ``.mw/decide.json`` ``min_confidence`` (lands in extras).
MIN_CONFIDENCE = 0.7
#: Number of registered decision points: exactly the eight active entries of
#: spec §1.1 (T03). The 25 pre-consolidation ids are retired, never registered.
EXPECTED_DP_COUNT = 8

#: The three per-dp policy knobs (spec §14 AC-016 / design D-048). ``model`` and
#: ``transport`` are deliberately NOT here: they stay global so the signed
#: engine triple cannot be overridden per point.
POLICY_KEYS = ("min_confidence", "max_questions", "timeout_s")

#: Built-in (last-resort) layer of the resolve order. ``MIN_CONFIDENCE`` is the
#: single global constant every dp uses today, so it is also the per-dp builtin.
POLICY_DEFAULTS: dict[str, float | int] = {
    "min_confidence": MIN_CONFIDENCE,
    "max_questions": 8,
    "timeout_s": 20,
}

#: Legal domain of a per-dp ROW value. The global ``.mw/decide.json`` layer keeps
#: its own looser transport budget (any positive integer / number) so an existing
#: file that already set ``max_questions=12`` keeps working.
POLICY_ROW_BOUNDS: dict[str, tuple[float, float]] = {
    "min_confidence": (0.0, 1.0),
    "max_questions": (1.0, 8.0),
    "timeout_s": (1.0, 300.0),
}

#: Resolve order labels, strongest first (AC-016: row > decide.json > builtin).
POLICY_LAYERS = ("row", "decide.json", "builtin")

#: Frozen ``escalated_reason`` values — the single vocabulary for the whole
#: feature (design D-030). ``decide_archive._ESCALATED_REASONS`` validates the
#: same set (plus the read-only ``input-invalid`` legacy value), so an archived
#: reason is the real cause instead of an archive-side synonym. Transport reasons
#: (``decision.REASON_CODES``) are carried in
#: :attr:`DecisionOutcome.transport_reason`, so a single escalation never has
#: two competing vocabularies.
#:
#: ``p0`` is reserved for a P0 point that must be confirmed by a human after it
#: reached the transport layer (lands with the P0 confirmation path); it is part
#: of the vocabulary now so the two modules cannot drift again.
ESCALATED_REASONS = frozenset(
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


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Trigger:
    """One decision request as handed in by a call site.

    ``data`` is the caller-supplied L0/L1 material consumed by
    ``DecisionPoint.build_state``; it must never carry credentials, user
    quotations, absolute paths or code (spec §5.4 L2). ``trigger_id`` becomes
    the ``decision_id`` suffix (``<dp>:<trigger_id>``, spec §6.1).
    """

    trigger_id: str | None = None
    key: str = ""
    task_key: str | None = None
    data: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def from_mapping(
        cls,
        raw: Mapping[str, Any] | None = None,
        *,
        trigger_id: str | None = None,
        key: str | None = None,
        task_key: str | None = None,
    ) -> "Trigger":
        """Build a trigger from a plain mapping (CLI / JSON call sites)."""
        payload = dict(raw or {})
        return cls(
            trigger_id=trigger_id or payload.get("trigger_id"),
            key=key if key is not None else str(payload.get("key") or ""),
            task_key=task_key if task_key is not None else payload.get("task_key"),
            data=payload,
        )

    def resolved_id(self) -> str:
        """``trigger_id`` fallback chain: explicit id -> task_key -> key -> ts."""
        if self.trigger_id:
            return str(self.trigger_id)
        if self.task_key:
            return str(self.task_key)
        if self.key:
            return str(self.key)
        return datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _coerce_trigger(trigger: Trigger | Mapping | None) -> Trigger:
    if isinstance(trigger, Trigger):
        return trigger
    if isinstance(trigger, Mapping):
        return Trigger.from_mapping(trigger)
    if trigger is None:
        return Trigger()
    # Duck-typed call sites (objects exposing .data/.key) are accepted read-only.
    data = getattr(trigger, "data", None)
    return Trigger(
        trigger_id=getattr(trigger, "trigger_id", None),
        key=str(getattr(trigger, "key", "") or ""),
        task_key=getattr(trigger, "task_key", None),
        data=dict(data) if isinstance(data, Mapping) else {},
    )


# ---------------------------------------------------------------------------
# Registry (design §2.1)
# ---------------------------------------------------------------------------


#: Question keys that make up :func:`_questions_version` (FIX-O contract):
#: only the question *shape* is versioned. ``instructions`` / ``labels`` /
#: ``criteria`` are model-facing text — editing the wording must not change the
#: version an archived row or a ``state.questions_version`` handshake carries.
VERSIONED_QUESTION_KEYS = ("id", "type", "choices", "dynamic_choices")

#: The only legal ``noul`` criteria keys (FIX-O): the two boolean outcomes.
NOUL_CRITERIA_KEYS = frozenset({"true", "false"})


def _validate_question(dp_id: str, question: object, seen: set[str]) -> None:
    """Import-time question validation (mirrors the decision.py input rules)."""
    if not isinstance(question, Mapping):
        raise ValueError(f"{dp_id}: question must be a mapping, got {type(question).__name__}")
    qid = question.get("id")
    if not isinstance(qid, str) or not qid:
        raise ValueError(f"{dp_id}: question id must be a non-empty string")
    if qid in seen:
        raise ValueError(f"{dp_id}: duplicate question id {qid!r}")
    seen.add(qid)
    qtype = question.get("type")
    if qtype not in decision.QUESTION_TYPES:
        raise ValueError(f"{dp_id}: question {qid!r} has unknown type {qtype!r}")
    if qtype != decision.QUESTION_CHOICE and "dynamic_choices" in question:
        raise ValueError(
            f"{dp_id}: question {qid!r} 'dynamic_choices' is only valid for type 'choice'"
        )
    if qtype == decision.QUESTION_CHOICE:
        choices = question.get("choices")
        dynamic_key = question.get("dynamic_choices")
        if dynamic_key is not None:
            # FIX-I: the candidate ids are rendered from state at decide time;
            # a static list would make two authorities for the same enum.
            if not isinstance(dynamic_key, str) or not dynamic_key.strip():
                raise ValueError(
                    f"{dp_id}: question {qid!r} 'dynamic_choices' must be a non-empty state key"
                )
            if choices is not None:
                raise ValueError(
                    f"{dp_id}: question {qid!r} cannot carry both 'choices' and 'dynamic_choices'"
                )
        elif not isinstance(choices, list) or not choices:
            raise ValueError(f"{dp_id}: question {qid!r} type 'choice' requires a non-empty choices list")
    if qtype == decision.QUESTION_SCORE:
        low, high = question.get("min"), question.get("max")
        if not isinstance(low, int) or not isinstance(high, int) or isinstance(low, bool) or isinstance(high, bool):
            raise ValueError(f"{dp_id}: question {qid!r} type 'score' requires integer min/max")
        if low > high:
            raise ValueError(f"{dp_id}: question {qid!r} min ({low}) exceeds max ({high})")
    if "instructions" in question:
        instructions = question.get("instructions")
        if not isinstance(instructions, str) or not instructions.strip():
            raise ValueError(
                f"{dp_id}: question {qid!r} 'instructions' must be a non-empty string"
            )
    if "labels" in question:
        labels = question.get("labels")
        if qtype != decision.QUESTION_CHOICE:
            raise ValueError(
                f"{dp_id}: question {qid!r} 'labels' is only valid for type 'choice'"
            )
        if question.get("dynamic_choices") is not None:
            # Dynamic choices render their labels from state (FIX-I); a static
            # label map would be a second authority for the same enum.
            raise ValueError(
                f"{dp_id}: question {qid!r} 'labels' is not allowed on a dynamic choice"
            )
        if not isinstance(labels, Mapping) or not all(
            isinstance(option, str) and isinstance(label, str)
            for option, label in labels.items()
        ):
            raise ValueError(
                f"{dp_id}: question {qid!r} 'labels' must be a string->string mapping"
            )
        choices = question.get("choices")
        if set(labels) != set(choices or []):
            raise ValueError(
                f"{dp_id}: question {qid!r} 'labels' keys must equal 'choices' exactly"
            )
    if qtype == decision.QUESTION_NOUL and "criteria" in question:
        criteria = question.get("criteria")
        if not isinstance(criteria, Mapping):
            raise ValueError(f"{dp_id}: question {qid!r} 'criteria' must be a mapping")
        if set(criteria) != NOUL_CRITERIA_KEYS:
            raise ValueError(
                f"{dp_id}: question {qid!r} 'criteria' must have exactly the keys 'true' and 'false'"
            )
        if not all(isinstance(value, str) for value in criteria.values()):
            raise ValueError(f"{dp_id}: question {qid!r} 'criteria' values must be strings")


def _questions_version(questions: tuple[dict, ...]) -> str:
    """Content hash short code (``q-<8 hex>``): changes with the question set.

    Only :data:`VERSIONED_QUESTION_KEYS` are hashed (FIX-O): the version names
    the question *shape*, so adding model-facing ``instructions`` / ``labels`` /
    ``criteria`` text leaves every registered ``questions_version`` untouched.

    The ``q-`` prefix is the shape the decision archive validates (card T-03:
    ``decide_archive._QUESTIONS_VERSION_RE``), so a row can never carry a
    version string the archive layer would reject.
    """
    versioned = [
        {key: question[key] for key in VERSIONED_QUESTION_KEYS if key in question}
        for question in questions
    ]
    canonical = json.dumps(list(versioned), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "q-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:8]


@dataclass(frozen=True)
class DecisionPoint:
    """One registered decision point (design §2.1; the registry is code).

    Import-time fail-loud rules live in :meth:`__post_init__`: a broken registry
    is a code bug, in deliberate contrast to the fail-soft config read side.
    """

    id: str
    tier: str
    default_enabled: bool
    default_mode: str
    questions: tuple[dict, ...]
    build_state: Callable[[Trigger], dict]
    executor: Callable[[dict, Trigger], str] | None
    questions_version: str
    p0_consequences: str | None
    description: str
    # T03 protocol identity (defaults keep every hand-built test point constructible):
    # how the answer enum is produced, who may initiate, where candidates come
    # from and (route only) which entries may be targeted.
    kind: str = "fixed"
    role_scope: str = "pm"
    candidate_source: str = "static-enum"
    candidate_bounds: Mapping[str, object] | None = None
    target_entries: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("DecisionPoint.id must be a non-empty string")
        if self.tier not in TIERS:
            raise ValueError(f"{self.id}: tier must be P0|P1|P2, got {self.tier!r}")
        if self.default_enabled is not (self.tier == "P2"):
            raise ValueError(f"{self.id}: default_enabled must follow tier (P2 on, P1/P0 off)")
        if self.default_mode not in MODES:
            raise ValueError(f"{self.id}: default_mode must be auto|suggest, got {self.default_mode!r}")
        if not isinstance(self.questions, tuple) or not self.questions:
            raise ValueError(f"{self.id}: questions must be a non-empty tuple")
        if len(self.questions) > decision.DecisionConfig.max_questions:
            raise ValueError(f"{self.id}: more than {decision.DecisionConfig.max_questions} questions")
        seen: set[str] = set()
        for question in self.questions:
            _validate_question(self.id, question, seen)
        if not isinstance(self.questions_version, str) or not self.questions_version:
            raise ValueError(f"{self.id}: questions_version must be a non-empty short code")
        if not callable(self.build_state):
            raise ValueError(f"{self.id}: build_state must be callable")
        if self.executor is not None and not callable(self.executor):
            raise ValueError(f"{self.id}: executor must be callable or None")
        if self.tier == "P0":
            if not isinstance(self.p0_consequences, str) or not self.p0_consequences.strip():
                raise ValueError(f"{self.id}: P0 dp requires p0_consequences")
        if self.tier == "P2" and self.executor is None:
            raise ValueError(f"{self.id}: P2 dp requires an executor (auto mode must be able to act)")
        if not isinstance(self.description, str) or not self.description:
            raise ValueError(f"{self.id}: description must be a non-empty string")
        if self.kind not in ENTRY_KINDS:
            raise ValueError(f"{self.id}: kind must be one of {list(ENTRY_KINDS)}")
        if self.role_scope not in ACTOR_ROLES:
            raise ValueError(f"{self.id}: role_scope must be one of {list(ACTOR_ROLES)}")
        if not isinstance(self.candidate_source, str) or not self.candidate_source.strip():
            raise ValueError(f"{self.id}: candidate_source must be a non-empty string")
        if self.kind == "fixed" and self.candidate_source != "static-enum":
            raise ValueError(f"{self.id}: a fixed entry must use candidate_source 'static-enum'")
        if self.kind == "route-targets":
            if self.candidate_source != "entry-targets":
                raise ValueError(f"{self.id}: a route entry must use candidate_source 'entry-targets'")
            if tuple(self.target_entries) != ROUTE_TARGETS or self.id in self.target_entries:
                raise ValueError(f"{self.id}: route targets must be the seven other active entries")
        elif self.kind == "dynamic-candidates":
            if not self.candidate_source.startswith("pm-supplied:"):
                raise ValueError(
                    f"{self.id}: a dynamic entry must declare 'pm-supplied:<state field>'"
                )
            if self.target_entries:
                raise ValueError(f"{self.id}: target_entries are route-only")
        elif self.target_entries:
            raise ValueError(f"{self.id}: target_entries are route-only")
        if self.candidate_bounds is not None and not isinstance(self.candidate_bounds, Mapping):
            raise ValueError(f"{self.id}: candidate_bounds must be a mapping or None")
        if self.kind in ("dynamic-candidates", "route-targets"):
            if self.executor is not None and not getattr(self.executor, "unwired", False):
                raise ValueError(
                    f"{self.id}: {self.kind} entries must not own an executor "
                    "(a selection is not a release)"
                )


def _state_builder(dp_id: str) -> Callable[[Trigger], dict]:
    """Generic L0/L1 state builder: registry identity + caller-supplied data.

    Never fabricates defaults for required fields (spec §6 Q5.5): a missing
    field stays missing so :func:`decide_for` can escalate ``input-incomplete``.
    """

    def build_state(trigger: Trigger) -> dict:
        state: dict[str, Any] = {"schema_version": STATE_SCHEMA_VERSION, "decision_point": dp_id}
        for name, value in dict(trigger.data or {}).items():
            state.setdefault(name, value)
        if trigger.key and not state.get("key"):
            state["key"] = trigger.key
        if trigger.task_key and not state.get("task_key"):
            state["task_key"] = trigger.task_key
        registry_dp = _REGISTRY_BY_ID.get(dp_id)
        if registry_dp is not None and not state.get("questions_version"):
            state["questions_version"] = registry_dp.questions_version
        return state

    return build_state


def _unwired_executor(dp_id: str) -> Callable[[dict, Trigger], str]:
    """Executor placeholder for P2 points whose call site lands later (T-06/T-07).

    It raises on purpose: DS-4 forbids a default action, so an unwired executor
    escalates to a human as ``over-authority`` instead of pretending to act.
    """

    def executor(answers: dict, trigger: Trigger) -> str:
        raise NotImplementedError(f"{dp_id}: executor not wired yet (call site card pending)")

    # Marker read by :func:`_executor_kind` (and the export drift test): the
    # placeholder is registered, so ``executor is not None``, but it can never
    # act. Detecting it by marker instead of by qualname survives a rename of
    # the factory and needs no call (a call raises by design).
    executor.unwired = True  # type: ignore[attr-defined]
    return executor


def _echo_conclusion_executor(dp_id: str) -> Callable[[dict, Trigger], str]:
    """Side-effect-free executor: echo the answered conclusion back to the caller.

    For ``dp25-signoff-conclusion`` the answer *is* the whole action, so this
    executor writes nothing: it returns ``signoff:<conclusion>`` from the answer
    (falling back to the trigger state's ``conclusion``) and touches no file, no
    network and no config. The sign-off file stays owned by ``mw decide sign``;
    an ``intent="answer"`` call site never reaches this function at all (step 9
    returns before the executor branch). Registering it satisfies the P2 rule
    "auto mode must be able to act" without creating a second authority for the
    sign file.
    """

    def executor(answers: dict, trigger: Trigger) -> str:
        item = dict(answers or {}).get("q-conclusion")
        value = item.get("value") if isinstance(item, Mapping) else item
        if not isinstance(value, str) or not value.strip():
            state = getattr(trigger, "data", None)
            value = state.get("conclusion") if isinstance(state, Mapping) else None
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{dp_id}: no conclusion to echo")
        return f"signoff:{value}"

    return executor


def _point(
    *,
    dp_id: str,
    tier: str,
    questions: tuple[dict, ...],
    description: str,
    p0_consequences: str | None = None,
    executor: Callable[[dict, Trigger], str] | None = None,
    default_mode: str = "auto",
    role_scope: str = "pm",
    kind: str = "fixed",
    candidate_source: str = "static-enum",
    candidate_bounds: Mapping[str, object] | None = None,
    target_entries: tuple[str, ...] = (),
) -> DecisionPoint:
    """Registry entry factory: derives default_enabled / questions_version."""
    return DecisionPoint(
        id=dp_id,
        tier=tier,
        default_enabled=(tier == "P2"),
        default_mode=default_mode,
        questions=questions,
        build_state=_state_builder(dp_id),
        executor=executor,
        questions_version=_questions_version(questions),
        p0_consequences=p0_consequences,
        description=description,
        kind=kind,
        role_scope=role_scope,
        candidate_source=candidate_source,
        candidate_bounds=candidate_bounds,
        target_entries=target_entries,
    )


# ---------------------------------------------------------------------------
# Eight active entries (T03: design §10 D-003A + D-009A)
# ---------------------------------------------------------------------------

#: The exact active (callable) decision points, spec §1.1 order.
ACTIVE_DP_IDS: tuple[str, ...] = (
    "dp-w-type",
    "dp-pm-steer",
    "dp-w-check-task",
    "dp-QG",
    "dp-gate-approve",
    "dp-sign-key",
    "dp-auto",
    "dp-route",
)
#: Explicit alias for callers that speak of "entries" instead of "points".
ENTRY_IDS: tuple[str, ...] = ACTIVE_DP_IDS

#: The seven entries dp-route may select (itself is never a target).
ROUTE_TARGETS: tuple[str, ...] = tuple(
    entry for entry in ACTIVE_DP_IDS if entry != "dp-route"
)

#: How an entry's answer enum is produced.
ENTRY_KINDS: tuple[str, ...] = ("fixed", "dynamic-candidates", "route-targets")

#: Roles eligible to *initiate* an entry (design §4.1). Eligibility only: it
#: grants no tool, write face, budget or role beyond the existing process bind.
ACTOR_ROLES: tuple[str, ...] = ("pm", "worker")

ENTRY_ROLES: Mapping[str, str] = MappingProxyType(
    {
        "dp-w-type": "pm",
        "dp-pm-steer": "pm",
        "dp-w-check-task": "worker",
        "dp-QG": "pm",
        "dp-gate-approve": "pm",
        "dp-sign-key": "pm",
        "dp-auto": "pm",
        "dp-route": "pm",
    }
)

#: Frozen technical choice ids per entry (single source: the registry questions
#: are built from this table and validated against it at import time).
ENTRY_CHOICES: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "dp-w-type": ("coding", "research", "review", "vision"),
        "dp-pm-steer": ("narrow", "split", "direct-exec", "escalate"),
        # AC-046, three frozen ids (no dynamic 2..5/cN surface):
        # continue    = conditions are sufficient, keep working;
        # terminate   = conditions are insufficient, output the truthful
        #               completed/unfinished/blocked conclusion and end THIS run
        #               (never the goal or the key);
        # investigate = keep working and gather bounded evidence for the named
        #               unknown (investigation.* plan required).
        "dp-w-check-task": ("continue", "terminate", "investigate"),
        "dp-QG": ("pass", "fix", "reopen"),
        "dp-gate-approve": ("approve", "steer", "need_fix", "reject"),
        "dp-sign-key": ("finalize", "continue", "user-confirm"),
        # dp-auto has no static menu: the PM prepares the candidates per request.
        "dp-auto": (),
        "dp-route": ROUTE_TARGETS,
    }
)

#: Per-entry answer-enum provenance. ``pm-supplied:`` names the state field the
#: PM fills; ``entry-targets`` can only name another active entry. The old dp3
#: ``2..5`` / contiguous-``cN`` rules are NOT part of any active entry (they
#: survive only as the legacy renderer's history).
ENTRY_CANDIDATE_SOURCE: Mapping[str, str] = MappingProxyType(
    {
        "dp-w-type": "static-enum",
        "dp-pm-steer": "static-enum",
        "dp-w-check-task": "static-enum",
        "dp-QG": "static-enum",
        "dp-gate-approve": "static-enum",
        "dp-sign-key": "static-enum",
        "dp-auto": "pm-supplied:handling_options",
        "dp-route": "entry-targets",
    }
)

ENTRY_CANDIDATE_BOUNDS: Mapping[str, Mapping[str, object] | None] = MappingProxyType(
    {
        "dp-auto": MappingProxyType({"min": 2, "max": None, "id_scheme": "free"}),
    }
)

#: Dispositions of a retired id. ``migrated`` names the active entry that
#: carries the responsibility today; ``retired`` means the independent DP duty
#: ended (its note may name the entry that absorbed the business scenario).
RETIRED_DISPOSITIONS: tuple[str, ...] = ("migrated", "retired")


@dataclass(frozen=True)
class RetiredDecisionPoint:
    """Read-only explanation of one pre-consolidation DP (never callable).

    The record exists so history can explain *what happened to* an old id. It is
    not a registry entry: it carries no questions, no state contract and no
    executor, and :func:`require_active_dp` refuses every one of these ids before
    any work happens. ``migrated_to`` explains the responsibility move; the
    runtime never follows it as an alias.
    """

    id: str
    tier: str
    description: str
    disposition: str
    migrated_to: str | None
    note: str


#: Read-only cross-field explanation of the retired entries (never enforced).
RETIRED_STATE_FIELD_CROSS_CHECKS: Mapping[str, tuple[dict[str, str], ...]] = MappingProxyType(
    {
        "dp4-failure-handling": (
            {"kind": "lte", "left": "failure.attempt", "right": "failure.limit"},
        ),
        "dp6-qg-verdict": (
            {"kind": "count_lte", "array": "qg.checks_failed", "bound": "qg.checks_total"},
        ),
        "dp17-spec-lock": (
            {"kind": "subset", "items": "spec.ac_changed", "of": "spec.ac_ids"},
        ),
        "dp20-stage-close": (
            {"kind": "lte", "left": "stage.tasks_done", "right": "stage.tasks_total"},
        ),
        "dp3-worker-clarify": (
            {"kind": "dynamic_candidates", "array": "handling_options"},
        ),
    }
)


#: The 25 pre-consolidation ids, read-only (spec §1.1: 6 migrated, 19 retired).
RETIRED_DP_REGISTRY: tuple[RetiredDecisionPoint, ...] = (
    RetiredDecisionPoint(
        "dp1-dispatch-type",
        "P2",
        "派发 type/角色/范围",
        "migrated",
        "dp-w-type",
        "职责迁至 dp-w-type（含 vision 候选）；旧编号只读解释，不是可调用别名。",
    ),
    RetiredDecisionPoint(
        "dp2-checkpoint-split",
        "P2",
        "checkpoint 拆/收/直执",
        "migrated",
        "dp-pm-steer",
        "职责迁至 dp-pm-steer；四项 ID 与不降目标语义保留。",
    ),
    RetiredDecisionPoint(
        "dp3-worker-clarify",
        "P2",
        "worker 澄清（问题原文 + 四项背景 + 针对问题的处理候选）",
        "migrated",
        "dp-w-check-task",
        "职责迁至 dp-w-check-task；旧动态 2..5/cN 候选不迁移。",
    ),
    RetiredDecisionPoint(
        "dp4-failure-handling",
        "P1",
        "失败处置",
        "retired",
        None,
        "独立 DP 职责退出；失败事实与处置规则仍由既有框架硬检查保留。",
    ),
    RetiredDecisionPoint(
        "dp5-test-triage",
        "P2",
        "测试失败归类",
        "retired",
        None,
        "独立 DP 职责退出；测试基线/回归分类仍由既有测试流程与硬检查保留。",
    ),
    RetiredDecisionPoint(
        "dp6-qg-verdict",
        "P1",
        "QG 结论处置",
        "migrated",
        "dp-QG",
        "职责迁至 dp-QG；pass/fix/reopen 为正式审核结论。",
    ),
    RetiredDecisionPoint(
        "dp7-gate-failure",
        "P2",
        "相位门禁失败",
        "retired",
        None,
        "相位门失败后的 PM 处置交 dp-auto（职责吸收，不是别名）；原门禁判据不重写。",
    ),
    RetiredDecisionPoint(
        "dp8-scope-change",
        "P0",
        "变更范围",
        "retired",
        None,
        "独立 DP 职责退出；写面/范围硬检查与授权边界不因退役放宽。",
    ),
    RetiredDecisionPoint(
        "dp9-model-select",
        "P2",
        "模型/降级选择",
        "retired",
        None,
        "独立 DP 职责退出；模型/降级仍由既有配置与能力检查约束。",
    ),
    RetiredDecisionPoint(
        "dp10-dependency",
        "P1",
        "依赖升级",
        "retired",
        None,
        "独立 DP 职责退出；依赖变更仍走既有评审与 lockfile 规则。",
    ),
    RetiredDecisionPoint(
        "dp11-credential",
        "P0",
        "凭据/权限",
        "retired",
        None,
        "独立 DP 职责退出；凭证隔离与权限硬检查不删、不放宽。",
    ),
    RetiredDecisionPoint(
        "dp12-destructive",
        "P0",
        "破坏性操作",
        "retired",
        None,
        "独立 DP 职责退出；破坏性操作的人工确认与备份规则仍然生效。",
    ),
    RetiredDecisionPoint(
        "dp13-commit-release",
        "P0",
        "提交(P1) / 发布+版本号(P0)",
        "retired",
        None,
        "独立 DP 职责退出；提交/发布仍按发布流程与人工授权执行。",
    ),
    RetiredDecisionPoint(
        "dp14-rule-conflict",
        "P0",
        "用户指令 vs 规则",
        "retired",
        None,
        "独立 DP 职责退出；规则冲突仍须用户明确确认，不自动越权。",
    ),
    RetiredDecisionPoint(
        "dp15-autopilot-gate",
        "P0",
        "6 类人工门",
        "migrated",
        "dp-gate-approve",
        "职责迁至 dp-gate-approve 四选项；PM note 与模型依据分别保存。",
    ),
    RetiredDecisionPoint(
        "dp16-goal",
        "P0",
        "goal 确立/变更",
        "retired",
        None,
        "独立 DP 职责退出；goal 采用仍按 H06 授权规则，不由退役别名放行。",
    ),
    RetiredDecisionPoint(
        "dp17-spec-lock",
        "P1",
        "spec/AC 锁定",
        "retired",
        None,
        "独立 DP 职责退出；AC/VC 冻结与受控变更规则不因退役消失。",
    ),
    RetiredDecisionPoint(
        "dp18-claim",
        "P1",
        "key 抢占冲突",
        "retired",
        None,
        "独立 DP 职责退出；claim/独占写面检查仍是硬门。",
    ),
    RetiredDecisionPoint(
        "dp19-foreign-write",
        "P0",
        "越面写预授权",
        "retired",
        None,
        "独立 DP 职责退出；越面写仍需明确授权与写面协调。",
    ),
    RetiredDecisionPoint(
        "dp20-stage-close",
        "P0",
        "stage 闭环",
        "retired",
        None,
        "阶段关闭 gate 审批由 dp-gate-approve 承接（职责吸收，不是别名）。",
    ),
    RetiredDecisionPoint(
        "dp21-refine",
        "P2",
        "project-refine 升级",
        "retired",
        None,
        "独立 DP 职责退出；refine 流程如需裁决走现场准备的 dp-auto。",
    ),
    RetiredDecisionPoint(
        "dp22-debug-plan",
        "P2",
        "debug 方案确认",
        "retired",
        None,
        "独立 DP 职责退出；debug 流程仍按既有系统性调试规则执行。",
    ),
    RetiredDecisionPoint(
        "dp23-snapshot",
        "P2",
        "memory 快照",
        "retired",
        None,
        "独立 DP 职责退出；快照写入仍按既有记忆流程处理。",
    ),
    RetiredDecisionPoint(
        "dp24-pi-trust",
        "P0",
        "pi core 交互",
        "retired",
        None,
        "独立 DP 职责退出；pi 信任边界与核心禁止面不变。",
    ),
    RetiredDecisionPoint(
        "dp25-signoff-conclusion",
        "P2",
        "任意 key 收尾的签收结论（按 key 计算，替代人签）",
        "migrated",
        "dp-sign-key",
        "职责迁至 dp-sign-key；四部材料与三数组契约原样保留。",
    ),
)

#: The 25 retired ids as a set (old ids are never callable aliases).
RETIRED_DP_IDS: frozenset[str] = frozenset(record.id for record in RETIRED_DP_REGISTRY)


#: The eight active entries (spec §1.1). Each one declares its own answer enum,
#: initiating role, candidate provenance and (only for dp-auto) candidate bounds.
DP_REGISTRY: tuple[DecisionPoint, ...] = (
    _point(
        dp_id="dp-w-type",
        tier="P2",
        description="Worker 派发类型（coding/research/review/vision）",
        role_scope="pm",
        questions=(
            {
                "id": "triage_type",
                "type": "choice",
                "choices": list(ENTRY_CHOICES["dp-w-type"]),
                "instructions": "这个任务应该派给哪一类 worker？",
                "labels": {
                    "coding": "需要写代码或改代码或跑命令",
                    "research": "只做检索取证不改代码",
                    "review": "审计别人已完成的产出",
                    "vision": "需要读取图片，且有效模型必须已证明图像能力",
                },
            },
        ),
        executor=_unwired_executor("dp-w-type"),
    ),
    _point(
        dp_id="dp-pm-steer",
        tier="P2",
        description="PM 任务编排（narrow/split/direct-exec/escalate，不降目标）",
        role_scope="pm",
        questions=(
            {
                "id": "checkpoint_action",
                "type": "choice",
                "choices": list(ENTRY_CHOICES["dp-pm-steer"]),
                "instructions": "以当前进度，这一步该继续、拆小、直接执行还是上抛人？",
                "labels": {
                    "narrow": "收窄到剩余预算内能完成的一小块",
                    "split": "拆成多个任务重派",
                    "direct-exec": "PM 自己直接做完",
                    "escalate": "风险高到必须问人",
                },
            },
        ),
        executor=_unwired_executor("dp-pm-steer"),
    ),
    _point(
        dp_id="dp-w-check-task",
        tier="P2",
        description="Worker 本次任务可达性（continue/terminate/investigate，fire-and-forget）",
        role_scope="worker",
        questions=(
            {
                "id": "reachability",
                "type": "choice",
                "choices": list(ENTRY_CHOICES["dp-w-check-task"]),
                "instructions": (
                    "当前任务条件是否足以继续？条件不足时写出真实结论并结束本次执行；"
                    "可在边界内补证时先做有界补证。"
                ),
                "labels": {
                    "continue": "条件充足：继续任务",
                    "terminate": "条件不足：写出完成/未完成/阻断及证据，结束本次执行（不是取消目标或 key）",
                    "investigate": "继续任务并为具体未知做有界补证（须给来源、预算与结束判据）",
                },
            },
        ),
        executor=_unwired_executor("dp-w-check-task"),
    ),
    _point(
        dp_id="dp-QG",
        tier="P1",
        description="正式质量审核（pass/fix/reopen，附可复核依据与未覆盖面）",
        role_scope="pm",
        questions=(
            {
                "id": "qg_verdict",
                "type": "choice",
                "choices": list(ENTRY_CHOICES["dp-QG"]),
                "instructions": (
                    "按正式质量审核要求给出结论，并说清可复核依据、具体缺口或依据问题及未覆盖面。"
                ),
                "labels": {
                    "pass": "满足明确质量/验收要求，必要证据充分且无未解决阻断",
                    "fix": "要求/依据明确，但产物或证据有具体整改缺口",
                    "reopen": "要求、设计或验收依据本身有实质问题，需重新讨论确认",
                },
            },
        ),
    ),
    _point(
        dp_id="dp-gate-approve",
        tier="P0",
        description="具体 gate 审批（approve/steer/need_fix/reject，PM note 与理由分列）",
        role_scope="pm",
        p0_consequences=(
            "自动越过 gate 会让未获授权的 stage/goal/预算/契约变更落地，"
            "且该效果不可在一次决策内撤回"
        ),
        questions=(
            {
                "id": "gate_decision",
                "type": "choice",
                "choices": list(ENTRY_CHOICES["dp-gate-approve"]),
                "instructions": (
                    "按 PM 送审前的 note 与当前条件判断：批准本 gate、交 PM 编排、"
                    "补具体缺口，还是拒绝本次方案。"
                ),
                "labels": {
                    "approve": "满足本 gate 条件，按 note 中的受限动作继续或收尾",
                    "steer": "任务组织/主线/拆分/执行主体需调整，交 PM 发起 dp-pm-steer",
                    "need_fix": "推进方式基本明确但有具体技术/材料缺口，交 PM 发起 dp-auto",
                    "reject": "拒绝本次推进方案；只有 note 另有明确获授权遗留方案才按其收尾",
                },
            },
        ),
    ),
    _point(
        dp_id="dp-sign-key",
        tier="P2",
        description="任意 key 收尾的签收结论（四部材料 + 三数组，按 key 计算）",
        role_scope="pm",
        questions=(
            {
                "id": "q-conclusion",
                "type": "choice",
                "choices": list(ENTRY_CHOICES["dp-sign-key"]),
                "instructions": (
                    "按交付目标、实际完成与验证证据判断：这次交付可以收尾，还是需要继续完成，"
                    "或交用户确认？不以任务数量或完成声明代替证据。"
                ),
                "labels": {
                    "finalize": "可以收尾：按交付目标与验收条件直接签收",
                    "continue": "继续完成：交 PM 推进未完成的缺口",
                    "user-confirm": "交用户确认：由 PM 提出具体待确认项",
                },
            },
        ),
        # The write stays in `mw decide sign`; this executor only echoes the
        # conclusion, so there is no second authority for the same file.
        executor=_echo_conclusion_executor("dp-sign-key"),
    ),
    _point(
        dp_id="dp-auto",
        tier="P2",
        description="PM 现场动态行动选择（候选由 PM 准备，仅从候选集合选择）",
        role_scope="pm",
        kind="dynamic-candidates",
        candidate_source=ENTRY_CANDIDATE_SOURCE["dp-auto"],
        candidate_bounds=ENTRY_CANDIDATE_BOUNDS["dp-auto"],
        questions=(
            {
                "id": "handling",
                "type": "choice",
                "dynamic_choices": "handling_options",
                "instructions": (
                    "从 PM 已准备的候选处理方式中选出最合适的一项；不得提出未准备的方案，"
                    "也不得以失败原因或概率代替依据。"
                ),
            },
        ),
        executor=_unwired_executor("dp-auto"),
    ),
    _point(
        dp_id="dp-route",
        tier="P2",
        description="独立业务入口路由（只选其余七个入口，不携带业务结论）",
        role_scope="pm",
        kind="route-targets",
        candidate_source=ENTRY_CANDIDATE_SOURCE["dp-route"],
        target_entries=ROUTE_TARGETS,
        questions=(
            {
                "id": "entry",
                "type": "choice",
                "choices": list(ROUTE_TARGETS),
                "instructions": (
                    "这个临时问题应进入哪一个决策入口？只选择入口；"
                    "该入口的业务结论与动作仍需按它的合同另发一次决策。"
                ),
                "labels": {
                    "dp-w-type": "派发类型选择",
                    "dp-pm-steer": "PM 任务编排",
                    "dp-w-check-task": "Worker 本次任务可达性",
                    "dp-QG": "正式质量审核",
                    "dp-gate-approve": "具体 gate 审批",
                    "dp-sign-key": "key 交付签收",
                    "dp-auto": "PM 现场动态行动选择",
                },
            },
        ),
        executor=_unwired_executor("dp-route"),
    ),
)

_REGISTRY_BY_ID: dict[str, DecisionPoint] = {}


def _validate_registry(entries: tuple[DecisionPoint, ...]) -> dict[str, DecisionPoint]:
    """Import-time registry validation (fail-loud: a broken registry is a bug)."""
    by_id: dict[str, DecisionPoint] = {}
    for entry in entries:
        if not isinstance(entry, DecisionPoint):
            raise ValueError(f"DP_REGISTRY entries must be DecisionPoint, got {type(entry).__name__}")
        if entry.id in by_id:
            raise ValueError(f"DP_REGISTRY has duplicate id {entry.id!r}")
        by_id[entry.id] = entry
    if len(entries) != EXPECTED_DP_COUNT:
        raise ValueError(f"DP_REGISTRY must hold {EXPECTED_DP_COUNT} decision points, got {len(entries)}")
    if set(by_id) != set(ACTIVE_DP_IDS):
        raise ValueError(
            "DP_REGISTRY ids must be exactly the eight active entries "
            f"{list(ACTIVE_DP_IDS)}; got {sorted(by_id)}"
        )
    return by_id


_REGISTRY_BY_ID = _validate_registry(DP_REGISTRY)


def _validate_retired_registry(
    records: tuple[RetiredDecisionPoint, ...],
) -> dict[str, RetiredDecisionPoint]:
    """Import-time validation of the read-only retired directory."""
    by_id: dict[str, RetiredDecisionPoint] = {}
    for record in records:
        if not isinstance(record, RetiredDecisionPoint):
            raise ValueError(
                "RETIRED_DP_REGISTRY entries must be RetiredDecisionPoint, got "
                f"{type(record).__name__}"
            )
        if record.id in by_id:
            raise ValueError(f"RETIRED_DP_REGISTRY has duplicate id {record.id!r}")
        if record.id in ACTIVE_DP_IDS:
            raise ValueError(f"retired id {record.id!r} is also an active entry")
        if record.tier not in TIERS:
            raise ValueError(f"{record.id}: retired tier must be P0|P1|P2, got {record.tier!r}")
        if record.disposition not in RETIRED_DISPOSITIONS:
            raise ValueError(
                f"{record.id}: disposition must be one of {list(RETIRED_DISPOSITIONS)}, "
                f"got {record.disposition!r}"
            )
        if not str(record.description).strip() or not str(record.note).strip():
            raise ValueError(f"{record.id}: retired description/note must be non-empty")
        if record.disposition == "migrated":
            if record.migrated_to not in ACTIVE_DP_IDS:
                raise ValueError(
                    f"{record.id}: migrated_to {record.migrated_to!r} is not an active entry"
                )
        elif record.migrated_to is not None:
            raise ValueError(f"{record.id}: a retired (not migrated) id must not name a migrated_to")
        by_id[record.id] = record
    return by_id


_RETIRED_BY_ID: dict[str, RetiredDecisionPoint] = _validate_retired_registry(
    RETIRED_DP_REGISTRY
)


def _validate_protocol_contract() -> None:
    """Single-source checks of the eight-entry protocol (fail-loud).

    Runs at import, after the registry and the state tables exist: the target
    set, the retired composition, the per-entry enum provenance and the
    "route/auto own no executor" rule must agree before any entry is callable.
    """
    if len(ACTIVE_DP_IDS) != EXPECTED_DP_COUNT:
        raise ValueError(
            f"ACTIVE_DP_IDS must hold {EXPECTED_DP_COUNT} entries, got {len(ACTIVE_DP_IDS)}"
        )
    if len(set(ACTIVE_DP_IDS)) != len(ACTIVE_DP_IDS):
        raise ValueError("ACTIVE_DP_IDS has a duplicate id")
    if set(ENTRY_CHOICES) != set(ACTIVE_DP_IDS):
        raise ValueError("ENTRY_CHOICES must declare exactly the active entries")
    if set(ENTRY_ROLES) != set(ACTIVE_DP_IDS):
        raise ValueError("ENTRY_ROLES must declare exactly the active entries")
    if set(ENTRY_CANDIDATE_SOURCE) != set(ACTIVE_DP_IDS):
        raise ValueError("ENTRY_CANDIDATE_SOURCE must declare exactly the active entries")
    if len(ROUTE_TARGETS) != 7 or "dp-route" in ROUTE_TARGETS:
        raise ValueError("ROUTE_TARGETS must be the seven other active entries")
    migrated = [record for record in RETIRED_DP_REGISTRY if record.disposition == "migrated"]
    retired = [record for record in RETIRED_DP_REGISTRY if record.disposition == "retired"]
    if len(RETIRED_DP_REGISTRY) != 25 or len(migrated) != 6 or len(retired) != 19:
        raise ValueError(
            "retired composition must be 25 = 6 migrated + 19 retired, got "
            f"{len(RETIRED_DP_REGISTRY)} = {len(migrated)} + {len(retired)}"
        )
    if set(RETIRED_STATE_FIELDS) != set(_RETIRED_BY_ID):
        raise ValueError("RETIRED_STATE_FIELDS must explain exactly the 25 retired ids")
    for entry in DP_REGISTRY:
        if entry.kind not in ENTRY_KINDS:
            raise ValueError(f"{entry.id}: kind must be one of {list(ENTRY_KINDS)}")
        if entry.role_scope != ENTRY_ROLES[entry.id]:
            raise ValueError(f"{entry.id}: role_scope drifted from ENTRY_ROLES")
        if entry.candidate_source != ENTRY_CANDIDATE_SOURCE[entry.id]:
            raise ValueError(f"{entry.id}: candidate_source drifted from ENTRY_CANDIDATE_SOURCE")
        if tuple(entry.target_entries) != (() if entry.kind != "route-targets" else ROUTE_TARGETS):
            raise ValueError(f"{entry.id}: target_entries must be () unless the entry is a route")
        question = entry.questions[0]
        for question_spec in entry.questions:
            for value in question_spec.get("choices") or ():
                if value in _RETIRED_BY_ID:
                    raise ValueError(
                        f"{entry.id}: retired id {value!r} must not be a callable alias"
                    )
        if entry.kind == "fixed":
            if question.get("choices") != list(ENTRY_CHOICES[entry.id]):
                raise ValueError(f"{entry.id}: static choices drifted from ENTRY_CHOICES")
        elif entry.kind == "route-targets":
            if question.get("choices") != list(ROUTE_TARGETS):
                raise ValueError(f"{entry.id}: route choices must be the seven targets")
        else:
            source_field = entry.candidate_source.split(":", 1)[1]
            if question.get("dynamic_choices") != source_field:
                raise ValueError(
                    f"{entry.id}: dynamic question must render from {source_field!r}"
                )
            if entry.candidate_bounds is None:
                raise ValueError(f"{entry.id}: dynamic candidates must declare candidate_bounds")
            bounds = dict(entry.candidate_bounds)
            if bounds.get("id_scheme") != "free" or bounds.get("max") is not None:
                raise ValueError(
                    f"{entry.id}: candidate ids must be free/unbounded (no legacy cN/2..5)"
                )
            if bounds.get("min") != 2:
                raise ValueError(f"{entry.id}: candidate_bounds.min must be 2")
            if source_field not in _declared_state_paths(entry.id):
                raise ValueError(
                    f"{entry.id}: candidate source {source_field!r} is not a declared state path"
                )
        if entry.kind != "fixed":
            unwired = entry.executor is None or getattr(entry.executor, "unwired", False)
            if not unwired:
                raise ValueError(
                    f"{entry.id}: {entry.kind} entries must not own an executor "
                    "(a selection is not a release)"
                )


def is_retired_dp(dp_id: str) -> bool:
    """True when ``dp_id`` is a retired pre-consolidation id (history only)."""
    return isinstance(dp_id, str) and dp_id in _RETIRED_BY_ID


def retired_dp(dp_id: str) -> RetiredDecisionPoint | None:
    """Read-only retired explanation for a history projection (never callable)."""
    if not isinstance(dp_id, str):
        return None
    return _RETIRED_BY_ID.get(dp_id)


def require_active_dp(dp_id: str) -> DecisionPoint:
    """Resolve one active entry; a retired id is refused with its own contract.

    This is the first check of every request entry point: it runs before any
    replay lookup, backend resolution, credential snapshot, archive row or
    executor, so a retired id cannot produce a model call, a business action or
    a new valid decision. The refusal names the disposition only and never maps
    the old id to its successor, because that mapping would be an alias.
    """
    record = _RETIRED_BY_ID.get(dp_id) if isinstance(dp_id, str) else None
    if record is not None:
        raise decision.DecisionInputError(
            f"retired decision point id {dp_id!r} ({record.disposition}): "
            "not callable; old ids are read-only history, not aliases"
        )
    dp_point = _REGISTRY_BY_ID.get(dp_id) if isinstance(dp_id, str) else None
    if dp_point is None:
        raise decision.DecisionInputError(f"unknown decision point id {dp_id!r}")
    return dp_point


def get_decision_point(dp_id: str) -> DecisionPoint:
    """Resolve a registered dp; retired and unknown ids fail loudly.

    Retired ids get their own refusal (spec §5.2 / AC-002 / AC-011) instead of a
    generic "unknown id": the history explanation stays reachable through
    :func:`retired_dp`, while the runtime entry stays closed.
    """
    return require_active_dp(dp_id)


def questions_map(dp_point: DecisionPoint | str) -> dict[str, dict]:
    """Registry question tuple -> the ``{qid: spec}`` mapping ``decision`` expects.

    Accepts the registry id as well (the CLI/acceptance surface quotes an id);
    an unknown id still fails loudly through :func:`get_decision_point`.
    """
    if isinstance(dp_point, str):
        dp_point = get_decision_point(dp_point)
    out: dict[str, dict] = {}
    for question in dp_point.questions:
        spec = dict(question)
        out[str(question["id"])] = spec
    return out


# ---------------------------------------------------------------------------
# Registry export (card D-CFG): the frozen, framework-readable snapshot
# ---------------------------------------------------------------------------

#: Question keys of one exported question, in a frozen order. A key that the
#: registry question does not carry is omitted (``criteria`` only on ``noul``,
#: ``dynamic_choices`` only on a dynamic ``choice``); any key outside this tuple
#: (a future ``score``'s ``min``/``max``) is appended in sorted order.
SNAPSHOT_QUESTION_KEYS = (
    "id",
    "type",
    "instructions",
    "choices",
    "labels",
    "criteria",
    "dynamic_choices",
)

#: ``schema`` of :func:`registry_snapshot` (bump only on a shape change).
#: 2 = per-point wiring (``wired``/``trigger``/``adopted_at``/``wiring_note``)
#: plus ``required_state_fields`` as ``{name, type, description}`` objects; the
#: generated snapshot owns no top-level ``wiring`` section any more.
#: 3 = per-point ``optional_state_fields`` plus the declared field constraints
#: (``enum``/``max_items``/``item_type``/``max_bytes``/``item_max_bytes``/
#: ``signed``/``min_value``) on every exported field, i.e. the typed business
#: contract of design §4.5 is exported, not just the required path names.
SNAPSHOT_SCHEMA = 4

#: Per-point wiring keys, in frozen order (hand-maintained TS call sites, which
#: the Python registry cannot know; the export writer merges them in).
SNAPSHOT_WIRING_KEYS = ("wired", "trigger", "adopted_at", "wiring_note")

#: Default wiring of a dp with no hand-written entry: no claimed call site.
UNWIRED_SNAPSHOT_WIRING: Mapping[str, object] = MappingProxyType(
    {
        "wired": False,
        "trigger": None,
        "adopted_at": None,
        "wiring_note": "unwired",
    }
)


def _executor_kind(executor: object) -> str:
    """Three-way executor view: ``none`` / ``unwired`` / ``wired``.

    ``_unwired_executor``'s placeholder is registered (P2 requires an executor)
    but always raises, so it must not read as ``wired``; a real executor does.
    """
    if executor is None:
        return "none"
    return "unwired" if getattr(executor, "unwired", False) else "wired"


def snapshot_field_dict(path: str) -> dict:
    """One declared state path as an exportable field spec.

    ``{name, type, description}`` in a frozen order, plus every declared
    constraint from :data:`STATE_FIELD_CONSTRAINT_KEYS` (``enum`` as a JSON
    array). A path without a :data:`STATE_FIELD_DESCRIPTIONS` entry is a
    registry bug, so it fails loud instead of exporting a field the reader has
    to guess at. This is the single renderer for the required *and* the optional
    field list, so both artifacts carry one vocabulary.
    """
    spec = STATE_FIELD_DESCRIPTIONS.get(path)
    if spec is None:
        raise ValueError(f"state path {path!r} has no STATE_FIELD_DESCRIPTIONS entry")
    field: dict = {
        "name": path,
        "type": spec["type"],
        "description": spec["description"],
    }
    for key in STATE_FIELD_CONSTRAINT_KEYS:
        if key not in spec:
            continue
        value = spec[key]
        field[key] = list(value) if key == "enum" else value
    return field


def _snapshot_state_fields(paths: Iterable[str]) -> list[dict]:
    """Render declared state paths (required or optional) for the export."""
    return [snapshot_field_dict(path) for path in paths]


def _model_state_fields_export(dp_id: str) -> dict:
    """The per-entry model key table (every active entry declares one).

    An absent key still means "no allowlist declared" and keeps the historical
    "send the declared state unchanged" fallback, but no active entry relies on
    it any more.
    """
    paths = MODEL_STATE_FIELDS.get(dp_id)
    if paths is None:
        return {}
    return {"model_state_fields": list(paths)}


def _snapshot_question(question: Mapping) -> dict:
    """One registry question as a JSON-ready dict with a stable key order."""
    ordered = {
        key: copy.deepcopy(question[key]) for key in SNAPSHOT_QUESTION_KEYS if key in question
    }
    for key in sorted(question):
        if key not in ordered:
            ordered[key] = copy.deepcopy(question[key])
    return ordered


def registry_snapshot() -> dict:
    """The eight active dps as a plain document (pure: no file access).

    This is the generator behind ``packages/multi-workers/decide_registry.json``
    (``mw decide dp export --write``). Keys are inserted in a frozen order and
    every value is JSON-ready, so the same registry always renders the same
    bytes (``registry_snapshot_text``) and drift is a byte comparison.

    Every point is self-describing: ``required_state_fields`` /
    ``optional_state_fields`` read :data:`REQUIRED_STATE_FIELDS` /
    :data:`OPTIONAL_STATE_FIELDS` + :data:`STATE_FIELD_DESCRIPTIONS` at call
    time (both definitions sit in the structured-input section below) and render
    ``[{name, type, description, ...constraints}]``, ``[]`` for a dp without an
    entry; a declared path without a description raises here (an exported field
    with no semantics is the gap this shape closes). ``model_state_fields`` is
    each entry's model key table (every active entry declares one). The four
    wiring keys fall back to :data:`UNWIRED_SNAPSHOT_WIRING`: they name TS call
    sites, which the registry cannot know, so the export writer merges the
    hand-written values in point by point (``mw._dp_export_doc``).

    The retired directory is exported as its own top-level ``retired`` section
    (never mixed into ``points``): history stays explainable read-only while the
    callable set stays exactly eight.
    """
    points: list[dict] = []
    for dp_point in DP_REGISTRY:
        points.append(
            {
                "id": dp_point.id,
                "tier": dp_point.tier,
                "default_enabled": dp_point.default_enabled,
                "default_mode": dp_point.default_mode,
                "description": dp_point.description,
                "kind": dp_point.kind,
                "role_scope": dp_point.role_scope,
                "candidate_source": dp_point.candidate_source,
                "candidate_bounds": (
                    None
                    if dp_point.candidate_bounds is None
                    else dict(dp_point.candidate_bounds)
                ),
                "target_entries": list(dp_point.target_entries),
                "questions_version": dp_point.questions_version,
                "p0_consequences": dp_point.p0_consequences,
                "wired": UNWIRED_SNAPSHOT_WIRING["wired"],
                "trigger": UNWIRED_SNAPSHOT_WIRING["trigger"],
                "adopted_at": UNWIRED_SNAPSHOT_WIRING["adopted_at"],
                "wiring_note": UNWIRED_SNAPSHOT_WIRING["wiring_note"],
                "executor": _executor_kind(dp_point.executor),
                "required_state_fields": _snapshot_state_fields(
                    REQUIRED_STATE_FIELDS.get(dp_point.id, ())
                ),
                "optional_state_fields": _snapshot_state_fields(
                    OPTIONAL_STATE_FIELDS.get(dp_point.id, ())
                ),
                **_model_state_fields_export(dp_point.id),
                "questions": [_snapshot_question(question) for question in dp_point.questions],
            }
        )
    return {
        "schema": SNAPSHOT_SCHEMA,
        "generated_from": "decision_points.DP_REGISTRY",
        "question_types": sorted(decision.QUESTION_TYPES),
        "preparation": {
            "keys": list(PREPARATION_KEYS),
            "basis_item_keys": list(BASIS_ITEM_KEYS),
            "basis_source": BASIS_SOURCE,
            "independent_of": "material",
        },
        "points": points,
        "retired": [
            {
                "id": record.id,
                "tier": record.tier,
                "description": record.description,
                "disposition": record.disposition,
                "migrated_to": record.migrated_to,
                "note": record.note,
            }
            for record in RETIRED_DP_REGISTRY
        ],
    }


def registry_snapshot_text(snapshot: Mapping | None = None) -> str:
    """Canonical bytes of a snapshot: ``ensure_ascii=False``, 2 spaces, one ``\\n``.

    The single serializer for both the writer (``mw decide dp export --write``)
    and the drift guard, so "regenerate and compare bytes" cannot drift on
    formatting alone. ``snapshot=None`` renders :func:`registry_snapshot`.
    """
    doc = registry_snapshot() if snapshot is None else snapshot
    return json.dumps(doc, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------------------
# Dynamic choices (FIX-I): a ``choice`` whose enum comes from state
# ---------------------------------------------------------------------------

#: Max candidates rendered into one dynamic question (FIX-I frozen contract).
DYNAMIC_CHOICES_MAX = 5
#: Max rendered label length; the ``c1..cN`` ids are the answer surface.
DYNAMIC_CHOICE_LABEL_MAX = 80

_DYNAMIC_CHOICE_ID_RE = re.compile(r"^c[1-9]$")


def dynamic_choices_value_error(candidates: object) -> str:
    """Validate one ``dynamic_choices`` state value; ``""`` means renderable.

    Frozen shape: ``[{"id": "c1", "label": "..."}, ...]`` with 1..5 items,
    ids contiguous from ``c1``, and a non-empty single-line label of at most
    :data:`DYNAMIC_CHOICE_LABEL_MAX` characters. Never raises: the caller turns
    a non-empty reason into ``input-incomplete`` (zero HTTP).
    """
    if not isinstance(candidates, list):
        return "expected a list of {id,label} objects"
    if not candidates:
        return "expected at least 1 candidate"
    if len(candidates) > DYNAMIC_CHOICES_MAX:
        return f"expected at most {DYNAMIC_CHOICES_MAX} candidates, got {len(candidates)}"
    for index, item in enumerate(candidates, start=1):
        if not isinstance(item, Mapping):
            return f"candidate #{index} is not an object"
        candidate_id = item.get("id")
        if not isinstance(candidate_id, str) or not _DYNAMIC_CHOICE_ID_RE.match(candidate_id):
            return f"candidate #{index} id {candidate_id!r} is not cN (c1..c9)"
        if candidate_id != f"c{index}":
            return f"candidate #{index} id {candidate_id!r} is not contiguous (expected c{index})"
        label = item.get("label")
        if not isinstance(label, str) or not label.strip():
            return f"candidate {candidate_id} label must be a non-empty string"
        if "\n" in label or "\r" in label:
            return f"candidate {candidate_id} label must not contain a newline"
        if len(label) > DYNAMIC_CHOICE_LABEL_MAX:
            return (
                f"candidate {candidate_id} label is {len(label)} chars "
                f"(> {DYNAMIC_CHOICE_LABEL_MAX})"
            )
    return ""


def dynamic_choice_labels(
    questions: Mapping, state: object, *, dp_id: str | None = None
) -> dict[str, dict[str, str]] | None:
    """``{qid: {candidate_id: label}}`` for every dynamic question, or ``None``.

    ``None`` means at least one dynamic question cannot be rendered (missing
    state key or an illegal candidate list), so the caller must refuse the
    decision as ``input-incomplete`` instead of sending a partial enum.
    """
    rendered: dict[str, dict[str, str]] = {}
    for qid, spec in questions.items():
        key = spec.get("dynamic_choices") if isinstance(spec, Mapping) else None
        if not isinstance(key, str):
            continue
        if not isinstance(state, Mapping) or key not in state:
            return None
        candidates = state[key]
        if not isinstance(candidates, list):
            return None
        if dp_id is not None and _REGISTRY_BY_ID.get(dp_id) is not None and (
            _REGISTRY_BY_ID[dp_id].kind == "dynamic-candidates"
        ):
            # The active dynamic entry (dp-auto) has no legacy cN/2..5 bound; its
            # one candidate contract is pm_candidate_issues.
            if pm_candidate_issues(candidates):
                return None
        elif dynamic_choices_value_error(candidates):
            return None
        rendered[str(qid)] = {
            str(item["id"]): str(item["label"]) for item in candidates
        }
    return rendered


def resolve_dynamic_choices(
    questions: Mapping, state: object, *, dp_id: str | None = None
) -> dict[str, tuple[str, ...]] | None:
    """Legal answer ids per dynamic question; ``None`` when any cannot render.

    The ids are the *rendered* enum the model may answer with, not the registry
    question set: ``questions_version`` still hashes the registry questions only
    (it names the question-set shape, the candidates are input data).
    """
    labels = dynamic_choice_labels(questions, state, dp_id=dp_id)
    if labels is None:
        return None
    return {qid: tuple(candidate_ids) for qid, candidate_ids in labels.items()}


# ---------------------------------------------------------------------------
# Observation-only question overrides (T10): one validated, normalised shape
# ---------------------------------------------------------------------------

#: The only keys an override of one registered question may carry. Everything
#: except ``instructions`` is validated against the registry (or, for a dynamic
#: choice, against ``state``) and is never taken from the override: the registry
#: and the state stay the single authority for types, choices and criteria.
QUESTION_OVERRIDE_FIELDS: tuple[str, ...] = (
    "id",
    "type",
    "instructions",
    "choices",
    "labels",
    "criteria",
    "dynamic_choices",
)
#: A test-edited instruction is model-facing prose, not material: bound it so a
#: question override can never be used to smuggle an unbounded request body.
QUESTION_INSTRUCTIONS_MAX_BYTES = 2048
#: ``score`` criteria levels, mirroring the wire builder's documented bounds
#: (``decision_backends.MIN_SCORE_LEVELS`` / ``MAX_SCORE_LEVELS``). Only the
#: shape is validated here; the registry/builder stays the generation authority.
_SCORE_CRITERIA_MIN_LEVELS = 2
_SCORE_CRITERIA_MAX_LEVELS = 10


@dataclass(frozen=True)
class QuestionOverride:
    """One observation-only question override: the normalised set or the issues.

    ``questions`` is ``None`` when ``issues`` is non-empty. The normalised set is
    the registry questions with only ``instructions`` replaced, so the request
    builder keeps generating types/choices/criteria from the registry and, for a
    dynamic choice, from ``state`` (dp3: ``handling_options`` is the one
    candidate source).
    """

    questions: dict[str, dict] | None
    issues: tuple[tuple[str, str], ...] = ()


def _generated_choice_criteria(spec: Mapping) -> dict:
    """The criteria the wire builder generates for a registered static choice.

    Mirrors ``decision_backends._choice_criteria`` for a registry spec (declared
    ``criteria`` first, then ``labels`` over ``choices``). It is used only to
    validate/normalise an override; the builder remains the send authority.
    """
    declared = spec.get("criteria")
    if isinstance(declared, Mapping) and declared:
        return dict(declared)
    labels = spec.get("labels") if isinstance(spec.get("labels"), Mapping) else {}
    options = [str(choice) for choice in spec.get("choices", ())]
    if not options and labels:
        options = [str(option) for option in labels]
    return {
        option: labels.get(option) if isinstance(labels.get(option), str) else None
        for option in options
    }


def _criteria_override_issues(
    qid: str, base: Mapping, criteria: object, rendered: Mapping[str, str] | None
) -> list[tuple[str, str]]:
    """Legal criteria shape plus the one-authority conflict check."""
    qtype = base.get("type")
    if qtype == decision.QUESTION_CHOICE:
        expected = dict(rendered) if rendered is not None else _generated_choice_criteria(base)
        if not isinstance(criteria, Mapping):
            return [(f"{qid}.criteria", "must be a mapping of option -> label")]
        if set(criteria) != set(expected):
            return [
                (
                    f"{qid}.criteria",
                    "must name exactly the legal choice ids of this question",
                )
            ]
        issues: list[tuple[str, str]] = []
        for option, label in criteria.items():
            if rendered is None and (
                not isinstance(label, str) or not label.strip() or "\x00" in label
                or len(label.encode("utf-8")) > QUESTION_INSTRUCTIONS_MAX_BYTES
            ):
                issues.append((f"{qid}.criteria.{option}", "must be a non-empty, bounded description without NUL"))
            elif rendered is not None and label != expected.get(option):
                issues.append(
                    (
                        f"{qid}.criteria.{option}",
                        "conflicts with the state/registry rendered label (one candidate source)",
                    )
                )
        return issues
    if qtype == decision.QUESTION_SCORE:
        if not isinstance(criteria, list) or not all(
            isinstance(item, str) and item.strip() for item in criteria
        ):
            return [(f"{qid}.criteria", "must be a list of non-empty level labels")]
        if not _SCORE_CRITERIA_MIN_LEVELS <= len(criteria) <= _SCORE_CRITERIA_MAX_LEVELS:
            return [
                (
                    f"{qid}.criteria",
                    f"must have {_SCORE_CRITERIA_MIN_LEVELS}..{_SCORE_CRITERIA_MAX_LEVELS} levels",
                )
            ]
        declared = base.get("criteria")
        if isinstance(declared, list) and list(criteria) != list(declared):
            return [(f"{qid}.criteria", "conflicts with the registered score levels")]
        return []
    if qtype == decision.QUESTION_NOUL:
        declared = base.get("criteria")
        if not isinstance(declared, Mapping):
            return [
                (
                    f"{qid}.criteria",
                    "the registered question declares no criteria; a per-send override is not supported",
                )
            ]
        if criteria != dict(declared):
            return [(f"{qid}.criteria", "conflicts with the registered criteria")]
        return []
    return [(f"{qid}.criteria", f"is not a legal field for type {qtype!r}")]


def question_override_issues(
    dp_point: DecisionPoint | str,
    questions: object,
    state: object = None,
) -> tuple[tuple[str, str], ...]:
    """Strict validation of one observation-only question override.

    Enforced, in this order: the DP's own question mapping (exactly its ids, no
    more, no less); legal types (a different type conflicts instead of being
    coerced); non-blank, bounded ``instructions``; legal ``criteria`` whose keys
    are the question's legal choice set, with editable static descriptions or
    labels matching ``state``'s rendered candidates (dynamic); and no unknown
    key (so an execution/authorization field cannot ride along). Field paths and
    registry-owned text only are reported - never a submitted value.
    """
    if isinstance(dp_point, str):
        dp_point = get_decision_point(dp_point)
    registry = questions_map(dp_point)
    if not isinstance(questions, Mapping) or not questions:
        return (("questions", "must be a non-empty mapping of this dp's question ids"),)
    issues: list[tuple[str, str]] = []
    for qid in sorted(set(questions) - set(registry), key=str):
        issues.append((str(qid), "is not a registered question id of this decision point"))
    for qid in sorted(set(registry) - set(questions), key=str):
        issues.append((str(qid), "is missing: an override carries every registered question id"))
    dynamic = dynamic_choice_labels(registry, state)
    for qid, base in registry.items():
        if qid not in questions:
            continue
        spec = questions[qid]
        if not isinstance(spec, Mapping):
            issues.append((qid, "must be a mapping"))
            continue
        for name in sorted(set(spec) - set(QUESTION_OVERRIDE_FIELDS)):
            issues.append((f"{qid}.{name}", "is not an overridable question field"))
        if "id" in spec and spec.get("id") != qid:
            issues.append((f"{qid}.id", "must equal the question id it overrides"))
        qtype = base.get("type")
        if "type" in spec and spec.get("type") != qtype:
            issues.append((f"{qid}.type", f"conflicts with the registered type {qtype!r}"))
        if "instructions" in spec:
            instructions = spec.get("instructions")
            if not isinstance(instructions, str) or not instructions.strip():
                issues.append((f"{qid}.instructions", "must be a non-empty string"))
            elif "\x00" in instructions:
                issues.append((f"{qid}.instructions", "must not contain a NUL character"))
            elif len(instructions.encode("utf-8")) > QUESTION_INSTRUCTIONS_MAX_BYTES:
                issues.append(
                    (
                        f"{qid}.instructions",
                        f"is longer than {QUESTION_INSTRUCTIONS_MAX_BYTES} UTF-8 bytes",
                    )
                )
        for name in ("choices", "labels", "dynamic_choices"):
            if name in spec and spec.get(name) != base.get(name):
                issues.append(
                    (f"{qid}.{name}", "conflicts with the registered question definition")
                )
        if "criteria" in spec:
            rendered = (dynamic or {}).get(qid)
            if base.get("dynamic_choices") is not None and rendered is None:
                issues.append(
                    (
                        f"{qid}.dynamic_choices",
                        "the dynamic candidates cannot be rendered from the submitted state",
                    )
                )
            else:
                issues.extend(
                    _criteria_override_issues(qid, base, spec.get("criteria"), rendered)
                )
    return tuple(issues)


def apply_question_override(
    dp_point: DecisionPoint | str, questions: Mapping
) -> dict[str, dict]:
    """Registry identity/options plus validated observation text.

    Static criteria descriptions and instructions may differ for this send.
    Dynamic criteria are always regenerated from state, never the override.
    Preview and send consume this same normalised question set.
    """
    if isinstance(dp_point, str):
        dp_point = get_decision_point(dp_point)
    normalised: dict[str, dict] = {}
    for qid, base in questions_map(dp_point).items():
        spec = dict(base)
        override = questions.get(qid)
        instructions = override.get("instructions") if isinstance(override, Mapping) else None
        if isinstance(instructions, str) and instructions.strip():
            spec["instructions"] = instructions
        if isinstance(override, Mapping) and "criteria" in override and base.get("dynamic_choices") is None:
            criteria = override["criteria"]
            spec["criteria"] = dict(criteria) if isinstance(criteria, Mapping) else list(criteria)
        normalised[qid] = spec
    return normalised


def resolve_question_override(
    dp_point: DecisionPoint | str, questions: object, state: object = None
) -> QuestionOverride:
    """Validate and normalise one override; ``questions=None`` when refused."""
    issues = question_override_issues(dp_point, questions, state)
    if issues:
        return QuestionOverride(questions=None, issues=issues)
    return QuestionOverride(questions=apply_question_override(dp_point, questions))


#: The identity/association facts that are not decision material. Used only to
#: describe what a stored input body says about the business state. The values
#: mirror ``AUDIT_STATE_PATHS`` (defined later in this module) plus the identity
#: keys every builder writes; the literal keeps this block free of a forward
#: reference at import time.
NON_MATERIAL_STATE_KEYS: tuple[str, ...] = (
    "schema_version",
    "decision_point",
    "questions_version",
    "key",
    "task_key",
    "trigger_id",
)


def send_state(dp_id: str, state: Mapping) -> tuple[dict, tuple[str, ...], int]:
    """The exact model projection + canonical budget fit :func:`decide_for` sends.

    One authority for the send material: the observation preview calls this same
    function, so a preview can never describe a state the send path would not
    produce.
    """
    return _fit_state(model_state_for(dp_id, state))


# ---------------------------------------------------------------------------
# Structured input: required fields, optional fields, truncation (design D-019)
# ---------------------------------------------------------------------------

#: JSON-native kinds a declared state path may use (design §4.5).
STATE_FIELD_TYPES: tuple[str, ...] = (
    "string",
    "integer",
    "number",
    "boolean",
    "array",
    "object",
)
#: A new plain string value may carry at most this many UTF-8 bytes.
STATE_STRING_MAX_BYTES = 512
#: A new plain string *array element* may carry at most this many UTF-8 bytes.
STATE_ARRAY_ITEM_MAX_BYTES = 128
#: ``max_items`` of a new plain array (design §4.5 unified boundary).
STATE_ARRAY_MAX_ITEMS = 32
#: ``max_items`` of the wide arrays (dp17 covers a key's full AC set).
STATE_ARRAY_MAX_ITEMS_WIDE = 128
#: Optional declaration keys of one field spec, in export order. ``type`` and
#: ``description`` are mandatory; everything here is a declared constraint:
#:
#: - ``enum``: closed value set (strings only);
#: - ``max_items`` / ``item_type`` / ``item_max_bytes``: array shape;
#: - ``max_bytes``: string byte cap (also used for array elements);
#: - ``signed``: negative integers are legal (dp23 ``snapshot.delta_bytes``);
#: - ``min_value``: integer floor (``0`` for the new counts/sizes);
#: - ``empty_is_value``: an empty array/object of this field is the producer's
#:   real "none" value, not an unreplaced placeholder (dp25 ``p0_open``: ``[]``
#:   means "no P0 open right now"). Only the decision book's placeholder scan
#:   consumes it (and keeps refusing placeholder text inside the array); the
#:   typed contract, the closed key set, the missing/null refusal and the
#:   evidence requirement are unchanged (T05h).
STATE_FIELD_CONSTRAINT_KEYS: tuple[str, ...] = (
    "enum",
    "max_items",
    "item_type",
    "max_bytes",
    "item_max_bytes",
    "signed",
    "min_value",
    "empty_is_value",
)

#: The structural identity keys `_state_builder` writes for every dp; a dp's
#: business contract is declared *in addition* to these (design §4.5 "每 DP plus
#: 结构身份").
STATE_IDENTITY_PATHS: tuple[str, ...] = (
    "schema_version",
    "decision_point",
    "questions_version",
)

#: The autopilot human-gate vocabulary (``autopilot.gates.GATE_KINDS``). Kept as
#: a literal here (no import-time dependency on the autopilot package) and
#: locked against the authority by ``test_decision_dashboard_contracts``.
GATE_KIND_ENUM: tuple[str, ...] = (
    "stage-confirm",
    "stage-close",
    "stalled",
    "budget-exhausted",
    "goal-change",
    "xkey-authorize",
)

#: Required state paths per dp (missing / None / blank string => input-incomplete).
#: dp1/dp2/dp3 sets come from the structured-input contract (D6 Q5.1); dp4..dp24
#: carry the typed business contract of design §4.5 (each dp: the three
#: structural identity keys the builder always writes, plus its business facts);
#: dp25 keeps exactly the facts `decide_signoff.collect()` folds. The generic
#: builder already guarantees ``schema_version``/``decision_point``/
#: ``questions_version``.
#: Required state paths per *active* entry (missing / None / blank string =>
#: input-incomplete). The three structural identity keys are written by the
#: builder, so they are not part of the business material table.
REQUIRED_STATE_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "dp-w-type": (
            "task_goal",
            "task_requirements",
            "task_deliverables",
        ),
        "dp-pm-steer": (
            "task_goal",
            "task_requirements",
            "task_deliverables",
            "pm_decision_background",
        ),
        # AC-046: the Worker judges reachability from its own task facts; the
        # bounded-evidence plan (investigation.*) is conditional on the
        # investigate choice, so it is declared optional and enforced by
        # entry_choice_issues.
        "dp-w-check-task": (
            "task_goal",
            "reachability_facts",
            "completed",
            "remaining",
            "blockers",
            "constraints",
        ),
        # AC-005/AC-053: the formal review carries its requirements, the evidence
        # it actually examined, its findings and the uncovered scope.
        "dp-QG": (
            "review_requirements",
            "review_evidence",
            "review_findings",
            "uncovered_scope",
        ),
        # AC-007: the PM note is a separate business input (subject, planned
        # action, goal/evidence/budget/authority basis). It stays independent of
        # the model-selected basis in preparation.basis_catalog.
        "dp-gate-approve": (
            "gate_background",
            "current_state",
            "condition_evidence",
            "pm_note.subject",
            "pm_note.planned_action",
            "pm_note.basis.goal",
            "pm_note.basis.evidence",
            "pm_note.basis.budget",
            "pm_note.basis.authority",
        ),
        # dp-sign-key keeps exactly the four approved parts (no diff, no count,
        # no engine fact). ``[]`` is a real "none"; null/missing is refused.
        "dp-sign-key": (
            "delivery_goal",
            "actual_completion",
            "verification_evidence.verified",
            "verification_evidence.unverified",
            "unfinished_impact",
        ),
        # AC-042: the PM prepares the live problem, the real background and the
        # candidate actions; the entry only picks one of them.
        "dp-auto": (
            "question",
            "background.task_goal",
            "background.current_state",
            "background.tried",
            "background.unknowns",
            "background.constraints",
            "handling_options",
        ),
        # AC-040: a route request names the real actor, the object and the
        # concrete pending question; the answer only selects an entry.
        "dp-route": (
            "decision_actor",
            "decision_object",
            "question",
        ),
    }
)

#: Read-only material explanation of the 25 retired ids. This table is never
#: consulted by a runtime gate (the ids are refused first); it exists so the
#: migration can be audited entry by entry without reviving a callable contract.
RETIRED_STATE_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "dp1-dispatch-type": (
            "task_goal",
            "task_requirements",
            "task_deliverables",
        ),
        "dp2-checkpoint-split": (
            "task_goal",
            "task_requirements",
            "task_deliverables",
            "pm_decision_background",
        ),
        "dp3-worker-clarify": (
            "question",
            "background.task_goal",
            "background.current_state",
            "background.decision_reason",
            "background.constraints_impact",
            "handling_options",
        ),
        "dp4-failure-handling": (
            *STATE_IDENTITY_PATHS,
            "failure.kind",
            "failure.attempt",
            "failure.limit",
            "failure.artifact_present",
        ),
        "dp5-test-triage": (
            *STATE_IDENTITY_PATHS,
            "test.failed_cases",
            "test.baseline_cases",
            "test.changed_paths",
            "test.repro_consistent",
        ),
        "dp6-qg-verdict": (
            *STATE_IDENTITY_PATHS,
            "qg.checks_total",
            "qg.checks_failed",
            "qg.blocking",
            "qg.scope",
        ),
        "dp7-gate-failure": (
            *STATE_IDENTITY_PATHS,
            "gate.name",
            "gate.missing_items",
            "gate.verdict_age_hours",
            "gate.has_config_error",
        ),
        "dp8-scope-change": (
            *STATE_IDENTITY_PATHS,
            "scope.requested_paths",
            "scope.write_scope",
            "scope.cross_key_conflicts",
            "scope.requirement_delta",
        ),
        "dp9-model-select": (
            *STATE_IDENTITY_PATHS,
            "model.requested",
            "model.available",
            "model.transport_status",
        ),
        "dp10-dependency": (
            *STATE_IDENTITY_PATHS,
            "dependency.name",
            "dependency.current",
            "dependency.target",
            "dependency.breaking",
            "dependency.reviewed",
        ),
        "dp11-credential": (
            *STATE_IDENTITY_PATHS,
            "credential.provider",
            "credential.kind",
            "credential.scope",
            "credential.exposed_to",
        ),
        "dp12-destructive": (
            *STATE_IDENTITY_PATHS,
            "action.command",
            "action.targets",
            "action.reversible",
            "action.backup_available",
        ),
        "dp13-commit-release": (
            *STATE_IDENTITY_PATHS,
            "release.version_current",
            "release.version_next",
            "release.staged_paths",
            "release.changelog_ready",
            "release.ci_green",
        ),
        "dp14-rule-conflict": (
            *STATE_IDENTITY_PATHS,
            "conflict.user_instruction",
            "conflict.rule_ref",
            "conflict.rule_strength",
            "conflict.irreversible",
        ),
        "dp15-autopilot-gate": (
            *STATE_IDENTITY_PATHS,
            "gate.kind",
            "gate.pending_items",
            "gate.age_minutes",
            "gate.evidence_refs",
        ),
        "dp16-goal": (
            *STATE_IDENTITY_PATHS,
            "goal.current_digest",
            "goal.proposed_delta",
            "goal.alignment",
        ),
        "dp17-spec-lock": (
            *STATE_IDENTITY_PATHS,
            "spec.ac_ids",
            "spec.ac_changed",
            "spec.open_questions",
        ),
        "dp18-claim": (
            *STATE_IDENTITY_PATHS,
            "claim.key",
            "claim.owner",
            "claim.heartbeat_age_min",
            "claim.owner_active",
        ),
        "dp19-foreign-write": (
            *STATE_IDENTITY_PATHS,
            "write.target_path",
            "write.cross_key_owner",
            "write.write_scope",
            "write.foreign_paths",
            "write.allow_foreign_write",
        ),
        "dp20-stage-close": (
            *STATE_IDENTITY_PATHS,
            "stage.id",
            "stage.tasks_done",
            "stage.tasks_total",
            "stage.open_blockers",
            "stage.evidence_refs",
        ),
        "dp21-refine": (
            *STATE_IDENTITY_PATHS,
            "refine.clause",
            "refine.impact_paths",
            "refine.reversible",
        ),
        "dp22-debug-plan": (
            *STATE_IDENTITY_PATHS,
            "debug.signal",
            "debug.last_green_ref",
            "debug.repro_available",
            "debug.change_scope",
        ),
        "dp23-snapshot": (
            *STATE_IDENTITY_PATHS,
            "snapshot.size_bytes",
            "snapshot.delta_bytes",
            "snapshot.sections_changed",
        ),
        "dp24-pi-trust": (
            *STATE_IDENTITY_PATHS,
            "project.path",
            "project.trust_state",
            "project.origin",
            "project.pending_changes",
        ),
        "dp25-signoff-conclusion": (
            "delivery_goal",
            "actual_completion",
            "verification_evidence.verified",
            "verification_evidence.unverified",
            "unfinished_impact",
        ),
    }
)

#: Meaning of every required state path: ``{type, description}`` (the
#: self-describing half of :data:`REQUIRED_STATE_FIELDS`, joined by path).
#: ``type`` is the JSON-native kind (``object|string|integer|number|boolean|
#: array``) a producer has to supply; a required path without an entry here
#: makes :func:`registry_snapshot` fail loud (never a bare name with no meaning).
STATE_FIELD_DESCRIPTIONS: Mapping[str, dict] = MappingProxyType(
    {
        "schema_version": {
            "type": "integer",
            "description": "State schema version (currently 2).",
        },
        "decision_point": {
            "type": "string",
            "description": "Decision point id this state was built for.",
        },
        "key": {
            "type": "string",
            "description": "AgenticTask key, e.g. mw-decision-substitution.",
        },
        "phase": {
            "type": "string",
            "description": "Current AgenticTask phase, e.g. EXECUTE.",
        },
        "task_type": {
            "type": "string",
            "description": "Task type of the work being decided: coding|review|research|rag-research|vision|verifier|reviewer|repair|phase-writer|roadmap-writer.",
        },
        "requested_type": {
            "type": "string",
            "description": "Task type the dispatch entry requested: the same vocabulary as task_type.",
        },
        "risk": {
            "type": "string",
            "description": "Risk tier of the task: low|mid|high.",
        },
        "risk_source": {
            "type": "string",
            "description": "Who assigned the risk: machine (auto-derived) | pm-label (labelled by the PM).",
        },
        "authority_tier": {
            "type": "string",
            "description": "Decision authority tier: P0|P1|P2.",
        },
        "task_summary": {
            "type": "string",
            "description": "One-line summary of the task being decided.",
        },
        "questions_version": {
            "type": "string",
            "description": "Registry question-set version, e.g. q-fcbd3847.",
        },
        # The approved four-DP business material (design §2 / plan "最小固定跨卡接口").
        # No arbitrary per-field byte/item caps here: necessary material is either
        # sent complete or refused against the existing transport budget.
        "task_goal": {
            "type": "string",
            "description": "Task goal exactly as handed to the task (原文), no summary.",
        },
        "task_requirements": {
            "type": "string",
            "description": "Task requirements exactly as handed to the task (原文).",
        },
        "task_deliverables": {
            "type": "string",
            "description": "Task deliverables exactly as handed to the task (原文).",
        },
        "pm_decision_background": {
            "type": "string",
            "description": "Why the PM needs a checkpoint decision now, plus the constraints that shape it.",
        },
        "worker_execution": {
            "type": "string",
            "description": "Optional real worker execution (done/remaining/blocked/attempted and time budget); omit when there is no worker, never invent it.",
        },
        "question": {
            "type": "string",
            "description": "The pending question verbatim (what exactly needs a decision), written before any answer.",
        },
        "background.task_goal": {
            "type": "string",
            "description": "Task goal the question is asked against.",
        },
        "background.current_state": {
            "type": "string",
            "description": "What is actually known so far; unknowns are marked unknown, never invented.",
        },
        "background.decision_reason": {
            "type": "string",
            "description": "Why this question needs a decision now.",
        },
        "background.constraints_impact": {
            "type": "string",
            "description": "Constraints and the impact of each candidate handling.",
        },
        "handling_options": {
            "type": "array",
            "description": (
                "PM-prepared, problem-specific action candidates "
                "[{id,label,description,consequence,risk,conditions}]; ids only need to be "
                "unique in this request (no legacy cN/2..5 bound)."
            ),
            "item_type": "object",
            "max_items": STATE_ARRAY_MAX_ITEMS,
        },
        "delivery_goal": {
            "type": "string",
            "description": "Delivery goal including the user's acceptance conditions.",
        },
        "actual_completion": {
            "type": "string",
            "description": "What was actually completed against the delivery goal.",
        },
        "verification_evidence.verified": {
            "type": "array",
            "description": "Verification evidence that was actually verified; [] when there is none.",
            "item_type": "string",
            "empty_is_value": True,
        },
        "verification_evidence.unverified": {
            "type": "array",
            "description": "Evidence that is not verified (or was not run); [] means a verified none, never a missing fact.",
            "item_type": "string",
            "empty_is_value": True,
        },
        "unfinished_impact": {
            "type": "array",
            "description": "Unfinished items and their impact; [] means nothing is unfinished, never a missing fact.",
            "item_type": "string",
            "empty_is_value": True,
        },
        "scope.write_scope": {
            "type": "array",
            "description": "Paths the task may write, repo-relative (string array).",
        },
        "scope.file_extensions": {
            "type": "array",
            "description": "File extensions the task touches, e.g. [\".py\"] (string array).",
        },
        "progress.elapsed_minutes": {
            "type": "integer",
            "description": "Minutes spent on the task so far (wall clock or budget clock).",
        },
        "progress.budget_minutes": {
            "type": "integer",
            "description": "Minute budget assigned to the task.",
        },
        "progress.phases_done": {
            "type": "integer",
            "description": "AgenticTask phases completed so far.",
        },
        "progress.phases_total": {
            "type": "integer",
            "description": "AgenticTask phases planned for the task.",
        },
        "progress.artifact_present": {
            "type": "boolean",
            "description": "Whether the checkpoint artifact exists on disk.",
        },
        "ambiguity.kind": {
            "type": "string",
            "description": "Kind of the ambiguity: scope|fact|intent.",
        },
        "ambiguity.question": {
            "type": "string",
            "description": "The clarifying question the worker could not answer.",
        },
        "local_candidates": {
            "type": "array",
            "description": "Candidate answers found locally: [{id, label, path?, line?}], max 5.",
        },
        "rows_total": {
            "type": "integer",
            "description": "Decide rows counted for this key in the archive (sign-off rows of dp25 itself excluded).",
        },
        "rows_available": {
            "type": "integer",
            "description": "Of rows_total, how many have available=true (a real answer came back).",
        },
        "chain_ok": {
            "type": "boolean",
            "description": "Whether the archive hash chain is intact (seq contiguous from 1, prev_sha closes).",
        },
        "p0_open": {
            "type": "array",
            "description": "Enabled P0 dp ids right now (string array; [] when none or the table is absent).",
            # The producer writes [] for "no P0 open": that empty array is the
            # real value of this field, not an unreplaced scaffold placeholder
            # (T05h). Field-level and book-only; no other field declares it.
            "empty_is_value": True,
            # The same unified array boundary every new array declares (design
            # §4.5, T05k N5): sorted registry P0 dp ids, 10 today, longest 19 B,
            # so 32 items / string / 128 B is headroom, not a producer limit.
            # No enum: the element space is dp ids, not a closed set invented
            # here.
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        # dp25 optional L1 facts (T05c): the rest of the *real*
        # ``decide_signoff.signoff_state`` escalation vocabulary. Declared here
        # so the book, the seam and the export share one contract instead of a
        # seam-only allowance.
        "rows_escalated": {
            "type": "integer",
            "description": "Of rows_total, how many carry an escalated_reason (signoff collect fact).",
            "min_value": 0,
        },
        "escalated_reasons": {
            "type": "array",
            "description": "Distinct escalated_reason values seen in the counted rows (sorted; [] when none).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "engine_violations": {
            "type": "array",
            "description": "transport/model/confidence_source triples that are not the real engine (sorted; [] when all real).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        # ------------------------------------------------------------------
        # dp4..dp24 business contract (design §4.5). Every new string declares
        # its byte cap, every new array its ``max_items``/element cap, every
        # enum its closed value set, every new count its ``>= 0`` floor. The
        # description names the fact and where it comes from; it never invites
        # a caller to invent a value (a missing fact must stay missing).
        # ------------------------------------------------------------------
        "failure.kind": {
            "type": "string",
            "description": "Failure class observed on the attempt: transient|deterministic|infra|unknown (from the failing step's own error report).",
            "enum": ("transient", "deterministic", "infra", "unknown"),
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "failure.attempt": {
            "type": "integer",
            "description": "How many attempts have already been made for this failure (0-based count).",
            "min_value": 0,
        },
        "failure.limit": {
            "type": "integer",
            "description": "Attempt budget the task was given; it must not be exceeded.",
            "min_value": 0,
        },
        "failure.artifact_present": {
            "type": "boolean",
            "description": "Whether the failed attempt left a usable artifact on disk (fs-stated, not assumed).",
        },
        "test.failed_cases": {
            "type": "array",
            "description": "Failing test ids exactly as the runner reported them.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "test.baseline_cases": {
            "type": "array",
            "description": "Known-failing (baseline) test ids for this project, from the recorded baseline.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "test.changed_paths": {
            "type": "array",
            "description": "Repo-relative paths the change touched (diff scope), not the whole write face.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "test.repro_consistent": {
            "type": "boolean",
            "description": "Whether repeated runs reproduced the same failures (recorded rerun result).",
        },
        "qg.checks_total": {
            "type": "integer",
            "description": "Number of quality-gate checks the verdict was computed over.",
            "min_value": 0,
        },
        "qg.checks_failed": {
            "type": "array",
            "description": "Ids of the quality-gate checks that failed (subset of the total).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "qg.blocking": {
            "type": "array",
            "description": "Failure ids the quality gate reported as blocking (cannot be waived).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "qg.scope": {
            "type": "string",
            "description": "Which surface the verdict covers: impl (code) or spec (locked requirements).",
            "enum": ("impl", "spec"),
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "gate.name": {
            "type": "string",
            "description": "Gate that failed, by its recorded gate id or name.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "gate.missing_items": {
            "type": "array",
            "description": "Checklist items the gate still reports as missing.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "gate.verdict_age_hours": {
            "type": "integer",
            "description": "Age in hours of the verdict that failed the freshness gate.",
            "min_value": 0,
        },
        "gate.has_config_error": {
            "type": "boolean",
            "description": "Whether the gate failure is a configuration error rather than missing work.",
        },
        "scope.requested_paths": {
            "type": "array",
            "description": "Paths the new requirement asks to write (repo-relative), as requested.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "scope.cross_key_conflicts": {
            "type": "array",
            "description": "Paths or keys another key already claims (conflict facts from the claim index).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "scope.requirement_delta": {
            "type": "string",
            "description": "One-line description of what the requirement adds or removes.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "model.requested": {
            "type": "string",
            "description": "Model id the task asked for (config or card), before fallback.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "model.available": {
            "type": "array",
            "description": "Model ids the transport reports as reachable right now.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "model.transport_status": {
            "type": "string",
            "description": "Observed transport state for the requested model: ok|rate-limited|unavailable.",
            "enum": ("ok", "rate-limited", "unavailable"),
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "dependency.name": {
            "type": "string",
            "description": "Dependency package name as declared in the manifest.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "dependency.current": {
            "type": "string",
            "description": "Version currently installed or pinned.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "dependency.target": {
            "type": "string",
            "description": "Version the decision would move to.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "dependency.breaking": {
            "type": "boolean",
            "description": "Whether the target version is declared semver-breaking (from its changelog/metadata).",
        },
        "dependency.reviewed": {
            "type": "boolean",
            "description": "Whether the target version's changelog was actually reviewed.",
        },
        "credential.provider": {
            "type": "string",
            "description": "Credential provider (e.g. timi, anthropic); never a credential value.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "credential.kind": {
            "type": "string",
            "description": "Credential kind (api-key, oauth-token, ...); never a credential value.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "credential.scope": {
            "type": "string",
            "description": "Scope the credential grants or would grant; never a credential value.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "credential.exposed_to": {
            "type": "array",
            "description": "Processes/roles that would see the credential (isolation facts, not values).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "action.command": {
            "type": "string",
            "description": "The destructive command, redacted (no credentials); never raw secret material.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "action.targets": {
            "type": "array",
            "description": "Files/dirs the destructive command would touch (repo-relative).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "action.reversible": {
            "type": "boolean",
            "description": "Whether the action can be undone in this repository (git or backup facts).",
        },
        "action.backup_available": {
            "type": "boolean",
            "description": "Whether a current backup/snapshot exists that could restore the targets.",
        },
        "release.version_current": {
            "type": "string",
            "description": "Version currently published/tagged for the packages.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "release.version_next": {
            "type": "string",
            "description": "Version the release decision would publish.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "release.staged_paths": {
            "type": "array",
            "description": "Paths staged for the commit/release (repo-relative).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "release.changelog_ready": {
            "type": "boolean",
            "description": "Whether every touched package's [Unreleased] section is updated.",
        },
        "release.ci_green": {
            "type": "boolean",
            "description": "Whether CI is green on the commit being released (recorded run status).",
        },
        "conflict.user_instruction": {
            "type": "string",
            "description": "The user instruction as given, summarized (no quotes beyond one line).",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "conflict.rule_ref": {
            "type": "string",
            "description": "The project rule the instruction conflicts with: <path>:<line> reference.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "conflict.rule_strength": {
            "type": "string",
            "description": "How binding the rule is: hard (must ask) or advisory (may override with a reason).",
            "enum": ("hard", "advisory"),
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "conflict.irreversible": {
            "type": "boolean",
            "description": "Whether following the instruction has irreversible external effects.",
        },
        "gate.kind": {
            "type": "string",
            "description": "Autopilot human-gate class (autopilot.gates.GATE_KINDS, 6 values).",
            "enum": GATE_KIND_ENUM,
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "gate.pending_items": {
            "type": "array",
            "description": "Items the human gate still lists as pending.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "gate.age_minutes": {
            "type": "integer",
            "description": "How long the gate has been pending, in minutes.",
            "min_value": 0,
        },
        "gate.evidence_refs": {
            "type": "array",
            "description": "Evidence references attached to the gate (<path>:<line> or command).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "goal.current_digest": {
            "type": "string",
            "description": "Digest/fingerprint of the current goal document the decision is measured against.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "goal.proposed_delta": {
            "type": "string",
            "description": "What the proposed goal change adds or removes, in one line.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "goal.alignment": {
            "type": "string",
            "description": "Alignment verdict of the change: aligned|drift|conflict (against goal.md).",
            "enum": ("aligned", "drift", "conflict"),
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "spec.ac_ids": {
            "type": "array",
            "description": "Every AC id in the locked spec (a key's full set fits: up to 128).",
            "max_items": STATE_ARRAY_MAX_ITEMS_WIDE,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "spec.ac_changed": {
            "type": "array",
            "description": "AC ids this change touches; must be a subset of spec.ac_ids (up to 128).",
            "max_items": STATE_ARRAY_MAX_ITEMS_WIDE,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "spec.open_questions": {
            "type": "array",
            "description": "Open questions that must be resolved before the spec can be locked.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "claim.key": {
            "type": "string",
            "description": "AgenticTask key whose claim conflicts.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "claim.owner": {
            "type": "string",
            "description": "Recorded claim owner (worker/session id from the claim index).",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "claim.heartbeat_age_min": {
            "type": "integer",
            "description": "Minutes since the owner's last heartbeat (liveness fact, not a guess).",
            "min_value": 0,
        },
        "claim.owner_active": {
            "type": "boolean",
            "description": "Whether the owner process was confirmed alive (pid/activity fact).",
        },
        "write.target_path": {
            "type": "string",
            "description": "Repo-relative path the task wants to write outside its face.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "write.cross_key_owner": {
            "type": "string",
            "description": "Key that owns the foreign path, if any (from the key index).",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "write.write_scope": {
            "type": "array",
            "description": "The task's declared write face (repo-relative globs/paths).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "write.foreign_paths": {
            "type": "array",
            "description": "Paths outside the declared face that would be written.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "write.allow_foreign_write": {
            "type": "boolean",
            "description": "Fact about whether a previous authorization allowed this foreign write (not a grant).",
        },
        "stage.id": {
            "type": "string",
            "description": "Stage identifier the close decision applies to.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "stage.tasks_done": {
            "type": "integer",
            "description": "Tasks of the stage already closed (must not exceed the total).",
            "min_value": 0,
        },
        "stage.tasks_total": {
            "type": "integer",
            "description": "Tasks the stage contains, per its roadmap table.",
            "min_value": 0,
        },
        "stage.open_blockers": {
            "type": "array",
            "description": "Blockers still open for the stage (ids/refs).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "stage.evidence_refs": {
            "type": "array",
            "description": "Evidence files backing the stage close (<path>:<line> or command).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "refine.clause": {
            "type": "string",
            "description": "The requirement clause the refinement would change.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "refine.impact_paths": {
            "type": "array",
            "description": "Files the refinement would touch (repo-relative).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "refine.reversible": {
            "type": "boolean",
            "description": "Whether the refinement can be undone without losing accepted work.",
        },
        "debug.signal": {
            "type": "string",
            "description": "The failing signal/stack-first-line the debug plan starts from.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "debug.last_green_ref": {
            "type": "string",
            "description": "Last known-good reference (commit sha or run id) the plan compares against.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "debug.repro_available": {
            "type": "boolean",
            "description": "Whether a reproduction exists/ran (recorded fact, not an assumption).",
        },
        "debug.change_scope": {
            "type": "array",
            "description": "Paths the debug change would touch (repo-relative).",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "snapshot.size_bytes": {
            "type": "integer",
            "description": "Current size of the memory snapshot artifact in bytes (fs-stated).",
            "min_value": 0,
        },
        "snapshot.delta_bytes": {
            "type": "integer",
            "description": "New size minus old size in bytes; negative means the snapshot shrank (signed).",
            "signed": True,
        },
        "snapshot.sections_changed": {
            "type": "array",
            "description": "Document sections the snapshot rewrite changes.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
        },
        "project.path": {
            "type": "string",
            "description": "Project path the trust decision applies to (as pi recorded it).",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "project.trust_state": {
            "type": "string",
            "description": "Current pi trust state for the project: untrusted|trusted.",
            "enum": ("untrusted", "trusted"),
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "project.origin": {
            "type": "string",
            "description": "Where the project came from: user (created locally)|clone|foreign.",
            "enum": ("user", "clone", "foreign"),
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "project.pending_changes": {
            "type": "boolean",
            "description": "Whether the project has uncommitted changes that the trust grant would cover.",
        },
        # ------------------------------------------------------------------
        # Optional L1 paths (design §4.5): declared, type-checked, never
        # required, dropped first when the state budget needs room.
        # ------------------------------------------------------------------
        "history": {
            "type": "object",
            "description": "Recent dispatch outcome counters (recent_done/recent_failed/...), optional L1.",
        },
        "scope.images_required": {
            "type": "boolean",
            "description": "Whether the task needs image input, optional L1.",
        },
        "progress.writes": {
            "type": "integer",
            "description": "Tool writes counted so far in the checkpoint window, optional L1.",
            "min_value": 0,
        },
        "progress.uniq_targets": {
            "type": "integer",
            "description": "Distinct files written so far, optional L1.",
            "min_value": 0,
        },
        "progress.repeat_top": {
            "type": "integer",
            "description": "Highest repeat count on one target (thrash signal), optional L1.",
            "min_value": 0,
        },
        "progress.trend": {
            "type": "array",
            "description": "Per-checkpoint {elapsed_minutes, reads, writes} points, optional L1.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "object",
        },
        "progress.last_land_age_min": {
            "type": "integer",
            "description": "Minutes since the worker last landed an artifact, optional L1.",
            "min_value": 0,
        },
        # ------------------------------------------------------------------
        # T03 eight-entry business material (new entries). Every field names a
        # fact the initiator really has; a missing fact must stay missing.
        # ------------------------------------------------------------------
        "images_required": {
            "type": "boolean",
            "description": "Whether the dispatched task needs to read images; true means vision only, false/absent is never an image-capability proof.",
        },
        "reachability_facts": {
            "type": "string",
            "description": "What is actually known about whether this task can be completed inside its authorization/budget.",
        },
        "completed": {
            "type": "string",
            "description": "What is actually finished so far, with evidence references; saying none is a real statement.",
        },
        "remaining": {
            "type": "string",
            "description": "What is still unfinished for this task.",
        },
        "blockers": {
            "type": "string",
            "description": "What blocks completion inside the boundary, or an explicit none.",
        },
        "constraints": {
            "type": "string",
            "description": "Constraints, remaining budget and authorization that bound this judgement.",
        },
        "investigation.unknown": {
            "type": "string",
            "description": "The one concrete unknown the bounded evidence step would resolve (investigate branch only).",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "investigation.evidence_source": {
            "type": "string",
            "description": "A source that can actually be consulted inside the existing authorization.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "investigation.budget": {
            "type": "string",
            "description": "The real remaining budget the evidence step may use (never a reset or a new grant).",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "investigation.stop_condition": {
            "type": "string",
            "description": "The concrete criterion that ends the evidence step; no open-ended investigation.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "review_requirements": {
            "type": "string",
            "description": "The quality/acceptance requirements this review is measured against.",
        },
        "review_evidence": {
            "type": "array",
            "description": "Evidence references the review actually examined (<path>:<line> or command); [] when none.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
            "empty_is_value": True,
        },
        "review_findings": {
            "type": "string",
            "description": "What the review found, including the concrete gap for a fix verdict.",
        },
        "uncovered_scope": {
            "type": "string",
            "description": "What this review did not cover; an explicit none is a real statement.",
        },
        "basis_issue": {
            "type": "string",
            "description": "The substantive requirement/design/acceptance problem that forces reopen; must be absent for pass.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "gate_background": {
            "type": "string",
            "description": "The concrete gate matter and why it is being sent for a decision now.",
        },
        "current_state": {
            "type": "string",
            "description": "The current real state of the gate facts, with unknowns marked unknown.",
        },
        "condition_evidence": {
            "type": "array",
            "description": "Evidence references for the gate conditions that are claimed to hold; [] when none.",
            "max_items": STATE_ARRAY_MAX_ITEMS,
            "item_type": "string",
            "item_max_bytes": STATE_ARRAY_ITEM_MAX_BYTES,
            "empty_is_value": True,
        },
        "pm_note.subject": {
            "type": "string",
            "description": "The PM's pre-submission note: what exactly is being approved.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "pm_note.planned_action": {
            "type": "string",
            "description": "The limited action the PM would take after an approve (never implied by the choice alone).",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "pm_note.basis.goal": {
            "type": "string",
            "description": "The goal/acceptance basis the note relies on.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "pm_note.basis.evidence": {
            "type": "string",
            "description": "The evidence the note relies on, with references.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "pm_note.basis.budget": {
            "type": "string",
            "description": "The remaining budget/limit the note relies on (no new budget is granted here).",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "pm_note.basis.authority": {
            "type": "string",
            "description": "The existing authorization the note relies on; this note never creates one.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "background.tried": {
            "type": "string",
            "description": "What has already been tried for this live problem, factually.",
        },
        "background.unknowns": {
            "type": "string",
            "description": "The facts still unknown; never filled in by inference.",
        },
        "background.constraints": {
            "type": "string",
            "description": "The authorization/budget/role constraints that bound every candidate.",
        },
        "decision_actor": {
            "type": "string",
            "description": "The real business subject whose decision is needed (not a self-reported role claim).",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
        "decision_object": {
            "type": "string",
            "description": "The concrete object/artefact the pending question is about.",
            "max_bytes": STATE_STRING_MAX_BYTES,
        },
    }
)

#: Optional L1 paths per dp (the closed set of *legal but not required* input).
#: Only the approved four-DP contract keeps an optional model field here; the
#: replaced dp1/dp2/dp3/dp25 audit and count facts are no longer part of the
#: business contract (identity/association stay in the local envelope).
#: Optional L1 paths per active entry (the closed set of *legal but not
#: required* input). A conditional requirement (investigate plan, reopen basis)
#: is enforced by the pure choice validator, not by making the field required.
OPTIONAL_STATE_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        # A task that needs images must be dispatched as vision; the fact stays
        # with the real dispatch material (never a capability claim).
        "dp-w-type": ("images_required",),
        # The PM may attach real worker execution (done/remaining/blocked/tried),
        # but no worker or no self-assessment is legal and never fabricates one.
        "dp-pm-steer": ("worker_execution",),
        # AC-046/AC-047: bounded evidence gathering must name the unknown, a real
        # source, the remaining budget and the stop criterion.
        "dp-w-check-task": (
            "investigation.unknown",
            "investigation.evidence_source",
            "investigation.budget",
            "investigation.stop_condition",
        ),
        # AC-005/AC-053: a basis problem is the reopen-specific fact; pass may
        # not be combined with one.
        "dp-QG": ("basis_issue",),
    }
)

#: The exact business keys sent to the model, per dp (design D001: one allowlist
#: projection, declared here and exported to TS). ``None``/absent means the dp
#: keeps its pre-existing contract and :func:`model_state_for` returns the state
#: unchanged. Identity (``STATE_IDENTITY_PATHS``) and association/audit facts
#: (``AUDIT_STATE_PATHS``) never appear here, so they can never be projected.
#: The exact business keys sent to the model, per active entry (design D001: one
#: allowlist projection, declared here and exported to TS). Every active entry
#: declares its own business material; identity (``STATE_IDENTITY_PATHS``) and
#: association/audit facts (``AUDIT_STATE_PATHS``) never appear here, so they can
#: never be projected. An id without an entry keeps the legacy "send the state
#: unchanged" fallback, but no active entry relies on it.
MODEL_STATE_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "dp-w-type": (
            "task_goal",
            "task_requirements",
            "task_deliverables",
            "images_required",
        ),
        "dp-pm-steer": (
            "task_goal",
            "task_requirements",
            "task_deliverables",
            "pm_decision_background",
            "worker_execution",
        ),
        "dp-w-check-task": (
            "task_goal",
            "reachability_facts",
            "completed",
            "remaining",
            "blockers",
            "constraints",
            "investigation.unknown",
            "investigation.evidence_source",
            "investigation.budget",
            "investigation.stop_condition",
        ),
        "dp-QG": (
            "review_requirements",
            "review_evidence",
            "review_findings",
            "uncovered_scope",
            "basis_issue",
        ),
        "dp-gate-approve": (
            "gate_background",
            "current_state",
            "condition_evidence",
            "pm_note.subject",
            "pm_note.planned_action",
            "pm_note.basis.goal",
            "pm_note.basis.evidence",
            "pm_note.basis.budget",
            "pm_note.basis.authority",
        ),
        "dp-sign-key": (
            "delivery_goal",
            "actual_completion",
            "verification_evidence.verified",
            "verification_evidence.unverified",
            "unfinished_impact",
        ),
        "dp-auto": (
            "question",
            "background.task_goal",
            "background.current_state",
            "background.tried",
            "background.unknowns",
            "background.constraints",
            "handling_options",
        ),
        "dp-route": (
            "decision_actor",
            "decision_object",
            "question",
        ),
    }
)

#: Local association/audit keys of the four model-contract dps: legal in the
#: local state (a ``Trigger.from_mapping`` payload carries them) but never part
#: of the business allowlist, so the projection and the transport drop them.
AUDIT_STATE_PATHS: tuple[str, ...] = ("key", "task_key", "trigger_id")

#: Optional L1 paths dropped first when the canonical state exceeds the budget
#: (lowest decision value first; derived from :data:`OPTIONAL_STATE_FIELDS`).
OPTIONAL_STATE_PATHS: tuple[str, ...] = tuple(
    dict.fromkeys(
        path
        for paths in OPTIONAL_STATE_FIELDS.values()
        for path in paths
    )
)

#: Required L1 paths truncated (halved) when dropping optional fields is not enough.
TRUNCATABLE_STATE_PATHS: tuple[str, ...] = ("task_summary", "ambiguity.question")

#: Cross-field facts the registry owns (design §4.5): the left/array value must
#: stay consistent with the bound it is compared to. Only active entries carry
#: enforced rules; the retired ones keep their explanation in
#: ``RETIRED_STATE_FIELD_CROSS_CHECKS`` (read-only, never consulted).
STATE_FIELD_CROSS_CHECKS: Mapping[str, tuple[dict[str, str], ...]] = MappingProxyType(
    {
        # AC-042: the PM-prepared candidate set is the only legal answer space.
        # No 2..5 / contiguous-cN bound (that legacy rule stays history-only).
        "dp-auto": (
            {"kind": "pm_candidates", "array": "handling_options"},
        ),
    }
)

_MISSING = object()


def _declared_state_paths(dp_id: str) -> tuple[str, ...]:
    """Required + optional paths of one dp, in declaration order (no duplicates)."""
    return tuple(
        dict.fromkeys(
            (*REQUIRED_STATE_FIELDS.get(dp_id, ()), *OPTIONAL_STATE_FIELDS.get(dp_id, ()))
        )
    )


def _utf8_len(value: str) -> int:
    return len(value.encode("utf-8"))


def _value_matches_type(value: object, kind: str) -> bool:
    """JSON-native type check (``bool`` is never an ``integer``/``number``)."""
    if kind == "string":
        return isinstance(value, str)
    if kind == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "boolean":
        return isinstance(value, bool)
    if kind == "array":
        return isinstance(value, list)
    if kind == "object":
        return isinstance(value, Mapping)
    return False


def _value_issues(path: str, value: object, spec: Mapping) -> list[tuple[str, str]]:
    """Enforce one declared value against its own spec (type/enum/caps)."""
    kind = str(spec["type"])
    if not _value_matches_type(value, kind):
        return [(path, f"expected {kind}, got {type(value).__name__}")]
    issues: list[tuple[str, str]] = []
    options = spec.get("enum")
    if options is not None and value not in options:
        # Closed-set output only (T05c N3): path/type/allowed set are safe facts,
        # the offending value is caller free text and is never echoed.
        issues.append(
            (path, f"must be one of {list(options)}, got str ({_utf8_len(value)} B)")
        )
    if kind == "string":
        max_bytes = spec.get("max_bytes")
        if not value.strip():
            issues.append((path, "must be a non-empty string"))
        elif max_bytes is not None and _utf8_len(value) > max_bytes:
            issues.append((path, f"{_utf8_len(value)} B > {max_bytes} B"))
    elif kind == "integer":
        min_value = spec.get("min_value")
        if min_value is not None and value < min_value:
            issues.append((path, f"must be >= {min_value}, got {value}"))
    elif kind == "array":
        max_items = spec.get("max_items")
        if max_items is not None and len(value) > max_items:
            issues.append((path, f"{len(value)} items > max_items {max_items}"))
        item_type = spec.get("item_type")
        if item_type is None:
            # Existing arrays (dp1/dp2/dp3/dp25) keep their pre-contract shape:
            # no declared element type means no new element rule.
            return issues
        item_max_bytes = spec.get("item_max_bytes")
        for index, item in enumerate(value):
            item_path = f"{path}[{index}]"
            if not _value_matches_type(item, item_type):
                issues.append(
                    (item_path, f"expected {item_type}, got {type(item).__name__}")
                )
                continue
            if item_type != "string":
                continue
            if not item.strip():
                issues.append((item_path, "must be a non-empty string"))
            elif item_max_bytes is not None and _utf8_len(item) > item_max_bytes:
                issues.append((item_path, f"{_utf8_len(item)} B > {item_max_bytes} B"))
    return issues


def _cross_field_issues(dp_id: str, state: Mapping) -> list[tuple[str, str]]:
    """Enforce the declared cross-field facts of one dp (skips missing values)."""
    issues: list[tuple[str, str]] = []
    for rule in STATE_FIELD_CROSS_CHECKS.get(dp_id, ()):
        kind = rule["kind"]
        if kind in ("lte", "count_lte"):
            left_path = rule["left"] if kind == "lte" else rule["array"]
            right_path = rule["right"] if kind == "lte" else rule["bound"]
            left = _lookup(state, left_path)
            right = _lookup(state, right_path)
            if kind == "lte":
                if not isinstance(left, int) or isinstance(left, bool):
                    continue
                left_value: object = left
            else:
                if not isinstance(left, list):
                    continue
                left_value = len(left)
            if not isinstance(right, int) or isinstance(right, bool):
                continue
            if kind == "lte" and left_value > right:
                issues.append(
                    (
                        left_path,
                        f"{left_path} ({left_value}) must be <= {right_path} ({right})",
                    )
                )
            elif kind == "count_lte" and left_value > right:
                issues.append(
                    (
                        left_path,
                        f"{left_path} has {left_value} items > {right_path} ({right})",
                    )
                )
        elif kind == "dynamic_candidates":
            path = rule["array"]
            candidates = _lookup(state, path)
            # Type/shape of a non-list is reported by the typed check above.
            if not isinstance(candidates, list):
                continue
            if len(candidates) < 2:
                issues.append(
                    (
                        path,
                        "needs at least 2 distinguishable handling candidates "
                        f"(got {len(candidates)}); a single candidate is not a choice",
                    )
                )
                continue
            problem = dynamic_choices_value_error(candidates)
            if problem:
                issues.append((path, problem))
                continue
            labels: set[str] = set()
            for index, item in enumerate(candidates):
                item_path = f"{path}[{index}]"
                description = item.get("description")
                if not isinstance(description, str) or not description.strip():
                    issues.append((f"{item_path}.description", "must be a non-empty string"))
                    continue
                label = str(item.get("label"))
                if label in labels:
                    issues.append(
                        (f"{item_path}.label", "must be distinct from every other candidate label")
                    )
                labels.add(label)
        elif kind == "pm_candidates":
            candidates = _lookup(state, rule["array"])
            if not isinstance(candidates, list):
                continue
            issues.extend(pm_candidate_issues(candidates))
        elif kind == "subset":
            items_path = rule["items"]
            of_path = rule["of"]
            items = _lookup(state, items_path)
            of = _lookup(state, of_path)
            if not isinstance(items, list) or not isinstance(of, list):
                continue
            missing = [item for item in items if item not in of]
            if missing:
                issues.append(
                    (
                        items_path,
                        f"{items_path} must be a subset of {of_path}; not present: {missing}",
                    )
                )
    return issues


def state_field_issues(dp_id: str, state: Mapping) -> tuple[tuple[str, str], ...]:
    """``(dotted path, detail)`` for every declared path that violates its spec.

    This is the single typed-contract checker behind the decision book (and the
    observation seam T05 reuses): it enforces the *present* declared values
    (required and optional) against type / ``enum`` / ``max_items`` / element
    byte caps / integer floors, then the cross-field facts. Missing required
    fields are reported by the closed-key-set gate instead (one defect, one
    code), and ``None`` on an optional path means "not reported".

    Unknown paths are not judged here: the closed key set is checked by
    :func:`state_unknown_key_issues`, the same checker the decision book uses.
    """
    issues: list[tuple[str, str]] = []
    for path in _declared_state_paths(dp_id):
        spec = STATE_FIELD_DESCRIPTIONS.get(path)
        if spec is None:  # pragma: no cover - import-time validation forbids it
            continue
        value = _lookup(state, path)
        if value is _MISSING or value is None:
            continue
        issues.extend(_value_issues(path, value, spec))
    issues.extend(_cross_field_issues(dp_id, state))
    return tuple(issues)


def state_identity_issues(dp_id: str, state: Mapping) -> tuple[tuple[str, str], ...]:
    """``(dotted path, detail)`` for identity values that contradict the registry.

    The three structural keys (``schema_version`` / ``decision_point`` /
    ``questions_version``) are written by the builder, so a *missing* value is
    not a defect (``_join_digest`` normalizes it the same way); an explicitly
    present value must equal the one authority:

    * ``schema_version`` == :data:`STATE_SCHEMA_VERSION`;
    * ``decision_point`` == the dp being decided;
    * ``questions_version`` == the registry entry of that dp.

    Pure and shared: the decision book delegates here (T05c N2) instead of
    keeping a second version table, and the seam runs it in step 5b so a
    non-book producer cannot send a state that names another dp/version. Details
    name only closed-set facts (the dp id, the registry version, the JSON type)
    — never the arbitrary value itself.
    """
    issues: list[tuple[str, str]] = []
    registry_dp = _REGISTRY_BY_ID.get(dp_id)
    expected = {
        "schema_version": STATE_SCHEMA_VERSION,
        "decision_point": dp_id,
        "questions_version": (
            None if registry_dp is None else registry_dp.questions_version
        ),
    }
    kinds = {
        "schema_version": "integer",
        "decision_point": "string",
        "questions_version": "string",
    }
    for path in STATE_IDENTITY_PATHS:
        value = _lookup(state, path)
        if value is _MISSING or value is None:
            continue
        kind = kinds[path]
        if not _value_matches_type(value, kind):
            issues.append((path, f"expected {kind}, got {type(value).__name__}"))
            continue
        wanted = expected[path]
        if wanted is None or value == wanted:
            continue
        if path == "schema_version":
            issues.append((path, f"must be {wanted}, got a different integer"))
        elif path == "decision_point":
            issues.append((path, f"must equal the decision's dp {dp_id!r}"))
        else:
            issues.append((path, f"must equal the registry value {wanted!r}"))
    return tuple(issues)


def _flatten_state(value: object, prefix: str = "") -> dict[str, object]:
    """Nested mapping -> ``{dotted_path: leaf}`` (empty mappings stay leaves).

    The flattening rule is shared with the decision book's closed-key gate so
    both surfaces report the same path for the same nested defect.
    """
    if isinstance(value, Mapping) and value:
        out: dict[str, object] = {}
        for key, child in value.items():
            child_prefix = f"{prefix}.{key}" if prefix else str(key)
            out.update(_flatten_state(child, child_prefix))
        return out
    if isinstance(value, Mapping) and not prefix:
        return {}
    return {prefix: value}


def state_unknown_key_issues(
    dp_id: str,
    state: Mapping,
    *,
    allow_context: bool = False,
    redactor: object | None = None,
) -> tuple[tuple[str, str], ...]:
    """``(dotted path, detail)`` for every state key the registry does not declare.

    The single closed-key-set checker (T05b F1): the registry's required +
    optional paths of one dp, plus :data:`STATE_IDENTITY_PATHS`, are the only
    legal keys; a subtree under a declared optional path is legal too (dp1
    ``history`` owns its whole tree). ``allow_context=True`` additionally admits
    the engineered ``context`` block, which production producers may attach and
    :mod:`decision_context` fits - the decision book keeps ``context`` at the top
    level instead, so its gate stays strict (``allow_context=False``).

    Missing required fields are reported by :func:`_missing_required` and the
    decision book's required check (one defect, one code); this checker only
    answers "is this key part of the contract at all?". The declared optional
    paths are the *only* widening (no caller-supplied allowance any more, T05c).

    Returned paths are display paths: the closed-key decision is still made on
    the raw flattened key (so field associations and the legal set do not
    change), but a segment that is arbitrary text or known-secret material is
    reported as ``<key>`` (``decision.safe_path_text``). ``redactor`` is the
    call's actual known-secret set (F3/T05e); ``None`` keeps the env/Bearer/
    ``sk-`` heuristic.
    """
    required = REQUIRED_STATE_FIELDS.get(dp_id, ())
    required_set = set(required)
    allowed = set(_declared_state_paths(dp_id)) | set(STATE_IDENTITY_PATHS)
    # Local association/audit facts are legal material for the local state of
    # EVERY dp (``Trigger.from_mapping`` injects them); ``model_state_for`` strips
    # them from the sent state, so they can never reach the model (design D001).
    allowed |= set(AUDIT_STATE_PATHS)
    optional_paths = OPTIONAL_STATE_FIELDS.get(dp_id, ())
    context_key = decision_context.CONTEXT_KEY
    issues: list[tuple[str, str]] = []
    for path in _flatten_state(state):
        if path in allowed:
            continue
        if any(path.startswith(item + ".") for item in optional_paths):
            continue
        if allow_context and (path == context_key or path.startswith(context_key + ".")):
            continue
        parent_of_required = any(item.startswith(path + ".") for item in required_set)
        display = decision.safe_path_text(path, redactor)
        if parent_of_required:
            holding = sorted(
                item for item in required_set if item.startswith(path + ".")
            )
            issues.append((display, f"must be an object holding {holding}"))
        else:
            issues.append(
                (display, "not in required_state_fields (closed key set)")
            )
    return tuple(issues)


def _validate_state_field_contract() -> None:
    """Import-time validation of the typed contract (a broken table is a bug).

    Fail-loud like :func:`_validate_registry`: an undeclared path, an unknown
    constraint key, an enum on a non-string, a non-array ``max_items``, a
    non-integer ``signed``/``min_value``, an optional path that is also required,
    or a cross-field rule naming an undeclared path must stop the import instead
    of exporting a contract no caller can satisfy.
    """

    def check_path(owner: str, path: str) -> None:
        spec = STATE_FIELD_DESCRIPTIONS.get(path)
        if spec is None:
            raise ValueError(
                f"{owner}: state path {path!r} has no STATE_FIELD_DESCRIPTIONS entry"
            )
        unknown = set(spec) - {"type", "description"} - set(STATE_FIELD_CONSTRAINT_KEYS)
        if unknown:
            raise ValueError(f"{owner}: {path!r} has unknown spec keys {sorted(unknown)}")
        kind = spec["type"]
        if kind not in STATE_FIELD_TYPES:
            raise ValueError(f"{owner}: {path!r} has unknown type {kind!r}")
        if not isinstance(spec["description"], str) or not spec["description"].strip():
            raise ValueError(f"{owner}: {path!r} has an empty description")
        options = spec.get("enum")
        if options is not None:
            if kind != "string":
                raise ValueError(f"{owner}: {path!r} declares enum on type {kind!r}")
            if (
                not isinstance(options, tuple)
                or not options
                or not all(isinstance(option, str) and option for option in options)
                or len(set(options)) != len(options)
            ):
                raise ValueError(f"{owner}: {path!r} enum must be unique non-empty strings")
        if "max_items" in spec or "item_type" in spec or "item_max_bytes" in spec:
            if kind != "array":
                raise ValueError(f"{owner}: {path!r} declares array constraints on {kind!r}")
        max_items = spec.get("max_items")
        if max_items is not None and (
            not isinstance(max_items, int) or isinstance(max_items, bool) or max_items < 1
        ):
            raise ValueError(f"{owner}: {path!r} max_items must be a positive integer")
        item_type = spec.get("item_type")
        if item_type is not None and item_type not in STATE_FIELD_TYPES:
            raise ValueError(f"{owner}: {path!r} has unknown item_type {item_type!r}")
        if "item_max_bytes" in spec and item_type != "string":
            raise ValueError(
                f"{owner}: {path!r} item_max_bytes needs item_type 'string'"
            )
        for key in ("max_bytes", "item_max_bytes"):
            limit = spec.get(key)
            if limit is not None and (
                not isinstance(limit, int) or isinstance(limit, bool) or limit < 1
            ):
                raise ValueError(f"{owner}: {path!r} {key} must be a positive integer")
        if "signed" in spec:
            if kind != "integer" or not isinstance(spec["signed"], bool):
                raise ValueError(f"{owner}: {path!r} signed must be a boolean on an integer")
        min_value = spec.get("min_value")
        if "empty_is_value" in spec:
            if kind not in ("array", "object") or not isinstance(
                spec["empty_is_value"], bool
            ):
                raise ValueError(
                    f"{owner}: {path!r} empty_is_value must be a boolean on an "
                    "array/object"
                )
        if min_value is not None and (
            kind != "integer" or not isinstance(min_value, int) or isinstance(min_value, bool)
        ):
            raise ValueError(f"{owner}: {path!r} min_value must be an integer on an integer")

    for dp_id, paths in RETIRED_STATE_FIELDS.items():
        if dp_id not in _RETIRED_BY_ID:
            raise ValueError(f"RETIRED_STATE_FIELDS: unknown retired id {dp_id!r}")
        for path in paths:
            check_path(dp_id, path)
    for dp_id, paths in REQUIRED_STATE_FIELDS.items():
        if dp_id not in _REGISTRY_BY_ID:
            raise ValueError(f"REQUIRED_STATE_FIELDS: unknown dp id {dp_id!r}")
        if len(set(paths)) != len(paths):
            raise ValueError(f"{dp_id}: duplicate required state path")
        for path in paths:
            check_path(dp_id, path)
    for dp_id, paths in OPTIONAL_STATE_FIELDS.items():
        if dp_id not in _REGISTRY_BY_ID:
            raise ValueError(f"OPTIONAL_STATE_FIELDS: unknown dp id {dp_id!r}")
        overlap = set(paths) & set(REQUIRED_STATE_FIELDS.get(dp_id, ()))
        if overlap:
            raise ValueError(f"{dp_id}: optional paths are also required: {sorted(overlap)}")
        for path in paths:
            check_path(dp_id, path)
    for dp_id, rules in STATE_FIELD_CROSS_CHECKS.items():
        declared = set(REQUIRED_STATE_FIELDS.get(dp_id, ()))
        for rule in rules:
            for key in ("left", "right", "array", "bound", "items", "of"):
                if key in rule and rule[key] not in declared:
                    raise ValueError(
                        f"{dp_id}: cross-field rule names undeclared path {rule[key]!r}"
                    )
    for dp_id, paths in MODEL_STATE_FIELDS.items():
        if dp_id not in _REGISTRY_BY_ID:
            raise ValueError(f"MODEL_STATE_FIELDS: unknown dp id {dp_id!r}")
        if len(set(paths)) != len(paths):
            raise ValueError(f"{dp_id}: duplicate model state path")
        declared = set(_declared_state_paths(dp_id))
        for path in paths:
            if path not in declared:
                raise ValueError(f"{dp_id}: model path {path!r} is not a declared state path")
            if path in STATE_IDENTITY_PATHS or path in AUDIT_STATE_PATHS:
                raise ValueError(f"{dp_id}: model path {path!r} is local-only material")
        missing = set(REQUIRED_STATE_FIELDS.get(dp_id, ())) - set(paths)
        if missing:
            raise ValueError(
                f"{dp_id}: required paths missing from MODEL_STATE_FIELDS: {sorted(missing)}"
            )
        unprojected_optional = set(OPTIONAL_STATE_FIELDS.get(dp_id, ())) - set(paths)
        if unprojected_optional:
            raise ValueError(
                f"{dp_id}: optional paths missing from MODEL_STATE_FIELDS: "
                f"{sorted(unprojected_optional)}"
            )


def _lookup(state: Mapping, dotted: str) -> object:
    current: object = state
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _set_path(target: dict, dotted: str, value: object) -> None:
    """Set one dotted path on ``target``, creating the intermediate objects."""
    parts = dotted.split(".")
    current = target
    for part in parts[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[parts[-1]] = value


def model_state_for(dp_id: str, state: Mapping) -> dict:
    """The single model allowlist projection of one dp's local state.

    A dp with a :data:`MODEL_STATE_FIELDS` entry sends exactly those business
    paths: identity (``schema_version``/``decision_point``/
    ``questions_version``) and local association/audit facts (``key``/
    ``task_key``/``trigger_id``) stay local, and any non-declared material was
    already refused by the closed key set, so this function never silently
    decides business content. Values are deep-copied so the caller's material
    and the sent payload cannot mutate each other.

    An id without an allowlist entry keeps the historical contract (a shallow
    copy of the state); no active entry relies on that fallback.
    """
    paths = MODEL_STATE_FIELDS.get(dp_id)
    local_only = {key: value for key, value in state.items() if key not in AUDIT_STATE_PATHS}
    if paths is None:
        return dict(local_only)
    projected: dict = {}
    for path in paths:
        value = _lookup(state, path)
        if value is _MISSING:
            continue
        _set_path(projected, path, copy.deepcopy(value))
    return projected


def _is_blank(value: object) -> bool:
    if value is _MISSING or value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _missing_required(state: Mapping, dp_id: str) -> tuple[str, ...]:
    missing = [path for path in REQUIRED_STATE_FIELDS.get(dp_id, ()) if _is_blank(_lookup(state, path))]
    return tuple(missing)


_validate_protocol_contract()
_validate_state_field_contract()


# ---------------------------------------------------------------------------
# Eight-entry protocol validators (T03): pure, read-only, no authority
# ---------------------------------------------------------------------------

#: The PM-prepared basis is a separate preparation input (D012A), never part of
#: the business material and never part of the sign-key four-part contract.
BASIS_SOURCE = "pm-prepared"
PREPARATION_KEYS: tuple[str, ...] = ("basis_catalog", "prepared_at")
BASIS_ITEM_KEYS: tuple[str, ...] = ("id", "text", "material_refs", "applies_to")
CANDIDATE_ITEM_KEYS: tuple[str, ...] = (
    "id",
    "label",
    "description",
    "consequence",
    "risk",
    "conditions",
)
#: A candidate label stays one short line (a quality rule, not the old bound).
CANDIDATE_LABEL_MAX = DYNAMIC_CHOICE_LABEL_MAX


def resolve_entry_choices(
    dp_id: str, material: Mapping | None = None
) -> tuple[str, ...]:
    """Legal answer ids of one active entry, in declaration order.

    Fixed entries return their frozen enum; dp-route returns the seven targets;
    dp-auto returns the ids of the PM-prepared ``handling_options`` (empty when
    no material was supplied yet). No default or first candidate is ever added.
    """
    entry = require_active_dp(dp_id)
    if entry.kind == "dynamic-candidates":
        if not isinstance(material, Mapping):
            return ()
        candidates = material.get(entry.candidate_source.split(":", 1)[1])
        if not isinstance(candidates, list):
            return ()
        return tuple(
            str(item["id"])
            for item in candidates
            if isinstance(item, Mapping) and isinstance(item.get("id"), str)
        )
    return tuple(ENTRY_CHOICES[dp_id])


def role_issues(dp_id: str, actor_role: object) -> tuple[tuple[str, str], ...]:
    """Whether the real initiating actor may submit this entry (eligibility only).

    It grants no tool, no write face and no new role: a route selection never
    authorises the selected entry, and a self-reported role is not evidence.
    """
    require_active_dp(dp_id)
    if not isinstance(actor_role, str) or actor_role not in ACTOR_ROLES:
        return (
            (
                "actor_role",
                f"must be one of {list(ACTOR_ROLES)}; an unknown or self-reported "
                "role neither grants nor substitutes authorization",
            ),
        )
    required = ENTRY_ROLES[dp_id]
    if actor_role != required:
        return (
            (
                "actor_role",
                f"role-forbidden: {dp_id} may only be initiated by {required}, "
                f"got {actor_role}",
            ),
        )
    return ()


def pm_candidate_issues(candidates: object) -> tuple[tuple[str, str], ...]:
    """Validate the PM-prepared candidate set of dp-auto (no legacy cN/2..5).

    AC-042: at least two distinguishable candidates, each with a non-empty
    description, consequence, risk and conditions; ids are free-form and only
    need to be unique inside this request, because the old ``c1..cN`` scheme and
    the 2..5 cap are history, not this entry's contract.
    """
    key = "handling_options"
    if not isinstance(candidates, list):
        return ((key, "expected a list of PM-prepared candidates"),)
    if len(candidates) < 2:
        return (
            (
                key,
                f"needs at least 2 distinguishable prepared candidates (got {len(candidates)}); "
                "a single candidate is not a choice",
            ),
        )
    issues: list[tuple[str, str]] = []
    seen_ids: set[str] = set()
    seen_labels: set[str] = set()
    for index, item in enumerate(candidates):
        item_path = f"{key}[{index}]"
        if not isinstance(item, Mapping):
            issues.append((item_path, "candidate is not an object"))
            continue
        unknown = sorted(set(item) - set(CANDIDATE_ITEM_KEYS))
        if unknown:
            issues.append((item_path, f"unknown candidate keys {unknown}"))
        for name in CANDIDATE_ITEM_KEYS:
            value = item.get(name)
            if not isinstance(value, str) or not value.strip():
                issues.append((f"{item_path}.{name}", "must be a non-empty string"))
        candidate_id = item.get("id")
        if isinstance(candidate_id, str) and candidate_id.strip():
            if candidate_id in seen_ids:
                issues.append((f"{item_path}.id", "must be unique inside this request"))
            seen_ids.add(candidate_id)
        label = item.get("label")
        if isinstance(label, str) and label.strip():
            if "\n" in label or "\r" in label:
                issues.append((f"{item_path}.label", "must be a single line"))
            elif len(label) > CANDIDATE_LABEL_MAX:
                issues.append(
                    (f"{item_path}.label", f"{len(label)} chars > {CANDIDATE_LABEL_MAX}")
                )
            if label in seen_labels:
                issues.append(
                    (f"{item_path}.label", "must be distinct from every other candidate")
                )
            seen_labels.add(label)
    return tuple(issues)


def entry_candidates_issues(
    dp_id: str, candidates: object
) -> tuple[tuple[str, str], ...]:
    """Candidate-set validation for the one dynamic entry (no other entry has one)."""
    entry = require_active_dp(dp_id)
    if entry.kind != "dynamic-candidates":
        return (
            (
                "candidates",
                f"{dp_id} has a {entry.kind} answer enum; prepared candidates are not its contract",
            ),
        )
    return pm_candidate_issues(candidates)


def entry_material_issues(
    dp_id: str, material: object
) -> tuple[tuple[str, str], ...]:
    """Full material contract of one entry: presence, closed keys, types, cross rules.

    Pure and read-only. It never fills a missing fact and never chooses an
    answer; a missing required path, an unknown key, a wrong type or a null where
    an array is required is a blocking issue, not a degraded success.
    """
    require_active_dp(dp_id)
    if not isinstance(material, Mapping):
        return (("material", "must be an object holding the entry's business material"),)
    issues: list[tuple[str, str]] = []
    for path in _missing_required(material, dp_id):
        issues.append((path, "missing or blank (input-incomplete)"))
    issues.extend(state_unknown_key_issues(dp_id, material))
    issues.extend(state_field_issues(dp_id, material))
    if dp_id == "dp-sign-key":
        issues.extend(sign_key_material_issues(material))
    if dp_id == "dp-gate-approve":
        issues.extend(pm_note_issues(material.get("pm_note")))
    if dp_id == "dp-auto":
        issues.extend(pm_candidate_issues(material.get("handling_options")))
    return tuple(issues)


def sign_key_material_issues(material: object) -> tuple[tuple[str, str], ...]:
    """The three sign-off arrays must be arrays: ``[]`` is real, null/missing is not.

    AC-051: ``verified``/``unverified``/``unfinished_impact`` keep the original
    array contract. An empty array is the producer's real "none"; null or a
    missing key can never be upgraded to it (that would fabricate material).
    """
    paths = (
        "verification_evidence.verified",
        "verification_evidence.unverified",
        "unfinished_impact",
    )
    issues: list[tuple[str, str]] = []
    for path in paths:
        value = _lookup(material, path) if isinstance(material, Mapping) else _MISSING
        if value is _MISSING or value is None:
            issues.append(
                (path, "must be an array; [] is the real none, null/missing is refused")
            )
        elif not isinstance(value, list):
            issues.append((path, f"expected array, got {type(value).__name__}"))
    return tuple(issues)


def pm_note_issues(note: object) -> tuple[tuple[str, str], ...]:
    """PM's pre-submission note: subject, planned action and the four-part basis.

    The note is a separate business input (AC-007): the model's basis selection
    never overwrites it, and the note never becomes a model-selected reason.
    """
    key = "pm_note"
    if not isinstance(note, Mapping):
        return ((key, "must be an object {subject, planned_action, basis{...}}"),)
    issues: list[tuple[str, str]] = []
    unknown = sorted(set(note) - {"subject", "planned_action", "basis"})
    if unknown:
        issues.append((key, f"unknown note keys {unknown}"))
    for name in ("subject", "planned_action"):
        value = note.get(name)
        if not isinstance(value, str) or not value.strip():
            issues.append((f"{key}.{name}", "must be a non-empty string"))
    basis = note.get("basis")
    if not isinstance(basis, Mapping):
        issues.append((f"{key}.basis", "must be an object {goal,evidence,budget,authority}"))
    else:
        unknown_basis = sorted(set(basis) - {"goal", "evidence", "budget", "authority"})
        if unknown_basis:
            issues.append((f"{key}.basis", f"unknown basis keys {unknown_basis}"))
        for name in ("goal", "evidence", "budget", "authority"):
            value = basis.get(name)
            if not isinstance(value, str) or not value.strip():
                issues.append((f"{key}.basis.{name}", "must be a non-empty string"))
    return tuple(issues)


def entry_choice_issues(
    dp_id: str, choice: object, material: Mapping | None = None
) -> tuple[tuple[str, str], ...]:
    """Validate one answer against the entry's own contract (no default choice).

    A missing/non-string selection is refused (never coerced to the first
    candidate or to approve/release). Conditional material is enforced only for
    the branch that needs it; a mismatch is a blocking issue, not a rewrite.
    """
    entry = require_active_dp(dp_id)
    if not isinstance(choice, str) or not choice.strip():
        return (("choice", "missing selection: no default candidate is applied"),)
    issues: list[tuple[str, str]] = []
    legal = resolve_entry_choices(dp_id, material)
    if entry.kind == "dynamic-candidates":
        prepared = (
            material.get(entry.candidate_source.split(":", 1)[1])
            if isinstance(material, Mapping)
            else None
        )
        # The PM-prepared set is part of the answer contract: a selection out of
        # a one-candidate / duplicate-id / incomplete set is not legal either.
        issues.extend(entry_candidates_issues(dp_id, prepared))
    if entry.kind == "dynamic-candidates" and not legal:
        issues.append(
            ("handling_options", "no PM-prepared candidates: the selection cannot be checked")
        )
    elif legal and choice not in legal:
        issues.append(
            (
                "choice",
                f"must be one of the {len(legal)} legal ids of {dp_id}; "
                "invented or retired ids are refused",
            ),
        )
    if dp_id == "dp-route" and choice == "dp-route":
        issues.append(("choice", "dp-route may not route to itself"))
    if dp_id == "dp-w-check-task" and choice == "investigate":
        for path in OPTIONAL_STATE_FIELDS["dp-w-check-task"]:
            if _is_blank(_lookup(material if isinstance(material, Mapping) else {}, path)):
                issues.append(
                    (path, "required by the investigate branch (bounded evidence plan)")
                )
    if dp_id == "dp-QG":
        basis_issue = (
            _lookup(material, "basis_issue") if isinstance(material, Mapping) else _MISSING
        )
        if choice == "reopen" and _is_blank(basis_issue):
            issues.append(
                ("basis_issue", "required by reopen: name the substantive basis problem")
            )
        if choice == "pass" and not _is_blank(basis_issue):
            issues.append(
                ("basis_issue", "pass cannot be combined with an unresolved basis problem")
            )
    return tuple(issues)


def _material_reference_set(material: object) -> set[str]:
    """Every referenceable path of one material object (leaves plus top keys).

    A basis item may cite a precise fact (``background.current_state``) or a
    whole declared input (``verification_evidence``); nothing else is accepted,
    so a prepared reason must point at material that really exists.
    """
    if not isinstance(material, Mapping):
        return set()
    return set(material) | set(_flatten_state(material))


def basis_catalog_issues(
    dp_id: str,
    catalog: object,
    material: Mapping | None = None,
) -> tuple[tuple[str, str], ...]:
    """Validate the PM-prepared D012A basis catalog (independent of material).

    Elements are ``{id, text, material_refs, applies_to}``: a unique non-empty
    id, a non-empty prepared text, at least one reference that exists in the
    submitted material, and at least one legal choice it applies to. Failure
    reasons, probabilities or the PM note are not catalog fields, so they cannot
    be presented as the model's selected reason.
    """
    require_active_dp(dp_id)
    key = "basis_catalog"
    if not isinstance(catalog, list) or not catalog:
        return (
            (
                key,
                "must be a non-empty list of prepared basis items "
                f"{list(BASIS_ITEM_KEYS)}; without it the entry is blocked",
            ),
        )
    legal = set(resolve_entry_choices(dp_id, material))
    references = _material_reference_set(material)
    issues: list[tuple[str, str]] = []
    seen: set[str] = set()
    for index, item in enumerate(catalog):
        path = f"{key}[{index}]"
        if not isinstance(item, Mapping):
            issues.append((path, "basis item is not an object"))
            continue
        unknown = sorted(set(item) - set(BASIS_ITEM_KEYS))
        if unknown:
            issues.append(
                (
                    path,
                    f"unknown basis keys {unknown}; a failure reason/probability "
                    "is not a prepared basis",
                )
            )
        item_id = item.get("id")
        if not isinstance(item_id, str) or not item_id.strip():
            issues.append((f"{path}.id", "must be a non-empty string"))
        elif item_id in seen:
            issues.append((f"{path}.id", "must be unique inside this catalog"))
        else:
            seen.add(item_id)
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            issues.append((f"{path}.text", "must be a non-empty prepared reason"))
        refs = item.get("material_refs")
        if not isinstance(refs, list) or not refs:
            issues.append(
                (f"{path}.material_refs", "must be a non-empty list of real material refs")
            )
        else:
            for position, ref in enumerate(refs):
                if not isinstance(ref, str) or not ref.strip():
                    issues.append(
                        (f"{path}.material_refs[{position}]", "must be a non-empty string")
                    )
                elif ref not in references:
                    issues.append(
                        (
                            f"{path}.material_refs[{position}]",
                            "does not reference a fact present in this material",
                        )
                    )
        applies = item.get("applies_to")
        if not isinstance(applies, list) or not applies:
            issues.append(
                (f"{path}.applies_to", "must name at least one legal choice id")
            )
        else:
            for position, target in enumerate(applies):
                if not isinstance(target, str) or not target.strip():
                    issues.append(
                        (f"{path}.applies_to[{position}]", "must be a non-empty string")
                    )
                elif legal and target not in legal:
                    issues.append(
                        (
                            f"{path}.applies_to[{position}]",
                            "is not a legal choice id of this entry",
                        )
                    )
    return tuple(issues)


def basis_selection_issues(
    basis_id: object,
    catalog: object,
    choice: object = None,
) -> tuple[tuple[str, str], ...]:
    """Validate the model's same-call basis id against the prepared catalog.

    The selection must exist in the catalog and (when a choice is given) the
    item must apply to that choice. A missing/unknown/mismatched basis is a
    blocking issue: no second call is made to ask for a reason, and the failure
    reason/confidence is never promoted to a basis.
    """
    key = "basis_id"
    if not isinstance(basis_id, str) or not basis_id.strip():
        return ((key, "missing basis selection: the prepared catalog is required"),)
    if not isinstance(catalog, list):
        return ((key, "no basis catalog to validate the selection against"),)
    matched = [
        item
        for item in catalog
        if isinstance(item, Mapping) and item.get("id") == basis_id
    ]
    if not matched:
        return ((key, "is not an id of the prepared basis catalog"),)
    item = matched[0]
    applies = item.get("applies_to")
    if isinstance(choice, str) and choice.strip() and isinstance(applies, list):
        if choice not in applies:
            return ((key, "does not apply to the selected choice"),)
    return ()


def preparation_issues(
    dp_id: str,
    preparation: object,
    material: Mapping | None = None,
    *,
    choice: object = None,
    basis_id: object = None,
) -> tuple[tuple[str, str], ...]:
    """Validate the separate D012A preparation block of one entry.

    ``preparation`` must be ``{basis_catalog, prepared_at}``. It is not part of
    the business material and not part of the sign-off arrays; without a
    complete catalog the entry stays blocked (no second model call).
    """
    require_active_dp(dp_id)
    if not isinstance(preparation, Mapping):
        return (
            (
                "preparation",
                f"must be an object {list(PREPARATION_KEYS)} (D012A prepared basis)",
            ),
        )
    issues: list[tuple[str, str]] = []
    unknown = sorted(set(preparation) - set(PREPARATION_KEYS))
    if unknown:
        issues.append(("preparation", f"unknown preparation keys {unknown}"))
    prepared_at = preparation.get("prepared_at")
    if not isinstance(prepared_at, str) or not prepared_at.strip():
        issues.append(
            ("prepared_at", "must be a non-empty ISO-8601 timestamp with an explicit offset")
        )
    else:
        # Same timestamp contract as the package's task-state observations:
        # ISO-8601, parsed with ``fromisoformat`` and carrying an explicit offset.
        try:
            parsed = datetime.datetime.fromisoformat(
                prepared_at[:-1] + "+00:00" if prepared_at.endswith("Z") else prepared_at
            )
        except ValueError:
            issues.append(("prepared_at", "is not an ISO-8601 timestamp"))
        else:
            if parsed.tzinfo is None or "T" not in prepared_at:
                issues.append(
                    (
                        "prepared_at",
                        "must be an ISO-8601 timestamp with an explicit offset (Z or +hh:mm)",
                    )
                )
    issues.extend(basis_catalog_issues(dp_id, preparation.get("basis_catalog"), material))
    if basis_id is not None:
        issues.extend(
            basis_selection_issues(
                basis_id, preparation.get("basis_catalog"), choice
            )
        )
    return tuple(issues)


def prepared_request_issues(
    dp_id: str,
    material: object,
    preparation: object = None,
    *,
    actor_role: object = None,
    choice: object = None,
    basis_id: object = None,
) -> tuple[tuple[str, str], ...]:
    """One pure gate for a prepared request: role -> material -> basis -> choice.

    Order follows the runtime contract: a retired/unknown id raises first (no
    model call), then the real role, then the complete material, then the
    prepared basis, then the answer. The role is the request's eligibility input
    (design.md:241 ``bound_actor``), so an omitted/unknown/cross-role value is
    refused exactly like a wrong one; a self-reported role is still not evidence
    of authorization. Nothing here executes, releases or signs, and the gate
    does not demand the model's same-call choice/basis before that call happens.
    """
    require_active_dp(dp_id)
    issues: list[tuple[str, str]] = []
    issues.extend(role_issues(dp_id, actor_role))
    issues.extend(entry_material_issues(dp_id, material))
    issues.extend(
        preparation_issues(dp_id, preparation, material, choice=choice, basis_id=basis_id)
    )
    if choice is not None:
        issues.extend(entry_choice_issues(dp_id, choice, material))
    return tuple(issues)


def vision_dispatch_issues(
    material: Mapping,
    choice: object,
    image_capability: object,
) -> tuple[tuple[str, str], ...]:
    """dp-w-type's image hard gate (AC-044): no proof means no vision worker.

    ``image_capability`` is the real dispatch fact: ``proven`` when the selected
    model is known to accept images, ``unproven``/``unknown``/anything else
    otherwise. An unknown capability is never a yes, a task that needs images is
    never downgraded to coding, and a non-vision type is refused when images are
    required.
    """
    issues: list[tuple[str, str]] = []
    needs_images = material.get("images_required") is True
    if choice == "vision":
        if not needs_images:
            issues.append(
                ("vision", "requires images_required=true on the real dispatch material")
            )
        if image_capability != "proven":
            issues.append(
                (
                    "image_capability",
                    "vision dispatch requires a proven image-capable model; "
                    "unknown/unproven must not start a worker and coding is not a fallback",
                )
            )
    elif needs_images:
        issues.append(
            (
                "images_required",
                "the task needs images but the selected type is not vision; "
                "do not start a worker that cannot read them",
            )
        )
    return tuple(issues)


def _without_path(state: Mapping, dotted: str) -> dict:
    """Copy-on-write removal of one dotted path (never mutates the caller's data)."""
    parts = dotted.split(".")
    return _remove_parts(state, tuple(parts))


def _remove_parts(state: Mapping, parts: tuple[str, ...]) -> dict:
    out = dict(state)
    if not parts:
        return out
    head, rest = parts[0], parts[1:]
    if head not in out:
        return out
    if not rest:
        out.pop(head, None)
        return out
    child = out[head]
    if not isinstance(child, Mapping):
        return out
    out[head] = _remove_parts(child, rest)
    return out


def _with_halved_path(state: Mapping, dotted: str) -> dict:
    parts = tuple(dotted.split("."))
    return _halve_parts(state, parts)


def _halve_parts(state: Mapping, parts: tuple[str, ...]) -> dict:
    out = dict(state)
    if not parts:
        return out
    head, rest = parts[0], parts[1:]
    if head not in out:
        return out
    if not rest:
        value = out[head]
        if isinstance(value, str) and len(value) > 8:
            out[head] = value[: max(1, len(value) // 2)]
        return out
    child = out[head]
    if not isinstance(child, Mapping):
        return out
    out[head] = _halve_parts(child, rest)
    return out


def _state_size(state: Mapping) -> int:
    return len(decision._encode_state(state))


def _fit_state(state: Mapping, *, limit: int = MAX_STATE_BYTES) -> tuple[dict, tuple[str, ...], int]:
    """Two-stage truncation (design D-019 step 6): drop optional L1, then halve.

    Returns ``(state, dropped_paths, size)``; a size still above ``limit`` means
    the required input itself is over budget and the caller must escalate
    ``input-oversize`` (never guess, never send an oversized payload).

    The engineered ``context`` block is fitted FIRST, against the headroom the
    rest of the state leaves (W6 / D-052): it is optional input, so it loses to
    every required field, and its bytes are counted inside the same
    :data:`MAX_STATE_BYTES` budget instead of riding on top of it.
    """
    current = dict(state)
    dropped: list[str] = []
    raw_context = current.get(decision_context.CONTEXT_KEY)
    if isinstance(raw_context, Mapping):
        base = {key: value for key, value in current.items() if key != decision_context.CONTEXT_KEY}
        headroom = limit - _state_size(base) - decision_context.CONTEXT_KEY_OVERHEAD
        fitted, cut_slots = decision_context.fit_context(raw_context, budget=headroom)
        current = dict(base)
        if fitted:
            # The model sees this text: run the same credential scrub the rest of
            # the decide layer applies to human-readable fields.
            current[decision_context.CONTEXT_KEY] = decision_context.redact_context(fitted)
        dropped.extend(f"context.{name}" for name in cut_slots)
        if cut_slots:
            # A cut context is a real truncation of the sent input: surface it the
            # same way the L1 stages do (ordered, stable, name-only).
            dropped = sorted(dropped)
    size = _state_size(current)
    if size <= limit:
        return current, tuple(dropped), size
    for path in OPTIONAL_STATE_PATHS:
        if path not in dropped and _lookup(current, path) is not _MISSING:
            candidate = _without_path(current, path)
            if _state_size(candidate) < _state_size(current):
                dropped.append(path)
                current = candidate
                size = _state_size(current)
                if size <= limit:
                    return current, tuple(dropped), size
    for path in TRUNCATABLE_STATE_PATHS:
        if _lookup(current, path) is _MISSING:
            continue
        candidate = _with_halved_path(current, path)
        if candidate != current:
            dropped.append(f"{path} (halved)")
            current = candidate
            size = _state_size(current)
            if size <= limit:
                return current, tuple(dropped), size
    return current, tuple(dropped), size


# ---------------------------------------------------------------------------
# Config read side (design §2.2, L0..L7) + hot reload (design D-022)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PointConfig:
    """Effective value for one dp (registry defaults merged with the table row)."""

    id: str
    tier: str
    enabled: bool
    mode: str
    note: str = ""
    source: str = "config"  # "config" | "default"
    orphaned: bool = False
    table_tier: str | None = None
    issues: tuple[str, ...] = ()
    #: Validated per-dp policy overrides (AC-016); ``None`` = this layer does not
    #: decide for that key, so the resolver falls through to ``.mw/decide.json``.
    min_confidence: float | None = None
    max_questions: int | None = None
    timeout_s: int | None = None


@dataclass(frozen=True)
class PointsConfig:
    """Parsed authorization table (fail-soft: never raises out of the read side)."""

    path: pathlib.Path | None
    exists: bool
    layer: str  # "L0".."L7" worst degradation applied, "OK" when clean
    warnings: tuple[str, ...] = ()
    points: Mapping[str, PointConfig] = field(default_factory=dict)
    signature: tuple[int, int] | None = None
    version: int | None = None

    def row(self, dp_id: str) -> PointConfig | None:
        """Return the configured row (includes ``orphaned`` rows) or ``None``."""
        return self.points.get(dp_id)

    def effective(self, dp_point: DecisionPoint) -> PointConfig:
        """Effective config for a registered dp: row wins, else registry default."""
        row = self.points.get(dp_point.id)
        if row is None or row.orphaned:
            return PointConfig(
                id=dp_point.id,
                tier=dp_point.tier,
                enabled=dp_point.default_enabled,
                mode=dp_point.default_mode,
                source="default",
            )
        # L4/L7: the registry tier always wins over the advisory table column.
        return replace(row, tier=dp_point.tier)

    def orphaned_ids(self) -> tuple[str, ...]:
        return tuple(sorted(row.id for row in self.points.values() if row.orphaned))

    def enabled_ids(self) -> tuple[str, ...]:
        return tuple(sorted(row.id for row in self.points.values() if row.enabled and not row.orphaned))


#: ``path string -> ((st_mtime_ns, st_size) | None, PointsConfig)``
_CONFIG_CACHE: dict[str, tuple[tuple[int, int] | None, PointsConfig]] = {}


def clear_points_config_cache() -> None:
    """Reset the in-process cache (tests / a caller that knows the file changed)."""
    _CONFIG_CACHE.clear()


def decide_points_config_path(project_dir: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(project_dir) / DECIDE_POINTS_RELATIVE_PATH


def _defaults_view(
    path: pathlib.Path | None,
    *,
    signature: tuple[int, int] | None,
    layer: str,
    warnings: tuple[str, ...] = (),
    exists: bool = False,
) -> PointsConfig:
    return PointsConfig(
        path=path,
        exists=exists,
        layer=layer,
        warnings=warnings,
        points=MappingProxyType({}),
        signature=signature,
        version=None,
    )


def _policy_number(value: object) -> float | None:
    """JSON number -> float (``bool`` is NOT a number), else ``None``."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) else None


def coerce_policy_value(
    key: str, value: object, *, per_dp: bool
) -> tuple[float | int | None, str | None]:
    """Validate one policy value; ``(value, problem)`` — never raises (AC-016).

    ``per_dp=True`` applies the row domain from :data:`POLICY_ROW_BOUNDS`;
    ``per_dp=False`` is the ``.mw/decide.json`` layer, which keeps its own looser
    transport budget (any number in [0, 1] for the confidence gate, any positive
    integer for the two budgets).
    """
    number = _policy_number(value)
    if number is None:
        return None, f"must be a number, got {value!r}"
    if key == "min_confidence":
        low, high = POLICY_ROW_BOUNDS[key] if per_dp else (0.0, 1.0)
        if not low <= number <= high:
            return None, f"{number:g} is outside [{low:g}, {high:g}]"
        return float(number), None
    if not number.is_integer():
        return None, f"must be an integer, got {value!r}"
    integer = int(number)
    if per_dp:
        low, high = (int(bound) for bound in POLICY_ROW_BOUNDS[key])
        if not low <= integer <= high:
            return None, f"{integer} is outside [{low}, {high}]"
    elif integer < 1:
        return None, f"must be >= 1, got {integer}"
    return integer, None


def _parse_row(dp_point: DecisionPoint, row_raw: object) -> tuple[PointConfig, tuple[str, ...], str]:
    """Parse one registered row; returns ``(row, issues, layer)``.

    Layers (design §2.2): L2 row not an object, L3 field type error, L4 illegal
    tier value, L5 ``enabled`` not a bool, L7 tier differs from the registry.
    L2/L3/L5 force ``enabled=false`` for that dp only; L4/L7 keep the registry
    tier; every degradation is recorded, never raised. L8 (spec §14 AC-016) is
    the advisory per-dp policy layer: the value is dropped and the resolver falls
    back, nothing is disabled.
    """
    issues: list[str] = []
    layer = "OK"
    enabled = dp_point.default_enabled
    mode = dp_point.default_mode
    note = ""
    table_tier: str | None = None
    force_off = False

    if not isinstance(row_raw, Mapping):
        return (
            PointConfig(
                id=dp_point.id,
                tier=dp_point.tier,
                enabled=False,
                mode=dp_point.default_mode,
                note="",
                source="config",
                table_tier=None,
                issues=(f"L2: row must be an object, got {type(row_raw).__name__}",),
            ),
            (f"L2 {dp_point.id}: row must be an object, got {type(row_raw).__name__}",),
            "L2",
        )

    if "mode" in row_raw:
        raw_mode = row_raw["mode"]
        if isinstance(raw_mode, str) and raw_mode in MODES:
            mode = raw_mode
        else:
            force_off = True
            issues.append(f"L3: mode must be auto|suggest, got {raw_mode!r}")
    if "note" in row_raw:
        raw_note = row_raw["note"]
        if isinstance(raw_note, str):
            note = raw_note
        else:
            force_off = True
            issues.append(f"L3: note must be a string, got {type(raw_note).__name__}")
    if "tier" in row_raw:
        raw_tier = row_raw["tier"]
        if not isinstance(raw_tier, str):
            force_off = True
            issues.append(f"L3: tier must be a string, got {type(raw_tier).__name__}")
        else:
            table_tier = raw_tier
            if raw_tier not in TIERS:
                issues.append(f"L4: tier {raw_tier!r} is not P0|P1|P2; registry tier kept")
            elif raw_tier != dp_point.tier:
                issues.append(f"L7: tier {raw_tier!r} differs from registry tier {dp_point.tier!r}; registry wins")
    if "enabled" in row_raw:
        raw_enabled = row_raw["enabled"]
        if isinstance(raw_enabled, bool):
            enabled = raw_enabled
        else:
            force_off = True
            issues.append(f"L5: enabled must be a boolean, got {type(raw_enabled).__name__}")

    # AC-016 per-dp policy knobs. A bad value never disables the dp and never
    # raises: it is dropped here (so the resolver falls through to the next
    # layer) and recorded as an L8 advisory issue, which `dp check`/`dp show`
    # print as the fallback reason.
    policy_values: dict[str, float | int | None] = dict.fromkeys(list(POLICY_KEYS))
    for key in POLICY_KEYS:
        if key not in row_raw:
            continue
        parsed, problem = coerce_policy_value(key, row_raw[key], per_dp=True)
        if problem is None:
            policy_values[key] = parsed
        else:
            issues.append(
                f"L8: {key} {problem}; effective value falls back to the next layer"
            )

    if force_off:
        enabled = False

    layers = [issue.split(":", 1)[0] for issue in issues]
    if layers:
        layer = max(layers)  # L2 < L3 < L4 < L5 < L7 lexicographically holds
    warnings = tuple(f"{issue.split(':', 1)[0]} {dp_point.id}: {issue.split(':', 1)[1].strip()}" for issue in issues)
    row = PointConfig(
        id=dp_point.id,
        tier=dp_point.tier,
        enabled=enabled,
        mode=mode,
        note=note,
        source="config",
        orphaned=False,
        table_tier=table_tier,
        issues=tuple(issues),
        min_confidence=policy_values["min_confidence"],
        max_questions=policy_values["max_questions"],
        timeout_s=policy_values["timeout_s"],
    )
    return row, warnings, layer


def _parse_orphan_row(dp_id: str, row_raw: object) -> PointConfig:
    """L6: unknown dp id — keep the row, mark it ``orphaned``, never drop it."""
    if not isinstance(row_raw, Mapping):
        return PointConfig(
            id=dp_id,
            tier="",
            enabled=False,
            mode="auto",
            orphaned=True,
            issues=(f"L6: unknown dp id; row is not an object ({type(row_raw).__name__})",),
        )
    raw_enabled = row_raw.get("enabled")
    raw_mode = row_raw.get("mode")
    raw_tier = row_raw.get("tier")
    return PointConfig(
        id=dp_id,
        tier=raw_tier if isinstance(raw_tier, str) else "",
        enabled=raw_enabled if isinstance(raw_enabled, bool) else False,
        mode=raw_mode if isinstance(raw_mode, str) and raw_mode in MODES else "auto",
        note=row_raw.get("note") if isinstance(row_raw.get("note"), str) else "",
        source="config",
        orphaned=True,
        table_tier=raw_tier if isinstance(raw_tier, str) else None,
        issues=("L6: unknown dp id; row kept and marked orphaned",),
    )


_LAYER_ORDER = ("L0", "L1", "L2", "L3", "L4", "L5", "L6", "L7", "L8")


def _worst_layer(current: str, candidate: str) -> str:
    if current == "OK":
        return candidate
    if candidate == "OK":
        return current
    return candidate if _LAYER_ORDER.index(candidate) > _LAYER_ORDER.index(current) else current


def _parse_points_text(
    text: str, path: pathlib.Path, signature: tuple[int, int]
) -> PointsConfig:
    try:
        raw = json.loads(text)
    except ValueError as exc:
        return _defaults_view(
            path,
            signature=signature,
            layer="L1",
            warnings=(f"L1: invalid JSON ({exc.__class__.__name__}); all defaults applied",),
            exists=True,
        )
    if not isinstance(raw, Mapping):
        return _defaults_view(
            path,
            signature=signature,
            layer="L1",
            warnings=(f"L1: top level must be a JSON object, got {type(raw).__name__}; all defaults applied",),
            exists=True,
        )
    points_raw = raw.get("points")
    if points_raw is None:
        return _defaults_view(
            path,
            signature=signature,
            layer="L1",
            warnings=("L1: 'points' is missing; all defaults applied",),
            exists=True,
        )
    if not isinstance(points_raw, Mapping):
        return _defaults_view(
            path,
            signature=signature,
            layer="L1",
            warnings=(f"L1: 'points' must be an object, got {type(points_raw).__name__}; all defaults applied",),
            exists=True,
        )

    version_raw = raw.get("version")
    version = version_raw if isinstance(version_raw, int) and not isinstance(version_raw, bool) else None

    points: dict[str, PointConfig] = {}
    warnings: list[str] = []
    layer = "OK"
    if version is None:
        # Not a degradation layer of design §2.2: the rows still parse normally.
        warnings.append("version is missing or not an integer (advisory only)")

    for dp_id_raw, row_raw in points_raw.items():
        if not isinstance(dp_id_raw, str) or not dp_id_raw.strip():
            warnings.append(f"L2: dp id must be a non-empty string, got {dp_id_raw!r}; row ignored")
            layer = _worst_layer(layer, "L2")
            continue
        dp_id = dp_id_raw.strip()
        dp_point = _REGISTRY_BY_ID.get(dp_id)
        if dp_point is None:
            points[dp_id] = _parse_orphan_row(dp_id, row_raw)
            warnings.append(f"L6 {dp_id}: unknown dp id; row kept and marked orphaned")
            layer = _worst_layer(layer, "L6")
            continue
        row, row_warnings, row_layer = _parse_row(dp_point, row_raw)
        points[dp_id] = row
        warnings.extend(row_warnings)
        layer = _worst_layer(layer, row_layer)

    return PointsConfig(
        path=path,
        exists=True,
        layer=layer,
        warnings=tuple(warnings),
        points=MappingProxyType(points),
        signature=signature,
        version=version,
    )


def load_points_config(
    project_dir: pathlib.Path | str, *, use_cache: bool = True
) -> PointsConfig:
    """Load ``.mw/decide-points.json`` fail-soft, with ``(mtime_ns, size)`` caching.

    This function never raises: every failure degrades to registry defaults
    (L0/L1) or per-row degradations (L2..L7). A cached view is reused only when
    the file's ``(st_mtime_ns, st_size)`` signature is unchanged, so a rewrite
    inside the same second (Windows FAT 2 s granularity) is still observed — the
    writer is expected to set ``os.utime(ns=...)`` explicitly (design D-022).
    """
    path: pathlib.Path | None = None
    try:
        path = decide_points_config_path(project_dir)
        signature: tuple[int, int] | None
        try:
            st = path.stat()
            signature = (int(st.st_mtime_ns), int(st.st_size))
        except OSError:
            signature = None

        cache_key = str(path)
        if use_cache:
            cached = _CONFIG_CACHE.get(cache_key)
            if cached is not None and cached[0] == signature:
                return cached[1]

        if signature is None:
            view = _defaults_view(path, signature=None, layer="L0")
        else:
            try:
                text = path.read_text(encoding="utf-8")
            except Exception as exc:  # noqa: BLE001 - read side must never raise
                view = _defaults_view(
                    path,
                    signature=signature,
                    layer="L1",
                    warnings=(f"L1: table unreadable ({type(exc).__name__}); all defaults applied",),
                    exists=True,
                )
            else:
                view = _parse_points_text(text, path, signature)

        if use_cache:
            _CONFIG_CACHE[cache_key] = (signature, view)
        return view
    except Exception as exc:  # noqa: BLE001 - last-resort guard (design §2.2)
        _LOGGER.warning("decide-points read failed hard (%s); defaults applied", type(exc).__name__)
        return _defaults_view(path, signature=None, layer="L1", warnings=(f"L1: {type(exc).__name__}",))


# ---------------------------------------------------------------------------
# Per-dp policy resolution (spec §14 AC-016 / design D-048..D-051)
# ---------------------------------------------------------------------------


def _row_policy_value(row: PointConfig | Mapping | None, key: str) -> float | int | None:
    """The row layer for one key, already validated (``None`` = no usable value).

    A :class:`PointConfig` carries values validated by :func:`_parse_row`; a raw
    mapping (parity fixtures, ad-hoc callers) is validated here with the same
    coercer, so an illegal value falls through instead of leaking out.
    """
    if isinstance(row, PointConfig):
        return getattr(row, key)
    if isinstance(row, Mapping) and key in row:
        parsed, _problem = coerce_policy_value(key, row[key], per_dp=True)
        return parsed
    return None


def _global_policy(decide_cfg: object | None) -> dict[str, float | int | None]:
    """The ``.mw/decide.json`` layer (``DecisionConfig`` or a raw mapping).

    Only keys the file actually declares speak from this layer: a
    :class:`decision.DecisionConfig` carries dataclass defaults (``20.0`` / ``8``)
    that must not be mistaken for a configured value, otherwise every origin
    would read ``decide.json`` and the fallback display in ``dp check``/
    ``dp show`` would be useless. A config built by hand (no project root) has no
    file to consult and contributes nothing; such callers pass a raw mapping.
    """
    values: dict[str, float | int | None] = dict.fromkeys(list(POLICY_KEYS))
    raw: dict[str, object] = {}
    if isinstance(decide_cfg, decision.DecisionConfig):
        root = getattr(decide_cfg, "project_root", None)
        declared: Mapping | None = None
        if root is not None:
            try:
                loaded = json.loads(
                    (pathlib.Path(root) / ".mw" / "decide.json").read_text(encoding="utf-8")
                )
            except (OSError, ValueError):
                loaded = None
            if isinstance(loaded, Mapping):
                declared = loaded
        if declared is not None:
            raw = {key: declared.get(key) for key in POLICY_KEYS}
        else:
            extras = decide_cfg.extras if isinstance(decide_cfg.extras, Mapping) else {}
            raw = {"min_confidence": extras.get("min_confidence")}
    elif isinstance(decide_cfg, Mapping):
        raw = {key: decide_cfg.get(key) for key in POLICY_KEYS}
    else:
        return values
    for key in POLICY_KEYS:
        if raw.get(key) is None:
            continue
        parsed, _problem = coerce_policy_value(key, raw[key], per_dp=False)
        values[key] = parsed
    return values


def _resolve_policy(
    dp_id: str,
    row: PointConfig | Mapping | None,
    decide_cfg: object | None,
) -> tuple[dict[str, float | int], dict[str, str]]:
    """``(effective values, per-key origin)`` for one dp, layer by layer."""
    effective: dict[str, float | int] = {}
    origins: dict[str, str] = {}
    global_layer = _global_policy(decide_cfg)
    for key in POLICY_KEYS:
        row_value = _row_policy_value(row, key)
        if row_value is not None:
            effective[key] = row_value
            origins[key] = "row"
            continue
        global_value = global_layer[key]
        if global_value is not None:
            effective[key] = global_value
            origins[key] = "decide.json"
            continue
        effective[key] = POLICY_DEFAULTS[key]
        origins[key] = "builtin"
    return effective, origins


def resolve_policy(
    dp_id: str,
    row: PointConfig | Mapping | None = None,
    decide_cfg: object | None = None,
) -> dict[str, float | int]:
    """Effective per-dp policy: per-dp row > ``.mw/decide.json`` > built-in.

    Exactly the three knobs of spec §14 AC-016 (``min_confidence``,
    ``max_questions``, ``timeout_s``). Illegal values are skipped, never raised:
    the resolver simply continues with the next layer, so nothing here can break
    a worker's decision chain. ``dp_id`` is accepted for the audit trail and for
    a future per-dp builtin table; the same defaults apply to every point today.
    """
    return dict(_resolve_policy(dp_id, row, decide_cfg)[0])


def resolve_policy_origins(
    dp_id: str,
    row: PointConfig | Mapping | None = None,
    decide_cfg: object | None = None,
) -> dict[str, str]:
    """Which layer decided each key (``row`` / ``decide.json`` / ``builtin``)."""
    return dict(_resolve_policy(dp_id, row, decide_cfg)[1])


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DecisionOutcome:
    """The single return type of :func:`decide_for`.

    ``status``: ``acted`` (auto mode executed the answer), ``suggested``
    (mode=suggest: archive row only, nothing acted on), ``escalated`` (a human
    must decide; ``escalated_reason`` says why). ``state_digest`` is computed in
    Python only (design D-004) so upstream clients never hash.

    ``answers``/``confidence_source``/``latency_ms`` are the transport facts the
    ``intent="answer"`` call sites (``mw decide run``) hand back verbatim; they
    are filled from the response whenever a transport call happened and stay
    ``None``/``0`` on the zero-spawn paths.
    """

    dp: str
    status: str
    escalated_reason: str | None
    answer: Mapping | None
    actual_action: str | None
    decision_id: str
    archived: bool
    detail: str = ""
    mode: str = "auto"
    state_digest: str | None = None
    transport_reason: str | None = None
    response: Mapping | None = None
    truncated: tuple[str, ...] = ()
    answers: Mapping | None = None
    confidence_source: str | None = None
    latency_ms: int = 0
    # ------------------------------------------------------------------
    # Observation / capture facts (mw-decision-dashboard T05). All additive
    # and ``None`` on a decision whose side ledger was not consulted, so the
    # pre-T05 outcome (and every frozen key) stays byte-identical.
    # ------------------------------------------------------------------
    #: Logical client call id of this decision (same id the ``call-end`` row
    #: carries); ``None`` when no client call happened (step 2/4 returns).
    call_id: str | None = None
    #: Reference of the per-call material snapshot (``book-<hex>`` /
    #: ``state-<hex>``); ``None`` when no state material existed.
    snapshot_ref: str | None = None
    #: Archive signal of this decision, a member of :data:`ARCHIVE_STATES`.
    archive_state: str | None = None
    #: Worst capture status of this decision (``ok``/``partial``/``failed``),
    #: ``None`` when nothing was captured (see :attr:`capture_channel`).
    capture_status: str | None = None
    #: Why capture did or did not happen, a member of :data:`CAPTURE_CHANNELS`.
    capture_channel: str | None = None
    #: Observation facts (``observe_only``/``bypassed``/``submission_id``);
    #: ``None`` on a production decision.
    observation: Mapping | None = None
    #: Pure authorization preview (:func:`authorization_preview`); only filled
    #: for an observation, where production's verdict is the thing observed.
    preview: Mapping | None = None


# ---------------------------------------------------------------------------
# Observation seam (design §5.3 / D-003; consumer = card T06)
# ---------------------------------------------------------------------------

#: Closed set of the ``decision-end`` archive signal (design §4.4).
#: ``not-attempted`` is this card's explicit value for the pre-transport
#: escalations (disabled / unavailable / input-*): no archive write was
#: attempted there by design, which is *not* the same fact as ``unknown``
#: (attempted, module unavailable or reason unknown).
ARCHIVE_STATES = ("created", "replayed", "skipped", "failed", "unknown", "not-attempted")

#: Why the side ledger did or did not receive this decision. ``no-scope`` means
#: "nothing was expected here" (the decision returned before a capture scope
#: existed), ``module-unavailable`` means "expected but broken" - the two must
#: stay distinguishable (T03 review F-1).
CAPTURE_CHANNELS = (
    "module-unavailable",
    "scope-error",
    "test-scope",
    "production-scope",
    "no-scope",
)

#: Snapshot kinds: the loaded decision book or the state that was actually sent.
SNAPSHOT_KINDS = ("book", "input-state")

#: Actor kinds the side ledger accepts. The authority is
#: ``decision_history.ACTOR_KINDS`` (T07c); it is repeated as a literal here
#: because ``decision_history`` imports ``decide_signoff``, which imports this
#: module (`decision_points` -> `decision_history` would be circular). The
#: dashboard contract test locks the two tuples to each other, so a drift is a
#: test failure instead of a silently accepted actor kind.
ACTOR_KINDS: tuple[str, ...] = ("human", "system", "unknown")

#: Byte cap for ``Observation.actor_id``, the metadata cap the side ledger
#: applies to actor ids (``decision_wire.METADATA_TEXT_LIMIT``), locked by the
#: same contract test.
ACTOR_ID_MAX_BYTES = 512


@dataclass(frozen=True)
class Observation:
    """Explicit human observe-only submission (design §5.3; card T06 submits).

    The seam is a *paired* contract, enforced by :func:`decide_for` before any
    state is built: ``intent`` must be ``answer`` and ``archive`` must be
    ``False``, otherwise the same call could observe *and* archive/act. The
    scope is the caller's isolated test scope (``scope_kind="test"`` with its
    own ``evidence_path``); production capture is never derived from it.

    Only the per-DP authorization gate is bypassed (``.mw/decide-points.json``
    ``enabled``/P0). The global transport switch, credentials, the typed input
    gate, the size budget and the answer check keep applying exactly as in
    production, so an observation cannot manufacture a request production
    would refuse.

    ``book`` is the loaded decision book when the submission came from one; it
    is snapshotted as the ``book`` kind. Without it the seam snapshots the sent
    state as ``input-state`` (never as a fabricated book).
    """

    scope: Any
    observe_only: bool = True
    submission_id: str | None = None
    book: Mapping | None = None
    actor_kind: str = "human"
    actor_id: str = "user-explicit"


def known_secret_superset(
    snapshot: decision.CredentialSnapshot | None,
) -> tuple[str, ...]:
    """The legacy timi leg of this call's snapshot - frozen, never re-resolved.

    :func:`decision.credential_snapshot` freezes the value the transport sends.
    When it came from the explicit ``cfg`` leg (``cfg.api_key`` /
    ``cfg.extras["api_key"]``), the timi chain was deliberately not consulted
    for the sent value, while the book gate and the capture redactor always
    included it (T05e). Keeping that leg makes the known set a *superset* of the
    frozen value and of the legacy discovery - it never becomes smaller, so
    nothing that used to be refused or redacted turns acceptable or storable
    because of T05j.

    T05l: the leg is read from the snapshot (:meth:`CredentialSnapshot.
    known_superset`), which resolves it at most once per snapshot and then
    freezes it. This function no longer performs a discovery of its own: every
    gate/capture face of one decision gets the same tuple, and a credential
    rotated mid-call cannot make two faces disagree.

    T05n: an object that is not a :class:`decision.CredentialSnapshot` has no
    frozen contract (``known_superset``/``frozen_known_values``), so returning
    ``()`` would silently shrink this decision's known set to empty and let the
    material be sent. Refuse with a value-free ``DecisionInputError`` instead.
    """
    if snapshot is None:
        return ()
    if not isinstance(snapshot, decision.CredentialSnapshot):
        raise decision.DecisionInputError(
            "refusing a foreign credential snapshot: the known-secret set of this "
            "decision requires decision.CredentialSnapshot (frozen cfg/env/"
            "Authorization values and the legacy timi leg); an object of type "
            f"{type(snapshot).__name__} cannot prove any of them, so nothing is sent"
        )
    return snapshot.known_superset()


def _command_known_values(
    cfg: object, snapshot: decision.CredentialSnapshot | None
) -> tuple[str, ...]:
    """The complete frozen known-set values one decision must protect (T05l).

    Exactly the values :func:`command_known_secret_redactor` builds a redactor
    from: the snapshot's frozen cfg/extras/Authorization/env values (T05n: taken
    at snapshot creation, never re-read here), the actual ``Authorization``, the
    legacy timi leg frozen on the snapshot, caller extras and the Bearer/
    ``sk-`` layers (the last are regex layers, not values).
    """
    return decision.known_credential_values(
        cfg, extra_secrets=known_secret_superset(snapshot), snapshot=snapshot
    )


def command_known_secret_redactor(
    cfg: object = None, *, snapshot: decision.CredentialSnapshot | None = None
) -> decision.KnownSecretRedactor:
    """The known-secret set of one command/decision (T05j seam).

    Same discovery as ``decision.known_secret_redactor`` (cfg values, the env
    heuristics, Bearer/``sk-``), plus this call's frozen credential and the
    legacy timi leg frozen on the snapshot (T05l: the snapshot resolves it once;
    this seam never re-resolves it). Shared by the CLI book gate (``mw.py``) and
    the decision gates below, so one command cannot end up with two different
    definitions of "this member is a secret".

    When the frozen snapshot already recorded a failed discovery, the snapshot's
    ``discovery_error`` makes the returned redactor fail closed (every text is a
    hit) instead of accepting material nobody could prove clean. T05n: a foreign
    snapshot object without the frozen contract is refused by
    :func:`known_secret_superset` (value-free ``DecisionInputError``) instead of
    silently becoming an empty set at this gate.
    """
    return decision.known_secret_redactor(
        cfg, extra_secrets=known_secret_superset(snapshot), snapshot=snapshot
    )


def _wire_api() -> Any | None:
    """The side ledger module, or ``None`` when it is missing/broken.

    ``decision`` is the single owner of that optional import (card T03), so this
    is a read of *its* state instead of a second import cache that could
    disagree with the transport about whether capture exists.
    """
    try:
        return decision._wire_module()
    except Exception:  # noqa: BLE001 - capture must never break a decision
        return None


#: The side-ledger entry points this seam actually consumes. A module that is
#: importable but lacks them is "broken", not "absent" (T03 review F-1).
_WIRE_REQUIRED_API = ("record_event", "production_scope", "test_scope", "SubstringRedactor")


def _wire_ready() -> bool:
    """True only when the capture module exposes the API this seam uses."""
    wire = _wire_api()
    if wire is None:
        return False
    return all(callable(getattr(wire, name, None)) for name in _WIRE_REQUIRED_API)


def _preview_of(
    dp_point: DecisionPoint,
    effective: PointConfig,
    *,
    config_layer: str,
    mode: str,
    transport_configured: bool,
) -> dict[str, Any]:
    """The single pure authorization preview (production gate order, no I/O).

    Evaluated in exactly the order :func:`decide_for` applies its gates:
    per-DP authorization -> global transport -> mode -> executor capability.
    ``would_act`` is a *capability label*: it says the registered executor
    would be invoked, never that it would succeed (``executor_invoked=False``,
    ``action_outcome="unknown"``). Gates that need an answer (input gate,
    budget, answer legality, confidence) are deliberately not predicted here.
    """
    executor = _executor_kind(dp_point.executor)
    if not effective.enabled:
        would_status, reason = "escalated", "disabled"
    elif not transport_configured:
        would_status, reason = "escalated", "unavailable"
    elif mode == "suggest":
        would_status, reason = "suggested", None
    elif executor != "wired":
        # ``none`` and the ``unwired`` placeholder both end in step 11
        # (``over-authority``); neither may read as "would act".
        would_status, reason = "escalated", "over-authority"
    else:
        would_status, reason = "acted", None
    return {
        "dp": dp_point.id,
        "tier": dp_point.tier,
        "enabled": bool(effective.enabled),
        "enabled_source": effective.source,
        "config_layer": config_layer,
        "mode": mode,
        "transport": "configured" if transport_configured else "unavailable",
        "executor": executor,
        "would_status": would_status,
        "would_escalated_reason": reason,
        "would_act": would_status == "acted",
        "would_action_label": f"executor:{dp_point.id}" if would_status == "acted" else None,
        "executor_invoked": False,
        "action_outcome": "unknown",
        "observe_only_bypass": False,
    }


def authorization_preview(
    dp_id: str,
    project_dir: pathlib.Path | str = ".",
    *,
    points_config: PointsConfig | None = None,
    config: decision.DecisionConfig | None = None,
) -> dict[str, Any]:
    """Read-only authorization preview for one dp (``mw decide monitor`` list).

    Pure apart from reading ``.mw/decide-points.json`` / ``.mw/decide.json``:
    no state is built, no client is created, no request is made and nothing is
    written. A disabled point or a disabled transport is reported as such
    (``would_status``/``would_escalated_reason``) instead of being "fixed"
    here.
    """
    dp_point = get_decision_point(dp_id)
    project = _coerce_project_dir(project_dir)
    view = points_config if points_config is not None else load_points_config(project)
    effective = view.effective(dp_point)
    cfg = config
    if cfg is None:
        cfg, _cfg_error = decision.DecisionConfig.from_project(project)
    mode = effective.mode if effective.mode in MODES else dp_point.default_mode
    return _preview_of(
        dp_point,
        effective,
        config_layer=view.layer,
        mode=mode,
        transport_configured=bool(cfg is not None and cfg.is_configured),
    )


@dataclass
class _ArchiveTrace:
    """Mutable archive signal of one decision (created/replayed/skipped/...).

    ``state`` stays ``None`` until :func:`_maybe_archive` is called, which lets
    the emitter distinguish "no archive write was attempted" (``not-attempted``)
    from a recorded outcome instead of guessing one from ``archived=False``.
    """

    state: str | None = None

    def mark(self, state: str) -> None:
        if state not in ARCHIVE_STATES:
            raise ValueError(f"archive state {state!r} is not in {ARCHIVE_STATES}")
        self.state = state


@dataclass
class _DecisionCapture:
    """Per-decision capture state: scope, snapshot material and the preview.

    One instance per :func:`decide_for` call. It holds no credential itself;
    the scope carries the injected redactor and the ledger sink.
    """

    observation: Observation | None = None
    intent: str = "act"
    scope: Any | None = None
    channel: str = "no-scope"
    bypassed: bool = False
    mode: str | None = None
    dp_id: str | None = None
    decision_id: str | None = None
    questions_version: str | None = None
    state: Mapping | None = None
    questions: Mapping | None = None
    state_digest: str | None = None
    #: The policy echo of this decision (T10). The resolved per-dp policy is set
    #: at step 4b and re-stamped with the *effective* confidence threshold once
    #: step 8 computes it, so the persisted snapshot carries the same value the
    #: archive row does and no reader has to re-resolve the config.
    policy: Mapping | None = None
    preview: Mapping | None = None
    call_id: str | None = None
    snapshot_ref: str | None = None
    #: Set when the caller's material was refused as illegal (a missing/blank
    #: required field, the typed contract, the closed key set or the observation
    #: book). Refused material is never stored as a snapshot: only the refusal
    #: facts belong in the ledger (T05b F1/F2, T05k N1).
    material_refused: bool = False

    def attach(
        self,
        scope: Any | None,
        channel: str,
        *,
        dp_id: str,
        decision_id: str,
        questions_version: str,
    ) -> None:
        if channel not in CAPTURE_CHANNELS:
            raise ValueError(f"capture channel {channel!r} is not in {CAPTURE_CHANNELS}")
        self.scope = scope
        self.channel = channel
        self.dp_id = dp_id
        self.decision_id = decision_id
        self.questions_version = questions_version

    def remember_state(
        self,
        state: Mapping,
        *,
        questions: Mapping | None,
        state_digest: str | None,
    ) -> None:
        """Keep the material of this call (never a reconstruction of it)."""
        self.state = dict(state)
        self.questions = questions
        self.state_digest = state_digest

    def record_call(self, client: Any) -> None:
        call_id = getattr(client, "last_call_id", None)
        if not isinstance(call_id, str) or not call_id:
            call_id = getattr(self.scope, "last_call_id", None)
        self.call_id = call_id if isinstance(call_id, str) and call_id else None

    # -- snapshot ---------------------------------------------------------

    def _snapshot_document(self) -> dict[str, Any] | None:
        if self.state is None or self.dp_id is None:
            return None
        if self.material_refused:
            return None
        rendered = dynamic_choice_labels(self.questions or {}, self.state) or {}
        kind = (
            "book"
            if self.observation is not None and self.observation.book is not None
            else "input-state"
        )
        if kind not in SNAPSHOT_KINDS:  # pragma: no cover - closed by construction
            raise ValueError(f"snapshot kind {kind!r} is not in {SNAPSHOT_KINDS}")
        document: dict[str, Any] = {
            "kind": kind,
            "decision_id": self.decision_id,
            "dp": self.dp_id,
            "questions_version": self.questions_version,
            "state_digest": self.state_digest,
            # The decision's own policy facts (T10/AC-023): the effective
            # threshold this decision applied, persisted with the material it
            # belongs to (an observation writes no archive row).
            "policy": dict(self.policy) if self.policy is not None else None,
            # The rendered enum of this call (design §4.3): a later human answer
            # is validated against these ids, so they must be stored, not rerendered.
            "candidates": {
                qid: [{"id": cid, "label": label} for cid, label in labels.items()]
                for qid, labels in rendered.items()
            },
            "state": self.state,
        }
        if kind == "book":
            document["book"] = self.observation.book if self.observation is not None else None
        return document

    def _snapshot_ref(self, document: Mapping) -> str:
        """Internally generated, validated identifier (never a path/credential)."""
        identity = {
            "kind": document.get("kind"),
            "decision_id": document.get("decision_id"),
            "dp": document.get("dp"),
            "questions_version": document.get("questions_version"),
            "state_digest": document.get("state_digest"),
            "candidates": {
                qid: [item["id"] for item in items if isinstance(item, Mapping)]
                for qid, items in (document.get("candidates") or {}).items()
            },
        }
        canonical = json.dumps(identity, ensure_ascii=False, sort_keys=True, default=str)
        digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
        prefix = "book" if document.get("kind") == "book" else "state"
        return f"{prefix}-{digest}"

    # -- emission ---------------------------------------------------------

    def _actor(self) -> tuple[str, str] | None:
        if self.observation is None:
            return None
        return (self.observation.actor_kind, self.observation.actor_id)

    def finish(
        self,
        trace: _ArchiveTrace,
        *,
        outcome: DecisionOutcome | None,
    ) -> dict[str, Any]:
        """Write ``book-snapshot`` + ``decision-end``; return outcome updates.

        Never raises: a capture failure is a fact on the outcome
        (``capture_status="failed"``), not a change to the decision result.
        ``outcome=None`` is the exception path (the archive write raised): the
        decision's own status was never returned, so it is recorded as unknown
        instead of being guessed.
        """
        archive_state = trace.state or "not-attempted"
        wire = _wire_api()
        capture_status: str | None = None
        if wire is not None and self.scope is not None:
            emitted = self._emit(
                wire,
                status=None if outcome is None else outcome.status,
                escalated_reason=None if outcome is None else outcome.escalated_reason,
                truncated=() if outcome is None else outcome.truncated,
                archive_state=archive_state,
            )
            capture_status = "failed" if not emitted else _capture_status_of(self.scope)
        elif self.channel in ("module-unavailable", "scope-error"):
            capture_status = "failed"
        return {
            "archive_state": archive_state,
            "capture_channel": self.channel,
            "capture_status": capture_status,
            "call_id": self.call_id,
            "snapshot_ref": self.snapshot_ref,
            "observation": (
                {
                    "observe_only": True,
                    "bypassed": bool(self.bypassed),
                    "submission_id": (
                        self.observation.submission_id if self.observation is not None else None
                    ),
                    "scope_kind": "test",
                }
                if self.observation is not None
                else None
            ),
            "preview": (
                {**dict(self.preview or {}), "observe_only_bypass": bool(self.bypassed)}
                if self.observation is not None and self.preview is not None
                else None
            ),
        }

    def _emit(
        self,
        wire: Any,
        *,
        status: str | None,
        escalated_reason: str | None,
        truncated: Iterable[str],
        archive_state: str,
    ) -> bool:
        """Append the snapshot and the decision-end row; ``False`` means failed."""
        scope = self.scope
        written = True
        document = self._snapshot_document()
        if document is not None:
            # A failed snapshot write is isolated on purpose: the decision-end
            # row still has to say what happened (T05b F4).
            try:
                text = json.dumps(
                    document, ensure_ascii=False, sort_keys=True, default=str
                )
                snapshot_ref = self._snapshot_ref(document)
                result = wire.record_event(
                    scope,
                    "book-snapshot",
                    fields={
                        "book_ref": snapshot_ref,
                        "book": scope.capture(text),
                        "file_sha256": None,
                        "book_sha256": None,
                        "book_version": "input-memory",
                    },
                    actor=self._actor(),
                )
                if bool(getattr(result, "written", False)):
                    # A reference may only point at a row that really exists
                    # (T05b F4): a failed/raised write leaves snapshot_ref None
                    # and the decision-end row carries no dangling book_ref.
                    self.snapshot_ref = snapshot_ref
                else:
                    written = False
            except Exception:  # noqa: BLE001 - capture must never break the decision
                written = False
        try:
            result = wire.record_event(
                scope,
                "decision-end",
                fields={
                    "status": status,
                    "escalated_reason": escalated_reason,
                    "archive": archive_state,
                    "state_digest": self.state_digest,
                    "questions_version": self.questions_version,
                    "truncated": list(truncated),
                    "mode": self.mode,
                    "intent": self.intent,
                    "book_ref": self.snapshot_ref,
                },
                actor=self._actor(),
            )
            written = written and bool(getattr(result, "written", False))
        except Exception:  # noqa: BLE001 - capture must never break the decision
            return False
        return written


def _capture_status_of(scope: Any) -> str | None:
    """Scope-level capture status (``ok``/``partial``/``failed``), never raises."""
    try:
        status = getattr(scope, "capture_status", None)
    except Exception:  # noqa: BLE001
        return "failed"
    return status if isinstance(status, str) else None


# ---------------------------------------------------------------------------
# Archive seam (design §2.4; writer = decide_archive.py, card T-03)
# ---------------------------------------------------------------------------

#: DI seam for tests / wiring: ``callable(**kwargs) -> Any`` replacing
#: ``decide_archive.append_decide``. ``None`` = import the real writer lazily.
ARCHIVE_WRITER: Callable[..., Any] | None = None


def _resolve_archive_writer() -> Callable[..., Any] | None:
    if ARCHIVE_WRITER is not None:
        return ARCHIVE_WRITER
    try:
        import decide_archive  # type: ignore[import-not-found]  # sibling, card T-03
    except ImportError:
        _LOGGER.debug("decide_archive not available; decision archive row skipped")
        return None
    writer = getattr(decide_archive, "append_decide", None)
    if not callable(writer):
        _LOGGER.warning("decide_archive.append_decide missing; decision archive row skipped")
        return None
    return writer


def _archive_decision(
    *,
    dp_point: DecisionPoint,
    trigger: Trigger,
    project_dir: pathlib.Path,
    state: Mapping | None,
    mode: str,
    response: Mapping | None,
    authority: str,
    escalated_reason: str | None,
    acted: bool,
    actual_action: str | None,
    note: str | None = None,
    policy: Mapping | None = None,
) -> tuple[bool, bool]:
    """Write one ``kind=decide`` archive row; returns ``(archived, replayed)``.

    ``duplicate="existing"`` is always passed (design D-032): a repeated
    ``decision_id`` replays the existing immutable row instead of raising, and
    ``replayed=True`` tells :func:`decide_for` to annotate the outcome with
    ``note=duplicate-replay``. No new escalate value is introduced for a
    replay, and the archive bytes stay untouched.

    ``escalated_reason`` is forwarded verbatim: the archive layer validates the
    same frozen vocabulary (design D-030), so there is no translation table that
    could disguise ``disabled`` as ``unavailable``.

    A missing module degrades to "no row, log only"; any other archive failure
    is fail-loud (design D-005): the archive is a correctness dependency,
    unlike the best-effort transport evidence line in ``decision.py``.

    ``policy`` is the effective per-dp policy of this decision (AC-016/D-051).
    It rides the row only when the writer accepts it: ``decide_archive
    .append_decide`` still has the pre-AC-016 signature, and passing an unknown
    keyword would turn every decision into a fail-loud archive error. The gap is
    reported once per process instead of being dropped silently, and disappears
    as soon as the writer gains the field.
    """
    writer = _resolve_archive_writer()
    if writer is None:
        return False, False
    _warn_policy_writer_once(writer)
    transport_available = bool((response or {}).get("available"))
    payload: dict[str, Any] = dict(
        path=pathlib.Path(project_dir) / DECISIONS_RELATIVE_PATH,
        dp=dp_point.id,
        key=trigger.key,
        task_key=trigger.task_key,
        trigger_id=trigger.resolved_id(),
        state=state,
        questions_version=dp_point.questions_version,
        available=transport_available,
        authority=authority,
        answer=(response or {}).get("answers") if transport_available else None,
        reason=None if transport_available else (response or {}).get("reason"),
        escalated_reason=escalated_reason,
        acted=acted,
        actual_action=actual_action,
        mode=mode,
        transport=(response or {}).get("transport"),
        model=(response or {}).get("model"),
        attempts=int((response or {}).get("attempts") or 0),
        latency_ms=int((response or {}).get("latency_ms") or 0),
        confidence=_aggregate_confidence((response or {}).get("answers")),
        confidence_source=(response or {}).get("confidence_source"),
        note=note,
        duplicate="existing",
    )
    if policy is not None and _writer_accepts_policy(writer):
        payload["policy"] = dict(policy)
    try:
        result = writer(**payload)
    except ImportError:  # pragma: no cover - defensive: lazy import inside writer
        _LOGGER.debug("decide_archive disappeared at write time; row skipped")
        return False, False
    return True, _is_replay(result)


_POLICY_WRITER_WARNED = False


def _writer_accepts_policy(writer: Callable[..., Any]) -> bool:
    """Does this archive writer take the ``policy`` field (AC-016/D-051)?"""
    try:
        parameters = inspect.signature(writer).parameters
    except (TypeError, ValueError):  # builtins / C callables: assume the old shape
        return False
    return "policy" in parameters or any(
        parameter.kind is inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _warn_policy_writer_once(writer: Callable[..., Any]) -> None:
    """Report the archive-side gap once per process (never on every decision)."""
    global _POLICY_WRITER_WARNED
    if _POLICY_WRITER_WARNED or _writer_accepts_policy(writer):
        return
    _POLICY_WRITER_WARNED = True
    _LOGGER.warning(
        "decide archive writer has no `policy` field yet; decide rows carry no "
        "per-dp policy echo (spec §14 AC-016 archive half pending)"
    )


def _is_replay(result: object) -> bool:
    """``append_decide`` replay signal: ``(row, created=False)``.

    Wrappers that only echo a row (dict) are treated as fresh writes, so a test
    recorder keeps working unchanged.
    """
    return isinstance(result, tuple) and len(result) == 2 and result[1] is False


def _maybe_archive(
    archive: bool, *, trace: _ArchiveTrace | None = None, **kwargs: Any
) -> tuple[bool, bool]:
    """``archive=False`` short-circuits; else ``_archive_decision`` -> (archived, replayed).

    ``trace`` receives the observation signal of design §4.4 (T05):
    ``skipped`` for an explicit ``archive=False``, ``created``/``replayed`` for a
    written row, ``unknown`` when the writer module is missing (nothing was
    written and the reason is not a hard failure), and ``failed`` when the
    archive raised - the original exception is then re-raised unchanged
    (the archive stays a correctness dependency, design D-005).
    """
    if not archive:
        if trace is not None:
            trace.mark("skipped")
        return False, False
    try:
        archived, replayed = _archive_decision(**kwargs)
    except BaseException:
        if trace is not None:
            trace.mark("failed")
        raise
    if trace is not None:
        trace.mark("unknown" if not archived else ("replayed" if replayed else "created"))
    return archived, replayed


def _aggregate_confidence(answers: Mapping | None) -> float | None:
    """Weakest-link aggregate over answer confidences (None when unreported)."""
    if not answers:
        return None
    values: list[float] = []
    for entry in answers.values():
        if not isinstance(entry, Mapping):
            continue
        confidence = entry.get("confidence")
        if isinstance(confidence, (int, float)) and not isinstance(confidence, bool):
            values.append(float(confidence))
    return min(values) if values else None


def _value_fits(value: object, spec: Mapping, dynamic_ids: tuple[str, ...] | None = None) -> bool:
    """Is ``value`` an acceptable answer for one registry question spec?

    ``dynamic_ids`` carries the per-request enum of a ``dynamic_choices``
    question (FIX-I): those questions have no static ``choices``, so the
    rendered ids are the only legal vocabulary.
    """
    qtype = spec.get("type")
    if qtype == decision.QUESTION_CHOICE:
        legal = dynamic_ids if dynamic_ids is not None else (spec.get("choices") or ())
        return value in legal
    if qtype == decision.QUESTION_SCORE:
        # Official TypeSafe scores are floats (e.g. 1.7), so the answer check
        # accepts numbers, not just ints (FIX-H).
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        return spec["min"] <= value <= spec["max"]
    if qtype == decision.QUESTION_BOX:
        return isinstance(value, str) and bool(value.strip())
    if qtype == decision.QUESTION_NOUL:
        # ``noul`` answers are the probability of "no useful output" (FIX-H).
        if not isinstance(value, (int, float)) or isinstance(value, bool):
            return False
        return 0.0 <= float(value) <= 1.0
    # Unknown type: the transport already refused it; accept nothing extra.
    return True


def _unusable_answer(
    answers: Mapping | None,
    questions: Mapping[str, Mapping],
    dynamic: Mapping[str, tuple[str, ...]] | None = None,
) -> str | None:
    """Step 8 input side: describe why no answer can be acted on, else ``None``.

    Only qids and defect classes are reported — answer values may be L2 material
    (spec §5.4), so they never reach the detail string.
    """
    if not isinstance(answers, Mapping) or not answers:
        return "answer is empty"
    incomplete = [
        qid
        for qid in questions
        if not isinstance(answers.get(qid), Mapping) or "value" not in answers[qid]
    ]
    if incomplete:
        return f"missing answer for {', '.join(sorted(incomplete))}"
    rendered = dynamic or {}
    illegal = [
        qid
        for qid, spec in questions.items()
        if not _value_fits(answers[qid]["value"], spec, rendered.get(str(qid)))
    ]
    if illegal:
        return f"illegal value for {', '.join(sorted(illegal))}"
    return None


# ---------------------------------------------------------------------------
# decide_for (design §2.3, 11 steps)
# ---------------------------------------------------------------------------


def _outcome(
    *,
    dp_point: DecisionPoint,
    trigger: Trigger,
    status: str,
    escalated_reason: str | None = None,
    answer: Mapping | None = None,
    actual_action: str | None = None,
    archived: bool = False,
    detail: object = "",
    mode: str = "auto",
    state_digest: str | None = None,
    transport_reason: str | None = None,
    response: Mapping | None = None,
    truncated: tuple[str, ...] = (),
    replayed: bool = False,
    answers: Mapping | None = None,
    confidence_source: str | None = None,
    latency_ms: int | None = None,
) -> DecisionOutcome:
    if status not in STATUSES:
        raise ValueError(f"status {status!r} is not in {STATUSES}")
    if escalated_reason is not None and escalated_reason not in ESCALATED_REASONS:
        raise ValueError(f"escalated_reason {escalated_reason!r} is not in the frozen set")
    detail_text = decision._scrub_detail(detail)
    if replayed:
        # Design D-032: a repeated trigger replays the immutable archive row; the
        # marker lives on the outcome because the archive bytes must not change.
        detail_text = f"{detail_text}; note=duplicate-replay"
    return DecisionOutcome(
        dp=dp_point.id,
        status=status,
        escalated_reason=escalated_reason,
        answer=answer,
        actual_action=actual_action,
        decision_id=f"{dp_point.id}:{trigger.resolved_id()}",
        archived=archived,
        detail=detail_text,
        mode=mode,
        state_digest=state_digest,
        transport_reason=transport_reason,
        response=response,
        truncated=truncated,
        answers=answers if answers is not None else (response or {}).get("answers"),
        confidence_source=confidence_source
        if confidence_source is not None
        else (response or {}).get("confidence_source"),
        latency_ms=int(latency_ms if latency_ms is not None else ((response or {}).get("latency_ms") or 0)),
    )


def _coerce_project_dir(project_dir: pathlib.Path | str | None) -> pathlib.Path:
    if project_dir is None:
        return pathlib.Path(".")
    return pathlib.Path(project_dir)


def _actor_issue(observation: Observation) -> str | None:
    """Why this actor declaration is illegal, or ``None`` when it is legal.

    The wire's ``_actor_of`` promises a closed actor-kind set but never checks
    it; an observation is the caller-controlled entry point, so the declaration
    is validated here, before any fact is written (T05b F5). The id must be
    single-line printable text within the wire's metadata cap; it is still an
    unproven claim (a declared ``human`` does not prove a human acted).
    """
    if observation.actor_kind not in ACTOR_KINDS:
        return (
            f"observation.actor_kind must be one of {list(ACTOR_KINDS)},"
            f" got {observation.actor_kind!r}"
        )
    actor_id = observation.actor_id
    if not isinstance(actor_id, str) or not actor_id.strip():
        return f"observation.actor_id must be a non-empty string, got {actor_id!r}"
    if any(ord(char) < 0x20 or ord(char) == 0x7F for char in actor_id):
        return "observation.actor_id must be single-line printable text"
    if len(actor_id.encode("utf-8")) > ACTOR_ID_MAX_BYTES:
        return f"observation.actor_id is {len(actor_id.encode('utf-8'))} B > {ACTOR_ID_MAX_BYTES} B"
    return None


def _validate_observation(
    observation: Observation | None,
    *,
    intent: str,
    archive: bool,
    client: decision.DecisionClient | None,
    project: pathlib.Path,
) -> None:
    """Enforce the paired observation contract before any work happens.

    Everything here is an argument/scope contract, so a misconfigured observe
    call fails with exit-2 semantics instead of observing *and* archiving, or
    observing into a ledger nobody proved isolated (design §5.3).
    """
    if observation is None:
        return
    if not isinstance(observation, Observation):
        raise decision.DecisionInputError(
            f"observation must be a decision_points.Observation, got {type(observation).__name__}"
        )
    actor_issue = _actor_issue(observation)
    if actor_issue is not None:
        raise decision.DecisionInputError(actor_issue)
    if not observation.observe_only:
        raise decision.DecisionInputError(
            "observation.observe_only must stay True: an observation never acts or archives"
        )
    if intent != "answer":
        raise decision.DecisionInputError(
            f"observation requires intent='answer', got {intent!r}; "
            "an observe-only call must not run an executor"
        )
    if archive is not False:
        raise decision.DecisionInputError(
            "observation requires archive=False: a test submission writes no production row"
        )
    scope = observation.scope
    scope_kind = getattr(scope, "scope_kind", None)
    if scope_kind != "test":
        raise decision.DecisionInputError(
            f"observation requires an isolated test scope, got scope_kind={scope_kind!r}"
        )
    evidence = getattr(scope, "evidence_path", None)
    if evidence is None:
        raise decision.DecisionInputError(
            "observation requires an explicit test evidence_path "
            "(no fallback to the production triage ledger)"
        )
    try:
        resolved_evidence = pathlib.Path(evidence).resolve()
    except OSError:  # pragma: no cover - unresolvable path is still not the production one
        resolved_evidence = pathlib.Path(evidence)
    if resolved_evidence == (project / decision.EVIDENCE_RELATIVE_PATH).resolve():
        raise decision.DecisionInputError(
            "observation evidence_path must not be the production triage ledger"
        )
    scope_submission = getattr(scope, "submission_id", None)
    if (
        observation.submission_id is not None
        and scope_submission is not None
        and observation.submission_id != scope_submission
    ):
        raise decision.DecisionInputError(
            "observation.submission_id must match the test scope's submission_id "
            f"({scope_submission!r})"
        )
    client_scope = getattr(client, "_wire_scope", None) if client is not None else None
    if client_scope is not None and client_scope is not scope:
        raise decision.DecisionInputError(
            "observation scope must be the client's wire scope "
            "(one isolated ledger per submission)"
        )


#: DI seam: the read-only decision-book validator, registered by
#: :mod:`decision_book` at import time. A module hook instead of an import:
#: ``decision_book`` imports this module, so the reverse import would be circular
#: (T05b F2). ``None`` means no validator is available, which refuses book
#: material instead of trusting it.
BOOK_VALIDATOR: Callable[..., tuple[tuple[str, str], ...]] | None = None


def register_book_validator(
    validator: Callable[..., tuple[tuple[str, str], ...]],
) -> None:
    """Register the decision-book validator (called by ``decision_book``).

    Repeatable for the same registration (a reload of ``decision_book`` hands
    over the same callable) but never a silent replacement: an illegal value or
    a different callable over an existing one raises, so the book authority
    cannot be swapped at runtime by a caller (T05c N4). ``None`` stays
    fail-closed (a book is refused until a validator is registered).

    The registered callable is invoked as
    ``validator(book, project_dir, *, redactor=<this call's known-secret set>)``
    (T05e F1); a validator that cannot prove the configured known secrets must
    refuse rather than silently accept.
    """
    global BOOK_VALIDATOR
    if not callable(validator):
        raise TypeError(
            f"book validator must be callable, got {type(validator).__name__}"
        )
    current = BOOK_VALIDATOR
    if current is not None and current is not validator:
        raise ValueError(
            "a decision-book validator is already registered; "
            "replace it deliberately instead of overwriting it"
        )
    BOOK_VALIDATOR = validator


def _book_issue_path(path: str) -> str:
    """Prefix a book issue path so the refusal names the refused surface."""
    if path == "book" or path.startswith("book."):
        return path
    return f"book.{path}"


def _join_digest(state: Mapping, dp_point: DecisionPoint) -> str:
    """Canonical digest of a state with the builder-owned identity normalized.

    ``check_book`` has already validated every identity value of a book, and the
    builder writes the three identity keys for every dp, so a state that omits
    ``questions_version`` is still the same material (the sent state genuinely
    may not carry it). Every other key must match byte for byte.
    """
    normalized = dict(state)
    normalized.setdefault("schema_version", STATE_SCHEMA_VERSION)
    normalized.setdefault("decision_point", dp_point.id)
    normalized.setdefault("questions_version", dp_point.questions_version)
    return _state_digest(normalized)


def _observation_book_issues(
    book: Mapping,
    *,
    dp_point: DecisionPoint,
    sent_state: Mapping,
    project: pathlib.Path,
    redactor: object | None = None,
) -> tuple[tuple[str, str], ...]:
    """Why this book cannot be the material of record of this call (T05b F2).

    A caller-supplied ``Observation.book`` is a claim: it must belong to this
    dp, pass the same validation ``mw decide book check`` runs (schema, closed
    state, placeholders, evidence, budget, secrets) and carry the state that is
    actually sent. Anything less is refused before the transport, so an
    unvalidated book is never snapshotted as material.

    ``redactor`` is this call's actual known-secret set
    (``decision.known_secret_redactor(cfg)``: cfg/Authorization values, the
    resolved timi credential, env rules + Bearer/``sk-``); it is handed to the
    registered validator so the observation gate checks the same values the
    transport is configured with, not only the env heuristic (T05e F1).
    """
    if not isinstance(book, Mapping):
        return (("book", f"must be a JSON object, got {type(book).__name__}"),)
    book_dp = book.get("decision_point")
    if book_dp != dp_point.id:
        return (
            (
                "book.decision_point",
                f"must equal this decision's dp {dp_point.id!r}, got {book_dp!r}",
            ),
        )
    issues: list[tuple[str, str]] = []
    book_state = book.get("state")
    if not isinstance(book_state, Mapping):
        issues.append(("book.state", "must be a JSON object"))
    validator = BOOK_VALIDATOR
    if validator is None:
        issues.append(
            (
                "book",
                "no book validator is registered (decision_book is not imported); "
                "refusing unverified book material",
            )
        )
    else:
        for path, detail in validator(book, project, redactor=redactor):
            issues.append((_book_issue_path(path), detail))
    if isinstance(book_state, Mapping) and _join_digest(
        book_state, dp_point
    ) != _join_digest(sent_state, dp_point):
        issues.append(
            (
                "book.state",
                "the book state is not the state of this call (digest join failed)",
            )
        )
    return tuple(issues)


def _redactor_covers(redactor: object, value: str) -> bool:
    """True when ``redactor`` provably removes ``value`` from captured text.

    T05q: the judgement itself lives in :func:`decision._redactor_covers` (a
    boundary probe: complete value, long tail, protocol). ``decision_points``
    owns its own *entry*, not its own definition of "covered", so the two
    consumptions cannot drift: the points seam previously carried a copy of the
    ``hits > 0`` / "text changed" test and leaked the same partial replacements
    as the client-only path.
    """
    return decision._redactor_covers(redactor, value)


def _caller_owned_scope(capture: _DecisionCapture, client: object | None) -> Any | None:
    """The scope this decision did **not** build itself (caller-owned ledger)."""
    observation = capture.observation
    if observation is not None:
        return observation.scope
    return getattr(client, "_wire_scope", None) if client is not None else None


def _caller_scope_coverage_issue(
    scope: object | None,
    snapshot: decision.CredentialSnapshot | None,
    *,
    cfg: object = None,
) -> str | None:
    """Why a caller-owned capture redactor cannot be called safe for this call.

    T05j. A caller-owned scope keeps its redactor (the transport never replaces
    it, by contract); this decision only *verifies* that the filter covers the
    material of this call. ``redact=None`` is fine: a test ledger without a
    redactor stores metadata only (fail-closed by design) and a production
    ledger gets one injected from this decision's snapshot.

    T05l: coverage is verified against the **complete frozen known set**
    (cfg/extras, the actual ``Authorization``, the legacy timi leg), not only the
    sent value - sending A never exempts captured B material. Any filter that
    misses one of those values is an unprovable capture: the caller must rebuild
    it from the snapshot instead of letting one decision send a value its ledger
    would store raw.

    T05q: ``_redactor_covers`` also rejects a partial replacement (a long tail of
    the value surviving) and a filter without ``scrub_tail_prefix``; the latter is
    reported as a protocol refusal rather than a silent zero-row capture.

    The message names no value: only the fact (a count) and the remedy.
    """
    if scope is None or snapshot is None:
        return None
    redactor = getattr(scope, "redact", None)
    if redactor is None:
        return None
    contract_issue = decision._capture_filter_contract_issue(redactor)
    if contract_issue is not None:
        # T05q F-2: a filter without the capture boundary contract would make
        # ``WireScope.capture`` raise (swallowed into a silent zero-row capture).
        # Refuse it here, before the transport, with the same value-free detail.
        return f"refusing an unprovable capture: {contract_issue}"
    values = _command_known_values(cfg, snapshot)
    if not values:
        return None
    missing = sum(1 for value in values if not _redactor_covers(redactor, value))
    if not missing:
        return None
    return (
        "refusing an unprovable capture: the caller-owned capture redactor does "
        f"not cover {missing} of the {len(values)} known-secret values of this "
        "decision (client and capture would diverge); rebuild the redactor from "
        "the same decision.credential_snapshot() the gate and the client use"
    )


def _decision_credential_snapshot(
    cfg: decision.DecisionConfig, client: decision.DecisionClient | None
) -> decision.CredentialSnapshot:
    """The one credential snapshot of this decision (T05j).

    A client that already pinned one (the CLI resolves it once per command,
    before the book gate) *is* the authority: the decision reuses that exact
    object instead of resolving a second, later value. Without a pin the
    credential is resolved here - after the per-DP budget clone and before any
    known-set gate, the capture scope or the client - and exactly once.

    T05n: a pinned object must implement the frozen :class:`decision.
    CredentialSnapshot` contract. A duck object cannot prove this decision's
    known set, and continuing with it would either send unprovable material or
    shrink the set to empty; refuse before any capture/send instead.

    T05o: the class alone is not the contract either - a ``CredentialSnapshot``
    constructed directly (``frozen_known_values() is None``) froze nothing, so
    its known set is equally unprovable. Refuse it at this entry before the
    gates, the capture scope or the transport; the class itself stays usable as
    non-send data.
    """
    pinned = (
        getattr(client, "_pinned_credential_snapshot", None) if client is not None else None
    )
    if pinned is not None:
        if not isinstance(pinned, decision.CredentialSnapshot):
            raise decision.DecisionInputError(
                "refusing a foreign credential snapshot pinned on the client: this "
                "decision's known-secret gate/capture requires "
                "decision.CredentialSnapshot (frozen cfg/env/Authorization values and "
                f"the legacy timi leg), got {type(pinned).__name__}; nothing is sent"
            )
        if pinned.frozen_known_values() is None:
            raise decision.DecisionInputError(
                "refusing a credential snapshot pinned on the client without a "
                "frozen known set: this decision's known-secret gate/capture "
                "requires decision.credential_snapshot() (the cfg/env/"
                "Authorization values and the legacy timi leg frozen at "
                "creation); the pinned object was constructed directly and "
                "cannot prove any of them, so nothing is sent"
            )
        return pinned
    return decision.credential_snapshot(cfg)


@contextlib.contextmanager
def _bound_credential_snapshot(
    client: decision.DecisionClient | None, snapshot: decision.CredentialSnapshot | None
):
    """Bind this decision's snapshot to a caller-owned client for one call.

    An unpinned caller client would resolve its own credential at call time and
    could send a value the gate and the capture set never saw. The pin is set
    for the transport call only and restored in ``finally``; a client the caller
    already pinned is left untouched (it supplied the snapshot), so one decision
    can never rewrite the credential of the next one.
    """
    if client is None or snapshot is None:
        yield
        return
    if getattr(client, "_pinned_credential_snapshot", None) is not None:
        yield
        return
    try:
        client._pinned_credential_snapshot = snapshot
    except AttributeError as exc:  # pragma: no cover - a foreign client object
        raise decision.DecisionInputError(
            "refusing an unprovable transport: this decision cannot bind its "
            "credential snapshot to the caller-owned client, so the sent "
            "Authorization could differ from the gate/capture set; construct "
            "the client with credential_snapshot=decision.credential_snapshot(cfg)"
        ) from exc
    try:
        yield
    finally:
        client._pinned_credential_snapshot = None


def _capture_scope(
    capture: _DecisionCapture,
    *,
    project: pathlib.Path,
    cfg: decision.DecisionConfig | None,
    client: decision.DecisionClient | None,
    dp_point: DecisionPoint,
    decision_id: str,
    trigger: Trigger,
    snapshot: decision.CredentialSnapshot | None = None,
) -> tuple[Any | None, str]:
    """``(scope, channel)`` for this decision; a *fresh* production scope per call.

    The production scope is created here and carries a freshly built credential
    redactor (T03 review F-3: a rotated credential must never be captured through
    a reused redactor). A caller-provided client scope wins - it is the already
    explicit, already isolated ledger of that client - so no second scope can
    split one call across two files.

    ``snapshot`` (T05j) is this decision's single credential object: the
    production redactor is built from it, so the captured text and the sent
    ``Authorization`` cannot diverge and no second resolution happens here. A
    caller-owned scope keeps its own redactor; the caller's filter was verified
    against this snapshot before this function ran.
    """
    observation = capture.observation
    if observation is not None:
        return observation.scope, "test-scope"
    client_scope = getattr(client, "_wire_scope", None) if client is not None else None
    if client_scope is not None:
        kind = getattr(client_scope, "scope_kind", "production")
        return client_scope, ("test-scope" if kind == "test" else "production-scope")
    wire = _wire_api()
    if wire is None:
        return None, "module-unavailable"
    try:
        redactor = (
            decision.credential_redactor(
                cfg, extra_secrets=known_secret_superset(snapshot), snapshot=snapshot
            )
            if cfg is not None
            else None
        )
        scope = wire.production_scope(
            project,
            origin="decide",
            decision_id=decision_id,
            dp=dp_point.id,
            key=trigger.key or None,
            task_key=trigger.task_key,
            redact=redactor,
        )
    except Exception:  # noqa: BLE001 - a scope failure never blocks a production decision
        return None, "scope-error"
    return scope, "production-scope"


def decide_for(
    dp_id: str,
    trigger: Trigger | Mapping | None = None,
    project_dir: pathlib.Path | str = ".",
    *,
    client: decision.DecisionClient | None = None,
    config: decision.DecisionConfig | None = None,
    backend: decision.DecisionBackend | None = None,
    points_config: PointsConfig | None = None,
    min_confidence: float | None = None,
    archive: bool = True,
    intent: str = "act",
    observation: Observation | None = None,
    questions: Mapping[str, Mapping] | None = None,
) -> DecisionOutcome:
    """The only entry point for decision points (design §2.3).

    Step order, with the two hard constraints called out:

    1. unknown ``dp_id`` -> raise ``decision.DecisionInputError`` (exit 2);
    2. ``enabled=false`` -> ``escalate("disabled")``, returned **before**
       ``build_state`` / ``_encode_state`` / backend resolution, so this path
       cannot spawn, cannot touch the network and cannot read L2-ish state;
    3. ``mode`` read and validated against the registry;
    4. transport budget/availability -> ``escalate("unavailable")``;
    5. ``build_state`` + required fields -> ``escalate("input-incomplete")``;
    6. canonical size > MAX_STATE_BYTES -> drop optional L1, halve required, then
       ``escalate("input-oversize")`` if still oversized;
    7. ``DecisionClient.decide`` -> ``available=false`` -> ``escalate("unavailable")``;
    8. unusable answer (empty / missing qid / illegal value) ->
       ``escalate("low-confidence")``; an ``api``-scored confidence below the
       floor escalates the same way, while any other ``confidence_source`` is
       ignored entirely (neither gates nor escalates, design D-031);
    9. ``mode=suggest`` -> archive ``acted=false``, return the suggestion;
       ``intent="answer"`` takes the same branch for ``mode=auto`` (design
       D-035): the advice is archived as ``acted=false`` and no executor runs;
    10. ``mode=auto`` + executor -> act, ``acted=true`` + ``actual_action``;
    11. executor raised/returned nothing -> ``escalate("over-authority")``.

    ``intent`` is ``act`` (default, byte-identical pre-D-035 behaviour) or
    ``answer`` (skip steps 10/11; the answer plus ``decision_id``/``mode``/
    ``state_digest`` is what the caller wanted). An unknown intent is an
    argument error like an unknown dp id (exit 2 at the CLI).

    ``observation`` (card T05) is the explicit human observe-only submission
    seam. It is a paired contract - ``intent="answer"``, ``archive=False``, an
    isolated ``test`` scope with its own ``evidence_path`` - validated before
    anything else runs, and it bypasses **only** step 2 (the per-DP
    ``enabled``/P0 gate): the global transport switch, credentials, the typed
    input gate, the budget, the answer check and the confidence gate stay in
    force, and the executor is never reached. The returned outcome carries the
    observation facts, the pure authorization preview and the capture facts
    (``capture_channel``/``capture_status``/``archive_state``/``call_id``/
    ``snapshot_ref``).

    ``questions`` (card T10) is the optional observation-only override of the
    registered question set: the DP's own ids, legal types/instructions/
    criteria and the legal choice set are validated by
    :func:`resolve_question_override`, only validated observation text is taken from it
    and everything else is regenerated from the registry (dp3: from
    ``state.handling_options``). Without it the registry questions are used
    unchanged, so every existing caller keeps its behaviour.
    """
    # Step 1 — unknown ids fail loudly (never a silent degradation).
    dp_point = get_decision_point(dp_id)
    if intent not in INTENTS:
        raise decision.DecisionInputError(
            f"intent {intent!r} is not one of {INTENTS}"
        )
    trigger_obj = _coerce_trigger(trigger)
    project = _coerce_project_dir(project_dir)
    _validate_observation(
        observation, intent=intent, archive=archive, client=client, project=project
    )
    if observation is not None and not _wire_ready():
        raise decision.DecisionInputError(
            "observation requires a working wire capture module (record_event/scope API); "
            "refusing to fall back to an unwatched production path"
        )
    capture = _DecisionCapture(observation=observation, intent=intent)
    trace = _ArchiveTrace()
    try:
        outcome = _decide_for(
            dp_point,
            trigger_obj,
            project,
            client=client,
            config=config,
            backend=backend,
            points_config=points_config,
            min_confidence=min_confidence,
            archive=archive,
            intent=intent,
            questions_override=questions,
            capture=capture,
            trace=trace,
        )
    except Exception:
        # Record what is known (archive=failed when the archive raised) and
        # re-raise the original exception unchanged (design §4.4).
        capture.finish(trace, outcome=None)
        raise
    return replace(outcome, **capture.finish(trace, outcome=outcome))


def _decide_for(
    dp_point: DecisionPoint,
    trigger_obj: Trigger,
    project: pathlib.Path,
    *,
    client: decision.DecisionClient | None,
    config: decision.DecisionConfig | None,
    backend: decision.DecisionBackend | None,
    points_config: PointsConfig | None,
    min_confidence: float | None,
    archive: bool,
    intent: str,
    questions_override: Mapping[str, Mapping] | None,
    capture: _DecisionCapture,
    trace: _ArchiveTrace,
) -> DecisionOutcome:
    """Steps 2..11 of :func:`decide_for` (argument contract already validated)."""
    decision_id = f"{dp_point.id}:{trigger_obj.resolved_id()}"

    # Step 2 — authorization gate. Nothing expensive may run before this return.
    view = points_config if points_config is not None else load_points_config(project)
    effective = view.effective(dp_point)
    if not effective.enabled:
        if capture.observation is None:
            _LOGGER.debug(
                "decision point %s disabled (source=%s, layer=%s); escalating without spawn",
                dp_point.id,
                effective.source,
                view.layer,
            )
            return _outcome(
                dp_point=dp_point,
                trigger=trigger_obj,
                status="escalated",
                escalated_reason="disabled",
                detail=f"{decision_id}: disabled by config (source={effective.source}, layer={view.layer})",
                mode=effective.mode,
            )
        # The single observation exception (design §5.3 / AC-010): an explicit
        # human observe-only submission records the bypass and continues, but the
        # authorization facts stay visible on the outcome preview.
        capture.bypassed = True
        _LOGGER.debug(
            "decision point %s disabled (source=%s, layer=%s); observation bypasses "
            "only this gate",
            dp_point.id,
            effective.source,
            view.layer,
        )

    # Step 3 — mode: config value wins, registry default is the fallback.
    mode = effective.mode if effective.mode in MODES else dp_point.default_mode
    capture.mode = mode

    # Step 4 — transport availability/budget (`.mw/decide.json` owns transport).
    cfg: decision.DecisionConfig | None = config
    if client is not None:
        cfg = client.cfg
    elif cfg is None:
        cfg, _cfg_error = decision.DecisionConfig.from_project(project)
    transport_configured = cfg is not None and cfg.is_configured
    # The shared, pure authorization preview is computed from the *real* gates
    # (per-dp authorization, this transport state, the effective mode and the
    # registered executor), so it can never claim an act production would refuse.
    capture.preview = _preview_of(
        dp_point,
        effective,
        config_layer=view.layer,
        mode=mode,
        transport_configured=transport_configured,
    )
    if not transport_configured:
        # Nothing is sent and no known-set gate runs here (no book gate, no
        # transport call), so this refusal keeps the pre-T05j capture facts: the
        # scope is built from this cfg, without a credential snapshot pin.
        scope, channel = _capture_scope(
            capture,
            project=project,
            cfg=cfg,
            client=client,
            dp_point=dp_point,
            decision_id=decision_id,
            trigger=trigger_obj,
        )
        capture.attach(
            scope,
            channel,
            dp_id=dp_point.id,
            decision_id=decision_id,
            questions_version=dp_point.questions_version,
        )
        detail = (cfg.config_error if cfg is not None else None) or (
            "decision transport disabled (.mw/decide.json missing or enabled=false)"
        )
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="unavailable",
            detail=f"{decision_id}: {detail}",
            mode=mode,
            transport_reason=decision.REASON_DISABLED,
        )

    # Step 4b — effective per-dp policy (AC-016): row > `.mw/decide.json` >
    # builtin. Resolved here, after the transport config exists (it is the middle
    # layer) and before the first archive row (which echoes it, D-051).
    policy = resolve_policy(dp_point.id, view.row(dp_point.id), cfg)
    cfg = _apply_per_dp_budget(cfg, policy)
    # The decision's own policy echo: captured with the same values the archive
    # row reports, so the persisted snapshot and the row cannot disagree (T10).
    capture.policy = policy

    # Step 4c — the one credential snapshot of this decision (T05j). Taken after
    # the per-DP budget clone (the object the transport sits on) and before any
    # known-set gate, the capture scope and the client: the gate set, the
    # captured text and the sent Authorization are one frozen value, and the
    # next decision resolves a fresh one. A caller-pinned snapshot (the CLI's
    # per-command object) wins here instead of being resolved a second time.
    snapshot = _decision_credential_snapshot(cfg, client)
    # T05l: freeze the complete known-safe set of this decision (cfg/extras, the
    # actual Authorization, the legacy timi leg, the env heuristics) on this
    # snapshot, once. Every face below - the known-set gates, the production
    # capture redactor, the caller-owned scope verification and the client's own
    # redactor - reads this one tuple, so a credential rotated mid-call cannot
    # make two faces disagree. The next decision resolves afresh (no cache).
    freeze = getattr(snapshot, "known_superset", None)
    if callable(freeze):
        freeze()
    scope, channel = _capture_scope(
        capture,
        project=project,
        cfg=cfg,
        client=client,
        dp_point=dp_point,
        decision_id=decision_id,
        trigger=trigger_obj,
        snapshot=snapshot,
    )
    capture.attach(
        scope,
        channel,
        dp_id=dp_point.id,
        decision_id=decision_id,
        questions_version=dp_point.questions_version,
    )
    discovery_error = getattr(snapshot, "discovery_error", None)
    if discovery_error:
        # Fail closed (T05l): the known-secret discovery raised, so this
        # decision's set is incomplete and neither the gates nor the capture
        # could prove the material safe. Zero send, zero snapshot; the detail
        # names the failure kind only (never the message or a value).
        capture.material_refused = True
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="unavailable",
            detail=(
                f"{decision_id}: {discovery_error}; refusing to send "
                "(known-secret set incomplete)"
            ),
            mode=mode,
        )

    # Step 5 — structured state + required fields (missing => never sent).
    try:
        built = dp_point.build_state(trigger_obj)
    except Exception as exc:  # noqa: BLE001 - a builder bug must escalate, not crash
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="input-incomplete",
            detail=f"{decision_id}: build_state raised {type(exc).__name__}",
            mode=mode,
        )
    if not isinstance(built, Mapping):
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="input-incomplete",
            detail=f"{decision_id}: build_state returned {type(built).__name__}, not a mapping",
            mode=mode,
        )
    state = dict(built)
    missing = _missing_required(state, dp_point.id)
    if missing:
        # A missing/null/blank required field is illegal material exactly like a
        # typed refusal (step 5b): it is never sent and never stored as a
        # snapshot, while the decision-end row keeps the refusal fact (T05k N1).
        capture.material_refused = True
        capture.remember_state(state, questions=None, state_digest=None)
        # Field names only: values may be L2 material (spec §5.4).
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="input-incomplete",
            detail=f"{decision_id}: missing required state fields: {', '.join(missing)}",
            mode=mode,
            state_digest=_state_digest(state),
        )
    # Step 5b — the typed business contract of this dp (T05b F1): type / enum /
    # array caps / element lengths / cross-field facts plus the closed key set,
    # from the single registry authority. Before T05b only ``check_book``
    # enforced this, so every non-book producer (and the observation seam) sent
    # material production would refuse. Refused material is never snapshotted
    # and never reaches the budget or the transport.
    contract_issues = state_field_issues(dp_point.id, state)
    # Identity values, shared with the book (T05c N2): an explicit wrong
    # dp/version is illegal material, while a missing one keeps the builder's
    # own default semantics.
    contract_issues += state_identity_issues(dp_point.id, state)
    if dp_point.id in REQUIRED_STATE_FIELDS:
        # A dp with a declared contract has a closed key set; an ad-hoc dp
        # injected by tests has no declared paths, so there is nothing to close.
        # The display paths are sanitized with this call's actual known-secret
        # set (F3/T05e), built only on the refusal path so a legal decision does
        # not resolve a credential it never echoes.
        #
        # ``context`` is optional engineered input, never decision material: it
        # is legal when this dp still has a context slot producer, or when the dp
        # has a model allowlist (identity/local facts are stripped there, so the
        # block rides along locally and is fitted by ``_fit_state``). The four
        # rewritten dps declare no slot, so they keep the strict closed set.
        allow_context = dp_point.id not in MODEL_STATE_FIELDS or bool(
            decision_context.slot_names_for(dp_point.id)
        )
        unknown_keys = state_unknown_key_issues(
            dp_point.id, state, allow_context=allow_context
        )
        if unknown_keys:
            unknown_keys = state_unknown_key_issues(
                dp_point.id,
                state,
                allow_context=allow_context,
                redactor=command_known_secret_redactor(cfg, snapshot=snapshot),
            )
        contract_issues += unknown_keys
    if contract_issues:
        capture.material_refused = True
        capture.remember_state(state, questions=None, state_digest=None)
        # Paths and registry-owned constraint text only (no free-text values).
        detail = "; ".join(f"{path}: {issue}" for path, issue in contract_issues)
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="input-incomplete",
            detail=f"{decision_id}: illegal state ({detail})",
            mode=mode,
            state_digest=_state_digest(state),
        )
    questions = questions_map(dp_point)
    if questions_override is not None:
        # Observation-only question override (T10): validated against this dp's
        # own question mapping and the state that would be sent. A conflict is
        # illegal input like any other: zero send, no snapshot, paths only.
        override = resolve_question_override(dp_point, questions_override, state)
        if override.issues:
            capture.material_refused = True
            detail = "; ".join(f"{path}: {issue}" for path, issue in override.issues)
            return _outcome(
                dp_point=dp_point,
                trigger=trigger_obj,
                status="escalated",
                escalated_reason="input-incomplete",
                detail=f"{decision_id}: illegal questions ({detail})",
                mode=mode,
                state_digest=_state_digest(state),
            )
        assert override.questions is not None
        questions = override.questions
    if not questions:
        capture.remember_state(state, questions=None, state_digest=None)
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="input-incomplete",
            detail=f"{decision_id}: registry has no question set",
            mode=mode,
            state_digest=_state_digest(state),
        )

    # Step 6 — the single model projection, then the canonical budget
    # (drop optional L1, then halve the legacy truncatable paths, then refuse).
    # The projected object is the material that is actually sent and digested,
    # so identity/association facts can never ride along (design D001).
    # ``send_state`` is the one authority the observation preview reuses (T10).
    state, dropped_paths, size = send_state(dp_point.id, state)
    digest = _state_digest(state)
    # The material that is actually sent (post-truncation) is what gets
    # snapshotted; the rendered candidate enum belongs to the same call.
    capture.remember_state(state, questions=questions, state_digest=digest)
    if size > MAX_STATE_BYTES:
        dropped_note = f"; dropped: {', '.join(dropped_paths)}" if dropped_paths else ""
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="input-oversize",
            detail=f"{decision_id}: state is {size}B > {MAX_STATE_BYTES}B{dropped_note}",
            mode=mode,
            state_digest=digest,
            truncated=dropped_paths,
        )

    # Step 6b — a caller-supplied book is a material-of-record claim (T05b F2):
    # it must be this dp's book, pass `check_book` and carry the state that is
    # actually sent. A refused book sends nothing, stores no snapshot and leaves
    # no book_ref behind.
    book = capture.observation.book if capture.observation is not None else None
    if book is not None:
        book_issues = _observation_book_issues(
            book,
            dp_point=dp_point,
            sent_state=state,
            project=project,
            redactor=command_known_secret_redactor(cfg, snapshot=snapshot),
        )
        if book_issues:
            capture.material_refused = True
            detail = "; ".join(f"{path}: {issue}" for path, issue in book_issues)
            return _outcome(
                dp_point=dp_point,
                trigger=trigger_obj,
                status="escalated",
                escalated_reason="input-incomplete",
                detail=f"{decision_id}: observation book refused ({detail})",
                mode=mode,
                state_digest=digest,
                truncated=dropped_paths,
            )

    # Step 7 — one transport call; `decision.DecisionClient` never raises here.
    # A caller-owned capture ledger must be able to prove this call's actual
    # credential safe *before* the transport runs: a filter that misses it would
    # store the sent value raw. Material that was already refused never reaches
    # here, so this never displaces a business refusal.
    coverage_issue = _caller_scope_coverage_issue(
        _caller_owned_scope(capture, client), snapshot, cfg=cfg
    )
    if coverage_issue is not None:
        # An unprovable capture stores nothing: no material of record for this
        # call (T05l), and the caller's redactor/client stay untouched.
        capture.material_refused = True
        raise decision.DecisionInputError(coverage_issue)
    if client is None:
        client = decision.DecisionClient(
            cfg=cfg, backend=backend, project_root=project, credential_snapshot=snapshot
        )
    wire = _wire_api()
    # A caller-owned client is bound to this decision's snapshot for exactly one
    # call (T05j): it must send the value the gate and the capture set saw.
    with _bound_credential_snapshot(client, snapshot):
        if wire is not None and capture.scope is not None:
            # The client binds its own ``call``; this only hands it this decision's
            # scope, so attempt/call rows and the decision-end row share one ledger.
            with wire.scope_context(capture.scope):
                response = client.decide(state, questions, dp=dp_point.id)
        else:
            response = client.decide(state, questions, dp=dp_point.id)
    capture.record_call(client)
    if not response.get("available"):
        transport_reason = response.get("reason") or decision.REASON_UPSTREAM_ERROR
        archived, replayed = _maybe_archive(
            archive,
            trace=trace,
            dp_point=dp_point,
            trigger=trigger_obj,
            project_dir=project,
            state=state,
            mode=mode,
            response=response,
            authority="human",
            escalated_reason="unavailable",
            acted=False,
            actual_action=None,
            note=f"transport {transport_reason}",
            policy=policy,
        )
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="unavailable",
            archived=archived,
            detail=f"{decision_id}: transport unavailable ({transport_reason})",
            mode=mode,
            state_digest=digest,
            transport_reason=transport_reason,
            response=response,
            truncated=dropped_paths,
            replayed=replayed,
        )

    answers = response.get("answers") or {}
    confidence = _aggregate_confidence(answers)
    threshold = _confidence_threshold(cfg, min_confidence, policy)
    confidence_source = response.get("confidence_source")
    # The *effective* threshold is the decision's persisted fact (T10/AC-023):
    # the archive policy echo and the snapshot carry the value this decision
    # actually applied (an explicit ``min_confidence`` argument wins over the
    # resolved policy), so a reader never has to re-resolve the current config.
    policy = {**policy, "min_confidence": threshold}
    capture.policy = policy

    # Step 8 — input side first: a decision can only be acted on when every
    # registry question carries an acceptable value. No usable answer is the one
    # failure that is genuinely a confidence problem (design D-031).
    defect = _unusable_answer(answers, questions, resolve_dynamic_choices(questions, state))
    if defect is not None:
        # The transport was available but the payload is not an answer, so the
        # archive row must not claim one (available=false + a frozen reason).
        no_answer_response = dict(
            response, available=False, reason=decision.REASON_BAD_RESPONSE, answers=None
        )
        archived, replayed = _maybe_archive(
            archive,
            trace=trace,
            dp_point=dp_point,
            trigger=trigger_obj,
            project_dir=project,
            state=state,
            mode=mode,
            response=no_answer_response,
            authority="human",
            escalated_reason="low-confidence",
            acted=False,
            actual_action=None,
            note=f"no usable answer ({defect})",
            policy=policy,
        )
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="low-confidence",
            archived=archived,
            detail=f"{decision_id}: no usable answer ({defect})",
            mode=mode,
            state_digest=digest,
            response=response,
            truncated=dropped_paths,
            replayed=replayed,
        )

    # Step 8 — output side: only an API-scored confidence is a real gate. Under
    # DS-9 *whether* a point may run automatically is a config question, so a
    # self-reported / unknown source is ignored entirely: it neither gates nor
    # escalates, otherwise every B2 (``model-self-report``) P2 decision would be
    # escalated to a human and auto mode would never take effect.
    if confidence_source == decision.CONFIDENCE_SOURCE_API and (
        confidence is None or confidence < threshold
    ):
        archived, replayed = _maybe_archive(
            archive,
            trace=trace,
            dp_point=dp_point,
            trigger=trigger_obj,
            project_dir=project,
            state=state,
            mode=mode,
            response=response,
            authority="human",
            escalated_reason="low-confidence",
            acted=False,
            actual_action=None,
            note=f"confidence={confidence}",
            policy=policy,
        )
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="low-confidence",
            answer=answers,
            archived=archived,
            detail=f"{decision_id}: confidence={confidence} < min_confidence={threshold}",
            mode=mode,
            state_digest=digest,
            response=response,
            truncated=dropped_paths,
            replayed=replayed,
        )

    # Step 9 — suggest mode: archive the advice, act on nothing. ``intent="answer"``
    # rides the same branch for ``mode=auto``: an answer call site wants advice,
    # never an executor, so steps 10/11 are skipped here (design D-035). The row
    # still says ``acted=false``, so AC-011 holds on the answer path too.
    if mode == "suggest" or intent == "answer":
        archived, replayed = _maybe_archive(
            archive,
            trace=trace,
            dp_point=dp_point,
            trigger=trigger_obj,
            project_dir=project,
            state=state,
            mode=mode,
            response=response,
            authority="advisory",
            escalated_reason=None,
            acted=False,
            actual_action=None,
            note="mode=suggest" if mode == "suggest" else "intent=answer",
            policy=policy,
        )
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="suggested",
            answer=answers,
            archived=archived,
            detail=(
                f"{decision_id}: suggestion only (mode=suggest), nothing acted on"
                if mode == "suggest"
                else f"{decision_id}: answer only (mode={mode}), nothing acted on"
            ),
            mode=mode,
            state_digest=digest,
            response=response,
            truncated=dropped_paths,
            replayed=replayed,
            answers=answers,
            confidence_source=response.get("confidence_source"),
            latency_ms=int(response.get("latency_ms") or 0),
        )

    # Step 10/11 — auto mode: execute, or escalate when the executor cannot.
    if dp_point.executor is None:
        archived, replayed = _maybe_archive(
            archive,
            trace=trace,
            dp_point=dp_point,
            trigger=trigger_obj,
            project_dir=project,
            state=state,
            mode=mode,
            response=response,
            authority="human",
            escalated_reason="over-authority",
            acted=False,
            actual_action=None,
            note="no executor",
            policy=policy,
        )
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="over-authority",
            answer=answers,
            archived=archived,
            detail=f"{decision_id}: mode=auto but no executor is registered",
            mode=mode,
            state_digest=digest,
            response=response,
            truncated=dropped_paths,
            replayed=replayed,
        )
    try:
        actual_action = dp_point.executor(answers, trigger_obj)
    except Exception as exc:  # noqa: BLE001 - step 11: executor failure => human
        archived, replayed = _maybe_archive(
            archive,
            trace=trace,
            dp_point=dp_point,
            trigger=trigger_obj,
            project_dir=project,
            state=state,
            mode=mode,
            response=response,
            authority="human",
            escalated_reason="over-authority",
            acted=False,
            actual_action=None,
            note=f"executor raised {type(exc).__name__}",
            policy=policy,
        )
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="over-authority",
            answer=answers,
            archived=archived,
            detail=f"{decision_id}: executor raised {type(exc).__name__}",
            mode=mode,
            state_digest=digest,
            response=response,
            truncated=dropped_paths,
            replayed=replayed,
        )
    if not isinstance(actual_action, str) or not actual_action.strip():
        archived, replayed = _maybe_archive(
            archive,
            trace=trace,
            dp_point=dp_point,
            trigger=trigger_obj,
            project_dir=project,
            state=state,
            mode=mode,
            response=response,
            authority="human",
            escalated_reason="over-authority",
            acted=False,
            actual_action=None,
            note="executor returned no action",
            policy=policy,
        )
        return _outcome(
            dp_point=dp_point,
            trigger=trigger_obj,
            status="escalated",
            escalated_reason="over-authority",
            answer=answers,
            archived=archived,
            detail=f"{decision_id}: executor returned no usable actual_action",
            mode=mode,
            state_digest=digest,
            response=response,
            truncated=dropped_paths,
            replayed=replayed,
        )

    archived, replayed = _maybe_archive(
        archive,
        trace=trace,
        dp_point=dp_point,
        trigger=trigger_obj,
        project_dir=project,
        state=state,
        mode=mode,
        response=response,
        authority="binding",
        escalated_reason=None,
        acted=True,
        actual_action=actual_action,
        policy=policy,
    )
    return _outcome(
        dp_point=dp_point,
        trigger=trigger_obj,
        status="acted",
        answer=answers,
        actual_action=actual_action,
        archived=archived,
        detail=f"{decision_id}: acted ({actual_action})",
        mode=mode,
        state_digest=digest,
        response=response,
        truncated=dropped_paths,
        replayed=replayed,
    )


def _state_digest(state: Mapping) -> str:
    """``sha256(_encode_state(state))[:16]`` — computed here only (design D-004)."""
    return hashlib.sha256(decision._encode_state(state)).hexdigest()[:16]


def _confidence_threshold(
    cfg: decision.DecisionConfig,
    override: float | None,
    policy: Mapping | None = None,
) -> float:
    """Threshold precedence: explicit argument > resolved policy > legacy chain.

    The resolved policy (AC-016) already encodes per-dp row > ``.mw/decide.json``
    > :data:`MIN_CONFIDENCE`, so the legacy ``cfg.extras`` read below only serves
    callers that have no resolved policy at hand.
    """
    if isinstance(override, (int, float)) and not isinstance(override, bool):
        return float(override)
    if policy is not None:
        resolved = policy.get("min_confidence")
        if isinstance(resolved, (int, float)) and not isinstance(resolved, bool):
            return float(resolved)
    extra = cfg.extras.get("min_confidence") if isinstance(cfg.extras, Mapping) else None
    if isinstance(extra, (int, float)) and not isinstance(extra, bool):
        return float(extra)
    return MIN_CONFIDENCE


def _apply_per_dp_budget(
    cfg: decision.DecisionConfig, policy: Mapping
) -> decision.DecisionConfig:
    """Override the two budget keys of ``cfg`` with the effective policy values.

    Only the per-call clone changes, so an explicit ``config=`` argument stays
    untouched for the caller and every other dp keeps the global budget. Values
    equal to the global ones return ``cfg`` unchanged (no needless copy)."""
    timeout_s = policy.get("timeout_s")
    max_questions = policy.get("max_questions")
    updates: dict[str, Any] = {}
    if isinstance(timeout_s, (int, float)) and not isinstance(timeout_s, bool):
        if float(cfg.timeout_s) != float(timeout_s):
            updates["timeout_s"] = float(timeout_s)
    if isinstance(max_questions, int) and not isinstance(max_questions, bool):
        if int(cfg.max_questions) != max_questions:
            updates["max_questions"] = max_questions
    if not updates:
        return cfg
    return replace(cfg, **updates)
