# Task T-03: launcher.py 核心（轮询 + spawn）

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-001, AC-002, AC-003, AC-004, AC-005, AC-006, AC-008, AC-015, AC-023]
- vc_refs: [VC-001, VC-002, VC-003, VC-004, VC-005, VC-006, VC-007, VC-008, VC-009, VC-010, VC-011, VC-013, VC-023, VC-032]
- pattern_refs: []

## 描述
实现 `packages/multi-workers/launcher.py` 核心循环：
- 轮询 `_workers.parallel`，间隔 `DEFAULT_POLL_INTERVAL = 5`（秒）
- 过滤 `status=pending` 且不在 `running_procs` 的行
- 根据 `Cli` 列决定启动哪个 worker：
  - `pi`：注入 `ANTHROPIC_BASE_URL` + `PI_WORKER_TASK`（绝对路径）
  - `codex`：注入 `OPENAI_BASE_URL` + `OPENAI_API_KEY`
  - `claude`：注入 `ANTHROPIC_BASE_URL` + `ANTHROPIC_AUTH_TOKEN`
- 用 `subprocess.Popen` 启动（禁止 `shell=True`），记录 pid 到 `running_procs[task_key]`
- 监听子进程退出：exit 0 → `done`；exit 2 → `needs-clarification`；其他 → `failed`
- 回写 status 须先获取 `.mw/workers.lock`（`open(path, 'x')` 独占创建），再 read-modify-rename
- Windows 路径用 `pathlib.Path` 处理，支持含空格路径

## 输入
- 依赖文件: `_workers.parallel`（T-02 定义格式）；`providers.json`（T-04 创建，此 task 可先用硬编码端口占位）
- 依赖 Task: T-02（格式约定），T-04（providers.json，软依赖）
- AC 约束:
  > AC-001: launcher.py 轮询间隔 ≤ 5 秒（DEFAULT_POLL_INTERVAL ≤ 5）
  > AC-002: Cli=pi 时注入 ANTHROPIC_BASE_URL=http://localhost:{pi-port} + PI_WORKER_TASK=<绝对路径>
  > AC-005: exit 0 → status=done，3 秒内完成
  > AC-006: exit 1 → failed；exit 2 → needs-clarification；其他 → failed（兜底）
  > AC-008: 同一 task key 已在 running_procs 中时，不再 spawn 第 2 个进程
  > AC-015: Windows 含空格路径正确处理
  > AC-023: task.md 路径以 `<project-dir>/.agenticdoc/` 为前缀

## 预期产出
- `packages/multi-workers/launcher.py`
  - `DEFAULT_POLL_INTERVAL = 5`
  - `_build_env(entry, providers) -> dict`
  - `_exit_to_status(code) -> str`
  - `_update_status(entry, lock_path, workers_path)` —含文件锁
  - `run(project_dir, poll_interval, max_workers, dry_run)` 主循环
- 验证方式: VC-001（静态检查 DEFAULT_POLL_INTERVAL）、VC-002~011（单元测试 env/status 函数）、VC-008（exit 延迟 ≤ 3s）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-08-11 | 实现 launcher.py 核心循环 | DEFAULT_POLL_INTERVAL=5, _build_env, _exit_to_status, _update_status, run(), _spawn() |
| 2 | 2026-08-11 | 修复 VC-033：ANTHROPIC_BASE_URL 污染 deepseek env | 清除所有已知 base_url_env vars 后再设置目标 var |
| 3 | 2026-08-11 | 修复 VC-006/007：cli=claude 映射到 claude-cli provider | 添加 _cli_default_provider = {"claude": "claude-cli"} |
| 4 | 2026-08-11 | 全量单元测试通过 | VC-002/003 VC-004/005 VC-006/007 VC-033 VC-023 全 PASS |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|
| E-001 | 逻辑错误 | launcher.py:_build_env | ANTHROPIC_BASE_URL 被 deepseek 继承 | 已修复 |
| E-002 | 逻辑错误 | launcher.py:_build_env | cli=claude 用了 claude provider (7001) 而非 claude-cli (7003) | 已修复 |

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
