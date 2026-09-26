# T-01: conductor 守卫包（D1 正则 + D2 reject 对称守卫 + D4 stage 单调性）

- 波次: **0** · 依赖: 无
- 写面（独占）: 
  - `packages/multi-workers/autopilot/conductor.py`（守卫段 `:297-431`）
  - `packages/multi-workers/test_autopilot_gate_guards.py`（新建）
- AC: AC-022, AC-028 · VC: VC-029, VC-030, VC-031, VC-042
- 基线: `4a207ecfb`（改动前先核对 HEAD 与写面未被他人改动）

## 目标

修 spec D-003 硬前置里的三个守卫缺陷，且**只改守卫面**：不改任何判定语义、不动 `_REQUIRED_FIELDS`、不动 `_DEP_SATISFIED`。这是自动决策上线的前置（无上界的 approve 是灾难路径）。

## 交付物

- D1：`conductor.py:310` 的消费正则 `r"(gate-\d{4})\b"` → `r"(gate-\d+)\b"`（5 位及以上 id 不再静默失效；FM 已到 `gate-6687`）。
- D2：`_apply_stalled_rejections`（`:2363-2420`）补**与 approve 对称的消费守卫**（approve 侧锚点 `:2315`/`:2319`：已消费即不再改写 key-status）；可达性来源 = `mark_stalled:3958` 只短路 `== "stalled"`，允许 `closed-legacy → stalled`。
- D4：`_set_stage_status`（`:380-407`）加**纯函数单调判据**：顺序 `pending/approved(0) < running(1) < {closed, closed-human, halted}(2)`；终态族禁回退 / 禁互转 / 禁降级；拒绝时写一条**去重**的 `stage-reopen-refused`（去重方式沿用 `_consumed_gate_ids` 同族文件派生，不得引入新状态文件）。

## 契约（不得重定义）

- 只改写的**接受/拒绝条件**，不改既有合法转换的结果；`_stage_closure`（`:616-656`）终态集一格不动。
- 去重键 = 复合 `(stage, from, to, seq)`；同一违规重复出现只留一条。
- `roadmap.py` 侧若有 stage 状态镜像，**本卡不碰**（归 T-08，避免同文件冲突）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_gate_guards.py -q`（新用例：`gate-10000` 命中、reject 重放不二次改写、`closed → running` 被拒且留痕去重）
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_conductor_stage.py test_autopilot_closure.py -q`（既有面不回归）

## 非空洞对照（必须附在回执里）

- 把正则改回 `\d{4}` ⇒ `gate-10000` 用例必须变红（VC-029 变假）。
- 删掉 reject 消费守卫 ⇒ 重放 fixture 必须出现第二次 key-status 改写（VC-030 变假）。
- 删掉单调判据 ⇒ JC `gate-0001` 式回放必须把 `closed` 改回 `running`（VC-042 变假）。

## 风险与注意

- `_set_stage_status` 调用点需枚举确认全部是"向终态推进"；若有调用点依赖"修正性回退"，记录并汇报，不要自作主张放行。
- 本卡与 T-05/T-07/T-08 同文件 ⇒ 串行（见 plan §1.2）；开工前先 `git diff --stat` 确认他段未被改。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/t-01-conductor-guards/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿）。
