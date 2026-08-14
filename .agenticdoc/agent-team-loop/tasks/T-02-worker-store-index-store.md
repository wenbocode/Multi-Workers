# Task T-02: worker-store.ts + index-store.ts

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-027, AC-029, AC-032]
- vc_refs: [VC-036, VC-038, VC-041]
- pattern_refs: []

## 描述
实现两个共享存储模块：

**worker-store.ts**：管理 `_workers.parallel`（7 列管道分隔格式）。
写操作通过 T-01 的 `file-lock.ts` 持锁后执行 read-modify-rename 原子写。
导出 `WorkerEntry` interface、`WorkerStatus` 类型、`WorkerStore` class。

**index-store.ts**：管理 `_index.parallel`（AgenticTask 格式，7 列：Key|Status|Phase|ClaimId|Deps|Desc|Updated）。
写操作同样使用 read-modify-rename，但使用独立锁文件（`.mw/index.lock`）。
导出 `IndexEntry` interface、`IndexStore` class。

两文件格式独立，不互相写入。

## 输入
- 依赖文件: `shared/file-lock.ts`（T-01）
- 依赖 Task: T-01
- AC 约束:
  > AC-032: `_workers.parallel` 格式为 7 列管道分隔：`Task-Key|Status|Cli|Provider|TaskPath|DispatchedAt|UpdatedAt`；Status 值域：`pending/running/done/failed/needs-clarification`；与 AgenticTask `_index.parallel` 为独立文件，不共用
  > AC-027: 在 pm-orchestrator.ts 写入 `_index.parallel` 后，文件格式与 AgenticTask 规范兼容（管道分隔，列顺序：Key|Status|Phase|ClaimId|Deps|Desc|Updated），`python update_index.py list` 能无错读取
  > AC-029: 写操作须先获取 `.mw/workers.lock` 文件锁，再执行 read-modify-rename

## 预期产出
- `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts`
  - `WorkerStatus`: `'pending' | 'running' | 'done' | 'failed' | 'needs-clarification'`
  - `WorkerEntry`: 7 字段 interface
  - `WorkerStore`: `readAll()`, `upsert()`, `findByKey()`
- `packages/coding-agent/src/extensions/agent-team-loop/shared/index-store.ts`
  - `IndexStatus`: `'active' | 'idle' | 'done'`
  - `IndexEntry`: 7 字段 interface
  - `IndexStore`: `readAll()`, `upsert()`, `findByKey()`
- 验证方式: VC-036（update_index.py list 验证 index-store 格式）、VC-038（并发写入 worker-store）、VC-041（7 列格式）
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
