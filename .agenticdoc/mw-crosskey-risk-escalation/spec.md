# Spec: mw-crosskey-risk-escalation

> Key: mw-crosskey-risk-escalation
> 创建时间: 2026-09-23
> 状态: draft
> 来源：key `mw-worker-visibility-gate` 质检门禁 Q-X-006 / 残留 R-5（用户 2026-09-23 决定「开」）

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（status: active）

- 对齐：本 spec 服务于 goal「在 pi coding agent 之上构建一个 Agent Team 协作框架，让一个 PM Agent 管理多个 Worker Agent 并行开发同一个项目」中的两块：
  1. **Worker 执行过程中追踪 goal 一致性**——risk 检查点是"worker 是否在偏离"的机器判据，它现在只对 watched key 生效；本窗口亲自派出去的异地 worker 偏离时无人被唤醒，追踪链断在"谁派发的"这一步；
  2. **文件驱动的去中心化协调**——判定必须只读 `_workers.parallel`（含 `taskPath` 归属 key）、`trace.log`（`[CHECKPOINT]`）与窗口内存在派发登记，不引入中心调度器或跨窗口投递通道。
- 继承约束（GC 编号，供 design/plan 引用）：
  - GC-1: 不引入中心化调度器——升级判定只读文件 + 进程内 `dispatchedTaskKeys`，无守护进程、无跨进程队列；
  - GC-2: 不修改 pi 核心——改动落在 `packages/coding-agent/src/extensions/agent-team-loop/**`；
  - GC-3: 零 Python 行为改动（框架脚本属另一 git 仓库，本 key 不改）；
  - GC-4: goal.md 低 churn——本 key 不修改 goal.md；
  - GC-5（本 key 新增）：不引入跨窗口广播——投递面严格限定"本窗口派发的 task"（`PmWatchState.dispatchedTaskKeys`，进程内、不持久化），其他窗口派发的 worker 保持静默。
- 冲突：无（GC-5 是对既有性质的收紧，不是放宽）。
- 预期收益：本 key 达成后对项目目标的具体贡献（可观察、可验证；done 时在 achieved.md 对照判定）
  - **收益 1（可观察）**：PM 把 worker 派到 `_scratch`/他键（门禁兜底、临时隔离）后，该 worker 在 30 分钟检查点报 `risk=high` 时 PM **会被唤醒一次**，alert 文本带 owner key，PM 得以在同一次会话里决定收窄/分拆/直执。判定方式：fake timers 驱动 `startWorkerPollLoop`，断言恰好 1 条含 owner key 的 alert（AC-001）。
  - **收益 2（可观察）**：别窗口的 worker 仍然**不会**唤醒本窗口（保持"每个窗口只管自己那摊"），门禁不引入噪音。判定方式：同一夹具，task 不在 `dispatchedTaskKeys` 即 0 条 alert（AC-002）。

## §1 功能概述

### 1.1 目标

修一处 monitor 过滤面缺口（不改判定判据本身）：

`pm-orchestrator.ts` 的分化升级循环（`startWorkerPollLoop`，当前约 `:564-578`）在判定是否投递时用：

```ts
if (!watch.key || ownerKeyOf(entry, agenticdocRoot) !== watch.key) continue;
```

即"只有 owner key == 被 watch 的 key 的 running worker 才升级"。但同一个 key 的派发面还有第二条所有者语义：`PmWatchState.dispatchedTaskKeys`（`mw-task-scope-isolation` 引入，`list_tasks`/`ack_worker_result` 已按它扩可见面）。结果是本窗口派到 `_scratch` 或他键的 worker：

- `list_tasks` 看得见（owner 前缀行）；
- 底栏面板看得见（`mw-worker-visibility-gate` 的跨 key 聚合行，含 `risk=high:K`）；
- **但不会触发 PM 升级投递**——面板是"看着被动的信号"，PM 只有在主动看面板时才发现。

### 1.2 技术栈 / 语言

TypeScript（pi Extension API）。测试面：`packages/coding-agent/test/extensions/agent-team-loop.test.ts`（既有 monitor 用例所在文件，本 key 新增用例就近落在这里，复用 `fakePi` / `queueRunning` / `mkdtemp`）。

### 1.3 核心用户场景

1. 场景 A：PM 因为门禁兜底把调研 worker 派到 `_scratch`，该 worker 卡住并报 `risk=high` → 期望 PM 收到 1 条 alert（含 owner `_scratch`），能当场决定终止/重派/直执。
2. 场景 B：另一个窗口正在跑的 worker 报 `risk=high` → 本窗口**不该**被唤醒（那是别窗口的上下文与职责）。
3. 场景 C：回归 —— watched key 自身的高风险 worker 升级行为逐字不变（既有 AC-004 用例继续通过，alert 文本、`triggerTurn`、once-per-task 语义不变）。

### 1.4 范围说明（不做什么）

- 不包含：改动 risk 判据本身（`readTaskProgress` / `[CHECKPOINT]` 阈值 / 30 分钟锚点）。
- 不包含：低风险检查点的投递（保持"只进面板不投递"）。
- 不包含：跨窗口广播、全局（不限 owner）升级（见 §1.1 备选，已否决）。
- 不包含：面板聚合行（`mw-worker-visibility-gate` 已交付，本 key 不改 `renderWatchLines`）。
- 不包含：Python / 框架仓库 / `dist/**`（构建产物由收口时统一重建）。

## §2 业务约束

### 2.1 平台 / 环境

Windows 主开发环境；`vi.useFakeTimers()` 驱动轮询；Windows 环境基线 89 项失败只比增量。

### 2.2 性能指标

