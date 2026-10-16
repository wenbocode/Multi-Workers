# TRQ-2: worker settle/phase 机对 error turn 的盲视路径（research）

type: research

## 上下文

- 项目 goal：`.agenticdoc/goal.md`（agent-team-loop 扩展；worker 超时看门狗与收敛检查点）。
- 问题预判（PM 预研，须逐条核验或推翻）：`agent_settled` 在重试耗尽后的 error turn 上同样触发（`packages/coding-agent/src/core/agent-session.ts:1081` `_runAgentPrompt` finally 无条件 `_emitAgentSettled()`），而 `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:3707-3776` 的 `agent_settled` handler 不检查最后一条 assistant 消息的 `stopReason === "error"`：
  - 首 settle 无条件发 phases[0].prompt（:3715-3723）；
  - 后续 settle 一律按「phase 完成」处理（:3729-3760），error turn 会写 "Phase N complete" 并推进 phase 机；
  - 全 phase 耗尽后走 `settleOrSelfCheck()`（:3646）→ `finishSuccess()`（:3536+），exit code 依赖 gaps 判定，write 角色 `evidence.delivered=true`（:3548-3549），可能 exit 2 但 Exit Reason 误导为 recovery gap，甚至 exit 0。

## 要求

1. 逐行核验上述预判，修正行号与结论；列出 error turn 与成功 turn 在 worker-mode 可观测面上的全部差异（agent_end/turn_end 事件里 assistant message 的 stopReason/errorMessage 字段是否可用，:3139-3153）。
2. 对三类任务形态分别给出「模型全程 500」时的端到端结局表：a) 带 phases 的任务书 b) 无 phases 的 writeless 角色（review/research）c) 无 phases 的 write 角色（coding）。每行：终端 status、exit code、output.md `## Exit Reason` 实际文本、trace.log 关键行、PM 会看到什么。
3. print mode（`pi -p`）与 sendUserMessage 的交互：error settle 后 sendUserMessage 排队的下一 phase 是否会让 print mode 继续运行；worker 进程在此路径上的退出方式（自然 exit / process.exit）。
4. idle 看门狗被「error 自旋」投毒的判定：error turn 的 turn_end/agent_end 事件是否刷新 lastActivityAt（worker-mode.ts:3045-3049），从而使持续 500 的 worker 不会命中 10 分钟 idle 墙，只能靠 60 分钟 wall 或 phase 耗尽兜底。
5. `markOutcome`（worker-mode.ts:2655）与 `recordEnd`（:3156）的 exit code→status 映射核验（0=done / 2=needs-clarification / 其他=failed）。

## 写入允许面

- 仅允许写：`.agenticdoc/mw-model-error-perception/evidence/research/spec-settle-paths-2026-10-15.md`

## 交付格式

- 唯一证据文件：`.agenticdoc/mw-model-error-perception/evidence/research/spec-settle-paths-2026-10-15.md`（只写此一个文件）
- 结构：预判核验表（逐条 confirm/refute + 行号）→ 三类形态结局表 → print mode 交互事实 → 结论→决策映射（fail-fast 应挂在哪个事件、error settle 应如何被 phase 机区分）
