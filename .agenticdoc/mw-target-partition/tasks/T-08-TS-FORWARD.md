# Task T-08-TS-FORWARD: ui-bridge.ts + mw-runner.ts

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker mwtp-s3-cli
- ac_refs: [AC-012]
- vc_refs: [VC-012]
- pattern_refs: []

> [BACKFILLED @ 2026-09-19 verify 阶段质检补救：plan.md 内联任务清单拆分归档；任务已完成并通过验证（证据 evidence/verify-run-2026-09-19.md 与各 worker 回读），本文为形态对齐补记，非新建工作。]

## 描述

/mw partition set/show/clear/on/off 转发：mirror /mw target 模式（flag 解析、可注入 runner、usage），mw-runner partitionMw 一行包装；agent-team-loop.test.ts 新 describe（fake runner 参数序列/usage/未知动词）。set 输出确定性（透传 vs 直调字节一致）在 Py 测试断言。
