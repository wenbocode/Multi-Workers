# D4 设计调研：`ask_decision` 工具注册 + `tool_call` 钩子拦截（2026-10-19）

- 任务：`.agenticdoc/mw-decision-substitution/workers/ds-d4-ask-tool-hook/task.md`（卡片 `tasks/D4-ask-tool-hook.md`，sha256 `4aabf026…`）
- 角色：type: research。只读调研；未修改任何源码/配置；未做 git 操作。
- 方法：逐条核对卡片锚点在当前工作树的实际位置（卡片个别路径有出入处已在正文注明实际 `path:line`），先落骨架后补全；全文行号均为本日工作树实测。
- 术语：`ask_decision` = spec §5.3 的决策调用工具；dp 级拦截 = 扩展 `tool_call` 钩子按 decision-cfg 阻断受门控动作。

## Q1 工具注册 API（RQ-1）

### 1.1 注册入口与 ToolDefinition

- 注册 API：`pi.registerTool(tool)`，签名 `registerTool<TParams extends TSchema, TDetails, TState>(tool: ToolDefinition<...>): void`（`packages/coding-agent/src/core/extensions/types.ts:1246-1251`；`ExtensionAPI` 接口起于 `types.ts:1196`）。
- `ToolDefinition` 关键字段（`packages/coding-agent/src/core/extensions/types.ts:450-509`）：
  - `name` / `label` / `description`（给 LLM 的工具描述）；
  - `promptSnippet?`（默认系统提示 Available tools 一行，缺省时自定义工具不进该节）、`promptGuidelines?`（追加到系统提示 Guidelines 的要点，`worker_file` 用它注入使用契约，`worker-file-tool.ts:139-145`）；
  - `parameters: TParams`（TypeBox schema；参数校验由 loop 的 `validateToolArguments` 做，`packages/agent/src/agent-loop.ts:624`）；
  - `prepareArguments?`（schema 校验前的参数预处理 shim，`types.ts:475-476`）；
  - `executionMode?`（`"sequential" | "parallel"`，`types.ts:478-485`；`ask_decision` 应为 `"sequential"`——它改变门控状态，不允许与被门控工具并发）；
  - `execute(toolCallId, params, signal, onUpdate, ctx): Promise<AgentToolResult<TDetails>>`（`types.ts:502-508`）。
- 返回形状：`AgentToolResult { content: (TextContent|ImageContent)[]; details; usage?; addedToolNames?; terminate? }`——**没有 `isError` 字段**（`packages/agent/src/types.ts:355-368`）。失败的唯一表达是 `execute` 抛 `Error`：loop 捕获后 `createErrorToolResult(error.message)` + `isError:true`（`packages/agent/src/agent-loop.ts:694-702`），只有这条路径能让 `tool_execution_end.isError=true`、进而出现 `[TOOL_ERR]`（`worker-file-tool.ts:20-27` 的既有结论，实测成立）。

### 1.2 可直接照抄的最小骨架（以 `worker-file-tool.ts:130-152` 为模板）

```ts
import { Type } from "typebox";
import type { ExtensionAPI } from "../../../core/extensions/types.ts";

export const ASK_DECISION_TOOL = "ask_decision";

/** TS 侧只持 dp id 字符串常量（spec §5.2）；集合 ⊆ Python DP_REGISTRY，用 L0 测试锁死。 */
export const ASK_DECISION_DPS = [
  "dp12-destructive",
  "dp19-foreign-write",
] as const;

export function registerAskDecisionTool(pi: ExtensionAPI, projectDir: string): void {
  pi.registerTool({
    name: ASK_DECISION_TOOL,
    label: ASK_DECISION_TOOL,
    description:
      "Ask the external decision service for a human-style decision on a gated decision point. " +
      "Returns a single-line JSON payload. available=false means UNAVAILABLE: do NOT guess, do NOT proceed.",
    executionMode: "sequential",
    parameters: Type.Object(
      {
        dp: Type.Union(ASK_DECISION_DPS.map((id) => Type.Literal(id)), {
          description: "Registered decision point id (unknown ids are rejected, exit 2 upstream)",
        }),
        trigger: Type.String({ minLength: 1, maxLength: 256, description: "trigger_id, e.g. <task_key>#ckpt3" }),
        note: Type.Optional(Type.String({ maxLength: 800, description: "Short L0/L1 context summary (no secrets/absolute paths)" })),
      },
      { additionalProperties: false },
    ),
    execute: async (_toolCallId, params) => {
      const r = await runAskDecision(projectDir, params); // 见 Q6：异步 spawn + 硬超时
      return { content: [{ type: "text", text: renderDecisionPayload(r) }], details: {} };
    },
  });
}
```

