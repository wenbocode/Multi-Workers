# Task T-08: TS waitForMwStart 稳定窗（假成功播报修复）

## 基本信息
- Stage: 4
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-005]
- vc_refs: [VC-006]
- pattern_refs: []

## 描述
改造 `packages/coding-agent/src/extensions/agent-team-loop/shared/mw-runner.ts`（design D-006）：
1. `waitForMwStart(projectDir, timeoutMs = 8000, stableMs = 3000)`：PID 出现后须连续存活 `stableMs` 才返回 true；稳定窗内进程死亡则继续轮询（直到 timeout，最终以即时状态返回）
2. `pm-orchestrator.ts` session_start 播报：确认失败分支文案改为引导诊断（如 `[mw] Background service 未确认启动（可能预检失败）——运行 /mw doctor 诊断`），不再出现"Background service started."假成功
3. vitest 单测（新文件，见 T-10 的 `agent-team-loop.test.ts` 或独立 describe）：mock `getMwStatus` 序列（出现→3s 内死亡→超时）断言 false；（出现→持续存活）断言 true
4. 实现注意：轮询 tick 250ms 不变；连续存活的判定基于相邻 tick 状态（死亡重置稳定计时）

## 输入
- 依赖文件: mw-runner.ts、pm-orchestrator.ts
- 依赖 Task: 无（与 Python 侧并行）
- AC 约束:
  > AC-005: 在 mw serve 启动后实际死亡的条件下，PM 会话播报中不出现 "Background service started"，且 mw_status 工具在 10s 内报告 not running

## 预期产出
- mw-runner.ts / pm-orchestrator.ts 改造
- vitest 用例
- 验证方式: VC-006
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-08-28 20:10 | 执行完成（详见 evidence/runs/l2-summary.md） | PASS |

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: 无
- 卡住原因: 无
- 处置: 无
