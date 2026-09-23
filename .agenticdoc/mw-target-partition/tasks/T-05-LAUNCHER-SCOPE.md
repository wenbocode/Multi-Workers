# Task T-05-LAUNCHER-SCOPE: launcher.py + autopilot/dispatch.py

## 基本信息
- Stage: 2
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker mwtp-s2-dispatch
- ac_refs: [AC-006, AC-008, AC-020]
- vc_refs: [VC-006, VC-008, VC-020]
- pattern_refs: []

> [BACKFILLED @ 2026-09-19 verify 阶段质检补救：plan.md 内联任务清单拆分归档；任务已完成并通过验证（证据 evidence/verify-run-2026-09-19.md 与各 worker 回读），本文为形态对齐补记，非新建工作。]

## 描述

_worker_cwd mode 分派（partition→partition_root，single/dual 零变化）+ 撕裂校验（spawn 前 task.md profile 模式行 vs 当前 active，不一致任务 failed 含 config torn，不 spawn；v1 块按含 Game root 行判 dual 否则 single——防 single+sections 误判）+ _expand_read_scope partition 锚定（不因 parent 身份追加）+ describe_target_error 共享动态错误消息（v1 文案不变）。
