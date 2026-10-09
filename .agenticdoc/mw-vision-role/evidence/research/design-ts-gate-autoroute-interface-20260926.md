# Design research: TS 三处改动的签名与分支表（RQ-D4：能力门禁 / auto-route / worker 兜底）

## TL;DR
- 门禁与 auto-route 的唯一写盘前挂点仍是 `pm/ui-bridge.ts:1024 planDispatchFrontmatter`；两条派发入口共用它（tool `:1239-1255`、`/worker` `:1625-1642`），registry 分别来自 `_context?.modelRegistry`（`:1247`）与 `ctx.modelRegistry`（`:1633`），判据 `Model.input`（`packages/ai/src/types.ts:792`）。
- 建议新增纯函数 `modelImageCapability(registry, cli, provider, value): "yes"|"no"|"unknown"`；早退序逐条照抄 `validateModelValue`（`dispatch-models.ts:172-195`），把「可判定但不支持」与「不可判定」分开，后者一律 `"unknown"`（fail-open）。
- `planDispatchFrontmatter` 输入加 `images?: "yes"|"no"` + `description: string`；ok 载荷加 `type: string`（auto-route 后的有效类型）。两处回显（`:1272` / `:1648`）必须改用 `modelPlan.type`，否则 auto-route 后回显仍是旧 `typeField`。
- worker 兜底：`TaskMeta.images`（`worker-mode.ts:234`）解析插在 `origin:` 之后（`:301-303`）；检查放 `session_start`（`:738`），复用 `dispatchRefusal` 三件套（def `:464`，范式 `:693-704`，`exit(1)` `:704`）。
- **行号漂移**：`worker-mode.ts` 当前工作区被并行会话改过（+169/-13）；任务卡与 spec 引的 `:214/:442/:626/:668` 是 HEAD 附近旧号，工作区现值 `:234/:464/:693/:738`。`ui-bridge.ts` / `dispatch-models.ts` 干净，行号=HEAD。

## 决策问题
1. 门禁/auto-route 在 `planDispatchFrontmatter` 内的字段计算顺序、返回结构、写盘前拒绝点。
2. 能力三态 API 与 fail-open 分支；registry 可能 undefined 的全部情形。
3. 两条派发入口的调用与回显接线。
4. worker `[IMAGE-CAP]` 的落盘/退出契约与插入行号。
5. auto-route 机读来源写 `model-reason:` / `_workers.parallel` / trace.log 哪个。
6. 可复制的 L1 测试骨架（fakeRegistry / faux provider / `_context`）。

## 调研方法与出处
只读全量读：`pm/ui-bridge.ts`、`shared/dispatch-models.ts`、`worker/worker-mode.ts`、`worker/output-writer.ts`、`packages/ai/src/types.ts`、`core/model-registry.ts`、`core/extensions/types.ts`、`test/extensions/agent-team-loop.test.ts`、`test/suite/harness.ts`、`packages/ai/src/providers/faux.ts`，以及本 key 的 spec/design（D-001/D-004/D-010、AC-006/007/008/011/016/017）。未运行测试/LLM，未改源码。

## 发现

### Q1 `planDispatchFrontmatter` 现状（`ui-bridge.ts`）
- 定义 `:1024-1096`，签名 `(input: { cwd; cli; provider; taskType; phase?; model; modelReason; registry: ModelRegistry | undefined }): { ok: true; frontmatter: string; echo: string } | { ok: false; message: string }`。
- type 解析 `resolveDispatchType` `:982-998`：显式值必须 ∈ `DISPATCHABLE_TYPES`（`:992`），失败文案 `:994 Invalid type '<v>'. Must be one of: <join>.`；省略按 cli 推导（`:988 codex→codex / claude→review / 否则 coding`）。
- 字段顺序：`:1036 role=roleForTaskType(taskType)` → `:1037 configured=readRoleModel(cwd, role) ?? ""` → `:1038 requested=model.trim()` → `:1039 reason=oneLineReason(modelReason)` → `:1040-1043 typeLines = "type: T\n"`（phase 非空再追加 `phase: P\n`）→ `:1048 effective=requested||configured` → `:1050-1051 validateModelValue(...)` 失败即 `{ok:false,message}` → `:1054` 无 requested（echo configured/route default）→ `:1066` requested===configured 不 pin → `:1074-1081` configured 且无 reason 拒绝 → `:1083-1088` 行数组 `type[,phase][,model][,model-reason]` → `:1089-1095 echo`。
- 两个入口：tool `:1194` typeResolution → `:1239` plan → `:1249-1250` 返回拒绝文本 → `:1252-1255` mkdir+写 task.md → `:1272` 回显；`/worker` `:1594` → `:1625` → `:1635-1638 ui.notify(...,"warning")` → `:1642` 写 → `:1648` 回显。两边 echo 都用 `modelPlan.echo`，type 用外层 `typeField`（auto-route 需改这里）。

