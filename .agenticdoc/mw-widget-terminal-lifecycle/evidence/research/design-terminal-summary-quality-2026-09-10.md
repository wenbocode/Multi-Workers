# Research: 终态摘要质量与 TL;DR 注入点取证（design）

> 日期：2026-09-10
> 支撑 design D-004/D-005。

## 决策问题

- done 行单行结论的产出方式：worker 侧归一化还是 widget 侧清洗，注入点在哪
- failed/needs-clarification 行 detail 的取源与回退链
- 归一化规则的量化边界

## 调研方法与出处

- 样本取证（现有 output.md `## Summary` 首行实测）：
  - `.agenticdoc/goal-autopilot/workers/t03-roadmap/output.md`：`T-03 complete. All deliverables in place, tests green.`（合格——正是想要的单行结论）
  - `.agenticdoc/goal-autopilot/workers/ga-spec-design-review-2/output.md`：`## (a) BLOCKING issues`（markdown 标题混入）
  - OverCode 现场（用户 2026-09-10 反馈原文）：`## Task 002 执行完毕（TDD red 阶段完成）`、`任务完成。最终汇报：`、`Worker timed out waiting for agent_settled.`
- 读 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts`（buildSummary 507-512 行、timeoutExit、steerAtMs）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/worker/output-writer.ts`（writeOutput 节顺序）
- 读 `packages/coding-agent/src/extensions/agent-team-loop/pm/ui-bridge.ts`（readOutputSummary 204-210 行正则、readSpawnFailure 64KB guard）
- 读 `packages/multi-workers/launcher.py`（_starter_prompt 190-200 行——跨 CLI 唯一指令注入点）

## 发现

1. **Summary 首行质量随模型波动**：buildSummary = lastAssistantText 原文 + tools 行（worker-mode.ts:507-512）。首行可能是合格结论（t03）、markdown 标题（review-2）、纯前导句（`任务完成。最终汇报：`）。无法靠单一来源保证质量。
2. **_starter_prompt 是唯一跨 CLI 注入点**：pi/claude/codex 的 worker 都收到同一段 ASCII starter（launcher.py:190-200）。deadline steer 只在预算尾段触发（steerAtMs），正常完成的任务不经过；phase prompt 是任务作者写的，不受框架控制。→ 行为引导放 starter，归一化兜底放 worker 侧 writeOutput。
3. **writeOutput 增节不破坏旧读**：readOutputSummary 的正则只锚定 `## Summary` 节（ui-bridge.ts:204-210）；新增 `## TL;DR` 首节不影响任何既有消费方（readOutputBody 读全文投递，天然兼容）。
4. **归一化规则可机械判定**：首个非空行 → 剥离开头 `#{1,6} `、`**`、`[-*] `、`> ` 标记 → 折叠空白 → 截断 100 字符。样本回测：`## (a) BLOCKING issues` → `(a) BLOCKING issues`（信息保留）；`## Task 002 执行完毕…` → `Task 002 执行完毕…`；纯前导句 `任务完成。最终汇报：` 无法机器识别为「无信息」（诚实保留，靠 starter 引导改善源头）。
5. **failed 行卡点信息已在 Exit Reason**：timeoutExit 写 `${kind} timeout: ${detail}（checkpoint: risk/reads/writes/phases）`（worker-mode.ts），一行内含状态与证据；spawn 失败行已有 readSpawnFailure + 剥前缀逻辑（ui-bridge.ts 现状）。两者都不依赖模型输出质量。
6. **needs-clarification 回退链**：pi 侧无 exit 2 产出者（spec note 发现 5），`## Questions` 现状不可达；claude/codex 无 output.md。回退：Questions 首行 → worker.log 尾条非空行（复用 readSpawnFailure 的 size-guard 模式，上限 256KB——真实运行日志可达 MB 级，只在小文件时读）→ `no output.md` 提示。
7. **widget 行宽预算 110 字符（WATCH_LINE_MAX）**：所有 detail 截断沿用 trunc()，与现状一致。

## 结论 → 决策映射

- 发现 1+2 → D-005：starter prompt 加「最终回复第一行 = 单行结论（状态 + 关键产出/卡点）」指令 + writeOutput 侧 headline() 归一化双保险
- 发现 3 → D-005：TL;DR 作为 output.md 首节追加，不改 Summary 节
- 发现 4 → D-005：归一化规则四步（首非空行/剥标记/折叠空白/截断 100）
- 发现 5 → D-004：failed detail = spawnFailure ?? Exit Reason 首行
- 发现 6 → D-004：nc detail = Questions ?? worker.log 尾行(≤256KB) ?? no-output 提示
- 发现 7 → D-004：detail 统一 trunc 110
