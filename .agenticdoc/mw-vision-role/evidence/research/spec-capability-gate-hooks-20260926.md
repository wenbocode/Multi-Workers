# Research: 视觉能力门禁挂点与拒绝路径（RQ-2）

TL;DR
- 唯一正确挂点是 TS 派发面 `planDispatchFrontmatter`（ui-bridge.ts:1024/1048-1051）：与既有拒绝同构，在 `fs.mkdirSync`（:1253）之前返回 `{ok:false}`，`_workers.parallel` 零变化。
- registry 在 `dispatch_worker`（`_context.modelRegistry`，ui-bridge.ts:1156/1247）与 `/worker`（`ctx.modelRegistry`，:1633）都可达；判据 `Model.input`（packages/ai/src/types.ts:792）；fail-open 契约照抄 `validateModelValue`（dispatch-models.ts:166/173-176）。
- Python 侧**零先例**：packages/multi-workers 不读 pi 模型目录、不调 `pi --list-models`；而 `pi --list-models` 自身有 `images` 列（cli/list-models.ts:71）。
- 任务卡给的 `enforceConductorType`（worker-mode.ts ~436-460）**不存在**——真实范例是 `dispatchRefusal`（:442，调用 :626，exit 1 :638）；worker 的 `ctx.model` 只在事件回调可用（:668-671），AC-011 必须挂 `session_start`。

## 决策问题
1. 能力门禁落在哪一层（TS 派发面 / Python launcher / worker 启动）才能覆盖最终执行的模型？
2. 每个 hook 能否拿到 `ctx.modelRegistry`，怎么判一张模型支持图片？
3. 拒绝时函数返回什么、PM/用户看到什么、是否写盘？仓库已有几个同类范式？
4. Python 侧能否判定能力？做不到时漏判哪些回退分支？
5. worker 侧兜底的现成范式与 AC-011 最小改动点，以及可机读的 VC 断言。

## 调研方法与出处
- 只读源码：pm/ui-bridge.ts、shared/dispatch-models.ts、shared/implementation-gate.ts、shared/phase-docs.ts、worker/worker-mode.ts、worker/output-writer.ts、shared/worker-store.ts、pm/task-dispatcher.ts、core/tools/read.ts、core/extensions/types.ts、cli/list-models.ts、packages/ai/src/types.ts、core/model-registry.ts。
- Python：mw_common.py、launcher.py、mw.py（全文/邻域读取；`vision|image` 在 packages/multi-workers 下零命中）。
- 测试范式（供 VC 复用）：test/extensions/agent-team-loop.test.ts:5041 `fakeRegistry`、:5062 `setupTool`、:5117 `taskMdOf`、:5232-5233 fail-open 对照；test_dispatch_models.py `_TS_MIRROR`:159。
- 未发任何真实 API 调用；未运行 pi / worker / e2e。

## 发现

### F1 派发面完整链路（每个环节的 registry 可达性 + 判据）
1. 工具注册 `dispatch_worker` ui-bridge.ts:1111-1116；execute 签名带 `_context` :1156。
2. 写盘前的前置拒绝：RAG `validateRagEnabled` :1177-1180 → 类型 `resolveDispatchType` :1194-1196 → docs gate `dispatchDocGaps` :1207-1219。
3. 模型计划 `planDispatchFrontmatter`（定义 :1024，调用 :1239）→ `effective = requested || configured` :1048 → `validateModelValue(input.registry, ...)` :1050；registry 来自 `_context?.modelRegistry` :1247。**registry 可达（可选）。**
4. 写盘：`fs.mkdirSync(taskDir)` :1253 → task.md :1255 → `dispatchTask` :1257（task-dispatcher.ts:284）→ `WorkerStore.upsert`（worker-store.ts:67）→ 原子写 `_workers.parallel`（:79-81）。
5. `/worker` 斜杠路径同构：registry `ctx.modelRegistry` :1633，拒绝 `ctx.ui.notify(msg, "warning")` :1636-1638。
6. 判据：`Model.input: ("text" | "image")[]`（packages/ai/src/types.ts:792）；读法 `registry.find(provider, modelId)` / `getAll().filter(...)`（core/model-registry.ts:48/56）；前缀→provider 映射 `PREFIX_TO_PROVIDER_ID`（dispatch-models.ts:36-40），`provider` 由 `cli === "pi" ? "timi" : ""` 给出（ui-bridge.ts:1197）。

