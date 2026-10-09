# RQ-5: vision 能力的"框架主动感知面"与调用点清单（SPEC 期调研，只读）

TL;DR
- PM 的 LLM 可见面里**唯一枚举任务类型的是 `dispatch_worker` 的 `type` 参数描述**：`pm/ui-bridge.ts:1146` 硬编码 `'coding' | 'review' | 'research'`（连既有 `rag-research` 都没列）；PM 系统提示 `PARALLEL_PROTOCOL`（`pm/pm-orchestrator.ts:650-658`）只在 `:653` 点名 `type: research`。整个 agent-team-loop 扩展 grep `image|vision|png` 只命中 `supervision/revision` 子串，无任何视觉面。
- 因此新增 `design` 类型 + `vision` 角色后 PM **不会主动用**：只改 `DISPATCHABLE_TYPES` 是"能派但不提示"；不同步 `ui-bridge.ts:1146/1554/1993` + `PARALLEL_PROTOCOL`，PM 不知道它们存在。
- 四个运行时"配置可见面"（`mw model show`、`mw doctor`、conductor 派发、PM 窗口 main 应用）**没有一个展示 images 能力**；全仓只有 `cli/list-models.ts:71` 有 images 列。
- 自动路由挂点：PM 路径干净挂点 = `resolveDispatchType`（`ui-bridge.ts:982-998`）之后、`planDispatchFrontmatter`（`:1024-1096`）之前；conductor 路径**没有内容检测入口**（type 全是各调用点字面量），auto-route 必须新调用点。

## 决策问题
1. 新增 `design`/`vision` 后，哪些"告诉 PM 有哪些任务类型/角色/模型能力"的文本必须同步，PM 才会主动感知？
2. `mw model show` / `mw doctor` / conductor 派发 / PM 窗口 main 应用四个运行时代码点现在是否展示"模型能力（images）"？
3. "描述引用图片 → 自动用 vision 角色"的最小改动点在哪？与 AC-006 派发期拒绝的先后关系与冲突面？
4. PM 窗口自身看图（main 为纯文本模型）会发生什么？与"把图交给 vision worker"两条路径的可达性差异？

## 调研方法与出处
只读静态阅读（未运行测试、未改任何文件）：`packages/coding-agent/src/extensions/agent-team-loop/{pm/ui-bridge.ts,pm/pm-orchestrator.ts,shared/dispatch-models.ts}`（全文件）、`packages/coding-agent/src/modes/interactive/interactive-mode.ts`、`packages/coding-agent/src/{cli/list-models.ts,core/tools/read.ts}`、`packages/ai/src/{types.ts,api/transform-messages.ts}`、`packages/multi-workers/{mw.py,mw_common.py,README.md,UPDATE.md,dispatch-table.md,autopilot/dispatch.py,autopilot/conductor.py,skills/mw-rag/SKILL.md}`、`.agents/skills/agentic-task/**`、`AGENTS.md`；grep 覆盖"是否提及 images/vision"与硬编码类型清单。基线见 `spec-baseline-and-candidates-20260926.md`，类型/角色管道见 `spec-role-type-plumbing-20260926.md`。

## 发现

