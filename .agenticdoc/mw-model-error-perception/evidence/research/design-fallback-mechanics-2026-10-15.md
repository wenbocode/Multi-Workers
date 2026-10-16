# TRQ5 备用模型热切换机制——design 前置调研（design-fallback-mechanics）

- key: mw-model-error-perception / task trq5-fallback-mechanics (type: research)
- date: 2026-10-15
- 范围：worker-mode 内模型 id→Model 实例解析、`pi.setModel` 副作用面、dispatch.yml `fallback_models` 配置落点与 `PI_WORKER_FALLBACK_MODELS` 注入链、任务卡 `model:` 优先级互动、切换状态机的 API 事实基础。
- 对应 spec：AC-008 / AC-009（`.agenticdoc/mw-model-error-perception/spec.md:80-81`），待决点见 spec.md:91。

## 结论

1. **解析路径成立且已有先例**：worker 内把 `prefix/model-id` 解析为 `Model<any>` 用 `ctx.modelRegistry.find(PREFIX_TO_PROVIDER_ID[prefix], modelId)`；prefix 映射、解析、registry 校验在 `shared/dispatch-models.ts` 已全部存在（PM 侧 dispatch 校验同款），worker 侧直接复用，无新 API 需求。registry miss 的 id **不得**手工构造 Model（`buildFallbackModel` 会发出伪造 id 请求，正是 dispatch 校验拒绝的形态）——miss 即按 AC-009「无此模型」判耗尽。
2. **`pi.setModel` 三态返回面**：未配置凭证 → `false`（同步 pre-gate）；成功 → `true`；快照过期/凭证校验回调抛错 → **reject**。worker 侧必须 try/catch，false 与 throw 同判「该备用耗尽」。
3. **副作用面有一个必须写进 design 的全局写**：`setModel` 成功路径会 `setDefaultModelAndProvider` 把新模型写入**用户全局** `~/.pi/agent/settings.json`（非 mw 域文件）。另有 session `model_change` 条目、thinking clamp、`model_select` 扩展事件（source="set"，模型未变则不发）。切换只允许发生在两个 run 之间——不仅是「充分」，而是**必要**（run 中切换会把 model_change 条目插进 run 的 entry 流，且 worker 的重发依赖 agent_end handler 的排队续跑机制）。
4. **配置落点建议**：`.mw/dispatch.yml` 新增**顶层键** `fallback_models: {role: ["prefix/model", ...]}`。现 `models:<role>` 值被两侧读取器强校验为单行字符串，嵌套结构必被拒；顶层新键当前被两侧读取器忽略（滚动安全）。**硬约束**：Python `_model_write` 三个写路径（set/clear 等）都整文件重写且只带 `models`，不改造会把 fallback 配置静默抹掉；TS 侧需按 `readRoleModel` 同款窄解析器镜像。
5. **注入建议**：launcher 在 `inject_rag_env` 旁增加 `inject_fallback_env` post-step（launcher.py:1979 同位点），格式 `PI_WORKER_FALLBACK_MODELS="timi/glm-5.3,claude/x"`（逗号分隔 dispatch 值命名空间，禁止 `*_cli` 前缀）。worker 当前主模型**不需要**新 env：`ctx.model`（session_start，D-116 `[MODEL]` 行已走此路径）即权威主模型。
6. **任务卡 `model:` 互动结论**：`model:` 头只决定主模型（resolution 链第一优先、原样透传）；`fallback_models` 按**任务类别（role）**配置、与主模型来源正交——任务卡钉死主模型时 fallback 数组仍适用（否则钉死模型的任务完全失去降级）。worker 需按 provider+id 去重「fallback == 当前主模型」项。
7. **凭证现实**：跨 provider fallback 依赖该 provider 在 `~/.pi/agent/auth.json` 有 stored key（pi 取凭证 stored-first、worker env 被剥到只剩主路由凭证）；同 provider fallback 恒可用。v1 **不改** launcher 凭证注入（不弱化 AC-002~004 隔离），`false`→耗尽语义天然兜底。
8. **状态机 API 事实基础**：error run 判据 = `agent_end` 末条 assistant `stopReason==="error"`（pi 内部已按 settings.retry 默认 3 次指数退避重试过，worker 级 N=2 计的是**重试穷尽后**的 run；quota 类不可重试错误首轮即计入）。切换成功后重发用 `pi.sendUserMessage(..., {deliverAs:"followUp"})`（checkpoint steer 同通道，agent_end handler 排队消息会被续跑）。trace 行沿用 `[CHECKPOINT]` 的 best-effort append 模式；切换后补一条 `[MODEL] model=<新id>`（读侧取最后一条）。

