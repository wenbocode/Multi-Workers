"""T03 patch script: eight-entry protocol in the isolated copy of decision_points.py.

CRLF-preserving: the file is read as bytes, normalised to '\n' in memory for the
anchored replacements, then written back with the original line ending. Every
anchor must be present exactly once, so a drifted file fails loudly instead of
half-patching.

Usage:
    python patch_decision_points.py <decision_points.py> [--check]
"""

from __future__ import annotations

import hashlib
import pathlib
import sys

TARGET = pathlib.Path(
    sys.argv[1]
    if len(sys.argv) > 1
    else r"H:\git\Multi-Workers\.agenticdoc\mw-dp-consolidation"
    r"\implementation-worktree\packages\multi-workers\decision_points.py"
)
CHECK_ONLY = "--check" in sys.argv


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"anchor {label!r} found {count} times (expected 1)")
    return text.replace(old, new, 1)


def replace_block(text: str, start: str, end: str, new: str, label: str) -> str:
    """Replace [start, end) with ``new``; both anchors must be unique."""
    if text.count(start) != 1:
        raise SystemExit(f"start anchor {label!r} found {text.count(start)} times")
    if text.count(end) != 1:
        raise SystemExit(f"end anchor {label!r} found {text.count(end)} times")
    begin = text.index(start)
    stop = text.index(end, begin)
    return text[:begin] + new + text[stop:]


# ---------------------------------------------------------------------------
# 1. Docstring, __all__, module constant
# ---------------------------------------------------------------------------

DOCSTRING_OLD = """Four-DP contract (key ``mw-decision-context``, design §2): dp1/dp2/dp3/dp25
declare the approved business material only."""

DOCSTRING_NEW = """Eight-entry protocol (key ``mw-dp-consolidation``, card T03, design §10 D-001A /
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
material only."""

ALL_STEPS = [
    (
        "all active",
        '    "ACTOR_ID_MAX_BYTES",\n    "ACTOR_KINDS",\n    "ARCHIVE_STATES",',
        '    "ACTIVE_DP_IDS",\n    "ACTOR_ID_MAX_BYTES",\n    "ACTOR_KINDS",\n'
        '    "ACTOR_ROLES",\n    "ARCHIVE_STATES",',
    ),
    (
        "all basis",
        '    "CAPTURE_CHANNELS",\n    "DECISIONS_RELATIVE_PATH",',
        '    "BASIS_ITEM_KEYS",\n    "BASIS_SOURCE",\n    "CAPTURE_CHANNELS",\n'
        '    "CANDIDATE_ITEM_KEYS",\n    "CANDIDATE_LABEL_MAX",\n'
        '    "DECISIONS_RELATIVE_PATH",',
    ),
    (
        "all entries",
        '    "DP_REGISTRY",\n    "ESCALATED_REASONS",\n    "EXPECTED_DP_COUNT",',
        '    "DP_REGISTRY",\n    "ENTRY_CHOICES",\n    "ENTRY_IDS",\n'
        '    "ENTRY_KINDS",\n    "ENTRY_ROLES",\n    "ESCALATED_REASONS",\n'
        '    "EXPECTED_DP_COUNT",',
    ),
    (
        "all prep/retired",
        '    "POLICY_LAYERS",\n    "POLICY_ROW_BOUNDS",',
        '    "POLICY_LAYERS",\n    "POLICY_ROW_BOUNDS",\n    "PREPARATION_KEYS",\n'
        '    "RETIRED_DP_IDS",\n    "RETIRED_DP_REGISTRY",\n'
        '    "RETIRED_STATE_FIELDS",\n    "ROUTE_TARGETS",',
    ),
    (
        "all dataclass",
        '    "DecisionOutcome",\n    "DecisionPoint",\n    "Observation",',
        '    "DecisionOutcome",\n    "DecisionPoint",\n    "Observation",\n'
        '    "RetiredDecisionPoint",',
    ),
    (
        "all validators",
        '    "apply_question_override",\n    "question_override_issues",',
        '    "apply_question_override",\n    "basis_catalog_issues",\n'
        '    "basis_selection_issues",\n    "entry_candidates_issues",\n'
        '    "entry_choice_issues",\n    "entry_material_issues",\n'
        '    "is_retired_dp",\n    "pm_candidate_issues",\n'
        '    "pm_note_issues",\n    "preparation_issues",\n'
        '    "prepared_request_issues",\n    "question_override_issues",\n'
        '    "require_active_dp",\n    "resolve_entry_choices",\n'
        '    "retired_dp",\n    "role_issues",\n'
        '    "sign_key_material_issues",\n    "vision_dispatch_issues",',
    ),
]

