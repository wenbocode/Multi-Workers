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
    "ACTOR_ID_MAX_BYTES",
    "ACTOR_KINDS",
    "ARCHIVE_STATES",
    "CAPTURE_CHANNELS",
    "DECISIONS_RELATIVE_PATH",
    "DECIDE_POINTS_RELATIVE_PATH",
    "DP_REGISTRY",
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

#: Structured input budget (spec §5.4 / design D-019); transport keeps its own
#: 16 KiB ceiling in ``decision.DecisionConfig.max_state_bytes``.
MAX_STATE_BYTES = 2000
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
#: Number of registered decision points (spec §4 / design §2.1; dp25 added by
#: spec §15 AC-027).
EXPECTED_DP_COUNT = 25

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
    )


#: The 25 decision points: dp1..dp24 from spec.md §4 plus
#: ``dp25-signoff-conclusion`` (spec.md §15 AC-027, ids are frozen).
#:
#: ``dp13-commit-release`` carries the composite tier cell "P1/P0" in spec §4
#: (commit = P1, release/version = P0) and is registered as **P0** here: the
#: fail-closed reading of a composite cell, since the P0 sub-decision has
#: irreversible external effects. See the card report's residual section — the
#: spec count line (P2=9 / P1=6 / P0=9) double-counts dp13 and does not add up
#: to 24 distinct ids.
DP_REGISTRY: tuple[DecisionPoint, ...] = (
    _point(
        dp_id="dp1-dispatch-type",
        tier="P2",
        description="派发 type/角色/范围",
        questions=(
            {
                "id": "triage_type",
                "type": "choice",
                "choices": ["coding", "research", "review"],
                "instructions": "这个任务应该派给哪一类 worker？",
                "labels": {
                    "coding": "需要写代码或改代码或跑命令",
                    "research": "只做检索取证不改代码",
                    "review": "审计别人已完成的产出",
                },
            },
            {
                "id": "triage_risk",
                "type": "choice",
                "choices": ["low", "mid", "high"],
                "instructions": "这个任务做错了的代价有多大？",
                "labels": {
                    "low": "可随时撤销且不影响他人",
                    "mid": "影响同一 key 的其它任务或需要返工",
                    "high": "跨会话或跨 key 冲突或不可逆（发布、删除、凭据变更）",
                },
            },
        ),
        executor=_unwired_executor("dp1-dispatch-type"),
    ),
    _point(
        dp_id="dp2-checkpoint-split",
        tier="P2",
        description="checkpoint 拆/收/直执",
        questions=(
            {
                "id": "checkpoint_action",
                "type": "choice",
                "choices": ["narrow", "split", "direct-exec", "escalate"],
                "instructions": "以当前进度，这一步该继续、拆小、直接执行还是上抛人？",
                "labels": {
                    "narrow": "收窄到剩余预算内能完成的一小块",
                    "split": "拆成多个任务重派",
                    "direct-exec": "PM 自己直接做完",
                    "escalate": "风险高到必须问人",
                },
            },
        ),
        executor=_unwired_executor("dp2-checkpoint-split"),
    ),
    _point(
        dp_id="dp3-worker-clarify",
        tier="P2",
        description="worker 澄清（dp3a 事实可查 / dp3b 意图需人 / dp3c 已表态复用）",
        questions=(
            {
                "id": "answer_kind",
                "type": "choice",
                "choices": ["fact", "intent", "reuse"],
                "instructions": (
                    "这条澄清属于哪一类：能凭已给材料查到答案、需要人的意图判断、还是已有表态可复用？"
                ),
                "labels": {
                    "fact": "答案存在于给出的状态或候选条目里",
                    "intent": "取决于人想要什么（材料里没有）",
                    "reuse": "之前的表态或产物已经回答了它",
                },
            },
            {
                "id": "answerable",
                "type": "noul",
                "instructions": "仅凭 state 里给出的内容与候选条目，能否确定地回答上面这条澄清？",
                "criteria": {
                    "true": "材料里直接有答案",
                    "false": "材料不足或需要人表态",
                },
            },
            {
                "id": "candidate",
                "type": "choice",
                "dynamic_choices": "local_candidates",
                "instructions": "state.local_candidates 里哪一条最可能承载答案？",
            },
        ),
        executor=_unwired_executor("dp3-worker-clarify"),
    ),
    _point(
        dp_id="dp4-failure-handling",
        tier="P1",
        description="失败处置",
        questions=(
            {"id": "failure_action", "type": "choice", "choices": ["retry", "rework", "escalate"]},
        ),
    ),
    _point(
        dp_id="dp5-test-triage",
        tier="P2",
        description="测试失败归类",
        questions=(
            {
                "id": "test_category",
                "type": "choice",
                "choices": ["baseline-env", "flaky", "regression", "unknown"],
            },
        ),
        executor=_unwired_executor("dp5-test-triage"),
    ),
    _point(
        dp_id="dp6-qg-verdict",
        tier="P1",
        description="QG 结论处置",
        questions=(
            {"id": "qg_verdict", "type": "choice", "choices": ["pass", "fix", "reopen"]},
        ),
    ),
    _point(
        dp_id="dp7-gate-failure",
        tier="P2",
        description="相位门禁失败",
        questions=(
            {
                "id": "gate_cause",
                "type": "choice",
                "choices": ["missing-evidence", "stale-verdict", "config", "unknown"],
            },
        ),
        executor=_unwired_executor("dp7-gate-failure"),
    ),
    _point(
        dp_id="dp8-scope-change",
        tier="P0",
        description="变更范围",
        p0_consequences="扩面会改动他人写面外的文件，跨会话冲突不可在一次重派内撤回",
        questions=(
            {
                "id": "scope_decision",
                "type": "choice",
                "choices": ["keep", "narrow", "expand"],
                "instructions": "这次变更应该保持、收窄还是扩大范围？",
                "labels": {
                    "keep": "按原范围",
                    "narrow": "缩小到原范围内的一子集",
                    "expand": "扩大到原范围之外",
                },
            },
            {
                "id": "scope_reason",
                "type": "choice",
                "choices": [
                    "outside-write-face",
                    "cross-key-conflict",
                    "scope-creep",
                    "unclear-boundary",
                ],
                "instructions": "为什么需要或不需要改范围？",
                "labels": {
                    "outside-write-face": "目标文件在授权写面之外",
                    "cross-key-conflict": "会与他人写面重叠",
                    "scope-creep": "需求本身扩大了",
                    "unclear-boundary": "边界不清需要先界定",
                },
            },
        ),
    ),
    _point(
        dp_id="dp9-model-select",
        tier="P2",
        description="模型/降级选择",
        questions=(
            {"id": "model_class", "type": "choice", "choices": ["primary", "fallback", "degrade"]},
        ),
        executor=_unwired_executor("dp9-model-select"),
    ),
    _point(
        dp_id="dp10-dependency",
        tier="P1",
        description="依赖升级",
        questions=(
            {"id": "dependency_decision", "type": "choice", "choices": ["upgrade", "hold", "pin"]},
        ),
    ),
    _point(
        dp_id="dp11-credential",
        tier="P0",
        description="凭据/权限",
        p0_consequences="凭据隔离一旦放宽会外溢到其他 provider，泄露不可撤销",
        questions=(
            {"id": "credential_action", "type": "choice", "choices": ["isolate", "rotate", "deny"]},
        ),
    ),
    _point(
        dp_id="dp12-destructive",
        tier="P0",
        description="破坏性操作",
        p0_consequences="删除/覆盖他人工作区文件或历史不可恢复，属外部副作用",
        questions=(
            {"id": "destructive_action", "type": "choice", "choices": ["proceed", "block", "ask-human"]},
        ),
    ),
    _point(
        dp_id="dp13-commit-release",
        tier="P0",
        description="提交(P1) / 发布+版本号(P0)",
        p0_consequences="发布与版本号推进对外可见且不可撤回（tag 已推送即不可重发同一版本）",
        questions=(
            {
                "id": "release_action",
                "type": "choice",
                "choices": ["commit", "version-bump", "publish", "hold"],
            },
        ),
    ),
    _point(
        dp_id="dp14-rule-conflict",
        tier="P0",
        description="用户指令 vs 规则",
        p0_consequences="越过项目硬规则会改变授权边界，影响后续所有会话",
        questions=(
            {
                "id": "conflict_resolution",
                "type": "choice",
                "choices": ["follow-rule", "follow-instruction", "ask-human"],
            },
        ),
    ),
    _point(
        dp_id="dp15-autopilot-gate",
        tier="P0",
        description="6 类人工门",
        p0_consequences="自动越过 autopilot 人工门会让无人监管的推进落地，单次最贵的不可逆面",
        questions=(
            {"id": "gate_decision", "type": "choice", "choices": ["continue", "narrow", "revoke"]},
        ),
    ),
    _point(
        dp_id="dp16-goal",
        tier="P0",
        description="goal 确立/变更",
        p0_consequences="改项目级目标会让所有 worker 的方向对齐失效，历史上不可追溯",
        questions=(
            {"id": "goal_decision", "type": "choice", "choices": ["keep", "amend", "defer"]},
        ),
    ),
    _point(
        dp_id="dp17-spec-lock",
        tier="P1",
        description="spec/AC 锁定",
        questions=(
            {"id": "spec_lock", "type": "choice", "choices": ["lock", "reopen", "amend"]},
        ),
    ),
    _point(
        dp_id="dp18-claim",
        tier="P1",
        description="key 抢占冲突",
        questions=(
            {"id": "claim_conflict", "type": "choice", "choices": ["wait", "steal", "new-key"]},
        ),
    ),
    _point(
        dp_id="dp19-foreign-write",
        tier="P0",
        description="越面写预授权",
        p0_consequences="越面写会覆盖其他会话/其他 key 的文件，写坏即他人工作丢失",
        questions=(
            {"id": "write_decision", "type": "choice", "choices": ["allow", "deny", "redirect"]},
        ),
    ),
    _point(
        dp_id="dp20-stage-close",
        tier="P0",
        description="stage 闭环",
        p0_consequences="stage 闭环会推进不可回退的门禁与产物状态，错误闭环需要人工重建",
        questions=(
            {"id": "stage_action", "type": "choice", "choices": ["close", "hold", "rework"]},
        ),
    ),
    _point(
        dp_id="dp21-refine",
        tier="P2",
        description="project-refine 升级",
        questions=(
            {"id": "refine_decision", "type": "choice", "choices": ["accept", "defer", "reject"]},
        ),
        executor=_unwired_executor("dp21-refine"),
    ),
    _point(
        dp_id="dp22-debug-plan",
        tier="P2",
        description="debug 方案确认",
        questions=(
            {
                "id": "debug_plan",
                "type": "choice",
                "choices": ["hypothesis-first", "repro-first", "rollback"],
            },
        ),
        executor=_unwired_executor("dp22-debug-plan"),
    ),
    _point(
        dp_id="dp23-snapshot",
        tier="P2",
        description="memory 快照",
        questions=(
            {"id": "snapshot_decision", "type": "choice", "choices": ["write", "defer", "skip"]},
        ),
        executor=_unwired_executor("dp23-snapshot"),
    ),
    _point(
        dp_id="dp24-pi-trust",
        tier="P0",
        description="pi core 交互",
        p0_consequences="影响 pi 核心信任边界，误判后会话权限升级不可在一次重派内撤回",
        questions=(
            {"id": "trust_decision", "type": "choice", "choices": ["trust-once", "trust-always", "deny"]},
        ),
    ),
    _point(
        dp_id="dp25-signoff-conclusion",
        # P2 (not P1): the sign-off point is the default path for `mw decide
        # sign` (spec §15 AC-024/AC-027), so it is on by default and auto mode
        # must own a callable executor (the echo below, never a write).
        tier="P2",
        default_mode="auto",
        description="任意 key 收尾的签收结论（按 key 计算，替代人签）",
        questions=(
            {
                "id": "q-conclusion",
                "type": "choice",
                "choices": ["continue", "narrow", "revoke"],
                "instructions": (
                    "给出该 key 的收尾签收结论（任意 AgenticTask key 通用，key 由调用方传入）。判据：continue 需要 rows_available>=1、"
                    "chain_ok=true，且每一行都来自真实 jev 引擎 "
                    "timi-decisions/jev-latest/api（engine_violations 为空）；narrow 用于"
                    "降级：有证据但不足以为全量结论背书（N=0、部分行上抛、范围过大）；"
                    "revoke 用于 chain_ok=false（档案链断/被篡改）或 engine 不符（出现"
                    "非 jev 引擎的行）。信息不足时选 narrow，不要选 continue。"
                ),
                "labels": {
                    "continue": "证据充分：N>=1、链闭合、每行都是真实 jev 引擎",
                    "narrow": "降级：证据不足以背书全量结论，缩小范围后继续",
                    "revoke": "撤回：档案链断或出现非 jev 引擎的行",
                },
            },
        ),
        # The write stays in `mw decide sign` (W9); this executor only echoes the
        # conclusion, so there is no second authority for the same file.
        executor=_echo_conclusion_executor("dp25-signoff-conclusion"),
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
    return by_id

_REGISTRY_BY_ID = _validate_registry(DP_REGISTRY)


def get_decision_point(dp_id: str) -> DecisionPoint:
    """Resolve a registered dp; unknown ids fail loudly (spec §5.2 / AC-011)."""
    dp_point = _REGISTRY_BY_ID.get(dp_id)
    if dp_point is None:
        raise decision.DecisionInputError(f"unknown decision point id {dp_id!r}")
    return dp_point


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
SNAPSHOT_SCHEMA = 3

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
    """The 25 registered dps as a plain document (pure: no file access).

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
    with no semantics is the gap this shape closes). The four wiring keys fall
    back to :data:`UNWIRED_SNAPSHOT_WIRING`: they name TS call sites, which the
    registry cannot know, so the export writer merges the hand-written values
    in point by point (``mw._dp_export_doc``).
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
                "questions": [_snapshot_question(question) for question in dp_point.questions],
            }
        )
    return {
        "schema": SNAPSHOT_SCHEMA,
        "generated_from": "decision_points.DP_REGISTRY",
        "question_types": sorted(decision.QUESTION_TYPES),
        "points": points,
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


def dynamic_choice_labels(questions: Mapping, state: object) -> dict[str, dict[str, str]] | None:
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
        if not isinstance(candidates, list) or dynamic_choices_value_error(candidates):
            return None
        rendered[str(qid)] = {
            str(item["id"]): str(item["label"]) for item in candidates
        }
    return rendered


def resolve_dynamic_choices(
    questions: Mapping, state: object
) -> dict[str, tuple[str, ...]] | None:
    """Legal answer ids per dynamic question; ``None`` when any cannot render.

    The ids are the *rendered* enum the model may answer with, not the registry
    question set: ``questions_version`` still hashes the registry questions only
    (it names the question-set shape, the candidates are input data).
    """
    labels = dynamic_choice_labels(questions, state)
    if labels is None:
        return None
    return {qid: tuple(candidate_ids) for qid, candidate_ids in labels.items()}


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
REQUIRED_STATE_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "dp1-dispatch-type": (
            "schema_version",
            "decision_point",
            "key",
            "phase",
            "task_type",
            "requested_type",
            "risk",
            "risk_source",
            "authority_tier",
            "task_summary",
            "questions_version",
            "scope.write_scope",
            "scope.file_extensions",
        ),
        "dp2-checkpoint-split": (
            "schema_version",
            "decision_point",
            "key",
            "phase",
            "task_type",
            "risk",
            "risk_source",
            "authority_tier",
            "questions_version",
            "progress.elapsed_minutes",
            "progress.budget_minutes",
            "progress.phases_done",
            "progress.phases_total",
            "progress.artifact_present",
        ),
        "dp3-worker-clarify": (
            "schema_version",
            "decision_point",
            "key",
            "phase",
            "task_type",
            "risk",
            "risk_source",
            "authority_tier",
            "task_summary",
            "questions_version",
            "ambiguity.kind",
            "ambiguity.question",
            # FIX-I: the candidate question renders its enum from these entries;
            # without them the question set cannot be sent (zero HTTP).
            "local_candidates",
        ),
        # dp4..dp24 (design §4.5): the typed business contract. Identity-only
        # state is refused as `input-incomplete` (zero HTTP) — an "empty" book is
        # a virtual test channel, not a decision.
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
        # dp25 (spec §15 AC-027 / design D-067): exactly the facts
        # `decide_signoff.collect()` folds out of the archive. No diff, no code,
        # no document is part of this state.
        "dp25-signoff-conclusion": (
            "key",
            "rows_total",
            "rows_available",
            "chain_ok",
            "p0_open",
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
        # required, dropped first when the 2000 B budget needs room.
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
    }
)

#: Optional L1 paths per dp (the closed set of *legal but not required* input).
#: Design §4.5: dp1's already-used ``history``/``scope.images_required`` and
#: dp2's real producer fields (``pm-orchestrator.buildDp2CheckpointState``) are
#: declared here, so the book closed key set, the export and the drop order are
#: all derived from one table instead of a second hard-coded tuple.
OPTIONAL_STATE_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType(
    {
        "dp1-dispatch-type": ("history", "scope.images_required"),
        "dp2-checkpoint-split": (
            "progress.writes",
            "progress.uniq_targets",
            "progress.repeat_top",
            "progress.trend",
            "progress.last_land_age_min",
        ),
        # dp25's real producer facts (``decide_signoff.signoff_state``): declared
        # here so the seam, the book and the export read one contract (T05c).
        "dp25-signoff-conclusion": (
            "rows_escalated",
            "escalated_reasons",
            "engine_violations",
        ),
    }
)

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
#: stay consistent with the bound it is compared to. ``lte`` = integer <=
#: integer, ``count_lte`` = array length <= integer, ``subset`` = every item is
#: present in the other array. A rule names only declared required paths.
STATE_FIELD_CROSS_CHECKS: Mapping[str, tuple[dict[str, str], ...]] = MappingProxyType(
    {
        "dp4-failure-handling": (
            {"kind": "lte", "left": "failure.attempt", "right": "failure.limit"},
        ),
        "dp6-qg-verdict": (
            {
                "kind": "count_lte",
                "array": "qg.checks_failed",
                "bound": "qg.checks_total",
            },
        ),
        "dp17-spec-lock": (
            {"kind": "subset", "items": "spec.ac_changed", "of": "spec.ac_ids"},
        ),
        "dp20-stage-close": (
            {"kind": "lte", "left": "stage.tasks_done", "right": "stage.tasks_total"},
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


def _lookup(state: Mapping, dotted: str) -> object:
    current: object = state
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _is_blank(value: object) -> bool:
    if value is _MISSING or value is None:
        return True
    return isinstance(value, str) and not value.strip()


def _missing_required(state: Mapping, dp_id: str) -> tuple[str, ...]:
    missing = [path for path in REQUIRED_STATE_FIELDS.get(dp_id, ()) if _is_blank(_lookup(state, path))]
    return tuple(missing)


_validate_state_field_contract()


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
    every required field, and its bytes are counted inside the same 2000 B
    budget instead of riding on top of it.
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
    preview: Mapping | None = None
    call_id: str | None = None
    snapshot_ref: str | None = None
    #: Set when the caller's material was refused as illegal (typed contract,
    #: closed key set or observation book). Refused material is never stored as
    #: a snapshot: only the refusal facts belong in the ledger (T05b F1/F2).
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


def _capture_scope(
    capture: _DecisionCapture,
    *,
    project: pathlib.Path,
    cfg: decision.DecisionConfig | None,
    client: decision.DecisionClient | None,
    dp_point: DecisionPoint,
    decision_id: str,
    trigger: Trigger,
) -> tuple[Any | None, str]:
    """``(scope, channel)`` for this decision; a *fresh* production scope per call.

    The production scope is created here and carries a freshly built credential
    redactor (T03 review F-3: a rotated credential must never be captured through
    a reused redactor). A caller-provided client scope wins - it is the already
    explicit, already isolated ledger of that client - so no second scope can
    split one call across two files.
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
        redactor = decision.credential_redactor(cfg) if cfg is not None else None
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
    6. canonical size > 2000 B -> drop optional L1, halve required L1, then
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
    if not transport_configured:
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
        unknown_keys = state_unknown_key_issues(
            dp_point.id,
            state,
            allow_context=True,
        )
        if unknown_keys:
            unknown_keys = state_unknown_key_issues(
                dp_point.id,
                state,
                allow_context=True,
                redactor=decision.known_secret_redactor(cfg),
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

    # Step 6 — canonical budget <= 2000 B (two-stage truncation, then refuse).
    state, dropped_paths, size = _fit_state(state)
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
            redactor=decision.known_secret_redactor(cfg),
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
    if client is None:
        client = decision.DecisionClient(cfg=cfg, backend=backend, project_root=project)
    wire = _wire_api()
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