## 证据

### 0. 调研方法与出处

纯源码阅读（未执行代码）：pi core（`packages/coding-agent/src/core/*`）、pi-ai（`packages/ai/src/*`）、agent-team-loop 扩展（`packages/coding-agent/src/extensions/agent-team-loop/**`）、mw Python 侧（`packages/multi-workers/{launcher,mw_common,mw}.py`）。所有行号为 2026-10-15 工作区状态。任务卡锚点核验结果：`types.ts:1350` setModel 签名 ✓、`agent-session.ts:2403` handler ✓、`launcher.py:1372-1388` 命令组装 ✓（实际函数体 1363-1403）、`launcher.py:280-368` `_build_env` ✓（265-368）。卡中「Python resolveDefaults」实为 `resolve_dispatch_model`（`_rag_resolve_defaults` 是 RAG 专用，无关）。

### 1. 问一：模型解析路径与 setModel 对未配置/不存在模型的行为

**解析面（extension ctx 可用面）**

- `ExtensionContext`：`modelRegistry: ModelRegistry`（core/extensions/types.ts:322）、`model: Model<any> | undefined`（:325）、`scopedModels: readonly ScopedModel[]`（:329，`ScopedModel { model, thinkingLevel? }` core/model-resolver.ts:63-67）、`getScopedModels()`（ExtensionAPI，types.ts:1643）。
- `ModelRegistry` 是 ModelRuntime 的同步兼容门面（core/model-registry.ts:31-33）：`getAll()` :47、`getAvailable()` :50、`find(provider, modelId)` :53（→ `runtime.getModel`）、`hasConfiguredAuth(model)` :60。
- 值命名空间：`parseModelValue`（shared/dispatch-models.ts:47-51）+ `PREFIX_TO_PROVIDER_ID`（:30-37，timi→timi、claude→anthropic、codex→openai-codex、deepseek→deepseek、zai→zai-coding-cn），与 Python `MODEL_PREFIX_TO_PI_PROVIDER`（mw_common.py:127-133）互为镜像（双侧注释都要求 keep-in-sync）。`*_cli` 前缀是另一 transport，registry 校验跳过（dispatch-models.ts:69-70）。
- 现成校验先例：`validateModelValue`（dispatch-models.ts:200-232）——registry `find` miss 即拒绝，理由写在注释里：pi 会把不可解析 id 当 custom model（core/model-resolver.ts:174-189 `buildFallbackModel` 克隆同 provider 基准模型换 id）**带着伪造 id 发请求**。`setModel` 接收的是 Model 实例，不存在「不存在模型」入口——worker 侧解析 miss 时必须判耗尽，不得手工造 Model。
- 工作区现状：worker 分支（worker/worker-mode.ts）目前**零**模型解析代码（`rg setModel|modelRegistry` 无命中）；PM 主窗口侧 `applyMainModelConfig` 已走完整链（dispatch-models.ts:293-320：parse → prefix 映射 → `ctx.modelRegistry.find` → miss 则 ui.notify → `pi.setModel`）。

**`pi.setModel` 行为（ExtensionAPI，core/extensions/types.ts:1350 `setModel(model): Promise<boolean>`）**

