# Task T-05: 终态 detail 取源（PM 展示侧回退链）

## 基本信息
- Stage: 3
- 代码状态: 代码完成（PM 直执）
- 验证状态: 验证通过（vitest 100/100 含 7 个新用例 + [VERIFY] VC-007/008/009 埋点；biome 零告警）
- 负责 Agent: 待定
- ac_refs: [AC-007, AC-008, AC-009]
- vc_refs: [VC-007, VC-008, VC-009]
- pattern_refs: []

## 描述
`packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`：

1. **`readOutputSection(taskDir: string, section: string): string | undefined`**——泛化现有 readOutputSummary 的节匹配（`## ${section}` 起至下一 `## ` 或文末）；readOutputSummary 改为其薄封装或移除（按实际引用决定，不留死代码）
2. **`readWorkerLogTail(taskDir: string): string | undefined`**——worker.log 最后一条非空行；文件 >256KB 或缺失 → undefined
3. **`readTerminalDetail(taskDir: string, status: WorkerStatus): string`**（D-004 回退链，返回单行已 trim，行宽截断由调用方 trunc 处理）：
   - failed：`readSpawnFailure`（现有，已剥 `[launcher]` 前缀）?? `readOutputSection(dir, "Exit Reason")` 首行
   - needs-clarification：`readOutputSection(dir, "Questions")` 首行 ?? `readWorkerLogTail(dir)` ?? `"no output.md"`
   - done：`readOutputSection(dir, "TL;DR")` 首行 ?? 清洗后 `readOutputSection(dir, "Summary")` 首行；清洗 = 剥开头 `#{1,6} `/`**`/`[-*] `/`> ` 标记（与 worker 侧 headline 同规则，展示侧为旧文件兜底）
   - 首行提取统一 `split("\n")[0].trim()`
4. renderWatchLines 终态分支改用 readTerminalDetail（本 Task 先接上，分区重构在 T-06）

**测试**（agent-team-loop.test.ts 追加 describe；此为 PM 直执任务，无并行冲突）：
- failed：Exit Reason 首行直出（VC-007）；spawn 失败行优先且剥前缀；detail 无 `#`/`**`/`- ` 开头
- needs-clarification：Questions 首行（VC-008）→ 无 Questions 有 worker.log → 尾行 → 两者皆无 → `no output.md`；worker.log >256KB 不读
- done：TL;DR 直出；无 TL;DR 旧文件 → Summary 首行剥标记（VC-009 展示半）；超长截断
- 输出对应 `[VERIFY] VC-007/008/009: ...` 埋点行

## 输入
- 依赖文件: `pm/ui-bridge.ts`（readOutputSummary/readSpawnFailure 现状）
- 依赖 Task: T-03（TL;DR 节格式已定义）
- AC 约束:
  > AC-007: 在 worker 行状态为 failed 时，widget 行 detail 为该任务 output.md `## Exit Reason` 节首行（超行宽截断）；launcher spawn 失败行为 spawn failed 原因行（剥除 `[launcher]` 前缀）；detail 不以 `#`、`**`、`- ` 开头
  > AC-008: 在 worker 行状态为 needs-clarification 时，widget 行 detail 为 output.md `## Questions` 节首行（超行宽截断）；无 `## Questions`（含 claude/codex 任务无 output.md 的情形）时回退为 worker.log 最后一条非空行，仍无则显示 no-output 提示
  > AC-009: …旧 output.md（无 TL;DR）回退取 `## Summary` 首行并剥离开头 markdown 标记（`#`/`**`/`- `）（展示半）
- 设计约束:
  > D-004: 按状态取源 + 回退链；worker.log 回退读加 256KB size guard

## 预期产出
- `pm/ui-bridge.ts`（readOutputSection / readWorkerLogTail / readTerminalDetail + render 终态分支接线）
- `agent-team-loop.test.ts`（追加 describe + 埋点）
- 验证方式: vitest 该文件全绿（既有 90 用例零回归）+ 埋点
- 验证等级: Level 1

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10T07:39Z | readOutputSection 泛化（readOutputSummary 改薄封装）；readWorkerLogTail（256KB guard）；readTerminalDetail（failed: spawnFailure剥前缀??Exit Reason；nc: Questions??log尾??no output.md；done: TL;DR??headline(Summary)）；firstLine 统一剥开头 markdown 标记（AC-007 无标记保证）；render 终态分支接线 | vitest 97/97（新增 7 用例）+ 埋点 VC-007/008/009；biome 修复 2 文件格式后零告警 |
### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
