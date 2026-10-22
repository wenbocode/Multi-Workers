# SPEC RQ-2：pi 交互面能力调研（jev 决策替人的接触面清单）

- key: `mw-decision-substitution` / ds-rq2-pi-interaction-surface
- 日期: 2026-10-16
- 调研对象: pi Extension API（GC-2 不改核心），代码基线 `packages/coding-agent@0.83.0` 工作区源码
- 方法: 全文读 `packages/coding-agent/docs/extensions.md`（2988 行）+ 源码核对（`src/core/extensions/*`、`src/core/agent-session.ts`、`packages/agent/src/agent-loop.ts`）+ agent-team-loop 现有代码 + `mw-jev-provider-integration` 接入文档
- 结论速览: **确认面可完全接管（jev 可做确认者）**；**提问可用自定义工具替代（jev 答案以工具返回值回灌最安全）**；**"人已表态"实时可检测、事后从 session 文件不可分辨**；**worker 与 PM 加载同一扩展，两侧都能注入 turn**；**~5s 决策调用严禁放进每-LLM-调用的 `context` 钩子**。

---

## Q1 可用钩子清单（钩子 / 代码位置 / 能做什么 / 不能做什么）

发射点（pi 核心侧）：`packages/agent/src/agent-loop.ts` 与 `packages/coding-agent/src/core/agent-session.ts`、`src/core/extensions/runner.ts`。