要点：schema `default` 不被 `Value.Convert` 应用，缺省值要在 `execute` 里落（`worker-file-tool.ts:19-27, 160` 既有经验）；错误返回走 `throw new Error(...)`（`worker-file-tool.ts:164`）。

### 1.3 可见性的三层机制与 PM/worker 差异

注册 ≠ 可见。LLM 能否看到工具由三层决定：

1. **模式分支（进程内是否存在）**：`agent-team-loop/index.ts:72-75` 以 `PI_WORKER_TASK` 分叉——设了走 `workerModeActivate(pi)`，否则 `pmActivate(pi)`。只在 worker 分支里 `registerTool`，PM 会话里该工具根本不存在；这是最粗的一层开关。
2. **会话级 registry 允许/拒绝**：`AgentSessionConfig.allowedToolNames? / excludedToolNames?`（`packages/coding-agent/src/core/agent-session.ts:213-216`；SDK 侧等价入口 `tools?: string[]` / `noTools?`，`packages/coding-agent/src/core/sdk.ts:55-70`）。registry 过滤在 `_refreshToolRegistry`（`agent-session.ts:2460-2466`：`!allowedToolNames || allowedToolNames.has(name)`）。
3. **每轮 active 集**：`setActiveToolsByName`（`agent-session.ts:928-941`，"Only tools in the registry can be enabled. Unknown tool names are ignored"）← `pi.setActiveTools`（`types.ts:1340`，绑定 `agent-session.ts:2400`）。worker 运行时在每次 `before_agent_start` 里 `applyRagTools(pi, rt, type)` 重算并 `setActiveTools(activeToolsForType(type) ∪ rag 子集)`（`worker-mode.ts:2848-2856`；`rag/tools.ts:400-414`）。注册了但不在 active 集的工具对 LLM 不可见。

既有范例：`mw_run_detached` 在 PM/worker 两条 activate 路径都注册（"The allowlist gate above decides visibility"，`worker-mode.ts:2821-2826`）；`worker_file` 只对无 write/edit 的角色注册（`worker-mode.ts:2827-2832`）。

**`ask_decision` 建议**：只在 worker 分支注册（worker 是 dp 门控的主要承载，spec §5.3 “worker 侧：同一扩展”）；PM 侧的决策发生在派发点（dp1 旁路 triage 已是同步调用 `pm/ui-bridge.ts:244`，dp2 走 checkpoint 升级），不需要 LLM 主动工具。若未来 PM 也要，按 `registerRunDetachedTool` 的“两边注册、白名单控可见”模式加，不改结构。

## Q2 工具返回值契约（RQ-2）

### 2.1 入参

- `dp`：字面量枚举，来源是 TS 常量数组，且“TS 常量 ⊆ 注册表 id 集合”由测试断言锁死（spec §5.2，`spec.md:122-131`）；未注册 id 一律拒绝，Python 侧 `mw decide run --dp <未知>` exit 2。
- `trigger`：`trigger_id` 字符串（dp2 语境为 `<task_key>#ckpt<N>`，spec §6.1 `spec.md:172`）；工具不猜，让模型从任务上下文抄。
- `note`：可选，≤800 B 的 L0/L1 摘要（spec §5.4 三级敏感度：L2 凭据/用户原话/绝对路径/代码永不外发，`spec.md:158`）。
- `question`（可选单题 id）：问题集归 Python 注册表所有（spec §5.2 “含问题集与输入构造”），TS 不自造题；省略 = 全题。Python 每请求 `max_questions=8`（`packages/multi-workers/decision.py:14, 243` 附近，D-004 预算）。

### 2.2 返回值（工具文本内容 = 单行 JSON + 固定指令行）

Python 合同（`decision.py`）：`DecisionClient.decide` 返回 `BackendOutcome { available, reason, retryable, answers, latency_ms, detail }`（`decision.py:149-161`），`reason` 只取冻结值集（如 `entry-unavailable`，`decision.py:77,120` 附近），`confidence_source` 随响应传播且 `model-self-report` 不得冒充 `api`（`decision.py:21-23`）。TS 侧映射为：

