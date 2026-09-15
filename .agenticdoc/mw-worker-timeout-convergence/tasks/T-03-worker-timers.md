# Task T-03-WORKER-TIMERS: worker-mode.ts

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-001, AC-002, AC-003]
- vc_refs: [VC-001, VC-002, VC-003]
- pattern_refs: []

> [BACKFILLED @ 2026-09-09 恢复复验轮：自 plan.md 内联任务清单拆分归档；任务在 2026-09-09 已完成并通过质检（evidence/quality-gate-report-2026-09-09.md 9/9 充分），本文为形态对齐补记，非新建工作。]


## 描述

worker-mode.ts：预算解析（task.md `timeout:` 头 > PI_WORKER_TIMEOUT_MS > 默认 60m）、事件 touch 活动跟踪、idle interval + wall timeout、checkpoint 调度（min(30m, budget/2) + 每 10m 刷新）、两处 steer（自评/收尾）、信号计数器、computeRisk 启发式

## 输入
- 依赖文件: worker/worker-mode.ts；含 T-05 parseTaskMd timeout 头（同文件独立提交点）

## 验证（补记自质检报告）

见 evidence/quality-gate-report-2026-09-09.md 对应 Q-AC/Q-VC 行：9/9 充分。
