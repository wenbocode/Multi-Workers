# Task T-07-PY-CLI: mw.py

## 基本信息
- Stage: 3
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: worker mwtp-s3-cli（PM 复核实测）
- ac_refs: [AC-010, AC-011, AC-013, AC-022, AC-023]
- vc_refs: [VC-010, VC-011, VC-013, VC-022, VC-023]
- pattern_refs: []

> [BACKFILLED @ 2026-09-19 verify 阶段质检补救：plan.md 内联任务清单拆分归档；任务已完成并通过验证（证据 evidence/verify-run-2026-09-19.md 与各 worker 回读），本文为形态对齐补记，非新建工作。]

## 描述

mw partition set/show/clear/on/off 全命令族：set 前置六道校验（交叉 env/缺参/--root 语法/路径存在/根关系/落盘）、v1 一次性迁移（.bak+手维护段迁入 dual 块+提示）、块级编辑+os.replace 原子写、同参幂等；target 命令族最小改动（show 守卫 active:partition exit 1、v2 dual 块分支、on/off 对称；v1 路径零改动红线）。test_mw_partition.py 41 用例。
