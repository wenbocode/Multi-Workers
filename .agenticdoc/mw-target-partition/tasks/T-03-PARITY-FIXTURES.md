# Task T-03-PARITY-FIXTURES: fixtures/target-config-cases/ + 两侧 runner

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker mwtp-s1-parse-retry
- ac_refs: [AC-001~003, AC-005, AC-017]
- vc_refs: [VC-001~003, VC-005, VC-017]
- pattern_refs: []

> [BACKFILLED @ 2026-09-19 verify 阶段质检补救：plan.md 内联任务清单拆分归档；任务已完成并通过验证（证据 evidence/verify-run-2026-09-19.md 与各 worker 回读），本文为形态对齐补记，非新建工作。]

## 描述

夹具续号 015~039 共 25 个新 case（v2 正常/驻留/混格式/坏 active/缺块/白名单/roots 键名/根关系相等与互嵌/EP 覆盖/空白串/env 无文件激活/交叉/v1+EP 交叉/dual 块 env），既有 001~014 零修改；共享参数表 active-mode-table.json（112 组合，规则行 2/3/5~12）双侧同表；两侧 runner 增量支持新可选字段（删行仅空值容差 or ""/?? null）。
