# Spec: mw-widget-terminal-lifecycle

> Key: mw-widget-terminal-lifecycle
> 创建时间: 2026-09-10
> 状态: locked

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active，存量三段式）

- 对齐：本 spec 服务于 goal「PM Agent 管理多个 Worker 并行开发」中的 PM 可观测性部分——底部 widget 是 PM 感知 worker 状态的主通道，终态行的生命周期与摘要质量直接决定 PM 吸收结果、决策重试/直执的效率。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不修改 pi 核心，全部通过 Extension API 实现
  - GC-2: 文件驱动协调（_workers.parallel / _index.parallel），并发写用文件锁
  - GC-3: 不引入中心化调度器，Worker 之间不直接通信
  - GC-4: 队列行格式（7/8 列）为 TS/Python 双侧共享协议，不得破坏（调研：evidence/research/spec-widget-terminal-forensics-2026-09-10.md 发现 6）
- 冲突：无
- 预期收益：
  - 超时/失败行从「永久占据 widget」变为「待处理清单」：PM 显式 ack 前常驻、ack 后折叠，widget 恢复有效信息密度（判定：终态行折叠区 ≤ 5 行 + more 行）
  - PM 一眼可判终态性质：failed 行显示机器原因（超时 kind + 证据），done 行显示单行结论（判定：终态行 detail 不再出现 markdown 标题前缀/文件路径列表/纯前导句）
  - serve 重启/被杀后，在飞 worker 的队列行不再永久停留 running：有终态证据时 ≤1 个 poll 周期收敛，无证据时 ≤90 分钟静默窗口收敛为 failed，PM 收到 readback 走既有处置分支

## §1 功能概述

### 1.1 目标

PM 窗口底部 watch widget（renderWatchLines）当前把该 key 的全部队列行排序展示、上限 6 行：终态行（done/failed/needs-clarification）没有任何「已被 PM 吸收」的生命周期概念，超时/失败行永久占据底部（OverCode 现场：4 个超时 + 2 个 done 占满）；终态行摘要取 output.md `## Summary` 冻结首行，常为 markdown 标题、纯前导句或文件路径，缺少「状态与卡点」；mw serve 停止/被杀后，在飞 worker 的队列行无人更新，永久停留 running。

本 key 交付：

1. **终态行生命周期（ack）**：`/mw ack` 命令 + `ack_worker_result` agent 工具，把终态行标记为已处理；ack 持久化（sidecar），不改队列行。
2. **widget 分区显示**：在跑（running/pending）与待处理（未 ack 的 failed/needs-clarification）行常驻不折叠；处理完/已完成（done + 已 ack 终态）行按 updatedAt 新→旧最多显示 5 行，超出折叠 `... +N more`。不使用 TTL。
3. **终态摘要质量**：failed → output.md `## Exit Reason` 首行；needs-clarification → `## Questions` 首行（含回退）；done → worker 侧归一化的单行结论（TL;DR），旧文件容错回退。
4. **孤儿 running 行 reconcile**：launcher 对非本实例管理的 running 行，按任务目录终态证据（trace.log [END]）或静默窗口收敛行状态。

### 1.2 技术栈 / 语言

TypeScript（agent-team-loop 扩展：ui-bridge.ts / pm-orchestrator.ts / worker-mode.ts / output-writer.ts）+ Python（launcher.py：reconcile、starter prompt 引导）。

### 1.3 核心用户场景

1. PM 在窗口底部观察所 watch key 的 worker 进度：在跑任务必须始终可见（实时心跳/阶段/当前动作/收敛检查点）。
2. worker 超时/失败/需澄清：行保持显示（带机器原因/问题），直到 PM 显式 ack；PM 由此获得一个确定的「待处理清单」。
3. PM 吸收终态结果（readback 消息）后调用 ack_worker_result（或用户执行 /mw ack），行进入历史折叠区；历史（done + 已 ack）超过 5 行折叠为 more...。
4. PM 扫一眼终态行即可决策：failed 行看到超时类型与证据（idle/wall、checkpoint risk），done 行看到单行结论。
5. mw serve 停止/重启（含被杀）后，之前在飞的 worker 行由 launcher 依据任务目录证据收敛为真实终态，PM 收到 readback 决定重派/直执/吸收。

### 1.4 范围说明（不做什么）