- handler（core/agent-session.ts:2403-2407）：`if (!this._modelRuntime.hasConfiguredAuth(model.provider)) return false; await this.setModel(model); return true;`
- `false` 路径：`hasConfiguredAuth` = provider ∈ `snapshot.configuredProviders`（core/model-runtime.ts:458-459），快照由后台 `runAvailabilityRefresh` 对**所有** provider 逐个 `checkAuth` 后重建（model-runtime.ts:280-314），且 `ModelRuntime.create` 启动时 await 首次 refresh（model-runtime.ts:208）——session 内调用时快照已就绪。
- **throw/reject 路径**（任务卡问「false 之外的 throw 路径」）：
  1. 内层 `AgentSession.setModel`（:1586-1589）再查**异步** `checkAuth`，失败 `throw new Error("No API key for <provider>/<id>")`——pre-gate（同步快照）与 live check 不一致时可达（如会话中途凭证被移除/快照过期窗口）。
  2. `checkAuth` 本身可 reject：provider 的 `apiKey.check` 回调抛错被包成 `ModelsError("auth", ...)`（packages/ai/src/models.ts:494-500）。未知 provider 在 `checkAuth` 返回 undefined（models.ts:513-514），但会被 pre-gate 先拦成 `false`。
  - **设计含义**：worker 侧调用必须 try/catch；`false` 与 rejection 同判「该备用不可用/耗尽」，不允许未捕获 rejection 冒泡到 agent_end handler（会变成 extension error 噪声）。
- 会话中途模型对象可被 `_refreshCurrentModelFromRegistry` 换绑（agent-session.ts:2328-2340）——比较模型一律按 provider+id，不得缓存对象引用。

### 2. 问二：setModel 副作用面

**成功路径内的顺序**（core/agent-session.ts:1586-1601）：

1. auth 校验（见上）；
2. `this.agent.state.model = model`（:1593）——立即生效，下一 turn 的请求即用新模型（`prepareNextTurnWithContext` 每轮取 `agent.state.model`，:541-553）；
3. `sessionManager.appendModelChange(provider, id)`（:1594）——session 文件追加 `model_change` entry（core/session-manager.ts:1083-1095）；
4. **`settingsManager.setDefaultModelAndProvider(provider, id)`（:1595）——写入用户全局 `~/.pi/agent/settings.json` 并 `save()`（core/settings-manager.ts:700-706）**。launcher 不重定向 `PI_CODING_AGENT_DIR`（launcher.py 全文无该串），mw worker 与用户其他 pi 会话共用全局设置：一次 fallback 切换会改掉用户账户级默认模型（main.ts:454-462 的后续 session 会在「无 --model 且有 scoped models」时读它）。design 必须显式接受该副作用（mw 属主机器场景可接受），至少写入 AC/风险节。
5. `setThinkingLevel(clamp 后的 level)`（:1597）——clamp 规则：`_getThinkingLevelForModelSwitch`（:1740-1748）：新模型 `!model.reasoning`（`supportsThinking` :1736-1738）→ 用 settings 默认或 `DEFAULT_THINKING_LEVEL="medium"`（core/defaults.ts:3）；否则沿用当前 level；`setThinkingLevel`（:1684-1692）再经 `clampThinkingLevel`（pi-ai compat，agent-session.ts:38 import；`_clampThinkingLevel` :1750-1752）夹到新模型支持档位。**对 design 的含义**：thinking level 无需 worker 干预，自动迁移/夹紧。
6. `await this._emitModelSelect(model, previousModel, "set")`（:1599）——`modelsAreEqual` 相同则不发（:1568-1573）。

**ModelSelectEvent**（core/extensions/types.ts:789-803）：`{ type:"model_select", model, previousModel, source:"set"|"cycle"|"restore" }`，订阅 `pi.on("model_select", ...)`（types.ts:1237）。PM 侧已有消费先例：`registerMainWindowModel` 在 model_select 时 `recordWindowModel`（dispatch-models.ts:326-332）——**worker 分支刻意不挂该 hook**（「worker windows … must not poison the inheritance file」，dispatch-models.ts:322-324 注释）；worker 的 fallback 切换同样不得写 `.mw/window-model`。

**切换后下一次 prompt 的事件序列**：`before_agent_start` → `agent_start` → `message_start(user)` → 流式 `message_update` → `message_end`/`message_start(assistant)`。**`MessageStartEvent` 只有 `{ type, message }`，无独立 model 字段**（types.ts:746-749）——「model 字段」实际长在 AssistantMessage 上：`provider` + `model`（请求 id）+ `responseModel`（上游返回 id）（packages/ai/src/types.ts:410-425）。监控侧的可读信号 = session 内 assistant 消息的 provider/model + trace/log 行；watch 徽章读 trace `[MODEL]` 行（shared/heartbeat.ts:92 `MODEL_LINE_RE`，读侧取最后一条），worker 在切换成功后应补写一条 `[MODEL]`（写入函数现成：`appendModel`，worker/output-writer.ts:589-598，D-116）。