- 可用：`{"available":true,"decision_id":"dp12-destructive:<trigger>","dp":"dp12-destructive","mode":"auto","acted":true,"answers":{"action":{"value":"block","confidence":0.83}},"confidence_source":"api","latency_ms":1420}`
  - `decision_id = "<dp>:<trigger_id>"`（spec §6.1，`spec.md:172`）；`mode` ∈ `auto|suggest` 来自 decision-cfg 行（`spec.md:117`）；`acted=true` 仅当 `mode=auto`（spec §5.1：“suggest = 只落档案 + 展示建议，不执行，行为等价于未开启但对人可见”，`spec.md:118`）。
- 不可用：`{"available":false,"unavailable":"timeout|upstream-error|bad-response|disabled|input-incomplete","action":"blocked-ask-human","dp":"...","trigger":"..."}`
  - 紧跟的第二行固定指令文本：`UNAVAILABLE(<reason>) — do NOT guess, do NOT proceed with the gated action. Report "blocked on decision <dp>" and wait for a human.`

### 2.3 返回值如何进对话上下文

`execute` 的 `content` → `AgentToolResult` → `createToolResultMessage` 变成 `role:"toolResult"`、`toolCallId` 配对、`isError` 随 finalized 带出（`packages/agent/src/agent-loop.ts:773-789`），`message_start/message_end` 落入会话（`:791-794`），下一次 LLM 调用时作为该 toolCall 的 tool 结果原文进入 provider payload（`convertToLlm` 边界转换，`agent-loop.ts:595-610` 附近）。即：**模型看到的就是我们 `content[0].text` 的逐字文本**——所以契约必须是确定性的单行 JSON（≤2000 B canonical，spec §5.4 `spec.md:157`）+ 固定指令行，不做自然语言改写。

### 2.4 如何避免模型把 `unavailable` 当成“可以自己猜”

四道独立防线（缺一不构成充分防御，全部落位才算闭环）：

1. **载荷自述**：`available:false` 永远携带 `action:"blocked-ask-human"` 和禁止猜测的指令行（§2.2）；`disabled` 另加一句 “disabled ≠ approval; 决策点未开启不等于放行，动作仍受其常规工具权限约束”（见 Q6 路径 4）。
2. **系统提示**：`promptGuidelines` 写明 “available=false 时唯一合法行为是上报 blocked 并停止”（Q1 骨架可扩展）。
3. **门控闭环（硬保证）**：即使模型猜了并重试被门控工具，`tool_call` 钩子查“本进程内/档案内的有效授权”（Q3 §3.4）仍无授权 → 继续拦截。**猜测永远解不开门**，这是与 1/2（纯提示级）的本质区别。
4. **审计可见**：每次 unavailable 落 trace 行（Q6），review 报表里能看到模型是否反复试探（spec §7.1）。

## Q3 钩子拦截（RQ-3）

### 3.1 处理器形状与调用链

- 订阅：`pi.on("tool_call", handler)`，`ExtensionHandler<ToolCallEvent, ToolCallEventResult>`（`types.ts:1239`）。自定义工具事件为 `CustomToolCallEvent { type:"tool_call", toolName:string, toolCallId, input:Record<string,unknown> }`（`types.ts:896-899`，联合类型 `types.ts:902-921`）。
- 返回值：`ToolCallEventResult { block?: boolean; reason?: string }`（`types.ts:1074-1078`）；返回 `undefined` = 放行。`event.input` 可原地修改以改参（`types.ts:904-906`），本设计不用。
- 调用点：`AgentSession._installAgentToolHooks` 把 `agent.beforeToolCall` 接到 `runner.emitToolCall(...)`（`packages/coding-agent/src/core/agent-session.ts:468-486`；`emitToolCall` 在 `:480`，即卡片锚点）。每次工具执行前、参数校验后触发（`packages/agent/src/agent-loop.ts:622-634`）。
- 聚合语义：`emitToolCall` 按扩展注册顺序跑全部 handler，**第一个 `{block:true}` 立即短路返回**，后续 handler 不再执行；非阻断结果被最后一个非空返回覆盖（`packages/coding-agent/src/core/extensions/runner.ts:932-951`）。含义：多守卫共存（bash 写面守卫、implementation-gate、本 dp 门）时互不吞并，先拦者赢；`ask_decision` 的钩子不应返回非空非阻断对象，避免覆盖他人语义。
- **异步与超时**：handler 是 `await` 的，框架**没有钩子级超时**——handler 挂多久 agent loop 就停多久。因此 dp 门钩子必须“同步快路径”：只做本地文件读（decision-cfg 按 mtime 热读，spec §5.1 `spec.md:113`）+ 命令/路径模式匹配 + 内存授权查表，**严禁在钩子里做 LLM 调用或 Python 子进程往返**；Python 往返属于 `ask_decision` 工具的 `execute`（天然 await 语境，自持硬超时）。这与 spec §5.3 表的分工一致：拦截=钩子（快），决策调用=工具（慢）。
- **异常**：`emitToolCall` 不 try/catch（对照 `emitUserBash` 的 try/catch，`runner.ts:953-971`）；异常直接冒泡到 `agent-session.ts:487-495` 重抛，再被 `agent-loop.ts:622-664` 的 catch 捕获 → `createErrorToolResult(error.message)` + `isError:true`。**框架语义天然 fail-closed**：钩子抛错 = 该次工具调用被拦，LLM 看到 "Extension failed, blocking execution: …" 或错误消息本身。

