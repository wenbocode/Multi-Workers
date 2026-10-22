# D1 设计调研 — dp 注册表数据结构 + 配置表 + `mw decide dp` 指令族

- key: mw-decision-substitution · card: tasks/D1-registry-config.md · type: research
- 日期: 2026-10-19 · 底座: mw-jev-provider-integration (DONE)
- 方法: 只读源码逐锚点实测（decision.py 全文 / mw.py decide 区段 / mw_common.py 锁协议 / triage-client.ts 全文）+ spec.md 交叉验证；未运行任何代码、未做 git 操作
- 行号口径: 卡片锚点与当前 HEAD 有 ±1~17 行漂移（spec.md:254-255 坑点预警的复现），本文一律用**实测行号**并标注卡面差异

## 结论

- 注册表 = 新文件 `packages/multi-workers/decision_points.py` 的冻结 dataclass 元组（DS-10），字段 id/tier/default_enabled/default_mode/questions/questions_version/build_state/executor/p0_consequences/sub_ids（Q1）。
- `decide_for(dp_id, trigger, project_dir)` 返回冻结 `DecisionOutcome`，escalated_reason 取冻结枚举（disabled-by-config / mode-suggest / transport-disabled / input-incomplete / 8 个透传 transport reason / answer-invalid / low-confidence / executor-failed / duplicate-trigger）；enabled=false 分支在 state 编码与 backend 解析之前返回，结构上不可能 spawn/联网（Q2）。
- 配置表 `.mw/decide-points.json`：8 层 fail-soft 读侧（L0 缺失=全默认 … L7 tier 冲突=enabled 胜出），`dp check` exit 0/1/2（Q3）。
- 热重载 = 模块级缓存 + `(st_mtime_ns, st_size)` 双组分签名，读侧无锁（os.replace 原子换 inode），Windows 风险与 `os.utime(ns=)` 可测方案（Q4）。
- 指令族挂 `decide_sub.add_parser("dp")`（mw.py:7508）之下再挂 action 子表，与 `mw decide set` 按 argparse 字面 token 天然分流；P0 on 缺 `--i-understand-p0` → exit 2 + 配置逐字节不变（Q5）。
- refresh = 单向合并：缺行补默认、不碰 enabled/mode/note、孤儿标 true 不删、无变化完全不写文件（保 mtime），第二次 added=0 由单调性保证（Q6）。

## Q1 注册表数据结构（DecisionPoint）

### 1.1 字段表（类型 + 生产者）

| 字段 | 类型 | 生产者 | 依据/说明 |
| --- | --- | --- | --- |
| `id` | `str`（非空，长形式如 `dp3-worker-clarify`） | 注册表作者（人；DS-10，spec.md:59） | 唯一主键；调用点只允许引用 id，未知 id 一律拒绝（spec.md:130-144；AC-011 spec.md:224） |
| `tier` | `Literal["P0","P1","P2"]` | spec §4 四问判据（可逆/机器可判/局部/无代价承诺，spec.md:64-96） | 档位只决定**默认值**与展示，运行时判定只看 `enabled`（AC-002，spec.md:215） |
| `default_enabled` | `bool` | 派生自 tier（P2→True，P1/P0→False，DS-9 spec.md:58）但**显式存储** | 防止 tier 调整静默翻转行为；`dp check` 校验 `default_enabled == (tier=="P2")`；注册表层 `__post_init__` fail-loud（注册表是代码，坏注册表要在 import 时炸，与配置表 fail-soft 相反） |
| `default_mode` | `Literal["auto","suggest"]` | DS-13（默认 `auto`，spec.md:62） | 预留给"某 dp 天生建议制"；配置行 mode 缺失时用它兜底 |
| `title` / `location` | `str` | spec §4 「决策点」「位置」两列搬运（spec.md:64-96） | `dp list`/`show` 人读输出与 `p0_consequences` 的素材 |
| `p0_consequences` | `str`（tier=="P0" 时必填，否则 `__post_init__` 拒绝） | 注册表作者 | DS-12：`dp on <P0>` 缺 flag 时 exit 2 并"列出该 dp 的不可逆后果"（spec.md:61,127） |
| `questions` | `dict[str, dict] \| None`（满足 decision.py:778-816 `_validate_input` 的 QUESTION_TYPES 约束：choice/score/noul/box，decision.py:106-110） | 注册表作者（Python 侧为唯一权威，spec.md:130 注释） | None 仅允许 suggest-only 或纯升级类 dp；非 None 则走静态校验 |
| `questions_version` | `int ≥ 1` | 注册表作者，问题集语义变更时 +1 | 落档案行 `questions_version` 字段（spec.md:170），旧档案行仍可解释（AC-006 spec.md:222） |
| `build_state` | `Callable[[Trigger], dict \| str] \| None` | 注册表作者（每个 dp 一个输入构造器，DS-10） | 产出结构化 canonical JSON ≤2 000 B（spec.md:156-162 §5.4）；复用 `_encode_state`（decision.py:402-417）做指纹，勿另写 |
| `executor` | `Callable[[dict, Any], Any] \| None` | 注册表作者 | `answers -> actual_action`；仅 status=acted 时调用；None = suggest-only 点 |
| `sub_ids` | `tuple[str, ...]`（默认空） | 注册表作者 | dp3 三切 `("dp3a-fact-lookup","dp3b-intent-human","dp3c-prior-answer")`（spec.md:97-102）；子 id 也必须在注册表可解析，`dp list` 展开显示 |
| `aliases` | `tuple[str, ...]`（默认空；不推荐新增） | 迁移期专用 | 仅用于旧短 id `dp1` 的显式迁移对照，见 1.3 |

### 1.2 问题集与 TS 侧 `DP1_QUESTIONS` 对齐（不双写）

现状：问题集字面量在 TS —— `DP1_QUESTIONS`（triage-client.ts:55-58，`triage_type`/`triage_risk` 两个 choice），随 stdin payload 发给 Python（triage-client.ts:273）。