**「切换必须发生在两个 run 之间」是否充分**——充分且**必要**：

- 扩展侧 `setModel` 无 idle 门（对比 RPC client 的 `#runIdleOperation`，core/client/remote-session.ts:197-202）——run 中调用不会被拒绝，但会把 `appendModelChange` 条目插进 run 的 entry 流中间，且 retry/续跑路径（`_handlePostAgentRun`，agent-session.ts:1077-1104）语义纠缠。design 保持「只在 agent_end/settle 后切换」。
- agent_end handler 内排队消息会被续跑：`_handlePostAgentRun` 检查 `agent.hasQueuedMessages()` 并 `agent.continue()`（agent-session.ts:1102-1104）——worker 在同一 handler 里 `setModel` → `sendUserMessage(followUp)` 的顺序是既定机制支持的（checkpoint steer 同款：worker-mode.ts:3363-3376）。

### 3. 问三：配置与注入链

**dispatch.yml 现状格式**（`.mw/dispatch.yml`）：`{"models": {role: "prefix/model"}}`，role ∈ `DISPATCH_ROLES = ("main","coding","review","research","vision")`（mw_common.py:146）。

- 读取：`load_dispatch_config`（mw_common.py:224-256）——缺文件 `({}, None)` 静默；顶层必须 mapping；`models` 必须 mapping；**role 必须在 DISPATCH_ROLES 内**（:252-253）；**值必须是非法空非空 str**（:254-255）→ `models.<role>` 下嵌套 dict/list 会被整体判坏。**未知顶层键被忽略**（只读 `models`）。
- TS 侧镜像读取：`readRoleModel`（dispatch-models.ts:112-145）手工窄解析 `models:` 块的 `role: value` 单行字符串（含 BOM 处理）——同样容不下嵌套结构。
- 写入：`_model_write`（mw.py:3437-3447）整文件重写 `{"models": models}`；`mw model set` :3524、`mw model clear` :3539（写 `{}` 整文件清空）、:3553 均走它 → **任何不在 `models` map 里的内容会被下一次 `mw model` 写操作静默抹掉**。这是 schema 落点的决定性约束。
- （任务卡所说「resolveDefaults」核对：mw_common.py:1005 `_rag_resolve_defaults` 是 RAG server/budget 专用；dispatch 模型链的实际实现是 `resolve_dispatch_model`（mw_common.py:296-321）+ launcher `_resolve_entry_model`（launcher.py:160-179）。）

**主模型 resolution 链**（`resolve_dispatch_model`，mw_common.py:296-321）：

```
task.md `model:` 头（原样透传，不做 compat 过滤，:310-311）
  > .mw/dispatch.yml models.<role>（role=TASK_TYPE_TO_ROLE[type]，经 model_value_compatible 过滤 :279-293）
  > .mw/window-model（PM 窗口记录，mw_common.py:258-264）
  > ""（per-cli 硬编码默认，launcher._build_command :1376 timi 默认 glm-5.3；直接 provider 无默认必须显式 :1380-1387）
```

launcher spawn 位点（launcher.py:1972-1981）：`_resolve_entry_model` → `_effective_entry`（launcher.py:228-263：prefix 重映射 provider；`*_cli` 必须 cli 匹配；bare 保留路由）→ `_build_env(effective, config, rag_config)` → `inject_rag_env(env, effective, project_dir)`（:1979，post-step 模式）→ `_build_command(effective)`。

- `_build_command` pi 分支（launcher.py:1365-1403）：显式 provider → `["pi","--provider",p,"--model",m,"-p",starter]`；generic → `["pi"(,"--model",m),"-p",starter]`。模型只是 CLI flag，凭证布线在 `_build_env` 不变（:1366-1371 注释）——**fallback 切换发生在 worker 进程内，天然继承同一凭证布线**。
- 任务卡 `model:` 的派发时校验（mw-dispatch-role-escape 面）：`planDispatchFrontmatter`（pm/ui-bridge.ts:1249-1310）对 `requested || configured` 跑 `validateModelValue`，未知 id 拒写卡；`/worker` 覆盖路径同检（ui-bridge.ts:3337）。