### 3.2 被 block 后 LLM 侧看到什么

`agent-loop.ts:636-641`（卡片锚点，实测在 `packages/agent/src/agent-loop.ts`，非 coding-agent 目录）：

```ts
if (beforeResult?.block) {
  return { kind: "immediate", result: createErrorToolResult(beforeResult.reason || "Tool execution was blocked"), isError: true };
}
```

即：工具**不执行**，取而代之一条 `role:"toolResult"`、`isError:true`、content=`[{type:"text",text:reason}]` 的消息（`:756-760, :773-789`）。worker 的 trace 层把它记为 `[TOOL_ERR]`（`worker-mode.ts:741, :3106-3162` 的 `[TOOL]`/`[TOOL_ERR]` 跟踪）。

### 3.3 防无限重试

框架对“被拦后模型换个姿势再试”没有任何内置熔断，必须自己建：

1. **reason 即指令**：block 文本固定为 `[<dp-id>] blocked by decision gate: call ask_decision(dp:"<dp-id>", trigger:"<trigger_id>") first. Retrying without a decision answer will keep failing.`——把正确出路写进错误文本（与 §2.4 防线 2 同源）。
2. **turn 级计数熔断**：扩展闭包内 `Map<toolName, {count, firstTs}>`，同一 agent run 内同一工具被同一 dp 门拦 ≥2 次 → block 文本切换为终态指令：`Terminal: stop retrying. Report "blocked on decision <dp>" via your report channel and end the turn.` 模型仍可重试，但每次都收到更强的停止信号；worker 侧还有 needs-clarification 判定链与 exit 2 兜底（spec §5.3 worker 行，`worker-mode.ts:2681`、`agent_settled:3824`）与活动看门狗兜底（无活动 10 分钟判挂死）。
3. **审计**：每次 block 追加 trace 行（复用 `appendBashWriteScopeTraceLine` 的行格式先例，`worker-mode.ts:2356`），review 报表可发现循环（spec §7.1）。

### 3.4 端到端示例：dp12 破坏性操作被拦

前置：decision-cfg 已由人开启 `dp12-destructive`（P0，spec §4 表 `spec.md:81`；开启需 `--i-understand-p0`，`spec.md:61`），worker 角色 `coding`。

1. 模型在 worker 会话（`pi -p` 启动，`launcher.py:2202-2210`）发起 `bash {command:"git reset --hard HEAD~3"}`。
2. `beforeToolCall` → `emitToolCall`；dp 门钩子（注册于 worker 分支，位置对齐其他守卫 `index.ts:47-70`）命中 `bash` → 提取写类候选（复用 `extractBashWriteCandidates` 语义）→ 静态判定为破坏性 git 操作 → 查 decision-cfg：`dp12 enabled=true, mode=auto` → 查授权表（内存 Map + 只读扫 `.agenticdoc/.../decisions.jsonl` 的 `kind=decide, decision_id="dp12-destructive:<trigger>"`, `acted=true` 行）→ 无授权。
3. 返回 `{block:true, reason:"[dp12-destructive] blocked by decision gate: git reset --hard is destructive. Call ask_decision(dp:\"dp12-destructive\", trigger:\"<task_key>\") first. Retrying without a decision answer will keep failing."}`（`worker-mode.ts:3001` 的既有 `{block:true, reason}` 同型）。
4. LLM 看到 error toolResult（§3.2），转而调用 `ask_decision {dp:"dp12-destructive", trigger:"<task_key>", note:"rollback 3 commits to recover phase-2 test failures"}`。
5. 工具 `execute`：异步 spawn `PYTHON_EXE -X utf8 mw.py decide run --project=<dir> --dp dp12-destructive --json`（参数面照抄 `triage-client.ts:180-193`，state 走 stdin），硬超时 20 s；Python `DecisionClient` 判后返回 `available=true, answers={action:{value:"block",...}}, mode=auto`；`decisions.jsonl` 由 Python 单写者落档（spec §6.1；TS 永不直写，`triage-client.ts:15` 的 D-005 先例）。
6. 工具返回可用载荷（§2.2）；若答案为 `action=block`，扩展把该 (dp,trigger) 记入授权表为“已决：禁止”，后续该动作继续被拦；若为允许类答案且 `acted=true`，钩子放行该 trigger 下匹配动作。
7. 若第 5 步 Python 不可用/超时 → 返回 `available:false`（Q6）→ 模型按指令上报 blocked；第 3 步的门持续有效。**没有任何一步“默认放行”**。

