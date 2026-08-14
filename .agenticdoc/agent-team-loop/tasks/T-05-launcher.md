# T-05: launcher.py（调度核心）

type: code-gen/impl
cli: codex
deps: T-02, T-03, T-04
status: pending

## Description
实现 `launcher.py`：轮询 `_index.parallel`，发现 pending task 后
按 CLI 字段 spawn 对应 worker 进程，收割完成后更新 index。

## Acceptance Criteria
- AC-1: `python launcher.py --dry-run` 打印预期 spawn 命令，不实际执行，exit 0
- AC-2: `build_pi_env` / `build_codex_env` / `build_claude_env` 注入正确 proxy URL
- AC-3: `poll_pending_tasks()` 读 `_index.parallel`，只返回 status=pending 且 cli 非空的行
- AC-4: 同一 key 不会被重复 spawn（running_procs 去重）
- AC-5: `--max-workers N` 限制同时活跃进程数（默认 3）
- AC-6: worker exit 0 时调用 `update_index.py` 更新 status=done
- AC-7: worker exit 1 时 status=failed；exit 2 时 status=needs-clarification
- AC-8: 单元测试文件 `test_launcher.py`（mock subprocess.Popen）覆盖 AC-3/AC-4/AC-5

## Tool Constraints
allowed: [read, write, bash, glob, grep]
denied: [network_fetch]

## Do NOT
- 不要硬编码 PLATFORM_DIR，启动时通过 detect_root.py --json 动态获取
- 不要使用 shell=True（命令注入风险）
- 变量展开时务必用列表形式传参，不要字符串拼接

## Expected Output
`agent-team-loop/launcher.py` + `agent-team-loop/test_launcher.py`。