### A. LLM 侧（PM"知情面"）逐条（file:line + 真实原文片段）
1. `dispatch_worker` 工具：注册 `pm/ui-bridge.ts:1112-1113`；工具自己的 `description`（`:1114-1116`）只写 "Dispatch a task to a background worker agent. Creates .agenticdoc/<task_key>/task.md and queues it..."，**不提类型、不提模型能力**，且无 `promptGuidelines`。类型清单只存在于 `type` 参数描述 `:1146`："Task type: 'coding' | 'review' | 'research'. Selects the dispatch.yml role (and the worker tool allowlist). Default: derived from cli (pi -> coding, claude -> review, codex -> codex)."
2. `dispatch_worker` 与 `/worker` 的**拒绝文案是动态的**（`resolveDispatchType`，`:982-998`：`:991` `DISPATCHABLE_TYPES.includes`，`:994` "Must be one of: ${DISPATCHABLE_TYPES.join(\", \")}"；当前值 `shared/dispatch-models.ts:74` `["coding","review","research","rag-research"]`）→ 加 `design` 后报错文本自动含它，但这只在 PM 已经试错之后才有信息。
3. `/worker` 帮助：`:1553` 注释 `Usage: /worker <claude|codex|pi> [--type <t>] ...`；`:1554` 常量 `"Usage: /worker <claude|codex|pi> [--type coding|review|research] [--model <id>] [--reason <text>] [--key <name>] <task description>"`；命令 `description`（`:1555-1557`）同样只有 `--type <t>`。三处均硬编码。
4. `/mw model set` 帮助：`:1993` `"Usage: /mw model set <role> <prefix/model> — roles: main, coding, review, research (e.g. ...)"` —— **角色名清单硬编码**，`vision` 不同步就永不出现（`/mw` 总帮助 `:2274` 只列子命令名，无角色）。UI 侧 `runMwModelCommand`（`:1972-1983`）`show` 仅 `ctx.ui.notify` 转发 CLI 文本（人可见，非 agent 上下文）。
5. PM 系统提示：`pm/pm-orchestrator.ts:650-658` `PARALLEL_PROTOCOL`（`before_agent_start` 追加，`:719-722`）唯一提到类型的是 `:653` "...一次性派发 N 个 type: research worker"；`:644-645` 注释 "research/review workers are read-only (worker-mode.ts TOOL_ALLOWLISTS)"。无 design/vision/images。
6. `list_tasks` 工具（`:1316-1321` 描述、`:1335-1340` 行格式 `${ownerKeyOf(...)} :: ${taskKey} | ${status} | ${cli}${model...}`）**不回显 `type`** → PM 事后也无法从工具面学到类型集。PM agent 工具面完整清单 = `mw_status`(`:956`)、`dispatch_worker`、`ack_worker_result`、`list_tasks`、`switch_key`、`advance_phase`（+RAG 工具）：**没有任何"列出角色/模型/能力"的工具**（`/mw model show`、`/mw doctor` 都是 `ctx.ui.notify` 的人可见通道）。
7. 技能/文档面：`.agents/skills/agentic-task/**`（`SKILL.md`、`core/pm-mind.md`、`core/dispatch-table.md`、`references/*`）**完全不描述 mw 派发类型或角色**（grep `dispatch_worker`/`type: coding` 零命中；其中的 `dispatch-table.md` 是 AgenticTask 自己的 workflow 路由表）；`AGENTS.md` 亦无。被动文档：`packages/multi-workers/README.md:95`（"角色：`main`…、`coding`…、`review`…、`research`。…"）、`:125`（"`type: coding | review | research`…"）、`UPDATE.md:68`（"role: main/coding/review/research | 写 `.mw/dispatch.yml`…"）；扩展**不注入**这些文件（扩展内 grep `README` 无注入点），PM 只有被要求读时才看到。`packages/multi-workers/skills/mw-rag/SKILL.md:15-17` 有一张类型→RAG 工具表（含 `rag-research`），是 RAG 面唯一的类型清单。`packages/multi-workers/dispatch-table.md` 只有 CLI/provider/use-case 表，**不含类型名或角色名**（唯一相关行是 "Code review / multi-file audit"）。
   → **第 1 问结论**：必须同步的最小文本集 = ①`ui-bridge.ts:1146`（补 `design` + 图片语义）、②`ui-bridge.ts:1554`（`/worker --type`）、③`ui-bridge.ts:1993`（`roles: ..., vision`）、④`PARALLEL_PROTOCOL`（`pm-orchestrator.ts:650-658`，补"引用图片的 UI/界面任务用 `type: design`"）、⑤`dispatch-models.ts:74`（否则 `type: design` 被 `:991` 直接拒）。只改 ⑤ → PM 能派但不会主动想到（**静默不用**）；只改文档（README/UPDATE/skill）→ 对 PM **零影响**（不注入）。