## Q4 headless/print/rpc 行为（RQ-4）

- **钩子与工具的执行机制与 UI 模式无关**：`beforeToolCall` 挂在 Agent 实例上（`agent-session.ts:468`），三种模式共用同一 session 机制；print 模式就是 `session.prompt(...)` 跑到收口（`packages/coding-agent/src/modes/print-mode.ts:33-136`）。worker 进程即 print 模式（`launcher.py:2202-2210`：`pi [--provider …] [--model …] -p <starter>`），今天线上就在 print 模式跑 `tool_call` 钩子（bash 写面守卫 `worker-mode.ts:2961-3001`）与自定义工具（`worker_file`、`mw_run_detached`）——工具+钩子在 headless 生效有生产先例，非推断。
- **三模式的差异只在 `ui.*`**：
  - interactive：真 TUI 实现（select/confirm/input 弹窗，`types.ts:136,139,142`）；
  - rpc：`createExtensionUIContext` 把 select/confirm/input 桥接为 JSONL 对话框，客户端取消/超时 → `undefined/false`（`packages/coding-agent/src/modes/rpc/rpc-mode.ts:136-160`）；
  - print：从不调 `setUIContext` → runner 永驻 `noOpUIContext`：`select→undefined, confirm→false, input→undefined`（`runner.ts:235-261`，卡片锚点 236-238；`setUIContext` 缺省回退 `runner.ts:433-434`；默认扩展模式即 "print"，`agent-session.ts:357, 2313`）。
- **设计红线（spec 已钉死）**：spec 陷阱表明令“pi 无逐工具确认门，headless UI fail-closed——用 `ui.confirm` 做决策入口在生产（print/rpc）下恒为 false，静默失败；只走 `tool_call` 钩子 + 工具返回值；禁止依赖 UI 对话框”（`spec.md:277`）。`ask_decision` 与 dp 门钩子全程不触碰 `ctx.ui`，故三模式行为逐字节一致。
- **“某模式下工具不可用”的失败路径**：`ask_decision` 不依赖模式，唯一缺席场景是扩展加载失败/分支未注册。此时 LLM 侧工具消失（调用会得到 `Tool xxx not found` 的 error toolResult，`agent-loop.ts:610-614`），但**门仍在**：dp 门钩子独立于该工具存在（同一扩展内先后注册；即便整扩展未加载，被门控动作也不会比现状更放行——P0 dp 默认关，`spec.md:95`）。运行中的兜底：钩子 block 文本引导 → 工具缺席 → 模型无法遵从 → §3.3 计数熔断转终态指令 → needs-clarification/exit 2 上抛人（`worker-mode.ts:2681`；spec §5.3 worker 行）。全程无静默放行路径。
- 未验证项：RPC 模式下 `ask_decision` 实跑表现（本调研未启动 RPC 会话实测；机制面已由代码证实与 print 同链路）。

## Q5 白名单与写面守卫的关系（RQ-5）

### 5.1 三层正交，不是二选一

| 层 | 机制 | 控什么 | 锚点 |
| --- | --- | --- | --- |
| 可见性 | `TOOL_ALLOWLISTS` + `activeToolsForType` + `setActiveTools` | LLM 能调用哪些工具 | `worker-mode.ts:96-130, 166-180, 2848-2856` |
| 参数面守卫 | `tool_call` 钩子（bash 写面、implementation-gate 等）+ 工具内谓词（`worker_file` 的 `judgeWriteTarget`） | 被允许的工具能写到哪 | `worker-mode.ts:2961-3008+`；`worker-file-tool.ts:60-67`（`shared/write-surface.ts` 单一谓词） |
| dp 授权 | decision-cfg（spec §5.1）+ dp 门钩子 + `ask_decision` | 该动作此刻是否需要人/服务裁决 | `spec.md:108-120, 146-155` |

