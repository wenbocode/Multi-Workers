# TRQ-3: PM 侧感知路径与重派回路（research）

type: research

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（文件驱动去中心化协调 _workers.parallel/_index.parallel；PM Agent 管理多个 Worker）。
- 问题：worker 因模型错误死亡后，PM 侧今天能看到什么、缺什么；自动重派（autopilot/PM triggerTurn 重派）会不会把新 worker 派进同一个死模型形成无限循环。历史坑（`.agenticdoc/_pitfalls.md`）：2026-09-22 12 个 review worker 中 4 个 `stream closed before response.completed` 空产出仍被判读；另一事故 worker 连续 12 次失败重派（疑似模型连接失败），PM 感知为「无限死循环、无法推进」。

## 要求

1. 画出 worker 终态到 PM 的完整感知链路：launcher.py（`packages/multi-workers/launcher.py`，run.json/worker.log 写入点，:2009-2017 附近）→ tree_watch.py（`packages/multi-workers/tree_watch.py`，watch 行生成）→ PM 窗口 widget（`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`）→ autopilot/conductor（`packages/coding-agent/src/extensions/agent-team-loop/autopilot/*.ts`、pm/pm-orchestrator.ts:500-600, 1828-1840 的 orphan/no-product 告警）。
2. 核验 `recordDispatchAlarm` 的 kind 集合与消费方（worker-mode.ts 触发 no-product；谁读告警、有没有阈值/熔断），列出新增 kind（如 model-error）需要动的全部位置。
3. 今天一个 worker 以 status=failed + Exit Reason X 终结时，PM 窗口的确切可见物（widget 行样式、是否需要 ack、autopilot 是否会因它暂停/继续）；自动重派路径盘点：谁会在 worker failed 后再次派发同一 key 的新 worker（conductor 重试语义、PM 手动、autopilot L1/L2/L3），现有频率限制。
4. 结论→决策映射：worker 侧应新增什么机器信号（trace 行/告警 kind/Exit Reason 约定），PM 侧「同 key 连续 N 次 model-error 终结即熔断并升级人工」应挂在哪个现有钩子上最小侵入。

## 写入允许面

- 仅允许写：`.agenticdoc/mw-model-error-perception/evidence/research/spec-pm-perception-path-2026-10-15.md`

## 交付格式

- 唯一证据文件：`.agenticdoc/mw-model-error-perception/evidence/research/spec-pm-perception-path-2026-10-15.md`（只写此一个文件）
- 结构：感知链路图（带 文件:行号）→ 告警 kind 全表 → 重派回路盘点 → 插桩点建议