### B. 运行时代码感知点（是否展示 images）
- `mw model show`：`mw.py:3136`（cmd）、`:3219-3233`。角色遍历是动态 `mw_common.DISPATCH_ROLES`（`mw_common.py:138`）→ `vision` 自动出现；但每行只有 `{role}: {value}` 或 `{role}: (unset) → {effective} [{source}]`（`:3226-3233`，含硬编码兜底串 `"(route default: glm-5.3 for pi+timi, gpt-5.6-sol for codex)"`），**无 images 列**。
- `mw doctor`：Python `_doctor_dispatch`（`mw_common.py:1256-1273`）只回 `exists/models/window_model/error`；文本行 `mw_common.py:2300-2308`（`dispatch: {role}={value}, ...; window model {window}`），issue 生成 `mw_common.py:2122-2127` 只覆盖 "dispatch.yml unusable (...)"。TS `/mw doctor` 渲染 `ui-bridge.ts:1758-1765`（`派发模型: {role}={value}; 窗口模型 {window}`）。三处均无能力列。
- conductor 派发：`autopilot/dispatch.py:71 REGISTRY` 每项字段仅 `tools/cli/provider/requires_read_scope/conductor_dispatchable`（`:57-67`），**无模型能力字段**；实际 type 是 `conductor.py:550`（roadmap-writer）、`:937/975`（phase-writer）、`:1007`（verifier）、`:1605`（reviewer）、`:1746`（repair）等调用点的字面量。
- PM 窗口 main 应用：`shared/dispatch-models.ts:221 applyMainModelConfig`（`:222` 见 D）只做 `ctx.modelRegistry.find(provider, modelId)` 命中即 `pi.setModel`，**无能力判断**。
- 唯一能力可见面：`cli/list-models.ts:71` `images: m.input.includes("image") ? "yes" : "no"`（表头 `:80`、行 `:111`）；数据源 `packages/ai/src/types.ts:792 input: ("text" | "image")[]`。

### C. 自动路由的可行位置与 AC-006 冲突面
- **PM 手工路径**：`resolveDispatchType`（`ui-bridge.ts:982-998`）→ `planDispatchFrontmatter`（`:1024-1096`，内含能力门禁姊妹检查 `validateModelValue`，`dispatch-models.ts:166`）→ 写 task.md（tool `:1239-1255`，`/worker` `:1625-1642`）。**未声明类型时的默认行为** = cli 推导（`:988` `const legacy = cli === "codex" ? "codex" : cli === "claude" ? "review" : "coding"`）。最小挂点 = `typeResolution` 算出后、`modelPlan` 之前（tool `:1194`↔`:1239`，`/worker` `:1594`↔`:1625`）：auto-route 必须先定 `taskType`，因为门禁读的是 `roleForTaskType(taskType)`（`:1036`→`dispatch-models.ts:77-79`）。冲突面：AC-006 拒绝"显式 `images: yes` + 解析出的模型非视觉"；若 auto-route 在门禁前把 `coding` 静默升级为 `design`，图片任务会被**改道而不是拒绝** → AC-006 只能覆盖"显式锁定角色/模型（task.md `model:` 头或显式 `type: coding`）"的用例。建议顺序：解析显式 `type`/`model` → auto-route（仅在未声明类型且检测到图片引用时）→ 能力门禁 → 回显改道（现有回显点 `:1272`/`:1648`）。AC-009 零字节约束与 auto-route 不冲突：未引用图片时不触发路由，task.md 逐字节不变。
- **conductor 自动路径**：`autopilot/dispatch.py:dispatch(...)` 的 `task_type` 是**必填位置参数**（签名 `:409`；未知类型拒绝 `:449` `"unknown-type"`；`:458` `"not-conductor-dispatchable: {task_type} is a PM-dispatched type, ..."`）。**没有"未声明类型"这一态**，也没有任何 prompt 内容检测/图片识别。auto-route 在此路径 = 新增调用点（从 roadmap/spec 文本识别 UI 设计子任务），并同步给 `REGISTRY` 加 `design` 及重冻 `test_autopilot_dispatch.py:32` 键集。两条路径的默认语义不同：PM 侧有 cli 推导兜底，conductor 侧 fail-closed；AC-006 的拒绝是 PM 侧独有（conductor 走 registry 拒绝）。

