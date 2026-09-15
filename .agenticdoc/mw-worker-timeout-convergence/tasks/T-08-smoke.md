# Task T-08-SMOKE: 小预算实机烟雾

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-001~AC-004]
- vc_refs: [VC-001~VC-004]
- pattern_refs: []

> [BACKFILLED @ 2026-09-09 恢复复验轮：自 plan.md 内联任务清单拆分归档；任务在 2026-09-09 已完成并通过质检（evidence/quality-gate-report-2026-09-09.md 9/9 充分），本文为形态对齐补记，非新建工作。]


## 描述

小预算实机烟雾：task.md `timeout: 2` 头 + PI_WORKER_IDLE_MS=20000，验证 wall/idle/checkpoint/steer 全路径实跑（Run 1 发现 steer 排队缺陷并修复 followUp/steer；Run 2 全路径 PASS，agent 预算内自行收尾 exit=0）

## 输入
- 依赖文件: workers/smoke-watchdog/、evidence/runs/smoke-watchdog-2026-09-09.md

## 验证（补记自质检报告）

见 evidence/quality-gate-report-2026-09-09.md 对应 Q-AC/Q-VC 行：9/9 充分。
