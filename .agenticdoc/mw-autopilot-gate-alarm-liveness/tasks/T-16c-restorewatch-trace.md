# T-16c — 人工认领 conductor 接管的 key 必须留痕（restoreWatch 静默认领）

type: coding
phase: execute
key: mw-autopilot-gate-alarm-liveness
覆盖 AC: AC-001, AC-002
依据: `.agenticdoc/mw-autopilot-gate-alarm-liveness/workers/mwgal-t16b-takeover-yield/report.md` `## 残留与未验证`（`restoreWatch` 静默认领条目）；
      T-16/T-16b 的合成 claim 让位链

## 上下文

- 项目目标锚点：`.agenticdoc/goal.md`（**无人值守时阻塞必须可见**；"谁在何时把 key 从 conductor 手里接走"如果无痕迹，运维就无法解释"为什么这个 key 突然被派发了/没被派发"）。
- 已核实锚点（自行复核）：`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:253 export function claimState(...)`、`:249 export type ClaimState = "free" | "held-live" | "held-stale" | "held-conductor"`（T-16b 新增）、调用点 `:97`/`:114`；`pm/pm-orchestrator.ts::restoreWatch`（窗口重启时的 watch 恢复路径）。
- **T-16b 自报的副作用（本卡要收口的那一条）**：新的 `held-conductor` 让 `takeOverKey` 谓词（保持 `=== "held-live"`）**天然放行**人工接管 ✓；但 `restoreWatch` 在**窗口重启**时会把被 conductor 接管的 key **静默认领回自己**（原先仅观察）——方向正确（人工优先），但**无痕迹** ⇒ 违反可见性要求。

## 要求

1. **留痕**：人工（窗口重启恢复路径）认领一个**处于 `held-conductor` 的 key** 时，必须留下**可见记录**：复用既有 timeline 事件名与既有事件形态（**不得新造事件名**），或在既有状态面（`_index.parallel` 的 claim 单元 + 面板）体现——报告须说明选择了哪一种及其为何满足"可见"。
2. **precedence 不变**：人工优先、conductor 不再抢回（T-16/T-16b 已实现，本卡不得回退）。
3. **不得扩大到非该场景**：对**真正被其他 live 窗口持有**的 key（`held-live`），`restoreWatch` 的行为**不得改变**（仍不得静默夺取）。
4. **幂等**：重启多次不得重复留痕/重复事件。
5. **回归测试**：① 窗口重启恢复 watch 且目标为 `held-conductor` ⇒ 认领成功 + **有可见痕迹**；② 目标为 `held-live`（他窗）⇒ 行为不变（不夺取、无越权痕迹）；③ 重启两次 ⇒ 痕迹不重复；④ T-16b 的 8 用例仍绿（不得回退）。

## 写入允许面

- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（仅当留痕需要）
- 新增：`packages/coding-agent/test/suite/mwgal-t16c-restorewatch-trace.test.ts`

## 写入禁止面

- `packages/coding-agent/src/extensions/agent-team-loop/shared/change-ledger.ts`、`worker/output-writer.ts`
- `packages/coding-agent/src/extensions/agent-team-loop/autopilot/**`（`monitor.ts`/`status-model.ts`）
- `packages/multi-workers/**`
- 其他 key 目录、其他项目仓库只读

## 验收命令

从 `packages/coding-agent`：
`node ../../node_modules/vitest/dist/cli.js --run test/suite/mwgal-t16c-restorewatch-trace.test.ts test/suite/mwgal-t16b-takeover-yield.test.ts`

## 改动历史

（填写：留痕落点与形态、为何不新造事件名、`held-live` 侧不变更的证据、幂等实现。）

## 交付格式

`report.md` 必须含以下**逐字 H2 段**：`## 结论`、`## 证据`、`## 改动清单`、`## 验证命令与实测输出`、`## 残留与未验证`、`## 上下文来源`。
