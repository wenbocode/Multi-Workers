# Task T-11: state-manager.ts + task-dispatcher.ts

## 基本信息
- Stage: 5
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-031, AC-032]
- vc_refs: [VC-040, VC-041]
- pattern_refs: []

## 描述
**state-manager.ts**：读写 `pm-state.md`。
- `Phase` 类型为字符串字面量联合（`'SPEC' | 'DESIGN' | 'PLAN' | 'TASKS' | 'EXECUTE' | 'DONE'`）
- `write(state: Partial<PmState>)` 传入非法 Phase 值时抛出 Error，pm-state.md 内容不变（先校验再写）
- 类型约束 + 运行时枚举校验双保险

**task-dispatcher.ts**：向 `_workers.parallel` 写入新 pending 任务。
- 调用 `WorkerStore.upsert()` 写入（持锁，T-02 实现）
- 生成 `DispatchedAt`（ISO 8601）、`UpdatedAt` 字段
- 格式符合 7 列约定（AC-032）

## 输入
- 依赖文件: `shared/worker-store.ts`（T-02）、`<key>/pm-state.md`（运行时文件）
- 依赖 Task: T-02
- AC 约束:
  > AC-031: StateManager.write() 传非法 Phase 值 → 抛 Error，pm-state.md 内容不变
  > AC-032: _workers.parallel 7 列格式，DispatchedAt + UpdatedAt 为 ISO 8601

## 预期产出
- `packages/coding-agent/src/extensions/agent-team-loop/pm/state-manager.ts`
  - `type Phase = 'SPEC' | 'DESIGN' | 'PLAN' | 'TASKS' | 'EXECUTE' | 'DONE'`
  - `class StateManager { async write(state: Partial<PmState>): Promise<void> }`
- `packages/coding-agent/src/extensions/agent-team-loop/pm/task-dispatcher.ts`
  - `export async function dispatchTask(entry: Omit<WorkerEntry, 'dispatchedAt' | 'updatedAt'>, store: WorkerStore): Promise<void>`
- 验证方式: VC-040（非法 Phase 被拒绝）、VC-041（7 列格式）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
