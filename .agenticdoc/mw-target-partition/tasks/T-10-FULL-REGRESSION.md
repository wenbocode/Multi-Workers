# Task T-10-FULL-REGRESSION: 全量测试 + 基线终验

## 基本信息
- Stage: 4
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker mwtp-s4-verify（PM 复核实测）
- ac_refs: [AC-013, AC-016]
- vc_refs: [VC-013, VC-016]
- pattern_refs: []

> [BACKFILLED @ 2026-09-19 verify 阶段质检补救：plan.md 内联任务清单拆分归档；任务已完成并通过验证（证据 evidence/verify-run-2026-09-19.md 与各 worker 回读），本文为形态对齐补记，非新建工作。]

## 描述

Py 全量 660 passed / TS extensions 族 377 passed / S0 基线双侧 MATCH / CLI E2E 冒烟七步（set/show/off/on/doctor/v1 迁移 .bak 440 字节完整/守卫 exit 1）。零修改审计：fixture 001~014 零改动，既有测试 6 删行全为 runner 空值容差。
