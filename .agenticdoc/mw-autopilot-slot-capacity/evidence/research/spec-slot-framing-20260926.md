# Research: slot 语义与并发上限的代码事实（spec 框架 / PM 自采）

## 决策问题

支撑 spec §1.1（"slot 到底是什么"）、§3 draft AC-001（三层上限清单）、§4 U-4（要提 key 层还是 worker 层）：在**不改动任何代码**的前提下，先由 PM 采一份最小代码事实集，用于给后续 4 个 research RQ 划定互不重叠的边界。

## 调研方法与出处

只读 grep + 阅读既有文件（命令与命中原样记录）：

- `rg -n "slots|max_parallel_keys|maxParallelKeys" packages/multi-workers packages/coding-agent/src`
- `rg -n "max_workers|maxWorkers|concurrency|in_flight_keys|busyKeys|Semaphore|max_parallel" packages/multi-workers/*.py packages/multi-workers/autopilot/*.py packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts`
- 直接读 `packages/multi-workers/autopilot/config.py`、`packages/multi-workers/autopilot/conductor.py:280-300`、`packages/coding-agent/src/extensions/agent-team-loop/autopilot/monitor.ts:505-525`

## 发现

1. **`max_parallel_keys` 是 key 层上限，默认 2，floor 2**：
   - `autopilot/config.py:16` 注释 `max_parallel_keys  int     2    (floor 2)`
   - `autopilot/config.py:52` `"max_parallel_keys": 2`
   - `autopilot/config.py:70` `"max_parallel_keys": (2, None)`（下限 2、无上限）
   - TS 镜像：`status-model.ts:79`（类型）、`:106`（`DEFAULT_CONFIG`）、`:136`（`INT_RANGES`）、`:271`（`intOf`）、`:296`/`:1166`（传递）、`:1199`（状态行文本）、`:1050`（状态 JSON 字段）
2. **它的唯一 gate 点在 conductor 派发**：`conductor.py:289` `if len(in_flight_keys) >= max(1, int(cfg["max_parallel_keys"])):`（其上游是同一函数内的 in-flight key 统计；具体语义待 RQ-1 取证到行）。
3. **监控面板的 "slot" = 有 running worker 的 key 集合大小**（不是 worker 数）：
   - `monitor.ts:509-512` `busyKeys` / `busyKeys.add(owner ?? w.taskKey)`
   - `monitor.ts:521-522` `slotsUsed: busyKeys.size` / `slotsMax: config?.max_parallel_keys ?? DEFAULT_CONFIG.max_parallel_keys`
   - `monitor.ts:596` 渲染 `slots ${used}/${max}`
4. **在本轮 grep 范围内没有发现 worker 层并发上限**：`max_workers|maxWorkers|concurrency|in_flight_keys|Semaphore|max_parallel` 在 `packages/multi-workers/*.py` 与 `autopilot/*.py` 中**零命中**（除 `in_flight_keys` 属于 conductor 的 key 统计）。⇒ worker 层是否存在隐式上限（例如 launcher 每次 poll 取几行、每 key 几轮、proxy 端口数、serve 的单线程循环）**未定**，这正是 RQ-1/RQ-2 的取证对象。
5. **项目配置面**：`README.md:225` 有 `max_parallel_keys | 2 | 同时推进的 key 上限` 一行（文档已记录该键，说明"2"是**有意的默认**而非偶然值——成因出处待 RQ-1/RQ-3）。

## 结论 → 决策映射

- 支撑 **spec §1.1**：必须在 spec 里把 "slot = key 层" 写死，否则用户的"并行度不够"会被误读成"worker 数不够"。
- 支撑 **draft AC-001**：三层清单（key / worker / serve-launcher）作为独立判据，因为现状只见到第一层。
- 支撑 **§4 U-4**：把"提 key 层还是 worker 层"列为待用户确认项。
- 支撑 **§4 风险 1**：进而在 RQ-3 中量化"槽位利用率"——若利用率长期 < 100%，提高上限无收益；若长期打满，才谈提高。
- **边界声明**：本笔记只做"发现与划界"，不做成因判定与吞吐测量；那两类结论分别由 RQ-1/RQ-2（代码与资源约束）与 RQ-3（历史吞吐）产出，避免与后续笔记重复。
