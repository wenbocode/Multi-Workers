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
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import Any

import decision
import decision_context

__all__ = [
    "DECISIONS_RELATIVE_PATH",
    "DECIDE_POINTS_RELATIVE_PATH",
    "DP_REGISTRY",
    "ESCALATED_REASONS",
    "EXPECTED_DP_COUNT",
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
    "STATE_FIELD_DESCRIPTIONS",
    "DecisionOutcome",
    "DecisionPoint",
    "PointConfig",
    "PointsConfig",
    "TIERS",
    "Trigger",
    "UNWIRED_SNAPSHOT_WIRING",
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
        state: dict[str, Any] = {"schema_version": 2, "decision_point": dp_id}
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
SNAPSHOT_SCHEMA = 2

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


def _snapshot_state_fields(dp_id: str) -> list[dict]:
    """``required_state_fields`` of one dp as ``{name, type, description}``.

    Order follows :data:`REQUIRED_STATE_FIELDS` (the authority for *which*
    paths are required); :data:`STATE_FIELD_DESCRIPTIONS` supplies the meaning.
    A path without an entry is a registry bug, so it fails loud instead of
    exporting a bare string the reader has to guess at.
    """
    fields: list[dict] = []
    for path in REQUIRED_STATE_FIELDS.get(dp_id, ()):
        spec = STATE_FIELD_DESCRIPTIONS.get(path)
        if spec is None:
            raise ValueError(
                f"{dp_id}: required state path {path!r} has no STATE_FIELD_DESCRIPTIONS entry"
            )
        fields.append(
            {"name": path, "type": spec["type"], "description": spec["description"]}
        )
    return fields


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

    Every point is self-describing: ``required_state_fields`` reads
    :data:`REQUIRED_STATE_FIELDS` + :data:`STATE_FIELD_DESCRIPTIONS` at call
    time (both definitions sit in the structured-input section below) and
    renders ``[{name, type, description}]``, ``[]`` for a dp without an entry;
    a required path without a description raises here (an exported field with
    no semantics is the gap this shape closes). The four wiring keys fall back
    to :data:`UNWIRED_SNAPSHOT_WIRING`: they name TS call sites, which the
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
                "required_state_fields": _snapshot_state_fields(dp_point.id),
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

#: Required state paths per dp (missing / None / blank string => input-incomplete).
#: dp1/dp2/dp3 sets come from the structured-input contract (D6 Q5.1); the
#: generic builder already guarantees ``schema_version``/``decision_point``/
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
        },
    }
)

#: Optional L1 paths dropped first when the canonical state exceeds the budget.
OPTIONAL_STATE_PATHS: tuple[str, ...] = (
    "history",
    "scope.images_required",
    "progress.writes",
    "progress.uniq_targets",
    "progress.repeat_top",
    "progress.last_land_age_min",
)

#: Required L1 paths truncated (halved) when dropping optional fields is not enough.
TRUNCATABLE_STATE_PATHS: tuple[str, ...] = ("task_summary", "ambiguity.question")

_MISSING = object()


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


def _maybe_archive(archive: bool, **kwargs: Any) -> tuple[bool, bool]:
    """``archive=False`` short-circuits; else ``_archive_decision`` -> (archived, replayed)."""
    if not archive:
        return False, False
    return _archive_decision(**kwargs)


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
    """
    # Step 1 — unknown ids fail loudly (never a silent degradation).
    dp_point = get_decision_point(dp_id)
    if intent not in INTENTS:
        raise decision.DecisionInputError(
            f"intent {intent!r} is not one of {INTENTS}"
        )
    trigger_obj = _coerce_trigger(trigger)
    project = _coerce_project_dir(project_dir)
    decision_id = f"{dp_point.id}:{trigger_obj.resolved_id()}"

    # Step 2 — authorization gate. Nothing expensive may run before this return.
    view = points_config if points_config is not None else load_points_config(project)
    effective = view.effective(dp_point)
    if not effective.enabled:
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

    # Step 3 — mode: config value wins, registry default is the fallback.
    mode = effective.mode if effective.mode in MODES else dp_point.default_mode

    # Step 4 — transport availability/budget (`.mw/decide.json` owns transport).
    cfg: decision.DecisionConfig | None = config
    if client is not None:
        cfg = client.cfg
    elif cfg is None:
        cfg, _cfg_error = decision.DecisionConfig.from_project(project)
    if cfg is None or not cfg.is_configured:
        detail = cfg.config_error or (
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
    questions = questions_map(dp_point)
    if not questions:
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

    # Step 7 — one transport call; `decision.DecisionClient` never raises here.
    if client is None:
        client = decision.DecisionClient(cfg=cfg, backend=backend, project_root=project)
    response = client.decide(state, questions, dp=dp_point.id)
    if not response.get("available"):
        transport_reason = response.get("reason") or decision.REASON_UPSTREAM_ERROR
        archived, replayed = _maybe_archive(
            archive,
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