### D. PM 窗口自身看图现状
- 粘贴：`interactive-mode.ts:2807-2826 handleClipboardPaste`（`onPasteImage` 挂载 `:2809`）把剪贴板图片写到临时文件并把**路径**插入编辑器（`:2822` `fs.writeFileSync(filePath, Buffer.from(image.bytes))`、`:2824` `this.editor.insertTextAtCursor?.(filePath)`），**不产生 ImageContent 附件** → "PM 看图"= PM 自己 `read` 那条路径。
- 纯文本 main：`read` 对 `input` 不含 `image` 的模型返回 `core/tools/read.ts:87-91` 的 `"[Current model does not support images. The image will be omitted from this request.]"`（调用点 `read.ts:246`，视觉分支 `:245-252`）；即使 ImageContent 进入请求，`packages/ai/src/api/transform-messages.ts:12-13/35-57` 也会替换为 `"(image omitted: model does not support images)"` / `"(tool image omitted: ...)"`。→ PM 拿不到任何像素信息，只拿到路径 + 降级提示。
- `applyMainModelConfig`（`dispatch-models.ts:221`）第一行 `:222` `if (hasCliModelFlag() || settingsDefaultModel()) return;`（`settingsDefaultModel` `:201`）→ 本机 `~/.pi/agent/settings.json` 有 `defaultModel` 时**永远跳过**，`.mw/dispatch.yml` 的 `main` 即使配成视觉模型也不生效（spec §1.4 明确不改）。可达性差异：现状 PM 自身看图为**不可用**（无像素、无报错，只一行降级文本）；把图交给 `vision` worker 为**可用但需 PM 显式派发**，且失败模式是"配置错角色"时被 AC-006 拒绝（比静默降级可诊断）。

### E. VC 候选（机器可判定，≥4）
1. `ui-bridge.ts` 中 `dispatch_worker` 的 `type` 参数描述文本必须同时含子串 `design` 与 `coding`（常量可导出/快照断言，锚 `:1146`）。
2. 从该描述解析出的类型 token 集合必须等于 `DISPATCHABLE_TYPES ∪ {cli 推导值}`（现状 `:1146` 已漏 `rag-research`，此断言锁住"描述与白名单不再漂移"）。
3. `PARALLEL_PROTOCOL`（`pm-orchestrator.ts:650-658`）冻结文本必须含 `type: design` 与 `type: research` 两条子串。
4. `ui-bridge.ts:1993` 角色帮助文本必须含 `vision`，且其角色集合必须等于 `mw_common.DISPATCH_ROLES`（`mw_common.py:138`，跨语言相等）。
5. 配置 `vision=timi/gpt-5.6-sol` 后，`mw model show`（`mw.py:3219-3233`）或 `mw doctor` 的 `dispatch:` 行（`mw_common.py:2308` / `ui-bridge.ts:1765`）必须含 `vision=` 且含 `images=yes`；配成非视觉模型时含 `images=no`。
6. 任务描述引用存在的 `.png` 且未声明 `type` 时，派发回显（`ui-bridge.ts:1272`/`:1648`）必须含 `type: design` 与 `role: vision`；未引用图片时 task.md 与改造前逐字节一致（与 AC-009 合并）。