设计（单一权威，消灭第二份字面量）：
1. **权威 = Python 注册表**（spec.md:130 "Python 侧为权威"）。dp1 的 questions 移入 `DP_REGISTRY` 对应项，`questions_version=2`（问题集从 triage-client 语义升级为注册表语义时递增并留档）。
2. **TS 侧删 `DP1_QUESTIONS` 字面量**，只持 id 常量：`export const DP_IDS = { dispatchType: "dp1-dispatch-type", ... } as const`。请求 payload 不再带 `questions`（triage-client.ts:273 改为 `{state}`）。
3. **Python 读侧兼容**：`mw decide run` 收到旧 payload 带 `questions` 时**忽略之**、以注册表问题集为准（档案行 `questions_version` 可追溯差异；旧 11 字段传输行仍可读，AC-006）。带非法 `questions` 不报错——因为不再消费。
4. **防漂移测试**（spec.md:130-144 明文要求"测试断言 TS 常量 ⊆ 注册表 id 集合"）：TS 侧测试 spawn `python -X utf8 mw.py decide dp list --json --project <tmp>`，断言 `Object.values(DP_IDS)` ⊆ 返回 id 集合。方向单一（TS⊆Python），无需 TS 读 Python 文件，也不需要 Python 读 TS——这就是"不双写"的落地：id 是字符串常量的**单份拷贝 + 一致性断言**，问题集则只有 Python 一份。
5. 同理 `decide.json` 里旧 `points.dp1.*` 键（triage-client.ts:146 消费、mw.py:691 `_DECIDE_POINT_KEYS`）降级为 legacy：授权改由 decide-points.json 决定后，`dp check` 对 decide.json 残留 `points.*` 报迁移提示；`readDecidePolicy`（triage-client.ts:132-154）改读 decide-points.json 的对应行。

### 1.3 id 迁移

triage-client.ts:47 `export const DP1_ID = "dp1"` vs 注册表长 id `dp1-dispatch-type`（spec.md:66）。单仓可同步改：TS 常量改为长 id，Python 不设 alias（`decide_for("dp1")` → 未知 id → exit 2，大声失败）。若 D 阶段想要缓冲期，再启用 `aliases=("dp1",)` 字段——但 alias 命中的档案行必须记**规范 id**，避免档案里出现双 id。

### 1.4 最终 Python 代码骨架（可编译 stub 级）

```python
"""decision_points.py — dp 注册表（唯一权威，DS-10）+ decide_for 入口（Q2）。

新文件：packages/multi-workers/decision_points.py。
配置表读取协议与 fail-soft 分层见 Q3/Q4；本骨架只锁数据结构。
"""

from __future__ import annotations

import dataclasses
import pathlib
from collections.abc import Callable
from typing import Any, Literal

import decision  # sibling：QUESTION_TYPES / DecisionInputError / _encode_state

Tier = Literal["P0", "P1", "P2"]
Mode = Literal["auto", "suggest"]

#: 配置表（唯一授权来源，DS-9）。与 decision.CONFIG_RELATIVE_PATH（.mw/decide.json，管传输）分工。
DECIDE_POINTS_RELATIVE_PATH = pathlib.Path(".mw") / "decide-points.json"

#: 冻结的 escalated_reason 值集（Q2）。
ESCALATED_REASONS = frozenset({
    "disabled-by-config", "mode-suggest", "transport-disabled", "input-incomplete",
    "answer-invalid", "low-confidence", "executor-failed", "duplicate-trigger",
    # 透传 decision.REASON_CODES 的 8 个 transport reason（decision.py:88-99）
}) | decision.REASON_CODES


def _validate_questions_static(dp_id: str, questions: dict) -> None:
    """注册表导入期校验（fail-loud），镜像 decision.py:778-816 的运行期规则。"""
    if not questions:
        raise ValueError(f"{dp_id}: questions must not be empty")
    if len(questions) > 8:  # D-004 max_questions（decision.py:196）
        raise ValueError(f"{dp_id}: questions > max_questions=8")
    for qid, spec in questions.items():
        if not isinstance(qid, str) or not qid or not isinstance(spec, dict):
            raise ValueError(f"{dp_id}: bad question entry {qid!r}")
        if spec.get("type") not in decision.QUESTION_TYPES:
            raise ValueError(f"{dp_id}: question {qid!r} has unknown type")
        if spec.get("type") == "choice" and not spec.get("choices"):
            raise ValueError(f"{dp_id}: question {qid!r} type choice requires choices")


@dataclasses.dataclass(frozen=True)
class DecisionPoint:
    """一个决策点的全部注册信息；import 期 fail-loud（坏注册表=代码 bug）。"""

    id: str
    tier: Tier
    default_enabled: bool                       # 必须等于 (tier == "P2")
    default_mode: Mode = "auto"
    title: str = ""
    location: str = ""                          # spec §4 位置列（函数名优先于裸行号，防漂移）
    p0_consequences: str = ""                   # tier=="P0" 必填（DS-12）
    questions: dict | None = None
    questions_version: int = 1
    build_state: Callable[[Any], Any] | None = None
    executor: Callable[[dict, Any], Any] | None = None
    sub_ids: tuple[str, ...] = ()
    aliases: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id:
            raise ValueError("DecisionPoint.id must be a non-empty string")
        if self.tier not in ("P0", "P1", "P2"):
            raise ValueError(f"{self.id}: tier must be P0|P1|P2")
        if self.default_enabled != (self.tier == "P2"):
            raise ValueError(f"{self.id}: default_enabled must follow tier (P2=on, P1/P0=off)")
        if self.default_mode not in ("auto", "suggest"):
            raise ValueError(f"{self.id}: default_mode must be auto|suggest")
        if self.tier == "P0" and not self.p0_consequences:
            raise ValueError(f"{self.id}: P0 dp requires p0_consequences")
        if self.questions is not None:
            _validate_questions_static(self.id, self.questions)


def _build_dp1_state(trigger: Any) -> dict:     # stub：D 阶段落位，≤2KB canonical JSON
    return {"requested_type": trigger.task_type, "cli": trigger.cli}


def _exec_dp1(trigger: Any, answers: dict) -> Any:  # stub：把建议写回 dispatch 元数据
    return {"triage_type": answers["triage_type"]["value"]}


DP_REGISTRY: tuple[DecisionPoint, ...] = (
    # 24 项逐条对齐 spec.md:64-96；此处示意首尾各一（P2 开 / P0 关）：
    DecisionPoint(
        id="dp1-dispatch-type", tier="P2", default_enabled=True,
        title="派发 type/角色/范围", location="pm/ui-bridge.ts planDispatchFrontmatter",
        questions={
            "triage_type": {"type": "choice", "choices": ["coding", "research", "review"]},
            "triage_risk": {"type": "choice", "choices": ["low", "mid", "high"]},
        },
        questions_version=2, build_state=_build_dp1_state, executor=_exec_dp1,
        aliases=("dp1",),
    ),
    DecisionPoint(
        id="dp24-pi-trust", tier="P0", default_enabled=False,
        title="pi core 交互", location="core/project-trust.ts project-trust",
        p0_consequences="影响 pi 核心信任边界，误判不可在一次重派内撤回",
    ),
    # dp2..dp23 同格式补齐（spec.md:64-96 全表搬运）……
)

_REGISTRY_BY_ID: dict[str, DecisionPoint] = {dp.id: dp for dp in DP_REGISTRY}


def get_decision_point(dp_id: str) -> DecisionPoint:
    """未知 id 一律拒绝（大声失败；spec.md:130-144、AC-011）。"""
    dp = _REGISTRY_BY_ID.get(dp_id)
    if dp is None:
        raise decision.DecisionInputError(f"unknown decision point id {dp_id!r}")
    return dp


def decide_points_config_path(project_root: pathlib.Path | str) -> pathlib.Path:
    return pathlib.Path(project_root) / DECIDE_POINTS_RELATIVE_PATH


@dataclasses.dataclass(frozen=True)
class DecisionOutcome:
    """decide_for 的唯一返回类型（raise 仅限未知 id 的 DecisionInputError）。"""

    dp: str
    status: Literal["acted", "suggested", "escalated"]
    escalated_reason: str | None                # ∈ ESCALATED_REASONS
    answer: dict | None
    actual_action: Any | None
    decision_id: str                            # "<dp>:<trigger_id>"（spec.md:170）
    archived: bool
    detail: str = ""                            # 人读补充，已经 decision._redact


def decide_for(dp_id: str, trigger: Any, project_dir: pathlib.Path) -> DecisionOutcome:
    """唯一入口：查注册表 → 查配置表 → 上抛或执行（控制流见 Q2）。"""
    raise NotImplementedError  # stub；完整分支序列见 Q2 表
```

