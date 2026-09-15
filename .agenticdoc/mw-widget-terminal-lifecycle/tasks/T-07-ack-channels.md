# Task T-07: ack 通道（命令 + 工具 + 徽标 + 提示链路）

## 基本信息
- Stage: 3
- 代码状态: 代码完成（PM 直执）
- 验证状态: 验证通过（vitest 106/106 含 6 个新用例 + [VERIFY] VC-004/005/006/010/011 埋点；三文件 119/119；biome 零告警）
- 负责 Agent: 待定
- ac_refs: [AC-004, AC-005, AC-006, AC-010, AC-011]
- vc_refs: [VC-004, VC-005, VC-006, VC-010, VC-011]
- pattern_refs: []

## 描述
`pm/ui-bridge.ts` + `pm/pm-orchestrator.ts`：

1. **共享校验助手** `ackTasks(workerStore, ackStore, keys: string[] | "all"): { acked: string[]; rejected: Array<{ key: string; reason: string }> }`：
   - "all" 展开 = workerStore.readAll() 中全部终态且未 ack 的 taskKey
   - 单 key：行不存在 → rejected(no-row)；running/pending → rejected(not-terminal)；终态 → ackStore.ack
2. **`/mw ack <task-key> | all`**：registerMwCommands 增 ack 子命令（签名注入 workerStore/ackStore，pmActivate 调用点同步）；结果 ui.notify：acked 清单 + rejected 原因
3. **`ack_worker_result` 工具**：registerWorkerTools 处注册（签名注入 ackStore）；参数 `task_key: string`（"all" 特殊值）；promptGuidelines 指示吸收结果后调用；返回文本含 acked/rejected 明细
4. **list_tasks 徽标**：行尾 ` | acked`（读 ackStore；registerWorkerTools 签名注入）
5. **PM_CONTINUE_HINT**（pm-orchestrator.ts）追加：「吸收上述结果后调用 ack_worker_result(task_key)（或 /mw ack all）确认处理完成，widget 待处理区才会清空。」
6. dispatchNewTasks 不改（VC-006 验证其不被 ack 影响）

**测试**（agent-team-loop.test.ts 追加）：
- /mw ack 终态行 → `_workers.acked` 有记录 + 新 AckStore 实例读出（VC-004 通道半）；all 覆盖全部未 ack 终态；running 行 → 错误提示且文件无该 key
- ack_worker_result 工具效果与命令一致；pmActivate 注册表含该工具；PI_WORKER_TASK 模拟下 activate 不注册（VC-005）
- ack 前后 `_workers.parallel` status 快照逐行相等；task.md 保留时 dispatchNewTasks 不新增 pending（VC-006）
- PM_CONTINUE_HINT 含 `ack_worker_result`（VC-010，L0）
- list_tasks：acked 行带 `acked`、未 ack 无（VC-011）
- 输出对应 `[VERIFY] VC-004/005/006/010/011: ...` 埋点行

## 输入
- 依赖文件: `pm/ui-bridge.ts`、`pm/pm-orchestrator.ts`
- 依赖 Task: T-01（AckStore）
- AC 约束:
  > AC-004: 执行 `/mw ack <task-key>` 后，`.agenticdoc/_workers.acked` 中存在该 task_key 的 ack 记录（含 ISO 时间戳，workers lock 保护写入），重启 pi 后 widget 分区仍按 ack 状态渲染；`/mw ack all` 覆盖当前全部未 ack 终态行；对 running/pending 行 ack 返回错误提示且不写记录
  > AC-005: PM 模式注册 agent 可调用工具 `ack_worker_result`（参数：task_key 或 all），效果与 /mw ack 等效；worker 模式（PI_WORKER_TASK 存在）下不注册该工具
  > AC-006: ack 操作前后 `_workers.parallel` 各行 status 列完全不变；ack 后模拟 agent_settled 触发 dispatchNewTasks，该 task_key 不被重新派发（dispatched 集合仍包含它）
  > AC-010: PM_CONTINUE_HINT 文本包含「吸收结果后调用 ack_worker_result」的显式指示
  > AC-011: list_tasks 工具输出中，已 ack 的终态行带 ack 标记（如 `acked`），未 ack 终态行无标记
- 设计约束:
  > D-002: 双通道收敛 ackTasks；PM-only 注册由 index.ts PI_WORKER_TASK 分支构造保证

## 预期产出
- `pm/ui-bridge.ts`（ackTasks + /mw ack + 工具 + list_tasks 徽标）
- `pm/pm-orchestrator.ts`（registerMwCommands/registerWorkerTools 调用点签名 + PM_CONTINUE_HINT）
- `agent-team-loop.test.ts`（追加用例 + 埋点）
- 验证方式: vitest 全绿零回归 + 埋点
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10T08:02Z | ackTasks 共享校验（all 展开/终态校验/拒绝原因）；/mw ack 子命令（registerMwCommands 加 workerStore+ackStore）；ack_worker_result 工具（promptGuidelines+拒绝明细）；list_tasks `acked` 徽标；PM_CONTINUE_HINT 追加 ack 指示；pmActivate 调用点同步 | vitest 106/106（新增 6 用例：持久化/拒绝/all、命令、PM-only（workerModeActivate 零工具注册）、工具等效、防重派发、hint+徽标）+ 五埋点；biome 零告警 |
### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
