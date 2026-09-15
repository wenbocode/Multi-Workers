# Research: 孤儿 running 行故障模式与 reconcile 证据基础（spec）

> 日期：2026-09-10
> 来源：用户指令「2 也纳入本 key」+ 源码取证。本 note 支撑 spec AC-012/013 与 design 的 reconcile 决策。

## 决策问题

- §1 范围：孤儿 running 行（serve 重启/被杀后无人更新的行）是否可被安全 reconcile，判据是什么
- §3 AC-008 前提核查：needs-clarification 状态的产出者与 output.md 前提是否成立

## 调研方法与出处

- 读 `packages/multi-workers/mw.py` cmd_serve 生命周期（242-247 行 finally 块）
- 读 `packages/multi-workers/launcher.py`（_poll_once reap 281 行、_spawn 395 行、_build_env 100/128 行、_exit_to_status）
- 读 `packages/coding-agent/src/modes/print-mode.ts`（35/147/158 行退出码）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（exit 钩子、timeoutExit、finishSuccess）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`（appendEnd [END] 行格式）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/shared/heartbeat.ts`（HEARTBEAT_INTERVAL_MS/HEARTBEAT_STALE_MS）
- 读 `packages/multi-workers/mw_common.py`（update_status docstring 410 行、worker_liveness 646 行）
- 现场样本：`.agenticdoc/goal-autopilot/workers/t03-roadmap/trace.log`（心跳 30s 连续 + [END] exit=0 elapsed=1766s）

## 发现

1. **serve 停止只终止 launcher 与 proxy，不终止 worker**：mw.py:242-247 finally 块仅对 `launcher_proc`/`proxy_proc` 调 terminate/kill。worker 是 launcher 的 Popen 子进程（launcher.py:395，仅 CREATE_NO_WINDOW，无 Windows Job Object），launcher 死后 worker 存活继续运行并写 trace.log/output.md，但无人 reap → 行永久停留 running。
2. **只有 spawn 方能更新行状态**：launcher.py:281 reap 循环只遍历本进程 `running_procs`；mw_common.py:410 `update_status` docstring 明确「launcher-side writer」。新 launcher 实例的 `running_procs` 为空，不会触碰旧 running 行。
3. **pi worker 的终态证据是机器可读的**：trace.log `[END] ts exit=<c> elapsed=<s>s tools=<n> phases=<d>/<t>`（output-writer.ts appendEnd）；且 worker-mode 进程 exit 钩子保证任何退出路径都写 output.md（硬杀除外）。[END] exit 码与 _exit_to_status 映射一致（0→done、2→needs-clarification、其他→failed）。
4. **claude/codex worker 无任务目录证据**：PI_WORKER_TASK 仅在 pi 分支注入（launcher.py:100,128），worker-mode 扩展不加载 → 无 trace.log/output.md，终态证据只有进程退出（reaper 捕获），launcher 死后永久缺失。此类孤儿行只能靠静默判据。
5. **pi print 模式退出码只有 0/1**：print-mode.ts:35,147,158。worker-mode 亦无 process.exit(2) 路径 → 当前 pi 任务实际不产出 needs-clarification；该状态只能来自 claude/codex CLI 的非常规退出码，而它们不写 output.md。**AC-008 的 `## Questions` 前提在现状下不可达，必须有回退路径**（worker.log 尾行/无输出提示）。
6. **活动信号判据**：pi worker 心跳 30s 间隔（heartbeat.ts HEARTBEAT_INTERVAL_MS）、90s 判 STALE（HEARTBEAT_STALE_MS，与 mw_common.py:646 doctor worker_liveness 的 90s 一致，仅提示不写队列）。pi worker 墙钟看门狗默认 60m（mw-worker-timeout-convergence）。claude/codex 无看门狗；观测到的 claude 运行 5-12m。
7. **90 分钟静默窗口的依据**：pi 活体 worker 最迟 60m 墙钟自杀并写 output.md（正证据路径接管）；心跳 30s 意味着活体行最多 90s 无文件活动。claude/codex 无心跳无看门狗，但观测运行 ≤12m，90m 静默远超任何合法静默期（claude -p 在结束前不写 stdout）。机器睡眠期间 launcher 自身冻结不轮询，无误判窗口；唤醒后活体 worker 心跳立即恢复。
8. **双 launcher 边界**：serve 被 kill -9 后 PID 文件指向死进程，新 serve 可启动，而孤儿 launcher 可能仍存活并正常 reap。新 launcher 若按静默判据处理旧 running 行会误杀仍被孤儿 launcher 管理的活体行。launcher 目前无实例注册机制（无 PID 表），需要最小协议（如 `.mw/launcher-beat` 心跳文件）让静默规则在检测到另一存活 launcher 时退让。正证据判据（[END]/output.md）是终态事实，双 launcher 下也安全（两端写出相同状态，幂等收敛）。
9. **正证据的微小竞态无害**：finishSuccess 写 output.md 后 pi 自然退出前有亚秒窗口，reconcile 可能先于 reaper 数百毫秒写出同值状态，收敛一致。
10. **2026-09-10 本仓库现场**：t03-t08 四行曾被误判僵尸，实为 UTC 时间戳误读本地时间（t03 心跳全程连续、29 分钟正常完成 exit=0）。确认「读队列时间戳必须统一 UTC 口径」为本 key 测试与实现的注意项。

## 结论 → 决策映射

- 发现 1+2 → 孤儿行是真实故障模式，reconcile 归属 launcher（队列单写者原则），仅处理 `running_procs` 之外的 running 行
- 发现 3 → 正证据判据：[END] exit 码映射终态（AC-012 主路径）
- 发现 4+6+7 → 静默判据：无终态证据 + 任务目录文件 mtime 与行 updated_at 均 ≥90m → failed（AC-013），默认值 env 可调
- 发现 8 → 静默规则需 launcher beat 防误杀；正证据规则无此约束
- 发现 5 → AC-008 增加回退（Questions 缺失时 worker.log 尾行/无输出提示）
- 发现 10 → 实现与测试统一 UTC 时间戳口径