## Q2 `decide_for` 控制流

### 2.1 分支序列（每步返回类型 + escalated_reason）

返回类型统一为 Q1.4 的 `DecisionOutcome`（frozen dataclass）；唯一 raise 是未知 id 的 `decision.DecisionInputError`（CLI 映射 exit 2，与底座唯一异常面一致，decision.py:138-143）。

| 步 | 条件 | 返回 | escalated_reason | 档案行 |
| --- | --- | --- | --- | --- |
| 0 | `dp_id` 不在注册表 | **raise** `DecisionInputError` → exit 2 | —（编程错误，非决策路径；spec.md:130-144；坑点"未知 id 静默降级"明令大声失败，spec.md:262-263） | 无 |
| 1 | 配置文件缺失 / 无该 dp 行 | 不是终点：取注册表默认值继续（P2 on / P1,P0 off；AC-001 spec.md:214） | — | 无 |
| 2 | `enabled=false`（含文件缺失后的默认 off） | `status="escalated"`，**在 build_state / client 构造之前直接返回** | `disabled-by-config` | 无（避免噪音；幂等约束不受影响） |
| 3 | 传输层未配置/关闭（`.mw/decide.json` 管传输，与授权表互不写入，spec.md:107-128 末条） | `status="escalated"`，不 spawn | `transport-disabled`（映射 `REASON_DISABLED`，decision.py:84） | 无 |
| 4 | `build_state(trigger)` 缺必需字段 / canonical 超 2KB | `status="escalated"` | `input-incomplete`（DS-4 禁止默认动作；spec.md:156-162、AC-005 spec.md:218） | 无 |
| 5 | `DecisionClient.decide` 返回 `available=false`（decision.py:630-745 内部归一化，永不抛） | `status="escalated"` | **透传**冻结 reason：`timeout` / `rate-limited` / `upstream-error` / `bad-response` / `budget-exhausted` / `entry-unavailable` / `unsupported-question-type`（decision.py:79-99） | 落 11 字段传输证据行（`_emit`→`_append_evidence`，decision.py:906-961，`available=false` 也落） |
| 6 | `mode=suggest` 且 available=true | 落档案（`kind=decide, acted=false`）→ `status="suggested"`（对外仍是"上抛人 + 附建议"） | `mode-suggest` | 有（AC-015 spec.md:228：建议只进回执/报告，**不注入 steer**） |
| 7 | 答案过不了 executor 语义校验（executor 前置断言：枚举越界/引用不存在） | `status="escalated"` | `answer-invalid` | 有（available=true 但 acted=false，reason 记 answer-invalid） |
| 8 | 低置信且 `confidence_source == "api"` 且低于阈值 | `status="escalated"` | `low-confidence` | 有；`confidence_source != api` 时**永不门控**（decision.py:268-277 "Never used for gating" 硬规则 + spec.md:230） |
| 9 | `mode=auto` 且答案有效 | `executor(answers, ctx)` → `status="acted"`，`acted=true` + `actual_action` 落档 | `None` | 有 |
| 10 | executor 执行抛异常 | `status="escalated"`（DS-4：失败→人，无默认动作；executor 必须设计成"先算后落"，保证未产生半态） | `executor-failed` | 有 |
| 11 | 同 `trigger_id` 已有 `kind=decide` 行（幂等冲突，spec.md:171-172） | `status="escalated"` | `duplicate-trigger` | 无新 decide 行 |