### F. 数据缺口（未确认 + 确认方式）
- 描述里的类型 token 解析是否稳定（`:1146` 的引号/或多处同名字符串）：未确认 → 确认方式：写解析器时对 `ui-bridge.ts` 全文做 token 匹配并断言只命中该描述。
- `PARALLEL_PROTOCOL` 是否真的进入 PM 会话（`before_agent_start` 在 PM 窗口的实际触发）：未确认 → 确认方式：tmux 起 PM 窗口，在 trace/会话中 grep `[mw] 并行优先协议` 标记。
- auto-route 的图片检测范围（"引用存在的图片文件" vs 扩展名出现在描述任意处）与误报面：未确认 → 确认方式：AC-006 风险 3 的误报用例（"生成的 png"）+ spec 待确认 2。
- conductor 路径是否需要/允许 `design`：未确认（spec 未写；`REGISTRY` 的 `conductor_dispatchable` 需定值）→ 确认方式：PM 决策后以 `test_autopilot_dispatch.py` 同型断言锁定。
- 若 `mw model show`/`doctor` 增加 images 列，其判定是否只用 registry（无网络）：未确认 → 确认方式：registry 缺失时必须有明确输出（fail-open 文案），并测其耗时 <20ms。
- `/mw doctor` 文本是否被 PM agent 读到（`ui.notify` 是否进上下文）：未确认 → 确认方式：在 PM 窗口执行 `/mw doctor` 后问 agent "输出里 vision 那行是什么"。

## 结论 → 决策映射
- 感知面最小同步集（缺则 PM 不主动用）：`ui-bridge.ts:1146`、`:1554`、`:1993` + `pm-orchestrator.ts:650-658` + `dispatch-models.ts:74`；对应 VC-E1..E4。文档面（`README.md:95/125`、`UPDATE.md:68`、`skills/mw-rag/SKILL.md:15-17`）为**人**的感知面，不构成 PM 主动感知，改动优先级低于前四项。
- 能力可见面：`mw model show`（`mw.py:3219-3233`）与 `mw doctor`（`mw_common.py:2300-2308` / `ui-bridge.ts:1758-1765`）是"人配置 vision 时唯一能看到 images 的地方"，建议二者共用 registry 查询（`types.ts:792`）；VC-E5 固化。
- auto-route 落点：PM 侧在 `resolveDispatchType`↔`planDispatchFrontmatter` 之间（`ui-bridge.ts:1194-1239`，`/worker` `:1594-1625`）判定，先于 AC-006 门禁；AC-006 只对"显式声明/显式锁定角色"生效，两者以"是否显式 `type`"分界（VC-E6）。conductor 侧无挂点，需新调用点 + `REGISTRY`/`conductor_dispatchable` 决策（F 缺口 4）。
- PM 自身看图：维持现状不可用（`interactive-mode.ts:2822-2824` 路径 + `read.ts:87-91` 降级 + `dispatch-models.ts:222` 跳过），不在本 key 范围（spec §1.4）；"把图交给 vision worker"是唯一可用路径，其可诊断性依赖 AC-006/AC-011。
- 交付形状建议：感知面改动是"文案 + 一条 `PARALLEL_PROTOCOL` 规则"，无新机制；无需新注入通道（`before_agent_start` 已有）→ 与 GC-1/GC-2 一致。

[VERIFY] `pm/ui-bridge.ts:1146` 的 `type` 参数描述原文为 "Task type: 'coding' | 'review' | 'research'. Selects the dispatch.yml role (and the worker tool allowlist). Default: derived from cli (pi -> coding, claude -> review, codex -> codex)."，且扩展内 grep `image|vision|png` 只命中 supervision/revision 子串
[VERIFY] `pm/pm-orchestrator.ts:653` 的 `PARALLEL_PROTOCOL` 条目原文含 "一次性派发 N 个 type: research worker"，且该数组（:650-658）不含 design/vision/images 字样
[VERIFY] `mw model show`（mw.py:3219-3233）与 `mw doctor`（mw_common.py:2300-2308、ui-bridge.ts:1758-1765）的渲染模板中均无任何 images/能力列
[VERIFY] `shared/dispatch-models.ts:222` 为 `if (hasCliModelFlag() || settingsDefaultModel()) return;`，即 settings.json 有 defaultModel 时 `.mw/dispatch.yml` 的 main 角色永不套用到 PM 窗口
