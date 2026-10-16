# Research: 模型错误不可感知问题的代码取证（spec）

## 决策问题

回答 spec §1 范围判定：确认「模型 500/连接失败 → worker 不可感知/伪成功/僵尸自旋」在当前代码中的确切机理，划定本 key 必须覆盖的代码面。

## 调研方法与出处

PM 预研直接读码（2026-10-15），关键出处：

- `packages/coding-agent/src/core/agent-session.ts:1081-1104` — `_runAgentPrompt` 的 `finally` 无条件 `_emitAgentSettled()`：重试耗尽后的 error turn 同样触发 `agent_settled`。
- `packages/coding-agent/src/core/agent-session.ts:2680-2730` — agent 级 auto-retry：`settings.retry` 默认 enabled=true、maxRetries=3、baseDelayMs=2000（`settings-manager.ts:806-822`）。
- `packages/ai/src/utils/provider-retry.ts:105-122` — provider 级重试默认 maxRetries=0；`packages/ai/src/timi-responses.ts:34` timi 路由默认 8 次。
- `packages/coding-agent/src/extensions/agent-team-loop/worker/worker-mode.ts:3707-3776` — `agent_settled` handler 不检查最后 assistant 的 `stopReason==="error"`：首 settle 无条件发 phases[0].prompt（:3715-3723）；后续 settle 一律按 phase 完成处理（:3729-3760），error turn 会写 "Phase N complete" 并推进 phase 机；全 phase 耗尽 → `settleOrSelfCheck`（:3646）→ `finishSuccess`（:3536+）。
- `worker-mode.ts:3139-3153` — agent_end 仅提取 text（lastAssistantText），丢弃 stopReason/errorMessage。
- `worker-mode.ts:3045-3049` — turn_end/agent_end 均刷新 lastActivityAt ⇒ error 自旋投毒 idle 看门狗，持续 500 的 worker 只能被 60 分钟 wall（:3462）或 phase 耗尽兜底。
- `worker-mode.ts:2655` — markOutcome：0=done / 2=needs-clarification / 其他=failed。
- `worker-mode.ts:3548-3549` — write 角色 `evidence.delivered=true` 恒真 ⇒ 模型全挂的 coding worker 终局 exit 依赖 gaps，Exit Reason 误导为 recovery gap。
- 历史事故（`.agenticdoc/_pitfalls.md`）：2026-09-22 12 个 review worker 中 4 个 `stream closed before response.completed` 空产出仍进入判读；wfg-i03 事故 worker 连续 12 次失败重派（疑似模型连接失败），PM 感知为「无限死循环、无法推进」。

## 发现

1. error turn 与成功 turn 在 worker-mode 的 settle 面上完全不可区分（不读 stopReason），是最核心缺口。
2. 模型失败的 errorMessage 全程不入 trace.log / worker.log / output.md，PM 无法归因。
3. error 自旋刷活动钟 ⇒ idle 看门狗失效，僵尸 worker 最长存活 60 分钟（wall 兜底）。
4. 带 phases 的任务书在模型全挂时 phase 机被 error settle 推进到底，终局可能 exit 0/2 且理由失真（伪成功风险）。
5. 重试本身有界（provider 级 ≤8 次 × agent 级 3 次），单次调用最坏耗时待 RQ-1 精确量化。

## 结论 → 决策映射

- 支撑 spec §1 范围：worker 侧必须（a）区分 error settle（b）fail-fast 熔断（c）[MODEL_ERR] 证据落盘；PM 侧最小侵入告警 kind（范围待用户确认）。
- 支撑 AC-001/002/003/004 的可测行为定义；阈值具体数值待 RQ-1 时序证据后修正。
