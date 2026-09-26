# T-07: 命题重写 + 自动决策核心（留痕/配额/熔断/影子/对账）

- 波次: **2** · 依赖: T-05, T-06
- 写面（独占）: 
  - `packages/multi-workers/autopilot/conductor.py`（命题/自动决策段）
  - `packages/multi-workers/test_autopilot_auto_decision.py`（新建）
- AC: AC-016, AC-017, AC-018, AC-019, AC-020, AC-024, AC-025, AC-029 · VC: VC-018, VC-019, VC-020, VC-021, VC-022, VC-023, VC-033, VC-034, VC-035, VC-036, VC-046, VC-047
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

把"门问什么"从恒真同义反复改成**可为假的事实面命题**，并让自动决策有条件、可审计、可回滚、可影子、可熔断。**这是本 key 的主交付。**

## 交付物

- 6 门事实面谓词（纯函数）：`stage-confirm`（结构校验空 ∧ goal sha 匹配）、`stage-close`（每 key verdict `meets`/`closed-legacy` ∧ `open_items` 空）、`stalled`（`reason_code` == 复算 `cause_class` ∧ 计数一致 ∧ `false_negative_class != undecidable`）、`budget-exhausted`（`used == limit + credits` ∧ blocking gaps 非空）、`goal-change`（前后 sha 不同 ∧ **仅规范面变更才起门**）、`xkey-authorize`（`red_after == 0` ∧ `rc == 0` ∧ `test_id` 绑定 ∧ `blast_radius ⊆ write_scope`）。
- `reason_code` 闭集 + 12 个 `mark_stalled` 调用点（`:900/986/991/1014/1099/1117/1635/1664/1690/1723/1737/1941`）的**逐点映射表**（写入卡内证据）。
- **恒真自检**：命题必须"可以为假"（F2）；无法证伪 ⇒ 直接归 case 3，不得进 case 1。
- 自动决策执行：`gate-auto-decision` 事件 + `auto-decisions.jsonl` 账本（append-only）+ 权威字段全部 conductor 派生 + 消费记录联动（T-05 字段）。
- `auto_gate_mode` 三态：`off`（行为与今天一致）/ `shadow`（只写账本、状态零改动）/ `live`（执行）；配额复用 P1–P9；**熔断状态落盘**（重启后仍熔断）；熔断动作 = 升级给人。
- `gate-auto-revoke` + 消费集合 = `answered − revoked`（按 `decision_id`）。
- 对账：`claimed_done ∧ ¬bound_meets` ⇒ `evidence-reconciliation` 事件 + **拦新的 stage-close 转换**（`:628-630` 之前加前置）；历史只 warn 不回退。

## 契约（不得重定义）

- `answered_by`/`answered_at` 只作展示，审计不得以其为权威。
- 影子门槛：≥5 夜 ∧ ≥20 条影子决策 ∧ 每条拟上线规则 ≥1 个"命题为假"反例（未达门槛 ⇒ `live` 不可开启）。
- `_DEP_SATISFIED` 不含 `pending-review`；`_REQUIRED_FIELDS` 不动。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_auto_decision.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_closure.py test_autopilot_audit.py -q`

## 非空洞对照（必须附在回执里）

- 恒真命题 fixture（命题主语 = 建门条件本身）⇒ 必须**拒绝自动**（VC-035 红若放行）。
- 每条规则构造一个"命题为假"反例 ⇒ 必须不自动（VC-036）。
- `shadow` 模式跑一遍 ⇒ gate 文件字节与 key-status **零改动**（VC-033）。
- 熔断后重启进程 ⇒ 仍必须熔断（落盘生效；内存态会红）。
- 撤销一条决策 ⇒ 消费集合只少那一条，其它不动（VC-023）。
- 改 `answered_by` 伪造来源 ⇒ 审计权威字段不受影响（VC-046 红若读取该字段）。

## 风险与注意

- 本卡与 T-05 同文件且是最大改动面 ⇒ 严格串行；建议先落谓词（纯函数 + 单测）再接触执行链。
- CS 侧的 `stage-close` 事实面**只作守卫**（必要不充分）：过了守卫**不等于**放行，仍归 case 3 —— 这句必须写进代码注释，防止后人把守卫当许可证。
- `xkey-authorize` / `goal-change` 的政策面**永不自动**。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-07-auto-decision-core/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