| 钩子 / API | 发射位置 | 能做 | 不能做 | 频率 |
|---|---|---|---|---|
| `tool_call` | `agent-session.ts:480`（`agent.beforeToolCall`）→ `runner.ts:932` `emitToolCall`；block 落地 `agent-loop.ts:636-641` | 看 toolName+全部参数；**就地改参数**（docs/extensions.md "Mutations to event.input affect the actual tool execution"）；返回 `{block:true, reason}` 拒绝，reason 作为 error 工具结果回给 LLM（`packages/agent/src/types.ts:56-63`） | **没有显式 allow 返回值**（`extensions/types.ts:1074-1077` 只有 `block?/reason?`，放行=返回 undefined）；看不到同批并行兄弟调用的结果（docs/extensions.md tool_call 节） | 每次工具执行前 |
| `tool_result` | `agent-session.ts:501-533`（`agent.afterToolCall`）→ `runner.ts:877` `emitToolResult` | 链式改写 content/details/isError/usage（docs/extensions.md tool_result 节） | 不能回滚已执行的动作 | 每次工具执行后 |
| `input` | `agent-session.ts:1143` `emitInput` → `runner.ts:1196` | 观察原始用户输入；`transform` 改写；`handled` 整条吞掉不进 LLM（`extensions/types.ts:846-849` 三种结果）；**带 `source: "interactive"/"rpc"/"extension"`**（`extensions/types.ts:830-831`） | source **不落 session 文件**（见 Q4）；skill/template 展开前（docs/extensions.md input 节） | 每条用户输入（含扩展注入） |
| `before_agent_start` | `agent-session.ts:1233` `emitBeforeAgentStart` → `runner.ts:1081` | 注入持久 custom message（进 LLM 上下文、落 session）；链式改写本轮系统提示（`agent-session.ts:1249-1255`） | 系统提示改写**不落 session 条目**（`_systemPromptOverride` 只设 `agent.state.systemPrompt`，无 appendMessage） | 每条 user prompt 一次（非每 LLM 调用） |
| `context` | `sdk.ts:351-355` `transformContext` → `runner.ts:984` `emitContext` | 每 LLM 调用前拿到深拷贝消息列表，可增删改（docs/extensions.md context 节） | 改动不持久化到 session；**每调用都跑**（Q6 最差挂点） | 每次 LLM 调用 |
| `before_provider_headers` / `before_provider_request` / `after_provider_response` | `runner.ts:1014/1049` + `sdk.ts:334-345` | 改 HTTP 头；替换整个 provider payload（含系统指令）；看响应状态 | payload 改写不反映进 `ctx.getSystemPrompt()`（docs/extensions.md） | 每次 provider 请求 |
| `turn_start` / `turn_end` | `agent-session.ts:733-747` | 每轮（一次 LLM 响应+工具批）通知；turn_end 带 message+toolResults | 不能改消息（turn_end 只读） | 每轮 |
| `message_start/update/end` | `agent-session.ts:749-767` | message_end 可整体替换同 role 消息（docs/extensions.md） | 替换必须保 role | 每条消息 |
| `tool_execution_start/update/end` | `agent-session.ts:781-805` | 观察执行生命周期、流式部分结果 | 不能阻止执行（阻止走 tool_call） | 每工具执行 |
| `session_before_switch/fork/compact/tree` | `agent-session.ts:1818-1820, 2080-2082`（compact）；docs session 事件节 | 可 `cancel:true` 取消会话级操作；可自定义压缩摘要 | — | 按操作 |
| `user_bash` | `runner.ts:966` `emitUserBash` | 人手敲 `!`/`!!` 命令可换后端或直接返回结果（`extensions/types.ts:855-863`） | 只管人手敲的 bash，不涉 agent 工具调用 | 人用 `!` 时 |
| `project_trust` | docs/extensions.md project_trust 节 | 接管信任决定 `{trusted:"yes"/"no"}` | 仅启动期、仅用户级/CLI 扩展参与 | 启动 |
| `pi.registerTool` | `ui-bridge.ts:1266`、`rag/tools.ts:246+`、`worker-file-tool.ts:132` 等在用 | 注册 LLM 可调工具；可覆盖内置工具同名（docs/extensions.md Overriding Built-in Tools）；`executionMode:"sequential"` 可串行化（`extensions/types.ts:480`，示例 `examples/extensions/question.ts:53`） | 工具 execute 内不能调 `ctx.reload()` 等 command-only 能力 | 注册即生效 |
| `pi.sendMessage({triggerTurn})` | `agent-session.ts:1430-1473` `sendCustomMessage` | 空闲时立即开新 turn（`:1458-1459`）；流式中 steer/followUp 排队；`nextTurn` 攒到下条用户消息一起进上下文（`:1226-1231, :1450-1451`） | custom message 有 customType 身份，**不像人** | 按需 |
| `pi.sendUserMessage` | `agent-session.ts:1480-1511` | 发**真 user 消息**（TUI 与 session 文件里都像人打的字），必触发 turn；流式中须 `deliverAs:"steer"/"followUp"`（`:1509` 传 `source:"extension"` 给 input 事件，**不落盘**） | 空闲时不能选不触发（总是触发） | 按需 |
| `ctx.ui.confirm/select/input/notify` | docs/extensions.md Custom UI 节 | TUI/RPC 弹窗问人并阻塞等答案；print 模式 `ctx.hasUI=false` 必须守卫（ctx.hasUI 语义见 docs；示例 `examples/extensions/question.ts:59-61`） | print 模式（worker/`-p`）不可用 | 按需 |
| `pi.appendEntry` | docs/extensions.md State Management 节 | 落 session 文件的 custom entry，**不进 LLM 上下文**（审计/状态持久化用） | 模型看不见 | 按需 |

## Q2 权限与确认面：能短路，因为门本来就是扩展级的