### Q2 `validateModelValue` 完整 fail-open 分支（`dispatch-models.ts`）
- `:152 interface ModelValidation { ok: boolean; message: string }`；`:166` 签名 `(registry: ModelRegistry | undefined, cli: string, taskProvider: string, value: string): ModelValidation`。
- 分支原文：`:172 trimmed` → `:173 if (!trimmed || !registry || cli.toLowerCase() !== "pi") return { ok: true, message: "" }`（**主 fail-open**）→ `:175` 无 modelId `Model value '<v>' carries no model id.`（拒绝）→ `:176` `CLI_EXECUTOR_PREFIXES.includes(prefix)` → ok（`:83 = ["codex_cli","claude_cli"]`）→ `:177-181` 前缀不在 `PREFIX_TO_PROVIDER_ID`（`:38`）→ `unknown prefix '...' (valid: ...)`（拒绝）→ `:182` 无 provider → ok → `:183-187` 该 provider 在 registry 无任何 id → ok（**目录冷 fail-open**）→ `:188 registry.find(provider, modelId)` 命中 ok → `:189-196` 未命中拒绝 `Model '<v>' not found for provider '<p>' (known ids include: <5>). Use /mw model set <role> <v> with a valid id, or omit the model to inherit the configured role default.`
- 表原文：`DISPATCH_ROLE_BY_TYPE` `:58-71`（coding/phase-writer/repair/roadmap-writer→coding；review/verifier/reviewer→review；research/rag-research→research）；`DISPATCHABLE_TYPES` `:74 ["coding","review","research","rag-research"]`；`roleForTaskType` `:77-79`（未知→coding）。`TOOL_ALLOWLISTS` 在 `worker-mode.ts:52-83`（10 键，无 vision）；TS 侧**没有** `DISPATCH_ROLES` 常量（只有 Python `mw_common.py:138`）。

### Q3 registry / `Model.input` 形态
- `ExtensionContext.modelRegistry: ModelRegistry`（`core/extensions/types.ts:319`，**类型上非可选**）；`model: Model<any> | undefined`（`:321`）。
- `ModelRegistry.find(provider, modelId): Model<Api> | undefined`（`core/model-registry.ts:56`）；`getAll(): Model<Api>[]`（`:48`）；`getError()`（`:47`）。`Model.input: ("text" | "image")[]`（`packages/ai/src/types.ts:792`）。
- registry 运行时 undefined 的全部情形：(a) 非标准 ctx——测试 `fakeCmdCtx().ctx` 根本没有该字段（`agent-team-loop.test.ts:5080-5082` 因此分叉，`undefined` 时 `_context?.modelRegistry` 为 undefined 走 fail-open）；(b) defensive `_context?.` 写法本身允许。生产 ExtensionContext 恒有 registry，但 `getAll()` 可能为空（models.json 坏/未刷新）→ 走 `:187` fail-open。
- 签名建议：`export type ImageCapability = "yes" | "no" | "unknown";` + `export function modelImageCapability(registry: ModelRegistry | undefined, cli: string, provider: string, value: string): ImageCapability`。分支表见 Q2 早退序：仅 `ok:true` 且 `find` 命中时取 `input.includes("image") ? "yes" : "no"`；空值/无 registry/非 pi/CLI 前缀/未知前缀/无 provider/目录为空/未命中 → `"unknown"`（未命中的拒绝由 `validateModelValue` 负责，能力函数绝不发明失败）。
- 配套建议：`export function detectImageNeed(cwd: string, description: string): boolean`（扩展名集同 `read.ts:212`；token 含 `*?[]`、含 `://`、`fs.existsSync(resolve(cwd,token))` 为假都跳过；`images: no` 由调用方最高优先短路）。

