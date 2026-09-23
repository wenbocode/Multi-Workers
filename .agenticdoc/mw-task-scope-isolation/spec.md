# Spec: mw-task-scope-isolation（worker 任务的窗口级隔离：list_tasks scope + ack 收窄）

> Key: mw-task-scope-isolation
> 创建时间: 2026-09-23
> 状态: locked

## §0 Goal Alignment

> 来源：`.agenticdoc/goal.md`（已确立）

- 对齐：goal 的模型是「一个 PM Agent 管多个 Worker，多个窗口并行开发同一项目」。多窗口并行的前提是**每个窗口只看得到、只动得了自己那一份**；本 key 修的正是当前唯一残留的越界面——worker 任务清单与 ack 通道是项目级全局的，任何窗口都能列、能 ack 别人的任务。
- 继承约束（GC 编号）：
  - GC-1: 不修改 pi 核心：只改 agent-team-loop 扩展的 PM 工具面（`pm/ui-bridge.ts`），走 `pi.registerTool`。
  - GC-2: 不引入中心化调度：不加服务端状态、不加记账文件、不改 `_workers.parallel` 列（Python 侧零改动、零格式变更）。
  - GC-3: 文件驱动协调不变：归属判定沿用既有文件事实（taskPath 的 owner key + 本窗口 claim）。
- 冲突：无。`scope:"all"` 保留旧行为，不删除任何既有能力。
- 预期收益：多窗口并行时，A 窗口的 `list_tasks` 不再混入 B 窗口的任务，`ack_worker_result("all")` 不再清空 B 窗口的待处理清单；PM 看什么、动什么与底部 watch widget 同口径（widget 已按 owner key 收窄）。判定：AC-001..AC-008 逐条通过。

## §1 功能概述

### 1.1 目标

1. `list_tasks` 增加 `scope: "mine" | "key" | "all"`（默认 `mine`）与 `key?: string`；输出行带上 owner key，使跨 key 列表可读。
2. `ack_worker_result` 与 `/mw ack`（共用 `ackTasks`）收窄到本窗口：`"all"` 只含本窗口的终态未 ack 行；显式指名别的 key 的行 → 拒绝并说明原因，不写盘。
3. 本窗口的"自己派发的"= **本窗口 watch 的 key** ∪ **本进程派发出去的任务**（显式跨 key 派发也算自己派发的）。

### 1.2 技术栈 / 语言

TypeScript（agent-team-loop 扩展，erasable syntax only）。零 Python 改动，零文件格式改动。

### 1.3 核心用户场景

1. **多窗口并行**：窗口 A 做 key X，窗口 B 做 key Y。A 的 `list_tasks` 只列 X 的任务；要看全局得显式 `scope:"all"`。
2. **跨 key 显式派发**：A 用 `dispatch_worker(key: "Y", ...)` 往 Y 塞了一个任务（既有能力，`resolveOwnerKeyWithSync` 允许显式 key）。该任务仍出现在 A 的 `mine` 里，A 也能 ack 它。
3. **误 ack 防护**：A 执行 `ack_worker_result(task_key_of_B)` → 拒绝，原因写明 owner key 与 `/pm-key switch` 指引，`_workers.acked` 不变。
4. **无 claim 窗口**：没接管任何 key 的窗口 `list_tasks` 返回空 + 提示（`switch_key` 或 `scope:"all"`），不抛异常。
5. **全局盘点**：需要查重 task_key / 全局巡检时 `scope:"all"` 一次拿全。

### 1.4 范围说明（不做什么）

- 不改 `_workers.parallel` 列（不加 dispatcher 字段）——会牵动 launcher/mw_common 的解析与并发重写，收益不抵成本。
- 不拆分 `.agenticdoc/_workers.acked`（ack 事实是项目级的、widget 读取端已按窗口收窄）；只收窄写入路径。
- 不改 watch widget 渲染（meta/widget 侧本来就按 owner key 收窄，本 key 是让工具对齐它）。
- 不做 `_scratch` 的特例泛化：`_scratch` 只是另一个 owner key，除非本窗口 watch 它或本窗口派发过它下面的任务，否则不属于 `mine`。
- 不改 autopilot/conductor 侧（Python）的 any-key 读取。

## §2 业务约束

### 2.1 平台 / 环境

Windows 开发机；PM 窗口；工具经扩展 bundle 装载（生效需 `mw build --install` + 新窗口）。

### 2.2 性能指标

`readAll()` 一次读、内存过滤（既有量级：几十行）；无新增 I/O、无新增定时器。

### 2.3 安全约束

- 收窄必须 fail-closed：无法判定归属时按"不是我的"处理（拒绝 ack / 不计入 mine），并给出可执行的指引。
- 拒绝路径不得写盘（`_workers.acked` 保持原样）。

### 2.4 兼容性约束

- `scope:"all"` 语义与当前 `list_tasks` 完全一致（含 acked 徽标）。
- ack 行为变化是**有意的行为变更**：`/mw ack all` 从"全项目"变为"本窗口"，写入 `packages/coding-agent/CHANGELOG.md` 的 Unreleased。
- 无 claim 窗口不得因收窄而无法 ack 自己刚派发的任务（AC-006 覆盖）。

## §3 验收标准（AC）

- AC-001: `list_tasks` 无参调用默认 `scope:"mine"`；返回行只含"本窗口 watch 的 key ∪ 本窗口本进程派发过的任务"；每行包含 owner key（形如 `<owner> :: <taskKey> | <status> | ...`）。
- AC-002: `scope:"all"` 的输出与改动前一致（全项目所有 owner key + `_scratch`，含 `acked` 徽标）。
- AC-003: `scope:"key"` + `key:"<k>"` 只返回该 owner key 的行；`scope:"key"` 缺 `key` 时返回参数错误提示文本，不抛异常。
- AC-004: 本窗口既无 watch key、也无本进程派发记录时，`scope:"mine"` 返回提示文本（含 `switch_key` 与 `scope:"all"` 指引），不抛异常、不返回其它窗口的行。
- AC-005: `ack_worker_result("all")` 与 `/mw ack all` 只 ack 本窗口的行（watch key ∪ 本进程派发）；别的 owner key 的终态未 ack 行保持不变。
- AC-006: `ack_worker_result(<task_key>)`：本窗口的（含显式跨 key 派发的）→ ack 成功；owner key 属于别处的 → 拒绝，原因含该 owner key 与 `/pm-key switch` 指引，且 `_workers.acked` 无新增行。
- AC-007: 显式跨 key 派发（`dispatch_worker` 带 `key:"X"`，X ≠ watch key）后，该任务出现在 `mine` 中且可被本窗口 ack（派发记账生效）。
- AC-008: 回归与质量：既有 `test/extensions/agent-team-loop.test.ts` 全绿（含 widget 渲染、dispatch 路由、ack 校验既有用例）；`npm run check` 零 error/warning/info；新增用例覆盖 AC-001..AC-007。

## §4 证据（evidence/research）

零外部调研：全部事实来自本仓代码（`ui-bridge.ts` 的 `list_tasks`/`ackTasks`/`ownerKeyOf`/`resolveOwnerKeyWithSync`、`ack-store.ts`、`worker-store.ts`），见 `evidence/research/spec-task-scope-isolation-2026-09-23.md`。
