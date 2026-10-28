# RQ9: 窗口上下文注入 —— 现有 PM 报人机制与 DP 选择后的变动作注入面（只核现状）

## 结论

1. PM 窗口当前只有两条**通用**注入通道，且都由 `pm/ui-bridge.ts` 收口：
   - `displaySummary`（`ui-bridge.ts:201`）：`pi.sendMessage` **不带** `triggerTurn` = 被动；空闲时只落上下文/显示，不消耗 turn。
   - `deliverPmAlert`（`ui-bridge.ts:218`）→ `pi.sendMessage(..., { triggerTurn: true })` = 唯一"唤醒 PM"通道；`deliverWorkerResult`（`:232`）只是它的别名。
2. 核心四态（`core/agent-session.ts:1436 sendCustomMessage`）：流式时 `deliverAs` 缺省走 **steer**（`:1452-1457`），`followUp` 走排队；空闲 + `triggerTurn` 走 `_runAgentPrompt`（`:1459`，新 turn）；空闲无 trigger 只 `state.messages.push` + `sessionManager.appendCustomMessageEntry`（`:1461-1469`）。
   → **显示 / 进入上下文 / 唤醒 / 排队 / 实际执行是五个不同事实**：`display:true` 只影响 TUI 渲染（`modes/interactive/interactive-mode.ts:3459`），上下文由 `convertToLlm`（`core/messages.ts:162-168`）把任意 custom 消息转成 `role:"user"`，与 `display` 无关；`excludeFromContext` 只存在于 bashExecution，custom 无此口。
3. PM 侧的 `ask_decision` 结果**不是**消息注入：它是当前 turn 内的 tool result 文本（`pm/decision-tool.ts:1877` 的 `execute` 返回 `{content:[{type:"text",text}]}`），不 `sendMessage`、不 `triggerTurn`、不排队。
4. 当前**没有**通用 DP 选择注入器。`dp7-gate-failure` 在 TS 侧只作为 `ask_decision` 的枚举值与生成 registry 出现（`decision-tool.ts:139`、`shared/decide-registry.generated.ts:827`），全扩展无任何"把某 dp 的 selection 注入窗口"的函数。
5. 已有的"注入执行体"只有两条，且都是 **Worker 侧文件→followUp steer**，不是 PM 侧通用机制：dp2 `steer-dp2.md`（生产端已退役，仅 PM 手写）、dp3 答案 steer（auto 时由 worker 自己注入）。

## 证据

### A. PM 显示/唤醒通道（全文读完 `pm/ui-bridge.ts` 5275 行；`pm/pm-orchestrator.ts` 只读相关段）

- `pm/ui-bridge.ts:201 displaySummary(pi, summary)`：`pi.sendMessage({customType:"agent-team-loop:worker-summary", content, display:true, details})`，**第二参数缺省**（无 triggerTurn）。
- `pm/ui-bridge.ts:218 deliverPmAlert(pi, text)`：同一 customType，`{triggerTurn:true}`（`:226`）；注释 `:212-217` 明确"无 triggerTurn 只入 LLM 上下文/transcript，空闲 PM 不醒；有 triggerTurn 空闲即起 turn，流式中被 steer 进当前 turn"。
- `pm/ui-bridge.ts:232 deliverWorkerResult(pi, summary)` → `deliverPmAlert`。
- 被动调用点：`pm-orchestrator.ts:412`（settle 归档写失败）、`:2281`（decision settle 写入失败）、`:2631/2633/2649/2656/2665`（/mw init 等）、`ui-bridge.ts:1459`（`makeScopedDocGateNotifier` 的 gate skip 提醒）、`ui-bridge.ts:5228`（`/mw decide` 无 UI 时把结果写进 transcript）。
- 唤醒调用点：`pm-orchestrator.ts:2220`（收敛检查点 risk=mid/high 发散告警）、`:2296/:2303`（终态 readback / 无 output.md 告警）、`:2366`（**gate 提醒** pending 超阈，conductor 判定，本循环只读 ledger）、`:2537`（`onRefusal`）、`:2562`（dispatch alarm）、`ui-bridge.ts:683`（dp1 建议与派发类型不一致）。
- 轮询：`pm-orchestrator.ts:2091 startWorkerPollLoop(...)`，`setInterval` 4s（`POLL_INTERVAL_MS`，`:102`），在 `pm-orchestrator.ts:2489` 被调用；同 tick 内顺序 = widget → 检查点唤醒 → 终态回读 → gate 提醒。

