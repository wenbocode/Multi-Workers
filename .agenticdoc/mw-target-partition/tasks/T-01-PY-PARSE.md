# Task T-01-PY-PARSE: mw_common.py

## 基本信息
- Stage: 1
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker mwtp-s1-parse-retry（首派 mwtp-s1-parse 模型流挂死，重派完成）
- ac_refs: [AC-001~005, AC-017]
- vc_refs: [VC-001~005, VC-017]
- pattern_refs: []

> [BACKFILLED @ 2026-09-19 verify 阶段质检补救：plan.md 内联任务清单拆分归档；任务已完成并通过验证（证据 evidence/verify-run-2026-09-19.md 与各 worker 回读），本文为形态对齐补记，非新建工作。]

## 描述

_decide_active_mode 纯函数（spec §1.5 规则表 12 行，行序即优先级）+ v2 检测（active 键）+ 块解析（dual/partition 白名单）/字段层 7 类校验/roots 键名与根关系/EP 覆盖统一（source 3 枚举不新增）/renderToolchainCommand mode 分派 token 集。v1 分支对既有合法输入行为零变化（S0 基线 MATCH 钉死）。
