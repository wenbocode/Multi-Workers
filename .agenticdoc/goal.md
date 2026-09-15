# Project Goal

## Goal

在 pi coding agent 之上构建一个 Agent Team 协作框架，让一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目，解决单 Agent 长上下文溢出和无法并行的问题。

核心交付：
- mw 后台服务（Python）：LLM 代理 + 任务调度器，常驻运行
- agent-team-loop 扩展（TypeScript）：PM 模式（编排） + Worker 模式（执行）
- 文件驱动的去中心化协调：_workers.parallel、_index.parallel、goal.md
- 项目级目标对齐（goal.md），Worker 执行过程中追踪 goal 一致性

## Context

- 基于 pi（@earendil-works/pi-coding-agent）扩展系统，不 fork
- 编程语言：TypeScript（扩展）+ Python（后台服务）
- 复用 AgenticTask 的 _index.parallel 格式和 Phase 门禁语义
- Worker 通过 pi 的 built-in extension 机制加载，PM/Worker 模式由 PI_WORKER_TASK 环境变量切换
- LLM 代理基于 timi-proxy-cli，为不同 CLI 类型提供隔离的本地代理端口
- 凭证隔离：每个 Worker 只拿到它需要的 API key，其他 provider 凭证从 env 中删除

## Key Constraints

- 不引入中心化调度器：协调通过文件系统（_workers.parallel + 文件锁），Worker 之间不直接通信
- 不修改 pi 核心：所有功能通过 Extension API 实现
- Worker 进程级隔离：每个 Worker 是独立的 pi 进程，崩溃不影响其他 Worker
- 文件锁并发控制：_workers.parallel 和 _index.parallel 的并发写入使用 O_CREAT|O_EXCL 锁
- 工具白名单按任务类型：coding（read/write/edit/bash）、review（read/find/grep/ls）、research（read/find/grep/ls/bash）
- Worker 超时看门狗（2026-09-09 修订，mw-worker-timeout-convergence）：activity watchdog（无 token 增量/工具/turn 活动 10 分钟判真挂死，PI_WORKER_IDLE_MS 可调）+ 墙钟兜底（默认 60m，task.md `timeout:` 分钟头 > PI_WORKER_TIMEOUT_MS > 默认）+ 30 分钟收敛检查点（[CHECKPOINT] 机器判据 + worker 自评，mid/high risk 经 triggerTurn 升级 PM 主窗口判断分拆/收窄/直执）+ deadline steer（预算尾段引导 agent 自行收尾落盘）
- goal.md 作为项目级目标锚点，Worker 在每个 phase 完成时记录 goal mtime 到 trace.log