**env 注入面**：`_build_env`（launcher.py:265-368）六条 return 路径，每条只注入**主路由**凭证（`TIMI_API_KEY` / `ZAI_CODING_CN_API_KEY` / `ANTHROPIC_API_KEY` / `DEEPSEEK_API_KEY` / 代理路由 key）+ `PI_WORKER_TASK`；`_stripped_env`（:126-148）把**所有**声明过的凭证 env 名 + base_url env 从继承环境剥掉（AC-024/025）。今天 worker env 里的 mw 标记只有 `PI_WORKER_TASK`（另有 worker 侧消费的 `PI_WORKER_TIMEOUT_MS`/`PI_WORKER_IDLE_MS`，worker-mode.ts:247,255）。

**`fallback_models` 键的落点建议（事实支撑）**：

- 新**顶层键** `fallback_models: {role: ["prefix/model", ...]}`：
  - `models.<role>` 放不下（两侧读取器强校验单行字符串，见上）；
  - 顶层新键今天被两侧读取器忽略 → 旧代码滚动安全；
  - 代价①：`load_dispatch_config` 需新增解析分支（role 校验复用 DISPATCH_ROLES；值 = 非空 str 列表）；代价②：**`_model_write` 全家族必须改为保留/合并额外顶层键**（或 fallback 走独立 `mw model fallback` 写命令 read-modify-write），否则静默丢失；代价③：TS 侧 `dispatch-models.ts` 加同款窄解析器（如 `readRoleFallbacks`），BOM 处理照抄 `readRoleModel`。
- 替代方案（独立文件 `.mw/fallback.yml`）可绕开写路径冲突，但多一个配置文件与 doctor 面，且 spec AC-008 明文「按 `.mw/dispatch.yml` 为某任务类别配置」——按 spec 走顶层键。

**`PI_WORKER_FALLBACK_MODELS` 注入格式建议**：逗号分隔 dispatch 值，`PI_WORKER_FALLBACK_MODELS="timi/glm-5.3,claude/claude-x"`：

- 用 dispatch 值命名空间（prefix/model）而非裸 `provider/model`：TS 侧 `parseModelValue`/`PREFIX_TO_PROVIDER_ID`/registry 校验全复用，与 trace `[MODEL_FALLBACK] from=/to=` 的值域一致（PM 可读）；
- 禁止 `*_cli` 前缀项（fallback 不能换 transport：tool allowlist/watchdog/[MODEL] 徽章都是 pi worker-mode 特性，`_effective_entry` docstring launcher.py:228-236）；
- 注入位点：`inject_fallback_env(env, effective, project_dir)` 紧跟 launcher.py:1979 `inject_rag_env` 之后（同一 post-step 模式，role 从 `_read_task_md_fields` 的 type 经 `TASK_TYPE_TO_ROLE` 得出）；列表为空则不设该 env（worker 视为无 fallback，与现状一致）。

### 4. 问四：worker 启动时如何知道当前主模型；任务卡 `model:` 覆盖时 fallback 是否仍适用

**主模型感知（不需要新 env）**：

- pi 启动解析：`--provider/--model` flag → `resolveCliModel`（main.ts:428-447）→ `options.model` → session 初始模型；无 flag 时 fallback 到 settings 默认/scoped（main.ts:454-476）。launcher 组装的 flag（含 timi 硬编码默认）全部经此路径落进 `ctx.model`。
- ExtensionAPI **没有**模型 getter（worker-mode.ts:2692-2694 注释明言），模型只能从事件 ctx 读：`pi.on("session_start", (_e, ctx) => ctx.model)`——D-116 的 `[MODEL]` 行已经走这条路（worker-mode.ts:2693-2696 → output-writer.ts:591-598）；`ctx.model` 每次 emit 现取（绑定 `getModel: () => this.model`，agent-session.ts:2413），恒为权威值。
- 结论：fallback 状态机的主模型锚 = session_start 时 `PROVIDER_ID_TO_PREFIX[ctx.model.provider]` + `ctx.model.id`（与 `recordWindowModel` 同规则，dispatch-models.ts:88-101）；prefix 不在映射内 → 该 worker 无 fallback（命名空间外，值域不闭环）。

