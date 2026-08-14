# Task T-06: mw.py serve/start/stop/status

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-034, AC-035]
- vc_refs: [VC-045, VC-046]
- pattern_refs: []

## 描述
在 `mw.py` 中实现后台服务管理子命令：

**serve**（前台阻塞）：
- 检查 `<project-dir>/.mw/mw.pid`；若存在且进程存活 → 输出错误（含 PID）并 exit 1
- 写当前 PID 到 `.mw/mw.pid`
- 用 `subprocess.Popen` 启动 `proxy_multi.py` 和 `launcher.py`（各自独立子进程）
- 监听 SIGTERM/SIGINT，收到信号后终止子进程并删除 PID 文件
- Pi 进程退出不影响本进程（mw serve 是独立进程组，不在 pi 的进程树中）

**start**：detach 模式（后台运行 serve）

**stop**：读 PID 文件，发 SIGTERM，等待退出，清理 PID

**status**：读 PID 文件，检查进程存活，打印状态

## 输入
- 依赖文件: `proxy_multi.py`（T-05）、`launcher.py`（T-03/T-04）
- 依赖 Task: T-03, T-04, T-05
- AC 约束:
  > AC-034: 启动后写 PID 到 `.mw/mw.pid`；第二实例检测到 PID 且进程存活 → 输出错误 + exit 1；进程退出时清理 PID
  > AC-035: pi 退出后 mw serve 及其管理的 worker 继续运行直到任务完成

## 预期产出
- `mw.py`（含 `serve`/`start`/`stop`/`status` 子命令）
  - `serve(project_dir, pi_port, codex_port, claude_port, max_workers, poll_interval)`
  - `_check_pid(pid_path)` → 检查 PID 文件 + 进程存活
  - `_write_pid(pid_path)` / `_remove_pid(pid_path)`
- 验证方式: VC-045（PID 文件 + 防重复，L1）、VC-046（pi 退出不中止 serve，L1）
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
