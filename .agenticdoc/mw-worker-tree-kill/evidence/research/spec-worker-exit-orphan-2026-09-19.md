# Research: worker 退出路径孤儿化子进程（spec）

## 决策问题

- §1 范围：修复落在哪一层（worker 扩展自自杀路径 vs launcher Job Object 兜底）
- §2 约束：是否触碰 pi 核心（goal Key Constraint「不修改 pi 核心」）
- §3 AC：可判定的杀树行为断言从何而来（真实事故链）

## 调研方法与出处

- 代码走读（本仓库，2026-09-19 会话）：
  - `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:651-670`（timeoutExit → `process.exit(1)`）、`:864-870`（agent_settled catch → `process.exit(1)`）、`:475-487`（process 'exit' 安全网，只补写 output.md，不清理子进程）
  - `packages/coding-agent/src/core/tools/bash.ts:99,108,112,120,142`（bash 工具 `trackDetachedChildPid(child.pid)` / 超时与 abort 时 `killProcessTree` / finally `untrack`）
  - `packages/coding-agent/src/utils/shell.ts:241-279`（tracked pid 集合 + `killTrackedDetachedChildren()` + `killProcessTree()`：Windows `taskkill /F /T /PID`，POSIX `kill(-pid)`）
  - `packages/coding-agent/src/modes/print-mode.ts:51-60`（`killTrackedDetachedChildren()` 仅挂在 SIGTERM/SIGHUP 信号 handler 上）
- 真实事故报告（用户转发，2026-09-19）：目标项目 skill-system-core-audit worker 的 idle watchdog 于 16:15 杀掉 worker（exit=1），其 bash 工具启动的 `python probe2.py` 孤儿化，50 分钟吃掉 WS 151 GB / 私有 252 GB；孤儿链 = 已死 worker(60816) → WindowsApps python.exe shim(43948) → pythoncore-3.14(62724)。

## 发现

1. pi 已有完整的子进程树追踪与终止设施：bash 工具把每个 spawn 的 shell pid 记入 `utils/shell.ts` 模块态 Set；`killProcessTree` 在 Windows 用 `taskkill /F /T /PID`（杀整棵树，含孙进程），POSIX 用 `kill(-pid)`（bash 工具在 POSIX 以 detached/组长方式 spawn，组杀有效）。
2. 但唯一的自动清理入口是 print 模式的 **SIGTERM/SIGHUP handler**。worker 的 watchdog（`timeoutExit`）直接 `process.exit(1)`，不经过任何信号 → tracked pid 集合被原样丢弃，挂起中的 bash 子进程树（pid 仍在 Set 里）无人杀。
3. Windows 父子进程寿命不联动 → 孤儿继续跑。观测到的 shim 父进程 = 已死 worker，与 git-bash `-c` 单命令 exec 优化一致（bash 原地 exec 成 shim，tracked pid 即 shim pid，`taskkill /T` 本可连真 python 一起带走）。
4. 其余 worker 死亡路径均无树杀：launcher.py 从不杀 worker 进程；mw serve 只 terminate conductor；agent_settled catch 路径同样裸 `process.exit(1)`。
5. 扩展层可零成本复用：`killTrackedDetachedChildren` 是 `utils/shell.ts` 的具名导出，agent-team-loop 与 bash 工具同属一个编译产物（built-in extension），import 后访问的是**同一模块实例**的 tracked Set —— 这是唯一能读到该 Set 的途径，不需要改 pi 任何核心行为。

## 结论 → 决策映射

- 修复定位在 **worker 扩展退出路径**（timeoutExit / settled-catch 显式调用 + 'exit' 安全网兜底），复用 `killTrackedDetachedChildren()`：精确覆盖本次事故链（tracked bash 子进程），不自杀、不动 pi 核心代码（只读复用导出，与既有 `../../../core/extensions/types.ts` import 同类）→ §1 范围、§2 约束。
- launcher Job Object（KILL_ON_JOB_CLOSE）能覆盖 worker 硬崩溃等扩展层兜不住的死法，但属独立交付物，记为后续 key，不在本次范围 → §1.4。
- AC 断言来源 = 事故链的机械反转：watchdog/异常退出前，每个 tracked pid 必须先经过树终止调用，且早于 `process.exit(1)`；正常完成路径行为不变 → §3。
