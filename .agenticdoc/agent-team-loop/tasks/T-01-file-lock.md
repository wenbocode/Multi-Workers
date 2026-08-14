# Task T-01: file-lock.ts（跨平台文件锁）

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-029]
- vc_refs: [VC-038]
- pattern_refs: []

## 描述
实现 `shared/file-lock.ts`：基于独占文件创建（`O_CREAT | O_EXCL` 等价语义）的跨平台文件锁。
在 Windows 上使用 `fs.openSync(path, wx)` 尝试创建锁文件；文件已存在则重试（指数退避，最多 10 次，基础间隔 50ms）；
持有锁的调用方完成操作后调用 `release()` 删除锁文件。
供 `worker-store.ts` 和 Python 侧（`open(path, 'x')`）共同使用——两侧约定同一锁文件路径 `.mw/workers.lock`。

## 输入
- 依赖文件: `packages/coding-agent/src/extensions/agent-team-loop/shared/` 目录（新建）
- 依赖 Task: 无
- AC 约束:
  > AC-029: 在两个进程并发写入 `_workers.parallel`（分别操作**不同** task key）时：（1）文件无半写行；（2）两个 key 的行均存在于最终文件中（无更新丢失）。写操作须先获取 `.mw/workers.lock` 文件锁，再执行 read-modify-rename

## 预期产出
- `packages/coding-agent/src/extensions/agent-team-loop/shared/file-lock.ts`
  - 导出 `acquireLock(lockPath: string, opts?: {retries?: number, baseDelayMs?: number}): Promise<() => void>`
  - 返回值为 `release` 函数，调用后删除锁文件
  - 锁文件已存在时重试，超出 retries 上限后抛出 Error
- 验证方式: VC-038（并发写入测试）
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