### B. 核心实现（只读函数与类型，未改 pi 核心）

- `core/extensions/types.ts:1300-1312`：`sendMessage(message, options?: {triggerTurn?, deliverAs?: "steer"|"followUp"|"nextTurn"})`；`sendUserMessage(content, options?: {deliverAs?: "steer"|"followUp"})`，注释"Always triggers a turn"。
- `core/agent-session.ts:1436-1471 sendCustomMessage`：四分支如上；`nextTurn` 进 `_pendingNextTurnMessages`（不立即入上下文）。
- `core/agent-session.ts:1480-1510 sendUserMessage` → `prompt(text,{streamingBehavior: options?.deliverAs, source:"extension"})`。
- `core/agent-session.ts:1167-1180 prompt`：流式且无 `streamingBehavior` **抛错**；否则 `followUp` → `_queueFollowUp`、`steer` → `_queueSteer`；空闲则一路走到 `:1272 _runAgentPrompt`（必然开 turn）。
- `core/agent-session.ts:1379 _queueSteer` / `:1396 _queueFollowUp`：各自 push 文本到 steering/followUp 队列 + `agent.steer/followUp`。
- `packages/agent/src/agent.ts:283 steer`（"injected after the current assistant turn finishes"）/ `:288 followUp`（"only after the agent would otherwise stop"）。
- `packages/agent/src/agent-loop.ts:167`（run 起始先取 steering）、`:259`（每个 assistant turn 结束后再取 steering，插在下一个 assistant 响应之前）、`:263-268`（agent 本要停止时才取 followUp，作为新一层 outer-loop turn）→ steer 与 followUp 的差别是**插入时机**，不是"是否执行"。
- 上下文投影：`core/messages.ts:162-168 convertToLlm` 的 `case "custom"` → `{role:"user", content}`；`display` 只被 TUI 用（`modes/interactive/interactive-mode.ts:3459 case "custom"`）。

### C. ask_decision 的实际通道（与外部消息注入不同）

- `pm/decision-tool.ts:1835-1877 registerAskDecisionTool` → `pi.registerTool({name:"ask_decision", parameters, executionMode:"sequential", execute})`；成功路径 `:1900-1922` 返回 `{content:[{type:"text",text:outcome.text}], details: outcome.payload}` —— 即**当前 turn 的 tool result**，模型在同一轮内看到；无 message/sendUserMessage、无 triggerTurn。
- 阻断路径 `:1945-1960`：同样只返回 tool result（第二次 block 带 `terminate:true` 终止 tool loop）。
- `decision_receipt`（`:1987` 起）同样只回 tool result，不注入。
- dp7 现状：`decision-tool.ts:139` 仅为枚举项；`shared/decide-registry.generated.ts:827 "dp7-gate-failure"` 仅为 registry 行；全 `agent-team-loop` 目录 grep `dp7|DP7` 无第三个命中 → **不存在通用 DP7（或任意 dp）选择注入器**。

### D. Worker 侧已有注入执行体（不是 PM 通用器）

- dp2 消费端：`worker/worker-mode.ts:3277 consumeDp2NarrowSteer(via)`（函数体 `:3277-3325`）读 `<taskDir>/steer-dp2.md`，`dp2SteerInjected` + `hasDp2ConsumedMarker` 双幂等，`:3300 pi.sendUserMessage(text,{deliverAs:"followUp"})`，成功后追加 `[dp2-consumed <runId> <ts>]` 标记（失败只写 trace，不改终态）；两个消费点：`before_agent_start`（`:3325-3328`）与 `finishSuccess`（`:4313`，命中则 return 保持 run open 让 followUp turn 执行）。
- dp2 生产端已退役：`pm/pm-orchestrator.ts:1932-1942` 注释"机器不再问 dp2、不再对答案动作；旧 `narrow` shortcut（poll loop 写 `steer-dp2.md`）已随自动调用移除"；`:1942-1943` "`decideDp2Checkpoint` remains the request/normalisation seam… **has no caller in the machine loop**"；`:2080-2090` 同一 RETIRED 说明。全 TS grep `steer-dp2` 只有 worker 侧读者与常量（`:1955 DP2_STEER_FILE`），**无写者**（PM 手写文件路径保留）。
- dp3：`worker-mode.ts:4268 pi.sendUserMessage(formatDp3AnswerSteer(actedDecision, lastAssistantText), {deliverAs:"followUp"})`（`decision.kind==="answer" && mode==="auto"` 时，D-041 采纳点即注入点）；`formatDp3AnswerSteer` 定义在 `:5765`，固定前缀 `[mw dp3-answer]` + decision_id。
- 其余 followUp 注入：`:4567` recovery self-check、`:4668/:4698` phase prompt；均属 Worker 内部，与 PM 窗口报人无关。

