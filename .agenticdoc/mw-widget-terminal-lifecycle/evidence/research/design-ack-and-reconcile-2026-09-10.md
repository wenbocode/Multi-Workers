# Research: ack 存储与孤儿 reconcile 的设计决策取证（design）

> 日期：2026-09-10
> 支撑 design D-001/D-002/D-006/D-007/D-008。

## 决策问题

- ack 状态存哪、谁写谁读、多窗口语义
- reconcile 由谁执行（launcher vs TS poll loop）、判据与防误杀协议
- 静默窗口参数依据与 beat 协议形态

## 调研方法与出处

- 读 `packages/coding-agent/src/extensions/agent-team-loop/index.ts`（10-12 行：PI_WORKER_TASK 分支）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/shared/file-lock.ts`（acquireLock wx + 重试）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/shared/worker-store.ts`（upsert lock+tmp+rename 模式）
- 读 `packages/multi-workers/mw_common.py`（update_status 410 行 docstring；worker_liveness 646 行）
- 读 `packages/multi-workers/launcher.py`（running_procs 字典、_poll_once 281 行 reap）
- 读 `packages/multi-workers/mw.py`（_check_pid 存活检查、242-247 行 finally）
- spec 调研 note：`spec-orphan-running-reconcile-2026-09-10.md`（发现 1-8）

## 发现

1. **PM-only 工具注册是构造保证**：index.ts 按 PI_WORKER_TASK 二选一 activate；workerModeActivate 不注册任何工具/命令。`ack_worker_result` 注册在 registerWorkerTools（pmActivate 路径）即天然满足 AC-005，无需运行时判断。
2. **TS 侧无法判定孤儿归属**：running_procs 是 launcher 进程内存字典，TS 扩展无法访问。TS poll loop 若做 reconcile 只能对所有 running 行猜测（会把活体行误判）。归属知识只在 launcher → reconcile 执行者必须是 launcher。
3. **队列单写者原则已确立**：mw_common.update_status docstring「launcher-side writer」；TS 侧仅 dispatch 时 upsert。reconcile 走 _update_status 保持该原则。
4. **正证据判据双 launcher 安全**：[END]/output.md 是终态事实；两个 launcher 依同证据写同值状态，幂等收敛（reaper 与 reconcile 竞态窗口亚秒，结果一致）。
5. **静默判据需要 launcher 实例标记**：serve 被 kill -9 后 PID 文件指向死进程（mw.py _check_pid 按存活判定），新 serve 可启动而孤儿 launcher 仍存活 reap。无实例标记时新 launcher 的静默规则会误杀孤儿 launcher 正管理的活体行。最小协议：launcher 每 poll 刷新 `.mw/launcher-beat`（pid + ts）；静默规则前置检查「beat 新鲜且 pid≠self 且存活」→ 退让。心跳新鲜阈值取 30s（6 个 poll 周期，容忍单次 poll 抖动）。
6. **ack 语义是项目级而非窗口级**：队列全局共享、单 PM 纪律（_index.parallel 单 active）；PM 窗口 A 吸收结果后，窗口 B 的 widget 也应折叠（结果已处理）。sidecar 全局生效与该语义一致，无需 per-window 状态。
7. **AckStore 可完整复用既有模式**：acquireLock（file-lock.ts）+ tmp+rename（worker-store.ts upsert）+ 同一 `.mw/workers.lock`——与队列写互斥，无新锁协议。
8. **静默窗口 90m 的量化依据**（承接 spec note 发现 6/7）：pi 活体行墙钟 60m 内必自杀并落正证据；心跳 30s 意味活体行 ≤90s 必有文件活动；claude/codex 观测运行 ≤12m。90m = 60m 墙钟 + 50% 余量，且远超 claude 合法静默。env 可调（PI_WORKER_ORPHAN_DEAD_MIN）供极端模型延迟场景。
9. **reconcile 原因行格式沿用既有惯例**：worker.log 已有 `[launcher] spawn failed (<ts>): <msg>` 格式（launcher.py _record_spawn_failure）；reconcile 原因行用 `[launcher] reconcile (<ts>): <reason>` 同族，PM 侧 readSpawnFailure 式读取可扩展消费。

## 结论 → 决策映射

- 发现 1 → D-002：ack 工具注册在 PM 路径，AC-005 构造保证
- 发现 2+3 → D-006：reconcile 执行者 = launcher，走 _update_status
- 发现 4 → D-007：正证据每 poll 无条件执行
- 发现 5 → D-008：beat 协议 `.mw/launcher-beat`，静默规则前置退让检查
- 发现 6 → D-001：sidecar 全局 ack，多窗口共享
- 发现 7 → D-001：AckStore 复用 workers lock + tmp+rename
- 发现 8 → D-007：ORPHAN_DEAD_AFTER 默认 90m，PI_WORKER_ORPHAN_DEAD_MIN 可调
- 发现 9 → D-007：原因行 `[launcher] reconcile (<ts>): ...`
