# 三路 DP 常规调用策略

## 系统行为变化

| 路径 | 本地判据与实际结果 | 自验 |
| --- | --- | --- |
| `dp-route` | 按当前入口、可读取的待办 gate、key 与阶段路由。常规路径零模型调用，错 key、读失败或关闭 gate 不获授权。显式 `dp-route` 查询仍调用原入口，复用结果时也重新核实际 gate。 | gate 路由 3 项通过。 |
| `dp-w-type` | 持认领的 PM 对合法卡片直接采用明确类型。实际派发写 1 个队列条目及 `task.md` 的钉住卡片摘要与 `type-selection`，分类和其反馈写入均为 0。显式比较仍走原准备与调用路径，调用失败仍由原规则判定能否由 PM 接回。 | 类型选择 11 项通过。 |
| `dp-sign-key` | `mw decide sign --for-done` 继续以现有独审、合同、产物和审批条件签收。正常签收和复用走正式 writer，模型调用为 0。缺独审、证据改变以及审批待决或拒绝时未签。 | 默认 Done 和显式本地证据各 6 项通过。 |

AC-001—004 按最终合同复验，见 [命令输出](evidence/codex-pm/self/1795335908169989300-xwerk4wj/command.log)。`npm run check` 在含本次改动及本地模型清单的隔离源码副本通过，避开共享目录的写式格式化。`triage-dispatch.test.ts` 在相同源码副本换回修改前派发入口后仍有原 15 个失败，包括旧 fixture 缺工作区配置或认领。定向测试使用离线替身。

## 遗留

八 DP 的决策本、完整模型请求、原始响应、原主体接回及回执的同次对账由 [mw-dp-material-pipeline](../mw-dp-material-pipeline/decision-chain-reconciliation.md) 验收。无真实模型调用、项目安装或线上回执。源基线为 `5216ae701` 加本工作区待提交差异。