### E. 五者差异（对本 RQ 的核心结论表）

| 事实 | displaySummary | deliverPmAlert | ask_decision tool result | worker dp2/dp3 steer |
| --- | --- | --- | --- | --- |
| 显示 | 是（display:true → TUI custom 渲染） | 是 | 否（tool 卡片） | 是（用户消息） |
| 进入 LLM 上下文 | 空闲：是；流式：是（被 steer 排入） | 是 | 是（作为 tool result 当轮） | 是（drain 时） |
| 唤醒空闲窗口 | **否** | **是（triggerTurn）** | 否（本来就在 turn 内） | 否（窗口有自己的 run） |
| 排队 | 流式时进 steering 队列 | 流式时进 steering 队列 | 无队列 | followUp 队列 |
| 实际执行 | 只在下一个 turn | 立即（空闲）/ 当前 turn 内注入（流式） | 无需执行 | 当前 turn 结束后新开 turn |

## 残留与未验证

- **未执行任何运行实例**：模块身份、真实 TUI 渲染效果、`triggerTurn` 在真实 PM 窗口的 delivery 效果（是否真起 turn、是否被 streaming 降级为 steer）全部**未知**；本报告只给代码路径，不给实测结论。
- `displaySummary` 流式中走 `agent.steer`（`agent-session.ts:1452-1457`，deliverAs 缺省分支）是从代码读出，未用真实 provider/窗口验证其插入点。
- `followUp` 在 `before_agent_start` 阶段（`worker-mode.ts:3327`）究竟算"流式中排队"还是"空闲新 turn"，取决于该回调时刻 `isStreaming`，未实测；两者最终都会进入上下文，但 turn 边界不同。
- 未读/未核：`mw.py` 侧 gate ledger 的写者、`autopilot` 目录的 conductor 行为、真实 `.mw/*` 配置与凭证（按约束禁止读取活配置/gate/ledger）；`readGateReminders` 的实现（`autopilot/status-model.ts`）只按调用点认定为只读。
- 覆盖说明：`pm/ui-bridge.ts` 全文 1-5275 行已分段读完；`pm/pm-orchestrator.ts`（5793 行）与 `worker/worker-mode.ts`（5793 行级）只读与本 RQ 相关的完整函数段（poll loop 2080-2400、dp2 生产端注释 1932-1958、dp2 消费 3272-3330、dp3 注入 4220-4275、dp2/dp3 契约注释 4900-5060、`formatDp3AnswerSteer` 5765-5782），其余未读。

## 上下文来源

- 任务卡：`.agenticdoc/mw-dp-consolidation/workers/dpc-rq9-window-context-injection/task.md`（card_path `tasks/RQ9-window-context-injection.md`，sha256 `ab26bb5c…`）。
- 目标锚点：`.agenticdoc/goal.md:5`（PM/Worker 并行框架）。
- 代码：`packages/coding-agent/src/extensions/agent-team-loop/{pm/ui-bridge.ts,pm/pm-orchestrator.ts,pm/decision-tool.ts,worker/worker-mode.ts,shared/decide-registry.generated.ts}`；pi 核心 `packages/coding-agent/src/core/{agent-session.ts,messages.ts,extensions/types.ts}`、`packages/agent/src/{agent.ts,agent-loop.ts}`、`modes/interactive/interactive-mode.ts`。
- 未使用：RQ7/RQ8 结论、任何 ask/provider 实调、测试/build/install/commit、服务操作、凭证/活配置/gate/ledger 读取、源码写入（唯一写入为本文件）。