顺序约束：`0 → 2 → 3 → 4 → ask(5) → 6/7/8 → 9/10/11`。**enabled 检查必须先于 build_state**——state 构造可能有读盘副作用且含 L2 敏感字段，关闭时不该碰（最小暴露）。

### 2.2 enabled=false 路径零 spawn 零网络（对照 complete-bypass 语义）

三重证据，结论：结构上不可能（不是约定上不希望）：

1. **本设计**：Q2.1 步 2 的返回点位于 `build_state`、`DecisionClient` 构造、`_encode_state`（decision.py:653）与 `_resolve_backend`（decision.py:660）全部之前。而进程 spawn/网络只可能发生在 `backend.decide()` 内部——backend 协议（decision.py:166-169）之下，真实传输在 `decision_backends` 的三个后端类（LLM transitional / llmproxy-anthropic / direct-systemone，decision.py:393-398 名表）。未解析 backend ⇒ 未调用 decide ⇒ 零 spawn 零网络。
2. **同语义 TS 先例**（卡面指定对照点）：triage-client.ts:266-267 —— `const policy = input.policy ?? readDecidePolicy(...); if (!policy.enabled || !policy.dp1Enabled) return unavailable("disabled");` 早退于 :268 `const run = input.run ?? runDecideMw;`；子进程唯一创建点 `runDecideMw`（triage-client.ts:166-190，spawnSync）只在 :268 的 `run(request)` 之后触达。文件头 :14-15 明文契约："this module then performs ZERO spawn and ZERO write"。
3. **Python 底座同构**：`DecisionClient.decide` 在 `not cfg.is_configured` 时直接 `_emit(..., REASON_DISABLED, 0, None, ...)` 返回（decision.py:644-651），state 编码（:653-657）与 backend 解析（:660）都未执行——"关了就一个字节都不发"是底座既有不变量。

可测断言：FakeBackend 的 `self.calls`（decision.py:573-574）长度为 0 + monkeypatch `subprocess`/socket 计数 0；以及 `_encode_state` 未被调用（构造 client 传 spy state）。

### 2.3 dp1 通道兼容

旧链 `triageDispatch`（triage-client.ts:263-306）迁移为"组装 trigger → `mw decide run --dp dp1-dispatch-type`"，其 20s 硬超时与 fail-soft 语义保留（`DEFAULT_TRIAGE_TIMEOUT_MS`，triage-client.ts:39；异常→`available=false`，:269-306），映射为 Q2.1 步 5 的透传 reason。`readDecidePolicy` 的授权判定源从 decide.json 换到 decide-points.json（1.2 第 5 点）。

## Q3 配置表 schema 与校验

### 3.1 JSON 形状与取值域

`.mw/decide-points.json`（spec.md:107-116 示例为准，本文补齐约束）：

```json
{
  "version": 1,
  "updated_at": "2026-10-19T08:00:00Z",
  "updated_by": "human",
  "points": {
    "dp3-worker-clarify":  { "tier": "P2", "enabled": true,  "mode": "auto", "orphaned": false, "note": "" },
    "dp4-failure-handling":{ "tier": "P1", "enabled": false, "mode": "auto", "orphaned": false, "note": "2026-10-20 signoff 关闭" }
  }
}
```

| 键 | 类型/取值域 | 缺省 | 备注 |
| --- | --- | --- | --- |
| `version` | `int ≥ 1` | 视作 1（记 warning） | 见 3.2 |
| `updated_at` | ISO-8601 UTC `str` | 无 | 仅记录用，运行时不读 |
| `updated_by` | `"human" \| "refresh"` | 无 | AC-010 审计口径（refresh 是唯一机器写面，spec.md:223） |
| `points` | `object`（键=dp 规范 id） | `{}` | 未知顶层键**保留原样**（extras 先例 decision.py:286-296）+ check warning |
| `points.<id>.tier` | `"P0"\|"P1"\|"P2"` | 注册表 tier | **advisory**：只影响显示与 refresh 元数据回填，判定不读它 |
| `points.<id>.enabled` | `bool` | 注册表 `default_enabled` | **唯一授权判定字段** |
| `points.<id>.mode` | `"auto"\|"suggest"` | `"auto"` | DS-13；suggest 行为等价于未开启但对人可见（spec.md:122-123） |
| `points.<id>.orphaned` | `bool` | `false` | 仅 refresh 写 true；人手写 false 会被下次 refresh 纠正 |
| `points.<id>.note` | `str` | `""` | 自由文本 |

### 3.2 `version` 演进策略

- 读侧只接受 `version ≤ 当前已知最大版本`；`version > known` → **整表 fail-soft**（全注册表默认 + doctor warning "decide-points.json written by a newer tool; upgrade mw"）。理由：新版本可能改了行语义，猜着读比不读危险。
- 升级姿势：新字段一律可选且缺省等价旧行为；由 `refresh` 负责给旧行补新字段的默认值（只增不翻）；**永远不做静默迁移写回**（AC-010：人不在场机器不改配置文件）。
- v1 即上表；无 v0。

### 3.3 读侧 fail-soft 分层（每层独立降级，永不抛进 worker 主链）

先例：`DecisionConfig.from_project`（decision.py:326-357）——缺失=unconfigured 且 `error=None`（正常态），坏文件=disabled + error 字符串给 doctor。同样的手感：

| 层 | 情形 | 降级动作 | 告警 |
| --- | --- | --- | --- |
| L0 | 文件缺失 | **全注册表默认**（P2 on / P1,P0 off），不算错误态 | 无（这是出厂态，AC-001 spec.md:214） |
| L1 | OSError（权限/占用） | 同 L0（全默认） | doctor warning（带异常摘要，过 `_redact`） |
| L2 | JSON 语法错 | 同 L0 | warning + `json.JSONDecodeError` 摘要 |
| L3 | 顶层不是 object / `points` 不是 object | 同 L0 | warning |
| L4 | 行不是 object（如 `"dp3": true`） | **该 dp `enabled=false`**，其余行正常 | warning（spec.md:117-118："行格式坏 → 该 dp 视为 enabled=false + doctor warning，绝不因配置崩溃 worker"） |
| L5 | 行字段类型错（enabled 非 bool / mode 出枚举 / tier 出域） | 同 L4（该 dp 关） | warning |
| L6 | 未知 dp id（注册表已删） | 行保留，内存标 `orphaned=true`，**绝不静默删除**（决策档案按 decision_id 引用它，spec.md:118-119） | `dp check` 列入 orphaned 清单 |
| L7 | `tier` 与 `enabled` 冲突（行称 P2 却 enabled=false） | **以 enabled 为准**继续判定 | warning（AC-002 spec.md:215） |