- **pi 核心没有内置的"破坏性操作确认"**：`src/modes/**` 全目录 grep `.confirm(|.select(|.input(` 零命中；`src/core/tools/bash.ts`、`write.ts` 无 confirm/approval/permission 逻辑（bash.ts 仅 `:418-423` worker heartbeat）。pi 只在启动期有 `project_trust`。
- 破坏性确认的**唯一实现层就是扩展的 `tool_call` 钩子**，官方示例即此模式：`examples/extensions/permission-gate.ts:9-27`（危险 bash 弹 confirm，拒绝返回 `{block:true, reason:"Blocked by user"}`）；`examples/extensions/confirm-destructive.ts`（会话级操作）。
- **jev 可在确认前完整接管**：`tool_call` 事件里 `event.input` 是完整工具参数（docs/extensions.md tool_call 节），扩展可在此同步调 jev（spawnSync `mw.py decide run`，即 DP-1 现成模式，`pm/ui-bridge.ts:232-251` + triage-client），然后：
  - 拒绝 → `return {block:true, reason:"jev: <理由>"}`；reason 经 `agent-loop.ts:636-641` 变成 error 工具结果回给 LLM，模型当场看到拒绝理由并自我修正；
  - 放行 → `return undefined`（无显式 allow 值，`extensions/types.ts:1074-1077`），或顺手 `event.input` 就地改参（如给命令加保护前缀）。
- **判据（DS-3）：可介入。** 结论：确认门 = `tool_call` 钩子 = 扩展代码，jev 可在"人本来会看到确认框的位置"做出 allow/deny，且 deny 附理由可审计（session 文件里有该 error toolResult）。
- 风险：①"放行"是消极语义（无返回），审计行要扩展自己写（trace/log/appendEntry）；②并行工具模式下 `tool_call` 串行 preflight（docs），一条 5s 决策会推迟同批所有工具的 preflight，必须按 toolName+危险模式门控；③worker 会话同样吃这个钩子，需按 `PI_WORKER_TASK`（`worker/worker-mode.ts:2557`）区分策略。

## Q3 用 jev 替代"提问"：三种回灌身份的对比

现状机制：
- **裸 pi**：模型在助手文本里写问题→结束 turn→等人打字（input 事件）。无内置 ask 工具。
- **扩展 ask 工具**：`examples/extensions/question.ts:45-61`、`qna.ts`——注册 `question` 工具，execute 里 `ctx.ui` 弹窗**阻塞**等人选，答案作为工具返回值回上下文。print 模式返回错误（question.ts:59-61）。
- **worker**：终端态 `needs-clarification`（`worker/worker-mode.ts:2678-2682`，exit 2），问题写进 output.md `## Questions`（`worker/output-writer.ts:525-527`），PM 读回呈报（`pm/ui-bridge.ts:666-685`）。

jev 替代方案 = 注册 `ask_decision` 工具（execute 内 spawnSync `mw.py decide run`，stdin 传 state+questions，复用 triage-client.ts:169 的调用形状，见 jev 文档 §1②），答案以不同身份回灌的三条路：

| 身份 | 机制 | 可见性/审计 | 风险 |
|---|---|---|---|
| **A. 工具返回值（推荐）** | execute 返回 `{content:[{type:"text",text:jev 答案}]}` | session 文件记 `role:"toolResult", toolName:"ask_decision"`（`docs/session-format.md:210` 形状）；TUI 工具行可见；天然带调用参数=问题原文，**全链路可审计** | 最低。模型可能把工具输出当"参考"而非"裁定"，需 `promptGuidelines`（registerTool 支持，docs/extensions.md Custom Tools 节）写明"该答案视作最终决策"；答案属 toolResult，不会触发人权（Q4 判人时不算人话） |
| **B. 伪造 user 消息** | `pi.sendUserMessage(jev答案, {deliverAs:"followUp"})`（`agent-session.ts:1480`） | session 文件里是普通 `{role:"user"}`，**与人打的字不可分辨**（`:1216-1224` 构造时不留 source；Q4） | 最高。污染"人说的话"这一最高权威信道：jev 答案会被后续任何"人已表态"检测误判为人意（违反"人 override 优先于 jev"），审计断链。**禁止用于 jev 答案**（mw 自身的注入都带 `[mw ...]` 前缀标记，`worker-mode.ts:3770-3775`，正是为了缓解这一点） |
| **C. 系统注入** | `sendMessage` custom message（`customType` 标识，`agent-session.ts:1430-1449`；session 条目 `custom_message`，`docs/session-format.md:273-283`）或 `before_agent_start` 改系统提示（`agent-session.ts:1249-1255`，**不落 session**） | custom message：模型可见、transcript 可见（display:true 时）、带 customType 身份，可审计；系统提示改写：**零痕迹**（不落 session、不出现在消息流） | 中。custom message 权威性弱于工具结果与 user（模型可忽略）；系统提示注入无法事后审计单次决策，只适合放长期政策（"ask_decision 的答案按最终裁定执行"），不适合逐案回灌 |

