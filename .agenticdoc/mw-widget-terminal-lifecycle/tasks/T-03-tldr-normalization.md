# Task T-03: TL;DR 归一化（worker 侧写入）

## 基本信息
- Stage: 2
- 代码状态: 已完成（代码+测试就绪，见执行记录）
- 验证状态: 验证通过（VC-009 写入半：agent-team-loop-output.test.ts 8/8 + 埋点；T-09 全量回归复验 121/121）
- 负责 Agent: 待定
- ac_refs: [AC-009]
- vc_refs: [VC-009]
- pattern_refs: []

## 描述
`packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`：

1. **导出 `headline(summary: string): string`**（D-005 归一化，纯函数）：
   - 取首个非空行 trim
   - 剥离开头标记（循环直至不再匹配）：`#{1,6}` + 空白、`**`、`[-*]` + 空白、`>` + 空白
   - 折叠连续空白为单空格
   - 截断 100 字符（截断加省略号，参照既有 truncLine 风格，总长 ≤100）
   - 空输入/全空行 → `(no conclusion)`
2. **`writeOutput` 增首节**：`## TL;DR\n\n${headline(opts.summary)}` 置于 `## Summary` 之前（所有 exitCode 统一；`## Summary` 节原样保留——readOutputSummary 正则兼容）
3. `worker/worker-mode.ts` deadline steer 文案追加一句：「最终回复第一行必须是单行结论（状态 + 关键产出/卡点）。」（微调，不动逻辑）

**测试**（新文件 `packages/coding-agent/test/extensions/agent-team-loop-output.test.ts`，独立 describe，不碰 agent-team-loop.test.ts）：
- headline 样本回测（来源 design-terminal-summary-quality 调研）：
  - `## (a) BLOCKING issues` → `(a) BLOCKING issues`
  - `## Task 002 执行完毕（TDD red 阶段完成）` → 剥 `## `
  - `T-03 complete. All deliverables in place, tests green.` → 原样
  - `**bold** 开头` → 剥 `**`
  - `- list item` → 剥 `- `
  - >100 字符长行 → 截断 ≤100
  - 空串/全空白 → `(no conclusion)`
- writeOutput：exitCode 0/1/2 产物首节均为 `## TL;DR` 且值为 headline；`## Summary` 节内容不变（旧正则可读）
- deadline steer 文案包含「单行结论」（L0 字符串断言）
- 输出 `[VERIFY] VC-009: tldr_len<=100, markdown_prefix=absent` 埋点行

## 输入
- 依赖文件: `worker/output-writer.ts`、`worker/worker-mode.ts`
- 依赖 Task: 无
- AC 约束:
  > AC-009: 在 worker 行状态为 done 时，widget 行 detail 为单行结论：新完成任务由 worker 侧在 output.md 写入 TL;DR（首行结论、无 markdown 标记、≤100 字符）；旧 output.md（无 TL;DR）回退取 `## Summary` 首行并剥离开头 markdown 标记（`#`/`**`/`- `）（本 Task 做写入半 + steer 文案；展示回退在 T-05）
- 设计约束:
  > D-005: TL;DR 首节 + headline 四步归一化；starter 引导（T-04）+ 归一化兜底双保险
  > spec §5 坑点: 不得破坏 readOutputSummary 的 `## Summary` 正则兼容

## 预期产出
- `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`（headline + writeOutput 首节）
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（steer 文案一句）
- `packages/coding-agent/test/extensions/agent-team-loop-output.test.ts`
- 验证方式: `node ../../node_modules/vitest/dist/cli.js --run test/extensions/agent-team-loop-output.test.ts` 全绿 + 埋点；既有 agent-team-loop.test.ts 零回归
- 验证等级: Level 1

## 约束（worker 派发适用）
- 只碰上述三个文件；禁改 agent-team-loop.test.ts / ui-bridge.ts
- 显式路径参数；[VERIFY] 埋点
- 完成后更新本文件执行记录

## 状态与证据

### 执行记录
| 轮次 | 时间 | 动作 | 结果摘要 |
|------|------|------|--------|
| 1 | 2026-09-10T15:34:41Z | output-writer.ts 导出 headline()（首个非空行 trim → 循环剥离开头标记 `#{1,6}`+空白/`**`/`[-*]`+空白/`>`+空白 → 折叠连续空白 → truncLine 总长≤100，空输入/全空行→`(no conclusion)`），writeOutput 在 `## Summary` 前统一插入首节 `## TL;DR`（所有 exitCode；Summary 原样保留）；worker-mode.ts deadline steer 文案追加「最终回复第一行必须是单行结论（状态 + 关键产出/卡点）。」；新建 test/extensions/agent-team-loop-output.test.ts（8 用例：调研样本回测/首行选取+堆叠标记剥离/100 截断边界/空回退/exitCode 0/1/2 首节+readOutputSummary 旧正则兼容/VC-009 截断与无标记前缀/steer 文案 workerModeActivate 集成断言） | 新测试 8/8 绿，输出 `[VERIFY] VC-009: tldr_len<=100, markdown_prefix=absent`；agent-team-loop.test.ts 90/90 零回归；biome 对三文件无告警，tsgo 仅报 packages/ai 既有错误（与本案无关）；未改 agent-team-loop.test.ts / ui-bridge.ts；未 commit |
### Error Fingerprint
| ID | 类型 | 文件:行 | 错误文本（原始）| 状态 |
|----|------|---------|---------------|------|

### 卡住记录
- 卡住时间: —
- 卡住原因: —
- 处置: —
