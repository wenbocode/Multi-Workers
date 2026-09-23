# Task T-00-BASELINE-GOLDEN: 双侧 golden 基线测试文件

## 基本信息
- Stage: 0
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker mwtp-s0-baseline（PM 复核实测）
- ac_refs: [AC-016]
- vc_refs: [VC-016]
- pattern_refs: []

> [BACKFILLED @ 2026-09-19 verify 阶段质检补救：plan.md 内联任务清单拆分归档；任务已完成并通过验证（证据 evidence/verify-run-2026-09-19.md 与各 worker 回读），本文为形态对齐补记，非新建工作。]

## 描述

实现合入前在当前 HEAD 录制 v1 dual 完整样例 + 无文件 single 样例的六类输出 golden（legacy 字段投影/_worker_cwd/scope 展开/target show/doctor 段 JSON——Py 五类；TS 加 profile 注入块全文与 render）。16 条 golden，缺失即录/存在即比对双模式，路径归一（tmp 根→<CTRL>）。此后每棒以基线 MATCH 为 v1 零行为活断言。