**结论**：jev 答案以 **A（工具返回值）** 回最安全：显式身份、全审计、不污染人权信道；配 C-变体（系统提示里写一条长期政策）解决权威性。B 明确排除。

## Q4 检测"人已表态"（jev 不得推翻人）

- **实时检测：可行。** `input` 事件带 `source`（`extensions/types.ts:830-831`）：`"interactive"`（人打字）、`"rpc"`（API 客户端，通常也是人驱动）、`"extension"`（`pi.sendUserMessage` 注入，`agent-session.ts:1509`）。扩展 `pi.on("input")` 里 `source!=="extension"` 即人开口，内存记账 + `pi.appendEntry`（不进 LLM 上下文、落 session 可跨 reload 恢复）持久化。
- **事后从 session 文件检测：不可行（结构上不可分辨）。** user 条目落盘形状固定 `{"role":"user","content":...,"timestamp"}`（`agent-session.ts:1216-1224`；`docs/session-format.md:75-80、:208`），无 source 字段；`message_start/end` 事件也只带 message（`extensions/types.ts:746-763`）。
- **可行的替代做法**：
  1. 扩展对自己发出的每条 user 注入打机器标记（agent-team-loop 已这么做：`[mw deadline]`、`[mw recovery self-check]`，`worker-mode.ts:3460-3464、3770-3775`），事后扫描时"不带已知机器前缀的 user 消息≈人话"。这是启发式（未验证覆盖所有历史注入路径，标 **未验证**：缺"枚举全部 sendUserMessage/sendMessage 调用点并核对前缀"的证据）。
  2. 权威判定放会话外文件：PM/worker 对关键决策把"是否有人已拍板"记入 task.md/_index 等人可写文件（现状：人通过 `/mw ack`、task.md 头部直接表态），jev 决策器读这些文件做人意短路——人改文件 = 人表态，文件 mtime/hash 可比对。
- 结论：**单会话内实时可判定；跨 session/事后只能靠注入打标 + 会话外状态文件**。jev 决策器必须先查"人已表态"再作答，优先级实现为人意文件/实时记账 > jev。

## Q5 worker 侧能力

