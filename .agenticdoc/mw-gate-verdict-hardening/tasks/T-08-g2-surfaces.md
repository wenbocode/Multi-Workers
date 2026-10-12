# T-08: G2 呈现（monitor 层 A + console 层 B）

- 波次: **1** · 依赖: T-05
- 写面（独占）:
  - `.../agent-team-loop/autopilot/monitor.ts`（类型区 `:156-176`、采集区 `:355-386`、渲染 `:707-727`）
  - `.../agent-team-loop/autopilot/console.ts`（门行呈现段）
- AC: AC-008 · VC: VC-011
- 基线: `10446aefb`

## 目标

把"哪个门挂了多久 / 是不是真在等人"放到**第一眼能看到**的位置（层 A 面板 + 层 B 状态视图），且与 gate 文件真值的偏差不超过一个 tick。

## 交付物

- `monitor.ts`：
  - `MonitorSnapshot`（`:170-176`）或 `MonitorAutopilot`（`:156-168`）增 snapshot 级 `blockedOnHuman: boolean`；
  - 采集在 `readMonitorState`（`:287`）内完成，`return` 在 `:386`；
  - 渲染：`if (s.autopilot.enabled)`（`:707`）分支内、attention 列表（`:724-727`）**之前**插入 `BLOCKED_ON_HUMAN` 置顶行；`trunc` 到 `MONITOR_LINE_MAX`；
  - 门行显示 `age=`（复用 `formatDuration:651-658`）。
- `console.ts`：`/autopilot status` 门行显示 pending 时长（消费 `T-05` 的 `GateView.ageMs`）。
- 面板高度**不得**在 tick 之间抖动：所有 section 始终存在（0 pending 也出行）。

## 契约（不得重定义）

- `blockedOnHuman` 真值表与 `T-07` 同口径（"有 pending 门 ∧ 非终态行数 == 0"）。
- `monitor.ts` **不得新增写路径**（既有用例 `autopilot-monitor.test.ts:412` 锁"三 tick 文件字节不变"）。
- `BLOCKED_ON_HUMAN` 字面量全仓唯一，不得在别处再造同义标记。
- `MONITOR_LINE_MAX` 截断规则保持"头保留"。

## [VERIFY]

- `cd packages/coding-agent && node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-monitor.test.ts test/suite/autopilot-gate-presentation.test.ts test/suite/autopilot-console.test.ts`

## 非空洞对照（必须附在回执里）

- 造"有 pending 门 + 0 在飞"与"有 pending 门 + 1 在飞"两个夹具 ⇒ `blockedOnHuman` 必须分别为 true/false（真值表非恒真）。
- 摘掉置顶行 ⇒ VC-011 的 `blocked_marker=true` 必须转红。

## 风险与注意

- **`monitor.ts` 是串行链第一段（T-08 → T-13）**：本卡不得触碰 T-13 的字段（`collectedAtMs`/`tickCount`/降级帧），也不得提前改 `startMonitor` 的生命周期段。
- `autopilot-monitor.test.ts:230/483/605` 用 fake timers（`vi.advanceTimersByTime(4000)`、`startMonitor(root, apply, { nowMs })`）——沿用同一装配方式。
- 面板行数变化会让 `autopilot-console.test.ts:374-378` 的精确 `toEqual` 转红：把新期望值写进回执，由 `T-14` 统一刷新。

## 回执

结果写入 `.agenticdoc/mw-gate-verdict-hardening/workers/t-08-g2-surfaces/report.md`（含 `[VERIFY]` 命令原文与输出、非空洞对照的实际红/绿），写完立即复制到 `evidence/runs/`。
