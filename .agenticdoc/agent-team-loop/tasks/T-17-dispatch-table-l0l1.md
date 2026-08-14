# Task T-17: dispatch-table.md + L0/L1 验证汇总

## 基本信息
- Stage: 7
- 代码状态: 代码完成
- 验证状态: 已验证（L0+L1 全部 PASS）
- 负责 Agent: claude-sonnet-4-6
- ac_refs: [AC-014]
- vc_refs: [VC-022]
- pattern_refs: []

## 描述
两项收尾工作：

**dispatch-table.md**（AC-014）：
创建 `dispatch-table.md`，说明不同任务类型路由到哪个 CLI + provider：
- 至少 2 行含 `| pi |`（如：通用编码任务、goal elicitation）
- 至少 1 行含 `| codex |`（如：代码补全/重构）
- 至少 2 行含 `| claude |`（如：长文本分析、代码审查）

**L0/L1 验证汇总**：
运行所有 L0（静态检查）和 L1（单元测试）VCs，汇总结果写入 `evidence/runs/l0l1-summary.md`：
- VC-001（DEFAULT_POLL_INTERVAL ≤ 5）
- VC-022（dispatch-table grep 计数）
- VC-036（update_index.py list 格式验证）
- VC-038（并发写入测试）
- VC-041（7 列格式）
- VC-040（非法 Phase 被拒绝）
- 其余 L1 单元测试

## 输入
- 依赖文件: 全部 Stage 1~6 产出 + smoke_test.sh（T-16）
- 依赖 Task: T-16
- AC 约束:
  > AC-014: grep -c "| pi |" dispatch-table.md >= 2；grep -c "| codex |" >= 1；grep -c "| claude |" >= 2

## 预期产出
- `dispatch-table.md`（项目根或 packages/multi-workers/）
- `evidence/runs/l0l1-summary.md`（汇总 L0/L1 VCs PASS/FAIL）
- 验证方式: VC-022（grep 计数）
- 验证等级: Level 0

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-08-11 | 创建 dispatch-table.md（AC-014） | pi=4, codex=2, claude=5 行，≥ 最低要求 ✓ |
| 2 | 2026-08-11 | 运行 L1 test-l1-full.ts（13 个 VC） | 12/13 PASS；VC-041 失败（trailing-space bug） |
| 3 | 2026-08-11 | 修复 test-l1-full.ts VC-041（split 策略） | 13/13 PASS |
| 4 | 2026-08-11 | L0 检查（VC-001/022/027/028/045） | 5/5 PASS |
| 5 | 2026-08-11 | 写入 evidence/runs/l0l1-summary.md | L0 5/5 + L1 13/13 = 18/18 PASS |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