### Q4 worker 侧兜底
- `TaskMeta`（`worker-mode.ts:234-266`）：`type/phase/phases/taskKey/agenticdocRoot/origin/trueAgenticdocRoot/timeoutMin/readScope/denyGlobs/readFileCap/readByteCap/ragChatBudget/ragTimeBudgetS`；`parseTaskMd` `:268`，逐行前缀扫描 `:288-330`，`origin:` 在 `:301-303`。建议紧接 `:303` 加同型解析：`if (trimmed.startsWith("images:")) images = trimmed.slice("images:".length).trim() === "yes"`（未声明 = undefined，零分支）。
- `dispatchRefusal(meta): string | undefined`（def `:464-481`，只对 `origin==="conductor"` 生效 `:465`）不是 AC-011 的调用体；三件套范式在 `:693-704`：`appendError`（trace.log `[ERROR]`，`output-writer.ts:238`）→ `writeOutput({exitCode:1, summary:"Task refused at startup (fail-closed).", exitReason})`（output.md，`output-writer.ts:45`）→ `writeWorkerLogLine("[worker] refused ...")`（`:426-434`，`fs.writeSync(1,…)`，launcher 重定向到 worker.log）→ `process.exit(1)`。
- `session_start` 回调 `:738-741`：`pi.on("session_start", (_event, ctx) => { const modelId = ctx.model?.id; if (modelId) appendModel(...) })`；`ctx.model` / `ctx.modelRegistry` 只在此事件上下文可用（`ExtensionAPI` 无模型 getter，注释 `:736-737`）。`:693` 的旧拒绝块早于事件注册，故 AC-011 只能挂 `:738`。
- `[IMAGE-CAP]` 伪代码（插入 `:738` 回调体、`appendModel` 之后）：
```
if (meta.images === true) {
  const m = ctx.model;
  if (m && Array.isArray(m.input) && !m.input.includes("image")) {
    const line = `[IMAGE-CAP] model=${m.id} provider=${m.provider} task=${meta.taskKey} declared=images:yes`;
    writeWorkerLogLine(line);                              // worker.log（机读行）
    appendError(meta.taskKey, meta.agenticdocRoot, line);  // trace.log
    writeOutput({ taskKey: meta.taskKey, agenticdocRoot: meta.agenticdocRoot,
      exitCode: 1, summary: "Task refused (image capability).", exitReason: line }); // output.md
    killTrackedDetachedChildren();
    process.exit(1);
  }
  if (!m) appendTrace(meta.taskKey, meta.agenticdocRoot, "[IMAGE-CAP] unknown model, fail-open");
}
```

### Q5 留证通道
- `model-reason:` 唯一写侧 = `ui-bridge.ts:1088`（`planDispatchFrontmatter`）；全仓**无读者**（worker `parseTaskMd` 不解析）。
- trace 既有 API：`appendTrace`（`output-writer.ts:91`，`[FLOW] ts <line>`）、私有 `appendLifecycleLine`（`:101`）、结构化 `appendModel`（`:128`，worker session_start 写、watch 已消费）、`appendError`（`:238`）。`_workers.parallel` 是队列状态（`dispatchTask`→`WorkerStore.upsert`），语义是行/状态而非来源证据。
- **推荐（=D-010）**：`model-reason: auto-route: <src-role> -> vision: <reason>`（复用既有头）+ 两处回显写 `type: <effective>, role: <effective role>, model-source: auto-route`。**否决**：仅回显（会话压缩丢证）、新增 `model-source:` 头（新契约面且无读者）、写 `_workers.parallel`（语义错位 + 破行格式）。

