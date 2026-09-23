# Research: pi Extension API 工具调用拦截能力（W1）

## 决策问题
spec §1.1/§1.4 与 §4 风险第一条——mw-implementation-gate 计划在 write/edit/bash 执行前做硬拦截（key 检查门禁）。pi 的 Extension API 能否在工具执行前拦截（block/gate），还是只能事后审计？现有扩展（含本仓 agent-team-loop）有无先例可复用？

## 调研方法与出处
- `packages/coding-agent/docs/extensions.md`（全文 2988 行通读 + 交叉引用）：:11（Event interception 能力声明）、:19/:21（Permission gates / Path protection 官方用例）、:751-813（tool_call 事件节）、:814-860（tool_result 事件节）、:2046+（Overriding Built-in Tools）、:2889（错误处理 fail-safe）。
- 事件 API 类型与分发源码：
  - `packages/coding-agent/src/core/extensions/types.ts:853-912`（ToolCallEvent 联合类型，含各工具 input 形状）
  - `packages/coding-agent/src/core/extensions/types.ts:1071-1075`（ToolCallEventResult）
  - `packages/coding-agent/src/core/extensions/types.ts:1018-1029`（isToolCallEventType 类型收窄）
  - `packages/coding-agent/src/core/extensions/types.ts:1188`（ExtensionHandler 签名）、:1236（on("tool_call") 重载）
  - `packages/coding-agent/src/core/extensions/runner.ts:932-951`（emitToolCall 分发语义）
  - `packages/coding-agent/src/core/agent-session.ts:479-500`（agent.beforeToolCall 挂接，:497 异常包装）
  - `packages/agent/src/types.ts:56-64`（BeforeToolCallResult 契约）、:271（hook 类型）
  - `packages/agent/src/agent-loop.ts:616-655`（prepareToolCall：校验→beforeToolCall→block 分支）；:445-452（sequential：每调用先 prepare 后执行）；:498-534（parallel：全部 preflight 完成后才 Promise.all 执行）
- agent-team-loop 事件接线（重点 tool 层）：
  - `packages/coding-agent/src/extensions/agent-team-loop/index.ts:40`（registerProtectedConfigGuard，所有模式注册）
  - `shared/protected-config.ts:249-274`（tool_call 硬拦截：write/edit 路径 + bash 命令文本级启发式）
  - `shared/pm-state-guard.ts:107-125`（tool_call 硬拦截 pm-state.md 接口行；注释明示 bash 侧不拦、由事后审计兜底）
  - `worker/worker-mode.ts:515-518`（before_agent_start 里 setActiveTools 工具白名单）
  - `worker/worker-mode.ts:527-552`（read-scope tool_call 拦截门）、:589-610（tool_execution_start/end 观察 + trace）
  - `pm/pm-orchestrator.ts:643`（registerPmStateGuard 注册点）、:671-679（tool_execution_start/end 关联 args——PM 侧纯观察，无拦截）
- examples/extensions/ 扫描（guard/deny/block/reject/protected 关键词 + tool_call 全量）：
  - `permission-gate.ts:13-30`、`protected-paths.ts:13-27`、`plan-mode/index.ts:164-173`、`rpc-demo.ts:46-60`（四种 tool_call block 先例）
  - `tool-override.ts:69-100`（同名注册覆盖内置 read，execute 内访问控制）
  - `sandbox/index.ts:16-19`（注释明示可用 tool_call input 变体替代换工具实现沙箱）
  - `bash-spawn-hook.ts:18-31`（createBashTool spawnHook）、`gondolin/index.ts`（工具 operations 路由进 micro-VM）

## 发现

