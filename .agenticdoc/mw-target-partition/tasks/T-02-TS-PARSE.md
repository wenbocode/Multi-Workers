# Task T-02-TS-PARSE: shared/target-config.ts

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker mwtp-s1-parse-retry
- ac_refs: [AC-001~005, AC-017]
- vc_refs: [VC-001~005, VC-017]
- pattern_refs: []

> [BACKFILLED @ 2026-09-19 verify 阶段质检补救：plan.md 内联任务清单拆分归档；任务已完成并通过验证（证据 evidence/verify-run-2026-09-19.md 与各 worker 回读），本文为形态对齐补记，非新建工作。]

## 描述

与 T-01 严格同构：export decideActiveMode、WorkspaceConfig 增量字段（gameRoot 可空/parentRoot/partitionRoot/roots）、v2 块解析与校验、EP 覆盖、渲染分派；下游 gameRoot 可空调用点按 mode 分支（partition 不调 discoverUproject）。
