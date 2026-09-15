# Task T-04-PM-ALERT-PATH: ui-bridge.ts + pm-orchestrator.ts

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM 窗口
- ac_refs: [AC-004, AC-005]
- vc_refs: [VC-004, VC-006]
- pattern_refs: []

> [BACKFILLED @ 2026-09-09 恢复复验轮：自 plan.md 内联任务清单拆分归档；任务在 2026-09-09 已完成并通过质检（evidence/quality-gate-report-2026-09-09.md 9/9 充分），本文为形态对齐补记，非新建工作。]


## 描述

ui-bridge.ts + pm-orchestrator.ts：deliverPmAlert 抽取；poll 循环 checkpoint 徽标（ck<m>m <risk>）+ mid/high 一次 triggerTurn 升级；PM_CONTINUE_HINT 超时分支（双倍预算重试一次→再失败转 PM 直执）

## 输入
- 依赖文件: pm/ui-bridge.ts、pm/pm-orchestrator.ts

## 验证（补记自质检报告）

见 evidence/quality-gate-report-2026-09-09.md 对应 Q-AC/Q-VC 行：9/9 充分。