**任务卡 `model:` 覆盖时 fallback 是否仍适用——适用（design 应如此定）**：

- 事实：`model:` 只在 resolution 链第一层决定主模型（mw_common.py:310-311 原样透传）；`fallback_models`（按本报告建议）按 **role** 配置，与主模型取值来源（task/ config:/window/default）正交。spec AC-008 的措辞是「按任务类别配置 fallback_models」——类别 = role，不是模型值。
- 若 design 选「task 卡钉了 `model:` 就跳过 fallback」，钉死模型的任务（恰恰是 PM 判断需要特定能力面时）将完全失去降级，与 AC-008 目的相悖。
- 需要的配套：worker 侧按 provider+id 去重——fallback 数组中等于当前主模型的项跳过（视为已耗尽或直接 skip，建议 skip 不计入耗尽日志噪音）。

### 5. 问五：结论→决策映射

**切换状态机应基于的 API 事实**：

| 状态机要素 | 事实基础 |
|---|---|
| error run 判据 | `agent_end` 的 `event.messages` 末条 assistant `stopReason==="error"`（`StopReason` 联合含 "error"，ai/src/types.ts:388；`errorMessage` :423）。`AgentEndEvent` 本身无 error flag（extensions/types.ts:720-723） |
| pi 内部重试已先行 | `_prepareRetry`（agent-session.ts:2695-2712+）：settings.retry 默认 `{enabled:true, maxRetries:3, baseDelayMs:2000}` 指数退避（settings-manager.ts:28-33），可重试判定 `isRetryableAssistantError`（ai/src/utils/retry.ts:230-240：quota/limit 模式与 `outerRetryEligible=false` 诊断不可重试）。→ worker 级 N=2 计的是**内部重试穷尽后**的 error run；quota 类错误首轮即计（更快触发降级，符合直觉） |
| per-model 连续计数 | 按 provider+id 键控；成功 run（末条 assistant stopReason ∈ stop/toolUse/length，**"aborted" 不重置也不计数**）或成功切换时清零 |
| 切换尝试序 | 按数组顺序逐项：skip（==当前主模型）→ registry `find` miss = 耗尽（AC-009「无此模型」）→ `try { ok = await pi.setModel(model) } catch { ok=false }`；`false`/throw = 耗尽，继续下一项 |
| 切换成功动作 | trace `[MODEL_FALLBACK] from=<prefix/curId> to=<prefix/newId> at_run=<k>`（worker-mode.ts:3264-3290 `[CHECKPOINT]` 行的 best-effort append 先例）+ `appendModel` 补 `[MODEL]` 行 + 计数清零 + `pi.sendUserMessage(<重发内容>, {deliverAs:"followUp"})`；agent_end handler 内排队消息由 `_handlePostAgentRun` 续跑（agent-session.ts:1102-1104） |
| 全部耗尽 | 不切换，error 计数继续走向既有熔断路径（AC-008「未配置 fallback 的类别行为与现状一致」同构） |
| 阈值 | `PI_WORKER_MODEL_ERR_MAX`（spec.md:91 待确认项，默认 2）读法照抄 `PI_WORKER_TIMEOUT_MS`/`PI_WORKER_IDLE_MS`（worker-mode.ts:247-255） |

**配置 schema 与注入格式建议**（汇总）：

```yaml
# .mw/dispatch.yml（新增顶层键；models: 区保持不变）
models:
  coding: timi/glm-5.3
fallback_models:
  coding: ["timi/glm-5.3", "claude/claude-x"]
  research: ["deepseek/deepseek-v4"]
```

- env：`PI_WORKER_FALLBACK_MODELS="timi/glm-5.3,claude/claude-x"`（逗号分隔，prefix/model 值域，注入位点 launcher.py:1979 后）；
- Python：`load_dispatch_config` 解析 + 校验（role ∈ DISPATCH_ROLES、每项为非空 str、`*_cli` 前缀拒绝）；`_model_write`/`cmd_model` 写路径改为保留未知顶层键（或 fallback 独立写命令）；launcher `inject_fallback_env` post-step；
- TS：`dispatch-models.ts` 加 `readRoleFallbacks`（镜像 readRoleModel 的窄解析 + BOM）；worker-mode 在 session_start 锚定主模型 + 挂 agent_end 计数/切换 handler；
- 主模型来源（task `model:` / role / window / default）不影响 fallback 适用性；`*_cli` 前缀的 worker（codex/claude transport）无 fallback（非 pi 进程，机制不适用）。

