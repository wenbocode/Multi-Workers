# T-06: smoke_test.sh + 端到端验证

type: test-gen/debug
cli: pi
deps: T-01, T-02, T-03, T-04, T-05
status: pending

## Description
编写并执行冒烟测试脚本，验证 Agent Team Loop 完整端到端流程（--dry-run 模式）。

## Acceptance Criteria
- AC-1: `smoke_test.sh` 存在且可执行
- AC-2: 脚本创建 smoke-test key 并写 task.md
- AC-3: `python launcher.py --dry-run` 的输出包含 `pi` 和 task.md 路径
- AC-4: dispatch-table.md CLI 列 grep 通过（VC-01）
- AC-5: `build_codex_env()` 返回 `OPENAI_BASE_URL=http://localhost:7002`（VC-04）
- AC-6: 脚本 exit 0

## Tool Constraints
allowed: [read, write, bash, glob, grep]
denied: [network_fetch]

## Do NOT
- 不要实际 spawn pi/codex/claude 进程（dry-run 即可）
- 不要依赖外部网络

## Expected Output
`agent-team-loop/smoke_test.sh`，exit 0 运行，stdout 显示各 AC 验证结果。