### Q1. 执行前拦截的精确 API 面
- 事件名 `tool_call`，`pi.on("tool_call", handler)` 注册（types.ts:1236）。handler 签名 `(event, ctx) => Promise<ToolCallEventResult | void> | ToolCallEventResult | void`（types.ts:1188），可同步可异步。
- event 字段：`{ toolName, toolCallId, input }`（types.ts:853-912）。
- 返回值语义（types.ts:1071-1075）：`{ block?: boolean; reason?: string }`。`block: true` 阻止执行；`reason` 成为回给 LLM 的错误结果文本。改参数不靠返回值——原地改 `event.input`（无二次校验）。
- 时序：before-tool。`tool_execution_start` 先发（agent-loop.ts:446/:501），随后 `prepareToolCall` 在 schema 校验之后、实际执行之前调用 beforeToolCall（agent-loop.ts:616-628）；`beforeResult?.block` → 立即返回 `createErrorToolResult(reason || "Tool execution was blocked")`，isError=true，工具本体从不执行（agent-loop.ts:636-641）。agent 层契约原文："Returning `{ block: true }` prevents the tool from executing. The loop emits an error tool result instead."（packages/agent/src/types.ts:56-64）。
- 并行模式时序保证：同一条 assistant 消息的兄弟调用先全部 preflight（含 tool_call 门禁）再并发执行（agent-loop.ts:498-534；extensions.md:751-757）——门禁对整批生效后才开跑，不存在"先执行的兄弟绕过门禁"竞态。
- 分发语义（runner.ts:932-951）：按扩展加载序遍历 handler；第一个返回 `block: true` 的 handler 短路胜出；非 block 返回值继续传播（对拦截无意义）。
- fail-safe：handler 抛错 → agent-session.ts:497 包装为 "Extension failed, blocking execution" → prepareToolCall 的 catch 兜住 → 立即错误结果（agent-loop.ts:651-655）。即 handler 故障=拦截，不会放行（extensions.md:2889 官方确认）。
- 对照：`tool_result`（执行后）只能修改结果内容，副作用已发生，无法撤销；`tool_execution_start/end` 纯观察无返回值语义。真正能 block 的只有 `tool_call`（工具层）与 `user_bash`（用户 `!` 命令层，另一套）。

### Q2. 拦截时能否看到工具参数
- 能。`event.input` 就是 `validateToolArguments` 的产物——工具即将实际执行的参数本体（agent-loop.ts:617-624 → agent-session.ts:487-491 透传）。write/edit 携带 `path`（+ `content` / `edits[{oldText,newText}]`），bash 携带 `command`（types.ts:858-911）。
- 且参数可原地改写：改动直接作用于真实执行、后续 handler 可见、无重校验（extensions.md:757-764）。
- 仓内先例均已这样读参数：protected-config.ts:251-257 读 `input.path`/`input.command`；pm-state-guard.ts:98-106 读 `input.edits[].oldText/newText`；worker-mode.ts:536-539 读 `input.path`（含 ls/find/grep 省略 path 时默认 "." 的堵漏）。

### Q3. 本仓先例（gate/reject/deny/block/protected 命中清单）
- 生产级（agent-team-loop 自身，即 MW 框架已 shipping 的模式）：
  - `shared/protected-config.ts:249-274`：write/edit 路径硬 block + bash 写构造启发式（fail-closed：引用受保护路径且带任意写构造即拒，读侧重跑）。index.ts:40 所有模式注册。这是"before-tool 硬门"最完整的本仓实现。
  - `shared/pm-state-guard.ts:107-125`：write/edit 修改 pm-state.md 接口行即 block。注释明确承认局限：bash 侧（sed/echo）不拦，由 audit_phase.py 两源分叉检查事后兜底。
  - `worker/worker-mode.ts:527-552`：read-scope 读侧遏制门，block 时同步写 trace.log + output.md 拒绝清单。
  - `worker/worker-mode.ts:515-518`：`pi.setActiveTools` 按任务类型收窄工具集（预防式，直接把 write/bash 从模型可用集移除）。
  - PM 侧（pm-orchestrator.ts:671-679）：只用 tool_execution_start/end 做 args 关联与事后接管，无拦截——与 worker 侧分工明确。
- 示例级：permission-gate.ts:13-30（危险 bash 确认门；`ctx.hasUI` 为 false 时默认 block——print 模式无 UI 只能按规则拒）；protected-paths.ts:13-27（.env/.git/node_modules 写保护）；plan-mode/index.ts:164-173（计划模式 bash 白名单门）；rpc-demo.ts:46-60（RPC 模式同型）；tool-override.ts:69-100（同名覆盖 read + execute 内访问控制，属"换实现"而非前置门）；sandbox/index.ts:16-19 注释明示 tool_call 变体是替代方案。

