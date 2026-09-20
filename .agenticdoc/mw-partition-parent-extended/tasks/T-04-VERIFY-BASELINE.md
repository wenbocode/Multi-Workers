# Task T-04-VERIFY-BASELINE: 全量验证与零回归审计

## 基本信息
- Stage: 4
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: PM（本窗口）或 worker
- ac_refs: [AC-006]
- vc_refs: [VC-009]
- pattern_refs: []

## 描述

前置：T-01/T-02/T-03 全部完成。

1. **Py 全量**：`packages/multi-workers` 既有测试入口全量运行（与 mw-target-partition verify 同口径：Py 全量 passed，0 failed）。基线参照：Windows 环境噪音对照 repo AGENTS.md 基线说明；multi-workers 包无已知基线失败。
2. **TS 全量**：`./test.sh`（repo 根，非 e2e）或 coding-agent 相关套件（autopilot-read-scope / profile-injection / agent-team-loop / target-config）全绿。
3. **`npm run check`**：0 error / 0 warning / 0 info（全输出留档）。
4. **修改面审计**（git diff 核对，AC-006）：
   - dual/single 既有用例零修改（autopilot-read-scope.test.ts 既有 describe、agent-team-loop-profile-injection.test.ts 既有 dual/single 用例、Py dual/single 用例）
   - partition 既有用例修改限于：`test_partition_anchors_at_partition_root`（T-01 翻转）、标签三触点（T-03）、golden fixture（T-03）——逐条列出归类
5. **VC-008 grep 审计**：`mw.py` partition 相关无 "read-only" 残留。
6. **bundle 重建**：`packages/multi-workers/dist/extensions/agent-team-loop.js` 重建（`npm run build` 于 multi-workers 或既有构建入口），`packages/coding-agent/dist` 随构建对齐。
7. **[VERIFY] VC-009 落盘**：`evidence/verify-run-<date>.md` 汇总 VC-001~009 证据行（复用各 task 输出 + 本 task 全量结果）。

## 完成判定

- 全量 Py/TS 绿 + check 0/0/0 + 审计清单落盘
- 输出 `[VERIFY] VC-009: legacy=green-zero-mod, partition_diff=bounded, check=0/0/0`