### Q6 L1 测试骨架（`test/extensions/agent-team-loop.test.ts`）
- 可复用件：`fakeRegistry` `:5041`（只需 `getAll`+`find`）、`setupTool` `:5062`、`setupCommand` `:5089`、`taskMdOf` `:5117`、`workerDirExists` `:5121`、legacy golden `:5331`；fail-open 对照 `:5222-5236`（`validateModelValue(undefined,...).ok === true`）。
- faux provider：`createHarness({ models: [{ id: "faux-text", input: ["text"] }] })`，`harness.ts:134` 把 `input` 透传进 registry；**faux 默认 `input=["text","image"]`**（`providers/faux.ts:482`）→ 纯文本用例必须显式传。
- 现有 `fakeRegistry` 的 entries 只有 `{provider,id}`（`:5042` spread）→ 需扩成支持 `input`，否则能力门禁恒 `"unknown"`（fail-open，测试会假绿）。骨架：
```
const fakeReg = (ms: Array<{provider:string;id:string;input:("text"|"image")[]}>) =>
  ({ getAll:()=>ms as Model<any>[], find:(p:string,i:string)=>ms.find(m=>m.provider===p&&m.id===i) } as ModelRegistry);
const TEXT = () => fakeReg([{provider:"timi",id:"timi-text",input:["text"]}]);
const VISION = () => fakeReg([{provider:"timi",id:"timi-vision",input:["text","image"]}]);
const yml = "models:\n  vision: timi/timi-vision\n  review: timi/timi-text\n";
// AC-006 拒绝（task 目录不存在）
const a = await setupTool(yml);
expect(await a.execute({task_key:"t1",description:"work",type:"vision",images:"yes"}, TEXT()))
  .toContain("mw model set vision");
expect(workerDirExists(a.root,"t1")).toBe(false);
// AC-007 放行 + 顺序 type < phase < images < model
const b = await setupTool(yml);
await b.execute({task_key:"t2",description:"work",type:"vision",images:"yes"}, VISION());
expect(taskMdOf(b.root,"t2")).toContain("images: yes\n");
// AC-008 fail-open
const c = await setupTool(yml);
expect(await c.execute({task_key:"t3",description:"work",type:"vision",images:"yes"}))
  .toContain("Dispatched worker");
// AC-016 auto-route：无显式 model + 存在的 png + 角色纯文本 + vision 视觉
fs.writeFileSync(path.join(d.root,"login.png"),"x");
const r = await d.execute({task_key:"t4",description:"match docs/ui/login.png"}, VISION_AND_TEXT);
expect(taskMdOf(d.root,"t4")).toContain("model-reason: auto-route");
expect(r).toContain("role: vision");
```\n
## 结论 → 决策映射
- **门禁**：在 `:1050-1051` validateModelValue 之后、`:1054` 之前插能力分支：`imagesRequested && modelImageCapability(...)==="no"` → `{ ok:false, message }`；`:1252` 之后任何写盘不得到达。消息须同时含 `images`、`mw model set vision`、豁免写法 `images: no`（AC-006）。
- **auto-route**：同函数内、`:1036 role` 之前判定（需要 `declaredType` 标记与 `imagesRequested`）。有效类型与模型改判后，`ok` 载荷新增 `type`，`:1272`/`:1648` 回显改读 `modelPlan.type`；来源证据走 `:1088` 同一行分支（`model-reason: auto-route: ...`）。顺序：解析显式 type/model → auto-route → 能力门禁 → 回显。
- **worker**：字段/伪代码如 Q4；退出码 1，三通道（worker.log/trace.log/output.md）与 `dispatchRefusal` 完全同构（AC-011）。
- **留证**：D-010 原样采纳（Q5）。
- **必须由 design 拍板的冲突（本卡实证）**：spec §4 边界写「显式 `type:` 或显式 `model:` 存在时不 auto-route」，但 **AC-017 明确要求 `type: review`（显式）+ review 角色纯文本时也路由到 vision**，与 D-004 互斥。两种实现：(A) 只按显式 `model:` 阻断（`type:` 不阻断，读 AC-016/017 字面）；(B) `type:` 也阻断（读 spec §4/D-004，但 AC-017 无法成立）。建议按 AC 优先取 (A)，并把 frontmatter 的 `type:` 行一并改判为 `vision`；若取 (B) 则 AC-017 必须改写或降级为「同能力即同结论」的弱断言。
- **依赖**：AC-017 需要 `DISPATCH_ROLE_BY_TYPE["vision"]="vision"` 与 `DISPATCHABLE_TYPES`+`"vision"`（现状均缺，`:58`/`:74`）；`planDispatchFrontmatter` 需同时支持 `phase` 与 `images` 的组装顺序 `type < phase < images < model`。

[VERIFY] `planDispatchFrontmatter` 的拒绝发生在 `fs.mkdirSync`/写 task.md 之前（`ui-bridge.ts:1051` 早于 `:1252-1255`），两入口分别用 `_context?.modelRegistry`(:1247) 与 `ctx.modelRegistry`(:1633)
[VERIFY] `validateModelValue` 的 fail-open 是 `:173` 一条主早退 + `:176`/`:182`/`:187`/`:188` 四条次早退；`:175/:178-180/:189-196` 才是拒绝（`dispatch-models.ts`）
[VERIFY] `worker-mode.ts` 工作区行号 = `TaskMeta:234 / parseTaskMd:268 / dispatchRefusal:464 / refusal 调用:693 / session_start:738`（HEAD 为 210/244/439/623/665；任务卡引用的 214/246/442/626/668 两者都不是）
[VERIFY] `model-reason:` 只有写侧 `ui-bridge.ts:1088`、全仓无读侧；worker 侧 `ctx.model` 仅 `session_start`(:738) 可读（`core/extensions/types.ts:321`）
[VERIFY] L1 骨架必须扩 `fakeRegistry`(:5041) 的 entry 支持 `input`，否则能力判定恒 unknown；faux 默认 `input=["text","image"]`（`providers/faux.ts:482`）