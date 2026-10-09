# T-19: case 2 生产者接线（本 key 主交付的最后一块）

- 波次: **3** · 依赖: T-07（自动决策核心）、T-08（`defer_key_to_review` 入口 + 收口前置）
- 写面（独占）: `packages/multi-workers/autopilot/conductor.py`（自动决策段：`_auto_decide_one` 邻域，约 `:5645+`）、`packages/multi-workers/test_autopilot_pending_review.py`（追加用例）
- AC: AC-027, AC-028 · VC: VC-039..VC-043
- **来源**：T-08 回执自报残留 + PM 独立复算确认

## 问题（实证）

`defer_key_to_review`（case 2 入口，`conductor.py:3031`）**只有测试在调**：

```
conductor.py:3031  def defer_key_to_review(
test_autopilot_pending_review.py:442  gate_path = conductor.defer_key_to_review(...)
```

生产路径**没有任何调用者**（全仓 `grep defer_key_to_review` 只有这两处），且 `PENDING_REVIEW_STATUS` 的唯一写入点就在该函数内部（`:3066`）。
⇒ **`pending-review` 在生产中不可达** ⇒ 三分处置的 case 2 是死代码；除非自动应答命中 case 1，否则 key 依旧**无限期停在 gate 等人**——正是本 key 要解决的主症状。

## 交付物

在自动决策的**放弃路径**上接线（落点：`_auto_decide_one` 内部，命题为假 / 附加理由不满足 / 规则不可自动执行的分支）：

1. **可延后 kind 白名单**（冻结，写在模块级常量旁并加注释引用 design 决策树）：
   `DEFERRABLE_GATE_KINDS = ("stalled", "budget-exhausted")` —— 这两个"可恢复、不挡不可逆动作"；
   `stage-confirm`/`stage-close`（挡不可逆的 stage 转移）与 `goal-change`/`xkey-authorize`（政策性授权）**一律不得延后**，只作 case 3 = 当场人审。
2. 命中白名单且机器**不能**应答时：`defer_key_to_review(project_root, st, key)`（该入口已幂等，重复调用安全）。
3. **必须**以 `_auto_mode_active(project_root)` 为门控（`off` ⇒ 零行为差异，字节不变；这是用户的硬约束，也是 T-07 全链的门控口径）。
4. 延后**不是应答**：门保持 `pending`，不得写入 `consumed_at`/`answered_by`，不得产生 `gate-auto-decision`；只改 key-status 并留 `pending-review` 事件（沿用 T-08 的事件形状）。
5. 若该 key 已有 in-flight 行或已 `pending-review`，直接跳过（entry 已幂等，但不得产生噪声事件）。

## 契约（不得重定义）

- `pending-review` 的既有不变量**不得**改动：不计 stage 终态、不进 `_DEP_SATISFIED`、进 `_DISPATCH_SKIP_STATUSES`、收口前置（同 stage 其它 key 全终态 ∧ 无 in-flight ⇒ 批量 `review-escalated{trigger=closure}`）、48h 读 `expires_at`。
- 不得新增 key-status 值、不得让 conductor 自动重开 stage、不得给 `pending-review` 加 `done`/`closed-legacy` 出口。
- 不得触碰 T-07 的 6 条规则本体与其 guard/approve 划分（本卡只加"放弃路径"的处置）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_pending_review.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_auto_decision.py test_autopilot_closure.py test_autopilot_conductor.py -q`

## 可达性判据（本卡的核心，必须端到端）

新增用例：构造一个 key 的 `stalled` 门、令其事实面为假（即机器不能应答），以 `auto_gate_mode: live` 驱动一次自动决策 pass，断言：

1. 该 key 的 status 变为 `pending-review`；门仍 `pending`、无 `consumed_at`；
2. 该 stage 的其它 key 全终态后，出现**批量** `review-escalated{trigger=closure}` 事件，且 `_stage_closure` 拒绝收口；
3. 答复该门（review 决策）后 key 回到 `running`/`stalled`（无 `done` 出口）。

## 非空洞对照（必须附）

- 去掉接线 ⇒ 可达性判据必须红（并贴出"status 仍为 `stalled`、无 `pending-review` 事件"的原始输出）。
- 把 `stage-close` 塞进 `DEFERRABLE_GATE_KINDS` ⇒ "不可逆 kind 永不延后"的判据必须红。
- `auto_gate_mode: off` ⇒ 同一场景下 key-status **逐字节不变**（贴出前后文件/行对照）。

## 风险与注意

- 与 T-18 同文件（`conductor.py`）⇒ **T-18 未终态前不得开工**。
- 自动决策 pass 的异常必须逐门隔离（T-07 已有 `try/except`）；延后失败只记 `config` 事件，不得让 tick 死掉。
- 若发现"延后会让某个既有判据（如 dispatch 跳过集/收口前置）产生新副作用"，**停下来报 PM**，不要自行放宽不变量。

## 回执

结果写入 `.agenticdoc/mw-autopilot-slot-capacity/workers/msc-t19-case2-producer/report.md`（含 `[VERIFY]` 原文与输出、可达性端到端三步的原始证据、三条反向对照的红/绿、残留风险）。