- **同一套扩展**：worker 模式由 `PI_WORKER_TASK` 环境变量在同一扩展内切换（`worker/worker-mode.ts:2557`），工具白名单 `TOOL_ALLOWLISTS`（`worker-mode.ts:96`）经 `before_agent_start` 钩子里的 `applyRagTools` → `pi.setActiveTools` 每轮重算（`worker-mode.ts:2849-2851`、`rag/tools.ts:400-406`）。
- **能调扩展注册的工具**：`worker_file`（`worker/worker-file-tool.ts:132`）、RAG 工具（`rag/tools.ts:246+`）都在 worker 进程注册；新增 `ask_jev` 类工具只要进对应 type 白名单即可被 worker 调用。
- **能触发注入**：worker 代码已在用 `pi.sendUserMessage`：checkpoint 自评 `deliverAs:"followUp"`（`worker-mode.ts:3429-3442`）、deadline steer `deliverAs:"steer"`（`:3458-3465`）、恢复自检补一轮（`:3765-3775`）。`sendMessage({triggerTurn})` 空闲开新 turn 的能力同样可用（print 模式下 `agent-session.ts:1458-1459` 走 `_runAgentPrompt`）。注意：worker 跑在 print 模式（`worker-mode.ts:3545` "after pi -p <task_content>"），`ctx.hasUI=false`，一切 `ctx.ui` 弹窗问人不可用——这正好迫使 worker 的"问"走 jev 工具而不是 UI。
- **needs-clarification 判定链与可插入点**：`agent_settled` 处理器（`worker-mode.ts:3824`）→ `finishSuccess` 判产物证据与恢复缺口 → `exitCode 0|2`（`:3664`）→ `markOutcome` 把 exit 2 映射成 `needs-clarification`（`:2678-2682`，`runState.status` 赋值在 `:2681`），Python launcher 侧同名映射（`_exit_to_status`，`:2679` 注释）。**判定前插一次 jev 决策调用完全可行**：该点就是扩展同步代码（现已在此 spawnSync/写文件），可把 `## Questions`/缺口摘要发 jev，拿到答案后按 `:3765-3775` 现成模式 `sendUserMessage followUp` 补一轮让 worker 消化答案。
- 风险：①设计红线——"给无产物 run 补 turn 会把 no-product 信号变开环"（`worker-mode.ts:3745-3756` 注释 T-13/D-015），jev 补轮必须只对"有产物但有问题"的 run 开；②凭据政策：现契约写明"决策由 PM 进程发起，Worker 侧不需要 key"（jev 文档 §3），worker 直连 jev 需要走同样的本地 Python 通道（auth.json 读盘，env 隔离不阻挡，技术上可行但属政策变更）；③每 worker 会话多 ~5s（预算内，见 Q6）。

## Q6 每-turn 钩子与成本（~5s 同步决策放哪）

每 LLM 调用/每 turn 必跑（会拖慢所有会话）：
- `context`：**每 LLM 调用**串行跑（`sdk.ts:351-355` transformContext → `runner.ts:984`），决策放这里=每次模型调用都 +5s，**最差挂点，禁止**。
- `before_provider_headers/request`、`after_provider_response`：每 provider 请求（docs/extensions.md），同上禁放。
- `turn_start/turn_end`、`message_start/update/end`、`tool_execution_*`：每轮/每消息/每工具，均高频，不宜放无条件决策。

按需触发（安全）：
- `tool_call`：仅工具执行时；配 toolName+危险模式门控后=只对真正要确认的调用付 5s（Q2 确认面方案）。同批并行工具的 preflight 会被串行推迟（docs/extensions.md），门控把频率压到极低即可接受。
- 自定义工具 execute（`ask_jev`）：模型主动调用才付费，**零常态开销**，Q3 推荐方案。
- `input` / `before_agent_start`：每条用户消息一次；若在 PM 窗口做"派发前 triage"即现状 DP-1（`ui-bridge.ts:232-251`，spawnSync 20s 上限、fail-soft `available=false` 不阻断，jev 文档 §2.4），频率=每次派发，可接受。
- 会话级事件（session_before_* 等）：按操作。

放置结论：**常态路径零钩子开销**；决策调用只出现在 (a) `ask_jev` 工具被调用、(b) `tool_call` 命中危险模式门控、(c) PM 派发点三处，全部按需。实测 jev 延迟 ≈5.1s/次（jev 文档 §4.2 `latency_ms≈5100`），worker 墙钟预算（默认 60m）内可忽略；PM 窗口用户可感知但被 20s 超时上限兜底（triage-client 模式）。

## 三接触面的可行形态