### Q4. 建议：硬门（before-tool hard intercept）是否仅靠 Extension API 可行
- **可行，无需改 pi 核心**。证据链完整闭合：`{ block: true }`（扩展返回）→ runner.emitToolCall 短路（runner.ts:932-951）→ agent.beforeToolCall 透传（agent-session.ts:479-500）→ prepareToolCall 立即错误结果、工具不执行（agent-loop.ts:636-641）。且本仓 protected-config / pm-state-guard / read-scope 三处生产代码已在用同一机制，非纸面能力。
- 设计必须带上的约束与配套（决定 gate 的形态）：
  1. **block 的反馈通道是 in-turn 错误结果**：被拒调用的 reason 文本会作为 isError 工具结果回到 LLM，模型当轮即可读到并自适应。因此 reason 必须是可行动的指引（如"无活动 key：先 /agentic 建 key 或走 mini-spec 快路径"），而非裸拒绝。protected-config 的 GUARD_EXPLANATION 就是这个范式。
  2. **门只覆盖工具中介的写**。bash 里的 `sed -i`、重定向、`mv/cp/rm`、python -c/node -e 内联写全部绕过 write/edit 门——pm-state-guard 已实证此洞并配事后审计；protected-config 用文本级写构造启发式 fail-closed 兜（会过拒，读侧重跑可接受）。纯 write/edit 硬门 + 无 bash 侧 = 一行 `echo > file` 即穿。
  3. **扩展加载序与短路序**：先 block 者胜（runner.ts:932-951）。gate 扩展与既有 tool_call 用户（protected-config、read-scope）天然可叠加——各 handler 顺序执行、共享 input 变异链，无需协调。
  4. **handler 故障即拦截**（fail-safe，agent-session.ts:497）：对 enforcement 是正确默认；handler 须保持轻量，避免每个工具调用都引入可感延迟（异步 await 串行在 preflight 路径上）。
  5. **无 UI 场景只能按码决策**：worker 跑 print 模式（ctx.hasUI=false），confirm/select 不可用（permission-gate.ts:20-23 先例：无 UI → 默认 block）。MW 的 key 门禁必须是纯代码判定，不存在人机确认路径。
  6. 另有两条更强的替代/补充，按需取用：`pi.setActiveTools`（worker-mode.ts:515-518——按类型直接摘除 write/bash，模型根本看不到该工具，属预防而非门）；同名工具覆盖 / spawnHook / operations 注入（tool-override.ts、bash-spawn-hook.ts、gondolin/——换实现层面做沙箱，代价是要复刻 result 形状）。

## 结论 → design 形态建议
- **采用前置硬拦截（hard intercept）为主形态**：`pi.on("tool_call")` 返回 `{ block: true, reason }` 挂 key 检查门，write/edit 直接判路径与 key 状态。仅 Extension API 即可实现、已在本仓生产验证、fail-safe 方向正确。post-hoc audit 不能作为主形态——副作用（文件已写入）不可撤销，事后只能发现不能阻止，与 spec §1.1 "从 advisory 升级为 enforcement" 的目标冲突。
- **形态为三层组合**（复用本仓既有模式，与 protected-config/pm-state-guard 同构）：
  1. write/edit 硬门（主体，精确判定，误报≈0）；
  2. bash 写构造启发式（fail-closed：疑似写且目标在管辖范围即拒 + 指引重跑只读部分；接受过拒成本，声明"非沙箱"）；
  3. 事后审计兜底（tool_result/会话级扫描 bash 逃逸写，对齐 pm-state-guard→audit_phase.py 先例）——第三层是补漏，不是主门。
- reason 文本即引导通道：把建 key 的最短路径写进 reason，让逃逸尝试在当轮转化为合规行为，而不是反复撞门。
- 不建议用 input 变体或工具覆盖实现本门禁：变异不阻断（只是改参），覆盖需复刻 result 形状且 interactive 模式有覆盖告警；`tool_call` block 语义最贴合、实现最薄。