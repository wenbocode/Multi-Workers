# T-07: G2 提醒判定（Python 侧唯一判据 + ledger 计数）

- 波次: **1** · 依赖: T-01, T-02
- 写面（独占）:
  - `packages/multi-workers/autopilot/conductor.py`（`tick` 段 `:2330-2410`）
  - `packages/multi-workers/test_autopilot_gate_reminder.py`（**新建**）
- AC: AC-005, AC-006, AC-007 · VC: VC-007, VC-008, VC-009, VC-010
- 基线: `10446aefb`

## 目标

让"闸门在等人"从"必须有人想起来看"变成"框架主动提醒"，且**判定只做一遍**（Python），extension 只负责呈现（`T-09`）。

## 交付物

- 挂点：`def tick`（`:2330`）里，`enabled/paused` 检查（`:2340-2341`）**之后**、goal 检测（`:2344`）**之前**——挂 `orchestrate` 会漏掉 goal-change 门（它在 `:2392-2395` 早退）。
- 触发条件（三者同时）：
  1. 存在 `status == "pending"` 且 `age ≥ n × gate_reminder_after_min`（n = 该门已提醒次数 + 1）；
  2. `_workers.parallel` 中**非终态**行数 == 0（**不是** `running` 口径）；
  3. 该门未被 answered / 未达 `gate_reminder_max`。
- 计数载体：`auto-decisions.jsonl` 追加 `phase: "remind"` 行（既有 8 处消费者全部以 `row.get("phase") == "decide"` 为入口 ⇒ 对它们**不可见**）；**不得**用 `_timeline_has_event`（尾 200 窗口 ≈20 min < 60 min 第二触发间隔 ⇒ 计数会复活）。
- 去重：复用 `notified` / `escalated` Set（`tick` 内构建）；**按 `gate.key` 作用域**（stage 级门用一个 session 级去重，只提醒一次，避免 N 个 PM 窗口各推一次）。
- answered 即停：`pending_gates` 每 tick 重算；门一旦 `status ≠ pending`，零残留。
- 事件：发 `gate-reminder`（名字由 `T-03` 定义）；`data` 带门 id/key/年龄/第几次。

## 契约（不得重定义）

- 时间锚 = 门的 `created_at`（历史 v1 门也有）；**禁止**用 `expires_at`（E2 实测 21 门全 v1、该字段全缺 ⇒ 永不触发）。
- 本卡**不**改 doctor 阈值（保持 24h/72h 零扰动）；阈值一致性靠"提醒阈值 ≤1440 min 严格更早"保证。
- 不新增常驻组件、不新增 tick 之外的循环（GC-1）。
- 提醒判据的**机器事实**只由本卡产生；`T-09` 只读 ledger 呈现，不得自己再判一次（避免双判分叉）。

## [VERIFY]

- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_gate_reminder.py -q`
- `cd packages/multi-workers && python -X utf8 -m pytest test_autopilot_conductor.py test_autopilot_auto_decision.py test_doctor_gates.py -q`

## 非空洞对照（必须附在回执里）

- 用 `_timeline_has_event` 作为计数载体（改造前的朴素做法）⇒ 第 3 次提醒用例必须转红（证明 ledger 方案真的必要）。
- 把挂点从 `tick` 移到 `orchestrate` ⇒ goal-change 门用例必须转红。
- 把条件 2 从"非终态行数 == 0"改成"`running` == 0" ⇒ EXECUTE 期在飞用例必须转红。

## 风险与注意

- `conductor.py` 串行链第二段：开工前确认 `T-01` 已落、且 `tick` 段未被他人改动（`git diff`）。
- 若发现 `auto-decisions.jsonl` 有第二写者，先回报 PM（append 冲突会静默丢行）。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-07-gate-reminder/report.md`（含 `[VERIFY]` 命令原文与输出、三组非空洞对照的实际红/绿），写完立即复制到 `evidence/runs/`。