COUNT_OLD = """#: Number of registered decision points (spec §4 / design §2.1; dp25 added by
#: spec §15 AC-027).
EXPECTED_DP_COUNT = 25"""
COUNT_NEW = """#: Number of registered decision points: exactly the eight active entries of
#: spec §1.1 (T03). The 25 pre-consolidation ids are retired, never registered.
EXPECTED_DP_COUNT = 8"""

# ---------------------------------------------------------------------------
# 2. DecisionPoint fields + the one registry factory
# ---------------------------------------------------------------------------

DATACLASS_OLD = """    id: str
    tier: str
    default_enabled: bool
    default_mode: str
    questions: tuple[dict, ...]
    build_state: Callable[[Trigger], dict]
    executor: Callable[[dict, Trigger], str] | None
    questions_version: str
    p0_consequences: str | None
    description: str
"""

DATACLASS_NEW = """    id: str
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
"""

DATACLASS_VALIDATE_OLD = """        if not isinstance(self.description, str) or not self.description:
            raise ValueError(f"{self.id}: description must be a non-empty string")
"""

DATACLASS_VALIDATE_NEW = """        if not isinstance(self.description, str) or not self.description:
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
"""

POINT_OLD = """def _point(
    *,
    dp_id: str,
    tier: str,
    questions: tuple[dict, ...],
    description: str,
    p0_consequences: str | None = None,
    executor: Callable[[dict, Trigger], str] | None = None,
    default_mode: str = "auto",
) -> DecisionPoint:
    \"\"\"Registry entry factory: derives default_enabled / questions_version.\"\"\"
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
    )"""

POINT_NEW = """def _point(
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
    \"\"\"Registry entry factory: derives default_enabled / questions_version.\"\"\"
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
    )"""

# ---------------------------------------------------------------------------
# 3. Protocol constants + retired directory + eight-entry registry
# ---------------------------------------------------------------------------

REGISTRY_START = "#: The 25 decision points: dp1..dp24 from spec.md §4 plus"
REGISTRY_END = "_REGISTRY_BY_ID: dict[str, DecisionPoint] = {}"

PROTOCOL_BLOCK = '''# ---------------------------------------------------------------------------
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

'''

# ---------------------------------------------------------------------------
# 4. Validation / retired rejection / get_decision_point
# ---------------------------------------------------------------------------

VALIDATE_START = "def _validate_registry(entries: tuple[DecisionPoint, ...]) -> dict[str, DecisionPoint]:"
VALIDATE_END = "def questions_map(dp_point: DecisionPoint | str) -> dict[str, dict]:"

VALIDATE_BLOCK = '''def _validate_registry(entries: tuple[DecisionPoint, ...]) -> dict[str, DecisionPoint]:
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


'''

# ---------------------------------------------------------------------------
# 5. State tables
# ---------------------------------------------------------------------------

REQUIRED_START = "REQUIRED_STATE_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType("
REQUIRED_END = "#: Meaning of every required state path:"

REQUIRED_BLOCK = '''#: Required state paths per *active* entry (missing / None / blank string =>
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

'''

OPTIONAL_START = "OPTIONAL_STATE_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType("
OPTIONAL_END = "#: The exact business keys sent to the model, per dp"

OPTIONAL_BLOCK = '''#: Optional L1 paths per active entry (the closed set of *legal but not
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

'''

MODEL_START = "MODEL_STATE_FIELDS: Mapping[str, tuple[str, ...]] = MappingProxyType("
MODEL_END = "#: Local association/audit keys of the four model-contract dps"

MODEL_BLOCK = '''#: The exact business keys sent to the model, per active entry (design D001: one
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

'''

CROSS_START = "#: Cross-field facts the registry owns (design §4.5): the left/array value must"
CROSS_END = "_MISSING = object()"

CROSS_BLOCK = '''#: Cross-field facts the registry owns (design §4.5): the left/array value must
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

'''

# ---------------------------------------------------------------------------
# 6. Descriptions
# ---------------------------------------------------------------------------

DESC_INSERT_OLD = '''        "progress.last_land_age_min": {
            "type": "integer",
            "description": "Minutes since the worker last landed an artifact, optional L1.",
            "min_value": 0,
        },
    }
)'''

DESC_INSERT_NEW = '''        "progress.last_land_age_min": {
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
)'''

HANDLING_OLD = '''        "handling_options": {
            "type": "array",
            "description": "Problem-specific handling candidates [{id,label,description}] rendered as the native dynamic choice.",
            "item_type": "object",
        },'''

HANDLING_NEW = '''        "handling_options": {
            "type": "array",
            "description": (
                "PM-prepared, problem-specific action candidates "
                "[{id,label,description,consequence,risk,conditions}]; ids only need to be "
                "unique in this request (no legacy cN/2..5 bound)."
            ),
            "item_type": "object",
            "max_items": STATE_ARRAY_MAX_ITEMS,
        },'''

QUESTION_OLD = '''        "question": {
            "type": "string",
            "description": "The clarifying question verbatim, written before any answer.",
        },'''