- 不新增全量读盘：复用循环内既有的 `workerStore.readAll()` 结果与一次 `readTaskProgress()`。
- 判定为 O(1) 集合查询（`Set.has`）。

### 2.3 安全 / 隔离约束

- `dispatchedTaskKeys` 是**进程内**状态（`PmWatchState` 注明"never persisted, never shared between windows"）——升级投递不得把它持久化或经文件共享。
- 去重语义不变：每 task 每窗口至多 1 条（`escalated` 集合）。
- 不写任何文件（升级路径只读 + `pi.sendMessage`）。

### 2.4 集成依赖

- `pm/pm-orchestrator.ts`（`startWorkerPollLoop`、`deliverPmAlert`、`ownerKeyOf`、`readTaskProgress`）；
- `pm/ui-bridge.ts`（`PmWatchState.dispatchedTaskKeys` 类型与派发登记点，本 key 只读）；
- 测试资产：`test/extensions/agent-team-loop.test.ts` 既有 "AC-004: diverging workers owned by other keys never wake this window" 用例（本 key 必须保持其绿）。

## §3 验收标准（AC）

> 🔒 AC Locked at 2026-09-23T11:40:00Z，编号永不回收

| AC 编号 | 描述 |
|--------|------|
| AC-001 | 在本窗口的 `dispatchedTaskKeys` 含 task T、T 的 owner key ≠ watched key、T 为 running 且其 `trace.log` 含 `risk=high` 检查点的条件下，轮询一个 tick 后恰好投递 1 条 alert，其文本含 owner key（T 所属 key 名）与既有判据字段（`risk=high`、`reads=`/`writes=`、`trace.log`、`progress.md`），且 `triggerTurn` 为 true |
| AC-002 | 在 owner key ≠ watched key 且 task T **不在** `dispatchedTaskKeys` 的条件下（别窗口的 worker），轮询后投递 0 条 alert（既有"别键 worker 不唤醒本窗口"性质不变） |
| AC-003 | 在本窗口派发的跨 key task 为 running 但 `risk=low`（或无检查点）的条件下投递 0 条；且当同一 task 在后续 tick 仍 `risk=high` 时不再重复投递（每 task 每窗口至多 1 条） |
| AC-004 | watched key 自身高风险 worker 的升级面逐字不变：既有 AC-004 用例（1 条 alert、文本含 `发散风险`/task 名/`risk=high`/`reads=74 writes=0`/`trace.log`/`progress.md`、`triggerTurn=true`、第二 tick 不重复）保持通过 |

## §4 风险与未决项

- 风险 R-1：`dispatchedTaskKeys` 只在当前进程有效——窗口重启后，重启前派出的异地 worker 不再触发升级（面板聚合行同理）。缓解/接受：重启后 PM 通过 `list_tasks` 或面板聚合行主动查看；跨会话追踪是另一议题（未决 Q-1）。
- 风险 R-2：把"本窗口派发"纳入升级面会略增唤醒次数（每个异地高风险 worker 一次）。缓解：once-per-task 去重 + 仅 mid/high。
- 未决 Q-1：`dispatchedTaskKeys` 是否值得持久化（跨会话追踪）？本 key 不做，保持进程内语义（GC-5 的反面即"持久化需另案评估"）。
- 未决 Q-2：是否把升级投递扩到"所有 running worker"（全局广播）？**已否决**（多窗口重复唤醒、越权上下文），见 design D-104。

## §5 记忆前馈（对接项目级记忆门禁）

### 可复用资产

- `pm/pm-orchestrator.ts`：`startWorkerPollLoop(...)`（轮询主体，`notified`/`escalated` 两个进程内集合 + fake-timer 可测结构）、`deliverPmAlert(pi, text)`（唯一投递口，`triggerTurn: true`）、`ownerKeyOf(entry, agenticdocRoot)`（owner 判定）、`readTaskProgress(taskDir)?.checkpoint`（risk 读取）。
- `pm/ui-bridge.ts`：`PmWatchState.dispatchedTaskKeys?: Set<string>`（本窗口派发登记，`mw-task-scope-isolation` 引入）——本 key 的判定输入。
- 测试资产：`test/extensions/agent-team-loop.test.ts` 的 `fakePi()`（捕获 `sendMessage` 文本与 options）、`queueRunning(root, key, taskKey)`（造 running 行）、`mkdtemp()`、既有 AC-004 两个用例（升级面 + 别键静默）——新用例与之同夹具、同断言风格。
- 进程内集合范式：`notified`（终态摘要 once-per-task）与 `escalated`（升级 once-per-task）——本 key 复用 `escalated`，不新增去重结构。

### 需规避坑点

- P-006（绿灯用例的日志通道可能是关闭的）：证据必须是 `output.md` 里可 grep 的 `[VERIFY]` 行（本次取 `agg`/alert 计数与文本片段），不接受"测试通过"的转述。
- P-007（review 无落盘通道）：本 key 任务以 `type: coding` 派发。
- P-010（Python 文本模式翻转换行）：本 key 不改 Python；新增测试文件若含中文断言文本，写入必须保留仓库主导换行（LF）。
- P-011（claim 双写分叉；`mw-worker-visibility-gate` 登记）：本 key 的"两种 owner 语义"（owner key vs 本窗口派发集合）是同类风险的协调面版本——判定必须把两者合并为**或**关系并把"别的窗口"排除在外（AC-002），否则升级面要么漏（当前 bug）要么越权（全局广播）。
- 既有性质守卫：`test/extensions/agent-team-loop.test.ts` 中 "diverging workers owned by other keys never wake this window" 是硬约束，任何放宽容忍度改动都必须让它保持绿（AC-002 即它的显式复述）。