实现注意：降级"该 dp 关"只在**判定时刻**生效，解析产物里同时保留原始坏值（`raw`），`dp check` 能报"第几行什么字段坏"，人修完 file 下一决策自动恢复（Q4 热重载）。

### 3.4 `dp check` 报告项与 exit 码

报告项（人读逐行 + `--json` 对象 `{path, exists, version, issues[], warnings[], orphaned[], missing_from_table[], decide_json_legacy[]}`）：

1. 文件存在性 / 是否可解析（L1/L2/L3 命中 → issue）；
2. `version` 数值与是否超出已知；
3. 未知顶层键（warning）；
4. 逐行：字段类型错 / mode·tier 出域（issue）；tier-enabled 冲突（warning，注明"运行时以 enabled 为准"）；orphaned 行清单（info）；
5. 注册表有而表缺的 dp id 清单（info，附提示"defaults apply; run `mw decide dp refresh` to materialize"）；
6. `.mw/decide.json` 残留 `points.*` 键的迁移提示（1.2/2.3，warning）。

exit 码（沿用 cmd_decide 既有约定"only invalid arguments/config writes are 2"，mw.py:970-980 docstring；doctor 的 0/1 健康位先例 mw.py:665 `return 0 if report["summary"]["healthy"] else 1`）：

- **0** = 干净（允许存在 info 级：缺行、orphaned）；
- **1** = 有 warning/issue 但表仍可用（fail-soft 在兜底）；
- **2** = 表不可用（L1/L2/L3）或命令参数非法（未知 dp id 等）。

## Q4 热重载

### 4.1 缓存放哪

- 不用 `lru_cache`：它的键是调用参数、没有按内容/mtime 失效能力，会把旧配置钉死在进程里——方向性错误。
- 两个候选：(a) 每次决策裸 stat+read+parse；(b) 模块级 dict 缓存 + `(st_mtime_ns, st_size)` 签名门控。
- **推荐 (b)，且 (a) 是可接受的 MVP 简化**。量级依据：决策频率是"每次派发/检查点/澄清"级（秒~分钟间隔），文件 <4KB，未命中路径 read+parse 在亚毫秒级，对比单次决策 5s~20s 的 LLM 往返（decision.py:196 `timeout_s=20`）可忽略。选 (b) 的理由是同进程连发多决策的场景（autopilot gate 循环、批量 `dp check`）省重复 IO，且实现只多一个模块级 dict：

```python
_DPTS_CACHE: dict[str, tuple[tuple[int, int], "DecidePointsView"]] = {}

def load_decide_points(project_root: pathlib.Path | str) -> "DecidePointsView":
    path = decide_points_config_path(project_root)
    try:
        st = path.stat()
        sig = (st.st_mtime_ns, st.st_size)      # 双组分：ns 精度 + size（防同 tick 改写）
    except OSError:
        return DecidePointsView.defaults()      # L0：缺失=全默认（Q3）
    hit = _DPTS_CACHE.get(str(path))
    if hit is not None and hit[0] == sig:
        return hit[1]
    view = parse_decide_points_fail_soft(path)  # Q3 的 L1..L7 分层
    _DPTS_CACHE[str(path)] = (sig, view)
    return view
```

- 进程边界：`mw decide run` 每次由 TS spawn 新 Python 进程（triage-client.ts:166-190），缓存天然清零；真正复用只发生在长命进程（mw serve / gate 循环）。缓存按 `str(path)` 键隔离多项目目录，不设全局失效 API——mtime 签名就是失效机制。

### 4.2 并发与锁的边界

- **读侧永不拿锁**。写入只有人执行的 CLI（on/off/set/preset）+ refresh（限只增/标孤儿），统一走 `_decide_write_config` 协议：`path.lock` + tmp 写 + `os.replace`（mw.py:773-789），锁本体 `mw_common.acquire_lock` 的 `O_CREAT|O_EXCL` 重试 20 次（mw_common.py:2369-2384；release :2386-2390）。
- 安全论证：`os.replace` 是原子换 inode——并发读者要么读到完整旧文件要么读到完整新文件，**无撕裂态**，所以读侧无锁正确。O_EXCL 锁只防 writer-writer（人同时开两个 CLI 改表），不防读写。缓存无锁化：dict 单键覆盖是 GIL 下的原子操作，最坏情况是"两个线程各 parse 一次"，结果一致。
- 边界声明：缓存签名在 stat 之后、read 之前可能过期（写者恰好插进来）——后果是本次读到旧内容、下次签名变化再刷新；决策场景可容忍（下一次决策即生效，不是本决策内生效）。

### 4.3 Windows mtime 精度风险与替代

- NTFS 时间戳名义粒度 100ns，但 (a) FAT32/exFAT 是 **2 秒**；(b) 两次快速写可能落进同一 tick；(c) Python 2 时代的 float `st_mtime` 有精度丢失——**必须用 `st_mtime_ns`（int）**，绝不比较 `st_mtime` float。
- 缓解：签名 = `(st_mtime_ns, st_size)` 双组分（即任务卡点名的 size+mtime 方案）；`_decide_write_config` 的 tmp 是新文件，`os.replace` 后 mtime=写前一刻，必然 ≥ 旧值，且内容变化几乎总是伴随 size 变化。
- 残余风险（同 tick 且同 size 的改写）接受为已知限制，兜底两条：`dp check` 增加绕过缓存的直读校验；写侧在 `updated_at` 里放 UTC 时间戳供人目检（运行时不依赖它）。
- **未验证**：FAT/exFAT 卷上 `st_mtime_ns` 的实际分辨率（本仓开发环境为 NTFS）；设计阶段建议以显式 `os.utime(ns=)` 测试固定行为，不依赖宿主时钟粒度。