- 不包含：widget 交互（more... 行不可展开点击，保持静态渲染）
- 不包含：`_workers.parallel` 行/列格式变更（GC-4）
- 不包含：TTL 自动隐藏（用户明确否决）
- 不包含：doctor 的 worker_liveness 与 reconcile 的合并统一（doctor 保持提示性，后续 key 处理）

## §2 业务约束

### 2.1 平台 / 环境

- pi 扩展（全局安装 bundle，mw build 重建）；Windows 为主力平台，路径处理需兼容
- sidecar ack 文件与 `_workers.parallel` 同目录（.agenticdoc/），并发写复用 `.mw/workers.lock`
- 时间戳口径统一 UTC（trace.log/queue 均为 UTC ISO；曾发生本地/UTC 误读，调研：evidence/research/spec-orphan-running-reconcile-2026-09-10.md 发现 10）

### 2.2 性能指标

- widget 渲染沿用 4s 轮询周期（POLL_INTERVAL_MS），ack 状态读取为小文件读，不引入新轮询
- ack 写入持锁 O(acked 行数)，与 WorkerStore.upsert 同量级
- reconcile 在 launcher 既有 5s poll 内执行，每孤儿行 ≤ 数次 stat + 小文件尾部读；不新增进程/线程

### 2.3 安全约束

- ack 只影响展示分区与 PM 工作流，不改变任务状态语义；对非终态行 ack 拒绝
- ack 记录不得含敏感信息（仅 taskKey + 时间戳）
- reconcile 绝不触碰当前 launcher 自己 spawn 的行；静默判据在检测到另一存活 launcher 时退让（防误杀）

### 2.4 集成依赖

- `dispatchNewTasks`（pm-orchestrator.ts）依赖 `_workers.parallel` 现存行判定「已派发」——ack 不得删行（调研：spec-widget-terminal-forensics 发现 5）
- 队列状态写入保持 launcher 单写者原则（mw_common.update_status「launcher-side writer」）；reconcile 复用该路径
- claude/codex worker 无任务目录终态证据（PI_WORKER_TASK 仅 pi 注入）——其孤儿行只有静默判据可用（调研：spec-orphan-running-reconcile 发现 4）
- list_tasks / PM_CONTINUE_HINT 消费 ack 状态

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-10T12:13:52+08:00，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在 renderWatchLines 输入中存在所 watch key 的 running/pending 行时，输出的任务行区包含全部 running/pending 行且无折叠标记（数量不设上限） |
| AC-002 | 在存在未 ack 的 failed/needs-clarification 行时，输出包含全部这些行且无折叠标记；这些行 ack 后不再出现在该区（由 AC-004 的 ack 状态驱动） |
| AC-003 | 在 done 行与已 ack 终态行总数 N > 5 时，按 updatedAt 新→旧输出前 5 行并追加一行 `... +N-5 more`；N ≤ 5 时全部输出且无 more 行 |
| AC-004 | 执行 `/mw ack <task-key>` 后，`.agenticdoc/_workers.acked` 中存在该 task_key 的 ack 记录（含 ISO 时间戳，workers lock 保护写入），重启 pi 后 widget 分区仍按 ack 状态渲染；`/mw ack all` 覆盖当前全部未 ack 终态行；对 running/pending 行 ack 返回错误提示且不写记录 |
| AC-005 | PM 模式注册 agent 可调用工具 `ack_worker_result`（参数：task_key 或 all），效果与 /mw ack 等效；worker 模式（PI_WORKER_TASK 存在）下不注册该工具 |
| AC-006 | ack 操作前后 `_workers.parallel` 各行 status 列完全不变；ack 后模拟 agent_settled 触发 dispatchNewTasks，该 task_key 不被重新派发（dispatched 集合仍包含它） |
| AC-007 | 在 worker 行状态为 failed 时，widget 行 detail 为该任务 output.md `## Exit Reason` 节首行（超行宽截断）；launcher spawn 失败行为 spawn failed 原因行（剥除 `[launcher]` 前缀）；detail 不以 `#`、`**`、`- ` 开头 |
| AC-008 | 在 worker 行状态为 needs-clarification 时，widget 行 detail 为 output.md `## Questions` 节首行（超行宽截断）；无 `## Questions`（含 claude/codex 任务无 output.md 的情形）时回退为 worker.log 最后一条非空行，仍无则显示 no-output 提示（调研：spec-orphan-running-reconcile 发现 5，pi 侧现状无 exit 2 产出者） |
| AC-009 | 在 worker 行状态为 done 时，widget 行 detail 为单行结论：新完成任务由 worker 侧在 output.md 写入 TL;DR（首行结论、无 markdown 标记、≤100 字符）；旧 output.md（无 TL;DR）回退取 `## Summary` 首行并剥离开头 markdown 标记（`#`/`**`/`- `） |
| AC-010 | PM_CONTINUE_HINT 文本包含「吸收结果后调用 ack_worker_result」的显式指示 |
| AC-011 | list_tasks 工具输出中，已 ack 的终态行带 ack 标记（如 `acked`），未 ack 终态行无标记 |
| AC-012 | 在 `_workers.parallel` 存在状态为 running 且不属于当前 launcher 进程管理（running_procs 之外）的行、其任务目录 trace.log 含 `[END]` 标记时，launcher 在 ≤1 个 poll 周期（默认 5s）内将该行更新为 `[END]` exit 码对应终态（0→done、2→needs-clarification、其他→failed）并在 worker.log 追加 reconcile 原因行；仅 output.md 存在而无 `[END]`（旧 bundle）时更新为 failed 且原因注明状态不可验证；当前 launcher 自己 spawn 的行不受 reconcile 影响 |
| AC-013 | 在上述孤儿行无终态证据（无 output.md 且无 `[END]`）、且任务目录全部文件 mtime 与该行 updated_at 均早于当前时间 ≥90 分钟（默认值，环境变量可调）时，launcher 将该行更新为 failed 并在 worker.log 追加 `[launcher] reconcile` 原因行；任一活动证据新鲜于该窗口（如心跳）时行保持 running；检测到另一存活 launcher 的新鲜心跳标记时跳过本规则（正证据规则不受此限制） |

