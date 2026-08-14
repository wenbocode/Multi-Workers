# T-04: worker-mode.ts（L4 Pi Extension）

type: code-gen/impl
cli: pi
deps: T-01
status: pending

## Description
实现一个 Pi Extension，让 `pi` CLI 在检测到 `PI_WORKER_TASK` 环境变量时
进入 worker 模式：读取 task.md，执行任务，写 output.md 和 evidence 日志后退出。

## Acceptance Criteria
- AC-1: 当 `PI_WORKER_TASK` 未设置时，extension 不做任何事（正常交互模式）
- AC-2: 当 `PI_WORKER_TASK` 设置时，在 agent 启动前读取 task.md 并配置 tools
- AC-3: `resolveTools(taskType)` 按 task.type 返回正确的 tool allowlist
- AC-4: `agent_end` 事件回调里写 output.md（格式符合 task-protocol.md）
- AC-5: `agent_end` 事件回调里写 `evidence/runs/<key>/trace.log`（含 [FLOW]/[VERIFY] 行）
- AC-6: exit 0（成功）/ exit 1（失败）/ exit 2（需要澄清）
- AC-7: `npx tsc --noEmit` 在 packages/coding-agent 下通过（无类型错误）

## Tool Constraints
allowed: [read, write, bash, glob, grep]
denied: [network_fetch]

## Do NOT
- 不要在 startup hook 里调用 process.exit()，必须在 agent_end 里
- 不要修改 packages/coding-agent 的核心代码，只写 extension 文件
- 不要 await import()，所有 import 放顶层

## Expected Output
`agent-team-loop/worker-mode.ts`，完整 TypeScript Pi Extension。
包含：default export 函数、resolveTools、writeOutput、writeEvidenceLog 四个函数。