### 4.4 可测的"改文件后下一次决策即生效"

1. **单元（缓存命中/失效）**：写 v1 → `load()`（填缓存）→ 改内容并用 `os.utime(path, ns=(t1, t1))`（t1 > t0，ns 级显式推进，不赌真实时钟）→ `load()` 返回 v2；再断言签名不变时返回**同一对象**（`is` 判断命中路径）。
2. **集成（决策生效）**：同一进程内 `decide_for("dp3-worker-clarify", trigger, P)` 两次，中间用 `_decide_write_config` 把该行翻 `enabled=false` → 第二次返回 `escalated_reason="disabled-by-config"`（AC-001 spec.md:214"无重启"；建议再加 mode=suggest→auto 的对称用例，覆盖 AC-015 spec.md:228）。
3. **Windows 专项**：全部测试用 `os.utime(ns=...)` 设置 mtime；跑一条"真实文件系统写入（不用 utime）+ 断言 size 变化触发刷新"的用例，覆盖 size 分量。
4. **验收证据形态**：测试名即证据（`test_decide_points_hot_reload_*`），输出 `enabled 翻转前后两次 decide_for 的 escalated_reason` 对照。

## Q5 `dp` 指令族

### 5.1 挂载与解析分流（`mw decide dp ...` vs `mw decide set ...`）

- 挂载点：现有 `decide_sub = decide_p.add_subparsers(dest="decide_action", required=True)`（mw.py:7508）下 `decide_sub.add_parser("dp", ...)`，再在其下挂 `dp_sub = dp_p.add_subparsers(dest="dp_action", required=True)` 挂 list/show/on/off/set/refresh/check/preset。
- 分流论证：argparse 子命令按**字面 token** 匹配（mw.py:981-988 `cmd_decide` 按 `args.decide_action` 分发）。`mw decide set KEY=VALUE` → `decide_action="set"`（走 `_decide_set`，mw.py:915-955，管传输表 decide.json）；`mw decide dp set <id> k=v` → `decide_action="dp"` + `dp_action="set"`（管授权表 decide-points.json 的行）。两个 "set" 处在不同层级、token 路径不同（`set` vs `dp set`），**无歧义**，不需要改既有 set 的任何解析。`cmd_decide` 只需加一个分支 `if action == "dp": return _decide_dp(args, project_dir)`（放在现有 run/probe/show/set 分支序列里任意位置均可，mw.py:970-987）。
- 命名规则写进 help 文案：`mw decide set` = transport（decide.json）；`mw decide dp set` = authorization row（decide-points.json）——对应 spec.md:107-128 末条"互不写入"。

### 5.2 命令规格（全部 `--project` 必填，`--json` 可选；exit 码 0/2 为主）

| 命令 | 参数 | 人读输出（≤6 行） | `--json` | exit |
| --- | --- | --- | --- | --- |
| `dp list` | `[--tier P0\|P1\|P2] [--all]`（默认隐藏 orphaned） | 每行 `id tier default effective mode 标记`；已开 P0 行打 **`P0-ON`**（DS-12，spec.md:127），孤儿行打 `orphaned` | `{rows:[{id,tier,default_enabled,enabled,source:"default"\|"file",mode,orphaned,p0_on}]}` | 0 |
| `dp show` | `dp_id` | 生效行 + 来源 + `questions_version` + location + p0_consequences（P0 时） | 单行对象 | 未知 id → 2 |
| `dp on` | `dp_id [--i-understand-p0]` | `enabled <id> (tier=…, mode=…)` | `{path, row}` | 见 5.3 |
| `dp off` | `dp_id` | 同 on | `{path, row}` | 0；未知 id 2 |
| `dp set` | `dp_id KEY=VALUE...` | `updated <id>` | `{path, row}` | 非法键/值 2（**先全量校验后写**，先例 `_decide_set` 经 `DecisionConfig.from_dict` 校验再落盘，mw.py:950-953） |
| `dp refresh` | 无 | `refresh: added=N kept=M orphaned=K total=T` | `{added,kept,orphaned,total}` | 0（表不可写 → 2） |
| `dp check` | 无 | 逐项报告（Q3.4 清单） | `{path,exists,version,issues,warnings,orphaned,missing_from_table,decide_json_legacy}` | 0/1/2（Q3.4） |
| `dp preset` | `disable\|enable\|advance` | 写入的行清单 | `{changed:[ids]}` | 0；未知档名 2 |

- `preset`（DS-1，spec.md:55）：`disable`=全部行 enabled=false；`enable`=P2 档开；`advance`=P2 档开 + 指定 P1 清单开。只改它点名的行，写 `updated_by="human"`；"指定 P1 清单"的成员 spec 未定死（残留项见文末），骨架上作为注册表常量 `ADVANCE_PRESET_P1: tuple[str, ...]` 留待 D 阶段落位。
- 人读输出显式 UTF-8 落盘/打印（Windows GBK 控制台坑，spec.md:266-267；CLI 侧沿用 `-X utf8` spawn 先例 triage-client.ts:169-171）。

### 5.3 P0 门槛（DS-12：三道门）

`dp on <P0-dp>` 缺 `--i-understand-p0` 时：
1. 打印注册表 `p0_consequences` 字段全文（Q1.1：该字段 tier=="P0" 时必填，import 期强制）；
2. **exit 2，配置逐字节不变**——fail-closed 可测：写测试断言命令前后 `decide-points.json` 的 sha256 相等（AC-002 spec.md:215"无 flag 则 exit 2 且配置不变"）。

成功路径：写 `enabled=true` + 追写档案行 `kind=authority-change, by=human:p0-confirm`（spec.md:127；档案协议 spec.md:166-176）；此后 `dp list` 对该行显示 `P0-ON`。`off` 无需 flag（关是安全方向）。DS-12 明确**不保留代码硬拒**——P0 可开，门槛是确认+留痕+签收必列，否则"唯配置论"不成立。