**叠加关系**：`ask_decision` 不替代任何一层。它没有 `write/edit/bash` 那样的直接副作用面（TS 侧零文件写；`decisions.jsonl` 由 Python 单写者落，`triage-client.ts:15` D-005、spec §6.1），因此不进入 `worker-file-tool` 写面谓词的判定域；bash 写面守卫（`worker-mode.ts:2961` 起，卡片“worker-mode.ts:2986”即该 handler 内的 AC-007/T-07 escape-hatch 块）与 write/edit 分支（`:3008` 起）原样保留。dp 门是新增的第四个钩子，与既有守卫在 `emitToolCall` 里按注册顺序并存、先拦者赢（Q3 §3.1）。

### 5.2 要不要进白名单：加，但走 append 通道，不动 `TOOL_ALLOWLISTS`

- 硬约束：`TOOL_ALLOWLISTS` 与 Python 侧 `autopilot/dispatch.py` REGISTRY 逐字节相等，由 T-17 L0 测试锁定（`worker-mode.ts:101-107` 注释明令 "must stay EXACTLY equal … the T-17 L0 parity test locks that equality"）。`worker_file` 与 `mw_run_detached` 的先例就是**不进表**、在 `activeToolsForType` 里按角色追加（`worker-mode.ts:164-180`："Never goes into TOOL_ALLOWLISTS (T-17 parity lock)"）。
- **建议**：在 `activeToolsForType` 里给**所有角色**追加 `"ask_decision"`（不分 research/coding/review）：
  - 理由 1：dp 门按动作触发、不按角色触发——review 角色也可能撞上 dp12 语义外的门（dp4/dp6 等），任何角色都可能需要问；
  - 理由 2：该工具对仓库零写面（Q5 §5.1），进 read-only 角色的 active 集不放大写风险；
  - 理由 3：追加通道零破坏 T-17 锁，测试面改动最小（锁 `activeToolsForType` 输出而非表本体）。
- PM 模式：`pmActivate` 不注册（Q1 §1.3），故 PM 白名单无需动。
- `rag-research`/`vision` 等旁路桶也经 `activeToolsForType` 汇聚（`worker-mode.ts:166-180`），自动获得。

## Q6 失败安全（RQ-6）

四条路径 + 框架级第五条（钩子异常），全部收口为“结构化不可用 + 上抛人”，无“默认继续”：

| # | 失败 | 检测点 | 工具返回 | LLM 看到 | 留痕 |
| --- | --- | --- | --- | --- | --- |
| 1 | Python 不可用（mw.py 缺失 / spawn 错 / 非零 exit） | `runAskDecision` 的 spawn 包装：`{status, error, timedOut}`（先例 `triage-client.ts:171-193`：`findMwPy()` 失败即 error；`status!==0` → upstream-error `:285-287`） | `{available:false, unavailable:"upstream-error", action:"blocked-ask-human", …}` | 单行 JSON + "do NOT guess / report blocked / wait for human" 指令行 | trace `[DECISION_UNAVAILABLE] dp=… reason=upstream-error`；Python 侧证据行由其自留（`decision.py:34-36` D-005） |
| 2 | 超时 | 异步 spawn + AbortController kill，硬墙 20 s（先例 `DEFAULT_TRIAGE_TIMEOUT_MS=20_000`，`triage-client.ts:39`；Python 默认 `timeout_s=20.0`，`decision.py:241`；`.mw/decide.json` `timeout_s` 可调，`triage-client.ts:141-156`） | `{available:false, unavailable:"timeout", …}` | 同上 | trace 同上 `reason=timeout` |
| 3 | 返回非法 JSON | 两候选解析（全文 / 最后一行）失败 → `undefined`（先例 `parseJsonPayload`，`triage-client.ts:225-240, 284-286`）；解析失败绝不抛裸异常 | `{available:false, unavailable:"bad-response", …}` | 同上 | trace `reason=bad-response` |
| 4 | 配置禁用（decision-cfg 行 `enabled=false` / 未注册 dp / P0 未开） | 工具侧先查 decision-cfg（fail-soft 读，缺失=默认关，`spec.md:112`）；钩子侧 enabled=false 不设门 | `{available:false, unavailable:"disabled", …}` + 固定文 "disabled ≠ approval: the gated action remains under its normal tool permissions; if unsure, ask a human." | 明确“这不是许可” | trace `reason=disabled` |

第五条（框架自带）：钩子 handler 抛异常 → 不执行工具 → error toolResult（`agent-loop.ts:622-664`，Q3 §3.1）——**天然 fail-closed**。

