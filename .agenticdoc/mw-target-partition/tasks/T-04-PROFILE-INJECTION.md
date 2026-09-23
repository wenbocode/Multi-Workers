# Task T-04-PROFILE-INJECTION: pm/task-dispatcher.ts

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker mwtp-s2-dispatch（PM 复核实测）
- ac_refs: [AC-007, AC-018ab, AC-019]
- vc_refs: [VC-007, VC-018, VC-019]
- pattern_refs: []

> [BACKFILLED @ 2026-09-19 verify 阶段质检补救：plan.md 内联任务清单拆分归档；任务已完成并通过验证（证据 evidence/verify-run-2026-09-19.md 与各 worker 回读），本文为形态对齐补记，非新建工作。]

## 描述

PROFILE_MARK v2（仅 partition 注入；dual/single 维持 v1 标记文本零变化——AC-007 [REVISED @ 2026-09-19] 裁定）+ renderPartitionProfileBlock（mode 行/parent/partition/roots/渲染 toolchain/firewall/contract）+ 切换整体替换（标记行到 EOF；含 v1 旧块遇 partition 激活整体替换、切回不注入模式字节还原）。