QUESTION_NEW = '''        "question": {
            "type": "string",
            "description": "The pending question verbatim (what exactly needs a decision), written before any answer.",
        },'''

# ---------------------------------------------------------------------------
# 7. Pure validators (inserted where the typed contract is validated)
# ---------------------------------------------------------------------------

VALIDATOR_ANCHOR = """_validate_state_field_contract()


def _without_path(state: Mapping, dotted: str) -> dict:"""

VALIDATOR_BLOCK = '''_validate_protocol_contract()
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
            if "\\n" in label or "\\r" in label:
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
        issues.append(("prepared_at", "must be a non-empty ISO timestamp"))
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
    prepared basis, then the answer. Nothing here executes, releases or signs.
    """
    require_active_dp(dp_id)
    issues: list[tuple[str, str]] = []
    if actor_role is not None:
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


def _without_path(state: Mapping, dotted: str) -> dict:'''

# ---------------------------------------------------------------------------
# 8. Small one-line / branch replacements
# ---------------------------------------------------------------------------

SMALL_STEPS = [
    (
        "cross branch",
        '''        elif kind == "subset":
            items_path = rule["items"]''',
        '''        elif kind == "pm_candidates":
            candidates = _lookup(state, rule["array"])
            if not isinstance(candidates, list):
                continue
            issues.extend(pm_candidate_issues(candidates))
        elif kind == "subset":
            items_path = rule["items"]''',
    ),
    ("snapshot schema", "SNAPSHOT_SCHEMA = 3", "SNAPSHOT_SCHEMA = 4"),
    (
        "snapshot point",
        '''                "description": dp_point.description,
                "questions_version": dp_point.questions_version,''',
        '''                "description": dp_point.description,
                "kind": dp_point.kind,
                "role_scope": dp_point.role_scope,
                "candidate_source": dp_point.candidate_source,
                "candidate_bounds": (
                    None
                    if dp_point.candidate_bounds is None
                    else dict(dp_point.candidate_bounds)
                ),
                "target_entries": list(dp_point.target_entries),
                "questions_version": dp_point.questions_version,''',
    ),
    (
        "snapshot return",
        '''    return {
        "schema": SNAPSHOT_SCHEMA,
        "generated_from": "decision_points.DP_REGISTRY",
        "question_types": sorted(decision.QUESTION_TYPES),
        "points": points,
    }''',
        '''    return {
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
    }''',
    ),
    (
        "snapshot doc",
        '    """The 25 registered dps as a plain document (pure: no file access).',
        '    """The eight active dps as a plain document (pure: no file access).',
    ),
    (
        "snapshot doc2",
        '''    ``[{name, type, description, ...constraints}]``, ``[]`` for a dp without an
    entry; a declared path without a description raises here (an exported field
    with no semantics is the gap this shape closes). ``model_state_fields`` is
    the approved four-DP model key table and is absent for the 21 legacy dps
    (absent = no allowlist, state sent unchanged). The four wiring keys fall
    back to :data:`UNWIRED_SNAPSHOT_WIRING`: they name TS call sites, which the
    registry cannot know, so the export writer merges the hand-written values
    in point by point (``mw._dp_export_doc``).
    """''',
        '''    ``[{name, type, description, ...constraints}]``, ``[]`` for a dp without an
    entry; a declared path without a description raises here (an exported field
    with no semantics is the gap this shape closes). ``model_state_fields`` is
    each entry's model key table (every active entry declares one). The four
    wiring keys fall back to :data:`UNWIRED_SNAPSHOT_WIRING`: they name TS call
    sites, which the registry cannot know, so the export writer merges the
    hand-written values in point by point (``mw._dp_export_doc``).

    The retired directory is exported as its own top-level ``retired`` section
    (never mixed into ``points``): history stays explainable read-only while the
    callable set stays exactly eight.
    """''',
    ),
    (
        "model export doc",
        '''    """The per-dp model key table, exported only for the four approved dps.

    An absent key means "no allowlist declared": the 21 legacy dps keep sending
    their declared state unchanged (``model_state_for`` returns it as-is).
    """''',
        '''    """The per-entry model key table (every active entry declares one).

    An absent key still means "no allowlist declared" and keeps the historical
    "send the declared state unchanged" fallback, but no active entry relies on
    it any more.
    """''',
    ),
    (
        "state doc",
        '''    The other 21 dps have no allowlist entry and therefore keep their existing
    contract unchanged (a shallow copy of the state).
    """''',
        '''    An id without an allowlist entry keeps the historical contract (a shallow
    copy of the state); no active entry relies on that fallback.
    """''',
    ),
    (
        "dynamic labels sig",
        "def dynamic_choice_labels(questions: Mapping, state: object) -> dict[str, dict[str, str]] | None:",
        "def dynamic_choice_labels(\n    questions: Mapping, state: object, *, dp_id: str | None = None\n) -> dict[str, dict[str, str]] | None:",
    ),
    (
        "dynamic body",
        "        if not isinstance(candidates, list) or dynamic_choices_value_error(candidates):\n            return None",
        '''        if not isinstance(candidates, list):
            return None
        if dp_id is not None and _REGISTRY_BY_ID.get(dp_id) is not None and (
            _REGISTRY_BY_ID[dp_id].kind == "dynamic-candidates"
        ):
            # The active dynamic entry (dp-auto) has no legacy cN/2..5 bound; its
            # one candidate contract is pm_candidate_issues.
            if pm_candidate_issues(candidates):
                return None
        elif dynamic_choices_value_error(candidates):
            return None''',
    ),
    (
        "dynamic resolve sig",
        "def resolve_dynamic_choices(\n    questions: Mapping, state: object\n) -> dict[str, tuple[str, ...]] | None:",
        "def resolve_dynamic_choices(\n    questions: Mapping, state: object, *, dp_id: str | None = None\n) -> dict[str, tuple[str, ...]] | None:",
    ),
    (
        "dynamic resolve body",
        "    labels = dynamic_choice_labels(questions, state)",
        "    labels = dynamic_choice_labels(questions, state, dp_id=dp_id)",
    ),
    (
        "retired state validate",
        '''    for dp_id, paths in REQUIRED_STATE_FIELDS.items():
        if dp_id not in _REGISTRY_BY_ID:
            raise ValueError(f"REQUIRED_STATE_FIELDS: unknown dp id {dp_id!r}")''',
        '''    for dp_id, paths in RETIRED_STATE_FIELDS.items():
        if dp_id not in _RETIRED_BY_ID:
            raise ValueError(f"RETIRED_STATE_FIELDS: unknown retired id {dp_id!r}")
        for path in paths:
            check_path(dp_id, path)
    for dp_id, paths in REQUIRED_STATE_FIELDS.items():
        if dp_id not in _REGISTRY_BY_ID:
            raise ValueError(f"REQUIRED_STATE_FIELDS: unknown dp id {dp_id!r}")''',
    ),
]


