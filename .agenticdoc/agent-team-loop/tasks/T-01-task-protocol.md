# T-01: task-protocol.md（L2 协议文档）

type: design/synthesis
cli: claude
deps: none
status: pending

## Description
编写 Agent Team Loop 的文件总线协议文档，规范 PM 与 worker 之间通过文件交换
任务和结果的三份格式：task.md、output.md、evidence/runs/。

## Acceptance Criteria
- AC-1: 文档存在于 `agent-team-loop/task-protocol.md`
- AC-2: 包含 task.md 格式规范（所有字段 + 示例）
- AC-3: 包含 output.md 格式规范（所有字段 + 示例）
- AC-4: 包含 evidence/runs/ 日志格式规范（[FLOW]/[VERIFY] 行格式）
- AC-5: 包含版本号（v1.0）和变更记录占位

## Tool Constraints
allowed: [write]
denied: [bash, network]

## Do NOT
- 不要实现任何代码，只写文档
- 不要修改 spec.md / design.md

## Expected Output
`agent-team-loop/task-protocol.md`，Markdown 格式，包含所有三份格式规范和示例。