**“无默认继续”证明（穷举矩阵）**：对被门控动作 A，设谓词 `gateOn(dp)`（decision-cfg 开）、`granted(dp,trigger)`（内存/档案有效授权）。
- `gateOn=false`：门不设 → A 的放行与否由**既有**工具权限/写面守卫决定，与 `ask_decision` 无关——这不是本机制引入的继续路径（P0 dp 默认关正是此态，`spec.md:95`）。
- `gateOn=true ∧ ¬granted`：钩子返回 `block:true`（唯一出口是拿到 `available:true ∧ acted:true` 的授权写入授权表）。
- `gateOn=true ∧ granted`：放行，且放行依据是审计档案里的 `decision_id` 行（可追溯、可撤销，spec §6.1 负行撤销）。
- 授权的**唯一**写入点是 `ask_decision` 的 `execute` 成功路径；该路径的四类失败（路径 1-4）全部返回 `available:false`，不写授权。 ⇒ 不存在任何失败分支能把 `granted` 置真或让钩子返回放行。Q.E.D.

实现注意：`runAskDecision` 用异步 spawn（`node:child_process` `spawn` + exit/timeout 竞速），**不要**照抄 `triage-client.ts` 的 `spawnSync`——那是 PM 派发路径的同步语境可接受，放进工具 `execute` 会阻塞整个事件循环 20 s（worker print 模式无 UI 可冻，但会拖住看门狗心跳与 trace 写入；PM 交互窗则可见卡顿）。

## 结论

1. **注册**：`pi.registerTool` + TypeBox schema + `throw` 表错（无 `isError` 字段），骨架可逐字照抄 `registerWorkerFileTool`（`worker-file-tool.ts:130-152`）；可见性 = 模式分支 × registry 允许/拒绝 × 每轮 `setActiveTools` 三层叠加（`index.ts:72-75`、`agent-session.ts:213-216/928-941`、`worker-mode.ts:2848-2856`）。
2. **契约**：入参 `dp`（TS 常量枚举 ⊆ Python 注册表）/`trigger`/可选 `note`、`question`；返回单行 JSON `{available, decision_id:"<dp>:<trigger>", mode, acted, answers, confidence_source, latency_ms}` 或 `{available:false, unavailable:<冻结 reason>, action:"blocked-ask-human"}` + 固定禁止猜测指令行；防猜测的硬保证是“钩子授权表只有 ask_decision 成功路径能写”（Q6 矩阵）。
3. **拦截**：`pi.on("tool_call")` 返回 `{block:true, reason}`，框架在 `agent-loop.ts:636-641` 落地为 error toolResult（工具不执行、`[TOOL_ERR]`）；钩子必须同步快（禁 LLM/子进程），Python 往返归 `ask_decision` execute（异步 spawn + 20 s 硬超时）；防循环 = reason 内嵌出路 + turn 级计数熔断 + trace 审计。
4. **三模式**：钩子/工具与 UI 模式无关，worker 本就跑在 print 模式且钩子已在线上生效；print 的 `noOpUIContext`（confirm 恒 false）正是 spec 禁用 `ui.confirm` 入口的原因；工具缺席时门仍在，计数熔断后上抛人，无静默放行。
5. **白名单关系**：三层正交、叠加不替代；`ask_decision` 加进 `activeToolsForType` 的全角色 append（不动 `TOOL_ALLOWLISTS`，保 T-17 parity 锁），不进写面谓词判定域，PM 模式不注册。
6. **失败安全**：四路径 + 钩子异常全部收口 `available:false` / fail-closed block + trace 留痕；穷举矩阵证明不存在失败分支导致放行。

## 证据

核心锚点（本日实测行号）：

