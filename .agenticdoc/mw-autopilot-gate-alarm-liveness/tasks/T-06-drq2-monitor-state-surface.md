# T-06 — DRQ-2｜状态面设计（monitor 常驻行 / 抑制原因 / 无 watch 丢弃）

type: research
phase: design
key: mw-autopilot-gate-alarm-liveness
唯一证据文件: .agenticdoc/mw-autopilot-gate-alarm-liveness/evidence/research/design-drq2-monitor-state-surface-20261013.md

## 上下文（种子，不是上界）

- 项目目标锚点：`.agenticdoc/goal.md`；本 key 的 §0：**状态面优先于事件面**（时间不保险）。
- 已核实事实（RQ-1 / RQ-4）：
  - 渲染链：`monitor.ts:234 scanPendingGate` → `:335 readMonitorState`（age 在 `:427`）→ `:766 renderMonitorLines` 的 gates 段 `:879-908`（宽 110，drop 序 `1reason→2age→3scope→4drift`）。
  - 结论：**不需要新状态源**（id/kind/stage/key/`created_at`/ageMs 已收齐）；但**抑制原因无任何现成字段可承载**（`gate-reminder` 事件 `conductor.py:2721-2737` 与 `phase:"remind"` 台账行 `:2712-2720` **只在发射时写**）。
  - cap 轴唯一权威输入：`_reminder_count`（`conductor.py:2512`）；TS 已有 `readGateReminders`（`pm-orchestrator.ts:1289`）**未接入 monitor**。
  - 唯一 push 消费面要求**窗口正在 watch 该 key**（`pm-orchestrator.ts:1466-1513`，`:1489`）否则事件被丢弃；面板 `BLOCKED_ON_HUMAN` 与"全项目在飞抑制"**同源同盲区**。
  - `GateView` 缺 key/stage，且被 `autopilot-console.test.ts:384-389` 精确锁死。
- 允许自行扩大取证。

## 要求

1. **派生字段设计**：常驻行需要哪些派生字段、各自**在哪个读面算**（Python 侧 or TS 侧 or 两处）、如何保证"不落盘"且成本可控（每 tick 的读放大是多少）。
2. **抑制原因六值枚举**（`key-in-flight / stage-terminal / cap-reached / not-due / unresolved-scope / gate-queue-unreadable`）：逐值给出判定输入与计算位置（`path:line`），并给出**优先级**（一个 gate 同时符合多值时显示哪个）。
3. **`GateView` 锁死下的扩展方式**：如何在不破坏 `autopilot-console.test.ts:384-389` 断言的前提下把 key/stage/原因带上（新增视图类型？可选字段？），给两个候选方案 + 各自的改动面与风险。
4. **无 watch 丢弃的可见痕迹**：设计"事件被丢弃 ⇒ 留下可见记录"的最小落点（不要新造通道）。
5. **重启后复核检查点**：设计"重启后 pending 门禁未被新自动裁决意外改写"的检查（输入、比对、告警出口）。
6. 只读；唯一允许写的是本卡声明的证据文件。

## 交付格式

证据文件必须含以下**四个 H2 段**（逐字）：
`## 结论`、`## 证据`、`## 残留与未验证`、`## 上下文来源`。