### PM 侧（PM 主窗口，TUI）
- **能替代到什么程度**：中高。派发类型/风险分诊已替代（DP-1，`ui-bridge.ts:216-251` + `pm-orchestrator.ts:619` 争议告警，锚点见 jev 文档 §2.3）；PM"想问人"的场景（歧义、分拆判断、验收标准）可由 `ask_decision` 工具替代大部分中低风险提问；**人的最终拍板/验收（ack、lgtm 类）不可替代**——那是 Q4 的人意权威本身。
- **实现位置**：`pm/ui-bridge.ts` registerTool 区（`:1266` 起）；决策通道复用 triage-client spawnSync + `.mw/decide.json` 门控 + `triage-decisions.jsonl` 证据行；PM 主动唤醒已有通道 `deliverPmAlert`（`ui-bridge.ts:198-210`，triggerTurn）用于"jev 不可用/高争议"升级人。
- **风险**：PM 提示词必须教它"先 ask_decision 再问人"，否则它会绕过工具直接问（提示级约束，非硬门）；派发路径上每决策 +5s（上限 20s fail-soft）；争议仅告警不改派的现行红线（jev 文档 §2.4）若要改成"按 jev 执行"需新决策点与门控。

### worker 侧（print 模式独立进程）
- **能替代到什么程度**：中。worker 的 `needs-clarification`/`## Questions` 在判定前插入 jev（`worker-mode.ts:3664` 之前）+ followUp 补轮，可替代"worker 卡住甩人"里的中低风险问题；`ask_jev` 进白名单后 worker 可随问随答；无产物退出（AC-006）与高危操作不可替代。
- **实现位置**：`worker/worker-mode.ts` agent_settled 判定段（`:3824` 起）+ `TOOL_ALLOWLISTS`（`:96`）加 `ask_jev`；注入复用 `:3765-3775` followUp 模式。
- **风险**：print 模式无人 UI（天然隔离，问=jev 或终态）；"补轮变开环"红线（T-13，`:3745-3756`）限定只对有产物 run；worker 发起 jev 调用需政策放行（现契约归 PM，jev 文档 §3）；每 worker 多 5s 在预算内。

### pi 确认面（tool_call 门，PM 与 worker 通用）
- **能替代到什么程度**：**完全可替代确认动作本身**（这层门本来就是扩展代码，核心无内置确认，Q2）。jev 可对 bash 危险命令/write-edit 目标做 allow/deny 并附理由；人的 override 走 Q4 的实时 input 记账与会话外文件，人已表态则 jev 让位。
- **实现位置**：新扩展或 agent-team-loop 内 `pi.on("tool_call")`（发射点 `agent-session.ts:480-493`；block 语义 `agent-loop.ts:636-641`、`packages/agent/src/types.ts:56-63`）；deny 理由即 reason 字符串，随 error toolResult 落 session 可审计。
- **风险**：①无显式 allow 值，"jev 放行了"必须扩展自记审计行（trace/appendEntry），否则放行零痕迹；②必须按 toolName+模式门控，否则并行批 preflight 被逐个拖 5s；③worker 与 PM 共用钩子，需按 `PI_WORKER_TASK`（`worker-mode.ts:2557`）分策略；④`confidence_source!="api"` 的自报置信度不得做阈值门控（jev 文档 §2.2 P0 硬规则）。

## 残留与未验证

- **未验证**：事后从 session 文件识别人话的"机器前缀枚举"启发式——未枚举 agent-team-loop 全部 `sendUserMessage`/`sendMessage` 调用点核对前缀覆盖；若要用此启发式需补一次全调用点清点。
- **未验证**：jev 文档 §5.3 自认的三条缺口（真实 llmproxy 回喂形状、TS spawn 真函数无直测、失败无可读 detail）沿用为本文前提，未复核。
- **未验证**：`tool_call` 钩子短路链路在 print 模式（worker）会话未实跑验证（源码核对通过；建议 DS-3 落地时配一条 suite 冒烟）。
- RPC 模式 `source:"rpc"` 归类为"人"是基于 docs 语义（`extensions/types.ts:830-831`），多 worker 场景下 rpc 客户端若为自动化脚本则该假设不成立——部署时需约定 rpc 仅人用。