## 残留与未验证

- 全部结论来自源码阅读，**未执行任何代码**。以下为推断而非观察：
  - reject 路径 1（快照过期 → 内层 `checkAuth` throw）是代码推演，未实际构造复现；
  - 扩展 `setModel` 在 `-p` print mode 下的行为无 mode 门禁（runner.bindCore 无差别绑定），推断可用，但未实测；
  - `setModel` 全局 settings 写对**并行其他 worker/PM 窗口**的实际影响半径（settings-manager `save()` 的写冲突行为）未验证。
- `mw model` 第三个 `_model_write` 调用点（mw.py:3553）所属子命令未逐一展开（set/clear 已核实为整文件重写，结论不受影响）。
- `DEFAULT_THINKING_LEVEL` 之外，settings `getDefaultThinkingLevel()` 的项目级覆盖值未枚举（不影响 clamp 语义）。
- spec.md:91 的待决数值（N=2 默认、告警阈 K=2）属 design 决策，本调研只提供 `PI_WORKER_MODEL_ERR_MAX` 的既有 env 模式，不定值。
- 跨 provider fallback 的真实凭证可用率（auth.json 是否常备多 provider key）是部署事实，非代码事实——design 应把「同 provider 优先」作为 fallback 数组的排列建议而非机制强制。

## 上下文来源

- spec：`.agenticdoc/mw-model-error-perception/spec.md:23,80-81,91`（AC-008/009、待决点）
- goal：`.agenticdoc/goal.md`（工具白名单 / 进程隔离 / 凭证隔离约束）
- pi core：`packages/coding-agent/src/core/agent-session.ts`（1586-1601 setModel；2403-2407 扩展 handler；1568-1573 _emitModelSelect；1684-1752 thinking；1077-1104 post-run 续跑；2695+ retry；2328-2340 模型换绑；2413 ctx.model 绑定）
- pi core：`core/extensions/types.ts`（322-329 ctx 面；746-749 MessageStartEvent；789-803 ModelSelectEvent；720-728 AgentEndEvent/AgentSettledEvent；1350 setModel 签名；1643 getScopedModels）
- pi core：`core/model-registry.ts`（47-61 门面）；`core/model-runtime.ts`（208 首次 refresh；280-314 快照重建；458-459 hasConfiguredAuth）；`core/session-manager.ts`（1083-1095 model_change）；`core/settings-manager.ts`（28-33 retry 默认；700-706 全局设置写）；`core/defaults.ts:3`；`core/model-resolver.ts`（63-67 ScopedModel；174-189 buildFallbackModel）；`main.ts`（428-476 启动模型解析）
- pi-ai：`packages/ai/src/types.ts`（388 StopReason；410-425 AssistantMessage）；`packages/ai/src/models.ts`（494-517 checkAuth）；`packages/ai/src/auth/resolve.ts`（46-100 stored-first）；`packages/ai/src/utils/retry.ts`（230-240）
- 扩展：`shared/dispatch-models.ts`（30-51 映射/解析；88-101 recordWindowModel；112-145 readRoleModel；200-232 validateModelValue；293-332 applyMainModelModel/register）；`worker/worker-mode.ts`（2552 入口；2692-2696 [MODEL]/session_start；3264-3290 [CHECKPOINT]；3363-3376 steer 通道）；`worker/output-writer.ts`（589-598 appendModel D-116）；`shared/heartbeat.ts`（92 [MODEL] 行读取）；`pm/ui-bridge.ts`（1249-1310、3337 派发校验）
- mw Python：`launcher.py`（126-148 _stripped_env；160-179 _resolve_entry_model；228-263 _effective_entry；265-368 _build_env；370+ inject_rag_env；1363-1403 _build_command；1972-1981 spawn 位点）；`mw_common.py`（111-146 dispatch 配置/角色；224-256 load_dispatch_config；258-264 window-model；279-321 model_value_compatible/resolve_dispatch_model）；`mw.py`（3437-3447 _model_write；3450+ cmd_model；3524/3539/3553 写位点）