- 注册与可见性：`packages/coding-agent/src/core/extensions/types.ts:450-509`（ToolDefinition）、`:1246-1251`（registerTool）、`:1340`（setActiveTools）、`:1074-1078`（ToolCallEventResult）、`:896-921`（CustomToolCallEvent / can-block 注释）、`:136,139,142`（select/confirm/input）、`:828-850`（InputSource / InputEvent / InputEventResult）；`packages/coding-agent/src/core/agent-session.ts:213-216`（allowed/excludedToolNames）、`:468-495`（beforeToolCall→emitToolCall，锚点 :480）、`:928-941`（setActiveToolsByName）、`:2400`（绑定）、`:357, :2313`（默认 print 模式）；`packages/coding-agent/src/core/sdk.ts:55-70`（tools/noTools）；`packages/coding-agent/src/extensions/agent-team-loop/index.ts:72-75`（PI_WORKER_TASK 分叉）。
- block 落地与错误形状：`packages/agent/src/agent-loop.ts:610-614`（tool not found）、`:622-643`（beforeToolCall，block 落地 :636-641）、`:660-664` 与 `:694-702`（异常→error result）、`:756-760`（createErrorToolResult）、`:763-771`（isError 带出）、`:773-789`（createToolResultMessage，role:"toolResult"）；`packages/agent/src/types.ts:355-368`（AgentToolResult 无 isError）。
- 钩子聚合与 noOp UI：`packages/coding-agent/src/core/extensions/runner.ts:235-261`（noOpUIContext，卡片锚点 236-238）、`:433-443`（setUIContext/hasUI）、`:932-951`（emitToolCall 首个 block 短路、无 try/catch）、`:953-971`（emitUserBash 对照）。
- 既有工具/守卫先例：`worker-file-tool.ts:20-27, :130-152, :159-165`（注册模板、throw 语义）；`worker-mode.ts:96-130`（TOOL_ALLOWLISTS+T-17 锁）、`:164-180`（activeToolsForType append 先例）、`:2821-2832`（run-detached/worker_file 注册位）、`:2848-2856`（before_agent_start→applyRagTools）、`:2961-3008+`（bash/write/edit 写面 `tool_call` 钩子，`{block:true,reason}` 在 :3001；卡片锚点 2986 在其内）、`:2356`（trace 行先例）、`:741, :3106-3162`（[TOOL]/[TOOL_ERR]）；`rag/tools.ts:400-414`（applyRagTools）。
- Python 决策服务合同：`packages/multi-workers/decision.py:14-15`（预算：timeout_s=20/max_retries=2/max_questions=8/max_state_bytes=16384/max_tokens=1024）、`:21-23`（confidence_source 硬规则）、`:34-36`（证据行）、`:77` 附近与 `:112-130`（冻结 reason 集与字段）、`:149-161`（BackendOutcome）、`:241-244`（timeout_s/max_state_bytes 默认）；`pm/triage-client.ts:15`（D-005 单写者）、`:39`（20 s 先例）、`:171-193`（runDecideMw spawn 面）、`:196-198`（unavailable 归一）、`:225-240`（parseJsonPayload）、`:263-296`（triageDispatch 失败矩阵）；spec：`.agenticdoc/mw-decision-substitution/spec.md:108-120`（§5.1 配置/mode 语义）、`:122-131`（§5.2 dp 抽象）、`:146-155`（§5.3 执行面表）、`:157-161`（§5.4 输入契约）、`:163-186`（§6 档案/关联）、`:61`（P0 门槛）、`:81`（dp12 行）、`:95`（P0 默认关）、`:277-278`（陷阱：禁 ui.confirm / 禁 context 钩子）。
- 模式面：`packages/coding-agent/src/modes/print-mode.ts:33-136`；`packages/coding-agent/src/modes/rpc/rpc-mode.ts:136-160, :321`；`packages/coding-agent/src/main.ts:884, :918`；`packages/multi-workers/launcher.py:2202-2210`（worker = `pi -p`）。

## 残留与未验证

- RPC 模式实跑 `ask_decision` 未实测（未启动 RPC 会话）；机制面已由代码证实与 print 同链路（Q4），风险低。
- `decisions.jsonl` 只读扫描的并发安全（读半行/写中读）未验证——建议实现时按“最后一行 JSON 解析失败即视为无授权”fail-closed（与 `parseJsonPayload` 末行候选同法）。
- `mw decide run` 对 dp2+ 的响应中 `mode/acted` 字段是否已在 Python 侧输出未逐行核对（`decision.py` 现有字段见 `:112-130`；`mode/acted` 属 spec §6.1 计划字段，落地时以 Python 实现为准）。
- `trigger` 的 canonical 形态（`<task_key>` vs `<task_key>#ckpt<N>` vs 裸 `ts`）由 spec §6.1 定义但 worker 侧拼接点未定，留待实现卡。

## 上下文来源

- 任务卡：`.agenticdoc/mw-decision-substitution/workers/ds-d4-ask-tool-hook/task.md`（含上下文/要求 RQ-1..RQ-6/交付契约）。
- 规范：`.agenticdoc/mw-decision-substitution/spec.md` §5.1-5.4、§6、§4（dp 表）、陷阱表。
- 源码（全部只读）：上节“证据”所列 `packages/coding-agent/src/**`、`packages/agent/src/**`、`packages/multi-workers/{decision.py,launcher.py}`。
- 本任务前置骨架：本文件初版（write-first），本次为整体替换补全。

Q-answered: 6/6
