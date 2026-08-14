# Task T-13: pm-orchestrator.ts + ui-bridge.ts

## 基本信息
- Stage: 5
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-027, AC-028, AC-030]
- vc_refs: [VC-036, VC-037, VC-039]
- pattern_refs: []

## 描述
**pm-orchestrator.ts**：PM mode 主协调器，整合所有 pm/ 子模块。

`pmActivate(pi)` 入口逻辑：
1. 调用 `goal-reader.ts` 确保 goal.md 存在
2. 注册 `/pm-key` 命令（通过 ui-bridge.ts）
3. 启动 `_workers.parallel` 轮询循环（间隔 ≤ 5s），检测 status=done/failed
4. done → 读 output.md，调用 ui-bridge.ts 展示 Summary
5. 写 `_index.parallel`（AgenticTask 格式，7 列）—— 调用 IndexStore.upsert()

**ui-bridge.ts**：TUI 命令注册和结果展示。
- 注册 `/pm-key new/switch/list` 命令处理
- 提供 `displaySummary(pi, summary)` 在 TUI 展示文本

## 输入
- 依赖文件: `pm/state-manager.ts`（T-11）、`pm/task-dispatcher.ts`（T-11）、`pm/goal-reader.ts`（T-12）、`shared/index-store.ts`（T-02）、`shared/worker-store.ts`（T-02）
- 依赖 Task: T-02, T-11, T-12
- AC 约束:
  > AC-027: 写入 _index.parallel 后，python update_index.py list 无错读取（管道分隔，7 列 AgenticTask 格式）
  > AC-028: /pm-key new/switch/list 命令在 pi TUI 内执行对应操作并输出结果
  > AC-030: 轮询检测到 status=done 时，读 output.md 并在 TUI 展示 Summary 节内容（非空）

## 预期产出
- `packages/coding-agent/src/extensions/agent-team-loop/pm/pm-orchestrator.ts`
  - `export async function pmActivate(pi: PiApi): Promise<void>`
  - `startWorkerPollLoop(pi, workerStore, agenticdocRoot, pollIntervalMs): void`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`
  - `export function registerPmKeyCommands(pi: PiApi, indexStore: IndexStore): void`
  - `export function displaySummary(pi: PiApi, summary: string): void`
- 验证方式: VC-036（update_index.py list）、VC-037（/pm-key list E2E）、VC-039（done → TUI 展示 Summary）
- 验证等级: Level 1（VC-036）/ Level 2 E2E（VC-037/039）

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: Pi Extension TUI 命令注册 API 待确认
- 处置: 实现前查 Pi Extension API 命令注册示例