### F2 拒绝路径的既有范式（派发类全部在写盘前返回）
- 模型值拒绝（同族，最直接的模板）：dispatch-models.ts:185-191 消息 `Model '<v>' not found for provider '<p>' (known ids include: ...). Use /mw model set <role> <v> with a valid id, or omit the model to inherit the configured role default.`；调用方 ui-bridge.ts:1249-1251 返回 tool text；`/worker` 侧 :1635-1638 `ui.notify(..., "warning")`。task.md 与 `_workers.parallel` 零变化。
- docs gate：ui-bridge.ts:1211-1213 `Worker dispatch blocked: key '<k>' is missing phase documentation.\n- <gap>\n<DOC_GATE_HINT>`（phase-docs.ts:142/159）。
- RAG gate：rag/tools.ts:415-419 `RAG config rejected dispatch (<kind>): <msg>`（ui-bridge.ts:1177-1180）。
- 工具级 fail-closed（旁证，非派发）：implementation-gate.ts:686 `gateDecision` → :725 `blocked:true`；消息 :674 `implementation-gate: blocked <tool> targeting code path <p>: ...`；:768 返回 `{block:true, reason}`；索引缺失/不可解析即无 claim（:218-228，fail-closed）。
- worker 启动 fail-closed：worker-mode.ts:442 `dispatchRefusal`；:626 调用 → `appendError` + `writeOutput({exitCode:1, summary:"Task refused at startup (fail-closed).", exitReason: refusal})`（:629-635）+ `writeWorkerLogLine('[worker] refused task=<k> type=<t>: <reason>')`（:636）+ `process.exit(1)`（:638）。`writeWorkerLogLine` 走 `fs.writeSync(1, ...)`（:407-412），launcher 把 stdout 重定向到 worker.log。

### F3 Python 侧能力判定：无先例，且派发面漏判两条回退
- packages/multi-workers 全量 grep `list-models|models.generated|packages/ai|vision|image`：**无能力表、无缓存、无 pi 子命令调用**。唯一 `pi` 调用是 bootstrap 的 `shutil.which("pi")`/`pi --version` 链路检查（mw.py:4429-4433）；mw.py:4309 的 models.dev 是构建期注释，非运行时能力读取。`_doctor_dispatch`（mw_common.py:1256-1274）只报 `dispatch.yml` 角色值 + `window_model`。
- 故 AC-010 目前**无判据来源**：需新增 Python 侧探针（解析 `pi --list-models`，images 列见 cli/list-models.ts:71），或由 TS 侧产出能力 JSON 供 doctor 读。
- 派发面判不到的分支（风险 2 的具体形态）：`resolve_dispatch_model`（mw_common.py:286；:303 task > :307 `config:<role>` > :309 window > :311 `"default"`）里 TS 只校验 `requested || configured`（ui-bridge.ts:1048），因此
  (a) **window 回退** :309-310 → `_effective_entry` launcher.py:186/197-206 → `--model <id>`；
  (b) **per-cli 默认** :311 → `_build_command` launcher.py:476 `model or "glm-5.3"`（timi 路由）；
  (c) 直接 provider 无 model 时 launcher.py:483-487 显式抛错（会失败，不算静默漏判）。

### F4 worker 侧兜底（AC-011）可行性与最小改动点
- 现成范式：`dispatchRefusal`（worker-mode.ts:442-461）返回 reason 字符串；拒绝块 :626-638 就是 AC-011 要的"output.md 落盘 + 机读行 + 非零退出"三件套（见 F2 末条）。
- 但该块跑在 :626，早于 `session_start` 注册（:668），此刻拿不到模型：`ExtensionContext.model`/`modelRegistry` 定义在 core/extensions/types.ts:321/:319，源码注释明确 "ExtensionAPI has no model getter — the resolved id is only readable from an event context"（worker-mode.ts:666-667）。
- 模型确实可读：:668-671 `pi.on("session_start", (_event, ctx) => ctx.model?.id ...)`；`ctx.model.input` 同源可取（types.ts:792），`ctx.modelRegistry` 同回调可用。
- 最小改动点：(1) `TaskMeta` 加 `images?: boolean`，按 `timeout:` 同款解析（TaskMeta:214-243，parseTaskMd:246+）；(2) 图片能力检查搬进 session_start 回调（:668），用 `ctx.model.input` 判定，输出含模型 id 的 `[IMAGE-CAP]` 行（复用 writeWorkerLogLine/appendTrace 的既有通道），再 `writeOutput({exitCode:1,...})` + `process.exit(1)`；(3) 未声明 `images:` 时零分支（AC-011 后半）。

