# T-10 — 状态面：pending gate 常驻行 + stage 主闸行 + 六值抑制原因

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-001, AC-003, AC-010, AC-016
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/design.md` §2 D1/D3、§3 接口契约、§5 验证策略；
      `evidence/research/design-drq2-monitor-state-surface-20261013.md`、`spec-rq1-reminder-chain-20261013.md`、`spec-rq4-schema-and-view-surface-20261013.md`

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（无人值守并行开发；编排链路自身不得静默失效）。
- 已核实锚点（自行复核，勿凭本卡断言）：
  - `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts:234`（`scanPendingGate`）、`:335`（`readMonitorState`）、`:427`（age 计算）、`:766`（`renderMonitorLines`）、`:879-908`（gates 段渲染）。
  - `.../autopilot/status-model.ts:660-701`（冻结 40 名序 TS 镜像）、`:1349-1356`（`blocked_on_human`）、`:873`（parser 保留 None 的形态）、`:1003-1013`（readdir/readFile 失败静默退化为 0 pending 的位置之一）。
  - `.../pm/pm-orchestrator.ts:1289`（`readGateReminders`，**已存在但未接入 monitor**）、`:1466-1513`（push 消费面）、`:1489/:1490/:1511`（三处丢弃点）。
  - `packages/multi-workers/autopilot/conductor.py:2512`（`_reminder_count`，cap 轴唯一权威）、`:2558`（全项目级在飞抑制）、`:2688-2735`（发射与台账写入、无 stderr）。
- 关键事实：`GateView` 缺 key/stage 且被 `test/suite/autopilot-console.test.ts:384-389` 精确 `toEqual` **锁死** ⇒ 只能扩展，不能破坏断言。
- 症状锚：事故形状（keyed gate + reason）下现行 drop 序先丢 `reason` 再丢 `age`（141→120→109 列），与"原因恒可见"冲突。

## 要求

1. **常驻 pending-gate 行**：每个 `pending` gate 恒显示 id/kind/key/stage/已等时长/**抑制原因**/scope 可解析性；无 cap、无衰减、无去重；数据取自磁盘并在读面派生，**不依赖任何事件**。
2. **stage 主闸行（AC-016）**：显示每个 stage 的状态（pending/running/closed/halted）+ 卡在哪道门（stage-confirm / stage-close / stalled 冻结 / 预算 / goal-change）+ 已等时长 + 被冻结的 key 列表。依据 `conductor.py:671 _stage_activation` 是"是否放行逐 key 派发"的开关（调用点 `:245-247` 提前 return）。
3. **六值抑制原因封闭枚举**：`gate-queue-unreadable / key-in-flight / cap-reached / stage-terminal / not-due / unresolved-scope`，**优先级 = 代码漏斗序**（`queue-unreadable > key-in-flight > cap-reached > stage-terminal > not-due`；`unresolved-scope` 与抑制正交）；到期必须显式 `reason=-`（不得用空值冒充未知）。cap 轴输入接 `readGateReminders`（`pm-orchestrator.ts:1289`）。
4. **drop 序修正**：`reason` 与 `age` 最后丢（不得先丢 reason）。
5. **不得静默吞队列不可读**：`readdir`/`readFile` 失败必须显示为 `gate-queue-unreadable`（现状退化为"0 pending"）。
6. **无 watch 丢弃留痕（AC-010）**：`pm-orchestrator.ts:1489/:1490/:1511` 的丢弃必须留下可见记录（面板状态行或独立 entry，不新造日志文件）。
7. `blocked_on_human` 的 per-key 改造只做`status-model.ts:1349-1356` **这一处**（另两处由 T-11 负责），不得提前改其他文件。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/status-model.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
- `packages/coding-agent/test/suite/autopilot-console.test.ts`（**仅允许新增用例，不得修改 `:384-389` 既有断言**）
- 新增测试：`packages/coding-agent/test/suite/mwgal-t10-state-surface.test.ts`

## 写入禁止面

- `packages/multi-workers/**`（Python 侧属 T-11/T-12/T-14/T-16）
- `packages/coding-agent/src/extensions/agent-team-loop/shared/**`（属 T-17）
- 其他 key 目录、其他项目仓库（`E:\CLI_workspace\*`、`H:\git\E2Feature`、`H:\git\JCodingAss`）只读
- 不得改动 `GateView` 的既有字段集与 `autopilot-console.test.ts:384-389` 的断言

## 验收命令

从 `packages/coding-agent` 目录：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/autopilot-console.test.ts test/suite/mwgal-t10-state-surface.test.ts`

## 改动历史

（本卡为首次改动，填写：改了哪些文件、每处为什么、以及被否决的替代方案。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 改动清单`（文件 + 行范围 + 为什么）、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