### 5.4 `dp set` 允许的键集合（白名单）

`{"enabled": bool, "mode": "auto|suggest", "note": str, "tier": "P0|P1|P2"}`（spec.md:119"set 白名单字段 tier|enabled|mode|note"）。类型收敛复用 `_decide_coerce`（mw.py:727-744，bool/int/number/str 四型；mode/tier 出域在 coerce 后再做枚举校验）；写路径复用 `_decide_write_config`（mw.py:773-789）。`enabled` 之外的键改动不触发判定变化；`tier` 改动永远只是元数据（Q3.1 advisory 定位）。

### 5.5 机器零写配置的 CLI 边界（AC-010，spec.md:223）

全仓允许写 `decide-points.json` 的路径穷举 = 4 个人口命令（`dp on/off/set/preset`，全部仅人执行）+ `dp refresh`（限"补缺失行/标孤儿/回填缺失元数据"，永不触碰已有 `enabled/mode/note` 现值，见 Q6）。`dp apply <file>`（签收建议批量应用）在 agent 会话内拒绝执行（spec.md:186、AC-009 spec.md:226）——它不属于本指令族 MVP，仅在 help 里注明拒绝语义。

## Q6 `refresh` 合并算法（注册表 → 配置表，单向）

### 6.1 伪代码

```python
def dp_refresh(project_dir: pathlib.Path) -> dict:
    reg = _REGISTRY_BY_ID                          # 权威侧（代码，DS-10）
    path = decide_points_config_path(project_dir)
    table = _read_raw_table(path)                  # 原始 dict；缺失/全坏 → {"version": 1, "points": {}}
    points = table.setdefault("points", {})
    added = kept = newly_orphaned = 0
    changed = False
    for dp_id, dp in reg.items():
        row = points.get(dp_id)
        if not isinstance(row, dict):              # 缺行；或行不是对象（坏行按缺失重建，见 6.4）
            points[dp_id] = {"tier": dp.tier, "enabled": dp.default_enabled,
                             "mode": dp.default_mode, "orphaned": False, "note": ""}
            added += 1
            changed = True
        else:
            row.setdefault("tier", dp.tier)        # 只回填**缺失**元数据；
            kept += 1                              # enabled / mode / note 现值永不触碰
    for dp_id, row in points.items():
        if dp_id not in reg and isinstance(row, dict):
            if row.get("orphaned") is not True:
                row["orphaned"] = True             # 标记，绝不删除（决策档案按 decision_id 引用它）
                newly_orphaned += 1
                changed = True
    if changed:                                    # 无变化 → 完全不写文件（保 mtime ⇒ 不惊动 Q4 缓存）
        table["updated_by"] = "refresh"            # AC-010 唯一机器写面（spec.md:223 括号豁免）
        table["updated_at"] = _utc_now_iso()
        _decide_write_config(path, table)          # 锁 + tmp + os.replace（mw.py:773-789）
    return {"added": added, "kept": kept, "orphaned": newly_orphaned, "total": len(points)}
```

### 6.2 规则逐条对卡（RQ-6 要求项）

- **新增缺失行用默认值**：`enabled=default_enabled`（tier 派生）、`mode=default_mode`（默认 auto）——新 dp 从注册表出现到被人表态之前，行为=出厂默认（P2 on / P1,P0 off，DS-9）。
- **不动已有 `enabled/mode`**：合并只在 `isinstance(row, dict)` 为假（缺行/坏行）时写行；命中行唯一可写的是 `setdefault("tier", …)`（行里本来就没有 tier 才补）。
- **孤儿标 `orphaned` 不删**：`decisions.jsonl` 的 `decision_id = "<dp>:<trigger_id>"`（spec.md:170）长期引用历史 dp id；物理删行会让 `dp show`/报告无法解释档案。
- **`updated_by=refresh` 写**：写。它是 AC-010 审计 grep 的豁免锚——审计口径为"`updated_by=="refresh"` 的写入只允许 added/orphaned/tier 回填三类 diff"，可写一条测试直接 diff 前后两份 JSON 验证。

### 6.3 幂等性证明（第二次 added=0）

不动点论证：`added` 只在 `dp_id ∉ points 或行非 dict` 时 +1；第一遍跑完后注册表每个 id 都有 dict 行，该条件恒假 ⇒ `added=0`；同理所有孤儿已 `orphaned=True` ⇒ `newly_orphaned=0`；于是 `changed=False` ⇒ **第二次连文件都不写**，返回 `{added:0, kept:24, orphaned:0, total:N}` 且文件 mtime 不变（Q4 缓存签名不变，零扰动）。合并操作对"行存在性"单调（只增），故任意次重复收敛于同一状态。

### 6.4 输出计数格式与边界

- 口径：`added`=本次新建行数；`kept`=注册表命中已有行数；`orphaned`=**本次新标**孤儿数（非存量总数，存量看 `dp check`）；`total`=表内总行数（含孤儿）。人读一行与 `--json` 同口径。
- 坏行（非 object）：按缺失重建为默认行并计入 `added`，同时打 warning 附原值（JSON 序列化的旧行内容）——非对象行无法承载 `enabled`，保留只会让该 dp 永远停在 fail-soft 关闭态（Q3 L4），重建让人的一次 refresh 就拿到正确默认值。
- 24 项注册表首跑的期望输出：`refresh: added=24 kept=0 orphaned=0 total=24`（文件缺失时）。

## 证据

实测锚点清单（当前 HEAD；卡面行号漂移已在括号内标注）：