### F5 VC 候选（≥4，均可机检）
1. VC-REFUSE：`fakeRegistry([{provider:"timi", id:"deepseek-v4.1-flash", input:["text"]}])`（扩展 test:5041）+ `models: {vision: timi/deepseek-v4.1-flash}` + `type: design` + 声明图片 → 拒绝消息含 `images` 与 `mw model set vision`；`taskMdOf` 不存在、`_workers.parallel` 行数不变。
2. VC-PASS：同上模型 `input:["text","image"]` → ok，`_workers.parallel` +1，task.md 含 `images: yes`。
3. VC-FAILOPEN-REGISTRY：`execute(params, undefined)` + 声明图片 → ok +1（对照 test:5233）。
4. VC-FAILOPEN-CLI：模型值 `codex_cli/...`（或 `cli !== "pi"`）+ 声明图片 → ok +1（对照 dispatch-models.ts:176 与 test:5232）。
5. VC-WORKER：faux provider（test/suite/harness.ts）跑 `images: yes` 且模型 `input` 无 image → worker.log 含 `[IMAGE-CAP]` + 模型 id、退出码非零、output.md 存在；同 run 内未声明 `images:` 的控制任务正常执行。
6. VC-ZERO：未声明 `images:` 时 frontmatter 与改造前逐字节相等、`_workers.parallel` 该行不变（AC-009）。

### F6 数据缺口
1. `session_start` 在 `-p` 模式下是否**先于首次工具调用**触发（D-116 注释断言是，本次只读未运行验证）→ faux provider 跑一个 `images: yes` 任务，断言 `[IMAGE-CAP]` 出现在首个 `[TOOL]` 之前。
2. worker 的 `ctx.model` 在真实 spawn 中是否恒非空（launcher 只在 model 非空时传 `--model`，launcher.py:489-491）→ worker-mode 单测 + 一次 faux spawn。
3. AC-010 的 Python 判据来源未定（新增 `pi --list-models` 探针 vs TS 产出能力 JSON）；该表格列宽/凭证过滤的解析稳定性未验证。
4. `images:` 头的写侧与 auto-detect 归属在 RQ-3 契约内，本卡只定位挂点。

## 结论 → 决策映射
- 门禁**只挂 TS 派发面**（在 ui-bridge.ts:1050 旁加同构检查）：registry 现成、写盘前拒绝、`_workers.parallel` 零变化 → 直接满足 AC-006/007/008，并天然满足 AC-009 零字节。
- fail-open 三例（registry `undefined` / `*_cli` 前缀 / `cli !== "pi"`）照抄 `validateModelValue` 的早退序（dispatch-models.ts:173/176）。
- 风险 2 成立：window-model 与 per-cli 默认两条回退（mw_common.py:309-311、launcher.py:476）在 TS 侧不可见 → AC-011 必须保留，挂 `session_start`（worker-mode.ts:668），复用 :626-638 三件套。spec「待确认 3 = 保留」由本卡证据支持。
- AC-010 需先定 Python 判据来源（F3/F6-3）；建议 design 阶段决定，不要在本期假定可行。
- 拒绝消息须含确定性修复串 + 显式豁免写法（P-009）：子串 `images` 与 `mw model set vision`。
- 任务卡的 `enforceConductorType` 是过时符号（F4）；design/plan 引用时改用 `dispatchRefusal`。

[VERIFY] worker-mode.ts 中不存在 `enforceConductorType`；启动 fail-closed 是 `dispatchRefusal`（:442，调用 :626，exit 1 :638）
[VERIFY] `pi --list-models` 已有 `images` 列（cli/list-models.ts:71 `m.input.includes("image")`），但 packages/multi-workers 无任何代码调用它或读 packages/ai 模型目录
[VERIFY] TS 派发门禁只校验 `requested || configured`（ui-bridge.ts:1048-1051）；window（mw_common.py:309）与 per-cli 默认（launcher.py:476）两层未校验
[VERIFY] `ctx.model` / `ctx.modelRegistry` 仅在事件上下文中可用（core/extensions/types.ts:319/:321）；worker 在 session_start 捕获模型（worker-mode.ts:668-671）