## §4 风险与未决项

- 风险：多窗口并发 ack 写 sidecar——以 workers lock 串行化，幂等（重复 ack 覆盖时间戳）
- 风险：done 行 TL;DR 依赖 worker 最终回复的首行质量——用 starter prompt 引导（launcher `_starter_prompt` 要求最终回复第一行为单行结论）+ worker 侧归一化兜底；旧任务靠 AC-009 回退路径
- 风险：静默判据误杀极长静默的 claude/codex 任务（无心跳无看门狗）——90m 窗口远超观测运行时长（≤12m），且 failed 原因行明示 presumed，PM 可读 worker.log 复核（调研：spec-orphan-running-reconcile 发现 6/7）
- 已决 1（2026-09-10 用户默认）：done 行无需 ack，直接进折叠区；failed/needs-clarification 才需要显式 ack
- 已决 2（2026-09-10 用户指令）：孤儿 running 行 reconcile 纳入本 key（AC-012/013）
- 已决 3（2026-09-10 用户默认）：sidecar 文件名 `.agenticdoc/_workers.acked`

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- WorkerStore.upsert 的 lock + tmp + rename 原子写模式（worker-store.ts）——sidecar ack 写入直接复用同模式与同锁
- readTaskProgress 的 trace.log 结构化行解析（shared/heartbeat.ts）——[END]/TL;DR/Exit Reason 提取沿用同文件读取风格；Python 侧 reconcile 的 [END] 解析镜像 END_LINE_RE 正则
- deliverPmAlert / displaySummary 双通道（ui-bridge.ts）——ack 工具与命令的反馈通道
- `_project_log.md` 已录 mw-worker-timeout-convergence 的超时体系（Exit Reason 已含 kind+checkpoint），本 key 只做展示侧消费，不重造
- mw_common.update_status 的持锁单写者路径——reconcile 状态写直接复用

### 需规避坑点

- CJK 文本编辑的 unicode 码位笔误会让 edit oldText 静默失败（goal-autopilot Turn 记录 pattern ③）——改动中文提示文案前先核对码位
- 队列行格式是 TS/Python 双侧共享协议，7/8 列容忍解析，任何新列都会被静默丢弃（本 key 调研发现 6）
- worker-mode 的 output.md 是 PM readback 全文投递对象，新增 TL;DR 节不得破坏 readOutputSummary 的 `## Summary` 正则兼容（旧读回退路径）
- dispatchNewTasks 的 dispatched 集合只看现存行——任何「清理队列行」的设计都会触发重复派发（调研发现 5）
- 队列/trace 时间戳为 UTC，本地时区显示需换算（2026-09-10 曾因此误判 4 个健康 running 行为僵尸，调研发现 10）