| 断言 | 锚点 |
| --- | --- |
| reason 冻结值集 8 个 | `packages/multi-workers/decision.py:79-99` |
| 传输证据行 11 字段 | `decision.py:121-134`（`_EVIDENCE_FIELDS`）；append 先例 `decision.py:940-961` |
| 唯一异常面 DecisionInputError→exit 2 | `decision.py:138-143`；docstring `mw.py:970-980` |
| 配置读 fail-soft 先例 | `decision.py:326-357`（from_project：缺失=unconfigured+error=None；坏文件=disabled+error） |
| extras 保留未知键先例 | `decision.py:286-296` |
| 脱敏 `_redact` | `decision.py:378-387`（卡面同） |
| state 规范化 `_encode_state` | `decision.py:402-417`（卡面同） |
| 置信度永不门控 | `decision.py:268-277`（`_aggregate_confidence` docstring） |
| questions 运行期校验 | `decision.py:778-816`；QUESTION_TYPES `decision.py:106-110` |
| 预算常量（timeout 20s 等） | `decision.py:190-197`（D-004） |
| is_configured 早退（REASON_DISABLED） | `decision.py:644-651` |
| state 编码/backend 解析在配置检查之后 | `decision.py:653-657`、`decision.py:660` |
| FakeBackend 调用计数 | `decision.py:573-576` |
| backend 名表（传输=三后端） | `decision.py:393-398` |
| `_DECIDE_SET_KEYS` 白名单 | `mw.py:673-689`（卡面 672-688，+1 行） |
| 旧 point 键白名单 | `mw.py:691`（`_DECIDE_POINT_KEYS`） |
| KEY=VALUE 解析与类型收敛 | `mw.py:746-770`、`mw.py:727-744`（`_decide_coerce`） |
| 原子写协议（锁+tmp+replace） | `mw.py:773-789`（卡面 772-792，±1） |
| `_decide_run` | `mw.py:795-813`（卡面 794-813） |
| `_decide_set` 先校验后写 | `mw.py:915-955`（校验调用 `mw.py:950-953`） |
| `cmd_decide` 分支与 exit 约定 | `mw.py:970-988`（卡面 953-987，+17 行漂移） |
| doctor 0/1 健康位先例 | `mw.py:665` |
| decide 子命令树挂载点 | `mw.py:7500-7534`（`decide_sub` 在 `mw.py:7508`） |
| `acquire_lock` O_CREAT\|O_EXCL ×20 | `mw_common.py:2369-2384`（卡面同）；`release_lock` `:2386-2390` |
| complete-bypass（零 spawn 零写） | `triage-client.ts:14-15`（头注释）、`:266-267`（早退）、`:268`（run 解析在后）、`:166-190`（唯一 spawn 点 runDecideMw） |
| `DP1_QUESTIONS` / `DP1_ID` | `triage-client.ts:55-58`、`:47` |
| 20s 硬超时 | `triage-client.ts:39` |
| readDecidePolicy（decide.json 授权旧源） | `triage-client.ts:132-154`（`points.dp1` 消费在 `:146`） |
| questions 随 payload 下发（待删） | `triage-client.ts:273` |
| DS-9..DS-13 用户裁定 | `.agenticdoc/mw-decision-substitution/spec.md:58-62` |
| 24 dp 表 + 三档落位 | `spec.md:64-96`；dp3 三切 `spec.md:97-102` |
| 配置表规则（fail-soft/热生效/CLI/P0 门槛/与 decide.json 分工） | `spec.md:107-128` |
| 代码侧 dp 抽象（DS-10）与 TS⊆注册表断言 | `spec.md:130-144` |
| 档案 4 类行 / decision_id 幂等 | `spec.md:166-176` |
| AC-001/002/005/006/010/011/012/015 | `spec.md:214-228` |
| 行号漂移坑预警（本文复现实证） | `spec.md:254-255`；Windows/PS 坑 `spec.md:266-267` |

## 残留与未验证

1. **行号漂移实证**：卡面锚点 vs 实测——`_DECIDE_SET_KEYS` 672→673、`_decide_write_config` 772→773、`_decide_run` 794→795、`cmd_decide` 953→970（+17）。本文全部按实测引用；设计阶段引用处请以本文"证据"表为准并随实现复核。
2. **未验证（无法静态确认）**：FAT/exFAT 卷上 `st_mtime_ns` 的实际分辨率（本文按 NTFS 100ns 名义值论述，测试方案已规避对真实时钟粒度的依赖，见 Q4.3/Q4.4）。
3. **未验证**：`decision_backends.py` 三个后端内部是否还有除 `backend.decide()` 之外的 spawn/网络副作用——本文按 decision.py 协议面（`DecisionBackend.decide`，decision.py:166-169）论证 decide_for 早退路径不触网；backend 内部结构未逐行审（不在本卡读面必需范围内，D 阶段实现 decide_for 时以 FakeBackend 计数测试闭环）。
4. **spec 留白**：DS-1 `advance` 预设的"指定 P1 清单"成员未定死（spec.md:55 仅 "P2+指定 P1"）；本文以 `ADVANCE_PRESET_P1` 常量占位，建议 D 阶段落位（候选 dp4/dp17，依据 spec.md:71,88 的 P1 档成员）。
5. **迁移决策待 D 确认**：`dp1` 旧短 id 是否设 `aliases`（本文推荐不设、单仓一次性改常量）；`decide.json` 残留 `points.*` 是"仅提示"还是"一次性清理命令"，本文取"仅 check 提示"（AC-010 机器零写约束下最保守）。
6. 本任务只读：未运行任何 Python/TS 验证代码，全部结论基于源码与 spec 静态核对。

## 上下文来源

- 任务卡：`.agenticdoc/mw-decision-substitution/tasks/D1-registry-config.md`（RQ-1..RQ-6 + 交付格式 + 验收命令）
- 定稿 spec：`.agenticdoc/mw-decision-substitution/spec.md`（rev3；§3 用户裁定 / §4 注册表 / §5 配置表与执行面 / §8 AC）
- 源码（只读）：`packages/multi-workers/decision.py`（全文）、`packages/multi-workers/mw.py`（640-1019、7490-7545）、`packages/multi-workers/mw_common.py`（2350-2400）、`packages/coding-agent/src/extensions/agent-team-loop/pm/triage-client.ts`（全文）
- goal 锚点：`.agenticdoc/goal.md`（文件驱动去中心化协调 / goal 对齐——本设计的"配置表=项目侧文件、注册表=代码侧"分工即其投影）

Q-answered: 6/6
