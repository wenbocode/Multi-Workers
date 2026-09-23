# Task T-06-DOCTOR-CACHE: mw_common.py

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker mwtp-s2-dispatch
- ac_refs: [AC-009, AC-018cd]
- vc_refs: [VC-009, VC-018]
- pattern_refs: []

> [BACKFILLED @ 2026-09-19 verify 阶段质检补救：plan.md 内联任务清单拆分归档；任务已完成并通过验证（证据 evidence/verify-run-2026-09-19.md 与各 worker 回读），本文为形态对齐补记，非新建工作。]

## 描述

_doctor_target：partition 激活时 config 加 partition-only 键（parent_root/partition_root/roots；dual/single/v1 段 JSON 零新键）+ checks 对 parent_root/partition_root/root:<名> 各一条（无 uproject/engine）+ probe 缓存 resolved-config 指纹（active 模式+归一根集合）+ mtime 双判，旧缓存无指纹视为陈旧。
