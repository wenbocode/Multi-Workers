"""build_decide_cases.py - offline generator for the eight DP workbench cases.

The decision workbench ships exactly eight *synthetic* decision books, one for
each active entry of design §1.1 (``dp-w-type``, ``dp-pm-steer``,
``dp-w-check-task``, ``dp-QG``, ``dp-gate-approve``, ``dp-sign-key``,
``dp-auto``, ``dp-route``). They exist so a human can pick a complete, editable
book on the DP test page and observe the real decision chain without inventing
material by hand.

This script is the case's only writer and it is deliberately boring:

* **offline** - it reads the registry (``decision_points``) and this file's own
  bytes; it never reads a credential, opens a socket, starts a service or calls
  a model;
* **single source** - the eight case ids are :data:`CASE_IDS`; the business
  field names, types and closed key sets come from the registry
  (``decision_book.required_state_paths`` / ``optional_state_paths``), so a case
  cannot drift into a second hand-kept vocabulary;
* **complete schema 3** - every book is the layered contract of D-002A:
  ``material`` (business facts), ``preparation`` (the PM-prepared
  ``basis_catalog`` + ``prepared_at``, D012A) and the local-only ``meta``. There
  are no placeholders, no ellipses and no TODO markers, so a case never turns
  into a half-filled book that the observation gate would have to refuse;
* **honest provenance** - every required material field's ``notes.evidence``
  points at the exact line of this generator that defines that material
  (``path:line``), so the evidence is resolvable in the repository instead of
  being a scaffold placeholder. Each prepared basis item cites the material it
  relies on via ``material_refs`` and the choices it applies to via
  ``applies_to``; the model's same-call ``basis_id`` therefore always has a real
  referent;
* **no legacy writes** - the four pre-consolidation cases (``dp1.json``,
  ``dp2.json``, ``dp3.json``, ``dp25.json``) are read-only history. Their ids are
  retired, so this generator refuses them before writing anything; it only ever
  writes the eight names in :data:`CASE_IDS`;
* **budget respected** - the existing no-truncation send budget
  (``decision_points.MAX_STATE_BYTES``) is checked here and a too-large case
  fails loudly instead of being shortened.

Regenerate (no network, no credential, no model)::

    python scripts/build_decide_cases.py

The drift guard in ``test_decision_context_workbench.py`` re-runs
:func:`write_cases` and compares the result byte-for-byte with the shipped
files, so a hand edit that forgets to regenerate is caught.
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
from typing import Mapping

# The generator is also runnable as a plain script (``python scripts/build_decide_cases.py``),
# where sys.path[0] is the scripts directory; the decision modules live one level up.
_SCRIPT_DIR = pathlib.Path(__file__).resolve().parent
if str(_SCRIPT_DIR.parent) not in sys.path:
    sys.path.insert(0, str(_SCRIPT_DIR.parent))

import decision  # noqa: E402 - path bootstrap above
import decision_book  # noqa: E402
import decision_points  # noqa: E402

#: Shell version of the case container
#: (``{case_version, dp, title, note, questions, book}``).
CASE_VERSION = 1

#: The only eight case ids the workbench serves: one per active entry of design
#: §1.1. The route never scans a directory, so this table is the whole menu.
CASE_IDS: dict[str, str] = {
    "dp-w-type": "dp-w-type.json",
    "dp-pm-steer": "dp-pm-steer.json",
    "dp-w-check-task": "dp-w-check-task.json",
    "dp-QG": "dp-QG.json",
    "dp-gate-approve": "dp-gate-approve.json",
    "dp-sign-key": "dp-sign-key.json",
    "dp-auto": "dp-auto.json",
    "dp-route": "dp-route.json",
}

#: The four pre-consolidation cases: byte-locked read-only history. They are
#: listed here only so the generator can refuse to write them (the ids are
#: retired, so ``decision_points.require_active_dp`` rejects them anyway).
LEGACY_CASE_IDS: dict[str, str] = {
    "dp1-dispatch-type": "dp1.json",
    "dp2-checkpoint-split": "dp2.json",
    "dp3-worker-clarify": "dp3.json",
    "dp25-signoff-conclusion": "dp25.json",
}

HERE = pathlib.Path(__file__).resolve()
ASSET_DIR = HERE.parent.parent
DEFAULT_OUT_DIR = ASSET_DIR / "decide_cases"

#: ``preparation.prepared_at`` of the shipped case set: the recorded authoring
#: instant of this synthetic set (UTC, explicit ``+00:00``; frozen, never a per-run
#: clock read) so regeneration stays byte-identical. See the T05-R2 evidence
#: record; it is not evidence of a real preparation or authorization.
CASE_PREPARED_AT = "2026-10-27T13:45:28+00:00"

#: ``meta`` of the shipped case set: local identity only (never sent). The cases
#: are owned by this key/task and carry their own synthetic logical id; the
#: ``actor_role`` is the entry's registered initiator (eligibility only).
META_KEY = "mw-dp-consolidation"
META_TASK_KEY = "dpc-t05-eight-cases"

#: Title/note live in the case *shell* only: the monitor never forwards them to
#: validate/submit, so they can never reach the model state (design §4.5).
TITLES: dict[str, str] = {
    "dp-w-type": "派发类型：旧记录只读筛选的任务类型判定",
    "dp-pm-steer": "检查点：收窄、拆分、直接执行还是上抛人",
    "dp-w-check-task": "Worker 本次任务可达性：旧记录只读筛选",
    "dp-QG": "质量审核结论：旧记录只读筛选的验收缺口",
    "dp-gate-approve": "Gate 审批：只读筛选按获批范围收尾",
    "dp-sign-key": "Key 交付签收：四段材料与三个证据数组",
    "dp-auto": "现场行动选择：facets 接线与正文投影缺口",
    "dp-route": "临时问题路由：只选入口，不代替业务结论",
}

NOTES: dict[str, str] = {
    "dp-w-type": (
        "合成 case：材料取自只读筛选任务的原文范围，用于观察类型判定四候选；"
        "不含任何凭证或生产记录正文。"
    ),
    "dp-pm-steer": (
        "合成 case：PM 正在判断检查点动作，附一段真实形态的 worker 执行情况；"
        "选项仍由 registry 原文提供，case 不改写问题。"
    ),
    "dp-w-check-task": (
        "合成 case：worker 带着完成、剩余、阻断与预算边界判断本次任务是否可继续；"
        "investigate 分支给出有界补证的来源、预算与结束判据。"
    ),
    "dp-QG": (
        "合成 case：按审核要求、已审证据、发现与未覆盖面整理，用于观察 pass 与 "
        "fix 的差别；reopen 需要 basis_issue，本材料不预置该字段。"
    ),
    "dp-gate-approve": (
        "合成 case：PM 送审前写好 subject、planned_action 与四段依据，"
        "用于观察 gate 判断；note 本身不构成任何新授权。"
    ),
    "dp-sign-key": (
        "合成 case：按交付目标、实际完成、已验与未验、未完成影响四段整理，"
        "用于观察签收判断；三个证据数组按原数组契约给出真实内容。"
    ),
    "dp-auto": (
        "合成 case：PM 为现场问题准备了三个可区分候选（自由 id，非 cN），"
        "用于观察动态候选消费；模型只能从这批候选里选，动作仍由 PM 执行。"
    ),
    "dp-route": (
        "合成 case：主体、对象与待决问题清楚，用于观察路由只选入口；"
        "所选入口的业务结论仍需按它的合同另发一次决策。"
    ),
}

# ---------------------------------------------------------------------------
# Synthetic business material (one coherent scenario, no credentials)
# ---------------------------------------------------------------------------

#: The task these cases talk about: a read-only history filter for the monitor.
TASK_GOAL = "给 mw decide monitor 增加旧记录只读筛选，同时保持现有写入链路完全不动。"
TASK_REQUIREMENTS = (
    "只读，不写 archive、signoff 或 authority；不新增第二套事件协议；"
    "不改其余入口的既有契约。"
)
TASK_DELIVERABLES = "旧记录只读筛选的结论说明；本次任务的 report.md 与定向验证日志。"

MATERIALS: dict[str, dict[str, object]] = {
    "dp-w-type": {
        "task_goal": TASK_GOAL,
        "task_requirements": TASK_REQUIREMENTS,
        "task_deliverables": TASK_DELIVERABLES,
        # An explicit ``false`` is a real fact ("this task needs no image
        # reading"); it is still never an image-capability proof.
        "images_required": False,
    },
    "dp-pm-steer": {
        "task_goal": TASK_GOAL,
        "task_requirements": TASK_REQUIREMENTS,
        "task_deliverables": TASK_DELIVERABLES,
        "pm_decision_background": (
            "历史投影尚未交付，表结构、弹窗与本地 case 已完成；facets 下拉与"
            "正文渲染仍等后端字段。当前预算只够做一块，需要判断收窄到 facets 接线、"
            "拆成两个任务、PM 直接做完，还是以高风险上抛给人。"
        ),
        "worker_execution": (
            "已完成：五列表结构、四状态渲染、十节点 DAG 弹窗与日志弹窗。"
            "剩余：facets 下拉接线与正文渲染，等历史投影字段。"
            "阻塞：旧记录 detail 没有 workbench 字段，只能显示未记录。"
            "尝试：改过两版节点顺序，最终按后端投影顺序渲染。"
            "时间预算：已用 35 分钟，剩余 25 分钟。"
        ),
    },
    "dp-w-check-task": {
        "task_goal": TASK_GOAL,
        "reachability_facts": (
            "旧记录字段与投影函数在副本内可只读检索，表结构与弹窗已有定向用例；"
            "剩余接线依赖的 workbench 字段当前不存在。"
        ),
        "completed": (
            "已完成五列表、四状态、十节点 DAG 弹窗与日志弹窗，对应定向用例通过，"
            "日志留在本卡证据目录。"
        ),
        "remaining": (
            "facets 下拉与正文渲染仍缺后端投影字段，本任务预算内无法自证完成。"
        ),
        "blockers": (
            "旧记录 detail 没有 workbench 字段，页面只能显示未记录；补齐该字段属于"
            "投影写入方的范围。"
        ),
        "constraints": (
            "只读，不写 archive、signoff 或 authority；剩余预算 25 分钟，"
            "无新增授权，工具白名单不变。"
        ),
        "investigation": {
            "unknown": "旧记录 detail 是否已存在可复用的 workbench 投影字段。",
            "evidence_source": (
                "decision_history.py 的列表与详情投影函数，可在副本内只读检索。"
            ),
            "budget": "只读检索 10 分钟，不启动服务、不调用模型。",
            "stop_condition": (
                "找到字段来源即停止；找不到则按未记录收尾并写清阻断。"
            ),
        },
    },
    "dp-QG": {
        "review_requirements": (
            "旧记录只读筛选的验收要求：只读展示、写入链路不动、四状态与十节点 DAG "
            "断言通过、既有失败不被弱化。"
        ),
        "review_evidence": [
            "packages/multi-workers/scripts/build_decide_cases.py:1",
            "packages/multi-workers/test_decision_context_workbench.py:1",
        ],
        "review_findings": (
            "表结构、四状态与 DAG 弹窗用例通过；facets 接线与正文投影缺失，"
            "属具体整改缺口，不是要求或验收依据本身的问题。"
        ),
        "uncovered_scope": (
            "真实浏览器可见性、真实模型选择质量与投影字段补齐后的端到端未覆盖。"
        ),
    },
    "dp-gate-approve": {
        "gate_background": (
            "只读筛选已完成本地定向用例，PM 请求按获批范围在 stage 内收尾，"
            "需要 gate 判断是否批准这一受限推进。"
        ),
        "current_state": (
            "表结构、四状态与十节点 DAG 弹窗已有用例；facets 接线未完成；"
            "发布、部署与活配置变更均未执行。"
        ),
        "condition_evidence": [
            "packages/multi-workers/decision_book.py:1",
            "cmd: python -B -m pytest -p no:cacheprovider -q test_decision_context_workbench.py",
        ],
        "pm_note": {
            "subject": "只读筛选的表结构、四状态与 DAG 弹窗，按本卡 write face 收尾。",
            "planned_action": (
                "批准后仅标记本阶段收尾并交接未完成的 facets 接线，不部署、"
                "不改活配置。"
            ),
            "basis": {
                "goal": "验收要求是只读展示与既有失败不被弱化，未要求本轮补齐投影。",
                "evidence": "本卡证据目录内的定向用例日志与 changed-files 清单。",
                "budget": "剩余预算 25 分钟，只够收尾与交接，不含新实现。",
                "authority": "现有 key 的 worker 写面与只读约束；本次请求不新增授权。",
            },
        },
    },
    "dp-sign-key": {
        "delivery_goal": (
            "旧记录只读筛选在工作台可用：四状态主表、十节点 DAG、旧记录无 DAG、"
            "重试精确关联，且既有失败不被弱化。"
        ),
        "actual_completion": (
            "已完成五列表、四状态渲染、DAG 与日志弹窗、离线 case 选择与本地校验；"
            "facets 接线与正文投影未完成。"
        ),
        "verification_evidence": {
            "verified": [
                "workbench 用例中的四状态与十节点 DAG DOM 断言",
                "离线 case 生成器的逐字节漂移守卫",
            ],
            "unverified": [
                "真实浏览器窗口可见性",
                "真实模型的选择质量",
                "facets 投影接线后的端到端链路",
            ],
        },
        "unfinished_impact": [
            "facets 下拉与正文依赖投影字段，未接线前只显示未记录。",
            "真实浏览器与真实模型验收未执行，不能据此声称整条链路已验。",
        ],
    },
    "dp-auto": {
        "question": "旧记录 detail 缺少 workbench 字段时，本轮该怎样推进 facets 与正文渲染？",
        "background": {
            "task_goal": "为工作台的旧记录提供可核对的状态说明。",
            "current_state": (
                "表结构、四状态与 DAG 弹窗已有定向用例；detail 投影字段与 facets "
                "接线缺失。"
            ),
            "tried": (
                "试过按后端投影顺序渲染 DAG 节点，也试过在前端补默认值，"
                "最后撤掉了默认值。"
            ),
            "unknowns": "历史投影是否会在本轮交付 detail 字段，未知。",
            "constraints": (
                "只读，不写 archive、signoff 或 authority；剩余预算 25 分钟；"
                "无新增授权。"
            ),
        },
        "handling_options": [
            {
                "id": "wire-facets-now",
                "label": "本轮只接 facets 下拉",
                "description": "把 facets 下拉接到现有列表投影字段，正文继续显示未记录。",
                "consequence": "交互先可用，正文缺口保留并写进交接说明。",
                "risk": "低：只动只读展示，不触碰写入链路。",
                "conditions": "需要 facets 字段已在列表投影中存在。",
            },
            {
                "id": "split-projection-task",
                "label": "拆出投影字段任务再接线",
                "description": "把 detail 投影字段补齐拆成独立任务，本轮只交接依赖。",
                "consequence": "缺口由后续任务闭环，本轮交付范围变小。",
                "risk": "中：跨任务依赖需要新的调度确认。",
                "conditions": "PM 确认可拆且预算允许重派。",
            },
            {
                "id": "escalate-to-human",
                "label": "上抛给人确认优先级",
                "description": "把 facets 与正文的先后顺序交人确认，本轮不新增实现。",
                "consequence": "本轮收尾为只读用例交付，顺序由人决定。",
                "risk": "低：不产生代码动作，但会停一轮。",
                "conditions": "只有顺序确实需要人判断时才用。",
            },
        ],
    },
    "dp-route": {
        "decision_actor": "mw-dp-consolidation 的 PM",
        "decision_object": "只读筛选的 facets 接线与 detail 投影缺口",
        "question": "facets 接线与正文投影缺口，本轮应该走哪一个决策入口？",
    },
}

# ---------------------------------------------------------------------------
# PM-prepared basis (D012A): one real reason per choice the material supports
# ---------------------------------------------------------------------------

BASIS_CATALOG: dict[str, list[dict[str, object]]] = {
    "dp-w-type": [
        {
            "id": "w-type-coding",
            "text": "工作要在既有 TypeScript 模块内改代码并跑定向测试。",
            "material_refs": ["task_requirements"],
            "applies_to": ["coding"],
        },
        {
            "id": "w-type-research",
            "text": "只需核对旧记录字段来源并给出取证结论，不改代码。",
            "material_refs": ["task_goal"],
            "applies_to": ["research"],
        },
        {
            "id": "w-type-review",
            "text": "产物已存在，本次只审计其只读性与回归覆盖。",
            "material_refs": ["task_deliverables"],
            "applies_to": ["review"],
        },
        {
            "id": "w-type-vision",
            "text": "材料不含图片依赖，vision 只在图像能力已证明时才是合法选择。",
            "material_refs": ["images_required"],
            "applies_to": ["vision"],
        },
    ],
    "dp-pm-steer": [
        {
            "id": "pm-steer-narrow",
            "text": "剩余预算只够 facets 接线，收窄后可在本轮完成一块可验证的改动。",
            "material_refs": ["worker_execution", "pm_decision_background"],
            "applies_to": ["narrow"],
        },
        {
            "id": "pm-steer-split",
            "text": "投影字段与 facets 接线是两块独立工作，拆开重派能各自闭环。",
            "material_refs": ["pm_decision_background", "worker_execution"],
            "applies_to": ["split"],
        },
        {
            "id": "pm-steer-direct",
            "text": "剩余接线只涉及只读展示，PM 直接做完比再派一次更省预算。",
            "material_refs": ["worker_execution"],
            "applies_to": ["direct-exec"],
        },
        {
            "id": "pm-steer-escalate",
            "text": "投影缺口跨越写入方边界，只有人才能确认是否放宽本轮范围。",
            "material_refs": ["pm_decision_background"],
            "applies_to": ["escalate"],
        },
    ],
    "dp-w-check-task": [
        {
            "id": "check-continue",
            "text": "剩余工作都在已授权只读范围内，条件充足，可以继续。",
            "material_refs": ["reachability_facts", "constraints"],
            "applies_to": ["continue"],
        },
        {
            "id": "check-terminate",
            "text": "投影字段不在本任务授权面内，应写清完成与阻断后结束本次执行。",
            "material_refs": ["blockers", "remaining"],
            "applies_to": ["terminate"],
        },
        {
            "id": "check-investigate",
            "text": "字段是否存在只需一次有界只读检索即可确认，先补证再决定。",
            "material_refs": ["investigation.unknown", "investigation.budget"],
            "applies_to": ["investigate"],
        },
    ],
    "dp-QG": [
        {
            "id": "qg-pass",
            "text": "要求与证据一致且无未解决阻断，可以给出通过结论。",
            "material_refs": ["review_requirements", "review_evidence"],
            "applies_to": ["pass"],
        },
        {
            "id": "qg-fix",
            "text": "要求本身清楚，但 facets 与正文投影有具体整改缺口，应判整改。",
            "material_refs": ["review_findings", "uncovered_scope"],
            "applies_to": ["fix"],
        },
    ],
    "dp-gate-approve": [
        {
            "id": "gate-approve",
            "text": "note 的受限动作在现有授权与预算内，条件证据成立，可以批准。",
            "material_refs": ["pm_note", "condition_evidence"],
            "applies_to": ["approve"],
        },
        {
            "id": "gate-steer",
            "text": "收尾顺序涉及任务组织，应交 PM 发起检查点编排而不是直接批准。",
            "material_refs": ["gate_background"],
            "applies_to": ["steer"],
        },
        {
            "id": "gate-need-fix",
            "text": "facets 接线缺口是具体技术缺口，应补材料后再谈批准。",
            "material_refs": ["current_state"],
            "applies_to": ["need_fix"],
        },
        {
            "id": "gate-reject",
            "text": "当前证据不足以支撑本阶段收尾，本次推进方案应被拒绝。",
            "material_refs": ["current_state", "condition_evidence"],
            "applies_to": ["reject"],
        },
    ],
    "dp-sign-key": [
        {
            "id": "sign-finalize",
            "text": "交付目标与已验证据对齐，未完成项不影响本阶段收尾。",
            "material_refs": ["delivery_goal", "verification_evidence"],
            "applies_to": ["finalize"],
        },
        {
            "id": "sign-continue",
            "text": "facets 与正文投影仍未完成，继续推进才能满足原交付目标。",
            "material_refs": ["unfinished_impact", "actual_completion"],
            "applies_to": ["continue"],
        },
        {
            "id": "sign-user-confirm",
            "text": "真实浏览器与真实模型的验收未做，需要用户确认是否接受当前证据。",
            "material_refs": ["verification_evidence", "unfinished_impact"],
            "applies_to": ["user-confirm"],
        },
    ],
    "dp-auto": [
        {
            "id": "auto-wire-facets",
            "text": "facets 字段已存在，先接下拉是预算内可验证的一步。",
            "material_refs": ["background.current_state", "handling_options"],
            "applies_to": ["wire-facets-now"],
        },
        {
            "id": "auto-split-projection",
            "text": "投影字段与接线是两块工作，拆开才能各自闭环。",
            "material_refs": ["background.tried", "handling_options"],
            "applies_to": ["split-projection-task"],
        },
        {
            "id": "auto-escalate",
            "text": "先后顺序需要人判断，本轮不新增实现更稳妥。",
            "material_refs": ["background.constraints", "handling_options"],
            "applies_to": ["escalate-to-human"],
        },
    ],
    "dp-route": [
        {
            "id": "route-w-type",
            "text": "问题只在派工类型上，应由派发类型入口判断。",
            "material_refs": ["question"],
            "applies_to": ["dp-w-type"],
        },
        {
            "id": "route-pm-steer",
            "text": "问题涉及任务编排与预算分配，应由 PM 检查点入口判断。",
            "material_refs": ["decision_object"],
            "applies_to": ["dp-pm-steer"],
        },
        {
            "id": "route-w-check",
            "text": "问题由 worker 本次可达性引起，应由 worker 自检入口判断。",
            "material_refs": ["decision_object"],
            "applies_to": ["dp-w-check-task"],
        },
        {
            "id": "route-QG",
            "text": "问题涉及验收与质量证据，应由质量审核入口判断。",
            "material_refs": ["question"],
            "applies_to": ["dp-QG"],
        },
        {
            "id": "route-gate",
            "text": "问题是一次具体 gate 的条件是否成立，应由 gate 审批入口判断。",
            "material_refs": ["decision_object"],
            "applies_to": ["dp-gate-approve"],
        },
        {
            "id": "route-sign-key",
            "text": "问题涉及 key 交付能否签收，应由签收入口判断。",
            "material_refs": ["decision_object"],
            "applies_to": ["dp-sign-key"],
        },
        {
            "id": "route-auto",
            "text": "问题需要从 PM 已准备的现场候选里选一项，应由动态行动入口判断。",
            "material_refs": ["question"],
            "applies_to": ["dp-auto"],
        },
    ],
}


# ---------------------------------------------------------------------------
# Provenance: point every business field at its own definition line
# ---------------------------------------------------------------------------


def _first_leaf(value: object, *, minimum: int = 8) -> str:
    """First substantive string of a material value (short ids are not anchors).

    A candidate ``id`` is a key, not material text, so it is skipped: the anchor
    for ``handling_options`` is the first candidate label instead of a value that
    also appears in the prepared basis ``applies_to`` list.
    """
    if isinstance(value, str):
        return value if len(value.strip()) >= minimum else ""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key == "id":
                continue
            leaf = _first_leaf(item, minimum=minimum)
            if leaf:
                return leaf
        return ""
    if isinstance(value, (list, tuple)):
        for item in value:
            leaf = _first_leaf(item, minimum=minimum)
            if leaf:
                return leaf
        return ""
    return ""


def _line_of(text: str, needle: str, *, what: str) -> int:
    """1-based line of ``needle`` in ``text``; a missing/ambiguous needle fails."""
    matches = [
        index
        for index, line in enumerate(text.splitlines(), start=1)
        if needle and needle in line
    ]
    if not matches:
        raise SystemExit(f"build_decide_cases: cannot locate {what} in {HERE.name}")
    if len(matches) > 1:
        raise SystemExit(
            f"build_decide_cases: {what} is ambiguous ({len(matches)} lines); "
            "make the material text distinct"
        )
    return matches[0]


def _evidence_reference(prefix: str, *, what: str) -> str:
    """``path:line`` of the unique source line carrying this material.

    Material literals may be wrapped across lines, so the longest prefix that
    still matches exactly one source line is used. No match means the shipped
    literal and the recorded material drifted apart - fail loudly instead of
    pointing evidence at a random line.
    """
    text = HERE.read_text(encoding="utf-8")
    for length in range(min(len(prefix), 60), 7, -1):
        candidate = prefix[:length]
        matches = [
            index
            for index, line in enumerate(text.splitlines(), start=1)
            if candidate in line
        ]
        if len(matches) == 1:
            return f"packages/multi-workers/scripts/{HERE.name}:{matches[0]}"
    raise SystemExit(f"build_decide_cases: {what} has no unique source line in {HERE.name}")


# ---------------------------------------------------------------------------
# Case construction
# ---------------------------------------------------------------------------


def _meta(dp: str) -> dict[str, object]:
    """Local-only identity of the synthetic case (never sent to the model)."""
    return {
        "key": META_KEY,
        "task_key": META_TASK_KEY,
        "trigger_id": f"case-{dp}",
        "actor_role": decision_points.ENTRY_ROLES[dp],
        "logical_id": f"case-{dp}-v1",
    }


def _preparation(dp: str) -> dict[str, object]:
    """The PM-prepared basis catalog plus the recorded, frozen prepared_at."""
    catalog = BASIS_CATALOG.get(dp)
    if not catalog:
        raise SystemExit(f"build_decide_cases: no prepared basis for {dp!r}")
    return {
        "basis_catalog": json.loads(json.dumps(catalog, ensure_ascii=False)),
        "prepared_at": CASE_PREPARED_AT,
    }


def _business_material(dp: str) -> dict[str, object]:
    material = MATERIALS.get(dp)
    if material is None:
        raise SystemExit(f"build_decide_cases: no material for {dp!r}")
    return json.loads(json.dumps(material, ensure_ascii=False))


_MISSING = object()


def _lookup(state: object, dotted: str) -> object:
    current = state
    for part in dotted.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return _MISSING
        current = current[part]
    return current


def _evidence_for_material(dp: str, material: Mapping[str, object]) -> dict[str, str]:
    """One ``path:line`` evidence entry per registry-declared material path.

    The registry is the authority for *which* paths need evidence: required paths
    must be present, optional paths get evidence when the case uses them. A
    boolean/empty array has no text anchor of its own, so it carries no
    ``path:line`` row here (its facts are stated by the surrounding material);
    every other declared value must resolve to exactly one generator line.
    """
    evidence: dict[str, str] = {}
    required = decision_book.required_state_paths(dp)
    optional = decision_book.optional_state_paths(dp)
    for path in required:
        value = _lookup(material, path)
        if value is _MISSING:
            raise SystemExit(
                f"build_decide_cases: {dp} requires the registry field {path!r} but the "
                "case material does not define it"
            )
        leaf = _first_leaf(value)
        if not leaf:
            raise SystemExit(f"build_decide_cases: {dp}.{path} has no substantive material")
        evidence[path] = _evidence_reference(leaf, what=f"{dp}.{path}")
    for path in optional:
        value = _lookup(material, path)
        if value is _MISSING:
            continue
        leaf = _first_leaf(value)
        if leaf:
            evidence[path] = _evidence_reference(leaf, what=f"{dp}.{path}")
    return evidence


def _supported_choices(dp: str, material: Mapping[str, object]) -> tuple[str, ...]:
    """Choices this material really supports (branch-conditional fields given)."""
    supported = []
    for choice in decision_points.resolve_entry_choices(dp, material):
        if not decision_points.entry_choice_issues(dp, choice, material):
            supported.append(choice)
    return tuple(supported)


def _check_case(dp: str, material: Mapping[str, object], preparation: Mapping[str, object]) -> None:
    """Fail the generator instead of shipping a case the gate would refuse."""
    if decision_points.is_retired_dp(dp):
        raise SystemExit(
            f"build_decide_cases: {dp!r} is retired history; the generator never writes "
            "a retired case"
        )
    decision_points.require_active_dp(dp)

    material_issues = decision_points.entry_material_issues(dp, material)
    if material_issues:
        detail = "; ".join(f"{path}: {issue}" for path, issue in material_issues)
        raise SystemExit(f"build_decide_cases: {dp} material is not legal ({detail})")

    role_issues = decision_points.role_issues(dp, _meta(dp)["actor_role"])
    if role_issues:
        detail = "; ".join(f"{path}: {issue}" for path, issue in role_issues)
        raise SystemExit(f"build_decide_cases: {dp} role is not legal ({detail})")

    preparation_issues = decision_points.preparation_issues(dp, preparation, material)
    if preparation_issues:
        detail = "; ".join(f"{path}: {issue}" for path, issue in preparation_issues)
        raise SystemExit(f"build_decide_cases: {dp} preparation is not legal ({detail})")

    supported = set(_supported_choices(dp, material))
    covered = {
        choice
        for item in preparation["basis_catalog"]  # type: ignore[index]
        for choice in item["applies_to"]  # type: ignore[index]
    }
    if covered != supported:
        raise SystemExit(
            f"build_decide_cases: {dp} basis covers {sorted(covered)} but the material "
            f"supports {sorted(supported)}; every supported choice needs exactly one "
            "prepared reason"
        )
    for item in preparation["basis_catalog"]:  # type: ignore[index]
        for choice in item["applies_to"]:  # type: ignore[index]
            selection = decision_points.basis_selection_issues(
                item["id"], preparation["basis_catalog"], choice  # type: ignore[index]
            )
            if selection:
                detail = "; ".join(f"{path}: {issue}" for path, issue in selection)
                raise SystemExit(f"build_decide_cases: {dp} basis is not selectable ({detail})")

    questions = decision_points.questions_map(decision_points.get_decision_point(dp))
    question_issues = decision_points.question_override_issues(dp, questions, material)
    if question_issues:
        detail = "; ".join(f"{path}: {issue}" for path, issue in question_issues)
        raise SystemExit(f"build_decide_cases: {dp} questions are not legal ({detail})")

    sent = {
        "material": decision_points.model_state_for(dp, dict(material)),
        "preparation": dict(preparation),
    }
    encoded = decision._encode_state(sent)
    if len(encoded) > decision_points.MAX_STATE_BYTES:
        raise SystemExit(
            f"build_decide_cases: {dp} send payload is {len(encoded)} bytes > "
            f"{decision_points.MAX_STATE_BYTES}; shorten the material instead of truncating"
        )


def build_case(dp: str) -> dict[str, object]:
    """One complete schema-3 case shell for ``dp`` (deterministic, offline).

    The shell carries the DP's *complete native questions* from the registry, so
    the test page can show and edit them. Only ``instructions``/static criteria
    are editable on the observation path; dp-auto keeps
    ``material.handling_options`` as its only candidate source, so the case ships
    no second copy of the candidate set.
    """
    if decision_points.is_retired_dp(dp):
        raise SystemExit(
            f"build_decide_cases: {dp!r} is retired history; the generator never writes "
            "a retired case"
        )
    if dp not in CASE_IDS:
        raise SystemExit(f"build_decide_cases: {dp!r} is not one of the eight case ids")
    material = _business_material(dp)
    preparation = _preparation(dp)
    _check_case(dp, material, preparation)

    book: dict[str, object] = {
        "schema_version": decision_book.BOOK_SCHEMA_VERSION,
        "decision_point": dp,
        "material": material,
        "preparation": preparation,
        "meta": _meta(dp),
        "notes": {"evidence": _evidence_for_material(dp, material)},
    }
    questions = decision_points.questions_map(decision_points.get_decision_point(dp))
    return {
        "case_version": CASE_VERSION,
        "dp": dp,
        "title": TITLES[dp],
        "note": NOTES[dp],
        "questions": questions,
        "book": book,
    }


def build_cases() -> dict[str, dict[str, object]]:
    """Every case, keyed by dp id (deterministic order of :data:`CASE_IDS`)."""
    return {dp: build_case(dp) for dp in CASE_IDS}


def render_case(case: Mapping[str, object]) -> str:
    """Canonical on-disk form (stable key order, UTF-8, trailing newline)."""
    return json.dumps(case, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


#: The shipped blank template (``{"books": {...}}``): one native scaffold per
#: active entry. It is a *skeleton*, never a prepared request.
TEMPLATE_PATH = ASSET_DIR / "decide_book_template.json"


def build_template() -> dict[str, object]:
    """The blank eight-entry template, derived from the native scaffold.

    ``decision_book.scaffold_book`` is the same generator the observation seam
    uses, so the template cannot drift into a second hand-kept shape. Every book
    stays a skeleton: placeholder material/preparation/evidence and **no**
    ``meta`` - a local identity is a real producer's fact, not a template's.
    """
    return {"books": {dp: decision_book.scaffold_book(dp) for dp in CASE_IDS}}


def render_template(template: Mapping[str, object] | None = None) -> str:
    """Canonical on-disk form of the template (same rules as a case file)."""
    body = build_template() if template is None else template
    return json.dumps(body, ensure_ascii=False, sort_keys=True, indent=2) + "\n"


def write_template(out: pathlib.Path | str = TEMPLATE_PATH) -> pathlib.Path:
    """Write the blank template (offline, deterministic); returns its path."""
    target = pathlib.Path(out)
    target.write_text(render_template(), encoding="utf-8", newline="\n")
    return target


def write_cases(out_dir: pathlib.Path | str = DEFAULT_OUT_DIR) -> list[pathlib.Path]:
    """Write the eight case files; returns the written paths.

    The four legacy case files are never a target: their ids are retired and
    their filenames are refused here as well, so a future edit cannot turn the
    generator into a writer of read-only history.
    """
    target = pathlib.Path(out_dir)
    target.mkdir(parents=True, exist_ok=True)
    legacy_names = set(LEGACY_CASE_IDS.values())
    written: list[pathlib.Path] = []
    for dp, name in CASE_IDS.items():
        if name in legacy_names:
            raise SystemExit(
                f"build_decide_cases: {name} is read-only legacy history; the generator "
                "never writes it"
            )
        path = target / name
        path.write_text(render_case(build_case(dp)), encoding="utf-8", newline="\n")
        written.append(path)
    return written


def typed_status(cases: Mapping[str, Mapping[str, object]]) -> list[str]:
    """What the *current* registry says about each case (no pretending).

    ``check_book`` needs a repository root to resolve the ``path:line`` evidence,
    so this offline report covers the layers that do not touch the filesystem
    (material/preparation/questions/role/budget) and leaves the evidence
    resolution to the drift gate, which runs with the real root.
    """
    report: list[str] = []
    for dp, case in cases.items():
        book = case["book"]
        assert isinstance(book, Mapping)
        material = book.get("material")
        preparation = book.get("preparation")
        meta = book.get("meta")
        issues: list[str] = []
        if isinstance(material, Mapping):
            issues.extend(
                f"{path}: {issue}"
                for path, issue in decision_points.entry_material_issues(dp, material)
            )
        else:
            issues.append("material: not an object")
        issues.extend(
            f"{path}: {issue}"
            for path, issue in decision_points.preparation_issues(dp, preparation, material)
        )
        if isinstance(meta, Mapping):
            issues.extend(
                f"{path}: {issue}"
                for path, issue in decision_points.role_issues(dp, meta.get("actor_role"))
            )
        report.append(f"{dp}: ok" if not issues else f"{dp}: {len(issues)} issue(s): " + "; ".join(issues))
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT_DIR),
        help="output directory (default: the shipped packages/multi-workers/decide_cases)",
    )
    parser.add_argument("--quiet", action="store_true", help="only print the written paths")
    parser.add_argument(
        "--template-out",
        default=None,
        help="also (re)write the blank eight-entry book template to this path",
    )
    args = parser.parse_args(argv)
    cases = build_cases()
    written = write_cases(args.out)
    for path in written:
        print(f"wrote {path.name} ({path.stat().st_size} bytes)")
    if args.template_out:
        template_path = write_template(args.template_out)
        print(f"wrote {template_path.name} ({template_path.stat().st_size} bytes)")
    if not args.quiet:
        print("offline registry-typed validation (no filesystem evidence):")
        for line in typed_status(cases):
            print(f"  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
