---
type: research
write_face:
  - .agenticdoc/_scratch/evidence/t22-live-verify.md
---

# T22 live verify: 新决策记录的任务前后快照

## 上下文

目标锚点：`.agenticdoc/goal.md:5`。本任务是 T22（`.agenticdoc/mw-decision-context/tasks/T22-task-state-transition.md:1`）重打包后的**实机验收**：扩展 bundle 已从 `0d08fb32` 更新为含 T22 采集代码的 `d7efe818`，本任务自身的 dp1 派发就是第一个新记录。

你的 task_key 是 `t22-live-verify-20261025`，owner key 是 `_scratch`。

关键事实入口（只读）：
- `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts:3350`（派发前 `captureDecisionTaskState`）与 `:3433`（派发后 `taskAfter`）
- `packages/multi-workers/decision_lifecycle.py:485` 起（record-start / lifecycle 写入口）
- 生产账本：`.agenticdoc/_autopilot/decision-lifecycle.jsonl`

## 要求

1. 只读 `.agenticdoc/_autopilot/decision-lifecycle.jsonl`，筛出 `task_key == "t22-live-verify-20261025"` 的所有行，按文件顺序列出。
2. 逐项报告：`record-start` 行的 `task_before` 是否为对象、其 `status/source/observed_at/completed/remaining/blockers` 原值；`lifecycle` 行（consumed/executed/settled）各自的 `task_after` 原值。
3. 判定并明确写出三件事：(a) 决策前快照是否存在；(b) 实际处理后的快照是否存在；(c) `after.observed_at` 是否不早于 `before.observed_at`，且 after 行与 record-start 的 logical_id/key/task_key 是否一致。
4. 若字段缺失或为 null，直接写"未记录/不存在"，不要推断、不要用任务当前状态补填，不要改任何账本行。
5. 不运行测试、真实模型请求、mw serve、monitor、sign、build、install、commit；不调用 ask_decision；只读账本并写你自己的唯一证据文件。
6. 时间预算约 10 分钟，证据文件 <= 120 行。

## 交付格式

唯一证据文件含：结论（三件事各一行，是/否 + 原值）、筛选出的原始行摘要（键名 + 关键字段值）、判定依据（行序/时间戳）、未覆盖面。最终回复只给摘要和证据路径，不声称整 key 验收通过。

## 唯一证据文件

.agenticdoc/_scratch/evidence/t22-live-verify.md

## 写入允许面

- .agenticdoc/_scratch/evidence/t22-live-verify.md

## 写入禁止面

生产账本、任何源码、测试、registry/生成物、配置、framework、其他 key 的文档与证据、pi 全局配置与凭证。除框架自动管理的自身 worker 产物外不写其他路径。
