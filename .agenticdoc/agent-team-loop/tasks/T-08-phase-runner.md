# Task T-08: phase-runner.ts（Goal-Anchored 多阶段执行）

## 基本信息
- Stage: 4
- 代码状态: 代码完成
- 验证状态: 验证通过
- 负责 Agent: TBD
- ac_refs: [AC-016, AC-017, AC-018]
- vc_refs: [VC-024, VC-025, VC-026]
- pattern_refs: []

## 描述
实现 `worker/phase-runner.ts`：处理 task.md 含 `phases` 字段时的多阶段执行逻辑。

每完成一个阶段：
1. 将阶段摘要写入 `<key>/progress/phase-N.md`（N 为 1-indexed，> 20 bytes）
2. 读取 `.agenticdoc/goal.md` 的 mtime 和内容
3. 在 `<key>/trace.log` 追加 `[GOAL_CHECK] phase=N goal_mtime=<timestamp>`

goal.md mtime 变化（被 PM 修订）时，下一阶段开始前感知到变更并在 trace.log 记录更新后的 mtime。

## 输入
- 依赖文件: `worker/output-writer.ts`（T-09，写 trace.log 可复用）
- 依赖 Task: T-09（可先 stub）
- AC 约束:
  > AC-016: phases 非空时，每完成一 phase 写 progress/phase-N.md（> 20 bytes）
  > AC-017: 写 phase-N.md 后、下一 phase 前，读 goal.md mtime，写 [GOAL_CHECK] trace 记录
  > AC-018: goal.md mtime 变化时，下一 [GOAL_CHECK] 记录的 mtime 与修订后文件一致（误差 < 1s）

## 预期产出
- `packages/coding-agent/src/extensions/agent-team-loop/worker/phase-runner.ts`
  - `export async function runPhases(phases: TaskPhase[], context: PhaseContext): Promise<PhaseResult[]>`
  - `PhaseContext`: `{taskKey, agenticdocRoot, pi}`
  - 每个阶段产出 `{phaseIndex, summary, goalMtime}`
- 验证方式: VC-024（progress/phase-1.md > 20 bytes）、VC-025（trace.log [GOAL_CHECK]）、VC-026（mtime 误差 < 1s）
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|

### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