def main() -> int:
    raw = TARGET.read_bytes()
    original_sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8")
    eol = "\r\n" if b"\r\n" in raw else "\n"
    text = text.replace("\r\n", "\n")

    text = replace_once(text, DOCSTRING_OLD, DOCSTRING_NEW, "docstring")
    text = replace_once(text, COUNT_OLD, COUNT_NEW, "expected count")
    text = replace_once(text, DATACLASS_OLD, DATACLASS_NEW, "dataclass fields")
    text = replace_once(
        text, DATACLASS_VALIDATE_OLD, DATACLASS_VALIDATE_NEW, "dataclass validation"
    )
    text = replace_once(text, POINT_OLD, POINT_NEW, "point factory")

    text = replace_block(text, REGISTRY_START, REGISTRY_END, PROTOCOL_BLOCK, "registry")
    text = replace_block(text, VALIDATE_START, VALIDATE_END, VALIDATE_BLOCK, "validate")
    text = replace_block(text, REQUIRED_START, REQUIRED_END, REQUIRED_BLOCK, "required")
    text = replace_block(text, OPTIONAL_START, OPTIONAL_END, OPTIONAL_BLOCK, "optional")
    text = replace_block(text, MODEL_START, MODEL_END, MODEL_BLOCK, "model")
    text = replace_block(text, CROSS_START, CROSS_END, CROSS_BLOCK, "cross")
    text = replace_once(text, VALIDATOR_ANCHOR, VALIDATOR_BLOCK, "validator block")
    text = replace_once(text, DESC_INSERT_OLD, DESC_INSERT_NEW, "description block")
    text = replace_once(text, HANDLING_OLD, HANDLING_NEW, "handling description")
    text = replace_once(text, QUESTION_OLD, QUESTION_NEW, "question description")

    for label, old, new in ALL_STEPS:
        text = replace_once(text, old, new, f"__all__ {label}")
    for label, old, new in SMALL_STEPS:
        text = replace_once(text, old, new, label)

    if CHECK_ONLY:
        print(
            f"check only: 5 + 7 blocks + {len(ALL_STEPS) + len(SMALL_STEPS)} anchors "
            f"apply cleanly to {original_sha}"
        )
        return 0

    output = text.replace("\n", eol)
    TARGET.write_bytes(output.encode("utf-8"))
    print(f"patched {TARGET}")
    print(f"sha_before={original_sha}")
    print(f"sha_after={hashlib.sha256(TARGET.read_bytes()).hexdigest()}")
    print(f"bytes={TARGET.stat().st_size} eol={'CRLF' if eol == chr(13) + chr(10) else 'LF'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
